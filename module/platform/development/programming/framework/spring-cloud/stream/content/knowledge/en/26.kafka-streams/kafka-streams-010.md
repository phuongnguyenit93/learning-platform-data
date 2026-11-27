# Binding Function Parameters to the Right destination and applicationId

In the Spring Cloud Stream Kafka Streams Binder, a function bean describes a data-processing topology; the function's input parameters and return value are connected to bindings. Each binding must point to the right Kafka topic via `destination`. At the same time, a Kafka Streams application needs a stable `applicationId` so Kafka can manage consumer groups, offsets, and internal state resources.

These three concepts serve distinct roles: the **function name** determines which topology is selected; the **binding name and destination** determine which topics data enters and leaves; and **`applicationId`** establishes the identity of a Kafka Streams application. Misconfiguring any one of these can cause the application to read the wrong topic, write to the wrong output, fail to restore state properly, or spin up as an unintended independent consumer group.

This lesson belongs to the **Kafka Streams** chapter of the `SPRING_CLOUD_STREAM` module. It focuses on the `Function`/`BiFunction` programming model, how the first and second parameters map to `-in-0`/`-in-1`, how outputs map to `-out-0`, configuring `destination`, `applicationId`, Serdes, multiple topologies, multi-replica deployments, and safely changing identifiers.

## 1. Three Identifier Layers to Keep Separate

| Component | Question It Answers | Example |
|---|---|---|
| Function name | Which topology/function bean is activated? | `enrichOrders` |
| Binding name | Which input or output of the function is being configured? | `enrichOrders-in-0` |
| Destination | Which Kafka topic does the binding read from or write to? | `orders.created` |
| `applicationId` | Which instances belong to the same logical Kafka Streams application? | `order-enrichment-v1` |

A function name is not a topic name. A binding name is not a topic name either. `destination` is the logical topic name configured for a binding. `applicationId` does not identify input or output topics; it identifies the Kafka Streams application and is used for the consumer group and internal resources.

```text
Function bean: enrichOrders
       |
       +-- parameter 1 --> enrichOrders-in-0 --> destination: orders.created
       |
       +-- parameter 2 --> enrichOrders-in-1 --> destination: customers.current
       |
       +-- return value -> enrichOrders-out-0 -> destination: orders.enriched

Kafka Streams applicationId: order-enrichment-v1
       |
       +-- consumer group of the topology
       +-- offset and task coordination
       +-- internal state resource naming/identity
```

Separating these identifier layers makes configuration easy to read and prevents errors when renaming beans or topics. Changing a function name can change generated binding names; changing `destination` changes the topic a binding connects to; changing the application ID creates a different Kafka Streams application identity.

## 2. How Spring Cloud Stream Generates Binding Names

In the functional model, Spring Cloud Stream uses the function bean name to construct binding names by convention:

- First input: `<functionName>-in-0`.
- Second input: `<functionName>-in-1`.
- Subsequent inputs: `-in-2`, `-in-3`, ...
- First output: `<functionName>-out-0`.
- If the function has multiple outputs supported by its return type, each output receives its own index.

Single-input, single-output function example:

```java
@Bean
Function<KStream<String, OrderEvent>, KStream<String, OrderEvent>>
    filterOrders() {
    return orders -> orders
        .filter((key, event) -> event.total() > 0);
}
```

Generated bindings:

```text
filterOrders-in-0
filterOrders-out-0
```

Two-input function example:

```java
BiFunction<
    KStream<String, OrderEvent>,
    KTable<String, Customer>,
    KStream<String, EnrichedOrder>
> enrichOrders;
```

This is a shorthand signature to show the order of the two parameters; a complete implementation example appears in the following section.

Input and output bindings:

```text
enrichOrders-in-0  <- first parameter: KStream<String, OrderEvent>
enrichOrders-in-1  <- second parameter: KTable<String, Customer>
enrichOrders-out-0 <- return value: KStream<String, EnrichedOrder>
```

Parameter order matters. `in-0` binds to the first parameter in the function signature; `in-1` binds to the second parameter. Never infer order from variable names, topic names, or data type names.

## 3. `destination` Connects Bindings to Kafka Topics

`destination` is declared under `spring.cloud.stream.bindings`. With the Kafka Streams Binder, input bindings point to source topics; output bindings point to target topics.

