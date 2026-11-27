# Choosing Compatible Versions of Java, Spring Boot, and Spring Data REST

## Objectives

After this lesson, you will be able to:

- Choose a JDK that satisfies both the build environment and the runtime environment.
- Choose a Spring Boot version compatible with your JDK, build tool, and project libraries.
- Distinguish Spring Boot starter versions from Spring Data REST module versions.
- Use the Spring Boot BOM to align dependencies.
- Use the Spring Data Release Train BOM when managing Spring Data standalone.
- Inspect the actual dependencies resolved by Maven or Gradle.

## 1. Why Does Choosing Compatible Versions Matter?

Spring Data REST does not run in isolation. An application typically has the following dependency layers:

1. **Java JDK** provides the compiler, runtime, and foundational APIs.
2. **Spring Boot** provides application bootstrapping, auto-configuration, starters, and a curated set of dependency versions.
3. **Spring Framework** provides IoC, dependency injection, Spring MVC, and the core APIs used by Spring applications.
4. **Spring Data** provides the repository abstraction and integration modules for each database technology.
5. **Spring Data REST** exposes Spring Data repositories as HTTP resources, typically over Spring MVC and HAL representations.

These layers have compatibility constraints. A newer Spring Data REST version may require APIs from a newer Spring Framework version; that Framework version may in turn require a minimum JDK. If you pick individual libraries manually without checking the relationships between them, the application may fail to compile, fail to start, or fail at runtime.

You can visualize the dependency chain as follows:

```text
JDK
 │
 ▼
Spring Boot
 │  BOM manages compatible versions
 ├── Spring Framework
 ├── Spring Data Commons
 ├── Spring Data REST
 └── other integration libraries
      │
      ▼
Spring Data Repositories exposed as HTTP resources
```

Keep in mind: **components do not necessarily share the same version number**. Spring Boot has its own versioning scheme; Spring Data modules also have their own versions. Choose an appropriate Spring Boot line, then let the BOM manage the dependencies within that ecosystem.

## 2. Understanding the Different Version Types

| Component | Example | Meaning |
|---|---|---|
| Java | 17, 21, 25 | JDK version used to build and run |
| Spring Boot | 4.1.2 | Application platform version |
| Spring Framework | 7.0.10 | Core Spring version required by the corresponding Boot line |
| Spring Boot Data REST starter | 4.1.2 | Starter that integrates Spring Data REST into a Boot application |
| Spring Data REST WebMVC | 5.1.2 | Spring Data REST module running on Spring MVC, managed by Boot 4.1.2 BOM |
| Spring Data release train | 2026.0.1 | BOM version that aligns Spring Data modules when managed standalone |

For example, Spring Boot 4.1.2 manages `spring-boot-starter-data-rest` at version 4.1.2 and `spring-data-rest-webmvc` at version 5.1.2. Having two different numbers is normal: they belong to two different release schemes.

Spring Data uses a release train to coordinate modules that are developed and released on their own schedules. Do not assume that Spring Data REST must have the same version number as Spring Data JPA, Spring Data Commons, or Spring Boot.

## 3. Checking Java Constraints Before Choosing Boot

Identify the JDK your application must support before choosing a framework version.

### 3.1. Application Runtime JDK

This is the JDK installed on your server, container, or deployment platform. The application must be able to run on this version.

For example, if production only has Java 17, you cannot deploy bytecode that requires Java 21. Having a newer JDK on a developer's machine does not change production constraints.

### 3.2. Build Tool JDK

Maven or Gradle may run on a different JDK than the one you intend to target for the application. Check both the Java on your PATH and the JDK used by the build tool:

```bash
java -version
./mvnw -version
./gradlew --version
```

On Windows, use `mvnw.cmd -version` and `gradlew.bat --version`.

### 3.3. Compilation JDK and Java Toolchain

Building with a newer JDK does not force the application to emit bytecode for that exact JDK version. You can use a Java toolchain or compiler release setting to specify the target Java level, provided the framework and library versions support that level.

Distinguish between:

- **Build JDK**: the JDK that actually runs Maven or Gradle.
- **Compile release/toolchain**: the Java level that source code is compiled for.
- **Runtime JDK**: the JDK installed in the environment running the application.

All three values should be configured intentionally. If CI builds with a newer Java version while production runs an older one, verify the bytecode target and dependencies before releasing.

Beyond Java, check your Maven/Gradle Wrapper, IDE, build plugins, database drivers, Spring Cloud, security libraries, and third-party libraries. Just because a Spring Boot version supports a new JDK does not mean every external dependency already supports that JDK.

## 4. Choosing Spring Boot First

For a Spring Boot application, choose a stable GA release within a line that meets your project's requirements. Then use Boot's dependency management to manage Spring Framework, Spring Data, and related libraries.

Version selection sequence:

1. Confirm the JDK versions available in CI and production.
2. Read the **System Requirements** for the Spring Boot line you plan to adopt.
3. Verify that your Maven or Gradle Wrapper falls within the supported range.
4. Verify that critical third-party libraries are compatible.
5. Select an appropriate stable patch release in the chosen line.
6. Pin the Boot version in your project's parent, plugin, or BOM.

### Example from Documentation as of 11/11/2026

Spring Boot documentation currently lists Spring Boot **4.1.2** as a stable release. Its System Requirements state:

- Minimum Java: **17**.
- Maximum documented compatible Java: **27**.
- Minimum Spring Framework: **7.0.10**.
- Maven: **3.6.3 or later**.
- Gradle: **8.14 or later in the 8.x line**, or the **9.x** line.

Java 21 and Java 25 fall within the Java range documented for Spring Boot 4.1.2. Projects still need to check build plugins and third-party libraries before upgrading the JDK.

This is an example based on documentation at the time of writing, not a static compatibility table. Before starting a project or upgrading, revisit the System Requirements page for your exact Spring Boot version to confirm current limits.

## 5. Using the Spring Boot BOM to Manage Spring Data REST

A BOM (Bill of Materials) is a POM that declares dependency versions managed together. Spring Boot provides the `spring-boot-dependencies` BOM; the Spring Boot parent and Gradle plugin help projects consume this set of versions.

When using Spring Boot dependency management:

- Declare `spring-boot-starter-data-rest` without specifying a version.
- Do not set a custom version for `spring-data-rest-webmvc`.
- Do not set a custom version for `spring-data-commons` or related Spring Data modules.
- Do not upgrade a single module to the latest version in isolation without verifying compatibility across the entire dependency graph.

The Boot BOM selects versions tested to work together. When you upgrade Spring Boot, the managed versions are updated along with the new BOM.

### 5.1. Maven Using the Spring Boot Parent

Example of an application using Java 21 and Spring Boot 4.1.2:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>catalog-api</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-rest</artifactId>
        </dependency>
    </dependencies>
</project>
```

Explanation:

- `spring-boot-starter-parent` pins Spring Boot to 4.1.2 and provides default dependency management.
- `java.version` sets the target Java level for the Maven configuration provided by the parent.
- `spring-boot-starter-data-rest` omits the `version` tag; Maven resolves the managed version from Boot.
- Boot 4.1.2 manages the Data REST starter at 4.1.2 and the `spring-data-rest-webmvc` module at 5.1.2.

The starter provides Spring Data REST integration. It does not automatically create entities, repositories, schemas, or database connection settings. If your application uses JPA, you must also declare the JPA starter and an appropriate driver; Boot-managed dependencies should likewise be declared without individual versions.

### 5.2. Maven Without the Spring Boot Parent

If your project needs to inherit from a different parent POM, you can import the BOM directly in `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

After importing the BOM, Boot-managed dependencies can be declared without a version. Note that importing the BOM does not automatically apply all Maven plugin configurations provided by `spring-boot-starter-parent`; if you need those plugin configurations, declare them separately or use an appropriate parent.

### 5.3. Gradle

With Gradle, the Spring Boot plugin can automatically configure dependency management and import the Boot BOM. Example:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
}
```

You do not need to specify a version for the starter because the Boot plugin manages versions through the BOM. If your project does not use the Spring Boot Gradle plugin, you can import the BOM using a Gradle native platform:

```kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.2"))
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
}
```

Choose one clear version-management mechanism and apply it consistently across the project.

## 6. When to Use the Spring Data Release Train BOM

A plain Spring Framework application or a project managing Spring Data manually without the Spring Boot BOM needs to coordinate versions across Spring Data modules. In this case, use the **Spring Data Release Train BOM**.

At the time of writing, Spring Data documentation lists the current release train as **2026.0.1**. Maven example:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2026.0.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-rest-webmvc</artifactId>
    </dependency>
</dependencies>
```

After importing the BOM, you do not need to declare individual versions for each Spring Data module managed by the BOM. The release train keeps modules with different release schedules aligned.

Current Spring Data documentation requires Spring Data modules to run on Spring Framework **7.0.9 or later**. Cross-check this requirement against the Framework version used by your standalone application.

### Does a Spring Boot Project Also Need to Import the Spring Data BOM?

Usually not. Spring Boot already selects the versions of Spring Data modules in the Boot BOM. Importing another BOM that manages the same dependencies can cause resolved versions to diverge from the combination tested by Boot.

If a Spring Boot project truly needs to upgrade Spring Data to a newer release train, Spring Data documentation recommends using Spring Boot's `spring-data-bom.version` property to pick the desired train and iteration. Only do this after checking compatibility with Spring Framework, Spring Boot, and related modules, then verifying the dependency tree and running integration tests.

## 7. Verifying the Versions Resolved by Maven or Gradle

