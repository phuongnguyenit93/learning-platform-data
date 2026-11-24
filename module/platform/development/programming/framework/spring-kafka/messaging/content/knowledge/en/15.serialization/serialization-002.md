# StringSerializer and StringDeserializer

Kafka stores records as bytes. A producer must convert keys and values from Java types into `byte[]` before sending; a consumer converts the received bytes back into Java types for application processing. The Kafka client provides `StringSerializer` and `StringDeserializer` when keys or values are strings. This is a simple serializer/deserializer pair commonly used for text messages, identifiers, small commands, or JSON payloads represented as strings.

These two classes add no extra data structures or Java type metadata. `StringSerializer` encodes string content into bytes using the configured charset; `StringDeserializer` decodes bytes back into a string using the corresponding charset. Producer and consumer must agree on the byte format. If one side writes UTF-8 while the other decodes using a different charset, characters may become corrupted even though Kafka transmits the record normally.

## 1. Why Are Serializers and Deserializers Needed?

Kafka brokers do not directly understand `String`, `OrderCreated`, or any Java object. A record on the wire consists of byte-encoded keys and values along with metadata such as topic, partition, offset, timestamp, and headers. Therefore, applications need type conversion at both ends:

```text
Producer application
String key/value
      |
      v
StringSerializer
      |
      v
byte[] -----------------------> Kafka broker
                                  stores record in partition
                                      |
                                      v
Consumer application           byte[]
      ^                              |
      |                              v
String key/value <---------- StringDeserializer
```

For strings, the Kafka client provides out of the box:

- `org.apache.kafka.common.serialization.StringSerializer`: converts `String` into `byte[]`.
- `org.apache.kafka.common.serialization.StringDeserializer`: converts `byte[]` into `String`.

When both producer and consumer use this pair, applications can send and receive text without writing custom serializers. However, Kafka does not enforce that every producer writing to the same topic uses the same format. Encoding and payload conventions must still be agreed upon across applications.

## 2. How Does StringSerializer Encode Strings?

`StringSerializer` takes a `String` value and converts it into a byte array. The default charset is UTF-8. For example, the string `hello` is encoded into its corresponding UTF-8 bytes; Vietnamese strings such as `Xin chào Kafka` are also encoded into UTF-8 bytes to preserve accented characters.

Direct usage example:

```java
StringSerializer serializer = new StringSerializer();

byte[] bytes = serializer.serialize("notifications", "Xin chào Kafka");

System.out.println(Arrays.toString(bytes));
```

In this example, the first parameter is the topic name and the second is the string data. The serializer returns a `byte[]` for the Kafka producer to send. Normal applications do not need to call the serializer directly because `KafkaProducer` or Spring Kafka invokes it based on configuration.

`StringSerializer` also handles `null`: if the input data is `null`, the serializer returns `null` rather than a byte array. An empty string `""` is a different case: it is encoded as a zero-length byte array. This distinction matters for Kafka compacted topics, where a record with a key and a `null` value can serve as a tombstone marking key deletion.

## 3. How Does StringDeserializer Decode Bytes into Strings?

`StringDeserializer` performs the reverse operation. It receives bytes from Kafka and constructs a `String` using the configured charset. The default is also UTF-8.

```java
StringDeserializer deserializer = new StringDeserializer();

String value = deserializer.deserialize(
        "notifications",
        "Xin chào Kafka".getBytes(StandardCharsets.UTF_8));

System.out.println(value);
```

If the byte data is `null`, the deserializer returns `null`. If the data is an empty byte array, the result is an empty string. Therefore, when processing messages, distinguish:

| Received value | Meaning |
|---|---|
| `null` | The Kafka record has a `null` key/value at that position; for a value on a compacted topic, it may be a tombstone |
| `""` | A record exists and its payload is an empty string |
| `"hello"` | A record exists and its payload is the text `hello` |

If bytes were created using a charset other than UTF-8 while the deserializer uses UTF-8, characters may be replaced or rendered incorrectly. The deserializer cannot reliably guess the charset used by the producer. The best practice is to standardize on UTF-8 across all producers and consumers.

## 4. Configuring StringSerializer and StringDeserializer in Spring Boot

