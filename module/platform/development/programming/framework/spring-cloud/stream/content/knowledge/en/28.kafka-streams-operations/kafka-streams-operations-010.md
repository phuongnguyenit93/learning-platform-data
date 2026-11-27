# Testing Topologies with TopologyTestDriver

Kafka Streams processes records using a topology made up of sources, processors, state stores, and sinks. Whenever you change filtering logic, key selection, aggregations, joins, or time windows, you need to verify the output of the entire processing chain. `TopologyTestDriver` provides an in-JVM topology testing environment: tests feed records into input topics, the topology processes them synchronously, and tests then read outputs and query state stores.

`TopologyTestDriver` is ideal for verifying processing logic and state quickly and deterministically. It does not launch a real Kafka broker, nor does it simulate consumer group assignment or replication. Therefore, use it to test topology behavior, and complement it with Kafka integration tests when verifying binder configuration and broker behavior.

## 1. What Problem Does TopologyTestDriver Solve?

A Kafka Streams application can be written with the Streams DSL or the Processor API. Either way, the application ultimately produces a `Topology`. `TopologyTestDriver` takes that topology and simulates reading records from sources, running processors, updating state stores, and writing records to sinks.

A typical test follows these steps:

1. Build a topology matching the logic running in the application.
2. Instantiate `TopologyTestDriver` with the required Streams configuration.
3. Create a `TestInputTopic` for each input topic along with its serializers.
4. Feed records using `pipeInput` or `pipeRecordList`.
5. Create a `TestOutputTopic` for each output topic along with its deserializers.
6. Read output records and assert keys, values, timestamps, or headers.
7. Query state stores to verify post-processing state.
8. Close the driver to release resources.

~~~mermaid
flowchart LR
    A["TestInputTopic<br/>pipeInput"] --> B["TopologyTestDriver"]
    B --> C["Source"]
    C --> D["Processor / DSL"]
    D --> E["State store"]
    D --> F["Sink"]
    F --> G["TestOutputTopic<br/>assert output"]
    E --> H["Query state store"]
~~~

The driver processes inputs synchronously. When a test calls `pipeInput`, the record passes through all relevant processors before the call returns. Tests do not need to wait on consumer threads or polling loops like they do against a real broker.

## 2. Adding the Test Dependency

Kafka provides the `kafka-streams-test-utils` artifact. It is only needed in test scope:

~~~xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-streams-test-utils</artifactId>
    <version>${kafka.version}</version>
    <scope>test</scope>
</dependency>
~~~

The `kafka.version` value must match the `kafka-streams` version your application uses. If the project already uses Spring Boot or dependency management to manage Kafka versions, use that managed version instead of pulling in a mismatched `test-utils` version.

For projects using JUnit 5 and Spring Boot, tests can use `spring-boot-starter-test` for JUnit Jupiter and assertion libraries. `TopologyTestDriver` does not require a Spring `ApplicationContext` or a Kafka broker.

## 3. Extracting Topology Logic for Reuse in App and Tests

In the Spring Cloud Stream Kafka Streams Binder, applications typically declare a `Function` taking a `KStream` and returning a `KStream`. The binder connects input/output bindings to Kafka topics. To test the logic, place the Streams DSL transformations in a plain Java method; both the application's `Function` and the test topology invoke that same method.

Example counting word occurrences:

~~~java
import java.util.Arrays;
import java.util.Locale;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Produced;
import org.apache.kafka.streams.state.KeyValueStore;

public final class WordCountTopology {

    private WordCountTopology() {
    }

    public static KStream<String, Long> countWords(
            KStream<String, String> input) {

        return input
            .flatMapValues(text ->
                Arrays.asList(
                    text.toLowerCase(Locale.ROOT).split("\\W+")
                )
            )
            .groupBy(
                (originalKey, word) -> word,
                Grouped.with(Serdes.String(), Serdes.String())
            )
            .count(
                Materialized
                    .<String, Long, KeyValueStore<Bytes, byte[]>>as("word-counts")
                    .withKeySerde(Serdes.String())
                    .withValueSerde(Serdes.Long())
            )
            .toStream();
    }

