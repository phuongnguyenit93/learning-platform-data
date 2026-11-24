# Designing a Multi-Module Application with Properly Packaged Shared Libraries

## 1. Integrated Practice: Modules and Artifacts

As a Spring Boot application grows, placing domain logic, business rules, persistence, web endpoints, and integration code inside a single module makes the build hard to manage and code difficult to reuse. Splitting into modules establishes clear dependency boundaries, enables independent testing, and lets multiple applications share code.

A Java module used as a library must be packaged as a **standard library JAR**. An executable Spring Boot JAR has a specialized layout: application classes live under `BOOT-INF/classes` and dependencies live under `BOOT-INF/lib`. Other modules cannot read classes inside that executable archive as a regular library JAR.

This integrated practice guides multi-module Spring Boot design using Maven as the primary example, alongside the corresponding model for Gradle. The focus is on module structure, dependency graphs, version management, and packaging shared libraries so applications consume the right artifact.

After this lesson, you will be able to distinguish an aggregator POM, a parent POM, a BOM, and module dependencies; design shared libraries with clear boundaries; configure a Maven reactor; choose the proper packaging; manage dependency scopes and versions; inspect JARs; and build modules inside a reactor or publish libraries for reuse across multiple repositories.

## 2. Choosing Module Boundaries

Example of a catalog system:

| Module | Responsibility | Artifact |
| --- | --- | --- |
| `shared-kernel` | Value objects, domain primitives, interfaces, and shared code | Standard JAR |
| `catalog-app` | HTTP API, application services, runtime configuration, and entry point | Executable Boot JAR |
| `catalog-persistence` | Repository implementations, database mapping, and migrations | Standard JAR |
| `catalog-messaging` | Message adapters, producers/consumers | Standard JAR |
| `catalog-contracts` | DTO/event contracts shared across multiple services | Standard JAR |

You do not need to create all modules upfront. Split only when responsibility boundaries or reuse needs are sufficiently clear.

### 2.1. Dependency direction

A healthy dependency graph flows from the application toward the libraries/adapters it uses:

~~~text
             catalog-app
              /      \
             v        v
    shared-kernel   catalog-persistence
             ^
             |
      catalog-contracts
~~~

catalog-app depends on shared-kernel and catalog-persistence. catalog-persistence may depend on shared-kernel to use domain types. shared-kernel does not depend on catalog-app. catalog-contracts holds stable communication data types, without controllers or database implementations.

Avoid dependency cycles such as shared-kernel → catalog-app → shared-kernel. If two modules need each other's code, extract the shared abstraction into a smaller module or adjust boundaries so dependencies flow in one direction.

### 2.2. Keeping shared libraries clearly scoped

A common or utils module easily becomes a dumping ground for everything, making the API bloated and hard to evolve. Name modules by capability/context, such as catalog-domain, identity-contracts, or observability-support. Reserve shared-kernel for abstractions that are genuinely stable and used by multiple modules.

Keep the public API small. Do not export implementation classes just because they reside in the same module.

## 3. Maven Repository Structure

~~~text
catalog-platform/
├── pom.xml
├── shared-kernel/
│   ├── pom.xml
│   └── src/main/java/com/example/shared/
└── catalog-app/
    ├── pom.xml
    └── src/main/java/com/example/catalog/
~~~

The root POM manages versions and lists modules. Each module has its own POM, source tree, and artifact.

Maven has two related but distinct concepts:

- **Aggregation:** the root POM lists modules so the Maven reactor builds them together.
- **Inheritance:** a module declares the root POM as its parent to inherit properties, dependency management, plugin management, and shared configuration.

A single POM can act as both an aggregator and a parent. These two roles do not have to live in the same POM.

## 4. Root POM: Parent, Aggregator, and Dependency Management

