# Distinguishing the Standard Kafka Binder from the Kafka Streams Binder

Spring Cloud Stream provides two binders commonly used when building applications on Apache Kafka: the **standard Kafka Binder** and the **Kafka Streams Binder**. Both connect applications to Kafka topics and use Spring Cloud Stream's function and binding configuration, yet they serve two distinct programming models.

The standard Kafka Binder integrates with Spring Kafka to send and receive messages via producers, consumers, and listener containers. Applications typically process individual payloads or `Message<?>` objects using `Supplier`, `Function`, and `Consumer`. The Kafka Streams Binder integrates the Kafka Streams DSL to build stream-processing topologies with `KStream`, `KTable`, and `GlobalKTable`, supporting continuous transformations, joins, windowing, aggregations, and state stores.

This lesson belongs to the **Kafka Binder** chapter of the `SPRING_CLOUD_STREAM` module. We will compare the two binders across programming model, runtime, configuration, consumer groups, state, scaling, delivery guarantees, and testing so you can pick the right tool for each problem.

## 1. Two Binders, Two Processing Models

The standard Kafka Binder treats Kafka as a message transport system. Producers send records to topics; consumers read records via consumer groups; Spring Cloud Stream converts payloads into Java types and invokes the application's function or consumer.

The Kafka Streams Binder treats Kafka as the source and sink of a stream-processing topology. The application declares operations over streams and tables; the Kafka Streams runtime constructs the topology and manages tasks, state stores, changelogs, repartitions, and offsets.

```text
Standard Kafka Binder

Kafka topic
    |
    v
Spring Kafka listener container
    |
    v
Spring Message / Java payload
    |
    v
Supplier / Function / Consumer
    |
    v
Output binding -> Kafka topic


Kafka Streams Binder

Kafka topic(s)
    |
    v
Kafka Streams source node
    |
    v
KStream / KTable operations
    |
    +--> filter / map / join / window / aggregate
    |
    v
Kafka Streams sink node
    |
    v
Kafka topic(s)
```

These two binders are not two names for the same mode. Choosing a binder determines function signatures, runtime behavior, state management, and message-processing configuration.

The two commonly used starter dependencies are:

| Binder | Maven Artifact |
|---|---|
| Standard Kafka Binder | `spring-cloud-starter-stream-kafka` |
| Kafka Streams Binder | `spring-cloud-starter-stream-kafka-streams` |

Manage dependencies via the project's Spring Cloud release train/BOM so that Spring Cloud Stream, Spring Kafka, and Kafka Streams versions remain compatible. Do not manually upgrade a Kafka Streams library beyond the release train's compatibility matrix.

## 2. High-Level Comparison

| Criterion | Standard Kafka Binder | Kafka Streams Binder |
|---|---|---|
| Primary goal | Send/receive messages over Kafka | Build stream-processing topologies on Kafka |
| Processing API | Java payloads, `Message<?>`, `Supplier`/`Function`/`Consumer` | Kafka Streams DSL: `KStream`, `KTable`, `GlobalKTable` |
| Runtime | Spring Kafka producers and listener containers | Kafka Streams runtime, stream threads, and tasks |
| State management | Application manages state itself, usually via database/cache | Local state stores and changelog topics managed by Kafka Streams |
| Joins and windowing | Implemented manually or delegated to external systems | Native `join`, `window`, and `aggregate` operators in the DSL |
| Consumer identity | Binding's consumer `group` | Kafka Streams application's `application.id` |
| Scaling | Consumer group distributes partitions across consumers | Kafka Streams distributes tasks/partitions across instances and stream threads |
| Offsets and recovery | Driven by listener container, ack mode, and binder configuration | Kafka Streams manages offsets, tasks, state restoration, and processing guarantees |
| Best fit | Event integration, command handlers, general message processing | Stateful stream processing, joins, windowing, aggregations, and complex topologies |

The standard Kafka Binder fits the majority of business messaging flows. The Kafka Streams Binder fits problems that genuinely require topology-managed stream operations and state.

## 3. How Does the Standard Kafka Binder Process Messages?

With the standard Kafka Binder, a function receives a Java payload already converted by a message converter. For example, an order-event enrichment function:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String customerId, String status) {}

