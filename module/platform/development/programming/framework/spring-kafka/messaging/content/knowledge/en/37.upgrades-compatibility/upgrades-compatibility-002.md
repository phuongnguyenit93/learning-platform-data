# Spring Boot and kafka-clients Compatibility

A Spring Kafka application does not have just one version to care about. At build time, the application pulls libraries from Spring Boot, Spring Kafka, and Apache Kafka. At runtime, the Kafka client connects to a separately deployed Kafka broker. During testing, the project may also use spring-kafka-test or an embedded broker. These components are related, but they are not a single product and are not required to carry the same version number.

Spring Boot provides dependency management via a BOM to select a set of versions tested together. Spring Kafka builds on top of the Apache Kafka client API. Therefore, when upgrading, you must ensure the Spring Kafka version is compatible with Spring Framework and the Kafka client version it uses, while also checking whether the Kafka client can communicate with the current broker.

This lesson explains how to read version relationships, use the BOM properly, identify actual resolved versions in Maven/Gradle, override versions when justified, distinguish the client from the broker, handle Spring Kafka 3.x/4.x differences, and establish a controlled upgrade process.

> The illustrative versions in this lesson are checked against stable documentation as of 17-11-2026. This is a snapshot of the BOM at the reference date; when deploying, always verify the dependency management of the exact Spring Boot version you are using.

## Learning objectives

After this lesson, you will be able to:

- Distinguish Spring Boot, Spring Framework, Spring Kafka, kafka-clients, and Kafka broker.
- Explain the role of the Spring Boot BOM in selecting dependency versions.
- Read the Spring Kafka and Kafka client versions managed by Boot.
- Declare dependencies properly in Maven and Gradle.
- Distinguish how Spring Kafka is declared on Boot 3.x versus Boot 4.x.
- Override kafka.version or spring-kafka.version when there is a technical reason.
- Detect multiple versions of kafka-clients appearing in the dependency graph.
- Distinguish Java library compatibility from client-broker protocol compatibility.
- Check Java, Spring Framework, and build tool requirements before upgrading.
- Identify key changes when moving from Spring Kafka 3.x to 4.x.
- Update embedded Kafka tests for KRaft.
- Build a test matrix and rollout plan for an upgrade.

## 1. Which versions exist in a Spring Kafka application?

An application usually has at least five version components to distinguish:

| Component | Role | Where is it managed? |
|---|---|---|
| Spring Boot | Application platform, auto-configuration, and dependency management | Parent/BOM or Gradle plugin |
| Spring Framework | Container, DI, transactions, retry, and core APIs | Usually managed by Spring Boot |
| Spring Kafka | KafkaTemplate, @KafkaListener, listener container, error handling, and Spring integration | Managed by the Spring Boot BOM or declared directly |
| Apache Kafka client (kafka-clients) | Producer, Consumer, AdminClient, and protocol for talking to the broker | Usually managed by the Spring Boot BOM via kafka.version |
| Kafka broker | Actual cluster storing partitions, handling produce/fetch, and managing consumer groups | Deployed and upgraded independently from the application |

In addition, the project may use:

- spring-kafka-test for integration testing.
- kafka-streams if using Kafka Streams.
- kafka-streams-test-utils for topology testing.
- Schema Registry client, Avro/Protobuf/JSON Schema serializers.
- Kafka Connect client or vendor libraries.
- Testcontainers or an embedded Kafka broker.

Do not infer the broker version from the kafka-clients version in pom.xml. The broker typically lives in infrastructure, container images, or a separately managed Kafka service.

## 2. Distinguishing Spring Kafka and kafka-clients

spring-kafka is the library integrating Kafka into the Spring ecosystem. It provides abstractions and lifecycle management such as:

- KafkaTemplate for sending records.
- @KafkaListener for declaring listeners.
- ConcurrentMessageListenerContainer for managing consumers.
- KafkaAdmin and NewTopic for managing topics.
- Error handlers, retry, DLT, and transaction integration.
- Message converters, serializer/deserializer integration, and observation.

