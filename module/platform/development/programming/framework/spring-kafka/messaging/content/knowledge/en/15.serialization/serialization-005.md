# Declaring a Key Serializer

## Lesson Objectives

In the **Serialization** chapter, this lesson walks through declaring a serializer for Kafka record keys and configuring it in Spring Kafka. A key serializer converts an application's key value into bytes so the Kafka producer can transmit it over the network and use it when routing records to partitions.

**SPRING_KAFKA_MESSAGING** focuses on building event-producing and event-consuming Kafka applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, while helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-letter topics, transactions, exactly-once semantics, concurrency, and testing. The key serializer is part of the data contract between producer and consumer, and also affects how related records are distributed and read in Kafka.

After this lesson, you will be able to:

- Explain the role of the key in a Kafka record.
- Distinguish a key serializer from a value serializer.
- Declare a key serializer using Spring Boot properties and Java configuration.
- Choose a built-in serializer suited to the key type.
- Write a custom serializer when no built-in serializer fits the key type.
- Configure the corresponding key deserializer on the consumer.
- Understand how serialized keys affect partitioning, ordering, and log compaction.
- Test the byte representation, stability, and readability of keys.

## 1. What Is a Key in a Kafka Record?

A Kafka record can contain these main components:

- Topic: the data stream to which the record is sent.
- Partition: the location where the record is stored.
- Key: the value used to identify or group related records.
- Value: the main payload of the record.
- Timestamp: the timestamp associated with the record.
- Headers: additional metadata.

Example of an order event:

~~~text
Topic: commerce.order.created
Key:   order-10001
Value: {"orderId":"order-10001","customerId":"customer-20001"}
~~~

In this example, the key is the order ID. When a producer sends events for the same order with the same key and the default partitioner, Kafka typically routes them to the same partition. This is useful when preserving the order of events for a single order.

A key is not mandatory for every Kafka record. Producers can send records without a key. However, if the business logic requires entity-based routing, per-key ordering, or log compaction, the key should be chosen intentionally.

## 2. What Does a Key Serializer Do?

Kafka stores keys and values as bytes. On the producer side, the serializer converts a Java data type into a byte array before the record is sent to the broker.

For a `String` key:

~~~text
Java key:        "order-10001"
Key serializer:  StringSerializer
Serialized key:  byte[]
~~~

On the consumer side, the key deserializer performs the reverse operation, converting bytes back into a data type the application uses.

~~~mermaid
flowchart LR
    A["Java key: String"] --> B["Key Serializer"]
    B --> C["Serialized key: byte[]"]
    C --> D["Kafka Producer"]
    D --> E["Kafka Broker"]
    E --> F["Kafka Consumer"]
    F --> G["Key Deserializer"]
    G --> H["Java key: String"]
~~~

The key serializer and value serializer are two separate configurations:

| Component | Responsibility | Producer property |
|---|---|---|
| Key serializer | Converts key to bytes | `key.serializer` |
| Value serializer | Converts value to bytes | `value.serializer` |

A producer can use `StringSerializer` for the key and `JsonSerializer` for the value. Keys and values do not need to share the same data type or serializer.

## 3. Declaring a Key Serializer in Spring Boot

The simplest way is to declare serializers in `application.yml`.

Example of an application using `String` for the key and JSON for the value:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer

    consumer:
      group-id: billing-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
~~~

Meaning:

- `key-serializer` specifies the class converting Java keys to bytes.
- `value-serializer` specifies the class converting payloads to bytes.
- `key-deserializer` specifies the class restoring keys on the consumer.
- `value-deserializer` specifies the class restoring payloads on the consumer.

In this example, the key is a `String`, so the producer uses `StringSerializer` and the consumer uses `StringDeserializer`. The value is an event object, so the corresponding JSON serializer/deserializer is used.

Class names must match the dependencies and Spring Kafka/Kafka client versions in your project. When using Avro, Protobuf, or Schema Registry serializers, declare the corresponding libraries and registry configuration.