record EnrichedOrderEvent(
    String orderId,
    String customerId,
    String status,
    String source
) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderEvent, EnrichedOrderEvent> enrichOrder() {
        return event -> new EnrichedOrderEvent(
            event.orderId(),
            event.customerId(),
            event.status(),
            "order-service"
        );
    }
}
```

Binding configuration:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      kafka:
        binder:
          brokers: localhost:9092
      bindings:
        enrichOrder-in-0:
          destination: orders.created
          group: order-enrichment
          content-type: application/json
        enrichOrder-out-0:
          destination: orders.enriched
          content-type: application/json
```

The function receives an `OrderEvent`, builds an `EnrichedOrderEvent`, and the output binding sends the payload to the `orders.enriched` topic. The application does not need to know about Kafka `ConsumerRecord` or Kafka Streams topologies to perform this simple transformation.

The standard Kafka Binder works well when the logic processes individual messages or independent events, calls a database or API, applies business checks, and emits an output message. The application can accept `Message<T>` when it needs headers, correlation IDs, or transport metadata.

## 4. The Kafka Streams Binder Uses the Kafka Streams DSL

The Kafka Streams Binder brings Kafka Streams types directly into function signatures. For example, a function receiving `KStream<String, String>` and normalizing content:

```java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class StreamTopologyConfiguration {

    @Bean
    Function<KStream<String, String>, KStream<String, String>> normalizeOrders() {
        return input -> input
            .filter((key, value) -> value != null && !value.isBlank())
            .mapValues(String::trim)
            .mapValues(String::toUpperCase);
    }
}
```

This function defines a topology: read records from a source topic, drop blank values, normalize payloads, and write results to an output binding. It is not invoked once per message like the standard Kafka Binder's `Function<OrderEvent, Result>`. The Kafka Streams Binder invokes the function to build the topology; the Kafka Streams runtime then executes that topology continuously as records arrive.

Kafka Streams Binder configuration:

```yaml
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
            applicationId: order-normalizer
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
              default.value.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
```

`applicationId` is the identifier of the Kafka Streams application and is used to manage consumer groups, state, and internal resources. `default.key.serde` and `default.value.serde` define default key and value serialization/deserialization. For complex data types, configure compatible `Serde` implementations or specify per-operator/topology `Serde` instances.

Note: the example uses strings to clearly illustrate `Serde` configuration. When using JSON, Avro, Protobuf, or Java record types, configure the corresponding `Serde` and test against real schemas; the standard Kafka Binder's message converter does not automatically replace Kafka Streams `Serde`.

## 5. Differences in Function Signatures

The function signature is usually a clear indicator of which binder is being used:

| Function Signature | Appropriate Binder | Meaning |
|---|---|---|
| `Function<OrderEvent, OrderResult>` | Standard Kafka Binder | Processes one payload and returns one payload |
| `Consumer<OrderEvent>` | Standard Kafka Binder | Receives one payload and performs an action |
| `Supplier<OrderEvent>` | Standard Kafka Binder | Produces outbound messages via supplier/poller mechanism |
| `Function<KStream<K,V>, KStream<K2,V2>>` | Kafka Streams Binder | Builds a stream-to-stream topology |
| `Function<KStream<K,V>, KTable<K2,V2>>` | Kafka Streams Binder | Converts a stream into a state table |
| `BiFunction<KStream<K,V>, KTable<K2,V2>, KStream<K3,V3>>` | Kafka Streams Binder | Combines two input streams/tables |

Do not guess the binder from the bean name alone. Check the dependencies, selected binder, and parameter types. A `Function<Flux<T>, Flux<R>>` belongs to standard Spring Cloud Stream reactive processing, not the Kafka Streams DSL just because it handles multiple items.

## 6. KStream, KTable, and GlobalKTable

The Kafka Streams DSL provides distinct abstractions:

- **`KStream<K,V>`** represents a stream of records. Each record is an independent event; operators such as `filter`, `map`, `flatMap`, `branch`, and `merge` typically transform the event stream.
- **`KTable<K,V>`** represents the latest state per key. A record updating a key replaces the previous value in the table. `KTable` fits changelog data or key-based projections.
- **`GlobalKTable<K,V>`** represents a table materialized on every instance of the Kafka Streams application. It is useful for certain join patterns needing a global lookup table, at the cost of each instance maintaining a full copy of the state.

