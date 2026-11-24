# Implementing ACL with Inheritance and Share Revocation

## 1. Practice Objectives

An Access Control List (ACL) lets you assign permissions to **a specific object**, such as a folder, document, or record. When a document resides inside a folder, the application can allow the document to **inherit** read permissions from its parent folder. When the owner revokes a shared permission, the system must immediately produce a new decision without leaking the document through caches, list APIs, or other access paths.

This practice uses Spring Security ACL in a document management system to implement all three operations end to end:

1. **Granting permission:** adding an ACE (Access Control Entry) for a user or authority to a folder/document ACL.
2. **Permission inheritance:** linking a child ACL to a parent ACL and explicitly enabling or disabling inheritance.
3. **Revoking permission:** deleting a direct ACE, revoking permission on the parent ACL, or placing a DENY override / breaking inheritance on the child document according to the required scope.

After this lesson, you should be able to distinguish **deleting a grant record** from **blocking effective permission**; configure ACL/JDBC beans; write an ACL management service with operation-level permission checks; evaluate permissions via `hasPermission`; and test direct grants, inherited grants, revocations, and cross-tenant data.

This lesson belongs to **Spring Security - authorization / Integration Practice**. The Spring code below shows components to integrate into a database-backed Spring Boot 3.x/Spring Security 6.x application, not a standalone Java SE program. A standalone Java 17 program simulating inheritance/revocation is provided in section 9 to practice the rules before running integration tests.

## 2. Components of Spring Security ACL

| Component | Role |
|---|---|
| `ObjectIdentity` | Uniquely identifies a domain object: object type + ID. |
| `Acl` | An object's ACL, holding multiple ACEs, owner, parent ACL, and inheritance flag. |
| `AccessControlEntry` (ACE) | A rule containing SID, permission mask, `granting=true/false`, and audit flags. |
| `Sid` | Identity receiving the permission: `PrincipalSid` for a user or `GrantedAuthoritySid` for an authority. |
| `Permission` | Bit mask for actions. `BasePermission` includes READ, WRITE, CREATE, DELETE, ADMINISTRATION. |
| `MutableAcl` | Provides `insertAce`, `deleteAce`, `setParent`, `setEntriesInheriting`. |
| `MutableAclService` | `createAcl`, `readAclById`, `updateAcl`, `deleteAcl` to persist/load ACLs. |
| `JdbcMutableAclService` | JDBC implementation storing ACLs across four dedicated tables; requires DBMS-specific configuration. |
| `AclPermissionEvaluator` | Connects ACLs with method security expressions such as `hasPermission(...)`. |
| `LookupStrategy` and `AclCache` | Loads ACLs, including parent trees, and caches them to reduce repeated queries. |

The four foundational tables are `acl_sid` (identities), `acl_class` (domain types), `acl_object_identity` (each instance, parent, owner, inheritance flag), and `acl_entry` (ordered ACEs with mask, SID, granting). Spring Security ACL **does not automatically create ACLs when a repository saves an entity**: the application must proactively initialize and synchronize ACL lifecycle with resource lifecycle.

The ACL object owner does not automatically receive READ/WRITE on every object: the ACL owner is metadata for ACL administration under `AclAuthorizationStrategy`; data permissions must be represented and checked according to the application's policy. Nor should ACL owner, domain owner, and tenant administrator be conflated when those three concepts differ.

**Policies outside the ACL must still apply:** authenticated principal, active membership in the tenant owning the resource, existing non-deleted object, valid action, and the actor having permission to grant/revoke shares. `AclPermissionEvaluator` has no built-in knowledge of your product's tenant rules.

## 3. Problem Design and Sample Data

Suppose the application has two independent tenants A and B. A user can belong to multiple tenants with different roles; every resource carries `tenant_id`. Use **system-wide unique Long IDs** for Folder/Document in the example to avoid `ObjectIdentity` collisions; if IDs are only unique within each tenant, you must design JDBC-compatible object identities that include tenant scope or use a global key. Never use the descriptive names in the table below as real database keys.

### 3.1. Resource Tree

~~~text
Tenant A
└── Folder F10 "Aurora Project"      [parent ACL, owner alice]
    ├── Document D101 "Design"       [child ACL, inheriting=true]
    └── Document D102 "Plan"         [child ACL, inheriting=true]

Tenant B
└── Folder F20 "HR"                  [separate ACL, owner diana]
    └── Document D201 "Contract"     [tenant B child ACL]
~~~

Membership details:

| User | Tenant | Business Role | Meaning |
|---|---|---|---|
| alice | A | OWNER/EDITOR | Permitted to share folder F10 under the sample policy. |
| bob | A | VIEWER | Granted READ on F10, so he can read D101/D102 via inheritance. |
| carol | A | EDITOR | Granted WRITE directly on D101; does not automatically have SHARE unless policy permits. |
| diana | B | ADMIN | Cannot read F10/D101 merely because she is tenant B's ADMIN. |

