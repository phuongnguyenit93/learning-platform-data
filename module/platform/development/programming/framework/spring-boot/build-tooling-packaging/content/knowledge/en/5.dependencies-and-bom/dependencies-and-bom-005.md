# Role and Version Management Scope of spring-boot-dependencies

A Spring Boot application typically uses Spring Framework, Jackson, logging libraries, a servlet container, validation, JDBC, testing tools, and many third-party libraries simultaneously. Picking the version of each JAR independently can make them incompatible even when every dependency downloads successfully. **`org.springframework.boot:spring-boot-dependencies`** solves most of that problem with a curated set of **dependency versions managed per Spring Boot release**.

This is a **BOM (Bill of Materials)**, published as a Maven POM. For Spring Boot 3.3.13, its coordinates are:

```text
groupId    = org.springframework.boot
artifactId = spring-boot-dependencies
version    = 3.3.13
type       = pom
```

Version `3.3.13` is simply a **fixed anchor for reproducible examples in this lesson**; in real projects, pick a Spring Boot release aligned with your project's support and security-update requirements. Crucially, the **BOM version must be chosen deliberately**, and ecosystem dependencies should be verified against the version set supported by that release.

## 1. What Is a BOM, and How Does It Differ from a Normal Dependency?

A BOM is a descriptor stating **which versions should be used when a dependency appears in the dependency graph**. In Maven, managed entries live inside `<dependencyManagement>`; it can reference other BOMs to coordinate an entire family of libraries together.

Compare two scenarios:

```text
WITHOUT CENTRALIZED MANAGEMENT
Application
 ├─ Spring Boot starter: version chosen by author
 ├─ Jackson: version chosen by author
 ├─ Logging: version chosen by author
 └─ Test libraries: version chosen by author
  -> Easy for library groups to drift apart and costly to test compatibility

WITH SPRING BOOT BOM
Application
 ├─ Spring Boot 3.3.13 BOM: catalog of managed versions
 ├─ spring-boot-starter-web  -> looks up version from BOM
 ├─ jackson-databind         -> looks up version from BOM
 ├─ spring-boot-starter-test -> looks up version from BOM
 └─ other libraries listed in BOM -> look up versions from BOM
  -> Provides a consistent version baseline for testing
```

Distinguish clearly between:

- **`<dependencies>` or `implementation`**: declares libraries the application actually needs.
- **`<dependencyManagement>` or Gradle platform**: supplies version-selection rules for dependencies *if they are used*.
- **`spring-boot-dependencies`**: a POM-type artifact containing version management metadata. It is **not an executable JAR**, contains no application Java classes, and cannot be run with `java -jar`.
- **Spring Boot starter**: a dependency aggregating libraries for a capability (web, data, security, test...). Starters *typically* pull in transitive dependencies. The BOM only selects compatible versions.

For example, importing the BOM alone without declaring `spring-boot-starter-web` will **not** add a web server or endpoints. Conversely, when declaring a starter, the BOM helps pick the starter version and managed components.

## 2. Management Scope of spring-boot-dependencies

Typical groups in the Spring Boot 3.3 ecosystem include:

| Group | Example Components Managed by the BOM | Meaning |
| --- | --- | --- |
| Spring Boot | `spring-boot`, `spring-boot-autoconfigure`, `spring-boot-starter-*` | Keeps Boot artifacts consistent with the chosen release |
| Spring Framework and Spring projects | `spring-core`, `spring-web`, Spring Data, Spring Security... | Aligns generations of the framework and related projects |
| Web/runtime | Tomcat, Jackson, Jakarta APIs, validation | Selects baseline for HTTP, JSON, and API handling |
| Persistence | Hibernate, HikariCP, listed JDBC drivers | Limits version drift across the persistence stack |
| Logging/observability | SLF4J, Logback, Micrometer... | Keeps logging/metrics combinations compatible |
| Testing | JUnit, Mockito, AssertJ, Testcontainers... | Aligns managed testing libraries |

**The actual list and versions depend on the BOM release.** Do not assume Spring Boot manages *every* artifact in a group or every library in the Java ecosystem. To check whether a specific coordinate is managed, consult **Dependency Versions** for that release and inspect your project's dependency graph/effective model.

Spring Boot's BOM may also **import specialized BOMs** (for instance, the Jackson library suite or Spring projects) to coordinate across a release train. Although that is an internal mechanism, consumers only need to consume `spring-boot-dependencies` properly and verify resolved versions.

