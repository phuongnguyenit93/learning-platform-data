# Separating Library Modules, Application Modules, and Build Configuration Modules

As a Spring Boot project grows larger, keeping all business code, entry points, HTTP APIs, dependencies, and shared Maven/Gradle rules in the same module makes the system hard to reuse, hard to test independently, and prone to mispackaging. A well-organized **multi-module project** should clearly separate **library modules** (reusable code), **application modules** (runnable/deployable entry points), and **build configuration modules** (compiler conventions, plugins, dependency versions, testing, and publishing).

This lesson builds the same sample application with both **Maven** and **Gradle**, using **Java 17** and **Spring Boot 3.3.13**. After practicing, you will know how to make `boot-app` depend on `core-lib`, keep `core-lib` as a plain JAR, package only `boot-app` as an executable JAR, manage build conventions through Maven `build-parent` or Gradle `build-logic`, and verify the task/reactor dependency graph. The versions are used to illustrate a consistent configuration and do not imply the latest Spring Boot release.

## 1. The Three Roles and Standard Dependency Direction

| Role | Primary Responsibility | What It Contains | Artifact / Function |
| --- | --- | --- | --- |
| **Library — `core-lib`** | Provides reusable classes, interfaces, and logic, independent of deploy runtime | Java domain models, utilities, pure business logic, isolated tests | **Plain JAR**, used as a dependency |
| **Application — `boot-app`** | Wires components, boots Spring Boot, exposes endpoints, handles operational config | `@SpringBootApplication`, controllers, DI/configuration, integration tests | **Spring Boot executable JAR/WAR**, run via `java -jar` |
| **Build configuration — `build-parent` / `build-logic`** | Standardizes builds, toolchains, repositories, versions, test/plugin settings | Maven parent POM or Gradle convention plugin | Inherited/applied configuration, **not part of the application runtime** |

The source code dependency direction should be:

```text
                +-------------------------+
                |  Shared Build Rules     |
                | Maven build-parent /    |
                | Gradle build-logic      |
                +-----------+-------------+
                            |
                  applied / inherited
                      /           \
                     v             v
              +-----------+     +-----------+
              | core-lib  |<----| boot-app  |
              | plain JAR |     | Boot JAR  |
              +-----------+     +-----------+
                   ^
                   |
           reusable classes/interfaces
```

`boot-app → core-lib` is a **programming dependency**: application code imports classes from the library. `core-lib → boot-app` is a direction that **should not exist**, because it creates a circular dependency and couples the library to the deployment entry point.

Meanwhile, `build-parent`/`build-logic` only contains **build configuration** and must not be added as an `implementation` / `compile` dependency of Java code. These modules have different lifecycles:
- The library runs unit tests and produces a plain JAR.
- The application runs tests, packages a Boot JAR, and may build an image/container and deploy.
- The build configuration is read by Maven/Gradle **to define how to build**; it is not itself an application run by the JVM.

## 2. Modules, Packages, and Microservices Are Three Different Concepts

- A **Java package** such as `com.example.shared` only organizes namespaces, visibility, and class names.
- A **build module** such as `core-lib` has its own `pom.xml` or `build.gradle`, dependency graph, compile/test lifecycle, and artifact. A module can contain multiple packages.
- A **deployable application** such as `boot-app` owns the main class, runtime configuration, and running process; it can depend on dozens of libraries.
- A **microservice** is a boundary of deployment, operations, data, APIs, and system responsibilities. Having multiple modules in one repository **does not mean** you must have multiple microservices.
- A **build logic module** defines build rules for projects, not business code needed on the runtime classpath.

You can have a monorepo with 10 library modules and only one Spring Boot app; that is still a valid architecture. Never equate "contains `.java` files" with "must enable the Spring Boot plugin".

## 3. Shared Java Code for Both Maven and Gradle

Both hands-on versions share the same source tree:

```text
multi-module-demo/
├── core-lib/
│   └── src/main/java/com/example/shared/
│       └── GreetingService.java
└── boot-app/
    ├── src/main/java/com/example/app/
    │   ├── BootApplication.java
    │   └── GreetingController.java
    └── src/test/java/com/example/app/
        └── BootApplicationTest.java
```

### 3.1. Plain Java Class in the Library

Create `core-lib/src/main/java/com/example/shared/GreetingService.java`:

```java
package com.example.shared;

public final class GreetingService {

    public String greet() {
        return "hello-from-core-lib";
    }
}
```

`GreetingService` does not use any Spring Framework API, does not need `@SpringBootApplication`, and has no `main`. This is the clearest example of **code that belongs in a library**. The `com.example.shared` package is intentionally kept separate from the application package to demonstrate that bean wiring is not synonymous with component scanning.

### 3.2. Spring Boot Entry Point