Spring Boot lets you declare serializer/deserializer classes in `application.yml`. Example where both producer and consumer send/receive strings:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
    consumer:
      group-id: notification-reader
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      auto-offset-reset: earliest
      enable-auto-commit: false
```

In this configuration:

- Both producer key and value have Java type `String`.
- Both consumer key and value are decoded into `String`.
- `group-id` identifies the consumer group reading the topic.
- `auto-offset-reset: earliest` applies only when the group has no valid committed offset or the offset is out of range; it does not cause a group with a valid offset to re-read from the beginning.
- `acks: all` is the producer write acknowledgment policy and is unrelated to how strings are encoded.

If the key is a string while the value is an object or byte array, configure each serializer independently. Keys and values are not required to use the same data type.

## 5. Sending and Receiving Strings with KafkaTemplate and @KafkaListener

Once serializers/deserializers are configured, you can use `KafkaTemplate<String, String>` to send strings:

```java
@Service
public class NotificationPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public NotificationPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String userId, String message) {
        kafkaTemplate.send("notifications", userId, message);
    }
}
```

`userId` is the key and `message` is the value. The key helps route notifications for the same user to the same partition according to the active partitioner. This is useful when preserving per-user event ordering within a partition.

The consumer can receive the string directly:

```java
@Component
public class NotificationListener {

    @KafkaListener(
            topics = "notifications",
            groupId = "notification-reader")
    public void onMessage(String message) {
        notificationService.handle(message);
    }
}
```

If you need the key, partition, and offset for tracing, receive `ConsumerRecord`:

```java
@KafkaListener(
        topics = "notifications",
        groupId = "notification-reader")
public void onMessage(ConsumerRecord<String, String> record) {
    log.info("key={}, partition={}, offset={}, value={}",
            record.key(),
            record.partition(),
            record.offset(),
            record.value());
}
```

In Spring Kafka 3.x, `KafkaTemplate.send()` returns `CompletableFuture<SendResult<K, V>>`. Applications should track the send result when publish confirmation is required; APIs in older Spring Kafka versions may return `ListenableFuture`.

## 6. Configuring Raw KafkaProducer and KafkaConsumer

If you are not using Spring Boot, you can configure the Kafka client directly. Producer:

```java
Properties producerProps = new Properties();
producerProps.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
producerProps.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
producerProps.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());

try (KafkaProducer<String, String> producer =
             new KafkaProducer<>(producerProps)) {
    ProducerRecord<String, String> record =
            new ProducerRecord<>("notifications", "user-42", "Xin chào");
    producer.send(record, (metadata, exception) -> {
        if (exception != null) {
            log.error("Failed to send message", exception);
        } else {
            log.info("partition={}, offset={}",
                    metadata.partition(), metadata.offset());
        }
    });
}
```

Consumer:

```java
Properties consumerProps = new Properties();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "notification-reader");
consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
consumerProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

