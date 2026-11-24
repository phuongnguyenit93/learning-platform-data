# Applying the Boot Plugin to Application Modules and the BOM to Library Modules

## 1. The Problem to Solve in Multi-Module Projects

A sufficiently large Spring Boot project is usually divided into multiple modules: `shared-lib`/`domain`/`common` contains shared logic or APIs, while `service-app` holds the Spring Boot entry point and produces the runnable artifact. Applying the **Spring Boot build plugin** to **all** modules without distinguishing their roles can force library modules to build an executable JAR even though they **have no `main()`**. Conversely, omitting the Boot plugin on library modules without managing dependency versions can cause resolution errors when declaring Spring or Apache Commons libraries without a `version`.

The right separation:

> **The Spring Boot plugin packages and runs applications; the Spring Boot BOM aligns dependency versions.** A library module can use the BOM **without applying the Boot plugin**.

This lesson covers both **Gradle** and **Maven**, with Java 17+ examples, how to inspect tasks/outputs, distinguishing plain JARs from executable JARs, and common pitfalls.

### Goals After This Lesson

- Understand what `org.springframework.boot` (Gradle plugin) or `spring-boot-maven-plugin` (Maven plugin) is for.
- Understand that the `spring-boot-dependencies` BOM **manages versions** and does not automatically add dependencies or create packaging tasks.
- Apply the Boot plugin only in the **application module**; keep library modules as ordinary Java JAR structures.
- Use `project(':shared-lib')` (Gradle) or a reactor dependency (Maven) so the application consumes the library.
- Inspect `runtimeClasspath`, `dependencyInsight`, `dependency:tree`, and `BOOT-INF/lib` to verify final artifacts.
- Keep one consistent set of dependency versions across app and library, avoiding unintentional BOM or plugin version drift.

## 2. Three Distinct Roles: Plugin, BOM, and Module Dependency

| Component | Primary Role | What Does It Not Do Automatically? |
|---|---|---|
| **Gradle `org.springframework.boot` plugin** | When paired with Java plugin, adds `bootJar`, `bootRun`, `bootBuildImage`, and Boot configurations | Does not add `spring-boot-starter` automatically; does not manage versions unless a BOM or dependency management is configured |
| **Maven `spring-boot-maven-plugin`** | `repackage`s JAR/WAR into an executable archive; supports `spring-boot:run` and other goals | Is not `dependencyManagement`; declaring the plugin without an appropriate execution does not guarantee `package` will repackage |
| **`spring-boot-dependencies` BOM** | Provides managed versions for Spring Boot, Spring Framework, and many compatible libraries | Does not create executable JARs; does not add libraries to dependencies unless declared |
| **Gradle `java-library`** | Creates a library JAR and `apiElements`/`runtimeElements`; supports `api`/`implementation` | Does not require an application main class |
| **Gradle `java`** | Standard Java compile/test/JAR | Does not produce a Boot executable archive without the Boot plugin |
| **Maven `<packaging>jar</packaging>`** | Packages an ordinary Java JAR via the lifecycle | Does not turn the JAR into a Boot executable without running `repackage` |
| **Project/module dependency** | Connects the app to a library module in the same build | Does not control the BOM, plugin, or main class |

Example:

```text
multi-boot/
├── shared-lib   (library module, no main())
│   ├── Java library plugin
│   ├── Spring Boot BOM manages dependency versions
│   └── build -> shared-lib-1.0.0.jar (plain JAR)
│
└── service-app  (application module, has main())
    ├── Spring Boot plugin + Java plugin
    ├── Spring Boot BOM manages dependency versions
    ├── depends on shared-lib
    └── build -> service-app-1.0.0.jar (executable Boot JAR)
                         └── BOOT-INF/lib/shared-lib-1.0.0.jar
```

**The BOM and the Boot plugin are two independent axes**. Both library and app may need the BOM; only the app needs `bootJar`/`repackage` capabilities.

### Terminology Notes

- **Module/app project**: an independent set of source code, dependencies, and build configuration.
- **Root/aggregator**: coordinates modules and does not necessarily produce a runnable artifact.
- **BOM** (*Bill of Materials*): a table of dependency versions tested for compatibility by a framework.
- **Plain JAR**: classes sit at the root package path of the JAR; Java tooling can put it on the classpath as a library.
- **Executable Boot JAR**: application classes sit in `BOOT-INF/classes` and dependencies inside `BOOT-INF/lib`; launched via the Spring Boot Loader with `java -jar`.
- **Task/goal**: Gradle runs **tasks** (`bootJar`), while Maven runs **goals** (`spring-boot:repackage`); do not mix the two terms or syntaxes.

## 3. Gradle: Assigning Plugins Per Project

Below is the **Groovy DSL** model (`settings.gradle` and `build.gradle`). The example pins **Spring Boot 3.5.16** and **Java 17**. These versions illustrate a reproducible build; in real projects, pick a supported version consistent with other modules. You need a Gradle version compatible with Spring Boot 3.5 and a properly generated/maintained Gradle Wrapper (for example, Gradle 8.14.x suits this branch).

