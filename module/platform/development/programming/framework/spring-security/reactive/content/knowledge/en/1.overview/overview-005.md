# The Boundary Between Reactive Security and Servlet Security in Spring Security

## 1. Understanding the Boundary Accurately

Spring Security shares the same goals across both platforms: authenticating callers, checking permissions (authorization), protecting requests, and supplying identity to business code. However, **Servlet Security and Reactive Security are two different ways of integrating into the HTTP processing lifecycle**. The fact that controllers both use `@GetMapping`, both return JSON, or both accept JWTs does not make the two security pipelines interchangeable.

- **Servlet/MVC**: requests pass through the Servlet container, `jakarta.servlet.Filter`, `HttpServletRequest`/`HttpServletResponse`, and then `DispatcherServlet`. Spring Security uses `FilterChainProxy` and `SecurityFilterChain` beans.
- **Reactive/WebFlux**: requests pass through the WebFlux infrastructure with `ServerWebExchange`, `WebFilter`, and reactive publishers (`Mono`/`Flux`). Spring Security uses `WebFilterChainProxy` and `SecurityWebFilterChain` beans. WebFlux usually runs on Reactor Netty, though there is also an adapter for Servlet containers that support non-blocking I/O.
- **Same in security model**: `Authentication`, `GrantedAuthority`, least privilege, HTTP Basic, OAuth2/OIDC, JWT, access control, and CSRF protection. **Different in how they attach to requests, propagate context, and expose configuration APIs**.

A very easy sign to misread: a Spring MVC project that adds `spring-boot-starter-webflux` solely to use `WebClient` can still be a **Servlet** application. Under Spring Boot 3.x defaults, when both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, MVC is selected as the web application type; adding WebClient does not automatically switch server security to reactive. You must identify **which web stack is serving inbound requests**, rather than guessing from the presence of Reactor on the classpath.

## 2. How Do the Two Request Pipelines Work?

### Servlet

```text
HTTP request
  -> Servlet container
  -> DelegatingFilterProxy
  -> FilterChainProxy
  -> Matching SecurityFilterChain (Servlet Filters)
  -> DispatcherServlet / Spring MVC controller
  -> service / data
  -> HTTP response
```

Each `SecurityFilterChain` selects the Servlet Filters to run, such as authentication, CSRF, and authorization handling. `FilterChainProxy` selects the **first matching chain** in order; within a chain, filters execute in the defined security order. Servlet filters interact with Servlet API request/response objects, and the user context is normally bound to the current execution thread.

### Reactive

```text
HTTP request
  -> WebFlux HttpHandler
  -> WebFilterChainProxy
  -> Matching SecurityWebFilterChain (WebFilters)
  -> WebFlux handler / @RestController / RouterFunction
  -> Mono/Flux of service and data
  -> Asynchronous HTTP response
```

`SecurityWebFilterChain` uses `ServerWebExchangeMatcher` to select a chain; `WebFilter`s participate in the asynchronous processing flow. Each step's outcome may complete later on a different thread, so identity cannot rely on the assumption "one request = one fixed thread." In both stacks, if multiple chains exist, verify matcher scope and precedence order; making a chain too narrow can cause an endpoint to bypass the intended configuration.

## 3. API Map: Which Class Belongs to Which Stack?

| Concern | Servlet Security | Reactive Security |
|---|---|---|
| HTTP abstraction | `HttpServletRequest`, `HttpServletResponse` | `ServerWebExchange` |
| Security hook | Servlet `Filter`, `FilterChainProxy` | `WebFilter`, `WebFilterChainProxy` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Configuration DSL | `HttpSecurity` | `ServerHttpSecurity` |
| URL access rules | `authorizeHttpRequests`, `requestMatchers`, `anyRequest` | `authorizeExchange`, `pathMatchers`, `anyExchange` |
| Chain selection | `RequestMatcher` / `securityMatcher` | `ServerWebExchangeMatcher` / `securityMatcher` |
| Custom authentication | `AuthenticationManager`, `AuthenticationProvider` | `ReactiveAuthenticationManager` returning `Mono<Authentication>` |
| User lookup | `UserDetailsService` | `ReactiveUserDetailsService` returning `Mono<UserDetails>` |
| Runtime context | `SecurityContextHolder` (defaults to `ThreadLocal`) | `ReactiveSecurityContextHolder` (Reactor `Context`) |
| Web security context storage | `SecurityContextRepository`, often involving `HttpSession` | `ServerSecurityContextRepository`, can use `WebSession` |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| Common HTTP testing | `MockMvc` + `spring-security-test` | `WebTestClient` + `spring-security-test` |

