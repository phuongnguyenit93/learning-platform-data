# Syncing Permissions from an Identity Provider While Keeping Business Permissions Consistent

## 1. The Problem: When the Identity Source Changes, Business Permissions Must Stay Accurate

In many Spring Security applications, users log in via a **centralized identity source** (Identity Provider, IdP) such as an organization's SSO/OIDC system. The IdP may manage whether an account is active or locked, organizational group lists, departments, and HR attributes. Meanwhile, the application manages business permissions itself: who can approve invoices, view which tenant's reports, lock orders, export data, or approve a specific monetary limit.

Problems arise when either source changes:

- An employee transfers departments and the IdP removes the **finance** group; the application still holds an old record allowing approval.
- An account is disabled in the IdP, yet an existing JWT or permission cache remains valid.
- Group synchronization from the IdP overwrites all roles in the application database, wiping out business permissions intentionally granted by an administrator.
- A revocation event arrives first, then an older delayed event arrives later and overwrites the newer state, **re-enabling permissions incorrectly**.
- A user from tenant A is synced into tenant B by mistake due to matching identities on mutable email addresses or usernames.

The goal is not "copy every role from the IdP into the application." The goal is to **define which system is authoritative for which data**, ingest changes in proper order, and compute the **effective** permission for each request from current conditions.

After this lesson, you will be able to design the IdP–application boundary, handle idempotent sync, out-of-order events, account deactivation, periodic reconciliation, stale caches/tokens, and Spring Security tests without losing business-managed permissions.

## 2. Consistency Model: Two Authorities, One Final Decision

Consider invoice approval. An employee may approve only when:

1. Identity is authenticated from the expected issuer and subject.
2. Account status in the IdP is **active** and status data is sufficiently fresh per policy.
3. The user currently belongs to the **finance** organizational group per approved mapping rules.
4. The application still holds an active **business permission invoice:approve** granted by an authorized person in the app.
5. The user belongs to the invoice's tenant.
6. The invoice is in an eligible state (for example PENDING), and limits and business preconditions are met.
7. If the account was previously disabled or a sensitive group was revoked, a **re-approval step** for prior grants occurred before restoring activity.

The decision can be expressed as:

~~~text
allowed =
    authenticated_identity_is_valid
 AND idp_account_is_active
 AND idp_group_gate_is_satisfied
 AND local_business_grant_is_active
 AND tenant_and_resource_scope_match
 AND business_preconditions_are_satisfied
 AND no_reapproval_or_security_hold_is_pending
~~~

These AND conditions illustrate **one sensitive permission**. For other features, policies may differ; for instance, public viewing may not need a local grant. However, every permission must have an explicit formula and **deny by default when any required condition is missing**.

### 2.1. Defining Who Owns Which Data

| Data | Recommended Source of Truth | Usage |
| --- | --- | --- |
| Issuer, subject, account status | IdP / identity lifecycle system | Link user and block disabled accounts |
| Org groups, departments, HR relations | IdP when organization delegates directory management | Necessary or sufficient condition for certain permission sets |
| Application identity / tenant membership | System per data contract | Defines which tenants the user belongs to |
| invoice:approve, report:export, ACL, limits | Business system | Governs operations on data and approval limits |
| Invoice owner, PENDING state, invoice tenant | Business database | Constraints on the exact target resource |
| Mapping from IdP groups to capabilities | Reviewed and tested configuration | Versioned mapping table; never infer from raw group names |
| Audit of who granted/edited/revoked local grants | Business system | Investigation and proving origin of permission decisions |

**Ownership principle:** IdP events may update account status, org groups, and IdP-owned attributes; they **must never arbitrarily overwrite** application-owned invoice:approve grants. Conversely, a local grant must never turn an IdP-disabled account into an authorized user.

If a permission is genuinely **IdP-owned** by contract (for example a group is the sole source for intranet read access), you can sync that permission directly. What matters is separating **IdP-owned** from **business-owned** permissions cleanly so neither side continuously overwrites the same roles column.

### 2.2. Identity Group Does Not Equal Business Permission

The **finance** group may only indicate the user works in the finance department. It does not necessarily authorize approving **every** invoice or every tenant. A mapping table can define:

| IdP Group | Effect in Application | Additional Permission Needed |
| --- | --- | --- |
| employees | Eligible for basic employee features | report:read where required |
| finance | Eligible to be considered for invoice permissions | local grant invoice:approve + limits |
| finance-auditors | Eligible to read financial logs | audit:read + appropriate scope |
| suspended | Locks sensitive permissions if policy uses this group | Do not allow local grants to override locked state |

Never automatically treat a group named **admin** from an unverified claim as the application's ROLE_ADMIN. Mapping tables must use an **allowlist**, canonical names, trusted issuers, and tests for unknown groups, removed groups, duplicate names, and cross-tenant boundaries.

## 3. Durable User Identification: Issuer + Subject + Tenant

In OIDC/JWT, the **sub** claim is the subject identifier issued by an issuer; the same sub across two different issuers is not guaranteed to be the same person. Therefore the identity binding key should include at least **(issuer, sub)**, while tenant-scoped permissions must attach to an explicit tenant verified against application data.

~~~text
IdP A: iss=https://idp-a.example/realms/main, sub=abc123
IdP B: iss=https://idp-b.example/realms/main, sub=abc123
         │                                      │
         └── two distinct identities ───────────┘

