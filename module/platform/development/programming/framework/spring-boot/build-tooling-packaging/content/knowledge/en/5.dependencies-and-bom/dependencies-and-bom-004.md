# How Spring Boot Starters Aggregate Dependencies

In a Spring Boot project, a single dependency line like `spring-boot-starter-web` can bring along dozens of libraries for building an HTTP application: Spring MVC, Spring Core, JSON serialization, logging, and an embedded Servlet server. **Starters do not download "all of Spring."** They declare a curated group of dependencies for a specific purpose; Maven or Gradle resolves the transitive dependency graph and places the appropriate components onto the classpath.

This lesson explains the exact roles of **starters**, **BOM (Bill of Materials)**, **dependency management**, **transitive dependencies**, **auto-configuration**, and **application packaging**, so when you add a starter you know exactly what happens and how to verify it yourself. Configuration examples use **Spring Boot 3.3.5 and Java 17** to illustrate a consistent version. For other Spring Boot versions, inspect the actual dependency graph since components and versions can change.

## 1. What Is a Starter?

A **Spring Boot starter** is an "entry-point" dependency named `spring-boot-starter-*`, designed to gather libraries commonly needed for a capability. Most official starters are Maven/Gradle artifacts containing dependency-declaration metadata, rather than an application or a separate framework.

Examples of the purpose of several starters:

| Starter | Responsibility | Some Included Dependencies by Spring Boot 3.x Convention |
| --- | --- | --- |
| `spring-boot-starter` | Boot foundation | Core Spring Boot, auto-configuration, and default logging |
| `spring-boot-starter-web` | HTTP REST/Servlet MVC | Web MVC, Jackson JSON, embedded Tomcat by default |
| `spring-boot-starter-webflux` | Reactive HTTP/WebFlux | Spring WebFlux, Reactor, and Reactor Netty by default |
| `spring-boot-starter-data-jpa` | ORM/JPA | Spring Data JPA, Hibernate ORM, transactions, and related JDBC |
| `spring-boot-starter-jdbc` | JDBC/DataSource | Spring JDBC, transactions, and default connection pool |
| `spring-boot-starter-security` | Spring Security | Security libraries and default configuration integration |
| `spring-boot-starter-test` | Testing | Spring Test, JUnit Jupiter, AssertJ, Mockito, and related test libraries |
| `spring-boot-starter-actuator` | Observability/Operations | Spring Boot Actuator and operational endpoint infrastructure |

The list above summarizes **roles**, not an exact list of every JAR. For instance, `spring-boot-starter-data-jpa` brings JPA infrastructure onto the classpath, yet **does not create a database** or add an arbitrary PostgreSQL/MySQL driver. To connect to a concrete database, you still need the matching driver, URL, and credentials.

Key points to remember:

1. **Starters declare dependencies** so the build tool knows which artifacts are needed.
2. **The build tool downloads and resolves the dependency graph**, choosing versions based on version management configuration and conflict resolution rules.
3. **Spring Boot auto-configuration inspects the classpath and runtime conditions** to configure appropriate beans.
4. **The packaging plugin** builds the runnable artifact from classes and dependencies allowed into runtime.

These are four related yet distinct mechanisms. Adding a starter changes the dependency graph; it does not guarantee every bean or external service works automatically.

## 2. From One Starter Line to a Transitive Dependency Graph

Consider an application's direct dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

In Gradle, `implementation` adds a **direct dependency** to the main source set. Gradle reads the metadata of `spring-boot-starter-web`; that metadata declares other dependencies. Gradle continues reading their metadata until the required dependency set is resolved.

**Conceptual diagram** for Spring Boot 3.x (simplified; does not replace the `dependencies` output of an actual version):

```text
Application
└── spring-boot-starter-web                    (direct)
    ├── spring-boot-starter                    (transitive)
    │   ├── spring-boot
    │   ├── spring-boot-autoconfigure
    │   └── spring-boot-starter-logging
    ├── spring-boot-starter-json               (transitive)
    │   └── related Jackson libraries
    ├── spring-boot-starter-tomcat             (transitive, default)
    │   └── embedded Tomcat libraries
    ├── spring-web
    └── spring-webmvc
```

Each artifact has Maven coordinates consisting of **`groupId:artifactId:version`**, for example `org.springframework.boot:spring-boot-starter-web:3.3.5`. In a project with dependency management, you typically omit the version on individual lines because versions are managed centrally.