### 3.1. Using KafkaTemplate with Matching Generic Types

When the key is `String` and the value is `OrderCreated`, declare `KafkaTemplate` with both types:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.send(
            "commerce.order.created",
            event.orderId(),
            event
        );
    }
}
~~~

Generic types express the contract at the Java level:

- `K` is the key type.
- `V` is the value type.

`KafkaTemplate<String, OrderCreated>` must be paired with a `ProducerFactory` whose key serializer is compatible with `String` and whose value serializer is compatible with `OrderCreated`.

Generic types do not choose serializers automatically. The actual serializer is still determined by the producer factory configuration.

### 3.2. Sending Keys via Spring Message

If the application sends using `KafkaTemplate.send(Message<?>)`, the key can be placed in `KafkaHeaders.KEY`:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, "commerce.order.created")
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .build();

kafkaTemplate.send(message);
~~~

The value in `KafkaHeaders.KEY` must be compatible with the key type used by `KafkaTemplate` and the key serializer. If the template declares a `String` key while the header holds another object type, serialization may fail or raise a type error.

## 4. Declaring a Key Serializer with Java Configuration

When creating a `ProducerFactory` manually, you can declare the serializer via producer properties.

~~~java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> orderProducerFactory() {
        Map<String, Object> properties = new HashMap<>();

        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class
        );

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> orderProducerFactory) {
        return new KafkaTemplate<>(orderProducerFactory);
    }
}
~~~

Two important properties:

- `ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG`: declares the serializer for keys.
- `ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG`: declares the serializer for values.

You can pass a serializer instance to the `DefaultKafkaProducerFactory` constructor if direct configuration or custom-configured serializer state is needed. When supplying serializer instances, understand how the producer factory manages and closes serializer resources in your Kafka client version.

Do not declare conflicting key serializer configurations simultaneously across `application.yml`, producer properties, and a custom `ProducerFactory`. Identify which `ProducerFactory` is actually wired into `KafkaTemplate` to know which setting takes effect.

## 5. Commonly Used Built-in Key Serializers

The Kafka client provides several common serializers in the `org.apache.kafka.common.serialization` package.

| Java key type | Serializer | Corresponding deserializer |
|---|---|---|
| `String` | `StringSerializer` | `StringDeserializer` |
| `Integer` | `IntegerSerializer` | `IntegerDeserializer` |
| `Long` | `LongSerializer` | `LongDeserializer` |
| `Short` | `ShortSerializer` | `ShortDeserializer` |
| `Double` | `DoubleSerializer` | `DoubleDeserializer` |
| `Float` | `FloatSerializer` | `FloatDeserializer` |
| `byte[]` | `ByteArraySerializer` | `ByteArrayDeserializer` |

Example using `Long` as the key:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.LongSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.LongDeserializer
~~~

Corresponding `KafkaTemplate`:

~~~java
private final KafkaTemplate<Long, OrderCreated> kafkaTemplate;

public void publish(OrderCreated event) {
    kafkaTemplate.send(
        "commerce.order.created",
        10001L,
        event
    );
}
~~~

If the consumer needs to read the key as a `Long`, it must use `LongDeserializer`. Do not use `StringDeserializer` to read bytes produced by `LongSerializer`, because the two serializers produce different byte representations.

### 5.1. Choosing String or Numeric Types?

`String` is a popular choice for business keys such as order IDs, customer IDs, or account IDs. Strings are easy to read in administration tools and logs, making data investigation convenient.

`Integer` or `Long` fits when the key is genuinely numeric and all producers/consumers agree on the representation. Numeric types typically have fixed-width binary representations that differ from digit strings.

For example, key `10001`:

- `StringSerializer` encodes the character string `"10001"` into UTF-8 bytes.
- `LongSerializer` encodes the numeric value `10001` into the Kafka client's binary representation.

These two representations are incompatible even though they look like the same digits as text.