Local business grant:
(issuer, subject, tenant, capability, scope, status, approvedBy, version)
~~~

**Email should not be the primary key** for granting/revoking permissions: emails can change, be recycled, or collide across unnormalized sources. Usernames and display names can change too. If the application must link accounts across multiple IdPs, use a **verified account-linking process**, never auto-linking simply because two emails match.

**Tenants must never be trusted straight from the request** as proof of permission. When approving an invoice, the backend looks up the invoice to find its real tenant, then checks whether the user holds permissions in that tenant. If the system uses a tenant context from a token or header, it must still check membership and issuer boundaries.

When one employee belongs to two tenants, a local grant in tenant A **does not automatically apply** to tenant B; cache keys and unique constraints must include all relevant dimensions to prevent cross-tenant permission leaks.

## 4. Sync Pathways and Their Roles

~~~text
                    Identity Provider
          ┌────────────┼───────────────┐
          │            │               │
      SCIM / API    Webhook/event     JWT/OIDC login
          │            │               │
          └───────► Ingestion         Authenticate request
                     │                  │
           Verify source/schema         │
                     │                  │
           Inbox + version check        │
                     │                  │
         Update IdP projection          │
                     │                  │
          Outbox cache invalidation     │
                     │                  │
               Policy Service ◄─────────┘
                     │
             Business grants + ACL
                     │
              Allow / Deny
                     │
           Audit + metrics + trace
~~~

**SCIM 2.0** (RFC 7644) is a provisioning protocol for Users/Groups supporting POST/GET/PUT/PATCH/DELETE and versioning via ETag/meta.version. SCIM does not automatically convert received data into accurate business permissions; the application still must map authority sources and merge properly. ETag is typically an **opaque value used for concurrency control**—never assume it is an increasing integer for less-than/greater-than comparisons.

**Webhooks/events** propagate changes quickly but can arrive duplicated, out of order, or temporarily delayed. Ordering requires a **monotonically increasing revision/sequence per entity** or a source-guaranteed version comparison; raw timestamps are error-prone due to clock skew and retries.

**Login-time sync** can refresh groups from verified claims, yet it cannot push changes immediately while the user retains an existing session. Never rely on "waiting for the user to log in again" as the revocation control for high-risk actions.

**Periodic reconciliation** reads current identity state, compares it against the stored projection, and fixes missing/drifted records; it compensates for missed events. However, an IdP error, incomplete pagination, or temporarily missing snapshot **is not an order to mass-delete absent accounts**.

## 5. Workflow for Ingesting an Identity Change

### 5.1. Event Contract

An ideal event contains:

~~~json
{
  "eventId": "evt-000245",
  "source": "trusted-directory",
  "issuer": "https://idp.example/realms/main",
  "subject": "user-123",
  "revision": 245,
  "type": "IDENTITY_SNAPSHOT",
  "active": true,
  "groups": ["finance", "employees"]
}
~~~

This is an **internal contract example**, not a standard SCIM payload. The revision field should only be compared when the adapter has verified it actually increases **within the same issuer + subject scope**. If the provider does not guarantee ordering, use subject-partitioned queues, API ETag checks, or fetch the latest state to reconcile instead of guessing by arrival time.

**Full snapshot** events must have clear semantics for required fields. For **partial updates/PATCH**, an *omitted* groups field means **leave that field unchanged**, not "remove all groups." Only an explicit authenticated remove-groups operation means revocation. Confusing the two causes mass permission loss.

### 5.2. Step-by-Step Processing

1. **Verify source:** HTTPS/mTLS channel or webhook signature, allowed issuer, machine caller token, schema bounds, and replay protection. Never accept ordinary client-submitted JSON as an IdP event.
2. **Normalize key:** resolve issuer + sub and tenant mapping using verified rules; never join by email.
3. **Record inbox/eventId:** detect duplicates, track processing state, and link audit trails.
4. **Check ordering:** ignore stale records when deterministic revisions exist; prevent old events from overwriting newer state.
5. **Update IdP projection:** active, groups, applied version; strictly within IdP-owned fields.
6. **Apply revocation conditions:** when active=false or a high-risk prerequisite group is removed, effective permission decisions must flip to deny. Optionally flag **local grants requiring review** before reactivation.
7. **Commit transaction** and create an outbox event to invalidate caches or notify nodes. Acknowledge the event only after durable persistence.
8. **Reconcile** on schedule to repair missed events, record drift, and surface anomalies.

If the DB stores IdP state and event inbox in separate places, never ACK before committing the update and risk dropping retries. Use transactions, unique constraints, and transactional outboxes to tighten the pipeline. Cache invalidation is often asynchronous: define an **acceptable revocation latency bound** matching permission sensitivity.

### 5.3. Guarding Against Out-of-Order and Duplicate Updates

Suppose:

~~~text
revision 10: active=true,  groups=[finance]
revision 11: active=false, groups=[]
revision 9 : active=true,  groups=[finance]   ← arrived late
revision 11: active=false, groups=[]          ← replayed
~~~

Correct behavior: after revision 11, the account **stays locked**; late revision 9 and replayed revision 11 must not re-enable access. Never use "last write wins by arrival time" because late event 9 would overwrite the newest state. If two distinct sources update the same field without a unified order, define **which source is authoritative** or quarantine into conflict resolution rather than picking whichever arrived last.

