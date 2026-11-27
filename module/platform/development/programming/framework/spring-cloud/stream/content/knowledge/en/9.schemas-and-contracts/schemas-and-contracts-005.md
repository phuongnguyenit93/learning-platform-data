# Integrating Avro MessageConverter or Native Serde by Binder

Apache Avro is a schema-based binary data format. In a Spring Cloud Stream system, Avro helps producers and consumers exchange structured data, reduce payload size, and manage contract changes across versions. However, Avro is only effective when both sides agree on how to serialize, how to locate schemas, and how to resolve differences between the writer schema and reader schema.

Spring Cloud Stream can integrate Avro in two main ways. An application can use an **Avro MessageConverter** so the framework converts payloads based on content type and a schema registry, or use **native serializers/deserializers (Serde)** provided by the binder and broker client. The choice depends on the broker, existing schema infrastructure, and interoperability requirements with applications outside Spring Cloud Stream.

This lesson focuses on choosing and configuring these two approaches for Kafka, RabbitMQ, and Pulsar, while covering how to manage writer schemas, reader schemas, compatibility, and message contract testing.

## Learning Objectives

After this lesson, you will be able to:

- Explain the roles of an Avro schema, writer schema, reader schema, and schema registry.
- Distinguish Spring Cloud Stream's Avro MessageConverter from a binder's native Avro Serde.
- Choose between `SpecificRecord`, `GenericRecord`, or POJOs based on schema management needs.
- Configure an Avro MessageConverter with a fixed schema or a schema registry.
- Configure Kafka Avro Serializer/Deserializer and Pulsar Avro schema per binder.
- Choose an appropriate conversion approach when using RabbitMQ.
- Evaluate schema changes against backward, forward, and full compatibility.
- Test round-trip serialization and message readability across producer/consumer versions.

## 1. Avro Schemas and Message Contracts

Avro defines data structures using schemas. A schema describes the record name, namespace, fields, data types, default values, and related rules. The producer serializes data using the writer schema; the consumer decodes data using the schema associated with the message and the schema expected by the current application.

Example schema for the `OrderCreated` event:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    { "name": "totalMinorUnits", "type": "long" },
    { "name": "currency", "type": "string" },
    { "name": "source", "type": ["null", "string"], "default": null }
  ]
}
~~~

In this example, `totalMinorUnits` stores the monetary amount in the smallest unit of the currency, avoiding floating-point numbers in financial contracts. The `source` field is a union of `null` and `string`, with a default value of `null`.

The schema acts as the contract between producer and consumer. When changing a schema, consider whether running applications may still use older versions. A change that is valid for a new producer can still break an older consumer if it violates schema resolution rules.

### Writer Schema and Reader Schema

- **Writer schema** is the schema the producer uses to write the message.
- **Reader schema** is the schema the consumer uses to build the object read by the application.
- **Schema resolution** is the process by which Avro reconciles the two schemas to determine which fields are read, ignored, or populated with default values.

For example, producer v1 writes `OrderCreated` without the `source` field. Consumer v2 has added the `source` field with a default of `null`. When reading old messages, Avro can populate `null` for the new field using the default.

If the consumer requires a field that the writer schema does not supply and the reader schema declares no default, reading can fail. Thus, defaults in Avro schemas are part of the compatibility strategy, not merely convenient initializers.

### Schema Registry

A schema registry stores schemas, subjects, and versions so producers and consumers can look up the same contract. Depending on the system, the registry also enforces compatibility policies before accepting new versions.

A registry typically helps:

- Avoid embedding the entire schema into every message.
- Look up the writer schema via a schema ID or version metadata.
- Manage schema history per subject.
- Check compatibility before publishing a new schema.
- Allow consumers to use their own application version's reader schema.

A schema registry does not automatically guarantee message compatibility. Producers must still emit compliant schemas, consumers must have appropriate reader schemas, and compatibility policies must align with the deployment lifecycle.