Initial ACLs:

| Object | Direct ACE | Parent ACL | entriesInheriting |
|---|---|---|---|
| F10 | (bob, READ, ALLOW) | none | false/not applicable |
| D101 | (carol, WRITE, ALLOW) | F10 | true |
| D102 | none | F10 | true |
| F20 | (diana, READ, ALLOW) | none | false/not applicable |
| D201 | none | F20 | true |

**Initial expectations:** Bob can read both D101 and D102 due to the READ ACE on F10. Carol can edit D101 due to the direct WRITE ACE; she cannot implicitly edit D102. Diana cannot access tenant A's resources because the tenant boundary blocks before checking ACLs. WRITE and READ are distinct masks: never assume WRITE implicitly includes READ unless an explicit permission strategy defines that.

### 3.2. Revocation Contract

The phrase “revoke share permission” can mean several different things and must be clarified before acting:

- **Revoking a direct grant on D101:** deletes the recipient's ACE on D101. If the recipient still has READ via F10, deleting the ACE **does not remove** effective READ access.
- **Revoking a grant on F10:** deletes the ACE on F10; permissions inherited down to D101 and D102 disappear if no other grant exists.
- **Blocking Bob specifically on D101 while keeping Bob on F10:** creates a direct `DENY READ` ACE on D101 for Bob's SID according to verified policy and ACE ordering; D102 remains readable.
- **Cutting off all inheritance on D101:** `setEntriesInheriting(false)`; all ACEs present only on ancestors stop applying to D101. Direct ACEs on D101 remain intact.
- **Revoking Bob's membership from tenant A:** even if ACEs remain, the tenant policy outside the ACL must deny access. Residual grant rows may also need lifecycle cleanup.

Do not equate the three operations “delete ACE”, “deny on child”, and “setEntriesInheriting(false)”: they affect different users and permissions.

## 4. Inheritance Rules and Evaluation Order

A child ACL inherits ACEs from its parent only when **both** conditions hold:

1. The child ACL has a parent: `getParentAcl() != null`.
2. The child ACL enables inheritance: `isEntriesInheriting() == true`.

Simply linking parent and child is insufficient to propagate permissions. A parent may in turn point to a grandparent; cycles must never be created in the ACL tree.

With Spring Security's `DefaultPermissionGrantingStrategy`, the engine iterates through the requested permissions and SIDs in the supplied order, looking for matching ACEs on the current ACL; only when no matching ACE is found on the current ACL does it look up the parent (if inheritance is enabled). When a matching DENY ACE is found, the decision depends on the permission/SID lists and how the strategy processes them; in this practice, test **one permission and one PrincipalSid** so behavior is easy to verify. With multiple role/group SIDs or combined permission masks, test actual engine semantics rather than simplifying to “DENY always beats every ALLOW of every SID.”

| State | D101/Bob READ | D102/Bob READ | Reason |
|---|---|---|---|
| F10 has ALLOW READ Bob, both children inherit | ALLOW | ALLOW | Inherited from F10. |
| D101 has direct ACE DENY READ Bob | DENY | ALLOW | D101's local rule blocks before inheritance when SID/permission match. |
| Delete DENY on D101, parent still grants | ALLOW | ALLOW | Parent's grant surfaces again. |
| D101 disables inheritance, no direct READ | DENY | ALLOW | Child D101 does not receive F10's ACEs. |
| D101 re-enables inheritance, Bob's grant deleted on F10 | DENY | DENY | No remaining READ source from parent. |
| F10 revoked, yet D101 has direct ALLOW READ | ALLOW | DENY | Child's direct grant survives independently. |

This is the **single-SID/READ behavior matrix of the sample policy**. If the application uses shared role SIDs, custom permission masks, complex ACE ordering, or multi-level parent hierarchies, add corresponding tests. In particular, deleting a local ACE can **increase effective permissions** if the deleted local ACE was a DENY masking an inherited ALLOW — a frequently overlooked bug.

## 5. Preparing the Spring Boot Application and Database

### 5.1. Dependencies

In a Spring Boot 3.x/Spring Security 6.x application, add Spring Security ACL and JDBC (if not already present). Use the BOM/dependency management to keep all Spring Security libraries version-compatible:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.security:spring-security-acl")
    // JDBC driver for the DBMS, e.g., PostgreSQL, configured by the application
}
~~~

The application also needs the Spring MVC/Web starter when exposing REST controllers, plus Spring Security Test for integration tests. Spring Security 7 moves some **legacy Access APIs** like `AclEntryVoter` into a separate `spring-security-access` module; applications using only modern ACL/method security should not add the legacy module unless truly depending on those APIs.

### 5.2. Creating the ACL Schema

