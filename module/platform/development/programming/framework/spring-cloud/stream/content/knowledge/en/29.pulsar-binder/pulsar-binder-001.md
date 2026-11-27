# Choosing a Compatible Pulsar Binder Artifact and Version

To use Apache Pulsar in a Spring Cloud Stream application, you must choose the right binder artifact and align it with Spring Boot, the Spring Cloud release train, Spring Cloud Stream, the Pulsar client, and the Pulsar broker. These components each have their own versions; you cannot take the version number of one component and apply it to all of them.

Artifact selection also depends on the integration generation. Spring Cloud Stream 5.0.x uses the binder line released by Spring for Apache Pulsar. Starting in November 2026, Spring for Apache Pulsar moved to the Apache Pulsar project under the name Apache Pulsar support for Spring. Spring Pulsar 2.0.8 is the final release published by Spring; the Apache project has released the `3.0.0-M1` line with new Maven coordinates and Java packages. Spring Cloud 2026.0.0 was also released alongside Spring Boot 4.2.0 and Spring Cloud Stream 5.1.0. Therefore, when choosing dependencies, you must clearly determine whether you are maintaining an application on the legacy Spring line, using the binder in Spring Cloud Stream 5.1.0, or migrating to the new Apache Pulsar line.

This lesson walks through reading the compatibility matrix, choosing Maven/Gradle coordinates, using BOMs, controlling Pulsar client and Netty versions, inspecting the dependency tree, resolving classpath conflicts, and planning upgrades without unintended broker changes.

## Learning Objectives

After completing this lesson, you will be able to:

- Distinguish the binder artifact from the Spring Boot starter, Pulsar client, and BOM.
- Identify the Spring Boot version compatible with a Spring Cloud release train.
- Choose a binder based on the Spring Cloud Stream generation and where the project is maintained.
- Recognize the old and new Maven coordinates for Pulsar integration.
- Use the Spring Cloud BOM or Pulsar Spring BOM within the proper scope.
- Align the Pulsar client version and Netty version.
- Understand why the old and new binders should not be added simultaneously.
- Inspect the dependency tree and effective POM to find version conflicts.
- Verify the build, classpath, and connection to the Pulsar broker before deployment.

## 1. Components with Separate Versions

A Spring Cloud Stream application connecting to Pulsar can include the following dependency layers:

| Component | Role | Example artifact name |
|---|---|---|
| Spring Boot | Application foundation, auto-configuration, and dependency management | `spring-boot-starter` |
| Spring Cloud release train | Aligns Spring Cloud projects | `spring-cloud-dependencies` |
| Spring Cloud Stream | Programming model, binding abstraction, and binder SPI | `spring-cloud-stream` |
| Pulsar binder | Connects bindings to Pulsar topics, producers, and consumers | `pulsar-spring-cloud-stream-binder` |
| Spring Pulsar integration | Template, listener, auto-configuration, and Spring utilities for Pulsar | `pulsar-spring` |
| Pulsar Java client | Protocol communication with the Pulsar broker | `pulsar-client` or corresponding client artifacts |
| Pulsar broker | Messaging system running on the server | Apache Pulsar cluster |
| BOM | Manages compatible version sets | `spring-cloud-dependencies`, `pulsar-spring-bom` |

Do not confuse the following versions:

- Spring Boot version is the application platform version.
- Spring Cloud release train version is the BOM version for the Spring Cloud ecosystem.
- Spring Cloud Stream version is the version of the programming model and binder SPI.
- Pulsar binder version is the version of the adapter connecting Spring Cloud Stream to Pulsar.
- Spring Pulsar integration version is the version of the Spring libraries for Pulsar.
- Pulsar client version is the version of the client library running inside the application.
- Pulsar broker version is the server cluster version.

An application can run Spring Boot 4.2.0, Spring Cloud 2026.0.0, Spring Cloud Stream 5.1.0, Apache Pulsar binder 3.0.0-M1, and Pulsar client 5.0.x. Having different version numbers is normal; what matters is that the combination is supported by the documentation or BOM.

## 2. Reading the Compatibility Matrix Before Adding the Binder

Spring Cloud release trains are published per Spring Boot line. Choose the release train first, and then choose the dependencies belonging to that train.

