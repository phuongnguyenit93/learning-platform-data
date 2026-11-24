# Multi-User, Role, Tenant, and Sharing Relationship Test Dataset

## 1. Lesson Objectives

In a multi-tenant system, a request is permitted only when the **authenticated principal**, **correct tenant membership**, **role within the tenant**, **resource attributes**, and **valid sharing relationships** all satisfy the policy together. A test with only a single ADMIN user and a single document cannot detect cross-tenant data leaks, roles applied to the wrong scope, or sharing relationships that improperly escalate privileges.

This lesson guides you through creating a **test dataset with multiple users, roles, tenants, and sharing relationships**, determining expected results independently of the code under test, and then running an authorization matrix at both the policy and HTTP levels. The focus falls under the **Data and Policy Testing** topic of the **Spring Security - Authorization** module.

After this lesson, you will be able to:
- Distinguish among user, membership, role, owner, visibility, resource state, and ACL/share grant.
- Design fixtures containing allowed cases, denied cases, cross-tenant cases, expired/revoked grants, and different roles per tenant.
- Test combinations of RBAC (roles), ABAC (tenant, state, attributes), and ReBAC (owner/share) along with trust boundaries.
- Prove that a deny decision neither leaks data via list/search/count nor causes side effects in the database.
- Re-run deterministic tests using stable IDs, a fixed clock, and independent data cleanup.

## 2. Model and Trust Boundaries

| Component | Example Data | Role |
|---|---|---|
| Principal | u-alice, u-sam | Identity obtained from Authentication; logging in does not grant permissions on its own. |
| Tenant | t-a, t-b | Ownership and data isolation boundary. |
| Membership | (t-a, u-sam, EDITOR) | A single user can belong to multiple tenants with different roles. |
| Document | D-A1, tenant=t-a, owner=u-alice | Resource with tenant, owner, visibility, and state. |
| Share/ACL | D-A1 → u-carol, WRITE | Permission on a specific resource; has a recipient and an expiration timestamp. |
| Action | READ, EDIT, SHARE, DELETE | Actions that must be checked independently, not lumped into a generic "access" permission. |

Separate three mandatory checks:

1. **Authentication**: who is the user? Without a valid principal, protected endpoints must reject the request.
2. **Tenant membership**: does the user have a valid membership in the document's tenant? An ADMIN role in t-b has no effect in t-a. A client-supplied tenantId does not prove membership.
3. **Object/action authorization**: given a valid membership, evaluate role, owner, visibility, document state, and active grants. An EDITOR in the same tenant is not automatically allowed to edit every private document.

The source of truth is the authenticated principal and the membership/resource/share data looked up from the server/repository. Never trust ownerId, role, grantedBy, or tenantId in a request as proof of permission. Do not infer the real tenant from the "D-A" ID prefix; that is only a human-readable sample name.

## 3. Sample Policy Specification

The example uses three roles—ADMIN, EDITOR, and VIEWER; visibility PRIVATE/TENANT; state OPEN/ARCHIVED; and sharing permissions READ/WRITE. The recipient must be a member of the **same tenant**. A WRITE grant implies READ, but **does not elevate a VIEWER to an EDITOR** and does not automatically grant SHARE/DELETE. A grant is valid when **now < expiresAt**; at the exact expiration instant, it must be denied.

| Action | Condition after verifying membership in the correct tenant |
|---|---|
| READ | Owner, or ADMIN, or document has TENANT visibility, or has an unexpired READ/WRITE grant. ARCHIVED documents remain readable. |
| EDIT | Document is OPEN and actor is ADMIN, or actor is EDITOR and is also owner/has a WRITE grant. VIEWER cannot edit. |
| SHARE | Document is OPEN and actor is ADMIN or EDITOR who is also owner; when granting permission, verify the recipient is in the same tenant. |
| DELETE | Document is OPEN and actor is ADMIN or EDITOR who is also owner. ARCHIVED is immutable in this model. |
| Any action | Missing membership, wrong tenant, non-existent document, or unmet condition → DENY. |

There is no implicit "global ADMIN" privilege. The policy above is the **business convention for this test suite**, not a built-in default of Spring Security. Before writing tests, the project team must finalize a specification matching the real product. HTTP may return 403 for insufficient permissions or 404 to hide the existence of a document in another tenant; the contract must be agreed upon. The test table below uses ALLOW/DENY independently of the HTTP status code.

