# Configuring Multiple Chains for Distinct API Domains and Verifying Coverage

## 1. Why Do Gateway and Multi-Tenant Systems Need Multiple Security Chains?

A Spring WebFlux application often sits behind an API Gateway and serves multiple domains with different security contracts:
- `/api/admin/**`: administration, using JWT Bearer tokens with `SCOPE_admin.read`.
- `/api/tenant/{tenantId}/items`: multi-tenant API, requiring a JWT with `SCOPE_tenant.read` while verifying the user/service is permitted for the actual tenant.
- `/api/ping`: public read endpoint.
- `/ops/status`: internal operations endpoint, using HTTP Basic **solely to illustrate a different authentication mechanism**.
- `/api/v2/unreviewed` and `/diagnostics/secret`: new or sensitive handlers **not yet approved**, which must be blocked rather than accidentally left public.

With a single security chain, combining JWT, Basic, CORS, CSRF, entry points, and multiple scopes easily becomes a monolith that is hard to review. Spring Security Reactive supports multiple `SecurityWebFilterChain` beans, each with its own `securityMatcher` and `@Order`.

Core risk: **`anyExchange().denyAll()` inside a SecurityWebFilterChain protects only requests matching that specific chain, not every URL in the application by default.** If `securityMatchers` omit a route, requests can reach a handler without passing through any of those chains' security filters.

Therefore, you must verify **two layers**:
1. **Chain selection and coverage:** which chain does a request enter; are there gaps; does a broad chain shadow a narrow one?
2. **In-chain authorization:** was the user authenticated by the right mechanism, and do they hold the required scope/role/tenant/ownership?

This lesson belongs to the **Gateway and Multi-tenancy** group of the Spring Security - reactive module. It provides Java 17+ configurations, coverage matrices, a WebFlux application, `WebTestClient` tests, and a production checklist.

### Learning Outcomes

After this lesson, you will be able to:
1. Explain how `securityMatcher(...)` differs from `authorizeExchange().pathMatchers(...)`.
2. Use `@Order` to place narrow chains before broad chains, following the first-match principle.
3. Design a match-all fallback chain with `denyAll()`.
4. Isolate JWT Admin/Tenant APIs from HTTP Basic Ops.
5. Protect path roots, unapproved methods, new API versions, and URLs after Gateway rewrites.
6. Test at both the **matcher level** and **HTTP level** using `WebTestClient`.
7. Prevent cross-tenant access even when a JWT holds a valid scope.
8. Recognize that mock-token tests do not prove real signatures, issuers, audiences, or JWKS.
9. Prepare end-to-end Gateway, CORS, CSRF, and monitoring verification.

## 2. Distinguishing securityMatcher from authorizeExchange.pathMatchers

### 2.1. securityMatcher decides **which chain** applies

In Reactive:
~~~java
@Bean
@Order(1)
SecurityWebFilterChain admin(ServerHttpSecurity http) {
    return http
            .securityMatcher(ServerWebExchangeMatchers.pathMatchers(
                    "/api/admin", "/api/admin/**"))
            .authorizeExchange(ex -> ex
                    .anyExchange().hasAuthority("SCOPE_admin.read"))
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}
~~~

This is a configuration snippet; complete imports appear in the project below. When a request hits `/api/admin/report`, this `securityMatcher` matches. When a request hits `/api/tenant/acme/items`, it does not match, so Spring Security evaluates subsequent chains.

### 2.2. authorizeExchange decides **permissions inside** the chain

~~~java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/admin/report")
            .hasAuthority("SCOPE_admin.read")
    .anyExchange().denyAll())
~~~

`anyExchange()` here means "all remaining requests **within the already-selected admin chain**." It cannot substitute for a catch-all chain for `/diagnostics/secret` outside `/api/admin/**`.

### 2.3. Chain selection order

Spring Security Reactive uses `WebFilterChainProxy` to iterate through `SecurityWebFilterChain` beans in order. It selects **the first chain whose `matches(exchange)` returns true**. It does not combine the JWT filter of one chain with the Basic filter of another.

~~~text
GET /api/admin/report
       |
       v
