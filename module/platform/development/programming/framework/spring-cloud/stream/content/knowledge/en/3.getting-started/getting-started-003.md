# Choosing Core, Binder, and Testing Libraries

When initializing a Spring Cloud Stream application, you need to choose three dependency groups correctly: foundational application libraries, the binder connecting to the broker, and testing libraries. Dependency selection should start with the event-processing model and target broker, and only then determine versions and testing tools.

Spring Cloud Stream provides the `Supplier`, `Function`, and `Consumer` function model along with the binding mechanism. The binder implements connecting bindings to Kafka, RabbitMQ, Pulsar, or another messaging system. Testing libraries serve distinct goals: testing function logic, testing bindings in memory, and verifying real broker behavior. No single dependency replaces all of these layers.

## 1. Dividing Dependencies by Responsibility

An application typically has the following dependency layers:

| Layer | Responsibility | Examples |
|---|---|---|
| Spring Boot and Spring Cloud | Application foundation, configuration management, and version compatibility | Spring Boot, Spring Cloud release train |
| Spring Cloud Stream core | Function model, binding, message, and binder abstraction | `spring-cloud-stream` |
| Broker binder | Connects bindings to a specific broker | Kafka binder, Rabbit binder, Pulsar binder |
| Specialized stream processing | Builds stateful topologies on Kafka | Kafka Streams binder |
| Application testing | JUnit, Mockito, AssertJ, and Spring Test | `spring-boot-starter-test` |
| Binding testing | In-memory simulated binder | `spring-cloud-stream-test-binder` |
| Real broker testing | Spins up an isolated broker for integration tests | Testcontainers Kafka, RabbitMQ, or Pulsar |

In most applications, the binder starter already pulls in Spring Cloud Stream core as a transitive dependency. You can declare core directly if application code needs an explicit dependency on core APIs, but you should not add multiple starters just to get classes that are already pulled in.

It helps to distinguish three concepts:

- **Core** defines how the application declares and processes messages.
- **Binder** connects bindings to a broker and maps common configurations to broker semantics.
- **Test Binder** replaces the broker with an in-memory environment to test message flows at the application level.

## 2. Choosing Spring Boot and Spring Cloud Versions First

Spring Boot and Spring Cloud are released along version lines with a compatibility matrix. A binder may compile yet still be incompatible with the Spring Boot, Spring Framework, or Spring Cloud Stream version the application uses.

With Maven, you should import the Spring Cloud BOM compatible with your project's Spring Boot version. The BOM manages versions for modules belonging to the release train, avoiding separate version declarations for each binder:

```xml
<properties>
    <spring-cloud.version>SPRING_CLOUD_RELEASE_TRAIN</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

The value `SPRING_CLOUD_RELEASE_TRAIN` is a placeholder to be replaced with the release train published as compatible with your project's Spring Boot version. Do not copy a version number from an old guide without checking the current compatibility matrix.

Several principles for managing versions:

1. Choose the Spring Boot version based on the platform in use.
2. Check the Spring Cloud compatibility matrix and select the corresponding release train.
3. Let the BOM manage the versions of Spring Cloud Stream and binders belonging to the release train.
4. Check documentation for binders outside the release train, especially Pulsar or third-party maintained binders.
5. Only override Kafka, RabbitMQ, Pulsar, or Spring library versions when there is a clear reason and compatibility has been verified.

Do not arbitrarily pair a new binder with an old Spring Cloud Stream. When upgrading, inspect the dependency tree to detect unexpected versions of Spring Cloud Stream or broker clients being pulled in.

## 3. Choosing Core Libraries by Application Model

If the application uses Spring Cloud Stream's functional model, the binder starter is usually the main dependency to declare. For example, a function that receives an event and updates order status can be written as follows:

```java
@Configuration
class OrderFunctions {

