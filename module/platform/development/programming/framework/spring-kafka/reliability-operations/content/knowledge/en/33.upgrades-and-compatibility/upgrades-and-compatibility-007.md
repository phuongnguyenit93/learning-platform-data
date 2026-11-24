# Header and Record Metadata Changes When Upgrading Spring Kafka

## 1. Context: A Small Header Change Can Break Compatibility

When upgrading Spring Kafka, an application may still connect to the broker and read payloads, yet business logic fails because **header names changed**, **post-conversion data types differ from before**, **metadata is no longer where the code expects it**, or **a header was stripped by a mapper/serializer**.

For example, a consumer receives an order event:

```text
Kafka topic: orders.created
  key: ORD-1001
  value: {"orderId":"ORD-1001","amount":120.50}

  headers:
    x-correlation-id: "req-123"
    x-schema-version: "v2"
```

The application needs to know:

- `x-correlation-id` to correlate logs between the publishing and processing services.
- `x-schema-version` to select data-compatible parsing logic.
- `topic`, `partition`, and `offset` to investigate and replay messages.
- `timestamp` to distinguish when Kafka recorded the message from when it was processed.
- Error details and record provenance if the message moves to a retry topic or dead-letter topic (DLT).

During an upgrade, a developer updates `@KafkaListener` or `MessageConverter` without updating the header contract. The outcome might be:

```text
09:00 payload parse OK
09:00 x-correlation-id = null
09:00 group processing throws validation error
09:00 record retried multiple times
09:01 record moved to DLT but missing origin metadata
```

The bug lies in the **conversion and metadata layer**, not necessarily because the Kafka broker lost a message.

Within **Spring Kafka Reliability Operations → Upgrades and Compatibility**, this lesson guides you in distinguishing header layers, identifying version-specific API changes, implementing stable header reading/writing, and building contract tests before rolling upgrades of producers, consumers, converters, or retry infrastructure.

## 2. Distinguishing Three Information Sources: Native Headers, Message Headers, and Record Metadata

This is the most important foundation of the lesson.

### 2.1. Kafka Native Headers — Data Stored on the Record

The Kafka client provides `org.apache.kafka.common.header.Headers` and `Header`:

```java
public interface Header {
    String key();
    byte[] value();
}
```

Fundamentally, a native Kafka header has a **String key** and a **`byte[]` value** (or null per the native contract). Kafka allows **multiple headers with the same name** on a single record.

For example:

```text
ProducerRecord
  topic     = orders.created
  partition = (decided by broker/partitioner if unspecified)
  key       = ORD-1001
  value     = {...}
  headers   =
    x-correlation-id -> [114, 101, 113, 45, 49, 50, 51]
    x-schema-version -> [118, 50]
```

Those bytes may be decoded as UTF-8, JSON, an Avro schema identifier, or binary depending on the **contract between producer and consumer**. The Kafka broker does not inherently know whether a header is a String, UUID, Map, or Java object.

### 2.2. Spring MessageHeaders — Data After Message Conversion

When using Spring Messaging `Message<?>`, `@Header`, or `@Headers`, Spring Kafka can map native Kafka headers to `org.springframework.messaging.MessageHeaders` using a `KafkaHeaderMapper`.

```text
Kafka native Header("x-correlation-id", byte[])
                    |
                    v
             KafkaHeaderMapper
                    |
                    v
Spring MessageHeaders["x-correlation-id"] = String or byte[]
```

**The return type depends on the mapper and configuration.** If a producer sends raw UTF-8 bytes while the consumer expects a `String` reconstructed by a JSON mapper using type metadata, the result can differ from expectations when changing converters.

Beyond business headers, Spring Kafka uses internal or synthetic headers when working with `Message<?>`, such as `KafkaHeaders.RECEIVED_TOPIC`, `KafkaHeaders.OFFSET`, and `KafkaHeaders.RECEIVED_PARTITION`. These are not always native Kafka headers placed on the wire by the producer.

### 2.3. Record Metadata — Properties of a Record in the Kafka Log

Every `ConsumerRecord<K,V>` has these attributes:

```text
topic
partition
offset
timestamp
timestampType
serializedKeySize
serializedValueSize
key
value
headers
leaderEpoch (if present)
```

Attributes such as topic/partition/offset reside in **record metadata**; the producer does not need to add an `x-offset` header manually. Offsets are assigned by the broker upon append; the producer cannot know the **resulting offset** before the broker confirms the write.

Spring Kafka can **project metadata** into listener `MessageHeaders`, whereas a consumer accepting raw `ConsumerRecord` reads directly from the record. If code mistakes such metadata for native headers, errors or missing information arise when changing the processing path.

### Decision Table

| Information Needed | Where to Obtain It | What Not to Do |
| --- | --- | --- |
| Application-set Correlation ID | Agreed native header, mapped to String if needed | Assume every producer uses Spring's JSON mapper |
| Business schema version | Contract header or payload envelope | Equate it with Spring serializer's `__TypeId__` |
| Topic, partition, offset on consume | `ConsumerRecord` or Spring-provided metadata | Require the producer to send the offset |
| Offset of a just-succeeded publish | `SendResult.recordMetadata()` | Reuse the input record's offset |
| Delivery attempt | Header/metadata configured by error handler | Assume the header always exists |
| Error history when routed to DLT | Headers on the DLT record added by the recoverer | Treat them as the Kafka record's original log metadata |

## 3. Data Flow from Producer to Listener

```text
Producer application
  |
  +-- ProducerRecord(key, value, Headers)
  |        |
  |        +-- header x-correlation-id (byte[])
  |        +-- header x-schema-version (byte[])
  |
  v
Kafka broker
  |
  +-- assigns topic partition + offset
  +-- stores timestamp per topic config
  |
  v
KafkaConsumer.poll()
  |
  +-- ConsumerRecord<K,V>
  |       topic, partition, offset, timestamp
  |       headers (native Headers)
  |
  +-- record listener receives ConsumerRecord directly
  |
  +-- or MessagingMessageConverter
           |
           v
        Message<?> / @KafkaListener arguments
           payload, @Header, ConsumerRecordMetadata
```

An upgrade may alter **converters**, **serializers/deserializers**, **listener signatures**, **error handlers**, or **batch listener modes**. To pinpoint why metadata disappeared, trace **which layer** dropped it rather than inspecting only the final payload.

## 4. `KafkaHeaders` Changes When Moving from Spring Kafka 2.x to 3.x

Spring Kafka 3.0 **removed** several constants previously deprecated in the 2.9 line. This is a common compile-time break when bumping dependencies:

| Old Constant (2.x) | Constant in 3.x and Later | Context |
| --- | --- | --- |
| `KafkaHeaders.MESSAGE_KEY` | `KafkaHeaders.KEY` | Outbound record key when sending |
| `KafkaHeaders.PARTITION_ID` | `KafkaHeaders.PARTITION` | Outbound target partition |
| `KafkaHeaders.RECEIVED_MESSAGE_KEY` | `KafkaHeaders.RECEIVED_KEY` | Key of received record |
| `KafkaHeaders.RECEIVED_PARTITION_ID` | `KafkaHeaders.RECEIVED_PARTITION` | Partition of received record |

The new names are the published constants in Spring Kafka 3.x and 4.x. If a project still references `MESSAGE_KEY`/`PARTITION_ID` and jumps straight to 3.x, the code may fail to compile.

Example **before upgrade**:

