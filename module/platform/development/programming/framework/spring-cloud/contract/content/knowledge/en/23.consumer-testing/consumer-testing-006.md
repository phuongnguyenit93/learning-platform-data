# Testing Multiple Producers and Isolating Client Configurations

A consumer in a microservices architecture rarely calls only one producer. For example, **Checkout Service** must read an order from **Order Service**, then check stock at **Inventory Service**. If both HTTP clients share a single `baseUrl`, share authentication settings, or get assigned the wrong WireMock port, consumer tests can end up calling a valid stub for the wrong service—causing false passes or confusing errors under parallel execution.

With **Spring Cloud Contract**, each producer defines contracts using the **Groovy/YAML DSL**, generates implementation verification tests, packages a `stubs` artifact, and lets consumers run **Stub Runner** to test real HTTP client code. When a consumer depends on **multiple producers**, you must separately manage **artifact coordinates, versions, dynamic stub addresses, per-client configuration, test fixtures, and request journals**.

This lesson belongs to the **Consumer Testing** chapter of the **SPRING_CLOUD_CONTRACT** module. The goal is to design integration tests running multiple stubs in one test context **without cross-contaminating configurations**, understand the limits of consumer contract tests, and wire compatibility checks into CI when multiple producers release independently.

## 1. Why Does One Consumer Need to Test Multiple Producers?

Consider the flow for building a checkout summary:

~~~mermaid
flowchart TD
    A["Checkout Service"] --> B["OrderClient"]
    A --> C["InventoryClient"]
    B --> D["Order Service: GET /api/orders/42"]
    C --> E["Inventory Service: GET /api/stock/SKU-42"]
    D --> F["SKU, quantity, status details"]
    E --> G["Available stock quantity"]
    F --> H["CheckoutSummaryService aggregates"]
    G --> H
~~~

**Order Service** returns:

~~~http
GET /api/orders/42
Accept: application/json
~~~

~~~json
{
  "id": 42,
  "sku": "SKU-42",
  "quantity": 2,
  "status": "PAID"
}
~~~

**Inventory Service** returns:

~~~http
GET /api/stock/SKU-42
Accept: application/json
~~~

~~~json
{
  "sku": "SKU-42",
  "available": 8
}
~~~

Checkout combines both responses to determine that the order requests `2` units while `8` are in stock, yielding `enoughStock=true` in this example. What the consumer cares about is that **both requests went to the right two producers**, both payloads decoded cleanly, and the aggregation logic worked.

| Risk | Example | Testing Layer That Catches It |
| --- | --- | --- |
| Calling wrong host | InventoryClient points to Order Service's URL. | Per-client base URL checks, per-stub journals. |
| Calling wrong path | OrderClient sends `/api/order/42` instead of `/api/orders/42`. | Request matching, unmatched requests. |
| Schema mismatch | Inventory renames `available` to `stockCount`. | Producer verification and consumer deserialization. |
| Leaked headers | Order Service's Authorization header sent to Inventory. | Journal/header assertions on each stub. |
| Mixed versions | Checkout tests against order stub v1 with an incompatible inventory stub. | Artifact version matrix, consumer integration tests. |
| Call-order dependency | Test assumes two requests always fire in a fixed order when business logic makes no such guarantee. | Assert true interactions rather than enforcing arbitrary ordering. |

**A test suite using only one stub at a time** can prove each client works individually, yet may fail to catch **wiring mistakes when both clients coexist**. Therefore, test **each client independently** as well as a **combined flow exercising both**.

## 2. Four Layers That Must Be Isolated

To prevent cross-configuration bugs, distinguish:

1. **Artifact:** each producer has its own `groupId:artifactId:version:stubs`.
2. **Stub server:** each HTTP producer stub gets its own runtime URL/port assigned by Stub Runner.
3. **Client:** each HTTP client has its own base URL, auth, headers, timeouts, retries, and serializer per its producer's requirements.
4. **Test state:** request journals, scenario states, fixtures, and assertions belong to the right stub and test.

| Component | Order Service | Inventory Service |
| --- | --- | --- |
| Illustrative artifact | `com.acme:order-service:1.0.0:stubs` | `com.acme:inventory-service:2.0.0:stubs` |
| Stub HTTP URL | Looked up via `StubFinder` | Looked up separately via `StubFinder` |
| Client code | `OrderClient` | `InventoryClient` |
| Production property | `clients.orders.base-url` | `clients.inventory.base-url` |
| Example identification header | `X-Client: checkout-orders` | `X-Client: checkout-inventory` |
| Path | `/api/orders/42` | `/api/stock/SKU-42` |
| DTO | `OrderDto` | `StockDto` |
| Retry/timeout | Per Order API policy | Per Inventory API policy |