Create `boot-app/src/main/java/com/example/app/BootApplication.java`:

```java
package com.example.app;

import com.example.shared.GreetingService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BootApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootApplication.class, args);
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
```

The `@Bean` method tells Spring how to create `GreetingService`. A **project dependency** places library classes onto the classpath, but **does not automatically register every class as a Spring bean**. Here, explicit `@Bean` configuration both clarifies the app's responsibility and avoids overly broad package scanning.

### 3.3. REST Controller in the Application Module

Create `boot-app/src/main/java/com/example/app/GreetingController.java`:

```java
package com.example.app;

import com.example.shared.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/hello")
    public String hello() {
        return greetingService.greet();
    }
}
```

Spring Boot uses constructor injection to pass the `GreetingService` bean into the controller. When the application starts successfully, HTTP `GET /hello` returns the response body:

```text
hello-from-core-lib
```

This is the **HTTP body**, not the entire Spring Boot log or exact console output during startup.

### 3.4. Test to Verify Module Linkage and DI

Create `boot-app/src/test/java/com/example/app/BootApplicationTest.java`:

```java
package com.example.app;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.shared.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class BootApplicationTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void findsLibraryBean() {
        assertEquals("hello-from-core-lib", greetingService.greet());
    }
}
```

JUnit Jupiter executes `@Test` when the build tool has the appropriate dependencies/runner. `@SpringBootTest` verifies the Spring context and dependency injection; this test is not a direct HTTP endpoint test. If you want to test HTTP, use MockMvc or run the JAR and call `curl` as shown later.

All files have `public class` declarations and package paths compatible with Java 17; the library code does not require starters or Spring annotations.

## 4. Maven: Why You Must Understand Both Aggregator and Parent

Maven has two mechanisms that are often conflated into one:

1. **Aggregation**: the root `pom.xml` has `<packaging>pom</packaging>` and `<modules>`, telling the **Maven reactor** which projects belong to a build run. Maven reads the modules, computes the dependency graph, and builds them in the proper order.
2. **Inheritance**: each child project declares `<parent>` to inherit properties, `dependencyManagement`, `pluginManagement`, and shared configuration. **A parent does not have to be an aggregator**, and conversely an aggregator does not automatically become the parent of every module.

To make the **build configuration module** explicit in this lesson, we use two separate POMs:

```text
multi-module-demo/                      [Maven]
├── pom.xml                            # aggregator, packaging=pom
├── build-parent/
│   └── pom.xml                        # parent, packaging=pom
├── core-lib/
│   ├── pom.xml                        # library, packaging=jar
│   └── src/main/java/...
└── boot-app/
    ├── pom.xml                        # Spring Boot executable app
    ├── src/main/java/...
    └── src/test/java/...

root aggregator --> build-parent, core-lib, boot-app (reactor modules)
build-parent --> inherited by core-lib and boot-app
boot-app -----> depends on core-lib
```

This structure can evolve into a separately published **corporate parent POM** or a simple root aggregator without pulling application plugins into every module. The Maven reactor orders modules using parent/dependency relationships, not just the declaration order in `<module>`.

## 5. Maven Root `pom.xml` — Aggregating Modules Only

Create `multi-module-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>multi-module-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>build-parent</module>
        <module>core-lib</module>
        <module>boot-app</module>
    </modules>
</project>
```

This root does not have `spring-boot-maven-plugin` and does not produce an executable application JAR. It is invoked by Maven at the repository root, after which the Maven reactor locates each module by its relative path from the POM.

**Do not confuse `<module>core-lib</module>` with a dependency of `boot-app`:** one tells the reactor where the project is located, while the other puts the library onto the compile/runtime classpath. You need both for different purposes in this structure.

## 6. Maven `build-parent/pom.xml` — Shared Build Configuration

Create `build-parent/pom.xml`:

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
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>build-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>core-lib</artifactId>
                <version>1.0.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Explanation:
- `build-parent` is a **configuration-carrying POM**, with no `src/main/java` or `main`; `<packaging>pom</packaging>` fits its role.
- Inheriting `spring-boot-starter-parent` provides Java compiler defaults, the dependency BOM, plugin management, and a prepared `repackage` execution; it **does not force every child to run the Boot plugin**.
- `java.version=17` sets the Java level for the example; verify that Maven runs on a compatible JDK.
- `<dependencyManagement>` pins the version of `core-lib` so the app can declare the dependency without repeating `<version>`.
- Because `spring-boot-maven-plugin` is **not** declared in the parent's `<build><plugins>`, library modules do not accidentally run `repackage`.
- `<relativePath/>` on the Spring Boot parent prevents Maven from trying to look up the parent POM at an incorrect local path.

