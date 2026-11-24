# Declaring Dependencies for Kafka Testing

Testing a Spring Kafka application requires two groups of tools: tools for testing Spring applications and tools that help spin up a Kafka broker in the test environment. Proper dependencies help verify producers, consumers, serialization, and event flows reproducibly, without depending on a Kafka instance running on a local machine or shared environment.

In the `SPRING_KAFKA_MESSAGING` module, the application sends events using `KafkaTemplate` and receives events using `@KafkaListener`. Therefore, the testing dependency set should support both Spring context testing and real broker interaction testing.

## 1. Two Foundational Dependencies

### spring-boot-starter-test

`spring-boot-starter-test` provides Spring Boot's familiar testing foundation, typically including:

- JUnit Jupiter for writing and running tests.
- Spring Test for initializing the application context and testing beans.
- AssertJ for writing readable assertions.
- Mockito for mocking dependencies in unit tests.

This dependency is suitable for testing services, business logic, Spring configuration, and components that do not need a real Kafka broker.

### spring-kafka-test

`spring-kafka-test` adds utilities specific to Spring Kafka:

- `@EmbeddedKafka` and `EmbeddedKafkaBroker` to run an embedded Kafka broker inside the test process.
- `KafkaTestUtils` to build consumer/producer properties and assist in reading records.
- `ContainerTestUtils` to wait for listener containers to be assigned partitions.
- Utilities to help verify record sending, receiving, and processing flows.

This dependency has test scope. It is not a dependency for production applications to run a Kafka broker.

## 2. Declaring with Maven

If the project uses the Spring Boot parent or imports Spring Boot dependency management, both dependencies can be declared without specifying individual versions:

```xml
<dependencies>
    <!-- Application runtime dependencies, such as spring-kafka,
         are declared in the project's main dependencies section. -->

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Spring Boot dependency management manages compatible versions across the Spring Boot ecosystem. `spring-kafka-test` should match the Spring Kafka version used by the application. If the project does not use a Spring Boot BOM or parent, declare versions explicitly and ensure the Spring Kafka modules are compatible with one another.

After adding the dependencies, run:

```bash
./mvnw test
```

On Windows, you can use:

```powershell
.\mvnw.cmd test
```

## 3. Declaring with Gradle

With Gradle Groovy DSL:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

With Gradle Kotlin DSL:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
```

If the project already applies the Spring Boot Gradle plugin or Spring dependency management, versions are usually managed centrally. Otherwise, import an appropriate BOM or specify synchronized versions for Spring Boot and Spring Kafka dependencies.

Run tests with:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

## 4. Choosing How to Provide a Kafka Broker for Tests

There are three common levels of testing. Choose the level based on the behavior to verify.

| Testing Approach | Broker | Suitable for Verifying |
|---|---|---|
| Unit test | No broker needed | Business logic, error handling, and calls to `KafkaTemplate` |
| Embedded Kafka | Embedded broker in test process | Producers, consumers, listeners, serialization, and record flows |
| Testcontainers | Kafka running in a container | Integration close to deployment environment, network config, and broker compatibility |

### Unit Tests Without Kafka

If the goal is solely to verify which event a service decides to send, `KafkaTemplate` can be mocked. Tests run fast and need no extra broker.

Illustrative example:

```java
@ExtendWith(MockitoExtension.class)
class OrderEventServiceTest {

    @Mock
    private KafkaTemplate<String, String> kafkaTemplate;

    @InjectMocks
    private OrderEventService orderEventService;

    @Test
    void publishesOrderCreatedEvent() {
        orderEventService.publishCreated("order-42");

        verify(kafkaTemplate).send(
            "orders",
            "order-42",
            "ORDER_CREATED"
        );
    }
}
```

This unit test verifies that the service invokes the right topic, key, and payload. It does not prove that the broker receives the record or that a consumer can decode it. Those behaviors require integration tests.

### Embedded Kafka with spring-kafka-test

Embedded Kafka suits most integration tests that need a real broker while keeping execution compact inside the test suite without depending on Docker.

Declaring `@EmbeddedKafka` starts an embedded broker and creates topics for the test. The `bootstrapServersProperty` attribute injects the broker address into Spring Boot configuration so `KafkaTemplate` and listener containers use the same broker.

Example verifying a record is sent to a topic:

```java
@SpringBootTest(properties = {
    "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderPublisherIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Test
    void publishesRecordToOrdersTopic() throws Exception {
        Map<String, Object> consumerProperties = new HashMap<>();
        consumerProperties.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            embeddedKafka.getBrokersAsString()
        );
        consumerProperties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-test-group"
        );
        consumerProperties.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest"
        );
        consumerProperties.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class
        );
        consumerProperties.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class
        );

        try (Consumer<String, String> consumer =
                 new KafkaConsumer<>(consumerProperties)) {

            embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");

            kafkaTemplate.send(
                "orders",
                "order-42",
                "ORDER_CREATED"
            ).get(10, TimeUnit.SECONDS);

            ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofSeconds(10));

            assertThat(records.records("orders")).isNotEmpty();

            ConsumerRecord<String, String> record =
                records.records("orders").iterator().next();

            assertThat(record.key()).isEqualTo("order-42");
            assertThat(record.value()).isEqualTo("ORDER_CREATED");
        }
    }
}
```