### What Else Does a BOM Manage Besides Versions?

In Maven, `dependencyManagement` can hold some additional dependency management attributes, yet the primary value Spring Boot provides is the **version set** for listed artifacts. Do not view a BOM as an all-powerful policy managing runtime paths, security vulnerabilities, application configuration, or deployment workflows.

| What the BOM Influences | What the BOM Does Not Do by Itself |
| --- | --- |
| Supplies versions for declared dependencies that omit a version | Add dependencies absent from `<dependencies>` |
| Participates in selecting transitive dependency versions when build rules apply | Guarantee every transitive dependency stays at the same version under all overrides |
| Aligns libraries designed and tested together in a Spring Boot release | Manage JDK, Maven, Gradle Wrapper, or Docker base image versions |
| Lets you omit versions on dependencies present in its managed list | Configure Maven build plugins, Java compiler, test execution, packaging, or deployment |
| Provides a baseline for upgrading along Spring Boot releases | Automatically audit CVEs, licenses, or compatibility with out-of-BOM libraries |

**Important boundary:** Plugins for the *build process* and dependencies for *application code* are two separate categories. Importing a BOM into `<dependencyManagement>` **does not import `<pluginManagement>`** for Maven. `spring-boot-starter-parent` brings additional build defaults; that is a different choice from a pure BOM import.

## 3. How Does Maven Resolve Versions from a BOM?

In Maven, a direct dependency typically has `groupId:artifactId:version`. When a `groupId:artifactId` is managed in the effective POM, you can omit `<version>` on the dependency declaration and Maven uses the managed version.

General mechanism:

```text
pom.xml:
  dependency: spring-boot-starter-web (no version)
  dependencyManagement:
    import spring-boot-dependencies:3.3.13
                  |
                  v
           Effective POM
       maps dependency -> managed version
                  |
                  v
       Maven dependency resolution
                  |
                  v
    resolved artifact + transitive dependencies
```

With Maven, the standard BOM declaration uses `<type>pom</type>` and `<scope>import</scope>` **inside `<dependencyManagement>`**. Here `import` is not a runtime scope: Maven merges the managed entries from the BOM into the effective model.

Do not put the BOM inside `<dependencies>` expecting it to add all libraries to the application. Nor should you use `<scope>import</scope>` on a regular JAR dependency.

When direct version declarations or multiple management mechanisms exist, the outcome is no longer simply "the BOM always wins." Maven resolves according to the effective POM and dependency mediation rules; in later sections we will see how to inspect this.

## 4. Recommended Maven Approach for Typical Boot Apps: Starter Parent

A new application can inherit from `spring-boot-starter-parent`, thereby receiving `spring-boot-dependencies` dependency management **and** sensible build configuration such as encoding, Java compiler settings, plugin management, and `repackage` execution.

**Complete** `pom.xml` example for Java 17, Maven 3.9.x, Spring Boot 3.3.13:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>bom-demo</artifactId>
    <version>1.0.0</version>

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

Notes:

1. No `<version>` is needed for `spring-boot-starter-web` and `spring-boot-starter-test` because the parent supplies dependency management.
2. `<scope>test</scope>` is still required on the test starter, because version management **does not replace selecting the right scope**.
3. `spring-boot-maven-plugin` is **declared in `<build><plugins>`** to use the `repackage` configuration provided by the parent. If you remove this plugin, the project may still build a plain JAR, but you will not automatically get an executable Boot JAR.
4. Inheriting from starter parent is a separate decision; modules that already have an internal parent can use the BOM import approach in section 6.

### Runnable Java Code for the POM Above

Create `src/main/java/dev/example/bomdemo/BomDemoApplication.java`:

```java
package dev.example.bomdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class BomDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BomDemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "BOM managed";
    }
}
```

Create `src/test/java/dev/example/bomdemo/BomDemoApplicationTest.java`:

```java
package dev.example.bomdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BomDemoApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void helloReturnsExpectedText() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("BOM managed"));
    }
}
```

If the project has a Maven Wrapper use `./mvnw`, otherwise use `mvn` from an installed Maven:

```bash
mvn -version
mvn clean verify
java -jar target/bom-demo-1.0.0.jar
```

Once the application starts, open another terminal:

```bash
curl -s http://localhost:8080/hello
```

Exact returned body:

```text
BOM managed
```

What this example demonstrates: **even though the POM omits starter versions**, Maven still resolves dependencies, runs tests, and packages the app thanks to the parent + dependency management model. The HTTP response proves the app works; to see the **specific versions** Maven selected, use the dependency graph/effective POM tools in section 9.

## 5. Parent, BOM Import, and Plugin Management: Three Often-Confused Mechanisms

| Usage Pattern | Receives Dependency Management? | Receives Plugin/Build Defaults? | Suitable For |
| --- | --- | --- | --- |
| Maven inheriting `spring-boot-starter-parent` | Yes, via `spring-boot-dependencies` | Yes, from parent | Typical Maven Boot applications |
| Maven importing `spring-boot-dependencies` | Yes | **No** plugin management via import | Projects with their own parent |
| Gradle + `io.spring.dependency-management` + Boot plugin | Yes, Spring Boot plugin imports matching BOM automatically | Gradle plugins/build managed by plugins and separate Gradle config | Projects wanting property-based version customization |
| Gradle `platform("...spring-boot-dependencies...")` | Yes, as version constraints | Does not add build plugins automatically | Projects preferring Gradle's native BOM mechanism |

**Parent POM and BOM are not interchangeable names for the same thing.** Maven allows only one direct `<parent>`; if a project already has a corporate parent, you cannot add `spring-boot-starter-parent` as a second parent. Use BOM import to gain dependency management while keeping the existing parent.

**BOM import also differs from adding the Spring Boot Maven Plugin.** The BOM does not know whether the app needs the `repackage` goal, Surefire, Failsafe, or a specific Maven compiler release. Those must come from the parent or the respective plugins.

## 6. Maven Without Starter Parent: Explicit BOM Import

Place the **following snippet inside `<project>` of an existing `pom.xml`**; this is a **fragment**, not a standalone POM file:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

`jackson-databind` is added directly **only to illustrate omitting the version on a managed library**; in a typical web app it is already pulled in via the starter and needs no extra declaration without a specific reason. Both dependencies above receive managed versions from the BOM **when versions are not overridden**.

After importing, the project must still manage essential build parts normally preconfigured by Boot's parent. If building a standalone app, for example, explicitly decide:

- JDK/compiler: configure Maven Compiler Plugin (e.g., `<release>17</release>`) and an appropriate plugin version.
- Testing: configure Maven Surefire/Failsafe compatible with the JUnit/integration tests actually used.
- Executable JAR: declare `spring-boot-maven-plugin` along with its **plugin version** and `repackage` goal execution when building for `java -jar`.
- Resource filtering, encoding, and other plugins: inherit from an internal parent or configure explicitly.

Example plugin fragment inside `<build><plugins>` to build an executable JAR when using BOM import (without starter parent):

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.13</version>
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

The `repackage` goal defaults to the `package` phase, so this execution runs after Maven builds the original JAR (with `jar` packaging). **This is still a fragment**: you need a complete POM with proper compiler/test configuration to have a working Java 17 project.

Never replace `<scope>import</scope>` with `compile` or `runtime`. A BOM import serves the **dependency management model construction** step, not the runtime classpath.

## 7. Gradle: Two Ways to Consume a BOM

Gradle does not have `<parent>`/`<dependencyManagement>` like Maven. Spring Boot 3.3 supports two dependency management approaches in its official documentation.

### Approach A — Spring Dependency Management Plugin

