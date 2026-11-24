# Mapping byte[] headers in Spring Kafka

A Kafka header always has a simple structure: a header name as a `String` and a value as a `byte[]`. Kafka does not inherently understand whether that value is UTF-8, an integer, JSON, or a Java object. Producer and consumer must agree on how to encode and decode it.

In Spring Kafka, `KafkaHeaderMapper` maps between Kafka `Headers` and Spring `MessageHeaders`. When you need to keep headers in raw byte form, `SimpleKafkaHeaderMapper` is the right choice. This mapper sends `byte[]` headers directly and puts received headers into the Spring Message as byte arrays; you can additionally configure specific header names to convert back and forth between `String` and `byte[]`.

## 1. Kafka Header structure

Kafka defines a header with an interface having two methods:

```java
public interface Header {
    String key();
    byte[] value();
}
```

`key()` is the header name; `value()` is a byte array. For example, a record might carry:

```text
correlation-id -> [byte values of "corr-81a2"]
schema-version -> [byte values of "2"]
signature      -> [binary bytes]
```

Kafka only stores bytes. When reading `correlation-id`, the consumer must know the producer used UTF-8 to convert the string to bytes. For `signature`, the consumer needs to know the agreed cryptographic algorithm and binary format.

Kafka headers have important characteristics:

- The header name is a string; the value is `byte[]` or may be `null` per the record API.
- A record can contain multiple headers with the same name.
- Header order is preserved in the `Headers` collection.
- Kafka does not automatically deserialize headers using the record's `value-deserializer`.
- Headers do not replace the key and do not determine partition routing.

## 2. Why is byte[] mapping needed?

Headers typically carry small metadata for tracing or controlling processing flows, for example:

| Header | Recommended format | Purpose |
|---|---|---|
| `correlation-id` | UTF-8 | Link logs and traces across services |
| `event-id` | UTF-8 | Identify the event for deduplication |
| `schema-version` | UTF-8 or binary number per contract | Identify schema version |
| `content-type` | UTF-8 | Describe payload format |
| `signature` | Binary | Signature or checksum per agreed protocol |
| `traceparent` | UTF-8 | Propagate trace context per tracing standard |

Keeping headers as bytes allows Java, Go, Python, or .NET applications to exchange metadata without depending on specific Java types or Spring's internal JSON format.

For example, a Go consumer can read `correlation-id` as bytes and decode UTF-8. It does not need to understand `spring_json_header_types` or Java class names embedded in Spring metadata.

## 3. Writing byte[] headers directly via Kafka API

When creating a `ProducerRecord`, headers can be added directly via `headers().add(...)`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;

ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>("orders.created.v1", "order-42", event);

record.headers().add(
        new RecordHeader(
                "correlation-id",
                "corr-81a2".getBytes(StandardCharsets.UTF_8)));

record.headers().add(
        new RecordHeader(
                "schema-version",
                "2".getBytes(StandardCharsets.UTF_8)));

kafkaTemplate.send(record);
```

Key and value are still handled by Kafka serializers. Headers are already byte arrays so they do not pass through `value-serializer` or `key-serializer`.

If creating a record with `KafkaTemplate<String, byte[]>`, the producer factory needs matching serializers, such as `StringSerializer` for key and `ByteArraySerializer` for value. The payload serializer type does not change how Kafka stores headers.

## 4. Reading byte[] headers directly from ConsumerRecord

The consumer can retrieve a header with `lastHeader(name)`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

@KafkaListener(topics = "orders.created.v1")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    Header header = record.headers().lastHeader("correlation-id");

    String correlationId = header == null || header.value() == null
            ? null
            : new String(header.value(), StandardCharsets.UTF_8);

    // Process event and correlation ID.
}
```

`lastHeader(name)` returns the last header with the matching name or `null` if absent. When the contract allows multiple headers with the same name, use `headers(name)` to read all of them rather than taking only the last value.

Do not use `new String(bytes)` without specifying a charset. The result then depends on the default charset of the machine running the application. For text metadata, agree on UTF-8 and explicitly specify `StandardCharsets.UTF_8` on both sides.