    @Bean
    Consumer<OrderCreated> recordOrder(OrderService orderService) {
        return event -> orderService.record(event);
    }
}
```

The business function does not need to import Kafka or RabbitMQ APIs. Bindings and the binder handle receiving messages from the broker.

If you only need to send and receive messages using the functional model, Spring Cloud Stream core plus one binder is sufficient. If you need direct integration with Kafka, you can choose Spring for Apache Kafka (`spring-kafka`) with `KafkaTemplate` and `@KafkaListener`. If you need direct integration with RabbitMQ/AMQP, Spring AMQP (`spring-rabbit`) provides `RabbitTemplate` and `@RabbitListener`.

Do not add Spring Cloud Stream, Spring for Apache Kafka, and Spring AMQP all at once out of habit. Only add direct APIs when the application truly uses them—for instance, needing a specialized Kafka administrative component alongside Cloud Stream functions. Having multiple abstractions for the same data flow increases the number of configurations, listeners, and error-handling paths to operate.

## 4. Choosing a Binder by Broker and Processing Style

### Kafka message binder

For an application using Kafka as a standard message broker, you can use the starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-kafka</artifactId>
</dependency>
```

This starter provides the Kafka binder for Spring Cloud Stream. The application configures destinations as topics and groups as consumer groups. The binder handles creating producers/consumers, message conversion, and mapping binding configuration to Kafka properties.

Choose the Kafka binder when the application needs to receive or emit events in a message model, using Kafka-managed topics, partitions, consumer groups, and offsets. There is no need to add the Kafka Streams binder if you only process individual messages with a regular `Consumer` or `Function`.

### RabbitMQ binder

For RabbitMQ, use the starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-rabbit</artifactId>
</dependency>
```

The Rabbit binder connects bindings to exchanges and queues. Configurations such as destination, group, durable subscriptions, partitioning, and dead-lettering should be read against the Rabbit binder documentation because they map onto the AMQP model.

Choose the Rabbit binder when the application needs a queueing model and routing via exchanges, routing keys, and queues. Do not assume every Kafka property has a one-to-one equivalent in the Rabbit binder.

### Pulsar binder

If the system uses Apache Pulsar, you need to choose a Spring Cloud Stream binder compatible with your Spring Cloud Stream and Pulsar client versions. Some distributions provide an artifact named `spring-cloud-stream-binder-pulsar`; verify the groupId, version, maintenance status, and compatibility matrix according to that binder's own documentation before adding it to the project.

Do not confuse `spring-boot-starter-pulsar` with the Spring Cloud Stream Pulsar binder. The Spring Boot starter provides Pulsar integration at the Spring Boot/Spring Pulsar level; it does not automatically register a binder for Spring Cloud Stream bindings. If the application chooses the Spring Pulsar API directly, that is a different integration choice from the binder model.

When evaluating a Pulsar binder, verify whether important features are supported in that version: subscription types, consumer group semantics, partitioned topics, schemas, retries, dead-lettering, acknowledgements, transactions, and health indicators. Do not assume all common Spring Cloud Stream features are implemented identically by every binder.

### Kafka Streams binder

The Kafka Streams binder is for stateful stream processing applications using `KStream` and `KTable`, such as aggregations, joins, or windowing. The artifact used is:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
```

This is a specialized binder, distinct from the Kafka message binder. If the application only has a `Consumer<OrderCreated>` function, the Kafka message binder is usually more suitable. If the application needs a Kafka Streams topology and state stores, choose the Kafka Streams binder. Only put both on the classpath when a single application genuinely needs both models and has clearly configured its bindings, function definitions, and Kafka resources.

## 5. Dependency Selection Matrix

| Need | Primary dependency | Notes |
|---|---|---|
| Functions sending/receiving messages over Kafka | `spring-cloud-starter-stream-kafka` | Kafka message binder |
| Functions sending/receiving messages over RabbitMQ | `spring-cloud-starter-stream-rabbit` | Rabbit binder |
| Functions sending/receiving messages over Pulsar | Compatible Pulsar binder | Verify the binder's artifact and version matrix |
| Stateful stream processing on Kafka | `spring-cloud-stream-binder-kafka-streams` | Uses KStream/KTable and topology |
| Using Kafka API directly | `spring-kafka` or corresponding Spring Boot starter | Not a Cloud Stream binder |
| Using AMQP API directly | `spring-rabbit` or corresponding Spring Boot starter | Not a Cloud Stream binder |
| Using Pulsar API directly | Spring Pulsar / corresponding starter | Does not provide a Cloud Stream binder by itself |

