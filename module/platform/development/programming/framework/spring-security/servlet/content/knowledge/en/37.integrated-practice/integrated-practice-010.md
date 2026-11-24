# Completing the Test Matrix and Reviewing Deployment Configuration for Spring Security Servlet

> **Scope:** integrated practice for **Spring Security Servlet** applications on Java 17+, Spring Boot 3, Spring Security 6, Spring MVC, JUnit 5, and MockMvc. The goal is not merely getting a few tests to PASS, but proving **every HTTP surface selects the right SecurityFilterChain, authenticates properly, enforces authorization, and preserves defenses in real deployments**.
>
> Spring code snippets belong inside a project with proper dependencies, an `@SpringBootApplication` entry point, and environment config. The standalone Java 17 program in Section 5 runs independently. Environment examples use the domain `example.test`; this is an illustrative placeholder, not a real IdP server. **Never copy sample passwords/secrets, issuers, or origins into production.**

## 1. Acceptance Deliverables: Evidence, Not Just Configuration

The expected output is a testing and deployment dossier containing:

1. **Resource and security boundary map:** URL, HTTP method, authentication mode, session/cookie, authority/role, owner/tenant, and data sensitivity.
2. **Traceable test matrix:** case ID, inputs, identity, CSRF context, expected HTTP status/body/headers, test level, evidence, and owner.
3. **Automated tests:** unit, Spring Security Test/MockMvc, repository/service authorization, integration with real JWT decoder/session/DB where needed, and browser end-to-end.
4. **Deployment configuration review:** filter chain ordering, TLS/proxy, CORS, CSRF, sessions, cookies, headers, secret management, monitoring, dependency management, and container config.
5. **Release/rollback criteria:** which severe failures block deployment, who approves, post-rollout checks, and rollback paths.

A passing `GET /health` returning 200 does not prove `POST /transfer` is CSRF-protected or `GET /users/{id}` checks ownership. A passing `with(jwt())` test does not prove the JWT decoder verifies signatures. Conversely, a 403 test must also distinguish **CSRF** failures from **authorization** denials. The matrix must capture every layer accurately.

**Acceptance rule:** missing test coverage for a critical security boundary means *insufficient evidence*, never an automatic PASS.

## 2. Mapping the System Before Writing the Matrix

Suppose an application has two HTTP groups:

- **API:** `/api/**` uses `Authorization: Bearer <token>`, Resource Server validates JWTs, and never uses sessions/cookies as API credentials. Individual endpoints require scopes and ownership.
- **Web:** `/web/**`, `/admin/**`, and the login page use form login + session cookies; state-changing requests require a CSRF token.
- **Public:** `/api/public/ping`, `/login`, static assets.
- **Operations/management:** health/readiness, metrics, management endpoints; never expose all actuator endpoints publicly by default.
- **Infrastructure:** TLS termination, reverse proxy/load balancer, secrets, external identity provider/JWKS, session store, database.

This is an **illustrative model**, not a mandate that every app needs two chains or JWTs. If a system uses only form login, drop unrelated Bearer cases and add tests for the actual authentication mechanism. If a system uses HTTP Basic where browsers auto-send credentials, **never disable CSRF by default** just because endpoints start with `/api`.

### 2.1. Resource Inventory Table

| Resource | Method | Allowed Caller | Authentication | CSRF/Session | Data to Protect |
| --- | --- | --- | --- | --- | --- |
| `/api/public/ping` | GET | Anonymous | Not required | Stateless API | Contains no secrets |
| `/api/me` | GET | Scope `profile.read` | JWT Bearer | Does not rely on cookies | Caller's own profile only |
| `/api/me/update` | POST | Scope `profile.write` + owner rule | JWT Bearer | Rejects cookies in sample | Caller's own account update only |
| `/web/account` | GET | Logged-in user | HttpSession | Session cookie | Never expose other users' accounts |
| `/web/settings` | POST | Logged-in user | HttpSession | **CSRF required** | State-changing action |
| `/admin/report` | GET | Role ADMIN | HttpSession | Session cookie | Administrative data |
| `/login` | GET/POST | Anonymous or logged in | Form authentication | CSRF protects form POST | Password and session |
| `/logout` | POST | Logged-in user | Session + cookie | **CSRF required** | Invalidates current session |
| `/assets/**` | GET | Anonymous | Not required | Non-mutating | Static files, security headers |
| `/actuator/health` | GET | Per ops policy | Dedicated config | Endpoint-dependent | Limit system details |

This table is a **testing contract**. For each row, also record: HTTP host/port, servlet context, chain name, intended `AuthenticationEntryPoint`, service method permissions, data-protection criteria, and log redaction.

**Distinguish three decision points:**
1. `securityMatcher(...)` determines **which SecurityFilterChain is selected**.
2. Authentication filters determine whether credentials are verified.
3. `authorizeHttpRequests(...)` and method/domain authorization decide whether the user may operate on the resource.

Testing only Step 3 with mock users can miss the fact that real requests never enter any chain.

## 3. Designing a Traceable Test Matrix

Avoid overly generic rows like "test login, test logout". Each test case needs metadata:

| Column | Content to Record |
| --- | --- |
| `ID` | E.g. `API-AUTH-001`; unique and stable |
| `Feature/Threat` | JWT, CSRF, IDOR, CORS, session fixation, etc. |
| `Endpoint + method` | Exact URL and HTTP method |
| `Authentication context` | Anonymous, Basic, form login, valid/invalid JWT, remember-me |
| `Authority/ownership` | Role/scope and resource owner/tenant |
| `Request state` | CSRF token, cookies, origin, request body, session |
| `Expected` | Status, headers, body, side effects, and audit |
| `Level` | Unit, MockMvc, integration, E2E/browser, deployment probe |
| `Evidence` | Test method/run ID, redacted artifact, deployment version |
| `Owner + status` | Responsible owner, PASS/FAIL/BLOCKED/NOT_RUN |
| `Risk/priority` | Release blocker or warning to address |

