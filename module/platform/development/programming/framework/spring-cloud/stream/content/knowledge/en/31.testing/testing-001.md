# Layering Testing for Functions, Bindings, and Real Brokers

A Spring Cloud Stream application involves multiple components working together to process a message: the business function, message conversion, binding, binder, and broker. A unit test verifying that a function returns the right result does not prove that the binding uses the right destination; a test with an emulated binder does not prove that Kafka commits offsets, RabbitMQ ACKs messages, or Pulsar redelivers messages after NACK.

Therefore, testing should be organized in layers. The function layer verifies logic quickly and in isolation; the binding layer verifies that Spring Cloud Stream connects the function to message channels properly; the real broker layer verifies that the application interacts properly with the deployed Kafka, RabbitMQ, or Pulsar instance. For Kafka Streams, `TopologyTestDriver` adds a topology testing layer without requiring a broker.

This lesson explains how to choose the right tool for each layer, how to configure the Spring Integration Test Binder, how to start test brokers using Testcontainers, and which scenarios should be covered before deployment.

## 1. Overview of a Testing Flow

A typical processing flow can be tested across three boundaries:

~~~mermaid
flowchart TD
    A[JUnit test] --> B[Business function]
    B --> C[Spring Cloud Stream binding]
    C --> D[Binder]
    D --> E[(Kafka / RabbitMQ / Pulsar)]
    E --> F[Consumer or target application]

    G[Layer 1: Unit test] -. verifies .-> B
    H[Layer 2: Test Binder] -. verifies .-> C
    I[Layer 3: Real broker] -. verifies .-> D
    I -. verifies .-> E
~~~

| Layer | Component Under Test | Common Tools | Speed and Scope |
|---|---|---|---|
| 1. Function | Supplier, Function, Consumer, and business rules | JUnit, AssertJ, Mockito | Fast; no Spring context or broker required. |
| 2. Binding | Function activation, binding name, payload conversion, headers, and input/output flow | Spring Integration Test Binder | Runs in-JVM; does not connect to real middleware. |
| 3. Broker | Binder implementation, connections, destination provisioning, routing, groups, partitions, ACK, retry, DLQ, and delivery | Testcontainers or an equivalent test broker | Slower; verifies real broker protocol and behavior. |

Not every test needs to run through all three layers. Keep most business cases in the function layer, function/binding integration cases in the second layer, and select a high-value set of scenarios to run against a real broker.

## 2. Layer 1 — Unit Testing Supplier, Function, and Consumer

A Function bean in Spring Cloud Stream is still a plain Java function. If the logic does not depend on Spring or a broker, you can invoke the function directly in JUnit.

Example of an order event enrichment function:

~~~java
import java.math.BigDecimal;
import java.util.function.Function;

public record OrderCreated(String orderId, BigDecimal amount) {
}

public record EnrichedOrder(
        String orderId,
        BigDecimal amount,
        String currency) {
}

public class OrderEnricher {

    public Function<OrderCreated, EnrichedOrder> enrichOrder() {
        return event -> new EnrichedOrder(
                event.orderId(),
                event.amount(),
                "VND"
        );
    }
}
~~~

Unit test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderEnricherTest {

    private final OrderEnricher enricher = new OrderEnricher();

    @Test
    void enrichesOrderWithCurrency() {
        OrderCreated event =
                new OrderCreated("order-101", new BigDecimal("250000"));

        EnrichedOrder result = enricher.enrichOrder().apply(event);

        assertThat(result.orderId()).isEqualTo("order-101");
        assertThat(result.amount()).isEqualByComparingTo("250000");
        assertThat(result.currency()).isEqualTo("VND");
    }
}
~~~

Unit tests should focus on:

- Calculation, filtering, normalization, and data enrichment rules.
- Boundary values, missing data, malformed data, and exceptions.
- Idempotency conditions or duplicate-event skipping rules.
- Processing order in function composition when steps are called directly.
- Consumer outcomes and side effects via collaborators.

### Testing a Consumer with Collaborators

A Consumer often calls a service or repository. Mock the collaborator to verify behavior without initializing a binder:

~~~java
import static org.mockito.Mockito.verify;

import java.math.BigDecimal;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

interface OrderService {
    void handle(OrderCreated event);
}