### 5.2. Choosing ByteArraySerializer

`ByteArraySerializer` fits when the application already has key bytes following a well-defined format. In that case, the producer avoids converting the data type again.

However, using `byte[]` as a key makes the key contract harder to inspect in administrative tooling. Document the format, encoding, and byte-representation version so consumers and external tools can interpret it.

## 6. When Is a Custom Key Serializer Needed?

Built-in serializers suffice for basic data types. If a key is a domain object composed of multiple parts, a custom serializer may be needed.

For example, a system has an order key consisting of a tenant ID and an order ID:

~~~java
public record OrderKey(
    String tenantId,
    String orderId
) {
}
~~~

The application may need a dedicated serializer to convert this object into bytes in a stable format.

A custom serializer must implement `org.apache.kafka.common.serialization.Serializer<T>`:

~~~java
public class OrderKeySerializer implements Serializer<OrderKey> {

    @Override
    public byte[] serialize(String topic, OrderKey data) {
        if (data == null) {
            return null;
        }

        byte[] tenant = data.tenantId()
            .getBytes(StandardCharsets.UTF_8);

        byte[] order = data.orderId()
            .getBytes(StandardCharsets.UTF_8);

        ByteBuffer buffer = ByteBuffer.allocate(
            Integer.BYTES + tenant.length
                + Integer.BYTES + order.length
        ).order(ByteOrder.BIG_ENDIAN);

        buffer.putInt(tenant.length);
        buffer.put(tenant);
        buffer.putInt(order.length);
        buffer.put(order);

        return buffer.array();
    }
}
~~~

The illustrated format consists of:

1. Tenant ID length as an integer.
2. Tenant ID bytes in UTF-8.
3. Order ID length as an integer.
4. Order ID bytes in UTF-8.

Length-prefixed framing avoids ambiguity when a component contains a delimiter character. The example explicitly sets byte order to `BIG_ENDIAN` so the format does not depend on implicit assumptions. In production systems, specify byte order, length bounds, null-string handling, and a format versioning strategy.

### 6.1. Declaring a Custom Serializer

In `application.yml`:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: com.example.kafka.OrderKeySerializer
~~~

Or in Java configuration:

~~~java
properties.put(
    ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    OrderKeySerializer.class
);
~~~

The Kafka client will instantiate and use the declared serializer for producer keys.

If the serializer requires configuration parameters, implement the `configure(Map<String, ?> configs, boolean isKey)` method of the `Serializer` interface. Avoid embedding secrets or environment-specific dependencies directly in serializer code.

### 6.2. Custom Deserializers Must Understand the Same Format

The consumer needs an `OrderKeyDeserializer` capable of reading the exact format produced by `OrderKeySerializer`.

The deserializer must:

- Check for `null` input data.
- Verify sufficient bytes exist before reading lengths.
- Reject negative lengths or lengths exceeding remaining bytes.
- Restore components in the exact order.
- Reject trailing bytes or unsupported formats.
- Raise clear serialization errors when data is invalid.

Do not use `StringDeserializer` for the custom binary key above. The consumer must use a deserializer matching the byte format, otherwise the key will not be restored into `OrderKey` properly.

### 6.3. Avoid Java Native Serialization for Long-Lived Keys

Do not use Java native serialization as a long-term key contract across services. Its byte representation depends on classes, versions, and implementation details, making compatibility fragile as applications evolve.

For business keys, prefer simple and stable formats such as `String`, integers, or a binary format with an explicit schema and versioning rules.

## 7. How Does the Key Serializer Affect Partitioning?

The Kafka partitioner decides which partition receives a record. With the default partitioner and a non-null key, partition selection is based on the serialized key's bytes.

This can be visualized as:

~~~mermaid
flowchart TD
    A["Java key"] --> B["Key serializer"]
    B --> C["Serialized key bytes"]
    C --> D["Partitioner"]
    D --> E["Compute partition"]
    E --> F["Kafka partition"]
