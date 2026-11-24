# Connecting HTTP Interfaces with `RestClient` or `WebClient` Adapters

## Goal and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot connects systems via HTTP clients, databases, caches, message brokers, and Spring Integration adapters. An integration flow often needs to call Catalog, Inventory, or Payment services over HTTP. If every call site manually assembles URLs, builds requests, decodes JSON, and checks errors, code becomes duplicated and partner contracts become hard to govern.

Spring Framework's **HTTP interface** lets you describe client-side APIs using **Java interfaces and annotations** such as `@HttpExchange`, `@GetExchange`, or `@PostExchange`. `HttpServiceProxyFactory` then creates a proxy that executes HTTP calls through an **adapter**:

- `RestClientAdapter`: connects to synchronous `RestClient`.
- `WebClientAdapter`: connects to `WebClient`, suited for reactive return types like `Mono` and `Flux`.

This lesson belongs to the **HTTP interface** chapter, focusing on **connecting HTTP interfaces with `RestClient` or `WebClient` adapters** and applying them in Spring Boot integration architecture. Examples incorporate configuration management, data contracts, transactions, error handling, deduplication, testing, and observability.

After this lesson, you will be able to:

1. Create an HTTP interface using `@HttpExchange` and HTTP method-specific annotations.
2. Register an HTTP client proxy using `RestClientAdapter` or `WebClientAdapter`.
3. Inject Spring Boot-managed builders to retain HTTP settings, codecs, and observation instrumentation.
4. Choose synchronous or reactive return types according to how the application consumes data.
5. Separate the HTTP proxy from the business adapter, map 404/429/5xx errors, and set appropriate timeouts/retries.
6. Test methods, URLs, headers, request bodies, response bodies, and configuration wiring without calling real partner systems.

> **Boundary:** An HTTP interface is strictly a **client-side contract** and HTTP execution proxy. It does not create server APIs, does not generate distributed transactions, does not perform default retries/idempotency for every request, and does not guarantee downstream executes business logic exactly once.

## 1. What Problem Does an HTTP Interface Solve?

Instead of letting multiple services manipulate `RestClient` directly:

~~~java
// Each caller rewrites the HTTP request:
ProductDto product = restClient.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .body(ProductDto.class);
~~~

you define a single interface:

~~~java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(url = "/v1/products", accept = "application/json")
public interface CatalogHttpApi {

    @GetExchange("/{id}")
    ProductDto findById(@PathVariable("id") String id);
}
~~~

Callers then simply invoke:

~~~java
ProductDto product = catalogHttpApi.findById("P-100");
~~~

`CatalogHttpApi` is an **HTTP specification**, and does not gain an implementation merely from annotations. A proxy bean must be created via `HttpServiceProxyFactory` and an appropriate adapter.

~~~mermaid
flowchart LR
    A["Order / Catalog use case"] --> B["CatalogGateway"]
    B --> C["CatalogHttpApi interface"]
    C --> D["HttpServiceProxyFactory proxy"]
    D --> E{"HttpExchangeAdapter"}
    E -->|"Blocking"| F["RestClientAdapter"]
    E -->|"Reactive"| G["WebClientAdapter"]
    F --> H["RestClient"]
    G --> I["WebClient"]
    H --> J["Catalog HTTP API"]
    I --> J
~~~

Separate two easily confused concepts:

- **Spring Framework's `RestClientAdapter` / `WebClientAdapter`** bridges the HTTP service proxy to the underlying HTTP client.
- **Application business adapter `CatalogGateway`** translates HTTP errors, DTOs, and technical outcomes into business contracts for use cases.

An HTTP interface is a **consumer-side contract**. The partner's server can be written on any platform as long as it adheres to this HTTP contract. Client-side annotations do not cause the server to expose corresponding endpoints.

## 2. Key Components and APIs

| Component | Role | Example |
| --- | --- | --- |
| `@HttpExchange` | Sets shared HTTP metadata at interface or method level | Base path, Accept/Content-Type |
| `@GetExchange` | Declares HTTP GET | Fetch product by ID |
| `@PostExchange` | Declares HTTP POST | Create or trigger processing |
| `@PutExchange`, `@PatchExchange`, `@DeleteExchange` | Declare remaining HTTP methods | Update, delete resources |
| `@PathVariable` | Populates variables in URI templates | `/v1/products/{id}` |
| `@RequestParam` | Creates query parameters | `?active=true` |
| `@RequestHeader` | Adds headers to requests | `Idempotency-Key` |
| `@RequestBody` | Serializes payload into request body | JSON DTO |
| `@RequestPart` | Part of a multipart request | Upload file/metadata |
| `HttpServiceProxyFactory` | Creates dynamic proxy for interface | `createClient(CatalogHttpApi.class)` |
| `RestClientAdapter` | Connects proxy to RestClient | Blocking client |
| `WebClientAdapter` | Connects proxy to WebClient | Reactive client |
| `RestClient.Builder` / `WebClient.Builder` | Configures baseUrl, headers, interceptors/filters, and transport | Boot-injected builder |

