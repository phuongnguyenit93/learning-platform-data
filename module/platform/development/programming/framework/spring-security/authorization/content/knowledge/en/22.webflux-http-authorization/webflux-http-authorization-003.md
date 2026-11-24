# `anyExchange` and Default-Deny Scope in Spring Security WebFlux

## 1. When adding a new API, what protects it?

A Spring WebFlux application has approved endpoints:

```http
GET /public/ping
GET /api/profile
GET /api/reports/monthly
POST /api/reports
```

After a deployment, a developer adds `GET /api/preview`, `GET /api/admin/restricted`, and `GET /internal/diagnostics`. If the filter only uses:

```java
.authorizeExchange(ex -> ex
    .anyExchange().authenticated()
)
```

every route without a narrower policy can be accessed by **any logged-in user**, even before the security team has approved permissions for the new route.

The goal of this topic is to build an **HTTP allowlist**: allow only explicitly reviewed paths and methods; deny everything else by default.

```java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/profile")
        .authenticated()
    .pathMatchers(HttpMethod.GET, "/api/reports/{period}")
        .hasRole("AUDITOR")
    .pathMatchers(HttpMethod.POST, "/api/reports")
        .hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

This is an illustrative DSL snippet, not a standalone class. `anyExchange().denyAll()` is a **catch-all** rule: within the scope of the **SecurityWebFilterChain currently handling the request**, exchanges that did not match an earlier rule are denied even if the caller is an admin.

However, **do not assume** `anyExchange` protects the entire HTTP port without examining `securityMatcher` and multi-chain ordering. That is the main trap this guide addresses.

**Learning outcomes:** determine the scope of `anyExchange`; distinguish `denyAll`/`authenticated`/`permitAll`; write matchers in the proper order; configure multiple `SecurityWebFilterChain`s without leaving gaps; test GET/POST/HEAD, unapproved routes, CSRF, and the fallback chain using **WebTestClient**.

## 2. The WebFlux mechanism: select the chain first, evaluate rules second

Spring Security WebFlux does not use Servlet-style `HttpSecurity` and `SecurityFilterChain`. Core classes:

| WebFlux component | Role |
|---|---|
| `ServerHttpSecurity` | Builder for reactive HTTP security |
| `SecurityWebFilterChain` | A chain of WebFilters protecting exchanges that match the chain |
| `securityMatcher(...)` | Specifies which **chain** a request belongs to |
| `authorizeExchange(...)` | Defines the policy for exchanges **that entered the chain** |
| `pathMatchers(...)` | Matches HTTP path and, if specified, HTTP method |
| `anyExchange()` | The "remaining" rule inside an authorization specification |
| `ReactiveAuthorizationManager` | API for asynchronous reactive authorization checks |
| `WebTestClient` | Tests WebFlux applications and filter chains |
| `ReactiveSecurityContextHolder` | `SecurityContext` inside Reactor Context |

Basic flow:

```text
HTTP Request (ServerWebExchange)
          |
          v
[Select the first SecurityWebFilterChain matching securityMatcher]
          |
          v
[Apply authorizeExchange of the selected chain]
          |
       ┌──┴─────────────────────────┐
       v                            v
specific pathMatchers        anyExchange (remaining)
       |                            |
       v                            v
permitAll / authenticated   denyAll
/ hasRole / access               |
       |                            v
       v                        403 or 401 depending on auth/entrypoint
     ALLOW
       |
       v
  WebFlux handler / reactive service
```

**Both matching tiers** must be verified independently:

1. The chain's `securityMatcher(...)` decides **whether the chain participates**.
2. `pathMatchers(...)` and `anyExchange()` decide **the policy inside the selected chain**.

If no chain matches a request, you cannot assume `anyExchange().denyAll()` in another chain will protect it. You must design a catch-all chain or an unrestricted-scope chain.

### 2.1. A single chain without `securityMatcher`

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers(HttpMethod.GET, "/public/ping")
                .permitAll()
            .anyExchange().denyAll()
        )
        .build();
}
```

