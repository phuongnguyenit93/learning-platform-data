# Packaging Shared Filters and Managing Version Compatibility in Spring Cloud Gateway

In a microservices system, multiple Gateways or multiple routes often share requirements such as attaching correlation IDs, normalizing internal headers, recording metrics, checking size limits, and enriching metadata when forwarding requests. Rewriting that logic on every route or copying Java source files across repositories creates **hard-to-control drift**, especially when Spring Boot or Spring Cloud is upgraded.

With **SPRING_CLOUD_GATEWAY**, the sustainable approach is **packaging custom filters with clear contracts, publishing them as a shared library/starter, and testing compatibility against each release train**. This lesson belongs to the **Custom Filters** chapter and focuses on the question: *How can multiple Gateways reuse the same filter while keeping per-route configurability, reactive execution safety, collision-free factory names, and controlled version upgrades?*

The overarching context is a Gateway serving route predicates, filter chains, path/header transformations, service discovery/load balancing, authentication, rate limiting, circuit breakers, retries, TLS, and request observability. Custom filters must integrate with those layers rather than **assuming they can replace standard mechanisms**.

> **Scope:** Java examples target **Spring Cloud Gateway Server WebFlux**, typically deployed with Spring Boot 3.x / reactive Spring Security and a compatible Spring Cloud release train. Newer Gateway generations may change starters, artifacts, namespaces, APIs, and auto-configuration conditions. **Gateway Server MVC uses a different model**; never drop WebFlux filters onto an MVC classpath expecting them to work. Shared libraries must explicitly declare which versions have **actually been tested**, rather than guessing a version range.

## 1. Distinguishing Extension Points Before Creating a Library

In Spring Cloud Gateway Server WebFlux, common filter types do not share the same scope.

| Component | When does it run? | How is it configured/shared? | Caveat |
|---|---|---|---|
| `GatewayFilterFactory` | Factory creates a `GatewayFilter` bound to a matched route | YAML/Java route DSL, or `default-filters` | Ideal for filters with per-route `args` |
| `GlobalFilter` | Joins the filter chain of matched Gateway routes | Bean in the application | Not equivalent to a `WebFilter` covering unmatched requests |
| `WebFilter` | Inside Spring WebFlux's web-layer filter chain | Bean/WebFlux registration | Can run before route selection; different ordering and scope |
| `SecurityWebFilterChain` | Reactive authentication/authorization per security matcher | Spring Security `ServerHttpSecurity` | Never replace with manual header checks in a `GatewayFilter` |
| Built-in filter | Scenarios supported out of the box by Gateway | `RewritePath`, `SetRequestHeader`, `RequestRateLimiter`, etc. | Prefer built-ins whenever sufficient |

**Rule:** If each route needs its own parameter such as `prefix` or per-route enablement, start with **`GatewayFilterFactory`**. If a policy applies uniformly across all Gateway routes, consider **`GlobalFilter`**. If requests must be intercepted even before route matching (such as authentication, CORS, or edge rules), evaluate **`WebFilter`, Spring Security, or the ingress layer** accordingly.

### What Happens in the Pipeline?

~~~mermaid
flowchart TD
    C["Client HTTP request"] --> W["WebFlux WebFilters / Spring Security"]
    W --> M{"Do route predicates match?"}
    M -->|No| N["Other handler / 404 per config"]
    M -->|Yes| F["FilteringWebHandler"]
    F --> O["Sort GlobalFilter and GatewayFilter by order"]
    O --> X["Custom EdgeRequestId GatewayFilter"]
    X --> R["Built-in filters: path/header/Retry/RateLimiter..."]
    R --> B["Netty routing / LoadBalancer lb://"]
    B --> S["Backend microservice"]
    S --> P["Response unwinds through filter chain"]
~~~

**Never treat the order in this diagram as a rigid guarantee across every version.** `GlobalFilter`s and route-specific `GatewayFilter`s are merged and sorted by `Ordered`. Many filters also run logic before and after `chain.filter(exchange)`. Key points to observe are **when headers are added**, **when paths are rewritten**, **when requests go downstream**, and **when responses commit**.

## 2. Picking a Small, Stable Contract for Reuse

Let's build **`EdgeRequestIdGatewayFilterFactory`** as an example:

- Accepts per-route `prefix` configuration, e.g., `edge-` or `orders-`.
- Generates a fresh ID per request and **overwrites** `X-Edge-Request-Id` before forwarding downstream.
- Never trusts a correlation ID supplied by the client. This is a diagnostic ID, **not an authentication token**.
- Preserves method, path, query, and body without reading the request body.
- Uses no blocking I/O and stores no per-request state in shared Bean fields.
- Exposes a stable public factory name: `EdgeRequestId`.
- Validates configuration **when the factory builds the filter**, rather than discovering a bad prefix on every request.

### Functional Contract

| Input | Outcome | What must never happen |
|---|---|---|
| Request has `X-Edge-Request-Id: forged` | Downstream header is replaced with Gateway-generated ID | Never trust client header as a verified ID |
| Request has no header | Adds new header | Never alters body/query |
| Two concurrent requests | Two independent IDs generated | Never use an unsynchronized static mutable counter |
| Prefix `orders-` | Value shaped like `orders-<UUID>` | Never let an invalid prefix break HTTP syntax |
| Blank/oversized/disallowed-char prefix | Rejects configuration | Never silently inject CR/LF or arbitrary text into headers |
| Unmatched route | That route's factory does not run | Never stamp unrelated handlers by mistake |

