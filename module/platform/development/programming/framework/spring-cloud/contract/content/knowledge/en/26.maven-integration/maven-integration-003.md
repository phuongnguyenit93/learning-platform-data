# Binding Test Generation to the Maven Lifecycle

When using **Spring Cloud Contract**, placing a Groovy or YAML contract file in a **producer** project is only the step that describes the interaction. For the contract to genuinely protect the API, **Maven must generate test code from the contract before test compilation**, run that code against the producer's implementation, and only package/release stubs once mandatory checks pass. If the test-generation goal runs too late or is not bound to the lifecycle, Maven can report `BUILD SUCCESS` even though **not a single generated contract test executed**.

This lesson belongs to the **Maven Integration** chapter of the **SPRING_CLOUD_CONTRACT** module. The module teaches contract testing between producer and consumer using Groovy/YAML DSL for HTTP or messaging, generating producer tests, publishing stubs, using Stub Runner, and integrating with CI to detect incompatible API changes. This lesson focuses on **how plugin goals bind to the Maven lifecycle**, verifying the path from `generate-test-sources` to `test`/`package`, and designing reliable release gates.

The examples use **Spring Boot + Spring MVC + JUnit 5** with `spring-cloud-contract-maven-plugin` for illustration. Goal names and default phases should be verified against the **exact plugin version installed in your project**, because plugin configuration and generation/packaging behavior can vary across Spring Cloud Contract releases.

## 1. Distinguishing contract, goal, phase, and lifecycle

Maven uses a **lifecycle** made up of ordered **phases**. A **plugin goal** can be bound to a phase. When you run Maven up to that phase, earlier phases in the same lifecycle run sequentially.

| Concept | Example | Meaning |
| --- | --- | --- |
| **Contract** | `src/test/resources/contracts/orders/get_order.groovy` | Source specification describing request/response or message. |
| **Plugin** | `spring-cloud-contract-maven-plugin` | Build logic that turns contracts into generated tests and stubs. |
| **Goal** | `generateTests` | A specific task performed by the plugin. |
| **Phase** | `generate-test-sources` | A stage in the Maven lifecycle sequence. |
| **Lifecycle** | `default` | The sequence of phases from start through `package`, `verify`, `install`, `deploy`. |
| **Test runner** | Maven Surefire | Compiles/runs tests at the appropriate phase through corresponding goals. |

**Do not confuse `generateTests` with the `test` phase.** `generateTests` produces **test source code**; the `test` phase is where Surefire normally **runs the compiled tests**. If code is generated without running, the producer is still unverified.

~~~mermaid
flowchart TD
    A["Groovy/YAML contracts"] --> B["generate-test-sources: generateTests"]
    B --> C["process-test-resources: convert"]
    C --> D["test-compile: compile generated tests"]
    D --> E["test: Surefire runs tests"]
    E --> F{"Producer verification passes?"}
    F -->|No| G["Stop build; do not publish"]
    F -->|Yes| H["package: generateStubs creates stubs JAR"]
    H --> I["verify: run extra integration checks if any"]
    I --> J["install / deploy"]
    J --> K["Consumer downloads stubs via Stub Runner"]
~~~

The diagram shows the **expected producer path** when the plugin and test runner are configured properly. Maven only blocks publishing automatically if the pipeline executes the proper lifecycle, does not skip tests, and does not decouple publishing from verification gates.

## 2. Key Maven phases for Contract Verifier

In the `default` lifecycle of a `jar`-packaged project, the following phases relate directly to producer contract tests:

| Relative order | Maven phase | Activity to observe |
| --- | --- | --- |
| 1 | `validate` | Basic project/POM validation; custom build checks may bind here. |
| 2 | `generate-sources`, `compile` | Prepares and compiles the producer's main sources. |
| 3 | **`generate-test-sources`** | Spring Cloud Contract **generates Java/Groovy producer tests** from contracts. |
| 4 | `generate-test-resources`, **`process-test-resources`** | Prepares test resources; the plugin may **convert contracts into stub mappings**. |
| 5 | **`test-compile`** | Compiles generated tests and developer-written tests. |
| 6 | **`test`** | Surefire executes unit tests and recognized generated producer tests. |
| 7 | **`package`** | Builds the application artifact and `stubs` artifact if properly configured. |
| 8 | **`verify`** | Runs post-package checks; may include Failsafe integration-test verification. |
| 9 | **`install`** | Installs artifacts into the local Maven repository. |
| 10 | **`deploy`** | Publishes artifacts to the configured remote repository. |

**`mvn test` does not run `package`**, so it will not produce a fresh `stubs` JAR by default. **`mvn verify` passes through both `test` and `package`**, making it suitable for running all checks before release. **`mvn install`** and **`mvn deploy`** also traverse earlier phases unless skipped or altered by profiles.

Note that Maven also has intermediate phases not fully listed in this table. This lesson highlights the milestones that explain **the right order: generate → compile → run tests → package → publish**.

## 3. Three common Spring Cloud Contract goals and default phases