As of November 24, 2026, the relevant official milestones include:

| Spring Cloud release train | Compatible Spring Boot | Spring Cloud Stream in train | Notes |
|---|---|---|---|
| 2026.0.0 (Paddington) | 4.2.0 | 5.1.0 | Released on 2026-11-20 |
| 2025.1.x (Oakwood) | 4.0.x; 4.1.x from 2025.1.2 | 5.0.x | Choose the latest service release in the train |
| 2025.0.x (Northfields) | 3.5.x | 4.3.x | Older line |

This table lists release train milestones, not a direct compatibility table between every Pulsar broker and Pulsar client. When choosing a binder, continue checking the binder documentation and dependency management for the exact release train.

### 2.1. Example: Spring Boot 4.2.0 Application

If an application uses Spring Boot 4.2.0, Spring Cloud 2026.0.0 is the corresponding release train. This release train includes Spring Cloud Stream 5.1.0.

Maven BOM:

~~~xml
<properties>
    <java.version>17</java.version>
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
~~~

The Spring Cloud BOM manages the versions of artifacts belonging to the release train. When a dependency is managed by the BOM, do not manually set a different version just to make the version numbers look similar to Spring Boot.

### 2.2. Do Not Mix Release Trains by Guesswork

Example of what not to do:

~~~text
Spring Boot 4.2.x
Spring Cloud 2025.0.x
Spring Cloud Stream 5.1.x
Pulsar binder 4.3.x
~~~

The lines above belong to different generations. A dependency might still resolve from Maven Central, but a successful compilation does not prove the combination is supported. Use the compatibility matrix, BOM, and documentation for the exact release.

## 3. Choosing a Binder by Release Generation

Pulsar integration for Spring Cloud Stream has changed its development home and Maven coordinates. You need to recognize three common cases.

### 3.1. Spring Pulsar Line Before the Project Transfer

The Spring Cloud Stream 5.0.x documentation specifies using the binder artifact:

~~~xml
<dependency>
    <groupId>org.springframework.pulsar</groupId>
    <artifactId>spring-pulsar-spring-cloud-stream-binder</artifactId>
</dependency>
~~~

This is the coordinate in the binder documentation for the Spring for Apache Pulsar 2.x generation. Spring Pulsar 2.0.8 is the final release maintained by Spring. Applications running stably on this line can continue using it while preparing for migration, but you should not expect new patches from the Spring project after the handover.

Some Spring Cloud Stream binder generations were also published under the coordinate:

~~~text
org.springframework.cloud:spring-cloud-stream-binder-pulsar
~~~

The Apache project's migration guide lists this coordinate among the legacy artifacts being replaced. When maintaining an existing application, inspect `pom.xml`, Gradle dependency declarations, and the dependency tree to identify the exact artifact currently in use; do not add both Spring-side coordinates simply because you found them in documentation from different generations.

### 3.2. Spring Cloud Stream 5.1.0 Line

Spring Cloud 2026.0.0 ships Spring Cloud Stream 5.1.0. The project transfer announcement states that applications can continue using Spring Pulsar 2.0.8 and the 5.1.0 binder during the transition period.

If an application intentionally uses the binder managed in the Spring Cloud 2026.0.0 release train, use the artifact belonging to that train and let the Spring Cloud BOM manage the version. The binder coordinate in the Spring Cloud line is:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-pulsar</artifactId>
</dependency>
~~~

Do not manually specify a version when the 2026.0.0 BOM already manages the artifact. This keeps the binder aligned with Spring Cloud Stream 5.1.0. This is a compatible upgrade path for Spring Cloud applications; the new Pulsar integration project has moved to Apache Pulsar for ongoing maintenance and development.

### 3.3. Apache Pulsar Support for Spring Line

Starting November 10, 2026, Spring for Apache Pulsar moved to a subproject of Apache Pulsar named Apache Pulsar support for Spring. The first release is `3.0.0-M1`, published on Maven Central.

New binder artifact:

~~~xml
<dependency>
    <groupId>org.apache.pulsar</groupId>
    <artifactId>pulsar-spring-cloud-stream-binder</artifactId>
    <version>3.0.0-M1</version>
</dependency>
~~~

Gradle:

~~~kotlin
dependencies {
    implementation("org.apache.pulsar:pulsar-spring-cloud-stream-binder:3.0.0-M1")
}
~~~

This coordinate belongs to the Apache Pulsar support for Spring project, not an artifact managed by the Spring Cloud BOM. `3.0.0-M1` is a milestone release; evaluate its release status and support policy before selecting it for production. Once a newer GA release is available, use the version published in the official Apache Pulsar support for Spring documentation.

### 3.4. Decision Table

| Scenario | Artifact to consider | Version management |
|---|---|---|
| Legacy application following Spring Cloud Stream 5.0.x documentation | `org.springframework.pulsar:spring-pulsar-spring-cloud-stream-binder` | Per the corresponding Spring Pulsar BOM/documentation |
| Application using the Spring Cloud Stream 5.1.0 binder | `org.springframework.cloud:spring-cloud-stream-binder-pulsar` | Spring Cloud 2026.0.0 BOM |
| Application migrating to Apache Pulsar support for Spring | `org.apache.pulsar:pulsar-spring-cloud-stream-binder` | Declare version directly or import `pulsar-spring-bom` |

Choose one dependency path per application. Do not allow both the old Spring-side binder and the new Apache-side binder to appear on the classpath simultaneously.

## 4. Distinguishing Artifact, Starter, and BOM

### 4.1. Binder Artifact

The binder is an implementation of the Spring Cloud Stream Binder SPI. It connects bindings such as `orders-in-0` and `orders-out-0` to Pulsar topics, producers, and consumers. This is the required dependency for a Spring Cloud Stream application to use Pulsar as middleware.

### 4.2. Spring Boot Starter

A starter bundles dependencies and auto-configuration for building Spring Boot applications that use the Pulsar API directly. Example starter from the Apache project:

~~~xml
<dependency>
    <groupId>org.apache.pulsar</groupId>
    <artifactId>pulsar-spring-boot-starter</artifactId>
    <version>3.0.0-M1</version>
</dependency>
~~~

If your goal is to use the Spring Cloud Stream binder, start with the binder artifact. Only add the standalone starter when the application needs other Spring Pulsar APIs beyond what the binder already provides and the dependency graph confirms there is no duplicate auto-configuration.

Do not add the starter simply assuming every Spring Boot application must declare a separate Pulsar starter. The binder already brings in the necessary components through its dependencies.

### 4.3. BOM

A BOM is a POM for managing versions. It is not a runtime library and does not replace the binder artifact.

The two BOMs have different scopes:

- `spring-cloud-dependencies`: manages projects belonging to the Spring Cloud release train.
- `pulsar-spring-bom`: manages artifacts belonging to Apache Pulsar support for Spring.

When migrating to the Apache artifacts, the Spring Cloud BOM does not automatically manage the version of `org.apache.pulsar:pulsar-spring-cloud-stream-binder`. Specify the version directly or import the Apache project's BOM.

## 5. Managing Versions in the New Apache Line

Apache Pulsar support for Spring 3.0.0-M1 requires the Pulsar 5.0.x client. This project's version is no longer managed by Spring Boot as before. Therefore, the Spring Boot application needs to set `pulsar.version`; the project also recommends setting `netty.version` to an appropriate 4.2.x release.

Maven example declaring the version directly:

~~~xml
<properties>
    <pulsar-spring.version>3.0.0-M1</pulsar-spring.version>
    <pulsar.version>5.0.1</pulsar.version>
    <netty.version>4.2.20.Final</netty.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.pulsar</groupId>
        <artifactId>pulsar-spring-cloud-stream-binder</artifactId>
        <version>${pulsar-spring.version}</version>
    </dependency>
</dependencies>
~~~

The versions in this example illustrate the configuration published with 3.0.0-M1; before using them, check the release notes and client/Netty requirements of the Apache support for Spring version your project selects.

### 5.1. Using the Pulsar Spring BOM

If you have multiple Apache Pulsar support for Spring artifacts, import the BOM to avoid declaring mismatched Spring integration versions:

~~~xml
<properties>
    <pulsar-spring.version>3.0.0-M1</pulsar-spring.version>
    <pulsar.version>5.0.1</pulsar.version>
    <netty.version>4.2.20.Final</netty.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.pulsar</groupId>
            <artifactId>pulsar-spring-bom</artifactId>
            <version>${pulsar-spring.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.apache.pulsar</groupId>
        <artifactId>pulsar-spring-cloud-stream-binder</artifactId>
    </dependency>
</dependencies>
~~~

The BOM manages the versions of artifacts belonging to Apache Pulsar support for Spring. `pulsar.version` still needs to be set because Spring Boot may manage an older Pulsar client version. `netty.version` is a recommended property to align Netty with the new client.

Gradle:

~~~kotlin
extra["pulsar.version"] = "5.0.1"
extra["netty.version"] = "4.2.20.Final"

dependencies {
    implementation(platform("org.apache.pulsar:pulsar-spring-bom:3.0.0-M1"))
    implementation("org.apache.pulsar:pulsar-spring-cloud-stream-binder")
}
~~~

### 5.2. Do Not Use a BOM to Hide Version Conflicts

When importing multiple BOMs, the ordering and precedence of dependency management can affect the final resolved versions. Do not add a BOM just to force a library to a newer version without understanding the dependency graph.

After importing a BOM:

- Inspect the effective POM or Gradle dependency insight.
- Verify the actual resolved Pulsar client version.
- Check that Netty and Jackson are not pulled to conflicting versions.
- Verify that two binder implementations are not loaded together.
- Run the build and integration tests against the broker.

## 6. Pulsar Client Version vs. Broker Version

The Pulsar client is a library running inside the application's JVM. The Pulsar broker is a server in the cluster. These two versions do not necessarily have to match.

Apache Pulsar support for Spring 3.0.0-M1 requires the Pulsar 5.0.x client. The migration documentation notes that the 5.0.x client is compatible with older brokers, so upgrading the client does not mean you must upgrade the broker immediately.

However, distinguish carefully between:

- Protocol compatibility between client and broker.
- Client feature support when talking to an older broker.
- New broker features that an older client does not know about.
- Schema, transaction, and authentication features enabled on the cluster.

A new client can connect to an older broker, but that does not mean every new client feature is available on that broker. Check the Pulsar client/broker compatibility table and release notes before rolling out.

### 6.1. Unshaded Client Dependencies

The new Apache support for Spring line moves away from `pulsar-client-all` to unshaded client artifacts such as `pulsar-client-original` and `pulsar-client-admin-original`. This makes Netty, Jackson, and several other libraries regular dependencies on the classpath.

Consequences:

- Conflicts can occur with Netty/Jackson pulled in by other frameworks or libraries.
- Classes in the `org.apache.pulsar.shade` package are no longer available.
- You should not write code depending on implementations relocated inside `pulsar-client-all`.
- You need to inspect the dependency tree after migration.

If another dependency still pulls in `pulsar-client-all`, consider excluding it according to the official guide and verify carefully that all required classes remain present.

## 7. Package Changes When Migrating to Apache Pulsar Support for Spring

Migration does not only change Maven coordinates. Java packages also change:

| Old package | New package |
|---|---|
| `org.springframework.pulsar` | `org.apache.pulsar.spring` |
| `org.springframework.boot.pulsar` | `org.apache.pulsar.spring.boot` |
| `org.springframework.cloud.stream.binder.pulsar` | `org.apache.pulsar.spring.cloud.stream.binder` |

Import example:

~~~java
// Before migration
import org.springframework.pulsar.core.PulsarTemplate;

// After migration
import org.apache.pulsar.spring.core.PulsarTemplate;
~~~

Check the actual package names in the migration guide/Javadoc for the version you are using; the example above illustrates the namespace renaming rule.

The property prefixes `spring.pulsar.*` and `spring.cloud.stream.pulsar.*` are announced as unchanged during migration. That reduces the number of configuration changes needed, but it does not mean dependencies and Java imports can remain unchanged.

### 7.1. Replace, Do Not Add Side by Side

When switching from the Spring-side binder to the Apache-side binder:

1. Remove the old binder dependency.
2. Add `org.apache.pulsar:pulsar-spring-cloud-stream-binder`.
3. Update the relevant Java imports.
4. Align `pulsar.version` and `netty.version`.
5. Verify no old auto-configuration or old binder remains on the classpath.
6. Build and run integration tests.

Do not keep both the old binder and the new binder in the same runtime just for testing. Two sets of auto-configurations and SPI metadata can create duplicate bindings or bean conflicts.

## 8. Example Application Configuration Using the Pulsar Binder

After choosing the right artifact, Spring Cloud Stream configuration still uses functions and bindings just like other binders.

Java:

~~~java
@SpringBootApplication
public class PulsarEventsApplication {

    @Bean
    public Supplier<OrderCreated> orderSupplier() {
        return () -> new OrderCreated(
                UUID.randomUUID().toString(),
                Instant.now());
    }

    @Bean
    public Function<OrderCreated, OrderAccepted> acceptOrder() {
        return order -> new OrderAccepted(
                order.orderId(),
                "ACCEPTED",
                order.createdAt());
    }

    @Bean
    public Consumer<OrderAccepted> logAcceptedOrder() {
        return order -> log.info("Accepted order {}", order.orderId());
    }

    record OrderCreated(String orderId, Instant createdAt) {}

    record OrderAccepted(
            String orderId,
            String status,
            Instant createdAt) {}
}
~~~

YAML:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSupplier;acceptOrder;logAcceptedOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
        acceptOrder-out-0:
          destination: orders.accepted
        logAcceptedOrder-in-0:
          destination: orders.accepted
  pulsar:
    client:
      service-url: pulsar://localhost:6650
    admin:
      service-url: http://localhost:8080
~~~

This is an application structure example, not a complete production deployment configuration. With multiple functions, `spring.cloud.function.definition` selects the beans to activate. A `Supplier` has an output binding, a `Function` has input/output bindings, and a `Consumer` has an input binding.

### 8.1. Property Precedence

The Pulsar binder uses Spring Pulsar auto-configuration. Configuration can be set at three levels:

| Level | Prefix | Scope |
|---|---|---|
| Spring Boot/Pulsar | `spring.pulsar.*` | General client configuration |
| Binder | `spring.cloud.stream.pulsar.binder.*` | General binder configuration |
| Extended binding | `spring.cloud.stream.pulsar.bindings.<binding-name>.*` | Binding-specific configuration |

Binder precedence from highest to lowest:

1. Extended binding properties.
2. Binder properties.
3. Spring Boot properties.

If two bindings require different authentication, schema, or consumer settings, use extended binding properties instead of setting a single global value for the entire application.

## 9. Inspecting the Dependency Tree

A successful build is not enough to prove the application uses the right binder and Pulsar client. Inspect the actual dependency graph.

### 9.1. Maven

Show relevant dependencies:

~~~bash
./mvnw dependency:tree -Dincludes=org.apache.pulsar,org.springframework.pulsar,org.springframework.cloud,org.springframework.boot
~~~

View effective POM:

~~~bash
./mvnw help:effective-pom
~~~

Verify:

- The binder artifact has the correct `groupId`/`artifactId`.
- Only one generation of the Pulsar binder is loaded.
- The `pulsar-client` version is the intended version.
- No unintended legacy dependencies remain.
- The Netty version has not drifted.
- Spring Cloud Stream matches the Spring Cloud BOM line.

### 9.2. Gradle

View the runtime dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

View why a dependency was selected:

~~~bash
./gradlew dependencyInsight --dependency pulsar --configuration runtimeClasspath
./gradlew dependencyInsight --dependency netty --configuration runtimeClasspath
~~~

Gradle may choose a version due to conflict resolution. Read why that version was chosen rather than looking only at the dependency line declared in `build.gradle`.

### 9.3. Checking the Runtime Classpath

If the application starts up but cannot find the binder, check:

- Is the dependency on `runtimeClasspath` or only in compile/test scope?
- Are the binder's SPI metadata and auto-configuration packaged properly?
- Is there an exclusion removing the binder or Pulsar client?
- Are there two versions of the same library inside the fat JAR or container image?
- Is the dependency cache serving an old artifact?

Do not fix classpath errors by manually copying JARs into the application directory. Fix the build declaration so the dependency graph is reproducible.

## 10. Common Version Selection Mistakes

1. **Using the wrong artifact ID**: The Pulsar binder does not share the same coordinates as the Kafka or Rabbit binder. Use the coordinates from the documentation for the right generation.
2. **Changing only `groupId` while keeping the old `artifactId`**: Migrating to Apache changes `groupId`, `artifactId`, and packages. Update all of them per the migration guide.
3. **Using the Spring Cloud BOM to manage new Apache artifacts**: The Spring Cloud BOM does not automatically manage `org.apache.pulsar` versions. Set the version or import `pulsar-spring-bom`.
4. **Omitting `pulsar.version`**: Spring Boot may manage an older Pulsar client. Set the property as required by Apache support for Spring.
5. **Ignoring Netty**: Unshaded clients expose Netty as a regular dependency. Check and align `netty.version`.
6. **Mixing incompatible Spring Boot and Spring Cloud versions**: Dependencies may still resolve, but runtime errors can occur. Start from the compatibility matrix.
7. **Adding old and new binders simultaneously**: This can create duplicate auto-configurations or binder registrations. Replace the old dependency.
8. **Confusing client version with broker version**: Client and broker can run different versions within the compatibility range. Check the client/broker compatibility matrix.
9. **Treating a milestone as GA**: `3.0.0-M1` is a milestone. Check its release status and support policy before production use.
10. **Using old packages after changing artifacts**: Code fails to compile or classes are not found at runtime. Update imports per the migration guide.
11. **Keeping `pulsar-client-all` alongside unshaded clients**: This can cause duplicate or conflicting classes. Inspect the dependency tree and remove unnecessary artifacts.
12. **Setting different versions on individual Spring modules manually**: Modules can have mismatched APIs. Use a BOM to manage a consistent set of versions.
13. **Checking only compilation**: Compilation does not prove topic provisioner, authentication, or broker compatibility works. Run integration tests against Pulsar.

## 11. Artifact and Version Selection Workflow

When starting an application or upgrading the binder:

1. Determine the application's Spring Boot version.
2. Check the Spring Cloud compatibility matrix and choose the corresponding release train.
3. Identify the Spring Cloud Stream version provided by that release train.
4. Choose the Pulsar binder generation: Spring-side transitional or Apache-owned.
5. Look up the Maven coordinates in the official documentation for the exact generation.
6. Import the Spring Cloud BOM for Spring Cloud artifacts.
7. For Apache Pulsar support for Spring, set the binder version or import `pulsar-spring-bom`.
8. Set `pulsar.version` according to the binder's client requirement.
9. Align `netty.version` if using the unshaded client line.
10. Do not leave both the old and new binders on the classpath.
11. Inspect the dependency tree and effective POM.
12. Build the application, run tests, and connect to a compatible Pulsar broker.
13. Deploy to a test environment and monitor startup, topic provisioning, producer/consumer behavior, and schemas.
14. Record the artifact coordinates and versions in operational documentation so future upgrades are reproducible.

## Conclusion

Choosing a compatible Pulsar binder starts with Spring Boot and the Spring Cloud release train, followed by Spring Cloud Stream and the binder artifact. Spring Cloud 2026.0.0 is compatible with Spring Boot 4.2.0 and provides Spring Cloud Stream 5.1.0. The Spring Pulsar 2.0.8 line is the final release maintained by Spring; the Apache Pulsar support for Spring project has released the new binder `org.apache.pulsar:pulsar-spring-cloud-stream-binder` at version 3.0.0-M1.

When using the new Apache artifact, declare the version or import `pulsar-spring-bom`, set `pulsar.version`, and check `netty.version`. Migration also renames Java packages and switches the client to unshaded artifacts. Do not add old and new binders side by side; inspect the dependency tree, build, and run integration tests against the Pulsar broker before deployment.

## References

- [Spring Cloud — Release Train and Spring Boot Compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2026.0.0 Release Notes](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud Stream — Pulsar Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring for Apache Pulsar — New Home Announcement](https://spring.io/blog/2026/11/10/spring-pulsar-new-home-asf/)
- [Apache Pulsar Support for Spring — Migration Guide](https://pulsar.apache.org/pulsar-spring/reference/migration.html)
- [Apache Pulsar Support for Spring — Spring Cloud Stream Binder](https://pulsar.apache.org/pulsar-spring/reference/cloud-stream-binder.html)
