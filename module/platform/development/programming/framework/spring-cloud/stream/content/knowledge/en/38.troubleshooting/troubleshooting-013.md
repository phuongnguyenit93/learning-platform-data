# Kafka Streams Missing Serde, State Store Not Ready, or Restoration Failure

A Spring Cloud Stream application using Kafka Streams can start up yet fail to process records, or process input and then fail when querying a state store. Common causes include a Serde mismatch against topic data, an undeclared Serde inside the topology, an unmaterialized or unregistered state store, an inaccessible local RocksDB directory, or Kafka Streams still restoring state from a changelog topic.

These three scenarios show distinct symptoms:

- **Serde error:** a record cannot convert from bytes to key/value or from object to bytes; errors typically appear at input/output boundaries or when a state store reads its changelog.
- **Store not ready:** the topology is initializing, rebalancing, or restoring; interactive queries may throw `InvalidStateStoreException` even though the process is alive.
- **Restoration failing or stalled:** Kafka Streams cannot read the changelog, write local state, or catch up offsets to transition the task into active operation.

This lesson guides inspection in order: Serde → topology/state store → changelog/restoration → health and operations. Examples use the Spring Cloud Stream functional model with `KStream`, `KTable`, Kafka Streams Binder, and Micrometer/Actuator.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish input/output Serde errors from Serde errors inside the topology.
- Understand how the Kafka Streams Binder infers key/value Serdes and configuration precedence.
- Configure Serdes per binding or at the binder level.
- Know when to disable native decoding/encoding to use Spring `MessageConverter`.
- Materialize state stores via DSL, `KTable`, or the Processor API.
- Explain changelog topics and how Kafka Streams restores local state.
- Diagnose `InvalidStateStoreException`, RocksDB, disk, ACL, and changelog issues.
- Monitor restoration, thread states, active/standby tasks, and store readiness.
- Choose appropriate `application.id`, `state.dir`, standby replicas, and retry policies.
- Test Serdes, state stores, and recovery after restarts.

## 1. Distinguish Three Error Layers

A Kafka Streams topology can read records, transform data, update state stores, and emit outputs. When an error occurs, pinpoint where it happened:

~~~mermaid
flowchart TD
    A["Kafka input topic"] --> B["Key/value deserialization"]
    B --> C["KStream / KTable topology"]
    C --> D["State store read/write"]
    D --> E["Key/value serialization"]
    E --> F["Kafka output topic"]
    D <--> G["Changelog topic"]
    G --> H["Restore consumer"]
    H --> D
    D --> I["Interactive query"]
~~~

| Layer | Common Symptoms | First Question |
|---|---|---|
| Input Serde | `SerializationException`, `DeserializationException`, records failed/skipped/DLQ | Do topic bytes match the expected format and schema? |
| Topology Serde | Failure in `groupBy`, `aggregate`, `join`, `Materialized`, or Processor API | Do Serdes passed to operations/stores match the key/value types? |
| Output Serde | Failure writing to the output topic | Do output key/value Serdes match the wire contract? |
| Store readiness | `InvalidStateStoreException`, store unqueryable at startup | Have tasks been assigned and finished restoring? |
| State restoration | Restore lag stalls, RocksDB/disk errors, changelog fetch errors | Can Kafka Streams read the changelog and write local state? |

Serde stands for serializer/deserializer. One Serde pairs a `Serializer<T>` and `Deserializer<T>` for the same data type. Kafka stores bytes; Java types exist only after a deserializer converts bytes into objects.

Do not confuse Spring Message `content-type` with Kafka Streams Serdes. The Kafka Streams Binder uses native Kafka Serdes by default for keys and values. Spring `MessageConverter` participates only when native decoding/encoding is disabled per binding.

## 2. How the Kafka Streams Binder Infers Serdes

With the Kafka Streams Binder, keys are deserialized using native Serdes. Inbound values also default to native Kafka deserialization. The binder attempts to infer Serdes from the `Function` or `Consumer` signature and beans in the `ApplicationContext`.

Typical inference precedence:

