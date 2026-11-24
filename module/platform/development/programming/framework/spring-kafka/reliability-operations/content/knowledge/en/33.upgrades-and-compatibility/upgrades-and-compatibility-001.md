# Spring Kafka and Kafka Client Compatibility During System Upgrades

A Spring Kafka application can run stably for months and yet start failing after an upgrade of Spring Boot, Spring Kafka, the `kafka-clients` library, or the Kafka broker. Those failures are not limited to `ClassNotFoundException` or `NoSuchMethodError` at startup. In some cases, the application still starts and connects normally, but changes in consumer group behavior, offset commit, retry, serialization, or transactions cause duplicate data processing, loss of recoverability, or rising lag.

In the **Upgrades and Compatibility** group of **Spring Kafka Reliability Operations**, the article **Spring Kafka and Kafka Client Compatibility** explains how to identify the dependency layers, select an operable version combination, check impact before upgrading, and design reliable regression tests.

The goal is not to memorize an immutable version table, because releases and support policies change over time. What matters is understanding **who manages versions, at which layer compatibility is required, which features depend on the broker version, and what test evidence is sufficient for a safe release**.

Code examples primarily use **Java 17, Spring Boot 3.x, Spring Kafka 3.x**, and common Gradle/Maven syntax. For newer generations of Spring Boot/Spring Kafka, consult the corresponding migration guide and JDK requirements before using the code verbatim. Strings such as `3.x.y` in this document are version placeholders, not verified version recommendations for every project.

## 1. Map of Components Requiring Compatibility

A service using `@KafkaListener` typically has multiple dependency layers:

```text
Application code
  |  @KafkaListener, KafkaTemplate, error handlers
  v
Spring Boot (dependency management + auto-configuration)
  |
  +-- Spring Framework / Spring Security / Micrometer
  |
  v
Spring for Apache Kafka (spring-kafka)
  |
  +-- Listener container, annotation, retry/DLT
  +-- KafkaTemplate, KafkaTransactionManager
  +-- Serialization helpers, events, testing integrations
  |
  v
Apache Kafka Java client (kafka-clients)
  |
  +-- KafkaConsumer / KafkaProducer / AdminClient
  +-- Kafka protocol requests/responses
  +-- Group coordination and record delivery
  |
  v
Kafka brokers + controllers + cluster configuration
  |
  +-- Protocol/features and broker versions
  +-- Topic configuration, ACL, quotas
  +-- Consumer group protocol compatibility
  +-- Transaction coordinator
  |
  v
Message data contract / downstream systems
```

Beyond the Kafka runtime, the application also depends on:

- **JDK:** the Java version required by Spring Boot, Spring Framework, Spring Kafka, and the Kafka client.
- **Build tooling:** Gradle/Maven plugins and dependency-management/BOM.
- **Schema tooling:** JSON/Avro/Protobuf, Schema Registry, and third-party serializers/deserializers.
- **Security:** TLS, SASL, ACLs, certificates, and client authentication.
- **Observability:** Micrometer, Spring Observation, tracing, and client metrics.
- **Test runtime:** `spring-kafka-test`, Embedded Kafka, Testcontainers, broker image, and JUnit.

Therefore, the question "Can Spring Kafka version X work with Kafka broker Y?" solves only **one part** of the upgrade problem.

## 2. Three Types of Compatibility to Check Separately

### 2.1. API/Binary Compatibility on the JVM

`spring-kafka` is compiled against specific APIs of `kafka-clients` and Spring Framework. When a JAR is replaced with a version outside the supported combination, errors may appear before the application can even create a consumer:

```text
java.lang.NoSuchMethodError: ...
java.lang.NoClassDefFoundError: ...
java.lang.ClassNotFoundException: ...
java.lang.AbstractMethodError: ...
```

For example, one version of Spring Kafka calls a new method from the Kafka client, while the runtime classpath contains an older `kafka-clients`. Application source code may compile successfully in one environment yet still fail at runtime if dependency resolution differs.

**Conclusion:** Check the resolved versions on the **runtime classpath**, not just the declared lines in `build.gradle` or `pom.xml`.

### 2.2. Protocol Compatibility Between Kafka Client and Broker

Kafka uses a protocol with an API version negotiation mechanism between client and broker. As a result, **it is not mandatory for the client version number to match the broker version number** in every case. A newer client can connect to an older broker and use commonly supported APIs/features.

However:

- A new feature may require a sufficiently new broker.
- An older broker may not understand a new API request/version.
- A client may remove methods or connection mechanisms that are too old.
- A combination that connects successfully does not prove that transaction, group protocol, or security features all work.
- Major Kafka upgrades can change broker deployment prerequisites, Java runtime, or metadata mechanisms.

**Conclusion:** Wire protocol compatibility is different from Java API compatibility and different from whether a specific feature is supported.

### 2.3. Application Behavior Compatibility

Two version sets may both start up cleanly yet still differ in:

- Offset commit timing across ack modes.
- Listener container lifecycle and shutdown behavior.
- Error handling, backoff, seek, retry, and dead-letter publication.
- Consumer group assignment and rebalance.
- Serializer/deserializer defaults and headers.
- Kafka transactions, producer fencing, and idempotence.
- Metrics, event payloads, logging, and tracing.
- Default values of the Kafka client/Spring container.

This is the most easily overlooked risk category. For a reliable system, **a "send one message and receive one message" test is only the first step** and is not enough to prove a safe upgrade.

## 3. Reading a Version Matrix Properly

A high-level understanding of the product lines:

| Component | Common Reference Generation | What to Check |
| --- | --- | --- |
| Spring Boot 3.x | Typically paired with Spring Framework 6.x, Java 17+, and Spring Kafka 3.x per the BOM | Which exact **minor/patch** version is managed by the BOM. |
| Spring Kafka 3.x | Designed for the Spring Framework 6.x ecosystem and corresponding Kafka Java clients | The `kafka-clients` version tested/supported by the project. |
| Spring Boot 4.x / Spring Kafka 4.x | Generation with platform/API requirement changes compared to 3.x | Migration guide, Java baseline, Spring Framework, and Kafka client in use. |
| Kafka Java client 3.x / 4.x | Implements KafkaConsumer, KafkaProducer, AdminClient | Binary API, new features, broker minima, and removed/deprecated APIs. |
| Kafka broker 3.x / 4.x | Provides protocol, group coordination, transactions, and cluster features | Rolling upgrade policy, broker feature level, and controller type. |

