# ACL Inheritance from Parent Objects and Limiting Permission Propagation

> **Topic:** Spring Security – authorization · **Group:** ACL Foundation. This lesson focuses on **parent–child ACLs** in the domain-object security model: `parentAcl`, the `entriesInheriting` flag, ACE evaluation order, how to stop inheritance, restricting propagation by policy, and risks when resources span multiple tenants. Illustrative API scope: Spring Security ACL 6.x/7.x on Servlet, Spring Framework, and Java 17+. This is Spring Security's ACL mechanism, not to be confused with role hierarchies or default OS directory permissions.

## 1. The Problem and Learning Outcomes

An application stores a hierarchy:

~~~text
Workspace A
  |
  +-- Folder F (parent ACL)
        |
        +-- Document D1 (child ACL, inheriting)
        |
        +-- Document D2 (child ACL, non-inheriting)
        |
        +-- Subfolder S
               |
               +-- Document D3
~~~

The `ROLE_REVIEWER` group is granted **READ** on Folder F. Should it automatically read D1? D2? D3? If Folder F is also granted **WRITE**, can it edit D1? If D1 holds more sensitive content than Folder F, can **WRITE be blocked specifically at D1**? If Folder F is later moved to tenant B, what must be checked?

This is the problem of **permission propagation through parent–child ACL relationships**. Never answer intuitively "whatever permission the parent folder has applies to every child file," because Spring Security uses an inheritance flag and a specific ACE evaluation sequence.

After this lesson, you will be able to:

1. Distinguish **domain parent relationships** from **parent ACL links** and **ACE inheritance**.
2. Understand `Acl.getParentAcl()`, `Acl.isEntriesInheriting()`, and `MutableAcl.setParent(...)`/`setEntriesInheriting(...)`.
3. Predict authorization decisions when the child ACL has a matching ACE, when only the parent has an ACE, when inheritance is cut off, and when no ACE is found anywhere.
4. Distinguish `NotFoundException` from a DENY ACE; never treat "no ACE found" as GRANT.
5. Configure relationship creation/updates via `MutableAclService`, `updateAcl`, and ACL storage/cache.
6. Design tenant boundaries, sensitive-document boundaries, read-only propagation policies, and safe reparent/revoke handling.
7. Test inheritance/deny/stop in Spring ACL and a standalone Java 17 program; understand the boundaries of each test.

## 2. Concepts That Must Be Separated

| Concept | Role in Spring Security ACL |
| --- | --- |
| `ObjectIdentity` | Identifies *a protected object* (type + ID), e.g., Document 501 |
| `Acl` | Permission policy bound to an ObjectIdentity, containing direct ACEs and parent reference |
| `AccessControlEntry` (ACE) | A permission entry for a SID on an object: permission, grant/deny, order, audit flags |
| `Sid` | Security identity: principal (`PrincipalSid`) or authority (`GrantedAuthoritySid`) |
| `Permission` | Rights such as `BasePermission.READ`/`WRITE`/`DELETE`/`ADMINISTRATION` |
| `parentAcl` | Linked parent ACL for navigation/looking up inherited permissions |
| `entriesInheriting` | Whether falling back to the parent ACL is allowed during evaluation |
| `AclService` | Reads ACLs from storage/cache |
| `MutableAclService` | Creates/updates/deletes ACLs, persists parent links and ACEs |
| `PermissionGrantingStrategy` | Algorithm evaluating ACEs, e.g., `DefaultPermissionGrantingStrategy` |
| `AclPermissionEvaluator` | Connects `hasPermission(...)` in method security to `AclService` |

**Important:** A document having `folderId=12` in a business table **does not mean** the document's ACL automatically has Folder 12's ACL as its parent. The two structures can diverge. The application must explicitly set `parent_object` and `entries_inheriting` in ACL data, or invoke the API to establish the link.

### 2.1. Three Layers of Relationships

~~~text
Data relationship:      Document D1.folderId = F.id
                                 |
ACL relationship:       ACL(D1).parentAcl = ACL(F)
                                 |
Inheritance flag:       ACL(D1).entriesInheriting = true
~~~

For D1 to inherit ACEs from F under the default mechanism, having only the first or second relationship is not enough: at lookup time on the child ACL, **both a parent ACL and enabled inheritance must exist**. Turning off the flag at an intermediate level stops traversal up to grandparents.

### 2.2. Inheritance Here Is Not Copying ACEs

If F grants `READ` to Alice, and D1 enables inheritance without a local Alice READ ACE, Spring can **walk up to ACL(F)** to look it up. It **does not copy** a READ ACE row into ACL(D1). `child.getEntries()` returns the child's direct ACEs, not an aggregated list of all inherited parent ACEs; to **decide permissions**, always use `Acl.isGranted(...)` or an appropriate evaluator.

This creates a major consequence: modifying an ACE on F can affect many inheriting children without updating each child individually. In system design, this is both an administrative convenience and a **blast radius that must be controlled**.

## 3. Where Does JDBC Data Represent Inherited Permissions?

Spring Security ACL has four core tables:

- `acl_sid`: principals or granted authorities known to the ACL system.
- `acl_class`: protected domain object types.
- `acl_object_identity`: each object; holds `parent_object`, `entries_inheriting`, and owner SID.
- `acl_entry`: direct ACEs; holds `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting`, and audit flags.

Key columns involved:

~~~sql
-- Simplified structure to explain meaning, NOT a full migration with constraints.
acl_object_identity (
    id,
    object_id_class,
    object_id_identity,
    parent_object,       -- FK to a parent ACL row
    owner_sid,
    entries_inheriting   -- boolean: whether to consult parent permissions when needed
)

acl_entry (
    acl_object_identity,
    ace_order,
    sid,
    mask,
    granting,
    audit_success,
    audit_failure
)
~~~