1. Serdes configured directly on the input/output binding have highest priority.
2. The binder looks for a `Serde<T>` bean whose generic type matches the key/value type in the topology signature.
3. The binder recognizes built-in Serde types such as `String`, `Integer`, `Long`, `Short`, `Double`, `Float`, `byte[]`, and `UUID`.
4. The binder checks default Serdes in Kafka Streams configuration.
5. If no match is found, the binder may fall back to Spring Kafka's `JsonSerde` for JSON-friendly types.

Once a Serde is declared at the binding level, the binder uses it instead of continuing inference. This is useful when a single topology has multiple inputs with different schemas.

Signature example:

~~~java
@Bean
Function<KStream<String, OrderCreated>,
         KStream<String, OrderAccepted>> acceptOrders() {
    return orders -> orders.mapValues(order ->
        new OrderAccepted(order.orderId(), "ACCEPTED")
    );
}
~~~

The binder recognizes key `String` and values `OrderCreated`/`OrderAccepted`. `String` has a built-in Serde. For domain objects, the binder can use a `Serde<OrderCreated>` bean or JSON fallback where appropriate.

### Declaring Serde Beans

To control JSON Serdes explicitly, provide beans with matching generic types:

~~~java
import org.apache.kafka.common.serialization.Serde;
import org.springframework.kafka.support.serializer.JsonSerde;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderSerdeConfiguration {

    @Bean
    Serde<OrderCreated> orderCreatedSerde() {
        return new JsonSerde<>(OrderCreated.class);
    }

    @Bean
    Serde<OrderAccepted> orderAcceptedSerde() {
        return new JsonSerde<>(OrderAccepted.class);
    }
}
~~~

Bean names help readers understand intent. Critically, the generic type `Serde<OrderCreated>` must match the value type declared in the topology. If a bean returns a raw `Serde`, the binder may fail to infer the concrete type.

Avoid defining multiple `Serde` beans with the exact same generic type without a clear selection strategy. When the same Java type is serialized under two different wire formats, configure Serdes per binding so the binder never picks the wrong bean.

## 3. Configuring Serdes per Binding

When inference is insufficient, configure `keySerde` and `valueSerde` on each binding.

Example processor with two inputs:

~~~java
@Bean
BiFunction<KStream<CustomKey, OrderCreated>,
           KTable<CustomKey, CustomerProfile>,
           KStream<String, OrderSummary>> summarizeOrders() {
    // topology implementation
}
~~~

Input configuration:

~~~properties
spring.cloud.stream.kafka.streams.bindings.summarizeOrders-in-0.consumer.keySerde=com.acme.kafka.CustomKeySerde
spring.cloud.stream.kafka.streams.bindings.summarizeOrders-in-0.consumer.valueSerde=com.acme.kafka.OrderCreatedSerde

spring.cloud.stream.kafka.streams.bindings.summarizeOrders-in-1.consumer.keySerde=com.acme.kafka.CustomKeySerde
spring.cloud.stream.kafka.streams.bindings.summarizeOrders-in-1.consumer.valueSerde=com.acme.kafka.CustomerProfileSerde
~~~

Output configuration:

~~~properties
spring.cloud.stream.kafka.streams.bindings.summarizeOrders-out-0.producer.keySerde=org.apache.kafka.common.serialization.Serdes$StringSerde
spring.cloud.stream.kafka.streams.bindings.summarizeOrders-out-0.producer.valueSerde=com.acme.kafka.OrderSummarySerde
~~~

Binding names come from the function bean name and input/output direction. For a `BiFunction`, the two inputs are `summarizeOrders-in-0` and `summarizeOrders-in-1`; the output is `summarizeOrders-out-0`.

Custom Serde classes in this example must implement `Serde` for the respective types and be instantiable/configurable per your project setup. If a Serde needs a schema registry or secrets, supply those via binder configuration or typed Serde beans rather than hardcoding them inside the class.

