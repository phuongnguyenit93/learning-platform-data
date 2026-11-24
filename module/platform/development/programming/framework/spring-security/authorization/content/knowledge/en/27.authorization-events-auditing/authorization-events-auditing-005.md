# Auditing Subject, Tenant, Resource, Action, Decision, and Reason

> Context: **Spring Security – authorization**, topic **Events and Auditing**. This lesson uses a Java 17+ application on Spring Boot 3.x / Spring Security 6.x (Servlet stack) as an example. Audit design principles apply equally to services, message consumers, and background jobs; event sources in WebFlux, STOMP, or other framework versions need dedicated integration.

## 1. Goal and Scenario

Suppose user `u-42` is operating inside tenant `tenant-a` and invokes `invoice.approve` on invoice `INV-7`. The server rejects it due to missing permission. A simple log line `403 Forbidden` cannot answer:

- **Who** made the request? A real user, a service account, or anonymous?
- **Which tenant** is the permission scope in effect? Where was the tenant verified from?
- **Which resource** was accessed? Does the resource belong to that tenant?
- **Which action** was attempted? Read, approve, delete, or export?
- **What was the authorization result**—`ALLOW` or `DENY`?
- **Why** did the system reach that decision? Missing permission, cross-tenant, failed attribute check, or no matching policy?

A good audit records **the six dimensions above as a structured event**, along with enough supporting data to investigate and reconcile policy changes. It serves traceability, unauthorized-access detection, decision explanation, internal controls, and policy testing. Auditing does not replace **actually blocking** unauthorized requests; it must be integrated into the controlled decision path.

Distinguish three concepts:

| Concept | Example | Meaning |
| --- | --- | --- |
| Authentication event | `LOGIN_SUCCESS`, `LOGIN_FAILURE` | Identity was just verified or verification failed |
| Authorization decision audit | `u-42` tried `invoice.approve` on `INV-7` → `DENY` | Permission check result **for a specific action/resource** |
| Business operation outcome | `invoice.approve` saved successfully or transaction failed | Whether the business operation **actually completed or failed** |

**`ALLOW` does not mean the operation succeeded.** An `ALLOW` decision can be followed by a validation error, state conflict, timeout, or rollback. Separate `decision` (permission) from `outcome` (execution).

## 2. Six Core Fields of an Authorization Audit

| Field | Meaning and trusted source | Example | Notes |
| --- | --- | --- | --- |
| **Subject** | Acting identity from verified and normalized `Authentication/Principal` | `USER:u-42`, `SERVICE:job-8` | Do not take `subjectId` from the request body and treat it as identity |
| **Tenant** | Organizational scope **verified by the server** from trusted claims, membership, context, or internal data | `tenant-a` | Must distinguish the requested tenant from the resource's tenant |
| **Resource** | Type, ID, and if applicable, owning tenant of the checked object | `INVOICE:INV-7` | Avoid storing full payloads or sensitive object data |
| **Action** | Standardized operation name, independent of transport | `invoice.approve` | A single HTTP `POST` may encompass multiple business actions |
| **Decision** | Result returned by the policy engine/authorization guard | `ALLOW` / `DENY` | Do not infer backwards solely from HTTP status; `ABSTAIN`/evaluation errors must be defined clearly |
| **Reason — reasonCode** | Stable cause code produced by the decision point | `TENANT_MISMATCH`, `MISSING_PERMISSION` | Do not log explanations containing secrets or guess reasons from a 403 |

The six fields are a **semantic minimum**, not necessarily all populated with concrete values every time. For example, a request blocked at the URL layer before object lookup may not yet know `resourceId`; record `null`/`UNKNOWN` and `decisionStage=HTTP`, rather than inventing an ID to "fill all fields".

### 2.1 Subject: Who Is Acting?

`subject` should include a stable ID and identity type: user, service account, workload, system, or anonymous. `Authentication#getName()` is useful, but usernames/emails can sometimes change or contain personal data; long-lived audits should map to an **immutable internal ID** or an approved identifier.

If the system allows acting on behalf of someone else, distinguish:

- `actorId`: the actual identity calling the system, e.g., a support agent.
- `onBehalfOfId`: the represented subject, if any.
- `impersonationApproved`/delegation code: server-verified proof of delegation.

Never record passwords, bearer tokens, session IDs, cookies, full claims, or serialized `Authentication` objects.