    public static Topology buildForTest() {
        StreamsBuilder builder = new StreamsBuilder();

        KStream<String, String> input = builder.stream(
            "input-topic",
            Consumed.with(Serdes.String(), Serdes.String())
        );

        countWords(input).to(
            "output-topic",
            Produced.with(Serdes.String(), Serdes.Long())
        );

        return builder.build();
    }
}
~~~

In the Spring Cloud Stream application, the `Function` reuses the exact same transformation:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WordCountConfiguration {

    @Bean
    Function<KStream<String, String>, KStream<String, Long>> wordCount() {
        return WordCountTopology::countWords;
    }
}
~~~

In the application, the binder reads records from the `wordCount-in-0` binding and sends returned results via `wordCount-out-0`. In tests, `buildForTest` wires the same transformation to `input-topic` and `output-topic` so `TopologyTestDriver` can feed data and read outputs.

Extracting the transformation like this keeps tests focused on real application logic. If you rewrite a separate DSL copy solely for tests, tests may stay green even when the production `Function` is modified or misconfigured.

## 4. Writing Your First Test with Input and Output Topics

A JUnit 5 test can instantiate the driver directly:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import java.util.Properties;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.TestInputTopic;
import org.apache.kafka.streams.TestOutputTopic;
import org.apache.kafka.streams.TopologyTestDriver;
import org.apache.kafka.streams.state.KeyValueStore;
import org.junit.jupiter.api.Test;

class WordCountTopologyTest {

    @Test
    void shouldCountWordsAndUpdateStateStore() {
        Properties props = new Properties();
        props.put(StreamsConfig.APPLICATION_ID_CONFIG, "word-count-test");
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "dummy:9092");

        try (TopologyTestDriver driver =
                new TopologyTestDriver(
                    WordCountTopology.buildForTest(),
                    props
                )) {

            TestInputTopic<String, String> input = driver.createInputTopic(
                "input-topic",
                Serdes.String().serializer(),
                Serdes.String().serializer()
            );

            TestOutputTopic<String, Long> output = driver.createOutputTopic(
                "output-topic",
                Serdes.String().deserializer(),
                Serdes.Long().deserializer()
            );

            input.pipeInput("order-1", "spring cloud spring");

            Map<String, Long> latestCounts = output.readKeyValuesToMap();
            assertEquals(2L, latestCounts.get("spring"));
            assertEquals(1L, latestCounts.get("cloud"));
            assertEquals(2, latestCounts.size());
            assertTrue(output.isEmpty());

            KeyValueStore<String, Long> store =
                driver.getKeyValueStore("word-counts");
            assertEquals(2L, store.get("spring"));
            assertEquals(1L, store.get("cloud"));
        }
    }
}
~~~

In this example, the input topic receives a record with key `order-1` and a word string payload. `flatMapValues` splits the string into words, `groupBy` re-keys by word, and `count` updates occurrence counts. The output consists of `KTable` updates converted into a `KStream`.

`readKeyValuesToMap` returns the latest value per key, which is convenient when verifying only the final state of a table. To inspect every individual update, use `readKeyValuesToList` or `readRecordsToList`; the same key may appear multiple times in the list.

## 5. TestInputTopic and TestOutputTopic

`TestInputTopic` simulates a source topic of the topology. Common ways to feed data:

| Method | Purpose |
|---|---|
| `pipeInput(value)` | Sends a record without specifying a key |
| `pipeInput(key, value)` | Sends a key and value |
| `pipeInput(key, value, timestamp)` | Sends a record with an explicit event timestamp |
| `pipeRecordList(records)` | Sends a list of `TestRecord` instances, optionally with timestamps and headers |
| `pipeKeyValueList(records)` | Sends a list of `KeyValue` pairs |
| `advanceTime(duration)` | Advances the input topic's internal event-time clock |

`TestOutputTopic` offers several reading methods:

| Method | When to Use |
|---|---|
| `readValue` | Only need a single record's value |
| `readKeyValue` | Need a single record's key and value |
| `readRecord` | Need key, value, timestamp, and headers |
| `readValuesToList` | Read all values |
| `readKeyValuesToList` | Read all key/value pairs |
| `readRecordsToList` | Read all records with full metadata |
| `readKeyValuesToMap` | Get the final value per key when verifying table state |
| `isEmpty` | Verify no unread outputs remain |

Choose the reading method matching the output semantics. A `KStream` usually requires verifying the full sequence of events. A `KTable` converted to a `KStream` emits update records; when only the final state matters, a key-indexed map is easier to read.

## 6. Verifying Keys, Values, Timestamps, and Headers

If you only use `readKeyValue`, tests do not see timestamps and headers. For metadata-dependent logic, use `readRecord` or `readRecordsToList`.

Example sending a record with headers and a timestamp:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.time.Instant;

import org.apache.kafka.common.header.internals.RecordHeaders;
import org.apache.kafka.streams.test.TestRecord;

RecordHeaders headers = new RecordHeaders();
headers.add(
    "event_type",
    "order-created".getBytes(StandardCharsets.UTF_8)
);

TestRecord<String, String> record = new TestRecord<>(
    "order-1001",
    "{\"amount\":120}",
    headers,
    Instant.parse("2026-03-10T10:15:00Z")
);

inputTopic.pipeInput(record);

TestRecord<String, Long> outputRecord = outputTopic.readRecord();
assertEquals("order-1001", outputRecord.key());
assertEquals(
    Instant.parse("2026-03-10T10:15:00Z").toEpochMilli(),
    outputRecord.timestamp()
);
~~~

This snippet assumes the topology simply forwards records and preserves timestamps. If the topology changes keys or assigns new timestamps, assert according to that topology's intended behavior.

`TestRecord` can carry headers and timestamps just like a Kafka record. This lets you test processors that inspect `event_type` headers, correlation IDs, or time metadata without sending messages through a broker.

## 7. Testing State Stores

Stateful topologies often do more than emit output. Aggregations update `KTable` state, the Processor API can store data in a `KeyValueStore`, `WindowStore`, or `SessionStore`, and downstream processors can read that state.

`TopologyTestDriver` lets you query state stores after feeding inputs:

~~~java
KeyValueStore<String, Long> counts =
    driver.getKeyValueStore("word-counts");

assertEquals(2L, counts.get("spring"));
assertEquals(1L, counts.get("cloud"));
~~~

You can query a store before sending inputs to test behavior with pre-existing state. However, for stores with changelogs or logging enabled, avoid writing initial state arbitrarily. Prefer building state through input records just as in production. Only pre-populate a store directly when a test genuinely requires baseline state and the store is configured appropriately for it.

Accessible store types:

| Store | Stored Data | Testing Example |
|---|---|---|
| `KeyValueStore` | One current value per key | Order totals by `customerId` |
| `WindowStore` | Values by key and time window | Event counts in a 5-minute window |
| `SessionStore` | Activity sessions by key and time span | User browsing sessions |
| `ReadOnlyKeyValueStore` | Read-only queries for certain topologies/query APIs | Verify query results |

Store names must match the names declared in `Materialized` or the Processor API. If the name is wrong, the driver cannot find the store and the test fails—a helpful safeguard against unintended store renames.

## 8. Testing Event Time and Wall-Clock Time

Kafka Streams uses two kinds of time in processors:

- Event time: the timestamp attached to a record, typically taken from the Kafka record timestamp or a `TimestampExtractor`.
- Wall-clock time: the actual system clock time of the process.

`TopologyTestDriver` controls both clocks. When feeding records with timestamps, event-time punctuation can fire as stream time advances. Wall-clock punctuation must be triggered by advancing the simulated wall clock:

~~~java
import java.time.Duration;
import java.time.Instant;

inputTopic.pipeInput(
    "customer-42",
    "order-created",
    Instant.parse("2026-03-10T10:00:00Z")
);

driver.advanceWallClockTime(Duration.ofSeconds(30));
~~~

