# Serde Inference and Configuring keySerde and valueSerde

Kafka stores records as raw bytes. When Kafka Streams reads a record, it must convert key and value bytes into Java types for processing; when writing results, it must convert those Java types back into bytes. Kafka Streams uses a `Serde` (serializer/deserializer) to perform both directions. The Spring Cloud Stream Kafka Streams Binder can infer Serdes from generic types in `Function`, `Consumer`, `BiFunction`, or `StreamListener` signatures, yet applications still need to understand precedence order, how to configure `keySerde`/`valueSerde`, and when explicit declaration is required.

Serde inference reduces repetitive configuration when data types are clear. It cannot automatically guess every wire format, particularly when using Avro, Protobuf, custom schemas, erased generic types, or multiple topics with different contracts. Choosing the right Serde is essential for reading legacy data, writing new data, preserving keys for partitioning, and avoiding state store corruption.

## 1. What Is a Serde?

A `Serde<T>` is a pair consisting of:

- `Serializer<T>`: converts a Java object into bytes before writing to Kafka.
- `Deserializer<T>`: converts bytes read from Kafka into a Java object.

For example, `Serdes.String()` provides a serializer and deserializer for strings. `Serdes.Long()` does the same for long integers. Spring Kafka provides `JsonSerde<T>` to serialize/deserialize objects as JSON.

A Kafka record has two primary data components:

| Component | Role | Example |
|---|---|---|
| Key | Record identifier, commonly used for partition selection and grouping | `ORD-1001` |
| Value | Business payload | `OrderCreated` |

Keys and values can use two different Serdes. In many systems, the key is a `String` or `UUID`, while the value is JSON, Avro, or Protobuf. Never assume the same Serde applies to both.

## 2. Why Does Kafka Streams Need Serdes?

Kafka brokers do not store Java objects. Producers send bytes and consumers receive bytes. Kafka Streams needs to know how to translate those bytes at topology boundaries:

~~~text
Kafka topic
   |
   | bytes(key, value)
   v
Deserializer / Serde
   |
   | KStream<K, V>
   v
Kafka Streams DSL / Processor API
   |
   | KStream<K2, V2>
   v
Serializer / Serde
   |
   | bytes(key, value)
   v
Kafka output topic
~~~

If the key Serde does not match the bytes written by the producer, the consumer may fail to read the key or decode it into the wrong value. If the value Serde is incompatible, records can trigger deserialization exceptions before business logic runs. On the write path, an incorrect serializer writes records that downstream consumers cannot read.

Serdes also impact:

- Partitioning: Kafka partitioners typically compute partitions from serialized key bytes.
- Grouping and joins: keys must be decoded and compared under consistent semantics.
- Compaction: Kafka log compaction retains the latest state per key bytes.
- State stores and changelogs: Kafka Streams must serialize state data keys and values.
- Tombstones: a `null` value on a compacted topic can signify deleting a key from a `KTable`.

## 3. Binder Serde Inference from Function Signatures

In the functional model, the Kafka Streams Binder inspects the generic types of `KStream`, `KTable`, or `GlobalKTable` in the function signature. For example:

~~~java
@Bean
Function<KStream<String, OrderCreated>,
         KStream<String, OrderSummary>> summarizeOrders() {

    return orders -> orders
        .mapValues(event -> new OrderSummary(
            event.orderId(),
            event.total()
        ));
}
~~~

The signature tells the binder:

- Input key type is `String`.
- Input value type is `OrderCreated`.
- Output key type is `String`.
- Output value type is `OrderSummary`.

The binder can use this type information to locate matching Serdes for each binding. Default bindings are generated from the function name:

- `summarizeOrders-in-0`: input.
- `summarizeOrders-out-0`: output.

Declaring concrete generic types gives the binder more information. If you use `KStream<?, ?>`, raw types, or generic types erased at runtime, the binder may not know which key/value Serdes are needed. In such cases, explicit configuration is required.

