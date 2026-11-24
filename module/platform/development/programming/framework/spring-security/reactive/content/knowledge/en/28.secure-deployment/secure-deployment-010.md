# Pre-Release Review of CSRF, CORS, Security Headers, Matchers, and Sensitive Data — Spring Security Reactive

## 1. Objective: Turning Security Configuration into Testable Evidence

Before shipping a Spring Boot WebFlux application to production, seeing `SecurityWebFilterChain` start cleanly or a few requests return HTTP 200 is not enough. You must prove that: state-changing operations cannot be forged via a logged-in user's browser; only approved origins allow browser JavaScript to read responses; security headers fit how the app is deployed; every path and HTTP method passes through the intended authorization rules; and credentials, tokens, and personal data never leak via APIs, logs, errors, or observability infrastructure.

**Learning outcomes:**

1. Decide CSRF policy based on how the browser carries credentials, not merely whether the API returns JSON.
2. Verify CORS preflight, origin allowlists, credentials, and processing order in WebFlux.
3. Inspect response headers on the real HTTPS URL, covering both success and error responses.
4. Analyze `authorizeExchange` ordering, `pathMatchers`, multiple `SecurityWebFilterChain`s, and proxy/gateway paths.
5. Inventory every place sensitive data could be returned or logged; create repeatable test matrices and release-blocking gates.

**Scope:** Spring Security **Reactive/WebFlux** with `ServerHttpSecurity` and `SecurityWebFilterChain`. Servlet APIs such as `HttpSecurity`, `SecurityFilterChain`, `OncePerRequestFilter`, and `MockMvc` are not direct substitutes. Data access control at the service/repository layer remains essential alongside HTTP protection.

## 2. Map the Architecture Before Reviewing Configuration

First map out the real request flow:

```text
Browser / Mobile / Machine client
          |
          v
DNS -> CDN/WAF -> Load balancer / API Gateway (TLS, path rewrite, CORS?)
          |
          v
Spring WebFlux
    -> CorsWebFilter / CORS integration
    -> SecurityWebFilterChain (match chain -> CSRF -> authn -> authz)
    -> RouterFunction / @RestController -> Reactive service -> DB
          |
          +-> access log, tracing, audit, metrics, error handler
```

Questions that must have concrete answers: do users authenticate with form + `WebSession` cookie, HTTP Basic, OAuth2 Login, or bearer JWT? Does the browser automatically attach cookies/credentials on requests? Is the SPA on the same origin or a different origin? Are there multiple security chains, gateway path rewrites, Actuator management endpoints, or WebSockets? Where does HTTPS terminate? Which endpoints mutate state or handle sensitive data?

| Client / Credential Type | How Should CSRF Be Evaluated? | How Should CORS Be Evaluated? |
| --- | --- | --- |
| Web app using session cookies | Protect state-changing operations with tokens/equivalent controls; SameSite is an extra layer | If frontend is cross-origin, grant CORS only to trusted origins and credentials when required |
| SPA using auth cookies with cross-origin API | CSRF protection is still required; send token via header per designed mechanism | Allow exact origins, methods, headers, and `Access-Control-Allow-Credentials` if using cookies |
| SPA sending Bearer tokens **solely via JS Authorization header**, no auto-sent credentials | Disabling CSRF on a purely stateless chain may be considered after verifying all conditions; XSS and token leaks remain risks | Origin allowlist is still needed for browser access; CORS does not replace authn/authz |
| HTTP Basic in a browser | Browsers can cache and auto-send credentials, so do not assume immunity to CSRF | Check preflight if JavaScript sends `Authorization` |
| Non-browser mobile/server-to-server | CSRF is generally not the primary threat; enforce proper authn/authz and replay protection | CORS is a browser policy; it does not restrict `curl` or server clients |
| Mixed cookie + bearer app or multiple chains | Audit every chain/endpoint; avoid disabling CSRF globally and leaving cookie flows exposed | Scope CORS policies by domain and endpoint type rather than one broad allowlist |