Example root pom.xml for Spring Boot **4.1.2** and Java 17:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>catalog-platform</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>
    <modules>
        <module>shared-kernel</module>
        <module>catalog-app</module>
    </modules>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>shared-kernel</artifactId>
                <version>${project.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

- `packaging=pom` indicates the root is an aggregator/parent, not a runnable JAR.
- `modules` declares the directories participating in the reactor.
- `parent` inherits configuration from Spring Boot Starter Parent.
- `java.version` sets the Java release used by the parent/plugins.
- `dependencyManagement` manages the version of the shared module; it does not automatically add the dependency to child modules.
- Internal module versions in this example follow the platform version.

Starter Parent manages many dependency versions and plugin configurations. If an organization uses its own corporate parent, it can import the `spring-boot-dependencies` BOM into `dependencyManagement`. Importing the BOM manages dependency versions; it does not automatically add Spring Boot Maven Plugin executions to each module.

## 5. Shared Library: Packaging as a Standard Java JAR

POM for shared-kernel/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>catalog-platform</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>shared-kernel</artifactId>
    <packaging>jar</packaging>
</project>
~~~

This module uses jar packaging. The Maven JAR Plugin produces standard package paths, for example:

~~~text
com/example/shared/GreetingFormatter.class
~~~

It does not need the Spring Boot loader, `BOOT-INF/classes`, or `BOOT-INF/lib`. A library consumed as a regular dependency does not need the Spring Boot Maven Plugin.

### 5.1. Example shared class

File shared-kernel/src/main/java/com/example/shared/GreetingFormatter.java:

~~~java
package com.example.shared;

public final class GreetingFormatter {
    public String format(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.trim() + "!";
    }
}
~~~

This is plain Java library code. It does not need to know which application will call it or how the application boots.

Build this module alone in the reactor:

~~~bash
mvn -pl :shared-kernel clean verify
~~~

If this module depends on other internal modules, add `-am` so Maven also builds the required dependency modules.

## 6. Application Module: Consuming the Shared Library

POM for catalog-app/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>catalog-platform</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>catalog-app</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-kernel</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

The shared-kernel dependency does not need a version in the module because the root manages its version in dependencyManagement. Spring Boot dependency versions are also managed by Starter Parent.

Starter Parent preconfigures the execution ID `repackage`. Declaring the plugin in `build/plugins` of the application module enables executable packaging. The library module omits the plugin and therefore stays a plain JAR.

### 6.1. Using a class from the library

File catalog-app/src/main/java/com/example/catalog/GreetingController.java:

~~~java
package com.example.catalog;

import com.example.shared.GreetingFormatter;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingFormatter formatter;

    public GreetingController(GreetingFormatter formatter) {
        this.formatter = formatter;
    }

    @GetMapping(value = "/greet", produces = MediaType.TEXT_PLAIN_VALUE)
    public String greet(@RequestParam(defaultValue = "world") String name) {
        return formatter.format(name);
    }
}
~~~

File catalog-app/src/main/java/com/example/catalog/CatalogApplication.java:

~~~java
package com.example.catalog;

import com.example.shared.GreetingFormatter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
~~~

The bean is registered explicitly via `@Bean`. Component scanning by default scans the application class's package and its subpackages. If the library resides in a sibling package such as `com.example.shared`, it is not scanned automatically just because the JAR is on the classpath. For libraries containing Spring components, use `@Import`, targeted `@ComponentScan`, or proper auto-configuration.

Run the application after building:

~~~bash
java -jar catalog-app/target/catalog-app-1.0.0-SNAPSHOT.jar
~~~

Call the endpoint:

~~~bash
curl "http://localhost:8080/greet?name=Ada"
~~~

Output:

~~~text
Hello, Ada!
~~~

## 7. Maven Reactor and Build Order

When running at the root:

~~~bash
mvn clean verify
~~~

The Maven reactor collects modules, orders them by dependency relationships, and builds them in the proper sequence. Because catalog-app declares a direct dependency on shared-kernel, the reactor builds the library before the application.

You can build only the application along with its required modules:

~~~bash
mvn -pl :catalog-app -am clean verify
~~~

- `-pl :catalog-app` selects the module by artifactId.
- `-am` (also make) adds modules in the reactor that the selected module depends on.
- `clean verify` removes old outputs and runs the lifecycle up to verify, including compile, test, and package.

Declaring a version in dependencyManagement does not create a build order relationship. A reactor relationship is formed only when a module actually declares a dependency on another module. Simply listing two modules in `modules` also does not make the second module automatically depend on the first.

Useful commands:

~~~bash
mvn -pl :shared-kernel -am clean verify
mvn -pl :catalog-app -am package
mvn -pl :catalog-app dependency:tree
~~~