```java
@KafkaListener(topics = "orders.created")
public void listen(
        String payload,
        @Header(KafkaHeaders.RECEIVED_MESSAGE_KEY) String key,
        @Header(KafkaHeaders.RECEIVED_PARTITION_ID) int partition) {
    // Spring Kafka 2.x style.
}
```

Example **after upgrade**:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "orders.created")
public void listen(
        @Payload String payload,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false)
        String key,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition) {
    // Spring Kafka 3.x+ style.
}
```

**Distinguish context:** `KEY`/`PARTITION` describe the **send** side in Spring Messaging; `RECEIVED_KEY`/`RECEIVED_PARTITION` represent properties of the **received** record. Never replace all `RECEIVED_*` references with `KEY` just because the constant name is shorter.

### Why Check Both Source Code and Configuration?

A project may reference constants in:

- `@Header` on `@KafkaListener`.
- `MessageBuilder.setHeader(...)` when publishing.
- `KafkaTemplate.send(Message<?>)`.
- `KafkaListenerErrorHandler`.
- Filters, interceptors, converters, or adapters.
- Test assertions inspecting `MessageHeaders`.

Beyond compile errors, code using **string literals** like `"kafka_receivedMessageKey"` may keep compiling yet read the wrong key for the new synthetic headers. During migration, prefer the constants of your framework version rather than hardcoding internal names.

## 5. Null Keys: The Header May Be Absent

Since Spring Kafka 2.5, if an incoming record has a `null` key, the received key header is **omitted completely** instead of being populated with `null`. This aligns with the `spring-messaging` convention: headers with null values are not present.

Error-prone listener example:

```java
@KafkaListener(topics = "orders.events")
void onEvent(
        String payload,
        @Header(KafkaHeaders.RECEIVED_KEY) String key) {
    // required=true by default: can fail on null-key records.
}
```

Solution if business logic permits null keys:

```java
@KafkaListener(topics = "orders.events")
void onEvent(
        String payload,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false)
        String key) {

    if (key == null) {
        // Rule for records without a key.
    }
}
```

**When upgrading versions, null-key tests are mandatory** if topics contain tombstones, unkeyed records, or upstream sources that do not always supply keys. Never design business logic assuming the header is always present.

Null payloads and null keys are two distinct situations. A Kafka tombstone uses a **null value** for log compaction, yet the tombstone's key usually identifies the record to delete. Handle them per topic contract rather than lumping both into "skip if key or value is null."

## 6. Reading Record Metadata Directly via `ConsumerRecord`

When operational logic needs exact topic, partition, offset, and native headers, `ConsumerRecord` is explicit and depends minimally on mapping:

```java
package com.example.kafka.consumer;

import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderRecordListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-processors")
    public void onOrder(ConsumerRecord<String, String> record) {

        String topic = record.topic();
        int partition = record.partition();
        long offset = record.offset();
        long timestamp = record.timestamp();

        Header correlationHeader =
                record.headers().lastHeader("x-correlation-id");

        String correlationId = correlationHeader == null
                || correlationHeader.value() == null
                ? null
                : new String(
                        correlationHeader.value(),
                        StandardCharsets.UTF_8);

        // Use sanitized data for logging/auditing/processing.
        processOrder(
                record.value(), record.key(),
                topic, partition, offset, timestamp, correlationId);
    }

    private void processOrder(
            String payload, String key, String topic,
            int partition, long offset, long timestamp,
            String correlationId) {
        // Application-specific business logic.
    }
}
```

Advantages:

- Reads native `Headers` with exact bytes from the Kafka client after the deserialization stage.
- Does not rely on `KafkaHeaderMapper` conventions to turn custom headers into Strings/UUIDs.
- Retrieves record metadata directly without converter synthetic headers.
- Can handle multiple same-name headers via `record.headers().headers(name)`.

Limitations:

- `record.value()` has already passed through the value deserializer. If deserialization fails **before the listener is called**, this method does not automatically receive the raw record; `ErrorHandlingDeserializer` or an appropriate error handler is needed.
- Record metadata **does not prove downstream transactions committed**, nor does it tell how many times the listener retried unless you instrument it separately.
- Never commit offsets by mutating headers; offset acknowledgment belongs to the consumer/container.

### Avoid Parsing Binary Headers with the Wrong Encoding

`new String(header.value(), UTF_8)` is valid only when the producer guarantees **UTF-8 text**. If the producer stores a 16-byte UUID, a binary-encoded integer, or a JSON object, decode using the specified codec. Never guess types from header names.

## 7. Reading Metadata with `@Header` in `@KafkaListener`

When using `@KafkaListener` with payload mapping, Spring Kafka can supply metadata via synthetic message headers:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(
        topics = "orders.created",
        groupId = "order-processors")
public void listen(
        @Payload String payload,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false)
        String receivedKey,
        @Header(KafkaHeaders.RECEIVED_TOPIC)
        String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION)
        int partition,
        @Header(KafkaHeaders.OFFSET)
        long offset,
        @Header(KafkaHeaders.RECEIVED_TIMESTAMP)
        long timestamp) {

    // Log or process alongside Spring-supplied metadata.
}
```

This signature style is common in Spring Kafka 3.x. `KafkaHeaders.OFFSET` is the **offset of the consumed record**; it is not the offset of a new message when a listener forwards to another topic.

### Metadata Is Not a Producer-Written Header

If a consumer forwards a record to another topic by copying all `MessageHeaders`, it **must not accidentally turn synthetic headers** `RECEIVED_TOPIC`/`OFFSET` into business metadata of the new record. Converters normally exclude certain `ConsumerRecord`-bound headers when mapping outbound, yet in custom code copying headers manually, you must control this yourself.

A record on `orders.created` at offset 25, once republished to `orders.validated`, may be appended by the broker at offset 900. Attaching a header named `kafka_offset=25` to the new record does not change its real offset; instead it can mislead logs or downstream consumers about provenance.

To preserve provenance, use **dedicated business headers** such as `x-origin-topic`, `x-origin-partition`, and `x-origin-offset` with explicit formats/codecs, or use the standard headers provided by `DeadLetterPublishingRecoverer` when routing to a DLT.

## 8. `ConsumerRecordMetadata`: Getting Metadata Without Repeating `@Header`

Since Spring Kafka 2.5, a listener can accept `ConsumerRecordMetadata`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.adapter.ConsumerRecordMetadata;
import org.springframework.stereotype.Component;

@Component
public class OrderMetadataListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-processors")
    public void listen(
            String payload,
            ConsumerRecordMetadata metadata) {

        String topic = metadata.topic();
        int partition = metadata.partition();
        long offset = metadata.offset();
        long timestamp = metadata.timestamp();

        // ConsumerRecordMetadata does not carry key/value.
        audit(topic, partition, offset, timestamp);
    }

    private void audit(
            String topic, int partition, long offset, long timestamp) {
        // Application-defined.
    }
}
```

`ConsumerRecordMetadata` lives in `org.springframework.kafka.listener.adapter` and exposes record details (except key/value), including timestamp type. It is a **method argument supported by the listener adapter**, not a producer-sent header.

When you need key, value, and all native headers, use `ConsumerRecord`. When the method mostly handles payload yet needs topic/partition/offset for auditing, `ConsumerRecordMetadata` or `@Header` can be cleaner.

### Do Not Confuse with Producer `RecordMetadata`

Kafka clients also have `org.apache.kafka.clients.producer.RecordMetadata`, typically returned when **a producer send succeeds**. Despite similar names, producer-side and consumer-side metadata belong to two different moments:

```text
Producer: ProducerRecord -> broker append -> RecordMetadata result
Consumer: poll -> ConsumerRecord -> ConsumerRecordMetadata adapter
```

If a processor reads from an input topic and sends to an output topic, the **input offset** and **output offset** must be recorded as two distinct fields.

## 9. `RecordMetadata` When Producing to Kafka: `CompletableFuture` and Callbacks

Spring Kafka 3.x changed `KafkaTemplate` from returning `ListenableFuture` to `CompletableFuture`. This is a frequent breaking change in send-result tracking code.

### Before Spring Kafka 3.x

Some Spring Kafka 2.x applications used:

```java
ListenableFuture<SendResult<String, String>> future =
        kafkaTemplate.send("orders.out", "ORD-1001", payload);

