# Detecting Resource Enumeration, Repeated Denials, and Scope Escalation Attempts

> **Module:** Spring Security – authorization. **Parent topic:** Events and Auditing. This lesson guides you through identifying, recording, aggregating, and verifying anomalous access-control behaviors: probing many unauthorized resources, repeated denials, and attempting operations beyond assigned roles/tenants/scopes. Examples use Java 17+, Spring Boot 3.x / Spring Security 6.x on Servlet, combining audit events, sliding-window detection rules, and JUnit 5.

## 1. Learning Objectives and Security Boundaries

After practicing, you should be able to answer:

1. **Who** made the request, at **what time**, on **which resource group**, with **what action**, whether it was **allowed or denied**, and by **which policy**?
2. How does a user accidentally calling the wrong resource once differ from a session rapidly probing dozens of IDs within a few minutes?
3. When a user in tenant A tries to read tenant B's data, or a regular account repeatedly invokes admin functions, where does the "scope boundary probing" signal come from?
4. How do you use Spring Security events without storing tokens, cookies, sensitive data, or full paths containing personal identifiers?
5. How do you avoid duplicate alerts, reduce false positives, test detectors with reproducible data, and operate across multiple application instances?

Keep two mechanisms separated by responsibility:

- **Enforcement (blocking):** Spring Security and business policies decide whether a request is permitted **at access time**. Tenant/owner/role permissions must still be enforced at HTTP and/or method/object layers.
- **Detection/Audit (observing):** events from those decisions are recorded and correlated to find suspicious patterns. A disabled detector or unavailable audit sink **must never turn a denied request into an allowed one**.

An alert only indicates a **signal worth investigating**, not proof positive that a user is attacking.

## 2. Three Behavioral Patterns to Distinguish

### 2.1. Resource Enumeration (ID Probing)

Example API:

```http
GET /api/tenants/acme/invoices/1001
GET /api/tenants/acme/invoices/1002
GET /api/tenants/acme/invoices/1003
```

An account authorized only for invoice 1001 repeatedly probes other `invoiceId` values. What matters is not just the raw count of 403s, but the **number of distinct unauthorized resources** targeted within a time window.

The signal is stronger when combined with:

- One principal or client having many **distinct resource keys** denied.
- IDs that appear sequential/monotonic or probed rapidly (detected in the internal pipeline; avoid logging raw IDs).
- Multiple objects across different tenants.
- A sharp denial-rate spike relative to the baseline of that API or user.
- A burst of resource-related 403/404s following minimal legitimate accesses.

This pattern borders on **Broken Object Level Authorization (BOLA/IDOR)**. However, **resource enumeration does not mean the system suffers from BOLA**: if policies consistently deny properly, the requests are merely suspicious activity; if an API returns 200 for someone else's data, that is an **enforcement vulnerability** which looking solely at denial events may miss.

### 2.2. Repeated Denials

An account sends 12 denied requests to `/api/admin/reports` in 3 minutes. Possible causes: privilege-escalation attempts, endpoint probing scripts, stale UI permission caches, a client calling APIs with outdated scopes, or a user whose permissions were just revoked.

**Counting total HTTP 4xx is not enough**. 400 from validation, 401 from missing authentication, 403 from authorization, and 404 from nonexistent resources carry different meanings:

| Signal | Meaning and usage |
| --- | --- |
| `AuthorizationDeniedEvent` / policy deny result | Direct source for a failed authorization decision |
| HTTP 403 | Web outcome signal; may come from filters, methods, policies, or app code; does not include full reasons by default |
| HTTP 401 | Centers on authentication/credentials; correlate with login audits rather than lumping into "missing permission" |
| HTTP 404 | Could be a nonexistent resource **or** the app hiding existence of unauthorized resources; needs policy context |
| HTTP 429 | Rate limiter throttled request frequency; does not prove prior authorization errors |
| 2xx | Request succeeded; must verify scope/owner rather than assuming every 2xx is safe |

### 2.3. Scope Escalation Attempts (Scope / Tenant / Role Boundary Probing)

Examples:

- A user in tenant `north` requests a record in tenant `south`.
- A `ROLE_USER` account attempts to invoke `/api/admin/users/{id}/disable`.
- A token carrying only `reports:read` scope is used for `reports:write`.
- An account permitted to read its own data attempts to access a colleague's data.

This signal requires **specific permission context**:

```text
actor   = server-verified principal
action  = invoices.read
scope   = tenant:north (per verified claims/DB)
target  = invoice belonging to tenant:south (per trusted DB)
result  = DENY
reason  = TENANT_SCOPE_MISMATCH
```

Never infer `TENANT_SCOPE_MISMATCH` merely because a URL contains a different tenant name or because a client sent an `X-Tenant` header. Reason codes must originate from **trusted authorization policies** after reconciling subject/tenant/owner against server data. Missing roles are classified as `PRIVILEGED_OPERATION_DENIED` or `MISSING_AUTHORITY`, clearly separated from `INVALID_CREDENTIALS`.

## 3. Architecture: From Permission Decision to Alert

