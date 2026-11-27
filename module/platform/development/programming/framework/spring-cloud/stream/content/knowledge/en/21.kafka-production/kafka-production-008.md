# Header Mapper and Interoperability with Non-Spring Kafka Applications

A Kafka record has a payload, a key, and a set of headers. When a Spring Cloud Stream application sends a `Message<T>`, the binder must map Spring's `MessageHeaders` to Kafka's byte-based headers. When receiving a record, the binder performs the reverse mapping to construct a message for the function or consumer.

Kafka applications written in plain Java, Python, Go, or another framework do not automatically understand Spring's internal type conventions. Therefore, when multiple platforms communicate over a topic, headers need stable names, clear byte types, and published encoding rules. A header mapper is the translation layer between the two models; it is not a schema registry and does not replace payload contract design.

This lesson builds a header contract readable by both Spring Cloud Stream and standard Kafka clients, configures header filtering, handles data types, and tests bidirectional interoperability.

## 1. Distinguishing Kafka records, Spring Messages, and headers

A Kafka record contains a key, value, and headers. Each Kafka header has a string name and a `byte[]` value. A record may contain multiple headers with the same name.

Spring Messaging represents a message with a payload and `MessageHeaders`, where header values can be Strings, numbers, objects, or Spring types. Consequently, the binder must convert header values to bytes when publishing and restore appropriate types when consuming.

~~~text
Spring Cloud Stream                         Apache Kafka
+---------------------------+                +---------------------------+
| Message<T>                |                | ProducerRecord<K, V>      |
|                           |                |                           |
| payload: T  --------------+--------------> | value: byte[]             |
|                           |  serializer    |                           |
| headers: MessageHeaders --+--------------> | headers: key + byte[]     |
|                           | header mapper  |                           |
| KafkaHeaders.KEY ---------+--------------> | record key                |
+---------------------------+                +---------------------------+
                                                           |
                                                           v
                                                Non-Spring Kafka app
                                                reads value and header bytes
~~~

Concepts that should not be confused:

| Component | Meaning | Example |
|---|---|---|
| Payload/value | Main event content | OrderCreated JSON |
| Record key | Identifier used for partitioning/compaction | `order-1001` |
| Kafka header | Byte-based metadata attached to a record | `event-type=OrderCreated` |
| Spring MessageHeaders | Metadata in Spring's abstraction | `correlation-id`, `contentType` |
| Header mapper | Converts between Spring headers and Kafka headers | `KafkaHeaderMapper` |
| Payload serializer/converter | Converts payload to bytes and back | JSON serializer/converter |

A Kafka record key is not a custom header. In Spring, the key is typically set via `KafkaHeaders.KEY` when sending and read via the received key header. Do not invent a `record-key` metadata header and expect Kafka to use it for partitioning.

## 2. Kafka headers are bytes, not Java objects

The Kafka API represents a header with two properties:

~~~java
public interface Header {
    String key();
    byte[] value();
}
~~~

A plain Java application can read a header and decode it directly:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.common.header.Header;

Header header = record.headers().lastHeader("correlation-id");

if (header != null && header.value() != null) {
    String correlationId =
        new String(header.value(), StandardCharsets.UTF_8);
}
~~~

Kafka does not store the Java type of a header. If a producer sends a string, it must encode that string into bytes; the consumer must know to use UTF-8 or an agreed encoding to decode it. If a producer sends JSON, Avro, or binary bytes in a header, the consumer must likewise know the corresponding contract.

Therefore, cross-platform headers should favor simple scalar values:

- UTF-8 strings for event type, correlation ID, tenant ID, or trace context.
- Integers formatted as strings or a specified byte representation.
- Timestamps in ISO-8601 UTC or epoch millis, standardized on one format.
- Booleans as lowercase `true`/`false`.
- Do not use Java native serialization or Java class names as a cross-platform contract.

Choose stable header names, such as `event-type`, `event-version`, `correlation-id`, `causation-id`, and `traceparent`. Avoid names likely to collide with internal headers like `id` and `timestamp`, or casing variants like `ID` and `Id`.

## 3. What does a header mapper do?

Spring Kafka provides the `KafkaHeaderMapper` abstraction with two directions:

~~~java
public interface KafkaHeaderMapper {
    void fromHeaders(MessageHeaders headers, Headers target);
    void toHeaders(Headers source, Map<String, Object> target);
}
~~~

- `fromHeaders`: converts `MessageHeaders` into Kafka `Headers` when publishing.
- `toHeaders`: converts Kafka `Headers` into a map to build Spring `MessageHeaders` when consuming.

