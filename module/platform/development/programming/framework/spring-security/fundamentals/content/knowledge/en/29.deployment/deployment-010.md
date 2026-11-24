# Handling Security Incidents Without Logging Sensitive Data or Temporarily Opening Permissions

> **Context:** Spring Security — fundamentals / Deployment. This lesson guides **investigating and resolving authentication, authorization, CSRF, login session, and security configuration incidents** without **logging passwords, tokens, cookies, personal data, or keys**, and without **temporarily granting broader access** just to debug. Examples use Java 17+, Spring Boot 3.5.0, Spring Security 6.x (Servlet), Maven, JUnit 5, and MockMvc.

## 1. Two boundaries that must never be broken during an incident

Incidents often start with an urgent symptom: legitimate users get 401/403, login hits a redirect loop, an API is blocked after a deployment, or unauthorized requests appear. A dangerous "quick fix" is:

~~~java
// WRONG: opening the entire API just to find why 403 was returned.
http.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll());
~~~

Or enabling overly broad logging:

~~~properties
# NEVER use casually in production.
logging.level.root=TRACE
~~~

Doing both can simultaneously create a **second incident**: data access is opened up and credentials/PII land in centralized logs, APM, support tools, or CI artifacts.

**Two mandatory principles:**

1. **Never relax permissions to debug.** Never change `authenticated()` to `permitAll()`, disable role/ownership/tenant checks, or turn off CSRF or security filters just to get a 200 response. Investigate in a controlled environment or observability path while preserving **deny by default** and **least privilege**.
2. **Never log sensitive data for extra context.** Never dump raw `Authorization`, `Cookie`, `Set-Cookie`, passwords, OAuth2 codes, API keys, JWTs, CSRF tokens, private keys, customer record contents, or full HTTP bodies. Log **events, safe reason codes, route templates/endpoint buckets, statuses, and correlation IDs**.

Proper investigation increases **useful signal** without increasing **exposed privilege**. Under high risk, you may need to *narrow* access, roll back a release, or isolate a service; no business excuse authorizes "opening the entire API for a few minutes."

## 2. First classify: functional bug or security incident?

| Symptom | Possible causes | Signals to cross-check | Never do |
|---|---|---|---|
| API returns **401** | Missing/invalid credentials, expired token, issuer/audience mismatch, lost session | Authentication scheme, `WWW-Authenticate` if relevant, auth failure event, cookie-present **boolean** | Log raw Bearer/JSESSIONID/password |
| API returns **403** | Missing authority, wrong role, missing/invalid CSRF token, disallowed tenant/owner | Decision code, rule/method, categorized CSRF reason, whether principal authenticated | Replace `hasRole` with `permitAll` |
| Immediately anonymous after login | Cookie not sent, session expired, context not saved | Cookie-present, session lookup hit/miss, context-loaded, node ID | Log entire session, disable CSRF |
| Fails only through proxy | Path rewrite, HTTPS/forwarded headers, CORS, context path | Normalized route, request ID, node and redacted proxy traces | Trust `X-Forwarded-*` from Internet clients |
| User sees another user's object | BOLA/IDOR, missing owner/tenant check | Resource-policy decision and pseudonymized actor, controlled internal ID | Leave bug live and hide a UI button |
| Repeated 401s or unusual token use | Password spraying, credential stuffing, token compromise | Counts/rates by region/time window, pseudonymized identity audit | Print credentials "to see who is trying" |
| 403 after update yet DB changed | Authorization checked after side effect | Audit mutations, transactions, state invariants | Assume status 403 means system is safe |
| Sensitive data spotted in logs | Logging filter/debug, exceptions, Actuator, APM | Only count/source/retention; never redistribute secret | Copy raw logs into tickets/chat |

If an **active intrusion or leak** is detected, transition to incident response and notify the responsible team; prioritize containment and evidence preservation per policy. If it is a **false deny** from misconfiguration, verify policy and restore service safely using a tested fix or rollback.

Never assume `401` is a bug or `403` means "Spring Security blocked by mistake." A `403` on someone else's document may mean the system is **working properly**.

## 3. A 7-step response workflow without breaking security boundaries

### Step 1 — Activate an appropriately permissioned response channel

Identify the incident owner, coordinator, Spring Security specialist, SRE, data owner, and security representative. Use an internal ticket/chat channel **with appropriate access controls**; never paste raw sensitive logs into broad channels. Record discovery timestamp (with timezone), app version, affected user/endpoint scope, impact assessment, and priority.

Set expiration times on every temporary action—never "leave debug logging on until someone remembers to turn it off." Anyone viewing evidence must follow need-to-know; if customer data is involved, apply active data-protection policies.

### Step 2 — Keep policy intact, confirm scope

Capture **configuration hashes/versions, deployment revisions, rule/route names, and feature flags**, without capturing secret values. Determine:

- Does it affect only one `SecurityFilterChain`, one tenant, or all requests?
- Did failures begin after a deploy/config change, key rotation, identity provider change, or reverse proxy change?
- Is any endpoint actually returning unauthorized data, or only 401/403?
- Are there signs of an active attack?

If over-permissive access is found, **contain early** (e.g., block the specific sensitive route, revoke tokens, disable compromised clients). If the incident is an unintended permission denial, **never** use broad permission relaxation as a workaround.

### Step 3 — Increase observability minimally and safely

Use a server-generated request correlation ID, **allowlisted** HTTP method, route bucket or route template **containing no IDs/secrets**, categorized error code (authn/authz/CSRF/session), service instance, and timestamp. Record summary counts and latencies. Never dump sessions, principal objects, raw paths/queries, headers, payloads, or exception messages that could reflect input.

If per-user signals are needed, use an appropriately pseudonymized identifier authorized strictly for the incident; do not treat an unsalted hash of an email as "anonymous." Account for privacy rules around IP addresses, user agents, and device IDs.

### Step 4 — Reproduce with fake data and test accounts

Use staging or an isolated environment, fixtures containing no real data, and test identities with specific roles/tenants, testing the same request under two roles. Avoid copying a production database to a local laptop just to debug. If a bug occurs only in production, use **minimized safe telemetry** and time-bound, scoped, approved observability—never turn on system-wide tracing.

