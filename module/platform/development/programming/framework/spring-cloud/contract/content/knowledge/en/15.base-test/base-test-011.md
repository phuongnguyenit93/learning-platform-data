# Avoiding Base Tests That Mock the Very Producer Behavior Under Verification

## 1. The problem: valid contracts can still produce false greens

In **Spring Cloud Contract (SCC)**, the producer and consumer agree on HTTP or messaging behavior via **Groovy DSL/YAML DSL**. **Contract Verifier** generates tests for the producer; from contracts, **stubs** can also be packaged for consumers to run with **Stub Runner**. Bringing both tracks into CI helps detect breaking API changes before deployment.

However, a generated contract test is only trustworthy when it genuinely **executes the producer implementation under verification**. If the **base test** stands up a fake controller or mock that returns the exact sample response from the contract, tests can always pass even when the real controller, service, or logic was broken.

This is an especially dangerous test-design flaw: **the test proves that a test-authored mock matches the contract rather than proving the producer matches the contract**.

For example, the contract states:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

If the base test creates a fake controller returning that exact JSON, generated tests will pass even if the production app renamed the `available` field to `inStock`. At that point, **BUILD SUCCESS** does not reflect compatibility of the real API.

### Learning outcomes

After this article, you will be able to:

1. Explain how far a base test may go in **setting up the environment** without simulating the behavior under verification.
2. Distinguish a **real Spring context**, a fake controller, a mocked service, a fake repository, and stubs of external systems.
3. Write a Spring Boot/MockMvc base test wired to **the real controller and service**.
4. Spot anti-patterns such as `standaloneSetup` with a fake controller, `@MockitoBean` returning complete sample responses, or using WireMock in place of the producer itself.
5. Design deterministic test data while preserving **critical business execution paths**.
6. Use intentional producer mutations to verify that generated tests can genuinely catch bugs.
7. Identify where HTTP/message verification, consumer Stub Runner tests, and additional CI gates are needed.

## 2. What is the base test's job?

Contract Verifier generates tests, but generated tests need an **execution environment**: Spring ApplicationContext, HTTP adapters, sample data, mocks for external systems, or message triggers. The base test class wires these pieces together.

A proper base test typically:

- Boots the **producer application** with an appropriate Spring Boot test context.
- Configures **MockMvc, WebTestClient, or real HTTP** matching the plugin's generated test mode.
- Prepares repeatable data (test database, fixtures, fixed clock when appropriate).
- Isolates out-of-scope dependencies (third-party services, SMTP, payment gateways, external APIs).
- Provides **custom assertions** or message-trigger methods when contracts need them.
- Restores state between tests to prevent order-dependent results.

The base test **should never** hardcode responses for the endpoint the contract protects, unless the team **intentionally** restricts the test to a narrow slice and explicitly documents that limitation.

| Action in base test | Usually appropriate? | Condition |
|---|---|---|
| Loading Spring context with production controller | **Yes** | Generated tests invoke the real bean/endpoint |
| Configuring MockMvc with real context | **Yes** | Production controller is not replaced by a fake |
| Creating test rows in a dedicated database | **Yes** | Tests traverse queries and mappers under verification |
| Mocking an external email gateway | **Possibly** | Real email behavior is outside the contract under test |
| Mocking a repository to return raw data | **Possibly** | Service/controller/serialization stay real, scope is documented |
| Mocking a service to return a prebuilt response DTO | **High risk** | Skips service logic, testing only a thin HTTP layer |
| Creating a fake controller returning contract JSON | **No**, if verifying the real API | Tests never touch the production implementation |
| Having WireMock answer instead of the producer endpoint | **No**, if goal is producer verification | Verifies a stub rather than the producer |

**Key question:** "If I break the production code this contract is meant to protect, does this generated test turn red?" If not, revisit the base test or contract scope.

## 3. Three testing boundaries to keep separate

~~~mermaid
flowchart TD
    A["HTTP Contract"] --> B["Generated producer test"]
    B --> C["Base test configures HTTP/test context"]
    C --> D["Production controller"]
    D --> E["Production service"]
    E --> F["Repository or data adapter"]
    F --> G["Test DB / fake at chosen cut point"]
    A --> H["Stub artifact"]
    H --> I["Stub Runner for consumer"]
    I --> J["Consumer production HTTP client"]
~~~

In the diagram:

- **Producer verification** follows the upper branch: generated test requests must reach the **production controller** and traverse the application components the team wants to prove.
- **Controlled cut points** can sit at the database or an outbound port to an external service. Placing the cut point at **the very service implementing the contract**, however, blinds the test to service logic bugs.
- **Consumer verification** uses the producer's stub to test consumer clients/handlers. Stub Runner **does not replace** verifying the producer implementation.

There is no single "right depth for every project." A simple HTTP contract may scope to controller + mapper; a contract covering pricing rules, stock checks, or business errors may need both service and repository running. What is mandatory is **stating the scope explicitly and verifying that scope**—never claiming full-system coverage after mocking the most critical part.

## 4. Real producer example: Inventory Service

Suppose Inventory Service enforces the rule: when stock quantity exceeds 0, `available=true`. That is the rule tests must protect.

A data model:

~~~java
package com.example.inventory;

public record InventorySnapshot(
        String sku,
        boolean available,
        int quantity) {
}
~~~

**Production** service (kept in-memory here so the execution path is easy to inspect):

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final Map<String, Integer> stock =
            Map.of("SKU-123", 12, "SKU-456", 0);

    public InventorySnapshot find(String sku) {
        int quantity = stock.getOrDefault(sku, 0);
        return new InventorySnapshot(sku, quantity > 0, quantity);
    }
}
~~~

**Production** controller:

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
    public InventorySnapshot find(@PathVariable String sku) {
        return service.find(sku);
    }
}
~~~

This sample is intentionally simple to focus on testing. A real system typically queries a repository/database, needing fixtures or a test database for deterministic SKUs and stock counts. The essential point remains that **the controller and the logic converting quantity to `available` belong to production code**.

## 5. What does the HTTP contract protect?

