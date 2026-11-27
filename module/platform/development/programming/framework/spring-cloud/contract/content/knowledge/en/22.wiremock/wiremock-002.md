# @AutoConfigureWireMock for Isolated HTTP Testing

## Learning Objectives

In **Spring Cloud Contract**, producers and consumers can agree on HTTP or messaging behavior through the **Groovy/YAML DSL**. The tool generates **producer contract tests**, creates stubs, allows the consumer to run with **Stub Runner**, and integrates compatibility checks into **CI**.

Alongside that contract testing workflow, Spring Cloud Contract provides **WireMock** integration so a Spring Boot application can test its HTTP client **independently of the real service**. The `@AutoConfigureWireMock` annotation starts a WireMock server in the Spring Test context and lets tests replace an external HTTP service with controllable responses.

This lesson belongs to the **WireMock** chapter and focuses on using `@AutoConfigureWireMock` deliberately. After this lesson, you will be able to:

- Explain the difference between a **WireMock HTTP client test**, a **producer contract test**, and a **consumer test with Stub Runner**.
- Add the Spring Cloud Contract WireMock dependency and configure `@SpringBootTest` together with `@AutoConfigureWireMock(port = 0)`.
- Connect the application's real HTTP client to the dynamic WireMock port via the `wiremock.server.port` property.
- Declare HTTP stubs using the Java DSL, store JSON mappings in test resources, and verify the requests actually sent.
- Simulate success responses, `404`, `503`, slow responses, and connection faults with a clear testing scope.
- Reduce errors caused by overlapping mappings, leftover server state, fixed ports, timeouts, and parallel test execution.
- Know when to move from hand-written stubs to **contract-generated stubs / Stub Runner** to guard compatibility with the producer.

## 1. Why does HTTP client testing need a mock server?

Suppose **Checkout Service** needs to ask **Inventory Service** whether an item is in stock:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Inventory returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-101","available":true,"quantity":8}
~~~

Checkout needs an `InventoryClient` that sends the HTTP request, reads the JSON, maps it to Java data, and passes the result into the order flow. If tests call the real Inventory service directly, results can depend on the network, test accounts, the other team's database state, or service downtime.

With WireMock, we replace the **external HTTP target** with an HTTP server running right inside the test environment:

~~~mermaid
flowchart LR
    T["JUnit / Spring Boot test"] --> C["Real InventoryClient"]
    C -->|HTTP localhost:dynamic-port| W["Embedded WireMock server"]
    W -->|Sample response| C
    C --> A["Assertions on client result"]
    T --> V["Verify HTTP request on WireMock"]
    V --> W
~~~

**Key point:** `InventoryClient` must still **make a real HTTP request** to WireMock. We do not mock `inventoryClient.getStock(...)` directly; doing so stops the test from protecting how the client constructs URLs, headers, request serialization, or response deserialization.

### Testing scope

| Option | Real target under test | Simulated component | Goal |
|---|---|---|---|
| Mockito mock of `InventoryClient` | Code using the client in Checkout | Entire client invocation | Test service-calling logic, **not** HTTP |
| **`@AutoConfigureWireMock`** | Checkout's HTTP client/adapter | Inventory HTTP server | Test URL, headers, body, response parsing, errors |
| `MockMvc` | **Inbound** HTTP controller of a Spring MVC app | Servlet container/network | Test the app receiving requests |
| Generated producer contract test | Producer implementation (in proper test mode) | Dependencies set up in producer base test | Test that the producer actually fulfills the contract |
| **Stub Runner** | Consumer client and handling logic | Producer simulated from contract-generated stubs | Test the consumer against a contract version |

`@AutoConfigureWireMock` does not create Groovy/YAML contracts, does not run producer tests, and does not download stub artifacts from a Maven repository. It is a **tool for isolated HTTP testing** that can complement the Spring Cloud Contract workflow.

## 2. What `@AutoConfigureWireMock` configures

In a Spring Boot test context, the annotation:

~~~java
@SpringBootTest
@AutoConfigureWireMock(port = 0)
class InventoryClientTest {
    // ...
}
~~~

does the following:

1. Starts a **WireMock HTTP server** bound to the Spring Test context.
2. Registers the running port into the `wiremock.server.port` property.
3. Allows tests to define stubs via the WireMock Java DSL or load mappings from resources.
4. Cleans up/manages the WireMock lifecycle according to the Spring test context and library mechanics.

`port = 0` asks for an **available ephemeral port**; it does not mean the server listens on port 0. The actual port is assigned when the server starts and can vary across runs.

### Why choose a random port?

A fixed port like `8089` might already be used by another application or contended over by two test suites. With `port = 0`, CI can run multiple jobs more safely, provided each test uses the assigned port.

Never hardcode `http://localhost:8089` in the production client and hope tests can override it. The HTTP target must come from **application configuration**, and the test environment overrides that configuration.

### Key properties

| Property/configuration | Purpose |
|---|---|
| `@AutoConfigureWireMock(port = 0)` | Starts WireMock on a dynamic port |
| `wiremock.server.port` | Actual port assigned to WireMock during the test |
| `inventory.base-url` | **Application-defined** property telling the HTTP client where to call |
| `@SpringBootTest(properties = ...)` | Overrides properties in the Spring test context |
| Annotation `stubs` attribute | Specifies locations to load additional JSON mappings when using stub files |

`inventory.base-url` is **not a built-in Spring Cloud Contract property**. The Checkout team must write the client to use this property.

## 3. Adding dependencies and choosing compatible versions

For a consumer module using Spring Boot and Spring Cloud Contract, an example Maven dependency setup:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-contract-wiremock</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

If using Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-contract-wiremock'
}
~~~

These examples assume the project already uses the **Spring Cloud BOM** and selects a release train compatible with Spring Boot, so version numbers are omitted. If not using a BOM, valid versions must be declared for the relevant dependencies.

Primary classes/APIs:

~~~java
import org.springframework.cloud.contract.wiremock.AutoConfigureWireMock;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
~~~

`@AutoConfigureWireMock` belongs to **Spring Cloud Contract WireMock support**, while `stubFor`, `get`, `urlEqualTo`, `aResponse`, and `verify` come from the **WireMock Java DSL**.

**Version note:** different versions of Spring Boot/Spring Cloud Contract/WireMock may differ in Java baseline, JUnit, dependencies, or configuration APIs. Use a version set compatible with your project. The Java examples below use `RestClient` (Spring Framework 6.1+, typically included in Spring Boot 3.2+), and do not represent all older Spring Boot applications.

## 4. Creating a real HTTP client to verify

For tests to be meaningful, we first need a real HTTP client in Checkout. Suppose Inventory's response is modeled as:

~~~java
package com.example.checkout.inventory;

public record StockView(
    String sku,
    boolean available,
    int quantity
) {}
~~~

`record` here requires a Java version that supports records. If the project uses an older Java version, use a POJO with appropriate getters/constructor.

### InventoryClient adapter

~~~java
package com.example.checkout.inventory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryClient {

    private final RestClient http;

    public InventoryClient(
            RestClient.Builder builder,
            @Value("${inventory.base-url}") String baseUrl) {
        this.http = builder.baseUrl(baseUrl).build();
    }

    public StockView getStock(String sku) {
        return http.get()
            .uri("/api/inventory/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(StockView.class);
    }
}
~~~

In production, the `inventory.base-url` property can point to the real Inventory Service URL, managed by deployment configuration. In tests, the property points to WireMock.

This class exercises things that a direct Mockito stub would not verify:

- Constructing the path with the `sku` variable.
- Sending the `GET` HTTP method.
- Sending the `Accept: application/json` header.
- Reading the HTTP status and deserializing JSON via the Spring HTTP client.
- Returning `StockView` with the corresponding values/types.

There is no custom business error handling here yet; `retrieve()` by default raises exceptions for HTTP error statuses per `RestClient` behavior. We will test that branch separately.

## 5. A complete test with @SpringBootTest

Assume Checkout has a Spring Boot application and the `InventoryClient` bean is in component scan. Place the test under `src/test/java` in the consumer:

~~~java
package com.example.checkout.inventory;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.wiremock.AutoConfigureWireMock;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "inventory.base-url=http://localhost:${wiremock.server.port}"
})
@AutoConfigureWireMock(port = 0)
class InventoryClientWireMockTest {