`parent_object` represents the parent link. `entries_inheriting` indicates whether parent ACEs may be consulted when the decision algorithm needs to fall back. `ace_order` tracks ACE sequence; never assume every DENY ACE "always beats" every GRANT ACE regardless of order and SID.

Conceptual data example:

| ACL object | parent_object | entries_inheriting | Direct ACEs |
| --- | --- | --- | --- |
| Folder F | null | false | Alice READ = GRANT; Alice WRITE = GRANT |
| Document D1 | ACL(F) | true | No ACEs |
| Document D2 | ACL(F) | false | No ACEs |
| Document D3 | ACL(F) | true | Alice WRITE = DENY |

With a single Alice SID and each permission queried individually:
- D1 READ and WRITE can be inherited from F.
- D2 READ and WRITE do not traverse to F, because `entries_inheriting=false`.
- D3 WRITE is DENIED by its local ACE, and does not walk up to F's GRANT WRITE to override it.

**Never edit `parent_object` directly in SQL outside the ACL system expecting the cache to sync automatically.** In apps using `AclCache`, changes must evict/update properly; use `MutableAclService` and test against your actual database schema.

## 4. Default Algorithm: Check Child ACEs First, Then Parent

`Acl.isGranted(List<Permission>, List<Sid>, boolean administrativeMode)` is the permission decision API. In `AclImpl`, this delegates to `PermissionGrantingStrategy`, typically `DefaultPermissionGrantingStrategy`. To understand inheritance properly, examine **one permission and one SID first**.

~~~text
check(childAcl, Alice, READ)
   |
   +-- find matching ACE in childAcl
   |       |
   |       +-- GRANT found => true
   |       |
   |       +-- DENY found  => false
   |
   +-- no matching ACE in childAcl
           |
           +-- entriesInheriting = false => do not consult parent
           |
           +-- entriesInheriting = true and parentAcl != null
                   |
                   +-- evaluate parentAcl
                           |
                           +-- parent has matching ACE => grant/deny
                           +-- if still none => may continue to grandparent
   |
   +-- reached root with no ACE => NotFoundException
~~~

Note the three outcomes at the `Acl.isGranted` level in the default implementation: **true**, **false**, and **an exception when no decision is found**. Finding no ACE **is not** a default allow. An outer `AclPermissionEvaluator`/policy may translate results/exceptions into denials or other behavior per configuration; never assume everything turns into HTTP 403 or the same exception type.

### 4.1. Minimal Scenario Matrix

Legend: `G` = GRANT ACE, `D` = DENY ACE, `—` = no matching ACE for Alice/READ.

| Local D1 READ ACE | D1 inherits? | F READ ACE | `D1.isGranted(READ, Alice, false)` |
| --- | --- | --- | --- |
| — | true | G | **true** via parent |
| — | true | D | **false** via parent |
| — | false | G | **NotFoundException** (if no other decision source) |
| — | true | — | **NotFoundException** if no ACE exists in the tree |
| G | true | D | **true**, local grant evaluated on child |
| D | true | G | **false**, local deny stops this path |
| G | false | D | **true**, local grant present so parent not needed |
| D | false | G | **false**, local deny |
| — | false | — | **NotFoundException** |

This table is intentionally scoped to **one SID, one permission, and `DefaultPermissionGrantingStrategy`**. In real systems, an `Authentication` typically holds both a `PrincipalSid` and multiple `GrantedAuthoritySid`s; outcomes depend on permission/SID order and multiple ACEs. Thus, never turn a single-SID table into an absolute rule that "a child deny for one SID always blocks every grant for every SID."

### 4.2. Permission and SID Evaluation Order Matters

The `DefaultPermissionGrantingStrategy` Javadoc describes iterating **permissions in requested order**, then **SIDs in list order**, looking for the first ACE matching the permission:SID pair. If that ACE is GRANT, the algorithm returns true; if it is DENY, it proceeds to check remaining permissions. Only when **no matching ACE exists** on the current ACL does it try the parent (if inheritance is enabled). With multiple permissions or SIDs, the decision is also shaped by list order and how the implementation compares masks.

This leads to key principles:
- Keep ACE, SID, and permission ordering intentional; test with real principal + authority combinations.
- Do not describe ACLs like a simple firewall where "DENY anywhere in the tree always wins."
- Do not loop over `getEntries()` directly to pick first/last ACEs yourself when `isGranted` can be used.
- If you need a **mandatory deny for an entire tenant or locked account status**, enforce that constraint in an independent policy layer rather than relying on a single ACE that multiple SIDs might bypass.

### 4.3. Permission Masks Are Not Per-Document Bit Slots

`BasePermission` includes common permissions: READ, WRITE, CREATE, DELETE, ADMINISTRATION. Each permission is a bitmask; the system can hold huge numbers of documents without allocating a bit per document. Alice's same READ mask is evaluated separately against each document's `ObjectIdentity`.

Never assume WRITE implies READ or ADMINISTRATION inherits all capabilities unless your policy is designed that way. Masks can be combined via custom `Permission` types or mask matchers, but always test exact behavior with your active implementation.

## 5. Limiting Propagation: More Than One Boolean Flag

The `entriesInheriting` flag controls **whether to consult the parent when no matching ACE is found**. It is not a built-in allow-list saying "inherit only READ, do not inherit WRITE." With default ACL inheritance, if a child has no matching ACE and enables inheritance, READ/WRITE/DELETE/... can all walk up via the same mechanism.

### 5.1. Cutting Off Inheritance Completely at a Sensitive Child

To prevent D2 from inheriting from F:

~~~java
// Snippet using MutableAcl retrieved via MutableAclService.
childAcl.setParent(parentAcl);       // retains navigation link
childAcl.setEntriesInheriting(false); // does not inherit ACEs from parent
mutableAclService.updateAcl(childAcl);
~~~

