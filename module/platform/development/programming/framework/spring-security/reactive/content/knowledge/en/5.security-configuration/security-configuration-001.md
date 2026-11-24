# Configuration with Lambda DSL and Customizer in ServerHttpSecurity

> **Context:** Spring Boot 3.3.x, Spring WebFlux, Spring Security 6.x, and Java 17+. This lesson shows how to declare the HTTP security policy of a **reactive application** using `ServerHttpSecurity`, the lambda DSL, and `Customizer`; recognize when to keep default values and when to customize; and verify that the configuration actually takes effect.

## 1. Reading the three configuration components correctly

In a WebFlux application, `ServerHttpSecurity` is the **builder** used to define the security policy for `ServerWebExchange` instances. After configuring it, you call `build()` to create a `SecurityWebFilterChain`. Spring Security uses this chain to process requests before they reach the controller.

```text
Client HTTP request
    |
    v
ServerWebExchange (Spring WebFlux)
    |
    v
SecurityWebFilterChain
    |-- Check CSRF/CORS/headers as configured
    |-- Authenticate (e.g., HTTP Basic, form login, bearer token)
    |-- Authorize (authorizeExchange)
    v
@RestController -> Mono/Flux -> HTTP response
```

Three names that are very easy to confuse:

| Component | Role |
|---|---|
| `ServerHttpSecurity` | Builder for configuring **reactive** HTTP security policies |
| `Customizer<T>` | Functional interface that accepts a configuration object of type `T` to modify it |
| `SecurityWebFilterChain` | Result after `http.build()`, applied by Spring Security to requests |

In **Servlet/MVC** you commonly encounter `HttpSecurity` and `SecurityFilterChain`; in **WebFlux** you use `ServerHttpSecurity` and `SecurityWebFilterChain`. Do not mix types from the two stacks.

Minimal structure:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

This is a **method snippet placed inside a `@Configuration` class**, not a standalone Java program. The lambda in `authorizeExchange` defines who can access which requests; `Customizer.withDefaults()` in `httpBasic` and `formLogin` enables the corresponding authentication mechanism with Spring Security's default configuration. `build()` creates the chain.

## 2. How does the lambda DSL differ from the old chaining syntax?

The **lambda DSL** passes a function into each configuration method:

```java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/public").permitAll()
        .anyExchange().authenticated())
    .httpBasic(Customizer.withDefaults());
```

Here:

1. `authorizeExchange(...)` takes a `Customizer<ServerHttpSecurity.AuthorizeExchangeSpec>`.
2. The `exchanges` variable represents the authorization configuration section. The `pathMatchers(...)` and `anyExchange()` methods are used to register conditions in order.
3. After the closing `)` of the lambda, you return to the `http` builder so you can continue calling `httpBasic(...)`; **`.and()` is not needed**.
4. Finally, call `http.build()` once to create the chain.

The older style that relied heavily on non-lambda methods and `.and()` has become a pattern to avoid when moving to newer Spring Security versions. The lambda DSL makes the boundaries between configuring `authorizeExchange`, `httpBasic`, `formLogin`, `csrf`, or `headers` clear. In Spring Security 7, lambda configuration is the required direction; the examples in this lesson use the Spring Security 6.x API.

**What a lambda does not do automatically:** it does not make a route public, grant roles, create users, validate JWTs, or disable CSRF on its own. Every security effect comes from the methods called inside it.

## 3. `Customizer<T>`, lambdas, and `Customizer.withDefaults()`

`Customizer<T>` is a functional interface with the following concept:

```java
@FunctionalInterface
interface Customizer<T> {
    void customize(T target);
}
```

This is a **conceptual illustration**, not code that replaces `org.springframework.security.config.Customizer`. Spring Security provides the actual interface; when implementing, import:

```java
import org.springframework.security.config.Customizer;
```

Three call forms to distinguish:

| Form | Meaning |
|---|---|
| `.httpBasic(Customizer.withDefaults())` | Uses HTTP Basic with Spring Security's default options |
| `.httpBasic(basic -> {})` | Empty lambda: semantically equivalent to enabling HTTP Basic with defaults |
| `.httpBasic(basic -> basic.authenticationManager(manager))` | Customizes HTTP Basic with an authentication manager provided by the application; `manager` must be a valid `ReactiveAuthenticationManager` |

**`withDefaults()` does not mean "open access to everyone"**, nor does it mean "clear all previous configuration". It is a `Customizer` that performs no further modifications on the passed-in spec; the method receiving it still activates the corresponding mechanism with its defaults. A custom `Customizer` is a lambda containing specific calls.

Syntactically equivalent when **no additional options are needed**:

```java
// Two ways to write it in two alternative configurations:
http.httpBasic(Customizer.withDefaults());

// Equivalent form:
http.httpBasic(basic -> { });
```

Example of a customizer that makes actual changes:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/health").permitAll()
    .anyExchange().authenticated());
```

If you only want to enable the default configuration of the HTTP Basic mechanism, choose `withDefaults()` so readers know there are no hidden customizations. If you need to change a value, use a lambda with a body; do not call extra options you do not understand just because the IDE suggests them.

### A `Customizer` can be extracted into a reusable method

It is not mandatory to cram every lambda into the `@Bean` method. One clear approach that does not depend on auto-discovering customizer beans is to declare **a method that returns a `Customizer` and pass it explicitly**:

```java
private static Customizer<ServerHttpSecurity.AuthorizeExchangeSpec> rules() {
    return exchanges -> exchanges
        .pathMatchers("/health").permitAll()
        .anyExchange().authenticated();
}

@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(rules())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This snippet is **part of an illustrative configuration** and must be placed inside a class with imports and `@Configuration`; it **replaces** the corresponding `@Bean` configuration rather than being added alongside the complete example below. Benefit: it groups rules into a named customizer while preserving the call order and scope of the policy.

**Be careful when using auto-discovered `Customizer` beans:** the application mechanism and ordering of top-level customizers can depend on the Spring Security version; do not create multiple beans affecting the same matcher and assume an invariant order. For small applications, passing customizers explicitly to the exact chain is easier to reason about.

## 4. Parts of `ServerHttpSecurity` commonly configured with lambdas

| API | Purpose | Example |
|---|---|---|
| `authorizeExchange` | Allow/deny/authorize each request | `.authorizeExchange(ex -> ex.anyExchange().authenticated())` |
| `httpBasic` | Authenticate username/password via HTTP Basic | `.httpBasic(Customizer.withDefaults())` |
| `formLogin` | Form login and form-based authentication mechanism | `.formLogin(Customizer.withDefaults())` |
| `csrf` | CSRF protection for applicable requests | `.csrf(Customizer.withDefaults())` |
| `cors` | Integrate CORS handling with a CORS policy source | `.cors(Customizer.withDefaults())` |
| `headers` | Configure security response headers | `.headers(Customizer.withDefaults())` |
| `exceptionHandling` | Customize how the application responds to authentication/access denied errors | `.exceptionHandling(handler -> { /* configure when needed */ })` |
| `oauth2ResourceServer` | Validate bearer access tokens with resource server configuration | `.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))` |
| `securityMatcher` | Specify which requests the **entire chain** applies to | `.securityMatcher(matcher)` |
| `build` | Finalize the builder into a `SecurityWebFilterChain` | `.build()` |

Only enable the features you need. For example, the JWT configuration above **requires the corresponding dependency and issuer/JWK/introspection configuration**; a single line `jwt(withDefaults())` does not automatically validate tokens. Likewise, `cors(withDefaults())` does not mean every origin is allowed; an appropriate CORS policy must be provided.

Each method has its own defaults. **Spring Boot's default configuration when there is no custom chain** and **the features you explicitly call on a custom chain** are two distinct things. Declaring your own `SecurityWebFilterChain` causes Spring Boot to back off its default HTTP security configuration so your chain defines the policy; do not assume all paths remain protected as before if you omit rules.

## 5. Complete, runnable Spring Boot WebFlux example

