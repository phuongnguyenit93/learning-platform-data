# Configuring useNativeEncoding and useNativeDecoding

Spring Cloud Stream can convert Java payloads into broker-transmissible data using framework message converters, or delegate serialization to the binder's native mechanism. The two properties `useNativeEncoding` and `useNativeDecoding` control that choice independently in each direction:

- `useNativeEncoding` is placed on an output binding and determines how payloads are serialized before sending.
- `useNativeDecoding` is placed on an input binding and determines how data received from the broker is decoded into application objects.

By default, Spring Cloud Stream generally uses message conversion based on content type. When native encoding or decoding is enabled, the binder and broker client library handle the corresponding serialization or deserialization. This choice is useful when you need Kafka Serializers/Deserializers, native schemas, or broker-specific data formats. However, producers and consumers must agree on the wire format; if the two sides are configured incompatibly, messages may be sent successfully yet fail to decode at the consumer.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish Spring Cloud Stream message conversion from binder native serialization.
- Configure `useNativeEncoding` on output bindings and `useNativeDecoding` on input bindings.
- Choose appropriate serializers/deserializers when using the Kafka binder.
- Understand the role of content type when native encoding/decoding is enabled or disabled.
- Evaluate native serialization support across Kafka, RabbitMQ, and Pulsar binders.
- Pair producers and consumers with compatible wire formats.
- Test payloads through a broker and handle serialization/deserialization errors.

## 1. Two Data Conversion Mechanisms

A Spring Cloud Stream function works with Java types, such as `OrderCreated`. The broker needs data in a specific wire format such as JSON bytes, Avro bytes, or another binary format. Converting between Java objects and wire data is called serialization/deserialization or message conversion, depending on the layer performing it.

Spring Cloud Stream provides message conversion at the framework level. Binders can also use the native serialization mechanisms of the broker or client library.

### Spring Cloud Stream message conversion

When native encoding/decoding is disabled, the framework uses message converters to transform payloads based on data type and content type.

For example, an output binding receives an `OrderCreated` object and has `contentType: application/json`. A matching converter can serialize the object into JSON bytes. On the consumer side, a converter reads the JSON payload and reconstructs the Java object matching the function's input type.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          contentType: application/json
        inventory-in-0:
          destination: orders
          group: inventory
          contentType: application/json
~~~

This is the common approach when an application wants to use Spring Cloud Stream's unified conversion mechanism without configuring broker-specific serializers.

### Native encoding and native decoding

When `useNativeEncoding: true` is enabled, the output binding instructs the binder to use its native mechanism to serialize payloads. The framework does not perform normal outbound message conversion.

When `useNativeDecoding: true` is enabled, the input binding instructs the binder to use its native mechanism to decode received data. The framework does not perform normal inbound message conversion.

| Property | Binding | Data direction | Effect |
|---|---|---|---|
| `useNativeEncoding` | Output | Application → broker | Uses the binder's native serializer/mechanism |
| `useNativeDecoding` | Input | Broker → application | Uses the binder's native deserializer/mechanism |

The two properties are independent. An application can enable native encoding on an output binding while still using message converters on an input binding, or vice versa. What matters is that data on the wire is compatible with how the receiving side decodes it.

## 2. Processing Flow with Native Mode Enabled and Disabled

Outbound flow using message converter:

1. Function or service produces a Java payload.
2. Output binding determines content type and message converter.
3. Converter transforms the payload into bytes.
4. Binder sends bytes and required metadata to the broker.

Outbound flow with native encoding enabled:

1. Function or service produces a Java payload.
2. Output binding hands the payload to the binder.
3. Native serializer configured by the binder/client produces wire data.
4. Broker receives serialized data with native metadata.

Inbound flow using message converter:

1. Binder receives bytes from the broker.
2. Binder constructs a Spring Message and corresponding metadata.
3. Message converter uses content type to convert bytes into a Java payload.
4. Function or Consumer receives the data.

Inbound flow with native decoding enabled:

1. Binder receives data from the broker.
2. Native deserializer converts the data into the Java type expected by the application.
3. Binder passes the decoded payload to the input binding.
4. Function or Consumer receives the data.

~~~mermaid
flowchart TD
    A["Java payload at producer"] --> B{"useNativeEncoding?"}
    B -->|false| C["Spring MessageConverter"]
    B -->|true| D["Binder native serializer"]
    C --> E["Bytes on broker"]
    D --> E
    E --> F["Binder receives message"]
    F --> G{"useNativeDecoding?"}
    G -->|false| H["Spring MessageConverter"]
    G -->|true| I["Binder native deserializer"]
    H --> J["Java payload at consumer"]
    I --> J
~~~

