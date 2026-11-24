# Sending headers with KafkaTemplate

A Kafka record does not only have a key and a value. A record can also carry **headers** to pass metadata alongside the payload, such as `trace-id`, `correlation-id`, event type, contract version, or origin source. With Spring Kafka, headers can be sent by creating a `ProducerRecord` and calling `KafkaTemplate.send()`, or by creating a Spring `Message<?>` and sending it directly via `KafkaTemplate`.

Headers are useful when consumers need information for routing, observability, request correlation, or version handling without embedding all metadata into the JSON payload. You must distinguish Kafka headers from Spring Message headers: Kafka stores headers as names and byte arrays, whereas Spring Message can hold various Java types and requires a converter/header mapper to convert them.

## 1. What components make up a Kafka record?

A Kafka record has the following main components:

| Component | Role |
|---|---|
| Topic | Where the record is written |
| Partition | The partition holding the record |
| Key | Data commonly used to select a partition and identify an entity |
| Value | Business payload, usually JSON or bytes |
| Timestamp | Timestamp attached to the record according to topic configuration |
| Headers | Additional metadata as pairs of name and byte value |

Example of a payment event record:

```text
topic: payments.events
key: payment-9001
value: {"paymentId":"payment-9001","amount":250000}
headers:
  trace-id: 8d7a...
  correlation-id: checkout-123
  event-type: PaymentCompleted
  schema-version: 2
```

Headers are record metadata, outside the value. Adding `trace-id` does not alter the JSON payload, key, or offset. Partition selection still normally relies on the key and partitioner; headers only affect partitioning if the application implements a custom partitioner that reads headers.

## 2. Kafka headers are byte arrays

In the Kafka client, a header is represented by `org.apache.kafka.common.header.Header`, consisting of:

- `key()`: header name as a string.
- `value()`: value as a `byte[]`, which may be `null`.

A record can contain multiple headers with the same name. `Headers` preserves headers in insertion order; consumers can fetch the last header with `lastHeader(name)` or iterate over all of them with `headers(name)`.

Because the value is bytes, producer and consumer must agree on encoding. For text metadata, UTF-8 is the common choice. For binary data, keep raw bytes and use an agreed-upon format.

```java
byte[] traceBytes = traceId.getBytes(StandardCharsets.UTF_8);
```

Do not pass an arbitrary Java object directly into a Kafka header. Serialize that value into bytes according to an explicit format, or use a Spring Kafka header mapper when sending a Spring `Message<?>`.

## 3. Sending headers with ProducerRecord and KafkaTemplate

The most direct way is to create a `ProducerRecord`, add `RecordHeader` entries, and send it with `KafkaTemplate`. This approach gives exact control over header names, byte values, and duplicate header names.

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class PaymentEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    PaymentEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String paymentId, String json, String traceId) {
        var record = new ProducerRecord<>(
                "payments.events",
                paymentId,
                json
        );

        record.headers().add(new RecordHeader(
                "trace-id",
                traceId.getBytes(StandardCharsets.UTF_8)
        ));
        record.headers().add(new RecordHeader(
                "event-type",
                "PaymentCompleted".getBytes(StandardCharsets.UTF_8)
        ));

        kafkaTemplate.send(record);
    }
}
```

`ProducerRecord` holds topic, key, value, and headers. The three-argument constructor in the example lets the Kafka partitioner choose a partition based on the key. If you need to specify a partition or timestamp, use the corresponding `ProducerRecord` constructor.

In Spring Kafka 3.x, `KafkaTemplate.send()` returns `CompletableFuture<SendResult<K, V>>`; older versions may use `ListenableFuture`. In real-world applications, observe the asynchronous result to detect serialization errors, broker errors, or send failures. Do not treat calling `send()` as proof that the record was successfully written by the broker.

### Adding multiple headers with the same name

Kafka allows multiple headers with the same name. For example, if a record has multiple tags:

```java
record.headers().add(new RecordHeader(
        "tag", "priority".getBytes(StandardCharsets.UTF_8)));