Example `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '1.0.0'

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

When both the **Boot Gradle Plugin** and **`io.spring.dependency-management`** are applied, the Boot plugin automatically imports the `spring-boot-dependencies` BOM matching the Boot plugin version (`3.3.13` here). That is why both starters omit versions. If you only apply `org.springframework.boot` **without** the dependency management plugin or native `platform`, do not assume dependencies are automatically BOM-managed.

The dependency management plugin also supports overriding version properties used by the BOM; for example, `slf4j.version` as documented in Spring Boot docs. Only override with a clear reason and verified compatibility.

### Approach B — Native Gradle Platform

Using `build.gradle` again, but letting Gradle directly import the BOM as dependency constraints:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'dev.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create `settings.gradle`:

```groovy
rootProject.name = 'bom-demo'
```

Reuse `BomDemoApplication.java` and `BomDemoApplicationTest.java` from section 4 at their proper paths under `src/main/java/...` and `src/test/java/...`. With a Gradle Wrapper already created/installed compatible with the Boot plugin, run:

```bash
./gradlew clean build
java -jar build/libs/bom-demo-1.0.0.jar
```

On Windows, run `gradlew.bat` instead of `./gradlew`. If the project lacks a Wrapper, generate one using a compatible Gradle version; never assume `gradlew` always exists.

**Difference in constraint strength:** With `platform(...)`, versions in the BOM act as **recommendations/constraints** that can be overridden by the dependency graph, explicit constraints, or Gradle conflict resolution. With `enforcedPlatform(...)`, versions are enforced more strictly and can affect library consumers; use it only when you truly want enforcement and understand the impact. Spring Boot recommends considering Gradle's native BOM support because it can improve build performance, whereas the dependency management plugin makes property-based customization convenient.

Native `platform` applies only to the configurations you attach it to or configurations that extend them; hence the example declares it on both `implementation` and `testImplementation` so test paths also have explicit constraints. With Gradle native `platform`, **you cannot override properties inside a Maven BOM the way the dependency-management plugin does**; use Gradle dependency constraints or resolution strategy instead.

## 8. Precedence Rules: Why Actual Dependencies May Differ from the BOM

A BOM supplies a baseline, yet build tools also process several other version sources. Therefore, you cannot look solely at the BOM version and assert every artifact in `target` or `build/libs` uses that exact version.

**In Maven:**

1. An explicit version written on a direct dependency is typically used for that dependency, even if the BOM has a different managed entry.
2. A `<dependencyManagement>` entry declared directly in the project can override the corresponding entry imported from a BOM.
3. If multiple BOMs with overlapping coordinates are imported, import order and effective dependency management determine which applies; in Maven, **the entry from the first imported BOM usually takes precedence for overlapping coordinates** (unless overridden by a direct/inherited management entry with higher priority). Check the effective POM instead of guessing.
4. For transitive dependencies, Maven applies dependency management and dependency mediation (distance and declaration order) across the graph. When conflicts arise, inspect the actual graph rather than inferring from the direct POM.

**In Gradle:**

1. `platform` adds dependency constraints. Gradle still resolves conflicts using rules, constraints, and other versions in the graph.
2. `enforcedPlatform` enforces versions more strictly, which can have unintended effects on published libraries.
3. With the Spring Dependency Management Plugin, multiple imported BOMs are processed in plugin order; per plugin documentation, **a later imported BOM can override overlapping entries from an earlier BOM**. This rule *differs* from traditional Maven BOM imports.
4. A BOM constrains only the relevant configurations. Test/runtime classpaths can differ from the compile classpath if wired differently.

**Conflict example:** An application selects the Spring Boot 3.3.13 BOM, while an internal library directly declares a different Jackson version. With both requests in the graph, **the final outcome depends on the build tool and specific constraints**. The right approach is to run `dependency:tree` (Maven) or `dependencyInsight` (Gradle) to find the dependency chain and selection reason.

## 9. Inspecting What the BOM Actually Manages

### Maven — Viewing Effective Model and Dependency Graph

In the directory containing `pom.xml`:

```bash
mvn help:effective-pom
mvn dependency:tree
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
```

- `help:effective-pom` displays the project model after applying parent, imports, active profiles, and version management; look up `<dependencyManagement>`, `<pluginManagement>`, and the entry version of interest.
- `dependency:tree` displays dependencies **actually participating in the resolved graph**; very useful for finding paths pulling Jackson/SLF4J/Hibernate into the app. It does not list every library in the BOM if the app does not use it.
- `-Dincludes` restricts output to the target artifact; these commands are graph inspection examples, not substitutes for test or build gates.

### Gradle — Viewing Resolved Configurations and Version Selection Reasons

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-web --configuration runtimeClasspath
```

`dependencyInsight` identifies the module, transitive paths, and selection reasons (constraint, conflict resolution...). With the Gradle dependency-management plugin, you can inspect managed versions using reports supported by the plugin; still, the resolved classpath remains the evidence of what artifacts the application actually uses.

**Questions to answer with data, not guesses:** Which BOMs are active? Are there multiple BOMs? Is the target entry managed? Does any dependency carry an explicit version? Which version do runtime/test classpaths actually resolve? Do parent/profile/plugin constraints apply?

## 10. Overriding a BOM-Managed Version: When and How?

