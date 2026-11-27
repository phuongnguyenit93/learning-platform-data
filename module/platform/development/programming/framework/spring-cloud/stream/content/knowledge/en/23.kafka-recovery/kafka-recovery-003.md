# DLT Serializers When Using Native Decoding

In the Spring Cloud Stream Kafka binder, a consumer can let the Kafka client decode keys and values using Kafka's native deserializers instead of Spring Cloud Stream's message conversion. This approach is commonly called **native decoding**. It fits when an application uses Avro, Protobuf, a custom JSON serializer, or another format for which the Kafka client already has a corresponding deserializer.

When processing a record fails after it was decoded successfully, the Kafka binder can route the failed record to a dead-letter topic (DLT). However, the payload at that point may be a Java object such as String or OrderCreated, whereas the DLT producer must convert that object into byte[] to write it back to Kafka. Therefore, the DLT serializer must be compatible with the key and value types that the consumer decoded.

This is the critical distinction: the **consumer's deserializer** determines the data type the application receives; the **DLT producer's serializer** determines how that data type is written to the error topic. The two configurations are related, but they live on opposite sides.

## 1. Data Flow When Native Decoding Is Enabled

Normally, Spring Cloud Stream can use message converters to translate payloads between byte[] and application types based on content type. When native decoding is enabled, the Kafka client performs the decoding step using the deserializer configured for the consumer.

~~~mermaid
flowchart TD
    A[Kafka record: key bytes + value bytes] --> B[Kafka consumer deserializer]
    B --> C[Native decoding]
    C --> D[Spring Cloud Stream consumer]
    D --> E{Processing succeeded?}
    E -->|Yes| F[Complete processing and commit per ack mode]
    E -->|No| G[Retry per consumer policy]
    G --> H{Attempts remaining?}
    H -->|Yes| D
    H -->|No| I[DLT producer]
    I --> J[Key serializer and value serializer]
    J --> K[Dead-letter topic]
~~~

For example, Kafka stores values as byte[] while the consumer uses StringDeserializer. When the record reaches the application, the payload is already a String. If processing fails and the binder sends the payload to the DLT, the DLT producer must know how to serialize a String. The DLT producer's default serializer expects byte[]; keeping the default when the payload is String can cause DLT sending to fail due to a type mismatch.

## 2. Distinguishing the Three Serialization Configurations

| Configuration | Role | Example |
|---|---|---|
| Consumer key/value deserializer | Decodes records from the source topic into the Java types received by the application. | StringDeserializer, KafkaAvroDeserializer, custom deserializer. |
| DLT key/value serializer | Encodes the failed key and payload when the binder sends to the DLT. | StringSerializer, KafkaAvroSerializer, custom serializer. |
| Spring message converter | Converts payloads between messages and application types when native decoding is not used. | JSON message converter or custom converter. |

Do not use the business producer's serializer to assume the DLT producer is configured correctly. The DLT producer has its own property group called **dlqProducerProperties**. Settings here only affect the producer sending dead-letter records for that binding.

In the Kafka binder configuration, the key paths are:

~~~text
spring.cloud.stream.kafka.bindings.<binding-name>.consumer.dlqProducerProperties.configuration.key.serializer
spring.cloud.stream.kafka.bindings.<binding-name>.consumer.dlqProducerProperties.configuration.value.serializer
~~~

In YAML, you can write this in kebab-case:

~~~yaml
dlq-producer-properties:
  configuration:
    key:
      serializer: ...
    value:
      serializer: ...
~~~

When using the Kafka properties map format, dotted keys directly are often clearer:

~~~yaml
dlq-producer-properties:
  configuration:
    key.serializer: org.apache.kafka.common.serialization.StringSerializer
    value.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

## 3. Conditions for the Kafka Binder to Send Records to the DLT

With the regular Kafka binder, the consumer needs an explicit group and DLQ enabled on the input binding. Anonymous consumers cannot use the binder's DLQ facility.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: processData
    stream:
      bindings:
        processData-in-0:
          destination: input-topic
          group: processing-service
      kafka:
        bindings:
          processData-in-0:
            consumer:
              enable-dlq: true
              dlq-name: input-topic-dlt
~~~

If dlq-name is omitted, the default name takes the form:

~~~text
error.<destination>.<group>
~~~

For example, with destination input-topic and group processing-service, the default name is error.input-topic.processing-service.