**Key distinction:** CSRF addresses state-changing requests sent unintentionally by a browser when credentials are attached automatically. CORS governs **which origin's JavaScript the browser permits to read responses**; it is not server authentication and does not prevent simple cross-site requests from being sent. The same system may need both.

## 3. Reviewing CSRF Based on How Credentials Are Sent

### 3.1. Checking Protection Requirements

`CsrfWebFilter` is Spring Security WebFlux's CSRF component; default configuration enables CSRF protection. For apps using cookies/sessions, `POST`, `PUT`, `PATCH`, and `DELETE` operations must be tested with missing or invalid tokens. `GET`, `HEAD`, `OPTIONS`, and `TRACE` must remain non-mutating; if `GET /delete?id=...` deletes data, that is a design flaw even with default CSRF enabled.

Points to audit:

- No app-wide `csrf.disable()` just to "fix 403 errors," and no overly broad exclusion matchers like `/api/**` when sessions/cookies are still in use.
- Login, logout, password changes, config updates, webhook registration, privilege grants, and state-changing uploads must be in scope. WebFlux protects login by default; logout normally requires POST and CSRF.
- For HTML forms, embed the token in the form. For SPAs calling JSON APIs, send the token in a request header—never in URLs, logs, or error responses.
- The token repository config and the client's token-reading mechanism must match. By default tokens can live in `WebSession`; when using a cookie repository for an SPA, evaluate `HttpOnly`, `Secure`, `SameSite`, rotation, expiry, and token retrieval. Expose the CSRF token cookie to JavaScript only when the protocol requires it; the login session cookie should remain `HttpOnly`.
- Spring Security 6.x uses `XorServerCsrfTokenRequestAttributeHandler` by default to mitigate BREACH. When writing custom client token extraction or swapping handlers, test the exact token the client receives and the header the server validates so protection is not inadvertently disabled.
- SameSite, `Origin`/`Referer` checks, or Fetch Metadata (`Sec-Fetch-Site`) can support defense in depth; never treat a SameSite setting alone as proof that all CSRF scenarios are blocked.

**Common CSRF misunderstanding:** an HTTP 403 on `POST` can come from CSRF even when the user has the right role. Execute the exact same request with the same identity in two variants: **no token** and **valid token**. Then test authorization with a token-bearing request so a role-based 403 is not confused with a CSRF 403.

### 3.2. Disable CSRF Only with Explicit Security Justification

The following example is **only an illustrative config snippet**, appropriate for an API chain receiving bearer tokens in `Authorization` explicitly set by clients and accepting zero cookies/sessions or auto-sent credentials:

```java
// Illustrative snippet inside ServerHttpSecurity configuration,
// not a standalone Java program.
http.csrf(csrf -> csrf.disable());
```

To approve this choice, verify evidence: every endpoint on the chain uses a controlled auth mechanism; no cookie-based form/OAuth2 login, browser HTTP Basic, or session fallback exists; the gateway does not inject auth cookies; and new endpoints cannot accidentally land on the CSRF-disabled chain. If browser cookie endpoints still exist, split security chains with explicit matchers or keep CSRF and solve client token handling.

### 3.3. CSRF Test Matrix

| Action | Condition | Expectation |
| --- | --- | --- |
| Read-only GET resource | With/without valid credentials | Not blocked by CSRF; authorization still enforced |
| State-changing POST | Logged in via cookie, **missing token** | Rejected; data unchanged |
| State-changing POST | CSRF token **invalid or from another session** | Rejected; data unchanged |
| State-changing POST | Credentials, permissions, and token all valid | Passes CSRF check; business logic succeeds |
| POST changing roles | Valid token, missing ADMIN role | Rejected **by authorization** |
| Browser login / logout | Missing token on protected flow | State must not change against policy |
| CORS preflight OPTIONS | No cookie and no token | Handled by CORS; not treated as failed login |
| Expired session / logout | Replaying old token | Old token cannot mutate state for an ended session |

## 4. Reviewing CORS: Browser Origins, Preflight, and Credentials