future.addCallback(success -> {
    // success.getRecordMetadata()
}, error -> {
    // handle error
});
```

### In Spring Kafka 3.x and Later

```java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String key, String payload) {
        kafkaTemplate.send("orders.out", key, payload)
                .whenComplete((SendResult<String, String> result, Throwable ex) -> {
                    if (ex != null) {
                        recordPublishFailure(key, ex);
                        return;
                    }

                    RecordMetadata metadata = result.getRecordMetadata();
                    recordPublishSuccess(
                            key,
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset(),
                            metadata.timestamp());
                });
    }

    private void recordPublishFailure(String key, Throwable ex) {
        // Controlled logging/auditing.
    }

    private void recordPublishSuccess(
            String key, String topic, int partition,
            long offset, long timestamp) {
        // Record metadata of the OUTPUT record.
    }
}
```

Notes:

- `result.getRecordMetadata()` is the metadata of the **just-published record** confirmed by the broker per producer configuration; not the metadata of a record consumed by a listener.
- Callbacks execute on the future's lifecycle; do not assume they always run on the consumer listener thread or carry the caller thread's MDC.
- When code uses Kafka transactions, a successful send future **does not by itself prove the transaction ultimately committed**. The transaction may abort at a later step.
- Do not use a succeeded send offset as a business idempotency key; on produce retries, the offset can differ.
- During a 2.x → 3.x migration, locate all `ListenableFuture`/`addCallback` usages tied to `KafkaTemplate` and update outcome handling.

## 10. Native Kafka Headers Can Have Duplicate Names

Kafka supports multiple values under the same name:

```text
Headers:
  x-route: primary
  x-route: backup
  x-route: audit
```

With the native API:

```java
Headers headers = record.headers();

Header latest = headers.lastHeader("x-route");
Iterable<Header> all = headers.headers("x-route");
```

`lastHeader` retrieves the last entry for that name, while `headers(name)` iterates across all values. If an application contract permits only one value, seeing multiple values may indicate a **data error** and should be detected rather than silently taking the last one.

### Differences When Mapping to Spring `MessageHeaders`

`MessageHeaders` is essentially a map from a name to a single object. Before explicit multi-value mapping support, duplicate-named headers could collapse to a single value. Native `Headers` still holds multiple entries, yet converter output could retain **only the last value**.

Starting in **Spring Kafka 4.0**, `JsonKafkaHeaderMapper` and `SimpleKafkaHeaderMapper` support configuring multi-value mapping. To preserve all values when using Spring Messaging, declare names or patterns treated as multi-value:

```java
import org.springframework.kafka.support.mapping.JsonKafkaHeaderMapper;

JsonKafkaHeaderMapper mapper = new JsonKafkaHeaderMapper();
mapper.setMultiValueHeaderPatterns(
        "x-route",
        "x-audit-*");
```

This is a **Spring Kafka 4.x** API; do not copy it into 3.x code expecting it to compile. For headers configured as multi-value, the mapper can emit elements as separate native headers and receive them back as a `List<?>` across conversion steps.

**Important when upgrading:**

1. Inventory topics using duplicate-named headers, such as route lists or event baggage.
2. Check whether consumers currently expect `String`/`byte[]` or `List<?>`.
3. Enable multi-value only for headers with an explicit contract; avoid overly broad patterns if downstream consumers do not support them.
4. Test records with one, multiple, and zero headers, including ordering and byte contents.
5. If using `SimpleKafkaHeaderMapper`, verify how its collection handling differs from `JsonKafkaHeaderMapper`.

Defaults in 4.x mappers **do not mean every repeated header is preserved automatically**. Per the docs, without multi-value configuration a collection-valued header may be JSON-serialized as one blob or retain only the last value upon receipt. This is an important change for systems relying on multiple same-name headers.

## 11. `HeaderMapper`: Data Type Changes After Conversion

Spring Kafka provides common mappers:

| Mapper | Characteristics | Upgrade Risk |
| --- | --- | --- |
| `SimpleKafkaHeaderMapper` | Works primarily with raw bytes and a few String rules | Consumers must not assume every header becomes a Java object |
| `DefaultKafkaHeaderMapper` (Jackson 2) | JSON-encodes/decodes many header types using type metadata | `String`/`Map`/`UUID` types may differ when changing mappers |
| `JsonKafkaHeaderMapper` (Jackson 3, 4.x) | New implementation for Jackson 3, supports configurable multi-value | Class/config changes and requires wire compatibility testing |
| Native `ConsumerRecord.headers()` | Accesses exact bytes after deserialization | Caller decodes per contract |

### 11.1. Type Metadata Header `spring_json_header_types`

When using Spring Kafka's JSON mapper, a special header `spring_json_header_types` carries type information to map inbound headers back into their corresponding Java types.

Illustrative example:

```text
Kafka Headers:
  x-attempts            -> JSON/binary bytes
  x-correlation-id      -> UTF-8 bytes
  spring_json_header_types -> {"x-attempts":"java.lang.Integer", ...}
```

When an external non–Spring Kafka producer sends the same headers **without `spring_json_header_types`**, the consumer cannot automatically know `x-attempts` is an `Integer`. A mapper may surface it as `byte[]`. Avoid building cross-language contracts tied to mapper Java class names when producers/consumers span multiple technologies.

### 11.2. String Encoding Has Changed Historically

Historically in Spring Kafka, the JSON mapper changed how `String` headers were handled in version 2.3: string headers stopped being JSON-encoded with surrounding quotes by default, though type metadata still lets compatible Spring consumers interpret them.

When **multiple producer/consumer versions coexist**, an old producer and new consumer may disagree on bytes:

```text
Old producer serialization (illustrative):
  x-correlation-id = bytes of "req-123" (quoted JSON string)

Newer producer serialization (illustrative):
  x-correlation-id = bytes of req-123  (raw UTF-8)
```

For compatibility with older consumers in relevant migrations, mappers support `setEncodeStrings(true)` in corresponding versions. Do not enable it arbitrarily once using a raw interoperability contract; inspect the **actual wire bytes**.

### 11.3. Passing Raw UTF-8 Strings Across Multiple Languages

If a Java producer and Node/Python/Go consumers share `x-correlation-id`, a stable contract might look like:

```text
Name: x-correlation-id
Wire type: UTF-8 bytes
Value format: opaque printable identifier
Presence: optional
Maximum length: 128 bytes
Duplicates: forbidden
```

When using Spring Kafka's JSON header mapper on the Java side, configure raw mapping for this header:

```java
import java.util.Map;
import org.springframework.kafka.support.DefaultKafkaHeaderMapper;

