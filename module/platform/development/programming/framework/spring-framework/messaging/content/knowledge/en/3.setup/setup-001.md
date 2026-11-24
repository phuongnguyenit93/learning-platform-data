# Identifying Compatible Versions of Spring Framework, Java, and Protocol Libraries

## Objectives

When adding messaging to a Spring application, you need to choose a set of versions that can compile, run, and communicate with the target system together. Compatibility cannot be concluded simply by looking at the Spring Framework major version number. You must check the JDK, Spring modules, integration projects, protocol Java client, and broker/provider version.

After this lesson, you will be able to:

- Identify the JDK used for building and the actual JDK in the runtime environment.
- Choose the right Spring Framework generation based on Java and Jakarta namespace requirements.
- Look up compatible versions of Spring Integration, Spring AMQP, Spring for Apache Kafka, and Spring JMS.
- Manage dependencies with a BOM to prevent Spring modules from having mismatched versions.
- Inspect the dependency graph and verify connectivity with a real broker.

## 1. Compatibility Is a Stack of Multiple Layers

A messaging application typically has the following version layers:

| Layer | Example | What to check |
|---|---|---|
| Java runtime | JDK 17, 21, or 25 | Minimum JDK required by all libraries; JDK installed on the machine/container running the application. |
| Java compiler target | `--release 17` | Bytecode and Java APIs that the source code is allowed to use. |
| Spring Framework | `spring-core`, `spring-messaging`, `spring-jms`, `spring-websocket` | Framework version, JDK baseline, and Jakarta EE namespace. |
| Spring integration project | Spring Integration, Spring AMQP, Spring for Apache Kafka | Which Spring Framework version the integration project version supports. |
| Protocol client | RabbitMQ `amqp-client`, Kafka `kafka-clients`, JMS provider client | Minimum Java client version and APIs/protocols supported by the client. |
| Server/broker | RabbitMQ, Apache Kafka, ActiveMQ Artemis | Which protocols, features, and client versions the broker supports. |
| Build/runtime platform | Maven, Gradle, Tomcat, application server, container image | Whether the build tool and deployment environment meet the library requirements. |

Distinguish between three concepts:

- **Minimum requirement:** the lowest level published in the project documentation. This is a necessary condition, and does not automatically prove that every combination above that level has been tested.
- **Tested/recommended combination:** a combination that the project or Spring Boot release train declares as supported and tested.
- **Wire-protocol compatibility:** the ability of the Java client and broker to exchange messages according to the protocol. This is independent of whether the Java classes are compatible at compile time.

For example, `spring-kafka` may be compatible with a Spring Framework version, yet the Kafka broker still needs to satisfy Apache Kafka's client/broker matrix. Similarly, `spring-rabbit` uses the RabbitMQ Java client; the Spring AMQP version is not the RabbitMQ server version.

## 2. Choosing a Spring Framework Generation by JDK and Namespace

Reference milestones from the official Spring Framework support page as of November 7, 2026:

| Spring Framework | Published JDK range | Jakarta/Java EE platform | Community support status |
|---|---|---|---|
| 5.3.x | JDK 8–21 | Java EE 7–8, `javax.*` namespace | Open-source support ended August 2024; commercial support options remain. |
| 6.2.x | JDK 17–25 | Jakarta EE 9–10, `jakarta.*` namespace | Open-source support ended June 2026; commercial long-term support options available. |
| 7.0.x | JDK 17–25+ | Jakarta EE 11–12, `jakarta.*` namespace | Current production generation at the time of writing. |

Spring Framework 6.0 and later require Java 17+. Framework 7.0 keeps the minimum JDK at 17, while recommending JDK 25 for production. The LTS JDK versions tested and supported by Spring include 17, 21, and 25; intermediate JDK releases may only receive best-effort support.

Important consequences:

- Applications that still depend on `javax.jms.*`, `javax.servlet.*`, or legacy Java EE APIs need careful evaluation before migrating to Spring 6/7.
- Spring 6/7 uses the `jakarta.*` namespace. Changing dependencies without updating imports and provider APIs can cause compilation errors or class loading failures.
- Spring Framework 6.2 can still run on JDK 17, but at the time of writing it has reached the end of open-source support. For new projects, prefer a branch that is still supported.
- Spring Framework 7.1 is in preview/release candidate stage at the time of writing. Do not use preview releases for production unless you intentionally accept pre-GA release risks.

