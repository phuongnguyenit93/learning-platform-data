# Setting Up Maven or Gradle and Managing Dependency Versions

A Spring Cloud Stream application needs three groups of components: the Spring Boot foundation to launch the application, the Spring Cloud Stream library to declare and operate bindings, and a binder to connect to a messaging system such as Kafka, RabbitMQ, or Pulsar. When creating a project, choosing the right dependencies and synchronizing versions between Spring Boot and Spring Cloud is just as important as writing `Supplier`, `Function`, or `Consumer` functions.

Both Maven and Gradle can manage these components. Maven uses `pom.xml` together with dependency management; Gradle declares plugins, repositories, and dependencies in its build files. Both can import the Spring Cloud BOM (Bill of Materials) to use a compatible set of versions for Spring Cloud libraries.

## 1. Understanding Application Dependency Layers

Before adding libraries, you need to distinguish the role of each group:

| Group | Role | Examples |
| --- | --- | --- |
| Spring Boot | Application initialization, auto-configuration, lifecycle management, and foundational components | `spring-boot-starter`, `spring-boot-starter-actuator` |
| Spring Cloud Stream | Binding model, function integration, and message-processing abstractions | `spring-cloud-stream` |
| Binder | Connects the binding model to a specific broker | Kafka binder, Rabbit binder, Pulsar binder |
| Test | Supports testing the application and message flows | `spring-boot-starter-test`, `spring-cloud-stream-test-binder` |

In most applications, you should declare the starter for the binder being used. The starter pulls in the required libraries, including Spring Cloud Stream core and the corresponding broker integration. For example:

| Messaging system | Commonly used dependency |
| --- | --- |
| Apache Kafka | `org.springframework.cloud:spring-cloud-starter-stream-kafka` |
| RabbitMQ | `org.springframework.cloud:spring-cloud-starter-stream-rabbit` |
| Apache Pulsar | `org.springframework.cloud:spring-cloud-stream-binder-pulsar` |

Artifact names and packaging may change across binder version lines. Cross-check the documentation for the exact Spring Cloud Stream version in use before adding the Pulsar binder or an extended binder. Only add the binders the application actually needs; each binder brings additional client libraries and its own configuration onto the classpath.

If you only need Kafka, you do not have to manually declare both `spring-cloud-stream` and the Kafka client separately. `spring-cloud-starter-stream-kafka` is an appropriate starting point for a typical Spring Boot application. Only declare low-level dependencies when the project has special requirements or is building a custom integration.

## 2. Choosing Compatible Spring Boot and Spring Cloud Versions

Spring Boot and Spring Cloud are released on separate schedules. Spring Cloud groups multiple subprojects into release trains; each release train is tested against a specific range of Spring Boot versions. Therefore, you should not pick Boot and Cloud versions independently just because newer releases exist for each library.

The version selection workflow should follow this order:

1. Identify the Java version supported by the deployment environment.
2. Choose a Spring Boot line suited to Java and the project's operational requirements.
3. Check the official Spring Cloud compatibility table to select a release train that supports that Spring Boot line.
4. Use the release train's BOM to manage Spring Cloud Stream and the binders belonging to that train.
5. Check the documentation for the specific binder, especially when using Pulsar or a binder outside the main Spring Cloud set.

The Spring Cloud BOM usually has the coordinates `org.springframework.cloud:spring-cloud-dependencies`. The BOM version is the release train version, for example `2023.0.1`, rather than the version of `spring-cloud-stream` alone. The BOM manages versions for multiple Spring Cloud modules so those modules are used consistently together.

The examples in the configurations below use the illustrative version pair Spring Boot `3.2.4` and Spring Cloud `2023.0.1`. This is an example to explain how declarations work; when creating a new project, replace them with a version pair that is still supported and confirmed by the Spring Cloud compatibility table. Do not upgrade a single binder or `spring-cloud-stream` to a version outside the BOM without checking compatibility.

### What Problem Does the BOM Solve?

If you set versions manually for each dependency, a project can accidentally mix versions of Spring Cloud Stream, the Kafka binder, the Rabbit binder, and foundational libraries that were released or tested at different times. These differences can cause dependency resolution errors, `NoSuchMethodError`, `ClassNotFoundException`, or startup configuration failures.

A BOM centralizes managed versions in one place. After importing the BOM, regular dependency declarations do not need `<version>` or a version in the Gradle coordinate string. This mechanism reduces scattered version pinning and enables controlled upgrades.

Note: importing a BOM only manages versions; it does not automatically add all libraries to the application. To use the Kafka binder, the project must still declare the Kafka binder dependency in its dependencies list.

## 3. Configuring a Maven Project

Maven uses the `pom.xml` file. You can start with the Spring Boot parent to inherit Spring Boot's default build configuration and dependency management, then import the Spring Cloud BOM inside `dependencyManagement`.

Minimal `pom.xml` example for an application using Kafka:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>order-stream</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.4</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2023.0.1</spring-cloud.version>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Important parts:

- `spring-boot-starter-parent` provides Maven build configuration and manages Spring Boot dependencies. If your organization already has a custom parent POM, you cannot declare two parents; in that case, keep your organization's parent and import both the `spring-boot-dependencies` BOM and `spring-cloud-dependencies` BOM according to project conventions.
- `java.version` specifies the Java level used for compilation. The Java version must satisfy the requirements of the chosen Spring Boot line and the actual runtime environment.
- `spring-cloud.version` stores the release train version. You only need to change this value when performing an upgrade whose compatibility has been verified.
- `dependencyManagement` imports the BOM. The Spring Cloud dependencies below have their versions managed by the BOM, so they do not need separate `<version>` tags.
- `spring-cloud-starter-stream-kafka` provides Kafka integration for bindings.
- `spring-cloud-stream-test-binder` is placed in the `test` scope; it is only used for testing and does not need to be present in the production runtime.
- `spring-boot-maven-plugin` supports packaging and running the Spring Boot application.

If the application uses RabbitMQ, replace the Kafka starter with `spring-cloud-starter-stream-rabbit`. If multiple brokers are needed in the same application, you can declare multiple binders, but you must configure the appropriate binder for each binding and test how Spring Cloud Stream selects binders. For Pulsar, add the binder artifact specified by the documentation for the version in use and verify compatibility with Spring Cloud Stream.

### When Not Using the Spring Boot Parent

A project may need to keep a corporate or internal platform parent POM. Maven only allows one direct parent, so you cannot inherit both the organization's parent and `spring-boot-starter-parent`. The standard approach is to import both the Spring Boot and Spring Cloud BOMs in `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.2.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
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

When using this approach, the project must also configure the build plugins that the Spring Boot parent normally provides. Inspect the effective POM to understand the final dependencies and plugins Maven uses.

## 4. Configuring a Gradle Project

Gradle manages plugins and libraries through `build.gradle` or `build.gradle.kts`. The example below uses the Groovy DSL, the Spring Boot plugin, and the Spring Dependency Management plugin to import the Spring Cloud BOM.

Example `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.2.4'
    id 'io.spring.dependency-management' version '1.1.4'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

ext {
    set('springCloudVersion', '2023.0.1')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-stream-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In this configuration, `org.springframework.boot` is the Spring Boot build plugin, and `io.spring.dependency-management` applies BOM-based dependency management. `springCloudVersion` is the release train version imported into `dependencyManagement`. The Kafka dependency and test binder therefore do not need separate versions specified.

Another option is to use the BOM directly with Gradle `platform`:

```groovy
dependencies {
    implementation platform('org.springframework.cloud:spring-cloud-dependencies:2023.0.1')
    implementation 'org.springframework.cloud:spring-cloud-starter-stream-kafka'

    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}
```

`platform(...)` brings the version management rules from the BOM into Gradle's dependency configuration. Choose one consistent BOM management approach for the project and avoid importing the same BOM through multiple mechanisms without a clear reason. For multi-module projects, you can centralize versions and dependency rules in the root build or a convention plugin so modules do not pick different Spring Cloud lines on their own.

## 5. Choosing a Binder and Configuring Environment-Specific Dependencies

Dependencies determine which binders are present in the application; Spring Cloud Stream configuration determines which binding uses which binder and connects to which destination. These two aspects are related, but they do not replace each other.

For example, an application using only Kafka can declare the Kafka starter and configure the broker:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.in
          group: order-service
        processOrder-out-0:
          destination: orders.out
      kafka:
        binder:
          brokers: localhost:9092
```

The binding names `processOrder-in-0` and `processOrder-out-0` are formed from the function bean name and Spring Cloud Stream conventions. The Kafka binder dependency gives the application the ability to connect to Kafka; the `brokers` property specifies the broker address for the active environment.

If it needs to connect to both Kafka and RabbitMQ, the application can declare two binder dependencies. When multiple binders are on the classpath, do not leave binder selection to guesswork or unintended default behavior. Set a default binder or explicitly specify the binder on each binding according to the configuration supported by your Spring Cloud Stream version. At the same time, configure connection details separately for each binder.

Do not bundle all binders just "in case". Unnecessary dependencies increase application size, dependency resolution time, and configuration surface area. Add a binder only when an actual business flow requires it.

## 6. Managing Versions in Multi-Module Projects

In multi-module projects, version management needs to remain consistent across modules using Spring Cloud Stream. For example, `order-consumer` and `order-publisher` modules might use different binders, yet they should still draw Spring Cloud versions from the same release train unless the architecture explicitly defines an exception.

With Maven, place `spring-cloud.version` and the BOM in a shared parent POM for child modules to inherit. If a child module needs the Kafka or Rabbit binder, that module declares the corresponding starter without setting a version. Do not re-declare a separate Spring Cloud version inside individual modules.

With Gradle, place the BOM or version catalog in the root build, a convention plugin, or an internal dependency platform. Child modules declare only the libraries they need. This allows upgrading the release train in one place and makes it clear which module actually depends on which binder.

