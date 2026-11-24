# Managing Multiple Services, Version Compatibility, and Testing HTTP Service Client Proxies

## 1. Problem and Objectives

In a Spring application, a feature such as viewing order details may need to call **Inventory Service** to check stock, **Pricing Service** to read prices, and **Shipping Service** to estimate shipping. With HTTP Service Client, you can declare interfaces using @HttpExchange, @GetExchange, and @PostExchange, then create proxies that execute real HTTP calls via RestClient or WebClient.

When there is only one interface and one service, creating a proxy is short. With multiple services, new challenges arise: choosing the right host, preventing token leakage across services, configuring different timeouts and retries, handling API version changes without breaking, and testing whether the proxy sends **the exact real request**.

Lesson objectives:
1. Organize multiple HTTP Service Clients per remote service, with isolated base URLs, authentication, timeouts, and observability.
2. Identify HTTP contract version boundaries and distinguish compatible from breaking changes in both requests and responses.
3. Create and manage proxies with HttpServiceProxyFactory in Spring Framework 6.1+, while understanding version boundaries of group-based registration in Spring Framework 7.
4. Test proxy-generated requests (URI, method, headers, body), JSON mapping, error statuses, and contract evolution; distinguish unit tests from mock HTTP server tests and integration tests.
5. Design rollback-capable migrations when upstream/dependent services are deployed independently.

**Scope:** this lesson covers Spring's **HTTP Service Client**; the guidance on multiple services, versioning, and testing applies directly to proxies generated from interfaces. A proxy is an outbound client, **not a server implementing endpoints**, nor does it provide an API gateway, service discovery, circuit breaker, or registry on its own.

## 2. Each Service Must Have Its Own Contract and Configuration

Suppose a feature needs to call two different APIs:

| Service | Base URL in test environment | Contract | Data |
| --- | --- | --- | --- |
| Inventory | https://inventory.example.test | GET /v1/stock/{sku} | StockResponse |
| Pricing | https://pricing.example.test | GET /v2/prices/{sku} | PriceResponse |

Using different hosts here is only an example; the .test domain has no real API. Choosing versions /v1 and /v2 illustrates two independent services with separate contract lifecycles: **not every service has to move to v2 at the same time**.

Declare two separate interfaces:

~~~java
@HttpExchange(url = "/v1/stock", accept = MediaType.APPLICATION_JSON_VALUE)
public interface InventoryClient {
    @GetExchange("/{sku}")
    StockResponse findStock(@PathVariable("sku") String sku);
}

@HttpExchange(url = "/v2/prices", accept = MediaType.APPLICATION_JSON_VALUE)
public interface PricingClient {
    @GetExchange("/{sku}")
    PriceResponse findPrice(@PathVariable("sku") String sku);
}
~~~

This is **illustrative code for integration**; add the matching Spring annotation imports and define StockResponse and PriceResponse. If both share one factory and one HTTP client with a single baseUrl, calls risk going to the wrong host. Clearly separate responsibilities:

- **Interface** owns request signatures and response types per one API's contract.
- **RestClient/WebClient** owns target address, connectivity, codecs, default headers, auth/interceptors/filters, and transport policies.
- **HttpServiceProxyFactory** maps interface methods into requests sent through the adapter.
- **Application-internal service/facade** orchestrates results from multiple APIs and maps them to internal business models.

Suggested structure:

~~~text
src/main/java/com/example/client/
├── inventory/
│   ├── InventoryClient.java
│   └── StockResponse.java
├── pricing/
│   ├── PricingClient.java
│   └── PriceResponse.java
├── configuration/
│   └── PartnerClientsConfiguration.java
└── facade/
    └── ProductAvailabilityService.java
~~~

There is no need to cram all HTTP interfaces into one giant client class. A group of endpoints sharing the same host and policy can be split into multiple interfaces, as long as it is clear which factory creates which proxy.

### 2.1. Creating Proxies Explicitly with Spring 6.1+

