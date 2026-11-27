# Correlated Logs, Traces, and Redacting Tokens, Secrets, and Sensitive Claims

## 1. Why Must Logging and Tracing Be Designed Together with Security?

A Resource Server typically sits among many components: API Gateways, client applications, Authorization Servers, internal services, and databases. When a request fails, operations teams need to know where the request traveled, how long it took, which step rejected it, and which service caused the error.

Yet logs and traces are also common places where credentials leak. A single log line containing an Authorization header, refresh token, client secret, or full JWT claims can turn an observability platform into a sensitive data store. Far more people often have log-reading access than access to production tokens.

The goal of this lesson is providing enough context to investigate incidents without storing credentials or unnecessary personal data:

- Correlate logs and traces across requests using request IDs, trace IDs, and span IDs.
- Emit structured authentication and authorization events.
- Log only allowlisted fields instead of dumping requests, Authentication objects, or JWTs.
- Mask or exclude tokens, secrets, cookies, and sensitive claims at every logging layer.
- Propagate trace context across services without putting credentials into baggage.
- Verify with tests that logs never contain secret values.

## 2. Distinguishing Request ID, Trace ID, and Span ID

These three identifiers are related, but not interchangeable.

| Identifier | Scope | Used For |
| --- | --- | --- |
| Request ID | A single request or business transaction per application convention | Finding all logs tied to a request. |
| Trace ID | A distributed trace, potentially spanning many services | Grouping all spans belonging to a request journey. |
| Span ID | A specific operation within a trace | Identifying the service/operation emitting logs or latency. |

Example:

```text
Browser
  │ request.id = req-7f2a
  │ trace.id   = 4bf92f3577b34da6a3ce929d0e0e4736
  ▼
API Gateway
  │ span.id = 00f067aa0ba902b7
  ▼
Orders API
  │ span.id = 7a085853722dc6d2
  ▼
Inventory API
  │ span.id = 2e4b8c1a7f90d311
  ▼
Database
```

A trace can hold many spans. Each service logs the shared trace ID and the current operation's span ID. The request ID may be preserved end-to-end or regenerated at each boundary by convention, as long as a clear mapping exists.

### 2.1. A Request ID Is Not a Credential

A request ID is purely a correlation identifier. It does not prove user identity, grant permissions, or serve as a session ID or bearer credential.

If accepting an `X-Request-ID` header from callers:

- Treat it as untrusted input.
- Restrict length and character set.
- Disallow newlines and control characters.
- Replace invalid values with a system-generated ID.
- Never use it as an authorization key, permission cache key, or idempotency token without a dedicated contract.

For Internet-facing requests, organizations may choose to always generate an internal request ID and record the gateway-supplied ID in a separate validated field.

### 2.2. A Trace ID Is Not Proof of Authentication

W3C Trace Context defines `traceparent` and `tracestate` to propagate trace data between processes. They serve observability, not an identity protocol.

Never use trace IDs, span IDs, or baggage to decide:

- Whether a user can access a resource.
- Whether a calling service is trusted.
- Whether a token is valid.
- Who the tenant or subject is.

Authorization still rests on verified Authentication and policy.

## 3. Generating Request IDs and Managing MDC in Servlet Stacks

With Spring MVC/Servlet, a `OncePerRequestFilter` can generate or validate the request ID and place it in SLF4J MDC. MDC lets loggers automatically attach correlation fields to logs on the same thread.

Example:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
public class RequestIdFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-Request-ID";
    private static final String MDC_KEY = "requestId";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String supplied = request.getHeader(HEADER);
        String requestId = isSafe(supplied)
                ? supplied
                : UUID.randomUUID().toString();

        String previous = MDC.get(MDC_KEY);
        MDC.put(MDC_KEY, requestId);
        response.setHeader(HEADER, requestId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, previous);
            }
        }
    }

    private boolean isSafe(String value) {
        return value != null && SAFE_ID.matcher(value).matches();
    }
}
```

The `finally` block is mandatory. Servlet containers reuse threads; failing to clear or restore MDC can cause subsequent requests to log the previous request's ID.

### 3.1. Register the Filter Exactly Once

If a filter is declared as a Spring `Filter` bean and also manually added to the `SecurityFilterChain`, it may run twice because both the servlet container and the security chain register it.

Choose one registration mechanism:

- Register at the servlet container level so the request ID is available even before the security chain.
- Or register inside the `SecurityFilterChain` at a specific position.

Do not leave auto-registration active while also adding the filter to the chain without disabling the other registration.

### 3.2. Echo Only Validated IDs

The response header helps callers and operations teams reference the same request ID. Echo only validated values into responses. If you need to keep both a gateway-supplied ID and an internal ID, use two distinct fields, such as `requestId` and `upstreamRequestId`.

Never put arbitrary header values into MDC or responses without character and length restrictions.

## 4. Using Micrometer Tracing and W3C Trace Context

In Spring Boot with Micrometer Observation/Tracing, an application can integrate a tracer and exporter (such as OpenTelemetry or Brave) to create traces/spans and propagate trace context across instrumented clients.

With an appropriate tracing bridge, trace IDs and span IDs are typically populated into MDC per the application's logging configuration. Log patterns can reference `traceId` and `spanId`; exact key names depend on the bridge and configuration.

Illustrative Logback pattern:

```xml
<pattern>
  %d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX}
  %-5level
  [%thread]
  [requestId=%X{requestId}]
  [traceId=%X{traceId}]
  [spanId=%X{spanId}]
  %logger{36} - %msg%n