Learning goal: a single application with a **public GET**, a **GET requiring USER**, a **GET requiring ADMIN**, and a fallback requiring authentication. HTTP Basic + form login use `Customizer.withDefaults()`; authorization is expressed with the lambda DSL. No datasource or OAuth2 is added yet so the chain policy is easy to see.

Use **Spring Boot 3.3.13**, Java 17+, and a compatible Gradle version. Create the structure:

```text
security-lambda-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/security/
    │   ├── DemoApplication.java
    │   └── SecurityConfig.java
    └── test/java/example/security/
        └── SecurityDslTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'security-lambda-demo'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.security'
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
```

**src/main/java/example/security/DemoApplication.java**

```java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @RestController
    static class DemoController {
        @GetMapping("/api/ping")
        Mono<String> ping() {
            return Mono.just("pong");
        }

        @GetMapping("/api/report")
        Mono<String> report() {
            return Mono.just("report for USER");
        }

        @GetMapping("/api/admin")
        Mono<String> admin() {
            return Mono.just("admin area");
        }
    }
}
```

**src/main/java/example/security/SecurityConfig.java**

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/report").hasRole("USER")
                .pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

**Explanation of each part of the configuration:**

1. `@Bean SecurityWebFilterChain` provides the chain for Spring Security to use with WebFlux.
2. `ServerHttpSecurity http` is supplied by Spring when building the security configuration; it differs from MVC's `HttpSecurity`.
3. The three `pathMatchers(HttpMethod.GET, ...)` calls define specific policies for **GET** on each route. Other HTTP methods are not automatically exempted.
4. `permitAll()` allows access to `/api/ping` without logging in.
5. `hasRole("USER")` requires the `ROLE_USER` authority; `hasRole("ADMIN")` requires `ROLE_ADMIN`.
6. `anyExchange().authenticated()` sets a fallback for requests that did not match earlier rules. This is an **authentication requirement**, not authorization across every application object.
7. `httpBasic(Customizer.withDefaults())` enables HTTP Basic support; `formLogin(Customizer.withDefaults())` enables the default form login.
8. `build()` completes the chain. You do not need to call `.and()` between lambdas.

Because the example does not declare a custom `ReactiveUserDetailsService`, Spring Boot can provide a development account `user` with a random password printed in the startup log and the default `USER` role. You must change the authentication setup before deploying to production.

### Running the application and testing HTTP requests

In the project directory:

```bash
gradle bootRun
```

If the project already includes the Gradle wrapper, run `./gradlew bootRun` or `gradlew.bat bootRun` on Windows. Check the log to obtain the development password for that startup, then test:

```bash
# Public
curl -i -H "Accept: application/json" http://localhost:8080/api/ping

# Authentication required: no credentials
curl -i -H "Accept: application/json" http://localhost:8080/api/report

# Replace GENERATED_PASSWORD with the password shown in the startup log
curl -i -H "Accept: application/json" \
  -u "user:GENERATED_PASSWORD" \
  http://localhost:8080/api/report

# Same user, missing ROLE_ADMIN
curl -i -H "Accept: application/json" \
  -u "user:GENERATED_PASSWORD" \
  http://localhost:8080/api/admin
```

| Request | Expected primary outcome |
|---|---|
| `GET /api/ping` without credentials | `200 OK`, body `pong` |
| `GET /api/report` without credentials, `Accept: application/json` | `401 Unauthorized` |
| `GET /api/report` with `user` + valid password | `200 OK`, body `report for USER` |
| `GET /api/admin` with default user having `ROLE_USER` | `403 Forbidden` |

For browsers that prefer HTML, an unauthenticated request may receive a redirect to the form login page instead of an API-style `401` response. That is why the tests above explicitly set `Accept: application/json` to make HTTP Basic/API behavior easy to observe. Do not assume every error page body has a fixed format.

### Automated testing with WebTestClient

Add the file below to verify that the policy is not accidentally altered when editing lambdas. The test sets the password **only within the test application context**, without overwriting production values:

**src/test/java/example/security/SecurityDslTest.java**

