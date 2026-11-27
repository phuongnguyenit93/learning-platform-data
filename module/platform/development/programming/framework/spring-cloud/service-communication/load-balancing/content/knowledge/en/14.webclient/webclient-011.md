# Testing Load-Balanced Reactive Calls

In microservice architectures, **WebClient** is commonly used for reactive HTTP calls. When combined with **Spring Cloud LoadBalancer**, WebClient can call a logical address such as **http://inventory-service/api/stock/BOOK-01**; the framework fetches the list of **ServiceInstance**s, picks a replica, and replaces the service name with the real host/port before sending the request.

A test that only verifies the returned JSON is correct **is not enough** to prove client-side load balancing works. You need to verify all three things:

1. **Correct reactive flow:** Mono/Flux emits values, errors, completion, or cancellation per contract.
2. **Correct instance selection:** the service ID is resolved, the candidate list is used, and a valid replica is picked.
3. **Correct real HTTP:** the request is sent to the selected host/port preserving method, path, query, and headers; network/HTTP errors are handled properly.

This lesson presents a multi-layered testing strategy, from **StepVerifier + fake ExchangeFunction** to **Spring Boot integration tests with MockWebServer**. It also covers timeouts, retries, empty discovery sources, 4xx/5xx responses, Reactor Context, avoiding blocking, and test stability.

## 1. Understanding the WebClient Flow with Spring Cloud LoadBalancer

~~~mermaid
flowchart TD
    A["OrderService calls WebClient"] --> B["Logical URI: http://inventory-service/..."]
    B --> C["ReactorLoadBalancerExchangeFilterFunction"]
    C --> D["ReactiveLoadBalancer / LoadBalancerClientFactory"]
    D --> E["ServiceInstanceListSupplier"]
    E --> F["Discovery, cache, health, zone, hint"]
    F --> G["Select ServiceInstance"]
    G --> H{"Valid instance exists?"}
    H -->|No| I["Error response / LB-layer error"]
    H -->|Yes| J["Rebuild physical URI"]
    J --> K["HTTP connector sends request"]
    K --> L["Backend returns HTTP response or I/O error"]
    L --> M["WebClient decodes into Mono/Flux"]
    M --> N["StepVerifier verifies signals"]
~~~

In Spring Cloud LoadBalancer, **ReactorLoadBalancerExchangeFilterFunction** is the filter integrating WebClient with **ReactiveLoadBalancer**. It uses the original URI's host as the **service ID**, selects a ServiceInstance, and builds a new request pointing to the real address. **RoundRobinLoadBalancer** is the commonly used default algorithm, though applications can configure another policy.

**Distinguish the two layers clearly:**

- **WebClient** builds requests, executes I/O through a connector, and returns a Publisher (Mono/Flux).
- **Spring Cloud LoadBalancer** chooses an instance. It does not decide the business meaning of JSON, HTTP 404, or whether to retry a POST.

Invoking a method returning **Mono** does not mean a request was sent. With typical cold pipelines, operations run only **upon subscription**. A test that creates a Mono without subscribing or verifying can pass without ever invoking LoadBalancer or the backend.

## 2. Matrix: What to Test at Which Layer?

| Test Goal | Suitable Tool | Runs Real HTTP? | Tests Real LoadBalancer? |
| --- | --- | --- | --- |
| Building requests, path, query, headers | WebClient + fake ExchangeFunction | No | No, unless LB filter is explicitly added |
| JSON-to-DTO decoding, error mapping | ExchangeFunction or mock connector | No | No |
| Mono emits expected values/errors/completion | StepVerifier | Depends on Publisher source | Only if Publisher passes through LB |
| Filtering instance list / selection algorithm | Isolated Supplier/ReactiveLoadBalancer test | No | Yes, at the instance-selection layer |
| Service ID to real host/port | @LoadBalanced WebClient + MockWebServer | Yes | Yes |
| Retry switching instances after failure | LB integration + mock servers + explicit retry | Yes | Yes, if retry is configured |
| Socket timeout / connection reset / TLS | MockWebServer or WireMock | Yes | Yes, if using an LB-equipped client |
| WebFlux controller responds properly | WebTestClient | Possibly not | Not automatically |
| Real discovery/registry | Testcontainers/provider or test environment | Yes | Yes, with full setup |

**WebTestClient** is a tool for testing **HTTP servers/controllers** against their contracts; it can run without a real server. Meanwhile, to test an **outbound load-balanced WebClient**, Spring Framework documentation recommends using a **mock HTTP server** such as OkHttp MockWebServer or WireMock. Two tools having "WebClient" in their names do not share the same purpose.

## 3. Configuring WebClient in a Real Application

Spring Cloud configuration example:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Business client with a simple contract:

~~~java
record StockResponse(String sku, int available, String instanceId) {
}

@Service
class InventoryClient {

    private final WebClient webClient;

    InventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    Mono<StockResponse> getStock(String sku) {
        return webClient.get()
                .uri("/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);
    }
}
~~~

When calling **getStock("BOOK-01")**, LoadBalancer uses the service ID **inventory-service** to look up instances. If **10.0.0.42:8082** is chosen, the real URI becomes **http://10.0.0.42:8082/api/stock/BOOK-01**.

Integration requires:

- Spring WebFlux/WebClient on the classpath, typically via **spring-boot-starter-webflux** in corresponding Spring Boot generations.
- **spring-cloud-starter-loadbalancer** and a compatible Spring Cloud BOM.
- A ServiceInstance source, such as Eureka, Consul, Kubernetes, or SimpleDiscoveryClient.
- The proper **@LoadBalanced WebClient.Builder** or a manually attached integration filter.

**Do not attach the LoadBalancer filter twice.** If WebClient.Builder is already `@LoadBalanced` and Spring Cloud auto-adds the filter, do not also call **.filter(lbFunction)** on that same builder. Double load balancing can cause the resolved physical host to be re-read as a service ID, producing confusing errors.

## 4. Preparing Test Dependencies

Gradle example at the dependency declaration level (pick versions from your actual Spring Boot/Spring Cloud BOM):

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")