In both paths, the binder still manages connections, destinations, groups, and message delivery. Native mode only changes the serialization or decoding layer; it does not automatically alter consumer groups, partitions, retries, or broker retention policies.

## 3. Configuring useNativeEncoding on Output Bindings

The `useNativeEncoding` property is placed under the binding's `producer` section:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          producer:
            useNativeEncoding: true
~~~

When enabled, the binder uses the serializer or native mechanism configured for that binding. With Kafka, this usually means configuring Kafka producer serializers for key and value.

Example of an event-emitting function:

~~~java
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderSourceConfiguration {

    @Bean
    Supplier<OrderCreated> orderSource(OrderEventSource source) {
        return source::pollNextPendingEvent;
    }
}
~~~

The `orderSource-out-0` binding can be configured with native encoding. With a Supplier, each time the poller fetches an object, the binder applies the selected serializer to send the payload.

You can enable native encoding on one output binding while keeping default message conversion on another. There is no need to enable it application-wide if only one stream requires a specialized serializer.

## 4. Configuring useNativeDecoding on Input Bindings

The `useNativeDecoding` property is placed under the binding's `consumer` section:

~~~yaml
spring:
  cloud:
    stream:
      function:
        definition: inventory
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
          consumer:
            useNativeDecoding: true
~~~

When enabled, the binder uses the native deserializer to construct the Java payload. The data type returned by the deserializer must match the function signature.

Consumer example:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InventoryConfiguration {

    @Bean
    Consumer<OrderCreated> inventory() {
        return event -> {
            System.out.println("Order: " + event.orderId());
        };
    }
}
~~~

If the deserializer returns `byte[]` while the function expects `OrderCreated`, the consumer will not receive the expected data type. Either configure the deserializer to instantiate the right object, or design the function to accept a byte array and decode it according to the contract.

## 5. Kafka Example: Using Native Serializer and Deserializer

Kafka stores record values and keys as byte arrays. Kafka producers use serializers to convert objects into bytes; consumers use deserializers to turn bytes back into application types.

With the Kafka binder, native encoding/decoding is typically used when you need control over serializers/deserializers at the Kafka layer. Serializers and deserializers can be configured per binding under the Kafka binder namespace.

Suppose the producer sends `OrderCreated` as JSON using `JsonSerializer`, and the consumer decodes it with `JsonDeserializer`.

### Producer configuration

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          producer:
            useNativeEncoding: true
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
                value.serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

Here:

- `useNativeEncoding: true` tells the Kafka binder to use the native serializer.
- `StringSerializer` serializes the record key if the application uses string keys.
- `JsonSerializer` serializes the value object into JSON bytes.

If keys are unnecessary, key serializer configuration can be adjusted according to your application's key type and producer policy.

### Consumer configuration

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
          consumer:
            useNativeDecoding: true
      kafka:
        bindings:
          inventory-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
                spring.json.value.default.type: com.example.events.OrderCreated
                spring.json.trusted.packages: com.example.events
~~~

On the consumer side:

- `useNativeDecoding: true` tells the binder to use the Kafka deserializer.
- `StringDeserializer` decodes the record key into a string.
- `JsonDeserializer` decodes the value into `OrderCreated`.
- `spring.json.value.default.type` specifies the default target type if the serializer/deserializer configuration needs type information.
- `spring.json.trusted.packages` restricts packages allowed for decoding according to Spring Kafka configuration.

Replace the package and class names in the example with your application's actual types. Trust only packages containing controlled DTOs; never open trusted packages to all packages merely to bypass decoding errors.

### Contract between producer and consumer

Producers and consumers must agree on:

- The data type of the record key.
- The data type of the record value.
- The corresponding serializer and deserializer.
- JSON structure and schema compatibility rules.
- How type metadata generated by the serializer is handled.
- Versions of serializer/deserializer libraries in use.

If the producer uses `JsonSerializer` while the consumer uses `StringDeserializer` for the value, the consumer receives a JSON string instead of `OrderCreated`. That only works if the function accepts a string and parses it manually. If the function accepts `OrderCreated`, a compatible deserializer is required.

## 6. Content Type When Using Native Mode

Content type and native encoding/decoding are related, not interchangeable.

- `contentType` describes the payload format and supports Spring Cloud Stream message conversion.
- `useNativeEncoding` tells the binder to use native serialization for outbound messages.
- `useNativeDecoding` tells the binder to use native deserialization for inbound messages.

When native mode is enabled in one direction, do not assume Spring Cloud Stream still uses content type to convert payloads in that direction. Native serializers/deserializers must know how to handle the data type and wire format.

For example, Kafka's `JsonSerializer` produces JSON bytes. A consumer can decode them with Kafka's `JsonDeserializer` or receive bytes/strings and apply a separate conversion step. Setting `contentType: application/json` alone does not configure Kafka serializers/deserializers once native encoding/decoding is enabled.