RestClient is Spring Framework 6.1's **synchronous** HTTP client; HttpServiceProxyFactory.builderFor(HttpExchangeAdapter) was also introduced in 6.1. Bean registration in a Spring Boot application:

~~~java
@Configuration
public class PartnerClientsConfiguration {

    @Bean
    InventoryClient inventoryClient(
            RestClient.Builder baseBuilder,
            PartnerAddresses addresses) {

        RestClient restClient = baseBuilder.clone()
            .baseUrl(addresses.inventory())
            .defaultHeader("X-Consumer", "order-service")
            .build();

        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(restClient))
            .build()
            .createClient(InventoryClient.class);
    }

    @Bean
    PricingClient pricingClient(
            RestClient.Builder baseBuilder,
            PartnerAddresses addresses) {

        RestClient restClient = baseBuilder.clone()
            .baseUrl(addresses.pricing())
            .defaultHeader("X-Consumer", "order-service")
            .build();

        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(restClient))
            .build()
            .createClient(PricingClient.class);
    }
}
~~~

**This is an integration snippet**, not a standalone program. PartnerAddresses is an application-defined configuration bean with inventory() and pricing() methods returning URLs; the interfaces/DTOs are from the example above. Clone the builder before each branch because RestClient.Builder is **mutable**. This separates per-host configuration while still inheriting Spring Boot's RestClient.Builder customizers.

**Do not mistakenly declare** two proxy beans sharing a single RestClient with the inventory baseUrl. A proxy may not fail until it is actually invoked; Spring context startup succeeding does not prove routing is right.

### 2.2. Separating Policies per Target Service

A minimal policy checklist to consider per host:

| Setting | Inventory | Pricing | Reason |
| --- | --- | --- | --- |
| Base URL | Inventory config | Pricing config | Avoid calling the wrong host/env |
| Auth | Inventory token/audience | Pricing token/audience | Prevent credential leakage across upstreams |
| Timeout | Per inventory SLA | Per pricing SLA | Services have different latency budgets |
| Retry | Transient GET errors, bounded | Transient GET errors, bounded | Avoid unbounded request amplification |
| Rate limit/concurrency | Per inventory quota | Per pricing quota | Isolate load limits |
| Error mapping | OutOfStock/Unavailable | PriceNotFound/Unavailable | Shield business layer from transport errors |
| Logs/metrics | service=inventory | service=pricing | Pinpoint incidents to the right upstream |

External configuration example:

~~~yaml
partners:
  inventory:
    base-url: https://inventory.example.test
    connect-timeout: 1s
    read-timeout: 2s
  pricing:
    base-url: https://pricing.example.test
    connect-timeout: 1s
    read-timeout: 1s
~~~

This is **application-defined configuration**, not Spring built-in properties that automatically apply timeouts. You need @ConfigurationProperties/binding and must pass these values to the appropriate request factory or WebClient connector. Using one shared variable for both hosts and concatenating paths manually is error-prone when switching environments.

Do not put real URLs, tokens, or secret keys in annotations if they vary across environments; stable resource paths and contract versions can live in annotations, while hosts/auth belong in configuration. If two services use OAuth with different audiences, token caches must also separate scopes/audiences.

### 2.3. What Should Be Shared Is Proxy Creation, Not Rigid Policies

When you have 10 interfaces, you can reuse a small helper to create proxies:

~~~java
public final class HttpClientProxies {
    private HttpClientProxies() {}

    public static <T> T create(RestClient restClient, Class<T> api) {
        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(restClient))
            .build()
            .createClient(api);
    }
}
~~~

A single factory can create multiple interfaces for the same host/configuration if they share an adapter. However, **do not merge independent services into one shared adapter** just to save lines of Java. Each remote service may require different auth, codecs, logging, TLS, HTTP proxies, retries, and tests.

For WebFlux applications, apply the same principle with WebClientAdapter.create(webClient); interfaces return Mono<T>/Flux<T> when the contract supports reactive execution. Do not use Mono<T> with RestClientAdapter expecting the proxy to become non-blocking automatically.

