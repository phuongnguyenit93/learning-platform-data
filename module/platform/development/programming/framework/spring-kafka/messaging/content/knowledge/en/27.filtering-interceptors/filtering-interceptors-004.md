# Producer Interceptor

Kafka `ProducerInterceptor` is a producer-side extension point that lets you observe or adjust records right before the Kafka producer sends them and receive notifications when the send completes. In Spring Kafka, interceptors are configured on the Kafka `ProducerFactory`; therefore, producers created by the factory—including the producer used by `KafkaTemplate`—will run the interceptor.

A producer interceptor is suitable for cross-cutting tasks such as adding a source-service header, attaching technical metadata, collecting metrics, or observing send failures. It does not replace a serializer, does not manage business retries, and is not a consumer-side record filtering mechanism.

## 1. Where does ProducerInterceptor sit in the send flow?

When the application calls `KafkaTemplate.send(...)`, the template obtains a Kafka producer from `ProducerFactory` and calls the `KafkaProducer.send()` API. The producer interceptor is invoked at the Kafka client layer before the key/value are serialized into bytes and before the record is sent to the broker.

```text
Application
    |
    v
KafkaTemplate.send(topic, key, value)
    |
    v
ProducerFactory obtains KafkaProducer
    |
    v
KafkaProducer.send(ProducerRecord)
    |
    v
ProducerInterceptor.onSend(record)
    |
    v
Serializer + partition selection
    |
    v
Kafka broker
    |
    v
Broker acknowledgement / send failure
    |
    v
ProducerInterceptor.onAcknowledgement(metadata, exception)
    |
    v
KafkaTemplate callback / CompletableFuture
```

`onSend()` sees `ProducerRecord<K,V>` before the serializer converts the key/value to bytes. If the record does not yet specify a partition, the interceptor cannot know for certain which partition will ultimately be selected. After the broker responds, `onAcknowledgement()` receives `RecordMetadata` with the topic, partition, offset, and an exception if sending failed.

## 2. Lifecycle of ProducerInterceptor

Kafka defines the `org.apache.kafka.clients.producer.ProducerInterceptor<K,V>` interface with four methods:

| Method | When called | Purpose |
| --- | --- | --- |
| `configure(Map<String, ?> configs)` | When the Kafka client initializes the interceptor | Read producer configuration and interceptor-specific properties |
| `onSend(ProducerRecord<K,V> record)` | When the application calls `send()` | Observe or return a modified record before serialization |
| `onAcknowledgement(RecordMetadata metadata, Exception exception)` | When a send succeeds or fails | Observe broker metadata or send errors |
| `close()` | When the producer closes | Release resources created by the interceptor |

The Kafka client instantiates interceptors from the class list in the `interceptor.classes` configuration. Interceptors are normally created by the Kafka client, not the Spring container. Therefore, do not assume you can use constructor injection or `@Autowired` like an ordinary Spring bean.

## 3. Example: adding a source-service header

An application may want every outgoing record to carry a `source-service` header for tracing or investigation. Instead of repeating the header addition at every `KafkaTemplate` call site, you can use an interceptor:

```java
package com.example.messaging.kafka;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerInterceptor;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.header.internals.RecordHeader;

public class SourceServiceProducerInterceptor
        implements ProducerInterceptor<String, String> {

    private volatile String sourceService = "unknown";

    @Override
    public void configure(Map<String, ?> configs) {
        Object configured = configs.get("app.producer.source-service");
        if (configured != null) {
            sourceService = configured.toString();
        }
    }

    @Override
    public ProducerRecord<String, String> onSend(
            ProducerRecord<String, String> record) {

        if (record.headers().lastHeader("source-service") == null) {
            record.headers().add(new RecordHeader(
                    "source-service",
                    sourceService.getBytes(StandardCharsets.UTF_8)));
        }

        return record;
    }

    @Override
    public void onAcknowledgement(
            RecordMetadata metadata,
            Exception exception) {
        // Minimal example: only observe the result, do not block the I/O thread.
        if (exception != null) {
            System.err.println("Kafka send failed: " + exception.getMessage());
        }
        else if (metadata != null) {
            System.out.printf(
                    "Kafka record acknowledged: %s-%d offset=%d%n",
                    metadata.topic(), metadata.partition(), metadata.offset());
        }
    }

    @Override
    public void close() {
        // Close dedicated resources if the interceptor created any.
    }
}
```