### 3.1. Project Structure

```text
multi-boot-gradle/
├── settings.gradle
├── build.gradle
├── gradlew                  (if Wrapper has been generated)
├── gradlew.bat              (if Wrapper has been generated)
├── gradle/wrapper/...       (if Wrapper has been generated)
│
├── shared-lib/
│   ├── build.gradle
│   ├── src/main/java/com/example/shared/GreetingService.java
│   └── src/test/java/com/example/shared/GreetingServiceTest.java
│
└── service-app/
    ├── build.gradle
    └── src/main/java/com/example/app/ServiceApplication.java
```

There is **one Gradle multi-project build** with two subprojects. Do not add the Boot plugin to `shared-lib` merely because it uses a library from the Spring Boot BOM. `shared-lib` can be pure Java without depending on the Spring runtime.

### 3.2. settings.gradle: Registering Modules

```groovy
rootProject.name = 'multi-boot-gradle'

include 'shared-lib', 'service-app'
```

Names in `include` must match the actual subdirectories. The `:` in task/dependency selectors represents a Gradle project path, such as `:service-app:bootJar`.

### 3.3. build.gradle at Root: Managing Plugin Version Without Applying Yet

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16' apply false
}

allprojects {
    group = 'com.example'
    version = '1.0.0'

    repositories {
        mavenCentral()
    }
}
```

Meaning:

1. `id 'org.springframework.boot' version '3.5.16' apply false` declares the plugin version available to **subprojects**, without **applying the plugin to the root**; hence the root does not get `bootJar`.
2. `group` and `version` apply uniformly to all projects so artifacts have clear coordinates.
3. `mavenCentral()` provides the repository for dependency resolution; Gradle Plugin Portal is used by Gradle via its own plugin resolution mechanism.
4. The root **does not** apply `java` or `org.springframework.boot` across all modules. Adding `subprojects { apply plugin: 'org.springframework.boot' }` would pull the library module into the executable JAR flow — which is what we want to avoid.

**Distinguish "plugin is on the classpath" from "plugin is applied":** `apply false` creates no Boot tasks. Only `id 'org.springframework.boot'` in `service-app/build.gradle` in the next section does that.

### 3.4. shared-lib/build.gradle: java-library + BOM, Without the Boot Plugin

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    // Import the Spring Boot BOM as a Gradle platform for the library.
    // api(platform(...)) also exports version constraints to consumers
    // through Gradle's corresponding metadata mechanism.
    api platform('org.springframework.boot:spring-boot-dependencies:3.5.16')

    // Omit version because it is managed by the BOM.
    implementation 'org.apache.commons:commons-lang3'

    // Unit tests do not need a Spring ApplicationContext.
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Why use `java-library`?**

- It applies the Java plugin and creates `compileJava`, `jar`, and `test` tasks for the library.
- It provides `api` and `implementation` to distinguish dependencies exposed in the public API from internal details.
- There is no `bootJar`, and no need to locate a `public static void main`.
- `jar` produces an ordinary JAR: `GreetingService`'s class sits at `com/example/shared/GreetingService.class` at the archive root, ready for other modules to consume as a library.

**Why `api platform(...)`?** In Gradle `java-library`, declaring a BOM via `api platform(...)` allows the BOM's constraints to participate in the API variant as well and be exposed to consumers via Gradle's published metadata. This is an **intentional choice** in this example: the library is published for consumers in the same Spring Boot 3.5.x ecosystem. If a library is meant to be framework-neutral and should not push Spring Boot version recommendations onto consumers, consider `implementation platform(...)` for internal configuration and let applications manage their own BOM.

**Do not confuse:**

- `api platform('...')` manages dependency versions; it **does not add every JAR in the BOM** to the library.
- `implementation 'org.apache.commons:commons-lang3'` **is what declares the dependency**; its version is resolved by the graph's BOM/constraints.
- A shared library does not require `spring-boot-starter` if it only uses a plain Java utility.
- If a type from an external library appears in a **public method signature**, that dependency may need to move from `implementation` to `api` so consumers can compile.

### 3.5. service-app/build.gradle: Only the App Applies the Boot Plugin

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    // Actual dependency between the two projects in this build.
    implementation project(':shared-lib')

    // The application also needs explicit version management.
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )

    // The BOM manages versions; this dependency adds the actual Boot runtime.
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

`org.springframework.boot` is applied to `service-app`; because the project also has `java`, the Boot plugin creates `bootJar` and `bootRun`, and `assemble` typically depends on `bootJar`. `jar` (the plain JAR task) still exists, with the `plain` classifier by convention.

`implementation project(':shared-lib')` tells Gradle that the app must consume the **library's appropriate output**; there is no need to manually copy `shared-lib.jar` into `libs`. When `bootJar` packages the app, the library dependency is placed into the runtime archive by the task, typically under `BOOT-INF/lib`.

**Note:** this example **does not apply `io.spring.dependency-management`**. This is the **Gradle native BOM** (`platform`) approach; do not mix both version management approaches in the same example to avoid misunderstanding precedence rules.

### 3.6. Java 17 Library Source Code: No main()

`shared-lib/src/main/java/com/example/shared/GreetingService.java`:

```java
package com.example.shared;

