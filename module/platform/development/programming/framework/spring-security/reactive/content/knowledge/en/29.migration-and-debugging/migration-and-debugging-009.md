# Diagnosing Unmatched Security Chains or Rules Shadowed by Ordering in Spring Security WebFlux

> **Context:** Spring Boot 3.x, Spring Security 6.x, Java 17+, and **WebFlux/reactive**. This lesson focuses on `SecurityWebFilterChain`, `ServerHttpSecurity`, `ServerWebExchangeMatcher`, `authorizeExchange`, and `WebTestClient`. Avoid confusing these with Servlet configurations (`HttpSecurity`, `SecurityFilterChain`, `requestMatchers`, `MockMvc`).

A common security bug when migrating from Servlet to WebFlux or splitting API and web configurations is: the code declares a rule for `/api/admin/**`, yet regular users can still invoke the admin API; or `permitAll("/api/public")` is configured, yet the endpoint returns 401; or an endpoint still responds without login because **no security chain covers that URL**. Looking at a single `.hasRole(...)` line in isolation is not enough: first you must know **which chain the request entered and which rule was actually chosen**.

## 1. Objectives

After this lesson, you will be able to:

1. Describe the two matching layers: selecting a `SecurityWebFilterChain`, then selecting a rule inside `authorizeExchange`.
2. Detect a higher-priority chain "swallowing" requests meant for a lower-priority chain, an overly narrow `securityMatcher`, and gaps missing a catch-all chain.
3. Detect specific rules shadowed by broader rules, such as `/api/**` placed ahead of `/api/admin/**`.
4. Distinguish matching bugs from authentication failures, missing authorities, CSRF, missing routes, OAuth2 redirects, and method security.
5. Use `WebTestClient` to build a request/identity/HTTP-status matrix and read logs to prove the bug is fixed.
6. Migrate legacy configurations to WebFlux while preserving the exact intended permission policy.

## 2. Two Matching Layers: "Which Chain?" and "Which Rule?"

### 2.1. Decision Model

```text
HTTP request (method, path, headers, principal...)
                       |
                       v
          Spring Security WebFilterChainProxy
                       |
            List of SecurityWebFilterChains
                  ordered by @Order
                       |
                try securityMatcher
                       |
            +----------+-----------+
            |                      |
        No match              First match
            |                      |
     try next chain         Pick ONLY this chain
            |                      |
       No chain left?       auth filters, CSRF, ...
            |                      |
  Unprotected by               authorizeExchange:
  these chains             evaluate rules IN ORDER
                                   |
                           first matching rule
                                   |
                        permitAll / authenticated /
                        hasRole / hasAuthority / denyAll
                                   |
                          WebFlux handler / controller
```

Those two layers are independent:

- **Layer 1 – chain selection:** each `SecurityWebFilterChain` bean has its own matcher (declared via `http.securityMatcher(...)`). Spring Security iterates chains in priority order and uses the **first matching chain**. A request never "runs through every chain" to accumulate rules. `@Order(1)` has higher priority than `@Order(2)`; `Ordered.HIGHEST_PRECEDENCE` precedes normal numeric values.
- **Layer 2 – rule selection:** inside the chosen chain, `.authorizeExchange(...)` evaluates matchers/rules in **declaration order**. The first matching rule sets the permission requirement; later rules never get a chance to evaluate that request.
- **Layer 3 – enforcement mechanism:** authentication (`httpBasic`, OAuth2 Login, Bearer JWT/opaque), CSRF, headers, and other filters belong to that selected chain. Controllers and `@PreAuthorize` may add application-layer checks afterwards.

For example, on `GET /api/admin/report`, if a catch-all web chain sits ahead of the API chain, the `hasRole("ADMIN")` rule inside the API chain **is never evaluated**. If the API chain is selected yet `.pathMatchers("/api/**").authenticated()` precedes `.pathMatchers("/api/admin/**").hasRole("ADMIN")`, the ADMIN requirement is likewise shadowed.

### 2.2. Differences Between Three Easily Confused Concepts