    // The example below uses the okhttp3.mockwebserver.* API from OkHttp 4.x.
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}
~~~

The examples use **MockWebServer 4.x** with the **okhttp3.mockwebserver** package. If a project uses OkHttp 5.x, the mock server package/API may differ; update imports and dependencies consistently. MockWebServer is not mandatory: WireMock can also simulate endpoints and network-layer HTTP errors.

In tests, important imports typically include:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.reactive.function.client.WebClient;

import static org.junit.jupiter.api.Assertions.*;
~~~

This is an **illustrative import list**, not a complete Java class. Individual tests may require additional imports for Mono, Flux, ClientResponse, HttpStatus, ExchangeFunction, or Reactor Retry.

## 5. Testing Reactive Signals Before Testing HTTP

**StepVerifier** comes from **reactor-test**. It subscribes and asserts each signal emitted by the Publisher:

- **onNext:** a value is emitted.
- **onComplete:** the stream finishes normally.
- **onError:** the stream terminates with an exception.
- **cancel:** the subscriber stops consuming data; `onComplete` does not necessarily follow.

Example testing a simple Mono:

~~~java
Mono<StockResponse> response =
        Mono.just(new StockResponse("BOOK-01", 7, "inventory-a"));

StepVerifier.create(response)
        .assertNext(stock -> {
            assertEquals("BOOK-01", stock.sku());
            assertEquals(7, stock.available());
            assertEquals("inventory-a", stock.instanceId());
        })
        .verifyComplete();
~~~

Example verifying an error:

~~~java
Mono<StockResponse> response =
        Mono.error(new IllegalStateException("downstream failed"));

StepVerifier.create(response)
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                        && error.getMessage().contains("downstream"))
        .verify();
~~~

**verifyComplete()** asserts the Mono emits the expected value and completes; **expectError...verify()** asserts the stream terminates with an error. These assert the **reactive contract** and do not yet prove a service ID was resolved via LoadBalancer.

### 5.1. Do Not Call `block()` to Test Reactive Code

A test like:

~~~java
StockResponse result = client.getStock("BOOK-01").block();
assertEquals(7, result.available());
~~~

may inspect the value, but it does not cleanly verify signals, cancellation, event counts, or `onError` branches. It also encourages using **block()** in reactive code, which is dangerous on a WebFlux event loop.

StepVerifier also waits on the test thread to verify the stream, yet it is a **test tool**, not a blocking operator put into production pipelines. Always set a verification timeout so tests never hang forever:

~~~java
StepVerifier.create(client.getStock("BOOK-01"))
        .expectNextMatches(stock -> stock.available() >= 0)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
~~~

This is a **test timeout**; it does not configure HTTP response timeouts or deadlines for production WebClient.

## 6. Testing WebClient with a Fake `ExchangeFunction`: Fast, But Insufficient for LB

WebClient lets you replace **ExchangeFunction** with a stub function. This tests serialization/decoding and request construction without opening sockets:

~~~java
AtomicReference<URI> seenUrl = new AtomicReference<>();

ExchangeFunction fakeExchange = request -> {
    seenUrl.set(request.url());
    return Mono.just(ClientResponse.create(HttpStatus.OK)
            .header("Content-Type", "application/json")
            .body("""
                    {"sku":"BOOK-01","available":7,"instanceId":"fake"}
                    """)
            .build());
};

WebClient client = WebClient.builder()
        .baseUrl("http://inventory-service")
        .exchangeFunction(fakeExchange)
        .build();