Two producers can differ in authentication, SLAs, and release versions. **Never use a single "global downstream URL" or one shared mutable HTTP client builder mutated sequentially for both** without understanding whether configuration is copied/isolated.

## 3. Each Producer's Contracts Must Remain Independent

Each producer is responsible for **verifying its own implementation** before publishing stubs. Examples written in **Groovy DSL**:

### 3.1. Order Service Contract

In the **Order Service** repository, file `src/test/resources/contracts/orders/get_paid_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'

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
            sku: 'SKU-42',
            quantity: 2,
            status: 'PAID'
        )
    }
}
~~~

### 3.2. Inventory Service Contract

In the **Inventory Service** repository, file `src/test/resources/contracts/stock/get_stock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnAvailableStock'

    request {
        method 'GET'
        url '/api/stock/SKU-42'
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
            sku: 'SKU-42',
            available: 8
        )
    }
}
~~~

The two contracts describe two separate APIs. Sample values `42`, `SKU-42`, and `available=8` serve only a deterministic test scenario. They **do not guarantee** that production Order Service and Inventory Service share instantaneously consistent data or that stock cannot change between calls.

### 3.3. Same Behavior in YAML DSL

Order Service may choose YAML instead of Groovy:

~~~yaml
description: Order Service returns a paid order
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
    sku: SKU-42
    quantity: 2
    status: PAID
~~~

Inventory Service has its own YAML contract:

~~~yaml
description: Inventory Service returns stock quantity
request:
  method: GET
  url: /api/stock/SKU-42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-42
    available: 8
~~~

Inside one producer, pick **one active representation** per scenario; do not load both equivalent Groovy and YAML definitions at once and produce duplicate stub mappings. Two producers can use **different DSLs** while the consumer still runs Stub Runner against both independent artifacts.

## 4. Preparing Both Stub Artifacts

Each producer runs **Contract Verifier** with its own base test and environment. Once producer tests pass, the build packages the artifacts:

~~~text
com.acme:order-service:1.0.0:stubs
com.acme:inventory-service:2.0.0:stubs
~~~

In a local `LOCAL` practice run, each producer can use its configured Maven workflow:

~~~shell
mvn clean verify
mvn install
~~~

These are **illustrative commands run inside each producer repository**, not combined or executed simultaneously. Depending on the Maven lifecycle, `install` may re-run tests. In CI, structure stages so producer verification is a **mandatory gate before publishing**. If consumers run on different machines/runners, publish both artifacts to a Maven repository and use Stub Runner in `REMOTE` mode.

**Version note:** Order Service `1.0.0` and Inventory Service `2.0.0` do not need matching version numbers. The two services have independent release cycles; consumers must test a **specific version combination**, rather than automatically bumping all dependencies to "latest."

## 5. Having Stub Runner Download and Start Both HTTP Stubs

On the consumer side, Spring Cloud Contract Stub Runner can load multiple artifacts in one test:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = {
        "com.acme:order-service:1.0.0:stubs",
        "com.acme:inventory-service:2.0.0:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutConsumerContractTest {
    // Multi-producer tests will be written below.
}
~~~

**Do not pin fixed ports** in `ids` if you want Stub Runner to allocate ports dynamically, avoiding CI jobs colliding over `8089` or `8090`. Once stubs start, use **`StubFinder`** to look up each producer's URL:

~~~java
import java.net.URL;
import java.util.Objects;

@Autowired
private StubFinder stubFinder;

private URL orderStubUrl() {
    return Objects.requireNonNull(
        stubFinder.findStubUrl("com.acme", "order-service"),
        "Order Service stub was not started"
    );
}

private URL inventoryStubUrl() {
    return Objects.requireNonNull(
        stubFinder.findStubUrl("com.acme", "inventory-service"),
        "Inventory Service stub was not started"
    );
}
~~~

These snippets illustrate part of a test class and require the corresponding Spring StubFinder/JUnit imports. A `groupId + artifactId` pair is safer than looking up by `order-service` alone, especially when multiple groups share artifact names.

**Never reuse one shared URL** from a single port. For instance, this is a bug:

~~~java
String url = orderStubUrl().toExternalForm();
OrderClient orders = new OrderClient(url);
InventoryClient inventory = new InventoryClient(url); // Wrong.
~~~

This bug happens easily if the test keeps only a single `stubBaseUrl` variable. Create **two clearly named variables** and pass each to the right client:

~~~java
OrderClient orders = new OrderClient(
    orderStubUrl().toExternalForm()
);
InventoryClient inventory = new InventoryClient(
    inventoryStubUrl().toExternalForm()
);
~~~