Create the four ACL tables according to the official JDBC schema for your **exact version and DBMS**. Overview of relationships:

~~~text
acl_class 1 ── * acl_object_identity * ── 1 acl_sid (owner)
                         │
                         │ parent_object (self reference)
                         ▼
                  acl_object_identity
                         │ 1
                         │
                         * acl_entry * ── 1 acl_sid (recipient)
~~~

Characteristic columns of `acl_object_identity`: `object_id_class`, `object_id_identity`, `parent_object`, `owner_sid`, `entries_inheriting`. `acl_entry` typically has `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting`, `audit_success`, `audit_failure`.

Do not copy default HSQLDB SQL into PostgreSQL without checking sequences/identities: the `JdbcMutableAclService` API documentation notes that default identity queries target HSQLDB and may require configuring `sidIdentityQuery`/`classIdentityQuery` or other queries for your actual database. Use Flyway/Liquibase migrations, foreign keys, uniqueness on object class/id, and indexes on parent/ACE SID. Manage schema via migrations, never letting runtime “best-effort” patch tables in production.

**Tenant constraint:** the default ACL tables do not include `tenant_id`. Domain Folder/Document entities must store `tenantId`; services creating parent ACLs must verify parent/child belong to the same tenant and the principal holds valid membership. Never let clients supply arbitrary class/id or parent objects to link ACLs across tenants. Sharing Long IDs across tenants requires careful identity design and testing.

### 5.3. Minimal Bean Configuration

The example below illustrates configuration beans following the Spring Security ACL documentation pattern. Standard Spring/Spring Security imports are omitted for brevity; this is a **snippet inside a @Configuration class** with matching dependencies:

~~~java
@EnableMethodSecurity
@Configuration
class AclConfiguration {
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    AclPermissionEvaluator aclPermissionEvaluator(AclService service) {
        return new AclPermissionEvaluator(service);
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource, LookupStrategy strategy, AclCache cache) {
        return new JdbcMutableAclService(dataSource, strategy, cache);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource source, AclCache cache,
            AclAuthorizationStrategy authStrategy,
            PermissionGrantingStrategy grantingStrategy) {
        return new BasicLookupStrategy(
                source, cache, authStrategy, grantingStrategy);
    }

    @Bean
    AclCache aclCache(PermissionGrantingStrategy grantingStrategy,
                      AclAuthorizationStrategy authStrategy) {
        return new SpringCacheBasedAclCache(
                new ConcurrentMapCache("aclCache"),
                grantingStrategy, authStrategy);
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
    }

    @Bean
    PermissionGrantingStrategy grantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger());
    }
}
~~~

In a real application, `ROLE_ACL_ADMIN` is just this example's choice, not every organization's default role. Checking ACL modification rights via `AclAuthorizationStrategy` **does not replace** business-level share/tenant/owner checks. `ConcurrentMapCache` illustrates a development setup; multi-instance production needs a clear cross-node caching and invalidation strategy, along with post-mutation consistency tests.

## 6. Creating Parent and Child ACLs with Inheritance

Initialize the ACL right after creating the domain record inside the appropriate transaction. Parent data must be verified through a repository; never allow requests to supply an `ObjectIdentity` pointing to another tenant. Core operation pattern:

~~~java
// Illustrative code in a service with MutableAclService aclService,
// Folder, Document domain classes, and @Transactional already configured.
@Transactional
public void initializeAcls(long folderId, long documentId) {
    ObjectIdentity folderOid =
            new ObjectIdentityImpl(Folder.class, folderId);
    ObjectIdentity documentOid =
            new ObjectIdentityImpl(Document.class, documentId);

    MutableAcl parent = aclService.createAcl(folderOid);
    Sid bob = new PrincipalSid("bob");
    parent.insertAce(
            parent.getEntries().size(), BasePermission.READ, bob, true);
    parent = aclService.updateAcl(parent);

    MutableAcl child = aclService.createAcl(documentOid);
    child.setParent(parent);
    child.setEntriesInheriting(true);
    aclService.updateAcl(child);
}
~~~

Here `Folder` and `Document` are actual application domain classes; the type name passed into `ObjectIdentityImpl` must be **consistent** with the type used in the permission evaluator. Creating a duplicate ACL for an object identity can throw `AlreadyExistsException`; create parent/child in order rather than unconditionally recreating on every request.

**Expected behavior after commit:** if Bob is verified as a tenant member of the Folder, `hasPermission(documentId, DocumentType, READ)` can return ALLOW on the child document via parent F10 even though the document has no direct READ ACE. When the permission evaluator is invoked from method security, also verify tenant/membership conditions using policies outside the ACL.

### 6.1. Verifying Results via the ACL API

Read using `AclService.readAclById(documentOid)` and inspect `getParentAcl()`, `isEntriesInheriting()`, and effective permissions. In a test using a fully loaded SID:

~~~java
Acl child = aclService.readAclById(
        new ObjectIdentityImpl(Document.class, documentId));
Sid bob = new PrincipalSid("bob");
boolean allowed = child.isGranted(
        List.of(BasePermission.READ), List.of(bob), false);
~~~

This example assumes the parent was persisted, cache/lookup loaded full SID details, and the default strategy is active. When no matching ACE exists, `Acl.isGranted` can throw `NotFoundException`; if SID information is not fully loaded, it can throw `UnloadedSidException`. In real security decision paths, situations that cannot prove ALLOW must **fail closed**. Never write a catch-all exception handler that returns true.

### 6.2. Using hasPermission in Method Security

Integration snippet in a service with `@EnableMethodSecurity` and the evaluator configured above:

~~~java
@PreAuthorize(
    "@tenantPolicy.isActiveMember(authentication, #tenantId) and " +
    "hasPermission(#documentId, 'com.example.domain.Document', 'READ')")
public DocumentDto getDocument(long tenantId, long documentId) {
    Document doc = documentRepository
            .findByIdAndTenantId(documentId, tenantId)
            .orElseThrow(DocumentNotFoundException::new);
    return mapper.toDto(doc);
}
~~~

This is an illustrative service fragment; `tenantPolicy`, repository, DTO, exception, and FQCN classes must exist in the application. The `hasPermission` evaluation runs before entering the method body, so ensure the object exists/belongs to the real tenant and prevent clients from spoofing the domain type. For sensitive data, consider a centralized policy service receiving the tenant-scoped object to avoid extra queries or leaking existence via error responses.

Remember that `hasPermission(#documentId, 'com.example.domain.Document', 'READ')` uses a type string; it must match the identity stored in the ACL (e.g., `Document.class` in its actual package). Depending on version, permission strings must map properly via PermissionFactory/evaluator. Do not assume different type strings point to the same ACL.

## 7. Granting and Revoking Direct Shares

### 7.1. Granting a READ ACE on the Right Object

From a service that has already verified the actor has SHARE permission, the recipient is a member in the same tenant, and the object exists:

~~~java
@Transactional
public void grantReadOnDocument(long documentId, String recipient) {
    ObjectIdentity oid = new ObjectIdentityImpl(
            Document.class, documentId);
    MutableAcl acl = (MutableAcl) aclService.readAclById(oid);
    Sid sid = new PrincipalSid(recipient);

    // Check for duplicate ACE by (Sid, permission, granting) before inserting.
    acl.insertAce(acl.getEntries().size(),
            BasePermission.READ, sid, true);
    aclService.updateAcl(acl);
}
~~~

This is core logic, **not a standalone production service**: validate actor, tenant, document state, recipient, and idempotency before calling. An ACL with duplicate or conflicting ACEs for the same SID/permission makes ACE ordering dictate behavior and complicates auditing. Ideally enforce an invariant allowing only one direct rule per SID + permission on an object, or define clear conflict-resolution rules.

### 7.2. Revoking a Direct ACE with deleteAce

Never delete “the ACE at index 0” by guesswork. Indexes in `getEntries()` can shift after every grant/revocation. Locate the exact SID, permission, and mask on the **selected ACL**, then delete from higher indexes down to lower ones so unprocessed indexes do not shift:

~~~java
@Transactional
public boolean revokeDirectRead(long documentId, String recipient) {
    ObjectIdentity oid = new ObjectIdentityImpl(
            Document.class, documentId);
    MutableAcl acl = (MutableAcl) aclService.readAclById(oid);
    Sid recipientSid = new PrincipalSid(recipient);
    boolean changed = false;

    for (int i = acl.getEntries().size() - 1; i >= 0; i--) {
        AccessControlEntry ace = acl.getEntries().get(i);
        if (ace.getSid().equals(recipientSid)
                && ace.getPermission().getMask()
                    == BasePermission.READ.getMask()
                && ace.isGranting()) {
            acl.deleteAce(i);
            changed = true;
        }
    }
    if (changed) {
        aclService.updateAcl(acl);
    }
    return changed;
}
~~~

In practice, share-revocation interfaces must distinguish *which grant is being removed*: recipient/user, resource, permission, grant issuer, and version; verify the **actor's** permission before editing. The sample code removes only the direct READ ALLOW ACE on the Document, leaving the parent untouched. If Bob still gets READ through F10, after deleting the direct READ grant on D101, Bob **can still read** D101 via inheritance. Reporting “all permissions revoked” in the UI in that situation is wrong.

With `JdbcMutableAclService.updateAcl`, the implementation may delete and re-insert ACE rows in the database on every update; prevent concurrent updates from losing changes by using appropriate transactions/locking. Never reuse stale ACE indexes after another update.

