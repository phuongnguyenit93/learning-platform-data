# Choosing Between RestTemplate, RestClient, WebClient, Feign, or HTTP Interface

Spring Cloud LoadBalancer integrates with multiple HTTP clients, but **there is no single best choice for every application**. Selecting a client should be based on the service's processing model, streaming/concurrency requirements, how the team prefers to declare HTTP contracts, compatibility with existing code, and operability.

Five common options:

- **RestTemplate**: a familiar synchronous client, suitable for systems using it stably that need minimal changes.
- **RestClient**: Spring Framework's modern synchronous API, suitable for most new Spring MVC code.
- **WebClient**: a reactive/non-blocking API, suitable when the processing flow needs to preserve reactivity or streaming.
- **OpenFeign**: a client declared with interfaces and annotations, suitable when you want to describe HTTP APIs in a declarative style.
- **HTTP Interface**: an HTTP interface provided by Spring Framework; it can run on RestClient or WebClient, so blocking/reactive characteristics and LoadBalancer behavior depend on the underlying adapter.

This article belongs to the **Design Choices** chapter of the Spring Cloud LoadBalancer module. The focus is on deciding which client fits the application, how to integrate properly with a **service ID**, and the implications for timeouts, connection pools, retries, testing, and maintainability.

## 1. Start from the application's processing model

Before comparing APIs, identify which model the caller runs in:

~~~mermaid
flowchart TD
    A["Service needing to call downstream HTTP"]
    B{"Current execution flow?"}
    C["Imperative / blocking"]
    D["Reactive / non-blocking"]
    E{"Existing stable<br/>RestTemplate code?"}
    F["Keep RestTemplate<br/>and integrate LoadBalancer"]
    G["Use RestClient<br/>for new synchronous code"]
    H["Use WebClient<br/>keep reactive chain"]
    I{"Need API declaration<br/>via interface?"}
    J["OpenFeign<br/>if it fits the ecosystem"]
    K["HTTP Interface<br/>choose RestClient/WebClient adapter"]
    A --> B
    B -->|"Blocking"| C --> E
    E -->|"Yes"| F
    E -->|"No / new code"| G
    B -->|"Reactive"| D --> H
    C -->|"Need declarative interface"| I
    D -->|"Need interface proxy"| I
    I --> J
    I --> K
~~~

This is a **suggested decision path**, not a mandatory rule. One application can use multiple clients because it calls different types of downstreams; what should be avoided is letting each module choose clients, retries, and timeouts inconsistently.

Three questions to answer first:

1. **Can the caller tolerate blocking?** If you are in a Spring MVC/imperative service, RestClient, RestTemplate, or Feign are usually suitable. If you are in a WebFlux reactive chain, prefer WebClient or HTTP Interface running on WebClient.
2. **How do you want to write the calls?** Fluent API, declarative interface, or a custom business abstraction?
3. **Who manages connections and resilience?** You need to clarify which layer owns HTTP transport, pool, timeout, retry, metrics, and LoadBalancer.

## 2. Quick comparison table of the five options

| Criterion | RestTemplate | RestClient | WebClient | OpenFeign | HTTP Interface |
|---|---|---|---|---|---|
| API style | Imperative | Imperative, fluent | Reactive, fluent | Declarative interface | Declarative interface |
| Blocking by default | Yes | Yes | No when used reactively; can be blocked by caller | Yes | Depends on adapter |
| Reactive streaming/backpressure | Limited | Not the primary goal | Yes | Not a reactive model | Yes if using WebClient adapter |
| LoadBalancer integration | `@LoadBalanced RestTemplate` | `@LoadBalanced RestClient.Builder` | `@LoadBalanced WebClient.Builder` | Feign LB client when integration is present | Inherited from RestClient/WebClient |
| How endpoints are declared | URL and method in code | URL and method in code | URL and reactive operators | `@FeignClient` and mapping annotations | `@HttpExchange`, `@GetExchange`... |
| HTTP transport control | RequestFactory | RequestFactory | Connector/ConnectionProvider | Feign Client/delegate | Chosen adapter |
| Best suited for | Existing synchronous code | New synchronous code | Reactive/streaming | Declarative blocking client | Spring-standard contract interface |
| Common risk | Accidentally using a non-LB bean | Creating client from a plain builder | Using plain WebClient or blocking event-loop | Fixed URL bypassing LB | Proxy using wrong adapter/client |

