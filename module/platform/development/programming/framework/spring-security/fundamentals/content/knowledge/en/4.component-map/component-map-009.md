# Shared Contracts and Reactive-Specific APIs in Spring Security

Spring Security supports both **Servlet/Spring MVC** applications and **reactive/Spring WebFlux** applications. Both models share many core concepts and data types such as `Authentication`, `GrantedAuthority`, `SecurityContext`, `UserDetails`, and `PasswordEncoder`, yet **request paths, context storage mechanisms, filter chains, authentication APIs, and authorization execution** have important differences.

If you have already learned `SecurityFilterChain`, `HttpSecurity`, `AuthenticationManager`, and `SecurityContextHolder` in Spring MVC, do not carry that configuration straight over to WebFlux. In WebFlux, the corresponding components are typically **`SecurityWebFilterChain`, `ServerHttpSecurity`, `ReactiveAuthenticationManager`, and `ReactiveSecurityContextHolder`**. The core principles—"authenticate identity, decide permissions, protect requests"—remain the same; the implementation must fit asynchronous processing pipelines built on Reactor.

This lesson maps out the contracts and APIs, explains **why the separation exists**, presents a complete Spring Boot WebFlux example, and guides testing. The scope is **Spring Security for reactive HTTP servers**; client-side `WebClient`, gateways, OAuth2, RSocket, and method security are introduced at relevant points without collapsing them into a single API system.

## 1. Two Web Stacks, Several Shared Security Concepts

### 1.1. How Does Servlet/Spring MVC Process Requests?

In a Spring MVC application, an HTTP request passes through the **Servlet Filter chain** and then reaches `DispatcherServlet`/Controller. Spring Security integrates via Servlet Filters using components such as:

- **HttpSecurity**: DSL for configuring access control, HTTP Basic, form login, CSRF, and Servlet filters.
- **SecurityFilterChain**: a set of Servlet Filters applied to matching requests.
- **AuthenticationManager**: authentication contract returning `Authentication` or throwing `AuthenticationException` in the synchronous model.
- **SecurityContextHolder**: access point for `SecurityContext`, usually backed by a `ThreadLocal`-based strategy on normal Servlet threads.
- **AuthenticationEntryPoint / AccessDeniedHandler**: decides the response when authentication is required or access is denied in Servlet flows.

`ThreadLocal` works conveniently when related processing stays on an appropriately managed thread. However, if work hops to another thread, an asynchronous callback, or a reactive pipeline, **you cannot assume `SecurityContext` from `ThreadLocal` follows every step automatically**.

### 1.2. How Does Spring WebFlux Process Requests?

Spring WebFlux uses **WebFilter**, **WebHandler**, and Project Reactor publisher types:

- **Mono<T>**: represents an asynchronous process emitting at most one value or completing empty.
- **Flux<T>**: represents a process emitting 0 to many values under Reactive Streams, including error and completion signals.
- **Reactor Context**: carries metadata along a subscriber chain, suited for propagating security context across properly designed reactive operators.
- **SecurityWebFilterChain**: security `WebFilter` chain matching WebFlux requests.
- **ServerHttpSecurity**: dedicated DSL for WebFlux.
- **ReactiveSecurityContextHolder**: reads or attaches `SecurityContext` via Reactor Context, rather than relying on `ThreadLocal` in reactive logic.

HTTP semantics **remain the same**: GET, POST, cookies, `Authorization`, 401, 403, CSRF, CORS, HTTPS. Reactivity changes programming APIs and execution lifecycles; it **never exempts** checking roles, object-level permissions, tenants, or business security flows.

~~~text
Servlet / Spring MVC                     Reactive / Spring WebFlux

HTTP request                             HTTP request
     |                                        |
Servlet Filter chain                      WebFilter chain
     |                                        |
Spring Security                           Spring Security
SecurityFilterChain                       SecurityWebFilterChain
HttpSecurity                              ServerHttpSecurity
     |                                        |
DispatcherServlet                        DispatcherHandler / WebHandler
     |                                        |
MVC Controller                           WebFlux Controller / Handler
     |                                        |
Data/service                             Reactive publisher: Mono / Flux
     |                                        |
HTTP response                            HTTP response
~~~

This diagram is high-level. An application may use other async mechanisms; it does not mean Servlet always stays on one thread or WebFlux never touches threads. What matters is that **security context and framework contracts are designed for the running stack**.

## 2. Shared Contracts and Data Types

The following types belong to **Spring Security Core** and carry meaning in both Servlet and reactive apps:

| Type/contract | Meaning | How is it shared? |
| --- | --- | --- |
| **Authentication** | Represents an authentication request/evidence or an authenticated identity, principal, credentials, authorities, and authenticated flag. | Both stacks use appropriate `Authentication` implementations. |
| **GrantedAuthority** | Represents a granted permission, e.g. `ROLE_USER` or `SCOPE_orders.read`. | Shared foundational authority type; policies decide interpretation. |
| **SecurityContext** | Holds the `Authentication` for the current security context. | Shared interface; **storage, restoration, and context propagation** differ. |
| **UserDetails** | User account model, password hash, authorities, and account status flags. | Can be used with `UserDetailsService` or `ReactiveUserDetailsService` respectively. |
| **PasswordEncoder** | One-way encoding and password hash matching. | Synchronous interface still usable in reactive systems; evaluate CPU cost. |
| **AuthenticationException** | Exception hierarchy for failed authentication cases. | Both models express auth failures via exceptions, though pipeline signaling differs. |
| **AccessDeniedException** | Indicates access was denied. | Can arise at authorization checkpoints in either stack. |
| **UsernamePasswordAuthenticationToken** | Common `Authentication` type for username/password authentication. | Can participate in both synchronous and reactive flows when used properly. |