This table describes **corresponding roles**, not that two interfaces are subtypes or castable to one another. For instance, injecting a `SecurityFilterChain` into a WebFlux configuration does not create a `WebFilter` that protects WebFlux requests.

## 4. Core Difference: SecurityContext and Execution Flow

### Servlet: thread-bound context

In a typical Servlet setup, Spring Security manages `SecurityContext` via `SecurityContextHolder` using the default `ThreadLocal` strategy. Inside code executing on the thread initialized by the security filters, you can read:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String username = authentication.getName();
```

*This is an illustrative Servlet snippet, not a standalone Java program.* You must ensure the caller is authenticated and `authentication` is not `null`. When work moves to an `Executor`, `@Async`, or a manually spawned thread, do not assume the context follows automatically; mechanisms such as `DelegatingSecurityContextExecutor` help propagate context with proper lifecycle management. Setting and clearing context must be managed by the security mechanism to avoid leaking identity across requests that reuse threads.

### Reactive: subscriber-bound context, not fixed to a thread

Reactive Security stores `SecurityContext` in the publisher chain's **Reactor Context**. Retrieve the identity inside the pipeline with:

```java
// Method inside a WebFlux bean/handler; not a standalone Java file.
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

Required imports: `reactor.core.publisher.Mono`, `org.springframework.security.core.context.SecurityContext`, `org.springframework.security.core.Authentication`, and `org.springframework.security.core.context.ReactiveSecurityContextHolder`. If no security context exists in the subscription, the publisher may complete empty; the API should configure a policy for unauthenticated requests in the security chain or handle `switchIfEmpty` as business logic requires.

`Mono`/`Flux` are descriptions of work; the code inside runs upon **subscribe**. `publishOn`/`subscribeOn` may switch threads, yet Reactor operators still propagate Reactor Context properly within the same subscription. Risks arise when calling `subscribe()` manually to detach a flow, jumping to a `CompletableFuture`/callback not wired to the context, or calling `SecurityContextHolder` directly in WebFlux expecting the right identity.

Attaching context for **tests or internal publishers** can be illustrated as follows:

```java
Authentication demo = new TestingAuthenticationToken(
    "alice", "unused", "ROLE_USER"
);

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(demo));

// If subscribed via block() in a standalone test program:
// name.block() -> "alice"
```

*This is an illustrative snippet requiring Reactor and Spring Security on the classpath; `block()` is only mentioned for tests or non-event-loop programs.* Do not fabricate an `Authentication` from a self-declared header or unauthenticated input to populate the context this way in production.

## 5. Comparing Security Configurations for the Same Policy

Common requirement: `/public` is open, `/admin` requires role `ADMIN`, all other endpoints require login. The two snippets below are **for two separate applications**, illustrating only the config class; imports and dependencies must match the stack.

**Servlet / Spring MVC:**

```java
@Configuration
@EnableWebSecurity
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

**Reactive / Spring WebFlux:**

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

In the examples: `@Configuration` and `@Bean` come from `org.springframework.context.annotation`; `Customizer` comes from `org.springframework.security.config`. Servlet uses `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.web.SecurityFilterChain`, `@EnableWebSecurity`. Reactive uses `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain`, `@EnableWebFluxSecurity`.

- `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority under the default naming convention. It does not check the plain string `ADMIN`; if an identity has OAuth scope authorities, use `hasAuthority("SCOPE_...")` or an appropriate conversion policy.
- Rules in `authorizeHttpRequests`/`authorizeExchange` are evaluated in order. Place specific rules before broad rules, and usually include `anyRequest`/`anyExchange` to explicitly decide what happens to the rest.
- `securityMatcher` at the chain level decides **whether a request enters that chain**, whereas `requestMatchers` or `pathMatchers` decide permissions **after the chain has been selected**. When multiple chains are needed, set appropriate `@Order` values and provide a fallback chain covering remaining endpoints.
- Changing `SecurityFilterChain` to `SecurityWebFilterChain` changes the integration structure, bringing changes to matchers, filters, authentication managers, context repositories, test fixtures, and I/O dependencies.