Likewise, local grants have their own version/approval lifecycle. A new IdP event **does not touch businessGrant.version by default**. That is precisely how to prevent "a new group event wipes out application-granted business permissions."

### 5.4. Deletion and Deactivation

An account deletion event should be represented as a **versioned disabled/tombstone state**, avoiding hard-deleting the row so an old event cannot "recreate" it. You can retain audit records and local grants per data retention policies, while **effective access remains blocked**. If the IdP later creates a new account with a new subject, that is a different identity; never auto-attach the previous user's grants by email.

When an old account is reactivated, the system may require **re-approval** of previously held sensitive permissions. This policy must be decided jointly with business and security teams, because IdP account reactivation does not automatically mean old limits/delegations remain appropriate.

## 6. Recommended Data Model for Production Systems

You can separate at least three tables/blocks:

~~~sql
-- Illustrative SQL for logical structure; adjust data types per DB.
CREATE TABLE identity_projection (
    issuer        VARCHAR(512) NOT NULL,
    subject_id    VARCHAR(255) NOT NULL,
    active        BOOLEAN NOT NULL,
    group_data    TEXT NOT NULL,
    source_version VARCHAR(255) NOT NULL,
    observed_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (issuer, subject_id)
);

CREATE TABLE business_grant (
    grant_id      BIGINT PRIMARY KEY,
    issuer        VARCHAR(512) NOT NULL,
    subject_id    VARCHAR(255) NOT NULL,
    tenant_id     VARCHAR(100) NOT NULL,
    capability    VARCHAR(150) NOT NULL,
    grant_status  VARCHAR(30) NOT NULL,
    grant_version BIGINT NOT NULL,
    approved_by   VARCHAR(255) NOT NULL
);

CREATE TABLE identity_event_inbox (
    source_name VARCHAR(150) NOT NULL,
    event_id    VARCHAR(255) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (source_name, event_id)
);
~~~

**This is not complete production DDL:** you also need foreign keys or identity mappings, indexes by tenant/capability, unique constraints against duplicate grants, grant/revocation audit timestamps, version columns typed appropriately for the IdP, deletion policies, and encryption for sensitive fields. `source_version` is a String because ETags can be opaque; never run integer comparisons on opaque values. If the source provides genuinely monotonic revisions, store as BIGINT with version-conditional updates.

**Separated DB ownership:** event handlers write only `identity_projection` and review-required flags; business admin APIs write only `business_grant`; the policy engine **reads both** to make the final decision. The review-required state can live in `business_grant` or a separate security-status table with auditing, and must never be bypassed on re-enable.

**Audit:** log who/what/which source made the change, eventId/revision, tenant, allow/deny decision, and correlation id; avoid logging raw tokens, passwords, or unnecessary personal data. Metric tags should use bounded sets such as eventType/result, never email/sub/id due to high cardinality.

## 7. Standalone Java 17 Example: IdP Group as Necessary Condition, Business Grant as Separate Decision

The following fixture simulates a source delivering **full snapshots** with **guaranteed monotonic revisions** per key. It is a **single-threaded** educational example using in-memory Maps and Sets. It demonstrates the principles, not a production engine with transactions, persistence, or thread safety.

Policy: to approve an invoice, the user must be active, belong to the finance group, hold the local grant `invoice:approve`, match the tenant, the invoice must still be PENDING, and no re-approval review may be pending. **No IdP event ever creates a local grant automatically**.

### 7.1. Complete Java File

