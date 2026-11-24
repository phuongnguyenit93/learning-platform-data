# Designing Login Audit Logs and Tracking Related Devices and Sessions in Spring Security

> **Scope:** Building an audit trail for user authentication, device management, and related sessions on Spring Boot 3 / Spring Security 6.x (Servlet, Java 17+). The focus is on **logging the right events and correlating logins and sessions without leaking credentials**, distinguishing device signals from identity proof, managing session lifecycles, and testing incident traceability. A safe audit log must be useful for investigations and users, yet never become a storehouse for passwords, JWTs, session cookies, or unnecessary identifying data.

## 1. Learning objectives

After this lesson, you will know how to:

1. Distinguish **authentication attempts**, **provider authentication success**, **MFA completion**, **session creation/rotation**, **logout**, **expiration**, and **session revocation**.
2. Design an audit schema with event ID, UTC timestamp, event type, outcome, actor/subject, correlation ID, method/factor, source network, device reference, and session reference using minimal data.
3. Understand the difference between **user identity**, **observed device**, **bound device**, and **HTTP session / access token**.
4. Use `AuthenticationSuccessEvent`, `AbstractAuthenticationFailureEvent`, success/failure handlers, `HttpSessionEventPublisher`, `SessionRegistry`, and Spring Security session events for their intended purposes.
5. Generate safe correlation references from session IDs using HMAC with a separate secret; **never log raw `JSESSIONID`**, access tokens, or cookies.
6. Distinguish features for **viewing login history**, **listing active sessions**, **logging out other devices**, and **anomalous login alerts**.
7. Test behavior across multi-node clusters, late/duplicate events, asynchronous logout or revocation, sensitive data leaks, and multi-factor login flows.

**Core problem:** Not every authentication success creates a new session, not every HTTP session proves a full login, and not every new User-Agent/IP means a new device. To be trustworthy, a log must express **what actually happened**, at which boundary, and with what level of certainty.

## 2. Threat model: log to protect, not to leak more

Login auditing helps detect credential stuffing, brute-force attacks, account takeover, session hijacking, logins from anomalous sources, and unauthorized MFA recovery events. However, the logging system itself can be exploited:

| Risk | Example | Defense mechanism |
| --- | --- | --- |
| **Credential leak via logs** | Logging `Cookie`, `Authorization` headers, passwords, OTPs, or raw session IDs | Allowlist-based redaction; never log entire requests |
| **Log injection** | User-Agent containing CRLF or control characters to forge audit lines | Encode/sanitize input before serialization |
| **Account enumeration** | Logs and public responses revealing whether a username exists or is locked | Access-controlled internal outcomes; generic public responses |
| **Excessive tracking** | Assigning persistent cross-site fingerprints or retaining raw IPs indefinitely | Data minimization, retention limits, clear purpose and access control |
| **Broken session correlation** | Rotating session ID after login but logs treat it as two separate users | Record rotated old/new refs linked by a verified event |
| **Duplicated events** | Recording success at both AuthenticationProvider and handler as two logins | Event IDs, distinct event types, deduplication |
| **Audit loss when queue fills** | App reports success while critical security history cannot be traced | Durable queue/outbox, error budget, backpressure |
| **Unauthorized audit tampering** | Attacker compromises admin and deletes their own login logs | Append-only/immutable storage, least privilege, separation of duties |
| **Audit pipeline DoS** | Bots spam usernames, generating unbounded logs or notifications | Quotas; sample only low-priority telemetry while preserving critical audits |
| **Ineffective session revocation** | UI claims "device logged out" while another store still accepts the session | Revoke authoritative store; verify across all instances |

**Do not use logging as a substitute for authorization.** An "unknown device" alert is insufficient to stop an attacker if the session/token remains valid; step-up, revocation, or risk enforcement must occur at the security boundary.

## 3. Every use of the word "login" can refer to a different event

Milestones should have distinct names:

| Suggested event type | Actual event | What must not be inferred |
| --- | --- | --- |
| `AUTH_ATTEMPT_OBSERVED` | Server/gateway observed an authentication request | Whether the username even exists |
| `AUTH_PROVIDER_SUCCEEDED` | `AuthenticationManager`/provider verified one mechanism successfully | Whether MFA is finished or a session was issued |
| `AUTH_PROVIDER_FAILED` | An authentication attempt was rejected | Whether password was wrong; could be account locked or outage |
| `MFA_CHALLENGE_STARTED` | A second-factor challenge was created | Evidence of the second factor |
| `MFA_VERIFIED` | Second factor verified and anti-replay state committed | Whether the session was saved successfully |
| `LOGIN_COMPLETED` | Authentication policy satisfied all factors and app is ready to authorize | Whether the client actually received the cookie |
| `SESSION_CREATED` | Session created in servlet/session store | Could be an anonymous pre-login session |
| `SESSION_ID_ROTATED` | ID changed for session fixation protection | Not a new device |
| `SESSION_AUTHENTICATED` | Session holds a valid security context per policy | Distinct from bare session creation |
| `SESSION_ACTIVITY_OBSERVED` | Valid request associated with an existing session | Not a new login |
| `LOGOUT_REQUESTED` | Valid logout request received | Whether all external state was revoked |
| `SESSION_REVOKE_REQUESTED` | User/admin requested terminating a session | Proof that the entire cluster rejects the session yet |
| `SESSION_REVOKED` | Authoritative backend store invalidated the session | In-flight requests may have started earlier |
| `SESSION_DESTROYED` / `SESSION_EXPIRED` | Container/store reports the session is no longer active | Termination reason may need another source |
| `DEVICE_REMEMBERED` / `DEVICE_FORGOTTEN` | App registered/removed a remembered device with consent | Not equivalent to biometric or hardware-key authentication |
| `RISK_ALERT_RAISED` | Analytics detected a suspicious signal | An indicator, not proof of compromise |

**Distinguishing "authentication success" from "login completed":** Spring's `AuthenticationSuccessEvent` is emitted at the authentication mechanism layer when a publisher is configured. It can occur while a TOTP step remains, on every HTTP Basic request, or when a custom flow returns authentication without saving a session. To audit "login succeeded and session ready," emit an event at the **exact point where the application knows the entire flow is complete**, rather than inferring from provider success alone.