Consequence: D2 retains only its direct ACEs; if no ACE matches a SID/permission, `isGranted` can throw `NotFoundException`, and outer policy must handle it safely. **This does not mean everyone is blocked** if D2 has local GRANT ACEs.

Use when:
- A document holds more sensitive data than its general folder.
- A resource's permissions are "frozen" so they do not track changes to parent groups.
- A resource moves to a different security zone requiring an isolated ACL.
- A subtree must follow a different retention/compliance policy.

Important check: disabling inheritance **does not delete** existing local ACEs. Nor does it guarantee all descendants of D2 stop inheriting: if D3 inherits from D2, D3 can still inherit **D2's local ACEs**, though it will not traverse past D2 up to F while D2 stops at itself.

### 5.2. Wanting Only READ to Propagate, Not WRITE?

This is a common requirement that calls for explicit design. Three options:

**Option A — Disable inheritance, create local ACEs for retained permissions.**

- Keep the parent link for navigation if needed, but call `setEntriesInheriting(false)` on the child document.
- Grant explicit READ to permitted SIDs on the child document; do not grant WRITE.
- When the parent ACL changes, update/sync local ACEs via a dedicated process if policy requires child permissions to follow. **Not automatic** because inheritance is off.

Pros: clear boundaries, easy auditing; cons: requires ACE sync management, more rows, and added complexity when group memberships change.

**Option B — Enable inheritance, add local ACEs blocking WRITE as appropriate.**

- D1 inherits to reuse parent READ.
- Add local WRITE = DENY ACEs for the specific SIDs or groups to block.
- For a given SID and WRITE permission, the local DENY blocks parent lookup for that pair.

**Warning:** this is **not a general guarantee that "everyone is blocked from WRITE."** Users may hold multiple SIDs and other ACEs; SID/permission evaluation order, other roles, or custom strategies may yield a grant. You need a test matrix covering every applicable principal/role; for high-risk data, prefer cutting inheritance or enforcing a required policy "sensitive child => deny write" outside the ACL.

**Option C — Additional policy wrapping the ACL.**

For example, business policy requires:
- For READ: accept ACL READ across the hierarchy.
- For WRITE: in addition to ACL WRITE, require the service-level `document:write` capability and valid state/tenant.
- For classified documents: deny mutations regardless of parent ACL, except via a separately governed/audited break-glass workflow.

This fits when a single all-or-nothing inheritance flag cannot express per-action permission boundaries. However, the policy must be **genuinely enforced**, not merely hidden in the UI.

### 5.3. Multi-Level Permission Propagation

~~~text
Root ACL: Alice READ = G
   |
   v   entriesInheriting = true
Folder ACL: no Alice READ ACE
   |
   v   entriesInheriting = true
Doc ACL: no Alice READ ACE
   |
   +--> reads from Root => GRANT
~~~

If Folder has `entriesInheriting=false` and Folder **has no local READ**, Doc cannot "skip over" Folder to Root under the default mechanism. If Folder has a local READ GRANT, Doc can still inherit **Folder's own grant** when Doc inherits from Folder.

There is no standard toggle meaning "look at grandparent while skipping parent." Achieving that requires a different parent structure or custom strategy, which can hurt tree auditability.

## 6. How Many Objects Does One Parent Change Affect?

When multiple children inherit from F, a change such as:

~~~text
Before:
ACL(F) -> group REVIEWERS: READ = G
D1: inherits = true
D2: inherits = false
S : inherits = true, D3 inherits S

After:
ACL(F) -> remove REVIEWERS READ
~~~

Expected results:
- D1 no longer receives the READ grant from F, unless it has a local ACE or another grant source.
- D2 is unaffected **via inheritance** from F because the flag is off; D2's local ACEs remain intact.
- D3 may be affected if both S and D3 inherit and neither S nor D3 has an ACE stopping fallback.
- If S already has a local READ GRANT, D3 can still receive GRANT even after F removes its ACE.

Conversely, adding a WRITE grant on F can inadvertently expose WRITE down to inheriting children. Therefore, when widening permissions on a "shared folder," audit **all affected descendants**, not just the folder itself.

### 6.1. Impact Matrix Before Modifying a Parent ACL

| Change | Impact to Inspect |
| --- | --- |
| Grant additional READ on parent | Which children inherit and lack a local decision? |
| Grant WRITE/DELETE on parent | Are there sensitive/immutable child documents? |
| Revoke parent permission | Which children rely on inherited access and will lose it? |
| Add local GRANT on child | Does it widen access beyond parent policy? |
| Add local DENY on child | Does it block the right SID/permission or leave another authority path open? |
| `entriesInheriting true → false` | Will parent-only permissions be lost? |
| `entriesInheriting false → true` | Will unexpected permissions suddenly flow from the parent? |
| Reparent child to another folder | Does tenant/scope change, and what rights come from the new parent? |
| Delete parent | What links remain on child ACLs, and is the cascade policy appropriate? |
| Modify group membership | Do authority-based SIDs update in fresh Authentications? |

## 7. Linking Parent ACLs with `MutableAclService`

Spring ACL JDBC provides `MutableAclService` to perform updates rather than issuing raw SQL and forgetting the cache. Below is an **illustrative service method in an ACL-configured application**, not a standalone runnable Spring Boot program. It requires `MutableAclService`, `scopePolicy`, and domain repositories to exist.

~~~java
// Lives inside an ACL management @Service, with injected dependencies.
// Call only from authenticated and authorized admin paths.
@Transactional
@PreAuthorize("hasAuthority('acl:manage')")
public void reparentDocument(long documentId, long folderId,
                             boolean inheritEntries) {
    // Domain policy must verify: same tenant, valid parent, no cycle,
    // and caller has permission to edit ACLs of BOTH document and folder.
    scopePolicy.assertAllowedReparent(documentId, folderId);

    ObjectIdentity childId =
            new ObjectIdentityImpl("com.example.domain.Document", documentId);
    ObjectIdentity parentId =
            new ObjectIdentityImpl("com.example.domain.Folder", folderId);

    MutableAcl child = (MutableAcl) mutableAclService.readAclById(childId);
    Acl parent = mutableAclService.readAclById(parentId);

    child.setParent(parent);
    child.setEntriesInheriting(inheritEntries);
    mutableAclService.updateAcl(child);
}
~~~

