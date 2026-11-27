# Choosing a Compatible Spring Boot and Spring Cloud Release Train

## 1. Objectives and Problem to Solve

**Spring Cloud Contract (SCC)** supports contract testing between a **producer** (a service that provides APIs or publishes messages) and a **consumer** (a service that calls APIs or consumes messages). In a Spring Boot project, you can define HTTP or messaging behavior using **Groovy DSL/YAML DSL**, generate producer-side tests, package stubs, run **Stub Runner** on the consumer side, and integrate verification steps into CI to catch incompatible changes.

Before creating your first contract, you must select a **set of versions** that work together. If you simply pick the latest Spring Boot release and add an arbitrary Spring Cloud Contract version, the project can fail at startup, fail to generate tests, fail to run the plugin, or generate stubs with a different library version than the consumer expects.

This lesson answers the question: **How do you choose compatible Spring Boot, Spring Cloud Release Train, and Spring Cloud Contract versions, declare them properly, and verify that choice?**

After completing this lesson, you should be able to:

1. Distinguish between **Spring Boot**, **Spring Cloud Release Train**, and **Spring Cloud Contract** versions.
2. Read the compatibility matrix and support policy before locking in versions.
3. Configure the Spring Cloud BOM, dependencies, and build plugins for Maven or Gradle.
4. Verify resolved dependencies, generated contract tests, and stub artifacts.
5. Recognize version-mismatch errors and plan a controlled upgrade.

## 2. The Three Version Layers You Must Understand

| Layer | Example Name or Coordinates | What Does It Determine? | How Is It Managed? |
|---|---|---|---|
| **Spring Boot** | `org.springframework.boot:spring-boot-starter-parent`, plugin `org.springframework.boot` | Application foundation, Spring Framework, starters, core libraries, and Java/build tool requirements | Select a specific Boot version, typically via parent or plugin |
| **Spring Cloud Release Train** | `org.springframework.cloud:spring-cloud-dependencies` | The set of Spring Cloud versions coordinated and tested against a Spring Boot release line | Import the **BOM** for the matching release train |
| **Spring Cloud Contract** | `spring-cloud-starter-contract-verifier`, `spring-cloud-starter-contract-stub-runner`, SCC plugin | DSL, producer test generation, stub generation/consumption, and running Stub Runner | Dependencies via BOM; **build plugin has its own version** |

A **Release Train** is a **coordinated set of versions** across Spring Cloud projects released and tested together, for example named in the format `2025.0.x`. It is not the version number of Spring Boot or Spring Cloud Contract. Spring Cloud Contract has its own module version number, such as `4.x.y`, and belongs to a corresponding release train.

A proper setup can be visualized as follows:

~~~mermaid
flowchart TD
    B["Selected Spring Boot"] --> C["Choose compatible Spring Cloud Release Train"]
    C --> D["Import spring-cloud-dependencies BOM"]
    D --> E["Contract Verifier / Stub Runner dependencies"]
    C --> F["Determine matching Contract build plugin version"]
    E --> G["Run generated producer tests and consumer stub tests"]
    F --> G
    B --> G
~~~

A **BOM (Bill of Materials)** is a mechanism for managing coordinated dependency versions. Importing the Spring Cloud BOM typically lets you declare Spring Cloud dependencies **without specifying a version on each dependency**. However, **Maven build plugins** are not automatically versioned by `dependencyManagement`, and the Gradle plugin also uses its own version declaration. Therefore, having the right BOM while using the wrong SCC plugin line can still cause failures.

Beyond these three layers, there are **Java**, Maven/Gradle, testing framework versions (JUnit, MockMvc, WebTestClient, etc.), and major platform shifts such as `javax.*` to `jakarta.*`. These must be treated as input constraints when selecting versions, especially when crossing a Spring Boot major version.

## 3. Choosing a Release Train in the Right Order

Do not start by arbitrarily adding dependencies and letting the build tool pick a "close enough" version. A verifiable selection workflow is:

**Step 1 — Identify the target Spring Boot version.** Check the version the application currently uses, the Java runtime, Maven/Gradle, key libraries, and operational requirements. For a new project, choose a Boot release line that remains supported throughout your expected deployment lifecycle; for an existing project, assess the scope of changes required if upgrading Boot.

**Step 2 — Check the official Spring Cloud ↔ Spring Boot compatibility table.** On the Spring Cloud project page and the Supported Versions page, find the release train that supports the **selected Boot line**. You must verify both **technical compatibility** and **support/maintenance status** at the time of your project.

**Step 3 — Lock in specific patch versions on both sides.** Choose an actual Boot patch version and Spring Cloud train patch version that align with your team's policy. Record them in your build configuration, not just as "Boot 3.x" or "Cloud 2025.x" in operational docs.

**Step 4 — Identify the Spring Cloud Contract version in that train.** Read the selected BOM or release notes to confirm the managed SCC library version. For the Contract Maven/Gradle plugin, pick the plugin version from the same release line corresponding to the resolved verifier version. Never guess the plugin version solely from the Boot version number.

**Step 5 — Run real verification.** Resolve dependencies, run the application or an appropriate slice test, generate a producer test from a minimal contract, run the test, and package the stub. A version set is only considered verified for a project when the actual build succeeds.

### Common Version Mapping Examples

| Spring Cloud Release Train | Associated Spring Boot Line | Purpose of This Reference |
|---|---|---|
| `2023.0.x` | `3.2.x`, `3.3.x` | Identify an earlier version set in a project under maintenance |
| `2024.0.x` | `3.4.x` | Example of a release train/Boot pair |
| `2025.0.x` | `3.5.x` | Example of a release train/Boot pair |

**Note on time sensitivity:** The table above provides **examples of known release-line relationships**, not a table of "latest versions" or a guarantee that those lines are still supported when you read this. Spring Boot and Spring Cloud continue to ship new releases, and older release trains eventually reach end of support. For newer Boot majors, always consult the **current compatibility matrix** instead of extrapolating from the year number or forcing an old train.

Reference sources for your project:

- **Spring Cloud:** https://spring.io/projects/spring-cloud — project page and links to release trains.
- **Spring Cloud Supported Versions:** https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions — compatibility matrix and support lifecycle.
- **Spring Boot:** https://spring.io/projects/spring-boot — releases, documentation, and environment requirements.
- **Spring Cloud Contract Reference:** https://docs.spring.io/spring-cloud-contract/reference/ — version-specific documentation on integrating the verifier, plugin, and Stub Runner.

If documentation for an older release differs from the current compatibility matrix, clarify whether you are checking a **historical version** or a **target version**, and prioritize the release notes and documentation for that specific release line.

## 4. Example of a Documented Version Decision

Suppose a team is developing **inventory-service** (producer) and **checkout-service** (consumer), using Java 17 and looking to adopt Spring Cloud Contract on the Spring Boot 3.5 line.

An **illustrative version set for reading the configuration** is:

~~~text
Java runtime:                 17
Spring Boot:                  3.5.0
Spring Cloud Release Train:   2025.0.0
Spring Cloud Contract plugin: 4.3.0
~~~

This is an **illustrative version set for the 2025.0 line** in this lesson, **not a recommendation that these are the latest patches or still under support**. Before copying them into an active project, check current patch releases, verify that the plugin version matches the SCC version managed by the BOM, and substitute your approved patches.

The team should record a short decision note:

| Criterion | Question to Answer |
|---|---|
| Java | Do local runtimes and CI toolchains meet the minimum required by the target Boot version? |
| Spring Boot | Is the chosen line/patch supported for the expected operational window? |
| Spring Cloud | Does official documentation confirm that the release train supports the target Boot version? |
| Contract libraries | What exact version of verifier and Stub Runner does the BOM manage? |
| Contract plugin | Is the plugin version from the same release line as the Contract libraries? |
| Build | Do Maven/Gradle, JUnit, test base, and DSL work on the existing setup? |
| Artifacts | Does CI build and publish the right stub version for consumers? |

