# Choosing Compatible Java, Spring Boot, and Spring Cloud Release Train Versions

The `SPRING_CLOUD_CIRCUIT_BREAKER` module uses Spring Cloud CircuitBreaker to protect calls between services when a dependency is slow or unavailable. Before configuring `CLOSED`, `OPEN`, `HALF_OPEN` states, fallbacks, or sliding windows, you need to prepare a compatible toolchain. Java, Spring Boot, and Spring Cloud are released on separate cadences; picking valid individual versions while pairing the wrong release train can still prevent the application from starting or cause library linkage errors.

This lesson guides you through choosing a JDK, choosing Spring Boot, pairing the right Spring Cloud Release Train, declaring the BOM, and verifying the environment for a project using Resilience4j. Specific versions are current examples at the time of writing; when starting a new project or upgrading, verify the compatibility matrix and support lifecycle on the official Spring website.

## 1. Understanding the Role of Each Version

A Spring Cloud CircuitBreaker project involves several related version layers:

| Component | Role | What to Choose |
|---|---|---|
| JDK | Compiles and runs the Java application | A version within the range supported by Spring Boot and project libraries |
| Spring Boot | Provides the application foundation, auto-configuration, and baseline dependency management | A stable version in a branch supported by the Spring Cloud Release Train |
| Spring Cloud Release Train | A BOM grouping Spring Cloud versions compatible with each other and with a Spring Boot generation | The train corresponding exactly to the Spring Boot branch |
| Spring Cloud CircuitBreaker | Abstraction for invoking Circuit Breakers through a unified API | The version managed by the Spring Cloud BOM |
| Resilience4j | Implementation of Circuit Breaker, Retry, Bulkhead, and resilience mechanisms | The version managed by the Spring Cloud starter |
| Maven or Gradle | Dependency resolution and build tool | A version meeting the requirements of Spring Boot and the project |

You should not pick individual Spring Cloud project versions by looking up the latest version on Maven Central. For example, Spring Cloud CircuitBreaker, Spring Cloud Commons, and Spring Cloud Config belong to the same release train; the BOM ensures these libraries use versions tested together.

You also need to distinguish between the JDK installed on your machine and the Java version targeted by the project. A machine can have multiple JDKs installed, but the IDE, Maven, Gradle, and CI must all use the intended JDK. If the terminal runs Java 21 while the IDE runs Java 17, build errors may appear in only one environment.

## 2. Choosing a Baseline Version Set

At the time of writing, the following illustrative version set can be used for a new project:

| Component | Example Version | Notes |
|---|---:|---|
| JDK | 21 LTS | Practical baseline, supported by Spring Boot 4.0 |
| Spring Boot | 4.0.10 | Specific patch release of the 4.0.x branch |
| Spring Cloud Release Train | 2025.1.5 (Oakwood) | Compatible with Spring Boot 4.0.x and 4.1.x |
| Gradle | 8.14 or later in the 8.x branch, or 9.x | Spring Boot 4.0 requires Gradle 8.14+ or 9.x |
| Maven | 3.6.3 or later | Minimum version supported by Spring Boot 4.0 |

Spring Boot 4.0.10 requires a minimum of Java 17 and is compatible up to Java 27. Therefore, JDK 21 is a suitable LTS choice for this example; JDK 25 can be used if your IDE, build plugins, and remaining project libraries also support it. There is no need to use the newest JDK just because it is newer: choose a version tested across both development and deployment environments.

Spring Cloud 2025.1.5 was released on 2026-11-20 and is compatible with Spring Boot 4.0.x and 4.1.x. If a project is using Spring Boot 3.5.x, the corresponding release train is Spring Cloud 2025.0.x. Do not pair Spring Boot 4.0.x with Spring Cloud 2025.0.x; these are two incompatible generations according to the release train matrix.

Reference matrix for common generations:

| Spring Boot | Spring Cloud Release Train | Notes |
|---|---|---|
| 4.0.x, 4.1.x | 2025.1.x (Oakwood) | Use the latest published service release for the train |
| 3.5.x | 2025.0.x (Northfields) | Suitable for applications on the Boot 3.5 generation |
| 3.4.x | 2024.0.x (Moorgate) | Older branch; check support status before choosing for a new project |
| 3.2.x, 3.3.x | 2023.0.x (Leyton) | Legacy branch; use only when specific compatibility constraints apply |

This table describes the compatibility relationship between generations and does not claim that every patch of these branches is still supported. Before deciding, check the Spring Cloud page to see which release trains remain within their support window and pick the latest service release of that train.

## 3. Verifying the JDK and Build Tools

Install a full JDK rather than just a JRE. The JDK provides the `javac` compiler, diagnostic tools, and the runtime needed to build the application.