Examples of usage:

| Data | Typically Appropriate Abstraction |
|---|---|
| `OrderPlaced`, `OrderShipped` events | `KStream` |
| Latest state of an account by `accountId` | `KTable` |
| Small country-code reference table queried on every instance | `GlobalKTable` |

A `KTable` is not merely an in-memory collection. It represents keyed state updated from a changelog stream. Stateful operators require appropriate keys, partitioning, and `Serde`.

## 7. State Stores and State Recovery

An important distinction is that Kafka Streams natively supports stateful processing. Operations such as `count`, `aggregate`, `reduce`, windowed aggregations, and joins may require state stores.

State stores are typically stored locally on the processing instance. Kafka Streams uses changelog topics to record state mutations so state can be restored when a task moves to another instance or a process restarts. For operations requiring repartitioning, Kafka Streams can create repartition topics to co-locate records with the same key into the same partition before computing.

```text
Input topic
    |
    v
Repartition (if needed)
    |
    v
Stateful operator
    |
    +----> Local state store
    |             |
    |             +----> Changelog topic
    |
    v
Output topic
```

The standard Kafka Binder does not create state stores for functions. If a regular consumer needs state, the application typically manages state in a database, cache, or external store. That is the right choice when state is business data requiring independent queries, sharing across multiple services, or its own lifecycle.

Kafka Streams state stores fit state tightly coupled to a topology and key/partition. Plan local disk capacity, changelog retention, restoration time, and state querying mechanisms before moving to production.

## 8. Joins, Windowing, and Aggregations

The Kafka Streams Binder excels when processing relationships across event streams:

- Joining two `KStream`s by key within a time window.
- Joining a `KStream` with a `KTable` to enrich events with the latest reference state.
- Using a `GlobalKTable` for lookup tables replicated across instances.
- Windowed aggregations to count or summarize events over tumbling, hopping, or session windows.
- Materializing results into state stores for querying or downstream processing.

Example problem: summing order value per customer in every 5-minute window. With the Kafka Streams DSL, you can group by `customerId`, apply windowed aggregation, and emit results. Doing this with the standard Kafka Binder requires the application to manually manage state, window boundaries, late-arriving events, and update consistency.

Kafka Streams does not solve every windowing business concern automatically. You must specify timestamp extractors, grace periods, retention, keys, `Serde`, and late-record handling. Misconfiguration can cause results to be dropped or state stores to retain data longer than expected.

## 9. Consumer Groups and application.id

The standard Kafka Binder uses `group` on an input binding to create a consumer group. Consumers in the same group coordinate to divide topic partitions. If `group` differs, groups generally read independently and maintain separate offsets.

The Kafka Streams Binder uses `application.id` to identify a Kafka Streams application. Instances sharing the same `application.id` belong to the same logical application; Kafka Streams distributes tasks across instances. A separate logical application needs a different `application.id` to process independently.

| Concept | Standard Kafka Binder | Kafka Streams Binder |
|---|---|---|
| Processing group identity | Input binding `group` | `application.id` |
| Load sharing | Kafka consumer group assigns partitions to consumers | Kafka Streams assigns tasks/partitions to instances and stream threads |
| Internal state | No built-in Kafka Streams state stores | State stores and changelogs tied to the application |
| Independent consumption | Use a different `group` | Use a different `application.id` |

Do not generate a new `application.id` per replica. If every replica uses a different ID, each replica acts as an independent application reading the entire dataset instead of sharing load. Conversely, two independent topologies must not share an application ID if they require separate offsets and state.

## 10. Scaling and Parallelism

With the standard Kafka Binder, parallelism is bounded by partition count and the number of consumers in the group. If a topic has six partitions and the group has three consumers, each consumer may be assigned multiple partitions. If there are ten consumers, some consumers will receive no partitions.

With Kafka Streams, Kafka divides the topology into tasks based on source topic partitions. Each instance can run multiple stream threads; tasks are distributed across threads and instances. Increasing stream threads does not create additional partitions. Parallelism remains bounded by topology partitions and repartition stages.

When scaling a Kafka Streams application:

1. Keep `application.id` identical across replicas of the same topology.
2. Scale instance/stream-thread counts based on CPU and I/O capacity.
3. Check partition counts of source and repartition topics.
4. Monitor rebalances, task assignments, and state restoration.
5. Evaluate local state store sizes and restoration times when tasks migrate across instances.