### 7.3. Revoking Permissions on the Parent and Impact on Descendants

If the policy is “remove Bob from the entire folder F10”:
1. Confirm the actor has management permission on **Folder F10** in the right tenant.
2. Locate and delete Bob's READ ALLOW ACE in **F10**'s ACL.
3. Call `aclService.updateAcl(parentAcl)`.
4. Verify Bob's effective permission on F10, D101, and D102 after commit; documents holding other direct READ ACEs may still return ALLOW.
5. Verify that ACL caches for parent/descendants were invalidated or reloaded properly, especially across multiple application nodes.

Never delete F10's `acl_object_identity` record just to revoke one share: `deleteAcl` removes the entire ACL object and can impact children, rather than revoking a single ACE. When deleting real resources, design cascade rules and descendant ACL state separately.

## 8. Blocking Inherited Permissions Specifically on a Child

### 8.1. Using a Specific DENY ACE

To let Bob keep READ on F10/D102 while **denying reading D101**, one approach is placing a local DENY for Bob's SID + READ on D101:

~~~java
MutableAcl child = (MutableAcl) aclService.readAclById(
        new ObjectIdentityImpl(Document.class, documentId));
child.insertAce(0, BasePermission.READ,
        new PrincipalSid("bob"), false);
aclService.updateAcl(child);
~~~

ACE ordering can alter outcomes when an ACL holds multiple rules or when a user has multiple SIDs; before inserting DENY, inspect and remove conflicting ACEs per policy. With a single PrincipalSid and single READ mask as in this exercise, DENY on the child can override ALLOW on the parent; with multiple group SIDs, real tests against `DefaultPermissionGrantingStrategy`/your configured strategy are the final authority.

**Revoking a DENY** means deleting the `granting=false` ACE on D101. Once deleted, if F10 still holds ALLOW READ Bob and D101 inherits, Bob can read D101 **again**. Therefore, “unblock” operations must be audited separately from “revoke grant” operations.

### 8.2. Using setEntriesInheriting(false)

If D101 must be detached from all parent permissions, set:

~~~java
MutableAcl child = (MutableAcl) aclService.readAclById(
        new ObjectIdentityImpl(Document.class, documentId));
child.setEntriesInheriting(false);
aclService.updateAcl(child);
~~~

This flag turns off **all ACEs inherited from the parent**, not just Bob READ. For instance, Carol with WRITE on D101 keeps her direct WRITE, while permissions from F10 for all other users/roles are lost as well. Never use this approach to revoke one user if the system needs to preserve other inherited permissions.

### 8.3. Comparing Effects

| Operation | D101 | D102 | Who Is Affected |
|---|---|---|---|
| Delete direct READ ALLOW on D101 | May still ALLOW via F10 | Unchanged | Recipient on D101; inheritance still active |
| Delete Bob's READ ALLOW on F10 | Loses inherited READ unless direct grant exists | Loses inherited READ | Bob across all inheriting descendants |
| Add DENY READ Bob on D101 | DENY for Bob per test policy | Unchanged | Only Bob/D101 |
| Disable inheritance on D101 | Receives no parent ACEs | Unchanged | Everyone receiving permissions from parent for D101 |
| Delete direct DENY Bob on D101 | May ALLOW again via F10 | Unchanged | Bob/D101 |

Avoid using “revoke permission” as a generic label for all these operations in APIs. APIs should express explicit *scope* (DIRECT_OBJECT / PARENT_TREE / OVERRIDE / INHERITANCE) and test exact scope effects; the enum names here are design examples, not Spring Security APIs.

## 9. Standalone Java 17 Program: Proving Semantics

To practice without Spring or a database, the small program below models **one SID + one permission** per ACL branch; local ALLOW/DENY takes precedence over parent; missing rules yield DENY. This model teaches inheritance mechanics and **does not replicate the full algorithm** of `DefaultPermissionGrantingStrategy` when multiple SIDs, complex masks, and exceptions are involved.

~~~java
import java.util.HashMap;
import java.util.Map;

public class AclInheritanceDemo {
    record Key(String user, String permission) {}

    static class Node {
        final String name;
        final Node parent;
        boolean entriesInheriting;
        final Map<Key, Boolean> local = new HashMap<>();

        Node(String name, Node parent, boolean entriesInheriting) {
            this.name = name;
            this.parent = parent;
            this.entriesInheriting = entriesInheriting;
        }

        void grant(String user, String permission) {
            local.put(new Key(user, permission), true);
        }

        void deny(String user, String permission) {
            local.put(new Key(user, permission), false);
        }

        void revokeLocal(String user, String permission) {
            local.remove(new Key(user, permission));
        }

        boolean allowed(String user, String permission) {
            Boolean direct = local.get(new Key(user, permission));
            if (direct != null) {
                return direct;
            }
            return entriesInheriting && parent != null
                    && parent.allowed(user, permission);
        }
    }

