# Testing Deserialization Failures in Spring Kafka

A Kafka consumer can run smoothly for millions of events, yet a single record containing malformed bytes can cause it to fail repeatedly at the same offset. For example, a topic expects JSON for `OrderEvent`, but a producer sends `{broken-json`, sends Avro bytes to a JSON consumer, or attaches an untrusted type header. The error occurs **inside the Kafka deserializer before `@KafkaListener` is invoked**; a `try/catch` inside the listener cannot catch an error the listener has never seen.

With Spring Kafka, reliability test design must do more than prove "an exception happened"—it must answer: **where does the broken record go, does the consumer continue after the broken record, what policy governs offset handling, and if the recovery path fails, is data silently lost?**

This lesson belongs to **Spring Kafka Reliability Operations → Reliability Testing**, focusing on **Testing deserialization failures** with raw bytes, `ErrorHandlingDeserializer`, `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, Embedded Kafka tests, key/value failures, DLTs, retries, replay, offset observation, and testing commonly overlooked failure modes. Examples use Java 17+, Spring Boot 3.x, Spring Kafka 3.x, and corresponding Kafka clients; adjust configuration details to your actual version.

## 1. Testing goals and invariants

After this practice, a test suite should prove the following properties:

1. A record with **invalid value bytes** is detected as a deserialization failure instead of being turned into an incorrect DTO.
2. The listener that processes business events is **not invoked** as if the malformed record were a valid event.
3. The failed record is **quarantined to a DLT** or stops the consumer per the declared policy; it is not silently dropped.
4. If DLT-and-continue is chosen, valid records **later in the same partition** are processed.
5. The DLT preserves **raw bytes** and enough source metadata to investigate the topic, partition, and offset.
6. When DLT publishing fails, the system does not falsely declare recovery successful and advance past an unrecoverable offset.
7. Consumer restarts and potential redelivery/duplicates are handled according to the designed ack mode and idempotency.
8. Key deserialization, message conversion, and business validation are **not conflated as the same failure type**.

Each invariant requires explicit verification. For instance, "the listener continues" should be asserted using a valid record after the poison pill, not merely by a "consumer started" log line.

## 2. Kafka deserialization happens before the listener

The Kafka broker stores records as key/value byte arrays along with topic, partition, and offset metadata. Inside the consumer:

~~~mermaid
flowchart TD
    A["Kafka broker: key/value bytes"] --> B["KafkaConsumer.poll()"]
    B --> C["Key deserializer"]
    C --> D["Value deserializer"]
    D -->|Success| E["Spring Kafka listener container"]
    E --> F["@KafkaListener receives OrderEvent"]
    D -->|Direct deserializer throws error| G["Exception from poll()\nlistener has not run"]
    D -->|ErrorHandlingDeserializer catches error| H["Header contains DeserializationException\nvalue is typically null"]
    H --> I["CommonErrorHandler / DefaultErrorHandler"]
    I --> J["Recovery: DLT, stop, or other policy"]
~~~

For example:

~~~text
topic     = orders.events
partition = 0
offset    = 42
key bytes = UTF8("order-42")
value     = UTF8("{broken-json")
~~~

If `JsonDeserializer` cannot turn the value into an `OrderEvent`, the Java code in the listener **has no `OrderEvent` object to receive**. The error can surface directly from `KafkaConsumer.poll()`. When using a direct deserializer, an error handler that normally processes `ConsumerRecord` inside the listener container does not necessarily have enough record context for standard recovery.

### Distinguishing failures by layer

| Failure type | Location | Example | What to test |
|---|---|---|---|
| **Key deserialization** | Consumer decodes key bytes. | Malformed JSON key. | Does not get stuck, DLT retains raw key. |
| **Value deserialization** | Consumer decodes value bytes. | Syntax-invalid JSON, untrusted type header. | Error headers, raw value in DLT, subsequent records still run. |
| **Message conversion** | Spring converts record to method parameter/payload. | Converter cannot build DTO. | Conversion error handler, do not assume the same wrapper. |
| **Business validation** | Listener/service processes valid object. | `amount <= 0`. | Business error policy, separate retry/skip handling. |
| **Business infrastructure** | Service inside listener calls DB/API. | DB timeout, HTTP 503. | Retry/backoff, transactions/idempotency. |

Valid JSON that is missing a field does not necessarily trigger a deserialization exception; depending on the ObjectMapper, the field may become `null` or a default value and fail later during validation. To reliably trigger a **raw parsing failure**, use genuinely syntax-invalid payload bytes.

## 3. Why unit tests calling the listener directly are insufficient

For example:

~~~java
OrderEvent event = new OrderEvent("ORD-1", 100);
listener.handle(event);
~~~

This test verifies business logic **after** the DTO has already been created. It bypasses the broker, deserializer, error headers, consumer poll, container ack/offsets, and DLT. Therefore, it does not prove that a poison pill can be handled.

A deserialization integration test must use a producer with `ByteArraySerializer` to send **invalid raw bytes**, then observe the outcome using a production-like consumer and configuration. If a test merely mocks `JsonDeserializer.deserialize` to throw an exception, the recovery wiring between the Kafka client and the Spring listener container remains unverified.

## 4. Pitfalls of using JsonDeserializer directly

An initial configuration might look like this:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

When a malformed record fails inside `poll()`, a listener-level `DefaultErrorHandler` cannot automatically handle every `SerializationException` like a normal listener exception. Depending on the version/path, logs may indicate that the error handler cannot handle `SerializationException` directly and suggest `ErrorHandlingDeserializer`.

If the container keeps re-reading the same record without recovery, the partition can get **stuck at one offset**, preventing valid records behind it from being processed. Restarting the process with the same group may hit the exact same broken record again.

Key takeaway: **`DefaultErrorHandler` is not a substitute for proper deserializer configuration**. For raw JSON errors, Spring Kafka commonly recommends using `ErrorHandlingDeserializer` as a wrapper around a delegate `JsonDeserializer`.

## 5. ErrorHandlingDeserializer turns errors into handleable data

`org.springframework.kafka.support.serializer.ErrorHandlingDeserializer` invokes a **delegate deserializer**. When the delegate succeeds, the wrapper returns the DTO. When the delegate throws an exception, the wrapper stores `DeserializationException` details in Kafka headers per Spring Kafka's mechanism and typically returns `null`. The Spring Kafka listener container detects the error header and forwards it to `CommonErrorHandler` before the record listener is invoked as usual.

~~~mermaid
flowchart TD
    A["Raw value bytes"] --> B["ErrorHandlingDeserializer"]
    B --> C["Delegate: JsonDeserializer"]
    C --> D{"Decode OK?"}
    D -->|Yes| E["OrderEvent to listener"]
    D -->|No| F["Exception header + raw bytes\nnull value"]
    F --> G["Spring Kafka container"]
    G --> H["DefaultErrorHandler"]
    H --> I["DeadLetterPublishingRecoverer"]
    I --> J["orders.events.DLT"]
~~~

The wrapper **does not send to the DLT itself** and does not decide to skip on its own. It creates a path for the container error handler to classify the failure and apply a recovery policy. If `failedDeserializationFunction` is configured, the wrapper can return a fallback object; in that case, tests must determine whether that object reaches the listener or is still handled via headers.

With batch listeners, handling differs from record listeners and requires separate testing as covered later.

## 6. Spring Boot configuration wrapping the value deserializer

Suppose topic `orders.events` contains JSON:

~~~json
{"id":"ORD-1","amount":100}
~~~

DTO:

~~~java
package com.example.kafka;

public record OrderEvent(String id, long amount) {}
~~~

Example `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: orders-processor
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.kafka.OrderEvent
        spring.json.trusted.packages: com.example.kafka
        spring.json.use.type.headers: false
    listener:
      ack-mode: record
