# Choosing Compatible Spring Boot and Spring Cloud Release Train Versions

## Objectives

Spring Cloud is built on top of Spring Boot and provides dedicated libraries for discovery, load balancing, OpenFeign, gateway, circuit breaker, and many other distributed system capabilities. These libraries must be compatible with the Spring Boot and Spring Framework generation that the application is using. Choosing an incompatible version pair can cause the project to fail dependency resolution, fail to start, or encounter runtime compatibility errors.

In this lesson, you will learn how to:

- Read the compatibility matrix between Spring Boot and Spring Cloud Release Train.
- Distinguish between the Spring Boot version, the Spring Cloud Release Train version, and individual Spring Cloud module versions.
- Select a stable version pair based on project requirements.
- Declare the Spring Cloud BOM in Maven or Gradle to synchronize dependencies.
- Verify the Java version, build tool, and resolved dependencies before starting to configure Spring Cloud LoadBalancer.

## 1. Why Must You Choose the Right Version Pair?

Spring Boot manages the application foundation such as Spring Framework, auto-configuration, logging, embedded servers, and many core libraries. Spring Cloud adds capabilities for distributed systems, including service discovery and client-side load balancing.

A Spring Cloud version is built and tested against specific generations of Spring Boot. When combining two incompatible generations, issues can appear at multiple levels:

- **Dependency resolution**: a module requests a library version that does not exist or conflicts with the version managed by Boot.
- **Compile time**: APIs or data types have changed, causing source code compilation to fail.
- **Application startup**: auto-configuration cannot find a class, method, or bean expected by a module.
- **Runtime**: the application starts up, but fails when performing discovery, selecting a `ServiceInstance`, or calling a service.

Therefore, version selection must start from the official compatibility matrix. You should not assume that Spring Boot `4.0.x` will always use Spring Cloud `4.0.x`: Spring Cloud uses a different versioning scheme.

## 2. Understanding the Versioning Scheme

### 2.1. Spring Boot

Spring Boot uses semantic-style versions in the `MAJOR.MINOR.PATCH` format, for example `4.0.9` or `4.1.2`.

- `MAJOR`: major generation, which may contain changes that need review when upgrading.
- `MINOR`: feature release branch.
- `PATCH`: bug-fix and compatibility updates within the same branch.

When documentation refers to Spring Boot `4.0.x`, the `x` represents patch releases in the `4.0` branch, such as `4.0.7`, `4.0.8`, or `4.0.9`. Projects should generally use the latest supported stable patch release within the chosen branch.

### 2.2. Spring Cloud Release Train

Spring Cloud uses Calendar Versioning (CalVer) in the `YYYY.MINOR.MICRO` format, for example `2025.1.4`.

- `YYYY`: year of the Release Train generation.
- `MINOR`: Release Train branch within that year.
- `MICRO`: service release within the same Release Train, containing bug fixes and compatibility improvements.

The first two segments identify the Release Train generation. For example, `2025.1.0`, `2025.1.2`, and `2025.1.4` all belong to the `2025.1` generation. Do not mistake `2025.1` for Spring Boot `2025.1`, and do not infer the Spring Cloud version from the Spring Boot version number.

A Release Train bundles multiple Spring Cloud projects. Each module has its own version number. For example, Release Train `2025.1.4` manages modules such as Spring Cloud Commons and Spring Cloud OpenFeign on the `5.0.x` branch. You should use the Release Train BOM to keep module versions synchronized.

## 3. Reading the Spring Boot and Spring Cloud Compatibility Matrix

As of **November 17, 2026**, the main version pairs to recognize are as follows:

| Spring Boot | Spring Cloud Release Train | Status and Usage |
|---|---|---|
| `4.0.x` | `2025.1.x` | Compatible pair belonging to the current stable Spring Cloud generation. |
| `4.1.x` | `2025.1.x` | Supported starting from Spring Cloud `2025.1.2`; `2025.1.4` supports Boot `4.1.2`. |
| `3.5.x` | `2025.0.x` | Compatible pair for Boot 3.5 applications; `2025.0.3` is the final OSS release and OSS support ended on June 30, 2026. |
| `4.2.0-RC2` | `2026.0.0-RC2` | Preview release (Release Candidate), suitable for testing new features, not yet a stable choice for production. |