~~~

With the default partitioner, Kafka hashes the serialized key bytes to pick a partition among the existing partitions. Therefore:

- The same key and the same serializer generally yield the same bytes.
- The same key bytes and the same partition count generally yield the same partition.
- Two different Java keys that serialize to identical bytes may be treated as the same key at the Kafka layer.
- Changing the serializer or key format can send records for the same entity to a different partition.

Custom partitioners may apply different rules. Therefore, do not assume every producer uses the same algorithm if an application configures a custom `partitioner.class`.

### 7.1. Same Key Preserves Ordering Within a Partition

Consider events for `order-10001`:

~~~text
order-10001 -> OrderCreated
order-10001 -> PaymentAuthorized
order-10001 -> OrderCompleted
~~~

If they are sent with the same key and the partitioner routes them to the same partition, Kafka stores them in write order within that partition. Consumers read the partition in offset order.

This is the basis for processing event sequences per aggregate or business entity.

Kafka does not guarantee global ordering across partitions. If events for the same order are routed to different partitions, consumers cannot rely on offset order to infer their business order.

### 7.2. Changing Partition Count Can Change Key Placement

The default partitioner uses the partition count in its partition selection formula. Increasing the partition count can map the same key to a different partition.

This means:

- Older records for an order may reside in partition 1.
- After increasing partitions, newer records for the same order may be routed to partition 4.
- Two partitions are read independently, so ordering between older and newer records is not guaranteed.

If per-key ordering is critical, carefully evaluate partition expansion and migration strategies. Do not alter partition counts solely for throughput without accounting for the impact on key affinity.

## 8. Null Keys and Keyless Records

Kafka allows records without keys. When a key is `null`:

- The key serializer receives `null` and should return `null`.
- The default partitioner cannot hash a specific key to maintain entity affinity.
- Records are distributed using the partitioner's keyless strategy, commonly sticky partitioning to improve batching.

If the application needs events for the same order to always land in one partition, do not send `null` keys.

Distinguish these cases:

| Key | Value | Meaning |
|---|---|---|
| `null` | Has data | Keyless record |
| Has key | Has data | Record with identifier/key |
| Has key | `null` | Tombstone in a log-compacted topic |
| `null` | `null` | Record carrying neither key nor value; not a keyed tombstone |

In a compacted topic, a tombstone is a record with a non-null key and a `null` value. A tombstone indicates deletion of that key's state in the log compaction model. Do not confuse tombstones with records that have a `null` key.

## 9. Key Serializers and Log Compaction

Kafka supports log compaction to retain the latest state per key within each partition, rather than keeping every record version forever. Compaction does not merge the same key across two different partitions.

Example topic `customer-profile`:

~~~text
Key: customer-01, Value: {"name":"An"}
Key: customer-02, Value: {"name":"Binh"}
Key: customer-01, Value: {"name":"An Nguyen"}
~~~

After compaction in the partition holding these records, Kafka can retain the latest record for `customer-01` along with the record for `customer-02`. This mechanism relies on key bytes; therefore, the key serializer must produce a stable representation for the same entity.

If the same customer ID is sometimes serialized into bytes A and other times into bytes B, Kafka may treat them as two different keys and fail to compact them into a single state.

A tombstone with a specific key and `null` value can mark a key for deletion in a compacted topic. Tombstones are retained according to the broker/topic delete retention and compaction policies.

## 10. Principles for Designing Stable Keys

A key serializer must not only run without error; it must also generate consistent byte representations across the data's lifecycle.

Key principles:

- The same business entity must have a stable key.
- The same logical key must produce the same byte representation.
- Producer and consumer must agree on the format.
- Do not include timestamps or random values in the key if entity affinity is desired.
- Do not serialize objects by relying on an unspecified `toString()`.
- Do not arbitrarily change the key format while a topic holds active data.
- Establish a versioning strategy if the key format must evolve.
- Choose keys with suitable cardinality/distribution to avoid hot partitions.