In this example, the interceptor only adds the header when the header does not already exist. This check prevents creating duplicate `source-service` headers if the record already had metadata attached by the caller. Kafka headers store values as byte arrays; consumers need to decode UTF-8 when reading them.

The `System.err`/`System.out` lines are just to illustrate the callback. Real applications should use a non-blocking logger and metrics, avoiding excessive synchronous logging on send/receive threads.

## 4. Registering the interceptor with Spring Boot

Declare the interceptor class in producer properties:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      properties:
        "[interceptor.classes]": com.example.messaging.kafka.SourceServiceProducerInterceptor
        "[app.producer.source-service]": order-service
```

`interceptor.classes` is a Kafka producer configuration property. You can declare multiple interceptors as a class name list separated according to the list syntax supported by the Kafka client. Custom properties like `app.producer.source-service` are passed in the configuration map for the interceptor to read in `configure()`.

Because the interceptor is instantiated by the Kafka client, the class needs an accessible no-argument constructor. If the interceptor needs configuration data, pass it via producer properties or use a suitable static configuration mechanism; do not rely on Spring bean injection unless you have built a custom adapter.

When Spring Boot auto-configures `ProducerFactory`, the configuration above is placed into the producer properties. `KafkaTemplate` instances using that factory will use the interceptor automatically.

## 5. Registering the interceptor via ProducerFactory

If you construct `DefaultKafkaProducerFactory` manually, add `ProducerConfig.INTERCEPTOR_CLASSES_CONFIG` to the map:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, String> producerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(ProducerConfig.INTERCEPTOR_CLASSES_CONFIG,
                List.of(SourceServiceProducerInterceptor.class.getName()));
        properties.put("app.producer.source-service", "order-service");

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    public KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

This example illustrates standalone producer factory configuration. In a real application, add security, client ID, retries, idempotence, transactions, and any required environment properties. If the producer factory is shared by multiple `KafkaTemplate` instances, those templates will share the factory's interceptor policy.

## 6. Using an interceptor to modify records

`onSend()` can return the original record or a new `ProducerRecord`. For example, you can add headers, normalize metadata, or alter timestamp/key/value if the application design allows it.

When creating a new record, preserve the attributes you do not intend to change, such as topic, partition, timestamp, key, value, and headers. Typically, you should only modify `record.headers()` and return the original record to avoid accidentally dropping metadata.

Suitable use cases include:

- Adding default `source-service`, `correlation-id`, or trace metadata.
- Attaching the producer version or application name in a header.
- Counting application `send()` calls and categorizing them by topic.
- Recording technical send success/failure outcomes.
- Standardizing shared technical headers across multiple producers in the same service.

Do not use an interceptor to execute business logic such as updating orders, deducting balances, making HTTP calls, or writing critical data to a database. Those operations belong in an application service with clear transactions, retries, and idempotency.

## 7. How do onSend and onAcknowledgement differ?

The two callbacks occur at different times and have different information:

| Callback | What it can know | What it cannot conclude |
| --- | --- | --- |
| `onSend(record)` | Topic, specified partition if any, key, value, timestamp, and headers before serialization | Whether the broker received the record or the final offset |
| `onAcknowledgement(metadata, exception)` | Send result, broker metadata on success, exception on failure | Whether downstream business logic has processed the record |

`onSend()` is not a broker confirmation callback. Do not record a "sent successfully" metric here; you can only record send intent or `send()` API call counts.

`onAcknowledgement()` is invoked when the send produces a result. For successful records, `RecordMetadata` provides the actual partition and offset. On error, inspect `exception`; metadata may be unavailable. This callback does not replace the `KafkaTemplate` callback or `CompletableFuture` that application code uses to decide next business steps.

## 8. Ordering and multiple interceptors

The Kafka producer allows configuring multiple interceptors. The `interceptor.classes` list defines the producer's interceptor chain. When using multiple interceptors, order matters greatly if one interceptor creates a header that another interceptor reads or modifies.

Example:

```text
ProducerRecord
    |
    v