@Order(1) /api/admin + /api/admin/** -> MATCH -> ADMIN JWT
       |
       X Subsequent chains do not run:
@Order(2) /api + /api/**            -> would also match by path
@Order(3) /ops + /ops/**
@Order(99) match-all fallback
~~~

For `GET /api/tenant/acme/items`, the admin matcher does not match, and the general API matcher matches. For `GET /diagnostics/secret`, the first three matchers do not match; the catch-all receives the request and applies `denyAll`.

**Note:** first-match follows `@Order` (lower numbers take precedence); it is not determined by source-code order, URL length, or rule "strictness."

### 2.4. Two dangerous mistakes

**Mistake 1 — broad chain placed before narrow chain:**

~~~java
// ANTI-PATTERN: do not use this ordering.
@Order(1) // broad chain captures /api/admin/** too
SecurityWebFilterChain api(...) {
    return http.securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**"))
            .authorizeExchange(ex ->
                    ex.anyExchange().authenticated())
            .build();
}

@Order(2) // admin chain never runs for /api/admin/report
SecurityWebFilterChain admin(...) {
    return http.securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/admin/**"))
            .authorizeExchange(ex ->
                    ex.anyExchange().hasAuthority("SCOPE_admin.read"))
            .build();
}
~~~

A regular user token could access admin endpoints if the broad chain only checks `authenticated()` and lacks other domain controls.

**Mistake 2 — missing catch-all:**

~~~text
Configured: admin matcher /api/admin/**, API matcher /api/**, ops /ops/**
Existing controller: GET /diagnostics/secret
Without fallback: no chain matches /diagnostics/secret
Potential result: controller may run without these security filters
~~~

Never assume Spring Boot automatically adds an app-wide security chain once your application defines custom `SecurityWebFilterChain` beans.

## 3. Designing Coverage Across Paths, Methods, Auth Schemes, and Tenants

Before writing code, define a security contract matrix:

| Sample Request | Selected Chain | Authentication | Permission | Expected |
| --- | --- | --- | --- | --- |
| GET `/api/admin/report` | Admin @Order 1 | Bearer JWT | admin.read | 200 with sufficient scope |
| GET `/api/admin/report` with tenant.read token | Admin @Order 1 | Valid JWT | Missing admin.read | 403 |
| GET `/api/admin` | Admin @Order 1 | Bearer JWT | admin.read | 200 if route exists |
| GET `/api/tenant/acme/items` | API @Order 2 | Bearer JWT | tenant.read + tenant match | 200 |
| GET `/api/tenant/beta/items`, acme tenant JWT | API @Order 2 | Bearer JWT | tenant mismatch | 403 |
| GET `/api/ping` | API @Order 2 | Anonymous | permitAll | 200 |
| GET `/api/ping` with invalid Bearer | API @Order 2 | Invalid JWT | Authentication failure | 401 |
| POST `/api/ping` | API @Order 2 | JWT | No POST rule | 403 |
| GET `/ops/status` | Ops @Order 3 | Basic | ROLE_OPS | 200 |
| GET `/ops/status` with Bearer | Ops @Order 3 | Not Basic | ROLE_OPS | 401 |
| GET `/api/admin/report` with Basic | Admin @Order 1 | Not Bearer | admin.read | 401 |
| GET `/api/v2/unreviewed` | API @Order 2 | JWT | Unreviewed denyAll | 403 |
| GET `/diagnostics/secret` | Fallback @Order 99 | — | denyAll | 4xx, never 200 |
| GET `/api-admin/report` | Fallback @Order 99 | — | denyAll | 4xx |
| GET `/api` | API @Order 2 | JWT | No allow rule | 403 |
| GET `/api/tenant/acme/items` without token | API @Order 2 | Missing Bearer | tenant.read | 401 |

Include external host, internal path after proxy rewrite, audience, issuer, owner, expected 401/403/200, and test case ID columns in your real manifest. **Do not list only public URLs**: unreviewed routes, roots, and unexpected HTTP methods must also be tested.

## 4. Separating Chain Coverage, Route Authorization, and Domain Ownership

Three complementary layers:

1. **Chain selection:** `ServerWebExchangeMatcher` determines which filters run: JWT, Basic, CSRF, CORS, headers, and error entry points.
2. **Route authorization:** `authorizeExchange` enforces scopes/roles per HTTP method/path or `denyAll`.
3. **Domain authorization:** services check tenant membership and permissions on specific resources. Path `/api/tenant/beta/items` never grants a carrier of an `acme` tenant JWT access to tenant beta.

Example:

~~~text
JWT signature valid, aud=multi-tenant-api, scope=tenant.read,
tenant_id=acme
        |
        v
GET /api/tenant/beta/items
        |
        +-- Select API chain: PASS
        +-- JWT verified: PASS
        +-- SCOPE_tenant.read: PASS
        +-- tenant acme == requested beta: FAIL -> 403
~~~

In a real system, the `tenant_id` claim can serve as lookup input, but **in-tenant permissions** must still rely on trusted entitlements and ownership policies. Never use email domains, hostnames, `X-Tenant`, or caller-supplied query parameters to grant roles.

## 5. Java 17 + Spring Boot 3.5 Project Structure

We build a WebFlux project with **4 SecurityWebFilterChains**:
- Narrow Admin before general API.
- General API covering `/api/**`.
- Ops isolated with HTTP Basic.
- Fallback matching all remaining URLs with `denyAll`.

Project:

~~~text
webflux-multi-chain-coverage/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── MultiChainHttpTest.java
        └── ChainCoverageTest.java
~~~

**Transparent limitation:** `application.yml` uses illustrative issuer/JWKS hostnames with no real IdP. `WebTestClient` HTTP tests mock `ReactiveJwtDecoder`; they test filter chains, matchers, and authorization, **without verifying real RSA signatures/issuers/audiences**. Integration tests with a JWKS server and signed tokens are required before production.

### 5.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-multi-chain-coverage'
~~~

### 5.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Resource Server starter is required for JWT Bearer APIs; OAuth2 Login client is not needed. Choose a Boot/Spring Security line supported by your organization with appropriate security patches applied.

### 5.3. application.yml

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: webflux-multi-chain-coverage
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - multi-tenant-api
~~~

- `issuer-uri`: issuer that token `iss` must match.
- `jwk-set-uri`: trusted public keys to verify JWS signatures.
- `audiences`: resource server requires tokens intended for `multi-tenant-api`.

**Placeholder hostnames cannot authenticate production traffic.** In real deployments, configure the Authorization Server's HTTPS issuer/JWKS, an algorithm allowlist, key rotation, and a valid access-token profile. Mock decoder tests do not verify these conditions.

### 5.4. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

## 6. SecurityConfig.java — Complete Multi-SecurityWebFilterChain Configuration

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain adminApi(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers(
                                "/api/admin", "/api/admin/**"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                // Bearer-only, no browser session login.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/api/admin", "/api/admin/report")
                                .hasAuthority("SCOPE_admin.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain generalApi(ServerHttpSecurity http) {
        return http
                // /api/** also covers admin paths, but @Order(1) runs first.
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers(
                                "/api", "/api/**"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/api/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/tenant/*/items")
                                .hasAuthority("SCOPE_tenant.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain opsApi(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers(
                                "/ops", "/ops/**"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                // Keep default CSRF for Basic; Ops demo exposes GET only.
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/ops/status")
                                .hasRole("OPS")
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(99)
    SecurityWebFilterChain catchAllDeny(ServerHttpSecurity http) {
        return http
                // Unrestricted securityMatcher: matches remaining requests.
                .authorizeExchange(ex -> ex
                        .anyExchange().denyAll())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    ReactiveUserDetailsService demoOpsUsers() {
        UserDetails operator = User.withUsername("operator")
                // Local demo ONLY; never deploy {noop} passwords.
                .password("{noop}local-demo-only")
                .roles("OPS")
                .build();
        return new MapReactiveUserDetailsService(operator);
    }
}
~~~

### 6.1. Analyzing Each Chain

**Admin @Order(1):** matcher accepts `/api/admin` and all subpaths. It allows only GET on the root and report with `SCOPE_admin.read`. A JWT having only `tenant.read` receives 403. Basic auth from Ops does not work in the Admin JWT chain.

**General API @Order(2):** matcher accepts `/api` and subpaths **not already matched by the admin chain**. `GET /api/ping` is public; `GET /api/tenant/*/items` requires `tenant.read`; all other routes/methods hit `denyAll`. Because this chain is broad, newly added `/api/v2/new` routes will not accidentally become public.

**Ops @Order(3):** matcher accepts only `/ops` and `/ops/**`, using Basic + role OPS. Keeps default CSRF; only GET is allowed. Production requires TLS, network isolation, and strong credentials/identity providers; demo `{noop}` is strictly for study and never for production.

**Catch-all @Order(99):** has no restricting `securityMatcher`, so it matches every URL not claimed by an earlier chain. Denies everything, even real controllers outside `/api/**` and `/ops/**`. Never replace with `permitAll()`.

### 6.2. Why separate CSRF handling?

For JWT APIs accepting only client-sent Bearer Authorization headers (with no ambient cookies or browser-cached Basic credentials), `csrf(...disable)` can make sense under that threat model. With browser-cached HTTP Basic or OIDC Login/WebSession, CSRF risks exist because browsers automatically attach credentials. Never disable CSRF across every chain merely because an API Gateway sits in front.

### 6.3. Never expose "role OPS" on the Admin API

Configuring a Basic Ops chain must not grant the Basic operator admin access. Both `securityMatcher` and authentication mechanisms must stay separated. `hasRole("OPS")` in Ops checks `ROLE_OPS` by default, whereas the JWT APIs require `SCOPE_admin.read`/`SCOPE_tenant.read`. These authorities are not interchangeable.

## 7. ApiController.java — Including Handlers Intentionally Meant to Be Blocked

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/admin")
    public Mono<String> adminRoot() {
        return Mono.just("admin-root");
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> adminReport(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
                "result", "admin-report",
                "subject", jwt.getSubject()));
    }

    @GetMapping("/api/tenant/{tenantId}/items")
    public Mono<Map<String, Object>> tenantItems(
            @PathVariable String tenantId,
            @AuthenticationPrincipal Jwt jwt) {

        String authenticatedTenant =
                jwt.getClaimAsString("tenant_id");

        if (!tenantId.equals(authenticatedTenant)) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN,
                    "Principal not authorized for this tenant"));
        }

        // Demo only; production must verify object ownership in service/repo.
        return Mono.just(Map.of(
                "tenant", tenantId,
                "subject", jwt.getSubject(),
                "items", List.of("BOOK", "PEN")));
    }

    @GetMapping("/ops/status")
    public Mono<String> opsStatus() {
        return Mono.just("UP");
    }

    // These handlers EXIST intentionally to test fail-closed coverage.
    @GetMapping("/api/v2/unreviewed")
    public Mono<String> unreviewedApi() {
        return Mono.just("SHOULD_NOT_BE_EXPOSED");
    }

    @GetMapping("/diagnostics/secret")
    public Mono<String> diagnosticsSecret() {
        return Mono.just("SHOULD_NOT_BE_EXPOSED");
    }

    @GetMapping("/api")
    public Mono<String> apiRoot() {
        return Mono.just("SHOULD_NOT_BE_EXPOSED");
    }
}
~~~