Spring Boot is released after testing a specific combination of libraries. **Overriding is a decision requiring careful thought**, usually driven by urgent security patches, known bugs, compatibility requirements of external systems, or integration conflicts. Avoid arbitrarily bumping versions just to "be on the latest."

| Context | Override Mechanism | Notes |
| --- | --- | --- |
| Maven with `spring-boot-starter-parent` | Property named by the BOM (e.g., `slf4j.version`) or direct entry in `dependencyManagement`/dependency | Property overrides are convenient due to inheritance; verify the exact property name in your release |
| Maven BOM import without parent | Declare the desired version entry directly in `dependencyManagement` **before** the BOM import; or specify version on direct dependency if suitable | Project-level properties usually **do not override** values already interpolated inside an imported BOM |
| Gradle with `io.spring.dependency-management` | Override managed version property or explicit plugin dependency management | Be cautious when generating/publishing Maven POMs because published metadata may not reflect every property override |
| Gradle with native `platform` | Gradle dependency constraints, resolution strategy, or rich versions | Cannot override Maven BOM properties like the dependency-management plugin does |

Maven snippet **illustrating override structure** (placed inside `<project>`, not a complete POM):

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.3</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

The number `2.17.3` is an example version showing where to pin an artifact in the POM; it **does not mean you should replace the BOM-managed version with this number** or that all 2.17.x versions are compatible. Before making a real change, check the upstream version, fix goal, and compatibility, and re-run tests.

If you need to override an **entire Jackson library suite** consistently, consider managing that suite's BOM rather than pinning a single JAR and letting sibling modules drift in version; still ensure the Spring Boot release train supports it.

### Safe Change Workflow

1. Record the **currently resolved version** and dependency paths with `dependency:tree`/`dependencyInsight`.
2. Check release notes, compatibility, and the reason for changing; prefer upgrading Spring Boot to a release with an updated BOM when viable.
3. Pick **one consistent management point**: parent property, local `dependencyManagement`, a supplementary BOM, or Gradle constraints.
4. Inspect the effective model/resolved classpaths afterward, covering compile, test, and runtime.
5. Run unit tests, integration tests, and smoke tests on the **packaged artifact**, especially when changing Spring Framework, Jackson, Tomcat, Hibernate, Spring Data, or the logging stack.
6. Document the reason for the override and plan to remove it once a newer BOM version includes the fix.

## 11. Common Edge Cases

### 11.1. A Library Is Not in the BOM

If a Maven dependency has no `<version>` and no managed entry in the effective POM, Maven fails with an error like **dependency version is missing**. A BOM cannot guess safe versions for arbitrary libraries.

**Resolution:** declare an explicit version or add an appropriate `dependencyManagement`/BOM entry, then verify compatibility; do not add a random BOM just to silence the error.

### 11.2. Two BOMs on Different Release Trains

The Spring Boot BOM and another framework/service BOM may manage overlapping modules. For instance, Spring Cloud has its own release train/compatibility matrix; do not assume every Spring Cloud version works with every Spring Boot version.

**Resolution:** select release pairs from the official compatibility matrix, check BOM ordering, and inspect the resolved graph. Importing another BOM without checking precedence can silently shift versions unexpectedly.

### 11.3. Using a Starter While Attaching a Custom Version

For example, Maven uses `spring-boot-starter-parent` 3.3.13, yet one dependency declares `spring-boot-starter-web` at a different version. That acts as an explicit override and can misalign Spring Boot artifacts from the rest.

**Resolution:** omit explicit versions on starters when following the BOM baseline. Upgrade the Spring Boot version at the parent/BOM level as a controlled change rather than swapping individual starters ad hoc.

### 11.4. Importing a BOM and Expecting `java -jar` to Run

A POM that imports a BOM **does not automatically configure the `spring-boot:repackage` goal**. It only provides dependency management.

**Resolution:** add the Spring Boot Maven Plugin and execution, or use starter parent; build with `mvn package`/`verify`, then inspect the JAR and test running it.

### 11.5. BOM, JDK, and Plugins Have Different Sources of Management

A BOM does not pick the Gradle Wrapper, Maven version, JDK 17/21, or Maven Compiler Plugin version. With Maven BOM import without parent, compiler/plugin configuration can easily be missing.

**Resolution:** manage toolchains and build plugins separately; specify JDK and build tools in CI. Distinguish managing **library versions** from managing **build tools**.