**The table above is not a compatibility guarantee matrix for every version pair.** A `Spring Boot 3.2.x` and `Spring Boot 3.4.x` release may manage different Spring Kafka/Kafka client patches. Use the table only to identify **which documentation and dependencies need checking**, not to guess patch versions.

To create an official matrix for a project, record the **exact versions**:

```text
Application build:
  JDK runtime: ...
  Spring Boot: ...
  Spring Framework: ...
  spring-kafka: ...
  kafka-clients: ...
  spring-kafka-test: ...
  Serializer/Schema Registry clients: ...

Environment:
  Kafka broker version(s): ...
  Metadata/controller mode: ...
  Inter-broker / feature level: ...
  Security mechanism: ...
  Kafka topics and retention: ...
```

Then cross-check this combination against release notes, compatibility documentation, and integration test results.

### Useful Rule

**Prefer the combination managed by the Spring Boot BOM**, unless there is an explicit reason to override. A BOM does not replace testing, but it helps avoid combinations of JARs whose versions accidentally drift apart.

## 4. Who Actually Decides the `kafka-clients` Version?

In a Spring Boot application, many dependencies are managed by the Spring Boot BOM or a dependency management plugin. `spring-kafka` may pull in `kafka-clients` transitively; at the same time, another library may request a different Kafka client.

For example:

```text
spring-boot-starter-...
   |
   +-- spring-kafka: version A
         |
         +-- kafka-clients: version B

another-library
   |
   +-- kafka-clients: version C

Gradle/Maven resolver
   |
   v
runtimeClasspath: selected kafka-clients version
```

A **dependency convergence conflict** can occur if modules apply the BOM inconsistently.

Do not conclude that adding:

```groovy
implementation("org.apache.kafka:kafka-clients:some-version")
```

is enough to "upgrade Kafka." That declaration may force the Kafka client beyond the combination tested by the current Spring Kafka; it does not upgrade Spring Kafka, Spring Framework, or the broker.

### Reading the Dependency Graph with Gradle

In a Gradle project:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

On Windows PowerShell:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
```

Check:

- Which version is **selected**.
- Which module requests a different version.
- Which version is upgraded/downgraded by the BOM, constraints, or conflict resolution.
- Whether `compileClasspath`, `runtimeClasspath`, and `testRuntimeClasspath` differ.
- Whether multiple classloaders or a fat JAR differ from local check results.

These commands are used to **inspect dependencies** in a real upgrade workflow; this lesson itself does not require running a build of any specific repository.

### Reading the Dependency Graph with Maven

```bash
mvn dependency:tree -Dincludes=org.springframework.kafka:spring-kafka
mvn dependency:tree -Dincludes=org.apache.kafka:kafka-clients
mvn dependency:tree -Dverbose
```

When there are multiple modules, inspect the module that actually packages the application and the module that runs the tests. A parent POM managing dependencies can differ from the dependencies packaged into the final module's executable JAR.

## 5. Examples of Dependency Declarations via BOM

### 5.1. Gradle with Spring Boot

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.x.y'
    id 'io.spring.dependency-management' version '1.x.y'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

`3.x.y` and `1.x.y` are placeholders: the project must declare **versions that actually exist in the repository** and are supported by the corresponding plugins. In projects using a Gradle native platform/BOM instead of the dependency-management plugin, the declaration syntax differs, but the goal remains having **a single unified source of version management**.

If the application uses an internal organizational starter that already includes `spring-kafka`, avoid adding a direct declaration solely to change the version without checking transitive dependencies.

### 5.2. Maven with Spring Boot Parent

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.x.y</version>
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
</project>
```

Do not manually set versions for individual `spring-kafka` and `kafka-clients` artifacts unless an override is needed. Inspect the effective POM or dependency tree to see the result.

### 5.3. When Overriding the Kafka Client Is Truly Necessary

Sometimes a Kafka client upgrade is required for a security patch or a specific capability. In that case:

1. Identify the **vulnerability/feature** requiring the change.
2. Check the release notes and tested dependency range of Spring Kafka.
3. Check changed/removed APIs, deserializers, group protocol, transactions, and broker support.
4. Override intentionally in a single centralized location.
5. Verify the resolved runtime classpath and the final package.
6. Run regression + integration tests against a real broker.
7. Document the override reason, owner, and planned removal date.

Forcing a client version may be valid within a range confirmed by Spring Kafka, but **do not assume every patch/minor/major is safe**. Do not rely solely on Semantic Versioning assumptions, especially when public Java APIs or native dependencies are involved.

## 6. Binary Compatibility Errors: Symptoms and Investigation

### `NoSuchMethodError` or `NoClassDefFoundError`

For example, the application fails after deployment:

```text
java.lang.NoSuchMethodError:
  org.apache.kafka.clients.consumer.SomeType.someMethod(...)
```

Investigation steps:

1. Identify the class/method and the JAR being loaded at runtime.
2. Obtain the `runtimeClasspath` of the deployed module, not just `testRuntimeClasspath`.
3. Check whether a `kafka-clients` copy is bundled by a third-party library or shared classpath.
4. Compare the dependency graph between the failing deployment and the working release.
5. Determine compatibility with the Spring Kafka version using release notes.
6. Rebuild the artifact with explicit dependency convergence.
7. Run smoke tests and consumer/producer integration tests.

Do not fix this by adding multiple JAR versions to the classpath. In most Java applications, having multiple versions of the same class on the classpath leads to unpredictable class selection behavior.

### Compile Succeeds but Startup Fails

The compile build may use a different classpath from production:

```text
CI compile:    kafka-clients X
Prod runtime: kafka-clients Y
```

This risk appears when:

- Provided dependencies are used improperly.
- The container image loads external JARs.
- Build plugin repackaging has excludes/overrides.
- Another runtime supplies shared libraries.
- Dependency lockfiles are not applied consistently.

Include a check of the resolved dependencies of the **deployed artifact** in the release record, rather than storing only the declared list.

## 7. Wire Protocol Compatibility with Kafka Brokers

The Kafka client uses requests such as metadata, fetch, produce, offset commit, group coordination, transaction coordinator, and admin operations. The broker only supports certain APIs/versions. The Kafka client typically discovers broker capabilities via `ApiVersions`, but that does not mean the broker supports every new feature.

```text
Kafka client 4.x
    |
    | negotiate protocol API versions
    v
Kafka broker 3.x
    |
    +-- API supported by both? -> Can be used
    |
    +-- Requested feature unsupported? -> Fail / fallback per client
```

