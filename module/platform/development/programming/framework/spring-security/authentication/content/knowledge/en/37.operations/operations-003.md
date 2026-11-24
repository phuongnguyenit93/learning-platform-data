# Login Logging, Correlation IDs, and Personal Data Protection in Spring Security

When operating a Spring Security application, engineering teams need to answer questions such as: **who attempted to log in, which method was used, where did the request fail, and why does a user report they cannot access the system?** Logs, audit events, correlation IDs, and distributed tracing help investigate these issues. However, if recorded carelessly, the logging system itself becomes a source of leaks for **passwords, access tokens, session cookies, email addresses, IP addresses, or account data**.

Core principle: **record enough security events for traceability, but never log credentials or personal data beyond necessity**. A good login log entry states what happened, when, in which service, and for which request; it **does not need** to print the entire HTTP request, the `Authentication` object, passwords, or raw exception messages.

This lesson belongs to the **Operations** section of the Spring Security – authentication module, focusing on schema design, success/failure logging, request/trace/span IDs, MDC, header trust boundaries, PII controls, log injection prevention, centralized log operations, and Java 17+ tests.

## 1. Distinguishing Application Logs, Security Events, Audit Trails, and Distributed Traces

These four data sources often appear together, yet do not replace one another:

| Type | Primary Purpose | Example | Reliability and Retention |
| --- | --- | --- | --- |
| **Application log** | Technical diagnostics | "Password encoder timeout", "Request completed" | Varies by log level; not a durable audit record by default |
| **Security event** | Describing security behavior | Authentication succeeded/failed, account locked | Requires standardized categories and monitoring |
| **Audit trail** | Tracing critical actions | Who changed MFA, changed password, revoked session, added passkey | Requires integrity, access control, and clear retention |
| **Distributed trace** | Tracking work across services | Gateway → identity-service → user-store | Uses trace/span IDs; may be sampled |

Example of a login failure:

~~~text
Browser
   |
   v
API Gateway -------------------- traceId T / requestId R
   |
   v
Auth Service ------------------- auth_event=FAILURE reason=PROVIDER_ERROR
   |
   +----> Directory/IdP ---------- spanId S / timeout
   |
   +----> Audit/Observability ---- eventId E / severity=ERROR
~~~

`requestId` links entries within **a single request**; `traceId` links spans across multiple services; `spanId` identifies an individual step; `eventId` identifies **a specific event record**.

**Do not use session IDs, access tokens, or usernames as correlation IDs.** They serve different purposes, may grant access, or contain personal data. A randomly generated correlation ID is not proof of authentication and must never be used in place of a credential.

### One HTTP Request Is Not Always One Login

A single request may pass through multiple authentication components; one login may involve a password, MFA, or an OIDC redirect; a token refresh may create a new authentication without being an interactive login. Therefore, when building dashboards, distinguish:

- `AUTH_ATTEMPT` — one backend credential verification attempt;
- `AUTH_SUCCESS` / `AUTH_FAILURE` — authentication outcome reported by the framework;
- `LOGIN_COMPLETED` — the application completes the login flow and establishes the appropriate session/token;
- `MFA_CHALLENGE` / `MFA_COMPLETED` — additional factor verification steps;
- `LOGOUT_COMPLETED` / `SESSION_REVOKED` — session state changes;
- `AUTHORIZATION_DENIED` — principal is identified, but access to the resource is denied.

These terms should be defined in the organization's **event taxonomy**; do not assume a one-to-one mapping among `AuthenticationSuccessEvent`, HTTP 200, and an interactive user login.

## 2. Why Logging Full Request Bodies and Headers Is Dangerous

A login request can contain:

~~~http
POST /login HTTP/1.1
Host: accounts.example.org
Cookie: SESSION=<session-secret>
Authorization: Bearer <access-token>
Content-Type: application/x-www-form-urlencoded

username=lan@example.org&password=<password-secret>
~~~

If an access logger writes raw URLs, bodies, headers, or exception objects, it can expose:

- Passwords, OTPs, backup/recovery codes;
- Session cookies, access tokens, refresh tokens, API keys;
- Password-reset tokens in query strings, OAuth authorization codes;
- Raw email addresses, usernames, phone numbers, IPs/user agents (potentially personal data);
- Internal hostnames, secret configuration, stack traces containing credentials;
- `client_assertion` or private-key material in certain integrations.

**Passwords, Bearer tokens, and session identifiers must be treated as sensitive credentials that grant access.** Redact them before logs are created and sent to any sink; do not rely solely on deleting them after they reach a SIEM.

Commonly overlooked places:

| Layer | Risk |
| --- | --- |
| Servlet access log / reverse proxy | Query strings, full URLs, Cookie and Authorization headers |
| Request/response logging filter | Dumping bodies/headers containing credentials |
| Spring Security DEBUG/TRACE | Flow details, exceptions, or sensitive objects depending on configuration |
| HTTP client logging to IdP | Authorization headers, token requests/responses |
| Exception handler | `exception.getMessage()` containing username/query/endpoint |
| Distributed tracing | Span attributes/baggage containing email or access token |
| MDC | Setting userId/email and failing to clean up between thread-pool tasks |
| Error reporting/APM | Captured HTTP requests, headers, form fields |
| Log aggregation/export | Copying to multiple sinks with different permissions/retention |

Do not enable global body logging on `/login`, `/oauth2/token`, `/reset-password`, or `/webauthn/**`. If debugging is truly needed, use allowlisted event/metadata logs and control duration, access permissions, and cleanup.

## 3. Designing a Minimal Login Event Schema

Suggested JSON Lines schema — **not a structure emitted automatically by Spring Security**:

~~~json
{
  "eventId": "c8a62a8e-7b07-44f3-a218-6d73c7adfba2",
  "timestamp": "2026-11-06T03:00:00Z",
  "service": "identity-api",
  "environment": "production",
  "eventType": "AUTH_FAILURE",
  "authenticationMethod": "PASSWORD",
  "outcome": "FAILURE",
  "reasonCode": "BAD_CREDENTIALS",
  "requestId": "a640d00b-cf0c-4ee1-b5ce-36d547bc2bd0",
  "traceId": "ade6d79a3ebef5836a21ee27e4d60e70",
  "spanId": "8104c6c919a7b59f",
  "principalRef": null,
  "tenantRef": null
}
~~~

This is synthetic sample data for illustration, not real IDs or events.

| Field | Guidance |
| --- | --- |
| `timestamp` | Server UTC timestamp in ISO-8601; ensure clock synchronization |
| `eventId` | Unique record ID for deduplication and investigation |
| `eventType` | Small approved category set: AUTH_SUCCESS/FAILURE, MFA, LOCKOUT… |
| `authenticationMethod` | PASSWORD, PASSKEY, OIDC, SAML, API_KEY… from server-side state |
| `outcome` | SUCCESS, FAILURE, DENIED, ERROR… never inferred from HTTP status alone |
| `reasonCode` | Stable enum/allowlist without exception messages |
| `requestId` | Random HTTP request ID containing no credentials |
| `traceId` / `spanId` | Standard tracing IDs when instrumentation is active |
| `principalRef` | Controlled opaque ID only when truly needed; null for unauthenticated attempts |
| `tenantRef` | Opaque tenant ID from a trusted source if policy permits |
| `sourceClass` | E.g., WEB, MOBILE, API, BATCH; avoid unnecessary fingerprinting |

**Do not log the raw form `username` on login failures by default.** Attackers control the username field; it may contain someone else's PII or a log injection payload. For investigations requiring correlation of repeated attempts for the same identifier, a keyed HMAC pseudonym over the normalized value can be used per policy, provided key management, retention, and view restrictions are enforced; HMAC does not automatically render data strictly anonymous.

If `principalRef` provides no clear benefit, omit it from the event. Minimal data can be just eventType, outcome, reasonCode, service, timestamp, and requestId.

## 4. Defining Taxonomy and Reason Codes Without Leaking Identity

A backend-controlled reason code table:

| Reason Code | Internal Meaning | Not Equivalent To |
| --- | --- | --- |
| `BAD_CREDENTIALS` | Invalid credential | Proof that a username definitely exists |
| `ACCOUNT_LOCKED` | Policy marks account locked | Public disclosure of user existence |
| `ACCOUNT_DISABLED` | Account is not allowed to log in | Detailed reason to return to anonymous callers |
| `CREDENTIAL_EXPIRED` | Credential has expired | Normal session expiration |
| `PROVIDER_ERROR` | IdP/LDAP/DB outage or error | User entered the wrong password |
| `TOKEN_INVALID` | Invalid Bearer token or credential | Every HTTP 401 request is a password login |
| `MFA_REQUIRED` | Additional MFA step required by flow | Final authentication failure |
| `AUTH_OTHER` | Unclassified/unmapped | Excuse to print stack traces to public logs |

**Failure categories can be more detailed than the message sent to the client.** For example, the UI should return a generic login error to avoid account enumeration, while internal audits distinguish provider outages from credential failures. Still, only authorized personnel should view those internal details.

Never let clients submit reason codes via `X-Auth-Reason` and feed them into dashboards. Mappings must originate from verified `AuthenticationManager`/provider/exception states.

## 5. How Spring Security Publishes Authentication Events

Spring Security provides `AuthenticationEventPublisher` and `DefaultAuthenticationEventPublisher`, which can publish:

- `AuthenticationSuccessEvent` when an authentication path through the manager/publisher succeeds;
- Subtypes of `AbstractAuthenticationFailureEvent`, such as `AuthenticationFailureBadCredentialsEvent`, `AuthenticationFailureLockedEvent`, `AuthenticationFailureDisabledEvent`, or `AuthenticationFailureServiceExceptionEvent`.

A publisher can be declared as:

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new DefaultAuthenticationEventPublisher(applicationEvents);
}
~~~

This is a **Spring configuration snippet** requiring imports and an `ApplicationContext`. In Spring Boot/Security apps, publisher integration depends on the authentication manager/provider in use. If you instantiate `ProviderManager` manually, verify that it actually receives the publisher; do not assume adding `@EventListener` makes every flow emit events.

Spring Security maps known `AuthenticationException` classes to failure events; **custom exception subtypes do not automatically inherit superclass mappings** because the publisher uses exact exception class matching. When telemetry is needed for custom provider exceptions, configure `setAdditionalExceptionMappings(Map)` and a fallback event as supported by your version.

**Spring events are not automatically durable audit logs:** listeners run inside the `ApplicationContext`, may be synchronous, and do not forward themselves to Kafka/SIEM. If guaranteed storage is required, build a dedicated audit pipeline; do not assume default events propagate across nodes or survive restarts.

## 6. Safe Listener: Log the Event Type, Never Dump Authentication

Example class **AuthenticationAuditListener.java** in Spring Boot Servlet:

~~~java
package demo.authlogging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationFailureLockedEvent;
import org.springframework.security.authentication.event.AuthenticationFailureServiceExceptionEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.stereotype.Component;

@Component
public class AuthenticationAuditListener {

    private static final Logger LOG =
            LoggerFactory.getLogger(AuthenticationAuditListener.class);

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        LOG.info("security_event=AUTH_SUCCESS requestId={}",
                requestIdForLog());
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        String reason = "AUTH_OTHER";

