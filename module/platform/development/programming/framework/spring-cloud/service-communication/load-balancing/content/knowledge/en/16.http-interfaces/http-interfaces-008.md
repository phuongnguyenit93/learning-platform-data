# Comparing HTTP Interface with OpenFeign Based on Project Needs

When two microservices need HTTP communication, development teams usually want calls from `order-service` to `catalog-service` to look like a Java method invocation: `catalogClient.findById("42")`. Both **Spring HTTP Service Interface** and **Spring Cloud OpenFeign** support that *declarative HTTP client* style, yet they differ in proxy creation, annotations, underlying HTTP stack, configuration, and ecosystem integrations.

This lesson belongs to the **HTTP Interface** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. The focus is choosing according to **practical project needs**, especially when calling by **service ID**, selecting a `ServiceInstance` via Spring Cloud LoadBalancer, integrating discovery/health checks, and controlling timeouts, retries, and HTTP errors. The goal is not to declare one solution universally better than the other, but to understand the **trade-offs** so you can choose or migrate intentionally.

> **Scope:** Spring Framework 6.1+ for HTTP Service Interface with `RestClientAdapter`; Spring Cloud OpenFeign compatible with your project's Spring Boot/Spring Cloud versions. APIs and configuration properties can vary by release train, so verify against your actual versions. Examples primarily show synchronous applications; the `WebClient` section illustrates the reactive option.

## 1. Two Ways to Declare the Same HTTP API

Suppose service ID `catalog-service` exposes these endpoints:

| HTTP endpoint | Purpose | Assumed Response Contract |
|---|---|---|
| `GET /api/items/{id}` | Find a single item | `200` + JSON `ItemDto` or `404` |
| `GET /api/items?category=paper` | Search by category | `200` + JSON array |
| `POST /api/items` | Create an item | `201` + JSON `ItemDto` |
| `GET /api/items/events` | Stock update stream | `200 text/event-stream` if server supports it |

DTOs used in the examples:

~~~java
record ItemDto(String id, String name, int stock) {}

record CreateItemRequest(String name, int stock) {}
~~~

These are illustrative data types. To compile in a real project, place them in appropriate packages with matching visibility; client and server do not have to share a Java DTO library.

### Spring HTTP Service Interface

~~~java
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(
    url = "/api/items",
    accept = MediaType.APPLICATION_JSON_VALUE
)
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);

    @GetExchange
    List<ItemDto> search(@RequestParam("category") String category);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    ItemDto create(
        @RequestBody CreateItemRequest body,
        @RequestHeader("X-Idempotency-Key") String idempotencyKey
    );
}
~~~

### Spring Cloud OpenFeign

~~~java
import java.util.List;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;

@FeignClient(
    name = "catalog-service",
    path = "/api/items"
)
interface CatalogFeignApi {

    @GetMapping("/{id}")
    ItemDto findById(@PathVariable("id") String id);

    @GetMapping
    List<ItemDto> search(@RequestParam("category") String category);

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ItemDto create(
        @RequestBody CreateItemRequest body,
        @RequestHeader("X-Idempotency-Key") String idempotencyKey
    );
}
~~~

Both interfaces describe **the same HTTP behavior**. However, `@GetExchange` belongs to **Spring HTTP Interface**, whereas `@GetMapping` in the Feign example is interpreted by Spring Cloud OpenFeign using its own contract. Swapping an annotation without changing the registration/proxy creation mechanism can prevent requests from being built properly.

## 2. The Most Important Difference: Who Creates the Proxy and Who Executes Requests?

~~~mermaid
flowchart TB
    App["order-service calls findById(id)"] --> X{"Declarative client used"}
    X -->|HTTP Interface| HP["HttpServiceProxyFactory"]
    HP --> AD["RestClientAdapter or WebClientAdapter"]
    AD --> LB["Spring Cloud LoadBalancer if underlying client has @LoadBalanced"]
    X -->|OpenFeign| FP["Spring Cloud OpenFeign creates Feign proxy"]
    FP --> FC["Feign Client / transport"]
    FC --> LB2["Spring Cloud LoadBalancer if integrated and URL is not fixed"]
    SUP["Discovery + ServiceInstanceListSupplier"] --> LB
    SUP --> LB2
    LB --> A["catalog-service instance"]
    LB2 --> A
~~~

