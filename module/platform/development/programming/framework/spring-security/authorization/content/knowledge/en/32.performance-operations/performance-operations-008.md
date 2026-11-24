# Reviewing Accumulated Permissions, Privileged Accounts, and Expiration Policies

## 1. Why Review Authorization in a Running System?

Access rights do not stay static after a user logs in or after initial deployment. Across department transfers, project assignments, temporary grants, inherited roles, and admin access for incident response, an identity can accumulate far more permissions than its current job requires. Previously valid grants can also expire yet remain present in a session, token, cache, or another permission source.

Authorization review is the operational practice of **verifying which permissions are actually effective**, comparing them against current business needs and policies, deciding whether to keep/reduce/revoke, and verifying the changed permissions on actual request paths. For Spring Security, merely seeing `ROLE_ADMIN` or `REPORT_EXPORT` in `Authentication.getAuthorities()` is not the whole answer. The system may also use role hierarchies, groups, object-level grants, tenants, ACLs, time bounds, and business conditions.

Three operational goals of this lesson:

1. **Privilege accumulation:** detect excess permissions, duplicate sources, permissions lacking justification, and forgotten inheritance paths.
2. **Privileged accounts:** audit who can perform sensitive operations, when they use them, how they are protected, and whether admin rights can be revoked without unintended disruption.
3. **Expiration policies:** verify grants, exceptions, temporary permissions, and policies with effective/expiration dates; guarantee expired permissions are actually rejected at the API regardless of whether a cleanup job has run yet.

This lesson focuses on **Spring Security authorization in operations**. Authentication verifies identity, whereas authorization decides what that identity may do, on which objects, in which context, and at what time. Succeeding at login or holding a valid token does not imply permission to perform an action.

## 2. Concepts That Must Be Separated

| Concept | Meaning | Risk When Misunderstood |
| --- | --- | --- |
| Principal | The human, service, job, or admin identity acting | Shared accounts, inability to trace accountable individuals |
| Role | Permission grouping such as `ROLE_ANALYST`, `ROLE_ADMIN` | Assuming an assigned role only holds permissions explicitly named on that role |
| Authority | Permission string Spring Security uses for decisions, e.g. `REPORT_READ` | Treating session authorities as perpetually valid over time |
| Role hierarchy | Permissions/roles inherited via configuration | Revoking a child role while the permission still comes from a parent role |
| Grant | A permission issuance with source, scope, status, validity dates, approver | Looking only at the final permission without knowing which source to revoke |
| Effective permission | What is actually allowed after applying all conditions | Summing all direct and inherited rights while ignoring deny, scope, or expiration |
| Scope | Allowed objects, resources, projects, tenants, or environments | Turning a document-scoped grant into system-wide permission |
| Privileged account | Identity capable of administration, sensitive data access, or security changes | Auditing it like an ordinary user account |
| Time-bound grant | Permission with `valid_from` and/or `expires_at` | Failing to check expiration timestamps on the request path |
| Review/attestation | Resource owner or delegate confirming the need for access | Mistaking "opened the report" for "reviewed/revoked" |

**Accumulated permissions differ from effective permissions.** A person may have three sources granting `REPORT_READ`, yet only one remains valid for reports in tenant A. Conversely, revoking one source may **not** remove access if the other two sources still allow it. Reviews must inspect both **grant pathways** and **the final decision outcome**.

Example limitation: if the system has both `ALLOW` and `DENY`, precedence must be explicitly designed. Many applications use an allow-only model where "no allow ⇒ deny"; some have explicit deny overriding allow; some evaluate via a policy engine. Never assume Spring Security automatically merges database grants under a precedence rule the application has not implemented.

## 3. From Assigned Rights to Actually Effective Rights

Suppose these relationships exist:

```text
alice
 ├── direct: REPORT_READ, scope=project-7
 ├── group: project-7-reviewers
 │    └── role: ROLE_ANALYST
 │         ├── REPORT_READ, scope=project-7
 │         └── REPORT_EXPORT, scope=project-7, expires_at=2026-05-01T00:00:00Z
 └── temporary grant: REPORT_EXPORT, scope=project-7, expires_at=2026-04-30T12:00:00Z
```

On 2026-05-02 UTC, Alice still has read access on project 7 from at least two sources, yet **no longer has export permission** from the two expired time-bound grants. If another parent role still contains `REPORT_EXPORT` without an expiration, export may still be allowed: that is a privilege-accumulation review finding.

A conceptual evaluation expression:

```text
ALLOW(subject, action, resource, now, context)
    = authenticated(subject)
      AND functional_permission(subject, action)
      AND valid_grant_or_policy(subject, action, resource, now, context)
      AND resource_constraints_hold(resource, context)
      AND NOT explicit_deny_if_policy_uses_it
```

Where:

- `functional_permission` is the functional permission accepted by the application, such as `REPORT_EXPORT`.
- `valid_grant_or_policy` may need to inspect inherited roles, ownership, tenant, groups, and direct grants; revoked/expired grants must not count.
- `resource_constraints_hold` checks resource state (locked, deleted, internal-only, belonging to tenant, etc.).
- With role hierarchies, outcomes depend on the hierarchy configuration applied at the **decision point**. Do not assume every place in the application uses the same hierarchy unless configured consistently.

**Key property of expiration:** a simple, testable convention is `valid_from <= now < expires_at`; start **inclusive**, end **exclusive**. If `expires_at` is null, interpret as "no automatic expiration date" per policy; periodic review is still required. Store and compare using `Instant`/UTC; use the reviewer's timezone only for display.

## 4. Permission Source Map: What to Collect During a Review

You cannot conclude "what permissions Alice currently holds" from a single user-role table. Build a **sourced and scoped inventory**:

| Data Group | Required Fields | Review Questions |
| --- | --- | --- |
| Identity | stable principal ID, human/service/admin type, status, owner, tenant | Is the account still active and does someone own accountability? |
| Direct grants | permission/role, resource/scope, grantor, justification, approval ticket | Why does this permission exist? |
| Inherited rights | group memberships, role hierarchy, nested groups, IdP/SCIM source | Through which pathways does the permission arrive? |
| Time-bound grants | `valid_from`, `expires_at`, approval state, exceptions | Already expired, expiring soon, or extended outside process? |
| Admin rights | admin scope, ability to alter IAM/policy, break-glass accounts | Are there unnecessary standing admins? |
| Usage signals | last sign-in, last privileged action, last authorized use, environment | Is the permission genuinely needed for current work? |
| Decision history | review date, reviewer, decision, evidence, next review, action ticket | How far has confirmation and remediation progressed? |
| Enforcement path | application role mapping, Spring method checks, caches, sessions, JWT claims | After changing a grant, does the API deny immediately? |

Sources typically span IdP/SSO, HR systems, group directories, database ACLs, app configs, token issuers, API gateways, job schedulers, and audit logs. When aggregating, keep stable ID keys, uniform timestamps, policy versions, provenance, and tenant scopes. Never equate "same email" with "same principal" without verifying identity binding.

**Do not infer that an infrequently logged-in user automatically has unneeded permissions.** Some emergency-response accounts are meant to be used rarely. For those accounts, low activity is a cue to verify controls and accountability, not a reason to delete blindly.

## 5. Periodic and Event-Driven Review Workflow

An operational cycle can run as follows:

1. **Freeze snapshot:** record timestamp, sources, and policy version; collect all direct + inherited + scope + expiration data. Missing data reports must be marked "unverified," never assumed safe.
2. **Compute effective permissions:** normalize principal/action/resource/tenant, expand role graphs per active configuration, and apply expirations/states at the review timestamp. Retain **all grant pathways** for traceability.
3. **Prioritize by risk:** focus first on admin accounts, IAM/policy modification rights, bulk exports, sensitive data, cross-tenant rights, non-expiring grants, and departing personnel.
4. **Assign authorized reviewers:** resource owners confirm business need, technical owners confirm operational impact, and IAM/permission admins execute changes. Never let beneficiaries self-approve their own special privileges without independent oversight.
5. **Decide:** keep with justification, narrow scope, set expiry, revoke, convert to JIT, or request more evidence. Record decisions per grant or justified grant group; retain change tickets.
6. **Execute revocation:** update canonical sources, sync IdP/app, handle caches and sessions/tokens as needed, and check whether inherited permissions still leave an alternate path.
7. **Verify by behavior:** a request that should be denied must actually be denied. Test both data reads and writes/mutations, rather than just looking at a `REVOKED` row in a table.
8. **Close the review cycle:** store reviewer, completion timestamp, evidence, active exceptions, next review schedule, and remaining backlog.

Events that should trigger out-of-band reviews: offboarding/role change; project completion; temporary grant expiration; role hierarchy edits; admin elevation; secret rotation; security incidents; policy engine upgrades; IdP claim-mapping changes; discovery of cross-tenant access.

