# Aligning Spring Boot, Spring Cloud Contract, and Plugin Versions

## Lesson Objectives

In **Spring Cloud Contract**, the producer and consumer agree on HTTP or messaging behavior using the **Groovy/YAML DSL**, generate producer-side tests, package stubs, and use **Stub Runner** in consumer tests. This workflow only works reliably when **Spring Boot**, the **Spring Cloud release train**, **Spring Cloud Contract libraries**, the **Maven/Gradle plugin**, Java/JDK, and testing tools are chosen as a **compatible combination**.

The **Tool Compatibility** chapter does not only teach how to declare a version. The goal is to know **which version belongs to which scope**, **how to verify the actual resolved versions**, and **when a green build is not yet proof of producer–consumer compatibility**.

After this lesson, you can:

- Distinguish between the Spring Boot version, Spring Cloud release train, Spring Cloud Contract (SCC) library/plugin version, and stub artifact version.
- Understand the difference between **BOM/dependency management** and **Maven pluginManagement** and **Gradle plugin resolution**.
- Create a consistent Maven/Gradle producer configuration, avoiding mismatched version lines.
- Align JDK, Maven/Gradle wrapper, Groovy, JUnit, Spring MVC/MockMvc, WebFlux/WebTestClient, and WireMock.
- Use effective POM, dependency tree, Gradle dependencyInsight, and generated sources to diagnose issues.
- Upgrade frameworks/tooling without losing producer contract tests or consumer Stub Runner coverage.
- Design a CI matrix and evidence records for both tool compatibility **and** API compatibility.

> **Version Principle:** There is no simple formula like `Spring Boot X.Y = Spring Cloud Contract X.Y` that applies to every release. Supported version tables are subject to change. Before using a specific combination, consult the **official Spring Boot–Spring Cloud compatibility table and the release notes/documentation of the Contract plugin for that exact release**. The version labels in this lesson are illustrative placeholders demonstrating the methodology, **not a verified compatibility matrix**.

## 1. Why Can a Valid Contract Still Cause a Build to FAIL?

Suppose we have a contract:

~~~yaml
description: "Get a paid order"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

The contract is straightforward, yet learners may encounter:

- The plugin fails to download or does not generate tests.
- Generated tests import a JUnit API that is not on the test classpath.
- `NoSuchMethodError`/`ClassNotFoundException` in Spring, WireMock, Jackson, or RestAssured.
- The base test uses MockMvc while the test mode is generated for WebTestClient.
- Maven reports `BUILD SUCCESS` even though no producer contract tests ran.
- Consumer Stub Runner downloads mappings from an old artifact/version.
- Producer tests PASS, but the consumer cannot parse the new response format.

Each failure belongs to a different layer:

| Layer | Question |
| --- | --- |
| **Toolchain** | Can the JDK, build tool, plugin, and libraries run together? |
| **Contract syntax/semantics** | Does the DSL accurately describe the API/message behavior? |
| **Producer verification** | Do generated tests execute and prove the implementation? |
| **Stub packaging** | Does the artifact contain the right mappings/response files and checksum? |
| **Consumer verification** | Do Stub Runner and the consumer handle the new artifact properly? |

**Do not modify DSL matchers just to mask classpath errors**, and do not blindly upgrade the plugin when the producer genuinely violates the contract.

## 2. Diagram of Version Layers

~~~mermaid
flowchart TD
    J["JDK + Maven/Gradle wrapper"] --> B["Spring Boot"]
    B --> C["Spring Cloud release train"]
    C --> L["SCC test/runtime libraries"]
    B --> F["Spring Framework/Jackson/Test"]
    M["Maven Contract plugin"] --> G["Generated tests + stub mappings"]
    D["Gradle Contract plugin"] --> G
    L --> G
    F --> G
    G --> A["Producer stub JAR"]
    A --> SR["Consumer-side Stub Runner"]
    SR --> CT["Consumer tests"]
~~~

The diagram illustrates the **relationships that must be verified**, and does not imply that the Cloud BOM manages every tool shown.

| Component | Example | Role | Typical version mechanism |
| --- | --- | --- | --- |
| Java/JDK | `JAVA_VERSION` | Compilation, running tools and tests | CI image/toolchain |
| Spring Boot | `BOOT_VERSION` | Framework, auto-config, and test stack | Boot parent/BOM/Gradle plugin |
| Spring Cloud | `CLOUD_TRAIN` | Set of compatible Cloud projects | `spring-cloud-dependencies` BOM |
| Spring Cloud Contract | `SCC_LIBRARY_VERSION` | Verifier, Stub Runner, test libraries | Cloud BOM or dependency management |
| Maven Contract plugin | `SCC_MAVEN_PLUGIN_VERSION` | Generate tests/mappings/stub artifacts | `build.plugins/pluginManagement` |
| Gradle Contract plugin | `SCC_GRADLE_PLUGIN_VERSION` | Tasks and test generation | Gradle `plugins/pluginManagement` |
| JUnit/Test engine | `JUNIT_VERSION` | Discover/run generated tests | Test dependencies + runner |
| WireMock | `WIREMOCK_VERSION` | HTTP stub mappings/runtime | Resolved dependency graph |
| Stub artifact | `order-service:2.5.0:stubs` | Producer mock response set | Application release version |

In particular, `2.5.0` in `order-service:2.5.0:stubs` is the **application version**, not the Spring Cloud Contract plugin version.

## 3. Spring Cloud Release Train and Spring Boot

Spring Cloud coordinates multiple projects—such as Config, Gateway, and Contract—under a **release train**. Spring Boot has its own lifecycle. A release train is designated to support specific Spring Boot lines.

You may encounter train names such as `2023.0.x`, `2024.0.x`, or `2025.0.x`. These are **naming examples**, not a claim that every patch of each train supports every Boot minor version from a nearby year.

### Process for Choosing the Right Pair

1. Identify the current and target Spring Boot versions.
2. Check the **official Spring Cloud compatibility table** for the exact Boot minor version.
3. Choose a release train that is still supported under organizational policy.
4. Check the **SCC version** managed by the train.
5. Read the reference/release notes of the corresponding **SCC Maven/Gradle plugin**.
6. Verify the minimum JDK, Maven/Gradle, and test framework versions.
7. Lock the versions in the repository/CI and run producer + consumer contract tests.