| Mechanism | Where does it live? | What does it decide? | Which change fixes a bug? |
| --- | --- | --- | --- |
| `@Order` on a `SecurityWebFilterChain` bean | Outside the chain | Which chain is evaluated first | Place narrow chains ahead of the catch-all chain |
| `ServerHttpSecurity.securityMatcher(...)` | Chain definition | Which URLs/methods belong to this chain's scope | Fix the matcher to cover the exact target endpoints |
| `.authorizeExchange().pathMatchers(...)` | Inside the chosen chain | Whether the request is permitted, requires login, needs authority, or is denied | Place specific rules ahead of broad rules; `anyExchange` last |
| `SecurityWebFiltersOrder` / `.addFilterAt(...)` | Inside the filter pipeline | Ordering of WebFilters such as authentication and authorization | Adjust only when building custom filters; **never replaces** fixing the two matching layers |
| `@Order` on a custom `WebFilter` | General WebFlux WebFilter layer | Position of a custom `WebFilter` in the pipeline | Do not use to fix shadowed rules or chains |

With Java/WebFlux, **do not** port Servlet examples like `HttpSecurity.securityMatcher(...)`, `authorizeHttpRequests(...)`, or `FilterSecurityInterceptor` verbatim. Class names and mechanisms differ in WebFlux, even though the first-match principle is similar.

## 3. "Wrong Chain Matched" Bugs

### 3.1. Catch-All Chain Placed Ahead of the API Chain

**Wrong – illustrative code snippet:**

```java
@Bean
@Order(1)
SecurityWebFilterChain website(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex
                    .pathMatchers("/api/admin/**").hasRole("ADMIN")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(
                    Customizer.withDefaults()))
            .build();
}
```

Here the `website` chain declares no `securityMatcher`: by default its matcher matches every request. Because it has `@Order(1)`, even `/api/admin/report` goes into `website`. The `@Order(2)` API chain handles zero URLs already matched by `website`; Bearer JWTs may never even be decoded despite being valid.

**Right:** give the API chain with `securityMatcher("/api/**")` higher priority, and place the catch-all website chain last. Reordering alone is **insufficient** if the API chain still omits routes that need protection.

### 3.2. Chain Matcher Too Narrow

**Wrong:**

```java
.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/public/**"))
.authorizeExchange(ex -> ex
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().permitAll())
```

The `/api/admin/**` rule sits outside the `/api/public/**` chain scope, so it never runs. Such configuration can mislead readers into believing admin URLs are protected when they actually fall into another chain or outside every chain.

**Right:** make `securityMatcher` cover the **entire chain scope**, such as `/api/**`, then split `/api/public` and `/api/admin/**` permissions inside it.

### 3.3. Two Chains with Overlapping Scopes

Example:

```text
Chain A @Order(1): /api/**
Chain B @Order(2): /api/admin/**
Chain C @Order(3): match all
```

`/api/admin/report` matches both A and B, yet **A wins**. Chain B looks very specific, yet can never intercept that request.

There are two sound designs:

1. If admin differs only by **authorization rules**, keep one `/api/**` chain and place admin rules ahead of general API rules.
2. If admin uses a **different authentication mechanism**, place the `/api/admin/**` chain at higher priority than `/api/**` and document the exception.

Avoid adding extra chains just to "clarify each route"; multiplying chains makes scopes and priorities harder to reason about.

### 3.4. Missing Fallback Chain

**Wrong in an application with multiple routes:**