kafka-clients is the Apache Kafka library providing low-level client APIs:

- KafkaProducer.
- KafkaConsumer.
- AdminClient.
- ProducerRecord, ConsumerRecord.
- Serializers, deserializers, and client configurations.
- Network protocol and requests/responses with the broker.

Spring Kafka calls kafka-clients APIs. If you upgrade kafka-clients to a version with API changes that Spring Kafka does not yet support, the application may encounter compile errors or runtime errors such as NoSuchMethodError.

Conversely, if a newer Spring Kafka requires a Kafka client API but an older client is loaded at runtime, the application can also fail to start.

Therefore, do not upgrade kafka-clients on its own just because a newer Apache Kafka version exists. Check the Spring Kafka version and Spring Boot dependency management first.

## 3. What problem does the Spring Boot BOM solve?

A BOM (Bill of Materials) is a set of dependency version management rules. Spring Boot publishes the spring-boot-dependencies BOM containing library versions selected together.

When a project uses the Spring Boot parent or imports the BOM, managed dependencies can be declared without specifying a version on each dependency.

Example:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
~~~

Maven takes the version of spring-kafka from the active dependency management.

Benefits:

- Reduces the number of versions you must manage manually.
- Keeps Spring Framework and Spring libraries on the same baseline.
- Reduces the risk of a dependency pulling in an unexpected Kafka client version.
- When upgrading Boot, managed dependencies can be upgraded in sync.
- Makes it easier to reproduce the dependency graph across local, CI, and production environments.

The BOM does not guarantee that every third-party library in the application is compatible. It only manages dependencies listed in the BOM and those inherited according to build tool rules. Another library may declare its own version or pull in a dependency from a different baseline.

Spring Boot documentation recommends using Maven or Gradle to leverage dependency management and allows overrides when there is a specific need. See [Spring Boot – Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html).

## 4. Examples of versions managed by Spring Boot

The table below illustrates the dependency graph of two stable Spring Boot lines as of 17-11-2026:

| Spring Boot | Spring Framework baseline | Spring Kafka | kafka-clients | Minimum Java |
|---|---|---|---|---:|
| 3.5.16 | 6.2.19 | 3.3.16 | 3.9.2 | 17 |
| 4.1.2 | 7.0.10 | 4.1.2 | 4.2.2 | 17 |

These values are taken from the system requirements and managed dependency coordinates of each Boot release. See:

- [Spring Boot 3.5.16 – System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 3.5.16 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.1.2 – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4.1.2 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)

This table does not mean Spring Kafka 3.3.16 always requires Kafka client 3.9.2 or that every Boot 4 version uses Kafka client 4.2.2. These are the specific versions selected by the BOMs of these two Boot releases.

When using Spring Boot 3.5.16, dependency management selects Spring Kafka 3.3.16 and Kafka client 3.9.2. When using Spring Boot 4.1.2, the BOM selects Spring Kafka 4.1.2 and Kafka client 4.2.2.

If a new Boot patch release is published, the values in the BOM may change. Do not copy this table into a project as a set of versions to pin manually.

## 5. Spring Boot 3.x: declaring Spring Kafka without a version

With Spring Boot 3.5, the standard approach is to declare spring-kafka directly and let the BOM choose the version.

Maven with Spring Boot parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Do not declare versions for spring-kafka, spring-kafka-test, or kafka-clients if they are managed by the BOM.

If the project does not use the Spring Boot parent, you can import spring-boot-dependencies inside dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Then declare spring-kafka as a regular dependency without a version.

Spring Boot 3.5 manages Spring Kafka in its BOM, but does not have spring-boot-starter-kafka as an official starter like the Boot 4 line. Do not blindly copy Boot 4 dependency examples into Boot 3.5.

## 6. Spring Boot 4.x: using the Kafka starter

