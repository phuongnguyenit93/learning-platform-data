# Replacing the Producer Address with the URL Provided by Stub Runner

## Learning Objectives

In **Spring Cloud Contract**, the producer (the service providing an API or emitting messages) publishes behavior using the **Groovy/YAML DSL**. The tool generates tests on the producer side, creates a **stub** artifact, and the consumer uses **Stub Runner** to run those stubs in tests. When integrated into CI, both sides can detect incompatible API or message changes early.

This lesson belongs to the **Consumer Testing** chapter. The topic is very specific, yet it often determines whether a test is trustworthy: **how do you make the consumer's real HTTP client call the stub URL started by Stub Runner, instead of accidentally calling the real producer?**

After this lesson, you will be able to:

- Explain the relationship between **stub artifact coordinates**, the **stub server**, the **runtime port**, and the **HTTP client base URL**.
- Start stubs with `@AutoConfigureStubRunner` and obtain the port via `@StubRunnerPort` or `StubFinder`.
- Write tests using the **consumer's real client**, switching the HTTP endpoint to the stub's `localhost`.
- Choose a **dynamic port** when testing a client in isolation and a **fixed port** when you need to configure the entire Spring application context before beans are initialized.
- Distinguish between stub retrieval modes `LOCAL`, `REMOTE`, and `CLASSPATH` based on where the artifact lives.
- Verify responses, request matchers, stub versions, and error branches.
- Avoid pitfalls caused by configuration applied **too late**, hard-coded URLs, port collisions, stale artifact caches, or tests accidentally calling external environments.
- Connect producer contract tests, candidate stubs, and consumer tests into a traceable CI pipeline.

## 1. The Problem: The Test Is Green, But Where Is the HTTP Client Calling?

Suppose **Checkout Service** is the consumer. It calls **Inventory Service** to confirm stock availability before allowing a user to place an order:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Inventory is expected to return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

In production, Checkout might use the configuration:

~~~properties
inventory.base-url=https://inventory.internal.example
~~~

If a consumer test accidentally keeps this URL, there are several risks:

1. The test calls the **real service**, making results depend on the network, security, and environment data.
2. The test fails in CI because the network does not allow access to the producer.
3. The test may mutate real data if the API has side effects.
4. The test passes, yet **does not use the newly built stub**, so it fails to verify the candidate contract.
5. Reviewers see `@AutoConfigureStubRunner` in the test and assume the application switched URLs automatically.

**The annotation that starts the stub does not automatically change every HTTP client in the application.** The client must receive the stub URL/port through **dependency injection, a property, or a properly configured client factory**.

### The Correct Flow

~~~mermaid
flowchart TD
    A["Groovy/YAML contract in producer"] --> B["Generated producer tests"]
    B --> C{"Producer tests pass?"}
    C -->|Yes| D["Stub artifact: group:artifact:version:stubs"]
    C -->|No| X["Do not publish verified stub"]
    D --> E["Consumer test Stub Runner"]
    E --> F["Start HTTP stub on localhost:port"]
    F --> G["Test retrieves port/URL"]
    G --> H["Configure real InventoryClient"]
    H --> I["Client sends HTTP to stub"]
    I --> J["Assert data and Checkout decision"]
~~~

**Common mistake:** the steps "test retrieves port/URL" and "configure real InventoryClient" do not happen automatically just because Stub Runner downloaded the artifact.

## 2. Distinguishing Four Types of Addresses and Identifiers

| Concept | Example | Purpose |
|---|---|---|
| Producer service URL | `https://inventory.internal.example` | Real endpoint in a deployed environment |
| Stub artifact ID | `com.example:inventory-producer:1.0.0:stubs` | Identifies the stub package to download |
| Stub server URL | `http://localhost:18080` or dynamic port | Simulated HTTP address while Stub Runner runs |
| Consumer base URL property | `inventory.base-url` | Tells the HTTP client where to send requests |

**An artifact ID is not a URL.** The string `com.example:inventory-producer:1.0.0:stubs` helps Stub Runner locate the JAR package; the HTTP client needs a URL like `http://localhost:18080`.

**An artifact name is also not a default service discovery name.** If the consumer uses DNS or Spring Cloud LoadBalancer, you must explicitly configure what maps the service name to the stub address. In this lesson, we use an HTTP client with a direct **base URL** to learn how to wire the endpoint explicitly.

### Extended Stub Runner ID Coordinates

A common string used in `ids`:

~~~text
com.example:inventory-producer:1.0.0:stubs:0
|_________| |______________| |___| |___| |
   group       artifact      version classifier port
~~~

Where:

- `com.example`: producer group ID.
- `inventory-producer`: artifact ID.
- `1.0.0`: built/published stub version.
- `stubs`: stub artifact classifier.
- `0`: lets the operating system pick a free port for the stub server.

**Port 0 does not mean the HTTP client calls `localhost:0`.** It is a request for Stub Runner to choose an available port; the test must then retrieve the **actual port**.

