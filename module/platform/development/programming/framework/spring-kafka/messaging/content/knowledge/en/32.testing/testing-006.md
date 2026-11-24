# KafkaTestUtils.producerProps

## 1. What Is `producerProps()` Used For?

When testing a Kafka producer, each test needs to create a producer connected to the running test broker. Rewriting the full `bootstrap.servers`, serializer, buffer, and batch configuration for every test makes test code verbose and prone to drift.

Spring Kafka provides `KafkaTestUtils.producerProps()` in the `spring-kafka-test` artifact. This method creates a `Map<String, Object>` containing basic producer properties for sending records to a test broker.

Two common overloads:

```java
Map<String, Object> producerProps(EmbeddedKafkaBroker embeddedKafka);

Map<String, Object> producerProps(String brokers);
```

The overload taking `EmbeddedKafkaBroker` retrieves the broker address from `embeddedKafka.getBrokersAsString()` and delegates to the string-address overload. The `String` overload has been available since Spring Kafka 2.3.5 and fits tests using external brokers or Testcontainers where bootstrap servers are already available.

Key point to remember: `producerProps()` only builds configuration. It does not start a Kafka broker, create topics, instantiate a `KafkaProducer`, or send records. The broker and topics must be ready before creating the producer.

## 2. Adding the spring-kafka-test Dependency

`KafkaTestUtils` belongs to the package:

```java
import org.springframework.kafka.test.utils.KafkaTestUtils;
```

If using Spring Boot 4.x, the Spring Boot documentation recommends the Kafka test starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

For projects not using Spring Boot, or Boot projects managing Spring Kafka modules directly, add the `spring-kafka-test` artifact in `test` scope.

Maven:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

With Kotlin DSL and Spring Boot 4.x:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-kafka-test")
}
```

If the project uses Spring Boot dependency management, let the BOM manage compatible versions. If managing dependencies manually, pick `spring-kafka-test` from the same version line as `spring-kafka` and the Kafka client used by the application. Do not put test artifacts into production dependencies because test classes must not be present in the runtime application.

## 3. Combining with EmbeddedKafkaBroker

`producerProps(EmbeddedKafkaBroker)` is commonly used with `@EmbeddedKafka`. The annotation creates an embedded broker for the test context; Spring Kafka provides the `EmbeddedKafkaBroker` bean so tests can obtain the connection address.

JUnit Jupiter example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig
@DirtiesContext
@EmbeddedKafka(partitions = 1, topics = "orders")
class OrderProducerTests {

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Test
    void embeddedBrokerIsAvailable() {
        String brokers = embeddedKafka.getBrokersAsString();
        assertNotNull(brokers);
        assertFalse(brokers.isBlank());
    }
}
```

`@EmbeddedKafka` manages the broker lifecycle within the Spring test context scope. `partitions = 1` creates single-partition topics; `topics = "orders"` requests that the topic be created when the broker starts. `@DirtiesContext` closes the test context after the class and avoids race conditions where the embedded broker shuts down while another context is still using resources. In real tests, use dedicated topics per test or a naming convention so parallel tests do not read each other's records.

Spring Kafka 4.x runs the embedded broker in KRaft mode because Kafka 4.0 removed ZooKeeper. In older Spring Kafka lines, the embedded broker implementation and ZooKeeper/KRaft options depend on the version.

Once a test has `EmbeddedKafkaBroker`, there is no need to assemble ports manually or guess the broker address. Use this bean directly to build producer properties:

```java
Map<String, Object> producerProperties =
        KafkaTestUtils.producerProps(embeddedKafka);
```

## 4. Sending Records with KafkaProducer

The Javadoc describes the default producer properties as targeting an `<Integer, String>` producer. Therefore, this example directly uses `Integer` as the key and `String` as the value:

```java
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@Test
void sendsRecordToEmbeddedKafka() throws Exception {
    Map<String, Object> props = KafkaTestUtils.producerProps(embeddedKafka);

    try (KafkaProducer<Integer, String> producer = new KafkaProducer<>(props)) {
        ProducerRecord<Integer, String> record =
                new ProducerRecord<>("orders", 42, "ORDER_CREATED");

        RecordMetadata metadata = producer.send(record).get(10, TimeUnit.SECONDS);

        assertEquals("orders", metadata.topic());
        assertEquals(0, metadata.partition());
        assertTrue(metadata.offset() >= 0);
    }
}
```

`KafkaProducer` accepts the map returned by `producerProps()` directly. When sending, `send()` returns a `Future<RecordMetadata>`; calling `get()` in the test waits for broker acknowledgment instead of ending the test right after enqueuing the record in the local buffer.

