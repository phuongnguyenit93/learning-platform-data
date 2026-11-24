# Audit Logs Must Balance Traceability with Personal Data Protection

## 1. Audit Logs Are Evidence of Activity, Not a Data Mirror

In a Spring Security application, an **audit log (audit trail)** helps answer critical post-incident questions:

- **Who** attempted to log in, was authenticated, was denied access, or read/modified a resource?
- **Which action** was requested and **on which resource type**?
- **When**, in **which system**, with **what outcome**, and **under which rule**?
- Can events be correlated to a request, transaction, or permission change during investigation?

However, if you log raw requests and responses verbatim, each log line can capture passwords, access tokens, session cookies, emails, phone numbers, addresses, profile records, business data, or health information. Logs then become a **secondary data-leak source**, often harder to govern than the primary database because they are replicated across multiple collectors and monitoring systems.

Design principle: **record enough events to trace security decisions, while retaining only attributes necessary for auditing**. Logs must be protected by data policies, access controls, and appropriate retention periods.

For example, when a user is denied access to read document `doc-42`, a useful audit record looks like:

```json
{
  "eventType": "DOCUMENT_READ",
  "occurredAt": "2026-11-05T02:15:30Z",
  "actorRef": "actor-8f23",
  "resourceType": "DOCUMENT",
  "resourceRef": "doc-42",
  "action": "READ",
  "outcome": "DENIED",
  "reasonCode": "NOT_VISIBLE",
  "requestId": "e6baf6f7-780a-4a60-9469-c914cf5a8ed1"
}
```

The record **does not need** passwords, Bearer tokens, Cookies, full document contents, or complete user profiles. The values above only illustrate the format; in practice, timestamps and request IDs must be generated when events occur rather than hardcoded.

### Distinguishing Audit Logs, Application Logs, and Access Logs

| Log type | Primary goal | Examples |
| --- | --- | --- |
| **Audit log** | Establish activities and decisions involving permissions/data | Who changed roles, who was denied opening a document, whether sensitive actions succeeded or failed |
| **Application log** | Diagnose program flow and operational faults | Service startup, connection failures, timeouts, exceptions |
| **Access log** | Track calls at gateways/web servers | HTTP method, safely sanitized path, status, latency |
| **Security alert** | Warn based on aggregated signals | Repeated failed logins, abnormal spikes in blocked requests |

These log types may share a collection platform, yet **should not share the same default fields, read permissions, or retention periods**. Audit logs require consistency and traceability; access logs are high-volume and prone to containing sensitive URLs/queries; debug logs may need to be disabled or tightly restricted in production.

## 2. Designing Event Schemas: Answer Questions Without Extra Data

A sound audit schema clearly defines the **purpose** of each field before implementation.

| Field | Purpose | Data-protection note |
| --- | --- | --- |
| `eventId` | Deduplication, transport reconciliation | Stable random ID for the event; contains no identity |
| `occurredAt` | Chronological ordering, investigation | UTC timestamp with synchronized clocks; separate occurrence vs. ingestion time if needed |
| `eventType` / `action` | Categorize activity | Fixed catalog such as `AUTHN_FAILURE`, `DOCUMENT_READ`, `ROLE_CHANGED` |
| `actorRef` | Correlate actions by an authenticated identity | Use opaque internal IDs or controlled pseudonyms; limit real names/emails |
| `subjectRef` / `resourceRef` | Identify the affected object | Store only necessary identifiers; encrypt/pseudonymize if the ID itself is sensitive |
| `resourceType` | Identify resource kind | Fixed type codes instead of storing bodies |
| `outcome` | Show success, denial, or error | Distinguish `ALLOWED`, `DENIED`, `ERROR`; never conflate them |
| `reasonCode` | Explain which rule produced the outcome | Stable code like `OWNER_MISMATCH`; avoid sensitive policy expressions or exception text |
| `requestId` / `traceId` | Link events within a single request | Should be generated/verified by trusted systems; never treat client-supplied IDs as proof |
| `service` / `environment` | Scope where the event originated | Never embed server secrets or sensitive config details |
| `policyVersion` | Explain decisions against the active policy at the time | Useful when policies or approval workflows evolve |

