# Choosing Compatible Java, Spring Boot, Spring Cloud BOM, and Stream Versions

Before writing a Supplier, Function, or Consumer function, you need to choose a set of Java and Spring versions that work together. Spring Cloud Stream sits on top of Spring Boot and uses Spring Cloud Function along with a binder to connect to a messaging system. Therefore, picking the latest version of each library independently can easily cause dependency conflicts or an unsupported combination.

The safe workflow is to determine the JDK and Spring Boot version first, check the compatibility table to choose the Spring Cloud release train, and then let the release train's BOM manage the Spring Cloud Stream version and related Spring Cloud components. Only after that should you choose the binder for Kafka, RabbitMQ, or Pulsar and verify the corresponding client version.

## 1. Understanding the Version Layers

A Spring Cloud Stream application typically has the following component layers:

| Component | Version management responsibility |
|---|---|
| JDK | Java compiler and runtime environment; must meet the requirements of Spring Boot and the libraries used |
| Spring Boot | Provides the application foundation, auto-configuration, build plugins, and BOM for many foundational libraries |
| Spring Cloud release train | A collection of Spring Cloud projects whose versions are tested together; the train's BOM manages Spring Cloud dependencies |
| Spring Cloud Stream | Provides the messaging programming model, binding, and binder abstraction; the version is typically managed via the Spring Cloud BOM |
| Binder and client library | Connects to a specific broker, such as Kafka, RabbitMQ, or Pulsar; has its own additional compatibility requirements |
| Broker | The Kafka, RabbitMQ, or Pulsar server deployed in the runtime environment; the broker version must be compatible with the client and the features used |

These layers are related, but they do not replace one another. `spring-boot-dependencies` manages libraries within the Spring Boot ecosystem. `spring-cloud-dependencies` manages projects belonging to the Spring Cloud release train. A BOM is a set of version management rules; importing a BOM does not automatically add all libraries to your application.

For example, adding `spring-cloud-starter-stream-kafka` to dependencies is what brings the Kafka binder onto the classpath. Importing `spring-cloud-dependencies` lets Maven or Gradle know the compatible versions of the starter and related Spring Cloud libraries without specifying a version for each dependency.

## 2. Choosing the JDK and Target Java Version

### 2.1. Distinguishing the JDK, Java Compiler, and Java Runtime

The JDK is used to compile source code and run build tools. The packaged application needs a compatible Java runtime when deployed. In CI and production environments, you need to check both places because a developer machine may use a newer JDK than the server.

Three pieces of information need to be aligned:

- **JDK running the build:** the actual Java version that Maven or Gradle is using.
- **Java toolchain or compiler release:** the API and bytecode version that source code is compiled for.
- **JRE/JDK running the application:** the Java version on the server or in the container image.

You should not just look at `java -version` and conclude the build is using the right JDK. Maven and Gradle may run with a different Java due to `JAVA_HOME`, IDE settings, or toolchain configuration.

Check the environment:

~~~bash
java -version
javac -version
mvn -version
./gradlew --version
~~~

Only run the command corresponding to the build tool the project uses. On Windows, the Gradle Wrapper can be invoked with `gradlew.bat --version`; the Maven Wrapper can be invoked with `mvnw.cmd -version`.

### 2.2. Choosing a Java Version That Satisfies All Requirements

First, read the System Requirements section for the exact Spring Boot version. Each Boot line specifies a minimum Java version and supported Java range. Binders or third-party libraries may impose higher requirements. The chosen version must satisfy all of these constraints.

For new projects, Java LTS is usually easier to operate because of longer security update and support windows. Java 21 is a suitable example for the version set illustrated in this lesson. Spring Boot 4.x requires at least Java 17; choosing Java 21 still requires confirming that the specific Boot line, binder, and supporting libraries in use support that version.

Set the Java version explicitly in the build so each team member's machine does not choose a different level. For example, with Maven:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

With Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

A toolchain helps Gradle select the appropriate JDK for compilation. If CI or the deployment environment uses a different Java, explicitly configure that version in the pipeline and container image. Do not compile bytecode for a newer Java version than the production runtime can run.

## 3. Choosing Spring Boot Before Spring Cloud

Spring Boot manages many foundational dependencies such as Spring Framework, logging, JSON, web servers, and integration libraries. When choosing Boot, consider:

1. Whether the Boot line is still supported and receiving security fixes.
2. Whether your organization's Java version meets that Boot line's requirements.
3. Whether other critical libraries in the application have compatible versions.
4. Whether Maven or the Gradle Wrapper meets that Boot line's build requirements.
5. Whether CI systems, IDEs, and deployment images can use the same Java configuration.

