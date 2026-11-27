# Configuring the Contracts DSL in a Gradle Build

## 1. Why Configure Spring Cloud Contract Directly in Gradle?

**Spring Cloud Contract (SCC)** helps producer and consumer teams agree on HTTP or messaging behavior through **Groovy DSL/YAML DSL** contracts. On the producer side, **Contract Verifier** generates tests and verifies the real code. From the same contracts, the system can create HTTP stubs or message stubs for consumers to use with **Stub Runner**. When wired into CI, both sides can detect incompatible API changes earlier.

For a project using **Gradle**, placing contract files into the repository is only the first step. Gradle needs to know:

- Which plugin reads and processes the contracts;
- Which directory contains the contracts;
- Whether to generate tests using **MockMvc**, **WebTestClient**, or a mode suitable for the producer's stack;
- Which **base test class** the generated tests inherit from;
- Whether test sources and generated sources are compiled and executed;
- How stub mappings and the **stubs JAR** are created, verified, and published.

That is the role of the **`contracts { ... }` configuration block** provided by the Spring Cloud Contract Gradle plugin.

This lesson belongs to the **Gradle Integration** chapter and focuses on **configuring the contracts DSL in a Gradle build**. The content is structured for self-study and practical application in Spring Boot services, progressing from a simple HTTP example to multiple contract groups, multi-module builds, Stub Runner, and CI.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish the **Gradle contracts extension** from **Groovy/YAML contract files**.
2. Apply the Spring Cloud Contract plugin and declare dependencies using a compatible version set.
3. Configure commonly used properties such as `contractsDslDir`, `testMode`, and `baseClassForTests`.
4. Understand when multiple base classes are needed and how to organize contracts by business domain.
5. Write an HTTP contract, generate producer tests, and verify that the tests actually executed.
6. Generate stub mappings and a stubs JAR, and connect the consumer with Stub Runner.
7. Recognize differences between Gradle Groovy DSL and Kotlin DSL configurations.
8. Diagnose false-green builds caused by missing contracts, wrong directories, wrong test modes, or skipped tasks.
9. Integrate Gradle producer verification and consumer compatibility into CI.

## 2. Two Different Meanings of "DSL" in the Same Project

When working with SCC, two distinct contexts are both commonly called "DSL":

| DSL Type | Where does it live? | What does it do? |
|---|---|---|
| **Gradle Groovy DSL** | `build.gradle` | Configures plugins, dependencies, tasks, `contracts { ... }` |
| **Gradle Kotlin DSL** | `build.gradle.kts` | Same build configuration purpose, using Kotlin syntax |
| **Spring Cloud Contract Groovy DSL** | `*.groovy` files in the contracts directory | Describes request/response or input/output messages |
| **Spring Cloud Contract YAML DSL** | `*.yml`/`*.yaml` files in the contracts directory | Describes the same behavior using YAML |

Example block in `build.gradle`:

~~~groovy
contracts {
    contractsDslDir = file('src/test/resources/contracts')
    testMode = 'MockMvc'
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

This is **not** an HTTP contract. It only configures **how the plugin locates, generates, and executes tests/stubs**.

Example of a contract file:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method GET()
        url '/api/inventory/SKU-123'
    }
    response {
        status OK()
        body(sku: 'SKU-123', available: true, quantity: 12)
    }
}
~~~

The second file describes **communication behavior**. The Gradle plugin reads it based on the configuration in the first file.

**Key point to remember:** `contracts { ... }` is **build configuration**; `Contract.make { ... }` is a **producer–consumer behavior specification**. Mixing the contents of the two DSLs into the wrong place will not produce a valid contract testing pipeline.

## 3. Processing Flow from `build.gradle` to Consumer

~~~mermaid
flowchart TD
    A["build.gradle: plugin and contracts extension"] --> B["Find Groovy/YAML contract files"]
    B --> C{"Contract parses?"}
    C -- "No" --> X["FAIL: fix DSL/path"]
    C -- "Yes" --> D["Generate producer tests"]
    C --> E["Generate HTTP/message stub artifacts"]
    D --> F["Compile + run against real producer"]
    F --> G{"Tests pass?"}
    G -- "No" --> Y["FAIL: implementation or fixture diverges from contract"]
    G -- "Yes" --> H["Package candidate stubs JAR"]
    E --> H
    H --> I["Install / publish artifact"]
    I --> J["Consumer uses Stub Runner"]
    J --> K["Real consumer client/handler"]
    K --> L{"Consumer compatible?"}
    L -- "No" --> Z["FAIL: breaking change or client bug"]
    L -- "Yes" --> M["Passes compatibility gate"]
~~~

These stages represent the **logical target** of the workflow. Do not assume the plugin automatically runs every stage in every project: task wiring, publication configuration, and exact task names depend on **your Gradle version, SCC version, and how the build is written**.

A solid Gradle configuration must ensure each branch produces **verifiable output evidence**: contracts were discovered, tests were generated, tests actually ran, stub mappings are present, and the candidate artifact is consumed by the consumer.

## 4. Prerequisites Before Adding the Plugin

Suppose the producer is **Inventory Service**, a Spring Boot application using Spring MVC. The API to protect:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","available":true,"quantity":12}
~~~

Before configuring, align on:

- **JDK** supported by the chosen Spring Boot and Spring Cloud Contract versions.
- **Gradle** version compatible with the Spring Boot Gradle plugin.
- Compatible **Spring Boot version** and **Spring Cloud Release Train**.
- **Spring Cloud Contract plugin version** matching the Contract dependencies in the project.
- Whether the producer uses **Spring MVC**, **Spring WebFlux**, or a non-Spring HTTP stack.
- Whether the test runner uses **JUnit Jupiter** or another configuration.
- Where contracts and the base test live.

Do not grab a specific version from an old guide and pair it with an arbitrary Spring Boot version. **The Spring Cloud BOM managing dependency versions does not automatically manage the Gradle plugin version.** The plugin ID/version must be verified separately during plugin resolution.

