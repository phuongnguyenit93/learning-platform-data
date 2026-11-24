# `authorizeHttpRequests` and `authorizeExchange` in the Two Web Models

**Scope:** HTTP-layer endpoint authorization in Spring Security, comparing **Servlet/Spring MVC** and **Reactive/Spring WebFlux** applications. Both DSLs solve the same problem: for an HTTP request that has passed through the security processing steps, which paths and HTTP methods are accessible, who must be logged in, and who needs a specific role/authority. However, they belong to two different execution models and therefore **are not directly interchangeable**.

## 1. Distinguishing Authentication and Authorization

- **Authentication:** determines who the user/client is; Spring Security represents that information as an `Authentication` with an identity and a set of `GrantedAuthority` instances. Basic, form login, session, or OAuth2 Resource Server/JWT are different authentication mechanisms.
- **Authorization:** decides whether a request that has (or lacks) an identity/authorities may proceed to an endpoint. `authorizeHttpRequests` and `authorizeExchange` declare these rules at the HTTP layer.
- `permitAll()`: allows access to a public endpoint; does not require login.
- `authenticated()`: requires an identity that Spring Security considers authenticated, without requiring a specific authority.
- `hasAuthority("report:read")`: accepts only a `GrantedAuthority` equal to the exact string `report:read`.
- `hasRole("ADMIN")`: by the default prefix convention, looks for the authority `ROLE_ADMIN`. **Do not pass `"ROLE_ADMIN"` into `hasRole`**; if you already have the full string, use `hasAuthority("ROLE_ADMIN")`.
- `denyAll()`: denies all requests matching the rule.

**Limitation:** This is authorization at the HTTP entry point. It does not automatically check whether a specific record belongs to the user, does not issue tokens, and does not validate passwords. For business logic that needs to verify data ownership, add authorization at the service/method layer or a suitable `AuthorizationManager`.

## 2. Quick Overview of Differences

| Aspect | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Rule DSL | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| Builder | `HttpSecurity` | `ServerHttpSecurity` |
| Resulting bean | `SecurityFilterChain` | `SecurityWebFilterChain` |
| HTTP unit | `HttpServletRequest` | `ServerWebExchange` |
| Path matching | `requestMatchers(...)` | `pathMatchers(...)` |
| Match all remaining | `anyRequest()` | `anyExchange()` |
| Authorization enforcer | Typically `AuthorizationFilter` | `AuthorizationWebFilter` |
| Custom decision API | `AuthorizationManager<RequestAuthorizationContext>` | `ReactiveAuthorizationManager<AuthorizationContext>` |
| Identity propagation | `SecurityContextHolder` in the Servlet mechanism | `ReactiveSecurityContextHolder` via Reactor `Context` |
| Decision evaluation | Synchronous via `AuthorizationManager` | Reactive via `Mono<AuthorizationDecision>` |
| Common test tool | `MockMvc` + `spring-security-test` | `WebTestClient` + `spring-security-test` |

Intuitively, both follow the flow:

```text
HTTP request
  → Spring Security selects the applicable chain
  → authenticates and creates/restores Authentication
  → finds the authorization rule matching the request
  → sufficient permissions: proceeds to handler; insufficient: handles denial
```

**Key difference:** MVC is based on Servlet Filters and synchronous per-request calls; WebFlux uses WebFilters and reactive Publishers. In a `ReactiveAuthorizationManager`, the decision can depend on an asynchronous lookup and be returned via a `Mono`; do not call `block()` or `subscribe()` manually during the authorization decision.

## 3. Servlet Configuration: `HttpSecurity.authorizeHttpRequests`

The example below is **a complete configuration class** for a **Spring Boot MVC/Servlet application** using Spring Security 6.x, Java 17+. Place it in `ServletSecurityConfig.java` in the application's package; the application needs `spring-boot-starter-web` and `spring-boot-starter-security`. Do not place this class in a pure WebFlux application.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain servletSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**", "/actuator/health")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .requestMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("report:write")
                .requestMatchers("/admin/**")
                    .hasRole("ADMIN")
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

**Layer-by-layer explanation:**

