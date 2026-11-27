# Multi-Module Producer and Consumer Workflow

## Learning Objectives

When using **Spring Cloud Contract**, a **producer** service defines HTTP or messaging behavior using **Groovy/YAML DSL**. The Gradle plugin can generate **producer contract tests** to confirm the implementation obeys the contract, while also building a **stub artifact** for the **consumer** to use with **Stub Runner**. In a project with multiple Gradle modules, the biggest challenge is not merely declaring dependencies, but **ensuring test generation, producer verification, stub packaging, and consumer checks run in the right order with the right versions**.

This lesson belongs to the **Gradle Integration** chapter and focuses on the multi-module model inside a single Gradle multi-project build and how to translate that model to CI.

After this lesson, you will be able to:

- Design a `settings.gradle` structure for two modules `inventory-producer` and `checkout-consumer`, each with clear responsibilities.
- Configure the Spring Cloud Contract Gradle plugin **in the producer module**, avoiding blanket application of the verifier plugin to every consumer.
- Distinguish `src/contractTest/resources/contracts`, the `contractTest` source set, and the `generateContractTests`, `contractTest`, `generateClientStubs`, and `verifierStubsJar` tasks.
- Publish a stub JAR with the **`stubs` classifier** via `maven-publish`, only after producer tests pass.
- Configure the consumer to use `@AutoConfigureStubRunner` and a real HTTP client against stubs with the exact group/artifact/version.
- Sequence task dependencies or CI pipeline stages so consumer tests never run before a candidate stub exists.
- Avoid **circular dependencies**, stale artifacts in Maven cache, false-green Gradle test caches, and publishing stubs when producer tests fail.
- Distinguish what contract testing guarantees from database, broker, or network integrations that require additional tests.

> **Critical rule:** the producer must prove it implements the contract accurately before a stub is published as a verified interface; the consumer must test against the exact stub version for the change under review.

## 1. The Problem: Two Modules in One Repository

Suppose an ordering system has:

- **Inventory Service**: producer of `GET /api/inventory/{sku}`.
- **Checkout Service**: consumer calling Inventory to check stock availability.

Inventory exposes:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

Checkout needs an HTTP client that sends the right request and parses the JSON response with `quantity` as a **number** and `available` as a **boolean**.

When both services are developed inside the same repository, you want to:

1. Update contracts/implementation in `inventory-producer`.
2. Run generated producer tests.
3. Package Inventory's stub JAR from that contract.
4. Have `checkout-consumer` use the stub to test its HTTP client and business logic.
5. Block merge or publishing if either side fails.

A Gradle multi-project build helps coordinate these steps, **yet does not automatically turn a project dependency into a Spring Cloud Contract stub**. You must explicitly design the artifact and testing flow.

### Responsibility Map

~~~mermaid
flowchart TD
    R["Gradle root project"] --> P[":inventory-producer"]
    R --> C[":checkout-consumer"]
    P --> D["Groovy/YAML DSL"]
    D --> T["Generated contract tests"]
    T --> V{"Producer implementation PASSES?"}
    V -->|No| X["Block publish / consumer gate"]
    V -->|Yes| J["verifierStubsJar (:stubs)"]
    J --> M["Maven local or artifact repository"]
    M --> S["Stub Runner in consumer tests"]
    S --> H["Real HTTP client of Checkout"]
    H --> A["Consumer assertions"]
~~~

**Do not** make `checkout-consumer` depend directly on the runtime implementation of `inventory-producer`. The consumer should depend on the **communication contract** and stub at test time, keeping build and deployment of the two services decoupled.

## 2. Three Dependency Types to Distinguish

| Type | Example | Should you use it? |
|---|---|---|
| **Gradle project dependency** | `implementation project(':inventory-producer')` | Usually **no** for a microservice consumer; pulls producer code onto compile/runtime classpath |
| **Stub artifact by coordinates** | `com.example:inventory-producer:1.2.0-rc.1:stubs` | **Yes**, for Stub Runner at test runtime |
| **Shared API/schema module** | `implementation project(':inventory-api')` | Can be considered when intentionally sharing models; does not replace contract tests |

The big difference is that `implementation project(':inventory-producer')` tells Gradle to compile and put producer classes onto the consumer's classpath. In a microservice architecture, Checkout should not invoke internal Inventory classes directly just to test HTTP.

Meanwhile, Stub Runner needs the **JAR containing mappings/contracts**, not the application JAR. If the producer publishes two artifacts:

~~~text
com.example:inventory-producer:1.2.0-rc.1
com.example:inventory-producer:1.2.0-rc.1:stubs
~~~

the artifact with classifier `stubs` is what Stub Runner needs to load. The primary artifact may be a `jar`/`bootJar` for running the application, depending on packaging setup.

## 3. Gradle Multi-Project Organization

A reference layout:

~~~text
commerce-contract-demo/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── inventory-producer/
│   ├── build.gradle
│   ├── src/main/java/com/example/inventory/...
│   └── src/contractTest/
│       ├── java/com/example/inventory/contracts/InventoryContractBase.java
│       └── resources/contracts/inventory/stockAvailable.groovy
└── checkout-consumer/
    ├── build.gradle
    ├── src/main/java/com/example/checkout/...
    └── src/test/java/com/example/checkout/InventoryConsumerContractTest.java
~~~

Root `settings.gradle`:

~~~groovy
rootProject.name = 'commerce-contract-demo'

include 'inventory-producer'
include 'checkout-consumer'
~~~

