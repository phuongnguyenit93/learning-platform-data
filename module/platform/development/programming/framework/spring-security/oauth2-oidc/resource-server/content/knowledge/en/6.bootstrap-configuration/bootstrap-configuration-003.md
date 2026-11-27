# Initializing a Servlet or WebFlux Application Based on Execution Goals

When building an **OAuth 2.0 Resource Server with Spring Security**, one decision you need to make right at project initialization is whether to choose **Spring MVC on the Servlet stack** or **Spring WebFlux on the reactive stack**. Both can protect REST APIs with access tokens issued by an **Authorization Server**; the main differences lie in the **request processing model, I/O organization, programming APIs, and Spring Security components used**.

For example, an Orders API can use Spring MVC with `SecurityFilterChain` or WebFlux with `SecurityWebFilterChain`. In both cases, the client still sends:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

The Resource Server must verify the token, check permissions, and return the result. Choosing Servlet or WebFlux **does not change this OAuth 2.0 responsibility**, though it strongly affects libraries, return types, database access patterns, execution flow, and system scaling strategy.

## 1. Distinguishing Three Decisions Often Conflated

Before creating the project, separate three questions:

1. **What security role does the application play?** In this lesson, the application is a **Resource Server**, receiving access tokens from incoming requests. It does not issue access tokens or refresh tokens on behalf of clients.
2. **Which web stack does the application use?** Choose Spring MVC/Servlet or Spring WebFlux/reactive according to execution goals.
3. **Which mechanism does the application use to verify tokens?** Choose JWT with signatures/claims or opaque tokens with introspection, based on the contract with the Authorization Server. Both web stacks support configuring JWT and opaque tokens.

A system may use an Authorization Server supporting OIDC for user logins while the API acts purely as an OAuth 2.0 Resource Server. **OIDC login for a client and bearer-token authentication for an API are two separate concerns.** Choosing WebFlux does not automatically enable OIDC login; adding the Resource Server starter does not create a token endpoint either.

## 2. How Do Servlet and WebFlux Differ?

| Criterion | Spring MVC / Servlet | Spring WebFlux / Reactive |
| --- | --- | --- |
| Web processing model | Request/response model based on the Servlet API, typically using synchronous execution threads | Reactive model based on Reactive Streams, supporting non-blocking I/O and backpressure |
| Common web starter | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| Typical controller | `@RestController`, returning DTOs, `ResponseEntity<T>` | `@RestController`, typically returning `Mono<T>` or `Flux<T>` |
| HTTP Security | `HttpSecurity` → `SecurityFilterChain` | `ServerHttpSecurity` → `SecurityWebFilterChain` |
| Authentication context | `SecurityContextHolder` on the corresponding synchronous thread | `ReactiveSecurityContextHolder` bound to the Reactor context |
| JWT verification in Spring Security | `JwtDecoder`, typically `NimbusJwtDecoder` | `ReactiveJwtDecoder`, typically `NimbusReactiveJwtDecoder` |
| Opaque token introspection | Introspector component for the Servlet stack | Reactive introspector component |
| Native data access | JDBC, JPA/Hibernate, blocking libraries | R2DBC, reactive clients; caution needed if calling blocking libraries |
| Scaling model | Easy to use with synchronous Java libraries and the Servlet ecosystem | Helpful for high concurrent I/O when all layers are truly reactive |
| Handling large payloads/streaming | MVC async/streaming mechanisms available | `Flux`, streaming, and backpressure under the reactive model |

**There is no rule that "WebFlux is always faster than MVC."** Performance depends on actual load, database, I/O latency, degree of blocking, server configuration, and deployment setup. Servlet also has optimization options and newer Spring/Java versions can support virtual threads. WebFlux benefits from the reactive model when underlying components are genuinely non-blocking; performing blocking operations on an event loop diminishes that benefit or turns it into a bottleneck.

### How Servlet Processes a Request

In the traditional MVC model, service code may call a synchronous repository and wait for the result:

~~~text
HTTP request
     |
     v
Servlet container
     |
     v
Spring Security filter chain
     |
     v
Spring MVC Controller
     |
     v
Service -> JPA/JDBC (blocking) -> Database
     |
     v
HTTP response
~~~

