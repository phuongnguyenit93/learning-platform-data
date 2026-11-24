# Diagnosing 403 Caused by Missing Permissions, ROLE_ Prefix, or CSRF in Spring Security Reactive

## 1. Objectives and Scope

This lesson focuses on **HTTP 403 Forbidden** errors in **Spring WebFlux + Spring Security reactive** applications: when a request is authenticated yet lacks the required authority, when `hasRole`/`hasAuthority` configuration misuses the `ROLE_` prefix, or when a state-changing request lacks a valid **CSRF token**. These three causes often share the same client-side symptom yet require completely different fixes.

After this lesson, you should be able to:

1. Distinguish 401, 403, login redirects, and CORS/gateway errors, pinpointing the exact component that returned 403.
2. Compare `Authentication.getAuthorities()` against `authorizeExchange` and `@PreAuthorize` rules without confusing `ROLE_`, `SCOPE_`, or unprefixed strings.
3. Inspect CSRF by HTTP method, cookie/session, header/form token, and Spring Security 6 token protection—especially in SPAs.
4. Use Spring Security's `WebTestClient` to independently prove sufficient authority, insufficient authority, missing CSRF, and both satisfied.
5. Fix the root cause while preserving the **grant only the minimum required permission** principle.

Integration snippets use Spring Security 6.x/Spring Boot 3.x APIs and Java 17+. Some snippets sit inside an existing WebFlux/Spring Boot project; the pure Java simulation in Section 5 compiles standalone.

## 2. What 403 Means, and What Cannot Be Inferred

`403` indicates the request handler refused access. In Spring Security, 403 typically occurs when an `Authentication` has been established but does not satisfy authorization rules, or when `CsrfWebFilter` rejects an unsafe operation. However, the same status code can also be returned by a gateway, reverse proxy, WAF, controller, service, or custom error handler.

| Symptom | Common explanation | First check |
| --- | --- | --- |
| No token/not logged in, API returns `401` | Unauthenticated; entry point demands credentials | `Authorization` header, cookie, authentication policy |
| Not logged in, browser gets `302` to `/login` | Entry point for form login | `Location` header and matched chain |
| Valid JWT, GET returns `403` | Insufficient `GrantedAuthority` or failed access condition | `Authentication.getAuthorities()` and matcher/annotation |
| `GET` succeeds, `POST/PUT/DELETE` returns `403` for the same user | Suspect CSRF or method-dependent rule | CSRF token, HTTP method, per-method rules |
| Browser reports CORS error on `OPTIONS` preflight | Browser blocked at CORS or an upstream layer | Network: was the actual request sent? `OPTIONS` status and CORS headers |
| Every request gets 403, even unprotected paths | Wrong `SecurityWebFilterChain`, gateway, WAF, `denyAll`, or custom handler | Identify which layer generated the response before editing Spring Security |
| Service method throws `AccessDeniedException` | Method-level security or domain check denied access | `@PreAuthorize`, `@PostAuthorize`, authorization service |

**You cannot infer from status 403 alone** whether a token is wrong or a user lacks a role. A POST request with the right role can still be rejected by CSRF before route authorization runs. A GET request exempt from CSRF can still return 403 due to a `SCOPE_`/`ROLE_` mismatch. Keep all request parameters identical when comparing.

Diagnostic flow:

```text
Client sends request
   |
   v
Reverse proxy / API Gateway / WAF
   |-- 403 here? -> inspect upstream logs and policies
   v
Matching Spring Security WebFilter chain
   |
   +-- Unsafe method + invalid CSRF? -> 403, inspect token/session
   |
   +-- Invalid authentication? -> 401 / redirect / entry point error
   |
   +-- Authorization missing authority/policy check? -> 403
   |
   v
Controller -> Service / @PreAuthorize -> domain checks
   |-- Denied? -> 403 or app-defined response
   v
2xx / 4xx / other 5xx
```

Exact ordering can vary by filter chain and customizations; the diagram is for **isolating the cause**, not an absolute execution order of every `WebFilter`.

## 3. Evidence-Based Procedure to Isolate 403

### Step 1: Record an exact reproducible request

Capture **non-sensitive** fields: method, normalized path, environment, status, timestamp, correlation ID, and expected chain/route. In a controlled diagnostic channel, verify authentication type (session/JWT/Basic), authenticated principal, and granted authority **names**. **Never** put bearer tokens, session cookies, raw CSRF tokens, passwords, or `Authorization` headers into logs or tickets.