Mono<StockResponse> result = client.get()
        .uri("/api/stock/{sku}", "BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class);

StepVerifier.create(result)
        .assertNext(stock -> assertEquals(7, stock.available()))
        .verifyComplete();

assertEquals("inventory-service", seenUrl.get().getHost());
assertEquals("/api/stock/BOOK-01", seenUrl.get().getPath());
~~~

Additional imports:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
~~~

**This is not a LoadBalancer test.** The WebClient above has neither `@LoadBalanced` nor `ReactorLoadBalancerExchangeFilterFunction`; the URI seen by the fake exchange still contains the logical host **inventory-service**. The test only proves the request is built properly and JSON decodes into `StockResponse`.

Returning a fake `ClientResponse` immediately from a fake `ExchangeFunction` can mask transport, TLS, connection pooling, or network cancellation bugs. Test at the mock HTTP server layer to verify real integration.

### 6.1. Verifying Status Codes and `onErrorResume`

~~~java
ExchangeFunction fakeError = request -> Mono.just(
        ClientResponse.create(HttpStatus.NOT_FOUND)
                .header("Content-Type", "application/json")
                .body("{\"code\":\"STOCK_NOT_FOUND\"}")
                .build());

WebClient client = WebClient.builder()
        .exchangeFunction(fakeError)
        .build();

Mono<StockResponse> result = client.get()
        .uri("http://inventory-service/api/stock/{sku}", "MISSING")
        .retrieve()
        .bodyToMono(StockResponse.class);

StepVerifier.create(result)
        .expectError(WebClientResponseException.NotFound.class)
        .verify();
~~~

**retrieve()** by default converts 4xx/5xx into **WebClientResponseException**. An **onStatus** or **onErrorResume** branch can translate exceptions into domain results, but test it explicitly to avoid accidentally swallowing infrastructure errors.

## 7. Real Integration Test: `@LoadBalanced` WebClient + Two MockWebServers

This is the most important test: calling **http://inventory-service** in business code while verifying requests actually reach one of two **localhost:port** addresses provided by discovery.

### 7.1. Objective

Setup:

~~~text
Order Service test
    |
    | WebClient GET http://inventory-service/api/stock/BOOK-01
    v
Spring Cloud LoadBalancer
    |-- inventory-a -> localhost:<portA> -> MockWebServer A
    |
    |-- inventory-b -> localhost:<portB> -> MockWebServer B
~~~

Both servers return JSON with distinct `instanceId`s. The test verifies:

1. The result is a `StockResponse` decoded from a real HTTP response.
2. Each request hits a server declared in discovery.
3. Distribution is observable across multiple sequential calls.
4. Path, query, and headers remain intact after rebuilding the URI.
5. No request attempts a DNS lookup of `inventory-service` as a physical host.

### 7.2. A Complete Spring Boot Test

Illustrative example using JUnit Jupiter, Spring Boot Test, and MockWebServer 4.x:

~~~java
@SpringBootTest(
        classes = WebClientLoadBalancerIT.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class WebClientLoadBalancerIT {

    static final MockWebServer A = new MockWebServer();
    static final MockWebServer B = new MockWebServer();

    static {
        try {
            A.start();
            B.start();
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @DynamicPropertySource
    static void discoveryProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.discovery.client.simple.instances.inventory-service[0].uri",
                () -> A.url("/").toString());
        registry.add(
                "spring.cloud.discovery.client.simple.instances.inventory-service[1].uri",
                () -> B.url("/").toString());

        // Keep test focused on instance selection without implicit retries.
        registry.add("spring.cloud.loadbalancer.retry.enabled", () -> "false");
    }

    @Autowired
    @LoadBalanced
    WebClient.Builder loadBalancedBuilder;

    @Test
    void sendsRequestsToBothDiscoveredInstances() throws Exception {
        // Enough responses so the test does not depend on which server is chosen first.
        for (int i = 0; i < 8; i++) {
            A.enqueue(new MockResponse()
                    .setHeader("Content-Type", "application/json")
                    .setBody("""
                            {"sku":"BOOK-01","available":7,"instanceId":"a"}
                            """));
            B.enqueue(new MockResponse()
                    .setHeader("Content-Type", "application/json")
                    .setBody("""
                            {"sku":"BOOK-01","available":9,"instanceId":"b"}
                            """));
        }

        WebClient client = loadBalancedBuilder
                .baseUrl("http://inventory-service")
                .build();

        Set<String> observed = new HashSet<>();

        // Call sequentially: avoid assuming execution order under concurrency.
        for (int i = 0; i < 6; i++) {
            Mono<StockResponse> call = client.get()
                    .uri("/api/stock/{sku}?warehouse={wh}", "BOOK-01", "HCM")
                    .header("X-Correlation-Id", "test-123")
                    .retrieve()
                    .bodyToMono(StockResponse.class);

            StepVerifier.create(call)
                    .assertNext(stock -> {
                        assertEquals("BOOK-01", stock.sku());
                        assertTrue(Set.of("a", "b").contains(stock.instanceId()));
                        observed.add(stock.instanceId());
                    })
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        }

        assertEquals(Set.of("a", "b"), observed);
        assertEquals(6, A.getRequestCount() + B.getRequestCount());

        RecordedRequest requestA =
                A.takeRequest(1, TimeUnit.SECONDS);
        RecordedRequest requestB =
                B.takeRequest(1, TimeUnit.SECONDS);

        assertNotNull(requestA);
        assertNotNull(requestB);
        assertEquals("/api/stock/BOOK-01?warehouse=HCM", requestA.getPath());
        assertEquals("/api/stock/BOOK-01?warehouse=HCM", requestB.getPath());
        assertEquals("test-123", requestA.getHeader("X-Correlation-Id"));
        assertEquals("test-123", requestB.getHeader("X-Correlation-Id"));
    }

    @AfterAll
    static void stopServers() throws IOException {
        A.shutdown();
        B.shutdown();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
        @Bean
        @LoadBalanced
        WebClient.Builder loadBalancedWebClientBuilder() {
            return WebClient.builder();
        }
    }
}
~~~

Additional imports for the test class:

~~~java
import java.io.IOException;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
~~~

**Verification scope:** the example is designed to run with a compatible Spring Boot/Spring Cloud BOM containing both LoadBalancer auto-configuration and SimpleDiscoveryClient. Within the scope of a Knowledge article, the example has not been compiled/run in a repository; when applying it in practice, add imports, verify dependency versions, and run tests via your project build.

### 7.3. Why Start MockWebServer in a Static Initializer?

**@DynamicPropertySource** is processed by Spring while constructing the ApplicationContext, before standard `@BeforeAll` methods might set up resources in your expected order. Starting servers before the registry reads URIs ensures `getPort()`/`url()` are already available.

In complex suites, use a JUnit extension, Testcontainers, or an equivalent lifecycle manager. Ensure servers shut down after tests and dynamic ports are not stalely reused across Spring Test context caching.

### 7.4. Why Not Assert the First Request Definitely Goes to A?

`RoundRobinLoadBalancer` maintains an initial position counter; the starting position might not begin at A. Across an application with multiple tests or multiple selections, request order also depends on counter state, concurrency, and supplier filters.

The example above only requires:

- Both instances are observed over multiple **sequential** requests.
- Total request count matches subscription count.
- Each real server receives the expected path and headers.

To assert **A → B → A → B**, use a LoadBalancer with a fixed seed, a supplier returning a fixed list, no cache/health updates, and no concurrent requests. Only assert exact ordering when that exact order is the test's contract.

## 8. Testing the Discovery Boundary and `ServiceInstanceListSupplier`

In integration tests, **SimpleDiscoveryClient** is a static data source; it can supply two ServiceInstances without a real Eureka/Consul server. Yet when investigating selection algorithms, an isolated unit test for the supplier remains helpful:

~~~java
ServiceInstance a = new DefaultServiceInstance(
        "inventory-a", "inventory-service", "localhost", 8081, false);
ServiceInstance b = new DefaultServiceInstance(
        "inventory-b", "inventory-service", "localhost", 8082, false);

ServiceInstanceListSupplier supplier = new ServiceInstanceListSupplier() {
    @Override
    public String getServiceId() {
        return "inventory-service";
    }

    @Override
    public Flux<List<ServiceInstance>> get() {
        return Flux.just(List.of(a, b));
    }
};

StepVerifier.create(supplier.get().next())
        .assertNext(instances -> {
            assertEquals(2, instances.size());
            assertEquals("inventory-a", instances.get(0).getInstanceId());
            assertEquals("inventory-b", instances.get(1).getInstanceId());
        })
        .verifyComplete();
~~~

Required imports:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
~~~

**What this test proves:** the supplier returns a fixed list in the declared order. It **does not prove** RoundRobinLoadBalancer picked A/B or `ReactorLoadBalancerExchangeFilterFunction` rebuilt the URI. To test the algorithm, pass that supplier to a real LoadBalancer and verify **choose(Request)**; to test HTTP, continue using MockWebServer.

### 8.1. When Is a Custom Supplier Needed in Tests?

Tests with real discovery can be affected by registration state, cache TTL, or health checks. To reproduce edge cases such as only one instance left, zero instances, zone mismatch, or retry avoiding the previous instance, create a **stub supplier** returning a test-controlled list.

Pay attention to where the supplier is registered: Spring Cloud creates a separate child context per **service ID**. A custom configuration for `inventory-service` should be registered with **@LoadBalancerClient(name = "inventory-service", configuration = ...)**, keeping the supplier configuration class excluded from global component scanning.

Example per-service configuration:

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
class OrderApplication {
}

class InventoryLoadBalancerConfiguration {
    @Bean
    ServiceInstanceListSupplier supplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

The example above uses **blocking DiscoveryClient** for compatibility with SimpleDiscoveryClient; instance selection on WebClient still runs via `ReactiveLoadBalancer`. If the provider has a **ReactiveDiscoveryClient**, use **withDiscoveryClient()** instead of `withBlockingDiscoveryClient()`. Do not assume a static source automatically supports reactive discovery or auto-updates health.

## 9. Testing the No-Instance Scenario

If a request uses **http://missing-inventory-service/...** while discovery returns no instances for that service ID, LoadBalancer has no valid physical URI to connect to.

A test scenario should verify:

1. No `ServiceInstance` is returned for the test service ID.
2. Zero requests hit MockWebServer A/B.
3. The Mono terminates with an error or error response matching the active adapter.
4. Logs/metrics suffice to distinguish instance-selection failures from backend 503 responses.

Example test under **common default Spring Cloud LoadBalancer configuration**:

~~~java
Mono<String> call = loadBalancedBuilder.build()
        .get()
        .uri("http://service-that-does-not-exist/api/stock")
        .retrieve()
        .bodyToMono(String.class);

StepVerifier.create(call)
        .expectErrorSatisfies(error -> {
            assertInstanceOf(WebClientResponseException.class, error);
            WebClientResponseException httpError =
                    (WebClientResponseException) error;
            assertEquals(503, httpError.getStatusCode().value());
        })
        .verify(Duration.ofSeconds(5));
~~~

**Important caveat:** in many reactive integration versions, when no instances exist, the LoadBalancer filter generates an internal **HTTP 503 Service Unavailable**, which `retrieve()` turns into `WebClientResponseException`. However, behavior can be configured to use HTTP 404 or differ across adapters/release trains. Never hardcode 503 across every product: verify the exact contract of your running version and configuration.

If the test above fails with **UnknownHostException** attempting to DNS-resolve `service-that-does-not-exist`, first inspect the **@LoadBalanced builder/filter**. That is not necessarily an empty discovery issue; WebClient may lack LoadBalancer integration.

If the application has another filter translating errors, assert the **domain exception** at the adapter layer and separately test HTTP statuses at the integration layer.

## 10. Separating HTTP 4xx/5xx from Transport Errors

WebClient **retrieve()** by default converts HTTP 4xx/5xx statuses into **WebClientResponseException**. These are errors **with an HTTP response**. Network/connect/read errors may be wrapped in **WebClientRequestException**, alongside timeout errors emitted by Reactor operators.

| Scenario | Typical Signal Shape | Real HTTP Response? |
| --- | --- | --- |
| Backend returns 200 JSON | `onNext(StockResponse)`, `onComplete` | Yes |
| Backend returns 204 | `bodyToMono` may complete empty | Yes |
| Backend returns 404 | `WebClientResponseException.NotFound` | Yes |
| Backend returns 503 | `WebClientResponseException.ServiceUnavailable` | Yes |
| DNS/connection refused/TLS | `WebClientRequestException`, I/O root cause | No |
| `.timeout(...)` operator expired | `TimeoutException` from Reactor | Not necessarily |
| 200 response with unparseable JSON | `DecodingException` or codec exception | Yes |
| No `ServiceInstance` left | Error/response from LB filter | Possibly no network call yet |

Example with a **MockWebServer dedicated to testing 404**, enqueue:

~~~java
server.enqueue(new MockResponse()
        .setResponseCode(404)
        .setHeader("Content-Type", "application/json")
        .setBody("{\"code\":\"STOCK_NOT_FOUND\"}"));
~~~

Then:

~~~java
StepVerifier.create(inventoryClient.getStock("MISSING"))
        .expectErrorMatches(error ->
                error instanceof WebClientResponseException.NotFound)
        .verify(Duration.ofSeconds(5));
~~~

Conditions: the test fixture uses a supplier **having only an instance pointing to that server**, has no custom filter mapping 404 to a domain exception, and has no automatic retries hiding the first response. Each test must initialize/reset an independent response queue.

### 10.1. When Using `onStatus()` or `onErrorResume()`

The application may map HTTP 404 to a domain error:

~~~java
Mono<StockResponse> call = webClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> Mono.just(new StockNotFoundException(sku)))
        .bodyToMono(StockResponse.class);

StepVerifier.create(call)
        .expectError(StockNotFoundException.class)
        .verify(Duration.ofSeconds(5));
~~~

`StockNotFoundException` is an application-defined exception. If instead using:

~~~java
Mono<Optional<StockResponse>> result = webClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class)
        .map(Optional::of)
        .onErrorResume(WebClientResponseException.NotFound.class,
                ex -> Mono.just(Optional.empty()));
~~~

then `StepVerifier` must **expectNext(Optional.empty())** followed by `verifyComplete()`, no longer `expectError(NotFound)`. Only convert 404 to empty when the endpoint contract genuinely allows it; never swallow 404 errors caused by wrong paths or gateways.

## 11. Testing HTTP Timeouts in Two Distinct Ways

**HTTP timeouts** and **Reactor timeout operators** can both fail a Mono, yet **they are not the same mechanism**:

1. **Connector response timeout:** e.g., Reactor Netty configured via `HttpClient.responseTimeout()`; the filter/connector may report `WebClientRequestException` with a Netty/network cause.
2. **Mono.timeout(Duration):** if the publisher fails to emit on time, Reactor generates `TimeoutException` at the operator level regardless of TCP connection state.

### 11.1. Testing `Mono.timeout` with a Slow Server

MockWebServer 4.x can delay the body:

~~~java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setHeader("Content-Type", "application/json")
        .setBody("{\"sku\":\"BOOK-01\",\"available\":7}")
        .setBodyDelay(2, TimeUnit.SECONDS));
