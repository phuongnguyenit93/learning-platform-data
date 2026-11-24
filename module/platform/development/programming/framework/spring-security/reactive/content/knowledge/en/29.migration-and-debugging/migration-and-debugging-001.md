# Migrating from HttpSecurity and SecurityFilterChain to ServerHttpSecurity and SecurityWebFilterChain

## 1. Goals and Boundaries of the Migration

In Spring Security, the security configurations of a Spring MVC/Servlet application and a Spring WebFlux application handle the same kinds of requirements, such as user authentication, URL-based authorization, HTTP Basic, OAuth2 Resource Server, CSRF, and access-denied handling. However, they run on **two different execution models**:

- **Servlet:** requests pass through `jakarta.servlet.Filter`; the security chain is declared with `HttpSecurity` and produces a `SecurityFilterChain`. The processing flow is typically tied to a Servlet request and a synchronous model.
- **Reactive WebFlux:** requests pass through `org.springframework.web.server.WebFilter`; configuration uses `ServerHttpSecurity` and returns a `SecurityWebFilterChain`. Security information is attached to the Reactor Context, and asynchronous authentication/authorization operations can return a `Mono`.

A proper migration means translating **the security contract and how components are wired into the reactive pipeline**, not merely renaming classes. After migrating, the goals are: the same endpoints require the same permission levels, unauthenticated users cannot access protected resources, authenticated users without sufficient permissions are denied, I/O steps do not block the event loop, and login state/CSRF/OAuth2 still satisfy the intended architecture.

This lesson uses **Spring Boot 3.3, Spring Security 6.x, and Java 17+** as its illustrative baseline. An application should run only the security stack matching its actual web application type. Importing reactive classes into a project that still runs MVC does not by itself turn the project into WebFlux.

## 2. Key API Migration Map