With OAuth2/OIDC, the IdP also has its own login/SSO session while the application has its local session. Local logout **does not guarantee** IdP logout or revocation of every refresh token; logs must reflect the actual outcome in each system.

## 4. Three-entity model: account, device, session

~~~text
                     ACCOUNT (user_id)
                         |
               +---------+-----------+
               |                     |
         DEVICE RECORD A        DEVICE RECORD B
         (if the app            (if the app
          actually manages it)   actually manages it)
               |                     |
       +-------+-------+             +-------+
       |               |                     |
   SESSION S1       SESSION S2            SESSION S3
   browser A        browser A            mobile B
   shared tabs      different profile    or client token
       |
       +-- AUTH ATTEMPTS / MFA EVENTS / RISK SIGNALS / ACTIVITY
~~~

One account can have multiple devices and multiple sessions. One browser profile can have multiple sessions due to logout/login or cleared cookies. Multiple tabs in the same browser profile normally **share the same session cookie**, so "3 open tabs" **does not** equal 3 devices or 3 concurrent sessions. A session can change its ID after login/reauth while remaining the same authentication journey.

### Account/user identity

- Before authentication, username/email is a **client-supplied claim** that may be wrong or nonexistent; store an access-controlled fingerprint rather than treating it as a verified `user_id`.
- After authentication, use the application's immutable subject ID (or issuer + subject for OIDC) as the identity reference. Do not rely on email as a global key if emails can change or collide across tenants.
- In multi-tenant systems, stable identity should include tenant/issuer; never allow clients to supply an arbitrary tenant ID to link another user's history.

### Device

- `User-Agent`, IP, ASN, OS/browser version, or inferred location are **observed signals**—error-prone, frequently changing, and spoofable.
- An app-issued device ID in a cookie can support a "familiar device" UX, yet a copied cookie can also be forged. Do not treat it as proof of device possession or a substitute for passwords/MFA.
- Only WebAuthn/FIDO2 credentials or device keys with proof of possession can support **cryptographic binding** when properly enrolled and verified; policies, revocation, and risk assessment are still needed.
- "Remembered device" differs from "device trusted enough to skip MFA"; reducing step-up requires dedicated mechanisms, TTLs, user consent, and security review.

### Session

- `HttpSession` in Servlet containers is typically referenced by a container-managed `JSESSIONID` cookie. The cookie is a **bearer secret**, not an identifier to display in logs/UI.
- In Spring Security, `SecurityContext` holds `Authentication` (principal, authorities, state). A session can exist before login, unauthenticated, or mid-MFA flow.
- Stateless APIs using access tokens/JWTs do not share the HTTP session lifecycle; tokens have their own `jti`/issuer/subject and expiry, and revocation of self-contained JWTs must be designed separately. Never write raw JWTs into audits.

## 5. Designing a minimal, consistent, and semantic audit schema

An audit record should include the following field groups (all data validated before writing):

| Field | Suggested data | Rules |
| --- | --- | --- |
| `event_id` | Server-issued unique UUID/ULID | Deduplication and immutable cross-referencing |
| `event_type` | Enum such as `AUTH_PROVIDER_FAILED` | Versioned taxonomy, never free-form from clients |
| `schema_version` | 1, 2... | Supports consumer upgrades |
| `occurred_at` | UTC `Instant` timestamp | Never trust client clocks |
| `recorded_at` | When the audit system actually received it | Measures queue lag and late events |
| `service`/`environment`/`region` | Bounded server-supplied identifiers | Cross-service correlation, low cardinality |
| `actor_ref` | Verified identifier/pseudonym | Null when user is unknown |
| `submitted_identifier_ref` | HMAC fingerprint of login input if needed | Not a verified user ID |
| `tenant_ref` | Tenant from a trusted source | Never use raw tenant params to assert authorization |
| `outcome`/`reason_category` | SUCCESS, DENIED, INFRA_ERROR... | Internal reason, avoid raw exceptions |
| `auth_method`/`factor` | PASSWORD, OIDC, WEBAUTHN, TOTP... | Marks actual verification level |
| `attempt_ref` | ID for one login attempt / MFA journey | Links prelogin -> postlogin steps |
| `session_ref` | HMAC/surrogate, never raw cookie | Cannot be used as a bearer credential |
| `previous_session_ref` | Only on verified session ID rotation | Links before and after |
| `device_ref` | Device record/app-issued reference if any | Categorize device evidence level |
| `source_network` | Truncated/HMAC IP, ASN if needed | Comply with privacy/retention rules |
| `user_agent_family` | Reduced browser/OS family | No need to log full User-Agent |
| `request_id`/`trace_id` | Trace issued by gateway/backend | Must not contain query secrets or PII |
| `action`/`confidence` | Allow, step-up, alert; low/medium/high | Do not treat inferred signals as ground truth |
| `causation_event_id` | Event that led to the new event | Trace action chains and prevent loops |

**Schemas can be stored as JSON lines, indexed audit tables, or message-broker events.** Not every product needs every column. Retain only data genuinely serving defense, investigation, user support, compliance, and operations. Normalize `event_type` and `reason_category` via finite enums to prevent log injection and metric explosion.

### A sanitized audit event

~~~json
{
  "schema_version": 1,
  "event_id": "3c9b2e18-248b-4a40-927b-9009a8acbc67",
  "event_type": "SESSION_AUTHENTICATED",
  "occurred_at": "2026-11-06T09:10:00Z",
  "service": "customer-portal",
  "environment": "prod",
  "actor_ref": "usr_ea24c9",
  "attempt_ref": "att_f712",
  "session_ref": "sr_47a11ad7c29a9b7234e98fc70225d3aa",
  "device_ref": "dev_a5c1",
  "auth_method": "PASSWORD_TOTP",
  "outcome": "SUCCESS",
  "source_network": "203.0.113.0/24",
  "user_agent_family": "Chrome",
  "request_id": "req_2b18"
}
~~~

