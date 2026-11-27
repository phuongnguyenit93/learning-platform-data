# Reading Version-Appropriate Documentation and the Spring Cloud Compatibility Matrix

When learning and upgrading Spring Cloud Stream, errors often do not come from Java syntax, but from applying documentation from **another Spring generation** to the running dependencies. A `@StreamListener` example from an older Spring Cloud Stream version cannot be treated as standard guidance for a project using the `Supplier`/`Function`/`Consumer` functional model. Similarly, a binder property or API from Spring Boot 4 does not automatically exist in a Boot 3 project.

To understand accurately how to configure bindings for Kafka, RabbitMQ, or Pulsar, you need to identify the **Spring Boot version**, **Spring Cloud release train**, **Spring Cloud Stream/binder**, and **underlying broker libraries**. Only then can you select the right reference page, release notes, migration guide, and API Javadoc. This lesson presents the lookup workflow, Maven/Gradle examples, how to inspect resolved dependencies, and a verified upgrade plan.

> **Reference point:** The release versions listed in the table below were cross-checked against official announcements as of **November 24, 2026**. Support status and patch releases may change. When deploying at another time, re-check the Spring Cloud project page, individual project pages, and release notes rather than treating the table in this lesson as a permanent support commitment.

## 1. Why is a "Spring version" not just a single number?

A Spring Cloud Stream application has multiple layers:

~~~mermaid
flowchart TD
    A[Java / Gradle / Maven] --> B[Spring Boot]
    B --> C[Spring Cloud release train BOM]
    C --> D[Spring Cloud Stream + Function]
    D --> E[Kafka Binder / Rabbit Binder / Kafka Streams Binder]
    E --> F[Spring Kafka / Spring AMQP / Kafka Streams / Pulsar client]
    F --> G[Kafka / RabbitMQ / Pulsar broker]
~~~

Each layer has its own release schedule and compatibility requirements. For example, in a project you might see:

| Name/version | Role |
|---|---|
| Spring Boot `4.2.0` | Foundation for auto-configuration, lifecycle, Actuator, and dependency management |
| Spring Cloud `2026.0.0` | Release train/BOM grouping compatible Spring Cloud versions |
| Spring Cloud Stream `5.1.0` | Binding and functional programming framework for message-driven apps |
| Kafka binder `5.1.0` | Module integrating Spring Cloud Stream with Kafka, managed by the train |
| Kafka client / Spring Kafka | Underlying Kafka connection and processing libraries, with their own versions |
| Kafka broker | External service outside the application; requires checking client/protocol compatibility |

Do not assume "Spring Cloud 2026.0 means Spring Cloud Stream 2026.0". Spring Cloud uses **calendar versioning** for release trains, while projects like Spring Cloud Stream have their own versioning sequence. A single train can contain multiple projects with different major version numbers.

## 2. Spring Boot — Spring Cloud — Stream compatibility matrix

According to the Spring Cloud matrix and official release announcements:

| Spring Boot | Spring Cloud release train | Spring Cloud Stream | Notes |
|---|---|---|---|
| **4.2.0** | **2026.0.0 — Paddington** | **5.1.0** | GA on November 20, 2026 |
| **4.0.x / 4.1.x** | **2025.1.x — Oakwood** | **5.0.x** | Boot 4.1.x supported starting from compatible service releases; `2025.1.5` confirms both lines |
| **3.5.x** | **2025.0.x — Northfields** | **4.3.x** | Check support/EOL before using |
| **3.4.x** | **2024.0.x — Moorgate** | **4.2.x** | Older branch, check support/EOL |
| **3.2.x / 3.3.x** | **2023.0.x — Leyton** | **4.1.x** | Boot 3.3.x supported starting from compatible service releases |

This is a **branch-level** table, not a guarantee that every patch combination within the same branch is compatible. For instance, a newer service release might only add support for a Boot patch/minor version or fix issues introduced after an upgrade. For production, you must verify the **exact version pair**, not just look at the first two numbers.