Spring Boot 4 provides an official starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka</artifactId>
</dependency>
~~~

The starter brings the required dependencies and Kafka auto-configuration into the application. The version is managed by the Spring Boot BOM.

With Spring Boot 4.1.2:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

If you need KafkaTemplate, @KafkaListener, or spring.kafka.*, this starter provides the Spring Kafka integration. You do not need to manually add another spring-kafka version.

If you need to declare the Spring Kafka library directly instead of the starter, you can use org.springframework.kafka:spring-kafka and still let the Boot BOM manage the version.

References: [Spring Kafka Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html) and [Spring Boot Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html).

## 7. Configuring Gradle with the Spring Boot BOM

Gradle can use the io.spring.dependency-management plugin or Gradle's native BOM mechanism.

Example using the plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-kafka'
    testImplementation 'org.springframework.boot:spring-boot-starter-kafka-test'
}
~~~

You do not need to specify a version for the starter. The Spring Boot plugin and dependency management plugin import Boot's BOM into dependency management.

If using Gradle Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-kafka")
    testImplementation("org.springframework.boot:spring-boot-starter-kafka-test")
}
~~~

With Spring Boot 3.5, the commonly used dependencies are:

~~~groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

If using native BOM support, you can import the BOM with platform():

~~~kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.2"))
    implementation("org.springframework.boot:spring-boot-starter-kafka")
    testImplementation("org.springframework.boot:spring-boot-starter-kafka-test")
}
~~~

Do not combine multiple dependency management mechanisms arbitrarily. Identify which BOM is the primary management source and check the final resolved versions.

## 8. Do not declare a separate version for kafka-clients unless needed

A common mistake is adding kafka-clients with a different version just to use a new API:

~~~xml
<!-- Do not do this without checking compatibility -->
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-clients</artifactId>
    <version>4.2.2</version>
</dependency>
~~~

If Spring Boot 3.5 is managing Spring Kafka 3.3.x and Kafka client 3.9.2, forcing the client to 4.2.2 can create an unsupported combination. Spring Kafka may call APIs that differ from what is loaded at runtime.

Only declare kafka-clients directly when the application actually uses Apache Kafka APIs directly and has a reason to manage that dependency. In normal cases, spring-kafka already pulls in the appropriate Kafka client.

If you need a different Kafka client version, check:

- Does the Spring Kafka version support that Kafka client?
- Does the Spring Boot BOM have a corresponding override property?
- Do Kafka Streams and other Kafka modules need the same version?
- Does spring-kafka-test use the corresponding broker/test dependencies?
- Are other libraries pulling in another kafka-clients version?

A dependency graph has only one effective Kafka client version. If multiple versions are declared, Maven/Gradle resolves them according to mediation/constraint rules. The final version may not be the one you assumed when reading a single dependency line.

## 9. Overriding kafka.version when justified

Spring Boot uses the kafka.version property to manage the versions of Apache Kafka modules, including kafka-clients and related modules such as kafka-streams.

The example below illustrates property overrides for a combination of Spring Kafka 4.1.2 and Kafka client 4.0.0 used as a sample in the Spring Kafka documentation. This is not the default configuration of Spring Boot 4.1.2 and should not be copied to Boot 3.5:

~~~xml
<properties>
    <kafka.version>4.0.0</kafka.version>
    <spring-kafka.version>4.1.2</spring-kafka.version>
</properties>
~~~

When a project uses the Spring Boot parent or a BOM that supports this property, managed Kafka dependencies can be changed via the property.

Gradle example with io.spring.dependency-management:

~~~groovy
ext['kafka.version'] = '4.0.0'
ext['spring-kafka.version'] = '4.1.2'

dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.apache.kafka:kafka-streams'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

Only override after verifying that the version is compatible with Spring Kafka and the modules in use.

Do not override the Kafka client merely to match the broker version number. Client and broker have independent release cycles; base your decision on the compatibility matrix and actual APIs.