These are **two Gradle subprojects**, not two source set variants within one module. Gradle identifies tasks by path:

~~~text
:inventory-producer:contractTest
:inventory-producer:verifierStubsJar
:checkout-consumer:test
~~~

Task paths allow CI to target the right module, avoiding running everything accidentally or skipping mandatory steps.

### Centralizing Plugin Versions at the Root

For a real project, manage compatible Spring Boot, Spring Cloud Contract, and Gradle versions. For example, `settings.gradle` can declare plugin versions (replace placeholders before use):

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
    plugins {
        id 'org.springframework.boot' version 'REPLACE_BOOT_VERSION'
        id 'io.spring.dependency-management' version 'REPLACE_DEP_MGMT_VERSION'
        id 'org.springframework.cloud.contract' version 'REPLACE_SCC_VERSION'
    }
}

rootProject.name = 'commerce-contract-demo'
include 'inventory-producer', 'checkout-consumer'
~~~

The `settings.gradle` snippet above **replaces the shorter settings snippet earlier** when centralizing plugin versions; do not declare `include` twice. The `REPLACE_...` strings are placeholders, not downloadable versions.

Root `build.gradle` can hold shared coordinate defaults:

~~~groovy
allprojects {
    group = 'com.example'
    version = providers.gradleProperty('releaseVersion')
        .orElse('1.2.0-rc.1')
        .get()

    repositories {
        mavenCentral()
    }
}
~~~

Illustrative `gradle.properties`:

~~~properties
releaseVersion=1.2.0-rc.1
~~~

**Note:** because the Gradle project version is shared in this example, both producer and consumer share a version number. That does **not** make them the same artifact. Their full coordinates still differ by `artifactId`.

Never put publish repository credentials or tokens into a committed `gradle.properties`. Supply credentials via CI/secret manager only in authorized publish steps.

## 4. Producer Keeps Contracts in a Dedicated Source Set

For the Spring Cloud Contract Gradle plugin from 3.x onward, the convention documented is:

~~~text
inventory-producer/
└── src/contractTest/
    ├── resources/contracts/
    │   └── inventory/stockAvailable.groovy
    └── java/
        └── com/example/inventory/contracts/InventoryContractBase.java
~~~

**This is a common difference compared to Maven examples.** The modern Gradle plugin uses the `contractTest` source set; `src/test/resources/contracts` appeared in older docs and is a transitional path that should not be assumed as the new standard.

A simple Groovy DSL contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Inventory for SKU-101 has 8 units in stock'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 8
        )
    }
}
~~~

If preferring YAML DSL, an alternative `stockAvailable.yml` file can be used:

~~~yaml
description: 'Inventory for SKU-101 has 8 units in stock'
request:
  method: GET
  url: '/api/inventory/SKU-101'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
    available: true
    quantity: 8
~~~

**Include only one contract version** for the same request/response in a build; both variants are shown here just to illustrate Groovy and YAML.

### Do Not Let the Consumer Keep Its Own Copy of the Contract

In this model, Inventory owns the HTTP contract. Checkout tests against the **stub artifact generated from the contract** rather than copying `stockAvailable.groovy` into the consumer module and editing it independently.

If an organization wants consumer-driven proposals or a separate contract repository, Spring Cloud Contract also supports fetching contracts from Maven/SCM. However, that is **a different ownership and distribution model**: you still must ensure the producer runs generated tests against the consumer-proposed contract and publishes a clearly versioned artifact.

## 5. Configuring the Gradle Plugin in the Producer Module

Example `inventory-producer/build.gradle` (Groovy DSL, with comments explaining the layout):

~~~groovy
import org.gradle.api.publish.maven.tasks.PublishToMavenLocal
import org.gradle.api.publish.maven.tasks.PublishToMavenRepository

plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
    id 'org.springframework.cloud.contract'
    id 'maven-publish'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}

contracts {
    testFramework = 'JUNIT5'
    testMode = 'MockMvc'

    baseClassForTests =
        'com.example.inventory.contracts.InventoryContractBase'

    contractsDslDir = file('src/contractTest/resources/contracts')
}

tasks.named('contractTest', Test) {
    useJUnitPlatform()
}

publishing {
    publications {
        stubs(MavenPublication) {
            artifact tasks.named('verifierStubsJar')
        }
    }
}

// For both local and remote publications, enforce a mandatory gate
// requiring producer contract tests to run before publishing.
tasks.withType(PublishToMavenLocal).configureEach {
    dependsOn tasks.named('contractTest')
}

tasks.withType(PublishToMavenRepository).configureEach {
    dependsOn tasks.named('contractTest')
}
~~~

This example assumes:

- Plugin versions are configured in `pluginManagement`.
- A compatible Spring Cloud BOM or dependency-management setup manages dependency versions; if absent, you must add the appropriate BOM or dependency constraints.
- The Gradle plugin creates `contractTest` and `verifierStubsJar` tasks per its documentation.
- The project specifies a valid base class and the producer application has a working controller.
- `maven-publish` creates a `stubs` publication inheriting group/version from the Gradle project, with default `artifactId` `inventory-producer` and `verifierStubsJar` carrying classifier `stubs` per plugin convention.

**Note:** the snippet above is a **technical configuration skeleton**, not a repository that has been executed and verified here. Syntax/behavior can vary across Gradle, Spring Boot, and Spring Cloud Contract versions. Run `./gradlew :inventory-producer:tasks --all` and inspect build logs to confirm tasks, source sets, and publications in your real project.