Single-input, single-output function example:

```yaml
spring:
  cloud:
    function:
      definition: filterOrders
    stream:
      bindings:
        filterOrders-in-0:
          destination: orders.created
        filterOrders-out-0:
          destination: orders.validated
```

The `filterOrders` function reads from `orders.created` and writes results to `orders.validated`. If `destination` is omitted for an output, the framework may use the binding name as the default destination; therefore, specify topic names explicitly to avoid writing to unintended topics.

Binding names must match the function name and index exactly. A typo such as `filterOrder-in-0` instead of `filterOrders-in-0` prevents the configuration from applying to the active binding.

## 4. Binding Multiple Parameters to Multiple Destinations

Consider a topology that enriches orders with customer details. The function accepts a `KStream` of order events and a `KTable` containing the latest customer state:

```java
import java.math.BigDecimal;
import java.util.function.BiFunction;

import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String customerId, BigDecimal total) {}

record Customer(String customerId, String displayName) {}

record EnrichedOrder(
    String orderId,
    String customerId,
    String customerName,
    BigDecimal total
) {}

@Configuration
class OrderTopologyConfiguration {

    @Bean
    BiFunction<
        KStream<String, OrderEvent>,
        KTable<String, Customer>,
        KStream<String, EnrichedOrder>
    > enrichOrders() {
        return (orders, customers) -> orders
            .selectKey((orderId, event) -> event.customerId())
            .join(customers, (event, customer) -> new EnrichedOrder(
                event.orderId(),
                event.customerId(),
                customer.displayName(),
                event.total()
            ));
    }
}
```

`selectKey` rekeys the stream to `customerId` to match the `KTable` key. Kafka Streams may need to repartition the stream before the join if the new key differs from the current key. In this example, the join produces an `EnrichedOrder` containing the customer's name at the time the topology processes the event.

Binding configuration:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.created
        enrichOrders-in-1:
          destination: customers.current
        enrichOrders-out-0:
          destination: orders.enriched
```

Mapping:

| Binding | Function Parameter / Return | Destination |
|---|---|---|
| `enrichOrders-in-0` | Parameter 1: `KStream<String, OrderEvent>` | `orders.created` |
| `enrichOrders-in-1` | Parameter 2: `KTable<String, Customer>` | `customers.current` |
| `enrichOrders-out-0` | Return value: `KStream<String, EnrichedOrder>` | `orders.enriched` |

If the two parameters are swapped in Java, you must revisit the corresponding binding indices and Serdes. Never simply rename destinations in YAML without cross-checking the function signature.

## 5. Using `spring.cloud.function.definition` to Select the Right Function

An application may contain multiple function beans. `spring.cloud.function.definition` specifies which function or function chain Spring Cloud Stream activates.

Example:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrders
```

If the right function name is not selected, the binder may not create the bindings targeted by your configuration. When an application defines multiple `Supplier`, `Function`, or `Consumer` beans, declaring `definition` explicitly prevents the framework from picking an unexpected function.

Names in `definition` must match function bean names, not destinations or application IDs. When using composition, `definition` syntax can combine function names via Spring Cloud Function; in that case, verify the composed binding names generated by your framework version.

## 6. Configuring `applicationId`

Kafka Streams requires `application.id` to identify a stream-processing application. The Kafka Streams Binder provides the `applicationId` binder property, typically placed under:

```text
spring.cloud.stream.kafka.streams.binder.applicationId
```

Example:

```yaml
spring:
  application:
    name: order-stream-service
  cloud:
    function:
      definition: enrichOrders
    stream:
      kafka:
        streams:
          binder:
            brokers: localhost:9092
            applicationId: order-enrichment-v1
```

Setting `applicationId` explicitly keeps the application identity stable and independent of artifact names or runtime environments. If omitted, the binder may fall back to defaults derived from application configuration such as `spring.application.name` or the binder version's default mechanism. In production, configure it explicitly to avoid accidentally altering identity when renaming a Spring service.

`applicationId` is a Kafka Streams application property, not the `group` property of the regular Kafka Binder. In Kafka Streams, the application ID serves as the consumer group ID and forms part of the stateful topology's identity.

At the Kafka Streams client layer, the underlying property name is `application.id`. The Kafka Streams Binder exposes `applicationId` in the binder namespace to set this value. Avoid specifying conflicting values between `binder.applicationId` and `binder.configuration.application.id`; pick one clear configuration source per your binder version to avoid unintended identities.

