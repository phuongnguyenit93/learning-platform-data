# `anyRequest`, `anyExchange`, and Policies for Remaining Paths

> **Spring Security fundamentals → Endpoint protection.** In an application with many API routes, rules for `/public/**`, `/api/**`, or `/admin/**` usually cover only a subset of requests. This lesson explains how to choose the **final** rule for unmatched requests, distinguishes Servlet's `anyRequest()` from WebFlux's `anyExchange()`, and prevents leaving paths unprotected when an application has multiple security filter chains.

## 1. Starting Question: What Happens to Requests Not Matching Specific Rules?

Suppose an application has three URLs:

- `GET /public/ping`: allowed for everyone.
- `GET /api/profile`: requires login.
- `GET /api/admin/report`: requires the ADMIN role.

After a deployment, the team adds `GET /internal/diagnostic` without yet deciding who is allowed to call it. What matters is the **policy applied to the new URL**, even when the controller already exists.

With standard configuration, there are two clear choices:

```java
// Servlet / Spring MVC
.anyRequest().authenticated()
```

This line requires all **remaining requests inside the selected chain** to carry an authenticated identity. A logged-in user can still pass through the HTTP layer into a new endpoint if there are no additional checks.

```java
// Reactive / Spring WebFlux
.anyExchange().denyAll()
```

This line denies all **remaining exchanges inside the selected chain**. A new endpoint is not accidentally exposed when the team forgets to add a rule for it.

Both `anyRequest()` and `anyExchange()` are **catch-all authorization matchers**. They do not decide which chain applies, do not authenticate users by themselves, and do not replace CSRF, business permission, or data-level permission checks. They answer one specific question: **"When none of the preceding authorization matchers match, what policy applies?"**

## 2. Mastering the Three Decision Layers

A request goes through three distinct logical steps:

```text
HTTP request / WebFlux exchange
           |
           v
[1] Select the matching security filter chain
    - Servlet: SecurityFilterChain + securityMatcher(...)
    - WebFlux: SecurityWebFilterChain + securityMatcher(...)
           |
           v
[2] Evaluate authorization rules in order
    - requestMatchers(...) / pathMatchers(...)
    - Only the first matching rule decides here
    - Finally: anyRequest(...) / anyExchange(...)
           |
           v
[3] If allowed: controller → service → data
    - Method security and object/tenant scope still apply
```

Here are three concepts that are often confused:

| Concept | Servlet/MVC | WebFlux/reactive | Meaning |
|---|---|---|---|
| Select chain | `HttpSecurity.securityMatcher(...)` | `ServerHttpSecurity.securityMatcher(...)` | Does this chain handle the request/exchange? |
| An authorization rule | `authorizeHttpRequests(...).requestMatchers(...)` | `authorizeExchange(...).pathMatchers(...)` | For a request in the chain, which rule matches? |
| Final fallback rule | `anyRequest()` | `anyExchange()` | Which rule handles the **unmatched** remainder in the chain? |
| Allow all | `permitAll()` | `permitAll()` | This rule requires no permissions to pass the authorization step |
| Require login | `authenticated()` | `authenticated()` | Requires an authenticated principal; does not prove business permissions |
| Deny all | `denyAll()` | `denyAll()` | This rule denies regardless of roles/authorities |

**Scope is critical:** An `anyRequest().denyAll()` inside a chain that only applies to `/api/**` does **not** automatically protect `/internal/**`. If `/internal/**` does not match any chain, Spring Security may not participate in protecting that request. You need a fallback chain covering all remaining requests.

## 3. Servlet: `anyRequest()` in `authorizeHttpRequests`

### 3.1. Configuring from Specific to General

The illustrative Java snippet below sits inside a Spring configuration/bean and is not a standalone program:

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/admin/report")
                .hasRole("ADMIN")
            .requestMatchers(HttpMethod.GET, "/api/profile")
                .authenticated()
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

What happens when a request arrives:

1. Spring Security evaluates matcher → authorization pairs **in declaration order**.
2. If the request matches `GET /public/ping`, `permitAll` applies; it does not continue to `anyRequest`.
3. If it matches `GET /api/admin/report`, `ROLE_ADMIN` is required per the default role prefix.
4. If it matches `GET /api/profile`, only login is required at the HTTP layer.
5. If none of the rules above match, `denyAll` applies.

`anyRequest()` should be placed **last** in the rule chain. Because it catches everything remaining, placing it before specific rules leaves later rules with no chance to run, and the DSL API may reject such configuration.

Note that `requestMatchers(HttpMethod.GET, ...)` distinguishes methods: a `POST /api/profile` request **does not match** the GET rule and falls through to the fallback, even though the path is identical. If a matcher specifies only a path, it can apply to multiple HTTP methods. When designing sensitive APIs, define supported verbs explicitly and test this behavior separately.

### 3.2. Is `anyRequest().authenticated()` Safe Enough?

`authenticated()` fits when **every endpoint without its own rule is intentionally expected to require only login**, such as an intranet with strict method-level security. However, if the team accidentally adds `/internal/diagnostic` and forgets to record a policy, any regular logged-in user can reach that endpoint.

Comparing catch-alls:

| Catch-all | Anonymous user | Logged-in user | Typical purpose |
|---|---|---|---|
| `anyRequest().permitAll()` | Passes authorization step | Passes authorization step | Application truly intends all remaining URLs to be public; rarely appropriate for sensitive APIs |
| `anyRequest().authenticated()` | Prompted to authenticate | Passes HTTP authorization step | All remaining endpoints are intended for logged-in users |
| `anyRequest().hasRole("ADMIN")` | Insufficient privileges | Only ADMIN passes | All remaining endpoints are uniformly designed as an ADMIN area |
| `anyRequest().denyAll()` | Denied | Denied | **Allowlist / deny by default**: only declared routes are open |

**General recommendation for APIs with varying sensitivity:** explicitly declare public endpoints, authenticated endpoints, and permission-protected endpoints; end with `anyRequest().denyAll()`. For applications that intentionally stipulate "all undeclared routes remain for logged-in users," `authenticated()` is a deliberate choice, but the risk of widening access when adding endpoints must be documented.

### 3.3. Broad Rules Can Shadow Narrow Rules