## 4. Input Serde Inference Precedence

For inbound deserialization, the Kafka Streams Binder follows these steps:

1. If the application defines a `Serde<T>` bean whose type `T` matches the key/value type in the function signature, the binder can use that bean.
2. The binder checks types natively supported by Kafka Streams: `Integer`, `Long`, `Short`, `Double`, `Float`, `byte[]`, `UUID`, and `String`.
3. The binder checks whether default Serdes in Kafka Streams configuration match the required type.
4. If the type is a JSON-compatible object, the binder can use Spring Kafka's `JsonSerde`.
5. If inference cannot resolve a suitable Serde, the application must configure Serdes at the binding level or in default configuration.

A `keySerde` or `valueSerde` declared directly at the input binding level takes precedence over inference. Once configured there, the binder skips inference for that component.

For example, with `KStream<String, OrderCreated>`, the binder can typically pick `StringSerde` for the key and `JsonSerde<OrderCreated>` for the value. However, if the upstream producer emits Avro bytes, `JsonSerde` cannot read them; you must configure an appropriate Avro Serde or use compatible message conversion.

## 5. Output Serde Inference

Outbound serialization likewise relies on the output `KStream` key/value types. The binder looks up Serdes matching the output types. For Kafka-supported primitive/built-in types like `String`, `Long`, `UUID`, or `byte[]`, the binder selects the corresponding Serde; for JSON-friendly objects, it can use `JsonSerde`.

If a key Serde cannot be inferred, configure it explicitly. If a value Serde cannot be inferred or uses a specialized schema format, declare `valueSerde` on the output binding.

Example:

~~~java
@Bean
Function<KStream<String, OrderCreated>,
         KStream<String, OrderSummary>> summarizeOrders() {
    return input -> input.mapValues(event ->
        new OrderSummary(event.orderId(), event.total()));
}
~~~

Input and output have different value types. Input needs a Serde for `OrderCreated`; output needs a Serde for `OrderSummary`. Do not copy input configuration onto the output by default when the type or schema has changed.

## 6. Declaring keySerde and valueSerde per Input Binding

When the binder cannot infer a Serde, or when a specific schema is required, configure Serdes directly on the input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
          group: order-processor
      kafka:
        streams:
          bindings:
            processOrders-in-0:
              consumer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: com.example.kafka.OrderEventSerde
~~~

The exact prefix for the Kafka Streams Binder is `spring.cloud.stream.kafka.streams.bindings`, not the regular Kafka message-channel binder prefix `spring.cloud.stream.kafka.bindings`.

In this example:

- `consumer.key-serde` deserializes keys of the input topic.
- `consumer.value-serde` deserializes values of the input topic.
- `OrderEventSerde` is an application-provided Serde, either a class with a suitable constructor or a bean recognized by type.

With multiple inputs, each binding may use a different schema. For example, a `BiFunction` accepting a `KStream` and a `KTable`:

~~~java
@Bean
BiFunction<KStream<String, OrderEvent>,
           KTable<String, Customer>,
           KStream<String, EnrichedOrder>> enrichOrders() {
    return (orders, customers) ->
        orders.leftJoin(customers,
            (order, customer) -> new EnrichedOrder(order, customer));
}
~~~

Per-input configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            enrichOrders-in-0:
              consumer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: com.example.kafka.OrderEventSerde
            enrichOrders-in-1:
              consumer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: com.example.kafka.CustomerSerde
~~~

Do not assign a shared `valueSerde` across multiple inputs when topics carry different schemas. Binding-level Serdes give each input its own deserialization contract.

## 7. Declaring Serdes per Output Binding

Output bindings are configured similarly under the `producer` branch:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            enrichOrders-out-0:
              producer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: com.example.kafka.EnrichedOrderSerde
~~~