~~~

What these properties express:

- The actual Kafka client-level deserializer is `ErrorHandlingDeserializer`.
- `spring.deserializer.value.delegate.class` selects `JsonDeserializer` as the delegate.
- `spring.json.value.default.type` specifies the DTO for JSON without type headers.
- `spring.json.use.type.headers: false` makes sense in a demo with one topic and a fixed target type.
- `spring.json.trusted.packages` restricts packages allowed for deserialization; do not arbitrarily set `*` just to make a test pass.
- `ack-mode: record` and `enable-auto-commit: false` use the container's commit mechanism, though that **does not prove offsets commit immediately** after the error handler runs in every scenario.

If producers attach type headers, the application may use type mappings or a different schema contract. Do not change `trusted.packages` to a wildcard to bypass a compatibility error without understanding the risk of deserializing unexpected types.

### What if the error is in the key?

Keys can also be wrapped with `ErrorHandlingDeserializer`, for example when a topic uses a JSON key:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.key.default.type: com.example.kafka.OrderKey
~~~

This is a **key-policy replacement fragment**; do not blindly apply it to topics using String keys. If key deserialization fails, the key may be forwarded as **raw `byte[]` when sent to the DLT**, so the DLT producer must also have a compatible key serializer. Do not use `StringSerializer` for raw key bytes and expect the recoverer to fix it automatically.

## 7. Choosing a policy for an undecodable record

Each data source has its own rules. A malformed reference record might be quarantined so the stream continues; a mandatory transaction might require stopping the entire consumer group or preventing downstream publication.