Trains marked as having reached end of open-source support on the project page may still exist on Maven Central and have reference documentation. **The fact that an artifact can be downloaded does not mean it is still maintained or receives security fixes.** For commercially supported environments, consult your organization's separate policies and entitlements.

## 3. Release train vs. individual library version

Spring Cloud follows a format similar to `YYYY.MINOR.MICRO`, for example:

~~~text
2026.0.0   Spring Cloud release train (Paddington)
5.1.0      Spring Cloud Stream released in the above train
4.2.0      Spring Boot version compatible with the train
~~~

Within a release train:

- `2026` is the year in the train name, **not the major semantic version** of a project.
- `.0` identifies the train line within that year; there may also be a `.1` train in the same year.
- The trailing `.0` indicates the specific release of the train; releases like `2025.1.5` are service releases with fixes/updates.
- Names like *Paddington*, *Oakwood*, and *Northfields* help identify the line, but must not be used in place of Maven coordinates.

Each module still publishes artifacts under its own version. The `org.springframework.cloud:spring-cloud-dependencies` BOM defines the coordinated versions published by Spring. Manually setting a Spring Cloud Stream version different from the BOM can pull in incompatible versions of Spring Cloud Function, Commons, or Spring Integration.

A safe rule: **choose Boot first → choose the compatible Cloud release train → use the BOM → verify the modules that the BOM resolves**.

## 4. Which sources are trustworthy when reading documentation?

Prioritize in the following order:

1. **Spring Cloud project page**: Boot ↔ release train matrix and support lifecycle links.
2. **Spring Cloud release announcement/release notes**: confirms newly supported patch pairs, which projects were upgraded, breaking changes, and security fixes.
3. **Spring Cloud Train Reference**: check which versions the release train brings individual projects to.
4. **Version-selected Spring Cloud Stream Reference**: how to configure functional bindings, Kafka/Rabbit/Kafka Streams binders, retry/DLQ, partitioning, and testing.
5. **Reference/Javadoc of lower-level libraries**: Spring Kafka, Spring AMQP, Apache Kafka/Pulsar APIs.
6. **Source code, changelog, issues/PRs, and community articles**: use only as supplementary material and verify the exact tag/version; never prioritize over official documentation.

Note that a project page's overview table may update more slowly than the GA announcement. For example, Spring Cloud `2026.0.0` was announced on November 20, 2026 with Spring Boot `4.2.0` and Stream `5.1.0`. If the overview table has not yet displayed the new row, use the release announcement and the corresponding Train Reference page to verify, then re-check once the table is updated.

## 5. Do not read the wrong "current" or "latest" page

Spring documentation pages usually have a version selector, including **Stable**, **Preview**, **Snapshot**, and older versions. A URL without a pinned version may redirect to the latest stable version at the time it is opened.

Example starting points:

~~~text
Spring Cloud Stream 4.3:
https://docs.spring.io/spring-cloud-stream/reference/4.3/index.html

Spring Cloud Stream 5.0:
https://docs.spring.io/spring-cloud-stream/reference/5.0/index.html

Spring Cloud Train Reference:
https://docs.spring.io/spring-cloud-release/reference/index.html
~~~

For Spring Cloud Stream `5.1.0`, navigate from the Spring Cloud Train `2026.0.0` page and select the documentation link for `spring-cloud-stream 5.1.0`. Do not assume that a URL constructed manually from a version number exists or has updated content; verify the version header displayed at the top of the page.

Before using an example, record:

- The project name and **version displayed on the page**.
- The URL path and corresponding branch/tag.
- The Spring Boot/Cloud version in the project you are studying.
- The Stable/Preview/Snapshot status.
- The release notes announcement date or build release date.

A snippet taken from version `4.3` may differ from `5.0` or `5.1` even when the guide section path looks the same. Conversely, many APIs and properties remain unchanged; verify rather than assuming everything is breaking.

## 6. Example: finding the right documentation for Kafka Binder

Suppose an application has:

~~~text
Spring Boot          3.5.x
Spring Cloud         2025.0.x
Spring Cloud Stream  4.3.x
Binder               kafka
~~~