`StubFinder` returns the URL of the **running stub server**, not the Maven repository URL. `REMOTE` mode also downloads artifacts from the repository and then starts local WireMock servers on dynamic ports; `REMOTE` **does not mean** the HTTP client calls the Maven repository itself.

## 6. Writing Two HTTP Clients with Isolated Configuration

With Spring Framework 6.1+ / compatible Spring Boot, you can use **`RestClient`**. Create **a separate RestClient instance per client**, rather than sharing a single mutable builder and repeatedly swapping base URLs/headers.

### 6.1. OrderClient

~~~java
package com.acme.checkout.clients;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient http;

    public OrderClient(String baseUrl) {
        this.http = RestClient.builder()
            .baseUrl(baseUrl)
            .defaultHeader("X-Client", "checkout-orders")
            .build();
    }

    public OrderDto getOrder(long id) {
        return http.get()
            .uri("/api/orders/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(
        long id, String sku, int quantity, String status
    ) {}
}
~~~

### 6.2. InventoryClient

~~~java
package com.acme.checkout.clients;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class InventoryClient {
    private final RestClient http;

    public InventoryClient(String baseUrl) {
        this.http = RestClient.builder()
            .baseUrl(baseUrl)
            .defaultHeader("X-Client", "checkout-inventory")
            .build();
    }

    public StockDto getStock(String sku) {
        return http.get()
            .uri("/api/stock/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(StockDto.class);
    }

    public record StockDto(String sku, int available) {}
}
~~~

The two clients have **distinct URLs and headers**. In this example, `X-Client` is used solely to illustrate configuration verification; it is not a Spring Cloud Contract requirement. If the real producers require specific headers, put them in **producer-verified contracts** and configure each client accordingly.

**Why avoid sharing a mutable builder?** A `RestClient.Builder` retains customizations after calls like `baseUrl(...)` or `defaultHeader(...)`. If the same builder is mutated sequentially for Order and Inventory, headers/tokens/interceptors from the first client can leak unintentionally onto the second. Creating a fresh builder per client or **explicitly cloning** per framework APIs keeps configurations isolated.

With `WebClient` or `RestTemplate`, the same principle holds: **each producer has its own endpoint, auth, codec, timeout, and retry settings**, even if clients share thread-safe infrastructure like a connection pool when properly designed.

## 7. Production Configuration Must Use Two Separate Properties

To transition from tests to the real application, never hard-code URLs inside clients. Spring Boot configuration can bind two separate properties:

~~~yaml
clients:
  orders:
    base-url: ${ORDERS_API_URL}
  inventory:
    base-url: ${INVENTORY_API_URL}
~~~

This is an illustrative `application.yml` snippet: environment variables `ORDERS_API_URL` and `INVENTORY_API_URL` are supplied at deployment time. Never commit production tokens/secrets into contracts or test code.

A Spring factory configuration:

~~~java
package com.acme.checkout.config;

import com.acme.checkout.clients.InventoryClient;
import com.acme.checkout.clients.OrderClient;
import com.acme.checkout.service.CheckoutSummaryService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OutboundClientsConfig {

    @Bean
    OrderClient orderClient(
            @Value("${clients.orders.base-url}") String baseUrl) {
        return new OrderClient(baseUrl);
    }

    @Bean
    InventoryClient inventoryClient(
            @Value("${clients.inventory.base-url}") String baseUrl) {
        return new InventoryClient(baseUrl);
    }

    @Bean
    CheckoutSummaryService checkoutSummaryService(
            OrderClient orders, InventoryClient inventory) {
        return new CheckoutSummaryService(orders, inventory);
    }
}
~~~

This class provides two beans of **different types and different properties**. If multiple clients share the same `RestClient` type, use explicit bean names or qualifiers to avoid mis-injection.

A configuration rule worth adopting in real projects:

| Setting | Isolate Per Producer? | Why |
| --- | --- | --- |
| Base URL / service discovery name | **Yes** | Order and Inventory are distinct targets. |
| Authorization/token audience | **Yes** | Never leak Order tokens to Inventory or vice versa. |
| Default headers | **Yes** | Avoid sending metadata to the wrong producer. |
| Timeout/retry/circuit breaker | **Yes** | Each API has different SLAs and idempotency guarantees. |
| DTO/serializer/schema | **Yes** | Producers may use different enums, date formats, or fields. |
| Metrics/logging tags | **Yes** | Distinguish Order vs. Inventory errors in monitoring. |
| Connection pool | **Can be shared carefully** | Only if thread-safe with clear resource/isolation policies. |

**Never share the same token across all downstream services if the authorization model forbids it.** Tokens in consumer tests must be dummy fixtures. When testing a client, assert only headers that belong to the contract, and never put real credentials into WireMock request journals or CI logs.

## 8. Orchestration Layer Using Both Clients

A consumer often contains data-aggregation logic. To test meaningfully, exercise **that real orchestration service** rather than just firing two raw HTTP calls in the test.

~~~java
package com.acme.checkout.service;

import com.acme.checkout.clients.InventoryClient;
import com.acme.checkout.clients.OrderClient;

public final class CheckoutSummaryService {
    private final OrderClient orders;
    private final InventoryClient inventory;

    public CheckoutSummaryService(
            OrderClient orders, InventoryClient inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    public CheckoutSummary summaryFor(long orderId) {
        OrderClient.OrderDto order = orders.getOrder(orderId);
        InventoryClient.StockDto stock =
            inventory.getStock(order.sku());

        if (!order.sku().equals(stock.sku())) {
            throw new IllegalStateException(
                "Inventory SKU does not match order SKU");
        }

        return new CheckoutSummary(
            order.id(),
            order.sku(),
            order.quantity(),
            stock.available(),
            stock.available() >= order.quantity()
        );
    }

    public record CheckoutSummary(
        long orderId,
        String sku,
        int requestedQuantity,
        int availableQuantity,
        boolean enoughStock
    ) {}
}
~~~

This is a **read-and-aggregate** flow, not a distributed transaction. Stock levels can change after reading; if the business process requires reserving stock or paying atomically, dedicated APIs/workflows must guarantee it. A consumer contract test with two stubs **does not by itself prove cross-service consistency or atomicity**.

## 9. Complete Consumer Test: Two Dynamic URLs and Real Logic

In Checkout Service, we create a minimal Boot test context so Stub Runner starts both stubs. Real clients are constructed **after** `StubFinder` resolves the URLs, avoiding guessing ports before the Spring context finishes starting.

~~~java
package com.acme.checkout;

import com.acme.checkout.clients.InventoryClient;
import com.acme.checkout.clients.OrderClient;
import com.acme.checkout.service.CheckoutSummaryService;

import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = MultiProducerContractTest.TestApp.class)
@AutoConfigureStubRunner(
    ids = {
        "com.acme:order-service:1.0.0:stubs",
        "com.acme:inventory-service:2.0.0:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class MultiProducerContractTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {}

    @Autowired
    private StubFinder stubFinder;

    @Test
    void combinesOrderAndInventoryResponses() {
        URL ordersUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub missing"
        );
        URL inventoryUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "inventory-service"),
            "Inventory Service stub missing"
        );

        assertThat(ordersUrl.toExternalForm())
            .isNotEqualTo(inventoryUrl.toExternalForm());

        // Use the application's real HTTP client classes.
        OrderClient orders = new OrderClient(
            ordersUrl.toExternalForm()
        );
        InventoryClient inventory = new InventoryClient(
            inventoryUrl.toExternalForm()
        );

        CheckoutSummaryService service =
            new CheckoutSummaryService(orders, inventory);

        var summary = service.summaryFor(42L);

        assertThat(summary.orderId()).isEqualTo(42L);
        assertThat(summary.sku()).isEqualTo("SKU-42");
        assertThat(summary.requestedQuantity()).isEqualTo(2);
        assertThat(summary.availableQuantity()).isEqualTo(8);
        assertThat(summary.enoughStock()).isTrue();
    }
}
~~~

