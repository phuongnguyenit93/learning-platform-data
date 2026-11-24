# KafkaTestUtils.consumerProps

`KafkaTestUtils.consumerProps()` is a utility from the `spring-kafka-test` module used to quickly build a `Map<String, Object>` containing basic properties for a Kafka consumer in tests. This method helps tests connect to the broker, select a consumer group, and set common defaults needed when reading records just sent by the test.

Remember that `consumerProps()` **only creates configuration**. It does not instantiate a consumer, subscribe to topics, poll records, or automatically assert results. After receiving the map, the test still needs to create a `KafkaConsumer` or `DefaultKafkaConsumerFactory`, subscribe to topics, and use `KafkaTestUtils.getSingleRecord()` or `getRecords()` to read data.

## 1. Adding the Testing Dependency

If the project uses Spring Boot, add the Kafka testing starter with `test` scope:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

For Spring Kafka projects not using the Spring Boot starter, add `spring-kafka-test` with a version compatible with `spring-kafka`:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Classes commonly used in tests:

| Class | Role |
|---|---|
| `EmbeddedKafkaBroker` | Provides broker addresses and manages the embedded Kafka broker |
| `KafkaTestUtils` | Builds consumer/producer properties, polls records, and reads offsets |
| `DefaultKafkaConsumerFactory` | Creates a Kafka consumer from a configuration map |
| `ConsumerRecord` | Represents a record received by a consumer |
| `KafkaTemplate` or `KafkaProducer` | Sends records to prepare test data |

Spring Kafka now uses JUnit Jupiter in its testing guides; recent versions no longer support JUnit 4. With Kafka 4.0, the embedded broker moved completely to KRaft and `EmbeddedKafkaKraftBroker` is the implementation used.

## 2. What Does `consumerProps()` Return?

The method takes broker information, a consumer group, and auto-commit mode, then creates a property map for the consumer. In Spring Kafka 4.x, the main overloads are:

```java
// Using EmbeddedKafkaBroker directly
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka, "orders-test", false);

// Using a bootstrap servers string
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka.getBrokersAsString(),
                "orders-test", false);

// Since Spring Kafka 3.3: auto-commit defaults to false
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka.getBrokersAsString(),
                "orders-test");
```

Meaning of the parameters:

- `embeddedKafka` or `brokers`: the broker the consumer connects to. With an embedded broker, the address is typically obtained via `getBrokersAsString()`.
- `group`: the consumer group used in the test. Use a separate group per scenario so offsets from previous tests do not affect results.
- `autoCommit`: enables or disables `enable.auto.commit`. Most tests need `false` to explicitly control when offsets are committed.

In current versions, the method returns `Map<String, Object>`, not `Properties` and not an already-created `Consumer`.

## 3. Default Values Configured

`consumerProps()` builds a basic configuration and sets several convenient test defaults. In the current implementation, the main properties are:

| Kafka Property | Configured Value | Meaning |
|---|---|---|
| `bootstrap.servers` | Passed-in broker address | Target connection for the consumer |
| `group.id` | Value of `group` | Consumer group identifier |
| `enable.auto.commit` | Per the `autoCommit` parameter | Whether offsets are committed automatically |
| `auto.commit.interval.ms` | `10` | Auto-commit interval when auto-commit is enabled |
| `session.timeout.ms` | `60000` | Consumer session timeout |
| `key.deserializer` | `IntegerDeserializer` | Default key in utility examples is Integer |
| `value.deserializer` | `StringDeserializer` | Default value is String |
| `auto.offset.reset` | `earliest` | Reads from the beginning if the group has no valid committed offset |

Since Spring Kafka 2.5, `consumerProps()` sets `auto.offset.reset=earliest`. This helps a new consumer read records that the test sent before the consumer started. If `latest` were used, a new consumer might only read records sent after it started reading.

`earliest` applies only when the group has no committed offset or the current offset is no longer valid. If reusing a group that already has a committed offset, the consumer resumes from that offset; setting `earliest` does not automatically rewind the group to the start of the topic.