Do not confuse `TestInputTopic.advanceTime` with `driver.advanceWallClockTime`:

| Action | Clock Affected | Effect on Stream Time |
|---|---|---|
| `pipeInput` with a new timestamp | Record event time | Can advance stream time when the record is processed |
| `TestInputTopic.advanceTime` | Auto-generated timestamp clock of the input topic | Does not advance stream time until a new record is sent |
| `TopologyTestDriver.advanceWallClockTime` | Simulated wall-clock time | Fires wall-clock punctuation when scheduled time arrives |

Window testing example:

1. Send the first record at `10:00:00`.
2. Send the next record at `10:00:30`.
3. Send a record with a newer timestamp to advance stream time past the window boundary.
4. Verify expected outputs are emitted or state stores are updated properly.
5. Send a late record within the grace period and verify behavior.
6. Send an overly late record and verify the drop or custom handling policy.

Event-time punctuation fires based on timestamps of processed records. Advancing the input clock alone without sending a new record does not advance stream time. For wall-clock punctuation, use `advanceWallClockTime` so tests never depend on real wall-clock sleep.

## 9. Testing Multiple Input Topics and Joins

A topology may read multiple source topics, such as `orders` and `customers`. Create one `TestInputTopic` per source:

Suppose the application declares the following data types and matching Serdes:

~~~java
public record Order(
    String orderId,
    String customerId,
    int amount
) {}

public record Customer(
    String customerId,
    String displayName
) {}
~~~

~~~java
TestInputTopic<String, Order> orders = driver.createInputTopic(
    "orders",
    Serdes.String().serializer(),
    orderSerde.serializer()
);

TestInputTopic<String, Customer> customers = driver.createInputTopic(
    "customers",
    Serdes.String().serializer(),
    customerSerde.serializer()
);

orders.pipeInput(
    "customer-42",
    new Order("order-1001", "customer-42", 120)
);

customers.pipeInput(
    "customer-42",
    new Customer("customer-42", "Lan")
);
~~~

For `KStream`-`KStream` joins, tests must assign appropriate timestamps to both sides and verify records fall within the join window. For `KStream`-`KTable` joins, feed table data before or after stream records according to the business scenario to verify state lookup at processing time.

Because `TopologyTestDriver` processes inputs synchronously, tests can deterministically control record ordering to reproduce left-before-right arrival, right-before-left arrival, out-of-window records, or tombstones deleting keys.

The driver simulates each input topic as a single partition. It is well-suited for testing join logic by key and time, but does not prove real topics are co-partitioned or that all cluster partitions are properly assigned to tasks.

## 10. Testing Repartitioning and Internal Topics

When a topology changes keys and then performs `groupBy` or a join, Kafka Streams may create an internal repartition topic. `TopologyTestDriver` can run topologies containing internal repartitions, letting you verify logical results after redistribution.

You can inspect which topics the topology produced to:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;

Set<String> producedTopics = driver.producedTopicNames();
assertTrue(producedTopics.contains("output-topic"));
~~~

The produced topic list can contain both business topics and internal topics such as repartition or changelog topics. Internal topic names depend on `application.id` and processor/repartition names generated in the topology.

The test driver does not simulate multiple physical partitions. Thus, testing repartitioning with the driver only verifies data flow through the topology and operator outputs. To verify partition counts, partitioners, ACLs, replication factors, or broker creation of internal topics, write an integration test against a Kafka broker.

## 11. Testing the Processor API and Punctuators

`TopologyTestDriver` supports topologies built with the Processor API, including sources, processors, state stores, and sinks. Tests can assert forwarded records, post-processing store state, and punctuation effects.

For a custom processor:

1. Build a topology containing a source and processor.
2. Register the state store with the processor.
3. Use `TopologyTestDriver` to feed records.
4. Read outputs from the sink.
5. Query the store to verify updates.
6. Use input timestamps or `advanceWallClockTime` to trigger schedules appropriately.