The Maven reactor also supports `-amd` to build modules that depend on the selected module, `-N` to disable recursive builds, and `-rf` to resume from a project.

## 8. Library JAR and Executable Boot JAR Have Different Structures

| Artifact | Main structure | Usable as a standard Java dependency? |
| --- | --- | --- |
| Library JAR | Package classes at root, e.g., com/example/shared/GreetingFormatter.class | Yes |
| Executable Spring Boot JAR | App classes in BOOT-INF/classes, dependency JARs in BOOT-INF/lib | Do not use as a regular library JAR |
| Executable Spring Boot WAR | Classes in WEB-INF/classes, dependencies in WEB-INF/lib and WEB-INF/lib-provided | Used to deploy/run in WAR layout |

Spring Boot repackage transforms the archive built in the package phase into an executable archive runnable with java -jar. By default, this goal replaces the main artifact with the repackaged archive; the regular artifact is retained with the .original suffix in the output directory.

When another module depends on a repackaged JAR, the Java compiler/runtime cannot locate classes at standard package paths because the classes reside under BOOT-INF/classes. Therefore, **reusable modules must publish standard JARs**.

### 8.1. Correct configuration

- shared-kernel: Maven jar, without Spring Boot repackage.
- catalog-app: Maven jar with Spring Boot repackage.
- Other adapters/libraries: standard JARs depending only on required APIs.
- Executable artifacts are built only in modules representing applications.

Do not add the Spring Boot Maven Plugin to a shared parent build and accidentally trigger repackage in every module. If you need centralized plugin version management, use `pluginManagement` in the parent and declare the plugin only in `build/plugins` of application modules.

## 9. When One Module Needs Both a Library JAR and an Executable JAR

Some modules both expose an API to other modules and include a standalone runnable demo/CLI program. In that case, keep the standard artifact and attach the executable artifact with a classifier, such as `exec`.

If using Spring Boot Starter Parent, customize execution ID `repackage`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Expected output:

~~~text
shared-kernel-1.0.0.jar
shared-kernel-1.0.0-exec.jar
~~~

The artifact without a classifier is the standard JAR for other modules to depend on; the artifact with the exec classifier is the executable archive for standalone execution. Normal consumers omit the classifier and therefore receive the standard JAR.

When the parent already supplies execution ID repackage, customize only that execution ID. Creating a different execution ID can cause the goal to run twice. If not using Starter Parent, declare the plugin version and a single repackage execution in the needed module.

## 10. Dependency Scopes and Library APIs

| Maven scope | Compile classpath | Runtime classpath | Passed transitively to consumers? |
| --- | --- | --- | --- |
| compile (default) | Yes | Yes | Yes |
| provided | Yes | No on Maven runtime classpath | No |
| runtime | No | Yes | Yes at runtime |
| test | Test only | Test only | No |
| system | By systemPath | By systemPath | Not recommended |
| import | Used to import BOM in dependencyManagement | Not a regular dependency scope | Imports dependency management |

### 10.1. Dependencies required for the public API

If a library's public method accepts/returns a type from an external dependency, consumers generally need that dependency on their compile classpath. Maven's compile scope is the default and is propagated transitively.

For example, a library's public API uses the Money type from another artifact:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>money-types</artifactId>
    <version>2.1.0</version>
</dependency>
~~~

If a dependency is only used internally in the implementation and does not appear in the public API, consider designing the API so consumers do not need to depend directly on that type. Maven has no exact equivalent to Gradle's api/implementation scopes; control dependency exposure through API design, scopes, optional dependencies, and appropriate exclusions.

### 10.2. Optional, provided, and systemPath

If a library has an optional integration with an external system, you can mark the dependency as optional:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>remote-adapter</artifactId>
    <version>2.1.0</version>
    <optional>true</optional>
</dependency>
~~~

Consumers needing that feature must declare the corresponding dependency. Do not mark a dependency optional if every public API or code path requires it.

`provided` normally indicates a dependency supplied by the deployment environment and is not propagated transitively per Maven dependency semantics. Do not set a dependency to provided just to shrink the JAR. Spring Boot repackage has its own rules and by default includes provided dependencies declared in the project because they may be needed at runtime in the executable archive.