## 4. API Differences Across Spring Kafka Versions

The signature of `consumerProps()` changed in Spring Kafka 4.0. When upgrading dependencies, check the overload being used to avoid deprecation warnings or compilation errors.

| Version | Typical Signature | Status |
|---|---|---|
| 3.2.x and earlier | `consumerProps(String group, String autoCommit, EmbeddedKafkaBroker broker)` | Legacy signature |
| 3.2.x and earlier | `consumerProps(String brokers, String group, String autoCommit)` | Legacy signature |
| Since 3.3 | `consumerProps(String brokers, String group)` | Auto-commit defaults to false |
| Since 4.0 | `consumerProps(EmbeddedKafkaBroker broker, String group, boolean autoCommit)` | New API |
| Since 4.0 | `consumerProps(String brokers, String group, boolean autoCommit)` | New API |

The two overloads taking `String autoCommit` and the overload taking `group, autoCommit, EmbeddedKafkaBroker` were deprecated for removal in Spring Kafka 4.0.0. When using 4.x, prefer the new overload taking `boolean`:

```java
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka, "orders-test", false);
```

If the project still uses Spring Kafka 3.2 or earlier, use the String-parameter signature provided by that version:

```java
Map<String, Object> props =
        KafkaTestUtils.consumerProps("orders-test", "false", embeddedKafka);
```

Do not copy Spring Kafka 4.x examples into a 3.x project without checking the dependency. Conversely, once upgraded to 4.x, migrate away from the deprecated String overloads.

## 5. Creating a Consumer from the Configuration Map

The basic workflow consists of four steps:

1. Obtain the running broker from `EmbeddedKafkaBroker`.
2. Call `consumerProps()` to build the map.
3. Pass the map into `DefaultKafkaConsumerFactory` and create a consumer.
4. Subscribe to a topic or use the embedded broker helper to assign partitions, then poll records.

```java
Map<String, Object> consumerProperties =
        KafkaTestUtils.consumerProps(embeddedKafka, "orders-test", false);

DefaultKafkaConsumerFactory<Integer, String> consumerFactory =
        new DefaultKafkaConsumerFactory<>(consumerProperties);

Consumer<Integer, String> consumer = consumerFactory.createConsumer();
```

The newly created consumer does not automatically read topics. With an embedded broker, you can use:

```java
embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");
```

This helper assigns the consumer to the topic and seeks the assigned partitions to the beginning. If using a raw Kafka consumer directly, call `subscribe()` or `assign()` before calling `poll()`.

Close the consumer after the test completes to release sockets, heartbeat threads, and other resources. Prefer try-with-resources:

```java
try (Consumer<Integer, String> consumer = consumerFactory.createConsumer()) {
    embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");
    // poll and assert here
}
```

## 6. Complete Example with Embedded Kafka and JUnit Jupiter

The following example sends a record with an Integer key and String value, then creates a consumer using `consumerProps()` to receive that exact record. The test uses a dedicated topic and a new group.

```java
@SpringJUnitConfig
@EmbeddedKafka(partitions = 1, topics = "orders")
class KafkaConsumerPropsTest {

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Test
    void shouldConsumeRecordUsingConsumerProps() throws Exception {
        // Prepare record before creating the consumer.
        try (Producer<Integer, String> producer = new KafkaProducer<>(
                KafkaTestUtils.producerProps(this.embeddedKafka))) {

            producer.send(new ProducerRecord<>("orders", 42, "created"))
                    .get(10, TimeUnit.SECONDS);
        }

        Map<String, Object> consumerProperties = KafkaTestUtils.consumerProps(
                this.embeddedKafka, "orders-test", false);

        DefaultKafkaConsumerFactory<Integer, String> consumerFactory =
                new DefaultKafkaConsumerFactory<>(consumerProperties);

        try (Consumer<Integer, String> consumer = consumerFactory.createConsumer()) {
            this.embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");

            ConsumerRecord<Integer, String> received = KafkaTestUtils.getSingleRecord(
                    consumer, "orders", Duration.ofSeconds(10));

            assertThat(received.key()).isEqualTo(42);
            assertThat(received.value()).isEqualTo("created");
            assertThat(received.topic()).isEqualTo("orders");
            assertThat(received.partition()).isZero();
        }
    }
}
```