The matrix should be rigorous enough that **someone else can re-run it without asking the author**. In particular, `401/403/302` expectations depend on the application type and authentication entry point; never force one answer across every project.

### 3.1. HTTP Matrix: Authentication and Authorization

Below are the **expectations for the sample architecture** in Section 2 and the configuration in Section 7:

| ID | Request and Identity | Expected Outcome | What It Proves |
| --- | --- | --- | --- |
| AUTH-01 | Anonymous `GET /api/public/ping` | 200, `pong` | Public API still traverses the right chain |
| AUTH-02 | Anonymous `GET /api/me` | 401, `WWW-Authenticate: Bearer` | API entry point, no login redirect |
| AUTH-03 | Tampered Bearer token signature to `GET /api/me` | 401 | Decoder rejects forged tokens |
| AUTH-04 | Expired JWT | 401 | Expiry enforced |
| AUTH-05 | JWT with wrong `iss`/`aud` per policy | 401 | Issuer/audience validators active |
| AUTH-06 | Valid JWT missing `profile.read` | 403 | Authentication succeeded, missing authority |
| AUTH-07 | Valid JWT with `profile.read` scope | 200, caller's data only | Authority and data ownership |
| AUTH-08 | Valid JWT with `profile.write` scope, valid POST schema | 2xx, updates caller only | Write permission, input validation, and audit |
| AUTH-09 | JWT with only `profile.read`, POST update | 403 | Read scope does not grant write scope |
| AUTH-10 | Valid JWT where requester spoofs another `userId` | 403/404 per policy, no cross-user read/write | Object-level authorization / IDOR |
| AUTH-11 | Anonymous `GET /web/account` | 302 to login | Web chain uses form authentication |
| AUTH-12 | Alice session `GET /web/account` | 200, Alice's account | Session authentication |
| AUTH-13 | USER session `GET /admin/report` | 403 | Role gate |
| AUTH-14 | ADMIN session `GET /admin/report` | 200, matching tenant/data scope | Role + business authorization |
| AUTH-15 | Anonymous `GET /apiary` | Web policy, not misrouted as `/api/**` | Matcher boundary |

In AUTH-10, returning 403 vs. 404 is a **design policy**: some systems return 404 to curb enumeration, while strictly **returning no data and mutating no state**. Never misuse status codes to hide that a service skipped owner checks altogether.

### 3.2. CSRF, CORS, Cookie, and Session Matrix

| ID | Scenario | Expected Outcome |
| --- | --- | --- |
| WEB-CSRF-01 | Session user POST `/web/settings` **without CSRF** | 403, no data modified |
| WEB-CSRF-02 | Session user POST `/web/settings` **with valid CSRF** | 2xx when authorized and input valid |
| WEB-CSRF-03 | POST `/logout` missing CSRF | 403, session stays logged in |
| WEB-CSRF-04 | POST `/logout` with CSRF | Current session invalidated, cookie/remember-me handled per config |
| SESS-01 | Successful login from existing session | Session ID rotates per session-fixation policy |
| SESS-02 | Two Alice sessions, one-session cap | Matches expire-old or prevent-new policy |
| SESS-03 | Logout on one browser | Never claims all other browsers were logged out |
| SESS-04 | Remember-me without active session | Auto-authenticates only if token valid and policy allows |
| SESS-05 | Revoked remember-me token (persistent mode) | Cannot re-authenticate with old token series |
| CORS-01 | Allowed origin sends preflight with Authorization header | Preflight succeeds with expected allow-origin/method/headers |
| CORS-02 | Disallowed origin | No CORS permission granted; preflight rejected per config |
| CORS-03 | Cross-site request with web cookie | CORS does not replace CSRF; unsafe action blocked without token |
| COOKIE-01 | Session cookie over HTTPS | `Secure`, `HttpOnly`, `SameSite`, and path/domain per policy |
| COOKIE-02 | Client mutates `JSESSIONID` | Does not inherit authenticated session |
| COOKIE-03 | Logout deletes cookie | Uses matching path/domain; tested in real browser |

If an API **only** accepts Bearer tokens from client-set `Authorization` headers and uses no cookies/Basic, it can run statelessly with CSRF disabled on the API chain *after verifying the threat model*. Whenever credentials are auto-sent by browsers, evaluate CSRF even if the endpoint returns JSON.

### 3.3. Data, Header, Error, and Resource Matrix

| ID | Check | Expected Outcome |
| --- | --- | --- |
| DATA-01 | Malformed or oversized request body | Appropriate 400/413, no update |
| DATA-02 | Cross-tenant path/ID | 403/404, object not disclosed |
| DATA-03 | SQL metacharacters in input | Parameterized queries, SQL structure unchanged |
| DATA-04 | HTML string in display name | Rendered as escaped text; no DOM XSS |
| DATA-05 | Redirect target outside allowlist | Rejected or safely redirected internally |
| DATA-06 | Upload with spoofed extension/MIME | Rejected by validation/storage policy |
| HDR-01 | HTML response | CSP, `nosniff`, frame policy as expected |
| HDR-02 | HTTPS response | HSTS when appropriate for host and environment |
| HDR-03 | Personal/sensitive response | `Cache-Control: no-store` per policy |
| ERR-01 | Unauthenticated request | No stack trace or token leaked in response |
| ERR-02 | Authorization denied | Minimal audit log, no credentials logged |
| ERR-03 | Rejected by URL firewall | Filter chain not bypassed to admit anomalous paths |
| OPS-01 | Liveness/readiness | Exposes only necessary status details |
| OPS-02 | Management/config endpoints | Not public unless intentionally permitted |
| OPS-03 | Probing undefined route | Does not become an anonymous Spring Security bypass |