**Why include "SHOULD_NOT_BE_EXPOSED" handlers?** A path with no controller returns 404 even without security; testing 404 proves nothing about coverage. With a real handler mapped, if the fallback is removed or switched to `permitAll`, requests will return 200 and tests will catch the regression.

### 7.1. The tenant check is in the right direction, not yet a complete policy

`tenant_id` in a JWT is trustworthy only after signature/issuer/audience/timestamp validation. The demo compares it against the path variable to illustrate **post-route-scope authorization**. In a real application:
- A principal may belong to multiple tenants, requiring membership/entitlement lookups.
- Data queries must be scoped by tenant and object owner.
- Clients must never be allowed to pick an unauthorized tenant via `X-Tenant`, query parameters, or spoofed hostnames.
- Never grant roles based on email domain.
- 403 and 404 are options for hiding object existence depending on the API contract.
- Check tenant at the service/data layer; never mistake a route matcher for tenant isolation.

## 8. MultiChainHttpTest.java — Verifying Real HTTP Behavior Through WebFilters

The tests use `WebTestClient.bindToApplicationContext(context).apply(springSecurity())`, issuing GET/POST requests with Authorization headers. The `ReactiveJwtDecoder` bean is mocked using Spring Framework Test 6.2+/Spring Boot 3.5's `@MockitoBean` strictly inside the test context.

