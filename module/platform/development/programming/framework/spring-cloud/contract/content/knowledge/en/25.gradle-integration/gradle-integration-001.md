# Applying the Spring Cloud Contract Plugin and Declaring Dependencies

A project using **Gradle** cannot simply place contract files in `src/test/resources/contracts` and expect them to turn into tests automatically. The **Spring Cloud Contract Gradle Plugin** must be applied to the build; the test dependencies must be present on the classpath; and the test framework, test mode, and base test must be compatible with the producer. When these steps are configured properly, Gradle can **generate producer verification tests** from the Groovy/YAML DSL, run them, and create the **stubs** artifact for consumers to test against via **Stub Runner**.

This lesson belongs to the **Gradle Integration** chapter of the **SPRING_CLOUD_CONTRACT** module. The learning scope covers contract testing between producer and consumer, describing HTTP or messaging interactions using Groovy/YAML DSL, producer verification, stub packaging, and CI integration to detect incompatible APIs. The focus of this lesson is **applying the plugin and declaring dependencies in Gradle**, while explaining how the build configuration connects to the steps that actually happen afterward.

The examples use **Gradle Groovy DSL** (`build.gradle`) as the primary flow; `build.gradle.kts` is introduced separately. The versions shown in the examples are **an intentional illustrative set**, not the latest or default versions for every project. When adopting this in a real system, you must choose compatible **Spring Boot, Spring Cloud release train, Spring Cloud Contract, Gradle, and Java** versions according to the documentation for your project's version set.

## 1. What Does the Gradle Plugin Solve?

**Contract Verifier** and **Stub Runner** have different responsibilities:

| Component | Where does it live? | Primary responsibility |
| --- | --- | --- |
| **Spring Cloud Contract Gradle Plugin** | **Producer** build | Discovers contracts, generates test sources, generates stub resources, and provides the corresponding Gradle tasks. |
| **spring-cloud-starter-contract-verifier** | Producer `testImplementation` | Provides the libraries needed to run the generated contract tests. |
| **Base test** | `src/test/java` or an appropriate test source set | Prepares the Spring context, MockMvc/WebTestClient, fixtures, and initial state. |
| **spring-cloud-starter-contract-stub-runner** | **Consumer** `testImplementation` | Downloads and starts stubs, providing APIs/annotations for consumer tests. |
| **Maven/Artifact repository** | Distribution infrastructure | Stores the `stubs`-classifier JAR by group/artifact/version. |
| **Groovy/YAML contracts** | Usually in the producer's test resources | Specifies HTTP request/response or observable message contracts. |

One way to view the lifecycle:

~~~mermaid
flowchart TD
    A["Producer: Groovy/YAML contracts"] --> B["Gradle Spring Cloud Contract Plugin"]
    B --> C["Generate producer tests"]
    B --> D["Generate resources/mappings for stubs"]
    C --> E["Gradle test task runs against real producer"]
    E --> F{"Producer verification passes?"}
    F -->|No| G["Block release"]
    F -->|Yes| H["Package stubs-classifier JAR"]
    D --> H
    H --> I["Publish Maven artifact"]
    I --> J["Consumer Gradle test + Stub Runner"]
    J --> K["Test real HTTP client or message listener"]
~~~

**The producer's plugin does not replace `spring-cloud-starter-contract-stub-runner` on the consumer side.** Conversely, merely adding the Contract Verifier dependency to the producer **without applying the plugin** may not generate any tests at all. Both the **generation phase** and the **execution phase** are required.

## 2. Defining a Compatible Version Set Upfront

Suppose the hands-on exercise uses:

| Tool | Example value | Role |
| --- | --- | --- |
| Java | 17 | Language/runtime for the illustrative Spring Boot 3.x application. |
| Gradle | Version supported by the Gradle Wrapper and Spring Boot plugin | Runs builds, plugins, and test tasks. |
| Spring Boot | 3.3.x | Producer/consumer framework. |
| Spring Cloud release train | 2023.0.x | Manages Spring Cloud dependency versions. |
| Spring Cloud Contract Gradle Plugin | 4.1.x | Generates tests and stub resources matching the appropriate Spring Cloud set. |
| JUnit | JUnit Jupiter | Runs generated tests when `JUNIT5` is selected. |
| Producer HTTP stack | Spring MVC | Example uses `MOCKMVC`. |

**This table illustrates one version family, not a guarantee that every arbitrary patch version in these lines is compatible.** The team must check the release train and compatibility matrix for the exact versions chosen. When upgrading Spring Boot, you typically need to re-evaluate the Gradle Wrapper, Spring Cloud BOM, Spring Cloud Contract plugin, starters, and base tests.

Rules to remember:

1. The **plugin version** in `plugins` is the build plugin's version; it **does not automatically replace all dependency version management** on `testImplementation`.
2. The **Spring Cloud BOM** helps manage Spring Cloud dependencies in the project; it **does not necessarily manage the version of the plugin** downloaded by Gradle during plugin resolution.
3. The **Gradle Wrapper** (`./gradlew`, `gradlew.bat`) determines the build's Gradle runtime. Use the wrapper verified by the project and avoid relying on a pre-installed Gradle on each machine.
4. The **Java toolchain** helps Gradle select the expected JDK for compiling/running; if CI lacks the JDK or cannot download the toolchain, the build can still fail.

## 3. Producer Project Structure with Gradle

Example Order Service:

~~~text
order-service/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
├── src/
│   ├── main/
│   │   └── java/com/acme/orders/
│   │       ├── OrderApplication.java
│   │       └── OrderController.java
│   └── test/
│       ├── java/com/acme/orders/
│       │   └── ContractTestBase.java
│       └── resources/
│           └── contracts/
│               └── orders/
│                   └── get_paid_order.groovy
└── build/
    └── ... generated test sources, mappings, reports, and artifacts
~~~

`build/` is output generated by Gradle, **not a place to manually edit generated tests**. The assets that must be managed in source control are **contracts, base tests, plugin/dependency configuration, and the producer implementation**.

The `settings.gradle` file can declare repositories for Gradle to resolve plugins:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = 'order-service'
~~~

`pluginManagement.repositories` is used when Gradle **resolves build plugins**, whereas `repositories` in `build.gradle` is used when the project **resolves application/test libraries**. The two scopes should not be confused. In enterprises with internal mirrors/repositories, public repositories can be replaced with approved sources.

## 4. Applying the Plugin in `build.gradle`

A Groovy DSL example for a Spring MVC producer:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
    id 'org.springframework.cloud.contract' version '4.1.5'
    id 'maven-publish'
}

group = 'com.acme'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