| Policy | Meaning | When appropriate | What to verify |
|---|---|---|---|
| **Stop/fail** | Consumer stops or holds offset for incident handling. | Every event is mandatory and cannot be skipped. | Alerts, runbook, no silent endless retries. |
| **DLT then continue** | Publish raw failed record to a dead-letter topic. | Individual records may be isolated. | DLT receives bytes/headers, consumer processes next record. |
| **Bounded retry** | Retry when the error may be transient. | Schema registry or dependency temporarily unavailable. | Backoff/timeout; do not endlessly retry malformed JSON. |
| **Fallback payload** | Return an object describing the decode failure. | Application routes error handling itself. | Fallback is never treated as a valid business event. |
| **Policy-based discard** | Advance offset without keeping the record. | Only when explicitly approved by business rules. | Audit trail, alerts, counts of dropped items. |

A `{broken-json` payload will not turn into valid JSON even after 1,000 retries. If the error stems from a producer sending syntactically invalid bytes, the fix usually belongs in the producer or source data, not waiting for the parser to "self-heal."

## 8. DefaultErrorHandler and DeadLetterPublishingRecoverer

Spring Kafka provides `DefaultErrorHandler` as the standard record error mechanism and `DeadLetterPublishingRecoverer` to route failed records to a DLT.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.support.serializer.DeserializationException;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<String, Object> dltKafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
        dltKafkaTemplate,
        (record, error) ->
            new TopicPartition(record.topic() + ".DLT", record.partition())
    );

    // Demo: no additional retries for a recovered record.
    var handler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(0L, 0L));

    handler.addNotRetryableExceptions(DeserializationException.class);
    return handler;
}
~~~

What this means:

1. The destination is `orders.events.DLT` when the source is `orders.events`.
2. It preserves the source partition, so the DLT topic must have **at least as many partitions**.
3. `FixedBackOff(0L, 0L)` performs no extra retries, fitting a permanent JSON failure demo. Transient listener failures need a different policy.
4. Deserialization errors are often already classified as fatal/non-retryable in `DefaultErrorHandler` in corresponding versions; declaring it explicitly shows intent.
5. Publishing to the DLT does not mean a DLT consumer has finished business remediation.

**Easily missed detail:** When `ErrorHandlingDeserializer` fails on the **value**, `DeadLetterPublishingRecoverer` can reuse the **raw `byte[]`** as the DLT record's value. For a listener failure after JSON decoding succeeds, the value may be `OrderEvent`. The producer writing to the DLT needs serializers matching the types it will actually encounter.

### What if the DLT publisher fails?

If the recoverer cannot publish because the DLT topic is missing, the producer serializer is wrong, ACLs reject the write, or the broker fails to ACK, a system requiring zero record loss must **not treat that as a successful recovery**. Verify publisher acknowledgements, error handler behavior when the recoverer throws, and source offset commits under the specific ack mode and transaction settings. Never apply the assumption "after the error handler runs, the offset is always committed" to every configuration.

## 9. A DLT KafkaTemplate that handles both raw bytes and DTOs

In an example testing only **value deserialization failures with String keys**, `DelegatingByTypeSerializer` can be used on the DLT producer:

~~~java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.Serializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Bean
ProducerFactory<String, Object> dltProducerFactory(
        @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers) {

    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

    Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
    delegates.put(byte[].class, new ByteArraySerializer());
    delegates.put(OrderEvent.class, new JsonSerializer<>());

    return new DefaultKafkaProducerFactory<>(
        props,
        new StringSerializer(),
        new DelegatingByTypeSerializer(delegates)
    );
}

@Bean
KafkaTemplate<String, Object> dltKafkaTemplate(
        ProducerFactory<String, Object> dltProducerFactory) {
    return new KafkaTemplate<>(dltProducerFactory);
}
~~~

This producer template can serialize `byte[]` and `OrderEvent` values for the demo policy. If the system emits multiple DTO types or listener exceptions of other types, expand the serializer mappings or design a DLT envelope. If **key deserialization can also fail**, the key may become `byte[]`; the `StringSerializer` in this example will not work for that case and must be replaced with mixed key serializers or an appropriate template.

Producer `ENABLE_IDEMPOTENCE_CONFIG=true` helps reduce duplicates during certain producer retries per Kafka semantics, but it does not make the workflow **end-to-end exactly once**. The app can still crash after the DLT ACK and before committing the source offset, then publish the same DLT record again on the next recovery pass.

## 10. A listener to prove the consumer moves forward

A minimal listener:

~~~java
package com.example.kafka;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final BlockingQueue<String> processed =
        new LinkedBlockingQueue<>();

    @KafkaListener(topics = "orders.events", groupId = "orders-processor")
    public void handle(OrderEvent event) {
        processed.add(event.id());
    }

    public String awaitProcessedId(long timeoutSeconds)
            throws InterruptedException {
        return processed.poll(timeoutSeconds, TimeUnit.SECONDS);
    }
}
~~~

The queue serves purely as a test probe. A real consumer may write to a database or call a service and must be idempotent if records are redelivered.

The test will send **two records to the same partition**:

~~~text
offset N:   key="bad-1",  value=bytes("{broken-json")
offset N+1: key="good-2", value=bytes("{\"id\":\"ORD-2\",\"amount\":100}")
~~~

After the failed record is routed to the DLT:

- The listener never sees a valid `OrderEvent` from bad-1.
- The DLT contains the raw bytes `{broken-json`.
- The listener receives `ORD-2`, proving the partition was not blocked by the poison pill.

This assertion matters far more than merely seeing "message sent" at the producer.

## 11. Integration test with Embedded Kafka

Test dependencies typically require `spring-boot-starter-test` and `spring-kafka-test`. Use `@EmbeddedKafka` to create the broker/topics in the test, and a test Kafka producer **using ByteArraySerializer for the value** to send invalid raw bytes.

~~~java
package com.example.kafka;

import static java.nio.charset.StandardCharsets.UTF_8;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.ByteArrayDeserializer;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.events", "orders.events.DLT"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class DeserializationFailureIntegrationTest {

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    OrderListener listener;

    @Test
    void malformedValueGoesToDltAndValidValueContinues() throws Exception {
        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            embeddedKafka.getBrokersAsString());

        byte[] invalid = "{broken-json".getBytes(UTF_8);
        byte[] valid =
            "{\"id\":\"ORD-2\",\"amount\":100}".getBytes(UTF_8);

        try (var producer = new KafkaProducer<>(
                props, new StringSerializer(), new ByteArraySerializer())) {

            producer.send(new ProducerRecord<>(
                "orders.events", "bad-1", invalid))
                .get(10, TimeUnit.SECONDS);

            producer.send(new ProducerRecord<>(
                "orders.events", "good-2", valid))
                .get(10, TimeUnit.SECONDS);
        }

        // Prove the consumer is not stuck on the malformed record.
        assertThat(listener.awaitProcessedId(10)).isEqualTo("ORD-2");

        Map<String, Object> dltProps = KafkaTestUtils.consumerProps(
            "dlt-reader-" + UUID.randomUUID(),
            "false",
            embeddedKafka
        );
        dltProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        try (Consumer<String, byte[]> dltConsumer =
                new DefaultKafkaConsumerFactory<>(
                    dltProps,
                    new StringDeserializer(),
                    new ByteArrayDeserializer()
                ).createConsumer()) {

            dltConsumer.subscribe(List.of("orders.events.DLT"));

            ConsumerRecord<String, byte[]> dlt =
                KafkaTestUtils.getSingleRecord(
                    dltConsumer,
                    "orders.events.DLT",
                    Duration.ofSeconds(15)
                );

            assertThat(dlt.key()).isEqualTo("bad-1");
            assertThat(dlt.value()).isEqualTo(invalid);
            assertThat(dlt.headers().lastHeader(
                KafkaHeaders.DLT_ORIGINAL_TOPIC)).isNotNull();
        }
    }
}
~~~

### Assumptions of this integration test

1. The application context includes `OrderListener`, `ErrorHandlingDeserializer` configuration, and the DLT error handler from earlier sections.
2. The DLT producer has a serializer supporting **raw `byte[]`** values and String keys.
3. The test is isolated: no leftover consumer group offsets or DLT records from other tests. If multiple tests share a broker, use separate topics/groups or reset fixtures deterministically.
4. Both `orders.events` and `orders.events.DLT` have partition 0.
5. The consumer reading the DLT uses `ByteArrayDeserializer` to compare **original bytes**, rather than reusing the failing JSON deserializer.
6. `OrderListener`'s queue contains no leftover results from prior tests; in larger suites, add an explicit probe reset or isolate the test context.
7. `KafkaTestUtils.getSingleRecord` fits when expecting one DLT record. If intentionally sending multiple failing records, poll/filter by key and the corresponding original source offset.

This example **tests the real flow** and requires the application's beans/configuration. It is not meant to replace testing transactions, security, multi-broker setups, and consumer rebalances in a production-like environment.

## 12. Verifying original topic, partition, and offset

Do not only assert that the DLT contains raw bytes; source metadata helps locate the record in the broker. `DeadLetterPublishingRecoverer` can attach headers describing the original topic, partition, and offset. Example within a test scope that has `dlt`:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.support.KafkaHeaders;

Header sourceTopic = dlt.headers().lastHeader(
    KafkaHeaders.DLT_ORIGINAL_TOPIC);

assertThat(sourceTopic).isNotNull();
assertThat(new String(
    sourceTopic.value(), StandardCharsets.UTF_8))
    .isEqualTo("orders.events");

assertThat(dlt.headers().lastHeader(
    KafkaHeaders.DLT_ORIGINAL_PARTITION)).isNotNull();

assertThat(dlt.headers().lastHeader(
    KafkaHeaders.DLT_ORIGINAL_OFFSET)).isNotNull();
~~~