This lesson uses placeholders such as `BOOT_VERSION`, `CLOUD_TRAIN_VERSION`, and `CONTRACT_PLUGIN_VERSION`. They must be replaced with **real versions**; they are not runnable literals.

## 5. Directory Structure of a Gradle Producer

A clear layout:

~~~text
inventory-service/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
└── src/
    ├── main/
    │   └── java/com/example/inventory/
    │       ├── InventoryApplication.java
    │       ├── InventoryController.java
    │       └── InventoryService.java
    └── test/
        ├── java/com/example/inventory/
        │   └── ContractTestBase.java
        └── resources/
            └── contracts/
                └── inventory/
                    └── get-stock.groovy
~~~

The file `src/test/resources/contracts/inventory/get-stock.groovy` will be processed by the plugin. `ContractTestBase` provides the setup for generated tests to invoke the real producer application.

The `src/test/resources/contracts` path is a common convention for Spring Cloud Contract producer projects. If a project wants to use a different directory, it must specify it accurately via `contractsDslDir` and verify that the task reads from that directory.

**Do not** put all contracts under `src/main/resources` and expect the plugin to discover them automatically if configuration points to `src/test/resources/contracts`.

## 6. Configuring `build.gradle` with Gradle Groovy DSL

Illustrative build script for a Spring MVC producer:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'BOOT_VERSION'
    id 'io.spring.dependency-management' version 'DEPENDENCY_MANAGEMENT_VERSION'
    id 'org.springframework.cloud.contract' version 'CONTRACT_PLUGIN_VERSION'
}

group = 'com.example'
version = '1.3.0-rc1'

repositories {
    mavenCentral()
}

