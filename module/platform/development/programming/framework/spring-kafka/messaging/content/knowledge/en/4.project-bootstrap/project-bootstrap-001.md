# Choosing a Starter and Compatible Versions

When bootstrapping a Spring Kafka application, the first decision is not picking an arbitrary Kafka client version, but identifying the Spring platform in use and letting the related libraries follow a compatible version set. A project can compile successfully yet fail at runtime if Spring Boot, Spring Framework, Spring Kafka, the Kafka client, or testing libraries are mixed from incompatible version lines.

Spring Kafka provides `KafkaTemplate`, `@KafkaListener`, listener containers, and integrations with the Kafka client. Spring Boot adds auto-configuration and dependency management to reduce manual configuration. Choosing the right dependency and using the right version set helps the application start reliably, while laying the foundation for subsequent lessons on producers, consumers, serialization, retries, and transactions.

## 1. Identify the Application Type Before Choosing Dependencies

There are two main integration approaches:

| Project Type | Commonly Used Dependency | Configuration Management Approach |
| --- | --- | --- |
| Spring Boot 4.x | `org.springframework.boot:spring-boot-starter-kafka` | Boot starter and auto-configuration |
| Spring Boot 3.x and older Boot lines | `org.springframework.kafka:spring-kafka` | Use Spring Boot dependency management/BOM; Boot auto-configures when Spring Kafka is on the classpath |
| Spring Framework, without Boot | `org.springframework.kafka:spring-kafka` | Manage versions and configure producer, consumer, listener container, and admin manually |

Dependency names can change across Spring Boot release lines. Therefore, check the documentation for the exact Boot line you are using or select the “Spring for Apache Kafka” dependency on Spring Initializr. For Spring Boot 4, the Spring Kafka Quick Tour currently guides using `spring-boot-starter-kafka`. For earlier Boot lines, the common approach is to declare `spring-kafka` and let Boot's BOM manage the version.

If the application uses Spring Kafka directly, `spring-kafka` is the core integration library. There is no need to declare `kafka-clients` separately in normal cases because Spring Kafka already declares the appropriate client as part of its dependencies. Only add other Kafka artifacts, such as `kafka-streams`, when the application actually uses the corresponding functionality.

## 2. Choosing Dependencies for Spring Boot

### Spring Boot 4.x: Use the Kafka Starter

For a Spring Boot 4 project, declare the Kafka starter provided by Boot. The starter pulls the required components onto the classpath and works with Boot's auto-configuration mechanism.

Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

Do not specify versions directly for these dependencies when the project already uses the Spring Boot parent or BOM. Boot will select the versions belonging to the dependency set managed by that Boot release line.

### Spring Boot 3.x and Older Boot Lines: Use `spring-kafka`

In Boot lines that do not yet provide a dedicated Kafka starter, declare the Spring Kafka library directly. Boot's auto-configuration detects the Kafka components on the classpath and can create common beans such as `KafkaTemplate`, `KafkaAdmin`, and the default listener container factory.

Maven:

```xml
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

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

The snippets above assume the project already applies Spring Boot dependency management, such as via `spring-boot-starter-parent` in Maven or the corresponding plugin/dependency platform in Gradle. Without a BOM, the build tool does not automatically know which versions to use; in that case, you must declare a verified compatible version set.

### Creating a Project with Spring Initializr

For a new project, you can choose a Spring Boot version compatible with your JDK and select the **Spring for Apache Kafka** dependency on Spring Initializr. Initializr generates the build configuration corresponding to the chosen Boot line. After generating the project, still inspect `pom.xml` or `build.gradle` to understand the actual dependencies and confirm the project uses the right BOM.

## 3. Using Spring Kafka Without Spring Boot

In an application that only uses Spring Framework, declare `spring-kafka` with a specific version:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
    <version>${spring.kafka.version}</version>
</dependency>
```

`${spring.kafka.version}` here is a project-defined property set to a version verified in the Spring Kafka release documentation. Gradle can be configured similarly:

```groovy
ext {
    springKafkaVersion = findProperty('springKafkaVersion')
}

dependencies {
    implementation "org.springframework.kafka:spring-kafka:${springKafkaVersion}"
}
```