Key imports: `org.springframework.security.acls.model.ObjectIdentity`, `Acl`, `MutableAcl`, `org.springframework.security.acls.domain.ObjectIdentityImpl`, `org.springframework.transaction.annotation.Transactional`, `org.springframework.security.access.prepost.PreAuthorize`.

This is an **excerpt**: `scopePolicy` must be implemented by your application; it is not a built-in Spring API. Clearly separate ACL-editing policies from document-viewing policies:
- **Reading a Document** requires READ permission on the Document.
- **Changing a Document's parent ACL** requires verified ACL administration capability, often with rights on both parent and child.
- Being able to READ the parent **does not automatically grant** permission to alter `parentAcl` or `entriesInheriting`.
- Never take a client-supplied `folderId` and allow reparenting to another tenant's ACL. Validate both domain and ACL relationships under proper transactions/locking.

### 7.1. When Creating a New Child ACL

~~~java
// Business snippet (within a valid ACL-provisioning transaction/workflow).
ObjectIdentity childId =
        new ObjectIdentityImpl("com.example.domain.Document", newDocumentId);
ObjectIdentity parentId =
        new ObjectIdentityImpl("com.example.domain.Folder", folderId);

Acl parent = mutableAclService.readAclById(parentId);
MutableAcl child = mutableAclService.createAcl(childId);
child.setParent(parent);
child.setEntriesInheriting(true);
mutableAclService.updateAcl(child);
~~~

`createAcl` creates a new ACL for the `ObjectIdentity`, and `updateAcl` persists changes. If the `ObjectIdentity` already exists, `createAcl` can throw `AlreadyExistsException`; `updateAcl` on a missing record can throw `NotFoundException`. Do not call `new AclImpl(...)` expecting `updateAcl` to insert the DB row automatically. For batch creation of many objects, maintain consistency if domain persistence succeeds while ACL creation fails; use transactions, outbox, or compensating workflows depending on infrastructure.

### 7.2. Modifying Parent Permissions

~~~java
// Snippet after verifying ACL administration permission.
MutableAcl folderAcl =
        (MutableAcl) mutableAclService.readAclById(parentId);
folderAcl.insertAce(
        folderAcl.getEntries().size(),
        BasePermission.READ,
        new GrantedAuthoritySid("ROLE_REVIEWER"),
        true
);
mutableAclService.updateAcl(folderAcl);
~~~

`getEntries()` lists local ACEs, not effective permissions from parents. When adding ACEs, `ace_order` matters; in practice, check for duplicate ACEs and ordering conventions before inserting. The snippet assumes `getEntries()` returns a valid list in your implementation; in robust code, handle missing local entries per API/version and avoid duplicates.

ACL mutation in `AclImpl` is also governed by `AclAuthorizationStrategy`. Having `@PreAuthorize('acl:manage')` alone **does not bypass** that strategy's owner/permission checks. Configure `AclAuthorizationStrategyImpl` with appropriate administrative authorities and **least privilege**; never attach admin authority to every request to work around permission errors.

### 7.3. Cutting Off Inheritance Without Deleting the Parent Link

~~~java
MutableAcl child =
        (MutableAcl) mutableAclService.readAclById(childId);
child.setEntriesInheriting(false);
mutableAclService.updateAcl(child);
~~~

You do not need to call `child.setParent(null)` if you still want to retain the ACL navigation link. Setting the flag to `false` creates the boundary blocking fallback to parent ACEs. On the other hand, if the domain genuinely changes ownership and the old parent is no longer valid, update or clear the link by design rather than leaving an outdated parent.

### 7.4. Cycles and Unsafe Reparenting

A valid ACL tree must **not contain cycles** such as A → B → A; otherwise, parent traversal can loop infinitely or fail. Do not rely on a parent FK constraint to prevent cycles — an FK does not stop circular references. Domain services must enforce acyclicity and tenant boundaries on reparent; under concurrency, use locking/transactions so two requests cannot jointly create a cycle. Never accept arbitrary parent `ObjectIdentity` types from clients.

## 8. Configuring Spring ACL with JDBC and Method Security

In a Spring Boot Servlet project with an existing `DataSource`, ACL tables, and the `spring-security-acl` dependency, the common setup wires `JdbcMutableAclService`, `BasicLookupStrategy`, `SpringCacheBasedAclCache`, `AclPermissionEvaluator`, and `DefaultMethodSecurityExpressionHandler`. The configuration sample below targets Spring Security 6.x using standard beans; adapt datasource/schema/transactions and security rules for production.

Create `src/main/java/demo/acl/AclSecurityConfig.java`:

~~~java
package demo.acl;

import javax.sql.DataSource;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.LookupStrategy;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
@EnableMethodSecurity
public class AclSecurityConfig {
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    JdbcMutableAclService aclService(DataSource dataSource,
                                     LookupStrategy lookup,
                                     AclCache cache) {
        return new JdbcMutableAclService(dataSource, lookup, cache);
    }

    @Bean
    LookupStrategy lookupStrategy(DataSource dataSource,
                                  AclCache cache,
                                  AclAuthorizationStrategy authorizationStrategy,
                                  PermissionGrantingStrategy permissionStrategy) {
        return new BasicLookupStrategy(
                dataSource, cache, authorizationStrategy, permissionStrategy);
    }