    static void check(String label, Node node, String user,
                      String permission, boolean expected) {
        boolean actual = node.allowed(user, permission);
        if (actual != expected) {
            throw new AssertionError(label + " expected=" + expected
                    + " actual=" + actual);
        }
        System.out.println(label + ": " + (actual ? "ALLOW" : "DENY"));
    }

    public static void main(String[] args) {
        Node folder = new Node("F10", null, false);
        Node design = new Node("D101", folder, true);
        Node plan = new Node("D102", folder, true);

        folder.grant("bob", "READ");
        design.grant("carol", "WRITE");

        check("inherit design", design, "bob", "READ", true);
        check("inherit plan", plan, "bob", "READ", true);
        check("no inherited write", plan, "carol", "WRITE", false);

        design.deny("bob", "READ");
        check("local deny", design, "bob", "READ", false);
        check("sibling unaffected", plan, "bob", "READ", true);

        design.revokeLocal("bob", "READ");
        check("deny removed reveals parent", design, "bob", "READ", true);

        design.entriesInheriting = false;
        check("inheritance disabled", design, "bob", "READ", false);
        check("direct write retained", design, "carol", "WRITE", true);

        design.entriesInheriting = true;
        folder.revokeLocal("bob", "READ");
        check("parent grant revoked", plan, "bob", "READ", false);
        check("child after parent revoke", design, "bob", "READ", false);

        design.grant("bob", "READ");
        check("child direct grant", design, "bob", "READ", true);
        design.revokeLocal("bob", "READ");
        check("child direct revoked", design, "bob", "READ", false);
    }
}
~~~

Save as `AclInheritanceDemo.java`, then compile and run:

~~~bash
javac --release 17 AclInheritanceDemo.java
java AclInheritanceDemo
~~~

Expected stdout:

~~~text
inherit design: ALLOW
inherit plan: ALLOW
no inherited write: DENY
local deny: DENY
sibling unaffected: ALLOW
deny removed reveals parent: ALLOW
inheritance disabled: DENY
direct write retained: ALLOW
parent grant revoked: DENY
child after parent revoke: DENY
child direct grant: ALLOW
child direct revoked: DENY
~~~

Explanation: READ on the folder flows down to children with inheritance enabled. Local DENY blocks inherited permission, yet deleting the DENY re-exposes the permission if the ancestor still grants it. Disabling inheritance drops only inherited permissions without removing direct WRITE. Revoking the parent grant blocks all children that relied on the parent; a direct grant on a child can still confer separate permission. Because of these states, post-revocation tests **must verify effective permission**, not merely assert that a row in `acl_entry` was deleted.

## 10. Sharing APIs and Security Boundaries

Suppose the controller exposes these endpoints:

~~~text
POST   /api/tenants/{tenantId}/folders/{folderId}/shares
DELETE /api/tenants/{tenantId}/folders/{folderId}/shares/{recipient}
POST   /api/tenants/{tenantId}/documents/{documentId}/shares
DELETE /api/tenants/{tenantId}/documents/{documentId}/shares/{recipient}
PATCH  /api/tenants/{tenantId}/documents/{documentId}/inheritance
GET    /api/tenants/{tenantId}/documents/{documentId}
~~~

This is a **business API sketch**, not endpoints automatically generated by Spring Security ACL. Every request must perform:
1. Extract actor from the authenticated principal; verify active tenant membership.
2. Load Folder/Document **by tenantId and objectId** from the repository. Never call only `findById` and trust a client-supplied tenant.
3. For SHARE/REVOKE/CHANGE_INHERITANCE, verify the actor has share-management permission (owner, right-tenant admin, or custom policy). Never let the recipient self-grant permissions.
4. Verify the recipient is a member of the same tenant and the permission is in the allowed set; if applying an ACL to a role SID, that role must belong to the right tenant.
5. When changing a parent ACL, verify parent/child belong to the same tenant, no cycles are introduced, and the document is not moved into an unauthorized folder.
6. Persist the domain mutation and ACL mutation within the configured transaction; after commit refresh/invalidate caches so subsequent reads reflect the result.
7. Audit actor/tenant/resource/recipient/action/scope/before/after. Do not log tokens or unnecessary sensitive data.

Return 403 if the actor lacks SHARE permission, or 404 for undisclosed resources per the API contract; pick a consistent contract and test it. For DELETE share, define idempotency: deleting a nonexistent grant may return 204/404 per contract, yet **must never delete another ACE by mistake**.

### 10.1. Caution with PrincipalSid and GrantedAuthoritySid