**What this test proves:** a single consumer business flow can talk to **two separate stubs**, send requests through two distinct clients, decode two DTO types, and aggregate values accurately per the published fixtures.

**What this test does not yet prove:** that the production Spring configuration `OutboundClientsConfig` injects properties properly across all profiles. The test intentionally constructs clients after resolving dynamic URLs. Write a **dedicated wiring test** for `clients.orders.base-url` and `clients.inventory.base-url`, or use a test configuration that binds dynamic URLs within the bean lifecycle in a controlled way, if you need to guard the application's DI setup.

In the test class above, `@SpringBootConfiguration + @EnableAutoConfiguration` creates a minimal test context rather than the full production Spring Boot application. Compatible Spring Boot/Stub Runner versions and both artifacts installed in Maven local are required. If you want to test the **full application configuration**, boot the real app context and supply stub URLs at the proper lifecycle phase. Never use a static `@DynamicPropertySource` method to access an uninitialized `@Autowired StubFinder` instance.

## 10. Verifying Requests Hit the Right Stub via the Journal

Getting the right response does not automatically prove **every client was configured properly**. Two stubs might share a broad mapping, or tests could have overly permissive matchers. The **WireMock request journal** lets you verify requests **arrived at the right server** with that client's headers.

For HTTP stubs started by Stub Runner, you can query the **WireMock Admin API** on each base URL. Example request-counting helper:

~~~java
import java.util.Map;
import java.util.Objects;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

record RequestCount(int count) {}

static int countRequests(
        String stubBaseUrl,
        String path,
        String expectedClientHeader) {
    RequestCount result = RestClient.create(stubBaseUrl)
        .post()
        .uri("/__admin/requests/count")
        .contentType(MediaType.APPLICATION_JSON)
        .body(Map.of(
            "method", "GET",
            "url", path,
            "headers", Map.of(
                "X-Client", Map.of("equalTo", expectedClientHeader)
            )
        ))
        .retrieve()
        .body(RequestCount.class);

    return Objects.requireNonNull(result).count();
}
~~~

After running `service.summaryFor(42L)`, the test can assert:

~~~java
assertThat(countRequests(
    ordersUrl.toExternalForm(),
    "/api/orders/42",
    "checkout-orders"
)).isEqualTo(1);

assertThat(countRequests(
    inventoryUrl.toExternalForm(),
    "/api/stock/SKU-42",
    "checkout-inventory"
)).isEqualTo(1);
~~~

To confirm **no request was sent to the wrong server**, also check counts for paths belonging to the other producer:

~~~java
static int countByPath(String baseUrl, String path) {
    RequestCount result = RestClient.create(baseUrl)
        .post()
        .uri("/__admin/requests/count")
        .contentType(MediaType.APPLICATION_JSON)
        .body(Map.of("method", "GET", "url", path))
        .retrieve()
        .body(RequestCount.class);
    return Objects.requireNonNull(result).count();
}

assertThat(countByPath(
    ordersUrl.toExternalForm(),
    "/api/stock/SKU-42"
)).isZero();
assertThat(countByPath(
    inventoryUrl.toExternalForm(),
    "/api/orders/42"
)).isZero();
~~~

**Crucial note on journal isolation:** `/__admin/requests/count` counts requests **recorded since server startup or the last reset**. If multiple tests share stubs, reset the request journal at the right boundary or isolate servers; otherwise counts accumulate across tests. `DELETE /__admin/requests` clears only the journal, whereas `resetAll()` can wipe mappings and should not be called carelessly against Stub Runner.

If tests run in parallel on the same instance, **never reset another test's journal**. Isolate per test context/server or include a unique correlation ID in request matchers and counts. Checking counts by path alone does not prove every request detail was right; inspect `GET /__admin/requests/unmatched` or query the journal by headers/body when needed.

## 11. Checking for Leakage of Authentication, Headers, and Default Settings

In real systems, Order Service might use an OAuth2 bearer token while Inventory Service uses an API key. If a shared HTTP client builder retains `Authorization`, the token could be sent to the wrong host—both an integration bug and a security risk.

Design target:

~~~text
OrderClient:
  baseUrl: orders API URL
  auth: token scoped for the orders audience/scope
  headers: X-Client=checkout-orders
  timeout: Order API policy

InventoryClient:
  baseUrl: inventory API URL
  auth: dedicated API key for inventory
  headers: X-Client=checkout-inventory
  timeout: Inventory API policy
~~~

In consumer tests, use **dummy tokens/keys** to verify presence, format, and **non-leakage**; never write real secrets into contracts, WireMock mappings, or CI logs.

| Misconfiguration | How to Catch in Tests |
| --- | --- |
| Inventory header appears on Order requests. | Query Order stub journal and assert header absence. |
| Order bearer token is sent to Inventory. | Check Inventory stub journal for absence of Order's Authorization header. |
| Both clients accidentally share timeout/retry settings. | Inject controlled errors/delays per stub and assert call counts and failures. |
| An interceptor mutates query/body for both clients. | Verify path/header/body per artifact and run combined tests. |
| Same DTO reused across both producers. | Maintain separate fields, types, and schemas for `OrderDto` and `StockDto`. |

**Never treat the request journal as a store for raw tokens.** In tests you can assert header absence using matchers, and when printing journals for debugging, redact Authorization headers, cookies, and sensitive payloads. WireMock recording a request does not mean it **validated** those tokens.

## 12. Timeouts, Retries, and Circuit Breakers Must Also Be Isolated

Two producers exhibit different failure modes and latencies. A `GET` request may be retried on transient errors; a mutating `POST` may require an idempotency key and a stricter policy.

**Illustrative** policy example, not Spring Cloud Contract defaults:

| Policy | OrderClient | InventoryClient |
| --- | --- | --- |
| Connection/read timeout | Short to keep order lookup responsive. | May differ per inventory SLA. |
| Retry on 503 | Up to max attempts agreed by Order team. | Up to max attempts agreed by Inventory team. |
| Retry on 404 | Usually no, if business 404. | Depends on Inventory API and 404 semantics. |
| Circuit breaker ID | `orderService` | `inventoryService` |
| Metrics tag | `producer=orders` | `producer=inventory` |