Adding instances does not always raise throughput if partition count is low, a hot key skews traffic, or state stores are I/O-bound. Increasing parallelism may require redesigning partition keys and topologies, keeping in mind that changing partition counts can also impact ordering and data distribution.

## 11. Serde and MessageConverter Are Not the Same

The standard Kafka Binder relies heavily on Spring message conversion to translate payloads between bytes/messages and Java types. Content types like `application/json` help the framework pick a converter.

Kafka Streams uses Kafka `Serde` (serializer/deserializer) for record keys and values within a topology. `Serde` must be defined appropriately for every data type and operator. Declaring `content-type: application/json` on a binding does not automatically replace Kafka Streams `Serde`.

| Component | Role |
|---|---|
| Spring `MessageConverter` | Converts Spring message payloads, such as JSON to DTO |
| Kafka `Serializer`/`Deserializer` | Converts Kafka keys/values to bytes and back |
| Kafka Streams `Serde<T>` | Bundles serializer and deserializer for type `T` inside a topology |

For strings, `Serdes.String()` can be used. For JSON, Avro, or Protobuf, configure the corresponding `Serde`, schema registry if used, and schema compatibility policy. If a key or value fails deserialization, errors typically surface when Kafka Streams executes the topology or restores state.

## 12. Delivery Semantics and Transactions

The standard Kafka Binder offers producer transactions, acknowledgements, offset commits, and error handling via Spring Kafka/Kafka Binder options. Exact configuration depends on version and binding type. Kafka Streams has Kafka Streams processing guarantees, such as `at_least_once` or `exactly_once_v2` on supported Kafka versions.

With Kafka Streams, `exactly_once_v2` can coordinate reading offsets, executing the topology, and writing outputs/state changelogs within Kafka transactions. It does not automatically encompass an external database, HTTP API, or email provider. If a function calls external systems, proper idempotency, outbox, or saga patterns are still needed.