record.headers().add(new RecordHeader(
        "tag", "customer-facing".getBytes(StandardCharsets.UTF_8)));
```

The consumer can read all `tag` values. Do not assume header names are always unique within a record; explicitly define whether the application wants the first value, the last value, or the entire list.

## 4. Sending headers with Spring Message and KafkaHeaders

Spring Kafka supports sending a Spring `Message<?>` via `KafkaTemplate.send(message)`. This approach fits well when the application already uses Spring Messaging and wants to express topic, key, partition, and metadata as message headers.

Common constants in `KafkaHeaders`:

| Constant | Purpose |
|---|---|
| `KafkaHeaders.TOPIC` | Target topic |
| `KafkaHeaders.MESSAGE_KEY` | Key of the Kafka record |
| `KafkaHeaders.PARTITION` | Target partition if explicitly specified |
| `KafkaHeaders.TIMESTAMP` | Record timestamp if specified |
| `KafkaHeaders.CORRELATION_ID` | Correlation ID used in request/reply or message correlation |

Example sending a message with custom headers:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class SpringMessagePaymentPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    SpringMessagePaymentPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String paymentId, String json, String traceId) {
        Message<String> message = MessageBuilder
                .withPayload(json)
                .setHeader(KafkaHeaders.TOPIC, "payments.events")
                .setHeader(KafkaHeaders.MESSAGE_KEY, paymentId)
                .setHeader(KafkaHeaders.CORRELATION_ID, "checkout-123")
                .setHeader("trace-id", traceId)
                .setHeader("event-type", "PaymentCompleted")
                .build();

        kafkaTemplate.send(message);
    }
}
```

`KafkaHeaders.TOPIC` and `KafkaHeaders.MESSAGE_KEY` are metadata controlling `ProducerRecord` creation. Custom headers such as `trace-id` and `event-type` are converted into Kafka record headers via the `RecordMessageConverter` and header mapper configured on the template.

Do not confuse `KafkaHeaders.MESSAGE_KEY` with a custom header named `message-key`. Using `KafkaHeaders` constants tells Spring Kafka which fields control topic, key, partition, or timestamp; any other custom names are application metadata.

## 5. Spring Message headers and Kafka record headers differ

A Spring `Message<?>` has a payload and a Spring Messaging headers map. Values in the map can be `String`, `UUID`, `Long`, objects, or other types. Kafka record headers only store byte arrays. The converter/header mapper is responsible for converting between the two models.

| Characteristic | Spring Message header | Kafka record header |
|---|---|---|
| Value type | Java Object | `byte[]` or `null` |
| Scope | Inside the Spring Messaging application | Stored alongside the record in Kafka |
| Conversion | Can keep Java types at runtime | Must be encoded/serialized into bytes |
| Multiple values with same name | Standard header map has one value per key | Can have multiple headers with the same name |

When using `KafkaTemplate.send(Message<?>)`, the template uses `RecordMessageConverter` to convert the Spring Message into a Kafka `ProducerRecord`. The header mapper used by the converter decides how custom headers are mapped.

For text metadata, prefer `String` values and verify whether the active mapper maps those headers. For complex object headers, `DefaultKafkaHeaderMapper` can serialize values and attach type metadata to restore objects across Spring Kafka. When communicating with non-Spring applications, prefer string/byte headers with explicit encoding and schema.

If mapping control is needed, you can configure a dedicated `MessagingMessageConverter` and attach an appropriate `KafkaHeaderMapper`. Default APIs and mappers can differ across Spring Kafka versions; check the actual converter on `KafkaTemplate` in your application before relying on automatic mapping behavior.

The example below uses `SimpleKafkaHeaderMapper` for `String` and `byte[]` custom headers:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Configuration
class KafkaMessageConverterConfiguration {

