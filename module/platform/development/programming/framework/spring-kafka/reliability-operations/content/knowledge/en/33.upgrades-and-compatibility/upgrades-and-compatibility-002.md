# Spring Boot Compatibility in Spring Kafka — Safe Upgrade Guide

## 1. The Problem: Upgrading Spring Boot Is Not Just Changing a Version

An order-event processing application has been running stably on Spring Boot 2.x and Spring Kafka 2.x. After the development team switches to Spring Boot 3.x, the build may still succeed, yet producer callbacks no longer match the API, listeners use legacy exception handlers, or consumers cannot deserialize JSON with type headers from the previous system. When upgrading further to Boot 4.x, changes in modular starters, Jackson 3, Kafka client 4, and the retry API become part of the problem.

For Kafka systems, **Spring Boot compatibility** means preserving **message transport and processing behavior**, not merely compiling:

- Producers still send records to the right topic/partition, acknowledged by the broker per `acks`.
- Consumers still join the right group and read/commit offsets according to policy.
- Payloads and headers written by the old version can still be read by the new version.
- Retry, backoff, and dead-letter topics (DLT) still work without dropping messages.
- When an app crashes/rebalances, replay does not duplicate business effects.
- Metrics/traces/logs still reflect operational health accurately.
- Kafka broker, Kafka clients, Spring Kafka, and Spring Boot are within a supported set of versions.

This article belongs to **Spring Kafka Reliability Operations → Upgrades and Compatibility → Spring Boot Compatibility**, using Java 17+, Spring Kafka, Kafka clients, Gradle/Maven, JUnit 5, Embedded Kafka, and Testcontainers. Boot 3.x/Spring Kafka 3.x and Boot 4.x/Spring Kafka 4.x examples must be applied **according to the exact patch versions** your project uses.

> Version tables and migration notes in this article are based on official sources consulted on **2026-11-16**. Support matrices, released patches, and dependency BOMs continue to evolve; before an actual upgrade, always review the current compatibility page and release notes for the exact versions planned for deployment.

### What Should You Be Able to Do After This Lesson?

1. Distinguish compatibility at the source API, runtime binary, Kafka protocol, and message schema levels.
2. Select a well-founded Java–Spring Boot–Spring Kafka–Kafka clients–broker combination.
3. Use the Spring Boot BOM instead of mixing dependency versions arbitrarily.
4. Recognize changes when migrating Boot 2 → 3 → 4: future API, error handler, Jakarta, starters, KRaft, Jackson, and retry.
5. Design a test matrix covering mixed-version producer/consumer, DLT, replay, transactions, and security.
6. Plan canary/rolling deployments/rollbacks based on business outcomes.
7. Investigate common post-upgrade failures such as `NoSuchMethodError`, `ClassNotFoundException`, rising lag, or missing DLT records.

---

## 2. Four Core Compatibility Layers

```text
            Application code
     KafkaTemplate / @KafkaListener
                   |
                   v
            Spring Boot
      auto-configuration / properties
      starters / Actuator / tracing
                   |
                   v
             Spring Kafka
      consumer container / retry / DLT
         transactions / serializers
                   |
                   v
         Apache kafka-clients
        Producer / Consumer / Admin
       wire protocol / authenticator
                   |
                   v
          Apache Kafka brokers
       partitions / ISR / ACL / KRaft

Cross-cutting across layers:
  JDK, Spring Framework, Jackson,
  schema registry, Kafka Streams,
  build tools, security, testing.
```

| Layer | Question That Must Be Answered |
| --- | --- |
| Java / Spring Framework | Do the JDK and APIs support the target Boot release? |
| Spring Boot | Are dependency management and auto-config right? |
| Spring Kafka | Are listener, error handler, retry, and transaction APIs still compatible? |
| Kafka clients | Is the version within the client range supported by Spring Kafka? |
| Kafka broker | Does the cluster/feature level support that client/protocol? |
| Wire schema | Can the new consumer read records/headers created by the old producer? |
| Runtime semantics | Do ack/offset/retry/DLT preserve the desired behavior? |
| Infrastructure | Are TLS/SASL, ACLs, DNS, ports, and topic policies compatible? |

### 2.1. Source Compatibility, Binary Compatibility, and Behavioral Compatibility

**Source compatibility** answers "Does the code still compile?" — for example, an API returning `ListenableFuture` in an older version but changing to `CompletableFuture` in a newer version.

**Binary compatibility** answers "Do bytecode/linkage match at runtime?" — for example, `NoSuchMethodError` when Spring Kafka was compiled against one `kafka-clients` version while runtime loads a different JAR.

**Behavioral compatibility** answers "Are messages still processed and persisted properly?" — for example, the listener still receives records, yet after the upgrade it commits offsets earlier than the business transaction, causing data loss, or type headers no longer map to the right Java class.

A pipeline that fails behavioral compatibility cannot be considered safely upgraded even if the first two layers succeed.

### 2.2. Boot Version Is Not the Kafka Broker Version

Changing `org.springframework.boot` from major 3 to 4 **does not upgrade Kafka brokers**. Brokers have their own release train, protocol feature level, replication, and metadata. When upgrading to a larger client, verify compatibility with the running brokers first; a successful TCP handshake does not prove all API/protocol features are supported.

---

## 3. Reading the Spring Boot / Spring Kafka Matrix