`new PrincipalSid("bob")` identifies a user, whereas `new GrantedAuthoritySid("ROLE_EDITOR")` is an authority that may apply to multiple users. Sharing via a group/role can let Bob keep access even after his personal ACE is deleted. When revoking “all of Bob's permissions,” evaluate **every SID Bob currently holds**, not only `PrincipalSid("bob")`. In multi-tenancy, authority names must be tenant-scoped or checked against membership before evaluating ACLs.

## 11. Integration Testing Against a Real Database

### 11.1. Seeding and Sequences

Use a dedicated test database (such as Testcontainers) with ACL schema migrations matching the DBMS. Seed:
- Tenants A/B, users Alice/Bob/Carol/Diana, and memberships.
- Folders F10/F20, Documents D101/D102/D201.
- ACL F10 (Bob READ ALLOW), ACL D101 (parent F10, inherit=true, Carol WRITE ALLOW), ACL D102 (parent F10, inherit=true), separate ACLs for B.
- Test authentication constructs the corresponding principal; never treat role/tenant from an HTTP body as truth.

Each test needs a clean baseline or intentional transaction rollback and proper cache resets; revocation tests must not depend on execution order or results of prior tests.

### 11.2. Required Test Matrix

| Test | Before Operation | Operation | Expected After Operation |
|---|---|---|---|
| Inherit READ | Bob READ D101/D102 = ALLOW | Unchanged | Keeps ALLOW on both children. |
| Direct WRITE | Carol WRITE D101 = ALLOW | Unchanged | Carol cannot WRITE D102. |
| Child deny | Bob READ D101/D102 = ALLOW | Insert DENY Bob READ D101 | D101 DENY; D102 ALLOW. |
| Remove DENY | D101 DENY; F10 ALLOW | Delete local DENY D101 | D101 returns to ALLOW. |
| Disable inheritance | F10 grants READ Bob | D101 setEntriesInheriting(false) | D101 DENY if no direct READ; D102 ALLOW. |
| Re-enable inheritance | D101 inherit=false | setEntriesInheriting(true) | D101 ALLOW if parent grant remains. |
| Revoke parent | F10 grants READ Bob | Delete Bob READ ALLOW F10 | D101/D102 DENY if no other direct READ. |
| Direct grant survives | F10 grant; D101 direct READ Bob | Revoke Bob on F10 | D101 ALLOW; D102 DENY. |
| Cross-tenant | Diana ADMIN B | READ/share D101 tenant A | DENY; A's ACL unchanged. |
| Missing ACL/SID | No matching rule | Invalid read | DENY/fail closed, no 500 leaking metadata. |
| Group SID | Bob holds authority granted on F10 | Delete Bob's personal ACE | May still ALLOW via group; per policy. |
| Concurrent revoke | Grant exists; two parallel updates | Revoke + grant/update | No silent overwrite; clear final state per contract. |
| Stale cache | Bob read before revocation | Revoke then read again via another node | Permissions update per consistency guarantee. |

Do not stop at asserting ACE counts. For each case, reload the fresh ACL from the database, test `hasPermission` with a real test principal, and call REST GET/UPDATE where applicable. **DENY must mean responses leak no data and mutations produce no side effects.**

### 11.3. Guiding Test Example

In a test class already configured with `MockMvc`, authentication, repositories, ACL beans, and seed data, the snippet below shows the flow to test (not standalone compilable):

~~~java
// 1. Let Bob read D101 before revocation.
mvc.perform(get("/api/tenants/A/documents/101")
        .with(user("bob").roles("VIEWER")))
    .andExpect(status().isOk());

// 2. Alice revokes Bob's READ permission on folder F10.
mvc.perform(delete("/api/tenants/A/folders/10/shares/bob")
        .with(user("alice").roles("OWNER"))
        .with(csrf()))
    .andExpect(status().isNoContent());

// 3. Bob no longer has inherited READ on D101 and D102
// if neither document has another direct READ grant.
mvc.perform(get("/api/tenants/A/documents/101")
        .with(user("bob").roles("VIEWER")))
    .andExpect(status().isForbidden());
~~~

Status codes are illustrative contract choices (an application may choose 404 for denied objects). In apps using CSRF, supply a valid token to distinguish CSRF errors from authorization errors; for stateless Bearer APIs, use the corresponding test authentication mechanism. Tests must ensure the second read genuinely traverses policy and cache after revocation rather than reading an object memoized in a single request.

### 11.4. Checking Queries and Performance

Listing 100 documents and calling `hasPermission` per item can cause N+1 ACL lookups. When evaluating many IDs, consider `AclService.readAclsById(objectIdentities, sids)`, ACL batch/cache mechanisms, or permission-filtered list queries before pagination. Never load all documents and apply `@PostFilter` after `LIMIT` because pagination/totals can break; design permission query projections equivalent to the ACL engine, especially when inheritance and DENY ACEs exist.

## 12. Caching, Transactions, and Concurrency During Revocation