ext {
    springCloudVersion = '2023.0.4'
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
    baseClassForTests = 'com.acme.orders.ContractTestBase'
    testFramework = 'JUNIT5'
    testMode = 'MOCKMVC'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Example scope:** the version numbers in `plugins` and `springCloudVersion` only illustrate how to declare them. If your project is on a different release train, choose a compatible set instead of pairing `4.1.5` with a newer Spring Boot without checking. The snippet above also does not yet include the controller, base test, contract, or `stubs` artifact publishing configuration; those parts are built below.

### 4.1. Understanding Each Block

| Block or line | Meaning |
| --- | --- |
| `id 'java'` | Adds Java tasks, source sets, compilation, and testing. |
| `id 'org.springframework.boot'` | Integrates the Spring Boot build. |
| `id 'io.spring.dependency-management'` | Allows importing a Maven BOM via the `dependencyManagement` block in the example. |
| `id 'org.springframework.cloud.contract'` | Applies the **Spring Cloud Contract Gradle Plugin** to the producer. |
| `id 'maven-publish'` | Allows creating a Maven publication to publish artifacts. |
| `group` and `version` | Part of the Maven coordinates for the artifact and stub. |
| `java.toolchain` | Requests a Java 17 environment for the example. |
| `repositories { mavenCentral() }` | Specifies where to look up application/test dependencies. |
| `springCloudVersion` + `mavenBom` | Aligns Spring Cloud libraries to the chosen release train. |
| `testImplementation '...contract-verifier'` | Places the verification libraries on the producer's **test classpath**. |
| `contracts { ... }` | Instructs the plugin to generate tests with the chosen base class, framework, and mode. |
| `useJUnitPlatform()` | Enables the Gradle `test` task to discover and run JUnit Jupiter tests. |

**Do not confuse Maven configuration style:** Maven uses `spring-cloud-contract-maven-plugin` in `pom.xml`. With Gradle, you must apply **`org.springframework.cloud.contract`** in `plugins`; do not copy Maven `<plugin>` tags directly into `build.gradle`.

## 5. Why Do You Need Both the Plugin and the Verifier Dependency?

The two parts have complementary responsibilities:

~~~groovy
plugins {
    id 'org.springframework.cloud.contract' version '4.1.5'
}

dependencies {
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}
~~~

- The **Gradle Plugin** participates in the build process, **reads contracts**, and **generates test/stub resources**.
- The **Verifier starter** provides the libraries so that **the generated test code can compile and execute** in the producer project.

That does not mean the plugin and starter can use **any two arbitrary versions**. Manage dependencies via a BOM compatible with the plugin version. If you see `NoClassDefFoundError`, `NoSuchMethodError`, or generated tests with nonexistent imports, check **the plugin, BOM, starter, Spring Boot**, and the Gradle runtime together.

### 5.1. Differences Between `implementation` and `testImplementation`

| Gradle configuration | Example | When to use |
| --- | --- | --- |
| `implementation` | `spring-boot-starter-web` | Libraries needed by the producer application at runtime. |
| `testImplementation` | `spring-boot-starter-test`, `spring-cloud-starter-contract-verifier` | Libraries needed to compile and run tests. |
| `testRuntimeOnly` | Test engine or runtime provider in combinations that require separate declaration | Needed at test runtime but not for test compilation. |
| `runtimeOnly` | Application JDBC driver or architecture-specific runtime component | Not needed to compile the application. |

**Do not put the Contract Verifier starter in `implementation` just to fix a test compile error**, because doing so can pull testing dependencies into the production runtime artifact. Look for the cause of missing classes in the **test configuration** first.

When using the Gradle Java plugin, `testImplementation` belongs to the default test source set's dependency graph. If you organize a **custom test source set**, you need to configure the corresponding dependencies and tasks; do not assume generated tests automatically move to the custom source set.

## 6. Configuring the `contracts` Extension: Base Test, Framework, Mode

A key plugin configuration block:

~~~groovy
contracts {
    baseClassForTests = 'com.acme.orders.ContractTestBase'
    testFramework = 'JUNIT5'
    testMode = 'MOCKMVC'
}
~~~

Three distinct choices:

| Property | Example | What it decides |
| --- | --- | --- |
| `baseClassForTests` | `com.acme.orders.ContractTestBase` | The class that generated producer tests extend, preparing fixtures and the HTTP test client. |
| `testFramework` | `JUNIT5` | The framework/syntax of the generated tests. |
| `testMode` | `MOCKMVC` | How generated tests invoke the producer's HTTP layer. |

Common modes:

- **`MOCKMVC`** for **Spring MVC**, using MockMvc through the Spring Test context without opening a real HTTP socket.
- **`WEBTESTCLIENT`** for **Spring WebFlux** when the plugin version supports the configured stack/client.
- **`EXPLICIT`** when generated tests need to call a **real HTTP server** via a host and port started in the test.
- Some versions/integrations may provide **`JAXRSCLIENT`** for JAX-RS; select it only if it fits your actual framework and plugin.

**Using Groovy DSL for contracts does not force generated tests to use Groovy/Spock.** A `.groovy` file can still generate Java JUnit 5 tests. Conversely, switching `testFramework` to Spock requires an appropriate Groovy/Spock toolchain and test discovery setup; do not simply change one string and expect Gradle to already be configured.

## 7. Writing a Sample HTTP Contract in Groovy DSL

Place at `src/test/resources/contracts/orders/get_paid_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Order Service returns paid order status'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID'
        )
    }
}
~~~

This contract specifies:

1. The request is `GET /api/orders/42` with header `Accept: application/json`.
2. The response has HTTP `200` and a JSON Content-Type.
3. The response body has `id=42` and `status=PAID`.

**There is no Gradle, Maven, MockMvc, Stub Runner, Java class, or port inside the contract.** It describes the HTTP interaction; the plugin and base test decide how the real producer is verified.

### 7.1. If Your Team Uses YAML DSL

A standalone YAML file, for example `get_paid_order.yml`:

~~~yaml
description: Order Service returns paid order status
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

**Choose only one of the Groovy or YAML files as the active contract source** for the same scenario in a single build. If both are loaded by the plugin at the same time, duplicate generated tests or mappings may be produced, causing confusion when modifying the contract.

## 8. Base Test for a Spring MVC Producer

Suppose Order Service has the endpoint:

~~~java
package com.acme.orders;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public OrderView getOrder(@PathVariable long id) {
        if (id != 42L) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.NOT_FOUND
            );
        }
        return new OrderView(42L, "PAID");
    }

    public record OrderView(long id, String status) {}
}
~~~

And the application has a `@SpringBootApplication` class named `com.acme.orders.OrderApplication`.

Create `src/test/java/com/acme/orders/ContractTestBase.java`:

~~~java
package com.acme.orders;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = OrderApplication.class)
@AutoConfigureMockMvc
public abstract class ContractTestBase {

    @Autowired
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

In this example, `MOCKMVC` needs a `MockMvc` configured by Spring Test; `RestAssuredMockMvc.mockMvc(mockMvc)` connects the test client to the Spring MVC handlers. If an endpoint depends on a database, authentication, or external services, **the base test must also prepare fixtures and initial state**; the hardcoded order 42 example is only to keep the focus on Gradle configuration.

If the plugin cannot find the base class or generated tests call an unconfigured client, check **the `baseClassForTests` value, package, test framework, and the actual generated test code**. Do not edit generated tests directly because the next build will overwrite them.

## 9. Gradle Tasks to Know

After the plugin is applied, the commonly involved tasks include:

| Common task | Role |
| --- | --- |
| `generateContractTests` | Reads contracts and generates producer test sources. |
| `generateClientStubs` | Generates stub resources from contracts. |
| `test` | Runs the Java project's test task, including generated tests if plugin wiring is correct. |
| `check` | Runs verification tasks attached to the testing lifecycle. |
| `build` | Builds the project, including checks/tests and packaging according to the Gradle configuration. |
| `verifierStubsJar` | Packages the `stubs`-classifier stub artifact in plugin versions that provide this task. |
| `publishToMavenLocal`, `publish` | Publishes configured Maven publications; does not automatically publish every artifact unless declared. |

**Task names and the task graph may vary by plugin version and configuration.** To inspect your actual environment, you can run in the producer project:

~~~shell
./gradlew tasks --all
./gradlew help --task generateContractTests
./gradlew help --task verifierStubsJar
~~~

On Windows PowerShell or Command Prompt:

~~~powershell
.\gradlew.bat tasks --all
.\gradlew.bat test
~~~

The commands in this lesson are **instructions for the learner to practice**, not commands that were executed while authoring this lesson.

### 9.1. Verifying the Path from Test Generation to Test Execution

A reference run:

~~~shell
./gradlew clean test
~~~

Outcomes to verify:

- The `get_paid_order.groovy` file was **discovered and parsed** by the plugin.
- The generated producer test class exists in Gradle's **generated test sources** (usually under `build/`, exact path depends on the plugin).
- The generated test properly extends `ContractTestBase`.
- The Gradle `test` task executes that **JUnit Jupiter** test; the report shows test count > 0.
- The response from the real producer is verified for `status=200`, Content-Type, and JSON.
- If you intentionally change the controller's `status` from `PAID` to `PENDING`, the test must **FAIL**.

**A single `BUILD SUCCESSFUL` line is not enough.** Tests might have been skipped, the `test` task might have received 0 tests, contracts might be in the wrong directory, or generated source sets might not be wired into the Gradle test task. To verify, inspect the `build/reports/tests/test/` report if the default configuration writes reports there, along with the logs of `generateContractTests` and `test`.

## 10. Generating the `stubs` JAR and Understanding Artifact Coordinates

The consumer needs to download the exact set of stubs verified by the producer. For the example:

~~~text
group       = com.acme
artifactId  = order-service
version     = 1.0.0
classifier  = stubs
~~~

Coordinates commonly used with Stub Runner:

~~~text
com.acme:order-service:1.0.0:stubs
~~~

A JAR generated by Gradle might be named:

~~~text
order-service-1.0.0-stubs.jar
~~~

**Distinguishing the application JAR from the stub JAR**:

- The application JAR contains the producer's runtime code.
- The `stubs` JAR contains HTTP mappings, contracts, and data needed by Stub Runner depending on the contract type and plugin.
- The `stubs` JAR **does not replace** a running Spring Boot application.

HTTP stub builds usually contain WireMock mapping data; messaging contracts require contract resources and corresponding messaging integration. **Do not simply count mapping files** and conclude that a messaging-only stub is missing data.

### 10.1. Declaring a Publication for the Stub Artifact

When `maven-publish` is applied, you can add a publication in `build.gradle`:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifact(tasks.named('verifierStubsJar'))
        }
    }
}
~~~

This snippet **depends on the `verifierStubsJar` task actually existing in the plugin version in use**. Run `./gradlew tasks --all` first to check. The Jar task needs the `stubs` classifier so the artifact coordinates requested by the consumer match the published artifact. Some plugin versions/configurations may already set up the artifact/publication automatically or provide their own publishing mechanism; do not declare the same classifier **twice** and cause duplicate artifacts in the publication.

After configuring the publication, you can try:

~~~shell
./gradlew clean build
./gradlew publishToMavenLocal
~~~

**Do not assume `publishToMavenLocal` automatically forces `test` to run in every configuration.** For reliable CI, establish explicit job ordering or task dependencies so publishing only happens **after producer verification passes**. To publish to a private repository, declare `publishing.repositories` and use `./gradlew publish` in a workflow with appropriate authentication.

## 11. Gradle `maven-publish` Does Not Mean Stub Runner Can Already Download the JAR

Two independent steps:

1. The **producer** must publish the right JAR with `groupId`, `artifactId`, `version`, and classifier `stubs`.
2. The **consumer** must have access to that repository and request the exact matching coordinates.

Example consumer running with the local repository after `publishToMavenLocal`:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

For CI using a remote repository:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/maven-releases"
)
~~~

The repository URL is **illustrative only**. `REMOTE` means **downloading the artifact from a Maven repository**, not that the consumer HTTP client sends requests to the repository URL. After downloading, Stub Runner can start WireMock on a **dynamic port**, and the consumer test looks up the URL via `StubFinder`.

**Check group and artifact names:** if `settings.gradle` sets a project name different from the `artifactId` requested by Stub Runner, or if the publication alters the artifact name, the consumer may fail to find the stubs even though the producer built successfully.

## 12. Consumer-Side Dependency: Stub Runner, Not the Verifier Plugin

In the **Billing Service** (consumer) repository, you normally **do not need to apply the Spring Cloud Contract Gradle Plugin** just to run tests against stubs published by Order Service. The consumer needs the **Stub Runner starter in test scope**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

repositories {
    mavenCentral()
}

ext {
    springCloudVersion = '2023.0.4'
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Key differences:**

- The producer uses the **`org.springframework.cloud.contract` Gradle Plugin** and **`spring-cloud-starter-contract-verifier`** to **generate, run tests, and export stubs**.
- The consumer uses **`spring-cloud-starter-contract-stub-runner`** to **load stubs and execute real client code** in tests.
- Both must choose **dependency versions compatible with their respective Spring Boot and Spring Cloud BOMs**. The producer and consumer do not have to share the exact same application version number, but the stub artifact the consumer loads must match the contract it relies on.

If a consumer is also a producer for another service, the same repository may need **both** kinds of integration, while keeping each dependency's purpose and scope clear.

## 13. Simple Consumer Test with Stub Runner

A Spring RestClient HTTP client class in Billing:

~~~java
package com.acme.billing;

import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient client;

    public OrderClient(String baseUrl) {
        this.client = RestClient.create(baseUrl);
    }

    public OrderDto getOrder(long id) {
        return client.get()
            .uri("/api/orders/{id}", id)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(long id, String status) {}
}
~~~

Consumer JUnit 5 test:

~~~java
package com.acme.billing;

import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {

    @Autowired
    StubFinder stubFinder;

    @Test
    void readsPaidOrderThroughStub() {
        URL url = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub was not started"
        );

        OrderClient orderClient = new OrderClient(url.toExternalForm());
        OrderClient.OrderDto order = orderClient.getOrder(42L);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
    }
}
~~~

**Why retrieve the URL dynamically?** Stub Runner can automatically pick a free port; avoid hardcoding `localhost:8089` when CI runs multiple jobs in parallel. `StubFinder` here returns the address of the **running HTTP stub**, not the JAR path or Maven repository.

The example exercises the **real OrderClient code** and the published JSON/HTTP contract. However, a green consumer test against a stub **does not by itself prove the real producer adheres to the contract**; that guarantee is enforced by producer verification running in the Order Service build.

## 14. How Do Gradle Groovy DSL and Kotlin DSL Differ?

The two Gradle file formats cannot be copied character-for-character:

| Element | Groovy DSL: `build.gradle` | Kotlin DSL: `build.gradle.kts` |
| --- | --- | --- |
| Plugin | `id 'org.springframework.cloud.contract' version '4.1.5'` | `id("org.springframework.cloud.contract") version "4.1.5"` |
| Test dependency | `testImplementation 'group:artifact'` | `testImplementation("group:artifact")` |
| Repository | `mavenCentral()` | `mavenCentral()` |
| JUnit test task | `tasks.named('test') { useJUnitPlatform() }` | `tasks.test { useJUnitPlatform() }` |
| BOM with Gradle platform | `implementation platform('group:bom:version')` | `implementation(platform("group:bom:version"))` |

An illustrative Kotlin DSL starter:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.6"
    id("io.spring.dependency-management") version "1.1.6"
    id("org.springframework.cloud.contract") version "4.1.5"
    id("maven-publish")
}

group = "com.acme"
version = "1.0.0"

repositories {
    mavenCentral()
}

extra["springCloudVersion"] = "2023.0.4"

dependencyManagement {
    imports {
        mavenBom(
            "org.springframework.cloud:spring-cloud-dependencies:" +
                extra["springCloudVersion"]
        )
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.cloud:spring-cloud-starter-contract-verifier")
}

tasks.test {
    useJUnitPlatform()
}
~~~

**The snippet above illustrates Kotlin syntax for plugins/dependencies/test tasks.** Writing `contracts { ... }` in Kotlin DSL depends on how the plugin exposes its extension and property types in the version being used. Check the extension API recognized by your IDE/Gradle, rather than copying Groovy's `baseClassForTests = '...'` into Kotlin without adjusting syntax and types.

If you want to avoid the dependency-management plugin, Gradle also supports **`platform(...)`** to import a BOM. Choose **one clear version management strategy** and avoid importing the same BOM through multiple mechanisms with conflicting versions, which makes the dependency graph hard to reason about.

## 15. Can You Use Gradle Native BOM Instead of the Dependency-Management Plugin?

In some projects, teams choose native Gradle `platform(...)` to declare the BOM instead of `io.spring.dependency-management`:

~~~groovy
dependencies {
    implementation platform(
        'org.springframework.cloud:spring-cloud-dependencies:2023.0.4'
    )
    testImplementation platform(
        'org.springframework.cloud:spring-cloud-dependencies:2023.0.4'
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}
~~~

**Note:** if you omit the dependency-management plugin, you must define how **Spring Boot starter versions** and other dependencies are managed. In some setups, the Spring Boot Gradle Plugin works alongside the dependency-management plugin to apply the Spring Boot BOM by the convention many projects expect. With a native Gradle platform, you must also import the appropriate BOM or specify matching versions explicitly.

Both version management approaches can be valid. The goal is not "which one is shorter", but that:

1. Every `spring-cloud-*` dependency has a version **matching the release train**.
2. The Spring Cloud Contract Gradle plugin has a version **compatible** with the contract/verifier dependencies.
3. The Gradle dependency graph does not contain two conflicting versions of the same library.
4. Both the project and CI use the same Gradle Wrapper/lockfile/version catalog when available.

If a dependency conflict occurs, inspect the dependency graph of the exact configuration rather than just reading a single `testImplementation` line:

~~~shell
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-contract-verifier --configuration testRuntimeClasspath
~~~

These are commands **learners can run to investigate**; this lesson does not execute Gradle on behalf of the project.

## 16. Messaging Contracts: Different Dependencies and Test Setup

Spring Cloud Contract does not verify only HTTP. For an `OrderCreated` event, the producer might publish a message to `orders.created`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'

    input {
        triggeredBy('publishOrderCreated()')
    }

    outputMessage {
        sentTo('orders.created')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'OrderCreated')
        }
        body(
            eventId: 'evt-00042',
            orderId: 'ORD-1042'
        )
    }
}
~~~

In Gradle, beyond the Contract Verifier starter, the application **needs the actual messaging dependencies** it uses (such as Spring Cloud Stream and the appropriate binder). The generated test requires a **base test trigger method** named `publishOrderCreated()` and a **messaging adapter/MessageVerifier/test binder** to observe output.

**Do not select `testMode=MOCKMVC` and treat that as a complete messaging verification setup.** `MOCKMVC` only relates to HTTP requests on Spring MVC; message contracts require a test environment with appropriate send/receive channels.

When packaging the `stubs` artifact, messaging contracts can be used by Stub Runner to emit **sample messages** via a `label` and messaging integration. The consumer does not necessarily use an HTTP port for that scenario. In CI, verify **serialization/wire metadata** separately when the consumer relies on JSON bytes, Avro/Protobuf, or broker header mapping.

## 17. Multi-Module Gradle: Where to Apply the Plugin?

A Gradle repository might look like:

~~~text
commerce-platform/
├── settings.gradle
├── build.gradle
├── order-service/
│   └── build.gradle
├── inventory-service/
│   └── build.gradle
└── checkout-service/
    └── build.gradle
~~~

**Do not apply the Contract Verifier plugin to every module just because they live in the same repository.** Identify the roles:

| Module | Role | Required configuration |
| --- | --- | --- |
| `order-service` | Order API Producer | Contract Verifier plugin + verifier test dependency + contracts/base test. |
| `inventory-service` | Inventory API Producer | Contract Verifier plugin + verifier test dependency + contracts/base test. |
| `checkout-service` | Consumer of both producers | Stub Runner test dependency + two stub artifacts; Verifier plugin is only needed if it is also a producer. |

If using the root `build.gradle` to manage plugin versions, you can declare the plugin with `apply false` and then apply it to **subprojects that are actually producers**. For example:

~~~groovy
// Root build.gradle: only declares the plugin version.
plugins {
    id 'org.springframework.cloud.contract' version '4.1.5' apply false
}
~~~

And in `order-service/build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.cloud.contract'
}
~~~