Do not confuse **shared data types** with **how that data is accessed**. For example, `Authentication` is the exact same interface; yet in a reactive chain, you typically obtain the current identity via **`Mono<SecurityContext>`** and Reactor Context rather than calling `SecurityContextHolder.getContext()` and assuming it always holds the request's principal.

**Never trust client-asserted data as a valid `Authentication`.** Headers like `X-Role: ADMIN`, `userId` in a body, or a merely Base64-decoded JWT do not prove permission. Both Servlet and WebFlux must verify credentials via the configured mechanism before using authorities for authorization.

### 2.1. `ROLE_` and Scopes Share the Same Semantics

In Spring Security, **`hasRole("ADMIN")`** typically checks for authority **`ROLE_ADMIN`**, whereas **`hasAuthority("ADMIN")`** checks for the exact supplied authority. This rule holds for corresponding DSLs in both stacks.

With OAuth2 Resource Server, scopes can be represented as authorities such as **`SCOPE_orders.read`**, depending on the configured converter. Do not assume claims named `role` or `scope` always convert to identical authorities across all projects.

### 2.2. What Are Not Directly Interchangeable Shared Contracts?

- **AuthenticationManager** (synchronous) and **ReactiveAuthenticationManager** (reactive) serve the same goal yet **differ in API signatures and execution model**.
- **UserDetailsService** and **ReactiveUserDetailsService** are not the same interface. Both answer "find user by username", yet reactive returns **`Mono<UserDetails>`**.
- **SecurityContextHolder** and **ReactiveSecurityContextHolder** use different context-storage mechanisms; similar in purpose, not mechanically swappable.
- **SecurityFilterChain** is for Servlet; **SecurityWebFilterChain** is for WebFlux.
- **HttpSecurity** is for Servlet; **ServerHttpSecurity** is for WebFlux.

Sharing the word "Security" is not enough to choose an import. Always check **package, method signatures, and web stack** instead of guessing by similar names.

## 3. Comparison Table of Servlet and Reactive APIs

| Purpose | Servlet / Spring MVC | Reactive / Spring WebFlux | Key note |
| --- | --- | --- | --- |
| HTTP security configuration | **HttpSecurity** | **ServerHttpSecurity** | Two separate DSLs; do not mix imports. |
| Security chain | **SecurityFilterChain** | **SecurityWebFilterChain** | Servlet `Filter` differs from `WebFilter`. |
| Base filter | `javax`/`jakarta` Servlet Filter by generation | **org.springframework.web.server.WebFilter** | WebFlux uses non-blocking publisher APIs. |
| Chain-level request matching | `RequestMatcher` / `securityMatcher` | **ServerWebExchangeMatcher / securityMatcher** | Different request objects inspected. |
| URL rules | **authorizeHttpRequests / requestMatchers** | **authorizeExchange / pathMatchers** | Same intent, different DSL. |
| Catch-all rule | `anyRequest()` | **anyExchange()** | Both should have an intentional fallback. |
| Authentication | **AuthenticationManager** | **ReactiveAuthenticationManager** | Synchronous `Authentication` vs. `Mono<Authentication>`. |
| User lookup | **UserDetailsService** | **ReactiveUserDetailsService** | Shared `UserDetails`; different return wrapper. |
| In-memory users | `InMemoryUserDetailsManager` | **MapReactiveUserDetailsService** | Demo/testing only, not a production identity source. |
| Current context | **SecurityContextHolder** | **ReactiveSecurityContextHolder** | `ThreadLocal` vs. Reactor Context. |
| Save/restore context | `SecurityContextRepository` | **ServerSecurityContextRepository** | Request/response integration per stack. |
| Custom auth filter | Servlet authentication filters | **AuthenticationWebFilter** | Reactive filter handling publishers and reactive managers. |
| Start authentication | **AuthenticationEntryPoint** | **ServerAuthenticationEntryPoint** | e.g. 401/challenge or login redirect. |
| Access denial | **AccessDeniedHandler** | **ServerAccessDeniedHandler** | Handles 403 or other denial policies. |
| Exception translation | `ExceptionTranslationFilter` | **ExceptionTranslationWebFilter** | Converts certain exceptions into HTTP responses. |
| Method security | **@EnableMethodSecurity** | **@EnableReactiveMethodSecurity** | AOP and Reactor Context must work together. |
| HTTP testing | `MockMvc` | **WebTestClient** | Test the right stack and configured handlers. |

Recognize three distinct layers:

1. **Core contracts**: identity, authorities, security context, password hashing.
2. **Stack adapters**: filter chains, request matchers, HTTP configuration, handlers.
3. **Application integration**: reading principals, querying users/permissions, databases, message queues, and business logic.

Do not classify every type containing "Reactive" as a newer, better version of Servlet. They address **different execution models**, chosen based on application architecture.

## 4. ReactiveAuthenticationManager and ReactiveUserDetailsService

### 4.1. Synchronous Authentication

In Servlet, the core contract is:

~~~java
// Signature description only, not a standalone Java file.
Authentication authenticate(Authentication request)
        throws AuthenticationException;