In Maven Plugin versions providing these goals, Spring Cloud Contract documentation describes:

| Plugin goal | Default phase | Primary output | Dependency relationship |
| --- | --- | --- | --- |
| **`generateTests`** | **`generate-test-sources`** | Produces **producer verification test** sources. | Needs valid contracts and base test to compile and run. |
| **`convert`** | **`process-test-resources`** | Converts contracts into **stub mappings/resources**. | Requires discoverable contracts in a supported format. |
| **`generateStubs`** | **`package`** | Packages the stub JAR from converted resources. | **`convert` must run first**. |

The goal names above use the exact casing from Maven Plugin documentation. **Do not assume every plugin version has a goal named `packageStubs`**; for the goal set described here, the JAR-creation goal is **`generateStubs`**.

Other goals such as `run`, `help`, or SCM stub-push goals serve separate purposes. `run` serves stubs and does not replace `generateTests` or executing producer tests in a build.

**An easily overlooked detail:** binding goals to phases is **not enough** if Surefire fails to discover generated classes, generated tests are skipped, or the plugin finds no contracts. Always inspect the **test report**, not just whether Maven executed the goal.

### 3.1. Why must `convert` run before `generateStubs`?

Contracts can be written in Groovy/YAML DSL, whereas HTTP Stub Runner typically uses **WireMock mappings** to serve responses. `convert` produces the required stub resources; `generateStubs` then **packages the converted resources**. Invoking `generateStubs` on a directory never prepared by `convert` can yield errors or an artifact missing expected contents.

For **messaging-only contracts**, the packaged resources can differ from HTTP mappings: labels, destinations, headers, and payloads may be processed by Stub Runner via messaging adapters. Do not look only for `mappings/*.json` and conclude no stubs exist.

## 4. Minimal producer POM: dependencies and plugin

Consider an illustrative project `com.acme:order-service:1.0.0` using Spring Boot 3.3.x and Spring Cloud 2023.0.x. Below is a **reference POM** showing the placement of the BOM, dependencies, and plugin:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>order-service</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2023.0.4</spring-cloud.version>
        <spring-cloud-contract.version>4.1.5</spring-cloud-contract.version>
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
                <version>${spring-cloud-contract.version}</version>
                <extensions>true</extensions>
                <configuration>
                    <testFramework>JUNIT5</testFramework>
                    <testMode>MOCKMVC</testMode>
                    <baseClassForTests>
                        com.acme.orders.ContractTestBase
                    </baseClassForTests>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Version warning:** the three version numbers above illustrate a matching Spring Boot/Spring Cloud Contract stack, **not a guarantee that every patch in those lines is compatible or the latest**. Before applying, verify against your project's release train and compatibility matrix; never upgrade only the plugin while leaving starters/BOMs outdated.

### 4.1. Distinguishing dependencies and the Maven Plugin

| POM component | Role |
| --- | --- |
| `spring-boot-starter-web` | Runs the real Spring MVC producer. |
| `spring-boot-starter-test`, scope `test` | Spring Test, JUnit Jupiter, MockMvc, and matching test utilities. |
| `spring-cloud-starter-contract-verifier`, scope `test` | Components required to compile and run generated producer tests. |
| `spring-cloud-contract-maven-plugin` in `build/plugins` | Executes **test generation, conversion, and stub packaging** goals. |
| `spring-cloud-dependencies` BOM | Manages versions of Spring Cloud dependencies. |
| `spring-cloud-contract.version` | Sets the **build plugin** version, which is not automatically filled in by the BOM inside the plugin's `<version>` tag. |

Declaring only the Verifier starter **without the Maven Plugin** can leave zero generated tests produced. Conversely, having the Maven Plugin without test dependencies or a base test causes compile or runtime errors. Both pieces must be configured deliberately.

## 5. Using `<extensions>true</extensions>` for lifecycle integration

In Spring Cloud Contract Maven guides, a common pattern is declaring the plugin with:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>
            com.acme.orders.ContractTestBase
        </baseClassForTests>
    </configuration>
</plugin>
~~~

With the corresponding plugin/lifecycle configuration, Maven can generate tests and stubs during standard phases such as `mvn clean verify`. **You do not need to call `generateTests` manually before every Maven run** once the plugin is properly integrated into the lifecycle.

Do not treat `<extensions>true</extensions>` as an "automatic test correctness switch": it only participates in **how Maven loads the plugin and integrates lifecycle bindings**. The test runner still needs to compile and execute generated tests. Confirm via Maven logs and `effective-pom` that the goals are actually bound.

### 5.1. Avoid accidentally declaring duplicate executions

If an extension configuration already binds goals to the lifecycle automatically, adding an identical `<executions>` block can cause **goals to run twice**, overwriting generated sources or building stubs repeatedly. Conversely, in projects with custom lifecycle setups, you may need **explicit executions**.

**Rule:** pick one clear strategy, then verify using Maven debug logs/`effective-pom` and test reports. Do not paste every plugin snippet found online into the same POM.

## 6. Alternative: binding goals explicitly with `<executions>`