Create **IdentityPermissionSyncDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class IdentityPermissionSyncDemo {

    public record Key(String issuer, String subject, String tenant) {
        public Key {
            Objects.requireNonNull(issuer, "issuer");
            Objects.requireNonNull(subject, "subject");
            Objects.requireNonNull(tenant, "tenant");
        }
    }

    // Verified snapshot; revision increases within a single Key.
    public record DirectoryEvent(
            Key key, long revision, boolean active, Set<String> groups) {
        public DirectoryEvent {
            Objects.requireNonNull(key, "key");
            groups = Set.copyOf(groups);
        }
    }

    public record DirectoryState(
            long revision, boolean active, Set<String> groups) {}

    public record Invoice(String tenant, boolean pending) {}

    public static final class Engine {
        private final Map<Key, DirectoryState> directory = new HashMap<>();
        private final Map<Key, Set<String>> localGrants = new HashMap<>();
        private final Set<Key> reviewRequired = new HashSet<>();

        // Updates only IdP projection and review-required state.
        public void apply(DirectoryEvent event) {
            DirectoryState previous = directory.get(event.key());
            if (previous != null
                    && event.revision() <= previous.revision()) {
                return; // Ignore stale and replayed events.
            }

            boolean lostFinanceGroup = previous != null
                    && previous.groups().contains("finance")
                    && !event.groups().contains("finance");

            if (!event.active() || lostFinanceGroup) {
                reviewRequired.add(event.key());
            }

            directory.put(event.key(), new DirectoryState(
                    event.revision(), event.active(), event.groups()));
        }

        // Only an authorized business workflow/admin may call this method.
        public void grantLocally(Key key, String capability) {
            localGrants.computeIfAbsent(key, ignored -> new HashSet<>())
                    .add(capability);
        }

        // Simulates an authorized reviewer re-evaluating prior grants.
        public void approveReview(Key key) {
            DirectoryState current = directory.get(key);
            if (current == null || !current.active()
                    || !current.groups().contains("finance")) {
                throw new IllegalStateException(
                        "Identity is not eligible for approval");
            }
            reviewRequired.remove(key);
        }

        public boolean mayApprove(Key key, Invoice invoice) {
            if (key == null || invoice == null) {
                return false;
            }

            DirectoryState current = directory.get(key);
            return current != null
                    && current.active()
                    && current.groups().contains("finance")
                    && !reviewRequired.contains(key)
                    && key.tenant().equals(invoice.tenant())
                    && invoice.pending()
                    && localGrants.getOrDefault(key, Set.of())
                            .contains("invoice:approve");
        }

        public long lastRevision(Key key) {
            DirectoryState current = directory.get(key);
            return current == null ? -1L : current.revision();
        }
    }

    public static void main(String[] args) {
        Key alice = new Key("https://idp.example", "alice-sub", "tenant-a");
        Invoice pendingA = new Invoice("tenant-a", true);
        Engine engine = new Engine();

        engine.grantLocally(alice, "invoice:approve");
        engine.apply(new DirectoryEvent(alice, 10, true,
                Set.of("finance", "employees")));
        System.out.println("initial=" + engine.mayApprove(alice, pendingA));

        engine.apply(new DirectoryEvent(alice, 9, false, Set.of()));
        System.out.println("stale-event=" + engine.mayApprove(alice, pendingA));

        engine.apply(new DirectoryEvent(alice, 11, false, Set.of()));
        System.out.println("disabled=" + engine.mayApprove(alice, pendingA));

        engine.apply(new DirectoryEvent(alice, 12, true, Set.of("finance")));
        System.out.println("reactivated=" + engine.mayApprove(alice, pendingA));

        engine.approveReview(alice);
        System.out.println("reviewed=" + engine.mayApprove(alice, pendingA));

        engine.apply(new DirectoryEvent(alice, 13, true, Set.of("employees")));
        System.out.println("group-removed=" + engine.mayApprove(alice, pendingA));

        engine.apply(new DirectoryEvent(alice, 14, true, Set.of("finance")));
        System.out.println("group-restored=" + engine.mayApprove(alice, pendingA));

        engine.approveReview(alice);
        System.out.println("group-reviewed=" + engine.mayApprove(alice, pendingA));

        Invoice otherTenant = new Invoice("tenant-b", true);
        System.out.println("cross-tenant="
                + engine.mayApprove(alice, otherTenant));
    }
}
~~~

**Run directly with JDK 17+:**

~~~bash
javac IdentityPermissionSyncDemo.java
java IdentityPermissionSyncDemo
~~~

**Exact program output:**

~~~text
initial=true
stale-event=true
disabled=false
reactivated=false
reviewed=true
group-removed=false
group-restored=false
group-reviewed=true
cross-tenant=false
~~~

Explanation:

1. Initially IdP group, local grant, tenant, and invoice status all satisfy the rule, so approval is allowed.
2. Event revision 9 arriving after revision 10 is ignored; it does not overwrite.
3. Revision 11 disables the account; effective access is immediately denied in the projection.
4. Revision 12 re-enables the account, yet **reviewRequired** remains set; local grants are not auto-restored.
5. After an explicit approveReview step, permission works again.
6. Revision 13 removes finance, blocking access and marking for review.
7. Revision 14 re-adds finance, yet stays blocked until business review approves.
8. Local grant scoped to tenant-a grants no access on tenant-b.

### 7.2. Limitations of the In-Memory Model

The Engine does not verify event authenticity itself; it assumes it is **called only after an adapter authenticated the source**. It does not persist to a DB, hold concurrent locks, or guard against concurrent multi-node writes. In production, revision checks and state updates must be **atomic** via transactions/CAS, with unique constraints and an outbox for invalidation. `grantLocally` in the example is an illustrative API; in practice it must be guarded by an independent business workflow verifying the grantor and writing audits.

The lesson enforces a policy of **requiring re-approval after deactivation or losing the finance group** for sensitive permissions. That is a specific policy choice; another product may choose temporary suspension until resolved or deleting the grant, yet should never auto-restore sensitive permissions after major lifecycle changes without an explicit design decision.

## 8. JUnit 5 Tests: Do Not Test Only the Allowed Path

Add JUnit Jupiter to your project's test suite. If using Gradle Spring Boot 3.x:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

test {
    useJUnitPlatform()
}
~~~

Place **IdentityPermissionSyncDemoTest.java** in the same package as the example (the demo omits a package declaration so it uses the default package in this exercise; real projects should use consistent packages):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Set;
import org.junit.jupiter.api.Test;

class IdentityPermissionSyncDemoTest {
    private static final IdentityPermissionSyncDemo.Key ALICE =
            new IdentityPermissionSyncDemo.Key(
                    "https://idp.example", "alice-sub", "tenant-a");
    private static final IdentityPermissionSyncDemo.Invoice INVOICE =
            new IdentityPermissionSyncDemo.Invoice("tenant-a", true);

