# Role of RestTemplate in Existing Systems

In many long-running Spring Boot systems, **RestTemplate** remains the component that performs **synchronous** HTTP requests between services: fetching inventory information, calling payment systems, synchronizing data, or communicating with third-party APIs. In systems using Spring Cloud LoadBalancer, RestTemplate can also send requests to a **service ID** instead of a fixed IP/port address. As a result, business code does not need to know which replica is running, and LoadBalancer can select an appropriate **ServiceInstance**.

To maintain or upgrade such a system, you need to understand **what responsibilities RestTemplate handles**, when it actually goes through LoadBalancer, where the limitations of the blocking model lie, and when to migrate to **RestClient**, **WebClient**, or **OpenFeign**.

**Version context:** Spring Framework 6.x still provides RestTemplate and its familiar APIs. Spring Framework 7.x documentation has marked RestTemplate as a deprecated API in favor of **RestClient** for synchronous HTTP; the direction announced by Spring is removal in a future major release. Therefore, this article explains how to **understand, operate, and migrate existing code**, without treating RestTemplate as the default choice for new projects.

## 1. What RestTemplate Is and Is Not

RestTemplate lives in the **org.springframework.web.client** package of Spring Framework. It is an HTTP client using the **template method API** pattern. The application calls methods such as **getForObject**, **getForEntity**, **postForEntity**, **exchange**, or **execute**; RestTemplate builds the HTTP request, sends it through a **ClientHttpRequestFactory**, converts the body using **HttpMessageConverter**, and returns the result or throws an exception.

Example:

~~~java
@Service
class InventoryReader {

    private final RestTemplate restTemplate;

    InventoryReader(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    StockResponse getStock(String sku) {
        return restTemplate.getForObject(
                "https://api.example.net/stock/{sku}",
                StockResponse.class,
                sku);
    }
}
~~~

In this example, RestTemplate is simply a synchronous HTTP client calling a specific URL. **There is no automatic service instance lookup or load balancing** without Spring Cloud LoadBalancer integration.

### What RestTemplate Does

- Builds HTTP requests with URL/URI, method, headers, and body.
- Executes HTTP/HTTPS calls through the configured request factory.
- Converts Java objects to JSON/XML or vice versa using message converters.
- Returns **ResponseEntity** when status, headers, and body are needed.
- Allows configuring interceptors, request factory, error handler, and timeouts.
- Can integrate with Spring Cloud LoadBalancer to turn a service ID into a real instance address.

### What RestTemplate Does Not Do on Its Own

- Does not automatically register services into Eureka/Consul/Kubernetes.
- Does not automatically fetch the ServiceInstance list from the registry without LoadBalancer integration.
- Does not safely retry all requests by default or guarantee idempotency.
- Does not provide non-blocking I/O; the calling thread must wait for the result.
- Does not replace a circuit breaker, tracing, secure logging, or load limiting policies.
- Does not turn every URL into a service ID: physical URLs remain direct HTTP calls in a standard RestTemplate.

## 2. Why RestTemplate Still Appears in Running Systems

RestTemplate was widely used before Spring introduced RestClient and before microservices shifted heavily toward the reactive stack. A running codebase may have dozens of clients depending on it:

| Usage pattern | Example | Role of RestTemplate |
| --- | --- | --- |
| Internal service-to-service | Order calling Inventory | Sends synchronous HTTP between microservices |
| Partner API | Billing calling invoice gateway | Exchanges JSON with a fixed endpoint |
| Background task synchronization | Exchange rate update job | Makes HTTP calls inside a scheduler |
| Legacy system | Spring MVC application | Keeps stable code, avoids sweeping upgrades |
| HTTP metadata needed | API call requiring status/headers | Uses ResponseEntity/exchange |
| Testing and mocking | Client adapter unit tests | Uses MockRestServiceServer |

Practical value of RestTemplate in legacy systems:

1. **Stable and familiar:** The API has been used for a long time, with extensive tests and error-handling patterns.
2. **Deep integration:** Request interceptors, tracing, authentication, and logging are already embedded in operational workflows.
3. **Compatible with blocking code:** Spring MVC or background jobs do not necessarily need end-to-end reactive execution.
4. **Gradually upgradeable:** Existing code can keep running while individual adapters migrate to RestClient.

However, keeping RestTemplate should be a **managed decision**, not an excuse to ignore timeouts, retries, or thread exhaustion risks. New capabilities in Spring HTTP clients focus heavily on RestClient/WebClient; as the technology lifecycle evolves, a maintenance or migration plan is needed.

## 3. Where RestTemplate Sits in Spring Cloud LoadBalancer Architecture

In client-side load balancing architecture, RestTemplate is the **synchronous HTTP entry point** of the flow. Once **@LoadBalanced** is applied, an interceptor collaborates with **BlockingLoadBalancerClient** to select a ServiceInstance and convert the logical URI into a physical URI.

~~~mermaid
flowchart TD
    A["OrderService.getStock()"] --> B["RestTemplate calls logical URI"]
    B --> C["LoadBalancerInterceptor"]
    C --> D["BlockingLoadBalancerClient"]
    D --> E["LoadBalancerClientFactory"]
    E --> F["ServiceInstanceListSupplier"]
    F --> G["Discovery/cache/health/filter"]
    G --> H["ServiceInstance list"]
    H --> I["RoundRobin / Random selects instance"]
    I --> J["reconstructURI"]
    J --> K["ClientHttpRequestFactory sends HTTP"]
    K --> L["Inventory Service instance"]
~~~

Example logical request:

~~~text
GET http://inventory-service/api/stock/BOOK-01
~~~

Registry knows:

| Service ID | Instance ID | Physical URI |
| --- | --- | --- |
| inventory-service | inv-a | http://10.10.1.21:8080 |
| inventory-service | inv-b | http://10.10.1.22:8080 |

If LoadBalancer selects **inv-b**, the HTTP connector actually calls:

~~~text
GET http://10.10.1.22:8080/api/stock/BOOK-01
~~~

Each layer has its own responsibility:

- **RestTemplate:** method, URL, headers, body, response conversion.
- **LoadBalancerInterceptor:** intercepts requests containing a service ID to apply instance selection.
- **BlockingLoadBalancerClient:** executes target selection via LoadBalancer.
- **ServiceInstanceListSupplier:** provides the instance list after discovery, caching, and filters.
- **ClientHttpRequestFactory:** opens the connection and performs HTTP I/O to the reconstructed URI.

RestTemplate **does not directly** perform Round Robin selection or build lists from the registry. Those two tasks belong to other LoadBalancer components.

## 4. Configuring a Load-Balanced RestTemplate

Spring Boot **does not automatically create a RestTemplate bean just because spring-web is on the classpath**. The application must declare the bean itself and annotate it with **@LoadBalanced** if it wants to call by service ID.

### 4.1. Dependencies

The application needs dependencies matching the Spring Boot/Spring Cloud versions in use:

- **spring-web** or an appropriate web starter, providing RestTemplate.
- **spring-cloud-starter-loadbalancer**, providing Spring Cloud LoadBalancer.
- A discovery implementation such as Eureka/Consul for a dynamic registry, or SimpleDiscoveryClient configuration for local testing.

Gradle example for an environment using compatible Spring Boot BOM and Spring Cloud BOM:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    // When using a real registry, add the corresponding discovery provider starter.
}
~~~

