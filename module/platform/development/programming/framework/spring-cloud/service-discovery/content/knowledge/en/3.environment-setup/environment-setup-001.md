# Choosing Compatible Spring Boot, Spring Cloud Release Train, and JDK Versions

When building microservices with service discovery, three version layers must be selected together: the JDK used to compile and run the application, Spring Boot as the application foundation, and the Spring Cloud Release Train managing the distributed-system libraries. An incompatible version pair can cause an application to fail immediately at startup, even when the service discovery code itself has no bugs.

This lesson uses official release information as of November 24, 2026. New versions will continue to be released, so re-check the compatibility table before every project creation or upgrade.

## 1. Understanding the Role of Each Version

| Component | Role | What to Check? |
|---|---|---|
| JDK | Provides the JVM and compiler to compile and run Java applications | Minimum/maximum versions supported by Spring Boot and third-party libraries; the actual JDK used by the IDE, Maven, Gradle, and runtime environment |
| Spring Boot | Creates application structure, manages configuration, auto-configuration, web server, and core dependencies | Minimum Java version, supported build tools, and changes across major/minor versions |
| Spring Cloud Release Train | A coordinated set of Spring Cloud versions tested together, including Discovery, LoadBalancer, Eureka, Consul, and other cloud components | Which Release Train is compatible with the Spring Boot line in use; choose the latest service release within that train |

Spring Boot and Spring Cloud have two separate dependency management mechanisms. The Spring Boot parent or BOM manages Spring Boot libraries. The `spring-cloud-dependencies` BOM manages Spring Cloud modules. When both BOMs are imported properly, dependencies such as `spring-cloud-starter-netflix-eureka-client` typically do not need an explicit version declaration.

A Release Train is a release branch of the entire Spring Cloud ecosystem. For example, `2026.0.0` is a Release Train version; inside that train, Spring Cloud Netflix has its own module version. Do not take an individual module's version number and put it into `spring-cloud.version`.

## 2. Check the Spring Boot and Spring Cloud Compatibility Table First

Do not choose Spring Cloud simply because it is the latest version. Identify the Spring Boot line first, then select the Release Train officially published by Spring as compatible with that Boot line.

The reference table below reflects published information as of November 24, 2026:

| Spring Cloud Release Train | Compatible Spring Boot | Notes |
|---|---|---|
| `2026.0.0` (Paddington) | `4.2.0` | GA on November 20, 2026; the first release of this train is based on Spring Boot 4.2.0 |
| `2025.1.x` (Oakwood) | `4.0.x`; `4.1.x` starting from `2025.1.2` | Suitable for projects using Boot 4.0 or 4.1 |
| `2025.0.x` (Northfields) | `3.5.x` | The Spring Cloud page currently marks this train as end-of-life for community support |
| `2024.0.x` (Moorgate) | `3.4.x` | The Spring Cloud page currently marks this train as end-of-life for community support |

Spring Cloud 2026.0.0 was announced based on Spring Boot 4.2.0. The Spring Cloud page also clearly specifies the compatibility relationships for the 2025.1.x, 2025.0.x, and 2024.0.x trains. Trains marked with an asterisk on the project page have reached end of life; you should not choose them for a new system unless there is a requirement to maintain a legacy version or a separate support agreement.

Version selection rules:

1. Note the exact existing Spring Boot line, such as `4.2.x`, `4.1.x`, or `3.5.x`.
2. Look up the compatible Release Train in the table on the Spring Cloud page. Do not infer compatibility merely from nearby version numbers.
3. Choose the latest service release within the corresponding train. Service releases typically contain bug fixes and compatibility updates within the same train.
4. Keep the chosen Boot/Cloud pair consistent across all services in the same lab set or system, unless there is a separately tested upgrade plan.
5. If using an end-of-life train, document the reason and upgrade plan clearly. Do not treat a successful build as proof that the version is still supported.

## 3. Choosing a Suitable JDK

The JDK must satisfy the requirements of Spring Boot, Spring Cloud libraries, and every third-party library in the application. Boot's minimum Java version is only the first condition; another driver, SDK, or plugin may require a higher JDK.

