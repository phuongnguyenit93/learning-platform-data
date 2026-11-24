# Distinguishing permitAll from Bypassing the Entire Security Chain in Spring Security WebFlux

## Learning Objectives

After this lesson, you will be able to:

- Explain accurately that `permitAll()` in `authorizeExchange(...)` means **allowing access at the HTTP authorization rule level**.
- Distinguish **a request being matched into a `SecurityWebFilterChain`** from **an authorization rule permitting that request**.
- Understand why a `permitAll()` endpoint can still run authentication, CSRF, security headers, CORS, and other configured WebFilters—and may even still return `401`/`403`.
- Recognize when a URL **does not match any `SecurityWebFilterChain`** and the consequences when Spring Security's internal chain filters do not apply to that URL.
- Write a Java 17+ configuration for safe public endpoints, split multiple chains using `securityMatcher(...)`, and test the difference over HTTP.

> **Scope:** **Reactive** Spring Security uses Spring WebFlux and `ServerHttpSecurity`. Servlet APIs such as `HttpSecurity`, `SecurityFilterChain`, and `WebSecurityCustomizer.ignoring()` follow a different model; do not copy Servlet syntax or expectations directly to WebFlux.

## 1. Two separate decisions: chain selection and authorization

There are two logic layers to distinguish when an HTTP request passes through Spring Security WebFlux.

**Layer A — Selecting the security chain.** Spring Security's `WebFilterChainProxy` finds the `SecurityWebFilterChain` matching the request via the chain's matcher, usually configured with `http.securityMatcher(...)`. When there are multiple `SecurityWebFilterChain` beans, Spring Security evaluates them in order and picks the **first matching chain**. If there is a catch-all chain with `anyExchange`/default matcher, requests not matching specific chains still pass through that fallback chain.

**Layer B — HTTP access decision inside the selected chain.** The authorization filter applies the rules in `http.authorizeExchange(...)`. A rule like `pathMatchers("/public/**").permitAll()` states that requests matching that path **do not need to be approved based on login status or roles** to pass that authorization step.

The two layers differ in purpose and position:

~~~text
HTTP request
  |
  v
WebFlux and application WebFilters
  |
  v
Spring Security WebFilterChainProxy
  |
  +-- Any SecurityWebFilterChain matches? -- NO --> No internal filters of any
  |                                                SecurityWebFilterChain run
  |                                                (other WebFilters still run)
  |
  YES
  |
  v
Filters inside the selected SecurityWebFilterChain
  |-- SecurityContext / authentication (if configured)
  |-- CSRF / security headers / error handling (if configured)
  |-- AuthorizationWebFilter
         |
         +-- permitAll() rule ----> authorization allows
         +-- authenticated() -----> requires authentication
         +-- hasRole(...) --------> checks role
         +-- denyAll() -----------> authorization denies
  |
  v
Handler / controller (if not blocked by an earlier filter)
~~~

Conceptual diagram; the exact sequence and active filters depend on your Spring Security configuration. The core takeaway is that **`permitAll()` belongs to Layer B, and does not cancel Layer A**.

## 2. What does permitAll() actually allow?

Example:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**", "/login").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is an illustrative configuration method placed inside a Spring configuration class; it requires importing `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer`, and `@Bean`. Assuming this chain matches all requests (not restricted by `securityMatcher`):

- `GET /public/info` does not require a logged-in user to pass the authorization rule.
- `GET /admin/audit` requires `ROLE_ADMIN` (`hasRole("ADMIN")` applies the default `ROLE_` prefix).
- Remaining paths require an `Authentication` satisfying `authenticated()`.
- **No path is excluded from the security chain merely because of `permitAll()`.**

Things `permitAll()` **does not guarantee**:

1. It does not promise the request always returns `200 OK`. The controller can still return `404`, `400`, or other errors, or another security filter can reject before authorization.
2. It does not disable `CsrfWebFilter`. A `POST` to a public route can still return `403` if CSRF is enabled and a valid token is missing.
3. It does not disable enabled authentication filters (HTTP Basic, bearer token, etc.). If a client **actively sends invalid credentials**, an active authentication filter may fail and return `401` even when the URL is `permitAll()`.
4. It does not turn off security response headers such as `X-Content-Type-Options: nosniff` or `X-Frame-Options: DENY`.
5. It does not guarantee a specific principal. A public endpoint can run with no logged-in user; if valid credentials are provided and processed by an authentication mechanism, a principal may still be established.
6. It does not bypass **method-level** security. If reactive method security is enabled, a method annotated with `@PreAuthorize(...)` can still deny the call according to its rule, even if the URL is `permitAll()`.

**Short sentence to remember:** `permitAll()` waives the authorization requirement for the URL in that rule; the request is still processed inside the selected security chain.

## 3. What does "bypassing the entire security chain" mean?

In WebFlux, a notable scenario is when **a request does not match any `SecurityWebFilterChain` bean**. In that case, `WebFilterChainProxy` has no internal Spring Security chain to apply to that request.

Example illustrating only a chain-level matcher:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/open").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Requires importing `org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher`. If this is the **only `SecurityWebFilterChain`** in the application:

- `/api/open`: matches the `/api/**` chain and passes authorization via `permitAll()`; other filters in the chain can still run.
- `/api/private`: matches the `/api/**` chain; requires authentication.
- `/public-outside`: does not match `/api/**`; **no internal `SecurityWebFilterChain` is selected**.

If the application also has another bean matching all requests—such as a default chain without a restrictive `securityMatcher`—`/public-outside` **will pass through that chain**. Therefore, you cannot conclude a path "bypasses security" solely by seeing it does not match one specific chain's matcher.

Note the scope distinction: WebFlux `WebFilter` instances **outside** `SecurityWebFilterChain` (custom filters, gateway filters, CORS handling at another layer, etc.) can still run. Method security and controls at other layers do not vanish either. "Bypassing the entire security chain" here applies only to **the filters inside an unselected Spring Security chain**, not to bypassing every middleware or every security control in the system.

## 4. Comparison table of the three cases

| Question | Route in chain with `permitAll()` | Route handled by another Spring Security chain | Route matching **no** `SecurityWebFilterChain` |
|---|---|---|---|
| Is a `SecurityWebFilterChain` selected? | Yes | Yes, by `securityMatcher` and `@Order` | No |
| HTTP authorization rule | Permitted by `permitAll()` | Governed by the other chain's rules | No `SecurityWebFilterChain` authorization filter |
| Spring Security authentication filter | May run if configured | Depends on selected chain | No authentication filter from unmatched chains |
| Spring Security CSRF | May still apply to unsafe requests | Depends on chain config | Not applied from unmatched chains |
| Spring Security response headers | May still be added | Depends on chain config | Not added by unmatched chain filters; other layers may still add headers |
| Spring Security 401/403 handling | Can occur from active filters | Depends on config | Not from unselected internal chains; other layers may still deny |
| Other application WebFilters | Still run in order | Still run in order | Can still run |
| Conclusion | **Public endpoint with general protections intact** | **A different security policy** | **Risk of creating an area unprotected by Spring Security** |

Do not treat the presence or absence of `Authentication` at an endpoint as the sole test: with `permitAll()`, authentication is not required for the authorization decision, yet configured authentication mechanisms can still operate.

## 5. How does securityMatcher(...) differ from pathMatchers(...).permitAll()?

### 5.1. `securityMatcher(...)` decides which chain is selected

~~~java
http.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**"));
~~~

This is a **`SecurityWebFilterChain`-level** condition. Request `/api/products` falls within the chain's scope. Request `/docs/index.html` falls outside this chain's scope, though it may match another chain.

### 5.2. `pathMatchers(...).permitAll()` decides access inside the chain

~~~java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated());
~~~

These rules are evaluated **after the corresponding chain has been selected**. They do not create additional `SecurityWebFilterChain` beans and do not move the request out of the current chain.

### 5.3. Order matters at both layers

