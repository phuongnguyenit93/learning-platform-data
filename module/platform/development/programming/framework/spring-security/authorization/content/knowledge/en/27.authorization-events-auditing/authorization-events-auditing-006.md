# Distinguishing Access Audits from Permission-Change History

In **Spring Security - authorization**, the question **"Who accessed or was denied when?"** differs from **"Who changed permissions, what changed, and when did it take effect?"**. Both require auditing, but they observe **two different kinds of behavior**. Mixing them up leaves operations teams seeing an HTTP 403 without knowing who revoked the permission; conversely, they might see a user's role elevated without knowing whether that privilege was ever exercised.

This lesson belongs to the **Events and Auditing** group. Its goal is to design, collect, and properly correlate **access/authorization decision audits** with **permission-change history** in Servlet-based Spring Security applications.

## 1. Precisely Defining the Two Types of Evidence

### 1.1. Access Audit: What Happened at Permission-Check Time?

An **access audit event** records an instance where the system evaluated or enforced permissions for an action on a resource, for example:

- `alice` was **ALLOW**ed when requesting to read `invoice:42` at 10:00.
- `bob` was **DENY**ed when requesting the same action at 10:01.
- A request was denied at the HTTP layer by `AuthorizationFilter`; or a method was blocked by `@PreAuthorize`.
- A sensitive operation such as exporting data, approving a transaction, or deleting a resource was authorized and actually executed.

Distinguish three levels: **authorization decision** (ALLOW/DENY), **HTTP response** (200/401/403/404/5xx), and **business outcome** (operation succeeded/failed). They are not identical: an ALLOW decision can still lead to 500; an authorized method can fail a database update; 401 can occur during authentication before any full authorization decision.

Suggested data fields for an **access audit**:

| Field | Meaning |
| --- | --- |
| `eventId`, `occurredAt` | Unique ID; UTC timestamp of the event |
| `principalId`, `principalType`, `tenantId` | Subject being checked: user/service/workload; tenant if applicable |
| `action`, `resourceType`, `resourceId` | Action and target object evaluated, e.g., `invoice:read` and `invoice:42` |
| `decision`, `reasonCode` | ALLOW/DENY and standardized reason, e.g., `MISSING_AUTHORITY` |
| `policyVersion` or `entitlementVersion` | Version of rules/entitlements **actually used** during the check, if supported |
| `requestId`, `traceId`, `serviceId` | Links to the request/trace and the service making the decision |
| `authenticationMethod`, `sessionIdHash` (if needed) | Minimal authentication context, per data-protection policies |
| `operationOutcome` (if applicable) | Business execution status after ALLOW; must not be conflated with `decision` |

You do not need to record everything for every endpoint. Choose granularity based on risk, traffic, security, and investigative goals. Values such as URLs, IPs, user-agents, or IDs can be personal data and must be governed by policy.

### 1.2. Permission-Change History: How Did Authorization Configuration Change?

A **permission-change event** records a **change in effective state or change request** for an authorization component, for example:

- An administrator grants or revokes the `REPORT_VIEWER` role for `bob`.
- The `REPORT_VIEWER` role has the `INVOICE_EXPORT` permission added.
- An ABAC rule changes from "owner-only" to "owner or assigned reviewer".
- The ACL of `document:19` changes from `bob:READ` to `bob:READ,WRITE`.
- A policy has a new version published, is rolled back to a prior version, or changes activation status.
- A temporary grant expires, is revoked, or is renewed.

This is an **audit of administrative permission changes**, not a copy of the current role/permission table. Records need enough data to prove *who proposed, who approved, who executed, what changed, when it took effect, and why*.

Suggested data fields for **permission-change history**:

| Field | Meaning |
| --- | --- |
| `changeId`, `occurredAt`, `effectiveAt` | Event ID, recorded time, and effective time |
| `operatorId`, `approverId` (if applicable) | Who executed/approved the change |
| `targetType`, `targetId`, `tenantId` | Whose permissions or which policy/role/resource was modified |
| `changeType` | `GRANT`, `REVOKE`, `POLICY_UPDATED`, `ROLE_PERMISSION_CHANGED`, `EXPIRED`, `ROLLBACK` |
| `before`, `after` or `diff` | Old/new state of the **exact scope of change**, not a dump of the entire principal |
| `oldVersion`, `newVersion` | Permission/policy version before and after; aids historical reconciliation |
| `reason`, `ticketId`, `approvalId` | Business reason and approval evidence |
| `transactionId`, `deploymentId`, `source` | Links to commit, config, automated request, or deployment |
| `result` | `APPLIED` / `REJECTED` / `FAILED`, so failed operations are not misrecorded as permission changes |

**Assigning a role to a user**, **changing a role's permissions**, **editing a policy**, and **changing an object's ACL** are distinct scopes of change. Each record must make the scope explicit. Storing only "role added to bob" without knowing what permissions that role held at that moment makes reconstructing past access decisions difficult later.

## 2. Quick Comparison

| Criterion | Access audit | Permission-change history |
| --- | --- | --- |
| Core question | Who requested what on which resource; allowed or denied? | Who changed which permission/role/policy/ACL? |
| Recorded actors | **Principal being checked** | **Executing operator**, **affected target**, approver if any |
| Trigger | Permission check, sensitive action, or operation outcome | Grant/revoke command, policy publish, role edit, ACL update, rollback |
| Outcome | `ALLOW`/`DENY` and separate business outcome | `APPLIED`/`FAILED`/`REJECTED` and before/after |
| Core data | `principal`, `action`, `resource`, `decision`, `policyVersion`, `requestId` | `operator`, `target`, `changeType`, `before`, `after`, `version`, `reason` |
| Frequency | Often very high | Typically lower, with high investigative value |
| Origin | Authorization filter, method security, service decision, business action | IAM/admin service, role store, ACL service, policy pipeline |
| What it does not prove | ALLOW does not guarantee the business operation succeeded | A new permission does not prove it was ever used |
| Typical analysis | Sudden DENY spikes, sensitive resource access | Who granted out-of-policy privileges, who altered rules before an incident? |

**Authentication audit** is a separate category: login successes/failures, MFA, logout, or token refreshes. Successful authentication does not mean permission to access a resource. **Data-change audit** answers "who changed business data values?". An invoice edit can have both an access audit (permitted to edit) and a data-change audit (which fields changed), even without any permission change.

## 3. Timeline: Why Both Are Needed

Suppose the `INVOICE_READ` permission is used to read `invoice:42`.

| UTC | Trail | Event |
| --- | --- | --- |
| 10:00 | Access | `alice` reads `invoice:42`: ALLOW, permissions version `v1` |
| 10:01 | Access | `bob` reads `invoice:42`: DENY, `v1` |
| 10:02 | Permission change | `admin` GRANTs `INVOICE_READ` to `bob`; version `v1 -> v2`, ticket `T-42` |
| 10:03 | Access | `bob` reads `invoice:42`: ALLOW, `v2` |
| 10:04 | Permission change | `admin` REVOKEs `INVOICE_READ` from `bob`; `v2 -> v3`, ticket `T-99` |
| 10:05 | Access | `bob` reads `invoice:42`: DENY, `v3` |

Looking only at the access audit shows `bob`'s decisions flipping DENY → ALLOW → DENY, **without explaining why permissions changed**. Looking only at the history shows two grant/revoke actions, **without showing whether `bob` actually accessed `invoice:42` during the granted window**. Correlating by `principal/target`, `action`, resource scope, time, and `policyVersion` reconstructs the full sequence.

Note: outcomes can also change **without any GRANT/REVOKE** due to ABAC conditions, ownership, business hours, resource state, feature flags, policy rollouts, token TTLs, or context attributes. Thus "every DENY must have a preceding permission-change event" is a false assumption. A role change may have committed while an older token/JWT or cache still holds prior claims; recording the **version or snapshot used at decision time** explains those cases.