## 5. Converting numbers and binary data

Not every header is a string. If you need to pass a `long` number, you can use a fixed binary format:

```java
import java.nio.ByteBuffer;

long createdAtEpochMillis = 1_790_000_000_000L;
byte[] timestampBytes = ByteBuffer.allocate(Long.BYTES)
        .putLong(createdAtEpochMillis)
        .array();

record.headers().add(new RecordHeader("created-at", timestampBytes));
```

The consumer reads according to the exact agreed format:

```java
Header header = record.headers().lastHeader("created-at");
if (header != null && header.value() != null
        && header.value().length == Long.BYTES) {
    long createdAt = ByteBuffer.wrap(header.value()).getLong();
}
```

`ByteBuffer` defaults to big-endian. If the protocol requires a different byte order, producer and consumer must set the same byte order. Always check length before reading to avoid `BufferUnderflowException` or misinterpreting data.

For UUIDs, you can agree on a UTF-8 string representation or 16 binary bytes. For signatures/checksums, preserve the bytes from the cryptographic library and do not convert them to a string without an explicit encoding specification.

## 6. SimpleKafkaHeaderMapper

`SimpleKafkaHeaderMapper` is the mapper for cases where you want simple header mapping without JSON-encoding Java types. Basic behavior:

- Outbound: only headers with `byte[]` values are mapped directly to Kafka headers.
- Inbound: Kafka headers are mapped as-is into `byte[]` in the Spring Message.
- Selected headers can be configured to convert `String` to bytes when sending and bytes to `String` when receiving.
- Special Spring headers representing `ProducerRecord`/`ConsumerRecord` properties are normally not sent as custom Kafka headers.

Example configuring a converter with a raw byte mapper:

```java
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;

SimpleKafkaHeaderMapper headerMapper = new SimpleKafkaHeaderMapper();
MessagingMessageConverter converter = new MessagingMessageConverter();
converter.setHeaderMapper(headerMapper);
```

This converter can be attached to the listener container factory:

```java
factory.setRecordMessageConverter(converter);
```

Or to `KafkaTemplate`:

```java
kafkaTemplate.setMessageConverter(converter);
```

As a result, the listener can receive `Message<?>` and access custom headers as byte arrays. When direct use of `ConsumerRecord.headers()` is needed, you can receive `ConsumerRecord` without a message mapper.

## 7. Reading byte[] headers via Spring Message

When a listener receives `Message<OrderCreated>` and uses `SimpleKafkaHeaderMapper`, custom headers typically have type `byte[]`:

```java
@KafkaListener(
        topics = "orders.created.v1",
        groupId = "order-projection",
        containerFactory = "ordersListenerContainerFactory"
)
public void onOrder(Message<OrderCreated> message) {
    byte[] rawCorrelationId = message.getHeaders()
            .get("correlation-id", byte[].class);

    String correlationId = rawCorrelationId == null
            ? null
            : new String(rawCorrelationId, StandardCharsets.UTF_8);

    OrderCreated event = message.getPayload();
    // Process event.
}
```

If the header does not exist, `get(...)` returns `null`. If headers can be sent by a producer that does not adhere to the contract, check the type and length before decoding.

Another way is to receive the header directly via `@Header`:

```java
@KafkaListener(topics = "orders.created.v1")
public void onOrder(
        @Payload OrderCreated event,
        @Header(name = "correlation-id", required = false) byte[] correlationBytes) {

    String correlationId = correlationBytes == null
            ? null
            : new String(correlationBytes, StandardCharsets.UTF_8);
}
```

Set `required = false` if the header is optional. If the header is required by the contract, you can leave it required and handle missing-header errors with appropriate validation/error handling.

## 8. Selectively converting byte[] headers to String

If you want most headers to remain `byte[]` while selected text headers are converted to `String`, configure `rawMappedHeaders` on `AbstractKafkaHeaderMapper`:

```java
SimpleKafkaHeaderMapper mapper = new SimpleKafkaHeaderMapper();
mapper.setRawMappedHeaders(Map.of(
        "correlation-id", true,
        "event-id", true,
        "signature", false
));
```

Meaning:

| Header | Boolean | Outbound from Spring Message | Inbound into Spring Message |
|---|---:|---|---|
| `correlation-id` | `true` | String is encoded into bytes using mapper charset | bytes are decoded into String |
| `event-id` | `true` | String is encoded into bytes using mapper charset | bytes are decoded into String |
| `signature` | `false` | String if present is still written as raw bytes; byte[] is preserved | Value is kept as byte[] |
| Header not in map | Not configured | byte[] is mapped directly; String does not automatically become raw header | Value is mapped as raw byte[] |

`true` does not mean Kafka stores a String. Kafka still stores a byte array; the boolean simply instructs the mapper to convert bytes to String when receiving. `false` keeps the received value as raw bytes.

The mapper's default charset is UTF-8. If the contract uses another charset, you can configure the charset on the mapper, but producer and consumer must use the same charset.

## 9. Using mapAllStringsOut when sending all String headers as raw bytes

`setMapAllStringsOut(true)` instructs the mapper to convert all outbound String headers into byte arrays using the configured charset. This can be suitable when all text headers need to be exchanged with non-Spring systems.

```java
SimpleKafkaHeaderMapper mapper = new SimpleKafkaHeaderMapper();
mapper.setMapAllStringsOut(true);
```

However, this configuration has a broader scope than `rawMappedHeaders`. If some headers need to remain other types or should not appear on the wire, use explicit name and pattern mapping. Do not indiscriminately map Spring internal headers like `id` and `timestamp` into custom Kafka headers.

For inter-service protocols, an allowlist by header name is usually easier to review and more stable than sending every String header from a Spring Message.

## 10. Comparing SimpleKafkaHeaderMapper and JSON header mapper

Spring Kafka has two main mapping directions:

| Criterion | `SimpleKafkaHeaderMapper` | JSON header mapper |
|---|---|---|
| Outbound values | Primarily maps byte[] directly; optional String-to-byte | JSON-encodes rich header types |
| Inbound values | Defaults to keeping byte[]; can decode selected headers to String | Uses type metadata to convert headers back to corresponding types |
| Jackson dependency | Not needed for raw mapping | Requires Jackson for JSON mapping |
| Cross-language compatibility | Good when byte/encoding contract is clear | Non-Spring consumers must understand JSON header format to restore types |
| Suitable use cases | Trace ID, correlation ID, signatures, byte-encoded version codes | Richly typed object headers between Spring applications |

In older Spring Kafka versions, the JSON header mapper is usually named `DefaultKafkaHeaderMapper`. Newer documentation/APIs may use the name `JsonKafkaHeaderMapper`. Check the class present in your project's dependencies before copying code.

JSON header mappers can add metadata headers like `spring_json_header_types` to describe Java types. If the goal is a language-independent wire contract consisting only of header names and `byte[]`, `SimpleKafkaHeaderMapper` is usually a better fit.

## 11. Which headers are mapped and which are record metadata?

Not every Spring Message header is written as a Kafka header. Some `KafkaHeaders` represent record properties, for example:

| Spring header | Meaning when sending |
|---|---|
| `KafkaHeaders.TOPIC` | Target topic of the record |
| `KafkaHeaders.MESSAGE_KEY` | Key of the record |
| `KafkaHeaders.PARTITION` | Specified partition |
| `KafkaHeaders.TIMESTAMP` | Specified timestamp |
| `KafkaHeaders.RECEIVED_TOPIC` | Topic metadata of the received record |
| `KafkaHeaders.OFFSET` | Offset of the received record |

Headers such as topic, key, partition, and timestamp are used by the converter to build `ProducerRecord`; they do not necessarily become custom Kafka headers. Application headers like `correlation-id`, `event-id`, and `schema-version` are the metadata typically mapped via `KafkaHeaderMapper`.

Do not use custom header names that collide with Spring Kafka's reserved header names. Choose an explicit namespace for application metadata, such as `x-correlation-id` or `event-source`.