### 2.2 Tenant: Within Which Organizational Boundary?

In multi-tenant systems, there are usually at least two pieces of data: `requestedTenantId` (client-selected) and `authorizedTenantId` or `effectiveTenantId` (server-confirmed). If the resource belongs to another tenant, also record `resourceTenantId`. Do not treat an `X-Tenant-Id` header as access permission merely because the header is present.

Trust chain: verify token/session → look up user membership and roles in the tenant → determine active tenant → load resource and owning tenant from a server source → evaluate policy. The tenant in the audit must reflect **verified context**, never blindly copied untrusted data from URLs/bodies.

### 2.3 Resource and Action: "Permission on What?"

A stable `resource.type` + `resource.id` pair aids aggregation. Include `resource.tenantId` when doing tenant-level checks. Actions should use policy vocabulary—such as `invoice.read`, `invoice.approve`, `invoice.export`, `user.invite`—rather than just `GET`/`POST`; map HTTP endpoints, STOMP messages, or job actions consistently to business actions.

If one request processes multiple objects, you can record **multiple decisions** with separate `decisionId`s and the same `requestId`. A single "ALLOW upload" record does not automatically prove permission for every individual file if policy requires per-file checks.

### 2.4 Decision and Reason: Conclusion and Basis

Use a controlled value set:

- `ALLOW`: policy allows the request, **without guaranteeing business outcome**.
- `DENY`: a required condition failed (deny by default if no matching permission is found).
- `INDETERMINATE`/`ERROR`: cannot evaluate reliably due to a failing dependency or insufficient data. For sensitive resources, **fail closed** (block the operation), while distinguishing evaluation errors from normal `DENY` when analyzing audits.

`reasonCode` values can include `POLICY_MATCH`, `MISSING_PERMISSION`, `TENANT_MISMATCH`, `SUBJECT_UNAUTHENTICATED`, `RESOURCE_NOT_VISIBLE`, `ATTRIBUTE_CONDITION_FAILED`, `NO_MATCHING_POLICY`, and `POLICY_EVALUATION_ERROR`. Codes must originate from the **actual reason-determination step**. Do not assign `TENANT_MISMATCH` simply because you see HTTP 403; 403 can also come from CSRF or elsewhere.

When multiple conditions fail, define a **reason priority order** (e.g., subject → tenant → resource visibility → permission → attributes) or record a policy-approved list of `reasonCodes`. Do not disclose internal reasons to clients that could confirm the existence of a confidential object.

## 3. Recommended Audit Record Structure

An extensible schema can use JSON:

~~~json
{
  "schemaVersion": 1,
  "eventType": "AUTHORIZATION_DECISION",
  "eventId": "evt-a1",
  "occurredAt": "2026-11-05T10:30:00Z",
  "subject": {
    "type": "USER",
    "id": "u-42"
  },
  "tenant": {
    "effectiveId": "tenant-a",
    "source": "VERIFIED_MEMBERSHIP"
  },
  "resource": {
    "type": "INVOICE",
    "id": "INV-7",
    "tenantId": "tenant-a"
  },
  "action": "invoice.approve",
  "decision": "DENY",
  "reasonCode": "MISSING_PERMISSION",
  "policy": {
    "id": "invoice-approval",
    "version": "v3"
  },
  "decisionStage": "DOMAIN",
  "requestId": "req-19",
  "traceId": "trace-72",
  "service": "billing-service"
}
~~~

The illustrative values above are not a real event. `eventId`, `requestId`, and `traceId` are all generated by the system or received from a trusted tracing mechanism with format validation. In production, avoid putting arbitrary client-sent trace IDs into logs without normalization.

Valuable supporting fields:

| Supporting field | Purpose |
| --- | --- |
| `schemaVersion` | Allows schema upgrades while older consumers can still read records |
| `eventId` / `decisionId` | Identifies a single decision, prevents duplicates on retries |
| `occurredAt` | UTC time of the decision; add ingestion time if needed |
| `requestId` / `traceId` | Correlates event chains across gateway, service, and database |
| `decisionStage` | `HTTP`, `METHOD`, `DOMAIN`, `MESSAGE`… |
| `policy.id` / `policy.version` | Explains why the same request may receive a different result after a rule change |
| `service` / `environment` | Identifies execution location; never mix staging with production |
| `actorType`, `sessionAssurance` | Classifies user, service, MFA/step-up if policies depend on these factors |
| `decisionLatencyMs` | Monitors policy evaluation cost |
| `operationId` / separate `outcome` | Links later to execution results without conflating them with authorization |