~~~

An `AuthenticationManager` decides whether authentication evidence is valid and returns an appropriate `Authentication` or signals an error. `AuthenticationProvider`s can be composed inside `ProviderManager`.

### 4.2. Reactive Authentication

In WebFlux, the contract is:

~~~java
// Signature description only, not a standalone Java file.
Mono<Authentication> authenticate(Authentication authentication);
~~~

**ReactiveAuthenticationManager.authenticate(...)** returns a publisher:

- Emits an authenticated **Authentication** on success.
- Completes with **Mono.empty()** when the implementation cannot decide for that `Authentication` type.
- Emits a reactive error when authentication fails.

This is a major difference from returning `Authentication` immediately. Inside a reactive authentication filter, the framework subscribes/processes the pipeline by its own rules; you **should not call `subscribe()` or `block()` manually** just to extract `Authentication` in application code.

**ReactiveUserDetailsService** has the method:

~~~java
// Signature description only, not a standalone Java file.
Mono<UserDetails> findByUsername(String username);
~~~

`UserDetails` remains a shared core type. Yet user lookup can run via reactive databases or network services using Reactor. Implementations must emit completion/error signals per contract and never return `null` instead of a `Mono`.

Conceptual lookup example (**illustrative snippet requiring an existing reactive repository**):

~~~java
public Mono<UserDetails> findByUsername(String username) {
    return reactiveUserRepository.findByUsername(username)
        .map(account -> User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities())
            .disabled(!account.enabled())
            .build());
}
~~~

Never call blocking JDBC directly inside this method and wrap it in `Mono.just(...)`. **`Mono.just(repository.findByUsername(...))`** still executes the blocking call immediately when constructing the publisher. For an unavoidable blocking source, design proper isolation and schedulers; for true WebFlux systems, prefer non-blocking drivers/repositories whenever possible.

### 4.3. PasswordEncoder Is an Interesting Case

**PasswordEncoder** still has synchronous methods such as `encode(...)` and `matches(...)`. BCrypt is intentionally CPU-intensive and does not become "non-blocking" merely by wrapping it in a `Mono`.

In small demos, hashes can be created at startup. In high-traffic production systems, password-processing cost, schedulers, thread pools, concurrency limits, and brute-force defenses must all be evaluated. Never use reactive operators expecting CPU cost to vanish.

**Never use `User.withDefaultPasswordEncoder()` in real applications**, and never store plaintext passwords. Pick an appropriate `PasswordEncoder` and manage passwords and hash versions per system policy.

## 5. ReactiveSecurityContextHolder and Reactor Context

In Servlet, many examples use:

~~~java
// Servlet snippet; do not use to read the principal in a WebFlux pipeline.
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
~~~

This approach easily misleads when moving to WebFlux. A reactive publisher can resume on a different thread. **`ThreadLocal` is not a reliable mechanism for propagating security context across all Reactor steps**.

In WebFlux, use:

~~~java
// Illustrative snippet in code already using Project Reactor/Spring Security.
Mono<String> currentUserName =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

The current context is looked up in the **per-subscription Reactor Context**, not a global variable or permanent `ThreadLocal`.

### 5.1. Reading the Principal in a WebFlux Controller

A Controller can accept **`Mono<Principal>`** via Spring WebFlux parameter resolution:

~~~java
@GetMapping("/api/me")
public Mono<String> me(Mono<Principal> principal) {
    return principal.map(Principal::getName);
}
~~~

This is a **method fragment to place inside a `@RestController`**, using `java.security.Principal` and `reactor.core.publisher.Mono`. It leverages WebFlux integration to retrieve the principal attached to the request by the framework.

In a reactive service needing the context, use `ReactiveSecurityContextHolder`. When a stream runs outside an HTTP request (schedulers, message consumers, manually built publishers), **never automatically assume an HTTP request's security context exists**.

### 5.2. Attaching Authentication to a Mono Chain

When writing tests or proactive context integrations, the API provides:

~~~java
Mono<String> value = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );
~~~

This is only a **code snippet**; `authentication` must be a valid `Authentication` produced by a trusted mechanism. **`withAuthentication`** supplies a Reactor Context for that publisher branch; it does not forge valid credentials from client data, does not persist sessions, and does not mutate global context outside that branch.

Reactor reminders:

- **`subscribe`** triggers execution of most cold pipelines; most Controllers return `Mono`/`Flux` for the framework to subscribe.
- **`contextWrite`** attaches/transforms context over a subscription scope following Reactor propagation rules.
- **`publishOn`/`subscribeOn`** can switch threads; Reactor context propagates according to Reactor semantics, whereas arbitrary `ThreadLocal`s do not.
- Detaching a publisher from the request lifecycle, calling `subscribe` manually, bridging to non-Reactor callbacks, or using unintegrated libraries can break security assumptions. Test propagation on real paths.
- Never store `Authentication` in a static/global field across requests; that can leak data or mix identities across users.

## 6. ServerHttpSecurity and SecurityWebFilterChain

### 6.1. Familiar Servlet Configuration

A typical Servlet configuration looks like:

~~~java
// Spring MVC/Servlet configuration snippet; cannot be plugged directly into WebFlux.
@Bean
SecurityFilterChain servletSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

`HttpSecurity`/Servlet `SecurityFilterChain` types are **not** what WebFlux uses.

### 6.2. Corresponding WebFlux Configuration