Web starter names and managed dependencies may vary across Spring Boot generations. Match your project's BOM/release train; do not arbitrarily mix Spring Framework 6/7 with an incompatible Spring Cloud release.

### 4.2. Bean Declaration

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class LoadBalancedHttpConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Consuming the bean in the application:

~~~java
@Service
class InventoryClient {

    private final RestTemplate restTemplate;

    InventoryClient(@LoadBalanced RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    StockResponse getStock(String sku) {
        return restTemplate.getForObject(
                "http://inventory-service/api/stock/{sku}",
                StockResponse.class,
                sku);
    }
}
~~~

**@LoadBalanced** is the key: it marks the bean so Spring Cloud attaches the LoadBalancer interceptor. A URL with host **inventory-service** is a logical URI. If you use a RestTemplate without the interceptor and there is no DNS entry for that name, the connection may fail with **UnknownHostException**.

### 4.3. When Both Direct and Load-Balanced Clients Are Needed

An application often calls both internal services by service ID and partner APIs by fixed URL. Separate the beans to avoid accidentally routing external traffic through LoadBalancer:

~~~java
@Configuration(proxyBeanMethods = false)
class HttpClientsConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }

    @Bean
    @Primary
    RestTemplate directRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Constructor injection example:

~~~java
@Service
class ExternalAndInternalClient {

    private final RestTemplate internalClient;
    private final RestTemplate externalClient;

    ExternalAndInternalClient(
            @LoadBalanced RestTemplate internalClient,
            @Qualifier("directRestTemplate") RestTemplate externalClient) {
        this.internalClient = internalClient;
        this.externalClient = externalClient;
    }
}
~~~

When multiple beans share the same type, attach **@Qualifier** or **@LoadBalanced** at the injection point to make the intent explicit. Marking the direct client with **@Primary** ensures unqualified injections pick the standard bean. This is an example of separating roles; you can add distinct bean names and dedicated configurations to prevent ambiguity.

### 4.4. Configuring via RestTemplateBuilder

Applications using **RestTemplateBuilder** can also declare a builder bean with **@LoadBalanced**:

~~~java
@Bean
@LoadBalanced
RestTemplateBuilder loadBalancedRestTemplateBuilder() {
    return new RestTemplateBuilder();
}
~~~

With Spring Boot, the pre-configured builder or RestTemplateCustomizer beans may carry timeouts, message converters, and observability. You need to understand **which builder is being injected** and whether creating a new builder preserves Boot's customizations. Do not assume **new RestTemplateBuilder()** includes every customizer that Boot auto-configures.