### Why Does `maven-publish` Require Manual Configuration?

Spring Cloud Contract documentation notes that since **3.0.0**, default automatic stub publication is disabled. Thus, applying the Verifier plugin alone **does not mean** `publishToMavenLocal` or `publish` will include `*-stubs.jar`. You must attach `verifierStubsJar` to a Gradle `MavenPublication`.

In the example:

~~~groovy
publishing {
    publications {
        stubs(MavenPublication) {
            artifact tasks.named('verifierStubsJar')
        }
    }
}
~~~

is the essential piece for creating the Maven artifact:

~~~text
com.example:inventory-producer:1.2.0-rc.1:stubs
~~~

After configuring, check the files in `inventory-producer/build/libs` and the actual published artifact. Never assume any JAR containing "stubs" in its name has the right classifier or layout.

### Why Gate the Publication Task?

The `verifierStubsJar` task can build a stub JAR from DSL even when the producer has not proven its code works. It is **not a synonym for `contractTest`**.

These two rules:

~~~groovy
tasks.withType(PublishToMavenLocal).configureEach {
    dependsOn tasks.named('contractTest')
}

tasks.withType(PublishToMavenRepository).configureEach {
    dependsOn tasks.named('contractTest')
}
~~~

force Gradle publication tasks to **wait on `contractTest`**. However, they cannot protect JAR upload paths **outside the Gradle task graph**, such as a shell script directly pushing `build/libs/*-stubs.jar` to a repository. CI must block any publish path that bypasses the gate.

If the project has other critical integration tests, the quality gate can require `check` or additional tasks, not only `contractTest`.

## 6. Producer Base Test Exercising the Real Implementation

Generated producer tests need a base class the plugin can extend. In `MockMvc` mode, the base class typically wires the real controller and fakes/mocks downstream dependencies to produce deterministic fixtures.

Example `src/contractTest/java/com/example/inventory/contracts/InventoryContractBase.java`:

~~~java
package com.example.inventory.contracts;

import com.example.inventory.InventoryController;
import com.example.inventory.InventoryService;
import com.example.inventory.StockResponse;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;

import java.util.Optional;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

public abstract class InventoryContractBase {

    @BeforeEach
    protected void setUpContract() {
        InventoryService service = mock(InventoryService.class);

        when(service.findBySku("SKU-101"))
            .thenReturn(Optional.of(
                new StockResponse("SKU-101", true, 8)
            ));

        RestAssuredMockMvc.standaloneSetup(
            new InventoryController(service)
        );
    }
}
~~~

This example uses `InventoryController`, `InventoryService`, and `StockResponse` **created by the project**. You must implement the controller with `GET /api/inventory/{sku}`, dependency injection, JSON response, and status handling.

Important points:

1. Generated tests must invoke the **real producer controller**, not an HTTP stub returning canned JSON.
2. The fake service returning `8` establishes a clear scenario, yet does not verify the real repository or database.
3. If error responses depend on `@ControllerAdvice`, security, filters, or custom converters, `standaloneSetup` may not load the full configuration. Consider `WebApplicationContext` or testing over a real HTTP server when needed.
4. `@BeforeEach` matches **JUnit 5**, since the Gradle plugin sets `testFramework = 'JUNIT5'`.
5. The base class must live in a source set visible to generated contract tests for compilation; **never place it arbitrarily only in main sources**.

### Three Pieces of Evidence to Inspect in Generated Tests

- Does the test extend `InventoryContractBase`?
- Does the test send `GET /api/inventory/SKU-101` and assert `200` + rightly typed body fields?
- Did the test **execute** in `:inventory-producer:contractTest` rather than merely being written into `build/generated-test-sources`?

Generated files in Gradle typically sit under `inventory-producer/build/generated-test-sources/contractTest/java` or the path configured by your plugin. **Never edit generated tests directly**; edit the DSL or base class and regenerate.

## 7. Key Gradle Tasks and Their Relationships

| Producer module task | Role | Proof that producer complies? |
|---|---|---|
| `generateContractTests` | Generates test sources from Groovy/YAML DSL | No; tests may not have run yet |
| `contractTest` | Executes generated contract tests | **Yes**, if tests were discovered and actually executed |
| `generateClientStubs` | Generates HTTP WireMock mappings/stub definitions | No |
| `verifierStubsJar` | Packages stub artifact from mappings/contracts | No |
| `copyContracts` | Copies contract sources into stub packaging area | No |
| `publishStubsPublicationToMavenLocal` | Publishes the `stubs` publication to the local Maven repo | Conditionally; only when gated |
| `publishStubsPublicationTo...Repository` | Publishes the `stubs` publication to a configured repository | Conditionally; only when gated |

The Spring Cloud Contract Gradle plugin registers the relevant tasks; exact output paths and `dependsOn` relationships may vary by version. **Never infer outcomes from task names alone.**

### Trust Ordering

~~~mermaid
flowchart TD
    A["generateContractTests"] --> B["contractTest executes"]
    B --> C{"PASSES with valid test count?"}
    C -->|No| X["STOP: do not publish"]
    C -->|Yes| D["generateClientStubs"]
    D --> E["verifierStubsJar"]
    E --> F["publishStubsPublicationToMavenLocal"]
    F --> G[":checkout-consumer:test"]
    G --> H{"Consumer PASSES?"}
    H -->|No| I["Block release, review compatibility"]
    H -->|Yes| J["Eligible for review/publish"]