### 4.1. Foundational Rules

An **origin** consists of scheme, hostname, and port. `https://app.example.com` differs from `http://app.example.com` or `https://app.example.com:8443`. Never equate "same site" with "same origin," and never allow every subdomain solely because they share a root domain.

A preflight request may look like:

```http
OPTIONS /api/profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type,x-csrf-token
```

Preflights typically **carry no session cookies**, so they must be handled before authentication filters reject them for lacking identity. Spring Security Reactive integrates CORS via `CorsWebFilter` and `CorsConfigurationSource`. CORS configuration should have one clear source of truth, avoiding gateways and the app emitting conflicting `Access-Control-*` values.

Check each rule against the approved API specification:

- `allowedOrigins`: list the **exact** trusted production origins; never use `*` when returning credentials. Keep local/dev origins out of production allowlists unless explicitly approved.
- `allowedMethods`: only the HTTP methods clients actually need; do not open everything by default.
- `allowedHeaders`: include headers clients genuinely send such as `Authorization`, `Content-Type`, `X-CSRF-TOKEN`; do not widen arbitrarily.
- `allowCredentials`: enable only when browser clients need cross-origin cookies or credentials; verify `SameSite=None; Secure` cookies if third-party cookies are truly used along with current browser restrictions.
- `exposedHeaders`: list only response headers JavaScript needs; never expose `Set-Cookie` or any secret credential.
- `maxAge` and caching: preflight caches can retain old policies; when changing allowlists, plan transition timing, coordinate CDNs, and set `Vary: Origin`/preflight headers appropriately.
- Invalid origins, `Origin: null`, port/protocol variants, or disallowed headers must fail per policy. A CORS "cannot read" response does not mean the server prevented all side effects: CSRF and authorization are still required.

**CORS is a browser policy.** `curl` can send any `Origin` and still reach the server if authentication/authorization allows it. Never use the `Origin` header as proof of user authority or to select a tenant without independent verification.

### 4.2. Warning Signs of Dangerous Configurations

| Config Pattern / Symptom | Risk | Fix |
| --- | --- | --- |
| `allowedOriginPatterns("*")` with credentials | Any website can receive credentialed CORS responses via origin reflection | Allowlist exact origins with clear owners |
| Allowing every `Header` / `Method` / route for a single SPA | Larger exposure surface, harder change audits | Scope by `/api/**`, exact methods, and needed headers |
| Preflight returns 401/302 to login page | Browser blocks valid requests before the actual call | Integrate CORS ahead of auth; check filter/gateway order |
| Gateway adds `Access-Control-Allow-Origin` alongside backend | Conflicting headers or policy drift | Pick one CORS owner and test at public ingress |
| Testing only unauthenticated GET | Misses POST + Authorization + CSRF header failures | Test OPTIONS and real requests from allowed/blocked origins |
| Believing CORS prevents CSRF | Forms/auto-sent credentials can still trigger side effects | Keep CSRF protection wherever needed |

## 5. Reviewing Security Headers on Real **Responses**

Spring Security provides several default headers, yet the right policy still depends on app type, deployment, and frontend. Run `curl -I` on HEAD-supporting endpoints or `curl -i` with GET, and inspect Browser Network tools on the real HTTPS domain. Inspect 200, 401, 403, redirects, and gateway-generated error pages; Spring's headers do not guarantee what the final CDN/ingress emits.