## 3. Managing HTTP Contract Versions as Services Evolve Independently

**API version** differs from the version of the Java library containing the interface and differs from the service's deployment version. A server release may still serve the /v1 API; one application may use Inventory v1 and Pricing v2 simultaneously.

Versioning styles are **dictated by the server contract**, not decided by annotations:
- URL path: /v1/stock/{sku}, /v2/stock/{sku}.
- Media type: Accept: application/vnd.example.inventory.v2+json.
- API-defined header, e.g., X-Api-Version: 2.
- Query parameter if that is the service's convention.

Pick only the **single** convention matching the upstream; do not stack multiple versioning mechanisms thinking it is safer. Changing path/Accept/headers on the client **does not upgrade the server**.

### 3.1. Which Changes Are Potentially Compatible?

Compatibility must be evaluated from the data and expectations of **running consumers**, not just from the provider's perspective.

| Provider-side change | Consumer-side risk | How to evaluate |
| --- | --- | --- |
| Adding an optional field to JSON response | Usually compatible if consumer ignores unknown fields | Test current JSON decoder/DTO |
| Adding a new endpoint | Usually does not affect existing endpoints | Regression-test endpoints in use |
| Adding an optional query parameter with unchanged default | Usually compatible | Verify old requests retain the same meaning |
| Renaming/removing a response field in use | Data loss or parse failure | Breaking unless temporary migration/compatibility exists |
| Changing amount type from number to string | DTO mapping may break or fail parsing | Must test types and semantics |
| Changing amount unit from cents to dollars | Business errors **even when JSON parses cleanly** | Semantically breaking, needs new version/field |
| Making an optional request field required | Old consumers get 4xx | Breaking |
| Changing 404 to 200 with empty body | Error handling behavior changes | Breaking for status-driven logic |
| Shortening TTL or changing timezone/precision | Wrong caching or time comparisons | Review contract obligations |
| Adding a new enum value | Consumers with exhaustive switches may fail | Check unknown-value handling |
| Changing auth/header requirements | Old consumers may get 401/403 | Config migration and rollout |
| Removing /v1 API | Consumers still on /v1 will fail | Only after observing zero remaining traffic |

A **tolerant reader** can ignore new JSON fields, while still constraining core fields. Example price response:

~~~json
{
  "sku": "A-7",
  "amountInCents": 129900,
  "currency": "VND"
}
~~~

If the upstream later adds `"taxIncluded": true`, it usually will not break consumers whose DTOs allow extra fields. However, if the provider renames `amountInCents` to `"price"` and the old field disappears, the consumer could receive null or 0, or even miscalculate prices without validation.

Designing DTOs to prevent silent failures:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record PriceResponse(String sku, Long amountInCents, String currency) {
    public PriceResponse {
        Objects.requireNonNull(sku, "sku required");
        Objects.requireNonNull(amountInCents, "amountInCents required");
        Objects.requireNonNull(currency, "currency required");
        if (amountInCents < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }
    }
}
~~~

This is a model-only snippet once Jackson/java.util.Objects imports are added; it is not a complete program. Using **Long** instead of **long** for required fields catches missing fields instead of silently receiving default 0. The compact constructor validates semantics immediately upon deserialization. @JsonIgnoreProperties(ignoreUnknown = true) must be a **deliberate choice**: strict contracts may require failing on unknown fields.

### 3.2. Separate Wire-Format DTOs from Business Models

The interface defines the **actual remote API data**; a facade translates it into internal models:

~~~java
public record Money(long amountMinorUnits, String currency) {}

public final class PriceFacade {
    private final PricingClient pricing;

    public PriceFacade(PricingClient pricing) {
        this.pricing = pricing;
    }

    public Money priceOf(String sku) {
        PriceResponse wire = pricing.findPrice(sku);
        return new Money(wire.amountInCents(), wire.currency());
    }
}
~~~

This snippet uses PricingClient and PriceResponse above; it is not a standalone program. When an upstream changes its contract, the adapter/DTO/facade layer absorbs the translation while order calculation logic stays decoupled from external JSON.