`producerProps()` is also a `KafkaTestUtils` utility; it builds default producer properties for an Integer/String pair. In the example, the producer sends the record before the consumer is created. `auto.offset.reset=earliest` together with the helper seeking the topic to the beginning lets the consumer read the existing record.

`getSingleRecord()` waits for a record on the topic and requires receiving exactly one record. The overload taking `Duration` sets an explicit wait limit; the overload without `Duration` uses a longer default timeout. If no record is received or more than one record for that topic is received in the poll, the helper fails instead of returning an ambiguous result.

## 7. Changing Deserializers and Other Properties After Calling the Helper

`consumerProps()` is designed for an `<Integer, String>` consumer. If the test's key or value uses different types, replace the corresponding deserializers in the map before creating the consumer.

Example test using String for both key and value:

```java
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka, "string-orders-test", false);

props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);

ConsumerFactory<String, String> factory = new DefaultKafkaConsumerFactory<>(props);
```

For JSON payloads or domain types, configure the matching deserializer, type information, and trusted packages consistent with the serializer the producer uses. Do not leave the default `IntegerDeserializer` when the producer actually sends String keys; deserialization errors may occur during polling and fail the test before assertions run.

Any property can be overridden after receiving the map:

```java
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka, "orders-test", false);

props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 5);
props.put(ConsumerConfig.CLIENT_ID_CONFIG, "orders-test-client");
```

Values set by the test after calling the helper overwrite entries with the same key. Use `ConsumerConfig` constants to avoid typos in property names.

## 8. Choosing Auto Commit vs. Manual Commit in Tests

The `autoCommit` parameter controls `enable.auto.commit`:

| Value | Behavior | When to Use |
|---|---|---|
| `false` | Consumer does not commit offsets periodically | Testing record processing, retries, manual commits, and deterministic offsets |
| `true` | Consumer commits offsets automatically per `auto.commit.interval.ms` | Only when tests need to verify auto-commit behavior |

Normally pass `false`. Tests can commit explicitly after processing:

```java
Map<String, Object> props =
        KafkaTestUtils.consumerProps(embeddedKafka, "manual-commit-test", false);

try (Consumer<Integer, String> consumer =
             new DefaultKafkaConsumerFactory<Integer, String>(props).createConsumer()) {

    embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");
    ConsumerRecord<Integer, String> record =
            KafkaTestUtils.getSingleRecord(consumer, "orders", Duration.ofSeconds(10));

    process(record);
    consumer.commitSync();
}
```

When `autoCommit=true`, the helper sets `auto.commit.interval.ms=10`. A short commit interval can cause offsets to change while the test is inspecting them. Therefore, do not enable auto-commit just to let a consumer read records; `auto.offset.reset=earliest` already handles groups without offsets.

## 9. Combining with Other KafkaTestUtils Helpers

`KafkaTestUtils` provides several helpers to reduce boilerplate in tests:

| Method | Purpose |
|---|---|
| `consumerProps(...)` | Creates a consumer configuration map |
| `producerProps(...)` | Creates a producer configuration map |
| `getSingleRecord(consumer, topic)` | Polls and requires exactly one record from the topic |
| `getSingleRecord(consumer, topic, timeout)` | Same, with an explicit timeout |
| `getRecords(consumer)` | Polls and returns `ConsumerRecords` |
| `getRecords(consumer, timeout)` | Polls with an explicit timeout |
| `getCurrentOffset(...)` | Reads the committed offset of a group/topic/partition |
| `getEndOffsets(consumer, topic, partitions...)` | Retrieves end offsets of partitions |

Example checking the committed offset after the consumer commits:

```java
OffsetAndMetadata offset = KafkaTestUtils.getCurrentOffset(
        embeddedKafka.getBrokersAsString(),
        "orders-test",
        "orders",
        0);

assertThat(offset).isNotNull();
assertThat(offset.offset()).isEqualTo(1L);
```

The committed offset is the next position the consumer group will read, not the offset of the record just processed. If the read record had offset `0` and the commit succeeded, the committed offset is normally `1`.

## 10. Avoiding Data Contamination from Previous Runs

An embedded broker can be shared across multiple test classes to reduce startup time. When sharing a broker, data on topics also persists while the broker remains running. You must control the starting read position and consumer groups.

- Prefer a separate topic per test or scenario so old records do not skew expected counts.
- Use a separate group ID per test if `auto.offset.reset=earliest` must take effect.
- `consumeFromAnEmbeddedTopic()` and related helpers typically seek assigned partitions to the beginning after assignment. If reusing a topic and wanting only new records, use the overload supporting `seekToEnd=true` when provided by your version, or explicitly seek to the end before sending test data.
- Do not rely on `auto.offset.reset=earliest` to reset a group that already has a valid committed offset.
- Close consumers, producers, and test resources after each scenario; if sharing a broker, let the framework manage the broker lifecycle at the test suite level.

When tests run in parallel, use distinct topics/groups or isolate data another way. If two tests write to and read from the same topic, `getSingleRecord()` can receive multiple records and fail as designed.

## 11. Common Errors

| Symptom | Cause | Solution |
|---|---|---|
| Cannot read records sent before consumer creation | Using a group that already has offsets or `auto.offset.reset` is not `earliest` | Use a new group and check the reset policy |
| `SerializationException` or `RecordDeserializationException` | Default deserializers do not match key/value types | Override `KEY_DESERIALIZER_CLASS_CONFIG` and `VALUE_DESERIALIZER_CLASS_CONFIG` |
| `getSingleRecord()` reports no records | Not subscribed/assigned, wrong topic, producer send not completed, or timeout too short | Check topic, await send completion, and increase timeout reasonably |
| `getSingleRecord()` reports multiple records | Topic/group shared with another test or stale data | Use separate topics/groups, or seek to end before sending |
| Test offset changes unexpectedly | `autoCommit=true` or group already has a committed offset | Use auto-commit false and a new group |
| Does not compile after upgrading to Spring Kafka 4.x | Still calling an overload taking `String autoCommit` | Switch to the overload taking `boolean` or `consumerProps(broker, group, boolean)` |
| Consumer stays open after test | Consumer or producer not closed | Use try-with-resources and clear lifecycle management |

## 12. Key Takeaways

- `KafkaTestUtils.consumerProps()` returns a consumer configuration `Map<String, Object>`; it does not create or start a consumer itself.
- The helper defaults to Integer keys, String values, `auto.offset.reset=earliest`, and accepts `autoCommit` as a parameter.
- Since Spring Kafka 2.5, the helper sets `earliest`; this helps new groups read records sent before the consumer started.
- Since Spring Kafka 4.0, prefer overloads taking `boolean`; legacy overloads taking `String autoCommit` are deprecated for removal.
- After calling the helper, you can override deserializers, `auto.offset.reset`, `max.poll.records`, and other properties before creating the consumer.
- Use `autoCommit=false` to control offsets in most tests; use `getSingleRecord()` or `getRecords()` to read results.
- Use dedicated topics/groups, watch for the embedded broker helper seeking to the beginning, and always close consumers after tests.

## References

- [Spring for Apache Kafka 4.1 — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [KafkaTestUtils — Spring Kafka 4.0 API](https://docs.spring.io/spring-kafka/docs/4.0.x/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [KafkaTestUtils — Spring Kafka 3.2 API](https://docs.spring.io/spring-kafka/docs/3.2.x/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [Spring Kafka — EmbeddedKafkaBroker API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/test/EmbeddedKafkaBroker.html)
