# Limitations of the Test Binder with Transactions, Broker Metadata, and Kafka Streams

The Spring Cloud Stream Test Binder helps quickly test how a function or consumer processes messages without starting Kafka, RabbitMQ, or Pulsar. The Test Binder runs in the same JVM, uses Spring Integration as an intermediary broker, and provides send/receive endpoints for tests. Because there is no real broker, it does not simulate Kafka protocols, metadata, partitions, consumer groups, transactions, or storage mechanics.

A green test with the Test Binder only proves that the application code executed in that test environment behaves as expected. It does not prove that the Kafka Binder created the right topic, the broker accepted a transaction, the consumer committed offsets atomically with output records, or Kafka Streams restored state stores and distributed partitions properly. Choose the tool based on the question you want to verify: the Test Binder for binding/message logic, TopologyTestDriver for Kafka Streams topologies, and a real broker for integration behavior.

## 1. How Does the Test Binder Work?

Spring Cloud Stream provides the `spring-cloud-stream-test-binder` artifact to replace the messaging binder with an in-memory broker backed by Spring Integration. Tests can send messages to input bindings and pull messages from output bindings without a network or external services.

Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Declare `@EnableTestBinder` in the test configuration:

~~~java
@SpringBootTest
@EnableTestBinder
class UppercaseFunctionTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void convertsInputAndPublishesOutput() {
        input.send(new GenericMessage<>(
            "hello".getBytes(StandardCharsets.UTF_8)
        ));

        Message<byte[]> result = output.receive(1_000);