~~~java
// WebFlux configuration snippet inside a @Configuration class.
@Bean
SecurityWebFilterChain webfluxSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public").permitAll()
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Specific differences:

- `HttpSecurity` → **ServerHttpSecurity**.
- `SecurityFilterChain` → **SecurityWebFilterChain**.
- `authorizeHttpRequests` → **authorizeExchange**.
- `requestMatchers` → **pathMatchers** for WebFlux URL paths.
- `anyRequest` → **anyExchange**.
- Corresponding filters/entry points live in **`web.server`** rather than Servlet web.

When a policy should apply only to a specific HTTP method, use the overload taking **`HttpMethod`**:

~~~java
.pathMatchers(HttpMethod.GET, "/api/public").permitAll()
~~~

**`permitAll()`** permits access at the authorization layer, which does not mean bypassing all security `WebFilter`s. If a client sends malformed credentials to a public URL, enabled authentication filters may still process those credentials and return an error before reaching `permitAll`.

### 6.3. Multiple SecurityWebFilterChains

An application can declare multiple `SecurityWebFilterChain` beans with **`@Order`** and **`securityMatcher(ServerWebExchangeMatcher)`**. Spring Security picks the matching chain in order. For instance, `/api/**` APIs using Bearer tokens while a website uses form login is a case needing clear separation.

If a chain matches only `/api/**` and you forget a fallback chain, other URLs risk **skipping the policy you intended**. Verify behavior across all application routes, admin paths, and Actuator endpoints if configured.

### 6.4. What Determines Choosing WebFlux vs. MVC?

**`spring-boot-starter-webflux`** provides the WebFlux stack. **`spring-boot-starter-web`** provides MVC. In Spring Boot, when both `web` and `webflux` starters are present, MVC is normally chosen as the default server application type; adding WebFlux solely to use `WebClient` **does not mean** the server has switched to reactive.

If the need is **making HTTP calls from an MVC application**, you can use `WebClient` as an HTTP client while still configuring the server with **`HttpSecurity`/`SecurityFilterChain`**. Only when the server itself is WebFlux do you use **`ServerHttpSecurity`/`SecurityWebFilterChain`** for reactive HTTP server flows.

Do not choose reactive merely to be "faster". Reactive suits systems with heavy asynchronous I/O, yet adds complexity when dependencies and databases remain blocking. Evaluate based on workload, library support, and operational readiness.

## 7. Filters, Authentication Entry Points, and Denied Handlers in Reactive

Reactive components use **`WebFilter`** or **`Server...`** prefixes/suffixes:

| Task | Reactive API | Output |
| --- | --- | --- |
| Inject security logic into requests | **WebFilter**, **AuthenticationWebFilter** | Executes work as `Mono<Void>` inside the `WebFilter` chain. |
| Extract/convert login credentials | **ServerAuthenticationConverter** | Converts `ServerWebExchange` into `Mono<Authentication>` in that flow. |
| Perform authentication | **ReactiveAuthenticationManager** | Returns `Mono<Authentication>`. |
| Authentication success | **ServerAuthenticationSuccessHandler** | Continues or decides response depending on filter/config. |
| Authentication attempt failure | **ServerAuthenticationFailureHandler** | Translates failure into a response or next action. |
| Initiate authentication | **ServerAuthenticationEntryPoint** | Usually sends 401/challenge or redirects to login. |
| Permission denied | **ServerAccessDeniedHandler** | Usually sends 403. |
| Translate authn/authz errors | **ExceptionTranslationWebFilter** | Routes to entry point or denied handler based on authentication state. |
| Authorize web exchange | **AuthorizationWebFilter** with reactive policy | Blocks before handler if permissions are insufficient. |

**Not every 401/403 passes through one shared handler.** For example, credential errors in `AuthenticationWebFilter`, CSRF errors, or authorization errors may be handled by different filters/handlers. Inspect the enabled chain and authentication mechanism.

Distinguish:

- Servlet's **AuthenticationEntryPoint** vs. WebFlux's **ServerAuthenticationEntryPoint**.
- Servlet's **AccessDeniedHandler** vs. WebFlux's **ServerAccessDeniedHandler**.
- **AuthenticationSuccessHandler/FailureHandler** for Servlet form login vs. **ServerAuthenticationSuccessHandler/ServerAuthenticationFailureHandler** in reactive authentication flows.

Returning the same 401 or 403 status does not make these interfaces interchangeable. Even when final HTTP responses match, signatures and request objects are completely different.

## 8. AuthorizationManager and Reactive Method Security

In Servlet, you encounter **`AuthorizationManager<RequestAuthorizationContext>`** and method authorization APIs. In WebFlux, Spring Security provides **`ReactiveAuthorizationManager`** and contexts tailored to web exchanges. Implementations can make decisions based on the `Authentication` publisher and the request/resource under evaluation.

For URLs, use the **`authorizeExchange`** DSL:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
)
~~~

This is an illustrative configuration snippet. In real apps, **URL rules do not understand ownership relationships for individual `orderId`s or tenants**. Service/domain layers must check permissions on data:

~~~text
Authenticated principal: customer-17
GET /api/orders/42
Service loads order 42 and its owner/tenant
Returns order only if current user is allowed to view that order
~~~

### 8.1. Protecting Reactive Methods

In WebFlux, enable **`@EnableReactiveMethodSecurity`** when method-level annotations are needed:

~~~java
// Configuration snippet, placed on a @Configuration class.
@EnableReactiveMethodSecurity
~~~

And reactive methods can be guarded with:

~~~java
// Method snippet inside a Spring bean, not standalone.
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminReport() {
    return Mono.just("report");
}
~~~

Key points to remember:

- This is the API for **reactive method security**, not an arbitrary alias for Servlet's `@EnableMethodSecurity`.
- Return types are typically **`Mono`/`Flux` or compatible publishers** so Spring Security can apply the reactive authorization pipeline.
- `Authentication`/context propagates via Reactor Context per supported integration.
- Method security relies on Spring AOP; **self-invocation** within the same bean can bypass the proxy. Test through real bean call paths.
- Annotations do not replace object-level permissions, data filtering controls, or testing for side effects.

## 9. Complete Example: Spring Boot 3.3.6 + WebFlux + Spring Security

Demo goal: run a **reactive web server** with a public endpoint, a protected endpoint, and an admin endpoint. This is a real WebFlux project without Servlet Controllers or Mockito.

**Requirements:** JDK 17+, Maven 3.9+, free port 8080. The example uses HTTP Basic and in-memory accounts for illustration. Run on localhost and never use demo passwords in real systems. In deployments over real networks, require HTTPS and proper credential management.

~~~text
reactive-security-demo/
  pom.xml
  src/main/java/com/example/reactivesecurity/
    ReactiveSecurityApplication.java
    ApiController.java
    SecurityConfig.java
  src/test/java/com/example/reactivesecurity/
    ReactiveSecurityTests.java
~~~

### 9.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-security-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
~~~

**Important:** `pom.xml` includes **`spring-boot-starter-webflux`** and **omits `spring-boot-starter-web`**. This keeps the example a WebFlux server instead of accidentally booting MVC when both starters exist.

### 9.2. ReactiveSecurityApplication.java

~~~java
package com.example.reactivesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
~~~

The package containing `main` is **`com.example.reactivesecurity`**, the same package as the beans, so Spring Boot scans the classes below.

### 9.3. ApiController.java

~~~java
package com.example.reactivesecurity;

import java.security.Principal;
import java.util.Map;
import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(p -> Map.of("user", p.getName()));
    }

    @GetMapping("/api/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("message", "admin"));
    }
}
~~~

The controller returns **`Mono`** to reflect WebFlux processing style. The `Mono<Principal>` parameter on `/api/me` receives the principal via Spring WebFlux's mechanism. **There are no manual role checks inside the Controller**: access policies are configured in `SecurityWebFilterChain`.

In JSON, field names `message`/`user` are stable, yet **field ordering inside a JSON object should never be treated as a contract** when multiple fields exist.

### 9.4. SecurityConfig.java

