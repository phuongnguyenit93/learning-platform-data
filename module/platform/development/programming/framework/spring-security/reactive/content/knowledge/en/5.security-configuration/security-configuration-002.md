# Distinguishing `securityMatcher` Selecting a Chain and `authorizeExchange` Selecting a Rule

## 1. The problem: how is a request evaluated for security?

In **reactive** Spring Security (Spring WebFlux), when an application has multiple `SecurityWebFilterChain` beans, request processing occurs through **two distinct decision layers**:

1. **Selecting the security filter chain**: `securityMatcher(...)` decides whether a `SecurityWebFilterChain` applies to that request. Chains are evaluated in priority order; Spring Security uses the **first matching chain**.
2. **Selecting the authorization rule inside the chosen chain**: `authorizeExchange(...)` decides which requests get `permitAll()`, which require `authenticated()`, `hasRole(...)`, `hasAuthority(...)`, or must `denyAll()`.

These are two levels of configuration, even though both can inspect URL paths. If you confuse them, the application may apply the wrong login mechanism, accidentally skip ADMIN permission checks, or leave a group of endpoints unprotected by Spring Security.

Lesson objectives:
- Explain accurately the scope, evaluation order, and responsibilities of both APIs.
- Trace how a request flows through multiple `SecurityWebFilterChain` beans and multiple `authorizeExchange` rules.
- Know when a single chain suffices, when multiple chains are needed, and why a catch-all chain is usually essential.
- Run a Java 17+ example with public, user, and admin endpoints in both the API branch and the web branch.
- Write tests verifying HTTP 200, 401, and 403 and catching common misconfigurations.

## 2. Two matching layers: chain first, rule second

Logic diagram:

~~~text
HTTP GET /api/admin/report
       |
       v
Spring Security reactive WebFilterChainProxy
       |
       v
Evaluate SecurityWebFilterChain by @Order:
  API chain: securityMatcher("/api/**")  => MATCH
  Web chain: default any exchange        => not evaluated further
       |
       v
Select the API chain
       |
       v
Security filters configured in the API chain
       |
       v
authorizeExchange:
  "/api/public/**" -> permitAll()       => no match
  "/api/admin/**"  -> hasRole("ADMIN")  => MATCH
  anyExchange()    -> authenticated()   => not evaluated further
       |
       v
Authentication + authorization determine the outcome
       |
       +-- user has ROLE_ADMIN -> proceed to handler
       +-- authenticated user, missing role -> denied (typically 403)
       +-- unauthenticated -> challenge for authentication (typically 401 with HTTP Basic)
~~~

**Key takeaway:** `securityMatcher` does not have `permitAll()` or `hasRole()` methods because it does not directly decide permissions. Conversely, `pathMatchers` inside `authorizeExchange` does not switch to another chain; it only selects a rule **inside the already chosen chain**.

### 2.1. `securityMatcher` — scope applied to the entire chain

In the `ServerHttpSecurity` reactive DSL:

~~~java
http.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**")
);
~~~

The matcher is of type `ServerWebExchangeMatcher`. At runtime, it inspects the request information and returns a match or non-match result according to the reactive contract. `PathPatternParserServerWebExchangeMatcher` matches by path pattern; beyond paths, you can also design matchers by HTTP method, headers, or custom conditions when needed.

In the example above:
- `/api/orders` matches.
- `/api/public/info` matches.
- `/api/admin/report` matches.
- `/status` does not match.

A chain without an explicit `securityMatcher(...)` call typically uses a default matcher that matches every exchange. This is a convenient mechanism for the **final chain covering everything else**.

### 2.2. `authorizeExchange` — required permissions inside the chosen chain

~~~java
http.authorizeExchange(exchange -> exchange
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
);
~~~

This section is the **HTTP authorization rule set**. Spring Security evaluates rules in the order declared and applies the first matching rule. `anyExchange()` is the final rule for requests not caught by earlier rules.