Documentation lookup workflow:

1. Open the corresponding Spring Cloud release train section and confirm Boot `3.5.x` belongs to train `2025.0.x`.
2. Open the **Spring Cloud Stream 4.3.x** reference.
3. Select the **Kafka Binder** section, not **Kafka Streams Binder** by mistake.
4. Look up consumer/producer properties in the configuration options of that same version.
5. Check the Javadoc of Spring Kafka and Kafka clients **for the resolved version** if using low-level APIs.
6. Write tests to send and receive with a Kafka broker, verifying binding names, groups, keys/headers, and retry/DLQ.

If an example mentions `KStream`, `KTable`, `StreamsBuilder`, or `application.id`, it may be an example for the **Kafka Streams Binder** rather than the standard message-channel Kafka Binder receiving `Consumer<Message<T>>`. Using the wrong one leads to misconfiguration even though both sections contain the word "Kafka".

For RabbitMQ, choose the **RabbitMQ Binder** section matching the Stream version. For Pulsar, check both whether the Pulsar binder module belongs to the supported Stream version and the release notes of Spring for Apache Pulsar/Pulsar client. Do not assume every third-party binder is managed by the Spring Cloud BOM.

## 7. Using the Spring Cloud BOM in Maven

For the pair announced on November 20, 2026, a minimal Maven example:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>order-events</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2026.0.0</spring-cloud.version>
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

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-stream</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-stream-binder-kafka</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**Key point:** Do not manually declare versions for `spring-cloud-stream` and `spring-cloud-stream-binder-kafka`. The Spring Cloud BOM manages them according to the chosen train; the Spring Boot parent/BOM manages most foundational dependencies.

`java.version=21` is an illustrative choice for the project, not a conclusion that all Spring Boot versions require Java 21. For another train, look up the Java baseline, Gradle/Maven requirements, and container runtime in the corresponding Spring Boot reference.

If using Spring Boot with another parent, you can import `spring-boot-dependencies` in `dependencyManagement` instead of the parent, but you must manage plugins and BOM order appropriately. Do not mix dependency management from two different Spring Cloud trains in the same module.

## 8. Using the BOM in Gradle Kotlin DSL

An example `build.gradle.kts` using the Spring Boot Gradle plugin and dependency-management plugin:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.2.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

repositories {
    mavenCentral()
}

val springCloudVersion = "2026.0.0"

dependencyManagement {
    imports {
        mavenBom("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion")
    }
}