Developers typically write a method returning a Java object:

~~~java
@GetMapping("/api/orders/{id}")
public OrderDto getOrder(@PathVariable long id) {
    return orderService.getOrder(id);
}
~~~

If `getOrder` performs synchronous I/O, the processing thread waits for the data. This is an intuitive, widespread model that integrates smoothly with many libraries used in business applications.

### How WebFlux Processes a Request

In WebFlux, controllers and services can represent asynchronous results using `Mono` (0 or 1 value) and `Flux` (0 to many values):

~~~text
HTTP request
     |
     v
Reactive HTTP server
     |
     v
Spring Security WebFilter chain
     |
     v
WebFlux Handler
     |
     v
Reactive Service -> Reactive database/HTTP client
     |
     v
Mono/Flux -> HTTP response
~~~

Example:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<OrderDto> getOrder(@PathVariable long id) {
    return reactiveOrderService.getOrder(id);
}
~~~

`Mono<OrderDto>` does not mean "a new Java thread." It represents a reactive pipeline executed via subscription and contextual schedulers. Code calling blocking APIs inside that pipeline is still **blocking**, even if the method signature returns `Mono`.

## 3. Choosing a Stack from Execution Goals

Some practical criteria:

| Goal/condition | Preferred choice | Why |
| --- | --- | --- |
| CRUD REST API with JPA/Hibernate or JDBC | **Servlet / Spring MVC** | Aligns with blocking data libraries; straightforward execution flow |
| Team already operates well within the Spring MVC/Servlet ecosystem | **Servlet / Spring MVC** | Reduces new concepts and transition costs |
| API gateway, proxy, or aggregator calling multiple services over reactive HTTP | **WebFlux** if I/O end-to-end is reactive | Well-suited for composing many asynchronous requests |
| Data streaming, many I/O-bound connections, backpressure needs | **WebFlux** is worth considering | Reactor provides streaming operators and backpressure |
| Most dependencies are blocking, but want one `Mono` endpoint | **Servlet / Spring MVC** is usually still sensible | Returning a reactive type does not make the whole system non-blocking |
| System already uses R2DBC repositories and reactive WebClient | **WebFlux** | Maintains a reactive I/O chain from web down to data |
| Only need to verify Bearer JWT/OIDC issuer | **Both** | Token validation alone is not enough to dictate the web stack |

### Decision Flowchart

~~~mermaid
flowchart TD
    A["API will receive Bearer access tokens"] --> B{"Are business dependencies mostly blocking?"}
    B -->|Yes, JPA/JDBC/blocking SDKs| C["Prefer Spring MVC / Servlet"]
    B -->|No, or already reactive-ready| D{"Is there a clear reactive need?"}
    D -->|Yes: concurrent I/O, streaming, backpressure| E["Consider Spring WebFlux"]
    D -->|Unclear| F["Start with Spring MVC"]
    C --> G["Configure Resource Server and API permissions"]
    E --> G
    F --> G
~~~

This chart is an initial selection guide, not a substitute for real load measurement. If specific throughput or latency targets matter, benchmark with your actual dependencies, connection counts, and deployment topology.

## 4. Initializing the Project: Shared Elements

You can generate a Spring Boot application via Spring Initializr, IDE tooling, or an existing build template. Both options must align on:

- **Java/JDK** compatible with the chosen Spring Boot/Spring Security versions.
- **Maven or Gradle** managing dependency versions via Spring Boot parent/BOM or an equivalent mechanism.
- **Spring Boot application entry point** with `@SpringBootApplication`.
- **OAuth2 Resource Server starter**, plus the **appropriate web starter**.
- **Issuer address and/or JWK Set URI** or **introspection endpoint**, depending on access token type.
- **API access control contract**: audience, scopes/authorities, and business permissions.

Declare dependencies and web configuration clearly for one chosen option, creating only one of the two app setups below. If a project must pull libraries from both sides because of a client dependency, make sure you know exactly which web application type Spring Boot selects.

### Example Directory Structure

~~~text
orders-api/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/orders/
    │   │   ├── OrdersApiApplication.java
    │   │   ├── security/
    │   │   │   └── ApiSecurityConfiguration.java
    │   │   ├── controller/
    │   │   │   └── OrdersController.java
    │   │   └── service/
    │   │       └── OrdersService.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/