Illustrative diagram; **do not assume every 4.x client → 3.x broker combination is supported**. Check the minimum broker version for the client and enabled features.

### Checking Three Levels

- **Level 1: connectivity:** TLS/SASL, broker metadata, advertised listener, broker discovery.
- **Level 2: data CRUD:** producer sending, consumer reading, offset commit, and rebalancing.
- **Level 3: advanced features:** transactions, idempotent producer, cooperative rebalance, new group protocol, AdminClient features, delegation tokens, and broker-dependent settings.

An application that has "subscribed successfully" does not prove that the transaction coordinator and DLT/retry work properly.

### `UnsupportedVersionException`

If the client requests an API that the broker does not support, `UnsupportedVersionException` or similar feature capability errors may occur. When investigating:

1. Check which operation called the unsupported API.
2. Check the Kafka broker version, Kafka client version, and feature level.
3. Check which feature was newly enabled during the upgrade.
4. Check whether a supported fallback exists or the broker must be upgraded.
5. Test in an environment with the same broker version as production.

Do not "fix" this by disabling all reliability features such as idempotence or transactions without evaluating the consequences of data loss or duplication.

## 8. Kafka Broker Version Differs from Cluster Feature Level

In some broker upgrade processes, the **running binary version** and the **enabled feature level** are not necessarily the same immediately after a rolling upgrade. A Kafka cluster has feature/metadata management mechanisms depending on the Kafka generation; upgrading binaries does not automatically mean all new features are active.

In particular, check:

- Whether the cluster uses KRaft or still depends on an older controller mechanism per broker version.
- Whether the broker/controller quorum is in a mixed or unified state.
- Which feature levels are permitted to be raised after the entire cluster stabilizes.
- Whether new brokers are serving old clients during the rolling upgrade phase.
- Which consumer group/transaction features require a higher feature level.

**Kafka 4.0 is an important milestone on the broker side because this generation uses KRaft and no longer operates in the old ZooKeeper mode.** This is a **cluster/controller** upgrade concern; it does not mean a Spring Kafka application immediately needs `@KafkaListener` changes just because the broker switched metadata mode.

Even so, do not apply any rolling upgrade procedure across a major milestone without following the corresponding Kafka broker documentation. Rules for updating controllers, brokers, and feature levels must be based on a dedicated cluster plan.

## 9. Java/JDK Compatibility

Even when Spring Kafka and the Kafka client are API-compatible with each other, the JDK can be a blocker.

For example, determine:

- The **minimum** Java version of the Spring Boot release in use.
- The minimum Java version of Spring Framework/Spring Kafka.
- The minimum Java version of the running `kafka-clients`.
- The Java version of the Gradle/Maven runtime and the compile Java toolchain.
- The Java version in the production container image.
- TLS provider, JDK crypto policy, CA store, and certificate-related changes.

Spring Boot 3.x releases use a Java 17 baseline, but **do not infer that every Boot 4.x and Spring Kafka 4.x release will support the exact same set of JDK/runtimes**. Check the platform requirements table of the target release.

### Why a Compile Toolchain Is Not Enough

`gradle java.toolchain = 17` can ensure compiling/testing with the desired toolchain, yet the deployed image may still contain a different JRE. If the binary is compiled for a higher class file version than the runtime JVM, startup errors such as `UnsupportedClassVersionError` occur.

Record the actual JDK version in the artifact manifest or startup diagnostics, and inspect the container image deployed in the staging environment.

## 10. Compatibility When Upgrading Spring Kafka Major/Minor Versions

Spring Kafka provides higher-level APIs than the Kafka Java client. When upgrading, potential changes can include:

| API Group | Potential Impact |
| --- | --- |
| `KafkaTemplate` | Send result types, callback/future APIs, and exception handling. |
| `@KafkaListener` | Annotation attributes, container factory settings, endpoint handling. |
| `ConcurrentMessageListenerContainer` | Lifecycle, thread naming, pause/resume, event emission. |
| Error handlers | API changes or removal of legacy handlers, how records are routed to recovery/DLT. |
| Retry topics | Topic suffix/backoff/endpoint configuration and feature defaults. |
| `KafkaTransactionManager` | Transaction synchronization, propagation, and producer coordination. |
| Serialization | JSON mapper, headers, and trusted packages. |
| Metrics/events | Observation names, metric tags, event interfaces. |
| Testing | Embedded Kafka APIs and how the broker bootstrap property is configured. |

One API transition example seen when upgrading across ecosystem versions is handling the result from `KafkaTemplate.send(...)`. Applications with code tightly coupled to the future/callback type of one version line may need updates when a newer line switches the API to a different future type.

Rule: **read the migration guides of both Spring Kafka and Spring Boot**, then test-compile modules that use public APIs. Do not read only the Kafka broker release notes.

### What to Do Before Incrementing a Major Version

1. Inventory the APIs used by the application, especially custom `ConsumerFactory`, `ProducerFactory`, listener factories, and error handlers.
2. Find deprecation warnings already present in the current version.
3. Replace deprecated APIs with their replacements **before** moving to a major version if possible.
4. Upgrade Spring Boot/Spring Framework and Spring Kafka in a verified combination.
5. Run compile, unit, integration, performance, and chaos tests.
6. Review default configuration changes in the client and container.
7. Check whether logs/metrics/alerts need field name or event filtering updates.

### Do Not Import APIs by Pattern While Ignoring Version

For example, newer code using `DefaultErrorHandler` does not mean every older Spring Kafka version understands this class. Similarly, package names, overloads, or constructors can differ between two release lines.

When taking snippets from documentation, choose the **documentation version matching your project's dependency**, rather than copying the default latest page and assuming the code will work on every version.

## 11. Consumer Group Protocol and Rebalance

Consumer groups are one of the areas that must be tested after upgrading the Kafka client/broker. Some Kafka generations support a new group coordination protocol or different assignment strategies.

Configurations to review:

- `group.id` and how consumer groups are shared across service versions.
- `partition.assignment.strategy` in the classic consumer group protocol.
- `group.protocol` and related properties if the Kafka client/broker supports the new consumer group protocol.
- `max.poll.interval.ms`, `max.poll.records`.
- `session.timeout.ms` and heartbeat configuration per group protocol in use.
- `client.id`, static membership, and consumer instance limits.
- Listener container concurrency relative to partition count.