Not every event needs every field. For example, a **failed login** has not proved who sent it: never record a verified `actorRef` simply because the sender typed someone else's username. You can record `actorRef=unverified` and `reasonCode=INVALID_CREDENTIALS`; if attack analysis needs to track targeted accounts, store a **protected target-account reference** under a separate policy instead of treating it as the actor.

### Distinguishing Verified Identity from Client-Asserted Data

Suppose a request carries:

```http
POST /login
Content-Type: application/x-www-form-urlencoded

username=alice&password=incorrect-value
```

Recording `AUTHN_FAILURE actorRef=alice` is an **unsubstantiated claim**: the sender could be anyone guessing Alice's password. A failed authentication event proves only that **an attempt** with certain credentials was rejected—not who tried it.

Conversely, after authentication succeeds, the `Authentication` established by a trusted auth system can be mapped to an internal user ID. Even then, **being authenticated does not mean being authorized on every resource**: audits should also record object-access decisions where relevant.

### Never Treat Client-Supplied `requestId` as Proof

An `X-Request-Id` header from the Internet can be forged or duplicated. To use a gateway header, the gateway must generate/validate/normalize it and strip forged client values before forwarding to the backend. In simpler setups, the server generates a fresh UUID per request. `requestId` helps **correlate traces**, not prove user identity.

## 3. What Must Never Enter Ordinary Audit Logs

**Never log verbatim** the following fields, even when convenient for debugging:

- Passwords, OTP codes, recovery codes, security answers, API keys, private keys, OAuth client secrets.
- Bearer tokens, full JWT strings, refresh tokens, HTTP Basic headers, session IDs, CSRF tokens, session cookies, full `Authorization`/`Cookie` headers.
- Entire request bodies, response bodies, uploaded files, document contents, or business records just "to ease investigation".
- Personal data irrelevant to audit goals: emails/phones/addresses/government IDs, medical records, payment details.
- Error strings or stack traces combined with uncontrolled client input; they may contain credentials, SQL parameters, and PII.
- Full URLs when queries/paths contain tokens, emails, or sensitive data. Log normalized endpoint templates such as `/api/documents/{id}` rather than `request.getRequestURL()` plus `getQueryString()`.

Counter-example:

```java
// WRONG: may log tokens and sensitive information.
log.info("Headers: {}", request.getHeaderNames());
log.info("Authorization: {}", request.getHeader("Authorization"));
log.info("Body: {}", rawRequestBody);
log.info("User sent id: {}", request.getParameter("userId"));
```

The snippet above illustrates behavior to avoid; never put it in real processing paths. **Masking a few characters** of a token or password is not inherently safe: remaining substrings can still correlate accounts or aid secret recovery depending on token structure.

Instead, build a **field allowlist** per event type. Never pass raw `HttpServletRequest`, `Authentication`, `UserDetails`, or entities to auto-serializing loggers: those objects may gain sensitive fields in future versions.

### Pseudonymization Is Not Anonymization

An `actorRef` mapped from a user ID to a pseudonym reduces exposure of real names, yet it **remains linkable personal data** if systems can reverse-lookup or correlate events. Therefore:

- Keep actor-ID-to-real-user mapping tables in a separate store with restricted lookup permissions.
- If using HMAC over user IDs for stable pseudonyms, protect keys in a secret store and plan key scoping and rotation lifecycles.
- Never treat unkeyed `SHA-256(email)` as reliable anonymization: emails can be guessed and dictionary-attacked.
- When per-user correlation is unnecessary, store aggregated counts or omit `actorRef`.

