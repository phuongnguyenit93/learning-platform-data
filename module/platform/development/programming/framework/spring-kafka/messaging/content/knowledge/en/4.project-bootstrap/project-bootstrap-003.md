# Declaring spring-boot-starter-kafka

## 1. Purpose of the Kafka Dependency in Spring Boot

For a Spring Boot application to send and receive Kafka events, it needs the Kafka client library, the Spring Kafka integration, and Spring Boot's auto-configuration mechanism. The recommended declaration for Spring Boot 4.x projects is adding the official `spring-boot-starter-kafka` dependency.

A starter is a dependency descriptor that aggregates the required libraries and integration configurations aligned with the Spring Boot ecosystem. After adding the starter, the application can configure connections via `spring.kafka.*`, inject `KafkaTemplate` to send records, and use `@KafkaListener` to receive records. Through dependency injection, infrastructure components are managed by Spring in the ApplicationContext.

In the `SPRING_KAFKA_MESSAGING` module, this starter is the starting point for subsequent topics on topics, partitions, consumer groups, serialization, retries, dead-lettering, transactions, and testing. It provides application-side libraries; it **does not install or automatically start a Kafka broker**. You still need a Kafka cluster locally, in Docker, or in a shared environment.

## 2. Choosing the Right Dependency by Spring Boot Version

The dependency name depends on the Spring Boot line in use:

| Platform Version | Commonly Used Dependency | Notes |
|---|---|---|
| Spring Boot 4.x | `org.springframework.boot:spring-boot-starter-kafka` | Official Kafka starter, including Spring Boot's Kafka integration and Spring Kafka |
| Spring Boot 3.x | `org.springframework.kafka:spring-kafka` | Boot 3 projects typically declare Spring Kafka directly; check documentation for the exact Boot version to verify auto-configuration and compatible versions |
| Spring Framework application without Spring Boot | `org.springframework.kafka:spring-kafka` | Manually configure factories, templates, listener containers, and required infrastructure components |

For Spring Boot 4.x projects, do not replace the starter with `spring-kafka` alone if the application needs Boot auto-configuration. The `spring-boot-starter-kafka` starter enables Boot's integration, including `spring.kafka.*` property binding, `KafkaTemplate` configuration, and `@KafkaListener` infrastructure. Adding only `spring-kafka` may leave the application with Kafka classes on the classpath while missing the expected Boot beans and configurations.

Do not mix dependencies from different Spring Boot release lines in the same project. Before adding libraries, identify the Spring Boot version managed by the project's parent POM, Gradle plugin, or BOM.

## 3. Declaring the Dependency with Maven

If the project uses the Spring Boot parent or already imports the `spring-boot-dependencies` BOM, simply declare the artifact and let Spring Boot manage the version:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka</artifactId>
    </dependency>
</dependencies>
```

Usually there is no need to add a `<version>` tag for the starter. The Spring Boot BOM provides a version set tested for compatibility across Spring Boot, Spring Kafka, and the Apache Kafka client. When upgrading Spring Boot, dependency management updates the related versions as a cohesive set.

If the project does not use the Spring Boot parent, you can import the BOM inside `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Then declare `spring-boot-starter-kafka` inside `<dependencies>` without specifying an individual version. The `${spring-boot.version}` value must match the Spring Boot version chosen by the project.

For Spring Boot 3.x projects, the corresponding dependency is typically:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
```

Still use Spring Boot dependency management to manage the version; do not pick an arbitrary Spring Kafka version and pair it with Boot 3.x.

## 4. Declaring the Dependency with Gradle

With Gradle Groovy DSL, a Spring Boot 4.x project can declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-kafka'
}
```

With Gradle Kotlin DSL (`build.gradle.kts`):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-kafka")
}
```

The examples above assume the project already applies the Spring Boot Gradle plugin or corresponding dependency management mechanism to manage versions. If the project uses Spring Boot 3.x, the commonly used dependency is `org.springframework.kafka:spring-kafka`:

```kotlin
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
}
```

Do not declare both the Kafka starter and a different `spring-kafka` version just to force a version upgrade or downgrade. If an override is needed, follow the compatibility guidance for the exact Spring Boot line and inspect the full dependency graph.

## 5. Dependency for Testing

Testing producers and consumers may require a separate test library. For Spring Boot 4.x, you can add the Kafka test starter:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-kafka-test")
}
```