dependencies {
    implementation("org.springframework.cloud:spring-cloud-stream")
    implementation("org.springframework.cloud:spring-cloud-stream-binder-kafka")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

This is one **approach** to managing versions. Gradle also supports BOMs via `platform(...)` and native dependency constraints. Choose a consistent strategy; avoid importing multiple BOMs through different mechanisms while arbitrarily overriding project versions.

When upgrading within the same release train, update the BOM version in one place and inspect the dependency graph. When switching trains (e.g., `2025.1.x` to `2026.0.0`), upgrade both Boot and Cloud according to the matrix, rather than changing only one of the two.

## 9. Declared version vs. actually resolved version

`pom.xml` or `build.gradle.kts` describes what you intend, but dependency resolution may select different versions due to:

- Transitive dependencies from binders, starters, or third-party libraries.
- `dependencyManagement`, BOM import order, or Gradle platform constraints.
- Version overrides in parent or other modules.
- Forced versions, resolution strategies, or dependency substitutions.
- A direct dependency declaring a version outside the BOM.
- A third-party library bringing in old Spring APIs or a shaded Kafka client.

To know what **runtime actually uses**, run on your own project:

~~~bash
# Gradle, illustrative commands only; run when you have an actual project.
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-stream --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
~~~

With Maven:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

In CI, store the dependency tree or SBOM of the released artifact. When investigating bugs, compare the running release with the resolution result instead of only looking at the `springCloudVersion` variable in source.

Do not run those commands on a repository outside your authorized scope; in this lesson they are merely operational examples for learners.

## 10. Checking the Spring Cloud Compatibility Verifier

Spring Cloud Commons has a `CompatibilityVerifier` mechanism to detect certain incompatible combinations of Spring Boot and Cloud at application startup. When enabled and encountering a Boot version outside the accepted range, the application can stop and display a message about the version pair.

Properties to know:

~~~yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
      # Allowed list, illustrative only; do not arbitrarily override to force startup.
      # compatible-boot-versions:
      #   - 4.2.x
~~~

**Important:** the default of `spring.cloud.compatibility-verifier.enabled` can differ across Spring Cloud Commons lines; configuration references of some current versions list the default as `false`. Therefore, you cannot rely solely on successful application startup to confirm the matrix is valid. Check the exact configuration properties page and dependency sources of the resolved version.

Do not disable the verifier or manually add `compatible-boot-versions` just to bypass an incompatibility error. This property only changes the check step; it does **not** make an invalid dependency combination supported. Re-check the release train table, BOM, and release notes before changing configuration.

## 11. Distinguishing binder versions from broker versions

Spring Cloud Stream has different binders:

| Binder | Java module to read | Key runtime components |
|---|---|---|
| Kafka message-channel binder | `spring-cloud-stream-binder-kafka` | Spring Kafka, Kafka client, Kafka brokers |
| Kafka Streams binder | `spring-cloud-stream-binder-kafka-streams` | Kafka Streams library, state store, broker/partition |
| RabbitMQ binder | `spring-cloud-stream-binder-rabbit` | Spring AMQP, RabbitMQ Java client, RabbitMQ server |
| Pulsar binder | Pulsar binder module matching the Stream line | Pulsar client, schema/serialization, Pulsar broker |

Choosing the right Spring Cloud train is only a **necessary condition**, not sufficient to guarantee compatibility with production brokers. You also need to check:

- Minimum and maximum protocol/broker versions supported by the Java client.
- Authentication: SASL_SSL, TLS, OAuth, SCRAM, truststore/certificate.
- Kafka `min.insync.replicas`, transactions, idempotence, and admin topic provisioning.
- Kafka Streams state directory, RocksDB, changelog, repartition, serde, and topology upgrades.
- RabbitMQ quorum/classic queues, publisher confirms, dead-letter exchanges, and queue arguments.
- Pulsar subscriptions, acknowledgements, native DLQ, schema registry, and client version.
- Whether third-party binders have a release corresponding to the train.

Do not infer the Kafka broker version from the Spring Cloud version. Clients and brokers have separate compatibility policies; consult Apache Kafka or your broker vendor's documentation for the exact running version.

## 12. Reading the right type of documentation: Stream, Function, or Kafka Streams?

An example in Spring documentation may come from different layers:

| Seen in example | Documentation to check |
|---|---|
| `Consumer<Message<Order>>`, `StreamBridge`, `spring.cloud.stream.bindings` | Spring Cloud Stream core and the relevant binder |
| `Function<KStream<K,V>, KStream<K,R>>` | Spring Cloud Stream Kafka Streams Binder and Apache Kafka Streams DSL |
| `spring.cloud.function.definition` or function composition | Spring Cloud Function + Spring Cloud Stream of the same version |
| `@KafkaListener`, `Acknowledgment`, `KafkaTemplate` | Spring for Apache Kafka |
| `@RabbitListener`, `RabbitTemplate` | Spring AMQP |
| Pulsar acknowledgement/subscription | Spring for Apache Pulsar and the specific binder |
| `@StreamListener`, `@EnableBinding` | Legacy Spring Cloud Stream model documentation; requires migration cross-check |

Do not copy `@KafkaListener` into a sample that specifically asks for the functional binder while ignoring the different abstraction layers. Also do not conclude that `StreamBridge.send` is completely identical to sending with `KafkaTemplate`: the two APIs have different lifecycles, error propagation, and configurations.

When reading code on forums, ask "Which **version, programming model, and binder** is this example targeting?" before using it.

## 13. Signs you are using the wrong documentation

Easy-to-spot signals:

- An import does not exist in the active dependency graph.
- The IDE cannot find the `@EnableBinding` annotation or `Source`/`Sink` interfaces in new code.
- A binder property is documented in a guide, but configuration metadata does not recognize it.
- An example uses a class/method that is deprecated or moved to another package.
- Documentation binding names use `input`/`output`, whereas the current functional model generates `processOrder-in-0`/`processOrder-out-0`.
- A blog post uses Spring Boot 2.x while the project uses Boot 4.x.
- The Spring Cloud release train is on a new major version while the old sample specifies separate Maven versions per module.
- A Kafka Streams example uses the DSL API while the project only has the message-channel binder.

Do not fix imports one by one by guessing. First determine the version and BOM, then switch to the matching reference line and check migration notes. If an API has been removed, you need to change the implementation approach, not just rename packages.

## 14. Reading release notes before switching trains

Whenever upgrading from one Cloud line to another, read **all** of:

1. Release notes for the new Spring Boot and the migration guide from the old Boot.
2. Release notes for the target Spring Cloud release train.
3. Spring Cloud Stream release notes and the guide for the binder in use.
4. Spring Cloud Function/Commons if the app uses function routing/composition.
5. Spring Kafka, Spring AMQP, Spring Pulsar, and Kafka Streams if direct APIs are used.
6. Security advisories/CVEs related to modules actually present on the classpath.
7. Deprecations/removals, minimum JDK/Gradle/Maven, renamed configuration properties, and changed default behaviors.

For example, moving from **Boot 3.5 / Cloud 2025.0 / Stream 4.3** to **Boot 4.2 / Cloud 2026.0 / Stream 5.1** spans multiple generations of changes. Do not treat it as a patch upgrade.

The `2026.0.0` announcement includes notable changes worth reading before updating, such as Spring Cloud Bus moving into Spring Cloud Stream, and deprecation notices for some components/reactive Kafka binder or Schema Registry. These are items to evaluate if your project uses them, not reasons to automatically remove every similarly named dependency.

## 15. Creating an impact assessment table for a running project

A useful template before editing build files:

| Item | Current | Target | Questions to verify |
|---|---|---|---|
| Java runtime | 17/21 | Per target Boot | Are the build and runtime JDK/images compatible? |
| Spring Boot | 3.5.x | 4.2.x | Are there breaking changes in auto-config and starters? |
| Spring Cloud | 2025.0.x | 2026.0.x | Which release train supports the target Boot? |
| Spring Cloud Stream | 4.3.x | 5.1.x | Have function bindings, content types, or error handling changed? |
| Kafka binder | 4.3.x | 5.1.x | Have producer/consumer options changed? |
| Kafka Streams binder | If present | Matches train | Have state stores, serdes, restore, or EOS changed? |
| Broker | Kafka/Rabbit/Pulsar | Keep or upgrade | Client protocol, TLS/SASL, schema compatibility? |
| Observability | Current metrics/logs | No signal loss | Have health endpoints or Micrometer/Actuator changed? |
| Deployment | Container/Kubernetes | Rolling rollout | How are probes, SIGTERM, CPU/memory, and rollback handled? |

Fill in actual version numbers from `dependency:tree`/`dependencyInsight`. For applications with multiple binders or partner-maintained binders, add a separate row for each binder and check the vendor's compatibility matrix.

## 16. A verified upgrade workflow

A practical workflow:

~~~mermaid
flowchart TD
    A[List actual dependencies] --> B[Choose official Boot + Cloud train]
    B --> C[Select matching docs and release notes]
    C --> D[Update BOM/plugin and code]
    D --> E[Compile + unit + Test Binder]
    E --> F[Integration test with real broker]
    F --> G{Results and semantics pass?}
    G -->|No| H[Analyze dependencies / fix config]
    H --> D
    G -->|Yes| I[Canary and observe lag/DLQ]
    I --> J[Rollout with rollback plan]
~~~

Steps to execute in order:

1. Freeze the running baseline: versions, manifest/dependency tree, schemas, and binder configuration.
2. Verify the target is still maintained and compatible across Boot/Cloud/Stream.
3. Update the BOM and Spring Boot plugin/parent to the target pair.
4. Verify JDK/toolchain and dependency resolution before editing code.
5. Update changed APIs/properties per the migration guide; avoid arbitrary transitive overrides.
6. Run unit tests, Test Binder tests, and then send/receive tests against a real broker.
7. Verify restart behavior, retry/DLQ, consumer group offsets, and state restore if using Kafka Streams.
8. Build the container image, scan for CVEs, run a canary, and monitor business outcomes.
9. Perform a bounded rollout with a rollback plan and schema compatibility review.

A dependency combination that starts up successfully but alters retry behavior or offset commits can still break business requirements; you must test behavior, not just compilation.

## 17. Testing matrix specific to Spring Cloud Stream

| Scenario | Reason to verify after upgrade |
|---|---|
| Periodic `Supplier` emission | Are the poller and producer conversion still right? |
| `Function` payload transformation | Are content type, function binding names, and routing preserved? |
| `Consumer` with group | Are offset/ack mode and consumer assignment appropriate? |
| `StreamBridge` sending to dynamic destinations | Have binder name, caching, or output binding behavior changed? |
| Kafka partition key/header | Are ordering and partition assignment still accurate? |
| Kafka retry/DLQ | Are failed messages retried the expected number of times and routed to the right DLQ? |
| RabbitMQ queue/DLX | Have queue arguments or redelivery changed? |
| Pulsar subscription/ack | Do broker/client and binder semantics still align? |
| Kafka Streams aggregate/window/join | Store names, changelogs, serdes, state restore, and interactive queries? |
| Graceful restart | No message loss, safe duplicate handling? |
| Multi-instance deployment | Do rebalance, readiness, and backlog recovery meet SLOs? |
| Schema evolution | Can old producer + new consumer, and new producer + old consumer both read? |

Depending on the project you can omit irrelevant rows, but you must test both the *happy path* and the *error path*. Tests requiring a real broker cannot be completely replaced by the in-JVM Spring Integration Test Binder.

## 18. Troubleshooting runtime errors after switching trains

| Symptom | Common cause | How to verify |
|---|---|---|
| App reports Boot/Cloud incompatibility | Wrong release train or patch combination chosen | Cross-check matrix and announcement, inspect effective BOM |
| `NoSuchMethodError` / `ClassNotFoundException` | Transitive library overridden or major API changed | Check runtimeClasspath and dependency tree |
| Binder bean not created | Missing binder artifact, auto-configuration, or version mismatch | Check dependencies, conditions report, and binder name |
| Property no longer takes effect | Property name/default changed across versions | Open version-matched config options and configuration metadata |
| Consumer does not read messages | Binding name/destination/group differs from before | Compare binding, topic, group offsets, and logs |
| Kafka Streams restore fails | Store/changelog/serde/topology compatibility issue | Check application.id, state.dir, changelog, and migration guide |
| Serialization error | Schema/client mismatch | Inspect payload bytes, serializer, contentType, and schema ID |
| Retry/DLQ behavior changed | Binder/container error handler config changed | Integration test with a poison message and count attempts |
| Container image behaves differently from local | JDK/runtime or environment mismatch | Check image Java version, env, secrets, and advertised listeners |

Do not fix `NoSuchMethodError` by randomly adding a new JAR to the classpath. First identify which class is loaded from which dependency, its resolved version, and why it was brought in. Then align dependencies via the BOM or upgrade the paired counterpart.

## 19. Scenario: blog post uses Boot 2 while project uses Boot 4

Suppose a learner finds the example:

~~~java
// Historical example only, not recommended for new projects.
@StreamListener(Sink.INPUT)
public void consume(String payload) {
    System.out.println(payload);
}
~~~

With the functional model of modern Spring Cloud Stream, consult your project's version documentation and write:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConsumerConfiguration {

    @Bean
    Consumer<String> processOrder() {
        return payload -> System.out.println(payload);
    }
}
~~~