The value `1.0.0` here is purely illustrative. When testing a PR with a new candidate stub, replace it with the **exact version/candidate artifact** verified by the producer, rather than defaulting to an old stable version.

## 3. Preparation: The Producer's Stub Must Exist

Before the consumer starts Stub Runner, the producer must build the stub artifact from contracts. An example Groovy HTTP contract might be:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'SKU-101 inventory is in stock'

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

Alternatively, you can write the YAML DSL:

~~~yaml
description: 'SKU-101 inventory is in stock'
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

A real build only needs **one contract for this scenario**; do not duplicate Groovy and YAML as two separate contracts if that creates overlapping mappings.

When the producer runs the full verification lifecycle, the plugin typically generates **generated producer tests** and packages `*-stubs.jar`. Maven example:

~~~bash
# In the producer module configured with Spring Cloud Contract Verifier:
./mvnw clean verify

# If you want to use Stub Runner with stubsMode=LOCAL,
# you must install the stub artifact into the local Maven repository:
./mvnw install
~~~

`install` is only meaningful when the build is configured to create/attach the appropriate stub artifact. Check plugin output and test reports rather than assuming any Maven command automatically generates stubs.

More importantly: the existence of `stubs.jar` **is not enough to prove the producer passed the contract tests**. In a reliable release workflow, publish a stub as a verified commitment only when the generated producer tests **actually ran and PASSED**.

### Contents of a Stub Artifact

A common layout:

~~~text
inventory-producer-1.0.0-stubs.jar
└── META-INF/
    └── com.example/
        └── inventory-producer/
            └── 1.0.0/
                ├── contracts/
                │   └── inventory/stockAvailable.groovy
                └── mappings/
                    └── inventory_stockAvailable.json
~~~

Exact paths and names depend on the Spring Cloud Contract version and packaging setup. For HTTP, Stub Runner runs WireMock based on the mappings/contracts in the artifact. For messaging, it also uses labels/message definitions; **not every stub is an HTTP mapping**.

## 4. Required Dependencies on the Consumer Side

For a Spring Boot consumer using Maven:

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

With Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
}
~~~

These examples assume the project has already configured the appropriate Spring Boot/Spring Cloud BOM and repositories. Across different release trains, choose compatible dependency versions; do not copy versions from another project without checking the active BOM.

There are two key components:

~~~java
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
~~~

and to **obtain the running stub port**:

~~~java
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
~~~

`@AutoConfigureStubRunner` selects and starts the stubs; `@StubRunnerPort` injects the **runtime port** of a specific stub into the test. If multiple producers are started together, use explicit stub identifiers so you do not grab the wrong port.

## 5. Approach 1 — Dynamic Port, Creating the HTTP Client from the Stub Runner URL

This is the easiest approach to observe when you want to test the **real HTTP adapter/client** without fixing a port.

### Consumer HTTP Client

Suppose Checkout uses Spring `RestClient` and has a class implementing the real HTTP requests:

~~~java
package com.example.checkout.inventory;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public class InventoryClient {

    private final RestClient http;

    public InventoryClient(RestClient.Builder builder, String baseUrl) {
        this.http = builder.baseUrl(baseUrl).build();
    }

    public StockResponse findBySku(String sku) {
        return http.get()
            .uri("/api/inventory/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(StockResponse.class);
    }
}
~~~

Response model:

~~~java
package com.example.checkout.inventory;

public record StockResponse(
    String sku,
    boolean available,
    int quantity
) {}
~~~

`RestClient` is available in modern Spring Framework versions, such as Spring Framework 6.1+ (Spring Boot 3.2+). If the project uses `RestTemplate`, OpenFeign, or `WebClient`, the **principle of replacing the base URL remains the same**; only the configuration API differs.

The `InventoryClient` class above is used both in the real application and in tests; the test does not mock `findBySku(...)` and only swaps the **target address**. In production, a bean can be created via a `@Configuration` that reads `inventory.base-url` from environment configuration.

### Consumer Test with a Dynamic Port

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
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryClientContractTest {

    @StubRunnerPort("inventory-producer")
    int inventoryStubPort;

    @Autowired
    RestClient.Builder restClientBuilder;

    @Test
    void readsStockFromProducerStub() {
        String stubBaseUrl = "http://localhost:" + inventoryStubPort;

        // Use Checkout's real HTTP client class, only replacing the URL.
        InventoryClient client =
            new InventoryClient(restClientBuilder, stubBaseUrl);

        StockResponse response = client.findBySku("SKU-101");

        assertThat(response.sku()).isEqualTo("SKU-101");
        assertThat(response.available()).isTrue();
        assertThat(response.quantity()).isEqualTo(8);
    }
}
~~~

### Why Is This Example Trustworthy?

1. Stub Runner locates the stub artifact `com.example:inventory-producer:1.0.0:stubs` in the local Maven repository.
2. `:0` instructs it to start the HTTP stub on a **dynamic port**.
3. `@StubRunnerPort("inventory-producer")` retrieves the actual port of that stub.
4. The test creates a **real InventoryClient** using `http://localhost:<port>`, not the production Inventory URL.
5. The client sends a real HTTP request. The stub returns a response only if the request matches a mapping.
6. Assertions verify that the consumer parses the JSON and data types correctly.

**Exact scope:** the example verifies the **real InventoryClient class**, but **does not automatically verify Spring production bean wiring** because the test constructs the client directly with the URL. This is an intentional choice for an isolated HTTP adapter test. The next section shows how to test wiring as well.

### Notes on @StubRunnerPort

When there is only one `inventory-producer` artifact in the example, using the artifact ID is readable. When multiple artifacts share the same name across different groups, use the full identifier supported by your Stub Runner version to avoid ambiguity; never rely on server startup order.

If the `inventoryStubPort` field is 0 or not injected as expected, **do not try calling localhost:0**. Check the loaded artifact, active annotations, stub name in `ids`, version, and test context.

## 6. Retrieving the URL with StubFinder

Besides injecting the port, Spring Cloud Contract provides the `StubFinder` API to look up a running stub by producer identifier.

Example in a consumer test:

~~~java
import java.net.URL;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cloud.contract.stubrunner.StubFinder;

class StubUrlLookupExample {

    @Autowired
    StubFinder stubFinder;

    void inspectUrl() {
        URL inventoryUrl =
            stubFinder.findStubUrl("com.example", "inventory-producer");

        // inventoryUrl has the form http://localhost:<runtime-port>
        // Pass inventoryUrl.toString() into InventoryClient.
    }
}
~~~

`StubFinder` is useful when:

- The test manages **multiple stubs** and needs lookup by group/artifact.
- You need the **full URL**, not just the port number.
- You want to distinguish producer A's URL from producer B's URL without hard-coding port constants.
- A client factory accepts `String`/`URL`/`URI` directly.

**This is an illustrative snippet inside a Spring test context configured with Stub Runner**, not a standalone runnable class. API overloads/identifiers may vary slightly across versions; if your project uses a different version, verify the return types and `StubFinder` API available in your actual dependencies.

Avoid obtaining the URL by scanning open local ports yourself. Stub Runner already knows which server corresponds to which artifact; use the API/properties it provides.

## 7. Approach 2 — Fixed Port to Also Test Application Wiring

In the dynamic-port example, the test constructs the client after the stub starts. Sometimes, however, you want to test **CheckoutService with Spring already injecting InventoryClient** and calling its dependency through the active bean configuration.

When Spring creates `InventoryClient`, it may read `inventory.base-url` directly in the constructor. Therefore, the URL must be set **before bean initialization time**.

A simple, easily verifiable approach is to **instruct Stub Runner to use a fixed port in tests**, and configure the consumer application to point to that port.

### Bean Configuration in the Application

~~~java
package com.example.checkout.inventory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class InventoryClientConfiguration {

    @Bean
    InventoryClient inventoryClient(
            RestClient.Builder builder,
            @Value("${inventory.base-url}") String baseUrl) {
        return new InventoryClient(builder, baseUrl);
    }
}
~~~

The production application can keep the property:

~~~properties
inventory.base-url=https://inventory.internal.example
~~~

While the test overrides it with the local URL.

### Testing Spring Wiring as Well

~~~java
package com.example.checkout.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "inventory.base-url=http://localhost:18080"
})
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:18080",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutWiringWithStubTest {

    @Autowired
    InventoryClient inventoryClient;

    @Test
    void injectedClientUsesProducerStub() {
        StockResponse response = inventoryClient.findBySku("SKU-101");

        assertThat(response.available()).isTrue();
        assertThat(response.quantity()).isEqualTo(8);
    }
}
~~~

Here:

- `:18080` in `ids` instructs Stub Runner to start the stub on port `18080`.
- `inventory.base-url=http://localhost:18080` points the **Spring-managed InventoryClient bean** directly to Stub Runner.
- The test uses `@Autowired InventoryClient`, so it additionally protects **wiring through Spring configuration**, not just the client class implementation.

**Trade-off:** a fixed port risks being occupied or colliding during parallel test runs. Only use it when you can guarantee a free port or proper test isolation. If CI runs multiple jobs on the same host, prefer dynamic ports or a lifecycle-safe dynamic configuration approach.

### Comparing the Two Test Styles

| Criterion | Dynamic Port + Client Constructed in Test | Fixed Port + Injected Application Bean |
|---|---|---|
| Stub URL | Obtained from `@StubRunnerPort` | Fixed via `ids ... :18080` |
| Tests real HTTP client | Yes | Yes |
| Tests Spring bean wiring | Not completely | Yes |
| Avoids port collisions | Better | Must manage ports |
| Parallel test execution | Easier port isolation | Requires coordination |
| Best suited for | Fast, clear adapter/client tests | Application/configuration integration tests |

**Do not claim one approach is always superior.** Choose based on the boundary you want to verify and your CI characteristics.

## 8. Why Changing Properties in @BeforeEach Is Usually Too Late

