# Initializing the Controller or Application Under Verification

## Learning objectives

In **Spring Cloud Contract**, a contract describes the behavior a **producer** (the service providing an API or emitting messages) commits to a **consumer** (the service calling the API or receiving messages). Contracts written in **Groovy/YAML DSL** can be used to generate **producer-side tests** and **stubs** for consumer testing via **Stub Runner**. When integrated into CI, both test suites help catch breaking interface changes.

However, a generated producer test cannot verify an uninitialized controller on its own. One of the most important responsibilities of the **base test class** is standing up the right **target object or application under verification**, with deterministic enough state for contract-generated requests to receive the expected responses.

After this lesson, you will be able to:

- Explain the role of `baseClassForTests` in HTTP test generation.
- Initialize a **standalone controller** using `RestAssuredMockMvc.standaloneSetup(...)`.
- Initialize a **Spring WebApplicationContext** and use `RestAssuredMockMvc.webAppContextSetup(...)`.
- Distinguish `MOCKMVC`, `WEBTESTCLIENT`, and `EXPLICIT`, especially the difference between in-process invocation and sending HTTP over a real socket.
- Prepare fixtures, fake/mock dependencies, and test configuration so generated tests run reliably.
- Read generated tests and test failures to confirm you are verifying the **real producer**, not a stub returning hardcoded data.
- Know what scope should be protected by producer contract tests versus integration tests, consumer tests with Stub Runner, or additional CI checks.

## 1. Where does the base test class sit in the verification chain?

Suppose **Inventory Service** is the producer of the inventory API:

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

**Checkout Service** is the consumer: it reads `available` and `quantity` to decide whether to allow placing an order. The producer team writes a contract checking this response; the tool generates a test that sends `GET /api/inventory/SKU-101` and asserts status, headers, and body.

One question remains, however: **where does the test send the request?**

- To an `InventoryController` instantiated directly by the test?
- To the entire Spring Boot application's web context?
- Or to an application listening on a real TCP port?

The base class provides the **shared setup** so generated tests work with whichever choice you make.

