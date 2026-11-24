# Investigating 401, 403, and Redirect Loops Using Request Traces in Spring Security

> **Topic:** Spring Security – fundamentals • **Group:** Observability and Debugging • **Environment:** Spring MVC on the Servlet stack, Spring Boot 3.x / Spring Security 6.x, Java 17+. The goal is to pinpoint **which filter/handler** produced a 401, 403, or redirect chain using **request IDs, status/Location sequences, filter chain logs, and session/CSRF evidence**, rather than randomly changing permissions or disabling security mechanisms.

## 1. Real-World Scenario: All Mean "Cannot Get In," Yet Each Failure Differs

Three common symptoms:

- **401 Unauthorized:** an API returns 401, sometimes with `WWW-Authenticate`. The user is unauthenticated, or credentials/tokens are invalid for the configured mechanism.
- **403 Forbidden:** the request is authenticated but lacks authority; or it was blocked by another safeguard such as **CSRF**, the request firewall, or a policy at another layer. You cannot deduce "missing role" from the number 403 alone.
- **Redirect loop:** the browser bounces between `/private`, `/login`, or a callback path until it reports "too many redirects." Each HTTP 302 may be valid individually, yet together they form a cycle with no forward state progress.

A fourth symptom often accompanies these: **a browser button fails while curl/Postman succeeds**. In that case, compare cookies, CSRF tokens, `Origin`, `Accept`, caching, proxies, schemes, and every redirect—not just the controller.

This guide answers:

1. Which `SecurityFilterChain`, which filters, and whether a real request actually reached `DispatcherServlet`?
2. Is a 401 caused by missing authentication, wrong password, invalid token, or a misconfigured entry point?
3. Is a 403 caused by missing permission, CSRF, method security, a tenant/owner error, or another policy?
4. Which redirect produced `Location`, which one continued the chain, and why were session/credentials not preserved across hops?
5. How can you reproduce and prove the conclusion with logs, `curl`, and `MockMvc` without exposing sensitive data?

**Principle:** never use `csrf.disable()`, `permitAll()`, or `anyRequest().permitAll()` just to "make the error go away" before finding the root cause. That turns off safety guardrails rather than fixing the bug.

## 2. Reading 401, 403, and 302 in Context

| Symptom | Mechanism Likely Producing the Response | Investigation Leads |
| --- | --- | --- |
| 401 + `WWW-Authenticate: Basic ...` | HTTP Basic `AuthenticationEntryPoint` | Is the Authorization header present? Are password/encoder/user store right? |
| 401 + `WWW-Authenticate: Bearer ...` | OAuth2 Resource Server entry point | Are token expiry, issuer/audience, signature, scope, and scheme valid? |
| App-defined 401 JSON | Custom entry point or authentication failure handler | Did the expected handler write the response? Body schema does not prove source. |
| 403 on POST/PUT/DELETE | `CsrfFilter`, missing authority, business rule | Retry with a valid CSRF token; compare security TRACE and authorization logs. |
| 403 on GET data | Missing role/authority, object-level rule, firewall, or specialized entry point | Who is the actual principal? Which chain matched? Which rule denied? |
| 302 `Location: /login` | `LoginUrlAuthenticationEntryPoint` for a login-protected resource | Is `/login` accessible anonymously? |
| 302 `Location: /login?error` after login POST | `AuthenticationFailureHandler` | Wrong credentials, or was the POST blocked before the login filter due to missing CSRF? |
| 302 `Location: /web/home` after login POST | `AuthenticationSuccessHandler` | Did the browser store and send back the session cookie? |
| Consecutive 302s between two URLs | Proxy, login, saved request, invalid session strategy, application redirect | List every hop with `Location`, `Set-Cookie`, `Cookie`, scheme, host, and path. |
| 404 or 500 instead of expected 401/403 | Different route/filter chain, error dispatch, container/proxy | Did the request reach the app? Which route/dispatcher/exception produced the response? |

**An HTTP status code does not by itself tell you where it originated.** The same 403 can come from `CsrfFilter` returning before the controller, `AuthorizationFilter` denying the URL, `@PreAuthorize` on a service throwing `AccessDeniedException`, or the controller itself returning 403. You need a trace following **a single specific request**.

### 401 Does Not Always Appear for Browsers

If `formLogin` is configured with a login page, an anonymous visit to `/web/home` may receive **302 to /login**, not 401. With HTTP Basic, clients normally receive 401 and a challenge header. With Bearer tokens, behavior and `WWW-Authenticate` follow RFC/token handlers. Do not compare statuses across mechanisms without checking which entry point was selected.

### 403 Does Not Always Mean "Logged In"

Many 403 responses happen while **unauthenticated**, such as a missing CSRF token on a POST. An intentionally configured `Http403ForbiddenEntryPoint` can also return 403 to anonymous users. Thus "401 = not logged in, 403 = logged in" is only a common convention, **not a theorem** for every configuration.

## 3. Request Flow Map and Where to Place Traces

```text
Client/browser
    |
    v
CDN / WAF / reverse proxy / ingress       <--- Access log: status, Location, request ID
    |
    v
HTTP connector (Tomcat/Jetty/Undertow)
    |
    v
Servlet FilterChain                     <--- Request/response correlation filter
    |
    +-- DelegatingFilterProxy("springSecurityFilterChain")
    |       |
    |       v
    |    FilterChainProxy
    |       |
    |       +-- Selects first SecurityFilterChain matching request
    |       +-- SecurityContext / session
    |       +-- CsrfFilter
    |       +-- Authentication filter(s)
    |       +-- ExceptionTranslationFilter
    |       +-- AuthorizationFilter
    |       |
    |       +-- AuthenticationEntryPoint / AccessDeniedHandler
    |
    v
DispatcherServlet
    |
    +-- HandlerMapping, Controller, Service
    +-- @PreAuthorize / method security if enabled
    +-- HandlerExceptionResolver / @ControllerAdvice for MVC exceptions
    |
    v
Client receives status, headers, body
```

This diagram is a **model**: the actual filter order and list depend on configuration. `ExceptionTranslationFilter` only translates `AuthenticationException`/`AccessDeniedException` thrown within the chain segment it wraps; it does not catch every exception from any arbitrary filter. The Servlet container, `/error`, and proxies can generate responses **without invoking the original controller**.

Points to observe together:

- **Client trace:** request method + path, response status, `Location`, `WWW-Authenticate`, `Set-Cookie`, and redirect count.
- **Application:** request ID, dispatcher type, URL actually received by the server, filter invocations, CSRF outcome, normalized principal/authorities, and authorization decision.
- **Identity/session:** was the user actually authenticated, does the session exist/survive across redirects, and do cookie path/domain/secure attributes match?
- **Infrastructure:** did the request reach the app, did a proxy alter HTTP/HTTPS or paths, and did a WAF rule/route block it before the app?

If the **application-generated request ID** is missing from the response, the request may never have passed through the correlation filter/app, or an outer layer replaced the response. Do not rush to edit `SecurityFilterChain` when you only have WAF logs.

## 4. Ordered Investigation Workflow — Gather Evidence Before Fixing

### Step 1. Reproduce with a Minimal Request

Record **method, URL, scheme, host, path, possibly redacted query, masked key headers, client type, timestamp, and status**. Never copy raw `Authorization`, `Cookie`, access tokens, passwords, or private data into tickets or logs.

Use a request as close to production as possible: POST differs from GET; `Accept: text/html` differs from `Accept: application/json` and can trigger a different entry point; browsers manage cookies/redirects automatically whereas curl may not.

Example:

```bash
# Inspect only a single request's response; DO NOT follow redirects automatically.
curl -sS -D - -o /dev/null \
  -H 'Accept: text/html' \
  http://localhost:8080/web/home

# Show HTTP Basic API request/response, including status and headers.
curl -i http://localhost:8080/api/me
```

**Do not use `curl -L` right away**, because it makes you miss the first hop that emitted the redirect. Inspect each `Location` first.

### Step 2. Attach a Correlation ID

Every request should have a random server-generated ID or an infrastructure ID that has been **validated/sanitized**. Use this ID to join app logs, proxy logs, and DB/job queries if any. In the demo, the app generates a fresh ID per HTTP request and sets `X-Request-ID` on the response. A 302→302→200 chain is **multiple HTTP requests**, so it produces multiple IDs; group them by client trace session or test run.

In distributed environments, use W3C Trace Context (`traceparent`) via standard tracing tooling; never blindly trust a client-supplied ID that could contain CR/LF or malicious payloads. **A Trace ID is not a secret**, yet it can become data linking user activity, so it still needs a retention policy.

### Step 3. Enable Logging at the Right Scope and Time

In local/staging environments:

```properties
# application-local.properties — enable temporarily for debugging only
logging.level.org.springframework.security=TRACE
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.com.example.securitytrace=DEBUG
```

Spring Security emits `DEBUG`/`TRACE` logs covering requests, filter ordering, CSRF, and authorization. At startup, `DefaultSecurityFilterChain` usually prints the filter list; at runtime, `FilterChainProxy` at TRACE can show `Invoking ... (n/N)`. The list **can differ across versions** and across `SecurityFilterChain` beans—do not hard-code filter names or counts as test criteria.

Enable TRACE for a **narrow package** when possible, for a short time, in a test environment. Avoid leaving `org.springframework.security=TRACE` enabled long-term in production: logs can include paths, user metadata, and authentication-related details, generating high volume. Disable it after reaching a conclusion; runtime log levels can be adjusted via authorized operational tools if supported.

### Step 4. Find the Filter That Decided, Not Just the Last One Logging Status

Examples of *illustrative log lines*, not required verbatim stdout:

```text
trace=1f... request.start GET /api/me dispatch=REQUEST
DEBUG ... FilterChainProxy : Securing GET /api/me
TRACE ... FilterChainProxy : Invoking ...
DEBUG ... ExceptionTranslationFilter : ... start authentication ...
trace=1f... request.end status=401
```

Or:

```text
trace=2c... request.start POST /api/messages dispatch=REQUEST
TRACE ... FilterChainProxy : Invoking CsrfFilter ...
DEBUG ... CsrfFilter : Invalid CSRF token found for ...
trace=2c... request.end status=403
```

Do not infer from `status=403` that `@PreAuthorize` ran. If `CsrfFilter` stopped the request earlier, the service was never even called.

### Step 5. Build a Hypothesis and Control-Test Table

| Hypothesis | Controlled Experiment | Conclusion When Control Changes |
| --- | --- | --- |
| API 401 due to missing credentials | Try same path with valid HTTP Basic (local account) | 401→200 shows Basic path works; investigate client headers. |
| 401 due to wrong password/encoder | Try valid and invalid credentials; inspect auth logs without exposing passwords | Valid credentials still 401: inspect provider/UserDetailsService/encoder. |
| POST 403 due to CSRF | Keep same principal/URL, add a valid CSRF token | 403→201/200: root cause involves token or CSRF path. |
| 403 due to permissions | Keep valid token, swap authority/principal in test | Authorized user succeeds, unauthorized user is denied. |
| 403 due to object-level policy | Keep same principal, swap allowed vs forbidden resource ID | Proves owner/tenant rule rather than a general URL rule. |
| Redirect due to protected login page | Directly GET `/login` anonymously | GET /login also 302s to /login: fix login page access rule. |
| Loop due to session cookie dropped across redirects | Inspect `Set-Cookie` on login hop and `Cookie` on next hop | Cookie missing or altered: inspect Domain/Path/Secure/SameSite/proxy. |
| Loop due to proxy HTTP↔HTTPS or host mismatch | Follow each `Location` through proxy and call app directly in controlled way | Scheme/host flips back and forth: configure trusted forwarded headers and canonical URL. |

**Change only one variable at a time**: method, header, principal, CSRF, URL, or cookie. If you change three things simultaneously, a succeeding request does not prove which cause was right.

## 5. Runnable Demo: Two Protected Zones, One Tracing Filter

Use a single Servlet application to reproduce:

- `/api/**`: HTTP Basic; anonymous gets **401**, missing permission gets **403**; POST requires CSRF when enabled.
- `/web/**`: form login; anonymous gets redirected **302 to /login**; successful login goes to `/web/home`.
- `/login`, `/public/**`: permit anonymous access to prevent an immediate redirect loop on login.
- A Servlet `OncePerRequestFilter` placed before security that generates `X-Request-ID` and logs start/end timestamps even when security blocks before the controller.

This is a **local example** with hardcoded passwords, in-memory users, and simple observability logging. Do not deploy these users/passwords to production. Each code block is a separate file built and run with Gradle and the Spring classpath—**not** standalone Java files compilable via `javac` without adding dependencies.