DefaultKafkaHeaderMapper mapper =
        new DefaultKafkaHeaderMapper();
mapper.setRawMappedHeaders(
        Map.of("x-correlation-id", true));
```

This example targets **Spring Kafka 3.x using Jackson 2**. Setting `true` maps outbound String headers to raw bytes and inbound raw bytes back to Strings using the configured charset (default UTF-8). When moving to 4.x/Jackson 3, use the corresponding mapper class and verify methods/configs for that release.

If all apps commit to raw bytes, one way to avoid mapper dependency altogether is creating `ProducerRecord` with `RecordHeader` and reading `ConsumerRecord.headers()` directly wherever absolute precision is needed.

## 12. Serialization Type Headers Are Not a Business Schema Version

Spring Kafka JSON serializers may add type metadata headers such as:

```text
__TypeId__
__KeyTypeId__
__ContentTypeId__
```

These headers help Jackson-based serializers/deserializers identify Java types when payloads can represent multiple types. They **do not mean** the system's schema is version `v1`, `v2`, or `v3`.

Do not write:

```java
// Do not interpret __TypeId__ as a business schema version.
String schemaVersion = readHeader("__TypeId__");
```

Clearer business contract example:

```text
x-event-type: order.created
x-schema-version: 2
content-type: application/json
```

From the schema version, the consumer picks the right parser or migration logic. When using Avro/Protobuf/JSON Schema Registry, the schema identity may live inside the wire payload format or serializer-provided metadata; do not assume every framework uses the same header.

### 12.1. Why Does `__TypeId__` Disappear After Deserialization?

Under Spring Kafka JSON deserializer behavior, type info headers may be **removed by default after deserialization** (a behavior introduced in the 2.2 line). Thus a listener not seeing `__TypeId__` does not necessarily mean the producer never sent it.

In Spring Kafka 3.x with `JsonDeserializer`, relevant properties include:

```properties
spring.json.use.type.headers=true
spring.json.remove.type.headers=true
spring.json.trusted.packages=com.example.orders.events
```

These are **Kafka deserializer config keys**, not an entire `application.properties` file for Spring Boot. In Spring Boot, pass them under `spring.kafka.consumer.properties.*` or configure the deserializer directly:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.use.type.headers: true
        spring.json.remove.type.headers: true
        spring.json.trusted.packages: "com.example.orders.events"
```

Note that Spring Kafka 4.x introduces new Jackson 3 classes with corresponding constants/properties. During migration, pair the right serializer/deserializer; do not mix Jackson 2/3 packages randomly assuming old behavior holds.

If the application must retain type info for auditing, configure retention where appropriate, yet **never rely on technical type headers for long-term schema understanding**. Schema versions should be an independent business contract.

### 12.2. Trusted Packages Are a Security Boundary

Never set `trusted.packages=*` just to "silence errors" during an upgrade. Type metadata influences which Java objects a deserializer instantiates. Allow only necessary packages/schema types, or use a fixed target type when the topic contract allows.

With JSON header mappers, trusted-package configuration also governs which Java types may be reconstructed from `spring_json_header_types`. If a package is untrusted, the mapper may return a representation like `NonTrustedHeaderType` instead of deserializing into the original object.

When upgrading from Jackson 2 to Jackson 3, verify both **class names/imports** and **trusted type policies**; never apply broad wildcards as a quick fix.

## 13. Spring Kafka 4.x: Jackson 3 and New Class Names

Spring Kafka 4.x adds Jackson 3 support alongside Jackson 2 classes. Common pairs:

| Jackson 2 / Legacy Code | Jackson 3 / New Code | Role |
| --- | --- | --- |
| `DefaultKafkaHeaderMapper` | `JsonKafkaHeaderMapper` | JSON header mapping |
| `JsonSerializer` | `JacksonJsonSerializer` | Serialize JSON payloads |
| `JsonDeserializer` | `JacksonJsonDeserializer` | Deserialize JSON payloads |
| `JsonSerde` | `JacksonJsonSerde` | Serde for Kafka Streams |
| `JsonMessageConverter` and variants | `JacksonJsonMessageConverter` and variants | Message payload conversion |
| `DefaultJackson2JavaTypeMapper` | `DefaultJacksonJavaTypeMapper` | Mapping type identifiers |

Spring Kafka 4.x documentation notes that legacy Jackson 2 classes remain provided yet deprecated on the upgrade path. The framework may prefer Jackson 3 when both are on the classpath.

**Operational consequence:** adding a Jackson 3 dependency or bumping the parent BOM can shift the conversion path even with minimal business code changes. Migrations should inspect the **effective dependency tree**, the actual converter/mapper beans created, and bytes sent/received.

### A Cautious Upgrade Strategy

1. Lock compatible Spring Boot/Spring Kafka/Jackson versions together; do not update a single JAR in isolation.
2. Record the mapper/serializer/deserializer active in the old version.
3. Write contract tests comparing raw header bytes and converted types.
4. Migrate classes/imports to the new API on a dedicated branch if adopting Jackson 3.
5. Run mixed-version tests: old producer → new consumer, new producer → old consumer.
6. Upgrade consumers first or producers first depending on which forward/backward compatibility direction tests proved.
7. Enable monitoring for deserialization/conversion/retry errors and deploy via canary.
8. Remove compatibility flags only after no older version still requires support.

Do not assume Jackson 3 is merely an import change. In polyglot systems with producers/consumers across languages, the **wire contract** is what matters.

## 14. Producer Sending Headers: Use `ProducerRecord` When an Explicit Wire Contract Is Needed

To send a UTF-8 header precisely per a cross-system contract:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.springframework.kafka.core.KafkaTemplate;

public class OrderWirePublisher {

    private final KafkaTemplate<String, String> template;

    public OrderWirePublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public void publish(
            String orderId, String payload, String correlationId) {

        RecordHeaders headers = new RecordHeaders();
        headers.add(
                "x-correlation-id",
                correlationId.getBytes(StandardCharsets.UTF_8));
        headers.add(
                "x-schema-version",
                "2".getBytes(StandardCharsets.UTF_8));

        ProducerRecord<String, String> record =
                new ProducerRecord<>(
                        "orders.created",
                        null, // partition: let Kafka choose
                        orderId,
                        payload,
                        headers);

        template.send(record);
    }
}
```

In this example, we use the `ProducerRecord(topic, partition, key, value, headers)` constructor compatible with common Kafka client versions in Spring Kafka 3.x. `KafkaTemplate.send(record)` sends a raw Kafka producer record without going through `MessageBuilder` and Spring Messaging header mappers to represent custom headers.

However, **`template.send(record)` is asynchronous**. If you need to know the broker accepted the record, handle the `whenComplete(...)` future or await the result with a timeout. Never log "published successfully" merely because `send` returned a future.

### Passing Trace/Correlation via Headers

If the application uses Micrometer Tracing/OpenTelemetry, instrumentation can inject trace context into headers using its propagation format. Do not manually set `traceparent` or copy trace IDs unless you understand context propagation; let tracing instrumentation handle it. Business correlation IDs are an independent contract and may still be needed for auditing after traces expire from retention.

## 15. Using `MessageBuilder`: Distinguish Routing Headers from Wire Headers

With `KafkaTemplate.send(Message<?>)`, Spring Messaging headers can control the topic/key/partition/timestamp of the outgoing record:

```java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder
        .withPayload("{\"orderId\":\"ORD-1001\"}")
        .setHeader(KafkaHeaders.TOPIC, "orders.created")
        .setHeader(KafkaHeaders.KEY, "ORD-1001")
        .setHeader("x-correlation-id", "req-123")
        .build();