    @Bean
    AclCache aclCache(PermissionGrantingStrategy permissionStrategy,
                      AclAuthorizationStrategy authorizationStrategy) {
        Cache cache = new ConcurrentMapCache("aclCache");
        return new SpringCacheBasedAclCache(
                cache, permissionStrategy, authorizationStrategy);
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger());
    }
}
~~~

**Deployment note:** This config only wires ACL beans into an **existing** Spring Boot Security and DataSource setup. It **does not** create the four ACL tables, define a `SecurityFilterChain`, assign real roles, or define entities/repositories/tenant checks; hence it is **not a complete standalone application**. Consult the official schema for your actual DB (H2/PostgreSQL/MySQL differ in DDL and identity semantics). For Spring Security 7.x, verify dependency and API changes for your runtime version.

Minimal Gradle dependencies block in a project **already using the Spring Boot plugin and dependency management**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.security:spring-security-acl'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Add your JDBC driver and environment-specific `DataSource` configuration. `spring-security-acl` is a separate module; never assume `spring-boot-starter-security` includes ACL persistence.

### 8.1. Protecting a Read Service with `hasPermission`

A Document service can use:

~~~java
// Snippet of a Spring-managed service, not a complete class.
@PreAuthorize("hasPermission(#p0, 'com.example.domain.Document', 'READ')")
public DocumentView read(long documentId) {
    return repository.readView(documentId);
}
~~~

`'com.example.domain.Document'` must match your `ObjectIdentity`/`acl_class` convention. `'READ'` must resolve consistently to `BasePermission.READ` via `PermissionFactory`/evaluator; for custom permissions, configure the appropriate converter. Never hard-code `'Document'` in one place and the fully qualified class name in another expecting Spring to guess.

A single `hasPermission` call does not validate every business rule: you still need active-account checks, tenant scope, data masking, transactions, and business validation at the appropriate layers. ACL inheritance is only **one dimension of authorization**.

### 8.2. Avoiding Cache Bugs When Parent Permissions Change

In practice, lookups can pull both the ACL and its parent from cache. When updating a parent ACE or `entriesInheriting`:
- Use `MutableAclService.updateAcl` and a cache invalidation strategy fitting your framework version.
- With multiple app instances using local caches, ensure consistent invalidation/TTL or a distributed cache; a DB update on instance A does not automatically evict caches in instance B.
- Be cautious about long-lived permission results cached at the application layer; if caching decisions separately, key them by principal, tenant, object, permission, and policy version.
- For sensitive permissions, define the consistency window: how quickly new grants and revocations take effect.
- Test parent revocation across multiple instances or document architectural limits explicitly.

Never assume "after `updateAcl`, every worker/process sees the revocation immediately" without a distributed invalidation mechanism.

## 9. Testing Spring ACL Directly: Parent, Local Deny, Stop, and NotFound

This is a unit test **using Spring ACL's real `AclImpl`/`DefaultPermissionGrantingStrategy`**, constructing objects in memory without JDBC. It differs from a full integration test with DB, cache, and filter chains. Place it in a project containing `spring-security-acl` and JUnit Jupiter (via `spring-boot-starter-test`).

Create `src/test/java/demo/acl/AclInheritanceTest.java`:

~~~java
package demo.acl;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.Sid;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AclInheritanceTest {
    private static final Sid ALICE = new PrincipalSid("alice");

    private static AclImpl acl(long id, Acl parent, boolean inherits) {
        // Test-only: allows in-memory mutation.
        // Production MUST NOT use this no-op authorization strategy.
        AclAuthorizationStrategy testOnly = (a, changeType) -> {};
        return new AclImpl(
                new ObjectIdentityImpl("demo.acl.Document", id),
                id,
                testOnly,
                new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger()),
                parent,
                null,                   // Do not restrict SID subset in test.
                inherits,
                new PrincipalSid("acl-admin"));
    }

    private static boolean permitted(Acl acl, Sid sid,
                                     org.springframework.security.acls.model.Permission p) {
        return acl.isGranted(List.of(p), List.of(sid), false);
    }

    @Test
    void inheritsParentWhenChildHasNoMatchingAce() {
        AclImpl parent = acl(100, null, false);
        parent.insertAce(0, BasePermission.READ, ALICE, true);
        parent.insertAce(1, BasePermission.WRITE, ALICE, true);

        AclImpl child = acl(200, parent, true);

        assertSame(parent, child.getParentAcl());
        assertTrue(child.isEntriesInheriting());
        assertTrue(permitted(child, ALICE, BasePermission.READ));
        assertTrue(permitted(child, ALICE, BasePermission.WRITE));
    }

    @Test
    void localDenyPreventsFallbackForThatPermissionAndSid() {
        AclImpl parent = acl(100, null, false);
        parent.insertAce(0, BasePermission.READ, ALICE, true);
        parent.insertAce(1, BasePermission.WRITE, ALICE, true);

        AclImpl child = acl(201, parent, true);
        child.insertAce(0, BasePermission.WRITE, ALICE, false);

        assertTrue(permitted(child, ALICE, BasePermission.READ));
        assertFalse(permitted(child, ALICE, BasePermission.WRITE));
    }

    @Test
    void canRetainParentLinkButTurnOffInheritance() {
        AclImpl parent = acl(100, null, false);
        parent.insertAce(0, BasePermission.READ, ALICE, true);

        AclImpl child = acl(202, parent, true);
        child.setEntriesInheriting(false);

        assertSame(parent, child.getParentAcl());
        assertFalse(child.isEntriesInheriting());
        assertThrows(NotFoundException.class,
                () -> permitted(child, ALICE, BasePermission.READ));

        child.insertAce(0, BasePermission.READ, ALICE, true);
        assertTrue(permitted(child, ALICE, BasePermission.READ));
    }

    @Test
    void inheritanceStopsAtIntermediateAcl() {
        AclImpl root = acl(100, null, false);
        root.insertAce(0, BasePermission.READ, ALICE, true);
        AclImpl folder = acl(110, root, false);
        AclImpl document = acl(120, folder, true);

        assertThrows(NotFoundException.class,
                () -> permitted(document, ALICE, BasePermission.READ));

        folder.insertAce(0, BasePermission.READ, ALICE, true);
        assertTrue(permitted(document, ALICE, BasePermission.READ));
    }
}
~~~