Do not copy `heartbeat.interval.ms` verbatim to a different group protocol without re-reading its semantics. Some parameters controlled by the client in the classic protocol may be broker-controlled in the new mechanism.

### Risk Example During Rolling Deployment

```text
Old consumers (version A)         New consumers (version B)
           |                                  |
           +---------- same group ------------+
                              |
                              v
                    Kafka group coordinator
                              |
                              v
                  partition assignments change
```

During a rolling deploy:

- Old and new consumers may coexist in the same group.
- Assignment and rebalance occur as instances join/leave.
- Listeners currently processing may have partitions revoked.
- Uncommitted records may be redelivered.
- A new group feature may not support mixed-mode as the application expects.

For applications with strict SLAs or ordering requirements, test a **mixed-version rollout** in staging first. Do not assume every consumer group can switch protocols simultaneously without a plan.

### Key Measurements

- Rebalance count and rebalance duration.
- Partition assignments before/after rollout.
- Consumer lag per partition.
- Offset commit success/failure.
- Retry/redelivery event counts.
- Per-key message ordering within a partition.
- Drain time of old pods during shutdown.

## 12. Ack Mode and Offset Commit After Upgrade

Spring Kafka supports multiple acknowledgment modes via the listener container. Some systems use record listeners, while others use batch listeners or manual acknowledgment.

For example:

```java
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL);
```

This is only a configuration example; an application using manual ack must ensure the listener receives and calls `Acknowledgment.acknowledge()` at the right time.

Cases to test:

| Case | Post-Upgrade Risk |
| --- | --- |
| Listener succeeds | Is the offset committed properly after processing? |
| Listener throws exception | Are unprocessed offsets redelivered/retried properly? |
| Handler recovers and sends to DLT | Does committing the original record follow policy? |
| Shutdown/rebalance mid-processing | Is redelivery valid with no data loss? |
| Manual ack before external side effect | Data can be lost if the side effect fails after ack. |
| Manual ack after external side effect | Duplicates occur if commit/ack fails after the side effect completes. |
| Batch listener with one failing record | Are failed index selection and remaining record handling correct? |

Distinguish **at-least-once** from **exactly-once within Kafka transaction scope**. Changing the client version can change ordering/conditions on commit failure or timeout; if business side effects target a database/HTTP endpoint, idempotency is still required.

## 13. Error Handling, Retry, and DLT: Behavioral Compatibility

Many applications use `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, `ErrorHandlingDeserializer`, or `@RetryableTopic`.

What to verify after an upgrade:

1. **Deserialization failure:** does the error occur before or after the listener receives the record? Which error handler is invoked?
2. **Listener failure:** how many blocking retries occur, and what is the backoff?
3. **Non-retryable exception:** which exception types are classified as fatal immediately?
4. **DLT routing:** are the topic name, partition, headers, and serializer still right?
5. **Recovery failure:** if DLT publishing fails, is the original record retried?
6. **Offset commit:** is a recovered record replayed unexpectedly?
7. **Retry-topic scheduling:** are delay/backoff and topic topology right after deployment?
8. **Retries across restarts:** are offsets/transactions and business deduplication preserved?

Example error configuration for Spring Kafka 3.x:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    var backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
```

Main imports:

```java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.util.backoff.FixedBackOff;
```

This is a **policy illustration** pattern rather than a complete production configuration. It requires a DLT topic, a producer serializer capable of sending failed payloads, an exception classification policy, and understanding how retry counts are calculated under the API of the version in use.

### Why DLT Tests Cannot Just Assert "Topic Exists"

For example, a JSON payload failing deserialization may not become the object the listener expects. If the DLT producer serializer only supports deserialized object types, publishing raw invalid bytes can continue to fail.

Test with all of the following:

- Valid payload where the listener succeeds.
- Malformed payload.
- Old/new schema versions.
- Retryable business errors.
- Fatal errors that must go to the DLT.
- DLT temporarily unwritable.
- Error info headers and original record key.

Some changes from upgrading a serialization library can make the error handler look "broken," when in reality the DLT producer can no longer serialize failed data properly.

## 14. Serializer and Deserializer: Data Compatibility

JAR compatibility does not guarantee **message schema** compatibility. With JSON, Avro, Protobuf, or custom binary formats, old and new consumers can interpret data differently.

### 14.1. JSON and Type Headers

Spring Kafka JSON serializers/deserializers can use type information in headers depending on configuration. An upgraded producer may send a specific Java type header that a consumer in another module does not know or is not trusted to deserialize.

Decisions that must be clear:

- Are type headers used, or a fixed DTO contract?
- Are Java class/package names placed into headers?
- Which trusted packages does the consumer allow?
- When refactoring packages, can old consumers still read messages already stored on the topic?
- Is there a default target type when headers are missing/invalid?
- Is a schema registry needed instead of relying on Java class names?

Do not configure trusted packages as a system-wide wildcard just to silence deserialization errors without evaluating security risks. Allow only the types/packages actually used.

### 14.2. Schema Evolution

Example event record:

```json
{
  "eventId": "evt-01",
  "customerId": "c-01",
  "amountCents": 10000
}
```

A new version adds a field:

```json
{
  "eventId": "evt-02",
  "customerId": "c-01",
  "amountCents": 10000,
  "currency": "USD"
}
```

A new producer may send the extra `currency` field; whether an old consumer can read it depends on the serializer, validation, and ignoring unknown fields. Conversely, if a new consumer requires `currency` while old records on the topic lack that field, replay/rewind can fail.

Therefore tests must verify:

- **New consumer reads old messages.**
- **Old consumer reads new messages** if rollout requires mixed versions.
- Optional/default fields and unknown fields.
- Registry schema compatibility rules if using Avro/Protobuf.
- Records already stored within the retention window and DLT/retry topics.
- Messages replayed from backups or cluster migrations.

### 14.3. Do Not Upgrade Schema Registry Clients in Isolation

Third-party Avro/Protobuf serializers can pull in versions of the Kafka client, Jackson, or other libraries. When upgrading:

1. Inspect the dependency tree.
2. Check registry/server compatibility.
3. Test schema lookup/registration and caching.
4. Test real broker topic data with old/new schemas.
5. Ensure TLS/SASL credentials remain configured properly.
6. Check the DLT serializer for failed records.

## 15. Producer Idempotence, Transactions, and Exactly-Once

A reliable processing application may use:

- Producer idempotence.
- Kafka transactions.
- Container/producer transaction integration.
- Database transactions.
- Remote HTTP side effects.

These **do not share the same consistency boundary**.

