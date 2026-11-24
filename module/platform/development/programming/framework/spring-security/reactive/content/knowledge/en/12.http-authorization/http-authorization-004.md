# Authorization by Path, HTTP Method, and Path Variables in Spring Security WebFlux

> **Scope:** Spring WebFlux + Spring Security 6.x, Spring Boot 3.3.x, and Java 17+. The goal is to write **reactive HTTP authorization** policies based on path, HTTP method, and URI variables, understand matcher evaluation order, perform simple ownership checks using `AuthorizationContext`, and prove correctness/incorrectness with `WebTestClient`. Illustrative syntax targets Spring Security 6.x; when using newer versions, verify APIs and update to supported, security-patched dependencies.

## 1. Distinguishing Authentication and Authorization

**Authentication** answers "who is calling?". For example, the server verifies HTTP Basic, form login, or JWT and creates an `Authentication`. **Authorization** answers "is this authenticated request allowed to perform this action?". In WebFlux, Spring Security uses `SecurityWebFilterChain` to enforce policies before the request enters the controller.

```text
HTTP request: GET /api/accounts/alice
                 |
                 v
     SecurityWebFilterChain
                 |
       verify HTTP Basic/JWT...
                 |
       Authentication: name=alice
                 |
       authorizeExchange()
          +-- match URL/method
          +-- extract path variable {username}=alice
          +-- decide permission from Authentication
                 |
            grant / deny
                 |
           @RestController
```

The `authenticated()` condition only proves that the caller has a valid identity per the configured mechanism; it **does not automatically prove the caller owns the record** identified by the ID in the URL. `hasRole("ADMIN")` checks the role granted to the caller, not the owner of an order. When all three axes are needed, design the corresponding rules and check data permissions in the business layer.

In a **reactive** application:

- Builder: `org.springframework.security.config.web.server.ServerHttpSecurity`.
- Builder result: `org.springframework.security.web.server.SecurityWebFilterChain`.
- Request configuration: `authorizeExchange(exchanges -> ...)`.
- URL/method matcher: `pathMatchers(...)`.
- Manager for custom logic: `ReactiveAuthorizationManager<AuthorizationContext>`.
- Request and URI variable info: `org.springframework.security.web.server.authorization.AuthorizationContext`.

**Do not mix with Servlet/MVC:** `HttpSecurity`, `SecurityFilterChain`, and `authorizeHttpRequests().requestMatchers(...)` belong to a different API branch. Do not copy a Servlet `RequestAuthorizationContext` example into WebFlux assuming it is the same type.

## 2. Basic Structure: pathMatchers and anyExchange