If the team prefers **explicit goal–phase mappings in the POM** instead of relying on automatic binding, an alternative configuration places these executions inside `spring-cloud-contract-maven-plugin`:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>
            com.acme.orders.ContractTestBase
        </baseClassForTests>
    </configuration>
    <executions>
        <execution>
            <id>generate-contract-tests</id>
            <phase>generate-test-sources</phase>
            <goals>
                <goal>generateTests</goal>
            </goals>
        </execution>
        <execution>
            <id>convert-contracts-to-stubs</id>
            <phase>process-test-resources</phase>
            <goals>
                <goal>convert</goal>
            </goals>
        </execution>
        <execution>
            <id>build-contract-stubs-jar</id>
            <phase>package</phase>
            <goals>
                <goal>generateStubs</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

This is an **alternative to the plugin block in section 5**, **not something to append under an already auto-bound configuration**. Before using it, verify your plugin version supports all three goals and executes them **once** in the expected phases.

Why those phases?

- `generateTests` in **`generate-test-sources`**: test code exists **before `test-compile`**.
- `convert` in **`process-test-resources`**: mappings are prepared **before stub packaging**.
- `generateStubs` in **`package`**: builds the `stubs` classifier JAR from resources produced by `convert`.

**Do not bind `generateTests` to `verify`** if you expect the generated tests to be run by Maven `test` in the same build; `verify` runs **after `test`**, so test code generated then is too late for the current test phase.

### 6.1. When should explicit executions be used?

They help when a project has a non-standard parent POM, needs strict review of exact phase–goal bindings, or wants fine-grained control over conversion/packaging. However, explicit bindings **do not replace** other requirements: contracts, dependencies, a base test, the compiler, and Surefire must still be in place.

If the plugin is already configured in a **parent POM** and a child POM adds another execution, Maven may **merge configurations**. Inspect `effective-pom` to avoid inherited executions duplicating declared ones.

## 7. Distinguishing `<pluginManagement>` and `<plugins>`

This is a common multi-module Maven pitfall. For instance, a parent POM might only define:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-contract-maven-plugin</artifactId>
                <version>${spring-cloud-contract.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

The snippet above **manages default version/configuration**, which does not necessarily mean the goals run in every module. A producer module typically needs to **activate the plugin** under `<build><plugins>`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

When the parent manages full executions/configuration, the child can inherit them per Maven merge rules. **Do not copy plugin declarations into every module** just to "play it safe"; a consumer-only module does not need to generate producer tests if it owns no outbound contracts.

## 8. Sample HTTP contract loaded by Maven

Create `src/test/resources/contracts/orders/get_paid_order.groovy` in the producer:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Read a paid order'

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

The contract describes **observable HTTP behavior**: the request is `GET /api/orders/42`; the response is `200` with JSON `{"id":42,"status":"PAID"}`. It contains no Maven goal names, target paths, or WireMock ports.

If the team chooses **YAML DSL**, the same behavior can be defined in a separate YAML file:

~~~yaml
description: Read a paid order
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

In a real build, **pick one active contract source per scenario** so the plugin does not load both an equivalent Groovy and YAML file and generate duplicate tests/stubs.

### 8.1. Contract paths and test grouping

The plugin normally scans:

~~~text
src/test/resources/contracts/
└── orders/
    └── get_paid_order.groovy
~~~

Directory structure can be used to **group generated test classes/packages**. Do not arbitrarily diverge paths between CI and IDEs: if the plugin scans the wrong folder, Maven may still run subsequent phases, forcing you to check logs/`failOnNoContracts` to realize no contracts were loaded.

When contracts reside in a separate repository or module, the plugin provides options to fetch contracts externally. However, this lesson focuses on **contracts co-located with the producer** to keep the lifecycle clear; external contract usage requires matching repository/version configuration and never assumes an arbitrary dependency is read as a contract source.

## 9. Real producer and base test class so generated tests run

Create a Spring Boot application with `@SpringBootApplication`, e.g., `com.acme.orders.OrderApplication`. A controller serving the contract:

~~~java
package com.acme.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public OrderView getOrder(@PathVariable long id) {
        if (id != 42L) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return new OrderView(42L, "PAID");
    }

    public record OrderView(long id, String status) {}
}
~~~

This controller hardcodes ID 42 **purely to illustrate build mechanics**; a real application requires services, repositories, real data, and authentication as needed.

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
    void configureMockMvc() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

With `testFramework=JUNIT5` and `testMode=MOCKMVC`, generated tests need access to the Spring MVC test context. `ContractTestBase` prepares `MockMvc` and wires `RestAssuredMockMvc`. If the producer requires `Order 42` in a database or an auth token, the base test must also prepare fixtures and security **before the request**.

**The Maven Plugin does not generate the entire business environment.** If `GET /api/orders/42` returns 404 because the database was not seeded, that may be a fixture bug; if the controller renames the JSON field `status` to `state`, that is a producer contract violation. Distinguish them so you fix the right place.

## 10. How `mvn test`, `mvn package`, `mvn verify`, and `mvn install` differ