A single URL can be composed from annotations at multiple levels. For instance, `@HttpExchange(url = "/v1/products")` on the interface and `@GetExchange("/{id}")` on the method produce `/v1/products/{id}`. The root URL `https://catalog.example.org` is configured on the HTTP client builder.

### 2.1. Common Parameter Types

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(
        url = "/v1/products",
        accept = MediaType.APPLICATION_JSON_VALUE)
public interface CatalogHttpApi {

    @GetExchange("/{id}")
    ProductDto findById(@PathVariable("id") String id);

    @GetExchange
    ProductPageDto list(
            @RequestParam("page") int page,
            @RequestParam("size") int size,
            @RequestParam("active") boolean active);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    ProductDto create(
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestBody CreateProductRequest request);
}
~~~

When using `@PathVariable` / `@RequestParam`, specify the name explicitly in the annotation so the code does not rely on compiler flags preserving parameter names. This is a Java interface: methods have no bodies because the proxy executes the calls.

Java 17+ DTO examples:

~~~java
public record ProductDto(
        String id,
        String name,
        boolean active) {
}

public record CreateProductRequest(String name) {
}

public record ProductPageDto(
        java.util.List<ProductDto> items,
        int page,
        long totalElements) {
}
~~~

These records only illustrate the JSON contract. In practice, you must agree on exact field names, nullability rules, API versioning, ID semantics, pagination, and empty list behavior.

### 2.2. Return Types Determine Usage

| HTTP Interface Return Type | Suitable For | Notes |
| --- | --- | --- |
| `ProductDto` | `RestClientAdapter` / synchronous apps | Caller waits until the request finishes |
| `ResponseEntity<ProductDto>` | Blocking client | Needed when status/headers are required beyond the body |
| `void` | Calls with no response payload | Does not imply downstream definitely committed side effects |
| `Mono<ProductDto>` | `WebClientAdapter` | HTTP executes only when publisher is subscribed |
| `Flux<ProductDto>` | `WebClientAdapter` | Streaming/JSON collection contract must be verified |
| `Mono<ResponseEntity<ProductDto>>` | `WebClientAdapter` | Needs status, headers, and body in a reactive flow |

`RestClientAdapter` serves **blocking** models, so do not declare a method returning `Mono` just to make the interface look like WebClient. To support reactive flows, choose `WebClientAdapter` and declare corresponding return types. Some versions allow `WebClientAdapter` to handle synchronous methods by blocking, but that does not make the method non-blocking; use only when you understand the thread and timeout implications.

## 3. Dependencies and Version Requirements

### 3.1. `RestClient`

`RestClient` was introduced in **Spring Framework 6.1** and supported in Spring Boot starting with **3.2**. Common Gradle setup for a Spring MVC application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Boot 4 may split certain web MVC starters under updated naming; projects must use the starters supported by their **actual Boot version**. This lesson focuses on Spring Framework APIs and does not depend on a single major version to explain the proxy mechanism.

### 3.2. `WebClient`

`WebClient` belongs to Spring WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Adding the WebFlux starter to use `WebClient` inside an MVC application **does not automatically turn an MVC server into a reactive server** when Spring Web MVC is already present. Still, return type choices and blocking points must align with the caller's execution model.

Spring HTTP interfaces have existed since Spring Framework 6.0. Several `HttpServiceProxyFactory` and adapter APIs changed names or builders across 6.x releases; examples below use the common factory creation pattern in Spring Framework **6.1+ and 7.x**:

~~~java
HttpServiceProxyFactory.builderFor(adapter)
        .build()
        .createClient(MyApi.class);
~~~

Older guides targeting Spring 6.0 may show `HttpServiceProxyFactory.builder(...)` or different adapter APIs. Do not mix imports and APIs across versions. If an application is on Spring Boot 3.0/3.1, verify `RestClient` availability, as `RestClient` did not yet exist in those underlying Spring Framework lines.

## 4. Using `RestClientAdapter` for Synchronous HTTP Interfaces

### 4.1. Externalizing Endpoint Configuration

Suppose the Catalog API has different addresses per environment:

~~~yaml
# application.yml
integrations:
  catalog:
    base-url: ${CATALOG_BASE_URL:https://catalog.example.org}
~~~

`https://catalog.example.org` is an illustrative address. In production, use the official URL and supply secrets from a secret manager or environment variables. Do not commit real usernames, tokens, or API keys to version-controlled files.

Bind configuration with `@ConfigurationProperties`:

~~~java
// CatalogHttpProperties.java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integrations.catalog")
public record CatalogHttpProperties(URI baseUrl) {
}
~~~

`@ConfigurationProperties` enforces type safety and makes binding easy to test. In production, validate required values and allowed schemes/hosts using Bean Validation or custom validation; the record stays concise here to focus on connecting the interface to the client.

### 4.2. Building `RestClient` and Connecting to `HttpServiceProxyFactory`

~~~java
// CatalogRestClientConfiguration.java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogHttpProperties.class)
public class CatalogRestClientConfiguration {

    @Bean
    CatalogHttpApi catalogHttpApi(
            RestClient.Builder bootRestClientBuilder,
            CatalogHttpProperties properties) {

        RestClient restClient = bootRestClientBuilder
                .baseUrl(properties.baseUrl().toString())
                .defaultHeader(
                        "Accept", MediaType.APPLICATION_JSON_VALUE)
                .build();

        RestClientAdapter adapter =
                RestClientAdapter.create(restClient);

        HttpServiceProxyFactory proxyFactory =
                HttpServiceProxyFactory.builderFor(adapter).build();

        return proxyFactory.createClient(CatalogHttpApi.class);
    }
}
~~~

Explanation:

1. Spring Boot injects a Boot-configured `RestClient.Builder`.
2. The builder receives Catalog's dedicated base URL.
3. `build()` produces a thread-safe `RestClient` reusable across requests.
4. `RestClientAdapter.create(restClient)` wraps `RestClient` in the `HttpExchangeAdapter` contract expected by the factory.
5. `HttpServiceProxyFactory.builderFor(adapter).build()` configures the proxy factory.
6. `createClient(CatalogHttpApi.class)` returns an interface implementation registered as the `catalogHttpApi` bean.

Note that `Accept: application/json` is already declared in `@HttpExchange(accept = ...)` on the interface; the default header on the builder here only demonstrates builder customization. A project should standardize a single source for headers to avoid redundant configuration.

### 4.3. Calling from an Application Service

~~~java
// CatalogLookupService.java
import org.springframework.stereotype.Service;

@Service
public class CatalogLookupService {

    private final CatalogHttpApi catalogApi;

    public CatalogLookupService(CatalogHttpApi catalogApi) {
        this.catalogApi = catalogApi;
    }

    public ProductDto load(String productId) {
        return catalogApi.findById(productId);
    }
}
~~~

`load(...)` is a **synchronous** call: the calling thread waits for the HTTP response or an error/timeout. In a Spring MVC controller this is straightforward; on a WebFlux event-loop thread, never invoke blocking calls on the event loop.

**Why inject Boot's builder?** It can come pre-configured with request factories, message converters, HTTP client observations, and version-appropriate customizers. Calling `RestClient.create(...)` directly is still a valid API, but it does not automatically inherit customizations Boot applies to its managed builder.

## 5. Using `WebClientAdapter` for Reactive HTTP Interfaces

A reactive interface should express results with `Mono` / `Flux`. To avoid mixing two different contracts, create a separate interface targeting the same server API:

~~~java
// CatalogReactiveHttpApi.java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import reactor.core.publisher.Mono;

@HttpExchange(url = "/v1/products", accept = "application/json")
public interface CatalogReactiveHttpApi {

    @GetExchange("/{id}")
    Mono<ProductDto> findById(
            @PathVariable("id") String id);
}
~~~

Spring Boot creates and manages `WebClient.Builder` when the appropriate dependencies/conditions are met. Creating the proxy:

~~~java
// CatalogWebClientConfiguration.java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogHttpProperties.class)
public class CatalogWebClientConfiguration {

    @Bean
    CatalogReactiveHttpApi catalogReactiveHttpApi(
            WebClient.Builder bootWebClientBuilder,
            CatalogHttpProperties properties) {

        WebClient webClient = bootWebClientBuilder
                .baseUrl(properties.baseUrl().toString())
                .build();

        WebClientAdapter adapter =
                WebClientAdapter.create(webClient);

        HttpServiceProxyFactory factory =
                HttpServiceProxyFactory.builderFor(adapter).build();

        return factory.createClient(
                CatalogReactiveHttpApi.class);
    }
}
~~~

Both proxies can be registered in the same application, though when a module follows one calling style consistently, registering only the matching client avoids unnecessary resources and configuration.

### 5.1. Using the Proxy in a Reactive Service

~~~java
// CatalogReactiveGateway.java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CatalogReactiveGateway {

    private final CatalogReactiveHttpApi catalogApi;

    public CatalogReactiveGateway(
            CatalogReactiveHttpApi catalogApi) {
        this.catalogApi = catalogApi;
    }

    public Mono<ProductDto> findProduct(String productId) {
        return catalogApi.findById(productId);
    }
}
~~~