The `springKafkaVersion` property needs to be defined in `gradle.properties` with a verified version from the release documentation. Without Boot, the development team must also configure components such as `ProducerFactory`, `KafkaTemplate`, `ConsumerFactory`, `ConcurrentKafkaListenerContainerFactory`, and `KafkaAdmin` as needed.

## 4. Understanding the Version Layers That Must Be Compatible

A Spring Kafka application has multiple dependency layers. Check them along the following chain:

```text
JDK
  └── Spring Boot (if used)
        ├── Spring Framework
        ├── Spring for Apache Kafka
        │     └── Apache Kafka client (kafka-clients)
        └── Related testing libraries

Kafka broker (runtime/test environment; check compatibility separately)
```

### JDK and Spring Boot

Spring Boot defines a minimum Java version and supported Java versions for each release line. Choose the JDK first, then choose a Boot line that still supports that JDK. Do not look only at the Spring Kafka version to conclude that the project can run on the current JDK.

### Spring Boot and Spring Framework

Each Spring Boot line is built on a corresponding Spring Framework line. Do not upgrade `spring-core`, `spring-context`, or other Spring Framework modules individually beyond the version set managed by Boot unless there is an explicit requirement and verified compatibility.

### Spring Kafka and Kafka Client

Spring Kafka uses the Apache Kafka Java client, typically the `org.apache.kafka:kafka-clients` artifact. The Spring Kafka version determines the client range it was developed and tested with. When using Spring Boot, the BOM usually manages both dependency groups. Upgrading `kafka-clients` on your own while keeping an older Spring Kafka can cause API changes, behavioral differences, or runtime errors.

### Kafka Client and Kafka Broker

The Kafka client version in the application does not necessarily have to match the Kafka broker version number. Client and broker communicate over the protocol; interoperability depends on the compatibility matrix and the features the application uses. Check the Apache Kafka compatibility documentation for the specific client/broker pair, especially when using transactions, the Admin API, or new protocols and features.

### Testing Libraries

`spring-kafka-test` should match the application's Spring Kafka version. If using Embedded Kafka, also check the Kafka server/client version used by the test suite. If using Testcontainers, the Kafka image in tests also needs to match the client and features the application is testing.

Spring Kafka 4.1.2 documentation, for example, states its quick tour corresponds to Kafka Clients 4.0.x, Spring Framework 7.0.0, and a minimum Java version of 17. This is an example of how release documentation publishes compatibility ranges, not a rule applicable to every Spring Kafka version. Always open the documentation for your project's exact library version.

## 5. Why Should the Spring Boot BOM Manage Versions?

Spring Boot provides a set of dependency management metadata tested together. When a project uses the Boot parent or imports `spring-boot-dependencies`, dependencies can be declared without repeating the version on every line.

For example, a Maven dependency without a `<version>` tag:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
```

Benefits of this approach:

- Reduces the risk of picking a Spring Kafka version incompatible with Spring Framework.
- Keeps `spring-kafka`, `spring-kafka-test`, and the Kafka client on a synchronized version set.
- Enables controlled upgrades following the Spring Boot line.
- Keeps build files shorter and easier to review.

A BOM does not eliminate the need for verification. When upgrading Boot, check release notes, Java baseline, dependency changes, and deprecated configurations. Do not upgrade a single library just because a newer version appears on Maven Central.

## 6. When Should You Override Boot-Managed Versions?

Override only when there is a specific reason, such as needing a confirmed bug fix, using a new Kafka client feature, or maintaining compatibility with a specific broker environment. Before overriding, check Spring Kafka's guidance for the corresponding Boot line and run integration tests.

Spring Kafka documentation guides using dependency management properties such as `spring-kafka.version` to change the Spring Kafka version and `kafka.version` to change the Kafka client/Streams group when the Boot BOM supports that override mechanism. Exact property names and configuration should be checked against the documentation for the specific Boot version.

Maven example illustrating how to set the properties, not recommending a specific number:

```xml
<properties>
    <spring-kafka.version>VERIFIED_VERSION</spring-kafka.version>
    <kafka.version>VERIFIED_KAFKA_CLIENT_VERSION</kafka.version>
