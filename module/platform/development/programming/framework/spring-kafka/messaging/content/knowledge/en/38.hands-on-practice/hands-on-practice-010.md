# Simulating Deserialization Failures

A Kafka consumer must convert record bytes into a data type understood by the listener. In Spring Kafka, `JsonDeserializer` typically converts JSON into a DTO. If the payload is truncated, JSON syntax is malformed, type metadata is wrong, or a field cannot be converted, deserialization can fail right during the consumer poll. At that point, the `@KafkaListener` method has not been called yet, so you cannot catch the exception with a `try/catch` inside the listener.

This hands-on lab creates a topic receiving `OrderCreated` events, configures `ErrorHandlingDeserializer` wrapping `JsonDeserializer`, intentionally sends a malformed JSON payload, and uses `DefaultErrorHandler` with `DeadLetterPublishingRecoverer` to route the record to a dead-letter topic (DLT). At the end, we read back from the DLT to verify that the original byte payload and error metadata remain intact for investigation.

## 1. Objectives and Lab Flow

Once completed, you will be able to:

- Distinguish deserialization failures from exceptions thrown inside a listener.
- Configure `ErrorHandlingDeserializer` and its delegate `JsonDeserializer`.
- Understand why the listener does not receive a DTO when the payload is invalid.
- Configure `DefaultErrorHandler` to recover from deserialization failures.
- Use `DeadLetterPublishingRecoverer` to send failed records to a DLT.
- Read the original byte payload and source headers from the DLT.

Processing flow:

```text
Producer sends JSON bytes
          |
          v
      orders-json
          |
          v
ErrorHandlingDeserializer
          |
          v
    JsonDeserializer
       /       \
  Valid JSON   Invalid JSON
      |            |
      v            v
OrderCreated   exception stored in headers
      |            |
      v            v
@KafkaListener  DefaultErrorHandler
                   |
                   v
          DeadLetterPublishingRecoverer
                   |
                   v
             orders-json.DLT
```

Valid records reach the listener. Undeserializable records are detected by the container via the headers added by `ErrorHandlingDeserializer`; the listener is not invoked for those records. The error handler forwards the record to the recoverer, which publishes it to the DLT.

## 2. Preparing Dependencies and Topics

The application needs Spring Kafka, plus `spring-kafka-test` if running the lab with Embedded Kafka. With Maven:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

If using Spring Boot dependency management, let the BOM manage compatible versions. Do not upgrade `spring-kafka-test` independently to a different version than the application's Spring Kafka version.

Create the source topic `orders-json` and the DLT topic `orders-json.DLT`. By default, the recoverer routes records from the source topic to a topic suffixed with `.DLT` and usually preserves the corresponding partition. Therefore, the DLT must have at least as many partitions as the source topic. This lab uses one partition per topic for simplicity.

With a real broker, create topics through infrastructure governance processes, configuring appropriate replication factors and ACLs. Do not rely on broker topic auto-creation in production.

## 3. Creating the DTO and Listener for Valid Events

Create a simple event DTO:

```java
package com.example.orders.events;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerId) {
}
```

The listener receives the DTO and records events for business processing:

```java
package com.example.orders.listener;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import com.example.orders.events.OrderCreated;

@Component
public class OrderListener {

    private final BlockingQueue<OrderCreated> received =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            topics = "orders-json",
            groupId = "orders-deserialize-lab",
            containerFactory = "ordersListenerFactory")
    public void listen(OrderCreated event) {
        received.add(event);
    }

    public BlockingQueue<OrderCreated> received() {
        return received;
    }
}
```

`BlockingQueue` is used here solely for observation in the lab. A real application should invoke a business service and only finish the listener after side effects are durably stored per design.

## 4. Configuring ErrorHandlingDeserializer

`ErrorHandlingDeserializer` is a wrapper that delegates to another deserializer. If the delegate deserializes successfully, the wrapper returns the object normally. If the delegate throws an exception, the wrapper stores the exception details and raw data in headers and returns null so the container can detect the failure.

Java configuration example:

```java
package com.example.orders.config;

import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import com.example.orders.events.OrderCreated;

@Configuration
@EnableKafka
public class OrdersConsumerConfiguration {

    @Bean
    ConsumerFactory<String, OrderCreated> ordersConsumerFactory(
            @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers) {

        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-deserialize-lab");
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                ErrorHandlingDeserializer.class);

        props.put(
                "spring.deserializer.value.delegate.class",
                JsonDeserializer.class);
        props.put(
                JsonDeserializer.VALUE_DEFAULT_TYPE,
                OrderCreated.class.getName());
        props.put(JsonDeserializer.TRUSTED_PACKAGES,
                "com.example.orders.events");
        props.put(JsonDeserializer.USE_TYPE_INFO_HEADERS, false);

        return new DefaultKafkaConsumerFactory<>(props);
    }
}
```

Key points to note:

- `VALUE_DESERIALIZER_CLASS_CONFIG` points to `ErrorHandlingDeserializer`, not directly to `JsonDeserializer`.
- `spring.deserializer.value.delegate.class` specifies `JsonDeserializer` as the value delegate.
- `spring.json.value.default.type` defines the default DTO to instantiate.
- `spring.json.trusted.packages` restricts packages allowed for deserialization when reading type metadata.
- `spring.json.use.type.headers=false` tells the consumer to use the default type instead of relying on a class name in headers.

In Spring Boot YAML, the equivalent configuration can be written as:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-deserialize-lab
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
        spring.json.use.type.headers: false
```

Do not set trusted packages to `*` in production without an evaluated security reason. Only allow the contract packages the consumer needs to deserialize.

## 5. Configuring a Producer That Can Send Both DTOs and byte[]

We need to send two kinds of values to the same topic:

- Valid `OrderCreated` objects to test the normal flow.
- `byte[]` containing malformed JSON to simulate deserialization failure.

The recoverer also needs to publish the original raw bytes to the DLT. Therefore, the producer factory uses `DelegatingByTypeSerializer`: `byte[]` goes through `ByteArraySerializer`, while regular objects go through `JsonSerializer`.

```java
package com.example.orders.config;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.Serializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Configuration
public class OrdersProducerConfiguration {

    @Bean
    ProducerFactory<String, Object> ordersProducerFactory(
            @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers) {

        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ProducerConfig.ACKS_CONFIG, "all");

        Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
        delegates.put(byte[].class, new ByteArraySerializer());
        delegates.put(Object.class, new JsonSerializer<>());

        return new DefaultKafkaProducerFactory<>(
                props,
                new StringSerializer(),
                new DelegatingByTypeSerializer(delegates, true));
    }

    @Bean
    KafkaTemplate<String, Object> ordersKafkaTemplate(
            ProducerFactory<String, Object> ordersProducerFactory) {
        return new KafkaTemplate<>(ordersProducerFactory);
    }
}
```

Place these `@Bean` methods inside a `@Configuration` class. The serializer is selected by the runtime type of the value. Ordering the map with `byte[].class` before `Object.class` ensures raw byte data is handled by the byte serializer.

If the application does not need to send DTOs from this template, you can use a dedicated producer factory that only serializes `byte[]`. In this lab, a single template supporting both types allows the recoverer to publish the original payload when deserialization fails.

## 6. Configuring DefaultErrorHandler and the DLT Recoverer

Create a `DeadLetterPublishingRecoverer` using the `KafkaTemplate` above, then attach it to `DefaultErrorHandler`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;
import com.example.orders.events.OrderCreated;

@Configuration
public class OrdersListenerConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<String, Object> ordersKafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(ordersKafkaTemplate);
        // Do not retry deserialization errors; recover straight to the DLT.
        return new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(0L, 0L));
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> ordersConsumerFactory,
            DefaultErrorHandler ordersErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(ordersConsumerFactory);
        factory.setCommonErrorHandler(ordersErrorHandler);
        return factory;
    }
}
```

`DeserializationException` is treated by `DefaultErrorHandler` as a fatal/non-retryable error under the default classification in modern Spring Kafka versions. `FixedBackOff(0L, 0L)` also sets the retry count to 0, so the record is handed to the recoverer immediately after the first failure. This configuration makes the lab's intent clear: malformed JSON cannot turn into valid JSON simply by redelivering the same payload.