## 4. Which Spring Security Layer Emits Which Event?

In a **Spring Security Servlet** application:

1. Authentication filters and `AuthenticationManager` resolve identity/credentials; they can produce **authentication events**. That is not yet proof that the user has permission to read a specific resource.
2. `AuthorizationFilter` enforces `authorizeHttpRequests` at the request layer. `@EnableMethodSecurity` with `@PreAuthorize`/`@PostAuthorize` enforces checks at the method layer.
3. `AuthorizationEventPublisher` can publish **authorization events**. `SpringAuthorizationEventPublisher` emits `AuthorizationDeniedEvent` for denials; **granted events are not published by default** because they easily generate heavy traffic. If the product requires auditing all sensitive ALLOWs, configure publishing explicitly or collect at the appropriate business point.
4. `ExceptionTranslationFilter` together with `AuthenticationEntryPoint`/`AccessDeniedHandler` translates security errors into HTTP responses. HTTP status does not replace access decision records; the same 403 code can arise for multiple reasons.
5. Spring Boot Actuator has an **audit framework** and `AuditEventRepository`; its docs describe default events including authentication success/failure and access-denied exceptions. `InMemoryAuditEventRepository` is suitable for experimentation, **not as durable production history**.
6. **Spring Security does not automatically record an immutable versioned history of every role/ACL/policy edit in your application database.** Permission-update paths must emit application-owned business events tied to transactions and durable storage.

High-level flow:

~~~text
                     SECURITY DECISION PATH
HTTP -> Authentication -> AuthorizationFilter / Method Authorization
                                      |
                               ALLOW or DENY
                                      |
                          Authorization event/audit sink
                                      |
                   Not inherently a permission change

                     PERMISSION CHANGE PATH
Admin UI / IAM / Policy deploy -> authentication + admin permission check
                                      |
                               update role/ACL/policy
                                      |
                             commit + audit/outbox
                                      |
                            Permission-change history
~~~

Do not assume every filter runs exactly once per business action. One request can undergo multiple authorization checks (request + method + object), redirects/dispatches, retries, or async processing. To report "how many times users accessed invoices", define the **counting unit** and deduplication keys (`eventId`, `requestId`, `decisionPoint`).

## 5. Standalone Java 17 Example: One Timeline, Two Audit Ledgers

The following program **runs on JDK 17+** with no Spring or database required. It simulates access decisions against the current permission set, stores access audits, and stores history for each grant change in two record sets that are **immutable at write time**. The goal is to illustrate what data to store and how permission versions explain decisions, not to provide a production IAM system.

