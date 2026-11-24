# Boundaries Between Spring Boot HTTP Client Configuration and Business Service Integration

## 1. The Big Picture

A Spring Boot application calling external Catalog, Payment, Shipping, or partner HTTP services must separate **the technical capability to communicate** from **the business meaning of that communication**.

- **Spring Boot/HTTP infrastructure** prepares `RestClient.Builder`, `RestTemplateBuilder`, or `WebClient.Builder`; detects the HTTP transport; and applies connection settings, TLS, message converters, codecs, customizers, observability, and technical defaults.
- **Integration adapter** selects the host, API version, endpoints, request headers, wire DTOs, partner authentication, service-specific timeouts, response status mapping, and upstream contract rules.
- **Application/domain** executes the use case: quoting, checking stock, payment state, whether fallbacks are allowed, quantity rules, currency rules, and business authorization.
- **Inbound API/controller** translates the end client's HTTP request into a use case and maps domain results/exceptions to the public HTTP response. Never return raw partner payloads or error bodies straight to end users.

**Core rule:** Boot helps construct HTTP requests; the adapter understands the external system; the domain decides what to do with the outcome. No auto-configuration knows on its own whether a partner's 404 means "item does not exist", "wrong endpoint path", or "transaction not created yet".

This lesson belongs to the **Spring Boot - web-runtime** module, **HTTP client** group; it focuses on setting clean boundaries rather than merely introducing three libraries. The complete example uses **Java 17+, Maven, Spring Boot 3.5.16, and Spring Framework 6.2.x**. When upgrading to a new major Boot version, re-verify package and property names—especially in the HTTP client group.

## 2. Tracing Boundaries Through a Single Request

```text
GET /api/quotes/1?quantity=3
           |
           v
    QuoteController              -> Public HTTP contract
           |
           v
    CatalogApplicationService    -> Business rules: stock, pricing
           |
           v
    CatalogGateway (port)        -> Need: find item by ID
           ^
           |
    HttpCatalogGateway           -> Partner API: path, DTO, 404/503
           |
           v
    catalogRestClient (bean)     -> Boot builder/transport
           |
           v
    GET /partner/items/1        -> Catalog HTTP service
```

When Catalog renames JSON field `priceVnd` to `amountInMinorUnits`, the adapter and contract tests adapt without forcing domain changes. When switching transport from `RestClient` to `WebClient` or a partner SDK, rules like maximum quantity and price calculation should not live inside the client. When business rules disallow selling out-of-stock items, that is a domain rule, not automatically the partner's HTTP 409.

### Responsibility Assignment Table

| Decision | Boot/transport | Integration adapter | Application/domain |
| --- | --- | --- | --- |
| Constructing `RestClient.Builder` | Yes | Injects and builds | No |
| HTTP request factory, TLS, codecs | Baseline config | Overrides per host if needed | No |
| Catalog base URL | Does not know automatically | Yes, from typed configuration | No |
| URI `/partner/items/{id}` | No | Yes | No |
| Access token for catalog | Provides supporting mechanisms | Owns acquisition and audience matching | Decides permitted identity |
| Parsing `CatalogWireItem` | Converter decodes JSON | Validates schema, maps to domain | Independent of wire DTO |
| Status 404 from catalog | Client throws exception | Maps to empty/not-found per contract | Handles missing item |
| Status 503 from catalog | Client sees error | Maps to dependency unavailable | Decides not to quote |
| Returning 409 to buyer | No | No | Public API/domain policy |
| Default connect/read timeouts | Defaults | Overrides per service SLA | Total deadline per use case |
| Retrying GET vs. POST | Library offers API | Understands idempotency contract | Permits or forbids per use case |
| Observability | Builders/Actuator integration | Partner context/name, status | Business metrics |

Small projects do not need excessive ceremony. Still, **every decision must live at the layer with enough context to decide rightly**.

## 3. What Does Boot 3.5 Actually Auto-Configure?

### 3.1. `RestClient` for Imperative Applications

`RestClient` is a **synchronous, fluent** HTTP client. Spring Boot 3.5 provides a **prototype** `RestClient.Builder` bean pre-configured with HTTP message converters, a request factory, and environment customizers.

```java
@Bean
RestClient catalogClient(RestClient.Builder builder) {
    return builder.baseUrl("https://catalog.example.internal").build();
}
```

This is a snippet, separate from the complete project in Section 10. Boot **does not automatically create** a `catalogClient` bean for you. Your app supplies the service URL and owns the config; the built client is typically a reusable singleton bean rather than recreated on every request.

### 3.2. `RestTemplate` in Legacy Code

Boot normally **does not provide a default `RestTemplate` bean**, providing `RestTemplateBuilder` instead:

```java
@Bean
RestTemplate legacyClient(RestTemplateBuilder builder) {
    return builder
            .rootUri("https://legacy.example.internal")
            .connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(3))
            .build();
}
```

Snippet requires imports for `RestTemplateBuilder`, `RestTemplate`, and `Duration`. `RestTemplate` is **blocking** just like `RestClient`; migrate to `RestClient` for its fluent API and extensibility, not under the illusion that `RestTemplate` was blocking while `RestClient` isn't. Existing well-tested code with interceptors can migrate incrementally.

### 3.3. `WebClient` for Reactive or Streaming

`WebClient.Builder` is prepared when WebFlux is on the classpath. `WebClient` returns `Mono`/`Flux` and suits non-blocking HTTP.

```java
@Bean
WebClient warehouseClient(WebClient.Builder builder) {
    return builder
            .baseUrl("https://warehouse.example.internal")
            .build();
}
```

This snippet is not a standalone project. In a true WebFlux app, never call blocking `RestClient`/`RestTemplate` or `WebClient.block()` on a Reactor event loop. In an MVC app, `WebClient` can still be used for outbound HTTP, though **that alone does not turn the whole app into WebFlux**.