If currency units change, do not change the meaning of amountInCents on the old class. Create a new DTO (such as PriceV3Response) with explicit mapping, and test monetary amounts before and after migration. The risk of **semantic drift** is often greater than deserialization errors.

### 3.3. Multi-Version Migration

When an upstream wants to retire /v1 in favor of /v2, a common sequence is:

1. Provider publishes the /v2 contract, compatibility policy, and /v1 sunset timeline, and prepares a test environment.
2. Consumer adds v2 interface/DTO alongside v1 (if running in parallel), keeping internal mappings stable.
3. Run contract/integration tests for v2; test unknown fields, nulls, error statuses, auth, and performance limits.
4. Roll out incrementally by cohort/feature flag; log metrics by client version and service to observe before shifting all traffic.
5. Maintain a clear rollback path (switching config/feature flag back to v1 while still served by the provider).
6. Remove the v1 proxy only after real traffic drops to zero and the rollback window ends; only then does the provider retire the old endpoint.

Using a version header can be simpler than creating a new interface when the contract only adds compatible fields. When response shapes and semantics change substantially, two separate interfaces/DTOs are usually easier to review and roll back. **Do not guess API versions from deployment versions**: service version 2.5.1 can still serve API v1.

### 3.4. Note Spring Version Boundaries

In **Spring Framework 6.1**, this lesson uses @Configuration beans with RestClientAdapter/WebClientAdapter and HttpServiceProxyFactory.builderFor(...). This is the straightforward approach supported on the Spring Boot 3.3.x baseline.

Spring Framework **7** adds an HTTP Service Registry and HTTP service groups with @ImportHttpServices to register multiple interface/proxy beans by group. Spring Boot **4** supports configuring corresponding HTTP service groups. **Do not use @ImportHttpServices, HttpServiceProxyRegistry, or `spring.http.client.service.group.*` properties in a Spring 6.1/Boot 3.3 application expecting them to work automatically**. If a project upgrades to Spring 7/Boot 4, you can adopt the new mechanism and migrate independently; grouping design by host/policy still holds.

## 4. Testing the Right Target: Interface, Proxy, HTTP, and Contracts

A fake like:

~~~java
InventoryClient fake = sku -> new StockResponse(sku, true);
~~~

only works **if the interface is actually a functional interface**; this illustrates faking a dependency in business-layer unit tests and checks neither annotations nor HTTP. Nor does it prove the proxy calls the right host and headers.

There are multiple distinct test layers:

| Test layer | What it proves | What it does not prove |
| --- | --- | --- |
| Facade unit test with fake/mock InventoryClient | Orchestration, business calculations, fallbacks | URI/method/header/codec/proxy behavior |
| HTTP proxy test with MockRestServiceServer | @HttpExchange mapping, request headers, query, response JSON, and statuses on RestClient | Real DNS/TLS, HTTP transport/network |
| Integration test with socket-based mock HTTP server (WireMock/OkHttp MockWebServer) | Real HTTP wire path, request serialization, timeouts/connections, and production client setup | Whether the real provider follows the contract |
| Consumer-driven contract/provider verification | Whether the provider meets the consumer's published expectations | Automatically proving all business behavior if contracts are incomplete |
| Staging/E2E against real provider | Actual compatibility of deployed services | Deterministically reproducing every failure mode |

**MockRestServiceServer** replaces RestClient's ClientHttpRequestFactory, making it well suited for fast synchronous proxy tests. With WebClient/reactive, use a WebClient-compatible mock HTTP server to verify actual requests or test the corresponding adapter. When simulating TLS, socket resets, real timeouts, or HTTP proxies, use network/transport tests rather than MockRestServiceServer.

Every proxy should have tests verifying:
- Correct host and URL prefix, method, path variables, and query encoding.
- Correct headers for this service; no leakage of credentials/headers belonging to another service.
- Correct Content-Type/Accept and JSON serialization/deserialization.
- 2xx success, 204 no content, 4xx/5xx, timeouts/transport errors, and rejected requests.
- DTO accepts extra fields if allowed by contract, while missing/semantically changed required fields fail cleanly.
- Separate contract datasets for v1/v2; migration and rollback paths when running in parallel.