## 7. What Does `applicationId` Affect?

Kafka Streams uses the application ID for multiple purposes:

- Consumer group identity so instances of the same topology coordinate task assignment.
- Offset management for input topics.
- Naming internal topics such as changelog and repartition topics created by the topology.
- Identifying state stores and cross-instance state recovery.
- Distinguishing application-level metrics and client identity.

Consequently, the application ID must remain stable across restarts of the same topology. If every replica uses a different application ID, each becomes an independent Kafka Streams application; every application reads the entire input topic and emits duplicate outputs.

Conversely, two independent topologies must not share an application ID if they need separate offsets, state stores, and deployment lifecycles. Sharing an ID can cause them to join the same consumer group or collide on internal resources.

## 8. All Replicas of the Same Topology Must Share `applicationId`

Suppose an `enrichOrders` topology runs three replicas:

```text
Deployment: order-enrichment
applicationId: order-enrichment-v1

Replica A ------------------+
Replica B ------------------+---- same Kafka Streams application
Replica C ------------------+
```

All three replicas share the same application ID. Kafka Streams coordinates the consumer group and distributes tasks/partitions among them. When one replica stops, its tasks can shift to surviving replicas; required state is restored from state stores/changelogs via Kafka Streams' recovery mechanism.

Never set the application ID using pod names, hostnames, random UUIDs, or replica indices. Those values change across deployments and turn every run into a separate application, preventing offsets and state from being reused as intended.

## 9. Multiple Independent Topologies Need Separate `applicationId` Values

A Spring Boot application may define multiple Kafka Streams functions. When they represent independent topologies, each topology needs its own application identity if your binder/version supports per-function application IDs. Some Kafka Streams Binder versions expose per-function configuration as:

```text
spring.cloud.stream.kafka.streams.binder.functions.<functionName>.applicationId
```

Illustrative example for two functions:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrders;calculateSales
    stream:
      kafka:
        streams:
          binder:
            functions:
              enrichOrders:
                applicationId: order-enrichment-v1
              calculateSales:
                applicationId: sales-aggregation-v1
```

This configuration depends on binder version support. Verify property metadata and documentation for your exact release train before relying on it; if your version does not support per-function application IDs, deploy independent topologies in separate application/binder contexts. Never assign a single shared application ID to multiple independent topologies merely because they run in the same process.

If functions actually form a composed processing chain sharing one lifecycle and topology logic, treat them as one application according to how the binder builds topologies and assigns application IDs. Do not mechanically apply a "one ID per bean" rule when functions are composed into a single pipeline.

## 10. Serde Configuration Must Match Parameter Data Types

`destination` specifies which topic is read/written; `Serde` specifies which Java types key/value bytes convert to and from. Both configurations must align with the function signature.

For example, if a function uses:

```java
Function<KStream<String, OrderEvent>, KStream<String, OrderEvent>>
```

then input keys must deserialize as `String` and values as `OrderEvent`; outputs require corresponding serializers.

Example configuring a default Serde for `String` keys:

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
```

For complex payloads, configure dedicated Serdes per binding so `OrderEvent` and `Customer` deserialize into their proper types. Illustrative example (custom Serde classes must exist on the classpath and satisfy the constructors/configurations expected by the binder):

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            enrichOrders-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.OrderEventSerde
            enrichOrders-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.CustomerSerde
            enrichOrders-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.EnrichedOrderSerde