| Header / Attribute | What to Verify | Notes |
| --- | --- | --- |
| `Strict-Transport-Security` (HSTS) | Present over HTTPS with sensible duration; set at proxy if TLS terminates there | By default Spring Security adds it only when requests are seen as HTTPS; use `includeSubDomains` only if all subdomains support HTTPS |
| `X-Content-Type-Options: nosniff` | Present on protected responses with accurate `Content-Type` | Does not replace uploaded file content validation |
| `X-Frame-Options: DENY` | Not stripped by proxies, unless pages require iframes under a specific policy | Pair with `frame-ancestors` in CSP when serving HTML |
| `Content-Security-Policy` | Policy fits actual HTML/SPA resources; blocks unnecessary script sources | No universal "best" CSP; Spring Security does not configure a default CSP |
| `Cache-Control: no-store` and related | Personal data/credentials not cached by browsers/CDNs | Do not broadly drop security cache headers just to speed up static assets |
| `Referrer-Policy` | Sensitive paths/IDs do not leak in `Referer` outside the org | Choose `no-referrer` or `strict-origin-when-cross-origin` per product |
| `Permissions-Policy` | Disables unused browser features when serving web pages | Does not replace API controls |
| `Set-Cookie` | Session cookie has proper `Secure`, `HttpOnly`, `SameSite`, `Path`, and `Domain` | `SameSite=None` requires `Secure` on modern browsers; narrow domain scope where possible |
| `X-XSS-Protection` | Do not re-enable legacy "XSS filter" in place of CSP | Value `0` is intentional for modern browsers |

Note: Spring Security sets default headers such as no-cache, nosniff, and anti-framing; **CSP must be declared explicitly**. Calling `headers(headers -> headers.disable())` can wipe out a whole suite of protections. Test directly against the external domain and compare with staging; never judge solely from Java bean config.

**TLS and proxies:** verify HTTP-to-HTTPS redirects along real ingress paths, valid certificates, and forwarded-header rules trusting only managed proxies. Client-supplied headers like `X-Forwarded-Proto` must never trick the system into treating unencrypted HTTP as HTTPS if the edge has not scrubbed them.

**CSP rollout:** HTML/SPA apps with inline scripts, fonts, iframes, or analytics need a real inventory; test `Content-Security-Policy-Report-Only` before enforcing if needed. For backends returning only text/JSON, CSP's browser execution defense has narrower value; primary defenses remain accurate `Content-Type`, authorization, and leak prevention.

## 6. Reviewing Matchers and Route Coverage

### 6.1. Reading Rules as an Ordered Decision Chain

In `authorizeExchange`, Spring Security evaluates rules in declaration order; the first matching rule wins. Therefore:

```java
// Wrong order: broad rule renders the restriction below unreachable.
authorize
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll();
```

Place specific rules first and keep a fallback:

```java
// Right direction: each route/method is explicit and everything else is denied.
authorize
    .pathMatchers(HttpMethod.GET, "/public").permitAll()
    .pathMatchers("/api/admin", "/api/admin/**").hasRole("ADMIN")
    .pathMatchers(HttpMethod.GET, "/api/profile").authenticated()
    .pathMatchers(HttpMethod.POST, "/api/profile").hasAnyRole("USER", "ADMIN")
    .anyExchange().denyAll();
```

The snippets above are **partial configuration lambdas**, not standalone Java files; complete runnable code is in section 8. Check both root paths `/api/admin` and `/api/admin/**`, case sensitivity, trailing slashes, encoding, matrix params if any, different HTTP methods, and gateway-rewritten routes. Never assume the same policy covers all methods when only GET should be public.

With multiple `SecurityWebFilterChain`s, **`securityMatcher`** decides which chain claims an exchange before its internal `pathMatchers` run; `@Order` and chain match order are mandatory review items. An endpoint missing its intended chain can fall into another chain with a weaker policy. Never use `permitAll` to fix a sensitive endpoint before confirming why it was blocked.

### 6.2. Route Coverage Checklist

Build an inventory from controllers, functional `RouterFunction`s, gateway routes, Actuator/management, Swagger/OpenAPI UI, WebSocket handshakes, file uploads, and custom release endpoints. Each route needs **method, identity, role/scope, tenant, CSRF, and test result**.