### Producer Idempotence

An idempotent producer helps avoid certain duplicates caused by producer retries under the Kafka producer contract. It does not prevent the application from **sending the same business event twice** with separate `send()` calls and different business IDs.

### Kafka Transactions

Kafka transactions can tie record publishing and offset commits together within Kafka scope when consume-process-produce is configured in a supported pattern. However, a Kafka transaction **does not automatically roll back** sending an email, calling a payment API, or committing to an external database.

For example:

```text
Kafka record offset=100
       |
       v
Spring @KafkaListener
       |
       +-- Write local DB committed
       |
       +-- Publish Kafka output in Kafka TX
               |
               +-- Kafka TX abort
               |
               v
Local DB commit does not automatically disappear
```

If business logic needs durable coordination between a database and Kafka, you usually need to consider the transactional outbox or an orchestration mechanism with idempotency/reconciliation, rather than assuming enabling Kafka transactions creates "global exactly-once."

### `transactional.id` and Fencing

When using a Kafka transactional producer, changing the naming/prefix of transactional IDs during a rolling deploy can affect how producer instances are identified and the fencing mechanism. Avoid improperly reusing identities across multiple active instances, and do not change them haphazardly while investigating recovery.

### Testing Transactions Across Upgrades

- Producer sends and commits a transaction: a `read_committed` consumer sees the record.
- Producer aborts a transaction: a `read_committed` consumer does not see the aborted record.
- Process dies before commit: output is not exposed as committed.
- Consumer restarts: offsets and outputs do not create duplicate business side effects.
- Rolling deploy with multiple instances: transactional IDs/fencing do not produce abnormal errors.
- Broker coordinator version/features: transaction APIs work properly in the target environment.

Do not merely assert that a message appears on a topic: with transactions, distinguish **committed**, **aborted**, and **uncommitted** behavior.

## 16. Consumer/Producer Configuration Defaults Can Change

A common mistake when upgrading libraries is believing unchanged configuration means unchanged behavior. Many properties use **defaults** rather than being explicitly declared.

Create a before/after comparison profile:

| Property | Why It Matters |
| --- | --- |
| `bootstrap.servers` | Connection target, advertised listeners, and failover capability. |
| `client.id` | Identifies the client in metrics/broker logs. |
| `group.id` | Preserves consumer group identity across deploys. |
| `auto.offset.reset` | Behavior when the group has no committed offset. |
| `enable.auto.commit` | If the container manages ack/commit, avoid conflicting settings. |
| `max.poll.interval.ms` | Maximum time between polls under Kafka group semantics. |
| `max.poll.records` | Affects batch processing and poll return latency. |
| `isolation.level` | `read_committed` vs `read_uncommitted`. |
| `acks` | Producer acknowledgment guarantee. |
| `enable.idempotence` | Relates to duplicates from producer retries. |
| `delivery.timeout.ms` | Time budget for producer sending. |
| `request.timeout.ms` | Request wait timeout. |
| `retries` | Producer retries and interaction with delivery timeout. |
| `partition.assignment.strategy` | Partition distribution strategy. |
| `group.protocol` | Group protocol supported per client/broker. |
| `security.protocol` | `PLAINTEXT`, `SSL`, `SASL_SSL`, ... |
| `sasl.mechanism` | Authentication mechanism must be supported by the broker. |

Do not hardcode every property just to keep old defaults. What is essential is **understanding which defaults affect semantics** and explicitly configuring business decisions that must stay stable.

### Example Test Profile

```yaml
spring:
  kafka:
    consumer:
      group-id: reliability-compat-it
      auto-offset-reset: earliest
      properties:
        isolation.level: read_committed
    producer:
      acks: all
      properties:
        enable.idempotence: true
```

This is an illustrative test profile for specific behaviors; it does not automatically enable Kafka transactions and is not a mandatory configuration for every application. If tests do not produce transactional messages, `read_committed` still reads normally sent messages.

## 17. Kafka Listener Container and Concurrency

Spring Kafka uses listener containers to manage consumer threads. After an upgrade, check:

- Whether the container factory is created by Spring Boot auto-configuration or custom configuration.
- Whether `@KafkaListener(containerFactory = "...")` points to the right bean.
- `concurrency` relative to partition count.
- `AckMode`, `pollTimeout`, `monitorInterval`, `noPollThreshold`.
- `CommonErrorHandler` and transaction manager.
- Lifecycle: auto-startup, pause/resume, shutdown timeout.
- Event listeners: idle/non-responsive/consumer paused/resumed/stopped.

A Spring Kafka 3.x configuration example:

```java
@Configuration
@EnableKafka
public class OrderKafkaConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    orderListenerFactory(
            ConsumerFactory<String, String> consumerFactory,
            CommonErrorHandler commonErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory
                        <String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.setCommonErrorHandler(commonErrorHandler);

        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

Relevant imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.ContainerProperties;
```

With three partitions, concurrency three can use three consumer threads; with one partition, increasing concurrency to three does not make one partition processed in parallel by three consumers in the same group.

### Non-Responsive Monitor Is Also Within Compatibility Scope

After upgrading versions, test events such as `NonResponsiveConsumerEvent` if the application relies on them for alerting or automation. Event emission timing is affected by `pollTimeout × noPollThreshold` and the monitor interval; tests need explicit thresholds rather than relying on unchecked defaults.

## 18. Embedded Kafka and `spring-kafka-test`

The test runtime can be a source of version drift:

```text
Application runtime:
  spring-kafka     A
  kafka-clients    B

Test runtime:
  spring-kafka-test C
  kafka-clients    D
  Kafka broker test classes E
```

Keep `spring-kafka-test` aligned with the `spring-kafka` line/version in use, unless support documentation confirms otherwise. Do not upgrade only the runtime dependency while keeping the test library from an older major line.

### Embedded Kafka Is Not Equivalent to Production

Embedded Kafka is very useful for testing:

- Topic creation and consumer assignment.
- Sending/receiving messages.
- Listener container startup.
- Ack/offset, retry, and DLT at a basic level.
- Kafka events within the test broker scope.

However:

- The embedded broker version comes from test dependencies; it does not necessarily match production brokers.
- KRaft/ZooKeeper configuration may differ by Spring Kafka/Kafka generation.
- A single broker does not simulate failover/cross-zone/network partitions of a multi-broker cluster.
- TLS/SASL/ACLs/quotas may not be enabled.
- Startup and leader election may differ from production.