For Spring Boot 3.x or projects declaring Spring Kafka directly, commonly used is:

```kotlin
dependencies {
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
```

The test dependency provides tools supporting integration testing, such as an embedded broker and listener verification utilities. Add the test dependency only to the test scope (`testImplementation` or Maven `<scope>test</scope>`), never package it into the application runtime. The choice of test broker and how it is started should align with the Kafka client version and Spring Kafka version in use.

## 6. What Components Does the Starter Bring into the Application?

With Spring Boot 4.x, `spring-boot-starter-kafka` brings in Spring Boot's Kafka integration and Spring Kafka. From there, the application can use typical components:

| Component | Role |
|---|---|
| Spring Boot Kafka auto-configuration | Reads `spring.kafka.*` properties and creates appropriate infrastructure in the ApplicationContext |
| `ProducerFactory` | Creates and manages Kafka producers |
| `KafkaTemplate` | API for sending records from business services |
| `ConsumerFactory` | Creates Kafka consumers according to configuration |
| Listener container factory | Creates listener containers for endpoints receiving messages |
| `@KafkaListener` infrastructure | Detects endpoints and connects listener methods to containers |
| `KafkaAdmin` | Supports Kafka administrative operations, such as declaring topics with `NewTopic` |

These are Spring abstractions; the Kafka broker remains a separate process. When the application starts, Boot creates beans based on the classpath, configuration, and any custom beans declared. If the application provides custom factories or templates, configure them explicitly so listeners and publishers use the intended beans.

In a Spring Framework application without Boot, adding `spring-kafka` alone will not automatically create all infrastructure. You must declare `ProducerFactory`, `KafkaTemplate`, `ConsumerFactory`, listener container factory, and enable annotation processing with `@EnableKafka` as needed.

## 7. Minimal Connection Configuration

After declaring the dependency, create `application.yml` or add the following properties to the existing configuration file:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: spring-kafka-messaging
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer

app:
  kafka:
    topic: messaging-demo
```

Meaning of the key properties:

- `bootstrap-servers`: broker address used by the application to initiate connections and fetch metadata. Multiple brokers can be specified, separated by commas.
- `consumer.group-id`: default consumer group name. Instances in the same group share partitions of the topic.
- `consumer.auto-offset-reset`: starting position when the group does not yet have a valid offset; `earliest` requests reading from the oldest retained record, `latest` starts from records written after the group joins. This property does not overwrite an existing valid committed offset.
- `key-serializer` and `value-serializer`: convert key/value into bytes when the producer sends a record.
- `key-deserializer` and `value-deserializer`: convert bytes back into data types when the consumer receives a record.
- `app.kafka.topic`: custom application property to avoid hard-coding topic names in multiple places.

The example uses `StringSerializer` and `StringDeserializer` to start with string payloads. When switching to JSON or Avro, you must configure the corresponding serializer/deserializer and schema; simply changing the generic type of `KafkaTemplate` is not enough.

## 8. Creating the First Publisher and Listener

Once Spring Boot auto-configuration is active, `KafkaTemplate` can be injected directly:

```java
@Component
public class DemoEventPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final String topic;

    public DemoEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            @Value("${app.kafka.topic}") String topic) {
        this.kafkaTemplate = kafkaTemplate;
        this.topic = topic;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String key, String payload) {
        return kafkaTemplate.send(topic, key, payload);
    }
}
```

`KafkaTemplate` is configured by Boot from `spring.kafka.*`. The `send` method returns a future; the application should observe the result to log metadata or handle send failures. Do not ignore the future if the event represents an important business state change.

A consumer can be declared with `@KafkaListener`:

```java
@Component
public class DemoEventListener {