## 5. Runnable Java 17 Example: Two Services and Real Proxy Tests

The example below **does not call any public API**. It creates two RestClient/HTTP Service Clients with separate base URLs; uses MockRestServiceServer to assert the actual requests the proxies intend to send, returns mocked JSON, and verifies responses.

Requirements: **Java 17+**, **Maven**, Spring Boot 3.3.13 (Spring Framework 6.1.x). Versions are pinned to keep the example's API consistent, not to imply this is the latest or long-term supported production version.

### 5.1. Project Structure

~~~text
multi-http-client-demo/
├── pom.xml
├── src/main/java/demo/
│   ├── InventoryClient.java
│   ├── PricingClient.java
│   ├── StockResponse.java
│   ├── PriceResponse.java
│   └── ClientProxies.java
└── src/test/java/demo/
    └── ProxyContractTest.java
~~~

### 5.2. Maven Dependencies

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>multi-http-client-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
    </dependencies>
</project>
~~~

starter-web provides RestClient/Jackson for the demo; starter-test provides JUnit 5, spring-test, and MockRestServiceServer. The project does not need a running web server or a Spring ApplicationContext to test the proxies.

### 5.3. Five Source Files

**src/main/java/demo/InventoryClient.java**:

~~~java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(url = "/v1/stock", accept = MediaType.APPLICATION_JSON_VALUE)
public interface InventoryClient {
    @GetExchange("/{sku}")
    StockResponse findStock(@PathVariable("sku") String sku);
}
~~~

**src/main/java/demo/PricingClient.java**:

~~~java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(url = "/v2/prices", accept = MediaType.APPLICATION_JSON_VALUE)
public interface PricingClient {
    @GetExchange("/{sku}")
    PriceResponse findPrice(@PathVariable("sku") String sku);
}
~~~

**src/main/java/demo/StockResponse.java**:

~~~java
package demo;

public record StockResponse(String sku, boolean available) {}
~~~

**src/main/java/demo/PriceResponse.java**:

~~~java
package demo;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.Objects;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PriceResponse(String sku, Long amountInCents, String currency) {
    public PriceResponse {
        Objects.requireNonNull(sku, "sku required");
        Objects.requireNonNull(amountInCents, "amountInCents required");
        Objects.requireNonNull(currency, "currency required");
        if (amountInCents < 0) {
            throw new IllegalArgumentException("amountInCents must be >= 0");
        }
    }
}
~~~

PriceResponse accepts unknown new properties (per the illustrative contract), but rejects missing amountInCents. Checking in the constructor turns bad data into an explicit failure before it reaches price calculations.

**src/main/java/demo/ClientProxies.java**:

~~~java
package demo;

import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

public final class ClientProxies {
    private ClientProxies() {}

    public static <T> T create(RestClient restClient, Class<T> api) {
        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(restClient))
            .build()
            .createClient(api);
    }
}
~~~

### 5.4. Testing with MockRestServiceServer

**src/test/java/demo/ProxyContractTest.java**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.HttpClientErrorException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import org.springframework.http.HttpStatus;

public class ProxyContractTest {