### 5.1. Directory Structure

```text
security-trace-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── resources/application.properties
    │   └── java/com/example/securitytrace/
    │       ├── SecurityTraceApplication.java
    │       ├── SecurityConfig.java
    │       ├── RequestTraceFilter.java
    │       └── DemoController.java
    └── test/java/com/example/securitytrace/
        └── RequestTraceIntegrationTest.java
```

### 5.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'security-trace-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Plugin versions are pinned to reproduce the Boot 3.3 API examples cleanly; **this does not imply they are the latest patched releases for production**. Real projects must use versions actively updated and maintained by your organization. Gradle must be a version compatible with Spring Boot 3.3 and JDK 17+.

### 5.3. Logging Config — `src/main/resources/application.properties`

```properties
# Use locally for observation. In production: remove TRACE.
logging.level.org.springframework.security=TRACE
logging.level.com.example.securitytrace=DEBUG

# Show traceId from SLF4J MDC on each log line when present.
logging.pattern.level=%5p [trace=%X{traceId:-}]
```

During startup, MDC does not yet have a `traceId`, so the trace field is empty; that is normal. Once a request attaches an ID in the filter running on the request thread, security filter logs on that same thread can display the ID. If the system uses async tasks, Reactor/virtual threads, or multiple dispatches, **MDC does not propagate automatically across every thread**; use your platform's tracing context propagation.

### 5.4. Application — `SecurityTraceApplication.java`

```java
package com.example.securitytrace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityTraceApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTraceApplication.class, args);
    }
}
```

### 5.5. Two SecurityFilterChains — `SecurityConfig.java`

```java
package com.example.securitytrace;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/messages")
                    .hasAuthority("MESSAGE_WRITE")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        // Keep CSRF enabled for the demo. POST requires a valid token.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public/**", "/error")
                    .permitAll()
                .requestMatchers("/web/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/web/home", true)
                .failureUrl("/login?error")
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        var writer = User.withUsername("writer")
            .password(encoder.encode("writer-pass"))
            .authorities("ROLE_USER", "MESSAGE_WRITE")
            .build();

        var admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, writer, admin);
    }
}
```

**Why there are two chains:** `FilterChainProxy` picks **the first chain whose `securityMatcher` matches**. `/api/me` is handled by chain 1 (HTTP Basic), whereas `/web/home` and `/login` follow chain 2 (form login). If you insert a chain with matcher `/**` first, the remaining chain may never be selected. Two chains can have different sets of security filters; no single request runs both.

**Why `/login` is `permitAll`:** the login page must be reachable before authentication. With a custom `loginPage`, forgetting to allow anonymous access to the login page is a classic cause of **redirecting to `/login` itself**. The POST login action is also permitted by `formLogin(...permitAll())`, but **you must not drop the CSRF token** just because the login URL is permitted.

**Why `defaultSuccessUrl(..., true)`:** after a valid login, it always redirects to `/web/home` rather than using the saved request target. This keeps the demo consistent, not because every application should discard saved requests; in real apps, redirecting back to the originally requested URL is often appropriate.

**Why CSRF is kept on the Basic API:** the demo runs over Servlet and may be used by browsers; do not disable CSRF merely to make POST testing easier. For a real API accepting only Bearer tokens in headers and not relying on cookies, the CSRF threat model may differ. Base the decision on whether the client attaches credentials automatically, not merely on the label "REST API."

### 5.6. Correlation Filter — `RequestTraceFilter.java`

```java
package com.example.securitytrace;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class RequestTraceFilter extends OncePerRequestFilter {

    private static final Logger log =
        LoggerFactory.getLogger(RequestTraceFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String traceId = UUID.randomUUID().toString();
        long started = System.nanoTime();

        response.setHeader("X-Request-ID", traceId);
        MDC.put("traceId", traceId);

        try {
            log.info("request.start method={} path={} dispatcher={}",
                request.getMethod(), request.getRequestURI(),
                request.getDispatcherType());

            chain.doFilter(request, response);
        } finally {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started
            );

            log.info("request.end status={} durationMs={}",
                response.getStatus(), elapsedMs);

            MDC.remove("traceId");
        }
    }
}
```

**Detailed explanation:**

- `@Component` lets Spring Boot register the **Servlet Filter**; `@Order(Ordered.HIGHEST_PRECEDENCE + 10)` runs the filter earlier than the default security registration in typical Boot setups, allowing it to trace even 401/403 responses returned before the controller. In apps with custom registrations, always **verify actual ordering**.
- Generates a `UUID` on the server; this example does not trust a client-supplied `X-Request-ID`. Never log query strings, bodies, Authorization, Cookie, or CSRF tokens.
- `X-Request-ID` is set **before** `chain.doFilter`; if security blocks the request and the response still exits through the filter, the header remains present.
- `finally` logs duration/status and clears `MDC` even if the chain throws an exception. For unhandled exceptions, the status visible in the filter at that moment **is not necessarily the final status** produced later by the Servlet container or `/error` after the exception unwinds.
- `OncePerRequestFilter` has specific dispatch rules: do not assume the filter runs the same number of times for `REQUEST`, `ASYNC`, and `ERROR`. Check `shouldNotFilterAsyncDispatch()`, `shouldNotFilterErrorDispatch()`, and registration if needed.
- This is minimal request correlation; production typically uses Micrometer Tracing / OpenTelemetry with correlation IDs across proxies/gateways and services, along with sampling and redaction.

**URI logging warning:** even a path without a query string can contain a secret ID if an API embeds tokens in the path. For APIs with sensitive URLs, log a **route template** or redacted info rather than logging raw paths indiscriminately.

### 5.7. Controller — `DemoController.java`

```java
package com.example.securitytrace;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/public/csrf")
    public CsrfToken csrf(CsrfToken token) {
        return token;
    }

    @GetMapping(value = "/login",
                produces = MediaType.TEXT_HTML_VALUE)
    public String login(CsrfToken token) {
        return """
            <!doctype html>
            <html lang="en">
              <body>
                <form method="post" action="/login">
                  <input name="username" autocomplete="username">
                  <input name="password" type="password">
                  <input type="hidden" name="%s" value="%s">
                  <button type="submit">Sign in</button>
                </form>
              </body>
            </html>
            """.formatted(token.getParameterName(), token.getToken());
    }

    @GetMapping("/web/home")
    public String home(Authentication auth) {
        return "home:" + auth.getName();
    }

    @GetMapping("/web/admin")
    public String webAdmin() {
        return "web-admin";
    }

    @GetMapping("/api/me")
    public String me(Authentication auth) {
        return "api:" + auth.getName();
    }

    @GetMapping("/api/admin")
    public String apiAdmin() {
        return "api-admin";
    }

    @PostMapping(value = "/api/messages",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public String create(@RequestBody Message message) {
        return "created:" + message.text();
    }

    public record Message(String text) {
    }
}
```