kafkaTemplate.send(message);
```

Example for Spring Kafka 3.x and later; `kafkaTemplate` is assumed to be an injected `KafkaTemplate` in the service class. `KafkaHeaders.TOPIC` specifies the target topic and `KafkaHeaders.KEY` specifies the key when the converter builds the Kafka record. Remaining headers are converted by `MessagingMessageConverter`'s `KafkaHeaderMapper`.

If a non-Java consumer reads `x-correlation-id`, ensure the mapper encodes the header into **bytes matching the contract**. Do not infer from `MessageBuilder`'s `String` type that the Kafka broker stores a String; Kafka wire headers are always `byte[]`.

### Which Approach to Choose?

| Need | Convenient Approach |
| --- | --- |
| Want Spring Messaging payloads and routing headers | `MessageBuilder` + `KafkaTemplate.send(Message<?>)` |
| Want exact byte-level control of native headers | `ProducerRecord` + `RecordHeaders` |
| Want JSON object headers between Spring applications | JSON header mapper with explicit type contracts |
| Want stable cross-language communication | Native bytes per published UTF-8/binary/JSON contract |

## 16. Batch Listeners: Metadata Is Mapped by Position

In batch mode, listeners receive **multiple records**, so topic/partition/offset can be **lists** rather than single values.

Example listener configured for batch mode via a container factory:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-consumers",
        containerFactory = "batchKafkaListenerContainerFactory")
public void listenBatch(
        java.util.List<String> payloads,
        @Header(KafkaHeaders.RECEIVED_TOPIC)
        java.util.List<String> topics,
        @Header(KafkaHeaders.RECEIVED_PARTITION)
        java.util.List<Integer> partitions,
        @Header(KafkaHeaders.OFFSET)
        java.util.List<Long> offsets) {

    for (int i = 0; i < payloads.size(); i++) {
        audit(payloads.get(i),
                topics.get(i),
                partitions.get(i),
                offsets.get(i));
    }
}
```

This is an illustrative method snippet; `audit(...)` must be defined by the application. The container factory must actually have `batchListener=true`. Never use a record-listener signature and assume scalar metadata inside a batch.

### Batch Converted Headers vs. Native Headers

When using `BatchMessagingMessageConverter`:

- `KafkaHeaders.BATCH_CONVERTED_HEADERS` may contain `List<Map<String,Object>>`, each map corresponding to one item in the batch.
- When no header mapper is used, `KafkaHeaders.NATIVE_HEADERS` can provide native `Headers`; in batch mode this is a list corresponding to the records.
- Positions in header/metadata lists must align with positions in the payload list.

For records with **null keys**, header/metadata lists may follow presence rules different from a simple list of scalar values. Avoid zipping multiple lists without inspecting converter configuration and testing null/missing header cases. When per-record metadata certainty is needed, accept `List<ConsumerRecord<K,V>>` in the batch listener to read topic/partition/offset/native headers directly from each record.

## 17. Headers in Retry and Dead-Letter Topics

Reliability systems often use `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, or retry topics. When a record is sent to a DLT, the framework can preserve custom headers and add **origin and exception details**.

For example:

```text
Original:
  topic=orders.created, partition=2, offset=125
  headers:
    x-correlation-id=req-123

After DeadLetterPublishingRecoverer:
  topic=orders.created-dlt, partition=2, offset=10  (assigned by DLT broker)
  headers:
    x-correlation-id=req-123
    kafka_dlt-original-topic = orders.created
    kafka_dlt-original-partition = 2
    kafka_dlt-original-offset = 125
    kafka_dlt-exception-fqcn = ...
```

The native key names in the sketch **illustrate meaning**; in code use the `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, `KafkaHeaders.DLT_ORIGINAL_OFFSET`, and `KafkaHeaders.DLT_EXCEPTION_FQCN` constants of your exact version instead of hardcoding unverified wire strings.

### DLT Metadata Differs from the DLT Record's Own Metadata

A consumer reading from a DLT sees:

- `record.topic()/partition()/offset()`: the **current position inside the DLT**.
- `KafkaHeaders.DLT_ORIGINAL_*`: details of the **source record** attached by the recoverer.

When investigating the original message in `orders.created`, use the origin metadata rather than taking DLT offset `10` to search the input topic.

### Accumulated Headers Across Multiple Retries

Kafka permits duplicate header names. If a record is republished across multiple retry topics, DLT exception/origin headers can **accumulate**, especially stack traces. This can cause:

- Growing header lists.
- Records exceeding size limits.
- Consumers calling `lastHeader` when business logic wants the first origin.
- Misleading retry depth calculations from counting headers without a contract.

`DeadLetterPublishingRecoverer` offers management options such as `appendOriginalHeaders` and `stripPreviousExceptionHeaders`; defaults/scopes can differ between basic DLT usage and non-blocking retries. Check the actual configuration rather than relying on one generic assumption.

If an immutable origin header is needed across hops, clearly define **first origin** vs. **last failure**. Never overwrite source metadata arbitrarily when re-driving a DLT.

### Byte Encoding of DLT Headers

`DLT_ORIGINAL_PARTITION`/`DLT_ORIGINAL_OFFSET` values are encoded by Spring Kafka following its own convention. Do not assume they are UTF-8 ASCII text like `"125"`; when reading native headers, decode using the exact binary representation of your framework version or use the appropriate converter/utility. For DLT consumers written in other languages, the codec contract matters even more.

## 18. Delivery Attempt Header: Absence Does Not Mean First Attempt

Spring Kafka provides `KafkaHeaders.DELIVERY_ATTEMPT` to observe retries when supported by the error handler/after-rollback processor and enabled on the container:

```java
@KafkaListener(topics = "orders.created")
public void listen(
        String payload,
        @Header(name = KafkaHeaders.DELIVERY_ATTEMPT, required = false)
        Integer attempt) {

    int observedAttempt = attempt == null ? -1 : attempt;
    // -1: header unavailable/not enabled;
    // do not assert this means attempt=1.
}
```

On a raw `ConsumerRecord`, the delivery attempt header value may be a **4-byte encoded integer**, requiring decoding per framework convention:

```java
Header header =
        record.headers().lastHeader(KafkaHeaders.DELIVERY_ATTEMPT);

if (header != null && header.value() != null
        && header.value().length == Integer.BYTES) {
    int attempt = java.nio.ByteBuffer
            .wrap(header.value())
            .getInt();
}
```

A listener using a converted header mapper can receive `int` directly, while a raw listener receives `byte[]`. If an upgrade changes the listener signature from `ConsumerRecord` to `@Header`, test both **type and value** of the delivery attempt.

Do not assume the header is always enabled, or always populated on batch listeners. The `deliveryAttemptHeader` setting and error handler capabilities determine its presence.

## 19. Stable Header Contract Model for Producers and Consumers

A contract should specify more than header names. For example:

| Header | Wire Format | Required? | Duplicates? | Rule |
| --- | --- | --- | --- | --- |
| `x-event-type` | UTF-8 string | Yes | No | `order.created`, `order.updated`, ... |
| `x-schema-version` | UTF-8 ASCII digits | Yes | No | `1`, `2`, ... |
| `x-correlation-id` | UTF-8 string | Yes (except migration window) | No | Must not contain PII |
| `x-source-service` | UTF-8 string | Optional as needed | No | In known service registry |
| `traceparent` | W3C trace context per instrumentation | If tracing enabled | Per propagator | Never mutated by business code |
| `x-replay-reason` | UTF-8 enum | Only during replay | No | `manual`, `scheduled`, `repair` |
| Spring `__TypeId__` | Framework-specific | Not part of business contract | Per serializer | Never used as business schema version |

### Design Principles

1. Use **namespaced custom names** like `x-schema-version` for business semantics, avoiding names resembling internal Kafka/Spring metadata.
2. Clearly specify whether each header is optional or required.
3. Define raw bytes/charset/endianness, not only Java types.
4. Define whether duplicate same-name headers are allowed.
5. Bound size and allowed characters to prevent log/serialization abuse.
6. Distinguish **semantic fields** from transport metadata.
7. Maintain producer ↔ consumer tests at both byte level and converted-value level.
8. Include a compatibility window when changing names or types; avoid switching producer and consumer simultaneously and losing rollback ability.

### Standardizing Header Names

Kafka native header names are `String`s and case-sensitive. `X-Correlation-Id` and `x-correlation-id` can be treated as two different keys in consumer code. Pick a convention—for example, all lowercase kebab-case business header names—and test consistency.

## 20. Contract Migration: Add the New Header Before Removing the Old Header

Suppose the legacy system used `correlationId` (camelCase) while the new system wants `x-correlation-id`. Changing producer and consumer simultaneously creates risk during a rolling deployment.

A safe plan:

```text
Phase A:
  Old producer writes correlationId
  Old consumer reads correlationId

Phase B:
  Updated consumer reads x-correlation-id, fallback correlationId
  Producer still writes correlationId

Phase C:
  New producer writes BOTH headers
  New/old consumers still read fine

Phase D:
  Confirm no old consumers remain / no backlog needs old key
  New producer writes only x-correlation-id

Phase E:
  Remove consumer fallback once retention/backlog permits
```

Compatible code for native `ConsumerRecord`:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;

static String getCorrelationId(Headers headers) {
    Header newHeader = headers.lastHeader("x-correlation-id");
    Header oldHeader = headers.lastHeader("correlationId");

    if (newHeader != null && newHeader.value() != null) {
        return new String(newHeader.value(), StandardCharsets.UTF_8);
    }
    if (oldHeader != null && oldHeader.value() != null) {
        return new String(oldHeader.value(), StandardCharsets.UTF_8);
    }
    return null;
}
```

**Important:** if both headers exist with different values, do not silently pick one when the contract requires uniqueness. That could stem from a buggy producer, a proxy/bridge altering metadata, or a replay. For critical audit fields, **fail/quarantine** per policy, record an error category, and investigate.

### Retention/Backlog When Changing Headers

Even once all new producers write the new header, consumers may still read older records in topics or replays from the DLT. Therefore, the timing for removing the fallback must account for **topic retention, compaction, replay processes, DLT retention, and audit storage**, not just deployment day.

## 21. Testing Native Headers with the Kafka Client API

The following test needs no Kafka broker; it verifies bytes and duplicate semantics of `RecordHeaders`:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;

class NativeHeaderContractTest {

    @Test
    void utf8HeaderRetainsExactBytes() {
        RecordHeaders headers = new RecordHeaders();
        headers.add(
                "x-correlation-id",
                "req-123".getBytes(StandardCharsets.UTF_8));

        Header header = headers.lastHeader("x-correlation-id");

        assertNotNull(header);
        assertArrayEquals(
                "req-123".getBytes(StandardCharsets.UTF_8),
                header.value());
    }

    @Test
    void duplicateHeadersAreNotAutomaticallyCollapsed() {
        RecordHeaders headers = new RecordHeaders();
        headers.add("x-route", new byte[]{1});
        headers.add("x-route", new byte[]{2});

        List<Header> all = new ArrayList<>();
        headers.headers("x-route").forEach(all::add);

        assertEquals(2, all.size());
        assertArrayEquals(new byte[]{2},
                headers.lastHeader("x-route").value());
    }

    @Test
    void oldAndNewCorrelationKeysCanCoexist() {
        RecordHeaders headers = new RecordHeaders();
        headers.add(
                "correlationId",
                "req-123".getBytes(StandardCharsets.UTF_8));
        headers.add(
                "x-correlation-id",
                "req-123".getBytes(StandardCharsets.UTF_8));

        assertEquals("req-123", getCorrelationId(headers));
    }
}
```

`getCorrelationId(...)` is the helper from the previous section; place it inside the test class or static-import it from an application utility. This unit test verifies **Kafka header bytes**; it does not yet test mappers or real wire exchange with a broker.

## 22. Testing Header Mappers Between Two Versions

Maintain a **contract fixture** set:

```text
fixtures/
  native-headers-v1.json
  native-headers-v2.json
  payload-order-created-v1.json
  payload-order-created-v2.json
```

The fixture files are only a suggested test project layout, not files created in this lesson. For the Spring Kafka 3.x mapper, round-trip example:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.DefaultKafkaHeaderMapper;
import org.springframework.messaging.MessageHeaders;

class HeaderMapperContractTest {