    @Test
    void proxiesRouteToSeparateHostsAndKeepHeadersSeparate() {
        RestClient.Builder inventoryBuilder = RestClient.builder()
            .baseUrl("https://inventory.example.test")
            .defaultHeader("X-Target-Service", "inventory");
        RestClient.Builder pricingBuilder = RestClient.builder()
            .baseUrl("https://pricing.example.test")
            .defaultHeader("X-Target-Service", "pricing");

        // Bind mock servers BEFORE building RestClient instances.
        MockRestServiceServer inventoryServer =
            MockRestServiceServer.bindTo(inventoryBuilder).build();
        MockRestServiceServer pricingServer =
            MockRestServiceServer.bindTo(pricingBuilder).build();

        InventoryClient inventory = ClientProxies.create(
            inventoryBuilder.build(), InventoryClient.class);
        PricingClient pricing = ClientProxies.create(
            pricingBuilder.build(), PricingClient.class);

        inventoryServer.expect(
                requestTo("https://inventory.example.test/v1/stock/A-7"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header("X-Target-Service", "inventory"))
            .andRespond(withSuccess(
                "{\"sku\":\"A-7\",\"available\":true}",
                MediaType.APPLICATION_JSON));

        pricingServer.expect(
                requestTo("https://pricing.example.test/v2/prices/A-7"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header("X-Target-Service", "pricing"))
            .andRespond(withSuccess(
                "{\"sku\":\"A-7\",\"amountInCents\":129900,\"currency\":\"VND\"}",
                MediaType.APPLICATION_JSON));

        assertEquals(new StockResponse("A-7", true),
            inventory.findStock("A-7"));
        assertEquals(new PriceResponse("A-7", 129900L, "VND"),
            pricing.findPrice("A-7"));

        inventoryServer.verify();
        pricingServer.verify();
    }

    @Test
    void newlyAddedResponseFieldIsAccepted() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://pricing.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        PricingClient pricing = ClientProxies.create(
            builder.build(), PricingClient.class);

        server.expect(requestTo(
                "https://pricing.example.test/v2/prices/A-7"))
            .andRespond(withSuccess(
                "{\"sku\":\"A-7\",\"amountInCents\":129900," +
                "\"currency\":\"VND\",\"taxIncluded\":true}",
                MediaType.APPLICATION_JSON));

        assertEquals(129900L,
            pricing.findPrice("A-7").amountInCents());
        server.verify();
    }

    @Test
    void missingRequiredPriceFieldFailsContractValidation() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://pricing.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        PricingClient pricing = ClientProxies.create(
            builder.build(), PricingClient.class);

        server.expect(requestTo(
                "https://pricing.example.test/v2/prices/A-7"))
            .andRespond(withSuccess(
                "{\"sku\":\"A-7\",\"currency\":\"VND\"}",
                MediaType.APPLICATION_JSON));

        assertThrows(RestClientException.class,
            () -> pricing.findPrice("A-7"));
        server.verify();
    }

    @Test
    void missingItemReturnsHttp404ErrorByDefault() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://inventory.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        InventoryClient inventory = ClientProxies.create(
            builder.build(), InventoryClient.class);

        server.expect(requestTo(
                "https://inventory.example.test/v1/stock/UNKNOWN"))
            .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(HttpClientErrorException.NotFound.class,
            () -> inventory.findStock("UNKNOWN"));
        server.verify();
    }
}
~~~

What each test proves:
1. **proxiesRoute...:** creates two independent builders and mock servers; each proxy must hit the right URL, method, and header, then map JSON to its record. Each mock server expects one request, so cross-host calls or skipped requests fail.
2. **newlyAdded...:** the JSON response adds a `taxIncluded` field; `@JsonIgnoreProperties(ignoreUnknown = true)` lets the older reader continue reading the fields it uses. This is **one form of compatibility**, not proof that all changes are safe.
3. **missingRequired...:** the response omits `amountInCents`; the constructor enforces non-null so deserialization fails and is surfaced via a `RestClient` exception. This avoids silently using a zero price.
4. **missingItem...:** 404 under RestClient's default status policy is raised as `HttpClientErrorException.NotFound` rather than becoming an empty `StockResponse`.

Run:

~~~bash
mvn -q test
~~~

JUnit/Surefire runs **four tests**. If all pass, Maven returns **exit code 0**; depending on Maven/IDE, `-q` mode may omit the summary table. Inspect reports in `target/surefire-reports/` to verify test counts and actual statuses. If there is a compile, assertion, or mapping failure, Maven returns a non-zero exit code; do not treat expected output descriptions as proof of execution in your own environment.