Spring Cloud `2025.1.4` is the latest GA release at the time of writing. It is built on Spring Boot `4.0.9` and officially supports Spring Boot `4.1.2`. When starting a new project, the `Spring Boot 4.0.9 + Spring Cloud 2025.1.4` pair is a concrete, stable choice for practicing in this lesson. If a project has already standardized on Boot `4.1.2`, the same `2025.1.4` Release Train can be used.

Spring Cloud `2025.0.3` remains a published release for Spring Boot `3.5.x`, but it is the final OSS release of the `2025.0.x` branch; OSS support ended on June 30, 2026. When maintaining an existing Boot 3.5 application, you should evaluate the support policy and plan an upgrade. You should not choose an end-of-support branch for a new project that requires long-term security updates.

Spring Cloud `2026.0.0-RC2` corresponds to Spring Boot `4.2.0-RC2`. The `RC` suffix stands for Release Candidate, meaning a pre-release version. Only use this pair in an intentional testing environment; do not mix an RC version with GA dependencies and treat it as a supported production configuration.

> The compatibility matrix is only the starting point. For specific patch versions, read the Release Train release notes to check which Boot version is supported from which release. For example, support for the Boot `4.1.x` line started in Spring Cloud `2025.1.2`, not automatically in every earlier `2025.1.x` release.

## 4. Process for Selecting Versions for a Project

Follow this order:

1. **Determine the project state.** If the project already exists, read the current Spring Boot version from `pom.xml`, `build.gradle`, or `build.gradle.kts`. If it is a new project, identify Java, library, and deployment platform requirements before choosing Boot.
2. **Determine the Boot branch to use.** Choose a supported Boot branch that matches the runtime environment. Do not upgrade the major version just because a newer one exists if the project still depends on incompatible libraries.
3. **Consult the Release Train matrix.** Find the Release Train corresponding to the chosen Boot branch on the official Spring Cloud page.
4. **Select the latest GA release in that Release Train.** Service releases typically include bug fixes and compatibility updates. Do not pick `M`, `RC`, or `SNAPSHOT` releases if the goal is a stable project.
5. **Check the release notes.** Confirm that the exact Boot version in use falls within the support scope of that Cloud release; also check changes affecting the modules you plan to use, such as LoadBalancer, Netflix Eureka, or OpenFeign.
6. **Verify Java and the build tool.** The JDK, Maven, or Gradle version must meet the requirements of the chosen Spring Boot version.
7. **Declare the BOM and run a test build.** Let the BOM manage the Spring Cloud modules, then inspect resolved dependencies and run a build before adding discovery or load balancing configuration.