**Direct vs. transitive:**
- **Direct:** declared in the application's `build.gradle` / `pom.xml`.
- **Transitive:** declared by another dependency and brought in by the build tool when resolving the graph.
- **Overlapping dependencies:** multiple branches can require the same library; the build tool picks one final version according to its version resolution mechanism.
- **Scope/configuration:** determines whether a dependency is present at compile, test, runtime, or packaging.

Do not assume "starter A always contains exactly N JARs." Artifact count depends on version, platform/BOM, exclusions, other libraries, and conflict resolution rules.

## 3. BOMs Manage Versions, Starters Manage Components

These are the two roles most easily confused.

**Starters answer: "To do this job, which group of libraries is needed?"** They supply edges in the dependency graph.

**BOMs answer: "Which versions should libraries in the managed set use?"** A BOM is a POM with `<dependencyManagement>` declaring compatible versions of many artifacts for a Spring Boot line. A BOM **does not automatically add** all those artifacts to the application. Only when an artifact is actually requested by a direct/transitive dependency do version management rules take effect during resolution.

Conceptual model:

```text
                          spring-boot-dependencies BOM
                         ┌──────────────────────────────┐
                         │ manages versions for         │
                         │ Spring, Jackson, Tomcat...   │
                         └──────────────────────────────┘
                                        |
                                        v
Application --requests--> spring-boot-starter-web --requests--> spring-webmvc
                                                  \-----------> Tomcat, Jackson...
                                        |
                                 Maven/Gradle resolve
                                        |
                                        v
                     Runtime classpath with selected versions
```

In the same project, if you add both `spring-boot-starter-web` and `spring-boot-starter-data-jpa`, both may require Spring Core components. The build tool **resolves a single shared dependency graph**; it does not duplicate two completely independent copies of the same library just because there are two starters.

A BOM helps dependencies tested together by Spring Boot use compatible versions. However, it does not guarantee the entire graph always matches your expectations: explicit versions, extra platforms/constraints, other BOMs, exclusions, and conflict resolution rules can influence the outcome. **Inspect the resolved versions, not just the declared dependency lines.**

## 4. Maven: How Do Parent and BOM Work?

### 4.1. Common Setup with Spring Boot Parent

Minimal `pom.xml` example for a REST application using Spring Boot 3.3.5 and Java 17:

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
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>starter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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

Here:
- `spring-boot-starter-parent` inherits dependency management from `spring-boot-dependencies` of the same version and provides useful Maven/plugin defaults.
- `spring-boot-starter-web` needs no `<version>`: the version is managed by the parent.
- `spring-boot-starter-test` has `<scope>test</scope>`: used to compile/run tests and excluded from standard runtime artifacts.
- `spring-boot-maven-plugin` supports repackaging into an executable JAR when building per Spring Boot Maven plugin configuration.

**If the project must use another parent POM**, you can import `org.springframework.boot:spring-boot-dependencies` with `<type>pom</type>` and `<scope>import</scope>` inside `dependencyManagement`. Example snippet placed **inside `<project>`** while keeping the existing `<parent>`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Importing the BOM **manages dependency versions** but **does not inherit all plugin configurations and properties** from the Spring Boot parent. Without the parent, you must configure required Maven plugins yourself, such as the version/execution of `spring-boot-maven-plugin` per your project setup.

Maven uses a dependency mediation graph with Maven's version rules and `dependencyManagement`; a BOM import is not the same as declaring every dependency as a direct dependency.

### 4.2. Inspecting the Maven Dependency Tree

From the project directory containing `pom.xml`:

```bash
# With Maven Wrapper already generated
./mvnw dependency:tree

# Only inspect Spring-related dependencies
./mvnw dependency:tree -Dincludes=org.springframework.boot:*
```

In PowerShell, use `.\mvnw.cmd dependency:tree`; when using a filter containing `*`, quote the argument appropriately for your shell. Output displays direct/transitive paths, groups, artifacts, versions, and scopes. You can also run `./mvnw help:effective-pom` to inspect the POM after inheritance/merging, though **the effective POM does not replace the actual dependency tree**.

## 5. Gradle: Starters, Dependency-Management Plugin, and Gradle Platform