Recording this decision is especially valuable when a platform upgrade PR arrives months later, or when producer and consumer upgrade on different schedules.

## 5. Setting Up Maven with the Spring Cloud BOM

In Maven, a common approach is to let the **Spring Boot parent** manage foundational dependencies and import the **Spring Cloud BOM** inside `dependencyManagement`. Spring Cloud starters are then declared **without a version**; Maven resolves them via the BOM.

Example `pom.xml` on the producer side, using the illustrative version set from the previous section:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>inventory-service</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.0.0</spring-cloud.version>
        <!-- Verify the plugin version against the BOM before applying. -->
        <spring-cloud-contract.plugin.version>4.3.0</spring-cloud-contract.plugin.version>
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
                <version>${spring-cloud-contract.plugin.version}</version>
                <extensions>true</extensions>
                <configuration>
                    <baseClassForTests>com.example.inventory.ContractTestBase</baseClassForTests>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Two values to cross-check during upgrades:** `spring-cloud.version` and `spring-cloud-contract.plugin.version`, if a newer BOM moves Contract to a different release line. The example declares each value once in `properties` and references it in both the BOM and the plugin, avoiding duplicated literals that are easy to forget to update.

### Why Specify Both the BOM and the Maven Plugin Version?

Maven `dependencyManagement` manages **project dependencies**. The `spring-cloud-contract-maven-plugin` lives under `build/plugins`, so its version must be configured through plugin management. The Spring Cloud BOM **does not guarantee** that the right plugin version is chosen automatically. On the other hand, you normally **do not** need to specify a version for `spring-cloud-starter-contract-verifier` when the BOM manages that dependency.

If your organization already uses a custom parent POM, you can still import the Spring Cloud BOM inside `dependencyManagement`; you do not have to replace the company parent with the Spring Boot parent. In that case, also check how your existing parent manages Boot dependencies, plugins, and BOM precedence order.

### Base Class for Generated Producer Tests

SCC needs to know how generated tests should invoke your application. The `baseClassForTests` value in the example points to a test class you create under test sources, which can set up MockMvc, WebTestClient, RestAssured, or test data. Example using **MockMvc and RestAssuredMockMvc** (once the appropriate test libraries are on the classpath):

~~~java
package com.example.inventory;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.web.context.WebApplicationContext;

@SpringBootTest
public abstract class ContractTestBase {

    @Autowired
    WebApplicationContext context;

    @BeforeEach
    void setupContractTests() {
        RestAssuredMockMvc.webAppContextSetup(context);
    }
}
~~~

The base class does not define contracts; it provides the **runtime context so generated tests can execute**. Make sure you pick the matching test mode and compatible libraries in the plugin configuration. Contract DSL files live separately, typically under `src/test/resources/contracts/`.

## 6. Setting Up Gradle with the Plugin and BOM

In Gradle, Spring Boot and Spring Cloud Contract are typically declared via **plugins**, while the Spring Cloud BOM is imported through the `io.spring.dependency-management` plugin or whichever dependency platform mechanism the project uses.

Example **Groovy DSL** `build.gradle`, using the same illustrative version set:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'org.springframework.cloud.contract' version '4.3.0'
}

group = 'com.example'
version = '1.0.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.cloud:spring-cloud-dependencies:2025.0.0'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}

contracts {
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is an example of **how configuration pieces fit together**, not a lockfile for a production app. For projects using **Gradle Kotlin DSL**, version catalogs, plugin management, or native Gradle platforms, the syntax and BOM placement will differ; the rule remains **a single, consistently decided and verified Boot–Cloud–Contract version set**.

If you do not use the `io.spring.dependency-management` plugin, explicitly declare `platform("org.springframework.cloud:spring-cloud-dependencies:<train-version>")` in the relevant configurations. Avoid mixing multiple version management mechanisms without verifying the actual resolved output.

### Common Gradle Mistakes

- Declaring the right `spring-cloud-dependencies` BOM while the `org.springframework.cloud.contract` plugin is on a different release line.
- Applying the BOM to `implementation` but missing version constraints on `testImplementation`, causing test dependencies to resolve to unexpected versions.
- Using `resolutionStrategy.force` or a version catalog to pin a Spring Cloud library outside the BOM without a clear compatibility reason.
- Not applying the Java or Spring Boot plugin, or using versions incompatible with the running Gradle version.
- Declaring a Java 17 toolchain when the CI runner cannot download or locate a compatible JDK.

## 7. Consumer Configuration: Stub Runner Must Belong to the Same Ecosystem

The producer uses **Contract Verifier** to generate and run tests. The consumer uses **Stub Runner** to fetch and run producer stubs, usually in test scope only.

Example addition to the consumer's `pom.xml` when the project already uses a compatible Spring Cloud BOM:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
    <scope>test</scope>
</dependency>
~~~

Or in Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
}
~~~

