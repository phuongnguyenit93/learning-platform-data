# Running Generated Tests with the Right Test Runner

## 1. The problem: generating tests does not guarantee producer verification

In **Spring Cloud Contract (SCC)**, the producer and consumer agree on HTTP or messaging behavior via **Groovy DSL/YAML DSL**. **Contract Verifier** generates tests on the provider (producer) side; from the same contract, the tool can also create stubs for the consumer side to run with **Stub Runner**. Combining both flows in CI helps detect incompatible API changes before release.

In projects using **Maven**, many teams successfully add `spring-cloud-contract-maven-plugin`, see generated Java files under `target/`, and conclude "we have contract testing." However, the tests may still fail to run, run under the wrong framework, hit a fake controller, or mismatch the application type under verification:

- The plugin generates **JUnit 5 tests**, yet Maven Surefire is too old or fails to discover them.
- Generated tests require **RestAssuredMockMvc**, yet the base test only configures WebTestClient.
- The producer is **WebFlux**, yet uses a test mode meant only for MVC.
- Tests are named `*IT`, while the pipeline runs only **Surefire** and never runs **Failsafe**.
- The Maven build passes `-DskipTests` or `-Dmaven.test.skip=true` without CI enforcement.
- Generated tests point to a **fake controller** returning hardcoded sample responses, staying green even when production code is broken.
- The build succeeds, yet **no contracts were discovered** and executed contract test count is 0.

This lesson belongs to the **Maven Integration** chapter and focuses on **running generated tests with the right test tool**: selecting the test framework, test mode, Maven test plugin, base test, lifecycle, verifying execution, packaging stubs, and wiring into CI.

### After this lesson, you can

1. Explain the difference between **contract sources**, **generated tests**, the **test runner**, and the **stub artifact**.
2. Use the Maven Contract Verifier plugin to configure generated producer tests.
3. Choose **JUnit Jupiter/JUnit 5**, Surefire, or Failsafe based on test type and lifecycle.
4. Connect generated tests to **Spring MVC/MockMvc**, **Spring WebFlux/WebTestClient**, or a live HTTP server.
5. Set up a test base so generated tests invoke **real producer code**, not fake responses.
6. Run the right Maven phase and verify the **number of generated tests executed**, not merely seeing `BUILD SUCCESS`.
7. Handle message contracts using triggers and a message verifier/test binder.
8. Feed producer verification results and candidate stubs into consumer CI via Stub Runner.
9. Diagnose zero-test, wrong mode, wrong runner, skipped test, and false-green build scenarios.

## 2. Understanding Contract Verifier assets accurately

A simple flow:

~~~mermaid
flowchart TD
    A["Groovy/YAML contracts"] --> B["Maven Spring Cloud Contract plugin"]
    B --> C["Generated Java producer tests"]
    B --> D["Generated WireMock mappings / stubs"]
    C --> E["Maven compiler and test runner"]
    E --> F["Spring test base + real producer code"]
    F --> G{"Does response/message match contract?"}
    G -- "No" --> X["FAIL producer verification"]
    G -- "Yes" --> H["Package/publish candidate stubs"]
    D --> H
    H --> I["Stub Runner in consumer tests"]
    I --> J["Real consumer HTTP client / message handler"]
    J --> K{"Is consumer still compatible?"}
    K -- "No" --> Y["FAIL compatibility gate"]
    K -- "Yes" --> L["Proceed with release gates"]
~~~

Distinguish each role:

| Component | Role | Cannot substitute for |
|---|---|---|
| **Contract source** | Specifies agreed HTTP/message behavior | Executed tests |
| **SCC Maven plugin** | Reads contracts, generates tests and stub artifacts | JUnit/Surefire running assertions |
| **Generated Java test** | Auto-generated test source code | Proof that tests executed |
| **JUnit/TestNG or matching framework** | Provides test annotations, assertions, lifecycle | Proper Spring context setup |
| **Maven Surefire/Failsafe** | Discovers, launches, and reports tests per Maven lifecycle | Selecting test mode and base class |
| **Test base** | Initializes the environment testing the real producer | Contract DSL |
| **WireMock stub** | Returns sample responses for consumer tests | Producer code and producer verification |
| **Stub Runner** | Resolves and starts stubs for consumers | Correctness of the producer implementation |

**Principle:** always verify two independent questions: (1) **Were the tests generated correctly?** and (2) **Did the runner execute them against the real producer?** Only "yes" to both produces valid verification evidence.

## 3. How does the Maven lifecycle affect generated tests?

Maven has directly relevant phases:

~~~text
generate-test-sources
       ↓
test-compile
       ↓
test
       ↓
package
       ↓
integration-test
       ↓
verify
       ↓
install
       ↓
deploy
~~~

Responsibility table:

| Phase | Expected role in contract testing |
|---|---|
| `generate-test-sources` | Plugin generates Java producer tests and registers the appropriate source directory |
| `test-compile` | Compiler compiles generated tests and the test base |
| `test` | **Surefire** executes tests matching naming/provider conventions |
| `package` | Packages producer artifact; SCC may attach stub packaging per config |
| `integration-test` | **Failsafe** runs integration tests when executions are configured |
| `verify` | Runs verification checks; **Failsafe verify** fails the build on integration test errors when properly configured |
| `install` | Writes artifacts into the local Maven repository |
| `deploy` | Publishes artifacts to the configured remote repository |

The **SCC plugin** goal names and phase bindings depend on version and `<extensions>true</extensions>`. Never assume every Maven build already binds full generation and packaging. Inspect the **effective POM**, build logs, and output directories.

### Why do `mvn test` and `mvn verify` differ?

`./mvnw test` runs up to the `test` phase, suitable for checking generated tests managed by **Surefire**. `./mvnw verify` goes further, covering post-`test` phases and bound plugin executions such as **Failsafe**. However, if `failsafe-maven-plugin` is not configured to run, simply invoking `verify` will not conjure an integration test into existence.