        if (event instanceof AuthenticationFailureBadCredentialsEvent) {
            reason = "BAD_CREDENTIALS";
        } else if (event instanceof AuthenticationFailureLockedEvent) {
            reason = "ACCOUNT_LOCKED";
        } else if (event instanceof AuthenticationFailureServiceExceptionEvent) {
            reason = "PROVIDER_ERROR";
        }

        LOG.info("security_event=AUTH_FAILURE reason={} requestId={}",
                reason, requestIdForLog());
    }

    private static String requestIdForLog() {
        String value = MDC.get("requestId");
        return value == null ? "-" : value;
    }
}
~~~

This is a Spring component and **cannot run standalone with javac**. It requires `spring-security-core`, `spring-context`, SLF4J, and a publisher wired into the authentication flow.

Intentional design choices:

1. Event categories are constants or derived from framework subtype classes, never user-supplied data.
2. `requestId` comes from a trusted filter/tracing layer; if absent, `-` is logged rather than guessing a principal.
3. Never calls `getCredentials()`, never logs raw `event.getAuthentication()`.
4. Never logs `event.getException().getMessage()` or stack traces just to "see the reason"; those can hold uncontrolled data.
5. The listener does not grant authorities, send HTTP statuses, or mutate `SecurityContext`.
6. `AUTH_SUCCESS` is an authentication-layer event; if you need a metric for "user completed interactive login", define a business-level event after the full password/MFA/OIDC flow finishes.

If the listener runs asynchronously, the HTTP thread's MDC **is not automatically present** on executor threads; use tracing context propagation or pass appropriate opaque event metadata. Do not rely blindly on `MDC.get("requestId")` across async boundaries.

## 7. Failure Handlers and Application Logs Have Distinct Responsibilities

In Servlet form login, `AuthenticationFailureHandler` typically decides the HTTP response/redirect. It is not synonymous with `AuthenticationEventPublisher`.

| Mechanism | Primary Responsibility | What Not to Do |
| --- | --- | --- |
| `AuthenticationFailureHandler` | HTTP response for failed login | Return distinct messages revealing account existence |
| `AuthenticationEventPublisher` | Publish success/failure events | Treat as durable audit storage |
| `@EventListener` | Observe/audit/meter events | Dump passwords/exceptions/user objects |
| `AuthenticationEntryPoint` | Start authentication or return 401 | Infer principal from untrusted request headers |
| `AccessDeniedHandler` | Handle denial after authorization | Count all 403s as login failures |
| Access log filter | Request status, latency, requestId | Log credential-bearing bodies/headers |

An authenticated user lacking `ROLE_ADMIN` may receive HTTP 403. That is **authorization denied**, and should not be tagged `BAD_CREDENTIALS`. Maintaining this distinction prevents dashboards from mistaking permission issues for password-guessing attacks.

## 8. What Is a Correlation ID and Where Does It Come From?

`requestId` is an opaque ID linking log records within the same HTTP request. It should:

- Have sufficient uniqueness, such as `UUID.randomUUID()` generated by a trusted server/gateway;
- Contain no username/email/IP/session ID/token/tenant secret;
- Have bounded format/length, avoiding control characters or log forging;
- Be attached at the request boundary and cleared when the thread context ends;
- Optionally be returned via the `X-Request-ID` response header so users can share it with support, **without enabling access to private data using that ID**;
- Follow a consistent strategy alongside gateway/microservice tracing.

Example:

~~~http
HTTP/1.1 401 Unauthorized
X-Request-ID: 7f1a9228-6ae6-4706-a8e7-8bb8e6ad2520
Content-Type: application/json

{"message":"Unable to authenticate request."}
~~~

A Request ID does not identify a user, is not a reset token, and should never allow a public API to look up login details merely by presenting the ID.

### Handling External Headers

If a client sends:

~~~http
X-Request-ID: alice@example.org
~~~

or:

~~~http
X-Request-ID: abc
X-Request-ID: attacker-injected
~~~

it must not be trusted by default. The safest option is to **ignore all inbound `X-Request-ID` headers and generate a fresh UUID at the edge/backend**. If the organization uses a trusted gateway to issue IDs, strip/overwrite headers from the Internet, enforce length/character limits, and secure the gateway–backend network path.

A validated ID can be returned for support use, but never embed email addresses or personal data into the ID. Never construct IDs by concatenating `username + "-" + timestamp`.

## 9. MDC Attaches requestId to Logs, but MDC Is ThreadLocal

SLF4J `MDC` (Mapped Diagnostic Context) is a key/value map for loggers: a Logback encoder or pattern can print `%X{requestId}` so every log emitted on the current thread shares the same request ID.

Example Logback pattern:

~~~text
%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] req=%X{requestId:-} %logger - %msg%n
~~~

This is an illustrative layout, not automatically enabled in every configuration.

**MDC typically relies on thread-local state**: Servlet containers reuse threads, so without cleanup in `finally`, Bob's request could accidentally log Alice's request ID. In async and reactive stacks, simply calling `MDC.put(...)` on one thread does not preserve context when execution hops threads.

### Servlet OncePerRequestFilter: Generating IDs and Cleaning Up at the Boundary

File **RequestIdFilter.java** in a Spring Boot 3+/Jakarta Servlet application:

~~~java
package demo.authlogging;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RequestIdFilter extends OncePerRequestFilter {

    private static final String KEY = "requestId";
    private static final String ATTR =
            RequestIdFilter.class.getName() + ".requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Object stored = request.getAttribute(ATTR);
        String id;
        if (stored instanceof String existing) {
            id = existing;
        } else {
            id = UUID.randomUUID().toString();
            request.setAttribute(ATTR, id);
        }

        String previous = MDC.get(KEY);
        MDC.put(KEY, id);
        response.setHeader("X-Request-ID", id);

        try {
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(KEY);
            } else {
                MDC.put(KEY, previous);
            }
        }
    }

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false;
    }
}
~~~