Not every codebase implements every row if a feature does not exist. However, **any row marked N/A** needs justification and reviewer sign-off rather than "skipped for time".

## 4. Testing Strategy: Which Test Proves What?

| Test Level | Appropriate Target | Limitations to Record |
| --- | --- | --- |
| Unit | Input validation, role/scope mapping, domain policy | Does not prove Servlet filters or real JWT signatures |
| Security service/method test | `@PreAuthorize`, owner/tenant, business roles | Mocked principals can bypass login/decoders |
| MockMvc + Spring Security filter chain | Matching, entry points, CSRF, 401/403/302, headers | Cookies/browsers, external IdPs, real proxies need extra tests |
| Authentication integration | `JwtDecoder`/JWK, issuer/audience, login/session stores | Requires suitable test keys/IdP/emulator |
| Repository + DB integration | Object ownership, persistent remember-me, transactions, data filters | Embedded DB may differ from production SQL |
| Browser E2E | Cookies, redirects, CSRF forms, CORS, cross-origin, logout | Slower, environment-dependent |
| Deployment probe | TLS/HSTS, proxy forwarding, live headers, health, runtime config | Does not replace deep authorization tests |
| Controlled pen test / DAST | Unexpected behaviors, XSS/IDOR/misconfig | Does not replace automation and code review |

**Never conclude "JWT is secure" just because `with(jwt())` passes.** Spring Security Test's `jwt()` injects a test Authentication; signature, issuer, and JWK retrieval may never execute. For JWTs, run a dedicated integration test suite invoking the **real decoder** with valid, tampered, expired, and wrong-audience tokens.

**Never conclude "session fixation is safe" just because `MockHttpSession.getId()` changes.** MockMvc rotates the ID in memory without proving a real container/browser rejects the old session ID; test with an HTTP client and two cookie jars against a real container.

## 5. Standalone Java 17: Validating Matrix Case IDs and Error Coverage

This is a **pure JDK 17 program** demonstrating how to validate part of a **matrix's quality**. It sends no HTTP requests and does not replace Spring Security Test. File `SecurityMatrixAuditDemo.java`:

```java
import java.util.List;

public final class SecurityMatrixAuditDemo {
    record Case(String id, String method, String path,
                String identity, int expectedStatus) {}

    static void requireUniqueIds(List<Case> cases) {
        long distinct = cases.stream().map(Case::id)
            .distinct().count();
        if (distinct != cases.size()) {
            throw new IllegalStateException("Duplicate test case ID");
        }
    }

    public static void main(String[] args) {
        List<Case> cases = List.of(
            new Case("AUTH-01", "GET", "/api/public/ping", "anonymous", 200),
            new Case("AUTH-02", "GET", "/api/me", "anonymous", 401),
            new Case("AUTH-06", "GET", "/api/me", "no-scope", 403),
            new Case("AUTH-07", "GET", "/api/me", "profile.read", 200),
            new Case("WEB-CSRF-01", "POST", "/web/settings", "no-csrf", 403),
            new Case("WEB-CSRF-02", "POST", "/web/settings", "with-csrf", 200),
            new Case("AUTH-11", "GET", "/web/account", "anonymous", 302),
            new Case("AUTH-13", "GET", "/admin/report", "user", 403)
        );

        requireUniqueIds(cases);

        long httpErrors = cases.stream()
            .filter(c -> c.expectedStatus() >= 400)
            .count();

        boolean hasCsrfNegative = cases.stream()
            .anyMatch(c -> c.id().equals("WEB-CSRF-01")
                && c.expectedStatus() == 403);

        System.out.println("cases=" + cases.size());
        System.out.println("unique-ids=true");
        System.out.println("http-errors=" + httpErrors);
        System.out.println("csrf-negative=" + hasCsrfNegative);
    }
}
```

Compile/run:

```bash
javac SecurityMatrixAuditDemo.java
java SecurityMatrixAuditDemo
```

Exact stdout:

```text
cases=8
unique-ids=true
http-errors=4
csrf-negative=true
```

Analysis: `http-errors=4` counts 401/403 (while the 302 redirect is a 3xx response). Unique ID checks let the matrix serve as a test catalog or evidence registry; `csrf-negative=true` only confirms **a case was described**, not that the real endpoint returned 403. Never treat mock strings inside `Case` as a substitute for HTTP testing.

Useful project extensions: give each case `priority`, `owner`, `testMethod`, `actualStatus`, `evidenceUri`, `timestamp`, and `deploymentBuildId`; fail reports if P0/P1 cases are missing or expected != actual. There is no need to invent a custom test framework when JUnit + CI reporting already exist.

## 6. Filter Chain Ordering: Review Before Running Tests

Spring Security Servlet typically executes:

```text
HTTP request
  -> Servlet container filters
  -> DelegatingFilterProxy (springSecurityFilterChain)
  -> FilterChainProxy
      -> First SecurityFilterChain matching RequestMatcher
      -> filters inside the selected chain
  -> DispatcherServlet
  -> Controller / Service
```