## 12. Duplicate header names and header order

Kafka `Headers` allows multiple headers with the same name. For example:

```java
record.headers().add("tag", "priority".getBytes(StandardCharsets.UTF_8));
record.headers().add("tag", "retryable".getBytes(StandardCharsets.UTF_8));
```

Reading all values:

```java
for (Header header : record.headers().headers("tag")) {
    byte[] value = header.value();
    // Process each value in order.
}
```

`lastHeader("tag")` only returns the last occurrence. If the contract needs to preserve every value, use the API that retrieves all headers and do not put them into a single-valued map without rules.

With Spring Message mapping, multi-value behavior depends on version and mapper. Spring Kafka 4.x documentation supports declaring patterns for multi-valued headers on the JSON mapper; if duplicate headers must be preserved, check your version's capabilities or receive `ConsumerRecord` to read native `Headers`. `SimpleKafkaHeaderMapper` is not designed to automatically turn a collection of `byte[]` into multiple Kafka headers.

## 13. Designing header contracts between services

Headers are part of the event exchange protocol. Document an explicit contract table:

| Header name | Required | Encoding | Example |
|---|---|---|---|
| `correlation-id` | Yes | UTF-8 | `corr-81a2` |
| `event-id` | Yes | UTF-8 | `evt-1001` |
| `schema-version` | Yes | UTF-8 decimal | `2` |
| `traceparent` | Per tracing policy | UTF-8 | W3C Trace Context |
| `signature` | Per security policy | Binary | Bytes per chosen algorithm |

For each header, agree on:

- Exact name, including lowercase/hyphen conventions.
- Encoding and byte order.
- Whether it is required or optional.
- Maximum length and how empty values are handled.
- Whether duplicate headers with the same name are allowed.
- Versioning rules when changing formats.
- Compatibility rules when producers and consumers are deployed at different times.

Do not pass an arbitrary Java object by serializing `toString()` and expecting another service to understand it. If a header needs complex structure, define a small versioned binary/JSON schema, or move that data into the event payload.

## 14. Checking and validating input headers

Consumers should not trust that every header exists or has valid encoding. Example:

```java
private String requiredUtf8Header(Headers headers, String name) {
    Header header = headers.lastHeader(name);
    if (header == null || header.value() == null || header.value().length == 0) {
        throw new IllegalArgumentException("Missing required header: " + name);
    }

    return StandardCharsets.UTF_8.decode(
            ByteBuffer.wrap(header.value())).toString();
}
```

This snippet illustrates checking a required header and decoding UTF-8. For data needing strict validation, use a `CharsetDecoder` configured with `CodingErrorAction.REPORT` to reject invalid byte sequences instead of accepting replacement characters.

Checks to include:

- Does the required header exist?
- Is the value null or empty?
- Does the byte length exceed contract limits?
- Is the encoding valid?
- Do UUIDs, numbers, timestamps, or signatures match the expected format?
- Are duplicate header names permitted?
- Is the header within the allowlist used by the application?

Missing or malformed headers should be treated as input data errors according to the consumer's retry/DLT policy; do not fabricate default values that could corrupt correlation or security context.

## 15. Size limits and security

Kafka headers are transmitted with the record and increase data size on the wire. Do not use headers to carry large payloads, long stack traces, large JSON objects, or unbounded binary data.

Operational principles:

- Keep headers small and containing only necessary metadata.
- Do not put passwords, bearer tokens, private keys, or sensitive data into headers.
- Do not log full byte arrays; log only header names, lengths, or masked values when needed.
- Check byte length before decoding or parsing.
- Use TLS/SASL and Kafka ACLs to protect transport and topic access permissions.
- If a header is a signature, verify the signature over the exact byte sequence specified by the contract; do not decode and re-encode before verifying.

Kafka headers are not an independent security boundary. Any producer with write permission on a topic can craft arbitrary headers; consumers must validate and authenticate critical content.

## 16. Testing bidirectional byte[] mapping

Test both the mapper directly and integration through the broker.