@ExtendWith(MockitoExtension.class)
class OrderConsumerTest {

    @Mock
    private OrderService orderService;

    @Test
    void delegatesEventToOrderService() {
        OrderCreated event =
                new OrderCreated("order-101", new BigDecimal("250000"));
        Consumer<OrderCreated> consumer = orderService::handle;

        consumer.accept(event);

        verify(orderService).handle(event);
    }
}
~~~

If the Consumer has conditional logic before calling the service, test both the invoked branch and the skipped branch. There is no need to mock MessageChannel, Binder, or KafkaTemplate in a test meant solely to verify business rules.

### Testing a Supplier

A Supplier has no input message; each call to get() produces or fetches a new value. You can verify the content, format, and data source directly:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Supplier;
import org.junit.jupiter.api.Test;

record Heartbeat(String service, String status) {
}

class HeartbeatSupplierTest {

    @Test
    void createsHeartbeatEvent() {
        Supplier<Heartbeat> supplier =
                () -> new Heartbeat("inventory-service", "UP");

        Heartbeat event = supplier.get();

        assertThat(event.service()).isEqualTo("inventory-service");
        assertThat(event.status()).isEqualTo("UP");
    }
}
~~~

If the Supplier depends on a clock, UUID, or random source, inject the dependency so the test can control time and data. Avoid using Thread.sleep() to wait for a Supplier to emit messages; periodic emission belongs to the binding or scheduler layer and should be tested at the integration layer.

## 3. Layer 2 — Spring Integration Test Binder

Spring Cloud Stream provides the **Spring Integration Test Binder** to test applications without connecting to Kafka, RabbitMQ, or Pulsar. The Test Binder acts as an in-JVM message broker backed by Spring Integration channels.

It is suitable for testing:

- Which function is activated via spring.cloud.function.definition.
- Binding names and destination mappings.
- Messages flowing from the input binding to the function and output binding.
- Payload conversion, content types, and headers within the scope supported by the test binder.
- Multiple inputs/outputs or multiple independent functions.
- Behavior of StreamBridge and PollableMessageSource in appropriate test flows.

Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle:

~~~kotlin
testImplementation("org.springframework.cloud:spring-cloud-stream-test-binder")
~~~

Let the Spring Cloud BOM manage the version compatible with your application's Spring Boot and Spring Cloud Stream versions; do not pin a test binder version from a different release train than your runtime dependencies.

### Using InputDestination and OutputDestination

Example application with a Function that converts strings to uppercase:

~~~java
import java.util.function.Function;

import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableAutoConfiguration
@EnableTestBinder
public class UppercaseTestConfiguration {

    @Bean
    public Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }

    @Bean
    public Function<String, String> reverse() {
        return value -> new StringBuilder(value).reverse().toString();
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

@SpringBootTest(
        classes = UppercaseTestConfiguration.class,
        properties = "spring.cloud.function.definition=uppercase")
class UppercaseBindingTest {

    @Autowired
    private InputDestination input;

    @Autowired
    private OutputDestination output;

    @Test
    void sendsMessageThroughFunctionBinding() {
        input.send(new GenericMessage<>("hello".getBytes()),
                "uppercase-in-0");

        Message<byte[]> result =
                output.receive(1_000, "uppercase-out-0");

        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), java.nio.charset.StandardCharsets.UTF_8))
                .isEqualTo("HELLO");
    }
}
~~~

InputDestination sends messages into the input binding. OutputDestination retrieves messages emitted by the function to the output binding. The binding name parameter lets the test specify the exact port being tested; the receive timeout is in milliseconds.

In real projects, you can set the function definition through test configuration instead of hard-coding it in the class:

~~~properties
spring.cloud.function.definition=uppercase
~~~

This is useful when an application has multiple function beans, yet each test only wants to activate a specific function or composition chain.

## 4. Testing Binding Names and Multiple Inputs/Outputs

The binding name is the contract between the function and the destination configuration. A test might invoke the right function while sending messages to the wrong binding, especially when the application has multiple functions.

Example activating two independent functions:

~~~yaml
spring:
  cloud:
    function:
      definition: "uppercase;reverse"
~~~

The two functions have separate input/output bindings:

| Function | Input binding | Output binding |
|---|---|---|
| uppercase | uppercase-in-0 | uppercase-out-0 |
| reverse | reverse-in-0 | reverse-out-0 |