This is a **multi-module build fragment**, not a complete module configuration. Gradle plugin resolution, `group`/`version`, BOM, dependencies, and publication are still required in the appropriate scopes. If the root build pins the version but a subproject omits applying the plugin, no contract tasks will be generated for that producer.

**Each producer should publish its `stubs` JAR under its own coordinates.** A multi-producer consumer needs to load both artifacts by their exact group/artifact/version; do not arbitrarily merge mappings from multiple services into a single JAR and lose contract ownership.

## 18. CI Integration: build → verify → publish → consumer test

~~~mermaid
flowchart TD
    A["Producer commit changes API/contract"] --> B["Gradle resolves plugins + dependencies"]
    B --> C["generateContractTests / generateClientStubs"]
    C --> D["./gradlew clean test"]
    D --> E{"Generated producer tests ran and passed?"}
    E -->|No| F["Block artifact publication"]
    E -->|Yes| G["verifierStubsJar + Maven publication"]
    G --> H["Publish stubs with version"]
    H --> I["Consumer Gradle test + Stub Runner"]
    I --> J["Run real client code against stub"]
    J --> K["Verify response, request mapping, compatibility"]
~~~

A minimal producer pipeline should:

1. Use the **Gradle Wrapper** and a Java toolchain configured/available on the runner.
2. Resolve plugins/dependencies from accessible repositories and verify version compatibility.
3. Run **generated producer tests** with the appropriate JUnit/Spock engine.
4. Confirm **the number of executed tests**, rather than only checking for exit code 0 from the build command.
5. If verification **FAILS**, stop the publish step.
6. If verification **PASSES**, build/inspect the `stubs`-classifier JAR and publish it with the right coordinates.
7. Consumer CI **downloads the exact stub version** and runs consumer tests through Stub Runner.