Key points:

- The filter **generates** a UUID itself; it never accepts inbound `X-Request-ID` from the client.
- The request attribute preserves the same ID across dispatches of the same request.
- `finally` restores the previous MDC value or removes the key, even when a filter/controller throws an exception.
- `shouldNotFilterAsyncDispatch() = false` lets the filter apply MDC on an async dispatch **if the Servlet container actually maps the filter for ASYNC**.
- `shouldNotFilterErrorDispatch() = false` works similarly for ERROR dispatches; test against your container and nested ERROR handling.
- Because `OncePerRequestFilter` only guarantees once per request thread/dispatch per framework semantics, do not assume only one total invocation over an HTTP request's lifetime when async/error dispatches occur.

**This is a Servlet filter class**, not a standalone main program. When registered before `springSecurityFilterChain`, authentication events emitted synchronously within the request can read the request ID from MDC. Example registration (in Spring Boot configuration):

~~~java
@Bean
FilterRegistrationBean<RequestIdFilter> requestIdFilterRegistration() {
    FilterRegistrationBean<RequestIdFilter> bean =
            new FilterRegistrationBean<>();

    bean.setFilter(new RequestIdFilter());
    bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
    bean.setDispatcherTypes(
            DispatcherType.REQUEST,
            DispatcherType.ASYNC,
            DispatcherType.ERROR);
    bean.setAsyncSupported(true);
    return bean;
}
~~~

This registration snippet requires imports `org.springframework.context.annotation.Bean`, `org.springframework.boot.web.servlet.FilterRegistrationBean`, `org.springframework.core.Ordered`, and `jakarta.servlet.DispatcherType`. Ordering must be verified alongside other Servlet filters and the actual Spring Security configuration rather than assuming this order fits every application.

**Register the filter only once:** if you use `FilterRegistrationBean`, do not also annotate it with `@Component` for automatic Servlet container registration or call `addFilterBefore/After` again in `SecurityFilterChain` unintentionally. When only one boundary is needed, place the filter in **one** chain with clear ownership.

### An Important Detail About MDC Cleanup

The code uses `previous` to restore the key if an outer valid MDC context wraps the filter, instead of removing it unconditionally. However, if MDC already held a leaked value from an earlier request **before the filter ran**, restoring it can mask the root bug. Therefore, integration tests must verify clean servlet worker/entry boundaries, or adopt a policy that resets all request-owned keys at the gateway filter. Do not treat `try/finally` in one filter as proof that no stale MDC data exists anywhere in the system.

## 10. Correlation IDs with Micrometer Tracing in Spring Boot

When a project uses **Micrometer Tracing** and appropriate instrumentation, Spring Boot can populate `traceId` and `spanId` into MDC and display correlation IDs in logs. Spring Boot documentation describes the default format based on these two values.

Example Logback / Spring Boot configuration to customize display:

~~~properties
# Illustrative format; requires Micrometer Tracing to be installed.
logging.pattern.correlation=[%X{traceId:-},%X{spanId:-}]
~~~

Modern Spring Boot documentation uses `logging.pattern.correlation`; if you also maintain a separate `requestId`, design the pattern to avoid duplicate printing or confusing request ID with trace ID.

| ID | Typical Scope | Notes |
| --- | --- | --- |
| `requestId` | One HTTP request | Can be generated by edge or app |
| `traceId` | One distributed trace, across multiple spans | Propagated via W3C trace context/tracing SDK |
| `spanId` | One step within a trace | Typically changes across operations/services |
| `eventId` | One audit record | Used for deduplication/idempotency/integrity if needed |
| `sessionRef` | One session if policy permits | Never use raw session token as correlation ID |

One request can span multiple spans, and multiple requests can belong to the same trace in certain designs. Therefore **never use `traceId` as the primary key of a single login event**.

**Sampling:** distributed traces may be sampled and omit spans. Mandatory audits of MFA/password changes or suspicious logins must not depend entirely on tracing sampling. Maintain a dedicated, sufficiently reliable audit event pipeline.

**W3C `traceparent`/`tracestate`/`baggage`** must be processed by a securely configured SDK/gateway. Never treat arbitrary baggage keys as verified data, and never place `username`, `Authorization`, or tokens into baggage for correlation convenience.

## 11. Protecting Personal Data in Logs

Email addresses, phone numbers, IP addresses, user-agents, device IDs, account IDs, and tenant IDs can be personal data or linkable to an individual in context. Even an opaque account ID can remain personal data if the backend can trace it back to a person.

Operational principles:

1. **Purpose limitation:** what investigation does this field support? Who needs it?
2. **Data minimization:** can the field be omitted while still enabling investigation?
3. **Access control:** who can view the data, and should security/ops/support permissions be separated?
4. **Retention:** how long is storage necessary, and is automatic expiration/deletion enforced?
5. **Transparency and legal basis:** align with applicable privacy policies and laws; never assume one fixed legal TTL applies everywhere.
6. **Integrity:** protect logs against tampering/forgery using signing, hash chains, or WORM/immutable storage where appropriate.
7. **In-transit/at-rest protection:** TLS to collectors, encryption, and key management at rest.
8. **Exports/backups:** CSV exports, dashboard screenshots, backups, and incident attachments must share the same data classification.

An often-overlooked field is `clientIp`. Behind a proxy, client-sent `X-Forwarded-For` can be spoofed. Obtain the "effective client IP" only via **trusted proxy configuration**; otherwise investigations are misled and log injection or false attribution risks arise.

### Should You Log Username/Email on Failure?