In real projects, the versions of modules released together should follow a **synchronization strategy** so you do not have to edit multiple `1.0.0` literals. This lesson uses a fixed version to focus on build and packaging boundaries; when upgrading, update parent/dependency coordinates consistently.

## 7. Maven `core-lib/pom.xml` — Plain Java JAR

Create `core-lib/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>build-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../build-parent/pom.xml</relativePath>
    </parent>

    <artifactId>core-lib</artifactId>
    <packaging>jar</packaging>
</project>
```

The library inherits the group/version `com.example:core-lib:1.0.0` from the parent; `GreetingService` only needs the JDK and adds no dependencies. Maven packages it with standard `jar` rules.

Expected output: `core-lib/target/core-lib-1.0.0.jar`, containing `com/example/shared/GreetingService.class` at the root. This file is a **library JAR**, with no main method and no need for the Boot loader.

Do not add `spring-boot-starter-web` here just to make the module build. When a library genuinely needs a Spring API or another library, declare the library's exact dependency/scope. Spring Boot executable packaging is determined by the **deployable app** role, not by whether a library contains classes used by Spring.

## 8. Maven `boot-app/pom.xml` — The Only Module Running Spring Boot

Create `boot-app/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>build-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../build-parent/pom.xml</relativePath>
    </parent>

    <artifactId>boot-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core-lib</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

Four notable points:

1. The `com.example:core-lib` dependency is **explicitly** declared by the app. The version comes from the parent's `dependencyManagement`; merely managing the version in the parent **does not** automatically add the library to runtime.
2. `spring-boot-starter-web` brings in Spring MVC and the appropriate web server components; the library does not need to declare it again.
3. `spring-boot-starter-test` is in test scope only and is not packaged by default into production `BOOT-INF/lib`.
4. Only the app declares `spring-boot-maven-plugin`. The Spring Boot starter parent in the parent chain already prepares the plugin version and `repackage` execution, so `mvn package` builds an executable JAR.

Do not change `<parent>` in `boot-app` to the root aggregator POM if you still want to inherit the build configuration in `build-parent`. Maven allows only **one direct parent** per module. Aggregation and inheritance remain two separate relationships.

## 9. Maven Reactor: Building in the Right Order and Inspecting Artifacts

From the **root** containing the aggregator POM:

```bash
./mvnw clean verify
```

`verify` triggers earlier phases, including test/package according to each project's lifecycle. The Maven reactor builds the parent before children and the library before the application. The module order in XML is not a forced dependency order because the Maven reactor sorts projects based on inter-project relationships.

To build only the application along with the upstream reactor projects it needs:

```bash
./mvnw -pl boot-app -am clean package
```

- `-pl boot-app` selects the app module.
- `-am` (also make) pulls in the reactor projects the app needs, including the library and parent when part of the reactor.
- When running from the root, Maven does not require you to manually install `core-lib` into the local repository first for dependencies in the same reactor.
- Running `mvn package` directly inside `boot-app` when the parent/dependencies have not been resolved yet can fail; use a reactor command or install the required modules.

Expected output:

```text
core-lib/target/core-lib-1.0.0.jar
boot-app/target/boot-app-1.0.0.jar
```

Inspect:

```bash
jar tf core-lib/target/core-lib-1.0.0.jar
jar tf boot-app/target/boot-app-1.0.0.jar
```

Key entries:

```text
# Inside core-lib plain JAR
com/example/shared/GreetingService.class

# Inside boot-app executable JAR
BOOT-INF/classes/com/example/app/BootApplication.class
BOOT-INF/classes/com/example/app/GreetingController.class
BOOT-INF/lib/core-lib-1.0.0.jar
BOOT-INF/lib/spring-boot-3.3.13.jar
```

This is an **illustrative excerpt**, not the full `jar tf` listing. `core-lib` exists as a nested runtime JAR inside `boot-app`: this allows the app to load library classes via the Boot launcher. `core-lib` itself remains a plain JAR artifact.

Run:

```bash
java -jar boot-app/target/boot-app-1.0.0.jar
```

In a second terminal:

```bash
curl -s http://localhost:8080/hello
```

Expected HTTP body:

```text
hello-from-core-lib
```

If port 8080 is occupied, run `java -jar boot-app/target/boot-app-1.0.0.jar --server.port=8091` and call the endpoint on 8091. Stop the application after verifying.

## 10. Maven Without Spring Boot Starter Parent: What Must You Manage?

Many enterprises mandate a **corporate parent POM**. Maven only supports one direct `<parent>`, so `build-parent` can inherit the corporate parent and then **import the Spring Boot BOM** to manage dependency versions.

Example of the relevant sections in `build-parent/pom.xml` (this is a **POM snippet to merge**, not a standalone `pom.xml` file):

```xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
    <maven.compiler.release>17</maven.compiler.release>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