1. `HttpSecurity` configures HTTP security for the **Servlet stack**. `http.build()` creates the `SecurityFilterChain` bean.
2. `authorizeHttpRequests` registers a list of **request matcher → rule** pairs. Spring Security applies the **first matching rule** in the list of the selected chain.
3. The two public paths receive `permitAll`. To open additional endpoints, declare them explicitly; do not put `"/**"` in `permitAll` before protected rules.
4. `GET /api/reports/**` requires the exact authority `report:read`, whereas `POST` on the same path group requires `report:write`. If read and write are separate authorities, a user with only read permission is not implicitly allowed to write.
5. `/admin/**` requires the `ADMIN` role, corresponding to the `ROLE_ADMIN` authority under the default prefix.
6. `anyRequest().denyAll()` is a **default-deny policy**: unlisted endpoints are not accidentally exposed. Replace it with `authenticated()` if the product requirement is that every other endpoint is accessible to logged-in users; this is a **security decision** that must be stated explicitly.
7. `httpBasic(...)` simply selects an HTTP authentication mechanism so the example has context. Users, passwords, OAuth2/JWT, sessions, or the account data store still must be configured appropriately for a real application.

You can write a minimal snippet for an application that only needs "every request must be logged in":

```java
http.authorizeHttpRequests(authorize -> authorize
    .anyRequest().authenticated()
);
```

The minimal snippet is a **configuration excerpt**, not a standalone Java program. Do not infer that `authenticated()` automatically grants roles or verifies resource ownership.

## 4. Reactive Configuration: `ServerHttpSecurity.authorizeExchange`