If you use embedded Kafka, kafka.version can also affect the broker modules used in tests. In that case, you must re-test the test harness rather than only checking that the application compiles.

## 10. Overriding spring-kafka.version

Spring Kafka also has a version property in Spring Boot's dependency management. You can use spring-kafka.version when you want to use a different Spring Kafka version from the BOM default and that combination is supported.

Maven:

~~~xml
<properties>
    <spring-kafka.version>3.3.16</spring-kafka.version>
</properties>
~~~

In this example, 3.3.16 is the version managed by Spring Boot 3.5.16 as of the reference date. Keeping the same value merely pins the current version explicitly; if you need to change it, pick a Spring Kafka release from a line compatible with the Spring Framework of your Boot version and re-verify the dependency graph.

Gradle:

~~~groovy
ext['spring-kafka.version'] = '3.3.16'

dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

This property should be understood as changing the Spring Kafka family version, not a magic switch that makes any Spring Framework combination compatible.

For example, do not attach Spring Kafka 4.1.x to a Boot 3.5 application just because the property can be overridden. Boot 3.5 uses Spring Framework 6.2, whereas Spring Kafka 4.x is built on Spring Framework 7.0. Such a version override can cause class/method errors at runtime.

Similarly, do not upgrade spring-kafka-test independently from spring-kafka. Both artifacts need the same baseline so the test framework and runtime framework have compatible APIs.