### Step 5 — Fix the root cause instead of disabling defenses

Depending on the branch: fix request matchers/rule order, token verification, session store, proxy forwarded headers, CSRF integration, role mapping, or repository ownership predicates. Make small, reviewed changes with positive and negative tests.

For example, if `@PreAuthorize` was bypassed because `@EnableMethodSecurity` was missing, **enable proper enforcement** and test it. Do not replace it with a frontend role guard. If authorization is right yet the UI shows a confusing 403, improve the UX/message—**never** allow a forbidden action.

### Step 6 — Release safely and verify security is not weakened

Canary/roll out to a bounded cohort, tracking 401/403 counts, auth successes, CSRF denials, 5xx anomalies, and latency using minimized data. Re-verify that **authorized callers succeed**, **unauthorized callers fail**, and **rejected requests cause zero side effects**.

Roll back to a **known-safe** configuration when needed; never roll back to a vulnerable version just to "keep things running."

### Step 7 — Close the incident and clean up diagnostic traces

Remove approved temporary instrumentation, revoke any break-glass access, expire debug flags, review log access, purge or isolate sensitive evidence per retention policy, and write a postmortem **containing no raw secrets**. Add regression tests, alerts, and CI guardrails.

**Never delete evidence needed for legal/security investigations without authorization from the incident lead.** Distinguish **preserving evidence in an access-controlled vault** from **spreading copies into tickets or new logs**.

## 4. Safe log design: keep the signal, drop the data

A useful event might look like:

~~~json
{
  "event": "security_request_summary",
  "request_id": "server-generated-random-id",
  "timestamp": "2026-01-01T00:00:00Z",
  "route_bucket": "ops_status",
  "http_method": "GET",
  "http_status": 403,
  "outcome": "denied",
  "service": "account-api",
  "instance": "node-a"
}
~~~

**Illustrative data**, not logs from a real user. `request_id` must be generated or validated by server-side policy. `route_bucket` is a code-defined label, **not** raw `request.getRequestURI()` or `request.getQueryString()`.

| Safe to log when needed | Never log in ordinary application logs |
|---|---|
| Timestamp, service/version, event code | `Authorization: Bearer ...`, `Authorization: Basic ...` |
| Server-generated correlation ID | `Cookie`, `Set-Cookie`, `JSESSIONID`, session IDs |
| Normalized HTTP method, status | Raw request bodies for login, OTP, passwords |
| Static route template/bucket (no sensitive IDs) | Raw URLs with `token`, `code`, `key`, `email` query params |
| Authentication type (`basic`, `bearer`, `session`) if needed | Access tokens/refresh tokens, OAuth2 authorization codes |
| `ALLOW/DENY` decision and bounded internal reason code | `Authentication.toString()`, full `SecurityContext` |
| Session-present/context-loaded **boolean** after review | Session attribute contents, `UserDetails`, or full claims |
| Permitted per-tenant aggregates/metrics | Raw tenant/user/email/IP without genuine need and permission |
| Duration and instance ID | Private keys, client secrets, DB passwords, CSRF tokens |

**Not every "harmless-looking" field is actually harmless.** Paths like `/users/alice@example.com`, queries like `?access_token=...`, tenant slugs, and exception messages can hold private data. A principal name may be an email; raw IPs and user agents can also be personal data. Limit access, retention, and purpose.

### Log only safe reason codes

Instead of:

~~~java
// WRONG: objects and messages may contain usernames, tokens, or bodies.
log.error("Request failed: {} payload={} auth={}",
    exception.getMessage(), requestBody, authentication);
~~~

Use structured events with normalized cause codes:

~~~java
// Illustrative snippet: code accepts only controlled constants.
log.warn("security_event={} reason={} request_id={}",
    "authorization_denied",
    "MISSING_AUTHORITY",
    requestId);
~~~

Never concatenate `request.getParameter("reason")`, `Authorization`, or raw exception messages into logs. Even when using structured arguments or a JSON logger, restrict **allowed fields and sources**: JSON formatting does not make sensitive values safe.

### Defending against log forging

Input containing CR/LF or control characters can forge fake log lines or alter log meaning. Never log raw user agents, usernames, paths, or error messages. If policy ever requires logging client input, normalize, bound length, and escape control characters in a dedicated layer while restricting log read access. In particular, never trust a client-supplied `X-Request-ID` as a verified correlation ID.

## 5. Spring Security: choosing the right observation points

Spring Security Servlet uses a filter chain for authentication, CSRF, and authorization. Each point returning 401/403 has a different meaning:

| Observation point | Appropriate event | Avoid |
|---|---|---|
| `AuthenticationManager` / provider | Success/failure by **category**, no credentials | Full `UsernamePasswordAuthenticationToken` |
| `AuthenticationEntryPoint` | Unauthenticated request; 401 or login redirect per scheme | Error messages echoing tokens/passwords |
| `AccessDeniedHandler` | Principal lacks permission; 403 (or 404 if hiding resources) | Printing raw principal/ACL/resource contents |
| `CsrfFilter` | POST/PATCH/DELETE missing/invalid token | Dumping the real CSRF token |
| `AuthorizationFilter` / method security | Rule/decision and normalized reason code | Opening `permitAll` to avoid 403 |
| `SecurityContextRepository` | Context present/absent, session lookup hit/miss | Printing `SecurityContext`/session dumps |
| Controller/service | Resource action, minimized policy attributes | Printing entities, bodies, or private object fields |
| Reverse proxy/gateway | Request ID, route pattern/status, rate metrics | Raw URLs/queries, cookies/headers |

Inside `authorizeHttpRequests`, matchers are evaluated in order; `anyRequest().denyAll()` prevents new routes from opening accidentally. Only rules in the **selected `SecurityFilterChain`** apply. A chain with `securityMatcher("/api/**")` does not protect `/internal/**` if there is no fallback chain.

**Distinguish accurately during investigation:**