This is a **separate configuration class** for a **Spring Boot WebFlux application** using Spring Security 6.x, Java 17+. Place it at `ReactiveSecurityConfig.java` and use `spring-boot-starter-webflux` together with `spring-boot-starter-security`. This class **does not coexist** with the Servlet class above as a shared configuration; choose the class according to your actual web stack.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain reactiveSecurityWebFilterChain(ServerHttpSecurity http) {

        http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/public/**", "/actuator/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .pathMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("report:write")
                .pathMatchers("/admin/**")
                    .hasRole("ADMIN")
                .anyExchange()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

The policy semantics are **equivalent in intent** to the MVC example, but the classes and request types differ:

- `ServerHttpSecurity` builds a `SecurityWebFilterChain` instead of a `SecurityFilterChain`.
- `authorizeExchange` evaluates a `ServerWebExchange`. `pathMatchers` is WebFlux's path/method matcher; it **does not accept `HttpServletRequest`**.
- `anyExchange()` handles exchanges that did not match any earlier rule; its role is analogous to `anyRequest()`.
- Actual evaluation in a reactive system is executed through reactive components, which can emit signals asynchronously. Therefore, configuration and custom logic must preserve the Publisher chain.
- As with the Servlet example, `httpBasic(...)` does not create a user store or authority mappings by itself. The authentication mechanism can be reactive user details, HTTP Basic, or a reactive resource server/JWT.

Minimal WebFlux snippet:

```java
http.authorizeExchange(authorize -> authorize
    .anyExchange().authenticated()
);
```

**DSL naming note:** `authorizeHttpRequests` belongs to `HttpSecurity`; `authorizeExchange` belongs to `ServerHttpSecurity`. Do not mechanically rename the method in the same class while forgetting to switch the entire stack and the corresponding beans.

## 5. Reading and Evaluating Rule Order

Within **each chain**, Spring Security evaluates rules **in declaration order** and uses the first matching rule. For example, with the same rules across both stacks:

```text
1. /public/**                → permitAll
2. GET /api/reports/**       → hasAuthority("report:read")
3. POST /api/reports/**      → hasAuthority("report:write")
4. /admin/**                 → hasRole("ADMIN")
5. all remaining requests    → denyAll
```

| Request | First matching rule | Condition to proceed |
|---|---|---|
| `GET /public/about` | 1 | No login required |
| `GET /api/reports/42` | 2 | Must have `report:read` |
| `POST /api/reports/42` | 3 | Must have `report:write`; also subject to CSRF checks if enabled |
| `GET /admin/users` | 4 | Must have `ROLE_ADMIN` |
| `GET /unknown` | 5 | Denied even if logged in |

**Wrong due to order:**

```java
// Servlet — WRONG: broad rule catches everything before specific rules.
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

If there is a catch-all path matcher at the top of the list, the rule for `/admin/**` never gets a chance to decide. In WebFlux, the same bug occurs when `pathMatchers("/**").permitAll()` appears before `pathMatchers("/admin/**").hasRole("ADMIN")`.

**Correct:** declare specific cases first, broad cases later; place `anyRequest()`/`anyExchange()` at the end. Configuration must also explicitly cover HTTP methods when read and write permissions differ. `GET` differs from `POST`, while `HEAD`, `OPTIONS`, `PATCH`, `PUT`, and `DELETE` also need explicit policies if the endpoint supports them.

## 6. Chain-Selection Matchers vs. Rule-Selection Matchers

There are **two levels of selection** that are easy to confuse:

1. **Selecting the security chain:** in Servlet, `http.securityMatcher(...)` determines which requests use that `SecurityFilterChain`; in WebFlux, `http.securityMatcher(ServerWebExchangeMatcher)` decides which `SecurityWebFilterChain` applies to an exchange.
2. **Selecting a rule inside the applied chain:** Servlet uses `authorizeHttpRequests(...requestMatchers(...))`; WebFlux uses `authorizeExchange(...pathMatchers(...))`.

Conceptual example of a chain that protects only `/api/**`:

```java
// Servlet snippet: condition to SELECT THE CHAIN, then select the RULE.
http.securityMatcher("/api/**")
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
    );
```

```java
// WebFlux snippet: ServerWebExchangeMatcher selects the CHAIN.
http.securityMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**"))
    .authorizeExchange(authorize -> authorize
        .pathMatchers("/api/public/**").permitAll()
        .anyExchange().authenticated()
    );
```

The reactive snippet needs `import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers`. Both snippets sit inside a configuration method with the corresponding builder; they are not standalone Java classes.

**Important consequence:** `anyRequest()` or `anyExchange()` only means "all remaining requests/exchanges **in this chain**". If you define a dedicated chain for `/api/**` without a chain covering other paths, paths outside `/api/**` may **not be protected by Spring Security**. When using multiple chains, check `@Order` ordering, overlapping matchers, and a general fallback chain; do not confuse "deny all at the end of the API chain" with "deny all across the entire application".

General flow:

```text
Servlet:
HTTP request → FilterChainProxy → selects SecurityFilterChain
             → Servlet Filters → AuthorizationFilter
             → requestMatchers rules → controller

Reactive:
HTTP exchange → WebFilterChainProxy → selects SecurityWebFilterChain
              → WebFilters → AuthorizationWebFilter
              → pathMatchers rules → reactive handler
```

## 7. From Matchers to Custom Authorization Decisions

Rules like `permitAll`, `authenticated`, `hasRole`, and `hasAuthority` handle most basic needs. Cases like "a user may only view reports they own" usually require **object-level** permissions rather than URL-only rules.

- In **Servlet**, when custom request-level policy is needed, the DSL supports `.access(AuthorizationManager<RequestAuthorizationContext>)`. The manager receives `Supplier<Authentication>` and request data; authorization evaluation is synchronous. When verifying an owner in the database is required, you can place that logic in an appropriate service/method rather than doing expensive I/O directly inside a matcher.
- In **WebFlux**, `.access(ReactiveAuthorizationManager<AuthorizationContext>)` uses the exchange context and `Mono<Authentication>`; the logic must return a Publisher containing an `AuthorizationDecision` or a result matching the API. If the policy needs to read data asynchronously, combine `flatMap`/`map`; do not call `block()`, and do not `subscribe()` manually.
- In both models, **deny by default** when data is missing or inconclusive, and distinguish infrastructure errors from "access denied" for logging/observability and producing appropriate responses. Do not treat a client-supplied parameter as proof of ownership without checking it against the authenticated identity.

Intuitive example of the check:

```text
GET /users/alice/reports/42
  → matcher /users/{username}/reports/{id}
  → Authentication.name must satisfy the authorization policy
  → if needed, query data to verify report 42 belongs to the user
  → allow or deny BEFORE returning data
```

A path matcher can supply path variables to the policy engine depending on matcher configuration, but **matching the URL alone does not prove permission on the record**. To avoid mixing concepts, the configuration examples above only check static route authorities.

## 8. Key Differences to Remember When Switching MVC ↔ WebFlux

### 8.1. Do Not Swap APIs "One-for-One"

| Servlet | WebFlux |
|---|---|
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `requestMatchers("/foo/**")` | `pathMatchers("/foo/**")` |
| `requestMatchers(HttpMethod.GET, "/foo/**")` | `pathMatchers(HttpMethod.GET, "/foo/**")` |
| `anyRequest().authenticated()` | `anyExchange().authenticated()` |
| `Authentication` in the Servlet model | `Authentication` propagated via Reactor Context during reactive processing |

Do not import both `spring-boot-starter-web` and `spring-boot-starter-webflux` and assume every controller will automatically run reactively. In Spring Boot, having multiple web starters configured can cause the application to choose the Servlet stack; verify the actual application type before choosing the DSL. Avoid using `SecurityContextHolder.getContext()` as the sole source of the user in a WebFlux flow; use reactive integration mechanisms, such as `ReactiveSecurityContextHolder`, when you need to read the context.

### 8.2. HTTP Method, Path, and Query String

`requestMatchers` and `pathMatchers` can check paths and HTTP methods. Detailed pattern behavior depends on the matcher type, version, and configuration—especially with Servlet paths, context paths, encoded characters, or pattern parsers. Do not assume all pattern syntax behaves identically between MVC and WebFlux.

For example, `/api/reports/**` does not automatically enforce that `?owner=alice` matches the authenticated identity. Query parameters and ownership require custom matchers, an authorization manager, or an appropriate business-layer guard. You should also write tests with similar-looking paths (e.g., `/admin`, `/admin/`, `/adminx`), unlisted methods, and path variables to verify your project's exact matcher logic.

### 8.3. `permitAll` vs. Bypassing the Entire Security Chain

Allow public access with `permitAll()` so requests still pass through the security chain and can receive security headers or required protections. Avoid configuring complete Spring Security exclusion for static resources when there is no clear need. Using `permitAll` does not disable CSRF or other protections.

### 8.4. CSRF Is a Different Check Layer from Authorization Rules

Under default configurations with CSRF enabled, state-changing requests like `POST` can return **403 due to a missing CSRF token** even when the user has `report:write`. That **does not mean `hasAuthority` is wrong**. In tests, provide a CSRF token or design the CSRF policy according to reality: browser-based applications using cookies/sessions usually need CSRF; stateless APIs using bearer tokens in headers may have a different threat model. Do not disable CSRF globally just to make a test pass.

### 8.5. Servlet Dispatch and the WebFlux Request Lifecycle

In Servlet, dispatches such as `FORWARD` and `ERROR` can pass through `AuthorizationFilter`. If an application renders error/view pages and gets an unexpected `403`, consider an intentional rule via `dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)` or an appropriate rule; do not open all dispatches indiscriminately. In WebFlux, reactive context and lifecycle are managed by the framework; asynchronous authorization operations must stay inside the returned Publisher rather than switching to a detached subscription.

## 9. 401, 403, and Common Mistakes

**401 Unauthorized** usually indicates the request lacks valid authentication credentials and the authentication mechanism (such as HTTP Basic) requires authentication. **403 Forbidden** usually means the identity is authenticated but lacks permission, or another mechanism such as CSRF rejected the request. With form login, an unauthenticated request may be **redirected** to the login page instead of returning 401; the entry point/exception handler configuration determines the exact response. Therefore, never infer "the rule did not match" from the HTTP status alone.

Mistakes to avoid:

1. **Using the wrong stack:** putting `authorizeHttpRequests` on `ServerHttpSecurity` or vice versa; builders, beans, and the application are incompatible.
2. **Placing a broad rule before a narrow rule:** `/**.permitAll()` catches everything before `/admin/**`.
3. **Forgetting a catch-all:** leaving routes without an explicit policy, especially when endpoints are added later.
4. **Misunderstanding `hasRole`:** `hasRole("ADMIN")` checks `ROLE_ADMIN` by convention; `hasAuthority("ADMIN")` is a different authority.
5. **Confusing authentication and authorization:** having a valid token does not mean the token has the `report:write` authority.
6. **Mixing up `securityMatcher` and `requestMatchers`/`pathMatchers`:** a rule cannot protect a request if the request falls outside the selected security chain.
7. **Relying on the URL for object-level security:** knowing the path `/users/{id}` does not prove the caller is allowed to access that user.
8. **Reactive I/O mistakes:** calling `block()` or `subscribe()` manually inside an authorization manager; this breaks sequencing, error propagation, cancellation, and Reactor Context.
9. **Ignoring CSRF or ERROR dispatches:** assuming 403 responses come from authorization rules when another security layer is rejecting the request.

## 10. Testing Against a Shared Matrix

Use the **same set of business scenarios** for MVC and WebFlux, even though the test tools differ.

| Scenario | Authorization expectation |
|---|---|
| Anonymous accesses `GET /public/about` | Allowed through the authorization layer; if no handler exists, may still return 404 |
| User with `report:read` calls `GET /api/reports/42` | Allowed through the authorization layer |
| User with only `report:write` calls `GET /api/reports/42` | Denied due to missing `report:read` |
| User with `report:write` calls `POST /api/reports/42` | Allowed by the rule; must satisfy CSRF if enabled |
| User with `ROLE_ADMIN` calls `GET /admin/users` | Allowed by role |
| Regular user without `ROLE_ADMIN` calls `GET /admin/users` | Denied |
| Any user calls `GET /not-declared` | Denied by the `denyAll` catch-all |
| Same URL with an undeclared method, e.g., `DELETE` | Denied unless another rule allows it |
| WebFlux custom policy returns a delayed/error result | Does not let the request proceed before a decision; errors flow through the reactive pipeline |

**Servlet:** use `MockMvc` with `spring-security-test`. Example test snippet with `MockMvc`, Spring Security, and a real `GET /api/reports/42` endpoint configured:

```java
// static imports: get(...), user(...), status()
mockMvc.perform(get("/api/reports/42")
        .with(user("reader").authorities(
                new SimpleGrantedAuthority("report:read"))))
    .andExpect(status().isOk());
```

**Reactive:** use `WebTestClient` combined with `spring-security-test` and a mock user for WebFlux. Example snippet when `WebTestClient` is bound to the application and a matching endpoint exists:

```java
// static import: SecurityMockServerConfigurers.mockUser
webTestClient
    .mutateWith(mockUser().authorities(
            new SimpleGrantedAuthority("report:read")))
    .get().uri("/api/reports/42")
    .exchange()
    .expectStatus().isOk();
```

In both test snippets, import `org.springframework.security.core.authority.SimpleGrantedAuthority` and the corresponding static imports from `spring-security-test`. HTTP 200 only makes sense when the endpoint exists and the handler's business logic succeeds. Testing shows both whether the rule lets the request pass **and** what the handler returns; to isolate failures, check both. For `POST`, use CSRF testing appropriate to your stack or actual application configuration.

When testing 401/403, explicitly state the mechanism: Basic, form login, or resource server, the anonymous/authenticated user state, and CSRF. Test negative cases as well; testing only that "admin can access" does not prove regular users are blocked.

## 11. Configuration and Migration Checklist

1. Identify whether the application actually runs on **Servlet/MVC** or **WebFlux**; pick the right `HttpSecurity`/`ServerHttpSecurity` and filter chain type.
2. List public routes, login-required routes, authority/role-required routes, and method-specific routes.
3. Order matchers **specific first, general last**; place `anyRequest()`/`anyExchange()` at the end of each chain.
4. Define the fallback (`denyAll` or `authenticated`) according to product goals to avoid accidentally exposing new endpoints.
5. Verify role/authority mappings from the user store or token claims; `hasRole("ADMIN")` differs from `hasAuthority("ADMIN")`.
6. With multiple chains, distinguish chain-level `securityMatcher` from rule-level matchers; verify `@Order` and the catch-all chain.
7. Review CSRF, login entry point, static resources, Servlet dispatches, and error responses according to the stack.
8. For WebFlux, custom authorization must preserve the Publisher, Reactor Context, and non-blocking behavior.
9. Add business authorization at the service/method layer for owner/data permissions; endpoint protection alone is not enough.
10. Run both positive and negative tests for anonymous access, wrong role, wrong method, out-of-policy URLs, missing CSRF, and boundary paths.

## 12. Official References

- [Spring Security – Authorize HttpServletRequests (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security – ServerHttpSecurity API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security – Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)

**Key takeaway:** `authorizeHttpRequests` is the HTTP authorization DSL for **Servlet**; `authorizeExchange` is the corresponding DSL for **WebFlux**. Both share the goal of defining who may call an endpoint, but differ in builder, chain, matcher, request type, and authorization execution model. Configuring the right stack, rule order, and chain scope is the foundation for preventing endpoint exposure as an application grows.