**Note:** the example demonstrates Java 17/Spring 6.1 APIs with complete source and test files; `.test` URLs require no real DNS because MockRestServiceServer intercepts requests. Do not swap the mock for a real RestClient pointing at those URLs without a real server. To test actual transport, run WireMock/MockWebServer on localhost and update baseUrl accordingly.

### 5.5. From Proxy Tests to Cross-Service Contract Tests

Proxy tests only simulate the contract **the consumer believes the provider has**. If the mock returns `amountInCents` while the real deployed provider returns `priceInDollars`, consumer tests stay green even though the mock diverges from reality. You must anchor contracts to a shared source or verify the provider against those expectations.

A typical consumer-driven contract workflow (using Pact or a similar tool when needed by the organization):
1. Consumer records the exact requests it sends and minimal responses it requires.
2. Consumer tests run against the contract and produce/publish a versioned contract artifact.
3. Provider runs verification against the consumer artifact to prove endpoints comply.
4. Deployment pipelines check provider versions against active consumer cohorts and release compatible pairs.
5. Add integration tests with a mock HTTP server or real environment to catch differences in transport, auth, TLS, redirects, and operational config.

Beware of "overly strict contracts": if the consumer does not use `taxIncluded`, do not lock the entire JSON response to byte-exact matching. However, you must verify **the exact fields and semantics actually required by business logic**.

## 6. Unit Tests and Integration Tests for Multi-Proxy Configurations

A common mistake is testing individual interfaces with ad-hoc builders created inside tests while production configuration uses the wrong baseUrl or shares an interceptor across two hosts. Therefore, beyond section 5 tests, test the **actual wiring**:

- Create a minimal Spring context containing PartnerClientsConfiguration with distinct `inventory.base-url` and `pricing.base-url` properties.
- Attach independent stub servers to each client config, or run WireMock on two localhost ports.
- Retrieve `InventoryClient` and `PricingClient` from `ApplicationContext`; verify which bean calls which host.
- Send a request carrying credentials meant for inventory; verify that header **does not appear** on requests to pricing.
- Test 404/429/503 policies and timeouts through the actual registered beans, not via separately constructed test RestClients with different settings.
- When toggling version switches or feature flags, test both old/v1 and new/v2 branches; remove the old branch once the rollback window expires.

Distinguish **mock assertions** from **real network execution**. Mock tests are fast, deterministic, and verify mappings; real-socket tests verify timeouts, DNS/proxies, TLS, and wire encoding. With multiple remote dependencies, balance both appropriately instead of turning every unit test into a slow E2E test.

### When Using WebClient/Reactive

WebClientAdapter proxies typically return Mono<T>/Flux<T>. Test the reactive chain with a subscriber, timeouts, backpressure/streaming where applicable, and `retryWhen` scope. With a mock HTTP server on localhost:

~~~java
WebClient webClient = WebClient.builder()
    .baseUrl("http://localhost:8089")
    .build();

PricingReactiveClient client = HttpServiceProxyFactory
    .builderFor(WebClientAdapter.create(webClient))
    .build()
    .createClient(PricingReactiveClient.class);

StepVerifier.create(client.findPrice("A-7"))
    .assertNext(price -> assertEquals("A-7", price.sku()))
    .verifyComplete();
~~~

This is an **integration snippet** and will not run standalone without PricingReactiveClient, a pre-started test server, and the `reactor-test` dependency. Never use `.block()` in WebFlux handlers just for "quick testing"; use StepVerifier in tests, or subscribe/return publishers properly. Re-subscribing multiple times can issue multiple requests; retry tests should count actual request attempts too.

## 7. Common Mistakes When Managing Multiple Services