When using Resilience4j or a similar library, create **per-producer instances/names** instead of one shared circuit breaker where Inventory outages trip Order calls. Even when an orchestration flow has an overall timeout budget, configure **per-request** timeouts to pinpoint which downstream stalled.

In consumer tests, you can add error contracts or WireMock 503/delay scenarios to test retries per client. However, **never alter published stub artifacts with ad-hoc mappings** and treat them as the source of contract truth; use dedicated test-specific mappings or producer-verified error contracts. Under parallel tests, isolate scenarios and journals as well.

**A passing test with two 200 responses does not prove retry or timeout policies.** Write dedicated tests for those behaviors and verify actual request counts.

## 13. Error Orchestration: What Must the Consumer Do When One Producer Fails?

A consumer calling multiple producers must define behavior for **partial success and partial failure**. For example:

| Order Service | Inventory Service | Expected Checkout Behavior |
| --- | --- | --- |
| `200 PAID` | `200 available=8` | Produce summary with `enoughStock=true`. |
| `404 ORDER_NOT_FOUND` | Should not be called | Return order-not-found error; **skip calling Inventory** if business logic does not need it. |
| `200 PAID` | `404 SKU_NOT_FOUND` | Report missing inventory info rather than equating it with stock 0. |
| `200 PAID` | `503` | Apply bounded retries or report temporary inability to verify stock. |
| `503` | Should not be called | Return order lookup failure; verify Inventory is not called needlessly. |
| `200 PAID` | `200 available=1` | `enoughStock=false`, not an HTTP error. |

These rows are **examples of consumer design**, not universal rules of Spring Cloud Contract. Teams must explicitly agree on business behavior.

In particular, WireMock can return HTTP 404 when **no request mapping matches**. A consumer test that only asserts 404 can **false-pass** even if the client called the wrong URL. When testing business 404s, use **dedicated error contracts** with an error body/code (`ORDER_NOT_FOUND`, `SKU_NOT_FOUND`) and assert both the body and the request journal.

### 13.1. Verifying "Did Not Call the Other Producer"

Suppose Checkout must skip calling Inventory when the order does not exist. A test can check `countByPath(inventoryUrl, "/api/stock/SKU-42") == 0` to guard against **unnecessary calls**. Keep in mind, though, that a count of 0 could also happen if the client hit the **wrong path**; if you truly must guarantee Inventory **received zero requests at all**, inspect the full journal or match broadly after isolating test history.

For asynchronous flows, wait until the consumer operation completes before checking the journal; avoid arbitrary `Thread.sleep` calls. If background health checks share the context, filter business traffic with an appropriate matcher instead of assuming every request is a bug.

## 14. Spring Boot Bean Configuration: Avoiding Too-Early Initialization

A common trap when swapping production properties for dynamic stub URLs: **HTTP client beans are constructed during Spring application context startup**, whereas Stub Runner URLs are only guaranteed **after stubs start**.

What not to do:

~~~java
// Bad idea: using a static @DynamicPropertySource to
// access an @Autowired StubFinder instance that is not ready yet.
// There is no proper lifecycle guarantee for this approach.
~~~

Safe alternatives include:

1. **Construct real clients after querying StubFinder**, as in Section 9. Ideal for tests focused on HTTP/orchestration logic decoupled from application DI.
2. **Create a test configuration with a factory depending on StubFinder**, carefully verifying initialization order and Stub Runner integration mechanisms in your Spring Cloud Contract version.
3. **Use official property integration** supported by your Stub Runner version, after verifying the exact property name and when it becomes populated. Never invent `stubrunner.port.*` keys from memory.
4. **Test production wiring separately** using deterministic properties pointing to two test HTTP servers started on a known lifecycle. That test guards `OutboundClientsConfig` and `@Value` bindings, not just client constructors.

Testing can be split into **two layers**:

| Test Type | Purpose | Example |
| --- | --- | --- |
| **Consumer contract test** | Exercise real client and orchestration code against dynamically located stubs. | `MultiProducerContractTest` in Section 9. |
| **Spring configuration/wiring test** | Prove properties and bean injections are not swapped. | Boot context with two mock HTTP servers/known URLs verifying requests hit the right endpoints. |

Do not assume a contract test with manually constructed clients proves all `@Bean` definitions and production profiles are wired properly. Splitting into two layers makes every failure easy to localize.

## 15. Multiple Artifacts and Versions: Managing a Compatibility Matrix

When Order and Inventory release independently, Checkout needs to know which combinations are supported:

| Checkout Version | Order Stub | Inventory Stub | Test Outcome |
| --- | --- | --- | --- |
| `checkout-1.0` | `order:1.0.0` | `inventory:2.0.0` | **Baseline**: full client + orchestration suite passes. |
| `checkout-1.0` | `order:1.1.0` | `inventory:2.0.0` | Checks if Order upgrade breaks older Checkout. |
| `checkout-1.0` | `order:1.0.0` | `inventory:2.1.0` | Checks if Inventory upgrade breaks older Checkout. |
| `checkout-1.1` | `order:1.1.0` | `inventory:2.1.0` | Validates the next target deployment combination. |

Versions in this table are **illustrative**, not real pipeline output. You do not need the **full Cartesian product of every version**: pick supported, currently deployed, and upgrade-risk combinations, and document the compatibility strategy clearly.

In `LOCAL` mode, both artifacts must live in the CI runner/test machine's local Maven repository. In `REMOTE` mode, both artifacts must be published and the consumer must have `repositoryRoot`/credentials configured properly. **Using the same artifact-resolution mode does not mean both producers share a release cadence.**

**Never use mutable versions casually** (e.g., pulling an old snapshot one run and a new one the next). Consumer tests must record the **exact coordinates** of each artifact and link back to the corresponding producer commit or release.

## 16. CI: Protecting Multiple Producers Without Mixing Sources of Truth

A suggested pipeline:

~~~mermaid
flowchart TD
    OA["Order Service contracts"] --> OV["Order producer verification"]
    IA["Inventory Service contracts"] --> IV["Inventory producer verification"]
    OV --> OS{"Order tests pass?"}
    IV --> IS{"Inventory tests pass?"}
    OS -->|No| F["Block publishing corresponding artifact"]
    IS -->|No| F
    OS -->|Yes| OP["Publish order:version:stubs"]
    IS -->|Yes| IP["Publish inventory:version:stubs"]
    OP --> CS["Checkout CI fetches both selected artifacts"]
    IP --> CS
    CS --> RUN["Stub Runner provides separate URLs"]
    RUN --> TEST["Run OrderClient, InventoryClient, orchestration"]
    TEST --> JOURNAL["Verify request journal per stub"]
    JOURNAL --> COMPAT["Evaluate compatibility matrix"]
~~~

Essential CI requirements:

1. **Each producer owns its generated producer tests.** A producer's stub is never considered verified merely because a consumer test passed against it.
2. **Each artifact has an explicit version.** Consumer CI pins both versions under test.
3. **Stub Runner starts both stubs independently**; use `StubFinder` to resolve each base URL, avoiding fixed ports in parallel runs.
4. **Isolate per-client config:** URLs, dummy credentials, headers, timeouts/retries, and DTOs.
5. **Run both single-client and combined tests** to catch client wiring, schema parsing, and aggregation logic bugs.
6. **Verify request journals on the right servers**, ensuring zero cross-talk and zero unexpected unmatched requests.
7. **Isolate state** in parallel runs: never let concurrent tests reset a shared Stub Runner journal or scenario.
8. **Exercise per-producer failures:** controlled 404/503/timeouts, asserting fallbacks/retries/skipped calls per business rules.
9. **Validate older supported versions** before upgrading Order or Inventory. A field added or dropped by one producer can impact Checkout even when the other producer is unchanged.

If CI becomes slow, do not delete combined tests immediately: run per-client contract suites frequently and run multi-producer orchestration suites on pull requests touching wiring or versions, aligned with real risk.

## 17. Common Mistakes

| Mistake | Symptom | Fix |
| --- | --- | --- |
| Sharing one base URL across both clients. | Inventory requests hit Order WireMock, returning unmatched 404s. | Resolve both artifact URLs separately and pass each to its client. |
| Hard-coding two fixed ports in parallel CI. | `Address already in use` or hitting the wrong stub. | Drop fixed ports; use `StubFinder` and dynamic URLs. |
| Sharing one mutable builder for both clients. | Order's header/token/baseUrl leaks onto Inventory. | Create separate builders/clients or clone safely. |
| Asserting responses without checking journals. | Client may hit wrong endpoint matched by a broad stub. | Verify request method/path/headers on the target stub server. |
| Using unmatched 404 as a business error test. | 404 test passes even with the wrong path. | Define error body contracts and assert error code + matching. |
| Assuming manual client construction tests Spring DI. | Tests pass while production `@Value` properties are swapped. | Add dedicated bean/property wiring tests. |
| Resetting journals across parallel tests. | Counts fluctuate between 0 and 2, causing flakiness. | Isolate stub instances or correlation IDs; avoid shared resets. |
| Sharing one "generic DTO" across producers. | Schema changes cause silent mis-parsing. | Keep distinct DTOs/serializers per API and version. |
| Sharing retries/circuit breakers. | Inventory outages trip Order's circuit breaker. | Separate client policies and instance IDs. |
| Testing only the 200/200 happy path. | Broken fallbacks/timeouts/404 handling go unseen. | Add negative cases per the business matrix. |
| Always pulling `latest` stub versions. | Same consumer commit yields different results over time. | Pin versions and record artifact coordinates in reports. |
| Skipping producer verifier because consumer tests pass. | Stubs stay valid while real producer API drifted. | Block stub publishing unless producer verification passes. |