`Mono<ProductDto>` is a publisher describing the execution pipeline. The HTTP request normally starts when a **subscriber** subscribes—for instance, when the WebFlux framework receives the `Mono` from a controller and manages the subscription.

Do not call `subscribe()` arbitrarily inside a gateway just to "trigger" the request, because errors and results become detached from the business flow. Avoid calling `block()` on a Reactor event loop; if a blocking step is required for a JDBC database call, isolate it on an appropriate scheduler/thread or adopt a consistent imperative architecture.

### 5.2. `WebClientAdapter` Does Not Change the Server Contract by Default

Both clients send HTTP requests to the Catalog API, with important differences:

| Aspect | RestClientAdapter | WebClientAdapter |
| --- | --- | --- |
| Underlying client | `RestClient` | `WebClient` |
| Dominant model | Blocking | Reactive/non-blocking with suitable transport |
| Recommended return types | DTO, `ResponseEntity<DTO>` | `Mono<DTO>`, `Flux<DTO>` |
| Error path | Typically throws exceptions directly | Error signal inside publisher |
| Timeout | HTTP request factory + application policy | Connector/transport + timeout operator where appropriate |
| Spring MVC | Natural | Usable, but requires careful management of reactive boundary |
| Spring WebFlux | Unsuitable if called directly on event loop | Natural |
| Observation | Boot-managed builder | Boot-managed builder |

Choose based on the **actual consumption model**, not by picking `WebClient` merely to make HTTP calls or forcing `RestClient` to return `Mono` by wrapping a blocking call in `Mono.just(...)`.

## 6. HTTP Contracts: URLs, Headers, Bodies, Statuses, and Errors

### 6.1. Setting Base URL and Paths Within Proper Scope

If the base URL is `https://catalog.example.org` and the interface has:

~~~java
@HttpExchange(url = "/v1/products")
public interface CatalogHttpApi {
    @GetExchange("/{id}")
    ProductDto findById(@PathVariable("id") String id);
}
~~~

calling `findById("P-100")` builds an HTTP request to `https://catalog.example.org/v1/products/P-100` per adapter and URI template rules.

Pass path variables via `@PathVariable` so the framework performs URI expansion/encoding; do not manually concatenate URLs from user strings. When paths include a base path, verify leading/trailing `/` handling and potential path overrides when combining with `baseUrl`, especially behind proxy prefixes.

Never let an HTTP interface accept an **unvalidated full URL from users** and dispatch to arbitrary hostnames: that introduces SSRF risk. Only allow configured, verified downstreams.

### 6.2. Headers and POST Methods

Some operations require per-request headers, especially when tokens or idempotency keys vary by caller:

~~~java
@PostExchange(contentType = "application/json")
ProductDto create(
        @RequestHeader("Idempotency-Key") String idempotencyKey,
        @RequestBody CreateProductRequest request);
~~~

Supplying `Idempotency-Key` at the call site (generated by the application per business contract) ensures each retry of the same logical action retains the **same key**, while distinct business actions receive distinct keys. The partner server must also support idempotency key processing; the header alone does not guarantee deduplication.

For `Authorization`, avoid placing user A's token in `defaultHeader(...)` on a shared multi-user singleton client. Use proper transport/filter/interceptor auth mechanisms, or pass per-request headers after authentication and authorization checks. Ensure credentials are never inadvertently forwarded across different downstreams.

### 6.3. Choosing Return Types for Response Headers and Statuses

If the adapter needs the HTTP status, `ETag`, or pagination headers, return `ResponseEntity<ProductDto>`:

~~~java
@GetExchange("/{id}")
org.springframework.http.ResponseEntity<ProductDto> findWithMetadata(
        @PathVariable("id") String id);
~~~

On the reactive side, use `Mono<ResponseEntity<ProductDto>>`. Never assume "HTTP 200 with a valid body" for every response: APIs may return 204, 206, 304, or 404 with distinct meanings. Empty body decoding and error translation must follow the server contract accurately.

### 6.4. Error Classification