import org.apache.commons.lang3.StringUtils;

public final class GreetingService {
    private GreetingService() {
        // Utility class, no need to instantiate.
    }

    public static String greet(String name) {
        return StringUtils.capitalize("hello, " + name) + "!";
    }
}
```

This class uses `commons-lang3` inside its implementation. Its public signature takes and returns JDK `String` only, so there is **no need to expose** Commons Lang3 as an `api` dependency. There is no `main()` and no `@SpringBootApplication` in the library module.

### 3.7. Library Unit Test Without Starting Spring Boot

`shared-lib/src/test/java/com/example/shared/GreetingServiceTest.java`:

```java
package com.example.shared;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {

    @Test
    void greetsByCapitalizingFirstLetter() {
        assertEquals("Hello, Java!", GreetingService.greet("Java"));
    }
}
```

The test uses JUnit 5/Jupiter managed by the BOM. `:shared-lib:test` is a plain Java task requiring neither `bootTestRun` nor a Spring context.

### 3.8. Spring Boot Application Source Code

`service-app/src/main/java/com/example/app/ServiceApplication.java`:

```java
package com.example.app;

import com.example.shared.GreetingService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServiceApplication.class, args);
    }

    @Bean
    CommandLineRunner greetingRunner() {
        return args -> System.out.println(GreetingService.greet("Java"));
    }
}
```

The app uses only `spring-boot-starter`, with no web starter: it runs in the console, executes the `CommandLineRunner`, and exits. After starting successfully, the output **contains this exact line**:

```text
Hello, Java!
```

Spring Boot/Gradle may still print banners, logs, or other notices; do not claim the entire stdout consists of a single line.

**Note on component scanning:** `GreetingService` in `com.example.shared` is a plain Java class called directly by the app, so Spring component scanning into that package is unnecessary. If a library actually provides `@Service`, `@Configuration`, `@Entity`, or repositories, you must manage package scanning/imports/auto-configuration accordingly. Never confuse "module is on the classpath" with "Spring automatically registers every bean in that module".

## 4. Running and Verifying Gradle Results

On Linux/macOS, from the root with Gradle Wrapper:

```bash
# Inspect projects in the build:
./gradlew projects

# Run library unit tests:
./gradlew :shared-lib:test

# Build the Java library JAR and application executable JAR:
./gradlew :shared-lib:jar :service-app:bootJar

# Run the application in development mode:
./gradlew :service-app:bootRun

# Run the exact executable JAR just built:
java -jar service-app/build/libs/service-app-1.0.0.jar
```

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat`. If there is no Wrapper yet, generate it using a compatible installed Gradle (for instance, running `gradle wrapper --gradle-version 8.14.3` from the build root). `gradlew`/`gradlew.bat` files **do not appear automatically** just from writing `build.gradle`. You do not need to run `bootRun` and `java -jar` simultaneously; they are **two independent execution methods** shown for comparison.

### Expected Artifacts

| Module/Task | File or Status | Purpose |
|---|---|---|
| `:shared-lib:jar` | `shared-lib/build/libs/shared-lib-1.0.0.jar` | Plain JAR, containing `com/example/shared/GreetingService.class` |
| `:service-app:jar` | `service-app/build/libs/service-app-1.0.0-plain.jar` | Plain JAR of the app per Boot/Gradle convention |
| `:service-app:bootJar` | `service-app/build/libs/service-app-1.0.0.jar` | Executable Boot JAR |
| `:service-app:bootRun` | Task running the app from runtime classpath | Runs during development without `java -jar` |
| `:shared-lib:bootJar` | **Does not exist** in this configuration | Library does not apply the Boot plugin |

Filenames follow the **conventions** from the example's `group/version` and classifiers. If a project overrides `archiveBaseName`, `archiveVersion`, or `archiveClassifier`, the actual file may differ; inspect the task output.

List archive entries:

```bash
jar tf shared-lib/build/libs/shared-lib-1.0.0.jar
jar tf service-app/build/libs/service-app-1.0.0.jar
```

In the library, look for `com/example/shared/GreetingService.class`. In the executable app, look for:

```text
BOOT-INF/classes/com/example/app/ServiceApplication.class
BOOT-INF/lib/shared-lib-1.0.0.jar
BOOT-INF/lib/commons-lang3-....jar
```