| Command | Lifecycle runs up to | Use when | What not to infer |
| --- | --- | --- | --- |
| `./mvnw clean test` | `test` | Generating, compiling, and running generated producer tests. | Does not necessarily build the `stubs` JAR because `package` has not run. |
| `./mvnw clean package` | `package` | Running tests then packaging app and stubs. | Does not run post-`package` integration verifications. |
| **`./mvnw clean verify`** | `verify` | Running all goals/tests bound through `verify` before publishing. | Does not publish artifacts to a repository automatically. |
| `./mvnw install` | `install` | Installing artifacts into **local Maven** for consumer `LOCAL` tests. | Does not push artifacts to a shared repo for other CI runners. |
| `./mvnw deploy` | `deploy` | Publishing artifacts per `distributionManagement`/Maven deploy config. | Does not guarantee pipeline integrity if tests were skipped or artifacts unverified. |

`./mvnw` is the project's **Maven Wrapper**. On Windows you can use `mvnw.cmd`; if no wrapper is present, use `mvn` matching the verified Maven version.

An illustrative run:

~~~shell
./mvnw clean verify
~~~

Do not run `generateTests` directly and assume Maven finished testing; generating sources alone is insufficient. When goals are properly bound to the lifecycle, `verify` executes the **entire chain of tasks**.

### 10.1. Invoking a plugin goal directly differs from running a phase

For example:

~~~shell
./mvnw spring-cloud-contract:generateTests
~~~

tells the plugin to **generate tests**. It does not instruct Maven to run `test-compile`, `test`, `package`, or `verify`. Similarly:

~~~shell
./mvnw spring-cloud-contract:convert
./mvnw spring-cloud-contract:generateStubs
~~~

requests converting and packaging stub resources by goal, not full producer verification. `generateStubs` requires data created earlier by `convert`; direct goal invocations require proper configuration and ordering.

For Maven to recognize the `spring-cloud-contract:...` prefix, the environment may need `pluginGroups` configured or the plugin declared in the project. If the prefix cannot be resolved, invoke the **fully qualified goal**:

~~~shell
./mvnw org.springframework.cloud:spring-cloud-contract-maven-plugin:generateTests
~~~

**Do not treat the result of an isolated goal invocation as a substitute for `./mvnw verify`.** In CI, run the test runner and verify reports before publishing.

## 11. Are generated tests actually executed by Maven Surefire?

The normal path:

~~~text
Contract source (.groovy/.yml)
    -> generateTests at generate-test-sources
    -> Java/Groovy generated test sources
    -> test-compile
    -> Surefire executes in test phase
    -> target/surefire-reports/
~~~

Items to verify:

1. The plugin **finds the contracts** and generates at least one test.
2. Generated sources are **added to Maven test source roots** so the compiler sees them.
3. Tests **compile cleanly** against compatible JUnit/Rest Assured/Spring Test dependencies.
4. Surefire **discovers tests** using the right engine/framework.
5. Reports show **tests executed > 0**, not all `skipped`.
6. When you deliberately break the producer response, at least one test **FAILS**.

A Surefire configuration when a project needs to manage its version directly:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <!-- Select a Surefire version supporting JUnit Platform,
         compatible with the Spring Boot parent and Maven in use. -->
</plugin>
~~~

When using Spring Boot parent, many plugin versions are already managed; there is no need to override Surefire just to use JUnit 5. Override versions only with a clear reason and after compatibility checks. Report files normally reside under `target/surefire-reports`.

### 11.1. When tests are generated but not compiled

In certain IDEs or custom Maven builds, the generated test sources folder may **not be recognized** as a test source root. Investigate by checking the **path generated by the plugin under `target/`**, then check whether the Maven compiler reads it. Some projects use `build-helper-maven-plugin` to add a test source root, though **you should not add it blindly** when the plugin already registers the directory properly.

If `build-helper` is genuinely needed, bind `add-test-source` to `generate-test-sources` with the **exact generated sources path for your plugin version**:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>add-generated-contract-tests</id>
            <phase>generate-test-sources</phase>
            <goals>
                <goal>add-test-source</goal>
            </goals>
            <configuration>
                <sources>
                    <source>
                        ${project.build.directory}/generated-test-sources/contracts
                    </source>
                </sources>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**Condition:** apply this snippet only after confirming the actual generated test directory **matches that path** and the compiler has not already been configured by the plugin. Avoid registering duplicate test source roots or copying a default path from another version.

## 12. How to prove the lifecycle is bound correctly

Do not just inspect the POM by eye. Check the resolved Maven config after parent/profile inheritance and the goal order in logs:

~~~shell
./mvnw help:effective-pom
./mvnw clean verify
~~~

If you filter logs or run Maven in debug mode, look for:

~~~text
spring-cloud-contract:...:generateTests
spring-cloud-contract:...:convert
maven-compiler-plugin:...:testCompile
maven-surefire-plugin:...:test
spring-cloud-contract:...:generateStubs
~~~