**Standalone illustrative algorithm**—never hardcode keys. Java 17 can compute HMAC-SHA-256 as follows:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class AuditPseudonym {
    private AuditPseudonym() {}

    public static String hmacId(String userId, byte[] secretKey)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secretKey, "HmacSHA256"));
        byte[] value = mac.doFinal(
            userId.getBytes(StandardCharsets.UTF_8)
        );
        return HexFormat.of().formatHex(value);
    }
}
```

This is a **standalone Java class** if placed in `AuditPseudonym.java`; it requires a strong secret key supplied by secret management. Adding HMAC is only one part of a pseudonymization strategy and does not by itself govern log access permissions, retention, or data-protection obligations.

## 4. Auditing in Spring Security: Recording at the Right Points with the Right Semantics

In a Servlet-based Spring Boot 3.x / Spring Security 6.x application, audit-relevant signals appear across several layers:

| Event source | What can it know? | Caveats |
| --- | --- | --- |
| `AuthenticationSuccessEvent` | An authentication mechanism completed successfully | With stateless HTTP Basic, may fire on **every request**, not necessarily once per "login" |
| `AbstractAuthenticationFailureEvent` | An authentication attempt failed | Submitted principal is **unverified**; never log credentials |
| `AuthorizationManager` / `AuthorizationDeniedEvent` when configured | Security-layer authorization decisions | Not every app publishes all authorization events automatically; verify actual setup |
| Business service | Reads, ownership changes, exports, role updates, state transitions | Has business context that HTTP filters lack |
| Controller/gateway | Request ID, endpoint, status, timing | May not know authorization reasons or whether a transaction committed |

**Never equate every HTTP 200 with a successful data mutation**: a service might modify zero rows; a transaction might roll back after logging "success"; a background workflow might finish after the initial request. Critical business audits should reflect the **confirmed outcome** of the action. If audit persistence must commit atomically with data updates, use an audit table in the same transaction or a **transactional outbox** before shipping events to the audit store; exact design depends on consistency and failure requirements.

Likewise, never write a single `OncePerRequestFilter` and assume it covers all security decisions: filters do not necessarily know resource owners, service-level business rules, or final outcomes of asynchronous transactions.

### Authentication Events and Business Events Differ

**Authentication success** means credentials were valid. It does not mean the user could read a particular document. Auditing document reads should originate where **which document** and **which permission check** occurred are known. Conversely, logging inside a controller misses requests rejected earlier by filters; comprehensive 401/403 tracking requires observing security handlers or event publishers as well.

## 5. Runnable Spring Boot Example: Selective Auditing

We will build a small API with two accounts:

- Alice owns document `doc-a`.
- Bob owns document `doc-b`.

Learning objective: when someone attempts to view a document, log **event, actorRef, resourceRef, outcome, reasonCode, requestId** without logging passwords, document contents, or auth headers. HTTP Basic authentication emits success/failure events; the controller records an audit entry when deciding access on the document.

**Stack:** Java 17+, Spring Boot 3.x, Spring Security 6.x Servlet. Generate a Gradle project via Spring Initializr with **Spring Web** and **Spring Security**. Place the code below into:

```text
src/main/java/demo/audit/SafeAuditApplication.java
```

This is a **complete Spring Boot program inside a project with the dependencies above**; it cannot be compiled with plain `javac SafeAuditApplication.java` without Spring libraries. Accounts, data, and logging are for local practice, not a production audit storage architecture.

```java
package demo.audit;