The Spring Cloud Stream Kafka binder uses a header mapper to perform this translation. In typical cases, the binder provides a default mapper. A custom mapper is only needed when you have explicit requirements such as raw UTF-8 headers, allowlists, trusted packages, or special contracts with non-Spring applications.

A mapper can decide:

1. Which headers are allowed to be sent to Kafka.
2. Which headers are read into the application.
3. How values are encoded into bytes.
4. How bytes are decoded back into Strings or other types.
5. Whether repeated headers with the same name are supported.
6. Whether Spring JSON type metadata is converted.

If you write a custom mapper, you must implement both outbound and inbound directions. A one-way mapper can cause headers to appear at the producer but vanish when read by the consumer, or vice versa.

## 4. Shared header contract for Spring and Kafka clients

Suppose an order service emits an `OrderCreated` event. The JSON payload holds business data, while headers carry metadata for routing, tracing, and observability.

~~~text
Topic: orders.created
Key: order-1001
Value:
{
  "orderId": "order-1001",
  "customerId": "customer-42",
  "total": 125000,
  "currency": "VND"
}

Headers:
  event-type      = OrderCreated
  event-version   = 1
  correlation-id  = corr-checkout-9001
  causation-id    = cmd-place-order-9001
  traceparent     = 00-<trace-id>-<parent-id>-01
~~~

A contract table should specify names, encodings, and whether each header is required:

| Header | Byte type/encoding | Required | Purpose |
|---|---|---|---|
| `event-type` | UTF-8 string | Yes | Stable event name |
| `event-version` | UTF-8 decimal integer | Yes | Contract version |
| `correlation-id` | UTF-8 string | Per business flow | Links events across a journey |
| `causation-id` | UTF-8 string | Per event | References the direct cause |
| `traceparent` | W3C Trace Context ASCII | When tracing enabled | Links distributed traces |
| `tenant-id` | UTF-8 string | Per tenancy model | Routes or partitions by tenant |

These headers should not contain full payloads or sensitive data. Kafka headers are stored alongside the record and may be read by multiple applications; never place access tokens, passwords, session cookies, or secrets in them.

If a value requires a complex schema or multiple fields, put it in the payload/envelope. Headers should stay short, stable, and meaningful across platforms.

## 5. Sending headers from Spring Cloud Stream

A function can return `Message<T>` to attach metadata alongside the payload:

~~~java
import java.math.BigDecimal;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class OrderProducer {

    @Bean
    Supplier<Message<OrderCreated>> orderCreated() {
        return () -> MessageBuilder
            .withPayload(new OrderCreated(
                "order-1001",
                "customer-42",
                new BigDecimal("125000"),
                "VND"
            ))
            .setHeader("event-type", "OrderCreated")
            .setHeader("event-version", "1")
            .setHeader("correlation-id", "corr-checkout-9001")
            .setHeader("causation-id", "cmd-place-order-9001")
            .build();
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total,
        String currency
    ) {}
}
~~~

Output binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: orderCreated

    stream:
      bindings:
        orderCreated-out-0:
          destination: orders.created
          content-type: application/json

      kafka:
        bindings:
          orderCreated-out-0:
            producer:
              header-patterns: "event-type,event-version,correlation-id,causation-id"
~~~

`header-patterns` is a pattern list controlling which Spring headers are mapped to Kafka. Patterns can have leading or trailing wildcards and can be negated with `!`; the first matching rule wins. By default, the Kafka binder maps most headers except `id` and `timestamp`. For cross-platform communication, an explicit allowlist keeps the contract much easier to control.

The header mapper handles metadata only. `content-type: application/json` together with message converters handles the payload. Do not assume declaring a content type automatically defines how all headers are encoded.

## 6. Reading headers in a Spring Cloud Stream consumer

A consumer accepts `Message<T>` when it needs to access metadata:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
public class OrderConsumer {

    @Bean
    Consumer<Message<OrderCreated>> processOrder() {
        return message -> {
            OrderCreated event = message.getPayload();

            String eventType = message.getHeaders()
                .get("event-type", String.class);
            String correlationId = message.getHeaders()
                .get("correlation-id", String.class);

            // Process event and log metadata.
        };
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        java.math.BigDecimal total,
        String currency
    ) {}
}
~~~

Input binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-projection
          content-type: application/json
~~~