**This is a conceptual checklist for scanning logs**, not a guarantee of exact line ordering or output formatting across every Maven/Plugin version. What matters is confirming generated sources exist **before test compilation**, tests execute **before packaging**, and `generateStubs` packages **after conversion**.

To inspect goal descriptions for your exact version, the plugin provides a help command:

~~~shell
./mvnw org.springframework.cloud:spring-cloud-contract-maven-plugin:help \
    -Ddetail=true -Dgoal=generateTests
~~~

On Windows shells, write it on a single line instead of using POSIX `\` line continuation. When upgrading the plugin, run help similarly for `convert` and `generateStubs` to check actual **default phases, parameters, and goal names**.

## 13. How is the `stubs` artifact packaged?

Once the lifecycle reaches `package` and plugin packaging succeeds, the producer may contain:

~~~text
target/
├── order-service-1.0.0.jar
├── order-service-1.0.0-stubs.jar
├── generated-test-sources/
├── stubs/
└── surefire-reports/
~~~

This is an **illustrative diagram**. Exact paths depend on version, packaging, and Maven settings. The key point is that the **application JAR** and the **JAR with classifier `stubs`** serve distinct purposes.

Maven coordinates of the stub:

~~~text
groupId    = com.acme
artifactId = order-service
version    = 1.0.0
classifier = stubs
~~~

In shorthand:

~~~text
com.acme:order-service:1.0.0:stubs
~~~

In many plugin setups, `generateStubs` creates/attaches the `stubs` artifact during `package`. To verify, **inspect the JAR file and Maven metadata**, not just `target/stubs`. A build can generate mappings without producing the classifier JAR if the lifecycle stops before `package` or packaging is skipped.

### 13.1. Inspect JAR contents rather than just the filename

Using the JDK `jar` tool:

~~~shell
jar tf target/order-service-1.0.0-stubs.jar
~~~

HTTP stubs typically contain WireMock mappings and original contracts under `META-INF/...`. Consumer Stub Runner normally expects **resources and paths matching** the group/artifact/version. Do not assume from a correctly named JAR that it holds the **right contract version**: inspect its contents and cross-check generated producer tests.

For messaging contracts, the stub JAR may contain messaging contract resources rather than HTTP mappings for those events. **Do not count `mappings` = 0 and conclude packaging failed** if the project only defines message contracts.

## 14. Why must `install` or `deploy` wait for verification?

In the Maven lifecycle, `install` and `deploy` come **after `test`/`package`/`verify`**. In a normal lifecycle run **without skipping**, failing tests stop the build before `install`/`deploy`.

However, the following situations can still produce an **improperly verified** stub:

- A user invokes packaging goals directly **without running tests**.
- CI splits publishing into a separate job **without checking the producer test job result**.
- The build passes `-DskipTests` or `-Dmaven.test.skip=true`.
- Generated contract tests are not discovered by Surefire.
- Contracts fail to load, yet the build is allowed to pass.
- Plugin/test execution lives in a profile not activated in CI.

A safe operational flow is:

~~~text
validate POM & toolchain
  -> contract generation + producer tests
  -> inspect test reports / required test count
  -> package and verify
  -> attach stubs artifact
  -> install/publish/deploy
  -> consumer Stub Runner tests
~~~

**Never treat a successful `mvn deploy` as proof of quality if earlier verification steps were disabled.** CI gates must explicitly confirm producer verification executed and passed.

### 14.1. Distinguishing `-DskipTests` and `-Dmaven.test.skip=true`

In most Maven configurations:

| Flag | Typical effect | Risk |
| --- | --- | --- |
| `-DskipTests` | Skips test **execution**, though tests may still compile. | Generated tests exist but never run. |
| `-Dmaven.test.skip=true` | May skip both test **compilation and execution**. | Producer verification is bypassed completely. |
| Contract Verifier plugin skip flags | Can skip generation/conversion/packaging per parameter. | Missing contract verification or expected stubs. |

Do not make a local speed-up skip flag the default on release jobs. If you need a quick build to check compilation errors, mark that artifact as **not verified by producer verification** and never push it to an official release channel.

## 15. Surefire and Failsafe: unit tests or integration tests?

Maven provides **Surefire** for unit/component tests in `test` and **Failsafe** typically for integration tests across `integration-test`/`verify` when configured.

| Component | Typical phase | Role |
| --- | --- | --- |
| `maven-surefire-plugin` | `test` | Runs discovered test classes; normally includes generated contract tests. |
| `maven-failsafe-plugin:integration-test` | `integration-test` | Runs integration tests that may require servers/test containers. |
| `maven-failsafe-plugin:verify` | `verify` | Aggregates integration test results and fails the build when needed. |

Example Failsafe setup for **separately written** integration tests:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Do not confuse `generateTests` with `Failsafe integration-test`. **Generated contract tests from DSL are not automatically converted into Failsafe tests**. If a project wants to run them as integration tests, configure class naming, runner, and lifecycle appropriately; otherwise, let Surefire run them during `test` as in the standard workflow.

**Why use `verify` instead of invoking `integration-test` directly?** With Failsafe, the `verify` phase checks results so Maven returns the proper build failure status. Also, cleanup steps in `post-integration-test` may need to run in order. Following the full lifecycle instead of a single goal ensures the test environment starts and tears down cleanly.

## 16. Consumer Maven: Stub Runner is a test dependency, not a producer goal

Once Order Service has published `com.acme:order-service:1.0.0:stubs`, the consumer Billing Service needs **Spring Cloud Contract Stub Runner** in test scope:

~~~xml
<dependencies>
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

This is the **dependency section of the consumer POM**, requiring a compatible Spring Boot parent/BOM, Spring Cloud BOM, and application-specific dependencies. Consumers generally **do not need** `spring-cloud-contract-maven-plugin` solely to use stubs published by a producer. If Billing also acts as a producer for another service, it may need both Verifier and Stub Runner in their respective roles.

A real client:

~~~java
package com.acme.billing;

import org.springframework.web.client.RestClient;

public class OrderClient {
    private final RestClient restClient;

    public OrderClient(String baseUrl) {
        this.restClient = RestClient.create(baseUrl);
    }

    public OrderDto getOrder(long id) {
        return restClient.get()
            .uri("/api/orders/{id}", id)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(long id, String status) {}
}
~~~

Consumer test using Stub Runner:

~~~java
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
    void readsPaidOrder() {
        URL baseUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub was not started"
        );

        OrderClient client = new OrderClient(
            baseUrl.toExternalForm()
        );

        OrderClient.OrderDto order = client.getOrder(42L);

        assertThat(order.id()).isEqualTo(42);
        assertThat(order.status()).isEqualTo("PAID");
    }
}
~~~

`StubsMode.LOCAL` works when the producer has installed the stub artifact into the **same local Maven repository** used by the consumer test; on separate CI machines, use `REMOTE` with configured repositories and credentials. `StubFinder` returns the URL of the **started stub server**, not the Maven repository URL.

What the consumer test proves: **Billing's HTTP client code** sends requests and handles responses matching the contract stub. What it does not prove: that Order Service's implementation satisfies the contract. Hence, producer generated tests remain a mandatory pre-release gate.

## 17. Multi-module Maven and reactor builds

In a multi-module repository:

~~~text
commerce-platform/
├── pom.xml
├── order-service/
│   └── pom.xml
├── inventory-service/
│   └── pom.xml
└── checkout-service/
    └── pom.xml
~~~

Each module's role:

| Maven module | Role | Maven configuration |
| --- | --- | --- |
| `order-service` | Producer of Order API | Contract Verifier plugin + contract files + base test. |
| `inventory-service` | Producer of Inventory API | Separate Contract Verifier plugin and contract set. |
| `checkout-service` | Consumer of both APIs | Stub Runner test dependency and coordinates of both stub artifacts. |

The parent POM can centralize plugin versions and BOMs, but **plugin execution should take effect in the appropriate producer modules**. Avoid applying `generateTests` across every module if a module has no contracts, as the plugin may fail on missing contracts or add pointless build steps.

When using the Maven reactor, you can run:

~~~shell
./mvnw -pl order-service -am clean verify
~~~

`-pl` selects the project/module; `-am` builds **required dependent modules** in the reactor. **Do not assume `-am` automatically builds another producer just because a consumer downloads that producer's stub from a Maven repository**: reactor ordering relies on Maven dependencies and the project graph. An artifact with the `stubs` classifier must already be **packaged and resolvable** when consumer tests request it.

**Parallel reactor risk:** Spring Cloud Contract Maven Plugin goals such as `generateTests`/`convert`/`generateStubs` have versions not marked thread-safe. When enabling `mvn -T`, verify configuration safety, output directories, and build agents; never assume every goal is thread-safe in parallel builds.

## 18. Messaging contracts also need proper lifecycle binding

A producer might emit `OrderCreated` rather than only serving HTTP REST:

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

`generateTests` must still run **before test compilation**. However, the base test must provide `publishOrderCreated()` along with a **MessageVerifier/test binder/messaging adapter** so generated tests can observe the real event. `testMode=MOCKMVC` does not replace messaging test infrastructure.

In `package`, the stub artifact can include **messaging contracts** so Stub Runner emits sample messages via `StubTrigger`/adapters when requested by consumer tests. Messaging scenarios do not automatically become WireMock HTTP endpoints. In CI, add serialization/broker integration tests if consumers depend on raw bytes, headers, topics, or schemas over a real transport.

## 19. CI: forcing Maven to generate, run, and check before publishing

A reliable producer and consumer pipeline:

~~~mermaid
flowchart TD
    A["Producer PR edits code/contract"] --> B["Maven Wrapper + resolve POM/BOM/plugin"]
    B --> C["generateTests + convert"]
    C --> D["test-compile + Surefire"]
    D --> E{"Generated tests actually ran and PASSED?"}
    E -->|No| F["Block publish"]
    E -->|Yes| G["generateStubs in package"]
    G --> H["verify + integration checks"]
    H --> I["Check stubs JAR/classifier/version"]
    I --> J["install or deploy per CI"]
    J --> K["Consumer downloads artifact via Stub Runner"]
    K --> L["Consumer test runs real client code"]
~~~

CI checklist should cover:

1. **Pin versions** of Maven Wrapper/JDK, Spring Boot, Spring Cloud BOM, and Spring Cloud Contract Plugin.
2. **Never skip producer tests** in release jobs; verify `-DskipTests`/`maven.test.skip`/plugin skip flags are not passed implicitly.
3. **Verify contracts were discovered**, not just an empty `contracts` folder in the source tree.
4. **Verify generated tests compiled and ran**, with real counts in Surefire reports.
5. **Block publish when producer verification fails**; an artifact built before `verify` is not automatically a verified artifact.
6. **Package the `stubs` classifier with exact coordinates** and inspect its resources.
7. **Tie artifacts to an explicit commit/version** so consumers can reproduce tests.
8. **Consumer CI uses `LOCAL` or `REMOTE` appropriately**, never assuming two runners share a local Maven repository.
9. **Evaluate backward compatibility** when changing body/headers/status/errors/destinations, rather than checking only the latest contract.

You do not need to run `mvn test`, `mvn package`, and `mvn verify` sequentially in every job: invoking `verify` runs the preceding phases. Split jobs only when aiming for caching, reporting, or release control, and manage artifacts and dependencies explicitly.

### 19.1. If CI uses a separate publish job

Example structure:

~~~text
job producer-verify:
    ./mvnw clean verify
    check Surefire/Failsafe reports
    store built stubs artifact

job publish-stubs:
    runs only if producer-verify PASSED
    verify hash/metadata of handed-off artifact
    publish verified artifact

job consumer-contract-test:
    download stubs by exact version
    run ./mvnw test
~~~

**Do not rebuild different sources or skip tests in the publish job while still labeling it verified**, unless your release mechanism proves the published artifact has identical content from the verification step. A hash/commit/version aids traceability but **never replaces testing**.

## 20. Common lifecycle errors and how to investigate

| Symptom | Possible cause | Investigation path |
| --- | --- | --- |
| `BUILD SUCCESS` with no contract tests. | Plugin not bound to lifecycle, contracts in wrong directory, or tests skipped. | Check `effective-pom`, goal logs, `target/generated-test-sources`, and Surefire report. |
| Tests generated after `test` already ran. | `generateTests` bound to a phase that runs too late. | Use `generate-test-sources` before `test-compile`. |
| Goal `generateTests` runs twice. | `<extensions>true</extensions>` overlaps with `<executions>`, or parent/child POM inherit duplicates. | Inspect `effective-pom` and execution IDs; pick one binding strategy. |
| Test compile fails to find `ContractTestBase`. | Wrong package/base class or test sources not recognized. | Compare `baseClassForTests` with test file and source roots. |
| Generated JUnit 5 tests do not run. | Surefire/JUnit Platform engine/config or naming mismatch. | Check runner version, test count, and reports. |
| `mvn test` PASSES but no `stubs.jar`. | `generateStubs` belongs to `package`; `test` does not reach it. | Run `mvn package/verify` and inspect plugin executions. |
| `generateStubs` reports missing mappings. | `convert` did not run or stubs directory changed. | Check `convert` goal, `process-test-resources` phase, stubs directory. |
| `stubs` JAR named right but missing contracts. | Contracts not loaded, contents excluded, or wrong packaging config. | Open JAR to inspect resources and plugin logs. |
| `mvn install` succeeds yet consumer CI cannot download. | Consumer on another machine, repo not published, or wrong classifier coordinates. | Use `deploy` with proper repo config; check `ids`. |
| `mvn -DskipTests deploy` publishes unverified stub. | Test runner was skipped despite lifecycle running. | Remove skip flag and add CI gate checking test reports. |
| Producer test fails after adding a new contract. | Fixture, auth, base test, or implementation fails to satisfy it. | Separate setup bugs from contract violations; never tweak contract just to turn green. |
| WireMock returns 404 in consumer test. | Request misses mapping, wrong stub version, or business 404. | Check request journal and mappings; assert error body for business 404. |
| Multi-module runs contracts only at root. | Plugin applied at parent, not activated in child producer. | Check plugin in the exact module's effective POM. |
| Parallel Maven build has flaky tests. | Plugin goals not thread-safe, shared target/cache/broker/port. | Isolate state or limit parallelism on affected modules. |

**Diagnostic path:** effective POM after inheritance → plugin/goal bindings → contracts discovered → generated sources → test compilation → test execution/report → `convert` mappings → `generateStubs` JAR → repository/install/deploy → consumer Stub Runner.

## 21. Hands-on exercise: from POM to a verified stub JAR

Practice using two projects, `order-service` and `billing-service`:

1. **Create the producer Maven project** using Maven Wrapper and compatible Spring Boot/Spring Cloud/Contract versions; set `groupId=com.acme`, `artifactId=order-service`, `version=1.0.0`.
2. **Declare BOM and dependencies**: Spring MVC, Spring Boot Test, `spring-cloud-starter-contract-verifier` in test scope.
3. **Apply Spring Cloud Contract Maven Plugin** in `build/plugins`; pick one configuration style: lifecycle-extending plugin or explicit executions. Do not mix both without checking for duplicate goal runs.
4. **Write a Groovy contract** for `GET /api/orders/42` → 200 JSON `PAID`; optionally compare an equivalent YAML file, but load only one source.
5. **Create `OrderController` and `ContractTestBase`** configuring MockMvc in `@BeforeEach`; seed fixtures if your implementation needs them.
6. **Run `./mvnw clean test`**; confirm `generateTests` runs before `test-compile` and Surefire actually executes the generated test.
7. **Intentionally break the producer**: change `PAID` to `PENDING` while keeping the contract; confirm the build FAILS, then revert.
8. **Run `./mvnw clean verify`**; confirm `convert` produces mappings and `generateStubs` creates the `stubs` classifier JAR in `package`.
9. **Inspect `target/surefire-reports` and JAR contents**; never treat JAR existence as enough if tests were 0 or skipped.
10. **Run `./mvnw install`** on the verified producer to install locally. On the consumer, add `spring-cloud-starter-contract-stub-runner` in test scope.
11. **Write a real `OrderClient` and JUnit test**, using Stub Runner `LOCAL` and `StubFinder` for the dynamic URL, asserting JSON `id=42`, `status=PAID`.
12. **Try `REMOTE`** after publishing the artifact to a Maven repository, proving the consumer runs in a separate environment without starting the producer process.
13. **Try an intentional misconfiguration**: bind `generateTests` to `verify` or pass `-DskipTests` in a test branch, observe how tests fail to protect the producer as expected, then restore.
14. **Set CI gates**: producer `verify` PASSES + generated test count > 0 → publish versioned stubs → consumer Stub Runner tests.

**Success criteria:** Maven executes in the **exact order generate → compile → run tests → convert/package → verify → publish**, producer contract tests catch incompatible response changes, and the consumer downloads the right `stubs` artifact to test client code without launching Order Service.

## 22. Self-check questions

1. How does a plugin goal differ from a Maven phase? Why does `generateTests` not equal the `test` phase?
2. What are the responsibilities and default phases of `generateTests`, `convert`, and `generateStubs`?
3. Why must `generateTests` run before `test-compile`?
4. If `generateTests` is bound to `verify`, will Surefire run the generated producer tests in the same `mvn verify` invocation?
5. What does `<extensions>true</extensions>` do? When can adding `<executions>` cause duplication?
6. Why does placing the plugin only in `<pluginManagement>` of a parent POM not automatically activate goals in a producer module?
7. How do `mvn test` and `mvn package` differ regarding building the `stubs` classifier JAR?
8. Why is `mvn clean verify` an appropriate run before publishing?
9. Can you conclude the producer complies with contracts solely from `BUILD SUCCESS` when Surefire reports 0 generated tests?
10. How do `spring-cloud-starter-contract-verifier` and `spring-cloud-contract-maven-plugin` differ in responsibility?
11. When a generated test cannot find its base class, what should you check besides the Groovy contract?
12. Why does `generateStubs` need resources from `convert`?
13. How does `mvn install` differ from `mvn deploy` regarding where consumers can download stubs?
14. Why does `-DskipTests` weaken verification gates even though Maven still runs through `package` or `deploy`?
15. What does `maven-failsafe-plugin` add compared to Surefire, and why is the `verify` phase needed?
16. In a multi-module reactor, why shouldn't the plugin be applied indiscriminately to consumer-only modules?
17. When a consumer Stub Runner test is green, why is producer verification still required to trust the contract?

## 23. References and version caveats

Official documentation to verify **exact goal names, default phases, and plugin configuration per version**:

- Spring Cloud Contract — **Maven Project**: https://docs.spring.io/spring-cloud-contract/reference/maven-project.html
- Spring Cloud Contract Maven Plugin — **Goals**: https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/plugin-info.html
- Plugin goal `generateTests`: https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/generateTests-mojo.html
- Plugin goal `convert`: https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/convert-mojo.html
- Plugin goal `generateStubs`: https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/generateStubs-mojo.html

When viewing `/docs/current/` pages captured for a specific plugin line, **compare the version number under "Full name" with your project's version**. If they differ, check Maven Plugin `help` for your installed version rather than assuming all parameters and phases are identical.

**Key takeaway:** **Test generation from contracts must occur before test compilation and execution in the Maven lifecycle; stub packaging is trustworthy only when producer tests actually execute and pass**. With Spring Cloud Contract, `generateTests` typically binds to `generate-test-sources`, `convert` to `process-test-resources`, and `generateStubs` to `package`. Use consistent plugin/lifecycle configuration, verify `effective-pom` and Surefire reports, and never let skipped tests or duplicate executions hide verification. Finally, install or publish only verified `stubs` artifacts so consumers via Stub Runner and CI catch incompatible API changes reliably.