try (KafkaConsumer<String, String> consumer =
             new KafkaConsumer<>(consumerProps)) {
    consumer.subscribe(List.of("notifications"));

    while (running) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1000));

        for (ConsumerRecord<String, String> record : records) {
            process(record.key(), record.value());
        }

        consumer.commitSync();
    }
}
```

These examples omit imports, logger setup, the `running` flag, and shutdown handling. `try-with-resources` ensures the client is closed upon leaving scope. In real applications, commit only after the corresponding records have been processed successfully; committing on failure can cause records to be skipped on subsequent runs.

## 7. Encoding and Charset Configuration

By default, `StringSerializer` and `StringDeserializer` use UTF-8. The Kafka client provides separate encoding configuration properties for key/value and a shared fallback property:

| Side | Specific properties | Shared property |
|---|---|---|
| Serializer | `key.serializer.encoding`, `value.serializer.encoding` | `serializer.encoding` |
| Deserializer | `key.deserializer.encoding`, `value.deserializer.encoding` | `deserializer.encoding` |

Typically, you should keep UTF-8 on both sides rather than using another charset. If a legacy system requires a different encoding, configure the exact same charset on both the producer and consumer for that field, and test accented and non-ASCII characters.

Example of explicitly converting between strings and bytes using UTF-8 when interacting with byte-level systems:

```java
byte[] payload = message.getBytes(StandardCharsets.UTF_8);
String restored = new String(payload, StandardCharsets.UTF_8);
```

Do not use `new String(bytes)` or `message.getBytes()` without specifying a charset in integration code, because they depend on the JVM/environment default charset and can behave differently across developer machines, containers, and production. When using Kafka `StringSerializer`/`StringDeserializer`, letting the client use UTF-8 by default is usually the simplest and most consistent option.

## 8. StringSerializer Does Not Automatically Convert Objects to JSON

A common misconception is thinking `StringSerializer` can directly send a Java object. This serializer only accepts `String`. To send an object like `OrderCreated`, you must serialize the object to a JSON string first, or use a dedicated serializer such as Spring Kafka `JsonSerializer`, Avro, Protobuf, or a schema-registry serializer.

Example converting an object to a JSON string using Jackson:

```java
String json = objectMapper.writeValueAsString(orderCreated);
kafkaTemplate.send("orders.events", orderCreated.orderId(), json);
```

Consumer receiving the string and parsing JSON:

```java
@KafkaListener(topics = "orders.events", groupId = "order-reader")
public void onOrder(String json) throws JsonProcessingException {
    OrderCreated event = objectMapper.readValue(json, OrderCreated.class);
    orderService.handle(event);
}
```

In this model, Kafka only sees the value as bytes produced from a JSON string. `StringDeserializer` restores the JSON text; Jackson is the component converting JSON into a Java object. Because `StringSerializer` does not add type headers or schema metadata, producer and consumer must agree on JSON structure, field names, data types, and versioning policy.

If payloads need explicit schemas, cross-version compatibility checks, or polyglot support, consider Avro/Protobuf/JSON Schema with a schema registry instead of manually managing contractless JSON strings.

## 9. Keys and Values Can Use Different Serializers

Kafka allows keys and values to have different types. For example, the key is a string `orderId`, while the value is a JSON object serialized by `JsonSerializer`:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
```

In this case, the generic type of `KafkaTemplate` can be `KafkaTemplate<String, OrderCreated>`, not `KafkaTemplate<String, String>`. Make sure the consumer deserializer is compatible with the producer serializer. Changing the value serializer from `String` to a JSON object changes the data contract; older consumers expecting plain strings may fail to read it properly.

## 10. Null, Empty Strings, and Tombstones

With string serializers/deserializers, distinguish `null` from an empty string:

```java
serializer.serialize("customer-state", null); // returns null
serializer.serialize("customer-state", "");  // zero-length byte[]
```

In a topic with `cleanup.policy=compact`, a record with a non-null key and a `null` value is commonly used as a tombstone to mark key deletion. The consumer receives a tombstone as `record.value() == null`. If the application parses JSON or calls `isBlank()` without checking for `null` first, a `NullPointerException` can occur.

Example of explicit handling:

```java
@KafkaListener(topics = "customer-state", groupId = "customer-indexer")
public void onCustomer(ConsumerRecord<String, String> record) {
    if (record.value() == null) {
        customerIndex.delete(record.key());
        return;
    }

    if (record.value().isBlank()) {
        log.warn("Empty payload at partition={}, offset={}",
                record.partition(), record.offset());
        return;
    }

    customerIndex.update(record.key(), record.value());
}
```

Do not treat every `null` value as a tombstone in every topic. The meaning of `null` depends on the topic's contract and producer business logic. On regular topics, `null` might represent invalid data or a custom convention; clarify the contract before handling it.

## 11. Serialization and Deserialization Errors

Producer-side errors can occur when the serializer cannot handle the input data or is misconfigured. With `StringSerializer`, common errors are passing a non-`String` type into a mismatched `KafkaTemplate` generic type, or configuring the wrong serializer class. Beyond conversion errors, sending to the broker can also fail due to network, authorization, timeout, or topic issues.

Consumer-side errors can occur when the deserializer is misconfigured or the incoming bytes do not match the expected encoding/format. If a producer writes a JSON string while the consumer uses `JsonDeserializer` with an incompatible type mapping, the issue is not in `StringDeserializer`; the two sides do not agree on the contract.

Common symptoms:

| Symptom | Possible cause | Resolution |
|---|---|---|
| `ClassCastException` or generic/serializer error | Sent data type does not match configured serializer | Verify `KafkaTemplate<K, V>` and key/value serializers |
| Corrupted Vietnamese characters | Different charsets on producer and consumer, or inconsistent encoding | Standardize on UTF-8 and test Unicode strings |
| Consumer receives `null` | Record has a `null` value, tombstone, or producer sent `null` | Verify contract, key, topic cleanup policy, and producer |
| Consumer receives JSON string but parsing fails | Invalid JSON or different schema/version | Inspect payload, contract, and versioning |
| `SerializationException`/`RecordDeserializationException` | Deserializer cannot read bytes or misconfiguration | Check producer serializer, consumer deserializer, and actual bytes |
| Listener stops on malformed record | Deserialization exception occurs before listener runs | Consider `ErrorHandlingDeserializer` and Spring Kafka error handler |

With Spring Kafka, you can wrap the deserializer with `ErrorHandlingDeserializer` to route deserialization errors into the container's error-handling mechanism instead of letting the client's default behavior stop the consumer outside the listener flow. Example:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
```

Only use this wrapper when the application wants to integrate deserialization failures with an error handler/recoverer. If data is always plain strings under a controlled contract, using `StringDeserializer` directly is simpler. How exceptions are accessed and failed records routed to a dead-letter topic requires configuration compatible with your Spring Kafka version.

## 12. Testing StringSerializer and StringDeserializer

You can run standalone round-trip tests without a broker: serialize a string to bytes and deserialize it back, asserting that the result equals the original string.

```java
class StringSerializationTest {

    private final StringSerializer serializer = new StringSerializer();
    private final StringDeserializer deserializer = new StringDeserializer();

    @Test
    void shouldRoundTripVietnameseText() {
        String input = "Xin chào Kafka – tiếng Việt";

        byte[] bytes = serializer.serialize("test-topic", input);
        String actual = deserializer.deserialize("test-topic", bytes);

        assertEquals(input, actual);
    }

    @Test
    void shouldPreserveEmptyString() {
        byte[] bytes = serializer.serialize("test-topic", "");

        assertEquals(0, bytes.length);
        assertEquals("", deserializer.deserialize("test-topic", bytes));
    }

    @Test
    void shouldPreserveNull() {
        assertNull(serializer.serialize("test-topic", null));
        assertNull(deserializer.deserialize("test-topic", null));
    }
}
```

This is a unit test for serializer/deserializer conversion behavior. For integration testing, send records through a test broker or Embedded Kafka/Testcontainers, then verify key, value, partition, and offset on the consumer. Include tests for Unicode, empty strings, `null`/tombstones if the topic supports compaction, and JSON payloads if the application uses JSON strings.

## 13. Guidelines for Using StringSerializer and StringDeserializer

1. Use default UTF-8 and keep the same encoding across all producers and consumers.
2. Explicitly declare serializers for both key and value; never assume both fields share the same type.
3. Use `KafkaTemplate<String, String>` when both key and value are actually strings.
4. When sending JSON, serialize the object to a JSON string first and parse it on the consumer; `StringSerializer` does not handle objects automatically.
5. Define the contract for `null`, empty strings, and tombstones.
6. Inspect send futures/callbacks and configure an error handler for deserialization failures when needed.
7. Treat changing serializers or payload formats as a contract change between producer and consumer.
8. For data requiring schema evolution or multiple languages, consider schema-based serializers such as Avro/Protobuf/JSON Schema.

## Checklist

- Producer uses `StringSerializer` for the appropriate `String` key/value.
- Consumer uses `StringDeserializer` matching the data written by the producer.
- Both sides agree on UTF-8 or the chosen charset.
- `null` is distinguished from empty strings, and tombstone semantics are understood for compacted topics.
- Objects are not sent directly through `StringSerializer`; convert to a JSON string or use an appropriate serializer.
- Listener handles `null` safely and logs metadata when tracing is needed.
- Round-trip tests cover Unicode, empty strings, and `null`.
- Integration tests cover the producer-consumer contract if the topic is shared across services.

`StringSerializer` and `StringDeserializer` are simple, effective choices when Kafka data is genuinely text. When encoding, key/value types, and payload contracts are aligned, Spring Kafka applications can exchange strings reliably. For structured objects, choose an explicit serialization approach so consumers can read and evolve data safely.