When a function branches into multiple `KStream[]` outputs, each output can write to a different topic and schema. Configure Serdes individually per output if the binder cannot infer them:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            routeEvents-out-0:
              producer:
                value-serde: com.example.kafka.OrderCreatedSerde
            routeEvents-out-1:
              producer:
                value-serde: com.example.kafka.OrderCancelledSerde
~~~

Do not assume branched outputs share the same value type or schema just because they originate from one function.

## 8. Using Explicitly Typed Serde Beans

If you prefer configuring Serdes in Java, register a bean with a concrete generic type:

~~~java
import org.apache.kafka.common.serialization.Serde;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.support.serializer.JsonSerde;

@Bean
Serde<OrderCreated> orderCreatedSerde() {
    return new JsonSerde<>(OrderCreated.class);
}
~~~

When a function uses `KStream<String, OrderCreated>`, the binder can detect the `Serde<OrderCreated>` bean and apply it to the corresponding value. The generic type in the bean's return signature is crucial; a bean returning a raw `Serde` reduces type-based inference capability.

If multiple `Serde` beans exist for the same type, avoid ambiguity. Declare the Serde directly on the binding to make the choice explicit, or organize beans/configurations so each data type has one matching Serde.

For custom Serdes, verify:

- Serializer and deserializer use the same wire format.
- Schema registry configuration or required endpoints are passed into the Serde.
- The serializer handles `null`/tombstone values properly if required by business logic.
- The Serde closes resources properly if it holds connections or clients.
- Both producer and corresponding consumer use compatible settings.

## 9. Configuring Default Serdes at the Binder Level

If many bindings in an application share the same common key/value types, you can configure default Serdes in Kafka Streams configuration:

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

`default.key.serde` and `default.value.serde` are Kafka Streams properties, so they live under `spring.cloud.stream.kafka.streams.binder.configuration`. They apply at the binder/application scope, so use them only when they truly represent a suitable global default.

Whenever an input or output needs a different schema, declare `key-serde`/`value-serde` at the binding level to override the default. Do not set a global JSON or String default Serde expecting it to decode every topic with disparate schemas.

## 10. Differences Between Serdes and Spring MessageConverter

The Kafka Streams Binder supports two data conversion paths at processor boundaries:

| Approach | Handled By | When Appropriate |
|---|---|---|
| Native Kafka Serde | Kafka / Kafka Streams | Native serialization needed, strongly typed key/value, Avro/JSON/custom Serde |
| Spring Cloud Stream MessageConverter | Framework converts `Message` by content type | Upstream producer uses a format requiring a matching converter |

In the current Kafka Streams Binder, inbound keys are always decoded using native Serdes. Inbound values also use native Kafka decoding by default. If you want the framework to convert values via message conversion, disable native decoding on each input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          content-type: application/json
          consumer:
            native-decoding: false
~~~

The framework then uses the content type and an appropriate `MessageConverter` to convert the value. With multiple inputs, set `native-decoding: false` on each input that requires framework conversion.

On the output side, native encoding is used by default. To have Spring Cloud Stream's `MessageConverter` encode outbound values, set:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-out-0:
          content-type: application/json
          producer:
            native-encoding: false
~~~

When native decoding/encoding is disabled, the binder does not perform native Serde inference for that binding. The application must configure the corresponding content type and converter. Never mix both mechanisms without clearly defining which component owns byte serialization/deserialization.

## 11. JSON Serde Example for POJOs

Suppose the `orders.events` topic contains JSON payloads of `OrderCreated`. The function declares concrete types:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    long total
) {}

public record OrderSummary(
    String orderId,
    long total
) {}

@Bean
Function<KStream<String, OrderCreated>,
         KStream<String, OrderSummary>> summarizeOrders() {
    return orders -> orders.mapValues(event ->
        new OrderSummary(event.orderId(), event.total()));
}
~~~

For JSON-friendly POJOs, the binder can use Spring Kafka's `JsonSerde` if no more specific `Serde` bean or binding-level override exists. Topic and group configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: summarizeOrders
    stream:
      bindings:
        summarizeOrders-in-0:
          destination: orders.events
          group: order-summary
        summarizeOrders-out-0:
          destination: orders.summary