The `....` indicates the **actual version selected by BOM/Gradle resolution**, not a literal filename. If the executable JAR is missing `shared-lib`, inspect `implementation project(':shared-lib')` and `runtimeClasspath` instead of copying JARs manually.

### Inspecting Tasks and Dependency Graph

```bash
# Library has only standard Java tasks, no BootJar:
./gradlew :shared-lib:tasks --all

# App has Boot tasks:
./gradlew :service-app:tasks --all

# View dependencies per module:
./gradlew :shared-lib:dependencies --configuration compileClasspath
./gradlew :shared-lib:dependencies --configuration runtimeClasspath
./gradlew :service-app:dependencies --configuration runtimeClasspath

# Why was this version of Commons Lang3 chosen?
./gradlew :shared-lib:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3

# View variants exposed to other modules:
./gradlew :shared-lib:outgoingVariants
```

**Reading the results accurately:**

- `runtimeClasspath` is a resolution configuration, **not** a confirmed list of files in `BOOT-INF/lib`. Compare against the actual archive.
- `dependencyInsight` shows constraint/conflict resolution sources, helping uncover BOMs and overrides.
- `outgoingVariants` of `java-library` describes API/runtime variants; it does not imply a Boot fat JAR can be consumed as a Java library.
- `tasks --all` on a **specific project** shows whether `bootJar` exists there; tasks on the app do not prove the library has them too.
- Running `./gradlew build` at root can build/test both projects via the task graph. Select `:service-app:bootJar` when you only want to package the app and its required dependencies; choose `build` for full verification.

## 5. Why Should the Boot Plugin Not Be Applied to All Subprojects?

A configuration to **avoid** when the root contains plain Java modules:

```groovy
subprojects {
    apply plugin: 'java'
    apply plugin: 'org.springframework.boot'
}
```

If `org.springframework.boot` is applied to `shared-lib` alongside the Java plugin, Boot creates `bootJar` and `bootRun`, and `assemble` may depend on `bootJar`. Because `GreetingService` has no `main()`, building an executable archive can fail with a **main class not found** error. Even if you force a main class or disable `bootJar`, a library module must also ensure its published variants are not misconfigured into an executable layout.

### The Right Way

Keep the plugin version at the root with `apply false`, then apply it **only in `service-app/build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}
```

In `shared-lib/build.gradle`:

```groovy
plugins {
    id 'java-library'
}
dependencies {
    api platform('org.springframework.boot:spring-boot-dependencies:3.5.16')
}
```

The blocks above **excerpt the core parts**, not the full configuration replacing section 3. If the library needs actual dependencies, they still must be declared as in the `commons-lang3` example.

### What If You Must Temporarily Use the Boot Plugin in a Library?

You can disable the `bootJar` task in a project for special designs, yet that yields confusing configuration without fixing the architectural root cause: **libraries usually do not need application packaging features**. The preferred solution remains **not applying the Boot plugin** to that module. If a project enforces custom shared build logic, inspect the `jar` task, outgoing variants, Maven/Gradle publication metadata, and consumption tests as a library.

## 6. Gradle BOM: api platform, implementation platform, and enforcedPlatform

### 6.1. A BOM Is a Set of Version Constraints, Not an Application

Writing:

```groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.apache.commons:commons-lang3'
}
```

`platform(...)` imports version constraints from the Maven BOM into the **Gradle configuration**. `implementation 'org.apache.commons:commons-lang3'` is the actual dependency. Without the `implementation` line, the BOM does not automatically add Apache Commons Lang3 to the runtime JAR.

In a Java library module:

- `implementation platform(...)` applies constraints to dependencies needed internally by the module. This is usually the safe choice if the library does not want to impose a version policy on consumers.
- `api platform(...)` can also expose constraints to the API variant, so Gradle consumers can receive version constraints when using the project/library. Useful if the library **deliberately commits** to the same version ecosystem, though use caution for public multi-ecosystem libraries.
- `enforcedPlatform(...)` applies stronger constraints that can force versions across the graph and propagate to consumers through variants. Do not pick it by default just to "lock tightly"; it easily causes conflicts when consumers bring another BOM.

**A BOM is not "a JAR containing all libraries".** The `spring-boot-dependencies` artifact is primarily POM metadata with `dependencyManagement`. It guides version selection rather than containing bytecode for Commons Lang3 or Spring starters.

### 6.2. Platform Recommendations Are Not Absolute Locks

Gradle native `platform(...)` typically acts as **version recommendations**. If the dependency graph includes other constraints/versions, Gradle may pick a version different from the BOM via conflict resolution. Therefore, never say "the BOM always forces every dependency to 100% that exact version".

Diagnostic command:

```bash
./gradlew :service-app:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
```

When you see an unexpected version, check for:

- A direct dependency declaring a different version.
- A transitive dependency requesting a higher version.
- Another constraint/platform on the same classpath.
- A force rule, resolution strategy, dependency substitution, or version catalog.
- Published Gradle Module Metadata of a dependency.