</properties>
```

Do not override `kafka-clients` alone by adding a different dependency version at the bottom of the file without checking dependency mediation. The result can be part of the Kafka libraries at one version and the rest at another version. If changes are needed, use the BOM's official override mechanism and inspect the entire dependency tree.

## 7. Configuring the Connection After Choosing Dependencies

After adding the right dependencies, configure the broker connection in `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
```

Spring Boot can auto-configure `KafkaTemplate` and listener containers when Spring Kafka is present on the classpath. Producer, consumer, admin, and listener settings can be tuned via the `spring.kafka.*` property group. Serializer/deserializer, security, retry, and transaction settings should be added according to the requirements of each lesson, rather than copying a large configuration before understanding its effect.

This example only illustrates minimal configuration so the application knows the broker address and consumer group. It does not create a Kafka broker, nor does it prove a broker is ready. Local, test, and production environments should have separate configurations, especially for connection addresses and credentials.

## 8. Checking the Actual Versions Resolved by the Build

Do not just read the dependency declaration file; inspect the final versions after Maven or Gradle resolves dependencies.

With Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.kafka,org.apache.kafka
```

On Windows, you can run:

```powershell
.\mvnw.cmd dependency:tree -Dincludes=org.springframework.kafka,org.apache.kafka
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
```

When reviewing the output, confirm:

1. Only one Spring Kafka version is selected in the runtime classpath.
2. `kafka-clients` is the version expected by Spring Kafka/Boot BOM.
3. `spring-kafka-test` matches the application's Spring Kafka version.
4. No direct or transitive dependency forces a Spring Framework module to a version outside the Boot-managed set.
5. Additional Kafka libraries such as `kafka-streams` (if present) belong to a matching client line.

If the dependency tree shows multiple requested versions with only one selected, read the `omitted for conflict` lines or `dependencyInsight` output to see which dependency requested a different version. This is how to find the root cause of a conflict instead of adding a version override by guesswork.

## 9. Common Mistakes When Choosing Starters and Versions

| Mistake | Possible Consequence | Resolution |
| --- | --- | --- |
| Using a starter name that does not exist in the chosen Boot line | Build cannot find the artifact | Check documentation for the exact Boot line; use `spring-kafka` if that is the integration approach for that line |
| Declaring a separate version for `spring-kafka` in a project using Boot BOM | May drift from the Boot-tested version set | Remove the separate version or override via a documented property |
| Upgrading `kafka-clients` independently | API errors or incompatible behavior | Check the Spring Kafka/client compatibility matrix and use the official override mechanism |
| Using a `spring-kafka-test` version different from the application's | Errors when running tests or embedded broker | Let the BOM manage it or align the test artifact version |
| Choosing a JDK lower than the minimum required by Boot/Spring Kafka | Fails to compile or fails to start | Choose a supported JDK or use a more suitable library line |
| Assuming client and broker must have the exact same version | Unnecessary upgrades or overlooking the protocol matrix | Check client/broker compatibility docs and required features |

## 10. Recommended Selection Workflow

When starting a new project, proceed in order:

1. Identify the JDK that the build and production environments can use.
2. Choose a Spring Boot line that is still supported and compatible with that JDK.
3. Choose the Kafka dependency based on the Boot line: the Kafka starter if the Boot line provides one; otherwise, use `spring-kafka` per official guidance.
4. Let the Boot BOM manage Spring Kafka and Kafka client versions in normal cases.
5. Check the target Kafka broker and required features against the client/broker compatibility documentation.
6. Add `spring-kafka-test` or Testcontainers for integration testing with a compatible version.
7. Run dependency tree, start the application, and perform a send/receive test against a real or test broker.

## 11. Conclusion

Choosing the right starter for your Spring Boot line and letting dependency management handle versions is a safe way to start a Spring Kafka application. With Spring Boot 4, use the Kafka starter per current Boot documentation; with older Boot lines, declare `spring-kafka` and let the BOM manage versions. With Spring Framework without Boot, pick a Spring Kafka version compatible with your JDK, Spring Framework, and Kafka client, then configure the infrastructure yourself.

Treat JDK, Spring Boot, Spring Framework, Spring Kafka, Kafka client, broker, and testing libraries as a combined dependency set that needs to be verified together. Override only with a clear reason, inspect the dependency tree after changes, and run integration tests before promoting configurations to operational environments.

## References

- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Kafka — Quick Tour and Compatibility](https://docs.spring.io/spring-kafka/reference/quick-tour.html)
- [Spring Kafka — Override Spring Boot Dependencies](https://docs.spring.io/spring-kafka/reference/appendix/override-boot-dependencies.html)