The actual runtime type of a header after mapping depends on the mapper and configuration. With a raw mapper, the header may be `byte[]`; with a string-converting mapper, the value may be `String`; with JSON type mapping, the value may be restored to a trusted Java type. When integrating with non-Spring applications, choose a raw byte/string contract to avoid coupling to Java types.

Do not cast directly to `String` without verifying that the mapper returns a `String`. You can inspect the value safely:

~~~java
import java.nio.charset.StandardCharsets;

Object raw = message.getHeaders().get("correlation-id");

String correlationId;
if (raw instanceof String value) {
    correlationId = value;
} else if (raw instanceof byte[] bytes) {
    correlationId = new String(bytes, StandardCharsets.UTF_8);
} else {
    throw new IllegalArgumentException(
        "Unsupported correlation-id header type"
    );
}
~~~

## 7. Plain Java Kafka application sending records to Spring

A producer that does not use Spring needs only the Kafka client. It builds the payload per the JSON contract and adds byte-encoded headers:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;

Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("key.serializer",
    "org.apache.kafka.common.serialization.StringSerializer");
properties.put("value.serializer",
    "org.apache.kafka.common.serialization.StringSerializer");

try (KafkaProducer<String, String> producer =
        new KafkaProducer<>(properties)) {

    String json = """
        {
          "orderId": "order-1002",
          "customerId": "customer-77",
          "total": 85000,
          "currency": "VND"
        }
        """;

    ProducerRecord<String, String> record =
        new ProducerRecord<>("orders.created", "order-1002", json);

    record.headers().add(new RecordHeader(
        "event-type",
        "OrderCreated".getBytes(StandardCharsets.UTF_8)
    ));
    record.headers().add(new RecordHeader(
        "event-version",
        "1".getBytes(StandardCharsets.UTF_8)
    ));
    record.headers().add(new RecordHeader(
        "correlation-id",
        "corr-checkout-9002".getBytes(StandardCharsets.UTF_8)
    ));

    producer.send(record).get();
}
~~~

Non-Spring applications do not need to emit `spring_json_header_types` when sending agreed raw string headers. The Spring consumer uses an appropriate mapper to read bytes back into Strings.

The payload is serialized with `StringSerializer` because the example builds a JSON String. If the payload is a Java object, an appropriate JSON/Avro/Protobuf serializer is required; do not pass an arbitrary object to `StringSerializer`.

## 8. Plain Java Kafka application reading records from Spring

A Kafka client consumer receives `ConsumerRecord` and reads payload and headers independently:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

private void handle(ConsumerRecord<String, String> record) {
    Header eventTypeHeader =
        record.headers().lastHeader("event-type");

    Header correlationHeader =
        record.headers().lastHeader("correlation-id");

    String eventType = eventTypeHeader == null
        ? null
        : new String(
            eventTypeHeader.value(),
            StandardCharsets.UTF_8
        );

    String correlationId = correlationHeader == null
        ? null
        : new String(
            correlationHeader.value(),
            StandardCharsets.UTF_8
        );

    String orderId = record.key();
    String jsonPayload = record.value();

    // Deserialize JSON per published schema and process.
}
~~~

The Kafka client reads headers written by the Spring mapper as long as values are encoded according to a compatible contract. It does not need Spring, Jackson, or the producer application's packages to read raw UTF-8 bytes.

When receiving multiple headers with the same name, `lastHeader(name)` returns the last occurrence. If the contract permits repeated headers, the consumer must iterate over `record.headers().headers(name)` and define ordering/semantics. Do not assume every Spring mapper preserves multiple values for the same header name; that behavior depends on the mapper and version.

## 9. JSON headers and Spring type metadata

`JsonKafkaHeaderMapper` can serialize complex header values as JSON. To restore the original type, the mapper can add a special header named `spring_json_header_types`, containing a mapping from header names to Java types.

Conceptual example:

~~~text
Kafka record headers:
  correlation-id            -> UTF-8 bytes
  retry-count               -> JSON bytes
  spring_json_header_types  -> {"retry-count":"java.lang.Integer"}
~~~

Compatible Spring applications can use this metadata to restore types. Plain Kafka clients can still read the bytes, but they do not know what `spring_json_header_types` means unless they implement that convention themselves. Such clients can ignore that metadata header and read the published contract headers.

For polyglot integrations, avoid requiring consumers to understand Java class names like `com.example.OrderMetadata`. Instead:

- Use raw UTF-8 for simple metadata.
- Define a language-independent schema if a header needs structure.
- Place complex data in the payload with a well-defined schema.
- Do not use Java native serialization.
- Do not rely on `spring_json_header_types` as a required part of the public contract.