    @Bean
    RecordMessageConverter kafkaRecordMessageConverter() {
        var converter = new MessagingMessageConverter();
        converter.setHeaderMapper(new SimpleKafkaHeaderMapper());
        return converter;
    }
}
```

Attach this converter to the `KafkaTemplate` used by the application:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Bean
KafkaTemplate<String, String> kafkaTemplate(
        ProducerFactory<String, String> producerFactory,
        RecordMessageConverter kafkaRecordMessageConverter
) {
    var template = new KafkaTemplate<>(producerFactory);
    template.setMessageConverter(kafkaRecordMessageConverter);
    return template;
}
```

If custom headers contain `UUID`, numbers, or complex objects, choose a mapper capable of converting those types, such as `DefaultKafkaHeaderMapper`, and standardize decoding on the consumer. With non-Spring applications, prefer UTF-8 strings or bytes per a shared contract so there is no dependency on Spring-specific type metadata.

## 6. Reading custom headers on the consumer

When a listener receives a `ConsumerRecord`, it can read Kafka headers directly. Example:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class PaymentEventListener {

    @KafkaListener(topics = "payments.events", groupId = "payment-projection")
    public void consume(ConsumerRecord<String, String> record) {
        String traceId = readUtf8Header(record, "trace-id");
        String eventType = readUtf8Header(record, "event-type");

        process(record.key(), record.value(), traceId, eventType);
    }

    private String readUtf8Header(
            ConsumerRecord<String, String> record,
            String name
    ) {
        Header header = record.headers().lastHeader(name);
        if (header == null || header.value() == null) {
            return null;
        }
        return new String(header.value(), StandardCharsets.UTF_8);
    }

    private void process(
            String paymentId,
            String payload,
            String traceId,
            String eventType
    ) {
        // Process the event and attach traceId to logs/tracing context.
    }
}
```

If a header can repeat its name, use `headers(name)` to iterate over all entries instead of `lastHeader(name)`:

```java
for (Header header : record.headers().headers("tag")) {
    String tag = header.value() == null
            ? null
            : new String(header.value(), StandardCharsets.UTF_8);
    log.debug("tag={}", tag);
}
```

For listeners receiving the payload directly instead of `ConsumerRecord`, custom headers can be mapped into Spring Message headers if the converter/header mapper is configured accordingly. When specific Kafka metadata is needed or duplicate header names must be handled, receiving `ConsumerRecord` is clearer.

## 7. Using headers for correlation ID and trace ID

In a multi-service architecture, one request can trigger multiple events and traverse multiple consumers. `correlation-id` helps link messages belonging to the same business flow; `trace-id` helps the tracing system link spans across services.

Example processing flow:

```text
HTTP request
    |
    | trace-id = T1, correlation-id = C1
    v
Order service
    |
    | Kafka record + trace-id T1 + correlation-id C1
    v
orders.events
    |
    v
Billing consumer
    |
    | new record continues carrying correlation-id C1
    v
payments.events
    |
    v