This example is small enough to illustrate **library API design**, yet the same principles apply to header policies, metrics, auditing, metadata routing, or custom resilience filters. Only build custom filters when built-in factories fall short; every custom API adds long-term compatibility and maintenance duties.

## 3. Implementing a Standalone `GatewayFilterFactory`

Place the class in the library module **without `@Component`**, because in the starter packaging section we will register the Bean via auto-configuration. If writing directly inside a single Gateway app, use either `@Bean` or consistent component scanning—**never register the same factory both ways**.

~~~java
package com.acme.edge.filters;

import java.util.List;
import java.util.UUID;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.http.server.reactive.ServerHttpRequest;

public final class EdgeRequestIdGatewayFilterFactory
        extends AbstractGatewayFilterFactory<
                EdgeRequestIdGatewayFilterFactory.Config> {

    public static final String HEADER_NAME = "X-Edge-Request-Id";

    public EdgeRequestIdGatewayFilterFactory() {
        super(Config.class);
    }

    @Override
    public GatewayFilter apply(Config config) {
        String prefix = config.getPrefix();

        // Runs when route config builds the filter, preventing unsafe inputs.
        if (prefix == null || !prefix.matches("[A-Za-z0-9_-]{1,24}")) {
            throw new IllegalArgumentException(
                "EdgeRequestId.prefix must be 1..24 safe characters");
        }

        // Capture immutable config for the filter applied to this route.
        return (exchange, chain) -> {
            String value = prefix + UUID.randomUUID();

            ServerHttpRequest request = exchange.getRequest()
                .mutate()
                .headers(headers -> headers.set(HEADER_NAME, value))
                .build();

            return chain.filter(
                exchange.mutate().request(request).build());
        };
    }

    @Override
    public List<String> shortcutFieldOrder() {
        return List.of("prefix");
    }

    public static final class Config {
        private String prefix = "edge-";

        public String getPrefix() {
            return prefix;
        }

        public void setPrefix(String prefix) {
            this.prefix = prefix;
        }
    }
}
~~~

### Analyzing Each Choice

1. **`AbstractGatewayFilterFactory<Config>`** gives Gateway the foundation to bind route configuration into `Config`.
2. Ending the class name with **`GatewayFilterFactory`** yields the short config name **`EdgeRequestId`** by Gateway convention. Never use an incorrect suffix or assume a Java Bean name becomes the YAML factory name.
3. **`Config` is a static nested class with a no-arg constructor and getters/setters** for standard factory binding. Each route can configure its own `prefix`.
4. Validate `prefix` when `apply` runs. The allowlist permits only ASCII letters, digits, hyphens, and underscores, blocking CR/LF and arbitrary characters.
5. `headers.set(...)` **replaces all values for that header name** on the new request, unlike `add(...)` which can retain client-sent values.
6. `exchange.getRequest().mutate()` and `exchange.mutate()` create wrappers around the modified request rather than mutating an immutable request object directly.
7. `chain.filter(...)` is always called **exactly once** on the success path. The filter never stops requests or writes responses itself.
8. Never call `block()`, manually subscribe, or store per-request state in Bean fields.
9. `UUID` here is a diagnostic identifier—**never use it as a password, access token, authorization proof, or business idempotency key**.
10. `shortcutFieldOrder()` lets the binder map `EdgeRequestId=orders-` to `Config.prefix`.

**Java version note:** This code uses `List.of` (Java 9+) and `UUID.randomUUID()`. Spring Boot 3 lines typically require Java 17+. For other platform baselines, target a compatible Java version per your compatibility matrix and CI rather than compiling with a newer JDK for older runtimes.

## 4. Using the Filter Per Route and Sharing via `default-filters`

### Expanded Configuration

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - name: EdgeRequestId
              args:
                prefix: orders-
            - StripPrefix=1
~~~

`EdgeRequestId` is the factory **registered as a Bean** inside Gateway. If the starter is missing or auto-configuration did not run, Gateway will fail to locate the matching `GatewayFilterFactory`.