**The compatibility table is an input to the decision**, not something inferred from a successful local build.

### Why Boot Major Alone Is Not Enough

A Cloud train line may only support certain **Boot minor** versions. Therefore, "both are Spring Boot 3" does not prove that the chosen train supports both specific Boot 3.x releases.

If the Boot version is upgraded while the Cloud train remains unchanged, compatibility must be evaluated against the documentation, even if the application still compiles.

## 4. What Do the Spring Boot BOM and Spring Cloud BOM Manage?

The Spring Boot parent/BOM manages many dependencies for:

- Spring Framework, Spring Test, Spring Boot Test.
- Jackson and common serialization libraries.
- JUnit Jupiter/test starter.
- Reactor, Netty, and certain logging components.
- Starters and integration libraries within the Boot ecosystem.

The Spring Cloud BOM manages **Spring Cloud project dependencies** corresponding to the train.

Therefore, for producer contract tests, a sensible dependency setup is typically:

~~~text
Spring Boot test libraries      <- Boot dependency management
Spring Cloud Contract Verifier  <- Cloud dependency management
Spring Cloud Contract plugin    <- Separate plugin version
JDK + Maven/Gradle              <- Wrapper/toolchain
~~~

### Rules for Reducing Conflicts

- Prefer versions from the platform BOM.
- Limit explicit version overrides for libraries already managed by a BOM.
- Compare the **actually resolved** versions, not just the declared ones.
- When forced to override for a bug/security fix, review binary/runtime compatibility.
- Do not copy a dependency version from an old Boot project into a new Boot project without inspecting the dependency graph.

**If a `NoSuchMethodError` occurs in `spring-core`, the cause may be an incorrect dependency override**, not the contract DSL.

## 5. The BOM **Does Not Automatically Manage the Maven/Gradle Plugin Version**

This is the most critical mistake covered in this lesson.

### Dependency Management in Maven

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-dependencies</artifactId>
      <version>RELEASE_TRAIN_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

The dependency:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-starter-contract-verifier</artifactId>
  <scope>test</scope>
</dependency>
~~~

can inherit its version from the appropriate BOM.

However, the Maven Contract plugin:

~~~xml
<plugin>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-contract-maven-plugin</artifactId>
  <version>CONTRACT_PLUGIN_VERSION</version>
  <extensions>true</extensions>
</plugin>
~~~

requires its version from the plugin declaration or `pluginManagement`. **Importing `spring-cloud-dependencies` does not automatically assign a version to `build.plugins`**.

### Gradle Also Has Two Resolution Paths

In Gradle:

- `dependencies` use BOM/`platform(...)`/dependency-management/constraints.
- `plugins` are resolved via Gradle plugin markers, plugin repositories, and `settings.pluginManagement` or convention plugins.

**The Cloud BOM does not automatically force the Gradle Contract plugin to the right version**. You must align the plugin version and the Contract test dependency version separately.

## 6. Sample Maven Producer Configuration

This condensed POM uses explicit placeholders that **must be replaced with verified versions before running**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>VERIFIED_BOOT_VERSION</version>
    <relativePath/>
  </parent>

  <groupId>com.example.orders</groupId>
  <artifactId>order-service</artifactId>
  <version>2.5.0</version>

  <properties>
    <java.version>VERIFIED_JAVA_VERSION</java.version>
    <spring-cloud.version>VERIFIED_RELEASE_TRAIN</spring-cloud.version>
    <contract-plugin.version>CONTRACT_PLUGIN_VERSION</contract-plugin.version>
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
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-starter-contract-verifier</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-contract-maven-plugin</artifactId>
        <version>${contract-plugin.version}</version>
        <extensions>true</extensions>
        <configuration>
          <baseClassForTests>
            com.example.orders.contract.OrderContractBase
          </baseClassForTests>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**This is an illustrative skeleton, not a runnable POM while placeholders remain**:

- `java.version` must be a valid Java value such as `17`, not a placeholder string.
- The Contract plugin version must correspond to the Contract library line supported by the Cloud train.
- `baseClassForTests` must be a real test class with appropriate HTTP/message setup.
- If the producer uses WebFlux, replace `spring-boot-starter-web` and use the appropriate test mode.
- Having the plugin in the POM is not enough to prove that goals run and generated tests are discovered.

### Note on the Maven Parent

Do not infer the Boot parent version from `spring-cloud.version`. The two release and version management mechanisms are separate, even though they must be compatible.

## 7. Inspecting Maven Effective Configuration

Common diagnostic commands:

~~~bash
# POM after applying parent and dependency/plugin management.
./mvnw -B help:effective-pom

# Resolved Spring Cloud dependencies.
./mvnw -B dependency:tree -Dincludes=org.springframework.cloud

# Inspect the entire test dependency tree if conflicts exist.
./mvnw -B dependency:tree -Dscope=test

# Inspect goals and configuration options of the Contract Maven plugin.
./mvnw -B help:describe \
  -Dplugin=org.springframework.cloud:spring-cloud-contract-maven-plugin \
  -Ddetail
~~~