## 18. Practice Lab: Checkout Calling Order and Inventory

In a Spring Boot consumer using Spring Cloud Contract Stub Runner:

1. **Prepare both producer contracts** as in Section 3 across two separate producer repositories, each with its own generated tests and `stubs` artifact.
2. **Run producer verification** for Order and Inventory, confirming tests actually ran and PASSED; install both artifacts locally or publish to a repository.
3. **Implement both clients** `OrderClient` and `InventoryClient` with constructors taking a base URL and distinct `X-Client` headers.
4. **Implement `CheckoutSummaryService`** calling Order first then Inventory, checking SKU match, and computing `enoughStock`.
5. **Configure `@AutoConfigureStubRunner` with both IDs** without fixed ports and use `StubFinder` to resolve both URLs.
6. **Run the combined test**: call `summaryFor(42)`, assert `requested=2`, `available=8`, and `enoughStock=true`.
7. **Inspect the Admin request journal** on each stub: exactly one Order GET with `X-Client=checkout-orders`, exactly one Inventory GET with `X-Client=checkout-inventory`, and zero cross-path calls.
8. **Inject a deliberate wiring bug**: swap the two URLs when constructing clients. Observe the consumer test FAIL or unmatched requests; revert.
9. **Inject a schema bug**: rename `available` in an inconsistent test fixture; confirm the test catches it and distinguish this from producer verification.
10. **Exercise negative paths**: Order 404 → Inventory not called; Inventory 503 → retry/fallback per agreed policy. Use dedicated test mappings or producer-verified error contracts without confusing unmatched 404s with business errors.
11. **Test parallel execution** with dynamic ports and journal isolation to confirm neither client depends on a fixed port.
12. **Upgrade each stub version independently**, record supported Checkout version combinations, and wire both producer and consumer checks into CI.

**Completion criteria:** the consumer calls **two real HTTP clients**, each configured exclusively with **its own producer's base URL and settings**; tests verify requests landed on **the right two WireMock servers**, data aggregates accurately, and the pipeline catches swapped URLs, leaked headers, schema changes, and incompatible version bumps.

## 19. Self-Check Questions

1. When a consumer calls two producers, why is a single `stubBaseUrl` variable error-prone?
2. Must `order-service:1.0.0:stubs` and `inventory-service:2.0.0:stubs` share the same version number?
3. Does `StubFinder.findStubUrl("com.acme", "order-service")` return a Maven repository URL or the running HTTP stub URL?
4. Why does `StubsMode.REMOTE` not mean the HTTP client calls the Maven repository?
5. In our example, what guarantees `InventoryClient` does not accidentally send requests to Order Service?
6. Why can reusing one mutable `RestClient.Builder` across multiple clients leak headers?
7. If a test constructs clients directly from dynamic URLs, has it verified Spring Boot's production `@Value` wiring?
8. Using request journals, how do you prove requests reached each intended stub without cross-talk?
9. Why is an HTTP 404 response from WireMock insufficient to conclude the producer API returned a resource-not-found error?
10. When Order Service fails first, should Inventory Service still be called? Who decides this rule?
11. Should timeouts, retries, and circuit breakers be shared across all producers? Why or why not?
12. Why do two individually passing producer contract tests not automatically prove Checkout's multi-service orchestration logic works?
13. When two producers release independently, what versioning matrix strategy avoids breaking changes?
14. If a multi-producer consumer test passes while one producer skipped generated verification, can the stubs be considered trustworthy?

**Key takeaway:** **Consumer testing with multiple producers requires isolating artifacts, stub server URLs, client configurations, and test state.** Each producer verifies its own contracts with Contract Verifier and publishes versioned `stubs`; the consumer loads those artifacts with Stub Runner, resolves **distinct dynamic addresses** via `StubFinder`, and executes **real client and orchestration code**. Inspect both responses and per-stub request journals, isolate auth/headers/retries, and integrate a compatibility matrix into CI so multi-service consumers stay independently testable without sacrificing accuracy or hitting the wrong producer.