~~~

`JsonSerde` must have enough metadata to deserialize the target type accurately. If producer and consumer do not share the same type-header convention, or upstream sends plain JSON without type headers, configure the target type explicitly via a `Serde` bean or an appropriate deserializer. Do not assume any JSON document automatically becomes the target POJO just because the function signature declares that type.

## 12. Avro Serde and Schema Registry Example

With Avro, producers typically write payloads in the wire format defined by Schema Registry serializers. Consumers need the matching Serde, such as `SpecificAvroSerde` for generated `SpecificRecord` classes:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              schema.registry.url: http://schema-registry:8081
          bindings:
            processOrders-in-0:
              consumer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: io.confluent.kafka.streams.serdes.avro.SpecificAvroSerde
            processOrders-out-0:
              producer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: io.confluent.kafka.streams.serdes.avro.SpecificAvroSerde
~~~

This example assumes Confluent Serde dependencies are on the classpath and the corresponding Avro schemas and generated classes exist. `schema.registry.url` configures the Serde; if the environment requires authentication or a custom subject naming strategy, configure them according to your Schema Registry policy.

For Protobuf or other formats, use the corresponding ecosystem Serde. What matters is that the consumer reads the exact wire format written by the producer; similar Java class names do not guarantee compatible byte encodings.

## 13. Binding Boundary Serdes vs. DSL Serdes

The binder infers or configures Serdes for inbound and outbound bindings. Those Serdes govern reading from input topics and writing to output topics.

Inside business logic, several Kafka Streams DSL APIs also require their own Serdes. The binder cannot infer every Serde used internally within a topology. Applications must pass them when calling APIs such as:

- `Consumed.with(keySerde, valueSerde)`.
- `Produced.with(keySerde, valueSerde)`.
- `Grouped.with(keySerde, valueSerde)`.
- `Joined.with(keySerde, leftValueSerde, rightValueSerde)`.
- `Repartitioned.with(keySerde, valueSerde)`.
- `Materialized.with(keySerde, valueSerde)`.

Example grouping by key and counting events:

~~~java
@Bean
Function<KStream<String, OrderCreated>, KTable<String, Long>> countOrders(
        Serde<OrderCreated> orderCreatedSerde) {

    return orders -> orders
        .groupByKey(Grouped.with(
            Serdes.String(),
            orderCreatedSerde
        ))
        .count(Materialized.as("order-counts"));
}
~~~

`Grouped.with` tells Kafka Streams which Serdes to use when grouping and repartitioning. If a topology uses joins, repartitions, aggregations, or state stores, check the Serdes required by each DSL operator. Binding-level Serdes do not automatically substitute for explicit Serdes in internal operators.

## 14. Serdes for State Stores and Changelogs

Kafka Streams creates state stores when a topology uses stateful operations such as `count`, `aggregate`, `reduce`, `join`, or `materialize`. State stores use key/value Serdes to write local data and changelog topics.

Serdes can be specified on `Materialized`:

~~~java
Materialized.<String, Long, KeyValueStore<Bytes, byte[]>>as("order-counts")
    .withKeySerde(Serdes.String())
    .withValueSerde(Serdes.Long());
~~~

If a binding receives a `KTable` and you want to materialize it into a named state store, the Kafka Streams Binder also provides `materializedAs` on the consumer binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            processOrders-in-1:
              consumer:
                materialized-as: customer-store
~~~

`materializedAs` names the store for an incoming `KTable` binding; it does not replace choosing the right key/value Serdes for the store. If using the Processor API and building a `StoreBuilder` manually, pass the matching Serdes to the store builder.

When changing a state store/changelog Serde, evaluate compatibility with existing state. If the new byte format cannot read the old changelog, the application may need a new store name/application ID or a controlled state reset/rebuild plan. Never change Serdes in production without checking existing state data.