This file includes a minimal HTML login page solely to **test form login and redirects**. Real applications should use a template engine with HTML escaping and proper UI rather than string concatenation for arbitrary inputs. Here, the CSRF parameter name and token are supplied by Spring Security; both strings are framework-generated values, not taken directly from the client.

`GET /public/csrf` makes it possible to fetch a token when testing POST with curl. When a system uses a **session cookie** to protect requests, the client must send both the matching token and cookie; MockMvc's `csrf()` helper works inside tests and does not replace real CSRF token exchange in browsers.

### 5.8. Running the Demo

```bash
# With Gradle wrapper already created in the project:
./gradlew test
./gradlew bootRun

# If no wrapper exists and a compatible Gradle version is installed:
gradle test
gradle bootRun
```

The project requires JDK 17+. For reproducibility, you can run tests first and start the app afterward. There is no fixed summary stdout/log because timestamps, threads, and request IDs vary; the assertions in section 8 serve as automated proof.

## 6. Investigating HTTP 401: Authentication and Entry Point

### 6.1. Comparing Against /api/me

With the demo running:

```bash
# 401: no Authorization header
curl -i http://localhost:8080/api/me

# 200: Basic header built from valid local credentials
curl -i -u reader:reader-pass \
  http://localhost:8080/api/me

# 401: invalid Basic credentials
curl -i -u reader:wrong \
  http://localhost:8080/api/me
```

Expected results:

| Request | Status | Key Body/Header |
| --- | --- | --- |
| Anonymous GET `/api/me` | 401 | Typically includes `WWW-Authenticate` from the HTTP Basic entry point. |
| Valid Basic `reader` | 200 | `api:reader`. |
| Wrong Basic `reader` | 401 | Does not invoke `me()` to return `api:reader`. |
| Anonymous GET `/web/home` | 302 | `Location` pointing to `/login`, from the form login entry point. |

**Do not print raw base64 credentials** in logs or tickets; Base64 does not securely encrypt passwords, it merely encodes the HTTP Basic header. Use TLS for Basic in real environments. The `curl -u user:password` commands here use demo credentials only; in production, use mechanisms that avoid exposing passwords in shell history or process lists.

### 6.2. When 401 Appears, Read the Trace in Order

1. **Identify the chain:** do `FilterChainProxy` logs show `Securing GET /api/me` and invocation of the Basic filter? If routed into a chain without Basic, the same credentials will not be processed.
2. **Inspect the request:** is `Authorization: Basic ...` or `Bearer ...` present with the right scheme? Did a proxy strip the header? Did the client drop the header after a cross-origin redirect?
3. **Identify the auth provider:** does the user store have that username, do `PasswordEncoder` and the stored hash match, and is the account locked, disabled, or expired?
4. **Check exception/entry point:** was 401 produced because no auth was provided, or due to a failed login attempt? `AuthenticationEntryPoint` and `AuthenticationFailureHandler` are distinct components.
5. **Check environment differences:** seeded test passwords, secrets, JWKS caches, issuer/audience/time skew, proxies, or system clocks.
6. **Check request ID:** if app logs do not show the response's ID, the request may have been blocked by a gateway or routed to a different service.

### 6.3. Bearer JWT Differs from HTTP Basic

If a real system uses an OAuth2 Resource Server:

- `401` usually involves a missing token, bad signature, expired token, or invalid issuer/audience/scheme.
- `403` can happen when the token is valid yet lacks the required authority/scope.
- `WWW-Authenticate: Bearer ...` may carry scheme-specific error codes; do not strip the header blindly just to force arbitrary JSON onto clients.
- `with(jwt())` in Spring Security Test **creates a mocked JWT principal**, without verifying token signatures. To test decoders, issuers, or key rotation, write integration tests with a real JWT/IdP setup.

Do not copy the demo's Basic-specific tests and conclude all JWT authorization is verified.

## 7. Investigating HTTP 403: CSRF, Permissions, Object Policy, or External Block?

### 7.1. CSRF Can Produce 403 Before Authentication or Controller Execution

`POST /api/messages` in the demo requires `MESSAGE_WRITE` and a CSRF token. Even though `writer` has the authority, a request missing CSRF can stop at `CsrfFilter`.

Test:

```bash
# Writer has valid credentials but lacks CSRF => 403.
curl -i -u writer:writer-pass \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' \
  http://localhost:8080/api/messages
```

Enable security TRACE locally and look for `CsrfFilter` messages about a missing or invalid token. If no request logs appear in the app, check the proxy/WAF first.

To properly test **authorization**, supply a valid CSRF token while using an account without `MESSAGE_WRITE`. With `curl` and `jq`:

```bash
# Fetch CSRF token from web chain, keeping the session cookie in a file.
TOKEN=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/public/csrf | jq -r '.token')

# Reader has valid CSRF but lacks write authority => 403.
curl -i -u reader:reader-pass \
  -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' \
  http://localhost:8080/api/messages

# Writer has CSRF and authority => 201.
curl -i -u writer:writer-pass \
  -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' \
  http://localhost:8080/api/messages
```

**Important note for the two-chain demo:** each `SecurityFilterChain` can carry its own `CsrfTokenRepository`, CSRF handler, and session strategy. The commands above illustrate the flow only when default configurations are compatible; in real multi-chain setups, a token obtained from the web chain is **not always** accepted by the API chain. For reliable end-to-end HTTP tests, issue the CSRF token via an endpoint **within the same chain** or configure a shared repository explicitly. With `MockMvc`, `with(csrf())` supplies a valid token within that specific test's scope, but does not prove real token exchange works end-to-end.

If a valid request still returns 403, distinguish among:

- CSRF failure due to missing/invalid token — traced at `CsrfFilter`.
- Authority failure — traced at `AuthorizationFilter` and the denied handler.
- Method security failure — the service was invoked through its proxy and the policy denied it.
- Object/tenant-level failure — identity is valid, but the resource is outside allowed ownership/scope.
- 403 from WAF/proxy — may never enter the app and has no app trace ID.
- `RequestRejectedException` from `HttpFirewall` — handled by `RequestRejectedHandler`, not automatically equivalent to `AccessDeniedException`.

### 7.2. When Permissions Are Truly Missing

The user `reader` has `ROLE_USER`, not `ROLE_ADMIN`. Therefore:

```bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/admin

curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin
```

Expected: `reader` gets **403**, `admin` gets **200**. Because this test uses GET, it is not confused with POST CSRF. However, it only verifies **function-level** URL rules; per-record permissions require checking owner/tenant rules in the service or repository layer.

**Remember role prefixes:** `hasRole("ADMIN")` normally matches `ROLE_ADMIN`, whereas `hasAuthority("MESSAGE_WRITE")` matches the exact string. A JWT with `scope=admin` does not automatically become `ROLE_ADMIN` unless a converter maps it. Trace authorities in a **minimized, test-only** form to verify exact names.

## 8. MockMvc to Verify Hypotheses Instead of Guessing

Create test file `src/test/java/com/example/securitytrace/RequestTraceIntegrationTest.java`:

```java
package com.example.securitytrace;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestTraceIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiAnonymousGets401WithTraceHeader() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"))
            .andExpect(header().exists("X-Request-ID"));
    }

    @Test
    void apiCorrectBasicCredentialsWork() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:reader"));
    }

    @Test
    void wrongPasswordGets401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithoutAdminAuthorityGets403() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminGets200() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api-admin"));
    }

    @Test
    void writerWithoutCsrfGets403() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("writer", "writer-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerWithCsrfButNoWritePermissionGets403() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerWithCsrfGets201() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("writer", "writer-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:hello"));
    }

    @Test
    void anonymousBrowserRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/home"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location",
                org.hamcrest.Matchers.endsWith("/login")
            ));
    }

    @Test
    void loginPageIsReachableAnonymously() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                org.hamcrest.Matchers.containsString("<form")
            ));
    }

    @Test
    void browserLoginCreatesSessionForFollowingRequest() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location",
                org.hamcrest.Matchers.endsWith("/web/home")
            ))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/web/home").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("home:reader"));
    }

    @Test
    void wrongFormPasswordRedirectsToLoginError() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location",
                org.hamcrest.Matchers.endsWith("/login?error")
            ));
    }
}
```

**Value of these tests:** the same filter configuration produces **401** for anonymous API calls, **403** for `reader` missing a role, **403** for POST missing CSRF, **302** for anonymous browsers, and **302** for login success/failure. Testing one variable at a time avoids misattributing failures.

**Important points about `MockMvc`:**

- `@SpringBootTest` + `@AutoConfigureMockMvc` loads the Spring context and attaches Boot-configured filters to MockMvc (`addFilters=true` by default). Using `standaloneSetup` without Security's `FilterChainProxy` can return 200 on URLs that should return 401/403.
- `httpBasic(...)` generates a real Basic auth header for the filter to authenticate against the in-memory user store; `@WithMockUser` and `with(user(...))` inject a test principal and **do not** verify passwords or real providers.
- `with(csrf())` supplies a valid test token. It does not prove that a browser preserves real cookies and tokens across a reverse proxy.
- `MockMvc` **does not automatically follow redirects**. Each `mvc.perform(...)` is a single request; to test sessions across requests, reuse `MockHttpSession` or an appropriate mechanism.
- The correlation ID filter runs in MockMvc if registered. In a real embedded server, headers and statuses can still be altered by proxies or error pages.
- If an exception occurs before `DispatcherServlet`, MockMvc may propagate the exception directly to the test instead of responding like Tomcat/`/error`; use live HTTP tests for those cases.

**Never disable `addFilters` or slap `@WithMockUser` onto every test just to make the suite pass.** A suite that skips security filters proves nothing about authorization.

## 9. Diagnosing Redirect Loops Hop by Hop

### 9.1. What Needs to Be Collected?

An example sequence:

```text
1) GET /web/home
   302 Location: /login
   Set-Cookie: ... (if any)

2) GET /login
   302 Location: /login

3) GET /login
   302 Location: /login
   ... repeats
```

Signal: `/login` itself requires authentication, or another filter/controller redirects the login page back to itself. For a cookie issue, the sequence might look like:

```text
1) GET /web/home   -> 302 /login
2) GET /login      -> 200 form
3) POST /login     -> 302 /web/home; Set-Cookie: JSESSIONID=...
4) GET /web/home   -> 302 /login (without a valid cookie)
5) GET /login      -> 200 form
... user keeps re-entering password; looks like a "loop"
```

These two sequences have **different causes**: the first is a direct redirect loop, whereas the second is a **session/login loop** triggered after user action. Distinguish them when reading HAR files and status histories.

### 9.2. Using curl to Capture and Boundedly Follow Redirects

```bash
# Observe the first hop without following Location:
curl -sS -D - -o /dev/null \
  http://localhost:8080/web/home

# View every hop in a sequence (bounded so it cannot loop forever):
curl -v -L --max-redirs 5 \
  -b cookies.txt -c cookies.txt \
  http://localhost:8080/web/home
```

`curl -v` prints detailed request headers, which may include cookies or Authorization if supplied. **Never paste raw verbose logs into tickets**; mask secrets before sharing. You can extract only statuses, `Location`, masked `Set-Cookie`, `X-Request-ID`, and method/host/path.

**Do not carelessly use `curl -I -L` to simulate a browser GET**: `-I` sends HEAD; security and controllers may handle HEAD differently from GET. To trace a GET redirect loop, use GET with `-D - -o /dev/null` as shown above.

### 9.3. Real Login Flow with CSRF and a Cookie Jar

Example using the demo's `/public/csrf` endpoint. In Bash with `jq`:

```bash
# Fetch CSRF token and keep cookies (if the app sets a cookie).
CSRF=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/public/csrf | jq -r '.token')

# POST form login. Omit -L to inspect Location and Set-Cookie on this hop.
curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  --data-urlencode "username=reader" \
  --data-urlencode "password=reader-pass" \
  http://localhost:8080/login

# Send the cookie after login; expect 200 instead of 302 /login.
curl -i -b cookies.txt -c cookies.txt \
  http://localhost:8080/web/home
```