The IDs, network address, and timestamps above are **illustrative documentation values**, not real logs. The IP belongs to the TEST-NET-3 documentation range. In real request logs, `device_ref`/`actor_ref` may be unknown: leave them null, and **never fabricate** an identity or "device" from an untrusted header.

### Which data must never be logged directly?

- Passwords, TOTP/HOTP codes, recovery codes, passkey private keys, PINs, security answers.
- `JSESSIONID` cookies, `Authorization` headers, access/refresh tokens, full JWTs, API keys, CSRF tokens, or raw session IDs.
- Full `Authentication.toString()`, `SecurityContext`, login request bodies, exceptions containing credentials, or stack traces sent to user channels.
- URL queries containing tokens/reset links; raw User-Agents with newlines/control characters; detailed IP addresses or precise geolocation when unnecessary.
- Sensitive PII fields added solely to inflate metric cardinality or perform purposeless "device analytics."

OWASP recommends correlating sessions **without storing raw session IDs**; salted hashes or HMACs can be used instead. HMAC with a secret audit key prevents exposing raw session identifiers and resists ID guessing from logs better than an unkeyed hash; still enforce access controls and retention limits on audit references.

## 6. Multiple ID types: never mix them up

| ID | Where generated | Purpose | Safe to log verbatim? |
| --- | --- | --- | --- |
| `user_id`/`subject` | Trusted user store or IdP | Verified identity | Policy-dependent; often pseudonymized |
| `attempt_id` | Server at flow start | Links authentication and MFA | Yes if random and grants no access |
| `request_id` | Trusted ingress/server | Single HTTP request | Usually yes if format-validated |
| `trace_id` | Tracing framework/gateway | Across spans/services | Yes if sensitive baggage is stripped |
| Raw `HttpSession.getId()` | Servlet container/session store | Session authentication and routing | **No** in audits/logs |
| `session_ref` | HMAC/audit mapping | Correlates events of one session | Yes, as restricted audit data |
| `device_id` | Server/credential enrollment | Groups sessions sharing a device record | Conditionally; does not replace auth |
| `jti`/token family ref | Issuer/token service | Identifies issued tokens | Per policy; never log raw bearer token |

**Session fixation protection:** After login, Spring Security may rotate the session ID. A `session_ref` computed from the old ID differs from the new one; linking logs requires a `SESSION_ID_ROTATED` event containing both `previous_session_ref` and the new `session_ref`. Generate this link exclusively from server/container data and ensure both refs belong to the same session transition, never from browser-supplied claims.

**HMAC key protection note:** Store the audit HMAC key in KMS/a secret manager, separate from JWT or token signing keys, with versioning, least-privilege access, and a rotation schedule. Use sufficient digest length (e.g., 128 bits or more for correlation within data bounds) to minimize collisions, and compute it from the **raw session ID solely in server memory**, never emitting the raw ID into events. When rotating the audit key, old/new refs may differ; design key versioning or transition windows aligned with retention. An HMAC session ref cannot be used in place of a session cookie to log in.

## 7. Standalone Java 17: safe session references and log injection

This is a plain JDK 17 example illustrating how to generate an **HMAC-SHA256 correlation reference** for a session without printing the raw ID, link events before/after ID rotation, and neutralize basic newline/control characters. The HMAC key and session IDs in the program are **dummy test data**, not production configuration.

