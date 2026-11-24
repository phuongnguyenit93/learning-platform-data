# Controlling ACL Inheritance, Caching, and Permission Updates

> **Scope:** Spring Security on the **Servlet stack**, Java 17+, per-resource permissions using the **Access Control List (ACL)** model. The focus is parent–child ACL relationships and the inheritance flag, Access Control Entry (ACE) ordering, the difference between caching ACL records and caching authorization decisions, updating permissions/inheritance flags, and properly scoped cache invalidation. Covers both **Spring Security ACL** APIs and a **runnable Spring Boot 3.3.5** application simulating the principles with an in-memory ACL, HTTP Basic, CSRF, and tests. Both parts are kept explicitly distinct: the real Spring Security ACL model vs. a custom-built learning lab demonstrating permission-update effects clearly.

## 1. Why Roles Are Insufficient

Under role-based authorization, a user with `ROLE_EDITOR` may be allowed to edit documents. Real-world requirements are usually finer-grained:

- Alice can read the Workspace folder and documents inside it.
- Bob cannot read the Workspace folder.
- A specific document inside Workspace can **explicitly deny Alice**.
- Auditor can read multiple documents via an audit authority group.
- Administrators can grant or revoke read access per user and per document.
- Permissions granted on a parent folder can **inherit down to child documents**, while inheritance can be stopped on a sensitive document.
- After permissions are updated, subsequent requests must never receive stale decisions from cache.

These requirements concern **individual resource objects**, not just global roles.

Example document tree:

```text
Workspace (id=101)
  ACE: alice READ allow
  ACE: bob   READ deny
  ACE: role AUDITOR READ allow
  entriesInheriting = false
        |
        +-- Quarterly plan (id=102)
        |     entriesInheriting = true
        |     local ACE: none
        |     => typically falls back to parent decision when local is inconclusive
        |
        +-- Private draft (id=103)
              entriesInheriting = true
              local ACE: alice READ deny
              => denies Alice at this node before consulting parent
```

Initial outcomes in **the lab with an explicit local-first rule**:

| User | Resource 101 | Resource 102 | Resource 103 |
| --- | --- | --- | --- |
| Alice | Allow | Allow via inheritance | Deny via local ACE |
| Bob | Deny | Deny via inheritance | Deny via inheritance |
| Auditor | Allow | Allow via inheritance | Allow via inheritance |
| Admin | Allow per example ACE | Allow via inheritance | Allow via inheritance |

**Distinction required:** this table describes the lab's specific policy; **it is not a claim that every ACL engine follows a "deny always beats allow" rule**. ACE traversal, SID precedence, permission masks, and parent fallback logic must be verified against the actual implementation. In the Spring Security ACL section below, we clarify how that works.

## 2. Components in Spring Security ACL

Spring Security has a dedicated ACL module, typically added via the `spring-security-acl` dependency. It **does not activate automatically just because an application includes `spring-boot-starter-security`**. A full ACL deployment requires storage, lookup, caching, SID/permission definitions, and authorization wiring.

| Term / API | Meaning |
| --- | --- |
| `ObjectIdentity` | Identifies a resource by **type** and **ID**, e.g., `("example.Document", 102L)` |
| `Sid` | Security identity, representing a **principal** or **granted authority** |
| `PrincipalSid` | SID for a single user, e.g., `alice` |
| `GrantedAuthoritySid` | SID for an authority/role, e.g., `ROLE_AUDITOR` |
| `Permission` / `BasePermission` | Requested permission, typically bit-masked like READ/WRITE/DELETE |
| `AccessControlEntry` (ACE) | One ACL entry: SID, Permission, grant/deny, position |
| `Acl` | ACL of an `ObjectIdentity`, containing ACEs, owner, parent, inheritance flag |
| `MutableAcl` | ACL supporting edits to ACEs, parent, and inheritance flag |
| `AclService` | Reads an object's ACL from storage |
| `MutableAclService` | Creates, updates, and deletes ACLs (implementation-dependent) |
| `LookupStrategy` / `BasicLookupStrategy` | Mechanism for querying ACLs, ACEs, and parent links from the database |
| `AclCache` | Cache for ACL objects to reduce database queries during authorization |
| `PermissionGrantingStrategy` | Defines how ACEs determine grant/deny |
| `AclPermissionEvaluator` | Bridge from `hasPermission(...)` expressions to ACL lookup/evaluation |
| `AclAuthorizationStrategy` | Checks permissions to perform ACL management operations, not automatically document read rights |

Typical Spring Security ACL packages:

```java
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.BasePermission;
```

These are **reference imports** for an app with the ACL dependency; the runnable project in Section 10 is a custom-built learning model and **does not pretend to be JdbcMutableAclService**.

### ObjectIdentity Is Not a Username

An ACL attaches to an object, such as document 102, not solely to Alice.

```java
ObjectIdentity documentId =
        new ObjectIdentityImpl("example.Document", 102L);

Sid alice = new PrincipalSid("alice");
Sid auditorRole = new GrantedAuthoritySid("ROLE_AUDITOR");
Permission read = BasePermission.READ;
```

This fragment depends on the ACL module. `"example.Document"` is merely a **class/type key** in the architectural snippet; if your database uses a different class/identifier name, preserve the real mapping. Never reuse the same numeric ID across multiple resource types while ignoring type.

### Sid Differs from Authority

`GrantedAuthority` is attached to `Authentication`; `Sid` is an ACL concept used to match ACEs. `PrincipalSid("alice")` represents a principal. `GrantedAuthoritySid("ROLE_AUDITOR")` represents an authority/role. A user holding multiple authorities can map to multiple SIDs during permission checks.

Never trust role or username values self-declared by the client in HTTP headers to construct permitting SIDs. SIDs used for authorization must originate from a verified `Authentication` and trusted mappings.

## 3. ACL Storage Schema and Inheritance Relationships

A traditional JDBC implementation of Spring Security ACL typically uses these tables:

```text
acl_class
  id
  class

acl_sid
  id
  principal
  sid

acl_object_identity
  id
  object_id_class        -> acl_class.id
  object_id_identity     -> resource ID
  parent_object          -> acl_object_identity.id (nullable)
  owner_sid              -> acl_sid.id
  entries_inheriting     -> boolean

acl_entry
  id
  acl_object_identity    -> acl_object_identity.id
  ace_order              -> ACE order
  sid                    -> acl_sid.id
  mask                   -> permission bit mask
  granting               -> grant or deny
  audit_success
  audit_failure
```

The column names above represent the standard ACL schema model; data types, DDL, indexing, and resource identities must match your database and module version. **Do not run this model verbatim as a CREATE TABLE script**. Before deploying to production, use the official schema for your chosen Spring Security ACL version and RDBMS, along with tested migrations.

### Parent Object, Owner, and Inheritance Flag

