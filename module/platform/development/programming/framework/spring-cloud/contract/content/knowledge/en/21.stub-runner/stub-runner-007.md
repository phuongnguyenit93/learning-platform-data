# Starting Multiple Producer Stubs in the Same Test

## 1. When a consumer needs to call multiple producers

In a microservices system, one consumer frequently depends on multiple APIs. For example, **Checkout Service** needs to ask **Inventory Service** about stock availability and **Pricing Service** about pricing before allowing a customer to place an order. To test Checkout conventionally, the development team might have to start both producers along with databases, network setups, and related resources. That makes feedback loops slow, hard to reproduce, and coupled to the development schedules of two teams.

**Spring Cloud Contract (SCC)** allows producers and consumers to commit to HTTP or messaging behavior using **Groovy/YAML DSL**. From contracts, Contract Verifier generates producer-side tests and creates stubs for the consumer to run via **Stub Runner**. Within the same test, Stub Runner can load **multiple stub artifacts** from different producers, start HTTP stub servers, and let consumer code call them instead of real services.

This lesson belongs to the **Stub Runner** chapter, focusing on **starting multiple producer stubs in the same test**: from artifact identification and port management to client wiring, error handling, compatibility guarantees, and CI setup.

### Learning outcomes

After this lesson, you will be able to:

1. Describe the flow of one consumer calling two producers and know what each stub simulates.
2. Prepare independent stubs JARs published by each producer.
3. Configure `@AutoConfigureStubRunner` with **multiple `ids`** in the same Spring Boot test.
4. Distinguish fixed ports from dynamic ports; look up the right port for each producer.
5. Bind Stub Runner URLs to the **consumer's real HTTP clients**, instead of mocking business results.
6. Test happy paths and individual producer errors, distinguishing business 404 from unmatched 404.
7. Diagnose missing artifacts, wrong versions, stale caches, overlapping mappings, and port collisions.
8. Integrate multi-producer stub tests into CI with exact candidate versions.

## 2. Running scenario: Checkout, Inventory, and Pricing

Checkout needs to display a preview for **2 units of SKU-123**. In production, the application executes two calls:

~~~mermaid
flowchart LR
    C["Checkout Service<br/>Consumer"] -->|"GET /api/inventory/SKU-123"| I["Inventory Service<br/>Producer A"]
    C -->|"GET /api/prices/SKU-123"| P["Pricing Service<br/>Producer B"]
    I -->|"available, quantity"| C
    P -->|"unitPriceVnd"| C
~~~

Inventory API:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","available":true,"quantity":12}
~~~

Pricing API:

~~~http
GET /api/prices/SKU-123 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","unitPriceVnd":150000}
~~~

Checkout merges the two responses:

~~~json
{
  "sku": "SKU-123",
  "canCheckout": true,
  "subtotalVnd": 300000
}
~~~

These numbers are **illustrative** data. Calculating subtotal = 2 × 150,000 belongs to **Checkout's logic**, not Stub Runner's responsibility.

In the consumer test, replace the two real services with two stub servers:

~~~mermaid
flowchart LR
    C["Real Checkout code"] -->|"Inventory HTTP client"| WI["WireMock Inventory<br/>port A"]
    C -->|"Pricing HTTP client"| WP["WireMock Pricing<br/>port B"]
    R["Stub Runner"] --> WI
    R --> WP
    A["Inventory stubs JAR"] --> R
    B["Pricing stubs JAR"] --> R
~~~

This is still a **Checkout** test. One test may need both stubs because a single real consumer operation must interact with two APIs.

## 3. Distinguishing producer verification from consumer stub tests

| Test type | What runs? | What does it prove? |
|---|---|---|
| **Inventory producer verification** | Generated tests on real Inventory code | Inventory meets the stock contract |
| **Pricing producer verification** | Generated tests on real Pricing code | Pricing meets the pricing contract |
| **Checkout consumer contract test** | Real Checkout code + two HTTP stubs | Checkout sends requests and handles both producers' responses per contract |
| **Integration/E2E test** | Checkout + real producers and appropriate infrastructure | Real deployed interaction behavior beyond stub simulation |