Example declaring processing guarantee in the Kafka Streams Binder:

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              processing.guarantee: exactly_once_v2
```

Enable this mode only when the broker and Kafka Streams version support it, the cluster is properly configured for transactions, and the application accepts the associated operational overhead. Test failover, transaction timeouts, and state recovery in a production-like environment.

With the standard Kafka Binder, producer transactions and offset commits likewise have their own scope. Do not treat `send()` as proof that a consumer processed a record successfully, or assume side effects outside Kafka are automatically exactly-once.

In both models, consumers and processors must account for restarts, rebalances, retries, duplicates, and poison messages. Choose delivery semantics based on business requirements and test against the actual broker configuration.

## 13. Error Handling and DLQ

The standard Kafka Binder supports consumer retries and dead-letter topics via Kafka binder properties, such as `enableDlq` and DLQ naming in supported versions. When a message handler fails, the framework can retry and then route failed messages to the DLQ as configured.

Kafka Streams handles errors within the topology and provides dedicated hooks for deserialization, production, processing, and uncaught exceptions. Do not assume standard Kafka Binder DLQ settings automatically apply to the Kafka Streams Binder. With Kafka Streams, inspect `DeserializationExceptionHandler`, `ProductionExceptionHandler`, `StreamsUncaughtExceptionHandler`, or error-handling mechanisms supported by your binder/Kafka Streams version.

Categories of errors to distinguish:

- Deserialization errors: bytes cannot be converted into key/value via `Serde`.
- Processing errors: exceptions inside an operator or user function.
- Production errors: broker rejects or producer fails to send output.
- State store errors: local state or changelog fails to restore or write.
- Business errors: structurally valid data violates business rules.

A DLQ is one part of an error-handling strategy, not a substitute for classifying errors and defining replay procedures. Capture event ID, source topic, partition, offset, and exception metadata whenever possible for investigation.

## 14. Which Configuration Belongs to Which Binder?

The two binders have separate configuration namespaces. Mixing properties is a common reason applications start up yet behave unexpectedly.

| Setting | Standard Kafka Binder | Kafka Streams Binder |
|---|---|---|
| Brokers | `spring.cloud.stream.kafka.binder.brokers` | `spring.cloud.stream.kafka.streams.binder.brokers` |
| Consumer identity | `spring.cloud.stream.bindings.<name>.group` | `spring.cloud.stream.kafka.streams.binder.applicationId` |
| Producer/consumer options | `spring.cloud.stream.kafka.bindings.<name>...` | `spring.cloud.stream.kafka.streams.bindings.<name>...` and Kafka Streams configuration |
| Key/value conversion | Spring message conversion and Kafka serializer/deserializer | Kafka Streams `Serde` |
| Runtime processing config | Spring Kafka listener/producer properties | `spring.cloud.stream.kafka.streams.binder.configuration` |

For example, `spring.cloud.stream.kafka.binder.brokers` configures the standard Kafka Binder. It does not replace broker configuration for the Kafka Streams Binder. When an application uses both binders, explicitly assign the appropriate binder to each binding or function and avoid ambiguous defaults.

Exact property names and configuration capabilities can change across release trains. Use properties matching the running versions of Spring Cloud Stream, Spring Kafka, and Kafka Streams; do not copy properties from one binder to the other.

## 15. When Should You Choose the Standard Kafka Binder?

Choose the standard Kafka Binder when:

- Each message is an independent business request or event.
- Functions receive Java DTOs, run business checks, call a database/API, and emit outputs.
- Kafka needs to integrate with other messaging systems via the binding model.
- State is managed in a database or dedicated storage service.
- Kafka Streams DSL features like joins, windows, or stateful aggregations are unnecessary.
- You want familiar Spring Kafka listener, producer, and message-handling mechanics.

Example: receive `PaymentRequested`, call a payment service, save the outcome, and emit `PaymentAuthorized`. This is a message workflow; the standard Kafka Binder is usually the natural fit.

## 16. When Should You Choose the Kafka Streams Binder?

Choose the Kafka Streams Binder when:

- Multiple topics must be joined by key or within a time window.
- Events must be continuously aggregated, such as total order value per customer every 5 minutes.
- A `KTable`/`GlobalKTable` is needed for lookups or maintaining state per key.
- Local state stores with changelogs and topology-managed recovery are required.
- Event time, windowing, late-arriving records, or repartitioning must be handled.
- The logic naturally fits the Kafka Streams DSL and can be expressed as a topology.

Example: join `orders` and `customers`, compute total order value per customer, and emit `customer-sales-summary`. The Kafka Streams Binder provides abstractions and runtime support better suited than building a custom stateful consumer over regular listeners.

## 17. Testing the Two Binders

The two binders require different test suites because their runtimes and semantics differ.

| Test Type | Standard Kafka Binder | Kafka Streams Binder |
|---|---|---|
| Logic unit test | Invoke function/consumer with DTOs | Test transformations or topology logic |
| Binding test | Spring Cloud Stream Test Binder or test broker | Verify function bindings and topology with Streams config |
| Broker test | Topics, groups, offsets, retries, DLQ | Topics, application ID, task assignment, state stores, changelogs |
| Recovery test | Consumer restart, rebalance, and redelivery | Task migration, state restoration, and rebalance |
| Serialization test | `MessageConverter` and Kafka serializer/deserializer | `Serde` for keys/values, state stores, and changelogs |
| Delivery guarantee test | Ack/commit/producer transactions per config | `processing.guarantee` and Kafka Streams transactions |

For Kafka Streams, `TopologyTestDriver` is useful for testing topologies in-memory without a broker. However, it does not replace integration tests against real Kafka when verifying partition assignment, transactions, changelog restoration, or rebalances.

For the standard Kafka Binder, the Test Binder checks function bindings and message flow; integration tests with a real broker validate consumer groups, offsets, retries/DLQ, and producer settings.

## 18. Common Mistakes When Choosing or Configuring Binders

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Function expects `KStream` but receives DTO or fails | Using the standard Kafka Binder | Switch to the Kafka Streams Binder and matching dependency |
| `KStream` does not get bound as expected | Function definition or Kafka Streams Binder not configured | Check binder, function signature, and binding names |
| Kafka Streams reports `Serde` error | Key/value `Serde` incompatible with data | Configure proper `Serde` for inputs, outputs, and stateful operators |
| Two replicas both process the entire topic | Different `application.id` across replicas | Use the same `application.id` for the same logical topology |
| Two independent topologies share offsets/state | Unintentionally sharing `application.id` | Assign a distinct `application.id` per logical application |
| Topic/changelog/repartition topics grow unexpectedly | Topology or stateful operators create internal resources | Inspect topology, naming, retention, and cleanup policies |
| DLQ missing despite standard Kafka Binder config | Using Kafka Streams Binder or wrong namespace | Use error handling appropriate for Kafka Streams |
| State restoration takes long after restart | Large state store or slow changelog restore | Monitor restoration, optimize state, and tune broker infrastructure |
| `content-type` does not fix deserialization error | Handled by Kafka Streams `Serde` | Configure `Serde` instead of changing only `MessageConverter` |

## 19. Can Both Binders Be Used in One System?

A system can have some services using the standard Kafka Binder and others using the Kafka Streams Binder. Each service picks the model suited to its workload. Within a single Spring Cloud Stream application having multiple binders, the framework supports multiple binders, provided each binding explicitly specifies its binder and you verify which function is wired to which binder.

Do not add both starters just to "have every feature available." Each runtime brings its own configuration, lifecycle, dependencies, and semantics. If a service just receives a message and calls an API, the standard Kafka Binder is simpler. If a service requires a stateful stream topology, the Kafka Streams Binder supplies the needed abstractions.

A common architecture looks like:

```text
Order service
  Standard Kafka Binder
       |
       v