### 3.4. Builders, Customizers, and Scope

| Mechanism | Scope | Put here | Do not put here |
| --- | --- | --- | --- |
| Boot `spring.http.client.*` | Defaults for synchronous clients | Connect/read timeouts, request factory | Business 404/409 policies |
| Boot `spring.http.reactiveclient.*` | Defaults for reactive connector | Connect/read timeouts, connector | Business fallbacks |
| `RestClientCustomizer` | Additive customization across Boot-managed `RestClient` builders | Shared non-sensitive technical rules | A single partner's bearer token |
| `WebClientCustomizer` | Additive customization for `WebClient` | Technical filters, observations when appropriate | Partner-specific tokens/URLs |
| Per-partner bean | One HTTP upstream | Base URL, auth, SLA overrides, dedicated SSL trust | Product pricing or shipping rules |
| Per-request headers | One call | Item ID, idempotency key, controlled user context | Mutable global state |
| Application service | One use case | Quantity, price, business status | JSON fields, TCP pools |

`RestClient.Builder` and `WebClient.Builder` are **stateful**. When using one builder to build multiple clients and repeatedly changing `baseUrl`/headers, later clients retain earlier edits; inject separate builder instances or call `builder.clone()`. Once built, the client itself is suitable for reuse.

Calling `RestClient.create()` or `WebClient.create()` directly skips Boot's auto-customizers and defaults applied to injected builders. Never replace auto-configured builders without understanding the impact on TLS, codecs, metrics, tracing, and transports.

## 4. Boot Configuration Differs from Partner Configuration

### 4.1. Boot 3.5 Properties

```properties
# Defaults for synchronous HTTP clients:
spring.http.client.connect-timeout=2s
spring.http.client.read-timeout=3s
spring.http.client.redirects=dont-follow

# Defaults for reactive HTTP connector, if using WebClient:
spring.http.reactiveclient.connect-timeout=2s
spring.http.reactiveclient.read-timeout=3s
```

These are **Spring Boot 3.5** property names. Newer Boot releases introduce `spring.http.clients.*`; do not copy docs from another major version and assume config failed when keys don't match.

`connect-timeout` bounds establishing a connection; `read-timeout` bounds reading/waiting for a response per the underlying HTTP transport. They **are not necessarily a whole-use-case deadline**, especially with retries, pool waits, or sequential upstream calls.

### 4.2. Application-Defined Custom Properties

```properties
integrations.catalog.base-url=https://catalog.example.internal
integrations.catalog.api-version=v2
integrations.catalog.cache-ttl=15s
```

The `integrations.catalog.*` group is not recognized automatically by Boot. You must bind it via `@ConfigurationProperties`/`@Value` or custom config code. These properties express service contract settings; putting them in properties alone does not create a Catalog HTTP client.

**Distinction:** platform teams may supply connection addresses/networking; however, endpoint names, API versions, auth header conventions, and fallbacks belong to **the integration owner**. Cache TTL may be configured in the adapter, while whether stale prices/stock are acceptable is a business decision.

### 4.3. Type-Safe and Fail-Fast

```java
@Validated
@ConfigurationProperties(prefix = "integrations.catalog")
public record CatalogProperties(@NotNull URI baseUrl) {
}
```

This is a snippet. `@NotNull` catches missing properties when config binding/validation is active, and `URI` gives clear structure. It **does not** verify HTTPS usage, hostname allowlists, safe DNS resolution, or absence of sensitive paths. Production requires security validation and network egress controls.

### 4.4. Secrets and Environments

Dev environment example:

```properties
integrations.catalog.base-url=${CATALOG_BASE_URL:http://localhost:8080}
```

In production, provide controlled URLs and service secrets through environment config, secret managers, or SSL bundles/mTLS; **never commit API keys, private keys, or refresh tokens to Git**. In Kubernetes/containers, `localhost` refers only to the current container/pod, not another catalog service.

## 5. An HTTP Contract Is Not a Business Contract

### 5.1. The Same Status Can Mean Different Things

| Upstream HTTP result | Catalog item | Payment transaction | Email provider |
| --- | --- | --- | --- |
| 200 | Item exists | Current status | Result per contract |
| 202 | Async processing | Cannot confirm paid yet | Queued only |
| 204 | Empty body | Per contract | Per contract |
| 400 | Adapter sent invalid request | Invalid payment payload | Invalid email data |
| 401/403 | Wrong/expired service auth | Wrong token/audience | Invalid provider auth |
| 404 | Item does not exist | Transaction ID missing or unauthorized | Message resource missing |
| 409 | Schema/version conflict | Possible duplicate idempotency key | Send conflict |
| 422 | Invalid data | Business validation rejected | Invalid recipient |
| 429 | Rate limited | May need to wait | May need to wait |
| 503 | Catalog unavailable | **Unknown whether payment committed** | May have partially sent |
| Network timeout | Uncertain response | **Does not prove money wasn't deducted** | May have succeeded |

Boot and client libraries see only status codes and bytes. **The adapter understands the partner contract**, the application service decides use-case outcomes, and the public API picks external statuses. Never install one global exception handler turning every partner 404 into "item not found" when other services use 404 differently.

### 5.2. Three Error Categories to Separate

- **Transport**: DNS, TLS, connection refused, timeout, proxy failure, pool exhausted; there may be **no HTTP response**.
- **Protocol/contract**: 404/429/503, wrong content type, undecodable JSON, missing fields, incompatible API version.
- **Domain outcome**: missing item, out of stock, payment limit exceeded, currency rules, order conflict.

Never leak `HttpServerErrorException`/`WebClientResponseException` straight into domain logic if the domain shouldn't couple to HTTP libraries. Never return raw upstream error bodies to end clients, as they can reveal tokens, stack traces, or PII.

### 5.3. Adapters Map 404 by Contract, Not Habit

