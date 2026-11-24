# Distinguishing Spring HTTP Interfaces from OpenFeign and External Libraries

## 1. Context: One HTTP Contract, Many Ways to Write a Client

In a **Spring Boot Integration** application, an order service often needs to call inventory, pricing, or shipping APIs over HTTP while also writing to a database, updating Redis caches, and publishing events to Kafka/RabbitMQ. When writing `RestClient` or `WebClient` manually, each call site can repeat URL assembly, header setup, JSON parsing, and error translation. A **declarative HTTP client** lets you describe HTTP requests directly on Java interface methods and have a library generate the actual HTTP-calling code.

The Spring ecosystem offers several options that are often conflated:

- **Spring Framework HTTP interface**: core mechanism introduced in Spring Framework 6 using `@HttpExchange`, `@GetExchange`, `@PostExchange`... and `HttpServiceProxyFactory`, delegating network execution to a configured HTTP client.
- **Spring Cloud OpenFeign**: Spring Cloud's integration with OpenFeign/Feign, typically using `@FeignClient`, `@GetMapping`, `@PostMapping`, with its own configuration model and extensions.
- **External libraries**: Feign core, Retrofit, MicroProfile Rest Client, or OpenAPI-generated clients; each solution carries its own annotations, transport mechanisms, serializers, and lifecycles.

These are **different ways to implement an HTTP client**. None of them guarantees a partner API stays healthy, makes distributed transactions safe, or handles duplicates automatically. Those still require timeouts, bounded retries, circuit breakers, bulkheads, idempotency, testing, and observability.

After this lesson, you will be able to explain when to choose Spring's native HTTP interface, when a system already using OpenFeign should keep using it, how to set timeouts and register beans, and how to migrate without breaking the HTTP contract.

## 2. Clarifying Terminology

### 2.1. What Is Spring's HTTP Interface?

An **HTTP interface** is a Java interface annotated to describe HTTP exchanges. For example:

```java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(url = "/api/inventory", accept = "application/json")
public interface InventoryHttpApi {

    @GetExchange("/{sku}")
    InventoryResponse getAvailability(@PathVariable("sku") String sku);
}

record InventoryResponse(String sku, boolean available, long version) {}
```

The annotations declare a **client contract**: paths, methods, content types, parameters, and return types. They **do not turn the interface into a controller** or expose an HTTP endpoint on the server. To make network calls, the application must create a proxy for the interface using `HttpServiceProxyFactory` and connect it to a properly configured client.

Spring Framework supports common annotations:

| Annotation | Primary Meaning | Example |
| --- | --- | --- |
| `@HttpExchange` | Shared interface/method settings such as URL, accept, content type | `/api/inventory` prefix |
| `@GetExchange` | HTTP GET | Check stock |
| `@PostExchange` | HTTP POST | Create reservation |
| `@PutExchange` | HTTP PUT | Replace/update resource |
| `@PatchExchange` | HTTP PATCH | Partial update |
| `@DeleteExchange` | HTTP DELETE | Delete/cancel per contract |
| `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody` | Bind path, query, headers, and body | SKU, filters, token, and JSON |