```

Serde names, constructors, trusted packages, and schema compatibility depend on your libraries and versions. Do not assume `content-type: application/json` automatically replaces Kafka Streams Serdes; Spring's `MessageConverter` and Kafka Streams Serdes are two distinct layers.

If `enrichOrders-in-0` expects `OrderEvent` while the topic holds Avro bytes, configuring `JsonSerde` will fail even though the destination is right. Similarly, if the second parameter is `KTable<String, Customer>`, the Serde for `customers.current` must match `Customer`.

## 11. Naming Bindings Accurately in YAML

A common mistake is configuring `destination` under a non-existent binding name. Cross-check your function signature against the table below before running:

| Signature | Input Bindings | Output Bindings |
|---|---|---|
| `Function<KStream<K,V>, KStream<K2,V2>> normalize` | `normalize-in-0` | `normalize-out-0` |
| `BiFunction<KStream<K,V>, KTable<K2,V2>, KStream<K3,V3>> enrich` | `enrich-in-0`, `enrich-in-1` | `enrich-out-0` |
| `BiFunction<KStream<K,V>, KStream<K2,V2>, KStream<K3,V3>> correlate` | `correlate-in-0`, `correlate-in-1` | `correlate-out-0` |
| `Consumer<KStream<K,V>> audit` | `audit-in-0` | No output binding |

The bean name is the root of every binding name. Renaming `enrich` to `enrichOrders` in Java requires updating `definition` and the corresponding YAML bindings. Updating only one side prevents configuration from applying to the intended function.

## 12. Complete Configuration Example for a Topology

```yaml
spring:
  application:
    name: order-enrichment
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.created
        enrichOrders-in-1:
          destination: customers.current
        enrichOrders-out-0:
          destination: orders.enriched
      kafka:
        streams:
          binder:
            brokers: kafka-1:9092,kafka-2:9092
            applicationId: order-enrichment-v1
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
          bindings:
            enrichOrders-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.OrderEventSerde
            enrichOrders-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.CustomerSerde
            enrichOrders-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.EnrichedOrderSerde
```

Reading the configuration in order:

1. `definition` selects the `enrichOrders` function bean.
2. The first parameter is a `KStream`, so `enrichOrders-in-0` points to `orders.created`.
3. The second parameter is a `KTable`, so `enrichOrders-in-1` points to `customers.current`.
4. The function returns a `KStream`, so `enrichOrders-out-0` writes to `orders.enriched`.
5. `applicationId` is `order-enrichment-v1` for this topology.
6. Serdes must match the actual keys/values of each topic; because the two inputs have different value types, the example configures per-binding Serdes.

Never place `applicationId` into `bindings.enrichOrders-in-0.destination`. These two properties belong to separate configuration branches and cannot substitute for each other.

## 13. Distinguishing `applicationId` from Regular Kafka Binder Consumer Groups

Spring Cloud Stream has both a regular Kafka Binder and a Kafka Streams Binder. Both use Kafka, but consumer identity is configured differently:

| Model | Identity Configuration | Meaning |
|---|---|---|
| Regular Kafka Binder | `spring.cloud.stream.bindings.<binding>.group` | Consumer group of an input binding |
| Kafka Streams Binder | `spring.cloud.stream.kafka.streams.binder.applicationId` | Identity of the Kafka Streams application/topology |

With the Kafka Streams Binder, do not use a regular binding's `group` property in place of `applicationId`. Kafka Streams needs `applicationId` to manage tasks, offsets, and state. If only `group` is set without the proper `applicationId`, the topology may use a default application identity or behave differently than expected.

## 14. What Happens When Changing `destination`?

Changing `destination` means a binding begins reading from or writing to a different topic. For example:

```text
Before: enrichOrders-in-0 -> orders.created.v1
After:  enrichOrders-in-0 -> orders.created.v2
```

This is a data-source change. Kafka Streams may start reading the new topic according to its offset policy; existing state stores and changelogs still belong to the application ID/topology. Changing `destination` does not automatically migrate data or state from the old topic to the new topic.

Before making the change, verify:

- Whether the new topic exists with suitable partitions.
- Whether key/value schemas and Serdes remain compatible.
- Where the consumer group/application ID will start reading offsets on the new topic.
- Whether data needs backfilling or state stores need rebuilding.
- Whether the output topic remains compatible with downstream consumers.
- Whether old and new versions need to run side-by-side during migration.

If you change only the topic name while keeping the old application ID, Kafka Streams may continue using the existing application's state/changelog against the new input topic. Determine whether existing state remains valid for the new data source or whether a new application ID is needed for an intentional rebuild.

## 15. What Happens When Changing `applicationId`?

Changing `applicationId` creates a new Kafka Streams application identity. The new application gets a new consumer group, separate offsets, and a fresh namespace for internal topics and state. When no committed offsets exist for the new group, initial consumption depends on `auto.offset.reset` or equivalent offset configuration.

Example:

```text
Old applicationId: order-enrichment-v1
New applicationId: order-enrichment-v2
```

This can cause v2 to re-read from `earliest` or start from `latest` as configured, rather than continuing v1's offsets. v1's state stores do not automatically transfer to v2. If v2 needs complete state, replay inputs or execute a planned state migration.

Do not change `applicationId` on every deployment. Change it only when intentionally establishing a new application identity—such as rebuilding a projection, running a new topology in parallel, or splitting a logical application. Before retiring v1, verify outputs, state, offsets, and cleanup/retention policies for old internal topics.

## 16. Internal Topics and Kafka Permissions

Kafka Streams may create changelog topics and repartition topics for stateful operations. Internal topics are normally named using the application ID and store/operator names. Thus, a stable application ID enables state recovery across restarts.

The application's Kafka principal needs permissions to:

- Read input topics.
- Write output topics.
- Read/write internal topics used by Kafka Streams.
- Join the corresponding consumer group.
- Create internal topics if the cluster allows application auto-creation.

In production, internal topics may be pre-provisioned or governed by ACLs and infrastructure workflows. Do not grant permissions only to business topics while overlooking changelog/repartition topics. An application may read inputs successfully yet fail when initializing state stores or joins due to missing ACLs on internal topics.

## 17. Partition Counts, Tasks, and `applicationId`

`applicationId` is not a partition count and does not directly control task counts. Kafka Streams creates tasks from input topic partitions and the topology. Instances sharing the same application ID coordinate task distribution.

| Component | Role |
|---|---|
| `destination` | Selects the source/target topic |
| Partition count | Determines how many partitions a topic has |
| Key | Determines which partition a record routes to via the partitioner |
| `applicationId` | Identifies the Kafka Streams application group |
| Stream thread | Number of processing threads within one instance |
| Task | Unit of processing bound to partitions of the topology |

If a topic has six partitions and the application runs three replicas sharing an application ID, Kafka Streams can distribute tasks across the three replicas. If each replica uses a different application ID, each replica becomes an independent application and can end up processing all six partitions.

## 18. Per-Environment `destination` and `applicationId`

Dev, staging, and production environments typically require separate topics and application IDs to avoid cross-environment reads and writes:

```yaml
spring:
  cloud:
    stream:
      bindings:
        enrichOrders-in-0:
          destination: ${ORDERS_INPUT_TOPIC:orders.created}
        enrichOrders-in-1:
          destination: ${CUSTOMERS_INPUT_TOPIC:customers.current}
        enrichOrders-out-0:
          destination: ${ORDERS_OUTPUT_TOPIC:orders.enriched}
      kafka:
        streams:
          binder:
            applicationId: ${KAFKA_STREAMS_APPLICATION_ID:order-enrichment-dev}