**A stub is not the producer implementation.** If Inventory changes code and returns the wrong `available` value, an Inventory stub can still return the contract's sample JSON. Thus, never substitute consumer stub tests for generated producer tests.

Conversely, both producer tests passing does not prove Checkout handles the combination of stock and pricing properly. That is precisely the added value of a multi-stub consumer test.

## 4. Each producer owns its own contracts and artifact

Source layout:

~~~text
inventory-service/
  src/test/resources/contracts/inventory/get-stock.groovy
  -> inventory-service-1.3.0-rc1-stubs.jar

pricing-service/
  src/test/resources/contracts/prices/get-price.yml
  -> pricing-service-2.1.0-rc2-stubs.jar

checkout-service/
  src/test/java/.../CheckoutMultiProducerContractTest.java
~~~

Inventory contract in Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout checks stock for SKU-123'
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

Pricing contract in YAML DSL:

~~~yaml
description: Checkout checks price for SKU-123
name: get_price_sku123

request:
  method: GET
  url: /api/prices/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    unitPriceVnd: 150000
~~~

These are **two contracts belonging to two producers**, not two versions of one contract. Each producer generates tests, verifies its implementation, and packages WireMock mappings and related resources into its own stubs artifact.

One artifact can contain many endpoints and many response scenarios; **you do not need one artifact or one stub server per endpoint**.

## 5. Coordinates identifying each stub

Stub Runner typically accepts IDs in the form:

~~~text
groupId:artifactId:version:classifier:port
~~~

Example:

~~~text
com.example:inventory-service:1.3.0-rc1:stubs:18081
com.example:pricing-service:2.1.0-rc2:stubs:18082
~~~

| Field | Meaning | Example |
|---|---|---|
| `groupId` | Producer artifact namespace | `com.example` |
| `artifactId` | Producer name | `inventory-service` |
| `version` | Candidate or pinned stable build | `1.3.0-rc1` |
| `classifier` | Distinguishes stubs JAR from application JAR | `stubs` |
| `port` | Requested HTTP port for the stub | `18081` |

If the **port part is omitted**, Stub Runner can allocate a dynamic port per configuration. If using a dynamic version (such as `+` in supported versions), outcomes may depend on repository/cache state and become hard to trace. For CI verifying a PR, use the **exact candidate version**.

**Common mistake:** the stub port is a port on the **test/CI machine**, not the production port of Inventory or Pricing. When running multiple stubs, each HTTP server needs a distinguishable address/port.

## 6. Preparing the stubs JARs before running Checkout

For `LOCAL` mode, Stub Runner needs to find **both** artifacts in the local Maven repository or configured local source. Hence, each producer must complete:

1. Read Groovy/YAML contracts.
2. Generate producer tests.
3. Run tests against real producer code.
4. Generate WireMock mappings and related response files.
5. Package the stubs JAR with the right group/artifact/version/classifier.
6. Install/publish where consumer tests will retrieve it.

In a Maven producer configured with SCC, reference command:

~~~bash
# Run separately inside the Inventory and Pricing projects.
./mvnw clean install
~~~

This command is only meaningful if each producer's plugin/lifecycle is properly configured. With Gradle, check the corresponding tasks:

~~~bash
./gradlew tasks --all
./gradlew clean build
~~~

Gradle `build` **does not prove by default** that the stubs artifact was published to local Maven or a remote repository. Check the project's publication/task configuration and output artifacts.

Before moving to Checkout tests, confirm:

- `inventory-service-1.3.0-rc1-stubs.jar` exists.
- `pricing-service-2.1.0-rc2-stubs.jar` exists.
- Each JAR contains the required mappings and body files when referenced.
- The JAR version is one **verified by producer tests**.
- A regular application JAR is not used in place of the `stubs`-classifier artifact.

## 7. Starting two producer stubs with @AutoConfigureStubRunner

Spring Boot integration test configuration in Checkout:

~~~java
package com.example.checkout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "clients.inventory.base-url=http://localhost:18081",
    "clients.pricing.base-url=http://localhost:18082"
})
@AutoConfigureStubRunner(
    ids = {
        "com.example:inventory-service:1.3.0-rc1:stubs:18081",
        "com.example:pricing-service:2.1.0-rc2:stubs:18082"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutMultiProducerContractTest {

    @Autowired
    CheckoutPreviewService checkout;

    @Test
    void composesTwoProducerResponses() {
        CheckoutPreview result = checkout.preview("SKU-123", 2);

        assertThat(result.sku()).isEqualTo("SKU-123");
        assertThat(result.canCheckout()).isTrue();
        assertThat(result.subtotalVnd()).isEqualTo(300_000L);
    }
}
~~~

Here:

1. `ids` is an **array of two distinct coordinates**; Stub Runner must start stubs for both Inventory and Pricing.
2. Each stub is instructed to use a **separate port**.
3. `@SpringBootTest(properties=...)` supplies both base URLs as Spring creates the Checkout context.
4. The test `@Autowired`s **Checkout's service** so it invokes the real HTTP clients.
5. `LOCAL` requires stub artifacts in the local source; separate-repository CI can use `REMOTE`.

Ports 18081/18082 are illustrative. If CI runs multiple suites in parallel, consider **dynamic ports** to reduce collisions.

## 8. Real Checkout code must call both stub servers

For the test to be meaningful, Checkout must use the same HTTP client code intended to run in production. Example `CheckoutPreviewService` using `RestClient`:

~~~java
package com.example.checkout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CheckoutPreviewService {

    private final RestClient inventory;
    private final RestClient pricing;

    public CheckoutPreviewService(
            @Value("${clients.inventory.base-url}") String inventoryUrl,
            @Value("${clients.pricing.base-url}") String pricingUrl) {
        this.inventory = RestClient.create(inventoryUrl);
        this.pricing = RestClient.create(pricingUrl);
    }

    public CheckoutPreview preview(String sku, int amount) {
        InventoryStock stock = inventory.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryStock.class);

        PriceInfo price = pricing.get()
                .uri("/api/prices/{sku}", sku)
                .retrieve()
                .body(PriceInfo.class);

        if (stock == null || price == null) {
            throw new IllegalStateException("Producer response is empty");
        }
        if (!sku.equals(stock.sku()) || !sku.equals(price.sku())) {
            throw new IllegalStateException("SKU mismatch");
        }

        boolean allowed = stock.available()
                && stock.quantity() >= amount;

        long subtotal = Math.multiplyExact(
                price.unitPriceVnd(), amount);

        return new CheckoutPreview(sku, allowed, subtotal);
    }

    public record InventoryStock(
            String sku, boolean available, int quantity) {}

    public record PriceInfo(String sku, long unitPriceVnd) {}
}
~~~

And the result type:

~~~java
package com.example.checkout;

public record CheckoutPreview(
        String sku, boolean canCheckout, long subtotalVnd) {
}
~~~

**Core point:** `preview` actually calls **two distinct HTTP servers**, deserializes JSON, and combines the results. Replacing `InventoryStock`/`PriceInfo` with Mockito in tests would stop verifying URLs, headers, serialization, and consumer response handling protected by the contract.

The example omits validation for `amount <= 0`, timeouts, security, retries, 4xx errors, and currency rules to stay focused on multi-stub behavior. A real system needs corresponding additional checks.

## 9. Fixed ports: easy to configure, yet risky

With fixed ports, Spring tests can configure client beans before invoking them:

~~~text
clients.inventory.base-url = http://localhost:18081
clients.pricing.base-url   = http://localhost:18082
~~~

Pros: simple configuration, easy to follow results, and suited for learning.

Cons:

- The port might already be used by another application/test.
- Two CI suites running in parallel might both try to bind port 18081.
- A client might copy the wrong URL and hit the other server.
- If a prior test left a WireMock server on the port, a new suite might hit the wrong server.
- Production code might not read test properties and continue using discovery or hardcoded URLs.

Therefore, fixed ports suit **isolated** environments, whereas dynamic ports usually work better when multiple test jobs share a host.

## 10. Dynamic ports: do not guess by order

When omitting the `port` part in `ids`, Stub Runner can allocate available ports automatically:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = {
        "com.example:inventory-service:1.3.0-rc1:stubs",
        "com.example:pricing-service:2.1.0-rc2:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutDynamicPortsTest {

    @StubRunnerPort("com.example:inventory-service")
    int inventoryPort;

    @StubRunnerPort("com.example:pricing-service")
    int pricingPort;

    @Test
    void hasTwoDistinctStubPorts() {
        assertThat(inventoryPort).isPositive();
        assertThat(pricingPort).isPositive();
        assertThat(inventoryPort).isNotEqualTo(pricingPort);
    }
}
~~~

`@StubRunnerPort` lets the test retrieve a port by **producer identifier**, rather than guessing "the first artifact gets the lowest port." Exact annotation name, identifier syntax, and injection behavior must be verified for your specific SCC version.

### Passing dynamic ports to HTTP clients

Obtaining the port in a test field **does not automatically change** the URL of a previously constructed Checkout bean. If consumer clients receive base URLs at Spring context startup, use a configuration mechanism aligned with that lifecycle, such as:

- Using fixed ports in `@SpringBootTest(properties=...)` for a simple suite.
- Using Stub Runner's registry/lookup and a factory to instantiate clients at the right moment.
- Using dynamic URL configuration hooks in Spring tests/plugins supported by your running version.

Example creating clients during test setup after ports are known:

~~~java
String inventoryUrl = "http://localhost:" + inventoryPort;
String pricingUrl = "http://localhost:" + pricingPort;

// Pass URLs into the application's real client constructors
// or configure beans through a test-specific factory.
~~~

This is not asking you to build brand-new HTTP clients in place of Checkout's code: the goal remains verifying **real client implementations** against the actual URLs of both stubs.

## 11. Configuring from test properties instead of annotations

Another way to organize this is letting tests read stub IDs from configuration:

~~~yaml
stubrunner:
  ids:
    - com.example:inventory-service:1.3.0-rc1:stubs:18081
    - com.example:pricing-service:2.1.0-rc2:stubs:18082
  stubs-mode: local

clients:
  inventory:
    base-url: http://localhost:18081
  pricing:
    base-url: http://localhost:18082
~~~

This YAML snippet illustrates the structure; verify property binding and the Stub Runner activation mechanism for your project version. Never place this configuration in production profiles. You can use `application-contract-test.yml` or equivalent in test sources.

If you use **both annotations and properties** with two differing lists, configuration precedence issues or unexpected artifact downloads can occur. Choose one primary configuration source and verify startup logs.

## 12. Each producer can serve multiple contract scenarios

An Inventory stub JAR can contain:

~~~text
GET /api/inventory/SKU-123 -> 200, in stock
GET /api/inventory/SKU-456 -> 200, out of stock
GET /api/inventory/SKU-404 -> 404, does not exist
~~~

At the same time, a Pricing stub JAR can contain:

~~~text
GET /api/prices/SKU-123 -> 200, priced
GET /api/prices/SKU-404 -> 404, not priced yet
POST /api/prices/quote -> 200 or 400 depending on request
~~~

Stub Runner loads all mappings of an artifact into its corresponding server. **One server per producer stub set** can serve multiple endpoints.

However, when one artifact contains multiple mappings with the **same method/path**, request conditions must be strict enough. If mapping A also matches mapping B's request, WireMock can return the wrong scenario. Inspect `headers`, `queryParameters`, `bodyPatterns`, and `priority` in the actual mappings and run negative tests.

## 13. Verifying each stub server before testing the combined result

With fixed ports, two independent requests can verify wiring:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:18081/api/inventory/SKU-123

curl -i \
  -H "Accept: application/json" \
  http://localhost:18082/api/prices/SKU-123
~~~

These commands only work while the test/Stub Runner servers are actually listening. In the real test, **Checkout service must still invoke both real clients** rather than relying on curl output.

| Request | Expected response |
|---|---|
| Inventory port + inventory path | 200, `quantity:12` |
| Pricing port + price path | 200, `unitPriceVnd:150000` |
| Inventory port + price path | Does not unintentionally return a valid business price |
| Pricing port + inventory path | Does not unintentionally return valid inventory |

The two negative checks catch **two clients pointing to swapped ports** or mappings belonging to the wrong producer. If an artifact intentionally serves multiple paths, evaluate against actual contracts.

## 14. Business 404 differs from WireMock unmatched 404

An Inventory contract might explicitly commit to:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"SKU_NOT_FOUND","sku":"SKU-404"}
~~~