The HTTP exchange annotations live in `org.springframework.web.service.annotation`; several parameter annotations reuse `org.springframework.web.bind.annotation`. Return types can be DTOs, `ResponseEntity<T>`, or reactive types like `Mono<T>`/**`Flux<T>`** when supported by the adapter. Match the return type to your HTTP client and processing flow; a reactive interface does not automatically turn a blocking transport into non-blocking I/O.

### 2.2. What Is Spring Cloud OpenFeign?

**OpenFeign/Feign core** is a standalone library that builds HTTP clients from interfaces. **Spring Cloud OpenFeign** adds Spring integration on top of Feign: `@FeignClient`, the Spring MVC contract, named client beans/configurations, and optional integrations with Spring Cloud LoadBalancer, observability, or circuit breakers when configured.

```java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "inventory", url = "${integration.inventory.base-url}")
public interface InventoryFeignApi {

    @GetMapping("/api/inventory/{sku}")
    InventoryResponse getAvailability(@PathVariable("sku") String sku);
}
```

A Feign interface uses `@FeignClient` to declare a client name and target resolution. In Spring Cloud OpenFeign, `@GetMapping` belongs to the Spring MVC contract; Feign core uses its own annotations/contract such as `@RequestLine` when used outside Spring MVC integration. Therefore, **Feign core is not identical to Spring Cloud OpenFeign**, and you should never copy a Feign interface into a Spring HTTP interface expecting all annotations to behave identically.

### 2.3. What Do External Libraries Mean?

Beyond those two choices, an application may use:

- **Retrofit**: interface design using Retrofit's `@GET`, `@POST`, converters, and call adapters; popular in Java/Android ecosystems, distinct from Spring HTTP interfaces.
- **MicroProfile Rest Client**: `@RegisterRestClient` with JAX-RS annotations and MicroProfile runtime configuration; suited for compatible MicroProfile/Jakarta stacks.
- **OpenFeign core**: building Feign clients without the Spring Cloud starter; teams wire contracts, decoders, encoders, retries, and dependency injection themselves.
- **OpenAPI-generated client**: Java code generated from an OpenAPI contract, selectable across multiple HTTP backend libraries via generator options. This is a **code generation and contract-management strategy**, not a single fixed transport.
- **OkHttp, Apache HttpClient, Java HttpClient**: low-level HTTP transports/clients; they can sit underneath a declarative facade or be used directly when low-level protocol control is required.

Many teams pick declarative interfaces for readability, yet still need to manage timeouts, connection pools, authentication, serializers, logging, and resource lifecycle cleanup.

## 3. Comparison Table for Decision-Making

| Question | Spring HTTP Interface | Spring Cloud OpenFeign | Retrofit / External Libraries |
| --- | --- | --- | --- |
| Scope | Spring Framework, native fit with Spring Web | Spring Cloud + Feign | Depends on chosen library/runtime |
| Primary annotations | `@HttpExchange`, `@GetExchange`... | `@FeignClient`, Spring MVC mappings | Retrofit `@GET`; MicroProfile/JAX-RS or custom contract |
| Client creation | `HttpServiceProxyFactory` with adapter | Beans registered via `@EnableFeignClients`/scanning | Library-specific builders/factories/injection |
| HTTP transport | `RestClient`, `WebClient`, version-compatible adapters | Configured Feign client/transport; Apache HC5/OkHttp via dependencies | Library-dependent, e.g. OkHttp |
| Blocking / reactive | Blocking or reactive depending on adapter | Spring Cloud OpenFeign is primarily blocking; lacks native WebClient-style reactive client | Depends on call adapters and framework |
| Timeout, interceptor config | Configured on `RestClient`/`WebClient` and request factory/connector | Feign properties, request interceptors, client config | Dedicated builders, call adapters, and config |
| Load balancing/service discovery | Via client builders/adapters and compatible Spring Cloud integration; verify specific setup | Integrates with Spring Cloud LoadBalancer when configured compatibly | Integrated manually per runtime |
| Error/codec extensibility | Status handlers, Jackson/converters/filters of Spring clients | Feign `ErrorDecoder`, `Encoder`, `Decoder`, `RequestInterceptor` | Custom converters/error adapters |
| Dependency footprint | Usually minimal when Spring Web is already used | Adds Spring Cloud release train/starters | Adds external library and independent version management |
| Migration | Update proxy creation, annotations/return types | Update Feign clients and Feign-specific config | May require changing annotations, error model, and transport |

**Do not choose purely by annotation syntax.** The underlying HTTP transport determines timeouts, TLS/mTLS, connection pooling, proxies, tracing, retries, and runtime exceptions. Two visually similar interfaces can differ substantially in default retries, exception hierarchies, URL encoding, or empty-body behavior.

### 3.1. Selection Rules by Project

- New Spring Boot project already using Spring MVC/WebFlux and needing concise declarative clients: **evaluate Spring HTTP interfaces first**, reusing Spring HTTP clients/converters and reducing extra frameworks to learn.
- Existing project heavily invested in Spring Cloud OpenFeign with stable clients, configs, interceptors, `ErrorDecoder`, load balancing, and tests: **no need to switch just to swap annotations**; any migration needs a clear technical driver.
- Project requiring OpenAPI code generation, multi-language SDKs, or strict contract-first workflows: consider **generated clients**; evaluate generator targets and schema-update workflows.
- Non-Spring Java project or specialized runtime call adapters: an external library may fit better.
- Fully reactive WebFlux/Reactor pipelines: evaluate Spring HTTP interfaces with **`WebClientAdapter`** or `WebClient` directly; never put blocking calls on the event loop.

When selecting libraries, verify **Spring Boot – Spring Framework – Spring Cloud release train – Feign** compatibility for your project's versions. Never copy a Boot 2 snippet straight into Boot 3/4: packages, properties, defaults, and proxy registration can change.

## 4. Spring HTTP Interface with `RestClient`: Complete Implementation

This example targets **Spring Boot 3.2+ / Spring Framework 6.1+**, where `RestClient` and `RestClientAdapter` support HTTP interfaces. Sample API: checking a SKU and creating a stock reservation in an inventory service.

### 4.1. Environment-Driven Properties Configuration

```yaml
# application.yml — illustrative defaults; override per environment
integration:
  inventory:
    base-url: "${INVENTORY_BASE_URL:http://localhost:18080}"
    connect-timeout: 500ms
    read-timeout: 2s
```

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integration.inventory")
public record InventoryClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout
) {}
```

Register this config record with `@EnableConfigurationProperties(InventoryClientProperties.class)` or scan with `@ConfigurationPropertiesScan`. In production, add validation such as `@Validated`, `@NotNull`, positive timeout bounds, and HTTPS scheme / host allowlist checks per policy. Never keep environment-specific URLs or secrets hardcoded in Java source.

### 4.2. Defining the HTTP Contract

```java
import java.math.BigDecimal;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

record AvailabilityResponse(String sku, boolean available, long version) {}
record ReserveRequest(String orderId, String sku, int quantity) {}
record ReserveResponse(String reservationId, String status) {}

@HttpExchange(url = "/api/inventory", accept = "application/json")
interface InventoryHttpClient {

    @GetExchange("/{sku}")
    AvailabilityResponse getAvailability(
            @PathVariable("sku") String sku,
            @RequestHeader("X-Correlation-Id") String correlationId);

    @PostExchange(url = "/reservations", contentType = "application/json")
    ReserveResponse reserve(
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestHeader("X-Correlation-Id") String correlationId,
            @RequestBody ReserveRequest request);
}
```

`@HttpExchange` sets the shared path prefix and `Accept` header. `@GetExchange` / `@PostExchange` specify per-method verbs, paths, and media types. Request/response DTOs must match the real API contract; if upstream uses different field names, configure Jackson mappings explicitly rather than assuming Java records match automatically.

`@RequestHeader("Idempotency-Key")` in the example is a **business contract agreed by both parties**, not an automatic Spring idempotency implementation. The inventory server must persist and check keys to ensure `reserve` is not executed twice when a client retries.

### 4.3. Registering the Proxy with `RestClientAdapter`

```java
import java.net.http.HttpClient;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryHttpClientConfig {

    @Bean
    InventoryHttpClient inventoryHttpClient(
            InventoryClientProperties properties,
            RestClient.Builder restClientBuilder) {

        HttpClient jdkClient = HttpClient.newBuilder()
                .connectTimeout(properties.connectTimeout())
                .build();

        JdkClientHttpRequestFactory factory =
                new JdkClientHttpRequestFactory(jdkClient);
        factory.setReadTimeout(properties.readTimeout());

        RestClient restClient = restClientBuilder
                .baseUrl(properties.baseUrl().toString())
                .requestFactory(factory)
                .build();

        RestClientAdapter adapter = RestClientAdapter.create(restClient);
        HttpServiceProxyFactory proxyFactory =
                HttpServiceProxyFactory.builderFor(adapter).build();

        return proxyFactory.createClient(InventoryHttpClient.class);
    }
}
```

Execution flow:

1. Spring Boot binds and validates `InventoryClientProperties` from configuration.
2. `RestClient` manages the HTTP request factory, message converters, interceptors, and response handling.
3. `RestClientAdapter` connects the real client to `HttpServiceProxyFactory`.
4. The factory generates a proxy implementing `InventoryHttpClient`; business code injects the interface instead of assembling HTTP requests.
5. On method invocation, the proxy builds the HTTP exchange and decodes the response into the contract DTO.

**Version note:** `HttpServiceProxyFactory.builderFor(...)` belongs to Spring Framework 6.1+ configuration. Newer Framework releases may add automatic HTTP service client registration mechanisms; this example registers the bean explicitly to make proxy construction transparent. Never assume writing `@HttpExchange` alone causes every Spring Boot version to scan and create beans automatically.

### 4.4. Calling from a Business Service

```java
import org.springframework.stereotype.Service;

@Service
class OrderInventoryService {
    private final InventoryHttpClient inventory;

    OrderInventoryService(InventoryHttpClient inventory) {
        this.inventory = inventory;
    }

    boolean isAvailable(String sku, String correlationId) {
        AvailabilityResponse response =
                inventory.getAvailability(sku, correlationId);
        return response != null && response.available();
    }

    String reserveForOrder(
            String orderId, String sku, int quantity,
            String idempotencyKey, String correlationId) {
        ReserveResponse response = inventory.reserve(
                idempotencyKey,
                correlationId,
                new ReserveRequest(orderId, sku, quantity));
        if (response == null || response.reservationId() == null) {
            throw new IllegalStateException("Missing inventory reservation ID");
        }
        return response.reservationId();
    }
}
```

Avoid wrapping slow HTTP calls inside long-lived DB transactions unless strictly necessary: waiting on the network ties up DB connections and locks. For workflows coordinating DB writes and stock reservations, consider saga/compensation, transactional outbox, or intermediate states instead of assuming an HTTP call and DB commit share one transaction.

## 5. Using `WebClient`: HTTP Interface Keeps the Same Idea

A WebFlux application must avoid blocking the event loop while waiting on HTTP. With `WebClientAdapter`, Spring HTTP interfaces support Reactor return types:

```java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import reactor.core.publisher.Mono;

@HttpExchange("/api/inventory")
interface ReactiveInventoryHttpClient {
    @GetExchange("/{sku}")
    Mono<AvailabilityResponse> getAvailability(
            @PathVariable("sku") String sku);
}
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration
class ReactiveInventoryConfig {
    @Bean
    ReactiveInventoryHttpClient reactiveInventoryHttpClient(
            WebClient.Builder webClientBuilder) {
        WebClient client = webClientBuilder
                .baseUrl("https://inventory.example.internal")
                .build();
        HttpServiceProxyFactory factory = HttpServiceProxyFactory
                .builderFor(WebClientAdapter.create(client))
                .build();
        return factory.createClient(ReactiveInventoryHttpClient.class);
    }
}
```

This snippet illustrates proxy wiring; it is **not complete production config**. Configure connect/response/read timeouts on the underlying connector, retry policies, pool limits, and TLS where required. When using `Mono`/`Flux`, subscribe/compose within managed reactive pipelines and avoid calling `block()` on event loops. Nor is reactive automatically superior: blocking `RestClient` remains simpler and well suited for MVC applications with properly sized resources and concurrency caps.

## 6. Spring Cloud OpenFeign: Same Requirement, Different Configuration

### 6.1. Dependencies and Client Registration

For applications using Spring Cloud, add the starter and align with a **Spring Boot-compatible Spring Cloud BOM**. Do not pin standalone Feign versions outside dependency management without verifying compatibility.

```kotlin
// build.gradle.kts — compatible Spring Cloud BOM already configured
implementation("org.springframework.cloud:spring-cloud-starter-openfeign")
```

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

@SpringBootApplication
@EnableFeignClients(basePackageClasses = InventoryFeignApi.class)
public class OrderApplication {}
```

```java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "inventory", url = "${integration.inventory.base-url}")
interface InventoryFeignApi {
    @GetMapping("/api/inventory/{sku}")
    AvailabilityResponse getAvailability(
            @PathVariable("sku") String sku,
            @RequestHeader("X-Correlation-Id") String correlationId);
}
```

With an explicit URL, the client calls the configured endpoint. When using service discovery/load balancing, naming/URL conventions and dependencies must follow the Spring Cloud documentation for your version. Each Feign client can have dedicated auth/interceptors, logging, encoders/decoders, timeouts, or circuit breakers.

### 6.2. Configuring Timeouts by Client Name

```yaml
integration:
  inventory:
    base-url: "${INVENTORY_BASE_URL:https://inventory.example.internal}"

spring:
  cloud:
    openfeign:
      client:
        config:
          inventory:
            connectTimeout: 500
            readTimeout: 2000
            loggerLevel: basic
```

In Spring Cloud OpenFeign 4.x, `connectTimeout` and `readTimeout` are expressed in **milliseconds** in Feign config. This differs from the `Duration` syntax `integration.inventory.read-timeout: 2s` in the Spring `RestClient` example. During migration, it is easy to confuse `2000` with seconds or vice versa; check property metadata for your project version.

More verbose `loggerLevel` settings can expose headers and bodies; never enable `FULL` casually in production, as payloads may contain tokens or personal data. Feign typically throws `FeignException` or Feign-specific transport exceptions, whose hierarchy and mapping differ from Spring's `RestClientResponseException`. Translate them into a unified **application-domain error** model at the boundary.

### 6.3. What Easily Differs When Migrating Away from Feign?

| Aspect | Active Feign Setup | Spring HTTP Interface Replacement |
| --- | --- | --- |
| Annotations | `@FeignClient` + `@GetMapping` | `@HttpExchange` + `@GetExchange` |
| Bean creation | `@EnableFeignClients`/scanning | `HttpServiceProxyFactory` proxy registration or version-supported auto-registration |
| Request interception | `RequestInterceptor` | `RestClient` interceptor / `WebClient` filter |
| Error decoding | `ErrorDecoder`, `FeignException` | `RestClient` status handlers/exceptions or `WebClient` filters / response handlers |
| JSON/content negotiation | Feign encoders/decoders and configured Spring codecs | `HttpMessageConverter`/codecs of Spring HTTP client |
| Retries | Feign `Retryer`/config and application policy | Retries/circuit breakers designed in application/client resilience layer |
| Timeouts/pools/TLS | Feign client transport and properties | `ClientHttpRequestFactory` or WebClient connector |
| Metrics/tracing | Feign/Micrometer integration, Spring Cloud instrumentation | `RestClient`/`WebClient` observation and Spring instrumentation |
| Load balancing | Spring Cloud client name/load balancer config | Dedicated builder/transport/Spring Cloud integration config |

**Do not copy-paste Feign properties into Spring HTTP interfaces** and expect them to take effect. For example, `spring.cloud.openfeign.client.config.inventory.readTimeout` does not govern `RestClient` in Section 4. Likewise, do not assume interceptors, retryers, circuit breakers, or metrics automatically carry over to the new proxy.

## 7. HTTP Error Behavior and Exception Contracts

In integrated systems, the choice of client library is an internal implementation detail; business APIs must expose consistent error semantics. Classify errors by *meaning* before mapping responses:

| Upstream Situation | Interpretation | Handling Approach |
| --- | --- | --- |
| 200 with valid data | Success | Map DTO, verify business invariants |
| 200 with empty/malformed body | Contract violation | Log contract error; never treat null as success |
| 404 for missing SKU | May mean "does not exist" per contract | Map to domain not-found if specified by API; avoid blind retries |
| 400/422 from invalid request | Data/contract error | Fix request or return business validation error |
| 401/403 | Authentication/authorization failure | Check credentials and permissions; no infinite retries |
| 429 | Upstream enforcing quota/rate limits | Respect `Retry-After` if present; slow down calls |
| 500/502/503 | Upstream error or unavailable | Circuit breaker, bounded retries if replay-safe |
| Connect/read timeout | Result state may be unknown | Avoid long waits; side effects require idempotency/reconciliation |
| Bulkhead full | App sheds load before calling | Fail fast or apply allowed fallback; no immediate retry |

With `RestClient`, 4xx/5xx responses are typically converted into exceptions when calling `retrieve()` under default handlers; status handling can be customized via `onStatus` or default status handlers. With `WebClient`, `retrieve()` also translates HTTP error statuses; Feign uses `ErrorDecoder` or Feign defaults. Place a **dedicated error-mapping adapter** so business logic never couples directly to transport exception classes.

### 7.1. Do Not Retry Every POST After a Timeout

Suppose `POST /reservations` persisted a stock hold, yet the response was lost and the client timed out. Retrying with a **new** idempotency key can create two reservations. Keep the same key across retries for the same logical operation and require server-side idempotency. When state is unknown, the API should support querying by business/command ID for reconciliation.

When combining retries with timeouts and bulkheads:

- Enforce an end-to-end deadline per request rather than summing unbounded waits per layer.
- Apply backoff with jitter, cap attempts, and classify retryable errors.
- Never immediately retry validation, auth, not-found, or bulkhead-rejection errors.
- Circuit breakers fail fast when upstream breaks persistently; bulkheads cap concurrency rather than replacing timeouts.
- When an API strictly depends on a partner, return an explicit error (e.g. 503) instead of fabricating dummy data.
- If Redis caching is used as a fallback, surface staleness explicitly and guard against cache stampedes when the partner or Redis recovers.

## 8. Authentication, Headers, TLS, and Metadata Propagation

Each client must define explicitly:

1. **Base URLs and endpoints** per environment; never take URLs from client requests (prevents SSRF).
2. **Outbound authentication**: service tokens, OAuth2 client credentials, mTLS, or request signing per contract.
3. **Allowed headers to propagate**: standard correlation IDs/trace context and required metadata; never forward a user's `Authorization` header blindly to an unrelated partner.
4. **Timeouts and connection pools** aligned with RTO/SLO, traffic, and upstream quotas.
5. **TLS/truststores/proxies** matching real network topology; never disable certificate verification as a quick environment workaround.
6. **Logging boundaries**: never log tokens, cookies, sensitive bodies, or URL queries containing personal data.

In HTTP interfaces, metadata can be explicit `@RequestHeader` parameters (transparent, easy to test) or injected via interceptors/filters per unified policy. Feign commonly uses `RequestInterceptor`—same goal, different configuration hook. If using Micrometer/Observation tracing, verify Boot-managed builders and real trace propagation instead of hand-rolling malformed `traceparent` headers.

**Correlation IDs are not idempotency keys.** Correlation IDs tie together all attempts within a workflow; idempotency keys identify a single logical action for deduplication. Never reuse a correlation ID as a deduplication key across an entire flow.

## 9. Contract Testing to Compare Two Clients

When switching client libraries, prove that the **HTTP wire contract stays unchanged**. Use a real mock HTTP server like WireMock or `MockWebServer`, alongside integration tests exercising the configured proxy/HTTP client:

| Scenario | What to Check | Acceptance Criterion |
| --- | --- | --- |
| Normal SKU GET | Method, path encoding, `Accept`, body parse | DTO and path match contract |
| Query/path with spaces, Unicode, special chars | URI encoding of both clients | No malformed URLs or double-encoding |
| POST reservation | `Content-Type`, JSON body, `Idempotency-Key` | Logical operation keeps a stable key |
| HTTP 404/409/422 | Response status and error schema | Consistent domain error mapping |
| HTTP 429/503 + `Retry-After` | Wait times/attempts | No retry storms; honors deadlines |
| Cannot open connection | Connect timeout | Fails early; permits/resources released |
| Upstream hangs reading body | Read/response timeout | Request threads/connections do not hang forever |
| Empty/malformed body | Converter/decoder | Never treated as valid business data |
| Redirects, compression, charset | Behavior of chosen transport | Complies with security policy and contract |
| Trace/correlation | Outbound request headers | Required propagation present without leaking tokens |
| Concurrent burst | Connection pool, bulkhead, timeouts | Stays within concurrency budget |
| OpenFeign → HTTP interface | Compare requests/responses from both clients | Identical semantics post-migration |

If an API returns 429, never write a test asserting only "an exception was thrown": verify rate-reduction policy, attempt counts, and total elapsed time. For side-effecting POSTs, simulate committing on the first call while dropping the response; verify server-side idempotency, as client libraries cannot enforce it alone.

### 9.1. Testing Proxy and Client Config per Profile

Use a Spring Boot test loading environment configuration against a mock server to confirm the `InventoryHttpClient` bean injects and applies profile base URLs and timeouts. Exercise real error paths through the client/adapter rather than mocking the entire interface, because mocking the interface hides URL encoding bugs, media-type mismatches, error handlers, and network timeouts.

When multiple clients share a type, assign clear bean names/qualifiers and ensure unrelated partners never share auth/header configs. Prevent undersized or unbounded HTTP connection pools from starving JDBC, Redis, or broker consumer threads under load.

## 10. Roadmap for Migrating from OpenFeign to Spring HTTP Interfaces

Break the migration into small, measurable steps:

1. **Inventory existing Feign clients**: paths, methods, queries, headers, bodies, error decoders, encoders/decoders, interceptors, auth, timeouts, retries, load balancing, logging, metrics, and tracing.
2. **Freeze contracts** with tests checking real HTTP requests/responses, especially enums, dates, `Pageable`, multipart, PATCH, empty responses, and error payloads.
3. **Select Spring transport**: `RestClient` for MVC/blocking; `WebClient` for reactive; configure pools, timeouts, TLS, and observability per environment.
4. **Migrate one low-risk client**: replace `@FeignClient`/mappings with `@HttpExchange`/`@GetExchange` and register the proxy via `HttpServiceProxyFactory`.
5. **Redesign extensions**: Feign interceptor → `RestClient` interceptor, Feign `ErrorDecoder` → status handling, retryer/circuit breaker → explicit resilience policy. Only reuse components with identical semantics.
6. **Compare behavior**: against the same stub upstream, verify both clients emit identical HTTP methods, URLs, headers, bodies, timeouts, errors, and traces per contract.
7. **Roll out gradually**: toggle implementations by configuration or behind a shared adapter interface. Watch p95/p99 latency, errors, retry counts, connection pools, and key business outcomes.
8. **Clean up legacy code** once no references remain: remove unused Feign starters/configs/beans, update dashboards, and update operational runbooks.

Do not migrate all clients in a big bang merely for "consistency". In complex integrations, every transport change can affect SSL, proxies, auth, retries, codecs, and resource limits. Migrations should have concrete goals and measurements.

### 10.1. Cases Where Annotations Cannot Be Swapped One-for-One

- Feign uses `@SpringQueryMap` or specialized query-object contracts; parameters and encoding must be explicitly redefined on the HTTP interface.
- Feign uses an `ErrorDecoder` mapping status/body to domain exceptions; port the mapping logic explicitly.
- Feign uses client-specific TLS, auth signing, proxies, or load balancing; recreate equivalent settings on `RestClient`/`WebClient`.
- Feign uses custom fallbacks/circuit breakers; verify execution order (retry → circuit breaker → bulkhead) when replacing.
- Multipart uploads/downloads, streaming, SSE, reactive streams, or large bodies; return types and buffering differ and require benchmarking/testing.
- Interceptors adding dynamic headers or non-standard JSON serialization; contract tests must inspect exact wire bytes when request signatures depend on canonical encoding.

## 11. Combining HTTP Interfaces with Other Integration Components

### JDBC and Transactions

A database command and an outbound HTTP call do not share an atomic transaction. Spring `@Transactional` manages only its local transactional resource; it cannot roll back an already-executed HTTP request. Use an outbox for post-commit event publishing, sagas for multi-step orchestration with compensation, and idempotency for replayable operations.

### Redis Cache and Circuit Breakers

Caching reduces partner API traffic, yet requires TTLs, invalidation, and stampede protection. When a partner fails, serve stale cached data **only if business rules allow it**. Enforce circuit breakers, bulkheads, and timeouts at the HTTP client layer rather than expecting declarative annotations to provide resilience automatically.

### Kafka/RabbitMQ and Spring Integration

A message consumer calling an HTTP interface inherits the same latency and timeout impacts as a controller. When downstream fails, ack/retry/DLQ and idempotency rules determine whether side effects are lost or duplicated. Never ack a message as complete before processing finishes; never retry failing HTTP calls on the same message endlessly in a tight hot loop. In async flows, test correlation ID and trace-context propagation across boundaries.

### Observability

Emit metrics with bounded tags such as `dependency="inventory_api"`, `operation="reserve"`, `outcome="timeout"`. Never place raw URLs containing SKUs, user IDs, order IDs, correlation IDs, or trace IDs in metric labels. Detailed identifiers belong in access-controlled structured logs and traces with data minimization. For both HTTP interfaces and Feign, verify instrumentation **on the live client**, not just by looking at annotation names.

## 12. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| `@HttpExchange` creates a server endpoint | It is a client annotation; server controllers use dedicated server registration mechanisms |
| Having annotations makes Spring Boot auto-create proxies in all versions | Proxies/clients must be registered according to your framework version's capabilities |
| Spring HTTP interface is a new HTTP engine | It is a declarative layer; requests execute via `RestClient`/`WebClient` or matching adapters |
| OpenFeign and Feign core are identical | Spring Cloud OpenFeign adds Spring-specific integration and configuration |
| `@FeignClient` and `@HttpExchange` swap 1:1 | Bean registration, interceptors, error models, retries, and timeouts can differ |
| Spring HTTP interfaces are always reactive | Blocking vs reactive depends on the adapter and return types |
| Feign retries identically to `RestClient` by default | Defaults and retry configs vary by library and version; always verify |
| A 2-second read timeout is the total deadline | Connection setup, queuing, retries, backoff, and internal work also consume time |
| Adding an idempotency header to POST is enough | Upstream must persist and enforce idempotent responses |
| Load balancing works automatically because the interface uses Spring | Requires configuring service discovery/load balancer or appropriate endpoints |
| Mocking the interface suffices for integration testing | Must verify real HTTP requests/responses through the transport |

## 13. Checklist for Choosing and Operating a Client

- [ ] Identified exact Spring Boot/Framework/Cloud versions and supported client options.
- [ ] Selected `RestClient`, `WebClient`, Spring Cloud OpenFeign, or an external library based on blocking/reactive needs, discovery, tooling, and contracts.
- [ ] Interface accurately specifies methods, path/query encoding, headers, bodies, content types, and return types.
- [ ] Proxy/Feign beans are properly registered, and each partner has dedicated base URL, credentials, timeouts, and pools as needed.
- [ ] Connect/read/response timeouts, total deadlines, retries/backoff, circuit breakers, and bulkheads have explicit policies.
- [ ] HTTP, transport, deserialization, and empty-body failures translate into meaningful domain errors.
- [ ] Side-effecting POST/PUT/PATCH operations carry idempotency keys or reconciliation for retries after timeouts.
- [ ] Auth headers and correlation/trace contexts cross boundaries safely without exposing tokens or PII.
- [ ] Real wire contracts verified against a mock HTTP server: success, 4xx, 5xx, timeouts, encoding, malformed bodies, concurrency.
- [ ] When migrating from Feign, ported interceptors, error decoders, retries/timeouts/metrics rather than changing annotations alone.
- [ ] Integrations with DB/Redis/brokers properly coordinate transactions, cache fallbacks, acks, retries, and duplicate deliveries.
- [ ] Metric tags stay bounded, logs/traces respect privacy policies, and alert dashboards remain accurate after client changes.

**Desired Outcome:** Development teams understand that Spring HTTP interfaces declare contracts and build proxies over Spring HTTP clients, OpenFeign is its own client ecosystem integrated by Spring Cloud, and external libraries bring their own contracts and extensions. Regardless of the tool chosen, integration correctness rests on HTTP contracts, transport configuration, error handling, idempotency, observability, and end-to-end testing.