## 5. Commonly Seen RestTemplate Methods

| Method | Typical scenario | Return value |
| --- | --- | --- |
| getForObject | GET, only body needed | Object T |
| getForEntity | GET, status/headers/body needed | ResponseEntity<T> |
| postForObject | POST, only response body needed | Object T |
| postForEntity | POST, response metadata needed | ResponseEntity<T> |
| put | PUT to update resource | void |
| delete | DELETE resource | void |
| exchange | Custom method, headers, body, response type | ResponseEntity<T> |
| execute | Low-level, request/response callbacks | Callback-dependent |

These methods share the same request-sending infrastructure. From the LoadBalancer perspective, **whether GET or POST, instance selection still happens before execution** if the URI uses a service ID.

### 5.1. GET with ResponseEntity

~~~java
ResponseEntity<StockResponse> response =
        restTemplate.getForEntity(
                "http://inventory-service/api/stock/{sku}",
                StockResponse.class,
                sku);

if (response.getStatusCode().is2xxSuccessful()) {
    StockResponse stock = response.getBody();
}
~~~

With the default error handler, 4xx/5xx responses normally throw an exception rather than continuing to the status check; do not write code assuming every status returns a normal ResponseEntity.

### 5.2. POST with Body and Headers

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_JSON);
headers.set("Idempotency-Key", operationId);

ReserveRequest payload = new ReserveRequest(sku, quantity);
HttpEntity<ReserveRequest> entity = new HttpEntity<>(payload, headers);

ResponseEntity<ReserveResponse> result = restTemplate.exchange(
        "http://inventory-service/api/reservations",
        HttpMethod.POST,
        entity,
        ReserveResponse.class);
~~~

RestTemplate can send custom headers and JSON bodies like a standard HTTP client. **Idempotency-Key** here is a contract implemented by the application itself, not a built-in feature of RestTemplate or Spring Cloud LoadBalancer. The server must store and process the key to prevent duplicate side effects on retry.

### 5.3. Generic Response Types

When an API returns a list of DTOs or a generic type, use **ParameterizedTypeReference**:

~~~java
ResponseEntity<List<StockResponse>> response = restTemplate.exchange(
        "http://inventory-service/api/stock",
        HttpMethod.GET,
        HttpEntity.EMPTY,
        new ParameterizedTypeReference<List<StockResponse>>() {});

List<StockResponse> items = response.getBody();
~~~

This preserves the generic type information needed by the message converter, rather than ambiguously deserializing into List<Map>.

## 6. What Happens When RestTemplate Receives HTTP 4xx/5xx?

RestTemplate uses **ResponseErrorHandler** to decide which responses count as errors. With the default error handler:

- HTTP **4xx** usually throws **HttpClientErrorException**.
- HTTP **5xx** usually throws **HttpServerErrorException**.
- Certain other protocol errors or status codes are reported via corresponding exception branches.
- Network, DNS, TLS, or timeout errors may be wrapped in **ResourceAccessException**.

Example client-side error classification:

~~~java
try {
    return restTemplate.getForObject(
            "http://inventory-service/api/stock/{sku}",
            StockResponse.class,
            sku);
} catch (HttpClientErrorException.NotFound e) {
    throw new StockNotFoundException(sku, e);
} catch (HttpServerErrorException e) {
    throw new InventoryUnavailableException("Inventory returned 5xx", e);
} catch (ResourceAccessException e) {
    throw new InventoryUnavailableException("Inventory transport failure", e);
}
~~~

Important distinctions in design:

| Error type | Example | Possible cause |
| --- | --- | --- |
| 404 | SKU does not exist | Business error or wrong path |
| 400/422 | Invalid data | Request contract/schema mismatch |
| 401/403 | Unauthorized | Token, scope, policy |
| 429 | Rate limit | Downstream overload/throttling policy |
| 502/503/504 | Gateway/downstream unavailable | Infrastructure, timeout, no instance available |
| ResourceAccessException | Connection refused, timeout | Transport, TLS, DNS, or network |

Do not automatically retry all 4xx responses. **404/400/401/403** are usually not transient errors that retrying can fix. Some 429 and 5xx responses may be retried, but you must consider **Retry-After**, deadlines, idempotency, and overall policy.

### 6.1. Custom Error Handlers

RestTemplate allows replacing the error handler if the system needs to translate error responses into domain-specific exceptions. However, replacing the handler to **swallow all 4xx/5xx** easily suppresses failure signals and hinders diagnostics. Preserve the status code, downstream error code, and trace ID while avoiding logging bodies containing sensitive data.

A maintainable strategy is to let the HTTP adapter **translate exceptions into domain exceptions** per endpoint; business logic does not need to know the details of HttpServerErrorException or ResourceAccessException.

## 7. Timeouts and Blocking I/O Must Be Explicitly Defined