In a real POM, **merge** this `dependencyManagement` section with your company's existing dependency management and with `core-lib`; do not create two `<dependencyManagement>` blocks side by side just from copying examples. The corporate parent may also manage compiler/Surefire; inspect with `help:effective-pom`.

**Important:** importing the `spring-boot-dependencies` BOM **only** manages dependency versions; it **does not** automatically add plugin versions or the `repackage` execution. Therefore, without inheriting the execution from the Spring Boot parent, `boot-app` needs an explicit plugin execution:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

This is an **alternative configuration for an app not inheriting the Boot parent**. With the complete POM in section 8, do not add the execution a second time: the Spring Boot parent already defines an execution with id `repackage`.

## 11. Gradle: How `settings.gradle` and `build-logic` Differ from a Maven Parent

Gradle does not have a `<parent>` hierarchy like Maven; it uses:
- `settings.gradle` to define the **project graph**.
- Each subproject's `build.gradle` to apply plugins and declare dependencies.
- **Convention plugins** to group shared configuration, which projects opt into.
- An **included build `build-logic`** to build convention plugins for build scripts.

Equivalent structure with the same Java code:

```text
multi-module-demo/                      [Gradle]
├── settings.gradle
├── build.gradle                        # can be left empty
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/groovy/
│       └── java-common-conventions.gradle
├── core-lib/
│   ├── build.gradle
│   └── src/main/java/com/example/shared/
│       └── GreetingService.java
└── boot-app/
    ├── build.gradle
    ├── src/main/java/com/example/app/
    │   ├── BootApplication.java
    │   └── GreetingController.java
    └── src/test/java/com/example/app/
        └── BootApplicationTest.java
```

`build-logic` is a **build included for plugin resolution purposes**, not a business subproject `:build-logic`. This distinction determines how it is declared and used.

## 12. Gradle `settings.gradle`: Putting Subprojects and the Plugin Build in the Right Place

Create `multi-module-demo/settings.gradle`:

```groovy
pluginManagement {
    includeBuild('build-logic')

    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = 'multi-module-demo'

include 'core-lib', 'boot-app'
```

- `include 'core-lib', 'boot-app'` creates the project paths `:core-lib` and `:boot-app` with their own sources/build logic.
- `pluginManagement { includeBuild('build-logic') }` provides convention plugins from the included build to `plugins { id '...' }` in subprojects.
- `pluginManagement.repositories` is used for **plugin resolution** (for example `org.springframework.boot`); repositories for application code can be configured in the convention plugin or `dependencyResolutionManagement`.
- The root `build.gradle` can be left empty for this example, since there is no application at the root.

**Do not replace `includeBuild('build-logic')` with `include 'build-logic'`** if the goal is to create Gradle convention plugins under this structure. One is an independent **included build**, while the other is an ordinary **subproject**.

## 13. Gradle `build-logic`: Convention Plugin for Common Java Configuration

### 13.1. Create the Included Build

`build-logic/settings.gradle`:

```groovy
rootProject.name = 'build-logic'
```

`build-logic/build.gradle`:

```groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
```

`groovy-gradle-plugin` provides the ability to compile and register **precompiled Groovy script plugins** from `src/main/groovy`. With Kotlin DSL, the corresponding plugin is typically `kotlin-dsl` with `.gradle.kts` files; this lesson stays consistent with Groovy DSL for ease of running.

### 13.2. Write the Shared Plugin

Create `build-logic/src/main/groovy/java-common-conventions.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

tasks.withType(org.gradle.api.tasks.testing.Test).configureEach {
    useJUnitPlatform()
}
```

The file name `java-common-conventions.gradle` produces the plugin id **`java-common-conventions`**. When applied, each module receives:
- The Java plugin and default compile/test/jar tasks.
- A Java 17 toolchain (Gradle may require suitable JDK/toolchain provisioning).
- Group/version for the module artifact.
- Maven Central for resolving dependencies.
- `useJUnitPlatform()` for `Test` tasks, though it **does not automatically add** JUnit Engine/Launcher dependencies.

**The Spring Boot plugin is intentionally not applied in the common convention.** Doing so would also create Boot tasks like `bootJar` on `core-lib` even though the library has no main class. Common configuration should contain only what **every module receiving it actually needs**.

A convention plugin differs from `allprojects { ... }` in that each module wanting a convention **explicitly applies the corresponding plugin**. This is easier to test and evolve as the number of modules grows.

## 14. Gradle `core-lib`: Applying the Java Library Plugin

Create `core-lib/build.gradle`:

```groovy
plugins {
    id 'java-common-conventions'
    id 'java-library'
}
```