If every binding in a processor uses `String` keys and values, you can set default Serdes at the binder level:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
              default.value.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Default configuration fits only when all bindings genuinely share the same wire type. For topics carrying JSON objects, Avro, Protobuf, or custom keys, per-binding Serdes or typed beans are safer.

### Key Serde and Value Serde Mismatches

Kafka records have separate keys and values. Configuring only the value Serde will not fix key deserialization failures. Common mismatches:

- Producer writes Avro keys while consumer reads keys as `String`.
- Producer emits UUID bytes while consumer configures `StringSerde`.
- Producer writes JSON values while consumer uses an Avro deserializer.
- Output key/value Serdes disagree with downstream schema expectations.
- Windowed keys require a Windowed Serde rather than the underlying key Serde.

When hitting a deserialization failure, read the exception to determine key vs value, topic, partition, and offset. Do not swap both Serdes simultaneously if only one side is wrong.

## 4. Avro, Schema Registry, and Custom Serdes

If an upstream producer uses Confluent Avro, the Kafka Streams consumer must use the matching Serde. You cannot simply set `content-type` to `application/avro` and expect the native Kafka deserializer to decode it.

Example bean for a generated Avro class:

~~~java
import java.util.Map;

import io.confluent.kafka.streams.serdes.avro.SpecificAvroSerde;
import org.apache.kafka.common.serialization.Serde;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AvroSerdeConfiguration {

    @Bean
    Serde<OrderCreatedAvro> orderCreatedAvroSerde() {
        SpecificAvroSerde<OrderCreatedAvro> serde =
            new SpecificAvroSerde<>();

        String registryUrl = System.getenv("SCHEMA_REGISTRY_URL");
        serde.configure(
            Map.of("schema.registry.url", registryUrl),
            false
        );

        return serde;
    }
}
~~~

This example assumes `OrderCreatedAvro` is generated from an Avro schema and Confluent Serde dependencies match the Kafka client in your BOM. In production, verify `SCHEMA_REGISTRY_URL`, credentials, and TLS before initializing Serdes.

With a `Serde<OrderCreatedAvro>` bean, the binder can infer it from the generic type. If configuring a Serde by class name on the binding, ensure the class can be instantiated and receives the registry config. Never commit usernames, passwords, or API keys in config files; load them from a secret store or environment variables.

### Schema Evolution Also Affects Restoration

State stores maintain their own changelogs. If a store Serde changes wire format, records already in the old changelog remain serialized in the previous format. A new app deployment may read the input topic cleanly yet fail while restoring the store from its changelog.

When changing a state-store Serde:
- Preserve backward compatibility to read existing changelog records whenever possible.
- Check schema history for both keys and values inside the store.
- Test booting the new version against an existing changelog in a staging environment.
- For breaking changes, plan to create a new store/topic or rebuild state from source topics.
- Never delete production changelogs or local state just to see if the error disappears.

## 5. Native Serdes or Spring `MessageConverter`?

The Spring Cloud Stream Kafka Streams Binder uses native encoding/decoding by default. If an upstream producer uses a format that Kafka Streams Serdes cannot decode directly, you can delegate conversion to Spring Cloud Stream.

Disable native decoding on a specific input:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        acceptOrders-in-0:
          consumer:
            native-decoding: false
          content-type: application/json
~~~

Disable native encoding on an output:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        acceptOrders-out-0:
          producer:
            native-encoding: false
          content-type: application/json
~~~

When using `MessageConverter`:
- Verify the actual message `content-type`.
- Register the matching converter.
- Verify the payload type after conversion.
- Configure each input/output individually if the topology has multiple bindings.
- Do not expect the binder to infer native Serdes for bindings with native conversion disabled.

For Kafka Streams, prefer native Serdes whenever possible because the Kafka Streams API also needs Serdes for internal topology operations. `MessageConverter` only handles the Spring Cloud Stream message boundary; it does not supply Serdes to `groupBy`, `aggregate`, `join`, `Materialized`, or the Processor API.

## 6. Serdes Inside the Topology and State Stores

A common mistake is configuring input/output binding Serdes while stateful operators inside the topology still lack Serdes.