A typical event-processing service should have one primary binder. Multiple binders only make sense when a service needs to connect multiple messaging systems, bridge between brokers, or migrate data. In that case, you must explicitly configure the default binder, the binder attached to each binding, destination names, groups, and broker-specific properties.

## 6. Choosing Testing Libraries by Layer

No single testing library proves the full behavior of an event-driven application. Use complementary testing layers.

### Testing Function Logic

Use JUnit 5, Mockito, and AssertJ through Spring Boot's test dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

You can invoke a `Consumer` or `Function` directly in a unit test, pass input data, and verify service calls or return values. This test style runs fast and helps verify business rules, invalid data handling, idempotency, and error cases.

Example:

```java
class OrderFunctionsTest {

    @Test
    void recordsCreatedOrder() {
        OrderService service = mock(OrderService.class);
        OrderFunctions functions = new OrderFunctions();

        Consumer<OrderCreated> consumer =
            functions.recordOrder(service);

        OrderCreated event = new OrderCreated("order-42");

        consumer.accept(event);

        verify(service).record(event);
    }
}
```

Unit tests do not need to start a Spring context or a broker if the goal is solely to verify function logic.

### Testing Bindings in Memory

Add the Spring Cloud Stream Test Binder in test scope:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
```

The Test Binder provides `InputDestination` and `OutputDestination` to send and receive messages in memory. It is suitable for checking function definitions, binding names, message conversion, and application-level processing flows without starting Kafka or RabbitMQ.

Example with a function that converts content to uppercase:

```java
@SpringBootTest(properties = {
    "spring.cloud.function.definition=uppercase"
})
class UppercaseBindingTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void sendsMessageThroughFunction() {
        input.send(
            new GenericMessage<>("hello".getBytes(StandardCharsets.UTF_8)),
            "uppercase-in-0"
        );

        Message<byte[]> result =
            output.receive(1000, "uppercase-out-0");