For Spring Boot 4.2.0, the System Requirements documentation specifies:

- Minimum Java 17; published compatibility up to Java 27.
- Maven 3.6.3 or later.
- Gradle 8.x from 8.14 or later, or Gradle 9.x.

For tutorials and typical development environments, JDK 21 LTS is a balanced choice: above the minimum, supported by Boot 4.2.0, and generally well-compatible with existing Java libraries. JDK 25 is also within Boot 4.2.0's compatibility range; it can be chosen if the project's dependencies, plugins, CI, and deployment environment are confirmed to support it. Do not upgrade the JDK simply because a new version was just released.

Distinguish between three versions that can differ on the same machine:

- The JDK found by the `java` command via `PATH`.
- The JDK used by Maven or Gradle to run the build.
- The JDK toolchain used by the compiler to compile source code.

For example, `java -version` might return Java 25 while `mvn -v` shows Maven is running on Java 17 because `JAVA_HOME` points to a different directory. The IDE can also configure a separate Project SDK. Check all of these places to avoid a situation where a local machine builds successfully but CI or a container fails.

With Gradle, declaring a Java toolchain helps the build select the right compiler:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

With the Maven Spring Boot parent, you can set the Java version in properties:

```xml
<properties>
    <java.version>21</java.version>
</properties>
```

Setting the Java version in the build configuration does not install the JDK automatically. Both the build machine and runtime machine still need an appropriate JDK/JRE installed, or the corresponding toolchain/container configured.

## 4. Recommended Version Pair for New Projects

For a service discovery learning project started at the time this article was updated, you can use the following configuration:

| Component | Example Version |
|---|---|
| JDK | 21 LTS |
| Spring Boot | `4.2.0` |
| Spring Cloud Release Train | `2026.0.0` |
| Maven | `3.6.3+` (Maven Wrapper is recommended to pin the build version) |
| Gradle (if choosing Gradle) | `8.14+` or `9.x` (Gradle Wrapper is recommended) |

This is a version set with published compatibility relationships. When Spring releases a new patch, check the release notes and upgrade within the same train instead of manually replacing individual Spring Cloud dependencies.

### Maven Example

Core configuration snippet for `pom.xml` when using Spring Boot 4.2.0:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

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
    <!-- Service REST API -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>

    <!-- HTTP client used by Eureka Client -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-restclient</artifactId>
    </dependency>

    <!-- Do not declare a separate version: managed by Spring Cloud BOM -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

In this example, the Spring Boot parent manages Boot dependencies and Maven plugins; the Spring Cloud BOM manages the Eureka Client version and related Spring Cloud modules. Current Spring Cloud Netflix documentation requires a supported HTTP client on the classpath; the example uses `spring-boot-restclient`. If the application chooses WebClient, you need to configure the corresponding dependency according to the documentation for the version in use.

### Gradle Example

Equivalent configuration snippet for `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

ext {
    set('springCloudVersion', '2026.0.0')
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-restclient'
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
}
```

Do not declare versions for individual Spring Cloud starters when the BOM already manages them. If you manually pin a Spring Cloud module to a version outside the train, the dependency tree may contain modules that were not tested together.

## 5. Creating a Project with Spring Initializr