Example counting orders by customer key:

~~~java
import java.util.function.Function;

import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.springframework.kafka.support.serializer.JsonSerde;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderCountTopology {

    @Bean
    Function<KStream<String, OrderCreated>, KTable<String, Long>>
    countOrders(Serde<OrderCreated> orderCreatedSerde) {
        return orders -> orders
            .groupByKey(
                Grouped.with(Serdes.String(), orderCreatedSerde)
            )
            .count(
                Materialized.as("orders-by-customer")
                    .withKeySerde(Serdes.String())
                    .withValueSerde(Serdes.Long())
            );
    }

    @Bean
    Serde<OrderCreated> orderCreatedSerde() {
        return new JsonSerde<>(OrderCreated.class);
    }
}
~~~

In this example:
- `Grouped.with` specifies key/value Serdes when grouping records.
- `Materialized.as` assigns a stable store name.
- `withKeySerde` and `withValueSerde` define the state store's Serdes.
- `count` creates a `KTable` holding counts per key.

Store names must be unique within a topology. When multiple topologies run in the same application, never reuse the same store name across distinct builders unintentionally.

Omitting Serdes on APIs that require them causes Kafka Streams to throw `ConfigException`, `SerializationException`, or Serde-related errors when building the topology or when a record enters the operator.

## 7. How Are State Stores Created?

Kafka Streams creates state stores automatically in the high-level DSL when calling stateful operations such as `count`, `aggregate`, `reduce`, `join`, or `Materialized`.

Three common patterns:

| Creation Method | Registration Mechanism |
|---|---|
| DSL materialization | Call a stateful operation with `Materialized.as("store-name")` |
| Input `KTable` | Configure `materializedAs` on the `KTable` binding when naming the store |
| Processor API | Register a `StoreBuilder` so the topology knows about the store |

### Naming a Store for an Incoming `KTable`

For a function taking a `KStream` and a `KTable` input:

~~~java
@Bean
BiFunction<KStream<String, Long>,
           KTable<String, String>,
           KStream<String, Long>> process() {
    // use the table as a lookup/reference stream
}
~~~

Configure the store name on the `KTable` binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            process-in-1:
              consumer:
                materialized-as: incoming-store
~~~

The name `incoming-store` materializes the incoming `KTable` data into a named state store. This property is for `KTable` inputs; for stores created by DSL operations, name them via `Materialized.as`.

### Registering Custom Stores in the Processor API

When using the Processor API, define a `StoreBuilder` bean so the binder adds the store to `StreamsBuilder`:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.state.KeyValueStore;
import org.apache.kafka.streams.state.StoreBuilder;
import org.apache.kafka.streams.state.Stores;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class StateStoreConfiguration {

    @Bean
    StoreBuilder<KeyValueStore<String, Long>> customerTotalsStore() {
        return Stores.keyValueStoreBuilder(
            Stores.persistentKeyValueStore("customer-totals"),
            Serdes.String(),
            Serdes.Long()
        );
    }
}
~~~

The processor accesses the registered store in `init`:

~~~java
@Override
public void init(ProcessorContext context) {
    KeyValueStore<String, Long> totals =
        context.getStateStore("customer-totals");
}
~~~

The name passed to `getStateStore` must match the registered store name. If the store was never added to the topology or the name mismatches, the processor cannot retrieve it. For `GlobalKTable`/global stores, registration differs; use the appropriate `StreamsBuilderFactoryBean` customizer rather than assuming all `StoreBuilder` beans are wired identically.

## 8. Changelog Topics and Restoration Mechanics

Local state stores are normally backed by RocksDB. To avoid losing state when an instance crashes, Kafka Streams maintains a changelog topic recording store mutations. Changelogs are typically compacted to retain the latest state per key.

When a task is assigned to a new instance:
1. Kafka Streams checks local state and checkpoints.
2. If local state does not exist, the restore consumer reads the changelog from the beginning of the needed range.
3. If local state has a valid checkpoint, restoration resumes from the checkpointed offset.
4. Kafka Streams applies changelog records into the local store.
5. Once state catches up, the task begins normal record processing.