~~~

**This diagram shows *quality-assurance* ordering, not a claim that Gradle tasks must run in strictly sequential physical order line by line.** A Gradle build can generate mappings/JARs before running producer tests, as long as **publishing** cannot run when producer tests fail.

### Step-by-Step Commands

Using the Gradle wrapper at the root:

~~~bash
# 1. Confirm producer plugin and available tasks.
./gradlew :inventory-producer:tasks --all

# 2. Run generated producer contract tests.
./gradlew :inventory-producer:contractTest

# 3. Build the stub JAR via the plugin.
./gradlew :inventory-producer:verifierStubsJar

# 4. Publish candidate to Maven local once producer gate passes.
./gradlew :inventory-producer:publishStubsPublicationToMavenLocal

# 5. Run consumer tests using Stub Runner LOCAL.
./gradlew :checkout-consumer:test
~~~

These commands are **practice instructions**, not commands executed within this lesson. Because the publication task is configured with `dependsOn contractTest`, step 4 still requires producer tests to pass in Gradle's task graph; tests already run in step 2 may be treated as up-to-date if inputs/outputs have not changed.

**Never** add `-x contractTest`, `-x test`, or gate-bypass flags into a release pipeline.

## 8. Consumer Only Needs Stub Runner, Not the Verifier Plugin

In `checkout-consumer/build.gradle`, the consumer needs the test dependency:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

Only the **producer** module needs the `org.springframework.cloud.contract` Gradle plugin to generate/check producer tests and stubs from source contracts. The consumer only needs the **stub-runner test dependency** when consuming the generated artifact.

Do not add:

~~~groovy
// ANTI-PATTERN for a microservice consumer that only needs HTTP:
implementation project(':inventory-producer')
~~~

because that couples producer implementation code into Checkout's runtime and does not replace Stub Runner.

### A Real HTTP Client on the Consumer

Java class example:

~~~java
package com.example.checkout.inventory;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public class InventoryClient {

    private final RestClient http;

    public InventoryClient(RestClient.Builder builder, String baseUrl) {
        this.http = builder.baseUrl(baseUrl).build();
    }

    public StockView findBySku(String sku) {
        return http.get()
            .uri("/api/inventory/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(StockView.class);
    }
}
~~~

Response type:

~~~java
package com.example.checkout.inventory;

public record StockView(
    String sku,
    boolean available,
    int quantity
) {}
~~~

`RestClient` requires Spring Framework 6.1+; on older versions, use `RestTemplate`, `WebClient`, or Feign with the same base URL configuration principle. `record` requires a Java version supporting records.

In production, the client can be created by a `@Configuration` bean reading `inventory.base-url`. In the consumer test adapter, we pass the URL provided by Stub Runner so tests never hit real Inventory by mistake.

## 9. Consumer Test Using Stub Runner's Actual Runtime Port

Example `checkout-consumer/src/test/java/.../InventoryConsumerContractTest.java`:

~~~java
package com.example.checkout.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.0-rc.1:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryConsumerContractTest {

    @StubRunnerPort("inventory-producer")
    int inventoryStubPort;

    @Autowired
    RestClient.Builder restClientBuilder;

    @Test
    void readsStockFromStub() {
        assertThat(inventoryStubPort).isGreaterThan(0);

        InventoryClient client = new InventoryClient(
            restClientBuilder,
            "http://localhost:" + inventoryStubPort
        );

        StockView result = client.findBySku("SKU-101");

        assertThat(result.sku()).isEqualTo("SKU-101");
        assertThat(result.available()).isTrue();
        assertThat(result.quantity()).isEqualTo(8);
    }
}
~~~

In this example:

- `ids` specifies **group, artifact, version, classifier**, and requests a dynamic port `:0`.
- `LOCAL` tells Stub Runner to look up the stub in the local Maven repository of the **test execution environment**.
- `@StubRunnerPort("inventory-producer")` injects the real port the stub is listening on.
- `InventoryClient` is the consumer's **real client**, differing only in the producer address.
- Assertions verify both field names and the data types the consumer expects.

This is a **consumer HTTP adapter test**; it does not yet test how the production bean is wired with `inventory.base-url` because the client is instantiated in the test via its constructor. To test Spring bean wiring too, configure the base URL **before the bean is created** (such as a fixed stub port in a test profile) rather than mutating a property in `@BeforeEach` and expecting a singleton bean to rebuild itself.

### Never Use Port 0 as a URL

When `ids` ends with `:0`, **the real port is not 0**. Never write:

~~~java
String baseUrl = "http://localhost:0"; // Wrong
~~~

Always resolve it via `@StubRunnerPort` or Stub Runner's `StubFinder`. With multiple producers, look up each port/URL by its specific artifact.

### Why Are Stub Tests Alone Not Enough to Trust the Producer?

Stubs return responses based on the DSL, without calling the real Inventory Service. If producer code returns `"quantity":"8"` while the DSL specifies `quantity: 8`, the consumer can still pass against the stub. Therefore, **generated producer contract tests are a mandatory gate before publishing stubs**.

## 10. Connecting Tasks Across Both Modules in the Same Gradle Build

When testing locally on one machine or in a single CI job, you can ensure consumer tests start only after the producer has published the candidate stub to the local Maven repository.

In `checkout-consumer/build.gradle`, you can add:

~~~groovy
tasks.named('test', Test) {
    // This publication task only exists when the producer configured
    // a MavenPublication named 'stubs' as shown in Section 5.
    dependsOn ':inventory-producer:publishStubsPublicationToMavenLocal'
}
~~~

When running:

~~~bash
./gradlew :checkout-consumer:test
~~~

Gradle follows the test task's dependency, meaning it runs the **producer publication task** first; the publication task in turn depends on `contractTest`.

### Why Must the Producer Not Depend on the Consumer?

Never create a mutual dependency:

~~~text
:checkout-consumer:test
    dependsOn :inventory-producer:publishStubsPublicationToMavenLocal

:inventory-producer:contractTest
    dependsOn :checkout-consumer:test    # WRONG
~~~

That creates a **circular task dependency**. Gradle will fail to construct the task graph.

Rule:

- The producer **provides** contracts and stubs.
- The consumer **consumes** stubs.
- **Producer verification** tasks do not depend on consumer tests running.
- A **public release** decision may require both producer and consumer gates to PASS, yet that is a **release pipeline** dependency, not a loop between source modules.

### Optional Root Orchestration Task

If a team wants an easy-to-remember command, root `build.gradle` can register:

~~~groovy
tasks.register('verifyProducerAndConsumer') {
    group = 'verification'
    description = 'Verify producer contracts then run consumer tests'
    dependsOn ':checkout-consumer:test'
}
~~~

With the consumer's `test.dependsOn(':inventory-producer:publishStubsPublicationToMavenLocal')` and the producer publication gate above, a single command:

~~~bash
./gradlew verifyProducerAndConsumer
~~~

executes the configured task graph. **No need to run two tests across two projects in ad-hoc shell scripts without exit-code checks.**

### Distinguish the Gradle Task Graph from Artifact Resolution

`dependsOn` only coordinates **when tasks run**. Stub Runner `LOCAL` still has to find the artifact at the exact coordinates inside the local Maven repository.

If the publication is renamed, the classifier is wrong, the version disagrees with `ids`, or Gradle publishes to another repository, consumer tests still fail to load stubs even though the task graph ran in order.

## 11. Version and Cache Pitfalls in Multi-Module Builds

In our example:

~~~text
Producer project version:
  1.2.0-rc.1

Published stub coordinate:
  com.example:inventory-producer:1.2.0-rc.1:stubs

Consumer test annotation:
  ids = "com.example:inventory-producer:1.2.0-rc.1:stubs:0"
~~~

**All three places must refer to the exact same version.** If the project version changes yet the annotation stays `1.1.0`, Stub Runner can load the stale stub and tests still pass. That is a serious **false positive**: the producer change under review was never tested by the consumer.

### Passing Version via a Gradle Property

You can configure:

~~~properties
# gradle.properties
releaseVersion=1.2.0-rc.1
~~~

In the consumer, pass this property to the test JVM:

~~~groovy
tasks.named('test', Test) {
    systemProperty 'stub.version', project.version.toString()
}
~~~

For Stub Runner annotations, how a dynamic version gets interpolated into `ids` depends on Spring Test/Stub Runner property resolution in your active version. **Do not assume every annotation interpolates `${stub.version}` identically.** The least ambiguous approach in this lesson is using a **fixed candidate version** verified across root project and tests, updating them together.

In professional CI, you can feed a test profile/annotation from a framework-supported **versioned property** or configure Stub Runner via application properties. What matters is **logging the exact version Stub Runner resolved**.

### Two Caches That Can Cause False-Green Tests

| Cache | Risk | Mitigation |
|---|---|---|
| **Maven local `~/.m2/repository`** | Holds a stub with the same version from an earlier build | Use unique versions/digests and isolated repository environments |
| **Gradle build cache / up-to-date checks** | Consumer `test` task is marked up-to-date when an external `LOCAL` artifact changed outside task inputs | Declare appropriate inputs, disable caching for sensitive gates, or force re-execution in CI |

For instance, if you **overwrite a stub artifact under the same version in Maven local** without changing Checkout's code or inputs, Gradle may mark `:checkout-consumer:test` as **`UP-TO-DATE`**. CI then lacks proof that consumer tests actually ran against the new stub.

You can run:

~~~bash
./gradlew :checkout-consumer:test --rerun-tasks --no-build-cache
~~~

as a safeguard to force tests to re-run when debugging or validating candidates. Long-term, the cleaner design is **immutable artifact versions** and proper task input declarations so Gradle detects changes automatically.

### Do Not Share a Mutable Local Maven Cache Across Parallel CI Jobs

If two PRs overwrite `com.example:inventory-producer:1.2.0-SNAPSHOT:stubs` in the same `~/.m2`, PR A's consumer tests may accidentally pull PR B's artifact. Safer options:

- Give each pipeline its own **isolated local Maven repository**, or
- Use a **unique candidate version per commit/build ID**, or
- Pass artifacts from producer job to consumer job as checksummed CI artifacts, or
- Use a staging repository with strict isolation and permissions.

Avoid `latest`/`+` in consumer release gates when you must prove compatibility for an **exact candidate revision**.

## 12. When Producer and Consumer Live in Two Separate Repositories

The Gradle multi-project demo helps visualize the flow, yet real-world microservices usually live in **two repositories with two pipelines**.

The key difference: you cannot rely on Gradle's `dependsOn ':inventory-producer:...'` when the producer is not a subproject in the same build.

A typical pipeline:

~~~mermaid
sequenceDiagram
    participant PR as Producer PR
    participant PV as Producer CI
    participant SA as Stub candidate artifact
    participant CR as Consumer CI
    participant R as Release
    PR->>PV: Update code + Groovy/YAML contracts
    PV->>PV: Run generated producer tests
    alt Producer PASSES
        PV->>SA: Package artifact with unique version
        SA->>CR: Provide stub via artifact transfer/staging
        CR->>CR: Stub Runner + real consumer tests
        alt Consumer PASSES
            CR-->>R: Compatibility gate passed
        else Consumer FAILS
            CR-->>PR: Investigate breaking change
        end
    else Producer FAILS
        PV-->>PR: Stop, do not publish verified stub
    end
~~~

In this setup, the consumer can use `StubRunnerProperties.StubsMode.REMOTE` with a Maven artifact repository, `LOCAL` if CI installed the candidate into an isolated local repo, or `CLASSPATH` if the stub is placed on the test classpath.

### CI Artifacts vs. Release Artifacts

Once producer tests succeed, you can build a **candidate stub** to test compatibility. This candidate does not need to be published publicly as an official release yet; it can live in a staging repository or CI job artifacts.

- **Candidate artifact:** serves test jobs, with traceable version/digest.
- **Published/released stub:** published only after all mandatory organizational gates pass.

If consumer tests are a required release gate, never publish the release stub before consumer tests run; pass the candidate through staging/CI artifacts instead.

### Guaranteeing the Same Revision

A useful CI report:

~~~text
Producer source SHA: <commit-A>
Contracts SHA:       <commit-A>
Producer test count: 6 run / 6 passed
Candidate stub:      com.example:inventory-producer:1.2.0-rc.1:stubs
Candidate checksum:  <sha256>
Consumer source SHA: <commit-B>
Consumer test count: 4 run / 4 passed
Stub actually loaded: 1.2.0-rc.1
Decision: eligible for release review
~~~

Values in `<...>` are placeholders filled from real CI. If the consumer accidentally loaded `1.1.0`, never report "candidate compatible" just because tests passed.

## 13. Example CI Task Orchestration for a Single Gradle Repository

A minimal Gradle CI job might run:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# Wrapper and plugins configured across root + subprojects.
./gradlew :inventory-producer:contractTest

# This task must depend on the producer test gate per build.gradle.
./gradlew :inventory-producer:publishStubsPublicationToMavenLocal

# Test consumer against the freshly installed candidate stub.
./gradlew :checkout-consumer:test --rerun-tasks --no-build-cache
~~~

This is an **illustrative script guide**, not an artifact executed inside this lesson. `set -euo pipefail` stops execution if any command fails. On PowerShell/Windows, check exit codes appropriately, and avoid `&&` on Windows PowerShell 5.1.

### When Using a Single Aggregate Command

If task dependencies are configured as in Section 10:

~~~bash
./gradlew verifyProducerAndConsumer --no-build-cache
~~~

Gradle schedules tasks per the task graph; using the pinned Gradle wrapper keeps CI and developer machines on the same tool version. However, if an external artifact outside task inputs changes while a task appears up-to-date, apply the cache safeguards explained above.

### Separating Publish Permissions

A production CI pipeline should separate:

1. **Verify job** without remote publish credentials: runs producer contracts, builds candidate, tests consumer.
2. **Release job** running only on approved commits/tags after all gates PASS: uploads the exact verified artifact with checksum, or rebuilds and verifies on that exact commit.

In Gradle, publication tasks can be invoked with `publish`/`publishToMavenLocal`. Never assume `publish` makes Gradle run `contractTest` automatically unless `dependsOn` rules or pipeline gates are configured.

For remote repositories, add `publishing.repositories.maven { ... }` and secure credentials via CI secrets. **Never put passwords/tokens in a committed `build.gradle`**, and never publish mutable artifacts under an existing release version.

## 14. Adding a Third Module: Shared Contracts or Shared Models?

Some teams add an `inventory-api`, `contracts-common`, or `testing-support` module. Distinguish the goals:

| Additional module | Contents | Should you create it? |
|---|---|---|
| `inventory-api` | Shared interfaces/DTOs between two services | Only when intentionally sharing code; can create tight coupling |
| `contract-test-support` | Shared base tests/helpers, matcher utilities, or test fixtures | Useful when multiple producers share testing infrastructure |
| `api-contracts` | Groovy/YAML DSL reviewed by multiple teams | Useful when ownership lives in a separate module/repository |
| `inventory-producer` | Producer implementation | Should **not** be a runtime dependency of Checkout just for stubs |

If moving DSL files into an `api-contracts` module, the producer must **fetch the exact contract version** and generate producer tests from it. The Spring Cloud Contract Gradle plugin offers `contractDependency`/`contractRepository` to fetch contracts from an artifact or SCM, though configuration differs from keeping contracts inside the producer.

Never create:

~~~text
inventory-producer dependsOn checkout-consumer
checkout-consumer dependsOn inventory-producer
~~~

as Gradle project dependencies; that creates an invalid build/runtime dependency cycle between two independent microservices.

### Choosing an Ownership Model

- **Producer-side contracts:** producer stores DSL, generated tests, and stub artifact; consumer uses Stub Runner. Simplest for this lesson.
- **Consumer-proposed contracts:** consumer proposes expectations, producer verifies and publishes stubs from the accepted contract; may use a shared repo/PR workflow.
- **Shared contract repository:** fits organizations where multiple producers and consumers follow a centralized review process, requiring stricter governance, versioning, and CI verification.

Invariant: **every published contract must have proof the producer satisfies it**, regardless of which module stores the DSL files.

## 15. Error HTTP Branches and Messaging Also Belong in the Pipeline

Do not test only `200 OK`. A consumer may rely on:

- `404` + error code `SKU_NOT_FOUND` when a SKU does not exist.
- `503` + `Retry-After` when Inventory is temporarily unavailable.
- `200` with `available=false` and `quantity=0` when out of stock.
- A `StockChanged` message with the right destination, headers, and payload.

For HTTP:

~~~groovy
Contract.make {
    description 'SKU does not exist'
    request {
        method 'GET'
        url '/api/inventory/SKU-404'
    }
    response {
        status 404
        headers {
            contentType(applicationJson())
        }
        body(code: 'SKU_NOT_FOUND')
    }
}
~~~

For messaging:

~~~groovy
Contract.make {
    label 'stock_changed'
    input {
        triggeredBy('emitStockChanged()')
    }
    outputMessage {
        sentTo('stock-events')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-101',
            quantity: 0
        )
        headers {
            messagingContentType(applicationJson())
        }
    }
}
~~~