Example `build.gradle` (Groovy DSL) compatible with Spring Boot 3.3.5:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In this configuration, when the Spring Boot Gradle plugin is applied together with `io.spring.dependency-management`, the Boot plugin uses dependency management from the `spring-boot-dependencies` BOM matching the Boot plugin version. `implementation` is for main code, and `testImplementation` adds test libraries. No versions are needed on the two starters above.

**Gradle also has a native BOM/platform mechanism.** Without applying `io.spring.dependency-management`, you can explicitly declare the BOM:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is a **drop-in replacement for the `dependencies` block**, used in a build that already has `java`, repositories, and appropriate plugins/configuration. When using Gradle native `platform`, place it on **each configuration that needs management** (in the example, main and test); do not assume every custom configuration receives the BOM automatically. Avoid mixing the two version management mechanisms without a clear need, as version overrides/constraints can become hard to reason about.

### 5.1. Viewing the Graph and Selected Versions in Gradle

```bash
# All dependencies resolved for runtime classpath
./gradlew dependencies --configuration runtimeClasspath

# Why was spring-webmvc selected at this version?
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath

# Graph used when compiling/running tests
./gradlew dependencies --configuration testRuntimeClasspath
```

On Windows, use `.\gradlew.bat` instead of `./gradlew`. `dependencyInsight` shows paths pulling in the dependency and reasons for version selection. When multiple libraries request different versions of `jackson-databind`, `dependencyInsight --dependency jackson-databind --configuration runtimeClasspath` is far more useful than guessing the version from a starter name.

**Note on Gradle conflicts:** Gradle defaults to preferring the highest version among requested versions compatible with active rules/constraints; Maven has a different mediation mechanism. Constraints, `enforcedPlatform`, resolution strategies, and dependency management plugins can alter the result. Never mechanically apply Maven rules to explain Gradle or vice versa.

## 6. Starters Supply Libraries; Auto-Configuration Decides Runtime Setup

A starter contains dependency metadata; **auto-configuration** is mainly implemented by Spring Boot classes (notably in `spring-boot-autoconfigure` and auto-configurations supplied by related modules).

Once `@SpringBootApplication` starts the application, auto-configuration evaluates conditions such as:
- **`@ConditionalOnClass`**: are the required libraries/classes present on the classpath?
- **`@ConditionalOnMissingBean`**: has the application already declared a bean to replace the default?
- **`@ConditionalOnProperty`**: is the feature enabled via configuration?
- **Application type**: is it running as Servlet web, reactive web, or non-web?

For example, with `spring-boot-starter-web` in Boot 3.x, Spring MVC and embedded Tomcat classes are on the runtime classpath; if the application runs as a Servlet app and configuration conditions are satisfied, Spring Boot can auto-create the web server, `DispatcherServlet`, and many integration beans. **Having a library on the classpath is an input condition, not an unconditional guarantee that every bean will be created.**

To inspect why an auto-configuration was applied or skipped, in a test/dev run you can pass `--debug` at startup or set `debug=true` in test/dev config. Spring Boot will print the **Conditions Evaluation Report**; examine each matched/unmatched condition rather than guessing from the dependency graph. Avoid enabling debug by default in production if logs become too verbose.

## 7. Complete Example: One Starter Creates an HTTP Application

Use either the Maven or Gradle setup above. Create `src/main/java/com/example/starterdemo/StarterDemoApplication.java`:

```java
package com.example.starterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class StarterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StarterDemoApplication.class, args);
    }
}

@RestController
class HelloController {

    @GetMapping("/hello")
    String hello() {
        return "Hello from Spring Boot";
    }
}
```

This is a valid Java file on Java 17+: the public class matches `StarterDemoApplication.java`, and `HelloController` is a package-private class in the same file. Spring Boot component-scans from `com.example.starterdemo` and discovers this controller.

Run the application with either command (the project needs the corresponding Wrapper):

```bash
# Gradle project:
./gradlew bootRun

# Or Maven project:
./mvnw spring-boot:run
```

On Windows, use `.\gradlew.bat bootRun` or `.\mvnw.cmd spring-boot:run`. Once the application starts successfully with default configuration, send an HTTP request:

```bash
curl -s http://localhost:8080/hello
```

The expected **response body** is:

```text
Hello from Spring Boot
```

Depending on shell and display, tools may add prompts/newlines; the endpoint body is that exact string. If port 8080 is busy or `server.port` was changed, use the actual port. `curl` only proves the endpoint responds, not that the entire graph is correct; still run `dependencies`/`dependency:tree` to check components and versions.