```java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.security.user.password=test-password")
@AutoConfigureWebTestClient
class SecurityDslTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsAllowed() {
        client.get().uri("/api/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void reportRequiresLogin() {
        client.get().uri("/api/report")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void userCanReadReport() {
        client.get().uri("/api/report")
            .headers(headers -> headers.setBasicAuth("user", "test-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report for USER");
    }

    @Test
    void ordinaryUserCannotReadAdmin() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth("user", "test-password"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Run:

```bash
gradle test
```

Expected result: **4 tests PASS** once dependencies are downloaded successfully and the app starts in the test context. This is a complete example with class name, package, source path, and corresponding dependencies; no manual schema/database setup is needed. If you try this on a project that already replaced `ReactiveUserDetailsService` with a custom bean, the auto-generated user behavior will differ: adjust the test fixture to match that project's authentication source.

## 6. Matcher ordering in `authorizeExchange`

Rules are evaluated in registration order; **a broad rule placed earlier can shadow a specific rule placed after it**.

Correct for an API that has both public and admin areas:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll())
```

The snippet above is only an **illustrative configuration lambda fragment**, not standalone Java; if you use `anyExchange().denyAll()` together with form login, remember to account for the login paths, static resources, and operational endpoints that must be served/permitted by design. In the runnable example in section 5, the fallback uses `authenticated()` to avoid mixing the two goals.

