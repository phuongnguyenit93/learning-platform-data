# Public Error Codes, Correlation IDs, and Operations-Only Details

## 1. Core Objectives and Principles

A user fails to sign in on a Spring Security application. The browser needs to know whether to retry, sign in, perform stronger authentication, or contact support. Operations staff need to know accurately whether the failure involved a nonexistent account, password lockout, unreachable JWKS, overloaded database, or denied policy. **Both audiences must never receive the same level of detail.**

Sound design separates into three tiers:

1. **Public error code:** a stable, bounded, safe identifier for clients to branch logic on—for example, `AUTH_FAILED`, `AUTH_REQUIRED`, `ACCESS_DENIED`. Never reveal sensitive causes.
2. **Correlation/request ID:** an opaque identifier used to locate an exact request in logs/traces without sending stack traces to users. Can be returned in the `X-Request-ID` header and `requestId` body field.
3. **Operations-only details:** actual exception type, failing dependency, failure stage, trace/span, server instance, JWT/MFA verification outcome, internal reason codes, metrics, and audits. These belong in **access-controlled logs/traces**, never copied into public JSON.

In Spring Security, authentication response handling can occur **before a request ever reaches a Spring MVC controller**, so writing `@RestControllerAdvice` alone is not enough. You need `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, and for Bearer APIs you must preserve `WWW-Authenticate` per RFC 6750.

### What Can You Do After This Lesson?

- Separate public codes from internal error reasons and design a versioned code catalog.
- Pick exact HTTP statuses `400/401/403/429/503` without turning every error into 401.
- Generate safe request IDs, record the same ID in responses and structured logs; distinguish request IDs from distributed trace IDs.
- Apply RFC 9457 `application/problem+json` for APIs while preserving OAuth2 Bearer challenge semantics.
- Configure Spring Security Servlet for form login failures, unauthenticated protected APIs, and authenticated-but-forbidden access.
- Prevent user enumeration, token/PII disclosure, log injection, and leakage of operational internals.
- Write a runnable Java 17 demo and a test suite verifying public behavior and internal observability.

**Scope:** Spring Boot 3.x, Spring Security Servlet 6.x, Java 17+. Spring framework snippets are illustrative integration examples requiring appropriate dependencies/configuration; the standalone pure Java 17 program in section 7 compiles directly with `javac` without Spring.

## 2. Response Contract: public code, requestId, and Private Diagnostics

An API response for a failed login can use RFC 9457:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: c1d4e9f5-9fcb-48d2-9e2c-1037560fd229

{
  "type": "https://api.example.test/problems/authentication-failed",
  "title": "Authentication failed",
  "status": 401,
  "detail": "Invalid login credentials.",
  "instance": "urn:uuid:c1d4e9f5-9fcb-48d2-9e2c-1037560fd229",
  "code": "AUTH_FAILED",
  "requestId": "c1d4e9f5-9fcb-48d2-9e2c-1037560fd229"
}
~~~

This is an **application-designed contract**, not the default body of every Spring Security filter. `type` is a URI identifying the problem type; `title` and `detail` carry only safe information; `status` aligns with the HTTP status. `code` and `requestId` are RFC 9457 **extension fields**. `instance` is a URI reference for one occurrence; the example uses a UUID URN without sensitive paths/queries. Never put token values, emails, usernames, or SQL paths into `instance`.

**Important note:** the template above is for **form login/JSON login**. For an OAuth2 Resource Server, requests missing a Bearer token normally require a `WWW-Authenticate: Bearer ...` header; the `error` parameter in the challenge is defined by RFC 6750 and is **distinct from** business error codes like `AUTH_FAILED`.

### Three Practical Data Tiers

| Data | Send to Client? | Store in Logs/Traces? | Notes |
| --- | --- | --- | --- |
| HTTP status | Yes | Yes | Standard semantics; never use 200 for login errors just to hide causes |
| Public code `AUTH_FAILED` | Yes | Yes | Stable name for client handling |
| Text `"Invalid login credentials"` | Yes | Optional | Never state whether account exists, password is wrong, or locked |
| Opaque `requestId` | Yes | Yes | Contains no PII, never acts as a credential |
| `traceId`, `spanId` | Optional, per policy | Yes | For observability/distributed tracing, not required to be exposed |
| `BadCredentialsException` class | No | Yes, categorized | Technical detail for operations |
| `UsernameNotFoundException` | No | Only if needed, restricted | Risks revealing account existence |
| `user_id`/email/IP/User-Agent | Never echo in body | Restricted, protected by policy | PII; never embed directly as request ID |
| Password values, OAuth codes, Bearer tokens, cookies | **No** | **No** | Credentials must be redacted; never store verbatim |
| DB connection strings, internal hosts, stack traces | No | Controlled per incident | Restrict access and retention |
| Predicted account unlock time or lock status | Caution | Possible in security audits | Can become a user-enumeration side channel |

A request ID is **strictly for locating** an event; it does not replace authentication proof, OTPs, or log-viewing permissions. Knowing a `requestId` does not grant a user permission to read another person's stack trace.

## 3. Intentional Public Error Code Catalog

Public codes must remain **stable across internal refactors**, be documented, and clearly classify retryability. Never expose Java class names, SQLSTATEs, microservice names, or detailed password/lockout reasons as public codes.

| HTTP | Application Public Code | What Client Should Understand | Private Reasons May Differ |
| --- | --- | --- | --- |
| 401 | `AUTH_REQUIRED` | Must authenticate before calling protected endpoint | Missing cookie/session/Bearer |
| 401 | `AUTH_FAILED` | Login failed, without distinguishing accounts | UNKNOWN_USER, BAD_PASSWORD, ACCOUNT_LOCKED, BAD_MFA (per threat model) |
| 401 | `INVALID_ACCESS_TOKEN` | Bearer credential invalid; fetch fresh token via proper flow | JWT_SIGNATURE, EXPIRED, BAD_AUDIENCE, REVOKED |
| 403 | `ACCESS_DENIED` | Authenticated yet lacking permission or policy denied | MISSING_SCOPE, DENIED_BY_ACL, TENANT_MISMATCH |
| 400 | `INVALID_AUTH_REQUEST` | Malformed authentication syntax/request | MALFORMED_BEARER_HEADER, INVALID_PARAMETER |
| 429 | `AUTH_RATE_LIMITED` | Too many requests; wait per policy | IP_LIMIT, DEVICE_LIMIT, IDENTITY_LIMIT |
| 503 | `AUTH_SERVICE_UNAVAILABLE` | Authentication service temporarily unavailable | IDP_TIMEOUT, DB_OUTAGE, JWK_PROVIDER_UNAVAILABLE |
| 500 | `INTERNAL_ERROR` | Incident cannot currently be processed | BUG, MISCONFIGURATION, SERIALIZATION_FAILURE |

All codes in the table are **application policy examples**, not generated by Spring out of the box. When clients speak standard OAuth/OIDC, preserve standard codes at the protocol surface; `invalid_token` and `insufficient_scope` are RFC-defined Bearer challenge values, separate from your application's JSON extension catalog.

**Do not conflate 401 and 403:** 401 means missing/invalid credentials (HTTP authentication semantics); 403 usually means authenticated yet lacking permissions. For browser form login, Spring may redirect (302) to the login page instead of returning JSON 401, depending on UX. Never force an HTML UI to return JSON when it needs a redirect. For OAuth2/OIDC `authorization endpoint` or `token endpoint` controlled by a provider, protocol error formats follow their own rules.

**Do not collapse every exception into `AUTH_FAILED 401`:** an upstream IdP/JWKS or database outage is an availability failure that may require 503/5xx and internal alerts. Turning them into 401 forces clients into useless login retries, adds load, and hides outages.

### Public Code Versioning

- Every public code has a name, semantics, HTTP status, client action, owner, and sensitivity classification.
- Add new codes under an API versioning process; clients must fall back to HTTP status when encountering unknown codes.
- Never let clients parse `message/detail` to drive control flow: display text can be localized and tuned for UX.
- Never create separate public codes like `USER_NOT_FOUND`, `PASSWORD_INCORRECT`, or `TOTP_NOT_ENROLLED` on anonymous endpoints if distinguishing them aids account enumeration.
- For **already authenticated** sessions past step-up verification, specific codes such as `REAUTH_REQUIRED` or `MFA_ENROLLMENT_REQUIRED` can be exposed when helpful for UX and without revealing other accounts' states.
- Avoid putting `exception.getMessage()` directly into `detail`; exception messages are not a public contract and may contain PII/secrets.

## 4. HTTP Semantics and Bearer WWW-Authenticate

### Form Login and Session-Based APIs

A `POST /login` request with a nonexistent username, wrong password, locked account, or invalid credentials should return the **same** public message while unauthenticated, per anti-enumeration policy. Spring Security can 302 redirect to `/login?error` for HTML browsers, or a failure handler can return 401 JSON for AJAX login.

An unauthenticated request to a protected resource passes through `AuthenticationEntryPoint`: browsers may receive a login redirect, REST APIs typically 401. An authenticated request missing a role/authority goes through `AccessDeniedHandler`, typically 403. `@RestControllerAdvice` does not handle all security filter chain errors because many are intercepted **before DispatcherServlet**.

### OAuth2 Resource Server — Never Break the Protocol When Adding JSON

RFC 6750 specifies Bearer challenge responses. Sample patterns:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
X-Request-ID: c1d4e9f5-9fcb-48d2-9e2c-1037560fd229
~~~

When no credentials are sent: `WWW-Authenticate` should appear without `error=...`, which could disclose unnecessary information.

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
X-Request-ID: c1d4e9f5-9fcb-48d2-9e2c-1037560fd229
~~~

Expired, malformed, revoked, or bad-signature tokens can all use `invalid_token`. Never emit `JWT_SIGNATURE_INVALID_FOR_TENANT_ACME` publicly. The RFC permits `error_description` where appropriate, yet secrets/claims/user identities must never be included.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
X-Request-ID: c1d4e9f5-9fcb-48d2-9e2c-1037560fd229
~~~

`insufficient_scope` is the protocol error for lacking an appropriate scope. For access denied due to business ACLs (e.g., user A reading user B's resource), returning a specific scope is not necessarily desirable: it can reveal policy or resource existence. Decide between `403` and `404` per threat model and IDOR controls.

Spring Security provides `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` for status/challenge handling; when custom JSON is needed, **delegate** to them to preserve `WWW-Authenticate` instead of returning a JSON map while forgetting headers. Spring's handlers can inspect `BearerTokenError` and choose HTTP statuses per protocol—for example, a malformed Bearer header is sometimes 400—so do not assume every invalid request returns 401.

### Automatic Retries Carry Risk

`401 invalid_token` can normally prompt a client to request a **new access token** via the OAuth flow; it does not mean a browser should resubmit passwords endlessly. `403` should not auto-refresh Bearer tokens and retry forever when lacking scope. `429` requires rate-limit handling, considering `Retry-After` if it does not open a side channel. `503` needs exponential backoff/circuit breaking, never turning into credential stuffing.

## 5. Preventing Leaks via Responses and Timing

OWASP recommends **generic authentication error messages**. Unauthenticated users must never be able to deduce whether an account exists, a password is wrong, an account is disabled/locked, or the exact remaining attempt count.

Unsafe example:

~~~json
{
  "code": "USER_NOT_FOUND",
  "message": "No user alice@example.test found",
  "userId": null,
  "sql": "select * from users where email=..."
}
~~~

Safer example:

~~~json
{
  "code": "AUTH_FAILED",
  "message": "Invalid login credentials.",
  "requestId": "c1d4e9f5-9fcb-48d2-9e2c-1037560fd229"
}
~~~

**Matching bodies alone is not enough:** differing HTTP statuses, response lengths/redirects, headers, caching behavior, and latencies can still leak account existence. If a nonexistent user is rejected instantly while an existing user runs an expensive password hash, attackers can measure timing; apply proper verification (such as dummy hash comparisons), rate limiting, monitoring, and timing analysis for your threat model.

Content constraints:

- Never return stack traces, exception classes, source files, line numbers, SQL queries, detailed token claims, or internal hostnames/private IPs.
- Never echo raw `Authorization` headers, `Cookie` headers, request body passwords/OTPs, OAuth authorization codes, refresh tokens, recovery codes, or MFA seeds.
- Never embed sensitive usernames/emails/userIds in correlation IDs: request IDs should be opaque and identity-free.
- If accepting a `traceId` from a public request header, validate format, length, and trust boundaries; never treat arbitrary client-supplied strings as server-verified IDs.
- Set `Cache-Control: no-store` on authentication responses holding sensitive data across all appropriate proxy hops.
- Never tell anonymous users "provider X is timing out" if that helps probe internal architecture; publicly, stating the service is temporarily unavailable suffices.
- Support messages should say "please provide the request ID" rather than "send a full screenshot containing your token".
- Never pass private details through `?error=SQLException...` or URL redirects to untrusted domains.

Policies may differ for self-service after a user completes strong authentication (allowed to see *their own* MFA status details). What matters is **controlling context and viewing permissions**, not hiding every state in all situations.

## 6. Correlation ID, Trace ID, and Audit Event ID

A **requestId** ties to **one HTTP request**. A **traceId** (e.g., OpenTelemetry/W3C Trace Context) can span multiple spans and services. An **auditEventId** ties to a business security event such as a failed login or authentication-method change; a single request may emit multiple audit events.

~~~text
Browser
 POST /login
   |
   | X-Request-ID: 589d...  (server generated)
   v
Gateway -> Auth service -> User store / IdP
             |               |
             | trace_id=T-17 |
             | span_id=S-2   |
             |               |
             + audit_event_id=E-42
   |
   v
Response:
  requestId=589d...
  publicCode=AUTH_FAILED

Restricted logs:
  request_id=589d...
  trace_id=T-17
  audit_event_id=E-42
  internal_reason=UNKNOWN_USER
  result=FAILURE
~~~

IDs in the diagram are illustrative notation. In real HTTP traffic, a request ID should be a random UUID or opaque ID generated by a trusted server/gateway; `traceId` follows the tracing system's format rather than concatenating username and timestamp.

### Generating, Propagating, and Sanitizing

- At the ingress edge, **generate a fresh request ID** or accept the header only from a **trusted gateway** after allowlist, length, and format validation. Internet clients must not force an ID to spoof logs.
- Store the ID in a request attribute and response header, and put it in MDC/structured logger for the request scope. In Java servlet thread pools, **always clear MDC in `finally`** so subsequent requests do not inherit stale labels.
- With async processing or executors, MDC does not automatically propagate across threads. Controlled context propagation is required; otherwise async logs lose correlation or carry wrong context.
- Across services, distinguish trusted distributed-tracing context from custom request IDs; use W3C `traceparent` / `tracestate` via OpenTelemetry/Micrometer when deployed.
- Never feed client-provided request IDs unescaped into SQL queries or log lines; block CR/LF and control characters to prevent **log injection**.
- Generate the ID before auth-handling filters so both `AuthenticationFailureHandler` and `AuthenticationEntryPoint` see the same ID.
- Never promise a request ID will always locate long-term logs: retention/sampling/incident policies vary; auditing sensitive events must not rely solely on trace sampling.

### Structured Operations Logs

Example event **strictly inside restricted-access logging**, never sent verbatim to clients:

~~~json
{
  "timestamp": "2026-11-06T03:27:18Z",
  "service": "auth-api",
  "environment": "production",
  "event_type": "authentication.failure",
  "request_id": "c1d4e9f5-9fcb-48d2-9e2c-1037560fd229",
  "trace_id": "d7390c4f0e8541b682512646b49263e7",
  "public_code": "AUTH_FAILED",
  "internal_reason": "BAD_PASSWORD",
  "http_status": 401,
  "principal_ref": "hmac-sha256:restricted-pseudonym",
  "result": "DENIED"
}
~~~

This is an illustrative log entry. `principal_ref` requires HMAC/pepper and key/rotation policies when pseudonymizing; plain hashes of emails can be vulnerable to dictionary attacks. When a username does not exist, do not invent a fake `user_id` that causes confusion. IP, user-agent, email addresses, and geolocation are sensitive data requiring retention policies. `trace_id` can sometimes be untrusted input; sanitize and bound its length.

### Who Can View Private Details?

- Clients/public support see only safe codes and request IDs.
- On-call/triage staff have role-based permission to search redacted logs and audits, with lookup activity logged.
- Security analysts can view reason codes, rate-limit signals, and alerts on a need-to-know basis.
- Access to stack traces/protected PII must be tightly restricted, with retention, masking, and audit trails.
- Public dashboards must never allow querying logs by requestId without authentication/authorization. Never turn a request ID into a "password" unlocking error pages.

**Section conclusion:** correlation IDs bridge the two perspectives; they must never be used to leak the operational view into public responses.

## 7. Standalone Java 17: Mapping Internal Failures to a Public Contract

The following example uses **pure JDK 17**, requiring no Maven, Spring, or server. It illustrates cases where distinct internal reasons produce identical public responses. The request ID is passed in from the request boundary, never derived from an email. The code performs no logging and is not a real authentication system.

Save `PublicAuthErrorsDemo.java`:

~~~java
import java.util.List;
import java.util.Objects;

public class PublicAuthErrorsDemo {

    enum InternalFailure {
        UNKNOWN_USER,
        WRONG_PASSWORD,
        ACCOUNT_LOCKED,
        NO_CREDENTIAL,
        BAD_BEARER_TOKEN,
        NOT_ENOUGH_PERMISSION,
        TOO_MANY_ATTEMPTS,
        IDP_UNAVAILABLE
    }

    record PublicError(
            int httpStatus,
            String code,
            String message,
            String requestId) {

        PublicError {
            Objects.requireNonNull(code);
            Objects.requireNonNull(message);
            Objects.requireNonNull(requestId);
        }
    }

    static PublicError toPublic(
            InternalFailure failure, String requestId) {
        Objects.requireNonNull(failure);
        Objects.requireNonNull(requestId);

        return switch (failure) {
            // Do not reveal whether the account exists or is locked.
            case UNKNOWN_USER, WRONG_PASSWORD, ACCOUNT_LOCKED ->
                new PublicError(
                    401, "AUTH_FAILED",
                    "Invalid login credentials", requestId);

            case NO_CREDENTIAL ->
                new PublicError(
                    401, "AUTH_REQUIRED",
                    "Authentication required", requestId);

            case BAD_BEARER_TOKEN ->
                new PublicError(
                    401, "INVALID_ACCESS_TOKEN",
                    "Invalid authentication credentials", requestId);

            case NOT_ENOUGH_PERMISSION ->
                new PublicError(
                    403, "ACCESS_DENIED",
                    "Access denied", requestId);

            case TOO_MANY_ATTEMPTS ->
                new PublicError(
                    429, "AUTH_RATE_LIMITED",
                    "Please try again later", requestId);

            case IDP_UNAVAILABLE ->
                new PublicError(
                    503, "AUTH_SERVICE_UNAVAILABLE",
                    "Service temporarily unavailable", requestId);
        };
    }

    public static void main(String[] args) {
        String requestId = "req-0007";
        List<InternalFailure> attempts = List.of(
            InternalFailure.UNKNOWN_USER,
            InternalFailure.WRONG_PASSWORD,
            InternalFailure.ACCOUNT_LOCKED,
            InternalFailure.NO_CREDENTIAL,
            InternalFailure.NOT_ENOUGH_PERMISSION,
            InternalFailure.IDP_UNAVAILABLE
        );

        for (InternalFailure failure : attempts) {
            PublicError response = toPublic(failure, requestId);
            System.out.println(
                failure + " => " + response.httpStatus()
                + " " + response.code()
                + " " + response.requestId());
        }

        PublicError unknown =
            toPublic(InternalFailure.UNKNOWN_USER, requestId);
        PublicError wrongPassword =
            toPublic(InternalFailure.WRONG_PASSWORD, requestId);

        System.out.println(
            "samePublicLoginResponse="
            + unknown.equals(wrongPassword));
    }
}
~~~

Run:

~~~bash
javac PublicAuthErrorsDemo.java
java PublicAuthErrorsDemo
~~~

**Exact stdout** from the code (no randomness/time):

~~~text
UNKNOWN_USER => 401 AUTH_FAILED req-0007
WRONG_PASSWORD => 401 AUTH_FAILED req-0007
ACCOUNT_LOCKED => 401 AUTH_FAILED req-0007
NO_CREDENTIAL => 401 AUTH_REQUIRED req-0007
NOT_ENOUGH_PERMISSION => 403 ACCESS_DENIED req-0007
IDP_UNAVAILABLE => 503 AUTH_SERVICE_UNAVAILABLE req-0007
samePublicLoginResponse=true
~~~

In production, real requests must have **unique request IDs**. Fixing `req-0007` in the demo is solely to keep stdout deterministic. The final check shows `UNKNOWN_USER` and `WRONG_PASSWORD` map identically across the entire public record given the same ID; that says nothing about timing/HTTP headers in a real system.

Key takeaways:

- Public codes differ from the **InternalFailure enum**; never serialize the internal enum externally.
- Status/code choices are application policy and can be tuned for protocol accuracy at each endpoint.
- On `IDP_UNAVAILABLE`, return 503 instead of 401 to preserve the distinction between bad credentials and operational outages.
- When using OAuth Bearer, `WWW-Authenticate` must also be set per RFC 6750; the standalone program illustrates body semantics only and does not replace filters.
- Demo messages intentionally omit account-specific details and are not production multi-language copy.

## 8. Spring Boot 3 / Spring Security 6: Recording Request IDs and Returning Safe JSON

### 8.1. Do Events Happen in Filters or MVC?

~~~text
Incoming HTTP request
        |
        v
Request ID servlet filter (before Spring Security)
        |
        v
Spring Security FilterChain
        |
        +-- POST /login, wrong password
        |      -> UsernamePasswordAuthenticationFilter
        |      -> AuthenticationFailureHandler
        |
        +-- GET /api/private, missing credentials
        |      -> AuthorizationFilter denies
        |      -> ExceptionTranslationFilter
        |      -> AuthenticationEntryPoint (401/challenge)
        |
        +-- GET /api/admin, authenticated yet lacking scope
        |      -> AuthorizationFilter denies
        |      -> ExceptionTranslationFilter
        |      -> AccessDeniedHandler (403)
        |
        +-- Bearer JWT malformed/expired
        |      -> BearerTokenAuthenticationFilter
        |      -> AuthenticationEntryPoint / Bearer challenge
        |
        +-- MVC Controller/Service error
               -> @ControllerAdvice / ErrorResponse/ProblemDetail
~~~

`@RestControllerAdvice` handles MVC errors, yet **does not automatically cover Spring Security filter failures** occurring before DispatcherServlet. Some exceptions may be thrown inside method security and follow other handlers; concrete integration tests are needed. There is no default "single `@ExceptionHandler` catching all auth errors".

### 8.2. Request ID Filter Placed Before Security

The snippet below is a **standalone Java class in a Spring Boot Servlet project**, requiring `spring-boot-starter-web` and SLF4J/MDC logging. Create `RequestIdFilter.java` in the application package:

~~~java
package example;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String ATTRIBUTE = "requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // Server-generated: do not trust client-sent X-Request-ID.
        String requestId = UUID.randomUUID().toString();

        request.setAttribute(ATTRIBUTE, requestId);
        response.setHeader("X-Request-ID", requestId);

        MDC.put("requestId", requestId);
        try {
            chain.doFilter(request, response);
        } finally {
            // Servlet threads are reused; avoid leaking into the next request.
            MDC.remove("requestId");
        }
    }
}
~~~

Limitations: the example generates **one ID per HTTP request**. Trusted gateways may already generate IDs; when preserving an ID across hops, accept/forward headers only from verified sources and validate format/length. With async dispatches and executors, configure dedicated context propagation: MDC is ThreadLocal and does not cross threads automatically. `@Order(HIGHEST_PRECEDENCE)` places the Servlet filter before security; verify actual registration order in the app and avoid running the filter twice if manually adding the bean to a chain as well.

### 8.3. Public Problem Details Writer

Spring Framework supports `ProblemDetail` and RFC 9457 in Spring MVC. However, inside Servlet security filters, you can write JSON directly **after verifying the response is not committed**, guaranteeing consistent public codes.

The example below is a **utility used in a Spring Boot app with Jackson**. Create `PublicAuthErrorWriter.java`:

~~~java
package example;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.stereotype.Component;

@Component
public class PublicAuthErrorWriter {

    private final ObjectMapper mapper;

    public PublicAuthErrorWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void write(HttpServletRequest request,
                      HttpServletResponse response,
                      int status, String code,
                      String publicTitle, String publicDetail)
            throws IOException {

        if (response.isCommitted()) {
            return;
        }

        Object stored = request.getAttribute(RequestIdFilter.ATTRIBUTE);
        String requestId = stored instanceof String text
            ? text
            : UUID.randomUUID().toString();

        response.setStatus(status);
        response.setContentType("application/problem+json");
        response.setCharacterEncoding("UTF-8");
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("X-Request-ID", requestId);

        // Map does not guarantee key order; JSON serializer decides.
        // instance excludes path/query that might contain tokens/PII.
        Map<String, Object> problem = Map.of(
            "type", "https://api.example.test/problems/" + code.toLowerCase(),
            "title", publicTitle,
            "status", status,
            "detail", publicDetail,
            "instance", "urn:uuid:" + requestId,
            "code", code,
            "requestId", requestId
        );

        mapper.writeValue(response.getOutputStream(), problem);
    }
}
~~~

**About `instance`:** in the filter example, requestId is always a real UUID from `RequestIdFilter`, so `urn:uuid:<uuid>` is valid. The fallback UUID handles the case where the filter did not run as assumed. If using non-UUID requestIds from another system, use another valid URI reference rather than prepending `urn:uuid:` to arbitrary strings. The example `type` is an illustrative URI; production must use an organization-managed namespace with stable documentation.

`Map.of` outputs valid bodies without guaranteeing property order; clients must parse JSON by key name. Never pass `Exception` into the writer, and never splice `exception.getMessage()` into `detail`.

### 8.4. Wiring Handlers at the Right Spring Security Extension Points

A clean configuration for a REST Bearer API (resource server) and web form is **two `SecurityFilterChain`s**. File `SecurityErrorConfig.java`:

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityErrorConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http, PublicAuthErrorWriter writer)
            throws Exception {

        var bearer401 = new BearerTokenAuthenticationEntryPoint();
        var bearer403 = new BearerTokenAccessDeniedHandler();

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Only for APIs authenticating via Authorization: Bearer;
            // do not apply to endpoints that also use browser cookies.
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth -> oauth
                .authenticationEntryPoint((req, res, ex) -> {
                    bearer401.commence(req, res, ex);
                    // Preserve RFC 6750 status and WWW-Authenticate.
                    if (!res.isCommitted()) {
                        int status = res.getStatus();
                        String code = status == 400
                            ? "INVALID_AUTH_REQUEST"
                            : "INVALID_ACCESS_TOKEN";
                        writer.write(req, res, status, code,
                            "Authentication required",
                            "Invalid authentication request.");
                    }
                })
                .accessDeniedHandler((req, res, ex) -> {
                    bearer403.handle(req, res, ex);
                    if (!res.isCommitted()) {
                        writer.write(req, res, res.getStatus(),
                            "ACCESS_DENIED",
                            "Access denied",
                            "You do not have permission to perform this action.");
                    }
                })
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(
            HttpSecurity http, PublicAuthErrorWriter writer)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                // JSON login UX: differs from web pages needing redirects.
                .failureHandler((req, res, ex) ->
                    writer.write(req, res,
                        HttpServletResponse.SC_UNAUTHORIZED,
                        "AUTH_FAILED",
                        "Authentication failed",
                        "Invalid login credentials.")))
            .build();
    }
}
~~~

**This is an illustrative configuration**, not a copy/paste production template needing no testing. Running Bearer JWT requires `spring-boot-starter-oauth2-resource-server`, issuer/JWK, `JwtDecoder`, and proper validators; form login requires a user store, CSRF form setup, and session/cookie security. Never use `.csrf(disable)` in `webChain`. If a project uses only HTML web forms, `AuthenticationFailureHandler` should redirect to a **generic** error page instead of forcing clients to receive JSON; routes and `Accept` should be clearly designed.

**Note for Bearer:** `BearerTokenAuthenticationEntryPoint` can return **status 400 or 401 depending on `BearerTokenError`**. The example preserves the status while mapping simple JSON codes; when no token is present, you may pick `AUTH_REQUIRED` instead of `INVALID_ACCESS_TOKEN` if app policy requires it, classifying safely **based on the authentication outcome** without reading/echoing raw tokens. For 403, `BearerTokenAccessDeniedHandler` can emit `insufficient_scope` when authentication qualifies; the writer must never remove/alter `WWW-Authenticate` written by the handler.

Test coordination across multiple security chains, the `oauth2ResourceServer` DSL, and `exceptionHandling`, as entry point configuration can vary by route and version. Never assume security filters always invoke `@ControllerAdvice`. Logging exception details must happen **internally** and strictly stay out of the writer.

### What Information May Be Logged Inside Handlers?

Log only **sanitized metadata**, such as event type, allowlisted internal reason code, requestId/MDC trace ID, HTTP status, timestamp, policy-compliant account pseudonym, and route template. Never log `ex.toString()` indiscriminately or keep raw `Authorization` in context. When stack traces are needed to investigate `503/500` faults, send them to restricted-access logs with sanitization/retention rather than user-facing JSON.

### Where Does @ControllerAdvice Fit?

In MVC, you can use `@RestControllerAdvice` and `ProblemDetail.forStatus(...)` / `ResponseEntityExceptionHandler` to return the same contract for controller errors. Yet Spring Security filter errors and login failures still need handlers on the filter chain. If sharing error serialization, extract a `PublicErrorFactory` usable by both MVC and filters, **without making the Servlet security flow depend on DispatcherServlet**.

## 9. Mandatory Test Cases

| Test | Expected Outcome |
| --- | --- |
| Nonexistent username | Exact same public code/body/status as wrong password, no username leak |
| Wrong password | Same response as nonexistent account; private reason audited separately |
| Account locked/disabled | Generic response on anonymous login per threat model, no status leak |
| Protected REST missing token | 401 + Bearer `WWW-Authenticate`; includes requestId |
| Invalid/expired Bearer token | Typically 401 + `invalid_token`, body holds no JWT/claims |
| Malformed Bearer | Exact `BearerTokenError` status/challenge, do not force 401 if spec mandates 400 |
| Missing scope, authenticated token | 403; `insufficient_scope` when semantically appropriate |
| Business ACL denial | 403 or 404 per policy, no owner/resource disclosure |
| Brute-force over threshold | 429/anti-automation control, no account existence leak |
| IdP/JWK/DB unavailable | 503/5xx and alert, never fake `AUTH_FAILED 401` |
| Request ID in header/body | Same server-generated value |
| Input `X-Request-ID` with CRLF / too long | No log pollution; server issues valid ID |
| Concurrent requests | Correlation IDs never cross between Servlet threads |
| Async tasks | Proper context propagation or explicit missing-context log, no stale MDC |
| MVC exception | Public ProblemDetail per contract, no stack trace leak |
| Exception in security filter | Still produces safe body/headers despite skipping ControllerAdvice |
| Authorization grant lacks scope | Never lets client retry endlessly |
| OAuth callback failure | Never exposes authorization code, `state`, `nonce`, or IdP tokens |
| Security telemetry | Logs contain requestId + internal reason without secrets |
| Support lookup | RequestId searchable only by authorized staff, with lookup audit |

### MockMvc Test Snippets (Not a Standalone Class)

In a project with Spring Security Test, `MockMvc mvc`, JWT test config, and matching test controllers:

~~~java
// 1. Missing Bearer token.
mvc.perform(get("/api/admin/report"))
   .andExpect(status().isUnauthorized())
   .andExpect(header().exists("X-Request-ID"))
   .andExpect(header().string(
       "WWW-Authenticate",
       org.hamcrest.Matchers.startsWith("Bearer")));

// 2. Mocked JWT Authentication lacking admin scope.
mvc.perform(get("/api/admin/report")
       .with(jwt().authorities(
           new SimpleGrantedAuthority("SCOPE_read"))))
   .andExpect(status().isForbidden());

// 3. Never expose exception class in public body.
mvc.perform(post("/login")
       .param("username", "someone")
       .param("password", "wrong")
       .with(csrf()))
   .andExpect(status().isUnauthorized())
   .andExpect(jsonPath("$.code").value("AUTH_FAILED"))
   .andExpect(jsonPath("$.requestId").isString());
~~~

The snippets above **require static imports, MockMvc context, user store, and real routes**. Spring Security Test's `jwt()` mocks Authentication: it **does not verify real JWT signatures**. To verify `invalid_token` and JWT validators, use a real decoder/test keys, send properly/improperly signed Bearer tokens, and assert the HTTP challenge. Never assert only `401` and call a response safe; also assert headers, body redaction, timing, logs, and no-store.

### Unit Testing Public Error Code Mapping

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PublicAuthErrorsDemoTest {

    @Test
    void unknownUserAndWrongPasswordHaveSamePublicResponse() {
        String id = "req-1";
        assertEquals(
            PublicAuthErrorsDemo.toPublic(
                PublicAuthErrorsDemo.InternalFailure.UNKNOWN_USER, id),
            PublicAuthErrorsDemo.toPublic(
                PublicAuthErrorsDemo.InternalFailure.WRONG_PASSWORD, id)
        );
    }

    @Test
    void backendOutageIsNotReportedAsWrongPassword() {
        var result = PublicAuthErrorsDemo.toPublic(
            PublicAuthErrorsDemo.InternalFailure.IDP_UNAVAILABLE,
            "req-2");
        assertEquals(503, result.httpStatus());
        assertEquals("AUTH_SERVICE_UNAVAILABLE", result.code());
    }
}
~~~

This is a JUnit 5 class in the same package as the pure Java demo, requiring Jupiter dependencies. Mapping tests do not verify filters, trace propagation, SQL/IdP, or log security.

## 10. Operational Workflow: Receiving a Correlation ID and Handling Safely

A support workflow:

1. Client displays: "Authentication failed. Request ID: `c1d4e9f5-...`". No internal reason shown.
2. Support receives the ID and verifies access permissions; never ask the user to send passwords, OTPs, or screenshots containing access tokens.
3. Search for requestId in the log index by time window/tenant; if logs are missing due to sampling/retention, state that limitation instead of guessing.
4. Correlate with `trace_id`, `audit_event_id`, internal reason code, and dependency status; determine whether it is a user-enumeration attack, DB outage, or token validation failure.
5. Operations creates an incident/alert or remediates per runbook. Unlocking accounts, resetting MFA, changing passwords, or issuing tokens **must never** be performed solely on the basis of a requestId.
6. Once resolved, update public status/message if needed without placing stack traces/PII in reply emails.

### Meaningful Metrics and Alerts

- `authentication.failure.count` grouped by **internal reason category**, never using usernames/raw emails as metric labels.
- Ratios of `401`/`403`/`429`/`5xx`, login SLOs, latency, and success rates across methods (password/OIDC/MFA).
- IdP/JWK/LDAP outages and timeouts, retry storms; lockout/brute-force detection using account pseudonyms in security systems.
- Consecutive failures per principal or IP per anti-abuse policy; avoid recording PII in public analytics.
- Alert on anomalous authentication failure spikes or rising 503 errors, carrying redacted requestId/traceId context.

**Caution with logs/traces:** the OWASP Logging Cheat Sheet recommends never storing raw passwords, session identifiers, access tokens, encryption keys, or unnecessary sensitive data; protect logs with access controls, retention, integrity, time synchronization, and monitoring. Correlation IDs are valuable, yet never turn logging into a substitute for security auditing.

## 11. Common Design Mistakes

1. Sending `exception.getMessage()` or stack traces to clients: can expose SQL schemas, hosts, providers, account state, and secrets.
2. Creating public codes `USER_NOT_FOUND`, `WRONG_PASSWORD`, `ACCOUNT_LOCKED` on anonymous login: user enumeration.
3. Normalizing only the body while neglecting HTTP status, headers/redirects, or timing: discrepancies still leak.
4. Returning `200 OK` for all auth errors: clients/caches/proxies and monitoring misinterpret semantics.
5. Returning `401` for DB/JWK outages: masks incidents, causes credential retries, and hinders operations.
6. Turning insufficient-permission `403` into `401`: clients infinitely refresh access tokens without resolving policy.
7. Adding JSON for Bearer while dropping `WWW-Authenticate`: breaks OAuth2 client expectations.
8. Using `@RestControllerAdvice` for all Spring Security errors: some failures are blocked before MVC.
9. Trusting raw `X-Request-ID` sent by browsers: log injection, ID spoofing, unbounded length.
10. Forgetting to clear MDC in `finally`: old user/request metadata bleeds into another request.
11. Logging full HTTP headers/request bodies: exposes passwords, bearer/refresh tokens, cookies, OTPs.
12. Attaching usernames/emails/tokens to metric labels: leaks data, explodes cardinality and cost.
13. Leaving requestId detail lookup endpoints unprotected: turns an opaque ID into a doorway to private logs.
14. Treating `requestId` as account-recovery proof: it is neither a credential nor proof of ownership.
15. Skipping tests across multiple HTML/API chains and 401/403/429/503 distinctions: API contracts drift by filter.
16. Having clients parse localized messages instead of stable public codes: breaks easily when wording changes.
17. Reusing one correlation ID for every request in a session: fails to distinguish attempts and creates continuous linkage leakage.
18. Treating RFC 9457 `instance` as a place for full URLs: can leak tokens in query strings, paths, or PII.

## 12. Completion Checklist

- [ ] Public code catalog has defined semantics and versioning; never reflects raw internal exceptions.
- [ ] Anonymous login failures return identical responses for bad username/password/locked per threat model.
- [ ] 401, 403, 400, 429, and 503 are clearly distinguished; HTML browser redirects are designed separately.
- [ ] OAuth2 Bearer responses preserve `WWW-Authenticate` and appropriate RFC 6750 parameters.
- [ ] Correlation IDs are generated by trusted server/gateway, opaque, and identical across headers/body/logs.
- [ ] Request IDs are never used as authorization for ops tools or recovery credentials.
- [ ] Structured logs include internal reasons, request/trace/audit IDs, and retention/access controls; zero secrets.
- [ ] MDC is cleaned up with try/finally; async context propagation is tested.
- [ ] Spring Security `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, and MVC errors return a consistent contract.
- [ ] Production tests check user enumeration via status/body/headers/timing and error info leakage.
- [ ] Support runbooks, alerts, and audits exist for incident lookups by requestId.

**Summary:** the public side needs only **a programmatic error code + generic message + opaque correlation ID**, matching HTTP/OAuth protocols; the operations side needs **access-controlled reason codes, traces, metrics, and audits**. Bridging both views with a request ID without exposing Java exceptions or secrets to the API is how you build authentication responses that are both useful and secure.

## 13. Official Documentation and Security Practices

- Spring Security — `ExceptionTranslationFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html
- Spring Security — Form Login Failure Handling: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — OAuth2 Resource Server Bearer: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html
- Spring Security API — `BearerTokenAuthenticationEntryPoint`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html
- Spring Security API — `BearerTokenAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html
- Spring Framework — Error Responses and `ProblemDetail`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
- RFC 6750 — Bearer Token Usage, Section 3: https://www.rfc-editor.org/rfc/rfc6750.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- W3C — Trace Context: https://www.w3.org/TR/trace-context/