Do not use `systemPath` pointing to a file like ../shared-kernel/target/shared-kernel.jar. This depends on the working directory, does not participate in normal dependency graphs, and breaks easily on CI. Use Maven coordinates; within the same reactor, Maven resolves artifacts via module dependencies, and across independent builds it fetches artifacts from repositories.

## 11. Dependency Management, BOM, and Plugin Management

| Mechanism | Manages | Automatically adds dependency/plugin to module? |
| --- | --- | --- |
| dependencyManagement | Default dependency versions, scopes, and exclusions | No |
| BOM import | Dependency management from another POM | No |
| pluginManagement | Plugin versions and default plugin configuration | Does not automatically trigger plugin execution |

Example root managing the version of an internal library:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-kernel</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Consuming modules only declare coordinates:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>shared-kernel</artifactId>
</dependency>
~~~

If using the Spring Boot BOM without Starter Parent, import the BOM:

~~~xml
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
~~~

The BOM manages dependency versions. The version and execution of Spring Boot Maven Plugin must be configured separately in pluginManagement/build/plugins.

## 12. Publishing a Shared Library Independently

If the application and library reside in the same repository/reactor, Maven can build directly from source modules. If the library lives in another repository or is shared across multiple teams, publish a proper artifact.

~~~bash
mvn clean verify
mvn install
mvn deploy
~~~

- verify runs verification steps before release.
- install installs artifacts into the local Maven repository of the machine running the build; useful for local development and testing a consumer on the same machine.
- deploy uploads artifacts and POMs to the configured remote repository.
- install does not replace publishing for other developers or CI.

Consumers declare the published groupId, artifactId, and version. Do not manually copy JARs into project directories, commit binaries into the source tree, or rely on a developer's local repository.

### 12.1. Version management

**Shared release version:** all modules in the platform share one version, such as 1.4.0. This is simple when they are released together.

**Independent versions:** the library has its own version, e.g., shared-kernel:2.3.1, and applications release on separate cadences. This suits libraries consumed by many applications with clear compatibility policies.

With SNAPSHOTs, consumers may receive unreleased changes based on repository update policies. Release versions should be immutable; if code changes are needed, release a new version. Never republish a release version with different contents.

If a library builds independently while inheriting a parent POM, the parent coordinates must also be resolvable. Publish the parent first or use an existing corporate parent.

## 13. Inspecting the Dependency Graph and Artifacts

Do not rely solely on BUILD SUCCESS. Inspect both the dependency graph and archive contents.

### 13.1. Dependency tree

~~~bash
mvn -pl :catalog-app dependency:tree -Dincludes=com.example:shared-kernel
mvn -pl :catalog-app dependency:tree -Dverbose
~~~

Confirm the right groupId/artifactId/version, appropriate dependency scope, no old versions pulled in, and no unexpected duplicate artifacts.

### 13.2. Inspecting the library JAR

~~~bash
jar tf shared-kernel/target/shared-kernel-1.0.0-SNAPSHOT.jar
~~~

Look for the class:

~~~text
com/example/shared/GreetingFormatter.class
~~~

The library JAR must have standard package paths at the root. If you see BOOT-INF/classes/com/example/shared/GreetingFormatter.class in an artifact used as a dependency, the module is being repackaged as a Boot application.

### 13.3. Inspecting the executable application JAR

~~~bash
jar tf catalog-app/target/catalog-app-1.0.0-SNAPSHOT.jar
~~~

Important entries:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/catalog/CatalogApplication.class
BOOT-INF/lib/shared-kernel-1.0.0-SNAPSHOT.jar
BOOT-INF/lib/spring-boot-*.jar
~~~

Exact version names and dependency JARs depend on the build. What must be verified is that application classes reside in BOOT-INF/classes and the shared library is packaged as a dependency JAR inside BOOT-INF/lib.

### 13.4. Running the final artifact

~~~bash
java -jar catalog-app/target/catalog-app-1.0.0-SNAPSHOT.jar
curl "http://localhost:8080/greet?name=Ada"
~~~

Expected response:

~~~text
Hello, Ada!
~~~

If runtime reports ClassNotFoundException or NoClassDefFoundError, check whether the library JAR was included in the executable archive, whether the version/scope is correct, and whether the class is at the right package path.