For the Gradle producer, the test command is typically:

~~~shell
./gradlew clean test
~~~

For the Gradle consumer:

~~~shell
./gradlew test
~~~

**Do not impose Maven habits on Gradle:** `mvn verify`, `mvn install`, and `./gradlew test` belong to two different lifecycles. `./gradlew publishToMavenLocal` only publishes declared publications; it is not a substitute for generating and running producer contract tests.

### 18.1. Verifying the Published Artifact

After publishing, you need to prove that:

- The stub file actually has the **`stubs` classifier**, not just the application JAR.
- The artifact's Maven coordinates match `ids` in `@AutoConfigureStubRunner`.
- The contents include HTTP mappings or messaging contracts according to the chosen contract type.
- Those resources came from the **exact commit/version verified by the producer**.
- Consumer tests load the artifact from `LOCAL` or `REMOTE` at the right location, not from stale leftover build files.

Do not assume Gradle publishes stubs by default simply because `maven-publish` is applied; verify `publishing.publications` and the actual publishing logs and coordinates.

## 19. Common Errors When Integrating Gradle

| Symptom | Possible cause | How to investigate/fix |
| --- | --- | --- |
| `Plugin [id: 'org.springframework.cloud.contract'] was not found` | Missing version or plugin repository, or plugin version is unavailable in declared sources. | Check `plugins`, `pluginManagement.repositories`, access permissions, and supported versions. |
| Gradle reports `contracts` extension does not exist. | The plugin has not been applied to the module being configured. | Check `plugins` in the right subproject, not just `apply false` in the root. |
| `generateContractTests` is missing. | Plugin not applied, wrong module, or plugin version uses a different task name. | Run `./gradlew tasks --all` in the right project and check plugin resolution. |
| `build` is green but no generated tests exist. | Contracts are in the wrong directory, generator/task is not wired to test, or tests were skipped. | Check contract paths, generated sources, test reports, and the task graph. |
| Java tests do not run with `JUNIT5`. | Missing JUnit Platform engine/configuration. | Check `useJUnitPlatform()`, test dependencies, and the Gradle test report. |
| Generated test cannot find base class. | `baseClassForTests` has the wrong package or base test is not in the test source set. | Compare the exact class name, compiled test classes, and generated test imports. |
| MockMvc test fails due to uninitialized HTTP client. | Base test is missing `RestAssuredMockMvc.mockMvc(mockMvc)` or Spring test context. | Check `@AutoConfigureMockMvc`, `@BeforeEach`, and `testMode`. |
| `NoSuchMethodError` or `NoClassDefFoundError`. | BOM, Contract Plugin, Verifier starter, or Spring Boot are incompatible. | Check the dependency graph and release train; do not fix with arbitrary versions. |
| `verifierStubsJar` is missing. | Task name differs by version, plugin is missing, or packaging is not configured. | Check `tasks --all` and the stub packaging mechanism of the plugin in use. |
| `publishToMavenLocal` runs but consumer cannot find stub. | `stubs` classifier not published, wrong group/artifact/version, or different Maven local environment. | Check the Maven publication, artifact metadata, and Stub Runner `ids`. |
| Consumer reports WireMock 404 even though stub loaded. | Request does not match mapping, wrong base URL, or mappings belong to another version. | Inspect stub mappings and the request journal; distinguish no-match from business 404. |
| CI stays green even when producer changes a contract-breaking field. | Generated tests did not run or assertions are too loose. | Intentionally change a field, check the report, and fix the contract/setup. |
| When running multiple jobs, the WireMock port is already in use. | Consumer hardcodes port `8089`. | Use Stub Runner's dynamic port and look up the URL with `StubFinder`. |
| Groovy contract exists but unexpectedly generates Spock tests. | `testFramework` or Gradle test toolchain mismatch. | Cross-check the `contracts` extension, test engine, and generated source type. |