If a third-party library pulls in a different version of Spring Cloud Stream or Spring Kafka, inspect the dependency tree before adding an exclusion or override. An exclusion can resolve a specific conflict, but it can also remove a library the binder needs at runtime.

## 7. Checking Resolved Dependencies

After configuring the build, verify the effective dependencies rather than checking only the declaration file.

Common Maven commands:

```bash
# Compile and run tests
./mvnw clean verify

# View the dependency tree for Spring Cloud libraries
./mvnw dependency:tree -Dincludes=org.springframework.cloud

# View the effective POM after applying parent and BOM
./mvnw help:effective-pom
```

On Windows, you can use `mvnw.cmd` instead of `./mvnw`. If the project does not have the Maven Wrapper yet, use `mvn` when a compatible Maven version is installed on the machine.

Common Gradle commands:

```bash
# Run tests
./gradlew clean test

# View runtime dependencies
./gradlew dependencies --configuration runtimeClasspath

# Find where the selected spring-cloud-stream version is declared
./gradlew dependencyInsight --dependency spring-cloud-stream --configuration runtimeClasspath
```

On Windows, use `gradlew.bat`. When examining the output, pay attention to the versions of `spring-cloud-stream`, the binder, Spring Integration, and the broker client library. If the same library has multiple version requests, understand Maven's or Gradle's version selection rules and identify which dependency introduces that version into the tree.

A successful build is a good signal, but it is not enough to confirm the configuration is production-ready. Run application tests, binding tests with the test binder, and integration tests with a real broker or equivalent environment. For Kafka, RabbitMQ, and Pulsar, also verify permissions, resource provisioning, routing, consumer groups, or subscriptions according to the chosen binder.

## 8. Common Dependency Configuration Mistakes

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Class or binder not found at startup | Binder dependency missing or wrong artifact used | Inspect the dependency tree and binder documentation for the version in use. |
| `NoSuchMethodError` or `ClassNotFoundException` | Incompatible Spring Cloud modules or foundational libraries | Check Spring Boot, the Spring Cloud BOM, and any overridden versions. |
| Dependencies downloaded but no active bindings | Binder library present, but function not selected or binding not configured | Check `spring.cloud.function.definition`, binding names, and destination configuration. |
| Application connects to the wrong broker when multiple binders exist | Appropriate binder not specified for the binding, or unexpected default configuration | Declare the binder for each binding and configure the corresponding connection settings. |
| Tests pass but production application lacks libraries | Binder or required library placed in a test-only scope | Put runtime binders in `implementation` or the appropriate compile/runtime scope; keep only the test binder in test scope. |
| Upgrading one dependency causes errors in another module | Custom version pin drifts from the BOM or causes transitive dependency conflicts | Remove unnecessary version pins, inspect the dependency tree, and upgrade under a unified plan. |

Do not try to fix issues by randomly pinning the latest version on individual dependencies. First identify which component manages versions, which dependency pulls in the conflicting version, and what the current release train supports. Only override dependency management when there is a clear requirement, proper testing, and documented justification.

## 9. Safe Dependency Upgrade Workflow

When you need to upgrade Spring Boot or Spring Cloud, follow a verifiable cycle:

1. Record the current Java, Spring Boot, Spring Cloud release train, and binder versions in use.
2. Choose a Boot and Cloud pair confirmed by the compatibility table; check the minimum Java requirement.
3. Update the BOM or parent/plugin version in one centralized place.
4. Run dependency tree or dependency insight to find changed versions and overridden dependencies.
5. Compile, then run unit tests and binder tests.
6. Run integration tests with the corresponding broker, including sending/receiving messages, retries, and DLQs if the application uses those features.
7. Verify deployment configuration, runtime image, and production environment before releasing.

For applications with Kafka Streams, also check the Kafka Streams version used by the binder, state store recovery, and topology compatibility after upgrading. For RabbitMQ or Pulsar, check changes in the client and binder related to acknowledgements, subscriptions, routing, or provisioning.

## 10. Maven or Gradle?

Both tools support Spring Boot and Spring Cloud Stream well. Maven is often a good fit for projects that want a clear XML structure, uniform build conventions, and Maven lifecycle plugins. Gradle fits projects needing flexible build scripts, convention-plugin configuration, or multi-module management with Kotlin/Groovy DSLs.

Choosing between them should be based on team standards, CI/CD pipelines, and how existing modules are built. There is no need to switch from Maven to Gradle just to use Spring Cloud Stream. What matters is having a single clear place to manage versions, using a compatible Spring Boot/Spring Cloud pair, and verifying effective dependencies before deployment.

## Conclusion

To initialize a Spring Cloud Stream application, pick a Spring Boot version compatible with Java, select a Spring Cloud release train from the compatibility table, import the `spring-cloud-dependencies` BOM, and declare the required binder. Maven does this with `dependencyManagement`; Gradle can use the Spring Dependency Management plugin or `platform`. When versions are managed centrally and the dependency tree is verified, the application has a stable foundation to move on to configuring functions, bindings, destinations, consumer groups, and message delivery mechanisms.