| Situation | RestClient | WebClient | Business Adapter Reaction |
| --- | --- | --- | --- |
| 2xx + valid JSON | DTO/ResponseEntity | `Mono`/`Flux` emits result | Map to internal model/port result |
| 204/no body | May have no body | May complete empty | Explicitly define empty result semantics |
| 404 | Usually `RestClientResponseException` for status | `WebClientResponseException.NotFound` | Distinguish "not found" from failures |
| 400/422 | HTTP client error | HTTP error signal | Do not blindly retry; fix contract/data |
| 401/403 | Authentication/authorization error | Authentication/authorization error | Check secrets/permissions |
| 429/503 | Rate limit/downstream error | Error signal | Bounded retry with backoff per contract |
| Network/DNS/timeout | Client/I/O layer exception | Usually `WebClientRequestException` or timeout signal | Distinguish connection vs deadline failures |
| JSON schema mismatch | Deserialization error | Decoding error signal | Version compatibility/contract testing |

An HTTP interface **does not automatically turn 404 into `Optional.empty()` by business convention**. Place this translation policy in the gateway so controllers and use cases stay decoupled from HTTP status codes.

## 7. Placing a Business Adapter in Front of the HTTP Interface

`CatalogHttpApi` knows URLs/methods/bodies; the application wants to know "was the product found?". Those are distinct responsibilities.

Example business port:

~~~java
// ProductCatalogPort.java
import java.util.Optional;

public interface ProductCatalogPort {
    Optional<ProductDto> findById(String productId);
}
~~~

Implementing the port over the synchronous HTTP interface:

~~~java
// HttpProductCatalogAdapter.java
import java.util.Optional;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientResponseException;

@Component
public class HttpProductCatalogAdapter
        implements ProductCatalogPort {

    private final CatalogHttpApi api;

    public HttpProductCatalogAdapter(CatalogHttpApi api) {
        this.api = api;
    }

    @Override
    public Optional<ProductDto> findById(String productId) {
        try {
            return Optional.ofNullable(api.findById(productId));
        } catch (RestClientResponseException exception) {
            if (exception.getStatusCode().value() == 404) {
                return Optional.empty();
            }
            throw new CatalogUnavailableException(
                    "Unable to read Catalog data",
                    exception);
        }
    }
}
~~~

Business/adapter exception:

~~~java
public class CatalogUnavailableException extends RuntimeException {
    public CatalogUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

In this example, 404 is interpreted as not found; other HTTP error statuses are translated into an adapter exception. In production, distinguish **transient** errors (eligible for retry) from **permanent** errors (400/403/schema mismatches) using more specific exceptions or result types. Never log raw response bodies containing PII or tokens.

Similarly, with a WebClient proxy:

~~~java
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

public Mono<ProductDto> findOptional(String productId) {
    return catalogReactiveApi.findById(productId)
            .onErrorResume(
                    WebClientResponseException.NotFound.class,
                    ignored -> Mono.empty());
}
~~~

The `onErrorResume` branch applies strictly to 404; connection errors and 5xx failures still propagate so the orchestration layer can enforce appropriate policies. Never use `onErrorResume(ignored -> Mono.empty())` for all exceptions, as that hides an outage as "product not found".

### 7.1. API Contracts Must Be Versioned

If a partner changes the `active` field from boolean to string, an HTTP proxy can still send the request successfully yet fail during deserialization. Therefore:

- Specify API path/version, DTOs, enums, date/time formats, null handling, and error structures.
- Separate downstream DTOs from internal domain models; use mappers when lifecycles diverge.
- Do not catch JSON errors and return a seemingly valid default object.
- Run contract tests using real responses or partner-agreed fixtures.
- Avoid leaking `RestClientResponseException`/`WebClientResponseException` into domain/use-case layers that do not need HTTP details.

## 8. Timeouts, Retries, and Preventing Duplicate Execution

HTTP interfaces declare requests; timeouts and retries must be configured for the corresponding **transport and operations**.

### 8.1. Three Commonly Confused Timeouts

1. **Connect timeout**: time to establish the TCP/TLS connection to downstream.
2. **Read/response timeout**: time waiting for response data at the HTTP transport layer.
3. **Application deadline**: maximum time for the overall business flow, which may include queuing, multiple requests, retries, and data transformations.

Example in a WebClient reactive flow:

~~~java
public Mono<ProductDto> findWithDeadline(String id) {
    return catalogReactiveApi.findById(id)
            .timeout(java.time.Duration.ofSeconds(5));
}
~~~

`timeout(...)` bounds the Reactor pipeline at the point where the operator is placed, **not as a complete substitute** for HTTP client connect and response timeouts. When calling multiple downstreams sequentially, the application deadline must reflect total elapsed time, not just each individual request.

With `RestClient`, configure timeouts on the request factory/HTTP client selected by Boot and via version-appropriate extension points. Spring Boot 3.x and 4.x differ in shared HTTP client properties, so do not blindly copy configuration verbatim across versions. If you replace the request factory or WebClient connector manually, verify that you have not bypassed connection pooling, shared resources, or observation configured by Boot.

### 8.2. Retries by HTTP Method and Side Effects

| Method and Operation | Retryable? | Conditions |
| --- | --- | --- |
| Pure read-only GET | Usually yes | Bounded attempts, transient errors only, backoff |
| PUT setting deterministic state | Yes, if server genuinely enforces idempotency | Depends on API contract and state |
| POST creating orders/payments | Only with deduplication mechanisms | Preserve same `Idempotency-Key` across retries |
| DELETE | Depends on contract | Must clarify whether 404 on already-deleted resource is success or failure |
| HTTP timeout after write request | Outcome is **unknown** | Reconcile state before resending or use idempotency key |

Example reactive pipeline retrying **only a specific transient error**, with bounds:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;
import org.springframework.web.reactive.function.client.WebClientResponseException;

public Mono<ProductDto> findWithRetry(String id) {
    return catalogReactiveApi.findById(id)
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(200))
                            .filter(error ->
                                    error instanceof
                                            WebClientResponseException.ServiceUnavailable));
}
~~~