| Illustrative Route | Method | Who May Access | Additional Conditions |
| --- | --- | --- | --- |
| `/public` | GET | Unauthenticated | Must not mutate data |
| `/api/profile` | GET | Authenticated user | Data must belong to that principal |
| `/api/profile` | POST | USER/ADMIN | CSRF if browser uses cookies/Basic; validate input and ownership |
| `/api/admin/report` | GET | ADMIN | Block USER role from reading admin data |
| `/api/admin/roles` | POST | ADMIN | CSRF as appropriate, post-commit audit, tenant checks |
| `/actuator/**` | GET/POST per endpoint | Per separate management policy | Never expose `env`, `configprops`, heap dump, or loggers publicly |
| Undeclared routes | Any | Nobody | Fail closed: `denyAll` once inventory is complete |

Beyond matchers, verify **record-level** access: holding the USER role does not grant permission to read `/users/{otherUserId}`. At the service/repository layer, compare the subject/tenant from `ReactiveSecurityContextHolder` or the verified principal against the object's owner. Never trust client-supplied roles or `tenantId` values.

When using WebFlux method security, verify reactive method security is enabled and actually test `@PreAuthorize`/`@PostAuthorize` where applied; HTTP matchers do not automatically guard every internal call. Never confuse Spring MVC/Servlet security annotations with Reactive chains.

## 7. Pre-Release Sensitive Data Leak Review

Create a **data-flow inventory**: inputs via headers, URLs, bodies, file uploads, and credentials; outputs via responses, exceptions, logs, traces, metrics, audits, caches, exports, and diagnostics. List field names, sensitivity levels, storage locations, who has access, retention, and masking/retention rules.

### 7.1. Leak Sources That Must Be Checked

| Location | Common Mistake | Acceptance Criterion |
| --- | --- | --- |
| Request/response logs, Netty wiretap, `WebClient` debug | Printing full `Authorization`, `Cookie`, login bodies, OTPs, refresh tokens | Log via field allowlist; mask/omit secrets; disable verbose debug in production |
| Exceptions and JSON errors | Stack traces, SQL, tokens, internal hostnames, user records in 4xx/5xx | Concise error contract with error code/correlation ID; details only in scrubbed internal logs |
| API DTOs / serializers | Returning password hashes, secrets, internal fields, raw DB entities | Dedicated response DTOs, explicit field mapping, and snapshot/contract tests |
| URLs and query strings | Tokens, reset links, email/PII entering browser history, proxy logs, `Referer` | Never pass secrets in query strings when safer options exist; single-use short-lived links |
| Cookies, browser storage | Session/refresh tokens readable by JS or scoped to broad domains | `HttpOnly` on auth cookies, `Secure`, `SameSite`, and minimal `Domain`/`Path` |
| Tracing/metrics | Tokens/PII entering span attributes, baggage, or high-cardinality labels | Use only non-secret correlation IDs; cap attributes and cardinality |
| Audit trails | "Saving full payloads for traceability" | Record who/what/outcome/safe object ID; never record credentials or full PII records |
| Caches/CDNs | Personal responses cached publicly or across tenants | Proper `Cache-Control`; never share cache keys without user/tenant and auth scope |
| Actuator/diagnostics | `/actuator/env`, `heapdump`, `loggers`, internal config left public | Expose only approved endpoints; restrict network, identity, and privileges |
| Client errors / CORS | JS from unknown origins reading responses with personal data | Never return sensitive data without authn/authz; exact origin allowlist |

**Values that must never leak:** passwords, password hashes, client secrets, API keys, full JWTs, access/refresh tokens, session IDs, OTP/recovery codes, private keys, DB URLs with credentials, and sensitive payment data. Even emails/IPs/usernames can be personal data: apply data minimization. A 401/403 error must not reveal "account A exists and is locked" if anti-account-enumeration is required.

### 7.2. Practices in Reactive Pipelines