SourceHeaderInterceptor
    |
    v
CorrelationHeaderInterceptor
    |
    v
MetricsProducerInterceptor
    |
    v
Serializer / Kafka producer
```

Keep each interceptor focused on a single responsibility and test the actual ordering in configuration. Avoid having multiple interceptors write the same header using conflicting rules.

## 9. Thread safety and performance

The Kafka producer is thread-safe and can be called from multiple application threads. The interceptor instance used by the producer can also receive concurrent calls. Therefore:

- Do not use unsynchronized mutable fields to store per-record state.
- Use thread-safe structures for counters or metrics; prefer Micrometer over incrementing a shared `long` variable manually.
- Do not retain payloads/records in unbounded collections.
- Do not perform database, HTTP, or blocking I/O operations inside `onSend()` or `onAcknowledgement()`.
- Do not wait on `Future.get()` or wait for other callbacks inside an interceptor.
- Do not create a new producer or recursively call `KafkaTemplate.send()` from an interceptor.
- Keep `close()` safe when the producer shuts down.

`onSend()` runs on the thread calling producer send; `onAcknowledgement()` usually runs on the producer I/O thread. Acknowledgement callbacks must be very fast because blocking work can slow down producer response handling and degrade throughput.

## 10. Exceptions inside an interceptor

An interceptor is not the right place to reject a record by throwing an exception. The Kafka client catches and logs exceptions thrown by interceptors; those exceptions are not propagated back as normal send errors for the application to rely on.

Therefore:

- Validate business data before calling `KafkaTemplate.send()`.
- Use serializers to control payload conversion.
- Use `KafkaTemplate` callbacks/futures to handle send results.
- Use interceptors only for metadata and fault-tolerant technical observability.

If an interceptor fails while adding a header, record an appropriate metric/log and choose a safe fallback. Do not assume throwing an exception from `onSend()` will cancel sending the record.

## 11. Interceptors in a transactional producer

Producer interceptors also apply when the Kafka producer is configured for transactions. `onSend()` runs for the send call from the application; internal batch retries by the Kafka producer do not mean the interceptor is called again for every internal retry.

If `KafkaTemplate` sends within a listener container transaction, the interceptor can add headers to output records. However, the interceptor's own side effects—such as logging, pushing metrics, or calling systems outside Kafka—are not part of the Kafka transaction. A transaction rollback cannot erase a log already written or undo an HTTP call already executed.

In EOS flows, interceptors should keep a technical role and not execute business logic that requires atomicity. If you need durable auditing of committed events, record it based on commit completion or design an audit event/outbox appropriately; do not treat `onSend()` as proof that the transaction committed.

## 12. Distinguishing ProducerInterceptor, ProducerListener, and consumer RecordInterceptor

These similarly named APIs sit at different layers:

| Component | Layer | Purpose |
| --- | --- | --- |
| Kafka `ProducerInterceptor` | Kafka producer client | Observe/modify `ProducerRecord` before send and receive acknowledgement |
| Spring Kafka `ProducerListener` | `KafkaTemplate` | Spring callback when a send succeeds or fails |
| Spring Kafka `RecordInterceptor` | Consumer listener container | Observe or modify records before invoking the listener |
| `RecordFilterStrategy` | Consumer listener container | Filter out records that do not need to be passed to the listener |

If the goal is to add headers before sending, use `ProducerInterceptor` or attach headers in application code. If you need to handle callbacks per `KafkaTemplate.send()` call, use `ProducerListener` or the send future. If you want to filter records when the consumer receives them, use `RecordFilterStrategy`; a producer interceptor does not perform that role.

## 13. Testing ProducerInterceptor

You should unit-test interceptor logic separately and integration-test it through the producer factory.

### Unit test for onSend

Create a `ProducerRecord`, call `configure()` with a configuration map, then call `onSend()` and verify the header:

```java
package com.example.messaging.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Test;

class SourceServiceProducerInterceptorTest {