```java
@Bean
SecurityWebFilterChain apiOnly(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Once you define this custom chain, **never assume Spring Boot still auto-generates a chain protecting other routes**. A URL like `/admin` not matching `/api/**` can proceed straight to its handler without protection from these Spring Security chains.

**Right:** add a final fallback chain with an explicit default policy (`authenticated` or `denyAll` per design), and test a route outside the API group. Leave a public area only when declared intentionally.

## 4. "Right Chain Selected, Yet Rules Are Shadowed" Bugs

### 4.1. Broad Rule Placed Ahead of Strict Rule

**Wrong:**

```java
.authorizeExchange(ex -> ex
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
```

`/api/admin/report` matches `/api/**` first, so it only requires **being authenticated**—not `ROLE_ADMIN`. The `hasRole("ADMIN")` rule below becomes a "dead rule" for admin paths.

**Right:**

```java
.authorizeExchange(ex -> ex
        .pathMatchers("/api/public").permitAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/reports/**").hasAuthority("SCOPE_reports:read")
        .anyExchange().authenticated())
```

Order from **specific → general**. For unanticipated endpoints, the choice between `authenticated()` and `denyAll()` must be governed by your API contract; in especially sensitive API surfaces, prefer `denyAll()` after listing allowed routes.

### 4.2. Public Rule Placed in the Wrong Position

**Wrong:**

```java
.authorizeExchange(ex -> ex
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/public").permitAll())
```

`permitAll()` has no effect on `/api/public`, because `/api/**` already matched first. Conversely, placing `permitAll("/api/**")` ahead of `hasRole("/api/admin/**")` opens access far wider than intended.

Place intentional public endpoints **ahead** of broad rules; avoid overly broad wildcards like `/**` or `/api/**` with `permitAll()` when you only meant to expose `/api/health`.

### 4.3. `anyExchange()` Misplaced

`anyExchange()` is the fallback for requests not matched by earlier rules, so place it at the end of the declaration chain. Some builder variants reject registering further rules after `anyExchange()` with a configuration error; regardless, never expect a trailing rule to "override" it.

Each **chain** can have its own `anyExchange()`. `anyExchange()` in the API chain applies **only after** the API chain has been chosen; it cannot protect requests that never entered the API chain.

### 4.4. Roles vs. Authorities

- `.hasRole("ADMIN")` requires the `ROLE_ADMIN` authority under Spring Security's default prefix.
- `.hasAuthority("ADMIN")` requires the exact `"ADMIN"` authority.
- `.hasAuthority("SCOPE_reports:read")` fits when Resource Server maps OAuth2 scope `reports:read` to `SCOPE_reports:read`.

If both chain and rule matched properly yet the result is **403**, inspect granted authorities and rule expectations. Never "fix" it by weakening `hasRole` to `authenticated` without verifying policy.

## 5. Complete Java 17+ Example: Two Chains with Distinct Permissions

This sample app runs on Spring Boot 3.3.x + Spring Security 6.x. Its goal is demonstrating and testing **matching** using HTTP Basic to avoid external IdP dependencies. HTTP Basic in this example requires HTTPS in real deployments; the accounts and `{noop}` are strictly for test/lab use.

### 5.1. Dependencies

In Gradle Groovy DSL for a Spring Boot project with the proper plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

### 5.2. Application and Security Configuration

Save file: `src/main/java/example/chainorder/SecurityChainOrderApplication.java`.

```java
package example.chainorder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SecurityChainOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityChainOrderApplication.class, args);
    }

    // Chain 1 handles only /api/**, ahead of the catch-all.
    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .authorizeExchange(ex -> ex
                        .pathMatchers("/api/public").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    // Chain 2 has no securityMatcher => fallback for other URLs.
    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/home").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    // Illustrative only. Never use {noop} + static passwords in production.
    @Bean
    MapReactiveUserDetailsService testUsers() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}password")
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}password")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @RestController
    static class DemoRoutes {
        @GetMapping("/api/public")
        Mono<String> publicApi() {
            return Mono.just("API public");
        }

        @GetMapping("/api/private")
        Mono<String> privateApi() {
            return Mono.just("API authenticated");
        }

        @GetMapping("/api/admin/report")
        Mono<String> adminReport() {
            return Mono.just("API admin");
        }

        @GetMapping("/home")
        Mono<String> home() {
            return Mono.just("Web public");
        }

        @GetMapping("/account")
        Mono<String> account() {
            return Mono.just("Web authenticated");
        }
    }
}
```

Explanation across the five routes:

| Request | Selected chain | First matching rule | Expected outcome |
| --- | --- | --- | --- |
| `GET /api/public` without credentials | `apiChain` | `/api/public → permitAll` | 200 + `API public` |
| `GET /api/private` without credentials | `apiChain` | `anyExchange → authenticated` | 401 with HTTP Basic |
| `GET /api/private` with `alice` | `apiChain` | `anyExchange → authenticated` | 200 + `API authenticated` |
| `GET /api/admin/report` with `alice` | `apiChain` | `/api/admin/** → hasRole("ADMIN")` | 403 |
| `GET /api/admin/report` with `admin` | `apiChain` | `/api/admin/** → hasRole("ADMIN")` | 200 + `API admin` |
| `GET /home` without credentials | `fallbackChain` | `/home → permitAll` | 200 + `Web public` |
| `GET /account` without credentials | `fallbackChain` | `anyExchange → authenticated` | 401 with HTTP Basic |

**Intentional limitation:** the example exposes only GET endpoints so default CSRF settings need not be altered. Do not disable `.csrf()` globally just to test chain ordering. If adding POST/PATCH/DELETE, test CSRF separately or choose a stateless policy matching your real architecture.

### 5.3. Integration Testing with `WebTestClient`

Save file: `src/test/java/example/chainorder/SecurityChainOrderApplicationTest.java`.

```java
package example.chainorder;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        classes = SecurityChainOrderApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityChainOrderApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicApiUsesFirstChain() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("API public");
    }

    @Test
    void privateApiNeedsAuthentication() {
        client.get().uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/private")
                .headers(h -> h.setBasicAuth("alice", "password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("API authenticated");
    }

    @Test
    void specificAdminRuleWinsOverGenericApiRule() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("alice", "password"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("admin", "password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("API admin");
    }

    @Test
    void fallbackChainCoversWebUrls() {
        client.get().uri("/home")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Web public");

        client.get().uri("/account")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Run from a project with Gradle Wrapper:

```bash
./gradlew test --tests 'example.chainorder.SecurityChainOrderApplicationTest'
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests 'example.chainorder.SecurityChainOrderApplicationTest'
```

**Expectation:** four tests pass when the project has the required dependencies and no extra configuration alters the chains. There is no fixed Java stdout because tests assert HTTP statuses and bodies. If copying this class into a system with existing security beans, avoid competing beans or test contexts adding extra filters, which can alter outcomes.

**What this test proves:** the real HTTP path passes through `SecurityWebFilterChain`, Authentication, and Authorization rather than testing controller methods in isolation. The example creates test users in memory so it does not depend on an IdP. In real JWT environments, replace HTTP Basic on the corresponding chain with OAuth2 Resource Server and also test tokens/authorities; chain ordering carries the exact same semantics.

## 6. Inducing Controlled Failures and Observing Differences

Perform these experiments only on a lab copy, never directly in production.

### Experiment A: Admin Rule Shadowed

In `apiChain`, change the order to:

```java
.authorizeExchange(ex -> ex
        .pathMatchers("/api/public").permitAll()
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
```

Prediction: `specificAdminRuleWinsOverGenericApiRule` fails because already-authenticated user `alice` receives **200** on `/api/admin/report`. This is a **critical authorization bug**: the 403 test is the regression check that catches it. Fix by moving `/api/admin/**` ahead of `/api/**`, or removing the broad rule when `anyExchange().authenticated()` already suffices.

### Experiment B: Catch-All Placed First

Move `fallbackChain` to `@Order(1)` and `apiChain` to `@Order(2)`.

Prediction: `/api/public` ceases to be `permitAll` because fallback uses `anyExchange().authenticated()` → returns 401; meanwhile `/api/admin/report` can be permitted by fallback for any authenticated user → `alice` gets 200. Exactly **one chain-priority error** simultaneously causes one false block and one privilege escalation.

### Experiment C: Chain Scope Too Narrow

Change the API matcher to `"/api/admin/**"` while leaving `"/api/public"` and `"/api/private"` in API rules. Requests to `/api/public` fall through to fallback and demand login despite `permitAll` still appearing in API code. That is a chain-scope bug, not a bug in `permitAll()`.

### Experiment D: Missing Fallback

Delete the `fallbackChain` bean. If `/account` still exists, tests must verify anonymous requests never reach sensitive data. In apps defining custom `SecurityWebFilterChain` beans, do not assume auto-configuration adds a catch-all for you. Add a fallback and re-verify via HTTP tests.

**Learning rule:** when inducing faults, change **one variable at a time** (chain order, chain matcher, or rule order) and run the exact same matrix. Changing all three at once makes proving root cause difficult.

## 7. Production Diagnostic Workflow by Decision Point

### Step 1 – Pin Down the Exact Failing Request

Record complete **credential-free** details:

```text
Method:        GET
External URL:  https://app.example.com/api/admin/report
Upstream path: /api/admin/report
Expected:      alice (ROLE_USER) -> 403
Observed:      200
Auth mode:     HTTP Basic (lab) / Bearer JWT (production)
```

Distinguish paths **before and after** reverse proxies, API Gateways, `StripPrefix`, rewrites, `server.webflux.base-path`, and the actual path seen by `ServerWebExchange`. Security matchers inspect the request WebFlux receives and do not automatically know how a proxy rewrote the public URL.

Keep the exact method (`GET` differs from `POST`), URL encoding, trailing slashes, casing, `Authorization` header, content type, and session state when reproducing. Never print full tokens in support logs.

### Step 2 – List All `SecurityWebFilterChain` Beans and Priorities

Inspect the real Java configuration and build a table:

| Priority | Bean | `securityMatcher` | Authentication mechanism | Fallback |
| --- | --- | --- | --- | --- |
| 1 | `apiChain` | `/api/**` | HTTP Basic (demo), JWT per system | No |
| 2 | `fallbackChain` | Default match all | HTTP Basic (demo) | Yes |

Start from the highest-priority chain. For each chain, answer: **does the matcher match the real method/path?** Stop at the first matching chain. Do not read further chains as if they could add rules onto an already-claimed request.

If every chain uses a restricted matcher, check whether any URL slips outside all chains. Non-API endpoints like `/actuator/**`, `/login/**`, `/oauth2/**`, `/callback`, `/error`, and `/websocket` also need explicit policies. Never open all of Actuator just because a health endpoint needs to be public.

### Step 3 – Inside the Selected Chain, Read Every Rule in Order

Build a table following code order, for example:

| Rule | Pattern | Policy | `/api/admin/report` |
| --- | --- | --- | --- |
| 1 | `/api/public` | `permitAll` | No match |
| 2 | `/api/admin/**` | `hasRole("ADMIN")` | **Match; stop** |
| 3 | `anyExchange` | `authenticated` | Not evaluated |

If rule 2 is moved below `/api/**`, the broader rule matches first; tests will catch it. Never write overlapping rules expecting the framework to pick the "most specific" rule automatically. In `authorizeExchange`, **declaration order determines priority**, not automatic specificity scoring.

### Step 4 – Check Actual Identity

Verify:

- Was the request handled by the authentication filter of the **selected chain**? A JWT `/api/**` request entering a form-login web chain may get a 302 to login rather than a Bearer 401.
- Does the principal hold `ROLE_ADMIN`, or only `ADMIN` or `SCOPE_admin`? `hasRole("ADMIN")` differs from `hasAuthority("SCOPE_admin")`.
- Is the JWT unexpired with valid issuer/audience and scope mapping? Invalid tokens usually produce 401 before authorization runs.
- Is session/cookie/OAuth2 Login or Basic/Bearer being used? Avoid assuming HTTP 302/401 proves the chain matcher is wrong.
- Is `@PreAuthorize`, `@PostAuthorize`, or a custom reactive authorization manager rejecting at the method layer? Passing web security can still be denied by method security.

### Step 5 – Distinguish 401, 403, 302, 404, and 405

| HTTP status/symptom | Likely cause | What to inspect? |
| --- | --- | --- |
| **401 Unauthorized** | Unauthenticated, missing Basic/Bearer, or invalid token | Chain's authentication entry point, credentials, and Bearer token decoder |
| **403 Forbidden** | Authenticated yet lacking permission, or CSRF rejected a write | Authorities, matched rule, CSRF, method security |
| **302/303 to login** | Form-login/OAuth2 Login chain selected instead of intended API chain | Chain order, default entry point, API matcher |
| **404 Not Found** | HandlerMapping lacks route or upstream rewrite mismatch; security may also have allowed it | Real route, path reaching app, handler mappings, chain rules |
| **405 Method Not Allowed** | Route exists, yet does not support that HTTP method | Controller mappings and request method |
| **200 despite lacking permission** | Broad `permitAll`/`authenticated` shadowed `hasRole`, or URL missed every chain | Both matching layers, fallback chain, anonymous/low-role tests |
| **CORS preflight OPTIONS fails** | CORS not handled before auth, or path/method matcher mismatch | WebFlux/Spring Security CORS config, OPTIONS request, origin/headers |
| **POST gets 403 while GET works** | Missing CSRF token or method-specific rule | CSRF policy, cookies/sessions, per-method rules |

You cannot draw a firm conclusion from a single status code alone. For example, HTTP 403 **does not always mean** the user lacks a role; CSRF and method security can also return 403. A request allowed by Security may receive 404 from a controller; conversely, 404 does not guarantee an endpoint is unexposed.

### Step 6 – Enable Short-Lived Security Logs and Test Matchers Deliberately

For test/staging profiles:

```yaml
logging:
  level:
    org.springframework.security: TRACE
    org.springframework.web.reactive: DEBUG
```

Start with the test config, reproduce **one** request, and inspect logs covering security filters, authentication, authorization, and request paths. TRACE can be very verbose, and exact log strings change across versions. **Never** treat the presence or absence of a specific log phrase as absolute proof of which chain was picked.

When higher certainty is needed, write tests for `ServerWebExchangeMatcher` and integration tests with real requests. Never add a global `WebFilter` logging raw `Authorization` headers, JWTs, session cookies, or client secrets for "quick debugging". Disable TRACE once evidence is collected.

To make internal policy observation easier, name beans by area (`apiChain`, `fallbackChain`), keep configuration consolidated in few classes, and use credential-free request correlation IDs. Logs reveal symptoms; HTTP tests prove there is no regression.

## 8. Matcher Tests: Isolating Path/Method Bugs from Everything Else

In Spring WebFlux, `ServerWebExchangeMatcher` returns `Mono<MatchResult>`. You must **subscribe** for the matcher to evaluate. You can unit-test patterns in isolation as follows.

JUnit example in the same test module (standalone test class using `spring-test` and `reactor-test`):

```java
package example.chainorder;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ApiPathMatcherTest {

    @Test
    void adminPathFallsInsideApiChain() {
        var matcher =
                new PathPatternParserServerWebExchangeMatcher("/api/**");

        var request = MockServerHttpRequest.get("/api/admin/report");
        var exchange = MockServerWebExchange.from(request);

        StepVerifier.create(matcher.matches(exchange))
                .assertNext(result -> assertTrue(result.isMatch()))
                .verifyComplete();
    }
}
```

Run test:

```bash
./gradlew test --tests 'example.chainorder.ApiPathMatcherTest'
```

**Expected outcome:** PASS when `/api/admin/report` matches `/api/**`. This test verifies **only one matcher**; it does not prove the whole app picks the API chain first or enforces strict admin rules. Combine it with `WebTestClient` in Section 5.3 to verify full chains and rules.

If a matcher also depends on HTTP method, use constructors/matchers accepting `HttpMethod` and build requests with the target method. For custom `ServerWebExchangeMatcher` implementations, explicitly test match, no-match, and error cases. A reactive matcher can return an asynchronous `Mono`; never call `.block()` inside a production `WebFilter`.

## 9. Applications Migrating from Servlet to WebFlux

| Servlet stack | WebFlux stack | Common mistake |
| --- | --- | --- |
| `SecurityFilterChain` | `SecurityWebFilterChain` | Using Servlet beans in a reactive app |
| `HttpSecurity` | `ServerHttpSecurity` | Using the wrong stack's configuration DSL |
| `RequestMatcher` | `ServerWebExchangeMatcher` | Legacy custom matchers have no effect |
| `authorizeHttpRequests().requestMatchers(...)` | `authorizeExchange().pathMatchers(...)` | Mixing DSLs or misunderstanding order |
| `FilterChainProxy` | `WebFilterChainProxy` | Reading logs expecting Servlet filters |
| `Filter` / `OncePerRequestFilter` | `WebFilter` | Custom Servlet filters are never invoked |
| `MockMvc` | `WebTestClient` | Tests bypass the required reactive filter chain |
| ThreadLocal-based `SecurityContextHolder` | `ReactiveSecurityContextHolder` / Reactor Context | Misreading auth across reactive thread switches |
| `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` | Method authorization forgotten or misapplied |

A very common post-migration bug: the old codebase had two `SecurityFilterChain` beans, yet after switching controllers to WebFlux, the app still retains Servlet/WebMVC and Servlet security libraries. In that situation, determine the **actual running web application type** (SERVLET/REACTIVE) from dependencies, Boot auto-configuration, and startup runtime. Never assume reactive security is running just because methods return `Mono`.

When using Spring Cloud Gateway, downstream path matchers do not necessarily match client URLs if the gateway rewrites prefixes. Verify every hop with real tests; do not copy Gateway URL routes into downstream `securityMatcher`s when paths have been rewritten.

### Should You Use One Chain or Multiple Chains?

**One chain** is usually enough when differences are mainly **authorization rules**: public, user, admin, and scoped APIs. Place specific rules first and set a clear fallback.

**Multiple chains** fit when **authentication/filter behaviors** must differ: `/api/**` using stateless Bearer JWT only while `/web/**` uses OAuth2 Login/sessions; special endpoints requiring X.509/mTLS; or separating CSRF behavior by client type. When splitting, ensure distinct matchers, explicit priorities, a fallback, and negative tests per area.

Directional example (DSL fragment, not a standalone class):

```java
@Order(1)
@Bean
SecurityWebFilterChain jwtApi(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex
                    .pathMatchers("/api/admin/**")
                        .hasAuthority("SCOPE_admin")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(
                    Customizer.withDefaults()))
            .build();
}

@Order(2)
@Bean
SecurityWebFilterChain browserLogin(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers("/", "/about").permitAll()
                    .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
}
```

This requires a project with OAuth2 Resource Server + OAuth2 Client and valid issuer/client registration config. `@Order(1)` ensures `/api/**` is chosen ahead of fallback. Never assume enabling Resource Server protects every Bearer-token request automatically; the chain containing `.oauth2ResourceServer(...)` must actually **match** that request.

## 10. Testing Strategy to Prevent Rule Shadowing When Adding Endpoints

For each route group, maintain a minimal matrix:

| Request | Anonymous | Authenticated wrong role | Right role | Bug prevented |
| --- | --- | --- | --- | --- |
| `/api/public` | 2xx | 2xx | 2xx | Not blocked by broad rules |
| `/api/private` | 401 | 2xx if policy is authenticated-only | 2xx | Unauthenticated access prevented |
| `/api/admin/report` | 401 | 403 | 2xx | Regular users cannot get 200 |
| `/home` | 2xx | 2xx | 2xx | Fallback does not block public pages |
| `/account` | 401/redirect per auth scheme | 2xx | 2xx | Routes outside `/api/**` not left unprotected |
| Nonexistent API URL | 401/403 when under-privileged, 404 after passing auth | Depends on policy | 404 | Not accidentally `permitAll` by default |

Do not test only the **happy path** with ADMIN; testing **lower-privileged users being denied** is what catches an `authenticated()` rule shadowing `hasRole("ADMIN")`. Anonymous tests catch missing fallback chains.

When using `mockJwt()`/`mockUser()`/`mockOpaqueToken()`:

- Ensure `WebTestClient` is configured with Spring Security test support when bound to the application context: `.apply(springSecurity())`.
- Authorization tests with mocked principals are fast and reliable, yet **do not** prove JWT/IdP decoders or HTTP `Authorization` headers work. Add integration tests with real tokens when verifying the authentication path.
- When testing directly against a random port, send Basic/Bearer credentials matching the chain's real mechanism as in Section 5.
- Role/authority checks must test both invalid and valid values; avoid `@WithMockUser(roles="ADMIN")` across all tests, which masks overly broad admin rules.

An especially valuable mutation test: **deliberately** move `/api/**.authenticated()` above `/api/admin/**.hasRole("ADMIN")` and run the tests. If the suite stays green, it is not testing for shadowing; add a `ROLE_USER → 403` case.

### Invariants to Maintain as Configuration Grows

1. Every sensitive URL is covered by at least one chain; no matcher gaps exist.
2. Narrow-scoped chains precede broad/catch-all chains whenever scopes overlap.
3. Strict, specific rules precede broad rules; `anyExchange` always comes last.
4. Public scope is minimal and verified with anonymous tests.
5. Each chain's authentication mechanism matches its request type (Bearer API, web login, Basic test).
6. HTTP tests run after every rule/endpoint addition, route/gateway prefix change, or Spring Security upgrade.
7. CSRF, method security, and routing errors are diagnosed separately—never silenced by broad `permitAll`.

## 11. "Firefighting" Actions to Avoid

- **Randomly changing `@Order`** until an endpoint stops returning 401 without understanding which chain won; another area may lose protection.
- **Using `.anyExchange().permitAll()`** in the catch-all chain "temporarily"; every URL outside narrow chains can become completely public.
- **Changing `.hasRole("ADMIN")` to `.authenticated()`** just to stop 403s for normal users; the real bug may be role mapping or rule shadowing.
- **Prepending `.pathMatchers("/**").permitAll()`** because health checks or login were blocked; it shadows every specific rule below.
- **Disabling CSRF globally** when POST returns 403 due to a missing CSRF token rather than chain ordering.
- **Adding a custom `WebFilter`** to override Authorization instead of fixing matchers; this creates competing policy sources that are hard to test.
- **Looking at one HTTP status alone** to diagnose matching; check method/path, auth mechanism, cookies, principal, and route mappings.
- **Calling `.block()` inside a reactive `WebFilter`** to debug matchers or permissions; this can stall the event loop.
- **Logging raw Bearer tokens/session cookies** at TRACE; protect user credentials during debugging.

## 12. Self-Assessment Exercises

### Question A

Given three chains:

```text
@Order(1) matcher /api/**
@Order(2) matcher /api/admin/**
@Order(3) catch-all
```

Which chain does `GET /api/admin/export` enter?

**Answer:** `@Order(1)`, because it matches `/api/**` first; `@Order(2)` is shadowed. If admin requires a separate mechanism, give `/api/admin/**` higher priority. If it only differs in authority, move the admin rule into the `/api/**` chain.

### Question B

Inside the API chain:

```java
.pathMatchers("/api/**").authenticated()
.pathMatchers("/api/admin/**").hasRole("ADMIN")
.anyExchange().denyAll()
```

What happens when a `ROLE_USER` user calls `/api/admin/export`, assuming the route exists and no other filter blocks it?

**Answer:** it passes the `authenticated()` rule first, so web authorization **allows** it and the handler may return 2xx. `hasRole("ADMIN")` is never evaluated. This is a policy bug even though an ADMIN rule appears in the code.

### Question C

Only one chain exists with `securityMatcher("/api/**")`. Can `/reports/private` return 200 to an anonymous caller even though the API chain uses `anyExchange().authenticated()`?

**Answer:** yes. `anyExchange()` applies **only within the selected chain**. Because no chain covers `/reports/private`, the API chain's security filters do not run for it. You must add a fallback chain or expand the matcher per policy.

### Question D

`POST /api/admin/report` with `ROLE_ADMIN` returns 403, while GET succeeds. Is that enough evidence to conclude rule ordering is wrong?

**Answer:** not yet. Check CSRF (if browser/session), method-specific rules, request method, CORS preflight, handler, and method security. A 403 can originate from CSRF before the handler ever runs. Reproduce both GET and POST with `WebTestClient` to separate authorization from CSRF.

## 13. Bug-Closing Checklist and References

Before closing an "unmatched chain / shadowed rule" bug, gather evidence of:

- [ ] A specific request with method, actual path reaching WebFlux, and known identity.
- [ ] A table of all chains in priority order with their `securityMatcher` and authentication mechanisms.
- [ ] Proof of which chain matched **first**, confirming no catch-all chain sits erroneously ahead of it.
- [ ] Proof of which `authorizeExchange` rule matched **first** inside the selected chain.
- [ ] Comparison of actual `ROLE_` / `SCOPE_` / authority names against rule requirements.
- [ ] Tests covering anonymous, under-privileged user, and authorized user, asserting both status and body rather than body alone.
- [ ] If 403 persists with the right role, checks for CSRF and method security; if 404, checks for routing/path rewrites.
- [ ] TRACE logging disabled or reverted after debugging, with no credentials stored in logs.
- [ ] A regression test for the exact shadowing bug added before deployment.

**Official documentation:**

- Spring Security 6.5 — [WebFlux Security: Multiple Chains Support](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html#_multiple_chains_support): `@Order`, `securityMatcher`, and single-chain selection.
- Spring Security 6.5 — [Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html): rules evaluated in order.
- Spring Security 6.5 — [WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): integrating Spring Security test support.
- Spring Security 6.5 — [Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): 401/403 and mock users.
- Spring Framework — [Testing WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-test.html): `WebTestClient` and reactive mock requests/exchanges.

**Expected outcome:** whenever an endpoint returns an unexpected 401/403/200, you can identify the **selected chain**, the **first rule applied**, and the **actual authentication/authorization mechanism**, fixing scopes/ordering with tests proving sensitive endpoints are neither shadowed nor left outside all chains.