- Never call `block()` just to log or mask data during request handling; use non-blocking APIs or proper logging infrastructure. Never enable global Reactor/Netty wiretap in production expecting to strip logs later.
- Never place raw credentials into `Reactor Context`, MDC, trace baggage, or message brokers. Context propagates data along the flow; it does not encrypt or protect it.
- Reject mass assignment: DTOs declare only client-editable fields, validating types, sizes, values, and owner/tenant at the service layer; never bind arbitrary JSON straight into entities containing `role`/`enabled` fields.
- Always use TLS for credentials; check `WebClient`, redirects, proxies, and downstream service accounts. Never forward bearer tokens to another origin via unvalidated redirects.
- Keep passwords/secrets out of source and artifacts using a secret manager and tight read permissions. Environment variables can still leak in crash dumps or diagnostic endpoints; by themselves they are not proof of security.
- For formal audit logs, use structured schemas and integrity-protected storage rather than dumping raw payloads. Event lookups must themselves enforce authorized access.

## 8. Runnable Example: WebFlux Config for Pre-Release Verification

This example uses **Java 17**, **Spring Boot 3.3.13**, Spring WebFlux, and Spring Security Reactive. It demonstrates a policy with four endpoint categories, CORS limited to `https://app.example.com`, default CSRF retained, HTTP Basic for testing, and security headers. Hardcoded accounts/passwords in source are **for local demo only**, not production config. The POST endpoint returns an illustrative string without writing to a database.

### 8.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>reactive-release-review</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.2. `src/main/java/dev/example/release/ReactiveReleaseReviewApplication.java`

```java
package dev.example.release;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class ReactiveReleaseReviewApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveReleaseReviewApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class ReviewSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var member = User.withUsername("member")
                .password(encoder.encode("demo-member"))
                .roles("USER")
                .build();
        var admin = User.withUsername("root")
                .password(encoder.encode("demo-admin"))
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(member, admin);
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        var configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(List.of("GET", "POST"));
        configuration.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-CSRF-TOKEN"));
        configuration.setAllowCredentials(true);
        configuration.setMaxAge(1800L);

        var source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", configuration);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public").permitAll()
                        .pathMatchers("/api/admin", "/api/admin/**")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET, "/api/profile")
                            .authenticated()
                        .pathMatchers(HttpMethod.POST, "/api/profile")
                            .hasAnyRole("USER", "ADMIN")
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .cors(withDefaults())
                .csrf(withDefaults())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp
                                .policyDirectives(
                                  "default-src 'none'; object-src 'none'; frame-ancestors 'none'")))
                .build();
    }
}

@RestController
class ReviewApi {
    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/api/profile")
    public Mono<String> profile() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName());
    }

    @PostMapping("/api/profile")
    public Mono<String> updateProfileDemo() {
        return Mono.just("accepted");
    }

    @GetMapping("/api/admin/report")
    public Mono<String> report() {
        return Mono.just("admin report");
    }
}
```

**Explanation:**

- `GET /public` is public, while all undeclared routes/methods hit `denyAll`. `GET /api/profile` requires authenticated; `POST /api/profile` requires USER or ADMIN; the admin branch comes first and requires ADMIN.
- `httpBasic(withDefaults())` enables Basic for testing; `csrf(withDefaults())` intentionally retains CSRF protection. Even when Basic provides a valid username/password, a `POST` without a token can still return 403.
- `corsConfigurationSource` specifies an exact origin for `/api/**`, allowing clients to send `Authorization`, `Content-Type`, and `X-CSRF-TOKEN`; `allowCredentials(true)` fits only when the app genuinely needs cross-origin credentials. Update origin/credentials appropriately before production.
- The `default-src 'none'` CSP example suits text-only APIs. If the application serves HTML/SPAs from the same server, replace it with a valid policy covering actual scripts/styles/images/fonts and test functionality.
- There is only one chain in the demo. Real projects must analyze every chain and auth mechanism; additional components like OAuth2, resource servers, gateways, and Actuator require dedicated tests.

### 8.3. Integration Testing with `WebTestClient` and Spring Security Test

Create `src/test/java/dev/example/release/ReactiveReleaseReviewSecurityTest.java`:

```java
package dev.example.release;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest
class ReactiveReleaseReviewSecurityTest {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void configureClient() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void matcherAndRoleMatrix() {
        client.get().uri("/public").exchange()
                .expectStatus().isOk();

        client.get().uri("/api/profile").exchange()
                .expectStatus().isUnauthorized();

        client.mutateWith(mockUser("member").roles("USER"))
                .get().uri("/api/admin/report").exchange()
                .expectStatus().isForbidden();

        client.mutateWith(mockUser("root").roles("ADMIN"))
                .get().uri("/api/admin/report").exchange()
                .expectStatus().isOk();

        client.mutateWith(mockUser("root").roles("ADMIN"))
                .get().uri("/unlisted").exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unsafeMethodRequiresCsrfToken() {
        client.mutateWith(mockUser("member").roles("USER"))
                .post().uri("/api/profile").exchange()
                .expectStatus().isForbidden();

        client.mutateWith(mockUser("member").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/api/profile").exchange()
                .expectStatus().isOk();
    }

    @Test
    void corsPreflightAllowsOnlyTrustedOrigin() {
        client.options().uri("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                        "authorization,content-type,x-csrf-token")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin",
                        "https://app.example.com");

        client.options().uri("/api/profile")
                .header("Origin", "https://untrusted.example")
                .header("Access-Control-Request-Method", "POST")
                .exchange()
                .expectHeader().doesNotExist(
                        "Access-Control-Allow-Origin");
    }

    @Test
    void securityHeadersArePresent() {
        client.get().uri("/public").exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Content-Type-Options", "nosniff")
                .expectHeader().valueEquals(
                        "X-Frame-Options", "DENY")
                .expectHeader().exists(
                        "Content-Security-Policy");
    }
}
```

Here `mockUser(...)` injects a principal to focus on testing authorization; `csrf()` adds a valid token to the mock exchange. This test **does not prove Basic passwords are verified, does not prove HSTS on public HTTPS, and does not prove edge gateway/CORS behavior works**. Add end-to-end tests through the real entry point before release.

Run with:

```bash
mvn test
mvn spring-boot:run
```

From another terminal, try a few requests:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/profile
curl -i -u member:demo-member http://localhost:8080/api/profile
curl -i -u member:demo-member http://localhost:8080/api/admin/report
curl -i -u root:demo-admin http://localhost:8080/api/admin/report
curl -i -u member:demo-member -X POST http://localhost:8080/api/profile

curl -i -X OPTIONS http://localhost:8080/api/profile \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type,x-csrf-token'
```

Expected: `/public` → 200 with body `public`; `/api/profile` without credentials → 401; with member → 200 and body `member`; member hitting admin → 403; root hitting admin → 200 and body `admin report`; member POST without token → 403; valid preflight includes `Access-Control-Allow-Origin: https://app.example.com`. Dynamic headers, error messages, and logs can vary by environment so no fixed fake stdout is listed. To verify **POST with a valid token**, see the `WebTestClient` test above; you cannot just pass an arbitrary token header in `curl` and expect it to be accepted.

**Demo limitations:** in-memory accounts, no HTTPS/gateway, no formal audit persistence, no real state mutations, and no object/tenant-level authorization. This is a configuration and test template, not a release-ready production build.

## 9. Pre-Release Acceptance Matrix

Run automated tests on the exact release-candidate build, then repeat **smoke tests through the real ingress domain** in production-like staging. The matrix must include both "allowed" and "denied" cases; otherwise a global `denyAll` config might falsely look secure.