Example of a configuration mistake in **ordering**, which should not be used:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").permitAll()        // too broad
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated())
```

The request `/api/admin/users` already matches `/api/**`, so the ADMIN rule placed after it no longer protects it as intended. Place stricter/specific rules before broader rules.

Meaning of authorization actions:

| Action | Check |
|---|---|
| `permitAll()` | Allows everyone, including unauthenticated callers |
| `authenticated()` | Requires a valid identity |
| `hasRole("ADMIN")` | Requires `ROLE_ADMIN` (with the default role prefix) |
| `hasAuthority("SCOPE_orders.read")` | Requires an authority with the exact parameter name, useful for scopes when the system maps scopes to corresponding authorities |
| `denyAll()` | Denies all requests matching the rule |
| `access(...)` | Calls a custom reactive authorization manager, typically needed when access depends on context |

**`hasRole("ADMIN")` should not be passed `"ROLE_ADMIN"` as its argument** by default, because the API automatically prepends the role prefix. If authorizing by JWT scopes, verify the exact authority mapping before choosing `hasAuthority(...)`. HTTP rules do not replace **per-record/per-tenant** authorization checks in the service layer.

## 7. `pathMatchers` and `securityMatcher` are not the same

- `pathMatchers(...)` **inside** `authorizeExchange` only decides authorization for requests that have already entered the chain.
- `securityMatcher(...)` **on the `ServerHttpSecurity` builder** decides whether a request enters **that chain** at all.

If you only have one chain covering the entire application, you may not need `securityMatcher` yet. When you have multiple chains, this is a mandatory consideration so you do not leave paths outside the matched scope unprotected.

**Alternative example to the single configuration in section 5** when you want to separate API routes and web routes. Place the two `@Bean` methods in **one** `@Configuration` class, with the imports below; do not keep the old chain bean from section 5 at the same time.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher
    .PathPatternParserServerWebExchangeMatcher;

@Configuration(proxyBeanMethods = false)
class MultiChainSecurityConfig {

    @Bean
    @Order(0)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/ping").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

**Note on the code above:** Java does not allow splitting a single `import` line across two lines as shown for formatting; when copying, write it out on a single line:

```java
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
```

Here `@Order(0)` selects the API chain before trying the web chain. The API chain applies only to URLs starting with `/api/`. The web chain has no specific `securityMatcher`, so it can serve as a fallback. **If there is no fallback and a URL does not match any chain, Spring Security will not protect that URL through the declared chains.** Test non-matching routes, including both HTTP methods and path prefixes.

The multi-chain section is intended to illustrate scope and ordering; if an application only serves HTTP APIs, a single clear chain like section 5 is usually easier to maintain.

## 8. Using lambdas to enable/disable or configure CSRF, CORS, and form login

### 8.1 Enabling defaults vs. disabling a feature

```java
// Keep CSRF using the default mechanism
.csrf(Customizer.withDefaults())

// Only when the architecture proves CSRF is not needed on this chain
.csrf(csrf -> csrf.disable())
```

**CSRF** is especially relevant when the browser automatically attaches cookies/sessions or credentials to state-changing requests. The section 5 example only uses GET, so there is no need to disable CSRF for the demo. Do not copy `csrf.disable()` into a web app that uses form login just because POST returns `403`. First determine how the CSRF token is issued and sent. For a true bearer-token API that does not rely on credentials automatically sent by the browser, the CSRF design may differ, but the assumptions should be documented and tested.

### 8.2 Using `Customizer.withDefaults()` for form/basic

```java
.httpBasic(Customizer.withDefaults())
.formLogin(Customizer.withDefaults())
```

Both are **authentication mechanisms**, not access-granting rules. If you want an API to accept only bearer tokens, you typically disable form login and Basic in **that API's** chain while configuring token verification, though you must still review the application's cookie/session/CSRF setup:

```java
// Alternative configuration fragment; requires the resource-server dependency,
// issuer/JWK configuration, and an appropriate policy in a real application.
http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/public").permitAll()
        .anyExchange().authenticated())
    .httpBasic(basic -> basic.disable())
    .formLogin(form -> form.disable())
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()));
```

**The snippet above is not a standalone runnable JWT configuration:** it is missing the `SecurityWebFilterChain` bean, `build()`, the Spring Security resource server dependency, and the issuer/JWK trust settings. Only copy it when you are implementing that exact resource server model and have configured everything completely.

### 8.3 CORS is not an "allow all" policy

```java
.cors(Customizer.withDefaults())
```

This line integrates CORS using a `CorsConfigurationSource` or the corresponding WebFlux CORS configuration, depending on the design. It does not grant access to every origin and does not replace authentication/authorization. Do not combine `allowedOrigins("*")` with credentials just for convenience during development. Browsers enforce CORS, whereas curl or service clients can send requests directly without being blocked by browser mechanisms.

### 8.4 Customizing the login page

```java
.formLogin(form -> form.loginPage("/login"))
```

This is a configuration fragment: if you choose a custom login page, **the application must actually serve** `GET /login` and have a policy permitting access to it appropriately. Do not set `loginPage("/login")` and expect Spring to generate your custom HTML UI automatically. If you do not need to change the login page, `formLogin(Customizer.withDefaults())` is simpler.

## 9. Choosing the right configuration structure

**A single chain with inline lambdas** fits when the policy is short and there are only a few routes: you can see the matcher order right inside `@Bean`.

**Extracting `Customizer<AuthorizeExchangeSpec>` into methods** fits when multiple logical policies have clear names and you want to reuse them deliberately while keeping call order explicit.

**Multiple chains with `securityMatcher` and `@Order`** fit when you need separate configurations for API and web UI, or regions with different authentication mechanisms. There must be a fallback so paths are not accidentally left unprotected.

Two configuration axes must be distinguished:

| Axis | Questions |
|---|---|
| Authentication | Who is the caller? Basic, form, JWT, OAuth2, or custom manager? Where are credentials verified? |
| Authorization | Is the caller allowed to access the URL/action or specific data? `permitAll`, `authenticated`, role, scope, access policy? |

Customizing `SecurityWebFilterChain` does not automatically define the user source. If Boot still meets the conditions to create a development user, the `user` account with an auto-generated password can still appear even after you have written a lambda DSL.

## 10. Common mistakes and how to recognize them

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| Using `HttpSecurity`/`SecurityFilterChain` in WebFlux | Those are Servlet stack types | Use `ServerHttpSecurity`/`SecurityWebFilterChain` |
| Thinking `Customizer.withDefaults()` allows anonymous access | It enables the feature with its default configuration | Put `permitAll()` on the right matcher if public access is intended |
| Calling `anyExchange()` before specific rules | A catch-all rule shadows or invalidates later matchers | Put specific rules first and the fallback last |
| Writing `"/api/**".permitAll()` before `"/api/admin/**"` | Admin URLs match the broad public rule | Place stricter admin rules before public/broad rules |
| Forgetting a fallback or forgetting chain scope | Endpoints can be missed or bypass the chain | Explicit `anyExchange()` and final chain; test unmatched URLs |
| Using `.and()` from older guides | Easy to confuse builders/specs and not idiomatic for the current lambda DSL | Write sequential lambdas and call `build()` |
| Confusing `hasRole("ADMIN")` with `hasAuthority("ADMIN")` | Roles usually prepend the `ROLE_` prefix automatically | Verify the actual authorities in the principal |
| Disabling CSRF to fix `403` errors | Can open CSRF vulnerabilities for cookie/session web apps | Check cookies, CSRF token, and flow per client type |
| Enabling `cors(withDefaults())` and thinking all origins are allowed | CORS requires a specific source policy | Deliberately configure allowed origins/methods/headers |
| Enabling JWT without issuer/audience | Tokens are not validated thoroughly enough | Configure the resource server and appropriate validators |
| Having multiple `SecurityWebFilterChain` beans without managing order | Requests may enter an unexpected chain | Use `securityMatcher`, `@Order`, and test each group |
| Declaring a chain bean and thinking Boot still applies its initial policy | A custom chain causes HTTP auto-configuration to back off | Define all rules and the fallback explicitly |
| Testing only `200` responses | An endpoint might be accidentally public | Test `401`, `403`, unauthorized routes, and other HTTP methods |

A systematic debugging approach:

1. Verify the application is actually running **reactive** and the Security starter is on the classpath.
2. Confirm how many `SecurityWebFilterChain` beans exist and which chain has a `securityMatcher` matching the request.
3. Read the order of `pathMatchers` in `authorizeExchange` before looking at the controller.
4. Determine whether the request was rejected due to being **unauthenticated** (usually `401` or login redirect) or **insufficient permissions/CSRF** (usually `403`).
5. Inspect the actual roles/scopes on the principal; do not guess from the username.
6. Use `WebTestClient` for both allow and deny cases, with the appropriate HTTP method and `Accept` header.

When diagnostic security logging is needed, only enable verbose log levels in a controlled test environment and do not log or share bearer tokens, passwords, or sensitive cookies/sessions.

## 11. Self-check exercises

1. Starting from the section 5 example, change `/api/ping` to `authenticated()`; demonstrate that the public test fails and update the test to match the new policy.
2. Change `/api/report`'s matcher from `hasRole("USER")` to `hasAuthority("ROLE_USER")`; explain why the result is usually equivalent for the default user.
3. Replace `.httpBasic(Customizer.withDefaults())` with `.httpBasic(basic -> {})` and test the four statuses in section 5. State what changes and what stays the same.
4. Place `pathMatchers("/api/**").permitAll()` before the admin rule, and demonstrate with a test why rule ordering is a security control.
5. Add `@Order` and `securityMatcher` to separate API/web, then test a URL outside `/api/**` and explain which chain receives it.
6. Explain why adding `.cors(Customizer.withDefaults())` does not mean allowing all origins, and why `.csrf(csrf -> csrf.disable())` is not the default solution for form-login web apps.

**Remember:** `ServerHttpSecurity` builds the security chain; the **lambda DSL** describes the policy section by section; **`Customizer.withDefaults()`** simply asks to use that feature's default configuration. Safety comes from defining the right chain scope, matcher order, authentication mechanisms, and authorization conditions, then verifying them with real requests and negative tests.

## Official references

- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Security — Authorize ServerHttpRequest (reactive): https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/authorize-http-requests.html
- Spring Security — Lambda DSL and `Customizer.withDefaults()`: https://spring.io/blog/2019/11/21/spring-security-lambda-dsl/
- Spring Boot 3.3 — Security (WebFlux): https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
