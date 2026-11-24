# Deep Dive into Authorization, Servlet, or Reactive Based on Application Architecture

## 1. Goals of the Next Learning Stage

After mastering Spring Security fundamentals (authentication, authorization, `SecurityContext`, and the filter chain), the next step is not to learn every API all at once. Answer two independent questions:

1. **To what granularity does the application need access control?** Role-based, fine-grained permissions, per-record permissions, organization/owner checks, or business conditions? This is the **authorization** track required by every architecture.
2. **Which model does the application use to handle HTTP?** Spring MVC on Servlet or Spring WebFlux with a reactive pipeline? The answer determines the configuration APIs, where the security context lives, and the testing tools.

Expected outcomes: read the security flow of an existing project; draw an authorization matrix; select the right Servlet or reactive configuration; test both permitted and denied access; know when to dive deeper into OAuth2 Resource Server, method security, and resource ownership.

## 2. Choosing a Learning Track Based on Real Architecture

| Signal in the project | Learning priority | Characteristic Spring Security tools |
| --- | --- | --- |
| `spring-boot-starter-web`, Spring MVC, `DispatcherServlet`, controllers returning objects/`ResponseEntity` | **Servlet** plus authorization | `HttpSecurity`, `SecurityFilterChain`, `FilterChainProxy`, `SecurityContextHolder`, `MockMvc` |
| `spring-boot-starter-webflux`, handlers returning `Mono`/`Flux`, non-blocking pipeline | **Reactive** plus authorization | `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebFilterChainProxy`, `ReactiveSecurityContextHolder`, `WebTestClient` |
| Multiple roles, multiple resources, owner/tenant rules | **Deep authorization** first, then apply to your Servlet or reactive stack | `hasAuthority`, `hasRole`, `@PreAuthorize`, `AuthorizationManager`, permission tests |
| System with a WebFlux gateway and MVC services | Learn **both**, each app per its own runtime; align authorization principles across services | Gateway: reactive; MVC services: Servlet; both authenticate/authorize within their scope of responsibility |
| API receiving JWTs from an identity provider | Learn **OAuth2 Resource Server** after understanding authorization rules | JWT decoder/verifier, issuer/audience, scope/role mapping, runtime-appropriate Resource Server config |

**Do not use high request volume as the sole reason to switch to reactive.** WebFlux fits best when the entire I/O chain and supporting libraries are non-blocking; calling JDBC or blocking HTTP directly on the event loop negates the benefits and causes stalls. MVC services can also serve high loads when properly configured. Switching runtimes merely to use a different security DSL is the wrong focus.

**Check the classpath:** When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are added to the same app, Spring Boot defaults to Spring MVC; using `WebClient` does not automatically turn an app into WebFlux. Verify the actual application type before picking a security chain. The two example configurations below are for **two separate applications**, not combined into one.

## 3. Authorization Foundations Required on Both Tracks

### 3.1. Authentication Differs from Authorization