~~~mermaid
sequenceDiagram
    participant K as Kafka changelog topic
    participant R as Restore consumer
    participant S as Local RocksDB store
    participant T as Stream task
    R->>K: Fetch changelog records
    K-->>R: Key/value updates
    R->>S: Apply updates
    S-->>R: Write completed
    R-->>T: Restore reaches required offset
    T->>T: Start normal processing
~~~

A task that is currently restoring cannot yet serve interactive queries or transition to `RUNNING`. This is normal progress as long as the changelog is being read and restoration advances.

### What Must Be Protected

- Changelog topics must exist, and the broker must grant the app read/write permissions.
- `application.id` must remain stable across restarts of the same logical processor.
- Internal topic naming and store names must be managed as part of the topology contract.
- Changelog retention/cleanup policies must align with fault-tolerance needs.
- Never delete changelog topics or arbitrarily change the application ID when trying to recover an instance.
- When changing a store's Serde, verify the new app can read changelogs written with the old Serde.

If a changelog is deleted or missing needed history, local stores cannot recover from an old checkpoint. At that point you need a plan to rebuild from source topics or restore from valid backups; simply increasing retries will not solve it.

## 9. `application.id` and `state.dir`

`application.id` identifies a Kafka Streams application. It governs group membership and serves as the prefix for internal changelog/repartition topics. In the Spring Cloud Stream Kafka Streams Binder, set this ID explicitly in production.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: countOrders
    stream:
      kafka:
        streams:
          binder:
            application-id: order-counts-v1
            configuration:
              state.dir: /var/lib/order-stream/state
~~~

In applications running multiple Kafka Streams processors, assign a distinct application ID per function using `spring.cloud.stream.kafka.streams.binder.functions.<function-name>.applicationId`. Replicas of the same processor must share the same application ID to participate in the same logical application.

`state.dir` is the local directory holding state stores. Every Kafka Streams instance sharing a host filesystem must use its own state path. Never let multiple pods write to the same RocksDB directory. In Kubernetes, mount appropriate persistent or writable local volumes, isolate paths per pod/instance, and monitor disk usage. If local disk is lost, Kafka Streams can restore from changelogs, though restore times may spike significantly.

Never change `application.id` just to clear a state error. A new ID creates a new consumer group and fresh internal topics, starting a separate state lifecycle. That can cause full data replays, duplicate side effects, or rebuilding state from scratch depending on offset/reset policies.

## 10. Standby Replicas and Fast Recovery

Kafka Streams can maintain standby tasks holding shadow copies of state stores on other instances. When an active task fails, an up-to-date standby can take over, slashing restoration time.

Example configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              num.standby.replicas: 1
~~~

Setting `num.standby.replicas = 1` requires at least two `KafkaStreams` instances to host an active and a standby task. In general, `n` standby replicas need at least `n+1` instances. One standby roughly doubles local state disk usage across instances. Balance disk, network, and broker load before enabling multiple standbys.

Kafka Streams also offers `acceptable.recovery.lag` and warmup replicas in supported versions to avoid promoting lagging instances while healthier instances still serve traffic. Size lag thresholds from actual restore throughput and workload; too low slows failover, while too high lets stale instances take over tasks.

## 11. State Store Not Ready and `InteractiveQueryService`

An app may finish booting while its store is still unqueryable because tasks are unassigned, rebalancing, or restoring changelogs. Calling `InteractiveQueryService` too early throws `InvalidStateStoreException` or an exception stating `KafkaStreams`/the store is not ready.

Store query example:

~~~java
ReadOnlyKeyValueStore<String, Long> store =
    interactiveQueryService.getQueryableStoreType(
        "orders-by-customer",
        QueryableStoreTypes.keyValueStore()
    );
~~~

The store name must match the name materialized in the topology. If queried before the store is ready, treat unready state as a retriable startup condition.

The Kafka Streams Binder provides retries for `InteractiveQueryService` calls:

~~~properties
spring.cloud.stream.kafka.streams.binder.stateStoreRetry.maxAttempts=8
spring.cloud.stream.kafka.streams.binder.stateStoreRetry.backoffPeriod=1000
~~~

Defaults are typically 1 attempt and 1,000 ms backoff. Tune attempts and backoff to match expected restoration times.

This retry config retries fetching store/host metadata while `KafkaStreams` becomes ready. It cannot fix Serde errors, missing changelogs, RocksDB write failures, or unreachable brokers. If restoration fails repeatedly, fix the root cause instead of raising retries indefinitely.

### Interactive Queries Across Multiple Instances

A key may live on a task running on another instance. When exposing interactive queries across multiple replicas, configure `application.server` so Kafka Streams knows which host owns each key.

Example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              application.server: order-stream-0.order-stream:8080
~~~

In multi-replica deployments, every instance must advertise its own reachable address. `InteractiveQueryService` exposes host metadata for a key; if the key lives elsewhere, route or proxy the request to that host.

## 12. Monitoring Health and Restoration Progress

Add Spring Boot Actuator to use the Kafka Streams Binder health indicator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Enable binder health:

~~~yaml
management:
  health:
    binders:
      enabled: true
  endpoint:
    health:
      show-details: when-authorized
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

The Kafka Streams Binder health indicator reports thread states and active/standby task metadata. Common thread states include:

- `CREATED`
- `RUNNING`
- `PARTITIONS_REVOKED`
- `PARTITIONS_ASSIGNED`
- `PENDING_SHUTDOWN`
- `DEAD`

Binder health is `UP` when all registered Kafka Streams threads are `RUNNING`. During startup, rebalances, or restoration, threads may not be `RUNNING` yet. Inspect thread details, task IDs, partitions, and standby tasks to separate active restoration from dead threads.

### `StateRestoreListener`

Kafka Streams provides `StateRestoreListener` to observe restoration:
- `onRestoreStart`: restoration begins for a store partition, including starting/ending offsets.
- `onBatchRestored`: each restored batch is applied, including batch end offset and record count.
- `onRestoreEnd`: restoration completes, reporting total records restored.
- `onRestoreSuspended`: restoration paused because the task moved to another instance.

Use this listener to log/emit metrics on store name, topic partition, restored record count, and duration. Because the listener is shared across stream threads, implementations must be thread-safe. Register it via Kafka Streams customizer/factory bean integration supported by your Spring for Apache Kafka version.

### Metrics to Watch

| Category | Metrics | How to Interpret |
|---|---|---|
| Stream threads | Thread state, thread count, task count | Are threads dead or rebalancing? |
| Restoration | Restore record rate, duration, remaining lag | Is restoration advancing? |
| Changelog | Consumer fetch rate, lag, request errors | Can restore consumers read the changelog? |
| State store | RocksDB size, open files, read/write latency | Is the store out of disk or throttled? |
| Runtime | CPU, heap, GC, disk I/O, file descriptors | Is the instance resource-starved? |
| Interactive query | Query success, unavailable count, retry count | Is the store ready to serve traffic? |

The Kafka Streams Binder exports metrics through Micrometer `MeterRegistry`. Expose Actuator metrics and Prometheus only inside protected management networks; never expose internal endpoints publicly.

## 13. Diagnosing by Symptom