## 15. KeySerde, Partitioning, and Compaction

Kafka partitioners typically select partitions based on serialized key bytes. Two producers might build the same Java `CustomerKey` object, yet if they use different Serdes, the resulting key bytes differ—leading to different partitions. Events for the same customer can then scatter across partitions, breaking ordering and grouping assumptions.

Key Serdes also matter for log compaction. Kafka identifies records with the same key based on serialized key bytes. If a producer changes how keys are encoded without migrating, the same customer can exist under two distinct key byte sequences and compaction will not treat them as the same key.

Principles:

- Choose a stable key schema and encoding.
- Use the same key Serde across every producer and consumer participating in a stream.
- Do not change key normalization, casing, or formatting across versions.
- If key formats must change, design a migration or versioned topic.
- Verify actual partition placement whenever changing Serdes, partition counts, or partitioners.

## 16. Tombstones and Null Values

In a compacted topic, a record with a non-null key and a `null` value is typically a tombstone instructing Kafka to remove that key's state during compaction. For a `KTable`, a tombstone deletes the corresponding row.

Example:

~~~text
key = "customer-100"
value = {"name":"An","tier":"GOLD"}

key = "customer-100"
value = null
~~~

The second record signals deleting `customer-100` from the state table. Value Serdes and business logic must handle `null` gracefully. Do not treat every `null` value as a corrupted message or attempt to deserialize `null` into a POJO. If a topic does not use tombstone semantics, document explicitly what `null` means in the event contract.

## 17. Windowed Keys and Specialized Serdes

When a topology uses windowing, keys in certain state stores or outputs may be `Windowed<K>` rather than plain `K`. In that case, a plain `Serdes.String()` is insufficient for the windowed key. Kafka Streams provides specialized Serdes for time windows and session windows, such as `TimeWindowedSerde` or `SessionWindowedSerde`.

Select the right Serde matching the window type in use. When writing windowed keys to a topic, downstream consumers must either understand that wire format or map back to a standard business key before publishing. Never let `Windowed<K>` leak into an output contract where downstream expects plain `K`.

## 18. Handling Deserialization Errors

If topic bytes do not match the configured Serde, Kafka Streams can raise a deserialization exception before the function receives the record. The binder supports these handling strategies:

- `logAndFail`: logs the error and stops processing; this is Kafka Streams' default.
- `logAndContinue`: logs the error and skips the faulty record to continue.
- `sendToDlq`: sends the faulty record to a dead-letter topic.

This can be configured at the binder level:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            deserialization-exception-handler: sendToDlq
~~~

Or configured individually per input binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            processOrders-in-0:
              consumer:
                deserialization-exception-handler: sendToDlq
~~~

A binding-level handler takes precedence over a binder-level handler. When using `sendToDlq`, create and configure an appropriate DLQ topic. By default, failed records are routed to the same partition number as the source partition, so the DLQ needs enough partitions; if you change the partitioning strategy, provide a `DlqPartitionFunction`.

Do not enable `logAndContinue` blindly for financial data or events that cannot be lost. Skipping records can corrupt downstream state. For poison pills, a DLQ usually preserves the record for investigation and replay after fixing the schema or Serde.

## 19. Common Serde Configuration Mistakes

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `SerializationException` when writing output | Output `valueSerde` does not match object type | Check output generics and producer Serde |
| `DeserializationException` when reading input | Topic uses a different wire format than configured Serde | Inspect raw bytes, producer serializer, and schema registry |
| Key decoded as `byte[]` or unexpected type | Missing suitable key Serde or overly broad generic type | Declare `consumer.keySerde` |
| JSON deserializes into wrong class | Missing type mapping/headers or wrong target type | Use a typed `Serde` bean or custom deserializer |
| Avro schema not found | Incorrect registry URL, authentication, or subject strategy | Check Schema Registry settings and schema ID |
| Join fails despite seemingly identical keys | Key bytes or normalization rules differ | Compare serialized keys and Serdes on both inputs |
| State store fails to restore after deploy | Changelog byte format incompatible with new Serde | Check state store, changelog, and migration plan |
| Branch output fails on one topic | Multiple outputs have different schemas but share one Serde | Configure dedicated Serdes per output binding |

