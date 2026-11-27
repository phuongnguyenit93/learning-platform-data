# Managing Dependencies Using the Spring Cloud BOM with Maven or Gradle

## 1. Objectives and Context

A **Spring Cloud Task** application is a Spring Boot process with a finite runtime: it starts up, performs work, and terminates. Spring Cloud Task provides infrastructure such as `TaskRepository` to record runs (`TaskExecution`), start/end timestamps, and execution status. When the application also uses Spring Batch, Spring JDBC, and a database driver, the libraries must have mutually compatible versions.

After this lesson, you will be able to:

- Explain what a BOM (Bill of Materials) and a release train are, and the difference between *version management* and *adding a library*.
- Choose a compatible Spring Boot – Spring Cloud pair before creating a Task project.
- Import `spring-cloud-dependencies` in Maven or Gradle and declare `spring-cloud-starter-task` without specifying an explicit version.
- Inspect the actually resolved versions, diagnose conflicts, and perform controlled upgrades.

This lesson belongs to the **Environment** chapter, focusing on setting up the dependency system for Spring Cloud Task. Configuring `TaskRepository`, parameters, error handling, scheduling, and Spring Batch integration in subsequent steps will build on this dependency foundation.

## 2. What Does a BOM Manage?

A **BOM** is a POM file describing coordinated dependency versions across an ecosystem. `org.springframework.cloud:spring-cloud-dependencies` is the BOM for a **Spring Cloud release train**; `org.springframework.boot:spring-boot-dependencies` manages Spring Boot components and many related libraries.

For example, once the appropriate BOM has been imported, you can declare:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-task</artifactId>
</dependency>
```

There is no `<version>` tag here: the build tool looks up the managed version. That does **not** mean the BOM automatically adds Spring Cloud Task to your application. You must declare `spring-cloud-starter-task` in `dependencies`.

| Component | Role | Automatically Adds Library Code to the App? |
| --- | --- | --- |
| Spring Boot parent/BOM | Manages versions of Spring Boot and its related library ecosystem | No |
| Spring Cloud release train BOM | Manages versions of the corresponding Spring Cloud projects | No |
| `spring-cloud-starter-task` | Pulls in the libraries needed to enable Spring Cloud Task infrastructure | Yes |
| `com.h2database:h2` | Provides an embedded database for experimentation | Yes |
| Maven/Gradle plugin | Compiles, tests, packages, and runs the application | Not a BOM |

Dependency resolution flow:

```text
Spring Boot parent/BOM ──> Spring Boot library versions
Spring Cloud BOM ────────> Spring Cloud library versions
                               │
dependencies {                 │
  spring-cloud-starter-task  } ─┘
          │
          └─> Spring Cloud Task, compatible transitive libraries
```

The most important benefit is that when upgrading a release train, the Spring Cloud components managed by the BOM are updated as a consistent set rather than guessing and pinning manual versions for each `starter`.

### Choosing Compatible Spring Boot and Spring Cloud Versions

Spring Cloud does not share the same version numbers as Spring Boot. First select the Spring Boot generation based on project requirements, then check the official **release train compatibility table** at [spring.io/projects/spring-cloud](https://spring.io/projects/spring-cloud/).

Some illustrative pairs:

| Spring Boot | Spring Cloud release train | Notes |
| --- | --- | --- |
| `4.1.x` | `2025.1.2+` (Oakwood) | Supported per the official compatibility table |
| `4.0.x` | `2025.1.x` (Oakwood) | Select a compatible patch release within the branch |
| `3.5.x` | `2025.0.x` (Northfields) | Legacy branch; check support status before using for new projects |

**Version set used in this lesson's examples:** Spring Boot **4.1.0**, Spring Cloud **2025.1.5**, Java **17+**. This pair belongs to the compatible branches published as of the writing date (November 24, 2026); it is an illustrative set that can be substituted when appropriate patch releases arrive. Do not copy version numbers into a new product without checking support status and security advisories.

## 3. Maven Configuration: Spring Boot Parent and Spring Cloud BOM

In `pom.xml`, the Spring Boot parent provides Spring Boot version management and common build configuration. Also import the Spring Cloud BOM under `dependencyManagement`; then add the starter under `dependencies`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>daily-report-task</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-task</artifactId>
        </dependency>
        <!-- H2 is used for learning and testing on a local machine. -->
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

Read the configuration in exact order:

1. `spring-boot-starter-parent` locks the Spring Boot version and shared build configuration.
2. The `spring-cloud.version` property sets the release train version in a single place.
3. `dependencyManagement` uses `type=pom` and `scope=import` to import the BOM; **do not** place the BOM as a regular runtime `dependency`.
4. `dependencies` actually adds `spring-cloud-starter-task` and H2 to the application without declaring `version` when already managed by the appropriate BOM.

If a project cannot use the Spring Boot parent because it already has an internal parent POM, you can import **both** `spring-boot-dependencies` and `spring-cloud-dependencies` inside `dependencyManagement`, and configure the required plugins separately. The Spring Boot BOM only manages library versions; it does not carry over all plugin configurations from `spring-boot-starter-parent`.

## 4. Gradle Configuration

Gradle has two common approaches: using the `io.spring.dependency-management` plugin or Gradle's native `platform(...)` BOM mechanism. Choose one clear version-management strategy per project.

### Approach A: `io.spring.dependency-management` Plugin

Example `build.gradle` in **Groovy DSL**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.0'
    id 'io.spring.dependency-management' version '1.1.7'
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
    set('springCloudVersion', '2025.1.5')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    runtimeOnly 'com.h2database:h2'
}
```