    @Test
    void rawCorrelationStringIsCompatible() {
        DefaultKafkaHeaderMapper mapper =
                new DefaultKafkaHeaderMapper();
        mapper.setRawMappedHeaders(
                Map.of("x-correlation-id", true));

        MessageHeaders source =
                new MessageHeaders(
                        Map.of("x-correlation-id", "req-123"));

        RecordHeaders nativeHeaders = new RecordHeaders();
        mapper.fromHeaders(source, nativeHeaders);

        Map<String, Object> received = new HashMap<>();
        mapper.toHeaders(nativeHeaders, received);

        assertEquals("req-123", received.get("x-correlation-id"));
    }
}
```

This example uses **Spring Kafka 3.x/Jackson 2**. For 4.x/Jackson 3, use the corresponding `JsonKafkaHeaderMapper`. Keep fixtures from the legacy system to test:

- Names/bytes of native headers produced by the producer.
- Types inside converted `MessageHeaders`.
- Missing headers or null values.
- Strings containing Unicode, quotes, or escaped characters.
- Duplicate headers and data direction through the mapper.
- Untrusted package type metadata cases.

**Round-trip testing with the same mapper is not enough to prove interoperability.** Even if mapper A encodes and decodes its own output, older mapper B may still fail to read it. Test the actual producer-version A ↔ consumer-version B pairs directly.

## 23. Integration Testing with a Broker: Old Producer and New Consumer

For Spring Boot 3.x/Spring Kafka 3.x projects, use `spring-kafka-test` with `@EmbeddedKafka` or Testcontainers Kafka. Broker tests verify producer sends, assigned metadata, converters, error handlers, and actual listener signatures end to end.

### Test Matrix

| Producer | Consumer | What Must Be Proven |
| --- | --- | --- |
| Old version | Old version | Baseline contract still holds |
| Old version | New version | Backward compatibility |
| New version | Old version | Forward compatibility during rolling window |
| New version | New version | Target format |
| External (non-Spring) | New Spring | Raw UTF-8/binary headers do not depend on Java type mapper |
| New Spring | External | Producer does not emit bytes an external consumer cannot parse |
| DLT from old version | New re-drive consumer | Origin metadata and exception headers remain readable |
| Record with null key/value | New consumer | Signature/required headers match |
| Record with duplicate headers | New mapper | No out-of-contract data loss |

### What Should the Integration Test Verify?

1. Send a record with a key, payload, and two custom headers.
2. Await the producer future; read `SendResult.getRecordMetadata()` for the **output offset**.
3. Consume with `read_committed` or `read_uncommitted` per test goal (do not misconfigure isolation level).
4. Compare native header bytes retrieved from `ConsumerRecord.headers()`.
5. If the listener uses conversion, compare converted header values and types.
6. Assert `topic`/`partition`/`offset` on the listener using metadata from the received record, not a hardcoded literal.
7. Inject a controlled exception, route to the DLT, and verify origin topic/partition/offset.
8. Repeat using the exact producer/consumer versions planned for deployment.

Note: a producer receives an offset after sending, yet concurrent tests can shift actual offset ordering. Correlate by key or correlation ID rather than asserting a message always lands at a fixed offset unless the topic/partition/test setup is isolated.

## 24. Testing Batch Metadata and DLT

When migrating from a record listener to a batch listener, there is a risk of misaligning positional metadata. A test should publish three records to the same topic with distinct keys and headers:

```text
Record A: key=A, correlation=req-a
Record B: key=B, correlation=req-b
Record C: key=C, correlation=req-c
```

When receiving `List<ConsumerRecord<String,String>>`, test directly:

```java
for (ConsumerRecord<String, String> record : records) {
    String key = record.key();
    String correlation =
            decodeUtf8(record.headers(), "x-correlation-id");

    assertEquals(expectedCorrelationByKey.get(key), correlation);
}
```

`decodeUtf8(...)` and `expectedCorrelationByKey` are test helpers/fixtures. With lists of `Message<?>` or converted-header lists, verify indices between payloads and metadata align.

In DLT tests, record separately:

```text
dltRecord.topic / partition / offset
originTopic / originPartition / originOffset
errorCategory
correlationId
```

Do not conflate DLT `offset` with `originOffset`. When retrying/re-driving across multiple topics, verify origin metadata is not accidentally overwritten by intermediate hop metadata.

## 25. Observing Post-Upgrade Header Incidents

A rollout plan should include useful logging without exposing sensitive data:

```json
{
  "event": "kafka_header_contract_violation",
  "service": "orders-consumer",
  "topic": "orders.created",
  "partition": 2,
  "offset": 125,
  "headerName": "x-schema-version",
  "errorCategory": "MISSING_REQUIRED_HEADER",
  "consumerVersion": "vNext",
  "producerContractVersion": "v2"
}
```

This is a proposed log schema, not an automatic Spring Kafka record. Usually log:

- `topic`, `partition`, `offset` to trace the record.
- `consumerGroup` and application version to identify which deployment failed.
- Header name, error category, expected codec/schema version.
- Controlled correlation ID if non-sensitive.
- Exception class and summarized cause.

Never write raw payloads containing PII, `Authorization` headers, tokens, or full DLT exception stack traces to public logs.

### Suggested Metrics

| Metric | Low-Cardinality Tag Group | Purpose |
| --- | --- | --- |
| `kafka_header_contract_error_total` | service, topic, errorCategory | Detect incompatibility early |
| `kafka_deserialization_failure_total` | service, topic, errorCategory | Distinguish wire payload vs. type header errors |
| `kafka_dlt_publish_total` | service, sourceTopic, reason | Track errors leading to DLT |
| `kafka_record_process_duration` | service, listenerId | Detect converter latency regressions |
| `kafka_record_retry_total` | service, listenerId, reason | Spot data errors driving up retries |
| `kafka_consumed_lag` | group, topic | Alert on backlogs during rollout |

These are **illustrative application metric names**, not claims that Spring Kafka/Micrometer provides these exact names out of the box. Avoid using `offset`, correlation IDs, payloads, exception messages, or header values as metric labels due to high cardinality.

### Signals for Pinpointing Root Causes

| Symptom | Possible Cause | What to Inspect |
| --- | --- | --- |
| Compiler reports `MESSAGE_KEY` does not exist | Constant removed in Spring Kafka 3.x | Switch to `KEY` |
| Listener throws required-header exception on null key | `RECEIVED_KEY` header absent | `required=false` and null-key contract |
| Consumer receives `byte[]` instead of `String` | Mapper or raw header contract mismatch | Header mapper, `rawMappedHeaders`, codec |
| Consumer does not see `__TypeId__` | Deserializer stripped type headers | `removeTypeHeaders` config and pipeline |
| JSON header turns into `NonTrustedHeaderType` | Package missing from trusted list | Whitelist required packages |
| After Jackson 3 upgrade, map value types change | New mapper/serializer/deserializer active | Bean types, dependency tree, fixtures |
| Duplicate header drops first value | Default mapper exposes only last value | Native headers or 4.x multi-value mapping |
| Scalar `@Header` metadata fails in batch listener | Batch passes lists | Switch to batch signature or raw records |
| Publish callback fails to compile | `ListenableFuture` changed to `CompletableFuture` | `whenComplete` / `getRecordMetadata` |
| DLT offset mismatches source | Confusing DLT record offset with original offset | `DLT_ORIGINAL_OFFSET` |
| Retry count stays 1 or absent | Delivery attempt header disabled or wrong type read | Container config and raw/converted view |
| Offset collides after republish? | Offsets are per topic-partition, not event IDs | Use business keys/correlation IDs |

## 26. Production Header/Metadata Upgrade Procedure

A runbook can be divided into the following phases.

### Phase 1 — Inventory

List **all** producers/consumers touching the topic:

- Spring Kafka 2.x, 3.x, 4.x, or direct Kafka clients.
- Other languages: Python, Node.js, Go, .NET.
- Required and optional headers.
- Codecs and payload versions.
- Deserialization/type mapping policies.
- Retry/DLT/re-drive flows, retention, and consumer groups.
- Batch listeners vs. record listeners.

### Phase 2 — Freeze the Contract

Capture sample records containing:

- Native header bytes.
- Kafka key and payload bytes/format.
- Presence/absence of optional headers.
- Duplicate headers if producers can emit them.
- Spring JSON type info headers.
- DLT original headers and exception headers.
- Topic/partition/offset/timestamp from record metadata.

These fixtures must be versioned and stored outside the application release cycle for comparison during upgrades.

### Phase 3 — Build and Compile Migration

Replace `MESSAGE_KEY` → `KEY`, `RECEIVED_MESSAGE_KEY` → `RECEIVED_KEY`, `PARTITION_ID` → `PARTITION`, and `RECEIVED_PARTITION_ID` → `RECEIVED_PARTITION` when moving from 2.x to 3.x. Migrate `KafkaTemplate` futures from `ListenableFuture` to `CompletableFuture`.

When moving from 3.x to 4.x and adopting Jackson 3, identify the new serializer/header mapper classes. Never mix APIs from different versions in a runnable example without verifying packages.

### Phase 4 — Contract and Integration Tests

Run unit tests for native headers, mapper round-trips, and mixed-version broker tests. Test null keys, duplicate headers, UTF-8, header type metadata, DLT, and delivery attempts. Record output record metadata.

### Phase 5 — Canary and Rolling Deployment

Deploy compatible consumers reading **both old and new headers** if the contract changes. Next upgrade producers with a dual-write phase. Monitor conversion failures, DLT rates, lag, and header contract logs with clear rollback thresholds.

### Phase 6 — Conditional Removal of Compatibility Shims

Only after no old consumers remain and retained records/backlogs no longer require old fields should dual-write/fallbacks be removed. Document the contract so downstream teams know wire header types and metadata meanings.

## 27. Design Mistakes to Avoid

### 27.1. Treating a Kafka Header as a String

Kafka headers on the wire are bytes. Decoding with the wrong charset or confusing JSON bytes with raw text causes subtle bugs. Always follow a contract-defined codec.

### 27.2. Treating `KafkaHeaders.RECEIVED_*` as Producer-Sent Native Headers

These are Spring Messaging constants representing incoming record attributes. When using `ConsumerRecord` directly, read metadata from the record. Never hardcode synthetic names into cross-language contracts.

### 27.3. Renaming Constants Without Checking Send vs. Receive Direction

`KEY` is outbound; `RECEIVED_KEY` is inbound. Swapping them can compile cleanly yet break conversion paths.

### 27.4. Reading Required `@Header` When the Header Is Optional

Incoming keys can be null, retry/delivery attempt headers may not be enabled, and business headers may be absent in historical records. Use `required=false` or nullable APIs with an explicit missing-header policy.

### 27.5. Relying on Java Class Names as a Schema Contract

`__TypeId__` and `spring_json_header_types` are framework-internal metadata, not semantic schema versions. Class/package refactors or Jackson upgrades can break interoperability.

### 27.6. Opening Trusted Packages with Uncontrolled Wildcards

Setting `trusted.packages=*` to silence deserialization errors widens the surface for instantiating objects from external data. Whitelist specific packages or use a fixed target type/schema.

### 27.7. Losing Duplicate Headers Through Mappers

Native Kafka supports multiple values, whereas Spring `MessageHeaders` does not automatically represent duplicates by default. In 4.x, configure multi-value explicitly; in 3.x, read native headers when the contract requires duplicates.

### 27.8. Confusing Source Record Offsets with DLT/Output Record Offsets

Offsets have meaning only within a single **topic-partition**. Republished records receive new offsets. Use origin headers or business IDs to link events, never a single offset as a global ID.

### 27.9. Putting Oversized Headers or Secrets on Records

Kafka headers count toward message size and can be copied through retries/DLTs. Never embed arbitrary stack traces, full payloads, tokens, or sensitive info in custom headers. Watch message size limits and retention.

### 27.10. Testing Only the Payload

An application may parse JSON fine yet lose correlation IDs or DLT origins. Upgrade tests must assert **headers and metadata**, not only message counts and business payloads.

## 28. Hands-On Exercises

**Exercise 1 — Reading native headers.** Write a producer sending `x-correlation-id` and `x-schema-version` as UTF-8 bytes. Have the consumer accept `ConsumerRecord`, decode them, and log topic/partition/offset/timestamp. Test a record missing one header.

**Exercise 2 — Migrating `KafkaHeaders`.** Find and replace legacy constants `MESSAGE_KEY`, `PARTITION_ID`, `RECEIVED_MESSAGE_KEY`, and `RECEIVED_PARTITION_ID` with their new names. Explain which apply to producers and which to consumers.

**Exercise 3 — Null key.** Publish a record with a null key; write a listener with required `@Header(RECEIVED_KEY)` and observe the error. Switch to `required=false` and verify proper handling.

**Exercise 4 — `ConsumerRecordMetadata`.** Write two equivalent listeners: one using individual `@Header` parameters and one using `ConsumerRecordMetadata`. Compare topic/partition/offset for the same record.

**Exercise 5 — Producer output `RecordMetadata`.** Publish a message and handle `CompletableFuture<SendResult>`; log output metadata. Do not equate output offset with input offset when building consume-transform-produce pipelines.

**Exercise 6 — Raw vs. JSON mapper.** Create an `x-attempts` header as String and Integer in Spring Messaging. Inspect bytes after outbound conversion and inbound types; then send a raw record without `spring_json_header_types` to see what type the consumer receives.

**Exercise 7 — Jackson type headers.** Use the JSON serializer with type metadata. Toggle `remove.type.headers` on the version-appropriate deserializer, observe headers reaching the listener, and write an independent `x-schema-version` contract.

**Exercise 8 — Duplicate headers.** Send a record containing two `x-route` headers and read them with `headers(name)` and `lastHeader`. If using Spring Kafka 4.x, configure `setMultiValueHeaderPatterns(...)` and verify `List<?>` after conversion.

**Exercise 9 — DLT provenance.** Intentionally throw an exception in the listener until the record lands in the DLT. Compare the DLT offset with `DLT_ORIGINAL_OFFSET`; then re-drive the DLT and verify expected source identity is preserved.

**Exercise 10 — Mixed-version rollout.** Use two producer/consumer versions or two mapper configurations. Run old→old, old→new, new→old, and new→new combinations using fixtures with Unicode, null keys, and optional headers.

**Exercise 11 — Batch listener.** Convert a record listener to a batch listener using metadata lists or `List<ConsumerRecord>`. Verify headers and offsets for each message never shift when null keys are present.

**Exercise 12 — Operations runbook.** Design `errorCategory` logs for `MISSING_HEADER`, `TYPE_CONVERSION_FAILED`, `UNTRUSTED_TYPE`, and `DLT_ORIGIN_MISSING`. Write canary rollback instructions if error rates spike after an upgrade.

## 29. Conclusion

When upgrading Spring Kafka, **headers and record metadata are part of the compatibility contract**, not minor payload details. Changes in `KafkaHeaders`, header mappers, Jackson serializers/deserializers, batch listeners, or DLT recoverers can cause an application to misread **keys, offsets, correlation IDs, type metadata, or failed-record origins** even while the Kafka broker runs normally.

Principles for safe upgrades:

- Distinguish **native Kafka headers (`String` → `byte[]`)**, **Spring `MessageHeaders`**, and **`ConsumerRecord`/`RecordMetadata`**.
- Use the exact `KafkaHeaders` constant names for your version; pay special attention to names removed in 3.0.
- Define business headers via a **stable wire contract**: names, codecs, required/optional status, duplicate policy, and schema version.
- Understand that Spring JSON type headers and header type mapping do not replace a business schema contract; trust only necessary packages.
- On Spring Kafka 4.x, verify Jackson 3 and how **multi-value header mapping** is configured if data uses duplicate headers.
- Verify metadata of **received records**, **published records**, and **DLT origins** in tests and observability.
- Execute bidirectional-compatible migrations during rolling upgrades and inspect backlogs/retention before removing fallbacks.

A test showing only that JSON payloads parse without errors is insufficient. Kafka reliability also depends on producers and consumers sharing the same understanding of headers, offsets, schemas, retries, and record provenance across application versions.

### References

- [Spring Kafka Reference — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
- [Spring Kafka Reference — Listener Annotation / Consumer Record Metadata](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring Kafka Reference — Sending Messages / SendResult](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka Reference — Serialization, Deserialization, and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring Kafka Reference — Change History (KafkaHeaders, Jackson 3, multi-value headers)](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
- [Spring Kafka Reference — Handling Exceptions and Dead-letter Headers](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Reference — Non-blocking Retry Header Management](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html)
- [Spring Kafka Javadoc — KafkaHeaders](https://docs.spring.io/spring-kafka/docs/4.0.0/api/org/springframework/kafka/support/KafkaHeaders.html)
- [Apache Kafka — Record Headers API](https://kafka.apache.org/40/javadoc/org/apache/kafka/common/header/Headers.html)