If catalog documents `GET /items/{id}` returning 404 when an item is absent, the adapter can return `Optional.empty()` from `find`. If a partner returns 404 due to a **wrong route or deprecated version**, that is an integration outage needing alerts—contract specs and contract tests distinguish them. Similarly, a 200 response with invalid JSON is a contract failure, **not** a valid item.

## 6. Boundaries for Timeouts, Retries, and Resilience

### 6.1. Timeouts

Boot supplies technical defaults; integration overrides per upstream SLA; application enforces an end-to-end deadline matching client experience.

```text
Browser deadline 3s
  |
  +-- Catalog GET: connect 500ms, read 800ms
  +-- Pricing rules: 200ms
  +-- Optional promotions: 300ms
  +-- Margin for retries, network overhead, gateway
```

This is an **illustrative budget**, not measurements from a live system. Giving each partner a 30s timeout while the API gateway times out after 3s wastes server resources. Track connect timeout, read timeout, pool acquire timeout, and total deadline independently.

### 6.2. Are Retries Safe?

Libraries provide technical retry hooks, yet only integration/business layers know:

- Catalog GETs are normally idempotent when the upstream respects GET semantics.
- Payment POSTs may already have succeeded before the client timed out; retrying without an idempotency key risks duplicate charges.
- Email POSTs may already have sent; retrying causes duplicate emails.
- 429s may include `Retry-After`; never retry unboundedly.
- Never infinitely retry 400, 401, 403, 404, invalid JSON, or contract mismatches.

Use max attempts, exponential backoff + jitter, total deadlines, and concurrency limits. Avoid stacking retries across gateway, service mesh, `WebClient`, and business code without counting total multiplied calls.

### 6.3. Circuit Breakers, Bulkheads, and Fallbacks

Spring Boot auto-configures client builders—**it does not automatically give each integration a domain-aware circuit breaker**. You can add Resilience4j or Spring Cloud CircuitBreaker when appropriate.

- **Circuit breaker:** temporarily stops calling an upstream experiencing dense failures.
- **Bulkhead:** limits concurrent requests/threads/connections dedicated to one partner.
- **Rate limit:** stays within upstream quotas.
- **Fallback:** serve cache/defaults only when **business rules permit stale/missing data**. Never silently pretend `available=true` or `price=0` when catalog returns 503.

Every policy needs an owner, metrics, and tests; none appear automatically just from using `RestClient.Builder`.

## 7. Security, Observability, and Trace Propagation

### 7.1. Per-Service Credentials, Never Global

Catalog's token goes only to Catalog. Never create a global `RestClientCustomizer` attaching `Authorization: Bearer ...` to every outbound HTTP client—that leaks the token to Shipping or Payment. With OAuth2, distinguish service credentials from on-behalf-of user delegation, ensuring correct scopes and audiences.

A singleton gateway **must never store a mutable user token in a field** per request, or concurrent requests will overwrite and leak across users. Pass controlled user context into per-request headers or use official thread-safe context propagation.

### 7.2. SSL Bundles

Spring Boot 3.5 supports `RestClientSsl`/`WebClientSsl` to apply truststores/keystores from named SSL bundles.

```java
@Bean
RestClient secureCatalog(
        RestClient.Builder builder, RestClientSsl ssl) {
    return builder
            .baseUrl("https://catalog.example.internal")
            .apply(ssl.fromBundle("catalog"))
            .build();
}
```

**Snippet**, non-standalone: requires importing `org.springframework.boot.autoconfigure.web.client.RestClientSsl` and defining an SSL bundle named `catalog`. Never use trust-all, disable hostname verification, or commit private keys to bypass SSL errors.

### 7.3. Metrics and Tracing

Using Boot-managed builders preserves Micrometer/Actuator/Observation integration when matching dependencies are active. Track p95/p99 latency, status classes, timeouts, connection pools, retry counts, and low-cardinality upstream names. Domain code can track outcomes like `quote.out_of_stock` or `quote.failed.catalog` separately from HTTP metrics.

Never log raw requests/responses containing PII, access tokens, or session IDs. Carry correlation/trace IDs across inbound → gateway → upstream, verify context propagation across async/reactive boundaries, and avoid high-cardinality customer IDs in metric tags.

### 7.4. SSRF

Never accept arbitrary URLs from a browser and fetch them with `RestClient` under backend privileges. Use fixed/allowlisted base URLs, validate schemes/domains/IPs/redirects, and enforce egress policies. In the demo project, localhost is used **solely to simulate an upstream**, never as production config.

## 8. Before-and-After Architecture Examples

### 8.1. Anti-Pattern: Everything Inside the Controller/Service

```java
// Anti-pattern snippet, not a complete program.
@GetMapping("/quote/{id}")
public Object quote(@PathVariable long id) {
    // 1. Build HTTP client and hardcode/choose URL inside controller.
    // 2. Call partner and parse raw JSON.
    // 3. Catch all exceptions and return 200 or 404 regardless of cause.
    // 4. Calculate price and handle out-of-stock inline.
    // 5. Return the partner's wire DTO directly.
    throw new UnsupportedOperationException("Do not use this pattern");
}
```

Warning signs: business code knows endpoint URLs and HTTP exceptions; logic is hard to test without networking; auth/timeouts get duplicated; and partner schema changes break controllers everywhere.

### 8.2. Clean Boundary Pattern

```java
interface CatalogGateway {
    Optional<CatalogItem> find(long itemId);
}

@Service
class QuoteService {
    private final CatalogGateway gateway;
    // Computes business logic solely from domain CatalogItem.
}
```

This is an **illustrative snippet** (incomplete Java). An `HttpCatalogGateway` implementation owns HTTP details. A fake `CatalogGateway` powers fast unit tests. The public API controller knows nothing about `RestClient`.

## 9. Requirements for the Standalone Runnable Example

The project below uses:

- **Spring Boot MVC** with `spring-boot-starter-web`, without the WebFlux starter.
- **RestClient** built from Boot 3.5's auto-configured builder.
- **CatalogProperties** binding the base URL from `application.properties` via `@ConfigurationPropertiesScan`.
- **CatalogGateway** port decoupling domain logic from HTTP.
- **HttpCatalogGateway** mapping 404 to empty, other client failures to dependency unavailable, and validating the response body.
- **CatalogApplicationService** validating quantity, stock, and safe price multiplication.
- **QuoteController** returning public JSON, with `PublicErrorAdvice` mapping domain errors to HTTP status codes.
- **DemoPartnerController** simulating the external service offline on localhost.
- **JUnit + MockRestServiceServer** testing the adapter without real networking and testing domain logic with a fake port.

This is valid Java 17+ code structured as a Maven project. No database, Docker, token, or Internet connection to a third-party API is required once dependencies are cached.

## 10. Complete Project: Spring Boot 3.5.16 + Java 17 + RestClient

### 10.1. File Structure

```text
client-boundary-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/clientboundary/
    │   │   ├── ClientBoundaryApplication.java
    │   │   ├── CatalogProperties.java
    │   │   ├── CatalogClientConfiguration.java
    │   │   ├── CatalogIntegration.java
    │   │   ├── CatalogApplicationService.java
    │   │   └── HttpControllers.java
    │   └── resources/application.properties
    └── test/java/com/example/clientboundary/
        ├── HttpCatalogGatewayTest.java
        └── CatalogApplicationServiceTest.java
```

Classes inside `CatalogIntegration.java` and `HttpControllers.java` are package-private; Java allows **multiple non-public top-level types in a single file**. All `public` classes match their filenames.

### 10.2. Complete `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>client-boundary-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

No WebFlux dependency is needed for synchronous `RestClient`. Boot's parent manages Spring, Jackson, and JUnit versions.

### 10.3. Main Class

`src/main/java/com/example/clientboundary/ClientBoundaryApplication.java`:

```java
package com.example.clientboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ClientBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientBoundaryApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` registers the properties record in Section 10.4. Component scanning detects controllers, services, gateways, and configs in the same package.

### 10.4. Configuration Record

`src/main/java/com/example/clientboundary/CatalogProperties.java`:

```java
package com.example.clientboundary;

import java.net.URI;

import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "integrations.catalog")
public record CatalogProperties(@NotNull URI baseUrl) {
}
```

This is **application configuration**, not a property whose domain meaning Boot understands on its own.

### 10.5. Creating the Per-Partner `RestClient` Bean

`src/main/java/com/example/clientboundary/CatalogClientConfiguration.java`:

```java
package com.example.clientboundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            RestClient.Builder builder,
            CatalogProperties properties) {
        return builder
                .baseUrl(properties.baseUrl().toString())
                .build();
    }
}
```

Boot's builder supplies infrastructure while the app supplies the URL. Do not place 404 mapping or pricing rules inside this bean factory.

### 10.6. Port, DTOs, Domain, and Adapter

`src/main/java/com/example/clientboundary/CatalogIntegration.java`:

```java
package com.example.clientboundary;

import java.util.Optional;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

record CatalogWireItem(long id, String name, long priceVnd,
                       boolean available) {
}

record CatalogItem(long id, String name, long priceVnd,
                   boolean available) {
}

interface CatalogGateway {
    Optional<CatalogItem> find(long itemId);
}

class CatalogDependencyException extends RuntimeException {
    CatalogDependencyException(String message) {
        super(message);
    }

    CatalogDependencyException(Throwable cause) {
        super("Catalog upstream failure", cause);
    }
}

class ItemNotFoundException extends RuntimeException {
    ItemNotFoundException(long id) {
        super("Item not found: " + id);
    }
}

class OutOfStockException extends RuntimeException {
    OutOfStockException(long id) {
        super("Item out of stock: " + id);
    }
}

@Component
class HttpCatalogGateway implements CatalogGateway {

    private final RestClient client;

    HttpCatalogGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    @Override
    public Optional<CatalogItem> find(long itemId) {
        try {
            CatalogWireItem dto = client.get()
                    .uri("/partner/items/{id}", itemId)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(CatalogWireItem.class);

            if (dto == null
                    || dto.id() != itemId
                    || dto.name() == null
                    || dto.name().isBlank()
                    || dto.priceVnd() < 0) {
                throw new CatalogDependencyException(
                        "Catalog returned invalid data");
            }

            return Optional.of(new CatalogItem(
                    dto.id(), dto.name(),
                    dto.priceVnd(), dto.available()));
        }
        catch (HttpClientErrorException.NotFound ex) {
            // Per Catalog contract: 404 => item does not exist.
            return Optional.empty();
        }
        catch (RestClientException ex) {
            // 5xx, other 4xx, I/O, timeouts, decode errors.
            throw new CatalogDependencyException(ex);
        }
    }
}
```

**Reading across the boundaries:**

1. `CatalogGateway` contains no `RestClient`, URLs, or Spring HTTP types.
2. `CatalogWireItem` belongs to the partner API; `CatalogItem` is the stable domain model.
3. The adapter specifies `GET /partner/items/{id}` and the JSON format.
4. 404 maps to `Optional.empty()` **solely because of this example's contract**.
5. Other HTTP client exceptions translate to `CatalogDependencyException`; the domain never catches Spring HTTP exceptions.
6. A 200 response with a null DTO, blank name, mismatched ID, or negative price is treated as a **contract failure** rather than issuing a wrong quote.

**Example limitation:** the DTO uses primitive `long/boolean`; JSON missing those fields deserializes to defaults (`0`/`false`), so real systems need stricter schema validation, nullable wrapper types, or Bean Validation when partners send inconsistent payloads.

### 10.7. Application Service Handling Business Logic Only