`RecordMetadata` reports the topic, partition, and offset assigned to the record by the broker. With a single-partition topic, the expected partition is `0`. If the topic has multiple partitions and the record does not specify a partition, do not hard-code the partition in assertions; check the key/partitioner or simply verify the partition falls within the valid range.

`try-with-resources` guarantees the producer is closed even if assertions or sends fail. Closing the producer flushes pending requests and releases network threads, buffers, and sockets.

## 5. Properties Created by producerProps

In the current implementation, the overload accepting a broker string builds a map with the following values:

| Kafka Producer Property | Value | Meaning |
|---|---|---|
| `bootstrap.servers` | Passed-in broker address | Initial connection point for the producer to fetch cluster metadata |
| `batch.size` | `16384` | Default 16 KiB batch size per partition |
| `linger.ms` | `1` | Producer may wait up to about 1 ms to batch records before sending |
| `buffer.memory` | `33554432` | 32 MiB producer buffer memory |
| `key.serializer` | `IntegerSerializer.class` | Converts `Integer` keys into byte[] |
| `value.serializer` | `StringSerializer.class` | Converts `String` values into byte[] |

`batch.size` and `buffer.memory` are represented as numeric strings in the map; `linger.ms` is set as an integer. The Kafka client accepts configuration values in the appropriate representation for each property.

These properties are a convenience set for writing basic producer tests. The method does not configure every producer option. Properties absent from the map use Kafka client defaults or come from additional configuration supplied by the test.

In particular, do not interpret `batch.size`, `linger.ms`, or `buffer.memory` here as production benchmark tuning. These are convenient test values; real applications must configure them according to throughput, latency, message size, and resources.

You can verify the helper's contract with a small unit test:

```java
@Test
void producerPropsContainsExpectedDefaults() {
    Map<String, Object> props = KafkaTestUtils.producerProps(embeddedKafka);

    assertEquals(embeddedKafka.getBrokersAsString(),
            props.get(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG));
    assertEquals("16384", props.get(ProducerConfig.BATCH_SIZE_CONFIG));
    assertEquals(1, props.get(ProducerConfig.LINGER_MS_CONFIG));
    assertEquals("33554432", props.get(ProducerConfig.BUFFER_MEMORY_CONFIG));
    assertEquals(IntegerSerializer.class,
            props.get(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG));
    assertEquals(StringSerializer.class,
            props.get(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG));
}
```

This is a contract test of the helper for the active implementation. If upgrading Spring Kafka, default values might change; this test helps the team detect configuration changes and deliberately decide whether test setups need updating.

## 6. Why Are the Default Types Integer and String?

`KafkaTestUtils.producerProps()` is built for the `<Integer, String>` type pair:

- Key serializer is `IntegerSerializer`.
- Value serializer is `StringSerializer`.

Thus the following producer is directly compatible:

```java
KafkaProducer<Integer, String> producer =
        new KafkaProducer<>(KafkaTestUtils.producerProps(embeddedKafka));
```

If generic types do not match the serializers, the test may fail when sending. For example, using a `String` key while keeping `IntegerSerializer` can cause a `ClassCastException` or serialization error.

Java generic types do not automatically alter the Kafka serializer. Declaring `KafkaProducer<String, OrderCreated>` only helps the compiler check types; the Kafka producer still needs the matching serializers in its configuration.

## 7. Overriding Serializers for Custom Data Types

The returned map is mutable. When needing a `String` key and a JSON object value, copy or update the map and replace both serializers:

```java
import org.springframework.kafka.support.serializer.JacksonJsonSerializer;

Map<String, Object> props = new HashMap<>(
        KafkaTestUtils.producerProps(embeddedKafka));

props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JacksonJsonSerializer.class);

try (KafkaProducer<String, OrderCreated> producer = new KafkaProducer<>(props)) {
    OrderCreated event = new OrderCreated("order-42", "CREATED");
    RecordMetadata metadata = producer.send(
            new ProducerRecord<>("orders", event.orderId(), event))
            .get(10, TimeUnit.SECONDS);

    assertEquals("orders", metadata.topic());
}
```

`JacksonJsonSerializer` belongs to `org.springframework.kafka.support.serializer`. In Spring Kafka 2.x/3.x using Jackson 2, the familiar serializer is `JsonSerializer`; starting in Spring Kafka 4.0, `JsonSerializer` was deprecated in favor of `JacksonJsonSerializer` for Jackson 3. If using another serializer, substitute the corresponding class and ensure test consumers use a compatible deserializer.