Upon successful login, Spring Security may **clear/rotate the old CSRF token**; if you send another POST after login, fetch a new token. Browsers send session cookies only when Domain/Path/Secure/SameSite align; HTTPS, reverse proxies, and CORS settings must be tested realistically. For HTTP Basic APIs, session/cookie behavior does not necessarily match form login.

### 9.4. Typical Loop Causes and How to Prove Them

| Cause | Typical Trace | Verification Method |
| --- | --- | --- |
| `/login` is protected | Anonymous GET `/login` returns 302 to `/login` | Add exact `permitAll` rule and verify anonymous GET login returns 200. |
| Login POST URL is outside the right chain | Login POST returns unexpected 404/403/302 | Check `securityMatcher`, `loginProcessingUrl`, and chain ordering. |
| Login succeeds but session is not saved | Login POST 302s to private page, GET private 302s back to login | Check `Set-Cookie` and `Cookie`, session repository, proxy, auth success handler. |
| Browser rejects the cookie | DevTools warns on `Set-Cookie` or next request omits `Cookie` | Check Secure/HTTPS, Domain, Path, SameSite, and third-party cookie policies. |
| Session ID repeatedly treated as invalid | Redirects to `invalidSessionUrl` and redirects again | Inspect `SessionManagementFilter`, invalid session strategy, stale cookies; avoid endlessly forcing new sessions. |
| Request cache saved an inappropriate URL | Login success redirects to a URL that triggers auth again | Log saved request/target (without leaking secret queries), success URL selection, cache policy. |
| Proxy alternates HTTP↔HTTPS or hosts | `Location` flips between HTTP and HTTPS or domain A/B | Check trusted forwarded headers, TLS termination, and URL canonicalization. |
| Bad OAuth2/OIDC callback | Login → IdP → callback → login → IdP ... | Check registered redirect URI, state/nonce/session cookie, client config, and clock. |
| Another app route redirects on its own | Security logs allow it, yet controller returns 302 | Inspect controller/Servlet filter redirects and gateway rules. |

**Do not "fix" a loop by removing authorization from the target page** when the real cause is a missing session cookie; doing so can turn a private page into a public one.

### 9.5. Notes on Saved Requests

`ExceptionTranslationFilter` can use `RequestCache` to save the original request before sending the user to login. `SavedRequestAwareAuthenticationSuccessHandler` can then return them to that URL after authentication. If the original URL was misrouted by the app/proxy or itself triggers a different authentication mechanism, post-login navigation can re-enter the failing loop.

To investigate, log **normalized paths and hashed session/trace IDs** per your logging policy—never full query strings containing tokens. If the app intentionally always navigates to one fixed URL, `defaultSuccessUrl(..., true)` can make the flow clearer; that is a **product policy**, not a universal cure for every loop.

## 10. Investigating Mismatches Caused by Reverse Proxies, TLS, and Forwarded Headers

An external request might flow like this:

```text
Client:  https://example.com/web/home
Proxy:   http://app:8080/web/home
App sees request.isSecure() == false if forwarded info is not processed
App redirects /login or http://example.com/login
Proxy redirects http://example.com/... -> https://example.com/...
App generates an HTTP URL again -> can become a loop
```

Not every reverse proxy causes such a loop, yet if **the same URL keeps switching schemes or hosts**, check where absolute redirects are generated and how forwarded headers are processed.

Servlet-based Spring Boot supports configuring forwarded headers, such as `server.forward-headers-strategy` set appropriately for the deployment environment. Some containers/ingresses require specific settings and a **trusted proxy** policy. Never blindly trust `X-Forwarded-Host`/`X-Forwarded-Proto` from arbitrary external clients; untrusted headers can lead to host header injection or open redirects.

Verification steps:

1. Check the external `Host`, scheme, and URL visited by the browser.
2. Inspect proxy access logs and forwarded headers at the trusted boundary.
3. Log `request.getScheme()`/`isSecure()` in a **protected** diagnostic log, without logging arbitrary raw input.
4. Compare `Location` generated by the app vs modified/returned by the proxy.
5. Verify `Secure` cookies over HTTPS, `Path` matching context path, `Domain`, and `SameSite`.
6. After configuring, test live requests both through the proxy and directly to the backend in a controlled test environment.

**HTTP 301/308 are also redirects**, not only 302. Browsers caching permanent redirects can make post-fix tests look confusing; test with a fresh/incognito client or curl to rule out caching.

## 11. Multiple SecurityFilterChains and Matchers: Subtle Causes of 401/302

The demo has:

```text
@Order(1) securityMatcher("/api/**")
    -> httpBasic
    -> 401 for anonymous API

@Order(2) fallback chain
    -> formLogin
    -> 302 to /login for anonymous browser
```

If a service configures `securityMatcher("/api/**")` for form login as well while leaving `loginProcessingUrl("/login")` outside `/api/**`, the login filter in that chain **never receives POST /login**. The result can be 404, 403, a redirect loop, or another chain handling the request.

Questions to answer with traces:

- Is the final path after proxy/context path `/api/login`, `/login`, or something else?
- Did `FilterChainProxy` choose the chain containing the needed authentication filter?
- Are `requestMatchers` rules evaluated inside **the right chain** and in the right order?
- Does `permitAll` in one chain carry over to another chain? **No**: the request already picked the first matching chain.
- Is `web.ignoring()` or `filters="none"` making requests skip security? For public URLs, **`permitAll` usually keeps the security filter chain** and many useful protections intact.
- Does a mismatch between `/api/**` and `/api` (without trailing slash) or context path cause wrong chain selection? Verify with explicit tests.

Tests should cover **every critical path on both sides of matcher boundaries**: `/api/me`, `/api/admin`, `/web/home`, `/login`, `/error`, and actual callback/`loginProcessingUrl` paths. Never assume having "the right rule" in config is enough if that rule sits in a chain that is never selected.

## 12. Session, SecurityContext, and "Logged In, Then Immediately Logged Out"

### 12.1. What Must Be Persisted?

With stateful form login, successful authentication is normally tied to a session/security context; the browser stores a cookie (typically `JSESSIONID`) for subsequent requests. `AuthenticationSuccessHandler` returning 302 **does not guarantee the browser sent the session cookie on the next request**.

Check:

- Was a `Set-Cookie` header emitted when the session was created or its ID changed?
- Did the client actually accept and store the cookie?
- Did the follow-up request to `/web/home` carry the matching `Cookie` header?
- Does cookie `Path` cover the target path? Do `Domain`, scheme, `Secure`, and `SameSite` align?
- When the server receives the cookie, does the session exist in the repository? Is a load balancer routing to another node without shared sessions?
- Are session timeouts, invalid-session strategies, or concurrent-session controls invalidating the session?
- How are `SecurityContextRepository` and security context persistence configured for your Spring Security version?
- Is a custom filter overwriting `SecurityContextHolder`, or is a stateless session policy applied to the wrong chain?

**Never log raw session IDs.** To correlate across logs, use a salted/scoped hash or a correlation code that cannot be replayed as a session credential. A client request ID does not replace a session ID.

### 12.2. Use MockMvc to Test Sessions, But Do Not Stop There

`browserLoginCreatesSessionForFollowingRequest` shows that server-side session state is preserved across two MockMvc requests when passing `MockHttpSession`. It **does not test** whether a browser accepts the cookie under domain/secure/samesite rules or proxy rewrites. Run a live HTTP/browser test when a loop occurs only in production.

### 12.3. Stateless Bearer Differs from Cookie Login

With stateless JWTs, every request must send a valid Bearer token. If the client receives a token and forgets to attach `Authorization` on a redirect or subsequent request, 401 happens even though "login just succeeded." Do not debug `JSESSIONID` if the system uses no sessions. Inspect token delivery, storage, renewal, and CORS policies while avoiding token leakage in query strings or logs.

## 13. Protecting Data While Collecting Traces

Traces are technical evidence, yet they can become a security risk. A good trace contains:

- Timestamp with timezone, request ID/trace ID, service/instance, method, route template, dispatcher type, status, duration.
- The filter/handler that made the block decision and a **standardized reason code**, such as `AUTH_REQUIRED`, `ACCESS_DENIED`, `CSRF_INVALID`, `LOGIN_REDIRECT`.
- Pseudonymized user ID or minimal identifier, controlled authorities, and policy-minimized tenant ID.
- **Validated and redacted** redirect target; if query strings contain codes/tokens, never log them verbatim.
- Request category/scope for comparing TEST vs PROD while avoiding PII content.

Never log:

- `Authorization`/Bearer/JWTs, cookies/session IDs, raw CSRF tokens, passwords, OTPs, client secrets, SAML assertions, OAuth authorization codes.
- Login request bodies, forms containing credentials, or personal information.
- Full query strings containing tokens, password-reset links, or signed URLs.
- All headers at DEBUG/TRACE without redaction.
- Repeated stack traces containing sensitive details in production logs.

**Client-facing error codes can stay safe while server-side logs remain specific enough to distinguish causes.** Never tell anonymous callers whether account X exists; never echo raw `AuthenticationException.getMessage()` into response bodies.

When temporarily enabling TRACE in production for incident response, enforce restricted access, short duration, volume caps, retention limits, and redaction. On systems holding highly sensitive data, prefer reproducing in staging with synthetic data.

## 14. Distinguishing MVC Exceptions from Security Filter Rejections

`@RestControllerAdvice` handles exceptions routed through Spring MVC `DispatcherServlet` and `HandlerExceptionResolver`, not automatically every Servlet Filter. A request rejected by `CsrfFilter` or an authentication entry point returning 401 may **never invoke the controller or advice**.

Example flow:

```text
POST /api/messages
  -> RequestTraceFilter logs START
  -> Spring Security CsrfFilter missing token
  -> AccessDeniedHandler returns 403
  -> RequestTraceFilter logs END status=403
  -> DemoController.create(...) DOES NOT RUN
```

By contrast:

```text
GET /web/home (authenticated)
  -> RequestTraceFilter
  -> Spring Security permits
  -> DispatcherServlet -> DemoController.home(...)
  -> 200 "home:reader"
```

If a custom filter throws an unhandled `IllegalArgumentException`, the app may return 500 from the container/`/error`, not the JSON expected from controller advice. When analyzing status codes, determine whether a **filter stopped the chain**, an **MVC handler threw an error**, or the **container/gateway handled the error**.

## 15. Testing Redirect Loops with Bounded Tests

A test should never actually loop redirects infinitely. Measure **one or a few exact hops**:

- Anonymous `GET /web/home` must receive a redirect `Location` to `/login`.
- Anonymous `GET /login` must return 200 HTML, never redirect back to `/login`.
- Login POST with CSRF and valid credentials must redirect to `/web/home`.
- Passing the returned `MockHttpSession`, `GET /web/home` must return 200, not bounce back to `/login`.
- Login POST with wrong credentials must redirect to `/login?error`, and **`GET /login?error` must be reachable** (meaning the login path rule covers anonymous access).
- If `invalidSessionUrl` is configured, test requests with stale cookies and the target invalid-session URL as well; avoid creating a new loop.
- If using OAuth2/OIDC, test registered callback URIs, state, nonce, and cookies in a real browser.

You can supplement with an **HTTP client test** configured with a "never follow" redirect policy to assert each hop, or "max 5" to detect loops without running infinitely. For specific apps, running integration tests in front of the proxy in a production-like environment is the strongest way to catch scheme/host/cookie bugs.

## 16. When Failures Appear Only in Real Environments

A 3-layer testing strategy helps:

| Layer | Test/Tool | What It Can Prove | What It Cannot Prove Alone |
| --- | --- | --- | --- |
| Controller/method logic tests | JUnit + MockMvc with proper security context | Mapping, handlers, and Spring authorization when filters are attached | That browsers and proxies accept/return cookies realistically |
| Full application + Servlet container tests | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + HTTP client | Real embedded server connector and servlet lifecycle, cookies/headers/error dispatch | External TLS/proxies/IdPs if not included in test setup |
| E2E through production-like ingress/IdP | Browser automation, redacted HARs, gateway logs | Redirect sequence, cookie policies, HTTPS, CORS, SSO/callbacks | Uncovered error branches lacking test cases |

Watch out for commonly confused concepts:

- **CORS preflight** is OPTIONS; rejection before the browser sends the main request may appear as a CORS error in the UI. Check OPTIONS responses and CORS config rather than only running GET with curl.
- **Cookie SameSite/Secure** are browser policies; curl may send cookies in situations where browsers refuse, so curl "working" does not prove the frontend works.
- **Forwarded headers** must come from trusted proxies; never let external clients dictate host/scheme used by the app for redirects.
- **HTTP response caching** can cause frontends to replay stale 302s; check cache headers and test with a fresh client.
- **Node/session affinity** can allow login to succeed on node A while the next GET lands on node B without the session; inspect instance IDs and session stores.
- **RequestRejectedHandler/HttpFirewall** can block URIs containing unusual encodings/semicolons/paths before MVC; safely compare the raw edge URL with the app's normalized URL.