</pattern>
```

This pattern is illustrative. Verify the exact MDC keys used by your actual bridge before configuring.

### 4.1. Propagating Trace Context Across HTTP Clients

When an HTTP client is instrumented by Micrometer Observation/Tracing, W3C trace context can be injected into outbound requests. On the target service, instrumentation extracts the context and starts a child span.

```text
Orders API
  trace.id = 4bf92f3577b34da6a3ce929d0e0e4736
  span.id  = 7a085853722dc6d2
       │
       │ traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-7a085853722dc6d2-01
       ▼
Inventory API
  trace.id = 4bf92f3577b34da6a3ce929d0e0e4736
  span.id  = 2e4b8c1a7f90d311
```

The `traceparent` header contains version, trace ID, parent span ID, and trace flags. It does not contain access tokens. Even so, never insert tokens, emails, subjects, or sensitive data into `tracestate` or `baggage`.

### 4.2. Trace Flags Are Not Security Policy

Trace flags can influence trace sampling. Never use caller-supplied flags to make access control or trust decisions. Configure samplers per your system's observability policy.

### 4.3. Do Not Manually Craft Trace Context When Instrumentation Exists

Generating random `traceparent` strings manually in every service breaks distributed traces. Use the tracer/instrumentation to start new traces when no context exists, continue traces when valid context arrives, start child spans on outbound calls, and inject/extract per standard.

When an edge gateway receives external trace context, consider trust boundaries and sampling policies; trace context still never counts as authentication data.

## 5. Structured Logging: Log Events, Not Object Dumps

Structured logs enable querying by stable fields instead of parsing free-form prose. An authentication event might look like:

```json
{
  "timestamp": "2026-11-15T10:00:00.000Z",
  "level": "INFO",
  "event": "resource_server.authentication",
  "service": "orders-api",
  "requestId": "req-7f2a",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "7a085853722dc6d2",
  "authOutcome": "success",
  "authMethod": "bearer",
  "issuerId": "internal-oidc",
  "resource": "orders-api"
}
```

This event is enough to locate the request and see that authentication succeeded on which API. It needs no raw JWT, full claims, Authorization header, or `Authentication` object dump.

### 5.1. Fields to Consider

| Field | Purpose | Notes |
| --- | --- | --- |
| event | Stable event name | E.g. `resource_server.authentication_failed`. |
| service | Service name | Never use arbitrary request hostnames/URLs. |
| requestId | Request correlation | Validated or system-generated. |
| traceId, spanId | Distributed trace correlation | Obtained from tracer/MDC. |
| http.method | HTTP method | Standard enum values. |
| http.route | Route template | E.g. `/api/orders/{id}`, avoiding raw URLs with queries. |
| http.status_code | Status code | Useful for dashboards. |
| auth.outcome | success/failure | Never log tokens. |
| auth.failure_reason | Standardized error code | E.g. `invalid_signature`, `invalid_issuer`, `invalid_audience`, `expired`. |
| auth.scheme | Mechanism | E.g. `bearer`. |
| resource | API identifier | Use stable configured names. |
| scope.required | Permission needed for operation | Log only if policy permits. |
| duration_ms | Processing duration | Without credentials. |

Not every application needs all of these fields. Add a field only if it serves a concrete operational or audit question.

### 5.2. Fields That Should Never Be Logged

Never log directly:

- Authorization headers or raw Bearer tokens.
- ID tokens, access tokens, refresh tokens, DPoP proofs, or client assertions.
- `client_secret`, passwords, private keys, signing keys, or API keys.
- Authorization codes, PKCE `code_verifier`, session cookies, or CSRF tokens.
- Full OAuth Token Endpoint request/response bodies.
- Full JWT claims or `Authentication.toString()`.
- Emails, phone numbers, addresses, birthdates, full names, or personal identifiers without a legitimate need.
- Long groups/roles claims or tenant memberships unless needed for investigation.
- Full URLs with query strings containing codes, tokens, states, sessions, or personal data.

Never rely on JWT Base64URL encoding as protection. A JWS payload is merely encoded; anyone holding the token can read its claims.

## 6. Logging Authentication Events Safely in Spring Security

When logging authentication outcomes, extract only the required fields from `Authentication`—never log the entire object.

Example helper for JWT:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

final class SecurityEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(SecurityEventLogger.class);

    static void authenticationSucceeded(
            JwtAuthenticationToken authentication,
            String resource) {

        String issuer = authentication.getToken().getIssuer() == null
                ? "unknown"
                : safeIssuerId(authentication.getToken().getIssuer().toString());

        log.atInfo()
                .addKeyValue("event", "resource_server.authentication")
                .addKeyValue("outcome", "success")
                .addKeyValue("scheme", "bearer")
                .addKeyValue("issuerId", issuer)
                .addKeyValue("resource", resource)
                .log("Resource Server authentication succeeded");
    }

    static void authenticationRejected(String reason, String resource) {
        log.atWarn()
                .addKeyValue("event", "resource_server.authentication")
                .addKeyValue("outcome", "failure")
                .addKeyValue("failureReason", reason)
                .addKeyValue("resource", resource)
                .log("Resource Server authentication rejected");
    }

    private static String safeIssuerId(String issuer) {
        // Map issuer URI to a configured name; do not log arbitrary URLs.
        if ("https://login.example.test".equals(issuer)) {
            return "internal-oidc";
        }
        return "unrecognized";
    }

    private SecurityEventLogger() {
    }
}
```