**Do not confuse Maven's `verify` phase with the product name "Contract Verifier."** They are two different concepts: one is a Maven lifecycle phase, the other is the contract generation and verification toolkit.

## 4. End-to-end example: Inventory Service as producer

Suppose Checkout Service is the consumer and Inventory Service is the producer. Checkout calls:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

The producer promises:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

In this lesson, we use a Spring Boot + Spring MVC app to illustrate `MockMvc` mode, and later compare it with WebFlux and live HTTP server tests.

Contract sources inside the producer:

~~~text
inventory-service/
├── pom.xml
├── mvnw
├── mvnw.cmd
└── src/
    ├── main/java/com/example/inventory/
    │   ├── InventoryApplication.java
    │   ├── InventoryController.java
    │   └── InventoryService.java
    └── test/
        ├── java/com/example/inventory/
        │   └── ContractTestBase.java
        └── resources/contracts/inventory/
            └── get-stock.groovy
~~~

If the project places contracts in a different directory, the Maven plugin must receive the right path and generated test source directory.

## 5. A concrete Groovy DSL contract

File `src/test/resources/contracts/inventory/get-stock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout can look up stock for SKU-123'

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

In an equivalent YAML DSL version:

~~~yaml
description: Checkout can look up stock for SKU-123
name: inventory_sku123

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

The two snippets are **mutually exclusive alternatives**; do not keep both in the same project for a single scenario, as that can create duplicate tests and mappings.

The contract states what data the producer must return, but **does not decide which test runner executes the generated Java file**. Maven and the base test must be configured in the following sections.

## 6. Configuring the Maven Contract Verifier plugin

An illustrative POM excerpt:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>CONTRACT_PLUGIN_VERSION</version>
            <extensions>true</extensions>
            <configuration>
                <testFramework>JUNIT5</testFramework>
                <testMode>MOCKMVC</testMode>
                <baseClassForTests>
                    com.example.inventory.ContractTestBase
                </baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

### Meaning

- `spring-cloud-contract-maven-plugin` handles contract processing, generated tests, and stubs.
- `CONTRACT_PLUGIN_VERSION` is a placeholder; **replace it with a real version** compatible with your project's Spring Boot/Cloud.
- `extensions=true` enables the plugin's lifecycle integration mechanism supported by the SCC line.
- `testFramework=JUNIT5` illustrates generating tests using JUnit Jupiter.
- `testMode=MOCKMVC` targets generated tests for a Spring MVC application.
- `baseClassForTests` links generated tests to the test base, which sets up the Spring context and REST Assured MockMvc adapter.

**Version note:** enum values/syntax for `testFramework` and `testMode` can vary across SCC lines. Check the reference docs for your exact version and inspect generated Java imports instead of assuming names that merely look reasonable.

When a project has multiple contract groups requiring different base classes, you may need to map groups by package/path rather than using one `baseClassForTests`. Avoid creating one base class that stubs out all endpoints to dodge setup errors.

## 7. Dependency management: aligning Spring Boot, Cloud, and plugin

The producer side typically declares `spring-cloud-starter-contract-verifier` in test scope:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-verifier</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

A Spring Boot project can import the Spring Cloud BOM (for example):

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>CLOUD_TRAIN_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

In a real POM, `dependencyManagement` may also contain corporate BOMs or other dependencies. Version placeholders **will not work** until replaced.

### Three versions to check separately

1. **Spring Boot version:** determines Spring Framework, test infrastructure, and core dependencies.
2. **Spring Cloud Release Train:** aligns Spring Cloud dependencies to versions compatible with Boot.
3. **Spring Cloud Contract Maven plugin version:** the build plugin version, not necessarily managed by the BOM like test dependencies.

Also verify **Maven Surefire/Failsafe plugin versions**: a JUnit 5 line not properly supported by the runner can prevent tests from executing. Choose a test plugin version verified by the project rather than relying on an outdated Maven parent default.

## 8. JUnit 5 or JUnit 4: framework must match generated code

A generated JUnit Jupiter test may contain imports like:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
~~~

Whereas JUnit 4 uses:

~~~java
import org.junit.Test;
import org.junit.Before;
~~~

The two sets of annotations are **not interchangeable**. If the plugin generates JUnit 5 while the test base puts lifecycle setup on JUnit 4's `@Before`, adapter initialization may fail to run under the runner. Conversely, mixing JUnit Vintage and Jupiter haphazardly makes test discovery hard to diagnose.

In this lesson, we use **JUnit 5/Jupiter** consistently:

- The plugin is configured to generate JUnit 5 per version capabilities;
- `spring-boot-starter-test` and `spring-cloud-starter-contract-verifier` supply matching test dependencies;
- The test base uses `@BeforeEach`;
- Maven Surefire supports JUnit Platform;
- Generated sources actually contain `org.junit.jupiter.api.Test`;
- The Surefire report shows **tests run > 0**.

**Do not mix frameworks just to keep base test code from an old example.** When upgrading Spring Boot/Contract versions, re-check generated code and test reports.

## 9. Maven Surefire: who actually runs generated tests?

`maven-surefire-plugin` normally binds to the `test` phase. It discovers and runs tests based on provider, test framework, and class name patterns.

POM example:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>SUREFIRE_VERSION</version>
            <configuration>
                <failIfNoTests>true</failIfNoTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`SUREFIRE_VERSION` is a placeholder; pick a version supporting JUnit 5 and compatible with your Maven and JDK. `failIfNoTests` catches cases where the test task finds zero tests, but **does not replace** verifying that **generated contract tests exist**. If the project has many unit tests, Surefire can still execute them and pass even if contract generation was skipped.

### Naming conventions

By default, Surefire typically recognizes names like:

~~~text
TestSomething
SomethingTest
SomethingTests
SomethingTestCase
~~~

Meanwhile, tests named `SomethingIT` follow **Failsafe** conventions. If SCC generates classes whose names do not match runner rules, adjust **test naming configuration or plugin includes** per version, and verify it does not cause a double run.

For example, when you need to include custom names, you can configure:

~~~xml
<configuration>
    <includes>
        <include>**/*Test.java</include>
        <include>**/*Tests.java</include>
    </includes>
</configuration>
~~~

This illustrates pattern configuration; do not copy it to **override working includes** if your project uses other test names. Check generated source names first and add only minimal patterns.

## 10. Maven Failsafe: for lifecycle-bound integration tests

`maven-failsafe-plugin` is typically used for tests needing a live web server, containers, databases, or integration components. It does not run automatically just because you invoke `mvn verify`; executions must be configured.

Example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>FAILSAFE_VERSION</version>
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

Under standard naming conventions, Failsafe executes `*IT`/`IT*` or configured patterns. If SCC's generated contract tests are named `*Test`, they **do not automatically move to Failsafe** just because this plugin is present.

| Configuration | Command to observe | What to confirm |
|---|---|---|
| Generated `*Test`, Surefire | `./mvnw test` | Surefire runs contract tests |
| Generated `*IT`, Failsafe configured | `./mvnw verify` | Failsafe `integration-test` and `verify` run |
| Generated `*IT`, `./mvnw test` only | Insufficient | Failsafe phase not reached |
| Generated `*Test`, expecting Failsafe | Insufficient | Naming/includes must match runner |
| Surefire + Failsafe matching same class | Risky | May run tests twice with non-isolated setup |

**Do not manually rename generated Java files under `target/` to "make tests run."** Adjust naming config, test runner plugins, or the SCC generator as supported by your version. Output under `target/` gets wiped and regenerated on `clean`.

## 11. Proper Base Test configuration for Spring MVC + MockMvc

Suppose the application uses Spring MVC and must verify the real `InventoryController`. JUnit 5 base class:

~~~java
package com.example.inventory;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class ContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

What this accomplishes:

1. `@SpringBootTest` initializes the **producer's** Spring ApplicationContext.
2. `@AutoConfigureMockMvc` provides MockMvc wired to the Spring MVC context.
3. `@Autowired MockMvc` retrieves the real adapter from the context.
4. `RestAssuredMockMvc.mockMvc(mockMvc)` binds the adapter for generated tests using RestAssuredMockMvc.
5. Generated tests send requests to the **producer's controller**, not an HTTP stub.
6. Actual responses are generated by the controller/service and asserted against the contract.

**MockMvc does not open a TCP port**, yet it executes through Spring MVC handler mapping, message converters, and the controller inside the test context. If a contract must validate network/container details (TLS, reverse proxy, server-specific behavior), supplement it with another HTTP integration test.

## 12. Which base tests produce false-green results?

Anti-pattern:

~~~java
// WRONG if the goal is verifying the producer implementation:
@BeforeEach
void setup() {
    RestAssuredMockMvc.standaloneSetup(
        new FakeInventoryController()
    );
}
~~~

Where `FakeInventoryController` always returns:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

Generated contract tests pass because the fake returns the sample body—even if production `InventoryController` lost its mapping or `InventoryService` returns `available:false`.

A subtler anti-pattern: booting the real Spring context while replacing the **entire business service** with a mock returning a canned `StockResponse` matching the contract. That test still checks controller routing and serialization, **but does not verify service business logic**.

**Verification question:** if you intentionally break producer code that the contract should protect, does the generated test turn **red**? If not, the test may be mocking/faking at too high a layer, or not actually running.

You can mock external dependencies (payment gateway, email sender) or use a test database/fake repository supplying raw records, as long as the **critical business execution path** stays production code.

## 13. A producer implementation for mutation testing

An illustrative application:

~~~java
package com.example.inventory;

public record StockResponse(
        String sku, boolean available, int quantity) {
}
~~~

Real service:

~~~java
package com.example.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    public StockResponse lookup(String sku) {
        int quantity = "SKU-123".equals(sku) ? 12 : 0;
        return new StockResponse(sku, quantity > 0, quantity);
    }
}
~~~

Real controller:

~~~java
package com.example.inventory;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public StockResponse getStock(@PathVariable String sku) {
        return service.lookup(sku);
    }
}
~~~

On a test branch, change:

~~~java
return new StockResponse(sku, quantity > 0, quantity);
~~~

to:

~~~java
// Deliberately wrong: use only for the mutation check.
return new StockResponse(sku, quantity == 0, quantity);
~~~

For SKU-123 with quantity 12, the contract requiring `available:true` must **fail** if the generated test hits the real service.

After observing the failure, **restore the correct logic** and confirm the test goes green again. This experiment proves the test suite can catch regressions within the promised scope.

## 14. Choosing MockMvc, WebTestClient, or live HTTP?

SCC can generate different styles of producer tests depending on `testMode` and plugin version. Choose based on the **actual stack and verification scope**.

| Stack/execution style | Execution path | Required base test | Watch out for |
|---|---|---|---|
| Spring MVC | **MockMvc** | Spring MVC context + RestAssuredMockMvc setup | Never replace controller with a fake |
| Spring WebFlux | **WebTestClient** if supported by SCC version | Reactive context and WebTestClient matching generated test | Do not blindly use MockMvc on a reactive stack |
| Live HTTP server | Appropriate **Explicit/HTTP mode** | Start server and supply URL/port to test | Test must call real producer, not WireMock |
| REST producer outside Spring MVC/WebFlux | HTTP client mode supported by plugin | Matching server/test harness | Avoid irrelevant Spring MVC base classes |
| Message producer | Messaging verifier infrastructure | Production trigger and observer/message verifier | Do not manually publish sample payloads from base |

`testMode` names and generated APIs **depend on version**. Never guess enums or copy one `<testMode>...` across every stack. After generating tests, read the generated Java to see whether the class needs `RestAssuredMockMvc`, `WebTestClient`, `RestAssured`, or messaging support.

**Running the right tool** does not merely mean picking a framework that compiles; it must exercise the **real production code path** protected by the contract.

## 15. WebFlux: when to choose WebTestClient?

With Spring WebFlux, controllers can return `Mono<StockResponse>` or `Flux<StockResponse>`. A base test must boot the WebFlux app context and provide WebTestClient in the way generated tests expect.

Illustrative setup excerpt:

~~~java
package com.example.inventory;

import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
public abstract class ReactiveContractTestBase {
    // Add WebTestClient injection/binding matching generated tests
    // and the corresponding SCC testMode=WEBTESTCLIENT version.
}
~~~

A hand-written WebTestClient test can verify the endpoint:

~~~java
@Autowired
WebTestClient client;

@Test
void readsStock() {
    client.get()
        .uri("/api/inventory/SKU-123")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.available").isEqualTo(true);
}
~~~

This snippet only illustrates the **WebFlux HTTP testing tool**. **It is not an SCC-generated test**; inspect the actual plugin-generated test directly, then provide whatever fields/methods the generated test requires in the base class.

Because reactive applications perform asynchronous operations, ensure requests/responses are subscribed and test timeouts are bounded. For long-lived `Mono/Flux` operators, supplement with `StepVerifier`/virtual time where appropriate; an HTTP contract test alone does not verify retry, backpressure, or cancellation semantics.

## 16. Live HTTP: when MockMvc scope is not enough

Some contracts depend on live HTTP server behavior (response compression, networking, servlet filter/container config, or middleware). In those cases, use an HTTP/client mode supported by your SCC version alongside a base test that starts the web server during tests.

**Conceptual** example for a RestAssured HTTP test:

~~~java
package com.example.inventory;

import io.restassured.RestAssured;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.server.LocalServerPort;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
public abstract class HttpContractTestBase {

    @LocalServerPort
    int port;

    @BeforeEach
    void setup() {
        RestAssured.port = port;
    }
}
~~~

**Version note:** the package for `@LocalServerPort` changed across Spring Boot lines. The example above reflects an older Boot package; in newer Boot releases, the annotation lives in the test package `org.springframework.boot.test.web.server`. Use the import matching your project's version and verify that generated code actually invokes the RestAssured HTTP client with the right host and port.

For tests running in parallel, **`RestAssured.port` is a global setting** that can cause cross-test interference. Control parallelism or use per-test client configuration if supported by your API/plugin version.

**Never use Stub Runner inside producer HTTP verification** to return sample responses. Doing so only proves the test calls a contract stub, not that the real producer implementation satisfies the contract.

## 17. Message contracts: a different runner from HTTP

Spring Cloud Contract also supports message contracts. For example, Inventory Service emits an event:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stockChanged'

    input {
        triggeredBy('triggerStockChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-123',
            available: true
        )
    }
}
~~~

Generated messaging tests need:

- The **right test framework** (JUnit 5/Jupiter in this example).
- A `triggerStockChanged()` method callable by the generated test.
- A **message verifier / test binder** or messaging test infrastructure to observe output.
- Finite timeouts if output is emitted asynchronously.
- Fixtures and cleanup to prevent receiving leftover messages from other tests.

The base test should call the **production** application service:

~~~java
@Autowired
InventoryApplicationService inventoryApplicationService;

public void triggerStockChanged() {
    inventoryApplicationService.changeStock("SKU-123", 12);
}
~~~

`InventoryApplicationService` here is an illustrative application bean; in a real project, it must **actually create and emit the event**. Never do this:

~~~java
// Defeats the purpose of producer verification:
public void triggerStockChanged() {
    testSink.send(
        "inventory.events",
        "{\"eventType\":\"StockChanged\",\"sku\":\"SKU-123\",\"available\":true}"
    );
}
~~~

The wrong approach makes generated tests pass even when production producer code fails to emit the right message.

**For message tests, choosing Surefire/Failsafe is still only the test runner; HTTP MockMvc does not provide a message verifier.** You must configure the proper messaging adapter/binder for your Spring Cloud Stream/Kafka/Rabbit stack and SCC version.

## 18. When are helper assertions or base-class setup needed?

A contract may include complex matchers, such as requiring a body field to satisfy a custom rule:

~~~groovy
response {
    status OK()
    body(
        sku: 'SKU-123',
        quantity: 12
    )
    bodyMatchers {
        jsonPath('$.quantity',
            byCommand('assertNonNegativeQuantity($it)'))
    }
}
~~~

The generated test may need to call a helper method from the base class:

~~~java
public void assertNonNegativeQuantity(Object value) {
    if (!(value instanceof Number)) {
        throw new AssertionError("quantity must be a number");
    }

    double quantity = ((Number) value).doubleValue();

    if (quantity < 0) {
        throw new AssertionError("quantity must not be negative");
    }
}
~~~

This illustrates the rule that "a custom command must have a matching method available to the generated test." For currency or strict precision, avoid `double` and validate exact types such as `BigDecimal` or `Long` per contract.

If generated Java fails to compile because `assertNonNegativeQuantity` cannot be found, do not delete the matcher just to make the build green. Check `baseClassForTests`, visibility, and method signature against the **actual generated source**.

## 19. Maven plugin test generation: where to find the files?

In many SCC Maven plugin versions, generated Java tests are placed under a directory inside `target/generated-test-sources`, such as:

~~~text
target/generated-test-sources/contracts/...
~~~

The exact path is determined by plugin/configuration. `target/` is **build output**, not the place to edit contracts or generated Java manually.

When inspecting, check three layers:

~~~text
src/test/resources/contracts/
  -> Committed input contracts

target/generated-test-sources/...
  -> Test sources generated by Contract Verifier

target/surefire-reports/ or target/failsafe-reports/
  -> Proof that tests actually executed
~~~

In a project, class names are derived from contract names, packages, and SCC conventions. Do not rely on a fixed name like `GetStockTest` if the generator produces a different name; read names **from actual output**.

**A test source that exists on disk yet is never discovered by the Maven test runner is still a gap.**

## 20. Maven commands to use in development

Use the project's **Maven Wrapper** to keep Maven versions consistent:

~~~bash
# Follows plugin/phase lifecycle, generating and running tests when configured.
./mvnw clean test

# Runs through verify, including bound plugin executions.
./mvnw clean verify

# Inspects effective POM to verify inherited/overridden configuration.
./mvnw help:effective-pom

# Views detailed debug logs when troubleshooting.
./mvnw -X test
~~~

On Windows:

~~~powershell
.\mvnw.cmd clean test
.\mvnw.cmd clean verify
.\mvnw.cmd help:effective-pom
~~~

These commands are **practical guidance**, not executed during authoring. Run them inside the producer module or from the parent with the right module selector in multi-module builds.

### Which commands are insufficient to prove compatibility?

- `./mvnw compile`: stops before `test`; does not prove generated tests ran.
- `./mvnw test-compile`: compiles tests only, without executing them.
- `./mvnw package -DskipTests`: can build artifacts while skipping verification.
- `./mvnw verify -Dmaven.test.skip=true`: can skip both test compilation and execution.
- `./mvnw -Dtest=InventoryUnitTest test`: may run only a single unit test and **skip generated contract tests**.
- `./mvnw integration-test`: may run Failsafe tests without executing the **failsafe verify goal** to report failures properly.

For stub-publishing pipelines, use a Maven lifecycle target that executes **true producer verification**, and only then hand the candidate artifact to consumer tests.

## 21. Reading Surefire/Failsafe reports instead of guessing from exit code

After running Maven tests, inspect the runner reports:

~~~text
target/surefire-reports/
  TEST-com.example.inventory.GetStockTest.xml
  com.example.inventory.GetStockTest.txt

target/failsafe-reports/
  TEST-com.example.inventory.SomeIntegrationIT.xml
  ...
~~~

These are **illustrative filenames**, not confirmed project output. Look for:

- Number of tests run, failures, errors, and skipped;
- Generated test class names;
- Test mode/base class used;
- Assertion errors showing status/header/body/message mismatches;
- Whether any tests were skipped via annotations, profiles, or build flags;
- Whether the report comes from a **fresh build** after `clean`.

### Guarding contract test counts

Even when Surefire runs 100 unit tests, the **generated contract test count can still be 0**. Therefore, CI should assert **contract discovery > 0** and **executed generated contract tests > 0** for modules expected to own contracts. You can use a plugin or report-checking script fitting your CI; this lesson specifies the verification requirement without adding external scripts or files.

## 22. Naming tests so Surefire or Failsafe does not miss them

A verification matrix:

| Generated class | Expected runner | What to verify |
|---|---|---|
| `GetStockTest` | Surefire | `*Test` pattern matches |
| `GetStockTests` | Surefire | `*Tests` pattern matches |
| `InventoryContractIT` | Failsafe if configured | `*IT` pattern matches and `verify` goal runs |
| `InventoryContractSpec` | Not default for all runners | Explicit `includes` configured |
| `AbstractContractTestBase` | Should not run standalone | Abstract class is not treated as a real test |
| Helper class without `@Test` | Should not count as executed tests | Count executed test methods, not class files |

If the project uses an SCC naming extension or custom suffix for generated tests, synchronize runner includes/excludes accordingly.

**Do not configure both Surefire and Failsafe to match the same generated class** unintentionally: tests may run twice, causing side effects or inflated CI times. If splitting unit tests and producer integration tests, define a consistent strategy across naming, source sets, and lifecycle.

## 23. Test resources, deterministic data, and Spring context

Generated tests typically call production endpoints, so data must be deterministic. For example, the GET SKU-123 contract expects quantity 12.

If the producer reads a database, you can use:

- An isolated test database or Testcontainers when persistence behavior is in scope.
- `@Sql`/fixture loaders to seed data before tests.
- A test profile isolating repositories/endpoints from production.
- Mocked third-party gateways while keeping real business controllers/services.
- A fixed clock/seed if responses contain app-generated timestamps or IDs.

Example with a SQL test fixture:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@org.springframework.test.context.jdbc.Sql(
    scripts = "/sql/inventory-contract-fixture.sql"
)
public abstract class ContractTestBase {
    // Configure RestAssuredMockMvc with Spring MockMvc as in section 11.
}
~~~

This only illustrates the annotation; the SQL file must exist in a real project if used. Authoring this lesson does not create extra files.

**Separate test data from business logic:** a fake repository may return raw entity records, yet mocking `return new StockResponse("SKU-123", true, 12)` straight out of the service prevents generated tests from catching broken service logic.

## 24. Do not use `Thread.sleep` to wait for reactive/message producers

With reactive HTTP or messaging, tests can depend on asynchronous signals. Waiting with `Thread.sleep(5000)` causes CI flakiness because scheduling and host load vary.

Establish **clear deadlines** per layer:

| Layer | Example | Role |
|---|---|---|
| Service timeout | `Mono.timeout(Duration.ofSeconds(1))` | Application/business rule |
| HTTP test client timeout | WebTestClient/RestAssured timeout | Bounds response wait |
| StepVerifier deadline | `verify(Duration.ofSeconds(3))` | Prevents Reactor test hangs |
| Message receive timeout | Messaging test infrastructure | Bounded wait for message output |
| Runner timeout | Surefire/Failsafe forked JVM timeout, test annotation | Prevents stuck suites |
| CI job timeout | Job-level deadline | Final safety net |

Values are illustrative and must reflect real SLOs and environments. A **test client timeout** does not make the producer return HTTP 504; a test timeout means the test never received a response, whereas HTTP 504 must be mapped by the producer from an application error into the public contract response.

For `Mono/Flux` logic, use `StepVerifier`/virtual time to test time operators when possible; with real networks or brokers, bounded-timeout integration tests are still necessary.

## 25. Testing error responses, not only happy paths

A producer typically has multiple contracts:

~~~text
GET /api/inventory/SKU-123 -> 200, available=true
GET /api/inventory/SKU-456 -> 200, available=false
GET /api/inventory/SKU-404 -> 404, SKU_NOT_FOUND
GET /api/inventory/SKU-503 -> 503, INVENTORY_UNAVAILABLE
~~~

A `404` YAML contract:

~~~yaml
description: SKU does not exist

request:
  method: GET
  url: /api/inventory/SKU-404

response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: SKU_NOT_FOUND
    message: SKU does not exist
~~~

Generated producer tests must send requests to real producer code and assert **status + error body**, not merely accept "any 404 response." In consumer tests with Stub Runner, distinguish a **business 404** intentionally served by a mapping from a **WireMock unmatched 404** caused by a client sending the wrong URL or header.

Covering only a single happy-path contract means a green build never proves error mapping, validation, retries, or compatibility when the producer introduces new fields/enums.

## 26. Generating stubs after producer verification

SCC can generate WireMock mappings and package a stubs JAR containing contract resources. Example coordinates:

~~~text
groupId:     com.example
artifactId:  inventory-service
version:     1.3.0-rc1
classifier:  stubs
type:        jar
~~~

Illustrative JAR filename:

~~~text
inventory-service-1.3.0-rc1-stubs.jar
~~~

The Maven lifecycle can build and attach the stubs artifact when the plugin is configured properly, yet you must **inspect actual output** rather than assuming from goal names.

To inspect the JAR structure after a build (adjust the filename to actual output):

~~~bash
jar tf target/inventory-service-1.3.0-rc1-stubs.jar
~~~

Confirm the required mappings and response body files are present. An empty JAR or one carrying stale artifacts fails consumer verification.

**Important:** Stub Runner on the consumer side is not the tool that runs generated producer tests. The two tasks are linked by a **candidate artifact from the same contract revision/commit**, requiring **producer verification** before publishing the stub.

## 27. Consumer tests with Stub Runner: a distinct role

In Checkout Service:

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
    void checkoutHandlesInventoryResponse() {
        // Call Checkout's real Inventory HTTP client,
        // deserialize JSON, and verify business handling.
    }
}
~~~

`LOCAL` assumes stubs already live in the test environment's local repository. For cross-project CI, use `REMOTE` with appropriate repository configuration.

Consumer tests should invoke Checkout's **real HTTP client**. Mocking the client itself to return sample DTOs misses bugs in HTTP method, URL, headers, serialization, deserialization, or error mapping.

### Incompatible API changes

If the producer changes the body from:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

to:

~~~json
{"sku":"SKU-123","inStock":true,"quantity":12}
~~~

new producer tests may pass if the contract was updated too. Yet old Checkout still reads `available`. Therefore, old Checkout must be tested against the **new producer's candidate stubs artifact**, not a previously cached stable version.

## 28. CI: a pipeline that truly verifies contracts

~~~mermaid
flowchart TD
    A["Producer PR: code + contract + POM"] --> B["Maven generates tests"]
    B --> C["Compile generated Java"]
    C --> D["Surefire/Failsafe runs real tests"]
    D --> E{"Executed contract tests > 0 and all pass?"}
    E -- "No" --> X["BLOCK"]
    E -- "Yes" --> F["Build/publish candidate stubs JAR"]
    F --> G["Consumer tests via Stub Runner"]
    G --> H{"Consumer client compatible?"}
    H -- "No" --> X
    H -- "Yes" --> I["Proceed with release gates"]
~~~

**A minimal CI gate must confirm:**

1. The plugin reads the right contract directory; not a zero-contract run.
2. Generated test files are produced.
3. Test sources compile cleanly.
4. Surefire/Failsafe runs the right framework with **executed contract tests > 0**.
5. Assertions genuinely run against the **real producer implementation**.
6. `-DskipTests` and `-Dmaven.test.skip=true` are never enabled in the verification stage.
7. The stubs JAR contains valid mappings with exact group/artifact/version/classifier.
8. Candidate artifacts trace back to an explicit Git commit.
9. Consumer tests fetch the **exact candidate version**, never `latest` or an ambiguous cache.
10. Consumers run real clients/handlers against Stub Runner, including critical error cases.
11. The pipeline archives test reports, Maven/JDK/Boot/Cloud/Contract versions, and logs.
12. When a contract introduces a breaking change, supported active consumers are verified before release.

This is a **CI design blueprint**; this lesson does not create extra Jenkinsfile/GitHub Actions files since the assigned scope covers only Markdown documentation and YAML status.

## 29. Multi-module Maven: which tests run in which module?

A repository might look like:

~~~text
commerce-platform/
  pom.xml
  inventory-service/
    pom.xml
    src/test/resources/contracts/...
  pricing-service/
    pom.xml
    src/test/resources/contracts/...
  checkout-service/
    pom.xml
    src/test/java/...consumer tests...
~~~

The SCC Maven plugin should only be **activated in producer modules needing generated contract tests**. A parent POM can manage the plugin version, without implying the plugin should automatically run in every module.

Example running only Inventory (depending on reactor/module names):

~~~bash
./mvnw -pl inventory-service -am clean verify
~~~

`-pl` selects the module, and `-am` builds reactor dependencies when needed. Inspect the test reports and artifacts of **`inventory-service`** specifically. Running `verify` from the parent where only Checkout unit tests pass does not prove Inventory contract tests ran.

If two producers have distinct base classes and contracts, each module requires its own source directory, test mode, and matching dependencies.

## 30. Skipped test scenarios: Maven has many ways to bypass

A warning table:

| Setting/command | Common effect | Risk |
|---|---|---|
| `-DskipTests` | Skips test execution in Surefire/Failsafe | Green build without verification |
| `-Dmaven.test.skip=true` | May skip both test compilation and execution | Generated Java may never be checked |
| `-Dtest=SomeUnitTest` | Selects only a subset of tests | Generated contracts never run |
| `-DskipITs` | Skips Failsafe integration tests | `*IT` tests are bypassed |
| `<skipTests>true</skipTests>` in plugin | Can skip all test execution | CI misses mismatches |
| Maven profile disables SCC execution | Skips expected test/stub generation | Zero-contract/zero-test |
| Surefire includes miss generated class | Tests never discovered | False green without a guard |
| `@Disabled` test or JUnit condition | Test skipped | Report shows `skipped > 0` |

Not every property has identical semantics across all versions/plugins; **check the effective POM and logs**. If `skipTests` is used in a stage strictly packaging an artifact already verified in a prior stage, require strict provenance and guarantee **zero code/contract changes between stages**.

**For the primary verification stage, fail closed is recommended:** if zero contracts or zero executed generated tests are found, the job must fail rather than pass.

## 31. Symptom-based troubleshooting

| Symptom | Possible cause | Next check |
|---|---|---|
| No generated Java | Plugin didn't run, wrong contract path, YAML/Groovy undetected | POM/plugin logs, contract directory |
| Generated files exist but fail to compile | Wrong imports, JUnit version, base class, or helpers | Compiler errors, generated source |
| Generated tests compile but do not run | Surefire/Failsafe includes, naming, or old runner | Reports, runner logs, test count |
| JUnit 5 test runs without calling `@BeforeEach` | Framework/lifecycle mismatch or setup in wrong class | Generated imports and base test annotations |
| MockMvc lacks context | Missing `@SpringBootTest`/`@AutoConfigureMockMvc` | Test base Spring setup |
| WebFlux test uses MVC adapter | Wrong `testMode` | Plugin config and generated code |
| HTTP mode hits wrong port | Server not started, wrong port/base URL | Random port/setup, actual request |
| Message test receives no event | Wrong trigger/binder/verifier | Production trigger, destination, timeout |
| Stub tests pass while producer code is broken | Ran Stub Runner only, skipped generated producer tests | Producer test report and mutation check |
| Test stays green when breaking service | Fake controller or mocked service too high up | Test base, Spring bean overrides |
| Green build with zero contracts | Wrong path or plugin skipped | Contract discovery guard |
| Surefire reports no tests | Naming/provider mismatch | Generated class names, plugin version |
| Failsafe tests only run on `verify` | `integration-test`+`verify` not configured/enabled | Failsafe executions |
| Fails in CI but passes locally | Different JDK/Maven/profile/clock/fixtures | Wrapper, effective POM, reports |
| Stubs JAR lacks mappings | Wrong generation/packaging, empty inputs | Inspect JAR entries |
| Consumer sees old API schema | Wrong stub version/cache | Exact candidate coordinate/commit |

### A helpful debugging order

~~~text
1. Check source contracts (Groovy/YAML)
2. Check SCC Maven plugin version + configuration
3. Check test/stub generation goal logs
4. Open generated Java: framework + test mode + base class
5. Check test compilation
6. Check Surefire/Failsafe report and executed test count
7. Check real producer response/message
8. Open stubs JAR, check mappings/fixtures
9. Check consumer Stub Runner exact artifact
10. Compare old/new behavior and breaking changes
~~~

Do not tweak step 8 when the error is at step 4 (JUnit imports), and never alter the contract to match broken code when a test is catching a real regression.

## 32. Lab A — JUnit 5 + Surefire + MockMvc

**Objective:** generate and execute a real producer contract test with Maven.

1. Create Spring MVC Inventory Service with the controller and service from section 13.
2. Pick compatible JDK/Maven/Boot/Cloud/Contract versions.
3. Add the SCC Maven plugin and `spring-cloud-starter-contract-verifier`.
4. Configure `<testFramework>JUNIT5</testFramework>`, `<testMode>MOCKMVC</testMode>`, and `baseClassForTests` per version.
5. Create a `@SpringBootTest + @AutoConfigureMockMvc` base test with `RestAssuredMockMvc.mockMvc(...)`.
6. Write the GET contract from section 5.
7. Run `./mvnw clean test` in the project environment.
8. Inspect the generated class and `target/surefire-reports`; record how many tests actually ran.
9. Deliberately flip `quantity > 0` to `quantity == 0` and confirm the test goes **red**.
10. Restore the code and rerun tests.

**Submission evidence:** POM, contract, test base, generated Java/test report, mutation fail/pass logs.

## 33. Lab B — Choosing the right runner for integration tests

**Objective:** distinguish tests running in `test` from tests running in `integration-test/verify`.

1. Identify current generated test names (e.g., `*Test`).
2. Confirm they are discovered and executed by Surefire.
3. If the project has integration test classes named `*IT`, configure Failsafe executions.
4. Run `./mvnw test`, inspect Surefire reports.
5. Run `./mvnw verify`, inspect Failsafe reports.
6. Confirm generated contract tests are **neither skipped nor executed twice**.
7. Temporarily pass `-DskipITs` on a test branch to understand which gate gets disabled.
8. Restore flags and finalize CI lifecycle.

**Submission evidence:** matrix of test name → runner → Maven phase → executed count.

## 34. Lab C — Comparing MockMvc, WebTestClient, and live HTTP

**Objective:** pick the test mode fitting stack and scope instead of copying configs mechanically.

1. For Spring MVC, use MockMvc + real context; verify generated tests ran.
2. Inspect a separate WebFlux/Mono controller example and test it with WebTestClient.
3. Check whether your SCC plugin version offers `WEBTESTCLIENT` mode or an equivalent config.
4. Check which base test fields/methods the generated code requires.
5. When a live HTTP server is needed, try HTTP mode with a random port and REST Assured if supported by your version.
6. Never use WireMock in place of the producer in any producer verification.
7. Introduce an intentional controller/service bug for each mode; tests must catch it.
8. Document what each test **does not cover** (network, security, broker, downstream).

**Submission evidence:** table mapping mode ↔ runner ↔ base setup ↔ bugs caught.

## 35. Lab D — Producer verification to consumer Stub Runner

**Objective:** ensure the consumer tests the exact artifact of the changing producer.

1. Run generated producer tests until green.
2. Generate and package the stubs JAR; inspect mappings/contents.
3. Install/publish the stub candidate with an unambiguous version.
4. Configure Checkout to load the exact candidate version via Stub Runner.
5. Call Checkout's real Inventory HTTP client and assert `available`/`quantity`.
6. Create a candidate producer version renaming `available` to `inStock`.
7. Run old Checkout against the **new stub** to detect the breaking change.
8. Propose migration/versioning if consumers do not yet support it.
9. Enforce pipeline gates per section 28.

**Submission evidence:** producer reports, stubs artifact metadata, consumer test report, contract changes, and compatibility plan.

## 36. Pre-merge checklist for POM/contracts

- [ ] `spring-cloud-contract-maven-plugin` is applied to the exact producer module.
- [ ] Spring Boot, Cloud Release Train, Contract plugin, Maven/JDK, and Surefire/Failsafe versions are compatible.
- [ ] Contract sources reside in the right directory with valid Groovy/YAML schemas.
- [ ] `testFramework` matches JUnit/Jupiter or the chosen runner.
- [ ] `testMode` matches MVC/WebFlux/HTTP/message testing infrastructure.
- [ ] `baseClassForTests` points to the right class, package, and lifecycle annotations.
- [ ] Generated tests invoke **real producer code**, not fake controllers/services returning canned bodies.
- [ ] Generated Java is produced and compiled inside the Maven lifecycle.
- [ ] Surefire/Failsafe includes discover generated class names properly.
- [ ] Verification stage enables no accidental skip flags or test filters.
- [ ] **Executed contract tests > 0** and failures/errors/skipped are evaluated.
- [ ] Fixture data is stable and never uses production databases/credentials.
- [ ] Async/message timeouts use finite deadlines; fixed sleeps are never used as primary synchronization.
- [ ] Mutation check breaking critical behavior was run to prove tests turn red.
- [ ] Critical HTTP success and error contracts are covered.
- [ ] Message contract triggers invoke production code and verifiers observe real output.
- [ ] Stubs JAR contains mappings/body files with the right version and classifier.
- [ ] Consumer Stub Runner uses the producer's **exact candidate artifact**.
- [ ] Consumer tests use real HTTP clients/message handlers, covering deserialization and error mapping.
- [ ] Multi-module CI runs the right module/phase, never mistaking another module's unit tests for producer verification.
- [ ] Logs and reports provide enough evidence to trace failures by contract/framework/runner.
- [ ] No tokens or real customer data are hardcoded in contracts or test fixtures.
- [ ] Breaking changes are verified against supported active consumers.

## 37. Self-check questions

**1. Why isn't the appearance of generated Java files enough to prove a contract is verified?**

Because tests might fail to compile, go undiscovered by Surefire/Failsafe, or be skipped. Test reports are needed to prove execution and assertions ran against the real producer.

**2. Do the Spring Cloud Contract Maven plugin and Maven Surefire perform the same job?**

No. The SCC plugin processes contracts and generates tests/stubs; Surefire is the test runner executing tests during Maven's `test` phase.

**3. When should Failsafe be used instead of Surefire?**

When a project intentionally structures tests as integration tests in the `integration-test/verify` lifecycle, usually matching `*IT`. Failsafe executions must be configured while avoiding double runs.

**4. Why must JUnit 5 generated tests match the test base?**

Because Jupiter annotations and lifecycle differ from JUnit 4. If generated tests use `org.junit.jupiter.api.Test`, `@BeforeEach` setup and the runner must align.

**5. Why not use MockMvc for every producer?**

Because MockMvc targets the Spring MVC stack. WebFlux or a live HTTP server has better-fitting adapters/modes; always check your SCC version and generated code.

**6. Is it safe for the test base to spin up a fake controller returning the contract body?**

No, if the goal is verifying the producer implementation. Tests pass even when real code is broken. Invoke production controllers/services within contract scope.

**7. Why might `./mvnw verify` still fail to run integration tests?**

Because Failsafe is not configured to run `integration-test` and `verify` goals, or test naming/includes do not match. Maven phases do not configure every plugin automatically.

**8. How do `-DskipTests` and `-Dmaven.test.skip=true` differ?**

Typically `skipTests` skips test **execution**; `maven.test.skip` can skip both test **compilation and execution**. Both are dangerous in compatibility verification stages.

**9. Why isn't it enough for producer tests to pass after changing a field in both producer and contract?**

Because older consumers may still read the old field. You must test consumers against the **stub generated from that exact candidate contract/version**, not a stale cache.

**10. What minimum evidence does CI need?**

Contracts discovered, generated tests compiled, **tests executed > 0**, assertions passing against the real producer, valid stubs JAR, explicit artifact version/commit, and consumer tests running Stub Runner with the exact candidate.

## 38. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, Groovy/YAML DSL, producer tests, and Stub Runner.
- [Spring Cloud Contract — Maven Project Features](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): plugin, lifecycle, generated tests, and stubs.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): HTTP/message contract syntax.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): consumer compatibility testing.
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): `test`, `integration-test`, `verify`, `package`, and `deploy` phases.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): test discovery, includes/excludes, reports, and JUnit Platform.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): integration tests and the `verify` goal.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): Jupiter lifecycle, test annotations, and discovery.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): testing MVC without a TCP server.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing WebFlux HTTP endpoints.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): determining which requests match stubs.

**Version note:** `testFramework/testMode` values, generated source paths, goal bindings, JUnit/Jupiter providers, the `@LocalServerPort` package, Surefire/Failsafe behavior, and stub packaging can vary across Maven/SCC/Spring Boot lines. Always check documentation of the **exact same version** as your real build. Placeholder versions must be replaced with supported versions; commands and examples illustrate the workflow and **are not results executed against a repository during authoring**.

---

**Key takeaway:** To "run generated tests with the right test tool," connect **Spring Cloud Contract generator → JUnit/test framework → Maven Surefire/Failsafe → right-mode test base → real producer implementation**. Only when generated tests actually execute, produce reports, and turn red when the producer violates a contract do they provide verification value. Only then should you package the stubs JAR for the **exact candidate commit** and have consumers run **Stub Runner** in CI to catch incompatible API changes.