## 10. Using rawMappedHeaders to transmit UTF-8 strings

Spring Kafka supports configuring String headers to map directly to bytes instead of JSON. `rawMappedHeaders` is a map from header name to boolean:

- `true`: outbound Strings are encoded to bytes; inbound bytes are decoded to Strings using the configured charset.
- `false`: inbound bytes are not automatically converted to Strings.
- Headers absent from the map keep the mapper's raw handling behavior.

Example with a Spring Kafka mapper:

~~~java
import java.util.Map;

import org.springframework.kafka.support.DefaultKafkaHeaderMapper;
import org.springframework.kafka.support.KafkaHeaderMapper;
import org.springframework.context.annotation.Bean;

@Bean
KafkaHeaderMapper kafkaHeaderMapper() {
    DefaultKafkaHeaderMapper mapper =
        new DefaultKafkaHeaderMapper(
            "!id",
            "!timestamp",
            "event-*",
            "correlation-id",
            "causation-id",
            "traceparent"
        );

    mapper.setRawMappedHeaders(Map.of(
        "event-type", true,
        "event-version", true,
        "correlation-id", true,
        "causation-id", true,
        "traceparent", true
    ));

    return mapper;
}
~~~

This example illustrates configuring a Spring Kafka mapper. When using it with the Kafka binder, register the mapper with the exact bean name and configure `spring.cloud.stream.kafka.binder.header-mapper-bean-name` per your binder version. If using `BinderHeaderMapper` provided by the binder, use the API appropriate for that version. Do not add a custom mapper bean if the default mapper already satisfies the contract.

Place the `kafkaHeaderMapper()` method inside a `@Configuration` class so Spring registers the bean. This snippet illustrates creating the mapper; when using the binder, configure the bean name referenced by the binder rather than assuming any `KafkaHeaderMapper` bean is picked up automatically.

For data from untrusted sources, do not widen trusted packages with wildcards. JSON header mappers can reconstruct objects from type metadata; trust only the specific packages needed. The safest and most interoperable approach remains simple strings/bytes, requiring no Java object deserialization from headers.

## 11. Custom KafkaHeaderMapper with a raw-bytes allowlist

When you need an explicit byte contract and want no dependency on JSON type metadata, you can implement a mapper that permits only specific headers. The following example maps four String headers using UTF-8:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.springframework.kafka.support.KafkaHeaderMapper;
import org.springframework.messaging.MessageHeaders;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InteropHeaderMapperConfiguration {

    @Bean
    KafkaHeaderMapper interopHeaderMapper() {
        return new KafkaHeaderMapper() {
            @Override
            public void fromHeaders(
                    MessageHeaders source,
                    Headers target) {

                addString(source, target, "event-type");
                addString(source, target, "event-version");
                addString(source, target, "correlation-id");
                addString(source, target, "traceparent");
            }

            @Override
            public void toHeaders(
                    Headers source,
                    Map<String, Object> target) {

                copyString(source, target, "event-type");
                copyString(source, target, "event-version");
                copyString(source, target, "correlation-id");
                copyString(source, target, "traceparent");
            }
        };
    }

    private static void addString(
            MessageHeaders source,
            Headers target,
            String name) {

        Object value = source.get(name);
        if (value instanceof String text) {
            target.add(
                name,
                text.getBytes(StandardCharsets.UTF_8)
            );
        }
    }

    private static void copyString(
            Headers source,
            Map<String, Object> target,
            String name) {

        Header header = source.lastHeader(name);
        if (header != null && header.value() != null) {
            target.put(
                name,
                new String(
                    header.value(),
                    StandardCharsets.UTF_8
                )
            );
        }
    }
}
~~~

Set the bean name in binder configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          header-mapper-bean-name: interopHeaderMapper
~~~

This mapper acts as an allowlist: only those four headers are mapped. Other headers are not forwarded automatically. If the application needs `contentType`, trace baggage, or other metadata, add them intentionally to both the contract and the mapper.

The example uses `lastHeader` to pick the last value if a Kafka record carries multiple headers with the same name. If the contract needs to preserve multiple values, iterate over all matching headers and define how lists are placed into Spring `MessageHeaders`. Check the mapper's multi-value API and Spring Kafka version before deploying.

Do not configure multiple different mappers simultaneously without explicitly knowing which one the binder uses. `headerMapperBeanName` points to the bean chosen by the binder; check the bean name and startup logs if headers are not transferred as expected.