import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SafeAuditApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeAuditApplication.class, args);
    }

    // Internal information; do not serialize directly to JSON.
    public record StoredDocument(
        String id,
        String ownerUsername,
        String content
    ) {}

    // DTO containing only information permitted to be returned.
    public record DocumentView(String id, String content) {}

    static final class DocumentStore {
        private final Map<String, StoredDocument> documents = Map.of(
            "doc-a",
            new StoredDocument(
                "doc-a", "alice", "Alice's content"
            ),
            "doc-b",
            new StoredDocument(
                "doc-b", "bob", "Bob's content"
            )
        );

        StoredDocument find(String id) {
            return documents.get(id);
        }
    }

    @Bean
    DocumentStore documentStore() {
        return new DocumentStore();
    }

    // Demo maps authenticated identity -> opaque reference.
    // Production: fetch internal actor ID or pseudonym from
    // a trusted store; never put usernames/emails in logs.
    static final class AuditTrail {
        private static final Logger LOG =
            LoggerFactory.getLogger(AuditTrail.class);

        private final Map<String, String> actorRefs = Map.of(
            "alice", "actor-1001",
            "bob", "actor-1002"
        );

        String actorRef(Authentication authentication) {
            if (authentication == null
                    || !authentication.isAuthenticated()) {
                return "unverified";
            }
            return actorRefs.getOrDefault(
                authentication.getName(), "actor-unmapped"
            );
        }

        void record(
                String event,
                String actorRef,
                String resourceRef,
                String outcome,
                String reasonCode,
                String requestId) {

            // Log only intentional fields; never stringify
            // Authentication, HttpServletRequest, or entities.
            LOG.info(
                "audit event={} actor_ref={} resource_ref={} "
                    + "outcome={} reason_code={} request_id={}",
                event, actorRef, resourceRef,
                outcome, reasonCode, requestId
            );
        }

        @EventListener
        void authenticationSucceeded(AuthenticationSuccessEvent event) {
            record(
                "AUTHN_SUCCESS",
                actorRef(event.getAuthentication()),
                "none",
                "ALLOWED",
                "CREDENTIAL_ACCEPTED",
                "unavailable"
            );
        }

        @EventListener
        void authenticationFailed(AbstractAuthenticationFailureEvent event) {
            // Do not read unverified username or credentials
            // from event.getAuthentication().
            record(
                "AUTHN_FAILURE",
                "unverified",
                "none",
                "DENIED",
                "AUTHN_FAILED",
                "unavailable"
            );
        }
    }

    @Bean
    AuditTrail auditTrail() {
        return new AuditTrail();
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher publisher) {
        // Enable publishing standard authentication events
        // from AuthenticationManager/ProviderManager.
        return new DefaultAuthenticationEventPublisher(publisher);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/documents/**"
                ).authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @RestController
    static final class DocumentController {
        private final DocumentStore documents;
        private final AuditTrail audit;

        DocumentController(DocumentStore documents, AuditTrail audit) {
            this.documents = documents;
            this.audit = audit;
        }

        @GetMapping("/api/documents/{documentId}")
        ResponseEntity<?> readDocument(
                @PathVariable String documentId,
                Authentication authentication) {

            // Server-generated ID: never trust a client-supplied value.
            String requestId = UUID.randomUUID().toString();
            String actorRef = audit.actorRef(authentication);
            StoredDocument document = documents.find(documentId);

            boolean allowed = authentication != null
                && authentication.isAuthenticated()
                && document != null
                && document.ownerUsername().equals(
                    authentication.getName()
                );

            if (!allowed) {
                // Do not log raw documentId when no trusted record
                // is found. Do not distinguish nonexistent IDs
                // from IDs the caller is not permitted to view.
                String resourceRef =
                    document == null ? "unknown" : document.id();

                audit.record(
                    "DOCUMENT_READ",
                    actorRef,
                    resourceRef,
                    "DENIED",
                    "NOT_VISIBLE",
                    requestId
                );

                return ResponseEntity
                    .status(HttpStatus.NOT_FOUND)
                    .header("X-Request-Id", requestId)
                    .build();
            }

            audit.record(
                "DOCUMENT_READ",
                actorRef,
                document.id(),
                "ALLOWED",
                "OWNER_MATCH",
                requestId
            );

            return ResponseEntity
                .ok()
                .header("X-Request-Id", requestId)
                .body(new DocumentView(
                    document.id(), document.content()
                ));
        }
    }
}
```

### Explaining the Example's Security Boundaries

**`AuditTrail.record(...)` uses a field allowlist.** All `event`, `outcome`, and `reasonCode` values are generated in code from intentional fixed sets. `actorRef` comes from a server-side mapping of the Spring Security-authenticated identity. `resourceRef` comes from a trusted record when present; guessed client IDs are never logged verbatim when no record exists. `requestId` is generated as a UUID on the server inside the controller. Bodies, passwords, Authorization headers, Cookies, and exception messages are never logged.

**`AuthenticationEventPublisher` supplies authentication events.** `DefaultAuthenticationEventPublisher` translates matching authentication outcomes into Spring events. `authenticationSucceeded(...)` uses the verified principal; `authenticationFailed(...)` **does not** log the username the client entered, because the sender did not prove ownership of that username. Whether a specific event is emitted also depends on the authentication provider and exception type; never assume every external integration emits identical failure events.

**With stateless HTTP Basic, `AUTHN_SUCCESS` may fire on consecutive requests by the same account.** It is a **per-request authentication success event**, not necessarily "the user started a new login session". Counting it as "login count" skews metrics. Form login/sessions carry different semantics. Define event units clearly before building security reports.

**`DOCUMENT_READ` is recorded where ownership is checked.** The controller accepts `documentId`, yet the actor never comes from client URLs or JSON. Even when Alice sends valid Basic credentials, reading `doc-b` is blocked and logged as `DENIED`. For both nonexistent and forbidden records, the API returns **404** to limit existence disclosure; this is a demo choice, not a rule that every API must prefer 404 over 403.

**`requestId` in this example is created only when the controller runs.** Hence `AUTHN_SUCCESS`/`AUTHN_FAILURE` events emitted from filters carry `request_id=unavailable` and are not yet linked to the controller request ID. In real products, correlating from gateway to Security filters to business events requires initializing a correlation ID at the **start of the request**, generated/normalized by a trusted component and cleared after the request. Do not claim this short sample has end-to-end tracing.

**SLF4J logs are an illustration tool**, lacking tamper-evident storage, viewer access control, encryption, retention, time standardization, and durable delivery. Those must be designed for production. Audit consistency with transactions must also be ensured separately; logging "ALLOWED" before the actual write does not mean the data committed.

### Running the Project and Trying Scenarios

Inside the project directory with the Gradle Wrapper:

```bash
./gradlew bootRun
# Windows PowerShell:
# .\gradlew.bat bootRun
```

In another terminal, issue HTTP GET requests:

```bash
# 1. Unauthenticated: handled at Security filter, typically 401.
curl -i http://localhost:8080/api/documents/doc-a

# 2. Wrong password: authentication rejected.
curl -i -u alice:wrong http://localhost:8080/api/documents/doc-a

# 3. Alice reads her own document: 200.
curl -i -u alice:alice123 http://localhost:8080/api/documents/doc-a

# 4. Alice tries reading Bob's document: 404 per demo policy.
curl -i -u alice:alice123 http://localhost:8080/api/documents/doc-b

# 5. Bob reads his own document: 200.
curl -i -u bob:bob123 http://localhost:8080/api/documents/doc-b
```

In PowerShell, if `curl` aliases `Invoke-WebRequest`, use `curl.exe`. Never use demo credentials on public systems. HTTP Basic is safe only when protected by HTTPS on real networks, as Base64 is not encryption.

Outcomes to verify:

| Scenario | HTTP status | Expected audit |
| --- | --- | --- |
| No Basic credentials | 401 | May not emit `AUTHN_FAILURE`; this is an **unauthenticated** request, distinct from bad credentials |
| Wrong Basic credentials | 401 | `AUTHN_FAILURE` if AuthenticationEventPublisher/provider emits matching event |
| Alice reads `doc-a` | 200 | `AUTHN_SUCCESS` and `DOCUMENT_READ ALLOWED` |
| Alice reads `doc-b` | 404 | `AUTHN_SUCCESS` and `DOCUMENT_READ DENIED` |
| Bob reads `doc-b` | 200 | `AUTHN_SUCCESS` and `DOCUMENT_READ ALLOWED` |

Example **shape** of audit lines in the console (ordering, timestamps, and request IDs vary per run; logging framework prefixes omitted):

```text
audit event=AUTHN_FAILURE actor_ref=unverified resource_ref=none outcome=DENIED reason_code=AUTHN_FAILED request_id=unavailable
audit event=AUTHN_SUCCESS actor_ref=actor-1001 resource_ref=none outcome=ALLOWED reason_code=CREDENTIAL_ACCEPTED request_id=unavailable
audit event=DOCUMENT_READ actor_ref=actor-1001 resource_ref=doc-a outcome=ALLOWED reason_code=OWNER_MATCH request_id=<server-generated-request-id>
audit event=DOCUMENT_READ actor_ref=actor-1001 resource_ref=doc-b outcome=DENIED reason_code=NOT_VISIBLE request_id=<server-generated-request-id>
```

The lines above show only **event types and logged fields**; never treat them as fixed stdout for a run. When testing audits, assert event categories, outcomes, reason codes, and the presence of generated IDs rather than exact timestamps or UUIDs.

## 6. Where to Collect Events for Just-Enough Traceability

A well-audited system needs an **event emission map**. No single listener always knows everything:

1. **Authentication layer:** log auth successes/failures with the semantics of each mechanism (form login, Basic, token refresh, OAuth2/OIDC, MFA, etc.).
2. **Authorization layer:** log meaningful denials. A request can be rejected by `AuthorizationFilter`, `@PreAuthorize`, CSRF filters, policy engines, or business services; pick emission points to avoid dropping or duplicating events.
3. **Business services:** log auditable actions such as viewing/exporting sensitive data, modifying roles, transferring ownership, approving transactions, or deleting/restoring records. Events must reflect final outcomes, not merely "controller invoked".
4. **Background workers:** may run without an HTTP request. Log **service/job identity** and validly propagated initiator context rather than reading a finished request's ThreadLocal.
5. **Gateways/proxies:** supply correlation IDs, endpoints, and operational signals; never assume they know data-layer ownership.

If every layer emits `AUTHN_FAILURE` for one call, counts are double-counted. Define **clear event owners**: e.g., AUTHN from the auth subsystem, DOCUMENT_READ from the document service, ROLE_CHANGED from the authorization service. When multiple components can emit duplicates, use `eventId` or idempotency keys for deduplication.

### Logging Failures and Successes Differently

- **A blocked action:** log timestamp, action type, verified actor if available, normalized resource or pseudonym, outcome `DENIED`, and a safe reason code. Avoid revealing detailed policy conditions to clients.
- **A successful read:** if sensitive and auditing is required, log "who read which document category", never copying the document itself into logs.
- **A successful write:** log changes at the necessary level such as update type, actor, resource, and commit outcome. Avoid dumping full "before–after" snapshots of sensitive fields into broadly accessible logs.
- **A system error:** log outcome `ERROR` and error codes; put stack traces in separate data-controlled application logs. Never turn a transport failure into `DENIED` just to reduce event types.

## 7. Protecting Audit Logs After They Are Written

**Logging minimal data is step one; the log store itself must still be protected like critical data.**

### 7.1. Read Permissions and Separation of Duties

Developers, operators, customer support, and auditors do not inherently need the same read access. You can design:

- Operational dashboards showing aggregated events, reason codes, and metrics without resolving real identities.
- Investigators granted time-bound, justified access to resolve `actorRef` to real identities via controlled procedures with their own access log.
- Application accounts permitted only to **append/write** events, unable to modify or delete existing entries.
- Business DB administrators not automatically granted permission to alter audit history.

Also log **who accessed the audit store and why**, preventing the audit system from becoming an unchecked personal surveillance tool.

### 7.2. Protecting Transit and Storage

Use authenticated, encrypted transport from services to log collectors; enable encryption at rest where appropriate; manage keys, rotation, and backups under separate policies. Never place logging-pipeline secrets in public configs or the logs themselves. For audit data needing strong integrity, consider append-only storage, WORM/immutable retention, hash chains/HMAC signatures, or immutable ledgers with independent verification. **A self-computed checksum column stored next to a row where an admin can edit both does not prove nobody tampered with the log.**

Synchronize server clocks (UTC/NTP) and record ingestion timestamps when distributed systems need latency analysis. Correlation IDs tie traces together, yet multi-service investigations also require checking clock reliability, delayed logs, and delivery retries.

### 7.3. Retention and Data Deletion

Do not apply "keep audit logs forever" universally. Determine usage goals, investigation windows, legal/contractual obligations, and applicable regulations to set **different retention periods per event type**. For example, operational logs may have shorter lifecycles than privileged role-change events; that is an organizational policy decision, not a single universal day count.

Manage copies across collectors, data lakes, search indexes, backups, and alert systems too. A deletion schedule on the primary table **does not mean** data is gone from all replicas. When handling requests to restrict or erase personal data, evaluate evidence-retention duties and legal bases rather than deleting blindly or refusing every request.

### 7.4. Reducing Log Injection Risk

When logging client-supplied values such as usernames, paths, or user agents, strings may contain newlines or control characters to forge fake log lines. Proper defenses are **omitting unnecessary values**, normalizing inputs, and using structured logging/encoders with proper escaping. For fields that must be logged, bound length, characters, and schema format before sending to sinks. Never concatenate arbitrary strings into log templates when controlled structured fields can be used.

## 8. Auditing Multi-Tenant Applications and Sensitive-Data Systems

An actor may belong to multiple tenants or act under delegation. Then `actorRef` alone cannot explain a decision; you may need `tenantRef`, `actingOnBehalfOfRef`, `policyVersion`, or `delegationRef`—only when genuinely needed for auditing and derived from trusted sources.

Example: a tenant A admin accesses a tenant B resource:

```json
{
  "eventType": "DOCUMENT_EXPORT",
  "actorRef": "actor-1001",
  "tenantRef": "tenant-a",
  "resourceRef": "doc-tenant-b-1",
  "outcome": "DENIED",
  "reasonCode": "CROSS_TENANT_ACCESS"
}
```

The record states the **reason for denial** instead of copying user profiles or full internal conditions. If tenant IDs or document IDs are sensitive themselves, use opaque identifiers, controlled pseudonyms, or viewer-scoped masking.

Avoid two opposite mistakes:

- **Over-logging** for fast debugging, leaking personal profiles, passwords, or transaction contents.
- **Under-logging** so much that you cannot distinguish an authorized role change, an auth failure, a system fault, and an unauthorized access attempt.

The right balance comes from concrete **audit questions**. For instance, "Who granted ADMIN role and did it commit?" needs actor, target account reference, action, suitably encoded/bounded before/after roles, commit outcome, timestamp, and correlation ID—not names, emails, full request bodies, and every account field.

## 9. Testing Both Traceability and Data-Leak Risk

A strong audit test verifies **two branches simultaneously**:

1. Critical security events **are recorded with all required fields**.
2. Sensitive values **do not appear** in logs, collectors, or ordinary viewing locations.

| Scenario | Required event | Content that must NOT appear |
| --- | --- | --- |
| Wrong Basic credentials | `AUTHN_FAILURE` with unverified actor | Password, Basic header, unverified username unless governed by separate target-tracking policy |
| Alice reads her own document | `DOCUMENT_READ ALLOWED`; opaque actorRef | Passwords, full requests, tokens |
| Alice tries reading Bob's document | `DOCUMENT_READ DENIED` | Bob's document content, Bob's private info |
| Unauthenticated caller | Optional access/security "authentication required" event per design | Never attribute to an authenticated account |
| Admin changes permissions | `ROLE_CHANGED` with actor and target refs, post-commit outcome | Credentials, session tokens, unrelated personal attributes |
| Client sends query with token or email | Normalized endpoint logged if needed | Raw query string containing token/email |
| Request injects newline in header | Event keeps valid structure if field is collected | No forged log lines or exceeded length limits |
| Collector unavailable | Failure monitoring signal, queue/retry, or policy fallback | Never silently mark "durably audited" without confirmation |
| Retention-based deletion | Expired records handled per policy across replicas | No orphaned index/backup outside stated control boundaries |

With the demo app, verify `curl` and console output for 401, 200, and 404 as in section 5; then send a query `?password=secret-value` to an accessible URL. **`secret-value` must never appear in `AuditTrail` log lines**, because the code does not log URLs/queries. However, external reverse proxies or access logs **might** still record query strings if configured to do so; inspect the entire pipeline, not just Java application loggers.

Never put real tokens or real personal data in leak tests. Use recognizable dummy markers to confirm filters omit them across raw logs, structured events, collectors, dashboards, and relevant backups.

## 10. Practical Implementation Checklist

1. **Define audit questions** before picking fields: which investigation queries must be answered, and who may view results.
2. **Define the event schema** with event ID, UTC timestamp, actor/resource references, action, outcome, reason, correlation ID, and source when genuinely needed.
3. **Derive actors from trusted authentication**; never treat a username entered in a failed login as a verified caller.
4. **Derive resource attributes from the server**; never trust client-asserted owner, role, or tenant.
5. **Allowlist logged data**, forbidding credentials, tokens, sessions, cookies, and sensitive bodies/responses.
6. **Separate authentication, authorization, and business audits** to avoid omissions or double counting.
7. **Record outcomes at the right time**, accounting for transactions, retries, async jobs, and rollbacks.
8. **Control read, search, export, and edit access to logs**, protecting transit, storage, integrity, and replicas.
9. **Define retention and deletion/restriction procedures** aligned with purpose and applicable obligations.
10. **Test both required events and forbidden data**, monitoring collector failures and framework-upgrade changes.

**Key takeaway:** a good audit log is not one that stores as much data as possible. It is a **structured, purposeful, trustworthy, access-controlled chain of evidence** sufficient to explain security actions while minimizing retention of personal data and secrets.

### References

- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security API — DefaultAuthenticationEventPublisher](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/DefaultAuthenticationEventPublisher.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP User Privacy Protection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/User_Privacy_Protection_Cheat_Sheet.html)
- [OWASP API Security Top 10](https://owasp.org/API-Security/)