**Avoid arbitrary overrides**: every Spring Boot release is tested against a curated combination of dependencies. Only override when justified (security, bug fix, compatibility) and verified by tests.

### 6.3. Boot Plugin Version and BOM Must Stay Synchronized

In the example:

```text
org.springframework.boot Gradle plugin: 3.5.16
spring-boot-dependencies BOM:        3.5.16
spring-boot-starter runtime:         managed by BOM 3.5.16
```

Avoid accidentally using plugin `3.5.16` while the library BOM is `3.4.x` and the app BOM is `3.5.x`; constraints can conflict and yield unintended versions. For large builds, manage versions via one shared property/version catalog/convention plugin rather than copying version numbers independently.

Example of a **shared variable snippet** for Groovy DSL when managing configuration yourself:

```groovy
// gradle.properties of the build root:
springBootVersion=3.5.16

// In build.gradle files using dependency coordinates:
dependencies {
    implementation platform(
        "org.springframework.boot:spring-boot-dependencies:${springBootVersion}"
    )
}
```

These are **two snippets from two different files** illustrating version management; do not paste `springBootVersion=...` literally into `build.gradle`. For `plugins {}`, putting plugin versions into `settings.gradle` `pluginManagement` or a version catalog follows specific rules; do not assume Groovy property interpolation works inside every `plugins` block.

## 7. Alternative: `io.spring.dependency-management` Plugin, Not to Be Confused with the Boot Plugin

The Spring Boot Gradle Plugin supports two primary dependency management paths:

1. **Gradle native BOM** via `platform(...)` — used throughout the main example.
2. **Plugin `io.spring.dependency-management`** — provides the `dependencyManagement` DSL, imports Maven BOMs, and supports customizing managed versions via properties.

When **both the Boot plugin and `io.spring.dependency-management` are applied in one project**, the Spring Boot plugin automatically imports the `spring-boot-dependencies` BOM matching the Boot plugin version. However, **if you apply only `io.spring.dependency-management` in a library**, you must **explicitly import the BOM** — there is no Boot plugin in the library to trigger that automatic integration.

An **alternative approach** — not to be mixed into the native BOM build in section 3 — declares at the root:

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}
```

In `shared-lib/build.gradle`:

```groovy
plugins {
    id 'java-library'
    id 'io.spring.dependency-management'
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.16'
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3'
}
```

In `service-app/build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