By default, the recoverer routes `orders-json` to `orders-json.DLT` and preserves the matching partition. Pre-create the DLT topic with a partition count equal to or greater than the source topic. If changing the DLT naming rule, supply a custom destination resolver to `DeadLetterPublishingRecoverer`.

## 7. Why Does the Listener Never Receive the Failing Record?

For a listener expecting `OrderCreated`, Spring Kafka must deserialize the value before invoking the listener method. If `JsonDeserializer` throws an exception without `ErrorHandlingDeserializer`, the error occurs during `poll()` and the container has no valid business object to pass to the listener.

When wrapped with `ErrorHandlingDeserializer`:

1. The delegate `JsonDeserializer` attempts to convert the JSON bytes into `OrderCreated`.
2. If it succeeds, the object is passed to the listener.
3. If it fails, the wrapper stores the exception and original bytes in the record's headers and returns a null value.
4. The container detects the deserialization failure header and routes the exception to `CommonErrorHandler`.
5. `DefaultErrorHandler` invokes the recoverer; `DeadLetterPublishingRecoverer` extracts the original bytes from the error metadata and publishes them to the DLT.

Because the failure happens before the listener, do not put `try/catch` inside `onOrder()` expecting to catch JSON errors. The listener never runs when deserialization fails.

## 8. Sending One Valid Record and One Malformed JSON Record

After the application runs and the listener container has started, send a valid record:

```java
OrderCreated valid = new OrderCreated(
        "event-100", "order-100", "customer-7");

ordersKafkaTemplate.send("orders-json", "order-100", valid);
```

The listener receives `OrderCreated` and puts it into the observation queue. Next, send a syntactically invalid payload as `byte[]`:

```java
import java.nio.charset.StandardCharsets;

byte[] invalidJson = "{\"eventId\":\"bad-1\",\"orderId\":"
        .getBytes(StandardCharsets.UTF_8);

ordersKafkaTemplate.send("orders-json", "bad-order-1", invalidJson);
```

This payload is truncated mid-property and is not complete JSON. The producer can still send it successfully because the producer only serializes `byte[]`; it does not know whether the consumer expects `OrderCreated` or whether the payload is valid JSON.

To observe failures deterministically, wait on the `send()` future in tests or register a callback in the application. Broker acknowledgment of the publish only proves the record was written according to producer settings, not that the consumer deserialized it successfully.

## 9. Reading the Original Record from the DLT

You can use a separate Kafka consumer with `ByteArrayDeserializer` to inspect the DLT. Example:

```java
import java.time.Duration;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.serialization.ByteArrayDeserializer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.test.utils.KafkaTestUtils;

Map<String, Object> dltProps = KafkaTestUtils.consumerProps(
        "orders-dlt-inspector", "false", embeddedKafka);
dltProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

try (Consumer<String, byte[]> dltConsumer =
        new DefaultKafkaConsumerFactory<String, byte[]>(
                dltProps,
                new StringDeserializer(),
                new ByteArrayDeserializer()).createConsumer()) {

    embeddedKafka.consumeFromAnEmbeddedTopic(
            dltConsumer, "orders-json.DLT");

    ConsumerRecord<String, byte[]> dltRecord =
            KafkaTestUtils.getSingleRecord(
                    dltConsumer,
                    "orders-json.DLT",
                    Duration.ofSeconds(10));

    System.out.println(new String(
            dltRecord.value(), StandardCharsets.UTF_8));
}
```

This snippet uses `EmbeddedKafkaBroker` in tests; against a real broker, substitute the appropriate bootstrap servers and consumer properties. The DLT consumer uses `ByteArrayDeserializer` because the goal is to inspect the exact original bytes rather than trying to deserialize a broken payload into a DTO again.