Normally, do not include Stub Runner in `implementation`/production runtime if it is only used for integration tests. Producer and consumer **do not have to share every application library version**, but each side needs its own compatible Boot–Cloud stack; at the same time, the stub format/protocol, artifact coordinates, and tests must be compatible with the consumer side.

For example, the producer builds:

~~~text
com.example:inventory-service:1.1.0-rc1:stubs
~~~

The consumer must know the exact **groupId, artifactId, version, and classifier** of the candidate stub so it does not pick up a stale version. Having a valid BOM only solves library foundations; it does not confirm that the consumer pulled the **right stub for the candidate commit**.

## 8. Verifying with Build Commands: Inspect What Actually Resolved

After choosing a version set and declaring dependencies, the next step is to **inspect what the build tool actually downloads**. Simply reading the POM or Gradle script is not enough, because parents, BOMs, transitive dependencies, and override rules can alter the outcome.

### With Maven

On Unix/macOS use `./mvnw`; on Windows you can use `mvnw.cmd`. Key commands:

~~~bash
# Check the JDK and Maven Wrapper version in use.
./mvnw --version

# Inspect the effective POM after merging parent, BOM, and plugin configurations.
./mvnw help:effective-pom

# Inspect the Spring Cloud dependencies that actually resolved.
./mvnw dependency:tree -Dincludes=org.springframework.cloud

# Run the build/test lifecycle associated with Contract Verifier.
./mvnw clean verify
~~~

When reading the output, confirm that:

1. **Spring Boot** comes from the parent or dependency management at the exact version selected.
2. **Spring Cloud Contract** dependencies belong to the release line intended by the BOM; avoid multiple conflicting SCC versions caused by manual declarations.
3. The Contract **Maven plugin** picked the intended version; check the effective POM rather than only the dependency tree.
4. **Generated contract tests** were created and executed by the test runner, instead of a green build simply because no contracts existed.
5. The build has no classloading/`NoSuchMethodError`/`NoClassDefFoundError` issues, and controllers or message handlers are invoked properly.

The generated sources path depends on the plugin and build configuration. In Maven, generated contract tests usually appear under `target/generated-test-sources/contracts/`. Rely on the plugin logs and your project's actual output directory.

### With Gradle

~~~bash
# Check the Gradle and JVM versions in use.
./gradlew --version

# Inspect the test dependency graph.
./gradlew dependencies --configuration testRuntimeClasspath

# Find the specific Spring Cloud Contract dependency and where its version comes from.
./gradlew dependencyInsight --dependency spring-cloud-contract-verifier --configuration testRuntimeClasspath

# List tasks provided by the Contract plugin.
./gradlew tasks --all

# Run tests, including generated contract tests if the plugin is wired properly.
./gradlew clean test
~~~

On Windows you can use `gradlew.bat`. Exact task names and output may vary by plugin version; use the task list and build logs to verify. **Do not assume contract tests ran just because the test command exited with 0.**

## 9. Minimal Verification: From Contract to Generated Test

You can use a simple HTTP endpoint to confirm the foundation is set up properly before writing contracts for the entire API.

Suppose `inventory-service` exposes:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Expected response:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