When asserting the exact offset number, take `RecordMetadata.offset()` from the producer send result for the malformed record rather than hard-coding `0`. On a broker that already holds data, offsets will not start at 0 as the test might assume.

Exception headers can contain class names, messages, or stack traces. Do not forward raw exception headers/payloads to centralized logging if they contain PII, tokens, or internal information. DLTs require appropriate ACLs, retention, replay controls, and data access permissions.

## 13. Negative test without ErrorHandlingDeserializer

Create **a separate test context/consumer group** using `JsonDeserializer` directly and send malformed bytes. Verify:

- A deserialization-related error arises from the consumption path before the listener.
- The listener does not receive the malformed event as a valid DTO.
- A record-based error handler cannot necessarily recover as it does with the wrapper.
- The consumer may repeatedly fail on the same record without a special handling policy.

Do not run the negative test on the same group/topic as the positive DLT test, or a bad record can stall the other test. The purpose of this test is to **prove the failure boundary sits before the listener**, without relying on an exact log string from a specific Spring Kafka version.

## 14. Testing key deserialization failures

If keys are serialized as JSON `OrderKey` instead of Strings, a dedicated test is needed:

~~~text
key bytes   = "{broken-key"
value bytes = "{\"id\":\"ORD-3\",\"amount\":10}"
~~~

In the test, use `ByteArraySerializer` for both key and value to build the raw record:

~~~java
ProducerRecord<byte[], byte[]> badKey = new ProducerRecord<>(
    "orders.events",
    "{broken-key".getBytes(UTF_8),
    "{\"id\":\"ORD-3\",\"amount\":10}".getBytes(UTF_8)
);
~~~

This is a record-construction fragment; the actual test needs its own JSON-key producer and consumer configuration. Expectations:

1. The key wrapper catches the error and the container processes the error header properly.
2. The listener does not receive the invalid event as a success.
3. The DLT retains the original raw **key bytes**.
4. The DLT producer has a serializer for `byte[]` keys rather than relying on `StringSerializer`.
5. After recovery, valid records on the same partition continue to be processed per policy.

If the DLT does not receive the record, inspect the **DLT producer**, not only the consumer deserializer: serializer mismatches, insufficient topic partitions, missing publish permissions, or broker timeouts can all cause failures at the recovery step.

## 15. Valid JSON with invalid business data: not the same test

Payload:

~~~json
{"id":"ORD-4","amount":-100}
~~~

This is valid JSON and can be deserialized into `OrderEvent`. If the application requires a positive amount:

~~~java
if (event.amount() <= 0) {
    throw new InvalidOrderException("INVALID_AMOUNT");
}
~~~

then the error belongs to **business validation** inside the listener/service, not deserialization. A separate test should verify handler retry/DLT behavior for the business exception type. Do not use this kind of error to claim malformed JSON was tested.

Similarly, if JSON omits `id`, Jackson may still construct the object with `null` depending on configuration. To reliably cause a deserialization failure, use invalid JSON syntax or an explicit mapping constraint verified at the deserializer layer.

### Type headers, trusted packages, and schema mismatches

A topic carrying multiple event types may use type headers or a schema registry. Failures can occur due to:

- Producer sending an unknown type header.
- Consumer not trusting the package or type not being mapped.
- Incompatible schema version.
- Payload serialized in a different format.
- Decoding succeeds, but contents/semantics violate the contract.

Tests should classify the failure at the right layer and keep trusted packages secure. Do not fix failures by setting `spring.json.trusted.packages=*` without a security review. For Avro/Protobuf/registry formats, test with the real serializers/deserializers and corresponding version errors; JSON tests do not replace those protocols.

## 16. Batch listeners require separate deserialization tests

A `@KafkaListener` can process individual records or batches:

~~~java
@KafkaListener(
    topics = "orders.events",
    containerFactory = "batchKafkaListenerContainerFactory"
)
void handleBatch(java.util.List<OrderEvent> orders) {
    // ...
}
~~~

In a batch listener, `ErrorHandlingDeserializer` may place a null payload and a deserialization exception header at the position of the failing record. How the failure reaches the error handler **is not automatically the same as for a record listener**. Depending on the batch converter/container mechanism, the application may need to inspect per-index exception headers and throw `BatchListenerFailedException` identifying the failing record/index.

Example test with 5 records and one failure at index 2:

| Situation | What to prove |
|---|---|
| Indices 0,1 valid | Processed correctly before the failure is identified. |
| Index 2 malformed | Listener accurately identifies the failing index/offset. |
| Indices 3,4 valid | After recovery, not lost or duplicated outside retry semantics. |
| Batch rollback/replay | Business handler tolerates redelivery. |
| Failed record sent to DLT | Correct raw bytes and metadata, without wrong offsets. |

Do not run only record-listener tests and conclude that a production batch listener is equally reliable. Batch retry policies, partial batch processing, converters, and ack modes must all be verified under the actual configuration.