This is a minimal example: it retries at most **two times after the initial attempt** on HTTP 503. In practice, you may also need to handle 429, eligible network errors, jitter, total deadline, circuit breakers, and policy-based exception filtering. Never retry all 4xx/5xx responses, and never stack retries across multiple layers (HTTP client, service, broker consumer) without capping total requests.

### 8.3. Transactions and Outbox

Suppose a use case updates SQL and then calls an HTTP interface to submit an order:

~~~text
DB COMMIT succeeds
    |
    +-- POST /orders times out
           |
           +-- Unclear whether the partner created the order or not
~~~

SQL `@Transactional` does not make an HTTP request an ACID member of the same transaction. A resilient design writes the **business row and an outbox row in the same DB transaction**, after which a worker/broker consumer dispatches the HTTP call with an idempotency key and records the reconciliation outcome.

When receiving a broker message subject to redelivery, the HTTP adapter must also derive a stable idempotency key from the event/business identity—not from a traceId or message-id regenerated on each attempt.

## 9. Customizing Clients: Per-Client vs Global Configuration

An application may call Catalog API, Payment API, and Inventory API with different base URLs, timeouts, authentication, and headers. Avoid keeping a single mutable builder and repeatedly mutating baseUrl/headers across those systems.

| Need | Approach |
| --- | --- |
| Catalog-specific URL and headers | Customize builder when creating Catalog proxy bean |
| Payment-specific URL and auth | Create a separate Payment RestClient/WebClient bean |
| Shared policies across HTTP clients | Use Boot-supported customizers per version |
| Reusing one builder across multiple clients | Call `builder.clone()` before each branch or inject separately |
| Deriving a client from an existing one | `restClient.mutate()` or `webClient.mutate()` then `build()` |
| Metrics/tracing instrumentation | Prefer Boot-injected builder; verify Actuator/tracing dependencies |

Each interface should describe a clear downstream contract. Avoid creating a single giant interface mixing methods for different hosts that have independent auth, SLAs, retries, and versioning.

**Client builders are stateful.** Calling `baseUrl(...)` or `defaultHeader(...)` mutates the builder; if you reuse the exact same builder object across clients, stale headers/filters can bleed into new clients. Boot-provided builders are typically prototype-scoped per injection point, but that does not protect you if your own code holds and reuses **the same instance**.

## 10. Security and Trace Context Propagation

An easy-to-use HTTP proxy also makes misconfigurations propagate quickly. Control:

- **Secret management:** retrieve passwords, API keys, and bearer tokens from a secret manager or token provider; never hardcode them in annotations.
- **Per-caller tokens:** pass via appropriate request scope/filters/interceptors rather than putting one user's token on a singleton client.
- **TLS:** use HTTPS and verify certificates and hostnames; never disable certificate validation as a workaround.
- **SSRF:** configure validated base URLs and avoid constructing absolute request URIs from untrusted input.
- **Data minimization:** do not blindly forward all inbound request headers to downstream services.
- **Logging:** never write Authorization headers, cookies, raw customer payloads, or sensitive responses to logs.
- **Rate limiting:** cap request rates/concurrency to protect partner APIs under load or retry bursts.
- **Trace propagation:** Boot-managed clients typically integrate with Micrometer Observation/tracing when required dependencies and active contexts are present; verify across HTTP and async boundaries.