`src/main/java/com/example/clientboundary/CatalogApplicationService.java`:

```java
package com.example.clientboundary;

import org.springframework.stereotype.Service;

record Quote(long itemId, String name, int quantity,
             long unitPriceVnd, long totalVnd) {
}

@Service
public class CatalogApplicationService {

    private final CatalogGateway catalog;

    public CatalogApplicationService(CatalogGateway catalog) {
        this.catalog = catalog;
    }

    public Quote quote(long itemId, int quantity) {
        if (itemId <= 0) {
            throw new IllegalArgumentException(
                    "itemId must be positive");
        }
        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "quantity must be 1..100");
        }

        CatalogItem item = catalog.find(itemId)
                .orElseThrow(
                        () -> new ItemNotFoundException(itemId));

        if (!item.available()) {
            throw new OutOfStockException(itemId);
        }

        long total;
        try {
            total = Math.multiplyExact(
                    item.priceVnd(), (long) quantity);
        }
        catch (ArithmeticException ex) {
            throw new CatalogDependencyException(
                    "Catalog price exceeds safe range");
        }

        return new Quote(item.id(), item.name(), quantity,
                item.priceVnd(), total);
    }
}
```

Quantity validation, availability checks, and total calculation belong to the **use case**. There is no `GET`, `RestClient`, `HttpStatus`, or partner URL anywhere in this class. Whole-VND `long` amounts are for demo simplicity; production systems require dedicated currency, tax, rounding, minor-unit, and validation rules.

### 10.8. Public API, Error Mapping, and Partner Stub

`src/main/java/com/example/clientboundary/HttpControllers.java`:

```java
package com.example.clientboundary;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestController
class QuoteController {

    private final CatalogApplicationService service;

    QuoteController(CatalogApplicationService service) {
        this.service = service;
    }

    @GetMapping("/api/quotes/{id}")
    Quote quote(
            @PathVariable long id,
            @RequestParam(defaultValue = "1") int quantity) {
        return service.quote(id, quantity);
    }
}

// Partner stub for local demo only. Never deploy like this.
@RestController
class DemoPartnerController {

    @GetMapping("/partner/items/{id}")
    CatalogWireItem item(@PathVariable long id) {
        if (id == 1) {
            return new CatalogWireItem(
                    1, "Pen", 12_000L, true);
        }
        if (id == 2) {
            return new CatalogWireItem(
                    2, "Notebook", 35_000L, false);
        }
        if (id == 503) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE, "Demo outage");
        }
        throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "No such item");
    }
}

@RestControllerAdvice
class PublicErrorAdvice {

    @ExceptionHandler(ItemNotFoundException.class)
    ResponseEntity<Map<String, String>> notFound(
            ItemNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                Map.of("code", "ITEM_NOT_FOUND",
                       "message", "Item not found."));
    }

    @ExceptionHandler(OutOfStockException.class)
    ResponseEntity<Map<String, String>> outOfStock(
            OutOfStockException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                Map.of("code", "OUT_OF_STOCK",
                       "message", "Item is out of stock."));
    }

    @ExceptionHandler(CatalogDependencyException.class)
    ResponseEntity<Map<String, String>> dependency(
            CatalogDependencyException ex) {
        return ResponseEntity.status(
                HttpStatus.SERVICE_UNAVAILABLE).body(
                Map.of("code", "CATALOG_UNAVAILABLE",
                       "message", "Catalog is temporarily unavailable."));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalidInput(
            IllegalArgumentException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(
                Map.of("code", "INVALID_QUOTE_REQUEST",
                       "message", "Invalid quote request parameters."));
    }
}
```

All top-level classes in `HttpControllers.java` are package-private, so Java permits them in one file. `QuoteController` invokes the use case; `PublicErrorAdvice` selects public statuses and messages. The partner stub exists solely so the example runs offline.

### 10.9. Complete `application.properties`

```properties
server.port=8080
spring.application.name=client-boundary-demo

spring.http.client.connect-timeout=2s
spring.http.client.read-timeout=3s
spring.http.client.redirects=dont-follow

integrations.catalog.base-url=${CATALOG_BASE_URL:http://localhost:8080}
```

Boot's HTTP client defaults live under `spring.http.client.*`. `integrations.catalog.base-url` is custom app config; the record in Section 10.4 is what binds it.

### 10.10. Build and Run

Requires JDK 17+, Maven, and port 8080 available.

```bash
mvn clean package
java -jar target/client-boundary-demo-1.0.0.jar
```

From another terminal:

```bash
curl -s "http://localhost:8080/api/quotes/1?quantity=3"
```

Expected JSON:

```json
{"itemId":1,"name":"Pen","quantity":3,"unitPriceVnd":12000,"totalVnd":36000}
```

Key order may differ; the values reflect the partner stub returning unit price 12,000 and quantity=3, totaling 36,000.

Test out-of-stock:

```bash
curl -i "http://localhost:8080/api/quotes/2?quantity=1"
```

Expect **HTTP 409 Conflict**, JSON with `code=OUT_OF_STOCK`.

Test missing item:

```bash
curl -i "http://localhost:8080/api/quotes/9?quantity=1"
```

Expect **HTTP 404 Not Found**, JSON with `code=ITEM_NOT_FOUND`. Upstream 404 → adapter empty → use case `ItemNotFoundException` → API 404; each layer handles its exact responsibility.

Test partner outage:

```bash
curl -i "http://localhost:8080/api/quotes/503?quantity=1"
```

Expect **HTTP 503 Service Unavailable**, JSON with `code=CATALOG_UNAVAILABLE`. Upstream 503 never leaks its raw body to the frontend.

Test invalid input:

```bash
curl -i "http://localhost:8080/api/quotes/1?quantity=0"
```

Expect **HTTP 400 Bad Request**, JSON with `code=INVALID_QUOTE_REQUEST`. Invalid quantity is rejected before any outbound call happens.