The `java-common-conventions` plugin already applies `java`. The `java-library` plugin adds `api`/`implementation` configurations and outgoing variant rules for libraries. Applying them together in this module is valid; `java-library` does not enable Spring Boot.

Build the plain JAR:

```bash
./gradlew :core-lib:jar
```

Expected artifact:

```text
core-lib/build/libs/core-lib-1.0.0.jar
```

Running `jar tf` will show `com/example/shared/GreetingService.class` at the archive root; there is **no** Spring Boot nested JAR layout `BOOT-INF/classes`/`BOOT-INF/lib`.

When a library needs external dependencies, use:
- `api` if the dependency is part of the library's **public API** that consumers need to compile against;
- `implementation` if it is an internal implementation detail;
- `testImplementation` and `testRuntimeOnly` for dependencies needed only in tests.

Syntax example — **do not add to the hands-on exercise** because the coordinates below are placeholders belonging to a non-existent example system:

```groovy
dependencies {
    api 'com.acme:public-contract:1.0.0'
    implementation 'com.acme:internal-helper:1.0.0'
}
```

In real code, use your project's actual artifacts. With the pure-Java `GreetingService` in section 3, you **do not need** this dependency block.

## 15. Gradle `boot-app`: Project Dependency and Boot Tasks

Create `boot-app/build.gradle`:

```groovy
plugins {
    id 'java-common-conventions'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation project(':core-lib')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.app.BootApplication'
}
```

This is the **complete `build.gradle` file** for the app, adding to the shared plugin configuration from `build-logic`. Meaning:

1. `implementation project(':core-lib')` is a **project dependency**. It both provides the compile/runtime classpath and tells Gradle which task outputs must be built before the app.
2. `spring-boot-starter-web` and the test starter have their versions resolved by dependency management matching the chosen Spring Boot version.
3. `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` adds the launcher at test runtime; `useJUnitPlatform()` is already defined by the convention plugin.
4. `springBoot.mainClass` defines the entry point of the executable JAR. It **does not** affect how `core-lib` creates its plain JAR.
5. Only `boot-app` applies `org.springframework.boot`, so Boot tasks do not run on the library.

### 15.1. Build and Test

```bash
./gradlew :boot-app:test
./gradlew :boot-app:bootJar
```

Or:

```bash
./gradlew :core-lib:jar :boot-app:bootJar
```

Gradle inspects the project dependency and automatically pulls in the necessary upstream compile/jar tasks of `core-lib`. Do not run a shell script to copy an old JAR from `build/libs` to fake a dependency, because that breaks the task graph and up-to-date behavior.

Expected executable archive:

```text
boot-app/build/libs/boot-app-1.0.0.jar
```

Run:

```bash
java -jar boot-app/build/libs/boot-app-1.0.0.jar
```

Second terminal:

```bash
curl -s http://localhost:8080/hello
```

Result body:

```text
hello-from-core-lib
```

On Windows PowerShell use `.\gradlew.bat` instead of `./gradlew`. If you need another port, pass `--server.port=8091` at the end of the `java -jar` command.

### 15.2. Inspect Library Packaging

```bash
jar tf core-lib/build/libs/core-lib-1.0.0.jar
jar tf boot-app/build/libs/boot-app-1.0.0.jar
```

Expected excerpt:

```text
# Plain library JAR
com/example/shared/GreetingService.class

# Spring Boot application JAR
BOOT-INF/classes/com/example/app/BootApplication.class
BOOT-INF/classes/com/example/app/GreetingController.class
BOOT-INF/lib/core-lib-1.0.0.jar
```

The Spring Boot loader handles `BOOT-INF/lib/core-lib-1.0.0.jar` as a nested dependency JAR. Do **not** expect `core-lib` classes to be unpacked directly into `BOOT-INF/classes/com/example/shared` in this default packaging layout.

`boot-app` may also create a plain JAR with the `plain` classifier if the Gradle Java `jar` task is enabled. In CI, **select only the executable JAR**; avoid using a `*.jar` wildcard and accidentally deploying `-plain.jar` or the library.

## 16. Distinguishing Module Relationships and Runtime Scope

| Relationship | Example | Effect |
| --- | --- | --- |
| Maven aggregator modules | Root `<modules><module>core-lib</module>...` | Adds projects to the reactor |
| Maven parent | `<parent>build-parent</parent>` | Inherits properties, plugin/dependency management |
| Maven dependency | `<dependency>com.example:core-lib</dependency>` | Puts library classes on the app classpath |
| Gradle included build | `includeBuild('build-logic')` | Provides convention plugins to build scripts |
| Gradle project inclusion | `include 'core-lib','boot-app'` | Creates `:core-lib` / `:boot-app` |
| Gradle project dependency | `implementation project(':core-lib')` | Adds the library to the app's compile/runtime graph |
| Gradle task dependency | `dependsOn(':core-lib:jar')` | Requires running a task in the graph, **does not add the library to the classpath** |