SLF4J fluent key-value logging requires SLF4J 2.x. If your project uses another logger API, keep the same principles: structured event names and fields, field allowlists, and never stringifying the whole authentication.

### 6.1. Never Log `Authentication` or `Jwt` Verbatim

Avoid:

```java
// UNSAFE: the object may contain tokens and claims.
log.info("Authentication: {}", authentication);

// UNSAFE: may dump all claims.
log.debug("JWT claims: {}", jwt.getClaims());

// NEVER DO THIS: raw token.
log.debug("Bearer token: {}", jwt.getTokenValue());
```

`Authentication` and `Jwt` objects can carry credentials, claims, or identifying data. `toString()` can change across versions; never rely on it as a sensitive-data filter.

### 6.2. Standardizing Failure Reasons

Do not put raw exception messages or error descriptions into default logs. Map errors to a defined set of codes:

| Authentication Error | Suggested Log Code |
| --- | --- |
| Invalid signature | `invalid_signature` |
| Untrusted issuer | `invalid_issuer` |
| Audience mismatch | `invalid_audience` |
| Expired token | `expired_token` |
| Token not yet valid | `not_yet_valid` |
| Malformed token | `malformed_token` |
| Introspection reports inactive | `inactive_token` |
| JWKS/issuer dependency failure | `identity_provider_unavailable` |
| Missing credential | `missing_bearer_token` |

Not every `JwtException` reliably identifies a specific cause; assign a granular code only when the exception type genuinely confirms it. When unclear, use `token_validation_failed`.

### 6.3. Authentication Failure Handler

If you need to log where an authentication exception turns into an HTTP response, wrap `AuthenticationEntryPoint` or use an event listener. Log only standardized error codes and request context.

Skeleton entry point example:

```java
http.exceptionHandling(exceptions ->
        exceptions.authenticationEntryPoint((request, response, exception) -> {
            String requestId = MDC.get("requestId");

            log.atWarn()
                    .addKeyValue("event", "resource_server.authentication_failed")
                    .addKeyValue("requestId", requestId)
                    .addKeyValue("reason", "invalid_or_missing_token")
                    .log("Bearer authentication failed");

            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setHeader(
                    HttpHeaders.WWW_AUTHENTICATE,
                    "Bearer error=\"invalid_token\"");
        }));
```

This is a simplified example; a production handler must distinguish missing credentials from invalid tokens if required by the API contract, while avoiding logging exception messages containing tokens. Never log request headers or full exception objects.

## 7. Pseudonymizing Subjects When Correlation Is Needed

Sometimes incident investigations need to know whether the same subject encountered errors across multiple requests. Raw `sub` can be a stable, sensitive identifier. You can use HMAC to derive a pseudonym:

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

final class SubjectPseudonymizer {

    private final byte[] hmacKey;

    SubjectPseudonymizer(byte[] hmacKey) {
        this.hmacKey = hmacKey.clone();
    }