        assertThat(result).isNotNull();
        assertThat(new String(
            result.getPayload(), StandardCharsets.UTF_8
        )).isEqualTo("HELLO");
    }

    @SpringBootApplication
    static class TestApplication {
        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

Tests can verify that a function receives the expected payload, applies business transformations, and emits the expected output. You can send messages with headers, specify destinations when the application has multiple bindings, verify content types, or test output branches.

The Test Binder is well-suited for:

- Testing Supplier, Function, Consumer, and function composition logic.
- Testing payload/header mapping at the binding boundary.
- Testing routing and multiple output channels at the message contract level.
- Testing validation, exception mapping, and broker-independent business logic.
- Running fast, deterministic tests without managing broker processes.

## 2. Why Does the Test Binder Not Replace a Real Broker?

The Test Binder does not start a Kafka broker and does not use a Kafka client to send or receive records. Nor does it create topics, partitions, leaders, replicas, consumer groups, or offsets in Kafka. Consequently, behaviors that only exist when communicating with a broker are outside the scope of these tests.

| Behavior to Verify | Test Binder | Appropriate Tool |
|---|---|---|
| Function transforms payload properly | Yes | Test Binder or unit test |
| Message headers and content types at Spring Message layer | Can verify | Test Binder |
| Kafka topic exists with the right partition count | No | Real Kafka broker |
| Metadata returning leaders, replicas, and partitions | No | Real Kafka broker/AdminClient |
| Consumer group joins, offset commits, and rebalancing | No | Real Kafka broker |
| Producer acknowledgements, client retries, and broker errors | No | Real Kafka broker |
| Kafka transactions and isolation levels | No | Real Kafka broker |
| Kafka Streams topology and state store logic | Does not simulate Kafka Streams runtime | TopologyTestDriver |
| Kafka Streams Binder creates topology, internal topics, and joins group | No | Real Kafka broker |
| ACLs, TLS, SASL, network partitions, and broker failover | No | Compatible integration environment |

The Test Binder can test message-processing code before sending to output. However, it does not prove that output was persisted by a broker, nor that the input offset was committed. Do not use Test Binder results to conclude that the system satisfies at-least-once, exactly-once, or durability requirements.

## 3. Limitations When Testing Kafka Transactions

Kafka transactions link writing one or more output records with committing consumer offsets in a single transaction. When the transaction commits, consumers reading with the appropriate isolation level can see the committed output records. If the transaction aborts, output records belonging to that transaction are hidden from `read_committed` consumers, and the offset is not committed as a successful transaction.

The Test Binder does not run a Kafka transaction coordinator, transactional producer, transaction markers, or consumer isolation levels. Therefore, it cannot verify:

- Whether a transaction is opened and committed/aborted on the broker.
- Whether output records and input offsets are committed atomically.
- Producer fencing when another instance uses the same transactional ID.
- Whether `read_committed` consumers skip records from open or aborted transactions.
- Whether post-rollback retries and dead-lettering execute outside the rolled-back transaction.

You can test separately whether business logic enters the right error branch when an exception occurs, but that is not testing Kafka transactions. To verify transactions, run the real Kafka Binder against a broker that supports transactions.

## 4. Transactional Binder Configuration Must Be Tested with Real Kafka

With the Kafka Binder, enable transactions using a non-empty transaction ID prefix:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: test-orders-
~~~

In a processor application, the consumer starts a transaction; records sent on the consumer thread can participate in the same transaction. When the listener exits normally, offsets are included in the transaction and the transaction is committed. Shared producer properties for the transactional binder live under `spring.cloud.stream.kafka.binder.transaction.producer`; per-binding producer properties are ignored when transactions are enabled.

Each application instance needs a unique transaction ID prefix to avoid transactional ID collisions and fencing. When testing multiple instances, assign a distinct prefix to each instance.

A minimal transaction test should cover two cases:

1. **Commit:** send an input, let the processor publish output and exit normally; a `read_committed` consumer must receive the output and the input offset must be committed.
2. **Abort:** send an input causing the processor to throw an exception after publishing; output from the aborted transaction must not be visible to a `read_committed` consumer, and the input record must remain reprocessable per the retry/rollback policy.

The consumer observing results must set `isolation.level=read_committed`. Default `read_uncommitted` consumers can see uncommitted or aborted records under certain read patterns, so do not use them to assert transactional atomicity.

Note: standard binder retries and dead-lettering do not run the same way when transactions are enabled. Retries move to a post-rollback mechanism in the listener container; dead-lettering also runs after the main transaction rolls back. Verify this configuration and behavior with a real broker rather than inferring from the Test Binder.

## 5. What Is Broker Metadata and What Can the Test Binder Not Check?

Kafka clients fetch metadata from brokers to learn whether a topic exists, how many partitions it has, which broker leads each partition, and which replicas hold the data. The Kafka Binder also needs this information when provisioning bindings, choosing partitions, checking health, and creating or expanding topics.

The Test Binder has no Kafka metadata API. It cannot verify:

- Whether the topic name actually used by a binding exists on the broker.
- Whether the topic has enough partitions for producer partitioning or consumer concurrency.
- Whether metadata reports a leader for every partition.
- Whether replicas and in-sync replicas (ISR) meet durability requirements.
- Whether the broker grants permissions to create topics, add partitions, or read/write topics.
- Whether the binder's auto-create/auto-add partition configuration works.
- Whether clients can fetch metadata over real DNS, TLS, SASL, or network routes.

For example, a binding configuration requiring four partitions may still pass under the Test Binder because no broker checks metadata. When running with the real Kafka Binder against a single-partition topic without auto-add partitions allowed, the application may fail at startup or fail to achieve the expected concurrency.

## 6. Testing Topic and Partition Metadata

The Kafka Binder has properties related to topic provisioning:

| Property | Role |
|---|---|
| `autoCreateTopics` | Allows the binder to create topics if they do not exist |
| `autoAddPartitions` | Allows the binder to increase partition count when needed |
| `minPartitionCount` | Minimum partition count the binder configures for topics where applicable |
| `replicationFactor` | Replication factor for binder-created topics |
| `healthTimeout` | Time to wait for partition metadata before evaluating health |

These properties must be verified against a real Kafka broker. In particular, the binder's `autoCreateTopics` is an application-side setting; it is independent of broker-side `auto.create.topics.enable`. If the broker auto-creates a topic when a client sends a metadata request, the topic may be created with broker defaults instead of the application's intended settings.

Example using Kafka AdminClient to verify a topic has three partitions:

~~~java
try (Admin admin = Admin.create(Map.of(
        AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
        bootstrapServers))) {

    TopicDescription description = admin
        .describeTopics(List.of("orders.events"))
        .topicNameValues()
        .get("orders.events")
        .get(10, TimeUnit.SECONDS);

    assertThat(description.partitions()).hasSize(3);
    assertThat(description.partitions())
        .allSatisfy(partition ->
            assertThat(partition.leader()).isNotNull()
        );
}
~~~

This is a real broker metadata check. It can be extended to verify replicas, ISR, partition leaders, and AdminClient permissions per cluster policy. This check cannot be replaced by sending a message through the Test Binder.

## 7. Kafka Streams Needs Its Own Testing Strategy

The Kafka Streams Binder builds topologies from function signatures such as `Function<KStream<...>, KStream<...>>`, `Consumer<KStream<...>>`, or combinations of KStream/KTable. The standard Test Binder does not create a Kafka Streams runtime, does not create tasks, does not restore state stores from changelogs, and does not join Kafka consumer groups.

Therefore, separate two questions:

- Does the topology compute the right results for input records?
- Does the Kafka Streams Binder connect, deploy the topology, and operate properly on Kafka?

The first question can be tested with `TopologyTestDriver`. The second question requires a real Kafka broker and application tests using the Kafka Streams Binder.

## 8. Using TopologyTestDriver to Test Topology Logic

Kafka provides the `kafka-streams-test-utils` artifact with `TopologyTestDriver`. The driver runs a topology in tests without a Kafka broker; tests can feed records into simulated topics, read outputs, and query state stores.

Maven dependency (use the same Kafka Streams version as the application):

~~~xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-streams-test-utils</artifactId>
    <scope>test</scope>
</dependency>
~~~

Example testing a topology that counts orders by key:

~~~java
StreamsBuilder builder = new StreamsBuilder();
KStream<String, String> orders =
    builder.stream("orders.events");

KTable<String, Long> counts = orders
    .groupByKey()
    .count(Materialized.as("order-counts"));

Topology topology = builder.build();

Properties properties = new Properties();
properties.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "order-count-test"
);
properties.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "dummy:9092"
);
properties.put(
    StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
    Serdes.StringSerde.class
);
properties.put(
    StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
    Serdes.StringSerde.class
);

