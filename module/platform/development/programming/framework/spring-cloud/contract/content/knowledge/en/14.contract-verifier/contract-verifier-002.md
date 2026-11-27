# Choosing Framework, Language, and Test Mode in Contract Verifier

In **Spring Cloud Contract**, writing Groovy/YAML DSL contracts is only the first step. To ensure the **producer** implements the exact HTTP or messaging behavior that the **consumer** relies on, **Spring Cloud Contract Verifier** must translate contracts into tests and execute them in an appropriate environment. Choosing the **test framework**, **generated test language**, and **test mode** directly affects the generated test code, the base class you must prepare, the dependencies to declare, and how closely the HTTP environment is simulated.

This lesson belongs to the **Contract Verifier** chapter of the **SPRING_CLOUD_CONTRACT** module. Its goal is to provide an informed selection guide for **Spring MVC**, **Spring WebFlux**, or applications requiring real HTTP testing, rather than choosing by habit. Alongside generated producer tests, the Spring Cloud Contract workflow can also generate and publish **stubs**, allowing consumers to run **Stub Runner** in CI to detect incompatible API changes early. These two streams share the same contract source but have distinct responsibilities.

## 1. Three Independent Decisions to Distinguish

When configuring Contract Verifier, teams often conflate the following three choices into one:

| Decision | Question Answered | Examples |
| --- | --- | --- |
| **DSL used to write contracts** | What format will the team use to describe requests/responses or messages? | `.groovy`, `.yml`/YAML files supported by the tool version. |
| **Test framework and generated test language** | Which engine/assertion library and test syntax do generated tests run with? | JUnit 5/Java, JUnit 4/Java in legacy projects, Spock/Groovy. |
| **Test mode / HTTP test client** | What mechanism will generated tests use to send requests to the producer? | `MOCKMVC`, `WEBTESTCLIENT`, `EXPLICIT`; some integrations also offer `JAXRSCLIENT`. |

**Key takeaway:** using **Groovy DSL does not force generated tests to be Groovy/Spock**. For example, a `get_paid_order.groovy` file can generate a **JUnit 5 test in Java** running in **MockMvc** mode. Likewise, a YAML contract can still be used in a project choosing JUnit 5 or Spock if the toolchain supports that combination.

Choosing a DSL concerns **how contracts are written**; `testFramework` concerns **how test code is generated and run**; `testMode` concerns **how generated tests interact with the producer**. Do not change all three at once just because a test fails, as it becomes difficult to tell whether the error comes from DSL syntax, the test engine, or HTTP setup.

## 2. Where Do Generated Producer Tests Fit in the Overall Workflow?

Consider **Order Service** as the producer and **Billing Service** as the consumer. Billing calls:

~~~http
GET /api/orders/42
Accept: application/json
~~~

and expects:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

Spring Cloud Contract can use one contract as input for two branches:

~~~mermaid
flowchart TD
    C["Groovy or YAML contract"] --> G["Contract Verifier generates producer test"]
    C --> S["Generate HTTP/messaging stub"]
    G --> M["JUnit or Spock runs under testMode"]
    M --> P{"Real producer matches contract?"}
    P -->|No| F["Build/CI fails"]
    P -->|Yes| A["Allow packaging and publishing stubs"]
    S --> A
    A --> R["Stub Runner downloads and starts stub"]
    R --> T["Consumer writes and runs tests for real client code"]
~~~

**Generated producer tests** test **Order Service code**, not a stub. **Consumer tests** test **Billing Service code** against the stub, typically written by the consumer team. **Stub Runner** locates and launches the stub; it does not automatically generate all business assertions for Billing. Allowing stubs to be published only after producer tests pass is a **CI rule that must be enforced**, because stub artifacts can be produced during the build before all tests complete.

Therefore, picking the right framework and test mode ensures the producer branch delivers real value. If tests are generated but never run, or only call a mock environment that omits the controller/service under test, a green pipeline does not prove the promise was verified.

## 3. Choosing a Test Framework: JUnit 5, JUnit 4, or Spock?

Common options in the Spring Cloud Contract Verifier ecosystem:

| Test Framework | Typical Generated Test Language | When Suitable | Prerequisites to Verify |
| --- | --- | --- | --- |
| **JUnit 5 / Jupiter** (`JUNIT5`) | Java | Modern Spring Boot projects where the team uses Java and Jupiter. | Compatible test engine, Maven Surefire/Gradle test discovery, Jupiter annotations, Spring Test. |
| **JUnit 4** (`JUNIT`, in supported versions) | Java | Maintaining legacy systems with many existing JUnit 4 tests. | Compatibility with the Contract Verifier and Spring versions in use; migration strategy to Jupiter. |
| **Spock** (`SPOCK`, if supported by the version combination) | Groovy | Teams familiar with `given/when/then` style already using Spock/Groovy for tests. | Compatible Groovy, Spock, Spring Boot, plugin versions, and test runner setup. |

**Recommendation for new projects using Java and modern Spring Boot:** start with **JUnit 5** if your release train supports it; it aligns with most Spring Boot test suites today. Do not pick JUnit 4 in a new project merely to keep familiar syntax.

**Spock** is helpful when a team already has a Groovy background, but choosing it involves more than flipping a single `testFramework` line. You need the right Spock dependencies, Groovy test source compilation, and the corresponding execution runner. If the plugin generates Spock tests while the build is only configured to run Java/JUnit, those tests may be missed.

**Application source language and test language are two different things.** A producer can be written in Java or Kotlin while still using Groovy/YAML contracts. The team must verify that the chosen test framework generates code the pipeline can compile and execute. Do not assume a Kotlin application must generate Kotlin tests; the exact choice depends on plugin capabilities and project configuration.

### 3.1. Do Not Mix JUnit 4 and JUnit 5 Randomly

With JUnit 5, the base class typically uses:

~~~java
import org.junit.jupiter.api.BeforeEach;

@BeforeEach
void setUp() {
    // Prepare MockMvc, RestAssured, or fixtures.
}
~~~

In JUnit 4, the corresponding setup mechanism normally uses `org.junit.Before` and different runner annotations. If generated tests target **JUnit 5** while the base class uses an incompatible setup/engine, initialization may not run as expected. Standardize on one framework for contract tests or explicitly configure legacy compatibility rather than relying on auto-detection.

## 4. Choosing Test Mode by Application Type and Verification Scope

**Test mode** answers: how do generated producer tests interact with the producer's HTTP interface? The three most relevant options across most Spring projects:

| Mode | Interaction Mechanism | Best Suited When | Known Limitations |
| --- | --- | --- | --- |
| **`MOCKMVC`** | Uses **Spring MockMvc** to invoke Spring MVC handlers inside the test context, without a real HTTP socket. | Producer is a **Spring MVC** application or Servlet controller needing fast, stable tests. | Does not verify the full HTTP server, connector, proxy, or deployment network behavior. |
| **`WEBTESTCLIENT`** | Uses **Spring WebTestClient** tailored for the WebFlux/reactive stack and application test configuration. | Producer is built on **Spring WebFlux**. | Requires proper reactive client binding and test context setup; does not implicitly test external infrastructure. |
| **`EXPLICIT`** | Sends HTTP requests to a **real running server** at a URL/port configured for generated tests. | Need to test the application's real HTTP stack, custom filters/network adapters, or non-MockMvc cases. | Slower startup, port/server dependencies; can encounter environment issues MockMvc does not hit. |

Some Spring Cloud Contract versions/integrations also provide **`JAXRSCLIENT`** for JAX-RS applications. Choose it only when **both the plugin version and producer stack genuinely support it**, with matching client and base test configuration; do not pick it for an ordinary `@RestController` simply because its name sounds like an HTTP client.

**Do not equate `EXPLICIT` with "requiring a shared remote environment."** In a Spring Boot test, the test itself can start the producer via `@SpringBootTest(webEnvironment = RANDOM_PORT)` and send HTTP requests to that local port. This uses a real HTTP server while remaining isolated on the developer machine or CI runner.

### 4.1. Quick Selection Diagram