## 4. Multi-Dimensional Dataset Design

Fix **now = 2026-11-06T00:00:00Z** across the entire test suite. IDs, states, roles, and expiration timestamps are seeded against a single baseline; never use wall-clock time as the oracle.

### 4.1. Users and Memberships

| User | Tenant | Role | Purpose |
|---|---|---|---|
| u-alice | t-a | EDITOR | Owner of a private document. |
| u-bob | t-a | VIEWER | Recipient of READ and WRITE grants; tests role limits. |
| u-carol | t-a | EDITOR | Owner of another document and recipient of a WRITE grant from Alice. |
| u-diana | t-a | ADMIN | Administrator dedicated to tenant A. |
| u-sam | t-a | EDITOR | Same user with a higher role in tenant A. |
| u-erin | t-b | ADMIN | Tests a tenant B ADMIN accessing tenant A resources. |
| u-frank | t-b | VIEWER | Recipient with a grant expiring right on the boundary. |
| u-sam | t-b | VIEWER | Same user with a lower role in tenant B. |

There are **7 unique users, 8 memberships, 2 tenants, and 3 roles**. Roles must be looked up by the (tenantId, userId) pair. If roles are stored globally on the user, someone like u-sam can easily receive permissions in the wrong tenant.

### 4.2. Documents

| ID | Tenant | Owner | Visibility | State | Primary Scenario |
|---|---|---|---|---|---|
| D-A1 | t-a | u-alice | PRIVATE | OPEN | Owner and recipients have different permissions. |
| D-A2 | t-a | u-carol | TENANT | OPEN | Every member of A can read, not automatically edit. |
| D-A3 | t-a | u-carol | PRIVATE | ARCHIVED | Readable when authorized, but cannot be modified. |
| D-B1 | t-b | u-erin | PRIVATE | OPEN | Tests grant expiration. |
| D-B2 | t-b | u-sam | PRIVATE | OPEN | An owner with the VIEWER role can only read. |

### 4.3. Sharing Relationships

| Grant | Document → Recipient | Permission | ExpiresAt (UTC) | Meaning |
|---|---|---|---|---|
| S1 | D-A1 → u-bob | READ | 2027-01-01T00:00:00Z | Bob can read, not edit. |
| S2 | D-A1 → u-carol | WRITE | 2027-01-01T00:00:00Z | Carol (EDITOR) can edit, but cannot re-SHARE. |
| S3 | D-A2 → u-bob | WRITE | 2027-01-01T00:00:00Z | VIEWER still cannot EDIT. |
| S4 | D-A3 → u-alice | WRITE | 2027-01-01T00:00:00Z | ARCHIVED still blocks EDIT. |
| S5 | D-B1 → u-frank | READ | 2026-11-06T00:00:00Z | Exactly at expiry, READ is denied. |

In a real system, a grant should have tenantId, documentId, recipientId, grantedBy, permission, expiresAt, a revoked status or deletion mechanism, and audit timestamps. Foreign keys/transaction checks must keep the document and recipient in the same tenant. **Do not seed a cross-tenant grant into an integration database** when constraints forbid it; only intentionally inject a forged grant in a pure unit test to confirm the policy remains safe against invalid data.

### 4.4. Why Is This Fixture Useful?

- **Same resource, different actors:** Alice, Bob, Carol, Diana, and Erin on D-A1 expose differences among owner, recipient, admin, and tenant.
- **Same actor, different tenants:** u-sam across A/B exposes bugs where roles are applied globally.
- **Same WRITE grant, different roles:** Carol (EDITOR) can edit D-A1; Bob (VIEWER) cannot edit D-A2.
- **Same permission, different states:** WRITE takes effect on OPEN D-A1, not on ARCHIVED D-A3.
- **Same recipient, different relationship states:** Carol can read D-A1 before revocation and is denied after revocation; Frank is denied at expiry.

A small dataset with contrasting cases is far more valuable than randomly generating thousands of records containing only ALLOW cases.

## 5. Expected Authorization Matrix

**The oracle must be derived from the specification in Section 3**, not by taking the output of the function under test as the expected value.