Examples of suitable keys:

~~~text
order-10001
customer-20001
account-90001
tenant-01:order-10001
~~~

Unsuitable keys when the goal is per-order ordering:

~~~text
2026-11-17T10:00:00
random-uuid-per-event
thread-3
~~~

These values change per record or per runtime instance, causing events for the same order to no longer route by the same key.

## 11. Key Serializers and Schema Evolution

When a key is shared across multiple services, its format is part of the integration contract. Changing the key type or byte representation can affect:

- Partition assignment.
- The consumer's ability to deserialize older data.
- Log compaction.
- Query and data processing tools.
- Downstream systems using the key for joins or grouping.

For example, an older producer used `StringSerializer` for order IDs, and a new producer switches to a custom binary serializer. Even though the logical value is still `order-10001`, the byte representation has changed. New records may be routed to different partitions, and compaction may treat them as distinct keys.

Before changing a serializer, you must:

1. Identify the key format currently stored in the topic.
2. Check all producers writing to the topic.
3. Check consumers and connectors reading the key.
4. Assess partition affinity and ordering impacts.
5. Build a migration plan if byte representations change.
6. Test reading both old and new records during the transition period.

With Avro or Protobuf, serializers often integrate with a schema registry. When using those formats for keys, align on schemas, subject naming, compatibility rules, and how consumers retrieve schemas for deserialization. Never assume changing a key schema will leave partitioning unaffected.

## 12. Security and Data Inside Keys

Keys frequently appear in administrative tools, logs, metrics, or traces. Therefore, do not place secrets inside keys.

Avoid including:

- Passwords or access tokens.
- API keys or session secrets.
- Payment card numbers or directly sensitive data.
- Personal data unnecessary for routing.

If you must route by a sensitive identifier, consider an internal surrogate identifier or a properly designed hash value. However, hashing alone does not guarantee anonymity; values can be brute-forced if the input space is small.

Keys should also stay reasonably sized. Oversized keys increase record size, network transfer, and storage overhead without yielding proportional routing benefits.

## 13. Testing Key Serializers

Testing should include both serializer unit tests and Kafka integration tests.

### 13.1. Unit Tests

For custom serializers, verify:

- Identical inputs produce identical bytes.
- Deserializing the bytes restores the exact object.
- `null` values are handled per contract.
- Empty strings and Unicode characters are handled accurately.
- Corrupted data or truncated bytes are rejected.
- No unintended collisions occur across key pairs.

Example test for `StringSerializer`:

~~~java
class StringKeySerializerTest {

    private final StringSerializer serializer =
        new StringSerializer();

    @Test
    void shouldSerializeKeyAsUtf8() {
        byte[] bytes = serializer.serialize(
            "commerce.order.created",
            "order-10001"
        );

        assertThat(new String(bytes, StandardCharsets.UTF_8))
            .isEqualTo("order-10001");
    }

    @Test
    void shouldReturnNullForNullKey() {
        assertThat(
            serializer.serialize("commerce.order.created", null)
        ).isNull();
    }
}
~~~

### 13.2. Integration Tests with Kafka

Integration tests should verify that the producer writes the expected key and the consumer reads back the expected type.

Steps:

1. Start Kafka via EmbeddedKafka or Testcontainers.
2. Configure the producer key serializer.
3. Send a keyed record.
4. Read the record with a consumer using the matching key deserializer.
5. Verify key, value, topic, and partition.
6. Send multiple records with the same key to verify consistent routing while the partition count is unchanged.

Example verifying the key after reading:

~~~java
ConsumerRecord<String, OrderCreated> record =
    KafkaTestUtils.getSingleRecord(
        consumer,
        "commerce.order.created"
    );

assertThat(record.key()).isEqualTo("order-10001");
assertThat(record.value().orderId()).isEqualTo("order-10001");
~~~