By default, **do not log raw usernames/emails** for unauthenticated attempts. Attackers control the input, so events could overflow with others' PII or log-breaking payloads. To link multiple attempts for the same identifier:

- Normalize the identifier according to account policy (do not invent incorrect email-provider rules).
- Use a **keyed HMAC pseudonym**, such as HMAC-SHA-256 over the normalized identifier with a key in a secret manager; avoid unkeyed SHA-256 on guessable emails if that introduces dictionary-attack risk.
- Truncate/bound output, enforce retention and key rotation; never use the pseudonym as a credential.
- Enable this field only when permitted by threat model and legal policy; default logs without identifiers remain useful.
- Never return this hash/HMAC to browsers or unneeded services.

An HMAC pseudonym remains **linkable data** within the same key scope, not an absolute anonymity guarantee. Rotating the key alters historical correlation, so design key lifetimes intentionally.

## 12. Java 17+: Logging Only Approved Fields

The following console program simulates a safe login event formatter. It **does not run Spring Security or write to a SIEM**; it illustrates PII-free ID generation, an allowlisted reason enum, rejecting newlines in external identifiers, and excluding passwords/emails from events.

Create **SafeLoginAuditDemo.java**:

~~~java
import java.util.Set;
import java.util.UUID;

public class SafeLoginAuditDemo {

    private static final Set<String> REASONS = Set.of(
            "BAD_CREDENTIALS", "ACCOUNT_LOCKED", "PROVIDER_ERROR");

    static String reasonCode(String candidate) {
        return REASONS.contains(candidate) ? candidate : "AUTH_OTHER";
    }

    static String safeExternalId(String candidate) {
        return candidate != null
                && candidate.matches("[A-Za-z0-9-]{1,64}")
                ? candidate
                : "REJECTED";
    }

    static String auditLine(String requestId, String rawReason) {
        // Use only server-generated IDs and allowlisted reason codes.
        return "requestId=" + requestId
                + " event=AUTH_FAILURE reason=" + reasonCode(rawReason);
    }