~~~

WebClient uses a supplier pointing only to **server**. Test:

~~~java
Mono<StockResponse> call = webClient.get()
        .uri("http://inventory-service/api/stock/BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class)
        .timeout(Duration.ofMillis(250));

StepVerifier.create(call)
        .expectError(java.util.concurrent.TimeoutException.class)
        .verify(Duration.ofSeconds(3));
~~~

Assuming the server received the request but did not finish sending the body within 250 ms. This tests a **Reactor-layer deadline**, not proof of the HTTP engine's connect timeout.

Set timeouts far enough away from Spring context startup jitter and TCP handshakes; setting 1 ms can fail the test before the request even reaches the server, losing verification value.

### 11.2. Testing Reactor Netty's Response Timeout

Connector configuration example:

~~~java
HttpClient netty = HttpClient.create()
        .responseTimeout(Duration.ofMillis(300));

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(netty))
        .build();
~~~

In a similar slow HTTP server fixture, the test should verify:

- A request actually reached the server.
- The connector terminated within the configured budget.
- The exception belongs to the request/transport category and preserves the relevant cause.

Do not hardcode assertions against a single Netty subclass across Reactor Netty/HTTP engine versions. Test assertions should distinguish **receiving an HTTP response** from **I/O/timeout errors before response completion**.