    String pseudonym(String issuer, String subject) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));

            String input = issuer + "|" + subject;
            byte[] digest = mac.doFinal(
                    input.getBytes(StandardCharsets.UTF_8));

            return Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(digest);
        } catch (Exception exception) {
            throw new IllegalStateException(
                    "Cannot create subject pseudonym", exception);
        }
    }
}
```

The HMAC key must come from a secret manager/KMS and have a rotation policy. Never hardcode or log the key. Combine issuer and subject so two issuers sharing the same `sub` string do not collide into the same identity.

A pseudonym is still linkable across events. Store it only with a clear purpose, restricted access, and bounded retention.

## 8. Token Fingerprints When Investigating a Specific Token

In some incidents, security teams need to know whether multiple services saw the same token. Never log the raw token. You can derive an HMAC fingerprint from the token value:

```java
String tokenFingerprint(String token, byte[] fingerprintKey) {
    try {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(fingerprintKey, "HmacSHA256"));
        byte[] digest = mac.doFinal(
                token.getBytes(StandardCharsets.US_ASCII));

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest)
                .substring(0, 16);
    } catch (Exception exception) {
        throw new IllegalStateException(
                "Cannot fingerprint token", exception);
    }
}
```

Fingerprints are optional, not mandatory. Considerations:

- Use a dedicated HMAC key for fingerprinting, never a signing key or encryption key.
- Restrict who can read fingerprints.
- Digests may be truncated to reduce data, though collision risk must be evaluated.
- Rotate keys to limit long-term linkability.
- Never use fingerprints as credentials, authorization lookup keys, or proof of token validity.
- Never fingerprint refresh tokens or client secrets without an approved use case.

If there is no need to correlate specific tokens, omit this field completely.

## 9. Masking Tokens and Secrets Across Every Logging Layer

Masking only in the application logger is insufficient. Credentials can surface in reverse proxies, ingress controllers, API gateways, servlet access logs, HTTP client wire logs, APM agents, exception handlers, or centralized log backends.

### 9.1. Application Logs

- Never log Authorization, Cookie, Set-Cookie, token request bodies, or claims maps.
- Use structured events with allowlists.
- Never concatenate request headers/bodies into messages.
- Never log exception messages if they can embed requests/tokens.
- Log safe failure codes instead of object dumps.

### 9.2. Reverse Proxies, Ingress, and API Gateways

Audit access-log formats and custom variables. Never configure logging of all request headers. Explicitly exclude:

- `Authorization`
- `Cookie` and `Set-Cookie`
- Query parameters like `access_token`, `id_token`, `code`, `state`, `session`
- Internal headers carrying secrets or user data

Log only method, query-stripped route/path, status, duration, and required request/trace IDs.

### 9.3. Servlet Container Access Logs

Tomcat/Jetty access logs can use varied patterns. Check the actual patterns and any custom valves/filters. Never add the `Authorization` header to access logs for debugging.

### 9.4. HTTP Client Logs

Wire logging in Reactor Netty, Apache HttpClient, or other HTTP clients can dump request/response headers and bodies. Disable wiretap/body logging in production or use an allowlist filter that logs only method, route template, status, and duration.

Be especially careful with:

- OAuth Token Endpoint: request bodies hold `client_secret`, `subject_token`, `actor_token`, authorization codes, or refresh tokens.
- Introspection Endpoint: requests carry the token being introspected.
- UserInfo/downstream APIs: response bodies may contain PII.
- DPoP: proof JWTs and access tokens can appear in the same request.

### 9.5. APM, Tracing Collectors, and Crash Reporting

Check whether agents and exporters automatically capture headers, query strings, exception attributes, or request bodies. Configure denylists/allowlists at the collector and observability backend; never assume agents mask the `Authorization` header by default.

## 10. WebClient: Log Only Safe Metadata

Never turn on wiretap in production just to inspect requests. If you need outbound call logging, use a filter that logs selected fields only:

```java
ExchangeFilterFunction safeRequestLog =
        (request, next) -> {
            log.atDebug()
                    .addKeyValue("event", "http.client.request")
                    .addKeyValue("method", request.method().name())
                    .addKeyValue("path", request.url().getPath())
                    .log("Calling downstream service");

            return next.exchange(request)
                    .doOnNext(response ->
                            log.atDebug()
                                    .addKeyValue("event", "http.client.response")
                                    .addKeyValue(
                                            "status",
                                            response.statusCode().value())
                                    .log("Downstream response received"));
        };