If the client sends the wrong URL or omits a required header, WireMock can also return 404 because **no mapping matched**. Both situations share the same status code yet differ in semantics.

To test properly, the consumer must assert **error code/body/schema**, not just status code. When a request is unmatched:

1. Check Stub Runner logs for the **exact producer server**.
2. Inspect the URL, method, query, headers, and body sent by the real client.
3. Read the mapping inside the stubs JAR.
4. Use WireMock's request journal/near misses if supported by your version.
5. Confirm artifacts and ports were not swapped between Inventory and Pricing.

A 404 returned from the Pricing port should never be mistaken for Inventory failing to find a SKU.

## 15. Do two producers sharing a URL path conflict?

Suppose both Inventory and Pricing expose:

~~~text
GET /api/status
~~~

If the two stub servers listen on **two separate ports**, mappings can coexist completely independently:

~~~text
localhost:18081/api/status -> Inventory status
localhost:18082/api/status -> Pricing status
~~~

There is no conflict merely because routes look identical. Conflicts arise when:

- Two servers attempt to bind the same address/port.
- One producer's client is misconfigured to call the other producer's port.
- One server receives unintended mappings.
- Multiple mappings on the **same server** match one request due to overly broad predicates.

Do not rely on filename ordering or `ids` array ordering to solve those issues; inspect actual mappings and producer identifiers.