For new projects, [Spring Initializr](https://start.spring.io/) is a convenient way to generate the initial configuration:

1. Select Maven or Gradle and the Java language.
2. Choose a Spring Boot version matching the Spring Cloud Release Train you intend to use.
3. Choose a Java version supported by Boot and the dependencies; for example, select 21.
4. Select the dependencies needed for the lesson, such as Eureka Discovery Client or Consul Discovery.
5. Generate the project, open the build file, and verify that `spring-cloud-dependencies` has been added with the right train.

Initializr can add the corresponding BOM when you select Spring Boot and Spring Cloud projects. Even so, inspect `pom.xml` or `build.gradle` after downloading the project: verify the Boot version, Cloud BOM, Java version, and selected dependencies before writing code.

## 6. Verify the Environment Before Adding Discovery Logic

Run the following commands in the terminal inside the project directory:

```bash
java -version
mvn -v
./mvnw -v
```

With Gradle, check the JVM that Gradle uses:

```bash
./gradlew -version
```

On Windows, Maven Wrapper and Gradle Wrapper are typically invoked via `mvnw.cmd` and `gradlew.bat`.

After adding dependencies, inspect the dependency tree to confirm versions are managed consistently:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.cloud
./mvnw clean verify
```

Or with Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew clean build
```

Results to confirm:

- Spring Boot starters and Boot modules belong to the same version line managed by the Boot parent/plugin.
- Spring Cloud modules, including Eureka or Consul, come from the same Release Train BOM.
- There are no manual version overrides causing a Spring Cloud module to drift from the train.
- The build tool is running on a supported JDK and the compiler toolchain matches the intended version.
- The build succeeds before starting to configure registry addresses or write code calling `DiscoveryClient`.

## 7. Troubleshooting Common Compatibility Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| Startup reports `Spring Boot [...] is not compatible with this Spring Cloud release train` | Boot and Cloud Release Train are not in a compatible pair | Re-check the compatibility table, switch to the right train, and use an appropriate service release |
| `NoSuchMethodError`, `NoClassDefFoundError`, or `ClassNotFoundException` after adding a starter | Dependency version mismatch, overridden by another BOM or manual version declaration | Inspect `dependency:tree`/`runtimeClasspath`, remove unnecessary overrides, and let the BOM manage versions |
| `UnsupportedClassVersionError` when running the application | Runtime JDK is lower than the Java version used to compile a class or dependency | Upgrade the runtime JDK or compile down to a Java level supported by the entire environment |
| Compiler reports `--release` or selected source release is unsupported | The JDK Maven/Gradle uses to compile is lower than the source/toolchain configuration | Check `mvn -v`, `gradle -version`, `JAVA_HOME`, and the Java toolchain |
| Local machine builds fine but CI fails | JDK or build tool on CI differs from local; wrapper is not used consistently | Commit Maven/Gradle Wrapper, configure the same JDK for CI, and re-verify the toolchain |

Do not disable the compatibility verifier just to get the application past a version error at startup. This verification mechanism helps detect an unsupported Boot/Cloud combination; fix the root cause in dependency management first.

## 8. Version Selection Workflow for Existing Projects

If a project already uses Spring Boot, do not start by upgrading Spring Cloud to the latest version. Proceed in order:

1. Read the Spring Boot version in `pom.xml` or `build.gradle` and verify the effective version using the dependency tree.
2. Look up the Release Train compatible with that exact Boot line.
3. Check the train's support status and release notes, especially if the train is old.
4. Choose the latest patch in the corresponding train and keep the BOM managing dependencies.
5. If a major/minor Boot upgrade is needed, create a separate upgrade change: update JDK, Boot, Cloud train, plugins, and starters; then run tests/builds and verify migration changes.

For example, a Boot 4.1.x application needs Spring Cloud 2025.1.x starting from 2025.1.2 or higher. A Boot 3.5.x application matches Spring Cloud 2025.0.x according to the compatibility table, but this train is currently marked end-of-life for community support; you should plan an upgrade instead of starting a new project on that train.

## 9. Checklist Before Starting the Service Discovery Lesson

- [ ] Identified the exact Spring Boot version.
- [ ] Checked the compatibility table and selected the right Spring Cloud Release Train.
- [ ] Verified the train is still supported or documented a clear reason to maintain an older train.
- [ ] Local JDK, IDE, build tool, CI, and runtime align with the target Java version.
- [ ] Maven/Gradle Wrapper is configured for reproducible builds.
- [ ] Spring Cloud BOM is imported; Spring Cloud starters do not have pinned individual versions.
- [ ] Dependency tree has no Spring Cloud module drifting from the train.
- [ ] Build command completes before configuring Eureka, Consul, or DiscoveryClient.

## References

- [Spring Cloud — Release Train and Spring Boot Compatibility Table](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2026.0.0 (Paddington) Released](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Boot 4.2.0 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/4.2-SNAPSHOT/reference/using/build-systems.html)
- [Spring Cloud Netflix — Eureka Client and HTTP Client](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Initializr](https://start.spring.io/)
