# ByteArraySerializer for Binary Payloads

## 1. What Are Binary Payloads in Kafka?

Kafka stores both the key and value of every record as bytes. Producers convert application data types into byte arrays before sending; consumers receive bytes and convert them into forms the business logic can use. This two-way conversion is known as serialization and deserialization.

For text or object data, applications commonly use serializers such as `StringSerializer` or `JsonSerializer`. For payloads that are already in byte form, Kafka provides `ByteArraySerializer`. This serializer directly passes `byte[]` as the record's value without JSON encoding, string conversion, or adding any custom data structures.

Common types of binary payloads:

- PDFs, images, audio, or file attachments.
- Data already encrypted or compressed at the application layer.
- Messages already encoded in a binary format such as Protobuf or an internal format.
- Data blocks supplied by another system as `byte[]`.

In Spring Kafka, `ByteArraySerializer` is suitable when the application already has bytes to send and wants Kafka to transport them as-is. It does not understand PDFs, images, Protobuf, or any domain-specific format structure.

## 2. Serialization and Deserialization Flow

The producer sends `byte[]` via `KafkaTemplate`, and the Kafka producer uses `ByteArraySerializer` to produce the record's value bytes. On the receiving side, the consumer uses `ByteArrayDeserializer` to retrieve the byte array.

~~~mermaid
flowchart LR
    A["Application creates byte[] payload"] --> B["KafkaTemplate<String, byte[]>"]
    B --> C["ByteArraySerializer"]
    C --> D["Kafka record: key + value bytes + headers"]
    D --> E["Kafka topic"]
    E --> F["ByteArrayDeserializer"]
    F --> G["@KafkaListener receives byte[]"]
    G --> H["Application decodes / processes content"]
~~~

Compatible serializers and deserializers must be used:

| Producer side | Consumer side | Value type in application |
|---|---|---|
| `ByteArraySerializer` | `ByteArrayDeserializer` | `byte[]` |
| `StringSerializer` | `StringDeserializer` | `String` |
| `JsonSerializer` | Matching `JsonDeserializer` | Java object per type and trusted-packages configuration |

If the producer sends bytes while the consumer configures `StringDeserializer` or `JsonDeserializer`, the consumer may fail to read or misinterpret the payload. Conversely, if the producer uses `JsonSerializer` while the consumer receives `byte[]`, the received bytes represent serialized JSON rather than the original Java object.

`ByteArraySerializer` adds no schema, class name, or type information to the payload. Producer and consumer must agree on the data contract through other means, such as headers, format versions, or metadata embedded inside the payload.

## 3. Configuring ByteArraySerializer in Spring Boot

