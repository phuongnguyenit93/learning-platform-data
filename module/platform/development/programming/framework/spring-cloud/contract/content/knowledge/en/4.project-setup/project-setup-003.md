# Required Dependencies for Producer and Consumer

## Lesson Objectives

In the **Project Setup** chapter, this lesson guides you through choosing and configuring dependencies for both sides of **Spring Cloud Contract**:

- **Producer**: the service that exposes HTTP APIs or publishes messages, responsible for honoring agreed contracts and running tests generated from Groovy/YAML DSL.
- **Consumer**: the service that calls APIs or consumes messages, verifying its integration logic against **stubs** published by the producer, typically via **Spring Cloud Contract Stub Runner**.

After this lesson, you will be able to distinguish runtime application dependencies from test dependencies; configure Maven and Gradle basics; manage Spring Boot, Spring Cloud, and Spring Cloud Contract versions together; and integrate test generation, stub publishing, and consumer tests into CI.

> The configuration snippets below illustrate a **Spring Boot project** with existing application code. Spring Boot, the Spring Cloud release train, and Spring Cloud Contract versions must be chosen to be compatible with one another. This lesson uses version placeholders to avoid hardcoding a version set that may not fit your project.

## 1. What Components Do Both Sides Need?

Consider an example where **Inventory Service** provides a stock API and **Checkout Service** calls that API:

~~~mermaid
flowchart LR
    C["Checkout Service<br/>consumer"] -->|"GET /api/inventory/SKU-101"| P["Inventory Service<br/>producer"]
    K["Contract<br/>Groovy / YAML DSL"] --> G["Generate contract test"]
    K --> S["Generate HTTP stub"]
    G --> P
    S --> R["Stub Runner"]
    R --> T["Consumer integration test"]
    T --> C
~~~

In the testing flow, the producer is verified using **generated contract tests**, and the consumer is verified by calling an **HTTP stub** that simulates the exact behavior described in the contract. These two flows complement each other and do not completely replace end-to-end integration testing.

| Component | Used Where | Role | Typical Dependency Scope |
|---|---|---|---|
| `spring-boot-starter-test` | Producer and consumer | JUnit, assertion utilities, and Spring Boot Test support | Maven `test` / Gradle `testImplementation` |
| `spring-cloud-starter-contract-verifier` | Producer | Supports contract tests generated from DSL | Maven `test` / Gradle `testImplementation` |
| `spring-cloud-contract-maven-plugin` | Producer using Maven | Generates tests and stubs, integrates them into the build lifecycle | Maven **build plugin** |
| `org.springframework.cloud.contract` Gradle plugin | Producer using Gradle | Generates tests and packages stubs during the build | Gradle **plugin**, not a runtime dependency |
| `spring-cloud-starter-contract-stub-runner` | Consumer | Locates, downloads, and starts stubs for tests | Maven `test` / Gradle `testImplementation` |
| `spring-cloud-dependencies` BOM | Modules using Spring Cloud | Manages compatible versions across Spring Cloud libraries | Maven `dependencyManagement` / Gradle `platform` or dependency management |
| `spring-boot-starter-web` or matching HTTP stack | HTTP producer; consumer if actually needed | Provides HTTP server/client per application architecture | Runtime/implementation, as needed |

**Principle:** Contract verifier and Stub Runner libraries exist for **build/test**. Applications deployed to production normally **do not** carry them as runtime dependencies. By contrast, the consumer's real HTTP client (for example `RestClient`, `WebClient`, or OpenFeign) still requires dependencies matching the technology the application uses.

## 2. Aligning Spring Boot, Spring Cloud, and Contract Versions

A common setup mistake is choosing these three versions independently without checking the Spring Cloud compatibility matrix. Libraries may still download cleanly yet fail when starting tests or generating tests due to API changes in Spring Boot, Spring Framework, JUnit, or related libraries.

Version selection workflow:

1. **Lock in the Spring Boot version** for your producer and consumer projects.
2. **Select the Spring Cloud release train** compatible with that Boot version, based on the documentation/compatibility matrix for your target release.
3. **Import the `spring-cloud-dependencies` BOM** so Spring Cloud starters inherit versions managed by the release train.
4. **Set the Spring Cloud Contract build plugin version** to match the Spring Cloud Contract line managed by the BOM; the library BOM does not automatically manage the Maven/Gradle plugin version.
5. **Verify effective resolved versions** in the build, especially when multiple modules or BOMs participate in dependency management.

Do not take the **release train version number** and assign it directly as the **Maven plugin version**. A Spring Cloud release train name and a Spring Cloud Contract artifact version do not necessarily match.

### Shared BOM Configuration for Maven

For projects already using the Spring Boot parent or Spring Boot BOM, add the following to your parent/root `pom.xml`:

~~~xml
<properties>
    <!-- Replace with the release train compatible with your project's Spring Boot version -->
    <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>

    <!-- Replace with the Spring Cloud Contract version matching the BOM above -->
    <spring-cloud-contract.version>REPLACE_WITH_MATCHING_CONTRACT_VERSION</spring-cloud-contract.version>
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
~~~

The two values starting with `REPLACE_WITH_` are **placeholders to fill in**, not versions downloadable from a Maven Repository. If the project already imports the BOM in the parent POM, you do not need to re-import it in every submodule. Under `dependencyManagement`, the BOM supplies starter versions, so `<version>` is normally omitted on individual Spring Cloud dependencies.

The **Maven plugin** still needs its own managed version; define `spring-cloud-contract.version` at the root and reference it in the plugin configuration below.

### Shared BOM Configuration for Gradle

Example using Gradle Groovy DSL with the BOM imported via `platform`:

~~~groovy
ext {
    springCloudVersion = 'REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN'
}

dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    testImplementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
}
~~~

This snippet covers dependency management only—it is **not** a complete `build.gradle`: the project still needs the Spring Boot plugin, Java plugin, repositories, and standard application dependencies.

In multi-module builds, ensure both producer and consumer modules receive the appropriate BOM; applying `platform` only in another module without applying it to the active module can leave test dependencies unversioned. Some projects use the `io.spring.dependency-management` plugin instead of `platform`; pick one approach consistent with your existing build.

## 3. Maven: Producer Dependencies and Plugin

Assume the producer is a Spring Boot MVC application named `inventory-producer`. At minimum, the producer module needs the application's HTTP serving stack, testing libraries, and the **contract verifier**:

~~~xml
<dependencies>
    <!-- For synchronous HTTP APIs with Spring MVC -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Used when generating and running producer-side contract tests -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-verifier</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Add the Maven plugin to process contracts within the build lifecycle:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>${spring-cloud-contract.version}</version>
            <extensions>true</extensions>
            <configuration>
                <baseClassForTests>com.example.inventory.contract.ContractTestBase</baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`baseClassForTests` is an example path to a **test base class created by the project**. That class must set up the proper HTTP test environment and prepare any required stubbed data or mock services so generated tests run reliably. Do not add this configuration while leaving the class missing or empty: generated tests may fail to compile or fail to run. If your project follows a different base-class convention, adjust it to match your test layout.

Contract files are commonly stored at:

~~~text
inventory-producer/
├── pom.xml
└── src/
    └── test/
        ├── java/
        │   └── com/example/inventory/contract/ContractTestBase.java
        └── resources/
            └── contracts/
                └── inventory/
                    └── shouldReturnStock.groovy
~~~

Example minimal Groovy contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Get stock availability for a known SKU'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 12
        )
    }
}
~~~

When the plugin is configured properly, the build **generates tests from contracts**, runs them against the producer application configured for testing, and **produces the corresponding stub**. Values such as `SKU-101`, `true`, and `12` are sample scenarios; for dynamic data, use Spring Cloud Contract matchers rather than always matching literals verbatim.

**Running on a developer machine:**