DLQ is enabled via the Kafka binder's extended properties under the binding's consumer. A group is required for the binder to identify the consumer group and dead-letter destination. In addition, the DLT topic must have a partition count compatible with how the binder routes failed records.

By default, the binder typically sends failed records to the same partition number as the source partition. If you change the DLT partition count, review the dlq-partitions setting and the corresponding DlqPartitionFunction mechanism. This lesson focuses on serializers; topic creation, write permissions, and partitioning must still be configured properly.

## 4. Simple Example: Consumer Receiving byte[]

By default, the Kafka binder expects the DLT payload to be byte[]. If the function receives byte[] and does not convert types before throwing an error, the default serializer can serialize this payload.

~~~java
@Bean
public Consumer<byte[]> processData() {
    return value -> {
        // Process business data.
        throw new IllegalStateException("Unable to process record");
    };
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: processData
    stream:
      bindings:
        processData-in-0:
          destination: input-topic
          group: processing-service
      kafka:
        bindings:
          processData-in-0:
            consumer:
              enable-dlq: true
              dlq-name: input-topic-dlt
~~~

In this example, the consumer receives byte[] and the default DLT producer also expects byte[]. Therefore, no separate value.serializer declaration is needed just to handle this payload type.

That does not mean every native decoding case can skip serializer configuration. If the deserializer turns the value into a String, Avro object, or another Java type, the default byte[] serializer is no longer suitable.

## 5. Example: Consumer Decodes String While DLT Defaults to byte[]

Suppose the source record has a string key and value. The consumer uses StringDeserializer for both:

~~~java
@Bean
public Consumer<String> processData() {
    return value -> {
        if (value.startsWith("invalid")) {
            throw new IllegalArgumentException(
                    "Invalid payload");
        }
        // Process valid payload.
    };
}
~~~

Native decoding and DLT configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: processData
    stream:
      bindings:
        processData-in-0:
          destination: input-topic
          group: processing-service
          consumer:
            use-native-decoding: true
      kafka:
        bindings:
          processData-in-0:
            consumer:
              enable-dlq: true
              dlq-name: input-topic-dlt
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.apache.kafka.common.serialization.StringDeserializer
              dlq-producer-properties:
                configuration:
                  key.serializer: org.apache.kafka.common.serialization.StringSerializer
                  value.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

Explanation:

1. The Kafka client uses StringDeserializer to decode the source record's key and value.
2. The consumer function receives the value as a String.
3. When the function throws an exception and retries are exhausted, the binder needs to send the record to input-topic-dlt.
4. The DLT producer uses StringSerializer to serialize the String key/value.
5. The failed record is written to the DLT according to the binder configuration.

Both serializers in dlq-producer-properties must match the decoded data types. If the key is not a String, replace key.serializer with the matching serializer. If the value is byte[], use ByteArraySerializer; if the value is an Avro SpecificRecord, use a compatible Avro serializer.

## 6. Why Must Both Key Serializer and Value Serializer Be Configured?

A Kafka record has two independent data parts: key and value. A consumer can decode them with two different deserializers. When resending a failed record, the DLT producer must re-encode both parts according to their current types.

Examples:

| Source data | Consumer deserializer | Type received by app | Matching DLT serializer |
|---|---|---|---|
| String key, String value | StringDeserializer for both | String / String | StringSerializer / StringSerializer |
| String key, byte[] value | StringDeserializer and ByteArrayDeserializer | String / byte[] | StringSerializer / ByteArraySerializer |
| Long key, String value | LongDeserializer and StringDeserializer | Long / String | LongSerializer / StringSerializer |
| UUID key, Avro SpecificRecord value | UUIDDeserializer and KafkaAvroDeserializer | UUID / SpecificRecord | UUIDSerializer and matching KafkaAvroSerializer |

If you only configure value.serializer while the key has also been decoded into a non-byte[] type, the DLT producer can still fail when serializing the key. Conversely, if the key is null or remains byte[], the corresponding serializer should reflect that type.

Do not choose serializers based solely on the declared type of Consumer<T>. The Consumer<T> signature only describes the value payload; the key is managed separately by the Kafka deserializer and might not appear in the function parameter. To determine the key type, inspect key.deserializer and how the source producer creates records.

## 7. Example with Avro or Custom Serializers

Native decoding is commonly chosen when an application uses formats with dedicated serializers/deserializers. For example, with Confluent Avro, the consumer can decode the value into a SpecificRecord:

~~~yaml
spring:
  cloud:
    function:
      definition: orderConsumer
    stream:
      bindings:
        orderConsumer-in-0:
          destination: orders
          group: order-projection
          consumer:
            use-native-decoding: true
      kafka:
        bindings:
          orderConsumer-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders-dlt
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
                schema.registry.url: http://schema-registry:8081
                specific.avro.reader: true
              dlq-producer-properties:
                configuration:
                  key.serializer: org.apache.kafka.common.serialization.StringSerializer
                  value.serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
                  schema.registry.url: http://schema-registry:8081
~~~

The consumer can declare its payload type as the SpecificRecord class generated from the schema:

~~~java
@Bean
public Consumer<OrderCreated> orderConsumer() {
    return event -> {
        if (event.getTotal() < 0) {
            throw new IllegalArgumentException(
                    "Invalid total amount");
        }
        // Update projection.
    };
}
~~~

The example above illustrates configuration principles and does not replace Confluent Schema Registry dependency and security requirements. Both the consumer deserializer and DLT producer serializer must use the appropriate registry, along with the required schema compatibility policy and access permissions.

If you use a custom serializer, the serializer class must implement Kafka Serializer for the exact decoded object type. For instance, if the deserializer returns OrderCreated, the DLT serializer must know how to encode OrderCreated. You cannot use StringSerializer for an OrderCreated object just because its JSON can be represented as a string; you need a serializer that explicitly performs that conversion.

## 8. Distinguishing Business Processing Errors from Deserialization Errors

These two error types occur at different stages and require different handling mechanisms.

### Errors After the Consumer Receives the Payload

Processing flow:

1. The Kafka deserializer decodes successfully.
2. The consumer receives the decoded payload.
3. Business logic throws an exception.
4. The binder applies the retry policy.
5. Once attempts are exhausted, the binder can send the record to the DLT.

This is the case handled by enable-dlq and dlq-producer-properties in the earlier examples. The DLT serializer must be compatible with the decoded key/value.

### Errors During Deserialization

If the deserializer throws an exception while the Kafka consumer is polling, the record may never be returned to the listener. Therefore, Spring Cloud Stream's regular DLQ mechanism cannot handle this error as a business error inside the function.

For that case, Spring for Apache Kafka provides **ErrorHandlingDeserializer**. It delegates to the actual deserializer; when decoding fails, it preserves the raw bytes and exception in headers so an error handler can process the record.

General flow:

~~~mermaid
flowchart TD
    A[Kafka poll] --> B[ErrorHandlingDeserializer]
    B --> C{Decoding succeeded?}
    C -->|Yes| D[Consumer function]
    C -->|No| E[Preserve raw bytes and exception]
    E --> F[CommonErrorHandler]
    F --> G[DeadLetterPublishingRecoverer]
    G --> H[DLT]
~~~

To handle deserialization errors, configure ErrorHandlingDeserializer and a corresponding error handler, typically via ListenerContainerCustomizer, DefaultErrorHandler, and DeadLetterPublishingRecoverer. The dead-letter publisher's serializer must be able to write raw bytes or whatever data types the recoverer passes to the producer.

Example wrapper deserializer configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: orderConsumer
    stream:
      bindings:
        orderConsumer-in-0:
          destination: orders
          group: order-projection
          consumer:
            use-native-decoding: true
      kafka:
        bindings:
          orderConsumer-in-0:
            consumer:
              configuration:
                key.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
                spring.deserializer.value.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
~~~

This is only the deserializer portion. To route deserialization failures to the DLT, the application must also configure CommonErrorHandler/DeadLetterPublishingRecoverer on the listener container and a producer template with serializers compatible with raw bytes or the actual key/value types. Do not treat the example above as a complete DLQ configuration.

Key points to remember:

- The Kafka binder's **dlq-producer-properties** addresses the serializer for the binder-managed DLQ path when message processing fails after the consumer receives the record.
- **ErrorHandlingDeserializer + DefaultErrorHandler + DeadLetterPublishingRecoverer** handles deserialization errors occurring before the listener receives the record.
- Both mechanisms can coexist in an application, but neither automatically replaces the other.

## 9. The DLT Does Not Necessarily Preserve Original Raw Bytes

When native decoding succeeds, the consumer has already converted byte[] into a Java object. When the DLT producer serializes that object, the result may not be byte-for-byte identical to the original record.

For example, a JSON deserializer may create an OrderCreated object; a JSON serializer might later reorder properties, normalize whitespace, or format numbers differently. The business data may be equivalent, while the byte stream is not necessarily identical.

If auditing requirements demand preserving exact original bytes:

- Consider receiving the payload as byte[] and decoding at the application layer.
- Or preserve the raw ConsumerRecord/byte[] through an appropriate adapter.
- For deserialization errors, use ErrorHandlingDeserializer to retain raw bytes in the error details.
- Define clearly whether the DLT should store decoded payloads, normalized payloads, or original raw bytes.

Do not assume that using a serializer of the same family as the deserializer will reproduce exact original bytes. Some formats add schema IDs, metadata, framing, or registry details during serialization.

## 10. Retrying Before Sending to the DLT

The DLT typically receives records after the consumer has attempted processing per its retry policy. Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processData-in-0:
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 5000
            back-off-multiplier: 2.0
~~~

With this configuration, the binder can try up to four times, including the initial attempt. If all attempts fail, the DLQ mechanism triggers provided enable-dlq is enabled and the binding has a valid group.

Retries do not fix serializer errors. If the DLT producer uses the wrong serializer type, sending to the DLT still fails after processing retries are exhausted. Therefore, verify separately:

1. Does the consumer deserializer produce the exact type the application expects?
2. Does the retry policy have appropriate attempt counts and error classification?
3. Does the DLT producer have serializers for the decoded key and value?
4. Does the DLT topic exist, with sufficient partitions and write permissions?
5. Does the DLT consumer have deserializers compatible with the DLT format?

## 11. How to Read Records Back from the DLT

A DLT is only useful when operators can read, investigate, and decide to replay records. The DLT consumer must know the key/value format written by the DLT producer.

If the DLT producer uses StringSerializer, the DLT consumer can use StringDeserializer. If the producer uses an Avro serializer, the DLT consumer needs an Avro deserializer and matching registry configuration. If the DLT holds raw byte[], the consumer can use ByteArrayDeserializer to archive or analyze payloads.

Example DLT consumer reading strings:

~~~java
@Bean
public Consumer<String> inspectFailedOrder() {
    return payload -> {
        log.warn("DLT payload: {}", payload);
        // Record error and forward to investigation workflow.
    };
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: inspectFailedOrder
    stream:
      bindings:
        inspectFailedOrder-in-0:
          destination: input-topic-dlt
          group: dlt-inspector
      kafka:
        bindings:
          inspectFailedOrder-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.apache.kafka.common.serialization.StringDeserializer
~~~

This example is for a DLT containing String keys/values. If the DLT uses a different serializer, substitute the matching deserializer. Do not reuse the same consumer config for every DLT if bindings have different payload types.

## 12. Testing DLT Serializers

Tests must run against a test Kafka broker because unit-testing RetryTemplate alone does not prove the DLT producer serializes properly.

### Basic Test with String

1. Create the source topic and DLT.
2. Start the consumer with native decoding and StringDeserializer.
3. Send a record with a String key and String value.
4. Make the function throw an exception to trigger retries.
5. After attempts are exhausted, read the record from the DLT.
6. Confirm key/value can be deserialized with StringDeserializer.
7. Inspect dead-letter headers such as x-original-topic, x-exception-message, and x-exception-stacktrace if provided by the binder version in use.

### Test Matrix

| Scenario | Configuration | Expected verification |
|---|---|---|
| Consumer byte[] | Native decoding with ByteArrayDeserializer or byte[] payload. | Default DLT producer serializes byte[] payload successfully. |
| Consumer String | StringDeserializer and StringSerializer for DLT value. | Failed record is written to DLT and read back as String. |
| String key | StringDeserializer and StringSerializer for DLT key. | Key causes no serialization error when routing to DLT. |
| Different key/value types | Separate deserializer and serializer for each type. | Both key and value are written correctly. |
| Mismatched serializer | Consumer returns String while DLT uses ByteArraySerializer. | Test catches type error when sending to DLT. |
| Avro SpecificRecord | Avro deserializer/serializer with shared registry. | Failed record is written and read back with valid schema. |
| Retries exhausted | Handler always throws an exception. | DLT receives the record after the configured attempt count. |
| Deserialization error | Malformed wire data with ErrorHandlingDeserializer. | CommonErrorHandler/DeadLetterPublishingRecoverer handles the pre-listener error path. |
| DLT consumer | Uses deserializer matching the DLT serializer. | Consumer reads key/value and error metadata. |
| DLT write permission | Consumer account lacks produce permission to DLT. | Permission error is detected via logs/metrics; record is not assumed saved. |

### What to Observe

- Serialization error logs from the Kafka DLT producer.
- Consumer retry count before routing to the DLT.
- Actual number of records written to the DLT.
- Key and value can be deserialized back with the DLT consumer configuration.
- Partition and offset of the record in the DLT.
- Dead-letter headers generated per binder version.
- Authorization errors, missing topic, or incompatible partitions.

Do not only verify that the consumer stops throwing exceptions. Read the actual record from the DLT to prove the serializer wrote data in the right format.

## 13. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Consumer processes fine but DLT publish fails | DLT producer still uses ByteArraySerializer while payload was decoded into String or an object. | Declare the corresponding value.serializer in dlq-producer-properties. |
| DLT sends value but key fails | Key was decoded into a non-byte[] type while key.serializer is incompatible. | Configure key.serializer to match key.deserializer. |
| ClassCastException when sending to DLT | Serializer receives the wrong object type. | Match actual key/value types with serializers. |
| DLT consumer cannot read record | Consumer-side DLT deserializer does not match the serializer used. | Align wire format and serializer/deserializer on both sides. |
| enable-dlq is set but no DLT appears | Anonymous consumer or missing valid group. | Set group on the input binding. |
| Deserialization exception stops application | Error occurs during poll before binder receives message for standard DLQ handling. | Use ErrorHandlingDeserializer and configure CommonErrorHandler/DeadLetterPublishingRecoverer. |
| DLT payload differs from original bytes | Consumer decoded into an object and serializer regenerated the wire representation. | Keep byte[]/raw record if exact original bytes must be preserved. |
| DLT producer cannot write topic | Missing permissions, topic does not exist, or incompatible partitions. | Check ACLs, topic provisioning, and partition selection. |
| Serializer configured only for value | Key still uses incompatible default serializer. | Configure both key.serializer and value.serializer when both undergo type conversion. |

When investigating, check where the error occurs: inside the function after receiving the payload, inside the deserializer during poll, or inside the DLT producer during serialization. These three locations have distinct error handlers and configurations.

## 14. Pre-Deployment Checklist

- [ ] Consumer binding has an explicit group.
- [ ] enable-dlq is enabled on the right Kafka input binding.
- [ ] dlq-name is explicitly chosen or the default name is confirmed.
- [ ] use-native-decoding is enabled on the binding if Kafka client decoding is desired.
- [ ] key.deserializer and value.deserializer reflect the exact source wire format.
- [ ] key.serializer and value.serializer in dlq-producer-properties are compatible with the decoded types.
- [ ] If value is byte[], confirmed the default serializer is appropriate.
- [ ] If using Avro/Protobuf/custom serializers, the DLT producer has matching dependencies and configuration.
- [ ] DLT consumer uses deserializers matching the written format.
- [ ] Distinguished application processing errors from deserialization errors.
- [ ] Deserialization error path includes ErrorHandlingDeserializer and a dedicated error handler if needed.
- [ ] Retries, DLT topic, partitions, ACLs, and retention have been tested.
- [ ] Integration tests read actual records back from the DLT.

When using native decoding, the Kafka client decodes key/value before the payload reaches the function. If business processing fails and the binder needs to send the record to the DLT, the DLT producer must serialize the decoded data types again. Configure **dlq-producer-properties.configuration.key.serializer** and **value.serializer** to match the consumer's deserializers; by default, the DLT producer expects byte[] payloads. Also distinguish post-payload processing errors from deserialization errors occurring during poll, as the latter require ErrorHandlingDeserializer and an appropriate error handler. Testing by reading records back from the DLT is the final confirmation that the right serializers were chosen.

## References

- [Spring Cloud Stream Kafka Binder — Retry and Dead Letter Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html)
- [Spring Cloud Stream Kafka Binder — Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream Kafka Binder — Handling Deserialization Errors with DLQ](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring for Apache Kafka — Serialization, Deserialization and Error Handling](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