When applying `io.spring.dependency-management` alongside the Spring Boot plugin, the Spring Boot BOM is imported through the integration between these two plugins. The `dependencyManagement.imports` block adds the Spring Cloud BOM. You still need to declare the starters under `dependencies`.

### Approach B: Native Gradle `platform(...)`

If you prefer managing dependencies using Gradle's built-in capability, you can omit the `io.spring.dependency-management` plugin and explicitly import **both** BOMs:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.0'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.0')
    implementation platform('org.springframework.cloud:spring-cloud-dependencies:2025.1.5')

    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    runtimeOnly 'com.h2database:h2'
}
```

In this approach, `platform(...)` brings version constraints from the BOMs into Gradle's dependency resolution. Keep the Spring Boot BOM version synchronized with the Spring Boot plugin version and manage the Java toolchain/other build configurations yourself if needed. Do not assume that applying the `org.springframework.boot` plugin **alone** automatically imports the Spring Boot BOM when the dependency-management plugin is absent.

With **Kotlin DSL**, the equivalent native BOM declaration is:

```kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.0"))
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:2025.1.5"))
    implementation("org.springframework.cloud:spring-cloud-starter-task")
    runtimeOnly("com.h2database:h2")
}
```

This is only the `dependencies` block of `build.gradle.kts`, not a complete build file; `plugins`, `repositories`, and the Java toolchain must still be declared as appropriate for the project.

## 5. Verifying That the BOM Is Working

Do not rely solely on red squiggles disappearing in the IDE. Inspect the *effective dependency graph* resolved by the build tool, because a transitive library or a manual version declaration can affect the final result.

**Maven** (from the project root directory, assuming Maven Wrapper is present):

```bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dincludes=org.springframework.cloud
./mvnw test
```

- `help:effective-pom` shows the effective POM configuration after inheritance and imports.
- `dependency:tree` shows which Spring Cloud modules actually appear and which versions were selected.
- `test` confirms dependencies are sufficient to compile and test the project; a passing build does not prove production database configuration is accurate.

**Gradle** (from the project root directory, assuming Gradle Wrapper is present):

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-task-core --configuration runtimeClasspath
./gradlew test
```

`dependencyInsight` helps identify why a version was chosen (BOM, direct dependency, or a version requested by another library). On Windows, run the corresponding wrappers with `mvnw.cmd` and `gradlew.bat`.

### Distinguishing Build Success from Task Success

Declaring the BOM properly ensures **correct library resolution**, not automatic proof that the Task ran successfully. When `spring-cloud-starter-task` is added, Spring Cloud Task auto-configures infrastructure beans, including `TaskRepository` when conditions are met. Examples with embedded H2 are only suitable for learning: execution data can be lost when the process exits. For long-term execution history tracking, use a supported relational database, configure the datasource, and manage schemas according to your deployment environment.

A simple `ApplicationRunner` example to see the purpose of a finite-lived process:

```java
package com.example;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyReportTaskApplication {
    public static void main(String[] args) {
        SpringApplication.run(DailyReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner generateReport() {
        return arguments -> System.out.println("Daily report aggregated.");
    }
}
```

When logic inside the runner starts executing, Spring Cloud Task tracks the task lifecycle through its infrastructure. This code snippet illustrates the starter's application scope; the focus of this lesson remains managing versions properly before running.