## 20. Testing Serdes

Test both round-trip serialization and compatibility with real data:

1. Serialize a sample key/value, then deserialize it and assert equality.
2. Verify JSON/Avro/Protobuf bytes produced by the current producer can be read by the consumer.
3. Verify the key Serde across all producers emits identical bytes for identical business keys.
4. Test `null` values/tombstones if the topic is compacted or bound as a `KTable`.
5. Test historical records from prior schema versions before rolling out a new Serde.
6. Verify state stores and changelogs recover cleanly after a restart.
7. Send a record with an invalid wire format and confirm the deserialization exception handler triggers.
8. Verify every input and output binding on multi-input and branching functions.
9. Run integration tests against real Kafka or Testcontainers; the Test Binder does not replace testing real broker serializers/deserializers and raw record bytes.

Simple round-trip test example:

~~~java
@Test
void orderSerdeRoundTrip() {
    Serde<OrderCreated> serde = new JsonSerde<>(OrderCreated.class);
    OrderCreated original =
        new OrderCreated("evt-1", "ORD-1001", 250000L);

    byte[] bytes = serde.serializer().serialize("orders.events", original);
    OrderCreated decoded =
        serde.deserializer().deserialize("orders.events", bytes);

    assertThat(decoded).isEqualTo(original);
}
~~~

Close the Serde after testing if the test instantiates it directly and the Serde holds releasable resources. In integration tests, verify that the binder applies the right key/value Serdes to the right bindings, rather than testing the Serde class in isolation alone.

## 21. Configuration Checklist

- [ ] Function signatures use concrete generic types for keys/values of each `KStream`/`KTable`.
- [ ] Understand that inbound keys always use native Serdes and inbound values use native deserialization by default.
- [ ] Verify whether Serdes are resolved from beans, Kafka built-in types, default config, or `JsonSerde`.
- [ ] Configure binding-level `consumer.keySerde`/`consumer.valueSerde` when overriding input inference.
- [ ] Configure binding-level `producer.keySerde`/`producer.valueSerde` when outputs need specific Serdes.
- [ ] Binder-level default key/value Serdes fit application-wide scope.
- [ ] Distinguish the Kafka Streams Binder prefix from the regular Kafka Binder prefix.
- [ ] Native decoding/encoding vs. Spring `MessageConverter` is chosen explicitly.
- [ ] DSL operators such as `Grouped`, `Joined`, and `Materialized` receive appropriate Serdes.
- [ ] State stores, changelogs, tombstones, and windowed keys use compatible Serdes.
- [ ] Key encoding is consistent across all producers to preserve partitioning and compaction semantics.
- [ ] Deserialization exception handler and DLQ policies are defined.
- [ ] Round-trip, historical records, schema registry, and real-broker integration tests are verified.

Serdes determine how Kafka Streams reads and writes bytes for keys and values. The Spring Cloud Stream Kafka Streams Binder can infer Serdes in many cases from function signatures, `Serde` beans, and common Kafka types; when precise control is required, configure `keySerde` and `valueSerde` per binding or defaults at the binder level. Keep binding-boundary Serdes distinct from Serdes required inside DSL operators and state stores, and keep key encodings and schemas compatible across producers, processors, and consumers.

## References

- [Spring Cloud Stream — Kafka Streams Binder: Record Serialization and Deserialization](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html#record-serialization-and-deserialization)
- [Spring Cloud Stream — Kafka Streams Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring for Apache Kafka — Serialization, Deserialization and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Apache Kafka Streams — Data Types and Serdes](https://kafka.apache.org/documentation/streams/developer-guide/datatypes.html)