The test must send and receive on the matching bindings:

~~~java
Message<byte[]> inputMessage =
        new GenericMessage<>("Hello".getBytes());

input.send(inputMessage, "uppercase-in-0");
input.send(inputMessage, "reverse-in-0");

Message<byte[]> upper = output.receive(1_000, "uppercase-out-0");
Message<byte[]> reversed = output.receive(1_000, "reverse-out-0");

assertThat(new String(upper.getPayload())).isEqualTo("HELLO");
assertThat(new String(reversed.getPayload())).isEqualTo("olleH");
~~~

If destination aliases are configured, send and receive using the mapped destinations. For example:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: order-input
        uppercase-out-0:
          destination: order-output
~~~

Then the test can call input.send(message, "order-input") and output.receive(1_000, "order-output"). Verifying aliases helps catch configurations that accidentally mix default names with destination names.

### Multiple Inputs

For a BiFunction or curried function, send messages to each input binding in declaration order:

~~~java
input.send(customerMessage, "enrichOrder-in-0");
input.send(productMessage, "enrichOrder-in-1");
~~~

The test should verify that the function receives the correct data from each source, not just that the final output is non-null. If the function requires two inputs correlated by key, write tests with matching keys and non-matching keys to verify join rules.

## 5. Testing Message Conversion and Headers

Spring Cloud Stream converts messages based on content type, payload type, and binding configuration. The Test Binder layer is suitable for verifying conversion contracts within the application boundary:

- application/json converts JSON payloads into DTOs.
- String and byte array types are converted properly.
- Business message headers are read by the function.
- Headers are preserved or stripped according to configuration and header propagation policies.
- Invalid messages enter the error branch designed by the application.

Example sending a message with headers:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<byte[]> message = MessageBuilder
        .withPayload("{\"orderId\":\"order-101\"}".getBytes())
        .setHeader("event-type", "OrderCreated")
        .setHeader("correlation-id", "corr-101")
        .build();

input.send(message, "orders-in-0");
~~~

If the function uses event-type or correlation-id, verify the values the function actually receives. Do not assume every header passes through every binder intact: some headers are internal, some require mapping configuration, and brokers have their own limits on metadata types or sizes.

With Avro, Protobuf, or JSON Schema, verify both the serializer/deserializer and schema compatibility rules. The Test Binder can test logic after conversion, but it does not prove that Schema Registry or broker schema negotiation is working properly.

## 6. Limitations of the Test Binder

The Test Binder is an emulated in-JVM broker. It helps verify the connection between Spring Cloud Stream channels and functions, but it does not run the Kafka, AMQP, or Pulsar protocols.

Do not rely on the Test Binder alone to conclude that the following behaviors work properly:

- Kafka consumer group coordination, offset commits, partition assignment, and rebalancing.
- Kafka transactions, idempotent producers, broker replication, or log retention.
- RabbitMQ exchanges, queue declarations, bindings, routing keys, publisher confirms, mandatory returns, ACK/NACK, and broker DLQs.
- Pulsar subscription types, broker acknowledgements, redelivery, dead-letter topics, and broker schema enforcement.
- TLS, SASL, credentials, network partitions, broker restarts, or real-world permissions.

A passing test binder test only proves that the message flow in the test binder environment behaves as expected. It does not replace testing with a real middleware binder.

### Do Not Mix Test Binder and Real Binders in the Same Test Runtime

When the Test Binder is on the test classpath, Spring Cloud Stream may select it for bindings that need to communicate. Consequently, if a single test module tries to use both the Test Binder and a real Kafka/Rabbit/Pulsar binder, tests may accidentally connect to in-JVM channels instead of the broker.

The Spring Cloud Stream documentation recommends separating Test Binder tests and real middleware binder tests into separate modules so each group has a clear classpath. If the project architecture cannot split modules, explicitly configure auto-configuration exclusions/precedence and verify which actual binder is initialized in the test context.

Do not rely solely on the absence of connection errors to conclude a real broker is being used. Inspect binder initialization logs, broker connections, and verify a message read from the broker using an independent client.

## 7. Kafka Streams — Using TopologyTestDriver for Topology Logic