        assertThat(result).isNotNull();
        assertThat(new String(
            result.getPayload(), StandardCharsets.UTF_8
        )).isEqualTo("HELLO");
    }
}
```

The illustrative example assumes the application has a `Function<String, String> uppercase()` bean and an output binding configuration `uppercase-out-0`. In a real project, payload types, content types, and message converters must be consistent with the function under test.

The Test Binder does not start a real broker. It does not verify partition assignment, offset commits, consumer rebalancing, exchange routing, acknowledgements, transactions, broker retries, DLQs, security, or serializer compatibility with the broker. Do not use Test Binder results to conclude that production Kafka/RabbitMQ/Pulsar configuration is correct.

### Integration Testing with a Real Broker

Use Testcontainers or a dedicated test broker environment when you need to verify broker-dependent behavior. You can spin up a Kafka, RabbitMQ, or Pulsar container for the lifecycle of an integration test, configure the application to connect to the broker address provided by the container, and then send and receive messages just as in real deployment.

Commonly used Testcontainers modules include:

- Kafka: module `org.testcontainers:kafka`.
- RabbitMQ: module `org.testcontainers:rabbitmq`.
- Pulsar: module `org.testcontainers:pulsar`.

Artifact names and Java packages may change between Testcontainers versions; use the BOM or guide for the selected version to keep them aligned. Do not add random individual versions to each module.

Integration tests should verify behaviors important to the system: topic/queue creation or binding, serialization/deserialization, keys and partitions, consumer groups, acknowledgements, retries, DLQs, security configuration, and handling when the broker is temporarily unavailable. Not every test needs to cover all behaviors; choose the ones the application actually configures or relies on.

### Specialized Testing Libraries

Some integrations have dedicated tools:

| Component | Testing library | Goal |
|---|---|---|
| Spring for Apache Kafka | `spring-kafka-test` | Listener and Kafka testing tools; may provide an embedded broker depending on version |
| Kafka Streams | `kafka-streams-test-utils` | `TopologyTestDriver` for testing topologies and state stores |
| Spring AMQP | `spring-rabbit-test` | Test harness and utilities to assist listener testing |
| Spring Cloud Stream | `spring-cloud-stream-test-binder` | In-memory binding testing |
| Spring Boot | `spring-boot-starter-test` | JUnit, Mockito, AssertJ, and Spring Test |

Specialized libraries are only needed when the application uses the corresponding integration. For example, you do not need to add `spring-kafka-test` just because the application has the Kafka binder; if you are only testing functions and bindings, the Test Binder can suffice for that layer. If you need to test a Kafka Streams topology, `TopologyTestDriver` is a better fit than a unit test calling a business function directly.

## 7. Maven Configuration Example for a Kafka Application

The following example illustrates a service using the Kafka message binder and two testing layers: Spring Boot Test and Spring Cloud Stream Test Binder.

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-stream-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream-test-binder</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

The Spring Cloud BOM was declared in `dependencyManagement` in an earlier section. As a result, you do not need to attach individual versions to dependencies belonging to the release train.

If the project needs to test against real Kafka, you can add the Testcontainers Kafka module in test scope and manage the Testcontainers version with an appropriate BOM. When using RabbitMQ or Pulsar, swap in the container module for the corresponding broker. There is no need to package Testcontainers into the production artifact.

A test configuration should keep testing dependencies in `test` scope so mock libraries and containers do not end up on the runtime classpath of the deployed application.

## 8. Inspecting the Dependency Tree and Avoiding Conflicts

After adding dependencies, inspect the dependency tree to see which versions of core, Spring Kafka, Kafka client, Spring AMQP, or Pulsar client the binder pulled in. With Maven you can run:

```bash
mvn dependency:tree
```

Focus on checking:

- Only the expected release train and Spring Cloud Stream version are present.
- The binder matches the broker and processing model.
- There are not two different versions of the same Spring Framework or broker client caused by unintended overrides.
- Test libraries are in test scope.
- Neither Test Binder nor Testcontainers is packaged into runtime.
- Specialized modules such as the Kafka Streams binder and `kafka-streams-test-utils` have compatible versions.

If Maven reports dependency resolution errors or the application fails at startup with `NoSuchMethodError`, `ClassNotFoundException`, or `NoClassDefFoundError`, check the BOM and dependency tree before manually adding another version. These errors usually indicate an out-of-sync classpath or an incompatible library.

## 9. Practical Selection Workflow

You can follow this sequence when creating a new service:

1. Determine whether the application needs Spring Cloud Stream's functional API or the direct Kafka, AMQP, or Pulsar API.
2. Choose the Spring Boot version, then select the compatible Spring Cloud release train.
3. Choose exactly one binder matching the broker and processing style; for Kafka Streams, choose the Kafka Streams binder instead of the Kafka message binder if a stateful topology is the primary requirement.
4. Add `spring-boot-starter-test` for testing logic and the Spring context.
5. Add `spring-cloud-stream-test-binder` for in-memory binding tests.
6. Supplement with Testcontainers or specialized test libraries when broker behavior needs verification.
7. Inspect the dependency tree and run representative tests before deployment.

For example, a service that only consumes order events from Kafka typically needs the Kafka binder, Spring Boot Test, and the Test Binder. If verifying offsets, partitions, or retry topics is required, add integration tests with real Kafka. If a service aggregates orders per customer using time windows and state stores, use the Kafka Streams binder and test the topology with `TopologyTestDriver`.

Choosing the right libraries from the start keeps business code focused on events, lets the binder handle broker connectivity, and ensures the test suite verifies each layer within its proper scope. Before upgrading versions or switching brokers, re-check binder compatibility, delivery semantics, and the integration tests protecting the system.