~~~mermaid
flowchart TD
    A["Groovy/YAML contract"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer test"]
    C --> D["Base test class"]
    D --> E{"Test mode"}
    E -->|MOCKMVC standalone| F["Controller + fake/mock service"]
    E -->|MOCKMVC context| G["Spring WebApplicationContext"]
    E -->|EXPLICIT| H["HTTP app running on real port"]
    E -->|WEBTESTCLIENT| I["WebFlux handler/controller"]
    B --> J["Generated stub artifact"]
    J --> K["Stub Runner for consumer tests"]
~~~

**Note:** generated producer tests run against producer code; the stub artifact is for the consumer. If the producer's base class accidentally returns fixed mock responses without passing through the controller/logic to be protected, tests may pass without providing the proof the team expects.

## 2. Three components that must align

A producer verification test is only trustworthy when all three parts are present:

| Component | Example content | Responsibility |
|---|---|---|
| **Contract** | `GET /api/inventory/SKU-101` must return `200` with the agreed JSON | Defines the behavior to verify |
| **Generated test** | Sends the request, asserts status/headers/JSON | Checks the producer against the contract |
| **Base test class** | Stands up the controller or application, provides services and seed data | Enables generated tests to call the verification target |

If you have a contract without a controller yet, generated tests may fail due to unconfigured MockMvc, return `404`, or fail to load the context.

If you have a controller whose service reads from an empty real database, tests may return `404` instead of `200` due to **seed data**, not DSL syntax.

If the base class completely replaces the controller with a WireMock stub returning the right JSON, tests no longer verify the intended producer implementation.

Therefore, **base class setup is a test-scope decision**, not merely a way to turn a red pipeline green.

## 3. Defining an HTTP contract before writing the base class

Example Groovy DSL located at `src/test/resources/contracts/inventory/stockAvailable.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'SKU-101 has 8 items in stock'

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

This is the contract **the producer must satisfy**; it does not dictate whether the controller should be instantiated with `new` or which port the application should bind to. That part is the responsibility of the **base class and plugin configuration**.

YAML DSL can express the same scenario, for example:

~~~yaml
description: 'SKU-101 has 8 items in stock'
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

In a real project, **pick one format** for this scenario; avoid keeping both Groovy and YAML as two contracts with duplicate request conditions without a clear reason.

## 4. Declaring the base class in the plugin

### Maven

In the **producer** module, configure the Spring Cloud Contract Maven plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <!-- Fill in the plugin version compatible with Spring Boot/Cloud BOM -->
            <version>REPLACE_WITH_MATCHING_CONTRACT_VERSION</version>
            <extensions>true</extensions>
            <configuration>
                <testMode>MOCKMVC</testMode>
                <testFramework>JUNIT5</testFramework>
                <baseClassForTests>
                    com.example.inventory.contract.InventoryContractBase
                </baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

In the example, `InventoryContractBase` is a **team-authored class name**, not a class generated by Spring Cloud Contract. The plugin uses that name so generated tests extend or bind to the matching setup.

`REPLACE_WITH_MATCHING_CONTRACT_VERSION` is a placeholder to replace with a real version; it is not a downloadable artifact. Typically the project already uses Spring Boot parent/BOM and Spring Cloud BOM to manage compatible dependencies, but the **build plugin version** must still be managed explicitly.

Typical producer test dependencies:

~~~xml
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
~~~

The real HTTP application still needs its corresponding starter, such as `spring-boot-starter-web` for Spring MVC. Test libraries belong in **test scope**; there is no need to package them into the production runtime just to generate contract tests.

### Gradle

In a producer module with the matching Spring Cloud Contract Gradle plugin applied:

~~~groovy
contracts {
    testMode = 'MOCKMVC'
    testFramework = 'JUNIT5'
    baseClassForTests =
        'com.example.inventory.contract.InventoryContractBase'
}
~~~

This is only the `contracts` configuration block, not the entire `build.gradle`. The project needs the `java`/Spring Boot plugins, repositories, BOM, and appropriate dependencies.

**Version note:** how modes, test frameworks, tasks, and output names are specified can vary across plugin lines. If the project uses JUnit 5, the base class needs a lifecycle hook that generated tests/the test framework actually support; do not copy `@Before` from a JUnit 4 example into JUnit 5 code and assume it runs.

## 5. Approach 1 — Initializing a standalone controller with MockMvc

This is a fast, controllable approach when you want to verify **HTTP mapping, serialization, and controller behavior** with a fake service.

### A minimal controller

Suppose the producer code has the following response type and service (Java 17+):

~~~java
package com.example.inventory;

public record StockResponse(
    String sku,
    boolean available,
    int quantity
) {}
~~~

~~~java
package com.example.inventory;

import java.util.Optional;

public interface InventoryService {
    Optional<StockResponse> findBySku(String sku);
}
~~~

The production controller could be:

~~~java
package com.example.inventory;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {
    private final InventoryService inventoryService;

    public InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @GetMapping("/{sku}")
    public ResponseEntity<StockResponse> find(@PathVariable("sku") String sku) {
        return inventoryService.findBySku(sku)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

The controller knows nothing about Spring Cloud Contract. It simply implements the HTTP contract. In production, `InventoryService` might query a database, compute inventory, or call another service; in contract tests, we can supply **a mock service**.

### Base test class using `standaloneSetup`

Example file `src/test/java/com/example/inventory/contract/InventoryContractBase.java`:

~~~java
package com.example.inventory.contract;

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
    protected void setUpContractController() {
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

**What the example is doing:**

1. Creates a test-only `InventoryService` mock.
2. Stubs `SKU-101` to return a `StockResponse` with the values expected by the contract.
3. Instantiates the **real InventoryController** from producer code, passing the mock into its constructor.
4. Registers the controller with `RestAssuredMockMvc.standaloneSetup(...)` so generated tests in MockMvc mode dispatch requests in-process.
5. Does not need to start a web server on a TCP port.

**Outcome:** if the controller breaks the `/{sku}` mapping, returns a different status, or serializes JSON differently from the contract, the generated producer test can fail.

However, a mocked `InventoryService` does not prove the producer's real database/repository works properly. Therefore, recognize the **test boundary**: this is contract testing at the controller layer with isolated dependencies, not an end-to-end test.

### When does this approach fit?

- The controller uses constructor injection and is easy to instantiate.
- Request mapping, serialization, and controller logic need protection.
- Services depend on databases/networks that are slow or hard to reproduce.
- The team wants contracts to run quickly on every PR.
- Behavior can be reduced to deterministic cases using mocks/fakes.

### What standalone setup can easily miss

`standaloneSetup` does not automatically assemble the **entire** Spring Boot configuration. Components that require explicit configuration or addition if the contract depends on them include:

- Global `@ControllerAdvice` / exception handlers.
- Custom converters, Jackson modules, or specialized date/time formats.
- Filters, interceptors, Spring Security filter chain, authentication.
- Validators and custom validation configurations.
- Spring-managed beans instead of manually passed collaborators.

If a contract specifies `404` or an error body from a global exception handler, a base class that only instantiates the controller standalone may bypass the handler and produce results different from the real app. In that case, add the corresponding MockMvc configuration or switch to testing with an application context.

**Do not "fix" failures by making a mock return the exact expected HTTP response while bypassing the controller.** Doing so may fail to prove what the consumer needs.

## 6. Approach 2 — Building the Spring Boot application's WebApplicationContext

When the HTTP interface relies heavily on the application's MVC configuration, you can boot the web context and let Spring manage controllers, serialization, bean wiring, and related components.

Example base class:

~~~java
package com.example.inventory.contract;

import com.example.inventory.InventoryApplication;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.context.WebApplicationContext;

@SpringBootTest(
    classes = InventoryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@ActiveProfiles("contract")
public abstract class InventoryContractBase {

    @Autowired
    WebApplicationContext webApplicationContext;

    @BeforeEach
    protected void setUpContractContext() {
        RestAssuredMockMvc.webAppContextSetup(
            webApplicationContext
        );
    }
}
~~~

Here:

- `@SpringBootTest` initializes the **Spring application context** of Inventory Service.
- `webEnvironment = MOCK` does not require opening a real HTTP port.
- `RestAssuredMockMvc.webAppContextSetup(...)` binds generated MockMvc tests to the web context.
- The `contract` profile is only an illustrative name: the project must supply the corresponding configuration and fixtures; declaring the profile does not create a database/fakes automatically.
- Generated tests still use **in-process MockMvc** when the plugin uses `MOCKMVC`.

**Compared to standalone**, this approach verifies more real application configuration, but can be slower and more coupled to brokers, databases, environment config, or unrelated beans.

### Preparing data in the test context

If Inventory Service uses a repository, ensure:

- Record `SKU-101` with quantity `8` exists before the request runs.
- Data from other tests does not alter the outcome.
- The `contract` profile points to test resources, not a production database.
- Results do not depend on current date/time, randomness, external consumers, or prior state.

You can use an **isolated test database**, fake beans, mocks registered in the Spring test context, or data seeding in a lifecycle hook. Exact annotation names and bean-overriding mechanisms depend on the Spring Boot/Spring Framework version; for example, modern releases use `@MockitoBean`, while older projects may use `@MockBean`. Choose the mechanism supported by your project version instead of copying multiple annotations from different docs and mixing them.

If rollback/transactions are needed, verify whether the test transaction and request actually share the same boundary; with HTTP over a real server, the test method's transaction does not necessarily cover the server's transaction.

### Be careful with security and filters

`webAppContextSetup` ensures MockMvc has a web context, but how **Spring Security filter chain** and special filters apply may require additional test configuration. Do not infer that an unauthenticated `200` test verified real security. If contracts promise `401`/`403` or security headers, inspect which filter chain generated tests actually execute and add appropriate tests.

## 7. Approach 3 — Running the application on a real HTTP port with EXPLICIT

If you need to verify communication over a real HTTP socket rather than MockMvc, Spring Cloud Contract supports `EXPLICIT` test mode.

In the Maven plugin:

~~~xml
<configuration>
    <testMode>EXPLICIT</testMode>
    <baseClassForTests>
        com.example.inventory.contract.InventoryHttpContractBase
    </baseClassForTests>
</configuration>
~~~

Or Gradle:

~~~groovy
contracts {
    testMode = 'EXPLICIT'
    baseClassForTests =
        'com.example.inventory.contract.InventoryHttpContractBase'
}
~~~

Spring Boot base class:

~~~java
package com.example.inventory.contract;

import com.example.inventory.InventoryApplication;
import io.restassured.RestAssured;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(
    classes = InventoryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@ActiveProfiles("contract")
public abstract class InventoryHttpContractBase {

    @LocalServerPort
    int port;

    @BeforeEach
    protected void configureHttpClient() {
        RestAssured.baseURI = "http://localhost";
        RestAssured.port = port;
    }
}
~~~

`@LocalServerPort` provides the port assigned by Spring Boot to the test application. `RestAssured` configures the URL/port so `EXPLICIT`-generated tests call the **real endpoint over loopback networking**, instead of calling in-memory MockMvc.

Key points:

- `RANDOM_PORT` avoids fixed-port contention in CI environments.
- Starting a real server costs more than standalone/controller tests.
- Filters, serialization, servlet container, and real HTTP boundaries participate closer to production.
- If the application uses a database or external services, isolated test configuration is required.
- `RestAssured.baseURI` and `RestAssured.port` are mutable shared configuration; when running tests concurrently in one JVM, ensure tests do not overwrite each other's settings.

**Do not just add `@SpringBootTest(RANDOM_PORT)` to the base class while keeping `testMode` as `MOCKMVC` and expect requests to go over a socket.** The plugin determines test generation mode; the base class must **match** that mode.

## 8. What if the producer is WebFlux/reactive?

For Spring WebFlux, Spring Cloud Contract offers `WEBTESTCLIENT` mode to generate tests using WebTestClient instead of MockMvc. A minimal base class might use:

~~~java
import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import org.junit.jupiter.api.BeforeEach;

public abstract class ReactiveInventoryContractBase {

    @BeforeEach
    protected void setUp() {
        RestAssuredWebTestClient.standaloneSetup(
            new ReactiveInventoryController(/* fake dependencies */)
        );
    }
}
~~~

The snippet above only illustrates the **idea**; `ReactiveInventoryController` and its dependencies are project-defined. When using a full WebFlux context, initialize and bind WebTestClient according to Spring Cloud Contract and library version documentation.

| Characteristic | `MOCKMVC` | `WEBTESTCLIENT` | `EXPLICIT` |
|---|---|---|---|
| Typical stack | Servlet Spring MVC | Spring WebFlux/reactive | Live HTTP test app |
| TCP socket required? | No | Not necessarily | Yes |
| Basic setup | `RestAssuredMockMvc.standaloneSetup` or `webAppContextSetup` | `RestAssuredWebTestClient` with matching controller/context | Start server + configure HTTP client |
| Isolation level | From a single controller to web context | Depends on standalone/context | Closer to end-to-end HTTP testing |
| When to choose | MVC producer, fast HTTP contracts | WebFlux producer | Need to verify context path, filter/HTTP stack, or real integration |

You do not need to use every mode simultaneously. Pick **one mode suited to the producer** for the contract group under test; separate integration tests can use another mode when needed.

## 9. What should the base class prepare and what should it avoid?

### Responsibilities the base class should handle

1. **Initialize the right entry point:** real controller, real web context, or application listening on a real port.
2. **Provide controllable dependencies:** mocks/fakes or a seeded test database.
3. **Configure request infrastructure:** MockMvc, WebTestClient, or RestAssured according to the chosen test mode.
4. **Ensure deterministic data:** SKUs and sample states must repeat identically across runs.
5. **Ensure isolation:** prevent earlier test cases from affecting later ones.
6. **Choose safe profiles and configs:** do not call production databases, brokers, or external APIs unintentionally.
7. **Provide meaningful helpers if the DSL requires them:** such as custom assertion functions or methods invoked from contracts when supported by configuration.

### Things to avoid

- Do not mock **the entire HTTP response of the endpoint under verification** and claim producer contract tests verified the controller.
- Do not create test state by hard-mutating production data.
- Do not depend on execution order or a fresh random ID per run if the contract expects specific values.
- Do not build an overly broad base class containing dozens of unrelated mocks that let tests interfere with one another.
- Do not edit generated tests directly, since they are regenerated on build.
- Do not ignore false positives: a green test with a mocked service only proves **the controller and mappings tested**; it does not prove real DB queries or broker operations.

## 10. Organizing multiple base classes when APIs need different setups

Not all contracts fit a single shared environment. For example:

- `inventory`: tests controllers with a fake `InventoryService`.
- `payments`: requires a context with transactions, validators, and exception handlers.
- `notifications`: uses messaging mode rather than HTTP.
- `admin`: requires a different security test setup.

Spring Cloud Contract provides configuration for a **shared base class** and mechanisms to **map base classes by contract package/folder** (such as `packageWithBaseClasses` or base class mappings depending on the plugin). As the number of groups with distinct setup needs grows, split dedicated base classes per group instead of writing `if` branches checking test names.

Suggested directory layout:

~~~text
src/test/resources/contracts/
├── inventory/
│   ├── stockAvailable.groovy
│   └── stockNotFound.groovy
└── payments/
    ├── paymentAccepted.yml
    └── paymentRejected.yml

src/test/java/com/example/contract/
├── InventoryContractBase.java
└── PaymentsContractBase.java
~~~

The directory layout above is an **organizational suggestion**; it does not automatically trigger matching base class selection. You must configure mappings according to your **Maven/Gradle plugin version's** capabilities and read generated tests to confirm they inherit the right base class.

A good convention: name the base class after **what is stood up** and **the test layer**, e.g. `InventoryControllerContractBase` or `InventoryHttpServerContractBase`. Reviewers then immediately know whether tests run standalone MockMvc or a real application.

## 11. How are generated tests created and how do you verify the setup?

Once the producer build has the right plugin configured, you can use the Maven lifecycle:

~~~bash
./mvnw clean verify
~~~

With Gradle, use the contract tasks integrated by your project's plugin version; to list tasks:

~~~bash
./gradlew tasks --all
~~~

Depending on configuration, generated tests typically appear in output locations such as:

~~~text
Maven:
  target/generated-test-sources/contracts/

Gradle:
  build/generated-test-sources/contracts/
~~~

These are **common paths** and may be overridden by build configuration. Inspect the build logs.

When reading a generated test, check:

- Is the base class name exactly `InventoryContractBase`?
- Is the test compiled and **actually executed**?
- Does it call `GET /api/inventory/SKU-101` properly?
- Do assertions check `200` and JSON `sku`/`available`/`quantity` with the expected types?
- Does it use `RestAssuredMockMvc` or socket-based `RestAssured` matching the chosen mode?
- Is any bean, mock, fake, or fixture uninitialized and causing unintended failures?

Generated test logic can be summarized as follows (**pseudocode**, not verbatim output of a specific generator):

~~~text
class StockAvailableTest extends InventoryContractBase

test "validate_stockAvailable":
    given:
        GET /api/inventory/SKU-101
        Accept: application/json

    when:
        send request to controller/app prepared by base class

    then:
        status == 200
        Content-Type == application/json
        body.sku == "SKU-101"
        body.available == true
        body.quantity == 8
~~~

**Do not confuse "generated test was created" with "generated test ran."** The plugin may create files while the test runner fails to discover them, tests are disabled, or build filters skip them. Always inspect the test report, executed test count, and actual results.

## 12. Common setup errors and root-cause troubleshooting

| Symptom | Common cause | How to resolve |
|---|---|---|
| No generated tests created | Plugin not applied, wrong contract path, or build phase/task did not run | Check plugin config, DSL input, and generation logs |
| Generated tests fail to compile | Wrong `baseClassForTests` name/package, class outside test source set, or wrong framework | Verify full class name, imports, and JUnit version |
| `RestAssuredMockMvc` not initialized | `@BeforeEach`/`@Before` did not run or setup was not called | Check lifecycle hook, generated class, and test framework |
| Test returns `404` when contract expects `200` | Controller not registered, wrong URL mapping, or missing fixture data | Check real controller, base class, and request path |
| Test gets `500` / `NullPointerException` | Mock service missing stubbing or uninitialized bean | Check constructor injection, mock answers, and fixtures |
| App context fails to start | Missing bean, wrong test config, external DB/broker connection | Use test profile/fakes or appropriate context config |
| Wrong JSON response format | Standalone setup lacks production converters/Jackson modules | Use matching context or register required converters |
| Unexpected `401`/`403` | Security filters not matching or different auth setup | Inspect filter chain and test identity |
| `EXPLICIT` cannot connect | Server not running, wrong port, stale baseURI | Use `RANDOM_PORT` and configure RestAssured properly |
| Tests green but real service breaks | Mock replaced the service so DB/network was not tested | Add integration tests for critical dependencies |
| Flaky tests during parallel runs | Shared static RestAssured config or shared fixtures overwritten | Isolate client config and data; control parallelism |
| Consumer tests stay green after producer change | Consumer is using an old stub artifact | Pin stub versions and verify matching revisions in CI |

A notable pitfall is **JUnit 4 vs. JUnit 5 mismatch**. Many older examples use `org.junit.Before`, whereas JUnit 5 code uses `org.junit.jupiter.api.BeforeEach`. When the lifecycle method does not execute, MockMvc or seed data is never initialized. Do not fix a failing test by removing assertions; identify why setup did not run.

## 13. Producer tests, consumer tests, and integration tests have distinct responsibilities

| Test type | What does it call? | What does it protect? | Limitations |
|---|---|---|---|
| Generated producer contract test with standalone MockMvc | Real controller + fake/mock dependencies | Controller HTTP mapping and responses within setup scope | Does not verify real DB/broker |
| Generated producer contract test with WebApplicationContext | Producer's Spring MVC context | Wiring/config and HTTP behavior inside the test context | May still use fakes/mocks, not a real socket |
| Generated producer contract test `EXPLICIT` | Producer app over HTTP socket | Behavior through the test-configured server/HTTP stack | Does not replicate every production condition |
| Consumer test with **Stub Runner** | HTTP/message stubs from contracts | Consumer sends requests and handles committed responses | Does not call the real producer |
| Integration/end-to-end test | Producer + DB/broker and related services | Layer integration and operational behavior | Slower, heavier data and infrastructure needs |

If your goal is "when Inventory changes a route, Checkout detects it immediately," producer contract tests and consumer Stub Runner tests are two essential safeguards. If your goal is "inventory DB queries use proper transactions/locking," you need tests at the corresponding repository/service/integration layer.

Do not bloat the base class until every contract test has to boot the entire microservice ecosystem. Each test should establish the **smallest boundary that still proves what the contract promises**.

## 14. Putting base class setup into CI to detect breaking changes

A reference workflow:

~~~mermaid
sequenceDiagram
    participant Dev as Pull request
    participant Gen as Contract generator
    participant Base as Base test + producer
    participant Stub as Stub artifact
    participant Cons as Consumer test
    Dev->>Gen: Update Groovy/YAML contract
    Gen->>Base: Generate test extending base class
    Base->>Base: Initialize controller/context + fixtures
    Base->>Base: Call producer, check status/headers/body
    alt Producer contract test succeeds
        Gen->>Stub: Package stub at same revision
        Stub->>Cons: Stub Runner launches candidate stub
        Cons->>Cons: Call using consumer's real client
    else Producer test fails
        Base-->>Dev: Investigate setup or implementation
    end
~~~

Conditions to verify before accepting a PR:

1. **Contracts discovered:** DSL files are in the plugin's input location.
2. **Generated tests executed:** not a green build due to `0 tests`.
3. **Base class builds the right target:** controller, application context, or HTTP server matching `testMode`.
4. **Stable fixtures:** independent of production DB or test ordering.
5. **Sufficient assertions:** producer tests check the fields and statuses consumers actually rely on.
6. **Same-revision stubs:** artifacts are generated from verified contracts.
7. **Consumer tests the right stub:** Stub Runner loads the release candidate, not a stale cached build.
8. **Compatibility review:** changing fields, statuses, MIME types, schemas, or URLs can still break consumers even if producer tests pass against the new contract.

**Do not assume a build producing stubs proves producer tests passed.** CI gates must tie stub publication to passing producer contract tests.

## 15. Practice exercises: choosing the right initialization approach

### Scenario A — Simple controller

`InventoryController` only depends on `InventoryService`. The team wants to test `GET /api/inventory/{sku}` with a fake service for fast execution.

**Recommendation:** use `MOCKMVC` + `RestAssuredMockMvc.standaloneSetup(new InventoryController(fakeService))`. Set up the `SKU-101` fixture in the mock and ensure the real controller is called.

**Question:** does this test prove the repository persists inventory accurately?

**Answer:** no. It protects HTTP/controller behavior within the mock's scope; the repository requires separate tests.

### Scenario B — Error body from `@ControllerAdvice`

The producer uses a global exception handler to translate `InventoryNotFoundException` into `404` with JSON `{"code":"SKU_NOT_FOUND"}`. A standalone test only initializes the controller, so the test throws an exception instead of returning the error body.

**Recommendation:** register the exception handler/converters in standalone MockMvc or switch to `WebApplicationContext` to use the real MVC configuration. Do not write a separate controller just to make the test pass.

**Question:** if the test context skips security filters, can a `403` test be considered complete security verification?

**Answer:** no. Configure security/filters matching the test boundary or add integration/security tests.

### Scenario C — Context path and proxy-like behavior

The application serves endpoints under `/inventory-service/api/inventory/SKU-101` and the team wants to verify the context path over real HTTP.

**Recommendation:** consider `EXPLICIT` + `SpringBootTest(RANDOM_PORT)`, configure RestAssured to the assigned port, and ensure contracts describe the full path. Only use MockMvc if the scope has been agreed upon and real socket/context-path verification is unnecessary.

### Scenario D — Generated tests stay green even though the producer DB is broken

The base class mocked `InventoryService` to always return `8`. A PR breaks the repository so real data reads fail, yet contract tests stay green.

**Explanation:** the test only goes through the controller and mocked service without invoking the real repository. Add repository/integration tests; you may also add a contract suite running with a real context and test database if risk warrants it.

### Self-check questions

1. Why must `baseClassForTests` point to the exact class in the test source set?
2. How do `standaloneSetup` and `webAppContextSetup` differ in the Spring components they initialize?
3. Why does `@SpringBootTest(RANDOM_PORT)` not automatically switch test mode from `MOCKMVC` to `EXPLICIT`?
4. When should you mock a service versus use a real test database?
5. How can you tell when a JUnit lifecycle hook is not running?
6. Why can't producer contract tests replace consumer tests using Stub Runner?
7. If tests pass with zero generated tests executed, what check is CI missing?
8. Why shouldn't you edit generated tests directly instead of updating the DSL or base class?

## 16. Takeaways

**The base test class bridges contracts and the producer under verification.** It must instantiate the right controller or application, provide intentional dependencies and seed data, and bind generated tests to `MockMvc`, `WebTestClient`, or an HTTP socket matching the chosen test mode. `standaloneSetup` keeps controller tests fast and isolated; `webAppContextSetup` exercises the Spring MVC context; `EXPLICIT` calls the application over a real port.

A good base class doesn't just make tests green—it makes **green tests meaningful**: requests flow through the real producer code, assertions actually execute, test state is repeatable, and mock boundaries are acknowledged. Afterward, the producer publishes stubs and consumers run Stub Runner in CI to catch breaking API or message changes early.

### References

- [Spring Cloud Contract — Getting Started](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html): `baseClassForTests` example and standalone controller setup.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): plugin configuration, test modes, and base classes.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): `contracts`, test tasks, and base class.
- [Spring Cloud Contract — Project Features](https://docs.spring.io/spring-cloud-contract/reference/project-features.html): WebFlux, `EXPLICIT`, context path, and producer/consumer mechanisms.