**Both are illustrative Groovy DSL contracts**, omitting base classes and binder setup. For messaging, producer tests require `@AutoConfigureMessageVerifier` and appropriate integration; the consumer needs Stub Runner label triggering alongside a listener/broker/test binder. Never assume an HTTP WireMock mapping simulates a message automatically.

In a Gradle multi-project build, messaging contract tests are likewise the **producer's responsibility**, while consumer tests using message stubs must use asynchronous assertions, such as Awaitility waiting for final state within a reasonable deadline.

## 16. Common Multi-Module Gradle Pitfalls

| Symptom | Possible cause | How to investigate |
|---|---|---|
| `Task 'contractTest' not found` | Plugin not applied to producer or version uses different task name | Inspect `:inventory-producer:tasks --all` and plugin setup |
| No generated test files | DSL placed in wrong folder; modern Gradle uses `src/contractTest/resources/contracts` | Check `contractsDslDir` and build logs |
| Base class fails to compile | Placed in wrong source set, missing verifier/test dependencies | Verify `src/contractTest/java`, classpath, and JUnit |
| `contractTest` runs zero tests | Contracts not found, or wrong test runner/filter/JUnit setup | Check test reports and executed test count |
| `verifierStubsJar` exists but no Maven publication | `maven-publish` not configured or artifact not attached | Check `publishing.publications` and `:tasks --all` |
| Stub artifact lacks `stubs` classifier | Custom JAR classifier mismatch, wrong publication | Inspect filenames and Maven coordinates |
| Consumer Stub Runner `LOCAL` cannot find stub | `publishStubsPublicationToMavenLocal` not run or version mismatch | Inspect Maven local repository and resolved artifact |
| Consumer receives unexpected 404 | Request matcher does not match mapping | Read generated WireMock mapping and actual HTTP request |
| Consumer test stays green despite contract edit | Consumer uses stale stub or Gradle test task was `UP-TO-DATE` | Pin version, inspect resolved artifact, rerun tests |
| Publication runs when producer test fails | Gate only in loose shell script; publish task lacks `dependsOn` test | Enforce task/pipeline dependencies and fail closed |
| Task graph reports circular dependency | Producer depends on consumer test, consumer depends on producer publish | Only producer -> stub -> consumer; release gate belongs in pipeline |
| Tests fail only in parallel | Shared stub ports/data/caches | Isolate environments, ports, and coordinates per pipeline |
| Multi-module build pulls entire producer into Checkout | Unnecessary `implementation project(':inventory-producer')` | Use only stub artifacts for consumer HTTP tests |
| Consumer behaves differently locally vs. CI | Inconsistent Maven cache/repos or JDK/BOM versions | Pin Gradle wrapper, versions, and stub digests |