**Operational reality:** large permission volumes should be tiered by sensitivity. For instance, admin rights are reviewed more frequently than internal read access; exact cadence numbers must follow internal standards and compliance requirements rather than any default cadence imposed by Spring Security.

## 6. Reviewing Admin and Privileged Accounts

Privileges are capabilities with major impact: editing policies, managing users/roles, accessing audit logs, viewing secrets, configuring production, bulk-exporting data, running migrations, or disabling controls. A role named "admin" does not define the risk by itself; list **actual permissions**.

### 6.1. Account Types to Separate

- **Human admin:** an individual using a dedicated identity for administrative tasks, with clear accountability and access trails.
- **Service account:** applications/jobs using technical identities; needs an owner, narrow API/scope limits, credential management, and rotation/expiry.
- **Break-glass account:** used when normal login/admin workflows are disrupted; needs explicit purpose, recovery capability, tight access controls, auditing, and periodic testing.
- **Delegated admin:** administers a specific tenant, project, or group; never equivalent to a global superuser.

For each account, check at minimum: owner, purpose, environment, effective rights, last intentional use, MFA/step-up controls where applicable, grant pathway, expiration, revocation procedure, activity logs, and separation of duties.

### 6.2. Standing Privileges vs. Just-in-Time Access

`Standing admin` is long-lived, always-on admin access. `Just-in-time (JIT) access` grants temporary access per approved request with explicit scope, purpose, and expiration. JIT reduces how long an identity holds sensitive rights, yet **does not guarantee safety by itself** if granted with overly broad scope, not revoked upon expiry, unaudited, or bypassed by another role path that always grants the same right.

A sound JIT workflow:

```text
Requester → reason/ticket → scope and approver review
          → issue grant with explicit valid_from/expires_at
          → re-check at the time of each sensitive operation
          → expiry/revoke → invalidate cache/token if needed
          → test DENY + audit review
```

Break-glass may use a separate workflow during incidents when primary approval systems are down, yet every use must still be logged, alerted, investigated post-incident, and tested for recovery. Never use a routinely shared admin account and call it break-glass.

### 6.3. Separation of Duties

An identity holding both `CREATE_PAYMENT` and `APPROVE_PAYMENT` violates separation of duties, even if each individual grant was approved by someone else. Reviews must check **conflicting permission combinations**, not just individual roles. Similarly, policy-management rights combined with audit-deletion rights is a high-risk combination.

Review acceptance criteria can include: zero ownerless accounts; zero admins outside approved scope; zero non-expiring admin grants except documented exceptions; zero unresolved toxic permission combinations; and every break-glass usage logged and reviewed.

## 7. Permission Expiration: Stored Status vs. Effective Status

States to distinguish:

| Record State | Effective at Request Time? |
| --- | --- |
| `PENDING`, not yet approved | No |
| `APPROVED`, before `valid_from` | No |
| `APPROVED`, within [`valid_from`, `expires_at`) | Yes **if** scope and all other conditions also hold |
| `APPROVED`, at or past `expires_at` | No |
| `REVOKED`, even before expiry | No |
| `APPROVED`, `expires_at = NULL` | Does not auto-expire, yet remains subject to policy, review, and revocation |

**Common bug:** running a nightly job to set `status = EXPIRED` while business-hours request handling only checks `status = APPROVED`. A grant expiring at 09:15 can remain usable until the next job run. Cleanup jobs are useful for data hygiene and reporting, whereas **the request path must evaluate the current timestamp**.

All time comparisons should use an injected `Clock` in services or a single trusted database time source, with clear conventions when clocks differ. With `Instant`, test `now == expiresAt`, 1 nanosecond before, and 1 nanosecond after. For databases with microsecond/millisecond precision, align test timestamps to actual column precision instead of expecting nanoseconds where columns do not retain them.

**Tokens do not equal grants:** an unexpired JWT `exp` does not mean the database grant has not expired. If authorities are embedded in the JWT, grant revocation may not take effect until the token expires or refreshes unless the API performs dynamic status/permission lookups, token revocation checks, or policy-version checks. Session authentication can also cache `GrantedAuthority` lists loaded at login. Review plans must specify revocation SLAs and how circulating credentials are handled.

## 8. Permission Data Design and Active-Grant Query

An illustrative schema for resource-scoped permissions:

```sql
CREATE TABLE authorization_grant (
    grant_id        BIGINT PRIMARY KEY,
    principal_id    VARCHAR(100) NOT NULL,
    permission_code VARCHAR(100) NOT NULL,
    tenant_id       VARCHAR(100) NOT NULL,
    resource_id     BIGINT NOT NULL,
    source_kind     VARCHAR(40) NOT NULL,
    source_ref      VARCHAR(100) NOT NULL,
    status          VARCHAR(30) NOT NULL,
    valid_from      TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at      TIMESTAMP WITH TIME ZONE NULL,
    granted_by      VARCHAR(100) NOT NULL,
    approved_by     VARCHAR(100),
    justification   VARCHAR(500),
    reviewed_at     TIMESTAMP WITH TIME ZONE NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL
);
```

This is an **illustrative SQL schema for RDBMS supporting `TIMESTAMP WITH TIME ZONE`** (such as PostgreSQL), not copy-paste DDL for every database. Add constraints like `expires_at > valid_from` when expiry is non-null, constrain status to finite values, and index `(principal_id, permission_code, tenant_id, resource_id, status)` plus time fields per query patterns. Store append-only grants or history events for auditing; updating current state must never erase evidence of who granted and revoked access.

Query checking **an approved, resource-matched, tenant-matched, unexpired grant**:

```sql
SELECT EXISTS (
    SELECT 1
      FROM authorization_grant g
     WHERE g.principal_id = :principal_id
       AND g.permission_code = :permission_code
       AND g.tenant_id = :tenant_id
       AND g.resource_id = :resource_id
       AND g.status = 'APPROVED'
       AND g.valid_from <= :now
       AND (g.expires_at IS NULL OR g.expires_at > :now)
) AS allowed;
```

`:principal_id` and `:tenant_id` must come from trusted identity/context; `:resource_id` may come from the request but must be bound to the tenant and real policy. `:name` syntax suits named-parameter APIs like `NamedParameterJdbcTemplate`; plain `JdbcTemplate` uses `?`. Never concatenate input values into SQL.

**Important:** this query only checks direct grants materialized in the table. If sources include groups, role hierarchies, or attribute-based policies (ABAC), evaluate those at the right layer, keep a single canonical source, handle cycles and expirations, and verify scope. Do not treat the SQL above as a universal algorithm for every IAM model.

If two allow grants exist from two sources for the same resource, revoking one does not guarantee denial; tests must assert the final effective outcome. When explicit denies exist, add deny evaluation per defined policy precedence rather than `EXISTS(ALLOW)` alone.

## 9. Standalone Java 17: Detecting Accumulated and Expired Permissions

The pure-Java model below captures identity, permission, scope, grant source, and time bounds. It verifies three principles: (1) permissions are active only inside their allowed time window, (2) two overlapping sources remain two distinct grants, and (3) a JIT admin grant expires cleanly at the `expiresAt` boundary. This is a logic model and **does not replace Spring Security, database, session, or JWT checks**.

File `PermissionReviewDemo.java`:

```java
import java.time.Instant;
import java.util.List;

public class PermissionReviewDemo {
    record Grant(
            String principal,
            String source,
            String permission,
            String scope,
            Instant validFrom,
            Instant expiresAt,
            boolean approved) {

        boolean activeAt(Instant now) {
            return approved
                    && !now.isBefore(validFrom)
                    && (expiresAt == null || now.isBefore(expiresAt));
        }

        boolean allows(
                String who, String action, String target, Instant now) {
            return activeAt(now)
                    && principal.equals(who)
                    && permission.equals(action)
                    && scope.equals(target);
        }
    }

    static boolean allowed(
            List<Grant> grants, String who, String action,
            String target, Instant now) {
        return grants.stream()
                .anyMatch(g -> g.allows(who, action, target, now));
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-01-01T00:00:00Z");
        Instant reviewAt = Instant.parse("2026-05-01T12:00:00Z");
        List<Grant> grants = List.of(
                new Grant("alice", "direct",
                        "REPORT_READ", "project-7",
                        start, null, true),
                new Grant("alice", "role:analyst",
                        "REPORT_READ", "project-7",
                        start, null, true),
                new Grant("alice", "temporary",
                        "REPORT_EXPORT", "project-7",
                        start,
                        Instant.parse("2026-05-01T00:00:00Z"),
                        true),
                new Grant("ops", "jit:incident-42",
                        "POLICY_EDIT", "production",
                        start, reviewAt, true));

        long readSources = grants.stream()
                .filter(g -> g.allows("alice",
                        "REPORT_READ", "project-7", reviewAt))
                .count();
        long expired = grants.stream()
                .filter(g -> g.expiresAt() != null
                        && !reviewAt.isBefore(g.expiresAt()))
                .count();

        System.out.println("alice.read=" + allowed(
                grants, "alice", "REPORT_READ", "project-7", reviewAt));
        System.out.println("alice.export=" + allowed(
                grants, "alice", "REPORT_EXPORT", "project-7", reviewAt));
        System.out.println("ops.edit=" + allowed(
                grants, "ops", "POLICY_EDIT", "production", reviewAt));
        System.out.println("alice.readSources=" + readSources);
        System.out.println("expiredGrants=" + expired);
    }
}
```