## 17. Poison pills in a partition and consumer progression

Example:

~~~text
orders.events partition 0:
  offset 100: valid A
  offset 101: malformed JSON
  offset 102: valid B
  offset 103: valid C

orders.events partition 1:
  offset 77: valid D
~~~

With a "DLT then continue" policy, A, B, and C are expected to be processed in order on partition 0, the record at offset 101 is quarantined, and partition 1 keeps operating within the consumer group. Do not assert **strict cross-partition ordering**, because Kafka only guarantees ordering per partition.

With a strict stop/fail policy, the right outcome may be for the container to stop/pause and raise an alert. Reliability does not always mean "skip every bad record"; it means consistent behavior matching the chosen business contract.

The DLT **does not delete the original record** from the source topic. Another group or an offset reset can encounter the exact same malformed bytes again. Tests must distinguish between **a record existing in the Kafka log** and **a consumer group's consumption position/committed offset**.

## 18. Verifying offsets after recovery and restart

To verify durability:

1. Send a malformed record followed by a valid record **to the same partition**.
2. Wait for the recoverer to publish to the DLT and the listener to process the valid record.
3. Stop the container cleanly and wait for the consumer to leave the group.
4. Query the group's committed offset or restart the container with the same group ID.
5. Verify it does not get stuck endlessly on the already-recovered malformed record.
6. If redelivery occurs due to a crash/commit race, both the DLT and business consumer must handle duplicates safely.

`AckMode.RECORD`, `MANUAL`, `MANUAL_IMMEDIATE`, and error handler/transaction options have different commit behaviors. **Do not assume the offset is committed the moment the recoverer callback finishes**. Tests must explicitly verify:

- *Functional progression*: subsequent valid records are processed.
- *Durable progression*: committed offsets/replay behavior align with policy across consumer restarts.

Avoid arbitrary `Thread.sleep(...)` calls to guess that offsets have been committed; use synchronization, container/group state waits, and bounded timeouts.

## 19. Fault injection at the DLT publisher

A DLT happy-path test does not cover failures in the recovery pipeline itself. You should exercise:

| Injected failure | What to verify |
|---|---|
| DLT topic missing when auto-creation is disabled. | Recoverer fails properly; no silent loss of source record. |
| Producer lacks write permission to DLT. | Appropriate alert/retry path; no false recovery success report. |
| DLT has fewer partitions than source. | Partition selection failure is caught; fix topic topology. |
| DLT value producer does not support `byte[]`. | Serialization error is reported, not treated as sent. |
| Key deserialization fails but DLT key serializer accepts only String. | Serializer mismatch is caught by key-path testing. |
| Broker does not ACK or publish times out. | Error handler preserves recovery/offset semantics per configuration. |
| Crash after DLT ACK before source offset commit. | DLT duplicate may occur; DLT processing path is idempotent. |
| DLT consumer reuses JsonDeserializer for raw malformed bytes. | Test fails at the right place; need a raw-bytes/envelope DLT reader. |

To prove "no record is lost," inspect **broker DLT write acknowledgements** and **source offset behavior** when publishing fails, rather than merely asserting `DeadLetterPublishingRecoverer.accept(...)` was called. If the recoverer publishes asynchronously, configure and verify future completion timing and timeouts for your actual version.

## 20. DLT replay and data remediation

The DLT is a **quarantine location** for failed records, not "business processing completed." Example DLT metadata:

~~~text
originalTopic     = orders.events
originalPartition = 0
originalOffset    = 42
rawValue          = "{broken-json"
errorCategory     = DESERIALIZATION
~~~

A controlled replay workflow:

1. Identify whether the error was caused by genuinely corrupted bytes, incompatible schema/version, misconfigured consumer deployment, or an untrusted type header.
2. Inspect the source producer and payload format; verify the corrected payload satisfies a valid data contract.
3. If the raw bytes are permanently corrupted, quarantine them or ask upstream to emit a corrected version; do not endlessly replay the same invalid bytes back into the source topic.
4. Once consumer config/schema is fixed, replay with a stable event key and monitor the outcome.
5. Apply idempotency to consumer business side effects because the DLT may contain duplicates from recovery races.
6. Record outcomes such as `REPLAYED`, `REJECTED_FINAL`, or `WAITING_FOR_SOURCE_FIX` in the application's audit trail.

You can build a source reference from the original topic, partition, and offset:

~~~text
sourceRecordRef = originalTopic + ":" +
                  originalPartition + ":" + originalOffset
~~~

This is a **positional identifier** within a Kafka log/cluster, not a global business ID. When a producer re-emits an event at a new offset, the business key remains essential to prevent duplicate side effects.

## 21. Observability: what to log and when to alert

A log event should capture enough metadata to investigate without dumping raw payloads:

~~~json
{
  "event": "kafka.deserialization.failed",
  "consumerGroup": "orders-processor",
  "topic": "orders.events",
  "partition": 0,
  "offset": 42,
  "errorCategory": "INVALID_JSON",
  "recoveryAction": "DLT",
  "dltTopic": "orders.events.DLT"
}
~~~

This is an **application-defined schema**, not a default log format. Values such as keys, headers, and raw payloads may contain PII/tokens, so store them only in the DLT or tools with proper access controls and retention if business rules require.

Metrics to observe:

| Metric | Issue detected |
|---|---|
| Deserialization errors by topic/error category | Is a new producer/schema rollout causing mass failures? |
| DLT publish success/failure | Is recovery working or is the quarantine path broken? |
| DLT backlog and oldest pending age | How many records await remediation? |
| Consumer group lag by partition | Is a poison pill holding an offset back? |
| Retry attempts and recovery duration | Are there infinite retries or unreasonable backoffs? |
| Valid records processed after failure | Is the container actually moving forward? |
| Replay success/failed/dropped | Is the DLT becoming a "data black hole"? |

Do not use offset, event ID, or unique correlation ID as **high-frequency metric labels** because cardinality explodes. Use logs/audits for granular identifiers and metrics for bounded dimensions.

Alerts should distinguish:

- One malformed record successfully sent to DLT: warning depending on policy.
- DLT publish failure: critical if no fallback recovery path exists.
- Sudden spike in error rate: an entire producer may be emitting the wrong schema.
- Steadily growing consumer lag on a single partition: may be stuck on a poison pill.
- Aging DLT backlog: records were retained but lack a final business resolution.

## 22. Reliability test matrix

| ID | Data or failure | Expectation |
|---|---|---|
| D-01 | Schema-valid JSON. | Listener processes it, no DLT. |
| D-02 | Malformed JSON `{broken-json`. | ErrorHandlingDeserializer reports error, raw bytes in DLT. |
| D-03 | Malformed then valid on same partition. | Subsequent valid record is processed. |
| D-04 | Malformed JSON key. | Key error path, DLT retains raw key with proper serializer. |
| D-05 | Valid JSON, negative amount. | Business validation error, not mislabeled as deserialization. |
| D-06 | Untrusted type header. | Does not deserialize out-of-policy class; recovers properly. |
| D-07 | Syntactically valid JSON with wrong mapped type. | Error classified at the right layer. |
| D-08 | Missing DLT topic / ACL denied. | No silent ack as successful recovery. |
| D-09 | DLT producer has wrong serializer. | Test catches serialization/publish failure. |
| D-10 | Restart after malformed record. | Offset progression and any replay match policy. |
| D-11 | Crash after DLT ACK. | Potential duplicate, DLT consumer is idempotent. |
| D-12 | Multi-partition with one poison pill. | Other partitions proceed per policy, no global order assumed. |
| D-13 | Batch listener with malformed record in middle index. | Identifies exact index/offset and recovers properly. |
| D-14 | Schema registry temporarily unavailable. | Bounded retry/backoff if classified as transient. |
| D-15 | Mass malformed records. | Error rate/quality alert, no invalid data published. |
| D-16 | DLT containing simulated PII. | Logs/metrics omit sensitive payload, proper permissions applied. |
| D-17 | Replay after producer/consumer fix. | Business outcome is not duplicated. |

For small projects, implement D-01, D-02, D-03, D-08, and D-10 first. These scenarios verify decoding, recovery, progression, and restart behavior that a listener unit test cannot cover.

## 23. Making tests stable and independent of random timing

Kafka integration tests easily become flaky when they merely call `Thread.sleep(1000)` and assert. Good practices:

1. **Use isolated topics/groups** per test or clean fixtures deterministically.
2. **Await producer ACKs** with `Future.get(timeout)` before observing the consumer.
3. **Await the listener with a queue/latch/Awaitility** using finite timeouts.
4. **Use actual offsets from RecordMetadata** when asserting DLT offsets; do not hard-code.
5. **Send fixed malformed raw bytes** instead of relying on mutable validation rules.
6. **Separate test probes from business side effects**, or use an idempotent test database.
7. **Control consumer lifecycle**, topic partition assignment, and group offsets when testing restarts.
8. **Read the DLT with ByteArrayDeserializer** for deserialization failure records.
9. **Avoid coupling to exact exception message strings**, preferring exception classes/categories and output behavior.
10. **Add production-like cluster tests** when ACLs, TLS, rebalances, rolling upgrades, broker outages, and multiple partitions matter.

Embedded Kafka is good for testing container mechanics inside the JVM/test process, but does not by itself prove all production infrastructure. With Testcontainers/Kafka cluster tests, wait for the broker to be ready, topics created, and listener assigned before sending fixtures.

## 24. Runbook when production hits a deserialization failure

Operators should follow this sequence:

1. **Identify topic/partition/offset and consumer group.** Collect timestamp and correlation ID if present.
2. **Classify the error:** key deserializer, value deserializer, conversion, validation, or listener service.
3. **Inspect deserializer configuration:** wrapper, delegate class, schema/type mappings, trusted packages, and header policy.
4. **Check the DLT:** topic, partitions, producer serializer, ACLs, ACKs, backlog, and retention.
5. **Assess blast radius:** one corrupt record or a producer deployment emitting the wrong schema across the board?
6. **Verify progression:** are valid records after the poison pill being processed, or is consumer group lag still climbing?
7. **Fix root cause and choose remediation:** producer fix, consumer config fix, quarantine, DLT replay, or stop per contract.
8. **Reconcile business side effects:** did redelivered events produce duplicate data?
9. **Close the incident with evidence:** failed records have outcomes, offset/lag stabilized, DLT backlog addressed.

Do not reset consumer group offsets or delete the DLT just to make dashboards turn green. Resetting offsets can replay millions of already-processed events; deleting the DLT can lose unremediated records. Such actions require approved decisions, an idempotency plan, and auditing.

## 25. Common mistakes

**"Adding a try/catch inside `@KafkaListener` solves it."** Deserialization errors happen before the listener, so tests must exercise raw bytes and the container.

**"`DefaultErrorHandler` handles every `SerializationException` from poll."** Not true by default with a direct deserializer; `ErrorHandlingDeserializer` turns the error into headers/context the container can process.

**"Enabling the wrapper automatically creates the DLT."** The wrapper does not create a recoverer, topic, or compatible KafkaTemplate.

**"Seeing a record in the DLT guarantees the consumer moved on."** You must assert that subsequent valid records on the same partition are processed, along with offset/restart semantics.

**"The DLT only needs JsonSerializer."** Raw deserialization failures can pass `byte[]` to the DLT producer; key errors also require a compatible key serializer.

**"Valid JSON with a wrong amount is a deserialization failure."** If the object was decoded, it is usually a validation/business error with its own policy.

**"Retrying many times will fix a malformed record."** The bytes in the Kafka log do not change when a producer fix is needed. Fix the format/config and then perform a controlled replay.

**"The DLT always has exactly one record, never duplicates."** Crashing after DLT ACK and before committing the source offset can republish; DLT handling must tolerate duplicates.

**"One EmbeddedKafka test is enough for production."** Broker outages, ACLs/TLS, rebalances, multi-partition setups, CDC/replay, and real infrastructure still need separate tests.

**"Logging full payloads/exception headers speeds up debugging."** This can expose PII, secrets, or internal data; prefer safe metadata and an access-controlled DLT.

**"Discarding a malformed record is always safe because it is just one record."** One record could be a mandatory financial transaction; deciding between drop, DLT, or stop must follow the data contract.

## 26. Workflow to complete the practice

1. Define the input contract of `orders.events`: key/value encoding, JSON target type, and malformed-bytes policy.
2. Configure `ErrorHandlingDeserializer` for values with a `JsonDeserializer` delegate.
3. Create a `DefaultErrorHandler` with a recoverer targeting `orders.events.DLT`.
4. Configure the DLT producer to support raw `byte[]`; create matching topics/partitions.
5. Create a thread-safe listener/probe for valid events.
6. Use `KafkaProducer<String,byte[]>` to send malformed JSON followed by valid JSON.
7. Assert that the subsequent valid record is processed by the listener.
8. Read the DLT with `ByteArrayDeserializer`; assert raw bytes and source metadata.
9. Test DLT publisher failures to ensure there is no silent loss.
10. Stop/restart the consumer to verify committed offsets and duplicate tolerance.
11. Add tests for key deserialization, batch listeners, untrusted type headers, and multiple partitions.
12. Build monitoring/runbooks for DLT backlog, error rates, and approved replays.

A test suite meets its goal when it proves both **behavior on failed records** and **behavior on valid records after the failure**, not just an exception class. If the system chooses to stop instead of routing to a DLT, tests must verify a controlled stop with zero data loss rather than forcing every consumer to skip.

## Conclusion

**Testing deserialization failures** in Spring Kafka must start with **invalid bytes on the broker**, because key/value deserializer errors can happen before `@KafkaListener` and trap the consumer at the same offset. `ErrorHandlingDeserializer` bridges the gap to Spring Kafka's error handling; `DefaultErrorHandler` and `DeadLetterPublishingRecoverer` allow isolating malformed records to a DLT when business rules permit.

Do not stop at asserting "an exception was thrown" or "the DLT has data." Reliability testing must prove **raw bytes and source metadata are preserved**, **subsequent valid records still run**, **DLT publish failures are not treated as success**, **offsets and restarts follow policy**, and **redelivery/duplicates do not corrupt business data**. These invariants turn deserialization failures from an uncontrollable poison pill into a detectable, investigable, and recoverable situation.