**You cannot replace a Maven `<dependency>` with a `<module>`**, or replace Gradle `implementation project(...)` with `dependsOn(...)`. One mechanism selects **projects/lifecycle**, while the other selects **code and artifacts on the classpath**.

In Maven, `dependencyManagement` manages versions but **does not pull in dependencies**; `pluginManagement` manages versions/config but does not force plugins to run in every module. In Gradle, `pluginManagement.repositories` serves plugin resolution and is not automatically a repository for Java application dependencies.

## 17. Spring Component Scan Across Modules: Understanding the Mechanism

`@SpringBootApplication` in `com.example.app` scans classes in the `com.example.app` package and its subpackages by default. However, the library's Java class resides in `com.example.shared`. Even when Gradle/Maven packages `core-lib` properly, **a `@Service` in a sibling package may still not be found by component-scan**.

In the example, `@Bean` on `BootApplication` resolves this transparently:

```java
@Bean
GreetingService greetingService() {
    return new GreetingService();
}
```

This is just a **method snippet** inside the `BootApplication` class already shown in section 3, not a standalone Java file.

In real systems, other options can include:
- `@Import` a configuration from the library.
- Conditional auto-configuration, registered according to the Spring Boot mechanism appropriate for your version.
- Deliberate `scanBasePackages` when the library genuinely contains components that need to be scanned.
- Placing packages under a common root namespace when the design allows.

Do not use `scanBasePackages="com.example"` unconditionally in a large repo: it can accidentally scan beans from other modules, pull in unwanted configurations, or cause bean name conflicts. **Module dependencies do not replace DI/component-scanning architecture.**

## 18. Why Not Enable the Spring Boot Plugin on Every Library?

An anti-pattern in Gradle:

```groovy
// Avoid doing this for all projects regardless of role.
subprojects {
    apply plugin: 'org.springframework.boot'
}
```

If `core-lib` has no `main`, `bootJar` may fail to find a main class or produce an executable archive unsuitable as a library dependency. Implicitly applying plugins from the root also makes modules harder to reason about when building.

In Maven, the analogous mistake is placing `spring-boot-maven-plugin` inside `<build><plugins>` of the parent so every child inherits it. When the `repackage` goal runs on a library, Maven may produce a Boot archive with the wrong role or fail due to the missing entry point.

The right approach:
- **Maven:** keep the plugin version/default config in `pluginManagement` at the parent; only the app declares the plugin in `build.plugins`.
- **Gradle:** keep Java/toolchain/test conventions in a shared plugin; only runnable application modules apply `org.springframework.boot` and have `bootJar`.
- **Library:** output a plain JAR so consumers can import classes with the proper layout.
- **Build config:** has no reason to produce a Boot executable JAR.

A library containing Spring annotations such as `@Configuration` or `@Component` can still **be a library JAR**; the artifact type depends on deployment responsibility, not on which Spring packages it imports.

## 19. Layered Testing and Build Verification

Separating tests by responsibility helps pinpoint where failures occur:

| Test | Module | Objective |
| --- | --- | --- |
| Function/algorithm unit tests | `core-lib` | Prove Java logic does not depend on a Spring context |
| Wiring/context integration tests | `boot-app` | Prove library beans are wired properly by the app |
| HTTP adapter tests | `boot-app` | Prove endpoints/JSON/status codes behave properly |
| Executable JAR smoke test | CI/deploy | Prove the real artifact runs and serves HTTP properly |
| Build convention tests | `build-logic` / POM validation | Prove build rules do not break modules |

In the example, `BootApplicationTest` uses `@SpringBootTest` and JUnit Jupiter to verify wiring. If you add JUnit tests to pure-Java `core-lib`, the library module must **declare its own appropriate test dependencies**, rather than assuming the app's test dependencies will flow backward to the library.

### 19.1. Maven CI

Run from the root:

```bash
./mvnw -B clean verify
```

If you only need to build the app and its reactor dependencies:

```bash
./mvnw -B -pl boot-app -am clean verify
```

`-B` enables batch mode, suited for CI. Collect test XML from `boot-app/target/surefire-reports` and any other modules with tests. The deployable JAR is `boot-app/target/boot-app-1.0.0.jar`, not `core-lib/target/core-lib-1.0.0.jar`.

### 19.2. Gradle CI

```bash
./gradlew :boot-app:test :boot-app:bootJar
```

To build all projects, you can run `./gradlew build` and inspect the actual task graph. Default test reports are usually located at `boot-app/build/test-results/test` and `boot-app/build/reports/tests/test`.