When not using native mode, content type is usually the key signal for the framework to choose a converter. Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          contentType: application/json
        inventory-in-0:
          destination: orders
          group: inventory
          contentType: application/json
~~~

If a producer uses native encoding and the consumer uses a message converter, the combination can still work when the native serializer emits the exact wire format that the receiving converter can decode for that content type. Conversely, a producer using a message converter and a consumer using native decoding can also work if the deserializer understands the exact bytes produced. Such combinations require integration testing rather than guessing from content type names.

## 7. Combining Native Encoding and Decoding

Both properties are configured independently per binding. The following table outlines how to reason about the combinations:

| Producer | Consumer | Condition |
|---|---|---|
| Native encoding off | Native decoding off | Spring Cloud Stream converters on both sides must agree on content type |
| Native encoding on | Native decoding on | Native serializer and deserializer must agree on wire format and data types |
| Native encoding on | Native decoding off | Bytes produced by native serializer must be decodable by the receiving converter |
| Native encoding off | Native decoding on | Bytes produced by framework converter must be compatible with native deserializer |

In a greenfield system, it is usually easiest to manage when both sides use the same serialization strategy. If you need to connect a non-Spring producer to a Spring Cloud Stream consumer, native mode can help integrate directly with the serializer/deserializer that the external producer already uses.

Not every binding in an application has to use the same mode. For example, one Kafka output binding can use an Avro serializer while another input binding still uses the JSON message converter. Per-binding configuration gives each stream its own data contract.

## 8. Native Encoding and Decoding with RabbitMQ and Pulsar

The general meaning of both properties is to instruct the binder to use its native mechanism instead of the framework's standard message conversion. However, capabilities and serializer/deserializer configuration vary by binder.

### RabbitMQ binder

RabbitMQ transmits bodies as bytes and supports AMQP properties and headers. The RabbitMQ binder typically integrates with Spring AMQP's message conversion mechanism. Support for native encoding/decoding and how converters are specified depend on the binder version and its configuration.

Do not take Kafka's `key.serializer`, `value.serializer`, or `value.deserializer` settings and apply them to RabbitMQ. Those properties belong to the Kafka client. With RabbitMQ, check the message converters and options specific to the Rabbit binder in use, and verify whether the actual body is JSON, a byte array, or another format.

If interoperating with a non-Spring AMQP application, agree on content type, content encoding, body type, and AMQP properties. Native mode does not automatically establish a shared schema across applications.

### Pulsar binder

Pulsar supports schema-aware producers and consumers. Native serialization can leverage schemas and data types supported by the Pulsar client, depending on binder and version. Producers and consumers must agree on schema type, schema version, and corresponding Java types.

Do not apply Kafka serializer/deserializer settings to Pulsar. Use the schema or serialization options provided by your current Pulsar binder version. If schemas are incompatible, consumers may fail to decode messages or fail to subscribe with the desired configuration.

### Comparison table

| Binder | Commonly involved native mechanism | What to verify |
|---|---|---|
| Kafka | Kafka Serializer/Deserializer for key and value | Serializer/deserializer classes, key/value types, JSON/Avro bytes, and trusted packages config |
| RabbitMQ | Spring AMQP and binder message conversion/serialization mechanism | Converter in use, content type, AMQP properties, and body bytes |
| Pulsar | Pulsar client Schema and serializer/deserializer | Schema type, schema version, payload type, and binder compatibility |

Not every binder exposes the same level of native configuration. Before enabling the flags, check the documentation for the exact binder and version being deployed. If a binder does not support the desired behavior, use standard message conversion or a serialization mechanism explicitly supported by that binder.

## 9. When Should You Use Native Encoding/Decoding?

Native mode is well suited in these situations:

- Producer or consumer requires a specific Kafka serializer/deserializer.
- The system uses Avro, Protobuf, or native schemas managed by the broker platform.
- A Spring application needs to exchange data with producers/consumers outside Spring Cloud Stream using an agreed wire format.
- Exact control over keys, values, and serialization is needed rather than relying on default converters.
- Leveraging binder-specific schema or serialization features.

Default message conversion is usually more convenient when:

- The application primarily transmits Java DTOs as JSON.
- Broker-specific serializer configuration is unnecessary.
- You want the same conversion mechanism across multiple binders.
- You want to rely on Spring Cloud Stream content types and message converters.

Native mode is not inherently faster or better. It shifts serialization responsibility to the binder/client and makes wire format configuration more critical. Choose based on integration requirements, schemas, and operability.