In multi-chain setups:
- **`securityMatcher`** limits which URLs/methods enter that chain.
- **`@Order`** sets the evaluation order of chain beans.
- **`authorizeHttpRequests(...requestMatchers...)`** enforces permissions once a chain is chosen.
- Catch-all chains belong after specialized chains.
- `permitAll` still runs the request through the security filter chain (unlike `web.ignoring()`).
- If **no chain matches**, the request may receive no Spring Security protection.

To review accurately, inspect `FilterChainProxy.getFilterChains()` in dev/test; for each chain, document its matcher, order, filters, entry point, and covered URLs. Enable `org.springframework.security.web.FilterChainProxy=TRACE` **only in test environments**, never logging raw tokens or session IDs.

### 6.1. Chain Review Template

| Chain | Matcher | Order | Authentication | CSRF | Fallback |
| --- | --- | --- | --- | --- | --- |
| API | `/api/**` | 1 | Bearer JWT | Disabled only if truly header-only/stateless | No |
| Web | Any request | 2 | Form login + session | Enabled | Yes |
| Separate management (if present) | Management matcher | Policy-dependent | Strong/segregated | Flow-dependent | No |

Test `/apiary`, `/api`, context paths, trailing slashes, encoded paths, servlet paths, and reverse proxy rewrites. **Never replace framework matchers with custom `startsWith("/api")` checks.**

## 7. Spring Boot 3 / Spring Security 6 Sample for Verification

The following example illustrates the **stateless JWT Bearer API + form-login web** architecture. It demonstrates an explicit policy, not a turnkey configuration for every enterprise. Required:
- `spring-boot-starter-web`;
- `spring-boot-starter-security`;
- `spring-boot-starter-oauth2-resource-server`;
- `spring-boot-starter-test` and `spring-security-test` in test scope;
- JDK 17+ and a Spring Boot main class;
- Valid JWT issuer/JWKS in production and user store/auth provider for form login.

### 7.1. SecurityConfig.java

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .hasAuthority("SCOPE_profile.read")
                .requestMatchers(HttpMethod.POST, "/api/me/update")
                    .hasAuthority("SCOPE_profile.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .cors(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout"))
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId()));

        return http.build();
    }
}
```

**Security decisions explained:**

1. `@Order(1)` places the API ahead of the catch-all web chain.
2. The API requires `SCOPE_profile.read` for GET, `SCOPE_profile.write` for POST, and `denyAll` for unrecognized API paths.
3. Bearer tokens are verified by the Resource Server (with a real JwtDecoder at runtime), while `@Order(2)` web uses form/session.
4. CSRF **is disabled only in the API chain**, because the sample threat model ensures the API **never accepts browser-auto-sent credentials like cookies/Basic**, accepting only Authorization Bearer headers without sessions. If a real app uses API cookies or Basic, redesign CSRF accordingly.
5. Web keeps default CSRF and uses session fixation protection with `changeSessionId()`.
6. Admin has a URL role rule, yet domain authorization/owner checks **still belong in the service layer**.
7. There is no blanket `permitAll` to silence test failures; unrecognized API paths are denied.

**Configure a real JWT decoder properly:** e.g., in `application.yml` (illustrative issuer name only):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
```

Production apps must point to a real issuer and verify signature, algorithm, `iss`, `exp`, and `nbf`; **audience** may require an explicit validator per provider/requirements. Never assume every JWT signed by an issuer carries the right audience for this API. If the IdP/JWKS is unreachable at startup or verification time, fail-closed/availability behavior depends on decoder setup; test it explicitly. Never disable signature validation just to pass integration tests.

### 7.2. CORS Configuration Restricted to Trusted Frontends

`CorsConfigurationSource` can be configured specifically for the API:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfig {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration c = new CorsConfiguration();
        c.setAllowedOrigins(List.of("https://app.example.test"));
        c.setAllowedMethods(List.of("GET", "POST"));
        c.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        c.setAllowCredentials(false);
        c.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", c);
        return source;
    }
}
```

This is a **template for a header-only Bearer API**, not a CORS policy for form-login web UIs. `allowedOrigins` requires exact origins (scheme/host/port)—never broad wildcards with credentials. CORS is a browser policy, **not backend authentication/authorization**; server-to-server or curl clients are unaffected by browser CORS, so APIs must still enforce auth themselves.

When testing CORS, send `OPTIONS` preflight requests with `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`, then verify the actual response rather than merely reading the bean definition.

### 7.3. Sample Controller for the HTTP Matrix

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    String ping() { return "pong"; }

    @GetMapping("/api/me")
    String apiMe() { return "profile"; }

    @PostMapping("/api/me/update")
    String updateProfile() { return "updated"; }

    @GetMapping("/web/account")
    String webAccount() { return "account"; }

    @PostMapping("/web/settings")
    String webSettings() { return "saved"; }

    @GetMapping("/admin/report")
    String adminReport() { return "report"; }
}
```

**Limitation:** the controller returns demo strings solely to test filter behavior; it has **no** DB, update side effects, validation, tenant checks, or owner checks. Seeing `updated` only proves an authorized request cleared the filter. Real systems must also verify service authorization, repositories, body validation, and transaction rollbacks.

## 8. MockMvc: Verifying Positive and Negative HTTP Cases

With `SecurityConfig`, `ApiCorsConfig`, and `DemoController` scanned, write `SecurityMatrixHttpTests.java`. To use `with(jwt())` without calling a live IdP, define a **test-only JwtDecoder**. This is intentionally a **mocked-authentication test**, not a cryptographic integration test.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Import(SecurityMatrixHttpTests.TestDecoder.class)
class SecurityMatrixHttpTests {

    @Autowired MockMvc mvc;

    @TestConfiguration
    static class TestDecoder {
        @Bean
        JwtDecoder jwtDecoder() {
            return token -> {
                throw new BadJwtException(
                    "Real JWT decoding not used by these mock-auth tests");
            };
        }
    }