In your terminal, check:

```bash
java -version
javac -version
```

Both commands should display the same JDK generation. Also check the environment configuration:

- `JAVA_HOME` points to the desired JDK directory.
- `PATH` prioritizes `%JAVA_HOME%\bin` on Windows or `$JAVA_HOME/bin` on Linux/macOS.
- The IDE is configured to use the same JDK for Project SDK, Maven importer, and Gradle JVM.
- CI uses the same JDK generation as the development environment.

Check Maven:

```bash
mvn -v
```

Check the project's Gradle Wrapper:

```bash
./gradlew -version
```

On Windows, you can run:

```powershell
.\gradlew.bat -version
```

Gradle Wrapper stores the Gradle version inside the project, ensuring every team member and CI uses the same build tool without depending on a globally installed Gradle. With Maven, you can use Maven Wrapper (`./mvnw` or `mvnw.cmd`) to pin the Maven version for the project.

Do not only check `java -version` in the terminal. Maven and Gradle may be launched by a different JDK due to `JAVA_HOME`, IDE settings, or daemon configuration. Read the JVM section in the output of `mvn -v` and `gradlew -version` to confirm accurately.

## 4. Creating a Project with Spring Initializr

Spring Initializr helps generate a project skeleton with the selected Spring Boot version and build tool.