Create file `AuthAuditDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class AuthAuditDemo {
    record AuditEvent(String type, String userRef,
                      String sessionRef, Instant occurredAt) {}

    static String sessionReference(String rawSessionId, byte[] auditKey)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(auditKey, "HmacSHA256"));
        byte[] digest = mac.doFinal(
                rawSessionId.getBytes(StandardCharsets.UTF_8));
        // First 16 bytes (128 bits) are enough for demo correlation.
        return "sr_" + HexFormat.of().formatHex(digest).substring(0, 32);
    }

    static String sanitize(String untrusted) {
        if (untrusted == null) {
            return "";
        }
        return untrusted.replace('\r', '_')
                .replace('\n', '_')
                .replace('\t', '_');
    }

    public static void main(String[] args) throws Exception {
        byte[] auditKey = "demo-only-audit-key-not-for-production"
                .getBytes(StandardCharsets.UTF_8);
        String originalSessionId = "session-secret-old";
        String rotatedSessionId = "session-secret-new";

        String oldRef = sessionReference(originalSessionId, auditKey);
        String newRef = sessionReference(rotatedSessionId, auditKey);

        List<AuditEvent> events = List.of(
                new AuditEvent("AUTH_PROVIDER_SUCCEEDED", "u_17",
                        oldRef, Instant.parse("2026-11-06T00:00:00Z")),
                new AuditEvent("SESSION_ID_ROTATED", "u_17",
                        newRef, Instant.parse("2026-11-06T00:00:01Z")),
                new AuditEvent("LOGOUT_COMPLETED", "u_17",
                        newRef, Instant.parse("2026-11-06T00:05:00Z"))
        );

        System.out.println("events: " + events.size());
        System.out.println("rotation changed reference: "
                + !oldRef.equals(newRef));
        System.out.println("logout same reference: "
                + events.get(1).sessionRef().equals(
                        events.get(2).sessionRef()));
        System.out.println("raw session absent: "
                + events.stream().noneMatch(e ->
                        e.sessionRef().contains("session-secret")));
        System.out.println("injection sanitized: "
                + sanitize("Chrome\r\nrole=admin")
                        .equals("Chrome__role=admin"));
        System.out.println("timestamps ordered: "
                + events.get(0).occurredAt().isBefore(
                        events.get(1).occurredAt()));
    }
}
~~~

Compile and run:

~~~bash
javac AuthAuditDemo.java
java AuthAuditDemo
~~~

Exact stdout:

~~~text
events: 3
rotation changed reference: true
logout same reference: true
raw session absent: true
injection sanitized: true
timestamps ordered: true
~~~

**Explanation:**

1. Two different raw session IDs produce two different HMAC refs. In real audits, add a `previous_session_ref` field to the rotation event to link S1 -> S2; this program only illustrates that the ID ref changes.
2. The logout event and the rotated event share the new ref, allowing correlation without logging cookies.
3. The `sanitize` helper prevents CR/LF/tab from forging log lines in the example; production needs **structured logging with a proper encoder**, length limits, Unicode/control-character policies, and validation on every input field. Never rely on one small replace helper as your sole defense.
4. The code does not create, issue, validate, or revoke real sessions; `sessionReference` is strictly for **audit correlation**. Replace the hardcoded demo audit HMAC key with KMS/secret manager, versioning, and rotation in production.
5. Event timestamps use `Instant.parse` for deterministic output; production apps must use a trusted `Clock`/server time and also record `recorded_at` to measure ingestion lag.

## 8. Event flow: from login request to an active session

A username/password + TOTP flow in Servlet:

~~~text
POST /login
    |
    +-- REQUEST_OBSERVED (new attempt_ref)
    |
    +-- AuthenticationManager
           |
           +-- BadCredentials -> AUTH_PROVIDER_FAILED, no login session
           |
           +-- password OK -> AUTH_PROVIDER_SUCCEEDED (factor=PASSWORD)
                                  |
                                  v
                           MFA_CHALLENGE_STARTED
                                  |
                            correct TOTP + atomic replay update
                                  |
                                  v
                           MFA_VERIFIED
                                  |
                         policy-sufficient auth/authorities
                                  |
                      session fixation protection
                      session ID may change
                                  |
                     SecurityContext persisted
                                  |
                                  v
                          SESSION_AUTHENTICATED
                                  |
                  +---------------+----------------+
                  |               |                |
                activity        logout       expiry/revoke
                  |               |                |
          SESSION_ACTIVITY   LOGOUT_*      SESSION_DESTROYED
~~~

All milestones depict an **application event-semantics model**—not every arrow automatically emits a Spring event with that same name. Spring provides a few built-in events; events like `MFA_VERIFIED`, `SESSION_AUTHENTICATED`, and `DEVICE_REMEMBERED` are security business events that **the application must emit itself** after the corresponding transaction commits.

A provider success can occur **multiple times** in a single login (password, OTP, OAuth2 callback, remember-me, or another token authentication), or create no local HTTP session in stateless REST. Do not equate `AuthenticationSuccessEvent` counts with "successful user logins" without separating flows and deduplicating.

### Two timestamps that are often overlooked

- `occurred_at`: when the authentication/session step occurred on the source node.
- `recorded_at`: when the audit sink confirmed persisting the event.

When using queues, `recorded_at` can lag seconds or minutes behind `occurred_at`. Nodes can also have clock skew, so tracing should use `attempt_ref`, `causation_event_id`, and state-transition ordering rather than sorting UTC timestamps alone to assert causality.

## 9. Spring Security: capturing provider success/failure events

Spring Security 6.x supports `AuthenticationEventPublisher`. `DefaultAuthenticationEventPublisher` can publish `AuthenticationSuccessEvent` and subclasses of `AbstractAuthenticationFailureEvent` based on exceptions. When building a custom `AuthenticationManager`, make sure the publisher is attached; do not assume every custom authentication path publishes events automatically.

Bean to publish if the application lacks an appropriate publisher:

~~~java
package example.security;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;

@Configuration
public class AuthenticationEventConfiguration {

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationEvents) {
        return new DefaultAuthenticationEventPublisher(applicationEvents);
    }
}
~~~

Conceptual listener: receives the **authentication object** from Spring, extracts sanitized fields, and forwards them to an audit sink. This snippet runs inside a project with real `AuditWriter`/`IdentityReferences` beans; **it is not a standalone `javac` program**:

~~~java
package example.security;

import java.time.Instant;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.stereotype.Component;

@Component
public final class AuthenticationAuditListener {
    private final AuditWriter writer;
    private final IdentityReferences identities;

    public AuthenticationAuditListener(
            AuditWriter writer, IdentityReferences identities) {
        this.writer = writer;
        this.identities = identities;
    }

    @EventListener
    public void success(AuthenticationSuccessEvent event) {
        String subject = identities.fromVerified(
                event.getAuthentication());
        writer.append(new AuditRecord("AUTH_PROVIDER_SUCCEEDED",
                subject, "SUCCESS", Instant.now()));
    }

    @EventListener
    public void failure(AbstractAuthenticationFailureEvent event) {
        String submitted = identities.fromSubmitted(
                event.getAuthentication());
        String reason = reasonCategory(event.getException());
        writer.append(new AuditRecord("AUTH_PROVIDER_FAILED",
                submitted, reason, Instant.now()));
    }

    private static String reasonCategory(AuthenticationException error) {
        if (error instanceof BadCredentialsException) {
            return "BAD_CREDENTIALS";
        }
        if (error instanceof LockedException) {
            return "LOCKED";
        }
        return "AUTH_ERROR";
    }

    public record AuditRecord(
            String type, String subjectRef, String result, Instant at) {}

    public interface AuditWriter {
        void append(AuditRecord record);
    }

    public interface IdentityReferences {
        String fromVerified(Authentication authentication);
        String fromSubmitted(Authentication authentication);
    }
}
~~~

**Conditions for correct use:**

- `IdentityReferences.fromVerified` extracts a stable verified user ID or appropriate pseudonym. `fromSubmitted` must convert an unverified username into a keyed HMAC/fingerprint with an appropriate TTL without asserting account existence or logging raw user input.
- Never call `event.getAuthentication().toString()`: the object may contain credentials, request details, principal attributes, or personal data.
- `reasonCategory` maps only categories needed for analysis and never logs `exception.getMessage()`; backend errors should be categorized separately when the contract allows. Custom exceptions may require `DefaultAuthenticationEventPublisher.setAdditionalExceptionMappings(...)` because default mapping uses **exact exception-class matching**, not automatic subclass coverage.
- `AuthenticationSuccessEvent` does not carry full request/session/device metadata in every flow. Collect controlled context at the filter/gateway or success handler and join via `attempt_ref`/trusted request context; **never** infer IP/device from `Authentication.getName()`.
- Avoid configuring multiple publishers or listeners writing the same event type and causing double counts. With custom `ProviderManager` instances and parent managers, verify publishing paths to prevent duplicate events.
- `@EventListener` runs synchronously with the publisher by default. `AuditWriter.append` must never block login over slow SIEM networking; use a bounded durable outbox/queue with clear contracts for critical events.
- On stateless REST APIs, an authentication event may fire on **every request** rather than once per browser login. Keep HTTP request auth metrics separate from login session counts.

## 10. Spring Security: success/failure handlers and HTTP context

`AuthenticationSuccessHandler`/`AuthenticationFailureHandler` in form login have access to request/response, allowing them to see remote addresses, selected headers, CSRF/redirect/correlation metadata, and flow outcomes. This complements listeners at the provider layer.

Never use a success handler to record "session created" **before** session fixation, saving `SecurityContext`, or MFA step-up finishes. If a custom success handler replaces the default handler, responsibility for managing `SecurityContext`/sessions and redirects can change; test against your exact framework version. Simply entering the handler only proves handler execution started, not that the browser received the cookie or used the session.

You can generate a random server-side `attempt_ref` in the pre-auth flow, carry it across MFA steps, and attach it to the session-level audit upon login completion. Protect against session fixation, CSRF, replay, and scope misuse of the attempt reference; never trust a client-supplied query parameter to link two different users. In OIDC, use `state`/nonce per protocol, and **never reuse them as public event labels** or print them to logs.

The **login failure handler** should map errors to a generic public message while auditing a controlled reason category. `BadCredentialsException` differs from `LockedException` and `AuthenticationServiceException`; recording the wrong event type can trigger false-positive account takeover alerts or hide an IdP/LDAP outage.

### Emission point for custom event SESSION_AUTHENTICATED

At the end of the flow, emit only when:

1. Identity and all mandatory factors have been verified.
2. Session fixation protection (if used) has completed and the final session ID is known.
3. `SecurityContextRepository` saved the security context and the backend committed; in Spring Security 6, custom auth may require **explicit `saveContext(...)`** to persist across requests.
4. Authorization/TTL/remember-me decisions per policy have been applied, and the event holds `actor_ref` and a `session_ref` newly derived from the server-side ID.
5. If an event was emitted before commit and commit fails, record a `FAILED` outcome or use a transactional outbox to prevent phantom login audits.

**Never log cookie values.** If correlation is needed in tests, compute an HMAC `sessionRef` on the trusted server side; never send raw IDs to a message broker.

## 11. Managing session lifecycle and concurrency

Spring Security Servlet provides `HttpSessionEventPublisher` to translate servlet session lifecycle events into Spring application events, `SessionRegistry`/`SessionRegistryImpl` for concurrent session control, and `SessionInformation` to describe sessions. Example configuration for a session-based form login app:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class SessionSecurityConfiguration {

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error", "/assets/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionFixation(fix -> fix.changeSessionId())
                        .maximumSessions(3)
                        .maxSessionsPreventsLogin(false))
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

**Meaning and limitations:**

- `sessionFixation(...changeSessionId())` rotates the ID via the Servlet mechanism at login to prevent session fixation; rotating the ID does not mean creating a new device. The server can receive `SessionIdChangedEvent` when the lifecycle publisher is properly configured.
- `maximumSessions(3)` sets an illustrative limit of 3 concurrent sessions per user; by default, exceeding the limit expires the oldest session depending on `maxSessionsPreventsLogin`. Choose numbers per policy and test across devices. With custom authentication filters, you may need to attach the session authentication strategy manually.
- `HttpSessionEventPublisher` helps report session destroyed/ID changed; it **does not** guarantee every session end (closing a browser tab, losing network, expired JWT) emits an event immediately.
- `SessionRegistryImpl` defaults to JVM local memory. Across multiple instances, if you want a **cluster-wide** active session list or revocation state, use a shared session repository/registry or integrate Spring Session where compatible with your store—do not assume using Redis for general caching makes the registry distributed.
- When using a custom `UserDetails` as the principal, implement consistent `equals()/hashCode()` if the registry keys by principal object, otherwise per-user session counts will be wrong.
- `SessionInformation.expireNow()` marks a session expired in the registry; actual enforcement usually happens on the next request when a Spring filter checks state. Do not promise "terminated all in-flight requests" without backend stream/connection closing mechanisms. With a distributed session store, delete the authoritative record and propagate invalidation per design.
- With stateless OAuth2 Resource Server/JWT, HTTP `SessionRegistry` does not manage client access tokens like session cookies; design token revocation/short TTL/introspection separately.

### Different session events

`SessionCreationEvent`, `SessionDestroyedEvent`, `SessionIdChangedEvent`, and their HTTP counterparts reflect container lifecycles, not whether a user completed MFA. When receiving session-destroyed, you may not know whether the cause was logout, timeout, concurrent expiry, or admin revocation unless you keep a separate causal event. Record `LOGOUT_REQUESTED`/`SESSION_REVOKE_REQUESTED` and correlate with destruction for reliable reasons.

Spring Security emits logout events from framework flows when configured, yet local logout success does not prove the IdP SSO session, remember-me tokens, or all client tokens were revoked. Explicitly tag scope as **`LOCAL_SESSION_LOGOUT`** when only the local session is cleared.

## 12. "My devices and sessions" view for users

A helpful account security UI can display:

| UI column | Source / meaning | What not to do |
| --- | --- | --- |
| Device/browser | Browser family, OS family inferred from User-Agent | Claim exact device model/owner from UA alone |
| Sign-in time | `SESSION_AUTHENTICATED` of that session | Display provider success as a completed login |
| Last activity | `SESSION_ACTIVITY_OBSERVED` throttled by interval | Write a DB update on every pixel/API call |
| Approximate region | IP geolocation when permitted and reliable | Display street-level address accuracy |
| Current session | Matched server-side against the current authenticated request's `sessionRef` | Trust `current=true` sent by the client |
| Remembered device | Enrolled device record with user consent | Grant elevated trust solely because UA looks similar |
| Status | Active, expired, revoked, logged out, unknown | Claim "online realtime" from last-seen timestamps alone |
| Actions | Log out this session, log out all other sessions, forget device | Only delete UI/audit rows without real revocation |

**Two distinct datasets: history and active sessions.** Login history is an append-only sequence of past events, including dead sessions. Active sessions are a live view of the authoritative session store/registry, cross-checked against TTL, expired flags, and revocation. A historical login audit record **does not mean** the session is still alive days later.

### Suggested APIs (application-built)

| Endpoint | Function | Security boundary |
| --- | --- | --- |
| `GET /account/security/logins` | Read login history filtered to current user | Authenticated subject only, pagination/retention |
| `GET /account/security/sessions` | List active sessions from registry/repository | Never expose raw session IDs/tokens |
| `DELETE /account/security/sessions/{publicRef}` | Revoke a session looked up by opaque UI ref | Server-side ownership check, anti-IDOR |
| `POST /account/security/sessions/revoke-others` | Revoke other sessions | Reauthentication/MFA per policy, CSRF protection |
| `GET /account/security/devices` | List registered device records | Keep inferred fields separate from verified ones |
| `DELETE /account/security/devices/{deviceRef}` | Forget/revoke a remembered-device credential | Do not auto-revoke all sessions unless policy requires |

These URLs are application API designs, **not endpoints auto-generated by Spring Security**. `publicRef` should be a random UUID/surrogate **unusable for authentication** and distinct from raw session cookies; the server maps it to the owned session after verifying `user_id`. A hijacked current session cookie could be used to click "log out other sessions"; high-risk actions should require **fresh authentication/MFA** before revoking everything or removing device trust.

To prevent CSRF, cookie-authenticated POST/DELETE session-management endpoints must enforce CSRF protection matching the application's session model. Never put `sessionId` in URLs or raw tokens in responses. After a user clicks revoke, the backend must actually update the session store/registry, not merely delete an audit row or `device record`.

## 13. Login events from "unfamiliar" devices and alerts

An unfamiliar device is a **probabilistic concept**, not automatically an attack. A browser auto-update, private browsing mode, cleared cookies, switching 4G/Wi-Fi, or using a VPN can produce the same signals as a new device. Conversely, an attacker can clone an old device's User-Agent and cookies.

### Useful signals

- Successful login after a large burst of failures or multiple IPs.
- New session appearing right after a password/MFA reset.
- Two sessions logging in from incompatible regions within a short window (**impossible travel** is only an uncertain signal).
- Never-seen device remembered cookie, or an enrolled device credential/attestation presenting invalid proof.
- Significant User-Agent/OS family change, risky IP/ASN, or unusual access time.
- Token reuse or refresh token family showing replay signs.
- Opening many sessions in a very short period, changing privileges, and exporting sensitive data.

**Never conclude "the user was definitely hacked" from a single new IP.** Risk engines need confidence levels, explainability, low false positives, escalation policies, and support paths. For sensitive operations, step up with registered TOTP/WebAuthn/passkeys, temporarily restrict actions, or require reauthentication; never permanently lock accounts based on imprecise IP geolocation.

### Notification design

- Send new-login alerts only after **login actually completes**, not on every `AUTH_PROVIDER_SUCCEEDED` mid-MFA.
- Keep content helpful yet minimized: timestamp, browser family, approximate region if needed, link to the session management page.
- Email links should point to the **official security page**, without long-lived magic tokens or raw sessions. Never let attackers inject arbitrary redirect URLs.
- Rate-limit/deduplicate notifications; prevent bots from triggering thousands of emails via bad passwords, and account for unauthenticated users.
- If a user clicks "That wasn't me," the next step must **revoke/reauthenticate per protocol** and report status—not just file a ticket or mark the alert read.
- Never trust notification channels recently altered by an attacker without audits and safeguards around email/phone changes.

## 14. Privacy, retention, and access control for login data

IP addresses, device history, estimated geolocation, login times, and session correlations can reveal personal behavior. Therefore, logging must obey **clear purpose, minimization, retention limits, access controls, and applicable law**. Pseudonymized IDs remain linkable/re-identifiable via the system and do not automatically become anonymous data.

### Separating three stores by purpose

| Store | Data contained | Who can access |
| --- | --- | --- |
| Operational metrics | Total auth successes/failures, latency, event lag, error categories | SRE/Monitoring; low cardinality, no raw PII |
| Security audit | Actor refs, event types, session refs, reasons, correlations, risk signals for investigation | Security/compliance with RBAC and read-access auditing |
| User-visible history | Login time, browser/OS family, approximate location, and status | Account owner only, paginated, no session secrets |

**Retention:** Set distinct policies for raw network data, device observations, security audit events, and aggregate metrics. For example, "keep audit logs for 90 days" is a product decision requiring approval, not a universal standard across all jurisdictions. Investigations or legal holds may follow dedicated legal workflows, yet must not become an excuse to keep every IP address forever.

**Access control:** Support staff do not need default visibility into full IPs or session correlations for every user. Access to sensitive logs requires explicit permissions, justification, auditing, and bulk-read alerts. Enforce export/download controls, encryption at rest/in transit, retention, and deletion per policy.

**Privacy-by-design:** Do not enable canvas/font/plugin fingerprinting just to label "this device is an iPhone." Prefer existing signals at appropriate granularity with consent and minimization, and surface uncertainty rather than misleading users into thinking IP geolocation is pinpoint accurate.

## 15. Reliable audit pipeline: durability, ordering, idempotency

Production systems typically decouple login/session transactions from the audit pipeline:

~~~text
Spring Security / Authentication service
    |
    +-- emit structured event with server-owned event_id, actor_ref
    |
    +-- durable outbox / bounded queue (depending on criticality)
                   |
                   v
          Audit consumer / sanitizer
                   |
           +-------+----------+
           |                  |
     Append-only log      Risk analytics
           |                  |
      Indexed queries     Alerts / step-up
           |
     User session history view (filtered)
~~~

**Do not perform heavy work inside a synchronous EventListener.** Querying geolocation, sending emails, calling SIEM, or formatting stack traces on the HTTP login thread slows authentication and creates DoS exposure when the audit backend lags. Use a durable queue, bounded sizing, backpressure, and idempotency—or a transactional outbox when login must be tightly bound to event evidence.

### Operational invariants

1. **Never fake success:** Emit `SESSION_AUTHENTICATED` only after authentication/session state has committed per contract. If emitted earlier and commit fails, record an accurate failure outcome or use an outbox in the same transaction.
2. **At-least-once => dedupe:** Message brokers can deliver the same event multiple times. Sinks must use `event_id` as an idempotency key; never turn duplicate deliveries into two logins.
3. **Out-of-order:** A logout event may arrive before session-created due to queue sharding. Consumers should process `causation_event_id`/sequences and never "resurrect" a session just because a late event arrived.
4. **Never delete historical events on revocation:** Audits are an append-only event stream; active sessions are a stateful view. Deleting a login record to "log out" is semantically wrong.
5. **Backpressure/failure policy:** When the sink is unavailable, follow a risk-assessed policy for mandatory security events rather than silently dropping them; secondary metrics may be sampled per policy. Never retry infinitely inside an HTTP request.
6. **Access integrity:** Audit storage should enforce append-only/immutable retention and separated permissions, with logging on configuration reads/changes.
7. **Clocks/traces:** Retain UTC timestamps, `recorded_at`, correlation/causation IDs, and schema versions; across multi-region clock skew, never infer absolute ordering solely from timestamps.
8. **Sensitive fields:** Sanitize at the source, minimize payloads before queuing, and verify redaction before exporting logs to third parties.

### Metrics without cardinality explosion

Use bounded labels such as `event_type`, `outcome`, `method`, `environment`, `region`, and `service`. Never put `user_id`, `session_ref`, full IP, `attempt_ref`, or device fingerprints in Prometheus labels. Those IDs belong in an access-controlled indexed audit store, not as dimensions in time-series metrics.

## 16. Multi-instance, Spring Session, and consistency limits

### SessionRegistryImpl does not auto-sync cluster-wide

With 3 application pods, each pod has its own `SessionRegistryImpl`, so calling `getAllSessions(...)` on pod A does not automatically include sessions registered on B/C. If the UI displays "all active sessions" or enforces cluster-wide maximum sessions, use a **shared session repository/registry** and test synchronization—such as integrating Spring Session when compatible with your session store. Do not treat using Redis for general caching as proof that the registry is properly distributed.

### "Revoked" sessions while requests are still running

A user/admin revocation flow can consist of:

1. Authenticating the requester and verifying target session ownership/authority using server-side data.
2. Writing revoked/expired state to the authoritative session store or deleting the session via backend APIs.
3. Emitting `SESSION_REVOKED` after commit with causation and `actor_ref`; issuing cache invalidations if applicable.
4. Testing that **new** requests using the old cookie are rejected across every pod/region.
5. Evaluating whether **in-flight** requests or websocket/long-poll streams need dedicated termination.
6. Updating the active-session UI from live state while keeping historical audits separate.

`SessionInformation.expireNow()` in Spring may only block the session on the next request when a filter checks state. If "immediate cluster-wide revocation" is required, ensure backend enforcement and measure the SLA rather than calling one method on a local registry and declaring done.

### Access tokens, JWTs, and refresh tokens

An app with browser session cookies may simultaneously issue JWT access tokens to mobile clients. Never conflate tokens with server `HttpSession`:

- Self-contained access tokens generally remain valid until `exp` unless the resource server adds mechanisms (denylist, token versioning, introspection, short TTL).
- Refresh tokens have separate lifecycles, rotation/reuse detection, and revocation; never log raw tokens, only family ID/`jti` per policy.
- `LogoutSuccessEvent` on a local web session does not prove IdP or other-device refresh tokens were revoked.
- Tag `auth_method` and `credential_type` so the UI accurately reflects web sessions, mobile app sessions, and API service accounts.

### Offline / missing session destroyed events

Closing a browser tab does not necessarily send a logout request; a user who loses connectivity sends no further requests. `last_seen_at` is not proof of being "online," and timeouts may only be noticed when the session store sweeps TTLs or an expired request arrives. The UI should state "last active at..." rather than claiming a device is online in real time without a heartbeat/proof.

## 17. Automated and real-world test scenarios

### Unit tests for schema, privacy, and correlation

- Event ID is unique, schema version and `event_type`/`outcome` come from accepted enums; invalid types never become arbitrary log fields.
- Raw `JSESSIONID`/cookies, access tokens, passwords, OTPs, and recovery codes **never appear** in JSON audits, exceptions, or log collectors.
- One session ID produces the same `session_ref` under the same audit key/version; different IDs produce different refs; rotation links previous/new refs accurately.
- Versioned HMAC key rotation allows authorized historical tracing without storing raw IDs; metric labels contain no per-user refs.
- User-Agent `"\r\nADMIN=true"`, Unicode control chars, and oversized strings are structured-encoded/sanitized and length-bounded without forging log lines.
- Pre-login unknown usernames are stored as unverified submitted refs, never attached to real `user_id` values.
- IPs are extracted from trusted reverse proxies, rejecting arbitrary client-forged `X-Forwarded-For`; geolocation carries appropriate confidence and precision.
- Idempotent consumers process duplicate `event_id` deliveries once; late timestamps do not overwrite revoked state.

### Spring Security integration tests

| Scenario | What to verify |
| --- | --- |
| Wrong username/password | `AUTH_PROVIDER_FAILED` with restricted reason, no authenticated session |
| Right password with MFA still pending | Provider success may appear; **no** full session event |
| MFA completed and SecurityContext persisted | `SESSION_AUTHENTICATED` with accurate user, factor, and `sessionRef` |
| Form login rotates session ID | `SESSION_ID_ROTATED` with old/new refs, no raw cookie |
| Browser opens second tab | Does not emit "new device/login" just for a new tab |
| Local logout | Ends local session, audits request + accurate outcome, does not promise IdP logout |
| Session timeout | Not shown as Active once backend confirms expired |
| Fourth login when `maximumSessions=3` | Handles old/new sessions per policy and registry |
| Admin/user revokes another session | New requests with old cookie rejected on every node |
| Revocation event arrives late | Does not resurrect the old session in UI projections |
| OIDC login or remember-me | Event taxonomy distinguishes mechanism without faking MFA |
| Stateless JWT | Not categorized as `HttpSession`; tracked via safe token metadata |
| Audit sink failure | Follows error policy and leaks no secrets |
| Attacker tampers with device ID/UI `publicRef` | Blocked by ownership check, never becomes a trusted session |
| Custom Spring `ProviderManager` | Publisher wired properly, no missing or duplicated events |

For Servlet, use `MockMvc` and session/cookie test requests as needed; test `HttpSessionEventPublisher` with a container/embedded server if `MockMvc` does not simulate full lifecycle behavior. For WebFlux, use `WebTestClient`, `ReactiveSecurityContextHolder`, and a reactive session registry; do not assume Servlet listeners apply.

### Operational and security tests

- Test logins from new browsers, cleared cookies, User-Agent updates, NAT/VPN, and imprecise geolocation: alerts must not cause excessive false blocks.
- Test two pods with shared Redis/DB session store: active session lists match and revocations enforce across every pod.
- Test logout followed by requests with the old cookie alongside in-flight requests to verify SLAs and check points.
- Test slow audit backend, full queues, at-least-once duplicates, and out-of-order events.
- Test retention/purge, approved legal holds, RBAC audit queries, and read/export auditing.
- Load-test login failures from multiple sources: logging must not exhaust CPU, threads, memory, or send email floods.
- Test that users can view their own history while blocked from viewing other users' histories/sessions (anti-IDOR).
- When sending "unfamiliar login" alerts, verify links contain no session tokens, do not redirect off-domain, and are rate-limited.

## 18. Common implementation mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Recording `AuthenticationSuccessEvent` as "login completed" | Wrong for MFA/Basic/custom authentication | Build boundary-based event taxonomy; emit `session authenticated` after commit |
| Logging `Authentication.toString()` or all request headers | Can expose passwords/tokens/user details | Allowlist fields and redact at the source |
| Logging raw `HttpSession.getId()`/cookies | Audit leaks turn into session hijacking | Use HMAC `sessionRef`/surrogates and protect the audit key |
| Treating User-Agent/IP as a unique trusted device | Easily spoofed, false positives, inaccurate tracking | Separate device observations from verified enrollment |
| Treating every tab as a session/device | Wrong UI when tabs share browser cookies | Rely on session store, not tab counting |
| Logout deletes audit rows without invalidating session | Cookie remains usable | Revoke authoritative session and verify |
| Treating local `SessionRegistryImpl` as cluster-wide | Misses sessions on other pods | Use shared store/registry and end-to-end tests |
| Assuming `expireNow()` cancels in-flight requests instantly | May only take effect on the next request | Define SLA and close streams if required |
| Treating JWTs like `HttpSession` | Broken revocation reporting | Separate token lifecycle and design token revocation |
| Synchronous events calling slow SIEM | Login latency and DoS when collector lags | Durable queue/outbox with bounded backpressure |
| At-least-once broker without deduplication | One login appears multiple times | Event ID idempotency and distinct event types |
| Ordering events solely by timestamp | Clock skew/out-of-order corrupts state | Use causation/sequence and authoritative state |
| Using raw emails/IPs in metric labels | Cardinality explosion and PII leaks | Aggregate metrics; keep details in RBAC-protected audit store |
| Allowing support to view/revoke any session | Privilege abuse and privacy violation | RBAC, ownership checks, reauth, and action auditing |
| Sending email on every failed login | Attackers cause notification bombing | Rate-limit/aggregate and apply thresholds |
| UI claims "online" from last-seen alone | Misleading status | Display last active timestamp |
| Presenting IP geolocation as exact street address | Misleading and excessive data collection | Show approximate region and confidence |
| Skipping OIDC/remember-me/MFA paths | Unaudited authentication paths | Inventory all authentication entry points |

## 19. Production checklist

**Data design and privacy**

- [ ] Define separate event types for authentication attempts, factors, sessions, devices, revocations, and alerts.
- [ ] Versioned audit schema with unique `event_id`, UTC `occurred_at`/`recorded_at`, `actor_ref`, `outcome`, correlation, and causation.
- [ ] Never log plaintext passwords/OTPs/tokens/cookies/CSRF/raw session IDs; include redaction and log-injection tests.
- [ ] Use HMAC/surrogate session correlation with sufficient entropy and a dedicated protected key separate from auth tokens.
- [ ] Label device observations explicitly as **risk signals**, not authentication substitutes; enforce privacy, retention, and access controls.

**Spring Security and storage**

- [ ] Configure `AuthenticationEventPublisher` on the right `ProviderManager` without duplicate or missing events.
- [ ] Separate provider success from login completion and MFA verification.
- [ ] Persist `SecurityContext` properly in custom auth; link session ID rotations safely.
- [ ] Test `HttpSessionEventPublisher`, session registry, and concurrency policy; use shared authoritative stores across multi-node clusters.
- [ ] Distinguish logout/timeout/revocation event sources and verify post-revocation requests are rejected.
- [ ] Track stateless JWTs/refresh tokens/mobile sessions with matching models rather than relying solely on the web session registry.

**Operations and UI**

- [ ] Keep UI login history, active sessions, and remembered devices as three distinct lists.
- [ ] Verify ownership server-side for all view/revoke actions; require RBAC and MFA/fresh auth for high-risk admin actions.
- [ ] Configure anomaly detection with confidence levels to avoid false lockouts on NAT/VPN/cookie changes.
- [ ] Implement durable queues/outboxes or clear failure policies for security audits, idempotency, and ordering.
- [ ] Maintain low-cardinality metrics, access auditing, retention/purges, and alerts for pipeline data loss.
- [ ] Test two-node clusters, multi-tab browsers, session fixation, pending MFA logins, logout, revocation, audit backlogs, and email bombing.

**Conclusion:** Login audit logs are useful when they accurately answer **who (after verification), which mechanism, when, from where with what confidence, which session was issued, and when it ended**. Devices are managed/observed concepts with varying levels of evidence; sessions are credentials with their own lifecycles; authentication success is a technical step rather than always a completed login. Clear event semantics, secret-free HMAC correlation, durable session registries, privacy controls, and end-to-end testing form the foundation for incident investigation and safe user session management.

## Official references

- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SessionRegistry and Session Events API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/package-summary.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)
- [Java 17 — Mac API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html)
- [Java 17 — Instant API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