The default binding is `processOrder-in-0`:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
~~~

The key takeaway is not just changing annotations: the binding model, function discovery, destination/group declaration, and dependencies are managed differently across generations. Properties from old examples must be re-verified in the version-matched reference.

## 20. Do not treat "latest" as an unconditional upgrade recommendation

Reading the latest documentation helps you learn about new features, but a production project must balance:

- Spring Boot/Cloud support timelines and organizational policies.
- Whether security fixes exist in a patch release within the **current train** or require switching trains.
- Whether third-party binders have compatible releases yet.
- Whether production brokers, schema registries, and client libraries are tested together.
- Canary capability, rollback readiness, and duplicate/event ordering control.
- Cost of changing Java, plugins, dependencies, Docker base images, and CI.

Do not pick a `-M`, `-RC`, or `-SNAPSHOT` pre-release for production simply because its link sits at the top of the docs. Conversely, staying on an unsupported train indefinitely also carries security risks. The goal is a **supported version that is compatible with the real system and verified by tests**.

## 21. Documentation lookup checklist before every change

- Identified the running Spring Boot version.
- Identified the Spring Cloud release train from the BOM/effective POM.
- Identified Spring Cloud Stream and each binder from resolved dependencies.
- Cross-checked the Boot/Cloud pair against the official matrix and specific patch release notes.
- Checked Java/toolchain, Maven/Gradle, runtime image, and broker versions.
- Selected the version-matched reference rather than relying solely on "current/latest" URLs.
- Distinguished the message-channel Kafka binder from the Kafka Streams binder.
- Verified whether the sample source uses the functional model or the legacy annotation model.
- Matched property names and default behaviors against the actual binder version.
- Read migration/deprecation/security notes for Boot, Cloud, Stream, and relevant clients.
- Checked whether third-party libraries/binders support the new train.
- Avoided overriding dependencies or disabling the compatibility verifier just to suppress errors.
- Executed unit, broker integration, restart/retry/DLQ, and schema compatibility tests.
- Prepared a canary, rollout, and rollback plan along with business metrics.
- Recorded versions/docs URLs/dependency graphs so teammates can reproduce the results.