**Diagnose along the chain:** plugin loaded → dependencies resolved → contracts discovered → generated sources exist → base test runs → producer verification executes → stub JAR generated → published with matching coordinates → consumer Stub Runner downloads and runs.

## 20. Hands-On Exercise: From Gradle Plugin to Consumer Test

Execute on two independent Spring Boot projects (`order-service` and `billing-service`):

1. **Prepare the Gradle Wrapper**, appropriate JDK, repositories, and compatible Spring Boot/Spring Cloud/Spring Cloud Contract versions.
2. **Apply `org.springframework.cloud.contract`** to producer `order-service/build.gradle`, declaring `java`, Spring Boot, BOM, and `testImplementation spring-cloud-starter-contract-verifier`.
3. **Configure `contracts`** with `baseClassForTests`, `testFramework=JUNIT5`, and `testMode=MOCKMVC`.
4. **Write a Groovy contract** for `GET /api/orders/42`, status 200, and JSON `PAID`; you may test an equivalent YAML file, but keep only one DSL active per build.
5. **Create the controller and ContractTestBase**, verifying MockMvc wiring and fixtures before generated tests send requests.
6. **Inspect the task graph** with `./gradlew tasks --all`, then run `./gradlew clean test`; confirm the generated test actually runs and PASSES.
7. **Introduce an intentional breaking change**: change the response `status=PAID` to `status=PENDING` in the controller without changing the contract. Re-run and verify the test **FAILS**; revert it.
8. **Package the stubs artifact**, inspect the `verifierStubsJar` task/packaging mechanism for your plugin version, and configure `maven-publish` if needed.
9. **Publish stubs to Maven local** with `./gradlew publishToMavenLocal` after verification passes; check coordinates `com.acme:order-service:1.0.0:stubs`.
10. **In the Billing consumer**, add `testImplementation spring-cloud-starter-contract-stub-runner`, configure the BOM and JUnit Platform.
11. **Write the real OrderClient**, use `@AutoConfigureStubRunner` with `LOCAL` and `StubFinder` to resolve the dynamic URL; run `./gradlew test` and assert DTO `id=42`, `status=PAID`.
12. **Try an incompatible Gradle Plugin/BOM combination in a scratch branch**, observe the resolve/compile/test errors, and revert; document how to select a compatible version set.
13. **Integrate into CI**: mandatory producer tests → stub publication → consumer tests pinned to a specific version; never publish if generated producer tests have not passed.