Illustrative Groovy DSL file at `src/test/resources/contracts/inventory/get-available-stock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout needs to know SKU-123 has 12 items in stock'

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

If the project uses YAML DSL, an equivalent alternative is:

~~~yaml
description: Checkout needs to know SKU-123 has 12 items in stock
name: get_available_stock

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

These two snippets are **mutually exclusive alternatives**. The contract specifies desired behavior, yet **does not dictate which controller gets called**. That depends on test mode/base test configuration.

Here, the test is meaningful only if `GET /api/inventory/SKU-123` hits the **real InventoryController**, and `available` is computed by the **real InventoryService**. If the test returns a sample body from a fake class, the contract is only verified against test-authored data.

## 6. Correct base test: using a real Spring context with MockMvc

When choosing **MockMvc** test mode matching your SCC version, the base test can be configured as:

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
    void setUp() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

This example targets a Spring Boot + Spring MVC project with **RestAssuredMockMvc** on the test classpath and the plugin configured to generate tests in **MockMvc mode**.

### Why is this more trustworthy than a fake controller?

1. `@SpringBootTest` initializes the **producer's ApplicationContext** (including scanned/configured beans).
2. `@AutoConfigureMockMvc` creates MockMvc wired to that Spring MVC context.
3. `@Autowired MockMvc` injects an adapter **bound to the real application context**.
4. `RestAssuredMockMvc.mockMvc(mockMvc)` supplies the adapter for generated tests to call HTTP handlers.
5. `InventoryController` and `InventoryService` remain ordinary production beans, unreplaced by fakes.
6. Contract tests observe actual status codes, headers, and JSON generated by the controller/service.

**MockMvc does not open a real TCP socket**, yet requests still pass through Spring MVC handler mappings, converters, validation, and controllers inside the test context. That differs fundamentally from **creating a fake controller** solely to return sample responses.

### An equivalent setup variant

Depending on project setup, the base test may use `WebApplicationContext`:

~~~java
@Autowired
WebApplicationContext context;

@BeforeEach
void setUp() {
    RestAssuredMockMvc.webAppContextSetup(context);
}
~~~

Pick **one** setup matching your test mode. In a real codebase, avoid mixing overlapping setups without a clear reason. Exact API names, imports, and support depend on RestAssured/SCC versions, so check your project's versions when implementing.

## 7. Bad base test: standaloneSetup with a fake controller

The counter-example below embodies the exact flaw this article warns against.

~~~java
package com.example.inventory;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

public abstract class WrongContractTestBase {

    @BeforeEach
    void setUp() {
        RestAssuredMockMvc.standaloneSetup(new FakeInventoryController());
    }

    @RestController
    @RequestMapping("/api/inventory")
    static class FakeInventoryController {

        @GetMapping("/{sku}")
        InventorySnapshot get(@PathVariable String sku) {
            // The test itself returns the response required by the contract.
            return new InventorySnapshot("SKU-123", true, 12);
        }
    }
}
~~~

Here generated tests send GET and receive the expected JSON, yet requests hit **FakeInventoryController** rather than production's `InventoryController`.

Consequences:

- Changing `InventoryService.find` from `quantity > 0` to `quantity == 0` may **leave the test green**.
- Deleting the real `GET /api/inventory/{sku}` mapping may **have zero effect** on tests.
- Changing production serializers or error handlers may be silently bypassed by tests.
- Tests simply verify a fake controller returning pre-programmed data, becoming a **self-fulfilling test**.

**Not all `standaloneSetup` usage is wrong.** Calling `standaloneSetup(new InventoryController(realService))` can work for an isolated controller test, provided you understand which Spring configuration, filters, controller advice, and components are omitted. It does not substitute for `@SpringBootTest` when contracts aim to protect the full application's HTTP interface.

For SCC-generated producer tests, the common safe default is a **base test that boots the real producer implementation** matching the agreed scope.

## 8. A subtler bad base test: mocking a service to return the full DTO

Sometimes a base test loads a real Spring context yet swaps the business bean for a mock:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
public abstract class RiskyContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    InventoryService inventoryService;

    @BeforeEach
    void setUp() {
        org.mockito.Mockito.when(
            inventoryService.find("SKU-123")
        ).thenReturn(
            new InventorySnapshot("SKU-123", true, 12)
        );

        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

This example uses `@MockitoBean` from Spring Framework lines supporting that annotation. Older projects use Spring Boot's `@MockBean`. Syntax changes across versions, yet the risk **stays identical**.

This style **still exercises the production controller, routes, serialization, and part of MVC configuration**, so it is not wholly useless. However, it **does not verify `InventoryService.find` logic**, because the response is pre-decided by the mock.

If the contract asserts "available when quantity > 0," mocking the entire service places the cut point **too high**: breaking changes inside the service will not turn contract tests red.

**Rule:** do not mock the processing unit the contract itself is meant to protect. When an MVC slice test is necessary, document explicitly that it protects only **HTTP adaptation/serialization**, and cover business logic with dedicated tests at another layer.

## 9. When are mocks/fakes reasonable?

Isolation does not mean "make everything real." Tests can use reasonable test doubles provided **the execution path under verification** remains intact.

Example architecture:

~~~text
GET /api/inventory/{sku}
    -> Real InventoryController
    -> Real InventoryService (available rule)
    -> InventoryRepository / InventoryGateway
    -> Test database or fake repository returning raw data
~~~

In this setup, you can:

- Use a **test database** seeded with SKU-123 and quantity 12. This also covers persistence mappings/queries when they matter.
- Use a **fake repository** returning an inventory entity/record if the goal is solely testing HTTP + service. The service still computes `available`.
- Mock an **email sender** or auxiliary audit system to prevent sending real notifications during tests.
- Stub **external services** called by the producer while ensuring the producer still processes external responses through real code.

Compare these two setups:

| Test setup | Still verifies `available = quantity > 0`? |
|---|---|
| Fake repository returns `StockEntity(quantity=12)`; real service computes `available` | **Yes** |
| Mock service returns prebuilt `InventorySnapshot(available=true, quantity=12)` | **No** |
| Fake controller returns sample body | **No** |
| Test database with stock rows; real controller/service/repository | **Yes**, with broader coverage |

Even a fake repository can produce false greens if it re-implements **the very business rule** under test. Cut points must be evaluated against **contract semantics**, not technology labels.

## 10. Stabilizing data while still testing the real implementation

Trustworthy tests need deterministic data independent across runs. Never achieve stability by hardcoding responses in the base class, though.

Appropriate techniques include:

- **Database migrations + fixtures:** create schemas and sample records in a test environment.
- **`@Sql` or fixture loaders:** insert SKUs and quantities used by contracts before tests, with proper cleanup/rollback.
- **Testcontainers:** run real databases or brokers in containers when near-production integration verification is needed.
- **Fixed clock:** inject a fixed test `Clock` when timestamps are generated by the app and exact wall time is non-essential.
- **Seeded random data** when diverse inputs are needed while preserving repeatability.
- **Test profiles:** point to isolated databases/test endpoints without weakening or replacing business implementations.

Conceptual `@Sql` usage on a base test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Sql(
    scripts = "/sql/inventory-contract-fixture.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
public abstract class ContractTestBase {
    // Set up RestAssuredMockMvc as in the earlier section.
}
~~~

This assumes **the project includes a matching SQL fixture file** and imports `org.springframework.test.context.jdbc.Sql`. It merely illustrates data-organization mechanics; this article creates no SQL files, controllers, or databases.

The key point is that inputs are controlled, while responses are still computed and serialized by **real producer code**.

## 11. Distinguishing proper MockMvc from real HTTP

MockMvc exercises the Spring MVC stack without traversing real networking and a live web server. Depending on the contract, stronger verification may be required:

| Execution mode | What is usually verified | What is not automatically guaranteed |
|---|---|---|
| MockMvc with `@SpringBootTest` | Mappings, controllers, converters, validation, context-loaded services/repositories | Sockets/networking, reverse proxies, TLS, or real container config |
| `@WebMvcTest` + mocked service | HTTP slice and controller with fake services | Mocked service/repository rules |
| `standaloneSetup` with real controller | Controller within configured unit/slice scope | Auto-configuration, filters, security, advice, etc. |
| HTTP test with server on random port | Running HTTP server + application stack | Stubbed external systems; production infra |
| E2E in an integration environment | Broader set of communication paths | Uncovered edge scenarios if test coverage is thin |

**Choose the mode to match the test goal.** If contracts depend on HTTP container behavior, auth filters, or error handling outside MVC, real HTTP integration tests may be necessary. If contracts verify body mappings and service logic, MockMvc with a real context offers fast, effective feedback.

Avoid dogmatic "everything must run for real" slogans: isolate external services deliberately for stable CI, **without hiding the layer responsible for producing contract behavior**.

## 12. Configuring Contract Verifier to point to the right base class

With Maven, the Contract Verifier plugin needs to know which test base to use. Illustrative config:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>CONTRACT_PLUGIN_VERSION</version>
    <extensions>true</extensions>
    <configuration>
        <baseClassForTests>
            com.example.inventory.ContractTestBase
        </baseClassForTests>
    </configuration>
</plugin>
~~~

`CONTRACT_PLUGIN_VERSION` is a placeholder; **replace it with a real version compatible with Spring Boot, the Spring Cloud Release Train, and Contract dependencies**. Do not run examples verbatim with the placeholder.

Producer `dependencies` typically include:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

With Gradle using the matching SCC plugin:

~~~groovy
contracts {
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

Ensure:

1. The plugin **actually executes** in the build lifecycle.
2. Generated tests extend or can use **the right base test**.
3. MockMvc/RestAssuredMockMvc or other adapters match the **generated test mode**.
4. Base tests from other contract groups do not accidentally swap beans/controllers.
5. Generated tests are **compiled and executed** by the test runner.
6. The plugin version does not drift from BOM-managed dependencies.

When projects have multiple contract groups, configure package/plugin base-class selection clearly so each generated test gets the right environment.

## 13. Anti-pattern: replacing the producer with its own stub

Stub Runner/WireMock is great for letting consumers develop independently of producers. However, substituting stubs for the producer endpoint during generated producer tests **defeats the purpose**.

Example of an untrustworthy verification loop:

~~~text
Contract:
GET /api/inventory/SKU-123 -> {"available":true}

Base test:
  starts WireMock with mappings from the same contract
  generated producer test sends request to WireMock
  WireMock returns {"available":true}

Result: PASS, even though real InventoryController was never invoked.
~~~

That merely **compares the contract against a copy of itself**. If the real producer renames `available` to `inStock`, the test still passes.

Proper separation:

- **Producer tests:** requests must hit **producer application code**.
- **Consumer tests:** **consumer client** requests hit **the producer's stub**.
- **E2E tests (when needed):** consumer client hits the real producer in a test environment.

Name CI jobs clearly so teams never confuse "producer verification" with "consumer stub tests."

## 14. Not just HTTP: base tests for message contracts

Spring Cloud Contract also covers messaging contracts. For instance, a producer emits an event on stock changes:

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

In producer tests, the base class can provide `triggerStockChanged()`. **It must invoke the real production path that builds the message**, such as an application service use case. Never let the test method **send a canned sample message straight to the test sink**, as that bypasses producer logic.

Conceptual counter-example:

~~~java
// WRONG for producer verification:
// The base test itself sends the exact payload the contract wants to verify.
public void triggerStockChanged() {
    testMessageSink.send(
        "inventory.events",
        "{\"eventType\":\"StockChanged\",\"sku\":\"SKU-123\",\"available\":true}"
    );
}
~~~

Instead, initialize the test context and invoke the **application entry point**:

~~~java
// Right approach: the production method constructs and emits the message.
// InventoryApplicationService is a real application bean.
@Autowired
InventoryApplicationService applicationService;

public void triggerStockChanged() {
    applicationService.changeStock("SKU-123", 12);
}
~~~

The snippet above illustrates wiring a test base to a **sample application service**; exact parameters/data seeding depend on your app. A message verifier/test binder must be configured to observe the producer's real output.

Messaging also has legitimate cut points: mocking external brokers, using test binders, or running test broker instances. What should not be faked is **the production code shaping payload, headers, and destination** promised by the contract.

## 15. Catching false greens: intentional mutation testing

A pragmatic sanity check is **breaking the real producer on an experiment branch** and observing generated tests.

### Experiment A — Rename a response field

1. Keep the contract expecting `available: true`.
2. Change the production response to return only `inStock` (drop `available`).
3. Re-run generated producer tests.
4. **Expected:** the test turns red because the body violates the contract.
5. Revert the code after the experiment.

If the test stays green, it likely **called a fake controller**, received a body from a mocked service, or never executed.

### Experiment B — Break a business rule

Change the service from:

~~~java
return new InventorySnapshot(sku, quantity > 0, quantity);
~~~

to:

~~~java
// Intentionally broken in an experiment branch, never keep in production.
return new InventorySnapshot(sku, quantity == 0, quantity);
~~~

With `SKU-123` having quantity 12, the contract requiring `available: true` must **fail**. If not, check whether the real service ran or was replaced by `@MockitoBean`.

### Experiment C — Remove the production endpoint

Temporarily remove or change `InventoryController`'s URL mapping. Properly scoped generated tests must report an unexpected response such as 404. If they still receive 200, a fake controller or different mapping is intercepting requests.

### Experiment D — Alter raw test data

Have the repository/test DB return quantity 0 while the contract still expects 12 and `available=true`. If tests stay green, check whether a mock is **returning a hardcoded response DTO** while ignoring underlying data.

**Mutation checks here test your test suite's defect-detection power**, not changes to merge. Run them on a separate branch and always revert before committing.

## 16. What evidence proves generated tests hit the real producer?

Having `@SpringBootTest` does not automatically guarantee every relevant bean is a production bean: Spring contexts can still be overridden by test configurations, `@Primary` beans, or mock annotations.

Collect concrete evidence:

| Verification point | How to check | Why it matters |
|---|---|---|
| Tests actually ran | Generated source + test report | Avoids false greens from 0 executed tests |
| Right test base | Generated class extends/declares expected base | Avoids inheriting another group's base |
| Right endpoint | Check request URL and Spring-mapped handler | Avoids fake controllers or wrong URLs |
| Production beans used | Inspect Spring context and overrides | Avoids services/controllers replaced by mocks |
| Business rules executed | Mutating service turns test red | Strong proof of test scope |
| Deterministic test data | Fixtures, seeding, isolation | Avoids order-dependent pass/fail |
| Real responses asserted | Inspect generated status/header/body assertions | Avoids overly loose matchers |
| Stubs match commit | Check artifact/version/mappings | Consumer tests validate candidate changes |

When multiple implementations of an interface exist, verify **which bean is active** in the test profile. A legitimate fake at the repository layer should not be confused with a mocked service skipping the behavior under test.

## 17. Sensible test-organization choices

| Scenario | Recommended base test | Complementary tests to maintain |
|---|---|---|
| Simple GET API, controller + service with no external deps | `@SpringBootTest` + MockMvc, real code | Unit tests for edge cases |
| API reading database where contracts cover mapping/persistence | Real context + test database/fixtures | Migration and repository integration tests |
| API calling a payment partner | Real controller/service; fake/mock outbound HTTP gateway | Gateway contract/integration tests, timeout handling |
| API protecting only controller HTTP mapping | MVC slice/standalone with real controller, scope documented | Separate service tests for business rules |
| API with critical auth/filters | Full application context and matching security filters | Security/integration tests |
| API depending on real container/headers | HTTP test with real booted server | E2E if needed |
| Producer emitting messages | Invoke production use case; use test broker or test binder | Consumer handler tests and message schema tests |

**No single mode replaces all others.** Spring Cloud Contract protects **behavior that is both specified and executed**. If critical application logic sits behind a mock, add matching tests elsewhere or lower the cut point.

## 18. Common mistakes and fixes

| Symptom | Common cause | Fix |
|---|---|---|
| Producer renames field yet contract tests stay green | Base test returns a fake response | Ensure generated requests invoke the real controller |
| Service changes do not turn tests red | `@MockitoBean`/mock service returns sample DTOs | Keep service real, mock lower deps, or add service tests |
| Tests miss filters/security/error handlers | Used `standaloneSetup` or overly narrow slice | Use an appropriate Spring context or add integration tests |
| `404` despite controller existing | Wrong application context, URL mapping, or base setup | Check bean scanning, paths, and generated requests |
| `200` from the wrong controller | Fake controller shares mapping or base overrides bean | Inspect actual handler mappings |
| Generated tests never run | Wrong plugin/lifecycle/source set | Check generated sources and executed test counts |
| Tests depend on a real database | Unisolated data and environment | Use test DBs/fixtures with proper cleanup/transactions |
| Flakiness from time/randomness | Uncontrolled dynamic data or wrong matchers | Fixed clock/seeds and semantically accurate matchers |
| Mocks accurate yet business rules untested | Cut point placed too high | Document scope, add service tests, or lower the cut point |
| Stub Runner green while producer is broken | Consumer tests stubs, not producer implementation | Enable separate producer generated contract tests |
| Consumer pipeline still tests stale stubs | Dynamic version/cache or unchanged artifact | Pin candidate stubs and verify mappings |
| Tests go red on code change and team edits contract immediately | Breaking change not evaluated | Test older consumers and plan migrations |

## 19. Integrating verification into CI/CD

~~~mermaid
flowchart TD
    A["PR changes producer, contract, or test base"] --> B["Generate and compile contract tests"]
    B --> C["Run generated tests against real producer"]
    C --> D{"Tests exist and all pass?"}
    D -- "No" --> X["Block PR / investigate"]
    D -- "Yes" --> E["Package stubs from same commit"]
    E --> F["Consumer CI uses Stub Runner with exact artifact"]
    F --> G{"Consumer tests pass?"}
    G -- "No" --> X
    G -- "Yes" --> H["Proceed to release gates"]
~~~

Reference commands in an SCC-configured project:

~~~bash
# Maven producer
./mvnw clean verify

# Gradle producer
./gradlew clean test
~~~

Adjust commands according to your plugin, tasks, test mode, and project layout. On Windows use the corresponding wrapper. Never treat exit code 0 as contract-test proof if zero generated tests ran.

Recommended CI gates:

1. **Input contracts present**, generated tests produced and executed (when the producer module owns contracts).
2. **No fake controllers/mocked business services** returning full contract bodies without documented scope justification.
3. **Run tests in the right mode and Spring context**; inspect real producer responses.
4. **Evaluate breaking changes** against active contracts and consumers rather than blindly updating contracts to match new code.
5. **Package candidate stubs** from the same verified producer commit.
6. Consumers run **real clients** through Stub Runner with exact versions/classifiers.
7. Archive test reports, stub coordinates, commit SHAs, and verification evidence for diagnostics.

You do not need mutation runs on every commit, but run one or two **periodic mutation checks** when refactoring base tests, switching test modes, or updating CI workflows. If the suite fails to catch an intentional producer bug, tighten the test boundary.

## 20. Hands-on lab: from a fake base test to a trustworthy base test

### Part A — Establish a baseline

1. Create Inventory Service with `InventoryController` and `InventoryService` as in section 4.
2. Write a Groovy or YAML contract protecting `GET /api/inventory/SKU-123`.
3. Configure the SCC plugin and a base test using a real Spring context.
4. Run generated producer tests and inspect generated sources/test reports to confirm execution.
5. Run consumer tests against candidate stubs, verifying Checkout reads `available`.

**Expected outcome:** both producer and consumer tests pass, and you know exactly which code executes on each side.

### Part B — Introduce an intentional false green

1. On an experiment branch, switch the base test to `standaloneSetup(new FakeInventoryController())` as in section 7.
2. Break `available` in the production service or remove the real endpoint mapping.
3. Re-run generated tests.
4. Observe if tests stay green and identify exactly why.
5. Restore the base test so tests target the real application context.

**Expected outcome:** understand why a false green **does not prove producer compatibility**.

### Part C — Cut dependencies at the right boundary

1. Replace the service's Map with a testable repository port.
2. Prepare a test DB or fake repository returning a record with quantity 12.
3. Keep the **production controller/service** real.
4. Intentionally change `quantity > 0` to `quantity == 0` and verify generated tests turn red.
5. Restore the formula and re-run tests.

**Expected outcome:** deterministic data is preserved while protecting response-building logic.

### Part D — Lock down consumer/CI gates

1. Package stubs from the producer after generated tests pass.
2. Point Checkout's Stub Runner to the exact candidate stub.
3. Try renaming response field `available` to `inStock`; evaluate impact on older consumers.
4. Configure CI gates to block builds when producer verification or consumer compatibility fails.
5. Archive test reports and artifact versions/commits.

**Lab deliverables:** cut-point diagram, contract files, before/after base tests, generated test reports, mutation logs, stub coordinates, and consumer test results.

## 21. Base test review checklist

- [ ] Contracts clearly state producer behavior to protect, not just status codes or overly loose fields.
- [ ] Generated tests are actually generated, compiled, and executed.
- [ ] Base test initializes HTTP/message adapters that **invoke the production implementation**.
- [ ] No fake controller replaces the endpoint under test.
- [ ] If a business service is mocked, that narrow scope is documented with complementary tests.
- [ ] Repositories/adapters are faked only when skipped layers **lie outside** the commitment under test.
- [ ] Test data is deterministic with proper cleanup/isolation.
- [ ] Handlers/beans in the test context are verified to be the real ones.
- [ ] An intentional mutation breaking critical behavior turns generated tests **red**.
- [ ] MockMvc/RestAssuredMockMvc/WebTestClient/HTTP mode aligns between plugin and base class.
- [ ] Stub Runner/WireMock is never substituted for the producer during producer verification.
- [ ] Messaging contracts trigger production use cases instead of sending sample payloads straight from the base test.
- [ ] Producer tests pass before generating/handing candidate stubs to consumers.
- [ ] Consumer tests run real clients/handlers against the exact stub version.
- [ ] CI never treats "green build with 0 tests executed" as sufficient evidence.
- [ ] Potentially breaking changes are evaluated against active consumers.

## 22. Self-check questions

**1. Why does using a fake controller in `standaloneSetup` create a false green?**

Because generated tests only check responses returned by the fake controller, bypassing the production endpoint and service. Breaking changes in real code may leave tests unaffected.

**2. Does `@SpringBootTest` guarantee every piece of producer logic is verified?**

No. Context beans can still be overridden by `@MockitoBean`, `@Primary`, or test configurations. You must inspect the cut points and which behavior actually executes.

**3. Is mocking a repository allowed?**

Yes, when contracts protect controller/service behavior and the repository only provides controlled raw data. If contracts also protect queries/persistence, use a test database or matching integration tests.

**4. When is `@WebMvcTest` useful?**

When testing an **MVC slice**—routing, binding, and controllers with mocked dependencies. Never use those results as proof that all producer services/business logic were verified.

**5. What is the fastest way to prove generated tests exercise the real producer?**

On an experiment branch, intentionally break production code protected by the contract. If generated tests turn red, that directly proves tests catch bugs in that scope.

**6. Can Stub Runner replace producer tests?**

No. Stub Runner helps consumers test against sample behavior from contracts. It does not prove the real producer implementation satisfies the contract.

## 23. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): producer/consumer model, Contract Verifier, and Stub Runner.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL and test generation.
- [Spring Framework – Testing Spring MVC](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): MockMvc and web-layer test scope.
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): SpringBootTest, test slices, and test context setup.
- [Mockito](https://site.mockito.org/): mocking/stubbing dependencies where appropriate for the verification scope.

**Version note:** Mock-bean annotations, test modes, RestAssuredMockMvc initialization APIs, and plugin configuration can vary across Spring Boot/Spring Cloud Contract lines. Check your active version's documentation and inspect generated sources and test reports before treating examples as complete project setup.

---

**Key takeaway:** A Spring Cloud Contract base test must **route generated tests to the producer code being protected**, never **return expected contract responses itself**. Mocks and fakes are valid isolation tools when placed at **the right cut point**; fake controllers or mocking core logic produces false greens. The strongest proof is **breaking the real producer → generated tests turn red**, followed by verifying consumers against **candidate stubs** in CI.