A typical WebFlux configuration:

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/api/admin/**").hasRole("ADMIN")
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

**This is an illustrative bean method**, which must be placed in a `@Configuration` class with the appropriate imports; `Customizer` is imported from `org.springframework.security.config.Customizer`. `.and()` is not needed when using the lambda DSL.

Meaning:

1. URLs under `/public/**`: allow everyone, even without logging in.
2. URLs under `/api/admin/**`: require authority `ROLE_ADMIN`.
3. Remaining URLs under `/api/**`: only require an authenticated identity.
4. Any other exchange: deny (fail closed).
5. HTTP Basic is enabled with `Customizer.withDefaults()` so clients can send credentials; it **does not replace** any authorization rule.

Rules are evaluated **in declaration order**; the first matching rule is used. Therefore, narrow/strict conditions must be placed before broad conditions, and the `anyExchange()` fallback goes **last**.

### Common Decisions

| Action | Meaning | When Appropriate |
|---|---|---|
| `permitAll()` | Requires no authentication/role for matching requests | Intentionally public health endpoints, public docs |
| `authenticated()` | Requires a genuinely authenticated user | Internal APIs for logged-in users |
| `hasRole("ADMIN")` | Requires authority `ROLE_ADMIN` under the default prefix | Administrative routes |
| `hasAuthority("SCOPE_reports.read")` | Requires the exact authority name passed | JWT scopes mapped to authorities as shown |
| `hasAnyRole("EDITOR", "ADMIN")` | Any one of the listed roles | Write endpoints for multiple groups |
| `denyAll()` | Blocks matching requests | URLs outside the listed scope |
| `access(reactiveManager)` | Applies custom permission logic | Comparing path variables with the user, async owner/tenant checks |

For `hasRole("ADMIN")`, do not write `hasRole("ROLE_ADMIN")` when using the default prefix; if your authority is `"ROLE_ADMIN"`, pass `"ADMIN"` to `hasRole`. With OAuth2/JWT, claim/scope/role mapping depends on configuration; always verify actual authorities rather than inferring from token text or username.

## 3. Authorization by **Path**

### 3.1 Common Patterns

| Matcher | Example Matching Path | Meaning |
|---|---|---|
| `/api/ping` | `/api/ping` | Exact path |
| `/api/accounts/*` | `/api/accounts/alice` | One segment at the `*` position |
| `/api/accounts/**` | `/api/accounts/alice`, sub-paths | Multi-segment scope; be careful when granting public access |
| `/api/accounts/{username}` | `/api/accounts/alice` | Matches segment with variable name `username` |
| `/api/projects/{projectId}/members` | `/api/projects/42/members` | Matcher with an inline variable |
| `/api/admin/**` | `/api/admin/audit` | Route branch requiring admin permissions |

Spring WebFlux and Spring Security matchers are built on path patterns; `{username}` is a **URI variable extracted from the path**. Do not treat the string `"{username}"` as a literal username. Specific patterns follow `PathPattern` semantics, so when using wildcards, encoded segments, trailing slashes, or context path prefixes, test the actual running system.

**Distinguish path from query string:** The URL `/api/accounts/alice?detail=full` has path `/api/accounts/alice`; the query parameter `detail=full` is not a variable in `/api/accounts/{username}`. If permissions depend on query params/headers, do not pretend `pathMatchers` automatically checks them; use verified logic at the appropriate layer or a custom matcher.

### 3.2 Critical Rule Ordering Error

**Wrong:**

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated())
```

The request `GET /api/admin/users` is already permitted by the preceding `/api/**` rule, so the admin rule no longer protects that URL.

**Right:**

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll())
```

These are **two mutually exclusive configuration snippets**; do not paste both simultaneously into the runnable example below. The "narrow before broad" principle does not replace code-reviewing order, because a correct rule in the wrong position still creates a vulnerability.

### 3.3 URL Matchers Differ from Controller Mappings

Security inspects requests **before** the controller handles them. Do not assume:

- `@GetMapping("/api/orders/{id}")` automatically grants permission to anyone who knows `id`.
- Security and the controller use the same normalization, decoding, trailing slash handling, or path prefix for the same URL if you customize matchers on one side.
- A URL without a controller handler will always be blocked safely. If the policy is too broad, Security may permit the request before WebFlux returns `404`.

Write tests for canonical URLs, URLs with extra segments, lookalike paths near sensitive matchers, and unintended methods.

## 4. Authorization by **HTTP Method**

`ServerHttpSecurity.AuthorizeExchangeSpec.pathMatchers` has an overload accepting `HttpMethod`:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/articles/**").permitAll()
    .pathMatchers(HttpMethod.POST, "/api/articles/**").hasRole("EDITOR")
    .pathMatchers(HttpMethod.PUT, "/api/articles/**").hasRole("EDITOR")
    .pathMatchers(HttpMethod.PATCH, "/api/articles/**").hasRole("EDITOR")
    .pathMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
    .anyExchange().denyAll())
```

This snippet requires importing `org.springframework.http.HttpMethod`.

**One URL, multiple methods, multiple policies:** publicly reading an article does not mean anyone can edit, delete, or create articles. For REST route groups, GET/HEAD, POST, PUT, PATCH, and DELETE are usually separated and authorized accordingly.

### 4.1 Method-Specific vs. Method-Agnostic

- `pathMatchers(HttpMethod.GET, "/api/articles/**")` only matches **GET** requests against that pattern.
- `pathMatchers("/api/articles/**")` does not constrain the method; if placed before write rules, it can allow all methods into the controller.
- When a matcher does not match the method, Spring Security checks the next rule; with `anyExchange().denyAll()`, unlisted methods are denied.

**HEAD and OPTIONS must be considered separately.** Spring WebFlux may support HEAD for GET handlers; that does not make an `HttpMethod.GET` matcher automatically match HEAD. CORS preflight uses OPTIONS with corresponding headers and requires proper CORS configuration rather than unconditionally opening `OPTIONS /**` just to silence frontend errors.

### 4.2 Authorization Differs from CSRF

A `POST` with `ROLE_EDITOR` can still receive **403 Forbidden** for lacking a CSRF token when the chain uses CSRF protection (common in web apps with cookies/sessions). `permitAll()` also **does not automatically disable CSRF**.

```text
POST /api/articles
  |
  +-- CSRF protection: valid token? (if applicable)
  |
  +-- Authentication: who is the caller?
  |
  +-- Authorization: does the caller have ROLE_EDITOR?
  |
  +-- Controller: write data
```

Do not fix `403` by defaulting to `csrf(csrf -> csrf.disable())`. Determine whether requests use browser cookies that automatically send credentials or API bearer tokens, then configure CSRF according to the threat model. The runnable example in Section 7 **keeps CSRF enabled** to test both method authorization and CSRF.

## 5. Path Variables and AuthorizationContext

For the pattern `/api/accounts/{username}`, you may want the rule: **the user themselves may view the account bearing their username, or ADMIN may view any account**.

```text
GET /api/accounts/alice
    |-- pathMatchers(..., "/api/accounts/{username}")
    |-- AuthorizationContext.getVariables()["username"] = "alice"
    |-- Authentication.getName() = "alice"
    |-- ownerOrAdmin? -> GRANT
```

In Spring Security reactive, when a matcher extracts URI variables, `AuthorizationContext` provides these APIs:

```java
context.getExchange();   // ServerWebExchange
context.getVariables();  // Map<String,Object>
```

Get the name and type right: this is `org.springframework.security.web.server.authorization.AuthorizationContext`, **not** Servlet's `org.springframework.security.web.access.intercept.RequestAuthorizationContext`. `getVariables()` yields values of type `Object`, not automatically validated IDs or controller `@PathVariable`s.

### 5.1 URI Variable Matchers Do Not Automatically Check Permissions

```java
.pathMatchers(HttpMethod.GET, "/api/accounts/{username}")
    .authenticated()
```

The configuration above only requires **the caller to be logged in**; it **does not check** whether the username in the URL equals the authenticated identity. Alice can still call `/api/accounts/bob` if the controller/service does not check permissions further. This is a classic example of **broken object-level authorization (BOLA/IDOR)**.

To perform a check at the HTTP layer, use `access(ReactiveAuthorizationManager<AuthorizationContext>)` or a lambda with the same signature. The decision must rely on a **trusted `Authentication`** and the inspected URI value, not on an `X-User` header or self-reported caller body.

### 5.2 ReactiveAuthorizationManager Reading Variables and Identity

A reactive manager in Spring Security 6.x has the signature pattern:

```java
Mono<AuthorizationDecision> check(
    Mono<Authentication> authentication, AuthorizationContext context);
```

This is the illustrative form of the method in `ReactiveAuthorizationManager<AuthorizationContext>`. Inside:

- `authentication`: publisher that may emit the `Authentication` provided by Spring Security; if absent, it may be empty.
- `context.getVariables()`: variables produced by the path matcher, such as `username`.
- `AuthorizationDecision(true/false)`: permit or deny.
- To stay reactive, use `map`/`flatMap` and return `Mono<AuthorizationDecision>`, **never call `block()`/`subscribe()` manually**.

A safe, deny-by-default version:

```java
private ReactiveAuthorizationManager<AuthorizationContext> ownerOrAdmin() {
    AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    return (authentication, context) -> {
        Object value = context.getVariables().get("username");
        if (!(value instanceof String username)) {
            return Mono.just(new AuthorizationDecision(false));
        }

        return authentication.map(auth -> {
            boolean admin = auth.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
            boolean owner = username.equals(auth.getName());
            return new AuthorizationDecision(
                trust.isAuthenticated(auth) && (owner || admin));
        }).defaultIfEmpty(new AuthorizationDecision(false));
    };
}
```

This is an **illustrative method**; in Section 7 it is placed inside a complete configuration class with exact imports. `AuthenticationTrustResolverImpl` avoids treating `AnonymousAuthenticationToken` (which can have raw `isAuthenticated()==true`) as a logged-in user; `trust.isAuthenticated(auth)` excludes anonymous. For missing/wrong-type variables or an empty publisher, it returns a deny decision.

**Scope of example:** comparing a URI username and `Authentication.getName()` is only an easy-to-understand pattern. In real systems, usernames can change and `Authentication.getName()` may be an issuer-assigned subject. If a URL contains a numeric order/project ID, ownership checks must rely on trusted ID/tenant mappings and server-side data, not mechanical username string comparisons.

### 5.3 When an ID Variable References a Real Resource: Data-Side Authorization

Another route:

```http
GET /api/orders/892
Authorization: Bearer <alices-token>
```

`892` is merely a client-supplied identifier. Knowing the caller is Alice does not prove order 892 belongs to Alice. A record-level authorization rule is needed:

```text
authenticated user: alice (verified by Security)
requested orderId: 892 (read from URL)
   |
   v
repository/service: which tenant does order 892 belong to?
   |
   +-- Is Alice allowed to view orders in this tenant? -> allow
   +-- No permission? -> deny (403/404 per API policy)
```

You can use a `ReactiveAuthorizationManager` calling a non-blocking R2DBC repository inside `flatMap`; or place the check directly inside the service data query (for example, querying by `id AND owner_id`). The key rule: **never authorize solely by a client-passed ID while skipping server data checks**.

**Reactive pseudocode** (incomplete class/repository, not standalone runnable):

```java
return authentication.flatMap(auth -> {
    if (!trust.isAuthenticated(auth)) {
        return Mono.just(new AuthorizationDecision(false));
    }
    return orderPermissionService.canRead(
            auth.getName(), orderId, tenantId)
        .map(AuthorizationDecision::new)
        .defaultIfEmpty(new AuthorizationDecision(false));
}).defaultIfEmpty(new AuthorizationDecision(false));
```

Validate `orderId`/`tenantId` from trusted sources, bound queries, handle errors, and fail closed. If the implementation accesses synchronous JDBC/JPA, **do not invoke it directly on the event loop**; use a blocking boundary with an appropriate scheduler/concurrency/timeout or switch to a reactive driver. Never put backend errors into `onErrorReturn(true)`.

## 6. Sample Authorization Plan

Design an API with three demo accounts and six request types:

| HTTP method | URL | Who Is Permitted |
|---|---|---|
| GET | `/api/public` | Everyone |
| GET | `/api/admin/metrics` | `ROLE_ADMIN` |
| GET | `/api/accounts/{username}` | The user matching the URL name, or `ROLE_ADMIN` |
| GET | `/api/reports` | `ROLE_READER` |
| POST | `/api/reports` | `ROLE_EDITOR` **and** a CSRF token when the chain applies it |
| Any other method/path | Outside policy | Denied via `anyExchange().denyAll()` |

The order is intentional: public GET, admin GET, owner GET, reports GET, reports POST, fallback. Only GET/POST are listed per actual functionality. The example includes three accounts: Alice and Bob have `ROLE_READER`; Admin has `ROLE_ADMIN`, `ROLE_READER`, and `ROLE_EDITOR`.

Note: calling the same path with a different method will **not** inherit the GET rule. For instance, `POST /api/accounts/alice` might match a future controller handler; with the current fallback, this request is denied.

## 7. Runnable Spring Boot WebFlux Project

This example uses **HTTP Basic** and an in-memory user store with BCrypt passwords; it is solely for local learning/localhost testing. Spring Boot 3.3.13 is an API-illustration version, **not a 2026 production recommendation**. Real projects require patched versions, secure password/IdP management, TLS, and proper CSRF/CORS/observability.

### 7.1 Project Structure

```text
webflux-http-authorization/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/authorization/
    │   ├── AuthorizationApplication.java
    │   ├── SecurityConfiguration.java
    │   └── ApiController.java
    └── test/java/demo/authorization/
        └── AuthorizationPolicyTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-http-authorization'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.authorization'
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
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add `spring-boot-starter-web` since this is a WebFlux example; if another project has both the MVC starter and WebFlux, Boot may select a different web application type. Test dependencies include Spring Security Test to test CSRF in `WebTestClient`.

### 7.2 Application

**src/main/java/demo/authorization/AuthorizationApplication.java**

```java
package demo.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthorizationApplication.class, args);
    }
}
```

### 7.3 Security Configuration — Path, Method, and URI Variables

**src/main/java/demo/authorization/SecurityConfiguration.java**

```java
package demo.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder passwordEncoder) {

        UserDetails alice = User.withUsername("alice")
            .password(passwordEncoder.encode("dev-alice-password"))
            .roles("READER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(passwordEncoder.encode("dev-bob-password"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(passwordEncoder.encode("dev-admin-password"))
            .roles("ADMIN", "READER", "EDITOR")
            .build();

        return new MapReactiveUserDetailsService(alice, bob, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin/metrics")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/accounts/{username}")
                    .access(ownerOrAdmin())
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasRole("READER")
                .pathMatchers(HttpMethod.POST, "/api/reports")
                    .hasRole("EDITOR")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .csrf(Customizer.withDefaults())
            .build();
    }

    private ReactiveAuthorizationManager<AuthorizationContext>
            ownerOrAdmin() {

        AuthenticationTrustResolver trust =
            new AuthenticationTrustResolverImpl();

        return (authentication, context) -> {
            Object value = context.getVariables().get("username");
            if (!(value instanceof String username)) {
                return Mono.just(new AuthorizationDecision(false));
            }

            return authentication
                .map(auth -> {
                    boolean isAdmin = auth.getAuthorities().stream()
                        .anyMatch(a ->
                            "ROLE_ADMIN".equals(a.getAuthority()));
                    boolean ownsPath =
                        username.equals(auth.getName());

                    return new AuthorizationDecision(
                        trust.isAuthenticated(auth)
                            && (ownsPath || isAdmin));
                })
                .defaultIfEmpty(new AuthorizationDecision(false));
        };
    }
}
```

**Reading the code carefully:**

1. `@EnableWebFluxSecurity` enables Spring Security WebFlux configuration; do not use MVC's `@EnableWebSecurity`.
2. `MapReactiveUserDetailsService` is a **development** user store, not a production identity management solution. Passwords are hashed with BCrypt; example data must not be used as real credentials.
3. `GET /api/public` requires no login. Other HTTP methods on `/api/public` are **not** permitted by default.
4. `GET /api/admin/metrics` requires `ROLE_ADMIN`.
5. `GET /api/accounts/{username}` uses `access(ownerOrAdmin())` to compare the URI variable against the authenticated principal or `ADMIN` role. If no principal or valid variable is present, it returns a deny decision.
6. `GET /api/reports` requires `ROLE_READER`. `POST /api/reports` requires `ROLE_EDITOR` **and** a CSRF token per the chain.
7. `anyExchange().denyAll()` denies requests not covered by a rule. It does not by itself define a fixed HTTP status for every failure mode; responses depend on authentication state, CSRF, and exception handling.
8. `httpBasic(withDefaults())` enables Basic login; `formLogin(disable)` prevents HTML redirects in this API demo.
9. `csrf(withDefaults())` keeps CSRF protection enabled. Valid POST tests must include a token; do not assume the `EDITOR` role is enough to bypass CSRF.
10. `ownerOrAdmin()` only uses trusted information from `Authentication` and the variable decoded by the matcher, never trusting an `X-User-Id` header or client-supplied JSON value.

Even though the example protects `/api/accounts/{username}` by the username itself, real-world business rules usually require mapping issuer+subject to an account ID and checking data permissions in the service. **Do not treat a URL username as a complete representation of ownership for every record.**

### 7.4 Illustrative Controller

**src/main/java/demo/authorization/ApiController.java**

```java
package demo.authorization;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/api/admin/metrics")
    public Mono<String> metrics() {
        return Mono.just("admin metrics");
    }

    @GetMapping("/api/accounts/{username}")
    public Mono<String> account(@PathVariable String username) {
        return Mono.just("account:" + username);
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return Mono.just("reports");
    }

    @PostMapping("/api/reports")
    public Mono<String> createReport() {
        return Mono.just("created");
    }
}
```

The controller does not handle authorization itself, because `SecurityWebFilterChain` already decides who can invoke the handler. Even so, in applications with a database, the service must still check **object/tenant** permissions and avoid returning sensitive data outside policy. The demo only returns fixed strings without accessing a real store.

### 7.5 Trying It Out with curl

Requires JDK 17+, a Gradle version compatible with Boot 3.3, and access to download Maven dependencies. From the project directory:

```bash
gradle bootRun
```

If a compatible wrapper is present, use `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). The credentials below are for local use only.

```bash
# Public, no password sent
curl -i http://localhost:8080/api/public

# Not logged in: login required
curl -i -H "Accept: application/json" \
    http://localhost:8080/api/accounts/alice

# Curl will prompt for password in terminal: enter dev-alice-password
curl -i -u alice \
    http://localhost:8080/api/accounts/alice

# As alice, re-enter dev-alice-password: not allowed to read bob's account
curl -i -u alice \
    http://localhost:8080/api/accounts/bob

# As admin, enter dev-admin-password: allowed to read bob's account
curl -i -u admin \
    http://localhost:8080/api/accounts/bob

# Alice has ROLE_READER so GET reports is permitted
curl -i -u alice \
    http://localhost:8080/api/reports

# Without a valid CSRF token: POST will return 403
curl -i -u admin -X POST \
    http://localhost:8080/api/reports
```

When using PowerShell, `curl` may be an alias; use `curl.exe` when needed. Never put passwords into shell history or log files.

| Request | Key Expected Result |
|---|---|
| `GET /api/public` no credentials | `200`, body `public` |
| `GET /api/accounts/alice` no credentials | `401` with Basic |
| `GET /api/accounts/alice` as Alice | `200`, body `account:alice` |
| `GET /api/accounts/bob` as Alice | `403` |
| `GET /api/accounts/bob` as Admin | `200`, body `account:bob` |
| `GET /api/reports` as Alice | `200`, body `reports` |
| `GET /api/admin/metrics` as Alice | `403` |
| `GET /api/admin/metrics` as Admin | `200`, body `admin metrics` |
| `POST /api/reports` as Admin without CSRF | `403` |
| `GET /api/unknown` as Admin | `403` due to `denyAll` fallback |

The statuses shown apply to the example configuration; on a system with a custom entry point, login redirect, exception handler, or CORS, the HTTP response may differ. The POST command above is only to demonstrate CSRF; for POST to succeed, a valid token from the server's CSRF mechanism or the `WebTestClient` test in the next section is required.

## 8. Automated Authorization Testing with WebTestClient

Tests use the mock server inside the Spring Boot application and **real** HTTP Basic against the demo user store, not merely a mocked principal. `spring-security-test` provides `csrf()` for testing state-changing requests. This enables testing 200, 401, 403, and unmatched-path branches without a database.

**src/test/java/demo/authorization/AuthorizationPolicyTest.java**

```java
package demo.authorization;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class AuthorizationPolicyTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicGetDoesNotNeedLogin() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void protectedAccountRejectsUnauthenticatedRequest() {
        client.get().uri("/api/accounts/alice")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void ownerCanReadOwnAccount() {
        client.get().uri("/api/accounts/alice")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("account:alice");
    }

    @Test
    void ownerCannotReadSomeoneElsesAccount() {
        client.get().uri("/api/accounts/bob")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanReadOtherAccount() {
        client.get().uri("/api/accounts/bob")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("account:bob");
    }

    @Test
    void getReportsAndAdminMetricsRequireDifferentRoles() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-password"))
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/admin/metrics")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-password"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/admin/metrics")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void postMethodNeedsEditorAndCsrf() {
        // Editor role without CSRF is still blocked.
        client.post().uri("/api/reports")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isForbidden();

        // Valid CSRF, but Alice lacks ROLE_EDITOR.
        client.mutateWith(csrf())
            .post().uri("/api/reports")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-password"))
            .exchange()
            .expectStatus().isForbidden();

        // Has both ROLE_EDITOR and valid CSRF.
        client.mutateWith(csrf())
            .post().uri("/api/reports")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("created");
    }

    @Test
    void unlistedPathAndMethodAreDenied() {
        client.get().uri("/api/unknown")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isForbidden();

        client.mutateWith(csrf())
            .post().uri("/api/accounts/alice")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongCredentialIsRejected() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("alice", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Run:

```bash
gradle test
```

Expect **9 test methods to PASS** when the project, dependencies, and configuration are compatible, assuming the Spring Security Test CSRF mutator is wired into the `WebTestClient` mock server. Do not claim a build/test passed merely because code is presented: if it fails, inspect the stack trace and actual Spring Boot/Security/Gradle versions.

### Why Are Negative Tests Important?

- No credentials → `401`: protects the authentication requirement.
- Valid credentials but wrong owner/role → `403`: authenticated, but not authorized.
- Right role but missing CSRF → `403`: permissions do not substitute for CSRF.
- URL or method outside policy → `403`: fallback deny is working.
- Admin with the right role or user with matching owner → `200`: avoids overly strict policies breaking functionality.

For routes with database owner/tenant relationships, add cross-tenant tests and attempts to access records belonging to another user; tests comparing a URL username only verify the sample policy and do not replace real BOLA testing.

## 9. Multiple SecurityWebFilterChains and Policy Scope

An application may have one chain for `/api/**` (HTTP Basic, JWT) and one chain for web pages (form login). Distinguish:

| Component | Role |
|---|---|
| `ServerHttpSecurity.securityMatcher(...)` | Determines whether a request **enters this chain** |
| `authorizeExchange().pathMatchers(...)` | Once inside the chain, decides which rule checks permissions |
| `@Order` on chains | Priority of which chain is tried first |
| Fallback chain | Covers requests not matching specific chains so they do not bypass Spring Security |

Example **illustrative configuration snippet**:

```java
@Bean
@Order(0)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(1)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().denyAll())
        .build();
}
```

This code **replaces** part of the Section 7 configuration; do not add these two beans alongside the demo's `securityWebFilterChain`. Requires importing `Order` and `PathPatternParserServerWebExchangeMatcher`; when configuring multiple chains, each chain carries its own authentication/CSRF/authorization policies. An API chain's `securityMatcher` does not automatically permit all `/api/**` URLs, since `authorizeExchange` inside that chain is still needed.

Without a fallback chain, if a URL matches **no chain at all**, that request can pass through without protection from any Spring Security filters in these chains. Therefore, test routes outside both `/api/**` and intended web pages.

## 10. Tricky Cases to Analyze

### 10.1 A Path Variable Is Not Authentication

`GET /api/accounts/{username}` with caller Alice requesting `/api/accounts/bob`. Both URI variables and request bodies/headers are client-controlled; only the identity verified by Spring Security is trustworthy for comparison. Never do this:

```java
// WRONG: self-asserted header as proof of identity
String claimedUser =
    exchange.getRequest().getHeaders().getFirst("X-User");
boolean allow = claimedUser.equals(requestedUsername);
```

This snippet is **insecure**—never use it in a real service. If an API gateway injects an identity header, you must have a trusted-proxy model, mTLS/network boundary, and anti-spoofing policy, never trusting a header sent by an Internet client.

### 10.2 Query Parameters Are Not Equivalent to PathPattern

`GET /api/orders?user=alice` does not have a `{user}` variable just because the query has a parameter named `user`. If clients pass `?tenantId=...`, determine the verified tenant from claims or server-side mapping. Query-based authorization should only be used with clear justification, sufficient custom matchers/tests, and backend object-level authorization.

### 10.3 Request Methods Can Change Through Proxies/Gateways

The server must recognize the final HTTP method accurately. Do not place arbitrary HTTP method override headers inside the trust boundary; if a proxy rewrites routes/methods, test behavior parity between gateway and app. `@GetMapping` does not turn a POST into a GET for `pathMatchers(HttpMethod.GET,...)`.

### 10.4 URL Authorization Does Not Automatically Hide Response Data

Even when `GET /api/accounts/alice` is accessible only by Alice/Admin, a controller might accidentally return the full profile, tokens, or another tenant's records. Use minimal DTOs, filter data in the service/repository, and separate read/write policies.

### 10.5 Authentication Failures, Denials, and Business Errors

When a request fails policy checks, you may see:

- **401 Unauthorized:** missing/invalid credentials and the authentication mechanism prompts to retry (Basic).
- **403 Forbidden:** authenticated principal lacks the role, fails the owner rule, or lacks CSRF.
- **404 Not Found:** controller has no route/record; some APIs return 404 instead of 403 to avoid leaking resource existence, though this must be designed consistently.
- **405 Method Not Allowed:** a handler exists for the path but does not support the method; however, if Security `denyAll` blocks earlier, the caller may receive `403` before WebFlux decides 405.

Do not infer from status alone which security layer executed; inspect security chains, matchers, CSRF, login flow, and controlled logs.

### 10.6 Rules Are Ordered by Source Declaration, Not Path Length

The framework evaluates declaration order rather than automatically sorting rules by "longest path" to prioritize admin routes. If `/api/**.permitAll()` is placed before `/api/admin/**.hasRole(...)`, the broad matcher can win first. Code reviews must verify ordering, and tests must catch overly broad permissions.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using Servlet's `HttpSecurity`/`requestMatchers` | Wrong API stack | Use `ServerHttpSecurity`, `SecurityWebFilterChain`, and `pathMatchers` |
| Placing `/api/**.permitAll()` before admin matchers | Opens sensitive routes | Place specific matchers before broad matchers |
| `authenticated()` on `/accounts/{username}` | User A can read User B's URL | Use a manager/object-level authorization check |
| Omitting `anyExchange()` fallback | New routes may lack protection | Use `denyAll` fallback / explicit policy |
| Using `pathMatchers("/api/articles/**").permitAll()` for GET | Accidentally opens POST/DELETE too | Use the `HttpMethod.GET` overload |
| Thinking a GET policy automatically covers HEAD/OPTIONS | HEAD/preflight may be rejected or handled differently | Enumerate/test real methods and configure CORS properly |
| Calling `hasRole("ROLE_ADMIN")` | Role prefix handled incorrectly | Pass `"ADMIN"` with the default role prefix |
| Comparing `@PathVariable username` against a self-asserted header | Clients can spoof identities | Compare against verified `Authentication` |
| Concatenating path variables into SQL/LDAP strings | Injection and cross-tenant access | Parameterized queries/filter escaping + authorization |
| Using raw `authentication.isAuthenticated()` to filter guests | Anonymous tokens can carry `true` | Use trust resolver / authorization framework |
| Calling `block()` inside a reactive manager | Blocks the event loop or destroys throughput | Return `Mono`; offload blocking backends with bounds |
| Enabling `csrf.disable()` because POST returned 403 | Increases risk with browsers/cookies | Understand CSRF tokens and the threat model |
| Testing only `200` cases | Fails to detect overly broad permissions | Test anonymous, wrong credentials, wrong role, wrong owner |
| Authorizing at URL level without DB authorization | Vulnerable to BOLA/IDOR, cross-tenant leaks | Check owner/tenant on records and actions |
| Splitting into multiple chains without a fallback | URLs may be left unprotected | Add a catch-all chain, test URLs outside matchers |

## 12. Production Implementation Checklist

1. Document all HTTP methods/path patterns, user groups, and corresponding data permissions.
2. Verify the app truly uses WebFlux, which chain applies, and `@Order` when multiple chains exist.
3. Make only genuinely public routes open with `permitAll()`; do not use broader matchers than required.
4. Use `HttpMethod` in matchers when the same URL has different read/write rules; test HEAD/OPTIONS/PATCH/DELETE per the real API.
5. Whenever `{username}` or `{id}` is present, decide whether owner/tenant/ownership checks in the DB are required.
6. In `ReactiveAuthorizationManager`, rely only on trusted authenticated identities, fail closed on missing variables or backend errors, and never perform blocking I/O on the event loop.
7. With OAuth2/JWT, verify signature, issuer, audience, expiration, and authority mapping per configuration; never trust claims before verification.
8. Keep CSRF protection enabled when browsers automatically send cookie credentials, and configure CORS with proper origins/methods/headers; never allow all OPTIONS/POST unconditionally.
9. Design an `anyExchange().denyAll()` fallback and a fallback chain when using multiple chains; review after every new controller.
10. Log policy names/statuses safely (no credentials/tokens), and monitor 401/403s, security exceptions, and traffic anomalies.
11. Test both allow and deny cases: guest, user, admin, wrong role, wrong owner, cross-tenant, wrong method, nonexistent ID, missing CSRF.
12. Never deploy demo passwords or in-memory accounts to production. Keep Spring Security and dependencies updated per security advisories.

## 13. Practice Exercises

1. Keep `GET /api/public` public and add `POST /api/public`; explain why the `denyAll()` fallback blocks the new method unless a rule is added.
2. Replace `.pathMatchers(HttpMethod.GET, "/api/accounts/{username}").access(ownerOrAdmin())` with `authenticated()`, write a test where Alice reads Bob's account, and analyze the bug.
3. Add role `ROLE_SUPPORT` for a user and design a policy allowing access only to accounts belonging to authorized tenants; do not treat a query parameter tenant as sole proof.
4. Try swapping `/api/**.permitAll()` and `/api/admin/**.hasRole("ADMIN")`; prove with a security test why ordering matters.
5. Enable `POST /api/reports` for role `EDITOR` and write tests with and without CSRF. Why is having the right role insufficient when CSRF is enabled?
6. Write a matcher for `DELETE /api/reports/{id}` allowing only `ADMIN`. For a record belonging to another tenant, what additional condition must the service check?
7. Use `AuthorizationContext.getVariables()` to extract `projectId` from `/api/projects/{projectId}/members`; write a manager using a reactive repository to check membership/tenant. Define behavior when no record exists and when the repository errors.
8. Split `/api/**` and `/web/**` into two `SecurityWebFilterChain` beans and add a deny fallback. Test a URL outside both.
9. Create a test suite for HEAD, OPTIONS preflight, trailing slashes, encoded URLs, and URLs resembling sensitive matchers; compare results between Spring Security and WebFlux mapping.
10. Explain why `hasAuthority("SCOPE_orders.read")` only works if the JWT/identity provider is configured to map the scope to that authority.

## Summary

**Reactive HTTP authorization** uses `ServerHttpSecurity.authorizeExchange(...)` to combine three pieces of information: **path pattern**, **HTTP method**, and **authenticated identity/authorities**. A matcher like `/accounts/{username}` can extract variables into `AuthorizationContext.getVariables()`; a `ReactiveAuthorizationManager` uses those variables to produce an `AuthorizationDecision`. Rules are evaluated in declaration order, so specific matchers must precede broad matchers, and you should always consider `anyExchange().denyAll()`. URL-level checks are only one layer of defense: service-layer data/tenant ownership and client-appropriate CSRF/CORS remain mandatory.

## Official Documentation

- Spring Security 6.3 — Authorize ServerHttpRequest (reactive), rule ordering and access managers: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/authorize-http-requests.html
- Spring Security 6.3 — WebFlux Security configuration and multiple `SecurityWebFilterChain`: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Javadoc 6.2.8 — `AuthorizationContext.getVariables()`: https://docs.spring.io/spring-security/site/docs/6.2.8/api/org/springframework/security/web/server/authorization/AuthorizationContext.html
- Javadoc — `AuthenticationTrustResolver.isAuthenticated`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authentication/AuthenticationTrustResolver.html
- Spring Security — Reactive WebTestClient authentication testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security — Reactive CSRF testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Framework — WebFlux annotated controller method arguments: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/controller/ann-methods/arguments.html