## 14. Component Scanning and Spring Configuration in Libraries

A plain JAR can contain Spring components, but being present on the classpath does not mean Spring automatically scans every package.

By default, @SpringBootApplication includes component scanning starting from the application class's package down to its subpackages. If the application is in com.example.catalog and the library component is in com.example.shared, the two packages are siblings; components in shared are not discovered automatically.

There are three ways to handle this:

1. **Explicit registration:** the application declares @Bean or @Import for configuration from the library.
2. **Expanded component scan:** use @ComponentScan with controlled base packages.
3. **Create an auto-configuration module:** the library supplies auto-configuration and metadata following Spring Boot's auto-configuration mechanism.

For Spring Boot libraries with auto-configuration, metadata is placed at:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Do not place @SpringBootApplication inside a shared library. The application module should own the entry point, component scan root, and its own runtime configuration.

## 15. Gradle Multi-Project: The Equivalent Model

Gradle uses settings.gradle(.kts) to define the root project and subprojects. A project dependency establishes build order and places the required module's outputs/dependencies onto the consumer's classpath.

Structure:

~~~text
catalog-platform/
├── settings.gradle.kts
├── build.gradle.kts
├── shared-kernel/build.gradle.kts
└── catalog-app/build.gradle.kts
~~~

settings.gradle.kts:

~~~kotlin
rootProject.name = "catalog-platform"
include(":shared-kernel", ":catalog-app")
~~~

Root build.gradle.kts:

~~~kotlin
plugins {
    id("org.springframework.boot") version "4.1.2" apply false
}
allprojects {
    group = "com.example"
    version = "1.0.0-SNAPSHOT"
}
~~~

Shared library build.gradle.kts:

~~~kotlin
plugins {
    id("java-library")
}
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

The Java Library Plugin provides two configurations:

- `api`: dependency exported to the consumer's compile classpath when the library's public API needs that type.
- `implementation`: dependency used internally only, not exposed to the consumer's compile classpath.

Application build.gradle.kts:

~~~kotlin
plugins {
    java
    id("org.springframework.boot")
}
dependencies {
    implementation(project(":shared-kernel"))
    implementation("org.springframework.boot:spring-boot-starter-web:4.1.2")
}
~~~

The project dependency implementation(project(":shared-kernel")) tells Gradle that the application needs the shared library. Gradle builds the library first and puts its compiled classes and transitive dependencies on the application's classpath. The Spring Boot plugin is applied only to catalog-app; the bootJar task creates the executable archive, while the shared module uses the jar task to build a standard JAR.

Verification commands:

~~~bash
./gradlew :shared-kernel:jar
./gradlew :catalog-app:bootJar
./gradlew :catalog-app:dependencies --configuration runtimeClasspath
~~~

Do not configure bootJar for a shared library if it is only consumed as a Java dependency.

## 16. CI Pipeline, Common Pitfalls, and Implementation Workflow

CI should build from the root reactor so inter-module dependencies are resolved in a single build.

Example GitHub Actions job:

~~~yaml
name: Multi-module build
on:
  push:
  pull_request:
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Verify reactor
        run: ./mvnw -B -ntp clean verify
~~~

Quality gates should include: building the entire reactor from a clean workspace; running unit tests for both the library and application; ensuring the dependency tree contains no out-of-policy versions; ensuring the shared library JAR does not have Boot layout; ensuring the application JAR has a valid manifest and Boot layout; running a runtime smoke test with java -jar; archiving or publishing release artifacts; and ensuring the build does not rely on leftover JARs in the runner's workspace/local repository.

If changes occur in shared-kernel, downstream modules may need rebuilding:

~~~bash
./mvnw -pl :shared-kernel -amd verify
~~~