## 16. Each producer's errors must be tested individually

A single happy path of Inventory=12, Pricing=150000 leaves many critical cases uncovered:

| Inventory | Pricing | Decision Checkout must make |
|---|---|---|
| In stock | Priced | Allow checkout, calculate subtotal |
| Out of stock | Priced | Disallow checkout |
| SKU does not exist | Priced | Report invalid SKU |
| In stock | Not priced yet | Disallow checkout, report price unavailable |
| Inventory 503 | Priced | Retry/fallback or error per policy |
| In stock | Pricing 503 | Pricing error per convention |
| In stock | Pricing timeout | Trigger client timeout/retry, do not return fake price |

To simulate error responses that are part of the API, **each producer needs corresponding contracts**. Stub Runner does not invent error cases just from knowing an API exists. To simulate network latency or connection faults, use a dedicated **resilience test** (WireMock response delay/fault or a test server), since standard contract stubs respond immediately.

Consumer tests must confirm **errors are handled properly**: for example, Pricing 404 must never silently become price 0, and Inventory 503 must never be treated as "in stock."

## 17. Two independent stubs do not share business state automatically

Stub Runner does not turn two stubs into a live workflow. Each server returns data strictly from its own contracts/mappings.

For instance, if Checkout calls Inventory returning `SKU-123` while Pricing returns `SKU-456`, Stub Runner **does not reconcile the data automatically**. Checkout itself must check consistency across responses. That is why the sample consumer code asserts both `stock.sku` and `price.sku` equal the requested SKU.

For complex systems:

- Contract samples should remain consistent across related fields.
- Consumer integration tests verify how data is combined.
- Stateful scenarios should only be used when WireMock/SCC versions and test requirements truly call for them, not assumed by default.
- E2E/integration tests with real producers remain necessary when verifying transactions, eventual consistency, authorization, or multi-service logic.

**The value of multi-stub tests is verifying consumer orchestration**, not simulating every real-world effect of a distributed system.

## 18. Port lookup by group and artifact, not by index

With multiple stubs, the following assumption is unsafe:

~~~text
ids[0] -> lowest port
ids[1] -> next port
~~~

Instead, use full identifiers:

~~~java
@StubRunnerPort("com.example:inventory-service")
int inventoryPort;

@StubRunnerPort("com.example:pricing-service")
int pricingPort;
~~~

Some Stub Runner versions also provide `StubFinder` to look up running stub addresses. When the same `artifactId` exists under two different `groupId`s, you must use the full **group + artifact**.

If a single suite needs two **versions of the exact same artifact**, group/artifact lookup becomes ambiguous; verify what your Stub Runner version supports or split into two test suites with pinned versions.

## 19. LOCAL and REMOTE for multiple producer artifacts