### Focus Debugging on Three Questions

1. **Was the producer really verified?** Open generated contract tests and test reports.
2. **Which stub was published/loaded?** Check group, artifact, version, classifier, and digest.
3. **Did the consumer call the right stub using its real client?** Check runtime URL, request matchers, and business assertions.

Do not paper over failures by merely raising timeouts or switching to `latest`/`+`, as that hides the underlying bug.

## 17. Hands-On Exercise: Finding the Break in a Pipeline

### Prompt

A repository has two modules: `inventory-producer` and `checkout-consumer`. The team configured:

~~~groovy
// inventory-producer/build.gradle
publishing {
    publications {
        stubs(MavenPublication) {
            artifact tasks.named('verifierStubsJar')
        }
    }
}
~~~

And the CI script:

~~~bash
./gradlew :inventory-producer:verifierStubsJar
./gradlew :inventory-producer:publishStubsPublicationToMavenLocal
./gradlew :checkout-consumer:test
~~~

However, `publishStubsPublicationToMavenLocal.dependsOn contractTest` was not configured. The consumer uses Stub Runner `LOCAL` with version `1.1.0`, while the producer project was bumped to `1.2.0-rc.1`.

**Question 1. How many risks need fixing?**

At least three:

- The build packages and publishes a stub **without ensuring producer contract tests ran and passed**.
- The consumer is testing against an **old stub version**, not the candidate under review.
- The script shows no mechanism stopping the pipeline if one command fails (relying on shell/CI runner defaults).

**Question 2. Where should the gate be fixed?**

Configure the producer's publication task to depend on `contractTest`, and have CI verify **generated contract test counts** and PASS status. Do not rely solely on shell command order; enforce the constraint in the task graph so other invocation paths are protected too.