Creating `new HashMap<>(...)` makes it clear that the test owns its own configuration map for customization. You can call `put()` directly on the returned map since the implementation returns a new `HashMap`, but copying the map is helpful when wanting to keep the base config intact or reuse it across multiple different producers.

## 8. Overriding Other Producer Properties

Besides serializers, tests can add or replace other properties. Example:

```java
Map<String, Object> props = new HashMap<>(
        KafkaTestUtils.producerProps(embeddedKafka));

props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.CLIENT_ID_CONFIG, "orders-producer-test");
props.put(ProducerConfig.LINGER_MS_CONFIG, 0);
```

`Map.put(key, value)` overwrites the old value if the key already exists. In the example, `linger.ms` changes from `1` to `0`; `acks` and `client.id` are added.

Only add properties with a specific testing purpose. For example, `client.id` helps identify the producer in broker logs; `acks` may be needed when testing write-acknowledgment semantics. Avoid copying the entire production configuration into tests if a test only needs to verify serialization and record sending.

If a test needs to verify a property, assert directly against the map before creating the producer:

```java
assertEquals("all", props.get(ProducerConfig.ACKS_CONFIG));
assertEquals("orders-producer-test", props.get(ProducerConfig.CLIENT_ID_CONFIG));
```

Do not depend on the iteration order of entries in the map; `Map` does not guarantee iteration order.

## 9. Using producerProps(String brokers)

When not using `EmbeddedKafkaBroker`, the overload taking a bootstrap servers string still creates the same base property set:

```java
String bootstrapServers = "localhost:9092";
Map<String, Object> props = KafkaTestUtils.producerProps(bootstrapServers);

try (KafkaProducer<Integer, String> producer = new KafkaProducer<>(props)) {
    producer.send(new ProducerRecord<>("orders", 7, "ORDER_CREATED"))
            .get(10, TimeUnit.SECONDS);
}
```

This is how it is used with brokers running outside the test process, such as Kafka Testcontainers or a separate Kafka test cluster. `producerProps(String)` does not check whether the broker is actually ready; the address must be valid and the broker must be reachable.

If the broker requires SASL, TLS, or credentials, the base map does not automatically add security properties. Tests must add `security.protocol`, SASL/SSL config, truststore, and credentials via appropriate test secrets. Do not put real passwords or keytabs into source control.

## 10. Using producerProps with KafkaTemplate

Spring Kafka applications typically send records using `KafkaTemplate`, so integration tests can create a `DefaultKafkaProducerFactory` from `KafkaTestUtils`'s map and instantiate the template.

Example with a `String` key and `OrderCreated` value:

```java
import org.springframework.kafka.support.serializer.JacksonJsonSerializer;

@Test
void sendsEventWithKafkaTemplate() throws Exception {
    Map<String, Object> props = new HashMap<>(
            KafkaTestUtils.producerProps(embeddedKafka));
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JacksonJsonSerializer.class);

    DefaultKafkaProducerFactory<String, OrderCreated> producerFactory =
            new DefaultKafkaProducerFactory<>(props);
    KafkaTemplate<String, OrderCreated> kafkaTemplate =
            new KafkaTemplate<>(producerFactory);

    try {
        OrderCreated event = new OrderCreated("order-100", "CREATED");
        SendResult<String, OrderCreated> result = kafkaTemplate
                .send("orders", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

        assertEquals("orders", result.getRecordMetadata().topic());
    } finally {
        producerFactory.destroy();
    }
}
```

`KafkaTemplate` does not replace the serializer. The template passes keys/values down to the producer factory; the serializers configured in the map still determine how data is converted to bytes.

In tests using a real Spring context, it is usually better to inject the `KafkaTemplate` configured in the application context and let Spring manage its lifecycle. The manual factory/template example above fits when a test wants to isolate producer config; you must destroy the factory after the test to close the cached producer.

## 11. Sending Asynchronously and Waiting for Results Properly

The Kafka producer sends asynchronously. `send()` returns a `Future<RecordMetadata>` (or the corresponding API depending on the Kafka client version). In tests, there are three common approaches:

**Awaiting the Future:**

```java
RecordMetadata metadata = producer.send(record).get(10, TimeUnit.SECONDS);
```

This is simple and allows asserting metadata. The timeout ensures the test terminates within a bound if the broker does not respond.

**Calling flush:**

```java
producer.send(record);
producer.flush();
```

`flush()` waits for previously sent records to finish processing on the producer side, but does not return `RecordMetadata` for assertions. When needing to verify partition/offset or catch specific send errors, keep the Future and call `get()`.