Compile and run on JDK 17 or higher:

```bash
javac PermissionReviewDemo.java
java PermissionReviewDemo
```

Exact stdout:

```text
alice.read=true
alice.export=false
ops.edit=false
alice.readSources=2
expiredGrants=2
```

At `reviewAt = 2026-05-01T12:00:00Z`, export permission expired at 00:00; `POLICY_EDIT` hit its 12:00 expiry and is also denied. Alice still has **two sources** granting read access, so removing read access requires addressing both sources. `allowed` intentionally operates on a normalized grant list; it does not implement group recursion, explicit denies, tenant ACLs, or a policy engine. When your system uses those mechanisms, compute effective rights per the real policy and write equivalent tests.

## 10. Enforcing Expiration and Scope in Spring Security

Spring Security stores `GrantedAuthority` inside `Authentication`; authorization managers and method security use authorities for checks. In practice, object-scoped and time-bound permissions usually need a **policy service** querying current state from the database or policy engine at request time. Do not flatten thousands of per-ID permissions into thousands of `GrantedAuthority` strings loaded into the session.

### 10.1. Configuring Method Security and Clock

The example below targets Spring Boot 3.x, Spring Security 6, and JDBC-backed servlet applications. These snippets belong to **an application already configured with DataSource, authentication, and the `authorization_grant` table**, not a standalone Java file. The sample uses `authentication.name` as `principal_id`; in production, map to a stable principal subject/ID to avoid bugs on username renames.

File `AuthorizationConfiguration.java`:

```java
package com.example.authorization;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class AuthorizationConfiguration {
    @Bean
    Clock authorizationClock() {
        return Clock.systemUTC();
    }
}
```

`@EnableMethodSecurity` must be active for `@PreAuthorize` expressions to run. Injecting `Clock` lets tests swap in `Clock.fixed(...)` for time-boundary tests without changing the system clock. Endpoints still need an appropriate HTTP security filter chain (authentication, CSRF/bearer policy, etc.); method security is just one layer.

### 10.2. Policy Service Checking Live Grants

For example, receiving `reportId` and the user's tenant from a trusted component (`TenantIdentity`). Here `trustedTenant` is passed as a server-determined parameter; never accept client-asserted tenants from the body.

File `ActiveGrantPolicy.java`:

```java
package com.example.authorization;

import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("activeGrantPolicy")
public class ActiveGrantPolicy {
    private final JdbcTemplate jdbc;
    private final Clock clock;

    public ActiveGrantPolicy(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    public boolean canReadReport(
            Authentication actor, long reportId, String trustedTenant) {
        if (actor == null || reportId <= 0
                || trustedTenant == null || trustedTenant.isBlank()) {
            return false;
        }

        Instant now = clock.instant();
        Integer count = jdbc.queryForObject("""
                SELECT COUNT(*)
                  FROM authorization_grant g
                 WHERE g.principal_id = ?
                   AND g.permission_code = 'REPORT_READ'
                   AND g.tenant_id = ?
                   AND g.resource_id = ?
                   AND g.status = 'APPROVED'
                   AND g.valid_from <= ?
                   AND (g.expires_at IS NULL OR g.expires_at > ?)
                """,
                Integer.class, actor.getName(), trustedTenant,
                reportId, Timestamp.from(now), Timestamp.from(now));
        return count != null && count > 0;
    }
}
```

The SQL never trusts client data for principal/tenant; `trustedTenant` must be resolved/verified server-side rather than chosen freely by the client. In multi-tenant systems, also constrain **the actual resource** (`reports.tenant_id`) to match `trustedTenant` on reads/writes so users cannot probe IDs across tenants. The `authorization_grant` table is only one illustrative source; if roles/groups come from other sources, the policy must incorporate them in the same decision.

For simplicity, the example queries grants directly on every request, clearly demonstrating correctness on revocation. Large applications may cache results, provided keys include actor + tenant + action + resource + policy version/time, TTLs are short enough, and invalidation covers revocation/expiry. High-risk admin rights may require stricter dynamic checks.