| Mode | Stub source | When appropriate | What to verify |
|---|---|---|---|
| **LOCAL** | Local Maven repository or configured local source | Dev/testing on one machine after installing stubs | Are **both** artifacts present? |
| **REMOTE** | Configured artifact repository | Multi-repo CI across teams | Access permissions, exact versions, caches, checksums/mappings |

With REMOTE, configure repository URLs and credentials per your SCC version's guidance. Never hardcode tokens in annotations or YAML sources. One artifact downloading successfully does not prove both are present: startup logs must show **each resolved coordinate** and its server/mappings.

If the goal is testing a candidate build of Inventory while the repository lacks the candidate JAR, the pipeline must fail; never silently fall back to stable Inventory and treat the PR as verified.

## 20. Candidate versions of each producer are independent

Both producers do not always change in the same PR. An example matrix:

| Change under test | Inventory stub | Pricing stub |
|---|---|---|
| Inventory PR | **Inventory candidate** | Pinned stable Pricing |
| Pricing PR | Pinned stable Inventory | **Pricing candidate** |
| Checkout PR | Declared supported producer versions | Declared supported producer versions |
| Simultaneous change in both producers | **Inventory candidate** | **Pricing candidate** |

Each CI run must record **both exact coordinates** and related commits. Using `+`/latest versions can cause jobs to grab older or newer artifacts uncontrollably.

A common risk:

~~~text
Inventory candidate renames response "available" -> "inStock".
Pricing does not change.
Old Checkout still reads "available".

If Checkout test loads old Inventory stub: false PASS.
If Checkout test loads Inventory candidate stub: may FAIL,
exposing incompatible consumer.
~~~

The new Inventory producer may pass on its own if both code and contract changed together. **Consumer tests with candidate stubs** are a necessary additional gate before releasing breaking changes.

## 21. Parallel execution and port collisions

When two test suites on the same host both declare:

~~~text
Suite A: Inventory=18081, Pricing=18082
Suite B: Inventory=18081, Pricing=18082
~~~

one suite may fail to bind ports, or interact with a server left behind by another suite. Mitigation:

1. Prefer dynamic ports when CI runs multiple suites in parallel.
2. Inject allocated ports into clients using a lifecycle-appropriate mechanism.
3. Isolate test containers/jobs if fixed ports are required.
4. Avoid sharing singleton/static base URLs across test classes with different stub sets.
5. Ensure the test lifecycle stops servers and cleans state after each suite.
6. Never use `Thread.sleep` to "wait for stubs to start"; rely on test framework lifecycles and proper readiness checks.

Dynamic ports eliminate bind-collision risks, yet won't help if two clients are still accidentally configured with the same URL.

## 22. Common issues and diagnostic paths

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Inventory runs but Pricing won't start | Pricing stubs JAR not installed/published or wrong ID | Check artifact coordinates, repository, and logs |
| Pricing returns 404 | Pricing path, header, or mapping mismatch | Compare raw request with loaded mappings |
| Both clients return Inventory JSON | Both base URLs point to Inventory port | Check properties, bean wiring, logs |
| One stub reports bind error | Port occupied or duplicated | Dynamic ports or isolate suites |
| Disabling Pricing stub still leaves test green | Checkout client is mocked or logic never calls Pricing | Inspect consumer code and add negative test |
| Data changed yet response stays stale | Old artifact version or cache | Pin exact coordinates, inspect JAR and mappings |
| Producer build green yet stub JAR empty | Contract discovery or packaging skipped | Check generated tests and mapping count |
| Passes locally, fails in CI | CI missing one artifact in local repo | Configure REMOTE/full install, verify mode |
| 404 mistaken for SKU_NOT_FOUND | WireMock unmatched request | Assert body code, inspect request journal |
| Test accidentally calls production producer | HTTP client not using test URL | Check target host, service discovery, bean setup |
| One scenario returns wrong status | Overlapping mappings on same server | Check predicates/priority and negative tests |
| Consumer passes yet real producer fails | Generated producer tests never ran | Add producer verification for each producer |
| Parallel CI flaky | Port conflict, shared test state | Dynamic ports, cleanup, isolation |

Effective investigation order: **Stub Runner startup logs → coordinates and port of each producer → mappings inside each artifact → raw requests from each client → responses → Checkout assertions → generated producer test reports**.