Prefer a **versioned, stable, strongly typed** schema. For fields unavailable due to an early decision, use `null` or a meaningful `UNKNOWN` state; avoid empty strings that look like collection bugs.

## 4. Path of an Event in Spring Security Architecture

~~~text
Request / message / scheduled job
          │
          ▼
Authentication: identify actor
          │
          ▼
Tenant resolver: verify membership and effective tenant
          │
          ▼
Authorization check (URL, method, domain, resource)
          │
          ├── ALLOW ──► audit decision: ALLOW + reason/policy
          │                 │
          │                 └── run business logic -> separate outcome (success/failure)
          │
          └── DENY  ──► audit decision: DENY + reason/policy
                            │
                            └── block operation / throw AccessDeniedException / return 403
                                    (how HTTP translation behaves depends on auth status)
~~~

Each layer has a different perspective:

- **HTTP authorization** via `authorizeHttpRequests` / `AuthorizationFilter` knows the method/path and principal, and typically **does not yet know the resource owner or tenant of a database record**.
- **Method security** via `@EnableMethodSecurity`, `@PreAuthorize`, and `AuthorizationManagerBeforeMethodInterceptor` may know method parameters, though not necessarily full DB data.
- **Domain authorization** in a service/policy guard knows permissions on a specific object after loading it from a trusted source; this is usually the best place to record all six fields and exact reason codes.
- **Authentication events** and **CSRF rejections** are distinct security signals; do not assume every login/CSRF error appears as a domain-decision `AuthorizationDeniedEvent`.

If the same request is checked at HTTP and then in a service, there may be **two different audit decisions**, with different `decisionStage`/`policy.id` values. This is valid if each record represents one exact checkpoint and carries its own `decisionId`. If business requirements want only one canonical decision record, designate one canonical emission source and route other checks into supporting telemetry; avoid double-counting as two "denied accesses".

### An ALLOW Trail Does Not Prove the Transaction Committed

For example, `u-42` passes policy and receives `ALLOW` to approve an invoice. Afterward, the database rolls back due to an insufficient balance. The authorization audit records `ALLOW`, while the business audit records `OPERATION_FAILED`. Changing `ALLOW` to `DENY` after a rollback corrupts authorization history. You can use the same `operationId` to link the two events.

## 5. Standalone Java 17 Example: Producing Three Audit Decisions

The following example simulates decisions checking **tenant first, then permission**. It uses a pre-verified permission set; the code does not demonstrate login or loading tenants from a database. Put it in `AuthorizationAuditExample.java`:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Set;

public class AuthorizationAuditExample {

    enum Decision { ALLOW, DENY }

    record Actor(
        String id,
        String tenantId,
        Set<String> permissions
    ) {}

    record Resource(
        String type,
        String id,
        String tenantId
    ) {}

    record AuditEvent(
        Instant occurredAt,
        String subjectId,
        String tenantId,
        String resourceType,
        String resourceId,
        String action,
        Decision decision,
        String reasonCode
    ) {}

    static AuditEvent evaluate(
        Actor actor,
        Resource resource,
        String action,
        String requiredPermission
    ) {
        Decision decision;
        String reason;

        if (!actor.tenantId().equals(resource.tenantId())) {
            decision = Decision.DENY;
            reason = "TENANT_MISMATCH";
        } else if (!actor.permissions().contains(requiredPermission)) {
            decision = Decision.DENY;
            reason = "MISSING_PERMISSION";
        } else {
            decision = Decision.ALLOW;
            reason = "POLICY_MATCH";
        }

        // Fixed timestamp so lesson output is always reproducible.
        return new AuditEvent(
            Instant.parse("2026-01-02T09:00:00Z"),
            actor.id(),
            actor.tenantId(),
            resource.type(),
            resource.id(),
            action,
            decision,
            reason
        );
    }