## 10. Common Risks and Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Consumer cannot decode payload | Deserializer incompatible with serializer | Align serializer/deserializer and wire format |
| Function receives `byte[]` instead of DTO | Native deserializer returns bytes or target type is unconfigured | Configure deserializer with the right type or decode explicitly in the app |
| Kafka reports serializer error | Serializer does not support actual payload type | Use a serializer matching the object type or convert payload before sending |
| Kafka reports deserializer error | Bytes are malformed or JSON type is invalid | Check producer bytes, default type, and schema |
| JSON is on the broker but function fails | Consumer has native decoding enabled with wrong deserializer | Choose `JsonDeserializer` or use message converter |
| Content type makes no difference | Native mode bypasses framework conversion in that direction | Configure native serializer/deserializer |
| Producer sends fine but consumer never receives | Deserializer throws errors, or wrong group/destination | Check binder logs, consumer group, and broker resources |
| Avro/Protobuf incompatibility | Schema version or schema registry mismatch | Synchronize schemas and compatibility policies |
| RabbitMQ receives body but cannot read it | AMQP converter or content type mismatch | Check body bytes, contentType, and binder converter |
| Pulsar cannot decode | Schema type or schema version incompatible | Check schema and Pulsar binder native configuration |

When diagnosing, distinguish send errors from decode errors. A producer can send successfully because its serializer works, yet the consumer still fails when its deserializer receives unexpected byte structures. Check logs on both sides and inspect actual payloads in a test environment.

## 11. Testing Native Serialization

Testing native mode should cover three levels.

### Unit testing serializer/deserializer

If the application uses custom serializers, verify round-trip behavior:

1. Create a sample object.
2. Serialize into bytes.
3. Deserialize bytes back into an object.
4. Compare key fields and verify schema version.

For JSON, check fields, numeric types, dates/times, and null values. For Avro or Protobuf, check schemas and compatibility rules when adding or changing fields.

### Binding tests

The Test Binder can test functions and bindings at the Spring Cloud Stream level, but it does not fully simulate all broker-native serializers. Do not use Test Binder results as sole proof that Kafka `JsonSerializer`, Avro serializers, or Pulsar schemas work correctly.

### Broker integration tests

Run a real broker or Testcontainers to verify:

- Output binding uses the right serializer.
- Messages on the broker have the expected wire format.
- Input binding uses the right deserializer.
- Function receives the expected payload type.
- Required headers and metadata remain present.
- Consumer processes messages properly after application restarts.

With Kafka, you can use a console consumer or a test consumer configured with the appropriate deserializer to inspect the topic. Do not read with the wrong deserializer and conclude the data is corrupted. With Pulsar, use a schema-compatible client; with RabbitMQ, inspect bodies and AMQP properties with an appropriate client or management tool.

## 12. Hands-On Workflow: Enabling Native Mode for Kafka

Carry out these steps in a development environment with Kafka:

1. Declare the `OrderCreated` record with `eventId`, `orderId`, and `total`.
2. Create output binding `orders-out-0` targeting destination `orders`.
3. Enable `producer.useNativeEncoding: true`.
4. Configure Kafka `JsonSerializer` for value and an appropriate serializer for key.
5. Create input binding `inventory-in-0` with destination `orders` and group `inventory`.
6. Enable `consumer.useNativeDecoding: true`.
7. Configure Kafka `JsonDeserializer` with target type `OrderCreated` and appropriate trusted packages.
8. Start producer and consumer, and emit a sample event.
9. Verify the consumer receives the right object and data fields.
10. Try swapping the deserializer to `StringDeserializer`; observe the consumer receiving a string or throwing a type error depending on function signature.
11. Restore the right deserializer and re-run the test.
12. Try a compatible schema change, then verify producer and consumer still exchange messages.

Illustrative producer and consumer configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      bindings:
        orders-out-0:
          destination: orders
          producer:
            useNativeEncoding: true
        inventory-in-0:
          destination: orders
          group: inventory
          consumer:
            useNativeDecoding: true
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
                value.serializer: org.springframework.kafka.support.serializer.JsonSerializer
          inventory-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
                spring.json.value.default.type: com.example.events.OrderCreated
                spring.json.trusted.packages: com.example.events
~~~

Replace `com.example.events.OrderCreated` and the corresponding package with the real class in your application. If producer and consumer are two independent applications, ensure both use compatible schemas and settings. Do not set trusted packages broader than necessary.

## Conclusion

`useNativeEncoding` and `useNativeDecoding` let Spring Cloud Stream delegate payload serialization and deserialization to the binder's native mechanism. Producers use native encoding on output bindings; consumers use native decoding on input bindings. The two options are independent, but they must produce a compatible wire format.

With Kafka, properly configure serializers/deserializers for key and value; with RabbitMQ, understand converters and AMQP body/properties; with Pulsar, agree on schemas and binder-supported data types. Run round-trip tests on a real broker, because content types or the Test Binder alone do not prove that native serialization is configured properly.