If testing an isolated Processor API component, `MockProcessorContext` may fit better. `MockProcessorContext` lets you inspect forwarded records and registered punctuation schedules, but does not run a full topology or automatically trigger punctuators. When testing punctuation execution inside a topology, use `TopologyTestDriver`.

## 12. Configuring Serdes in Tests

`TopologyTestDriver` simulates producers and consumers working with `byte[]`; `TestInputTopic` uses serializers to turn Java objects into bytes and `TestOutputTopic` uses deserializers to read bytes back into objects. Consequently, tests should use the exact same Serdes as the application.

When the topology uses custom types:

~~~java
TestInputTopic<String, Order> input = driver.createInputTopic(
    "orders",
    Serdes.String().serializer(),
    orderSerde.serializer()
);

TestOutputTopic<String, OrderSummary> output = driver.createOutputTopic(
    "order-summaries",
    Serdes.String().deserializer(),
    orderSummarySerde.deserializer()
);
~~~

Common pitfalls:

- Serializer and deserializer using mismatched schemas or versions.
- Key Serde differing from the key type after `selectKey`.
- Wrong value Serde used for aggregate outputs.
- JSON/Avro mapper missing required modules.
- Test-constructed Serde configured differently from the application's Serde.

Verify both round-trip serialization and business outputs. Tests that invoke Java transformation methods directly without serialization will miss serializer/deserializer bugs.

## 13. Testing Errors and Edge-Case Data

`TopologyTestDriver` can verify error-handling branches inside topology logic, such as:

- Records with `null` keys or `null` values.
- Payloads failing business validation after successful deserialization.
- Missing required headers.
- Negative timestamps or timestamps outside valid business bounds.
- Duplicate event IDs.
- Tombstones deleting keys from a `KTable`.
- Late records arriving beyond the grace period.
- Aggregate values exceeding limits or becoming invalid.

However, deserialization errors occur before records enter the topology. The driver uses test-supplied serializers/deserializers and does not fully simulate Kafka consumer exception handlers, retry listeners, or the binder's DLQ. Test deserialization failures, producer failures, and broker authorization with dedicated integration tests.

## 14. Limitations to Understand Before Relying on Tests

`TopologyTestDriver` is fast because it runs no broker. In return, it does not verify cluster or distributed runtime properties.

| Well-Tested with `TopologyTestDriver` | Requires Kafka Broker or Integration Environment |
|---|---|
| Filtering, mapping, `selectKey`, aggregations | Consumer groups and rebalancing |
| Joins and windows with controlled timestamps | Co-partitioning across multiple real partitions |
| Output keys/values/headers/timestamps | Replication factor and leader election |
| State stores and tombstones | ACLs, SASL, TLS, and authorization |
| Event-time and wall-clock punctuation | Broker transactions and coordinator failures |
| Internal topology and repartition logic | Broker internal topic creation, quotas, and topic configs |
| Serdes of tested records | Network connectivity, timeouts, and broker compatibility |
| Processor API logic | Multi-instance assignment and state restoration from changelogs |

Per the Kafka API, the test driver simulates each input topic as a single partition. It also processes records synchronously; `commit.interval.ms` and `cache.max.bytes.buffering` do not behave as they do in a live runtime, because behavior is simulated as if committing/flushing after every input record.

Never rely on `TopologyTestDriver` results alone to conclude an application is ready for deployment. It verifies that the topology handles the scenarios fed into the test.

## 15. When Do You Need Kafka Integration Tests?

Add integration tests when you need to verify:

- Spring Cloud Stream Kafka Streams Binder creates the right bindings and topics.
- Function definitions and binding names map accurately.
- Kafka Streams `application.id` and consumer configurations.
- Real key/value Serdes, schema registry, or native encoding.
- Internal repartition/changelog topics are created by the broker with expected settings.
- Partition counts, partitioners, and co-partitioning.
- Transactions, offsets, exactly-once, and coordinator failures.
- Security, ACLs, TLS, SASL, and topic access permissions.
- Rebalances, state restoration, standby replicas, and multi-instance runs.
- Retries, deserialization exception handlers, and DLQs.