| # | Actor/role/tenant | Action | Resource | Expected | Reason |
|---|---|---|---|---|---|
| 1 | Alice / EDITOR A | READ | D-A1 | ALLOW | Owner. |
| 2 | Alice / EDITOR A | EDIT | D-A1 | ALLOW | Owner + EDITOR + OPEN. |
| 3 | Bob / VIEWER A | READ | D-A1 | ALLOW | Active S1 READ grant. |
| 4 | Bob / VIEWER A | EDIT | D-A1 | DENY | VIEWER cannot edit. |
| 5 | Carol / EDITOR A | EDIT | D-A1 | ALLOW | Active S2 WRITE grant. |
| 6 | Carol / EDITOR A | SHARE | D-A1 | DENY | Has WRITE, but is not owner/admin. |
| 7 | Diana / ADMIN A | DELETE | D-A1 | ALLOW | ADMIN in the correct tenant, OPEN. |
| 8 | Erin / ADMIN B | READ | D-A1 | DENY | Wrong tenant despite being ADMIN. |
| 9 | Bob / VIEWER A | READ | D-A2 | ALLOW | TENANT visibility. |
| 10 | Bob / VIEWER A | EDIT | D-A2 | DENY | S3 WRITE does not elevate VIEWER. |
| 11 | Alice / EDITOR A | EDIT | D-A2 | DENY | Not owner and has no WRITE grant. |
| 12 | Alice / EDITOR A | READ | D-A3 | ALLOW | S4 WRITE implies READ. |
| 13 | Alice / EDITOR A | EDIT | D-A3 | DENY | ARCHIVED disallows mutation. |
| 14 | Frank / VIEWER B | READ | D-B1 | DENY | S5 expired at now. |
| 15 | Sam / VIEWER B | READ | D-B2 | ALLOW | Owner can read. |
| 16 | Sam / VIEWER B | EDIT | D-B2 | DENY | Owner does not override role. |
| 17 | Sam / EDITOR A | READ | D-B2 | DENY | Membership A is not valid in B. |
| 18 | Carol / EDITOR A | READ | D-A1 after revoking S2 | DENY | No valid relationship remains. |
| 19 | No membership | READ | D-A1 | DENY | Lacks an eligible subject. |
| 20 | Erin / ADMIN B + forged grant | EDIT | D-A1 | DENY | Tenant boundary blocks before ACL. |

Always pass the membership for the right tenant based on the authenticated identity. Never write a test stating "Sam is an EDITOR" without specifying whether that is membership A or B.

## 6. Standalone Java 17 Example: Policy and 20 Checks