~~~bash
./mvnw clean verify
~~~

This command executes the testing and packaging phases according to the configured lifecycle. For the producer to publish the artifact together with its stub into the local Maven repository so the consumer can test in LOCAL mode, run:

~~~bash
./mvnw clean install
~~~

A properly configured producer build typically produces a stub artifact carrying the **`stubs` classifier**, for example `com.example:inventory-producer:1.0.0:stubs`. Exact versioning and artifact coordinates depend on your project's `groupId`, `artifactId`, and `version`. Only treat a stub as trustworthy after producer contract tests have passed.

## 4. Maven: Consumer Dependencies

Consumer `checkout-consumer` needs the HTTP client library appropriate for the application and the **Stub Runner** dependency in test scope.

Example if using Spring Boot with existing code calling Inventory Service:

~~~xml
<dependencies>
    <!-- Depends on your application's client; here is a Spring Boot MVC example -->
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
        <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The consumer **does not need** `spring-cloud-starter-contract-verifier` just to invoke stubs with Stub Runner. Nor does a consumer module need the Spring Cloud Contract Maven plugin if it is not generating contract tests or stubs.

### How Does the Consumer Fetch Stubs?

Stub Runner uses the producer's artifact coordinates to locate the stub. An example consumer test configuration:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest(properties = {
    "inventory.base-url=http://localhost:10000"
})
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:10000",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryClientContractTest {

    @Test
    void checkoutUnderstandsInventoryResponse() {
        // Call the consumer's real InventoryClient with
        // the base URL pointed to the stub at localhost:10000.
        // Assert the consumer's response-handling logic here.
    }
}
~~~

What this configuration means:

- `ids` follows the general pattern `groupId:artifactId:version:classifier:port`; here `stubs` is the classifier and `10000` is the stub port for the test.
- `LOCAL` searches for the stub artifact in the test environment's local Maven repository. Therefore, you must **build and install the producer first** or ensure the artifact is already in the local repository.
- `inventory.base-url` is only an **illustrative property name**: it must match the real property read by `InventoryClient`. If the client uses a hardcoded URL or another configuration key, the test is not hitting the stub yet.
- The `@Test` body is intentionally reserved for assertions exercising the **real client**. A test that merely calls the stub directly and checks that the stub returns the expected JSON does not verify that consumer logic handles the payload properly.

In CI, each job may have its own isolated local Maven repository. Never assume a stub installed via `mvn install` in one job automatically appears in another. Either chain jobs within a shared workspace/repository or publish stubs to an artifact repository accessible to the consumer.

### When Stubs Must Be Fetched from an Artifact Repository

Instead of `LOCAL`, use the mode that fetches stubs from a configured repository (commonly `REMOTE`). Set the repository location using the corresponding Stub Runner property, such as `spring.cloud.contract.stubrunner.repositoryRoot`, and configure credentials using your build system's secure secret mechanism.

Never place passwords or tokens directly inside `pom.xml`, test sources, or configuration files committed to Git. When services belong to different teams, a shared artifact repository with clear versioning lets pipelines consume exact verified stubs.

## 5. Gradle: Equivalent Setup

If the project uses Gradle Groovy DSL, the producer needs the Spring Cloud Contract **plugin** and the verifier in test scope. The template below illustrates the required pieces; placeholders must be replaced with chosen compatible versions:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_BOOT_VERSION'
    id 'org.springframework.cloud.contract' version 'REPLACE_WITH_CONTRACT_PLUGIN_VERSION'
}

repositories {
    mavenCentral()
}

def springCloudVersion = 'REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN'

dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    testImplementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}

contracts {
    baseClassForTests = 'com.example.inventory.contract.ContractTestBase'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Gradle plugin provides tasks for contract test generation and stub packaging. **Exact task names and build lifecycle wiring can vary by plugin line**; inspect the tasks actually registered in your project and make sure generated tests run before publishing stubs.

On the Gradle consumer side, assuming `org.springframework.boot` and `java` plugins along with a compatible BOM setup are already present:

~~~groovy
dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    testImplementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
}
~~~