After building, verify:
1. Plain JAR `core-lib` actually contains `GreetingService.class`.
2. Boot JAR has `BOOT-INF/classes/...BootApplication.class` and nested `BOOT-INF/lib/core-lib-1.0.0.jar`.
3. `java -jar` starts up successfully.
4. `GET /hello` returns `hello-from-core-lib`.
5. The pipeline deploys the **right artifact**, rather than using a wildcard to pick the first JAR.

A green build that does not produce or inspect the final artifact is **not enough** to prove deployability. Also do not treat build logic `build-logic` as a Java artifact to publish like a business library.

## 20. Differences in Versioning and Publishing

Maven:
- The parent `build-parent` has a `groupId:artifactId:version` and `pom` packaging.
- `core-lib` and `boot-app` have separate artifacts; the sample uses a shared version `1.0.0`.
- `dependencyManagement` selects the version of `core-lib`, yet the app still declares the actual dependency.
- `pluginManagement` selects Maven plugin versions/config, yet does not apply the Boot plugin to the library.
- If a corporate parent is not the Boot parent, import the BOM and declare the appropriate plugin execution.

Gradle:
- `java-common-conventions` sets a shared Java toolchain/group/version on subprojects that apply the plugin.
- Gradle `project(':core-lib')` resolves project dependencies via outgoing variants without manually copying JARs.
- The Spring Boot plugin version and BOM/dependency versions are separate concepts that must be kept compatible.
- `build-logic` holds plugin code for the build and can be versioned separately if published later for multiple repositories.

If `core-lib` is consumed by multiple applications on different release schedules, consider **independent versioning**, compatibility rules, and repository publishing. If the app and library always release together, a synchronized version is usually simpler. Never rename a `.jar` file manually to change its version without updating dependency coordinates/POM/publication metadata.

## 21. Troubleshooting Common Issues

| Symptom | Likely Cause | Check / Fix |
| --- | --- | --- |
| Maven `boot-app` reports `core-lib` not found | Not built via reactor, version mismatch, library not installed | Run from root with `-pl boot-app -am`, inspect `dependency:tree` |
| Maven fails to resolve `build-parent` | Wrong `<relativePath>` or parent coordinates | Check `../build-parent/pom.xml` and group/version |
| Root Maven does not see a module | Wrong `<module>` path or missing child POM | Check the root aggregator and module directory |
| Maven library gets `repackage`d | Boot plugin inherited via parent `build.plugins` | Enable plugin only on app; parent manages version in `pluginManagement` |
| Gradle cannot find `java-common-conventions` | Included build/config misconfigured | Check `pluginManagement.includeBuild`, script name, and `groovy-gradle-plugin` |
| Gradle cannot find project `:core-lib` | Missing/wrong `include` in `settings.gradle` | Check `./gradlew projects` |
| Gradle `core-lib` gets a `bootJar` task | Boot plugin applied broadly | Remove the Spring Boot plugin from the library |
| Boot JAR is missing the library | App did not declare dependency or wrong scope | Check `runtimeClasspath` / Maven dependency tree |
| Gradle compiler does not see `GreetingService` | Only task `dependsOn` exists instead of a project dependency | Add `implementation project(':core-lib')` |
| ApplicationContext cannot find `GreetingService` bean | Library package is outside component scan | Use `@Bean`, `@Import`, or appropriate scanning |
| HTTP 404 when calling `/hello` | Controller not scanned or different endpoint path | Check `com.example.app` package and `@GetMapping` |
| Spring tests are not discovered | Gradle missing `useJUnitPlatform()`, missing test engine; Maven Surefire misconfigured | Inspect `testRuntimeClasspath`/Surefire reports |
| App JAR is plain and `java -jar` fails | Boot plugin or `repackage`/`bootJar` did not run, or wrong classifier picked | Check `BOOT-INF/classes`, manifest, and output filename |
| Library depends back on app | Module cycle / bad API boundary | Push interfaces down to the library/lower-level module |
| CI passes locally but pipeline fails | Different wrapper/JDK/versions/environment | Pin JDK/toolchain, check plugins and dependency versions |
| `spring-boot-starter-web` repeated in every library | Unnecessarily Boot-ifying libraries | Include only dependencies the module genuinely needs |
| `<dependencyManagement>` present, yet app lacks library classes | Version management does not pull in dependencies | Declare `<dependency>core-lib</dependency>` in the app |
| Gradle root `build` unclear on which modules run | Multi-project task graph differs from expectations | Use project paths `:boot-app:bootJar` and `--dry-run` to verify |

### 21.1. Maven Diagnostic Commands

```bash
./mvnw -pl boot-app -am validate
./mvnw -pl boot-app -am dependency:tree
./mvnw -pl boot-app help:effective-pom -Doutput=effective-pom.xml
```