You can run Kafka using Testcontainers or Spring Kafka's `EmbeddedKafka`. For Spring Cloud Stream applications, boot the `ApplicationContext` against a test Kafka broker and verify bindings actually publish/consume on topics. This is a different test layer from `TopologyTestDriver`: integration tests verify the framework, binder, and broker working together.

## 16. Layered Testing Pattern for Spring Cloud Stream Projects

An event-processing project can organize tests into three layers:

| Layer | Tools | Goal |
|---|---|---|
| Business logic unit tests | JUnit, AssertJ, Mockito | Verify pure Java calculation or validation methods |
| Topology tests | `TopologyTestDriver` | Verify pipelines, state stores, timestamps, joins, and outputs |
| Integration tests | Kafka Testcontainers or `EmbeddedKafka`, Spring Boot Test | Verify binder, serialization, brokers, partitions, transactions, and deployment config |

Example package structure:

~~~text
src/
  main/
    java/
      com/example/orders/
        OrderFunctions.java
        OrderTopology.java
  test/
    java/
      com/example/orders/
        OrderFunctionsTest.java
        OrderTopologyTest.java
        OrderBinderIntegrationTest.java
~~~

`OrderFunctionsTest` tests pure Java logic. `OrderTopologyTest` instantiates `TopologyTestDriver` and pipes records through the pipeline. `OrderBinderIntegrationTest` boots the Spring context with a test Kafka broker to verify real bindings and configuration.

## 17. Checklist for Writing a Good TopologyTestDriver Test

- [ ] Test topology invokes the exact same DSL transformations as the production `Function`.
- [ ] Dedicated test `application.id` that does not collide with running applications.
- [ ] Key/value Serdes configured to match real records.
- [ ] One `TestInputTopic` per source topic.
- [ ] One `TestOutputTopic` per output topic being verified.
- [ ] Explicit timestamps used for window, join, or punctuation tests.
- [ ] Both outputs and state stores asserted when the topology is stateful.
- [ ] Empty-output cases verified with `isEmpty`.
- [ ] `TestRecord` read when timestamps or headers must be checked.
- [ ] `TopologyTestDriver` closed after each test.
- [ ] Do not assume the driver tests multi-partitioning or broker behavior.
- [ ] Integration tests added for binder and Kafka behaviors that affect correctness.

## 18. Implementation Workflow

1. Identify the behaviors to test: outputs, state stores, time handling, joins, or data errors.
2. Extract topology transformations into a method shared with the production `Function`.
3. Build the test topology with explicitly named input and sink topics.
4. Add the `kafka-streams-test-utils` dependency matching your Kafka Streams version.
5. Initialize `Properties` with a dedicated `application.id` and appropriate Serde settings.
6. Create `TopologyTestDriver` inside a try-with-resources block.
7. Create `TestInputTopic` and `TestOutputTopic` instances for sources/sinks.
8. Feed representative and edge-case records into the topology.
9. Assert outputs per `KStream` or `KTable` semantics.
10. Query state stores and verify final state values.
11. Drive event time or wall-clock time when the topology uses punctuation/windows.
12. Add integration tests for behaviors dependent on the Kafka broker and Spring binder.

## Official References

- [Apache Kafka 4.4 - Testing a Streams Application](https://kafka.apache.org/44/streams/developer-guide/testing/): `test-utils` dependency, `TestInputTopic`, `TestOutputTopic`, state stores, punctuation, and test limitations.
- [Apache Kafka 4.4 - TopologyTestDriver API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/TopologyTestDriver.html): creating the driver, configuration, input/output topics, state stores, and time control.
- [Apache Kafka 4.4 - TestInputTopic API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/TestInputTopic.html): `pipeInput`, timestamps, and record lists.
- [Apache Kafka 4.4 - TestOutputTopic API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/TestOutputTopic.html): reading `KeyValue`, `TestRecord`, final result maps, and checking output queues.
- [Spring Cloud Stream Kafka Streams Binder Reference](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html): functional programming model, `KStream` bindings, Serdes, and binder configuration.