| Symptom | Possible Cause | Next Check |
|---|---|---|
| `SerializationException` on input | Key/value Serde mismatches producer | Identify key vs value; inspect wire format and schema |
| Only one input of a `BiFunction` fails | Serde configured on wrong binding index | Compare `process-in-0` and `process-in-1` |
| Input reads fine yet `aggregate` fails | Missing Serde in `Grouped`/`Materialized` | Configure key/value Serdes inside DSL |
| Output topic receives wrong bytes | Producer Serde mismatches consumer | Check `producer.keySerde`/`valueSerde` and schema |
| `InvalidStateStoreException` right after startup | Store still restoring or task not `RUNNING` | Check thread state, restore listener, and query retries |
| Restoration makes zero progress | Changelog fetch failed, ACLs, or broker/network | Check restore consumer, changelog topic, authorization |
| RocksDB open/write error | Disk full, wrong permissions, lock, or bad filesystem | Check `state.dir`, volume, disk I/O, and ownership |
| Full restore repeats on every restart | Local state not persisted or useless checkpoints | Check volumes, `state.dir`, and shutdown behavior |
| Store restore throws deserialization error | Store/changelog written with a different Serde/schema | Check schema history and state-store Serde version |
| Thread transitions to `DEAD` | Unhandled exception or fatal error | Read root exception, thread state, and uncaught handler |
| Tasks rebalance continuously | Instance churn, session timeouts, partition moves | Check deploys, network, heartbeats, and instance stability |
| Input consumes cleanly yet query finds no store | Store not materialized or wrong query name | Check `Materialized.as`, `materializedAs`, store name |
| Standby never created | Too few instances or standby replica config | Check `num.standby.replicas` and replica count |
| DLQ stays empty | `sendToDlq` disabled, topic missing, or missing ACL | Check handler, DLQ name, partitions, and permissions |

## 14. Handling Poison Pills and Deserialization Errors

By default, the Kafka Streams Binder uses `logAndFail` for deserialization exceptions. Select the appropriate handler:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            deserialization-exception-handler: sendToDlq
~~~

Supported binder options include:
- `logAndFail`: logs the error and stops processing per handler.
- `logAndContinue`: logs the error and continues to the next record.
- `skipAndContinue`: skips the bad record and continues.
- `sendToDlq`: sends undeserializable records to a dead-letter topic.

With multiple input bindings, configure handlers per binding so each input follows its own policy:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            process-in-0:
              consumer:
                deserialization-exception-handler: sendToDlq
            process-in-1:
              consumer:
                deserialization-exception-handler: skipAndContinue
~~~

Per-binding handlers override binder-level settings. If using `DlqDestinationResolver`, ensure all possible DLQ topics are pre-created because the binder cannot predict every topic name the resolver might return. With static `dlqName`, explicitly provision the topic and grant publish permissions.

By default, DLQs preserve the original record's partition, so the DLQ topic needs sufficient partitions. Input-Serde poison pills differ from state-store restoration errors: sending a bad input record to a DLQ will not fix a changelog already written with an incompatible Serde.

## 15. Investigation and Recovery Procedure

Follow this order to preserve evidence and avoid losing state:

1. Record `application.id`, function name, input bindings, store name, and application version.
2. Identify whether the failure occurs at input deserialization, topology operations, output serialization, queries, or restoration.
3. Read the first exception in the logs, not just the final wrapped exception after retries.
4. Check key and value Serdes on every binding.
5. Check Serdes inside `Grouped`, `Materialized`, joins, and the Processor API.
6. Verify the store was created/registered and its name matches the query.
7. Check binder health, thread states, task assignments, and restoration progress.
8. Verify changelog topics exist with matching partitions and read/write ACLs.
9. Check `state.dir`, filesystem permissions, disk space, RocksDB files, and local volumes.
10. Verify changelog schemas are compatible with current Serdes.
11. Wait for restoration to advance and enable queries only once stores are ready.
12. If state must be rebuilt, create a dedicated plan covering source retention, offsets, side effects, and duplicates before acting.

### When Is Deleting Local State Appropriate?

Deleting local state should only be a controlled recovery step in an appropriate environment. When local state is wiped, Kafka Streams replays the changelog from the start of the needed range. If the changelog is intact and Serdes match, this cleanly rebuilds the local copy. If the changelog is missing or unreadable, wiping local state destroys a valuable checkpoint and makes recovery harder.

Before deleting:
- Confirm changelog topics and partitions exist.
- Confirm consumers have read permissions on changelogs.
- Confirm current Serdes can read historical bytes.
- Estimate restoration duration and disk capacity.
- Confirm the application can tolerate query unavailability during restore.
- Have snapshots/backups or a source-topic rebuild plan ready if needed.