RestTemplate is a synchronous client. If downstream takes several seconds to respond, **the thread calling RestTemplate must wait** accordingly. In Spring MVC, this typically holds a request-processing thread; in batch jobs, it holds a worker thread. High concurrency combined with long timeouts can exhaust the thread pool.

Do not assume the framework has already configured connect timeouts, read timeouts, and deadlines suitable for your service's SLO. Explicitly define:

- **Connect timeout:** time allowed to establish the connection.
- **Read/response timeout:** time waiting for returned data after connecting, depending on the request factory/HTTP library.
- **Connection-pool acquisition timeout:** time waiting to borrow a connection from the pool when the pool is exhausted.
- **End-to-end deadline:** total time budget, including discovery, instance selection, connection, response, and retries.

Simple example configuring RestTemplate with a request factory:

~~~java
@Bean
@LoadBalanced
RestTemplate loadBalancedRestTemplate() {
    SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofSeconds(2));
    factory.setReadTimeout(Duration.ofSeconds(5));
    return new RestTemplate(factory);
}
~~~

This snippet illustrates the API in recent Spring Framework versions, importing **java.time.Duration** and **SimpleClientHttpRequestFactory**. Actual timeout behavior depends on the HTTP engine; production environments may use Apache HttpComponents or another request factory with connection pooling.

**Read timeout is not always the deadline for the entire request.** If the server streams chunks without finishing, total elapsed time can exceed the read timeout. When retries are enabled, you must account for total attempts plus backoff. It is possible for downstream to complete the business operation while the client times out waiting for the response.

## 8. Retries, Timeouts, and Re-selecting Service Instances

Spring Cloud LoadBalancer has its own retry mechanism for certain HTTP client integrations. When enabled with the appropriate dependencies and policies, a retry can **select another ServiceInstance**. RestTemplate itself does not guarantee a safe retry policy for every request.

Example:

~~~text
Attempt 1:
  serviceId = inventory-service
  instance = inventory-a:8080
  HTTP POST /reservations
  client times out before receiving response

Attempt 2:
  LoadBalancer may select inventory-b:8080
  HTTP POST /reservations
~~~

You cannot conclude Attempt 1 failed merely because the client timed out. For a POST creating a reservation, if the backend does not deduplicate via an idempotency key, two calls can create two reservations.

When evaluating retries in a legacy system:

1. **Check where retries are enabled:** RestTemplate interceptor, Spring Retry, Spring Cloud LoadBalancer, circuit-breaker wrapper, or service mesh.
2. **Avoid uncontrolled nested retries:** two retry layers can multiply the actual number of calls.
3. **Retry only appropriate conditions:** timeouts/503 may be transient; validation errors usually are not.
4. **Bound attempts and total deadline:** so the caller does not hold a thread for too long.
5. **Use bounded backoff/jitter:** reduces retry storms when downstream is failing.
6. **Ensure idempotency:** especially for POST or financial write operations.
7. **Observe the instance before and after retry:** retries may switch targets; do not assume the same instance is always used.

**Do not retry an operation just because the HTTP method is PUT/DELETE** if the application performs out-of-contract side effects or the system state does not guarantee safety. HTTP semantics and business idempotency must be designed together.

## 9. ClientHttpRequestFactory Determines Network Communication Behavior

RestTemplate is the upper API layer; the actual HTTP engine is provided by **ClientHttpRequestFactory**. When reading a system using RestTemplate, check the request factory configuration as well because it directly affects:

- TCP/TLS connections and DNS lookups.
- Connect timeout, read timeout, and HTTP version selection.
- Connection pool management, keep-alive, and connection reuse.
- Proxies, proxy authentication, truststores, and mTLS.
- Redirect handling and specific behaviors of the HTTP client implementation.

| Component | Role |
| --- | --- |
| RestTemplate | Synchronous API and HTTP send/receive workflow |
| ClientHttpRequestFactory | Creates actual network connections and requests |
| ClientHttpRequestInterceptor | Augments/intercepts requests, e.g., tracing or headers |
| HttpMessageConverter | Converts Java objects ↔ HTTP body |
| ResponseErrorHandler | Classifies HTTP error responses |
| Spring Cloud LoadBalancer interceptor | Selects instance and rewrites logical URI |

For example, **SimpleClientHttpRequestFactory** is a basic option built on JDK infrastructure. For high throughput or explicit pool configuration, a factory backed by Apache HttpComponents or JDK HttpClient may be used, depending on the Spring Framework version.

Do not assume swapping the request factory only changes performance. Behavior regarding timeouts, redirects, cookies, TLS, headers, and request body streaming can differ. When changing factories during migration, run regression tests at the real HTTP layer.

### 9.1. Sharing RestTemplate as a Configured Bean

RestTemplate is usually declared as a reusable bean rather than instantiated on every request. This reuses interceptors, converters, observability, and HTTP connection infrastructure.