## 23. Separating HTTP stubs from messaging and resilience tests

A producer can have both HTTP and message contracts. Starting two HTTP WireMock servers should never be confused with starting a Kafka broker or RabbitMQ exchange. For message contracts, Stub Runner provides API/message-trigger support per compatible test infrastructure and version; consumer handlers must be tested at the messaging layer.

Similarly, Stub Runner typically serves fast sample responses and does not prove Checkout handles:

- Delayed HTTP responses;
- Connection timeouts;
- Retries and backoff;
- Reactive WebClient cancellation;
- Circuit breakers or fallbacks.

Those requirements need separate **resilience tests**, such as WireMock response delays/faults in a test environment. Never hand-edit candidate stubs JARs to inject delays and treat them as official producer artifacts.

## 24. Designing CI to verify multiple producers

~~~mermaid
flowchart TD
    A["Inventory candidate build"] --> B["Inventory producer contract tests"]
    C["Pricing candidate/stable build"] --> D["Pricing producer contract tests"]
    B --> E["Inventory stubs JAR"]
    D --> F["Pricing stubs JAR"]
    E --> G["Checkout consumer verification"]
    F --> G
    G --> H["Stub Runner downloads both"]
    H --> I["Real Checkout clients call both stubs"]
    I --> J{"Compatibility tests pass?"}
    J -- "No" --> X["BLOCK + analyze breaking change"]
    J -- "Yes" --> K["Proceed to integration/release gates"]
~~~

The pipeline should verify:

1. **Producer verification:** generated tests for candidate producers are generated and actually run.
2. **Packaging:** each stubs JAR contains required mappings and is non-empty.
3. **Publication:** both artifacts carry distinct version/commit metadata resolvable by the Checkout job.
4. **Startup:** Stub Runner loads exact coordinates and starts two servers on distinct addresses.
5. **Wiring:** each real Checkout HTTP client points to its matching producer stub.
6. **Assertions:** tests verify combined outcomes and critical error cases.
7. **Provenance:** archive logs/test reports, group/artifact/version/classifier, and commit SHAs.
8. **Release gate:** do not promote when older consumers break on new contracts without a migration plan.

Never treat `BUILD SUCCESS` as evidence when generated tests didn't run, stub artifacts lack mappings, or Checkout still pulls stubs from an earlier commit.

## 25. Practice A — Starting two producer stubs

**Goal:** Checkout preview works without running real Inventory/Pricing services.

1. Write Inventory and Pricing contracts following Section 4.
2. Have each producer generate tests, run producer verification, and build its stubs JAR.
3. Install into the local Maven repository or publish test artifacts.
4. Add `@AutoConfigureStubRunner(ids={...})` with both coordinates and distinct ports.
5. Configure `CheckoutPreviewService` with both base URLs.
6. Call `preview("SKU-123", 2)`.
7. Assert `canCheckout=true` and `subtotalVnd=300000`.
8. Check Stub Runner logs to confirm **both stubs** were loaded.

**Evidence:** each producer's contract, stubs coordinates, port logs, consumer test source/report.

## 26. Practice B — Catching wrong producer and unmatched requests

1. On a test branch, point `PricingClient` to the Inventory port.
2. Run the test: it must fail because the Pricing endpoint is absent or returns the wrong response.
3. Restore the port; intentionally alter `Accept` or URL in the client if constrained by contract.
4. Inspect unmatched requests on the corresponding WireMock server.
5. Add a business 404 for SKU-404 and assert the body `code` to distinguish it from unmatched 404.
6. Try omitting ports in `ids` and retrieve `@StubRunnerPort` per producer.
7. If running in parallel, verify zero port collisions.

**Evidence:** raw HTTP requests, mappings, near misses, and negative test results.

## 27. Practice C — Testing a breaking change in one producer

Suppose Inventory renames field `available` to `inStock`, while Pricing remains unchanged.

1. Keep the old Inventory contract while changing code: generated producer tests must fail if protecting that field.
2. Once new behavior is agreed upon, update the contract; producer tests can pass.
3. Build an Inventory **candidate stubs JAR** for the new commit.
4. Run existing Checkout against **Inventory candidate + Pricing stable**.
5. Observe Checkout deserialization/logic/assertion failures when `available` disappears.
6. Plan compatibility: temporarily keep the old field alongside the new field, or version the API when needed.
7. Rerun consumer tests with a compatible client, recording both artifact coordinates.