Spring Kafka documentation covers overrides at [Override Spring Boot Dependencies](https://docs.spring.io/spring-kafka/reference/appendix/override-boot-dependencies.html). Follow the example for the exact stable documentation line you are using.

## 11. Distinguishing the client version from the broker version

kafka-clients is a library running inside the Spring application. The Kafka broker is a server in the cluster. They communicate over the Kafka protocol.

There is no mandatory rule that the client version must equal the broker version.

Example:

~~~text
Spring Boot application
  Spring Kafka 3.3.x
  kafka-clients 3.9.x
          |
          | Kafka protocol
          v
Kafka broker cluster 3.9.x
~~~

Or a newer client can communicate with an older broker if the required protocol APIs are still supported and no broker-only newer features are used.

Client-broker compatibility depends on:

- Kafka protocol API versions.
- Producer/consumer features used by the application.
- APIs removed or changed across major versions.
- Metadata version and broker capabilities.
- Consumer group protocol configuration.
- Transactions, idempotent producer, and new broker features.
- Vendor client libraries if not using the Apache Kafka client.

Do not look at kafka-clients 4.x and conclude the broker must be 4.x. Nor should you assume a 3.x broker automatically supports every new feature of a 4.x client.

## 12. Kafka 4 client and older brokers

Kafka 4.0 removes old protocol APIs prior to 0.10.x. When upgrading the Java client to Kafka 4.0, Apache Kafka documentation requires the broker to be 2.1 or newer; a 4.0 client is incompatible with brokers older than that threshold.

Distinguish the two directions of checking. The requirement for broker 2.1 or newer above is the condition for a 4.0 client to connect to older brokers. Apache Kafka's compatibility matrix also checks the reverse direction: 2.1–2.8 clients are only partially compatible with a Kafka 4.0 broker, whereas 3.x clients are listed as fully compatible with a Kafka 4.0 broker. Do not invert these two conclusions.

When upgrading the client, check the matrix for the exact target Kafka version and the APIs your application uses:

- [Apache Kafka – Compatibility](https://kafka.apache.org/43/getting-started/compatibility/)
- [Apache Kafka – Upgrading](https://kafka.apache.org/40/getting-started/upgrade/)

These limits concern the client-broker protocol. They do not replace checking whether Spring Kafka is compatible with the selected Kafka client APIs.

## 13. Kafka 4 broker and KRaft are separate from the Kafka 4 client

Kafka 4 brokers only support KRaft; ZooKeeper mode has been removed. This is a server-side change in how cluster metadata is managed.

Using a Kafka 4 client does not mean the broker cluster must be upgraded to Kafka 4 at the same time. Applications can upgrade the client first within protocol compatibility bounds, and plan the broker upgrade separately.

When upgrading brokers from Kafka 3.x to Kafka 4.x:

- ZooKeeper clusters must be migrated to KRaft first.
- KRaft clusters must meet version and metadata version requirements.
- The rolling upgrade procedure must be tested.
- Feature levels must be checked before finalizing the upgrade.
- Do not assume metadata can be downgraded after raising the feature level if the Kafka version does not support it.

Apache Kafka 4.0 documentation states that brokers can be upgraded from 3.3.x through 3.9.x after meeting KRaft prerequisites; clusters using ZooKeeper must migrate first. See [Kafka 4.0 Upgrade Guide](https://kafka.apache.org/40/getting-started/upgrade/).

Do not confuse this change with upgrading the kafka-clients dependency in an application. One is upgrading a client library; the other is changing the server platform and cluster metadata architecture.

## 14. Java and build tool requirements

The Spring Boot version sets runtime and build tool requirements. The Kafka client version also has its own requirements, though in a Spring Boot application you must satisfy the highest requirement across the entire stack.

As of the reference date:

| Platform | Minimum Java | Spring Framework | Build tool |
|---|---:|---|---|
| Spring Boot 3.5.16 | 17 | 6.2.19 or higher | Maven 3.6.3+, Gradle 7.6.4+ or 8.4+ |
| Spring Boot 4.1.2 | 17 | 7.0.10 or higher | Maven 3.6.3+, Gradle 8.14+ or 9.x |

Spring Boot 4.1.2 requires Java 17 or higher and Spring Framework 7.0.10 or higher. Boot 3.5.16 requires Java 17 or higher and Spring Framework 6.2.19 or higher.

Do not check only the JDK on a developer machine. You must check:

- JDK in CI.
- JDK in the Docker image or runtime platform.
- Maven/Gradle wrapper.
- Toolchain configured in Gradle.
- maven.compiler.release or Java toolchain.
- Compiler, test, and packaging plugins.
- JDK used to run embedded Kafka tests.

A project that compiles locally on JDK 21 while CI still runs JDK 17 can fail if bytecode targets or plugins are configured inconsistently.

## 15. What changes in Spring Kafka 4.x require attention?

Upgrading from Spring Kafka 3.3 to 4.0 is a major upgrade and should not be treated as merely changing a version in the BOM.

Notable changes:

| Area | Spring Kafka 3.3 | Spring Kafka 4.0 and higher |
|---|---|---|
| Spring Framework | 6.x line | 7.x line |
| Kafka client baseline | 3.x line | Kafka 4.0 and higher |
| Embedded Kafka | Can use ZooKeeper or KRaft infrastructure depending on configuration | KRaft only |
| EmbeddedKafkaZKBroker | Still exists | Removed |
| EmbeddedKafkaRule JUnit 4 | Present | Removed |
| Retry API | Relies on Spring Retry in some configurations | Moves to retry support in Spring Framework 7 and Spring Kafka |
| Backoff annotation | @Backoff | @BackOff |
| Jackson | Jackson 2 is the common choice | Supports Jackson 3, prefers Jackson 3 if present |

Spring Kafka 4.0 also has other API changes such as the ConsumerRecords constructor, certain Kafka Streams APIs, and removal of deprecated APIs. Read the change history and migration guide before upgrading.

Reference: [Spring Kafka Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html).

## 16. Retry annotation changes when moving to Spring Kafka 4

Spring Kafka 4 removes the Spring Retry dependency and uses Spring Framework 7's retry support. This affects several retry APIs and configurations.

Previously:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
            delay = 2000,
            maxDelay = 10000,
            multiplier = 2
    )
)
@KafkaListener(topics = "orders")
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

In Spring Kafka 4:

~~~java
@RetryableTopic(
    attempts = "4",
    backOff = @BackOff(
            delay = 2000,
            maxDelay = 10000,
            multiplier = 2
    )
)
@KafkaListener(topics = "orders")
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

The change is not just the annotation name. Spring Retry API types such as BackOffPolicy, BinaryExceptionClassifier, or legacy callbacks may need to be migrated to the corresponding Spring Framework 7/Spring Kafka 4 APIs.

Do not just rename the annotation and assume the upgrade is complete. Search for Spring Retry imports and classes in application code, tests, and custom error handlers.

## 17. Embedded Kafka tests change when moving to Spring Kafka 4

Spring Kafka 4 only supports embedded Kafka running on KRaft. ZooKeeper-related APIs have been removed.

Changes to review:

- EmbeddedKafkaZKBroker is removed.
- EmbeddedKafkaKraftBroker is the broker implementation.
- JUnit 4's EmbeddedKafkaRule is removed.
- The kraft attribute in @EmbeddedKafka is no longer needed because KRaft is the only mode.
- ZooKeeper attributes such as zookeeperPort, zkConnectionTimeout, and zkSessionTimeout are removed.
- Imports and test utilities may have changed packages.
- Replication factor configuration in tests must fit KRaft and the broker count.

Example of the new test annotation style:

~~~java
@SpringBootTest
@EmbeddedKafka(
    topics = "orders",
    partitions = 3,
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderKafkaIntegrationTest {
    // Integration tests
}
~~~

Do not include `kraft = true` in new examples because Spring Kafka 4 no longer has a ZooKeeper embedded broker option.

If the project is still on Spring Kafka 3.3, the test framework may have legacy APIs and configurable KRaft mode. Check the dependency version before copying test code between the two major branches.

## 18. How to inspect the actual dependency graph

Do not only read pom.xml or build.gradle. Inspect the final versions resolved by the build tool.

### Maven

View all Kafka-related dependencies:

~~~bash
mvn dependency:tree -Dincludes=org.apache.kafka,org.springframework.kafka
~~~

View the effective POM and properties after importing the BOM:

~~~bash
mvn help:effective-pom
~~~

If you need to inspect only the Kafka client:

~~~bash
mvn dependency:tree -Dincludes=org.apache.kafka:kafka-clients
~~~

### Gradle

View the runtime dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Find why a particular version was selected:

~~~bash
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
~~~

Check Spring Kafka:

~~~bash
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
~~~

Pay particular attention to:

- How many versions of kafka-clients are requested?
- Which version is actually selected?
- Which dependency pulls that version in?
- Does kafka-streams have a different version from kafka-clients?
- Does spring-kafka-test have the same version as spring-kafka?
- Does any vendor library bundle its own Kafka client?

If the dependency graph contains multiple versions during resolution, find the source pulling in the other version before forcing a resolution strategy.

## 19. Checking dependency alignment in a multi-module project

A project may consist of multiple modules:

~~~text
messaging-platform
  |
  +-- order-service
  |     +-- spring-kafka
  |
  +-- billing-service
  |     +-- spring-kafka
  |
  +-- event-contract
  |     +-- does not need kafka-clients if it only contains DTOs
  |
  +-- integration-tests
        +-- spring-kafka-test
        +-- embedded Kafka
~~~

If each module imports a different BOM, the runtime or test classpath can drift out of alignment.

You should:

- Set a unified Spring Boot version in the build root when services share a build.
- Import one primary BOM for Spring dependencies.
- Avoid scattering Kafka client versions across individual modules.
- Keep spring-kafka and spring-kafka-test on the same baseline.
- If using Kafka Streams, align kafka-streams with the Kafka client version.
- Inspect the dependency graph of test modules separately, not only application modules.
- Avoid having a shared library bundle or shade a different copy of kafka-clients.

If each service is built and deployed independently, each service can have its own BOM. In that case, verify protocol compatibility with the broker and do not assume all services must run the exact same client version.

## 20. Test matrix when upgrading

An upgrade should not stop at a passing `mvn test`. Verify build, startup, message flow, broker, and test harness.

| Test layer | What to verify |
|---|---|
| Compile | No removed APIs or imports remain |
| Application context | Boot auto-configuration creates KafkaTemplate and listener factories |
| Producer | Serializers, keys, headers, retries, and send results work |
| Consumer | Deserializers, group membership, offsets, and rebalances work |
| Retry/DLT | Error handler, retry topics, recoverer, and partition routing are correct |
| Transaction | Producer transactions, offset transactions, and rollbacks work properly |
| Security | SSL, SASL, JAAS, truststore, and ACLs connect properly |
| Observability | Metrics, tracing, and logs do not lose information |
| Integration test | spring-kafka-test or Testcontainers works with the chosen client/broker |
| Broker compatibility | New client communicates with the current cluster |
| Load test | Latency, throughput, memory, and rebalances do not degrade unexpectedly |

For major upgrades, have a staging environment running a broker version close to production. Embedded Kafka is suitable for logic tests but does not fully replace testing against a real deployed broker, especially for security, replication, ACLs, and rolling upgrades.

## 21. Layered upgrade process

Do not upgrade every component simultaneously in one large change without good reason.

A reference workflow:

1. **Inventory:** record Boot, Spring Framework, Spring Kafka, Kafka client, broker, Java, and build tool versions.
2. **Read the target BOM:** identify the Spring Kafka and kafka-clients versions managed by the new Boot release.
3. **Check Java:** upgrade the JDK and build tool if required by the target Boot version.
4. **Upgrade Boot:** change the parent/plugin/BOM and remove version overrides that are no longer needed.
5. **Inspect dependency graph:** confirm there is only one appropriate Kafka client version.
6. **Fix APIs:** update deprecated or removed Spring Kafka/Kafka client APIs.
7. **Upgrade tests:** update spring-kafka-test, embedded broker, JUnit, and KRaft test setup.
8. **Run integration tests:** verify producer, consumer, retry, transactions, and security.
9. **Check broker compatibility:** compare the new client against the running cluster.
10. **Deploy to staging:** observe logs, consumer lag, rebalances, and throughput.
11. **Rolling rollout:** upgrade service instances according to plan, keeping code rollback capability while still compatible.
12. **Upgrade the broker separately:** if the server needs upgrading, follow Apache Kafka's upgrade and KRaft migration procedures.

If upgrading from Spring Boot 3.5 to 4.1, treat this as a major migration because Spring Framework moves from 6.2 to 7.0 and Spring Kafka moves from 3.x to 4.x.

## 22. Separating client and broker upgrade plans

A plan can be split into two independent tracks:

~~~mermaid
flowchart TD
    A["Inventory dependencies and broker"] --> B["Upgrade Spring Boot application"]
    B --> C["Upgrade Spring Kafka / kafka-clients"]
    C --> D["Test against current broker"]
    D --> E["Deploy application"]
    E --> F["Evaluate broker upgrade"]
    F --> G{"Cluster already on KRaft?"}
    G -->|Yes| H["Plan broker upgrade"]
    G -->|No| I["Migrate ZooKeeper to KRaft"]
    I --> H
    H --> J["Rolling upgrade broker"]
    J --> K["Verify metadata and feature levels"]
~~~

For example, an application can move to Spring Kafka 4 and Kafka client 4 before the broker cluster undergoes a major upgrade, provided client-broker compatibility is verified. Upgrading the broker to Kafka 4, in turn, requires KRaft.

Do not roll out kafka-clients and broker changes to production in the same step without separate observation and rollback plans. If an error occurs, separating the changes helps identify the root cause faster.

## 23. Common mistakes

**Manually pinning spring-kafka version while using the Boot BOM.** The dependency can drift out of sync with Spring Framework or other modules. Remove the version so the BOM manages it, unless there is a verified override reason.

**Upgrading kafka-clients independently.** Spring Kafka may call APIs that do not exist in the runtime client. Check compatibility and the dependency graph first.

**Using Spring Kafka 4 with Spring Framework 6.** Spring Kafka 4 is based on Spring Framework 7. Upgrade Boot/Spring Framework according to supported combinations.

**Using a different version of spring-kafka-test from spring-kafka.** Test APIs and runtime APIs may be incompatible. Align both artifacts.

**Assuming the Kafka client must match the broker version.** Client and broker can differ within protocol compatibility limits. Check the Apache Kafka matrix.

**Assuming a Kafka 4 client forces the broker to be Kafka 4.** Client and broker upgrades are two separate efforts. Check protocol thresholds and the features in use.

**Upgrading to a Kafka 4 broker while the cluster is still in ZooKeeper mode.** Kafka 4 brokers only support KRaft. Metadata migration must be completed according to Apache Kafka's guide.

**Using EmbeddedKafkaZKBroker after upgrading to Spring Kafka 4.** This API has been removed. Switch to the KRaft test infrastructure.

**Keeping @Backoff when upgrading to Spring Kafka 4.** The API moved to @BackOff and the new retry support. Audit imports, annotations, and custom retry configurations.

**Running only unit tests.** Unit tests do not prove broker compatibility, transactions, rebalances, or security. Add integration tests with an appropriate broker.

**Reading only declared dependencies without inspecting resolved dependencies.** Dependency mediation can choose a different version. Use dependency:tree or dependencyInsight.

**Using a set of versions from an old tutorial for a current project.** BOMs change across patch releases. Check the documentation for your exact Boot version.

## 24. Compatibility checklist before merging

- [ ] Identified the active Spring Boot version and BOM.
- [ ] Identified the Spring Framework version managed by Boot.
- [ ] Identified the resolved Spring Kafka version.
- [ ] Identified the actual kafka-clients version.
- [ ] Identified the broker version and broker mode (KRaft/ZooKeeper).
- [ ] Java runtime meets the requirements of Boot and libraries.
- [ ] Maven/Gradle wrapper meets build requirements.
- [ ] No unexpected multiple Kafka client versions exist.
- [ ] spring-kafka and spring-kafka-test are aligned.
- [ ] kafka-streams and other Kafka modules are aligned if used.
- [ ] Any overrides to kafka.version or spring-kafka.version have a reason and tests.
- [ ] Checked the client-broker compatibility matrix.
- [ ] Audited deprecated/removed APIs in Spring Kafka and Kafka client.
- [ ] Embedded Kafka tests updated for KRaft if moving to Spring Kafka 4.
- [ ] Retry, DLT, transactions, security, and observability have been tested.
- [ ] Appropriate rollout and rollback plans are in place.
- [ ] Broker upgrade is planned separately from the application upgrade.

## Conclusion

Spring Kafka compatibility depends on multiple layers: Spring Boot manages dependencies via a BOM, Spring Kafka uses kafka-clients APIs, and the Kafka broker is a server system communicating over a protocol. Let the BOM manage versions in typical cases, inspect the actual dependency graph, and only override when a compatible combination is verified. When performing a major Spring Boot or Spring Kafka upgrade, review Java/Spring Framework requirements, retry APIs, KRaft embedded Kafka, and Kafka client changes. Finally, test both the application and the current broker before rollout; do not infer broker versions from client versions or assume version numbers must be identical.

## References

- [Spring Boot – Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot – Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Boot 3.5 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.1 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Kafka – Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html)
- [Spring Kafka – Override Spring Boot Dependencies](https://docs.spring.io/spring-kafka/reference/appendix/override-boot-dependencies.html)
- [Spring Kafka – Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
- [Apache Kafka – Compatibility](https://kafka.apache.org/43/getting-started/compatibility/)
- [Apache Kafka – Upgrade Guide](https://kafka.apache.org/40/getting-started/upgrade/)