File `AuditTimelineDemo.java`:

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AuditTimelineDemo {

    enum Decision { ALLOW, DENY }

    record AccessAudit(
            Instant time,
            String requestId,
            String principal,
            String resource,
            String permission,
            Decision decision,
            long policyVersion) {
    }

    record PermissionChange(
            Instant time,
            String changeId,
            String operator,
            String target,
            String permission,
            boolean before,
            boolean after,
            long versionBefore,
            long versionAfter,
            String reason) {
    }

    private final Map<String, Set<String>> grants = new HashMap<>();
    private final List<AccessAudit> accesses = new ArrayList<>();
    private final List<PermissionChange> changes = new ArrayList<>();
    private long policyVersion = 1;

    private static Instant at(String value) {
        return Instant.parse(value);
    }

    private void check(String requestId, String principal,
                       String resource, String permission, String time) {
        boolean allowed = grants.getOrDefault(principal, Set.of())
                .contains(permission);

        accesses.add(new AccessAudit(
                at(time), requestId, principal, resource,
                permission, allowed ? Decision.ALLOW : Decision.DENY,
                policyVersion));
    }

    private void changeGrant(
            String changeId, String operator, String target,
            String permission, boolean grant, String reason, String time) {
        Set<String> beforeSet = grants.getOrDefault(target, Set.of());
        boolean before = beforeSet.contains(permission);

        if (before == grant) {
            return; // No state change; consider auditing ATTEMPT separately.
        }

        Set<String> next = new HashSet<>(beforeSet);
        if (grant) {
            next.add(permission);
        } else {
            next.remove(permission);
        }

        long previousVersion = policyVersion;
        grants.put(target, Set.copyOf(next));
        policyVersion++;

        changes.add(new PermissionChange(
                at(time), changeId, operator, target, permission,
                before, grant, previousVersion, policyVersion, reason));
    }

    private void printReports() {
        System.out.println("=== ACCESS AUDIT ===");
        for (AccessAudit a : accesses) {
            System.out.printf(
                    "%s req=%s principal=%s resource=%s perm=%s decision=%s version=v%d%n",
                    a.time(), a.requestId(), a.principal(),
                    a.resource(), a.permission(), a.decision(),
                    a.policyVersion());
        }

        System.out.println("=== PERMISSION HISTORY ===");
        for (PermissionChange c : changes) {
            System.out.printf(
                    "%s change=%s by=%s target=%s perm=%s %s->%s version=v%d->v%d reason=%s%n",
                    c.time(), c.changeId(), c.operator(), c.target(),
                    c.permission(), c.before(), c.after(),
                    c.versionBefore(), c.versionAfter(), c.reason());
        }
    }

    public static void main(String[] args) {
        AuditTimelineDemo demo = new AuditTimelineDemo();

        // Initial v1 state already existed before the simulation.
        demo.grants.put("alice", Set.of("INVOICE_READ"));

        demo.check("req-101", "alice", "invoice:42", "INVOICE_READ",
                "2026-01-01T10:00:00Z");
        demo.check("req-102", "bob", "invoice:42", "INVOICE_READ",
                "2026-01-01T10:01:00Z");

        demo.changeGrant("chg-201", "admin", "bob", "INVOICE_READ",
                true, "T-42", "2026-01-01T10:02:00Z");
        demo.check("req-103", "bob", "invoice:42", "INVOICE_READ",
                "2026-01-01T10:03:00Z");

        demo.changeGrant("chg-202", "admin", "bob", "INVOICE_READ",
                false, "T-99", "2026-01-01T10:04:00Z");
        demo.check("req-104", "bob", "invoice:42", "INVOICE_READ",
                "2026-01-01T10:05:00Z");

        demo.printReports();
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac --release 17 AuditTimelineDemo.java
java AuditTimelineDemo
~~~

Standard output (fixed timestamps, independent of system clock):

~~~text
=== ACCESS AUDIT ===
2026-01-01T10:00:00Z req=req-101 principal=alice resource=invoice:42 perm=INVOICE_READ decision=ALLOW version=v1
2026-01-01T10:01:00Z req=req-102 principal=bob resource=invoice:42 perm=INVOICE_READ decision=DENY version=v1
2026-01-01T10:03:00Z req=req-103 principal=bob resource=invoice:42 perm=INVOICE_READ decision=ALLOW version=v2
2026-01-01T10:05:00Z req=req-104 principal=bob resource=invoice:42 perm=INVOICE_READ decision=DENY version=v3
=== PERMISSION HISTORY ===
2026-01-01T10:02:00Z change=chg-201 by=admin target=bob perm=INVOICE_READ false->true version=v1->v2 reason=T-42
2026-01-01T10:04:00Z change=chg-202 by=admin target=bob perm=INVOICE_READ true->false version=v2->v3 reason=T-99
~~~

At version `v1`, `bob` lacked permission. After history `chg-201` was recorded and the version moved to `v2`, check `req-103` became ALLOW. Once `chg-202` revoked the permission, `req-104` returned to DENY. **You cannot prove the two permission edits from the four access events alone**, and **you cannot tell whether `bob` actually read the resource from the two change events alone**.

Limitations intentionally kept clear in this simulation:

- `changeGrant` is private and invoked from hardcoded calls, **without checking admin permissions**. Production code must verify operator, approver, and scope before committing.
- The logs and grants live only in RAM; lost when the process stops, with no transactions, integrity protection, or multi-instance coordination.
- `policyVersion` increments only for simulated grant changes; real systems need comprehensive versioning covering role definitions, policies, ACLs, and external data sources.
- `check` records the **decision**, not proof that the invoice document returned HTTP 200 or was successfully read.
- Initial permission seeding emits no history event in this example; real systems need a timestamped, sourced baseline to reconstruct full state.

## 6. Practical Integration with Spring Security Authorization Events

For Spring Security 6.x/7.x, Spring provides `AuthorizationEventPublisher` and `SpringAuthorizationEventPublisher`. The example below is a **configuration snippet inside a Spring Boot application** (not a standalone JDK program). It illustrates how to observe **permission denials**:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Configuration
class AuthorizationAuditConfiguration {

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher publisher) {
        return new SpringAuthorizationEventPublisher(publisher);
    }
}

@Component
class DeniedAuthorizationObserver {

    @EventListener
    void onDenied(AuthorizationDeniedEvent<?> event) {
        Authentication auth = event.getAuthentication().get();
        String principal = auth == null ? "unknown" : auth.getName();

        // Local observation only; replace with an audit sink with schema, protection, and durability.
        System.out.println("AUTHORIZATION_DENIED principal=" + principal);
    }
}
~~~

For method checks to take effect, the application must enable `@EnableMethodSecurity` when using `@PreAuthorize`/`@PostAuthorize`. For request authorization, configure `SecurityFilterChain` and `authorizeHttpRequests` as needed. **Do not casually log `event.getObject().toString()`**: the object contains method/request details, arguments, or sensitive data, and is not always a safely storable resource identifier.

The example above prints only the principal name to demonstrate event publication. A **production access audit record** also needs request/correlation IDs, standardized action and resource, tenant, reason code, and policy version; those must be enriched at a point with full context. A username alone is not enough to trace an incident. Also check actual execution paths: custom DENYs in business services do not automatically emit Spring events if your code handles them without using `AuthorizationManager` or publishing appropriate events.

### Why Can't You Rely Solely on AuthorizationDeniedEvent?

- The default publisher primarily records **denials**. ALLOW decisions can also matter (e.g., bulk exports or viewing PII), but you must choose a deliberate recording strategy because event volume can be very large.
- One request can be denied across multiple layers; do not assume **one event = one HTTP request**. Use decision points and correlation IDs for business-level deduplication.
- Authentication errors (`BadCredentialsException`) usually occur before authorization. You need a corresponding authentication audit system to investigate wrong passwords, account lockouts, or invalid tokens.
- An ALLOW decision does not say the action succeeded; to know whether a file finished downloading, funds transferred, or a record changed, you need application/business outcomes.
- `AccessDeniedHandler` only handles the HTTP response according to policy; seeing 403 in gateway access logs does not replace `policyVersion`, `reasonCode`, or effective permissions.
- Spring events are not automatic evidence of edits to role, ACL, or policy tables in the database. Those changes need dedicated business events.

### Where Does Spring Boot Actuator AuditEventRepository Fit?

Spring Boot Actuator describes auditing capabilities for authentication success/failure and access-denied exceptions when audit infrastructure is enabled; you can use `AuditEventRepository` or publish `AuditApplicationEvent` for custom business events. However, if the goal is **verifiable permission-change history**, design appropriate schemas/transactions and durable storage. `InMemoryAuditEventRepository` does not survive restarts and is unsuitable as long-term production evidence. Actuator endpoints must be secured separately and never exposed publicly to regular users.

## 7. Storage Design: Two Tables or Two Streams, Shared Correlation Keys

A minimal SQL model can separate them:

~~~sql
-- Illustrative DDL; adapt data types to your database engine.
CREATE TABLE access_audit (
    event_id        VARCHAR(64) PRIMARY KEY,
    occurred_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    principal_id    VARCHAR(128) NOT NULL,
    tenant_id       VARCHAR(128),
    action          VARCHAR(128) NOT NULL,
    resource_type   VARCHAR(128) NOT NULL,
    resource_id     VARCHAR(128) NOT NULL,
    decision        VARCHAR(8) NOT NULL,
    reason_code     VARCHAR(128),
    policy_version  VARCHAR(128),
    request_id      VARCHAR(128)
);

CREATE TABLE permission_change_audit (
    change_id       VARCHAR(64) PRIMARY KEY,
    occurred_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    effective_at    TIMESTAMP WITH TIME ZONE,
    operator_id     VARCHAR(128) NOT NULL,
    target_type     VARCHAR(64) NOT NULL,
    target_id       VARCHAR(128) NOT NULL,
    change_type     VARCHAR(64) NOT NULL,
    before_json     TEXT,
    after_json      TEXT,
    version_before  VARCHAR(128),
    version_after   VARCHAR(128),
    reason          VARCHAR(256),
    ticket_id       VARCHAR(128),
    result          VARCHAR(32) NOT NULL
);
~~~

The DDL above omits indexes/partitioning, tenant scoping constraints, encryption, TTL, policy version lineage, cryptographic integrity, and table access rights; it is a **structural example**, not a production schema. Sensitive resources may prohibit storing raw resource IDs; substitute internal IDs or pseudonyms per your threat model. Never turn audits into a full replica of personal data.

**Correlation matters more than "shoving everything into one table":**

- From access events, read `principal_id`, `resource_id`, `action`, timestamp, `policy_version`, and `request_id`.
- From permission changes, read `target_id`, target scope, `version_after`, and `effective_at`.
- From the policy store, retrieve the configuration/role mapping active at that version.
- Inspect context affecting permissions: tenant, ownership, attributes, token scopes, policy rollouts, caches, and validity windows.
- For data-leak or privilege-escalation incidents, reconcile **when permission was granted**, **when permission was used**, and **when the business action completed**.

Do not join solely on mutable `username` strings, and do not assume causation merely from close timestamps. Use immutable identifiers, versions, causation/correlation IDs, and transaction/deployment evidence.

## 8. Recording Permission-Change History at Transaction Time

Changing permissions is a high-privilege operation. The flow should be:

1. Operator logs in; system checks **permission to administer the target scope**; if approval applies, verify the approval decision as well.
2. Read the pre-change state with a version/ETag or appropriate lock; compute an explicit diff.
3. Validate business conditions: which roles may be granted, which tenant, expiration, and dual-control rules if required.
4. In the same transaction as the permission change, persist the **permission-change audit** or **transactional outbox** containing full before/after, version, operator, and reason. Only on successful commit is it `APPLIED`.
5. If using an outbox, the consumer forwards events to an immutable audit store and handles duplicates by `changeId`; retries must not create phantom extra "grants".
6. After commit, handle session/token/cache/policy invalidation; record effective time or activation/version to explain timing gaps.
7. As required, separately record rejected **attempts**, validation failures, or failed admin requests with `result=REJECTED`, never conflating them with applied changes.

**Dual-write risk:** if you commit the database first and then `publishEvent` to a broker and the process crashes in between, history can lose critical changes. Transactional outbox/CDC or inserting the audit within the same database transaction are common ways to close this gap. An in-memory `@EventListener` is not equivalent to durable storage or an "exactly once" guarantee.

**Current permissions are not historical permissions.** The current `user_role` table only answers "permissions now"; explaining yesterday's ALLOW requires snapshots/diffs/versions and time validity. If storing `before`/`after` as JSON, include a schema version, redaction rules, and readability across policy format changes.

## 9. Mandatory Audit Protections

**Integrity and Anti-Tampering**

- Prefer append-only; separate audit edit/delete rights from role-granting rights. Application permission admins must not implicitly have rights to erase their own tracks.
- Enforce role-based access: operations sees aggregate metrics; security auditors can view events needed for investigations; audit export may require approval.
- Add immutable/WORM storage, hash chaining or signatures, storage versioning, and external timestamps depending on compliance requirements; do not assume an unprotected append-only table is tamper-proof.
- Define backups, retention, legal hold, and reconciliation between source-of-truth and audit sink. Alert on audit-sink failures; for dangerous grant operations, have fail-closed policies or verified durable outboxes.

**Privacy and Data Minimization**

- Never record passwords, access/refresh tokens, API keys, cookies, full JWTs, raw request bodies, or unnecessary PII. Be careful logging URLs containing tokens, query strings, or object dumps.
- Use fixed reason codes like `MISSING_ROLE`, `OUT_OF_SCOPE`, or `POLICY_CONDITION_FALSE` instead of arbitrary exception messages that can leak internals.
- Mask/pseudonymize IDs when needed, encrypt at rest and in transit, cap retention, and enforce deletion/anonymization under applicable regulations. Audits are themselves data that must be protected.
- Use UTC timestamps with clear formatting, synchronized clocks, and distinguish `occurredAt`, `ingestedAt`, and `effectiveAt`. Queue lag must not cause wrong ordering conclusions.
- In multi-tenant setups, store tenant/scope and enforce cross-tenant checks when querying audits; never let one tenant's audit viewer see another tenant.

**Completeness, Reliability, and Cost**

- Choose ALLOW audit levels by risk: DENY events, admin actions, sensitive data access, and high-impact operations are usually worth keeping; recording every `permitAll` on static assets creates useless volume.
- For very high decision volumes, use async sinks with bounded queues, retries, backpressure, and dropped-event alerts. Never silently drop mandatory event types.
- Stamp the true policy/entitlement version at decision time; never retroactively update old records with the current version.
- One request may need two events: **decision** and **business outcome**; avoid claiming an operation completed merely because permission was granted.
- In distributed systems, standardize `eventId`, `traceId`, and `serviceId`; define the source of truth clearly to avoid double-counting when both gateway and service log the same request.

## 10. Incident Analysis Across Both Audit Dimensions

**Scenario A: A user was previously DENYed, then ALLOWed on the same resource.**

First pull access events by principal/resource/time. Compare policy version and context, then query permission history for the subject, roles, role-permission mappings, policies, and related ACLs. If a new grant exists, verify operator, approval, ticket, `effectiveAt`, cache state, and when the permission was used. If no grant exists, inspect ownership/ABAC and deployment/feature-flag/policy conditions.

**Scenario B: An administrator is suspected of granting unauthorized permissions.**

Pull permission-change audits by operator and target; inspect GRANT/REVOKE/ROLLBACK, before–after states, approvals, and modified policies. Then query the target's access audit during the effective window to answer whether the privilege was used, on which objects, and with what DENY/ALLOW outcomes. To prove data was actually exported, correlate business outcomes/download logs rather than concluding from ALLOW alone.

**Scenario C: The system shows mass 403s after a rollout.**

Group access DENYs by resource/action/service/policy version before and after deployment. Check permission changes and policy deployment history. Do not assume a 403 spike came from revoked permissions: it could be security matcher configuration, missing authorities in tokens, broken ACL lookups, CSRF, or unavailable policy services. Check authentication and infrastructure logs as needed.

**Scenario D: Claiming "no one has used the new permission yet".**

History only confirms the permission was granted; access auditing must cover **every path where the permission can be used** (UI/API/export/batch/message consumer). If granted events are disabled or sampled, you cannot conclude "unused" from missing events. Evaluate telemetry coverage and verify retention before making an audit claim.

## 11. Essential Test Scenarios

| Scenario | Access audit must show | Permission history must show |
| --- | --- | --- |
| User reads a permitted resource | ALLOW with exact resource, action, policy version | No permission change generated merely from a read |
| User reads a blocked resource | DENY, principal, and safe reason code | No grant/revoke generated |
| Admin successfully grants permission | The admin action itself has appropriate decision/outcome | GRANT or policy diff, before/after, operator, version, approval |
| Underprivileged admin attempts to grant | DENY for the admin action | No `APPLIED` event; optional separate `REJECTED ATTEMPT` |
| Rollback/revoke | Subsequent accesses reflect the correct version | REVOKE/ROLLBACK with old/new version and reason |
| DB commit fails | Admin operation not reported as successful | No false `APPLIED` event recorded |
| Broker temporarily down | Mandatory audits not silently lost | Outbox/retries ensure redelivery without duplication |
| Stale token holds claims from before revoke | Decision records actual version/context used | History still shows revoke committed and `effectiveAt` |
| Multiple requests share requestId due to retries | Counted per `eventId`/decision point per contract | Permission change carries `changeId` for idempotency |
| Admin edits role definition instead of user-role | Subsequent accesses use matching policy/role version | Diff on role definition, not fabricating a user-role assignment |

Key assertions: events **leak no secrets**, timestamps are never rewritten, `before` is never overwritten with current state, ALLOW events are not mistaken for business success, every committed change has a matching audit, and replays produce no logical duplicates.

## 12. Common Mistakes and How to Avoid Them

1. **Using login history as an access audit.** `AuthenticationSuccessEvent` proves an authentication method succeeded, not that access to `invoice:42` was granted.
2. **Using 403 in access logs as complete authorization evidence.** A 403 lacks policy, role snapshots, or structured reasons; one request can be blocked at multiple layers.
3. **Using current permissions to explain past decisions.** ACLs/roles may have changed; you need effective timestamps, policy versions, and historical snapshots.
4. **Recording permission changes only when the admin UI clicks "Save".** Data imports, batch scripts, migrations, IAM syncs, external policy rollouts, and auto-expirations also change permissions.
5. **Writing permission-change events before commit.** If the transaction rolls back, history becomes false. Tie audits/outbox to the transaction and separate attempts from applied changes.
6. **Omitting operator or approver.** Recording only the target user cannot answer who granted the privilege and why.
7. **Logging whole `Authentication` or full HTTP requests.** Can contain credentials, PII, claims, and session IDs; extract only needed fields and apply redaction.
8. **Uncontrolled enabling of all ALLOW events.** Causes log floods, higher costs, and risk of losing critical events; define audit levels based on data sensitivity.
9. **Conflating DENY with business failure.** Access ALLOW followed by a controller 500 is not a DENY; record outcomes separately.
10. **Treating `@EventListener` or `InMemoryAuditEventRepository` as immutable auditing.** You need durable storage, retention, backpressure, authorization, and integrity checks.
11. **Auditing only at the API gateway.** The gateway lacks object- and method-level permission visibility; emit events at actual decision points.
12. **Not versioning role-definition changes.** Knowing a user held `REPORT_VIEWER` without knowing what that role permitted on the day of an incident.
13. **Using the audit ledger as the live authorization system.** The policy engine should read governed live permission sources; audits prove history and enable reconstruction, and may feed projections without replacing the transactional source of truth.

## 13. Mastery Checklist

- [ ] Can explain: **Access audit = permission check/usage**; **permission history = change in grant/rule state**.
- [ ] Distinguish authentication events, authorization decisions, HTTP responses, and business outcomes.
- [ ] Know Spring Security has `AuthorizationDeniedEvent`, granted events are off by default, and what must be built to capture sensitive ALLOWs.
- [ ] Design minimal data fields for each stream, especially operator vs. target and before/after.
- [ ] Reconstruct a historical DENY/ALLOW using real principal, resource, context, time, and policy version.
- [ ] Record permission changes tied to commit/outbox; idempotent retries; never conflate failed attempts with applied changes.
- [ ] Protect logs against unauthorized modification/deletion and avoid storing unnecessary credentials/PII.
- [ ] Write tests proving permission changes produce audits, accesses produce decisions, and the two event types stay distinct.
- [ ] Never conclude "permission unused" when ALLOW event coverage is missing.

### Official References

- Spring Security — Authorization Events: https://docs.spring.io/spring-security/reference/servlet/authorization/events.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Boot Actuator — Auditing: https://docs.spring.io/spring-boot/reference/actuator/auditing.html