- `401` usually means missing or invalid authentication; HTTP Basic may return `WWW-Authenticate`.
- `403` can mean an authenticated user lacks a role or a request lacks a CSRF token. Never infer from 403 that "the user lost login."
- `404` may mean a non-existent resource or intentional hiding of another user's ID. Never swap 404 for 200 just to check data.
- Browser form login may redirect `302` instead of returning 401; verify your API contract.

When an endpoint requires ownership/tenant checks, `hasRole("USER")` is not enough; enforce it in the service/repository. Incident diagnostics must never bypass this check.

## 6. A Java 17 application illustrating safe observability

To demonstrate in practice, we build a small service with:

- `GET /public/health`: public, returning only non-sensitive status.
- `GET /api/ops/status`: `ROLE_OPS` only, returning a fixed status.
- All other methods/paths blocked via `denyAll()`.
- A servlet filter **placed before Spring Security** that generates a server-side correlation ID and logs **only** allowlisted event metadata—even when the request is blocked before reaching a controller.
- Two demo accounts `ops` and `viewer`; passwords are supplied **via runtime configuration**, never committing production values into source.
- MockMvc tests verifying functionality, permissions, and absence of leaked secrets in **test application logs** and responses.

The demo has no endpoint to dump config, view sessions, change roles, or disable permissions. It illustrates triage **without** needing a "debug backdoor."

**Tools:** JDK 17+, Maven 3.9+, Spring Boot 3.5.0 / Spring Security 6.x.

~~~text
safe-incident-debug/
├── pom.xml
├── src/main/java/com/example/safediag/
│   ├── SafeIncidentApplication.java
│   ├── SecurityConfig.java
│   ├── SafeRequestAuditFilter.java
│   └── DiagnosticController.java
└── src/test/java/com/example/safediag/
    └── SafeIncidentSecurityTest.java
~~~

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>safe-incident-debug</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

### 6.2. SafeIncidentApplication.java

~~~java
package com.example.safediag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeIncidentApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeIncidentApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfig.java

~~~java
package com.example.safediag;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${OPS_PASSWORD}") String opsPassword,
            @Value("${VIEWER_PASSWORD}") String viewerPassword) {

        return new InMemoryUserDetailsManager(
            User.withUsername("ops")
                .password(encoder.encode(opsPassword))
                .roles("OPS")
                .build(),
            User.withUsername("viewer")
                .password(encoder.encode(viewerPassword))
                .roles("VIEWER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(HttpMethod.GET, "/public/health")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/ops/status")
                    .hasRole("OPS")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Do not disable CSRF, do not permitAll globally, do not open debug paths.
        return http.build();
    }
}
~~~