`effective-pom` shows the merged parent/plugins/dependency management. `dependency:tree` shows why `core-lib` and its version were selected. In a multi-module project, remember to run from the root and select the right module.

### 21.2. Gradle Diagnostic Commands

```bash
./gradlew projects
./gradlew :core-lib:tasks --all
./gradlew :boot-app:tasks --all
./gradlew :boot-app:dependencies --configuration runtimeClasspath
./gradlew :boot-app:dependencyInsight --dependency core-lib --configuration runtimeClasspath
./gradlew :boot-app:bootJar --dry-run
```

`--dry-run` only displays the task graph and **does not build or inspect JAR files**. To know whether classes/runtime dependencies are actually in the JAR, you must run the build and use `jar tf`.

## 22. When to Add More Modules or Repositories?

The three roles above are a starting point, not a rigid limit:

- **API/contracts module:** holds shared DTOs/interfaces if multiple apps need the same contract.
- **Domain module:** separates framework-independent business logic from web/persistence adapters.
- **Persistence adapter module:** holds JPA/JDBC implementations and database-specific dependencies.
- **Batch/worker app module:** has a different main class and deployment from the REST app.
- **Integration-test module:** if tests require dedicated infrastructure and lifecycles, wired properly into the build.
- **Separate build convention repo:** only when shared across multiple repositories that need independent policy/versioning.

Every module adds overhead for dependency management, testing, publishing, and releasing. **Do not split modules just to organize folders**; split when there is a clear boundary of responsibility, coupling, dependencies, ownership, or release cadence.

A path for migrating from a single project to multi-module:
1. Extract pure Java domain/utility code into `core-lib`.
2. Keep the main class, HTTP adapters, and runtime configuration in `boot-app`.
3. Ensure dependencies flow only from the app down to libraries, with no cycles.
4. Move common compiler/test/plugin rules into a Maven `build-parent` or Gradle convention plugin.
5. Enable Spring Boot packaging only on the app.
6. Run tests and build the reactor/task graph.
7. Verify the library JAR versus the executable JAR.
8. Update CI artifact paths and smoke tests on the **actual deployed file**.

## 23. Architecture and Build Checklist

- [ ] Clearly separate **library**, **application**, and **build configuration** roles and dependency direction.
- [ ] `core-lib` holds reusable Java code, with no Spring Boot main/packaging plugin.
- [ ] `boot-app` has `@SpringBootApplication`, controllers, DI/configuration, and depends on `core-lib`.
- [ ] Build configuration is not added to Java runtime dependencies.
- [ ] Maven root aggregator `<modules>` lists the right projects; child POMs use `build-parent` properly.
- [ ] Maven parent uses `dependencyManagement`/`pluginManagement` properly; only the app enables `spring-boot-maven-plugin`.
- [ ] If not inheriting the Boot parent, the Maven app has an appropriate plugin version and `repackage` execution.
- [ ] Gradle `settings.gradle` distinguishes `include 'core-lib','boot-app'` from `pluginManagement.includeBuild('build-logic')`.
- [ ] The Java Gradle convention plugin does not apply the Boot plugin to the library.
- [ ] The Gradle app declares `implementation project(':core-lib')`, not merely `dependsOn` or manual JAR copying.
- [ ] Bean wiring/component scanning across modules is tested; never assume every class in a dependency becomes a Spring bean.
- [ ] Maven reactor with `-am` or Gradle project dependencies build in the right order.
- [ ] JUnit Platform/Surefire tests are discovered and reports record results.
- [ ] The plain library JAR contains classes at the root; the app Boot JAR contains `BOOT-INF/classes` and `BOOT-INF/lib/core-lib-1.0.0.jar`.
- [ ] `java -jar` starts the app, and `GET /hello` returns `hello-from-core-lib`.
- [ ] CI/CD picks only the app's executable artifact, without confusing it with libraries or plain JARs.
- [ ] Java, Spring Boot, Gradle/Maven plugins, and module versions are managed consistently.

**Conclusion:** The **library** owns *reusable code and APIs* and packages a **plain JAR**. The **application** owns the *entry point, DI, and operations* and packages a **Spring Boot executable JAR/WAR**. **Build configuration** owns *how builds work* and is inherited/applied without entering runtime. Maven requires distinguishing **aggregator from parent**; Gradle requires distinguishing **subprojects from included-build convention plugins**. Only then do you achieve a clear dependency graph, reproducible builds, and artifacts deployed for their exact purpose.

## References

- [Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Maven — POM Reference](https://maven.apache.org/pom.html)
- [Spring Boot 3.3 — Using the Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html)
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html)
- [Gradle — Precompiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html)
- [Gradle — Sharing Build Logic Between Subprojects](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)