Illustrative Groovy DSL file at `src/test/resources/contracts/inventory/shouldReturnStock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Return stock availability so checkout can decide whether to place the order'
    request {
        method GET()
        url '/api/inventory/SKU-123'
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

A project using **YAML DSL** can express the same behavior in YAML instead of Groovy:

~~~yaml
description: Return stock availability so checkout can decide whether to place the order
request:
  method: GET
  url: /api/inventory/SKU-123
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

For this check to be meaningful, the producer must **actually implement the endpoint**, and the test base class must wire generated tests to the right application context. When running Maven `verify` or Gradle `test`, look for the generated test containing status/body assertions and check its execution result. If the implementation does not exist yet, the test is expected to fail; that proves the plugin and test runner are working, **not a version compatibility error**.

Once producer tests pass, the build can produce a **stub artifact**. The exact packaging/publishing command depends on the plugin and pipeline; locally, verify that the `stubs` artifact is produced with the right coordinates. The consumer points Stub Runner to this artifact to test API calls or message handling against the contract.

### When Testing Message Contracts

For Kafka, RabbitMQ, or Spring Cloud Stream, the same versioning process applies: choose a compatible Boot–Cloud–Contract stack, configure the appropriate messaging adapter/test binder, write input/output message contracts, and run generated verification. With messaging, you must also check serialization versions, headers, topics/destinations, and test infrastructure; the SCC plugin running alone is not enough to conclude that production broker interactions are verified.

## 10. Spring Cloud Compatibility Verifier and Version Mismatch Errors

Some Spring Cloud setups include a **Compatibility Verifier** that checks the running Spring Boot line against the Spring Cloud release train. When mismatched, the application may fail at startup with an error like:

~~~text
Spring Boot [X] is not compatible with this Spring Cloud release train
~~~

The message may suggest which Boot lines are supported. Treat this as a configuration signal that needs to be fixed, not a random developer-machine glitch.

For instance, if an app upgraded to Boot 3.5.x while still importing a release train built for Boot 3.4.x, dependencies might still resolve, yet the app fails to boot or hits API errors during tests. **The right fix** is to select a Boot–Cloud pair inside the compatibility matrix and update the corresponding Contract plugin.

Some online guides suggest disabling the check via configuration:

~~~properties
spring.cloud.compatibility-verifier.enabled=false
~~~

This is **not a compatibility fix**. Disabling the verifier only bypasses a startup check—it does not change the classpath, APIs, or runtime compatibility of the libraries. Never use this to "turn CI green" without confirming the root cause and the compatibility of the version set.

## 11. Version Selection Failures and How to Diagnose Them

| Symptom | Likely Cause | How to Check / Fix |
|---|---|---|
| App reports Boot is incompatible with Cloud train | Wrong Boot–Cloud pair selected | Check Supported Versions table and switch the release train or Boot version |
| `NoSuchMethodError` / `NoClassDefFoundError` when running generated tests | Spring/Contract library mismatch, dependency override, or mismatched plugin | Inspect dependency tree/insight, effective POM, and plugin version |
| Build is green but no contract tests were generated | Plugin not enabled, DSL placed in wrong folder, or build skipped required lifecycle/task | Check plugin tasks, test generation logs, and source output directory |
| Maven resolves one Contract verifier version while plugin uses another | BOM only manages dependencies; plugin is pinned separately | Align the plugin version with the actual Contract library line |
| Gradle resolves test dependencies outside the BOM | BOM applied only to certain configurations, or overridden by version catalog/force | Inspect `testRuntimeClasspath` using `dependencyInsight` |
| Compilation fails on `javax.*` or `jakarta.*` imports | Major Spring Boot/Framework upgrade and API namespace migration | Review migration requirements for the target Boot line |
| Build passes locally but fails in CI | Different Java/Gradle/Maven, local Maven cache, plugin repository, or profile | Pin toolchain/wrapper, use a reproducible build environment, and check logs |
| Stub Runner cannot fetch artifact | Stub not published/installed to repository, wrong classifier/version, or wrong LOCAL/REMOTE mode | Verify artifact coordinates, repository source, permissions, and candidate version |
| Producer contracts pass but consumer breaks after API change | New contract fits producer but breaks existing consumer expectations | Run consumer tests against the **candidate** stub; consider expand–migrate–contract |

Troubleshooting in the order **platform → resolved dependencies → Contract plugin → generated tests → stub artifact → consumer tests** helps avoid mistaking dependency compatibility issues for contract content bugs.

## 12. Controlled Upgrades of Spring Boot and Spring Cloud Contract

When upgrading Spring Boot, do not just bump a single number and hope old dependencies keep working. A practical upgrade workflow includes:

1. **Record the starting state:** current Boot version, Cloud train, Contract dependency/plugin, Java, build tool, test reports, and stub coordinates.
2. **Choose the target from the official matrix:** check support windows, Java, build tool, and major changes in Spring Framework and Contract.
3. **Update the version set together in configuration:** update Boot, Cloud BOM, Contract plugin, and any related BOMs/overrides. Never treat an out-of-matrix intermediate state as safe.
4. **Inspect resolved dependencies:** remove unnecessary version pins and detect duplicate or conflicting SCC lines on the classpath.
5. **Run producer verification:** compile, generated contract tests, unit/integration tests, and startup smoke tests.
6. **Package stubs from the upgrade commit:** tag with a candidate version so the stub reflects the tested contract and implementation.
7. **Run consumer verification with candidate stubs:** cover active consumers, including supported versions currently deployed.
8. **Document results and decide rollout:** if a contract has breaking changes, define a migration/versioning plan and deployment order.

If you are only applying a patch upgrade within the same release train, the scope of change is usually smaller than a major Boot upgrade, yet you should still re-run key verifications. A patch release can fix bugs or alter behavior in ways existing tests do not cover.

### Example Upgrade Path

Suppose a system is on `Spring Boot 3.4.x + Spring Cloud 2024.0.x` and wants to move to Boot 3.5. The team cannot simply change `3.4.x` to `3.5.x`; they must select the matching `2025.0.x` train, check which Contract version the new train manages, update the plugin version, and then verify both producer and consumers against the new stub. The exact patch choice still depends on the official documentation and support policy at the time of the upgrade.

## 13. Bringing Version Choices into CI/CD

A local demo on a developer machine does not guarantee repeatability in a pipeline. With Spring Cloud Contract, make sure the toolchain and artifacts are fully captured:

~~~mermaid
flowchart TD
    A["Lock JDK + Boot + Cloud train + Contract plugin"] --> B["CI resolves dependencies and compiles"]
    B --> C["Generate and run producer contract tests"]
    C --> D{"Tests pass?"}
    D -- "No" --> E["Block change, analyze version/contract/code"]
    D -- "Yes" --> F["Package stub tagged with candidate version/commit"]
    F --> G["Consumer CI runs Stub Runner with matching artifact"]
    G --> H{"Consumer tests pass?"}
    H -- "No" --> E
    H -- "Yes" --> I["Pass compatibility gate, continue release pipeline"]
~~~

A solid pipeline should:

- Use the exact verified **JDK/toolchain**, Maven/Gradle Wrapper, and version properties.
- Resolve dependencies from explicitly configured repositories; control snapshots or dynamic versions.
- Execute real **generated tests**, rather than letting a build pass without contracts.
- Package stubs and record **version, commit SHA, classifier, and repository** metadata.
- Have consumers test against the **candidate stub**, avoiding stale caches or production stubs by mistake.
- Fail clearly when an artifact is missing; never treat "skip tests" as valid.
- Enforce a merge/release gate whenever producer tests or consumer compatibility checks fail.

**Note:** A valid Boot–Cloud pair is a prerequisite for the testing tooling to function, not proof of API compatibility. Catching breaking changes still depends on thorough contracts and consumer tests running against the candidate stub.

## 14. Hands-On Exercise: Lock In and Verify a Version Set

**Scenario:** Inventory Service exposes `GET /api/inventory/{sku}`. Checkout Service calls this endpoint to decide whether to accept an order. Both services need Spring Cloud Contract set up to verify this behavior.

**Task 1 — Choose versions**

- Consult official documentation and pick a supported Spring Boot patch that meets project requirements.
- Find the matching Spring Cloud release train; record your rationale and documentation links.
- Identify the SCC version managed by the BOM and the corresponding Maven/Gradle plugin version.
- Check Java and build tool versions in both local development and CI environments.

**Task 2 — Configure the producer**

- Create a Spring Boot Web project, import the Spring Cloud BOM, and add Contract Verifier in test scope.
- Apply the Contract Maven/Gradle plugin with the appropriate version and configure the test base class.
- Write a Groovy or YAML HTTP contract describing the stock endpoint response.

**Task 3 — Verify the build**

- Run commands to inspect resolved dependencies.
- Run the build to generate and execute the producer contract test.
- If the test fails, classify the issue: version/plugin setup, missing implementation, wrong test base, or wrong contract expectation.
- Confirm that the stub artifact is generated with traceable coordinates.

**Task 4 — Connect the consumer**

- Add the Stub Runner test dependency via the consumer's BOM.
- Configure the consumer test to point to the **candidate producer stub**.
- Run the real Checkout client test and assert that the stock payload is parsed accurately.
- Simulate renaming a JSON field and observe which verification step catches the failure.

**Deliverables:** version decision table; BOM and plugin configuration; resolved dependency/version logs; generated test name and outcome; stub artifact coordinates; consumer test result; and a short explanation of why the selected Boot–Cloud pair is appropriate.

## 15. Pre-Contract Checklist

- [ ] A specific **Spring Boot version** is chosen, with Java/build tool requirements known.
- [ ] **Spring Cloud Release Train** appears in the official compatibility matrix for that Boot line.
- [ ] **Support status** and patch suitability were checked instead of blindly picking the highest number.
- [ ] The right **Spring Cloud BOM** is imported, without unjustified overrides on individual Contract dependencies.
- [ ] The **Contract build plugin** is pinned to a version matching the resolved Contract libraries.
- [ ] `spring-cloud-starter-contract-verifier` is in test scope on the producer side.
- [ ] `spring-cloud-starter-contract-stub-runner` is in test scope on the consumer side if using stub tests.
- [ ] The build actually **generates and runs** producer contract tests with the proper application context.
- [ ] CI publishes/retrieves **candidate stubs** with exact version, commit, and classifier.
- [ ] Consumer tests run against candidate stubs before any release decision.

## 16. Self-Check Questions

**1. Is Spring Cloud `2025.0.x` the version of Spring Cloud Contract?**

No. That is a Spring Cloud **release train**. Spring Cloud Contract is a project within the release train with its own module version; the release train BOM manages the corresponding library version.

**2. Once the Spring Cloud BOM is imported, do you still need to specify a version for the Maven Contract plugin?**

Yes. Maven `dependencyManagement` manages project dependencies, whereas `spring-cloud-contract-maven-plugin` is a build plugin and must be configured with an appropriate version.

**3. Does a successful Maven `verify` command prove that Contract is working?**

Not by itself. You must confirm that the plugin generated **generated contract tests** from at least one contract, that the test runner executed them, asserted the expected behavior, and packaged the stub as intended.

**4. Why shouldn't you disable the Spring Cloud Compatibility Verifier to handle a mismatch error?**

Because doing so only skips the startup check without changing dependencies or binary compatibility. You should choose a valid Boot–Cloud pair and verify it through actual builds and tests.

**5. Do producer and consumer have to use the exact same Spring Boot version?**

Not necessarily. Each service must use an internally compatible Boot–Cloud set; communication compatibility is governed by the contract/stub and how HTTP or messages are serialized and handled between the two services. Consumer tests must run against the stub of the producer version under test.

---

**Key takeaway:** Choosing a Spring Cloud Contract version means choosing **a cohesive stack**: a Spring Boot release compatible with a Spring Cloud Release Train, Contract libraries managed by the BOM, and a matching Contract build plugin. Always verify via **dependency trees, generated tests, stub artifacts, and consumer tests**—never rely solely on configuration that merely looks valid.