## 6. Common Errors and How to Resolve Them

| Symptom | Common Cause | How to Check / Resolve |
| --- | --- | --- |
| Maven reports missing `version` for `spring-cloud-starter-task` | Cloud BOM not imported or `dependencyManagement` misplaced | Check `groupId`, `artifactId`, `type=pom`, `scope=import`, and BOM version |
| Gradle reports `Could not find ...` or cannot resolve version | BOM not imported into the appropriate configuration; missing repository | Check `mavenCentral()` and `dependencyManagement` or `platform(...)` |
| Application reports compatibility error on startup | Mixing incompatible generations of Spring Boot and Spring Cloud | Cross-check the compatibility table on spring.io and update both versions in sync |
| `NoSuchMethodError` / `ClassNotFoundException` | Potential transitive dependency conflict or manual version override | Run `dependency:tree` / `dependencyInsight`; remove unnecessary overrides and check third-party libraries |
| BOM imported but `TaskRepository` is missing | BOM does not add the starter automatically, or auto-configuration was not activated properly | Verify `spring-cloud-starter-task` is on the runtime classpath and inspect configuration logs |
| Task finishes but no history remains on the next run | Using in-memory H2; data lives only as long as the process | Switch to a persistent database and configure schema/datasource for a real environment |

**Note on version precedence:** A `<version>` declared directly in Maven or a version string written directly on a Gradle dependency can cause resolution to diverge from the intended version set. In Gradle, constraints and conflict-resolution rules also affect the final version. Read the dependency graph instead of assuming the BOM always overrides every other declaration.

### When You Need to Add Spring Batch

Spring Cloud Task records *process/task executions*; Spring Batch manages *Jobs*, *Steps*, checkpoints, and chunked reading/writing. If an application uses both, add the appropriate Batch starter, for example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-batch</artifactId>
</dependency>
```

The Batch starter version is managed by the Spring Boot BOM/parent. You still need to design `JobRepository`, `TaskRepository`, and the appropriate database; the BOM does not replace configuration or orchestration. Specifically avoid adding a separate `spring-batch-core` version without justification and compatibility testing.

## 7. Upgrade Process and Practice Exercises

Suppose the reporting application runs on a nightly schedule and persists status to PostgreSQL. The team is preparing to upgrade because a Spring Cloud library received a bug fix.

1. **Record current versions.** Note Spring Boot, Spring Cloud BOM, JDK, plugin versions, and the dependency graph before making edits.
2. **Choose a compatible pair.** Check the release train table; lock the appropriate patch version without bumping individual `spring-cloud-*` libraries when they are managed by the BOM.
3. **Update at a single source.** With Maven, adjust `<spring-cloud.version>` and the Spring Boot parent if needed. With Gradle, update the BOM/Boot plugin versions together according to the active strategy.
4. **Verify build and execution.** Review the dependency graph, run tests, and then run a Task in a test environment backed by a proper database.
5. **Verify execution metadata.** Confirm Task start, end, exit code, and tracking tables; if combined with Spring Batch, also verify Job/Step records and launch behavior.
6. **Deploy with rollback readiness.** Commit versions in VCS, record schema changes, keep a rollback plan, and monitor the first runs after the upgrade.

**Self-practice exercise:** Create a Maven or Gradle project following the examples above, add `spring-cloud-starter-task` and H2, then answer:

- Why is declaring the BOM in `dependencyManagement` or `platform(...)` not enough by itself to get `TaskRepository`?
- Which version did the build tool select for `spring-cloud-task-core`, and which constraint did it come from?
- If you remove the Cloud BOM while keeping the starter without a version, how does your build respond? Restore the configuration after testing.
- When migrating from embedded H2 to PostgreSQL, which part is a *dependency change* and which part is *operational configuration*?

**Completion criteria:** The project resolves the Task starter without specifying an explicit version; the dependency graph shows the BOM-managed version set; the sample Task runs to completion; and you can explain why in-memory H2 data is unsuitable for long-term execution history.

## Official References

- [Spring Cloud — release trains, compatibility table, and how to import the BOM](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2025.1.5 — release announcement and Spring Boot compatibility](https://spring.io/blog/2026/11/20/spring-cloud-2025-1-5-has-been-released/)
- [Spring Cloud Task — Getting Started](https://docs.spring.io/spring-cloud-task/reference/getting-started.html)
- [Gradle — Platforms and BOMs](https://docs.gradle.org/current/userguide/platforms.html)
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