This is a **configuration sample** for a single-chain application. Without a dedicated `securityMatcher`, the chain normally matches every request in the web application, so the catch-all applies to the rest of that application.

### 2.2. A chain matching only `/api/**`

```java
@Bean
SecurityWebFilterChain apiOnly(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        )
        .authorizeExchange(ex -> ex
            .anyExchange().denyAll()
        )
        .build();
}
```

This snippet is **not sufficient as the entire security config of an application** if routes exist outside `/api/**`. `GET /internal/diagnostics` is not matched by `apiOnly`. Without a fallback `SecurityWebFilterChain`, that request risks going unprotected by Spring Security.

**Conclusion:** no matter how strict `denyAll` is, it has zero effect on requests that **never enter the chain containing it**.

## 3. Comparing three common catch-all rules

```java
.anyExchange().permitAll()
```

Lets remaining exchanges pass this **authorization decision** without requiring authentication. This is usually unsuitable for backends with sensitive data.

```java
.anyExchange().authenticated()
```

Only requires the caller to be authenticated; any new route can be accessed by every logged-in account. This is **default requiring authentication**, not an **explicit allowlist**.

```java
.anyExchange().denyAll()
```

Grants no access to remaining exchanges, even for admins. Simply adding a controller endpoint does not make that endpoint allowed. Developers must add an explicit rule and a regression test.

| Exchange without a specific matcher | permitAll | authenticated | denyAll |
|---|---|---|---|
| Anonymous GET /api/preview | Passes authorization | Blocked / login required | Blocked |
| User GET /api/preview | Passes | Passes | Blocked |
| Admin GET /api/preview | Passes | Passes | Blocked |
| User POST /api/preview | Passes authorization (CSRF may block separately) | Passes authorization | Blocked |
| New route after deploy | Requires no approval | Open to authenticated users | Closed by default |

**Note:** `permitAll` does not disable CSRF, CORS, security headers, request validation, or routing. Conversely, `denyAll` in a chain does not replace tenant/object-level checks on endpoints that were allowed.

### 3.1. `denyAll` does not mean one fixed status code

For an **authenticated** user, it is typically HTTP **403 Forbidden**. For an **unauthenticated** user, the authentication entry point may produce HTTP **401 Unauthorized** (HTTP Basic/Bearer) or a redirect (form login). Never assert that every `denyAll` returns 403.

## 4. Matcher order: the first matching rule applies

A safe configuration:

```java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/profile")
        .authenticated()
    .pathMatchers(HttpMethod.GET, "/api/reports/{period}")
        .hasRole("AUDITOR")
    .pathMatchers(HttpMethod.POST, "/api/reports")
        .hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

A dangerous configuration:

```java
// Counter-example: broad rule shadows narrow policy.
.authorizeExchange(ex -> ex
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

Once `/api/admin/x` matches `/api/**`, having `hasRole("ADMIN")` below does not **AND** the two rules together; the later rule may never be evaluated. Nor can `anyExchange().denyAll()` revoke access already granted by an earlier matcher.

**Rule:** narrow, sensitive matchers first; broad matchers later; `anyExchange().denyAll()` **at the very end**. Trying to place rules after `anyExchange` may be rejected by the builder as unreachable.

### 4.1. HTTP method is part of the policy

```java
.pathMatchers(HttpMethod.GET, "/api/profile")
    .authenticated()
```

Describes only GET:
- `GET /api/profile` by an authenticated user: may proceed.
- `POST /api/profile`: does not match, falls into deny.
- `DELETE /api/profile`: does not match, falls into deny.
- `HEAD /api/profile`: must be tested separately; do not assume a GET security rule equals a HEAD rule.
- Query `GET /api/profile?debug=true`: the path is still `/api/profile`, so if `debug` reveals sensitive content, check it in the handler/service.

Nested routes are not implicitly opened: `/api/reports/{period}` matches one period segment like `monthly`, and does not cover `/api/reports/monthly/details`.

### 4.2. Role prefix

`hasRole("AUDITOR")` usually corresponds to checking `ROLE_AUDITOR`. `hasAuthority("report:read")` matches the exact authority string. A user with `ROLE_ADMIN` does not automatically have `ROLE_AUDITOR` unless the app configures a suitable role hierarchy.

`anyExchange().denyAll()` has no implicit exception for `ROLE_ADMIN` or `ROLE_SUPER_ADMIN`.

## 5. Multiple chains and a default-deny fallback

With multiple `SecurityWebFilterChain`s, Spring Security evaluates them by `@Order` and picks the **first chain matching** `securityMatcher`. It does **not** intersect policies across all chains.

Recommended design:

```text
Incoming request
   |
   +-- @Order(1) API chain, securityMatcher("/api/**")
   |       |
   |       +-- API role/path rules
   |       +-- anyExchange().denyAll()
   |
   +-- @Order(2) catch-all fallback (no narrow securityMatcher)
           |
           +-- GET /public/ping permitAll()
           +-- anyExchange().denyAll()
```

Meaning:
- `GET /api/reports/monthly` is decided by the API chain.
- `GET /public/ping` does not enter the API chain; it is evaluated by the fallback and permitted.
- `GET /internal/diagnostics` does not enter the API chain; it enters the fallback and is denied.
- If `GET /api/preview` is added without changing policy, the API chain denies it.
- Even Admin cannot reach a route lacking an explicit rule.

**Never place a catch-all `permitAll` at the highest priority**, because it can shadow the API chain entirely. Do not think the fallback chain will "correct" the API chain's outcome: once the API chain is chosen, the fallback is not consulted for that exchange.

## 6. Decision table before coding

| Method + path | Chain | Condition | Expected |
|---|---|---|---|
| GET /public/ping | Fallback | Public | Allow |
| POST /public/ping | Fallback | Unapproved | Deny |
| GET /api/profile | API | Authenticated | Allow if logged in |
| GET /api/reports/monthly | API | ROLE_AUDITOR | Allow for Auditor |
| POST /api/reports | API | ROLE_ADMIN + CSRF when applicable | Allow for Admin |
| GET /api/reports | API | No GET rule | Deny |
| GET /api/reports/monthly/details | API | Nested path has no rule | Deny |
| GET /api/preview | API | Unapproved new route | Deny |
| GET /api/admin/restricted | API | Route name is not an authority | Deny even for Admin |
| GET /internal/diagnostics | Fallback | Not public | Deny |
| GET /public/secret | Fallback | Not public | Deny |
| GET /actuator/health | Fallback | No rule in demo | Deny if same context/chain |

This is a **policy for the demo**, not a mandate to block every health endpoint. If health must be public for load balancer probes, add a **narrow** rule for the exact endpoint and method after reviewing topology and exposed information.

## 7. Sample project: Java 17 + Spring Boot 3.5.6 + Spring Security 6.5.x

The demo includes **two chains**, a WebFlux controller with both permitted and intentionally denied routes, and a **JUnit 5 + WebTestClient** test suite. Include only `spring-boot-starter-webflux` without `spring-boot-starter-web` to preserve the **REACTIVE** web application type.

### 7.1. Directory layout

```text
webflux-default-deny/
  pom.xml
  src/main/java/com/example/webflux/
    WebfluxDefaultDenyApplication.java
    SecurityConfiguration.java
    ApiController.java
  src/test/java/com/example/webflux/
    WebFluxAuthorizationTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>webflux-default-deny</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

### 7.3. Main

**`src/main/java/com/example/webflux/WebfluxDefaultDenyApplication.java`**

```java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxDefaultDenyApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebfluxDefaultDenyApplication.class, args);
    }
}
```

### 7.4. SecurityConfiguration

**`src/main/java/com/example/webflux/SecurityConfiguration.java`**

```java
package com.example.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
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
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**")
            )
            .authorizeExchange(ex -> ex
                .pathMatchers(
                    HttpMethod.GET, "/api/profile"
                ).authenticated()
                .pathMatchers(
                    HttpMethod.GET, "/api/reports/{period}"
                ).hasRole("AUDITOR")
                .pathMatchers(
                    HttpMethod.POST, "/api/reports"
                ).hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        // Do not set securityMatcher: matches the remaining requests.
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(
                    HttpMethod.GET, "/public/ping"
                ).permitAll()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers(
            PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();
        UserDetails auditor = User.withUsername("auditor")
            .password(encoder.encode("auditor-pass"))
            .roles("AUDITOR")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(
            alice, auditor, admin
        );
    }
}
```

**Why is this setup safer than a lone API chain?**

- `apiChain` applies only to `/api/**`, evaluated first at `@Order(1)`.
- Inside the API chain, `anyExchange().denyAll()` denies every unapproved route/method.
- `fallbackChain` has no narrow matcher, so it catches requests outside the API chain.
- The fallback makes only `GET /public/ping` public and denies everything else.
- `httpBasic` only illustrates an authentication mechanism; using JWT/OAuth2 in production requires separate token and scope verification.
- CSRF is **kept at its default**. POST tests supply a valid CSRF token to separate CSRF errors from authorization errors.

`MapReactiveUserDetailsService` holds 3 local demo accounts for running `spring-boot:run`; passwords are encoded with `DelegatingPasswordEncoder`. Never use these accounts in production.

### 7.5. API controller

**`src/main/java/com/example/webflux/ApiController.java`**

```java
package com.example.webflux;

import java.security.Principal;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @PostMapping("/public/ping")
    public Mono<String> pingWrite() {
        return Mono.just("not allowed");
    }

    @GetMapping("/public/secret")
    public Mono<String> publicSecret() {
        return Mono.just("sensitive");
    }

    @GetMapping("/api/profile")
    public Mono<String> profile(Principal principal) {
        return Mono.just("profile:" + principal.getName());
    }

    @GetMapping("/api/profile/extra")
    public Mono<String> profileExtra() {
        return Mono.just("sensitive profile data");
    }

    @GetMapping("/api/reports/{period}")
    public Mono<String> report(
            @PathVariable("period") String period) {
        return Mono.just("report:" + period);
    }

    @GetMapping("/api/reports/{period}/details")
    public Mono<String> details() {
        return Mono.just("not approved");
    }

    @PostMapping("/api/reports")
    public Mono<ResponseEntity<String>> createReport() {
        return Mono.just(ResponseEntity.accepted().body("queued"));
    }

    @GetMapping("/api/preview")
    public Mono<String> preview() {
        return Mono.just("preview not released");
    }

    @GetMapping("/api/admin/restricted")
    public Mono<String> adminRestricted() {
        return Mono.just("restricted admin data");
    }

    @GetMapping("/internal/diagnostics")
    public Mono<String> diagnostics() {
        return Mono.just("internal data");
    }
}
```

The handlers `/api/preview`, `/api/admin/restricted`, and `/internal/diagnostics` **intentionally exist** without allow rules. Getting 403 in tests proves security blocked an existing route, rather than merely returning 404 because no handler existed.

### 7.6. WebTestClient: unit/integration tests for each branch

**`src/test/java/com/example/webflux/WebFluxAuthorizationTest.java`**

```java
package com.example.webflux;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringBootTest
class WebFluxAuthorizationTest {
    @Autowired ApplicationContext context;
    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient as(String username, String role) {
        return client.mutateWith(mockUser(username).roles(role));
    }

    private WebTestClient withCsrf(String username, String role) {
        return as(username, role).mutateWith(csrf());
    }

    @Test
    void anonymousCanPingPublicEndpoint() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void authenticatedCanAlsoPingPublicEndpoint() {
        as("alice", "USER").get().uri("/public/ping")
            .exchange().expectStatus().isOk();
    }

    @Test
    void unauthenticatedProfileIsChallenged() {
        client.get().uri("/api/profile")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserCanReadProfile() {
        as("alice", "USER").get().uri("/api/profile")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("profile:alice");
    }

    @Test
    void auditorMayReadReport() {
        as("auditor", "AUDITOR")
            .get().uri("/api/reports/monthly")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report:monthly");
    }

    @Test
    void userCannotReadAuditorReport() {
        as("alice", "USER")
            .get().uri("/api/reports/monthly")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminDoesNotAutomaticallyHaveAuditorRole() {
        as("admin", "ADMIN")
            .get().uri("/api/reports/monthly")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void nestedReportDoesNotMatchSingleSegmentPattern() {
        as("auditor", "AUDITOR")
            .get().uri("/api/reports/monthly/details")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void extraProfilePathNotWhitelisted() {
        as("admin", "ADMIN")
            .get().uri("/api/profile/extra")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void unreleasedPreviewIsDeniedForAdmin() {
        as("admin", "ADMIN")
            .get().uri("/api/preview")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminNamedPathIsNotAutomaticallyAllowed() {
        as("admin", "ADMIN")
            .get().uri("/api/admin/restricted")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminCanPostReportWithCsrf() {
        withCsrf("admin", "ADMIN")
            .post().uri("/api/reports")
            .exchange().expectStatus().isAccepted()
            .expectBody(String.class).isEqualTo("queued");
    }

    @Test
    void ordinaryUserCannotPostReportWithCsrf() {
        withCsrf("alice", "USER")
            .post().uri("/api/reports")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void auditorCannotPostReportWithCsrf() {
        withCsrf("auditor", "AUDITOR")
            .post().uri("/api/reports")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminWithoutCsrfCannotPost() {
        as("admin", "ADMIN")
            .post().uri("/api/reports")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void getReportCollectionIsNotImplicitlyAllowed() {
        as("admin", "ADMIN")
            .get().uri("/api/reports")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void postProfileRemainsDenied() {
        withCsrf("admin", "ADMIN")
            .post().uri("/api/profile")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void postPublicPingDeniedEvenWithCsrf() {
        withCsrf("alice", "USER")
            .post().uri("/public/ping")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void internalDiagnosticsDeniedByFallback() {
        as("admin", "ADMIN")
            .get().uri("/internal/diagnostics")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void publicSecretIsNotPartOfPublicAllowlist() {
        as("admin", "ADMIN")
            .get().uri("/public/secret")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void unlistedApiPathDenied() {
        as("admin", "ADMIN")
            .get().uri("/api/unknown")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void unlistedNonApiPathDenied() {
        as("admin", "ADMIN")
            .get().uri("/unknown")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void actuatorStylePathDeniedByFallback() {
        as("admin", "ADMIN")
            .get().uri("/actuator/health")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void headDoesNotGetGetMethodPermissionByDefault() {
        as("admin", "ADMIN")
            .head().uri("/api/profile")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void queryParameterDoesNotChangeProfilePathRule() {
        as("alice", "USER")
            .get().uri("/api/profile?view=normal")
            .exchange().expectStatus().isOk();
    }

    @Test
    void auditorReportQueryParameterRemainsAllowed() {
        as("auditor", "AUDITOR")
            .get().uri("/api/reports/monthly?format=text")
            .exchange().expectStatus().isOk();
    }

    @Test
    void postToGetOnlyReportPathDenied() {
        withCsrf("admin", "ADMIN")
            .post().uri("/api/reports/monthly")
            .exchange().expectStatus().isForbidden();
    }
}
```

**Why use this setup?** `WebTestClient.bindToApplicationContext` builds the WebFlux handler/filter chain from the Spring ApplicationContext; `apply(springSecurity())` enables integration test security; `mockUser` creates a mock principal in tests; `csrf()` proves POST requests are blocked or allowed by role **rather than** all returning 403 due to missing CSRF.

These are application-context integration tests, not end-to-end tests of HTTP Basic over TCP, reverse proxies, or JWT cryptographic validation. Production needs additional tests through the real network and gateway configuration.

### 7.7. How to run and expected results

From the directory containing `pom.xml`:

```bash
mvn test
```

The `@Test` methods above are expected to pass according to the described policy. **Maven has not been executed**, so do not present this as an observed measurement. When running in your environment, check the JUnit output and confirm WebFlux reactive startup rather than Servlet MVC.

To run the application:

```bash
mvn spring-boot:run
```

Example GET checks:

```bash
curl -i http://localhost:8080/public/ping
curl -i -u alice:alice-pass http://localhost:8080/api/profile
curl -i -u auditor:auditor-pass \
  http://localhost:8080/api/reports/monthly
curl -i -u admin:admin-pass \
  http://localhost:8080/api/preview
curl -i -u admin:admin-pass \
  http://localhost:8080/internal/diagnostics
```

According to the code, the expected statuses are **200**, **200**, **200**, **403**, and **403** respectively. Do not treat this as an actual executed stdout transcript. For POST with Basic/cookies, a CSRF token must be supplied per the configured mechanism; the `WebTestClient` tests above handle this.

## 8. Boundaries with other controls

### 8.1. `anyExchange` does not replace object-level authorization

A route:

```java
.pathMatchers(HttpMethod.GET, "/api/documents/{id}")
    .authenticated()
```

only requires the user to be logged in to call the route. It does **not** verify which tenant `Document#123` belongs to, or whether the user has READ permission on that document. If `repository.findById(id)` omits the tenant predicate, an **IDOR/BOLA** vulnerability still exists on the permitted route.

For object-level protection:
- Verify the resource ID and canonical tenant server-side from the DB.
- Check membership and owner/share/role against the actual operation.
- Use reactive service-level authorization where appropriate.
- Push tenant/authorization predicates down into repository queries, especially for list, update, and delete.
- Never trust client-provided `tenantId`/`owner` as proof of permission.

### 8.2. Reactive Method Security is an additional layer

For services returning `Mono`/`Flux`, you can enable:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodConfig {
}
```

And declare:

```java
@Service
class ConfidentialService {
    @PreAuthorize("hasRole('AUDITOR')")
    public Mono<String> readInternal() {
        return Mono.just("auditor-only");
    }
}
```

The two snippets above are **illustrative samples, not standalone files**, as they omit imports and wiring. In WebFlux, reactive method security uses Reactor Context; do not assume reading `ThreadLocal SecurityContextHolder` across asynchronous boundaries works reliably.

If `anyExchange().denyAll()` already blocked the request, the method never runs. If the HTTP route was allowed, the service can still enforce `@PreAuthorize` by role/resource. Never use `@PostAuthorize` on a method that performs side effects before denial without accounting for transactions and access control.

### 8.3. CSRF

`CsrfWebFilter` can reject POST/PUT/DELETE before role authorization rules are evaluated. Therefore, tests verifying roles on POST must send a valid CSRF token. Do not blindly call `csrf.disable()` merely because an API returns JSON; evaluate whether credentials can be automatically sent by browsers, such as cookies or Basic authentication.

For a stateless API using only bearer tokens in the `Authorization` header, the CSRF threat model differs, yet the configuration choice must still be grounded in the real authentication mechanism and risks.

### 8.4. CORS, OPTIONS, static resources, and Actuator

A CORS preflight typically uses OPTIONS. Never solve every issue with an unchecked `pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()`. Configure explicit CORS origins/methods/headers, and test both preflight and actual requests.

Likewise:
- Static assets, favicon, login/logout, and callback routes must be reviewed explicitly.
- Actuator health may need to be public for load balancers, but should not be exposed the same way as metrics/env.
- If the management server runs on a **different port or application context**, this chain does not automatically cover that port.
- WebSocket handshakes may pass through HTTP security; per-message authorization requires separate controls.
- Functional routing (`RouterFunction`) can also introduce new routes and must be checked for chain coverage just like annotated controllers.

### 8.5. Proxies, base paths, and encoding

Security matchers run on the request WebFlux receives, which can differ from the external gateway path if a proxy rewrites it. Test:
- Proxy-prefixed/rewritten URLs.
- Trailing slashes, multiple slashes, encoded segments, and path variables.
- Whether query parameters alter sensitive output.
- Less common HTTP methods: HEAD, OPTIONS, PATCH, DELETE.
- New routes introduced by dependencies, management, functional endpoints, or feature flags.

Never roll your own `String.startsWith("/api/admin")` on raw URLs for authorization without proper canonicalization and path parsing controls.

## 9. Advanced case: dynamic authorization in WebFlux

When permissions depend on a resource or tenant and require calling a reactive data source, you can implement `ReactiveAuthorizationManager<AuthorizationContext>` and wire it into the DSL via `access(...)`. Conceptual template:

```java
public final class DocumentAccessManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final ReactiveDocumentPolicy policy;

    public DocumentAccessManager(ReactiveDocumentPolicy policy) {
        this.policy = policy;
    }

    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {
        return authentication
            .flatMap(auth -> policy.allowed(
                auth, context.getExchange()))
            .map(AuthorizationDecision::new)
            .defaultIfEmpty(new AuthorizationDecision(false))
            .onErrorReturn(new AuthorizationDecision(false));
    }
}
```

This is an **API reading template**, not yet part of a runnable project since `ReactiveDocumentPolicy`, imports, and bean configuration are needed. Verify the `ReactiveAuthorizationManager` signature for your version; do not confuse it with the Servlet manager that takes `Supplier<Authentication>`. Goals:
- Never call `block()` on the event loop to query a permissions DB.
- Use a real principal/context and canonical object data.
- Missing decisions or downstream errors must **fail closed** for mandatory security policies.
- Use bounded timeouts, observability, and pre-pagination batching/filtering for large lists.

When a policy only needs to distinguish HTTP methods and roles, `pathMatchers(...).hasRole(...)` is usually simpler and easier to audit than a custom manager.

## 10. How to review security chain changes

Before merging a pull request that adds an endpoint:
1. Identify whether the endpoint uses a WebFlux annotated controller or `RouterFunction`.
2. Find which chain matches the request (including `securityMatcher`, port, and `@Order`).
3. Find the **first matcher** matching that method/path inside that chain.
4. If the route is public, restrict it to the exact path/method and returned data.
5. If the route requires permission, choose the appropriate authority/role or object-level check.
6. Add **allow** tests for valid actors and **deny** tests for anonymous callers, wrong-role actors, and cross-tenant actors.
7. Add tests for unapproved HTTP methods, queries/nested paths, and fallback routes.
8. If CSRF applies, supply a token when testing role checks on unsafe methods.
9. Never remove the fallback catch-all or switch to blanket `authenticated`/`permitAll` to "fix a 403" without review.
10. Test against the real gateway/actuator/management ports when changing topology.

**Self-verification technique:** intentionally define a handler without an allow rule in each chain and confirm authenticated requests still receive 403. The demo includes `/api/preview` (API chain) and `/internal/diagnostics` (fallback chain), proving the catch-all is enforced rather than merely returning 404 for a missing handler.

## 11. Common pitfalls

| Pitfall | Risk | Fix |
|---|---|---|
| `anyExchange().authenticated()` instead of `denyAll` | Any new route may open to all logged-in users | Use an explicit allowlist followed by `denyAll` |
| `/api/** permitAll` before `/api/admin/**` | Broad rule shadows narrow role | Place specific matchers first |
| Only having a `securityMatcher("/api/**")` chain | Routes outside `/api` lack a protecting chain | Add a catch-all fallback |
| Catch-all `permitAll` given highest priority | Narrower chains behind it are never chosen | Review `@Order` and matchers |
| Assuming all chains are combined | Misunderstanding multi-chain behavior | First matching chain wins |
| Treating a GET rule as covering POST/HEAD | Other methods accidentally lack explicit policies | Match methods explicitly, test HEAD/POST |
| Denying GET while leaving POST broadly permitted | Alternate operation exists | Inspect all supported HTTP methods |
| Allowing admin because the route name says `admin` | Route names carry no security semantics | Write an explicit role rule |
| Testing only URLs with no handler | 404 does not prove `denyAll` | Test real handlers that are not yet allowed |
| Making all of `/public/**` public | Can expose `/public/secret` | Permit exact methods/paths only |
| Removing CSRF to make POST tests pass | Can introduce CSRF vulnerabilities | Use `csrf()` in `WebTestClient` |
| Using `HttpSecurity`/`MockMvc` for WebFlux | Wrong security stack | Use `ServerHttpSecurity`/`WebTestClient` |
| Assuming ADMIN implicitly includes AUDITOR | Wrong authority mapping | Configure explicit role hierarchy if needed |
| Checking only route without checking document ID | BOLA/IDOR | Enforce tenant and object-level authorization |
| Leaving the management port without a policy | System endpoints exposed unexpectedly | Verify security per context/port |
| Ignoring proxy path rewrites | Matchers protect a different path than exposed | Run integration tests through the gateway |
| Building a custom reactive policy with `block()` | Blocks event loop, hurts throughput | Use `Mono`/`Flux` and Reactor Context |

## 12. Checklist

- [ ] Using Spring WebFlux / `ServerHttpSecurity` properly, not confused with Servlet.
- [ ] `authorizeExchange` has matchers by path and HTTP method.
- [ ] Specific matchers appear before general matchers.
- [ ] `anyExchange().denyAll()` is placed last in every chain requiring an explicit allowlist.
- [ ] Every `SecurityWebFilterChain`'s `@Order`/`securityMatcher` has been reviewed.
- [ ] A catch-all fallback chain exists for requests not entering specialized chains.
- [ ] Not assuming `anyExchange` protects outside the chain containing it.
- [ ] `permitAll` applies only to exact public endpoints.
- [ ] `authenticated` is not used in a way that accidentally opens all new APIs.
- [ ] Authenticated requests to existing handlers without allow rules are tested.
- [ ] GET/POST/HEAD, roles, queries, nested paths, and unknown paths are tested.
- [ ] 401 for anonymous when entry point requires auth and 403 for insufficient privileges are tested.
- [ ] CSRF/CORS are controlled independently, with no blanket disable.
- [ ] Allowed routes still verify per-object/tenant permissions.
- [ ] Management port, gateway, WebSocket, and background access have dedicated security where needed.
- [ ] Logs/metrics track 401/403 and policy changes without printing secrets.
- [ ] Policy changes require review, negative tests, and a regression suite.

## 13. Self-check questions

**1.** Does `anyExchange().denyAll()` inside a chain matching only `/api/**` block `/internal/diagnostics`?

**Answer:** No. That request is not selected by the API chain. You need a catch-all fallback chain or a chain covering the entire application.

**2.** Is `anyExchange().authenticated()` an "approved-endpoints-only" allowlist?

**Answer:** No. It requires login, but does not distinguish approved routes from unapproved ones.

**3.** Why can `/api/admin/restricted` return 403 even when the caller has `ROLE_ADMIN`?

**Answer:** Because the route lacks an allow rule. `anyExchange().denyAll()` has no exception for admins.

**4.** `GET /api/reports/monthly` grants access to `ROLE_AUDITOR`. Is POST to the same path automatically allowed?

**Answer:** No; the rule is restricted to HTTP GET. POST must have its own rule, otherwise it is denied.

**5.** Why must a CSRF token be sent when testing a POST with the right role?

**Answer:** Without CSRF, the filter can reject the request before authorization is checked. Adding the token ensures the test actually verifies the role/matcher.

**6.** Is opening `GET /api/documents/{id}` to authenticated users enough to protect each tenant's data?

**Answer:** Not yet. You must still check the document's canonical tenant, membership, owner/share, and action permission. `anyExchange` is HTTP-route authorization and does not solve BOLA by itself.

## 14. Official documentation

- [Spring Security 6.5 — Reactive Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `pathMatchers`, `anyExchange`, and authorization decisions.
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): `SecurityWebFilterChain`, `ServerHttpSecurity`, multiple chains, and `@Order`.
- [Spring Security 6.5 — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): Reactor Context, reactive method checks, and `@PreAuthorize`.
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): `bindToApplicationContext`, `springSecurity()`.
- [Spring Security 6.5 — Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): reactive `mockUser()` and `@WithMockUser`.
- [Spring Security 6.5 — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): `csrf()` in `WebTestClient`.

**Remember:** `anyExchange().denyAll()` only blocks remaining exchanges **inside the selected `SecurityWebFilterChain`**. For true default-deny WebFlux protection, combine **narrow method/path matchers**, **correct first-match ordering**, **a fallback chain covering requests outside specialized chains**, **`WebTestClient` negative tests**, and **object-level checks** on allowed routes.