**HTTP Service Interface** belongs to Spring Framework: the interface only carries metadata. To use it, the application creates an `HttpServiceProxyFactory` with an execution adapter such as `RestClientAdapter` or `WebClientAdapter`, then calls `createClient(...)`. Spring Cloud LoadBalancer is wired into the **underlying HTTP client**, not into the `@HttpExchange` annotation.

**OpenFeign** is Spring Cloud's integration of the Feign project: when `@EnableFeignClients` and matching configuration are present, Spring builds a Feign proxy from `@FeignClient`. With `name = "catalog-service"`, Feign can route by service ID through Spring Cloud LoadBalancer integration when the required dependencies and configuration exist.

Both separate the interface from business logic. What you need to weigh is **the proxy-creation mechanism and HTTP stack your team already operates**.

## 3. Dependencies and Version Requirements

For HTTP Interface using `RestClient` in a Spring Boot/Spring Cloud project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

For OpenFeign:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-openfeign'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

These snippets only illustrate the relevant dependencies; a real project needs build plugins, a BOM, and other required dependencies. `spring-cloud-starter-openfeign` is not a Spring Framework API itself; it enables Spring Cloud's Feign configuration ecosystem. `spring-cloud-starter-loadbalancer` should be present when the goal is resolving **service IDs** via Spring Cloud LoadBalancer.

To run HTTP Interface on `WebClient`, a reactive HTTP client is required:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

**Do not mix release trains arbitrarily:** for example, `RestClient` requires Spring Framework 6.1+; `HttpServiceProxyFactory` APIs, Spring Cloud OpenFeign, and timeout properties depend on the versions in your actual dependency management. Check the Spring Boot and Spring Cloud compatibility matrix before copying code.

## 4. Creating an HTTP Service Interface Proxy with `RestClient` and LoadBalancer

The HTTP Interface in section 1 does not yet have a proxy. Example bean configuration for the caller:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
class CatalogHttpInterfaceConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder lbRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    CatalogHttpApi catalogHttpApi(
            @Qualifier("lbRestClientBuilder") RestClient.Builder builder) {

        RestClient restClient = builder
            .baseUrl("http://catalog-service")
            .build();

        RestClientAdapter adapter = RestClientAdapter.create(restClient);

        HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(adapter).build();

        return factory.createClient(CatalogHttpApi.class);
    }
}
~~~

Here:

1. `@LoadBalanced` marks the builder so Spring Cloud configures service-ID URL resolution.
2. `baseUrl("http://catalog-service")` is a logical URL, not an instance hostname.
3. `RestClientAdapter.create(restClient)` connects the proxy to the synchronous `RestClient`.
4. `HttpServiceProxyFactory.createClient(CatalogHttpApi.class)` produces an object implementing the interface.
5. `@HttpExchange("/api/items")` + `@GetExchange("/{id}")` forms the path `/api/items/{id}`.

With `catalogHttpApi.findById("42")`, the HTTP client performs a **synchronous call**. HTTP status handling, connection timeouts, and response reading depend on `RestClient` and its request factory.

Do not use a standalone `RestClient.create("http://catalog-service")` assuming it gets LoadBalancer automatically; the URL can end up hitting standard DNS. Conversely, when calling external Internet APIs directly, do not accidentally use a load-balanced builder if the host is not a service ID in discovery.

## 5. Registering an OpenFeign Proxy via `@FeignClient`

With Feign, you do not invoke `HttpServiceProxyFactory` yourself. Register the interface generated by Spring Cloud OpenFeign:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

@SpringBootApplication
@EnableFeignClients(clients = CatalogFeignApi.class)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

The `CatalogFeignApi` interface already carries `@FeignClient(name = "catalog-service", path = "/api/items")`; Spring Cloud OpenFeign creates the corresponding bean and injects it into business services.

Usage:

~~~java
import org.springframework.stereotype.Service;

@Service
class ItemService {

    private final CatalogFeignApi catalog;

    ItemService(CatalogFeignApi catalog) {
        this.catalog = catalog;
    }

    ItemDto getItem(String id) {
        return catalog.findById(id);
    }
}
~~~

In real projects, `@EnableFeignClients` can use package scanning or list clients explicitly. Listing required classes avoids missing interfaces located outside the default scan package.

**Do not register both `CatalogHttpApi` and `CatalogFeignApi` simultaneously just because the examples show two options** if the application only needs one client approach. The two interfaces are **alternatives** for the same downstream; they may coexist during a migration, but need distinct bean names and clear usage boundaries.