```

This filter logs no request headers, URI queries, or bodies. In a real application, prefer route templates or downstream service names over dynamic paths that could contain sensitive identifiers.

To record duration, measure with Micrometer Observation/Timer or track timestamps via appropriate APIs; avoid buffering request/response bodies to measure time.

## 11. Never Log Raw URLs or Query Strings

Some OAuth flows use query parameters or callback URLs carrying sensitive values. Examples:

```text
/login/oauth2/code/oidc?code=...&state=...
/callback?access_token=...
/reset-password?token=...
```

Access logs should record route templates:

```text
GET /login/oauth2/code/{registrationId}
GET /callback
POST /reset-password
```

Never log raw query strings. If investigating a parameter, log only the parameter name or presence flag—never the credential value.

## 12. Sensitive Claims and the Allowlist Principle

JWT claims typically span multiple data categories:

| Claim/Data | Risk | Recommendation |
| --- | --- | --- |
| `sub` | Stable identifier, can link users | Omit or pseudonymize if genuinely needed. |
| `email`, `phone_number`, `name` | Direct PII | Do not log by default. |
| `address`, `birthdate`, `locale` | Personal data | Do not log by default. |
| `groups`, `roles`, `entitlements` | Reveals org structure/permissions | Log only needed policy codes; never dump full lists. |
| `tenant`, `organization` | Can be sensitive or expose customer relationships | Use approved tenant codes or pseudonyms. |
| `scope` | Reveals app permissions | Log only scopes relevant to security events; never dump all claims. |
| `iss`, `aud` | Trust/resource metadata | Map to configured identifiers; avoid arbitrary URLs. |
| `exp`, `iat`, `nbf` | Token timing metadata | Log only for investigation; no need to log full token. |
| `cnf`, key thumbprint | Sender-constrained credential metadata | Restrict read access; log only when debugging binding. |
| Custom claims | Issuer/domain-specific | Do not log by default until approved. |

### 12.1. Allowlists Beat Denylists

A denylist tries to enumerate every possible sensitive claim. Whenever the issuer adds a new claim, a denylist can miss it.

An allowlist records only explicitly chosen fields:

```java
Map<String, Object> safeClaims = new LinkedHashMap<>();

safeClaims.put("issuerId", "internal-oidc");
safeClaims.put("resource", "orders-api");
safeClaims.put("subjectRef",
        subjectPseudonymizer.pseudonym(issuer, subject));
```

Do not do this:

```java
// UNSAFE: claims can grow or contain PII/token metadata.
log.debug("claims={}", jwt.getClaims());
```

When the issuer introduces a new claim, an allowlist will not automatically log it. That is the desired property.

### 12.2. Never Put Claims in Trace Baggage

Baggage travels across many services and can surface in telemetry. Never insert:

- `sub`, email, phone, or name.
- Access/refresh/ID tokens.
- Client secrets or private key material.
- Full roles/groups or entitlement lists.
- Session IDs or sensitive tenant data.

If business context must propagate, propagate only approved non-sensitive codes with small size and appropriate lifetime.

## 13. MDC in Async Execution

MDC is normally thread-bound. With `@Async`, executors, or thread pools, tasks can run on different threads and lack the original request's MDC.

You can use a `TaskDecorator` to capture and restore context:

```java
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

import java.util.Map;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
```

Attach the decorator to application-managed executors. Context must be restored in `finally` because worker threads are reused.

### 13.1. MDC Propagation Does Not Mean SecurityContext Propagation

MDC carries log context only. It does not propagate authentication or access rights.

If an async task must run with a security identity, use appropriate Spring Security mechanisms such as `DelegatingSecurityContextExecutor` or `DelegatingSecurityContextAsyncTaskExecutor`, and only when propagating security context fits the business model.

Never use MDC to restore a principal or token.

## 14. Reactor/WebFlux and Context Propagation

In WebFlux, a request can hop threads across operators. Because MDC relies on `ThreadLocal`, it is not a reliable context carrier for reactive pipelines.

Principles:

- Use Reactor Context and Micrometer Context Propagation/Observation to carry trace context.
- Use compatible tracing instrumentation to create spans and inject/extract W3C context.
- Never call `MDC.put()` and assume the value survives across `publishOn`/`subscribeOn`.
- Never stuff tokens or sensitive claims into Reactor Context for logging.
- When logging inside a reactive chain, retrieve trace context through version-appropriate instrumentation or context accessors.

Example logging an event in a reactive flow without reading raw tokens:

```java
return inventoryClient.getInventory(sku)
        .doOnSuccess(result ->
                log.atDebug()
                        .addKeyValue("event", "inventory.lookup")
                        .addKeyValue("outcome", "success")
                        .log("Inventory lookup completed"));
