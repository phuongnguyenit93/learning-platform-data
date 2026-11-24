# Creating a WebClient from a Spring Boot-Managed WebClient.Builder

## Objectives and Context

In a Spring Boot application, integrating with external services often starts with an HTTP call: fetching product information, checking inventory, confirming payments, or sending data to a partner system. `WebClient` is Spring WebFlux's asynchronous HTTP client supporting reactive programming. This lesson focuses on **how to create `WebClient` instances from the `WebClient.Builder` provided by Spring Boot**, rather than manually assembling every connection component.

After this lesson, you should be able to:

- Inject `WebClient.Builder` into a Spring component and create a dedicated `WebClient` for each downstream system.
- Externalize service URLs and related configuration outside the source code.
- Understand what Spring Boot auto-configures and the scope of customizations applied to the builder.
- Use the client in an integration adapter, handling errors, timeouts, and testing without losing Boot's baseline configuration.

This content falls within the scope of organizing system integration in Spring Boot: an HTTP client is an outbound communication adapter that must respect data contracts, configuration, business transactions, error handling, observability, and testing. `WebClient` only executes HTTP calls; it does not automatically guarantee distributed transactions, duplicate prevention, or safe retry mechanisms.

## 1. How Does Spring Boot Manage WebClient.Builder?

When Spring WebFlux is on the classpath and the corresponding auto-configuration is active, Spring Boot pre-creates a **`WebClient.Builder` bean with `prototype` scope**. Each time Spring injects the builder at an injection point, it provides a builder already configured by Boot. From this builder, the application sets `baseUrl`, headers, filters, and custom rules, and then calls `build()`.

The Boot-provided builder inherits built-in configuration such as:

- Consistently managed HTTP codecs.
- A `ClientHttpConnector` matching the HTTP libraries on the classpath; with Reactor Netty or Jetty, Boot can share appropriate resources between the server and client.
- Registered `WebClientCustomizer` beans.
- Observation/tracing/metrics integration **when** the application has the corresponding observability components and configuration.

Two types of objects need to be distinguished:

| Component | Lifecycle and Characteristics | How to Use |
| --- | --- | --- |
| `WebClient.Builder` | Stateful; calls like `baseUrl()` or `defaultHeader()` mutate the builder | Configure the client at initialization; be careful when sharing |
| `WebClient` after `build()` | An object with stable configuration, safely reusable across multiple requests | Store as a field in an adapter/service; do not recreate per request |
| `WebClientCustomizer` | Customization applied by Boot to managed builders | Use for application-wide rules |

~~~mermaid
flowchart LR
    A["Spring Boot auto-configuration"] --> B["WebClient.Builder (prototype)"]
    C["Codecs / Connector / Customizers"] --> B
    B --> D["Per-downstream configuration"]
    D --> E["Built WebClient"]
    E --> F["CatalogGateway / adapter"]
    F --> G["Catalog HTTP API"]
~~~

> **Key takeaway:** `WebClient.create(...)` and `WebClient.builder()` are valid Spring Framework APIs, but creating a client manually this way does not automatically receive the full configuration and `WebClientCustomizer` beans that Spring Boot applies to the injected builder. In Boot applications, prefer constructor injection of `WebClient.Builder`.

## 2. Preparing Dependencies and Configuration

A common way to obtain `WebClient` along with Reactor Netty is adding the WebFlux starter, even when the application primarily uses Spring MVC:

~~~groovy
// build.gradle (Gradle Groovy DSL)
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

In an application that already has `spring-boot-starter-web` (Spring MVC), adding the WebFlux starter **does not automatically switch the web application type to reactive**; the server model and HTTP client are separate decisions. If the system does not need a reactive API, `RestClient` is also a suitable choice. This lesson uses `WebClient` because the adapter needs to return `Mono` or `Flux`.

For example, suppose there is a product catalog service with the API `GET /v1/products/{id}`. Instead of hardcoding the address in Java, declare it in configuration:

~~~yaml
# application.yml
integrations:
  catalog:
    base-url: ${CATALOG_BASE_URL:https://catalog.example.org}
~~~

`https://catalog.example.org` is only an illustrative address. In each environment, set the `CATALOG_BASE_URL` variable accordingly. Do not commit real passwords, access tokens, or API keys into the repository.

Map the configuration into a strongly typed object:

~~~java
// CatalogProperties.java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integrations.catalog")
public record CatalogProperties(URI baseUrl) {
}
~~~

With Spring Boot 3.x/4.x and Java 17+, a single-constructor record like the one above can be bound via configuration properties. The properties bean will be registered using `@EnableConfigurationProperties` in the next step.

## 3. Creating a WebClient from the Injected Builder

Configure the bean representing the connection to the Catalog API:

~~~java
// CatalogClientConfiguration.java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogClientConfiguration {

    @Bean("catalogWebClient")
    WebClient catalogWebClient(
            WebClient.Builder builder,
            CatalogProperties properties) {

        return builder
                .baseUrl(properties.baseUrl().toString())
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
~~~

Explanation of each part:

1. Spring Boot injects the auto-configured `WebClient.Builder` into the `builder` parameter.
2. `CatalogProperties` provides the URL from environment configuration.
3. `baseUrl(...)` sets the root URL for relative URIs.
4. `defaultHeader(...)` sets a default header when a request does not explicitly specify that header.
5. `build()` creates a reusable `WebClient`; `@Bean("catalogWebClient")` allows selecting the right client with a qualifier.

If you only integrate with a single simple endpoint, you can also inject the builder directly into the adapter's constructor and build the client there. When a project integrates with multiple external services, registering named `WebClient` beans makes the configuration and injection points clearer.

Adapter calling the external service:

~~~java
// ProductDto.java
public record ProductDto(String id, String name, boolean active) {
}
~~~

~~~java
// CatalogGateway.java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class CatalogGateway {

    private final WebClient catalogWebClient;

    public CatalogGateway(
            @Qualifier("catalogWebClient") WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    public Mono<ProductDto> findById(String productId) {
        return catalogWebClient.get()
                .uri("/v1/products/{id}", productId)
                .retrieve()
                .bodyToMono(ProductDto.class);
    }
}
~~~

If `integrations.catalog.base-url` is `https://catalog.example.org` and `productId` is `P100`, the request takes the form `GET https://catalog.example.org/v1/products/P100`.

- `uri("/v1/products/{id}", productId)` expands the URI template and handles parameter encoding; avoid concatenating URL strings directly from input data.
- `retrieve()` is a concise way to handle standard responses; by default, 4xx/5xx responses are converted into a `WebClientResponseException`.
- `bodyToMono(ProductDto.class)` decodes a JSON object according to the data contract. If the API returns a list or a stream of items, choose an appropriate operator such as `bodyToFlux(...)`.

Calling `findById(...)` **returns a task description** as a `Mono`; the network request typically starts only when there is a subscriber. For example, a WebFlux controller can return `Mono<ProductDto>` directly and let the framework subscribe. Do not call `subscribe()` inside the adapter just to "trigger" the HTTP request, as that makes it difficult to propagate results and errors back to the business flow.

## 4. Separating Multiple WebClients and Avoiding Configuration Leakage

Suppose the application connects to Catalog and Inventory using two different hosts, headers, or authentication mechanisms. Create two separate clients:

~~~java
@Bean("catalogWebClient")
WebClient catalogWebClient(WebClient.Builder builder) {
    return builder.baseUrl("https://catalog.example.org").build();
}

@Bean("inventoryWebClient")
WebClient inventoryWebClient(WebClient.Builder builder) {
    return builder.baseUrl("https://inventory.example.org").build();
}
~~~

This is a simplified example to illustrate separating beans; in production code, both URLs should still come from configuration properties. Each builder parameter is resolved by Spring from a prototype bean, so they can be configured independently.

Note the case where **you hold onto the same builder reference** to create multiple clients:

~~~java
// builder is the same instance in the snippet below
WebClient catalog = builder.clone()
        .baseUrl("https://catalog.example.org")
        .defaultHeader("X-System", "catalog")
        .build();

WebClient inventory = builder.clone()
        .baseUrl("https://inventory.example.org")
        .defaultHeader("X-System", "inventory")
        .build();
~~~

`clone()` isolates subsequent configuration state. If you continuously mutate the same builder and call `build()`, previous headers or filters may remain on the client built afterward. When you already have a `WebClient` and need a variant, `existingClient.mutate()...build()` creates a new instance based on the current configuration without modifying the original client.

**Rules for choosing configuration scope:**

| Requirement | Recommended Approach | Notes |
| --- | --- | --- |
| Catalog-specific URL, headers, or filters | Customize the builder right before Catalog's `build()` | Does not affect other adapters |
| Multiple clients created from one retained builder | `builder.clone()` for each branch | Prevents accidentally carrying over configuration between branches |
| Application-identifying header or common non-secret filter | `WebClientCustomizer` bean | Affects every Boot-managed builder |
| Deriving a client from an existing running client | `webClient.mutate().build()` | Inherits the original client's configuration |
| Low-level HTTP connection settings | Boot properties or connector customization | Check impact on pooling, timeouts, and resource lifecycle |

## 5. Global Customization with WebClientCustomizer

When you genuinely need a setting applied to **every** HTTP client created from a Boot-managed builder, register a `WebClientCustomizer` bean:

~~~java
// Add inside a @Configuration class
@Bean
WebClientCustomizer clientIdentityCustomizer() {
    return builder -> builder.defaultHeader(
            "X-Client-Application",
            "spring-boot-integration");
}
~~~

The snippet assumes you have imported the `WebClientCustomizer` type corresponding to your Boot version:

- **Spring Boot 3.x:** `org.springframework.boot.web.reactive.function.client.WebClientCustomizer`.
- **Spring Boot 4.x:** `org.springframework.boot.webclient.WebClientCustomizer`.

`WebClientCustomizer` applies to Boot-managed builders, so do not put secret tokens, partner-specific headers, or filters making assumptions about a single API in a global customizer. Those belong in the configuration of that specific client.

If you need to attach a per-user bearer token or an expiring access token, use an appropriate security mechanism/filter per downstream. A `defaultHeader("Authorization", ...)` with a static token will not automatically handle token refresh.

## 6. Timeouts, Errors, and Integration Flow Reliability

Successfully creating a client is only the first step. A production HTTP adapter must enforce time bounds and define outcomes when the downstream service behaves abnormally.

### Timeouts

There are at least three concepts that often get mixed up:

- **Connect timeout:** time allowed to establish a connection to the server.
- **Read/response timeout:** limit when waiting for response data at the HTTP transport layer.
- **Reactive `timeout(...)`:** time limit on the `Mono`/`Flux` processing chain at the point where the operator is placed; this may include operations beyond the network call.

In **Spring Boot 4.x**, you can use shared HTTP client configuration, for example:

~~~yaml
spring:
  http:
    clients:
      connect-timeout: 2s
      read-timeout: 5s
~~~

These keys affect HTTP clients auto-configured by Boot; only set global values if they fit your services. Spring Boot 3.x has different connector configuration properties and APIs; do not copy 4.x properties mechanically into 3.x. If you need per-partner timeouts, choose the mechanism supported by your Boot version, or configure the connector for that specific client.

At the use-case layer, you can impose an overall time limit on a request:

~~~java
public Mono<ProductDto> findByIdWithDeadline(String id) {
    return findById(id)
            .timeout(java.time.Duration.ofSeconds(6));
}
~~~

This is a pipeline timeout, not a replacement for connection and response-read timeouts. If you manually replace `clientConnector(...)` with a hand-built `ReactorClientHttpConnector`, you may override the connector/resources prepared by Boot. Only do this when necessary, and verify connection pool lifecycle, resources, and observability afterward.

### Distinguishing HTTP Errors from Connection Errors

| Scenario | Typical Outcome | Handling at the Integration Boundary |
| --- | --- | --- |
| 2xx with contract-compliant JSON | `Mono<ProductDto>` emits data | Map to internal domain model |
| 204 or empty body | `Mono.empty()` in applicable cases | Explicitly define whether empty is allowed by contract |
| 404 | `WebClientResponseException.NotFound` by default with `retrieve()` | Decide whether "not found" is a business result or an error |
| Other 4xx/5xx | `WebClientResponseException` | Classify as contract, authorization, or downstream error |
| DNS, connection refused, I/O | Typically `WebClientRequestException` | Observe, apply controlled fallback/retry |
| Malformed or undecodable JSON | Decoding error | Check API version and data contract |

You can define custom 404 mapping for an adapter without treating every error response identically:

~~~java
public Mono<ProductDto> findRequiredById(String id) {
    return catalogWebClient.get()
            .uri("/v1/products/{id}", id)
            .retrieve()
            .onStatus(
                    status -> status.value() == 404,
                    response -> Mono.error(
                            new IllegalStateException(
                                    "Catalog does not have product: " + id)))
            .bodyToMono(ProductDto.class);
}
~~~

In a real application, replace the illustrative `IllegalStateException` with a purposeful business exception or result type, and map it at the API boundary. Avoid logging full response bodies or tokens. If you need different handling across status, headers, and body, consider `exchangeToMono(...)`; in that case, the application is responsible for handling every response branch.

Never enable unconditional retries. For idempotent `GET` requests, bounded retries with backoff for transient errors may be appropriate. For operations that create orders, record payments, or send messages, retries can create duplicate records; you must have an idempotency key, retry contract, and proper deduplication mechanism. Database transactions in Spring do not automatically roll back side effects that already occurred on an external HTTP system.

### Observability and Security

A Boot-managed builder is a good integration point for the application's existing metrics/tracing setup, though actual observation generation depends on dependencies and observability configuration. Use low-cardinality metric/tag names; do not include tokens, full URLs containing sensitive identifiers, or personal payloads in tags or logs. Authentication headers must be scoped strictly to the intended downstream service.

## 7. Testing Two Distinct Layers of Responsibility

A useful test suite should separate **Spring Boot wiring** from **HTTP adapter behavior**:

1. **Wiring test:** start the Spring context with `integrations.catalog.base-url` pointing to a mock HTTP server; verify the `catalogWebClient` bean is created using environment configuration and can be injected into `CatalogGateway`. You can use `@SpringBootTest` and `@DynamicPropertySource` to supply the mock server URL to the context.
2. **HTTP contract test:** use MockWebServer or WireMock to verify the method, path, headers, JSON decoding, and proper handling of 404/500 responses. Tests must call the mock server, never a real external service.
3. **Timing/timeout test:** simulate a slow server response or closed connection, verifying deadlines and error translation according to the adapter's policy.
4. **Multi-downstream test:** verify that requests to Catalog do not carry the base URL, API key, or headers meant only for Inventory.

Example verification of a reactive response (placed in a test with a configured mock HTTP server and gateway):

~~~java
StepVerifier.create(catalogGateway.findById("P100"))
        .assertNext(product -> {
            assertEquals("P100", product.id());
            assertEquals("Keyboard", product.name());
        })
        .verifyComplete();
~~~

`StepVerifier` comes from the `io.projectreactor:reactor-test` test dependency. The test also needs matching JSON stubbed on the mock server and JUnit imports; the snippet above only shows the assertion part. To prove Boot actually participates in configuration, include at least one test running inside a Spring context rather than calling `WebClient.builder()` directly in every test.

## 8. Common Configuration Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `No qualifying bean of type WebClient.Builder` | Spring WebFlux missing from classpath or auto-configuration excluded | Check dependencies and auto-configuration conditions |
| `No qualifying bean of type WebClient` | Boot provides a **builder**, not an auto-generated `WebClient` bean per API | Define a `@Bean` from the builder as shown |
| Two downstreams mix up URLs/headers | Reusing the same stateful builder, or a global customizer holds service-specific config | Isolate builders/clone, use named beans and `@Qualifier` |
| Returning `Mono` sends no request | No subscriber in the execution flow | Return the publisher to the framework/consumer responsible for subscribing |
| Hangs or unexpected slowness | Missing timeouts, slow downstream, or exhausted pool | Configure timeouts and monitor transport/pool metrics |
| `DataBufferLimitException` on large payloads | Codec buffer limit exceeded | Design streaming/pagination; only increase `maxInMemorySize` with justification |
| Observation metadata missing | Using a manually created client or missing observation setup | Use Boot's builder and verify observation dependencies/config |
| `block()` slows down reactive processing | Blocking on an event loop or reactive pipeline | Keep `Mono`/`Flux` end-to-end; only block at controlled imperative boundaries |

## 9. Completion Criteria for a WebClient Adapter

Before shipping an HTTP integration to production, review this checklist:

- [ ] Used the Boot-provided `WebClient.Builder` with appropriate dependencies and auto-configuration.
- [ ] Separated URLs and environment configuration from source code; secrets come from a secret/config provider.
- [ ] Dedicated client per downstream service and unambiguous injection points with `@Qualifier` where needed.
- [ ] Defined DTOs, HTTP statuses, empty payloads, and connection errors according to contract.
- [ ] Configured appropriate timeouts, clear retry/idempotency policies, and required observability.
- [ ] Tested against a mock server covering at least success, error, and timeout branches.

**Remember:** Spring Boot owns the baseline configuration of `WebClient.Builder`; the adapter owns downstream-specific configuration; the business layer owns how results, errors, and duplicate prevention are interpreted. Maintaining these boundaries makes integration flows easy to evolve, measure, and test.

## References

- [Spring Boot — Calling REST Services, WebClient](https://docs.spring.io/spring-boot/reference/io/rest-client.html): prototype builder, HTTP runtime, customization, and Boot integration.
- [Spring Boot 3.4 — Calling REST Services](https://docs.spring.io/spring-boot/3.4/reference/io/rest-client.html): cross-checking configuration with the 3.x branch.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): builder, `mutate()`, codecs, and connectors.