    private IdentityPermissionSyncDemo.Engine ready() {
        var engine = new IdentityPermissionSyncDemo.Engine();
        engine.grantLocally(ALICE, "invoice:approve");
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 10, true, Set.of("finance")));
        return engine;
    }

    @Test
    void activeGroupAndLocalGrantAllow() {
        assertTrue(ready().mayApprove(ALICE, INVOICE));
    }

    @Test
    void localGrantWithoutIdentityIsDenied() {
        var engine = new IdentityPermissionSyncDemo.Engine();
        engine.grantLocally(ALICE, "invoice:approve");
        assertFalse(engine.mayApprove(ALICE, INVOICE));
    }

    @Test
    void groupWithoutBusinessGrantIsDenied() {
        var engine = new IdentityPermissionSyncDemo.Engine();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 10, true, Set.of("finance")));
        assertFalse(engine.mayApprove(ALICE, INVOICE));
    }

    @Test
    void staleEventCannotUndoDisable() {
        var engine = ready();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 11, false, Set.of()));
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 9, true, Set.of("finance")));
        assertFalse(engine.mayApprove(ALICE, INVOICE));
        assertEquals(11, engine.lastRevision(ALICE));
    }

    @Test
    void duplicateEventDoesNotChangeProjection() {
        var engine = ready();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 10, false, Set.of()));
        assertTrue(engine.mayApprove(ALICE, INVOICE));
        assertEquals(10, engine.lastRevision(ALICE));
    }

    @Test
    void reactivationRequiresBusinessReview() {
        var engine = ready();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 11, false, Set.of()));
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 12, true, Set.of("finance")));
        assertFalse(engine.mayApprove(ALICE, INVOICE));
        engine.approveReview(ALICE);
        assertTrue(engine.mayApprove(ALICE, INVOICE));
    }

    @Test
    void removedGroupCannotBeRestoredSilently() {
        var engine = ready();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 11, true, Set.of("employees")));
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 12, true, Set.of("finance")));
        assertFalse(engine.mayApprove(ALICE, INVOICE));
    }

    @Test
    void differentTenantOrFinishedInvoiceIsDenied() {
        var engine = ready();
        assertFalse(engine.mayApprove(ALICE,
                new IdentityPermissionSyncDemo.Invoice("tenant-b", true)));
        assertFalse(engine.mayApprove(ALICE,
                new IdentityPermissionSyncDemo.Invoice("tenant-a", false)));
    }

    @Test
    void sameSubjectFromDifferentIssuerIsNotSameUser() {
        var engine = ready();
        var otherIssuer = new IdentityPermissionSyncDemo.Key(
                "https://another-idp.example", "alice-sub", "tenant-a");
        assertFalse(engine.mayApprove(otherIssuer, INVOICE));
    }

    @Test
    void inactiveIdentityCannotBeReviewed() {
        var engine = ready();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 11, false, Set.of()));
        assertThrows(IllegalStateException.class,
                () -> engine.approveReview(ALICE));
    }
}
~~~

The test suite covers **10 cases**: full permission, missing IdP, missing local grant, stale event, duplicate event, reactivation, group removal, wrong tenant/status, different issuer, and blocking review while inactive. When running in a Gradle project with JUnit Jupiter:

~~~bash
./gradlew test --tests IdentityPermissionSyncDemoTest
~~~

On Windows/PowerShell:

~~~powershell
.\gradlew.bat test --tests IdentityPermissionSyncDemoTest
~~~

**Expected code behavior:** all 10 tests pass. This is an expected result from the fixture, not a recorded Gradle run log. For a real system, add integration tests with a DB, message broker, cache, mock IdP, and concurrency to verify transactions and multi-node behavior.

## 9. Applying in Spring Security: Beyond Mapping JWT Groups to Roles

### 9.1. JWT Validation and Stable Identity

Spring Security OAuth2 Resource Server validates JWT signatures, exp/nbf lifetimes, and configured issuers. Real applications must also verify **audience (aud)** matches the served API and enforce issuer/trust boundary rules per contract.

Illustrative **application.yml** configuration for a resource server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example/realms/main
~~~

With default configuration, scope/scp is typically mapped to a GrantedAuthority prefixed with **SCOPE_**. Spring Security does not automatically treat arbitrary groups claims from various IdPs as application business permissions. When using groups, configure JwtAuthenticationConverter/GrantedAuthoritiesConverter explicitly with an allowlist; never blindly turn every group name into approval permissions.

A verified JWT **does not guarantee claims reflect recent changes** on the IdP: a user can still hold a token issued before being locked or removed from a group. Checking the exp claim alone is insufficient if features require near-immediate revocation.

### 9.2. Enforcing at the Service Layer with @PreAuthorize and Business Policy

In Spring Security 6.x, enable method security:

~~~java
// Snippet placed in an application @Configuration.
@Configuration
@EnableMethodSecurity
class AuthorizationConfiguration {}
~~~

Create a policy bean querying the database/permission service to combine the IdP projection state, local grants, and resource state. The snippet below **illustrates integration**, not a standalone program: domain repositories/interfaces must be implemented by your project.

~~~java
@Component("invoiceAccess")
public class InvoiceAccessPolicy {
    private final InvoiceRepository invoices;
    private final IdentityProjectionRepository directory;
    private final BusinessGrantRepository grants;

    public InvoiceAccessPolicy(InvoiceRepository invoices,
                               IdentityProjectionRepository directory,
                               BusinessGrantRepository grants) {
        this.invoices = invoices;
        this.directory = directory;
        this.grants = grants;
    }