    @Autowired
    InventoryClient inventoryClient;

    @BeforeEach
    void resetWireMock() {
        // Suitable when tests only create dynamic stubs using the Java DSL.
        reset();
    }

    @Test
    void readsStockFromHttpResponse() {
        stubFor(get(urlEqualTo("/api/inventory/SKU-101"))
            .withHeader("Accept", containing("application/json"))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {
                      "sku": "SKU-101",
                      "available": true,
                      "quantity": 8
                    }
                    """)));

        StockView stock = inventoryClient.getStock("SKU-101");

        assertThat(stock.sku()).isEqualTo("SKU-101");
        assertThat(stock.available()).isTrue();
        assertThat(stock.quantity()).isEqualTo(8);

        verify(1, getRequestedFor(
                urlEqualTo("/api/inventory/SKU-101"))
            .withHeader("Accept", containing("application/json")));
    }
}
~~~

### Step-by-step breakdown

| Stage | Code | Meaning |
|---|---|---|
| Boot application | `@SpringBootTest` | Initializes `InventoryClient` and consumer config |
| Start stub server | `@AutoConfigureWireMock(port = 0)` | Opens the simulated HTTP endpoint |
| Point client to stub | `inventory.base-url=http://localhost:${wiremock.server.port}` | Avoids calling the real Inventory service |
| Declare response | `stubFor(...willReturn(...))` | Specifies request conditions and response |
| Call real client | `inventoryClient.getStock(...)` | Tests how the consumer actually makes the HTTP call |
| Assert result | `assertThat(stock...)` | Checks data after deserialization |
| Verify request | `verify(1, getRequestedFor(...))` | Checks the sent method/path/headers |

This example uses JUnit 5, AssertJ, and Java text blocks (requiring Java 15+). In older Java projects, replace text blocks with regular strings. To run, the Spring Boot test must locate the application class or configure `classes=...` appropriately, and a `RestClient.Builder` bean must exist in the context.

**Note on `reset()`:** in this test, all stubs are registered **via the Java DSL inside each test**, so resetting before each test is appropriate. If you use default mappings loaded from files, calling `reset()` can wipe those mappings; you must organize resetting and reloading mappings intentionally rather than copying `reset()` blindly.

### Why verify both the response and the request?

If you only assert:

~~~java
assertThat(inventoryClient.getStock("SKU-101").quantity())
    .isEqualTo(8);
~~~

the test confirms the ability to read the response, but does not clearly prove that the client sent `Accept` or called the exact URL if the WireMock setup is too loose.

Conversely, if you only call `verify(...)`, you know the request was sent, without proving that the consumer properly deserializes `available` and `quantity`. A high-quality client test usually needs **both sides**.

## 6. @AutoConfigureWireMock and dynamic ports

The line:

~~~java
@AutoConfigureWireMock(port = 0)
~~~

makes WireMock listen on a random port. Spring Cloud Contract exposes that port in `wiremock.server.port`. Therefore you can configure:

~~~properties
inventory.base-url=http://localhost:${wiremock.server.port}
~~~

In the test example, the property is placed directly in `@SpringBootTest(properties=...)`. You can put it in a dedicated test configuration file if the project already has a clear convention:

~~~text
src/test/resources/application-contract-test.properties
~~~

If using a dedicated configuration file, ensure the `contract-test` profile is activated properly. The filename above is only an example of Spring Boot's configuration mechanism; it does not mean Spring Cloud Contract automatically detects every file with that name.

### Two different ports

A single test can run:

- **Checkout application test server** if `@SpringBootTest(webEnvironment = RANDOM_PORT)` is enabled.
- **WireMock server** created by `@AutoConfigureWireMock(port = 0)`.

These are **two separate servers and two separate ports**. `wiremock.server.port` points only to **WireMock**, not the Checkout application port. If you only need to test an outbound client, the default `@SpringBootTest` mode is usually enough; there is no need to start Checkout's own web server.

## 7. Matching requests with the WireMock Java DSL

WireMock can match many properties of a request:

| Component | Common Java DSL API | Example |
|---|---|---|
| Method | `get(...)`, `post(...)`, `put(...)` | `GET` |
| Exact path and query | `urlEqualTo(...)` | `/api/inventory/SKU-101` |
| Path without query | `urlPathEqualTo(...)` | `/api/inventory` |
| Query parameter | `withQueryParam(...)` | `sku=SKU-101` |
| Request header | `withHeader(...)` | `Accept: application/json` |
| JSON body | `matchingJsonPath(...)` or `equalToJson(...)` | `$.sku == SKU-101` |
| Form/text body | `equalTo(...)`, `containing(...)` | Fixed or partial content |
| Cookies | `withCookie(...)` | Cookie value the client must send |

Another example, with a search endpoint:

~~~java
stubFor(get(urlPathEqualTo("/api/inventory"))
    .withQueryParam("sku", equalTo("SKU-101"))
    .withHeader("Accept", containing("application/json"))
    .willReturn(okJson("""
        {"sku":"SKU-101","available":true,"quantity":8}
        """)));
~~~

If an API accepts a JSON body via POST:

~~~java
stubFor(post(urlEqualTo("/api/reservations"))
    .withHeader("Content-Type", containing("application/json"))
    .withRequestBody(matchingJsonPath(
        "$.sku", equalTo("SKU-101")))
    .willReturn(aResponse()
        .withStatus(201)
        .withHeader("Content-Type", "application/json")
        .withBody("""
            {"reservationId":"RSV-1001","accepted":true}
            """)));
~~~

Overly loose matching such as **checking only the URL without checking the `sku` field** can allow a request with a broken body to still receive a success response. Still, avoid hardcoding random headers, dynamic request IDs, or JSON object key ordering if the interface does not promise them.

### Body patterns and JSON types

`equalToJson` is useful when you want to compare the body as **JSON** rather than comparing text space by space. `matchingJsonPath` fits checking individual fields. Choose matchers based on what the producer actually requires from the consumer.

For example, numeric JSON:

~~~json
{"quantity":8}
~~~

differs from:

~~~json
{"quantity":"8"}
~~~

If the server API requires a number type, the test must be strict enough to catch this change. However, regex or string-based matchers can accidentally allow both forms; inspect the **mapping and actual matching behavior**, especially when constructing request bodies dynamically.

## 8. Testing HTTP 404, 503 errors, and client handling branches

An HTTP client must also handle failure scenarios.

### Simulating 404

~~~java
stubFor(get(urlEqualTo("/api/inventory/SKU-404"))
    .willReturn(aResponse()
        .withStatus(404)
        .withHeader("Content-Type", "application/json")
        .withBody("""
            {"code":"SKU_NOT_FOUND","message":"SKU does not exist"}
            """)));
~~~

With the illustrative `InventoryClient` using `RestClient.retrieve()` without a custom `onStatus`, Spring typically throws `HttpClientErrorException.NotFound` for `404`. A test can check:

~~~java
import org.springframework.web.client.HttpClientErrorException;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

assertThatThrownBy(() -> inventoryClient.getStock("SKU-404"))
    .isInstanceOf(HttpClientErrorException.NotFound.class);

verify(1, getRequestedFor(
    urlEqualTo("/api/inventory/SKU-404")));
~~~

If the application maps HTTP errors to a domain exception like `InventoryUnavailableException`, assert the **application's published exception type and outcome**, rather than coupling tests directly to RestClient's exception.

### Simulating 503

~~~java
stubFor(get(urlEqualTo("/api/inventory/SKU-UNAVAILABLE"))
    .willReturn(aResponse()
        .withStatus(503)
        .withHeader("Content-Type", "application/json")
        .withHeader("Retry-After", "2")
        .withBody("""
            {"code":"INVENTORY_TEMPORARILY_UNAVAILABLE"}
            """)));
~~~

`503` is a **real HTTP response with status/headers/body**, unlike a network timeout or connection reset. If the consumer must read `Retry-After`, parse the error code, or retry per policy, write tests for those branches.

**Do not treat WireMock's default `404` when a request fails to match as proof that the API returns `404` as defined.** To test the `SKU_NOT_FOUND` business error, create a dedicated mapping for the request, then check the error code and/or request journal. Otherwise, a test might get `404` simply because you mistyped the URL and matched no stub.

## 9. Slow responses and connection faults: proper HTTP client test scope

WireMock supports simulating latency:

~~~java
stubFor(get(urlEqualTo("/api/inventory/SKU-SLOW"))
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("Content-Type", "application/json")
        .withBody("""
            {"sku":"SKU-SLOW","available":true,"quantity":8}
            """)
        .withFixedDelay(1500)));
~~~

With `withFixedDelay(1500)`, WireMock delays the response by about **1,500 ms**. If Checkout's HTTP client is configured with a shorter request/read timeout, the test can verify the fallback or timeout exception.

**Simply adding delay in WireMock does not configure timeouts on `RestClient`.** Timeouts are controlled by the underlying HTTP client/request factory; depending on the Spring version and HTTP library, configuration differs. When testing, verify the configuration of the **actual client in use**, not just a property the client never reads.

A slow response also **does not simulate a connection timeout**: WireMock has already opened the port and can accept the connection immediately, only delaying the response afterward. For a connect timeout, an appropriate network/transport condition is needed.

### Connection fault

WireMock can simulate a reset connection:

~~~java
import static com.github.tomakehurst.wiremock.http.Fault.CONNECTION_RESET_BY_PEER;

stubFor(get(urlEqualTo("/api/inventory/SKU-RESET"))
    .willReturn(aResponse()
        .withFault(CONNECTION_RESET_BY_PEER)));
~~~

In this situation there may be **no valid HTTP response**. The exception seen by the consumer depends on the HTTP client, JDK, and platform. Verify that Checkout:

- Does not treat a network failure as `available=false` when no inventory data was received.
- Bounds retries within a time budget.
- Displays or returns an "unable to verify" state appropriate to business requirements.
- Logs/records diagnostic metrics without leaking sensitive data.

There is no need to put every WireMock fault into the contract DSL. In real applications, these typically belong to **resilience/consumer HTTP tests** kept separate from producer contract tests.

## 10. JSON file stubs instead of the Java DSL

When mappings are long or reviewed frequently, WireMock supports declaring JSON stubs in resources. A common structure:

~~~text
src/test/resources/
├── mappings/
│   └── stock-available.json
└── __files/
    └── stock-available-body.json
~~~

Contents of `mappings/stock-available.json`:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-101",
    "headers": {
      "Accept": {
        "contains": "application/json"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "bodyFileName": "stock-available-body.json"
  }
}
~~~

Contents of `__files/stock-available-body.json`:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

WireMock uses the **`mappings`** convention for JSON mappings and **`__files`** for response bodies read from files. With Spring Cloud Contract WireMock, these resources can be loaded when the WireMock server starts, depending on the annotation configuration and test resource paths.

You can also specify a custom mapping directory:

~~~java
@SpringBootTest
@AutoConfigureWireMock(
    port = 0,
    stubs = "classpath:/inventory-stubs"
)
class InventoryClientMappingTest {
    // JSON mappings in the specified location.
}
~~~

Notes:

- `stubs` is an `@AutoConfigureWireMock` parameter specifying the path from which mappings are loaded.
- `bodyFileName` is resolved relative to the **WireMock files root** (`__files` by default convention); if you customize the files root, verify the corresponding path.
- If tests use file-loaded mappings, do not call `reset()` and unexpectedly wipe those mappings without reloading them.
- Syntactically valid JSON files are not enough; you still need tests where the **real client** calls properly and processes the returned body.

### Pros and cons of the approaches

| Approach | Best suited when | Considerations |
|---|---|---|
| Java DSL `stubFor(...)` in tests | A few requests, keeping setup close to assertions | Tests grow long if mappings are complex |
| JSON mapping files | Large stubs, many scenarios, externalized bodies | Managing directories, files root, reset, and naming |
| Stubs generated from Groovy/YAML contracts | Keeping behavior aligned across producer and consumer | Requires producer contract tests + Stub Runner/artifact |

**Do not equate** hand-written JSON mappings with contract-generated stubs: both can run on WireMock, but only stubs produced through the Spring Cloud Contract producer verification workflow carry a verified link to the producer code.

## 11. Managing WireMock state across tests

WireMock retains **stub mappings** and the **request journal** across the server lifecycle. Spring tests can reuse the application context through context caching, so you should not assume each test method gets a brand-new server.

Common failure situations:

| Symptom | Cause | Fix |
|---|---|---|
| Second test matches first test's mapping | Stub mappings remain in the server | Intentionally reset/re-establish stubs |
| `verify(1, ...)` sees 2 requests | Request journal from an earlier test was not cleared | Reset requests before each test or isolate setup |
| File mappings mysteriously disappear | `reset()` wiped initially loaded stubs | Do not reset all when relying on default mappings; reload |
| Test passes alone, fails in suite | Shared context/server and mutable state | Isolation and avoiding conflicting parallel tests |
| WireMock receives requests from another client | Multiple beans point to the same base URL/server | Separate resources, request matchers, and define test scope |

For tests that only use the Java DSL to create stubs inside each method, you can clean up before every test:

~~~java
@BeforeEach
void resetAndPrepare() {
    reset();
    // Then each test registers its own stubFor(...).
}
~~~

For mappings loaded from `src/test/resources/mappings` or `stubs=...`, consider resetting only the request journal if that is what you need, or reloading mappings after reset. WireMock provides separate APIs to clear the **request journal** and **mappings**; choose the right operation instead of wiping everything blindly.

**Parallel tests:** `@AutoConfigureWireMock` usually ties the server to the Spring test context. If multiple tests sharing a context register stubs on a shared server, they can contend over state. Separate contexts, disable parallelism for that group, or use dedicated servers as needed; a random port **does not automatically solve mapping contention within the same server**.

## 12. Differences between @AutoConfigureWireMock and Stub Runner

Both tools can use WireMock for HTTP, but their goals differ.

| Criterion | `@AutoConfigureWireMock` | Spring Cloud Contract Stub Runner |
|---|---|---|
| Source of responses | Java DSL or WireMock JSON mappings supplied by the test | Stubs generated from Groovy/YAML contracts and packaged |
| Needs Maven artifact coordinates? | Not required | Usually `group:artifact:version:stubs` |
| Verifies the real producer automatically? | **No** | **No**; that is the job of generated producer tests |
| Can test the real HTTP client? | Yes | Yes |
| Can simulate arbitrary delays/faults? | Yes, via the WireMock API | Only if mappings/integration actually support it; usually clearer in separate tests |
| Use when | Isolated adapter/client tests, debugging, testing network errors | Consumer-driven contract tests pinned to a producer version |
| Primary risk | Hand-written stubs can **drift** from the real producer | Stale/wrong-revision artifact or producer tests were not run |
| How it fits into CI | Consumer module tests with embedded WireMock | Producer verification → candidate stub → consumer tests |

### A promise in the DSL needs verification from both sides

Example Groovy producer contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Stock for SKU-101'
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
        body(sku: 'SKU-101', available: true, quantity: 8)
    }
}
~~~

**Generated producer tests** verify whether the real Inventory service returns the promised response. **Stub Runner** enables Checkout to test against that exact contract.

If Checkout hand-writes a WireMock mapping with `quantity=8` while the real producer changed it to string `"8"`, an isolated WireMock test can still pass. Therefore, for interfaces **requiring cross-service compatibility checks**, use contract-generated stubs and Stub Runner instead of maintaining only unverified hand-written mappings.

Conversely, when you need to test handling for **HTTP timeouts**, **connection resets**, or cases outside the formal contract, `@AutoConfigureWireMock` can be the better tool to isolate the consumer.

### Combining both kinds of tests

A practical strategy:

- **Contract-driven consumer tests:** run with Stub Runner and candidate stubs verified by the producer.
- **Consumer resilience tests:** run with `@AutoConfigureWireMock` and delay/fault/edge-case mappings controlled by the consumer team.
- **Producer contract tests:** run in the producer repository against real producer code and an appropriate base test.
- **Integration/end-to-end tests:** complement for databases, brokers, TLS, proxies, or environments needing other evidence.

Clear separation of roles ensures that whenever a test fails, you know whether to investigate the contract, producer code, client HTTP handling, or infrastructure.

## 13. @AutoConfigureWireMock does not replace MockMvc

Both annotations/mechanisms may appear in Spring Boot tests, but they serve opposite directions:

~~~mermaid
flowchart TB
    O["Checkout Service under test"] -->|Outbound HTTP| W["WireMock simulating Inventory"]
    I["Checkout controller test"] -->|Inbound HTTP| M["MockMvc / WebTestClient"]
    M --> O
~~~

- `MockMvc` tests **inbound requests** into the Spring MVC application's controller/servlet stack without a real HTTP socket.
- `@AutoConfigureWireMock` starts an **HTTP server outside the application under test** to test **outbound requests** from an HTTP client.
- `@SpringBootTest` can bring up both if needed, but do not make a test more complex than its required scope.

If the goal is "Inventory Controller returns JSON matching the contract", use a producer test or Inventory controller test. If the goal is "Checkout calls Inventory with the right headers and parses JSON", WireMock for the outbound client is the natural choice.

In many applications, `@SpringBootTest` starts a fairly large context. For a test needing only one HTTP client bean, you can design a minimal test configuration; however, `@AutoConfigureWireMock` must be wired into the Spring test context properly—switching to a test slice does not guarantee the annotation will work identically without additional configuration.

## 14. Diagnosing failures when a WireMock test fails

### Case A: "Connection refused"

`InventoryClient` might still point to a production URL or hardcoded `localhost:8089` instead of `wiremock.server.port`, or WireMock may not have started in the Spring context.

Check:

1. Whether the `inventory.base-url` property is actually bound into the client bean at creation time.
2. Whether the WireMock port in logs/`wiremock.server.port` matches the URL being called.
3. Whether the client bean internally constructs a new client with a hardcoded base URL.
4. Whether the test runs with the right annotations and Spring Boot context.

### Case B: Unexpected HTTP 404

WireMock typically returns a no-match response when a request does not match any mapping. Check:

- Method `GET` or `POST`?
- Does the path have an extra context path or trailing slash?
- Does the URL include query parameters while the mapping uses `urlEqualTo`?
- Do `Accept`/`Content-Type` headers match the matchers?
- Do the JSON body and data types differ?

Do not change the expected response to `404` to make the test "match the error" when the real goal is a success scenario. Use WireMock's request journal and unmatched/near-miss details to see where the sent request differed from the mapping.

### Case C: Test cannot find stub mapping files

Check `src/test/resources/mappings`, the `stubs` path, whether resources are included on the test classpath, and the `__files` root for `bodyFileName`. If tests reset stubs after the server loads default mappings, adjust the reset strategy.

### Case D: Test times out on CI

Distinguish between:

- **WireMock never receives the request:** wrong URL/port.
- **WireMock receives the request but the response is delayed:** HTTP client timeout triggers as configured.
- **Client retries too many times:** total duration exceeds the deadline.
- **CI starts the context slowly:** different from a single request's network/read timeout.

Do not blindly raise timeouts without classifying the cause. For time-dependent tests, use a sufficiently large gap between delay and timeout, avoiding exact millisecond comparisons.

### Case E: Test passes alone, fails in the suite

Most likely there is a **shared request journal or shared stub mappings**. Clean the right kind of state, avoid running concurrent tests against the same mutable WireMock configuration, or isolate test contexts when necessary.

## 15. Checklist for a WireMock HTTP client test

- [ ] The consumer's HTTP client is **real code**, not mocked wholesale with Mockito.
- [ ] `@AutoConfigureWireMock` is used with the right dependency and Spring context.
- [ ] The WireMock port is **dynamic** (`port=0`) and read from `wiremock.server.port`.
- [ ] The client's base URL is configurable, not a hardcoded production URL.
- [ ] Stub matchers specify the important method, path, query, headers, and body.
- [ ] Simulated responses have the right status, headers, and JSON/body data types.
- [ ] The test asserts data **after client deserialization** or application behavior.
- [ ] The test verifies at least the critical requests actually sent by the client.
- [ ] An HTTP `404` from an unmatched mapping is not mistaken for an intentional business `404`.
- [ ] WireMock state is cleaned/isolated properly between tests.
- [ ] If using file mappings, test resources and files root are configured correctly.
- [ ] If testing timeouts/faults, client timeouts and retries are actually configured.
- [ ] Tests can run in CI without competing over fixed ports or shared state.
- [ ] Behaviors needing compatibility guarantees are additionally protected by contracts + Stub Runner.
- [ ] CI runs generated producer tests before publishing stubs for consumer use.

## 16. Practice exercise: fixing a test calling the wrong place

### Problem statement

The Checkout team wrote this test:

~~~java
@SpringBootTest
@AutoConfigureWireMock(port = 8089)
class InventoryClientTest {

    @Autowired InventoryClient inventoryClient;

    @Test
    void testStock() {
        stubFor(get(urlEqualTo("/api/inventory/SKU-101"))
            .willReturn(okJson("""
                {"sku":"SKU-101","available":true,"quantity":8}
                """)));

        StockView result = inventoryClient.getStock("SKU-101");
        assertThat(result.quantity()).isEqualTo(8);
    }
}
~~~

However, `InventoryClient` is receiving its base URL from production configuration: `https://inventory.internal.example`. The test sometimes reaches the real service, sometimes hits network errors, and on CI cannot reach that service at all.

**Question 1:** What is wrong?

**Hint:** WireMock is started on port `8089`, but the client **is not configured to point to WireMock**. Adding the annotation alone does not automatically replace the URL of every HTTP client in the application.

**Question 2:** How should the test be fixed?

~~~java
@SpringBootTest(properties = {
    "inventory.base-url=http://localhost:${wiremock.server.port}"
})
@AutoConfigureWireMock(port = 0)
class InventoryClientTest {
    // Configure the stub and assertions as in the main example.
}
~~~

The precondition is that `InventoryClient` actually reads `inventory.base-url` from Spring configuration. Using a dynamic port reduces collisions across runs.

**Question 3:** If the stub returns `quantity: 8` while the real producer now returns the string `"8"`, will an isolated WireMock test catch it?

**Answer:** Not necessarily. It only tests the consumer against the **manually declared sample response**. To catch drift between the contract and the real producer, run generated producer contract tests and consume candidate stubs via Stub Runner.

**Question 4:** Should `verify(...)` be added?

**Answer:** Yes, when method/path/headers/query are an important part of the interface. It gives the test evidence that the client sent the right request, rather than only checking the deserialized response.

**Question 5:** If a timeout test fails immediately, what is the first diagnostic step?

**Answer:** Check the URL/port, whether the request reached WireMock, and whether a mapping matched; only then inspect HTTP client delays and timeouts. Do not raise wait times before confirming the request even reaches the server.

### Advanced exercise

Write three independent tests for `InventoryClient`:

1. `200` + valid JSON → `StockView` has the right types and values.
2. `404` + `{"code":"SKU_NOT_FOUND"}` → the client or application adapter detects the not-found error and preserves the error code per design.
3. `503` or a delay longer than the read timeout → the consumer takes the "unable to verify stock" branch rather than assuming "out of stock".

For each test, explain why the stubs differ and how WireMock is cleaned before running. If the consumer retries, verify the number of outbound requests and ensure budget/side effects conform to policy.

## 17. Key takeaways and references

**`@AutoConfigureWireMock` enables isolated HTTP client testing by starting a WireMock server in the Spring test context.** For tests to be meaningful, the real client must be configured to point to that server via `wiremock.server.port`, tests must declare proper request matchers/responses, and both the parsed data and sent HTTP requests must be verified.

**Do not confuse a hand-written HTTP stub with a producer-verified contract.** When the goal is controlling cross-service compatibility, use the Spring Cloud Contract Groovy/YAML DSL, run generated producer tests, package stubs by revision, and let the consumer run Stub Runner. Standalone WireMock remains very useful for testing HTTP errors, timeouts, request construction, and client behavior when the producer is unavailable.

### References

- [Spring Cloud Contract — WireMock](https://docs.spring.io/spring-cloud-contract/reference/project-features-wiremock.html): configuring `@AutoConfigureWireMock`, random ports, stubs, and resource files.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): Java DSL and JSON stub mappings.
- [WireMock — Verifying Requests](https://wiremock.org/docs/verifying/): checking the request journal and call counts.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consumer running contract-generated stubs.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): using `RestClient`.

**Practical conclusion:** testing a client with `@AutoConfigureWireMock` requires three things: **right server**, **right HTTP request**, and **right consumer response handling**. Adding producer contract tests and Stub Runner in CI gives the team both fast, isolated HTTP client tests and a mechanism to catch incompatible API changes between producer and consumer.