    @Test
    void addsSourceHeaderWhenMissing() {
        var interceptor = new SourceServiceProducerInterceptor();
        interceptor.configure(Map.of(
                "app.producer.source-service", "order-service"));

        var record = new ProducerRecord<>(
                "orders.created", "order-42", "payload");

        var result = interceptor.onSend(record);

        assertThat(result.headers().lastHeader("source-service").value())
                .isEqualTo("order-service".getBytes(StandardCharsets.UTF_8));
    }
}
```

Add a test for when the header already exists to ensure the interceptor does not overwrite caller-provided values. You should also test missing source configuration, blank values, and records with multiple headers of the same name if the application allows them.

### Integration test

1. Create a producer factory with the interceptor registered.
2. Send a record via `KafkaTemplate` to a test topic.
3. Consume the record from the broker and verify the `source-service` header exists with the right encoding.
4. Verify the interceptor receives the acknowledgement callback when sending succeeds.
5. Simulate a broker/send failure to test the `exception` branch and ensure the callback does not hang the producer I/O thread.
6. If multiple interceptors are configured, verify their order and final header output.

Do not just invoke `onSend()` directly and conclude the Spring Boot configuration is correct. Integration tests verify the class name, producer factory, and Kafka client actually use the interceptor.

## 14. Common mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Interceptor is never called | `interceptor.classes` is not declared on the active producer factory | Inspect the exact `ProducerFactory` used by `KafkaTemplate` |
| `@Autowired` in the interceptor is null | Kafka client instantiates the class directly, bypassing the Spring bean lifecycle | Pass settings through `configure()` or design a dedicated adapter |
| Duplicate headers | Interceptor always adds the header without checking existing headers | Check `lastHeader()` before adding |
| Consumer reads header incorrectly | Inconsistent byte encoding | Use UTF-8 consistently and test header bytes |
| Exception in interceptor does not fail the send | Kafka client catches/logs interceptor exceptions | Validate before send and use callbacks/futures to handle errors |
| Throughput drops sharply | Callback performs blocking I/O or excessive logging | Use non-blocking metrics and avoid heavy work on the producer I/O thread |
| Wrong counter under concurrency | Using non-thread-safe mutable fields | Use Micrometer or `LongAdder` |
| Audit records uncommitted messages | Using `onSend()` as proof of success | Record commit status via a transaction-aware flow or outbox |
| Using producer interceptor to filter consumer records | Wrong extension layer chosen | Use `RecordFilterStrategy` or consumer `RecordInterceptor` |

## 15. Implementation checklist

- [ ] The interceptor has a no-arg constructor and reads config via `configure()`.
- [ ] The class is registered in `interceptor.classes` of the right producer factory.
- [ ] `onSend()` only performs fast, non-blocking work.
- [ ] Headers are added conditionally without unintentionally overwriting caller metadata.
- [ ] Header values use consistent encoding.
- [ ] The interceptor is thread-safe when multiple threads send concurrently.
- [ ] `onAcknowledgement()` handles both success and failure, including missing metadata.
- [ ] Interceptor exceptions are not used to validate or cancel sends.
- [ ] Business side effects requiring atomicity are not placed in the interceptor.
- [ ] Integration-tested via `KafkaTemplate` and a test broker.

## 16. Conclusion

`ProducerInterceptor` is a Kafka producer extension point used by Spring Kafka through configuration on `ProducerFactory`. `configure()` receives settings, `onSend()` observes or adjusts records before serialization, `onAcknowledgement()` receives send results, and `close()` releases resources.

Use producer interceptors for technical metadata, common headers, metrics, and send observability. Keep callbacks short, thread-safe, and non-blocking, and do not place critical business logic inside them. In Spring Kafka, configure `interceptor.classes` on the exact producer factory used by `KafkaTemplate`; if you need callbacks per send call, consider `ProducerListener` or the send future, while consumer-side record filtering belongs to `RecordFilterStrategy`.

## References

- [Apache Kafka — ProducerInterceptor API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/producer/ProducerInterceptor.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring for Apache Kafka — Filtering Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/filtering.html)