**Policy-broken configuration:**

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll())
```

`GET /api/admin/report` already matches `/api/**` on the first line, so the ADMIN rule below is never evaluated. Simply logging in is enough to bypass the **HTTP rule**. Even if the service still blocks it with method security, this configuration is a bug that needs fixing.

**Correct priority order:**

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
```

The specific rule is placed before the broad rule. Still, `/api/**` automatically covers **every new API in that namespace**. If the goal is to allow only approved endpoints, choose specific path + HTTP method matchers and a `denyAll` catch-all rather than an overly broad wildcard.

## 4. Reactive: `anyExchange()` in `authorizeExchange`

Spring WebFlux uses `SecurityWebFilterChain` and `ServerHttpSecurity`. An HTTP exchange holds the request/response and reactive context, while `anyExchange()` plays the equivalent role of `anyRequest()` in authorization rules.

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/admin/report")
                .hasRole("ADMIN")
            .pathMatchers(HttpMethod.GET, "/api/profile")
                .authenticated()
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Points to remember:

- `authorizeHttpRequests` + `requestMatchers` + `anyRequest` belong to **Servlet**; `authorizeExchange` + `pathMatchers` + `anyExchange` belong to **WebFlux**. Do not swap APIs directly between the two stacks.
- Reactive authorization integrates with the WebFlux filter chain and Reactor Context–based security; it does not rely on Servlet `HttpServletRequest`/`SecurityContextHolder` for the whole pipeline.
- Ordering from specific rules to the catch-all, the meanings of `permitAll/authenticated/denyAll`, and route-based authorization requirements remain similar.
- Evaluating `anyExchange` also **only happens after the exchange has been selected by a `SecurityWebFilterChain`**.
- Using `Mono`/`Flux` in a controller does not determine the security stack by itself: confirm whether the app boots Spring MVC or WebFlux. When a Boot project includes both web MVC and webflux starters, Boot usually prefers MVC unless configured otherwise.

Distinguishing the two "matches" is very helpful when debugging:

```text
WebFlux exchange GET /api/profile
  ├─ Does a SecurityWebFilterChain match the exchange?
  │    └─ Yes → authorizeExchange
  │          ├─ GET /public/ping? No
  │          ├─ GET /api/admin/report? No
  │          ├─ GET /api/profile? Yes → authenticated
  │          └─ anyExchange? No longer evaluated
  └─ No → Not protected by this chain;
          check other chains / catch-all chain
```

## 5. Runnable Example: Servlet / Spring Boot 3.x / Java 17+

This example demonstrates that **an endpoint already declared in a controller is still blocked** by `anyRequest().denyAll()` if no authorization rule opens it. To run, create a Spring Boot 3.x project using Java 17+ from Spring Initializr and choose Gradle.

### 5.1. Dependencies

In the `build.gradle` of the generated Spring Boot project, include this block:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This snippet is the **dependencies block**, not the entire `build.gradle`; keep the plugins, repositories, and Java toolchain provided by Spring Initializr.

### 5.2. Application Class and Security Rules

Place `src/main/java/example/fallback/mvc/MvcFallbackApplication.java`:

```java
package example.fallback.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class MvcFallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcFallbackApplication.class, args);
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "mvc public";
    }

    @GetMapping("/api/profile")
    public String profile() {
        return "mvc profile";
    }

    @GetMapping("/api/admin/report")
    public String adminReport() {
        return "mvc admin report";
    }

    // Endpoint genuinely exists but has NO rule granting access.
    @GetMapping("/internal/diagnostic")
    public String diagnostic() {
        return "should not be exposed";
    }

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo123")
            .roles("READER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}demo123")
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(reader, admin);
    }
}
```

`{noop}` is a non-hashing password encoder, **for local demonstration only**; production needs password hashing, TLS, and proper identity management. Demo users: `reader/demo123` has `ROLE_READER` and `admin/demo123` has `ROLE_ADMIN`.

### 5.3. Terminal Experiments

In the project directory, run:

```bash
./gradlew bootRun
```

On Windows run `gradlew.bat bootRun`. For simplicity, assume default port 8080 and no other filters/routes.

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/profile
curl -i -u reader:demo123 http://localhost:8080/api/profile
curl -i -u reader:demo123 http://localhost:8080/api/admin/report
curl -i -u admin:demo123 http://localhost:8080/api/admin/report
curl -i -u admin:demo123 http://localhost:8080/internal/diagnostic
```

| Request | Expected | Reason |
|---|---|---|
| Anonymous `GET /public/ping` | 200, `mvc public` | `permitAll` rule |
| Anonymous `GET /api/profile` | 401 with HTTP Basic | `authenticated` rule |
| Reader `GET /api/profile` | 200, `mvc profile` | Authenticated |
| Reader `GET /api/admin/report` | 403 | Missing `ROLE_ADMIN` |
| Admin `GET /api/admin/report` | 200, `mvc admin report` | Has `ROLE_ADMIN` |
| Admin `GET /internal/diagnostic` | 403 | Real route, but falls into `anyRequest().denyAll()` |

Here we intentionally test `/internal/diagnostic` as a **route that has a controller**. Calling only a non-existent URL can produce responses affected by MVC routing, error dispatches, or error pages, making it hard to distinguish "blocked by Security" from "handler not found." Do not rely on default bodies or every header from `curl -i` since they vary by version and configuration.

### 5.4. Regression Testing with MockMvc

Create `src/test/java/example/fallback/mvc/MvcFallbackTest.java`:

```java
package example.fallback.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class MvcFallbackTest {
    @Autowired MockMvc mvc;

    @Test
    void protectedAndFallbackRoutes() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("mvc public"));

        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/profile")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/admin/report")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin/report")
                .with(httpBasic("admin", "demo123")))
            .andExpect(status().isOk());

        // Decisive negative case: admin is also blocked on an undeclared URL.
        mvc.perform(get("/internal/diagnostic")
                .with(httpBasic("admin", "demo123")))
            .andExpect(status().isForbidden());
    }
}
```

Run `./gradlew test` or `gradlew.bat test`. The test uses the real Spring context and security filters, making it more meaningful than unit tests calling the controller directly (bypassing the filter chain). The test above checks GET routes; for POST/PATCH/DELETE, also test CSRF, HTTP methods, and business authorization.

## 6. Runnable Example: Reactive / Spring WebFlux / Java 17+

The second example must be in an **independent Boot project** separate from the Servlet example. If both run simultaneously, configure different ports. Create a Spring Initializr Boot 3.x project, Java 17+, **selecting only the WebFlux starter** as the web stack.

### 6.1. Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 6.2. Reactive Application and `anyExchange()`

Place `src/main/java/example/fallback/reactive/ReactiveFallbackApplication.java`:

```java
package example.fallback.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class ReactiveFallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveFallbackApplication.class, args);
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("reactive public");
    }

    @GetMapping("/api/profile")
    public Mono<String> profile() {
        return Mono.just("reactive profile");
    }

    @GetMapping("/api/admin/report")
    public Mono<String> adminReport() {
        return Mono.just("reactive admin report");
    }

    @GetMapping("/internal/diagnostic")
    public Mono<String> diagnostic() {
        return Mono.just("should not be exposed");
    }

    @Bean
    SecurityWebFilterChain webfluxSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo123")
            .roles("READER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}demo123")
            .roles("ADMIN")
            .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }
}
```

The controller returns `Mono<String>` to illustrate a reactive return type; `Mono.just` here involves no I/O, so do not use it as a performance benchmark. What matters is that HTTP rules live in `SecurityWebFilterChain`, not Servlet `SecurityFilterChain`.

Run `./gradlew bootRun` and call the URLs as in section 5.3 while the WebFlux project listens on port 8080. Decision outcomes are equivalent, with bodies on the three valid endpoints prefixed with `reactive`. Notably, admin accessing `/internal/diagnostic` is still denied due to `anyExchange().denyAll()`.

### 6.3. Testing with `WebTestClient`

Place `src/test/java/example/fallback/reactive/ReactiveFallbackTest.java`:

```java
package example.fallback.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveFallbackTest {
    @Autowired WebTestClient client;

    @Test
    void rulesAndCatchAll() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reactive public");

        client.get().uri("/api/profile")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("admin", "demo123"))
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/internal/diagnostic")
            .headers(h -> h.setBasicAuth("admin", "demo123"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Run `./gradlew test` (Windows: `gradlew.bat test`). Testing with an HTTP client against a random port with real authentication avoids relying on assumptions that a method is blocked just because configuration looks right.

## 7. Multiple Security Filter Chains: An In-Chain Catch-All Is Not Enough

This is the most easily overlooked architectural gap.

### 7.1. Servlet: `securityMatcher` vs. `requestMatchers`

Suppose there are two chains: an API chain using HTTP Basic and a web chain using form login. Selection logic:

```text
GET /api/reports
  → @Order(1) chain with securityMatcher("/api/**") → matches
  → evaluates requestMatchers inside the API chain
  → if no specific rule matches, anyRequest applies to the API

GET /internal/diagnostic
  → @Order(1) chain with securityMatcher("/api/**") → does not match
  → evaluates the second chain if one exists
  → if no suitable second chain exists, the request risks
    not being protected by Spring Security.
```

Example of **two beans replacing the single security bean in section 5**; do not add alongside that bean:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/profile")
                .authenticated()
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        // No securityMatcher set: this chain can match
        // any request not matched by higher-priority chains.
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Requires `import org.springframework.core.annotation.Order` alongside the Spring Security imports in the MVC example. The snippet above illustrates a multi-chain structure and is **not a standalone runnable Java class**. In a real project, check the bean count, `@Order` ordering, chain matchers, and auth mechanisms of each chain.

If you write `apiChain` with only `securityMatcher("/api/**")` and `anyRequest().denyAll()`, it blocks unknown routes **within /api/**, but makes no decision for `/admin/**`, `/internal/**`, or `/actuator/**`. A fallback chain **without a restricting `securityMatcher`** is the layer covering everything else.

### 7.2. Reactive: `securityMatcher` Also Selects the Chain Before `anyExchange()`

WebFlux supports multiple `SecurityWebFilterChain` beans, selected by `securityMatcher` and precedence. An equivalent illustrative structure:

```java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(ex -> ex
            .pathMatchers("/api/profile").authenticated()
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/public/**").permitAll()
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Requires additional imports `org.springframework.core.annotation.Order` and `org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers` alongside the imports in section 6. This is an **illustrative configuration snippet**, replacing the single chain in the WebFlux example; do not paste it directly into a class that already has a bean for the same purpose.

**Key point:** `securityMatcher` is the **chain-selection condition**; `pathMatchers`/`requestMatchers` and the catch-all are **rules inside the chain**. If no chain matches, `anyExchange` or `anyRequest` in non-matching chains cannot save you.

### 7.3. When Should the Fallback Chain Use `denyAll` vs. `authenticated`?

If high-level chains cover most business routes and everything else must be approved before opening, choose **`denyAll`**. If a dedicated web group has many valid dynamic pages and every remaining page is expected to require login, **`authenticated`** can be a deliberate policy. Either way, have **a final chain covering the entire application**, without accidentally restricting it to a prefix.

## 8. "Remaining Paths" Does Not Always Mean HTTP 404

Between HTTP authorization and request routing lie two questions:

- **Is the request protected and allowed to proceed?** Spring Security decides this via chains and rules.
- **Is there a controller/static resource/handler for the URL?** Spring MVC or the WebFlux router decides that.

For example, `GET /does-not-exist` has no controller, yet a `denyAll` catch-all can reject it before the router determines 404. Unauthenticated callers may see a 401 entry point, while authenticated callers usually receive 403 when denied. Actual status/body depend on the authentication entry point, exception handling, dispatches, filter chain, and framework version. Do not rely on "the URL does not exist so it will definitely be 404" to conclude security is working.

If business requirements call for **404 on non-existent routes** while still denying unapproved routes, design routing/error handling explicitly and weigh information-disclosure risks. Do not open wildcard `permitAll` just to make the 404 page look nicer.

### 8.1. Servlet ERROR/FORWARD Dispatches

Spring Security can authorize not only the initial request but also `ERROR`/`FORWARD` dispatches. For example, a controller error causes Spring Boot to dispatch to `/error`; if `anyRequest().denyAll()` blocks the second dispatch, a 500 or 404 response can turn into 403 and become hard to debug.

A **conditional** option, when genuinely needed for the app's error/forward rendering mechanism:

```java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.ERROR,
        DispatcherType.FORWARD
    ).permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().denyAll())
```

Import `jakarta.servlet.DispatcherType`. Allow only the necessary dispatcher types and test the output; this does not make initial `REQUEST`s public, but you still must evaluate interactions with custom filters/forwards. Do not open `/error` across all dispatchers without understanding the architecture.

### 8.2. CORS Preflight, CSRF, Login, and Static Assets

- Browsers can send `OPTIONS` preflight before the actual request. Configure **CORS** with proper origins/headers/methods and integration order rather than letting all `OPTIONS` pass by default just because the catch-all caused errors. CORS does not replace authentication/authorization.
- `POST`/`PUT`/`PATCH`/`DELETE` may be checked by **CSRF** when using cookies/sessions, even if an HTTP authorization matcher would allow them. When a test is rejected, determine whether the cause is a rule or CSRF. Do not disable CSRF just to make tests pass easily.
- When using form login, allow the login endpoint and appropriate supporting paths. For static CSS/JS, usually apply `permitAll` to public resources **inside the security chain**, rather than bypassing the entire chain with `web.ignoring()`, in order to preserve security headers.
- Actuator/health/metrics may use a management context/port or separate endpoints. Do not permit `/actuator/**` out of habit; expose only health/public level per real operational policy, protecting sensitive metrics/config/heapdump endpoints.
- WebSocket handshakes, SSE, management routes, forwarded paths, and proxy rewrites need dedicated tests. The HTTP catch-all is only one part of the protection system.

## 9. How to Design a Fallback Without Accidentally Locking Down the App

A `denyAll` policy has no logical flaw, yet it can block legitimate features if the team fails to list everything: login, logout, error renderer, static assets, health probes, or OAuth2 callbacks. Do not solve this by opening `anyRequest().permitAll()`, because then every unthought-of endpoint becomes public too.

Practical workflow:

1. **Build an inventory**: list URLs/verbs from controllers, static resources, authentication callbacks, actuator, management port, gateway routing, and other services.
2. **Tier the policy**: exact public; authenticated; role/authority; deny by default; object-level and method-level authorization where needed.
3. **Order rules by specificity**: admin endpoints before API wildcards; path + method where needed; dispatcher/infra exceptions reviewed individually.
4. **Choose chains and fallbacks**: with multiple chains, declare explicit precedence and ensure a final chain covers the entire app; each chain has a suitable authorization catch-all.
5. **Keep new routes private by default**: for newly added unapproved URLs, choose deny; opening them must accompany policy and tests.
6. **Verify both happy paths and denials**: if tests only see 403 for every request, the app may be misconfigured and locked down; if they only see 200, there is a risk of over-exposure.
7. **Record policy owners**: who reviews requests to open endpoints, who reviews admin permissions, and who owns regression tests.

### 9.1. Decision Matrix by Product Goal

| Scenario | Potentially suitable fallback policy | Notes |
|---|---|---|
| REST API handling sensitive data | `denyAll` | Open endpoints only via a reviewed allowlist |
| Internal portal where all other routes are for logged-in users | `authenticated` | Must have method/object authorization and an inventory of new routes |
| Standalone public static website | `permitAll` in an intentionally public chain | Do not share blanket rules with private APIs |
| Admin area allowing no unlisted routes | `denyAll` | Avoid wildcard `/admin/**` `authenticated` |
| One chain handling only `/api/**` | In-chain catch-all + final system-wide chain | Do not mistake `anyRequest` in the API chain for an app-wide fallback |
| Mix of browser sessions + bearer APIs | Multiple chains may be used | Must preserve login/CSRF, sessions, stateless auth, and per-chain fallback |

There is no "one-size-fits-all" catch-all for every application; there is only a choice that is **explicitly declared, explainable, and tested along the right execution paths**.

## 10. Common Mistakes and How to Spot Them

| Mistake/misconception | Consequence | Fix |
|---|---|---|
| Putting `anyRequest`/`anyExchange` before detailed rules | Later rules never run or config is invalid | Place catch-all last |
| Putting `/api/**` authenticated before `/api/admin/**` ADMIN | Regular users pass the admin HTTP guard | Put specific rule first |
| Using `anyRequest().permitAll()` "for convenience" | New URLs can become unintentionally public | Use `permitAll` only for public routes; fallback `denyAll` |
| Using `anyRequest().authenticated()` thinking all endpoints are strictly authorized | Logged-in users can call new sensitive endpoints | Check action/data permissions; consider `denyAll` |
| Thinking `anyRequest` protects paths outside `securityMatcher` | URLs can fall outside all chains | Add a fallback chain covering the entire application |
| Testing only non-existent URLs | 404/401/403 from router/dispatch causes confusion | Test a **real existing endpoint** without an authorization rule |
| Opening `/error` too broadly | Exposes unintended paths or masks auth errors | Check dispatcher type; permit only when needed |
| Making all `OPTIONS` public without checking CORS | Weak CORS configuration | Design a CORS policy; test real preflight |
| POST test gets 403 and blaming fallback | May be CSRF before authorization | Use a test with valid CSRF to isolate the rule |
| Mixing Servlet DSL with WebFlux DSL | Code fails to compile or wrong security stack | Verify stack before choosing matchers/chains |
| Ignoring path rewrites/context paths | Rules do not match real deployment | Check URLs from the framework's perspective behind proxies |
| Protecting only HTTP, forgetting service/data | Internal calls or other IDs still access wrong data | Combine method security and object scope |

## 11. Required Test Suite When Changing Routes

When adding, renaming, moving, or deleting endpoints, reviews should run a matrix of **route × HTTP method × anonymous/user/admin × chain × expected decision**. At minimum prove:

- **Public endpoint**: `GET /public/ping` still returns 200 without login.
- **Authenticated endpoint**: anonymous is blocked; logged-in reader/admin succeed on `GET /api/profile`.
- **Privileged endpoint**: reader gets 403, admin gets 200 on `GET /api/admin/report`.
- **Real fallback endpoint**: admin still cannot access `GET /internal/diagnostic` if the route has no rule; this is a negative test against forgotten policies.
- **Unknown path**: verify expected 401/403/404 behavior per contract and dispatch type; do not substitute an unknown path for a fallback route test.
- **Other methods**: same path with an undeclared verb must be blocked per policy, even when the controller supports that verb.
- **Multiple chains**: requests for each prefix enter the right chain; a URL outside an earlier chain's prefix is still handled by the final catch-all chain.
- **Authentication mode**: HTTP Basic, form login, bearer JWT, session/cookie if present; do not confuse unauthorized with forbidden.
- **POST + CSRF**: valid token checks authorization properly; missing/invalid token is blocked by exploit protection.
- **Real deployment**: context path, proxy rewrite, actuator/management port, static assets, error/forward, CORS preflight.

Add tests to the CI pipeline whenever policy changes. Negative tests usually catch matcher order bugs, chain scope issues, and authenticated/authorized confusion far better than reading config alone.

## 12. Checklist Before Approving a Remaining-Paths Policy

- [ ] Identified the exact web stack: Spring MVC/Servlet or WebFlux/reactive.
- [ ] Used the right DSL pair: `authorizeHttpRequests/anyRequest` or `authorizeExchange/anyExchange`.
- [ ] Specific matchers are declared before broad matchers and the catch-all.
- [ ] HTTP methods are included in matchers when policy depends on method.
- [ ] Final rule is `denyAll` / `authenticated` / `permitAll` with documented rationale and owner.
- [ ] `permitAll` applies only to genuinely public endpoints; no wildcards accidentally exposing data.
- [ ] With multiple chains, `securityMatcher` and `@Order` are reviewed; final chain covers remaining requests.
- [ ] No new sensitive controller/service relies solely on `authenticated`.
- [ ] Method/object/tenant-level authorization rules remain independent and complete.
- [ ] Error/forward dispatches, CORS, CSRF, static assets, actuator, login/logout tested under realistic conditions.
- [ ] Regression test exists for the fallback on a **real route** with the highest-privilege role.
- [ ] Decisions are documented and tests updated whenever endpoints are added.

**Practical conclusion:** In Servlet, use `anyRequest()`; in WebFlux, use `anyExchange()` to decide what happens to remaining requests/exchanges **within the selected security filter chain**. Put them at the end of the rule list; consider `denyAll()` when you want to approve each endpoint explicitly, and ensure there is a **final chain without a restricting matcher** so paths outside a prefix do not slip through. A good fallback is only valuable when tested across allowed routes, real unpermitted routes, and the scope of all chains.

## 13. Official Documentation

- [Spring Security — Authorize HTTP Requests, Servlet](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matcher order, `permitAll`, `denyAll`, `anyRequest`, dispatcher types.
- [Spring Security — Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher` vs `requestMatchers` and fallback chains.
- [Spring Security — Authorize ServerHttpRequest, Reactive](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `pathMatchers`, `anyExchange`.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): multiple `SecurityWebFilterChain` beans and chain selection rules.
- [Spring Security — MockMvc Support](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): testing requests with Spring Security.
- [Spring Security — WebTestClient Support](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html): testing reactive endpoints and authentication.

Examples use Spring Boot 3.x / Spring Security 6.x and Java 17+; verify APIs against the actual dependency versions in your application.