```

Trace/span correlation should be handled by Micrometer/Observation instrumentation. If integrating MDC with Reactor yourself, use version-appropriate Context Propagation and test across thread switches.

## 15. Correlation IDs Across Service Boundaries

When requests cross multiple services, standardize how context is propagated:

| Header | Purpose | Is It a Credential? |
| --- | --- | --- |
| `traceparent` | W3C trace context | No. |
| `tracestate` | Vendor-specific trace state | No; must contain no secrets. |
| `baggage` | Additional context propagation | No; must contain no tokens/PII. |
| `X-Request-ID` | Request correlation per internal contract | No. |
| `Authorization` | Bearer/client authentication | **Yes, must be protected.** |

Example safe outbound request:

```http
GET /api/inventory/SKU-100 HTTP/1.1
Host: inventory.internal
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-7a085853722dc6d2-01
X-Request-ID: req-7f2a
Authorization: Bearer <access-token>
```

Trace context and request ID are sent for correlation. The `Authorization` header is sent because the protocol requires it, but must be kept out of logs.

### 15.1. Correlation IDs Must Never Be Used as Authorization Input

An attacker can send a request ID colliding with another request's ID. Therefore:

- Never query user data solely from a request ID.
- Never grant access because a request carries a trace ID from a known trace.
- Never let a request ID override subject/tenant.
- Never use trace context as CSRF protection or replay protection.

Correlation helps find logs; authorization must rest on verified credentials and policy.

## 16. Logging Authentication and Authorization Are Two Separate Events

You can emit two distinct event types:

**Authentication event** answers whether the credential was accepted:

```json
{
  "event": "resource_server.authentication",
  "outcome": "success",
  "scheme": "bearer",
  "issuerId": "internal-oidc",
  "resource": "orders-api"
}
```

**Authorization event** answers whether the principal was permitted to perform the operation:

```json
{
  "event": "resource_server.authorization",
  "outcome": "denied",
  "reason": "insufficient_scope",
  "httpMethod": "POST",
  "route": "/api/orders",
  "requiredAuthority": "SCOPE_orders:write",
  "resource": "orders-api"
}
```

There is no need to log raw subjects. When audits require identifying the actor, use a pseudonymous subject reference or policy-protected identity reference.

### 16.1. Do Not Log Every Request as a Security Incident

A single valid request can emit plenty of technical logs. Choose meaningful events:

- Authentication success: metrics/traces or risk-based audits may suffice.
- Authentication failure: log standardized events with rate limiting/aggregation.
- Authorization denied: log resource, route, and standardized policy reason.
- Privileged action: audit separately per business requirements.

Avoid logging the exact same failure repeatedly across every filter, entry point, controller, and exception handler.

## 17. Audit Logs Differ from Application Logs and Traces

| Data Type | Purpose | Characteristics |
| --- | --- | --- |
| Application log | Debugging and operations | High volume; DEBUG/INFO/WARN/ERROR levels. |
| Distributed trace | Latency and dependency analysis | Parent/child spans, sampling, separate retention. |
| Security audit log | Recording critical security actions and decisions | Stable schema, stricter access control, retention, and integrity. |

Never use traces as the sole audit record: traces can be sampled or expire quickly. Never use application debug logs as the sole audit trail: logs can rotate, lack integrity, or contain noisy data.

An audit event should capture who acted via a protected identity reference, what action occurred, which resource/object via a classified identifier, allow/deny outcome, timestamp and request/trace correlation, and policy or reason code.

Never log tokens to prove who called. Record verified identity references and system decisions.

## 18. Log Injection and Caller-Controlled Data

Headers, queries, user-agents, URL paths, and error text can be caller-controlled. Logging them verbatim lets attackers inject newlines or forged log entries.

Mitigations:

- Use structured logging instead of free-form string concatenation.
- Validate request ID length and characters.
- Use route templates instead of raw paths when paths contain identifiers.
- Never log raw query strings.
- Never log upstream-returned exception descriptions verbatim.
- Bound the length of external fields.
- Use a JSON encoder with proper escaping.

Do not try to sanitize by stripping a couple of characters and assuming safety. The safest rule is logging only values conforming to defined formats.

## 19. Sampling, Retention, and Access Control

Trace sampling helps control cost, yet must not drop mandatory security audit events.

Recommendations:

- Choose trace sampling policies fitting traffic and incident response needs.
- Emit critical audit events via a dedicated policy independent of trace sampling.
- Record metric counters for all authentication failures alongside sampled traces.
- Rate-limit or aggregate failure logs that attackers could trigger in bulk.
- Synchronize clocks across services for timestamp correlation.
- Restrict log/trace access by least privilege.
- Encrypt data in transit and at rest.
- Set retention per purpose and regulation, deleting automatically upon expiry.
- Audit access and exports of logs containing sensitive data.
- Never ship production logs to development environments or unapproved external services.

## 20. Testing That Secrets Never Appear in Logs

A solid test checks more than status codes. It also verifies canary secrets never appear in logs.

Conceptual example with Logback `ListAppender`:

```java
String canaryToken = "test-secret-token-do-not-log";
String canaryEmail = "private-user@example.test";

// Send a test request or invoke the logging component with canary values.

String capturedLogs = listAppender.list.stream()
        .map(ILoggingEvent::getFormattedMessage)
        .collect(Collectors.joining("\n"));