## 6. Hands-on WebFlux + Security Example (Java 17+)

This example is for **a Spring Boot 3.x / Spring Security 6.x project already configured with the Spring Boot plugin and Java 17+**. Add two dependencies to `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Do not include `spring-boot-starter-web` in this demo project so Spring Boot does not default to MVC. Create `src/main/java/example/security/ReactiveSecurityDemoApplication.java`:

```java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
```

Create `src/main/java/example/security/StatusController.java`:

```java
package example.security;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class StatusController {

    @GetMapping("/public")
    public Mono<String> publicStatus() {
        return Mono.just("public");
    }

    @GetMapping("/private")
    public Mono<String> privateStatus() {
        return Mono.just("private");
    }

    @GetMapping("/admin")
    public Mono<String> adminStatus() {
        return Mono.just("admin");
    }
}
```

Run using `./gradlew bootRun` (Windows: `gradlew.bat bootRun`) in a project with a compatible Gradle wrapper and Spring Boot plugin. Test using `curl.exe` on Windows or `curl` on macOS/Linux:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u reader:reader-demo http://localhost:8080/private
curl -i -u reader:reader-demo http://localhost:8080/admin
curl -i -u admin:admin-demo http://localhost:8080/admin
```

Expected **HTTP status codes** are `200`, `401`, `200`, `403`, `200` respectively; successful response bodies are `public`, `private`, and `admin` accordingly. All headers/stdout of `curl -i` are not guaranteed to be identical across versions/servers. `401` means unauthenticated; `403` here means authenticated with an insufficient role. The usernames/passwords above are for learning environments only: production uses a real identity source, stores secure hashes, never embeds passwords in source code, and enables HTTPS.

Because the controller returns `Mono<String>` on the WebFlux infrastructure, the response completes via reactive subscription. However, **returning `Mono` alone does not prove the system is non-blocking**: a synchronous JDBC/JPA call or `Thread.sleep` inside the pipeline can still block the event loop.

## 7. Authentication, Sessions, and CSRF: Same Goal, Different Adapters

**Authentication.** On Servlet, login handling typically passes through synchronous `AuthenticationManager` and `AuthenticationProvider` implementations; on WebFlux, the corresponding API uses `ReactiveAuthenticationManager` returning `Mono<Authentication>`. Looking up accounts by username uses `UserDetailsService` (Servlet) or `ReactiveUserDetailsService` (Reactive). When an identity backend only supports blocking I/O, wrapping the result in `Mono.just(...)` does not make it non-blocking; evaluate reactive drivers/clients or bounded blocking isolation.

**Login sessions.** Servlet typically binds sessions to `HttpSession` and an appropriate `SecurityContextRepository`. WebFlux provides `WebSession` and `ServerSecurityContextRepository` (e.g., `WebSessionServerSecurityContextRepository`). The two types of context repositories/sessions cannot be swapped arbitrarily; stateful cookie-based login differs from stateless bearer tokens in state storage and logout lifecycle. Do not equate "reactive" with "necessarily stateless": WebFlux can still use sessions and form login.

**CSRF.** Spring Security enables CSRF by default on both Servlet and WebFlux for state-changing HTTP methods. In WebFlux, `CsrfWebFilter` and WebFlux's token mechanism are used; tokens can be stored in `WebSession`. If the application relies on cookies/sessions automatically sent by browsers, CSRF protection remains necessary. Consider disabling it for API endpoints only after confirming the authentication model truly does not rely on browser-attached credentials vulnerable to CSRF, and after testing real flows; never disable it simply because you see the word "REST" or "WebFlux."

**OAuth2 Resource Server / JWT.** The same access token can be accepted by both types of services if **each service** configures verification of signature, issuer, expiration, and appropriate audience/permissions. A Servlet resource server uses the builder on `HttpSecurity` and `JwtDecoder`; WebFlux uses the builder on `ServerHttpSecurity` and `ReactiveJwtDecoder`. If a provider issues scope `read`, Spring Security commonly maps it to authority `SCOPE_read`; that is not `ROLE_read`. Having an external gateway authenticate requests does not mean downstream services can trust arbitrary self-declared headers: every trust boundary must verify tokens or use a trusted identity-propagation protocol.