### 10.3. Using `@PreAuthorize` at the Service and Protecting the Data Layer

A service can declare:

```java
package com.example.authorization;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ActiveGrantPolicy grants;
    private final ReportRepository reports;

    public ReportService(ActiveGrantPolicy grants,
                         ReportRepository reports) {
        this.grants = grants;
        this.reports = reports;
    }

    @PreAuthorize("""
            hasAuthority('REPORT_READ')
            and @activeGrantPolicy.canReadReport(
                authentication, #reportId, #trustedTenant)
            """)
    public ReportView readReport(long reportId, String trustedTenant) {
        return reports.loadForTenant(reportId, trustedTenant);
    }
}
```

`ReportRepository` and `ReportView` are application domain types **not defined in this snippet**, making this integration/type-level pseudocode rather than a standalone compilable program. On builds that do not preserve parameter names, enable `-parameters` or annotate with `@P("reportId")`, `@P("trustedTenant")` so SpEL resolves parameters reliably.

**Two mandatory gates**: functional authority `REPORT_READ` and an active, resource/tenant-matched grant in the policy service. `ReportRepository.loadForTenant` must also query with `WHERE id = ? AND tenant_id = ?`, rather than loading by ID alone and hoping the controller checked. For mutations, use conditional updates checking tenant/owner/status, transactions, and rechecks to prevent TOCTOU.

**Never use `hasRole('ADMIN')` as a shortcut across all resources.** An admin role may manage system operations without necessarily being allowed to view cross-tenant data or bypass separation of duties. If an administrative exception exists, express it as an explicit policy with scope, approval, expiry, and audit instead of scattering arbitrary OR conditions across code.

### 10.4. Role Hierarchy and Indirectly Assigned Rights

Spring Security supports role hierarchies; for example `ROLE_ADMIN > ROLE_ANALYST` lets admins inherit analyst permissions at authorization points configured with that hierarchy. However, **inherited permissions do not automatically carry database grant time limits**. Where scope/expiry matters, ensure expiration policies are enforced on the service path too.

Reviews must capture hierarchy configs, detect cycles or misconfigurations, compute role closures, and record **source pathways** for each permission. Removing direct `ROLE_ANALYST` from a user can still leave `ROLE_ADMIN` providing the same rights. After modifying a hierarchy, run regression tests on all related endpoints because effective permissions shift for many users simultaneously.

Default note: `hasRole("ADMIN")` normally matches an authority prefixed with `ROLE_ADMIN`; `hasAuthority("ROLE_ADMIN")` matches the literal string, whereas `hasAuthority("REPORT_READ")` adds no prefix. Verify prefix/role-hierarchy configuration at runtime rather than guessing from permission table names.

## 11. Testing Expiration, Revocation, and Admin Controls

Good tests include both current state and **time** and **grant source**. Merely asserting a `status = REVOKED` column after calling a revocation API is insufficient; send real requests proving access is gone.

### 11.1. Scenario Matrix

| Scenario | Minimum Expectation |
| --- | --- |
| Approved and unexpired grant | Allowed if scope, tenant, authority, and other policies hold |
| `now = valid_from` | Allowed at start boundary |
| `now` immediately before `expires_at` | Active right up to the end boundary |
| `now = expires_at` | Denied |
| `now` after `expires_at` | Denied even before any cleanup job marks it expired |
| `REVOKED` status before expiry | Denied promptly per published SLA |
| Two grants for same permission, one revoked | Access may remain via second grant; report must explain remaining path |
| Direct role removed while parent role remains | Inherited permission may persist; hierarchy must be addressed |
| JIT admin grant expired | New admin actions denied; in-flight work follows transaction contract |
| Account disabled/terminated | Cannot start new sessions; existing sessions/tokens honor revocation SLA |
| Unexpired JWT while grant is revoked | Sensitive permissions deny via chosen refresh/recheck/revocation mechanism |
| Tenant transfer / owner change | Cannot access old tenant's data outside scope |
| Stale policy cache | Expiration/invalidation truly takes effect; never exceeds approved TTL |
| Ownerless service account or expired credential | Flagged and handled without gaps |
| Database/policy service failure | Deny/fail closed on sensitive paths; audit infrastructure reason properly |

Actively enforce permissions **at access time**. For long-running flows (batch or async), decide whether permissions are locked at submission, at execution, or both. For high-risk operations, revocation while a job is queued must have defined behavior and tests.

### 11.2. Using a Fixed Clock for Boundary Tests