- `parent_object` links to **the parent resource's ACL**, not merely a business foreign key on a document.
- `entries_inheriting` specifies whether the ACL may consult the parent's decision when the local ACL is inconclusive.
- `owner_sid` identifies the ACL owner SID. **The ACL owner does not automatically hold all READ/WRITE permissions on the resource** unless policy defines it; do not confuse the ACL owner with `document.ownerId`.
- `ace_order` matters: two ACEs for the same permission/SID or across multiple SIDs can yield different outcomes depending on evaluation order.
- `granting` distinguishes allow ACEs from deny ACEs. It does **not** mean every system universally prioritizes deny above all else.

Parent ACL links must form an **acyclic graph**. If A inherits B and B inherits A, lookup logic can loop infinitely or throw an exception; parent-update workflows must prevent cycles and enforce reasonable depth limits.

## 4. Inheritance Rule: Check Local First, Then Parent

In Spring Security ACL, an ACL typically evaluates local ACEs matching the requested permissions/SIDs. If the local ACL **produces no conclusive match**, and `isEntriesInheriting()` is true, evaluation can continue to `getParentAcl()`.

```text
checkAccess(object=102, SIDs=[alice, ROLE_USER], permission=READ)
    |
    v
Load ACL 102
    |
    +-- Check local ACEs by permission/SID/order
    |      |
    |      +-- Conclusive grant/deny -> return result
    |      |
    |      +-- Inconclusive
    |             |
    |             +-- entriesInheriting=false -> do not inherit
    |             |
    |             +-- entriesInheriting=true
    |                    |
    |                    v
    |              Load / check parent ACL
    |                    |
    |                    +-- continue up to higher ancestors if needed
    |
    v
Grant / Deny / inconclusive, depending on API and policy
```

**An important detail to get right:** in `BasicPermissionGrantingStrategy`, iterating ACEs and matching permissions/SIDs follows a **specific order**. An earlier grant ACE can permit before a later deny ACE is reached if evaluated under that strategy's matching criteria. Therefore, do not summarize it as "a deny ACE always overrides every allow ACE". Test ACE ordering and SIDs whenever conflicting permissions exist on the same resource.

### Examples with the Inheritance Flag

| Local ACL | entriesInheriting | Parent ACL | Expected Outcome |
| --- | --- | --- | --- |
| No matching ACE | true | Parent grants Alice READ | Alice can be granted |
| No matching ACE | false | Parent grants Alice READ | No inheritance: typically no grant |
| Local denies Alice READ | true | Parent grants Alice READ | Local deny can decide before parent |
| Local grants Alice READ | true | Parent denies Alice READ | Local grant can decide before parent |
| Local ACE for WRITE, requesting READ | true | Parent grants READ | Depending on permission mask/strategy, if local is inconclusive for READ, parent is checked |

"Can" here is intentional: the final decision depends on permission masks, loaded SIDs, ACE order, and `PermissionGrantingStrategy`. For the Section 10 lab, we pick the rule **first local ACE matching sid + permission decides; otherwise inherit; deny by default** to illustrate clearly.

### Inheritance Is Not Role Hierarchy

- **ACL inheritance:** a child document receives decisions from a parent document/folder ACL.
- **Role hierarchy:** one role includes another role per role hierarchy configuration.
- **Java class inheritance:** type/method inheritance across Java classes; grants no resource permissions.

These concepts are independent. `ROLE_ADMIN` does not automatically inherit ACLs of all resources if SID/permission mappings do not grant them.

## 5. Permission Bit Masks and ACE Ordering

`BasePermission` in Spring Security ACL defines common permission bits:

| Permission | Commonly Used Mask |
| --- | --- |
| `BasePermission.READ` | 1 |
| `BasePermission.WRITE` | 2 |
| `BasePermission.CREATE` | 4 |
| `BasePermission.DELETE` | 8 |
| `BasePermission.ADMINISTRATION` | 16 |

Masks represent permission bits, **not role strings**. Additional permissions can be defined with custom bitmasks or an appropriate `PermissionFactory`. If an application has an `APPROVE` permission, standardize its mask/semantics and evaluation logic; never map \`ROLE_APPROVER\` directly to the READ mask.

In Spring Security ACL, `Acl.isGranted(permissions, sids, administrativeMode)` evaluates according to the strategy for the supplied permissions and SIDs. It can throw `NotFoundException` if no ACE matches and no inherited decision exists, or `UnloadedSidException` when the ACL was not loaded with all SIDs being evaluated.

Thus in an application policy layer, never treat exceptions as **grants**. For requests to private resources, the standard handling is **deny or return an error per policy** when no conclusive grant exists; safely log data/schema/cache failures.

### Why Does ACE Order Matter?

Suppose a document has:

```text
ACE 0: ROLE_STAFF  READ allow
ACE 1: alice       READ deny
```

Alice is both principal alice and a member of ROLE_STAFF. An evaluation strategy may conclude on the first matching ACE. Hence **never assume** a later deny ACE is always reached or outranks an earlier grant ACE. Policy design must keep ACE ordering and SID resolution consistent.

Write integration tests with users holding **multiple SIDs** to verify actual outcomes, especially if the permission-granting strategy or custom ACL service is customized.

## 6. Two Cache Layers: ACL Cache vs. Authorization Decision Cache

This distinction is very easy to confuse.

### 6.1. Spring Security ACL's AclCache

`AclCache` typically stores **loaded ACLs** (ACL objects with ACEs and parent references) to avoid querying ACL tables repeatedly. Some setups use `SpringCacheBasedAclCache` backed by Spring Cache; exact configuration depends on version and cache provider.

```text
ACL lookup
  - ObjectIdentity("example.Document", 102)
       |
       v
AclCache?
   |             |
  HIT           MISS
   |             |
   |             v
   |        LookupStrategy / JDBC read ACL
   |             |
   |             v
   |        Populate AclCache
   +-------------+
          |
          v
   Acl.isGranted(permission, sids, ...)
```

Caching an ACL **does not mean per-user decisions are cached**. It caches policy structure, while the evaluation result can still vary by request, Authentication/SIDs, and requested permissions.

### 6.2. Application-Specific Decision Cache

A system may also cache **results** like "Can Alice READ document 102?" to save CPU or remote policy calls. This is **not an automatic feature of `AclCache`**.

A decision cache key must cover the complete context affecting the decision:

```text
tenantId
object type + object ID
principal ID + authorities / SID set
permission
ACL revision / ancestor revision
policy version
any other contextual attributes used by the policy
```

If cached by `documentId` alone, Alice being allowed can cause Bob to **wrongly receive an allow from cache**. If cached by username + document without authorities or tenant scope, decisions can also become wrong when roles or tenant memberships change.

**Negative caches** (deny results) must also be invalidated after a new grant; otherwise newly authorized users keep getting 403. **Positive caches** must be invalidated after revocation; otherwise revoked users keep reading resources.

### 6.3. Inheritance Complicates Cache Invalidation

A change to a parent ACL can change decisions for **every inheriting descendant**. For example:

```text
Before update:
 parent 101: Bob READ deny
 child 102:  no local ACE, inherit=true
 cached decision (Bob, 102, READ) = deny