1. Open [Spring Initializr](https://start.spring.io).
2. Choose Project as Gradle or Maven according to your team's standard.
3. Choose Java as the language.
4. Select Spring Boot 4.0.10 in this example set.
5. Set appropriate Group, Artifact, Name, and Packaging.
6. Select Java 21.
7. Add the required application starters, such as Spring Web MVC or WebFlux and Spring Boot Actuator.
8. Generate, extract, and open the project in your IDE.

Spring Initializr can manage baseline versions when creating the project. After generating the project, you still need to add the compatible Spring Cloud BOM and the CircuitBreaker starter. Do not manually add multiple individual Spring Cloud versions to each dependency.

If you are working on an existing repository, read the existing build configuration in that project before upgrading. Keep the build tool and Spring Boot branch unchanged if the application has constraints; determine the corresponding release train before changing versions. Do not upgrade Spring Cloud CircuitBreaker alone while skipping the Spring Cloud BOM.

## 5. Declaring the Spring Cloud BOM with Gradle

A BOM (Bill of Materials) is a set of dependency constraints that helps Gradle select Spring Cloud versions tested together by the release train team. With Gradle Groovy DSL, an illustrative configuration is as follows:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.10'
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
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

If the project uses Kotlin DSL (`build.gradle.kts`), you can declare the equivalent:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.0.10"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

extra["springCloudVersion"] = "2025.1.5"

dependencyManagement {
    imports {
        mavenBom("org.springframework.cloud:spring-cloud-dependencies:${property("springCloudVersion")}")
    }
}

dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

In both examples, do not specify a version directly for `spring-cloud-starter-circuitbreaker-resilience4j`. The Spring Cloud BOM will manage the corresponding version. The Spring Boot plugin manages Spring Boot dependencies; the Spring Cloud BOM manages dependencies in the Spring Cloud ecosystem. These two mechanisms complement each other.

If the project uses Gradle without the `io.spring.dependency-management` plugin, you can import the BOM using a native Gradle platform:

```groovy
dependencies {
    implementation platform('org.springframework.cloud:spring-cloud-dependencies:2025.1.5')
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
}
```

Choose only one consistent way to manage the BOM in the project. Avoid importing multiple different release trains or manually declaring versions that override dependencies managed by the BOM.

## 6. Declaring the Spring Cloud BOM with Maven

If using Maven, the Spring Boot parent manages common Spring Boot dependencies and plugins. Import the Spring Cloud BOM in `dependencyManagement` to manage Spring Cloud starters:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.0.10</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
    <spring-cloud.version>2025.1.5</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${springCloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

The snippet above shows the sections to place inside the `project` tag of `pom.xml`; keep the other project details, plugins, and dependencies that the application needs. If not using the Spring Boot parent, you can import both the Spring Boot BOM and the Spring Cloud BOM, but you must manage the order and version sources clearly.

Do not add `<version>` to the CircuitBreaker starter when the BOM already manages it. If Maven reports a missing version, check whether the BOM is inside `dependencyManagement` and whether the artifact coordinates are accurate.

## 7. Choosing Web MVC or WebFlux for Practice

Spring Cloud Circuit Breaker can wrap both synchronous and reactive calls. Choose the web stack according to your application's processing model:

| Requirement | Common Choice |
|---|---|
| Synchronous controllers and clients, handling requests in the Servlet model | Spring MVC and a synchronous HTTP client |
| Non-blocking pipeline using Reactor and WebClient | Spring WebFlux |
| Application already uses Spring MVC and only needs Circuit Breaker for synchronous calls | Keep Spring MVC; no need to migrate the entire application to WebFlux |
| Application needs end-to-end reactive processing | Use WebFlux and avoid calling `block()` inside the pipeline |

Adding the Resilience4j starter does not automatically make an application reactive. For reactive flows, use the `ReactiveCircuitBreakerFactory` API and ensure fallbacks also return a publisher such as `Mono` or `Flux`. For synchronous flows, use `CircuitBreakerFactory`. Do not mix both calling styles in the same pipeline in a way that blocks the event loop.

If your practice exercises require both approaches, create two separate modules or two small separate examples. That makes the dependencies and configuration of each style easier to understand and verify.

## 8. Verifying Versions After Project Creation

After configuring, verify the toolchain and dependency tree before writing Circuit Breaker logic.

With Gradle:

```bash
./gradlew -version
./gradlew dependencies --configuration runtimeClasspath
./gradlew clean test
```

On Windows:

```powershell
.\gradlew.bat -version
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat clean test
```

With Maven:

```bash
mvn -v
mvn dependency:tree
mvn clean verify
```

In the dependency tree, confirm the following points:

- Spring Boot dependencies belong to the expected 4.0.x branch in the example.
- Spring Cloud dependencies belong to the 2025.1.x release train.
- Spring Cloud CircuitBreaker and Resilience4j are resolved from the corresponding BOM.
- Multiple versions of Spring Framework or Spring Cloud Commons do not appear together due to manual version declarations.
- The Java compiler and runtime use the selected JDK.

Spring Cloud includes a compatibility verifier to detect certain incompatible Spring Boot combinations at application startup. If the application reports that the release train does not support the current Spring Boot version, fix the Boot or Cloud version according to the matrix. Do not disable the verifier just to bypass the error; disabling the check does not make the two libraries compatible.

## 9. Common Environment Errors

| Symptom | Possible Cause | How to Check and Resolve |
|---|---|---|
| `UnsupportedClassVersionError` | Runtime JDK is older than the compiled bytecode | Check `java -version`, IDE runtime, and CI configuration |
| Build succeeds in terminal but IDE reports errors | IDE uses a different JDK or Gradle JVM | Synchronize Project SDK, Gradle JVM, and Maven importer |
| `Spring Boot ... is not compatible with this Spring Cloud release train` | Wrong pairing of Boot and Cloud branches | Check the compatibility matrix and select the right release train |
| Spring Cloud dependency version not found | BOM not imported or BOM does not apply to the dependency | Check `dependencyManagement` or `platform(...)` |
| `NoSuchMethodError` or `ClassNotFoundException` at runtime | Dependency version mismatch or overridden version | Inspect the dependency tree, remove manual versions, and use the BOM |
| Maven/Gradle fails to download dependencies | Proxy, network, repository, or corrupted build cache | Check repositories and proxy; try refreshing dependencies if needed |
| Builds locally but fails in CI | Different JDK, build tool, or environment variables | Use Wrapper, pin the JDK toolchain, and align CI configuration |

When encountering compatibility errors, troubleshoot in order: confirm the running JDK, confirm the Spring Boot version, confirm the Spring Cloud BOM, and then inspect the dependency tree. Changing one version layer at a time makes it easier to pinpoint the cause.

## 10. Environment Preparation Checklist

Before starting Circuit Breaker practice, verify:

- [ ] A suitable JDK is installed, and both `java -version` and `javac -version` show the right version.
- [ ] IDE, terminal, Maven/Gradle, and CI use a consistent JDK.
- [ ] A still-supported Spring Boot version has been selected.
- [ ] A Spring Cloud Release Train matching the Spring Boot compatibility matrix has been selected.
- [ ] The Spring Cloud BOM is imported and BOM-managed starter versions are not manually pinned.
- [ ] The `spring-cloud-starter-circuitbreaker-resilience4j` starter has been added.
- [ ] Spring MVC or WebFlux has been chosen according to the processing model.
- [ ] The build tool Wrapper has a compatible version and the project builds successfully.
- [ ] The compatibility verifier remains enabled to catch incompatible configurations.

Once the checklist passes, the environment is ready for hands-on exercises on configuring Resilience4j, fallback, timeout, bulkhead, reactive flows, and metrics monitoring. If you change Spring Boot or Spring Cloud later, re-check the entire version matrix before updating.

## References

- [Spring Cloud — Release Trains and Compatibility Matrix](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2025.1.5 — Release Announcement](https://spring.io/blog/2026/11/20/spring-cloud-2025-1-5-has-been-released/)
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Initializr](https://start.spring.io)
- [Spring Cloud CircuitBreaker Reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
