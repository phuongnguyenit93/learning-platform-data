# Splitting Security Chains for Web UI, API, and Admin Endpoints in Spring Security Reactive

## 1. Objectives of This Integrated Practice

A Spring WebFlux application often serves multiple caller groups simultaneously: web pages for users, APIs for client apps, and operational endpoints for administrators. Those three groups have different requirements for login mechanisms, CSRF, sessions, permissions, error responses, and monitoring. Applying one policy to all URLs easily causes bugs such as APIs redirecting to a login page, admin pages accidentally accepting regular user login cookies, or disabling CSRF across the entire website.

This lab builds a **multiple `SecurityWebFilterChain`** configuration with Spring Security WebFlux, Java 17+, and Spring Boot 3.x / Spring Security 6.x, focusing on:

1. Separating one chain for **/admin/**, one chain for **/api/**, one chain for the **web UI**, and a **deny-by-default** fallback chain.
2. Controlling evaluation order with **@Order** and scope with **securityMatcher**.
3. Distinguishing **filter chain selection** from **in-chain request authorization**.
4. Designing sessions/CSRF and returning 401, 403, or 302 appropriately per group.
5. Testing the boundaries so credentials from one group cannot slip into another.

The code below shows configuration and endpoints for **a single Spring Boot WebFlux application**; Java files include explicit names and build commands. The JWT section requires a real Identity Provider/`ReactiveJwtDecoder` in deployment; in-memory accounts in the `local` profile are solely for learning and testing. Never carry sample passwords or admin HTTP Basic auth into production without evaluating MFA and additional protections.

## 2. Application Architecture and Policy Matrix

Suppose one WebFlux service exposes the following routes:

| Group | Typical URL | Authentication | Permissions | CSRF | Store Authentication |
| --- | --- | --- | --- | --- | --- |
| Public web page | GET /web/public/info | Optional | permitAll | Enabled on web chain; GET needs no token | WebSession may be used for web |
| User page | GET /web/home | Form login, session cookie | ROLE_USER | Enabled | WebSession |
| Web action | POST /web/actions | Form login, session cookie | ROLE_USER | Token required | WebSession |
| Public API | GET /api/public/ping | Optional | permitAll | Disabled if Bearer-header-only and cookie-free | Not stored in session |
| Read/write API | GET/POST /api/orders | JWT bearer | SCOPE_orders.read / SCOPE_orders.write | Disabled in stateless Bearer-header API | Not stored in session |
| Admin | GET /admin/status | HTTP Basic in demo | ROLE_ADMIN | Enabled | Not stored in session |
| Admin action | POST /admin/reindex | HTTP Basic in demo | ROLE_ADMIN | Token required | Not stored in session |
| Other | /unknown, /internal, /debug | None granted | denyAll | N/A | Receives no privileges from other groups |

**Classification rule:** Admin URLs are privileged resources. Do not assume naming a route /api/admin/** or /web/admin/** automatically places it under the /admin/** chain. Actual paths, matcher order, and per-chain permissions must be controlled consistently. Never expose the same admin capability under a general-purpose endpoint with weaker checks.

We choose:
- **ADMIN** chain at priority 1: /admin/**, HTTP Basic strictly to clearly demonstrate mechanism differences, requiring ROLE_ADMIN. CSRF stays enabled because browsers can send Basic credentials automatically.
- **API** chain at priority 2: /api/**, JWT bearer, scope-based, disabling CSRF **only when the API does not authenticate via cookies or browser auto-sent credentials**.
- **WEB** chain at priority 3: /web/**, /login, /logout, /assets/**, form login and CSRF; do not enable HTTP Basic on this group.
- **FALLBACK** chain at priority 4: all remaining requests, rejected with denyAll.

**Important caveat:** HTTP Basic + ROLE_ADMIN **is not equivalent to MFA**. It is a local test mechanism to illustrate an independent policy; production admin consoles should use OIDC/SSO with MFA or strong organization-approved auth, network access controls, and auditing. When swapping the admin auth mechanism, preserve the same separation of matchers, permissions, session/CSRF, and tests.

## 3. How a SecurityWebFilterChain Is Selected

An incoming WebFlux request is handled by **a single matching `SecurityWebFilterChain`** chosen in evaluation order. Chains do not automatically merge filters or inherit policies from later chains. Spring Security evaluates higher-priority chain matchers first; the first match wins.

There are two distinct matcher levels:

**Level 1 — `securityMatcher`:** decides which security chain processes the request. For example, a chain with `securityMatcher` for /api/** will not handle /web/home.

**Level 2 — `authorizeExchange`:** inside the chosen chain, enforces distinct rules per method/route. For example, GET /api/orders requires SCOPE_orders.read, while POST /api/orders requires SCOPE_orders.write.

A common pitfall:

~~~java
// Belongs only to the API chain; DOES NOT protect routes outside /api/**.
http.securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/public/**").permitAll()
        .anyExchange().authenticated());
~~~

If no other chain covers /admin/**, the API matcher does nothing to protect /admin/**. Likewise, placing a catch-all chain at @Order(1) ensures subsequent /api/** and /admin/** chains are never reached. Therefore, the fallback chain must have the lowest priority and default to denyAll.

**Do not confuse with Spring MVC/Servlet:** WebFlux uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ServerWebExchangeMatcher`. Servlet uses `HttpSecurity`, `SecurityFilterChain`, and `RequestMatcher`. Never copy Servlet examples and simply rename imports.

## 4. Creating the Project and Minimal Dependencies

Create a Spring Boot WebFlux project (Java 17+) with these dependencies:
- spring-boot-starter-webflux
- spring-boot-starter-security
- spring-boot-starter-oauth2-resource-server
- spring-boot-starter-test
- spring-security-test

The `pom.xml` snippet below is a **`dependencies` block**, assuming the project already has a compatible Spring Boot parent/BOM; it is not a standalone POM:

~~~xml
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
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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
~~~

If using Gradle, add the corresponding runtime starters via `implementation(...)` and test dependencies via `testImplementation(...)`, managed by the Spring Boot plugin/BOM. Avoid overriding Spring Security, Framework, Reactor, and Netty versions arbitrarily.

Here is the Spring Boot main class in `src/main/java/example/split/SplitSecurityApplication.java`:

~~~java
package example.split;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SplitSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(SplitSecurityApplication.class, args);
    }
}
~~~

**JWT API requirement:** In deployment environments, set `spring.security.oauth2.resourceserver.jwt.issuer-uri` pointing to a trusted token issuer, or supply an appropriate `ReactiveJwtDecoder`. With `issuer-uri`, the decoder verifies signatures and claims per config; a resource server does not mint bearer tokens. An arbitrary self-crafted string is not a valid JWT.

Do not embed issuers, client secrets, or JWT signing keys into lesson code just to “make it run.” The integration tests below use `mockJwt()` to verify authorization without a real Identity Provider; real token verification requires a dedicated environment with controlled keys and issuers.

## 5. Complete Configuration of Four WebFlux Chains

Create `src/main/java/example/split/SegmentedSecurityConfig.java`. This is a complete Java class in terms of imports/declarations; it needs Spring Boot WebFlux, Spring Security, and a real authentication setup to run.

~~~java
package example.split;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SegmentedSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers("/admin/**"))
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().hasRole("ADMIN"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers("/api/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/api/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/orders", "/api/orders/**")
                                .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST,
                                "/api/orders", "/api/orders/**")
                                .hasAuthority("SCOPE_orders.write")
                        .anyExchange().denyAll())
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(ServerWebExchangeMatchers.pathMatchers(
                        "/web/**", "/login", "/logout", "/assets/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/login", "/assets/**",
                                "/web/public/**").permitAll()
                        .pathMatchers("/web/**").hasRole("USER")
                        .anyExchange().authenticated())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(Customizer.withDefaults())
                .logout(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(4)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().denyAll())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Reading the configuration in order:**

1. `/admin/**` is evaluated first. Users must hold `ROLE_ADMIN` and send valid Basic credentials on each demo request. `NoOpServerSecurityContextRepository` avoids saving/loading `SecurityContext` via a session repository on this chain; it does not globally disable cookies or every other session mechanism in the app. CSRF stays enabled for state-changing requests.
2. `/api/**` is evaluated next. JWT bearer is configured in the same chain with scope rules, using the NoOp repository so web login sessions never authenticate API calls; CSRF is disabled only here.
3. The web UI uses form login + logout, CSRF, and `WebSession`. Default login is `/login` and default logout is `/logout`, so both paths must match the **web chain's `securityMatcher`**. Static `/assets/**` are also included in this chain.
4. Every other route hits the `denyAll` fallback, preventing a URL gap from being processed outside any security chain.

**Order 1–3 can be swapped** if matchers are truly disjoint, though order must stay explicit and tested. Whenever matchers overlap, the more specific/privileged chain must precede broader chains. Never assign the same `@Order` value to two chains and rely on incidental bean scanning order.

**Note on root paths:** If `/admin`, `/api`, or `/web` (without a trailing slash) should be accessible or redirected, verify exact `PathPattern` behavior and add explicit matchers/routes. Never assume `/admin/**` covers every `/admin` variant across every setup. In this example, fallback `denyAll` is a conservative default for paths outside intended matchers.

## 6. Explaining Three Auth Styles and Session Scope

### 6.1. Web UI: Form Login, Cookies, and CSRF

When a user visits `/web/home`, the web `SecurityWebFilterChain` requires `ROLE_USER`. If unauthenticated, the form-login entry point typically redirects to `/login`. Form login submits `username` and `password` per the configured contract; after authentication, Spring Security can store `SecurityContext` in `WebSession` for subsequent requests.

- `GET /login` must be allowed into the web chain so the login page renders.
- `POST /login` must hit the right chain with a valid CSRF token.
- `POST /logout` also requires a CSRF token under default behavior.
- When building a custom login page, the display URL, processing URL, static assets, and redirects must all match the chain. Adding a custom `loginPage()` without adding its path to `securityMatcher` can cause 302 redirect loops, 404s, or 403s.

**A browser session is not an API authentication method** in this design. A web user's session cookie cannot call `GET /api/orders`; the API requires a bearer token and scope.

### 6.2. API: Bearer JWT Without Login Cookies

An API client sends:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...<illustrative-token-string>
Accept: application/json
~~~

The string in `Authorization` above **only illustrates header format**, not a usable token. A valid JWT must pass decoder checks for signature, expiry, issuer, and related constraints (e.g., audience per policy). A mapper converts scopes/authorities into `GrantedAuthority`. Under section 5's rules:
- `GET /api/orders` requires `SCOPE_orders.read`.
- `POST /api/orders` requires `SCOPE_orders.write`.
- `GET /api/public/ping` allows anonymous callers via `permitAll`.
- All other API methods/URLs hit `denyAll`.

**Important nuance:** `permitAll` on `/api/public/**` does not mean an invalid bearer token is ignored. If a request sends a malformed `Authorization: Bearer`, the authentication filter can return 401 before authorization runs. Test public endpoints both without a header and with an invalid header.

**Why can CSRF be disabled on this API?** Because this API accepts only credentials explicitly attached in the `Authorization` header, without cookies/sessions or browser-cached Basic credentials. If you change the API to authenticate via session cookies, refresh cookies, or browser-auto-attached credentials, re-evaluate and restore CSRF protection. Putting “REST” in a path name never exempts an API from CSRF.

### 6.3. Admin Endpoints: High Privilege, Independent Scope

The demo's admin chain uses HTTP Basic to test `ROLE_ADMIN` separately from web forms and API JWTs:
- Missing Basic credentials: typically 401 with a Basic challenge.
- Basic credentials for a `ROLE_USER` account: authenticated yet unauthorized, typically 403.
- Basic credentials for `ROLE_ADMIN`: allowed when method and CSRF are valid.
- Web session cookie alone: ignored by the no-op security context repository on the admin chain.
- API JWT bearer alone: not authenticated by the admin chain in this example.

**Never use plain HTTP Basic as your production admin architecture.** For browser-operated admin consoles, prefer SSO/OIDC with MFA, WebAuthn, or strong org-wide auth policies; require HTTPS, potentially managed devices, VPN/allowlists, restricted privileged accounts, and audit logs. Switching mechanisms requires updating entry points, sessions, and CSRF specifically on the admin chain. Splitting chains organizes policy—it does not magically supply strong authentication.

**CSRF nuance:** Although `NoOpServerSecurityContextRepository` avoids storing `Authentication` in a session repository, default CSRF handling can still use `WebSession` to store tokens. Saying “no authentication session” is more accurate than claiming the entire admin chain never touches a session. When browsers use Basic auth, credentials can also be resent automatically, so keep CSRF protection on POST/PUT/PATCH/DELETE.

## 7. Sample Routes for Running and Testing

Create `src/main/java/example/split/DemoEndpoints.java`:

~~~java
package example.split;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoEndpoints {

    @GetMapping("/web/public/info")
    public Mono<String> publicWebInfo() {
        return Mono.just("web-public");
    }

    @GetMapping("/web/home")
    public Mono<String> webHome() {
        return Mono.just("web-home");
    }

    @PostMapping("/web/actions")
    public Mono<String> webAction() {
        return Mono.just("web-action-ok");
    }

    @GetMapping("/api/public/ping")
    public Mono<String> apiPing() {
        return Mono.just("pong");
    }

    @GetMapping("/api/orders")
    public Mono<String> readOrders() {
        return Mono.just("api-orders-read");
    }

    @PostMapping("/api/orders")
    public Mono<String> writeOrders() {
        return Mono.just("api-orders-write");
    }

    @GetMapping("/admin/status")
    public Mono<String> adminStatus() {
        return Mono.just("admin-status");
    }

    @PostMapping("/admin/reindex")
    public Mono<String> adminReindex() {
        return Mono.just("admin-reindex-requested");
    }
}
~~~

This demo controller returns plain strings to observe responses without real data mutations. In real systems, controllers are protected by the filter chain, yet critical services should still enforce business/ownership/tenant authorization. If a business method can also be triggered by a job/queue or another endpoint, route-level policies alone are not enough.

Spring WebFlux can bind these routes, while `SecurityWebFilterChain` decides whether a request ever reaches the controller. A `GET /api/orders` lacking the required scope cannot succeed simply because the controller omits direct permission calls.

## 8. Test Accounts Strictly for the `local` Profile

Create `src/main/java/example/split/LocalUsers.java`. This class is loaded only when the `local` profile is active. Passwords below are **dummy data—never use them in production**:

~~~java
package example.split;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

@Configuration(proxyBeanMethods = false)
@Profile("local")
public class LocalUsers {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails webUser = User.withUsername("webuser")
                .password(encoder.encode("web-only-local"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("opsadmin")
                .password(encoder.encode("admin-only-local"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(webUser, admin);
    }
}
~~~

- `webuser` holds `ROLE_USER` for web form login. Sending its Basic credentials to `/admin/status` will be denied.
- `opsadmin` holds `ROLE_ADMIN` for testing `/admin/status` with Basic auth. It does not automatically hold `ROLE_USER`.
- BCrypt hashes the sample passwords at bean creation, yet **plaintext passwords still sit in demo code**. Never activate the `local` profile in environments with real data, and never ship demo accounts to production.

In production, replace demo beans with a managed `ReactiveUserDetailsService`/`ReactiveAuthenticationManager`, SSO/OIDC, or managed identity store. Do not create a `MapReactiveUserDetailsService` just to support JWT bearer auth, because JWT validation uses its own decoder and Resource Server authentication manager.

## 9. Configuring the JWT Resource Server

In environments with a real issuer, configure:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/your-realm
~~~

The address above is **merely a config structure example**; replace it with a real issuer URI serving valid metadata/JWK before running. Never use a fake issuer and assume the Java config is broken. Depending on tokens, you may also use `jwk-set-uri` or a custom `ReactiveJwtDecoder` bean. Never disable signature, `exp`/`nbf`, issuer, or audience checks just to make tests pass.

When the issuer sends scope authorities, standard mapping creates `SCOPE_...` authorities (e.g., scope `orders.read` maps to `SCOPE_orders.read`). Not every IdP uses the same claim, so check your converter. `hasRole("ADMIN")` expects `ROLE_ADMIN`, unlike an unconverted `"admin"` JWT claim. Never assume raw role claims and Spring `GrantedAuthority` automatically match.

Production JWT requirements should be verified individually:
1. Signature, allowed algorithms, and key rotation.
2. Issuer, `exp`/`nbf` validity, and clock skew.
3. Audience matching this API, not just a valid issuer.
4. Scope/role mapping following least privilege.
5. Access token type, avoiding using ID tokens to access APIs.
6. Logs free of tokens, `Authorization` headers, JWK secrets, or personal claims.
7. Never turning tokens into cookie auth in an API while leaving `csrf.disable()` in place without a risk review.

## 10. Request Flow Through the Four Chains

Visualizing the flow:

~~~text
HTTP request
  |
  v
@Order(1): matches /admin/** ?
  |-- Yes --> Admin SecurityWebFilterChain --> ROLE_ADMIN, Basic, CSRF
  |
  v
@Order(2): matches /api/** ?
  |-- Yes --> API SecurityWebFilterChain --> JWT, scopes, no auth session
  |
  v
@Order(3): matches /web/**, /login, /logout, /assets/** ?
  |-- Yes --> Web SecurityWebFilterChain --> Form login, WebSession, CSRF
  |
  v
@Order(4): matches all remaining paths
  |-- Yes --> denyAll
~~~

Reference scenario table for the example configuration (assuming the app is running cleanly with matching decoder/API mocks and no custom exception handler altering statuses):

| Request | Identity | Expected | Why |
| --- | --- | --- | --- |
| GET /web/public/info | None | 200 | WEB permitAll |
| GET /web/home | None | 302 to /login | WEB formLogin entry point |
| GET /web/home | webuser session | 200 | ROLE_USER |
| POST /web/actions | webuser session, no CSRF | 403 | Rejected by WEB CsrfWebFilter |
| POST /web/actions | webuser session, valid CSRF | 200 | Auth + CSRF pass |
| GET /api/public/ping | None | 200 | API permitAll |
| GET /api/orders | None | 401 | API requires JWT |
| GET /api/orders | JWT with scope orders.read | 200 | SCOPE_orders.read |
| POST /api/orders | JWT with only orders.read | 403 | Missing orders.write |
| POST /api/orders | JWT with orders.write | 200 | Scope matches, API disables CSRF |
| GET /admin/status | None | 401 | ADMIN Basic challenge |
| GET /admin/status | Basic webuser | 403 | Lacks ROLE_ADMIN |
| GET /admin/status | Basic opsadmin | 200 | Role matches |
| POST /admin/reindex | Basic opsadmin, no CSRF | 403 | ADMIN CSRF is enabled |
| GET /admin/status | Web session cookie only | 401 | ADMIN ignores session auth |
| GET /api/orders | Web session cookie only | 401 | API ignores web session |
| GET /api/orders | Basic opsadmin | 401 | API enables Resource Server JWT only |
| GET /unknown | Any | 403 or appropriate deny response | FALLBACK denyAll |

Exact HTTP codes (especially 302/401/403) depend on entry points, exception handling, and extra filters. Base tests on actual configured behavior rather than treating this table as guaranteed across every version. If a router returns 404 before security or a gateway rewrites paths, verify the real routing path.

## 11. Testing with WebTestClient and spring-security-test

**Test setup:** Spring Boot context containing `SegmentedSecurityConfig`, `DemoEndpoints`, `LocalUsers` (`local` profile), and a suitable reactive decoder. For tests focused solely on chains and authorization, you can define a **test-only** decoder that rejects raw tokens and use `mockJwt()` to inject a mocked `Authentication`. That avoids contacting a real IdP when testing route policies; JWT signature tests belong in a separate suite.

Create `src/test/java/example/split/SegmentedSecurityTest.java`:

~~~java
package example.split;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@ActiveProfiles("local")
@Import(SegmentedSecurityTest.TestDecoder.class)
class SegmentedSecurityTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicEndpointsAreReachable() {
        client.get().uri("/web/public/info")
                .exchange().expectStatus().isOk();
        client.get().uri("/api/public/ping")
                .exchange().expectStatus().isOk();
    }

    @Test
    void protectedApiDoesNotAcceptAnonymous() {
        client.get().uri("/api/orders")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void apiReadScopeAllowsReadOnly() {
        WebTestClient apiReader = client.mutateWith(
                mockJwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")));

        apiReader.get().uri("/api/orders")
                .exchange().expectStatus().isOk();

        apiReader.post().uri("/api/orders")
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void apiWriteScopeAllowsPostWithoutCsrf() {
        client.mutateWith(mockJwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.write")))
                .post().uri("/api/orders")
                .exchange().expectStatus().isOk();
    }

    @Test
    void webWriteRequiresCsrf() {
        client.mutateWith(mockUser("webuser").roles("USER"))
                .post().uri("/web/actions")
                .exchange().expectStatus().isForbidden();

        client.mutateWith(mockUser("webuser").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/web/actions")
                .exchange().expectStatus().isOk();
    }

    @Test
    void adminRequiresBasicCredentialAndAdminRole() {
        client.get().uri("/admin/status")
                .exchange().expectStatus().isUnauthorized();

        client.get().uri("/admin/status")
                .headers(headers ->
                        headers.setBasicAuth("webuser", "web-only-local"))
                .exchange().expectStatus().isForbidden();

        client.get().uri("/admin/status")
                .headers(headers ->
                        headers.setBasicAuth("opsadmin", "admin-only-local"))
                .exchange().expectStatus().isOk();
    }

    @Test
    void webSessionDoesNotBecomeApiCredential() {
        // No bearer header -> cannot authenticate at the API.
        // A complete session test should first login via /login,
        // capture the session cookie and send it to /api/orders.
        client.get().uri("/api/orders")
                .exchange().expectStatus().isUnauthorized();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestDecoder {
        @Bean
        ReactiveJwtDecoder jwtDecoder() {
            return token -> Mono.error(
                    new BadJwtException(
                            "Raw tokens are intentionally rejected in this test"));
        }
    }
}
~~~

What these tests demonstrate:
- `mockJwt` injects `Authentication`/authorities to **test endpoint authorization**, not real token signature or issuer validation.
- Basic tests exercise `LocalUsers` to verify role handling without faking admin via `mockUser`.
- `webWriteRequiresCsrf` demonstrates active CSRF protection on the web chain.
- `webSessionDoesNotBecomeApiCredential` here only confirms the API rejects requests lacking a bearer header. **It does not yet exercise a real web session cookie**; to prove session boundary isolation fully, perform form login with CSRF, capture `Set-Cookie`, and replay that cookie against `/api/orders` and `/admin/status`. Never claim this test already proves complete session isolation.

If your test environment sets a production `issuer-uri`, clear the issuer property in the test profile or adjust config so `TestDecoder` is unambiguously selected instead of creating two competing `ReactiveJwtDecoder` beans. If your framework/test setup differs, keep the same test goals and consult docs matching your Spring Boot/Security versions.

Run with Maven Wrapper:

~~~bash
./mvnw -Dtest=SegmentedSecurityTest test
~~~

Or with Gradle:

~~~bash
./gradlew test --tests example.split.SegmentedSecurityTest
~~~

On Windows, use `mvnw.cmd` or `gradlew.bat`. In CI, also run tests without the `local` profile to prove demo users are excluded from production builds/runtimes.

## 12. The Most Important Tests: Boundaries Between the Three Groups

A single test calling `GET /admin/status` as an admin user is not enough. You must verify **credentials cannot cross group boundaries**:

1. A valid `webuser` session accesses `/web/home`; sending that same cookie to `/api/orders` or `/admin/status` without matching credentials must still be rejected.
2. Valid `opsadmin` Basic credentials work on `/admin/status` yet **never replace an API JWT bearer**. Sending a Basic header to `/api/orders` must fail.
3. A JWT with `SCOPE_orders.read` can call `GET /api/orders`; using that JWT on `/admin/status` in this Basic-protected admin chain must fail.
4. A JWT with `SCOPE_orders.read` cannot `POST /api/orders`; `SCOPE_orders.write` does not imply `SCOPE_orders.read` if the converter/issuer grants only one scope.
5. Holding `ROLE_ADMIN` does not automatically grant `ROLE_USER`; regular users must not view or mutate admin resources even if they know the endpoint.
6. `POST /web/actions` and `POST /admin/reindex` require valid CSRF; `POST /api/orders` with a bearer header skips CSRF per the stated design.
7. `/assets/**` may be public only if it holds safe static assets, while `/unknown`, `/debug`, `/actuator`, or unfamiliar routes must never become accidentally public.
8. Boundary paths such as `/admin`, `/admin/`, `/admin/status/`, `/api`, `/api/`, `/web`, and case variations must be tested against the actual router and matchers.
9. With multiple `SecurityWebFilterChain` beans, verify every route enters the **exact right chain** rather than being captured earlier by a catch-all.
10. When replacing form login with OIDC, callback and authorization URLs must reside in the web chain and be protected properly rather than blocked by fallback or misrouted into the API chain.

**Test quality:** Combine real-mechanism auth tests (form login, Basic, signed JWTs/decoder with test issuers) with mock tests that isolate authorization. If every test uses `mockUser` or `mockJwt` on every route, you can miss broken authentication managers, login endpoints, or session persistence.

## 13. Why Not Just Use One Chain with pathMatchers?

A single chain can still separate authorization:

~~~java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().permitAll());
~~~

However, this **fails to separate authentication mechanisms, CSRF, `SecurityContextRepository`, or entry points per group**. Enabling form login and bearer auth in one chain causes problems:
- An unauthenticated API call can receive an HTML 302 redirect to `/login` instead of a 401 JSON response.
- A browser holding a session cookie may be treated as authenticated on the API without a dedicated policy.
- Disabling CSRF across the whole chain to “make API calls easy” weakens web forms.
- An overly broad `permitAll` rule or wrong `pathMatchers` order can expose admin routes.
- When stronger admin requirements arrive, configuring exception handlers, header policies, tenant controls, and monitoring becomes tangled.

Multiple chains fit whenever **groups require different authentication or HTTP handling policies**. If an entire system is genuinely a single uniform JWT API, do not invent extra chains unnecessarily. Let real security boundaries determine chain count.

## 14. CSRF: Decide Based on How Browsers Send Credentials

**CSRF is not exclusively an HTML form vulnerability.** It occurs whenever a browser automatically attaches a victim's credentials on a cross-site request, such as session cookies or cached HTTP Basic credentials. Therefore:

- Web form login using session cookies: keep CSRF on POST/PUT/PATCH/DELETE, including login and logout.
- Admin HTTP Basic used from browsers: CSRF may still be needed because browsers resend credentials automatically. In this example, CSRF stays enabled.
- JWT APIs accepting only `Authorization` headers explicitly attached by JS/mobile/service clients: CSRF can be disabled on the API chain, provided no cookies/sessions/Basic auth are auto-sent.
- APIs using session cookies, refresh cookies, or auto-sent credentials: re-evaluate CSRF even if the endpoint returns JSON.
- CORS does not replace CSRF. `SameSite` cookies are defense-in-depth, not a universal substitute for CSRF tokens.

Mistake to avoid:

~~~java
// DO NOT put this on a catch-all chain in an app with forms/sessions.
http.csrf(ServerHttpSecurity.CsrfSpec::disable);
~~~

With multiple chains, disable CSRF only on APIs proven not to receive automatic credentials. Keep it enabled on web and admin chains. If an SPA uses cookies, configure an appropriate `ServerCsrfTokenRepository` and send tokens via headers; the implementation must align with `XorServerCsrfTokenRequestAttributeHandler`/BREACH protections and the client framework. Never place CSRF tokens in URLs, logs, or analytics.

## 15. Authentication, Authorization, and Business Boundaries

Every chain must answer three independent questions:

1. **Who is calling?** Form login, JWT bearer, Basic, OIDC, or another mechanism, and which component verifies the credential.
2. **Which routes may they call?** `authorizeExchange`, roles/authorities/scopes, methods, and policies.
3. **Which resources inside the route may they access?** Ownership, tenant isolation, field-level authorization, and method/service-layer checks.

For instance, `SCOPE_orders.read` does not allow reading every customer's orders. Services must restrict by user/tenant or use an appropriate authorization manager. `ROLE_ADMIN` does not necessarily authorize sensitive actions like locking accounts if extra approval or step-up authentication is required.

In reactive services, read the principal via `ReactiveSecurityContextHolder` or pass the verified Actor/Principal through `Mono`/`Flux`. Never rely on arbitrary-thread `ThreadLocal`/`SecurityContextHolder`, never cache `Authentication` in a singleton, and never write a `WebFilter` that trusts unverified client headers to inject roles.

When using method security, enable `@EnableReactiveMethodSecurity` per your version, enforce checks on Spring-managed beans, and test that internal self-calls do not bypass the method-security proxy.

## 16. Rules for Web Login and OIDC Callbacks

If the UI later switches to OAuth2/OIDC login:
- Initiation endpoints typically look like `/oauth2/authorization/{registrationId}`.
- Callback redirects typically look like `/login/oauth2/code/{registrationId}`.
- Login success/failure redirects may target `/web/...` or an explicitly defined URL.
- These paths must match the `securityMatcher` of the chain managing OAuth2 login and be handled by Spring Security's callback machinery—do not simply `permitAll` and hope callbacks work.
- With multiple chains using different OAuth2 logins, ensure login/redirect URIs, `registrationId`, session/correlation state, CSRF, and handlers do not collide.
- Allow only registered redirect URIs; never read arbitrary redirect targets from query params to prevent open redirects.

A classic anti-pattern: `webChain` matches only `/web/**`, while default `formLogin` redirects to `/login` and fallback has `denyAll`. Unauthenticated `/web/home` requests redirect to `/login`, which falls outside the web chain. Adding `/login` and `/logout` to `securityMatcher` in section 5 is **deliberate**, not a blanket `permitAll` on everything else.

## 17. CORS, Same-Origin, Cookies, and Proxies

If the UI and API live on different origins, configure CORS for trusted origins and actually used methods/headers. CORS policies do not replace authentication rules; preflight `OPTIONS` requests may need proper ordering relative to auth filters for browser clients. Avoid `Access-Control-Allow-Origin: *` combined with credentialed cookies. Even when UI and API share an origin, if the API uses bearer headers only, never treat the session cookie as API auth.

Operational points:
- Web cookies: `Secure`, `HttpOnly`, and `SameSite` per login/SSO needs, HTTPS, and suitably short session lifetimes; never log session IDs.
- API Bearer Authorization: never log JWTs/tokens; never place tokens in query strings or URLs.
- Reverse proxies: verify the paths WebFlux sees **after** gateway rewrites; `securityMatcher` matches application-layer paths, not imagined external URLs.
- Behind a context path or route prefix, test patterns against the real post-proxy path. Accept `Forwarded`/`X-Forwarded-*` headers only from trusted proxies, never directly from Internet clients.
- With multiple subdomains, distinguish host/origin policies and cookie domains from path matchers; path matchers do not isolate by hostname.
- `/actuator/**` may live on a separate management port or context; verify management endpoint security independently rather than assuming the application port's fallback guards all management paths.

## 18. Monitoring and Debugging Chain Order

When an endpoint misbehaves, diagnose step by step:

**Symptom: API returns HTML 302 to `/login`**
- Either the API chain didn't match, the web/fallback chain intercepted it, or the API accidentally enabled `formLogin`/an HTML entry point.
- Check the post-gateway path, `securityMatcher`, `@Order`, and configured auth mechanisms.
- Test `GET /api/orders` without a token: expect 401 in a bearer design.

**Web form login returns 403/404 or loops**
- `/login`, `POST /login`, or `/logout` is missing from the web chain; missing CSRF token; wrong form action; mismatched `loginPage` or redirect URL.
- Inspect session cookies, CSRF repository, and login success URLs per environment.

**Admin accepts a web cookie**
- A catch-all web chain matched admin first, or chains shared a repository and overly broad rules.
- Check `@Order`, `securityMatcher`, entry points, and admin-specific authentication policies.
- Test by sending only a web cookie to admin without valid Basic/JWT credentials.

**API POST returns 403 despite a valid JWT**
- Either the scope mapper did not emit `SCOPE_orders.write`, the request hit a CSRF-enabled chain, or the HTTP method isn't permitted.
- Distinguish CSRF, authorization, and signature/issuer errors; never disable all security to mask symptoms.

**403 or 404 on an unknown route**
- Verify route mappings, selected chain, and `denyAll` fallback.
- Never change fallback to `permitAll` as a “quick fix” for routing bugs.

When debugging, record only events, route templates, explicit chain identifiers, outcomes, and normalized error codes; never log passwords, cookies, raw `Authorization` headers, ID tokens/JWTs, or `SecurityContext`.

## 19. Pre-Production Security Review Checklist

Design checklist:

- [ ] `/admin/**`, `/api/**`, and `/web/**` prefixes are clearly defined; sensitive capabilities are not duplicated on weaker routes.
- [ ] `@Order` places privileged chains before catch-alls; fallback uses `denyAll` and has tests.
- [ ] `securityMatcher` scope and `authorizeExchange` method/role/scope rules are accurate without confusing the two layers.
- [ ] `/login`, `/logout`, OAuth2 callbacks, and static assets belong to the right chain when used.
- [ ] Web form login uses sessions + CSRF; CSRF is never disabled just because the API serves JSON.
- [ ] Bearer APIs truly ignore automatic cookies; JWT decoder enforces signature, issuer, expiration, audience, and scopes as required.
- [ ] Admin uses strong auth/MFA, network restrictions, and auditing; HTTP Basic appears only in demos or explicitly assessed cases.
- [ ] No in-memory `local`-profile users/passwords exist in production environments.
- [ ] Web sessions cannot authenticate API/admin; Basic admin cannot authenticate API; API JWTs do not authenticate admin.
- [ ] Tests cover anonymous, `ROLE_USER`, `ROLE_ADMIN`, API read/write scopes, CSRF pass/fail, disallowed methods, and unknown URLs.
- [ ] Integration tests cover real session cookies and real JWTs, not only `mockUser`/`mockJwt`.
- [ ] Operational routes, health, metrics, actuator, and gateway rewrites are tested separately.
- [ ] Credentials, cookies, tokens, and personal data never appear in logs or traces.
- [ ] After upgrading Spring Security or Spring Boot, re-run chain selection and 401/403/redirect tests.

## 20. Extension Exercises

**Exercise A — Chain hijacked:** Move `fallbackChain` to `@Order(1)` and run the tests. Explain why `/api/orders` is no longer handled by the JWT chain even though the bean still exists. Restore the order and prove it with tests.

**Exercise B — Mis-scoped CSRF:** Temporarily disable CSRF on `webChain` in a test environment and confirm `POST /web/actions` succeeds without a token when logged in; explain why this exposes session-cookie users to risk and restore protection.

**Exercise C — Cross-zone cookie:** Log in as `webuser` via `POST /login` with CSRF, capture the session cookie, and send it to `/admin/status` and `/api/orders` with no other credentials. Expect denial. If allowed, inspect chain matchers, repositories, and authentication.

**Exercise D — Adding a new admin route:** Add `/admin/audit/export` and `/api/admin/audit`. Configure exact permissions on both rather than relying on the word `admin` in the path for protection. Write tests proving regular users/under-scoped tokens cannot download data.

**Exercise E — Replacing Basic admin with OIDC:** Diagram separate login, MFA, callbacks, sessions, CSRF, and logout for admin. List special endpoints needed in `securityMatcher` and required test cases instead of casually copying general-user form/session settings.

**Exercise F — Dedicated management/admin port:** Place admin or management endpoints on a separate context/port. Identify where firewall, load balancer, TLS, and Spring Security policies apply, and evaluate which protections are active on each port.

Perform all exercises in an isolated environment with fake accounts/tokens, never production passwords or tokens. Success means HTTP statuses and policies hold firm, not merely finding a working credential.

## 21. Official References

- [Spring Security — WebFlux Security, Multiple Chains Support](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): selecting multiple `SecurityWebFilterChain` beans by `@Order` and matchers.
- [Spring Security — OAuth2 Resource Server WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): JWT/Opaque tokens and bearer authentication.
- [Spring Security — Cross Site Request Forgery for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF, sessions, login/logout, and state-changing requests.
- [Spring Security — Testing Authentication in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `WebTestClient`, `mockUser`, and reactive filter chains.
- [Spring Security — Testing OAuth2 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt` and checking authorities.
- [Spring Security — Testing CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `csrf()` with `WebTestClient`.
- [ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): `securityMatcher`, `authorizeExchange`, `formLogin`, `oauth2ResourceServer`, `csrf`, and HTTP Basic.

**Remember:** A WebFlux request is routed to one security chain by matcher/order before authorization checks run inside that chain. Splitting web, API, and admin makes sense whenever each group has distinct authentication and HTTP rules. Always keep specific chains at proper priority, CSRF on any UI using auto-sent credentials, bearer APIs with explicit scopes, strong admin controls, and a `denyAll` fallback for undeclared URLs.