    public boolean mayApprove(Authentication authentication, long invoiceId) {
        if (!(authentication instanceof JwtAuthenticationToken token)) {
            return false;
        }

        Jwt jwt = token.getToken();
        if (jwt.getIssuer() == null || jwt.getSubject() == null) {
            return false;
        }

        Invoice invoice = invoices.findById(invoiceId).orElse(null);
        if (invoice == null || !invoice.isPending()) {
            return false;
        }

        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        String tenant = invoice.getTenantId(); // Loaded from DB, never trust request.

        return directory.isActiveAndCurrent(issuer, subject)
                && directory.isInGroup(issuer, subject, "finance")
                && grants.hasActiveGrant(
                        issuer, subject, tenant, "invoice:approve")
                && grants.notPendingReapproval(issuer, subject, tenant);
    }
}

@Service
public class InvoiceService {
    @PreAuthorize("@invoiceAccess.mayApprove(authentication, #p0)")
    public void approve(long invoiceId) {
        // Conditional update by status/limit inside transaction.
    }
}
~~~

**Required imports** for the snippet: Configuration, EnableMethodSecurity, Component, Service, PreAuthorize, Authentication, JwtAuthenticationToken, Jwt. The repositories and Invoice class belong to the application and are omitted here.

**Why use #p0?** It references the first method parameter without depending on whether the project enables compiler flags to retain Java parameter names. The `invoiceAccess` bean must be Spring-managed, and the protected method must be invoked through the Spring AOP proxy. Calling `new InvoiceService()` manually or calling internally via `this.` can bypass the `@PreAuthorize` interceptor.

**Check right at the business operation:** the tenant name is looked up from the actual invoice, never taken from the client. If invoice state can change between check time and update time, use transactions, locking, or `UPDATE ... WHERE status='PENDING'` and verify updated row count to prevent TOCTOU bugs. For sensitive operations, effective permissions must be checked against sufficiently fresh data consistent with the transaction.

### 9.3. HTTP Layer and Token Scopes

You can use request rules for coarse initial filtering, then let the service policy make the resource decision:

~~~java
// SecurityFilterChain config snippet, not standalone.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
        .hasAuthority("SCOPE_invoices.approve")
    .anyRequest().denyAll()
).oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
~~~

The **SCOPE_invoices.approve** scope is a coarse-grained token-level right; **it does not replace** local business grants, tenant scope, account state, or invoice conditions in method security. With an old JWT that still holds the scope, the policy service can still deny based on the updated IdP projection and current business grants.

In systems not using JWT, or using session/OIDC login, `Authentication` has a different type; use a corresponding adapter to extract a trusted identity rather than forcing every request into `JwtAuthenticationToken`. Never treat `authentication.getName()` as a global primary key because many JWT setups return only `sub` without `issuer`.

### 9.4. Consistency Levels and Permission Caching

Each feature needs a clear policy on **maximum sync lag**:

| Operation Class | Handling When Projection Is Stale or IdP Unreachable |
| --- | --- |
| Approvals, money transfers, privilege escalation, sensitive exports | May require fresh status check or deny until verified; prefer fail closed |
| Non-sensitive reads, low-risk tasks | May permit bounded staleness per approved short TTL while still checking local grant and tenant |
| Background jobs with service identity | Check the service identity's own permissions, never borrow ROLE_ADMIN by default |
| Account disabled in projection | Deny; never let a stale allow cache override a locked status |

**There is no single TTL for every product.** Revocation goals must balance availability and be scoped by risk. In all cases, never interpret an IdP timeout error as "no updates found, keep granting indefinitely."

An **allow** decision cache needs a key covering issuer + sub + tenant + resource + action + permission/group versions (and any policy condition affecting outcomes). When a user is locked or a permission revoked, invalidate accurately; if invalidation lags, TTLs/safety gates must keep high-risk permissions within approved bounds.

## 10. Syncing and Reconciling Without Overwriting Business Permissions

### 10.1. Ingestion and Transactions

Example flow in **pseudocode** showing transactional responsibilities:

~~~text
receive(verified_event):
    validate_schema_and_trust(verified_event)
    key = (issuer, subject)
    begin transaction
        if inbox already contains (source, eventId):
            commit and acknowledge
        else:
            current = load IdP projection FOR UPDATE
            if event is a full snapshot with verifiable newer revision:
                update only IdP-owned fields
                if account was disabled or sensitive group removed:
                    mark local sensitive grants as requiring review
            store inbox eventId
            store outbox cache-invalidation message
    commit
    acknowledge only after commit
~~~

If the source version is an opaque ETag, do not compare "v2" > "v1" lexicographically/numerically; use concurrency control supported by the source or read the current snapshot with an adapter-provided revision. If an event is a PATCH, merge only changed fields; never treat omitted fields as empty.

In the database, an **atomic** conditional upsert or compare-and-swap prevents two workers from overwriting out of order. When outbox delivery fails, retries will not emit invalid authorization state because invalidation is idempotent and versioned.

### 10.2. Reconciliation Must Not Become "Mass Revocation"

A periodic reconciliation job should:

1. Read eligible identities/projections by issuer/tenant, handling all pages completely.
2. Record a watermark or snapshot version; confirm the source returned **complete and successful** results.
3. Compare active flags, groups, and identity bindings; log drift per key.
4. Repair **IdP-owned** attributes without overwriting local business grants.
5. For deletions/locks/group removals, apply the proper deny/review, invalidation, and audit policies.
6. For conflicting events or incomparable versions, route to dedicated conflict resolution rather than granting automatically.
7. Report results and alert on abnormal drift; design operations to be safely repeatable without unwanted side effects.