Revoking permissions often poses greater security risk than granting them because **stale ALLOW decisions** can linger in caches.

- **Cache at the ACL layer:** verify `AclCache` evicts modified ACLs on `updateAcl`, and separately evaluate loaded/cached child ACLs when parents change. Never assume updating a parent automatically synchronizes every child across every node.
- **Cache at the service/UI layer:** any `canRead`/`canWrite` cache keyed by user + tenant + resource + permission needs invalidation, policy versioning, or a tight TTL matching the contract. Never cache ALLOW results indefinitely.
- **Multiple instances:** `ConcurrentMapCache` lives inside one JVM; multi-node production needs reliable invalidation events or shared caching, tested by revoking on node A and reading from node B.
- **Transaction boundaries:** `updateAcl` may delete and re-insert ACEs; use transactions to avoid half-written state, and prevent lost updates when two actors edit an ACL concurrently (optimistic locking/domain version, per-object lock, or serialization).
- **TOCTOU:** permission may be revoked after the check step yet before mutation; for sensitive operations, evaluate permission inside an appropriate transaction/lock or recheck at write time per the threat model.
- **Auditing:** record who granted/revoked, timestamp, tenant, SID, resource, direct vs. inherited; also trace toggling inheritance and changing parents.
- **Failure semantics:** when ACL lookup misses, SIDs are unloaded, cache fails, or database errors occur, never return ALLOW. Instead of catching exceptions and granting fallback access, fail closed and log enough detail for investigation.

An “immediate revocation” policy must define whether it means **immediately after commit across all nodes** or within a bounded delay, and test accordingly. Never promise immediate consistency if distributed caches lack guaranteed invalidation.

## 13. Common Implementation Mistakes

1. **Calling only `setParent`:** forgetting `setEntriesInheriting(true)`, resulting in no inherited permissions.
2. **Deleting a direct ACE and assuming everything is revoked:** parent or group SIDs may still grant access.
3. **Using `setEntriesInheriting(false)` to revoke one user:** accidentally blocks all other users' inherited permissions.
4. **Adding DENY without control:** ACE ordering, multiple SIDs, and permission masks can produce unexpected results.
5. **Treating ACL owner as having full data rights:** ownership and permissions must follow business specifications.
6. **Not separating tenants:** colliding SIDs or ObjectIdentity IDs across tenants can cause cross-tenant access.
7. **Letting clients specify arbitrary object types/parents:** can create ACLs for other tenants' objects, cross trees, or form cycles.
8. **Forgetting to initialize ACLs:** domain record exists while `readAclById` misses, and handlers accidentally default to allow.
9. **Reusing ACE indexes after updates:** deletes the wrong user's grant; always match by SID/mask and account for shifting indexes.
10. **Asserting only database rows:** caches or parents keep effective permission as ALLOW.
11. **Forgetting group SIDs:** revoking PrincipalSid does not remove permissions still granted via authority SIDs.
12. **Treating `updateAcl` as trivial needing no locks:** concurrent updates can overwrite each other or unexpectedly delete/recreate ACEs.
13. **Using `@PostFilter` for paginated lists:** can return under-filled pages and leak counts; design query/batch evaluation with matching semantics.
14. **Checking permissions only in controllers:** services invoked by jobs/schedulers or other APIs can still modify data; protect the true business boundary.

## 14. Practice Completion Checklist

An ACL inheritance and revocation implementation meets requirements when:

- Every Folder/Document has a stable object identity, proper tenant, valid schema, and acyclic parent ACL.
- Inheritance works only when a parent exists and `entriesInheriting=true`, matching multi-level expectations.
- Grant APIs are executed only by actors with share rights; same-tenant recipients/memberships are verified.
- Revocation APIs state their scope explicitly: delete direct grant, delete parent grant, add DENY override, or disable inheritance.
- For every operation, **effective permissions** of recipients are checked before and after; remaining grants via parent/group are accurately explained.
- Negative tests cover cross-tenant access, missing ACLs, duplicate grants, concurrent updates, stale caches, and no-side-effects on DENY.
- ACL data updates consistently inside transactions, and cache/policy invalidation is verified across all relevant nodes.
- `Permission`, `Role`, `Sid`, `Owner`, and `Tenant membership` are never conflated.

**Core takeaway:** in an inheriting ACL model, effective permissions are computed from the current ACL **and potentially the parent ACL chain**, combined with tenant/role policies outside the ACL. Revoking one ACE only removes one decision source; to truly block access, you must prove no other valid ALLOW path remains.

## 15. Official Documentation

- Spring Security — Domain Object Security (ACLs): https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html
- Spring Security — `Acl` interface and inheritance: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html
- Spring Security — `MutableAcl` interface: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAcl.html
- Spring Security — `JdbcMutableAclService`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html
- Spring Security — `DefaultPermissionGrantingStrategy`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