Example testing that `SimpleKafkaHeaderMapper` preserves raw bytes:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.messaging.MessageHeaders;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void shouldMapRawBytesWithoutChangingThem() {
    SimpleKafkaHeaderMapper mapper = new SimpleKafkaHeaderMapper();

    byte[] expected = new byte[] {0x01, 0x02, 0x7F};
    MessageHeaders messageHeaders = new MessageHeaders(
            Map.of("signature", expected));

    Headers kafkaHeaders = new RecordHeaders();
    mapper.fromHeaders(messageHeaders, kafkaHeaders);

    Header mapped = kafkaHeaders.lastHeader("signature");
    assertThat(mapped.value()).containsExactly(0x01, 0x02, 0x7F);

    Map<String, Object> inbound = new HashMap<>();
    mapper.toHeaders(kafkaHeaders, inbound);

    assertThat((byte[]) inbound.get("signature"))
            .containsExactly(0x01, 0x02, 0x7F);
}
```

When checking `byte[]`, compare array contents with `containsExactly` or `Arrays.equals`; do not use `==` to compare two array objects because that compares references.

If `rawMappedHeaders` is configured, add tests verifying:

- Headers with `true` convert outbound Strings to bytes and inbound bytes to Strings.
- Headers with `false` keep inbound bytes as `byte[]`.
- Headers not in the map retain default raw behavior.
- The charset is configured identically on both sides.
- Duplicate headers are preserved or discarded per agreed rules.

Integration tests with `@EmbeddedKafka` or Testcontainers should send records with custom headers, read the records back, and verify byte arrays, header names, order, and duplicate semantics. Mapper unit tests do not prove that the broker/client is using the right serializer and converter configuration.

## 17. Common pitfalls

**Reading byte[] as String with default charset:** use `StandardCharsets.UTF_8` or the agreed charset.

**Producer sends String but SimpleKafkaHeaderMapper does not map it:** outbound mapper only maps `byte[]` by default. Send a byte array or configure `rawMappedHeaders`/`mapAllStringsOut`.

**Consumer expects String but receives byte[]:** add the header name to `rawMappedHeaders` with `true`, or decode from `byte[]` manually in the listener.

**Using Default/JSON mapper while non-Spring consumer does not understand headers:** choose the raw byte mapper or configure raw mapping for cross-service headers.

**Confusing headers with key/value serializers:** header values must be created as `byte[]` separately; Kafka's value serializer does not automatically convert custom headers.

**Reading only lastHeader when producer sends duplicates:** use `headers(name)` and define multi-value rules.

**Header missing at the broker:** check the mapper's outbound patterns, header data type, and whether the header name belongs to Spring's reserved metadata.

**Putting large objects or secrets into headers:** move large data into the payload, remove secrets, and cap metadata size.

**Changing encoding without versioning the contract:** consumers decode data incorrectly. Keep encoding stable or release a new schema/header version.

## 18. Production checklist

- Every header has its name, byte type, encoding, and semantics documented in the contract.
- Text headers explicitly use UTF-8; binary data has a defined format and byte order.
- Producers build contract-compliant byte arrays before adding Kafka headers.
- Consumers check header existence, length, and encoding before use.
- Choose `SimpleKafkaHeaderMapper` when raw byte mapping is desired; only enable String conversion for necessary headers.
- Do not enable mapping all String headers without evaluating the mapping scope.
- Use a JSON header mapper when rich header types are needed and all sides understand that format.
- Specify whether duplicate headers are allowed and how multiple values are preserved.
- Do not use headers for large payloads, secrets, or unnecessary personal data.
- Have mapper unit tests and integration tests through a Kafka broker.
- Monitor missing/malformed header errors without logging sensitive content.

Mapping `byte[]` headers keeps Kafka metadata on a simple, language-independent contract. Use `SimpleKafkaHeaderMapper` for raw bytes, configure selective String conversion, and standardize encoding between producer and consumer. When the contract clearly states names, formats, duplicate semantics, and size limits, headers support tracing and metadata without introducing coupling to internal Java types.