Inspect the upstream wire DTO directly:

```bash
curl -s http://localhost:8080/partner/items/1
```

JSON payload:

```json
{"id":1,"name":"Pen","priceVnd":12000,"available":true}
```

Compared with `Quote`, the public API does not expose the partner's `priceVnd` field verbatim; the app's own contract uses `unitPriceVnd` and `totalVnd`.

**Deployment note:** the loopback self-call setup is strictly for the demo. Across multiple nodes or small servlet thread pools, self-calling the same process can exhaust threads. In production, call external services over DNS/HTTPS with proper connection pooling.

## 11. Testing the Adapter with Mock HTTP and Domain Logic with a Fake Port

### 11.1. Adapter Test: No Real Network

File `src/test/java/com/example/clientboundary/HttpCatalogGatewayTest.java`:

```java
package com.example.clientboundary;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class HttpCatalogGatewayTest {

    private static final String BASE =
            "http://catalog.example.test";

    @Test
    void mapsDtoToDomain() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl(BASE);
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        server.expect(requestTo(BASE + "/partner/items/1"))
                .andRespond(withSuccess(
                        "{\"id\":1,\"name\":\"Pen\","
                        + "\"priceVnd\":12000,\"available\":true}",
                        MediaType.APPLICATION_JSON));

        HttpCatalogGateway gateway =
                new HttpCatalogGateway(builder.build());

        assertEquals(Optional.of(
                new CatalogItem(1, "Pen", 12000, true)),
                gateway.find(1));
        server.verify();
    }

    @Test
    void maps404ToMissing() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl(BASE);
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        server.expect(requestTo(BASE + "/partner/items/9"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        HttpCatalogGateway gateway =
                new HttpCatalogGateway(builder.build());

        assertTrue(gateway.find(9).isEmpty());
        server.verify();
    }

    @Test
    void maps503ToDependencyFailure() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl(BASE);
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        server.expect(requestTo(BASE + "/partner/items/503"))
                .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

        HttpCatalogGateway gateway =
                new HttpCatalogGateway(builder.build());

        assertThrows(CatalogDependencyException.class,
                () -> gateway.find(503));
        server.verify();
    }

    @Test
    void rejectsInvalidPayload() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl(BASE);
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        server.expect(requestTo(BASE + "/partner/items/1"))
                .andRespond(withSuccess(
                        "{\"id\":2,\"name\":\"wrong-id\","
                        + "\"priceVnd\":12000,\"available\":true}",
                        MediaType.APPLICATION_JSON));

        HttpCatalogGateway gateway =
                new HttpCatalogGateway(builder.build());

        assertThrows(CatalogDependencyException.class,
                () -> gateway.find(1));
        server.verify();
    }
}
```

`MockRestServiceServer.bindTo(RestClient.Builder)` attaches a mock request factory to that builder so expected requests make no real network calls. These tests verify **the partner HTTP contract and adapter mapping**, not Boot auto-config, TLS, or connection pooling. To test Boot wiring, write a separate integration test.

### 11.2. Business Test: No HTTP Library Needed

File `src/test/java/com/example/clientboundary/CatalogApplicationServiceTest.java`:

```java
package com.example.clientboundary;

import java.util.Optional;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CatalogApplicationServiceTest {

    private final CatalogGateway fake = id -> {
        if (id == 1) {
            return Optional.of(
                    new CatalogItem(1, "Pen", 12000, true));
        }
        if (id == 2) {
            return Optional.of(
                    new CatalogItem(2, "Notebook", 35000, false));
        }
        return Optional.empty();
    };

    private final CatalogApplicationService service =
            new CatalogApplicationService(fake);

    @Test
    void calculatesQuote() {
        assertEquals(
                new Quote(1, "Pen", 3, 12000, 36000),
                service.quote(1, 3));
    }

    @Test
    void rejectsUnavailableItem() {
        assertThrows(OutOfStockException.class,
                () -> service.quote(2, 1));
    }

    @Test
    void rejectsMissingItem() {
        assertThrows(ItemNotFoundException.class,
                () -> service.quote(9, 1));
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> service.quote(1, 0));
    }
}
```

Even if the adapter switches from `RestClient` to `WebClient`, gRPC, or an SDK, these business tests need no edits as long as port semantics stay intact.

Run:

```bash
mvn test
```

Tests run under JUnit Jupiter from `spring-boot-starter-test` without starting a web server. When testing controller + Boot wiring on a random port, dynamically override the base URL or start a separate mock upstream server; **random port does not automatically update the custom `integrations.catalog.base-url` property**.

### 11.3. Recommended Test Matrix

| Layer | What to verify | Suggested tool |
| --- | --- | --- |
| Domain/application | quantity, stock, total, overflow | JUnit with fake `CatalogGateway` |
| Adapter | URI, headers, 200/404/429/503, invalid JSON | `MockRestServiceServer`/WireMock |
| Bean/config | Properties binding, TLS/SSL bundles, timeouts | `ApplicationContextRunner` or `@SpringBootTest` |
| Network/integration | DNS, proxy, certificates, source IP, retries | Staging partner / test container |
| Contract | Schema, version, enum values, dates/currencies | Consumer/provider contract tests |
| Security | Host allowlist, token audience, secret redaction | Static/security/egress tests |
| Resilience | Circuit breaker, backoff, timeouts, load | Fault injection |
| Performance | Pool saturation, p95, retry storms | Controlled load tests |

## 12. Scaling to Multiple Partners

### 12.1. One Clearly Named Bean Per Upstream

```java
@Bean("catalogRestClient")
RestClient catalog(RestClient.Builder builder) {
    return builder.baseUrl("https://catalog.example.internal")
            .build();
}

@Bean("shippingRestClient")
RestClient shipping(RestClient.Builder builder) {
    return builder.baseUrl("https://shipping.example.internal")
            .build();
}
```