If the IdP API times out mid-pagination, the missing tail of the list does not mean those users were deleted. A reconciliation system should only perform **deletion by absence** when it holds a **complete verified snapshot** or an explicit contractual deletion signal.

### 10.3. Who May Change the Permission Map?

The IdP group → business eligibility mapping table must have an owner, version, review workflow, and tests. From a domain perspective, an IdP group rename must never accidentally grant **invoice:approve** to an entire group. Mapping tables are authorization code and require the same testing, review, and deployment rigor.

If an organization varies policy groups per tenant, audit precisely which rule applied at decision time. When mapping contracts change, consider bumping policyVersion to invalidate caches and avoid mixing two interpretations of permissions.

## 11. Integration Test Matrix for Guaranteed Consistency

| Case | IdP State | Local Grant | Resource/Condition | Expectation |
| --- | --- | --- | --- | --- |
| A1 | Active, finance | invoice:approve | Right tenant, PENDING | Allow |
| A2 | Active, finance | No invoice:approve | Right tenant | Deny |
| A3 | Active, no longer finance | invoice:approve | Right tenant | Deny |
| A4 | Disabled | invoice:approve still stored | Right tenant | Deny |
| A5 | Reactivated after disabled | Old grant awaiting review | Right tenant | Deny until re-approved |
| A6 | Active, finance | invoice:approve | Different tenant | Deny |
| A7 | Active, finance | invoice:approve | Completed invoice | Deny |
| A8 | Newer revision locks first; older active revision arrives late | Grant still stored | Right tenant | Deny, no rollback |
| A9 | Same eventId replayed multiple times | Unchanged | Unchanged | Idempotent |
| A10 | Same sub, different issuer | Grant from old issuer | Right tenant | Deny |
| A11 | Unexpired JWT after IdP locks account | Grant still stored | Sensitive permission | Deny per current projection |
| A12 | Finance group revoked then re-added | Old grant needs review | Right tenant | Deny until new decision |
| A13 | SCIM PATCH omits groups field | Keep local grant | Right tenant | Do not wipe groups on missing field |
| A14 | Reconciliation fails mid-run | Incomplete state | Many accounts | No mass-delete |
| A15 | Permission re-granted in tenant A | No grant in tenant B | Resource B | Deny |
| A16 | Two sync workers apply different revisions concurrently | Separate grants | Right tenant | Highest valid revision wins |
| A17 | Allow cache not yet invalidated | Permission was revoked | Sensitive action | Deny per freshness mechanism |
| A18 | IdP temporarily unresponsive | Local grant present | High-risk approval | Apply approved stale/fail-closed policy |

**Test layering:** JUnit unit tests verify merging logic as in section 8. DB integration tests verify transactions/unique versions, broker tests verify duplicates/reordering/retries, Spring Security tests verify 401/403, and end-to-end tests with a mock IdP verify old JWTs after account lock.

A Spring test using only `@WithMockUser(authorities="invoice:approve")` **does not prove permission sync works** because it injects authorities directly in the test. You need fixtures controlling the IdP projection, local grants, tenant/resource, and versions independently. For HTTP endpoints using sessions/CSRF, POST tests must include a valid CSRF token if testing permissions rather than CSRF.

For concurrency, test two consumers receiving revisions 21 and 22 concurrently: the final state must remain 22. If the system uses multi-node caching, verify one node updates and another cannot keep honoring revoked permissions beyond the freshness window.

## 12. Operations: Tracking Latency and Data Drift

| Metric Group | Monitoring Suggestions |
| --- | --- |
| Event ingestion | Events received/processed, duplicates, stale versions, schema/signature errors |
| Sync | Latency from IdP change to projection update, backlog, and oldest event age |
| Reconciliation | Drift record count, successful repairs, incomplete snapshot runs |
| Effective permissions | Allow/deny rates by bounded capability, denials due to inactive/group/local/tenant |
| Cache | Cache hits/misses, invalidation latency, version mismatches, stale usage duration |
| Security | Reapproval requests count, revocation effective time, abnormal permission churn |
| Infrastructure | IdP API errors, timeouts, retries, slow outbox, DB contention, and policy latency |

**Notable alerts:** a sync batch modifying large numbers of `invoice:approve` permissions, sudden denial spikes after a mapping release, large inbox backlogs, or projections staler than threshold for sensitive rights.

Never place **sub, email, tenantId, invoiceId, token, or raw URL** as unbounded-cardinality metric tags. Store detailed trace info in access-controlled audit logs linked by correlation id.

### 12.1. When the IdP Temporarily Goes Down

Absolute instantaneous consistency between an IdP and an application is impossible when the two systems are separate. State the **consistency model** explicitly: event-driven eventual consistency, SLA-bound polling, online IdP checks for high-risk actions, or deny when state is too stale.

For financial approval rights, staleness beyond a short configured threshold may be unacceptable. For low-sensitivity reads, the business may tolerate bounded staleness. Decisions must be designed, measured, and tested—never assumed as a side effect of having a cache TTL.

### 12.2. Business Permission Change Lifecycle