Step-by-step explanation of the mechanism:

1. `spring-boot-starter-web` puts Spring MVC, the Servlet server, and supporting libraries onto the classpath.
2. BOM/dependency management resolves versions from a compatible group.
3. The Java compiler locates `SpringApplication`, `@RestController`, and `@GetMapping` from the resolved libraries.
4. At runtime, Spring Boot reads the classpath, applies auto-configuration, and creates the web server/`DispatcherServlet` when conditions match.
5. HTTP `GET /hello` is routed by Spring MVC to `HelloController.hello()`.
6. When packaging an executable JAR, the plugin places application classes and runtime dependencies into the artifact following Spring Boot's layout.

**If you remove `spring-boot-starter-web` without replacing it with equivalent web dependencies**, imports under `org.springframework.web.bind.annotation.*` are no longer guaranteed to exist at compile time. Adding web libraries manually can still work, but you must understand and maintain all required components and versions yourself. That is the practical value of starters.

## 8. Adding Multiple Starters: Shared Libraries, Not Duplicated Modules

Suppose an application both serves HTTP and uses JPA:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Here:
- `starter-web` brings web infrastructure into the graph.
- `starter-data-jpa` brings Spring Data JPA, Hibernate, and related JDBC/transaction components.
- `runtimeOnly 'org.postgresql:postgresql'` adds the PostgreSQL driver at runtime; it does not need to be on the application's compile classpath if you only use standard APIs like `DataSource`.
- `starter-test` is for tests.
- Dependencies requested by multiple branches, such as certain Spring Framework components, are resolved to a single final version rather than being declared twice for each starter.

To run for real, you still need datasource/credentials configuration and a running database. Merely adding `starter-data-jpa` can cause startup to fail without a valid DataSource/driver/configuration. That failure reflects incomplete configuration, **not a broken starter**.

Do not add both `spring-boot-starter-web` and `spring-boot-starter-webflux` just to "get all features": in Spring Boot 3.x, when both Spring MVC and WebFlux are present, Boot normally prefers a Spring MVC application unless configured otherwise. Choose Servlet or reactive based on your intended architecture; using `WebClient` alone does not require converting the entire application to a reactive server.

## 9. Customization: Exclusions and Replacing Default Components

Starters represent **opinionated defaults**, not a requirement to use every component they pull in.

Example: replacing default Tomcat with Jetty when using `spring-boot-starter-web` with Boot 3.3.x.

Gradle Groovy DSL:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
```

Maven (inside `<dependencies>`):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
```

**This is only an example of swapping servers; there is no need to do this on standard Tomcat projects.** After changing, run tests and inspect `dependency:tree`/`runtimeClasspath` to verify Tomcat is not brought in via another dependency path. A Gradle exclusion on one branch or a Maven exclusion on one dependency does not guarantee the artifact is removed if another branch still requests it.

If a library needs a version different from the BOM's managed version, identify the real cause: feature need, CVE, API change, or third-party conflict. Prefer upgrading the **Spring Boot version** to an appropriate maintained release and testing compatibility before pinning an individual transitive dependency. Version overrides can break the alignment supplied by the BOM.

In particular, **never use exclusions to hide errors** without understanding what the library does. Dropping an artifact can let the application compile while failing at runtime with `ClassNotFoundException`, `NoClassDefFoundError`, bean creation failures, or missing functionality.

## 10. How Starters Affect Compile, Test, Runtime, and Packaging Scopes

In Spring Boot, the build tool resolves configurations/scopes for each stage:

| Need | Common Gradle | Common Maven | Primary Effect |
| --- | --- | --- | --- |
| Library used by app at compile and runtime | `implementation` | `compile` (default) | Serves main code and is normally included in runtime artifacts |
| Library needed only at runtime, like JDBC driver | `runtimeOnly` | `runtime` | Present on runtime classpath |
| Tools/libraries only for tests | `testImplementation` / `testRuntimeOnly` | `test` | Absent from default executable JAR |
| Library needed only at compile time | `compileOnly` | `provided` *not completely equivalent* | Depends on build tool/deployment; inspect specific runtime classpath |

For example, `spring-boot-starter-test` must be placed in test scope/configuration. Declaring it mistakenly in `implementation` or Maven `compile` scope enlarges the production dependency footprint and can accidentally bundle test libraries into the runnable package.