## 6. Service IDs and `ServiceInstance` Selection

This is the shared core with the Spring Cloud LoadBalancer module.

Suppose discovery knows two instances:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

For service ID `catalog-service`, both HTTP Interface and OpenFeign can pick between A and B using the active selector.

~~~mermaid
sequenceDiagram
    participant B as Business code
    participant C as Declarative HTTP client
    participant LB as LoadBalancer
    participant S as ServiceInstanceListSupplier
    participant I as catalog-a or catalog-b

    B->>C: findById("42")
    C->>LB: Needs instance of catalog-service
    LB->>S: Fetch candidates (discovery, health, filter)
    S-->>LB: [A, B]
    LB-->>C: Select B
    C->>I: GET /api/items/42
    I-->>C: HTTP 200 + JSON
    C-->>B: ItemDto
~~~

**HTTP Interface:** the service ID normally sits in `baseUrl("http://catalog-service")` on a `@LoadBalanced` `RestClient`/`WebClient`; `@HttpExchange` defines the API path.

**OpenFeign:** `@FeignClient(name = "catalog-service")` defines the client/service name used for LoadBalancer when no fixed URL is given, and `path` sets the shared endpoint prefix.

If Feign configures `url` pointing to a fixed address, e.g., `@FeignClient(name = "catalog-service", url = "http://localhost:18081")`, the client will **call the specified URL** instead of distributing across `catalog-service` instances through normal target selection. This semantic shift must be noted carefully when moving configuration from dev to staging/production.

Likewise, with HTTP Interface, using a non-load-balanced builder with a direct host `baseUrl` bypasses Spring Cloud LoadBalancer. **Interface names or bean names do not activate service discovery automatically.**

## 7. Comparing Annotations and Request Representation

| Need | HTTP Service Interface | OpenFeign |
|---|---|---|
| Marking the interface | `@HttpExchange` | `@FeignClient` |
| URL prefix | `@HttpExchange(url = "/api/items")` | `@FeignClient(path = "/api/items")` |
| GET | `@GetExchange("/{id}")` | `@GetMapping("/{id}")` |
| POST | `@PostExchange` | `@PostMapping` |
| PUT/PATCH/DELETE | `@PutExchange`, `@PatchExchange`, `@DeleteExchange` | `@PutMapping`, `@PatchMapping`, `@DeleteMapping` |
| Path variable | `@PathVariable("id")` | `@PathVariable("id")` |
| Query | `@RequestParam("category")` | `@RequestParam("category")` |
| Request body | `@RequestBody` | `@RequestBody` |
| Request header | `@RequestHeader` | `@RequestHeader` |
| Content negotiation | `accept`, `contentType` on exchange annotations | `produces`, `consumes` on mappings per contract |
| Advanced request parameters | Per HTTP Interface argument resolvers/adapters | Per Feign contract, encoders, capabilities |

**Note:** identically named annotations such as `@PathVariable` and `@RequestBody` come from Spring MVC packages, yet both mechanisms leverage them in a client context. Conversely, `@GetExchange` and `@GetMapping` **cannot be swapped arbitrarily**; each framework has its own metadata reader and contract.

### A Very Common URL Concatenation Mistake

HTTP Interface:

~~~java
@HttpExchange("/api/items")
interface CatalogHttpApi {

    // Correct: add only the endpoint segment
    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

OpenFeign:

~~~java
@FeignClient(name = "catalog-service", path = "/api/items")
interface CatalogFeignApi {