Therefore, use both **Embedded Kafka** and **Testcontainers/cluster tests** when high reliability is required.

### Testcontainers with Exact Broker Version

A test using a Kafka/Confluent image can select a broker version close to production. When upgrading the client, test at a minimum against both **old** and **target** brokers if the organization has a rolling upgrade phase.

Image tags and runtime metadata must be recorded in test reports. Do not let a `latest` tag cause the environment to change between CI runs.

## 19. Minimal Integration Test Example with Embedded Kafka

Purpose: confirm a Spring Kafka–managed `@KafkaListener` can receive a message via `KafkaTemplate` and the test broker while avoiding startup races.

Example using Spring Kafka 3.x and Spring Boot 3.x:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "spring.kafka.consumer.group-id=compat-integration-test",
    "spring.kafka.consumer.auto-offset-reset=earliest",
    "spring.kafka.consumer.key-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.value-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.producer.key-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "compat-integration-test",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@Import(KafkaCompatibilityIT.FixtureConfig.class)
class KafkaCompatibilityIT {

    @Autowired
    private KafkaTemplate<String, String> template;

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @Autowired
    private Probe probe;

    @Test
    void producerAndListenerCanExchangeRecord() throws Exception {
        var container =
                registry.getListenerContainer("compat-listener");

        assertThat(container).isNotNull();

        ContainerTestUtils.waitForAssignment(container, 1);

        template.send(
                "compat-integration-test",
                "order-1",
                "hello-version-check").get(10, TimeUnit.SECONDS);

        assertThat(probe.received.await(10, TimeUnit.SECONDS))
                .isTrue();

        assertThat(probe.payload.get())
                .isEqualTo("hello-version-check");
    }

    static final class Probe {
        final CountDownLatch received = new CountDownLatch(1);
        final AtomicReference<String> payload = new AtomicReference<>();