A common mistake:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class IncorrectSetup {

    @StubRunnerPort("inventory-producer")
    int port;

    @BeforeEach
    void changeUrlTooLate() {
        System.setProperty(
            "inventory.base-url",
            "http://localhost:" + port
        );
    }

    @Autowired
    InventoryClient inventoryClient;
}
~~~

**The problem:** `@SpringBootTest` builds the Spring application context and singleton beans **before** running a test method's `@BeforeEach`. If `InventoryClient` reads the property when its constructor runs, it already holds the old base URL.

Moreover, `System.setProperty` is **JVM-global** state that can affect other tests and make parallel runs flaky.

**How to fix it:**

- If only testing the client: inject the port and **instantiate the client after Stub Runner has a URL** (Section 5).
- If testing wiring: choose a predetermined port and set `@SpringBootTest(properties=...)` upfront (Section 7).
- If you must have both dynamic ports **and** full application wiring: use a bootstrap/configuration mechanism compatible with Stub Runner's and Spring Boot's lifecycle in your project version; verify when the property is registered relative to bean creation. Never read a `@StubRunnerPort` field inside a static initializer assuming it already has a value.

Some setups rely on **runtime properties registered by Stub Runner** for the ports of running servers. Exact property names/identifiers and registration ordering depend on integration/version; if you use this approach, verify against the real test context and inspect which URL the bean actually received. A configuration that sounds plausible on paper but takes effect **after the bean is built** offers no protection.

## 9. Configuring Clients for Multiple Producers

Checkout may call **Inventory Service**, **Pricing Service**, and **Payment Service**. Each producer has its own stub:

~~~java
@AutoConfigureStubRunner(
    ids = {
        "com.example:inventory-producer:1.0.0:stubs:0",
        "com.example:pricing-producer:2.1.0:stubs:0",
        "com.example:payment-producer:3.0.0:stubs:0"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

Each client needs **that specific producer's URL**:

~~~java
@StubRunnerPort("inventory-producer")
int inventoryPort;

@StubRunnerPort("pricing-producer")
int pricingPort;

@StubRunnerPort("payment-producer")
int paymentPort;
~~~

Then:

~~~java
InventoryClient inventory =
    new InventoryClient(builder, "http://localhost:" + inventoryPort);

// Similarly: Checkout's real pricingClient and paymentClient,
// each receiving its own base URL.
~~~

Avoid:

- Accidentally using Inventory's port for Pricing just because both have `GET` endpoints.
- Relying on the **startup order** of stub servers.
- Omitting group/artifact/version when multiple stubs could share names.
- Using one shared configuration variable like `external.base-url` for all dependencies without explicit routing.
- Using `latest` stubs for each producer, making tests hard to reproduce.

### Service Discovery and Load Balancing

If the application uses `http://inventory-service` via service discovery instead of a direct URL, decide **which layer in tests replaces the service name with the stub target**. You can override target URL settings, register a fake service instance, or use Stub Runner's load-balancing/discovery integration per your version.

This lesson prioritizes an **explicitly configured base URL**. Never assume Stub Runner automatically overrides DNS for every service name in the application.

## 10. Testing What the Consumer Actually Needs, Not Just Status 200

A meaningful consumer contract test should verify **how the consumer processes the response**:

~~~java
StockResponse response = client.findBySku("SKU-101");

assertThat(response.sku()).isEqualTo("SKU-101");
assertThat(response.available()).isTrue();
assertThat(response.quantity()).isEqualTo(8);
~~~

If Checkout has a business rule "do not allow ordering more than available stock," test the **business flow directly** when setup allows, rather than only checking JSON deserialization.

Pseudocode example:

~~~text
given stub: SKU-101 available=true, quantity=8
when Checkout asks to order 9 units
then Checkout rejects quantity > 8

given stub: SKU-101 available=true, quantity=8
when Checkout asks to order 2 units
then Checkout allows next checkout step
~~~

**Do not hard-code `available=true` inside CheckoutService just to make the test pass.** The test must call through the client and genuinely consume the stub response.

### Comparing Testing Layers

| Test | Protects Well | Does Not Protect |
|---|---|---|
| Unit test with mocked `InventoryClient` | Checkout branching on fake responses | URLs, HTTP headers, serialization |
| Consumer test with Stub Runner + real client | HTTP requests and how the consumer reads the contract stub | Real producer implementation (if producer tests have not run) |
| Generated producer contract test | Real producer satisfies the described contracts | Application logic across all consumers |
| End-to-end test with real services | Selected real integration flows | All error/edge cases unless simulated |

This lesson focuses on **consumer tests via Stub Runner**; they must be paired with **producer contract verification** so both sides have shared evidence.

## 11. Testing HTTP Errors: Do Not Confuse Unmatched-Mapping 404s

Suppose the producer contract includes this scenario:

~~~http
GET /api/inventory/SKU-404 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"SKU_NOT_FOUND","message":"SKU does not exist"}
~~~

Once Stub Runner has loaded the artifact containing this error contract, the consumer can test its handling branch.

Example using `RestClient.retrieve()` without a custom `onStatus`:

~~~java
import org.springframework.web.client.HttpClientErrorException;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

assertThatThrownBy(() -> client.findBySku("SKU-404"))
    .isInstanceOf(HttpClientErrorException.NotFound.class);
~~~

If the application translates `404` into a business outcome with code `SKU_NOT_FOUND`, the test should assert that exact outcome type; not every consumer needs to expose raw HTTP library exceptions directly.

**Crucial point:** when WireMock cannot find a matching mapping, it can also return a default `404`. Therefore, a test that only asserts "received 404" **does not necessarily prove** that the `SKU_NOT_FOUND` case in the contract was matched.

Ways to increase confidence:

1. Verify the stub artifact contains the corresponding contract.
2. Inspect the method, path, query, and headers the client actually sends.
3. Assert the **error body/code** per the interface, not only the status.
4. When needed, check WireMock/Stub Runner unmatched request logs or the request journal.
5. Confirm you are calling the right Stub Runner server, not another WireMock instance.

### Do Not Use a 503 Response to Prove Timeout Handling

`HTTP 503` is a response with a status, headers, and body. A **client timeout** happens when the client receives no result within the allowed window. A `503` contract does not simulate a slow connection or TCP reset.

To test retries, timeouts, or specific network faults, add dedicated consumer tests with WireMock faults/delays. Do not arbitrarily alter official contracts just to force resilience tests to get a desired status.

## 12. Stub Runner LOCAL, REMOTE, and CLASSPATH

Where stubs come from directly affects the reproducibility of consumer tests.

| Mode | Stub Source | When to Use | What to Watch Out For |
|---|---|---|---|
| `LOCAL` | Local Maven repository of the test runner | Dev machines or pipelines that installed the candidate stub locally | Stub must be installed at the exact version; risk of stale cache |
| `REMOTE` | Configured artifact repository | CI or other consumers pulling versioned stubs from Nexus/Artifactory/Maven repository | Requires repository URL, read credentials/permissions, and explicit version |
| `CLASSPATH` | Stubs packaged/present on the test classpath | Integration tests bundled with stub dependencies | Requires proper layout/resources; does not automatically search Maven local |

### LOCAL

Example:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

If the producer has not installed `inventory-producer-1.0.0-stubs.jar` into the local repository, Stub Runner may fail to find the artifact. A file sitting in the producer workspace does not automatically mean it is in the Maven local repo read by consumer tests.

### REMOTE

When using a remote repository, configure the source parameters in the annotation/properties appropriate for your version:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    repositoryRoot = "https://artifacts.example.test/repository/stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE
)
~~~