### 16.1. Common errors table

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Application cannot find class in shared library | Dependency undeclared or unsuitable scope | Check POM and dependency tree |
| Library module packaged as Boot JAR | Spring Boot repackage ran in the library | Remove Boot plugin from library or use classifier to keep standard JAR |
| Maven building app alone misses shared artifact | Built app without building/installing/deploying library | Use -am in reactor or publish the library |
| Module works locally but fails in CI | Relied on JAR installed in local Maven repository | Build entire reactor or fetch artifact from repository |
| Two modules use different shared library versions | Versions declared in scattered places | Centralize version management and check dependency tree |
| Standard JAR replaced by executable archive | Repackage without classifier | Remove plugin from library or set classifier |
| Repackage runs twice | Parent execution and child execution have different IDs | Customize execution ID repackage instead of adding a new ID |
| Shared Spring bean not found | Library package outside component scan root | Use @Import, @ComponentScan, or auto-configuration |
| Dependency cycle between modules | Unclear module boundaries and dependency direction | Extract abstractions/contracts |
| App JAR missing shared library | Dependency excluded, wrong scope, or wrong packaging | Inspect BOOT-INF/lib |
| Library JAR has BOOT-INF/classes | Mistakenly using executable Boot JAR | Build library with JAR plugin |
| Using systemPath works locally but fails in CI | Local path does not exist on runner | Use Maven coordinates |
| Gradle app does not build shared project first | Referencing manual JAR file | Use implementation(project(":shared-kernel")) |
| Runtime missing class despite compile passing | Dependency excluded from runtime archive | Check runtimeClasspath and executable archive |

### 16.2. Implementation workflow

1. Sketch the dependency graph; identify application, libraries, contracts, and adapters; verify there are no cycles.
2. Create aggregator/parent; root POM uses packaging pom and declares modules.
3. Decide version policy: shared platform version or independent versions.
4. Create the shared library with packaging jar and framework-independent code when possible.
5. Create the application module and declare the dependency on the library using Maven coordinates.
6. Enable Spring Boot repackage only on the application; keep libraries as standard JARs.
7. Manage dependencies with dependencyManagement/BOM, scopes, and intentional optional flags.
8. Build via reactor with mvn clean verify or mvn -pl :catalog-app -am verify.
9. Use jar tf to verify layouts of the library JAR and executable application JAR.
10. Run a smoke test with java -jar and call the endpoint.
11. Use mvn install for local development and mvn deploy for remote repositories.
12. Add CI gates for tests, dependency tree, artifact layout, and runtime.

## 17. Self-Check Exercises

**1. How do an aggregator POM and a parent POM differ?**

Answer: An aggregator lists modules so the reactor builds them together; a parent supplies configuration inherited by modules. One POM can fulfill both roles.

**2. Why should a shared library use packaging jar?**

Answer: It creates a JAR with classes at standard package paths, which compilers/classloaders of other modules can use directly.

**3. Why shouldn't Spring Boot repackage run in every module?**

Answer: Repackage moves classes into the Boot archive layout. Executable JARs cannot be used as standard library dependencies.

**4. Does dependencyManagement automatically add the shared library to the application?**

Answer: No. It manages versions/configuration; the application must still declare the dependency in dependencies.

**5. How does the Maven reactor know to build the shared library before the application?**

Answer: The application declares a project dependency on the shared library; the reactor uses that relationship to determine build order.

**6. When do you use -pl :catalog-app -am?**

Answer: When you only want to build the application and the modules in the reactor that it depends on.

**7. Where are classes located in an executable Boot JAR?**

Answer: Application classes live in BOOT-INF/classes; dependencies live in BOOT-INF/lib.

**8. How do you keep both a standard JAR and an executable JAR in one module?**

Answer: Configure Spring Boot repackage with a classifier, such as exec, so the executable archive is attached alongside the standard artifact.

**9. Why aren't shared Spring beans discovered automatically?**

Answer: Default component scanning starts from the application class's package and its subpackages; sibling packages need explicit import or scanning.

**10. How do Gradle api and implementation differ?**

Answer: api exports the dependency to the consumer's compile classpath when the public API requires that type; implementation keeps the dependency internal to the library's implementation.

## 18. Official References

1. [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
2. [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
3. [Apache Maven — Dependency Scopes](https://maven.apache.org/repositories/dependencies.html)
4. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
5. [Apache Maven — Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/)
6. [Apache Maven — Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/)
7. [Spring Boot 4.1.2 — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
8. [Spring Boot 4.1.2 — Maven Plugin Goals](https://docs.spring.io/spring-boot/maven-plugin/goals.html)
9. [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
10. [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
11. [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
12. [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html)