- `permitAll()`: an authorization rule allowing access without requiring a logged-in identity. Other filters in the chain may still run.
- `authenticated()`: requires an authenticated identity.
- `hasRole("ADMIN")`: by default convention, requires the `ROLE_ADMIN` authority.
- `denyAll()`: denies access.
- `pathMatchers(...)`: selects requests by path or combined with HTTP method; it does not create a new `SecurityWebFilterChain`.

Sign to recognize: `securityMatcher` is a **chain-level** condition; `pathMatchers` inside the `authorizeExchange` DSL is a **rule-level** condition.

## 3. Direct comparison

| Aspect | `securityMatcher(...)` | `authorizeExchange(...)` |
| --- | --- | --- |
| Role | Determines whether the security chain applies to the request | Determines authorization requirements for a request already inside the chain |
| Location | On `ServerHttpSecurity` when building each `SecurityWebFilterChain` | On `ServerHttpSecurity` to register authorization rules |
| Condition | `ServerWebExchangeMatcher`, e.g., `/api/**` | `pathMatchers`, `matchers`, `anyExchange` |
| Outcome | Match/no match → selects the first matching chain | Rule `permitAll`, `authenticated`, `hasRole`, ... |
| Ordering | Across chains: `@Order` (smaller value has higher priority) | Across rules: declaration order inside `authorizeExchange` |
| When unmatched | Tries the next chain; if no chain matches, no web security chain processes the request | Moves to the next rule in the **same chain** |
| Common pitfalls | General chain placed before specialized chain, or missing catch-all | Broad rule shadows strict rule, or missing final rule |

Do not confuse the two kinds of precedence:
- `@Order(1)` and `@Order(2)` determine **which chain is evaluated first**.
- The order of `pathMatchers` inside `authorizeExchange` determines **which rule is evaluated first within the active chain**.
- `WebFilter` ordering inside a chain is a different mechanism; do not conflate it with the two precedences above.

## 4. When to use one chain vs. multiple chains?

### 4.1. One chain is usually enough when only access permissions differ

If all endpoints use the same authentication mechanism and similar filters, describe the paths directly in a single `authorizeExchange`:

~~~java
@Bean
SecurityWebFilterChain singleChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is an **illustrative configuration snippet**, requiring the corresponding imports and authentication beans. It uses a single default chain matching every request; `pathMatchers` only decides permissions. You do not need to create three separate `SecurityWebFilterChain` beans for the three permission levels `public`, `admin`, and `authenticated`.

### 4.2. Multiple chains are useful when request groups differ in security mechanisms

For example:
- `/api/**` might use OAuth2 Resource Server to validate Bearer JWTs.
- Browser pages might use form login, cookies/sessions, and appropriate CSRF protection.
- A group of operational endpoints might use a special authentication setup.

Each chain can have its own matcher, authentication mechanism, authorization rules, and appropriate session/CSRF policy. Two chains should not be split solely because each has one endpoint needing `permitAll`; simple rules handle that better.

**Always account for remaining paths:** if you only declare one chain with `securityMatcher("/api/**")`, requests outside `/api/**` will not match this chain. If no other chain catches them, they **are not protected by a Spring Security web filter chain**. This is especially dangerous for internal endpoints that become unintentionally public. Add a final catch-all chain or deliberately control scope with other safeguards.

## 5. Complete Java 17+ example with two chains

The example uses Spring Boot 3.3.13, Spring Security WebFlux, Java 17+, and Gradle 8.x. All endpoints are GET to focus on the two matcher layers. Both chains use **HTTP Basic** so they are easy to test; in real systems, API and web can certainly use different authentication mechanisms.

### 5.1. Project structure

~~~text
reactive-chain-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── ReactiveChainDemoApplication.java
    │   ├── DemoController.java
    │   └── SecurityConfig.java
    └── test/java/demo/
        └── SecurityRoutingTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-chain-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/java/demo/ReactiveChainDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveChainDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveChainDemoApplication.class, args);
    }
}
~~~