Kafka Streams provides TopologyTestDriver in the kafka-streams-test-utils artifact. The driver lets you feed records into a topology and read outputs without running a Kafka broker. It is well-suited for testing DSL operations, processors, joins, aggregates, windows, and state stores at the topology level.

Example topology that converts strings to uppercase:

~~~java
import java.util.Properties;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.TopologyTestDriver;
import org.apache.kafka.streams.TestInputTopic;
import org.apache.kafka.streams.TestOutputTopic;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Produced;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderTopologyTest {

    @Test
    void transformsInputRecord() {
        StreamsBuilder builder = new StreamsBuilder();
        builder.stream(
                        "orders",
                        Consumed.with(Serdes.String(), Serdes.String()))
                .mapValues(String::toUpperCase)
                .to("orders-uppercase",
                        Produced.with(Serdes.String(), Serdes.String()));

        Properties properties = new Properties();
        properties.put(StreamsConfig.APPLICATION_ID_CONFIG, "orders-test");
        properties.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "dummy:9092");
        properties.put(StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
                Serdes.String().getClass().getName());
        properties.put(StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
                Serdes.String().getClass().getName());

        try (TopologyTestDriver driver =
                     new TopologyTestDriver(builder.build(), properties)) {
            TestInputTopic<String, String> input =
                    driver.createInputTopic(
                            "orders",
                            Serdes.String().serializer(),
                            Serdes.String().serializer());
            TestOutputTopic<String, String> output =
                    driver.createOutputTopic(
                            "orders-uppercase",
                            Serdes.String().deserializer(),
                            Serdes.String().deserializer());

            input.pipeInput("order-101", "created");

            assertThat(output.readValue()).isEqualTo("CREATED");
        }
    }
}
~~~

TopologyTestDriver processes input synchronously, making tests fast and reproducible. The driver simulates producers/consumers at the byte array level and provides TestInputTopic and TestOutputTopic to serialize/deserialize test data.

The driver does not run a real broker. It does not verify Kafka consumer groups, broker partition assignment, inter-broker transactions, networking, replication, or the behavior of the Spring Cloud Stream Kafka Streams binder when provisioning topics. For those requirements, add integration tests running the binder application against real Kafka.

## 8. Layer 3 — Testing with a Real Broker

To verify the binder, you need to start a compatible broker and configure the test application to connect to the dynamic address provided by the broker. Testcontainers provides modules for Kafka, RabbitMQ, and Pulsar; containers are started during the test and stopped once the test completes.

Common Testcontainers modules:

| Broker | Testcontainers Module | Connection Details to Retrieve |
|---|---|---|
| Kafka | testcontainers-kafka | Bootstrap servers. |
| RabbitMQ | testcontainers-rabbitmq | Host, AMQP port, username/password if changed from defaults. |
| Pulsar | testcontainers-pulsar | Pulsar broker URL and HTTP/admin URL. |

With Gradle, test dependencies can be declared as follows; manage versions via the Testcontainers BOM or the project's existing dependency management:

~~~kotlin
testImplementation("org.testcontainers:testcontainers-junit-jupiter")
testImplementation("org.testcontainers:testcontainers-kafka")
testImplementation("org.testcontainers:testcontainers-rabbitmq")
testImplementation("org.testcontainers:testcontainers-pulsar")
~~~

Only add the module for the broker that the test suite actually uses. The JUnit Jupiter integration provides `@Testcontainers` and `@Container` to manage container lifecycles.

Using Testcontainers gives tests an independent broker, a controllable initial state, and no dependency on brokers pre-installed on developer machines. Choose an image compatible with your production version; do not use the latest image tag for stable tests.

### Starting a Kafka Container

Example with JUnit Jupiter and the Testcontainers Kafka module:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class KafkaBinderIntegrationTest {

    @Container
    static final KafkaContainer KAFKA =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.stream.kafka.binder.brokers",
                KAFKA::getBootstrapServers);
    }

    @Test
    void applicationStartsWithRealKafkaBinder() {
        // Send message through binding and verify on actual consumer/output.
    }
}
~~~

The image apache/kafka-native:3.8.0 is only an API illustration example. Replace it with the broker version supported by your target deployment and pin a specific tag. The Kafka binder reads the broker address from spring.cloud.stream.kafka.binder.brokers.