Admin updates ACL 101:
 parent 101: Bob READ allow

If only parent 101's cache is cleared:
 child 102 may retain cached deny or a stale cached parent snapshot

Correct:
  - invalidate ACL cache for both parent and affected children;
  - invalidate decision cache for affected descendants;
  - ensure new requests read the committed policy revision.
```

Common approaches:

1. **Subtree invalidation:** locate affected descendants and evict both their ACL caches and cached decisions.
2. **Versioning:** track revisions per ACL/ancestor or policy generation; cache entries with mismatched revisions are ignored.
3. **Global version/clear:** simple and easy to keep correct for learning or small systems; on update, clear the entire decision cache.
4. **TTL:** a secondary safeguard capping staleness windows, **not a replacement for invalidation** when immediate revocation is required.
5. **Distributed invalidation:** publish events/outbox messages or use a cluster-aware cache provider; ensure events reach all nodes and handle lag, duplicates, and retries.

**Correctness matters more than hit rate.** For sensitive systems, a stale allow after permission revocation can be a security vulnerability.

## 7. Modifying ACLs: Updating ACEs, Parents, and Inheritance Flags

A permission-change workflow should be tightly controlled:

1. **Authenticate the actor** making the change.
2. **Authorize the actor** to manage ACLs for the target resource and tenant; `authenticated()` alone is insufficient.
3. Read the current ACL/revision from a trusted data source.
4. Verify the resource exists, belongs to an allowed tenant, the parent is valid, and no cycle is created.
5. Add/remove/update ACEs by SID + permission + defined order; avoid unpredictable duplicate ACEs.
6. Update `entriesInheriting` or the parent ACL when business policy permits.
7. **Persist updates in a transaction** aligned with domain changes (if any).
8. Invalidate affected caches, including descendants and parent-dependent decisions.
9. Audit actor, resource, old/new policy, reason, and correlation ID without exposing secrets.
10. Immediately test a **new request** for the granted/revoked user, not just the HTTP status of the update API.

### Different Updates Have Different Blast Radii

| Change | Potentially Affected Scope |
| --- | --- |
| Add local grant on child 102 | Child 102; possibly descendants inheriting from 102 |
| Add local deny on child 102 | Child 102 and descendants deriving decisions from it |
| Change grant/deny on parent 101 | All inheriting descendants not decided by local ACEs |
| Set `entriesInheriting=false` on child | Child and subtree may lose ancestor permissions |
| Change child's parent ACL | Child and descendants may change permissions completely |
| Revoke a user's role/authority | Affects all ACLs referencing that role SID, even if ACL rows did not change |
| Delete resource / ACL | ACL, children/links, caches, and related domain references |
| Change `PermissionGrantingStrategy` | Can affect every decision; requires a new policy cache version |

**No single eviction strategy fits every architecture.** With Spring Security ACL JDBC, verify the behavior of `JdbcMutableAclService` and your cache implementation for your exact version; standard service updates invoke cache hooks, whereas custom DAOs, bulk SQL, and distributed caches can **bypass** them.

## 8. Spring Security ACL APIs: Creating and Updating Permissions

The following snippets show **real Spring Security ACL APIs**, but are **fragments requiring pre-configured** `MutableAclService`, database/schema, `LookupStrategy`, `AclCache`, and transactions. They are not the code of the runnable in-memory model in Section 10.

### 8.1. Loading an ACL by ObjectIdentity

```java
ObjectIdentity oid =
        new ObjectIdentityImpl("example.Document", 102L);

Acl acl = aclService.readAclById(oid);
boolean inheritanceEnabled = acl.isEntriesInheriting();
Acl parentAcl = acl.getParentAcl();
```

Match `ObjectIdentity` type/ID exactly with `acl_object_identity`. If the object has no ACL yet, `readAclById` may throw `NotFoundException`; never treat absence as public allow.

### 8.2. Adding an ACE Granting READ to Bob

```java
// Fragment inside a service that has MutableAclService mutableAclService,
// transaction, and authorization for an ACL-editing actor.
ObjectIdentity oid =
        new ObjectIdentityImpl("example.Document", 102L);

MutableAcl acl =
        (MutableAcl) mutableAclService.readAclById(oid);

Sid bob = new PrincipalSid("bob");

// Append ACE at the end per system policy.
// If a Bob/READ ACE already exists, update/remove properly to avoid duplicates.
acl.insertAce(acl.getEntries().size(), BasePermission.READ, bob, true);

mutableAclService.updateAcl(acl);
```

**Handle duplicates and ordering:** if the ACL already has an earlier deny for Bob/READ, appending a grant at the end may **not allow Bob** because the strategy evaluates ACEs in order. Locate and replace the matching ACE per policy rather than blindly inserting.

Calling `updateAcl` does not replace actor, tenant, domain-state validation, or transaction management. In production, guard the service with dedicated ACL management permissions and protect against lost updates.

### 8.3. Disabling Inheritance on a Child

```java
ObjectIdentity childId =
        new ObjectIdentityImpl("example.Document", 102L);

MutableAcl child =
        (MutableAcl) mutableAclService.readAclById(childId);

child.setEntriesInheriting(false);
mutableAclService.updateAcl(child);
```

When `entriesInheriting=false`, parent policies will not automatically fill gaps on the child via inheritance. If the child lacks a matching local grant, the user can be denied even though the parent allows it.

### 8.4. Switching Parent ACL

```java
ObjectIdentity childId =
        new ObjectIdentityImpl("example.Document", 102L);
ObjectIdentity newParentId =
        new ObjectIdentityImpl("example.Folder", 201L);

MutableAcl child =
        (MutableAcl) mutableAclService.readAclById(childId);
Acl newParent = mutableAclService.readAclById(newParentId);

// Must check tenant, admin permission, and cycles first.
child.setParent(newParent);
child.setEntriesInheriting(true);
mutableAclService.updateAcl(child);
```

A parent may have a different type if your data model and ACL schema allow it, but **never** allow arbitrary cross-tenant inheritance. Before calling `setParent`, verify the target parent exists, introduces no cycles, and complies with business policy. Updating a parent must invalidate decisions for affected children/subtrees.

### 8.5. AclCache and Invalidation Outside Standard Service Paths

An `AclCache` provides evict and clear operations depending on the implementation. Example fragment:

```java
// Use when the system knows for certain the ACL was modified outside standard service paths
// and perform full invalidation, not just one node.
ObjectIdentity oid =
        new ObjectIdentityImpl("example.Document", 102L);