    public static void main(String[] args) {
        Actor actor = new Actor(
            "u-42", "tenant-a", Set.of("invoice.read")
        );

        Resource own = new Resource("INVOICE", "INV-7", "tenant-a");
        Resource other = new Resource("INVOICE", "INV-8", "tenant-b");

        List<AuditEvent> events = List.of(
            evaluate(actor, own, "invoice.approve", "invoice.approve"),
            evaluate(actor, other, "invoice.read", "invoice.read"),
            evaluate(actor, own, "invoice.read", "invoice.read")
        );

        for (AuditEvent e : events) {
            System.out.printf(
                "subject=%s tenant=%s resource=%s:%s action=%s decision=%s reason=%s%n",
                e.subjectId(),
                e.tenantId(),
                e.resourceType(),
                e.resourceId(),
                e.action(),
                e.decision(),
                e.reasonCode()
            );
        }
    }
}
~~~

Run commands (JDK 17+):

~~~bash
javac AuthorizationAuditExample.java
java AuthorizationAuditExample
~~~

Exact stdout:

~~~text
subject=u-42 tenant=tenant-a resource=INVOICE:INV-7 action=invoice.approve decision=DENY reason=MISSING_PERMISSION
subject=u-42 tenant=tenant-a resource=INVOICE:INV-8 action=invoice.read decision=DENY reason=TENANT_MISMATCH
subject=u-42 tenant=tenant-a resource=INVOICE:INV-7 action=invoice.read decision=ALLOW reason=POLICY_MATCH
~~~

Notes:

1. The actor is allowed `invoice.read` but cannot `invoice.approve`.
2. Even with `invoice.read`, access is denied when the resource belongs to another tenant.
3. The `ALLOW` decision only says the actor is permitted to read the resource; it does not say the read operation succeeded.
4. In production, replace `Instant.parse(...)` with `Clock.instant()`/`Instant.now()`; use trusted IDs and unique eventId/traceId values; write through a controlled audit writer.
5. The code returns `AuditEvent` for illustration; at enforcement points, you must **block the operation on `DENY`**, not merely log it. A policy is unsafe if it logs DENY and still calls the service.

## 6. Connecting to Spring Security Authorization Events

Spring Security provides events in the `org.springframework.security.authorization.event` namespace, notably `AuthorizationDeniedEvent` and `AuthorizationGrantedEvent`. Event publishing relies on `AuthorizationEventPublisher`. In integration flows that support the publisher, `SpringAuthorizationEventPublisher` translates decisions into Spring application events; **DENY** events are published under the publisher's default behavior, whereas **GRANT is not published wholesale by default** because it easily produces high volume.

### 6.1 Registering the Publisher

Configuration example for compatible Spring Security versions:

~~~java
// AuthorizationEventsConfig.java, package and imports depend on project
package example.audit;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;

@Configuration
public class AuthorizationEventsConfig {
    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher events) {
        return new SpringAuthorizationEventPublisher(events);
    }
}
~~~

This is a configuration class in a **Spring Boot project with the `spring-boot-starter-security` dependency**, not standalone Java runnable with `javac`. For method security, enable `@EnableMethodSecurity` if the application uses `@PreAuthorize`. Having a publisher bean does not itself add authorization policies; HTTP/method/domain rules must still be configured.

### 6.2 Listening to Denied Events Without Serializing Raw Context

~~~java
// AuthorizationDeniedObserver.java
package example.audit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class AuthorizationDeniedObserver {
    private static final Logger log =
        LoggerFactory.getLogger(AuthorizationDeniedObserver.class);

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> event) {
        Authentication authentication = event.getAuthentication().get();

        String actorKind =
            (authentication == null
                || authentication instanceof AnonymousAuthenticationToken)
                ? "ANONYMOUS" : "AUTHENTICATED";

        Object target = event.getObject();
        String targetKind = target == null
            ? "UNKNOWN" : target.getClass().getSimpleName();

        log.warn("authz_event=DENY actor_kind={} target_kind={}",
            actorKind, targetKind);
    }
}
~~~

**Meaning and limits:** this listener observes DENY signals safely at a coarse level, **and does not yet produce a full six-field audit record**. `event.getObject()` may be a request context, method invocation, or framework object depending on the checkpoint; calling `toString()` or serializing the whole object can expose sensitive URLs, headers, method arguments, or bodies. Moreover, default events do not necessarily carry `tenantId`, `resourceId`, and business `reasonCode`.

Therefore, for complete audits, the service/policy guard must supply trusted context and **reason codes evaluated by the policy itself**. Never guess `MISSING_PERMISSION` just because a listener saw `AuthorizationDeniedEvent`. If you also need to observe `ALLOW`, configure the publisher to emit **selectively** for sensitive decisions/permissions, or emit domain audits where permitted; avoid enabling all grants in high-traffic systems without load design.