Spring Kafka also provides spring-kafka-test with @EmbeddedKafka and KafkaTestUtils. An embedded broker works well for many local integration tests; Testcontainers is useful when you want to run the exact broker image, verify networking/containers, and stay closer to the deployment environment. With Kafka 4.x, the embedded broker uses KRaft.

### Starting a RabbitMQ Container

The RabbitMQ binder uses the Spring Boot ConnectionFactory by default, so connection settings use the spring.rabbitmq prefix.

Example mapping container addresses:

~~~java
@DynamicPropertySource
static void rabbitProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.rabbitmq.host", RABBIT::getHost);
    registry.add("spring.rabbitmq.port", RABBIT::getAmqpPort);
    registry.add("spring.rabbitmq.username", RABBIT::getAdminUsername);
    registry.add("spring.rabbitmq.password", RABBIT::getAdminPassword);
}
~~~

RABBIT is a RabbitMQ container instance managed by Testcontainers. The testcontainers-rabbitmq module dependency provides the appropriate container. Even if the test image uses default credentials, still read credentials from the container rather than hard-coding them into the test.

With RabbitMQ, tests should verify that queues and exchanges are provisioned by the binder, messages are routed by binding key, queue groups work, ACK/NACK behaves properly, and dead-letter exchanges/queues receive messages as configured.

### Starting a Pulsar Container

The Testcontainers Pulsar module provides PulsarContainer. Spring for Apache Pulsar uses spring.pulsar.client.service-url for the client and spring.pulsar.administration.service-url for the administration client when the binder needs to provision topics.

Example:

~~~java
@DynamicPropertySource
static void pulsarProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.pulsar.client.service-url",
            PULSAR::getPulsarBrokerUrl);
    registry.add(
            "spring.pulsar.administration.service-url",
            PULSAR::getHttpServiceUrl);
}
~~~

PULSAR is a container managed by Testcontainers. If the Spring for Apache Pulsar/Spring Boot version in your project uses a different administration property name, check the configuration metadata for that exact BOM version. The client URL and admin URL are two distinct endpoints; do not substitute the HTTP URL with the Pulsar binary protocol URL.

## 9. Testing the Application Through a Real Binder

A valuable integration test must go through the real binder implementation. Both producers and consumers can be tested:

1. Start the Spring Boot application with the function definition and destination under test.
2. Start the broker container and inject its dynamic address into the binder configuration.
3. Send a message using StreamBridge or an independent producer client.
4. Verify that the message is received by the binder consumer and processed by the function.
5. Read the output from the broker with an independent consumer client or verify observable side effects.
6. Clean up topics/queues/subscriptions after the test if they are not automatically managed.

Example sending a dynamic message via StreamBridge:

~~~java
boolean accepted = streamBridge.send("orders", event);
assertThat(accepted).isTrue();
~~~

A true result from StreamBridge.send only indicates that the message was accepted into the send pipeline according to the API. For tests requiring delivery guarantees, you still need to wait and verify on the consumer side or read the message from the broker. Do not use this return value as a substitute for publisher confirms, consumer ACKs, or evidence that the message was processed.

To assert asynchronous consumers, use Awaitility or a CountDownLatch with a timeout. Example:

~~~java
await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                verify(orderService).handle(event));
~~~

The timeout must be sufficient for broker startup, topic provisioning, and consumer assignment in CI environments. When a timeout occurs, application, broker, and binder logs help determine whether the test failed due to connectivity, provisioning, routing, or the function itself.

## 10. Behaviors to Verify by Broker

Do not only verify that a single message gets through. Choose scenarios that reflect the semantics your application relies on.

### Kafka Binder

- Topics are provisioned with the appropriate partition count and replication.
- Message keys are propagated properly, and identical keys are consistently routed to partitions by the partitioner.
- Consumer groups distribute partitions across instances as expected.
- Offsets are committed according to the configured acknowledgement/auto-commit policy.
- When a consumer stops or restarts, uncommitted messages are reprocessed according to the chosen semantics.
- Retries, DLTs, and error handlers work for conversion or processing errors.
- Schemas/Serdes are compatible between producers and consumers.
- With Kafka Streams, the topology runs through the binder, and state stores and changelogs are initialized; test restore/rebalance with a real broker when needed.