1. **Two proxies sharing the wrong baseUrl:** method annotations are right, yet requests hit the wrong upstream. Test full URLs, clone builders, and configure per host.
2. **Headers or tokens of service A leaking to B:** sharing interceptors/defaultHeaders without distinguishing targets. Isolate configurations and write negative header tests (credential A absent on request B).
3. **Confusing code version with API version:** releasing application v3 does not mean HTTP endpoint `/v3` exists. Versions must come from the provider contract.
4. **Overly permissive JSON parsing:** ignoring missing required fields and getting primitive default 0 or null that corrupts calculations. Validate DTOs at the boundary.
5. **Overly strict JSON parsing:** rejecting harmless extra fields, causing failures when providers deploy before consumers. Decide tolerance per schema contract.
6. **Adding a version to the interface without checking the server:** code compiles, yet the server may not support the new URL/Accept.
7. **Mocking only the interface in unit tests:** misses wrong path/query/header annotations and serialization bugs. Add proxy tests with HTTP expectations.
8. **Testing proxies only with artificial builders:** production beans may still be misconfigured. Add integration tests for Spring configuration.
9. **Assuming 2xx always carries a DTO:** 204 No Content yields an empty body; the contract must be explicit.
10. **Retrying all POSTs:** a timed-out request does not prove the server did not commit. Require server idempotency and bounded retries.
11. **Stacking retries across multiple layers:** client, gateway, and service all retrying causes exponential attempt amplification; assign clear retry ownership.
12. **Using Spring 7 APIs on Spring 6.1:** `@ImportHttpServices`/group registries do not exist on older classpaths; version-gate and plan upgrades.
13. **Forgetting the v1 sunset deadline:** low-traffic consumers still on v1 break when the provider deletes the API; track metrics by caller/version.
14. **Checking only data types while ignoring semantics:** currency unit changes, timezone shifts, or changed default logic can pass JSON parsing yet break business logic.

## 8. Pre-Release Checklist

### Before Merging a New Client

- `@HttpExchange` interface targets the right method, path, and API version; DTOs, nullability, and status semantics are documented.
- Each remote host has isolated configuration; secrets come from configuration/secret management, never hardcoded.
- Timeouts, retry budgets, and circuit/rate controls match each provider's SLA and capacity.
- Facade unit tests, proxy URI/header/body/codec/status tests, and wiring integration tests match the change scope.
- Provider contract can be verified via contract verification or a real integration environment.

### Before Migrating to a New API Version

- List consumers/deployments still using the old version and how long the provider supports it.
- Write tests with old/new sample payloads, including field/type/semantic changes and error codes.
- Provide rollout and rollback mechanisms while both versions remain active.
- Measure metrics by service, version, status, latency, and retry count; alert on spikes in mapping/4xx/5xx errors.
- Remove the old version **after** traffic and dependent consumers reach zero, not merely after releasing the new version.

## 9. Summary

To manage multiple HTTP Service Clients in Spring, separate **interface contracts**, **per-service client configuration**, **factories/proxies**, and **business facades**. Versioning is a coordinated consumer–provider responsibility; compatibility must consider JSON shape, error codes, and **data semantics**. Proxy tests must execute through a real adapter to verify the HTTP requests generated, supplemented by provider contract verification and transport/wiring integration tests.

On **Spring Framework 6.1 / Boot 3.3**, creating per-configuration RestClient/WebClient and HttpServiceProxyFactory beans is the appropriate pattern. When using **Spring Framework 7 / Boot 4**, you can evaluate the group-based HTTP Service Registry to reduce boilerplate configuration, while still preserving per-service boundaries for auth, versioning, rollback, and testing.

## 10. Official Documentation and Further Reading

- Spring Framework 6.1 API — HttpServiceProxyFactory, builderFor, and createClient: https://docs.spring.io/spring-framework/docs/6.1.7/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html
- Spring Framework 6.1 API — RestClient.Builder (clone/baseUrl/defaultHeader): https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/web/client/RestClient.Builder.html
- Spring Framework 6.1 API — MockRestServiceServer.bindTo(RestClient.Builder): https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html
- Spring Framework Reference — Testing Client Applications: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html
- Spring Framework Reference — HTTP Service Client: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Engineering Blog — HTTP Service Client Enhancements (Spring Framework 7): https://spring.io/blog/2025/09/23/http-service-client-enhancements/