HTTP proxies run on the caller's thread or reactive context. If the caller is a scheduler, broker consumer, or Spring Integration endpoint, the trace context may start fresh or require explicit propagation across executors/transports. `HttpServiceProxyFactory` does not replace cross-process trace propagation configuration.

## 11. Testing HTTP Contracts and Proxy Wiring Correctly

Test at least two layers: **HTTP contracts** and **Spring Boot wiring**. Simply mocking `CatalogHttpApi` and asserting that a service called a method is insufficient—that test does not verify whether the proxy produces valid HTTP requests.

### 11.1. Testing `RestClientAdapter` with `MockRestServiceServer`

Spring Test lets you bind a mock HTTP server to `RestClient.Builder`. Minimal example verifying path and JSON:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class CatalogHttpApiTest {

    @Test
    void mapsFindByIdToHttpGet() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        CatalogHttpApi api =
                HttpServiceProxyFactory.builderFor(
                                RestClientAdapter.create(
                                        builder.build()))
                        .build()
                        .createClient(CatalogHttpApi.class);

        server.expect(requestTo(
                        "https://catalog.test/v1/products/P-100"))
                .andRespond(withSuccess(
                        "{\"id\":\"P-100\",\"name\":\"Keyboard\",\"active\":true}",
                        MediaType.APPLICATION_JSON));

        ProductDto product = api.findById("P-100");

        assertEquals("P-100", product.id());
        assertEquals("Keyboard", product.name());
        server.verify();
    }
}
~~~

This is a contract test of **interface + proxy + `RestClientAdapter`**; it intentionally builds the builder directly for isolation. It **does not verify Spring Boot's builder** or externalized configuration; those require a separate Spring context test.

In real tests, add expectations for GET HTTP method, `Accept` header, query parameters, POST request bodies, and per-request `Idempotency-Key` headers. Error tests can configure the mock server to return 404/503 and verify that the business adapter maps errors properly.

### 11.2. Testing Spring Boot Wiring

Use `@SpringBootTest` or a test context containing the necessary beans, pointing `integrations.catalog.base-url` to an HTTP stub server via `@DynamicPropertySource` or test configuration. Verify:

1. Spring injects the `CatalogHttpApi` or `CatalogReactiveHttpApi` bean.
2. The base URL comes from test environment properties.
3. The HTTP client uses Boot's managed builder.
4. The proxy sends expected headers, timeouts, and auth filters/interceptors per configuration.
5. Responses with 404, 429, 500, empty bodies, or invalid JSON follow policy.
6. If instrumentation is enabled, key traces/metrics are emitted properly without user IDs in tags.

You can use WireMock, MockWebServer, or an equivalent HTTP test server. With `WebClientAdapter` and `Mono`, use `StepVerifier` to assert completion/errors rather than `block()` as in blocking code:

~~~java
StepVerifier.create(reactiveApi.findById("P-100"))
        .assertNext(product ->
                assertEquals("P-100", product.id()))
        .verifyComplete();
~~~

The snippet assumes an active HTTP stub server, injected `reactiveApi`, Reactor Test/JUnit imports, and JSON fixtures. Do not treat it as a complete standalone test without setting up the server.

### 11.3. High-Value Test Scenarios

| Scenario | What to Verify |
| --- | --- |
| GET product | Method, base URL, URI template, and JSON decoding |
| GET with ID requiring encoding | Path variable expanded/encoded accurately |
| Pagination query | `page`, `size`, `active` serialized as query parameters |
| POST create product | `Content-Type`, request body, idempotency header |
| 404 | Adapter returns `Optional.empty()` or domain error per contract |
| 401/403 | No infinite retry; token not logged |
| 429/503 | Bounded retry/backoff; sufficient observability data |
| Timeout | Transport timeout and total deadline distinguished |
| JSON schema drift | Fails clearly on decoding; does not return bogus default data |
| Two downstreams | No auth/base URL/header leakage between clients |
| WebClient reactive | Requests only on subscribe; errors emitted as error signals |
| Database + outbound HTTP | Does not assume SQL transaction rolls back HTTP side effects |
| POST retry | One business operation retains the same `Idempotency-Key` |

## 12. Observability and Operations

When the application includes Actuator and Micrometer, Spring Boot-managed clients can be instrumented with observations to collect HTTP client metrics and propagate trace headers, depending on version/transport/tracer config.

Useful metrics:

| Metric | Operational Question |
| --- | --- |
| Outbound request rate by `client`/`uri template` | Which downstream is called most frequently? |
| Latency p95/p99 | Which API is running slowly? |
| HTTP 4xx/5xx | Contract errors, auth errors, or downstream outage? |
| Timeouts and connection errors | Network, server, or connection pool causing failures? |
| Retry attempts per operation | How many requests is a single event generating? |
| Circuit breaker/rate-limit events | Are downstreams properly protected? |
| Queue/outbox lag | Are slow HTTP proxy calls creating a backlog? |

The `uri` metric should use the **URI template** (e.g., `/v1/products/{id}`), never individual product IDs in labels. Never put `eventId`, bearer tokens, emails, user IDs, or sensitive query strings into metric labels. For tracing, control both span attributes and header logging.

An **HTTP 200** from a partner only indicates that the HTTP request was accepted/completed per the server contract. If the server returns 202 Accepted, business processing may still sit in a queue. Therefore, distinguish **HTTP attempt outcome** metrics from **business final outcome** metrics, especially when integrating with brokers, outboxes, and schedulers.

## 13. Common Configuration Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No bean for `CatalogHttpApi` | Only declared interface without creating proxy bean | Build `HttpServiceProxyFactory` and register `@Bean` |
| `RestClient` class missing | Spring Framework/Boot too old | Check Spring Framework 6.1+/Boot 3.2+ support |
| `RestClientAdapter` unresolved | Missing dependency or version-mismatched import | Verify `spring-web` and imports |
| `WebClientAdapter` unresolved | Missing WebFlux dependency | Add appropriate WebClient/WebFlux starter |
| Builder method `builderFor` error | Mixing Spring 6.0 and 6.1+/7 API examples | Check `HttpServiceProxyFactory` API for your version |
| `No qualifying bean of type RestClient.Builder` | Missing Boot auto-config/dependency or excluded | Check Boot conditions and classpath |
| Proxy called but no HTTP request sent | Reactive `Mono` not subscribed | Return publisher to framework/consumer to subscribe |
| `block()` fails on event-loop | Blocking inside WebFlux thread | Stay reactive end-to-end or isolate blocking work |
| Wrong base URL | Incorrect property/profile/env override | Inspect property binding and URI paths |
| `RestClientAdapter` present but 401 | Missing token or wrong auth scheme | Inspect filter/interceptor/secrets; avoid logging tokens |
| JSON errors after server upgrade | DTO schema mismatch | Contract tests and versioning |
| Retries create duplicate orders | POST lacks idempotency contract | Use `Idempotency-Key` and reconciliation |
| Missing metrics/traces | Manually created builder or missing Actuator/tracing/exporter | Use Boot-managed builder and verify instrumentation |
| Requests hit wrong service | Reused mutable builder with shared headers/baseURL | Create separate client beans or clone builders |

## 14. HTTP Interface Adapter Completion Checklist

- [ ] HTTP API client clearly defined with `@HttpExchange` and corresponding method annotations.
- [ ] `RestClientAdapter` or `WebClientAdapter` chosen to match the actual blocking/reactive execution model.
- [ ] HTTP proxy registered as a Spring bean via `HttpServiceProxyFactory` (or equivalent version-specific registration mechanism).
- [ ] Boot-managed builder used to preserve client settings, codecs, and observability where applicable.
- [ ] Base URLs, timeouts, auth, and API versions isolated per downstream and environment.
- [ ] DTOs, headers, statuses, empty responses, and errors specified as a formal data contract.
- [ ] Business adapter translates HTTP results/errors into port/domain outcomes per policy.
- [ ] Bounded retries for GET/POST; write requests carry an idempotency key or reconciliation mechanism.
- [ ] SQL transactions separated from HTTP side effects; outbox/inbox used where reliability requires it.
- [ ] Tested HTTP paths/methods/bodies/headers, 404/503, timeouts, and reactive subscriptions.
- [ ] Metrics/traces/logs scoped cleanly without leaking secrets or high-cardinality tags.

**Takeaway:** An HTTP interface declares the client-side contract; `HttpServiceProxyFactory` creates the proxy; `RestClientAdapter` and `WebClientAdapter` determine the request execution model. Spring Boot provides the builder and baseline configuration; the integration layer owns downstream isolation, error classification, timeouts, retries/idempotency, transaction boundaries, and observability. Keeping these boundaries clear makes multiple HTTP APIs easier to test, evolve, and operate.

## References

- [Spring Framework — HTTP Interface](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-http-interface): `@HttpExchange`, proxies, and connecting HTTP clients.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, error handling, and HTTP interfaces.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive requests, response handling, and client configuration.
- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): Boot-managed builders and client configuration.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): metrics/tracing and `ObservationRegistry`.
- [Spring Framework API — HttpServiceProxyFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html): creating HTTP interface proxies.