    @Test
    void publicApiIsAccessible() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousApiGetsBearerChallenge() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string("WWW-Authenticate",
                containsString("Bearer")));
    }

    @Test
    void scopeReadAllowsGet() throws Exception {
        mvc.perform(get("/api/me").with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isOk())
            .andExpect(content().string("profile"));
    }

    @Test
    void missingScopeDeniesGet() throws Exception {
        mvc.perform(get("/api/me").with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeAllowsPostForStatelessApi() throws Exception {
        mvc.perform(post("/api/me/update").with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.write"))))
            .andExpect(status().isOk())
            .andExpect(content().string("updated"));
    }

    @Test
    void webPostNeedsCsrf() throws Exception {
        mvc.perform(post("/web/settings").with(user("alice")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/web/settings").with(user("alice"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("saved"));
    }

    @Test
    void anonymousWebRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void ordinaryUserCannotReadAdminReport() throws Exception {
        mvc.perform(get("/admin/report").with(user("alice")
                .roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedOriginPreflight() throws Exception {
        mvc.perform(org.springframework.test.web.servlet.request
                .MockMvcRequestBuilders.options("/api/me")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.test"));
    }
}
```

In this test, **`with(jwt())` skips real JWT parsing/verification** and supplies a test Authentication to the filter chain. The nested `TestDecoder` is a **test-only bean** so ApplicationContext has a `JwtDecoder` without reaching an IdP. **Never ship this test bean to production**: using it instead of a real decoder rejects all tokens or alters auth semantics.

Run in a Maven project:

```bash
mvn -Dtest=SecurityMatrixHttpTests test
```

Or Gradle:

```bash
./gradlew test --tests SecurityMatrixHttpTests
```

This test suite proves a set of route/authority/CSRF/CORS expectations for the **sample config**, not an entire production application. Replace `DemoController` with real controllers and add service-layer tests, input validation, and JWT decoder integration tests. Statuses/headers may differ when adding custom entry points, context paths, or security filters; the matrix must record your **chosen contract**.

### 8.1. Testing the Real JWT Decoder, Not Just with(jwt())

For a production Resource Server, write a separate test class configuring `JwtDecoder` with **test public keys/JWKS** or a trusted test IdP. Sign test tokens using a fixture private key (never production keys) and send over HTTP:

```http
GET /api/me HTTP/1.1
Host: api.example.test
Authorization: Bearer <test-jwt-signed-by-test-key>
```

Test at least these negative cases:
- Invalid signature or public key outside trusted JWKS → 401.
- `exp` in the past → 401.
- `nbf` in the future beyond allowed clock skew → 401.
- `iss` differs from configured issuer → 401.
- `aud` lacks the API's audience → 401 **when an audience validator is configured**.
- Untrusted signing algorithm → rejected.
- Valid signature yet missing scope → **403**.
- Key rotation / JWKS outage: verify caching, availability, and error responses per design.

**Never assume Spring Security validates every product-policy claim out of the box.** Built-in validators handle issuer/timestamps depending on configuration, while **audience** and business claims often require explicit validators per provider/architecture.

### 8.2. Testing Real Sessions, Login, and Logout

When the web chain uses form login:
1. Create a pre-login session and verify the session ID rotates upon valid login.
2. Replay the pre-login session ID against a real container: must remain unauthenticated.
3. Test POST `/logout` with CSRF; current session is invalidated.
4. Test POST `/logout` without CSRF; blocked with no side effects.
5. With concurrent-session control enabled, test two independent browsers (not two tabs sharing a cookie jar) for expire-old / prevent-new policies.
6. With remember-me enabled, distinguish token-based from persistent tokens; **deleting a browser cookie** does not always equal **server-side revocation** of token copies.
7. Test session timeout, SameSite/Secure/HttpOnly, and multi-node session stores.
8. With OAuth2 login, test state/redirect/callback and token/client registration separately.

Use `MockHttpSession` to test filter logic; test real containers/browsers for cookie attributes, old-session replay, and multi-node behavior.

## 9. Verifying Input Validation, Output Encoding, and Resource Authorization

The HTTP security matrix does not end at `authorizeHttpRequests`. An endpoint returning 200 for `SCOPE_profile.read` can still leak another user's profile if the service reads `?userId=123` without checking ownership.

### 9.1. Object-Level Access Control

For `GET /api/accounts/{id}`:
- Alice accesses Alice's account: allowed.
- Alice accesses Bob's account: **denied**, even though Alice's JWT carries a general profile-read scope.
- Alice alters `tenantId` in the request: cannot escape tenant boundaries.
- Admin holds the right role yet can read only tenants within their authorized scope per policy.

Test both **repository query filtering** and service authorization. URL authorization never replaces owner/tenant checks in business logic.

### 9.2. Input Validation and Injection

For a real `POST /api/me/update`:
- Use DTOs with `@Valid`, `@NotBlank`, `@Size`, and `@Pattern` matching each field's contract.
- Bound body/array/upload sizes and validate enum/state transitions and value ranges.
- Use prepared statements / ORM parameter binding instead of SQL string concatenation.
- When returning HTML, encode for HTML text/attribute contexts; frontends should use `textContent` instead of `innerHTML` for plain text.
- Rich HTML must pass through a sanitizer with an allowlist of tags, attributes, and protocols.
- Validate schemes/hosts/paths/egress for redirect URLs and SSRF targets.
- Never rely on CSP or input validation in place of output encoding.

Negative tests must verify **zero side effects**, not just HTTP 400/403. For databases, transaction tests should inspect record counts, owner/tenant fields, and audit logs.

## 10. Deployment Configuration Review: Layer-by-Layer Checklist

### 10.1. TLS, Reverse Proxy, and Trust Boundaries

- Production enforces valid HTTPS/TLS with org-approved ciphers/protocols; HTTP redirects to HTTPS where appropriate.
- HSTS is emitted over HTTPS for the right hosts; `includeSubDomains`/preload only after verifying every subdomain.
- Reverse proxies **strip incoming client-supplied `Forwarded`/`X-Forwarded-*` headers** and set fresh ones; the app trusts only controlled proxies.
- `Secure` session cookies are not lost because a backend behind TLS termination misreads the request scheme.
- Backend services are not directly reachable from the Internet over an unguarded HTTP port.
- URLs/matchers are tested against real context paths, servlet paths, hosts, and proxy rewrites.
- Request headers like `Host` and `X-Forwarded-Host` are never blindly trusted for redirects, RP IDs, or allowed origins.
- Proxy-to-backend links are secured per architecture, using mTLS where needed.

### 10.2. Filter Chains, Authentication, and Authorization

- Enumerate `FilterChainProxy.getFilterChains()`; verify matchers and `@Order`.
- Specialized chains precede the catch-all chain; no protected URL falls outside all chains.
- Use `permitAll` only for intended public routes; avoid reckless `web.ignoring()`, which strips security headers.
- Bearer APIs use `BearerTokenAuthenticationFilter` and proper JWT/opaque verifiers.
- Form login/sessions accept cookies/credentials only through the intended flow.
- `401` for anonymous API calls; `403` for authenticated missing permissions; `302` for web login per design.
- Method security (`@EnableMethodSecurity`, `@PreAuthorize`) has tests for proxies, self-invocation, and ownership.
- Never log raw Authorization headers, access tokens, passwords, secret keys, or session IDs.
- Custom filters sit in the right order; avoid registering as both a container filter and inside `SecurityFilterChain`, which causes double execution.
- Anonymous callers and error/async dispatches introduce no bypasses.

### 10.3. CSRF, CORS, and Request Boundaries

- Distinguish cookies/sessions/HTTP Basic from Bearer-header-only APIs when deciding CSRF policy.
- Unsafe web requests require CSRF; never disable CSRF globally just to pass tests.
- CORS allowlists exact origins, methods, and headers; never equate CORS with authorization.
- `OPTIONS` preflight traverses the CORS filter properly; both allowed and disallowed origins are tested.
- Never reflect arbitrary `Origin` headers when credentials are allowed.
- Cookies set `Secure`, `HttpOnly`, and `SameSite` per architecture, with tightly scoped path/domain.
- Rate limiting and abuse detection sit at gateway/app per policy; enabling Spring Security filters alone does not provide full anti-bot/DoS defense.
- Redirect targets are validated; Bearer/CSRF tokens are never placed in URLs.

### 10.4. Sessions, Logout, and Remember-Me

- Form login rotates the session ID after authentication (session fixation).
- Session timeout and concurrent-session policies are accurate, backed by a multi-node registry when clustered.
- `LogoutHandler` invalidates session/context; POST logout + CSRF matches design.
- Session cookies are cleared with matching path/domain, verified in a browser test.
- Remember-me enforces TTL, secure cookie flags, and key rotation/revocation policies, distinguishing token-based from persistent tokens.
- Single-device logout does not implicitly claim logout-all; if logout-all is offered, it revokes backend sessions/tokens properly.
- Sensitive user authentication state is not retained in logs/caches beyond policy.

### 10.5. JWT, Secrets, Cryptography, and Dependencies

- JWT `iss`, `exp`, `nbf`, signature, and trusted algorithms/JWKS are verified, plus `aud` per API requirements.
- Reject `alg=none`; never "decode JWT without verifying" and build an Authentication from it.
- JWK caching/rotation and IdP outage fail-closed/availability behavior are tested.
- Client credentials, remember-me keys, database passwords, and signing keys come from a controlled secrets manager/env, never committed to Git.
- Key rotation plans exist with known blast radius on exposure; secrets are never logged.
- Dependency versions align with the release's Spring Boot BOM; Spring Security core/web/config/test versions stay synchronized.
- Monitor CVEs/security advisories, SBOMs, and software supply-chain controls per organizational policy.
- Container images and JDKs stay patched and run with least privilege.

### 10.6. HTTP Headers, Caching, and Assets

- CSP fits the app: never enable `unsafe-inline`/`unsafe-eval` casually.
- `X-Content-Type-Options: nosniff` paired with accurate MIME types.
- `frame-ancestors`/`X-Frame-Options` per anti-clickjacking policy.
- HSTS only over proper HTTPS; verify live responses behind proxies.
- `Referrer-Policy`/`Permissions-Policy` where valuable per threat model.
- Sensitive responses set appropriate `Cache-Control`, typically `no-store`; static assets use a separate cache policy.
- Never serve uploaded active HTML files on the application origin without strict isolation and protection.
- Error pages never expose stack traces, configuration, or internal identifiers.

### 10.7. Logging, Observability, and Operations

- Audit login success/failure, access denied, privilege changes, account recovery, logout-all, and key rotation per privacy policy.
- Logs include request/correlation IDs without raw cookies, tokens, or passwords.
- Restrict `org.springframework.security=TRACE` to dev/test or short, controlled investigation windows.
- Health/readiness checks reflect DB/IdP/session dependencies sensibly without leaking sensitive details publicly.
- Metrics track `401/403/5xx`, login failures, JWT decoder errors, CSRF rejections, and latency/rate limits.
- Alert thresholds/baselines and runbooks for false positives exist.
- Owners are assigned for secret rotation, backups, incident response, alert routing, and rollbacks.

## 11. Verifying Configuration Across Environments

A common pitfall is running dev/test on HTTP localhost with mocked auth while production runs behind CDNs/reverse proxies, external IdPs, and multiple replicas. **A green local test suite does not prove the full deployment.**

| Item | Local/Test | Staging | Production |
| --- | --- | --- | --- |
| TLS | Localhost exemption acceptable for dev | Production-like HTTPS | Real HTTPS/headers |
| JWT issuer/JWKS | Test keys/fixtures; mocks for unit-only | Test IdP integration | Trusted issuer/JWKS |
| CORS origins | Strict dev origins | Exact staging origins | Exact production origins |
| Session store | Mock/in-memory | Shared store if multi-node | HA/replication/TTL policy |
| Secrets | Test-only; never reuse production | Managed staging secrets | Secrets manager/rotation |
| Logging | Controlled DEBUG allowed | Centralized, redacted | INFO/audit, no broad TRACE |
| Filter chain | MockMvc tests | HTTP/proxy tests | Safe live probes |
| Rollback | No user traffic involved | Deployment rehearsal | Artifact/schema/session compatibility |

### 11.1. Fail Closed and Dependency Failures

If the JWT verifier cannot fetch JWKS, never fall back to "trust token payload" or `permitAll` to keep traffic flowing. If the session store fails, never allow unauthenticated users to perform sensitive actions. If CORS fails, never open `*` unconditionally. Measure availability and design caching/retries while preserving **authenticity and authorization checks**.

### 11.2. Management Endpoints

`/actuator/health` may be public with minimal detail, whereas `/actuator/env`, `/actuator/configprops`, `/actuator/heapdump`, `/actuator/loggers`, metrics, and debug endpoints need dedicated policies—typically restricted by network, role, and exposure. The Spring Boot management port can use a separate container/filter chain; test against the real ingress. Never assume `/actuator/**` `permitAll` safely covers management endpoints.

## 12. Evaluating the Quality of a Test Matrix

Having **many rows** does not guarantee strong coverage. Check all dimensions:

1. **Endpoints:** sensitive resources as well as public/edge routes.
2. **HTTP methods:** GET/HEAD, POST, PUT, PATCH, DELETE, OPTIONS; path + method rules.
3. **Identities:** anonymous, user, admin, wrong tenant, disabled account, expired credential.
4. **Credential states:** missing, invalid, expired, revoked, sufficient scope, insufficient scope.
5. **Session states:** unauthenticated, authenticated, remembered, expired, concurrent, logged out.
6. **CSRF/CORS:** with/without CSRF, allowed/disallowed origins, preflight, cookie flags.
7. **Data:** valid/invalid schema, boundary sizes, IDOR, stored XSS, SQL parameterization.
8. **Failure modes:** IdP timeout, DB outage, JWKS rotation, invalid secrets, spoofed proxy headers.
9. **Environments:** dev/test, staging, production-specific ingress, multi-node.
10. **Evidence:** actual HTTP exchanges/statuses/headers, DB state, audits, build/git commit.

For every **critical control**, require both positive and negative tests: `GET /api/me` with valid scope returns 200 and missing scope returns 403; web POST with CSRF succeeds and without CSRF fails; valid cookie/session passes and invalid cookie fails.

Do not measure coverage by counting test methods if they all use `@WithMockUser` and bypass the JWT decoder or web filters. Code coverage measures executed lines, whereas security acceptance must verify **real invariants and boundaries**.

## 13. CI Quality Gates and Release Blockers

A baseline pipeline:

```text
Compile + dependency audit
   -> Unit tests (validation/domain)
   -> MockMvc Spring Security filter tests
   -> Integration tests (DB/JWT decoder/session)
   -> Browser/HTTP tests (TLS/CORS/cookies/proxy)
   -> Security configuration review
   -> Staging smoke + approval
   -> Progressive rollout + monitoring
```

Example severity classification:

| Level | Examples | Handling |
| --- | --- | --- |
| **P0 / release blocker** | Anonymous access to private data; tenant bypass; tampered JWT accepted; CSRF bypass on sensitive cookie-authenticated action | Block deploy, fix, and re-run tests |
| **P1 / release blocker** | API hits wrong chain; lost auth on a route; committed secrets; public admin endpoint; logout-all fails to revoke when promised | Block release per policy |
| **P2 / requires triage** | Missing non-critical header on non-sensitive page, bounded test flakiness, missing safe log fields | Owner assesses risk, fixes pre-rollout or logs explicit exception |
| **N/A with justification** | Remember-me absent so remember-me cases do not apply | Reviewer confirms feature truly does not exist |

Never automatically classify every 401/403 as P0: an intentional policy-enforced 403 can be a **PASS**. Judge based on **actual vs. expected behavior** and security impact.

### 13.1. Workflow When a Test Case FAILS

1. Record case ID, environment, build SHA, expected/actual, HTTP method/path, and authenticated principal type; **redact credentials**.
2. Identify which security chain was selected (`FilterChainProxy` / dev TRACE).
3. Classify as authentication (401), authorization/CSRF (403), login redirect (302), routing (404/405), or app error (5xx).
4. If JWT fails, inspect decoder/issuer/audience/algorithm rather than adding `permitAll`.
5. If CSRF fails, inspect cookie auth / CSRF token / same-origin flow without disabling protection to pass tests.
6. Fix at the responsible layer and add a regression test for the exact failure condition.
7. Re-run related tests and the full security matrix before release.

## 14. Deployment Evidence: Verifying Over Live HTTP

In staging/production, use browser DevTools or an HTTP client with isolated cookie jars in an authorized environment. Example **safe read-only probes**:

```bash
# Test public endpoint only, no tokens included:
curl -i https://api.example.test/api/public/ping

# Inspect HTML page headers (real route provided by the app):
curl -I https://app.example.test/login

# CORS preflight with allowed origin:
curl -i -X OPTIONS https://api.example.test/api/me \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Domains are illustrative; substitute your controlled staging origins on real systems. **Never place Bearer tokens, remember-me cookies, or passwords into shared shell histories or logs.** `curl` does not enforce browser CORS policy; it inspects response headers without proving browsers actually block/allow scripts per CORS. Use dedicated browser E2E tests for that.

When reverse proxies alter scheme/host/port or cache headers, inspect the **HTTP response after ingress/CDN**, not just backend `MockMvc`.

### 14.1. Minimal Evidence Packet

A concise release packet includes:
- Migration/dependency manifest and source commit;
- Reviewed `SecurityFilterChain` + matcher/order inventory;
- Test matrix with case IDs, results, build/environment;
- JWT cryptographic integration report;
- CSRF/session/CORS/browser test report;
- Redacted headers/TLS/proxy probe evidence;
- Open exceptions/risks and approver sign-offs;
- Rollback steps and on-call owner.

Never include session IDs, tokens, credentials, raw JWTs, private keys, or full request bodies with personal data in acceptance documents.

## 15. Common Pitfalls When Finalizing Practice

1. **Testing only the happy path:** 200 works while anonymous, missing-role, bad-token, and CSRF cases are untested.
2. **Overly broad matrix rows:** "API authorization PASS" without naming endpoint/method/user/context.
3. **Using `with(jwt())` and concluding the decoder checks signatures:** Authentication was mocked; cryptography was not tested.
4. **Using `@WithMockUser` to test form login/session fixation:** credential login mechanics were skipped.
5. **Assuming every 403 is an authorization error:** 403 can come from CSRF.
6. **Using CORS to protect APIs instead of authentication:** non-browser clients still reach unauthenticated APIs.
7. **Disabling CSRF globally because the API uses JSON:** cookie/session web routes remain vulnerable to CSRF.
8. **Putting the catch-all chain before the API chain:** API requests enter the wrong filter chain.
9. **Making `/api/**` permitAll just to pass tests:** introduces severe bypasses.
10. **Skipping owner/tenant checks:** a JWT with a broad scope can still read someone else's data.
11. **Testing only on local HTTP:** misses real `Secure` cookie, HSTS, and proxy trust bugs.
12. **Logging tokens while debugging:** leaks credentials into logs and CI artifacts.
13. **Forgetting to lock down actuator:** management endpoints expose config or runtime state.
14. **Relying on HTTP headers instead of output encoding/input validation:** CSP/HSTS do not replace XSS/SQLi defenses.
15. **Equating remember-me cookie deletion with revoking all token copies:** token-based remember-me carries distinct risks.
16. **Using two tabs in one browser to prove session concurrency:** both tabs share the same cookie jar/session.
17. **No rollback plan:** when session/IdP/DB issues hit in rollout, no tested recovery path exists.
18. **Green tests despite runtime BOM drift:** check resolved dependencies and container JDK/Jakarta compatibility.
19. **Ignoring upstream failures:** JWKS/IdP/session store outages must never fail open.
20. **Marking PASS without evidence:** impossible to trace which environment, build ID, or test verified behavior.

## 16. Final Handoff Checklist

- [ ] Inventory exists for URLs, HTTP methods, principals, scopes/roles, owner/tenant, auth mechanisms, and session flows.
- [ ] Every sensitive endpoint has anonymous + authorized + unauthorized authenticated tests.
- [ ] JWT/opaque tokens are tested with real issuer/signature/expiry/audience per policy, not just `with(jwt())`.
- [ ] CSRF is enabled wherever browsers auto-send credentials; POST/logout have negative CSRF tests.
- [ ] CORS origins/methods/headers and preflight are tested against real browsers/proxies.
- [ ] Filter chains have accurate `securityMatcher`/`@Order`, catch-all last, and no unintended unprotected URLs.
- [ ] Domain authorization/IDOR/tenant boundaries are enforced and tested at service and DB layers.
- [ ] Form login, session fixation, concurrency, remember-me, and logout are tested where used.
- [ ] Input validation, parameterized SQL, output encoding, and safe redirects/uploads have negative tests.
- [ ] TLS, HSTS, cookies, CSP, headers, and proxy trust are verified on real deployments.
- [ ] Secrets, keys, JWK rotation, dependency BOM, JDK/container versions, and SBOM are reviewed.
- [ ] Actuator/management endpoints are not exposed contrary to policy; readiness leaks no secrets.
- [ ] No raw credentials are logged; audits/metrics/alerts have owners and retention policies.
- [ ] Test evidence records case ID, build commit, environment, expected/actual, timestamp, and owner.
- [ ] All blockers are fixed, and any exceptions have explicit approval and risk acceptance.
- [ ] Canary/rollout/rollback playbooks are prepared with designated owners.

**Conclusion:** A Spring Security Servlet configuration is accepted only when **the test matrix proves the security invariants** and **deployment reviews verify the live environment preserves them**. Combine MockMvc filter-chain/401/403/CSRF tests, integration tests for token cryptography and data access, and real browser/HTTP checks for cookies/CORS/TLS/proxies, then govern releases with evidence, owners, and rollback plans. **"Build succeeded" and "happy-path tests green" are the starting line, not a security sign-off.**