~~~

The entry point is essentially identical on both stacks:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApiApplication.class, args);
    }
}
~~~

In the `pom.xml` snippets below, we assume the project uses the Spring Boot parent/BOM for version management; the dependency blocks go inside `<dependencies>`. Starter names may vary across major Spring Boot generations; use starters present in your selected version and never arbitrarily mix major Spring versions.

## 5. Option A: Creating a Resource Server on the Servlet Stack

### 5.1. Dependencies

For a Spring Boot structure with the MVC web starter named `spring-boot-starter-web`:

~~~xml
<dependencies>
    <!-- Spring MVC running on the Servlet stack -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <!-- Bearer token authentication for the API -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
~~~

The MVC web starter typically configures an embedded servlet container (e.g., Tomcat) according to the starter's defaults. The Resource Server starter supplies the Spring Security components needed to process bearer tokens with JWT or opaque tokens as configured.

This is a **Resource Server**, not an OAuth2 Client or Authorization Server. If the application needs to call another API and acquire tokens itself for outbound requests, that is an additional capability to design separately.

### 5.2. Configuring Issuer for JWT

Example `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

`issuer-uri` must match the actual issuer published by the Authorization Server and present in the `iss` claim. The Resource Server uses metadata/verification keys via supported mechanisms to validate JWTs. This address is **illustrative**, not a live issuer.

When configuring JWTs, also define **audience** checks per your API contract to avoid accepting access tokens issued for other resources. Do not assume `issuer-uri` alone covers audience validation and business permissions.

If the Authorization Server issues **opaque access tokens**, replace the JWT branch with the corresponding introspection configuration, using the dedicated endpoint and credentials for the Resource Server. Do not use a JWT decoder to parse an opaque token.

### 5.3. Servlet Security Configuration

File `security/ApiSecurityConfiguration.java`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            // Only appropriate when the API uses Bearer tokens, not cookie sessions.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Meaning of each component:**

- `HttpSecurity` and `SecurityFilterChain` are the **Servlet** branch APIs.
- `oauth2ResourceServer(...jwt(...))` enables Bearer JWT authentication for incoming requests.
- With Spring Security's standard scope mapping, scope `orders.read` becomes authority `SCOPE_orders.read`; issuers using different claims require appropriate mapping configuration.
- `SessionCreationPolicy.STATELESS` fits APIs that do not use HTTP sessions to maintain login state.
- Disabling CSRF in the example is only valid when authentication relies strictly on Bearer tokens explicitly sent by the client. If the app uses authentication cookies automatically attached by browsers, evaluate and enforce CSRF protection.
- `permitAll()` only waives authorization checks for the specified path; it does not make the whole application a public API.

In particular, `hasAuthority("SCOPE_orders.read")` only checks permissions at the route level. The API must still verify whether the user is allowed to read **that specific order** based on tenant, ownership, or business policies.

### 5.4. Minimal Servlet Controller

~~~java
package com.example.orders.controller;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/orders/me")
    public Map<String, String> currentSubject(
            @AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject() == null ? "unknown" : jwt.getSubject(),
            "message", "Access token was accepted"
        );
    }
}
~~~

`@AuthenticationPrincipal Jwt` simply extracts data from the authentication context already populated by Spring Security. This demonstrates reading the subject, **not proof that the subject is authorized to read all orders**. A real controller should call a service that enforces record-level permissions.

For `/api/orders/me`, the token requires the `orders.read` scope per the security chain above. The `/public/ping` endpoint can be called without a token.

## 6. Option B: Creating a Resource Server on the WebFlux Stack

### 6.1. Dependencies

For Spring Boot with the `spring-boot-starter-webflux` starter:

~~~xml
<dependencies>
    <!-- Spring WebFlux and reactive web runtime -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <!-- Bearer token authentication for the API -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
~~~

A reactive WebFlux application normally runs on **Reactor Netty** by default via the WebFlux starter. WebFlux can also run on certain Servlet containers supporting async, so distinguish the **web programming model** from the **underlying HTTP server name**.

### 6.2. JWT Configuration

A WebFlux Resource Server can likewise use:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

The issuer value has the same meaning as in Servlet: tokens must come from a trusted source and pass the API's authentication/authorization checks. The reactive Spring Security components validating JWTs execute via `ReactiveJwtDecoder` instead of the synchronous `JwtDecoder`.

### 6.3. WebFlux Security Configuration

File `security/ApiSecurityConfiguration.java`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            // Appropriate when the API authenticates solely via Bearer tokens.
            .csrf(csrf -> csrf.disable())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Differences from Servlet:**

- `ServerHttpSecurity` instead of `HttpSecurity`.
- `SecurityWebFilterChain` instead of `SecurityFilterChain`.
- `authorizeExchange` and `pathMatchers` instead of `authorizeHttpRequests` and `requestMatchers`.
- The security context in a reactive pipeline lives in the **Reactor context**; do not assume authentication data always resides in a fixed thread's `ThreadLocal`.
- Do not copy Servlet's `SessionCreationPolicy.STATELESS` directly into WebFlux. The reactive branch has its own APIs and security context/session management; a bearer API must be designed not to depend on server-side login sessions.

Same CSRF note: the example disables CSRF for a pure Bearer-token API. If a WebFlux application accepts cookie authentication from browsers, keep or configure CSRF appropriately for that model.

### 6.4. Minimal WebFlux Controller

~~~java
package com.example.orders.controller;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/orders/me")
    public Mono<Map<String, String>> currentSubject(
            @AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject() == null ? "unknown" : jwt.getSubject();

        return Mono.just(Map.of(
            "subject", subject,
            "message", "Access token was accepted"
        ));
    }
}
~~~

This snippet demonstrates the **reactive signature** of the controller without performing asynchronous I/O yet. In a real application, composing repositories, HTTP clients, or data streams is where you design `Mono`/`Flux` pipelines and proper backpressure policies.

If you need `Authentication` deeper inside a reactive pipeline, use the appropriate API like `ReactiveSecurityContextHolder` or pass identity/claims explicitly. Never assume `SecurityContextHolder.getContext()` will return the same data across asynchronous steps after a pipeline switches schedulers.

## 7. Similarities and Differences in Resource Server Configuration Across Stacks

### What Is the Same

Both MVC and WebFlux Resource Servers:

- Receive access tokens typically via the `Authorization: Bearer ...` header.
- Validate tokens against issuer, signature/keys or introspection, expiration, and required conditions.
- Apply scope, authority, and resource-level authorization rules.
- Typically return **401** when lacking valid authentication, and **403** when authenticated but lacking sufficient permissions.
- Do not issue access tokens or refresh tokens for clients.
- Can serve APIs using tokens issued by an OAuth 2.0/OIDC-compliant Authorization Server, provided tokens match the API contract.

### What Is Different

| Feature | Servlet | WebFlux |
| --- | --- | --- |
| Security config object | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain bean | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Web request matching | `requestMatchers(...)` | `pathMatchers(...)` |
| Authorization rules setup | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| Extensible JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Business return values | Plain DTOs or `ResponseEntity` | `Mono<T>`, `Flux<T>`, or WebFlux-compatible types |
| Authentication context | Traditional Servlet thread-bound | Reactor context across the pipeline |

If you need custom `aud` validation or custom claim mapping, use the **decoder/converter matching your stack**. A synchronous `JwtDecoder` bean is not a drop-in replacement for WebFlux's `ReactiveJwtDecoder`; likewise, an MVC `SecurityFilterChain` configuration cannot be pasted verbatim into a WebFlux layer.

### JWT vs. Opaque Token

Choosing Servlet or WebFlux **does not force tokens to be JWTs**. For opaque tokens, the Resource Server can use introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: YOUR_INTROSPECTION_CLIENT_ID
          client-secret: YOUR_INTROSPECTION_CLIENT_SECRET
~~~

The values above are placeholders; use actual endpoints, permissions, and secure credential handling. Replace `jwt(...)` in the security chain with the corresponding opaque token mode for your stack. Introspection is **checking an existing token**, not a refresh token grant.

## 8. Choosing Data Access Technology Alongside the Web Stack

The Servlet vs. WebFlux choice affects many layers **behind** authentication:

### Servlet + JPA/JDBC

This is the common pairing when using a synchronous transaction model:

~~~text
Controller (Servlet)
    -> Service
        -> @Transactional
            -> JPA Repository / JDBC
                -> Database
~~~

Blocking data reads/writes execute within a corresponding processing thread. Implementing transactions, tracing, and error handling follows a familiar synchronous programming model.

### WebFlux + R2DBC/Reactive HTTP Client

A reactive system typically uses R2DBC or SDKs with native Reactive Streams support and `WebClient` for HTTP calls:

~~~text
Handler (WebFlux)
    -> Reactive Service
        -> Mono/Flux
            -> R2DBC / WebClient
                -> Database / Remote API
~~~

Example service combining two asynchronous calls:

~~~java
import reactor.core.publisher.Mono;

public Mono<OrderView> getOrderView(String orderId) {
    Mono<Order> order = orderRepository.findById(orderId);
    Mono<Customer> customer = customerClient.getByOrderId(orderId);

    return Mono.zip(order, customer)
        .map(tuple -> new OrderView(tuple.getT1(), tuple.getT2()));
}
~~~

This example assumes the repository/client return `Mono` and perform truly reactive operations; `OrderView` is an application DTO. `Mono.zip` combines two result sources, but **does not prove two tasks always run faster** under every circumstance.

### If You Must Call a Blocking Library from WebFlux

For example, an SDK offering only a synchronous API:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<LegacyResult> callLegacySdk() {
    return Mono.fromCallable(() -> legacySdk.fetch())
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Offloading blocking calls onto an appropriate scheduler helps avoid blocking the event loop. However, this **does not make the SDK non-blocking**: thread limits, memory, connection counts, and transaction context still need careful sizing. If most of the service executes blocking code, Spring MVC is usually a simpler starting point.

Conversely, an MVC app can also use `WebClient` for HTTP calls. Adding the WebFlux dependency solely to use `WebClient` **does not automatically switch the entire server to WebFlux**.

## 9. Avoiding Wrong Web Application Type Detection with Multiple Starters

A common initialization mistake is adding **both** `spring-boot-starter-web` and `spring-boot-starter-webflux` and assuming the system will definitely run reactively.

Under Spring Boot's standard auto-detection, when both Spring MVC and WebFlux are present, **Spring MVC typically takes precedence for the web application type**. Having `Mono` or `WebClient` on the classpath does not turn all servlet filters and controllers into a reactive web runtime.

Therefore:

1. If your target is MVC, pick the MVC web starter and use `SecurityFilterChain`.
2. If your target is WebFlux, pick the WebFlux web starter and use `SecurityWebFilterChain`.
3. If a project must carry libraries from both sides, explicitly determine the desired application type and configure it using Spring Boot's supported mechanism—such as `spring.main.web-application-type`—when there is a real reason to override manually.

Example targeting reactive **when a mixed classpath requires forcing the type**:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Only set this after understanding the dependencies, auto-configurations, and their compatibility. Do not treat it as a fix-all for mixing synchronous beans/filters with reactive ones.

A related mistake is configuring:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) { /* ... */ }
~~~

in an application running purely on WebFlux. Using the wrong security API family leads to missing beans, startup failures, or policies not being applied as expected. Use the matching pair:

- **Servlet:** `HttpSecurity` + `SecurityFilterChain`.
- **WebFlux:** `ServerHttpSecurity` + `SecurityWebFilterChain`.

## 10. Smoke-Testing a Newly Initialized Resource Server

### 10.1. Preparing the Authorization Server

Before testing protected endpoints:

- The Authorization Server must issue access tokens with the configured issuer.
- If using JWTs, the Resource Server must be able to reach metadata/JWKS matching its configuration to verify signatures (depending on decoder setup).
- If using opaque tokens, the Resource Server must be able to reach the introspection endpoint with valid credentials.
- Tokens used against the Orders API must contain an audience and permissions accepted by the app, e.g., scope `orders.read`.

A token issued for another app or an ID token from an OIDC login is not automatically a valid access token for the Orders API.

### 10.2. Starting the Application

With Maven Wrapper on Unix-like systems:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

This command illustrates running the project after creating the build file and choosing the web stack. Startup may fail if configuration is missing, dependencies conflict, or issuer metadata is unreachable when discovery runs at startup.

### 10.3. Testing the Public Endpoint

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Expected output with the sample controller:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok"}
~~~

### 10.4. Testing a Protected Endpoint Without a Token

~~~bash
curl -i http://localhost:8080/api/orders/me
~~~

The Resource Server typically responds with:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Headers/body may differ depending on exception handling configuration and framework version. The goal of this test is to confirm the API protects the route rather than redirecting a normal Bearer API call to an OIDC login page.

### 10.5. Testing with a Valid Access Token

~~~bash
curl -i \
  -H "Authorization: Bearer <VALID_ACCESS_TOKEN>" \
  http://localhost:8080/api/orders/me
~~~

Replace `<VALID_ACCESS_TOKEN>` with an actual test token issued for the API by the issuer. With a token having a valid signature, issuer, lifetime, audience, and scope `orders.read`, the sample controller can return:

~~~json
{
  "subject": "user-42",
  "message": "Access token was accepted"
}
~~~

If the token is invalid or expired, the API normally returns **401**. If the token is authenticated but lacks `orders.read`, the API normally returns **403**. Clients must handle these two outcomes differently and should not infinitely refresh tokens upon receiving 403.

**Never place real tokens in URLs, source code, commits, or logs.** In a terminal, use environment variables or a secret manager rather than pasting tokens into shell history.

## 11. What to Configure Once the Project Runs

### 11.1. Validating Issuer, Audience, and Lifetime

A secure Resource Server must enforce:

- `iss`: the token must be issued by a trusted issuer.
- `aud`: the token must be intended for the receiving API.
- `exp` and `nbf`: the token must be valid in time per policy and clock skew.
- JWT signature/keys or opaque token status must be valid.
- Scopes/authorities and business permissions must match the operation.

Spring Security supports the relevant validators, yet **audience configuration and domain-specific rules must be explicitly defined** per system requirements. Never treat a validly signed JWT as a pass to call every API sharing the same issuer.

### 11.2. CORS and CSRF Are Two Separate Mechanisms

If a browser SPA on a different origin calls the API, configure **CORS** appropriately for allowed origins, headers, and methods. CORS controls whether a browser can read responses; it **does not replace bearer token authentication or API authorization**.

**CSRF** is a different risk, especially critical when browsers **automatically attach authentication cookies**. Only disable CSRF as shown in the example when the API truly relies on Bearer tokens explicitly attached by the client and does not rely on automatically sent auth cookies. Evaluate CORS and CSRF separately for both MVC and WebFlux.

### 11.3. Record-Level Access Control

If both Alice and Bob have `orders.read`, the Orders API must still check whether Alice is allowed to view Bob's order. Route-level authorization such as `hasAuthority("SCOPE_orders.read")` is only the initial gate; tenant, record, and business-state permissions belong in service/domain authorization.

### 11.4. Secrets and Environment Configuration

Never hardcode private keys, introspection client secrets, or tokens in the repository. Store credentials in a suitable secret management system and configure dev/staging/production separately. Issuer URLs must be stable, use HTTPS in operational environments, and follow trust policies.

### 11.5. System Observability

In production, monitor 401/403 rates, API latency, introspection latency (if used), JWKS discovery failures, downstream warnings, and I/O load. However, **never write raw access tokens, refresh tokens, or authorization headers** into logs or traces.

With WebFlux, also watch for blocking operations on the event loop, timeouts, and memory pressure from large pipelines. With Servlet, monitor thread pools, database connection pools, and downstream wait times.

## 12. Common Bootstrap Errors and How to Interpret Them

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Cannot inject `HttpSecurity`/`SecurityFilterChain` as expected | App is configured as reactive or security dependency is missing | Check web application type, starters, and use the matching security family |
| Cannot inject `ServerHttpSecurity`/`SecurityWebFilterChain` | Project is actually running Servlet MVC or missing WebFlux/reactive security | Check dependencies, web application type, and annotations/config |
| `Mono` is present but server is still MVC | WebFlux library is only on the classpath; Boot picked Servlet | Check actual starters and auto-detection rules |
| Every protected endpoint returns 401 | Missing token, wrong issuer/audience, expired, bad signature, or decoder misconfiguration | Check Authorization header, issuer, token type, JWK/introspection |
| 403 even when sending a token | Valid token lacking required authority/scope or business permission | Check scope claim, `SCOPE_` mapping, and record-level policies |
| App fails to start due to issuer | Metadata/JWKS unreachable or bad URI when discovery is required at startup | Check issuer URL, network, TLS, metadata, and JWK Set URI config |
| Abnormally high WebFlux latency under load | Blocking I/O on the event loop, slow downstream, or poor pipeline design | Inspect SDKs, repositories, schedulers, timeouts, and load tests |
| `SecurityContextHolder` empty inside reactive callbacks | Reactive context differs from synchronous ThreadLocal | Use `ReactiveSecurityContextHolder` or proper injection |
| Browser blocks request due to CORS | Origin/header/method not allowed | Configure CORS properly on the API while keeping auth/authorization |
| API uses login cookies yet disabled CSRF per example | Misapplied pure Bearer-token API assumption | Redesign CSRF for the actual cookie/session model |

Do not fix these issues by skipping signature verification, disabling all filters, or permitting all routes. Pinpoint the **active web stack**, the **active security chain**, and the **valid token type** issued by the issuer.

## 13. Three Typical Design Scenarios

### Scenario A — Order Management System with JPA

The app performs many CRUD operations, `@Transactional` work, JPA Repositories, and REST endpoints. The team is already comfortable with Spring MVC. The natural choice is:

- Spring MVC/Servlet starter.
- Resource Server starter.
- SecurityFilterChain, `HttpSecurity`, and issuer-based JWT/opaque-token validation.
- JPA/JDBC in the data access layer; per-order permission checks in services.

Users may sign in through a separate OIDC client; the Orders API only needs to authenticate incoming request access tokens.

### Scenario B — Aggregator API Combining Multiple Reactive Sources

The API handles dashboard requests and fans out concurrently to multiple HTTP backends, all integrated via `WebClient`/reactive SDKs. The system already uses reactive persistence and needs streaming. In that case, choose:

- WebFlux starter.
- Resource Server starter.
- `SecurityWebFilterChain`, `ServerHttpSecurity`, `ReactiveJwtDecoder`.
- `Mono`/`Flux` end-to-end across I/O, avoiding blocking SDK calls on the event loop.

JWTs must still satisfy the same issuer/audience/scope rules; using WebFlux does not automatically make tokens more secure.

### Scenario C — Existing MVC Backend Needing a Reactive HTTP Client

An MVC backend only needs `WebClient` to call another service. You can add `WebClient`/required libraries **without switching the server to WebFlux**. Keep the outbound client concerns separate from the inbound Resource Server role. If the backend acquires tokens itself for downstream APIs, that is an additional **OAuth2 Client** capability, independent of whether it is an MVC or WebFlux Resource Server.

## 14. Initialization Workflow for a New Project

An execution-goal-driven bootstrap workflow:

1. **Identify dominant request and I/O patterns**: blocking CRUD/JPA vs. reactive HTTP/DB, streaming, and many I/O-bound connections.
2. **Select a single target web stack**: MVC/Servlet or WebFlux; pick the matching starter and security family.
3. **Initialize the Spring Boot project** with entry point, Resource Server starter, and environment config.
4. **Pick the access token mechanism** per the Authorization Server contract: JWT/JWKS or opaque/introspection.
5. **Declare issuer, audience, authority mapping, and API permissions**. Avoid checking only the token while neglecting record-level permissions.
6. **Build the matching security chain**: `SecurityFilterChain` on Servlet or `SecurityWebFilterChain` on WebFlux.
7. **Create public and protected endpoints**, and test without a token, with a bad token, with missing scope, and with sufficient permissions.
8. **Implement matching synchronous or reactive service/data access**, then measure latency, load, and error handling in a realistic environment.

**Conclusion:** MVC/Servlet is the right fit for many synchronous business APIs; WebFlux shines when the system has clear reactive goals and end-to-end non-blocking I/O. In either case, a **Spring Security OAuth 2.0 Resource Server** holds the same security responsibility: **verify access tokens, enforce access permissions, and protect resources**. Choose your web stack based on the application's execution model, then use that stack's proper security APIs, decoders, and data libraries.