orders.events topic
       |
       v
Analytics service
  Kafka Streams Binder
       |
       +--> join / window / aggregate
       |
       v
sales.summary topic
       |
       v
Reporting service
  Standard Kafka Binder
```

Services share Kafka while each service selects the runtime suited to its job.

## 20. Selection and Implementation Process

When starting a Kafka processing flow in Spring Cloud Stream:

1. Determine whether the problem is message-by-message processing or stream topology processing.
2. If it only needs to receive DTOs, run business logic, and emit outputs, consider the standard Kafka Binder.
3. If it needs joins, windowing, aggregations, or state stores tied to a Kafka topology, consider the Kafka Streams Binder.
4. Pick the dependency/starter matching the binder; do not infer runtime from function names.
5. Configure brokers inside the corresponding binder namespace.
6. For the standard Kafka Binder, configure destination, group, content type, producer/consumer options, and error handling.
7. For the Kafka Streams Binder, configure `application.id`, `Serde`, topology, and state stores.
8. Determine appropriate partition keys, partition counts, concurrency, or stream threads.
9. Design delivery semantics, retries, DLQs, and idempotency for either model.
10. Test logic, bindings, serialization, restarts, rebalances, and real broker behavior.
11. Monitor consumer lag or Streams task/state restoration depending on the runtime.

## 21. Self-Check

- [ ] Can explain that the standard Kafka Binder uses Spring Kafka to send and receive messages.
- [ ] Can explain that the Kafka Streams Binder uses the Kafka Streams DSL to build topologies.
- [ ] Can distinguish `Function<OrderEvent, Result>` from `Function<KStream<K,V>, KStream<K2,V2>>`.
- [ ] Can distinguish `group` from `application.id`.
- [ ] Can describe the roles of `KStream`, `KTable`, and `GlobalKTable`.
- [ ] Can explain state stores, changelogs, and repartition topics.
- [ ] Can distinguish `MessageConverter` from Kafka Streams `Serde`.
- [ ] Understands how scaling consumer groups differs from scaling Kafka Streams tasks.
- [ ] Understands the scope of Kafka Streams exactly-once and its limits with external systems.
- [ ] Can choose the right binder for message workflows vs. stateful stream processing.
- [ ] Can design separate tests and monitoring for each runtime.

## Conclusion

The standard Kafka Binder uses Spring Kafka to send and receive messages per binding, fitting functions processing Java payloads, consumer groups, and business workflows. The Kafka Streams Binder uses the Kafka Streams DSL with `KStream`, `KTable`, state stores, joins, windowing, and aggregations to build stateful stream-processing topologies. The two binders differ in function signatures, runtime, broker configuration, identity, `Serde`, scaling, and delivery semantics. Choose the standard Kafka Binder for general message processing; choose the Kafka Streams Binder when the problem requires stream operators and state bound to a Kafka topology. Both still require proper idempotency, error handling, broker testing, and operational observability.