The program uses enum, record, List, and Instant; neither Spring nor a database is required. The Membership class in this example **is assumed to be a server-verified record**, not an object the client can construct itself. The allow method handles null for the missing-membership case.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public class AuthorizationDatasetDemo {
    enum Role { ADMIN, EDITOR, VIEWER }
    enum Visibility { PRIVATE, TENANT }
    enum State { OPEN, ARCHIVED }
    enum Permission { READ, WRITE }
    enum Action { READ, EDIT, SHARE, DELETE }

    record Membership(String userId, String tenantId, Role role) {}
    record Document(
            String id, String tenantId, String ownerId,
            Visibility visibility, State state) {}
    record Share(
            String documentId, String recipientId,
            Permission permission, Instant expiresAt) {}

    static boolean hasGrant(List<Share> shares, Document doc,
                            Membership actor, Permission needed, Instant now) {
        return shares.stream().anyMatch(s ->
                s.documentId().equals(doc.id())
                && s.recipientId().equals(actor.userId())
                && now.isBefore(s.expiresAt())
                && (s.permission() == needed
                    || (needed == Permission.READ
                        && s.permission() == Permission.WRITE)));
    }

    static boolean allow(Membership actor, Document doc, Action action,
                         List<Share> shares, Instant now) {
        if (actor == null || doc == null || action == null || now == null
                || !actor.tenantId().equals(doc.tenantId())) {
            return false;
        }

        boolean admin = actor.role() == Role.ADMIN;
        boolean editor = actor.role() == Role.EDITOR;
        boolean owner = actor.userId().equals(doc.ownerId());

        return switch (action) {
            case READ -> admin || owner
                    || doc.visibility() == Visibility.TENANT
                    || hasGrant(shares, doc, actor, Permission.READ, now);
            case EDIT -> doc.state() == State.OPEN
                    && (admin || (editor && (owner
                        || hasGrant(shares, doc, actor, Permission.WRITE, now))));
            case SHARE, DELETE -> doc.state() == State.OPEN
                    && (admin || (editor && owner));
        };
    }

    static void check(String name, Membership actor, Document doc,
                      Action action, List<Share> shares, Instant now,
                      boolean expected) {
        boolean actual = allow(actor, doc, action, shares, now);
        if (actual != expected) {
            throw new AssertionError(name + ": expected=" + expected
                    + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");
        Instant future = Instant.parse("2027-01-01T00:00:00Z");

        Membership alice = new Membership("u-alice", "t-a", Role.EDITOR);
        Membership bob = new Membership("u-bob", "t-a", Role.VIEWER);
        Membership carol = new Membership("u-carol", "t-a", Role.EDITOR);
        Membership diana = new Membership("u-diana", "t-a", Role.ADMIN);
        Membership samA = new Membership("u-sam", "t-a", Role.EDITOR);
        Membership erin = new Membership("u-erin", "t-b", Role.ADMIN);
        Membership frank = new Membership("u-frank", "t-b", Role.VIEWER);
        Membership samB = new Membership("u-sam", "t-b", Role.VIEWER);

        Document a1 = new Document(
                "D-A1", "t-a", "u-alice", Visibility.PRIVATE, State.OPEN);
        Document a2 = new Document(
                "D-A2", "t-a", "u-carol", Visibility.TENANT, State.OPEN);
        Document a3 = new Document(
                "D-A3", "t-a", "u-carol", Visibility.PRIVATE, State.ARCHIVED);
        Document b1 = new Document(
                "D-B1", "t-b", "u-erin", Visibility.PRIVATE, State.OPEN);
        Document b2 = new Document(
                "D-B2", "t-b", "u-sam", Visibility.PRIVATE, State.OPEN);

        List<Share> shares = List.of(
                new Share("D-A1", "u-bob", Permission.READ, future),
                new Share("D-A1", "u-carol", Permission.WRITE, future),
                new Share("D-A2", "u-bob", Permission.WRITE, future),
                new Share("D-A3", "u-alice", Permission.WRITE, future),
                new Share("D-B1", "u-frank", Permission.READ, now));

        check("owner read", alice, a1, Action.READ, shares, now, true);
        check("owner edit", alice, a1, Action.EDIT, shares, now, true);
        check("shared read", bob, a1, Action.READ, shares, now, true);
        check("viewer edit", bob, a1, Action.EDIT, shares, now, false);
        check("shared write", carol, a1, Action.EDIT, shares, now, true);
        check("recipient reshare", carol, a1, Action.SHARE, shares, now, false);
        check("tenant admin delete", diana, a1, Action.DELETE, shares, now, true);
        check("cross tenant admin", erin, a1, Action.READ, shares, now, false);
        check("tenant visible", bob, a2, Action.READ, shares, now, true);
        check("write cannot elevate viewer", bob, a2, Action.EDIT, shares, now, false);
        check("editor no grant", alice, a2, Action.EDIT, shares, now, false);
        check("archived readable", alice, a3, Action.READ, shares, now, true);
        check("archived immutable", alice, a3, Action.EDIT, shares, now, false);
        check("expiry boundary", frank, b1, Action.READ, shares, now, false);
        check("viewer owner read", samB, b2, Action.READ, shares, now, true);
        check("viewer owner edit", samB, b2, Action.EDIT, shares, now, false);
        check("role scoped to tenant", samA, b2, Action.READ, shares, now, false);

        List<Share> revoked = shares.stream()
                .filter(s -> !(s.documentId().equals("D-A1")
                        && s.recipientId().equals("u-carol")))
                .toList();
        check("revoked share", carol, a1, Action.READ, revoked, now, false);
        check("missing membership", null, a1, Action.READ, shares, now, false);

        List<Share> tampered = new ArrayList<>(shares);
        tampered.add(new Share("D-A1", "u-erin", Permission.WRITE, future));
        check("forged cross tenant grant",
                erin, a1, Action.EDIT, tampered, now, false);

        System.out.println("All checks passed.");
    }
}
~~~

Save the file as **AuthorizationDatasetDemo.java**, then run:

~~~bash
javac --release 17 AuthorizationDatasetDemo.java
java AuthorizationDatasetDemo
~~~

Exact stdout if all assertions pass:

~~~text
All checks passed.
~~~

**Logic explanation:** the tenant check is performed before any grant/role; READ accepts TENANT visibility or an unexpired READ/WRITE grant. EDIT requires OPEN and a sufficiently strong role combined with owner/WRITE. SHARE/DELETE are not derived from a WRITE grant. The condition now.isBefore(expiresAt) causes cases equal to the exact expiry timestamp to be denied. Revoking S2 is simulated with a new share set omitting Carol's relationship; Erin's forged data never crosses the tenant boundary.

This is a policy example and does not yet cover real membership lookup, repositories, transactions, auditing, write-path protection, or concurrency. Those parts are implemented in the Spring application and database.

## 7. Applying to Spring Security and HTTP Tests

### 7.1. Server-Side Access Control Flow

For GET /api/tenants/{tenantId}/documents/{id}, the system must: extract userId from Authentication; look up membership by the **exact tenantId + userId**; read the document by **tenantId + id**; fetch shares for the right tenant/document; evaluate the READ policy; and serialize the document into the response only after ALLOW. For POST/PUT/DELETE, check the exact action inside a transaction and verify no mutation occurs on DENY.

Brief flow diagram:

~~~text
Authentication → Membership(userId, tenantId)
                → Document(tenantId, documentId)
                → Share(documentId, recipientId, expiresAt)
                → Policy(action, role, owner, visibility, state, now)
                → ALLOW / DENY → HTTP + database outcome
~~~

An illustrative service snippet (not a standalone class, since repository, mapper, exceptions, and policy are defined by the application):

~~~java
public DocumentView readDocument(
        String tenantId, String documentId, Authentication authentication) {
    String userId = authentication.getName();
    Membership membership = membershipRepository
            .findByTenantIdAndUserId(tenantId, userId)
            .orElseThrow(AccessDeniedException::new);
    Document document = documentRepository
            .findByTenantIdAndId(tenantId, documentId)
            .orElseThrow(DocumentNotFoundException::new);
    List<Share> shares = shareRepository
            .findByTenantIdAndDocumentId(tenantId, documentId);

    if (!policy.allow(membership, document, Action.READ,
                      shares, clock.instant())) {
        throw new AccessDeniedException("Document access denied");
    }
    return mapper.toView(document);
}
~~~

You can place the check in @PreAuthorize via a policy bean or AuthorizationManager, but the annotation does not automatically infer tenant/ownership/shares. If a query only calls findById(documentId) without tenantId, the query must be fixed; a policy check cannot replace data scoping for list/search/count.

### 7.2. Simulating Principals in MockMvc

In a Spring Boot test configured with MockMvc, a seeded database, and spring-security-test, you can verify that an ADMIN of t-b cannot read D-A1. Example choosing a **404 contract for out-of-tenant resources**:

~~~java
mockMvc.perform(get("/api/tenants/{tenantId}/documents/{id}", "t-a", "D-A1")
        .with(jwt().jwt(j -> j.subject("u-erin"))
                .authorities(new SimpleGrantedAuthority("SCOPE_documents:read"))))
    .andExpect(status().isNotFound());
~~~

This is an illustrative test snippet inside a class that already has imports/fixtures, not a standalone runnable file. If the product specifies 403 for cross-tenant access, change the expected status to 403. You must confirm the membership query for u-erin only finds (t-b, ADMIN) so it cannot retrieve a t-a document. Mock JWT only creates an authentication in tests and does not verify token signatures with a real IdP.

Do not use @WithMockUser(roles="ADMIN") as proof of having created a tenant membership: that annotation does not automatically seed domain roles, owners, or ACLs. Distinguish authorities like SCOPE_documents:read from business roles in a tenant: holding a JWT scope does not mean having permission on every object.

### 7.3. Database and Mutations

Constraints to guarantee:
- Unique membership per (tenant_id, user_id) with a valid role; changing a role must not accidentally affect another tenant.
- Document belongs to one tenant and its owner is verified by business rules; query by (tenant_id, id).
- Share belongs to the same tenant as both document and recipient; do not accept grantedBy/ownerId from the client as trusted data.
- Check the actor's SHARE permission before creating, modifying, or revoking a grant; do not allow regular users to write ACLs directly.
- Maintain appropriate indexes on (tenant_id, document_id, recipient_id), a mechanism to identify expired/revoked grants, and cache invalidation when roles change or grants are revoked.
- Avoid races between authorization and mutation: combine transactions and versioning/locking when policies can change concurrently.

For denied edit/share/delete tests, snapshot the document and share list **before/after** the request and confirm no changes occurred. Asserting only the HTTP status is insufficient: the application might have written to the database before returning an error.

## 8. Recommended Test Layers

| Test Layer | Fixture Used | Evidence to Verify |
|---|---|---|
| Pure unit | Fixed Membership/document/share/Clock | All 20 ALLOW/DENY decisions match the matrix. |
| Repository | 2 tenants with separate documents and separate sharing | No cross-tenant results from detail/list/search/count; tenant predicate applied to pagination. |
| HTTP integration | Corresponding principal + seeded DB | Status matches contract, body does not leak cross-tenant documents; JWT scopes do not bypass policy. |
| Mutation | EDIT/SHARE/DELETE, revoke and re-grant | ALLOW modifies the right object; DENY leaves data unchanged. |
| Lifecycle | grants before/at/after expiry, role change, revoke | Permissions update immediately, without stale caches or an uncontrolled real Clock. |

Extended cases if supported by the product: recipient no longer holds a membership, duplicate shares, owner change, tenant transfer, owner leaving the tenant, multiple roles within the same tenant, link sharing, bulk download/export, events, or background jobs. Also test empty lists, secret data leaked via counts/totals, and replacing object IDs in routes to catch IDOR (insecure direct object reference). Only add cases that match the real specification, avoiding inventing non-existent permissions.

To keep fixtures reproducible:
1. Build deterministic test factories/seeds and fix time with an injectable Clock. Do not rely on the test run date, test order, or hard-to-debug random UUIDs.
2. Use an independent baseline per test; roll back transactions or reset the DB/container. Do not reuse data mutated by an earlier test.
3. Use a manually derived expected matrix as the oracle; do not invoke the policy first and treat its output as expected.
4. On failure, report userId + tenantId + action + documentId + grantId + expected/actual; avoid logging real tokens/PII.
5. Enforce authorization in the service/database and across all paths that can return resources; hiding buttons in the UI is UX, not an authorization boundary.

## 9. Common Pitfalls

- **Single tenant only:** cannot detect queries missing tenant_id; add t-b with an ADMIN and separate documents.
- **Global roles:** u-sam (EDITOR in A) accidentally gains EDIT in B; must look up by the membership pair.
- **Same tenant = full access:** D-A2 TENANT allows every member to READ, not to EDIT.
- **WRITE share = SHARE/DELETE:** Carol has S2 and can only edit D-A1 under her EDITOR role, not re-share it further.
- **WRITE share elevates VIEWER:** Bob has S3 yet is still denied EDIT.
- **Owner overrides role:** Sam (VIEWER) owning D-B2 still cannot edit under the defined policy.
- **Dynamic time:** flaky expiry tests; use a fixed Instant and test the boundary at expiresAt.
- **Checking status only:** a request returning 403 may still cause mutations; re-read the DB.
- **Ignoring list/search/count:** resources from another tenant can leak in total result counts even when the detail endpoint blocks them.
- **Trusting client-declared input:** tenant, role, owner, and grantedBy must be verified server-side.
- **Syntactically valid but cross-tenant grant:** the database must reject invalid relationships, and the policy still enforces the tenant boundary.
- **Fixtures leaking state across tests:** standalone test runs will fail; reset seed/rollback for every case.

## 10. Acceptance Checklist

A dataset is considered sufficient to test this policy when it includes multiple users, at least two tenants, roles bound to memberships, PRIVATE/TENANT and OPEN/ARCHIVED resources, distinct owners, active/expired/revoked READ/WRITE relationships, and at least one multi-membership user. Tests must provide contrasting ALLOW/DENY cases, denied cross-tenant ADMIN access, VIEWER with WRITE not exceeding their role, data scoping at query/HTTP layers, and zero side effects on denied commands. IDs, Clock, and baseline must be deterministic so anyone re-running the suite obtains the exact same results.

The key takeaway is to intentionally include cases in the fixture that **appear authorized**—an ADMIN in another tenant, an EDITOR with a role in another tenant, a VIEWER granted WRITE, and a recipient with a grant on an ARCHIVED document—to verify that tenant boundaries, roles, relationships, and states cannot be bypassed.