~~~mermaid
flowchart TD
    A{"Which stack serves HTTP in the producer?"}
    A -->|Spring MVC| B{"Need to test real server/network adapter?"}
    B -->|No| C["MOCKMVC"]
    B -->|Yes| D["EXPLICIT"]
    A -->|Spring WebFlux| E{"Want to test via WebTestClient?"}
    E -->|Yes| F["WEBTESTCLIENT"]
    E -->|Want real HTTP server| D
    A -->|JAX-RS or other stack| G["Check plugin-supported combination"]
    G --> H["JAXRSCLIENT if suitable or EXPLICIT"]
    C --> I["Choose JUnit 5/Spock per toolchain"]
    F --> I
    D --> I
    H --> I
~~~

If you want both high speed and protection for real HTTP deployment characteristics, you can use **MockMvc** for most generated tests and add a focused set of **real-HTTP integration tests**. There is no need to force every test to use `EXPLICIT` if the target risk is already covered at the right layer.

## 5. Shared Sample Contract for All Three Modes

To see that **test mode does not change contract meaning**, let us use a Groovy HTTP contract in the producer at:

`src/test/resources/contracts/orders/get_paid_order.groovy`

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Returns status of paid order 42'

    request {
        method 'GET'
        url '/api/orders/42'
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

In essence, the generated test must issue a request equivalent to **GET /api/orders/42**, then assert **HTTP 200**, **JSON Content-Type**, `id=42`, and `status=PAID`. What differs across MockMvc, WebTestClient, and explicit HTTP is **the request execution tool and environment initialization**, not permission for the producer to alter status codes or schemas.

The contract can be written in **YAML DSL** instead of Groovy; that choice does not change the test mode either. Equivalent example:

~~~yaml
description: Returns status of paid order 42
request:
  method: GET
  url: /api/orders/42
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

These two snippets are **two ways to express the same behavior**. Within a single build, avoid placing both equivalent Groovy and YAML files in the scanned directory to prevent duplicate or conflicting tests and stubs.

## 6. Spring MVC Producer Example to Try the Options

Create a simple Spring Boot application with an endpoint matching that behavior:

~~~java
package com.acme.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

And the controller:

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
                org.springframework.http.HttpStatus.NOT_FOUND);
        }
        return new OrderView(42L, "PAID");
    }

    public record OrderView(long id, String status) {}
}
~~~

This is a **learning fixture**, hardcoding order 42 so verification does not depend on a database. In a real project, the base test should wire services, mock dependencies, or seed deterministic data; do not put hardcoded ID logic like this into production business flows.

## 7. Configuring Contract Verifier for JUnit 5 and MockMvc

For a Spring MVC producer using Maven, configure the required test dependencies, for example:

~~~xml
<dependencies>
    <!-- Along with spring-boot-starter-web in the producer application. -->
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
~~~

Under `<build><plugins>` in `pom.xml`, configure the plugin:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>com.acme.orders.ContractTestBase</baseClassForTests>
    </configuration>
</plugin>
~~~

**Note:** these XML snippets are **POM fragments**, not a complete standalone POM. The project needs a Spring Boot parent or BOM, a compatible Spring Cloud BOM, and a properly declared `spring-cloud-contract.version` property; the plugin version must match the Spring Cloud Contract dependency versions in use. Do not pick a plugin version independently from the release train.

From this configuration:

- `testFramework=JUNIT5`: generates tests targeting **JUnit Jupiter**.
- `testMode=MOCKMVC`: uses **MockMvc** to invoke Spring MVC.
- `baseClassForTests`: generated tests extend `ContractTestBase`, which prepares the Spring context and request execution tool.

### 7.1. Writing a Proper Base Test with MockMvc

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

**Why is this the base class?** Spring initializes the Order Service context and configures `MockMvc`; the setup connects Rest Assured MockMvc to that context. Generated tests inherit from this class so requests hit the **real producer controller inside the test context**, not a WireMock stub.

Across different versions and configurations, the way generated tests call Rest Assured MockMvc may vary; inspect the Java code in the generated test sources directory to confirm it uses the object/configuration provided by the base test. Do not edit generated tests directly; the next generation run can overwrite them.

## 8. Switching to EXPLICIT When You Need to Test a Real HTTP Server