## 17. Ways NOT to Fix Errors When You Hit Them

1. **Disabling `csrf.disable()` globally because POST returns 403:** can open CSRF vulnerabilities on cookie/session-based apps.
2. **Adding `anyRequest().permitAll()` to stop 401s:** exposes protected endpoints publicly.
3. **Arbitrarily calling `web.ignoring().requestMatchers("/login")`:** strips security filters from the URL; `permitAll` usually lets the login page load while keeping appropriate protections.
4. **Turning every status into 200 with `{"success":false}`:** misleads clients and monitoring systems.
5. **Forcing login by writing `SecurityContextHolder` manually without proper context/session persistence:** can cause login loops or bypass session strategies.
6. **Logging raw request headers/bodies to "find the bad token":** can write real passwords, JWTs, or cookies into logs.
7. **Removing `WWW-Authenticate` on HTTP Basic/Bearer in a custom entry point:** clients may not know which protocol challenge to satisfy.
8. **Changing filter order without identifying the active chain:** breaks CSRF, exception translation, or authorization elsewhere.
9. **Redirecting blindly to an unvalidated `next` query URL:** introduces open redirect vulnerabilities.
10. **Looking only at the final URL from `curl -L`:** loses visibility into which hop caused the loop.
11. **Testing with `@WithMockUser` and claiming passwords/providers work:** mock users bypass credential verification.
12. **Treating a 302 redirect as proof of auth success:** 302 can come from an entry point requiring login or from a failure handler.
13. **Fixing only the frontend when the backend is actually returning 401/403:** use log correlation to identify where the decision happened.
14. **Analyzing multiple hops under one trace assumption without separating requests:** redirects create new HTTP requests, making it easy to mix logs and draw false conclusions.
15. **Changing proxy scheme/host without locking down trusted forwarded headers:** can introduce new bugs or security flaws.
16. **Ignoring `ERROR`/`FORWARD` dispatches:** error-page statuses can mask the original failure, or security may block the error dispatch.
17. **Leaving Spring Security TRACE on all day in production:** increases log volume and metadata exposure risk.
18. **Ignoring side effects of blocked requests:** verify data was not mutated even if the final response was 403.

## 18. Practical Checklist When Receiving a 401/403/Redirect Loop Ticket

- [ ] Record URL/method, timestamp, client, environment, status, and necessary masked response headers.
- [ ] Identify `X-Request-ID`/trace ID and the corresponding app instance/ingress hop.
- [ ] Determine whether the request reached the app or was blocked earlier by proxy/WAF.
- [ ] Identify which `SecurityFilterChain` matched the request and the active filter order.
- [ ] Distinguish entry-point 401, login-failure 401, authorization 403, CSRF 403, and other 403 mechanisms.
- [ ] Test valid vs invalid credentials without exposing passwords/tokens in logs.
- [ ] For POST/PUT/DELETE, test with valid CSRF to separate CSRF errors from permission errors.
- [ ] For permission 403s, verify exact authority strings, role prefixes, JWT/claims mapping, and object policies.
- [ ] For redirects, record status/Location per hop and the component generating each redirect; set a redirect cap.
- [ ] Verify anonymous GET `/login` returns 200 and does not redirect to itself.
- [ ] Verify the login POST URL falls inside the right chain, CSRF is valid, and success/failure handlers pick the right target.
- [ ] Track redacted `Set-Cookie` and `Cookie` headers between login POST and private GET.
- [ ] If behind a proxy, cross-check HTTP/HTTPS, host, context path, and trusted forwarded headers.
- [ ] If multi-node, verify shared session store or sticky routing.
- [ ] If using async/error dispatches or custom filters, verify final status in a real container.
- [ ] Write MockMvc tests to prevent regressions; add live HTTP/E2E tests for behavior outside MockMvc.
- [ ] Turn off temporary DEBUG/TRACE, redact, and restrict retention of diagnostic evidence.

### Self-Check Questions

1. Why do anonymous HTTP Basic APIs typically return 401 while anonymous web forms typically redirect with 302?
2. Why can two requests both returning 403 come from CSRF vs authorization, and which experiment separates them?
3. How does `FilterChainProxy` decide which `SecurityFilterChain` runs when multiple chains exist?
4. Why does `@ControllerAdvice` not automatically catch every error raised by security filters?
5. Is a 302 `/login` response enough to conclude login succeeded?
6. What evidence shows that the browser failed to send the session cookie after login POST?
7. Why does `MockMvc` with `@WithMockUser` not prove real passwords are verified?
8. Why should a request ID be assigned before security filters and cleared from MDC in `finally`?
9. Why can an HTTP→HTTPS redirect loop involve `X-Forwarded-Proto`?
10. Why can tracing with unbounded `curl -L` hide the origin of a redirect?
11. In a multi-chain app, why might `/login` fail to be handled by the login filter even when `formLogin` is declared?
12. Why is leaving production TRACE enabled long-term not a safe default observability practice?

**Hints:** (1) different entry points/challenges; (2) supply valid CSRF while keeping principal and URL unchanged; (3) first chain matching the request's matcher; (4) MVC resolvers sit behind servlet/security filters; (5) no, it can be the redirect to initiate login; (6) inspect Set-Cookie/Cookie, browser DevTools, and Domain/Path/Secure/SameSite policies; (7) mock users bypass the authentication provider; (8) correlate logs and prevent MDC leaking into other requests; (9) app does not see external HTTPS when proxy terminates TLS; (10) hides the offending hop and risks infinite looping; (11) loginProcessingUrl sits outside securityMatcher; (12) log volume and potentially sensitive metadata/credentials.

## Official Documentation

- Spring Security 6.5 — Servlet architecture, FilterChainProxy, logging, and exception translation: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security — Servlet authentication architecture and SecurityContext: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — Form login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security — Session management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — Request authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — MockMvc setup: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Spring Security — Testing HTTP Basic: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Spring Boot 3.3 — Logging: https://docs.spring.io/spring-boot/3.3/reference/features/logging.html
- Spring Boot 3.3 — Testing Spring Boot applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