An initialized RestTemplate can be called concurrently from multiple threads **provided its configuration is not mutated during use** and the underlying request factory supports concurrency. Do not call `setInterceptors()`, `setRequestFactory()`, `setErrorHandler()`, or add converters per request on a shared singleton bean; runtime mutations like these easily cause race conditions.

When different configurations are needed per downstream service, create separate beans/client adapters with appropriate timeouts, headers, authorization, and pools.

## 10. Interceptors, Header Propagation, and Security

In microservices, RestTemplate rarely carries only a path and body. Applications commonly use request interceptors to attach:

- Downstream-specific Authorization or tokens.
- Trace context such as W3C traceparent.
- Correlation ID.
- Tenant or API version headers required by the contract.
- Idempotency headers for write requests.
- Logging with sensitive data redacted.

Example of an interceptor adding a header from a safe value propagated in the request context:

~~~java
class CorrelationIdInterceptor implements ClientHttpRequestInterceptor {

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        String correlationId = CorrelationContext.currentId();
        if (correlationId != null && !correlationId.isBlank()) {
            request.getHeaders().set("X-Correlation-Id", correlationId);
        }

        return execution.execute(request, body);
    }
}
~~~

**CorrelationContext** is an illustrative helper provided by the application, not a built-in Spring class. In production, prefer propagating context via tracing/observability infrastructure when available instead of inventing duplicate headers.

Registering the interceptor:

~~~java
@Bean
@LoadBalanced
RestTemplate loadBalancedRestTemplate() {
    RestTemplate restTemplate = new RestTemplate();
    restTemplate.getInterceptors().add(new CorrelationIdInterceptor());
    return restTemplate;
}
~~~

### 10.1. Interceptor Order Affects What Is Observed

Spring Cloud may add **LoadBalancerInterceptor** to RestTemplate's interceptor list. If a custom interceptor logs **request.getURI()**, it may observe either the logical URI or the physical URI depending on interceptor ordering and when logging occurs.

Therefore:

- Do not assume the URL in an interceptor log is always the final IP/port.
- When you need to know the selected instance, use LoadBalancer lifecycle/corresponding metrics or log on the server side.
- Do not manually add duplicate LoadBalancerInterceptors.
- Do not modify interceptors after the bean is already in concurrent use by the application.

### 10.2. Do Not Blindly Copy Sensitive Headers

When calling another service, do not automatically copy all headers from the inbound request to the outbound request. User session cookies, Authorization, or X-Forwarded-* headers may not belong to the downstream contract. Forward only explicitly allowlisted and security-validated headers.

For external URLs, avoid using a RestTemplate pre-configured with internal tokens by default. **Separating internal and external RestTemplates** reduces the risk of leaking credentials.

### 10.3. Controlled Logging

Never log raw Authorization, Cookie, query strings containing tokens, cardholder details, or full request/response bodies. A useful outbound log typically contains:

~~~text
traceId | serviceId | instanceId | method | path template | status | durationMs
~~~

Depending on the tooling, `instanceId` may not yet be available in a basic RestTemplate interceptor. If accurate LoadBalancer data is needed, use appropriate hooks/observability rather than guessing from the host name.

## 11. Observability: Measuring RestTemplate at the Right Layer

In a multi-service system, the same HTTP error can originate at different layers:

~~~text
Business Service
    ↓
RestTemplate
    ↓
LoadBalancerInterceptor
    ↓
Discovery + ServiceInstanceListSupplier
    ↓
Select ServiceInstance
    ↓
ClientHttpRequestFactory
    ↓
Network / TLS / Backend
~~~

For diagnosis, separate the signals:

| Signal | Answers the question |
| --- | --- |
| Service ID | Which logical downstream is being called? |
| Instance ID/host:port | Which replica was selected? |
| HTTP method/path template | Which API endpoint failed? |
| HTTP status | Did the backend return a 4xx/5xx error? |
| IOException/timeout/TLS error | Did the transport fail before an HTTP response arrived? |
| Request duration | How much time was spent? |
| Retry attempt | Which attempt number is this? |
| Trace ID | Which services did the correlated request traverse? |
| Cache/health state | Is the instance list fresh and healthy? |

Spring Boot and Spring Framework support observability through Micrometer Observation, while Spring Cloud LoadBalancer provides lifecycle callbacks and metric integrations depending on configuration/version. If the application creates RestTemplate manually via **new RestTemplate()**, verify whether Boot's customizers and observation registry are actually applied.

A solid approach is to use the Boot-managed builder or intentionally configure RestTemplate, then verify traces and HTTP client metrics in a test environment.

**Do not assume every 503 error is a LoadBalancer bug.** A service instance may be selected properly while downstream still returns 503 due to overload. Conversely, when no instances exist, LoadBalancer can return an error before any real network connection occurs.

## 12. Testing RestTemplate Clients Without Calling Real Services

### 12.1. Unit Testing with MockRestServiceServer