```

Example environment values:

| Environment | Input Topic | Output Topic | Application ID |
|---|---|---|---|
| Local | `dev.orders.created` | `dev.orders.enriched` | `order-enrichment-local` |
| Staging | `staging.orders.created` | `staging.orders.enriched` | `order-enrichment-staging` |
| Production | `orders.created` | `orders.enriched` | `order-enrichment-prod` |

Separating application IDs across environments keeps their offsets and state independent. Topic names must also point to the proper cluster/environment; changing only the application ID while still reading production topics from dev can cause unintended side effects.

## 19. Common Binding Mistakes

| Mistake | Possible Symptom | How to Check |
|---|---|---|
| Wrong function definition | Function is not activated as intended | Check bean names and `spring.cloud.function.definition` |
| Wrong binding name | `destination` does not apply to actual input/output | Cross-check `<functionName>-in-N`/`-out-N` |
| Swapped parameter order | Input topic bound to the wrong `KStream`/`KTable` type | Match function signature against indices |
| Wrong `destination` | Topology reads/writes unexpected topics | Inspect binding properties and broker topics |
| Missing output `destination` | Output binding does not write to intended topic | Declare `<functionName>-out-0` |
| `applicationId` varies per pod | Every replica becomes an independent app, duplicating work | Use a shared, stable application ID |
| Shared `applicationId` across independent topologies | Offsets/state/internal topics collide unintentionally | Assign distinct application IDs per logical topology |
| Using `group` instead of `applicationId` | Kafka Streams identity differs from expectations | Configure Kafka Streams binder `applicationId` |
| Serde mismatches payload | Runtime serialization/deserialization errors | Check key/value Serdes for every input/output |
| Changing `destination` while keeping incompatible old state | Wrong or incomplete join/aggregate outputs | Evaluate state restore, replay, and migration |
| Changing `applicationId` without an offset plan | App unexpectedly replays or skips data | Check `auto.offset.reset` and backfill plan |

## 20. Testing Function, Destination, and applicationId Bindings

Verify configuration from both the Spring context and Kafka broker sides:

| Scenario | How to Test | What to Verify |
|---|---|---|
| One input, one output | Send records to the input topic | Function reads from `-in-0` and outputs to `-out-0` destination |
| Two inputs | Send records to both topics | Parameter 1 reads `-in-0`, parameter 2 reads `-in-1` |
| Wrong binding name | Intentionally alter a suffix | Startup/configuration checks detect binding mismatch |
| Wrong `destination` | Point input to a different topic | Confirm topology reads only the configured topic |
| Replicas with same app ID | Run two instances with the same application ID | Both instances share tasks/partitions of the same app |
| Replicas with different app IDs | Run two instances with different IDs | They act as two independent apps; duplicate outputs appear if writing to the same topic |
| Restart with same app ID | Stop and restart an instance | Offsets and state recover via Kafka Streams |
| Changed app ID | Run a version with a new ID | Confirm new group/offsets/internal topics and offset reset behavior |
| Wrong Serde | Configure Serde incompatible with payload | Serialization/deserialization errors are caught |
| Internal topic ACLs | Revoke changelog/repartition permissions | Verify state initialization/processing fails as expected and confirm required ACLs |
| Multiple topologies | Assign separate application IDs per function if supported | Offsets and state remain isolated across independent topologies |

`TopologyTestDriver` is great for testing topology logic and data mapping in unit tests. Integration tests against real Kafka or a compatible broker are essential to verify application IDs, consumer groups, offsets, internal topics, partition assignments, and state restoration.

## 21. Safe Configuration Process

When wiring a Kafka Streams function:

1. Pick a stable function bean name and declare it in `spring.cloud.function.definition`.
2. Inspect the function signature to determine input parameter count and order.
3. Derive binding names using `<functionName>-in-0`, `-in-1`, ... and `<functionName>-out-0`.
4. Assign `destination` to each binding pointing to the right source/target topic.
5. Choose a stable `applicationId` for the logical topology.
6. Use the same application ID across all replicas of the same topology.
7. Use separate application IDs for independent topologies; verify per-function ID support in your binder version.
8. Configure Serdes compatible with each topic's keys/values and parameter types.
9. Grant ACLs for inputs, outputs, consumer groups, and internal topics.
10. Test input/output mappings, partition assignment, restarts, and state restoration.
11. Make an explicit plan before changing `destination` or `applicationId`.
12. Monitor consumer lag, task assignment, restore times, and serialization errors in production.

## 22. Self-Check

- [ ] Can distinguish function name, binding name, destination, and application ID.
- [ ] Can accurately derive `-in-0`, `-in-1`, and `-out-0` binding names from a function signature.
- [ ] Can explain which input binding the first and second parameters map to.
- [ ] Can configure separate destinations for every input and output.
- [ ] Knows how `spring.cloud.function.definition` selects function beans.
- [ ] Can explain the role of Kafka Streams `applicationId`.
- [ ] Knows that all replicas of the same topology must share the same application ID.
- [ ] Knows that independent topologies need distinct application IDs when deployed as separate applications.
- [ ] Can distinguish `applicationId` from the regular Kafka Binder's `group`.
- [ ] Can configure Serdes matching the key/value types of every parameter.
- [ ] Understands how changing `destination` and `applicationId` affects offsets and state.
- [ ] Can design tests covering mappings, restarts, internal topics, and multiple replicas.

## Conclusion

In the Kafka Streams Binder, the function signature determines input and output bindings: the first parameter binds to `-in-0`, the second parameter binds to `-in-1`, and the return value binds to `-out-0`. Each binding uses `destination` to specify its corresponding topic. `applicationId` identifies the Kafka Streams application, consumer group, offsets, and internal state; all replicas of the same topology must share a stable ID, while independent topologies need distinct identities. Cross-checking function signatures, binding names, destinations, Serdes, and application IDs before deployment prevents reading wrong topics, duplicate processing, broken state recovery, and unintended internal topics.