```text
HTTP client
    │ request + credential
    ▼
Spring Security FilterChain
    ├─ Authentication (who is calling?)
    ├─ AuthorizationFilter / AuthorizationManager
    └─ DispatcherServlet → controller → @PreAuthorize / object-level policy
                                  │
                 ALLOW / DENY (enforcement)
                                  │
                 AuthorizationDeniedEvent (when publisher configured)
                                  │
                  Audit event collector / outbox
                                  │
                  normalize + pseudonymize identifiers + dedup
                                  │
                  event stream / protected audit store
                                  │
          sliding window + distinct resource + scope reason
                                  │
                 alert → triage → investigate → respond
```

**Critical timing:** a denial event describes a **permission decision**. The final HTTP status is chosen by the web layer and can be 401/403/404 depending on policy and error handlers. To store both, join the two signals with a **server-generated** `requestId`, and capture the status only after the response completes. Never assume `AuthorizationDeniedEvent` automatically carries the full URL, response status, or tenant reason code.

In distributed systems, a request can flow gateway → service A → service B. Use `traceId` for correlation and `eventId` for deduplication; do not count one failure logged at 3 layers as 3 separate access attempts. Audit streams may have at-least-once delivery, so events need stable IDs and consumers must deduplicate idempotently.

## 4. Designing Audit Records for Detection

A **normalized** audit record may look like:

```json
{
  "schemaVersion": 1,
  "eventType": "AUTHORIZATION_DENIED",
  "eventId": "evt-6e37f7ce",
  "occurredAt": "2026-11-05T08:12:09Z",
  "requestId": "req-c09d2",
  "traceId": "trace-a16c",
  "service": "billing-api",
  "layer": "METHOD",
  "actorKey": "hmac:9a8b...",
  "clientKey": "hmac:70d1...",
  "actorClass": "AUTHENTICATED_USER",
  "routeTemplate": "/api/tenants/{tenantId}/invoices/{invoiceId}",
  "operation": "invoice.read",
  "targetType": "invoice",
  "targetKey": "hmac:fc71...",
  "decision": "DENY",
  "policyReason": "TENANT_SCOPE_MISMATCH",
  "httpStatus": 403
}
```

This is **illustrative data**, not a payload automatically emitted by Spring Security. To get detailed `policyReason`s, the application must attach them during business-policy evaluation; to get `httpStatus`, capture it from the web outcome. When using a unified record, the pipeline must mark unknown fields explicitly rather than fabricating values.

| Field | Trusted way to obtain | Notes |
| --- | --- | --- |
| `eventId`, `requestId`, `traceId` | Server-side generation/correlation, tracing middleware | Never use a client-supplied request ID alone as a dedup key |
| `actorKey` | Subject from verified `Authentication`, pseudonymized | Never log passwords, tokens, cookies, or raw principal/email unnecessarily |
| `clientKey` | Trusted gateway identifies client, then pseudonymize | `X-Forwarded-For` is trustworthy only when proxies are properly configured |
| `routeTemplate` | Router/server-defined template, e.g., `/api/invoices/{id}` | Avoid logging raw URLs/queries with IDs or personal data |
| `operation`, `targetType` | Controlled business names | Use stable enums/names, not free-form strings from requests |
| `targetKey` | HMAC of normalized resource ID, enabling distinct counting | Avoid unkeyed hashes of guessable IDs; manage keys |
| `policyReason` | Internal policy engine/authorization code | Never infer reasons mechanically from HTTP status |
| `decision` | AuthorizationManager / policy | Record `DENY` with a clear source |
| `httpStatus` | Final response after web processing | May be absent in method/non-HTTP events |
| `occurredAt` | Server/collector UTC clock | Account for clock skew when aggregating across services |

**Audit data invariants:** timely; minimal yet sufficient for traceability; encrypted in transit/at rest; segregated audit access; retention and deletion per policy. Never log `AuthorizationDeniedEvent#getObject().toString()` directly, as the object may hold sensitive request/argument data.

### 4.1. Why Use HMAC for Resource Keys?

With plain `SHA-256("1002")`, anyone reading the logs can hash an entire range of guessable IDs and match them. HMAC with a secret key managed outside code prevents trivially reversing IDs from digests. Store enough digest length to count distinct items with acceptable collision probability; if truncating digests, evaluate collisions and security policy. Using the same key and normalization across an investigation window allows comparing repeated IDs; key rotation affects historical linking.

You do not need to send raw IDs to the detector if the policy-owning component already computes `targetKey`. Log access controls, auditing who reads logs, and tamper protection remain essential; HMAC does not replace those controls.

## 5. Collecting Events Properly from Spring Security

### 5.1. Enabling Authorization Denial Event Publishing

In modern Spring Security, add an `AuthorizationEventPublisher` bean. `SpringAuthorizationEventPublisher` uses Spring's `ApplicationEventPublisher` and defaults to **denial events**; publishing every allow event can generate heavy load.

Example **`src/main/java/example/audit/AuthzEventConfig.java`**:

```java
package example.audit;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class AuthzEventConfig {

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher applicationEvents) {
        return new SpringAuthorizationEventPublisher(applicationEvents);
    }
}
```