dependencies {
    implementation project(':shared-lib')
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

In `app`, the Boot plugin pairs with the dependency-management plugin to import the BOM; in the library, the import is explicit because the Boot plugin is absent. These blocks **replace** the corresponding plugin/dependency management blocks of the main configuration rather than layering two version-management systems on top of each other.

### Note for Published Library Modules

`io.spring.dependency-management` and Gradle native `platform` are not identical in how they implement version constraints, override properties, and published metadata. When exporting a library to a Maven repository:

- Use `maven-publish` and `from components.java` to publish the Java component.
- Inspect `gradle.module`, the generated `pom.xml`, and test with a **separate consumer project**.
- Do not assume every version constraint in Gradle Module Metadata will be expressed identically for Maven consumers.
- Verify transitive dependencies and compatibility in the final consumer, not only inside the library module's build.

## 8. Maven Multi-Module: BOM in Parent, Boot Repackage Only in App

The same idea is implemented differently in Maven. Maven has no `apply false` like Gradle; instead, place the **BOM in the aggregator/parent** so modules inherit `dependencyManagement`, while **only the app module** declares `spring-boot-maven-plugin` with the `repackage` goal.

Example structure:

```text
multi-boot-maven/
├── pom.xml                        (aggregator/parent)
├── shared-lib/
│   ├── pom.xml
│   ├── src/main/java/com/example/shared/GreetingService.java
│   └── src/test/java/com/example/shared/GreetingServiceTest.java
└── service-app/
    ├── pom.xml
    └── src/main/java/com/example/app/ServiceApplication.java
```

You can **reuse the exact same Java 17 files** from sections 3.6, 3.7, and 3.8. They do not depend directly on the build tool, only on Java libraries properly managed by Maven.

### 8.1. Root pom.xml: Aggregator + BOM + Plugin Management

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>multi-boot-maven</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared-lib</module>
        <module>service-app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-boot.version>3.5.16</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <version>${spring-boot.version}</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

**Core points:**

- `<packaging>pom</packaging>` acts as aggregator/parent, with no runnable Java app at the root.
- `<modules>` informs the Maven Reactor about the two modules.
- `<dependencyManagement>` imports the BOM so **child modules inherit dependency versions**, without yet adding concrete dependencies.
- `<pluginManagement>` manages versions for compiler, Surefire, and Spring Boot Maven Plugin; it **does not automatically trigger `repackage` in every module**.
- This root example **does not use `spring-boot-starter-parent`**. Therefore `repackage` is **not automatically bound** as in a Starter Parent setup; the execution must be declared in the app (section 8.3).
- Compiler plugin version and `maven.compiler.release=17` make Java 17 builds consistent rather than relying on overly old Maven defaults.
- Surefire 3.5.2 supports running JUnit Jupiter tests per the example setup.

### 8.2. shared-lib/pom.xml: Plain JAR, No Boot Plugin

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>multi-boot-maven</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>shared-lib</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Both `commons-lang3` and `junit-jupiter` omit `<version>` because the root already imports the Spring Boot BOM. JUnit stays in `test` scope and does not enter the library's runtime JAR. `<packaging>jar</packaging>` uses the standard Maven JAR lifecycle. **Do not declare `spring-boot-maven-plugin` in `shared-lib`**, because the library has no application entry point.

### 8.3. service-app/pom.xml: Only the App Has repackage

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>multi-boot-maven</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>service-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-maven-plugin` gets its version from `pluginManagement` at root. The `repackage` execution is **declared only in the app**, so when building the reactor, the app packages an executable JAR while `shared-lib` remains a plain library JAR. Having the plugin version in root `pluginManagement` **does not** mean the library runs the `repackage` goal too.

**Version syntax note:** `${project.version}` in the app points to the app's project version (matching `1.0.0` of the library in this example). If the library has an independent version, use the matching property/coordinates rather than assuming synchronized versions.

### 8.4. Build and Run the Maven Reactor

From the root containing `pom.xml`, using an installed Maven:

```bash
mvn clean verify

# Build only the app and required projects by dependency:
mvn -pl :service-app -am clean package

# Run the executable JAR:
java -jar service-app/target/service-app-1.0.0.jar
```

If the project has a Maven Wrapper, replace `mvn` with `./mvnw` (Windows PowerShell: `.\mvnw.cmd`). The two build commands above are **alternatives** for two different needs; you do not need to run both to produce a new JAR. `-pl :service-app` selects the module by `artifactId`; `-am` adds projects that module depends on in the reactor, such as `shared-lib`.

When the application runs successfully, logs will contain the line `Hello, Java!` from `CommandLineRunner`; other Spring Boot logs may also appear.

Expected results:

```text
shared-lib/target/shared-lib-1.0.0.jar        (library JAR)
service-app/target/service-app-1.0.0.jar     (Boot executable JAR)
```

Inspect:

```bash
jar tf shared-lib/target/shared-lib-1.0.0.jar
jar tf service-app/target/service-app-1.0.0.jar

mvn -pl :shared-lib dependency:tree
mvn -pl :service-app dependency:tree
mvn -pl :service-app help:effective-pom
```

The library JAR has `com/example/shared/GreetingService.class` at the root. The executable app JAR has `BOOT-INF/classes/com/example/app/ServiceApplication.class` and the nested JAR `BOOT-INF/lib/shared-lib-1.0.0.jar`. Exact filenames depend on `finalName`/classifiers if the project changes conventions.

### 8.5. Why Does the Maven BOM Not Replace Starter Parent?

If a project uses `spring-boot-starter-parent` as its Maven parent, in addition to dependency management it also supplies plugin management, compiler defaults, and the proper `repackage` execution when the app declares the plugin. However, when merely **importing the BOM** into a custom parent POM like in the example:

- You get **dependency version management**.
- You do **not** automatically inherit all plugin management/executions from Starter Parent.
- You have **no** guarantee Boot repackage is bound to the app unless you declare the plugin/execution.
- You must configure compiler/testing/encoding/plugin versions independently to suit the project.

This is why the root POM in section 8.1 manages Maven Compiler/Surefire/Boot Plugin and the app POM in section 8.3 **explicitly declares `repackage`**.

## 9. Scope, Dependency Exposure, and Publishing: Beyond Just a Green Build

### 9.1. Libraries Should Declare Only the Minimal Necessary Dependencies

If `shared-lib` only holds utilities like `GreetingService`, do not add `spring-boot-starter` just to "stay aligned with Spring Boot". Adding a starter in a library can drag logging/auto-configuration and unnecessary dependencies into consumer applications.

If the library needs Spring features such as `@ConfigurationProperties`, Spring Core, validation, or a Spring Data API, declare the **narrowest dependency** matching that feature. The BOM still manages versions without forcing you into a starter or Boot packaging plugin.

### 9.2. Gradle api vs implementation

`java-library` distinguishes:

- `api 'group:artifact'`: when a type from the dependency appears in a **public signature**, consumers need to see that library on their compile classpath.
- `implementation 'group:artifact'`: the dependency is an internal detail. Consumers generally do not need to see it on their compile classpath, yet still need it at runtime.
- `compileOnly`: compile-time only, not present at runtime automatically; misusing it can cause `NoClassDefFoundError`.
- `runtimeOnly`: runtime only, typically suited for drivers/providers not referenced directly at compile time.
- `api platform(...)` and `implementation platform(...)`: bring version constraints within scope; they are not binary class dependencies like `api '...'`.

In Maven, `compile` is the default scope, while `provided`/`test` follow different rules. Maven lacks a full equivalent to Gradle's `api`/`implementation` pair, so if publishing a library for both build tools, inspect the dependencies in both the POM and Gradle Module Metadata rather than assuming identical metadata on both sides.

### 9.3. Publishing a Library Differs from Publishing an Application

If `shared-lib` needs to be consumed across projects via a Maven repository, in Gradle you can apply `maven-publish` and add a publication:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

publishing {
    publications {
        library(MavenPublication) {
            from components.java
        }
    }
}
```

This is a **replacement/extension snippet for the library's plugin config**; do not paste a second `plugins {}` block into the middle of a file without reorganizing. `from components.java` selects the Java component, not a Boot executable JAR. It is the proper way to ship public APIs, plain JARs, and dependency metadata to consumers.

In `app`, if you want to publish the executable JAR, publish the `bootJar` artifact separately and define an appropriate publication. Do **not** treat `BOOT-INF/classes` as a standard library JAR layout for other applications to compile against. If one module must serve as both library and app, design clear module/artifact/classifier boundaries, or better yet, split into two modules as shown here.

### 9.4. A Library's BOM Can Affect Consumers

If `shared-lib` is published across multiple ecosystems or major Spring Boot versions, consider:

- Not exporting an overly specific BOM through the API if the library aims to stay framework-neutral.
- Avoiding `enforcedPlatform` by default, as it can override consumer versions.
- Testing with an independent consumer project, not solely a project dependency inside the reactor.
- Verifying that the generated POM/module metadata at publish time contains the right dependencies and constraints.
- Documenting a compatibility matrix for Spring Framework/Boot, Java, and Jakarta APIs if the library has public signatures tied to the framework.

## 10. Common Errors When Applying Plugins to the Wrong Module

| Symptom | Common Cause | Check / Resolution |
|---|---|---|
| `:shared-lib:bootJar` asks for a main class | Boot plugin applied to a library with the Java plugin | Remove Boot plugin from the library; use only `java-library` + BOM |
| Root `build` tries to create executable JARs for every module | `subprojects { apply plugin: 'org.springframework.boot' }` | Separate plugin application per project; use `apply false` at root |
| Gradle `implementation '...:commons-lang3'` lacks version and fails resolution | Real dependency declared without importing BOM into matching configuration | Add `platform('...spring-boot-dependencies:...')` or dependency-management plugin in the right project |
| Library has BOM, yet app `bootJar` lacks Spring runtime | BOM does not add starters automatically | App must declare `implementation 'org.springframework.boot:spring-boot-starter'` or the right starter |
| `bootJar` has app classes but no library | App missing `implementation project(':shared-lib')` or runtime variant altered | Check `runtimeClasspath` and `jar tf` on the executable archive |
| App throws `NoClassDefFoundError` during `java -jar` | Library JAR/runtime dependency missing or wrongly excluded | Compare `BOOT-INF/lib`, Gradle `runtimeClasspath`, Maven dependency tree |
| Maven lib becomes an executable JAR and consumers cannot find classes | Boot `repackage` attached to library module | Keep `repackage` goal **app-only**; library stays a plain JAR |
| Maven imports BOM yet `spring-boot:repackage` does not run | BOM does not auto-configure plugin executions | Declare Boot plugin and `repackage` execution in the app |
| Maven `The requested profile ...` or module not found | Wrong `-pl`/module path or building from wrong root | Inspect `<modules>` and reactor summary; use `-pl :service-app -am` |
| Wrong Java compiler level or `UnsupportedClassVersionError` | Maven/Gradle/JDK/toolchain mismatch across modules | Pin Java 17 toolchain/release, check `java -version` and build logs |
| `@Service` in library is not found by Spring | App component scan does not cover library package | Use `@Import`, `scanBasePackageClasses`, or proper auto-configuration |
| Dependency versions differ across modules | Mismatched BOM versions/direct overrides | Use `dependencyInsight`/`dependency:tree`; align BOM policy |
| Gradle `No matching variant` | Consumer requests incompatible variant/Java version | Check `outgoingVariants`, Gradle metadata, and toolchain |
| `-plain.jar` pushed to repository as the app executable | Confused `components.java` with `bootJar` | Explicitly distinguish which artifact type is published |
| Maven standalone app build fails to resolve `shared-lib` | `shared-lib` not in local repository and reactor not used | Build from root with `-am` or run appropriate `mvn install` |
| Library includes unnecessary starter | Copied app configuration into library | Trim down to the narrowest dependencies the library truly uses |

### Architectural Verification Scenario

1. From Gradle root, run `:shared-lib:tasks --all`: there must be **no** `bootJar` in the library.
2. Run `:service-app:tasks --all`: `bootJar`/`bootRun` are present in the app.
3. Run `:shared-lib:jar` and inspect the JAR: classes are at the root package path.
4. Run `:service-app:bootJar` and inspect the app JAR: the library sits in `BOOT-INF/lib`.
5. Run `:service-app:bootRun` and then `java -jar service-app/build/libs/...`: both print the same `Hello, Java!` line from the app.
6. Run `:shared-lib:dependencyInsight` to check whether Commons Lang3 was chosen via BOM constraints or an override.
7. With Maven, inspect effective POMs of library and app: BOM is inherited, while `repackage` is declared/executed only in the app.
8. Run reactor `mvn clean verify`, inspect test reports; only then evaluate the whole project build.

## 11. Multiple Application Modules, Multiple Libraries

The model above scales by role, not by a blanket rule that "every subproject looks the same":

```text
root
├── domain-core          -> java-library + BOM
├── shared-integration   -> java-library + BOM + actual needed dependencies
├── account-service      -> Boot plugin + Java + BOM
├── billing-service      -> Boot plugin + Java + BOM
└── build-conventions    -> manages version/toolchain/quality rules
```

Each **application** has its own main class and its own executable JAR. **Libraries** remain plain JARs and can be shared across multiple apps. For cross-framework libraries, use a neutral BOM or explicit dependency versions when needed instead of forcing every consumer onto the same Spring Boot release.

When multiple projects import the BOM, manage it in **one single place**:

- Gradle: `gradle.properties`, version catalog `libs.versions.toml`, or convention plugins to pin Boot/BOM versions.
- Maven: root parent properties + `dependencyManagement` + `pluginManagement`.
- CI: consistent wrapper/toolchain and reactor/multi-project commands; inspect dependency graphs of **release artifacts**.
- When upgrading Spring Boot: bump plugin/BOM together per policy, re-run unit/integration tests, and smoke test executable archives.

### Do Not Confuse a BOM with a Version Catalog

A Gradle **version catalog** centralizes project-declared coordinates/versions, whereas `platform(BOM)` imports **dependency constraints published as a Maven BOM**. You can use both together (catalog for BOM and plugin coordinates; platform for resolution), yet a catalog does not act like a BOM unless a project actually declares the `platform` dependency.

## 12. Real-Project Adoption Checklist

- [ ] List which modules are **libraries** and which are **applications** before writing plugin declarations.
- [ ] Root Gradle declares the Boot plugin version with `apply false`, without applying Boot across all modules.
- [ ] Libraries use `java-library` and **do not apply `org.springframework.boot`** if no executable archive is needed.
- [ ] Libraries still receive version management from the Spring Boot BOM or a dedicated policy; never apply the Boot plugin solely to get the BOM.
- [ ] The app uses Boot plugin + Java plugin, has a main class, and declares an actual `project(':shared-lib')` dependency.
- [ ] The app imports the proper BOM or configures `io.spring.dependency-management` correctly; never treat the Boot plugin alone as a BOM.
- [ ] Do not confuse `platform(...)` with an actual dependency; the BOM does not add starter or commons JARs automatically.
- [ ] Use `api`/`implementation` accurately at the public API boundary, avoiding unnecessary transitive dependencies.
- [ ] Maven root manages the BOM in `dependencyManagement` and never binds `repackage` on libraries.
- [ ] In Maven without Starter Parent, the app explicitly declares the Boot plugin and `repackage` execution.
- [ ] Verify library JAR classes sit at root package paths, while the Boot app has `BOOT-INF/classes` and `BOOT-INF/lib`.
- [ ] Use `dependencyInsight`/`dependency:tree` to inspect version sources, especially after upgrades.
- [ ] Run library unit tests, app tests, and run the **exact executable artifact** after building.
- [ ] When publishing a library, verify the Java component/Maven POM/Gradle Module Metadata with an independent consumer.
- [ ] Align plugin/BOM/Java toolchain across modules and in CI; do not force versions outside the BOM without testing.

**Conclusion:** In a multi-module build, the Spring Boot **build plugin is the tool for packaging/running applications**, while the Spring Boot **BOM is the source for aligning dependency versions**. Therefore, **a library can need the BOM without needing the Boot plugin**; **an application needs both the Boot plugin and concrete dependencies**. Separating these roles keeps libraries reusable, ensures apps package cleanly, avoids missing-`main()` errors, prevents version conflicts, and keeps task graphs and release artifacts predictable.

### Official Documentation

- [Spring — Creating a Multi Module Project](https://spring.io/guides/gs/multi-module/)
- [Spring Boot 3.5 — Gradle Getting Started](https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html)
- [Spring Boot 3.5 — Gradle Managing Dependencies](https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html)
- [Spring Boot 3.5 — Reacting to Other Gradle Plugins](https://docs.spring.io/spring-boot/3.5/gradle-plugin/reacting.html)
- [Spring Boot 3.5 — Maven Using the Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Platforms and BOMs](https://docs.gradle.org/current/userguide/platforms.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)