    // Correct: add only the endpoint segment
    @GetMapping("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

Repeating `/api/items` on the method annotation creates duplicated or wrong paths. Always verify the actual emitted request URL rather than just reading method names.

## 8. Synchronous, Reactive, and Streaming

A major selection criterion is the **application's request-handling model**.

### HTTP Interface via `RestClientAdapter`

HTTP Service Interface can use `RestClientAdapter` with return types such as:

~~~java
ItemDto findById(String id);
ResponseEntity<ItemDto> getEntity(String id);
void delete(String id);
~~~

`RestClient` is a **blocking client**. If a Spring MVC thread calls three services sequentially, wait times add up. The label "declarative interface" does not make calls non-blocking.

### HTTP Interface via `WebClientAdapter`

You can create a proxy via `WebClientAdapter` backed by a `@LoadBalanced` `WebClient`. The interface can then declare:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record StockEvent(String sku, int quantity) {}

@HttpExchange("/api/items")
interface ReactiveCatalogHttpApi {

    @GetExchange("/{id}")
    Mono<ItemDto> findById(@PathVariable("id") String id);

    @GetExchange(
        url = "/events",
        accept = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<ServerSentEvent<StockEvent>> streamEvents();
}
~~~

Creating the proxy:

~~~java
WebClient webClient = lbWebClientBuilder
    .baseUrl("http://catalog-service")
    .build();

HttpServiceProxyFactory factory =
    HttpServiceProxyFactory.builderFor(
        WebClientAdapter.create(webClient))
        .build();

ReactiveCatalogHttpApi api =
    factory.createClient(ReactiveCatalogHttpApi.class);
~~~

In this abbreviated snippet, `lbWebClientBuilder` is a Spring-managed `WebClient.Builder` annotated with `@LoadBalanced`. In complete code, import `WebClient`, `WebClientAdapter`, and `HttpServiceProxyFactory` as shown in the configuration sections.

`Mono<T>` and `Flux<T>` fit non-blocking pipelines and SSE streaming. However, HTTP Interface itself does not produce reactive execution; **the adapter determines the HTTP stack**. Avoid calling `block()` inside a WebFlux event-loop.

### OpenFeign

Spring Cloud OpenFeign primarily uses a **synchronous** invocation model. Do not assume you can simply change a `@FeignClient` return type to `Mono<T>`/`Flux<T>` and get a reactive HTTP client equivalent to `WebClient`. If a project requires non-blocking streaming, choose `WebClientAdapter` or an explicitly supported reactive technology.

| Need | Consideration |
|---|---|
| Spring MVC, short request-response calls, team familiar with Feign | Either OpenFeign or HTTP Interface + `RestClient` works well |
| New app wanting to use Spring Framework's HTTP stack directly | HTTP Interface + `RestClient`/`WebClient` |
| WebFlux needing `Mono`/`Flux` and long-lived SSE | HTTP Interface + `WebClientAdapter` is usually a better fit |
| Project with many existing Feign clients, error decoders, and mature config | Keep OpenFeign until there is a clear reason to migrate |
| Need to swap HTTP transport or tune connection pooling | Verify actual transport customization capabilities of each option and dependency |

Do not choose purely by line count of declarations: account for maintainability, threading model, observability, and existing project integrations.

## 9. How Do HTTP Errors and Exceptions Differ?

Suppose the backend returns `404` when an item is missing and `503` when overloaded.

**HTTP Interface via `RestClientAdapter`** normally uses `RestClient` status handling. Unhandled HTTP `4xx/5xx` statuses can throw exceptions in the `RestClientResponseException` hierarchy. You can configure a default status handler when building `RestClient` or handle exceptions at the service layer.

**HTTP Interface via `WebClientAdapter`** uses `WebClient`; HTTP status errors normally surface as error signals such as `WebClientResponseException`. Reactive apps should handle them via `onErrorResume`, `onErrorMap`, or a suitable resilience layer, not `try/catch` around merely constructing a `Mono`.

**OpenFeign** typically represents error statuses with `FeignException` or a custom exception returned by an `ErrorDecoder`.

Categorized handling example in Feign:

~~~java
import feign.FeignException;

try {
    ItemDto item = catalogFeignApi.findById("missing");
} catch (FeignException.NotFound ex) {
    // HTTP 404 from backend: handle per contract.
} catch (FeignException ex) {
    int httpStatus = ex.status();
    // Check 429, 503, transport, and business policy.
}
~~~

Exact exception classes depend on Feign's transport and `ErrorDecoder`. If a custom decoder throws domain exceptions, `catch` blocks differ accordingly.

Example with HTTP Interface + `RestClient`:

~~~java
import org.springframework.web.client.RestClientResponseException;

try {
    ItemDto item = catalogHttpApi.findById("missing");
} catch (RestClientResponseException ex) {
    int status = ex.getStatusCode().value();
    // Received error HTTP response from endpoint.
}
~~~

**Neither example covers every connection failure.** When no `ServiceInstance` can be selected, or on connect timeout, TLS handshake failure, or server reset before response, there may be no backend HTTP status to decode.

| Scenario | HTTP Interface / `RestClient` | OpenFeign |
|---|---|---|
| HTTP 404 | Status handler or `RestClientResponseException` | `FeignException.NotFound` or `ErrorDecoder` |
| HTTP 503 | Status handler or `RestClientResponseException` | `FeignException` / `ErrorDecoder` |
| No instance available | LoadBalancer error before HTTP | LoadBalancer/Feign client error before HTTP |
| Connect timeout | Transport/client error | Transport/client error depending on Feign HTTP stack |
| JSON incompatible with DTO | Message conversion error | Decoder error |
| Fallback | Configured in wrapper/resilience layer | Requires circuit breaker/fallback integration |

**Do not compare solely by raw exception class names.** Standardize mapping to domain errors such as `ITEM_NOT_FOUND`, `DOWNSTREAM_UNAVAILABLE`, and `TIMEOUT` at the application boundary. Separate *no instance available* from *backend returned HTTP 503* for accurate diagnosis.

## 10. Timeouts and Retries: Annotations Do Not Guarantee Reliability

Both approaches make HTTP calls over the network, so timeouts and retry caps are essential.

### HTTP Interface: Configure on the Underlying Client

Example using a request factory for `RestClient`:

~~~java
import org.springframework.http.client.SimpleClientHttpRequestFactory;

SimpleClientHttpRequestFactory requestFactory =
    new SimpleClientHttpRequestFactory();

requestFactory.setConnectTimeout(2000);
requestFactory.setReadTimeout(3000);

RestClient restClient = lbRestClientBuilder
    .requestFactory(requestFactory)
    .baseUrl("http://catalog-service")
    .build();
~~~

This **replaces** the `RestClient` creation inside the bean configuration above rather than registering a second bean. Both values are milliseconds in this request factory API; production systems may use Apache HttpComponents or another transport with connection pooling and corresponding settings.

### OpenFeign: Configure by Client Name

In `application.yml`, you can configure:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            connectTimeout: 2000
            readTimeout: 3000
            loggerLevel: basic
~~~

The name `catalog-service` must match the configured Feign client. Timeouts above are interpreted in milliseconds in standard Spring Cloud OpenFeign configuration; verify your exact version and active transport.

A practical advantage of OpenFeign in systems with many clients is its **built-in per-client-name configuration system**. With HTTP Interface, teams typically define beans/configurations per proxy group or establish conventions for shared base URLs, timeouts, and headers.

### Retries Differ, Yet Both Carry Risk

Do not assume Spring Cloud OpenFeign and HTTP Interface retry the same errors under the same policy by default. Spring Cloud OpenFeign commonly defaults to `Retryer.NEVER_RETRY` per its documentation, unlike certain Feign core defaults; verify during upgrades or when declaring a custom `Retryer`.

HTTP Interface has no built-in retry simply because a method bears `@GetExchange`. Retries live in the underlying client, LoadBalancer, Resilience4j/Spring Retry, or application-level Reactor operators such as `retryWhen`.

General principles:

- Classify recoverable errors before retrying: connect timeouts, HTTP 429/503 per contract, overload signals.
- Cap **total attempts, backoff, and overall deadline**; avoid stacking retries across client, gateway, and service mesh.
- For `POST`/`PATCH` or side-effecting operations, retry only when genuine idempotency/deduplication exists.
- Verify whether retries pick the same instance or a different one; framework names do not guarantee target switching.
- Tune connection pooling and concurrency limits so retries do not trigger retry storms.

A request that reached the server and succeeded while its response was lost can execute again. **This is a distributed semantics problem**, not something client annotations can solve alone.

## 11. Circuit Breakers and Fallbacks

Some teams prefer Feign because of its familiar fallback declaration:

~~~java
@FeignClient(
    name = "catalog-service",
    path = "/api/items",
    fallback = CatalogFallback.class
)
interface CatalogFeignApi {
    @GetMapping("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

This **illustrates a Feign fallback configuration**; it will not work simply by copying the interface snippet. For fallbacks to run, you need Spring Cloud CircuitBreaker integration, dependencies, properties enabling circuit breakers, a `CatalogFallback` Spring bean implementation, and version-compatible wiring. Never treat `fallback=...` as an automatic `try/catch` in every Feign project.

With HTTP Interface, resilience is usually placed in a wrapper around the proxy — for example, a `CatalogGateway` calling `CatalogHttpApi` and applying a circuit breaker, fallback, or bulkhead using the project's chosen library. This requires slightly more wiring code, yet keeps a clean boundary between **transport API** and **business recovery policy**.

A safe business fallback might return a read-only cached value marked stale while catalog is temporarily unavailable. By contrast, for **creating orders, deducting stock, or charging payments**, a fallback pretending success when downstream never ran can cause severe data corruption.

When deciding, ask operations: does this API endpoint truly permit a fallback, should circuit breakers be per service or per endpoint, and are data errors separated from infrastructure failures?

## 12. Logging, Tracing, Authentication, and Shared Configuration

Client tooling cannot replace observability and security. Both approaches require:

- Correlation/trace IDs across caller and downstream.
- Metrics for HTTP request duration, status, timeouts, retry attempts, and selected instance.
- Categorized error logs that never print access tokens, cookies, or sensitive bodies.
- Clear service-to-service authentication and authorization scopes.
- Explicit rules for token propagation when user context must travel downstream.

**HTTP Interface:** configuration centers on the builder and adapter. With `RestClient`, use request interceptors, default headers, or Spring/Boot observation integration; with `WebClient`, use filters and connector configuration.

**OpenFeign:** provides extension points such as `RequestInterceptor`, `ErrorDecoder`, `Logger.Level`, encoders/decoders, and capabilities depending on config. Micrometer/Observation integration is available when supporting dependencies and settings are enabled. Do not assume every metric is emitted identically across all release trains.

A dynamic request header can be declared on either interface style:

~~~java
ItemDto findById(
    @PathVariable("id") String id,
    @RequestHeader("X-Correlation-Id") String correlationId
);
~~~

If an interface already has a method taking only `id`, this example is an **alternative signature**, not an extra overload to register alongside it. For automatic trace propagation, prefer standard instrumentation instead of manually threading headers across dozens of methods.

### Per-Downstream Configuration

When a project calls many services:

| Goal | HTTP Interface | OpenFeign |
|---|---|---|
| URL by service ID | Each proxy uses an underlying client with a logical base URL | `@FeignClient(name=...)` when using discovery |
| Per-downstream timeouts | Build client/builder/proxy per group | Configure `openfeign.client.config.<name>` |
| Shared headers | `RestClient` interceptors or `WebClient` filters | `RequestInterceptor` or Feign config |
| Custom error mapping | Status handlers/mappers on adapter or gateway | Per-client `ErrorDecoder` |
| Custom retry policy | Resilience layer or HTTP stack | `Retryer`/circuit-breaker integration |
| Logging | Spring HTTP client + observation | Feign logging/capability + observation |
| Authentication | HTTP client interceptors/filters | Interceptors and OAuth2 integration if used |

As the number of downstreams grows, configuration consistency matters more than short interface syntax: standardize naming, default timeouts, exception mapping, and contract tests.

## 13. Testing: Verifying Contract, Service ID, and Real Failures

Tests should be separated into three layers:

1. **Business unit tests:** mock `CatalogHttpApi` or `CatalogFeignApi` to test DTO/exception handling without network calls.
2. **HTTP client contract tests:** use a mock HTTP server such as WireMock, MockWebServer, or a test server to verify HTTP method, path, query, headers, body, and status mapping.
3. **LoadBalancer integration tests:** two real or stub instances registered via discovery, verifying service ID resolution and instance selection under a stable instance list.

Mocking only the interface does not prove your annotations produce the right URL. Testing against only one real backend does not prove LoadBalancer distribution.

### Shared Test Matrix for Both Clients

| Scenario | HTTP Interface | OpenFeign |
|---|---|---|
| GET by ID | Proxy emits exact `GET /api/items/{id}` | Feign emits exact `GET /api/items/{id}` |
| Query and body | `@RequestParam`/`@RequestBody` encoded accurately | Spring MVC contract encoded accurately |
| Idempotency header | Value sent with request | Value sent with request |
| HTTP 404 | Mapped via `RestClient`/`WebClient` | Mapped via `ErrorDecoder` |
| HTTP 503 | Classified as downstream error | Classified as downstream error |
| No instance available | Fails before HTTP response | Fails before HTTP response |
| Instance stops after selection | Transport error/timeout | Transport error/timeout |
| `POST` retry | Must not create duplicate resources if contract deduplicates | Same |
| Tracing | Captures service ID, downstream, status | Captures service ID, downstream, status |
| API schema change | DTO/codec catches mismatch | DTO/decoder catches mismatch |

To verify two instances, have the backend return an `X-Instance-Id` header or `instanceId` field in test environments only and invoke repeatedly. Never expose internal addresses or sensitive operational metadata in public APIs.

### Static Discovery Setup for Lab

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Start two backend instances under the same service ID and use the default Round Robin or an explicitly configured policy. A short burst of calls may not split evenly if there are concurrent callers, health probes, or caches; measure enough invocations and inspect logs and supplier state.

## 14. Tool Selection Matrix by Project Type

| Project Need | Usually Better Fit | Rationale / Condition |
|---|---|---|
| New project already using `RestClient`/`WebClient` wanting fewer client-specific dependencies | **HTTP Interface** | Builds directly on Spring Framework's active HTTP stack |
| Mature project with many stable `@FeignClient` definitions | **Keep OpenFeign** if it meets goals | Avoid low-value migrations; team already has tooling and contracts |
| Simple blocking Spring MVC API | **Either** | Choose based on config, error handling, and team experience |
| Non-blocking WebFlux, SSE, or long-lived streaming | **HTTP Interface + `WebClientAdapter`** | Returns `Mono`/`Flux` with proper subscription management |
| Want per-client config by service name via built-in properties | **OpenFeign** has an edge | Mature per-client property ecosystem |
| Want direct control over Spring's HTTP stack, filters, and request factories | **HTTP Interface** has an edge | Adapter wraps your `RestClient`/`WebClient` directly |
| Need existing Feign fallbacks wired with circuit breakers | **Keep OpenFeign** until an equivalent is ready | Fallbacks do not appear automatically on HTTP Interface |
| Only a few downstreams and want minimal framework machinery | **HTTP Interface** is often simpler | A few explicit proxies with minimal extra framework layers |
| Special encoder, multipart, OAuth, or logging requirements | **Evaluate with a spike** | Extension points differ; verify integration end-to-end |
| Need gRPC, Kafka, or event sourcing | **Not solved by picking either** | Both are HTTP clients; revisit protocol/architecture |

Do not treat this matrix as a fixed performance ranking. **Real throughput and latency** depend on transport, connection pooling, server capacity, concurrency, serialization, circuit breakers, and tuning — not just annotations or proxy-generation frameworks.

### Five Decision Questions

1. **Execution model:** is the application built on Spring MVC/blocking or WebFlux/reactive?
2. **Existing assets:** how many stable Feign clients, decoders/interceptors/fallbacks, and integration tests exist?
3. **Operational needs:** how much per-service configuration, telemetry, and retry customization is required?
4. **Customization level:** does the org standardize on `RestClient`/`WebClient`, or is it heavily invested in Feign?
5. **Migration cost:** is there a real technical gap unmet by the current tool, or only a desire to change annotation style?

## 15. Migration Workflow from Feign to HTTP Interface

If you decide to migrate some Feign clients, never do a repository-wide search-and-replace from `@GetMapping` to `@GetExchange`. Follow a controlled process:

1. **Inventory** each Feign client: service name, path, headers, timeouts, retries, error decoders, interceptors, fallbacks, circuit breakers, auth, and tests.
2. **Pick one simple client** (usually a GET without complex streaming or multipart) as a proof-of-concept.
3. **Write an equivalent HTTP Interface** with `@HttpExchange` and matching annotations; preserve the HTTP/DTO contract.
4. **Create the proxy via an adapter** with a `@LoadBalanced` `RestClient.Builder` or `WebClient.Builder` and `baseUrl("http://service-id")`.
5. **Port resilience policies**: status mapping, timeouts, retry budgets, idempotency, circuit breakers, and fallbacks.
6. **Compare actual HTTP requests** against a stub server; check path, query, headers, body, media types, and encoding.
7. **Run discovery/LoadBalancer integration tests** with at least two instances plus empty-list and dead-instance cases.
8. **Add equivalent logging/metrics/tracing** before shifting traffic; verify security headers.
9. **Roll out gradually**, watching error rates and p95/p99 latency; keep a rollback path if contracts or observability shift.
10. **Remove Feign dependencies** only after confirming no remaining clients, configs, or capabilities rely on them.

Common migration mistakes:

- Setting `baseUrl` to a physical host instead of the service ID, accidentally dropping LoadBalancer.
- Removing `@EnableFeignClients` while some Feign clients still remain during a partial migration.
- Losing per-service timeouts by sharing an uncloned `RestClient.Builder`.
- Changing exception types without updating exception mapping in business services.
- Forgetting to port error decoders/fallbacks or HTTP 404/503 rules.
- Allowing previously controlled `POST` retries to duplicate across both gateway and the new client.
- Switching code from blocking to reactive while still calling `block()` on the event loop.
- Copying method annotations with duplicated URL prefixes or wrong media types.

A successful migration proves **HTTP behavior and SLOs do not regress**, not merely that the project compiles.

## 16. Controlled Comparison Lab

**Context:** `order-service` calls `catalog-service` running two local instances on `localhost:18081` and `localhost:18082`. Both instances expose `GET /api/items/42` and return an `X-Instance-Id` header to identify the target in the lab.

### Experiment A — HTTP Interface

- Define `CatalogHttpApi` and the `CatalogHttpInterfaceConfiguration` bean per sections 1 and 4.
- Configure static discovery for `catalog-service`.
- Call `catalogHttpApi.findById("42")` multiple times; record the actual method/path at the backend and the selected instance.
- Query a non-existent ID to trigger HTTP 404 and observe `RestClient` exception mapping.
- Stop one instance without updating discovery; observe failures while the supplier still lists that instance.

### Experiment B — OpenFeign

- Swap the proxy for `CatalogFeignApi` and enable `@EnableFeignClients`.
- Use the same service ID, discovery list, and endpoints.
- Re-run all cases from Experiment A; compare the emitted HTTP requests and exception types.
- Intentionally configure a short timeout via `openfeign.client.config.catalog-service`; compare with the corresponding HTTP Interface timeout.
- If measuring retries, enable a separate policy per option with the same total deadline and error conditions.

### Results Recording Table

| Criterion | HTTP Interface | OpenFeign |
|---|---|---|
| Interface signature | `@HttpExchange` / `@GetExchange` | `@FeignClient` / `@GetMapping` |
| Actual method/path/query | Record result | Record result |
| Selected service ID | Record from logs/traces | Record from logs/traces |
| Instances hit | Record result | Record result |
| HTTP 404 -> app error type | Record result | Record result |
| HTTP 503 -> app error type | Record result | Record result |
| Connect/read timeout | Record result | Record result |
| Retry attempts | Record result | Record result |
| Security/correlation headers | Verify | Verify |
| p95 latency and resources | Measure under identical conditions | Measure under identical conditions |

Never assume the option with fewer lines of code has lower latency. When benchmarking, hold backend, payload, pools, concurrency, and attempt counts constant to avoid unfair comparisons.

## 17. Architecture Checklist and Conclusion

Before choosing HTTP Interface or OpenFeign, confirm that:

- The team clearly understands **service IDs** and how discovery/health suppliers provide instances.
- HTTP Interface creates proxies via `RestClientAdapter`/`WebClientAdapter` with a **load-balanced underlying client** when needed.
- OpenFeign uses `@FeignClient(name=...)` properly without accidentally setting a fixed `url` when instance distribution is intended.
- Annotation syntax and path prefixes are verified by HTTP tests, not just Java compilation.
- The blocking/reactive model aligns with the web stack and application SLOs.
- Status mapping, decoders, exceptions, timeouts, retries, deadlines, and fallbacks form a consistent contract.
- Write operations enforce idempotency and the system prevents retry storms.
- Connection pools, health checks, caches, zones, and selection policies are tuned to requirements.
- Tracing, logs, and metrics clearly separate instance-selection failures, connection failures, HTTP 4xx/5xx, and decode errors.
- If migrating, contract tests, performance benchmarks, and a rollback plan are in place.

**Conclusion:** **Spring HTTP Service Interface** fits well when you want type-safe declarative HTTP directly on Spring Framework's HTTP stack, especially with `RestClient` or `WebClient` and reactive/streaming needs. **Spring Cloud OpenFeign** fits well when a project already has a stable Feign ecosystem leveraging per-client configuration, encoders/decoders, interceptors, and resilience integrations. Both can route through **Spring Cloud LoadBalancer**, provided the underlying client is configured properly so logical hostnames resolve to `ServiceInstance` targets. The best choice is the one that satisfies your project's **API contracts, execution model, operational needs, and maintenance cost** — not the one with shorter annotations.