### Shortcut Configuration

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-api
          uri: lb://catalog-service
          predicates:
            - Path=/api/catalog/**
          filters:
            - EdgeRequestId=catalog-
~~~

This form uses `shortcutFieldOrder()` to map the value after `=` into `prefix`. For filters with multiple complex fields, prefer **expanded form** for easier review, type safety, and spotting missing fields.

### Applying a Shared Policy Across Multiple Routes

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - EdgeRequestId=edge-
      routes:
        - id: orders
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
        - id: catalog
          uri: lb://catalog-service
          predicates:
            - Path=/api/catalog/**
~~~

`default-filters` works well if every **Gateway route** needs that header. However:

- **Never** assume the filter runs on requests matching no Gateway route.
- Do not also declare `EdgeRequestId` on individual routes unless you want it to run twice and regenerate IDs.
- For routes from `DiscoveryClient` locators, verify the effective filter list and version behavior to confirm default filters apply as intended.
- When policies vary per tenant/route, prefer explicit per-route config over a single global prefix.
- If an ID must be generated before security or route matching, a `GatewayFilterFactory` cannot satisfy that goal; design an outer filter layer explicitly.

### This Filter Does Not Send the ID Back to the Client Automatically

The example only sets a **Gateway → downstream request header**. Clients will **not automatically see** `X-Edge-Request-Id` in the response. To return a correlation ID to clients, add a response header hook **before response commit**, consider CORS `exposedHeaders`, and guard against metadata leaks. Never confuse `request.getHeaders()` with `response.getHeaders()`.

## 5. Why Not Use One `GlobalFilter` for Everything?

A `GlobalFilter` is convenient to package when behavior applies identically across all Gateway routes:

~~~java
package com.acme.edge.filters;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class RequestMarkerGlobalFilter
        implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain) {
        // Illustrative stub: implement trustworthy policy/tracing here.
        return chain.filter(exchange);
    }
}
~~~

This snippet illustrates only the **API signature and order**, without business logic. `getOrder() = -100` is an example value, **not a position guaranteed safe relative to every built-in filter**.

| Requirement | Prefer |
|---|---|
| Different prefix per route | `GatewayFilterFactory` |
| Toggleable per route via YAML | `GatewayFilterFactory` |
| Uniform policy across all Gateway routes | `GlobalFilter` or `default-filters` depending on config |
| Handle public web paths programmatically at the web tier | `WebFilter` or matching security/web routing |
| Verify Bearer JWTs, enforce scopes | **Spring Security WebFlux**, not a custom header filter |
| Per-user/tenant rate limiting | Built-in `RequestRateLimiter` + `KeyResolver` before writing a custom limiter |
| Retry / CircuitBreaker | Built-in factories from your release train before inventing custom behavior |

**Never register both a `GlobalFilter` and a route filter doing the exact same work** unless deduplication is designed. For observability, doing so emits duplicate metrics, headers, or spans for a single request.

## 6. Designing Shared Library and Starter Structure

A common pattern is separating **filter logic** from **Bean registration / auto-configuration**.

~~~text
edge-gateway-filters/
  edge-filters-core/
    src/main/java/com/acme/edge/filters/
      EdgeRequestIdGatewayFilterFactory.java
  edge-filters-autoconfigure/
    src/main/java/com/acme/edge/autoconfigure/
      EdgeFiltersAutoConfiguration.java
    src/main/resources/META-INF/spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports
  edge-filters-starter/
    dependency: edge-filters-core + edge-filters-autoconfigure
  edge-filters-test/
    contract and compatibility tests against Gateway runtimes
~~~

This is a **recommended layout**, not a rule forcing four modules on day one. For a tiny filter, a library with core + auto-config may suffice. As the library grows, separating APIs from auto-registration helps:

- Avoid forcing every Gateway to pull unused dependencies.
- Let applications register Beans manually if they opt out of the starter.
- Manage optional integrations such as metrics, Redis, or Spring Security.
- Ship a single implementation and test suite across multiple Gateway apps.
- Clearly separate **public API packages** from internal helpers that may change.

### Dependency Rules

If a custom filter uses only `AbstractGatewayFilterFactory`, `GatewayFilter`, and WebFlux HTTP APIs, do not drag OAuth2, Redis, or database starters into every consumer.

In the library modules:

- Declare dependencies to **compile against Gateway/WebFlux APIs** from the target release train; choose `api`/`implementation`/`compileOnly` based on your Gradle model and runtime ownership.
- In the starter, declare required dependencies intentionally; never "shade" or repackage Spring Framework/Spring Cloud classes into your JAR.
- Never hard-pin a Spring Cloud version that conflicts with the **consuming app's BOM**.
- Keep JUnit, Reactor Test, and test helpers strictly in **test scope**.
- If using Spring Boot auto-configuration, depend on the matching `spring-boot-autoconfigure` rather than copying `AutoConfiguration` APIs from another Boot generation.

**A shared library is a versioned product**, not a copy-paste Java package. It requires versioning, changelogs, contracts, upgrade guides, and an explicit support matrix.

## 7. Auto-Configuration in a Spring Boot Starter

For **Spring Boot 3.x**, a library can provide an auto-configuration class so consumers only add the dependency without manually defining Beans.

~~~java
package com.acme.edge.autoconfigure;

import com.acme.edge.filters.EdgeRequestIdGatewayFilterFactory;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;

@AutoConfiguration
@ConditionalOnClass(AbstractGatewayFilterFactory.class)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.REACTIVE)
@ConditionalOnProperty(
    prefix = "acme.gateway.edge-request-id",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
public class EdgeFiltersAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(EdgeRequestIdGatewayFilterFactory.class)
    EdgeRequestIdGatewayFilterFactory edgeRequestIdGatewayFilterFactory() {
        return new EdgeRequestIdGatewayFilterFactory();
    }
}
~~~

**Meaning of the conditions:**

- `@AutoConfiguration`: Spring Boot discovers the configuration when packaged properly in the starter.
- `@ConditionalOnClass`: creates the Bean only when required Gateway APIs are on the classpath.
- `@ConditionalOnWebApplication(Type.REACTIVE)`: never wires WebFlux filters into a Servlet/MVC web stack.
- `@ConditionalOnProperty`: lets an app opt out of registering the factory if desired.
- `@ConditionalOnMissingBean`: lets an app supply its own factory Bean override when customizing behavior.

### The `AutoConfiguration.imports` Registration File

For Spring Boot 3.x auto-configuration, the auto-config JAR must include this exact path:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

That plain-text file lists **fully qualified class names**, one per line:

~~~text
com.acme.edge.autoconfigure.EdgeFiltersAutoConfiguration
~~~

This file must be **packaged inside the JAR**, not configured in `application.yml`. Having the Java class without `AutoConfiguration.imports` means consuming apps **may fail to register the Bean automatically**.

**Compatibility note:** Earlier Spring Boot generations used `META-INF/spring.factories` with `EnableAutoConfiguration`. Never assume a Boot 3 starter works on Boot 2 or vice versa. Pick the mechanism and API for the version lines you **actually build and test**, instead of shipping both styles together to mask version issues.

### Avoiding Double Registration

If `EdgeRequestIdGatewayFilterFactory` carries `@Component` while auto-configuration also defines `@Bean`, consuming apps can accidentally register the factory twice. Consequences:

- Bean name or factory name conflicts can occur.
- `EdgeRequestId` resolution can behave unexpectedly.
- Configuration might pass in one app and fail in another depending on component-scan packages.

**Establish clear Bean ownership:** keep `@Component` off the core class, register it via starter auto-config, and let apps override via `@Bean` ahead of `@ConditionalOnMissingBean` under a tested contract.

## 8. What Does a Consuming App Need?

Once the artifact is published to an internal repository, a Gateway application can depend on the starter.

**Conceptual dependency snippet** for a Gradle app whose project build already configures Spring Boot/Spring Cloud BOMs:

~~~groovy
dependencies {
    // Pick the exact Gateway Server WebFlux starter name for your release train.
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'

    // Your library's version, tested against this Boot/Cloud BOM.
    implementation 'com.acme.platform:edge-filters-starter:1.4.0'
}
~~~

Coordinates `com.acme.platform` and version `1.4.0` are **illustrative placeholders**, not published artifacts. Gateway starter names vary across Spring Cloud Gateway lines; older docs often refer to `spring-cloud-starter-gateway`. Choose the right runtime dependency via your BOM and official docs.

Application configuration:

~~~yaml
acme:
  gateway:
    edge-request-id:
      enabled: true

spring:
  cloud:
    gateway:
      routes:
        - id: profile-api
          uri: lb://profile-service
          predicates:
            - Path=/api/profile/**
          filters:
            - EdgeRequestId=profile-
~~~

When Gateway boots:

1. The starter is loaded from the classpath.
2. Boot discovers auto-configuration from the JAR.
3. Conditions pass, registering `EdgeRequestIdGatewayFilterFactory`.
4. Gateway binds `EdgeRequestId=profile-` to `Config.prefix` and builds the `GatewayFilter`.
5. Matching requests get a new ID and forward the updated header.

If `enabled: false` is set, the Bean is omitted, meaning **routes still referencing `EdgeRequestId` will fail to bind that filter**. Disabling the factory must therefore accompany route config updates or an explicit fallback plan—never treat a disable flag as "silently ignore YAML filter lines" across versions.

## 9. Designing a Stable API: Factory Names and Args Are the Public Contract

For a Gateway filter library, the **public contract goes far beyond Java method signatures**. It includes:

- **Factory name** in YAML: `EdgeRequestId`.
- **Arg names and types**: `prefix` as String; length/charset constraints.
- **Shortcut syntax**: `EdgeRequestId=edge-` via `shortcutFieldOrder`.
- **Route / `default-filters` scope**.
- **Execution timing and effects on path/header/body**.
- **Error behavior**: fail configuration on invalid values or skip?
- **Interactions with security, rate limiters, retries, circuit breakers, and caching**.
- **Header names created/overwritten** and non-disclosure rules.
- **Supported Java, Spring Boot, and Spring Cloud/Gateway versions**.

### Examples of Breaking Changes

| Change | Breaking risk? | Why |
|---|---|---|
| Rename `EdgeRequestId` to `RequestId` | **Yes** | Consumer YAML routes can no longer resolve the factory |
| Rename `prefix` to `valuePrefix` without an alias | **Yes** | Binder fails on existing args |
| Reorder `shortcutFieldOrder` | **Yes** | Shorthand routes bind values to wrong fields |
| Switch from `headers.set` to `headers.add` | **Yes** | Anti-spoofing and single-value header guarantees break |
| Start generating IDs even when no route matches | **Yes** | Alters execution scope and metrics |
| Add a new optional field with a behavior-preserving default | Usually no | Still test binder and backward compatibility |
| Tighten validation rules | Potentially | Previously accepted configs may now be rejected |
| Move public classes to a different package | Potentially | Consumer Java code and auto-config may break |
| Raise Java bytecode target to a newer JDK | **Yes** | Older runtimes fail to load classes |
| Refactor internal implementation while preserving semantics | Usually no | Still run contract tests to catch regressions |

Write release notes **from the YAML user's perspective**: will old configs keep working, which values are now rejected, how do headers change, and does filter order shift?

### Schema / Config Metadata

When a filter accepts multiple parameters, document every parameter: name, type, default, validation, plus both expanded and shortcut examples. Spring Boot configuration metadata for `@ConfigurationProperties` helps auto-config properties like `acme.gateway.edge-request-id.enabled`, yet **`GatewayFilterFactory` args do not behave identically to standard `@ConfigurationProperties`**.

Never maintain defaults in three separate places that drift apart: the `Config` class, documentation, and integration tests must all match.

## 10. Compatibility Matrix and Release Trains

Spring Cloud Gateway ships inside the **Spring Boot + Spring Cloud release train + Spring Framework + Reactor Netty** ecosystem. Never pick an artifact version simply because "it is the latest" and force it onto an app running a different baseline.

Build your matrix from **official BOMs and real test runs**, for example:

| App platform | Gateway stack | Library version | Test result |
|---|---|---|---|
| Boot line A, Cloud train A | Compatible WebFlux A | edge-filters 1.3.x | `SUPPORTED` after CI passes |
| Boot line B, Cloud train B | Compatible WebFlux B | edge-filters 1.4.x | `SUPPORTED` after CI passes |
| Boot line C, Cloud train C | Gateway Server MVC | edge-filters WebFlux | **UNSUPPORTED** without an MVC implementation |
| Boot line D, Cloud train D | Newer Gateway WebFlux major | Older edge-filters 1.x | `UNVERIFIED` until built and tested |
| Different Java runtime target | Any | Too-new JAR bytecode | **UNSUPPORTED** |

**A/B/C/D in the table are placeholders**, not real release train names. Fill those columns with exact BOM versions from your organization's current baselines. Never claim support merely because Maven/Gradle resolved dependencies.

### Upgrade Boundaries to Verify

1. **Spring Boot major:** annotations, auto-configuration discovery, minimum Java, AOT/native, property binding.
2. **Spring Cloud release train:** BOM and matching Boot compatibility.
3. **Gateway Server WebFlux vs. MVC:** packages, filter abstractions, request/response APIs, and routing models.
4. **Spring Framework / Reactor:** method signatures, Context propagation, Netty/HTTP encoding, and cancellation.
5. **Third-party dependencies:** Caffeine, Micrometer, Jackson, Security, Resilience4j if used by the filter.
6. **Application config namespace:** `spring.cloud.gateway.*` layout can evolve; never hardcode legacy namespaces in guides for newer lines.
7. **Native image / AOT:** reflection/binding metadata for `Config`, auto-config, and hints if native builds are supported.
8. **Classloader / dependency conflicts:** two JAR versions exposing the same factory name cause subtle failures.

### Library Versioning Policy

A straightforward policy:

- **MAJOR:** breaking changes to factory names, args, behavior, or supported baselines.
- **MINOR:** backward-compatible factories/features, or new optional fields with safe defaults.
- **PATCH:** bug fixes preserving contracts.

This applies **semantic versioning**, without promising every fix fits a patch release. If a security fix must alter behavior, document the migration impact and rollout plan clearly.

### Never Mix Two Gateway Majors Carelessly

A WebFlux starter compiled against one release train **should not advertise universal compatibility** via wide version ranges or dependency exclusions forcing the classpath. When multiple platform baselines must be supported, maintain:

- A maintenance branch/release line for older supported Boot/Cloud trains.
- A branch for newer Boot/Cloud trains with API adaptations where needed.
- A stable YAML contract above, backed by line-appropriate implementations below.

Keep the number of supported lines minimal to limit maintenance overhead. **Runtime compatibility must be proven**, never assumed.

## 11. Dependency Management and Avoiding Classpath Conflicts

In consuming apps, Spring Boot/Cloud versions should be coordinated by a compatible **BOM**. When compiling the library against Gateway APIs, align with the target line's baseline. Avoid:

- Pinning an arbitrary Reactor Netty version that diverges from the Gateway app's BOM.
- Shading/repackaging `org.springframework.cloud.gateway.*` or `org.springframework.web.*` into a custom JAR.
- Pulling `spring-boot-starter-web` into Gateway Server WebFlux just for a controller or test helper.
- Adding both Gateway Server MVC and WebFlux starters and hoping filters work.
- Mixing a Servlet Spring Security starter into reactive `ServerHttpSecurity` code.
- Using dynamic `+` or `LATEST` versions in production CI builds.

### Better Dependency Classification

| Dependency | How to think about it |
|---|---|
| Gateway filter API | Needed to compile and run on the Gateway runtime |
| Spring WebFlux API | Needed for `ServerWebExchange`/`ServerHttpRequest`; must align with Gateway |
| Spring Boot autoconfigure | Needed only by auto-config/starter modules at a matching version |
| Spring Security | Optional when filter has security logic; avoid forcing onto every app |
| Redis / Micrometer / Resilience4j | Optional per feature; avoid pulling into the whole starter by default |
| JUnit / Reactor Test / `WebTestClient` | Test-only |
| Logging API | Use the right facade API; never bundle arbitrary logging implementations |

If a filter must call an external API, prefer `WebClient` with timeouts, backpressure, and reactive error handling—while remembering **not to make per-request remote calls** when a built-in filter already suffices.

## 12. Unit Testing the `GatewayFilterFactory` Contract

A shared library must go beyond "the Spring context starts". Verify the **filter's output** across `GatewayFilterChain` with simulated requests.

~~~java
package com.acme.edge.filters;

import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class EdgeRequestIdGatewayFilterFactoryTest {

    private final EdgeRequestIdGatewayFilterFactory factory =
        new EdgeRequestIdGatewayFilterFactory();

    @Test
    void overwritesUntrustedHeaderBeforeForwarding() {
        var config = new EdgeRequestIdGatewayFilterFactory.Config();
        config.setPrefix("orders-");

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/orders/42")
                .header("X-Edge-Request-Id", "spoofed"));

        AtomicReference<ServerWebExchange> forwarded =
            new AtomicReference<>();

        GatewayFilterChain chain = next -> {
            forwarded.set(next);
            return Mono.empty();
        };

        StepVerifier.create(factory.apply(config)
                .filter(exchange, chain))
            .verifyComplete();

        String header = forwarded.get().getRequest().getHeaders()
            .getFirst("X-Edge-Request-Id");

        assertNotNull(header);
        assertNotEquals("spoofed", header);
        assertTrue(header.startsWith("orders-"));
        assertEquals("/api/orders/42",
            forwarded.get().getRequest().getURI().getPath());
    }

    @Test
    void rejectsUnsafePrefixAtFactoryApplication() {
        var config = new EdgeRequestIdGatewayFilterFactory.Config();
        config.setPrefix("bad prefix\r\n");

        assertThrows(IllegalArgumentException.class,
            () -> factory.apply(config));
    }
}
~~~

**Key takeaway:** the mocked `GatewayFilterChain` receives the **mutated exchange** without hitting a real backend. Unit tests therefore verify header logic, config validation, and path preservation, yet **do not prove** YAML binding, auto-configuration, or Netty router compatibility.

### Minimum Contract Test Suite

| Test | Expected |
|---|---|
| Default prefix | Without args, generates ID with documented default prefix |
| Custom prefix | `EdgeRequestId=orders-` maps properly to `Config.prefix` |
| Client-spoofed header | Overwritten, never appended with `spoofed` |
| Two consecutive requests | Distinct IDs per design |
| Request path and query | Left intact by the custom filter |
| Multi-valued incoming header | `set` replaces all values with the same name |
| Blank/invalid prefix | Configuration fails clearly |
| Chain complete / error / cancel | Never swallows errors or spawns detached subscriptions |
| Factory name | `EdgeRequestId` resolves to the right class |
| Bean override | When consumer defines its own Bean, auto-config yields without duplicates |
| Disabled property | When Bean is disabled, routes avoid referencing it or fail as planned |
| Java baseline | Build/bytecode runs on supported JDKs |

If a real filter accesses sessions, JWTs, or tokens, add tests for missing principals, anonymous callers, expired tokens, multi-tenant isolation, and log redaction. Never treat unverified mock claims as proof of production security correctness.

## 13. Integration Testing: From YAML to Downstream Receiving the Header

An integration test must boot a **real Gateway runtime** with the embedded starter, load YAML routes, and forward to a test backend (such as WireMock or an embedded HTTP server). Verify:

1. **`AutoConfiguration.imports`** registered the factory in the context.
2. `@ConditionalOnWebApplication(Type.REACTIVE)` holds for the WebFlux app.
3. `EdgeRequestId=orders-` bound from YAML.
4. Route `Path` matched and the filter ran before routing.
5. Backend received the new header, never `spoofed`.
6. Response status/body from backend remain intact per policy.
7. Requests not matching the route are not processed by this route filter.
8. Another Gateway app consuming the same starter upholds the identical contract.

Manual check when a mock backend exposes a header-echo endpoint:

~~~bash
curl -i "http://localhost:8080/api/orders/42" \
  -H "X-Edge-Request-Id: spoofed"
~~~

The test backend should record the **Gateway-generated ID** (different from `spoofed`), while business payloads stay unchanged. If the backend echoes that header back to the client in a lab, remember **that does not happen automatically**; the backend or a response filter must actively emit it.

### Testing Interactions with Other Filters

| Combination | Risks to test |
|---|---|
| `RewritePath` / `StripPrefix` | ID preserved, downstream path matches target |
| `SetRequestHeader` with same name | Later filter may overwrite ID; define clear ownership |
| `AddRequestHeader` with same name | Header can become multi-valued, breaking contract |
| `RequestRateLimiter` | 429 from limiter may short-circuit before ID filter depending on order |
| `Retry` | One client request may spawn multiple outbound attempts; clarify whether ID changes across attempts |
| `CircuitBreaker` / fallback | Does fallback receive a valid ID without leaking raw error details? |
| `LocalResponseCache` | Cache hit skips backend; never miscount as "downstream received ID" |
| `lb://service-id` | Every downstream instance receives ID under the same contract |
| Spring Security | Filter never replaces authentication or grants permissions |
| CORS / response headers | If browser JS reads the ID from responses, expose headers properly |
| TLS / mTLS | Diagnostic IDs are not proof of authenticated callers |

**Retry note:** if the UUID filter wraps outside `Retry`, outbound attempts for one client request share the same ID; if the filter sits inside the retried segment, each attempt gets a fresh ID. Define **request ID** (per client request) vs. **attempt ID** (per outbound attempt) clearly as separate concepts. Never infer from YAML line order alone; inspect runtime execution and trace spans.

## 14. Version Compatibility Must Be Tested Against a Matrix

Every starter release should execute tests across the **Boot/Cloud/Gateway combinations your organization actually supports**. A strong CI pipeline includes:

~~~text
Build library at Java baseline
    |
    +--> Unit contract tests (Config, headers, errors)
    |
    +--> Starter auto-configuration tests (matching / non-matching conditions)
    |
    +--> Gateway Server WebFlux integration tests
    |       - YAML shortcut / expanded routes
    |       - downstream HTTP echo
    |       - Spring Security / Retry / header ordering
    |
    +--> Dependency/BOM alignment checks
    |
    +--> Multi-instance smoke tests if relevant state exists
    |
    +--> Native/AOT tests if release promises support
    |
    +--> Publish artifacts + changelog + migration notes
~~~

Never rely solely on **unit tests running without a Gateway runtime** to claim compatibility. Real breakages typically surface when an app boots and binds routes.

### Checking Binary / Source / Config Compatibility

| Compatibility dimension | Example failure | How to catch it |
|---|---|---|
| **Binary** | `NoSuchMethodError`, `NoClassDefFoundError` | Boot app with target BOM; run integration tests |
| **Source** | Changed imports, packages, or method signatures | Compile tests against each baseline |
| **Configuration** | `EdgeRequestId`/`prefix` fails to bind | Test shortcut and expanded YAML directly |
| **Behavior** | Filter ordering, response commit, or header mutation changed | End-to-end HTTP assertions |
| **Security** | Trusting client headers, leaking tokens, or auth bypass | Negative security tests |
| **Performance** | Latency, CPU, or allocation regressions | Compare p95/p99 and profile appropriately |
| **Native / AOT** | Missing Bean/Config metadata or hints | Native build + smoke test when supported |
| **Deployment** | Old/new nodes emit differing headers | Canary / rolling-upgrade compatibility tests |

If you run binary API diff tools such as japicmp or Revapi, treat them as **one layer among several**, never a replacement for running real routes inside a Gateway runtime.

## 15. Observability, Logging, and Safety in Shared Libraries

A filter shared across many apps has a wide blast radius: a tiny logging mistake can cause errors or data leaks across **every Gateway**.

### Logging Principles

- Log **factory name, route ID, outcome, and correlation ID** within safe bounds.
- Never log raw `Authorization`, `Cookie`, API keys, JWTs, session IDs, or sensitive request bodies.
- Never use full URL queries containing PII as metric labels.
- Never use per-request random IDs as Micrometer/Prometheus tags, which cause unbounded cardinality.
- For distributed tracing, prefer ecosystem standards rather than inventing custom headers to replace `traceparent`.
- When a filter attaches diagnostic metadata, define clearly **who may read it** and whether it may leave trust boundaries to third parties.

### Performance and Reactive Constraints

| Risky pattern | Consequence |
|---|---|
| `block()` inside `GatewayFilter` | Blocks event loop, spikes latency across connections |
| Manual `subscribe()` then continuing chain | Race conditions, lost errors, ignores cancellation |
| Per-request state in singleton Bean fields | Cross-request state leaks, concurrency races |
| Buffering every request body just to log | Memory pressure, PII exposure, breaks streaming |
| Remote calls without timeouts | Hanging requests, cascading failures |
| Setting response headers after commit | Headers silently ignored or runtime errors |
| Calling `chain.filter(exchange)` twice | Double forwarding and duplicate side effects |
| Exception messages in metric tags | High cardinality and internal detail leaks |

**Rule:** Filters must **compose publishers** (`Mono`/`Flux`) and let the framework manage subscriptions, cancellation, and backpressure. If external resources (HTTP clients, Redis, thread pools, caches) are used, design clean lifecycles, timeouts, and cleanup instead of allocating them per request.

## 16. Controlled Deployment, Upgrades, and Rollback

A realistic release workflow for a shared library:

1. **Design and review the contract:** factory name, args, defaults, path/header impact, security, and error semantics.
2. **Build and unit-test** at the Java baseline; align dependencies with the target BOM.
3. **Run the test matrix** across all supported Boot/Cloud/Gateway combinations.
4. **Publish immutable artifacts** and changelogs; never overwrite an existing version.
5. **Canary one Gateway app** with the new version; watch startup errors, route binding, 4xx/5xx, latency, and memory.
6. **Roll out by app group**, verifying compatibility while cluster nodes run mixed versions.
7. **Roll back** to a known-good artifact and config if contracts or policies break.
8. **Patch and withdraw vulnerable releases** under security response procedures when critical flaws arise.

### Why Are Rolling Upgrades Harder Than They Look?

Suppose Gateway node A runs the new starter emitting `X-Edge-Request-Id`, while node B still runs the older version emitting `X-Trace-Id`. Backends must handle both during rollout, or the organization must emit **both names** during a transition window. That is an **internal protocol change**, not just swapping a JAR.

Similarly, if a filter library alters `Retry` behavior or header ordering ahead of `RequestRateLimiter`, staggered upgrades across Gateway nodes can apply inconsistent policies per request. You may need to:

- Ship a transitional release supporting both old and new names.
- Roll out backend support for the new contract **before** switching Gateways.
- Keep the previous version deployable long enough for rollback.
- Gate releases if route configs lack a migration path.

**Never simply bump a version and "hope every app updates cleanly".** Shared libraries can have dozens of consumers on independent release schedules; forward compatibility must be engineered.

## 17. Troubleshooting When a Shared Filter Fails to Work

| Symptom | Likely causes to check | How to resolve |
|---|---|---|
| `Unable to find GatewayFilterFactory with name EdgeRequestId` | JAR missing from classpath, auto-config didn't register Bean, wrong factory name, or disabled flag | Check imports/conditions, starter dependency, and class name |
| App fails to start after BOM bump | Incompatible APIs/bytecode/runtime | Inspect `NoSuchMethodError`, `ClassNotFoundException`, and support matrix |
| Two Beans registered for the same factory | Both `@Component` and `@Bean` active | Choose one registration strategy; test overrides |
| YAML `prefix` has no effect | Wrong property name, missing setter/Config binding | Test both expanded and shortcut forms on target version |
| Shortcut fails while expanded works | Wrong `shortcutFieldOrder` or unsupported shortcut syntax | Inspect `List` arg order and YAML |
| Client's `spoofed` header still reaches backend | Filter didn't run, a later filter overwrote it, or `add` was used | Inspect runtime route, filter order, and backend echo |
| Some requests lack the ID | Unmatched route, rejected early by Security/RateLimiter, or cache hit bypassed routing | Identify which layer needs the ID |
| Header generated twice | Both `default-filters` and route filter active, or duplicate `GlobalFilter` | Remove duplicate registrations; inspect request/response |
| Node A works, Node B fails | Artifact/config drift or auto-config disabled | Compare versions, conditions, and runtime routes |
| Gateway Server MVC ignores the filter | WebFlux abstractions used on a Servlet stack | Implement a factory compatible with Server MVC |
| Version bump changes status/headers | Behavior changed across releases | Run contract tests and read release notes/migration guides |
| App memory grows after adding filter | Body buffering, per-request state leaks, or metric cardinality | Profile memory and audit reactive code |
| 401/403 still returned despite ID filter | Correlation headers do not replace authentication | Inspect Spring Security separately |
| CORS blocks JS from reading `X-Edge-Request-Id` | Header set only on request, absent from response, or not exposed | Set response header and configure `exposedHeaders` if needed |
| Retry produces different IDs per attempt | Filter sits inside the retried chain segment | Separate request-id vs. attempt-id and verify ordering |
| Native build fails | Auto-config/hints incompatible with AOT | Run native tests and add version-appropriate hints |

### Six Questions to Narrow Down Issues Quickly

1. **Right web stack?** Gateway Server WebFlux or MVC?
2. **Which starter/version** is running, and does it match the Boot/Cloud BOM?
3. **Is the factory Bean** created uniquely, and do auto-config conditions match?
4. **Does the runtime route** actually include `EdgeRequestId` with the right args?
5. **Do `GatewayFilterChain` ordering** and other filters overwrite or strip the header?
6. **What did the backend actually receive**, and did the error occur before routing, inside a filter, during routing, or after response commit?

Use Actuator Gateway route inspection when supported by your version, while **protecting management endpoints** with network controls and authorization. Never expose admin APIs by disabling authentication just to debug.

## 18. Acceptance Checklist for a Custom Filter Library

- [ ] I distinguish `GatewayFilterFactory`, `GlobalFilter`, `WebFilter`, and `SecurityWebFilterChain`.
- [ ] I build a custom filter only when built-in factories cannot fulfill the contract.
- [ ] I use a stable factory name, a class ending in `GatewayFilterFactory`, and a bindable `Config`.
- [ ] I validate args and define clear failure behavior for invalid configuration.
- [ ] The filter never trusts client-supplied request headers as authentication sources.
- [ ] The filter never calls `block()`, manually calls `subscribe()`, stores per-request state in singletons, or invokes the chain twice.
- [ ] I respect response commits and never mutate responses after commit.
- [ ] I have unit tests covering headers, paths, concurrency, errors, and shortcut binding.
- [ ] I have integration tests loading YAML, auto-configuring Beans, and forwarding real HTTP traffic.
- [ ] I do not register both `@Component` and a starter `@Bean` for the same factory.
- [ ] For Boot 3, the auto-config JAR includes `AutoConfiguration.imports` at the exact path.
- [ ] I declare only **tested** Boot/Cloud/Gateway/Java ranges rather than guessing compatibility from version numbers.
- [ ] I never force Servlet/MVC dependencies into Gateway WebFlux.
- [ ] I align with a compatible BOM without shading framework classes or overriding Reactor carelessly.
- [ ] I maintain versioning, changelogs, migration guides, and rollback procedures.
- [ ] I check for breaking changes in factory names, args, shortcuts, response/header semantics, and filter ordering.
- [ ] I tested interactions with Spring Security, Retry, CircuitBreaker, RateLimiter, CORS, and LoadBalancer.
- [ ] I measure p95/p99, errors, memory, and audits without logging raw tokens or PII.
- [ ] I verified rolling upgrades when multiple Gateway apps/nodes run mixed versions.
- [ ] I publish a support matrix only after CI actually passes across all committed baselines.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — sections on **Writing Custom GatewayFilter Factories**, **Global Filters**, filter ordering, route configuration, and Server WebFlux.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — identifying versions and release trains.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html) — `@AutoConfiguration`, `AutoConfiguration.imports`, and conditional Bean registration in modern Spring Boot.
- [Spring Boot — Dependency Management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html) — managing BOMs and avoiding version conflicts.
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — `ServerWebExchange`, reactive filters, and response lifecycle.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/) — `Mono`, cancellation, non-blocking composition, and Reactor Context.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/) — metrics, tags, and cardinality bounds.
- [Semantic Versioning](https://semver.org/) — distinguishing breaking API changes and library version levels.

**Takeaway:** A shared filter is more than **a reusable Java class**. It is a **YAML/Java contract and HTTP behavior** encompassing factory name, args, ordering, execution scope, security boundaries, and supported runtime versions. To scale safely across multiple Gateways, package it with proper starter/auto-configuration, test **from Bean registration through real downstream requests**, manage release trains via BOMs, and deploy against an evidence-backed compatibility matrix.