The address above is an illustrative URL, not a real accessible repository. In real CI, configure your internal repository and approved authentication mechanism; **never put tokens/passwords directly into source code or URLs**.

### CLASSPATH

With `CLASSPATH`, stubs are loaded from resources/dependencies placed on the test classpath. Setup depends on how stubs are packaged and loaded in your version. Do not assume `CLASSPATH` tells Stub Runner to search the local Maven repository automatically.

**General rule:** regardless of mode, the test must know the **exact stub artifact/revision** being executed. If the producer updates a contract while the consumer still runs an old version, the test may stay green without verifying the PR's changes.

## 13. Stub Runner Started, But the Client May Still Be Misconfigured

When debugging, separate three distinct steps:

~~~text
A. Stub Runner RESOLVED artifact
   ↓
B. Stub Runner STARTED HTTP server at runtime port
   ↓
C. Consumer HTTP client USED that server URL
~~~

A and B can succeed while C fails.

### Symptoms and Diagnosis

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| `@StubRunnerPort` not injected properly | Wrong stub name, artifact failed to load, wrong annotation/test context | Check Stub Runner logs, ID, and version |
| `Connection refused` | Client points to an old port, stub not running, or wrong server | Safely print the client's actual URL in test logs |
| Client calls production URL | `inventory.base-url` not overridden or bean initialized before change | Inspect bean/client config and when the property is read |
| HTTP 404 despite contract having a 200 case | URL/header/body did not match mapping | Check WireMock unmatched requests and actual mappings |
| Client receives wrong data but test passes | Test does not assert key fields or uses a mock client | Assert after deserialization and across business flows |
| Passes locally, fails in CI | `LOCAL` cache has artifact, CI runner does not | Install candidate in CI or use `REMOTE` |
| CI uses stale stub | Mutable version, cache, `+`/latest coordinates | Pin version/commit/digest, check resolved artifact |
| Port conflicts in parallel runs | Shared fixed port | Switch to `:0` or isolate runners |
| Producer test green, consumer fails | Contract change broke the client or stub matcher is wrong | Compare candidate artifact, generated tests, and consumer logic |
| Consumer test green, production fails | Stub not verified by producer or scenario uncovered | Check producer verification and test matrix |

Never try to fix every error by replacing `:0` with a fixed port. First determine **which URL the client is targeting**, **where the stub is listening**, and **whether the request matches the contract**.

## 14. Distinguishing Stub Runner from @AutoConfigureWireMock