A single-node Kafka container can verify basic flows, but it does not prove replication or fault tolerance of a multi-broker cluster. If production requirements depend on replication factor, ISR, or broker failover, a more representative test topology is needed.

### RabbitMQ Binder

- Exchanges, queues, and bindings are declared properly.
- Named consumer groups create shared queues; anonymous consumers create temporary queues as configured.
- Routing keys and binding patterns deliver messages to the right queues.
- Durable queues and persistent messages retain data as expected across restarts.
- Consumer ACK, NACK, reject, and requeue behave properly.
- Retries, DLX/DLQ, TTL, and queue expiration operate as configured.
- Publisher confirms and publisher returns are handled when the application requires publish guarantees.
- Pre-created queues/exchanges have attributes compatible with the binder's declarations.

If a test only uses TestRabbitTemplate, the message listener may be invoked directly in the JVM; such a test does not verify exchanges, queues, routing, or broker ACKs. For broker semantics requirements, run real RabbitMQ in a container.

### Pulsar Binder

- Topics and subscriptions are created with the right name, tenant, namespace, and partition count.
- The subscription type matches requirements: Exclusive, Failover, Shared, or Key_Shared.
- Message keys and ordering are preserved according to subscription/partition semantics.
- Ack, negative ack, and redelivery work as configured.
- Retry letter topics and dead letter topics receive messages properly after the configured number of failed attempts.
- Schemas are registered and compatibility-checked as configured.
- Authentication, authorization, and TLS are tested if used by the application.

A Pulsar test container can enable transactions or the Functions Worker when tests need those features. Do not assume a default container enables every extended feature.

## 11. Testing Schemas, Serialization, and Message Contracts

A message can pass through a broker while the consumer still fails to understand the payload. Therefore, contract tests should verify the data contract independently of processing logic:

- Field names, data types, nullability, and defaults.
- Encoding/decoding with the right serializer and deserializer.
- Schema versions written by the producer and supported by the consumer.
- Headers, content type, correlation ID, and event ID.
- Compatibility rules when adding, removing, or renaming fields.
- Behavior when receiving messages with invalid schemas or truncated/corrupted payloads.

If using Avro/Protobuf and Schema Registry, include the corresponding Registry container or test service in the integration suite. Direct serializer/deserializer tests can check formats quickly; real-broker tests confirm that the binder configuration and registry endpoint are actually used.

Do not only assert the object after deserialization. For critical contracts, keep versioned message fixtures to test backward/forward compatibility according to your system's policy.

## 12. Data Isolation and Avoiding Flaky Tests

Message brokers process asynchronously and retain state across test runs. Reusing topics, queues, or consumer groups without proper cleanup can cause tests to read stale messages or share offsets with other tests.

Apply these principles:

1. Use separate topics, queues, subscriptions, or groups per test class/test case when isolation is needed.
2. Append a UUID or test run ID to resource names to avoid collisions during parallel execution.
3. Wait using Awaitility, latches, or receive APIs with timeouts; do not rely on fixed Thread.sleep() calls.
4. Set auto.offset.reset and group ID explicitly in Kafka probe consumers.
5. Purge queues or delete resources after tests when needed; do not delete queues shared across the suite.
6. Close producers, consumers, admin clients, and application contexts according to their lifecycle.
7. Do not assert global ordering across Kafka partitions or concurrent Rabbit/Pulsar consumers if the system does not guarantee that ordering.
8. Keep event IDs stable to identify duplicates during retries or restarts.

With Kafka, a new consumer group often needs auto.offset.reset=earliest if the test sends records before the probe consumer starts. Using latest may cause the consumer to read only records sent after it receives an assignment. Choose the policy deliberately so tests do not depend on startup timing.

With RabbitMQ, queues must be provisioned before sending messages if the test expects to verify stored messages. Messages published before a queue is bound may not appear in a queue created later, depending on the exchange and alternate exchange configuration.

With Pulsar, check the subscription initial position and subscription name. Reused subscriptions can resume from an old cursor, causing tests to receive data from previous runs.

## 13. Test Matrix for a Spring Cloud Stream Application

The matrix below helps select the right testing layer and the evidence to verify:

| Scenario | Appropriate Layer | Evidence to Verify |
|---|---|---|
| Calculations inside a Function | Unit test | Correct output for inputs and edge cases. |
| Consumer invoking a service | Unit test | Collaborator receives the expected event and call count. |
| Supplier creating an event | Unit test | Event has valid data, timestamp, and format. |
| Function activation | Test Binder | Correct function is activated according to definition. |
| Binding name/destination alias | Test Binder | Messages enter and exit the right bindings. |
| Payload conversion | Test Binder + contract test | Correct DTO/bytes and content type. |
| Header mapping | Test Binder + real broker if broker-dependent | Business headers are read/written properly. |
| StreamBridge dynamic binding | Test Binder + real broker | Dynamic binding is created and message reaches destination. |
| Kafka partition key | Real Kafka | Key, partition, and record distribution are correct. |
| Kafka consumer group/rebalance | Real Kafka | Assignment, offsets, and reprocessing are correct. |
| Kafka Streams transform/join/aggregate | TopologyTestDriver | Topology output and state stores are correct. |
| Kafka Streams binder integration | Real Kafka | Bindings, topics, application ID, state restore, and output are correct. |
| Rabbit exchange/queue/routing | Real RabbitMQ | Messages arrive in the right queue. |
| Rabbit ACK/NACK/retry/DLQ | Real RabbitMQ | Delivery, requeue, and dead-lettering are correct. |
| Pulsar subscription/ack/redelivery | Real Pulsar | Subscription cursor, ack, and redelivery are correct. |
| Schema Registry or broker schemas | Real Broker + Registry | Schema is registered and serialized/deserialized properly. |
| Broker restart or connection loss | Real Broker, potentially with fault injection | Application recovers and processes messages per defined semantics. |

## 14. Example Test Suite Structure

A project can organize tests by package or module:

~~~text
src/test/java/
  function/
    OrderEnricherTest.java
    OrderConsumerTest.java
  binding/
    OrderFunctionBindingTest.java
    FunctionRoutingTest.java
  kafka/
    KafkaBinderIntegrationTest.java
    KafkaStreamsTopologyTest.java
  rabbit/
    RabbitBinderIntegrationTest.java
  pulsar/
    PulsarBinderIntegrationTest.java
~~~

If the Test Binder and real binder cannot run safely in the same module due to auto-configuration/classpath conflicts, split them into separate test modules:

~~~text
application/
application-test-binder/
application-broker-integration-tests/
~~~

The application-test-binder module contains spring-cloud-stream-test-binder. The application-broker-integration-tests module contains the real binder and corresponding Testcontainers modules. Both test the main application or shared test fixtures, while keeping each module's classpath and binder configuration unambiguous.

Splitting modules is unnecessary if your project already has a reliable way to exclude Test Binder auto-configuration; what matters is that tests prove which binder is actually in use.

## 15. Running Tests in CI

CI needs an environment with a container runtime to run Testcontainers. Before running the integration suite, verify that the runner has Docker or a compatible container runtime and can pull broker images.

A pipeline strategy:

| Stage | Tests Executed | Goal |
|---|---|---|
| Fast pull request | Unit tests and Test Binder | Catch logic, binding, and conversion bugs early. |
| Pull request or merge | Kafka/Rabbit/Pulsar integration subset | Verify binder and broker behavior for critical flows. |
| Nightly or pre-release | Full broker suite, restart/retry/DLQ, schema, and fault scenarios | Validate operational behavior and reliability. |

Optimize execution time by reusing containers at an appropriate test class/suite scope while still creating separate logical resources per test. The Testcontainers JUnit Jupiter extension is tested for sequential execution; parallel test execution with this extension is not yet supported and may cause side effects. If enabling parallel execution, design custom container lifecycles and isolation rather than relying on `@Testcontainers` by default. Only enable container reuse on developer machines when you understand the persistent data state; CI should generally start from a clean environment to avoid tests depending on stale data.

When tests fail, archive application and broker container logs alongside the test report. For Kafka, logs of consumer groups and topics/partitions; for RabbitMQ, logs of connections, exchanges/queues, and unacked counts; for Pulsar, logs of topics/subscriptions and redeliveries help isolate root causes.