The build file shows the directly declared dependencies. The dependency tree shows the actual versions resolved by the build tool, including transitive dependencies.

### 7.1. Maven

Check the running Java and Maven versions:

```bash
java -version
./mvnw -version
```

Check the resolved Spring Data modules:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.data:*
```

Check the POM after dependency management is applied:

```bash
./mvnw help:effective-pom
```

Run the full build and tests:

```bash
./mvnw clean verify
```

If you are not using the Maven Wrapper, replace `./mvnw` with `mvn`. On Windows, use `mvnw.cmd`.

### 7.2. Gradle

Check the JDK and Gradle:

```bash
./gradlew --version
```

Inspect runtime dependencies:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Trace Spring Data REST specifically:

```bash
./gradlew dependencyInsight --dependency spring-data-rest-webmvc --configuration runtimeClasspath
```

Run tests:

```bash
./gradlew test
```

### 7.3. What to Verify

- The build tool is running on the expected JDK.
- The Java toolchain or compiler release does not exceed the target runtime JDK.
- `spring-boot-starter-data-rest` is managed at the selected Spring Boot version.
- `spring-data-rest-webmvc`, Spring Data Commons, and related modules are resolved according to the expected BOM.
- No dependency is forced to an unexpectedly old or new version.
- There are no conflicting versions of the same module on the runtime classpath.
- The build, unit tests, integration tests, and application startup all succeed.
- Repository endpoints work properly after the application starts.

If the dependency tree shows that a library is being overridden, locate the direct dependency, transitive dependency, or BOM that introduced that version. Fix it at the version-management source and re-run the dependency tree; do not add an arbitrary version to mask the conflict.

## 8. Common Version Selection Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming Spring Boot and Spring Data REST must share the same version number | Choosing the wrong version or misreading dependency tables | Distinguish Boot starter versions from Spring Data REST module versions |
| Pairing the newest Spring Data REST module with an older Boot version | May mismatch Spring Framework or Spring Data Commons | Let the Boot BOM manage versions in Boot projects |
| Upgrading `spring-data-commons` or `spring-data-rest-webmvc` individually | May cause linkage errors, `NoSuchMethodError`, or startup failures | Upgrade via the BOM and inspect the entire dependency graph |
| Running only `java -version` | Maven, Gradle, or CI may use a different JDK | Also check `mvnw -version` or `gradlew --version` |
| Building with a newer JDK while production runs an older JDK | Bytecode may fail to run in production | Set toolchain/compiler release to match the target runtime |
| Using snapshots, milestones, or release candidates in production | APIs and dependencies may still change | Prefer stable GA releases unless intentionally testing |
| Importing multiple BOMs that manage the same dependencies | Resolved versions may differ from expectations | Choose one primary management source and inspect the dependency tree |
| Adding only the Data REST starter without creating a repository | No repository endpoints to expose | Create a Spring Data repository and configure the appropriate persistence layer |

Errors such as `NoSuchMethodError`, `ClassNotFoundException`, or startup failures can be caused by misaligned dependencies. When encountering errors, check resolved versions and compatibility requirements before changing business code.

## 9. Version Selection Workflow for a New Project

Suppose a new service can run Java 21 and uses Maven:

1. Confirm that both CI and production can install Java 21.
2. Choose a stable Spring Boot release that supports Java 21.
3. Read the System Requirements to verify JDK and Maven Wrapper support.
4. Pin the Spring Boot version in the parent or BOM.
5. Add `spring-boot-starter-data-rest` without declaring a version.
6. Add the appropriate data store starter such as JPA, JDBC, or MongoDB; let Boot manage the version if the dependency is in the BOM.
7. Run `dependency:tree` to confirm the Spring Data REST and related module versions.
8. Run `clean verify`, start the application, and test the live endpoints.

For existing projects running Spring Boot 3.x, keep the Spring Data REST set managed by your current Boot line during routine bug fixes. If migrating to Boot 4.x, treat it as a platform upgrade: read the migration guide, confirm JDK and build tool versions, audit third-party dependencies, then upgrade and run full test suites. Do not upgrade Spring Data REST alone to a new major version before the Boot platform is ready.

## 10. Official References

- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): JDK, Maven, Gradle, and runtime requirements.
- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html): dependency versions managed by the Boot BOM.
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): using starters, Maven, Gradle, and dependency management.
- [Spring Data REST — Dependencies](https://docs.spring.io/spring-data/rest/reference/data-commons/dependencies.html): Spring Data Release Train BOM, version management with Boot, and Spring Framework requirements.
- [Spring Initializr](https://start.spring.io): generates project configurations by JDK, Spring Boot, and build tool.

Versions and limits can change. Before every new project or upgrade, re-check the System Requirements and Managed Dependency Coordinates for the exact Spring Boot version your project will use.