Spring Test provides **MockRestServiceServer** to test REST clients at the request/response level without running an HTTP server. Example testing an adapter using a regular RestTemplate:

~~~java
@Test
void fetchesStockFromHttpEndpoint() {
    RestTemplate restTemplate = new RestTemplate();

    MockRestServiceServer server =
            MockRestServiceServer.bindTo(restTemplate).build();

    server.expect(requestTo(
                    "https://api.example.net/stock/BOOK-01"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                    "{\"sku\":\"BOOK-01\",\"available\":7}",
                    MediaType.APPLICATION_JSON));

    InventoryReader client = new InventoryReader(restTemplate);

    StockResponse result = client.getStock("BOOK-01");

    assertEquals("BOOK-01", result.sku());
    assertEquals(7, result.available());
    server.verify();
}
~~~

In this example, **StockResponse** is an application DTO/record:

~~~java
record StockResponse(String sku, int available) {}
~~~

Imports for JUnit, MockRestServiceServer, and static helpers **requestTo**, **method**, **withSuccess** need to be added in the test project. This test demonstrates RestTemplate sending GET and deserializing JSON; it does not verify LoadBalancer instance selection.

### 12.2. Testing LoadBalancer Integration Separately

To test **service ID → ServiceInstance → physical URI**, you need a separate integration test:

1. Declare a static list for `inventory-service` using SimpleDiscoveryClient, or use a test registry.
2. Run two stub HTTP servers on two different ports, each returning its own **instanceId**.
3. Use a **@LoadBalanced** RestTemplate and send requests to **http://inventory-service/...**.
4. Verify requests arrive at one of the two physical addresses without attempting DNS resolution of `inventory-service`.
5. Shut down one server or swap the supplier, and observe error/health/cache/retry behavior.

Example `application-test.yml` using two static instances:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

**SimpleDiscoveryClient** does not automatically detect server shutdowns. If port 8081 is stopped while still kept in configuration, LoadBalancer may continue picking it until the instance source or health state is updated. That is not a RestTemplate bug.

### 12.3. Testing Network Failures with a Mock HTTP Server

To verify timeouts, connection resets, TLS, or redirects, **WireMock** or **MockWebServer** is generally more suitable than MockRestServiceServer because they run a real simulated HTTP server at the network layer. Spring Framework documentation also recommends considering a mock HTTP server for full transport testing.

Do not rely solely on MockRestServiceServer and conclude you have tested real connect timeouts or connection pooling.

## 13. When to Keep RestTemplate vs. When to Replace It

Spring Framework currently offers several HTTP client options:

| Tool | API style | I/O model | Best suited for |
| --- | --- | --- | --- |
| RestTemplate | Template methods | Blocking | Existing stable Spring code needing maintenance |
| RestClient | Fluent API | Blocking | New HTTP clients in synchronous Spring MVC/jobs |
| WebClient | Fluent reactive | Non-blocking | WebFlux, streaming, or high concurrency |
| OpenFeign | Annotated interface | Typically blocking in Spring Cloud OpenFeign integration | Declarative clients by service ID |
| HTTP Service Client | Java interface with @HttpExchange | Backed by RestClient/WebClient adapter | Type-safe contracts with reduced boilerplate |

**RestClient is not WebClient.** RestClient is still a synchronous HTTP client, but offers a more modern API than RestTemplate and can share request factories, interceptors, and message converters.

A system does not need to go fully reactive just to move off RestTemplate. For synchronous Spring MVC applications, **RestClient** is the natural migration target. For WebFlux or genuinely streaming/non-blocking workloads, **WebClient** fits better when the entire pipeline is designed to avoid blocking.

### 13.1. When RestTemplate Can Still Be Kept

- The application is on Spring Framework 6.x, with many legacy clients and stable tests.
- There is no requirement to change the API, or operational bug fixes take priority.
- Immediate migration would require major changes to error handling, authentication, or transport.
- A clear technical plan and framework lifecycle tracking are in place.

Keeping RestTemplate does not mean keeping every legacy configuration unchanged. Timeouts, retries, observability, credential handling, and dependency support must still be reviewed first.

### 13.2. When Migration Should Be Prioritized

- The project is upgrading to Spring Framework 7.x or preparing for subsequent releases.
- The team is building new client APIs or can upgrade adapters incrementally.
- You want to standardize HTTP clients and reduce usage of deprecated APIs.
- You need newer features developed primarily in RestClient.
- Many requests are stalling threads due to blocking; in that case evaluate WebClient architecture rather than merely renaming classes.

## 14. Non-Disruptive Migration Path from RestTemplate to RestClient

Spring Framework recommends migrating incrementally component by component. **RestClient.create(restTemplate)** lets you create a RestClient inheriting much of the configuration from an existing RestTemplate, which is useful for updating call syntax before replacing the entire HTTP infrastructure.

### 14.1. Step 1: Map Existing Clients

For each RestTemplate bean, document:

| Inventory item | Example |
| --- | --- |
| Bean name / qualifier | loadBalancedRestTemplate |
| Consuming services | InventoryClient, PaymentClient |
| Target destination | service ID or partner URL |
| Request factory | JDK/Apache HttpComponents |
| Interceptors | auth, tracing, correlation |
| Message converters | JSON, form, XML |
| Error handler | default or custom |
| Timeout | connect/read/pool acquisition |
| Retry/circuit breaker | which layer and under what conditions |
| Observability | client metrics, trace propagation |
| Regression tests | HTTP contract, LB, timeout, auth |

Inventorying avoids scenarios where switching syntax to RestClient drops a critical interceptor or inadvertently switches from a pooled HTTP engine to a different engine.

### 14.2. Step 2: Update Syntax in Individual Adapters

Existing RestTemplate code:

~~~java
StockResponse stock = restTemplate.getForObject(
        "http://inventory-service/api/stock/{sku}",
        StockResponse.class,
        sku);
~~~

You can create a RestClient from the already configured RestTemplate bean:

~~~java
RestClient restClient = RestClient.create(restTemplate);

StockResponse stock = restClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

Or with a LoadBalancer-integrated `RestClient.Builder`:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}
~~~

Then use the builder inside the client adapter:

~~~java
@Service
class InventoryRestClient {

    private final RestClient restClient;

    InventoryRestClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    StockResponse getStock(String sku) {
        return restClient.get()
                .uri("http://inventory-service/api/stock/{sku}", sku)
                .retrieve()
                .body(StockResponse.class);
    }
}
~~~

**Note:** `RestClient.create(restTemplate)` reuses existing configuration as supported by the framework, but does not replace regression tests. Verify that the LoadBalancer interceptor, timeouts, error handling, message converters, and observability continue operating equivalently.

### 14.3. Step 3: Check Behavioral Differences

During the parallel rollout phase:

1. Compare request method, URI, headers, and body.
2. Compare how logical URIs are resolved into physical URIs.
3. Check 4xx/5xx error mapping, timeouts, exceptions, and retries.
4. Check JSON serialization/deserialization, generic types, and status handling.
5. Compare proxies, redirects, TLS, and connection pooling.
6. Check trace propagation and client metrics.
7. Run contract tests against downstream and evaluate latency/error rates.

In particular, **RestClient and RestTemplate may pick different default request factories** when no additional HTTP library is on the classpath. Do not assume identical network behavior just because the new call syntax is shorter.

### 14.4. Step 4: Move Configuration to RestClient.Builder

Once adapters are using RestClient, standardize builder configuration, HTTP factory, auth, observability, and shared policies. Once complete, remove unused RestTemplate beans and update tests/monitoring.

You do not need to migrate all clients in a single release. You can start with lower-risk downstream services first, then move to payment/order or APIs with side effects after thorough verification.

## 15. Common Issues in Legacy RestTemplate Systems

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| UnknownHostException: inventory-service | Injecting a RestTemplate without @LoadBalanced | Check the exact bean/qualifier and interceptors |
| No RestTemplate bean found | Missing @Bean declaration or configuration not scanned | Check bean definitions and application configuration |
| No instances available | Discovery/supplier returns no instances | Check service ID, registry, cache, health |
| SSLHandshakeException | Mismatched TLS/certificate/SNI | Check instance scheme and truststore |
| High response time | Slow downstream or overly long timeouts | Measure latency; split connect/read/pool wait |
| Worker threads exhausted | Many blocking RestTemplate calls | Inspect thread dumps, pools, concurrency, timeouts |
| Unexpected 4xx/5xx behavior | DefaultResponseErrorHandler throws exceptions | Inspect exception mapping and error handler |
| Request missing trace/auth header | Bean created outside builder/customizer or missing interceptor | Inspect the actual list of interceptors |
| One POST processed twice | Retried after timeout without idempotency | Check retry layers and server deduplication |
| Logical URI not reconstructed | Missing Spring Cloud LoadBalancer or using direct client | Check dependencies and @LoadBalanced |
| Different errors after moving to RestClient | Different request factory, interceptors, status handling | Compare HTTP wire data and regression tests |
| Token leaked in logs | Logging raw query string/headers | Redact query parameters, credentials, and sensitive bodies |

### Minimal Investigation Workflow

~~~text
1. Which RestTemplate bean is injected?
2. Does that bean have @LoadBalanced and the expected interceptors?
3. Does the request use a service ID or a physical URL?
4. What instances does the supplier/discovery have?
5. Which instance did LoadBalancer select?
6. What is the physical URI and how is the HTTP request sent?
7. Did the failure happen during connect, read, TLS, status check, or deserialization?
8. Are retries active? How many total calls actually occurred?
~~~

This workflow separates RestTemplate-layer issues from discovery issues, LoadBalancer issues, and downstream issues.

## 16. Hands-On Exercise: Identifying the Role of an Active RestTemplate