ext {
    set('springCloudVersion', 'CLOUD_TRAIN_VERSION')
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
    contractsDslDir = file('src/test/resources/contracts')
    testMode = 'MockMvc'
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**This is a template to explain the configuration blocks**, not an immediately runnable `build.gradle`. Replace all placeholders with real versions verified for compatibility. Depending on Gradle/Boot/Cloud, the project may use `platform(...)` or `enforcedPlatform(...)` instead of the `io.spring.dependency-management` plugin; do not mix both BOM management approaches in conflicting ways.

### Purpose of Each Block

| Configuration | Purpose |
|---|---|
| `id 'org.springframework.cloud.contract'` | Applies the Contract Verifier Gradle plugin |
| `group/version` | Identifies the producer artifact and candidate stubs |
| `repositories` | Source for resolving dependencies |
| Spring Cloud BOM | Aligns Spring Cloud/Contract dependency versions |
| `spring-cloud-starter-contract-verifier` | Supports contract verification in test scope |
| `contractsDslDir` | Specifies the contracts source directory |
| `testMode` | Selects the generated producer test mode |
| `baseClassForTests` | Selects the base test class for generated tests |
| `useJUnitPlatform()` | Enables the Gradle test task to execute JUnit Jupiter if using JUnit 5 |

**Important:** merely adding the plugin and dependency does not guarantee tests will exist or run; you must have **input contracts**, an appropriate base class/test infrastructure, and tasks/lifecycle wiring that actually execute the generated tests.

## 7. `contractsDslDir`: Where Will the Plugin Read Contracts From?

This is the first setting to verify:

~~~groovy
contracts {
    contractsDslDir = file('src/test/resources/contracts')
}
~~~

Typically, the path is resolved relative to **the project/module where the plugin is applied**. In a Gradle multi-project build, `file('src/test/resources/contracts')` inside `:inventory-service` points to the directory inside **that subproject**, not by default to the repository root.

If a project uses another directory:

~~~groovy
contracts {
    contractsDslDir = file('contract-specifications')
}
~~~

then contracts must reside under `contract-specifications` of the corresponding module, and the generated tasks must be verified in practice.

### Common Mistakes

- Putting files in `src/test/contracts` while `contractsDslDir` still points to `src/test/resources/contracts`.
- Using the right directory name but applying the plugin in the **root project** instead of the producer module.
- Moving contracts into another directory via a custom source set without updating configuration.
- Writing YAML in a `.txt` file, or placing Groovy files in a location that is not scanned.
- Enabling a Gradle profile/condition that prevents the task from reading the directory or running.
- Moving code to another subproject while leaving paths relative to the old root.

**Verification rule:** do not merely count files on disk; confirm **the plugin actually parsed them into generated tests/stubs**.

## 8. Writing the First Groovy HTTP Contract

Create the file:

~~~text
src/test/resources/contracts/inventory/get-stock.groovy
~~~

Contents:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout can read stock for SKU-123'

    request {
        method GET()
        url '/api/inventory/SKU-123'

        headers {
            header('Accept', 'application/json')
        }
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

Explanation:

1. `request.method`, `url`, and `headers` specify the HTTP request the producer must handle and the stub must match.
2. `response.status` defines the promised HTTP status.
3. `response.headers` defines the response media type.
4. `response.body` describes sample JSON where `available` is a boolean and `quantity` is a number.
5. SCC generates **producer tests** to call the real endpoint with corresponding assertions.
6. SCC can also generate **WireMock mappings** for consumer stubs.

This contract covers **one specific scenario**. To test `404 SKU_NOT_FOUND` or zero stock, you should add supplementary contracts/fixtures with the corresponding request and response.

## 9. If Choosing YAML Contracts Instead of Groovy

The same behavior can be written as:

~~~yaml
description: Checkout can read stock for SKU-123
name: get_stock_sku123

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

The SCC Gradle plugin can process Groovy or YAML DSL according to the capabilities of the version used. The `contracts { ... }` block **does not turn a YAML file into Gradle DSL**; the plugin reads it as a **separate communication contract source**.

Notes:

- `available: true` is a JSON boolean; `available: 'true'` is a string.
- `quantity: 12` is a number; `quantity: '12'` is a string.
- Valid YAML syntax does not guarantee valid **SCC schema**; keys like `request`/`response` must be at the right nesting level.
- Do not add the exact same scenario in both YAML and Groovy in the same location just to have two formats, as that creates **duplicate mappings/tests**.
- Use the schema and matchers appropriate for your project's SCC version; **always open generated tests** to verify semantics.

## 10. `testMode`: Choosing How Generated Tests Call the Producer

Configuration:

~~~groovy
contracts {
    testMode = 'MockMvc'
}
~~~

`testMode` determines the **generation mode for HTTP producer tests**. For Spring MVC, `MockMvc` is commonly used to invoke controllers through the Spring MVC test infrastructure. For Spring WebFlux, some SCC versions support a corresponding **WebTestClient** mode. For producers not using those stacks, a real HTTP mode or custom setup may be required.

| Producer stack | Common testing approach | What to verify |
|---|---|---|
| Spring MVC | `MockMvc` | Generated requests use MockMvc/RestAssuredMockMvc and hit the real controller |
| Spring WebFlux | `WebTestClient` if supported by plugin version | Generated tests subscribe to/invoke the real reactive handler |
| HTTP server running on a port | Appropriate HTTP mode | URL/port are injected properly, not calling an external mock |
| Message producer | Messaging verifier/test infrastructure | Generated tests observe messages emitted by production code |

The exact `testMode` value names and syntax **depend on the plugin line**. For example, `MockMvc` shows a typical Gradle Groovy DSL configuration, but when using WebFlux or another HTTP mode, consult the exact version's documentation rather than guessing enum values from framework names.

A common configuration mistake: selecting `MockMvc` while the base class only initializes `WebTestClient`, or selecting a WebFlux test mode without wiring the generated test to a WebFlux application context. In that case, **the contract may be valid, yet generated tests fail to compile or run**.

## 11. `baseClassForTests`: The Bridge to the Real Producer Application

For HTTP contracts, generated tests need to know **how to invoke the real controller**. Gradle block:

~~~groovy
contracts {
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

The `ContractTestBase` class lives under `src/test/java` in the producer module.

Example for Spring MVC:

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
    void setUp() {
        RestAssuredMockMvc.webAppContextSetup(context);
    }
}
~~~

In this setup, the base test initializes the **producer's Spring context**; generated tests use the corresponding adapter to invoke the **production controller**, not a fake controller created by the test.

What to avoid:

~~~java
// Anti-pattern: the base test returns the contract's own canned response.
@BeforeEach
void wrongSetup() {
    RestAssuredMockMvc.standaloneSetup(
        new FakeInventoryController()
    );
}
~~~

If a fake controller always returns `{"available":true,"quantity":12}`, generated tests can turn **false green** even when the real Inventory implementation has been broken.

**Practical rule:** only mock/fake dependencies that are **outside the scope of the behavior being verified**. If the contract protects inventory logic computing `available` from `quantity`, do not mock `InventoryService` itself to return the entire sample response DTO.

## 12. What Do Generated Tests Look Like?

After reading contracts, SCC can generate a test class extending the base class and executing assertions. The code below is **illustrative pseudocode**, not the exact generated Java for every version:

~~~java
// PSEUDOCODE: class name, APIs, and assertions vary by SCC version.
class GetStockGeneratedTest extends ContractTestBase {

    @Test
    void verifyGetStock() {
        // Send GET /api/inventory/SKU-123 to the real controller.
        // Verify HTTP 200 and Content-Type application/json.
        // Read response JSON body.
        // Assert $.sku == "SKU-123".
        // Assert $.available == true.
        // Assert $.quantity == 12.
    }
}
~~~

After running the test generation step, **inspect the generated source** to answer:

1. Was a test generated for `get-stock.groovy`?
2. Does the generated class extend the right base class?
3. Does the test use the right test mode?
4. Do the request method/URL/headers match?
5. Which status, headers, and JSON fields are asserted?
6. Does the test source compile?
7. Does the JUnit test runner **actually execute that test**?

A passing build with zero generated tests **is not proof** that the producer complies with the contract.

## 13. Multiple Contract Groups and Base Class Mapping

A larger producer might have two endpoint groups:

~~~text
contracts/
  inventory/
    get-stock.groovy
  reservations/
    create-reservation.groovy
~~~

The inventory group has its own fixtures; the reservations group needs different data or security setup. If a single `ContractTestBase` does not fit both, some versions of the SCC Gradle plugin support **mapping contracts/generated packages to multiple base classes**.

Illustrative Gradle Groovy DSL configuration commonly seen:

~~~groovy
contracts {
    baseClassMappings {
        baseClassMapping('.*inventory.*',
            'com.example.inventory.InventoryContractBase')
        baseClassMapping('.*reservations.*',
            'com.example.inventory.ReservationContractBase')
    }
}
~~~

**Warning:** this example illustrates grouping **by pattern**. The `baseClassMappings/baseClassMapping` syntax and the exact target the regex matches against (path vs. generated package) must be confirmed against **your plugin version**. If the pattern fails to match, the plugin may pick a fallback base or generate uncompilable tests.

Some plugin lines also offer a `packageWithBaseClasses` option to use a package-based convention for base classes:

~~~groovy
contracts {
    packageWithBaseClasses = 'com.example.inventory.contract'
}
~~~

There is no need to enable every mechanism at once. When a single base class suffices, `baseClassForTests` is usually clearer and easier to maintain.

**Mandatory check:** inspect the generated test for **each group** to confirm it inherits the expected class, rather than only looking at `build.gradle`.

## 14. Distinguishing `settings.gradle` and `build.gradle` in Multi-Project Builds

A Gradle repository may contain:

~~~text
platform/
  settings.gradle
  build.gradle
  inventory-service/
    build.gradle
    src/test/resources/contracts/...
  pricing-service/
    build.gradle
    src/test/resources/contracts/...
  checkout-service/
    build.gradle
    src/test/java/...
~~~

`settings.gradle` can include:

~~~groovy
rootProject.name = 'commerce-platform'

include 'inventory-service'
include 'pricing-service'
include 'checkout-service'
~~~

`settings.gradle` declares **project topology**, not where HTTP contracts are normally configured. The `contracts { ... }` block should be applied in the **producer module that actually owns the contracts and code**:

~~~groovy
// In inventory-service/build.gradle
plugins {
    id 'org.springframework.cloud.contract' version 'CONTRACT_PLUGIN_VERSION'
}

contracts {
    contractsDslDir = file('src/test/resources/contracts')
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

The snippet above is a **configuration excerpt**, not a complete build script. If plugin versions are declared centrally in the root via `apply false` or a version catalog, the subproject application syntax may differ.

In multi-project Gradle builds:

- `project.file(...)` resolves paths relative to the subproject;
- generated test output also belongs to the subproject;
- Inventory's stubs JAR carries **Inventory's** group/artifact/version;
- Checkout is a **consumer**, typically not needing the producer contract generation plugin just to use Stub Runner;
- avoid applying the plugin to every module via `allprojects` when only a few modules own contracts.

## 15. Source Sets and Generated Output Locations

In a normal build, the Spring Cloud Contract plugin generates **Java test sources** and stubs into directories under `build/`. The exact paths depend on the plugin version and configuration.

Some versions provide an option to customize where generated test sources are written, conceptually:

~~~groovy
contracts {
    generatedTestSourcesDir = file('build/generated-contract-tests')
}
~~~

**Do not add this snippet to a production build before confirming** that your plugin version's extension exposes that exact property and that compile/test tasks recognize that directory as generated test sources. The default location is usually safer unless the project has a specific requirement.

Rules:

1. **Contract sources** belong in source control, usually under `src/test/resources/contracts`.
2. **Generated Java tests** are build outputs and **do not need to be committed** to the source tree in normal workflows.
3. **Stub mappings** are also generated outputs, packaged into artifacts by tasks/pipelines.
4. Do not use `build/generated...` to store hand-written source contracts, because `clean` can wipe everything.
5. Do not point generated sources directly into `src/test/java` unintentionally, as that risks stale files or conflicts.

A common pitfall: the Gradle generation task successfully writes test sources, yet the `test` task fails to compile/run them because source set wiring was altered by another customization. **Having generated files on disk is not enough; the test runner must execute them.**

## 16. Gradle Tasks: Find the Exact Tasks Instead of Guessing

After the plugin is applied, you can inspect available tasks with:

~~~bash
# Use the project's Gradle Wrapper.
./gradlew tasks --all

# Inspect task dependencies without executing.
./gradlew test --dry-run

# Run the configured test task.
./gradlew clean test
~~~

On Windows:

~~~powershell
.\gradlew.bat tasks --all
.\gradlew.bat test --dry-run
.\gradlew.bat clean test
~~~

Some Spring Cloud Contract Gradle plugin lines include tasks related to:

- `generateContractTests` — generates producer tests;
- `generateClientStubs` — generates client/HTTP stubs;
- `verifierStubsJar` — packages the stubs artifact;
- `test` or a configured test task — executes generated tests.

**Task names and task relationships must be checked in the actual project/version.** Do not copy a task name from an older article if `tasks --all` does not list it. Likewise, `--dry-run` shows the planned task graph, **not proof** that tests actually passed.

When running `./gradlew clean test`, check:

1. Generation logs show the contracts were read;
2. Generated sources compiled;
3. The test runner executed the expected number of tests;
4. Assertions actually verified the real producer;
5. The build did not filter or skip generated contract tests.

## 17. Base Test and `testMode` Must Match

Some configuration combinations look plausible but fail in practice:

| Test mode | Base test | Result |
|---|---|---|
| `MockMvc` | `RestAssuredMockMvc.webAppContextSetup(...)` with real MVC context | Usually the right approach for Spring MVC |
| `MockMvc` | Sets up only `WebTestClient` | May fail to compile/run due to adapter mismatch |
| `WebTestClient` | Appropriate WebFlux test infrastructure | Works if SCC version supports it and wiring is right |
| HTTP server mode | Base test starts no server or provides no port | Generated tests may fail to connect |
| Messaging contract | Base test only configures MockMvc, no message verifier/trigger | Message tests cannot observe output |

Do not create an empty `ContractTestBase` class and assume the plugin knows how to run every producer stack automatically. The base test must provide the **exact hook** the generated sources expect.

For WebFlux or special HTTP setups, the safest approach is:

- choose the test mode per the version's documentation;
- run a trial generation of the sources;
- inspect imports, method calls, and class inheritance;
- prepare the base class accordingly;
- run the tests and verify responses from the **real producer**.

## 18. Custom Assertions in Contracts and Base Tests

A contract may need to validate rules that simple equality or regex cannot express well, such as `quantity` falling in the range 0 to 1000.

The Groovy DSL can use a custom command:

~~~groovy
response {
    status OK()

    body(
        sku: 'SKU-123',
        quantity: 12
    )

    bodyMatchers {
        jsonPath('$.quantity',
            byCommand('assertValidQuantity($it)'))
    }
}
~~~

Then the base test needs to provide the method:

~~~java
public void assertValidQuantity(Object actual) {
    if (!(actual instanceof Number)) {
        throw new AssertionError(
            "quantity must be a JSON number");
    }

    int quantity = ((Number) actual).intValue();

    if (quantity < 0 || quantity > 1000) {
        throw new AssertionError(
            "quantity outside [0, 1000]: " + quantity);
    }
}
~~~

This snippet illustrates connecting the **Groovy contract DSL** with **`baseClassForTests`**. If a JSON number can be a non-integer decimal, converting via `intValue()` can lose precision; in that case use `BigDecimal` and validate type/integrality as required.

In Gradle, what matters most is that generated tests **inherit the right base class**. If `baseClassForTests` points to the wrong package or the method is not visible, tests may fail to compile. Never remove a matcher just to make the build green; fix the base class or matcher according to the agreed contract.

## 19. HTTP POST Contracts: Verifying Request Bodies When Generating Stubs

A reservation-creation API takes a JSON request:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json

{"sku":"SKU-123","quantity":2}
~~~

Illustrative Groovy contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        url '/api/reservations'

        headers {
            contentType(applicationJson())
        }

        body(
            sku: 'SKU-123',
            quantity: 2
        )
    }

    response {
        status CREATED()

        headers {
            contentType(applicationJson())
        }

        body(
            reservationId: 'R-1001',
            status: 'RESERVED'
        )
    }
}
~~~

In **generated producer tests**, the sample request body is sent to the implementation. In **generated WireMock stubs**, the request section of the contract builds **matching rules**, while the response section becomes the status/headers/body returned to the consumer.

A conceptually similar mapping:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {"contains": "application/json"}
    },
    "bodyPatterns": [
      {"equalToJson": "{\"sku\":\"SKU-123\",\"quantity\":2}"}
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "reservationId": "R-1001",
      "status": "RESERVED"
    }
  }
}
~~~