aclCache.evictFromCache(oid);
```

**Do not treat a single evict call as sufficient** when a parent ACL changes or the app also has a decision cache and multiple nodes. Standard JDBC/cache implementations may evict descendants on normal updates; verify your specific datastore/cache behavior, especially with direct SQL, external administration services, or event-driven updates.

### 8.6. hasPermission(...) in Service/HTTP Authorization

Once `AclPermissionEvaluator` is configured via `MethodSecurityExpressionHandler`, a policy method can use:

```java
@PreAuthorize(
    "hasPermission(#documentId, 'example.Document', 'READ')")
public DocumentView load(long documentId) {
    return repository.load(documentId);
}
```

This is a **fragment**, not standalone runnable: it needs method security, the evaluator bean, an ACL service, a matching resource type string, and a real repository. When DB records require tenant checks, combine tenant/ownership policies rather than relying solely on an ACL mask.

Example configuration bean:

```java
@Bean
MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        AclService aclService) {
    DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(
            new AclPermissionEvaluator(aclService));
    return handler;
}
```

This snippet requires imports and wiring matching your Spring Security version. With `@EnableMethodSecurity`, verify the framework actually uses this handler; never assume adding the ACL dependency makes all `hasPermission` expressions run automatically.

## 9. Ensuring Concurrent Updates, Transactions, and Revocation

### 9.1. Lost Updates

Suppose two admins simultaneously read ACL revision 7:

```text
Admin A: wants to grant READ to Alice
Admin B: wants to deny READ to Bob

Both read revision 7.
A writes the updated ACL.
B writes the stale snapshot + Bob edit.
If B overwrites unchecked, A's grant can be lost.
```

Mitigation strategies:

- Optimistic locking with a revision in the domain/ACL update workflow.
- Pessimistic locking or suitable transaction isolation.
- Conditional SQL updates with version checks.
- Serializing ACL mutations per resource if needed.
- A data model enforcing uniqueness on (object, SID, permission) or explicit ACE ordering policies.

Never assume proper cache eviction solves database lost updates.

### 9.2. Cache Invalidation and Transaction Commit

Another issue is **when** other nodes see new permissions:

```text
T1: starts transaction to edit parent ACL
T1: modifies ACE
T1: publishes cache invalidation event too early
T2: receives event, clears cache
T2: immediately reads DB, still sees old ACE (T1 not committed yet)
T2: re-caches old ACL
T1: commits
=> stale cache can persist after commit!
```

A practical strategy is publishing events after commit, using a transactional outbox, or monotonic cache versions verified on read. On transaction rollback, never announce success and leave caches or downstream layers believing the policy changed.

In a single instance with simple locking, you can update state and clear the cache within the same critical section; that is the approach in the Section 10 lab, not proof of multi-node correctness.

### 9.3. Permissions Revoked While Authentication Still Holds Old Authorities

The ACL cache is only part of the picture. If a user loses `ROLE_AUDITOR` while their session or JWT still carries that authority:

- The ACL containing the `ROLE_AUDITOR` ACE may **not change**.
- The user still resolves the same SID from the stale authentication.
- Clearing `AclCache` **does not update** `Authentication.getAuthorities()` on already-issued sessions/tokens.

For immediate revocation of sensitive permissions, the system may need session invalidation, token introspection/revocation, short-lived tokens, authority reloading, or dynamic policies reading fresh data. This is independent of ACL eviction.

### 9.4. Authorizing Who Can Update ACLs

An ACE-updating endpoint is a privilege-escalation target. Never use:

```java
// Anti-pattern: lets any logged-in user grant READ to themselves.
@PreAuthorize("isAuthenticated()")
public void grantAcl(Long id, String username) {
    // ...
}
```

Require an ACL management policy such as `ROLE_ACL_ADMIN`, `ADMINISTRATION` permission, appropriate ownership, and tenant restrictions. Having `ADMINISTRATION` on an ACL does not automatically equal the global `ROLE_ADMIN`; the application must define who may alter ACEs, parents, and inheritance.

On updates, audit logs should record actor, target ObjectIdentity, SID, permission, allow/deny, before/after policy, revision, reason, timestamp, and correlation ID, **without logging secrets**.

## 10. Runnable Demo: ACL Inheritance + Cache + Permission Updates

To make the logic transparent and explicitly test invalidation, the following project implements **a learning ACL model in Java** with local-first rules, inheritance, and **a decision cache keyed by user/authorities/object/permission**. It **does not use Spring Security ACL's JDBC tables, `AclService`, or `SpringCacheBasedAclCache`**. Section 8 covered the real Spring ACL module APIs. The purpose of this demo is to demonstrate **inheritance, updates, stale decisions, and cache clearing** in a runnable Spring Security Servlet application.

The demo application features:

- HTTP Basic for account authentication; `SessionCreationPolicy.STATELESS`.
- GET to read documents per the modeled ACL; `AccessDeniedException` yields 403 when authenticated without READ.
- POST to update a READ ACE or toggle inheritance, allowed **only for `ROLE_ACL_ADMIN`**.
- Default CSRF enabled for POSTs; `GET /api/csrf` supplies a token for the client to send back with its cookie.
- Decision cache and all ACL data in memory, synchronized within one instance via `synchronized` methods. Every mutation increments `revision` and clears the global decision cache.
- A test proving that updating a parent ACE immediately changes the child's decision on the next request.

### 10.1. Project Structure

```text
acl-inheritance-demo/
├── pom.xml
├── src/main/java/example/acl/
│   ├── AclDemoApplication.java
│   ├── SecurityConfig.java
│   ├── AclPolicyService.java
│   └── AclController.java
└── src/test/java/example/acl/
    └── AclIntegrationTest.java