### 6.3 Pattern for Recording Audits at Business Decision Points

Where the server already has the principal, verified active tenant, and resource from the database, the recommended order is:

~~~text
1. Identify actorId from trusted Authentication/Principal.
2. Verify actor membership in effectiveTenantId.
3. Load the resource using a tenant-scoped query; determine resourceType/resourceId.
4. Evaluate policy (including ownership, permission, status, attributes).
5. Create decisionId, decision, reasonCode, policyVersion.
6. Send an immutable AuditRecord to AuditSink.
7. DENY -> block via AccessDeniedException; ALLOW -> continue business logic.
8. Record a separate business outcome after the operation completes/rolls back.
~~~

If step 3 intentionally returns the same 404 for "does not exist" and "not permitted to view" to prevent enumeration, internal audits should still retain only minimal permitted data. Do not leak `RESOURCE_EXISTS_BUT_FORBIDDEN` to the client.

**Integration pseudocode** example (`AuditSink`, `TenantMembershipService`, and `InvoicePolicy` are application abstractions; this is not a standalone Java file):

~~~java
EffectiveTenant tenant = tenantService.requireMembership(actor, requestedTenant);
Invoice invoice = repository.loadForAuthorization(invoiceId);
PolicyResult result = invoicePolicy.check(
    actor, tenant, invoice, "invoice.approve");

AuditRecord record = AuditRecord.of(
    actor.stableId(), tenant.id(),
    "INVOICE", invoice.stableId(),
    "invoice.approve", result.decision(), result.reasonCode(),
    result.policyVersion(), currentRequestId());

auditSink.append(record);

if (!result.allowed()) {
    throw new AccessDeniedException("Action not permitted");
}

invoiceService.approve(invoice);
~~~

Two important points about real-world logic:

- If membership verification or resource lookup **rejects before the full object is available**, auditing must occur in that failure branch using explicit unknown fields; do not let a `throw` happen before an important decision trace is recorded.
- If the operation belongs to a category requiring **mandatory auditing**, define what happens when `auditSink` fails (block/fail closed or durable queue). Never let routine logging whimsically decide access rights without an explicit policy.

## 7. Designing Consistent `reasonCode` Values

A system is hard to trace if one place logs `"User missing right"`, another logs `"permission_denied"`, and another logs an entire exception message. Maintain a versioned code dictionary with testable meanings:

| `reasonCode` | When it occurs | Principle |
| --- | --- | --- |
| `SUBJECT_UNAUTHENTICATED` | No sufficiently trusted identity to evaluate | Usually belongs to authentication stage or a login-required policy |
| `TENANT_MEMBERSHIP_MISSING` | User does not belong to the selected tenant | Verify membership server-side |
| `TENANT_MISMATCH` | Resource tenant differs from allowed scope | Do not trust client-claimed resource tenant |
| `MISSING_PERMISSION` | Missing required `invoice.approve`/scope | Permission names must be standardized |
| `RESOURCE_NOT_VISIBLE` | Not allowed to view, or existence is hidden | Avoid exposing IDs to the client |
| `POLICY_CONDITION_FAILED` | Additional attributes failed (time, ownership, state…) | Optionally include `policyRuleId` in internal audits |
| `NO_MATCHING_POLICY` | No rule exists for this action/resource | Enforce deny by default |
| `POLICY_EVALUATION_ERROR` | Cannot evaluate due to dependency failure | Fail closed; distinguish from normal denials |
| `POLICY_MATCH` | All required conditions are satisfied | Reason for ALLOW, not used as business outcome |

Example with both missing permission and tenant mismatch: if the policy already rejected at the tenant guard, the primary reason should be `TENANT_MISMATCH` following evaluation order. Avoid inferring backwards about permissions that were never checked. If multiple reasons must be recorded, record only conditions that were actually evaluated and manage information-disclosure risks.

Note: `AccessDeniedException` or `AuthorizationDeniedEvent` typically proves only a denial decision; they **do not automatically provide** `TENANT_MISMATCH`, `MISSING_PERMISSION`, or a concrete `policyVersion`. Providing those is a design responsibility of the policy/domain layer or a custom `AuthorizationResult` carrying explanatory data under an application contract.

## 8. Trusted Data Sources and Anti-Spoofing in Multi-Tenancy