Refer to [Spring Framework Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions) and [Spring Framework Overview](https://docs.spring.io/spring-framework/reference/overview.html).

## 3. Compatibility Milestones for Messaging Libraries

Spring projects have their own release schedules. The version numbers of Spring Integration, Spring AMQP, and Spring Kafka do not need to match the Spring Framework version number. Use the matrix of each integration project itself.

### Example Version Set from the Current Generation

The versions below are a reference snapshot as of November 7, 2026, not a fixed rule for every project:

| Component | Illustrative version | Key compatibility requirements |
|---|---:|---|
| Java | 17 or higher | Baseline for Framework 7.0 and the integration lines listed below. |
| Spring Framework | 7.0.10 | JDK 17+; Jakarta EE 11 baseline. |
| Spring Integration | 7.1.2 | Java 17+ and Spring Framework 7.0 or higher. |
| Spring AMQP / `spring-rabbit` | 4.1.2 | Minimum Spring Framework 7.0.0; minimum RabbitMQ Java client `amqp-client` 5.28.0. |
| Spring for Apache Kafka | 4.1.2 | Spring Framework 7.0.0; minimum Java 17; compatible Kafka client line is 4.2.x. |
| Spring Boot (if used) | 4.1.2 | Use Boot's BOM to pull a dependency set managed by the release train. |

Notes when reading the table:

- Spring Integration 7.1.x requires Spring Framework 7.0 or higher. Therefore, Integration 7.1.x can be paired with Framework 7.0.x; do not assume the two minor numbers must be identical.
- Spring AMQP 4.1.x requires Spring Framework 7.0.0 or higher and `amqp-client` 5.28.0 or higher. If using RabbitMQ Streams, you also need to check `stream-client`; the Spring AMQP 4.1 documentation states a minimum of 1.5.0.
- The Spring for Apache Kafka 4.1.x matrix pairs with Kafka clients 4.2.x, Spring Boot 4.1.x, and Spring Integration for Apache Kafka 7.1.x. The Spring Kafka 4.1 quick tour documentation also confirms Spring Framework 7.0.0 and Java 17 as the baseline.
- These are library/client-side requirements. The Kafka or RabbitMQ broker version still has to be cross-checked against the broker's own matrix.

Sources: [Spring Integration requirements](https://docs.spring.io/spring-integration/reference/preface.html), [Spring AMQP compatibility](https://docs.spring.io/spring-amqp/reference/introduction/quick-tour.html), [Spring Kafka quick tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html), [Spring Kafka client compatibility matrix](https://spring.io/projects/spring-kafka), [Spring projects and release lines](https://spring.io/projects).

## 4. Checking by Protocol

### JMS

Spring JMS is a Spring Framework module that uses the JMS API provided by a provider.

- With Spring Framework 5.x, applications typically work with the `javax.jms.*` namespace and providers from the legacy Java EE generation.
- With Spring Framework 6.x/7.x, use the `jakarta.jms.*` namespace. Choose a JMS provider/client that provides the exact Jakarta Messaging API required by the framework.
- Check the provider's client version (for example ActiveMQ Artemis or another JMS provider), broker version, transaction mode, and the JMS features in use.
- Do not put both `javax.jms` and `jakarta.jms` APIs on the classpath at the same time expecting them to substitute for each other. Because the package names differ, they are two distinct Java types.

When upgrading from Spring 5 to Spring 6/7, `ClassNotFoundException: javax.jms...` or errors about missing `jakarta.jms...` classes usually indicate that the API/provider are not from the same generation.

### RabbitMQ via Spring AMQP

Components to cross-check:

1. Spring Framework.
2. Spring AMQP and the `spring-rabbit` module.
3. RabbitMQ Java client `com.rabbitmq:amqp-client`.
4. RabbitMQ server and the broker features in use.

Spring AMQP 4.1.2 requires Spring Framework 7.0.0 or higher and `amqp-client` 5.28.0 or higher. When using RabbitMQ Streams, also check `stream-client` according to the documentation of that exact Spring AMQP branch.

Do not upgrade `amqp-client` to a new major version on your own just because a new release is on Maven Central. Spring AMQP may depend on specific client APIs. Use the version supported by the Spring AMQP release train, then verify that the broker server supports the required protocols and features.

### Apache Kafka via Spring for Apache Kafka

Components to cross-check:

1. Spring Framework.
2. Spring for Apache Kafka (`spring-kafka`).
3. Apache Kafka Java client (`kafka-clients`).
4. Kafka broker and protocol/API version.
5. If using the Spring Integration Kafka adapter, also check the `spring-integration-kafka` version.

According to the Spring Kafka matrix, the 4.1.x branch is compatible with Kafka clients 4.2.x, Spring Boot 4.1.x, and Spring Integration for Apache Kafka 7.1.x. Do not mistake the Kafka broker version for the `kafka-clients` version: they are two different artifacts/products.

When changing the Kafka client, check Apache Kafka's client/broker compatibility matrix, the broker APIs used by the client, serializers/deserializers, authentication mechanisms, and TLS/SASL configuration. An application that compiles successfully does not yet prove that the client can connect to and use the production broker.

### WebSocket and STOMP

`spring-messaging` and `spring-websocket` are modules belonging to the same Spring Framework version; let the Framework BOM manage them together.

If using the built-in simple broker, it only supports a subset of STOMP commands and lacks the full feature set of a dedicated broker. If using a broker relay, the external broker must support STOMP and the features required by the application. Check STOMP version, heartbeat, acknowledgement, authentication, and TCP/TLS configuration.

Refer to [Spring WebSocket message flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html) and [external STOMP broker relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html).

## 5. Version Selection Workflow

Follow this order to avoid picking dependencies before knowing the runtime environment:

1. **Lock down the Java environment.** Record the JDK used on build machines, IDEs, CI, containers, and production. If production only has JDK 17, you cannot release bytecode requiring Java 21.
2. **Choose a supported Spring Framework branch.** Check the Java baseline, Jakarta EE namespace, support lifecycle, and removed APIs.
3. **Choose the Spring integration project.** Read the Requirements/Compatibility section of the exact Spring Integration, Spring AMQP, or Spring Kafka branch. Check both minimum Spring Framework and minimum Java.
4. **Choose the protocol client.** Check the client version required by the Spring library or managed by the release train. Do not pin a new client major version without confirmed compatibility.
5. **Check the broker/provider.** Cross-check the client/server matrix of RabbitMQ, Apache Kafka, or the JMS provider. Also check protocol, authentication, TLS, serializers, and features.
6. **Centralize version management.** If using Spring Boot, prefer Boot's BOM. If not using Boot, use the Spring Framework BOM for Framework modules and declare the release line of each integration project according to the official documentation.
7. **Inspect the resolved dependency graph.** Read the dependency tree and effective POM, not just directly declared versions.
8. **Build and run integration tests.** Run tests on the exact target JDK and connect to a broker of the same major/version planned for deployment.

## 6. Maven Example Without Spring Boot

The example below illustrates a set of versions following the Framework 7.0 generation as of November 7, 2026. It uses the Framework BOM to synchronize Spring Framework artifacts; Spring Integration, Spring AMQP, and Spring Kafka have separate release lines so they are declared separately.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>messaging-version-check</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>7.0.10</spring-framework.version>
        <spring-integration.version>7.1.2</spring-integration.version>
        <spring-amqp.version>4.1.2</spring-amqp.version>
        <spring-kafka.version>4.1.2</spring-kafka.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>${spring-framework.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>${spring-integration.version}</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.amqp</groupId>
            <artifactId>spring-rabbit</artifactId>
            <version>${spring-amqp.version}</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.kafka</groupId>
            <artifactId>spring-kafka</artifactId>
            <version>${spring-kafka.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

What this configuration means:

- `spring-framework-bom` manages synchronized versions for `spring-messaging`, `spring-core`, `spring-context`, and other Framework modules.
- Spring Integration, Spring AMQP, and Spring Kafka have their own release cadences. Do not assume the Framework BOM manages all artifacts belonging to those projects.
- The Java release version is 17. Even if built with JDK 21 or 25, the code is still compiled against Java 17 APIs/bytecode.
- The RabbitMQ and Kafka Java clients are typically pulled in transitively by the integration libraries. Check the actual resolved versions via the dependency tree before overriding.
- If also using `spring-integration-kafka`, pick the same Spring Integration 7.1.x release line and check the corresponding Spring Kafka matrix.

This is a dependency configuration example and does not replace verifying broker versions and running connectivity tests. When a project uses a different release train, replace the entire set of versions according to a verified matrix rather than changing individual numbers independently.

## 7. Example When Using Spring Boot

Spring Boot provides a dependency management BOM designed and tested with a specific set of Spring and third-party library versions. When using Boot, the standard safe approach is to declare starters without specifying individual versions:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
</dependencies>
~~~

Do not declare standalone versions for `spring-rabbit`, `spring-kafka`, `spring-core`, or Kafka/Rabbit clients when the BOM already manages them, unless there is a clear technical reason and it has been tested. Overriding can break alignment with the dependency set tested by that Boot version.

With Gradle, you can use Spring Boot's dependency management plugin or import the BOM using Gradle platform support. Example using native BOM support:

~~~kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.2"))

    implementation("org.springframework.boot:spring-boot-starter-amqp")
    implementation("org.springframework.boot:spring-boot-starter-kafka")
    implementation("org.springframework.boot:spring-boot-starter-integration")
}
~~~

Refer to [Spring Boot dependency management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html). If the project does not use Spring Boot, there is no need to add Boot just to get a BOM; you can manage the Framework BOM and each integration release line directly as in the previous Maven example.

## 8. Verifying the Actual JDK and Dependencies

The version declared in a POM is not necessarily the final version Maven selects. Transitive dependencies, dependency management, and version overrides can alter the outcome.

### Checking the JDK

~~~bash
java -version
javac -version
mvn -v
~~~

- `java -version` shows the Java runtime executing the `java` command in the shell.
- `javac -version` shows the compiler invoked from PATH.
- `mvn -v` shows the JDK that Maven is using.
- IDEs, CI, and containers may use a different JDK than the current shell. Check each environment.

In Maven, `maven.compiler.release` sets the target Java API and bytecode level. With Gradle, you can declare a toolchain and compiler release:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
~~~

If a library requires Java 17, setting target 17 will not make it run on Java 11. The runtime must still meet the library's baseline.

### Checking the Dependency Graph with Maven

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn dependency:tree -Dverbose
mvn clean verify
~~~

- Effective POM shows the versions after parent POMs, BOMs, and properties are applied.
- Dependency tree shows direct and transitive dependencies, including selected versions and omitted versions.
- `clean verify` checks compilation, tests, and verification phases configured in the project.

Focus on checking these artifact groups:

- `org.springframework` — Spring Framework.
- `org.springframework.integration` — Spring Integration.
- `org.springframework.amqp` — Spring AMQP.
- `org.springframework.kafka` — Spring for Apache Kafka.
- `org.apache.kafka` — Kafka Java client.
- `com.rabbitmq` — RabbitMQ Java client.
- `jakarta.jms` or `javax.jms` — JMS API.

### Checking with Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
./gradlew dependencyInsight --dependency amqp-client --configuration runtimeClasspath
./gradlew clean test
~~~

`dependencyInsight` helps identify which dependency requests a version, which version was selected, and why Gradle selected that version.

## 9. Testing Compatibility with the Broker/Provider

A successful build only proves that the source code and classpath can compile/link to a certain extent. To confirm the messaging version set, you need integration tests or smoke tests against an actual broker.

### With RabbitMQ

- Use the exact RabbitMQ server version planned for production.
- Verify the connection, TLS, username/password, or authentication mechanism in use.
- Publish a message, receive it, and verify the routing key, exchange, queue, and acknowledgement.
- If using RabbitMQ Streams, also check the stream plugin and the corresponding client library.

### With Kafka

- Use the broker version planned for production or an environment with the same major/API version.
- Verify the bootstrap connection, TLS/SASL, topic, partition, and consumer group.
- Send a record and read it back with a consumer; verify serializer/deserializer, key, headers, offset, and commit behavior.
- Cross-check Apache Kafka's client/broker compatibility matrix, especially during major upgrades.

### With JMS

- Use the exact provider and broker version to be deployed.
- Verify the API namespace (`jakarta.jms` vs `javax.jms`), connection factory, transaction, and acknowledgement mode.
- Test sending/receiving in both the success flow and rollback/retry flows if the application uses those features.

### With STOMP/WebSocket

- Verify that the broker supports STOMP and the required command versions.
- Test CONNECT, SUBSCRIBE, SEND, heartbeat, authentication, and reconnect.
- If the application relies on ACK/RECEIPT or clustering, do not treat the simple broker as an equivalent replacement for a full STOMP broker.

## 10. Common Signs of Incompatible Versions

| Error or symptom | Common cause | What to check |
|---|---|---|
| `UnsupportedClassVersionError` | Java runtime is lower than the bytecode level of the application or a dependency. | `java -version`, `mvn -v`, compiler release, and runtime JDK in the container. |
| `ClassNotFoundException` / `NoClassDefFoundError` | Missing dependency, wrong namespace, or library absent from the runtime classpath. | Dependency tree, excluded artifacts, and `javax.*`/`jakarta.*` differences. |
| `NoSuchMethodError` | Modules of the same library loaded at incompatible versions. | Effective POM, dependency tree, BOM, and dependency overrides. |
| `NoSuchFieldError` or `AbstractMethodError` | Binary API mismatch between caller and implementation. | Find which JAR the class comes from; align related modules. |
| Application starts but fails to connect to broker | Wrong endpoint, TLS/SASL, credentials, protocol, or broker version. | Connection logs, network, broker logs, and client configuration. |
| Kafka reports unsupported API/version or feature error | Client and broker do not share the required API/feature support level. | Kafka client/broker compatibility matrix and broker configuration. |
| RabbitMQ channel closed or broker rejects operation | Broker rejects protocol operation, permissions, or topology. | RabbitMQ logs, protocol version, permissions, exchange/queue declarations, and client docs. |
| JMS class not found | Provider pulls in `javax.jms` API while application expects `jakarta.jms`, or vice versa. | Provider client, API dependencies, and imports. |

Do not fix errors by forcing all dependencies to the latest version. First identify which class or client is causing the error, inspect the dependency graph, and cross-check the compatibility matrix of the corresponding release line.

## 11. Checklist Before Locking Versions

- [ ] Recorded the JDK on build machines, CI, IDEs, and production.
- [ ] Compiler release is not higher than the target runtime JDK.
- [ ] Spring Framework branch meets the Java baseline and has an appropriate support policy.
- [ ] `javax.*`/`jakarta.*` namespace matches the provider and container.
- [ ] Spring Integration / AMQP / Kafka release line supports the chosen Framework.
- [ ] Java protocol client meets the minimum version and release matrix of the adapter.
- [ ] Broker/provider supports the protocol and features the application needs.
- [ ] BOM or dependency management is used consistently; no unintended overrides exist.
- [ ] Dependency tree has no Spring Framework modules with mismatched versions.
- [ ] Build and tests run on the exact target JDK.
- [ ] Integration tests have sent and received messages through the broker/provider planned for production.
- [ ] Recorded versions in build/deployment documentation so future upgrades are reproducible.

## Key Takeaways

Choose versions in this order: **JDK runtime → Spring Framework → Spring integration library → protocol client → broker/provider**. Each layer has its own matrix. A BOM keeps dependencies within a release train consistent; the dependency tree shows which versions are actually loaded; integration tests verify the pipeline works with a real broker.

The version numbers in this lesson are a snapshot from November 7, 2026. Before every upgrade or new project, reopen the official documentation for the exact release line and check the latest matrix instead of copying patch versions verbatim.

## Official Documentation

- [Spring Framework Versions: JDK range, Jakarta EE level, and support status](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions)
- [Spring Framework Reference: Overview](https://docs.spring.io/spring-framework/reference/overview.html)
- [Spring Integration Reference: Requirements](https://docs.spring.io/spring-integration/reference/preface.html)
- [Spring AMQP Reference: Compatibility](https://docs.spring.io/spring-amqp/reference/introduction/quick-tour.html)
- [Spring for Apache Kafka: Compatibility matrix](https://spring.io/projects/spring-kafka)
- [Spring for Apache Kafka Reference: Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html)
- [Spring Boot: Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Apache Kafka: Compatibility Matrix](https://cwiki.apache.org/confluence/display/KAFKA/Compatibility+Matrix)