DLT records usually carry headers added by `DeadLetterPublishingRecoverer`, such as original topic/partition/offset, exception class, and exception message. You can inspect these headers via `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, `KafkaHeaders.DLT_ORIGINAL_OFFSET`, `KafkaHeaders.DLT_EXCEPTION_FQCN`, and `KafkaHeaders.DLT_EXCEPTION_MESSAGE` if your Spring Kafka version provides those constants.

## 10. Integration Testing with Embedded Kafka

One test can verify all three behaviors: valid records reach the listener, malformed JSON does not reach the listener, and malformed JSON appears in the DLT as the original raw bytes.

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.serialization.ByteArrayDeserializer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import com.example.orders.config.OrdersConsumerConfiguration;
import com.example.orders.config.OrdersListenerConfiguration;
import com.example.orders.config.OrdersProducerConfiguration;
import com.example.orders.events.OrderCreated;
import com.example.orders.listener.OrderListener;

@SpringJUnitConfig(classes = {
        OrdersConsumerConfiguration.class,
        OrdersListenerConfiguration.class,
        OrdersProducerConfiguration.class,
        OrderListener.class
})
@EmbeddedKafka(
        topics = {"orders-json", "orders-json.DLT"},
        partitions = 1,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class DeserializationFailureTest {

    @Autowired
    KafkaTemplate<String, Object> ordersKafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    OrderListener orderListener;

    @Test
    void malformedJsonIsRecoveredToDltAsOriginalBytes() throws Exception {
        OrderCreated valid = new OrderCreated(
                "event-100", "order-100", "customer-7");
        ordersKafkaTemplate.send("orders-json", "order-100", valid)
                .get(10, TimeUnit.SECONDS);

        OrderCreated received = orderListener.received()
                .poll(10, TimeUnit.SECONDS);
        assertNotNull(received);
        assertEquals(valid, received);

        byte[] invalidJson = "{\"orderId\":"
                .getBytes(StandardCharsets.UTF_8);

        Map<String, Object> props = KafkaTestUtils.consumerProps(
                "orders-dlt-test", "false", embeddedKafka);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        try (Consumer<String, byte[]> dltConsumer =
                new DefaultKafkaConsumerFactory<String, byte[]>(
                        props,
                        new StringDeserializer(),
                        new ByteArrayDeserializer()).createConsumer()) {

            embeddedKafka.consumeFromAnEmbeddedTopic(
                    dltConsumer, "orders-json.DLT");

            ordersKafkaTemplate.send(
                    "orders-json", "bad-1", invalidJson)
                    .get(10, TimeUnit.SECONDS);

            ConsumerRecord<String, byte[]> dltRecord =
                    KafkaTestUtils.getSingleRecord(
                            dltConsumer,
                            "orders-json.DLT",
                            Duration.ofSeconds(10));

            assertNotNull(dltRecord);
            assertEquals("bad-1", dltRecord.key());
            assertArrayEquals(invalidJson, dltRecord.value());
            assertEquals("orders-json", new String(
                    dltRecord.headers()
                            .lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC).value(),
                    StandardCharsets.UTF_8));
            assertNotNull(dltRecord.headers()
                    .lastHeader(KafkaHeaders.DLT_EXCEPTION_FQCN));
            assertNull(orderListener.received().poll(100, TimeUnit.MILLISECONDS),
                    "Deserialization failure records must not reach the listener");
        }
    }
}
```

This is a test skeleton; place the producer/consumer beans in your project's actual `@Configuration` classes and ensure `EmbeddedKafkaBroker` is injected by the test context. When using `@SpringBootTest`, set `bootstrapServersProperty` so Spring Boot points to the embedded broker rather than accidentally connecting to a local broker.

In real tests, also include a test that sends a valid `OrderCreated` and awaits `orderListener.received()` to confirm the listener works normally. Use `BlockingQueue.poll(timeout)` instead of `Thread.sleep()` to synchronize with the listener thread.

DLT header names can be accessed via `KafkaHeaders` constants instead of string literals. When asserting headers, verify the exact constant names in your project's Spring Kafka version. The primary goal of the test is confirming that the raw bytes in the DLT match the sent payload and that the record carries source metadata.

## 11. Distinguishing Deserialization Failures from Validation Failures

The two error types occur at different stages:

| Error type | Stage | Is the listener called? | How to handle |
| --- | --- | --- | --- |
| Deserialization failure | During consumer poll/converting bytes to object | No, the container handles the exception from `ErrorHandlingDeserializer` | `ErrorHandlingDeserializer` + `DefaultErrorHandler` + recoverer |
| Validation/business failure | After payload becomes a DTO and the listener/service runs | Yes | Validate in the service, throw exception, retry or DLT per policy |

For example, valid JSON with an empty `orderId` can deserialize into `OrderCreated`; that is a validation failure rather than a deserialization failure. The listener is invoked and the service must decide how to handle it. Conversely, JSON with mismatched braces or a numeric field that cannot parse into the expected type fails before the listener.

Do not use `ErrorHandlingDeserializer` as a substitute for business validation. Successful deserialization only proves the payload can be converted into a Java type, not that its contents are valid.

## 12. Retry or Send Straight to the DLT?

Syntactically invalid JSON is normally an error that cannot self-heal by resending the same bytes. Therefore, Spring Kafka classifies `DeserializationException` as fatal/non-retryable by default in modern versions. The recoverer can be invoked immediately without waiting through backoff delays.

If a failure can be transient (such as a temporary schema registry outage in a specific deserializer design), separate that technical exception from genuine payload errors. Never mark all deserialization exceptions as retryable or all consumer errors as non-retryable without examining the root cause. Configure classifiers, `BackOff`, and recoverers according to system policy.

When publishing to the DLT fails, recovery is not complete. Do not catch and swallow exceptions from `DeadLetterPublishingRecoverer`; let the error handler recognize recovery failures, monitor them, and apply the appropriate policy. The DLT producer must have write permissions, the target topic must exist, and the serializer must support raw `byte[]`.

## 13. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Listener does not receive malformed JSON record | Expected behavior because deserialization fails before the listener | Check the DLT and error handler instead of waiting on the listener |
| Consumer stops on malformed JSON | `JsonDeserializer` used directly without `ErrorHandlingDeserializer` | Wrap the delegate with `ErrorHandlingDeserializer` |
| DLT receives null value or loses original bytes | DLT template cannot serialize `byte[]` or raw data header is not recovered | Use `DelegatingByTypeSerializer` supporting both `byte[]` and objects |
| DLT publish fails due to partition | DLT has fewer partitions than the source topic | Create the DLT with matching partitions or use an appropriate resolver |
| `ClassNotFoundException` | Type header points to a class missing on the consumer | Use default type/type mapping and control trusted packages |
| Malformed JSON is retried repeatedly | Incorrect classifier/backoff or version-specific behavior | Check the actual exception and fatal/non-retryable classification |
| DLT consumer also fails deserialization | DLT consumer uses `JsonDeserializer` for broken payloads | Use `ByteArrayDeserializer` to read raw bytes |
| No records appear in DLT | Listener container not running, wrong topic/group, or recoverer not attached | Check factory, error handler, group, and target topic |

## 14. Lab Completion Checklist

- [ ] Source topic and DLT exist with compatible partition counts.
- [ ] Consumer uses `ErrorHandlingDeserializer` wrapping `JsonDeserializer`.
- [ ] Default type, trusted packages, and type-header strategy are explicitly configured.
- [ ] Listener receives valid JSON as a DTO.
- [ ] Malformed JSON payload is sent as raw `byte[]` to reproduce a real failure.
- [ ] `DefaultErrorHandler` is attached to the listener container factory.
- [ ] `DeadLetterPublishingRecoverer` uses a producer with a serializer supporting `byte[]`.
- [ ] Failed records never reach the listener and are routed to the DLT.
- [ ] DLT consumer uses `ByteArrayDeserializer` to read the original payload.
- [ ] Key, raw value, and DLT source/error headers are verified.
- [ ] DLT publish failure and recovery monitoring are tested.

The lab is complete when a valid record is deserialized and reaches the listener, while a malformed JSON record is detected by the container before the listener, routed through `DefaultErrorHandler`, and stored in the DLT with its original byte payload and error metadata. This test confirms the application can isolate corrupt data while preserving evidence for later investigation and reprocessing.