try (TopologyTestDriver driver =
         new TopologyTestDriver(topology, properties)) {

    TestInputTopic<String, String> input =
        driver.createInputTopic(
            "orders.events",
            Serdes.String().serializer(),
            Serdes.String().serializer()
        );

    input.pipeInput("customer-1", "order-A");
    input.pipeInput("customer-1", "order-B");

    KeyValueStore<String, Long> store =
        driver.getKeyValueStore("order-counts");

    assertThat(store.get("customer-1")).isEqualTo(2L);
}
~~~

TopologyTestDriver is well-suited for testing:

- Filter, map, branch, join, aggregate, and window operations.
- Output records by key/value/timestamp.
- State stores before and after processing.
- Event-time punctuation and wall-clock punctuation controlled in tests.
- Serdes at topic boundaries and null/tombstone cases.

The driver processes records synchronously and simulates single-partition input topics. It does not run a real broker. Thus, this test does not verify consumer groups, rebalancing, partition assignment across instances, broker metadata, replication, or Kafka broker transactions. Certain runtime settings such as commit interval/caching do not take effect the same way as at runtime because the driver processes records synchronously one by one.

## 9. Testing the Kafka Streams Binder with a Real Broker

To verify the binder, start the Spring Boot application alongside a Kafka broker and let the Kafka Streams Binder build and run the topology. Embedded Kafka can be used in test scope:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Example test skeleton:

~~~java
@SpringBootTest(properties = {
    "spring.cloud.stream.kafka.streams.binder.brokers=${spring.kafka.bootstrap-servers}"
})
@EmbeddedKafka(
    partitions = 3,
    topics = {"orders.events", "orders.summary"}
)
class OrderStreamsBinderIntegrationTests {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Test
    void streamsBinderConsumesAndPublishes() throws Exception {
        kafkaTemplate.send(
            "orders.events",
            "order-1",
            "{\"orderId\":\"order-1\",\"total\":120}"
        ).get(10, TimeUnit.SECONDS);

        // Use a test consumer subscribed to orders.summary.
        // Poll with a bounded timeout and assert the actual broker record.
    }
}
~~~

This snippet illustrates starting a test broker and sending input through real Kafka. In a complete test, create a consumer with its own group, configure deserializers matching the schema, poll with a timeout, and assert the output record. You can use `KafkaTestUtils` to build consumer/producer properties and fetch records from the broker.

If the application has `spring-cloud-stream-test-binder` on the test classpath, the test binder may replace the real binder. For tests requiring Embedded Kafka and the real Kafka Binder, exclude `TestSupportBinderAutoConfiguration` in the test class or organize test-binder tests and real-broker tests into separate modules/test contexts:

~~~java
@SpringBootTest(properties =
    "spring.autoconfigure.exclude="
        + "org.springframework.cloud.stream.test.binder.TestSupportBinderAutoConfiguration")
@EmbeddedKafka(
    partitions = 3,
    topics = {"orders.events", "orders.summary"}
)
class RealKafkaBinderTests {
    // Tests exercise the actual Kafka binder.
}
~~~

Do not let the test binder silently claim bindings when the test expects a real broker. When using `@EmbeddedKafka` with a Spring test context, consider `@DirtiesContext` if needed to ensure the application context closes before the broker and avoids JVM shutdown races.

## 10. What Are the Limitations of Embedded Kafka?

Embedded Kafka is a real Kafka broker running inside the test process, so it can test metadata, topics, partitions, consumer groups, offsets, and transactions at an integration level. However, typical setups use a single broker and few replicas. It does not fully represent a multi-broker production cluster.

| Check | Single-Broker Embedded Kafka | Multi-Broker Cluster |
|---|---|---|
| Kafka client connects and fetches metadata | Yes | Yes |
| Binder provisions topics/partitions | Yes | Yes |
| Producer/consumer operation | Yes | Yes |
| Basic Kafka transaction commit/abort | Yes | Yes |
| Replication factor higher than broker count | Cannot verify properly | Yes |
| ISR changes when a broker goes down | No | Yes |
| Leader election and failover across brokers | Limited or non-representative | Yes |
| Broker rack awareness, network partitions, and failure domains | Not representative | Yes |
| Production-like ACL/TLS/SASL | Only if configured explicitly, not by default | Can be tested close to production |

When you need to test basic transaction protocols, Embedded Kafka is useful. When you need to prove durability with replication factors, min ISR, broker failover, or single-node loss, use a multi-broker cluster in Testcontainers or an equivalent integration environment.

## 11. Testing Transactions with a `read_committed` Consumer

A transaction test must observe both output records and offsets/redelivery capability. The consumer checking output should set its isolation level:

~~~java
Map<String, Object> consumerProperties =
    KafkaTestUtils.consumerProps(
        "transaction-verifier",
        "false",
        embeddedKafka
    );

consumerProperties.put(
    ConsumerConfig.ISOLATION_LEVEL_CONFIG,
    "read_committed"
);
~~~

Commit scenario:

1. Send an input record to the topic.
2. The processor starts a transaction, processes, and sends output.
3. The processor exits normally.
4. The `read_committed` consumer receives the committed output.
5. Verify output appears only once per processing contract.

Abort scenario:

1. Send an input causing the processor to emit output and then throw an exception.
2. The transaction rolls back.
3. The `read_committed` consumer does not receive output belonging to the aborted transaction.
4. Verify retry/post-rollback handles the input per configured policy.

Do not assert output topic message counts using only a `read_uncommitted` consumer. That consumer can see uncommitted records, causing test results not to reflect the view of downstream applications using `read_committed`.

## 12. Testing Metadata and Provisioning with Embedded Kafka

Create topics with a deterministic partition count:

~~~java
@EmbeddedKafka(
    partitions = 4,
    topics = {"orders.events", "orders.retry"}
)
class TopicMetadataTests {
    @Autowired
    EmbeddedKafkaBroker broker;

    @Test
    void topicHasExpectedPartitions() throws Exception {
        Map<String, Object> properties = Map.of(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            broker.getBrokersAsString()
        );

        try (Admin admin = Admin.create(properties)) {
            TopicDescription topic = admin
                .describeTopics(List.of("orders.events"))
                .topicNameValues()
                .get("orders.events")
                .get(10, TimeUnit.SECONDS);

            assertThat(topic.partitions()).hasSize(4);
        }
    }
}
~~~

You can use this test to verify that the binder created topics and partition counts as configured. If the test simply declares topics in `@EmbeddedKafka`, it verifies topics created by the test fixture; to test binder provisioning, let the binder create topics in the test or inspect with AdminClient after the application context starts.

To test `autoAddPartitions`, pre-create a topic with fewer partitions than the binder requires, enable auto-add, and verify metadata after the binder initializes. To test broker policies denying topic creation, configure corresponding broker/test ACLs and assert startup failure. The Test Binder cannot execute any of these scenarios.

## 13. Testing Consumer Groups, Offsets, and Rebalancing

The Test Binder has no Kafka consumer group coordinator. Therefore, it cannot test:

- How two instances in the same group split partitions.
- That a partition is assigned to only one consumer in the group at a time.
- Rebalancing when a new instance joins or an old instance leaves the group.
- Offset commits after successful processing or rollbacks.
- Redelivery after crashing between processing and commit.
- Consumer lag and catch-up speed when a consumer is paused.

Use real Kafka to start at least two consumer instances in the same group, send records to multiple partitions, and observe assignments. Then stop one instance, wait for rebalance, and verify the remaining instance continues receiving partitions. For crash tests, precisely control processing, ack/commit, and restart timing to verify expected semantics.

## 14. Testing Broker and Connection Failures

The Test Binder cannot reproduce network or broker failures. Use a real Kafka environment to test:

- Broker unavailable when the application starts.
- Connection loss during publish or poll.
- Topic deleted or metadata changed while the application is running.
- Partition leader missing or newly re-elected.
- Broker rejecting requests due to ACLs or authentication.
- Producer timeouts, retries, and duplicates after lost confirms.
- Broker restart while a transaction is open.

Embedded Kafka suits tests with an in-process broker lifecycle. Testcontainers or shared clusters are better suited when multiple brokers, security, replication, and fault injection are needed. Do not inject random network failures into every unit test; keep these scenarios in integration/chaos suites with clear timing and conditions.

## 15. Choosing the Right Tool for Each Testing Layer

| Test Layer | Tool | Verifies | Do Not Conclude on Behalf Of |
|---|---|---|---|
| Unit test | JUnit, Mockito | Pure Java business logic | Bindings or brokers |
| Binding/message test | Spring Cloud Stream Test Binder | Input/output bindings and in-JVM Message handling | Kafka metadata, transactions, groups |
| Topology test | Kafka Streams TopologyTestDriver | Processor topology, Serdes, state stores, and punctuation | Kafka Streams Binder runtime, rebalancing |
| Binder integration | Embedded Kafka + real Kafka Binder | Bindings, topics, partitions, metadata, offsets, and basic transactions | Production replication/failover |
| Cluster integration | Testcontainers or multi-node Kafka cluster | Replication, ISR, leader election, ACL/TLS, and failures | Any production behavior not simulated |

A sound test pipeline typically runs unit tests and Test Binder tests frequently during development; runs TopologyTestDriver for Kafka Streams logic; runs Embedded Kafka/Testcontainers in CI for binder and broker semantics; and runs additional tests on a production-like cluster before changes involving transactions, metadata, or topologies.

## 16. Test Matrix for a Spring Cloud Stream Application

For example, consider an application with a function processing orders via the Kafka Binder and a Kafka Streams topology aggregating order counts. Tests can be divided as follows:

| Scenario | Test Binder | TopologyTestDriver | Embedded Kafka |
|---|---|---|---|
| Function normalizing payload | Yes | Not needed | Possible, though unnecessary |
| Header/content type mapping | Yes | Only when inside topology | Yes |
| Aggregates and state stores | Insufficient for Kafka Streams runtime | Yes | Yes |
| Serde reading/writing topics | Only tests JVM conversion | Can verify serializer bytes | Yes |
| Topic partition count | No | No | Yes |
| Transaction commit/abort | No | No | Yes |
| `read_committed` visibility | No | No | Yes |
| Consumer group rebalance | No | No | Yes |
| Broker leader/replica/ISR | No | No | One broker is insufficient for replication; multi-node cluster needed |
| ACL/TLS/SASL | No | No | Yes if broker and client are configured accordingly |

Each test should have a name reflecting its verification level. For instance, `uppercaseFunction_withTestBinder` should not be named `kafkaTransaction_isAtomic` because it does not run Kafka transactions.

## 17. Common Misconceptions

**Because the Test Binder can send messages, the Kafka Binder will definitely send them.** Incorrect. The Test Binder only passes messages through an in-memory broker; the Kafka client can encounter serialization, metadata, authorization, timeout, or broker rejection errors.

**Because the Test Binder tests outputs, transaction commits are working.** Incorrect. There is no Kafka transaction coordinator or transactional producer in the Test Binder.

**Because TopologyTestDriver has no broker, it is useless for Kafka Streams.** Incorrect. It is very useful for testing topology logic, state stores, timestamps, and outputs quickly and deterministically. Just add broker integration tests for runtime behaviors the driver does not simulate.

**Embedded Kafka is equivalent to a production cluster.** Incorrect. A single embedded broker does not prove replication, ISR, leader failover, or fault tolerance across multiple nodes.

**The Test Binder and real binder can automatically coexist in one test context.** Do not assume so. When the test binder is on the test classpath, Spring Cloud Stream may choose it instead of the real binder. Tests requiring a real broker must exclude test binder auto-configuration or separate tests/modules per Spring's guidance.

## 18. Checklist Before Accepting Test Results

- [ ] Test Binder is used only to verify function logic and message contracts in the JVM.
- [ ] Test Binder is not used to conclude broker metadata, partitions, or consumer groups work properly.
- [ ] Test Binder is not used to conclude Kafka transactions, offset commits, or `read_committed` visibility.
- [ ] Kafka Streams topologies are tested with TopologyTestDriver for logic and state stores.
- [ ] Kafka Streams Binder is tested against a real Kafka broker.
- [ ] Tests using a real broker exclude Test Binder auto-configuration when needed.
- [ ] Topic/partition metadata is verified via AdminClient or KafkaTestUtils.
- [ ] Transaction tests include both commit and abort cases, with verifying consumers using `read_committed`.
- [ ] Consumer group tests include multiple instances and rebalance scenarios if business logic depends on partition assignment.
- [ ] Limitations of single-broker Embedded Kafka are distinguished from multi-broker production clusters.
- [ ] ACL, TLS, replication, ISR, and failover tests run in an environment with full components.
- [ ] Tests use finite timeouts, dedicated topics/groups, and cleanup to prevent cross-run interference.

The Test Binder is a fast tool for verifying message processing in a Spring Cloud Stream application, but it is not a full Kafka emulator. Use TopologyTestDriver for Kafka Streams logic; use Embedded Kafka or Testcontainers with the real binder to verify transactions, metadata, partitions, and consumer groups; use a multi-broker cluster when you need to prove replication and failover. Choosing the right test layer gives green builds their true meaning and prevents confusing in-JVM logic checks with broker delivery guarantees.

## References

- [Spring Cloud Stream — Testing Applications with the Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream — Kafka Binder Reference and Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html)
- [Spring for Apache Kafka — Testing Applications and Embedded Kafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Apache Kafka — TopologyTestDriver API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/TopologyTestDriver.html)
- [Apache Kafka — Testing a Streams Application](https://kafka.apache.org/39/streams/developer-guide/testing/)