In applications configuring URLs via `SecurityFilterChain`, you still need **`authorizeHttpRequests`** and service authorization policies. The publisher bean does not replace rule configuration. For method security, methods must be invoked through the **Spring AOP proxy** for `@PreAuthorize` to apply; a method calling another method on the same object (`this.method()`) can bypass the proxy.

### 5.2. Listener Extracting Safe Metadata

The example **`src/main/java/example/audit/DeniedEventListener.java`** below is a compilable hook in a Spring Boot project with Spring Security/SLF4J. It logs only the **source layer** and **controlled method name** to confirm events work. It is not yet sufficient for a resource detector; enrichment is handled in the next section.

```java
package example.audit;

import org.aopalliance.intercept.MethodInvocation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DeniedEventListener {

    private static final Logger log =
            LoggerFactory.getLogger(DeniedEventListener.class);

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> event) {
        Authentication user = event.getAuthentication().get();
        String actorClass = user == null
                || user instanceof AnonymousAuthenticationToken
                || !user.isAuthenticated()
                ? "ANONYMOUS" : "AUTHENTICATED";

        Object secured = event.getObject();
        String layer;
        String operation;

        if (secured instanceof MethodInvocation invocation) {
            layer = "METHOD";
            operation = invocation.getMethod()
                    .getDeclaringClass().getSimpleName()
                    + "#" + invocation.getMethod().getName();
        } else {
            layer = "REQUEST_OR_OTHER";
            operation = "AUTHORIZATION_CHECK";
        }

        log.warn("securityEvent=AUTHORIZATION_DENIED layer={} "
                + "operation={} actorClass={}",
                layer, operation, actorClass);
    }
}
```

**What this listener does not do:** it does not distinguish user A from B, read raw method arguments, grab arbitrary URLs, identify exact tenants, or fabricate `TENANT_SCOPE_MISMATCH`. To measure resource probing, a production adapter must send **policy-enriched records** to an audit collector via an interface like `AuditSink.publish(record)`. Never automatically log `invocation.getArguments()` or `event.getObject()`.

In practice, a request may be blocked at the HTTP layer **before** reaching a method, producing no method event. Conversely, an internally authorized method denied access may have no HTTP request. Test both paths and define event sources.

### 5.3. Attaching Reason Codes from Business Policies