With Maven, `spring-boot-starter-parent` is a common choice. The parent provides compiler configuration, plugins, and dependency management aligned with Spring Boot. If the project already has to inherit an internal parent POM, you can import the `spring-boot-dependencies` BOM instead of inheriting another parent.

With Gradle, the `org.springframework.boot` plugin combined with the dependency management plugin or BOM platform helps manage dependencies according to the same Boot line. Use the Gradle Wrapper committed in the repository so every machine and CI uses the same Gradle version.

Do not set your own versions for Spring Framework, Jackson, logging, or other foundational dependencies already managed by Boot unless there is a verified compatibility reason. Arbitrary overrides can break the version set tested by Spring Boot.

## 4. Checking the Compatibility Table to Choose a Spring Cloud Release Train

Spring Cloud is released as release trains. Version names use a calendar format `YYYY.MINOR.PATCH`, for example `2025.1.5`. The first two segments identify the release train; the last segment is the service release containing bug fixes and compatibility updates within that train.

Spring Cloud release trains have a compatibility table with Spring Boot generations. Use the official table at [Spring Cloud - Version Mappings](https://spring.io/projects/spring-cloud/) to choose the train according to the Boot version in use. Do not infer the Cloud version from the Boot version number or mechanically pick the same major number.

At the time of writing this lesson (24/11/2026), the Spring Cloud page publishes the following main pairings:

| Spring Cloud release train | Published compatible Spring Boot | Notes |
|---|---|---|
| 2025.1.x (Oakwood) | 4.0.x; 4.1.x from 2025.1.2 | The line used in the hands-on examples |
| 2025.0.x (Northfields) | 3.5.x | The support page marks this train as end-of-life |
| 2024.0.x (Moorgate) | 3.4.x | Legacy train, do not choose for new projects |

The table above shows compatibility relationships between lines, not a recommendation to use every patch release of Boot or Cloud. Once you have chosen a train, continue checking its support status and pick the latest maintained GA service release of that train.

Spring Cloud 2026.0.0 has been released and includes Spring Cloud Stream 5.1.0. However, the Version Mappings table on the Spring Cloud page at the time of writing does not yet list a Boot relationship for the 2026.0.x train. Do not assume that you can simply pair it with Spring Boot 4.2.x just because the two version numbers share the same year. Wait for or verify the official compatibility announcement before choosing this train for a project that requires an explicitly published combination.

### 4.1. Example of a Mapped Version Set

To illustrate a version set with a published compatibility relationship, you can use:

| Component | Illustrative version |
|---|---|
| JDK | Java 21 |
| Spring Boot | 4.1.3 |
| Spring Cloud release train | 2025.1.5 |
| Spring Cloud Stream | 5.0.5, managed by the release train |

Spring Cloud 2025.1.x supports Spring Boot 4.1.x starting from service release 2025.1.2. Release 2025.1.5 includes Spring Cloud Stream 5.0.5. Therefore, this example demonstrates how to pair versions based on published mappings and BOMs. When applying this to a real project, you should still pick the latest Boot patch release that fits your support policy and re-test the entire application.

## 5. Letting the Spring Cloud BOM Manage Spring Cloud Stream

After determining Spring Boot and the release train, import the `org.springframework.cloud:spring-cloud-dependencies` BOM. This BOM manages the Spring Cloud projects in the train, including Spring Cloud Function and Spring Cloud Stream.

You do not need to pick a `spring-cloud-stream` version separately if the application already uses a compatible Spring Cloud release train. Specifying separate versions for Stream or a binder can cause components within the same ecosystem to drift from the version set managed by the train.

The Spring Cloud BOM is BOM-only: it contains dependency management information and does not provide plugins or automatically add starters to the classpath. The application must still declare the dependencies it actually uses.

### 5.1. Maven Configuration with the Kafka Binder

The following example uses Spring Boot 4.1.3, Spring Cloud 2025.1.5, and Java 21. The versions in the example illustrate a combination with a published compatibility mapping; when starting a new project, check the latest service release on the official site before locking versions.

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.3</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>stream-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2025.1.5</spring-cloud.version>
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
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-stream-test-binder</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Key points to note:

- The parent POM manages dependencies and plugins belonging to Spring Boot.
- `spring-cloud.version` selects the right Spring Cloud release train.
- `spring-cloud-dependencies` manages the versions of Spring Cloud dependencies.
- `spring-cloud-starter-stream-kafka` adds the Kafka binder to the application.
- `spring-cloud-stream-test-binder` supports testing bindings without a real broker in suitable tests.
- Do not specify individual versions for Spring Cloud dependencies that are already managed by the BOM.

If your organization uses a custom parent POM, you can replace the parent section with a configuration that imports the `spring-boot-dependencies` BOM and configures the corresponding Maven plugins. There is no need to both inherit the Spring Boot parent and redundantly import the Boot BOM.

### 5.2. Gradle Configuration

With Gradle, you can use the Spring Boot plugin and the dependency management plugin to import the same release train BOM:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.3'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

ext {
    set('springCloudVersion', '2025.1.5')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-stream-kafka'

    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The Gradle Wrapper must use a Gradle version supported by the selected Spring Boot plugin. Do not only check the Gradle installed globally on the machine; check `gradle-wrapper.properties` because CI typically runs the Wrapper.

A Gradle project can also manage BOMs using `platform(...)` or `enforcedPlatform(...)`. Only use `enforcedPlatform` when you truly want to force versions across the entire dependency graph and fully understand the impact on other libraries. For standard Spring Boot setups, the dependency management plugin or `platform` BOM is sufficient.

## 6. Choosing a Binder by Broker

Spring Cloud Stream provides a common programming model, but a binder is a specific dependency that connects the application to a broker. Only add the binder the application needs. Do not add multiple binders at once unless there is a requirement to use multiple messaging systems.

| Broker | Commonly used dependency | Where to check compatibility |
|---|---|---|
| Apache Kafka | org.springframework.cloud:spring-cloud-starter-stream-kafka or spring-cloud-stream-binder-kafka | Spring Cloud Stream Kafka Binder reference; Kafka client and broker versions |
| RabbitMQ | org.springframework.cloud:spring-cloud-starter-stream-rabbit or spring-cloud-stream-binder-rabbit | Spring Cloud Stream Rabbit Binder reference; Rabbit client and broker versions |
| Apache Pulsar | org.springframework.pulsar:spring-pulsar-spring-cloud-stream-binder | Spring for Apache Pulsar and Pulsar Binder reference; Spring Pulsar, Pulsar client, and broker versions |

The Kafka and RabbitMQ binders belong to the Spring Cloud Stream ecosystem and are typically managed via the Spring Cloud release train BOM. The Pulsar binder is provided within the Spring for Apache Pulsar ecosystem; you need to check which BOM manages its artifacts and compatible versions. Do not assume that every dependency with `stream` in its name is managed by `spring-cloud-dependencies`.

For example, when switching from Kafka to RabbitMQ, replace the binder dependency and connection configuration, then re-verify broker-specific properties such as exchange, queue, routing key, and acknowledgement. With Pulsar, you also need to inspect schema configuration, subscription, tenant, namespace, and Pulsar binder-specific properties. Keeping the function code unchanged does not make all configuration properties or broker semantics identical.

### 6.1. Checking the Client and Broker

A binder typically pulls in the corresponding client library. You need to identify:

- The broker version running in development, staging, and production environments.
- The client version selected by the binder through dependency management.
- The broker features the application needs to use, such as transactions, headers, partitions, schemas, or acknowledgement mechanisms.
- The official compatibility matrix between client and broker.
- TLS, authentication, serializer, and plugin requirements in the deployment environment.

A newer client may be able to connect to an older broker, but not all features will be available. Conversely, upgrading the broker without checking the client and binder can alter protocol behavior. Therefore, you should run integration tests using the exact broker type and a version close to production.

## 7. Verifying Effective Dependency Versions

Declarations in the build file only express the project's requirements. The final resolved versions also depend on BOMs, transitive dependencies, and the build tool's resolution rules. After importing the BOM and adding the binder, inspect the dependency graph to see which versions the application actually uses.

With Maven:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.cloud,org.springframework.kafka,org.springframework.amqp,org.springframework.pulsar
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-stream --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
~~~

When reviewing the output, check the following points:

1. There is only one dominant Spring Boot line in the dependency graph.
2. Spring Cloud Stream, Spring Cloud Function, and the binder come from the same selected release train.
3. No old versions are pulled in unexpectedly.
4. Spring Kafka, Spring AMQP, or Spring Pulsar is compatible with the corresponding binder.
5. No dependencies are manually overridden without a documented reason and testing.

If you see the same library appearing in multiple versions, identify which dependency is pulling in the unwanted version. You can use dependency exclusions when justified, but you should not exclude a library just to make the build pass without understanding the runtime impact.

## 8. Building and Smoke Testing After Locking Versions

After configuring the JDK, Boot, Cloud BOM, and binder:

1. Verify the Java version actually used by the build tool.
2. Refresh dependencies in the IDE to sync with the build file.
3. Build the project using the Maven Wrapper or Gradle Wrapper.
4. Run unit tests and binder tests.
5. Run integration tests with the exact broker and client versions planned for deployment.
6. Start the application and check the logs for binder initialization, broker connection, destination, and consumer setup.
7. Send a test message and verify that the payload is received and processed correctly.

Example build commands:

~~~bash
./mvnw clean verify
~~~

Or:

~~~bash
./gradlew clean test
~~~

A successful build is a necessary condition, but it does not prove compatibility with the production broker. An in-JVM test binder cannot verify every specific behavior of Kafka, RabbitMQ, or Pulsar. You need integration tests covering connections, acknowledgements, partitioning, retries, DLQs, and schemas that the application uses.

## 9. Planning Version Upgrades

You should not simultaneously upgrade Java, Spring Boot, Spring Cloud, the binder, and the broker in a single large change without comprehensive regression testing. When upgrading, follow a traceable process:

1. Record the current version set from the dependency graph and runtime environment.
2. Read the release notes and migration guides for Spring Boot, Spring Cloud, and the binder.
3. Check the compatibility table to identify the target release train.
4. Choose the latest supported GA service release in that train.
5. Update the BOM and JDK as required; let the BOM manage related dependencies.
6. Address deprecated APIs or configurations, then run unit and integration tests.
7. Deploy to staging and monitor logs and metrics before upgrading production.

When a release train reaches end-of-life, the application may still run, but it will no longer receive bug fixes and security patches from that branch. Plan to migrate to a supported train instead of maintaining an old combination long-term just because it still builds.

M (milestone), RC (release candidate), and SNAPSHOT builds are for pre-release testing. Production should normally use a released GA version. If you need to try a preview build to evaluate a feature, lock the experimental version separately, document the risks, and prevent it from unintentionally becoming a release dependency.

## 10. Common Version Selection Mistakes

**Choosing Spring Cloud by year without checking the mapping table.** Release trains are tested against specific Spring Boot generations. Always select based on the official compatibility table.

**Using the latest Spring Cloud Stream with an older Spring Boot.** Stream may require versions of Spring Framework, Spring Cloud Function, or Spring Messaging that differ from those managed by the older Boot dependency set.

**Specifying individual versions for each Spring Cloud starter.** This can cause modules in the same release train to drift out of sync. Import the Spring Cloud BOM and omit versions from dependencies managed by the BOM.

**Assuming the Spring Cloud BOM replaces the Spring Boot BOM.** The two BOMs manage different sets of dependencies. Use the Boot parent or Boot BOM for the Boot foundation, while also importing the Cloud BOM for Spring Cloud projects.

**Upgrading versions only in the IDE.** The IDE may use a different JDK or Gradle than CI. Check the Wrapper, `JAVA_HOME`, toolchain, and runtime image.

**Ignoring the broker client version.** The application may compile but fail to support features or protocols required by the running broker. Check the binder, client, and broker together.

**Treating a successful build as sufficient.** A build does not fully verify connections, acknowledgements, retries, DLQs, schemas, or transactions. You must test against a real broker.

## 11. Version Selection Workflow for a New Project

When starting a Spring Cloud Stream project, you can follow this sequence:

1. Identify the Java LTS supported by your organization and check Spring Boot's minimum Java requirement.
2. Choose a supported Spring Boot line with a patch release suitable for your system.
3. Check the Spring Cloud Version Mappings table to determine the release train compatible with Boot.
4. Choose the latest maintained GA service release of that train.
5. Import the `spring-cloud-dependencies` BOM to manage Spring Cloud Stream, Function, and binders.
6. Add the exact binder for Kafka, RabbitMQ, or Pulsar; verify which BOM manages that binder.
7. Inspect the dependency tree to confirm the effective versions.
8. Build, run binder tests, and run integration tests against the corresponding broker.
9. Lock the JDK, Wrapper, and runtime image in CI/CD to reproduce the exact same version set.

By following this sequence, the application has a consistent version foundation. The development team can focus on designing functions, bindings, and message contracts while knowing clearly which dependency is responsible for managing each layer of the system.

## Official References

- [Spring Boot - System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java and build tool requirements for each Boot version.
- [Spring Cloud - Version Mappings](https://spring.io/projects/spring-cloud/): compatibility table between Spring Boot and Spring Cloud release trains.
- [Spring Cloud - Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions): support status and service releases.
- [Spring Cloud - Release History](https://github.com/spring-cloud/spring-cloud-release/releases): contents of each release train, including released Spring Cloud Stream versions.
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html): dependencies, binders, and Spring Cloud Stream configuration.
- [Spring Cloud Stream - Apache Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html): dependency and binder configuration for Pulsar.