## 2. Choosing an Avro Integration Approach in Spring Cloud Stream

The two common approaches have different responsibility boundaries:

| Criterion | Avro MessageConverter | Native Avro Serde |
|---|---|---|
| Conversion component | Spring Cloud Stream message converter | Binder or broker client serializer/deserializer |
| Activation mechanism | Content type and registered/configured converter | Native encoding/decoding and Serde configuration |
| Schema management | Can use Spring Cloud Stream's `SchemaRegistryClient` | Follows broker's serializer/schema registry or schema API |
| Broker dependency | Lower at the conversion logic layer | Higher, depends on broker Serde |
| Interoperability outside Spring | Must align on converter wire format | Convenient when sharing the same Serde and wire format |
| Support scope | Depends on converter module and version | Depends on binder/client and schema features |

**Avro MessageConverter** fits when you want Spring Cloud Stream to manage payload conversion and potentially use the built-in schema registry client. **Native Serde** fits when the broker already has a standard serialization ecosystem, such as Kafka with Confluent Schema Registry or Pulsar with native schemas.

Do not pick native solely because Avro is binary. Determine who owns the schemas, what standard non-Spring producers use to serialize, and which Java types consumers expect to receive.

## 3. Using Avro MessageConverter with a Fixed Schema

Spring Cloud Stream provides `AvroSchemaMessageConverter` in the schema registry/converter support module matching your release train. The converter can work with a known schema, a schema on the classpath, or a schema derived from the payload's Avro type.

One approach is using Avro `SpecificRecord`: a Java class generated from an `.avsc` file that embeds its corresponding schema. Another approach is `GenericRecord`, where the application constructs records against an explicitly supplied schema.

Example registering a converter with a fixed schema on the classpath:

~~~java
import org.springframework.cloud.stream.schema.avro.AvroSchemaMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.MimeType;

@Configuration
public class AvroConverterConfiguration {

    @Bean
    AvroSchemaMessageConverter orderAvroConverter() {
        AvroSchemaMessageConverter converter =
            new AvroSchemaMessageConverter(MimeType.valueOf("avro/bytes"));

        converter.setSchemaLocation(
            new ClassPathResource("schemas/OrderCreated.avsc")
        );

        return converter;
    }
}
~~~

This example illustrates the converter API of Spring Cloud Stream Schema Registry Client. Verify the package, dependencies, and constructors for your project's version. If the target type is `GenericRecord`, the application must provide the schema so the converter knows the record structure.

Configure bindings to use the matching content type:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      bindings:
        orders-out-0:
          destination: orders
          contentType: avro/bytes
        inventory-in-0:
          destination: orders
          group: inventory
          contentType: avro/bytes
~~~

Here, the converter is registered with MIME type `avro/bytes`, so bindings must specify a content type matching the converter. If using the converter's default MIME type, set the content type to match that MIME type.

### Using SpecificRecord

With `SpecificRecord`, Java classes are usually generated from Avro schemas during build time. The producer creates an instance of the generated class, and the converter uses the schema embedded in the class to serialize. The consumer uses the corresponding class or a configured reader schema to deserialize.

Example usage at the function layer:

~~~java
@Bean
Consumer<OrderCreated> inventory() {
    return event -> {
        System.out.println(
            "Order " + event.getOrderId()
        );
    };
}
~~~

In this example, `OrderCreated` is a Java class generated from an Avro schema. Actual getter names depend on Avro code generation and naming conventions.

### Using GenericRecord

`GenericRecord` is useful when an application processes many schema types or wants to avoid generating a separate class per record. However, the converter needs to know the schema when reading and writing. Do not assume that merely declaring the type `GenericRecord` is enough for the framework to infer the structure.

With dynamic data, applications should manage schemas explicitly, check fields before reading, and handle optional fields or fields absent in the current schema version.

## 4. Using Spring Cloud Stream's Schema Registry