JUnit 5 example for pure Java logic using the demo classes:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class GrantExpiryTest {
    @Test
    void expiryIsExclusive() {
        Instant from = Instant.parse("2026-01-01T00:00:00Z");
        Instant until = Instant.parse("2026-05-01T12:00:00Z");
        PermissionReviewDemo.Grant grant =
                new PermissionReviewDemo.Grant(
                        "ops", "jit:incident-42",
                        "POLICY_EDIT", "production",
                        from, until, true);
        assertTrue(grant.activeAt(until.minusNanos(1)));
        assertFalse(grant.activeAt(until));
        assertFalse(grant.activeAt(until.plusNanos(1)));
    }
}
```

This requires JUnit 5 on the test classpath and `PermissionReviewDemo.java` in the same package (or default package as in the standalone example). `Instant` retains nanosecond precision in memory; in DB integration tests, match the precision supported by columns and drivers. With Spring, inject a `Clock.fixed(..., ZoneOffset.UTC)` bean for tests or a mutable test `Clock`; avoid `Thread.sleep` to wait out expiry because it makes tests flaky.

### 11.3. Verifying Through Spring Security / HTTP

Integration tests should enable `SecurityFilterChain` and `@EnableMethodSecurity`, seed grants into the test database, call the real endpoints with principals/authorities, and verify:

- Approved, scoped, unexpired request ⇒ succeeds and returns only matching-tenant data.
- Request with same credential after `status` becomes `REVOKED` ⇒ denied; token or session handled as designed.
- Keeping `status='APPROVED'` while setting `expires_at` in the past ⇒ denied **without running any grant cleanup job**.
- Account lacking `REPORT_READ` despite an active DB grant is blocked by functional authority; account with `REPORT_READ` but wrong resource/tenant is blocked by object policy.
- When updating admin permissions, assert state changes cause no unauthorized side effects; verify audits record actor, action, resource, policy version, and decision (never secrets/tokens).

In Spring MVC, `MockMvc` can use `@WithMockUser` or `SecurityMockMvcRequestPostProcessors.user(...)` to attach authorities to requests. `@WithMockUser` alone does not verify full SSO/token issuance; if testing claims/refresh/revocation, add tests at the authentication chain or end-to-end with real test-environment credentials/tokens.

## 12. Operational Metrics and Review Evidence

Metrics measure progress, yet never replace real access evidence:

| Metric | Calculation / Interpretation |
| --- | --- |
| Expired grants still marked active | Uncleaned source rows; far more severe if the API still allows access |
| Ownerless privileged accounts | Privileged identities lacking an accountable owner |
| Standing admins | Long-lived admin identities, broken down by environment/scope |
| Multi-source grants | `(principal, permission, scope)` tuples with two or more active paths |
| Overdue reviews | Grants past their review deadline, prioritized by high risk first |
| Revocation propagation lag | Time from revocation decision until requests are actually denied |
| Token/cache exposure window | Duration permissions can linger in credentials/caches post-revocation |
| Privileged action coverage | Share of sensitive actions with complete actor/action/target/time/decision audits |
| Exception inventory | Active exceptions with clear reason, approver, and expiry |

For example, if 20 admin grants require review and 16 were attested on time, completion rate is `16/20 = 80%`. That metric **says nothing** about whether the remaining 4 grants are safe; inspect their risk and evidence. Avoid treating "zero observed uses" as proof a permission is definitely unneeded.

An audit record for a review decision can contain:

```json
{
  "reviewId": "RV-2026-0412",
  "principalId": "principal-123",
  "permission": "REPORT_EXPORT",
  "scope": "project-7",
  "grantSources": ["role:analyst", "temporary:ticket-42"],
  "evaluatedAt": "2026-05-02T09:00:00Z",
  "decision": "REVOKE",
  "reviewerId": "reviewer-55",
  "reason": "Project completed",
  "actionTicket": "IAM-482",
  "verification": "DENIED_ON_API"
}
```

This is an **illustrative data template**, not a standard Spring Security format. Separate audit records from access tokens, passwords, and sensitive payloads. Retain enough detail to trace grant origins and enforced outcomes without logging secrets, refresh tokens, or full personal profiles.

## 13. Safe Revocation and Handling Stale-Session Risk

Revocation workflows should cover all four layers:

1. **Source of truth:** IdP, user-group mappings, ACLs, or database grants are updated at the authoritative source. Updating one copy does not ensure others stay in sync.
2. **Policy calculation:** role hierarchy/ABAC is recomputed; losing one grant while keeping another can still allow access.
3. **Credentials and caches:** sessions, cached `Authentication`, JWT claims, token issuers, API gateways, distributed caches, or DataLoaders may retain stale data. Choose invalidation, short-lived tokens, policy-version checks, or dynamic lookups per SLA.
4. **Execution/evidence:** call the endpoint or run the job with the revoked identity; verify denial, no data mutation, and audit trail presence.

When destructive or policy-changing privileges need immediate revocation, merely cutting cache TTL from hours to minutes may miss the SLA. Use live grant checks or version/revocation lists at the point of action, accounting for availability when the policy store is unreachable. Systems that deny on policy-service errors (*fail closed*) need monitoring and recovery runbooks so nobody tries to bypass checks to restore service.

When revoking an admin account, audit keys, credentials, sessions, API tokens, IAM/cloud permissions, and automations running under that identity. When transferring a service account owner, assign the new owner and verify jobs keep working; never delete production accounts blindly without a handover plan.

## 14. Common Mistakes to Spot

- **Listing only direct roles:** missing groups, parent roles, tenant/ACLs, and temporary grants; fix by computing effective permissions with provenance.
- **Treating login-session authority lists as eternal truth:** authorities go stale after revocation; add refresh/recheck per SLA.
- **Relying on cleanup crons instead of request-time expiry checks:** grants expiring between cron runs stay usable; check `now < expires_at` at authorization time.
- **Extending access by setting `expires_at = null` for convenience:** creates permanent standing privileges; require approvals and review cycles.
- **Revoking one grant while missing another:** same permission arrives via role/direct/group; re-test the final effective decision.
- **Making ADMIN bypass all domain policies:** admins cross tenants or read sensitive data unnecessarily; separate privileged operations from object/field access.
- **Shared admin accounts:** audits cannot pinpoint individual accountability; use personal identities, controlled access, and separate emergency procedures.
- **Equating token expiry with grant expiry:** an unexpired token can carry revoked rights; add verifiable refresh/revocation mechanisms.
- **Comparing dates in local time and ignoring timezones:** grants expire early/late across DST or environments; store `Instant` and test boundaries.
- **Rubber-stamp reviews:** reviewer approves yet permissions never change or requests still succeed; require execution evidence and post-change tests.
- **UI-only denial:** admin buttons are hidden while the API still executes; all enforcement must live in the backend/security layer.
- **Policy caches ignoring tenant or user:** one user's permission leaks to another; include complete keys and proper invalidation.
- **Purging audit logs to save space:** loses who granted/approved/used permissions; apply intentional retention, access controls, and data minimization.

## 15. Operational Exercises and Acceptance Criteria

### Exercise A — Trace Accumulated Permissions

Given Alice holding `REPORT_READ` from both a direct grant and `ROLE_ANALYST`, answer: (1) how many **sources** currently grant read access, (2) if the direct grant is revoked, does the API still allow access, (3) which sources must change for read access to disappear completely, and (4) is a role hierarchy involved? The report must list source paths, scope, and evaluation timestamp, not just `allowed=true/false`.

### Exercise B — Time-Bounded Admin Access

Grant `POLICY_EDIT` to `ops` from 08:00 to 12:00 UTC on 2026-05-01. Test 11:59:59 is allowed and exactly 12:00 is denied. Verify denial does not depend on any cron job. Record evidence: grant ID, approver, ticket, and a denied post-expiry request.

### Exercise C — Revocation After Role Change

An account leaves a project yet still holds `REPORT_EXPORT` via a group. Simulate removing the group and calling the export API: the result must be deny. If old tokens/sessions retain the permission, state the refresh mechanism and target SLA. For service accounts, verify related jobs still work after narrowing scope and updating owner.

### Exercise D — Privileged Account Review

Compile an inventory containing human admins, service accounts, and break-glass accounts. For each, identify owner, sensitive permissions, last privileged use, expiration, MFA/approval gates, logging, recovery path, and revocation procedure. Record the decision: retain, reduce, JIT, revoke, or time-bounded exception.

**Completion criteria:** the report captures **effective** permissions and all grant sources; accounts for role hierarchies and scopes; admin accounts have owners, justifications, and controls; expired grants are denied immediately on the API path; revocations are verified via requests; timestamps use UTC with boundary tests; and review logs trace who decided what and the verified runtime outcome.

## References

- Spring Security — Authorization Architecture (`GrantedAuthority`, role hierarchy, `AuthorizationManager`): https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Method Security (`@EnableMethodSecurity`, `@PreAuthorize`): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