In Gradle, `testImplementation` keeps Stub Runner and the verifier off the normal application runtime classpath. Just as with Maven, ensure stubs can be resolved and configure the consumer client to hit the stub port during tests.

**Plugin version note:** `id 'org.springframework.cloud.contract' version '...'` expects the Gradle plugin version, not `springCloudVersion`. Do not assign the same number to both without checking the release train versions.

## 6. Choosing Dependencies by Contract Type: HTTP or Messaging?

Spring Cloud Contract can describe **HTTP** interactions using Groovy/YAML DSL and also verify **messaging** interactions. However, business dependencies differ depending on the communication style.

| Communication Type | What Does the Producer Add? | What Does the Consumer Add? | What Stays the Same? |
|---|---|---|---|
| HTTP with Spring MVC | Web starter or matching HTTP server stack | Actual HTTP client in use | Contract verifier + plugin on producer, Stub Runner in consumer tests |
| HTTP with WebFlux | WebFlux starter and matching test mode config | WebClient or suitable client | BOM management, DSL, two-sided testing |
| HTTP via OpenFeign | Producer still uses its own HTTP stack | OpenFeign dependency if the app uses Feign | Stub Runner remains a consumer test dependency |
| Messaging (Kafka/RabbitMQ, Spring Cloud Stream, or another library) | Appropriate binder/broker or messaging library and contract test setup capable of triggering/observing messages | Appropriate message-receiving library; test setup able to simulate receiving events | Producer/consumer mindset, contracts, and behavior verification requirements |

**Do not add Kafka, RabbitMQ, Stream binders, or Rest Assured to every module just because you use Spring Cloud Contract.** Only add dependencies needed for the actual interaction style and test setup.

For messaging, a stub is not necessarily an HTTP server like in the examples above. Test generation, message destination configuration, triggers, and mock infrastructure must match how your app emits and consumes events. Producers should describe payloads and headers meaningful to consumers; guarantees like message ordering, retries, or duplicate delivery must be tested separately if business logic depends on them.

## 7. End-to-End Flow from Producer to Consumer

Here is a practical sequence for a first HTTP integration:

~~~mermaid
sequenceDiagram
    participant Dev as Developer / CI
    participant Prod as Producer build
    participant Repo as Stub repository
    participant Cons as Consumer test
    Dev->>Prod: Configure BOM, verifier, and Contract plugin
    Dev->>Prod: Commit Groovy/YAML contracts
    Prod->>Prod: Generate and run contract tests
    alt Producer tests succeed
        Prod->>Repo: Package and publish :stubs artifact
        Repo-->>Cons: Fetch exact stub version
        Cons->>Cons: Stub Runner starts stub
        Cons->>Cons: Run tests with real consumer client
    else Producer tests fail
        Prod-->>Dev: Report contract mismatch, stop release
    end
~~~

1. **Prepare the producer:** working application, valid test base class, matching BOM, verifier, and test/stub generation plugin.
2. **Author contracts:** e.g., `GET /api/inventory/SKU-101` returning `200` with JSON, plus a `404` case for a missing SKU.
3. **Run producer tests:** verify generated tests compile, execute, and verify the implementation against the contract.
4. **Package the stub:** publish the stub alongside the producer version. Locally, Maven can run `./mvnw clean install`; in CI, publish to the target repository.
5. **Prepare the consumer:** add the Stub Runner test dependency, specify the exact artifact and version, and point the client base URL to the stub.
6. **Run consumer tests:** verify the consumer sends requests and handles successful responses, empty data, errors, and any behaviors the consumer truly relies on.
7. **Integrate into CI:** run producer checks before stub publishing; consumer pipelines consume the verified stub version rather than accidentally pulling an outdated release.

If you use `+` or a version range in stub coordinates, understand how version resolution works and its impact on CI reproducibility. For reproducible builds, **pinning an explicit stub version** makes it much easier to trace why a run passed or failed.