Theoretical note: `NotFoundException` occurs because **no matching ACE exists** along the permitted lookup path, not because a DENY ACE was encountered. This test verifies the inheritance flag and lookup logic in `AclImpl` in memory; it does not test JDBC persistence of `parent_object`, cache eviction, or `AclPermissionEvaluator` behind a Spring method-security proxy. Those require separate integration tests.

### 9.1. Integration Tests with DB/ACL Schema

In a real project, add transactional tests with `JdbcMutableAclService` and a test database:

1. Create Folder F's ACL and grant READ to Alice via `insertAce`; persist with `updateAcl`.
2. Create Document D's ACL, set parent F, enable inheritance, and save.
3. Reload D via `AclService.readAclById(...)` with Alice's SID list; `isGranted(READ)` must be true.
4. Disable D's inheritance, `updateAcl`, evict/reload per config; grant from F disappears.
5. Re-enable inheritance, add local DENY READ for Alice; verify false.
6. Modify parent and re-test both valid-tenant and wrong-tenant readers; test persistence/reload through cache.
7. Revoke the READ ACE on F and prove inheriting D sees the update per the consistency contract.
8. Verify cross-tenant/cyclic reparenting is rejected by the administration service.

Always test state after **reloading through the ACL service**, not only on the same Java object sitting in memory. Also run tests across multiple workers/instances when using distributed caching.

## 10. Standalone Java 17 Demo: Simulating an Inheritance Path with Boundary Cutoffs

This is a pure JDK program requiring no Spring dependencies. It simply simulates **one user SID and one permission at a time**, checking local ACEs first, then walking up to the parent if `inherit=true`. It does not simulate bitmasks/multiple SIDs, permission ordering, Spring's `NotFoundException`, or an ACL database. Its purpose is understanding **control flow**, not replacing Spring Security in production.