**Question 3. Which version must the consumer use?**

In this exercise, Stub Runner must resolve:

~~~text
com.example:inventory-producer:1.2.0-rc.1:stubs
~~~

and run tests against the exact artifact from the verified producer commit.

**Question 4. Why might `--rerun-tasks` be needed in CI?**

If the consumer `test` task is considered up-to-date even though the Maven local artifact changed, Gradle may skip re-running tests. `--rerun-tasks --no-build-cache` is a short-term safeguard when testing candidates; a better long-term fix is immutable versions/digests and properly declared task inputs.

**Question 5. What if producer contract tests PASS yet consumer tests FAIL?**

This can indicate a breaking change for existing consumers, an incompatible matcher, a consumer client bug, or a mismatched stub artifact. Do not publish a new release if policy requires compatibility; cross-check the contract, implementation, generated test, stub, and consumer assertions.

### Extension Exercise: Adding a Pricing Module

Add `pricing-producer` to `settings.gradle` and design:

- Producer Inventory publishes `com.example:inventory-producer:...:stubs`.
- Producer Pricing publishes `com.example:pricing-producer:...:stubs`.
- Checkout uses Stub Runner to load **both artifacts** and resolves each producer's port separately.
- Consumer tasks run only after **both producer contracts** are verified and candidate stubs are ready.
- Avoid Gradle task cycles and avoid sharing one URL across both producers.
- CI records version/commit/digest for **each artifact**.

### Self-Check Questions

- Why is `project(':inventory-producer')` not equivalent to depending on `:stubs`?
- Why does Gradle `contractTest` in the producer differ from `test` in the consumer?
- Does `verifierStubsJar` need to be published explicitly via `maven-publish` in modern plugins?
- Why is `build/generated-test-sources/...` not the right place to edit test sources?
- When should a consumer use `LOCAL` versus `REMOTE`?
- Why does a green consumer test still require producer contract tests?
- If Gradle reports `UP-TO-DATE` when a stub artifact changes, what should you do?
- Why should multiple parallel CI jobs not share one mutable `SNAPSHOT`?

## 18. Configuration and Release Checklist

- [ ] Root `settings.gradle` declares all subprojects and compatible plugin versions.
- [ ] Producer owns Groovy/YAML DSL under `src/contractTest/resources/contracts` or a properly configured `contractsDslDir`.
- [ ] Producer Gradle plugin `org.springframework.cloud.contract` is applied to the right module.
- [ ] `testFramework` and base class match generated tests, classpath, and JUnit lifecycle.
- [ ] Generated contract tests are generated, compiled, and **actually executed**.
- [ ] `:inventory-producer:contractTest` PASSES with expected test count, not skipped/disabled.
- [ ] `verifierStubsJar` contains required mappings, contracts, and fixtures.
- [ ] `maven-publish` defines a publication including the stub JAR with classifier `stubs`.
- [ ] Publication tasks cannot run when producer contract tests fail.
- [ ] Consumer has **no** direct runtime dependency on the producer implementation just to run HTTP contract tests.
- [ ] Consumer includes `spring-cloud-starter-contract-stub-runner` on its test classpath.
- [ ] Stub Runner resolves the **exact candidate group/artifact/version/classifier**.
- [ ] Consumer's real HTTP client hits the stub URL/port, never calling real producer by mistake.
- [ ] Consumer tests assert fields, status codes, data types, and critical business behavior.
- [ ] Task dependencies or CI pipeline enforce one-way flow: producer -> artifact -> consumer.
- [ ] Artifacts and test reports carry traceable versions and commits/digests.
- [ ] Gradle cache/Maven local repository never causes stale stubs or skipped test runs.
- [ ] If messaging is added, test binders/triggers and async handler checks are properly designed.
- [ ] Breaking changes are reviewed against deployed consumers, not only the new contract.
- [ ] Release credentials exist only in authorized jobs after all quality gates pass.

## 19. Key Takeaways and References

**A well-designed Gradle multi-project build does not couple producer and consumer implementations; it orchestrates a chain of evidence:** Groovy/YAML contracts → generated producer tests → versioned stub artifact → Stub Runner → consumer tests using a real HTTP client. Gradle `contractTest` and `verifierStubsJar` are distinct steps; `publish` needs a quality gate, and `checkout-consumer:test` must load the exact right artifact.

With modern Spring Cloud Contract Gradle versions, pay close attention to the **`contractTest` source set** and the fact that **stub publications must be declared explicitly with `maven-publish`**. In CI, build candidate stubs after producer verification, supply the exact same revision to consumers, guard against stale caches, and block releases if any mandatory gate fails.

### References

- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): plugin, `contractTest` source set, `contractTest`/`verifierStubsJar` tasks, Gradle publishing, and external contracts.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): resolving stubs by coordinates and `LOCAL`/`REMOTE`/`CLASSPATH` modes.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): `@AutoConfigureStubRunner` and consumer test configuration.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): `settings.gradle`, `include`, project paths, and task dependencies.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): `MavenPublication` and publication tasks.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): how the build cache and task inputs/outputs affect test execution.

**Practical conclusion:** when multiple modules share Gradle, never stop at asking "is the build green?". Confirm that **producer tests ran and passed**, **stubs were published from the exact code/contract version**, and **consumer tests actually executed against that artifact**. Those three pieces of evidence enable CI to catch incompatible interface changes instead of giving a false sense of security from a false-green pipeline.