## 16. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Test Binder finds no output | Wrong binding name or function not activated. | Check function definition and *-out-0 name. |
| Test Binder receives byte[] payload instead of DTO | Test sent raw payload or content type/converter is unconfigured. | Check content type and send message per the expected contract. |
| Test Binder runs but broker receives no messages | Test runtime selected the emulated binder. | Split test modules or exclude Test Binder auto-configuration and inspect binder logs. |
| Kafka test fails to read sent records | Consumer group started at latest or is not yet assigned. | Use a dedicated group, set offset reset explicitly, and wait for assignment. |
| Kafka test reads old messages | Topic/group reused across tests. | Use separate topics/groups or reset offsets in a controlled manner. |
| Kafka Streams test produces no output | TopologyTestDriver did not create matching input/output topics or Serdes. | Verify topic names, serializers, and deserializers. |
| RabbitMQ test receives no messages | Queue does not exist or is not bound to the right exchange/routing key. | Verify broker topology before publishing. |
| RabbitMQ test receives duplicate messages | Consumer NACK/requeued or test reused a queue. | Check acknowledgement mode, retry, and cleanup. |
| Pulsar test resumes from an old cursor | Reused subscription name. | Create a dedicated subscription or reset it per test scenario. |
| Flaky integration tests | Fixed sleep used or broker not yet ready. | Use readiness checks and Awaitility/latches with timeouts. |
| Parallel tests suffer data pollution | Shared topics, queues, groups, or subscriptions. | Add test run IDs and isolate resources. |
| CI fails to start containers | Runner lacks Docker or cannot access image registry. | Check container runtime, socket permissions, and image pulls. |
| Schema test passes locally but fails on broker | Serializer, Registry URL, or schema compatibility differs across environments. | Test Registry and binder configuration with real containers. |

When investigating, identify the test layer first. If a unit test fails, focus on logic; if the Test Binder fails, check function definitions, binding names, and conversion; if only real broker tests fail, check connections, provisioners, broker topology, groups/subscriptions, serializers, and acknowledgements.

## 17. Pre-Deployment Checklist

- [ ] Functions and business rules have independent unit tests.
- [ ] Supplier, Function, and Consumer are tested with boundary data.
- [ ] Consumer side effects are verified through collaborators.
- [ ] Test Binder is used to verify function activation and bindings.
- [ ] InputDestination/OutputDestination use the right binding names or destination aliases.
- [ ] Payload conversion, content types, and critical headers are tested.
- [ ] Understood that Test Binder is an in-JVM broker and does not prove broker semantics.
- [ ] Test Binder does not accidentally replace the real binder in the integration suite.
- [ ] Kafka Streams topologies have TopologyTestDriver tests where appropriate.
- [ ] Real binder integration tests run against Kafka, RabbitMQ, or Pulsar containers.
- [ ] Broker images are pinned to production-compatible versions.
- [ ] Tests use dedicated topics, queues, groups, or subscriptions for data isolation.
- [ ] Timeouts and deterministic asynchronous waiting mechanisms are used.
- [ ] Partitions, groups/subscriptions, ACK, retry, and DLQ are verified for the broker in use.
- [ ] Schemas/Serdes are tested with real serializers and Registry if applicable.
- [ ] CI has a container runtime and archives logs when integration tests fail.

Testing Spring Cloud Stream should progress from functions to bindings and then to real brokers. Unit tests verify logic quickly; the Spring Integration Test Binder verifies functions, bindings, conversion, and in-JVM message flows; Testcontainers with real binders verify protocols, destinations, groups/subscriptions, partitions, acknowledgements, retries, and dead-letter handling. For Kafka Streams, TopologyTestDriver checks topology quickly, while integration tests with Kafka verify connectivity and operations. Proper layering catches bugs at the right boundary, keeps the test suite fast, and still provides reliable evidence before deployment.

## References

- [Spring Cloud Stream — Testing with Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring for Apache Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Apache Kafka — TopologyTestDriver API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/TopologyTestDriver.html)
- [Spring AMQP — Testing Support](https://docs.spring.io/spring-amqp/reference/testing.html)
- [Spring for Apache Pulsar — Testing Applications](https://docs.spring.io/spring-pulsar/reference/reference/testing-applications.html)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)
- [Testcontainers — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/)
- [Testcontainers — Apache Pulsar Module](https://java.testcontainers.org/modules/pulsar/)
- [Spring Cloud Stream — Kafka Binder Properties](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — RabbitMQ Binder Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/binder-properties.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