| Responsibility | Servlet/MVC | Reactive/WebFlux | What to preserve or verify |
| --- | --- | --- | --- |
| Enable web security | `@EnableWebSecurity` | `@EnableWebFluxSecurity` | Matches the application type and context. |
| HTTP configuration object | `HttpSecurity` | `ServerHttpSecurity` | Do not cast or directly adapt between the two DSLs. |
| Exposed chain bean | `SecurityFilterChain` | `SecurityWebFilterChain` | One matching chain per request, accounting for ordering when multiple chains exist. |
| Security filter | `Filter` / `FilterChainProxy` | `WebFilter` / `WebFilterChainProxy` | A Servlet Filter does not execute as a WebFilter. |
| Define URL rules | `authorizeHttpRequests(...)`, `requestMatchers(...)` | `authorizeExchange(...)`, `pathMatchers(...)` | Preserve specific-to-broad rule ordering. |
| Select chain by request | `securityMatcher(...)` | `securityMatcher(ServerWebExchangeMatcher)` | Distinct from authorization rules inside the chain. |
| Custom request matcher | `RequestMatcher` | `ServerWebExchangeMatcher` | WebFlux uses `ServerWebExchange` instead of `HttpServletRequest`. |
| Authentication manager | `AuthenticationManager` | `ReactiveAuthenticationManager` | The reactive path returns `Mono<Authentication>`. |
| User lookup | `UserDetailsService` | `ReactiveUserDetailsService` | Do not place blocking JDBC calls onto the event loop. |
| Custom authorization rule | `AuthorizationManager<RequestAuthorizationContext>` | `ReactiveAuthorizationManager<AuthorizationContext>` | The reactive decision is `Mono<AuthorizationDecision>`. |
| JWT Resource Server | `JwtDecoder` | `ReactiveJwtDecoder` | Preserve issuer/audience/keys, and migrate custom converters if any. |
| Store/read SecurityContext | `SecurityContextHolder`, `SecurityContextRepository` | `ReactiveSecurityContextHolder`, `ServerSecurityContextRepository` | Reactor Context differs from thread-local storage. |
| Request context | `HttpServletRequest`/`HttpServletResponse` | `ServerWebExchange`/`ServerHttpRequest`/`ServerHttpResponse` | Migrate handlers/filters that use the Servlet API. |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` | Protected methods must follow the appropriate reactive contract. |
| Web security testing | `MockMvc` | `WebTestClient` | Test success, unauthorized, and forbidden cases. |

**Two pairs never to confuse:** `HttpSecurity.build()` creates a `SecurityFilterChain`; `ServerHttpSecurity.build()` creates a `SecurityWebFilterChain`. Method names are often similar (`httpBasic`, `csrf`, `oauth2ResourceServer`), but the parameter types and SPIs differ; MVC code cannot be copied verbatim into WebFlux.

## 3. Migrating a Simple URL Rule Configuration: Before and After

Suppose both versions need the same policy:

- `GET /public/ping`: permitted for everyone.
- `GET /api/hello`: requires authentication.
- `GET /api/admin`: requires the `ROLE_ADMIN` authority.
- All remaining endpoints: require authentication.

### 3.1. Servlet/MVC Version Before Migration

Illustrative file `ServletSecurityConfig.java`, used only in a Spring MVC project with `spring-boot-starter-web` and `spring-boot-starter-security`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(rules -> rules
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

`hasRole("ADMIN")` checks the `ROLE_ADMIN` authority using the default prefix; `hasAuthority("ADMIN")` checks the exact string `"ADMIN"` and is not equivalent. If the system uses an OAuth2 JWT scope such as `SCOPE_admin`, use a rule matching that scope rather than blindly replacing it with `hasRole`.

### 3.2. Reactive WebFlux Version After Migration

Illustrative file `ReactiveSecurityConfig.java`, used only in a WebFlux project with `spring-boot-starter-webflux` and `spring-boot-starter-security`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(rules -> rules
                        .pathMatchers("/public/**").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Part-by-part comparison:

1. `@EnableWebSecurity` → `@EnableWebFluxSecurity`.
2. Bean parameter `HttpSecurity` → `ServerHttpSecurity`.
3. Return type `SecurityFilterChain` → `SecurityWebFilterChain`.
4. `authorizeHttpRequests` → `authorizeExchange`.
5. `requestMatchers` → `pathMatchers`; `anyRequest` → `anyExchange`.
6. `httpBasic` keeps a similar name, but is configured on the reactive DSL.
7. The reactive bean in this example **does not declare `throws Exception`**, because `ServerHttpSecurity.build()` does not have the same checked-exception contract as `HttpSecurity.build()`.

Do not place both of these example classes in the same project to "see which one runs": they are **two options belonging to two separate stacks**. Bring only the reconciled policies over into the target WebFlux configuration.

## 4. A Runnable WebFlux Application Example and Self-Verification

To see observable differences, here is a minimal WebFlux application: expose one public route, protect one route, and deny a route requiring the ADMIN role. The example uses HTTP Basic and an in-memory user **for practice only**; production applications must replace them with a secure identity source and password encoder.

### 4.1. Dependencies in a Spring Boot Project with Plugin/BOM Configured

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

In the target WebFlux module, verify that `spring-boot-starter-web` or unintended transitive MVC dependencies are absent. When both Spring MVC and WebFlux are present, Spring Boot normally selects MVC. You can verify via the dependency tree and startup web application type logs; `spring.main.web-application-type=reactive` is an override switch when there is a clear reason, but it does not replace resolving incompatible dependencies or configurations.

### 4.2. File `src/main/java/demo/ReactiveSecurityDemoApplication.java`

This is **a single Java file that compiles in the Boot WebFlux project above**; two package-private classes can reside in the same file as the main public class.

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(rules -> rules
                        .pathMatchers("/public/**").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}demo-pass")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/hello")
    Mono<String> hello() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> "hello " + ctx.getAuthentication().getName());
    }

    @GetMapping("/api/admin")
    Mono<String> admin() {
        return Mono.just("admin");
    }
}
```