Both can spin up a fake HTTP server for consumer tests, but their source of truth differs.

~~~java
// A: Stub Runner uses the contract artifact from the producer.
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

~~~java
// B: Embedded WireMock uses stubs registered directly by the test.
@AutoConfigureWireMock(port = 0)
~~~

| Criterion | Stub Runner | @AutoConfigureWireMock |
|---|---|---|
| Mapping source | Stubs generated from Groovy/YAML contracts | Java DSL or hand-written WireMock JSON mappings |
| Producer version coordinates | Core concept | Not required |
| Linked producer contract tests | Yes, via stub generation/verification workflow | Not automatically |
| Getting runtime URL | `@StubRunnerPort`, `StubFinder`, or integration mechanism | `wiremock.server.port` |
| Best suited for | Verifying the consumer against the producer-committed API | Standalone HTTP client tests, fault/latency tests |
| Common risk | Wrong artifact/version or forgetting to update client URL | Hand-written stubs drifting from the real producer |

`@AutoConfigureWireMock` can also use dynamic ports, but **`wiremock.server.port` is not the standard way to read the port of a stub managed by Stub Runner**. Use the right API for the right tool.

In a single test, starting both Stub Runner and another WireMock instance without clear client configuration makes it easy to hit the wrong server. Combine them only for a specific reason and document clearly which server each test calls.

## 15. Ensuring Tests Never Accidentally Call Real Services

For automated tests—especially those making mutating HTTP requests—minimize the risk of calling production.

Practices:

- Production URLs come only from deployment configuration, never hard-coded in test code.
- Tests replace the URL with the `localhost` stub **before the client is used**.
- When integration-testing multiple beans, verify which base URL the HTTP client bean received.
- Use an **unreachable dummy endpoint** as the default in the test profile when you want to catch forgotten overrides.
- Restrict test runners from reaching sensitive production networks unless explicitly needed.
- For `POST`/`PUT`/`DELETE`, watch out for side effects; never "test whether it reaches the real environment."
- If using an HTTP proxy or service discovery, make sure stub routing is not bypassed.

**Do not expect a test to fail if it accidentally calls production.** The real service might happen to return matching fixture data, leaving the test green. Test configuration must make accidental calls hard to trigger and easy to detect.

### Example Target URL Check

In a dynamic-port test:

~~~java
assertThat(inventoryStubPort).isGreaterThan(0);

String stubBaseUrl = "http://localhost:" + inventoryStubPort;

InventoryClient client =
    new InventoryClient(restClientBuilder, stubBaseUrl);
~~~

This confirms a port was assigned, but to prove requests actually hit that specific stub, **call the client and assert the response of a distinguishing mapping**. When in doubt, inspect the request journal or WireMock logs of the running stub.

## 16. When There Are Multiple Contracts for One Endpoint

One artifact may contain several mappings for `GET /api/inventory/{sku}`:

| Scenario | Request Matcher | Response |
|---|---|---|
| `stockAvailable` | `GET /api/inventory/SKU-101` | `200`, `available=true`, `quantity=8` |
| `stockEmpty` | `GET /api/inventory/SKU-EMPTY` | `200`, `available=false`, `quantity=0` |
| `stockNotFound` | `GET /api/inventory/SKU-404` | `404`, `code=SKU_NOT_FOUND` |
| `stockUnavailable` | `GET /api/inventory/SKU-UNAVAILABLE` | `503`, `code=INVENTORY_UNAVAILABLE` |

When consumer tests request each SKU, they exercise specific behavioral branches. If two mappings match the same request yet return different responses, the result may depend on mapping priority or WireMock configuration. Contracts should define **unambiguous** matchers rather than assuming the stub "remembers" stock changing over time.

Use the right request case to test the right branch; do not try to make one mapping return different responses merely by changing expected values in consumer tests.

### Mini Matrix for Checkout

~~~text
GET SKU-101
  -> Checkout can proceed with quantity <= 8

GET SKU-EMPTY
  -> Checkout shows out-of-stock

GET SKU-404
  -> Checkout reports SKU not found

GET SKU-UNAVAILABLE
  -> Checkout reports unable to verify inventory
     (and follows retry policy if applicable)
~~~

These scenarios are examples based on an assumed contract. Do not invent `503` contracts or retry rules unilaterally if producer and consumer have not agreed on them.

## 17. Structuring CI to Use the Right Candidate Stub

A pipeline can be structured as follows:

~~~mermaid
sequenceDiagram
    participant Dev as Pull request
    participant Prod as Producer contract tests
    participant Art as Candidate stub artifact
    participant Runner as Consumer Stub Runner
    participant Checkout as Consumer test
    Dev->>Prod: Change Groovy/YAML DSL and producer code
    Prod->>Prod: Generated tests run
    alt Producer tests pass
        Prod->>Art: Package stub for exact revision
        Art->>Runner: Download candidate stub by version/ID
        Runner-->>Checkout: Provide localhost:runtime-port
        Checkout->>Runner: Real HTTP client sends request
        Checkout->>Checkout: Assert business outcome
    else Producer tests fail
        Prod-->>Dev: Do not publish verified stub
    end