## Summary

Reading version-appropriate documentation is the first step of any Spring Cloud Stream change. Choose the **Spring Boot version first**, identify the **compatible Spring Cloud release train**, manage Spring Cloud Stream and binders with the **BOM**, and then read the **reference and release notes of that exact version**. The release train matrix only solves compatibility at the Spring layer; Kafka/RabbitMQ/Pulsar brokers, schemas, clients, and third-party binders still need separate verification.

As of November 24, 2026, the latest announced example is Spring Boot `4.2.0`, Spring Cloud `2026.0.0`, and Spring Cloud Stream `5.1.0`; while Spring Cloud `2025.1.5` is the train for Spring Boot `4.0.x/4.1.x`. These pairs are not an automatic recommendation to move production to the newest release: upgrade decisions must be based on support status, resolved dependencies, API changes, and end-to-end data testing.

## References

- [Spring Cloud project — Spring Boot / Spring Cloud release train matrix](https://spring.io/projects/spring-cloud)
- [Spring Cloud Train Reference — projects and versions in the train](https://docs.spring.io/spring-cloud-release/reference/index.html)
- [Spring Cloud 2026.0.0 / Paddington GA, Nov 20, 2026](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud 2025.1.5 / Oakwood, Nov 20, 2026](https://spring.io/blog/2026/11/20/spring-cloud-2025-1-5-has-been-released/)
- [Spring Cloud Stream 5.0 reference](https://docs.spring.io/spring-cloud-stream/reference/5.0/index.html)
- [Spring Cloud Stream 4.3 reference](https://docs.spring.io/spring-cloud-stream/reference/4.3/index.html)
- [Spring Cloud Stream project — binders and release trains](https://spring.io/projects/spring-cloud-stream)
- [Spring Cloud release — supported versions and support policy](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
- [Spring Cloud Commons — compatibility verifier properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Boot project — reference and support](https://spring.io/projects/spring-boot)