In DevTools, distinguish `OPTIONS` preflight requests from the actual `POST` request. On the command line, compare the same path (substitute your test host):

```bash
# Illustrative requests only; endpoint/credentials must match your environment.
curl -i https://localhost:8443/reports/demo
curl -i -X POST https://localhost:8443/reports/demo
```

These two commands carry no credentials, so they prove neither missing permissions nor CSRF; they only inspect chain responses and headers. When reproducing a failing request, use **valid staging test credentials** and keep every variable constant except the one under test. Never paste real tokens into third-party websites to decode or debug them.

### Step 2: Briefly enable security logs in an authorized environment

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.server.csrf: TRACE
```

Spring Security loggers help pinpoint filter chains, CSRF decisions, and authorization checks. Exact formatting and messages vary by version; never write logic depending on verbatim log text. Filter logs by request/correlation ID, restrict retention and access, and restore normal log levels once the bug is found. Diagnosing 403 **does not require** enabling TRACE across the entire app or printing raw headers.

In a Reactive app, do not rely on Servlet-style `ThreadLocal` or `SecurityContextHolder` inside Reactor callbacks. Spring Security WebFlux stores security context in **Reactor Context**; access it via `ReactiveSecurityContextHolder`.

An illustrative helper inside a Spring bean can list authority names for **internal testing**—never expose it as a public endpoint:

```java
import java.util.stream.Collectors;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> authorizedNamesForDiagnostics() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .map(auth -> auth.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .collect(Collectors.joining(",")))
            .defaultIfEmpty("(no reactive SecurityContext)");
}
```

This helper only reports **authority strings** for the current subscription; it does not determine whether a user is authorized for a specific resource. Never log principal/account names if policy forbids it; in production, prefer vetted metrics/structured events and denial counts by reason.

### Step 3: Test hypotheses one by one

1. If the error occurs only on **unsafe** methods (POST/PUT/PATCH/DELETE), retry as the same user with a **valid CSRF token in the same session**. If 403 disappears, the cause is CSRF; if 403 persists, inspect authorities/routes and domain policies.
2. If GET also fails, inspect the selected matcher, `Authentication`, and exact `GrantedAuthority` list, including case sensitivity and prefixes.
3. With JWTs, first verify the token was **validly verified**; then separate JWT `scope` mapped to `SCOPE_*` from business roles mapped to `ROLE_*`. Decoding a JWT payload without verifying its signature is never grounds for granting access.
4. If route authorization passes yet 403 still occurs, examine `@PreAuthorize`, `@PostAuthorize`, downstream service/gateway security, and business ownership checks. Do not alter policies before knowing which layer denied access.
5. If it fails only in browsers, check CORS preflight, cookies/sessions, `SameSite`, `Origin`, and how JavaScript attaches the CSRF header; Postman/curl behave differently from browsers and cannot rule out browser issues.

## 4. `GrantedAuthority`, `hasAuthority`, and the `ROLE_` Prefix

### 4.1. Roles in Spring Security Are Authorities Following a Naming Convention

`Authentication.getAuthorities()` returns a collection of `GrantedAuthority`. Each `GrantedAuthority.getAuthority()` value is a string, such as:

```text
ROLE_ADMIN
ROLE_REPORT_VIEWER
SCOPE_reports.read
ORDER_APPROVE
```

- `hasAuthority("ROLE_ADMIN")` compares directly against `"ROLE_ADMIN"`.
- `hasRole("ADMIN")` is shorthand that looks for `"ROLE_ADMIN"` by default. **Pass `ADMIN` to `hasRole`, not `ROLE_ADMIN`.**
- `hasAuthority("ADMIN")` requires the exact string `"ADMIN"`; it does not prepend `ROLE_`.
- `hasAuthority("SCOPE_reports.read")` checks a JWT scope using the default OAuth2 mapping.
- Authority comparison is sensitive to case, dots, hyphens, and prefixes; `role_admin`, `ROLE_ADMIN`, and `ADMIN` are three distinct values.

Decision table under the default prefix convention:

| Present authorities | Rule | Outcome | Explanation |
| --- | --- | --- | --- |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Allow | Spring prepends `ROLE_` when matching |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | Allow | Exact match |
| `ROLE_ADMIN` | `hasAuthority("ADMIN")` | Deny | Rule lacks the prefix |
| `ADMIN` | `hasRole("ADMIN")` | Deny | Granted authority lacks `ROLE_` |
| `SCOPE_admin` | `hasRole("ADMIN")` | Deny | OAuth2 scopes do not automatically become roles |
| `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` | Allow | Exact mapped scope name |
| `ROLE_REPORT_VIEWER` | `hasRole("report_viewer")` | Deny | Case mismatch |

`hasRole("ROLE_ADMIN")` **is not a fix**: many Spring Security APIs/versions reject a role parameter starting with `ROLE_` rather than silently treating it as an authority. To match an already-prefixed authority, use `hasAuthority("ROLE_ADMIN")`.

If the app intentionally customizes the role prefix via a supported mechanism (such as `GrantedAuthorityDefaults` for method security), verify that the configuration applies to that exact authorization layer. Never assume changing a prefix in a converter automatically alters every `hasRole` across filter chains and method annotations.

### 4.2. Reactive `SecurityWebFilterChain` Example

The configuration below requires role `VIEWER` for GET and `EDITOR` for POST; CSRF remains enabled. This is a Java configuration for an **existing Spring Boot WebFlux application**:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReportSecurityConfig {
    @Bean
    SecurityWebFilterChain reportSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/reports/demo")
                    .hasRole("VIEWER")
                .pathMatchers(HttpMethod.POST, "/reports/demo")
                    .hasRole("EDITOR")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Key takeaways:

- `hasRole("VIEWER")` requires `ROLE_VIEWER`; `hasRole("EDITOR")` requires `ROLE_EDITOR`.
- Each HTTP method has its own policy. A `PUT /reports/demo` request hits `denyAll()` because it matches neither GET nor POST, even if the user holds `ROLE_EDITOR`.
- `httpBasic` enables HTTP Basic authentication once a user store is configured; **CSRF still applies** to unsafe methods in this setup because browsers can send Basic credentials automatically.
- `anyExchange().denyAll()` illustrates a strict default policy. Never change it to `permitAll()` to resolve a 403.
- If the app defines multiple `SecurityWebFilterChain` beans via `securityMatcher`/`@Order`, confirm which chain actually receives the path. Rules in another chain cannot help a request matched by the current chain.
- Spring WebFlux uses `ServerHttpSecurity` + `SecurityWebFilterChain`. Never copy **Servlet** `HttpSecurity`/`SecurityFilterChain`/`authorizeHttpRequests` expecting equivalent behavior in WebFlux.

### 4.3. Common Mismatch Source During Username/Password Authentication

Suppose an app grants a user `["ADMIN"]` while the rule uses `hasRole("ADMIN")`. Authentication **succeeds**, yet authorization returns **403** because Spring expects `ROLE_ADMIN`. If the domain genuinely uses role conventions, update the trusted mapper to emit `ROLE_ADMIN`, or change the rule to `hasAuthority("ADMIN")` if literal authorities were intended by design.

Never "fix" this by adding every role to every account, changing the entire chain to `authenticated()`, or adding an "admin fallback". Fix one side consistently based on the **canonical authority contract** and test other endpoints to prevent over-privileging.

## 5. Self-Contained Java 17 Exercise: Observing the Root Cause of a Mismatch

This example **simulates string matching**, uses no Spring libraries, and does not replace real server testing. Save as `AuthorityDiagnosticDemo.java`:

```java
import java.util.Set;