## 12. How do headerPatterns, headerMode, and native encoding differ?

Three settings are frequently confused:

| Setting | Controls | Does not control |
|---|---|---|
| `headerPatterns` | Which Spring headers the mapper sends to Kafka | Payload serializer |
| `headerMode` | Whether headers use middleware-native mechanisms or are embedded in payload | Java type of payload |
| `useNativeEncoding` / `useNativeDecoding` | Whether the Kafka client serializer/deserializer handles the payload | Header allowlist and encoding type |

Kafka supports native record headers. When exchanging messages with non-Spring Kafka clients, using native Kafka headers is the natural choice. `embeddedHeaders` is a mechanism for embedding metadata into the payload for middleware lacking native headers; standard Kafka clients will not automatically decode that embedded format.

Native headers have been supported by Kafka clients since version 0.11.0.0. If you must integrate with a very old client/binder, check version limits and the binder's legacy header mechanisms; do not apply legacy settings to modern Kafka systems unless specifically required for compatibility.

`useNativeEncoding=true` delegates payload serialization to the Kafka client serializer. Payload marshaling then no longer relies on the binding's `content-type`; consumers must configure a matching deserializer. This does not mean Kafka headers are automatically converted by that same serializer. Payload and headers are two independent conversion paths.

When using native encoding, a JSON String payload can use `StringSerializer`, for instance; if using objects, choose a serializer with a shared contract such as Avro, JSON, or Protobuf. Do not enable `useNativeEncoding` merely to solve header issues.

## 13. Kafka key, topic, partition, and metadata headers

Certain Spring headers actually represent Kafka record properties:

| Spring header | Kafka meaning |
|---|---|
| `KafkaHeaders.KEY` | Outbound record key |
| `KafkaHeaders.RECEIVED_KEY` | Inbound record key |
| `KafkaHeaders.TOPIC` | Outbound/routing topic when configuration supports it |
| `KafkaHeaders.PARTITION` | Explicit outbound partition when applicable |
| `KafkaHeaders.RECORD_METADATA` | Send result metadata, including topic/partition/offset |

These properties must not be confused with custom headers such as `event-type`. The Kafka binder handles key, topic, and partition with dedicated semantics. A non-Spring Kafka app reads them via `ConsumerRecord.key()`, `topic()`, `partition()`, and `offset()`, rather than looking inside `record.headers()`.

When you need to preserve an incoming key through a function and emit a new record, pass the key using the appropriate key header. With reactive functions, the application must explicitly copy needed metadata/keys to the output message; do not assume all headers are retained automatically.

## 14. Interoperating with Python, Go, and other frameworks

Different languages can still read Kafka headers if they agree on names and byte encoding. For example, a Python consumer using a Kafka client can read the list of `(name, bytes)` pairs and decode them:

~~~python
headers = dict(record.headers() or [])

event_type = headers.get("event-type")
if event_type is not None:
    event_type = event_type.decode("utf-8")

correlation_id = headers.get("correlation-id")
if correlation_id is not None:
    correlation_id = correlation_id.decode("utf-8")
~~~

This snippet illustrates decoding raw byte headers. If a record contains multiple headers with the same name, converting to a dict can drop duplicate keys; iterate over the header list instead of a dict when the contract allows repeated headers.

For Go or other frameworks, the principle is the same: read the header byte value, decode UTF-8 per the contract, and process the payload using its own schema. Never require non-Spring applications to understand Java packages or Spring Messaging.

## 15. Security and reliability of headers

Headers coming from Kafka are external data. Do not trust types or values merely because the producer is an internal service.

- Map only necessary headers; use an allowlist rather than forwarding all metadata unchecked.
- Do not trust all packages when a JSON mapper reconstructs objects from type metadata.
- Check header lengths and total metadata size limits to avoid oversized records.
- Validate enums, versions, tenant IDs, and trace context before use.
- Do not use headers to carry secrets or tokens.
- Do not make headers the sole source for critical business rules if the payload contract should carry that information.
- Log headers selectively; avoid logging sensitive data.
- Do not treat a correlation ID or tenant ID as proof of identity authentication.

If a required header is missing or malformed, the consumer should raise an observable contract error. If an optional header is missing, define a clear fallback. Do not generate a fresh correlation ID in every service if the goal is to trace a single journey.

## 16. Testing bidirectional interoperability

A thorough integration test suite should cover at least three cases:

1. Spring producer sends payload and headers; a plain Kafka client reads the exact expected bytes.
2. Plain Kafka client sends a record with raw UTF-8 headers; a Spring Cloud Stream consumer reads the expected Strings.
3. Headers outside the allowlist are filtered out per policy; the payload still reads normally.

Test matrix:

| Scenario | Result to verify |
|---|---|
| Spring sends `event-type=OrderCreated` | Kafka record contains accurate UTF-8 header bytes |
| Java client sends `correlation-id` | Spring consumer receives String per mapper |
| Missing header | Consumer handles per optional/required policy |
| Header bytes are not valid UTF-8 | Validation reports an error or retains raw bytes without arbitrary decoding |
| Header has Java object type | Non-Spring consumer does not depend on class names |
| Duplicate header names | Both sides apply the same last/first/all rule |
| Header not in allowlist | Not forwarded unintentionally |
| Payload uses native encoding | Serializer/deserializer align; headers remain readable independently |
| Message passes through a function | Needed headers are explicitly copied |
| Older Kafka client | Verify native header support for the version |

You can use Testcontainers Kafka to run a real broker. Send a record with a plain `KafkaProducer`, read it with a Spring consumer, then send back from Spring and read with a plain `KafkaConsumer`. Unit tests on a mapper only prove local conversion; integration tests prove the binder actually writes/reads native Kafka headers.

## 17. Diagnostic checklist when headers are missing or mistyped

When a consumer does not see a header, check in order:

1. Did the producer actually set the Spring header before sending?
2. Are the header name spelling and casing exact?
3. Does the producer binding have `headerPatterns` excluding that header?
4. Is a custom mapper replacing the default mapper and dropping the header?
5. Does the mapper convert Strings to UTF-8 bytes?
6. Is the consumer binding using native Kafka headers or expecting embedded headers?
7. Does the consumer mapper read the right header name and decode with the right encoding?
8. Is the header colliding with framework-reserved names like `id`/`timestamp` or similar names?
9. Is the consumer reading a repeated header with `lastHeader` while the producer sent multiple values?
10. Is a record key or topic/partition metadata being confused with a custom header?

When debugging, use the Kafka console consumer or a small consumer client to print header names and bytes in hex/UTF-8. Compare the raw record against Spring `MessageHeaders`. If the Kafka record already carries the header but Spring does not see it, focus on the mapper/converter. If the record lacks the header, check producer patterns, custom mappers, and how the `Message` is constructed.

## 18. Practice sequence and completion criteria

Work through the exercise using the `orders.created` topic:

1. Define a JSON payload contract and five headers: `event-type`, `event-version`, `correlation-id`, `causation-id`, `traceparent`.
2. Write a Spring Supplier returning `Message<OrderCreated>` with those headers.
3. Configure Kafka producer `header-patterns` as an allowlist.
4. Use Kafka console/plain client to read the record and confirm the headers are UTF-8 bytes.
5. Write a plain Kafka Java producer sending a JSON String and raw header bytes.
6. Use a Spring Cloud Stream consumer to receive the message and read headers via the mapper.
7. Try a custom mapper with an allowlist and raw UTF-8.
8. Send missing headers, invalid encodings, and duplicate header names to test policies.
9. Enable native payload encoding in a separate test environment; configure matching serializers/deserializers and confirm headers remain independent.
10. Run bidirectional integration tests against a real broker.
11. Document the versions of Spring Cloud Stream, Spring Kafka, and kafka-clients along with the chosen header contract.

You have completed the lesson when you can explain the difference between Spring `MessageHeaders` and Kafka `Headers`; configure a header mapper; reliably send/receive raw bytes; enable non-Spring Kafka clients to read metadata; and diagnose lost, mistyped, or filtered headers.

## 19. Official references

- [Spring Cloud Stream — Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html) — Kafka binder, header mapper, and producer/consumer configuration.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html) — `headerMapperBeanName`, producer properties, and binder configuration.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — `headerMode`, `useNativeEncoding`, and `useNativeDecoding`.
- [Spring Cloud Stream — Kafka Tips and Tricks](https://docs.spring.io/spring-cloud-stream/reference/4.3/kafka/kafka_tips.html) — custom Kafka header mapper examples and special headers.
- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html) — KafkaHeaderMapper, JSON type metadata, rawMappedHeaders, and trusted packages.
- [Apache Kafka — Record Headers API](https://kafka.apache.org/40/javadoc/org/apache/kafka/common/header/Headers.html) — API for adding, reading, and iterating over Kafka headers.