This is an **alternative snippet**—do not add it alongside the demo project's `catalogRestClient` bean at the same time. Use `@Qualifier` or typed client wrappers when injecting; multiple `RestClient` beans without qualifiers cause DI ambiguity.

### 12.2. Global Customizers Only for Truly Shared Settings

```java
@Bean
RestClientCustomizer technicalCustomizer() {
    return builder -> builder
            .defaultHeader("X-App-Client", "my-spring-app");
}
```

Snippet requires importing `org.springframework.boot.web.client.RestClientCustomizer`; this header is only an example if partners accept it. Never turn a global customizer into a place for Catalog API keys, URLs, or payment retry rules. Boot customizers have broad reach—one change affects every upstream client of that type.

### 12.3. `@HttpExchange` Is an HTTP Interface, Not Automatically a Business Port

```java
@HttpExchange("/partner/items")
interface CatalogHttpApi {
    @GetExchange("/{id}")
    CatalogWireItem get(@PathVariable long id);
}
```

This is a **snippet** requiring a `RestClientAdapter`/`WebClientAdapter` and `HttpServiceProxyFactory`, not standalone runnable code. This interface still speaks the partner's HTTP language, whereas `CatalogGateway` speaks the application's language. Even with generated proxies, you still need DTO mappers, contract checks, business error mapping, and tests.

### 12.4. When a Partner Changes API Versions

If `/partner/items/{id}` moves to `/v2/products/{id}` with altered JSON fields, update the adapter and HTTP tests—**never edit the business service just to change a URL**. If the partner changes pricing or stock semantics too, then updating the domain is a legitimate business change, not an architectural failure.

## 13. WebFlux: Keep the Boundaries, Change the Execution Model

A reactive application can define a port:

```java
interface ReactiveCatalogGateway {
    Mono<CatalogItem> find(long itemId);
}
```

In this design, define clearly whether **`Mono.empty()` means not found vs. missing data**, and `Mono.error(...)` means dependency failure. Never define a synchronous port that randomly throws reactive errors or calls `block()` on the event loop.

Illustrative `WebClient` adapter **snippet**:

```java
Mono<CatalogItem> find(long id) {
    return webClient.get()
            .uri("/partner/items/{id}", id)
            .retrieve()
            .bodyToMono(CatalogWireItem.class)
            .map(dto -> new CatalogItem(
                    dto.id(), dto.name(),
                    dto.priceVnd(), dto.available()))
            .onErrorMap(WebClientRequestException.class,
                    CatalogDependencyException::new);
}
```

This is not yet a complete adapter: it still needs `404` mapping per agreed contract, DTO validation, 5xx handling, and decode-error mapping. It clearly shows that **`WebClient` does not automatically become a business adapter** merely by returning `Mono`.

In WebFlux:

- Never call blocking `RestTemplate`/`RestClient` directly on the event loop.
- Never call `WebClient.block()` on a reactive request thread.
- Never manually `subscribe()` inside a service and return before processing finishes.
- If a blocking library is unavoidable, isolate it with bounded `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.
- Explicitly design cancellation, context propagation, connection pooling, and backpressure.

An MVC service can still use `WebClient` outbound, yet that does not magically make JPA/JDBC business code non-blocking.

## 14. Checklist for Spotting Broken Boundaries and Fixing Them

| Signal | Issue | Fix |
| --- | --- | --- |
| Controller injects `RestClient` and computes pricing in one method | Mixes HTTP adapter with domain logic | Extract `CatalogGateway` + use case |
| `NoSuchBeanDefinitionException: RestTemplate` | Assumed Boot auto-creates a `RestTemplate` bean | Build a bean via `RestTemplateBuilder` |
| HTTP client metrics vanish after refactor | Constructed `RestClient.create()` outside Boot customizations | Inject Boot-managed builder |
| Catalog client sends Shipping's bearer token | Auth header placed in global customizer | Move token to per-partner bean/request |
| Every 404 maps to empty | Contract misunderstood | Map explicitly per adapter |
| Upstream 503 treated as item not found | Swallowed dependency failure | Raise dedicated `CatalogDependencyException` |
| 200 response with DTO missing price | Unvalidated schema | Add contract validation and tests |
| 429 retries indefinitely | Unbounded retry policy | Bounded backoff, `Retry-After`, circuit breaker |
| Payment POST retry creates duplicates | HTTP policy ignores idempotency | Idempotency keys and business policy |
| Partner A bean uses Partner B base URL | Shared mutable builder mutated across beans | Separate injections or `clone()`, use qualifiers |
| WebFlux requests stall | Blocking HTTP/DB on event loop | Use `WebClient` or bounded `boundedElastic` |
| Global timeout bumped to 30s for one partner | Confused global defaults with per-partner SLA | Override per service |
| Domain tests require real network | Domain depends directly on HTTP client | Use fake port; test adapter separately |
| Public API returns raw partner errors | Information/contract leak | Map to domain exceptions + controller advice |
| Upstream 403 returned as 403 to end user | Confused service credentials with user rights | Separate upstream auth from public semantics |
| Logs contain bearer tokens | Logging interceptor lacks redaction | Strip/mask sensitive headers |
| Production config has localhost base URL | Bad environment override | Require real URL/allowlist; fail fast on startup |
| Outbound call hits `169.254...` from user input | SSRF | Allowlist, egress rules, redirect/DNS checks |
| Connection pool exhausted | Unbounded concurrency or unclosed responses | Reuse clients, pool metrics, bulkhead |
| Stale prices used during checkout | Technical fallback contradicts business rules | Enforce freshness rules in use case |

## 15. Layer-by-Layer Incident Investigation Workflow

Suppose `GET /api/quotes/1` returns 503:

1. **Controller:** what public status/code returned? Were path and method valid?
2. **Application:** was input validated? Was `CatalogGateway` invoked?
3. **Adapter:** was the right URI sent to the partner? How were 404/503/JSON mapped?
4. **Client bean:** did `catalogRestClient` receive the right base URL and Boot builder? Are any unexpected global headers present?
5. **Transport:** are DNS, TLS, proxy, connection pool, and connect/read timeouts healthy?
6. **Partner contract:** did response schema, statuses, API version, or rate limits change?
7. **Gateway/mesh:** did infrastructure add retries, timeouts, or redirect rewrites?
8. **Observability:** are trace IDs complete across hops? Were any secrets accidentally logged?
9. **Tests:** add an adapter regression test for the failure; if business policy was affected, add a domain unit test.
10. **Deployment:** inspect real environment config, profiles, and secrets—never treat a laptop `curl` as proof that pods have connectivity.

Avoid "fixing" issues by disabling TLS verification, raising global timeouts indefinitely, or mapping every failure to HTTP 200; those hide bugs and trigger larger outages.

## 16. Exercises and Self-Assessment Questions

1. **Does Boot automatically create a dedicated `RestClient` for Catalog?** No. Boot prepares the builder; your app builds per-partner clients.
2. **Does Boot provide an injectable `RestTemplate` bean out of the box?** Normally no; it provides `RestTemplateBuilder`.
3. **Is Catalog's 404 always a routing bug?** No. In the demo contract, it means the item does not exist, and the adapter translates it accordingly.
4. **Why should the domain not see the partner's `ResponseEntity`?** It couples the business model to HTTP transport and external schemas.
5. **When a partner returns 503, should you fall back to `price=0`?** No, unless the business explicitly permits stale/default pricing; otherwise transactions break.
6. **Can you put Catalog's API key inside a global customizer?** No, because it can leak to other HTTP clients.
7. **Is a 3-second global timeout sufficient for every upstream?** Not necessarily. Evaluate per-service SLAs/deadlines and measure.
8. **Is retrying a payment POST on timeout safe?** Only with an explicit idempotency contract and proper retry policy.
9. **Does `@ConfigurationProperties` send HTTP requests on its own?** No, it only binds configuration.
10. **Why use a fake `CatalogGateway` in domain unit tests?** No Spring context, HTTP library, or server is required.
11. **Does `WebClient` turn the whole MVC app reactive?** No.
12. **When a partner changes its JSON API, which layer do you edit first?** Wire DTOs + integration adapter + contract tests.
13. **Does an `@HttpExchange` interface replace a business gateway?** No; it describes the HTTP contract.
14. **Why reuse client beans?** To preserve connection pooling, TLS, customizers, and observability while cutting overhead.
15. **Is a backend calling a partner blocked by browser CORS policy?** No; it is a server-to-server call.

### Applied Exercises

**A. Partner renames `priceVnd` to `amount`:** update the wire DTO/mapper, add a contract test, and leave `CatalogApplicationService.quote` unchanged if price semantics stay the same.

**B. Add Shipping:** create `ShippingProperties`, `shippingRestClient`, and `HttpShippingGateway` with its own auth and deadlines—never reuse Catalog's token.

**C. Partner returns 429:** map to a clear rate-limit error, honor `Retry-After`/budgets, and avoid blindly retrying every request.

**D. Add mTLS:** apply an SSL bundle to **catalogRestClient** via `RestClientSsl` without altering TLS for other clients.

**E. Migrate to reactive:** keep domain rules intact, define a reactive port, map errors/empty clearly, and never call blocking HTTP on the event loop.

**F. Catalog returns 200 with a different ID than requested:** adapter fails contract validation and never computes a quote from the wrong item.

## 17. Design and Operations Checklist

- [ ] Identify application type: synchronous MVC or reactive WebFlux.
- [ ] Use Boot-configured builders to retain converters, transports, and observability.
- [ ] Give each upstream typed config, its own base URL, and a dedicated client bean.
- [ ] Keep partner secrets, URLs, and business error mappings out of global customizers.
- [ ] Separate wire DTOs from domain/public DTOs and validate upstream contracts.
- [ ] Have the application call a gateway port without importing HTTP client exceptions.
- [ ] Have controllers handle only the public HTTP contract and domain outcomes.
- [ ] Enforce per-service SLAs, connect/read/total timeouts, pooling, and concurrency limits.
- [ ] Configure retries with idempotency, max attempts, backoff, budgets, and metrics.
- [ ] Enable fallbacks/circuit breakers only when business rules allow them.
- [ ] Enforce proper CA/hostname TLS validation; keep API keys/tokens in secret managers.
- [ ] Never let user input dictate arbitrary outbound URLs (SSRF).
- [ ] Write domain unit tests, adapter contract tests, and integration wiring/SSL tests.
- [ ] Observe status/latency/pool/retry metrics and separate upstream failures from domain outcomes.
- [ ] When changing major Boot versions, verify property names and builder/customizer semantics.
- [ ] Ensure every team knows who owns transport defaults, partner contracts, and business rules.

## 18. Official References

- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): Boot builders, HTTP factories, customizers, `WebClient`, and `RestTemplate`.
- [Spring Boot 3.5 — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.http.client.*` and `spring.http.reactiveclient.*`.
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): `RestClient`, HTTP interfaces, status semantics.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): Publisher, status handling, non-blocking operations.
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): `@ConfigurationProperties` and binding.
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): Micrometer/Tracing.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): test infrastructure.
- [Spring Framework — MockRestServiceServer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): mock HTTP contract tests.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): service credentials.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): methods/statuses/headers.

**Takeaway:** **Boot knows how to connect over HTTP safely and consistently; the adapter understands the external service; application/domain logic understands what the result means; and the controller owns the public API.** Keeping these responsibilities separate lets you swap transports, upgrade Boot, adapt to partner contract changes, and test business rules without sacrificing correctness.