    @KafkaListener(topics = "${app.kafka.topic}")
    public void receive(String payload) {
        System.out.println("Received: " + payload);
    }
}
```

With Spring Boot and the Kafka starter, listener infrastructure is auto-configured; normally there is no need to declare `@EnableKafka` yourself. When the application runs, the listener container connects to the broker and polls records. If the broker is not running or `bootstrap-servers` is wrong, the listener may fail to start cleanly and the producer cannot send records.

The example above illustrates verifying dependencies and configuration. In a real application, move business processing into a dedicated service, add an event ID, control errors, and design idempotent handlers to tolerate redelivered records.

## 9. Verifying Loaded Dependencies

After adding the dependency, run the command appropriate for your build tool to confirm the starter and related libraries appear in the dependency graph.

**Maven:**

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:*,org.springframework.kafka:*,org.apache.kafka:*
```

**Gradle:**

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
```

On Windows, `gradlew.bat` can be used instead of `./gradlew`. Check the following points:

1. `spring-boot-starter-kafka` is present in the runtime dependency graph for Boot 4.x projects.
2. Compatible Spring Kafka and Apache Kafka client libraries are pulled in.
3. No multiple versions of Spring Kafka or Kafka client are unexpectedly forced into the same runtime.
4. Test dependencies appear only in the test classpath, not in the runtime classpath.

If the build fails to download dependencies, check Maven/Gradle repositories, proxies, network connectivity, and JDK version before changing library versions.

## 10. Common Mistakes When Declaring the Starter

| Symptom | Common Cause | Resolution |
|---|---|---|
| Cannot inject `KafkaTemplate` | Missing Kafka starter or auto-configuration not enabled; custom bean configuration is incorrect | Check dependency for your Boot line, component/configuration scanning, and auto-configuration conditions |
| `spring.kafka.*` has no effect | Using the Spring Kafka dependency directly without the required Boot integration, or invalid YAML structure | For Boot 4.x use `spring-boot-starter-kafka`; check indentation and property names |
| `NoClassDefFoundError` or `NoSuchMethodError` | Incompatible versions of Spring Kafka, Spring Framework, or Kafka client | Use the Boot BOM; remove unnecessary version overrides and inspect the dependency tree |
| Listener does not receive records | Broker unreachable, wrong topic, group has no partition assigned, or deserializer error | Check broker, topic, group, partition assignment, and listener logs |
| Producer throws serialization error | Serializer does not support payload type or producer config mismatches data type | Align serializers/deserializers with key/value types |
| Build succeeds but runtime cannot connect to Kafka | Starter only provides application-side libraries; broker is not running or address is wrong | Start Kafka and verify `bootstrap-servers` |

Do not resolve errors by adding multiple dependency versions through trial and error. Identify the Spring Boot line, let the BOM manage versions, and inspect the dependency graph before changing configuration.

## 11. Recommended Initialization Workflow

1. Identify the Spring Boot and JDK versions supported by the project.
2. Choose the appropriate dependency: Boot 4.x uses `spring-boot-starter-kafka`; Boot 3.x follows its version-specific guide, typically declaring `spring-kafka`.
3. Let Spring Boot dependency management manage versions; avoid pinning Kafka client and Spring Kafka separately unless there is a specific compatibility requirement.
4. Add minimal `bootstrap-servers`, group ID, and serializer/deserializer configuration.
5. Verify the dependency graph and ensure the Kafka broker is running.
6. Inject `KafkaTemplate`, declare `@KafkaListener`, then test a record flowing end-to-end through send and receive.
7. Add JSON, retry, dead-letter, transaction, and test configurations according to business needs in subsequent steps.

## 12. Summary

- `spring-boot-starter-kafka` is the official starter for Spring Boot 4.x to integrate Apache Kafka.
- Spring Boot 3.x projects can use `org.springframework.kafka:spring-kafka` following the guidance for that Boot version.
- Use Maven or Gradle and let the Spring Boot BOM manage dependency versions.
- The starter provides application-side integrations such as `KafkaTemplate`, consumer factories, and listener infrastructure; it does not install a Kafka broker.
- `spring.kafka.*` configures connections and producer/consumer behavior; serializers/deserializers must match data types.
- Verify the dependency tree before troubleshooting missing beans or version conflicts.

Once dependencies and the basic connection work, the project has a foundation to implement publish-subscribe flows with `KafkaTemplate` and `@KafkaListener`, and then expand to Spring Kafka's reliability and operational mechanisms.

## References

- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Boot Reference — Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring for Apache Kafka — Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html)