**Completion criteria:** you have a producer `build.gradle` with **the right plugin and dependencies in their proper roles**, generated producer tests are created and executed, the `stubs` JAR is published with the right coordinates, and the consumer runs **real client code** through Stub Runner without starting the producer.

## 21. Self-Check Questions

1. Why does merely adding `spring-cloud-starter-contract-verifier` to `testImplementation` not guarantee generated producer tests will be created?
2. How do the `org.springframework.cloud.contract` plugin and the `spring-cloud-starter-contract-verifier` dependency differ in responsibility?
3. What parts does the `spring-cloud-dependencies` BOM manage, and does it automatically determine the plugin version in `plugins`?
4. Why should `testImplementation` be used instead of `implementation` for the verifier?
5. What does the `contracts { baseClassForTests; testFramework; testMode }` block control?
6. Does a contract written in Groovy DSL force generated tests to use Spock/Groovy?
7. When an application uses Spring WebFlux, is `MOCKMVC` still the best default choice?
8. Why does a successful `./gradlew clean test` reporting 0 generated tests fail to prove the producer obeys the contract?
9. Why shouldn't you directly edit Java tests generated under `build/`?
10. How do an application JAR and a `stubs`-classifier JAR differ?
11. What are the roles of `maven-publish` and `verifierStubsJar` in creating/publishing the stub artifact?
12. Why does `publishToMavenLocal` not mean a consumer on a different CI runner can download the artifact?
13. How does `StubsMode.LOCAL` differ from `REMOTE` regarding where the JAR comes from; does it determine the WireMock HTTP port?
14. Why does a consumer usually only need `spring-cloud-starter-contract-stub-runner` without applying the Contract Verifier Gradle Plugin?
15. In multi-module Gradle builds, why shouldn't the verifier plugin be applied automatically to every module?
16. To prove integration succeeded, which steps from the contract to the consumer client must be verified?

**Key takeaway:** **Integrating Spring Cloud Contract with Gradle requires two parallel steps: applying the right build plugin to generate tests/stubs, and declaring the right dependencies so tests can run.** On the producer side, choose `org.springframework.cloud.contract`, `spring-cloud-starter-contract-verifier`, compatible BOM/versions, the `contracts` extension, and an appropriate base test. Verify that generated tests actually **run and catch when the producer breaks the contract** before packaging/publishing the `stubs`-classifier JAR. On the consumer side, use `spring-cloud-starter-contract-stub-runner`, pin artifact versions, and run real client code against the stub. When Gradle tasks are properly wired into CI, teams can detect incompatible API changes **without running every microservice simultaneously**.