When an application has a `SchemaRegistryClient` in the Application Context, Spring Cloud Stream can auto-configure an Avro message converter for schema management. This mechanism lets producers register schemas and consumers look up writer schemas based on message metadata.

On the producer side, configure the output binding with a content type like `application/*+avro` to trigger the schema-registry-backed converter:

~~~yaml
spring:
  cloud:
    stream:
      schemaRegistryClient:
        endpoint: http://localhost:8990
      bindings:
        orders-out-0:
          destination: orders
          contentType: application/*+avro
~~~

When sending a message, the converter derives the schema from the payload type. If the schema does not exist for the corresponding subject, the converter registers it and receives version metadata; if it already exists, the converter uses the registered version. The content type metadata carries the subject and version so consumers can look up the writer schema.

An example generated content type looks like:

~~~text
application/vnd.order-created.v2+avro
~~~

In this example, `order-created` is the subject and `v2` is an illustrative version. The actual subject name depends on the subject naming strategy and payload type.

Upon receiving a message, the converter reads schema info from the content type, fetches the writer schema from the registry, and uses Avro schema resolution to convert data into the reader schema used by the consumer.

### Common Schema Registry Properties

| Property | Meaning |
|---|---|
| `spring.cloud.stream.schemaRegistryClient.endpoint` | Schema registry server URL |
| `spring.cloud.stream.schema.avro.dynamicSchemaGenerationEnabled` | Allows deriving schemas from POJOs via reflection when needed |
| `spring.cloud.stream.schema.avro.readerSchema` | Local schema used as the reader schema when overriding lookup |
| `spring.cloud.stream.schema.avro.prefix` | Prefix used in the content type carrying subject/version, if supported by the version |

Names and locations of certain properties may differ across Spring Cloud Stream or Schema Registry module versions. Cross-check against the documentation for your release train. For POJOs that are neither Avro `SpecificRecord` nor `GenericRecord`, dynamic schema generation must be enabled if you want the converter to infer schemas via reflection.

The schema registry client typically caches lookup results to reduce server calls. In production, ensure the registry has adequate availability, the endpoint is secured, and producers have schema registration permissions consistent with organizational policies.

## 5. Native Avro Serde with the Kafka Binder

Kafka does not have a schema registry built into the broker. A common solution is using Confluent's Kafka Avro Serializer/Deserializer alongside Confluent Schema Registry. Other registries or serializers can be used as long as all producers and consumers agree on the wire format.

When using native Serde, the Kafka client performs serialization/deserialization. The output binding must enable native encoding; configure the Kafka producer to use the Avro serializer. The consumer uses a compatible Avro deserializer and configures the target data type.

The example below illustrates configuring Confluent Avro Serde per binding:

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
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
                value.serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
                schema.registry.url: http://localhost:8081
          inventory-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
                specific.avro.reader: true
                schema.registry.url: http://localhost:8081
~~~

Key points to note:

- `useNativeEncoding: true` tells the producer to use Kafka's native serializer.
- `KafkaAvroSerializer` serializes values in Avro and registers/looks up schemas via Confluent Schema Registry.
- `KafkaAvroDeserializer` uses the schema ID in the wire format to fetch the writer schema and decode.
- `specific.avro.reader: true` instructs the deserializer to return an Avro `SpecificRecord` class when the application uses schema-generated classes.
- If using `GenericRecord`, configure the deserializer in generic mode according to the library version.

With the Kafka binder, the Kafka client performs deserialization before the payload reaches the binder. Consequently, some versions/scenarios do not require explicitly setting `useNativeDecoding`; verify the binder documentation and actual consumer configuration. Crucially, the value deserializer must return a type compatible with the function signature.

### Confluent Wire Format Differs from Raw Avro Bytes

Confluent Avro Serializer typically wraps payloads in its own wire format consisting of a magic byte, schema ID, and Avro data. A plain Avro converter or a consumer reading raw Avro bytes will not automatically understand this format.

Do not use Confluent `KafkaAvroDeserializer` to read payloads created by a different Avro `MessageConverter` unless both sides share the same wire format. Similarly, do not use Spring Cloud Stream's Avro converter to decode Confluent payloads just because both use Avro.

## 6. Native Avro Schema with the Pulsar Binder

Pulsar supports schemas at the topic and client level. The Pulsar binder can use native encoding/decoding to delegate serialization to the Pulsar client. For Avro, configure the schema type and message type for producer and consumer.

Example binding configuration:

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
    pulsar:
      bindings:
        orders-out-0:
          producer:
            schema-type: AVRO
            message-type: com.example.events.OrderCreated
        inventory-in-0:
          consumer:
            schema-type: AVRO
            message-type: com.example.events.OrderCreated
~~~

In this example:

- `use-native-encoding` and `use-native-decoding` enable native serialization in both directions.
- `schema-type: AVRO` selects Pulsar's Avro schema.
- `message-type` informs the binder of the source/target Java type to pair with the schema.

The `OrderCreated` type must be compatible with a schema the Pulsar client can handle. Exact configuration and class support depend on the Spring Cloud Stream Pulsar binder and Spring for Apache Pulsar versions. If messages have both keys and values with distinct types, the binder may provide dedicated properties to declare key/value types.

Pulsar schemas are managed per topic and can enforce broker compatibility policies. When a producer sends a new schema, Pulsar can validate it against the topic's policy. Verify schema type, schema version, and compatibility policy in a test environment before deployment.

Do not apply Confluent `schema.registry.url` or Kafka Avro serializer settings to Pulsar. These are two distinct schema/Serde ecosystems.

## 7. Avro with the RabbitMQ Binder

RabbitMQ transmits message bodies as bytes and supports AMQP properties and headers. RabbitMQ does not natively enforce a shared Avro schema registry across messages. Therefore, applications usually use an Avro `MessageConverter` or a converter/serializer integrated with Spring AMQP to produce Avro bodies.

One approach is using Spring Cloud Stream's Avro converter with a fixed schema or schema registry. On the RabbitMQ side, the body carries Avro bytes; metadata such as content type or schema version must be passed via AMQP properties/headers per the converter's contract.

When both producer and consumer use Spring Cloud Stream's Avro `MessageConverter`, both sides must align on MIME type, schema reference mechanism, and converter setup. When the consumer is a non-Spring application, explicitly document how to obtain the writer schema: fixed schema, registry subject/version, or metadata placed in the message.

There is no Kafka-style `value.serializer` configuration for RabbitMQ. If custom native serialization is needed, configure a message converter or serializer supported by your Rabbit binder / Spring AMQP version. Do not assume RabbitMQ automatically knows how to decode Avro just because a payload carries MIME type `application/avro`.

## 8. Comparing Integration Approaches by Binder

| Binder | Avro Integration Approach | Schema Reference | What Must Be Aligned |
|---|---|---|---|
| Kafka | Avro MessageConverter or Kafka Avro Serde | Spring Schema Registry or schema ID in Serde wire format | Serializer/deserializer, registry, subject, wire format, and reader type |
| Pulsar | MessageConverter or native Pulsar schema | Metadata/schema version managed by Pulsar | Schema type, message type, topic schema, and compatibility policy |
| RabbitMQ | Avro MessageConverter or Spring AMQP converter/serializer | Fixed schema, registry, or application-defined metadata | Body bytes, content type, schema reference, and AMQP properties |

Do not mix two wire formats merely because both use Avro. Producers and consumers must align on both the schema and how the schema reference is packaged. The fact that two payloads are both Avro does not mean they are mutually readable.

## 9. Managing Schema Evolution and Compatibility

Avro supports schema resolution between writer schema and reader schema. However, compatibility guarantees depend on deployment order and registry/broker policies.

Three common concepts:

- **Backward compatibility**: consumers using the new schema can read data written with the old schema.
- **Forward compatibility**: consumers using the old schema can read data written with the new schema.
- **Full compatibility**: satisfies both backward and forward according to registry rules.

Common schema changes:

| Schema Change | Impact to Evaluate |
|---|---|
| Adding a new field with a default | Generally supports new consumers reading old messages because the reader has a default value for the missing field |
| Adding a new field without a default | New consumers may fail to read old messages because the writer schema does not provide the required field |
| Removing a field | Old consumers may need a default if the new writer stops writing a field required by the old reader |
| Renaming a field | May require an alias or migration strategy; direct renaming easily causes readers to miss the field |
| Changing a data type | Only specific promotions are supported by Avro; verify specific rules |
| Adding an enum value | Old consumers may not recognize the new symbol unless an appropriate default exists |
| Changing namespace or record name | Can affect schema identity and how registries partition subjects |

Do not check the new schema solely against the immediately preceding version. Brokers may still retain messages written across several earlier versions. If retention is long or consumers can replay, ensure the current reader can decode all data still within the supported range.

### Safe Schema Change Workflow

1. Identify which schema versions producers and consumers are currently running.
2. Choose a compatibility policy matching the rollout strategy.
3. Add new fields compatibly, usually with defaults.
4. Register the new schema in a test environment.
5. Verify the registry/broker accepts the schema under the policy.
6. Test new consumers reading old data.
7. Test old consumers reading new data if forward compatibility is required.
8. Deploy producers/consumers in the appropriate order.
9. Monitor serialization/deserialization errors after rollout.
10. Remove old fields only when no consumers or retained messages depend on them.

A schema registry helps catch incompatible changes before release, but it does not replace integration testing and multi-version rollout planning.

## 10. Testing Avro MessageConverter and Native Serde

Test across multiple layers to isolate schema bugs from binder issues.

### Schema and Record Unit Tests

Verify:
- Required fields have values.
- Union fields and defaults are handled correctly.
- Data types and logical types map accurately.
- Generated `SpecificRecord` matches the source schema.
- `GenericRecord` usage does not access missing fields without checking.

### Round-Trip Serialization

For each serializer/deserializer:
1. Create a sample record.
2. Serialize into bytes.
3. Deserialize using the expected writer schema and reader schema.
4. Compare field values, defaults, and logical types.
5. Attempt reading messages using schemas from before and after the change.

### MessageConverter Tests

If using an Avro `MessageConverter`:
- Verify the content type activates the expected converter.
- Verify the converter locates the fixed schema or schema registry.
- Verify subject/version are propagated and looked up accurately.
- Verify the reader schema is applied on message receipt.
- Test behavior when the registry is unavailable or a schema does not exist.

### Native Serde Integration Tests

With Kafka:
- Use the actual Kafka Avro Serializer/Deserializer and corresponding Schema Registry.
- Verify schema IDs and wire format on the topic.
- Verify `SpecificRecord` or `GenericRecord` types match expectations.
- Verify producers/consumers share the same subject strategy and compatibility policy.

With Pulsar:
- Verify the topic receives the expected `AVRO` schema type.
- Verify message type and schema version.
- Verify consumers decode messages written by previous producer versions.

With RabbitMQ:
- Verify body bytes, content type, schema reference, and AMQP properties.
- Read messages with a compatible converter.
- Verify non-Spring consumers can decode according to the contract documentation.

Spring Cloud Stream's Test Binder can test functions and bindings at the framework level, but it does not replace broker integration tests for a schema registry, native Serdes, or specific wire formats.

## 11. Common Avro Integration Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Converter not found | Mismatched MIME type or missing Avro converter module | Check dependencies and content type |
| `GenericRecord` fails to serialize | Converter was not supplied a schema | Configure a fixed schema or schema registry |
| Schema registry rejects registration | Schema violates compatibility policy | Inspect field changes, defaults, aliases, and policy |
| Consumer cannot find writer schema | Missing schema reference or wrong registry endpoint | Check content type/schema ID and endpoint |
| Producer succeeds but consumer fails | Incompatible writer schema and reader schema | Check schema resolution and defaults |
| Kafka reports deserializer error | Wrong Serde or mismatched wire format | Align Kafka serializer/deserializer and registry |
| Kafka receives bytes unreadable by converter | Confluent wire format differs from raw Avro bytes | Use the matching deserializer or standardize on the same converter |
| Pulsar rejects schema | Mismatched schema type/message type or policy rejection | Check binding schema config and topic policy |
| RabbitMQ consumer cannot read body | Converter or MIME type differs from producer | Align converter, content type, and schema reference |
| New consumer cannot read old messages | Reader schema lacks defaults or old schema is no longer retrievable | Check schema retention and compatibility |
| Payload type changes after rollout | Generated classes, schemas, or serializers are out of sync | Run compatibility tests and deploy classes/schemas together |

When diagnosing, inspect step by step: the Java payload, schema used during serialization, actual bytes, schema reference, writer schema, reader schema, and the object type expected by the function. Do not rely solely on a "send success" log to conclude the Avro contract works properly.

## 12. Practice Exercise: Publishing OrderCreated with Avro

Build an order event stream with a producer and a consumer:

1. Write `OrderCreated.avsc` with fields `eventId`, `orderId`, `totalMinorUnits`, `currency`, and `source` with a default.
2. Generate a Java `SpecificRecord` class from the schema or construct a `GenericRecord` with an explicit schema.
3. Declare a producer function or service publishing `OrderCreated`.
4. Choose one of the two approaches: Avro `MessageConverter` with a schema registry, or native Serde per binder.
5. Configure the output binding destination `orders` and the corresponding content type or native encoding.
6. Configure the `inventory` consumer using an appropriate reader schema.
7. Send a sample message and verify the consumer receives the right fields.
8. Add a `salesChannel` field with a default in a new schema version.
9. Register the new schema or update the native schema per binder.
10. Test the new consumer reading old-version messages and the old consumer reading new messages according to your compatibility policy.
11. Try omitting the default on the new field in a test environment to observe compatibility errors.
12. Record the schema version, subject, serializer/converter, and application versions in the test results.

Practice checklist:

| Item | Result to Verify |
|---|---|
| Source schema | Valid, with stable namespace and record name |
| Producer type | `SpecificRecord` or `GenericRecord` matching schema |
| Serialization path | Chosen `MessageConverter` or native Serde |
| Schema reference | Subject/version or schema ID transmitted accurately |
| Consumer type | Compatible reader schema and Java type |
| Compatibility | All supported producer/consumer versions can read |
| Broker test | Payloads written and read properly on target broker |

Upon completion, you should be able to explain why Avro `MessageConverter` and native Serde can produce two different wire formats, why consumers need both writer schema and reader schema, and how to validate schema changes before deployment.

## Conclusion

Avro provides structured schemas and a schema resolution mechanism that help producers and consumers evolve contracts across versions. In Spring Cloud Stream, Avro `MessageConverter` lets the framework handle conversion and can integrate with `SchemaRegistryClient`; native Serde delegates serialization to the binder/broker client.

Kafka can use Kafka Avro Serializer/Deserializer with a schema registry; Pulsar can use native Avro schemas and message types; RabbitMQ usually needs an Avro converter or serializer at the application layer because AMQP only transports bodies and metadata. Whichever option you pick, producers and consumers must agree on wire format, schema references, and compatibility policies. Run round-trip tests with data across multiple versions before promoting a new schema to production.

## References

- [Spring Cloud Stream – Schema Registry and Avro Message Converters](https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html)
- [Spring Cloud Stream – Kafka Binder: Native Serializer and Deserializer](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring Cloud Stream – Pulsar Binder: Native Conversion with Pulsar Schema](https://docs.spring.io/spring-cloud-stream/docs/current-SNAPSHOT/reference/html/spring-cloud-stream-binder-pulsar.html)
- [Apache Avro – Specification](https://avro.apache.org/docs/)