Save as `AclBoundaryDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AclBoundaryDemo {
    enum Permission { READ, WRITE }
    record Ace(String sid, Permission permission, boolean grant) {}

    static final class Node {
        final String name;
        final Node parent;
        final List<Ace> entries = new ArrayList<>();
        boolean inherits;

        Node(String name, Node parent, boolean inherits) {
            this.name = name;
            this.parent = parent;
            this.inherits = inherits;
        }

        void add(String sid, Permission permission, boolean grant) {
            entries.add(new Ace(sid, permission, grant));
        }

        boolean allows(String sid, Permission permission) {
            for (Ace ace : entries) {
                if (ace.sid().equals(sid)
                        && ace.permission() == permission) {
                    return ace.grant();
                }
            }
            if (inherits && parent != null) {
                return parent.allows(sid, permission);
            }
            // Demo fails closed; Spring ACL may throw NotFoundException.
            return false;
        }
    }

    public static void main(String[] args) {
        Node folder = new Node("folder", null, false);
        folder.add("alice", Permission.READ, true);
        folder.add("alice", Permission.WRITE, true);

        Node document = new Node("document", folder, true);
        System.out.println("inherited-read=" +
                document.allows("alice", Permission.READ));
        System.out.println("inherited-write=" +
                document.allows("alice", Permission.WRITE));

        document.add("alice", Permission.WRITE, false);
        System.out.println("local-deny-write=" +
                document.allows("alice", Permission.WRITE));

        document.inherits = false;
        System.out.println("stop-read=" +
                document.allows("alice", Permission.READ));

        document.add("alice", Permission.READ, true);
        System.out.println("local-read=" +
                document.allows("alice", Permission.READ));

        Node child = new Node("grandchild", document, true);
        System.out.println("grandchild-read=" +
                child.allows("alice", Permission.READ));
        System.out.println("grandchild-write=" +
                child.allows("alice", Permission.WRITE));

        folder.add("bob", Permission.READ, true);
        System.out.println("bob-after-parent-change=" +
                document.allows("bob", Permission.READ));
    }
}
~~~

Compile with JDK 17 or newer:

~~~bash
javac --release 17 AclBoundaryDemo.java
java AclBoundaryDemo
~~~

**Exact program stdout:**

~~~text
inherited-read=true
inherited-write=true
local-deny-write=false
stop-read=false
local-read=true
grandchild-read=true
grandchild-write=false
bob-after-parent-change=false
~~~

Analysis:
- When document inherits without local READ/WRITE, it receives both READ and WRITE from folder.
- Local WRITE DENY overrides Alice's WRITE on document in this single-SID/permission demo.
- Turning off inherit drops READ from folder even though the parent link still exists.
- Local READ GRANT restores dedicated read permission.
- Grandchild inherits document's local ACE, but does not cross document up to folder to pick up new grants.
- After folder grants READ to Bob, document still denies Bob because the inheritance boundary is cut.

**Demo boundary:** Do not treat `allows(...) == false` at the top of the tree as an exact replica of `Acl.isGranted`. Spring ACL can throw `NotFoundException` when no ACE exists; the demo intentionally turns it into a fail-closed boolean for standalone execution.

## 11. Reparenting: Changing the Parent Alters Effective Permissions

Imagine Document D currently inherits from Folder F-A, and a user submits a request to "move D into F-B."

If only `document.folderId=F-B.id` is updated **without** updating `ACL(D).parentAcl`, permissions can keep inheriting from F-A. That causes a security bug *because the domain shows F-B while the actual ACL is still governed by F-A*. Conversely, reparenting the ACL before updating the domain changes effective access before the UI/DB reflects the move.

### 11.1. Safe Move Rules

1. Authenticate and verify the actor has permission to move D and permission to place D into F-B.
2. Check the tenant/organization of D and F-B; reject cross-tenant parents if policy forbids them.
3. Verify the structure introduces no ACL/domain cycles.
4. Compute/verify effective permissions after the move, especially inherited WRITE/DELETE/ADMINISTRATION.
5. Within an appropriate transaction, update both domain parent and ACL parent/inheritance; handle rollback/compensation if the two stores use separate transactions.
6. Evict/invalidate ACL caches and related authorization decisions per your consistency contract.
7. Audit who moved it, when, old/new parent, inheritance flag, and reason.
8. Test that users with access on the old parent **no longer** retain unintended access after the move, and users on the new parent gain only intended access.
9. For off-DB file/object storage, check object storage policies separately; Spring ACL does not configure S3 bucket ACLs automatically.

### 11.2. Parent Links Must Never Be Used to Cross Tenants

Spring ACL focuses on ACE/SID decisions; it **does not natively understand tenant domains** just because `ObjectIdentity` has an ID and type. Allowing a parent from tenant A to link to a child in tenant B lets tenant A's ACEs leak into tenant B when inheritance is enabled. A row-level policy or repository tenant filter plus relationship validation rules must block that setup. Never rely on cross-tenant IDs being hard-to-guess UUIDs.

## 12. Difference Between Inherited Permissions and Role Hierarchy

**ACL inheritance:** permissions on a specific object can be looked up on a parent ACL when the child lacks a matching ACE. Controlled by `parentAcl` and `entriesInheriting`.

**Role hierarchy:** one authority can imply another (e.g., `ROLE_ADMIN > ROLE_EDITOR`) if the application configures `RoleHierarchy`. That is a relationship between **an actor's authorities**, not a parent–child relationship between `ObjectIdentity` instances.

~~~text
Role hierarchy:        ROLE_ADMIN -> ROLE_EDITOR
                                   (which authorities does the actor have?)

ACL inheritance:       Folder ACL -> Document ACL
                                   (where does the object inherit ACEs from?)
~~~

Both can influence a single decision, yet neither replaces the other. Never assume "Admin sees the folder so every document is open" when a child has a local DENY, inheritance disabled, or another tenant rule. Conversely, granting a higher role does not write `parent_object` or `entries_inheriting`.

## 13. Common Mistakes and How to Fix Them

### Mistake 1 — Having a parent means auto-inherit

False. `getParentAcl() != null` is not enough. `isEntriesInheriting()==true` must be set on the child at lookup time. Test cases where the parent link exists but inheritance is disabled.

### Mistake 2 — Disabling inheritance wipes out local permissions

False. `setEntriesInheriting(false)` only stops consulting parent ACEs. Local ACEs continue to GRANT/DENY normally. To revoke local permissions, update local ACEs explicitly.

### Mistake 3 — Parent only allows READ, so child can never get WRITE

No such rule exists. If the parent grants WRITE to a matching SID and the child enables inheritance without a matching local ACE, WRITE can propagate down too. Enforce permission boundaries via local ACLs or mandatory policies.

### Mistake 4 — A local DENY for one role blocks all equivalent rights

Not guaranteed with multiple SIDs/permissions. `DefaultPermissionGrantingStrategy` traverses permission and SID lists in order. Test principals holding both a `PrincipalSid` and multiple `GrantedAuthoritySid`s alongside opposing ACEs; never assume global deny-always-wins.

### Mistake 5 — Finding no ACE means returning true

False. When no decision is found, standard `Acl.isGranted` implementations can throw `NotFoundException`. Policies should fail closed; never catch the exception and GRANT for "compatibility."

### Mistake 6 — `getEntries()` returns the effective permission set

False. A child's `getEntries()` lists only local ACEs. To make an inheritance-aware decision, call `isGranted(...)` or `AclPermissionEvaluator`. When UI needs to display effective permissions, compute and explain each permission's source separately.

### Mistake 7 — Creating a parent ACL via SQL FK is enough

False if ACL records, tenant policies, inheritance flags, and cache updates are omitted. Use `MutableAclService` and transactions; test reloading via JDBC.

### Mistake 8 — Updating domain parent without updating ACL parent

Leaves moved documents continuing to inherit permissions from the old folder. Treat domain and ACL reparenting as one workflow with transactions/compensation and auditing.

### Mistake 9 — Cutting permissions at a folder guarantees grandchildren have no access

Only true for upstream ACEs that were cut off. If the folder/child has matching local ACEs, grandchildren can still inherit those. Test every node in the chain and every SID/permission.

### Mistake 10 — Deleting a parent without considering children

`MutableAclService.deleteAcl(objectIdentity, deleteChildren)` has a parameter deciding whether to delete descendant ACLs via API, and may reject deletion while children remain. Never blindly cascade-delete an entire ACL subtree when deleting a domain folder. Define explicit archive/reparent/migration policies.

### Mistake 11 — Misusing ACL admin privileges to edit permissions from the web

Having READ on a document does not mean being allowed to call `setParent` or `insertAce`. Mutations require dedicated ACL administrative authorization, method security, and auditing. Never use a static admin `Authentication` across requests to bypass permission checks.

### Mistake 12 — Assuming caches propagate revocations instantaneously

A parent ACL may sit cached across multiple nodes. When editing/revoking, design cache invalidation and verify reads after reload. For sensitive permission changes, document consistency SLAs and stale-cache handling.

### Mistake 13 — Confusing ACL inheritance with copying permissions in the database

Inheritance does not generate new local ACEs; changing parent grants changes decisions on inheriting children. If you create child ACEs as a "snapshot," that is a **different policy artifact** requiring lifecycle management.

### Mistake 14 — Leaving list queries unprotected

Putting `hasPermission(id, type, READ)` only on a GET-by-id endpoint does not filter `findAll()` records or protect exports/reports. Push tenant/ACL predicates into queries or batch checks to avoid N+1 lookups and list metadata leakage. In particular, `@PostFilter` over large datasets breaks pagination.

### Mistake 15 — Testing only one user and one mask for production

A single-SID table helps learn the mechanics, not validate production. Add tests for users with multiple roles, conflicting deny/grant entries, multi-element permission lists, missing SIDs, domain moves, and cached revocations. Run negative tests proving fail-closed behavior.

## 14. Pre-Release Implementation Checklist

| Group | Mandatory Test / Evidence |
| --- | --- |
| Topology | `ObjectIdentity` has accurate type and ID; parent ACL matches domain tree |
| Inheritance | Child with inherit=true receives parent GRANT when local ACE is missing |
| Cutoff | Child with inherit=false does not consult parent; local ACEs still work |
| Override | Local DENY, local GRANT, opposing parent, single and multiple SIDs |
| Missing | No ACE anywhere; `NotFoundException` handled fail-closed |
| Multi-level | Grandparent → folder → child; cutoff at intermediate node |
| Security boundary | Tenant/organization, classified documents, sensitive WRITE |
| Reparent | No cycles, no cross-tenant links, domain and ACL consistency |
| Mutation rights | Only authorized ACL admins/owners; audited requests |
| Persistence | Update→reload via `AclService` preserves parent/inherit/ACEs |
| Cache | Evict/invalidation after updates and revocations across instances |
| Method security | `AclPermissionEvaluator` registered and real proxies invoked |
| Data access | Scoped queries never skip ACLs on list/export/stream |
| Concurrency | Concurrent reparent + permission update, transactions/locking |
| Monitoring | Denials and infrastructure errors logged adequately without leaking PII |

### Exercise 1: Sensitive Document in a Shared Folder

Folder F grants `ROLE_EDITOR` READ and WRITE. Document D sits inside Folder F and must grant editors **READ but not WRITE**. What design options can you choose?

**Answer:** Do not just enable inheritance hoping WRITE disappears. You can disable inheritance on D and grant explicit READ as needed; or enable inheritance, configure a local WRITE DENY, and thoroughly test all SIDs; for sensitive data, it is better to enforce a mandatory business policy forbidding WRITE on D. Your choice must stay consistent with how permissions should behave when the parent changes.

### Exercise 2: Why Does No ACE Not Equal a DENY ACE?

D2 has no READ ACE, its parent has READ GRANT, and D2 has `entriesInheriting=false`. Does `isGranted(READ, Alice, false)` return false or throw an exception?

**Answer:** With `DefaultPermissionGrantingStrategy` and no matching ACE anywhere, the result can be `NotFoundException`; that is not a DENY ACE. The policy layer should express a safe denial per contract, never turning an absent decision into GRANT.

### Exercise 3: Cutting Off Mid-Tree

Root grants Alice READ, Folder S has `entriesInheriting=false` and no local READ, and Document D inherits (`true`) from S. Can Alice view D via Root?

**Answer:** Not via the default inheritance path. D falls back to S, but S does not fall back to Root. If S had a local READ GRANT, D could still inherit that.

### Exercise 4: Moving a Document from Tenant A to Tenant B

Domain data moved Document D to Folder B, yet `ACL(D).parentAcl` still points to Folder A with `entriesInheriting=true`. What is the risk?

**Answer:** Users in tenant A can continue benefiting from Folder A's grant when reading D, or tenant B cannot view D as expected. Synchronize domain parent and ACL parent, verify actor permissions, and forbid invalid cross-tenant links.

### Exercise 5: Parent ACL Loses READ

Parent F removes Alice's READ ACE. Child D has a local READ GRANT for Alice and still inherits from F. Is D blocked from READ?

**Answer:** Not necessarily. The local READ GRANT on D suffices to decide true for that SID/permission pair; editing the parent does not overwrite local ACEs. Audit all permission sources on children when a thorough revocation is required.

## 15. Summary

In Spring Security ACL, **inheritance is a conditional fallback**, not automatic permission copying:

- `getParentAcl()` defines the path to the parent; `isEntriesInheriting()` decides whether that path may be traversed when no matching ACE exists.
- When the child ACL has a matching decision, the child's result takes precedence; it does not keep climbing to the parent "looking for a better grant."
- With `DefaultPermissionGrantingStrategy`, when no matching ACE exists along the entire lookup path, `isGranted` can throw `NotFoundException`. Never confuse absence with grant.
- `entriesInheriting=false` cuts permission flow from the parent while preserving local ACEs and optionally preserving the parent link.
- To restrict *only certain permissions* from propagating, build local policies/ACEs or enforce separate boundaries; a single boolean flag is not a per-permission allow-list.
- When creating/moving/revoking within a subtree, verify tenants, admin rights, transactions, ACL caches, and affected descendants.

**Mental formula:** *A permission decision on a child = look for a matching local ACE first; if none is found and the child enables inheritance, look at the parent; if no decision exists, fail closed per policy.*

## Official References

- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): ACL model, data tables, `AclService`, `AclPermissionEvaluator`, and JDBC configuration.
- [Spring Security – Security Database Schema](https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html): `acl_object_identity.parent_object`, `entries_inheriting`, and `acl_entry`.
- [Acl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html): `getParentAcl`, `isEntriesInheriting`, `isGranted`.
- [MutableAcl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAcl.html): `setParent`, `setEntriesInheriting`, `insertAce`.
- [DefaultPermissionGrantingStrategy Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): Permission/SID traversal order, parent fallback, and `NotFoundException`.
- [AclImpl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/AclImpl.html): permission/parent implementation, constructors, and metadata.
- [MutableAclService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAclService.html): `createAcl`, `updateAcl`, `deleteAcl`.