Notification consumer
```

When producing the next event, the application should continue propagating the correlation ID per business convention. For trace IDs, use a compatible tracing/instrumentation library to inject and extract context according to standards like W3C Trace Context; manually copying a `trace-id` string does not automatically create spans or complete propagation.

If a consumer forwards a record to another topic, decide which headers are preserved, modified, or removed. Avoid blindly copying every internal header because they may contain information meaningful only in the source service.

## 8. Naming conventions, encoding, and header size

Choose consistent, clear header names and avoid colliding with framework-managed headers. Example:

| Header | Recommended encoding/value | Purpose |
|---|---|---|
| `trace-id` | UTF-8 string | Link distributed traces |
| `correlation-id` | UTF-8 string | Correlate business flows |
| `event-type` | UTF-8 string | Event type name |
| `schema-version` | UTF-8 string or explicitly encoded number | Payload contract version |
| `source-service` | UTF-8 string | Service originating the record |

Principles to apply:

- Standardize on lowercase and hyphens in custom header names.
- Use UTF-8 for text metadata and agree on decoding.
- Clearly specify units if a header carries a number, such as milliseconds or seconds.
- Do not use headers to carry large payloads; business data belongs in the value.
- Avoid storing passwords, access tokens, session cookies, or sensitive personal data in headers.
- Keep the number and total size of headers small because they increase record/batch size as well as transmission and storage overhead.

Headers are not free storage. Large records can hit message/batch size limits or increase network and memory pressure. Measure actual sizes and set limits at the producer, broker, and consumer layers appropriate for the system.

## 9. When to choose ProducerRecord, when to choose Spring Message?

| Requirement | Appropriate approach |
|---|---|
| Want exact control over raw header bytes | `ProducerRecord` and `RecordHeader` |
| Need multiple headers with the same name | `ProducerRecord` |
| Need to specify topic/key/partition/timestamp with headers | `ProducerRecord` or Spring Message with matching `KafkaHeaders` |
| Application already uses Spring Messaging | `Message<?>` and `KafkaHeaders` |
| Want to transfer Java object metadata via mapper | `Message<?>` with explicitly configured converter/header mapper |
| Need simple interoperability with non-Spring consumers | UTF-8 or byte Kafka headers per shared contract |

Both approaches end up producing a Kafka `ProducerRecord`. Which one to choose depends on whether the application wants to work directly with the Kafka client API or leverage the Spring Messaging model.

## 10. Testing sending headers

When testing producers, verify both the record payload and its headers. With integration tests using real Kafka or an embedded broker, a consumer can receive `ConsumerRecord` and assert:

```java
assertThat(record.key()).isEqualTo("payment-9001");
assertThat(record.value()).contains("paymentId");

Header traceHeader = record.headers().lastHeader("trace-id");
assertThat(traceHeader).isNotNull();
assertThat(new String(traceHeader.value(), StandardCharsets.UTF_8))
        .isEqualTo("trace-abc");
```

Beyond checking values, verify:

1. Header names are spelled accurately and follow conventions.
2. Byte values have the right encoding.
3. Headers are preserved through converters/serializers.
4. Consumers handle missing, null, or duplicate headers.
5. Framework headers like type metadata are not unintentionally overwritten by custom mappers.

If sending via `Message<?>`, test the active converter/header mapper because custom header mapping depends on that configuration. If sending via `ProducerRecord`, you can inspect raw header bytes directly before sending and when the consumer receives the record.

## 11. Common misconceptions

1. **Thinking headers are part of the JSON value.** Kafka stores headers separately alongside key/value.
2. **Passing a Java object directly into a Kafka header.** Kafka headers only store bytes; encode explicitly or use a mapper.
3. **Thinking custom headers automatically determine the partition.** The default partitioner primarily uses the key; headers only participate if a custom partitioner reads them.
4. **Confusing Spring Message headers with Kafka record headers.** Converters and header mappers must convert between the two models.
5. **Assuming header names are always unique.** Kafka allows multiple headers with the same name; consumers must pick an appropriate reading strategy.
6. **Using headers to hold large payloads or secrets.** Headers increase record size and may appear in logs or admin tools.
7. **Thinking a trace ID automatically enables distributed tracing.** Standards-compliant instrumentation and context propagation are required.
8. **Thinking returning from `KafkaTemplate.send()` means the record is written.** You must observe the future/result and handle asynchronous errors.

Sending headers with `KafkaTemplate` allows metadata to travel with records from producer to consumer. Use `ProducerRecord` when byte-level control and duplicate headers are needed; use Spring `Message<?>` when integrating with Spring Messaging and `KafkaHeaders`. Whichever you choose, align on header names, encoding, and semantics, and verify the converter/header mapper so consumers receive the exact metadata intended.