- **Across multiple `SecurityWebFilterChain` beans**: order beans with `@Order`; Spring Security picks the first matching chain. A chain with a broad matcher placed earlier can shadow a narrower chain.
- **Across authorization matchers within the same chain**: specific rules must come before broad rules. `anyExchange()` goes last.
- If there is only an `/api/**` chain and you forget a fallback chain, unmatched routes may not be protected by Spring Security. This is a serious configuration flaw when new endpoints are added later.

**Pitfall:** Two `SecurityWebFilterChain` beans do not automatically "stack" filters for a single request. Spring Security selects the first matching chain rather than executing all matching chains sequentially.

## 6. Java 17+ lab: seeing the difference over HTTP

This small example intentionally has **a single chain matching only `/api/**`** to reveal three behaviors: (a) `permitAll` inside the chain, (b) a URL requiring login, and (c) a URL outside every chain. The out-of-chain path exists **solely for observation**, not as a recommended production configuration.

Uses Spring Boot `3.3.5` and Java 17. Spring Security and Reactor dependency versions are managed via the Spring Boot BOM.

### 6.1. Project structure

~~~text
permitall-webflux-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/PermitAllWebFluxDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'permitall-webflux-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

`src/main/java/example/PermitAllWebFluxDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class PermitAllWebFluxDemo {

    public static void main(String[] args) {
        SpringApplication.run(PermitAllWebFluxDemo.class, args);
    }

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            // Select only requests under /api/.
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.POST, "/api/public-post").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            // Intentionally keep default CSRF to observe it with POST.
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Strictly for running the demo on localhost.
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @RestController
    static class ApiController {

        @GetMapping("/api/public")
        Mono<Map<String, String>> publicGet() {
            return Mono.just(Map.of("access", "public"));
        }

        @PostMapping("/api/public-post")
        Mono<Map<String, String>> publicPost() {
            return Mono.just(Map.of("access", "public-post"));
        }

        @GetMapping("/api/private")
        Mono<Map<String, String>> privateGet(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "access", "private",
                    "username", principal.getName()));
        }

        @GetMapping("/outside")
        Mono<Map<String, String>> outsideGet() {
            return Mono.just(Map.of("access", "outside"));
        }
    }
}
~~~

**Configuration explanation:**

- `securityMatcher("/api/**")` limits the **entire chain** to the `/api/` URL group.
- `permitAll()` on GET `/api/public` and POST `/api/public-post` affects only authorization. The other filters in `apiChain` remain present, including Spring Security's default CSRF protection.
- `anyExchange().authenticated()` protects other APIs, such as `/api/private`.
- `/outside` does not match the `/api/**` chain. Because the demo has no fallback `SecurityWebFilterChain`, this endpoint is handled by WebFlux **without `apiChain`'s security filters**.
- The method accepts `ServerWebExchange` to read the principal on the private route; it does not read users from an arbitrary header.

### 6.2. Run commands

In the `permitall-webflux-demo` directory, requiring JDK 17+ and a compatible Gradle version (or your generated Gradle Wrapper):

~~~bash
gradle bootRun
~~~

If you have a wrapper: Linux/macOS uses `./gradlew bootRun`, Windows uses `gradlew.bat bootRun`. Once the app has started, in another terminal:

~~~bash
# 1. Public URL that is still inside the security chain
curl -i http://localhost:8080/api/public

# 2. URL requiring Authentication
curl -i http://localhost:8080/api/private

# 3. URL requiring Authentication with valid credentials
curl -i -u learner:demo-pass http://localhost:8080/api/private

# 4. permitAll URL using POST, missing CSRF token
curl -i -X POST http://localhost:8080/api/public-post

# 5. URL outside the single chain's matcher
curl -i http://localhost:8080/outside

# 6. Sending wrong Basic credentials to a public URL
curl -i -u learner:wrong-password http://localhost:8080/api/public
~~~

Note: in Windows PowerShell, if `curl` is an alias for another tool, use `curl.exe`. With Boot running on default port 8080 and no external configuration changing security, expected outcomes are:

| Request | Expected status | Meaning |
|---|---|---|
| `GET /api/public`, no credentials | `200` | Authorization `permitAll`; security headers added by the chain are still observable, e.g., `X-Content-Type-Options: nosniff`. |
| `GET /api/private`, no credentials | `401` | Authorization requires `Authentication`; HTTP Basic entry point creates a challenge. |
| `GET /api/private`, valid Basic | `200` | Valid authentication, JSON body contains `"username":"learner"`. |
| `POST /api/public-post`, no CSRF token | `403` | `permitAll` does not disable `CsrfWebFilter`; missing token on a state-changing HTTP method. |
| `GET /outside` | `200` | Endpoint exists, yet does not match the single `SecurityWebFilterChain`. No security headers **added by that chain**; components outside the chain might add their own headers. |
| `GET /api/public`, wrong Basic | May be `401` with this Basic setup | Authentication filter receives Basic credentials and fails even though URL authorization is `permitAll`. |

Example success body for `GET /api/public`:

~~~json
{"access":"public"}
~~~

`GET /api/private` with valid credentials returns a JSON object with `access=private` and `username=learner`; JSON field ordering is not guaranteed. `curl -i` output is HTTP headers/body, **not fixed Java program stdout**; ports, server logs, dynamic headers, and response times may vary. Use HTTP status codes and intentional headers for verification.

**Demo security limitations:** Accounts using `{noop}` and static passwords are strictly for local learning. Do not use outside test environments. Real deployments require an appropriate password encoder, secret management, and HTTPS. Do not treat the `/outside` path as a safe configuration; section 7 explains how to fix it.

## 7. Configurations to use in real applications

### 7.1. Common approach: one chain covering all URLs, permitAll for public ones

In the lab above, replace the `apiChain` bean with a bean that has no restrictive `securityMatcher`:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/public", "/outside")
                .permitAll()
            .pathMatchers(HttpMethod.POST, "/api/public-post")
                .permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
}
~~~

This is a **replacement method** for the bean in the demo; do not include both methods simultaneously. Imports and the controller stay the same. Because the chain-level matcher covers all URLs by default, `/outside` is now **public inside the security chain**, so it is still processed by the corresponding security filters. The `permitAll` rule on POST **still does not automatically remove the CSRF requirement**.

Advantage: public endpoints still receive general protections; newly added endpoints not declared public require authentication by default. When protection requirements differ more deeply between APIs and web pages, multiple chains can be used.

### 7.2. Multi-chain approach: different configurations, still with a fallback chain

The following snippets are an **integrated configuration example** inside a class with Spring beans, not to be used simultaneously with the demo's `apiChain`:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain fallbackSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/health").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
}
~~~

Requires importing `org.springframework.core.annotation.Order` and the imports from the previous example. If you want the `/outside` controller to be public in the fallback, declare it explicitly in the fallback with `pathMatchers(...).permitAll()`; the snippet above intentionally leaves `/outside` requiring authentication to illustrate default protection.

Chain selection rules:

- `/api/public` and `/api/private` match the `@Order(1)` chain.
- `/health` or `/outside` does not match `/api/**`, yet matches the second chain (whose default matcher matches all requests).
- `/health` in the fallback has `permitAll` yet still passes through the **fallback chain**, unlike being left without any chain.

Avoid placing the broad chain before the narrow chain; it would catch `/api/**` as well, shadowing the API chain configuration. Do not assume the framework automatically picks the most specific matcher regardless of order.

### 7.3. When would you genuinely want no SecurityWebFilterChain?

This requires a deliberate architectural decision and risk assessment—for example, a completely public static-asset area already protected by an actual security gateway with all necessary security headers configured at another layer. Even so, simply needing an endpoint to be public **is not a good enough reason** to exclude it from the chain.

Especially avoid omitting chains for `/api/admin/**`, endpoints containing user data, actuator/management endpoints, state-changing routes, or newly added unreviewed paths. A URL matching no `SecurityWebFilterChain` may lack the authorization filter, authentication filter, and Spring Security's default security headers.

## 8. Protective layers that remain active under permitAll

### 8.1. CSRF is independent of authorization

CSRF protects state-changing requests in scenarios where browsers automatically send credentials (such as session cookies). Spring Security WebFlux enables CSRF protection by default; a `permitAll` rule does not disable it automatically. A `POST /signup` route, even though public, may still need a CSRF token if the application model uses cookies/sessions.

If an API authenticates strictly with bearer tokens not auto-sent by browsers and **does not rely on cookies/sessions** for state-changing requests, adjusting CSRF can be evaluated. Never disable CSRF application-wide just to make a public `POST` work; consider the threat model, exact CSRF matcher, and how clients supply tokens.

### 8.2. Authentication can fail before the permitAll step

`permitAll` means authorization does not require authentication. It does not stop a configured `AuthenticationWebFilter` from validating credentials that a client actively sends. For instance, a malformed `Authorization: Basic ...` header can produce a `401` response. Therefore, testing `GET /public` without credentials **differs** from testing the same URL while sending invalid credentials.

This also means a public endpoint should not fetch user data using Servlet-style `SecurityContextHolder`. In reactive code, use `ReactiveSecurityContextHolder`/principal following proper subscription semantics and handle the case where no `Authentication` is present.

### 8.3. Security headers and CORS

When a chain is applied and headers are not disabled, Spring Security normally adds protective headers such as `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and cache-control. `Strict-Transport-Security` applies only over HTTPS per supporting configuration. `permitAll` is not a command to turn those headers off.

CORS is a browser policy with its own configuration; `permitAll` does not automatically configure `Access-Control-Allow-Origin` and does not mean every preflight succeeds. When using Spring Security CORS integration or WebFlux CORS, configure genuinely allowed origins/methods/headers. Never use `permitAll` as a fix for CORS errors.

### 8.4. Security context and sessions

Loading/saving `SecurityContext` depends on repository and authentication configuration. For public endpoints, a principal should not be mandatory, yet a user sending valid credentials can still be authenticated. `permitAll` does not equate to "always anonymous", nor does it necessarily trigger loading an entire session on every request. Verify what happens under your version and configuration rather than guessing from the authorization rule name.

### 8.5. Method security can maintain an extra barrier

With reactive method security enabled, a method annotated with `@PreAuthorize("hasRole('ADMIN')")` can reject calls even if the URL is `permitAll`. This **does not replace** an HTTP-level security chain: HTTP-level CSRF/headers/authentication protections and method authorization serve different responsibilities. Without a security chain, the principal/`Authentication` needed for method policies to work as intended may also be missing.

## 9. Common mistakes and how to fix them

**Mistake 1 — Writing `permitAll()` to "turn off Spring Security" for static resources.** The route still goes through the chain, and some people then try to remove the chain thinking that is the proper way. Usually keep public resources inside the chain and permit the needed URLs; security headers remain useful for static content.

**Mistake 2 — Thinking `securityMatcher` and `pathMatchers` are the same.** One **selects the chain**; the other **selects the authorization rule inside the chain**. Setting `securityMatcher("/api/**")` without a fallback leaves other paths outside every chain's scope.

**Mistake 3 — Using Servlet's `web.ignoring()` examples in WebFlux.** That belongs to the Servlet architecture, not reactive `ServerHttpSecurity` configuration. In WebFlux, reason in terms of `SecurityWebFilterChain` and `ServerWebExchangeMatcher`.

**Mistake 4 — Assuming `permitAll` guarantees every request returns 200.** CSRF, authentication failures, handler errors, HTTP method mismatches, or other filters can produce different outcomes. Read logs for the right component and test each mechanism.

**Mistake 5 — Placing fallback `anyExchange().authenticated()` before public rules.** A broader matcher can capture requests before reaching the public rule, causing `401`. Put specific rules before `anyExchange`.

**Mistake 6 — Putting the catch-all chain at `@Order(1)` and the API chain at `@Order(2)`.** The general chain captures every request first; the API chain is never selected. Put chains with narrow `securityMatcher`s first and the catch-all last.

**Mistake 7 — Testing URLs only with empty credentials.** You must test valid credentials, invalid credentials, CSRF, and `GET`/`POST` cases. Authorization `permitAll` does not make authentication or CSRF errors disappear.

**Mistake 8 — Treating missing security headers as "authentication disabled".** HTTP protection has multiple parts. Evaluate chain matching, authorization rules, security headers, CSRF, authentication, and method security separately.

**Mistake 9 — Leaving new endpoints outside the matcher.** A new endpoint outside `/api/**` without a fallback can be publicly accessible with no security filters. Test all URL groups and maintain an explicit catch-all policy.

## 10. Testing exercises and review checklist

### 10.1. Two-layer checklist

When reviewing an endpoint `/x`, answer in order:

1. How many `SecurityWebFilterChain` beans exist? What are their `@Order` values?
2. Which chain **first matches `/x`** by `securityMatcher`? If none, you have a security gap.
3. Inside the selected chain, which `pathMatchers`/`anyExchange` rule matches? Is it `permitAll`, `authenticated`, a role, or `denyAll`?
4. Which authentication/CSRF/headers/exception-handling filters are actually enabled in that chain?
5. If the URL is a public POST, is a CSRF token supplied according to the app's authentication model and CSRF risk?
6. Are there method-level policies or upstream gateways involved? They do not implicitly replace Spring Security HTTP configuration.
7. How are public `GET`, authenticated `GET`, wrong credentials, tokenless `POST`, and out-of-matcher URLs tested?

### 10.2. Self-assessment questions with answers

**Question 1.** A configuration has a chain `securityMatcher("/api/**")`, with `pathMatchers("/api/health").permitAll()` inside. Does `GET /api/health` bypass the security filter chain?

**Answer:** No. It matches the `/api/**` chain and passes the authorization step via `permitAll`; the remaining filters in the chain can still run.

**Question 2.** With only one chain matching `/api/**`, `GET /docs` does not match. Is `GET /docs` automatically rejected by Spring Security?

**Answer:** No. If no other `SecurityWebFilterChain` matches, Spring Security's internal filters do not apply to that URL. Controllers/resource handlers can serve content; mechanisms outside the chain may still apply.

**Question 3.** Why does `POST /signup` with `permitAll()` return 403?

**Answer:** A common cause is that the CSRF filter is enabled and the request lacks a valid token. Identify the rejecting filter from logs/tests; do not draw conclusions from status 403 alone. `permitAll` does not disable CSRF.

**Question 4.** If an app has two chains: `@Order(1)` matching `/api/**` and `@Order(2)` default matching everything, does `GET /docs` bypass chains?

**Answer:** No. It does not match the first chain, yet matches the second; it is governed by that chain's policy.

**Question 5.** A URL has `permitAll()` but a client sends wrong HTTP Basic credentials. Must it return 200?

**Answer:** No. An authentication filter may attempt to validate the client-supplied credentials and reject with 401 before authorization allows it.

## 11. Takeaways when designing reactive Spring Security

- **`securityMatcher` = select the chain**, whereas **`authorizeExchange().pathMatchers().permitAll()` = select an authorization rule inside the chain**.
- Public routes should usually **stay inside an appropriately scoped `SecurityWebFilterChain`**, where response headers, CSRF, and general defenses still operate as configured.
- A request **matching no `SecurityWebFilterChain`** is a completely different situation; never equate it with public `permitAll`.
- With multiple chains, keep **specific chains first, catch-all last**, and test all URL regions to avoid gaps from missed matchers.
- To determine actual behavior, inspect **chain matching, authorization rules, authentication/CSRF/headers, and HTTP responses** together, rather than looking at a single `permitAll()` line.

## Official documentation

- Spring Security — WebFlux Security (basic configuration, multiple chains, and ordering): https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Authorize ServerHttpRequest (`pathMatchers`, `permitAll`, `authenticated`): https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Security HTTP Response Headers for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