~~~java
package com.example.reactivesecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService reactiveUsers(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo-reader"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .roles("USER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Explanation:**

- **@EnableWebFluxSecurity** enables Spring Security WebFlux integration.
- **SecurityWebFilterChain** is the bean holding reactive HTTP policies.
- **ServerHttpSecurity** replaces `HttpSecurity`.
- **pathMatchers(HttpMethod.GET, ...)** restricts both path and method; a `POST` is not automatically `permitAll` just because `GET` is public.
- **authenticated()** requires only a valid identity, without demanding a specific role.
- **hasRole("ADMIN")** checks for authority `ROLE_ADMIN`.
- **anyExchange().denyAll()** denies exchanges not matching earlier rules.
- **httpBasic()** provides username/password authentication via HTTP Basic, convenient for simple testing.
- **ReactiveUserDetailsService** supplies user lookup through the reactive contract; `MapReactiveUserDetailsService` uses in-memory users.
- **PasswordEncoder** uses BCrypt hashing, never storing plaintext passwords as the `UserDetails` password field.

The demo only exposes **GET** endpoints and keeps default CSRF enabled. When adding POST/PUT/PATCH/DELETE, evaluate CSRF according to your authentication model, cookies, and clients. Never disable CSRF just because a POST test returned 403.

**This configuration is a learning sample.** In-memory accounts and demo passwords are unsuitable for production; HTTP Basic only Base64-encodes credentials, so HTTPS is mandatory over networks.

### 9.5. Running the Application

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

If port 8080 is free, the WebFlux app listens on `http://localhost:8080` by default. Test the cases with `curl` or `curl.exe` on Windows:

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u reader:demo-reader http://localhost:8080/api/me
curl.exe -i -u reader:demo-reader http://localhost:8080/api/admin
curl.exe -i -u admin:demo-admin http://localhost:8080/api/admin
~~~

**Expected results** (HTTP status codes and meanings; additional headers depend on version/configuration):

| Request | HTTP status | Response |
| --- | --- | --- |
| Anonymous `GET /api/public` | **200** | JSON with `message = public`. |
| Anonymous `GET /api/me` | **401** | Authentication required; HTTP Basic challenge. |
| `GET /api/me` with `reader`/`demo-reader` | **200** | JSON with `user = reader`. |
| `GET /api/admin` with `reader`/`demo-reader` | **403** | Has identity yet lacks `ROLE_ADMIN`. |
| `GET /api/admin` with `admin`/`demo-admin` | **200** | JSON with `message = admin`. |

The results reflect the **same security concepts** as Servlet: public, authenticated, role-based authorization. WebFlux's difference lies in the **`WebFilter` chain and how context is accessed/stored**, not a separate set of "reactive HTTP status codes".

Note: a public request carrying a malformed `Authorization` header may still trigger credential-error handling in the filter. When testing public routes, send the request **without credentials** to properly verify `permitAll()`.

## 10. Testing WebFlux with WebTestClient

Unlike `MockMvc` for Spring MVC, **`WebTestClient`** is the right tool for testing WebFlux. It can test reactive applications without opening a real port or by connecting to a live server, depending on how it is bound/configured.

Create **src/test/java/com/example/reactivesecurity/ReactiveSecurityTests.java**:

~~~java
package com.example.reactivesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveSecurityTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void privateEndpointRejectsAnonymous() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void privateEndpointAllowsValidBasicCredentials() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "demo-reader"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user").isEqualTo("reader");
    }

    @Test
    void privateEndpointRejectsWrongPassword() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void ordinaryUserCannotCallAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("reader", "demo-reader"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanCallAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "demo-admin"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("admin");
    }

    @Test
    void undeclaredRouteIsDenied() {
        client.get().uri("/api/unknown")
            .headers(h -> h.setBasicAuth("reader", "demo-reader"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Seven tests** verify anonymous access, invalid/valid credentials, user lacking a role, admin with sufficient role, and fallback `denyAll`. These are application-layer HTTP/security tests. Real systems also need tests through reverse proxies/TLS, object-level permissions, tenants, and write flows.

Notes on testing WebFlux:

- **`@AutoConfigureWebTestClient`** in Spring Boot 3.3 lives in package **`org.springframework.boot.test.autoconfigure.web.reactive`**.
- **`WebTestClient`** lives in **`org.springframework.test.web.reactive.server`**, distinct from `MockMvc`.
- To test method security with a mock principal, you can use **`SecurityMockServerConfigurers.mockUser(...)`** or matching JWT mutators; attach Spring Security test support to `WebTestClient` properly. Never apply Servlet's **`SecurityMockMvcRequestPostProcessors`** to `WebTestClient`.
- Mock users/test JWTs make testing **authorization** easier, yet do not prove real token validation works; include appropriate integration tests when using a real JWT decoder.
- For data-level authorization failures, tests must verify **no unauthorized response or side effects** occurred, not merely a 403 status.

## 11. Shared Authn/Authz Contracts, Different Reactive Execution

Some applications use WebFlux while still connecting to databases via JDBC or calling older security libraries that expose only synchronous APIs. You must distinguish:

**Shared data types** do not guarantee **non-blocking data sources or algorithms**.

Examples:

- **UserDetails** is a DTO/contract holding user info; by itself it is not blocking.
- **ReactiveUserDetailsService** returns `Mono<UserDetails>`, yet if its implementation calls blocking JDBC directly on the event loop, it still blocks the thread.
- **PasswordEncoder.matches(...)** is a synchronous method; BCrypt intentionally consumes CPU.
- **ReactiveAuthenticationManager** returns `Mono<Authentication>`, yet internally must call properly chosen providers/dependencies.
- **SecurityContext** is a core type; using `ReactiveSecurityContextHolder` is what fits Reactor pipelines.

A common mistake:

~~~java
// Anti-pattern: repository.findByUsername(...) is a blocking call.
Mono<UserDetails> user =
    Mono.just(blockingRepository.findByUsername("alice"));
~~~

**Why is this wrong?** The blocking method executes **right before** `Mono.just` receives its value, potentially blocking the event loop when building the publisher. Wrapping with `Mono` does not make it reactive.

One strategy when forced to interact with a blocking API (illustrative snippet):

~~~java
Mono<UserDetails> user =
    Mono.fromCallable(() ->
            blockingRepository.findByUsername("alice"))
        .subscribeOn(Schedulers.boundedElastic());
~~~

This example requires `Mono` and `reactor.core.scheduler.Schedulers` imports plus a real repository. Handle null/not-found results, errors, and timeouts per contract; **`boundedElastic`** is a temporary isolation measure, not a substitute for performance evaluation, connection limits, backpressure, or migrating to a non-blocking repository.

**Never call `block()` inside a reactive `WebFilter`/Controller** to "quickly grab `Authentication`". Doing so can stall request-processing threads and defeats reactive design. Compose pipelines with `map`, `flatMap`, `switchIfEmpty`, and intentional error handling.

## 12. ServerSecurityContextRepository and Sessions

**SecurityContext** remains a shared interface, yet storage/restoration mechanisms differ:

- Servlet has **`SecurityContextRepository`** integrating with Servlet requests/sessions per configuration.
- WebFlux has **`ServerSecurityContextRepository`** paired with `ServerWebExchange` and related `WebFilter`s.
- A reactive option like **`WebSessionServerSecurityContextRepository`** can use `WebSession`; **`NoOpServerSecurityContextRepository`** does not persist context across requests via that repository mechanism.
- Stateless Bearer token configurations typically authenticate credentials on each request and configure repository/session behavior intentionally.

**`ReactiveSecurityContextHolder` is not a session database.** It lets steps inside a publisher subscription see the context; persisting context across HTTP requests is a separate concern.

Depending on whether an app uses HTTP Basic, cookie sessions, or OAuth2 login, `SecurityContext` lifecycles differ. Never claim **WebFlux has no sessions by default**: WebFlux does support `WebSession`. Likewise, **`Mono` does not automatically mean stateless**.

Never store a principal globally or keep tokens in a static field. If your system needs user context across schedulers or message queues, design verified identity propagation with scoped permissions; never expect an HTTP request's Reactor Context to exist inside an independent background job.

## 13. CORS, CSRF, HTTP Basic, and Bearer in WebFlux

Protocol mechanisms remain critical:

- **CORS**: browsers enforce cross-origin policies; WebFlux provides matching CORS support. Browsers restrict JavaScript from reading responses, whereas `curl` and server-to-server clients do not enforce browser SOP/CORS. Never use CORS in place of authentication/authorization.
- **CSRF**: needs special care whenever browsers automatically send cookies/credentials. Spring Security WebFlux supports CSRF protection; when adding POST/PUT/DELETE, check request tokens and choose the right strategy. Never disable CSRF reflexively.
- **HTTP Basic**: credentials travel in `Authorization` Base64-encoded, **not secret encryption**. Use HTTPS in real environments.
- **Bearer token/JWT**: when enabling a reactive OAuth2 Resource Server, the server must verify signature or introspection, issuer, expiration, and audience/scope per trust requirements. Merely decoding a JWT payload is insufficient.
- **Role and object authorization**: an authenticated user can still be denied for lacking a role or not owning `orderId`. Both stacks must enforce the same business rules.
- **Security headers and HTTPS**: configure appropriately for your web environment, proxies, and gateways; do not assume WebFlux automatically solves all security concerns.

A WebFlux Resource Server configuration fragment using JWT looks like:

~~~java
// Illustrative snippet inside SecurityWebFilterChain.
// Requires spring-boot-starter-oauth2-resource-server and trusted issuer/JWK config.
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
)
~~~

Do not paste this into the HTTP Basic demo project without adding the dependency, issuer/JWK config, and matching policies. **JWT decoding/verification** in WebFlux can use **`ReactiveJwtDecoder`**; in Servlet it normally uses **`JwtDecoder`**. That is another example of the same goal with different reactive integration APIs.

## 14. Common Mistakes When Moving from MVC to WebFlux

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Importing **HttpSecurity** in a WebFlux server | Stack mismatch; missing beans or intended policies not applied. | Use **ServerHttpSecurity** and `SecurityWebFilterChain`. |
| Importing **SecurityFilterChain** instead of `SecurityWebFilterChain` | Creates a Servlet chain that does not protect WebFlux as intended. | Use the reactive filter chain. |
| Writing **authorizeHttpRequests** in reactive config | DSL API does not match. | Use **authorizeExchange** and `pathMatchers`. |
| Calling **SecurityContextHolder.getContext()** in a Reactor pipeline | May miss the principal after switching threads or lose context. | Use `ReactiveSecurityContextHolder` / principal injection. |
| Using blocking **UserDetailsService** in reactive flows without a plan | Blocks the event loop when querying DBs or external services. | Design **ReactiveUserDetailsService**, non-blocking sources, or proper blocking isolation. |
| Calling **.block()** in a `WebFilter` or Controller | Risk of thread starvation and reduced scalability. | Compose publishers with `map`/`flatMap`. |
| Confusing **WebClient** with a WebFlux server | Misconfigured stack just because WebFlux dependency exists for an HTTP client. | Identify whether the server runs Servlet or WebFlux via starters and runtime. |
| Assuming `Mono` is automatically secure or stateless | Skips permissions, context persistence, CSRF, and session concerns. | Design policies for requests, principals, and resources. |
| Forgetting **anyExchange().denyAll()** or a fallback chain | New endpoints may lack intended authorization. | Define a default policy and test unknown routes. |
| Using **MockMvc** to test a WebFlux chain | Does not test the actual reactive filters/server. | Use **WebTestClient** with security support. |
| Testing only 200 without object-level permissions | User A can read User B's data even though the API requires login. | Test cross-user/cross-tenant access at Service and API layers. |
| Returning arbitrary 401/403 without checking entry points | Clients cannot tell re-login from missing permissions; hard to debug. | Check `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`. |

One vital rule: **never copy a custom Servlet filter straight into WebFlux**. Servlet `Filter` handles `ServletRequest`/`ServletResponse`, whereas `WebFilter` handles `ServerWebExchange` and returns `Mono<Void>`. When extending, understand filter order, context, error pipelines, and avoid blocking.

## 15. How to Think When Designing Reactive Authentication

Suppose you are building a WebFlux API system using a database and an Identity Provider. You can sketch:

~~~mermaid
flowchart TD
    R["HTTP request"] --> F["SecurityWebFilterChain"]
    F --> C["AuthenticationWebFilter / matching auth mechanism"]
    C --> M["ReactiveAuthenticationManager"]
    M --> P["ReactiveUserDetailsService or decoder/provider"]
    P --> A["Authentication + GrantedAuthority"]
    A --> X["SecurityContext in Reactor Context"]
    X --> Z["AuthorizationWebFilter / Reactive authorization"]
    Z --> D{"Permitted?"}
    D -- "Yes" --> H["WebFlux handler → Mono/Flux"]
    D -- "No" --> N["Entry point / denied response"]
~~~

This is a **conceptual diagram**, not a byte-for-byte ordering of every `WebFilter`. For example, a request without credentials might skip calling `AuthenticationManager` and reach authorization, where the entry point challenges for authentication. There may be multiple chains, filters, decoders, and handlers.

When designing, answer these questions:

1. **Credential type**: cookie-session, HTTP Basic, JWT Bearer, opaque token, or mTLS?
2. **Identity source**: user DB, OAuth2/OIDC IdP, or service identity? Does the user store provide true reactive APIs?
3. **URL and method policy**: which endpoints are public, which require roles/scopes, and what is the default deny?
4. **Data-level permissions**: which user/tenant can read, edit, export, or refund a specific record?
5. **Saving and propagating context**: how is `SecurityContext` created, read inside publishers, persisted across requests, or passed to independent tasks?
6. **Performance**: are dependencies blocking, what is password-hashing cost, connection limits, timeouts, and backpressure?
7. **Testing**: `WebTestClient` checking 401/403/200, role and object tests, verifying no unauthorized side effects, and testing invalid/expired tokens with a Resource Server.
8. **Operations**: HTTPS, proxies, CORS/CSRF, no secrets in logs, and keeping Spring Security patches up to date.

## 16. Practice Exercises

**Exercise 1 — Classify types.** Group `Authentication`, `GrantedAuthority`, `UserDetails`, `SecurityContext`, `PasswordEncoder`, `HttpSecurity`, `ServerHttpSecurity`, `SecurityFilterChain`, and `SecurityWebFilterChain` into **shared core**, **Servlet-specific**, or **reactive-specific**. Explain why the same `SecurityContext` is accessed through two different mechanisms.

**Exercise 2 — Port a configuration.** Convert a Servlet policy with `GET /public` `permitAll`, `/admin` `hasRole("ADMIN")`, and default `authenticated` into a `ServerHttpSecurity` configuration using `authorizeExchange`. Point out where `pathMatchers` and `anyExchange` are required.

**Exercise 3 — Fix a context bug.** A developer calls `SecurityContextHolder.getContext().getAuthentication()` inside a WebFlux service and intermittently gets `null` after `publishOn`. Explain why `ThreadLocal` is not guaranteed and how to migrate to `ReactiveSecurityContextHolder` or `Mono<Principal>`.

**Exercise 4 — Blocking hazard.** Explain why `Mono.just(jdbcRepository.loadUser(...))` does not make JDBC non-blocking. Propose a reactive data source or proper blocking-isolation strategy, along with load and latency metrics to measure.

**Exercise 5 — Write tests.** Use `WebTestClient` to prove `GET /api/public` returns 200 anonymously, `GET /api/me` returns 401 anonymously, and account `reader` gets 200 on `/api/me` yet 403 on `/api/admin`.

**Exercise 6 — Object-level authorization.** Add endpoint `GET /api/orders/{id}` and explain why `authenticated()` is insufficient to prevent user A from reading user B's order. Write denial tests with two different users/tenants.

**Exercise 7 — Choose the stack.** A Spring Boot MVC app uses `WebClient` to call a partner API. Should `HttpSecurity` be replaced with `ServerHttpSecurity`? Explain by identifying the server stack from runtime and dependencies.

### Quick-Memory Checklist

- **Authentication, GrantedAuthority, SecurityContext, UserDetails, PasswordEncoder**: core concepts/types that can be shared.
- **HttpSecurity + SecurityFilterChain + Servlet Filter**: API set for Spring MVC/Servlet.
- **ServerHttpSecurity + SecurityWebFilterChain + WebFilter**: API set for Spring WebFlux.
- **AuthenticationManager** vs. **ReactiveAuthenticationManager**: direct result vs. `Mono<Authentication>`.
- **UserDetailsService** vs. **ReactiveUserDetailsService**: synchronous lookup vs. `Mono<UserDetails>`.
- **SecurityContextHolder** vs. **ReactiveSecurityContextHolder**: Servlet-suited `ThreadLocal`/strategy vs. Reactor Context.
- **AuthenticationEntryPoint/AccessDeniedHandler** vs. **ServerAuthenticationEntryPoint/ServerAccessDeniedHandler**: same HTTP security responsibilities, different interfaces.
- **@EnableMethodSecurity** vs. **@EnableReactiveMethodSecurity** and **MockMvc** vs. **WebTestClient**: always pick the matching stack.
- **Mono/Flux do not authenticate themselves, authorize themselves, or turn blocking code into non-blocking code**.
- **Use negative tests** to prove rules and object/tenant permissions genuinely work.

## References

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): configuring `ServerHttpSecurity` and `SecurityWebFilterChain`.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity` and Reactor Context.
- [Spring Security — Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): security support in `WebTestClient`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): WebFlux testing and `@AutoConfigureWebTestClient`.

**Version note:** API names and examples above target Spring Boot 3.3.6 / Spring Security 6.x. When using newer lines, consult the documentation for the **exact version in your project**, as configuration and class locations may change across releases.

## Conclusion

Spring Security shares a common set of contracts for **identity, authorities, `SecurityContext`, and passwords**, while providing a dedicated API suite for the reactive model to protect requests flowing through **`WebFilter` and Reactor publishers**. Understanding the corresponding pairs—**`HttpSecurity`/`ServerHttpSecurity`, `SecurityFilterChain`/`SecurityWebFilterChain`, `AuthenticationManager`/`ReactiveAuthenticationManager`, `SecurityContextHolder`/`ReactiveSecurityContextHolder`**—helps you read architectures and avoid mixing configurations across the two stacks. Whether choosing Spring MVC or WebFlux, applications must still verify credentials, enforce resource-level authorization, protect HTTP, preserve the right user context, and prove policies with tests.