~~~

### Essential CI Gates

1. **Producer contract discovery:** the generator finds all expected contracts.
2. **Producer test execution:** generated tests actually run and PASS, not skipped.
3. **Stub packaging:** the candidate artifact includes required mappings/contracts/fixtures.
4. **Revision consistency:** the artifact version/commit matches the producer build just verified.
5. **Consumer retrieval:** Stub Runner actually downloads the **right candidate**, without relying on ambiguous caches.
6. **URL replacement:** consumer tests call the localhost/port provided by Stub Runner.
7. **Consumer assertions:** go beyond calling the stub; verify application behavior.
8. **Compatibility review:** changing fields, headers, status, or URLs can break existing consumers even if producer tests pass against the new contract.
9. **Release policy:** never publish an unverified stub just because consumer tests passed against it.

### How Can LOCAL Work in CI?

If a pipeline can transfer artifacts between jobs, a straightforward flow is:

~~~text
Producer job:
  checkout commit A
  run generated producer tests
  package candidate stubs.jar
  publish temporary CI artifact (not a release)

Consumer job:
  get candidate from producer job
  install artifact into isolated Maven local repository
  run @AutoConfigureStubRunner(stubsMode=LOCAL)
  use @StubRunnerPort to configure HTTP client
  run consumer tests and save reports
~~~

The step "install artifact into isolated Maven local repository" should be implemented using your organization's build/repository tooling, not by copying a JAR into an arbitrary folder. The job must include full Maven metadata so Stub Runner resolves it accurately.

If using `REMOTE` with a staging repository, manage permissions, versioning, and TTL appropriately. Never upload a candidate that has not passed the producer gate to an official release repository just so consumer tests can "grab it easily."

## 18. Common Mistakes and How to Fix Them

### Scenario A: Stub Runner Is Present, But the Client Still Calls the Old Host

~~~java
@SpringBootTest(properties = {
    "inventory.base-url=https://inventory.internal.example"
})
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class IncorrectConsumerTest {
    @Autowired InventoryClient inventoryClient;
}
~~~

**Error:** the test started the stub, but the `InventoryClient` bean still uses the real service URL. Stub Runner does not rewrite application properties automatically.

**Fix:** construct the client using the URL from `@StubRunnerPort` in a client-level test, or configure the base URL at bean-creation time pointing to a known Stub Runner port.

### Scenario B: Formatting Port 0 into a URL

~~~java
String baseUrl = "http://localhost:0";
~~~

**Error:** port 0 is a signal **requesting a dynamic port**, not a real port for HTTP calls. **Fix:** retrieve the port assigned by Stub Runner, such as via `@StubRunnerPort`.

### Scenario C: Calling System.setProperty Too Late

~~~java
@BeforeEach
void setup() {
    System.setProperty("inventory.base-url",
        "http://localhost:" + inventoryStubPort);
}
~~~

**Error:** the client bean may already have been initialized. **Fix:** configure properties before context creation or explicitly construct the client from the runtime URL.

### Scenario D: Stub Runner Downloads the Wrong Artifact

~~~text
Producer PR: 1.1.0-rc.2
Consumer test: 1.0.0
Result: PASS
~~~

**Error:** the result only proves the consumer is compatible with stub `1.0.0`, not that it understands changes in `1.1.0-rc.2`. **Fix:** pass the candidate version from the producer job into consumer tests; log the version/digest in CI output.

### Scenario E: Stub Returns Default 404

The consumer test wants to verify `SKU_NOT_FOUND` but mistakenly sends `/api/inventory/SKU404`. WireMock matches no mapping and returns 404. Because the test only asserts status, it passes.

**Fix:** assert the error code/body and inspect the request path, mappings, and near misses. Only treat the test as passing when the **contract scenario's** response was actually returned.

## 19. Practice Exercise: Wiring the Right Port and Verifying Both Sides

### Problem Statement

The consumer has an application with:

~~~java
public class InventoryClient {
    public InventoryClient(RestClient.Builder builder, String baseUrl) {
        // ...
    }
    public StockResponse findBySku(String sku) {
        // ...
    }
}
~~~

The producer provided a stub:

~~~text
group    = com.example
artifact = inventory-producer
version  = 1.0.0
classif. = stubs

GET /api/inventory/SKU-101
-> 200 application/json
-> {"sku":"SKU-101","available":true,"quantity":8}
~~~

An initial test:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class WrongTest {

    @Test
    void stock() {
        InventoryClient client = new InventoryClient(
            RestClient.builder(),
            "http://localhost:0"
        );

        // ...
    }
}
~~~

**Question 1:** Why is `localhost:0` wrong?

Port 0 in `ids` is not a real server port. It only asks Stub Runner to pick an open port. The test must retrieve the **runtime port**.