## 8. Common Dependency Errors and How to Troubleshoot

| Symptom | Common Cause | How to Fix |
|---|---|---|
| Maven/Gradle plugin not found | Wrong plugin ID, group/artifact, or version; missing plugin repository | Check plugin coordinates, version, and allowed repositories |
| `NoClassDefFoundError`, `NoSuchMethodError` during test generation/run | Conflict or version mismatch across Boot/Cloud/Contract | Inspect dependency graph, BOM, plugin version, and overrides |
| Generated tests do not appear | Plugin not applied, contracts in wrong directory, or task/goal never ran | Inspect build logs, contract path, and configured tasks/goals |
| Generated tests exist but fail to compile | Missing test base class, imports, or test dependencies | Check class name, package, test framework, and test scope |
| Producer contract test fails even though endpoint exists | Test data, status, headers, body, or matchers mismatch | Compare the exact request/response checked by the generated test |
| Stub Runner cannot find `:stubs` | Producer never published stub, wrong `groupId`/`artifactId`/version/classifier, or wrong LOCAL/REMOTE mode | Verify artifact coordinates and actual repository contents |
| Consumer test hits the real producer | Client URL was not redirected to the stub port | Point the client's base URL to the Stub Runner port |
| Consumer tests pass while real deployment fails | Stale stub; producer skipped generated tests; missing contract scenarios | Sync versions, verify both sides, and add missing contract cases |
| Production build bundles test dependencies | Verifier or Stub Runner placed in runtime/implementation scope | Move to `test` / `testImplementation` |

In Maven, useful diagnostic commands include:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

In Gradle:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew tasks --all
~~~

These are **reference commands for learners to run** in their projects; they do not automatically prove every contract or every version is correct. Inspect the resolved dependencies and tasks directly, especially when multiple BOMs, plugins, or custom test configurations are present.

## 9. Practice: Identify Missing Configuration

A team has a Spring Boot producer whose `GET /api/inventory/{sku}` endpoint works when tested manually. They add `shouldReturnStock.groovy` under `src/test/resources/contracts` and notice:

- Running `./mvnw test` produces no generated contract tests;
- the consumer added `spring-cloud-starter-contract-verifier` yet cannot run stubs;
- the consumer pipeline keeps pulling an old artifact version;
- the producer returned the wrong data type for `quantity`, yet nothing failed.

Compare this against what you have learned:

1. **What is the producer missing?** Check the Spring Cloud Contract Maven plugin and its lifecycle integration, test verifier, base class, and test configuration. Having a Groovy file alone does not guarantee tests are generated and run.
2. **What should the consumer add?** `spring-cloud-starter-contract-stub-runner` in test scope; point to a stub artifact published by the producer and write tests calling the real client.
3. **What needs to change in CI?** Run generated tests before publishing stubs; have the consumer use the exact coordinates and version of the verified stub.
4. **How is a type change on `quantity` caught?** Specify the type in the contract/appropriate matcher; producer tests verify the response carries a number as agreed, while consumer tests against the corresponding stub verify client deserialization and handling.

### Self-Check

- Why does the producer need the **test-generation plugin** while the consumer mainly needs **Stub Runner**?
- Why is `spring-cloud-starter-contract-verifier` usually placed in `test` scope?
- Does the Spring Cloud BOM automatically set the version of the Maven/Gradle Contract plugin?
- Why can't `LOCAL` mode find a stub if the producer has not installed the artifact in that environment?
- If both pipelines are green yet use two different stub versions, what risk remains?

## Key Takeaway

Integrating **Spring Cloud Contract** requires aligning three parts: **compatible versions**, **producer tooling to generate/run tests and publish stubs**, and **consumer tests using Stub Runner with the exact stub version to test the real client**. Separating runtime dependencies from test dependencies keeps builds clean with clear responsibilities. When CI runs the verification chain in order and manages stub versions consistently, incompatible API or message changes are caught far earlier.