assertThat(capturedLogs).doesNotContain(canaryToken);
assertThat(capturedLogs).doesNotContain(canaryEmail);
```

This is a skeleton: attach `ListAppender` to the target logger, execute requests through the test filter chain, and inspect both formatted messages and structured key-value fields if the encoder stores them separately.

### 20.1. Inspect Structured Fields and MDC Too

Secrets might be absent from the formatted message while still hiding in key-value fields, MDC, or JSON encoder output. Tests should inspect the final serialized event or full event object:

- Message.
- Argument array.
- Structured key-value pairs.
- MDC properties.
- Exception messages and stack traces.
- Captured HTTP request/response logs when testing clients.

### 20.2. Use Distinct Canary Values per Secret Type

Generate recognizable values for Bearer tokens, refresh tokens, client secrets, cookies/sessions, email/phone claims, and `code`/`state` query parameters.

After executing requests, assert none of those values appear in application logs, access logs, or captured outbound HTTP loggers.

### 20.3. Test Request ID and Trace Propagation

Verify:

1. Valid request IDs land in MDC and the response header.
2. Request IDs with newlines or excessive length are replaced with fresh IDs.
3. MDC is cleaned up after requests even when controllers throw exceptions.
4. Two consecutive requests on the same thread do not share a request ID.
5. Outbound calls carry trace context per instrumentation.
6. No `Authorization` headers or sensitive baggage appear in outbound logs.

## 21. Operational Matrix

| Scenario | Logs/Traces Needed | Data to Avoid |
| --- | --- | --- |
| Valid JWT | requestId, traceId, resource, outcome=success | Raw token, full claims. |
| Bad signature | outcome=failure, reason=invalid_signature, traceId | Token, JWT payload. |
| Wrong audience | reason=invalid_audience, API identifier | Verbatim ID token/access token. |
| Missing scope | authorization denied, route, required authority | Full roles/groups if unneeded. |
| JWKS endpoint timeout | dependency name, duration, error category | HTTP headers/bodies with credentials. |
| Token exchange failure | AS dependency, grant category, standardized error code | `subject_token`, `actor_token`, `client_secret`. |
| Downstream 5xx | service name, route template, status, duration, trace ID | `Authorization` header, sensitive response body. |
| UserInfo returns PII | outcome and latency | UserInfo response body, email, phone. |
| Request query contains `code` | route template, status | Raw query string and authorization code. |

## 22. Safe vs. Unsafe Log Examples

### 22.1. Safe Log

```json
{
  "level": "WARN",
  "event": "resource_server.authentication_failed",
  "service": "orders-api",
  "requestId": "req-7f2a",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "7a085853722dc6d2",
  "resource": "orders-api",
  "reason": "invalid_audience",
  "httpMethod": "GET",
  "route": "/api/orders"
}
```

This log suffices to find the trace and see the token failed audience validation. There is no need to log `aud` verbatim when the API identifier is already known.

### 22.2. Unsafe Log

```text
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
JWT claims: {sub=user@example.test, email=user@example.test, ...}
OAuth token request body: subject_token=...&client_secret=...
Cookie: SESSION=...
```

These values allow credential replay or expose personal data. Never log them at any log level, including DEBUG or TRACE.

## 23. Common Pitfalls

1. **Logging full `Authentication` objects:** objects can hold JWTs and claims; extract allowlisted fields only.
2. **Logging raw JWTs for debugging:** payloads are readable and tokens can be replayed.
3. **Masking tokens only in the application logger:** proxies, access logs, HTTP clients, and APMs may still capture them.
4. **Using request IDs as identity:** correlation IDs are not authentication.
5. **Putting tokens into baggage:** baggage propagates across services and telemetry.
6. **Forgetting to clear MDC:** thread pools can leak old request IDs into later requests.
7. **Assuming MDC auto-propagates across async/reactive:** thread switches can drop or mix contexts.
8. **Logging raw URLs:** query strings can hold codes, tokens, states, or PII.
9. **Using claim denylists:** new claims added by the issuer slip through; prefer allowlists.
10. **Logging arbitrary exception messages:** upstreams can embed sensitive data in messages.
11. **Substituting traces for audit logs:** trace sampling and retention are unfit as sole audit records.
12. **Logging every authentication failure unboundedly:** attackers can cause log flooding.
13. **Using plain hashes for subjects/tokens:** unkeyed hashes can be probed or linked; where pseudonymization is needed, consider HMAC with rotation.
14. **Assuming DEBUG needs no protection:** debug logs are still collected and retained in centralized logging systems.

## 24. Implementation Checklist

- [ ] Request IDs are validated or internally generated.
- [ ] MDC is set and cleaned up in `finally`.
- [ ] Filters are registered exactly once.
- [ ] Trace IDs/span IDs come from Micrometer Tracing or compatible instrumentation.
- [ ] W3C trace context propagates across outbound clients per configuration.
- [ ] Trace/request IDs are never used as identity or authorization inputs.
- [ ] Structured logs use event names and field allowlists.
- [ ] `Authorization`, cookies, tokens, secrets, and OAuth request bodies are never logged.
- [ ] `Authentication`, `Jwt`, claims, and arbitrary exceptions are never dumped.
- [ ] Raw query strings and URLs containing credentials are never logged.
- [ ] Sensitive claims are omitted or pseudonymized per policy.
- [ ] Tokens/PII are never placed in trace baggage.
- [ ] Async executors propagate MDC with cleanup; `SecurityContext` is handled separately.
- [ ] WebFlux uses Reactor/Micrometer context propagation rather than `ThreadLocal` assumptions.
- [ ] Reverse proxies, ingress, access logs, HTTP clients, and APMs are all audited.
- [ ] Security audit events have dedicated retention and access policies.
- [ ] Log injection and log flooding are controlled.
- [ ] Canary tests verify tokens, secrets, and PII never appear in logs.

## 25. Self-Check Questions

**1. What is a request ID used for?** Finding logs related to a single request per the system's contract.

**2. How do trace ID and span ID differ?** Trace ID groups a distributed trace; span ID identifies a specific operation.

**3. Is `traceparent` a credential?** No. It is W3C trace context.

**4. Can a trace ID be used to make authorization decisions?** No.

**5. Why must MDC be cleaned up in `finally`?** Servlet and executor threads are reused; stale MDC values can leak into another request.

**6. Should `Authentication.toString()` be logged?** No; it can contain credentials or claims.

**7. Should all JWT claims be logged?** No. Use an allowlist of approved fields.

**8. Why is an allowlist better than a denylist?** Newly added claims are not automatically logged.

**9. Can raw access tokens be logged at DEBUG level?** No.

**10. What is an HMAC subject pseudonym used for?** Correlating the same subject without logging the raw subject, using a protected key.

**11. Is a token fingerprint a credential?** No; it is only a correlation identifier and still requires protection.

**12. Can an access token be placed in baggage?** No; baggage is propagated and can surface in telemetry.

**13. Does MDC propagate automatically across WebFlux thread switches?** Never assume so; use Reactor/Micrometer context propagation.

**14. Why must reverse proxy logs be checked?** Tokens can be logged before requests even reach the application.

**15. Why avoid logging raw query strings?** OAuth codes/states and various credentials can appear in queries.

**16. Do traces replace audit logs?** No; traces use sampling and different retention than audits.

**17. Should every authentication failure be logged unboundedly?** No; apply rate limiting or aggregation to prevent log flooding.

**18. Which test catches logged tokens?** Send canary tokens/secrets and assert serialized log events never contain those values.

## 26. References

- **Spring Boot Reference — Logging:** logging configuration and MDC/correlation in Boot apps. https://docs.spring.io/spring-boot/reference/features/logging.html
- **Spring Boot Reference — Actuator Observability:** Observation, tracing, and context propagation. https://docs.spring.io/spring-boot/reference/actuator/observability.html
- **Spring Security Reference — OAuth 2.0 Resource Server:** JWT/opaque authentication in Resource Server. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Micrometer Tracing Reference:** tracers, spans, context propagation, and bridges. https://docs.micrometer.io/tracing/reference/
- **W3C Trace Context:** `traceparent` and `tracestate` specification. https://www.w3.org/TR/trace-context/
- **W3C Baggage:** baggage context propagation and privacy considerations. https://www.w3.org/TR/baggage/
- **OpenTelemetry Specification — Context Propagation:** cross-process propagation and instrumentation. https://opentelemetry.io/docs/specs/otel/context/
- **OWASP Logging Cheat Sheet:** data to exclude from logs, log injection, and log protection. https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- **OWASP Secrets Management Cheat Sheet:** secret management and credential lifecycles. https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

## 27. Conclusion

Good logging and tracing trace requests across services, pinpoint authentication/authorization failures, and measure latency. They are safe only when every event records strictly what is needed. Use request IDs to find logs, trace/span IDs to connect distributed traces, and structured events to record outcomes and reason codes; keep tokens, secrets, raw claims, and PII out of messages, MDC, baggage, access logs, and APM.

In a Spring Security Resource Server, never dump `Authentication`, `Jwt`, or request headers. Log allowlisted fields such as resource, outcome, failure reason, route template, and correlation IDs. When subject correlation is needed, use keyed pseudonymization per policy; use token fingerprints only for clear investigative needs.

Finally, verify the entire data path: application, servlet container, proxy, gateway, HTTP client, tracing agent, and log backend. A canary test proving tokens and secrets never reach serialized logs is worth far more than header masking in a single logger. Correlation must aid incident response without creating a new credential-leak channel.