**Do not infer LoadBalancer behavior from the client name alone.** Each option requires the right bean, filter, interceptor, or delegate integrated with Spring Cloud LoadBalancer. A plain `RestClient.create("http://catalog-service")` does not become load-balanced simply because the starter is in the project.

## 3. RestTemplate: suitable when existing code is stable

`RestTemplate` is Spring's long-standing synchronous HTTP client. If an application already has many calls, interceptors, request factories, message converters, and stable tests, continuing to use it can make sense.

### Integrating with a service ID

~~~java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class CatalogRestTemplateConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate catalogRestTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

Using the bean:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
class CatalogRestTemplateClient {

    private final RestTemplate restTemplate;

    CatalogRestTemplateClient(
            @Qualifier("catalogRestTemplate")
            RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    ProductDto find(long id) {
        return restTemplate.getForObject(
                "http://catalog-service/api/products/{id}",
                ProductDto.class,
                id);
    }
}
~~~

Here, `catalog-service` is the **service ID** resolved by Spring Cloud LoadBalancer against the instance list. `@LoadBalanced` must be placed on the RestTemplate bean actually used; instantiating `new RestTemplate()` in another class will not automatically attach the interceptor.

### When to choose

- The codebase already uses RestTemplate extensively.
- The processing flow is blocking/imperative.
- You want to minimize migration risk in a release.
- RequestFactory, interceptors, and current testing practices are already standardized.

### When to consider another option

- You are writing new synchronous code and want a more fluent API: see RestClient.
- You need reactive composition, streaming, or backpressure: see WebClient.
- You want a declarative interface: see OpenFeign or HTTP Interface.

There is no need to migrate all RestTemplate usage just to "be able to use LoadBalancer"; RestTemplate can still integrate with client-side load balancing when configured properly.

## 4. RestClient: a strong default choice for new synchronous code

`RestClient` was introduced by Spring Framework in **Spring Framework 6.1**. Its fluent API makes code easy to read, while its execution model remains **blocking**.

### LoadBalancer integration

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogRestClientConfiguration {

    @Bean("catalogLoadBalancedBuilder")
    @LoadBalanced
    RestClient.Builder catalogLoadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            @Qualifier("catalogLoadBalancedBuilder")
            RestClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

Calling the API:

~~~java
ProductDto product = catalogRestClient.get()
        .uri("/api/products/{id}", 42)
        .retrieve()
        .body(ProductDto.class);
~~~

### Strengths

- Fluent API, readable and easy to organize into gateways/service adapters.
- Integrates with Spring message converters and the Spring ecosystem.
- Can use an appropriate RequestFactory, such as JDK HttpClient or Apache HttpClient 5, to control pools and timeouts.
- Simple blocking model for Spring MVC services and imperative business code.

### Points to watch

- `RestClient` **is not reactive**; the request thread waits for the result.
- You must use the exact `@LoadBalanced RestClient.Builder`, then inject the `RestClient` built from that builder.
- If you create `RestClient.create(...)` or `RestClient.builder()` elsewhere, the new client will not automatically inherit the LoadBalancer interceptor.
- If the project uses a Spring Boot–managed builder/customizer for observability, SSL, or converters, check how the builder is configured for your version so you do not inadvertently discard those customizations.

**Practical recommendation:** for a new Spring MVC service, if a declarative interface is not required and there is no specific reason to use Feign, RestClient is a solid synchronous starting point.

## 5. WebClient: choose when reactive or streaming is needed

`WebClient` is Spring WebFlux's non-blocking client. It is suitable when the caller needs to compose multiple asynchronous calls, handle streams, support backpressure, or uses WebFlux end-to-end.

### LoadBalancer integration

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogWebClientConfiguration {

    @Bean("catalogLoadBalancedWebClientBuilder")
    @LoadBalanced
    WebClient.Builder catalogLoadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean("catalogWebClient")
    WebClient catalogWebClient(
            @Qualifier("catalogLoadBalancedWebClientBuilder")
            WebClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

Reactive call:

~~~java
Mono<ProductDto> product = catalogWebClient.get()
        .uri("/api/products/{id}", 42)
        .retrieve()
        .bodyToMono(ProductDto.class);
~~~

### Strengths

- Non-blocking I/O when used reactively and properly.
- Supports streaming and composition via `Mono`/`Flux`.
- Fits well with WebFlux, reactive database drivers, and non-blocking dependencies.
- Allows control over the connector and Reactor Netty connection provider.

### Points to watch

- Simply using WebClient **does not make the whole application non-blocking**. If you invoke blocking JDBC/JPA inside a reactive callback, the event loop can be blocked.
- Calling `.block()` on an event loop is an anti-pattern; in Spring MVC, `.block()` can block servlet workers even though it is not an event loop.
- Reactor Netty's pool has its own characteristics and limits; monitor by remote host, pending acquire, and response latency.
- `@LoadBalanced` must be attached to the builder actually used to construct the client. `WebClient.create("http://catalog-service")` does not automatically include the LoadBalancer filter.

### When should you not choose WebClient?

If the entire service is blocking Spring MVC, downstream calls do not need streaming/reactivity, and the team has no need for reactive composition, using WebClient and calling `.block()` everywhere usually adds complexity without clear benefits.

## 6. OpenFeign: declarative client for HTTP APIs

OpenFeign lets you describe a remote API using a Java interface and annotations. It is suitable when you want to reduce request/response boilerplate and standardize clients per service.

### Declaring a Feign client by service ID

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/api/products/{id}")
    ProductDto findById(@PathVariable("id") long id);
}
~~~

Enabling scanning:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

@SpringBootApplication
@EnableFeignClients(basePackages = "com.example.orders.client")
class OrderApplication {
}
~~~

Commonly required dependencies:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-openfeign")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

When no fixed URL is declared and compatible Spring Cloud LoadBalancer integration is present, the Feign client can use `FeignBlockingLoadBalancerClient` to select an instance by service ID.

### Strengths

- The interface clearly expresses the service and operations.
- Reduces repetitive code for HTTP methods, paths, and binding.
- Fits imperative/blocking applications.
- Provides mechanisms to configure decoders, encoders, interceptors, and clients per context.

### Points to watch

- OpenFeign follows a blocking model; do not choose it if the core requirement is end-to-end reactivity.
- `@FeignClient(url=...)` or an explicit URL property will call a fixed endpoint and bypass name-based instance selection for that client.
- Check the actual HTTP delegate if you configure a custom `feign.Client`.
- Spring Cloud OpenFeign configures `Retryer.NEVER_RETRY` by default; do not assume retries work automatically just because LoadBalancer is present. Configure explicitly and consider idempotency.
- Interface annotations can create the impression that "it is just a Java method", yet it is still a network call with timeouts, transport failures, status codes, and contracts.

### When to choose

- The codebase has already standardized on OpenFeign.
- The team prefers declaring APIs with interfaces.
- Downstream calls are primarily blocking with clear contracts.
- Per-client configuration within the Spring Cloud OpenFeign ecosystem is needed.

## 7. HTTP Interface: Spring's declarative interface, where the adapter decides execution

HTTP Interface uses `@HttpExchange`, `@GetExchange`, and `@PostExchange` to declare an HTTP contract in a Java interface. Unlike OpenFeign, it is a Spring Framework mechanism and **does not define its own transport or LoadBalancer**.

Example interface:

~~~java
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.bind.annotation.PathVariable;

@HttpExchange("/api/products")
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ProductDto findById(@PathVariable("id") long id);
}
~~~

### Using the RestClient adapter

If you want blocking behavior and already have a load-balanced `RestClient`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Bean
CatalogHttpApi catalogHttpApi(
        @Qualifier("catalogRestClient") RestClient client) {

    HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(
                    RestClientAdapter.create(client))
                    .build();

    return factory.createClient(CatalogHttpApi.class);
}
~~~

The proxy executes through that RestClient adapter, thereby **inheriting the LoadBalancer** from the passed-in RestClient.

### Using the WebClient adapter

If you want reactive behavior, declare an interface returning `Mono`/`Flux` and create the proxy from a load-balanced WebClient:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange("/api/products")
interface ReactiveCatalogHttpApi {

    @GetExchange("/{id}")
    Mono<ProductDto> findById(long id);
}
~~~

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Bean
ReactiveCatalogHttpApi reactiveCatalogHttpApi(
        @Qualifier("catalogWebClient") WebClient client) {

    HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(
                    WebClientAdapter.create(client))
                    .build();

    return factory.createClient(ReactiveCatalogHttpApi.class);
}
~~~

Specific packages and APIs must match the application's Spring Framework version.

### Strengths and limitations

- The interface serves as a clean contract, easy to mock and reuse.
- You can choose the RestClient adapter for blocking or the WebClient adapter for reactive execution.
- No separate transport is needed just to use HTTP Interface.
- Timeout, pool, LoadBalancer, and retry characteristics **come from the underlying client/adapter**.
- Do not confuse `@HttpExchange` with `@LoadBalanced`; interface annotations do not enable discovery or instance selection on their own.

**HTTP Interface is especially suitable** when a team wants a declarative interface while keeping control over choosing RestClient/WebClient and Spring's transport configuration.

## 8. Choosing by practical scenario

| Scenario | Option to consider | Reason |
|---|---|---|
| Legacy app using RestTemplate with stable tests | Keep RestTemplate | Minimal change, can still integrate LB |
| New Spring MVC service making synchronous HTTP calls | RestClient | Fluent API, clear blocking model |
| WebFlux calling multiple reactive downstreams | WebClient | Preserves non-blocking chain and composition |
| Team standardized on declarative blocking clients | OpenFeign | Interfaces and per-client configuration |
| Want a Spring Framework declarative interface | HTTP Interface | Choose RestClient or WebClient adapter |
| Need streaming responses/reactive backpressure | WebClient or HTTP Interface + WebClient | Reactive pipeline |
| Need to call an external API via a fixed URL | Separate direct client | Avoid forcing external hosts into discovery |
| One module needs both service IDs and external URLs | Two separate client beans | Do not mix direct URLs and service IDs under the same policy |

### Decision rules

- **Keep existing code** if it is stable and there is no migration requirement.
- **RestClient** is a sensible starting point for new synchronous Spring MVC services.
- **WebClient** when reactivity is a genuine requirement across the pipeline.
- **OpenFeign** when declarative clients are already the team convention and a blocking model fits.
- **HTTP Interface** when you want a Spring-native interface and explicit control over choosing the adapter.
- **RestTemplate** for existing synchronous code or systems needing compatibility with legacy configuration.

Do not choose WebClient just because "reactive" sounds faster; do not choose Feign just for fewer lines of code; and do not migrate off RestTemplate solely to use Spring Cloud LoadBalancer.

## 9. Decoupling business logic from the HTTP client choice

A design that is easy to change lets the business service depend on a **business interface**, while each HTTP client lives inside an adapter:

~~~mermaid
flowchart LR
    A["OrderApplicationService"]
    B["CatalogGateway<br/>business port"]
    C["RestClient adapter"]
    D["WebClient adapter"]
    E["Feign adapter"]
    F["HTTP Interface adapter"]
    G["Spring Cloud LoadBalancer"]
    H["catalog-service instances"]
    A --> B
    B --> C
    B --> D
    B --> E
    B --> F
    C --> G
    D --> G
    E --> G
    F --> G
    G --> H
~~~

Example business interface:

~~~java
public interface CatalogGateway {
    ProductDto findProduct(long id);
}
~~~

The business service depends only on `CatalogGateway`, unaware of RestClient or Feign:

~~~java
import org.springframework.stereotype.Service;

@Service
class OrderApplicationService {

    private final CatalogGateway catalogGateway;

    OrderApplicationService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    OrderView createOrder(long productId) {
        ProductDto product = catalogGateway.findProduct(productId);
        // Execute business rules with the fetched product.
        return new OrderView(product.id(), product.name());
    }
}
~~~

Adapter implementing the port using RestClient:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class RestClientCatalogGateway implements CatalogGateway {

    private final RestClient client;

    RestClientCatalogGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    @Override
    public ProductDto findProduct(long id) {
        return client.get()
                .uri("/api/products/{id}", id)
                .retrieve()
                .body(ProductDto.class);
    }
}
~~~

Benefits:

- Business logic is not coupled to a specific HTTP library's API.
- Adapters can be swapped to Feign/HTTP Interface with minimal impact on the business service.
- Business unit tests only need to mock `CatalogGateway`.
- Adapters can be integration-tested separately to prove LoadBalancer and transport work.
- Consistent error contracts, logging, tracing, and timeout policies can be enforced at the gateway boundary.

Avoid building an overly complex generic abstraction just to wrap every RestClient method. The port should express **what the business needs**, rather than mirroring the entire HTTP API into a generic layer.

## 10. Comparing timeouts, pools, and retries by client

| Client | Where does connection/pool live? | Where are timeouts configured? | Retries to verify |
|---|---|---|---|
| RestTemplate | RequestFactory and underlying HTTP client | RequestFactory/transport | LB retry or resilience layer depending on config |
| RestClient | RequestFactory and underlying HTTP client | RequestFactory/transport | LB retry or resilience layer depending on config |
| WebClient | ClientConnector, usually Reactor Netty ConnectionProvider | Connect/response/pending acquire and overall deadline | Reactor retry and/or LB retry, avoid stacking layers |
| OpenFeign | Feign Client delegate, possibly HC5/OkHttp/JDK | Feign connect/read timeout and transport | Spring Cloud OpenFeign defaults to `Retryer.NEVER_RETRY`; configure explicitly |
| HTTP Interface | RestClient or WebClient adapter | Per adapter | Per adapter; the interface does not add retries itself |

### A timeout is not a single number

Distinguish between:

- **Pool acquisition timeout**: waiting for an available connection.
- **Connect timeout**: establishing TCP to the selected instance.
- **TLS handshake timeout**: completing TLS when using HTTPS.
- **Response/read timeout**: waiting for response/data according to transport semantics.
- **Overall deadline**: the entire operation, including selection, acquire, connect, response, decode, and retries.

For example, a client waiting 300ms for a pool connection, 500ms to connect, and 2s for a response can take more than 2s end-to-end. Do not assume `responseTimeout=2s` caps the whole operation.

### Retries must align with business semantics

- Do not retry indefinitely or without backoff when a downstream is overloaded.
- Only retry recoverable errors permitted by policy.
- Consider whether the request was already sent; a timeout after the server processes the request can leave an ambiguous outcome.
- For POSTs creating orders/payments, require an idempotency key or duplicate-write protection.
- Set caps on attempts and an overall deadline across layers.
- Track **logical operations** and **HTTP attempts** separately.

Not every client shares the same retry defaults. In particular, do not assume Feign retries like a WebClient `retryWhen`, or that HTTP Interface adds retries automatically just because it uses annotations.

## 11. Observability and error handling

Each client option may wrap exceptions differently, but you need a **shared operational contract**:

| Error category | Example cause | Information to record |
|---|---|---|
| `NO_INSTANCE` | Discovery/filter returns an empty list | Service ID, candidate count, policy |
| `DNS_RESOLUTION` | Logical service hostname resolved via DNS because client lacks LB, or physical host failed | Logical/physical host category, selected instance if any |
| `POOL_ACQUIRE_TIMEOUT` | Could not obtain a connection | Pool pending/leased/max, remote route |
| `CONNECT_TIMEOUT` | TCP to physical endpoint failed in time | Selected endpoint category, connect duration |
| `RESPONSE_TIMEOUT` | Backend/network did not return response in time | Service ID, instance, response duration |
| `HTTP_4XX/5XX` | Backend returned an HTTP status | Status, operation, trace ID |
| `DECODE_ERROR` | Response body does not match contract | Content type/schema category; do not log sensitive bodies |

With blocking RestClient/RestTemplate/Feign, trace spans typically follow the transport's HTTP client instrumentation. With reactive WebClient, context propagation/tracing requires the proper integration. HTTP Interface inherits the observability of its adapter and does not create a separate telemetry stack.

**Do not log full headers/bodies to debug errors.** Never log Authorization headers, cookies, raw URLs containing query tokens, or personal data. Use an allowlist consisting of service ID, operation/route template, error category, allowed instance label, duration, and trace ID.

## 12. Testing: separating unit, integration, and contract tests

| Layer | What to test? | Which clients need checking? |
|---|---|---|
| Business unit | Business rules with mocked `CatalogGateway` | Independent of specific HTTP client |
| Adapter unit | DTO mapping, status/error mapping, request parameters | Each adapter can have its own tests |
| LoadBalancer integration | Real client wired with LB, service ID resolves to instance URI | RestTemplate, RestClient, WebClient, Feign |
| HTTP Interface integration | Proxy built from the right adapter and adapter has LB | RestClient/WebClient adapter |
| Contract test | Compatible paths, headers, status codes, JSON schemas | All clients sharing the contract |
| Failure test | Empty discovery, physical host DNS, timeout, backend 5xx | Active client/transport |
| Load test | Pool, concurrency, p95/p99, retry amplification | End-to-end call path through caller |

### Integration testing principles

- Use a real Spring context for the wiring you want to verify.
- Use fake HTTP servers on dynamic ports and register URIs via `SimpleDiscoveryClient`/`@DynamicPropertySource`.
- Call the logical URL `http://catalog-service` from the configured client bean.
- Have backends return distinct `instanceId` values to prove selection.
- Disable or control retry/cache when testing a single attempt.
- Do not assert that the first call always picks A or that round-robin splits evenly over a short window.
- Write negative tests for plain clients if the test environment can control DNS; do not rely on random hostnames in CI.

Mocking a RestClient or Feign interface does not prove that the LoadBalancer interceptor is installed. At least one integration test must run over a **real HTTP transport**.

## 13. Common design mistakes

**1. Using a plain client with a service ID and expecting DNS to understand discovery.** The name `catalog-service` does not automatically become a Spring Cloud service ID.

**2. Placing `@LoadBalanced` on a builder while code builds the client from another builder.** The annotation only takes effect on the Spring-processed bean injected into the right place.

**3. Using a fixed URL in Feign while expecting LoadBalancer to pick instances.** Check both `@FeignClient(url=...)` and URL properties.

**4. Using WebClient and calling `.block()` throughout a reactive pipeline.** This can block threads and negate non-blocking benefits.

**5. Putting JDBC/JPA directly onto the event loop.** Offload blocking calls to an appropriate scheduler or use a non-blocking driver.

**6. Using one connection pool for every purpose without distinguishing routes.** Total pool and per-route/remote-host limits have different semantics.

**7. Retrying simultaneously in Feign, LoadBalancer, Reactor, and a gateway.** This can amplify attempts and trigger a retry storm.

**8. Creating a new client per request.** This loses connection pooling, customizers, and consistent observability.

**9. Letting business services depend directly on an HTTP library.** Unit testing and migration become harder.

**10. Picking a client based on trends rather than processing model.** Reactive, declarative, or fluent does not automatically make a system faster, more resilient, or easier to maintain.

## 14. Migration plan between clients

You do not need to change the entire system at once. Migrate one adapter at a time while preserving the service ID and contract.

### RestTemplate → RestClient

1. Inventory current request factory, timeouts, pools, and interceptors.
2. Create a dedicated `@LoadBalanced RestClient.Builder`.
3. Migrate a small gateway, keeping paths/DTOs/error mapping intact.
4. Compare metrics, retries, and connection pools.
5. Expand once integration tests pass.

### RestClient → HTTP Interface

1. Define the interface matching the actual endpoints/contract.
2. Create the proxy from the load-balanced RestClient.
3. Swap the gateway adapter while keeping the business port.
4. Verify path variables, headers, codecs, and exception behavior.
5. Do not add a new HTTP client/pool if the current adapter already suffices.

### Feign → HTTP Interface

1. Inventory Feign configuration: URL, encoder/decoder, interceptors, error decoder, timeouts, retries.
2. Identify whether the current client uses a service ID or a fixed URL.
3. Choose the RestClient adapter for blocking or the WebClient adapter for reactive execution.
4. Write integration/contract tests before switching.
5. Migrate one client at a time, observing error rates and latency before removing legacy Feign configuration.

### RestClient → WebClient

Only migrate when there is a reactive/streaming reason or a need for non-blocking composition. Re-check all downstream dependencies: a single blocking JDBC call in the pipeline can erase the benefits. Evaluate the event loop, connection provider, context propagation, and cancellation.

## 15. Final decision checklist

Before choosing a client for a service ID, answer:

1. Is the caller flow Spring MVC/imperative or WebFlux/reactive?
2. Is streaming/backpressure or composing multiple asynchronous requests needed?
3. Is there stable existing code worth keeping?
4. Does the team prefer a fluent API or a declarative interface?
5. If choosing HTTP Interface, is the underlying adapter RestClient or WebClient?
6. Is the actual client bean properly annotated with `@LoadBalanced`?
7. Are `spring-cloud-starter-loadbalancer` and a compatible release train present?
8. Does Feign have an explicit URL in annotations or properties?
9. Where are the pool, connect/read/response timeouts, and overall deadline managed?
10. At which layer are retries enabled, what is the total attempt count, and is the operation idempotent?
11. Are metrics/tracing in place for service ID, instance, pool, and HTTP errors?
12. Is there an integration test proving the client selects two instances over real HTTP?
13. Is there a gateway/business port decoupling business logic from the HTTP library?
14. Is there a rollout/rollback plan if changing the transport or client?

**Conclusion:** Do not choose a client merely by line count or buzzwords. For new blocking code, **RestClient** is a strong option to consider; keep **RestTemplate** if existing code is stable; choose **WebClient** when true reactive/streaming behavior is needed; use **OpenFeign** when a declarative blocking client matches team conventions; and use **HTTP Interface** when you want a Spring-native interface with control over choosing the adapter. Whichever option you pick, **LoadBalancer only works when the actual client is properly integrated**, and pools, timeouts, retries, observability, and testing must still be designed at the right layer.

**Official references:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – RestTemplate, RestClient, and WebClient LoadBalancer integrations](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework – HTTP Interface Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-http-interface)
- [Spring Cloud OpenFeign – Declarative REST Client](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