### 11.6. Does "Omitting Versions" Mean Reproducible Builds?

No. A BOM fixes many versions, yet builds are also affected by plugin versions, SNAPSHOT/dynamic dependencies, repositories, build metadata, OS, JDK, profiles, and caching/resolution rules.

**Resolution:** pin critical inputs, use Wrappers, inspect resolved graphs, and record checksums/digests and CI artifacts. A BOM is one layer in a reproducible-build strategy, not the entire strategy.

## 12. Scope Summary Through Practical Decisions

| Question | Accurate Understanding |
| --- | --- |
| I imported `spring-boot-dependencies`; will Maven download all starters automatically? | No. Only declared dependencies or those pulled through the dependency graph are downloaded. |
| Who chooses the version when a starter omits `<version>`? | Effective dependency management (typically from the Spring Boot BOM) supplies the version. |
| Will an external out-of-BOM library automatically get a version chosen? | No. You must declare a version or separate management unless the build tool has a matching constraint. |
| Does importing a BOM pin Maven/Gradle plugins? | Not via `import`; plugins/builds have separate configuration sources. |
| How does a BOM differ from `spring-boot-starter-parent`? | The BOM manages dependencies; the parent additionally inherits build defaults and plugin management. |
| Does Gradle native `platform` always enforce exact versions? | No. `platform` participates in conflict resolution; `enforcedPlatform` applies stronger enforcement. |
| If I change one dependency's version, am I still on the Boot baseline? | You have introduced an exception. Verify the graph and compatibility. |
| A version is managed in the BOM, but the app doesn't use that library; is the artifact in the JAR? | Not merely because the BOM manages it. |
| Is passing `mvn verify` proof that versions are right? | It only runs configured goals. You still need to inspect resolved dependencies and run required tests. |
| Can upgrading Boot change many transitive versions at once? | Yes. A new BOM release can manage a new set of versions; review dependency diffs and test. |

## 13. Check Your Understanding Exercises

**Exercise 1.** A POM imports `spring-boot-dependencies:3.3.13` and declares `spring-boot-starter-web` without `<version>`. What selects the starter version?

*Answer:* Maven looks up the `dependencyManagement` entry in the effective POM; if not overridden, the version managed by the 3.3.13 BOM is applied.

**Exercise 2.** Only the BOM is imported, without adding `spring-boot-starter-web`. Does the application automatically get embedded Tomcat?

*Answer:* No. Importing a BOM does not add runtime dependencies. Tomcat appears only if the actual graph pulls it in.

**Exercise 3.** A Maven project has a corporate parent and cannot inherit `spring-boot-starter-parent` directly. Can it still use Boot's managed dependencies?

*Answer:* Yes. Import `spring-boot-dependencies` inside `<dependencyManagement>` with `<type>pom</type>` and `<scope>import</scope>`, and configure build plugins and executable packaging yourself when needed.

**Exercise 4.** A Gradle project only has `id 'org.springframework.boot' version '3.3.13'`, and every dependency omits its version. Is that always sufficient?

*Answer:* No. An active dependency management mechanism is required: apply `io.spring.dependency-management` alongside the Boot plugin, or import the BOM via `platform(...)` or an equivalent mechanism.

**Exercise 5.** After adding another BOM, `jackson-databind` resolves to an unexpected version. What should you inspect?

*Answer:* Inspect the effective POM/import order (Maven) or `dependencyInsight` and constraints (Gradle), explicit versions, transitive graph, and compatibility, then fix at the version-management source.

**Exercise 6.** Someone claims the BOM also manages the Docker base image and Java runtime configuration. How do you respond?

*Answer:* False. A BOM manages dependency metadata; JDK/runtime/container images belong to separate build and deployment configurations.

### Takeaway

**`spring-boot-dependencies` helps select a consistent set of dependency versions aligned to a Spring Boot release.** It does not add libraries by itself, replace the project POM/Gradle build, import plugin management via BOM import, or prevent all overrides and conflicts. Choose a clear BOM consumption mechanism, inspect the **actual resolved graph**, and test whenever changing versions.

### Official Reference Documentation

- Spring Boot 3.3 — Maven Plugin, Using the Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot 3.3 — Gradle Plugin, Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Platforms and BOM imports: https://docs.gradle.org/current/userguide/platforms.html
- Spring Dependency Management Plugin reference: https://docs.spring.io/dependency-management-plugin/docs/current/reference/html/