Important imports in the example:

```java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

import static org.assertj.core.api.Assertions.assertThat;
```

In real tests, application classes and serializer/deserializer configuration must match the topic's data types. The example above uses `StringSerializer` and `StringDeserializer` to focus on the basic send/receive mechanism. If the application sends JSON DTOs, configure `JsonSerializer` and `JsonDeserializer` accordingly and verify the object conversion process as well.

### Testing @KafkaListener

When verifying that a listener receives and processes records, `@EmbeddedKafka` can be combined with a synchronization mechanism in the test, such as `BlockingQueue`, `CountDownLatch`, or Awaitility. Avoid using fixed `Thread.sleep()` calls because processing time varies across machines running tests.

If you need to ensure the listener has received partitions before sending records, `ContainerTestUtils.waitForAssignment(...)` in `spring-kafka-test` can wait until the listener container is assigned all expected partitions. This prevents race conditions between when the test sends a record and when the listener is ready.

## 5. Using Testcontainers When a Production-Like Environment Is Needed

Embedded Kafka tests many producer and consumer behaviors, but does not fully represent a real deployment topology. When you need to test a broker running in a container, listener configurations, Docker network connections, or behavior specific to a Kafka version, Testcontainers can be used.

With Testcontainers 1.x, commonly used dependencies are:

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>kafka</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Import the Testcontainers BOM to manage versions in sync. Artifact names and Java packages may change between Testcontainers major versions; use the Kafka and JUnit Jupiter modules corresponding to the selected major version, and do not mix dependencies from different major versions.

Typical configuration flow with JUnit 5:

1. Declare the Kafka container using `@Container`.
2. Use `@Testcontainers` to integrate container lifecycle with JUnit.
3. Register `getBootstrapServers()` into the `spring.kafka.bootstrap-servers` property using `@DynamicPropertySource`.
4. Run integration tests with `@SpringBootTest` just as with another broker.

The example below uses the Testcontainers 1.x API and a Confluent Kafka image compatible with that API:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class KafkaContainerIntegrationTest {

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse("confluentinc/cp-kafka:7.6.1")
        );

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers
        );
    }

    // Application integration tests go here.
}
```

Testcontainers requires a running Docker daemon on the machine or CI runner. Choose a broker image and version matching the deployment environment; if the system uses TLS, SASL, multiple listeners, or multiple brokers, extend the container configuration to simulate those conditions. With Testcontainers 2.x, the Kafka module and Java packages have changed; switch to the API/artifacts corresponding to that major version instead of mixing with the 1.x dependencies in the example.

## 6. Tests You Should Have for Spring Kafka

Once dependencies are declared, design tests around the risks of the messaging flow:

- **Producer**: verify topic, key, payload, headers, and send results.
- **Serialization**: verify objects are serialized into bytes and deserialized into the right data type.
- **Consumer**: verify the listener receives records and invokes the right business logic.
- **Consumer group**: verify listener containers are assigned partitions appropriately for the number of consumers and partitions.
- **Retry and dead-letter**: verify retry counts, conditions for routing records to a DLT, and record contents after routing.
- **Transaction**: verify Kafka operations that must commit or roll back together.
- **Broker errors**: verify the application reacts properly when the broker is temporarily unavailable, if required by the system.

Do not cram every case into a single large integration test. Unit tests should cover business logic; integration tests with Embedded Kafka verify common Kafka interactions; Testcontainers targets meaningful differences between the test environment and deployment environment.

## 7. Common Errors When Declaring Dependencies

| Symptom | Common Cause | Resolution |
|---|---|---|
| Cannot find `@EmbeddedKafka` | Missing `spring-kafka-test` or dependencies not synced | Add the dependency in test scope and reload Maven/Gradle |
| Cannot find `@SpringBootTest` or JUnit extension | Missing `spring-boot-starter-test` | Add the starter in test scope |
| `NoSuchMethodError` in tests | `spring-kafka-test` version mismatches `spring-kafka` | Use the Spring Boot BOM or align versions |
| Test cannot connect to broker | Application is using a bootstrap server different from the embedded broker | Configure `bootstrapServersProperty` or the corresponding property |
| Flaky listener tests | Sending records before the listener is assigned partitions | Wait for assignment or use a synchronization mechanism instead of sleep |
| Testcontainers fails to start | Docker is not running or image is incompatible | Check Docker daemon, image, and Testcontainers version |

After fixing dependencies, reload the project so the IDE and build tool pick up the updated classpath. If tests pass from the IDE but fail in CI, check Docker availability, Java version, dependency cache, and runner network configuration.

## 8. Principles for Choosing Dependencies

For most Spring Kafka projects, two dependencies should be in test scope:

- `spring-boot-starter-test` for JUnit, Spring Test, assertions, and mocking.
- `spring-kafka-test` for Embedded Kafka and Kafka testing utilities.

Add Testcontainers only when you need to verify behavior dependent on broker/container setup or production-like environments. Keep testing dependencies in test scope so they do not become runtime components of the application.

Once dependencies are properly declared and version-aligned, the team can test the `KafkaTemplate` → broker → `@KafkaListener` flow automatically and reproducibly both locally and in CI.