### Scenario

An `order-service` application uses two clients:

- **InventoryClient** calls internal **inventory-service** by service ID.
- **PartnerCatalogClient** calls **https://api.partner.example/catalog** via a fixed URL.

Requirement: both use RestTemplate with independent configurations, and only InventoryClient uses LoadBalancer.

### Setup

1. Add Spring Web and Spring Cloud LoadBalancer starters matching your BOM.
2. Declare a **@LoadBalanced RestTemplate** for InventoryClient.
3. Declare a **direct RestTemplate** for PartnerCatalogClient.
4. Configure separate timeouts for each client.
5. Use local SimpleDiscoveryClient to declare two Inventory replicas.
6. Create endpoint `GET /api/stock/{sku}` returning the SKU and `instanceId`.
7. Send multiple requests, record `instanceId`, and verify the routing path.

Example instance list:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Expected observations:

| Call | URI in code | Execution path |
| --- | --- | --- |
| InventoryClient.getStock() | http://inventory-service/api/stock/BOOK-01 | LoadBalancer selects localhost:8081 or :8082 |
| PartnerCatalogClient.getItem() | https://api.partner.example/catalog/BOOK-01 | Direct HTTP to the partner host |

Try removing `@LoadBalanced` from the Inventory bean and re-run to observe the difference between a logical service ID and a DNS-resolvable hostname. Then restore the correct configuration.

### Additional Verification Scenarios

- Stop one instance while keeping it in SimpleDiscoveryClient to observe the risk of stale static lists.
- Lower the timeout to distinguish `ResourceAccessException` from HTTP response errors.
- Add an interceptor that writes a correlation ID and verify the header appears on the stub server.
- Call an endpoint returning 404 to observe how the default error handler behaves.
- Wrap with `RestClient.create(restTemplate)` and re-run the same contract tests.
- Create a POST with an idempotency key and inspect behavior when the response is delayed after the server completes the business action.

## 17. Maintenance Team Checklist

- [ ] Know which downstream services RestTemplate serves and which bean is injected.
- [ ] Distinguish between a direct RestTemplate and a `@LoadBalanced` RestTemplate.
- [ ] Ensure the LoadBalancer starter and corresponding discovery source are present when calling by service ID.
- [ ] Configure appropriate connect/read/pool timeouts along with an overall deadline.
- [ ] Know which HTTP request factory is actually in use.
- [ ] Understand how the default error handler maps 4xx/5xx responses to exceptions.
- [ ] Avoid nested retries; ensure operations with side effects have idempotency mechanisms.
- [ ] Avoid losing auth/trace/interceptors during bean creation or migration.
- [ ] Never log credentials, cookies, tokens, or queries containing sensitive data.
- [ ] Maintain unit tests for client adapters and integration tests for load balancing/transport.
- [ ] Have metrics/traces to distinguish discovery, HTTP, and backend errors.
- [ ] Evaluate the RestTemplate lifecycle in Spring Framework 7.x.
- [ ] Maintain an incremental roadmap to migrate to RestClient or WebClient when appropriate.

## 18. Conclusion

**RestTemplate is a long-standing synchronous HTTP client that still plays an important role in running Spring systems.** It constructs and executes requests, serializes/deserializes bodies, and supports interceptors and error handling. When configured with **@LoadBalanced**, RestTemplate becomes an entry point to **Spring Cloud LoadBalancer**: calling by service ID, relying on discovery and ServiceInstanceListSupplier to find candidates, selecting an instance, and reconstructing the physical URI.

Understanding this separation of responsibilities helps maintenance teams troubleshoot at the right layer: RestTemplate handles the HTTP client; LoadBalancer handles instance selection; discovery provides replica metadata; and the request factory handles transport. For new systems or Spring Framework upgrades, **RestClient** is the preferred choice for blocking HTTP, while **WebClient** suits non-blocking/reactive pipelines.

Rather than replacing every RestTemplate at once, **inventory configurations, harden timeouts/retries/observability, build contract tests, and migrate client by client**, ensuring load balancing and existing security behaviors remain intact.

## 19. References

- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestTemplate, RestClient, WebClient, error handling, and migration guide to RestClient.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): @LoadBalanced RestTemplate, BlockingLoadBalancerClient, and multi-bean configuration.
- [Spring Cloud LoadBalancer Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ServiceInstanceListSupplier, retry, request transformers, and LoadBalancer options.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): RestTemplateBuilder, HTTP client configuration, and infrastructure reuse.
- [Spring Framework – Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): MockRestServiceServer and mock HTTP servers.
- [The State of HTTP Clients in Spring](https://spring.io/blog/2025/09/30/the-state-of-http-clients-in-spring/): explains why RestTemplate development stopped and the direction toward RestClient.
- [New in Spring 6.1: RestClient](https://spring.io/blog/2023/07/13/new-in-spring-6-1-restclient/): how to create RestClient from RestTemplate and fluent API usage patterns.