Multiline commands using `\` are for POSIX shells; in PowerShell, write them on a single line or use PowerShell's line continuation syntax.

| Tool | What it answers |
| --- | --- |
| `help:effective-pom` | What are the actual parent, properties, plugin versions, and plugin executions? |
| `dependency:tree` | Which versions of test/runtime dependencies are selected? |
| `help:describe` | Which goals/options does that plugin version support? |
| Generated test source | What code does the generator actually produce and which APIs does it import? |
| Surefire/Failsafe reports | Did the generated tests actually run? |

**Do not infer the Maven plugin version solely from `dependency:tree`**: plugins have their own classpath and resolution.

## 8. Sample Gradle Producer Configuration

Groovy DSL `build.gradle` example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'BOOT_PLUGIN_VERSION'
    id 'io.spring.dependency-management' version 'DEPENDENCY_MANAGEMENT_PLUGIN_VERSION'
    id 'org.springframework.cloud.contract' version 'CONTRACT_PLUGIN_VERSION'
}

group = 'com.example.orders'
version = '2.5.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(JAVA_VERSION)
    }
}

ext {
    set('springCloudVersion', 'RELEASE_TRAIN_VERSION')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}

contracts {
    baseClassForTests = 'com.example.orders.contract.OrderContractBase'
}
~~~

`BOOT_PLUGIN_VERSION`, `CONTRACT_PLUGIN_VERSION`, `JAVA_VERSION`, and the train version must be replaced; the example will not run as-is. A project may use `platform(...)` instead of `io.spring.dependency-management`; in that case, the BOM import syntax will differ.

**Three versions need to be checked independently:**

1. The Gradle **Spring Boot plugin**.
2. The Gradle **Spring Cloud Contract plugin**.
3. The `spring-cloud-dependencies` BOM and the SCC test libraries resolved from it.

There is no rule stating "both plugins belong to Spring so they must have the same version."

## 9. Inspecting Gradle Dependencies and Plugin Resolution

~~~bash
# Buildscript/plugin dependencies.
./gradlew buildEnvironment

# Test runtime dependency graph.
./gradlew dependencies --configuration testRuntimeClasspath

# Explain the selected Contract Verifier version.
./gradlew dependencyInsight \
  --configuration testRuntimeClasspath \
  --dependency spring-cloud-contract-verifier

# List plugin tasks on the actual project.
./gradlew tasks --all

# If the generateContractTests task exists in the version in use:
./gradlew help --task generateContractTests
~~~

The task name `generateContractTests` is a common name; the exact task and how it hooks into the lifecycle may vary depending on the plugin, version, and source set. Check `tasks --all` for the actual output.

When Gradle reports `Plugin ... was not found`, investigate the **plugin id**, **version**, `settings.pluginManagement.repositories`, Gradle Plugin Portal/corporate mirror, proxy/cache, and Gradle wrapper. Do not change the `spring-cloud-starter-contract-verifier` dependency version to fix a **plugin resolution** error.

## 10. Two Dangerous Version Mismatch Examples

### Newer Plugin, Older Test Libraries

~~~text
Boot:               BOOT_A
Cloud train:        TRAIN_A
Contract library:   CONTRACT_A (from BOM)
Contract plugin:    CONTRACT_B (overridden independently)
~~~

Risk: generated tests import APIs that no longer fit the test classpath, the DSL parser changes, or mappings are incompatible with the runner. Some patch combinations may work if verified, but they are **not valid by default**.

### Newer BOM, Older Plugin

~~~text
Boot:               BOOT_B
Cloud train:        TRAIN_B
Contract library:   CONTRACT_B
Contract plugin:    CONTRACT_A (forgotten upgrade)
~~~

Risk: the old plugin generates code for a new runtime with missing/changed APIs, generated tests fail to compile, or test/packaging defaults are no longer suitable.

**The right fix:** collect both **declared and resolved versions**, compare against a supported release train, align components to an evidence-backed baseline, and then run generated producer tests and Stub Runner.

Do not change matchers or DTOs just to work around a binary compatibility error in the generator.

## 11. Must Producer and Consumer Share the Same Boot Version?

**Not necessarily.** In production, the two services communicate over HTTP or messaging rather than sharing a JVM classpath.

~~~text
Producer Order Service:
  Spring Boot      = BOOT_P
  Spring Cloud     = TRAIN_P
  SCC plugin       = CONTRACT_P
  Stub artifact    = com.example.orders:order-service:2.5.0:stubs

Consumer Checkout:
  Spring Boot      = BOOT_C
  Spring Cloud     = TRAIN_C
  Stub Runner      = CONTRACT_C
  Resolved stub    = order-service:2.5.0:stubs
~~~

Producer and consumer can run different Boot generations as long as the **protocol and behavior** remain compatible. However, the consumer test classpath must be **internally compatible** with the consumer's own Boot/Cloud train:

- Can the Stub Runner library run in the consumer test runtime?
- Does the stub JAR generated by the producer plugin use a mapping format readable by the runner?
- Are there conflicts with WireMock dependencies/extensions?
- Can the consumer DTO/deserializer handle the new body/schema?

**Successful producer compilation does not prove consumer Stub Runner compatibility.** Both sides require separate evidence.

## 12. Stub Artifact Version Differs from Plugin Version

~~~text
Producer application version: 2.5.0
Producer stub coordinate:    com.example.orders:order-service:2.5.0:stubs
SCC plugin version:         CONTRACT_PLUGIN_VERSION
~~~

`2.5.0` belongs to **Order Service**. `CONTRACT_PLUGIN_VERSION` belongs to the **tool generating tests/stubs**. They do not need to match, and there is no numerical mapping between the two values.

An illustrative Stub Runner ID:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:2.5.0:stubs:8090",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.test/maven/releases"
)
class CheckoutContractTest {
    // Consumer assertions here.
}
~~~

This is an **annotation skeleton** requiring imports/dependencies/client wiring/assertions, not a complete test. Reading the ID:

~~~text
com.example.orders : order-service : 2.5.0 : stubs : 8090
groupId             artifactId       version  classifier port
~~~

The port is a Stub Runner runtime parameter, **not part of the Maven artifact identity**.

## 13. WireMock, Stub Runner, and Mapping Formats

Spring Cloud Contract can convert DSL definitions into mappings/response resources for HTTP stubbing. However, the **WireMock runtime**, **Stub Runner**, **mapping format**, and **SCC plugin** can evolve across release lines.

Risks:

- The WireMock runtime does not recognize a new property in the mapping JSON.
- A custom response transformer/extension uses an older WireMock major API.
- The project forces the WireMock dependency onto a major version unsupported by the Stub Runner line.
- Stub Runner starts, but requests go unmatched due to mapping/body matcher differences.
- The artifact was built by a different plugin or packaged without response files.

How to verify:

1. Identify the plugin version that generated the mappings.
2. List the contents of the `-stubs.jar` artifact.
3. Identify the WireMock version **resolved on the consumer**.
4. Read parser/startup errors and the request journal.
5. If using extensions, check the extension API against the active WireMock major version.
6. Send a scenario-matching request and assert the response—do not merely verify that the server starts.

**A security override for WireMock still requires regression testing**; upgrading a major version independently may resolve an advisory while breaking extension or Stub Runner compatibility.

## 14. JDK and Maven/Gradle Wrapper Are Also Versions to Align

Toolchain-related errors:

~~~text
UnsupportedClassVersionError
invalid target release
release version not supported
class file has wrong version
NoSuchMethodError
NoClassDefFoundError
~~~

`UnsupportedClassVersionError` usually indicates the JVM running the class does not understand the bytecode version. `invalid target release` usually relates to a compiler that does not support the specified release value. `NoSuchMethodError` can be a dependency binary mismatch, not necessarily caused by the JDK.

### Three Separate Java Questions

| Layer | What to determine |
| --- | --- |
| **JVM running the build tool** | Which JDK runs the Maven/Gradle daemon? |
| **Compiler/toolchain** | With which `--release` are generated tests and application compiled? |
| **JVM running tests** | Which Java version does the test runner/container use to load classes? |

A build can compile with a different toolchain than the JVM running Maven/Gradle. Do not rely solely on local `JAVA_HOME` on a laptop when CI uses a different image/toolchain.

Example commands to inspect the environment:

~~~bash
java -version
./mvnw -version
./gradlew --version
~~~

In a real project, only run the wrapper for the build tool in use; these commands are illustrative and you do not need to run both Maven and Gradle.

### Spring Framework Generation Shift

A major transition in the modern Spring ecosystem is the widespread use of **Jakarta EE APIs** under `jakarta.*` packages instead of legacy `javax.*` packages (such as Servlet, Validation, Persistence). Not every `javax.*` package in Java changed. If generated tests or web dependencies report missing `javax.servlet`/`jakarta.servlet`, check the Boot/Framework generation and starter/test libraries rather than manually adding an old `javax.servlet` JAR.

## 15. Groovy DSL and Groovy Runtime/Version

The Groovy DSL is processed by the plugin during the build. The Groovy runtime of the Maven plugin, Gradle/embedded Groovy, and Groovy in test dependencies **may reside on different classpaths**.

Some symptoms:

- `MissingMethodException`/`MissingPropertyException` when parsing the contract DSL.
- `NoClassDefFoundError` in Groovy internals.
- Helpers/extensions calling APIs absent in the actual Groovy version.
- The plugin does not recognize new matchers/syntax.
- Spock or Groovy test helpers use a line incompatible with the framework.

How to diagnose:

1. Determine whether the error occurs at **DSL parse**, **generated test compile**, or **test runtime**.
2. Check the Contract plugin version first.
3. Check direct Groovy overrides and Spock/test dependencies.
4. Compare the DSL against the **reference documentation for the exact plugin release**.
5. Use a minimal contract to isolate the cause if needed.
6. Do not add an arbitrary Groovy runtime just to eliminate a class-not-found error.

**A DSL parser error does not automatically mean the contract is business-incorrect.** The syntax may be supported in a different Contract version.

## 16. JUnit and Generated Test Framework

Generated tests can target different test frameworks/runners depending on configuration and plugin version.

| Component | Example to check |
| --- | --- |
| Generated import | `org.junit.Test` or `org.junit.jupiter.api.Test`? |
| Setup annotation | `@Before` or `@BeforeEach`? |
| Test engine | JUnit 4, JUnit Jupiter, or another supported engine? |
| Maven runner | Do Surefire/Failsafe discover generated tests? |
| Gradle Test | Are the framework and source set configured properly? |
| Base class | Does the generated test extend the appropriate class? |

If generated tests use **JUnit Jupiter** while the runtime only discovers **JUnit 4**, the build may compile and execute **0 tests**. Check generated imports, test reports, and runner configuration.

**Release gate condition:** when mandatory contracts exist and `0 generated producer tests` run, verification must fail; never infer PASS solely from a Maven/Gradle exit code of 0.

## 17. Choosing the Test Mode: MockMvc, WebTestClient, and Live HTTP

A failure caused not by version numbers, but by the **wrong test mode for the framework**:

| Producer stack | Typically suitable client/test mode | What to verify |
| --- | --- | --- |
| Spring MVC | MockMvc and RestAssuredMockMvc | MVC context, base class, and generated test wiring |
| Spring WebFlux | WebTestClient/RestAssuredWebTestClient when version-supported | Reactive codecs, application context, or server binding |
| Live HTTP server | Corresponding RestAssured/HTTP client | HTTP port, TLS, routing, and environment |
| Messaging | Contract Verifier message testing | Trigger method, test binder/broker, destination |

Some Contract plugin versions provide test modes such as `MOCKMVC`, `WEBTESTCLIENT`, and `EXPLICIT`. **Configuration values and setup APIs must be verified against the specific plugin release**.

### Incorrect Wiring Example

Generated tests use RestAssuredWebTestClient, yet the base test only configures:

~~~java
@BeforeEach
void setup() {
    RestAssuredMockMvc.mockMvc(mockMvc);
}
~~~

In this case, the issue is **test client mismatch with the generated code**, not necessarily an invalid response body or contract.

### Additional WebFlux Differences

- Reactor `Mono` and `Flux`, reactive HTTP codecs.
- Testing via application context differs from testing against a live server.
- Streaming SSE/NDJSON or infinite responses are not the same as a single JSON object.
- Blocking in the wrong place in a helper can cause deadlocks/stalls.
- Filter/security chains may differ when tests use standalone handlers instead of a real context.

A plugin may successfully generate static JSON tests, yet that is **insufficient** to prove streaming behavior in production. Define contract boundaries and supplementary tests accordingly.

## 18. Jackson, REST Assured, and Message Converters

A producer contract might use:

~~~yaml
description: "Get a paid order"
request:
  method: GET
  url: /api/orders/ORD-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

A generated test FAILing because JSONPath `$.status` does not exist could be due to:

- The DTO renamed `status` to `paymentStatus`.
- Jackson using a different naming strategy.
- `@JsonIgnore` or `@JsonInclude` omitting the field.
- The test context registering different modules/converters than the application runtime.
- An incorrect contract/fixture, or the producer genuinely breaking compatibility.

These failures are **not version mismatches by default**. Compare the actual response, headers, DTO/serialization, contract revision, and generated matchers before upgrading dependencies.

Conversely, a `NoSuchMethodError` in RestAssured/Jackson with a stack trace pointing into library APIs is a sign to inspect the **resolved dependency graph** and overrides.

## 19. Stub Runner and WireMock Have Independent Versions

WireMock is a core component of HTTP stubbing, yet packaging and resolution may vary across Spring Cloud Contract lines:

- Mappings/response files are generated by the Contract plugin.
- The stub JAR contains mappings and resources, typically under a `META-INF` structure by convention.
- Consumer-side Stub Runner loads the JAR and starts an HTTP stub runtime.
- The WireMock runtime along with extensions processes mappings and incoming requests.

If the producer plugin and consumer runner belong to different lines, format/API mismatches can occur.

### Common Misconceptions

A Stub Runner that **has started** does not mean:

1. It downloaded the right **GAV/classifier/version**.
2. All mappings inside the JAR were loaded.
3. Extensions loaded properly.
4. Consumer requests matched at least one mapping.
5. Consumer assertions verified business logic.

A good smoke test sends requests to the actual stub port and asserts status/headers/body per scenario, while also checking the resolved artifact version and checksum when needed.

### Avoid Arbitrary WireMock Overrides

If a transitive dependency pulls in a different WireMock version, do not force it to the latest version just to "make the numbers match." Check the version supported by the SCC/Stub Runner line, which extensions require upgrading, and relevant security advisories.

## 20. Tools Can PASS While Actual Producer Tests Are Zero

This is the most dangerous problem during migration:

~~~text
[INFO] BUILD SUCCESS

Generated contracts discovered: 0
Generated producer tests executed: 0
~~~

In this situation, **the toolchain builds cleanly, yet there is no evidence that the producer satisfies the contract**.

Causes:

- Incorrect contracts root.
- Maven plugin goals are unbound or skipped.
- Gradle Contract plugin tasks are not wired into the test lifecycle.
- Generated test sources are not picked up by the compiler/test runner.
- The test framework/engine does not discover the tests.
- CLI uses `-DskipTests` or an environment variable triggers skipping.
- Base class/test name/filter fails to meet conventions.
- CI only runs modules that do not contain producer contract tests.

### CI Rules

- Record the count of discovered contract scenarios.
- Verify that generated sources actually exist.
- Record the count of executed and skipped generated producer tests.
- If the mandatory contract set is non-empty but executed tests equal 0, **BLOCK**.
- Verify producer verification PASSES **before** publishing the stub JAR.

Never replace a failing assertion with "skip test" and declare the migration successful.

## 21. What Fields Should a Compatibility Baseline Record Contain?

A team-designed baseline might look like:

~~~yaml
# Sample record, NOT a default output of Spring Cloud Contract.
schema: "scc-toolchain-baseline/v1"
service: order-service

runtime:
  java_version: "VERIFIED_JAVA_VERSION"
  spring_boot_version: "VERIFIED_BOOT_VERSION"
  spring_cloud_train: "VERIFIED_TRAIN"

build:
  tool: Maven
  wrapper_version: "VERIFIED_WRAPPER_VERSION"
  contract_maven_plugin: "VERIFIED_PLUGIN_VERSION"

testing:
  contract_libraries: "RESOLVED_SCC_VERSION"
  test_framework: JUNIT5
  http_test_mode: MOCKMVC
  wiremock_runtime: "RESOLVED_WIREMOCK_VERSION"

evidence:
  source_commit: "ACTUAL_PRODUCER_COMMIT"
  contract_revision: "ACTUAL_CONTRACT_REVISION"
  ci_run_id: "CI_RUN_ID"
  generated_tests_report: "LINK_TEST_REPORT"
  verification: "ACTUAL_RESULT"
~~~

**Do not put these placeholders into a release record and mark PASS manually.** CI must capture actual resolved versions, commit IDs, and test results.

### Declared Version vs. Resolved Version

Two categories of data must be separated:

- **Declared:** the version placed in POM/Gradle/BOM or constraints.
- **Resolved:** the actual version chosen by Maven/Gradle after parent inheritance, dependency mediation, and plugin resolution.

A dependency without a declared version that is managed by a BOM **still has a resolved version**. A plugin inherited from a parent may differ from the version someone reading the root POM assumes.

## 22. Tool Matrix Differs from API Compatibility Matrix

### Matrix A — Build/Verify Capability of a Tool Combination

| Proposed set | Boot | Cloud train | Contract plugin | JDK | Generated tests |
| --- | --- | --- | --- | --- | --- |
| A | `BOOT_A` | `TRAIN_A` | `PLUGIN_A` | `JDK_A` | PASS/FAIL |
| B | `BOOT_B` | `TRAIN_B` | `PLUGIN_B` | `JDK_B` | PASS/FAIL |
| C | `BOOT_B` | `TRAIN_A` | `PLUGIN_A` | `JDK_B` | Only if supported |

This table is a **verification template**, not a verified matrix of valid versions.

### Matrix B — Which Consumer Version Works with Which Producer Stub?

| Producer stub | Checkout 1.8 | Checkout 2.0 | Sales Portal 4.1 |
| --- | --- | --- | --- |
| Order 2.4.0 | Historical PASS | NOT_RUN | Historical PASS |
| Order 2.5.0 | REQUIRED | REQUIRED | REQUIRED |

The two matrices do not replace each other:

- Matrix A PASS: the build/test toolchain **can execute**.
- Matrix B PASS: consumers **actually handle** the producer behavior simulated by stubs from a verified producer.

**Matching Boot/Cloud versions do not prove API compatibility**, and differing Boot/Cloud versions do not prove API incompatibility.

## 23. Upgrade in Coordinated Sets, Not Random Individual Libraries

A safe workflow:

~~~mermaid
flowchart TD
    A["Lock current PASSING baseline"] --> B["Check Boot–Cloud compatibility matrix"]
    B --> C["Select matching SCC line and Contract plugin"]
    C --> D["Verify JDK/Wrapper/JUnit/Test mode"]
    D --> E["Update BOM + plugin intentionally"]
    E --> F["Inspect effective dependency/plugin versions"]
    F --> G["Generate + run producer contract tests"]
    G --> H{"Did tests actually run and PASS?"}
    H -->|No| X["BLOCK / diagnose"]
    H -->|Yes| I["Package stub artifact + checksum"]
    I --> J["Consumer Stub Runner downloads exact JAR"]
    J --> K{"Required consumer tests PASS?"}
    K -->|No| X
    K -->|Yes| L["Record compatibility baseline and release record"]
~~~

### Step 1 — Lock the Old Baseline

Record the current Boot/Cloud/SCC/plugin/JDK/wrapper/JUnit versions, producer commit, contract revision, test reports, and stub artifact checksum.

### Step 2 — Choose a Documented Supported Set

Consult the official compatibility matrix for the target Boot release, select the Cloud train, and review SCC release notes/plugin versions plus Java/build tool requirements.

### Step 3 — Upgrade in Coordinated Groups

You do not necessarily have to change every version on the same day, but each **intermediate combination must have documented support**. Avoid changing API bodies and upgrading the framework in the same commit if they can be separated; doing so helps distinguish business regressions from tooling issues.

### Step 4 — Inspect the Resolved Graph

Review the effective POM, Gradle dependency graph, plugin resolution, and toolchain. Compare before and after, looking for direct overrides or dependency collisions.

### Step 5 — Generate and Execute Producer Tests

Compare discovered contracts, generated test sources, actual executed tests, and failures/skips. Never accept `BUILD SUCCESS` with `0 tests`.

### Step 6 — Test Stubs on the Consumer Side

Package the stub JAR from the same contract/producer build; the consumer Stub Runner must use the exact version/checksum and real assertions.

### Step 7 — Record Evidence Before Considering Release

Only claim a combination is compatible **within the scope of the verified scenarios**. Do not extrapolate to production performance, TLS, or every external consumer.

## 24. When Only the Contract Plugin Is Upgraded

Combination:

~~~text
Spring Boot:        BOOT_A
Spring Cloud BOM:   TRAIN_A
Contract library:   SCC_A
Contract plugin:    SCC_PLUGIN_B
~~~

can occur when a team edits a single line in `pom.xml` or `build.gradle`.

If plugin B is documented as compatible with library line A, it can be used after verification. Without confirmation, however, watch out for:

- Generated test code using APIs missing from the test classpath.
- Changes in DSL syntax/matcher semantics.
- Different default JUnit/test mode.
- Changes in mapping format or stub package layout.
- Build tool/plugin API incompatibility.

### Handling Rules

1. Identify the reason for upgrading independently (bug, security, feature).
2. Read release notes and compatibility information.
3. Lock the exact SCC libraries and plugin versions.
4. Run helper unit tests, generated producer tests, and stub tests.
5. Only publish if required consumer versions pass Stub Runner.

Do not "update the plugin to the latest" and keep reports from an old build as evidence for the new release.

## 25. When Only the Cloud BOM Is Upgraded and the Plugin Is Forgotten

Combination:

~~~text
Spring Boot:        BOOT_B
Spring Cloud BOM:   TRAIN_B
Contract library:   SCC_B
Contract plugin:    SCC_PLUGIN_A
~~~

In this case, generated sources may fail to compile even though Java business code has not changed.

### Investigation Steps

- From Maven effective POM/Gradle plugin config, obtain the actual plugin version.
- From the dependency graph, obtain the actual resolved SCC Verifier version.
- Read the generated test source to locate mismatched methods/imports.
- Check the JDK, JUnit engine, and base class wiring.
- Align the plugin and dependencies according to a verified release.
- Run a clean build and re-execute, saving new test reports.
- Compare stub mappings and consumer behavior.

**Do not modify contract fields to fix library method/import errors.** The contract may be completely valid while the generator and test classpath are on different lines.

## 26. Transitive Dependencies and Explicit Overrides

An internal test dependency may pull in another version of WireMock/Groovy/Jackson/RestAssured:

~~~xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>legacy-test-utils</artifactId>
  <version>LEGACY_VERSION</version>
  <scope>test</scope>
</dependency>
~~~

Places to inspect:

- Pinned direct dependency versions.
- Multiple BOM imports and their ordering/precedence.
- Maven parent, profiles, and module-specific overrides.
- Gradle version catalogs, constraints, `resolutionStrategy.force`, and excludes.
- Shared test helper artifacts.
- Custom WireMock extensions and Groovy test runtime.
- Plugin classpath independent of the project dependency graph.

**Do not reflexively use `exclude`**: removing a transitive dependency can cause missing classes at runtime. Understand which library requires that class and replace it with a tested compatible version.

## 27. Multi-Module Builds: Inspect the Right Module

Example:

~~~text
platform/
├── pom.xml                   # parent BOM/pluginManagement
├── order-service/            # producer
├── checkout-service/         # consumer
└── shared-test-support/      # base test/helper
~~~

Risks:

- Root manages a new plugin, while the producer module overrides an old plugin.
- Shared helper is compiled on a higher Java version than the test JVM.
- Contract DSL resides in a different source root than the plugin config.
- Consumer module uses a Stub Runner line incompatible with its Boot/Cloud versions.
- CI runs only the aggregator/root build without running producer generated tests.
- Stub is published from the wrong module artifactId/version.

**Read the effective configuration at the producer module**. Do not draw conclusions from the root POM or another module.

| Check | Purpose |
| --- | --- |
| Parent/child effective POM | Find inherited/overridden versions at the module |
| Build reactor/module selection | Verify the producer module is tested |
| Shared test helper Java target | Can generated tests load the base class? |
| Contract source root | Does the plugin discover DSL in the right location? |
| Attached stub classifier | Which module publishes the JAR? |
| Stub Runner resolution | Which artifact does the consumer actually download? |

## 28. Local PASS but CI FAIL: Check the Environment

Common causes:

- Local uses a different JDK than CI.
- Global Maven/Gradle version differs from the wrapper.
- Build cache holds stale generated sources/plugins.
- CI applies different profiles/test exclusions.
- Repository mirror returns a different artifact/SNAPSHOT.
- Gradle daemon still uses stale configurations/caches.
- Different timezone/locale/charset affects fixtures.
- Stub Runner `LOCAL` uses an old JAR in the local Maven repository.
- Test container network/ports differ from the laptop.
- CI runs only a subset of tests due to module selection.

### Making Evidence Reproducible

- Use the wrapper committed in the repository.
- Lock Java toolchain and versions.
- Use immutable release artifacts or record checksums when SNAPSHOTs are unavoidable.
- Compare effective dependency/plugin versions.
- Record commit, contract revision, CI run ID, and test reports.
- Do not reuse a PASSing test status from a previous commit to validate a new commit.

### SNAPSHOTs Are Not Immutable

`2.5.0-SNAPSHOT` can have multiple builds with different bytes. Consumer PASS yesterday does not prove consumer PASS today, even with identical coordinates. Record the resolved artifact identity and SHA-256, then re-run or prove the actual artifact has not changed.

## 29. Stage-by-Stage Diagnostic Workflow

~~~mermaid
flowchart TD
    A["Build/test FAIL"] --> B{"Did plugin resolve?"}
    B -->|No| P["ID, version, repositories, wrapper"]
    B -->|Yes| C{"Did contract parse/generate tests?"}
    C -->|No| D["DSL syntax, plugin API, Groovy runtime"]
    C -->|Yes| E{"Did generated code compile?"}
    E -->|No| F["SCC plugin vs libs, JDK, JUnit, base class"]
    E -->|Yes| G{"Were tests executed?"}
    G -->|No| H["Goals/tasks, test source set, engine"]
    G -->|Yes| I{"Did producer contracts PASS?"}
    I -->|No| J["Distinguish tool mismatch from API mismatch"]
    I -->|Yes| K{"Is stub artifact valid?"}
    K -->|No| L["Mappings, packaging, contract revision"]
    K -->|Yes| M{"Did consumer Stub Runner + tests PASS?"}
    M -->|No| N["Stub GAV, WireMock, DTO, behavior"]
    M -->|Yes| O["Record evidence and evaluate release"]
~~~

A good rule of thumb:

1. Record the **first exception** and the stage where it occurred.
2. Gather actual versions: Boot, train, plugin, libraries, JDK/wrapper.
3. Read generated test/source/mapping files when relevant.
4. Check test reports instead of only the build summary.
5. Separate dependency binary linkage errors from contract semantic failures.
6. Fix only the appropriate layer, then run a clean build.
7. Re-run producer tests and consumer tests against the freshly verified artifact.

Do not run "upgrade all" without evidence; a bulk upgrade makes isolating the root cause much harder.

## 30. Symptom Table and Quick Triage

| Symptom | Primary hypothesis | Evidence to inspect |
| --- | --- | --- |
| Maven cannot find Contract plugin | Plugin version/repository | Effective POM, plugin resolution logs |
| Gradle reports `Plugin not found` | Plugin id/version/pluginManagement | Gradle wrapper, repositories |
| `UnsupportedClassVersionError` | Runtime JVM too old | JDK/toolchain and class file version |
| `javax.servlet`/`jakarta.servlet` error | Wrong framework/API generation | Boot/Framework/web dependencies |
| `NoSuchMethodError` | Binary dependency mismatch | Full stack trace, dependency tree |
| Groovy `MissingMethodException` | DSL/plugin incompatibility | Plugin release, syntax, classpath |
| Wrong generated source imports | Plugin and verifier libs misaligned | Generated test + resolved dependencies |
| 0 generated tests | Plugin goals/tasks or runner skipped | Test reports, plugin logs |
| JUnit tests not discovered | Test framework/engine mismatch | Generated imports, Surefire/Gradle Test |
| WebFlux test setup fails | Wrong MockMvc/WebTestClient mode | Base test, generated source |
| Stub Runner unmatched 404 | Wrong stub version/request matcher | Mappings, request journal, GAV |
| WireMock transformer fails to load | WireMock/extension API mismatch | Dependency version and extension logs |
| Consumer body parsing FAILS | JSON schema/serializer changed | Actual response/DTO and contract |
| Local PASS, CI FAIL | Different JDK/wrapper/profile/cache | CI environment/effective graph |
| Same SNAPSHOT, different bytes | Mutable artifact/repository | Resolved metadata and checksum |
| Producer PASS, consumer FAIL | API incompatibility or wrong stub runtime | Producer evidence + consumer tests |

One exception can have multiple causes; the table provides only a **starting hypothesis**, not a substitute for the stack trace.

## 31. Practice Exercises

### Exercise A — BOM and Maven Plugin

A producer imports `spring-cloud-dependencies` but does not lock the version of `spring-cloud-contract-maven-plugin`.

**Task:** explain why the BOM does not automatically manage the plugin version, and describe how to find the actual version.

**Hint:** `dependencyManagement` differs from `build.plugins/pluginManagement`. Inspect the effective POM and plugin logs.

### Exercise B — New Boot Minor, Old Cloud Train

A team upgrades the Boot minor version without changing the Cloud train; the project compiles cleanly.

**Task:** is this sufficient proof of support?

**Hint:** consult the official Boot–Cloud compatibility matrix and run tests against the real stack.

### Exercise C — Gradle Plugin Not Found

Gradle reports that `org.springframework.cloud.contract` at the specified version cannot be found.

**Task:** what should be checked before editing the DSL?

**Hint:** plugin id/version, `settings.pluginManagement`, repositories/mirror, Gradle wrapper.

### Exercise D — Generated Java Fails to Compile

Only the SCC Maven plugin was upgraded, after which generated tests import APIs missing from the classpath.

**Task:** list the versions that must be recorded for diagnosis.

**Hint:** plugin, resolved SCC Verifier, Boot, Cloud train, JDK, and test engine.

### Exercise E — Jakarta Migration

After upgrading the Boot generation, generated tests report that the old Servlet API cannot be found.

**Task:** what might this error be, and why should you not arbitrarily add a `javax.servlet` JAR?

**Hint:** check the Framework generation and Jakarta vs. Javax APIs in the web/test stack.

### Exercise F — Zero JUnit Tests

Generated tests use JUnit Jupiter, but the runtime only discovers JUnit 4.

**Task:** what needs to change in the test runner and release gate?

**Hint:** select the matching engine; fail the gate if required contracts produce 0 tests.

### Exercise G — WebFlux with MockMvc

Generated tests use RestAssuredWebTestClient, but the base class only sets up RestAssuredMockMvc.

**Task:** diagnose which layer is wrong.

**Hint:** test mode/base class wiring; do not rush to edit the response body.

### Exercise H — WireMock Extension Failure

Stub Runner starts, but a custom response transformer fails to load after a WireMock upgrade.

**Task:** which components must be aligned?

**Hint:** WireMock runtime, extension API, and Stub Runner dependencies.

### Exercise I — Different Producer/Consumer Boot Versions

Producer uses a new Boot version, consumer uses an old Boot version, and the JSON contract remains unchanged.

**Task:** must both services use the same Boot version?

**Hint:** runtime classpaths are independent, but consumer Stub Runner and API assertions must PASS.

### Exercise J — Artifact Version and Plugin Version

The SCC plugin has version `PLUGIN_X`, and the stub artifact is `order-service:2.5.0:stubs`.

**Task:** what do these two versions represent?

**Hint:** plugin tool version differs from application version; store both the contract revision and artifact checksum.

### Exercise K — Multi-Module

The parent POM imports a new Cloud BOM, but the producer module overrides an old Contract plugin.

**Task:** where should inspection commands run, and why is the root POM not enough?

**Hint:** effective POM at the producer module, generated test sources, and reports.

### Exercise L — Unstable SNAPSHOT

The consumer PASSED yesterday with `2.5.0-SNAPSHOT:stubs`, and today has the same coordinate but a different checksum.

**Task:** can the old report be reused for release?

**Hint:** no if the artifact identity differs; must re-test or provide proof of promoting the exact bytes.

### Exercise M — Security Override

A WireMock library is forced to a new major version due to an advisory, causing a linkage error in Stub Runner.

**Task:** how should this be handled safely?

**Hint:** check supported releases, evaluate upgrading the corresponding line, verify the security fix with regression tests, and do not ignore the advisory.

### Exercise N — Business Bug or Tooling Issue?

Generated producer test receives HTTP 200 but the `status` field is missing in the JSON body; JDK/plugin/JUnit all work properly.

**Task:** should you upgrade the plugin right away?

**Hint:** inspect producer serialization, contract semantics, and consumer expectations first.

## 32. Version Alignment Checklist Before Merge/Release

### Stack Selection

- [ ] Aligned Boot version and Cloud train from the **official support table** for the active line.
- [ ] Contract libraries are intentionally managed via the Cloud BOM or verified dependency management.
- [ ] Maven/Gradle Contract plugin version is selected **separately**, not assumed to be managed by the BOM.
- [ ] Boot version is not used as the Contract plugin version.
- [ ] Release notes for Boot/Cloud/SCC have been reviewed for major/minor changes.
- [ ] JDK and Maven/Gradle wrapper meet the stack's requirements.
- [ ] No unreviewed dependency overrides/conflicts exist.

### Producer Verification

- [ ] Contract DSL is discovered at the right source root/revision.
- [ ] Generated tests are produced and source files inspected when needed.
- [ ] JUnit/test engine matches the framework generated by the tool.
- [ ] Base test class, lifecycle annotations, and test mode match the MVC/WebFlux/message stack.
- [ ] Producer tests actually execute and PASS, not 0 tests.
- [ ] Matchers have not been relaxed merely to cover up toolchain errors.
- [ ] Reports record producer commit, contract revision, and build ID.

### Stubs and Consumer

- [ ] Stub JAR contains mappings/response files per the contract.
- [ ] Artifact GAV/classifier/version/checksum are accurate.
- [ ] Stub Runner and WireMock runtime can read the artifact format/extensions.
- [ ] Consumer Stub Runner test classpath matches **the consumer's Boot/Cloud**, not assumed to match the producer.
- [ ] Consumer tests download the new stub, not a stale cache or old SNAPSHOT.
- [ ] Consumer assertions verify business behavior, not just that the stub server started.
- [ ] Still-supported consumer versions have been verified in the actual matrix.

### CI and Decisions

- [ ] CI uses a wrapper/toolchain with explicitly recorded versions.
- [ ] Declared and resolved dependency/plugin versions have been compared.
- [ ] Historical test results are not reused for an artifact with a different checksum.
- [ ] When upgrading the plugin, generation, producer verification, and consumer Stub Runner have all been tested.
- [ ] A rollback/migration plan exists if needed.
- [ ] Compatibility is declared **only within the scope of tested scenarios/versions**.
- [ ] Untested matrix cells are marked `NOT_RUN`/`BLOCKED`, never assumed PASS.

## Conclusion

**Aligning Spring Boot, Spring Cloud Contract, and plugin versions** is a matter of managing a **coordinated set of versions**, not tweaking a single dependency. The Spring Cloud release train manages Spring Cloud dependencies compatible with Spring Boot, yet **the BOM does not automatically lock the build plugin version**. Alongside that, the JDK, Maven/Gradle wrapper, Groovy, JUnit, test mode, WireMock, and Stub Runner must also be compatible within the build environment and consumer tests.

A combination is only qualified for use when resolved versions are verified, **generated producer contract tests actually run**, the stub artifact from the right source is published, and the consumer uses that exact stub to verify behavior. Only then can CI distinguish **tooling errors** from **breaking API changes**.

**Remember:** *Choose a documented supported version set; check the plugin separately from the BOM; inspect generated tests and the resolved dependency graph; never call a release compatible if producer or consumer contract tests have not run against the right artifact.*