**Note on configuration sources:** `@Value("${OPS_PASSWORD}")` and `@Value("${VIEWER_PASSWORD}")` read properties of those names; in the demo, they can come from env vars. If missing, the app must not fall back to a "default debug password" just to run. Tests supply **test-only values** via `@SpringBootTest(properties=...)`; these are not production passwords.

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` uses a proper encoder to hash demo passwords at runtime without writing raw passwords to loggers. In real systems, replace in-memory users with an IdP/DB, session/token policies, rotation, and least privilege. `STATELESS` fits the HTTP Basic demo, **not** systems that need to persist login via `HttpSession`.

`httpBasic` returns `401` for unauthenticated clients and `403` for authenticated users lacking `OPS`. Other `POST` requests are blocked by default CSRF or the catch-all rule; never disable CSRF to test permissions. `DispatcherType.ERROR`/`FORWARD` serve only internal dispatches needed by the demo's error/response handling, never opening public URLs.

### 6.4. SafeRequestAuditFilter.java

~~~java
package com.example.safediag;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class SafeRequestAuditFilter extends OncePerRequestFilter {

    private static final Logger log =
        LoggerFactory.getLogger(SafeRequestAuditFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Do not trust a client-supplied X-Request-ID header.
        String requestId = UUID.randomUUID().toString();
        request.setAttribute("app.requestId", requestId);
        response.setHeader("X-Request-ID", requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            log.info(
                "event=http_request request_id={} route_bucket={} "
                + "method={} status={}",
                requestId,
                routeBucket(request.getRequestURI()),
                safeMethod(request.getMethod()),
                response.getStatus()
            );
        }
    }

    private static String routeBucket(String uri) {
        // Read the URI for classification without writing the raw URI to logs.
        return switch (uri) {
            case "/public/health" -> "public_health";
            case "/api/ops/status" -> "ops_status";
            default -> "other";
        };
    }

    private static String safeMethod(String method) {
        return switch (method) {
            case "GET", "POST", "PUT", "PATCH", "DELETE",
                 "HEAD", "OPTIONS" -> method;
            default -> "OTHER";
        };
    }
}
~~~

**Why does this example not leak data?**

- `requestId` is randomly generated on the server—**never derived from session IDs, JWTs, or client-supplied headers**. It serves solely to correlate events for the same request.
- `routeBucket()` returns one of a fixed set of labels, never logging raw paths/queries. If a request hits `/reset-password?token=SECRET`, the log records only `other` with no token.
- `safeMethod()` allows only valid/normalized method names.
- Never calls `getHeader("Authorization")`, `getCookies()`, `getInputStream()`, `getParameterMap()`, `SecurityContextHolder.getContext().toString()`, or `request.toString()`, and never logs exception messages containing input.
- `@Order(Ordered.HIGHEST_PRECEDENCE + 10)` registers the servlet filter early enough in the demo to observe requests rejected by Spring Security, assuming container/filter registration honors Spring Boot ordering as expected.
- `finally` logs an event even if the chain exits abnormally. Note that the status there may not reflect the **final error dispatch** if errors are handled downstream; production needs logging aligned with error handling and async dispatches. This sample illustrates **synchronous** requests only.

**Limitation:** this event proves only that this filter **does not actively log secrets**. It does not guarantee logs from every dependency, servlet container, proxy, APM agent, or default access log are sanitized. Audit those layers under the same policy.

Never use a correlation ID as an authorization token or in place of a session ID. If the frontend sends an `X-Request-ID`, the system may store it in a separate validated field such as `client_trace_id` for debugging, but never treat it as identity/integrity proof or log it raw without bounds.

### 6.5. DiagnosticController.java

~~~java
package com.example.safediag;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiagnosticController {

    @GetMapping("/public/health")
    public Health health() {
        return new Health("ok");
    }

    @GetMapping("/api/ops/status")
    public OpsStatus opsStatus() {
        // Never return Environment, beans, keys, stack traces, or sessions.
        return new OpsStatus("operational");
    }

    public record Health(String status) {}
    public record OpsStatus(String status) {}
}
~~~

The OPS endpoint in the demo returns only a static status, **not** full config or server details. In production, many scenarios need no new OPS endpoint at all: existing metrics/tracing may be safer. When diagnostic endpoints are genuinely required, restrict networking, RBAC, allowed fields, lifetime, and auditing.

### 6.6. SafeIncidentSecurityTest.java

~~~java
package com.example.safediag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "OPS_PASSWORD=local-fixture-ops-only",
    "VIEWER_PASSWORD=local-fixture-viewer-only"
})
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class SafeIncidentSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicHealthDoesNotNeedCredentials() throws Exception {
        mvc.perform(get("/public/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(header().exists("X-Request-ID"));
    }

    @Test
    void anonymousCannotAccessOpsEndpoint() throws Exception {
        mvc.perform(get("/api/ops/status"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void viewerCannotUseOpsEndpoint() throws Exception {
        mvc.perform(get("/api/ops/status")
                .with(httpBasic(
                    "viewer", "local-fixture-viewer-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void opsCanReadOnlySafeStatus() throws Exception {
        mvc.perform(get("/api/ops/status")
                .with(httpBasic(
                    "ops", "local-fixture-ops-only")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("operational"));
    }

    @Test
    void spoofingRoleAndRequestIdCannotWidenPermissions(
            CapturedOutput logs) throws Exception {

        String secretCanary = "SENSITIVE_CANARY_NEVER_LOG_THIS";

        mvc.perform(get("/api/ops/status")
                .with(httpBasic(
                    "viewer", "local-fixture-viewer-only"))
                .header("X-Role", "OPS")
                .header("X-Request-ID", secretCanary)
                .header("X-Api-Key", secretCanary)
                .param("access_token", secretCanary))
            .andExpect(status().isForbidden())
            .andExpect(header().exists("X-Request-ID"));

        assertThat(logs.getAll())
            .contains("event=http_request")
            .doesNotContain(secretCanary);
    }

    @Test
    void deniedEndpointDoesNotReflectCredential(
            CapturedOutput logs) throws Exception {
        String canary = "BEARER_CREDENTIAL_NOT_FOR_LOGGING";

        mvc.perform(get("/internal/debug")
                .header("Authorization", "Bearer " + canary)
                .param("token", canary))
            .andExpect(status().isUnauthorized());

        assertThat(logs.getAll())
            .contains("event=http_request")
            .doesNotContain(canary);
    }

    @Test
    void thereIsNoTemporaryPermitAllForOtherPaths()
            throws Exception {
        mvc.perform(get("/internal/debug")
                .with(httpBasic(
                    "ops", "local-fixture-ops-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfIsStillEnforcedForUnsafeRequests() throws Exception {
        mvc.perform(post("/api/ops/status")
                .with(httpBasic(
                    "ops", "local-fixture-ops-only"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isForbidden());

        // Even with a CSRF token, denyAll still blocks POST because POST is outside policy.
        mvc.perform(post("/api/ops/status")
                .with(httpBasic(
                    "ops", "local-fixture-ops-only"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Notable test points:**

- No real controller reads `Authorization`, `X-Api-Key`, `X-Role`, or the `access_token` query parameter. The test intentionally sends a harmless fake-secret marker to prove the logging filter **does not echo the marker**.
- The authenticated `viewer` lacking `ROLE_OPS` gets `403`; anonymous gets `401`; authorized `ops` gets `200`.
- The `/internal/debug` test proves there is no debug backdoor—even authenticated `ops` gets `403`.
- `CapturedOutput` in Spring Boot Test inspects logs captured during **test execution**, not production logs or all infrastructure loggers.
- Client-sent `X-Request-ID` is never reused as the log ID; responses carry a fresh server-generated ID.
- `POST /api/ops/status` is forbidden even with a valid CSRF token. That is **method-level authorization**, not disabling CSRF "to make it run."
- `local-fixture-...` values are test strings with zero privileges anywhere real; production must use proper secret/config or identity systems.

`@SpringBootTest` and `@AutoConfigureMockMvc` exercise the security filter chain with MockMvc without opening a real HTTP port. Even when this test passes, **never infer that Nginx, ingress, service mesh, APM, sidecar, or tooling logs are safe**; verify and harden each layer independently.

## 7. Running and verifying the sample without opening permissions

In the project directory:

~~~bash
mvn test
~~~

Tests are expected to pass with compatible Java/Maven/dependencies. This is an **execution guide**, not a claim that Maven was run in this document.

Run the app locally with **two separate passwords supplied via environment variables** (bash). Silent prompts avoid recording raw secrets in shell history:

~~~bash
read -r -s -p "OPS password: " OPS_PASSWORD
echo
read -r -s -p "VIEWER password: " VIEWER_PASSWORD
echo
export OPS_PASSWORD VIEWER_PASSWORD
mvn spring-boot:run
~~~

Environment variables suit demos, yet can still be read by process inspection/debug tools; production should use a secret manager and strict permissions rather than treating env vars as absolute protection. Demo passwords must never enter Git/JARs/images or logs.

In another terminal:

~~~bash
# Public endpoint: 200.
curl -i http://localhost:8080/public/health

# Anonymous OPS request: 401.
curl -i http://localhost:8080/api/ops/status

# Authenticated OPS: 200. curl prompts for the password interactively.
curl -i -u ops http://localhost:8080/api/ops/status

# Authenticated OPS, but URL not approved: 403.
curl -i -u ops http://localhost:8080/internal/debug
~~~

On PowerShell, use `curl.exe` if `curl` is aliased to `Invoke-WebRequest`. Never pass passwords on the command line via `-u ops:secret`, as shell history and process lists can expose them. When finished testing:

~~~bash
unset OPS_PASSWORD VIEWER_PASSWORD
~~~

`unset` does not revoke credentials if exposed; reset/revoke them at the issuing system.

**What should appear in application logs:** a line like `event=http_request request_id=<random> route_bucket=ops_status method=GET status=403` or similar, with no raw passwords, tokens, cookies, or queries. This is an **example format**; UUIDs differ per request. Evaluate any separate proxy/container logs independently.

## 8. Debugging 401 and login failures without printing credentials

### Case A — 401 after sending a Bearer token

Possible causes: client omitted the header, expired token, untrusted issuer, invalid signature, wrong audience, malformed `Authorization` header, or out-of-sync key rotation. Safe to log:

~~~text
event=authentication_failure
auth_scheme=bearer
reason=TOKEN_VALIDATION_FAILED
route_bucket=orders_api
request_id=<server-generated>
status=401
~~~

**Never log:** token values, raw JWTs, full claims, signatures, refresh tokens, client secrets, or security contexts. If debugging requires distinguishing `expired` from `audience_mismatch`, use **reason codes in access-controlled logs** without returning sensitive details in public responses; weigh the risk of helping attackers probe tokens.

With Spring Security OAuth2 Resource Server, verify issuer, audience per contract, and allowed algorithms. During JWKS rotation, inspect key caches via safe version metadata—never distribute private keys to verifiers just to debug.

### Case B — 401 after session login

Observe along the chain:

~~~text
POST /login:
  authn_succeeded=true?
  set_cookie_session_present=true?
  security_context_saved=true?

GET /api/me:
  session_cookie_present=true?
  session_lookup_hit=true?
  security_context_loaded=true?
  authentication_present=true?
~~~

This is a list of **boolean/diagnostic signals**, not default fields emitted by every Spring logger. Never call `request.getSession()` inside a logging filter, because it can **create a brand-new session and distort diagnosis**; use `getSession(false)` in authorized components when needed.

Note that `HttpOnly` blocks JavaScript from reading `JSESSIONID`—it does not mean the browser lost the cookie. Session ID changes after login can be **session fixation protection**. Clearing `SecurityContextHolder` after a request is normal; if a custom login uses explicit saving yet forgets `SecurityContextRepository.saveContext(...)`, subsequent requests can appear anonymous.

### Case C — Wrong Basic credentials

Log only credential type `basic`, outcome `BAD_CREDENTIALS`, request ID, and aggregated rates. Never log Base64 `Authorization`: Base64 decodes directly back into username/password. Never run ad-hoc scripts decoding live headers "for convenience." Against password spraying, rely on rate limiting and alerts rather than logging millions of secrets.

## 9. Debugging 403 without disabling authorization or CSRF

First identify where `403` originated:

1. **CSRF denial:** unsafe method (POST/PUT/PATCH/DELETE) missing or presenting an invalid token; the filter blocks before reaching the controller. Authorization tests must supply valid tokens per client mechanism.
2. **Route authorization:** authenticated user lacks `ROLE_ADMIN` or `SCOPE_x`, or a matcher matched unexpectedly. Inspect method, path pattern, matcher ordering, and chain selection using minimized data.
3. **Method security:** `@PreAuthorize`/policy beans blocked the service; requires `@EnableMethodSecurity` and proper Spring proxy invocation.
4. **Object authorization:** user has the role but does not own the ID, belongs to another tenant, or lacks an ACL. This may be correct behavior; never grant access by removing the owner predicate.
5. **Firewall/CORS/proxy:** request never hit the right app route, preflight was blocked, or headers were rewritten; inspect ingress and app independently.

**Never apply these "temporary fixes":**

~~~java
// WRONG: removing protection layers to hide the 403 symptom.
http.csrf(csrf -> csrf.disable());
http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
~~~

Besides opening a vulnerability, such changes destroy diagnostic evidence: you no longer know which policy blocked the request. The proper fix is reproducing with a test principal, valid CSRF token, and test resource, then adjusting the **specific rule** confirmed wrong.

### HTTP status alone is insufficient: verify side effects

An endpoint returning 403 after already modifying the DB before the policy check is still a critical flaw. In tests:

~~~text
Actor: bob (does not own order 101)
Action: PATCH /api/orders/101
Expected HTTP: 403 or 404 per policy
Expected DB state: owner/order content unchanged
Expected side effects: no email, no event, no file write
~~~

Verifying that an authorized user succeeds while another user is denied tests the boundary from both sides. Never hide a frontend button as a substitute for backend tests.

## 10. Debugging requests/responses without raw payload dumps

Many request-logging libraries expose `includeHeaders`, `includePayload`, and `includeQueryString`. Turning them all on in production can log passwords, tokens, PII, and customer payloads.

Configuration never to deploy to production just to debug:

~~~java
// WRONG in environments holding sensitive data.
CommonsRequestLoggingFilter filter = new CommonsRequestLoggingFilter();
filter.setIncludeHeaders(true);
filter.setIncludePayload(true);
filter.setIncludeQueryString(true);
~~~

**Safer alternative:** log only route templates/buckets, normalized methods, statuses, request IDs, durations, and event codes. If you genuinely need to know why input failed validation, log a **validation rule ID** instead of raw input—e.g., `INVALID_DATE_FORMAT`, `MISSING_REQUIRED_FIELD`, `UNSUPPORTED_MEDIA_TYPE`. A plain hash of raw emails/tokens is usually insufficient anonymization and can be dictionary-attacked.

If requests must be correlated without storing raw data, consider an **HMAC fingerprint with a dedicated, short-lived, tightly scoped telemetry key**—only when justified by business need and data-protection policy. Never log `SHA-256(rawPassword)` or the last 4 characters of tokens by default: those can still leak sensitive info or enable improper correlation.

Avoid taking DevTools Network screenshots when headers carry tokens; if evidence must be shared, redact **before sharing** and verify images/PDFs carry no recoverable metadata or text layers.

## 11. Error responses safe yet informative enough for users to report bugs

Users need a way to file tickets without screenshotting tokens or internal error bodies. A safe response might be:

~~~json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to perform this action.",
  "requestId": "server-generated-id"
}
~~~

This is an **illustrative API contract**, not Spring Security's default response body from section 6. In Spring MVC, `ProblemDetail` works well for application exceptions; Spring Security's exception translation uses dedicated handlers for 401/403. Never let the frontend display raw stack traces or exception messages, and never embed secrets in error codes.

**Distinguish two audiences:**

- Client: short message, status, and request ID; never reveal details like "resource ID 515 belongs to Alice in tenant east."
- Authorized investigator: event codes, route templates, minimized metadata, and concrete audit trails accessed through an authorized observability system.

Never put `ex.getMessage()` straight into JSON, because exception messages can contain database URLs, queries, tokens, or client data. Never enable `server.error.include-stacktrace=always` or `server.error.include-message=always` in production just to debug.

## 12. Actuator and logging levels: avoid opening side channels to diagnose

Spring Boot Actuator provides observability and management endpoints, including sensitive ones like `env`, `configprops`, `heapdump`, `threaddump`, `loggers`, and `mappings`. Never open `management.endpoints.web.exposure.include=*` to the Internet or add `.permitAll("/actuator/**")` during an incident.

When additional metrics/health are needed:

- Expose only endpoints assessed safe on the right network with the right permissions.
- Restrict management interfaces/networks, dedicated roles, and mTLS/VPN per infrastructure—never rely on "obscure paths."
- Audit sanitization of config values and logs; key-name-based sanitization policies can miss custom names.
- Separate viewing or changing log levels from normal app users; never let arbitrary users invoke `loggers`.
- Require change records, TTLs, and monitoring for any temporary adjustment.

Examples to avoid:

~~~properties
# WRONG if applied broadly to "inspect all configuration".
management.endpoints.web.exposure.include=*
management.endpoint.env.show-values=always
logging.level.org.springframework.security=TRACE
~~~

`TRACE`/wire-level logs can capture sensitive data depending on the component. When verbose logging must be enabled for a specific service or request subset, review **what data types will be logged**, viewer permissions, auto-expiring TTLs, sampling, secure channels, and evidence retention rules. **Prefer targeted event logging** over raising the root log level.

## 13. Forbidden workarounds and proper alternatives

| Dangerous workaround | Why it is dangerous | Proper alternative |
|---|---|---|
| `.anyRequest().permitAll()` | Drops all route authorization | Review matchers/chains and fix the specific rule after testing |
| `.requestMatchers("/api/**").permitAll()` | Opens every API, including new endpoints | Enumerate valid routes/methods with `denyAll` fallback |
| `csrf.disable()` on browser apps | Opens CSRF risk when credentials auto-send | Issue/send proper CSRF tokens and test separately |
| `web.ignoring("/**")` | Bypasses filter chain and security headers | Use intentional `permitAll` for public assets; keep chain |
| Disabling password/JWT validation | Admits forged or invalid credentials | Fix issuer/key/audience/clock config with evidence |
| Removing owner/tenant predicates | Opens cross-user/cross-tenant access | Test and fix the exact query/policy |
| Debug login returning raw `Authentication` | Leaks credentials, roles, claims, and IDs | Return minimal booleans/principal fields per permission |
| Dumping `Cookie`/`Authorization` | Leaks sessions/tokens, enabling hijacking | Log cookie-present/auth-scheme booleans and event codes |
| Public `management...include=*` | Leaks config, memory, mappings, log controls | Management network/RBAC + endpoint allowlist |
| Adding a shared `ROLE_ADMIN` user | Breaks auditing and escalates privileges | JIT break-glass approval scoped by person/time/action |
| Disabling WAF/rate limits globally | Expands attack surface mid-incident | Narrow route/signature rules after verification |
| Downloading production DB to a laptop | Expands sensitive-data exposure | Synthetic fixtures or controlled forensic environments |
| Printing exception messages/bodies | Can echo secrets or PII | Enum-based reasons and request IDs |

When an emergency **recovery** change is required, assign an owner, perform a risk review, test, and plan rollback; it **must never be a change that drops authorization checks**. A legitimate route blocked by a bug should be fixed in the matcher or authority mapping—never by adding `/debug?skipAuth=true`.

## 14. Break-glass: emergency support without ad-hoc "temporary admins"

Some incidents genuinely require elevated privileges to restore systems. **Break-glass** is completely different from `permitAll` or handing `ROLE_ADMIN` to all users.

A proper break-glass workflow has:

1. **Clear justification:** incident ID, objective, and specific resource/action; never for everyday convenience.
2. **Independent approver:** per organizational policy, often two-person approval or security on-call.
3. **Individual identity and MFA:** no shared passwords or un-auditable hidden accounts.
4. **Least privilege:** read-only diagnostics where possible; never grant customer-data read access if only status checks are needed.
5. **JIT and short TTL:** auto-expires and is revoked immediately upon completion; never permanent.
6. **Isolated scope:** bounded by service, environment, action, host, and session; may require VPN/mTLS.
7. **Complete yet minimal audit:** who was approved, when, which action category, and outcome; never log raw secrets or payloads.
8. **Dedicated monitoring and post-review:** alerts on grant/revocation, review of executed commands, and runbook updates.

**Never** put into code:

~~~java
// WRONG: query parameter becomes an auth-disabling "switch".
if ("true".equals(request.getParameter("debug"))) {
    return allowEverything();
}
~~~

If a product must support a special recovery operation, build a **dedicated admin command protected at the identity, network, and policy layers** with review/auditing, or use controlled admin infrastructure. Never plant a query/header bypass inside an application endpoint.

## 15. Safe containment when active exploitation is suspected

When signs of credential compromise, token leakage, BOLA, or endpoint abuse appear, containment actions may include:

- Revoking access/refresh tokens, resetting compromised credentials, rotating client secrets or signing keys per runbook, and updating session invalidation.
- Blocking the **specific exploited endpoint/action/traffic pattern**, or switching sensitive features to read-only. Confirm blocks do not blind essential observability.
- Rolling back or rolling out a tightened-policy hotfix while monitoring negative and positive tests.
- Adding targeted rate limits or abuse detection without disabling core security middleware.
- Isolating a suspected compromised instance/service while preserving forensic artifacts in an RBAC-protected store with chain-of-custody.
- Checking tenant/owner scope for object-level authorization bugs, assessing blast radius, and notifying owning teams.

**Never delete logs, wipe container images, flush session stores, or destroy evidence before an incident response plan is in place.** The goal is limiting damage while preserving enough controlled evidence to find the root cause—without replicating secrets during investigation.

If a secret leaked into a log, **do not paste that log into a ticket**. Notify the incident owner, restrict access to the log store, rotate/revoke the secret based on blast radius, identify copies/retention, and handle the data per organizational policy.

## 16. Investigating broken rules/chains without logging entire requests

### Route rules in Spring Security

A `SecurityFilterChain` might look like:

~~~java
// Illustrative config snippet, not a standalone class.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/status").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
        .hasRole("USER")
    .anyRequest().denyAll()
);
~~~

If a valid user receives 403, check:

1. Is the HTTP method actually `GET` or `POST`?
2. Do the route mapping and context path match `/api/orders/{id}`?
3. Does the principal hold a trusted `ROLE_USER` or a differently formatted claim?
4. Did the request enter the right chain? An overly broad/narrow `securityMatcher` or wrong `@Order` can select a different chain.
5. Did service-level object authorization block based on owner/tenant?
6. Was the response emitted by CSRF, `AccessDeniedHandler`, method security, or a downstream exception?

You do not need to log raw `/api/orders/423?token=...` to answer these; use route templates, methods, and request IDs. Artifacts potentially holding customer IDs belong strictly in permissioned forensic stores with clear purpose.

### Multiple SecurityFilterChains

`securityMatcher` scopes the **entire chain**; `requestMatchers` authorizes **within the chain**. `.anyRequest().denyAll()` inside an `/api/**` chain does not protect `/legacy/**` if no fallback chain exists. When investigating unexpectedly open routes, audit the complete chain inventory and order—never "fix" it by broadening `/**` to `permitAll`.

### Method security and proxies

`@PreAuthorize` requires `@EnableMethodSecurity` in the relevant configuration. Internal self-invocation via `this.method()` can bypass AOP interceptors, and invoking services from background jobs or message listeners bypasses HTTP authorization. Enforce policies inside services/repositories and test every sensitive entry point.

## 17. Emitting root-cause signals without leaking data

**Targeted diagnostic codes** emitted by reviewed code/metrics can look like:

~~~text
AUTHN_MISSING
AUTHN_BAD_CREDENTIALS
TOKEN_EXPIRED
TOKEN_VALIDATION_FAILED
AUTHZ_MISSING_AUTHORITY
AUTHZ_OBJECT_DENIED
CSRF_MISSING
CSRF_INVALID
SESSION_NOT_FOUND
CONTEXT_NOT_LOADED
ROUTE_NOT_ALLOWED
RATE_LIMITED
~~~

These codes are **conceptual and illustrative**, not built-in Spring Security enums. When implementing, map explicitly from exception/event types without printing raw exception messages. Public APIs may intentionally return coarser codes to avoid revealing authentication internals.

For correlation across distributed systems:

- The gateway generates or normalizes a trace ID containing no credentials.
- Trusted services propagate the ID over controlled channels; untrusted client-supplied IDs must be validated or renamed.
- Each service logs `event_code`, `route_bucket`, `status`, `service_version`, and `trace_id`—never sending payloads or tokens in tracing baggage.
- Traces/spans are not automatically safe: HTTP semantic attributes, DB statements, span events, and exception attributes can still carry secrets. Configure allowlist-based redaction at collectors/agents.
- Keep metric cardinality low: never put raw user IDs, emails, tokens, or session IDs into metric labels.

A metric like `security_denial_total{reason="MISSING_AUTHORITY",route="ops_status"}` is far more useful than millions of labels carrying distinct users or URLs. When impacted users must be identified, use a separate audit store with proper RBAC and retention rather than stuffing PII into Prometheus labels.

## 18. Regression testing: permissions stay tight and data never leaks

Every incident fix requires both passing **and** failing checks:

| Case | Input | Passing evidence |
|---|---|---|
| Public health | Anonymous `GET /public/health` | 200, no config leaked |
| OPS status | Valid OPS credentials | 200, status-only response |
| OPS status | Valid Viewer credentials | 403, no sensitive diagnostics returned |
| OPS status | Anonymous | 401 per HTTP Basic |
| `/internal/debug` route | Authenticated OPS | 403 because outside allowlist |
| Unexpected method | `POST /api/ops/status` with valid CSRF | Still 403 per policy, no mutating handler |
| Missing CSRF | POST without token | 403, protection stays active |
| Spoofed `X-Role: OPS` header | Viewer sends spoofed header | Still 403 |
| Query/header holding fake secret canary | HTTP test request | Logs and response do not echo canary |
| Production root/logging level | Check deployment config | No reckless `TRACE` or header/payload dumps |
| Actuator, proxy, APM | Smoke test at real entry point | No config/secret leaks or unauthenticated endpoints |
| Read/modify cross-tenant resource | Another tenant's account | Properly denied with zero side effects |
| Rollback | Prior version verified safe | Policy still denies and negative tests pass |

**Never test only status codes.** For mutating endpoints, inspect the DB, queues, caches, and files after rejected requests. A 403 returned **after data was already modified** is not secure.

### Canary test procedure without exposing real secrets

In tests, place a fake marker such as `SENSITIVE_CANARY_NEVER_LOG_THIS` in queries, headers, or bodies under controlled test cases. Afterward, scan **test logs** and responses to verify the marker never appears. The marker is not a real password or token. Never inject production secrets into requests "to test redaction."

**Limitation to disclose:** a canary test does not prove every piece of data is redacted everywhere. Pair it with code reviews, integration tests, ingress/APM config reviews, source/artifact scanning, and post-deploy sampling checks.

## 19. Runbooks by incident category

### 19.1. "Mass 403s in production right after deploy"

- Compare timestamps against changes to `SecurityFilterChain`, `@EnableMethodSecurity`, claims mapping, route matchers, and proxy paths.
- Collect server request IDs, rule/route buckets, methods, authentication-presence booleans, and allowlisted reason codes; avoid printing JWTs just to inspect `roles`.
- Reproduce using a test token/user fixture with equivalent roles and the matching path/method.
- Distinguish `CSRF_INVALID` from `AUTHZ_MISSING_AUTHORITY`: they require different fixes.
- Roll back to a **verified non-permissive release** or hotfix the exact matcher/role; run negative tests with under-privileged principals.
- Never "fix" with `permitAll`, `web.ignoring`, disabling CSRF, or granting temporary ADMIN to everyone.

### 19.2. "JWTs expired, users getting logged out"

- Inspect expiry/issuer/audience, system clocks, JWKS caching, and rotation; distinguish **invalid token** from **unauthorized identity**.
- Log only permitted reason codes and key-version metadata; never log raw JWTs, refresh tokens, or `Authorization` headers.
- If key rotation drifted, coordinate JWKS/issuer overlap per policy; never distribute private keys to resource servers.
- If tokens were compromised, revoke/rotate per incident procedure instead of extending expirations globally or skipping signature checks.

### 19.3. "Session cookies aren't reaching the API"

- Inspect `Set-Cookie` attributes without recording cookie values: `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`, expiry.
- Check browser `fetch(credentials: "include")`, CORS, HTTPS, proxy host/scheme, and the session store.
- Use `getSession(false)` when observing so loggers never create new sessions.
- Never disable `HttpOnly`, `Secure`, or CSRF just so browsers "send the cookie."
- If the app is a stateless Bearer API, requests having no session may be completely intentional.

### 19.4. "User can read documents they don't own"

- Prioritize containment: block the **specific exploited action/route** without opening other permissions.
- Inspect route authn/roles, service ownership/tenant predicates, repository queries, cache keys, and list/export/file endpoints.
- Audit using policy-approved, minimized metadata; identify real resources and callers in an **RBAC-protected forensic store**, never dumping into general logs.
- Add Alice/Bob/cross-tenant tests verifying direct HTTP access and zero side effects on PATCH/DELETE.
- Assess leaked data and notify legal/security teams per policy; never hide the incident merely by hiding a frontend button.

### 19.5. "Logs already captured a session cookie or client secret"

- Restrict access to the log store, preserve evidence per response procedures, and trace emission sources and copies.
- Rotate/revoke affected credentials, log out/invalidate affected sessions, and audit log access and credential abuse.
- Fix the logger/redaction at the source; check ingress, APM, and CI backups too.
- Never paste real secret samples into PRs or tickets to explain the bug; reference field names, approved checksums/fingerprints, or test markers.
- Purge logs/history strictly under retention and forensic policies; **deleting logs does not revoke leaked secrets**.

## 20. Pre-flight review checklist before enabling diagnostics

1. Is there an incident/ticket ID and named owner? What is the concrete investigation goal?
2. Can existing metrics, event codes, and request IDs answer the question without enabling payload dumps?
3. Does any change to authn/authz/CSRF/sessions/proxy/WAF/rate limits **weaken** policy? If yes, reject that approach.
4. Which exact fields are needed? Do any contain tokens, cookies, emails, URL queries, raw bodies, `Authentication` objects, or keys?
5. Could input contain newlines/log-forging payloads or attacker-controlled values?
6. Are routes, methods, and statuses normalized with bounded cardinality?
7. Do logs have RBAC, encryption, retention, viewer auditing, and instrumentation TTLs?
8. Is there a plan to run with synthetic accounts/fixtures and both positive and negative test cases?
9. Is monitoring ready to catch permission drift or secret leakage immediately after rollout?
10. For break-glass access (if unavoidable), are MFA, policy dual approval, JIT TTL, narrow scope, and revocation enforced?
11. Have Actuator, proxy, tracing, APM, CI artifacts, and exception-response policies been reviewed?
12. Is there a schedule and confirming owner to remove temporary instrumentation after the incident?

## 21. Self-check questions

1. Why is `anyRequest().permitAll()` never a valid debugging step when an endpoint returns 403?
2. If a `POST` returns 403, how do you distinguish a missing CSRF token from a missing role **without disabling CSRF**?
3. Why can raw `request.getRequestURI()` and `request.getQueryString()` still leak secrets even when headers are not logged?
4. Why should `JSESSIONID` or a client-supplied `X-Request-ID` never serve as a trusted request correlation ID?
5. If a `SecurityFilterChain` has `securityMatcher("/api/**")`, does it protect `/internal/**`? What must you check?
6. What is dangerous about logging `Authentication.toString()` or a `@ConfigurationProperties` object?
7. Does "getting a 403" prove a request was rejected **before modifying data**? What must tests check?
8. Why can't you rely solely on Spring Boot Actuator sanitization?
9. When a client secret appears in CI logs, why is deleting the log or hiding the line in a ticket insufficient?
10. In an emergency recovery, how must break-glass access differ from a shared `ROLE_ADMIN` account?
11. What are the scope and limitations of a `CapturedOutput` test using a fake canary marker? Which infrastructure layers need separate checks?
12. If a rollback makes 401 errors vanish yet reintroduces a BOLA vulnerability, why is that an unsafe rollback?
13. Why does enabling `logging.level.org.springframework.security=TRACE` in production require a risk assessment and TTL rather than staying on indefinitely?
14. When debugging a browser sending the wrong cookie, what `Cookie`/session-present evidence do you need **without exposing cookie values**?
15. When a user reports being unable to access documents in another tenant, what proves the policy is working properly?

**Conclusion:** during a Spring Security incident, reliable response means **keeping permission boundaries intact, increasing observability via minimized/pseudonymized signals, reproducing with synthetic data, fixing the actual root cause, and verifying with positive/negative tests**. Never trade data protection for debugging convenience: raw secrets do not belong in logs, and "temporarily opening permissions" is not an observability tool.

## Official references

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Exception Handling / Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP — Incident Response Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Incident_Response_Cheat_Sheet.html)