public final class AuthorityDiagnosticDemo {
    static boolean hasAuthority(Set<String> actual, String required) {
        return actual.contains(required);
    }

    static boolean hasRole(Set<String> actual, String role) {
        if (role.startsWith("ROLE_")) {
            throw new IllegalArgumentException("pass role without ROLE_ prefix");
        }
        return hasAuthority(actual, "ROLE_" + role);
    }

    public static void main(String[] args) {
        Set<String> user = Set.of(
                "ADMIN", "ROLE_VIEWER", "SCOPE_reports.read");

        System.out.println("hasRole ADMIN: " + hasRole(user, "ADMIN"));
        System.out.println("hasAuthority ADMIN: "
                + hasAuthority(user, "ADMIN"));
        System.out.println("hasRole VIEWER: " + hasRole(user, "VIEWER"));
        System.out.println("hasRole reports.read: "
                + hasRole(user, "reports.read"));
        System.out.println("hasAuthority SCOPE_reports.read: "
                + hasAuthority(user, "SCOPE_reports.read"));
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 AuthorityDiagnosticDemo.java
java AuthorityDiagnosticDemo
```

Exact stdout:

```text
hasRole ADMIN: false
hasAuthority ADMIN: true
hasRole VIEWER: true
hasRole reports.read: false
hasAuthority SCOPE_reports.read: true
```

Takeaway: **having an authority does not mean every similarly named rule will match**. When investigating 403, compare the exact values returned by `getAuthorities()` against what the rule expects, including prefixes.

## 6. JWT OAuth2 Resource Server: `SCOPE_` Differs from `ROLE_`

In a WebFlux resource server validating JWTs, Spring Security by default maps the `scope` or `scp` claim to authorities prefixed with `SCOPE_`. For example, a valid token with claims:

```json
{
  "iss": "https://id.example.org/tenant-a",
  "sub": "user-42",
  "aud": ["reports-api"],
  "scope": "reports.read reports.write"
}
```

Once the token is **successfully verified by the decoder**, those scopes typically become:

```text
SCOPE_reports.read
SCOPE_reports.write
```

They **do not automatically become** `ROLE_REPORTS_READ` or `ROLE_ADMIN`. Therefore:

```java
// Illustrative configuration snippet for a WebFlux JWT resource server.
// This is a separate SecurityWebFilterChain, not combined with
// ReportSecurityConfig from the Basic/CSRF example.
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers(HttpMethod.GET, "/api/reports/**")
                .hasAuthority("SCOPE_reports.read")
            .pathMatchers(HttpMethod.POST, "/api/reports/**")
                .hasAuthority("SCOPE_reports.write")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}
```

This requires the same imports as `ReportSecurityConfig`, plus `spring-boot-starter-oauth2-resource-server` and issuer/JWK Set configuration. Do not drop this method into a codebase that already defines a `SecurityWebFilterChain` with overlapping matchers; clarify chain scopes first.

If a rule specifies `hasRole("REPORTS_READ")` when the token only grants `SCOPE_reports.read`, a valid request still receives 403. Fix the **rule to match your authorization model** (use `SCOPE_` for OAuth2 scopes) or, if business roles are genuinely needed, build a converter from a **trusted role claim** with a consistent allowlist and prefix everywhere.

**Never map arbitrary scopes into `ROLE_ADMIN`.** Only roles issued by a trusted issuer under contract—after signature verification and checking `iss`, `aud`, `exp`, and `nbf`—should become authorities, still applying least privilege. A token payload claiming `"roles":["ADMIN"]` with an invalid signature is zero evidence of admin privilege.

In WebFlux tests, `mockJwt().authorities(new SimpleGrantedAuthority("SCOPE_reports.read"))` isolates **authorization behavior**. It does not prove the decoder will accept production tokens; separate integration tests are required for JWT signature/issuer/audience and converters.

## 7. CSRF: Why 403 Happens Even When the User Has Full Permissions

### 7.1. Why CSRF Checks Differ from Authorization

**Cross-Site Request Forgery** occurs when a browser automatically attaches a logged-in user's credentials (typically session cookies or HTTP Basic/similar auto-sent mechanisms) to a request triggered by another site. An attacker does not need to read the response to cause a state-changing side effect unless the server verifies proof that another site cannot easily obtain.

Spring Security WebFlux **enables CSRF protection by default**. Safe methods like GET, HEAD, OPTIONS, and TRACE are normally exempt from CSRF checks; other methods such as POST/PUT/PATCH/DELETE require a valid token unless configured otherwise via matchers. **GET must never mutate state** if you rely on the safe-method exemption.

Suppose user `alice` has `ROLE_EDITOR`, sends a POST, and passes the role requirement:

```text
POST /reports/demo
Cookie: SESSION=...
X-CSRF-TOKEN: (missing)
```

Even with the right role, `CsrfWebFilter` can return 403 due to the missing token. Adding `ROLE_EDITOR` again will not help. Conversely, with a valid CSRF token yet only `ROLE_VIEWER`, the POST still returns 403 due to insufficient role. **Both conditions must hold simultaneously**.

### 7.2. CSRF Repositories and Header Names in WebFlux

By default, Spring Security reactive stores expected CSRF tokens in `WebSession` using `WebSessionServerCsrfTokenRepository`; the default header name is typically `X-CSRF-TOKEN` and form parameter `_csrf`. You must send the token issued for **the active session** in the right form field or header. A token copied from another tab, browser, or session will fail validation.

When using `CookieServerCsrfTokenRepository`, the default cookie name is `XSRF-TOKEN` and the server reads the token from the `X-XSRF-TOKEN` header (or `_csrf` parameter). Configuration allowing JavaScript clients to read the cookie:

```java
// Snippet added to ServerHttpSecurity builder for an SPA application
.csrf(csrf -> csrf.csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
```

Import: `org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository`. Choose `withHttpOnlyFalse()` only when JavaScript **must read the cookie** to send the header; otherwise keep `HttpOnly` to minimize exposure. The `XSRF-TOKEN` cookie is an anti-CSRF token, **not** a login cookie; the application still needs proper session, `SameSite`, `Secure`, and CORS policies.

**Spring Security 6 note:** by default, `XorServerCsrfTokenRequestAttributeHandler` protects emitted tokens to mitigate BREACH attacks. For SPAs reading a *raw* token from a cookie and echoing it in a header, verify how the request handler in your **exact WebFlux version** decodes/validates tokens; do not assume a Servlet example using `CsrfTokenRequestHandler` applies verbatim to Reactor. WebFlux documentation describes `ServerCsrfTokenRequestAttributeHandler` when simpler compatibility handling is genuinely required, though removing token masking must be evaluated against BREACH protection. Before swapping handlers, run a token-fetch → POST round trip within the same session and compare raw vs. masked tokens under your real configuration.

### 7.3. HTML Forms, SPAs, and Session Lifecycle

- **Server-rendered forms:** keep Spring Security's issued token inside the hidden `_csrf` field on POST forms; Thymeleaf integration generates the CSRF field automatically when configured properly. GET forms do not need a token because they must not mutate state.
- **Cookie-based SPAs:** obtain the session's issued token, read the cookie only if designed to do so, and send the matching header on state-changing requests; configure CORS/`SameSite` properly and never place tokens in URLs or logs. Verify Spring Security 6's XOR handler behavior.
- **Login/logout and session timeout:** CSRF tokens can be invalidated or become stale when the session rotates. Clients must fetch the fresh token afterwards; requests reusing an old token can receive 403 even though the user is logged in.
- **HTTP clients dropping cookies:** with `WebSession`-backed repositories, sending a token without the session cookie leaves the server without an expected token to compare against. Always inspect cookie jars and `Set-Cookie` responses.
- **HTTPS and reverse proxies:** `Secure`, `SameSite`, and cookie domain/path govern whether browsers attach cookies; misconfigured proxy forwarding can skew origin/host checks.
- **Do not abuse CORS as a fix:** CORS governs cross-origin browser access; it does not replace CSRF tokens. Enabling wildcard origins with credentials or disabling CSRF are separate security changes, not diagnostic steps.

### 7.4. Can CSRF Be Disabled for Bearer APIs?

When an API is **purely bearer-token-based**, never relies on browser auto-sent credentials, is stateless by design, and **does not need CSRF** for that exact endpoint group—for instance, a resource server accepting only explicit bearer headers—CSRF may be scoped via an appropriate `securityMatcher`/matcher after proper design and verification.

However, **never disable CSRF across the entire application** merely because endpoints return JSON or paths start with `/api`: one app can serve both cookie-session/form login and APIs. Never reach for `csrf.disable()` as your first reaction to a 403.

If a security review genuinely concludes CSRF should be disabled on a dedicated bearer-only API chain, prove that no session/Basic/cookie auto-sent authentication can reach endpoints in that chain, verify chain ordering, and keep authorization strict. Remaining session/browser chains must still enforce CSRF. **Intentional CSRF scoping** is very different from **disabling authentication or broadening permissions**.

## 8. Testable Integration Example: Distinguishing `ROLE_` and CSRF with WebTestClient

This fixture fits inside **an existing Spring Boot 3.x WebFlux project**. It uses three Java files in package `demo` with no real production endpoints. It demonstrates four distinct outcomes: GET with right role succeeds; GET with unprefixed authority gets 403; POST with role but no CSRF gets 403; POST with both role and CSRF succeeds.

Dependencies in `build.gradle` using Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**File 1:** `src/main/java/demo/ReportSecurityConfig.java` — same content as Section 4.2. In this fixture, declare only **that single** security chain; do not add Section 6's JWT config into the same test.

**File 2:** `src/main/java/demo/ReportEndpoint.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportEndpoint {
    @GetMapping("/reports/demo")
    public Mono<String> read() {
        return Mono.just("read-ok");
    }

    @PostMapping("/reports/demo")
    public Mono<String> write() {
        return Mono.just("write-ok");
    }
}
```

**File 3:** `src/test/java/demo/ReportAccessTest.java`:

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(controllers = ReportEndpoint.class)
@Import(ReportSecurityConfig.class)
class ReportAccessTest {
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
    void viewerRoleCanGet() {
        client.mutateWith(mockUser("alice").roles("VIEWER"))
                .get().uri("/reports/demo")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("read-ok");
    }

    @Test
    void unprefixedAuthorityCannotSatisfyHasRole() {
        client.mutateWith(mockUser("alice").authorities(
                        new SimpleGrantedAuthority("VIEWER")))
                .get().uri("/reports/demo")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorWithoutCsrfCannotPost() {
        client.mutateWith(mockUser("alice").roles("EDITOR"))
                .post().uri("/reports/demo")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorWithCsrfCanPost() {
        client.mutateWith(mockUser("alice").roles("EDITOR"))
                .mutateWith(csrf())
                .post().uri("/reports/demo")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("write-ok");
    }

    @Test
    void viewerWithCsrfStillCannotPost() {
        client.mutateWith(mockUser("alice").roles("VIEWER"))
                .mutateWith(csrf())
                .post().uri("/reports/demo")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Note on static imports: to avoid broken line wraps when copying, you can write three single-line imports in Java:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
```

**When running for real, use those three contiguous single-line imports instead of the wrapped pairs in the test block** if your formatter/tool does not support wrapped import lines. Java allows whitespace before `.`; both forms represent the same import, though single lines are easier to copy.

Run the tests using **that project's** Gradle wrapper:

```bash
./gradlew test --tests demo.ReportAccessTest
```

Or on Windows:

```powershell
.\gradlew.bat test --tests demo.ReportAccessTest
```

The assertions express the expected outcomes. There is no fixed stdout independent of Gradle, JDK, test framework, and project configuration; when all tests pass, Gradle typically reports `BUILD SUCCESSFUL`. `mockUser` and `csrf()` are test utilities only; they supply no real production users, secrets, or tokens. This test verifies **authorization/CSRF inside the mocked chain**, and does not replace integration tests for an IdP, JWT signatures, browser cookies, or reverse proxies.

## 9. Why 403 Still Happens Even When Tests Grant the Expected Role

### 9.1. Method-Level Security Is a Separate Decision Layer

If `@EnableReactiveMethodSecurity` is active, a method can carry annotations like:

```java
// Example method inside a Spring-managed service.
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Mono<Report> loadReport(String id) {
    return reportRepository.findById(id);
}
```

Allowing the request through `authorizeExchange` to reach the controller **does not remove** the `@PreAuthorize` check on the service method. A token holding `ROLE_VIEWER` without `SCOPE_reports.read` can still be rejected in the service.

To use method security with Reactor, ensure methods receive and enforce authorization through the reactive security context. Never replace `Mono`/`Flux` with `block()` on a request thread, never spawn a detached `subscribe()` outside the handler lifecycle, and never assume Servlet `SecurityContextHolder` contains the WebFlux user. Also verify method-security proxying: internal `this.securedMethod()` calls inside the same bean typically bypass the AOP proxy—which is a **bypass risk**, not a fix for 403.

If the issue appeared after migrating from Servlet to WebFlux, audit both `@EnableMethodSecurity`/`@EnableReactiveMethodSecurity` and reactive configuration classes. Never attempt to keep `HttpSecurity` or `OncePerRequestFilter` as WebFlux policies.

### 9.2. Matchers and Multi-Chain Ordering

Common misconfigurations:

```java
// Wrong order: broad rule matches first, specific rule never runs.
.authorizeExchange(ex -> ex
    .pathMatchers("/**").authenticated()
    .pathMatchers("/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll())
```

The broad `/**` rule prevents `/admin/**` from ever taking effect. In this example `authenticated()` can also be **overly permissive**, not just cause 403. Rule of thumb: place specific routes/methods first and wildcards last, and add tests ensuring sensitive endpoints are never accidentally relaxed.

With multiple chains:

```text
Chain A: securityMatcher("/api/**")       -> JWT + SCOPE_...
Chain B: securityMatcher("/**")           -> session + CSRF + ROLE_...
```

If `@Order` or matchers differ from expectations, `/api/reports` can enter Chain B, causing unexpected CSRF or authority checks. Avoid tweaking individual rules before confirming which chain actually matched. When requests pass through a gateway that rewrites paths or context paths, compare **the path seen by Spring WebFlux**, not merely the browser URL.

### 9.3. Valid Authentication Whose Authorities Were Lost During Conversion

With JWTs, the `Authentication` produced by the reactive JWT converter may contain `SCOPE_reports.read`; if you wrote a custom converter returning an empty authority list, the token may authenticate yet fail authorization with 403. With sessions or Basic auth, the user-details loader may return unprefixed or mis-mapped roles.

Cause lookup table:

| What to inspect | Observed result | What to fix |
| --- | --- | --- |
| JWT claim `scope=reports.read` | `getAuthorities=[]` | Inspect converter/claim name/decoder; never remove validation |
| JWT authorities `SCOPE_reports.read` | Rule `hasRole("REPORTS_READ")` | Standardize on scope authorization or an approved role mapping |
| UserDetails authorities `VIEWER` | Rule `hasRole("VIEWER")` | Map to `ROLE_VIEWER` or use exact authority if intended by design |
| Method `@PreAuthorize` needs `SCOPE_edit` | Route only requires `ROLE_EDITOR` | Review two-layer policy; never grant extra scopes arbitrarily |
| POST has permission yet lacks CSRF | Rejected by `CsrfWebFilter` | Fix token/session/header or proper CSRF setup |
| Browser fails CORS before POST | Actual request never reaches controller | Fix CORS/origins/credentials; do not change roles blindly |

## 10. Detecting Whether CSRF Is the Culprit Using Tests and Logs

A practical way to remove ambiguity is to **test the exact same user and endpoint, varying only CSRF**:

```text
Authenticated = ROLE_EDITOR, request POST /reports/demo
  A. Without CSRF -> 403 (expected)
  B. With valid CSRF in same session -> 200 (expected)

Authenticated = ROLE_VIEWER, request POST /reports/demo
  C. With valid CSRF -> 403 (expected)

Authenticated = ROLE_VIEWER, request GET /reports/demo
  D. CSRF not required for GET -> 200 (expected)
```

In `WebTestClient` tests, `mutateWith(csrf())` supplies a valid test CSRF token. If B still returns 403, check roles, URL/method, custom matchers, method security, and the controller. If A unexpectedly returns 200, check whether CSRF was disabled on the chain or excluded by a matcher. If C returns 200, the POST rule is likely too broad or not applied.

In real browser apps, verify:

1. The CSRF-token fetch executes under an active session and the `Mono<CsrfToken>` is actually subscribed/materialized rather than created unsubscribed.
2. The client sends the **exact header name expected by the repository** in the format accepted by the request handler.
3. Both the session cookie and CSRF token belong to the same user/session and are sent with valid domain/path/`SameSite`/`Secure`.
4. After login, logout, or session renewal, the client fetches the new CSRF token when the old one becomes invalid.
5. CSRF cookies are readable by JavaScript only when designed to be; never drop `HttpOnly` on the session cookie, and never confuse a CSRF token with a JWT.
6. CORS preflight is handled properly if the SPA is cross-origin. Blocked `OPTIONS` is not necessarily CSRF on `POST`.
7. Never log full cookies or CSRF tokens "for comparison"—rely on state/version metadata and verification outcomes instead of printing secrets.

## 11. Root-Cause Remediation Patterns

### Case A — Authenticated account missing `ROLE_`

**Symptom:** `GET /reports/demo` returns 403; diagnostics show `authorities=[VIEWER]`, while configuration uses `hasRole("VIEWER")`.

**Cause:** the rule expects `ROLE_VIEWER`, whereas the mapper emitted `VIEWER`.

**Fix:** decide whether the data contract uses `ROLE_`-prefixed roles or literal authorities; fix the mapper (in the user store/IdP) or switch to `hasAuthority("VIEWER")` if literal authorities are intentional. Add GET tests with and without the exact authority name, and verify other roles are not granted accidentally.

### Case B — JWT scopes checked as roles

**Symptom:** valid JWT has `scope=reports.read`, actual authorities contain `SCOPE_reports.read`, yet the rule uses `hasRole("REPORTS_READ")`.

**Cause:** OAuth scope conventions and Spring Security role conventions were mixed up.

**Fix:** use `hasAuthority("SCOPE_reports.read")` or `hasScope("reports.read")` depending on your WebFlux version. If business roles are genuinely needed, map them from a trusted, policy-validated role claim—**never** convert arbitrary scopes into admin roles.

### Case C — POST has the right role yet lacks CSRF

**Symptom:** GET succeeds; POST returns 403 only from the SPA/browser or from tools omitting a CSRF token.

**Cause:** unsafe HTTP method, missing or session-mismatched token, or client/repository/handler mismatch.

**Fix:** have the server issue the token, pass it via the proper form field or header, preserve session cookies, align SPA integration with Spring Security 6, and re-test using `WebTestClient.mutateWith(csrf())` plus browser integration tests. Never use `permitAll` or disable CSRF globally.

### Case D — 403 persists after fixing roles and CSRF

**Symptom:** isolated role and CSRF tests both pass, yet live requests still return 403.

**Possible causes:** `@PreAuthorize` method security, controller/domain ACLs, rewritten paths, multiple filter chains, custom access-denied handlers, gateway/WAF rules, or CORS preflight.

**Fix:** identify the status-producing layer via request IDs/logs, reproduce layer by layer, and compare path, method, principal, and authorities at that exact point. Never relax permissions for a "quick test"—that can create a vulnerability far worse than 403.

## 12. Anti-Patterns to Avoid When Debugging 403

| Wrong approach | Why it is wrong | Proper fix |
| --- | --- | --- |
| Setting `anyExchange().permitAll()` to see if the request works | Can bypass real authorization | Test with `mockUser` and specific scopes; keep deny-by-default |
| Replacing all `hasRole` rules with `authenticated()` | Removes business permission requirements | Standardize authorities and fix rules intentionally |
| Granting `ROLE_ADMIN` to the failing user | Violates least privilege | Determine which exact role is actually permitted |
| Changing `hasRole("ADMIN")` to `hasRole("ROLE_ADMIN")` | Misuses the API contract | Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` |
| Trusting unverified JWT claims | Attackers can forge roles/scopes in payloads | Verify signature, issuer, audience, and timestamps |
| Disabling CSRF on a cookie-session browser app | Opens a CSRF attack surface | Issue tokens and send matching headers/forms with the session |
| Enabling CORS without sending a CSRF token | CORS does not prove intentional user action | Handle CORS and CSRF as two separate mechanisms |
| Copying Servlet `HttpSecurity` config into WebFlux | Rules do not apply to the reactive chain | Use `ServerHttpSecurity` and `SecurityWebFilterChain` |
| Reading `SecurityContextHolder` inside async callbacks | Confuses ThreadLocal with reactive context | Use `ReactiveSecurityContextHolder` inside the subscription |
| Logging raw JWTs/cookies/CSRF tokens under DEBUG | Leaks authentication secrets | Log only safe diagnostic signals and failure categories |
| Testing only the 200 happy path | Leaves role/CSRF enforcement unverified | Include negative 403 tests for both missing role and missing CSRF |
| Assuming every 403 comes from Spring | Misses gateway/WAF/ACL rejections | Confirm which layer emitted the response via request ID |

## 13. Verification Checklist and Key Takeaways

When encountering a new `403`, work through this order:

1. **Identify the source of 403:** app, gateway, WAF, method security, or business logic; record method/path/correlation ID and check redirects/`OPTIONS`.
2. **Confirm authentication:** whether the request uses session, Basic, or bearer JWT; never confuse `401` with `403`.
3. **Compare exact authorities:** whether `getAuthorities()` holds `ROLE_*`, `SCOPE_*`, or plain strings; what do `hasRole`/`hasAuthority`/`@PreAuthorize` expect?
4. **Check HTTP method and matchers:** GET vs. POST differences, which rule matched, multiple chains, and whether `denyAll` caught the request unexpectedly.
5. **If unsafe HTTP method:** check valid CSRF token for the **same session**, header/form field names, cookies, Spring Security 6 XOR handler behavior, and login/logout lifecycle.
6. **Run isolated tests:** mock users with and without the role; same POST with and without `csrf()`; test both positive and negative cases.
7. **Fix the exact broken layer:** converter, user store, route policy, CSRF integration, method security, or upstream proxy. Never broaden permissions beyond requirements.
8. **Run regression checks:** verify public endpoints, 401/redirects, 403 for under-privileged users, 200 for authorized users, browser-session CSRF, JWT scopes, and concurrent requests.

Most importantly: **a 403 is the result of a specific check failing**. To fix it, you must know exactly which check failed. `ROLE_`, `SCOPE_`, CSRF, and multi-layer policies are separate mechanisms; fixing the right mechanism ensures both valid access and least privilege.

## Official Documentation

- Spring Security — Authorize ServerHttpRequest (WebFlux): https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — CSRF in WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — Testing WebTestClient authentication: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security — WebTestClient setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — Testing OAuth2/JWT: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