Example document-read policy designed with tenant/owner checks:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentView read(String documentId) {
    // Read logic runs after policy allows.
}
```

The snippet above is an **illustrative fragment**, depending on application-provided `documentPolicy` and `DocumentView` beans, not a standalone program. `canRead` must check the principal against **actual tenant/owner in the DB**, never trusting a client-supplied `tenantId`.

A policy can evaluate internal outcomes in the form:

```text
ALLOW
DENY:RESOURCE_NOT_OWNED
DENY:TENANT_SCOPE_MISMATCH
DENY:MISSING_REQUIRED_AUTHORITY
DENY:PRIVILEGED_OPERATION
```

A plain `boolean` returning `false` leaves `AuthorizationDeniedEvent` typically **without an explicit business reason**. To classify accurately, use an internal decision model `PolicyDecision(allow, reason)` and emit a domain audit event on denial, or use a controlled enrichment contract. Never guess `reason` from path names, 403s, or visible principal roles.

**Avoid double-counting:** one request can produce both a domain audit event and a framework authorization event. Use `requestId + operation + decisionStage` or an evaluation-generated `decisionId` to deduplicate. Standardize which event is the canonical source for alerts.

### 5.4. Spring Boot Actuator Auditing

Spring Boot Actuator supports `AuditEventRepository`, `AuditEvent`, and authentication/authorization audit listeners. When a repository bean is provided, the app can persist audit events in it. `InMemoryAuditEventRepository` is useful in development, but **unsuitable as a production investigative store** due to bounded capacity and data loss on restart. If exposing `/actuator/auditevents`, restrict endpoint access and response contents.

Framework auditing helps with **collection/querying**; detecting distinct resources, scope reasons, or cross-instance patterns still requires dedicated application processing. Do not assume a default `AuditEventRepository` carries `targetKey`, tenant context, request correlation, and sliding-window state.

## 6. Detection Rules: Time Windows, Counts, and Severity

To understand how a detector works, use **illustrative exercise thresholds** (not universal best-practice constants for every system):

| Rule | Condition within a 5-minute window | Suggested severity |
| --- | --- | --- |
| `REPEATED_DENIAL` | At least **6** distinct denial decisions for the same subject | Warning |
| `RESOURCE_ENUMERATION` | At least **5 distinct targetKeys** denied due to resource access | High |
| `SCOPE_BOUNDARY_PROBING` | At least **3** denials classified by policy as cross-tenant/privileged | High |
| `MULTI_ACCOUNT_SOURCE` | One `clientKey` linked to multiple denied subjects | Advanced correlation; guard against NAT false positives |
| `POST_REVOKE_ACCESS` | Repeated access attempts after a role/session revocation event | Advanced correlation; requires trusted IAM events |

**Reference examples:**

- Alice tries one wrong ID: record the event, **no alert yet**.
- Alice tries the same ID 7 times: triggers `REPEATED_DENIAL` but **not resource enumeration**.
- Alice tries 5 unauthorized IDs: triggers `RESOURCE_ENUMERATION`.
- Alice tries 3 requests to another tenant (reason from policy): triggers `SCOPE_BOUNDARY_PROBING`.
- Multiple employees behind shared NAT get 403s: a single IP does not prove a single actor, so alert per principal and combine sources.
- A legitimate client suffers a UI bug sending repeated requests: the detector may alert; operators must check deployments/UI and baselines.

Count **unique requests/decisions** using server-generated keys. If multiple events for the same request arrive from different layers, deduplicate before applying thresholds. In multi-service setups, tune thresholds across subject, source, route/operation, tenant, environment, and normal traffic profiles rather than applying one rigid limit to all users and endpoints.

## 7. Java 17: Independently Testable Sliding-Window Detector

The example below focuses on the **observation algorithm**. Input `Denial` is a normalized record containing **subjectKey**, **targetKey**, and **Reason** produced at a trusted layer; it accepts no raw HTTP requests or tokens. We use:

- The last 5 minutes as the observation window.
- 10 minutes as a cooldown avoiding re-sending **the same alert type** for a subject.
- `requestId` to prevent double-counting inside the window.
- An injected `Clock` to test time progression without `Thread.sleep`.
- `synchronized` so each instance updates internal counters consistently.

### 7.1. Detector Code

**`src/main/java/example/audit/DenialPatternDetector.java`**

```java
package example.audit;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class DenialPatternDetector {

    public enum Reason {
        RESOURCE_FORBIDDEN,
        TENANT_SCOPE_MISMATCH,
        PRIVILEGED_OPERATION_DENIED,
        OTHER_DENIAL
    }

    public enum Pattern {
        REPEATED_DENIAL,
        RESOURCE_ENUMERATION,
        SCOPE_BOUNDARY_PROBING
    }

    public record Denial(
            String requestId,
            String subjectKey,
            String targetKey,
            Reason reason) {
        public Denial {
            Objects.requireNonNull(requestId, "requestId");
            Objects.requireNonNull(subjectKey, "subjectKey");
            Objects.requireNonNull(reason, "reason");
            if (requestId.isBlank() || subjectKey.isBlank()) {
                throw new IllegalArgumentException("Missing correlation key");
            }
        }
    }

    public record Alert(Pattern pattern, String subjectKey, int count) {}

    private record Observation(Instant at, Denial denial) {}

    private static final class Bucket {
        final Deque<Observation> window = new ArrayDeque<>();
        final Map<Pattern, Instant> lastAlert =
                new EnumMap<>(Pattern.class);
    }

    private static final Duration WINDOW = Duration.ofMinutes(5);
    private static final Duration COOLDOWN = Duration.ofMinutes(10);

    private final Clock clock;
    private final Map<String, Bucket> bySubject = new HashMap<>();

    public DenialPatternDetector(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public synchronized List<Alert> accept(Denial event) {
        Objects.requireNonNull(event);
        Instant now = clock.instant();
        Bucket bucket = bySubject.computeIfAbsent(
                event.subjectKey(), ignored -> new Bucket());

        Instant oldest = now.minus(WINDOW);
        while (!bucket.window.isEmpty()
                && bucket.window.peekFirst().at().isBefore(oldest)) {
            bucket.window.removeFirst();
        }

        // A request is counted only once inside the window.
        boolean duplicate = bucket.window.stream().anyMatch(
                x -> x.denial().requestId().equals(event.requestId()));
        if (duplicate) {
            return List.of();
        }

        bucket.window.addLast(new Observation(now, event));
        int totalDenials = bucket.window.size();

        Set<String> distinctTargets = new HashSet<>();
        int scopeDenials = 0;

        for (Observation observation : bucket.window) {
            Denial denial = observation.denial();

            if (denial.targetKey() != null
                    && !denial.targetKey().isBlank()
                    && (denial.reason() == Reason.RESOURCE_FORBIDDEN
                    || denial.reason() == Reason.TENANT_SCOPE_MISMATCH)) {
                distinctTargets.add(denial.targetKey());
            }

            if (denial.reason() == Reason.TENANT_SCOPE_MISMATCH
                    || denial.reason() == Reason.PRIVILEGED_OPERATION_DENIED) {
                scopeDenials++;
            }
        }

        List<Alert> alerts = new ArrayList<>();
        emit(bucket, now, event.subjectKey(), alerts,
                Pattern.REPEATED_DENIAL, totalDenials, 6);
        emit(bucket, now, event.subjectKey(), alerts,
                Pattern.RESOURCE_ENUMERATION, distinctTargets.size(), 5);
        emit(bucket, now, event.subjectKey(), alerts,
                Pattern.SCOPE_BOUNDARY_PROBING, scopeDenials, 3);
        return List.copyOf(alerts);
    }

    private static void emit(
            Bucket bucket, Instant now, String subject,
            List<Alert> alerts, Pattern pattern,
            int current, int threshold) {

        if (current < threshold) {
            return;
        }

        Instant last = bucket.lastAlert.get(pattern);
        if (last != null && now.isBefore(last.plus(COOLDOWN))) {
            return;
        }

        bucket.lastAlert.put(pattern, now);
        alerts.add(new Alert(pattern, subject, current));
    }
}
```

This is a **single-process standalone** version: the algorithm runs against server event-receipt time rather than client-provided timestamps; out-of-order events are still ordered by arrival time. For production deployments:

- The `bySubject` map needs a TTL and subject cap so memory does not grow unbounded; this example intentionally stays simple for learning the mechanism.
- Separate instances do not share counters; use a stream processor, Redis with TTL, or an analytics store for cluster-wide detection.
- Deduplicating by `requestId` suffices for the lesson's fixture; multiple distinct legitimate decisions within one request may require `decisionId`. Finalize one counting model before implementation.
- Source IDs must be normalized; enforce length limits and allowlists for external audit fields.
- `synchronized` does not turn this into a high-throughput distributed system; production needs dedicated windows, backpressure, queues, durability, and audit retention.
- Alerts fire **when thresholds are crossed**; never automatically lock accounts solely from a single alert.

### 7.2. Unit Testing Behavioral Patterns

Example `src/test/java/example/audit/DenialPatternDetectorTest.java` using JUnit 5:

```java
package example.audit;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import org.junit.jupiter.api.Test;

import static example.audit.DenialPatternDetector.Pattern.*;
import static example.audit.DenialPatternDetector.Reason.*;
import static org.junit.jupiter.api.Assertions.*;

class DenialPatternDetectorTest {

    private DenialPatternDetector detector() {
        return new DenialPatternDetector(
                Clock.fixed(Instant.parse("2026-11-05T08:00:00Z"),
                        ZoneOffset.UTC));
    }

    private DenialPatternDetector.Denial denial(
            int request, String resource, DenialPatternDetector.Reason reason) {
        return new DenialPatternDetector.Denial(
                "request-" + request, "actor-hmac", resource, reason);
    }

    @Test
    void oneDeniedRequestIsOnlyAnEventNotAnAttackAlert() {
        var monitor = detector();
        assertTrue(monitor.accept(
                denial(1, "resource-A", RESOURCE_FORBIDDEN)).isEmpty());
    }

    @Test
    void repeatedDeniedRequestsTriggerAtSix() {
        var monitor = detector();
        for (int i = 1; i <= 5; i++) {
            assertTrue(monitor.accept(
                    denial(i, "same-resource", OTHER_DENIAL)).isEmpty());
        }
        List<DenialPatternDetector.Alert> alert =
                monitor.accept(denial(6, "same-resource", OTHER_DENIAL));

        assertEquals(1, alert.size());
        assertEquals(REPEATED_DENIAL, alert.get(0).pattern());
        assertEquals(6, alert.get(0).count());
    }

    @Test
    void fiveDistinctForbiddenResourcesTriggerEnumeration() {
        var monitor = detector();
        for (int i = 1; i <= 4; i++) {
            assertTrue(monitor.accept(
                    denial(i, "resource-" + i, RESOURCE_FORBIDDEN)).isEmpty());
        }
        var alerts = monitor.accept(
                denial(5, "resource-5", RESOURCE_FORBIDDEN));

        assertEquals(1, alerts.size());
        assertEquals(RESOURCE_ENUMERATION, alerts.get(0).pattern());
        assertEquals(5, alerts.get(0).count());
    }

    @Test
    void threeScopeViolationsTriggerScopeAlert() {
        var monitor = detector();
        for (int i = 1; i <= 2; i++) {
            assertTrue(monitor.accept(
                    denial(i, "target", TENANT_SCOPE_MISMATCH)).isEmpty());
        }
        var alerts = monitor.accept(
                denial(3, "target", TENANT_SCOPE_MISMATCH));

        assertEquals(1, alerts.size());
        assertEquals(SCOPE_BOUNDARY_PROBING, alerts.get(0).pattern());
        assertEquals(3, alerts.get(0).count());
    }

    @Test
    void sameRequestIsDeduplicated() {
        var monitor = detector();
        var first = denial(7, "resource-7", RESOURCE_FORBIDDEN);

        assertTrue(monitor.accept(first).isEmpty());
        assertTrue(monitor.accept(first).isEmpty());
        for (int i = 1; i <= 3; i++) {
            assertTrue(monitor.accept(
                    denial(i, "resource-" + i, RESOURCE_FORBIDDEN)).isEmpty());
        }
        // 4 unique requests, not yet 5 resources.
    }

    @Test
    void cooldownStopsIdenticalAlertFlood() {
        var monitor = detector();
        for (int i = 1; i <= 5; i++) {
            monitor.accept(denial(i, "same", OTHER_DENIAL));
        }
        assertEquals(1, monitor.accept(
                denial(6, "same", OTHER_DENIAL)).size());
        assertTrue(monitor.accept(
                denial(7, "same", OTHER_DENIAL)).isEmpty());
    }
}
```

Run in a Spring Boot Maven project with `spring-boot-starter-test`:

```bash
./mvnw test -Dtest=DenialPatternDetectorTest
```

**Expected result:** 6 tests pass without requiring DB/WebSocket connections. This tests the algorithm, **not** that Spring Security emits events properly or that a production audit sink works. Add integration tests as well.

### 7.3. Testing the Time Window

An easily missed detail: after 5 minutes with no new denials, older events must expire so denial counters do not grow forever. Tests should supply a mutable `Clock` (e.g., a `Clock` subclass storing `Instant` in an `AtomicReference`), send 5 denials initially, advance 6 minutes, send one more denial, and assert threshold 6 is **not** reached. After 10 minutes from the last alert, a new alert can fire if a later window qualifies. Never use `Thread.sleep` to test time because it is slow and flaky.

## 8. Practical Integration from Authorization Policy to Detector

Example business policy that must return "not permitted to read invoice" while maintaining security enforcement:

```java
@PreAuthorize("@invoicePolicy.canRead(authentication, #invoiceId)")
public InvoiceView readInvoice(String invoiceId) {
    return invoiceRepository.loadView(invoiceId);
}
```

This is **illustrative integration code**, requiring the project's `invoicePolicy` bean and `InvoiceView`/`invoiceRepository` types to run. Inside the policy:

1. Determine the actor's tenant and authorities from the authenticated security context.
2. Look up the invoice by ID from a trusted source to identify owner/tenant.
3. Make the allow/deny decision.
4. On deny, record a controlled `reason` and HMACed `targetKey`; emit a domain audit event carrying `decisionId` or pass it to the collector.
5. Return the deny result to Spring Security; never replace deny with allow just to "make auditing easier".

Another approach uses the framework's `AuthorizationDeniedEvent` and enriches it from request/method metadata. However, generic events are not guaranteed to carry business reasons or target keys; when details are missing, classify as `OTHER_DENIAL` and **do not** trigger tenant-based rules unless actually known.

### 8.1. When Authorization Spans Multiple Layers

A request might encounter:

```text
HTTP AuthorizationFilter: ALLOW (session exists)
Method @PreAuthorize: DENY (lacks invoice:read authority)
Object policy: not run
HTTP response: 403
```

Log the decision at the true source method and count **one denied request**. If the HTTP layer denies first, the method never runs, so missing object/tenant keys are normal. Do not emit two alerts merely because both a filter and a global exception handler log a 403. Use `requestId` + `decisionStage`/`decisionId` and agree on the canonical source.

An API supporting multiple protocols (REST, GraphQL, WebSocket STOMP) cannot rely solely on HTTP 403. For instance, a denied STOMP `SUBSCRIBE` may close the connection or send an ERROR frame; authorization denial events and subscription metadata are the right signals. Define a protocol-aware taxonomy instead of cramming everything into `httpStatus`.

### 8.2. Need an Independent Signal for Unauthorized Successful Access

If an endpoint **lacks an authorization check**, it can return 200 with **no denial event** even though data leaked. Therefore:

- Test object-level permissions with two users/tenants across both allow and deny cases.
- Verify `denyAll` fallback rules for undeclared URLs.
- Maintain separate audits for high-risk permitted actions: bulk exports, role changes, tenant switches, admin usage, and sensitive document downloads.
- Reconcile policy/owner-annotated data-access logs with application decisions; never rely on denial detectors as your sole BOLA check.

## 9. Computing Alerts on Event Stores and Metrics

An illustrative PostgreSQL query once the pipeline has normalized, deduplicated, and loaded events into `authorization_audit`:

```sql
SELECT
    actor_key,
    COUNT(*) AS denied_requests,
    COUNT(DISTINCT target_key) FILTER (
        WHERE policy_reason IN (
            'RESOURCE_FORBIDDEN',
            'TENANT_SCOPE_MISMATCH'
        )
    ) AS distinct_forbidden_targets,
    COUNT(*) FILTER (
        WHERE policy_reason IN (
            'TENANT_SCOPE_MISMATCH',
            'PRIVILEGED_OPERATION_DENIED'
        )
    ) AS scope_denials
FROM authorization_audit
WHERE occurred_at >= now() - INTERVAL '5 minutes'
  AND event_type = 'AUTHORIZATION_DENIED'
GROUP BY actor_key
HAVING COUNT(*) >= 6
    OR COUNT(DISTINCT target_key) FILTER (
        WHERE policy_reason IN (
            'RESOURCE_FORBIDDEN',
            'TENANT_SCOPE_MISMATCH'
        )
    ) >= 5
    OR COUNT(*) FILTER (
        WHERE policy_reason IN (
            'TENANT_SCOPE_MISMATCH',
            'PRIVILEGED_OPERATION_DENIED'
        )
    ) >= 3;
```

**Assumptions:** the table uses matching names/columns, and each row represents one deduplicated canonical decision. This is an example SQL query, not a schema DDL or production streaming solution. At scale, add proper indexes/partitions, handle late events, use event-time windows, scope by tenant/environment, and bound cardinality.

**Suggested metrics:**

- `security_authorization_denials_total{service,operation,reason}`: counter with bounded labels, never putting raw actors/URLs/resource IDs into labels.
- `security_audit_ingestion_lag_seconds`: delay from event emission to store ingestion.
- `security_audit_dropped_total{reason}`: count of lost/overflow events.
- `security_detector_alerts_total{pattern,severity}`: alert count after deduplication.
- Deny/allow ratio per operation (if allow collection is explicitly sampled or scoped).
- Distribution of distinct targets per actor for threshold tuning; compute inside stores/stream jobs rather than making each actor a Prometheus label.

Use traces to drill into a single request, metrics for high-level monitoring, and audit events to investigate decision chains. Never replace structured audit records with free-form log lines.

## 10. Integration Test Matrix: Ensuring Events and Alerts Are Accurate

Set up fixtures with two tenants `north`/`south` and 3 accounts: `readerNorth`, `readerSouth`, `admin`. Each tenant owns a separate set of resources. Wire `AuditSink` and the detector into tests alongside real Spring Security to verify events, HTTP statuses, and side effects.

| ID | Action | Expectation |
| --- | --- | --- |
| P01 | `readerNorth` reads an invoice in `north` | Allowed, zero denials; data matches scope |
| N01 | `readerNorth` reads an invoice in `south` | Denied 403 (or 404 hidden per policy); audit reason tenant mismatch, `targetKey` HMACed |
| N02 | One user probes 5 distinct unauthorized invoices within 5 minutes | `RESOURCE_ENUMERATION` alert once 5 distinct `targetKey`s are reached |
| N03 | One user sends 6 denied requests to the same resource | Only `REPEATED_DENIAL` alert, not misclassified as distinct-resource probing |
| N04 | Regular user attempts 3 admin actions | `SCOPE_BOUNDARY_PROBING` alert; methods/actions are actually blocked |
| N05 | One HTTP request logged at 2 layers with the same `decisionId` | Collector counts it only once |
| N06 | 5 denials, advance Clock 6 minutes, add 1 denial | No false trigger because older events expired from the window |
| N07 | 6 denials, then more denials during cooldown | No duplicate alert spam of the same pattern |
| N08 | Authorized request for a genuinely nonexistent resource | Business 404, not automatically flagged as a tenant-scope attack |
| N09 | Expired token / missing auth | Follows 401 flow; separate authentication audit, not mislabeled as BOLA |
| N10 | Buggy client/UI code retries the same endpoint repeatedly | May hit repeated-denial threshold; triage identifies false positive |
| N11 | Attempt denied while audit sink is unavailable | Permission is still denied; request is not allowed |
| N12 | User permissions revoked while session is still active | Subsequent requests denied with matching reason; stale permissions not retained |
| N13 | Attacker sends an ID with CRLF or huge length | No log injection; keys/fields normalized with bounded length |
| N14 | Two distinct users behind the same NAT | Not merged into one actor solely by IP |
| N15 | Request bypasses Spring Security / self-invoked service method | Tests catch event blind spots and enforce proper protection |

**Verifying a denied case end-to-end:** (1) HTTP/STOMP blocks the action, (2) DB/broadcast produces no unauthorized side effects, (3) audit event carries accurate server-derived actor/operation/reason, (4) detector increments counters properly, (5) alerts fire only when conditions are met, and (6) no sensitive data leaks into bodies/logs. Testing only `status().isForbidden()` or only detector unit tests is insufficient.

## 11. Reducing False Positives, Protecting Users, and Maintaining Alert Quality

Common benign causes of bursts of denials:

- Frontend firing requests from stale UI views right after an admin changed permissions.
- Mobile SDKs retrying permanent 403s as if they were transient 5xxs.
- Preload/prefetch mechanisms requesting batches of resources the client cannot access.
- Batch jobs running with under-scoped service accounts.
- Proxies/clients sharing an IP via NAT; CDNs or gateways writing non-standard `clientKey`s.
- Authorized security testing, monitoring systems, or scanners.
- A single request logged multiple times across services or security layers.
- Misconfigured policy after a deployment causing a sudden global spike in denials.

**Noise-reduction strategies:**

1. Maintain separate baselines by operation, role, tenant, environment, and time-of-day; track rate increases rather than only absolute counts.
2. Distinguish authenticated individuals, sessions, and clients/gateways; correlate with source IP **without treating IP alone as identity**.
3. Deduplicate using trusted IDs, designate canonical events, and handle retries and late arrivals.
4. Classify reasons cleanly; count distinct targets only when `targetKey` is normalized and policy genuinely denied object access.
5. Apply suppression with TTL/cooldown while preserving underlying audit records even when duplicate alerts are suppressed.
6. Account for permission updates, deployments, migrations, and ongoing incidents.
7. Tune thresholds against precision, recall, time-to-detect, and triage cost; version rules for comparison.
8. Separate severity tiers: one denial is an audit record; many denials are a warning; cross-tenant/privileged probes or data-leak indicators escalate urgency.

Never automatically lock accounts upon a single alert from a shared IP; adversaries can exploit that to cause **denial of service** for innocent users. Automated interventions must have high thresholds, bounded blast radius, recovery paths, and human reviewability.

## 12. Incident Response Workflow When the Detector Alerts

An actionable operational runbook:

1. **Confirm the signal:** gather `eventId`, time window, rule name, and counts; verify deduplication and healthy log ingestion.
2. **Verify enforcement:** trace decisions and returned responses; were there any 200s/unauthorized leaks or only policy-compliant 403s? If policy gaps exist, prioritize patching authorization.
3. **Correlate context:** cross-service requests/traces, authentication failures, role/tenant changes, deployment history, admin actions, and prior activity for the same actor.
4. **Assess blast radius:** how many targets/tenants/operations were touched, and were there exports or data mutations; use the least sensitive logs necessary.
5. **Respond proportionally:** alert on-call, require re-authentication, rate-limit by user/action, restrict sensitive endpoints, or revoke suspected compromised tokens—following operational policy with proper approvals.
6. **Preserve evidence:** use an access-controlled, retention-backed, integrity-checked audit store; record correlation IDs for investigation. Never paste tokens or secret payloads into tickets.
7. **Post-incident review:** update policies, BOLA tests, thresholds, missing metrics, and runbooks; track false positives and time to resolution.

If unauthorized access succeeded, that is an **access-control breach** requiring remediation and impact assessment; detection merely surfaced the trail. If all attempts were blocked, focus on identifying the anomalous source without confusing "an alert fired" with "the system was breached".

## 13. Common Design Mistakes

1. **Reading only HTTP 403 access logs to declare an attack.** Lacks policy reasons, trusted actor/tenant context, and distinction from 401/404.
2. **Assuming `AuthorizationDeniedEvent` always carries an HTTP status.** Method events have no response status on their own and can run outside HTTP.
3. **Forgetting to register the event publisher.** Listeners exist yet receive nothing; register the `AuthorizationEventPublisher` bean and write integration tests.
4. **Forgetting `@EnableMethodSecurity` or calling `this.securedMethod()`.** No interception occurs → denial events may be missing even if access should be blocked.
5. **Trusting client-supplied headers for all scopes.** Scopes/tenants must be verified from tokens/DB and policies.
6. **Using plain hashes on guessable IDs.** Use HMAC with managed keys; never write raw IDs to logs.
7. **Logging entire `event.getObject()`/method arguments/tokens.** Leaks sensitive data, risks log injection, and turns the audit store into a high-value target.
8. **Putting user IDs or resource IDs into Prometheus labels.** Causes cardinality explosions; keep labels bounded and investigate details in the audit store.
9. **Counting every layer's event as a separate attack request.** Deduplicate per request/decision.
10. **Using single-instance counters and assuming cluster-wide monitoring.** Scale-out requires centralized state/stream processors or reliable aggregation.
11. **Failing to test denial enforcement.** The detector runs fine while the endpoint still leaks data; test cross-tenant, role boundaries, and side effects.
12. **Leaving detector state unbounded.** Attackers can generate infinite actor/target keys, exhausting RAM or choking audits.
13. **Auto-blocking users from a single IP alert.** NAT/VPNs cause collateral damage to innocent users; investigate and keep interventions proportional.
14. **Treating every 404 as ID probing or every 2xx as safe.** Contextual authorization signals and independent BOLA testing are essential.
15. **Ignoring retention and audit access controls.** Retaining identifiable data too long increases insider and compliance risk.
16. **Letting audit-write failures flip allow/deny decisions.** Use queues, retries, circuit breakers, and clear operational policies; never invert security decisions.

## 14. Implementation Checklist in a Spring Service

- [ ] Policies enforce resource/tenant/owner and admin-action checks, not just URL patterns.
- [ ] `@EnableMethodSecurity` works on real beans/proxies; both allowed and denied paths are tested.
- [ ] `AuthorizationEventPublisher` is registered and integration tests receive `AuthorizationDeniedEvent` at expected layers.
- [ ] Permission denials are separated from authentication failures, not-found, validation, and rate-limit responses.
- [ ] Standard audit schema includes trusted `eventId`/`requestId`/`traceId`, UTC time, and operation/route template.
- [ ] Subject/resource keys are pseudonymized; no tokens, cookies, credentials, or raw method arguments are logged.
- [ ] Reason codes come from policies rather than inferred from client-supplied headers/paths.
- [ ] Deduplication, sliding windows, distinct-target counting, rule versioning, cooldowns, and state TTLs are implemented.
- [ ] Tests verify no alert on a single denial, alerts fire when thresholds are met, and windows expire properly.
- [ ] Drop/lag metrics, protected audit storage, log read permissions, and retention policies exist.
- [ ] Triage runbooks cover false positives, side-effect checks, and anomalous responses.
- [ ] Multi-instance deployments use a cluster-wide detection strategy rather than relying solely on per-node heap.

## 15. References

- [Spring Security – Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html): `AuthorizationEventPublisher`, `SpringAuthorizationEventPublisher`, `AuthorizationDeniedEvent`, and limits on granted events.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, interceptors, and denied events.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): HTTP policies and deny-by-default rules.
- [Spring Boot Actuator – Auditing](https://docs.spring.io/spring-boot/reference/actuator/auditing.html): `AuditEventRepository` and audit listeners.
- [OWASP API Security Top 10 – Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): per-object ID access control.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): event selection, sensitive-data filtering, log-injection defense, store protection, and alerting.
- [OWASP API Security Top 10 – Broken Function Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/): function/role-level authorization.

**Success criteria:** the system properly denies unauthorized access **and** produces an audit trail reliable enough to detect multi-resource enumeration, repeated denials, and tenant/role boundary probing. Alerts are computed on normalized/deduplicated events with explicit thresholds and windows, verified by positive and negative tests, protect privacy, and never replace authorization policies.