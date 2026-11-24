# authorizeExchange and the First-Match Rule Ordering Principle

> **Topic:** HTTP authorization in Spring Security **reactive / Spring WebFlux**, using Spring Boot 3.x, Spring Security 6.x, and Java 17+. The focus is on `ServerHttpSecurity.authorizeExchange(...)`, the rule that **the first matching request rule determines the policy**, how to place specific matchers before general matchers, and distinguishing rule order from `SecurityWebFilterChain` selection order.

## Objectives

After this lesson, you can:

1. Describe how Spring Security applies authentication and then authorization to HTTP requests in WebFlux.
2. Declare `authorizeExchange(exchanges -> exchanges...)` with `pathMatchers`, `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, `denyAll`, and `anyExchange`.
3. Predict **which rule will be selected** when the same URL matches multiple path patterns.
4. Detect vulnerabilities caused by `/api/**` or `/**` appearing before `/api/admin/**`.
5. Protect endpoints separately by HTTP method, role, and scope.
6. Run a Spring Boot/WebFlux application with Java 17+ and test with `WebTestClient` for 200/401/403 results.
7. Distinguish `http.securityMatcher(...)` (which selects the chain) from `authorizeExchange().pathMatchers(...)` (which selects a rule within the chain).
8. Know when CORS, CSRF, path variables, and resource ownership must be considered separately.

## 1. Where Does HTTP Authorization Happen?

In Spring WebFlux, requests pass through `WebFilter` instances. Spring Security registers `WebFilterChainProxy` to select the appropriate `SecurityWebFilterChain`. The selected chain contains filters related to security context, authentication, authorization, CSRF, and error handling. If a request is not permitted, it can be terminated before `DispatcherHandler` invokes the controller or functional handler.

```text
HTTP request (method, path, Authorization header)
       |
       v
WebFlux WebFilter pipeline
       |
       v
Spring Security WebFilterChainProxy
       |
       +-- Select SecurityWebFilterChain by securityMatcher / @Order
       |
       +-- Authentication: verify credentials, create Authentication
       |
       +-- Authorization: select rule in authorizeExchange
       |     |
       |     +-- does rule #1 match?
       |     |     +-- Yes -> evaluate permissions and stop selecting rules
       |     |     +-- No -> rule #2
       |     +-- rule #2 ...
       |     +-- fallback anyExchange()
       |
       +-- Insufficient permissions: block (usually 401/403 depending on scenario)
       |
       v
DispatcherHandler
       |
       +-- @RestController / annotated handler
       +-- RouterFunction / functional handler
       |
       v
HTTP response
```

The diagram only describes the **logical decision steps**, not the physical order of all filters. Spring Security HTTP authorization applies to `ServerWebExchange`, regardless of whether the handler is written with `@RestController` or `RouterFunction`.

### Authentication vs. Authorization

| Concept | Question Answered | Example |
| --- | --- | --- |
| Authentication | **Who** is the caller? | HTTP Basic verifies password, creates principal `reader` |
| Authorization | **What** is the caller allowed to do? | `/api/admin/**` requires `ROLE_ADMIN` |
| Rule matcher | Which rule applies to this request? | `GET /api/reports/**` |
| Authentication entry point | How is an unauthenticated caller handled? | Basic returns 401/challenge; form login may redirect |
| Access denied handling | What does an authenticated caller lacking permission receive? | Usually 403 |
| Security chain matcher | Which set of `WebFilter`s handles the request? | `securityMatcher("/api/**")` with the appropriate matcher |

**Do not confuse:** "Logged in" does not mean "allowed to call every API". `authenticated()` only requires an authenticated principal; `hasRole("ADMIN")`, `hasAuthority("SCOPE_reports.read")`, or business authorization restricts specific permissions.

## 2. Core Principle: Declaration Order Decides

In Spring Security reactive, rules are evaluated in **registration order**. The **first rule that matches** the request selects an authorization policy. If that policy denies the request, Spring Security does not continue trying lower rules to find an "easier" one.

Example:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
);
```

This is a **snippet inside a configuration method**, not a standalone class. It produces:

- `GET /public/ping` → matches `/public/**` → public.
- `GET /api/admin/stats` → does not match public, **matches admin** → requires `ROLE_ADMIN`. A user with only `ROLE_READER` is denied.
- `GET /api/profile` → matches `/api/**` → only requires being authenticated.
- `GET /unlisted` → matches fallback `anyExchange()` → denies everyone.

**Spring Security does not automatically sort longer paths before shorter paths.** The order in the DSL expresses your policy intent.

### 2.1 Counterexample: Broad Rule Before Narrow Rule

```java
// WRONG if /api/admin/** is only for ADMIN:
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll()
);
```

The request `GET /api/admin/stats` immediately matches `/api/**`. A logged-in `reader` user is approved by `authenticated()` **before** Spring Security has a chance to evaluate `hasRole("ADMIN")`. The admin rule is **shadowed** (rule shadowing); the policy has a vulnerability even though there is no compilation error.

Fix:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
);
```

Summary: **Place specific URLs, sensitive URLs, and intentional exceptions before broad URLs**. `anyExchange()` should be placed last, not first.

### 2.2 Rules Do Not Automatically Combine

These two rules **do not** mean "must have both FINANCE and SCOPE_approved":

```java
.pathMatchers("/api/finance/**").hasRole("FINANCE")
.pathMatchers("/api/finance/**").hasAuthority("SCOPE_approved")
```

The first rule already matched the path; the second rule is never evaluated for the same request. When you need to combine multiple AND/OR conditions, use **a single** custom `ReactiveAuthorizationManager` registered via `.access(...)`, or place business logic in service/method security and test it separately.

### 2.3 "Matcher Matches" vs. "Policy Permits"

Suppose the first rule matches `/api/admin/stats` with `hasRole("ADMIN")` and the principal is `reader`. This is not "the rule did not match because the user lacks the role"; **the matcher matched**, but **the authorization decision is denied**. Spring Security does not fall through to `/api/**.authenticated()`.

This is why a policy that "tries rules one by one until one permits" would be dangerous; in reality, Spring Security selects **the first rule whose matcher matches the request** and decides according to that rule.

## 3. Common Authorization Primitives

| DSL | Condition | Appropriate Use Case |
| --- | --- | --- |
| `permitAll()` | Does not require a logged-in principal | Intentionally public endpoints |
| `authenticated()` | Requires a valid `Authentication` per Spring Security | Logged-in user's own profile, though ownership checks are still needed when applicable |
| `hasRole("ADMIN")` | Requires authority `ROLE_ADMIN` | Admin UI/API |
| `hasAuthority("SCOPE_reports.read")` | Requires exact authority string `SCOPE_reports.read` | Scope or granular permission |
| `denyAll()` | Denies all requests matching the rule | Deny-by-default fallback |
| `anyExchange()` | Matcher catching all remaining exchanges in the **chain** | Final rule or explicit baseline |
| `access(customManager)` | Delegates to a custom policy | Tenant, ownership, combining multiple conditions |

### 3.1 `hasRole` vs. `hasAuthority`

`hasRole("ADMIN")` uses the default role prefix `ROLE_` and checks for authority `ROLE_ADMIN`. When creating a user with `User.roles("ADMIN")`, the builder automatically creates `ROLE_ADMIN`. Do not pass `"ROLE_ADMIN"` into `hasRole(...)` unless you know the API and the prefix has been changed.

`hasAuthority("SCOPE_reports.read")` matches the **exact authority name**. A JWT with scopes must be verified by a decoder/provider and mapped to appropriate authorities before the rule checks it. Writing `hasAuthority` alone does not verify the token signature.

### 3.2 `permitAll` Does Not Mean Bypassing WebFilters

Even if `/public/**` has `permitAll`, the request still goes through the security chain if the chain matches. The authentication filter may still process Basic credentials sent by the caller and fail, the CSRF filter may block unsafe methods, and CORS may affect browsers. A public rule only states that authorization requires no permissions, **not** that "all security filters are disabled".

### 3.3 `authenticated` Does Not Replace Data-Level Authorization

Suppose `GET /api/orders/{orderId}` only requires `authenticated()`; user A could try user B's `orderId`. HTTP rules need to work together with service-layer owner/tenant checks. URL-based authorization is only an **entry-gate** access control layer and does not automatically guarantee data-level access control.

### 3.4 `denyAll` vs. `authenticated` for Fallback

`anyExchange().denyAll()` means endpoints without an explicitly declared policy will **not accidentally be permitted**. This is a good choice for allowlist-based APIs. `anyExchange().authenticated()` can fit applications where almost all URLs are for logged-in users, but you must be careful that admin endpoints without a specific rule could become open to any authenticated user.

## 4. HTTP Method Is Also Part of the Matcher

WebFlux supports:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**").hasRole("READER")
.pathMatchers(HttpMethod.POST, "/api/orders").hasAuthority("SCOPE_orders.write")
```

These are DSL lines to place inside `authorizeExchange` with `HttpMethod` from `org.springframework.http.HttpMethod`. You must verify the path and method **actually received by the server**.

Example of an ordered method-specific configuration:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.write")
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasRole("READER")
    .pathMatchers("/api/**")
        .authenticated()
    .anyExchange().denyAll()
)
```

If `/api/**.authenticated()` is placed before the two specific lines, both POST and GET may only require login and bypass the per-action scope/role.

**CSRF Note:** Spring Security WebFlux usually enables CSRF protection by default. A POST with the right password/role can still receive 403 **due to a missing CSRF token** before the authorization rule takes effect. When testing state-changing requests, send a valid CSRF token for browser/cookie clients or design a CSRF policy fitting the API threat model—do not disable it app-wide just to make tests pass.

### 4.1 GET, HEAD, and OPTIONS

When a rule only specifies `HttpMethod.GET`, do not assume it automatically allows every `HEAD` or `OPTIONS` in every configuration. Browsers may send an `OPTIONS` preflight when an API uses the `Authorization` header and cross-origin requests. Preflight should be handled with an appropriate security CORS configuration, not fixed with `anyExchange().permitAll()`.

### 4.2 Path Prefix, Base Path, and Proxy

Matchers evaluate the request path seen by WebFlux. Differences such as `spring.webflux.base-path`, route rewrites at a gateway, trailing slashes, encoded path variables, and path naming mismatches between controllers and security can prevent the intended rule from matching. If you see `403` from the fallback even when the user has sufficient permissions, check the **received path/method**, not just the URL on the frontend.

## 5. Complete Hands-On Application

We will create a Spring Boot 3.x / Java 17+ application with only **one `SecurityWebFilterChain`**, a reactive in-memory user store, and multiple GET routes with different authorization rules. The example uses **HTTP Basic** to make testing credentials/roles simple; `authorizeExchange` rules still apply with other authentication mechanisms such as OAuth2 Bearer JWT or session.

### 5.1 Dependencies

In `build.gradle` of a Spring Boot project that already has plugin/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use the real WebFlux server. Do not simultaneously add `spring-boot-starter-web` (MVC) to this exercise; when both MVC and WebFlux are present, Spring Boot typically defaults to MVC/Servlet. `SecurityWebFilterChain`/`ServerHttpSecurity` are for the **reactive HTTP stack**, different from Servlet's `SecurityFilterChain`/`HttpSecurity`.

File structure:

```text
src/main/java/com/example/orderrules/
  RuleOrderApplication.java
  AccessRulesConfig.java
  DemoController.java
src/test/java/com/example/orderrules/
  AuthorizationOrderTest.java
```

Each `public` Java class must be in its own properly named file. The snippets below require Spring Boot dependencies and the Gradle wrapper, not a plain Java SE program run with raw `javac`.

### 5.2 RuleOrderApplication.java

`src/main/java/com/example/orderrules/RuleOrderApplication.java`:

```java
package com.example.orderrules;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuleOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuleOrderApplication.class, args);
    }
}
```

### 5.3 AccessRulesConfig.java: Ordered Rules

`src/main/java/com/example/orderrules/AccessRulesConfig.java`:

```java
package com.example.orderrules;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class AccessRulesConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                // 1. Public exception for exact path and GET
                .pathMatchers(HttpMethod.GET, "/public/**").permitAll()

                // 2. Specific policies before /api/**
                .pathMatchers(HttpMethod.GET, "/api/admin/**")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasRole("READER")

                // 3. Remaining GET APIs only require authentication
                .pathMatchers(HttpMethod.GET, "/api/**")
                    .authenticated()

                // 4. Deny all unmatched requests
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("ADMIN", "READER")
            .build();

        UserDetails analyst = User.withUsername("analyst")
            .password(encoder.encode("analyst-demo-password"))
            .authorities("ROLE_READER", "SCOPE_reports.read")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-demo-password"))
            .roles("VIEWER")
            .build();

        return new MapReactiveUserDetailsService(
            reader, admin, analyst, viewer
        );
    }
}
```

**How does each rule work?**

- `GET /public/ping` → public rule, no login required.
- `GET /api/admin/stats` → admin rule, requires `ROLE_ADMIN`. An authenticated `reader` is still not allowed.
- `GET /api/reports/monthly` → reports rule, requires exact `SCOPE_reports.read`. `analyst` is allowed, `reader` is not.
- `GET /api/orders/42` → orders rule, requires `ROLE_READER`. `reader`/`admin`/`analyst` have this role; `viewer` does not.
- `GET /api/profile` → general matcher `GET /api/**`, only requires authentication.
- `GET /private/unlisted` → `anyExchange().denyAll()` denies even `admin`.

**Password security:** `createDelegatingPasswordEncoder()` hashes demo passwords before creating users. In real production systems, do not hardcode usernames/passwords, do not log HTTP Basic credentials, and use TLS/HTTPS with a trusted identity store. `User.roles` automatically adds the `ROLE_` prefix, whereas `User.authorities` takes the exact authority string.

### 5.4 DemoController.java

`src/main/java/com/example/orderrules/DemoController.java`:

```java
package com.example.orderrules;

import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(
        value = "/api/profile",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> profile() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "Profile " + auth.getName());
    }

    @GetMapping(
        value = "/api/admin/stats",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> adminStats() {
        return Mono.just("admin-stats");
    }

    @GetMapping(
        value = "/api/reports/monthly",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> report() {
        return Mono.just("monthly-report");
    }

    @GetMapping(
        value = "/api/orders/{id}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> order(@PathVariable String id) {
        return Mono.just("order-" + id);
    }

    @GetMapping(
        value = "/private/unlisted",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> unlisted() {
        return Mono.just("must-not-be-visible");
    }
}
```

The controller does not check passwords/roles itself. The `WebFilter` protects the request **before** the method is invoked. `ReactiveSecurityContextHolder` reads the username from the Reactor Context of the authenticated request.

**An existing route does not mean access is permitted.** `/private/unlisted` has a valid handler method but is blocked by the `denyAll` policy. And if an authorized request passes security but WebFlux finds no route, it can still return 404.

## 6. Expected Behavior Matrix

| Request | Credential | First Matching Rule | Expected Result |
| --- | --- | --- | --- |
| GET `/public/ping` | None | Public → permitAll | 200, `pong` |
| GET `/api/profile` | None | General API → authenticated | 401 with HTTP Basic |
| GET `/api/profile` | reader | General API → authenticated | 200, `Profile reader` |
| GET `/api/admin/stats` | reader | Admin → hasRole(ADMIN) | 403 |
| GET `/api/admin/stats` | admin | Admin → hasRole(ADMIN) | 200, `admin-stats` |
| GET `/api/orders/42` | reader | Orders → hasRole(READER) | 200, `order-42` |
| GET `/api/orders/42` | viewer | Orders → hasRole(READER) | 403 |
| GET `/api/reports/monthly` | reader | Reports → hasAuthority(scope) | 403 |
| GET `/api/reports/monthly` | analyst | Reports → hasAuthority(scope) | 200, `monthly-report` |
| GET `/private/unlisted` | admin | Fallback denyAll | 403 |
| GET `/api/does-not-exist` | reader | General API → authenticated | After security, 404 if no handler exists |
| POST `/api/profile` | reader | Fallback denyAll | May be 403 due to CSRF or policy; GET handler does not accept POST |

**Key point:** When `GET /api/admin/stats` matches the admin rule but `reader` lacks `ROLE_ADMIN`, the request is denied **immediately at the admin policy**, without falling through to `GET /api/**.authenticated()`.

## 7. Testing with WebTestClient

Integration tests help detect **rule shadowing**: if you only test that `admin` gets 200, you will not know whether `reader` is unintentionally allowed to access admin endpoints. Always test at least one **authorized** user and one **unauthorized** user.

Create `src/test/java/com/example/orderrules/AuthorizationOrderTest.java`:

```java
package com.example.orderrules;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class AuthorizationOrderTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicPingDoesNotNeedAuthentication() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousCannotReadProfile() {
        client.get().uri("/api/profile")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedReaderCanReadProfile() {
        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("Profile reader");
    }

    @Test
    void readerCannotReadAdminRoute() {
        client.get().uri("/api/admin/stats")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanReadAdminRoute() {
        client.get().uri("/api/admin/stats")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-stats");
    }

    @Test
    void readerCanReadOrdersButViewerCannot() {
        client.get().uri("/api/orders/42")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("order-42");

        client.get().uri("/api/orders/42")
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void reportScopeIsMoreSpecificThanAuthenticated() {
        client.get().uri("/api/reports/monthly")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/reports/monthly")
            .headers(h -> h.setBasicAuth(
                "analyst", "analyst-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("monthly-report");
    }

    @Test
    void denyAllRejectsAuthenticatedAdminOnUnlistedPath() {
        client.get().uri("/private/unlisted")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Run from the Gradle project directory:

```bash
./gradlew test --tests '*AuthorizationOrderTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*AuthorizationOrderTest'
```

The 200/401/403 expectations in the test are **expected behavior based on the source code**; you need to run the build in the project to verify them in practice. The test uses a random-port Spring Boot web server and sends real Basic headers, thereby verifying authentication, authority mapping, and authorization together. Do not use `@WithMockUser` as the **sole evidence** that the HTTP Basic parser/password validator works correctly, although mock-user tests are useful when you only want to test policies.

### 7.1 Regression Testing by Intentionally Reversing Order

In `AccessRulesConfig`, try changing:

```java
.pathMatchers(HttpMethod.GET, "/api/**").authenticated()
.pathMatchers(HttpMethod.GET, "/api/admin/**").hasRole("ADMIN")
```

This is **an intentionally wrong change** for learning; keep the other rules, but move the general API rule before admin. Re-run `AuthorizationOrderTest`. The `readerCannotReadAdminRoute` test may start receiving 200 instead of 403, because `reader` is already authenticated. Restore the correct order immediately after the exercise.

A test that only checks "admin accesses admin endpoint and gets 200" **does not catch this vulnerability**, because admin is still permitted in both configurations. Testing **unauthorized users** is especially valuable when reviewing rule order.

### 7.2 401, 403, 404, and 302 Must Be Understood Correctly

- **401 Unauthorized:** typically occurs for unauthenticated requests when using the HTTP Basic entry point.
- **403 Forbidden:** an authenticated user lacks a role/scope, or the request is blocked by CSRF.
- **404 Not Found:** the request passed security, but WebFlux has no handler.
- **302 redirect:** may occur if using a form login entry point, not a sign that the policy is permitting access.

The status also depends on the active security chain, exception handlers, and authentication mechanism. When testing POST, **a 403 from CSRF** does not prove that the authorization rule was evaluated.

## 8. Two Selection Layers: securityMatcher and authorizeExchange

Large applications may have multiple `SecurityWebFilterChain` beans for APIs, browser UIs, or Actuator. In that case, there are **two different ordering mechanisms**:

1. **Selecting the chain:** `WebFilterChainProxy` inspects `SecurityWebFilterChain` beans by `@Order` and `securityMatcher`; a request uses the **first matching chain**.
2. **Selecting the rule inside the chosen chain:** `authorizeExchange` evaluates rules in declaration order; the first matching rule chooses the policy.

```text
GET /api/admin/stats
    |
    +-- @Order(1) apiChain: matcher /api/** -> MATCH -> chain selected
    |      |
    |      +-- admin rule /api/admin/** -> MATCH -> require ROLE_ADMIN
    |      +-- /api/** authenticated    -> not evaluated further
    |
    +-- @Order(2) webChain: match all   -> not selected
```

**Warning:** `anyExchange().denyAll()` in a chain that only matches `/api/**` **does not protect** `/private/**` outside that matcher. Without a fallback chain, requests may bypass Spring Security altogether, even if you think you have `denyAll`.

### 8.1 Multi-Chain Configuration: Alternative Example

The following class is an **alternative example replacing `AccessRulesConfig` in Section 5**—do not declare it at the same time as the single-chain bean unless intentional. To run as a standalone application, a `ReactiveUserDetailsService`/user store is still needed, such as the `users` and `passwordEncoder` beans shown earlier.

```java
package com.example.orderrules;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class MultipleChainsExample {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**")
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }
}
```

Explanation:

- `apiChain` only accepts `/api/**` because of `securityMatcher`. Inside it, the admin rule must come before `anyExchange().authenticated()`.
- `fallbackChain` does not define a `securityMatcher`, so by default it can match any URL **not already selected by a previous chain**.
- If the catch-all chain is placed at `@Order(1)`, it can "swallow" every request, preventing `apiChain` from ever being selected.
- If `fallbackChain` is omitted, paths outside `/api/**` are not protected merely by the `denyAll()` inside `apiChain`.
- If you want Bearer authentication for APIs and form login for browsers, each chain needs its own authentication mechanism and corresponding tests; this does not change the first-match rule at both layers.

## 9. Combining Multiple Permissions in One Policy

Because rules do not automatically combine with AND, if you want to require both `ROLE_FINANCE` **and** `SCOPE_approved`, you can use a custom `ReactiveAuthorizationManager` via `.access(...)`:

```java
.pathMatchers("/api/finance/**")
    .access((authentication, context) ->
        authentication.map(auth -> {
            boolean finance = auth.getAuthorities().stream()
                .anyMatch(a -> "ROLE_FINANCE".equals(a.getAuthority()));

            boolean approved = auth.getAuthorities().stream()
                .anyMatch(a -> "SCOPE_approved".equals(a.getAuthority()));

            return new org.springframework.security.authorization
                .AuthorizationDecision(finance && approved);
        })
    )
```

This is a **snippet inside `authorizeExchange`**, not a complete class. It returns `Mono<AuthorizationDecision>` from the existing authentication. Both authorities must come from a verified authentication provider/IdP, never taken from arbitrary query parameters/headers and self-assigned.

If the policy requires resource access by owner or tenant, additional checks are usually needed in the service layer. Authorization by URL and method only blocks at the **HTTP route level**.

### 9.1 Path Variables and Username-Based Authorization

Matchers can support variables, for example:

```java
.pathMatchers("/api/users/{username}")
    .access((authentication, context) ->
        authentication
            .map(auth -> auth.getName().equals(
                context.getVariables().get("username")
            ))
            .map(org.springframework.security.authorization.AuthorizationDecision::new)
    )
```

This snippet requires a matching `/api/users/{username}` route and that Spring Security has verified the principal. It demonstrates "only allow users to view their own URL", but **is not sufficient** to protect all resources with complex ownership relationships. If a service receives an `objectId` different from `username`, you must verify ownership/tenant against the actual data.

### 9.2 Consequences of Having Multiple Conditions

Need AND/OR? Put that logic **inside one policy**, such as `access(...)`, `@PreAuthorize` method security, or an authorization service. Do not write two `pathMatchers("/same/**")` lines expecting Spring Security to aggregate decisions.

## 10. Mistakes to Catch During Review

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `/api/**.authenticated()` before `/api/admin/**.hasRole("ADMIN")` | `reader` can access admin APIs | Place admin rule before API rule |
| `/**.permitAll()` before `/private/**.denyAll()` | Private endpoints are exposed | Do not use a public matcher covering the whole app |
| `/api/**.denyAll()` before `/api/public/**.permitAll()` | Public resources are blocked | Place public exceptions first |
| `anyExchange().denyAll()` before specific rules | All subsequent rules have no effect | Place fallback at the end |
| Two rules with the same pattern, each checking one permission | Thought to be AND, but only the first rule takes effect | Use `access(...)` / method security |
| `hasRole("ROLE_ADMIN")` | Wrong role prefix with default API | Use `hasRole("ADMIN")` |
| Using `authenticated()` for routes needing tenant/ownership | Other users can read the data | Add resource-level authorization |
| Only writing a success test for `admin` | Misses that `reader` can also access admin | Test denied cases with `reader` |
| Relying on HTTP 403 on POST to prove the rule works | CSRF could be the actual cause | Test CSRF and authorization separately |
| Using `securityMatcher("/api/**")` without a fallback | Paths outside `/api` may be unprotected | Add a catch-all `SecurityWebFilterChain` |
| Catch-all chain placed before API chain | API chain is never selected | Use proper `@Order` and specific matchers |
| Checking routes via frontend URL instead of server | Proxy/base path causes mismatch | Measure actual path/method at the WebFlux server |
| Setting `/actuator/**.permitAll()` unconditionally | Exposes management endpoints | Allowlist genuinely public endpoints only |
| Thinking `permitAll` skips all security filters | Requests with bad credentials/CSRF can still be blocked | Understand the scope is authorization only |
| Assuming a GET pattern covers every method | POST/HEAD/OPTIONS may have different policies | Use method matchers and test thoroughly |
| Using Servlet DSL in WebFlux | Security does not protect the expected runtime | Choose `ServerHttpSecurity` / `SecurityWebFilterChain` |

**Important sign during review:** If a specific rule sits below a broader rule and no request can ever reach the specific rule, that is **rule shadowing**. The vulnerability is easy to miss because Java still compiles and positive tests for authorized users still pass.

## 11. Self-Check Exercises

**Question 1.** Given the configuration:

```java
.pathMatchers("/api/**").authenticated()
.pathMatchers("/api/admin/**").hasRole("ADMIN")
```

Can a logged-in `reader` access `/api/admin/stats`?

**Answer:** Yes, they can. The `/api/**` rule matched first, so the `authenticated` policy lets them through. Move the admin rule above it.

**Question 2.** Why does writing `.pathMatchers("/api/reports/**").hasAuthority("SCOPE_reports.read")` right **after** `/api/**.authenticated()` fail to protect reports by scope?

**Answer:** The general API matcher matches first, shadowing the reports rule. Scope-specific rules must be placed before general rules.

**Question 3.** Do two rules with the same `/api/finance/**` pattern—one `hasRole(FINANCE)` and one `hasAuthority(SCOPE_approved)`—enforce both?

**Answer:** No. Only the policy of the first matching rule is evaluated. Use `access(...)` for combined conditions.

**Question 4.** Which authority does `hasRole("ADMIN")` check by default?

**Answer:** `ROLE_ADMIN`. In `User.withUsername(...).roles("ADMIN")`, the builder creates the corresponding authority.

**Question 5.** Does `anyExchange().denyAll()` in a chain that only matches `/api/**` deny `/private/home`?

**Answer:** No; the request must match the **chain** first before that chain's `anyExchange` runs. A fallback chain is needed.

**Question 6.** Does an authenticated POST with the required role receiving 403 prove the deny rule executed?

**Answer:** Not yet. The CSRF filter may block a POST missing a token. CSRF and policy must be tested separately.

**Question 7.** Why does passing `adminCanReadAdminRoute` not prove that rule ordering is safe?

**Answer:** When an `authenticated` rule shadows an admin rule, `admin` still passes **and `reader` may also pass**. Testing that `reader` receives 403 proves the admin restriction is active.

**Question 8.** Will a GET URL with no handler that falls into `anyExchange().denyAll()` necessarily return 404?

**Answer:** No. Security can deny with 401/403 before routing determines there is no handler.

## 12. Implementation Checklist

- [ ] Using genuine WebFlux reactive, not confusing it with Spring MVC/Servlet DSL.
- [ ] `authorizeExchange` clearly defines policies by path and HTTP method.
- [ ] Truly necessary public rules are declared specifically, without using `/**.permitAll()`.
- [ ] Sensitive rules (admin, reports, internal data) come before `/api/**` or general matchers.
- [ ] `anyExchange().denyAll()` or a safe fallback is placed at the end of the chain.
- [ ] Understand that the first matching matcher determines the evaluated policy, rather than aggregating multiple policies.
- [ ] `hasRole`, `hasAuthority`, and role/scope mappings match the identity model.
- [ ] If multiple chains exist, `@Order`, `securityMatcher`, and the catch-all chain have been verified.
- [ ] Tests exist for **anonymous**, **authorized user**, and **unauthorized user** on sensitive endpoints.
- [ ] 403 tests for POST/DELETE have ruled out CSRF confusion.
- [ ] Browser OPTIONS/CORS, actuator, reverse proxy, and base path are handled properly.
- [ ] Resource ownership/tenant authorization is checked where actual data resides.
- [ ] No demo credentials or HTTP Basic without TLS are used in production.
- [ ] The system has logging and monitoring to detect unauthorized access without leaking passwords/tokens.

**Conclusion:** `ServerHttpSecurity.authorizeExchange` is the HTTP authorization DSL in Spring Security reactive. **Rule order is itself part of the security policy**: the first matcher that matches a request decides the access condition. Place specific/sensitive rules before broad matchers, finish with a safe fallback, and test **unauthorized users** as well. When there are multiple `SecurityWebFilterChain`s, you must also inspect the chain-selection layer using `securityMatcher` and `@Order`; `anyExchange` only evaluates requests that enter that chain.

### Official Documentation

- [Spring Security — Authorize ServerHttpRequest (reactive)](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Security and Multiple SecurityWebFilterChain](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security 6.5 — ServerHttpSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — Reactive method security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Reactive test support](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