**Using a callback:**

```java
CompletableFuture<RecordMetadata> completion = new CompletableFuture<>();

producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        completion.completeExceptionally(exception);
    } else {
        completion.complete(metadata);
    }
});

RecordMetadata metadata = completion.get(10, TimeUnit.SECONDS);
```

Callbacks are useful when a test needs to verify asynchronous success and failure branches. Do not use a callback just to add complexity if a simple Future already meets the need.

Avoid fixed `Thread.sleep()` calls to wait for records to be sent. Waiting on a Future or using consumer polling with a timeout keeps tests synchronized to real events and less flaky.

## 12. Verifying the Record Actually Reached the Broker

A `Future<RecordMetadata>` completing successfully proves the broker acknowledged the send per producer configuration, but if the test needs to verify the payload a consumer reads, combine it with a consumer test.

Example illustrating the producer and consumer parts independently:

```java
Map<String, Object> producerProps =
        KafkaTestUtils.producerProps(embeddedKafka);

try (KafkaProducer<Integer, String> producer = new KafkaProducer<>(producerProps)) {
    producer.send(new ProducerRecord<>("orders", 9, "ORDER_CREATED"))
            .get(10, TimeUnit.SECONDS);
}

Map<String, Object> consumerProps =
        KafkaTestUtils.consumerProps(embeddedKafka, "orders-test-group", false);
consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, IntegerDeserializer.class);
consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);

try (KafkaConsumer<Integer, String> consumer = new KafkaConsumer<>(consumerProps)) {
    embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");
    ConsumerRecord<Integer, String> received =
            KafkaTestUtils.getSingleRecord(consumer, "orders", Duration.ofSeconds(10));

    assertEquals(9, received.key());
    assertEquals("ORDER_CREATED", received.value());
}
```

The consumer helper in this example uses the `consumerProps(EmbeddedKafkaBroker, String, boolean)` overload available since Spring Kafka 4.0. For older version lines, use the consumer properties overload supported in that version or configure the consumer map manually. This section only illustrates end-to-end verification; the focus of this lesson remains producer properties.

Pay attention to subscribe/assignment order: `consumeFromAnEmbeddedTopic()` assigns the consumer to the topic and by default seeks to the beginning of partitions in the embedded broker. If a test needs to read only new records after a point in time, pick an overload with the appropriate `seekToEnd` flag or use a dedicated topic for the test.

## 13. Using with Testcontainers or External Brokers

If a test uses Testcontainers Kafka, obtain the bootstrap servers from the container and pass them to the string overload:

```java
String brokers = kafkaContainer.getBootstrapServers();
Map<String, Object> props = KafkaTestUtils.producerProps(brokers);

props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
```

This method does not depend on `EmbeddedKafkaBroker`; it only needs a bootstrap servers string. This is useful when the same test suite can run against either an embedded broker or a container broker.

If the container requires a security protocol or the test uses multiple brokers, add the matching properties and ensure topics are created. Do not assume `producerProps()` configures Testcontainers or starts a Kafka container automatically.

## 14. What producerProps Does Not Do

To avoid wrong expectations, distinguish this helper from other components:

| Component | Responsibility |
|---|---|
| `KafkaTestUtils.producerProps()` | Creates a basic test producer property map |
| `@EmbeddedKafka` / `EmbeddedKafkaBroker` | Starts and manages an embedded broker for tests |
| `KafkaProducer` | Sends records using the Kafka Java client |
| `DefaultKafkaProducerFactory` | Creates/manages producers for Spring Kafka |
| `KafkaTemplate` | Spring API for sending records |
| `ProducerRecord` | Describes the topic, partition/key/value/timestamp/headers of the outgoing record |
| `spring-kafka-test` | Provides test utilities and embedded broker support |

`producerProps()` does not:

- Create topics or select partitions for records.
- Create a producer or `KafkaTemplate`.
- Wait for the broker to become ready.
- Configure consumer groups or deserializers.
- Automatically configure JSON serializers for domain objects.
- Automatically enable TLS, SASL, Kerberos, or credentials.
- Guarantee producer transactions or verify exactly-once semantics.
- Automatically close producers created from the map.

Those responsibilities belong to the broker, producer factory, Kafka client properties, or the corresponding test code.

## 15. Considerations When Running Tests in Parallel

An embedded broker can be shared across multiple test classes via the Spring test context cache. This reduces broker startup overhead, but tests sharing topics can interfere with each other.

To avoid execution-order dependencies:

- Use a dedicated topic per test class or test case if tests run in parallel.
- Use separate consumer group IDs when testing offsets independently.
- Do not rely on the default starting offset if a topic may already contain records from an earlier test.
- Wait for send Futures to complete before consumer assertions.
- Close producers/consumers after tests.
- If sharing context and broker, do not delete topics or stop the broker while other tests are still using them.

If a test needs to verify producer retries, idempotence, or transactions, configure the relevant properties separately and design an appropriate broker setup. Do not infer transaction behavior solely from a basic producer map.

## 16. Common Errors

| Symptom | Common Cause | Solution |
|---|---|---|
| `SerializationException` or `ClassCastException` | Key/value generics do not match default `IntegerSerializer` and `StringSerializer` | Override key/value serializers according to actual data types |
| `No resolvable bootstrap urls` | Broker string is empty, malformed, or broker is not ready | Use `embeddedKafka.getBrokersAsString()` or real bootstrap servers |
| `TimeoutException` waiting on Future | Broker not ready, topic does not exist, network or ACL error | Check broker lifecycle, topics, logs, and timeouts |
| Producer sends successfully but consumer sees no record | Late consumer subscribe/assignment, offset reset, or group already has offsets | Use a separate topic, check assignment and seek strategy |
| Test passes on one machine but fails on another | Fixed port, broker lifecycle, or tests sharing topics | Use dynamic ports, `@EmbeddedKafka`, dedicated topics, and bounded timeouts |
| Record sent but test ends before ack | Did not wait for Future or flush | Call `get(timeout)` or flush as appropriate |
| Producer threads still running after test | Producer/factory not closed | Use try-with-resources or destroy the factory |
| JSON payload fails to deserialize | Replaced producer serializer only while consumer still uses StringDeserializer or mismatched type config | Configure compatible deserializer and check type/headers |
| Test broker requires SASL/TLS and rejects producer | Helper only builds basic producer properties, missing security properties | Add protocol, JAAS/SSL, and test credentials |
| Multiple tests read the wrong records | Shared topic and consumer group/offsets | Isolate topics/groups or intentionally reset offsets |

## 17. Workflow for Using producerProps in a Test

1. Add `spring-boot-starter-kafka-test` if using Spring Boot 4.x, or `spring-kafka-test` in `test` scope for plain Spring Kafka projects; align versions.
2. Start a broker with `@EmbeddedKafka` or retrieve bootstrap servers from another test broker.
3. Build the map using `KafkaTestUtils.producerProps(embeddedKafka)` or `producerProps(brokers)`.
4. Check whether the test's key/value types match the default `<Integer, String>` serializers.
5. If data types differ, override `KEY_SERIALIZER_CLASS_CONFIG` and `VALUE_SERIALIZER_CLASS_CONFIG`.
6. Add custom properties only when the test needs them, such as `client.id`, `acks`, or security config.
7. Create `KafkaProducer` or `ProducerFactory`/`KafkaTemplate` from the map.
8. Send the record and wait for the Future to complete with a timeout.
9. Assert metadata or use a consumer to verify the payload.
10. Close the producer/factory and keep test topics/groups independent to avoid cross-talk.

## 18. Summary

- `KafkaTestUtils.producerProps()` creates a `Map<String, Object>` to configure a test producer.
- The `EmbeddedKafkaBroker` overload reads bootstrap servers from the broker; the `String` overload has been available since Spring Kafka 2.3.5.
- The default property set targets an `<Integer, String>` producer with `IntegerSerializer` and `StringSerializer`.
- The map includes bootstrap servers, batch size, linger, buffer memory, and serializers; other properties use Kafka client defaults unless overridden by the test.
- The map can be used with `KafkaProducer`, `DefaultKafkaProducerFactory`, or `KafkaTemplate`.
- When using key/value types different from the defaults, replace the matching serializers; generic types do not configure serializers automatically.
- Wait on send Futures with a timeout for deterministic test results; close the producer/factory after the test.
- The helper does not start a broker, create topics, enable security, or instantiate a producer.
- Use dedicated topics/groups and control assignment/offsets to avoid inter-test dependencies.

`KafkaTestUtils.producerProps()` reduces repetitive configuration when writing producer tests. Once you understand the properties the helper provides, its default data types, and how to override serializers, you can focus on verifying your Spring Kafka application's record-sending behavior while keeping tests with clear lifecycles and stable outcomes.

## References

- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka API — KafkaTestUtils](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [Spring Kafka source — KafkaTestUtils.java](https://github.com/spring-projects/spring-kafka/blob/main/spring-kafka-test/src/main/java/org/springframework/kafka/test/utils/KafkaTestUtils.java)