**Evidence:** before/after producer and consumer test reports, contract diff, artifact versions, migration decision.

## 28. Review checklist

- [ ] Listed all producers that a consumer flow actually calls.
- [ ] Each producer owns its own contracts, generated tests, and stubs artifact.
- [ ] `@AutoConfigureStubRunner` contains the exact `ids` to verify.
- [ ] Artifacts have **pinned versions** and the exact `stubs` classifier.
- [ ] Each HTTP stub has its own port; clients do not hit the wrong server.
- [ ] Dynamic ports are looked up by **producer ID**, not list index.
- [ ] Each stub URL is bound to its client bean with an appropriate lifecycle.
- [ ] Tests invoke **production consumer services/HTTP clients**, not fixed-result mocks.
- [ ] Combined outcomes and individual producer error scenarios are verified.
- [ ] Business 404 is distinguished from unmatched 404.
- [ ] Mappings/body files exist in each JAR; no critical scenario is missing.
- [ ] `LOCAL`/`REMOTE` matches the environment; CI never silently falls back to old stable stubs.
- [ ] Parallel tests neither collide on ports nor share unintended mappings/state.
- [ ] Timeouts, retries, or messaging have dedicated tests when relevant.
- [ ] CI ran producer verification for candidate producers and consumer compatibility against the **exact candidate stub set**.
- [ ] Logged versions/commits for **each producer**, not just a single shared version.

## 29. Self-check questions

**1. Why start multiple stubs in one Checkout test?**

Because one consumer flow needs to call multiple producers. Multi-stub tests run **real Checkout code** against independent simulated APIs without starting both producers.

**2. Does one producer with three endpoints need three stubs JARs?**

No. One stubs JAR can hold multiple WireMock mappings for multiple endpoints/scenarios of the same producer.

**3. Is having two stubs share one port safe?**

Two servers cannot normally bind the same host/port; sharing ports also risks misrouting clients. Separate ports or use dynamic port lookup per producer.

**4. What problem does `@StubRunnerPort` solve?**

It retrieves the port assigned by Stub Runner to a specific producer, avoiding guessing ports by position in the `ids` array.

**5. How do LOCAL and REMOTE differ?**

`LOCAL` resolves artifacts from a configured local source, usually the local Maven repository; `REMOTE` downloads artifacts from a remote repository. Both require exact versions/candidates.

**6. If a Checkout test passes against an old Inventory stub, does that prove compatibility with the Inventory candidate?**

No. It only proves compatibility with the old stub; you must test against the **Inventory candidate**.

**7. Does Stub Runner automatically synchronize prices and stock quantities between two producers?**

No. Two stubs simulate individually defined scenarios. Merging logic and consistency checks belong to the consumer; real cross-service behavior requires integration/E2E tests when appropriate.

## 30. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, stub generation, and Stub Runner.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): ids, modes, ports, artifact resolution, and multiple stubs.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML HTTP contracts.
- [Spring Cloud Contract — Maven Plugin](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): generated producer tests and stub packaging.
- [Spring Cloud Contract — Gradle Plugin](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): tasks for generating/packaging stubs.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): URL/header/body matchers and request diagnostics.
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): consumer HTTP client.
- [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): service-ID routing when not using static URLs.

**Version note:** Exact syntax for `@AutoConfigureStubRunner`, `@StubRunnerPort`, `StubFinder`, properties, and resolution can vary by Spring Cloud Contract release line. Choose a compatible Spring Boot–Spring Cloud Release Train–Contract set and inspect generated mappings, startup logs, and exact candidate artifacts. Examples in this lesson were not executed against a build during authoring.

---

**Key takeaway:** When a consumer depends on multiple producers, **package a stubs JAR per producer**, declare **multiple IDs in Stub Runner**, wire **each real HTTP client to its exact URL/port**, and verify how the consumer combines responses. CI must use the **exact candidate version of each producer**, running both producer verification and consumer compatibility; only then do you have a reliable foundation to catch incompatible API changes early.