This is an **illustrative mapping**, not the exact output of every SCC version. After a build, open the **actual generated mapping** to see whether the generator picked `equalToJson`, `matchesJsonPath`, `body`, or `jsonBody`. Do not assume every field is strictly validated just because the contract file includes a body.

## 20. Message Contracts Under the Same Gradle Configuration

Even though this lesson focuses on the `contracts` block, Spring Cloud Contract also supports **messaging contracts**. A messaging contract can describe:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        body(
            eventType: 'InventoryChanged',
            sku: 'SKU-123',
            available: true
        )
    }
}
~~~

With this contract:

- The plugin still locates the file using `contractsDslDir`.
- Generated tests require **`triggerInventoryChanged()`** in the base test or appropriate test support class.
- Tests must observe the event emitted by **the producer's production code** through appropriate messaging test infrastructure.
- `sentTo` is the destination observed by the verifier; it does not by itself prove Kafka partition keys, Rabbit routing keys, or that a production broker received the event.
- Consumers use Stub Runner/messaging test infrastructure where supported by the version, rather than treating a message contract as an HTTP WireMock mapping.

**Anti-pattern:** the base test manually pushes sample JSON into the test binder inside `triggerInventoryChanged()` so the generated test turns green, even though the real application service emits nothing. That is a false-green test. The base test should invoke the **production use case** so the output message is generated by real code.