If you want to scaffold a new project quickly, you can use [Spring Initializr](https://start.spring.io/), choose the Spring Boot version and required dependencies. Initializr will add the corresponding Spring Cloud BOM to the Maven or Gradle configuration. After generating the project, still verify the generated versions and support status before putting them into use.

## 5. Choosing Compatible Java and Build Tool Versions

Spring Boot `4.0.9` requires a minimum of Java 17. Its documentation specifies support for Maven `3.6.3` or later and Gradle `8.14` or later in the 8.x branch or the 9.x branch.

| Component | Requirement for the Spring Boot 4.0.9 example |
|---|---|
| JDK | Java 17 or later |
| Maven | 3.6.3 or later |
| Gradle | 8.14 or later in the 8.x branch, or 9.x |
| Spring Cloud | Compatible Release Train, e.g., `2025.1.4` |

Check the actual JDK used by your terminal and IDE:

```bash
java -version
javac -version
```

For Maven:

```bash
mvn -version
```

For Gradle:

```bash
gradle --version
```

In a team project, you should commit the Maven Wrapper (`mvnw`, `mvnw.cmd`) or Gradle Wrapper (`gradlew`, `gradlew.bat`). The wrapper ensures every team member and CI pipeline uses the same build tool version declared in the repository, reducing discrepancies caused by different local Maven or Gradle installations.

## 6. Declaring Versions Using the Spring Cloud BOM

### 6.1. What Does the BOM Do?

A BOM (Bill of Materials) is a specialized POM that manages dependency versions. Spring Cloud provides the `spring-cloud-dependencies` BOM for each Release Train. When the BOM is imported, Maven or Gradle can select the matching versions for Spring Cloud starters and modules without declaring individual versions on each dependency.

In a Spring Boot project:

- The Spring Boot parent or Spring Boot BOM manages dependencies in the Boot ecosystem.
- The Spring Cloud BOM manages dependencies in the Cloud ecosystem.
- The Spring Boot plugin version is the application build plugin version, not the Spring Cloud version.

You should not manually assign different Spring Cloud versions to individual starters. Doing so can put Cloud modules from multiple Release Trains on the classpath, causing API conflicts or unpredictable behavior.

### 6.2. Maven Configuration

The example below uses Spring Boot `4.0.9`, Java 17, and Spring Cloud `2025.1.4`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>load-balancing-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.1.4</spring-cloud.version>
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
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>
    </dependencies>
</project>
```

When adding a discovery provider, such as Eureka, declare the corresponding starter without adding a version if the dependency is managed by the BOM:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
```

If the project does not inherit from `spring-boot-starter-parent`, you can import the `spring-boot-dependencies` BOM in the appropriate structure, and then import the `spring-cloud-dependencies` BOM. Ensure clear ordering and dependency management rules so multiple BOMs do not unintentionally override the same dependency.

### 6.3. Gradle Configuration

Example using Gradle Groovy DSL and `platform` to import the Spring Cloud BOM:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.9'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

ext {
    springCloudVersion = '2025.1.4'
}

dependencies {
    implementation platform("org.springframework.boot:spring-boot-dependencies:4.0.9")
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
```

If the project uses Kotlin DSL (`build.gradle.kts`), the approach is similar: declare the Boot plugin at the chosen version, import the BOM with `implementation(platform("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"))`, and then declare the starters without specifying individual versions.

## 7. Verifying Dependencies After Configuration

Simply declaring the right version in the build file is not enough. You should inspect the actual resolved versions after Maven or Gradle resolves dependencies, because transitive dependencies, other BOMs, or project constraints can affect the result.

### 7.1. Checking with Maven

Run using the Maven Wrapper:

```bash
./mvnw -version
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.cloud
./mvnw clean verify
```

In PowerShell on Windows, use `.\mvnw.cmd` instead of `./mvnw` if the environment cannot run Unix scripts. The dependency tree output should show Spring Boot on the chosen branch and the Spring Cloud modules managed by the BOM from the same Release Train.

### 7.2. Checking with Gradle

Run using the Gradle Wrapper:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
./gradlew clean build
```

`dependencies` displays the dependency tree for the runtime classpath. `dependencyInsight` helps trace why a specific version was selected, which is useful when multiple dependencies request the same module.

### 7.3. Enabling Spring Cloud Compatibility Verification

Spring Cloud Commons includes a Compatibility Verification mechanism to check the Spring Boot version on the classpath. In Spring Cloud Commons `5.0.4`, the `spring.cloud.compatibility-verifier.enabled` property defaults to `false`. You can enable this check in development or CI environments:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

When an incompatible version pair is detected, this mechanism can output a report explaining that the Boot version is not supported. Fix the version pair according to the compatibility matrix and release notes. Do not disable the check just to hide an unresolved conflict.

## 8. Common Mistakes When Selecting Versions

| Symptom | Common Cause | Resolution |
|---|---|---|
| Maven reports artifact or version not found | Typo in artifact coordinates, using an unreleased version, or repository lacks the artifact | Verify dependency coordinates, GA/RC status, and repositories. |
| Application reports Boot is incompatible with Cloud | Selected a Release Train that does not support the current Boot branch | Consult the compatibility matrix and select the right Release Train. |
| `NoSuchMethodError` or `ClassNotFoundException` occurs | Spring or Spring Cloud modules have mixed versions | Inspect the dependency tree, remove manual versions, and let the BOM manage them. |
| Build succeeds but startup fails | Incompatible auto-configuration or module APIs | Check the stack trace, release notes, and actual versions on the runtime classpath. |
| IDE compiles fine but CI fails | Different JDK or build tool versions across environments | Use the Wrapper, standardize the JDK/toolchain, and check `java -version`. |
| Discovery starter does not work | Only LoadBalancer was added without a discovery provider or instance list | Add a suitable discovery implementation or configure a static instance source for testing environments. |

An error like `NoSuchMethodError` usually indicates that the runtime classpath differs from the API against which the source code or module was compiled. Trace the dependency before trying to add another library to work around the error.

## 9. Safely Upgrading Spring Boot or Spring Cloud

Upgrading Spring Boot and Spring Cloud is a change that can affect APIs, auto-configuration, and transitive dependencies. You should follow these steps:

1. Record the current Boot, Cloud BOM, JDK, Maven/Gradle, and starter versions.
2. Look up the Release Train that supports the target Boot version.
3. Read the Spring Boot and Spring Cloud release notes for the relevant branches; pay attention to breaking changes, deprecated APIs, and configuration changes.
4. Update Boot and the Cloud BOM together as a published compatible pair.
5. Remove manual Spring Cloud module versions if they conflict with the BOM.
6. Run the dependency tree check to inspect the classpath after upgrading.
7. Run unit tests, integration tests, and smoke tests for discovery, instance selection, and service invocation flows.
8. Check startup logs, health endpoints, metrics, and traces before deploying.

For an application currently on Spring Boot 3.5.x, do not just change Boot to 4.0.x while keeping Spring Cloud `2025.0.x`. Upgrade Spring Boot to `4.0.x` or `4.1.x` and Spring Cloud to the `2025.1.x` Release Train together, then follow the Spring Boot 4 migration documentation and Spring Cloud release notes. Also check third-party libraries outside Spring, as they may not yet support the new Spring generation.

## 10. Checklist Before Configuring LoadBalancer

- [ ] Identified the Spring Boot branch and checked its support status.
- [ ] Looked up the correct Spring Cloud Release Train in the official compatibility matrix.
- [ ] Selected the latest GA release in the appropriate Release Train.
- [ ] Checked the release notes for the specific Boot patch and Cloud service release.
- [ ] JDK meets the Spring Boot requirements.
- [ ] Maven or Gradle meets the requirements and the project uses the Wrapper.
- [ ] Spring Cloud BOM is properly imported.
- [ ] Spring Cloud starters do not have manual versions assigned outside the BOM.
- [ ] Dependency tree shows Boot and Cloud modules resolved consistently.
- [ ] Basic build and tests run successfully.

## Summary

The Spring Cloud version must be selected according to the Spring Boot generation supported by the Release Train. As of November 17, 2026, the `Spring Boot 4.0.9 + Spring Cloud 2025.1.4` pair is a concrete GA configuration suitable for starting this hands-on lesson; Spring Cloud `2025.1.4` also supports Boot `4.1.2`. Use the Spring Cloud BOM to keep modules synchronized, verify the JDK and build tool, and inspect the dependency tree before integrating discovery and load balancing.

## References

- [Spring Cloud — Getting Started and Release Train Compatibility Matrix](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2025.1.4 — Release Announcement and Compatible Spring Boot Pair](https://spring.io/blog/2026/10/23/spring-cloud-2025-1-4-has-been-released/)
- [Spring Cloud 2025.0.3 — Final OSS Release and End-of-Support Date](https://spring.io/blog/2026/06/11/spring-cloud-2025-0-3-aka-northfields-has-been-released/)
- [Spring Cloud Release — Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Cloud Commons — Compatibility Verification](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