Because tokens like `admin-token` are arbitrary strings rather than signed JWTs, these tests verify **Bearer extraction → mocked decoder → authorities → chain-specific authorization**, not real signatures/JWKS.

`src/test/java/demo/MultiChainHttpTest.java`:

~~~java
package demo;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class MultiChainHttpTest {

    @Autowired
    ApplicationContext context;

    @MockitoBean
    ReactiveJwtDecoder decoder;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();

        when(decoder.decode("admin-token"))
                .thenReturn(Mono.just(jwt(
                        "admin-token", "admin.read", "acme")));
        when(decoder.decode("tenant-token"))
                .thenReturn(Mono.just(jwt(
                        "tenant-token", "tenant.read", "acme")));
        when(decoder.decode("other-token"))
                .thenReturn(Mono.just(jwt(
                        "other-token", "profile", "beta")));
        when(decoder.decode("bad-token"))
                .thenReturn(Mono.error(
                        new BadJwtException("invalid test token")));
    }

    private Jwt jwt(String value, String scope, String tenant) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .claim("iss", "https://idp.example.test/issuer")
                .claim("sub", "user-42")
                .claim("aud", List.of("multi-tenant-api"))
                .claim("scope", scope)
                .claim("tenant_id", tenant)
                .issuedAt(now.minusSeconds(30))
                .expiresAt(now.plusSeconds(600))
                .build();
    }

    @Test
    void publicPingIs200() {
        client.get().uri("/api/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void badBearerOnPublicPingStillGets401() {
        client.get().uri("/api/ping")
                .headers(h -> h.setBearerAuth("bad-token"))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void adminWithoutBearerIs401() {
        client.get().uri("/api/admin/report")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void tenantScopeCannotEnterAdminChain() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBearerAuth("tenant-token"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminScopeCanReadAdminReport() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBearerAuth("admin-token"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.result")
                .isEqualTo("admin-report");
    }

    @Test
    void adminRootCannotBypassAdminChain() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBearerAuth("admin-token"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-root");
    }

    @Test
    void tenantApiWithoutBearerIs401() {
        client.get().uri("/api/tenant/acme/items")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void validTenantScopeCanReadSameTenant() {
        client.get().uri("/api/tenant/acme/items")
                .headers(h -> h.setBearerAuth("tenant-token"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.tenant").isEqualTo("acme");
    }

    @Test
    void validTenantScopeCannotReadOtherTenant() {
        client.get().uri("/api/tenant/beta/items")
                .headers(h -> h.setBearerAuth("tenant-token"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminScopeAloneDoesNotGrantTenantScope() {
        client.get().uri("/api/tenant/acme/items")
                .headers(h -> h.setBearerAuth("admin-token"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void basicCannotEnterJwtAdminChain() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth(
                        "operator", "local-demo-only"))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void opsWithoutBasicIs401() {
        client.get().uri("/ops/status")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void correctBasicCanAccessOps() {
        client.get().uri("/ops/status")
                .headers(h -> h.setBasicAuth(
                        "operator", "local-demo-only"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("UP");
    }

    @Test
    void wrongBasicPasswordGets401() {
        client.get().uri("/ops/status")
                .headers(h -> h.setBasicAuth(
                        "operator", "wrong"))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void bearerCannotEnterBasicOpsChain() {
        client.get().uri("/ops/status")
                .headers(h -> h.setBearerAuth("admin-token"))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void mappedButUnreviewedApiIsDenied() {
        client.get().uri("/api/v2/unreviewed")
                .headers(h -> h.setBearerAuth("tenant-token"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void apiRootIsDeniedWithJwt() {
        client.get().uri("/api")
                .headers(h -> h.setBearerAuth("admin-token"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void postToPublicGetEndpointIsDenied() {
        client.post().uri("/api/ping")
                .headers(h -> h.setBearerAuth("tenant-token"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("body")
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void catchAllBlocksRealDiagnosticsHandler() {
        client.get().uri("/diagnostics/secret")
                .exchange().expectStatus().is4xxClientError();
    }
}
~~~

The code above has **19 `@Test` methods**. Key test cases:
- `tenant.read` Bearer token is rejected on the Admin chain.
- A JWT with valid scope yet mismatched tenant claim still receives 403.
- Basic does not open JWT APIs, and Bearer does not open Basic Ops.
- A new handler under `/api/**` without an allow rule is still rejected with 403.
- A handler outside matched prefixes hits the fallback and never returns 200.
- `permitAll` does not remove the authentication filter: a bad Bearer token on a public API path can still return 401.

**All JWT tests here use a mocked decoder.** You cannot pass `tenant-token` at app runtime and claim Spring Security verified a real signature.

## 9. ChainCoverageTest.java — Verifying First-Match Order and Coverage

HTTP tests can return 403 from the **wrong** chain's `denyAll`, so status codes alone do not prove which chain was selected. The second test suite directly verifies `SecurityWebFilterChain.matches(ServerWebExchange)`.

Note the API return types:
- `SecurityWebFilterChain.matches(exchange)` returns `Mono<Boolean>`.
- `ServerWebExchangeMatcher.matches(exchange)` returns `Mono<MatchResult>`.

Do not confuse these return types. Inside a JUnit test, calling `block(Duration)` to await the matcher Mono outside a request event loop is acceptable; **never call `block()` in production WebFlux handlers or filters**.

`src/test/java/demo/ChainCoverageTest.java`:

~~~java
package demo;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.server.ServerWebExchange;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ChainCoverageTest {

    @Autowired
    List<SecurityWebFilterChain> chainsByOrder;

    private int firstMatch(String path) {
        ServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get(path).build());

        for (int i = 0; i < chainsByOrder.size(); i++) {
            Boolean match = chainsByOrder.get(i)
                    .matches(exchange)
                    .block(Duration.ofSeconds(2));
            if (Boolean.TRUE.equals(match)) {
                return i;
            }
        }
        return -1;
    }

    @Test
    void exactlyFourChainsAreRegistered() {
        assertEquals(4, chainsByOrder.size());
    }

    @Test
    void adminPathUsesFirstChain() {
        assertEquals(0, firstMatch("/api/admin"));
        assertEquals(0, firstMatch("/api/admin/report"));
    }

    @Test
    void normalApiPathsUseSecondChain() {
        assertEquals(1, firstMatch("/api"));
        assertEquals(1, firstMatch("/api/ping"));
        assertEquals(1, firstMatch("/api/tenant/acme/items"));
        assertEquals(1, firstMatch("/api/v2/unreviewed"));
    }

    @Test
    void opsPathUsesThirdChain() {
        assertEquals(2, firstMatch("/ops"));
        assertEquals(2, firstMatch("/ops/status"));
    }

    @Test
    void pathsOutsideKnownFamiliesUseFallback() {
        assertEquals(3, firstMatch("/diagnostics/secret"));
        assertEquals(3, firstMatch("/api-admin/report"));
        assertEquals(3, firstMatch("/unlisted"));
    }

    @Test
    void everyRepresentativeRequestHasSomeChain() {
        for (String path : List.of(
                "/api/admin/report",
                "/api/tenant/acme/items",
                "/api/ping",
                "/ops/status",
                "/api/v2/unreviewed",
                "/diagnostics/secret",
                "/unlisted")) {
            assertTrue(firstMatch(path) >= 0, path);
        }
    }
}
~~~

These are **6 additional tests**. The sample project totals **25 `@Test` methods** (19 + 6). `exactlyFourChainsAreRegistered` enforces code review whenever someone adds or removes a chain; first-match tests catch reversed admin/general ordering; fallback tests catch uncovered paths.

**Do not treat a test list of 7–10 URLs as mathematical proof for every byte-level URL encoding.** Add methods, paths, hosts, and Gateway E2E coverage for real projects.

## 10. Running the Project and Observing HTTP

In the project directory:

~~~bash
gradle test
gradle bootRun
~~~

If using the Gradle Wrapper, run `./gradlew test` on Linux/macOS or `gradlew.bat test` on Windows. **There is no claim that Gradle was executed in the environment where this lesson was authored.** Expected result: 25 test methods verifying security routing, permissions, and representative coverage; compile/runtime execution must still be confirmed by the learner.

Public API:

~~~bash
curl -i http://localhost:8080/api/ping
~~~

Expect **200 OK**, body:

~~~text
pong
~~~

Ops Basic unauthenticated:

~~~bash
curl -i http://localhost:8080/ops/status
~~~

Expect **401 Unauthorized** with Spring Security's Basic challenge.

Ops Basic with **demo-only credentials**:

~~~bash
curl -i -u operator:local-demo-only \
  http://localhost:8080/ops/status
~~~

Expect HTTP **200**, body:

~~~text
UP
~~~

Admin without Bearer:

~~~bash
curl -i http://localhost:8080/api/admin/report
~~~

Expect **401 Unauthorized** with a Bearer challenge.

~~~bash
curl -i http://localhost:8080/diagnostics/secret
~~~

Expect **4xx**, never returning `SHOULD_NOT_BE_EXPOSED`. This is a real handler proving the catch-all works.

### 10.1. JWT runtime requires a real issuer/JWKS

`application.yml` uses illustrative hostnames, so no real access token is supplied. Do not send `Authorization: Bearer tenant-token` expecting 200—that token string is accepted only by the test mock decoder.

In staging, configure a trusted issuer/JWKS, obtain an access token with `aud=multi-tenant-api` and the right scope, then call:

~~~bash
curl -i https://api-staging.example.test/api/tenant/acme/items \
  -H 'Authorization: Bearer <valid-staging-access-token>'
~~~

This is an example command; no real credential is included. Never store production Bearer tokens in logs, tickets, or source control.

## 11. CORS, CSRF, and Distinct Authentication Mechanisms

### 11.1. CSRF is not the same as API authentication

In the demo:
- Admin/General JWT chains accept only client-sent Bearer headers, so disabling CSRF aligns with the **no ambient browser credentials** assumption.
- The Ops Basic chain keeps default CSRF; browser-cached Basic credentials can create CSRF risks if unsafe methods are added.
- The catch-all chain only denies and does not need CSRF disabled.

If an application mixes OAuth2 Login/WebSession/cookies with a JWT Resource Server, threat-model each chain separately. Never apply a blanket global `csrf(disable)`.

### 11.2. CORS preflight carries no JWT

Browser SPAs calling cross-origin APIs typically send:

~~~http
OPTIONS /api/tenant/acme/items HTTP/1.1
Origin: https://frontend.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight requests usually **do not** carry an access token. Configure WebFlux CORS before auth per documentation, allowlist origins/methods/headers, and verify that actual GET requests still validate JWTs. Never use `permitAll OPTIONS /**` as a substitute for a CORS policy; nor does CORS block curl or non-browser clients.

### 11.3. permitAll can still run authentication filters

`GET /api/ping` has `permitAll()`, so anonymous requests return 200. However, if a client sends `Authorization: Bearer bad-token`, the general chain's JWT filter may fail authentication and return 401 before the authorization decision. A public route inside a JWT chain **does not mean security filters are skipped completely**.

If a product must skip Bearer parsing for a specific public endpoint, consider an early-matched public-only chain with a very narrow scope, checking methods and keeping a catch-all; never widen a public matcher across other routes.

## 12. Multi-tenancy: Chain Selectors Are Not Tenant Selectors

One `/api/**` chain usually suffices for many tenants sharing the same JWT mechanism. There is no need to create thousands of `SecurityWebFilterChain` beans—one per tenant. Identity and authorization can still enforce:
- Issuer/audience/algorithm/key policies.
- Scopes/roles.
- Multi-tenant entitlements.
- Resource ownership.
- Database scoping.
- Per-tenant rate limits/quotas and auditing.

When each tenant has its own issuer/JWKS, Spring Security Reactive provides `JwtIssuerReactiveAuthenticationManagerResolver` to handle multiple trusted issuers. **Never dynamically load JWKS from an arbitrary issuer URL inside an unverified JWT or from an `X-Tenant` header.** Trust only the issuer allowlist and validate API-specific audiences.

If Admin and Tenant are two logically independent resource servers, use distinct audiences such as `admin-api` and `tenant-api` with separate validators/decoders. The sample project uses one audience `multi-tenant-api` to focus on chain coverage; that does not mean all production domains should share an audience or that admin tokens hold tenant rights.

### 12.1. The Gateway can rewrite URLs

Example:

~~~text
https://admin.example.test/reports
          -> gateway -> /api/admin/report

https://tenant.example.test/acme/items
          -> gateway -> /api/tenant/acme/items
~~~

Security matchers inside the application typically inspect the path **after rewriting**, not necessarily the original external URL. If the Gateway alters path normalization, tenantId, route prefixes, forwarded hosts, or HTTP methods, direct `WebTestClient` tests alone cannot prove edge policies are accurate.

Never trust caller-supplied `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, or `X-Tenant` as roles. Derive identity/tenant from verified credentials and application policies.

## 13. URL Boundaries: Roots, Prefixes, Case, and Encoding

Variants to review and test in production:
- `/api/admin` vs. `/api/admin/`.
- `/api` vs. `/api/`.
- `/api-admin/report`: **distinct** from the `/api/**` prefix.
- `/api//admin/report`: double slash/normalization.
- `/api/%61dmin/report`: encoded characters.
- `/API/admin/report`: case sensitivity.
- Semicolons/path parameters.
- HTTP methods: GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE.
- Gateway path rewrites, `contextPath`, forwarded host.
- Functional routes, GraphQL/WebSocket/management ports outside annotated controllers.

Use `ServerWebExchangeMatchers.pathMatchers(...)` or `PathPatternParserServerWebExchangeMatcher`; never hand-roll `request.getPath().toString().startsWith("/api")` and guess prefix boundaries. Keep `ServerWebExchangeFirewall` enabled and test these variants through the real gateway; some URLs will be rejected with 400 by the firewall, while others may normalize differently.

**Never disable the firewall to "fix" an encoded-path test**, as doing so can open bypasses across inconsistent URI-parsing layers.

## 14. HTTP Status Codes Alone Do Not Prove the Right Chain Ran

| Result | Could Mean | Must Also Verify |
|---|---|---|
| 200 | Handler ran and succeeded | Right chain, right scope, tenant/ownership? |
| 401 | Missing/invalid authentication | JWT Bearer vs. Basic challenge, decoder/issuer |
| 403 | Insufficient permission, denyAll, or CSRF | Did the intended chain match; which permission failed? |
| 404 | Handler absent or hiding existence | **Does not prove security coverage** |
| 405 | HTTP method has no handler | Did any security filter run beforehand? |
| 400 | Malformed request or firewall rejection | URI encoding/normalization/network |
| TLS failure | Never reached HTTP request | Gateway/client certificates/transport |

A 403 response could come from the **generic fallback `denyAll`**, even when you expected the Admin chain. Therefore, testing `firstMatch(...)` is mandatory for sensitive systems, and HTTP tests must pair positive and negative rules to verify real enforcement.

### 14.1. Signals of the wrong auth scheme

- Admin Bearer API missing a token typically returns `WWW-Authenticate: Bearer`.
- Ops Basic missing credentials typically returns `WWW-Authenticate: Basic`.

If an Admin route without a token returns a Basic challenge, investigate `securityMatcher`/`@Order` and gateway rewrites before changing controllers. Headers alone also do not prove full tenant/object authorization.

## 15. Common Mistakes

| Mistake | Impact | Prevention |
| --- | --- | --- |
| Generic `/api/**` chain before `/api/admin/**` | Admin policy never runs | Put narrow matchers first |
| Assuming `anyExchange().denyAll()` covers the whole app | Routes outside matchers lack filters | Final catch-all chain |
| Missing match-all fallback | New routes may be public | Catch-all `denyAll`, test real sentinel handler |
| Catch-all `permitAll` | Every route outside prefixes is exposed | Fallback `denyAll` |
| Two chains without clear `@Order` | Unpredictable priority | Explicit priorities, order tests |
| Testing only 403 for admin | Generic `denyAll` also returns 403 | Test first-match directly |
| Testing only URLs with no controller | 404 does not prove security | Mapped sentinel endpoints |
| Not testing `/api` root | Root path may behave differently | Root matchers + negative tests |
| Not testing POST/OPTIONS | Other methods exposed or SPA broken | Method tests + CORS config |
| Tenant derived solely from path | Cross-tenant data leakage | Verified identity + ownership |
| Trusting `X-Tenant`/Host from request | Caller tenant impersonation | Trusted claims/membership |
| Accepting wrong-`aud` JWTs | Tokens from other APIs accepted | Issuer/audience validators |
| Using ID token as access token | Token substitution | Resource-server access tokens |
| Applying Basic auth across all APIs | Ops credentials over-privileged | Separate auth mechanisms per chain |
| Disabling CSRF for browser cookies/Basic | CSRF vulnerability | Policy per credential type |
| Manually parsing JWT payload into roles | Privilege escalation | `ReactiveJwtDecoder` + validators |
| Skipping Gateway E2E tests | Rewrites alter matcher input | Test external→internal routes |
| Treating `mockJwt` as signature proof | Validation left untested | Signed JWT/JWKS integration |
| Calling `block()` on event loop | Blocks reactive pipeline | `Mono`/`Flux` and Reactor context |

## 16. Troubleshooting in Gateway and Multi-Tenant Systems

### 16.1. Admin route returns 200 for a `tenant.read`-only token

Check:
1. Does `adminApi` have higher priority than `generalApi`?
2. Is the admin path after proxy rewrite still `/api/admin/report`?
3. Does the general chain set overly broad `authenticated()`?
4. Does the test JWT accidentally carry both `admin.read` and `tenant.read`?
5. Is a custom `ReactiveAuthorizationManager` permitting from an untrusted source?
6. Does a controller alias bypass authorization on another route?
7. Do matcher-level tests fail?

Never paper over wrong chain selection by merely changing the 403 status/body.

### 16.2. `/diagnostics/secret` returns 200 bypassing auth

Check that the fallback bean exists and is not disabled by profiles/conditional config; that it has `anyExchange().denyAll()`; and that no higher-priority match-all public chain exists. Check direct backend ingress and alternate management ports. Add a real sentinel handler to test rather than relying on 404.

### 16.3. `/ops/status` does not accept Basic

Check `@Order(3)`, the `/ops/**` matcher, HTTP Basic enabled, the user details service, and the password encoder. If the response contains a Bearer challenge, a JWT chain likely matched Ops first. Never enable Basic across all URLs to fix it.

### 16.4. Valid JWT gets 403 on tenant Items

Classify the cause:
- JWT lacks `SCOPE_tenant.read`.
- `tenant_id` differs from the path tenant.
- User membership was revoked.
- Data/object ownership denied access.
- Query was scoped to another tenant.
- Wrong token audience/issuer: typically 401 before reaching the controller.
- Proxy rewrite turned `/api/tenant/acme` into beta's path.

Keep the tenant policy intact; fix the identity mapping or authorization grants instead of disabling ownership checks.

### 16.5. SPA preflight OPTIONS returns 401

Never try to attach tokens to CORS preflight requests. Configure `CorsWebFilter`/WebFlux CORS properly for allowed origins/methods/headers so it runs before authentication. Actual API requests must still carry valid access tokens and permissions.

## 17. Coverage as a CI Security Contract

Real repositories should maintain a route inventory:
- External host/path/method.
- Internal path after Gateway rewrite.
- Expected first-matching chain.
- Authentication scheme (JWT, Basic, OIDC, mTLS).
- Trusted issuer/audience/algorithms.
- Required scopes/roles.
- Tenant membership/object ownership checks.
- Expected status for anonymous/invalid/valid-but-unauthorized callers.
- CORS/CSRF expectations.
- Responsible owner and test case ID.

Whenever adding a `@GetMapping`, `RouterFunction`, Actuator endpoint, new REST version, or Proxy route:
1. Update the inventory.
2. Run `ChainCoverageTest` directly.
3. Run positive/negative HTTP `WebTestClient` tests.
4. Run signed-token/issuer/audience JWT integration tests when changing security mechanisms.
5. Run Gateway E2E tests with external paths and forwarded headers.
6. Verify client credential isolation and tenant boundaries.
7. Test methods, trailing slashes, and encoded variants.
8. Block deployment if any sensitive handler falls outside all chains or lacks policy.

**You do not need one security chain per tenant.** For many tenants using the same JWT framework, one chain + service-level tenant/ownership policies is cleaner. For multiple issuers, use trusted-issuer resolution rather than synthesizing decoders from unverified claims.

## 18. Production Review Checklist

### Chain routing
- [ ] Every `SecurityWebFilterChain` has an explicit, distinct `@Order`.
- [ ] Narrow admin matcher runs before generic API matcher.
- [ ] Final match-all `denyAll()` chain exists.
- [ ] No fallback `permitAll`.
- [ ] Every public handler is allowed by exact method/path rules.
- [ ] Unreviewed handlers are denied even when mapped.
- [ ] Roots, trailing slashes, prefix boundaries, and encodings tested.
- [ ] WebFlux.fn, management port, actuator, WebSocket/GraphQL inventories reviewed.

### Authentication and authorization
- [ ] JWT issuer/JWKS/audience/expiration/signature policy verified.
- [ ] Admin scope is separate from Tenant scope; Basic cannot unlock JWT routes.
- [ ] Ops Basic is restricted to internal domains protected by TLS/mTLS/network policies.
- [ ] Tenant claim/membership checked against requested tenant and resource owner.
- [ ] `X-Tenant`/`X-Forwarded-Host` never treated as proof of identity.
- [ ] Roles/authorities mapped from trusted claims or an entitlement service.
- [ ] Raw tokens/PII never placed in logs or error bodies.

### Browser/gateway
- [ ] CORS preflight works; actual requests still require authorization.
- [ ] CSRF policy fits each auth scheme, especially Basic and cookies.
- [ ] Proxy rewrites tested E2E, not solely via direct `WebTestClient`.
- [ ] Direct backend ingress/alternate ports cannot bypass trust boundaries.
- [ ] Gateway validates certificates/headers per contract when using mTLS.

### Tests
- [ ] First-match order verified via `SecurityWebFilterChain.matches()`.
- [ ] `WebTestClient` verifies 200/401/403 per domain.
- [ ] Tests cover missing-scope tokens and tenant mismatches.
- [ ] Tests verify mapped sentinel in fallback never returns 2xx.
- [ ] Tests verify new API versions/methods are denied.
- [ ] Tests cover wrong schemes: Basic→Admin, Bearer→Ops.
- [ ] Real JWT tests cover signature, issuer, audience, and expiry separately.
- [ ] Tests cover Gateway rewrites and edge cases.

## 19. Review Questions

**1. How does `securityMatcher` differ from `pathMatchers`?**

> `securityMatcher` selects which `SecurityWebFilterChain` handles the request; `pathMatchers` inside `authorizeExchange` selects authorization rules within that chosen chain.

**2. If two chains both match a URL, which chain runs?**

> The chain evaluated first by `@Order` whose `matches(exchange)` returns true; subsequent chains are not merged.

**3. Why must `/api/admin/**` come before `/api/**`?**

> Because the broad matcher would shadow the narrow admin matcher and prevent the stricter admin policy from running.

**4. Does `anyExchange().denyAll()` in the Admin chain protect `/diagnostics/secret`?**

> No. It applies only to requests that entered the admin chain.

**5. How do you prevent new URLs from falling outside every security chain?**

> Add a final match-all catch-all chain with `denyAll()` and test with a real sentinel controller.

**6. Does a 403 prove the right chain was selected?**

> No. A generic `denyAll` can also return 403; matcher-level tests are needed.

**7. Does a 404 prove an endpoint is protected?**

> No. It may simply mean no controller exists for that path.

**8. Does a JWT with `tenant.read` grant access to read every tenant?**

> No. Membership and object ownership must be checked at the domain layer.

**9. Why can a `permitAll` `/api/ping` route still return 401 with an invalid Bearer token?**

> The chain's authentication filter can still run before the `permitAll` authorization rule.

**10. Why does Basic OPS not unlock JWT Admin?**

> Authentication mechanisms are configured per chain/matcher, and JWT Admin does not enable Basic.

**11. In `ChainCoverageTest`, what `Mono` type does `matches(exchange)` return?**

> `SecurityWebFilterChain.matches` returns `Mono<Boolean>`, not `ServerWebExchangeMatcher`'s `Mono<MatchResult>`.

**12. Should CSRF be disabled app-wide because of a JWT API?**

> No. Basic/browser cookie/OIDC session routes have different threat models.

**13. Why do Gateway rewrites affect coverage?**

> Matchers inspect the internal path the app actually receives, which may differ from the external URL.

**14. Does `mockJwt` or a `@MockitoBean` decoder prove signature/issuer/audience validation?**

> No. Real decoder tests with signed JWTs/JWKS and negative fixtures are required.

**15. Should you create a `SecurityWebFilterChain` for every tenant in the DB?**

> Usually not if the auth scheme is identical. Enforce tenant policies in services; split chains only when trust/auth behavior truly differs.

**16. What are the three layers of tests to use?**

> Matcher first-match, HTTP `WebTestClient` authorization, and E2E Gateway/real token validation.

## 20. Summary

Multiple Spring Security WebFlux chains separate API domains cleanly, yet **do not automatically prove full URL coverage**. A solid design consists of:

~~~text
Incoming request
     |
     v
@Order(1) /api/admin, /api/admin/** ?
       YES -> Admin JWT + admin scope
       NO
     v
@Order(2) /api, /api/** ?
       YES -> Tenant JWT / exact public GET / deny unreviewed
       NO
     v
@Order(3) /ops, /ops/** ?
       YES -> Ops HTTP Basic + ROLE_OPS
       NO
     v
@Order(99) match-all fallback
       -> denyAll
~~~

Three principles to maintain:
1. **First-match wins:** narrow matchers precede broad matchers, with `@Order` tested.
2. **Fail closed:** `anyExchange().denyAll()` inside each chain plus a final catch-all; unreviewed routes never become public automatically.
3. **Verify coverage + real permissions:** test `SecurityWebFilterChain.matches(ServerWebExchange)`, HTTP auth/statuses, tenant/object ownership, and E2E Gateway rewrites.

The example provides **25 tests** across HTTP and matcher layers, but because the JWT decoder in HTTP tests is mocked, real signatures/issuers/audiences are not yet proved. Do not claim Gradle was executed: build/test execution and staging E2E verification are still required before deployment.

### Official References

- Spring Security 6.5 — WebFlux Security / Multiple Chains Support: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 — Reactive Resource Server Multitenancy: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html
- Spring Security 6.5 — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Security 6.5 — Testing Reactive OAuth2/JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security 6.5 — Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — Reactive CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security 6.5 — Reactive CORS: https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html
- Spring Security API — SecurityWebFilterChain: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/SecurityWebFilterChain.html
- Spring Security API — ServerWebExchangeMatchers: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html
- Spring Security API — ServerHttpSecurity: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Boot 3.5 — Security Reference: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725