The [Spring for Apache Kafka](https://spring.io/projects/spring-kafka/) page provides the **Kafka Client and Spring Boot Compatibility** table. Common lines in the matrix as of this writing:

| Spring Boot | Generation-Matched Spring Kafka | Notes |
| --- | --- | --- |
| Boot 2.x | Kafka 2.x | Legacy; requires migration when moving to Boot 3 |
| Boot 3.1.x | Kafka 3.0.x | A published line in the matrix |
| Boot 3.2.x | Kafka 3.1.x | A published line in the matrix |
| Boot 3.3.x | Kafka 3.2.x | A published line in the matrix |
| Boot 3.4.x | Kafka 3.3.x | A published line in the matrix |
| Boot 3.5.x | Kafka 3.3.x across many patches | Check the BOM of the **specific Boot patch** |
| Boot 4.0.x | Kafka 4.0.x | Spring Framework 7, Kafka clients 4, Jackson 3 |
| Boot 4.1.x | Kafka 4.1.x | Newer range per compatibility matrix |

This table is only for **orientation**. A dependency coordinates page for a newer Boot 3.5 patch already manages Spring Kafka 3.3.x and Kafka clients 3.9.x. That shows you cannot guess the `kafka-clients` version from the label "Boot 3.5" while ignoring patches and the BOM.

### 3.1. Do Not Misuse the Matrix Scope

The Boot ↔ Spring Kafka ↔ kafka-clients matrix is **different** from the kafka-clients ↔ broker matrix. For mixed new/old major pairs, consult Apache Kafka documentation and validate on a broker cluster equivalent to production.

Some invalid conclusions:

- "Kafka client 4.0 can definitely connect to all Kafka 2.x brokers."
- "Spring Kafka 4.0 can be freely used with Boot 3.5 because both are Spring."
- "A newer version always works fine with old APIs."
- "KafkaTemplate sending successfully means old consumers can read the JSON."
- "Green unit tests mean retry/offset behavior has not changed."

### 3.2. Reference Sources

Check in this order:

1. [Spring Kafka project compatibility](https://spring.io/projects/spring-kafka/).
2. [Spring Boot managed dependencies](https://docs.spring.io/spring-boot/reference/appendix/dependency-versions/coordinates.html).
3. [Spring Kafka change history](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html).
4. [Spring Boot 4 migration guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide) when upgrading major versions.
5. [Apache Kafka documentation](https://kafka.apache.org/documentation/) on client/broker protocol.
6. The **resolved** dependency graph of the production build, not just `build.gradle` in Git.

---

## 4. Dependency Management: Using the Spring Boot BOM as the Primary Source

### 4.1. Why Not Pin Separate Versions for Every Kafka Dependency?

Problematic configuration:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka:4.0.0'
    implementation 'org.apache.kafka:kafka-clients:3.7.0'
    testImplementation 'org.springframework.kafka:spring-kafka-test:3.0.0'
}
```

This is an example of **deliberately mixing** three versions, not a recommended combination. `spring-kafka-test` may depend on helpers/APIs that no longer match runtime; `spring-kafka` may call methods only present in a different `kafka-clients` version.

With Spring Boot, normally:

- Boot manages Spring Kafka and Kafka clients via the BOM.
- Runtime and test Spring Kafka belong to the same generation.
- Version overrides are made only with a clear reason and compatibility testing.
- For multi-module Gradle builds, enforce a unified convention/BOM so each module does not force different Kafka versions.

### 4.2. Gradle with Boot 3.x

Example for Spring Boot 3.x (replace plugin patches with organization-approved releases):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In Boot 3.x, projects typically declare `org.springframework.kafka:spring-kafka` directly. Kafka dependencies do not pin separate versions; Boot's BOM selects compatible versions.

### 4.3. Gradle with Boot 4.x

Boot 4 modularizes many infrastructure parts and provides a dedicated Kafka starter:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-kafka-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-kafka` and `spring-boot-starter-kafka-test` belong to Boot 4's starter organization. Do not copy these coordinates back to Boot 3 without verifying the artifacts. Conversely, when upgrading from 3 to 4, using the new starters keeps auto-configuration and the classpath clearer.

Gradle can also manage BOMs using `platform(...)` instead of `io.spring.dependency-management`. Choose **one consistent strategy** and inspect resolved versions because constraint/force precedence depends on how it is configured.

### 4.4. Maven with Boot 3.x

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

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
```

### 4.5. Maven with Boot 4.x

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.0.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

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
```

If not using the Boot parent, import the BOM via `dependencyManagement`. Do not simultaneously use the Boot BOM and pin arbitrary versions on every dependency.

---

## 5. Reading the Actual Dependency Graph

### 5.1. Gradle

```bash
./gradlew dependencyInsight \
  --dependency spring-kafka \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency kafka-clients \
  --configuration runtimeClasspath

./gradlew dependencies \
  --configuration testRuntimeClasspath
```

In multi-module builds, target `:service-name:dependencyInsight`. `testRuntimeClasspath` may load different JARs than `runtimeClasspath`; tests must reflect the application that will be deployed.

### 5.2. Maven

```bash
mvn dependency:tree \
  -Dincludes=org.springframework.kafka,org.apache.kafka

mvn help:effective-pom
```

Also inspect Kafka Streams, Avro/Schema Registry clients, Jackson 2/3, Micrometer, Spring Retry, and legacy modules. A classpath with multiple versions/packagings can compile yet fail at runtime.

### 5.3. Pre-Upgrade Inventory

```text
Service:                 orders-consumer
Current Java:            [version]
Target Java:             [version]
Current Spring Boot:     [version + patch]
Target Spring Boot:      [version + patch]
Spring Kafka:            [resolved version]
kafka-clients:           [resolved version]
Kafka Streams:           [version if used]
Jackson:                 [major/version]
Spring Retry:            [if referenced]
Broker versions:         [every broker, feature level]
Topic schema versions:   [consumer/producer contract]
Auth:                    [TLS/SASL/ACL]
Producer acks:           [policy]
Consumer ack mode:       [policy]
DLT topology:            [topic/partitions/retention]
```

Do not use a runtime log version of a single dependency to infer all transitive versions. The inventory must combine dependency reports, broker information, and deployment configs.

---

## 6. Dependency Overrides: Necessary Cases and Risks

### 6.1. When Is an Override Justified?

An override may be reasonable when a security patch, Kafka client bug fix, or special broker compatibility fix is needed before the Boot BOM updates. However, overrides must stay within the **version range supported by Spring Kafka** and be tested against real Kafka brokers.

### 6.2. Maven Properties

In Spring Boot projects managing dependencies with override support, Spring Kafka documents these properties:

```xml
<properties>
    <!-- Syntax illustration only. -->
    <kafka.version>3.9.1</kafka.version>
    <spring-kafka.version>3.3.10</spring-kafka.version>
</properties>
```

The two numbers above **are not a pair guaranteed safe** for every Boot patch. Check Spring Kafka release notes, broker compatibility, and the dependency report after overriding.

### 6.3. Gradle

With the `io.spring.dependency-management` plugin:

```groovy
ext['kafka.version'] = '3.9.1'
ext['spring-kafka.version'] = '3.3.10'
```

With native Gradle platforms/version catalogs, overrides work differently and `ext` is not automatically guaranteed to take effect. Always measure the resolved version with `dependencyInsight`.

### 6.4. Controlled Override Process

1. Document the specific issue/CVE/feature requiring the override.
2. Check the client–Spring Kafka–broker matrix.
3. Align `spring-kafka-test` with runtime when needed.
4. Check Kafka Streams/Connect if in the same application.
5. Run producer/consumer, serializer, retry/DLT, and offset/replay integration tests.
6. Run a canary against broker feature levels matching production.
7. Record a review/removal date once the Boot BOM catches up.

Do not use `latest.release` or broad `force` in release builds: builds become non-reproducible and can accidentally jump major versions.

---

## 7. Spring Boot Kafka Auto-Configuration

### 7.1. What Does Boot Auto-Create?

When dependency/bean conditions match:

```text
  spring.kafka.* properties
            |
            v
       KafkaProperties
            |
     +------+------+-----------------+
     |             |                 |
     v             v                 v
ProducerFactory ConsumerFactory    KafkaAdmin
     |             |                 |
     v             v                 v
KafkaTemplate  Listener factory    NewTopic beans
                   |
                   v
               @KafkaListener
```

If the application defines its own bean of the same type/name, Boot may **back off** and skip creating the default bean. After an upgrade, this is a common reason `DefaultErrorHandler` is not applied: the handler is declared, yet a custom listener factory does not actually wire it in.

### 7.2. Illustrative Boot 3.x Configuration

```yaml
spring:
  kafka:
    bootstrap-servers: KAFKA_BOOTSTRAP_HOSTS
    client-id: orders-service
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
    consumer:
      group-id: orders-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      auto-offset-reset: earliest
      enable-auto-commit: false
      properties:
        max.poll.records: 100
    listener:
      concurrency: 3
      ack-mode: record
```

`KAFKA_BOOTSTRAP_HOSTS` here is an environment-supplied configuration value; replace it with the URL/service discovery of the authorized cluster. For production, do not hardcode `localhost:9092` everywhere.

Some options belong to the Kafka client (`delivery.timeout.ms`, `max.poll.records`, `acks`), not redefined by Spring Boot. After upgrading the Kafka client, check defaults and semantics.

### 7.3. Config Under `properties`

```yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
    producer:
      properties:
        max.in.flight.requests.per.connection: 5
    consumer:
      properties:
        isolation.level: read_committed
```

These settings can be overridden in role-specific properties or custom factories. Verify effective config from startup logs with secret masking, rather than reading only YAML.

### 7.4. `KafkaAdmin` and Topic Creation

Boot/Spring Kafka can use `NewTopic` beans to request topic creation if authorized. Many production clusters disable auto-create and do not grant CREATE ACLs to applications. If an upgrade causes startup failure in the admin client, do not blindly grant broad permissions; check `KafkaAdmin`, topic manifests, and appropriate ACLs.

---

## 8. Producer API Changes in Spring Kafka 3

### 8.1. From `ListenableFuture` to `CompletableFuture`

Spring Kafka 2.x code may use:

```java
// Legacy form:
ListenableFuture<SendResult<String, String>> result =
    kafkaTemplate.send(topic, key, value);

result.addCallback(
    success -> log.info("Sent"),
    failure -> log.error("Send failed", failure));
```

Spring Kafka 3.x uses `CompletableFuture` for standard send overloads:

```java
package example.kafka;

import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> template;

    public OrderPublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String eventId, String value) {
        return template.send(
            "orders.events", eventId, value);
    }
}
```

### 8.2. New Callback Style

```java
publisher.publish(
    "evt-101", "{\"state\":\"CREATED\"}")
    .whenComplete((result, error) -> {
        if (error != null) {
            // Handle send failure, bounded retry,
            // or fall back to outbox.
        } else {
            var metadata = result.getRecordMetadata();
            // metadata.topic(), partition(), offset()
        }
    });
```

Do not default to `send(...).get()` without a timeout for all production requests. Integration tests may await `get(10, TimeUnit.SECONDS)` to assert bounded broker acknowledgment.

### 8.3. Producer Ack Is Not Consumer Success

`acks=all` on a topic with replication factor 1 does not prove data survives broker failover. And producer future success does not prove `@KafkaListener` processed the business effect. After an upgrade, test both downstream consumers and DB outputs.

---

## 9. Listener and Consumer Group Compatibility

### 9.1. Minimal Listener

```java
package example.kafka;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderProjectionService service;

    public OrderListener(OrderProjectionService service) {
        this.service = service;
    }

    @KafkaListener(
        id = "orders-listener",
        topics = "orders.events",
        groupId = "orders-projection"
    )
    public void handle(
            ConsumerRecord<String, String> record) {

        service.applyIdempotently(
            record.key(), record.value());
    }
}
```

`OrderProjectionService` is an application-provided domain service. In production, it must protect unique business event IDs so reprocessing the same message does not cause unintended side effects.

### 9.2. `group.id` Is the Processing Progress Identifier

During a rolling upgrade, do not arbitrarily rename `group.id` from `orders-projection` to `orders-projection-v2` just so the app "reads cleanly from scratch."

- A new group has no old committed offsets.
- `auto.offset.reset=earliest` can replay all data still within retention.
- `auto.offset.reset=latest` can skip existing records.
- Multiple groups listening to a topic receive independent copies.

If replay is desired, use an explicit workflow and business idempotency. If only upgrading the framework, preserve the group ID per operational contract unless there is a migration plan.

### 9.3. Listener Concurrency

```yaml
spring:
  kafka:
    listener:
      concurrency: 4
```

If the topic has only 2 partitions, the same consumer group does not have four partitions to distribute across four members. Check partition counts, assignments, and rebalances when deploying more instances. Upgrading Boot does not automatically increase throughput simply by raising concurrency.

### 9.4. Offset Commit vs. Business Commit

```text
Consume E
    |
    v
DB transaction commits E
    |
    X app crashes before Kafka offset commit
    |
    v
E is replayed after restart
```

At-least-once delivery means consumers must tolerate replay. Newer Spring Boot/Kafka versions do not guarantee exactly-once for databases outside Kafka transactions.

### 9.5. Ack Mode

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
```

`RECORD`, `BATCH`, `MANUAL`, and `MANUAL_IMMEDIATE` differ in when offsets are committed. If a listener uses manual `Acknowledgment`, configure the corresponding manual ack mode. Changing listener factories across versions can change behavior even when listener code is unchanged.

---

## 10. Error Handler Migration: Boot 2/Spring Kafka 2 → Boot 3/Spring Kafka 3

### 10.1. Recognizing Legacy APIs

Spring Kafka 2.x code may contain:

```text
SeekToCurrentErrorHandler
SeekToCurrentBatchErrorHandler
ErrorHandler / BatchErrorHandler
Legacy listener container error handler overrides
```

The Spring Kafka 3.x generation centers on `CommonErrorHandler` and `DefaultErrorHandler`. Do not hold back JARs on an old version just to avoid migrating error handling.

### 10.2. `DefaultErrorHandler` with DLT

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler commonErrorHandler(
        KafkaTemplate<String, String> template) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(template);

    // Initial attempt + 2 retries.
    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(500L, 2L));
}
```

Ensure `CommonErrorHandler` is attached to the **running factory**. If the application declares a custom `ConcurrentKafkaListenerContainerFactory`, check its custom wiring rather than assuming Boot always attaches every bean automatically.

### 10.3. What Must Be Asserted

With poison message B:

```text
Topic input:
  A valid
  B POISON
  C valid

Expected:
  A -> processed once logically
  B -> attempts bounded -> DLT
  C -> processed
```

Do not just assert that the listener throws an exception. Measure:

- Number of delivery attempts per configuration.
- DLT topic, partition, key, value, and original-topic/error headers.
- What a recovery publisher failure does to the source offset.
- Ordering of C after B, depending on blocking/non-blocking retry.
- No duplicated DB side effects.

### 10.4. `@RetryableTopic` Is Not Like Blocking Retry

Non-blocking retries forward records to retry topics, freeing the partition from long waits, yet can change processing order among records with the same key. When upgrading, check retry topic names, partitions, consumer groups, concurrency, and backoff.

If using both `DefaultErrorHandler` and `@RetryableTopic`, understand precedence and per-container error handler configuration to avoid two retry layers accidentally adding attempts together.

---

## 11. Spring Boot 4 and Spring Kafka 4: Specific Migration Points

### 11.1. Spring Framework 7 and Modular Starters

Boot 4 moves to Spring Framework 7 and splits many auto-configuration modules. Dependencies:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-kafka'
testImplementation 'org.springframework.boot:spring-boot-starter-kafka-test'
```

should be evaluated when upgrading from Boot 3. Imports from internal `org.springframework.boot.autoconfigure.*` packages may relocate. If a project builds custom starters, review the Boot 4 migration guide instead of only bumping the plugin version.

### 11.2. Kafka Client 4 and KRaft-Only Embedded Broker

Spring Kafka 4 uses Kafka clients generation 4, and embedded test infrastructure is KRaft-only. Legacy APIs:

```text
EmbeddedKafkaZKBroker
EmbeddedKafkaRule
ZooKeeper properties in @EmbeddedKafka
@EmbeddedKafka(kraft=false)
```

are no longer applicable in Spring Kafka 4. Migrate the test harness per Spring Kafka 4 documentation and verify embedded broker startup, partitions, internal transaction topics, and listener assignment.

### 11.3. Kafka Client Interfaces

If the application implements `Producer`, `Consumer`, constructs `ConsumerRecords` directly, or uses older Kafka Streams APIs, upgrading to Kafka client 4 may require changing method signatures/constructors. A `MockConsumer`/`MockProducer` written years ago must compile against the target version and run new integration tests.

### 11.4. Jackson 3 Is Preferred in Boot 4

Jackson 3 moves many APIs from `com.fasterxml.jackson.*` to `tools.jackson.*`. Spring Kafka 4 provides Jackson 3 counterparts for serializers/deserializers/converters.

| Common Class in Jackson 2 | Migration Path in Spring Kafka 4 |
| --- | --- |
| `JsonSerializer` | `JacksonJsonSerializer` |
| `JsonDeserializer` | `JacksonJsonDeserializer` |
| `JsonSerde` | `JacksonJsonSerde` |
| `JsonMessageConverter` family | `JacksonJsonMessageConverter` family |
| `DefaultJackson2JavaTypeMapper` | `DefaultJacksonJavaTypeMapper` |

In Spring Kafka 4, Jackson 2 support may remain deprecated for a transition period, but should not be used as a long-term target. **Do not swap serializer classes without running schema/wire contract tests**.

### 11.5. Cross-Generation JSON Configuration

Spring Kafka 3/Jackson 2 consumer example:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: example.events.OrderEvent
        spring.json.trusted.packages: example.events
```

When switching to the Jackson 3 counterpart in Spring Kafka 4:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JacksonJsonDeserializer
      properties:
        spring.json.value.default.type: example.events.OrderEvent
        spring.json.trusted.packages: example.events
```

The new configuration requires compatible dependencies and Jackson major version. Check headers from old producers (type info), schema compatibility, and type mappings; never set `trusted.packages=*` just to bypass security errors.

### 11.6. Retry API in Spring Kafka 4

Spring Kafka 4 drops the Spring Retry dependency from its core retry mechanism and moves to Spring Framework 7's new mechanism. Migration example:

```java
// Before - Spring Kafka 3:
@RetryableTopic(
    backoff = @Backoff(
        delay = 2000,
        maxDelay = 10000,
        multiplier = 2))
```

```java
// After - Spring Kafka 4:
@RetryableTopic(
    backOff = @BackOff(
        delayString = "2s",
        maxDelayString = "10s",
        multiplier = 2))
```

Notice the capital `backOff` and the new `@BackOff` annotation; imports/types must follow the release. Custom exception classifiers, backoff generators, and retrying deserializers also need API change reviews.

### 11.7. Separate Kafka Streams Migration

If the project also uses `@EnableKafkaStreams`, Kafka Streams Serdes, processors, state stores, or Spring Kafka Streams utilities, do not test only `KafkaTemplate` and `@KafkaListener`. Spring Kafka 4/Kafka clients 4 also include Kafka Streams API changes; review state-store compatibility, topology version, and application ID before rolling deployment.

---

## 12. JSON Schema, Headers, and Compatibility Between Two Deployed Versions

### 12.1. Rolling Deployments Always Have a Mixed Phase

```text
producer old (Boot 3)
         |
         v
      Topic A
         |
   +-----+------+
   |            |
   v            v
consumer old   consumer new
(Boot 3)       (Boot 4)
```

During the rolling phase, new consumers must still read records already persisted by old producers. Once producers move to the new version, old consumers not yet stopped may also read new messages. Compatibility therefore must be tested **bidirectionally** if there is a mixed-version window.

### 12.2. Schema Compatibility

- **Backward:** new consumers can read old data.
- **Forward:** old consumers can read new data.
- **Full:** both directions comply per contract.
- **Breaking:** a change breaks one side's assumptions, such as changing a required field type.

Example JSON payload:

```json
{
  "eventId": "evt-101",
  "orderId": "O-100",
  "state": "CREATED",
  "schemaVersion": 1
}
```

If `currency` is added, do old consumers accept unknown fields? If `orderId` is removed, do new consumers have a valid default? If changing a date to a timestamp, how must schema/version change?

### 12.3. Type Headers Can Break Even When the JSON Body Is Unchanged

Spring Kafka serializers can attach a header containing a Java type name:

```text
Producer old:
  type header = com.legacy.events.OrderCreated

Consumer new:
  class = com.newapp.events.OrderCreated

=> deserialization may fail
```

Prefer stable logical type aliases/type mappings or a schema registry when appropriate, rather than relying long-term on fully-qualified Java class names as a wire contract.

### 12.4. Testing Contracts by Bytes and Headers

A contract test should:

1. Take payload + headers generated by the old producer.
2. Verify the new consumer deserializes properly.
3. Take payload + headers generated by the new producer.
4. Verify the old consumer deserializes if rolling rollout requires it.
5. Test missing optional fields, unknown fields, nulls, new enums, and date/time formats.
6. Test invalid JSON and the DLT serializer for raw bytes.

Do not test only Java objects in unit tests; serialization compatibility lives in the wire representation.

---

## 13. Deserialization Failures Happen Before `@KafkaListener`

Flow:

```text
Kafka bytes
     |
     v
Deserializer
     |
     +-- Invalid JSON / unknown type
     |          |
     |          v
     |      error handling
     |
     v
ConsumerRecord<K, V>
     |
     v
@KafkaListener
```

If the value deserializer throws an exception before constructing an object, the business listener is never called. A test where the listener throws `IllegalArgumentException` does not simulate a deserialization failure.

### 13.1. `ErrorHandlingDeserializer`

Illustrative configuration for Spring Kafka 3.x:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: example.events
```

When using Spring Kafka 4/Jackson 3, update the delegate class accordingly. Verify that the DLT recoverer can send raw bytes and error headers using a suitable serializer.

### 13.2. Required Tests

- Send valid JSON → business listener processes it.
- Send malformed JSON → error handler receives error details.
- Malformed payload goes to DLT or is handled per policy.
- DLT preserves original topic/partition/offset and exception metadata needed for auditing.
- Partition does not stall indefinitely.
- Never use wildcard `trusted.packages=*` without a threat model and controls.

---

## 14. Offsets, Acknowledgment, and Replay After Upgrade

### 14.1. Kafka Offset Is Group Progress, Not a Business ID

```text
topic orders.events / partition 0
 offset 10 : E-A
 offset 11 : E-B
 offset 12 : E-C

consumer group orders-projection
 committed offset = 12
 -> next read starts from offset 12
```

A committed offset does not mean a record was processed exactly-once in the database. A consumer can crash after a DB commit but before the offset commit.

### 14.2. Preserving Ack Semantics

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
```

If the app uses manual ack:

```java
@KafkaListener(
    topics = "orders.events",
    groupId = "orders-projection")
public void onRecord(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    orderService.persistIdempotently(
        record.key(), record.value());

    acknowledgment.acknowledge();
}
```

Import `org.springframework.kafka.support.Acknowledgment` and configure the matching manual ack mode. Acking after a business commit still does not automatically make a DB transaction + Kafka offset commit a single distributed atomic transaction.

### 14.3. Replay Requires Idempotency

Create table:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

PostgreSQL example:

```sql
INSERT INTO processed_event (event_id, order_id)
VALUES (?, ?)
ON CONFLICT (event_id) DO NOTHING;
```

If the same `eventId` is replayed, a duplicate insert does not increase logical row count. This is an example; if the consumer also calls a payment/email API, an idempotency key is needed on that downstream system too, not just a DB unique constraint.

### 14.4. Consumer Group Protocol

Kafka 4 supports a new consumer rebalance protocol under suitable conditions. When upgrading brokers and clients together, check group membership, assignments, rebalance frequency, `max.poll.interval.ms`, and static membership. Do not assume upgrading the client alone safely enables the new protocol against an older cluster.

---

## 15. Kafka Transactions: Key Boundaries During Migration

### 15.1. Kafka-to-Kafka

In a topology that consumes one topic and publishes to another with Kafka transactions configured properly, published records and consumed offsets can be coordinated in the same Kafka transaction.

Consumers reading transactional output can use:

```yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
```

### 15.2. Kafka Transactions Do Not Wrap Every System

```text
Consumer E
   |
   v
PostgreSQL COMMIT
   |
   X  Kafka transaction fails
   |
   v
E delivered again
```

Kafka transactions do not automatically roll back PostgreSQL, HTTP, email, or payment systems. When Boot/Spring Kafka major versions change, legacy transaction coordination APIs such as chained transaction managers must be reviewed for deprecation/removal. Build idempotency/outbox/reconciliation according to business requirements.

### 15.3. Transaction ID Prefix

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-
```

Check the strategy for generating transactional IDs per app instance and concurrency so producers do not fence one another during a rolling upgrade. Using the exact same fixed transactional ID across two replicas can cause one producer to be fenced.

### 15.4. Transaction Integration Tests

- Publish a committed record; `read_committed` consumer sees it.
- Abort a Kafka transaction; `read_committed` consumer does not see the aborted record.
- Crash after DB commit before offset commit; replay does not duplicate DB state.
- Rolling upgrade of two replicas does not cause unexpected transaction fencing.
- Broker/topic `transaction.state.log.*` is configured suitably for the topology.

Single-broker Embedded Kafka usually needs appropriate replication/ISR settings for internal transaction topics; such tests do not equal the durability of a multi-broker production cluster.

---

## 16. TLS/SASL/ACL: Compatibility at the Security Layer

### 16.1. Configuration Pattern

```yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: INJECTED_JAAS_SECRET
    ssl:
      trust-store-location: file:/etc/kafka/client.truststore.p12
      trust-store-password: INJECTED_TRUSTSTORE_PASSWORD
```

Do not commit secrets or JAAS credentials to the repository. Inject them via the deployment environment's secret manager/configuration.

After an upgrade, verify:

- Does the new JDK have truststore types/TLS ciphers compatible with the broker?
- Does the Kafka client receive the right JAAS/SASL configs?
- Does `KafkaAdmin` have the same credentials?
- Does the producer have WRITE ACL, consumer have READ ACL, and group have permissions?
- Can DLT/retry topics be created/written/read per policy?
- Are transactional ID ACLs right?

### 16.2. Auth Failures Are Not Infinite Retry Errors

`AuthenticationException`, `AuthorizationException`, and SSL handshake errors must be classified. Increasing retries/backoff does not fix wrong credentials and can cause an alert storm. If a production consumer stops processing after an upgrade, check auth/protocol before touching offsets or groups.

---

## 17. Observability and Micrometer After Upgrading Boot

Boot 3 emphasizes Micrometer Observation/Tracing; Boot 4 continues advancing observability infrastructure. After a major upgrade, a missing meter or span does not necessarily mean traffic is zero; meter names, tags, enable flags, or auto-config may have changed.

### 17.1. Signals You Should Have

| Signal | Meaning |
| --- | --- |
| Consumer lag by group/partition | Backlog and SLA |
| Listener p95/p99 | Processing latency |
| Producer send errors/latency | Delivery health |
| Retry attempts / DLT volume | Recovery path |
| Rebalance count/frequency | Group stability |
| Offset commit failures | Replay risk |
| Deserialization errors | Wire contract problems |
| DB duplicate key or idempotency conflict | Replay side effects |
| SASL/TLS failures | Security compatibility |
| Business completion delay | User impact |

Never use `eventId` or `customerId` as a metric tag per record due to high cardinality. Structured logs may contain sanitized identifiers depending on access policies.

### 17.2. Baseline and Canary

Before upgrading, capture a baseline over at least one meaningful traffic cycle. During canary, compare:

- Messages consumed/second, producer errors, lag.
- Retry/DLT rate and age of unprocessed records.
- Consumer rebalance frequency.
- Business DB outputs, duplicate/reconciliation findings.
- JVM CPU/heap/GC and latency.
- Do traces and dashboards still operate properly?

Do not conclude a 5-minute canary is sufficient if a critical workload runs once a day.

---

## 18. Compatibility Testing with Embedded Kafka

### 18.1. Synchronizing Runtime and Test Dependencies

If production runs Spring Kafka 3.x while `spring-kafka-test` is pinned to 2.x or 4.x, the test harness can drift out of sync. Always let the BOM manage matching test dependencies.

### 18.2. Testing Producer–Consumer with a Real Broker

Spring Kafka 3.x/Boot 3.x example:

```java
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@EmbeddedKafka(
    topics = {"orders.compat.it"},
    partitions = 1,
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaCompatibilityIT {

    @Autowired
    KafkaTemplate<String, String> template;

    @Autowired
    EmbeddedKafkaBroker broker;

    @Test
    void producerAndConsumerAreCompatible() throws Exception {
        String eventId = "e-" + UUID.randomUUID();

        Map<String, Object> props =
            KafkaTestUtils.consumerProps(
                "compat-" + UUID.randomUUID(), "false", broker);

        try (Consumer<String, String> consumer =
                new DefaultKafkaConsumerFactory<>(
                    props,
                    new StringDeserializer(),
                    new StringDeserializer()).createConsumer()) {

            broker.consumeFromAnEmbeddedTopic(
                consumer, "orders.compat.it");

            var sent = template.send(
                "orders.compat.it", eventId, "CREATED")
                .get(10, TimeUnit.SECONDS);

            assertEquals(
                "orders.compat.it",
                sent.getRecordMetadata().topic());

            var record = KafkaTestUtils.getSingleRecord(
                consumer,
                "orders.compat.it",
                Duration.ofSeconds(10));

            assertEquals(eventId, record.key());
            assertEquals("CREATED", record.value());
        }
    }
}
```

This example checks the Kafka client producer/consumer. It does not test the application's `@KafkaListener` or business database. Add real listener tests, wait for partition assignment with `ContainerTestUtils.waitForAssignment`, and assert business results using Awaitility.

### 18.3. Spring Kafka 4 Embedded Kafka

The 4.x embedded framework is KRaft-only: remove ZooKeeper props/classes such as `EmbeddedKafkaZKBroker`, `EmbeddedKafkaRule`, and `kraft=false`. Re-run transactional tests, bootstrap listeners, and topic/partition setups. That `@EmbeddedKafka` still compiles does not mean old assumptions about broker lifecycle remain valid.

### 18.4. Avoiding Flaky Tests

- Do not hardcode `localhost:9092`; use bootstrap servers provided by the test broker.
- Create topics/partitions explicitly.
- Create a dedicated consumer group per test or ensure offsets are reset.
- Wait for listener assignment before sending if the test depends on subscription.
- Use a blocking queue/Awaitility with timeouts, never fixed `Thread.sleep`.
- Do not depend on JUnit test-method execution order.
- Separate DLT/source topics and verify partition counts properly.
- Test on pinned Kafka images/versions and capture log evidence on failure.

---

## 19. Testcontainers for Real Broker and Database Testing

### 19.1. Why Are Testcontainers Needed?

Embedded Kafka makes tests fast. Testcontainers adds process isolation and fits when you need Kafka + PostgreSQL, networking, serialization/ACL scenarios, or an exact broker image.

Testcontainers 1.x example:

```java
@Testcontainers
@SpringBootTest
class KafkaPostgresIT {

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse(
                "confluentinc/cp-kafka:7.6.1"));

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers);
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl);
        registry.add(
            "spring.datasource.username",
            postgres::getUsername);
        registry.add(
            "spring.datasource.password",
            postgres::getPassword);
    }
}
```

Imports/Testcontainers module versions must align with the build; this example illustrates only test infrastructure, omitting listeners and topics. When moving to Testcontainers 2.x, some Kafka container modules/packages may change: consult the corresponding versioned docs.

### 19.2. `@ServiceConnection`

Spring Boot can create connection details from Testcontainers via `@ServiceConnection` when supported by the starter/version. When using this, avoid declaring duplicate `@DynamicPropertySource` entries for the same Kafka bootstrap servers without reason, as it can complicate diagnosing the effective endpoint.

### 19.3. Testing DB Idempotency

Use a `processed_event` table with primary key `event_id`. Send the same event ID twice or deliberately replay after a crash before offset commit. Assert:

- The consumer can receive the record again.
- Only one logical business effect exists.
- Subsequent valid records are not skipped.
- Offsets continue advancing when the business operation succeeds.

A single Testcontainers Kafka broker does not fully simulate cluster replication; testing leader failover/ISR requires a multi-broker topology or staging cluster.

---

## 20. Upgrade Regression Test Matrix

| ID | Scenario | Environment | Pass Criteria |
| --- | --- | --- | --- |
| C01 | Producer sends string | Embedded | Broker ack and record have right key/value |
| C02 | App listener receives record | Embedded | Business output persisted |
| C03 | New consumer reads old JSON | Contract/Embedded | Object and headers match |
| C04 | Old consumer reads new JSON | Contract/Embedded | Does not break mixed-version rollout |
| C05 | Deserialization error | Embedded | Failed record routed to DLT |
| C06 | Listener throws transient exception | Embedded | Bounded retries, proper recovery |
| C07 | Poison message | Embedded | DLT has record, partition advances |
| C08 | Kafka offset replay | Kafka + DB container | Output not duplicated |
| C09 | Kafka transaction abort | Transaction-enabled broker | `read_committed` does not see aborted record |
| C10 | Consumer rebalance | Container/multi-instance | No business records dropped |
| C11 | TLS/SASL authentication | Staging | No ACL/security loss |
| C12 | Target broker/client compatibility | Versioned cluster | No protocol errors |
| C13 | Per-key topic ordering | Multi-partition | Events with same key preserve partition order |
| C14 | DLT publisher failure | Container fault | Record not silently lost |
| C15 | Rolling mixed versions | Preproduction | Old/new apps share wire contract |
| C16 | Observability upgrade | Staging/canary | Metrics/traces exist, alerts accurate |

Not every test needs to run on every local commit. Before release, however, Kafka + DB, retry/DLT, schema, and broker security tests must have evidence.

---

## 21. Rolling Deployment Without Disrupting the Message Stream

### 21.1. Practical Steps

1. **Inventory:** record JDK, Boot, Spring Kafka, `kafka-clients`, broker, topics, groups, and schemas.
2. **Compatibility:** verify the matrix for target versions.
3. **Fix build:** switch BOM/starters and remove unnecessary version overrides.
4. **Migrate APIs:** futures, handlers, retry annotations, Jackson, Embedded Kafka.
5. **Test contract:** old producer → new consumer and vice versa if mixed rollout applies.
6. **Test reliability:** retry/DLT, offset/replay, DB idempotency, transactions.
7. **Stage:** connect to brokers with production-equivalent security/feature levels.
8. **Canary:** deploy a small group of instances and watch lag/DLT/duplicates.
9. **Rolling:** upgrade sequentially while protecting consumer groups and transactional IDs.
10. **Reconcile:** verify outputs/offsets/DLT before declaring completion.

### 21.2. Consumer-First or Producer-First?

If the new consumer can read both old and new payloads, consumer-first usually lowers risk: upgrade consumers before letting producers emit new schemas. Still verify the reverse direction during the rolling phase; some protocol/serializer changes do not support coexistence and require dual-write/dual-read or versioned topics.

### 21.3. Separate Application and Broker Upgrades

There is no need to force Boot application upgrades on the exact same day as broker cluster upgrades. Changing broker protocol, schemas, Spring Kafka, and JDK simultaneously makes root-cause analysis far harder on failure. Prefer phased changes with independent rollbacks and evidence.

### 21.4. Rollback Must Account for Data

Rolling back a JAR does not automatically undo:

- Kafka records already published in the new format.
- Consumer offsets already committed.
- DLT records already written.
- DB rows already updated.
- Broker feature/protocol levels already raised.

If old consumers cannot read the new schema, a "code rollback" can make the system worse. Maintain a compatibility window and remediation plan instead of treating rollback as trivial.

---

## 22. Post-Upgrade Error Diagnosis Runbook

### 22.1. `NoClassDefFoundError` or `NoSuchMethodError`

Likely causes: binary dependency mismatch, removed API classes, Jackson 2/3 conflicts.

Investigation:

```text
Stacktrace class/method owner
  -> runtimeClasspath
  -> dependencyInsight/dependency:tree
  -> Boot BOM + transitive versions
  -> Spring Kafka change history
  -> clean rebuild / container image
```

Do not fix by randomly adding a new JAR version without checking the matrix.

### 22.2. `NoSuchBeanDefinitionException` or Listener Fails to Start

Likely causes: missing Kafka starter/module, Boot auto-config backing off, custom bean factory missing configuration, relocated package imports in Boot 4.

Inspect `ConditionEvaluationReport`, `KafkaProperties`, bean types, and listener registry. Ensure the factory contains the proper error handler/serializer/security configs.

### 22.3. Producer Sends Successfully but Consumer Does Not Process

- Did the consumer group ID change?
- What are the committed offsets and `auto.offset.reset`?
- Has the listener been assigned partitions?
- Did the deserializer throw before the listener method?
- Are topic name/ACL/SASL/TLS correct?
- Does the JSON type header still map to the new class?
- What are lag and rebalances doing?

Producer ack does not mean consumer success.

### 22.4. Poison Record Does Not Reach DLT

Likely causes:

- Error handler not attached to the factory.
- DLT topic does not exist or has mismatched partitions.
- Missing WRITE ACL.
- DLT serializer does not support raw bytes.
- Retry policy never exhausts.
- `@RetryableTopic` API/bean topology changed.
- Recoverer throws an exception and offset handling was not checked.

Use an integration test that deliberately throws an error with a dedicated event ID and assert the DLT record/headers.

### 22.5. Consumer Lag Increases After Upgrade

Check poll interval, `max.poll.records`, listener latency, DB pool, CPU/GC, concurrency vs. partitions, group rebalance protocol, and broker/network. Do not raise concurrency indefinitely because of ordering, DB contention, and rate limits.

### 22.6. Duplicate Business Effects

If records are replayed, check business event IDs, DB unique constraints, offset commit timing, recovery policy, and transaction ordering. Do not solve this by changing the group ID or setting `auto-offset-reset=latest`; that can drop unprocessed records.

### 22.7. TLS/ACL Regression

If the producer works yet the DLT publisher fails, DLT-specific ACLs may be missing. If the listener cannot join the group, GROUP READ permissions may be missing. If `KafkaAdmin` fails at startup, topic creation permissions may be denied. Grant least-privilege permissions rather than wildcard ACLs for the application.

---

## 23. Common Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Changing only the `spring-boot` version | Starters/APIs not migrated | Follow the guide and full compatibility plan |
| Mixing Spring Kafka/kafka-clients/test versions | Runtime linkage error | BOM + dependency report |
| Using latest Kafka client with an old broker | Protocol/feature mismatch | Client/broker matrix |
| Keeping `ListenableFuture` code on Kafka 3 | Compile/source incompatibility | `CompletableFuture` |
| Keeping legacy `SeekToCurrentErrorHandler` | Error handler API mismatch | `DefaultErrorHandler` + tests |
| Using old `@Backoff` when upgrading to Kafka 4 | Incompatible retry config | `@BackOff` migration |
| Keeping `EmbeddedKafkaZKBroker` | Tests fail on Kafka 4 | KRaft-only test harness |
| Changing JSON class package without updating type mapping | Deserialization fails | Logical aliases/schema contract |
| Enabling `trusted.packages=*` to dodge errors | Deserialization risk | Whitelist trusted packages |
| Asserting only the producer future | Consumer/DLT can fail | End-to-end business assertions |
| Changing consumer group ID per release | Replay/lost offset history | Keep group or migrate explicitly |
| Treating Kafka EOS as covering PostgreSQL | Duplicate DB side effects | Idempotent projection/outbox |
| Rolling back code without checking schemas | Old consumer cannot read new messages | Compatibility window |
| Ignoring DLT after upgrade | Poison records lose recoverability | DLT metrics/tests |
| Skipping Testcontainers suite in CI | Loss of real-broker evidence | Enforce test policy |
| Increasing retries on credential errors | Retry storm | Classify auth errors and fix ACLs |
| Upgrading broker and app simultaneously | Hard to roll back/diagnose | Upgrade in phases |

---

## 24. Hands-On Exercises

### Exercise 1 — Check Dependency Compatibility

Given build:

```text
Spring Boot:       3.5.x
Spring Kafka:      3.3.x
kafka-clients:     4.0.x (override)
spring-kafka-test: 3.1.x
Broker:            3.x
```

Identify the risk points, consult the official matrix, and write `dependencyInsight`/`dependency:tree` commands to prove resolved versions. Do not assume client 4 definitely runs against broker 3.

### Exercise 2 — Migrating Producer Callbacks

Convert a Spring Kafka 2.x producer using `ListenableFuture.addCallback` to Spring Kafka 3.x using `CompletableFuture.whenComplete`. Test both broker ack and send failure with a bounded timeout.

### Exercise 3 — Listener Compatibility

Create a three-partition topic, a producer keyed by `orderId`, and a listener with concurrency 2. After upgrading, assert events sharing an order key preserve order within their partition. Do not demand topic-wide ordering.

### Exercise 4 — Retry/DLT

Create a listener that throws on payload `POISON`. Configure `DefaultErrorHandler` with 2 retries and a DLT recoverer. Assert attempt counts, original topic/offset metadata, and that subsequent valid records are processed.

### Exercise 5 — JSON Boot 3 → 4

Prepare JSON + type headers produced by Jackson 2/Spring Kafka 3. Configure Spring Kafka 4/Jackson 3 to read them. Test new producer → old consumer, added enums, and unknown fields if rolling deployment requires it.

### Exercise 6 — Embedded Kafka KRaft

Take an old `EmbeddedKafkaZKBroker` test. Migrate it to Spring Kafka 4's KRaft-enabled test. Remove ZooKeeper-only options and test producer/consumer, DLT, and appropriate transaction support.

### Exercise 7 — Kafka + PostgreSQL Testcontainers

Create an event projection table with unique `event_id`. Send one event twice and simulate a restart before offset commit. Assert one logical record exists.

### Exercise 8 — Offsets and Group ID

Create two consumer groups with `earliest` and `latest` on a topic that already contains records. Observe where reading starts. Explain why changing the group ID on release can trigger replay or skip messages.

### Exercise 9 — Transaction Scope

Build Kafka-to-Kafka processing with a Kafka transaction; test `read_committed` on committed/aborted outputs. Add a JDBC side effect and describe the window where the DB commits while the Kafka transaction fails.

### Exercise 10 — Migration Plan

Document source and target versions, test matrix, deploy order, rollback triggers, and post-rollback DLT/DB reconciliation. Choose consumer-first or dual-read/dual-write with concrete rationale.

### Exercise 11 — Runtime Error

A Boot 4 application throws `ClassNotFoundException` when a JSON type header contains `com.legacy.OrderEvent`. Distinguish a missing JAR from a wire type mapping error and design a schema contract test.

### Exercise 12 — Observability

Design a dashboard for consumer lag, listener p95, retries, DLT volume, producer failures, rebalances, duplicates, and business SLA. Point out which metrics may rename when Boot/Micrometer upgrades and how to verify via Actuator.

---

## 25. Production Upgrade Checklist

### Platform and Build Layer

- [ ] JDK and Spring Framework meet target Boot requirements.
- [ ] Spring Kafka is within the compatibility range for target Boot.
- [ ] `kafka-clients` is within the range supported by Spring Kafka and Kafka brokers.
- [ ] `spring-kafka-test` / Boot Kafka test starter matches runtime.
- [ ] Kafka Streams/Schema Registry dependencies checked separately if used.
- [ ] No unapproved version overrides.
- [ ] Runtime/test dependency graph saved in release evidence.

### Application/Wire Semantics

- [ ] Producer futures/callbacks migrated.
- [ ] `KafkaTemplate`, consumer factory, and listener factory are correct.
- [ ] `group.id`, topics, partitions, and ack mode preserve the contract.
- [ ] JSON/Avro/Protobuf schemas compatible between old/new producer–consumer.
- [ ] Error handler/retry/DLT tested against a real broker.
- [ ] Invalid JSON/deserialization errors have a recovery path.
- [ ] DB/event IDs protect against duplicate replay.
- [ ] Kafka transaction scope and external side effects are delineated.

### Operations

- [ ] TLS/SASL/ACLs and broker feature levels tested.
- [ ] Metric/trace/log dashboards continue working.
- [ ] Canary has clear baselines and rollback thresholds.
- [ ] Rollback accounts for schemas, offsets, and committed data.
- [ ] CI does not quietly skip required container integration tests.
- [ ] Runbooks for DLT replay/poison messages/idempotency are ready.
- [ ] Incident owner and compatibility window end time are assigned.

## 26. Conclusion

Upgrading Spring Boot for a Kafka application is not an isolated operation. You must control simultaneously:

\[
\mathrm{Java}
\rightarrow
\mathrm{Spring\ Boot}
\rightarrow
\mathrm{Spring\ Kafka}
\rightarrow
\mathrm{kafka\!-\!clients}
\rightarrow
\mathrm{Kafka\ brokers}
\]

as well as **wire schemas, offset commits, retry/DLT, transactions, security, and metrics**.

The safe approach is **letting the Spring Boot BOM manage dependencies by default**, consulting official compatibility matrices, writing regression tests against real brokers, supporting mixed-version rollout phases, and having a way to recover data after failures.

A service may start up cleanly and report a green health endpoint, yet if the DLT cannot record poison messages or the DB gets duplicated on replay, the upgrade has not achieved **reliability compatibility**. The final criterion must be correct business outcomes across both happy paths and failure paths.

## 27. References

- [Spring for Apache Kafka — Project Compatibility](https://spring.io/projects/spring-kafka/): matrix across Spring Kafka, Kafka clients, and Spring Boot.
- [Spring Kafka — Override Spring Boot Dependencies](https://docs.spring.io/spring-kafka/reference/appendix/override-boot-dependencies.html): managing/overriding Kafka versions.
- [Spring Kafka — Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html): Spring Kafka 3 → 4, KRaft, Jackson, and retry.
- [Spring Kafka — Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html): Kafka starter and Java baseline.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): DefaultErrorHandler, DLT.
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): retry topics and `@RetryableTopic`.
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): Kafka transactions and exactly-once scope.
- [Spring Kafka — Testing](https://docs.spring.io/spring-kafka/reference/testing.html): Embedded Kafka and test helpers.
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): Spring Boot Kafka auto-configuration.
- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/reference/appendix/dependency-versions/coordinates.html): managed versions per release.
- [Spring Boot 4 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): modular starters, Jackson 3, and API migration.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): service connections.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): client/broker protocol, transactions, security.