Document separately how `invoice:approve` is requested, granted, and revoked in the business system: requester, approver, tenant, limit, reason, effective time, expiry, and audit trail. **The identity sync consumer must never act as a business administrator.** When using a `business_grant` table, restrict write access and audit all write paths, not only HTTP endpoints.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using email as sync key | Misassigned permissions when email changes/recycles | Use issuer + subject and verified account linking |
| Copying IdP groups into business roles column | IdP sync overwrites app-granted permissions | Separate projection from business grants, merge in policy |
| Assuming group finance = invoice:approve | Privilege scope creep | Use necessary gate + local grant + tenant/resource check |
| Applying events by arrival time | Old events resurrect revoked permissions | Verified version/revision or snapshot/ETag |
| Treating SCIM ETag as an increasing integer | Version comparison becomes meaningless | Treat ETag as opaque; use contractual If-Match/snapshot sync |
| Treating PATCH missing groups as [] | Mass accidental revocation | Distinguish partial updates from full snapshots |
| Hard-deleting projection on deprovision | Old events can recreate it | Tombstone/versioning and lifecycle controls |
| IdP reactivation auto-restores old grants | Sensitive permissions skip review | Keep deny/review gate until approved |
| Treating unexpired JWT as freshest permissions | Slow permission revocation | Fresh projection/introspection/revocation/risk-based TTL |
| Cache key using only sub | Permission leaks across issuer/tenant/resource | Context-complete key, versioning, and invalidation |
| Treating incomplete reconcile page as deleted | Mass lockouts/permission loss | Process absence only on verified complete snapshots |
| IdP outage means infinite cache allow | Locked users continue operating | Freshness policy and fail closed for sensitive rights |
| Testing only allow, never deny | Escalation bugs go unnoticed | Positive/negative matrices and data-state tests |
| Relying on @WithMockUser to test provisioning | Tests bypass IdP/local grant sources | Test pipeline, DB, and token mapping directly |

## 14. Practice Exercises

**Exercise 1 — Preserve business permissions:** Grant `report:export` in localGrants for Alice. The IdP changes the `employees` group without changing the export prerequisite group. Prove no IdP event automatically deletes the local grant, while clearly defining when `report:export` must be blocked by effective policy.

**Exercise 2 — Out-of-order sync:** Send events revision 30 active, 32 inactive, 31 active. Write a test asserting the final revision is 32 and permission is denied. Add a duplicate eventId to test inbox idempotency.

**Exercise 3 — Multi-tenant:** Alice has `invoice:approve` in tenant A but not B. Add an invoices table where tenantId is loaded from DB; prove passing `tenant=A` in the request does not grant access if the actual resource belongs to B.

**Exercise 4 — Sync after deprovision:** Disable an account, retain the local grant for audit, then re-enable the account in the IdP. Implement `reviewRequired` and test that only a business admin can clear the review state after approval, with an audit log.

**Exercise 5 — Stale token:** Simulate a JWT issued before the IdP revoked `finance`. Test that the token still passes authentication yet `@PreAuthorize` denies based on the new projection. Test various TTLs and define acceptable revocation lag bounds.

**Exercise 6 — Incomplete reconciliation:** Mock the IdP API to return page 1 successfully and fail on page 2. Prove the logic does not infer all identities on page 2 were deleted. After recovery, run a full pass and log drift audits.

**Exercise 7 — Concurrency:** Two workers process revisions 44 and 45 for the same Key. Use transactions/unique constraints/optimistic locking to prove the final state can never revert to 44.

## 15. Acceptance Checklist

- [ ] Clear ownership table: IdP owns identity lifecycle/groups; business owns grants/ACLs/limits.
- [ ] Identity keys use issuer + subject, with verified tenant scope.
- [ ] Effective permissions include active status, group gates, local grants, and resource conditions.
- [ ] Ingestion verifies source, handles duplicate events, and handles out-of-order events.
- [ ] Partial updates do not wipe omitted fields; ETags follow proper semantics.
- [ ] Deprovision/tombstones prevent old events from resurrecting permissions.
- [ ] Reactivation after sensitive revocation has an explicit review policy.
- [ ] Reconciliation modifies only IdP-owned data and never treats incomplete snapshots as deletions.
- [ ] Stale caches/tokens are handled per defined freshness/revocation policies.
- [ ] `@EnableMethodSecurity` and `@PreAuthorize` run via Spring-managed beans; policies fetch tenant from trusted data.
- [ ] Tests cover both allow and deny for inactive, missing local grant, missing group, cross-tenant, stale token, replay, and concurrency.
- [ ] Audits and metrics support investigation without exposing tokens or sensitive data.

## 16. References

- Spring Security — OAuth2 Resource Server JWT, claims validation and JwtAuthenticationConverter: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Method Security / @EnableMethodSecurity / @PreAuthorize: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- RFC 7643 — SCIM Core Schema: https://www.rfc-editor.org/rfc/rfc7643
- RFC 7644 — SCIM Protocol, PATCH and ETag: https://www.rfc-editor.org/rfc/rfc7644
- OpenID Connect Core 1.0 — Issuer, Subject, ID Token: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Token Introspection (RFC 7662): https://www.rfc-editor.org/rfc/rfc7662
- OAuth 2.0 Token Revocation (RFC 7009): https://www.rfc-editor.org/rfc/rfc7009