Consider an attacker logged into tenant A who sends:

~~~http
POST /api/tenants/tenant-b/invoices/INV-8/approve
X-Tenant-Id: tenant-b
Authorization: Bearer <redacted>
~~~

The header/path only express client intent. The server must:

1. Validate the token by issuer, audience, signature, expiration, or session per architecture.
2. Identify the trusted `actorId` and verify real membership in `tenant-b`.
3. If not a member of tenant B, deny and audit `TENANT_MEMBERSHIP_MISSING`. Do not necessarily reveal whether `INV-8` exists.
4. If a member of tenant B, load `INV-8` under the matching tenant filter; verify resource owner and `invoice.approve`.
5. Write the audit with actor, server-verified effective tenant, resource/action, decision, and reason.

Do not use `ThreadLocal`/`SecurityContext` after switching to an async thread without propagating context through a controlled mechanism. In message consumers/jobs without an HTTP request, the subject may be a service identity; the tenant must come from a verified message or trusted metadata. If context is missing, evaluate **fail closed** per policy and audit the missing-context condition.

In multi-tenant systems, enforce **audit read permissions**: an operator in tenant A must not query tenant B's audits merely by knowing an `eventId`/`resourceId`. Enforce tenant and scope constraints in the audit storage/search system itself, not only in the primary business API.

## 9. Writing and Storing Audits: Integrity, Performance, Queryability

### 9.1 Immutable Events with Standard IDs and Timestamps

Use immutable records/schemas; include a unique `eventId`, UTC `occurredAt`, and `ingestedAt` when the pipeline receives the data. Never "rewrite history" by UPDATing old records when policies change; emit correction events if needed. With Kafka, outbox, queues, or async sinks, **at-least-once delivery** can redeliver messages: consumers must deduplicate by `eventId` and preserve retry trails appropriately.

### 9.2 Balancing Security and Latency

- **Mandatory audits for sensitive actions:** choose durable delivery, backpressure/failover, and an explicit fail-closed decision if recording cannot be guaranteed; evaluate throughput, timeouts, and recovery.
- **High-volume ALLOW telemetry:** sampling/aggregation is acceptable, but **never call sampled data a complete audit log**. Denial and security-critical events generally need higher delivery guarantees.
- **Avoid blocking requests over non-critical logging systems:** separate operational logs from security audits that require preservation.
- **Never write raw exceptions/HTTP bodies to sinks:** redact/mask/allowlist fields. Log lines should use structured JSON or a parseable format, capping client-supplied value lengths.

Spring Application Event listeners normally execute synchronously on the publisher thread under the default application event multicaster configuration. Slow database/network calls directly inside a listener can therefore prolong requests. For high event volume, decouple record normalization from durable delivery—but **never compromise audit guarantees** for operations where auditing is mandatory.

### 9.3 Protecting Audits from Tampering/Deletion

Enforce separated write/search permissions, policy-driven retention, PII controls, encryption in transit/at rest, backups, and tamper-detection mechanisms (append-only/WORM/signatures/hash-chaining as required). Synchronize clocks and trace IDs. When storing actor IDs or IPs under privacy rules, keep only necessary fields, limit retention, and restrict access.

Audits may be used in investigations, so **do not rely solely on ephemeral pod/container logs**. A centralized audit store or durable pipeline is more trustworthy than standalone stdout.

## 10. Testing Policies and Audits Together

Design tests covering both enforcement behavior and events:

| Scenario | Expected decision | Expected reason | Audit assertion |
| --- | --- | --- | --- |
| Authenticated, same tenant, sufficient permission | `ALLOW` | `POLICY_MATCH` | Correct subject/tenant/resource/action, policy version; do not assume business success |
| Same tenant, missing permission | `DENY` | `MISSING_PERMISSION` | One primary decision event; operation not executed |
| Has permission, resource in another tenant | `DENY` | `TENANT_MISMATCH` | Effective tenant and resource tenant distinguished |
| User spoofs `X-Tenant-Id` | `DENY` | `TENANT_MEMBERSHIP_MISSING` | Claimed tenant not treated as verified tenant |
| Anonymous calls login-required action | Blocked | `SUBJECT_UNAUTHENTICATED` if defined by policy | Subject type = ANONYMOUS, no fabricated user ID |
| Resource not visible to caller | Blocked | `RESOURCE_NOT_VISIBLE` or equivalent policy code | No sensitive ID/metadata leaked to client |
| Policy lookup system times out | Operation blocked | `POLICY_EVALUATION_ERROR` | Record failure stage; do not fake missing permission |
| ALLOW decision then DB rollback | `ALLOW` | `POLICY_MATCH` | Authorization audit remains ALLOW; business outcome reports FAILED separately |
| Retry emits same event | No extra logical decision record | Unchanged | Deduplicate by eventId/decisionId |
| Request blocked at HTTP before service | Blocked | Reason at HTTP layer | Do not claim uncomputed resourceId/domain reason |