```

### 10.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>acl-inheritance-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. AclDemoApplication.java

```java
package example.acl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AclDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclDemoApplication.class, args);
    }
}
```

### 10.4. SecurityConfig.java

```java
package example.acl;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String hash = encoder.encode("demo123");
        return new InMemoryUserDetailsManager(
            User.withUsername("alice").password(hash)
                .authorities("ROLE_READER").build(),
            User.withUsername("bob").password(hash)
                .authorities("ROLE_READER").build(),
            User.withUsername("auditor").password(hash)
                .authorities("ROLE_AUDITOR").build(),
            User.withUsername("admin").password(hash)
                .authorities("ROLE_ACL_ADMIN").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/resources/{id}")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/acl/{id}/read")
                    .hasRole("ACL_ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/acl/{id}/inheritance")
                    .hasRole("ACL_ADMIN")
                .anyRequest().denyAll());

        http.httpBasic(Customizer.withDefaults());
        http.formLogin(form -> form.disable());
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.requestCache(cache ->
                cache.requestCache(new NullRequestCache()));

        // HTTP Basic may be sent automatically by browsers, so the demo keeps CSRF.
        http.csrf(csrf -> csrf.csrfTokenRepository(
                new CookieCsrfTokenRepository()));

        return http.build();
    }
}
```

**Reading the configuration:** `hasRole("ACL_ADMIN")` checks the `ROLE_ACL_ADMIN` authority using the default role prefix. GET resource requires only authenticated at the filter; exact READ permission is checked by the service. POST also requires valid CSRF; missing tokens are usually rejected with 403 **before** the service updates anything. `STATELESS` avoids using sessions to load SecurityContext, but **does not automatically disable CSRF**.

### 10.5. AclPolicyService.java

```java
package example.acl;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AclPolicyService {

    private enum Permission {
        READ
    }

    private record Ace(String sid, Permission permission, boolean grant) {
    }

    private record Node(long id, String title, Long parentId,
                        boolean entriesInheriting, List<Ace> aces) {
    }

    private record CacheKey(long id, String principal,
                            List<String> authorities, Permission permission) {
    }

    public record DocumentView(long id, String title, Long parentId,
                               boolean entriesInheriting, long aclRevision) {
    }

    public record UpdateResult(long id, String username,
                               boolean grant, long aclRevision) {
    }

    public record InheritanceResult(long id, boolean enabled,
                                    long aclRevision) {
    }

    private final Map<Long, Node> nodes = new HashMap<>();
    private final Map<CacheKey, Boolean> decisions = new HashMap<>();
    private long revision = 1L;

    public AclPolicyService() {
        // Parent ACL: Alice gets READ, Bob is denied,
        // auditor (via role) and admin get READ.
        nodes.put(101L, new Node(101L, "Workspace", null, false, List.of(
            new Ace("user:alice", Permission.READ, true),
            new Ace("user:bob", Permission.READ, false),
            new Ace("role:ROLE_AUDITOR", Permission.READ, true),
            new Ace("user:admin", Permission.READ, true)
        )));

        // Child 102 has no local ACEs, inherits permissions from parent.
        nodes.put(102L, new Node(102L, "Quarterly plan", 101L, true,
                List.of()));

        // Child 103 denies Alice immediately at the local ACL, while still letting
        // other SIDs continue inheriting if no matching ACE exists.
        nodes.put(103L, new Node(103L, "Private draft", 101L, true,
                List.of(new Ace("user:alice", Permission.READ, false))));
    }

    public synchronized DocumentView read(Authentication auth, long id) {
        Node node = find(id);

        if (auth == null || !auth.isAuthenticated()
                || !isGranted(auth, id, Permission.READ)) {
            throw new AccessDeniedException(
                    "READ permission denied for resource " + id);
        }

        return new DocumentView(node.id(), node.title(), node.parentId(),
                node.entriesInheriting(), revision);
    }

    private Node find(long id) {
        Node node = nodes.get(id);
        if (node == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Resource not found");
        }
        return node;
    }

    private boolean isGranted(Authentication auth, long id,
                              Permission permission) {
        // Cache key separates principal, authorities, and permission type.
        // Without authorities in the key, a changed role
        // could wrongly reuse an old result for the same username.
        List<String> authorities = auth.getAuthorities().stream()
                .map(a -> a.getAuthority())
                .sorted()
                .collect(Collectors.toUnmodifiableList());

        CacheKey key = new CacheKey(id, auth.getName(),
                authorities, permission);
        Boolean hit = decisions.get(key);
        if (hit != null) {
            return hit;
        }

        boolean granted = evaluate(find(id), auth, permission,
                new HashSet<>());
        decisions.put(key, granted);
        return granted;
    }

    private boolean evaluate(Node node, Authentication auth,
                             Permission permission, Set<Long> visited) {
        if (!visited.add(node.id())) {
            throw new IllegalStateException("ACL parent cycle detected");
        }

        // LAB MODEL: the first local ACE matching SID+permission
        // decides; real Spring ACL has its own strategy and mask/order rules.
        for (Ace ace : node.aces()) {
            if (ace.permission() == permission
                    && matches(ace.sid(), auth)) {
                return ace.grant();
            }
        }

        if (node.entriesInheriting() && node.parentId() != null) {
            return evaluate(find(node.parentId()), auth,
                    permission, visited);
        }

        // Fail closed if no local/parent ACE grants.
        return false;
    }

    private boolean matches(String sid, Authentication auth) {
        if (sid.startsWith("user:")) {
            return sid.substring("user:".length()).equals(auth.getName());
        }
        if (sid.startsWith("role:")) {
            String wanted = sid.substring("role:".length());
            return auth.getAuthorities().stream().anyMatch(
                    a -> wanted.equals(a.getAuthority()));
        }
        return false;
    }

    @PreAuthorize("hasRole('ACL_ADMIN')")
    public synchronized UpdateResult setReadRule(long id, String username,
                                                   boolean grant) {
        // Prevent clients from arbitrarily creating SIDs for non-demo users.
        if (!Set.of("alice", "bob", "auditor", "admin").contains(username)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Unknown demo username");
        }

        Node old = find(id);
        List<Ace> updated = new ArrayList<>(old.aces());
        String sid = "user:" + username;

        // Replace existing ACE for same SID+permission, avoiding duplicate/ambiguous ordering.
        updated.removeIf(a -> a.permission() == Permission.READ
                && a.sid().equals(sid));
        updated.add(0, new Ace(sid, Permission.READ, grant));

        nodes.put(id, new Node(old.id(), old.title(), old.parentId(),
                old.entriesInheriting(), List.copyOf(updated)));

        // Single-instance model: global revision + clear entire
        // decision cache, including decisions on descendants.
        revision++;
        decisions.clear();
        return new UpdateResult(id, username, grant, revision);
    }

    @PreAuthorize("hasRole('ACL_ADMIN')")
    public synchronized InheritanceResult setInheritance(
            long id, boolean enabled) {
        Node old = find(id);

        if (old.parentId() == null && enabled) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Root ACL has no parent to inherit");
        }

        nodes.put(id, new Node(old.id(), old.title(), old.parentId(),
                enabled, old.aces()));

        revision++;
        decisions.clear();
        return new InheritanceResult(id, enabled, revision);
    }
}
```

**Model accuracy notes:**

- Each `Node` holds its parent ID, `entriesInheriting`, and local ACE list.
- `evaluate` walks local ACEs in order looking for a matching user or role SID; if inconclusive and inheritance is enabled, it walks up to the parent.
- `HashSet` detects parent cycles. Production must **prevent cycles at parent-update time**, not merely detect them during reads.
- `CacheKey` includes object ID, username, authorities list, and permission, so Alice's result is never served to Bob. Multi-tenant production adds tenant, namespace, policy/ACL revisions, and any attributes participating in decisions.
- `decisions` is a **custom-written decision cache** in the lab, not Spring Security ACL's `AclCache`. It caches both grants and denies.
- All read/update methods are `synchronized`; on update, `revision++` and `decisions.clear()` happen inside the same critical section. Flushing the whole cache guarantees inheriting children never hold stale results.
- This is **one JVM only**; there is no persistence, cluster invalidation, tenant-aware ACL, or distributed transactions. Restarting resets state. Never use this code as production ACLs.
- `@PreAuthorize("hasRole('ACL_ADMIN')")` on the service runs through the proxy when the controller calls the service; URL rules also enforce a matching admin policy, providing defense in depth.

### 10.6. AclController.java

```java
package example.acl;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class AclController {

    private final AclPolicyService policy;

    public AclController(AclPolicyService policy) {
        this.policy = policy;
    }

    @GetMapping("/api/csrf")
    public String csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());
        if (token == null) {
            throw new IllegalStateException("CSRF token unavailable");
        }
        return token.getToken();
    }

    @GetMapping("/api/resources/{id}")
    public AclPolicyService.DocumentView read(
            @PathVariable long id, Authentication auth) {
        return policy.read(auth, id);
    }

    @PostMapping("/api/acl/{id}/read")
    public AclPolicyService.UpdateResult updateRead(
            @PathVariable long id, @RequestBody ReadRuleRequest body) {
        if (body == null || body.grant() == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "grant must be true or false");
        }
        return policy.setReadRule(id, body.username(), body.grant());
    }

    @PostMapping("/api/acl/{id}/inheritance")
    public AclPolicyService.InheritanceResult updateInheritance(
            @PathVariable long id, @RequestBody InheritanceRequest body) {
        if (body == null || body.enabled() == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "enabled must be true or false");
        }
        return policy.setInheritance(id, body.enabled());
    }

    public record ReadRuleRequest(String username, Boolean grant) {
    }

    public record InheritanceRequest(Boolean enabled) {
    }
}
```

Update HTTP routes are blocked by `hasRole("ACL_ADMIN")` at the filter and checked again at the service with `@PreAuthorize`. Using boxed `Boolean` instead of primitive `boolean` rejects JSON requests missing the field (rather than silently treating it as false).

### 10.7. AclIntegrationTest.java

```java
package example.acl;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AclIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void aliceCanReadInheritedChildButNotLocallyDeniedChild()
            throws Exception {
        mvc.perform(get("/api/resources/102")
                .with(httpBasic("alice", "demo123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(102));

        mvc.perform(get("/api/resources/103")
                .with(httpBasic("alice", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void auditorInheritsRoleBasedRead() throws Exception {
        mvc.perform(get("/api/resources/103")
                .with(httpBasic("auditor", "demo123")))
                .andExpect(status().isOk());
    }

    @Test
    void userCannotChangeAclEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/acl/101/read")
                .with(httpBasic("alice", "demo123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"bob\",\"grant\":true}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void mutationWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/acl/101/read")
                .with(httpBasic("admin", "demo123"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"bob\",\"grant\":true}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void parentChangeInvalidatesChildDecisionAndInheritanceToggle()
            throws Exception {
        // First call creates a cached DENY for Bob on child 102.
        mvc.perform(get("/api/resources/102")
                .with(httpBasic("bob", "demo123")))
                .andExpect(status().isForbidden());

        // Admin updates parent 101; global cache must be cleared.
        mvc.perform(post("/api/acl/101/read")
                .with(httpBasic("admin", "demo123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"bob\",\"grant\":true}"))
                .andExpect(status().isOk());

        // New request must not use stale DENY from child cache.
        mvc.perform(get("/api/resources/102")
                .with(httpBasic("bob", "demo123")))
                .andExpect(status().isOk());

        // When inheritance is disabled on child 102, local ACL is empty:
        // Bob is no longer allowed READ even though parent granted it.
        mvc.perform(post("/api/acl/102/inheritance")
                .with(httpBasic("admin", "demo123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":false}"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/resources/102")
                .with(httpBasic("bob", "demo123")))
                .andExpect(status().isForbidden());
    }
}
```

**Why `@DirtiesContext`?** The mutating test alters in-memory state. Placing the annotation after the test method tells Spring to refresh the context afterward, limiting interference with other tests. Real test suites can use dedicated fixtures/resets, database transaction rollbacks, or a fresh store per test.

`@PreAuthorize` runs through the Spring-managed service proxy because the controller injects `AclPolicyService`. Removing `@EnableMethodSecurity` or instantiating the service with `new` would disable service-level protection; the URL-denial test would still pass due to HTTP rules, so real systems should add direct service-level tests to prove defense in depth.

### 10.8. Running the Application

In the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Requires JDK 17+ and Maven. By default the server listens on `http://localhost:8080`. Use HTTP Basic and demo secrets **only on localhost**; production requires HTTPS to protect credentials, cookies, and CSRF tokens.

## 11. HTTP Practice and Observing the ACL Cache

### 11.1. Reading a Resource via Inheritance

```bash
curl -s -u alice:demo123 http://localhost:8080/api/resources/102
```

Expected JSON before any updates:

```json
{"id":102,"title":"Quarterly plan","parentId":101,"entriesInheriting":true,"aclRevision":1}
```

Alice is allowed on child 102 because parent 101 has an Alice READ allow ACE and child 102 inherits.

### 11.2. Local Deny Blocks Alice

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:demo123 http://localhost:8080/api/resources/103
```

Output:

```text
403
```

Child 103 has a local Alice READ deny ACE. Because the local check is conclusive, the lab does not fall back to Alice's parent grant to override it.

### 11.3. Auditor Inherits from a Role SID

```bash
curl -s -u auditor:demo123 http://localhost:8080/api/resources/103
```

JSON:

```json
{"id":103,"title":"Private draft","parentId":101,"entriesInheriting":true,"aclRevision":1}
```

Auditor inherits the grant from `role:ROLE_AUDITOR` on parent 101 because child 103 has no local ACE for auditor.

### 11.4. Bob Is Denied Before Update

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u bob:demo123 http://localhost:8080/api/resources/102
```

Output:

```text
403
```

The deny result is stored in the decision cache keyed for principal Bob. Updating the parent afterward must invalidate this cached entry.

### 11.5. Fetching a CSRF Token for the Admin POST

Because the API keeps CSRF enabled, JSON POST requests need **a server CSRF token and its accompanying cookie**:

```bash
csrf_token="$(curl -fsS -c acl-cookies.txt \
  http://localhost:8080/api/csrf)"
```

The returned token is read via `CsrfToken.getToken()`; in Spring Security 6, tokens can be masked to match the active handler. Never assume copying a raw cookie value into the header works across every version/config. Use the token from the lab endpoint alongside the cookie:

```bash
curl -i -u admin:demo123 -b acl-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -H "Content-Type: application/json" \
  -d '{"username":"bob","grant":true}' \
  http://localhost:8080/api/acl/101/read
```

Expected status 200 and JSON:

```json
{"id":101,"username":"bob","grant":true,"aclRevision":2}
```

Admin modifies Bob's READ ACE **on parent 101**, bumping revision from 1 to 2 and clearing the entire single-JVM decision cache.

### 11.6. Bob Accesses the Child Immediately After Update

```bash
curl -s -u bob:demo123 http://localhost:8080/api/resources/102
```

JSON:

```json
{"id":102,"title":"Quarterly plan","parentId":101,"entriesInheriting":true,"aclRevision":2}
```

This is a crucial test: **even though Bob has no local ACE on child 102**, the new parent grant takes effect. If a stale cached deny remained, Bob would keep getting 403 despite the update succeeding—a classic **cache invalidation bug after parent ACL updates**.

### 11.7. Disabling Inheritance on the Child

Reuse the same CSRF token/cookie **if the token is still valid** (or re-fetch from the token endpoint if needed):

```bash
curl -i -u admin:demo123 -b acl-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -H "Content-Type: application/json" \
  -d '{"enabled":false}' \
  http://localhost:8080/api/acl/102/inheritance
```

Expected:

```json
{"id":102,"enabled":false,"aclRevision":3}
```

Now child 102 has no local ACE for Bob and inheritance is disabled:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u bob:demo123 http://localhost:8080/api/resources/102
```

Expected:

```text
403
```

Even though parent 101 grants Bob READ, child 102 no longer inherits that permission. When inheritance is re-enabled, if the parent grant still exists, Bob will be permitted again on the next request. Each lab mutation increments the revision and clears the cache.

### 11.8. Missing CSRF / Wrong Actor

Try the admin POST **without sending a CSRF token**:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:demo123 \
  -H "Content-Type: application/json" \
  -d '{"username":"bob","grant":true}' \
  http://localhost:8080/api/acl/101/read
```

Usually returns:

```text
403
```

This is a CSRF failure, not proof that the actor lacks `ACL_ADMIN`. If you send a valid token as `alice:demo123` (who lacks `ROLE_ACL_ADMIN`), the response is also 403—**but due to authorization**, not CSRF. For unauthenticated requests, the outcome can be 401 with valid CSRF or 403 if blocked earlier by the CSRF filter; do not collapse these into a single rule.

## 12. Cache Effects to Verify After Every Mutation

Important regression test table:

| Before Change | Admin Action | New Request to Check |
| --- | --- | --- |
| Parent denies Bob; child inherits | Grant Bob on parent | Child must flip **deny → grant** |
| Parent grants Alice; child inherits | Deny Alice on parent | Child loses grant unless locally overridden |
| Parent grants Alice; child inherits | Local deny Alice on child | Child denies; parent does not override |
| Parent grants Bob; child inherits | `entriesInheriting=false` on child | Child loses parent permission |
| Child inherit=false, local empty | Enable `entriesInheriting=true` | Child receives parent grant again |
| Parent grants role AUDITOR | Revoke user's role | Stale sessions/tokens must also be handled |
| Child moves to another parent | Change parent identity | Child derives policy from new parent |
| Resource ACL deleted | Delete ACL | Object/decision caches hold no stale entries |
| Multiple independent instances | Update on node A | Node B must not serve stale ACL/decision caches |
| ACL update rolled back | DB does not commit | Caches/state must not reflect uncommitted policy |

**One 200 right after an update does not prove the whole system is right.** With distributed caches, test other nodes; with parent ACLs, test descendants; with role-based ACEs, test active sessions/tokens; with deny caches, test subsequent grants; with grant caches, test revocations.

## 13. Multi-Node ACL Cache: Clearing One JVM Is Not Enough

A distributed topology:

```text
Client
   |
   v
Load Balancer
   +--> App A: AclCache_A + DecisionCache_A
   |
   +--> App B: AclCache_B + DecisionCache_B
   |
   +--> App C: AclCache_C + DecisionCache_C
               |
               v
             ACL DB
```

If an admin edits a parent ACL through App A:

- App A updates the DB.
- App A clears its local cache.
- App B/C **may continue serving stale cached policies** without invalidation.
- Long TTLs can allow revoked permissions to remain usable for an unacceptable window.

Production options to consider:

1. **Distributed cache** supporting consistent invalidation or very short TTLs matching risk requirements.
2. **Versioned cache keys**: every post-commit policy generation/revision is checked before deciding.
3. **Outbox/events**: database commits the update alongside an outbox record, a worker broadcasts events to instances, and each node evicts the affected subtree/revision. Handle lost events, duplicate deliveries, and retries.
4. **DB read-through** when sensitive permissions require stronger consistency than eventual caches.
5. **Observability**: hit/miss metrics, invalidation lag, stale reads, update conflicts, and audits of actor/policy revision.

**Consistency and performance are never both free.** Update frequency, ACL tree depth, user/SID count, TTLs, and revocation SLAs determine the cache design.

## 14. Tenant Boundaries and Permission to Update Parents

In SaaS, a resource can belong to tenant A while its parent accidentally points to tenant B. Ignoring this boundary allows inheritance to pull permissions from another organization onto the current resource.

Rules to enforce:

- ObjectIdentity must combine **class/type + ID** cleanly and include tenant scope per model.
- Allow parent ACLs only from permitted business scopes.
- Anyone editing an ACL must hold ACL-management rights on the **target resource**, not merely read access.
- Never let clients arbitrarily supply SID/role names to grant broad access.
- When updating a parent, check for cycles, maximum depth, and descendants if tenant/scope changes.
- When a user is deleted or a role is revoked, clean up orphaned ACEs/SIDs and invalidate caches.
- Use trusted internal IDs for principals/tenants; usernames are simple for demos but can collide or be renamed.
- Consider separation of duties: approvers must not grant themselves approval rights when forbidden by policy.

Avoid rules like:

```text
request.header["X-Tenant"] == acl.tenant
    => grant
```

Because arbitrary client-set headers do not prove tenant membership. Obtain tenant scope from verified authentication and trusted datastores, then match against resource identity.

## 15. Common Failures and Diagnostics

| Symptom | Possible Cause | Action |
| --- | --- | --- |
| Parent updated, child still 403 | Child decision cache holds stale deny, or child `entriesInheriting=false` | Check flag and invalidate descendant decisions |
| READ revoked, user still accesses | Stale cached grant, session/JWT still holds old role SID | Check ACL cache + decision cache + authentication lifecycle |
| Allow added, result still deny | Earlier deny ACE wins, duplicate/order/mask | Inspect ACE order and actual PermissionGrantingStrategy |
| Parent grants, child denies | Child has a overriding local ACE | Debug local ACL, Sid/mask, and inheritance flag |
| Child granted despite inherit off | Local grant ACE or stale decision cache | Check entriesInheriting and invalidation |
| Auditor misses role-based ACE | Authority mapping mismatches GrantedAuthoritySid | Check ROLE_ prefix and loaded SIDs |
| One node works, another fails | Distributed cache not invalidated | Check cluster events/revisions |
| ACL update returns 200, old policy persists | Uncommitted transaction, premature invalidation, cache refill race | Check commit/outbox/versioning |
| Two admins overwrite each other | Concurrent writes without version check | Optimistic locking or transaction locking |
| ACL read fails with UnloadedSidException | ACL loaded without all required SIDs | Check AclService.readAclById/lookup and SIDs |
| Permission has no matching ACE | No grant decision exists | Fail closed instead of defaulting to allow |
| ACL not found | Resource lacks ACL, wrong type/id | Verify ObjectIdentity and creation/migration |
| Cross-tenant data exposed | Cross-tenant parent or wrong principal mapping | Tenant-aware policy + tests |
| Cache holds stale Acl after direct SQL | Bypassed MutableAclService cache hooks | Invalidate fully, not just DB update |
| ACL update POST returns 403 | Missing CSRF or actor lacks role | Separate CSRF validation from authorization |
| Java demo loses updates on restart | In-memory state is non-persistent | Use JDBC ACL or production datastore |
| ACE ordering gives unexpected results | Multiple SIDs/masks, strategy ordering | Explicitly test sid/permission/ACE order |

### Step-by-Step Debugging Order

1. Verify `ObjectIdentity` has the right type/ID/tenant.
2. Verify actual Authentication/SIDs and role mappings—never trust client headers.
3. Inspect `Acl.getEntries()`, masks, `granting`, and `ace_order`.
4. Check `isEntriesInheriting()` and `getParentAcl()`.
5. Verify the parent chain has no cycles and policies stay within tenant boundaries.
6. Check whether `AclCache` serves stale data; if a separate decision cache exists, inspect it too.
7. Confirm the ACL update committed and the new revision is visible across instances.
8. Issue a fresh request for affected principals/permissions and child descendants.
9. Distinguish 401/403/404; never treat a CSRF 403 as proof of ACL denial.
10. Write safe audit logs without Authorization headers, passwords, session tokens, or full documents.

In development you can enable controlled Spring Security logging:

```properties
logging.level.org.springframework.security=DEBUG
```

Never enable raw secret/token logging in production. When diagnosing policies, log resource ID, actor, permission, revision, and decision instead of dumping entire objects or cookies.

## 16. Self-Check Questions

1. **How does an ACL differ from role-based authorization?** ACL binds permissions/SIDs to individual specific objects, optionally with parent inheritance.
2. **What does ObjectIdentity contain?** Resource type and unique ID within an appropriate namespace.
3. **Are SIDs only usernames?** No; there are PrincipalSid and GrantedAuthoritySid.
4. **What does an ACE contain?** SID, Permission/mask, grant/deny, ordering, and schema-dependent audit metadata.
5. **Does entriesInheriting=true mean a child always allows if the parent allows?** No; local ACEs can decide first, and SIDs/masks/strategy affect evaluation.
6. **Does entriesInheriting=false disable local ACEs?** No; it stops fallback to the parent.
7. **Does deny always beat allow in Spring ACL?** Do not generalize; ACE order and granting strategy matter.
8. **What does AclCache store?** Loaded ACL objects, not per-principal Boolean caches by default.
9. **What should a decision cache key include?** At minimum object, permission, principal/SIDs/authorities, and policy revision/context.
10. **Why must parent edits consider descendants?** Inherited permissions on children can change even when their local ACEs do not.
11. **When granting a new permission, invalidate grant or deny caches?** Both relevant decision types: stale denies break access, while stale grants create leaks on revocation.
12. **Is a cache TTL enough to guarantee immediate revocation?** No; an appropriate invalidation/consistency strategy is needed.
13. **What if a user's role is revoked while their JWT still holds the old role?** Evicting AclCache does not update old tokens/sessions.
14. **Why do ACL updates need transactions and concurrency control?** To prevent lost updates and premature pre-commit cache invalidation.
15. **Can you update ACLs via POST without CSRF using browser Basic auth?** Not in the demo; a valid CSRF token must be sent.
16. **Who is allowed to update an ACL?** An actor with the proper manage-ACL permission/role and trusted tenant scope.
17. **Why does the demo use a global revision and clear all decisions?** Simplicity—eliminates stale child decisions in one JVM, though not optimal at scale.
18. **Is the runnable demo using Spring Security ACL JDBC?** No, it is a learning model; real Spring ACL module APIs were covered in Section 8.
19. **How do you prove a cache fix works?** Prime a cached deny on a child, edit the parent ACE, then re-request the child and verify it flips to allow.
20. **What happens if a parent is changed to another tenant?** It can cross security boundaries; policies must block it.

## 17. Production Implementation Checklist

- [ ] Clear and unique ObjectIdentity type/ID/tenant model.
- [ ] SIDs come from verified authentication/authority mappings.
- [ ] ACE ordering, masks, grant/deny, and PermissionGrantingStrategy are documented and tested.
- [ ] Parent ACLs form an acyclic structure within tenant boundaries.
- [ ] `entriesInheriting` behavior is tested both enabled and disabled.
- [ ] ACL cache and decision cache are **clearly separated** without conflated keys.
- [ ] Decision cache keys include principal/SIDs, permission, object, and revision/context.
- [ ] ACL mutations invalidate affected parents/descendants and both positive and negative decisions.
- [ ] Multi-node deployments use post-commit distributed invalidation, versioning, or outbox.
- [ ] ACL writes use transactions and lost-update protection.
- [ ] Only actors with ACL-management rights and matching tenant scope may edit ACEs, parents, or inheritance.
- [ ] Session/JWT/role cache revocation is verified independently of AclCache.
- [ ] CSRF is never disabled for cookie/Basic APIs where browsers may send credentials automatically.
- [ ] Enforce HTTPS and avoid logging credentials, tokens, or sensitive resource payloads.
- [ ] Test parent updates changing child permissions, local denies, inheritance off, role SIDs, invalidation, and multi-node if applicable.
- [ ] Use version-matched ACL schema/migrations with indexes on object/parent/SID.
- [ ] Monitor cache hit/miss, invalidation lag, DB lookups, and audit ACL mutations.
- [ ] Use the in-memory demo for learning only, never as a production replacement for Spring Security ACL JDBC.

**Conclusion:** Spring Security ACL models **per-resource** permissions via `ObjectIdentity`, `Sid`, `Permission`, and a list of `ACE`s. The `entriesInheriting` flag determines whether evaluation continues to the parent ACL when local entries are inconclusive; ACE ordering and permission masks must be understood accurately. Whenever a **parent** ACL, **child** ACL, or SID/role changes, related caches can go stale—especially **cached allows after revocation**. Perform ACL updates with proper authorization, transactions, descendant/decision invalidation, and cross-node consistency, and always verify permissions on **fresh requests** afterward.