Imports: **reactor.netty.http.client.HttpClient** and **org.springframework.http.client.reactive.ReactorClientHttpConnector**. In production, configure connect, response, pool acquisition, and overall deadlines consistently.

## 12. Reactive Retries: Verify Actual Call Counts

Spring Cloud LoadBalancer has a per-service-instance retry mechanism, while Reactor provides **retryWhen(Retry...)** to retry a Publisher. Both mechanisms can compound and produce more requests than expected.

For a test focused solely on **Reactor-layer** retries, disable Spring Cloud LoadBalancer's automatic retry:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
~~~

Then simulate a server returning 503 followed by 200 on the next call:

~~~java
server.enqueue(new MockResponse()
        .setResponseCode(503)
        .setBody("temporarily unavailable"));

server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setHeader("Content-Type", "application/json")
        .setBody("""
                {"sku":"BOOK-01","available":7,"instanceId":"a"}
                """));
~~~

Client:

~~~java
Mono<StockResponse> result = webClient.get()
        .uri("http://inventory-service/api/stock/BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class)
        .retryWhen(Retry.max(1)
                .filter(error ->
                        error instanceof WebClientResponseException ex
                                && ex.getStatusCode().value() == 503));

StepVerifier.create(result)
        .assertNext(stock -> assertEquals(7, stock.available()))
        .verifyComplete();

assertEquals(2, server.getRequestCount());
~~~

Conditions: the test's supplier points to **one** MockWebServer; no proxy/server retries are enabled, and no other interceptor resends requests. With two instances, **Reactor retry can trigger instance selection again**, yet asserting an instance switch from A to B requires fixing selection seeds/policies and controlling the candidate list.

### 12.1. Do Not Retry Every Error

The filter condition in the example accepts only HTTP 503. Do not retry:

- HTTP 400/422 caused by invalid requests.
- HTTP 401/403 caused by authorization failures.
- 404 when the resource genuinely does not exist.
- JSON decode errors caused by incompatible contracts.

429 errors can be retried when paired with `Retry-After` handling. Timeouts and 503s can be retried for **safe/idempotent** requests within a bounded budget; for POSTs creating resources or processing payments, require backend-enforced idempotency keys.

### 12.2. When Retries Belong to Spring Cloud LoadBalancer

If the requirement is **testing a retry policy that picks a different instance**, do not only test the `retryWhen` operator. Use an integration fixture with two servers and the appropriate LoadBalancer retry policy:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 503
~~~

Properties can vary across release trains; current Spring Cloud LoadBalancer also includes avoid-previous-instance and backoff settings. Verify the actual retry dependency on the classpath, the auto-configured filter type, and which HTTP methods apply. Do not assume adding the YAML above guarantees a 503 will always retry onto B.

Tests must directly inspect **RecordedRequest** on each server. Only when both A and B receive a request and total attempts equal 2 do you have proof that retry switched instances. Seeing two responses on A alone proves retries occurred, not **load-balancer retry-to-next-instance**.

## 13. Virtual Time for Retries/Delays: Never Simulate TCP with Virtual Clocks

Reactor **StepVerifier.withVirtualTime** is very useful for unit-testing operators like `delayElements()`, `timeout()`, `Retry.fixedDelay()`, or `Retry.backoff()` when they use Reactor-managed schedulers.

The example below **uses no network**; it tests retry with a one-second interval using a virtual clock:

~~~java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
                    int n = attempts.incrementAndGet();
                    return n < 3
                            ? Mono.<String>error(
                                    new IllegalStateException("temporary"))
                            : Mono.just("ok");
                })
                .retryWhen(Retry.fixedDelay(
                                2, Duration.ofSeconds(1))
                        .filter(ex ->
                                ex instanceof IllegalStateException)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectNext("ok")
        .verifyComplete();

assertEquals(3, attempts.get());
~~~

**withVirtualTime takes a Supplier so the Publisher is created after the virtual scheduler is installed.** Pre-creating a Mono with a timer and passing an existing reference can bind the timer to the real scheduler, causing tests to hang or run slowly.

Important limits:

- Virtual time only controls Reactor schedulers participating in the substitution mechanism.
- It does not speed up **MockWebServer**, TCP sockets, DNS, or Reactor Netty response timeouts.
- For pipelines with multiple custom schedulers or continuous emission models, design tests carefully to prevent deadlocks.
- If the target is HTTP transport, use a real mock server with real timeouts and accept a small but stable test time budget.

## 14. Cancellation and Cleanup in Reactive Pipelines

When a user closes an inbound connection, upstream times out, or a subscriber cancels, WebClient can receive cancellation. Tests must confirm the pipeline stops waiting and releases resources according to connector capabilities.

An isolated unit test using a fake `ExchangeFunction`:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

ExchangeFunction neverResponding = request ->
        Mono.<ClientResponse>never()
                .doOnCancel(() -> cancelled.set(true));

WebClient client = WebClient.builder()
        .exchangeFunction(neverResponding)
        .build();

Mono<String> call = client.get()
        .uri("http://inventory-service/slow")
        .retrieve()
        .bodyToMono(String.class);

StepVerifier.create(call)
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(2));