Example assertion checklist in unit/integration tests:

~~~text
assert(response is 403 or configured deny response);
assert(domainOperationWasNotExecuted);
assert(audit.eventType == "AUTHORIZATION_DECISION");
assert(audit.subject.id == authenticatedSubjectId);
assert(audit.tenant.effectiveId == verifiedTenantId);
assert(audit.resource.type == expectedResourceType);
assert(audit.action == expectedAction);
assert(audit.decision == "DENY");
assert(audit.reasonCode == expectedReasonFromPolicy);
assert(noCredentialOrSecretInAudit);
~~~

The snippet above is **testing pseudocode**, not runnable Java syntax. In actual Java unit tests, you can assert that `AuthorizationAuditExample.evaluate(...)` returns the expected `AuditEvent`; in Spring integration tests, mock the audit sink and verify events are emitted only after policy evaluation and business commands are blocked on deny.

If there is a requirement for *one event per decision*, define the exact test boundary (one domain guard vs. a full request traversing multiple layers). Do not write `exactly once` tests on queue systems that can redeliver; test idempotent handling there instead.

## 11. Common Design Mistakes

1. **Logging only HTTP status**: loses actor, tenant, resource, action, and cause; 403 can also come from CSRF rather than a policy denial.
2. **Reading tenant/subject directly from the request**: clients can alter them; audits become inaccurate and permission decisions risk compromise.
3. **Recording generic `DENY` without reasonCode**: makes it hard to tell missing permission from tenant mismatch or dependency error.
4. **Inferring reasons from exception messages**: text is unstable and may expose internals; use policy-produced reason codes.
5. **Recording `ALLOW` as a successful transaction**: authorization and business outcome are two independent steps.
6. **Serializing the entire SecurityContext/request/method arguments**: can leak credentials, PII, or sensitive domain data.
7. **Enabling every `AuthorizationGrantedEvent`**: high volume easily raises latency/cost; emit selectively or via domain audits as needed.
8. **Catching only `AccessDeniedException` in controllers**: many decisions happen in filters/method interceptors and are easily missed. Record at the appropriate checkpoint.
9. **Multiple layers double-recording one decision**: lacking `decisionId` and `decisionStage` to distinguish them skews statistics.
10. **Writing an audit and still executing on `DENY`**: auditing is observation only, not resource protection. Enforcement is mandatory.
11. **No failure policy when audit writing fails**: for sensitive actions this creates traceability gaps; for unimportant logs it needlessly reduces availability.
12. **Letting tenants view all audit records**: the audit store is itself a resource needing permission control, tenant isolation, and data minimization.

## 12. Self-Check and Key Takeaways

Ask yourself these questions when designing an endpoint `POST /api/tenants/{tenantId}/invoices/{id}/approve`:

- Is the actor taken from `Authentication` or from a `userId` field in the body?
- Has tenant membership been verified, and does it match the invoice's owning tenant?
- Is the action name `POST` or `invoice.approve`; which policy version was applied?
- Where does the system record `DENY` with a specific reason before throwing an exception?
- If the decision is `ALLOW` but the database rolls back, how are the two events represented?
- Can an incident be investigated via `requestId`/`eventId` without hunting for tokens or sensitive data?

**Mental model:** auditing a decision = **verified subject + verified tenant + identifiable resource + standardized action + policy result + stable reason code**, enriched with timestamp, policy version, and correlation. Each field reflects facts known at **decision time**, not assumptions reconstructed afterward.

## 13. References

Official Spring Security documentation (check your dependency version before using APIs):

- Authorization Events: https://docs.spring.io/spring-security/reference/servlet/authorization/events.html
- Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Authentication Events (distinguish from authorization): https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- API AuthorizationDeniedEvent: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/event/AuthorizationDeniedEvent.html