        @KafkaListener(
                id = "compat-listener",
                topics = "compat-integration-test")
        void onMessage(String value) {
            payload.set(value);
            received.countDown();
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    @EnableKafka
    static class FixtureConfig {

        @Bean
        Probe probe() {
            return new Probe();
        }
    }
}
```

The example assumes the application has Spring Boot configuration to create `KafkaTemplate`, `ConsumerFactory`, `ProducerFactory`, and listener infrastructure. Tests must run on a compatible `spring-kafka-test` dependency, with the fixture class loaded into the context. For projects using other serializer types, adjust the template/record model accordingly.

This is a **smoke integration test**; it does not prove the safety of transactions, retry/DLT, rolling upgrades, or mixed-version groups. It is the first check to detect basic binary/protocol/configuration errors.

### Why Wait for Partition Assignment

Sending a record before the consumer joins the group while using `auto.offset.reset=latest` can cause test flakiness. `ContainerTestUtils.waitForAssignment(...)` confirms the consumer actually owns the partition before sending.

## 20. Integration Test Matrix for Upgrades

When planning to upgrade from dependency set A to B, build a matrix as follows:

| Application Set | Broker | Goal |
| --- | --- | --- |
| **Current app** | **Current broker** | Pre-upgrade baseline. |
| **Target app** | **Current broker** | Verify new client/framework against old broker during rollout. |
| **Current app** | **Target broker** | Verify old application against upgraded broker. |
| **Target app** | **Target broker** | Verify final post-upgrade state. |
| **Mixed app versions** | Planned current/target broker | Verify same consumer group and rolling deployment. |

This is a **logical** matrix; if a specific upgrade path does not support a pair, mark it **unsupported** and adjust the rollout sequence rather than forcing it as a mandatory test pair.

### Minimum Scenario Set

| Category | Scenario | Key Assertion |
| --- | --- | --- |
| Connectivity | Producer/consumer TLS/SASL connection | No auth/metadata errors, topic accessible. |
| Producer | Send/ack succeeds | Record written by broker per acks policy. |
| Consumer | Poll and process | Correct payload, key, headers, partition. |
| Offset | Restart after commit | No out-of-contract reprocessing. |
| Redelivery | Processing fails before commit | Record retried/redelivered per policy. |
| Serialization | Old/new schema | Consumer compatible with supported payloads. |
| Error handler | Retry then DLT | Retry count, DLT payload, and headers are correct. |
| Transactions | Commit/abort | `read_committed` distinguishes valid records. |
| Group rebalance | Join/leave/rolling deploy | Valid assignment, no lost side effects. |
| Long processing | Near/exceeds poll interval | Alerts/rebalance/recovery work properly. |
| Shutdown | Graceful pod termination | Appropriate commit, drain, and container lifecycle. |
| Network fault | Broker temporarily unreachable | Processing resumes after recovery, no retry storm. |
| Security | Certificate/token rotation | Client reconnects successfully per policy. |
| Performance | Throughput, lag, latency | No regression outside acceptable thresholds. |

For systems using only producers without listeners, running the full consumer-group suite is unnecessary. For financial systems using Kafka transactions or an outbox, crash-recovery correctness testing is the highest priority.

## 21. Testing Behavior Under Errors and Restarts

Some bugs only appear when a crash happens between two steps.

### 21.1. Listener Finishes Processing but Offset Not Yet Committed

```text
Poll record offset 100
     |
     v
Business side effect committed
     |
     X process crashes before offset commit
     |
Restart
     |
     v
offset 100 delivered again
```

This is a classic at-least-once scenario. After upgrading the Kafka client or changing ack mode, test idempotency of the writer/remote operation rather than only asserting how many times the listener is invoked in a normal run.

### 21.2. DLT Publish Fails

Simulate the DLT producer failing to send. Verify the original record is retained/retried per policy and not committed as recovered when the DLT actually never received the record.

### 21.3. Stuck Consumer

Use a latch in the listener and monitor `NonResponsiveConsumerEvent`. Confirm that upgrading versions does not break alerting or silently shift thresholds.

### 21.4. Rebalance During Processing

Run two consumer instances in the same group, hold one listener mid-processing, then stop the instance. Confirm offsets/side effects are not lost and business keys remain idempotent.

### 21.5. Producer Transaction Abort

Send a record inside a transaction, intentionally abort, and read with `read_committed`. An aborted record must never be treated as valid business data.

## 22. Broker and Client Upgrades: Deployment Sequence

There is no single order for every combination, but the process is generally safer when **keeping the scope of change small**.

### Preparation Phase

1. Record exact current/target versions of JDK, Boot, Framework, Spring Kafka, Kafka client, and broker.
2. Check official support matrices and broker/client minimum versions.
3. Read migration guides for major/minor versions with behavioral changes.
4. Check topic configs, ACLs, transactions, group protocol, and schema registry.
5. Back up/publish baseline metrics, consumer lag, error rate, and DLT backlog.
6. Run the dependency graph on the artifact.
7. Prepare a rollback plan and rollout stop criteria.

### Testing Phase

1. Upgrade dependencies on a separate branch; do not change all components simultaneously when unnecessary.
2. Run compile and unit tests.
3. Run Embedded Kafka smoke tests.
4. Run the Testcontainers/broker matrix with target versions.
5. Run network fault/rebalance/retry/DLT/transaction tests aligned with business needs.
6. Compare throughput and consumer lag against the baseline.
7. Check that dashboards/alerts still measure accurately after changes.

### Deployment Phase

1. Select a canary instance/topic/group or appropriate traffic scope.
2. Observe startup, authentication, broker metadata, and first records.
3. Upgrade additional replicas within rollout limits while monitoring rebalances.
4. Check group offsets and side effects in real time.
5. Raise feature levels/new consumer group protocol only when approved and compatible.
6. Drain and retire old instances via graceful shutdown.
7. Keep rollback artifacts/configs available.

### Post-Deployment Verification Phase

- DLT/retry backlog does not grow abnormally.
- Consumer lag and rebalances are stable.
- No lost messages or out-of-contract duplicate side effects.
- Publish/processing success rate matches baseline.
- No classpath errors, and the metrics exporter continues working.
- Document deployed versions and dependency override decisions.

**Do not upgrade the client, broker, schema registry, JVM, and group protocol mechanism at the same time unless strictly required.** When many variables change simultaneously, identifying root causes of failures becomes very hard.

## 23. Rolling Upgrade and Conditional Rollback

Rolling back an application is not as simple as re-running the old JAR if the upgrade changed data or protocols.

Before declaring rollback readiness, answer:

- Can old consumers read messages sent by new producers?
- Do new DLT/retry topics contain headers/schemas understood by the old app?
- Were topic configurations or ACLs changed in a way the old app cannot use?
- Does the new broker feature level still accept old clients?
- Can a consumer group using the new protocol revert to old behavior along a supported path?
- Do old app Kafka transactions / transactional IDs suffer fencing/conflicts?
- Are there accompanying state migrations in databases or external systems?

A good rollback plan must **verify backward compatibility** before rollout, rather than merely keeping the old container image.

### Canary and Blue/Green

Canary is appropriate when a subset of traffic/partitions can be routed to the new version and observed. Blue/green may need a separate group ID or separate data source, because two deployments in the same consumer group split partitions rather than automatically creating a "mirror test" of all traffic.

If creating a new group for shadow consumption, it maintains its own offsets; ensure the shadow listener **does not perform side effects** in production systems. Do not run two consumer groups concurrently writing to a non-idempotent target just to "compare versions."

## 24. Security Compatibility During Upgrades

An application may fail after an upgrade even when the Kafka client is completely protocol-compatible, because the security handshake is affected by the JDK or broker config.

Factors:

- TLS protocols/cipher suites accepted by the new JDK.
- CA truststore and certificate loading method.
- Hostname verification, broker SANs, and advertised listeners.
- SASL mechanisms: PLAIN/SCRAM/OAUTHBEARER/Kerberos depending on the system.
- Token expiry/refresh for OAuth.
- Kafka ACLs for consumer groups, topics, transactions, and idempotent producers.
- Secret rotation and truststore/key material.
- Network proxies, load balancers, and DNS behavior.

An `SSLHandshakeException` is not proof that Spring Kafka is API-incompatible with the Kafka broker. Diagnose the security layer separately.

### Do Not Log Secrets for Debugging

When capturing Kafka client configs or Spring Boot configuration properties in logs, mask/redact:

- SASL JAAS config.
- Passwords/secrets/tokens.
- Private keys.
- Credentials in endpoint URLs.
- Message payloads containing sensitive data.

Fields like `client.id`, `group.id`, broker host, and error class are usually far more useful than printing the entire raw config.

## 25. Observing Compatibility Through Logs and Metrics

An upgrade "without exceptions" can still increase lag, retries, or end-to-end latency.

Monitor at least:

| Signal | What to Compare Before/After |
| --- | --- |
| Consumer lag per partition | Whether there is sustained growth or imbalance. |
| Poll frequency / processing duration | Whether the consumer returns to poll at the expected cadence. |
| Rebalance count/duration | Whether excessive group rejoins occur. |
| Offset commit failures | Whether commit semantics changed or coordinator errors occurred. |
| Producer send latency/P95/P99 | Whether latency increased when acks/transactions changed. |
| Producer record error/retry rate | Whether broker errors, timeouts, or quotas occurred. |
| DLT publish rate | Increase due to business errors or changed deserializers. |
| Retry count/backoff | Whether a retry storm or altered policy occurred. |
| Transaction abort/fencing | Whether producer identity conflicts occurred. |
| Deserialization errors | Whether schemas/type headers changed. |
| JVM CPU/GC/threads | Whether client/Spring updates changed footprint. |
| Kafka broker/network | Quotas, request latency, connection churn. |

Add deployment metadata to logs/observability such as application version, Spring Kafka version, Kafka client version, and environment, but do not use `messageKey` or `offset` as metric labels due to high cardinality.

### Structured Log Example

```text
INFO kafka.consumer.started
  applicationVersion=2026.11.16
  listenerId=orders-listener
  groupId=orders-service
  springKafkaVersion=<resolved-version>
  kafkaClientVersion=<resolved-version>

WARN kafka.consumer.rebalance
  listenerId=orders-listener
  assignedPartitions=...
  durationMs=...

ERROR kafka.message.deserialize.failed
  listenerId=orders-listener
  errorType=...
  schemaVersion=...
```

In practice, versions can be obtained from build metadata/package implementation versions or the corresponding version utility library. Do not guess versions from hardcoded JAR filenames when artifact shading/repackaging may alter them.

## 26. Common Upgrade Mistakes

### 26.1. Upgrading Only `kafka-clients` While Keeping the Spring Kafka Major Version

This can cause `NoSuchMethodError` or unsupported API behavior changes. Before overriding, check the version range tested by Spring Kafka, compatibility notes, and regression tests.

### 26.2. Assuming Broker and Client Must Have the Same Version Number

That is not a universal rule of the Kafka protocol. However, there is also no guarantee that every version pair supports every feature. Distinguish basic connectivity from advanced capabilities.

### 26.3. Looking Only at Declared Dependencies

Gradle/Maven can resolve a different version due to BOMs/conflicts. Inspect the runtime classpath and packaged artifact.

### 26.4. Keeping `spring-kafka-test` from Another Release Line

This can break Embedded Kafka or test utilities even when the runtime is right. Keep test dependencies synchronized with runtime dependencies.

### 26.5. Using Only Embedded Kafka to Represent Production

The embedded broker does not necessarily match version, mode, TLS/SASL, cluster topology, and networking. Supplement with a broker matrix via Testcontainers/staging.

### 26.6. Not Testing Data Already Stored in Topics

New producers and new consumers work with new messages, yet new consumers fail to read old records. Always test schema evolution/replay/retention.

### 26.7. Not Testing DLT and Retry

The happy path succeeds, while deserialization errors or DLT publish failures stall the listener. Intentionally test failures and verify offsets.

### 26.8. Enabling the New Consumer Group Protocol Immediately When Upgrading Dependencies

Some features require broker/group support and have mixed-version conditions. Changing the protocol is a separate behavioral change and needs separate testing and rollout.

### 26.9. Changing Ack Mode Without Verifying Side Effects

Manual ack, record/batch commits, and transactions can alter redelivery conditions. Verify crash/rebalance cases as well.

### 26.10. Increasing Thread Count to "Cure" Post-Upgrade Lag

This can increase rebalances, overload databases/remote APIs, and complicate processing order. Measure bottlenecks and partition counts first.

### 26.11. Ignoring JDK/TLS

An old JDK runtime causes `UnsupportedClassVersionError`; TLS handshakes can fail due to cipher/truststore changes. Diagnose platform and security separately.

### 26.12. Not Preparing Rollback for New Schemas

If a new producer sends messages that old consumers cannot read, rolling back the old app will fail. Design backward/forward compatibility before rollout.

## 27. Hands-On Exercise: Upgrading Spring Kafka in an Order System

Suppose a system receives orders via Kafka:

```text
orders-api
  |
  v
Topic: orders.events (6 partitions)
  |
  v
orders-consumer-service
  +-- @KafkaListener
  +-- JSON deserialization
  +-- validates business event
  +-- writes PostgreSQL
  +-- DefaultErrorHandler
  +-- DeadLetterPublishingRecoverer -> orders.events.DLT
  |
  v
Business processing result
```

The organization wants to upgrade Spring Boot/Spring Kafka and the Kafka client, but in the initial phase the Kafka broker is not upgraded yet. The consumer service runs multiple replicas sharing the same `group.id`.

### Part A – Map Dependencies

1. Record current/target Java, Boot, Framework, Spring Kafka, Kafka client, and Kafka broker versions.
2. Run `dependencyInsight` or `dependency:tree` on the deployed module.
3. Identify `spring-kafka-test` and JSON/schema dependencies.
4. Document Kafka client properties affecting retry, commit, group protocol, and transactions.
5. Read release notes/migration docs for the exact versions being upgraded.

### Part B – Build Compatibility Matrix

1. Current application with current broker.
2. Target application with current broker.
3. Current application with target broker if the cluster plan includes this stage.
4. Target application with target broker.
5. Old/new consumer replicas in the same group during rolling deployment.
6. Explicitly mark any combination that is unsupported per official docs rather than assuming it can run.

### Part C – Data and Failure Testing

1. Send a valid JSON order and assert it is written once.
2. Send malformed-schema JSON and assert it goes through the error handler/DLT per policy.
3. Send old data within the retention window and assert the new consumer can read it.
4. Send a new schema and assert the old consumer can read it if rollback requires it.
5. Trigger a database failure after the listener receives a message; assert redelivery and idempotency.
6. Pause one replica mid-processing and confirm group rebalance does not lose records.
7. Test shutdown/drain and startup of a new replica.
8. Inject broker connection disruption and measure recovery and lag.

### Part D – Release Gates

Define example release conditions:

- Zero unresolved classpath/API errors.
- All required compatibility tests pass.
- No abnormal increase in DLT/deserialization error rate.
- Consumer lag returns to baseline after rollout.
- Zero out-of-contract duplicate side effects.
- Rollback plan verified against messages produced by the new producer.
- Alerts in place for rebalance storms, transaction aborts, and retry/DLT backlogs.
- Snapshot recorded of resolved dependencies and deployed versions.

### Self-Assessment Questions

- Why should the Spring Kafka version and `kafka-clients` version not be chosen independently at random?
- Why can an old Kafka broker and a new client connect yet a new feature still fail?
- Is seeing one message received via Embedded Kafka enough to conclude a production upgrade is safe?
- Which compatibility layer does a `NoSuchMethodError` point you to inspect?
- Why must you test old consumers reading messages sent by a new producer before rolling back?
- Does changing `max.poll.interval.ms` fix a listener making unbounded HTTP calls?
- Do Kafka transactions guarantee rolling back database and remote HTTP side effects?
- When mixed-version consumers share a group, which signals must be monitored?
- Why must `spring-kafka-test` also be checked when upgrading runtime dependencies?
- When should feature level/protocol upgrades be separated from upgrading application JARs?

## 28. References

- [Spring for Apache Kafka – Reference Documentation](https://docs.spring.io/spring-kafka/reference/): listener containers, producers, consumers, error handling, transactions, and testing.
- [Spring for Apache Kafka – Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html): changes between versions and migration notes.
- [Spring for Apache Kafka – Spring Boot Integration](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html): configuring `@KafkaListener` and listener containers.
- [Spring for Apache Kafka – Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): Kafka transactions and limitations when coordinating other resources.
- [Spring for Apache Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): error handlers, recoverers, and DLT.
- [Spring for Apache Kafka – Testing](https://docs.spring.io/spring-kafka/reference/testing.html): Embedded Kafka and integration test utilities.
- [Spring Boot Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html): dependency versions managed by the Spring Boot line in use.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): clients, brokers, protocol, security, and upgrade guidance.
- [Apache Kafka Protocol Guide](https://kafka.apache.org/protocol.html): API versioning and the Kafka wire protocol.
- [Apache Kafka Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): polling, groups, assignment, and consumer properties.
- [Apache Kafka Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs): idempotence, delivery timeouts, and producer properties.
- [Testcontainers Kafka Module](https://java.testcontainers.org/modules/kafka/): integration testing against specific broker versions.