- **Authentication**: who is calling? The result is typically an `Authentication` object in the security context containing the principal and `GrantedAuthority` instances.
- **Authorization**: is this principal allowed to perform this action on this specific resource? The decision must consider action, resource, and sometimes context such as owner, tenant, or order status.
- **Role** is a way of grouping permissions; an **authority** is a specific permission string. By default, `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority; `hasAuthority("report:read")` checks the exact string `report:read`. Avoid manually prepending `ROLE_` to the argument of `hasRole`.
- **JWT scopes** and **internal roles** are not synonymous. If a JWT contains scope `reports.read`, default mapping produces an authority like `SCOPE_reports.read`; if you want `report:read` or `ROLE_ADMIN`, design an explicit mapping with tests.

### 3.2. Two Decision Layers

1. **At HTTP:** block non-public paths early, restricting by HTTP method and user category. Servlet uses `authorizeHttpRequests` + `requestMatchers`; reactive uses `authorizeExchange` + `pathMatchers`.
2. **At the business layer:** check permissions directly at service methods and data policies, especially when services can be invoked via HTTP, scheduled jobs, events, GraphQL, or other entry points. Enable method security and use `@PreAuthorize` where appropriate.

Checking URL patterns alone **is not enough** for rules like “user A can read report 42 but cannot read someone else's report 43.” That rule requires comparing the principal against the resource owner in the business layer or data query, and checking tenant boundaries to prevent cross-organization access.

### 3.3. Designing an Authorization Matrix Before Writing Configuration

Suppose a system has these endpoints:

| Action | Unauthenticated guest | User with `report:read` | User with `ROLE_ADMIN` |
| --- | --- | --- | --- |
| `GET /public` | Allow | Allow | Allow |
| `GET /reports/{id}` | Deny | Allow **if** data policy permits | Depends on business policy; e.g., only if also holding `report:read` |
| `GET /admin/status` | Deny | Deny | Allow |
| Other undeclared paths | Deny | Deny | Deny |

For each row, document: identity source, required authority, owner/tenant condition, expected response, enforcement point, and a negative test. Apply **least privilege** and **deny by default**, never treating “logged in” as sufficient to read all data.

## 4. Servlet Track: Spring MVC / Filter-Chain-Based HTTP

### 4.1. Mechanisms to Understand

An HTTP request passes through the Servlet container's `Filter` chain. Spring Security uses `DelegatingFilterProxy` to bridge into `FilterChainProxy`; this proxy selects the matching `SecurityFilterChain` and runs authentication, exploit protection, and authorization filters in framework order. Only if permitted does the request proceed to `DispatcherServlet`/controllers.

`SecurityContextHolder` in traditional Servlet apps relies on `ThreadLocal` by default. When using async processing, thread pools, or offloading work to other threads, do not assume the security context follows across threads automatically; use context-propagation mechanisms supported by Spring Security and verify with tests.

With multiple `SecurityFilterChain`s, `securityMatcher` selects which chain applies to the **entire request**; `requestMatchers` defines rules **inside the selected chain**. The first matching chain applies. Configuring a chain matching only `/api/**` while forgetting other paths can leave gaps uncovered if there is no fallback chain.

### 4.2. Servlet Configuration Example

Example project: Java 17+, Spring Boot with `spring-boot-starter-web`, `spring-boot-starter-security`. The file below is configuration runnable **inside a Spring Boot application with a main class and matching controllers**; it is not a standalone Java program run directly via `javac`/`java`. The two in-memory accounts are for practice only.

~~~java
package demo.servlet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class ServletSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/reports/**")
                    .hasAuthority("report:read")
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}demo")
                .authorities("report:read")
                .build(),
            User.withUsername("admin")
                .password("{noop}demo")
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Explanation:**

- `/public` is publicly accessible; `GET /reports/**` requires the exact `report:read` authority; `/admin/**` requires `ROLE_ADMIN`; all unspecified requests are denied.
- Rules are evaluated in order: declare specific paths before `anyRequest()`. `hasAuthority` only checks route-level privilege; add owner checks if `/reports/{id}` holds private data.
- `httpBasic` is easy to observe in exercises, **which does not mean production architectures must use HTTP Basic**. Replace it with session login or OAuth2 Resource Server depending on how real clients authenticate.
- `{noop}demo` is only for quick learner experiments; production must use strong password hashing, an appropriate identity store, HTTPS, secret management, and login policies.
- These configurations do not create controllers or data. If an endpoint is not implemented yet, a request permitted at the security layer may still return `404`. Do not claim every permitted request returns `200`.

### 4.3. Servlet Topics to Learn Next

1. Choosing the right `SecurityFilterChain` when both API paths and web UI exist; understanding `@Order`, fallback chains, and `securityMatcher`.
2. Understanding sessions, login/logout, `SecurityContextRepository`, CSRF, and browser client characteristics.
3. For APIs receiving bearer tokens, validating JWTs via issuer/audience/signature, mapping authorities, and handling `401/403`. Do not write custom JWT filters when Spring Security Resource Server covers your needs.
4. Protecting service methods with `@EnableMethodSecurity`/`@PreAuthorize`; checking permissions on real data and testing service invocations across entry points.
5. Using `MockMvc` + `spring-security-test` to test anonymous users, authorized users, unauthorized users, paths, and sensitive HTTP methods.

## 5. Reactive Track: WebFlux / Non-Blocking Pipeline

### 5.1. Mechanisms to Understand

WebFlux processes requests through a reactive pipeline. Spring Security integrates via `WebFilterChainProxy` and one or more `SecurityWebFilterChain`s configured with `ServerHttpSecurity`. HTTP policies operate on `ServerWebExchange`; authentication and authorization hooks compose into reactive publishers.

User context lives in the **Reactor Context** and is accessed via `ReactiveSecurityContextHolder`, **not by reading `ThreadLocal` on arbitrary threads**. Avoid calling `block()`, JDBC queries, or blocking I/O directly on event-loop threads. If you genuinely must use a blocking library, offload it onto an appropriate scheduler and re-evaluate the architecture.

### 5.2. Reactive Configuration Example

A separate example project: Java 17+, Spring Boot with `spring-boot-starter-webflux`, `spring-boot-starter-security`. The configuration file below is solely for a WebFlux application with its own main class and handlers/controllers—**do not combine it with `ServletSecurityConfig`** from the Servlet track.

~~~java
package demo.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/reports/**")
                    .hasAuthority("report:read")
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    ReactiveUserDetailsService reactiveUsers() {
        return new MapReactiveUserDetailsService(
            User.withUsername("reader")
                .password("{noop}demo")
                .authorities("report:read")
                .build(),
            User.withUsername("admin")
                .password("{noop}demo")
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Comparison with Servlet:** The exact same authorization matrix, except `HttpSecurity / SecurityFilterChain / authorizeHttpRequests / requestMatchers / anyRequest` are replaced by `ServerHttpSecurity / SecurityWebFilterChain / authorizeExchange / pathMatchers / anyExchange`. The snippet above still uses HTTP Basic and demo passwords for easy comparison; production authentication mechanisms are chosen separately.

### 5.3. Reactive Topics to Learn Next

1. `SecurityWebFilterChain` selection order, `securityMatcher`, `pathMatchers` rules, and policy declaration order.
2. `ReactiveSecurityContextHolder` and how Reactor Context flows along `Mono`/`Flux` chains; differences when code switches schedulers or manually subscribes.
3. `@EnableReactiveMethodSecurity` on methods returning reactive types like `Mono<T>`/`Flux<T>`; non-blocking permission checks; never calling blocking repositories inside authorization expressions.
4. Reactive OAuth2 Resource Server, `ReactiveJwtDecoder`, and mapping claims to authorities; distinguishing missing token, invalid token, and insufficient scope/permission errors.
5. `WebTestClient` + `spring-security-test` utilities, including `mockUser()`/`mockJwt()` where appropriate, to test directly against the WebFlux pipeline.

## 6. Pushing Authorization Down to the Business Layer

In Servlet, declare `@EnableMethodSecurity`; in WebFlux, use `@EnableReactiveMethodSecurity`. Place permission conditions on methods of Spring-managed beans, usually in the service layer. The two methods below show **two separate variants**, each placed in its respective module; they illustrate annotation usage only, without controllers or data stores:

~~~java
// In a Servlet application:
@PreAuthorize("hasAuthority('report:read')")
public String readReport(String id) {
    return "report:" + id;
}

// In a reactive application:
@PreAuthorize("hasAuthority('report:read')")
public Mono<String> readReport(String id) {
    return Mono.just("report:" + id);
}
~~~

Import `org.springframework.security.access.prepost.PreAuthorize` and, in the reactive variant, `reactor.core.publisher.Mono`; these methods must belong to a Spring-managed bean with method security enabled. Note that internal self-invocation from another method on the **same object** may bypass the security proxy; design enforcement points at real service boundaries and test that case.

To enforce ownership, replace broad conditions with data-aware policies such as `hasAuthority('report:read') and @reportPolicy.canRead(authentication, #id)`. `reportPolicy` must be a Spring bean with a matching check method; ensure the parameter name `id` is visible to Spring (compiler config retaining parameter names or a supported parameter-naming annotation). Proper checks must also verify tenant and owner from trusted data sources rather than trusting an `ownerId` sent by the client. In reactive apps, permission lookups should remain non-blocking and follow reactive method security/authorization patterns.

Distinguish two points: **endpoint-level authorization** answers “may this caller invoke this kind of action?”, while **object-level authorization** answers “may this caller act on this specific record?”. Both are typically required, especially in multi-tenant APIs. Claims inside a token are only inputs to the decision; data state and business rules can change after the token was issued.

## 7. Authentication, Tokens, Sessions, and CSRF: Choose by Client

| Situation | Appropriate direction | What must be verified |
| --- | --- | --- |
| Browser UI using sessions/cookies | Session-based login, CSRF protection | Cookies, session lifetime, CSRF tokens, logout, CORS/Origin |
| API for mobile apps or servers using bearer JWTs | Servlet or reactive OAuth2 Resource Server | Signature, issuer, audience, expiration, scope/role mapping, `401/403` errors |
| Gateway validating JWTs and forwarding to services | Protect gateway **and** trust boundaries per backend | Does the backend re-verify tokens or trusted identity origin? Does the backend enforce resource permissions? |
| App serving both browsers and APIs | Separate chains/policies and auth mechanisms per endpoint | Avoid gaps from unscoped chains, overly broad CSRF disabling, or misordered rules |

**CSRF does not depend solely on whether there is a server-side session.** Browsers automatically attach cookies and sometimes Basic credentials; “stateless” apps using cookies can still suffer CSRF. Consider exempting CSRF only for API parts proven not to rely on browser auto-sent credentials, while keeping protection for the rest. CORS governs browser cross-origin calls; **it does not replace authentication, authorization, or CSRF**.

## 8. Testing Authorization by Behavior, Not Only Configuration

After adding real controllers/handlers for `GET /public`, `GET /reports/42`, and `GET /admin/status`, build the cases below. In the HTTP Basic example, an unauthenticated request typically receives `401`; an authenticated user lacking permission receives `403`. With form login, unauthenticated requests may be redirected to the login page; verify according to the actual authentication mechanism.

| Test case | Expectation |
| --- | --- |
| Anonymous calls `GET /public` | Passes security layer |
| Anonymous calls `GET /reports/42` | Blocked, typically `401` with Basic |
| `reader` calls `GET /reports/42` | Passes `report:read` authority check; then verify ownership check |
| `reader` calls `GET /admin/status` | `403` |
| `admin` calls `GET /admin/status` | Passes security layer |
| `admin` without `report:read` calls `GET /reports/42` | `403` per defined policy; do not auto-grant just for being admin |
| Calling `POST /reports/42` when only GET is allowed | Denied; distinguish from CSRF failures if using browser/cookies |
| User allowed to read report 42 requests another user's report 43 | `403` or `404` per data-hiding contract; never return the data |
| User in tenant A requests tenant B's data | Denied at the data policy |
| Undeclared URL | Denied by `denyAll` |

- **Servlet:** use `MockMvc` and `spring-security-test`; test `@WithMockUser` or `user()`, `httpBasic()`, and `csrf()` per scenario. You can use `@WithMockUser(authorities = "report:read")` to test permissions without creating real accounts. Ensure the security filter chain is integrated into `MockMvc`.
- **Reactive:** use `WebTestClient` with Spring Security support applied, paired with `mockUser()` or `mockJwt()`. Write authorized, unauthorized, and unauthenticated cases via `exchange().expectStatus()`; object-level permissions need fixtures with multiple owners/tenants.
- Also test error routes, async/reactive boundaries, and service methods called outside HTTP. Seeing HTTP `200` alone is not enough to declare a policy sound; verify the returned payload and absence of data leaks.

## 9. Project-Based Practice Roadmap

**Step 1 — Snapshot the current architecture:** confirm the web starter in use, controller/handler type, authentication mechanism, request flow, data types, and token issuer. Sketch a simple diagram from client to gateway, security filters, controller, service, and repository.

**Step 2 — Write the policy first:** create an action × resource × principal × tenant matrix; write concrete examples of missing permissions and ownership checks. Decide where authorization lives so it cannot be bypassed by new entry points.

**Step 3 — Implement for the right runtime:** Servlet uses `SecurityFilterChain` and `@EnableMethodSecurity` if needed; WebFlux uses `SecurityWebFilterChain` and `@EnableReactiveMethodSecurity` if needed. Start with `denyAll` for unknown paths and open only policy-approved routes.

**Step 4 — Swap demo auth for real auth:** wire sessions or OAuth2 Resource Server/JWT according to clients; verify issuer/audience, authority mapping, CSRF, CORS, `401/403` handling, and secret-free logging.

**Step 5 — Test and observe:** run positive/negative matrices, test cross-tenant and object ownership, confirm the right chain applies, and add logging/metrics on auth failures or access denials at an appropriate detail level. Finish only when tests cover undeclared paths and denied scenarios.

### Capstone Practice Exercise

Build two small **independent** applications sharing the same `/public`, `GET /reports/{id}`, and `/admin/**` policy: app A using Spring MVC and app B using WebFlux. Both must include real controllers/handlers, three test users (anonymous, reader, admin), and at least two records owned by two different owners. Apply the same authorization matrix, test with `MockMvc` and `WebTestClient`, and then describe the differences in chain configuration, context storage, and testing. You do not need to rewrite a whole production app into reactive just to complete this exercise.

## 10. Common Mistakes and Self-Checks

- **Confusing authentication with authorization:** logged in yet still able to view someone else's resources. Fix with action- and record-level policies.
- **Confusing `hasRole` with `hasAuthority`:** `hasRole("ADMIN")` checks `ROLE_ADMIN` by default; roles and JWT scopes require consistent mapping.
- **Putting `permitAll` or broad matchers ahead of sensitive matchers:** later rules never get a chance to decide. Check ordering and write deny tests.
- **Treating `securityMatcher` like `requestMatchers`:** the chain does not apply to URLs outside its scope. Check fallback chains and all entry points.
- **Disabling CSRF out of habit:** unintentionally opens browser state-changing endpoints. Evaluate credential mechanics before changing CSRF.
- **Copying Servlet code into WebFlux:** using the wrong `HttpSecurity`/`SecurityContextHolder` in a reactive pipeline. Switch to the matching chain type and Reactor Context.
- **Blocking inside WebFlux or permission checks:** stalls the event loop. Use non-blocking APIs or re-evaluate architectural boundaries.
- **Treating the gateway as the sole line of defense:** backend services may be reached via other paths or leak data through business logic. Define trust boundaries clearly and enforce authn/authz in the backend where appropriate.
- **Testing only happy paths:** skipping `401`, `403`, wrong-owner, cross-tenant, wrong-method, and undeclared URL cases.

## 11. Official Documentation for Deep Learning

- [Spring Security: Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security: Authorize Servlet HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security: Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security: WebFlux Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security: Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security: Testing Servlet with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security: Testing Reactive with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html)
- [Spring Boot: When MVC and WebFlux Are Both on the Classpath](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Security: CSRF Considerations](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)

All examples use modern DSL; when applying them to real projects, select the documentation version matching the Spring Security line managed by your Spring Boot BOM. Check API changes when upgrading, especially if an older project still uses `WebSecurityConfigurerAdapter` or `authorizeRequests`.

**Completion criteria:** learners can explain why Servlet or WebFlux was chosen, identify the exact places where authorization decisions occur, write and test configurations tailored to the running runtime, and accurately deny any out-of-scope access.