Keep the **Groovy contract from section 5** and **JUnit 5**, but change the plugin configuration to:

~~~xml
<configuration>
    <testFramework>JUNIT5</testFramework>
    <testMode>EXPLICIT</testMode>
    <baseClassForTests>com.acme.orders.HttpContractTestBase</baseClassForTests>
</configuration>
~~~

In this mode, generated tests use an HTTP client to call the producer over a listening port. With Spring Boot, the test can start the application itself using `RANDOM_PORT`:

~~~java
package com.acme.orders;

import io.restassured.RestAssured;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(
    classes = OrderApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
public abstract class HttpContractTestBase {

    @LocalServerPort
    private int port;

    @BeforeEach
    void configureHttpClient() {
        RestAssured.baseURI = "http://localhost";
        RestAssured.port = port;
        RestAssured.basePath = "";
    }
}
~~~

This example assumes generated tests use **Rest Assured HTTP** in explicit mode as supported by the corresponding toolchain. The Boot test starts an HTTP server on an available port, injects it via `@LocalServerPort`, and directs requests there. The exact initialization must match the HTTP client library and **the actual test code generated by the plugin**; if the custom base test is not extended or the port is not set, requests will be sent to the wrong address.

**Meaningful Comparison:**

| Aspect | MockMvc | EXPLICIT |
| --- | --- | --- |
| Calls `@RestController` via Spring test context. | Yes. | Yes, through an HTTP server. |
| Requires a real HTTP socket and port. | No. | Yes. |
| Tests additional real HTTP server/connector behavior. | Limited. | Offers broader coverage depending on how the app starts. |
| Speed and environmental stability. | Generally faster with fewer port dependencies. | Generally heavier; can hit port/startup issues. |
| Covers all production proxies, DNS, TLS, and networking. | No. | **Not automatically**; requires a corresponding test environment to verify those layers. |

Note that **Rest Assured uses static configuration** in the example above: when running generated tests in parallel across multiple servers/ports, tests can interfere with each other if they mutate global state concurrently. For parallel CI runs, design isolation per configuration or test class, or disable parallelism for affected suites; do not assign multiple ports into shared global configuration and expect deterministic results.

## 9. When the Producer Uses Spring WebFlux: WEBTESTCLIENT

For a **Spring WebFlux** application, consider `WEBTESTCLIENT` instead of `MOCKMVC`. Example plugin configuration:

~~~xml
<configuration>
    <testFramework>JUNIT5</testFramework>
    <testMode>WEBTESTCLIENT</testMode>
    <baseClassForTests>com.acme.orders.WebFluxContractTestBase</baseClassForTests>
</configuration>
~~~

An experimental base class can boot the WebFlux application context:

~~~java
package com.acme.orders;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;

@SpringBootTest(
    classes = OrderApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
public abstract class WebFluxContractTestBase {
    // Add WebTestClient/binding according to the generated test code and
    // capabilities of the Spring Cloud Contract version in use.
}
~~~

This is a **setup skeleton**, not a guarantee that copying it verbatim will run generated tests across every version. Depending on the Spring Cloud Contract version, `WEBTESTCLIENT` configuration may require a specific client/binding or static holder; **read the generated test class** to see what the base test must supply. Use compatible WebFlux starter, Spring Boot Test, and Contract Verifier versions.

**Reactive does not mean tests automatically handle every asynchronous aspect.** Design deterministic responses, timeouts, and fixtures; for streaming or scenarios that cannot be represented as a finite HTTP response, choose suitable contracts and test methods. If you want to test WebFlux's real HTTP server instead of WebTestClient via mocked bindings, you can consider `EXPLICIT` against a real server, depending on plugin version support.

## 10. When Should You Keep JUnit 4 or Choose Spock?

### 10.1. Legacy Projects Using JUnit 4

In a legacy system running JUnit 4 with a Spring Cloud Contract version that supports it, the configuration can select:

~~~xml
<configuration>
    <testFramework>JUNIT</testFramework>
    <testMode>MOCKMVC</testMode>
    <baseClassForTests>com.acme.orders.LegacyContractBase</baseClassForTests>
</configuration>
~~~

The base class must then follow **JUnit 4/Spring Test** conventions. Do not take the JUnit 5 base test from section 7 and merely swap `testFramework` without checking the runner, setup annotations, and test discovery. For new Spring Boot projects, evaluate migrating toward JUnit 5 instead of prolonging a legacy combination solely for generated tests.

### 10.2. Teams Already Using Spock/Groovy

If a project already has a Spock test suite and a compatible Groovy toolchain, you may consider:

~~~xml
<configuration>
    <testFramework>SPOCK</testFramework>
    <testMode>MOCKMVC</testMode>
    <baseClassForTests>com.acme.orders.SpockContractBase</baseClassForTests>
</configuration>
~~~

Appropriate **Spock and Spring integration** libraries, Groovy compilation configuration, and spec discovery during test execution are required. A Spock base class normally uses Spock lifecycle/setup methods rather than JUnit Jupiter's `@BeforeEach`. Confirm that the plugin generates valid Groovy/Spock code, that specs actually execute, and that fixture data is available.

**Practical rule of thumb:** a Java/JUnit Jupiter team does not need to introduce Groovy/Spock just because contracts are written in Groovy DSL; conversely, a team already invested in Spock does not need to abandon it if their Spring Cloud Contract version supports it cleanly and CI runs specs reliably.

## 11. Verifying That Generated Tests Actually Run

After configuring the producer, run from the project directory:

~~~shell
mvn clean verify
~~~

With Maven, a plugin bound to the appropriate lifecycle reads contracts, generates test code, and lets the test runner execute those tests. **Do not look only at the `BUILD SUCCESS` line.** Check:

1. **Contract loaded:** `get_paid_order.groovy` is processed by the plugin.
2. **Tests generated:** Java/JUnit 5 or Groovy/Spock files matching `testFramework` exist in generated test sources.
3. **HTTP code matches `testMode`:** MockMvc calls Spring MVC; EXPLICIT calls an HTTP server; WebTestClient uses a properly configured reactive client.
4. **Tests executed:** Surefire/Gradle reports show at least one test for the sample contract actually ran, without being skipped or filtered out.
5. **Assertions verify the right content:** request `GET /api/orders/42` is sent and the response has status `200`, `id=42`, `status=PAID`.
6. **Capable of catching errors:** change `status` to `state` in the controller, keep the contract unchanged, and re-run; the generated test must fail.

The generated test code may carry semantics equivalent to the following illustration:

~~~java
// Assertion illustration, not verbatim Java code generated by the plugin.
given()
    .get("/api/orders/42")
.then()
    .statusCode(200)
    .body("id", equalTo(42))
    .body("status", equalTo("PAID"));
~~~

The request library, static imports, base test wiring, and generated filenames depend on version, mode, and framework. **Do not manually edit generated tests** to fix failures; fix the contract, base test, or implementation instead.

## 12. Which Test Mode Should You Pick If a Producer Has Multiple Interfaces?

A producer may expose both HTTP controllers and message-publishing workflows. Do not assume one HTTP `testMode` configuration automatically covers every interface.

| Interface Type to Verify | Testing Approach |
| --- | --- |
| Spring MVC REST API | Choose `MOCKMVC` when in-process controller testing suffices; use `EXPLICIT` if a real HTTP server is needed. |
| Spring WebFlux REST API | Choose `WEBTESTCLIENT` when supported by the plugin and application; consider `EXPLICIT` for a real HTTP server. |
| JAX-RS endpoint | Check `JAXRSCLIENT` support in your version or use HTTP `EXPLICIT` with a suitable setup. |
| Producer **emitting messages** | Configure messaging testing, event triggers, and message-capturing mechanisms; do not replace with a plain WireMock request. |
| HTTP behind gateway, proxy, TLS | Generated producer tests can check the endpoint; add **supplementary integration/E2E tests** if gateway/proxy/TLS behavior itself is part of the promise. |

For messaging, Spring Cloud Contract can describe message triggers, destinations, headers, and payloads. Generated tests need **configuration to trigger and observe the producer emitting real messages**. The HTTP modes in the previous table do not substitute for testing brokers, transactions, retries, or event ordering on real infrastructure.

## 13. Connecting Producer Test Choices to Stub Publishing

Suppose Order Service uses **JUnit 5 + MockMvc** and producer tests pass. The build can package stubs as a Maven artifact with the `stubs` classifier, for example:

~~~text
com.acme:order-service:1.0.0:stubs
order-service-1.0.0-stubs.jar
~~~

The consumer can use Stub Runner to download and run that artifact:

~~~java
@SpringBootTest(properties = "orders.base-url=http://localhost:8089")
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs:8089",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientStubTest {

    @Autowired OrderClient orderClient;

    @Test
    void readsPaidOrder() {
        OrderDto dto = orderClient.getOrder(42L);
        assertThat(dto.status()).isEqualTo("PAID");
    }
}
~~~

This is an **illustrative consumer test**, assuming imports, dependencies, `OrderClient`, `OrderDto`, and an installed artifact in local Maven exist. If consumer CI fetches stubs **published to a remote repository**, switch to `REMOTE` along with `repositoryRoot` and proper authentication.

Crucially, **whether the producer used JUnit 5/MockMvc, Spock, or explicit HTTP does not alter the nature of the stub**: stubs are generated from the **contract**, while generated tests use the chosen test mode to verify the producer implements that contract. The consumer does not need to know whether the producer ran MockMvc or Rest Assured, but it does need to know **the stub version coordinates and mocked interface**.

A reliable CI pipeline should:

1. **Build and run generated producer tests** using the configured framework and mode.
2. **Block publishing when producer verification fails.**
3. **Package and publish versioned stubs**, traceable to verified source code and contracts.
4. **Run consumer tests via Stub Runner**, verifying the consumer's HTTP/messaging client code against protected scenarios.
5. **Verify backward compatibility** before modifying or removing contracts still relied upon by older consumer versions.

## 14. Common Configuration Pitfalls

| Symptom | Likely Cause to Check | Resolution |
| --- | --- | --- |
| Plugin generates Java tests, but Maven reports 0 tests. | Surefire/Test engine not recognizing JUnit 5; generated sources folder not added to compile/test lifecycle; tests filtered out. | Inspect runner reports, test names, plugin lifecycle, and test engine. |
| `NullPointerException` or requests fail to run in MockMvc mode. | Base test did not create/attach `MockMvc` or generated class does not extend the right base class. | Check `baseClassForTests` name, `@AutoConfigureMockMvc`, and `RestAssuredMockMvc` setup. |
| Generated test uses WebTestClient, yet producer is plain Spring MVC. | `WEBTESTCLIENT` choice mismatches application/test client setup. | Consider `MOCKMVC` or check supported WebTestClient configuration. |
| `EXPLICIT` test reports `Connection refused`. | No server running, wrong base URI, or port not injected. | Use `RANDOM_PORT` and configure Rest Assured with the actual port; inspect startup logs. |
| Test runs over HTTP but hits the wrong path. | Base path/servlet context path mismatches URL in contract. | Compare actual route, `RestAssured.basePath`, and contract endpoint. |
| Switched `testFramework` to Spock, and tests do not execute. | Missing Groovy/Spock dependencies, compile plugin, or spec discovery. | Complete the toolchain and confirm Spock specs actually run. |
| Build succeeds, yet changing controller field `status` to `state` goes undetected. | Generated tests skipped, contract not loaded, or assertions too loose. | Check test count, generated sources, matchers, and intentionally break the contract. |
| MockMvc tests pass, but production fails with reverse proxy or TLS. | MockMvc does not test deployment HTTP infrastructure. | Add integration/E2E tests over real network paths and matching config. |
| Stub published despite red producer tests. | CI does not gate publishing on test results. | Enforce mandatory passing producer verification before publishing. |
| JUnit 4 base test stops working after switching to JUnit 5. | Setup annotations/runner or test discovery mismatch. | Use a Jupiter-compliant base test and update the test engine, or keep a supported legacy combo. |

When diagnosing issues, follow the chain **contract loaded → test generated for right framework → base test initializes right mode → test actually executes → assertions compare real implementation → stub artifact published after passing**. This chain separates tooling errors from producer contract violations.

## 15. Hands-On Lab: Comparing MOCKMVC and EXPLICIT on the Same Contract

To observe the impact of test mode selection, practice on a sample Order Service project:

1. **Prepare** a Spring MVC application with endpoint `GET /api/orders/42` returning `{"id":42,"status":"PAID"}` and add a matching Groovy/YAML contract file.
2. **Choose JUnit 5 + MOCKMVC**, configure `ContractTestBase`, run `mvn clean verify`, and confirm the generated producer test **actually runs and PASSES**.
3. **Break the contract intentionally:** rename the JSON field from `status` to `state` while keeping the contract unchanged. Re-run tests and confirm **FAIL**.
4. **Revert** the controller, then switch `testMode` to `EXPLICIT` and swap to `HttpContractTestBase` with `RANDOM_PORT`. Re-run the same contract and confirm PASS.
5. **Inspect the differences:** compare generated tests and setup logs. MockMvc requires no HTTP socket; EXPLICIT waits for the server to boot and binds to the real port.
6. **Induce a controlled port failure:** omit port configuration in the EXPLICIT base test; observe the connection error, then restore it. Explain why this error is a **test environment failure**, not evidence that the endpoint violated its JSON schema.
7. **Package the stub** after producer tests pass, install it to the local repository or publish a test version. Have Billing run its consumer test via Stub Runner and confirm it reads `PAID`.
8. **Summarize your choice:** if a team builds a Spring MVC REST API needing a fast pipeline, why is MockMvc a sensible default? What specific project situations call for EXPLICIT to expand verification scope?

If your team uses WebFlux, replace the MockMvc comparison with **WEBTESTCLIENT vs. EXPLICIT**, making sure to use a WebFlux producer and suitable base test rather than changing a single POM value.

## 16. Decision Checklist and Self-Check Questions

A sound configuration decision can be documented concisely:

| Question to Finalize | Sample Answer for Order Service |
| --- | --- |
| Which DSL is used to write contracts? | Groovy for simple HTTP request/response, currently maintained by the team. |
| Which test framework/language is generated? | `JUNIT5`, Java tests running on Jupiter. |
| Which HTTP stack does the producer use? | Spring MVC with `@RestController`. |
| Which test mode is suitable? | `MOCKMVC` for generated producer tests; supplement with HTTP integration tests when needed. |
| Which base test is chosen? | `com.acme.orders.ContractTestBase` initializing the Spring context and MockMvc. |
| What indicates successful verification? | Generated tests run and PASS, and FAIL when intentionally breaking the `status` field. |
| How do stubs reach the consumer? | Versioned `stubs` artifact consumed via Stub Runner in CI. |

Answer the following questions yourself:

- If a contract is written in Groovy DSL, must generated tests use Spock? Why or why not?
- How does `testFramework` differ from `testMode`? For example, do `JUNIT5` and `MOCKMVC` decide the same thing?
- When is `MOCKMVC` more suitable than `EXPLICIT`, and vice versa?
- Why does `EXPLICIT` using a local HTTP port still not replace all production network/gateway checks?
- Why should a WebFlux producer consider `WEBTESTCLIENT` instead of copying a MockMvc setup by default?
- If generated Java tests exist but the Maven report shows zero tests executed, can you conclude the producer is verified?
- What else is required when switching to Spock besides `<testFramework>SPOCK</testFramework>`?
- Why do green consumer tests against a stub not prove the real producer honors the contract if producer verification was skipped?

**Remember:** treat **DSL**, **test framework/language**, and **test mode** as three separate decisions. For Spring MVC, usually start with **JUnit 5 + MockMvc**; for WebFlux, consider **WebTestClient**; when a real HTTP server must be verified, use **EXPLICIT** with the right base test and port. After configuring, **inspect generated tests, confirm they actually execute, induce a failure to prove mismatch detection**, and only then publish stubs for consumers to use via Stub Runner. The value of Spring Cloud Contract lies in both sides verifying the same validated contract, not merely in seeing a green build badge.