| Category | Minimum Verification | Evidence to Archive |
| --- | --- | --- |
| CSRF | POST/PUT/PATCH/DELETE with no token, wrong token, valid token; logout and expired session; verify DB unchanged when blocked | HTTP statuses + trace showing zero side effects |
| CORS | Preflight with allowed/disallowed origins, credentials, headers/methods; compare gateway vs. app responses | Sanitized request/response headers; zero untrusted origins granted read access |
| Headers | 200/401/403/5xx over HTTPS; HSTS, cache, nosniff, frame, CSP if HTML exists, cookie flags | Header snapshots from public URL, real browser, CDN checks |
| Matchers | Anonymous, USER, ADMIN; GET/POST; root/nested routes; unknown routes; multiple chains and method security | Route-role-method matrix, test results, owner for every exception |
| Sensitive data | Response DTOs, validation/500 errors, debug logs, traces, audits, Actuator, exports, URL queries | Canary/test-data filters; zero tokens/secrets/PII outside policy |
| Domain/tenant | User A reading/editing object B; tenant A accessing tenant B's data | IDOR/BOLA tests; queries must filter by owner/tenant |
| Deploy/edge | HTTPS redirects, forwarded headers, CORS between CDN and app, browser cookies | Results from properly configured public domain/port |
| Operations | Alerts for anomalous 401/403, log redaction, key rotation, CORS/CSP incidents, rollback | Dashboards, runbooks, retention, and clear ownership |

### 9.1. Release-Blocking Conditions

QA fails if any of the following occurs: a request can mutate state without authorization because CSRF/authorization is missing; an untrusted origin can read credentialed data; a `permitAll` rule or chain matcher exceeds approved scope; secrets/tokens/PII appear outside allowed places; an important security header is stripped at the edge; management endpoints are publicly exposed; or tests prove only 403s without positive tests showing legitimate business flows still work.

For observability gaps or CSP violations on new policies, release-blocking decisions must follow organizational policy and defined impact levels, with an assigned owner and remediation plan. Never "fix" CORS or CSRF by disabling the entire protection layer without revisiting the threat model.

### 9.2. Short Review Record to Archive with the Release

```yaml
security_review:
  build_id: "release-candidate-id"
  deployment: "staging-public-ingress"
  authentication: ["http-basic-demo"] # Replace with real mechanism
  csrf:
    decision: "enabled-for-browser-flows"
    tests: ["unsafe-no-token-denied", "valid-token-allowed"]
  cors:
    approved_origins: ["https://app.example.com"]
    preflight_positive_negative: "passed"
  headers:
    https_edge_verified: true
    csp_checked_for_html: true
  matcher_coverage:
    all_routes_inventory: true
    default_fallback: "deny"
    positive_negative_authorization_tests: true
  sensitive_data:
    api_response_review: true
    logs_traces_actuator_review: true
  open_findings: []
  approver: "security-owner"
```

The values above **illustrate evidence structure**, not verification of any specific system. In practice, store test run IDs, timestamps, commit/build hashes, environment, approver, and approved exceptions. Whenever auth flows, domains, routes, proxies, or login cookies change after QA, re-run affected tests before release.

## 10. Common Mistakes and Quick Ways to Spot Them

1. **Seeing 403 on POST and disabling CSRF:** re-run with no token, valid token, and valid role; identify which layer rejected before changing code.
2. **CORS `*` to "make the frontend work":** specify exact origins, methods, headers, and credentials; test an unknown origin via real preflight.
3. **Sending `OPTIONS` through a login redirect:** fix CORS ordering so preflights never require cookies.
4. **Placing `/api/**.permitAll()` before `/api/admin/**`:** audit matcher ordering; test both permitted USER and denied USER cases.
5. **Correct in Spring yet broken at the CDN:** inspect headers, path rewrites, TLS, and CORS on the public URL.
6. **Testing only unauthenticated requests:** test authenticated users missing roles, authorized users, cross-tenant access, and every HTTP method.
7. **Assuming HSTS/CSP are always active by default:** HSTS requires properly detected HTTPS, and CSP needs an explicit policy; verify the final response.
8. **Logging full requests/responses to debug production:** use field allowlists, strip secrets, remove wiretap, and bound log retention.
9. **Exposing DB entities straight out of APIs:** use explicit response DTOs with user/tenant data checks.
10. **Taking only QA screenshots:** add repeatable tests, sanitized request/response evidence, build IDs, and owners for every exception.

## 11. Official Reference Documentation

- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Reactive CORS: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Security — Reactive HTTP Headers: https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html
- Spring Security — Reactive request authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — Reactive WebFlux security configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive WebTestClient CSRF testing: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP — HTTP Headers Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