    public static void main(String[] args) {
        String requestId = UUID.randomUUID().toString();
        String rawPassword = "s3cr3t";
        String rawEmail = "lan@example.org";

        String line = auditLine(requestId, "BAD_CREDENTIALS");

        System.out.println("Generated ID format = " +
                requestId.matches(
                        "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                        + "[0-9a-f]{4}-[0-9a-f]{12}"));
        System.out.println("Known reason = "
                + reasonCode("BAD_CREDENTIALS"));
        System.out.println("Unknown reason = "
                + reasonCode("password=s3cr3t"));
        System.out.println("Injected ID = "
                + safeExternalId("abc\r\nFAKE_SUCCESS"));
        System.out.println("Raw password logged = "
                + line.contains(rawPassword));
        System.out.println("Raw email logged = "
                + line.contains(rawEmail));
    }
}
~~~

Compile and run:

~~~bash
javac SafeLoginAuditDemo.java
java SafeLoginAuditDemo
~~~

Exact stdout:

~~~text
Generated ID format = true
Known reason = BAD_CREDENTIALS
Unknown reason = AUTH_OTHER
Injected ID = REJECTED
Raw password logged = false
Raw email logged = false
~~~

Explanation:

- The random UUID format is verified; the program **does not print the concrete ID** so output stays reproducible.
- Reason codes are allowlisted, never derived from raw exception messages.
- A header containing CR/LF is rejected rather than written straight into logs.
- Raw password/email exist in the demo to prove **they are not concatenated into the event line**.
- In real applications, it is better to **generate `requestId` server-side and ignore external IDs** rather than relying solely on `safeExternalId()`: a valid format does not prove the header came from a trusted source.

This lab alone does not guarantee security across all loggers/proxies; review downstream sinks, structured JSON encoding, MDC cleanup, and integration tests.

## 13. Log Injection and Cardinality Attacks

An attacker can submit a username such as:

~~~text
alice
2026-11-06 INFO auth_event=AUTH_SUCCESS user=admin
~~~

If the application writes:

~~~java
// Wrong: concatenating raw input into the log line.
log.info("Login failed for " + userSuppliedUsername);
~~~

then newline characters can forge a fake "AUTH_SUCCESS" record. With JSON loggers, improperly escaped data can break schemas or mislead dashboards; with logfmt, injecting delimiters can fabricate fields.

Required controls:

- Prefer **structured logging** using a proper JSON encoder/logger rather than string concatenation.
- Use enums/allowlists for `eventType`, `reasonCode`, and `authenticationMethod`.
- Enforce length limits on request ID/URL/path/reason and reject control characters (CR, LF, NULL, tabs when disallowed).
- Do not trust `Host`, `X-Forwarded-For`, `User-Agent`, baggage, or correlation headers as safe just because a framework parsed them.
- Never allow an attacker to create unbounded distinct labels like one Prometheus label per email: **high cardinality** can overwhelm telemetry.
- Apply rate limiting/backpressure on event sinks so login attempt floods do not exhaust disk, queues, or SIEM quotas.

**Structured JSON does not replace minimization.** A perfectly escaping encoder still leaks data if the application puts `Authorization` or a password into a JSON field.

## 14. Login/Audit Processing Diagram with Clear Trust Boundaries

~~~text
External client (untrusted)
      |
      | POST /login
      v
Trusted ingress/gateway
      | strip untrusted forwarding/correlation headers
      | choose public host, maybe requestId/trace context
      v
Servlet request correlation filter
      | attach trusted requestId; MDC
      v
Spring Security AuthenticationManager
      | verify credential/account/policy
      +--> success/failure event publisher
      |         |
      |         v
      |     event listener / audit adapter
      |         | sanitize + allowlist fields
      |         +--> trusted async queue / secure audit store
      v
HTTP success/failure handler
      | generic client messaging, session/token policy
      v
Response with opaque X-Request-ID
      |
      v
Filter finally: clear/restore MDC thread scope
~~~

In multi-service architectures, tracing context is propagated separately and must be configured securely. `requestId` helps support trace a specific request, while determining who may view which logs requires RBAC and log-access auditing.

**Never use raw request headers directly to identify the actor or outcome.** The actor is established only after authentication succeeds from server-side identity. Before authentication, any username is a **claimed identifier**, not a verified principal.

## 15. Which Identity May a Login Event Contain?

| Flow | Trusted Principal at That Moment | Appropriate Logging |
| --- | --- | --- |
| Password login failed | No authenticated user | AUTH_FAILURE, reasonCode, requestId; no raw username |
| Password login succeeded | Verified Authentication | AUTH_SUCCESS, opaque principalRef if needed |
| Invalid passkey assertion | Credential unverified | TOKEN/CREDENTIAL_INVALID; do not assert account |
| OIDC callback succeeded | Subject verified via ID Token/UserInfo per policy | Auth method OIDC, checked issuer/subject ref with minimized PII |
| Valid API key | App/service/account verified via server metadata | principalType, issued opaque keyId, never raw key |
| Refresh token failed | Token rejected | TOKEN_INVALID, never log raw token |
| Logout | Session context if authenticated | LOGOUT_COMPLETED, never raw session id |
| Account lock triggered by policy | Server knows account state | Internal audit event; do not disclose state publicly |

If a `principalRef` field is needed, prefer an internal ID **that is not directly an email/phone**, keeping in mind it may still constitute personal data in context. Restrict reverse lookups and read access.

**Never use `getName()` on a failed `Authentication` object as proof that the person logged in.** It may simply be a client-supplied value or an unverified token.

## 16. Setting Log Levels and Keeping Debug Logs Clean

Spring Security offers many useful DEBUG/TRACE loggers for diagnostics, but they must be controlled:

~~~properties
# Example baseline policy; adjust for the real system.
logging.level.org.springframework.security=INFO
logging.level.demo.authlogging=INFO
~~~

Never enable full request body/header tracing just to "see the token clearly". If temporary debugging is required:

1. Require a ticket or incident ID, an owner, and an automatic expiration time.
2. Enable only on services/endpoints without credentials, or use custom safe logging.
3. Inspect actual generated logs before widening scope.
4. Restrict access to aggregators and exports.
5. Monitor log volume/retention/cost.
6. Delete/purge sensitive copies per policy if a secret leak is detected.
7. After the incident, evaluate whether exposed credentials must be rotated/revoked.

**Do not assume every Spring Security DEBUG line leaks secrets.** Output depends on the specific logger and version. Check your concrete pipeline and avoid configuring header/body dumps wherever credentials appear.

## 17. Securing Centralized Logs and Integrity

Multi-service systems typically ship logs to Fluent Bit/OpenTelemetry Collector/SIEM or an equivalent log platform. Essential controls:

| Risk | Mitigation |
| --- | --- |
| Unauthorized reading of login events | Role-based RBAC, least privilege, periodic access reviews |
| Insider bulk-exporting emails/IPs | Audit log access, restrict exports/downloads, require approvals |
| Attacker altering/deleting logs after host compromise | Remote append-only/WORM storage where appropriate, integrity checks |
| Log collector transmitting plaintext | TLS/mTLS or secured transport channels |
| Unbounded log retention | Retention policies, automated deletion, and backup lifecycle |
| Credential accidentally logged | Redaction at source + detection/quarantine and revocation |
| SIEM overwhelmed by login flood | Rate limiting/event aggregation/backpressure without dropping mandatory audits |
| Ingestion parser hit by log injection | Structured JSON, escaping/validation, schema validation |
| Clock skew across nodes | NTP and UTC timestamps, record service/host metadata |
| Mixing logs and metrics | Shared correlation IDs, separate access controls and retention |

For legally regulated audits, check applicable laws, contracts, and privacy policies; **do not hard-code an arbitrary retention day count** just because an example or public standard used one. Data deletion must cover backups, replicas, and exports per approved policy.

A correlation ID shared with support **grants no authority** for support or anyone else to retrieve full audit records. Log queries must enforce RBAC, processing purpose, and record-level restrictions.

## 18. Investigating Incidents Using requestId, traceId, and eventId

Scenario: a user reports "My login failed at 10:15 and I don't know why."

Investigation workflow:

1. Obtain the **requestId** from the response/screenshot or search the time window; never ask the user to send their password/token.
2. Search gateway and identity-service logs by `requestId`/`traceId`.
3. Identify `AUTH_FAILURE` and the allowlisted **internal `reasonCode`**, such as `PROVIDER_ERROR`.
4. Check directory/IdP spans (if present) to separate outages from credential errors.
5. Correlate metrics (failure rate, provider latency, error budget).
6. If account details are needed, query the identity store with authorized permissions rather than inferring from raw username input in logs.
7. Record the incident, remediation actions, and avoid copying full logs into public tickets.

If `reasonCode=BAD_CREDENTIALS`, do not immediately assume the user intentionally mistyped: the client could have used an expired token, provider mapping might be wrong, or automation may be involved. Cross-check multiple signals and service behavior.

If trace sampling dropped the span, audit events should still provide timestamp/service/eventId/requestId for investigation. Never treat a missing trace as proof that "no request occurred".

## 19. Metrics and Alerts: Avoiding PII in Labels

Useful metrics:

| Metric | Recommended Tags | Tags to Avoid |
| --- | --- | --- |
| `auth_attempt_total` | outcome, method, service, environment | Raw username, email, token |
| `auth_failure_total` | reasonCode allowlist, provider class | Exception message, sessionId |
| `auth_latency_seconds` | method, outcome | Per-request Request ID (excessive cardinality) |
| `idp_error_total` | provider name allowlist | Full URL with query/credentials |
| `mfa_stepup_total` | result, method | Raw user ID or OTP |
| `security_audit_sink_failure_total` | sink, errorCategory | Full event payload |

Never use per-request `requestId`/`traceId` as Prometheus counter/histogram labels; nearly unbounded strings cause high cardinality. Those IDs belong in **log/tracing fields**, not metric dimensions.

Rate- and time-based alerts:

- Rising credential failures on a source or endpoint (with privacy safeguards);
- Rising provider errors alongside IdP latency;
- An authenticated principal triggering unusual devices/locations per policy;
- Audit pipeline delivery stalls or prolonged retries;
- Abnormal login velocity and rising MFA failure rates;
- Sudden absence of request IDs or missing trace correlation after a deployment.

A single "login failure" event is not enough to declare an attack; tune thresholds and correlate multiple signals to avoid false positives.

## 20. Unit Testing: Ensuring Secrets Never Enter Events

For the Java 17 demo in section 12, verify these cases:

| Input | Expected |
| --- | --- |
| Server-generated UUID | Valid format, independent of username |
| Known reason | Preserves enum code |
| Unknown reason | `AUTH_OTHER` |
| Raw reason containing password | Replaced with `AUTH_OTHER` |
| External ID containing CR/LF | `REJECTED` |
| Event line | Contains no raw password/email |
| Very long user-supplied field | Bounded/rejected per policy |
| Non-allowlisted field | Excluded from event |
| Null/empty header | Does not infer principal |
| Unicode/control payload | JSON encoder/validator keeps log valid |

The goal is not merely `assertFalse(log.contains("password"))`, since real passwords take many forms and encodings. Test the **allowlist schema** to ensure `password` or `credentials` fields cannot be serialized, combined with canary secret scanning in integration tests.

## 21. Testing Spring Security Events and MDC

With Spring Boot Test or integration tests that capture logs (such as a Logback test appender or Spring Boot `OutputCaptureExtension`):

1. Construct a valid authentication attempt using test credentials.
2. Send the request through the full Spring Security filter chain.
3. Verify a success event of the expected type (or exact event count per policy).
4. Send a request with wrong credentials and verify the event category is `FAILURE`.
5. Ensure the same `requestId` appears across synchronous log lines of the request.
6. Verify response header `X-Request-ID` is UUID-formatted and contains no username/token.
7. Verify logs contain no canary passwords, bearer tokens, Cookies, reset tokens, or raw request bodies.
8. Send request B after request A on the same Servlet worker (or a test asserting thread reuse) and verify A's `requestId` is not reused for B.
9. Force a controller/filter exception and verify MDC is still cleared in `finally`.
10. If ASYNC/ERROR dispatches are used, verify the ID stays consistent within the same request and MDC does not leak to another request.
11. If tracing is enabled, check `traceId`/`spanId` when instrumentation is active; do not require spans when tracing is off.
12. Verify client failure messages remain generic and do not reflect internal reasons or account states.

Illustrative MockMvc/JUnit snippet (requires test application, imports, and assertion libraries):

~~~java
var first = mockMvc.perform(post("/login")
        .param("username", "lan")
        .param("password", "wrong-password")
        .with(csrf()))
        .andReturn().getResponse();

String firstId = first.getHeader("X-Request-ID");
assertNotNull(firstId);
assertTrue(firstId.matches("[0-9a-fA-F-]{36}"));

var second = mockMvc.perform(post("/login")
        .param("username", "lan")
        .param("password", "another-wrong-password")
        .with(csrf()))
        .andReturn().getResponse();

assertNotEquals(firstId, second.getHeader("X-Request-ID"));
~~~

This **is not a standalone Java class**. It requires `MockMvc` with Spring Security filters, `spring-security-test` for `csrf()`, a real `FilterRegistrationBean`, JUnit 5, and a configured login endpoint. Add log/event capture assertions and same-thread cleanup checks; two different response IDs **do not by themselves prove** MDC was cleaned up on the worker thread.

### Testing MDC Leaks with a Thread-Reusing Executor

To genuinely test thread cleanup, use a single-thread executor or test instrumentation to run two tasks sequentially **on the same thread**. Check `MDC.get("requestId")` after task A finishes and before task B starts; it must be empty or restored to the expected outer scope.

Do not simply run two sequential MockMvc requests and conclude they shared the same Servlet worker thread in real deployments. Tests must establish thread ownership explicitly.

## 22. Negative and Abuse Case Testing

| Case | Expected Behavior |
| --- | --- |
| Username with CR/LF or JSON escapes | No forged log entry created |
| Password containing canary string | Absent from all sinks/log captures |
| Invalid Bearer token | Emits `TOKEN_INVALID` event, does not print token |
| Session cookie | Never appears raw in events/traces |
| Duplicate/malformed `X-Request-ID` header | Untrusted; fresh server ID generated |
| Spoofed `X-Forwarded-For` | Never recorded as verified client IP |
| Trace baggage containing email | Never forwarded/logged in violation of policy |
| API key used by service | Logs issued public key ID if needed, never raw secret |
| Password login for nonexistent account | Does not reveal user existence in client response |
| Login succeeded but MFA incomplete | Not counted as `LOGIN_COMPLETED` |
| Provider outage | Reason `PROVIDER_ERROR`, not `BAD_CREDENTIALS` |
| Access denied 403 | Not confused with login failure |
| Audit sink unavailable | Fails closed or degrades per approved policy; alerts fire |
| Login attempt flood | Does not exhaust disk/SIEM; retains necessary security signals |
| Log export | Enforces RBAC, retention, and access auditing |
| Service restart | Does not lose mandatory audits when durability is required |

**Fail-closed or degrade?** There is no universal answer. A financial product may require durable audit persistence before allowing sensitive actions to succeed; another service may keep logins available during a log platform outage while buffering in a queue, alerting, and reconciling afterward. The decision must be documented in security/compliance requirements rather than left to an accidental exception in a synchronous listener.

## 23. Operating Safely in a Microservices Architecture

When requests travel from a gateway across multiple services:

- Maintain **one clear correlation policy**: use a dedicated request ID alongside distributed traces, or standardize how they link.
- The gateway trusts trace/request metadata only under explicit rules; downstream services never treat Internet-originating values as authenticated.
- Propagate traces via standard instrumentation instead of blindly copying all MDC keys into Kafka headers.
- Async messaging: attach allowlisted opaque correlation metadata to messages; never include passwords, session cookies, or PII by default.
- Consumers create appropriate new spans/events while retaining parent/correlation links when permitted.
- Prevent leaks when one thread handles multiple messages; place MDC cleanup in `finally` at the consumer boundary.
- Define audit ownership: which service emits the authoritative event so gateway and services do not double-count logins.
- Deduplicate by `eventId` when audit sinks retry; understand at-least-once delivery and never assume exactly-once.
- Balance differing retention needs: traces may be kept for a few days while business audits are kept longer per policy.
- Maintain investigation runbooks using `requestId`/`traceId`/`eventId`, never relying on user-supplied claims as proof.

If you must correlate a user across services, use a subject ID verified by the issuer/identity provider with appropriate scoping. A correlation ID **does not authenticate a user**; it only connects records.

## 24. Common Operational Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Logging `Authentication.toString()` | May leak principal/sensitive metadata | Log event type/outcome and minimal opaque ref |
| Logging unchecked exception messages | PII/credential leak or log forging | Allowlisted reason codes, exception category |
| Logging full headers/bodies | Exposes passwords/tokens/cookies | Field allowlists, disable sensitive body logging |
| Using username as request ID | Leaks PII and enables spoofing | Server-generated UUID |
| Trusting inbound `X-Request-ID` | Log spoofing/correlation poisoning | Strip/generate/enforce clear trust boundary |
| Skipping MDC cleanup | Bob gets Alice's request ID | `finally`/wrapper cleanup |
| Losing MDC in async code | Missing correlation in workers | Runtime-appropriate tracing/context propagation |
| Using ThreadLocal MDC in WebFlux without bridge | Wrong context when schedulers switch threads | Proper Reactor/tracing instrumentation |
| Mapping all exceptions to `BAD_CREDENTIALS` | Outages counted as credential attacks | Proper reason taxonomy |
| Using `AUTH_SUCCESS` as `LOGIN_COMPLETED` | MFA flows miscounted | Define events at exact boundaries |
| Using `requestId` as Prometheus label | High cardinality | Keep IDs in logs/traces; use enum tags in metrics |
| Trusting `X-Forwarded-For` from Internet | Spoofed audit IP | Trusted proxy configuration |
| Retaining logs forever | Privacy/cost/compliance risk | Retention + deletion policies |
| Audit only in in-memory listener | Data lost on crash | Durable audit pipeline when required |
| Overly broad log exporter permissions | Millions of identity records exposed | Least privilege/access auditing |
| Indefinite debug logging | Elevated risk and log volume | Change control/expiry/monitoring |
| Masking only in dashboard UI | Secrets already persisted in storage | Redact at the source |
| Putting all claims into trace baggage | PII leaks across services | Allowlist and minimize baggage |

## 25. Adoption Checklist

1. Is there a standard schema for `AUTH_SUCCESS`/`FAILURE`, MFA, logout, session revocation, and authorization denied?
2. Are `eventId`, `requestId`, `traceId`, `spanId`, and session/token IDs cleanly separated?
3. Are raw passwords, OTPs, cookies, access/refresh tokens, reset tokens, and authorization headers guaranteed never to be logged?
4. Do failure logs use backend-defined reason codes while avoiding raw usernames and exception messages?
5. Has every personal data field been reviewed for necessity, viewer permissions, and retention?
6. Are correlation IDs generated by a trusted server/gateway, independent of user input, and non-authoritative?
7. Do Servlet filters/MDC clean up in `finally` and handle `ASYNC`/`ERROR` dispatches properly?
8. Do async executors, Kafka consumers, WebFlux, and tracing propagate and clean up context per their execution model?
9. Are log integrity, encryption in transit/at rest, RBAC, export auditing, and backup retention enforced?
10. Are log injection, canary secrets, cross-service correlation, metric cardinality, and filter exceptions tested?
11. Are delivery failures, log sink outages, sampling, and duplicate events measured per policy?
12. Are incident investigation runbooks usable without asking users to send credentials?

**Conclusion:** Login logs are valuable when they preserve **context and accuracy**, yet security is only achieved when they simultaneously **minimize personal data and eliminate secrets**. Spring Security provides authentication events; Spring Boot/Micrometer can support trace correlation; MDC can attach request IDs on Servlet threads. Each mechanism has its own boundary. Good design requires controlled schemas, opaque IDs, trusted data sources, proper cleanup across threads/subscriptions, durable audits where mandated, access control, and leak-prevention testing. **Never trade user credentials for a few more readable debug lines.**

### References

- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Security Filter Chain: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Boot — Tracing and Logging Correlation IDs: https://docs.spring.io/spring-boot/reference/actuator/tracing.html
- Spring Framework — OncePerRequestFilter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- SLF4J — MDC API: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
- OpenTelemetry — Context Propagation: https://opentelemetry.io/docs/concepts/context-propagation/