Explanation of the design choices in the sample:

- `MapReactiveUserDetailsService` is the reactive equivalent of an in-memory user store. `{noop}` matches passwords in plaintext, **for demo use only**; for real users, store proper hashes and use a `PasswordEncoder`.
- `httpBasic` provides a Basic authentication challenge. Disable `formLogin` in this API example to avoid confusion with login-page redirects; for browser applications with form login, preserve the appropriate login flow and CSRF protection.
- `ReactiveSecurityContextHolder.getContext()` reads authentication info from the **Reactor Context when the publisher is subscribed**. Avoid replacing it with `SecurityContextHolder.getContext()` and assuming thread-local always holds across every event loop.
- All handlers return `Mono<String>`, never call `block()`, and perform no synchronous I/O.

Run with the project wrapper (already configured with the Boot plugin, dependency management, and compatible Java toolchain):

```bash
./gradlew bootRun
```

Send requests to observe behavior (assuming the application listens on localhost:8080):

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/hello
curl -i -u learner:demo-pass http://localhost:8080/api/hello
curl -i -u learner:demo-pass http://localhost:8080/api/admin
```

Expected results:

| Request | HTTP status | Notable body | Reason |
| --- | --- | --- | --- |
| `GET /public/ping` without credentials | `200` | `pong` | `permitAll`. |
| `GET /api/hello` without credentials | `401` | Depends on error handling | Missing authentication. |
| `GET /api/hello` with HTTP Basic `learner` | `200` | `hello learner` | Authenticated. |
| `GET /api/admin` with HTTP Basic `learner` | `403` | Depends on error handling | User has `ROLE_USER`, lacks `ROLE_ADMIN`. |

Do not assume HTTP header output is identical across all runtime versions; status codes and success bodies are what to verify. HTTP Basic must only be transmitted over HTTPS in real environments.

### 4.3. Integration Testing with `WebTestClient`

File `src/test/java/demo/ReactiveSecurityDemoApplicationTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveSecurityDemoApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicAndProtectedRoutesKeepTheirPolicies() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");

        client.get().uri("/api/hello")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/hello")
                .headers(headers ->
                        headers.setBasicAuth("learner", "demo-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("hello learner");

        client.get().uri("/api/admin")
                .headers(headers ->
                        headers.setBasicAuth("learner", "demo-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Run `./gradlew test`. These test requests verify **behavior from HTTP down to the controller**, helping catch wrong chains, wrong rules, status changes, or lost context propagation. When using `@WebFluxTest` instead of an integration test, import the relevant security configuration and ensure `WebTestClient` actually applies the Spring Security configuration before interpreting results.

## 5. Migrating Multiple Chains: Separating Chain Selection from Authorization Decisions

A Servlet application often has multiple `SecurityFilterChain` beans, such as one chain for APIs and one chain for the UI. In WebFlux, you still must determine **which chain applies to a request first**, and only then apply the rules inside that chain.

- `http.securityMatcher(...)` scopes the **entire chain**.
- `http.authorizeExchange(...).pathMatchers(...)` makes **authorization decisions inside the selected chain**.
- With multiple `SecurityWebFilterChain` beans, the framework evaluates them in `@Order` sequence and picks the **first matching chain**. A lower-priority chain is not evaluated afterwards to "supplement" rules for the already selected chain.
- Always include a catch-all chain with an explicit policy so no route falls outside every chain.

Illustrative two-chain WebFlux example (place these beans inside an `@Configuration @EnableWebFluxSecurity` class, in a project with the corresponding authentication mechanisms):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(rules ->
                    rules.anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain otherChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(rules -> rules
                    .pathMatchers("/public/**").permitAll()
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

This snippet shows **two bean methods to insert into a configuration class**, not a standalone runnable Java file. When a request hits `/api/orders`, `apiChain` matches first; for `/public/ping`, `otherChain` handles it. Changing `@Order` or placing the catch-all at higher priority can prevent the API chain from ever running. If the system uses session/form login on the web chain and Bearer tokens on the API chain, preserve **separation between mechanisms** during migration instead of accidentally enabling every login method on every route.

## 6. Authentication: Do Not Port Synchronous Components Directly

### 6.1. Username/Password, HTTP Basic, and Custom Authentication

For Servlet, security may use synchronous `AuthenticationManager` and `UserDetailsService`. In WebFlux, the corresponding SPIs are typically `ReactiveAuthenticationManager` and `ReactiveUserDetailsService`. The key difference is that authentication can involve reactive network/DB calls and return `Mono<Authentication>`.

API shape illustration:

```java
// Illustrates SPI signatures, not a standalone implementation.
Mono<Authentication> authenticate(Authentication input); // reactive
UserDetails loadUserByUsername(String username);        // servlet/blocking
Mono<UserDetails> findByUsername(String username);      // reactive
```

The exact method on `ReactiveUserDetailsService` is `findByUsername(String username)`; the method on `UserDetailsService` is `loadUserByUsername(String username)`. If the legacy project has a custom `AuthenticationProvider`, evaluate migrating it to a reactive manager or a controlled adapter; do not keep a synchronous DAO and call it directly inside the reactive pipeline. If a synchronous adapter cannot be eliminated immediately, isolate the blocking work on an appropriate scheduler, bound concurrency, measure load capacity, and plan the migration to non-blocking drivers/APIs.

For custom header-based authentication, `OncePerRequestFilter` or `jakarta.servlet.Filter`/`javax.servlet.Filter` are Servlet constructs. In WebFlux, register a `WebFilter` or Spring Security reactive components such as `AuthenticationWebFilter`, positioned at the appropriate `SecurityWebFiltersOrder`. A custom `WebFilter` that merely inspects a header and delegates `chain.filter(exchange)` **does not establish authentication by itself**. It must integrate properly with `ReactiveAuthenticationManager` and `ServerSecurityContextRepository`/Reactor Context, and ensure the filter neither drops context nor responds early with wrong error codes.

### 6.2. JWT/Opaque Tokens and OAuth2

When migrating an **OAuth2 JWT Resource Server**, the high-level DSL shifts from:

```java
// Servlet:
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));

// Reactive:
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

Even though the DSL looks identical, Servlet typically uses `JwtDecoder` while WebFlux uses `ReactiveJwtDecoder`. If the legacy app customized validators (`iss`, `aud`, `exp`), claim-to-authority mapping, key rotation, or Bearer error handling, those customizations must be migrated and re-verified accordingly. Never assume that because `jwt(...)` compiles, the full behavior is equivalent.

With Spring Boot Resource Server, issuer configuration can keep the same property shape:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/issuer
```

The URL above is only an example and must be replaced with the real issuer. JWT scopes are typically mapped to authorities prefixed with `SCOPE_`; if Servlet rules used `hasAuthority("SCOPE_reports.read")`, verify that reactive retains the exact same authority names. For **opaque tokens**, the SPI to examine is `ReactiveOpaqueTokenIntrospector`—do not mechanically drop in a Servlet `OpaqueTokenIntrospector` bean as a substitute. OAuth2 Login/OIDC, refresh tokens, and authorized clients also have distinct reactive clients, repositories, and services; do not assume JWT Resource Server covers the OAuth2 Login flow.

### 6.3. SecurityContext and Principal

In Servlet, this pattern is common:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
String username = authentication.getName();
```

In WebFlux, perform the equivalent **inside the reactive pipeline**:

```java
Mono<String> username =
        ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
```

Reactor can switch threads on `publishOn`/`subscribeOn`, so relying on thread-local `SecurityContextHolder` or custom `ThreadLocal` variables causes disappearing principals or context leakage. In controllers, Spring WebFlux principal injection can be used where appropriate; in reactive services, pass required identity data explicitly or use `ReactiveSecurityContextHolder`. Never cache `Authentication` in static fields or global state across requests.

If the application has session-backed login, compare the old design against `ServerSecurityContextRepository` and WebFlux `WebSession`; do not copy `HttpSessionSecurityContextRepository` over. If an API is intentionally stateless, consider `NoOpServerSecurityContextRepository` when appropriate for the authentication mechanism and business requirements—do not strip sessions merely because the word "reactive" appears.

## 7. Advanced Authorization and Method Security

For HTTP-method-based access rules, WebFlux can use `pathMatchers(HttpMethod.GET, "/api/reports/**")`, followed by write rules below. Specific rules must precede `anyExchange`. For data-ownership rules, a custom Servlet `AuthorizationManager` must be migrated to `ReactiveAuthorizationManager<AuthorizationContext>`. Its return type is `Mono<AuthorizationDecision>`; user-specific database or permission queries should be reactive or properly isolated.

Illustrative snippet **inserted inside the `authorizeExchange` lambda**, assuming an `accessService.canRead(username, id)` service returning `Mono<Boolean>`:

```java
.pathMatchers("/api/reports/{id}")
.access((authentication, context) ->
        authentication.flatMap(user ->
                accessService
                        .canRead(user.getName(),
                                context.getVariables().get("id"))
                        .map(AuthorizationDecision::new)))
```

This snippet illustrates policy composition and is **not a standalone runnable class**. Behavior when the principal is empty, the service errors, or the publisher completes empty must be handled explicitly; do not accidentally turn an empty result into implicit access. This hook shows where to apply the check; `canRead` must verify real permissions from a trusted source rather than comparing an arbitrary client-supplied ID alone.

For `@PreAuthorize` on services, WebFlux needs reactive method security enabled:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
class ReactiveMethodSecurityConfig {
}
```

Servlet `@EnableMethodSecurity` is not an equivalent substitute for Reactor Context. For reactive method security flows, return types should be `Mono`/`Flux` or supported reactive types; watch for synchronous methods and self-invocation bypassing proxies. Rules at both the HTTP layer and method layer may still be needed; reconfiguring only the HTTP layer does not guarantee all existing `@PreAuthorize` checks remain active.

## 8. CSRF, CORS, Login, Session, and HTTP Errors During Migration

### CSRF

Spring Security WebFlux includes CSRF protection; do not disable CSRF automatically just because the server uses WebFlux. For browsers relying on cookies/sessions, continue protecting state-changing operations (`POST`, `PUT`, `DELETE`, etc.) and issuing tokens via the reactive mechanism. For APIs that only accept Bearer tokens in the `Authorization` header and do not rely on browser-sent ambient credentials, disabling CSRF may be considered **for the architectural scope truly not exposed to CSRF**, after evaluating the auth flow and endpoints:

```java
// Place only when the API's security requirements allow it.
http.csrf(csrf -> csrf.disable());
```

Do not add this line blindly to every migration. In WebFlux, `ServerCsrfTokenRepository`/`CsrfWebFilter` and cookie/header CSRF token handling differ from several Servlet APIs; if an SPA uses cookies, verify token storage and BREACH protection behavior.

### CORS

Preflight `OPTIONS` requests usually carry no credentials. Verify CORS using WebFlux configuration (`CorsWebFilter`/reactive CORS config or integration via the security DSL) and test requests from real origins. Do not copy Servlet `CorsFilter`, `HttpServletRequest`, or a `CorsConfigurationSource` from the wrong package into the reactive pipeline. CORS **does not replace authorization**: an allowed origin does not mean a user is authorized to call the API.

### Login, Logout, and Session

For browsers, verify login/logout URLs, redirect pages, cookies (`SameSite`, `Secure`, `HttpOnly`), session timeout, CSRF, saved requests, and success/failure handlers. For HTTP Basic/Bearer, confirm whether stateless or session-backed mode is configured consistently. Do not automatically enable form login on a JSON API if clients expect `401`; equally, do not disable form login if the product still needs browser sessions.

### 401, 403, and 302

- `401 Unauthorized`: the request lacks valid credentials; HTTP Basic/Bearer typically sends a challenge.
- `403 Forbidden`: authentication is valid, but permissions are insufficient (subject to entry point or anonymous configuration exceptions).
- `302 Found`: may be a redirect to a form login page in a browser flow, which differs from what an API client expects.

When customizing error responses, WebFlux uses reactive interfaces such as `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler` instead of their Servlet counterparts. Do not mix handlers written for `HttpServletResponse` into WebFlux. Compare error bodies, content types, and `WWW-Authenticate` headers across both unauthenticated and forbidden cases.

## 9. Step-by-Step Execution Checklist in a Real Project

1. **Lock down the current policy:** list all routes, HTTP methods, role/scope permissions, public routes, multiple chains, form login, OAuth2, sessions, CSRF/CORS, method security, and custom filters. Confirm behavior from existing Servlet tests before migrating.
2. **Confirm the WebFlux runtime:** choose `spring-boot-starter-webflux`; inspect the dependency tree to remove unintended MVC/Servlet servers; verify the app actually boots in reactive mode.
3. **Create the new configuration:** replace `@EnableWebSecurity`/`HttpSecurity`/`SecurityFilterChain` with `@EnableWebFluxSecurity`/`ServerHttpSecurity`/`SecurityWebFilterChain`; migrate `authorizeHttpRequests` to `authorizeExchange` with equivalent rules.
4. **Preserve chain selection and ordering:** migrate `securityMatcher`, `@Order`, catch-all chains, and public routes; verify "first matching chain" for overlapping paths.
5. **Migrate authentication components:** choose the appropriate `ReactiveAuthenticationManager`, `ReactiveUserDetailsService`, `ReactiveJwtDecoder`/opaque introspector, and reactive OAuth2 components; verify authorities and error mapping.
6. **Migrate custom security filters/handlers:** replace Servlet Filter APIs with WebFilter/reactive SPIs; verify filter order, Reactor Context, error responses, and non-blocking event-loop behavior.
7. **Review browser protections:** keep CSRF, CORS, form login, logout, cookies/sessions, and redirects intact; do not turn off protections en masse when switching stacks.
8. **Migrate method security:** enable `@EnableReactiveMethodSecurity` and test `@PreAuthorize`/`@PostAuthorize` on reactive methods.
9. **Write before–after matrix tests:** public/anonymous, authorized user, under-privileged user, invalid/expired token, missing/valid CSRF, CORS preflight, browser login, multi-chain routing, and data-level policies.
10. **Verify under load:** monitor authentication latency, 401/403 responses, event-loop blocking, connection pools, and context propagation; roll out in narrow scopes where possible.

A sufficiently concrete per-route test matrix typically includes columns for: request path, HTTP method, credentials, authorities, expected security chain, prior Servlet result, new WebFlux result, and cause of any discrepancy. Compare both **policy and HTTP responses**, not merely whether the application starts.

## 10. Common Errors and How to Diagnose Them

| Symptom | Common cause | How to find and fix |
| --- | --- | --- |
| `No qualifying bean of type ServerHttpSecurity` or config class errors | WebFlux security not active, wrong stack dependencies or auto-config | Confirm `@EnableWebFluxSecurity`, Boot web application type, and starters. |
| `HttpSecurity`/`SecurityFilterChain` classes still in WebFlux config | Copied Servlet APIs | Separate MVC and reactive configs cleanly; import from `.web.server` packages. |
| Endpoints return 404 or security behaves unexpectedly | Application still boots as MVC; routes not registered in WebFlux | Check startup logs, dependency tree, and controller/router registration before blaming security. |
| `401` on seemingly valid token | Wrong reactive decoder/issuer/audience/keys/clock skew; missing Resource Server bean/config | Enable controlled debug logs, verify validators and Bearer format, never log raw tokens. |
| `403` when roles appear right | Confusing `ROLE_` vs `SCOPE_`, `hasRole` vs `hasAuthority`, or unmigrated authorities converter | Print or assert **non-sensitive** authorities in tests, then fix rules or mapping. |
| API returns `302` instead of `401` | Form login or browser entry point enabled on that chain | Split API and web chains and configure the right entry point. |
| POST gets `403` while GET works | Missing CSRF token in cookie/session flow | Confirm CSRF policy and send a valid token; disable only when the security model allows it. |
| Public routes remain protected | Rules ordered wrongly, or specific chain shadowed by catch-all | Check `@Order`, `securityMatcher`, and `pathMatchers` order. |
| Principal disappears after `flatMap`/`publishOn` | Thread-local `SecurityContextHolder` used or publisher built outside context | Use Reactor Context/`ReactiveSecurityContextHolder` and test in a real pipeline. |
| Latency spikes, event loop stalls | Custom authenticator/authorization calls `block()`, sync JDBC, or blocking HTTP client | Use reactive APIs, isolate blocking work properly, and load test. |
| App runs, but `@PreAuthorize` stops enforcing | Reactive method security not enabled or proxy bypassed | Migrate annotation/config, test reactive methods directly and check self-invocation. |

You can enable `logging.level.org.springframework.security=DEBUG` **temporarily in test environments** to inspect security progress and matcher decisions; do not enable TRACE/DEBUG broadly in production and never log Authorization headers, session cookies, bearer tokens, or passwords. For chain-mismatch issues, start from **securityMatcher and bean order**; for authn failures, inspect the auth mechanism/decoder/manager; for authz failures, compare authenticated authorities against target rules.

## 11. Pitfalls to Avoid

- **Renaming the DSL while leaving Servlet filters in place.** `OncePerRequestFilter` is not a `WebFilter`; mixing stacks can leave code unexecuted or fail startup.
- **Wrapping legacy DAO/Auth managers with `block()`.** This can stall the event loop and collapse throughput under concurrency.
- **Assuming the principal lives in ThreadLocal.** Reactive security context travels with the subscriber context; test across async boundaries.
- **Confusing chain matchers with authorization rules.** `securityMatcher` selects the chain; `pathMatchers` defines rules within the chain, and specific rules must come before `anyExchange`.
- **Merging everything into one chain without checking UI vs API.** Policies for form login, Basic/Bearer, sessions, and entry points can differ substantially.
- **Using `permitAll` everywhere to bypass migration errors.** This hides bugs and introduces authorization vulnerabilities; test and fix the root cause instead.
- **Skipping CSRF because the app is "reactive" or "REST".** What matters is whether client credentials are sent automatically by browsers and the actual authentication architecture.
- **Relying on the compiler instead of security tests.** Compiling code does not prove `401`/`403`, scopes, roles, chain ordering, or session flows remain correct.

## 12. Migration Completion Criteria

A migration meets requirements when: the application genuinely runs on WebFlux; every request passes through the intended `SecurityWebFilterChain`; URL rules and method security preserve their meaning; auth managers, user details, JWT/OAuth2, and custom filters use proper reactive components; the event loop is never blocked; CSRF/CORS and browser flows are verified; `200`/`401`/`403`/`302` tests match design expectations; and logs/metrics leak no credentials. When a policy has no 1:1 mapping between Servlet and WebFlux, document the business requirement and redesign that component rather than assuming identically named APIs behave identically.

**Official references:** [WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html), [Reactive HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html), [Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html), [Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html), [CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html), [Testing WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/test/web.html).