Example **Reactive resource server** configuration (an additional configuration snippet replacing the demo's Basic mechanism when using real JWTs):

```java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/public").permitAll()
            .pathMatchers("/reports/**").hasAuthority("SCOPE_reports.read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Prerequisites: Spring Boot-managed OAuth2 Resource Server/Jose dependencies, a trusted issuer configuration such as `spring.security.oauth2.resourceserver.jwt.issuer-uri`, and appropriate claim/audience policies. This snippet cannot run standalone without those prerequisites; do not place it alongside the Basic demo as two `SecurityWebFilterChain` beans covering all URLs without defining clear ordering and matchers.

## 8. Method Security and Asynchronous Boundaries

Servlet method security typically uses `@EnableMethodSecurity`. In a WebFlux application, use `@EnableReactiveMethodSecurity`; the authorization mechanism retrieves the principal from Reactor Context. For Java methods following the reactive model, the return type must be a `Publisher` such as `Mono<T>` or `Flux<T>` so method security integrates properly with subscription:

```java
// Snippet inside a @Service bean of an application with
// @EnableReactiveMethodSecurity enabled; not a standalone class.
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> readSensitiveReport() {
    return Mono.just("sensitive");
}
```

You must import `org.springframework.security.access.prepost.PreAuthorize`, `reactor.core.publisher.Mono`, and enable `@EnableReactiveMethodSecurity` in configuration. URL-level and method-level controls should complement each other: URL rules block at the perimeter, while method rules protect business logic across multiple call sites. Do not assume Servlet's `@PreAuthorize` annotation will automatically share an equivalent lifecycle on a reactive bean returning regular synchronous values.

**Blocking boundaries.** On Servlet/MVC, synchronous I/O typically consumes a request thread. On WebFlux, a long blocking call on the Netty event loop can affect many concurrent requests. `Schedulers.boundedElastic()` can isolate certain transitional blocking adapters, yet still consumes threads and resources; it is a bounded compatibility workaround, not a substitute for evaluating reactive clients/drivers and system load. Never use `.block()` inside a web handler or reactive filter to fetch identity or call services while thinking Reactive Security is done right.

**Do not split subscriptions arbitrarily.** Instead of manually calling `subscribe()` in a controller and returning immediately (which easily drops error chains/context and results), **return the `Mono`/`Flux`** to the framework, and chain operators like `flatMap`, `map`, `onErrorResume` on the same pipeline. When work must be handed off to an external system outside Reactor, explicitly design how identity, authorization expiration, and task cancellation are handled.

## 9. Choosing the Right Stack and Migrating Configuration

Before adding or migrating security, answer these questions in order:

1. **What is the inbound server?** Spring MVC/`DispatcherServlet` or WebFlux handlers? Inspect dependencies and the actual web application type; do not infer solely from `WebClient` or controller return types.
2. **Which security chain processes requests?** Servlet selects `SecurityFilterChain` and `HttpSecurity`; WebFlux selects `SecurityWebFilterChain` and `ServerHttpSecurity`. Check matchers, `@Order`, and fallback chains.
3. **How does identity follow execution?** Servlet thread context and dedicated async mechanisms; WebFlux Reactor Context across subscriptions. Do not use `ThreadLocal` to infer principal across reactive operators.
4. **Are account/token sources non-blocking?** Choose `UserDetailsService`/`ReactiveUserDetailsService` and `AuthenticationManager`/`ReactiveAuthenticationManager` accordingly; do not hide blocking JDBC behind `Mono.just`.
5. **What are the session and CSRF semantics?** Cookies/sessions or bearer tokens; define rules for state-changing requests, login/logout, and context storage on the right stack.
6. **Are permissions enforced at both HTTP and method layers?** Review `hasRole`, `hasAuthority`, role prefixes, JWT scope mapping, anonymous/401/403 behavior, and fallback routes.
7. **Which testing tools apply?** Servlet typically uses `MockMvc` with `spring-security-test`; WebFlux uses `WebTestClient` integrated with Spring Security. Test unauthenticated, authenticated-unauthorized, and authorized cases.

### Application scenarios

- **An MVC app that only calls other services with WebClient:** the server is still Servlet; keep `SecurityFilterChain`. Consider Reactor context only within the dedicated WebClient flow; do not mistakenly configure `SecurityWebFilterChain` for inbound MVC.
- **A WebFlux gateway forwarding requests to MVC APIs:** the gateway configures reactive security, while backend APIs configure servlet security. Tokens/sessions do not magically "flow" across HTTP boundaries; pass credentials using a designed protocol and verify permissions in each service.
- **Migrating an MVC service to WebFlux:** replace the security chain/DSL, authentication adapters, session/context repositories, method-security mode, and tests; audit all persistence/network clients to locate blocking calls. Changing controller annotations while keeping old blocking infrastructure is not a complete migration.
- **Multiple chains for APIs and web pages:** a bearer-token API chain and a form-login chain are only safe when matchers/precedence are cleanly separated, with explicit policy for out-of-scope routes. Do not assume "later chains automatically append filters to earlier chains."

## 10. Verifying Behavior and Common Pitfalls

A minimal test matrix for the demo in Section 6:

| Case | Expectation |
|---|---|
| `GET /public` without credentials | `200` |
| `GET /private` without credentials | `401` under the demo's HTTP Basic configuration |
| `GET /private` as `reader` | `200` |
| `GET /admin` as `reader` | `403` |
| `GET /admin` as `admin` | `200` |
| POST with authenticated cookie but missing CSRF token | Rejected by CSRF protection when enabled and method is unsafe |
| JWT with invalid signature, wrong issuer, or expired (when using resource server) | Authentication rejected; no permissions granted from unverified claims |

In WebFlux, `WebTestClient` combined with `spring-security-test` can simulate a principal with `mockUser()`; when binding manually to ApplicationContext, apply the `springSecurity()` configurer to the client. Use real HTTP tests or integration test setups to validate the filter chain and responses, rather than only unit-testing a method returning `Mono`. With Servlet, `MockMvc` has corresponding integration support.

Common mistakes and how to recognize them:

- **Defining beans for the wrong stack:** configured `SecurityFilterChain`, yet WebFlux requests are not protected as expected; verify the actual server type and use `SecurityWebFilterChain` for WebFlux.
- **Using `SecurityContextHolder` inside reactive operators:** user is intermittently null or wrong across thread/transaction switches; read context from `ReactiveSecurityContextHolder` within the same subscription.
- **Calling `.block()` or blocking drivers on the event loop:** latency spikes, potential blocking-call errors, or degraded throughput; evaluate truly asynchronous APIs.
- **Confusing chain-level matchers with rule-level matchers:** a URL falls outside the chain so policy is never enforced; include a fallback chain and test boundary routes.
- **Confusing `ROLE_ADMIN` with `SCOPE_admin`:** authenticated requests still get `403` despite a valid token; inspect actual authorities and mapping policy.
- **Blanket-disabling CSRF:** cookie/session-based requests become vulnerable to forgery; analyze the credential model before adjusting.
- **Trusting external identity headers:** a client sends an unsigned `X-User` header and the backend treats it as authenticated; only trust identity data through verified mechanisms.
- **Using the wrong test harness:** WebFlux tests omit the security WebFilter or mock a principal only in a single method, so tests pass while real HTTP paths behave differently; test 401/403/200 through the proper web stack.

## 11. Self-Check

**Question 1.** An application has both `spring-boot-starter-web` and `spring-boot-starter-webflux` in order to call `WebClient`. Without forcing the application type, which kind of security chain must be configured for server endpoints?

**Answer:** Under Spring Boot 3.x defaults, the server is MVC/Servlet, so use `SecurityFilterChain` and `HttpSecurity`.

**Question 2.** Why is `SecurityContextHolder.getContext()` not the standard way to get the principal in WebFlux?

**Answer:** `SecurityContextHolder` defaults to `ThreadLocal`, whereas Reactive Security keeps context in the Reactor subscription. Use `ReactiveSecurityContextHolder.getContext()` or WebFlux's official injection mechanism.

**Question 3.** Does using `Mono` in WebFlux guarantee there is no longer any blocking?

**Answer:** No. A synchronous JDBC call or `block()` inside an operator still blocks the execution thread.

**Question 4.** A JWT bearer token has scope `reports.read`, yet a route requires `hasRole("reports.read")`. Why might this return 403?

**Answer:** Resource Server typically creates the authority `SCOPE_reports.read`, while `hasRole` checks for a role with the `ROLE_` prefix. You need an authority rule or converter matching the verified claims.

## Official Documentation for Deeper Study

- [Spring Security – Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security – Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security – Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security – Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Security – WebTestClient Authentication Tests](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