Never delete production changelog topics to work around a local RocksDB error. Never change `application.id` to reset state without an explicit plan for consumer groups, offsets, replays, and duplicate side effects.

## 16. Hands-On Exercise: Restoring the `orders-by-customer` Store

Scenario: function `countOrders` reads topic `orders`, materializes store `orders-by-customer`, and exposes queries for order counts per customer. After a rollout, threads fail to reach `RUNNING` and queries throw `InvalidStateStoreException`.

1. Verify `countOrders` has signature `Function<KStream<String, OrderCreated>, KTable<String, Long>>`.
2. Check the `String` key Serde and `OrderCreated` value Serde.
3. Declare a `Serde<OrderCreated>` bean or configure `consumer.keySerde`/`valueSerde` on the binding.
4. Check `String` and `Long` Serdes inside the `Materialized` store.
5. Confirm store name `orders-by-customer` matches the name in `InteractiveQueryService`.
6. Confirm `application.id` was not altered unexpectedly.
7. Inspect the changelog topic derived from application ID and store name.
8. Check principal read/write ACLs on internal topics.
9. Check `state.dir` writability and free disk space.
10. Enable binder health and inspect thread states and active tasks.
11. Watch restore start, batch restored, and restore end events.
12. Wait for store readiness before issuing interactive queries.
13. If startup queries still fail briefly, configure bounded retries on `InteractiveQueryService`.
14. Test restarting an instance to confirm local state persists or restores from the changelog.
15. Simulate a fresh instance with empty local state in a test environment and confirm full changelog replay completes.
16. Record restore duration, record counts, lag, errors, and readiness conditions.

Acceptance Checklist:

| Item | Result to Confirm |
|---|---|
| Input Serde | Key/value deserialize cleanly against wire format |
| Output Serde | Output key/value serialize cleanly |
| DSL Serdes | `Grouped`/`Materialized`/`Join` have matching Serdes |
| Store registration | Store auto-created or registered via `StoreBuilder` |
| Store naming | `Materialized` name and query name match |
| Application ID | Stable across replicas and restarts |
| Changelog | Topic/partitions exist with proper ACLs and replication |
| Local state | `state.dir` writable, sufficient disk, not improperly shared |
| Restoration | Restore progress advances and completes |
| Health | Stream threads transition to `RUNNING` |
| Query readiness | Interactive queries execute only when stores are ready |
| Recovery | Fresh instance recovers cleanly from changelog |
| Error handling | Poison pills logged/skipped/DLQed per policy |
| Operations | Dashboards, alerts, and restore runbook in place |

## Conclusion

Missing Serdes, unready state stores, and restoration failures in Kafka Streams are related issues that must be diagnosed individually. Serdes must align at inputs, outputs, and every stateful operation inside the topology. Stores must be materialized or registered properly, and Kafka Streams restores local state from changelogs before tasks resume normal processing.

Keep `application.id` stable, isolate `state.dir` per instance, protect changelog topics, and monitor restoration progress. Use binder health, `StateRestoreListener`, Kafka Streams metrics, and bounded retries for interactive queries. Whenever changing a state-store Serde, test against historical changelogs and prepare an explicit rebuild plan. Never wipe state or changelogs impulsively, as doing so can turn a localized fault into a full-state rebuild.

## References

- [Spring Cloud Stream 5.0.4 – Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html)
- [Spring Cloud Stream – State Store](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/state-store.html)
- [Spring Cloud Stream – Interactive Queries](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/interactive-queries.html)
- [Spring Cloud Stream – Kafka Streams Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/health-indicator.html)
- [Spring Cloud Stream – Kafka Streams Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Apache Kafka 4.2 – Configuring Kafka Streams](https://kafka.apache.org/42/streams/developer-guide/config-streams/)
- [Apache Kafka 4.2 – Running Streams Applications and State Restoration](https://kafka.apache.org/42/streams/developer-guide/running-app/)
- [Apache Kafka 4.4 – StateRestoreListener API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/processor/StateRestoreListener.html)
- [Spring for Apache Kafka – JSON Serde](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