**Question 2:** How should it be fixed?

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CorrectTest {

    @StubRunnerPort("inventory-producer")
    int stubPort;

    @Autowired
    RestClient.Builder builder;

    @Test
    void readsStock() {
        InventoryClient client = new InventoryClient(
            builder,
            "http://localhost:" + stubPort
        );

        StockResponse response = client.findBySku("SKU-101");

        assertThat(response.sku()).isEqualTo("SKU-101");
        assertThat(response.available()).isTrue();
        assertThat(response.quantity()).isEqualTo(8);
    }
}
~~~

The example needs the appropriate JUnit, Spring, and AssertJ imports, as well as the producer stub in the local repository. It verifies the real HTTP client class, though it does not verify Spring application wiring when constructed manually.

**Question 3:** What if you want to verify bean wiring as well?

Choose a port configured for Stub Runner in `ids` and override `inventory.base-url` when the `@SpringBootTest` context is created, as in the `:18080` example. Or use a runtime property/bootstrap mechanism compatible with your project version. Never mutate properties in `@BeforeEach` assuming beans will rebuild.

**Question 4:** What if the consumer test passes, yet the producer code returns `quantity` as a string?

Testing against a stub only proves the client handles the **stub**. You must run generated producer contract tests to catch the real producer violating the schema, and ensure consumer tests use the stub from the verified revision.

**Question 5:** What if CI cannot find the artifact in LOCAL mode?

Build, verify, and **install the candidate stub artifact** into the runner's exact local Maven repository, or choose a different distribution repository/mode. Never switch back to an old version just to turn tests green.

### Extension Exercises

Design additional consumer tests for:

1. `SKU-EMPTY` returning `available=false`, `quantity=0`: Checkout must report out of stock.
2. `SKU-404` returning `404` with code `SKU_NOT_FOUND`: Checkout handles the missing resource without confusing it with a network error.
3. `SKU-UNAVAILABLE` returning `503`: Checkout reports a temporary inability to verify inventory and follows retry policies if configured.
4. Second producer `pricing-producer`: the pricing client must use its **own port**, never mixing up Inventory's port.

For each case, document which contract mapping is used, what real request the consumer sends, Checkout's final outcome, and the stub artifact revision tested.

## 20. Checklist Before Accepting a Consumer Test with Stub Runner

- [ ] Producer and consumer agreed on Groovy/YAML contracts for key interactions.
- [ ] Generated producer tests **ran and PASSED** before treating the stub as verified.
- [ ] `@AutoConfigureStubRunner` uses the exact group/artifact/version/classifier.
- [ ] `LOCAL`/`REMOTE`/`CLASSPATH` mode matches where the artifact is stored.
- [ ] When using dynamic port `:0`, tests **obtain the runtime port** via `@StubRunnerPort` or `StubFinder`.
- [ ] The real consumer HTTP client is constructed/configured with the stub URL and no longer calls the production URL.
- [ ] If verifying Spring wiring, the URL is configured **before beans are initialized**.
- [ ] `System.setProperty` in `@BeforeEach` is not used as a workaround for already-created singleton beans.
- [ ] Each producer has its own port/URL; tests never depend on server startup order.
- [ ] Tests assert response JSON/types or business outcomes the consumer relies on.
- [ ] Tests distinguish contract-defined 404s from unmatched-request 404s.
- [ ] Tests do not use stale stub artifacts or untraceable `latest` versions.
- [ ] Parallel tests do not collide on shared fixed ports or shared states/mappings.
- [ ] If retries/timeouts exist, dedicated scoped tests cover them; HTTP statuses are not equated with network faults.
- [ ] CI records the producer version/commit, candidate artifact, and consumer tests executed.
- [ ] Breaking API changes are evaluated against currently deployed consumers.

## 21. Key Takeaways and References

**Stub Runner starts an HTTP server for a stub artifact, but a consumer only truly tests against the stub once its HTTP client is pointed at the exact runtime URL.** `@StubRunnerPort` retrieves dynamic ports, `StubFinder` looks up URLs by stub identifier, and the application's base URL configuration controls where the client sends requests.

When testing a client in isolation, obtain the dynamic port and construct the **real client** with `http://localhost:<port>`. When verifying Spring application wiring as well, make sure the URL is configured **before beans initialize**; use a managed fixed port or a version-compatible dynamic bootstrap mechanism instead of overriding properties too late.

To genuinely verify compatibility, connect three pieces of evidence: **producer generated tests PASS**, **exact revision of the stub artifact**, and **consumer tests using the real client and Stub Runner URL**. None of these three pieces replaces the other two.

### References

- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): `@AutoConfigureStubRunner`, `@StubRunnerPort`, and using Stub Runner in Spring Boot tests.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): resolving and running stubs, `StubFinder`, and runtime URLs.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML contracts, producer verification, and stub generation.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient` API and client configuration.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): lifecycle for generating/verifying contract tests and packaging stubs.

**In short:** do not just ask "Is Stub Runner running?". Ask **"Which client called which URL, from which artifact version, and has the producer been verified?"**. That is how consumer tests genuinely help catch incompatible HTTP API changes in CI.