To test partition affinity, send multiple records with the same key and verify they land on the same partition under the same topic, partitioner, and partition count.

Do not use serializer unit tests alone to conclude partitioning is correct. Partitioning must be verified with an actual producer and partitioner configuration.

## 14. Common Errors When Declaring a Key Serializer

| Symptom | Possible cause | Resolution |
|---|---|---|
| `ClassCastException` on send | `KafkaTemplate` generic key type mismatches actual runtime data | Verify `KafkaTemplate<K, V>` and passed key |
| Serializer not found | Wrong class name or missing dependency | Check `key-serializer` and libraries |
| `SerializationException` | Serializer cannot process the key value | Check data type and serialization logic |
| Consumer misreads key | Incompatible key deserializer | Use the deserializer matching the serializer |
| Same entity lands on multiple partitions | Key changes or unstable byte representation | Inspect key value and serializer |
| Key shifts partition after scaling | Partition count changed or partitioner changed | Evaluate ordering and migration plan |
| Compaction keeps multiple records for seemingly same key | Serialized key bytes differ | Inspect key byte format |
| Consumer cannot read older keys | Incompatible key format change | Maintain compatible deserializer or migration |
| Records have no partition affinity | Producer sends `null` keys | Choose a stable business key |
| Records too large | Key contains excessive data | Keep keys short, containing only needed identifiers |

## 15. Complete Practical Workflow

Suppose an Order service emits events and wants all events for the same order routed by order ID.

### Step 1: Choose the Key Type

Choose `String` because order ID is a string identifier:

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {
}
~~~

### Step 2: Configure the Serializer

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

### Step 3: Declare KafkaTemplate

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send(
            "commerce.order.created",
            event.orderId(),
            event
        );
    }
}
~~~

### Step 4: Configure the Matching Consumer

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
~~~

### Step 5: Verify Partition Routing

Send multiple events with the same order ID and inspect the metadata returned by the producer or read records via a consumer. Records sharing the same key should route to the same partition as long as partition count and partitioner remain unchanged.

~~~mermaid
sequenceDiagram
    participant A as Order Service
    participant S as StringSerializer
    participant P as Kafka Partitioner
    participant K as Kafka Broker
    participant C as Billing Consumer

    A->>S: key = order-10001
    S-->>P: UTF-8 bytes
    P->>K: Select partition
    K-->>C: Record with key bytes
    C->>C: StringDeserializer
    C-->>C: key = order-10001
~~~

## 16. Pre-Production Checklist for Key Serializers

- [ ] Have you confirmed whether keys are needed for routing or compaction?
- [ ] Does the key type in `KafkaTemplate` match the passed data?
- [ ] Is `key.serializer` declared in the right `ProducerFactory`?
- [ ] Does the key serializer produce a stable byte representation?
- [ ] Does the consumer use the matching key deserializer?
- [ ] Do producer and consumer agree on the key format?
- [ ] Has `null` key behavior been verified?
- [ ] Is the key concise and free of secrets?
- [ ] Does the same entity use the same key across all events?
- [ ] Have impacts of changing serializers or partition counts been evaluated?
- [ ] If using log compaction, is the key stable and are tombstones properly understood?
- [ ] Does any custom serializer validate malformed data and handle versioning?
- [ ] Have byte representations been unit-tested and partition affinity integration-tested?
- [ ] Do other producers writing to the same topic follow the same key convention?

## Conclusion

A key serializer converts application key values into bytes for the Kafka producer to send records. In Spring Kafka, the serializer is declared via `spring.kafka.producer.key-serializer` or `ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG`; the key type on `KafkaTemplate` must match the chosen serializer. Consumers need a key deserializer that reads the exact byte format.

Key serialization also impacts partitioning, ordering, and log compaction. Therefore, choose stable business keys, produce consistent byte representations, keep producer and consumer compatible, and test both serialization and partition affinity. When a key format must change, assess existing data, active consumers, and record distribution impacts before rolling it out.