With a default **Spring Boot executable JAR**, the plugin usually packages application classes/resources under `BOOT-INF/classes/` and runtime dependency JARs under `BOOT-INF/lib/`. `src/test/java` and `src/test/resources` are not normal deployment contents. A BOM only manages versions; the BOM itself does not become a set of library JARs to ship.

Verify:

```bash
# Gradle:
./gradlew clean test bootJar
./gradlew dependencies --configuration runtimeClasspath

# Maven:
./mvnw clean package
./mvnw dependency:tree
```

Then run `jar tf <path-to-jar-file>` to list the contents of the **actually built JAR**. With Gradle, the artifact is typically in `build/libs/`; with Maven, typically in `target/`. Path and filename depend on the project. Do not use `jar tf` to infer compile/test configurations: it only inspects the finished artifact.

## 11. When to Create Your Own Starter?

In multi-module projects, organizations sometimes create an "internal starter" to bundle a shared group of dependencies and auto-configuration for multiple applications. Distinguish two artifacts:

- **Library/auto-configuration:** contains the auto-configuration code, e.g., `@AutoConfiguration` classes registered via metadata matching the Spring Boot version.
- **Starter:** declares dependencies on that auto-configuration and required libraries, providing a simple entry point for applications.

Not every application needs an internal starter. If a module is simply a shared library, a regular dependency may suffice. Creating a starter makes sense when many consumers need the same set of components, the same default configuration, and coordinated version management. Runtime tests against real classpaths are essential to avoid unintentionally activating unwanted beans.

When first learning Spring Boot, understand **official starters** and dependency trees first; building custom starters is an advanced build/auto-configuration design step.

## 12. Common Misconceptions

| Misconception / Mistake | Accurate Explanation and How to Check |
| --- | --- |
| "Adding a starter automatically downloads all Spring libraries." | Only dependencies reachable from the graph are downloaded; inspect the dependency tree. |
| "A BOM adds all JARs to the project." | A BOM supplies version rules; it does not request individual artifacts. |
| "Starter and auto-configuration are the same thing." | Starters declare dependencies; auto-configuration is Spring Boot code evaluating conditions at runtime. |
| "Having `starter-data-jpa` automatically gives you PostgreSQL and a database." | You still need a driver and matching DB configuration/instance; check runtime classpath and datasource properties. |
| "Omitting the version makes the system pick the latest version." | Parent/BOM/dependency management/platform determines or constrains the version. Check the actual resolved version. |
| "Adding an exclusion makes the JAR disappear completely." | Another dependency may pull it back in; inspect the entire graph. |
| "Putting the test starter in `implementation` makes no difference." | It can leak test dependencies into runtime/packaging; use test configurations/scopes. |
| "The same starter always produces the exact same JAR count across projects." | It also depends on Boot version, scopes, exclusions, other starters, and conflict resolution. |
| "Bumping a transitive JAR is always safe." | It can break BOM-coordinated compatibility; evaluate with tests, runtime, and target version docs. |
| "Build success means Spring creates all beans." | Builds verify compile/package; auto-configuration conditions and runtime environment decide which beans are created. |

## 13. Verification Workflow Every Time You Add a Starter

1. **Identify the capability actually needed:** Servlet REST, WebFlux, JPA, JDBC, Security, Actuator, or testing.
2. **Choose the minimal starter:** add the direct dependency with the right scope/configuration.
3. **Align versions via one clear strategy:** Spring Boot parent/BOM for Maven; dependency-management plugin or Gradle platform for Gradle.
4. **Inspect the resolved dependency tree:** check libraries, versions, incoming branches, and conflicts.
5. **Check runtime conditions:** if beans/web servers are missing or configured unexpectedly, enable the condition report in a dev environment.
6. **Run tests and package:** verify actual functionality works, not just that dependencies downloaded.
7. **Inspect the artifact:** ensure no test libraries are accidentally packaged; remove redundant dependencies with verification.
8. **When upgrading versions:** review starter/BOM changes, re-run dependency trees and tests, and verify runtime compatibility.

### Remember

**Starter = bundle of "which libraries are needed"; BOM = management of "which versions to use"; Maven/Gradle = resolving the graph and building classpaths; Spring Boot auto-configuration = deciding "which beans to instantiate at runtime"; packaging = selecting "what enters the deployable artifact."** Understanding these five layers keeps dependencies under control instead of treating a `spring-boot-starter-*` line as a black box.