## 21. Generating HTTP Stubs and the Stubs JAR in Gradle

Goal of the stubs branch:

~~~text
contracts/*.groovy or *.yml
    -> SCC generator
    -> HTTP WireMock mappings + response body files
    -> JAR classifier "stubs"
    -> artifact repository
    -> consumer's Stub Runner
~~~

Example artifact coordinates:

~~~text
groupId:     com.example
artifactId:  inventory-service
version:     1.3.0-rc1
classifier:  stubs
type:        jar
~~~

An illustrative filename:

~~~text
inventory-service-1.3.0-rc1-stubs.jar
~~~

With Gradle, the plugin may provide a task such as `verifierStubsJar` to package the artifacts. However, **creating the task or JAR does not automatically publish the artifact** to Maven local or a shared repository.

Verify that:

1. `generateClientStubs` or the corresponding task read the right contracts;
2. A mapping exists for every important scenario;
3. Body files (if used) were packaged;
4. The JAR has classifier `stubs` and the expected group/artifact/version;
5. The publication (if using `maven-publish`) attached the right stub artifact;
6. The consumer downloads **the exact candidate version**, not a stale cached artifact.

### Inspecting the JAR

After a real build generates the artifact:

~~~bash
# Replace the filename with the actual output in build/libs.
jar tf build/libs/inventory-service-1.3.0-rc1-stubs.jar
~~~

File locations and artifact names can vary. `jar tf` only inspects **entries inside the JAR**; it does not confirm that generated producer tests ran. Retain both test reports and the mapping list.

## 22. Publishing with `maven-publish`: Separating Gradle from SCC

Gradle `maven-publish` is responsible for uploading artifacts to a repository, whereas `contracts { ... }` configures SCC contract discovery and generation.

Illustrative organization:

~~~groovy
plugins {
    id 'maven-publish'
}

// Idea: the producer's publication needs to include
// the application artifact and the stubs JAR from the corresponding SCC task.
// Exact task names, artifact attachment syntax, and publication syntax
// must be verified against your actual Gradle/SCC plugin version.
~~~

Do not drop a publish configuration **guessing task names** into a pipeline without checking `tasks --all` and publish metadata. Design publishing in clear steps:

1. Configure repository URLs and credentials using a secret manager or CI variables;
2. Identify the exact `stubsJar`/`verifierStubsJar` task that exists;
3. Attach that task's output to the publication with **classifier `stubs`**;
4. Use candidate versions that do not overwrite one another across PRs/commits;
5. Run the publish stage only when producer verification passes;
6. Verify from the consumer job that the artifact resolves at the exact coordinates.

**Never store real tokens in `build.gradle` or commit credentials to Git.** Stub JARs should contain only synthetic fixtures, never real customer data or production secrets.

## 23. Consumer Using Stub Runner with a Gradle-Generated Artifact

A Checkout Service can test its real client against Inventory's stub:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.3.0-rc1:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryConsumerContractTest {

    @Test
    void consumerUsesInventoryStub() {
        // Call Checkout's real HTTP client against http://localhost:18081
        // and verify deserialization and business handling.
    }
}
~~~

`LOCAL` assumes the stub has been installed in a local source supported by Stub Runner. In multi-repository CI, a `REMOTE` repository with corresponding coordinates and credentials is typically used.

Do not merely spin up WireMock and assert raw HTTP responses with a test helper if the goal is to verify **Checkout's production client**. The real client must be verified for HTTP method, URL, headers, serialization, deserialization, and error mapping.

A consumer test passing against **the previous commit's stub** does not prove compatibility with the **candidate commit's API**.

## 24. Contracts Stored Outside the Producer Repository

Some organizations keep contracts in a separate repository or artifact. In that case, configuration is no longer as simple as reading `src/test/resources/contracts`.

Concepts to distinguish:

- **Local contracts:** contract sources reside inside the producer module.
- **External contracts:** contracts are fetched from another repository/source via contract dependency configuration.
- **Contract coordinates/path:** identifies the source, version, and contract slice for the producer.
- **Contracts mode:** how the tool locates contracts locally, in an artifact, or in a remote repository depending on the version.

SCC offers advanced configuration mechanisms for external contracts, but **their extension/property names depend on the version**. Do not guess `contractDependency`, `contractsMode`, or `contractsRepositoryUrl` syntax and put it into a real `build.gradle` without consulting the reference for your version.

Verification invariants that must hold:

1. The producer build downloads the exact **approved contract revision**.
2. Generated tests bind to that contract.
3. The stub artifact is built from the **same revision**.
4. The consumer uses that exact candidate artifact/revision.
5. CI records the contract source and commit if repositories are split.

For your first hands-on setup, start with **local `contractsDslDir`** to minimize moving parts that can fail.

## 25. How Does Kotlin DSL `build.gradle.kts` Differ?

If the project uses `build.gradle.kts`, note the differences:

| Gradle Groovy DSL | Gradle Kotlin DSL |
|---|---|
| `id 'org.springframework.cloud.contract' version '...'` | `id("org.springframework.cloud.contract") version "..."` |
| `file('src/test/resources/contracts')` | `file("src/test/resources/contracts")` |
| Property assignment with Groovy syntax | Property assignment via the Kotlin/property API exposed by the plugin version |
| Groovy closure `contracts { ... }` | Kotlin lambda/type-safe accessor or `configure<...>` if the extension lacks an accessor |

Illustrative plugin declaration (versions are placeholders):

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "BOOT_VERSION"
    id("org.springframework.cloud.contract") version "CONTRACT_PLUGIN_VERSION"
}
~~~

For the `contracts` block in Kotlin DSL, **do not mechanically replace every single quote in Groovy with double quotes**. A Gradle extension may expose property setters, Java methods, or require `configure<ContractVerifierExtension>`, depending on the plugin version and type-safe accessors.

Safe approach:

1. Check the Spring Cloud Contract Gradle plugin documentation **for your exact version** for Kotlin DSL examples.
2. Inspect Gradle Kotlin DSL accessors/IDE autocomplete for the `contracts` extension.
3. Use the exact property types rather than guessing `.set(...)` for every field.
4. Run generation in a trial project and inspect generated tests/stubs.
5. Do not paste `build.gradle` code verbatim into `build.gradle.kts`.

If your course or project already uses **Groovy Gradle DSL**, the main example in Section 6 is sufficient to understand how to configure the extension.

## 26. Checking Version Resolution and Plugin Classpath

A common failure occurs when dependency versions are managed by a BOM, yet **Gradle cannot resolve the plugin**:

~~~text
Plugin [id: 'org.springframework.cloud.contract',
        version: '...'] was not found
~~~

This is a **plugin resolution** error, not a contract syntax error.

Common causes:

- The plugin version does not exist or is incompatible;
- `pluginManagement.repositories` in `settings.gradle` is restricted;
- The build is running offline without the plugin cached;
- A corporate proxy or private repository blocks access;
- The Gradle/Java toolchain is too old or too new for the plugin.

How to diagnose:

~~~bash
./gradlew --version
./gradlew help --stacktrace
./gradlew dependencies --configuration testRuntimeClasspath
~~~

The third command inspects **test dependencies**, not the **plugin classpath/plugin resolution**. Read Gradle errors at the right phase: plugin lookup, dependency resolution, test compilation, execution, or packaging.

Do not try to tweak `contractsDslDir` while Gradle has not yet resolved the plugin, and do not work around plugin version errors by removing contract tests from the build.

## 27. When Gradle Build Is Green but No Contract Tests Ran

One of the most dangerous situations:

~~~text
./gradlew clean test
BUILD SUCCESSFUL

... yet zero generated contract tests actually ran.
~~~

Possible causes:

- `contractsDslDir` points to an empty directory or the wrong module;
- contracts were not committed or have an unrecognized file extension;
- the plugin was not applied to the producer module;
- the Gradle test task was customized in a way that skips generation;
- the generated source set is not wired to the compile/test task;
- `test` is disabled, excluded, or filtered;
- the pipeline ran `:some-other-module:test` instead of `:inventory-service:test`;
- the repository has contracts, but they failed to parse into generated tests as expected.

**Do not assume SCC always fails by default when no contracts exist.** Behavior varies by version and configuration. For producers required to have contracts, CI should assert **parsed contracts > 0** and **executed generated tests > 0**.

A basic guard might count files under the source directory, though file count **does not prove** the plugin read them successfully. Stronger evidence comes from generated sources, test reports, and stub mapping counts.

## 28. When Contracts or Base Classes Are Wrong

| Symptom | Error layer | How to fix |
|---|---|---|
| Groovy contract missing `}` | Parsing | Fix the DSL and inspect line/column numbers |
| YAML `status` has wrong indentation | Parsing/schema | Fix YAML indentation/structure |
| DSL references a missing body file | Resource resolution | Fix the fixture path |
| JSONPath matcher points to a missing field | Generation/test semantics | Align body and matcher with the real contract |
| Generated test cannot find `ContractTestBase` | Compilation | Fix `baseClassForTests`, package, or test source set |
| Base test uses a different adapter than `testMode` | Compilation/execution | Align test mode and base initialization |
| Test runs but returns 404 | Producer verification | Check endpoint, context, and request |
| Test stays green even when producer changes a field | Base test fakes responses or tests are not running | Inspect generated sources and run mutation check |
| Mappings exist but stubs JAR is empty | Packaging | Inspect the task graph and artifact inputs |
| Consumer uses stale stubs | Resolution/cache | Pin exact candidate version/commit |

**Pinpointing errors by layer** avoids bad "fixes" like deleting contracts or disabling generated tests when the root cause is merely a typo in `baseClassForTests`.

## 29. Negative Testing to Prove the Gradle Configuration Works

A trustworthy build configuration must **fail when the producer violates the contract**. In a test branch:

1. Start with a valid GET inventory contract and a green producer test.
2. Change the controller/service code to return `available: false` when the contract requires `true`.
3. Run generated producer tests.
4. **Expected:** the test turns red on the body assertion.
5. Revert the production code.
6. Temporarily move the contract out of `contractsDslDir`.
7. Run the build/CI gate and confirm a producer module requiring contracts **is blocked due to missing contracts**.
8. Restore the contract and re-run tests.

If **modifying the producer does not turn the test red**, check two possibilities:

- Tests were not generated or did not run;
- The base test uses a **fake controller/mock service** returning the contract's own sample data.

If **removing contracts leaves the pipeline green**, you need a contract/test count guard; never treat such a build as proof that the API is protected.

## 30. Checking Stub Artifacts After a Gradle Build

Having contract sources and passing producer tests is **not yet enough** for consumers to download usable stubs. Verify that:

1. The generation task created WireMock mappings for HTTP contracts.
2. Referenced body files (if any) were copied/packaged properly.
3. The stubs JAR actually exists in the producer module's output.
4. The JAR has classifier `stubs` and the exact candidate version.
5. The artifact was installed/published to the repository Stub Runner reads from.
6. Consumer tests use exact artifact coordinates, not uncontrolled `latest`/`+`.
7. The consumer exercises its **real HTTP client/handler** and asserts results.
8. Tests also cover important business error cases, not only the happy path.

Remember to distinguish a **business 404** defined by the contract from a **WireMock unmatched request 404** caused by the client sending the wrong URL, headers, or body. A consumer test that only asserts status 404 can mask request serialization bugs.

## 31. CI/CD: Connecting Gradle Producer Tests to Consumer Stub Runner

~~~mermaid
flowchart TD
    A["Producer PR: code + contract + build.gradle"] --> B["Gradle resolves plugin/dependencies"]
    B --> C["Generate + compile contract tests"]
    C --> D{"Tests executed and passed?"}
    D -- "No" --> X["BLOCK"]
    D -- "Yes" --> E["Generate mappings + package stubs JAR"]
    E --> F["Publish candidate artifact with unique version"]
    F --> G["Consumer tests use Stub Runner and real client"]
    G --> H{"Consumer compatible?"}
    H -- "No" --> X
    H -- "Yes" --> I["Proceed to release gates"]
~~~

In the producer Gradle build:

~~~bash
./gradlew clean test
~~~

This reference command **runs only the tasks wired into the task graph**. Packaging/publishing stages may require explicit tasks. In a multi-project build:

~~~bash
./gradlew :inventory-service:clean :inventory-service:test
~~~

Subproject names are examples; use the actual names from `settings.gradle`.

**Required gates:**

| Gate | Evidence |
|---|---|
| Contract discovery | Expected contracts were detected |
| Generated tests | Test sources exist and compile |
| Producer verification | Test report shows **executed tests > 0** and assertions passed |
| Stub packaging | Mappings/JAR contain expected entries with right classifier |
| Candidate provenance | Unambiguous version + commit SHA |
| Consumer verification | Stub Runner loads candidate artifact; real consumer client runs |
| Breaking-change detection | Consumer tests fail when an incompatible response schema is introduced |

CI should record the **Gradle Wrapper version, JDK, Spring Boot/Cloud/Contract versions, test mode, executed test count, artifact coordinates, and commit**. Do not pass `--offline` in CI if candidate artifacts may not be cached yet, unless distribution is explicitly controlled.

## 32. Hands-On Exercise A — Setting Up the Gradle `contracts` Extension

**Goal:** have the Gradle producer pick up a contract and generate runnable tests.

1. Prepare a Spring MVC Inventory application with a GET endpoint.
2. Select compatible JDK/Gradle/Boot/Cloud/Contract versions.
3. Apply the `org.springframework.cloud.contract` plugin.
4. Declare the `spring-cloud-starter-contract-verifier` test dependency.
5. Add:

~~~groovy
contracts {
    contractsDslDir = file('src/test/resources/contracts')
    testMode = 'MockMvc'
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

6. Create `ContractTestBase` wired to the real Spring MVC application context.
7. Write `inventory/get-stock.groovy` from Section 8.
8. Run `./gradlew tasks --all` and `./gradlew clean test` in your project environment.
9. Inspect generated sources, test reports, and status/body assertions.

**Deliverables:** `build.gradle`, the contract, the base test, and evidence of generated test execution.

## 33. Hands-On Exercise B — Changing the Contract Directory and Detecting Misconfigurations

1. Move the contract from `src/test/resources/contracts` to `contract-specifications` on a test branch.
2. Keep the old `contractsDslDir` and observe the plugin failing to read the contract as expected.
3. Update the configuration to:

~~~groovy
contracts {
    contractsDslDir = file('contract-specifications')
    testMode = 'MockMvc'
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

4. Re-run generation and confirm generated tests appear.
5. Intentionally point `baseClassForTests` to a wrong package: test compilation must fail if generated tests truly extend the base class.
6. Restore the correct base class.
7. Change the production response `available` from `true` to `false` and verify the test turns red.
8. Revert the code and re-run until green.

**Deliverables:** a table documenting discovery, compilation, and verification errors alongside layer-appropriate fixes.

## 34. Hands-On Exercise C — Generating Stubs and Verifying the Consumer

1. Generate HTTP stub mappings from the Inventory contract.
2. Package the stubs JAR using the appropriate plugin task.
3. Inspect JAR contents and candidate version.
4. Install/publish to the target repository.
5. Create a Checkout consumer test using Stub Runner to load Inventory's candidate artifact.
6. Have the real client call `GET /api/inventory/SKU-123` and assert the DTO.
7. Add a `404 SKU_NOT_FOUND` contract/error case and test that the client distinguishes a business 404 from an unmatched WireMock 404.
8. On a test branch, rename `available` to `inStock` in the producer and contract, and build a new candidate stub.
9. Run the existing consumer against the **new artifact** to detect the breaking change.
10. Save producer/consumer results together with stub coordinates and commit.

**Deliverables:** generated mappings, JAR, Stub Runner logs, consumer test report, and a migration plan if a breaking change occurred.

## 35. Gradle Configuration Review Checklist

- [ ] Using Gradle Wrapper and a JDK compatible with Spring Boot/Cloud/Contract.
- [ ] `org.springframework.cloud.contract` plugin is applied in the **right producer module**.
- [ ] Plugin version matches the chosen BOM/dependency versions.
- [ ] `contractsDslDir` points to the directory containing Groovy/YAML contracts.
- [ ] Contract files have valid DSL structure and are not missed due to extension/path issues.
- [ ] `testMode` matches the Spring MVC/WebFlux/HTTP stack.
- [ ] `baseClassForTests` points to the right package and the class exists in test sources.
- [ ] Base test connects to **real producer code**, not a fake returning canned contract responses.
- [ ] If multiple groups exist, base class mappings are verified in generated sources.
- [ ] Generated Java sources are actually compiled and executed in the Gradle test task.
- [ ] **Executed contract test count > 0** for producer modules required to have contracts.
- [ ] No `test.enabled = false`, excludes/filters, or profiles skip generated tests.
- [ ] Mappings/body files are generated and present in the stubs JAR.
- [ ] Candidate stubs JAR has the exact group/artifact/version/classifier.
- [ ] Publication/repository can serve the consumer's Stub Runner.
- [ ] Consumer tests use the **candidate stub and real client**.
- [ ] CI blocks when producer tests fail, contracts are missing, or the stubs artifact is empty.
- [ ] Breaking changes in APIs/messages were tested against the existing consumer.
- [ ] No credentials, secrets, or real customer data are committed into contract fixtures.
- [ ] Build logs/test reports suffice to trace version, commit, tasks, and failures by layer.

## 36. Self-Check Questions

**1. Is `contracts { ... }` in `build.gradle` an HTTP contract?**

No. It configures the **Gradle plugin** on how to discover and generate tests/stubs. HTTP contracts live in Groovy/YAML files describing requests and responses.

**2. What is `contractsDslDir` used for?**

It specifies the contract source directory that the plugin will read. If misconfigured, the project may fail to generate contract tests even when files exist elsewhere on disk.

**3. What is the role of `baseClassForTests`?**

It gives generated tests access to the test environment and setup needed to call the real producer, or helpers/assertions required by contracts. A wrong base class name, package, or test mode causes generated tests to fail compilation or execution.

**4. Why is choosing the wrong `testMode` dangerous?**

Because generated tests may use an HTTP adapter incompatible with the base class. Contracts may parse fine yet fail to verify the producer implementation, or produce tests that do not run.

**5. Is a passing `./gradlew clean test` enough to claim contracts are verified?**

Not yet. You must check **contract discovery, generated sources, and executed test count**. A build can pass with zero contracts or skipped generated tests depending on configuration.

**6. Why should you inspect the stubs JAR after producer tests pass?**

Because mappings/fixtures might not have been packaged or the artifact might not have been published. Consumer Stub Runner can only load an artifact that has valid contents in the expected repository/version.

**7. Can both Groovy contracts and YAML contracts be used in the same project?**

Yes, when supported by the plugin and when they describe **different scenarios**. Do not create two identical contracts just to have both syntaxes, as that can produce duplicate tests and mappings.

**8. If both producer and contract rename `available` to `inStock` and generated tests pass, is the consumer already safe?**

No. Existing consumers may still read `available`. You must build the **new commit's candidate stubs JAR** and run consumer tests to evaluate compatibility.

**9. Why shouldn't you apply the plugin to every subproject if only one service is a producer?**

Because it can create unnecessary tasks/generation, lead to confusion around **zero contracts** or source paths, and obscure which modules actually require verification.

## 37. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier workflow, Groovy/YAML DSL, producer tests, and Stub Runner.
- [Spring Cloud Contract — Gradle Project Features](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): plugin, `contracts` extension, task generation, and stubs.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML HTTP/message contracts and matchers.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): request/response structure.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): consumer tests with stub artifacts.
- [Gradle — Writing Build Scripts](https://docs.gradle.org/current/userguide/writing_build_scripts.html): Gradle Groovy/Kotlin DSL and extensions.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): root project, subprojects, and task targeting.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publications and repositories.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): inspecting mappings generated from HTTP contracts.

**Version note:** `contracts` extension properties, Gradle task names and relationships, test modes, generated source directories, base class selection mechanisms, and publication artifacts can change across **Spring Cloud Contract plugin versions**. Gradle blocks using placeholder versions in this lesson **cannot be run verbatim**; replace them with real compatible versions. The content illustrates the technical path and checkpoints, **not a report that build commands were executed**.

---

**Key takeaway:** The `contracts { ... }` block in Gradle determines **where SCC reads contracts from and how it generates producer tests**. `contractsDslDir` selects the Groovy/YAML source, `testMode` chooses the test adapter, and `baseClassForTests` connects generated tests to the **real producer implementation**. After producer tests pass, inspect the mappings/stubs JAR and run **Stub Runner with the exact commit's candidate artifact** to verify the consumer. A reliable pipeline must prove each stage actually ran, not merely see Gradle report `BUILD SUCCESSFUL`.