assertTrue(cancelled.get());
~~~

This tests **cancellation propagation inside a fake Publisher**. It does not prove real sockets closed immediately, the Netty pool released connections, or the backend stopped processing work. To test real I/O, configure a slow MockWebServer and observe the client connector, connection counts, and resource cleanup.

**Do not use `block()` to simulate cancellation of a reactive HTTP client.** Use `StepVerifier` and `doOnCancel`/`doFinally` hooks at the appropriate Publisher layer; avoid turning test hooks into shared production logic.

## 15. Context Propagation and Per-Request Headers

**Reactor Context** is per-subscription context, distinct from `ThreadLocal`. With WebClient, Context can carry trace/tenant IDs to a filter and translate them into HTTP headers when required by the contract.

Filter example:

~~~java
ExchangeFilterFunction traceFilter = (request, next) ->
        Mono.deferContextual(context -> {
            String traceId =
                    context.getOrDefault("traceId", "unknown");

            ClientRequest withTrace = ClientRequest.from(request)
                    .header("X-Trace-Id", traceId)
                    .build();

            return next.exchange(withTrace);
        });
~~~

At the call site:

~~~java
Mono<StockResponse> call = webClient.get()
        .uri("http://inventory-service/api/stock/BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class)
        .contextWrite(Context.of("traceId", "trace-123"));
~~~

**Context.of** lives in `reactor.util.context.Context`. With MockWebServer, assert the header **X-Trace-Id: trace-123** via `RecordedRequest`. Also test two independent subscriptions with different `traceId`s to verify there is no cross-request leakage.

Notes:

- Reactor Context **does not automatically become HTTP headers**. A filter or observability framework must perform propagation.
- Never rely on plain `ThreadLocal` to carry tenant/trace IDs across reactive schedulers; values can disappear on thread switches.
- Never automatically inject `Authorization` or sensitive tokens into headers merely because they exist in Context; enforce security policies.
- For hint/sticky-header load balancing, verify **filter ordering** and how Spring Cloud forwards request context to relevant `ServiceInstanceListSupplier`s.

If the application already uses Micrometer Tracing, prefer standard context propagation instead of hand-rolling custom trace headers for production. The snippet above illustrates the test point.

## 16. Concurrent Testing: Assert Correctness, Not Rigid Round-Robin Positions

WebClient supports many concurrent in-flight calls. A simple pattern:

~~~java
Flux<StockResponse> calls = Flux.range(0, 40)
        .flatMap(index ->
                webClient.get()
                        .uri("http://inventory-service/api/stock/{sku}",
                                "BOOK-01")
                        .retrieve()
                        .bodyToMono(StockResponse.class),
                8);

StepVerifier.create(calls.collectList())
        .assertNext(responses -> {
            assertEquals(40, responses.size());
            assertTrue(responses.stream().allMatch(
                    r -> Set.of("a", "b").contains(r.instanceId())));
        })
        .verifyComplete();
~~~

For this test to run, **each MockWebServer needs enough queued responses** or a dispatcher returning responses per request; if a queue runs dry, the test can hang or receive unexpected responses. Set a test deadline and ensure fixtures reset state between tests.

With **flatMap**, output element order **is not guaranteed to match index order**. Do not assert exact A, B, A, B ordering under concurrent requests. Instead:

- Verify total result count and request correctness.
- Verify every response came from a valid instance.
- Ensure no lost, duplicated, or mismatched data by request ID.
- When verifying distribution, use many requests and reasonable statistical thresholds; never demand an exact 50/50 split.

If the contract requires **response order matching input order**, use `concatMap` or `flatMapSequential` as appropriate, then check concurrency/latency impact. That is a Reactor operator property, not a guarantee provided by LoadBalancer.

## 17. Testing Streaming with `bodyToFlux()`

Not every downstream returns a single JSON object and closes the response. With NDJSON or Server-Sent Events, WebClient can return **Flux<T>** and emit elements as data arrives.

Business example:

~~~java
Flux<InventoryEvent> events = webClient.get()
        .uri("http://inventory-service/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(InventoryEvent.class);
~~~

In tests, instead of forcing everything into a `List`, verify two items and cancel:

~~~java
StepVerifier.create(events)
        .assertNext(event ->
                assertEquals("RESERVED", event.type()))
        .assertNext(event ->
                assertEquals("RELEASED", event.type()))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Simulate the exact **Content-Type** and framing of the stream protocol. For SSE, the mock server sends:

~~~text
data: {"type":"RESERVED"}

data: {"type":"RELEASED"}

~~~

Each event ends with a blank line; the HTTP response has Content-Type **text/event-stream**. For NDJSON, use the matching Content-Type and one JSON object per line.

This tests **stream decoding and cancellation**. To test **backpressure**, write unit tests with `TestPublisher` or a `Flux` source controlling demand requests; TCP streaming and HTTP connectors buffer data, so backpressure cannot be fully inferred solely from received item counts.

## 18. Testing Zone, Hint, Health, and Retry in the Supplier Chain

Spring Cloud LoadBalancer can use **ZonePreferenceServiceInstanceListSupplier**, **HintBasedServiceInstanceListSupplier**, **HealthCheckServiceInstanceListSupplier**, or retry-aware decorators. Once WebClient is integrated properly, the final list determines which instances HTTP requests can reach.

Example metadata:

| Instance | zone | hint | Simulated Health |
| --- | --- | --- | --- |
| A | zone-a | stable | UP |
| B | zone-b | canary | UP |
| C | zone-a | canary | DOWN |

Scenarios to verify:

| Scenario | Setup | Core Assertion |
| --- | --- | --- |
| Local zone | Client zone-a, A/C in list | Only same-zone instances remain candidates when matches exist |
| No zone match | Caller zone-c | ZonePreference falls back to delegate list |
| Hint canary | Header `X-SC-LB-Hint=canary` | Exact candidate set per hint metadata and decorator order |
| Health C DOWN | Health supplier excludes C | Requests avoid C once health state updates |
| No healthy same-zone instances | Health before Zone | Zone can fall back to B |
| Retry A failure | Retry-aware enabled and B is candidate | If config allows, tries another instance |
| Cache TTL not expired | Instance removed from registry while cache stale | May still select old instance temporarily |

**Never use randomly changing discovery data** to assert these scenarios. Unit tests should supply fixed snapshots so each decorator's exact input list is known. Integration tests then verify whether the policy affected URIs sent to servers.

In particular, **HealthCheckServiceInstanceListSupplier** uses a scheduler and updates results asynchronously. When testing health, wait until the list stabilizes or use an explicit synchronization condition rather than `sleep(100)` and assuming health updated.

## 19. Mistakes That Make Load-Balanced Reactive Tests Flaky

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Test builds Mono and finishes | No subscription | Use `StepVerifier.verify`/`verifyComplete` |
| WebClient tries DNS lookup for service ID | Not using `@LoadBalanced` builder | Check bean, starter, and filter |
| Real host treated as service ID | Double load-balancing filter | Choose only one LB integration approach |
| Test sees no server receive requests | Empty supplier, misconfigured context, Mono unsubscribed | Check discovery fixture and `StepVerifier` signals |
| Always hits instance A | Only one instance left after filters, cache/zone/hint, or prior test changed config | Print output list and metadata |
| A/B order changes across runs | Round-robin seed, concurrency, or shared context | Assert membership/counts; never hardcode first turn |
| Timeout occurs before server receives request | Operator timeout too short | Separate startup time from request deadline; raise test budget |
| Test hangs forever | MockWebServer queue exhausted or `StepVerifier` missing `verify` | Queue enough responses + `verify` timeout |
| Unexpected 503 response | LB had no instances or real server returned 503 | Check request count and trace/lifecycle |
| `onErrorResume` swallows 5xx too | Overly broad exception filter | Translate only contract-defined error types |
| Retries fire unexpectedly many times | Both Spring LB retry and Reactor retry enabled | Audit both layers; count `RecordedRequest`s |
| Virtual time does not speed up | Timer built before `withVirtualTime` or real TCP timeout | Construct publisher lazily and separate network tests |
| Test context leaks across cases | Shared MockWebServer queue/counter or Spring context cache | Reset fixtures; isolate properties/service IDs |
| Server DOWN yet still selected | Static `SimpleDiscoveryClient` or stale cache/health | Test discovery/health separately; do not blame WebClient |
| Missing header from Reactor Context | Missing propagation filter or wrong filter order | Assert `RecordedRequest` and `contextWrite` |

### 19.1. Ensuring Test Isolation

Follow these rules:

1. **Never use fixed ports** like 8081/8082 in parallel tests; use MockWebServer dynamic ports.
2. Give each test an explicit response queue independent of JUnit execution order.
3. Never share LoadBalancer Round-Robin state across tests expecting a fixed first turn.
4. Isolate service ID/metadata configurations when testing zones, hints, or retries.
5. Avoid `Thread.sleep` to wait for schedulers; use `StepVerifier`, await conditions, or virtual time as appropriate.
6. Bound `verify()` durations and network requests.
7. Count requests on the real server, not just by reading response bodies.
8. For debugging, temporarily capture service ID, instance ID, status, and trace ID logs; never log tokens or sensitive raw payloads.

## 20. Diagnostic Workflow for a Failing Test

When the client does not return the expected result, trace from outside in:

~~~text
1. Has the Publisher been subscribed to?
   |
2. Does WebClient.Builder have @LoadBalanced / the right filter?
   |
3. Does the logical URI have the right service ID as host?
   |
4. Which instances does ServiceInstanceListSupplier return?
   |
5. Which instanceId/host/port does LoadBalancer choose?
   |
6. Which MockWebServer actually received the request?
   |
7. Are path, query, headers, and method on the server correct?
   |
8. What HTTP status/body did the server return?
   |
9. How did WebClient emit onNext/onError/onComplete?
   |
10. Did retry/timeout/filters alter the result or resend the request?
~~~

At each layer, record safe diagnostic info:

~~~text
testId=lb-reactive-01
serviceId=inventory-service
instanceId=inventory-b
method=GET
pathTemplate=/api/stock/{sku}
status=200
attempt=1
durationMs=23
~~~

This is a **desired log format**, not default Spring Cloud metric names. To observe `instanceId`, use `LoadBalancerLifecycle`, server-side logs, or tracing/observability hooks. Never infer `instanceId` from responses unless it is trustworthy test data.

## 21. Minimal Test Suite Before CI

| Test ID | Objective | Tool | Passes When |
| --- | --- | --- | --- |
| WC-01 | JSON -> DTO | Fake ExchangeFunction | Mono emits expected DTO and completes |
| WC-02 | HTTP 404 | Mock exchange/server | `onError(NotFound)` or domain result per contract |
| WC-03 | Service ID -> real instance | `@LoadBalanced` + 2 MockWebServers | Requests hit discovery-declared ports |
| WC-04 | Path, query, headers | MockWebServer `RecordedRequest` | Request parts remain intact |
| WC-05 | No instances | Spring Cloud context with empty supplier | Error from LB; zero requests sent to backends |
| WC-06 | Backend returns 503 | Single-instance server | HTTP error distinguished from no-instance error |
| WC-07 | Transport timeout | Slow MockWebServer + connector timeout | Correct request/transport error emitted |
| WC-08 | Deadline timeout | `Mono.timeout` | `TimeoutException` emitted within budget |
| WC-09 | Exact retry count | 503 then 200 | Total `RecordedRequest`s match attempts |
| WC-10 | Retry picks another instance | Two servers + deterministic selection policy | Each attempt hits its expected instance |
| WC-11 | Cancellation | Fake ExchangeFunction + StepVerifier | Cancel hook invoked |
| WC-12 | Context propagation | Reactor Context + filter + MockWebServer | Correct header per subscription |
| WC-13 | Concurrent requests | Bounded-concurrency `flatMap` | Zero lost/duplicated requests; valid responses |
| WC-14 | Streaming | SSE/NDJSON mock response | `bodyToFlux` receives events and supports cancellation |

**Tiering in CI:** run fast, socketless unit tests on every commit; run MockWebServer integration tests in standard builds; run real discovery provider tests or chaos/network-fault tests in dedicated pipelines when infrastructure allows.

Do not benchmark production performance from fake `ExchangeFunction` test timings. To measure latency/throughput, use dedicated benchmarks and production-like environments isolating JVM warm-up, network, connection pools, zone routing, and retries.

## 22. Pre-Completion Checklist

- [ ] WebClient uses **@LoadBalanced WebClient.Builder** or an integration filter attached exactly once.
- [ ] Logical URIs use the service ID as host without hardcoding backend ports.
- [ ] Mono/Flux tests are always subscribed via `StepVerifier` or an appropriate subscriber.
- [ ] Unit tests using fake `ExchangeFunction` only validate request/response mapping, without claiming LB ran.
- [ ] Integration tests use two MockWebServers or other mock backends on dynamic ports.
- [ ] Discovery data or `ServiceInstanceListSupplier` is controlled and reproducible.
- [ ] Actual received requests are verified via `RecordedRequest`: method, path, query, headers.
- [ ] First-turn Round-Robin order is not asserted unless seed/state is fixed.
- [ ] Tests cover no-instance, HTTP 404/503, transport failures, and JSON decode failures.
- [ ] Reactor deadlines are kept distinct from HTTP connector response timeouts.
- [ ] Virtual time is used only for Reactor schedulers, not to simulate real sockets.
- [ ] Retries in Reactor and Spring Cloud LoadBalancer are configured and attempts counted explicitly.
- [ ] Requests with side effects are retried only with idempotency contracts.
- [ ] Cancellation, Context propagation, and concurrent access are tested where applicable.
- [ ] Mock server queues, timers, and Spring contexts are isolated across tests.
- [ ] Tests have explicit timeouts and do not rely on arbitrary sleeps.
- [ ] Logs/metrics never expose tokens, cookies, or sensitive payloads.

## 23. Conclusion

**Testing load-balanced reactive WebClient calls requires verifying both Publisher signals and real `ServiceInstance` selection plus HTTP I/O.** `StepVerifier` excels at checking `onNext`, `onError`, `onComplete`, and cancellation; fake `ExchangeFunction`s rapidly validate request building and deserialization; yet **only integration tests with `@LoadBalanced` WebClient and real mock HTTP servers prove the service ID resolved to the selected instance's host and port**.

With Spring Cloud LoadBalancer, control `ServiceInstanceListSupplier` inputs, avoid attaching the LoadBalancer filter twice, separate no-instance errors from HTTP or transport errors, and count requests under retries. Using **mock servers, explicit timeouts, virtual time for its proper purpose, and assertions independent of arbitrary execution order** yields accurate, fast, and non-flaky tests.

## 24. References

- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ReactiveLoadBalancer`, `RoundRobinLoadBalancer`, `ServiceInstanceListSupplier`, retries, health, hints, and WebClient integration.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): using `@LoadBalanced WebClient.Builder` and `ReactorLoadBalancerExchangeFilterFunction`.
- [Spring Framework – WebClient Testing](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): recommending mock web servers like OkHttp MockWebServer/WireMock for testing HTTP clients.
- [Spring Framework – WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): `bodyToMono`, `bodyToFlux`, default HTTP 4xx/5xx mapping, and `onStatus`.
- [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing HTTP servers/controllers and distinguishing from outbound WebClient testing.
- [Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, `TestPublisher`, `PublisherProbe`, and virtual time.
- [Reactor Test – StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `expectNext`, `expectError`, `thenCancel`, `verify(Duration)`, and `withVirtualTime`.
- [Reactor – retryWhen / Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): retry principles and Publisher handling.
- [Spring Cloud Commons source – RoundRobinLoadBalancer.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/RoundRobinLoadBalancer.java): instance selection logic, seed/counter, and empty-list handling.
- [Spring Cloud Commons source – ReactorLoadBalancerExchangeFilterFunction.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/client/loadbalancer/reactive/ReactorLoadBalancerExchangeFilterFunction.java): WebClient integration filter and reactive instance selection.