### 5.2. Endpoints to observe chain and rule selection

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class DemoController {

    @GetMapping("/api/public/info")
    Mono<String> publicApi() {
        return Mono.just("public-api");
    }

    @GetMapping("/api/orders")
    Mono<String> orders() {
        return Mono.just("orders");
    }

    @GetMapping("/api/admin/report")
    Mono<String> adminReport() {
        return Mono.just("admin-report");
    }

    @GetMapping("/status")
    Mono<String> status() {
        return Mono.just("healthy");
    }

    @GetMapping("/account")
    Mono<String> account() {
        return Mono.just("account");
    }
}
~~~

### 5.3. Configuring two `SecurityWebFilterChain` beans

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            // LAYER 1: this chain is selected only for /api/**.
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            // LAYER 2: permissions inside the API chain.
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            // No securityMatcher declared:
            // the final chain matches all remaining requests by default.
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/status").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers(
            PasswordEncoder passwordEncoder) {
        UserDetails reader = User.withUsername("reader")
            .password(passwordEncoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(passwordEncoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Explanation of choices:**
1. `@EnableWebFluxSecurity` enables reactive Spring Security configuration; in Spring Boot with the appropriate Security starter, this infrastructure is typically auto-configured as well. The annotation does not decide whether `/status` is public.
2. `@Order(1)` causes `apiSecurity` to be evaluated before `webSecurity`, which has `@Order(2)`. Lower numbers have higher priority.
3. `securityMatcher("/api/**")` on the API chain applies only to API paths. That condition **does not** grant access to the API; permission grants live in `authorizeExchange`.
4. `webSecurity` omits `securityMatcher`: by default it matches every request; it becomes the final chain serving `/status`, `/account`, and paths not matched by specialized chains.
5. `pathMatchers("/api/public/**").permitAll()` applies to the public API endpoint, while `pathMatchers("/api/admin/**").hasRole("ADMIN")` checks the ADMIN role; `anyExchange().authenticated()` protects the remaining API endpoints, such as `/api/orders`.
6. Both chains enable HTTP Basic and disable form login **only to make HTTP results easy to observe in the demo**. `PasswordEncoder` uses BCrypt; the in-memory users are demo accounts, not a production identity source.
7. CSRF is not disabled here; all demo endpoints are GET. For state-changing APIs, you must analyze the cookie/session, token, and CSRF mechanisms of each chain before changing the policy.

### 5.4. Why omitting `securityMatcher` on the final chain makes sense

Because every request passes through chain selection **in order**:
- Request `/api/orders` matches the `apiSecurity` chain first, so chain lookup stops; `webSecurity` is not applied to that request.
- Request `/status` does not match the API chain, so evaluation continues to `webSecurity` and `permitAll` is checked there.
- Request `/account` also enters `webSecurity` but does not match `/status`, so `anyExchange().authenticated()` applies.

If you reverse the `@Order` values so the catch-all chain is evaluated first, every request may be caught by the catch-all chain first. Then `/api/public/info` may require login and `/api/admin/report` may only require `authenticated()` instead of `ROLE_ADMIN` — which is a broken policy. You cannot expect Spring Security to evaluate the API chain after another chain has already matched.

## 6. Tracing each request: chain selection then rule selection

| Request | Selected chain | Selected rule | Outcome under table conditions |
| --- | --- | --- | --- |
| GET `/api/public/info`, unauthenticated | API (matches `/api/**`) | `/api/public/**` → `permitAll` | 200 |
| GET `/api/orders`, unauthenticated | API | `anyExchange().authenticated()` | 401 |
| GET `/api/orders`, Basic `reader` valid password | API | `anyExchange().authenticated()` | 200 |
| GET `/api/admin/report`, Basic `reader` valid password | API | `/api/admin/**` → `hasRole("ADMIN")` | 403 |
| GET `/api/admin/report`, Basic `admin` valid password | API | `/api/admin/**` → `hasRole("ADMIN")` | 200 |
| GET `/status`, unauthenticated | Web (catch-all) | `/status` → `permitAll` | 200 |
| GET `/account`, unauthenticated | Web (catch-all) | `anyExchange().authenticated()` | 401 |
| GET `/account`, Basic `reader` valid password | Web (catch-all) | `anyExchange().authenticated()` | 200 |

The HTTP codes above are the expected results of the **demo configuration** with HTTP Basic, form login disabled, GET endpoints, and no other custom security filters. In applications using OAuth2, form login, CORS, or custom exception handling, 401/403/redirect behavior may differ. `securityMatcher` and `authorizeExchange` do not emit HTTP status codes themselves; authentication, authorization, and exception handling filters enforce those decisions.

One practical distinction: `permitAll` grants **authorization** access, but it does not mean every filter in the chain is turned off. For example, a request sending a Basic header with a wrong password to a public endpoint can still be processed by the authentication filter and fail. Do not use `permitAll` as a way to remove all security filters.

## 7. Running with Gradle and curl

From the `reactive-chain-demo` directory, requiring JDK 17+, Gradle 8.x, and network access for initial dependency resolution:

~~~bash
gradle bootRun
~~~

If the Gradle Wrapper is present, run `./gradlew bootRun` on Unix/macOS or `gradlew.bat bootRun` on Windows.

Keep the server running at `http://localhost:8080`. The commands below print **only the HTTP status code** in a bash/Git Bash shell:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/public/info
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/orders
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/orders
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin/report
curl -s -u admin:admin-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin/report
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/status
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/account
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/account
~~~

Expected stdout, in order:

~~~text
200
401
200
403
200
200
401
200
~~~

Note: in Windows PowerShell, invoke `curl.exe` to use the curl binary instead of the alias; you may need to replace `/dev/null` with `NUL`. Do not use demo credentials in real environments, and with HTTP Basic outside localhost you must use HTTPS.

## 8. Automated testing with `WebTestClient`

Create `src/test/java/demo/SecurityRoutingTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class SecurityRoutingTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicApiUsesApiChainButNeedsNoLogin() {
        client.get().uri("/api/public/info")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public-api");
    }

    @Test
    void apiOrdersRequireAuthentication() {
        client.get().uri("/api/orders")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/api/orders")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void apiAdminRequiresAdminRole() {
        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-report");
    }

    @Test
    void webFallbackHasItsOwnAuthorizationRules() {
        client.get().uri("/status")
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/account")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/account")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("account");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Or `./gradlew test` / `gradlew.bat test` if the project has the wrapper. All four test methods are expected to PASS and Gradle should return exit code 0. Do not assert a fixed Gradle log string because console output depends on the environment.

These tests matter because they verify the **observable consequences** of both layers:
- `/api/public/info`: the API chain is selected properly and the public rule applies.
- `/api/admin/report`: the ADMIN authorization rule actually takes effect inside the API chain.
- `/status`, `/account`: requests outside the API are handled by the final chain.
- If chain ordering is wrong, at least one expectation fails, catching access-control regressions.

Endpoint tests only measure external outcomes; in complex cases, you can also inspect matcher conditions, chain beans, and security logs to explain why a result changed.

## 9. Four common failure scenarios

### 9.1. Using `securityMatcher` to "open" a public endpoint

Conceptually wrong example:

~~~java
http.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/public/**"))
    .authorizeExchange(ex -> ex.anyExchange().permitAll());
~~~

This chain only applies to `/public/**`; it **places no protective rules** on other URLs. If this is the only chain, a `/private` endpoint could fall outside the Spring Security web filter chain. To make one endpoint public while protecting the rest, use a catch-all chain:

~~~java
http.authorizeExchange(ex -> ex
    .pathMatchers("/public/**").permitAll()
    .anyExchange().authenticated()
);
~~~

The two code blocks above are **independent illustrations** of matcher semantics; do not add them simultaneously alongside the complete configuration in section 5.

### 9.2. General chain prioritized too early

Suppose the catch-all chain has `@Order(1)` and the API chain has `@Order(2)`. Because catch-all matches every exchange, the API chain is never selected. Rules inside the API chain such as `hasRole("ADMIN")` become ineffective for requests captured earlier by the catch-all chain.

**Fix:** give specialized chains higher priority, and put the catch-all chain last:

~~~java
@Order(1) // specialized /api/**
@Order(2) // all remaining URLs
~~~

These are only comments illustrating order; the annotations themselves must be placed on the `@Bean` methods as shown in the complete example.

### 9.3. Broad rule placed before strict rule

Inside a single `authorizeExchange`, the snippet below has an authorization flaw:

~~~java
.authorizeExchange(ex -> ex
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
)
~~~

Because `/api/admin/**` also belongs to `/api/**`, admin requests match the earlier `permitAll` rule. The ADMIN rule below it will not be reached for that case. Move the strict pattern earlier or narrow the public pattern specifically:

~~~java
.authorizeExchange(ex -> ex
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
)
~~~

**Changing `@Order` will not fix** this bug because the mistake is in **rule ordering within one chain**, not **ordering between chains**.

### 9.4. Forgetting the catch-all chain or catch-all rule

Two distinct mistakes that are easily conflated:
- **Missing catch-all chain:** some requests do not match any `SecurityWebFilterChain` and can bypass web security filters.
- **Missing catch-all rule inside the chosen chain:** some requests may not be governed by the explicit authorization rules you thought covered them. Final behavior depends on framework configuration; never rely on an "implicit" fallback to protect resources.

A safe construction for this lesson is **a final chain matching all URLs** and **each chain ending with `anyExchange().authenticated()` or `denyAll()` as appropriate**, after clearly defined exceptions.

## 10. Advanced considerations in reactive Spring Security

### 10.1. `ServerWebExchangeMatcher` and corresponding APIs

`securityMatcher` takes a `ServerWebExchangeMatcher` (for example `PathPatternParserServerWebExchangeMatcher`). This is a WebFlux API; do not confuse it with Servlet's `RequestMatcher`. Similarly, WebFlux configures with `ServerHttpSecurity` and returns `SecurityWebFilterChain`; Spring MVC/Servlet uses `HttpSecurity` and `SecurityFilterChain`.

When you need to match by HTTP method or other conditions, choose the appropriate matcher and test the exact method/path. Do not use an overly broad pattern to compensate for unclear scope.

### 10.2. Authentication filters and authorization rules are not the same thing

`authorizeExchange` does not create users, verify passwords, or decode JWTs. It defines **authorization conditions**. Mechanisms such as HTTP Basic, form login, or OAuth2 Resource Server perform **authentication**, and then authorization uses the resulting identity and authorities.

You can have `securityMatcher("/api/**")` on a chain with `oauth2ResourceServer(...)`, while the Web chain has `formLogin(...)`. In that case, the selected chain also determines **which set of authentication filters** is applied. This is a key reason to use multiple chains when an application serves multiple client types.

In the demo, both chains use Basic to keep testing simple; having separate chains is still meaningful because the **authorization rules differ**.

### 10.3. CSRF, HTTP methods, and CORS

`permitAll` is not synonymous with disabling CSRF. A POST/PUT/DELETE using a session or cookie can be rejected with 403 due to a missing CSRF token even when the authorization rule allows it. The GET tests in the example do not prove POST works. CSRF, CORS, and session configurations must be reviewed per endpoint group and authentication mechanism, especially when a stateless API and a session-based website use different chains.

If a proxy alters paths, context paths, or performs URL rewrites, inspect the actual path value received by the matcher to avoid unintended pattern behavior.

### 10.4. Method security is an additional layer

`@PreAuthorize` is enabled in WebFlux via the appropriate reactive method security configuration (for example `@EnableReactiveMethodSecurity`). This mechanism does not replace `securityMatcher` or `authorizeExchange`: it protects method invocations when executed. Sensitive endpoints should have both HTTP tests and authorization tests where business logic must be protected.

### 10.5. Logging and observing match decisions

When an endpoint unexpectedly returns 200/401/403, check in order:
1. The application is actually running reactive WebFlux, not accidentally running Servlet due to dependencies.
2. Which `SecurityWebFilterChain` beans are registered, and their `@Order`.
3. Which chain's matcher matches the request **first**.
4. Inside the selected chain, which `authorizeExchange` rule matches **first**.
5. What identity/authorities and other filters such as CSRF, HTTP Basic, or CORS/exception handling affect the outcome.

You can temporarily enable Spring Security logs to observe processing, but never include `Authorization` headers, passwords, JWTs, or session secrets in shareable logs. In production, use only observability levels consistent with security and privacy.

## 11. Practical checklist

- [ ] Clearly explain why **one or multiple** `SecurityWebFilterChain` beans are created.
- [ ] Specialized chains have properly scoped `securityMatcher` definitions.
- [ ] `@Order` places specialized chains **before** the catch-all chain.
- [ ] A final chain covers all requests that need protection.
- [ ] Within each chain, narrower rules precede broader rules.
- [ ] The final rule `anyExchange().authenticated()`/`denyAll()` is explicit.
- [ ] Public endpoints use `permitAll` as required; not misplaced at the chain layer.
- [ ] Tests cover anonymous, regular user, admin, API URLs, and non-API URLs.
- [ ] State-changing HTTP methods are also tested with CSRF when the application uses them.
- [ ] No demo passwords or unencrypted HTTP Basic credentials are used in production.

## 12. Self-check questions

1. **Does `securityMatcher("/api/**")` mean all APIs are allowed access?** No. It only decides which chain applies; `authorizeExchange` sets the permission rules.
2. **If two chains both match a request, do both run?** Not under Spring Security WebFlux chain selection: the first matching chain in order is chosen.
3. **How do `@Order(1)` and `pathMatchers` differ?** `@Order` orders *across chains*; `pathMatchers` orders rules inside the *selected chain* by declaration order.
4. **`/api/admin/report` belongs to the API chain but the caller only has ROLE_USER: why 403?** Because the `hasRole("ADMIN")` rule requires `ROLE_ADMIN`.
5. **What happens if the catch-all chain is placed before the API chain?** The API chain may never be evaluated and the API rules are bypassed.
6. **Is placing `pathMatchers("/api/**").permitAll()` before the ADMIN rule safe?** No, the overly broad pattern matches admin paths as well.
7. **What if only a chain for `/api/**` is declared and `/account` exists?** If no other chain matches, `/account` is not protected by those Spring Security web filter chains.
8. **Does `permitAll` stop all security filters and disable CSRF?** No; it is only an authorization decision.
9. **Do you need multiple chains just so `/public` needs no login and `/private` requires login?** Usually no. One chain and `authorizeExchange` are enough.
10. **In WebFlux, do you use `HttpSecurity` or `ServerHttpSecurity`?** Use `ServerHttpSecurity` and `SecurityWebFilterChain`.

## 13. Official references

- Spring Security — WebFlux Security, *Multiple Chains Support*: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Security — Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/authorize-http-requests.html
- Spring Boot 3.3 — System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3 — Gradle plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html

**Rule of thumb:** `securityMatcher` answers "**which chain manages this request?**"; `authorizeExchange` answers "**within that chain, what permissions does this request require?**". Only after answering both questions should you analyze authentication mechanisms, authorities, CSRF, and HTTP error responses.