You can configure producer and consumer in `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.ByteArraySerializer
      acks: all
      properties:
        enable.idempotence: true

    consumer:
      group-id: document-processor
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.ByteArrayDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest

    listener:
      type: single
      ack-mode: record
~~~

Key property meanings:

- `key-serializer` uses `StringSerializer` to convert `String` keys into bytes.
- `value-serializer` uses `ByteArraySerializer` to send the byte array directly.
- `key-deserializer` and `value-deserializer` must match the key/value types written by the producer.
- `acks: all` requires acknowledgment per Kafka's ISR rules; durability also depends on replication factor and `min.insync.replicas`.
- `enable-auto-commit: false` lets the Spring Kafka listener container manage offsets according to the ack mode.
- `auto-offset-reset: earliest` only determines the starting position when the group has no valid committed offset.

When using Spring Boot with the configuration above, auto-configuration normally creates the corresponding `ProducerFactory`, `ConsumerFactory`, and `KafkaTemplate`. You can inject `KafkaTemplate<String, byte[]>` into your publisher. If the application handles multiple payload types or multiple Kafka clusters, declare separate factories and templates so generic types, serializers, and settings do not collide.

## 4. Sending byte[] Payloads with KafkaTemplate

Suppose a document service receives file content from another component as `byte[]`. The publisher can send the bytes directly while using the document ID as the key so events for the same document are routed consistently:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
public class DocumentPublisher {

    private final KafkaTemplate<String, byte[]> kafkaTemplate;

    public DocumentPublisher(KafkaTemplate<String, byte[]> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, byte[]>> publish(
            String documentId,
            String contentType,
            byte[] content) {

        ProducerRecord<String, byte[]> record =
            new ProducerRecord<>("documents", documentId, content);

        record.headers().add(
            "content-type",
            contentType.getBytes(StandardCharsets.UTF_8)
        );

        record.headers().add(
            "payload-format-version",
            new byte[] { 1 }
        );

        return kafkaTemplate.send(record);
    }
}
~~~

In this example:

- The topic is `documents`.
- The key is `documentId`.
- The value is the raw `content` array.
- The `content-type` header describes the content format, such as `application/pdf` or `image/png`.
- The `payload-format-version` header is application-defined version metadata for the payload contract.

`ProducerRecord` gives control over topic, optional partition, timestamp, key, value, and headers. If you only need to send topic, key, and byte array, you can call the shorter overload:

~~~java
kafkaTemplate.send("documents", documentId, content);
~~~

Asynchronous sending does not mean the broker has acknowledged the record the moment the method returns. For flows that need to track the result, observe the future:

~~~java
documentPublisher.publish(documentId, "application/pdf", content)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error("Failed to send document documentId={}", documentId, error);
            return;
        }

        var metadata = result.getRecordMetadata();
        log.info(
            "Sent documentId={} topic={} partition={} offset={}",
            documentId,
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    });
~~~

The future completes successfully once the producer receives acknowledgments according to `acks`. That confirms the record write per producer policy, not that a consumer has downloaded or processed the file content.

## 5. Creating byte[] from Data Sources

If the data source is already a byte array, there is no need to convert through `String` or Base64. Example reading a small file:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

byte[] content = Files.readAllBytes(Path.of("sample.pdf"));

documentPublisher.publish(
    "DOC-1001",
    "application/pdf",
    content
);
~~~

`Files.readAllBytes` loads the entire file into memory. This works for small payloads of controlled size. For large files, do not default to reading the entire file into the heap and sending it in a single record. Consider storing the content in object storage or a distributed filesystem, then sending only metadata and references such as object key, URI, checksum, and size over Kafka.

If the data comes from an API or a content-generating component, keep it as `byte[]` throughout the send path. Converting bytes to a UTF-8 string is only appropriate when the data is genuinely UTF-8 text. For PDFs, images, audio, or compressed data, string conversion can corrupt the bytes.

Do not use Base64 just to send binary data over Kafka when both producer and consumer can exchange `byte[]`. Base64 inflates payload size by roughly one-third and adds encode/decode overhead. Only use Base64 when an integration contract mandates embedding binary content inside a text format.

## 6. Receiving byte[] Payloads on the Consumer

The consumer must configure `ByteArrayDeserializer`. The listener can receive `byte[]` directly if only the content is needed:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class DocumentListener {

    private final DocumentService documentService;

    public DocumentListener(DocumentService documentService) {
        this.documentService = documentService;
    }

    @KafkaListener(
        topics = "documents",
        groupId = "document-processor"
    )
    public void handle(byte[] content) {
        documentService.process(content);
    }
}
~~~

If key and headers are needed, receive `ConsumerRecord<String, byte[]>`:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class DocumentMetadataListener {

    private final DocumentService documentService;

    public DocumentMetadataListener(DocumentService documentService) {
        this.documentService = documentService;
    }

    @KafkaListener(
        topics = "documents",
        groupId = "document-metadata-processor"
    )
    public void handle(ConsumerRecord<String, byte[]> record) {
        byte[] content = record.value();

        Header contentTypeHeader =
            record.headers().lastHeader("content-type");

        String contentType = contentTypeHeader == null
            ? "application/octet-stream"
            : new String(
                contentTypeHeader.value(),
                StandardCharsets.UTF_8
            );

        documentService.process(
            record.key(),
            contentType,
            content
        );
    }
}
~~~

`ConsumerRecord` is useful when the consumer needs:

- Key to associate the content with a document or business entity.
- Headers for content type, payload version, or correlation ID.
- Topic, partition, and offset for logging, tracing, and error investigation.
- Timestamp for business logic or latency observability.

If the listener only needs the byte array, the signature `handle(byte[] content)` is shorter and easier to test. Avoid leaking Kafka metadata into the domain model if business logic does not need transport details.

## 7. Headers and Binary Payload Contracts

Because `ByteArraySerializer` carries no type information, producer and consumer must agree on how to interpret the bytes. Kafka headers are a suitable place to pass transport metadata such as:

| Suggested header | Example | Purpose |
|---|---|---|
| `content-type` | `application/pdf` | Indicates content media type |
| `payload-format-version` | `1` | Selects the corresponding decoder or reading rules |
| `event-id` | `evt-9a81` | Identifies the event across retries and deduplication |
| `correlation-id` | `req-123` | Correlates logs across services |
| `content-encoding` | `gzip` | Indicates payload was compressed at the application layer |
| `content-length` | `20480` | Original byte size per application contract |

Kafka headers are also byte arrays. When writing strings into headers, choose an explicit encoding, typically UTF-8; when reading, use the same encoding. Do not assume every header is a string.

For structured binary payloads, the contract should specify:

1. Byte layout and field ordering.
2. Format version.
3. Encoding rules for numbers, strings, and timestamps.
4. Handling of missing or newly added fields.
5. Compatibility rules between producer and consumer.
6. Size limits and malformed data checks.

You can place a magic/version byte at the start of the payload if the format needs to be self-describing, or use a version header if the entire system guarantees headers always accompany the value. Either way, the consumer must check the version before decoding.

If using Protobuf, Avro, or a format with a schema registry, consider the dedicated serializer/deserializer for that format. `ByteArraySerializer` only transports encoded bytes; it does not register schemas, manage schema evolution, or decode objects automatically.

## 8. Distinguishing Null from Empty Byte Arrays

A `byte[]` value can be `null`, or a valid array of length 0:

~~~java
byte[] noValue = null;
byte[] emptyPayload = new byte[0];
~~~

These two cases are not identical:

- A `null` value is used by Kafka as a tombstone in compacted topics. A tombstone indicates deletion of the corresponding key under log compaction semantics.
- `new byte[0]` is an existing value with a length of 0 bytes.

The consumer should handle `record.value() == null` explicitly, especially when log compaction is enabled on the topic. Do not assume every `null` means an empty file or corrupted payload.

~~~java
if (record.value() == null) {
    // Handle tombstone or null value according to topic contract.
    return;
}

if (record.value().length == 0) {
    // Payload exists but is empty; handle according to business rules.
    throw new IllegalArgumentException("Empty document payload");
}
~~~

For regular document topics without key compaction, clearly specify whether `null` is allowed. Checking for `null` before processing bytes prevents `NullPointerException` and prevents confusing tombstones with empty content.

## 9. Record Size, Memory, and Compression

Binary payloads can be much larger than typical JSON events. Kafka enforces size limits on the producer, broker, topic, and consumer. Increasing only one side may allow the producer to send, while the broker or consumer still rejects or fails to fetch the record.

Settings to review:

| Component | Property | Role |
|---|---|---|
| Producer | `max.request.size` | Limits outbound request size; affects ability to send large record batches |
| Broker | `message.max.bytes` | Limits the record batch size accepted by the broker |
| Topic | `max.message.bytes` | Can override the batch limit at the topic level |
| Consumer | `max.partition.fetch.bytes` | Limits data fetched per partition |
| Consumer | `fetch.max.bytes` | Limits total data fetched per request |
| Broker replica | `replica.fetch.max.bytes` | Limits data fetched by replicas from the leader |

Actual limits depend on Kafka version and cluster deployment. When raising sizes, check producer, broker/topic, replica fetch, and consumer fetch settings together. Some fetch settings may allow returning a first batch larger than the limit so consumers can make progress, but you should not rely on that exception as a design policy.

Producer configuration example:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        max.request.size: 2097152
~~~

The number above is only an example of a 2 MiB request limit; choose values based on real payload sizes and cluster limits. Do not set excessively high limits unnecessarily, as large records increase heap usage, transfer time, latency, replication pressure, and consumer processing time.

### Compression Is Not ByteArraySerializer's Responsibility

`ByteArraySerializer` only passes `byte[]` as the record value. Kafka compression is a separate mechanism of the producer and record batches. You can configure `compression.type` using a codec supported by your Kafka client and broker versions, such as `gzip`, `snappy`, `lz4`, or `zstd`.

~~~yaml
spring:
  kafka:
    producer:
      properties:
        compression.type: zstd
~~~

Kafka decompresses on the consumer side before the deserializer returns the value to the application. Therefore, the application still receives the original payload bytes. If the payload was already compressed at the application layer, use a header like `content-encoding` and decompress it in the consumer; do not confuse application-level compression with Kafka batch compression.

Some data types such as PDF or JPEG are already compressed, so additional compression may yield little size reduction. Measure with real data before selecting a codec and configuration.

## 10. Security and Payload Integrity

Binary payloads may contain documents, images, or sensitive data. Never dump raw bytes to logs or include intact payloads in exception messages. Log necessary metadata such as event ID, document ID, size, content type, topic, partition, and offset.

If application-layer end-to-end encryption is required, the producer can encrypt the bytes before calling `send`, and the consumer decrypts after receiving. In that case, manage keys, nonces/IVs, algorithms, encryption versions, and key rotation procedures under an explicit contract. TLS on Kafka connections protects data in transit between client and broker, but does not replace payload encryption if brokers or intermediaries must not read the contents.

You can compute a checksum such as SHA-256 to detect content tampering or verify data after storage:

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public String sha256(byte[] content) throws NoSuchAlgorithmException {
    byte[] digest = MessageDigest.getInstance("SHA-256")
        .digest(content);

    return HexFormat.of().formatHex(digest);
}
~~~

Checksums verify integrity, but they are not digital signatures and do not prove a trusted sender. If source authentication is required, use digital signatures or an authentication mechanism matching your security model.

## 11. Testing ByteArraySerializer

Tests should verify that the sent bytes arrive intact, not merely that the listener was invoked.

For publisher unit tests, you can mock `KafkaTemplate` to verify topic, key, value, and headers. For integration tests using Embedded Kafka or Testcontainers, send real bytes through the broker and read them back with a consumer configured with `ByteArrayDeserializer`.

Example content verification:

~~~java
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;

byte[] original = new byte[] {
    0x00, 0x01, 0x02, (byte) 0x80, (byte) 0xFF
};

kafkaTemplate.send("binary-documents", "DOC-1", original)
    .get(10, TimeUnit.SECONDS);

// Test helper polls consumer until a record arrives or timeout expires.
ConsumerRecord<String, byte[]> received = pollForRecord();

assertThat(received.key()).isEqualTo("DOC-1");
assertThat(received.value()).containsExactly(original);
~~~

Cases to test:

- Byte arrays containing `0x00`, Java signed-negative bytes, and non-ASCII bytes.
- Empty payloads and `null` according to topic policy.
- `content-type` and payload version headers preserved intact.
- Payloads near the configured size limit accepted cleanly.
- Misconfigured consumer deserializer detected by integration tests.
- Malformed payloads or unsupported versions handled as data errors.

Never use `new String(bytes)` to compare binary payloads. That conversion uses the default charset and can alter bytes. Compare using `Arrays.equals`, AssertJ `containsExactly`, or checksums.

## 12. Common Errors and Troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| Producer reports serialization error | Value is not `byte[]` while using `ByteArraySerializer` | Check generic types and passed value type |
| Consumer fails deserialization | Consumer uses `StringDeserializer` or `JsonDeserializer` | Configure `ByteArrayDeserializer` |
| Payload corrupted upon receipt | Bytes converted to String/Base64 violating contract | Keep raw bytes or use an agreed encoding |
| Consumer does not know how to read payload | Missing content type or version | Standardize header/format version and validate before decoding |
| Sending large payload fails | Incompatible producer, broker/topic, or fetch limits | Align size limits across the entire pipeline |
| High heap usage | Reading many large files into `byte[]`, retaining copies in memory | Bound payload size/concurrency or offload large content to object storage |
| Content treated as tombstone | Producer sent `null` value | Distinguish `null` from empty byte array and document semantics |

When troubleshooting, inspect in order: actual data type at the publisher, producer serializer, topic and size limits, consumer deserializer, and finally the business decoder.

## 13. When Should You Use ByteArraySerializer?

Use `ByteArraySerializer` when the application already has data in byte form and wants to transport those exact bytes over Kafka. It is well suited for small files, binary payloads, pre-encoded data, or formats already agreed upon by producer and consumer.

Consider an alternative when:

- The payload is a business object needing schemas and version evolution: consider JSON, Avro, or Protobuf.
- Files are very large or require streaming download: store content in object storage and send metadata and references via Kafka.
- The system needs a schema registry or schema-aware serializers: use dedicated serializers instead of manually converting objects to bytes.
- The content is plain text: `StringSerializer` is typically easier to read and operate.

Pre-deployment checklist:

- [ ] Producer uses `ByteArraySerializer` for `byte[]` values.
- [ ] Consumer uses `ByteArrayDeserializer` for `byte[]` values.
- [ ] Key serializer/deserializer matches the key type.
- [ ] Payload contract specifies content type, version, and encoding.
- [ ] `null` values are distinguished from empty byte arrays.
- [ ] Record size fits producer, broker/topic, and consumer limits.
- [ ] Compression is configured separately if needed.
- [ ] Sensitive payloads are not logged verbatim.
- [ ] Tests verify received bytes match sent bytes.

`ByteArraySerializer` enables Spring Kafka to send binary payloads without transforming the content. For reliable operations, producer and consumer must align on deserializers, metadata, and format versions, while controlling size, memory, security, and malformed payload handling.
