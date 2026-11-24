# Changing the Owner, Updating the Parent ACL, and Updating Inheritance in Spring Security ACL

## 1. Lesson Objectives

When implementing Spring Security ACL, granting a new `AccessControlEntry` (ACE) solves only part of the problem. In document, folder, project, or organization applications, permissions also change when **changing the ACL owner**, **moving a resource to a different parent ACL**, and **enabling/disabling permission inheritance**. These three operations correspond to three `MutableAcl` APIs:

```java
mutableAcl.setOwner(new PrincipalSid("bob"));
mutableAcl.setParent(parentAcl);
mutableAcl.setEntriesInheriting(true);
mutableAclService.updateAcl(mutableAcl);
```

This snippet only illustrates syntax. In practice, you must load the existing ACL from `MutableAclService`, verify administrative rights, validate the new parent, run inside an appropriate transaction, persist, and read back to confirm the effect.

This lesson belongs to the **ACL Implementation** topic in Spring Security Authorization. After completing it, you will be able to:

1. Distinguish the **ACL owner** from the business data owner and from users holding READ/WRITE ACEs.
2. Understand the difference between `Acl.getParentAcl()` and `Acl.isEntriesInheriting()`.
3. Change owner, change parent, and toggle inheritance using `MutableAcl` and `MutableAclService.updateAcl(...)`.
4. Explain how child ACEs, parent ACEs, explicit denies, missing ACEs, and multi-level inheritance interact.
5. Structure an administrative service: authorization, transactions, cycle detection, cross-tenant checks, and cache invalidation.
6. Write Java 17+ tests with HSQLDB and Spring Security ACL JDBC proving state **before and after changes**.
7. Avoid dangerous mistakes: assuming changing the owner grants READ, assuming linking a parent turns on inheritance, or mutating the in-memory object while forgetting `updateAcl`.

**Scope:** Spring Security ACL 6.5.x, Spring Boot 3.x, Java 17+, operating on Spring-managed services and JDBC ACLs. Projects using other SQL schemas, caches, SID strategies, or Spring Security versions should cross-check configuration and tests.

## 2. Recap of the ACL Model and Relevant Columns

An `Acl` protects a specific `ObjectIdentity`, such as `demo.Document#42`. It holds ACEs binding a `Sid` with a `Permission` and a `granting` flag. An ACL may have an **owner**, a **parent ACL**, and an **inheritance flag**.

```text
ObjectIdentity: ("demo.Document", 42L)
          |
          v
ACL of Document 42
  owner                 = PrincipalSid("acl-admin")
  parentAcl             = ACL of Folder#10
  entriesInheriting     = true
  local ACEs:
      PrincipalSid("alice")  WRITE   GRANT
      PrincipalSid("bob")    READ    DENY
          |
          | if no matching decision on child
          v
ACL of Folder#10
  owner                 = PrincipalSid("folder-admin")
  parentAcl             = null
  local ACEs:
      GrantedAuthoritySid("ROLE_REVIEWER") READ GRANT
      PrincipalSid("carol")                READ GRANT
```

Four tables commonly used with JDBC ACL:

| Table | Key columns | Meaning in this lesson |
| --- | --- | --- |
| `acl_sid` | `id`, `principal`, `sid` | Stores the new owner and ACE SIDs |
| `acl_class` | `id`, `class` | Distinguishes domain object types |
| `acl_object_identity` | `id`, `object_id_class`, `object_id_identity`, **`owner_sid`**, **`parent_object`**, **`entries_inheriting`** | The three bold columns change when updating owner/parent/inheritance |
| `acl_entry` | `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting` | Local permission rules for each ACL |

`Document#42` may have business ID 42 while its `acl_object_identity` row has a different PK; `parent_object` points to the **ID of the parent ACL row**, not the folder's ID in the domain table. `owner_sid` points to `acl_sid.id`.

Even though these columns are stored individually, **changes must go through authorized APIs and workflows**; an endpoint should never run raw `UPDATE acl_object_identity ...` bypassing Spring Security strategies and caches.

## 3. Operation 1 — `setOwner(Sid)`: Changing the ACL Owner

### 3.1. What Is the ACL Owner?

`Acl.getOwner()` returns a `Sid`, usually the `PrincipalSid` of the ACL administrator. The owner can be used by `AclAuthorizationStrategyImpl` to determine who may edit ACL permissions.

**Do not confuse this with permissions on business data:**

- `Acl.getOwner() == PrincipalSid("alice")` refers to the **ACL owner** in the ACL model.
- `Document.ownerId == "alice"` is a **business** field, not automatically synchronized by Spring ACL with `acl_sid`.
- Having `Acl.getOwner()` as Alice **does not mean** Alice automatically has `BasePermission.READ` or `WRITE`; domain permissions come from ACEs and `PermissionGrantingStrategy`.
- An existing `PrincipalSid("alice")/READ/GRANT` ACE remains intact when ownership moves to Bob, unless the admin service deliberately removes that ACE.

Under default `AclAuthorizationStrategyImpl`, the ACL owner, a principal with a configured ACL admin authority, or a caller with `BasePermission.ADMINISTRATION` may qualify to modify the ACL. **Do not** treat that as a complete business governance policy; enforce endpoint/service caller authorization per organizational rules.

### 3.2. How to Change the Owner Properly

```java
ObjectIdentity identity =
    new ObjectIdentityImpl("demo.Document", 42L);

MutableAcl acl = (MutableAcl) mutableAclService.readAclById(identity);
Sid oldOwner = acl.getOwner();

acl.setOwner(new PrincipalSid("bob"));
MutableAcl saved = mutableAclService.updateAcl(acl);

System.out.println(saved.getOwner());
```

This is an **integration snippet**, assuming `mutableAclService` is injected, ACL tables exist, and the caller is authorized to change ownership; stdout is not fixed because `Sid.toString()` depends on the implementation. `MutableAcl.setOwner` requires a **non-null** new `Sid`. Only `updateAcl` saves the change to the database and returns the reloaded ACL.

**Safe sequence for an ownership-transfer API:**

1. Authenticate the actor and verify the actor may **transfer ACL administration ownership** for this object.
2. Verify the object belongs to the right tenant and the target owner exists and is eligible to hold ownership.
3. Load the full ACL, record `oldOwner`, and call `setOwner(new PrincipalSid(...))`.
4. Call `updateAcl` inside an appropriate transaction.
5. Read back, audit actor/oldOwner/newOwner/objectId, and validate post-transfer policies.
6. If business rules require the new owner to have READ/WRITE, **update ACEs explicitly**; if the previous owner must lose domain permissions, **revoke their ACEs explicitly**. Never merge both requirements into assumptions.

**Special note:** `AclAuthorizationStrategy` defines change types `CHANGE_OWNERSHIP`, `CHANGE_GENERAL`, and `CHANGE_AUDITING`. `AclAuthorizationStrategyImpl` can take one authority shared across all three or three separate authorities in ownership/auditing/general order. Changing ownership is more sensitive than routine permission edits, so consider separating its privileges.

## 4. Operation 2 — `setParent(Acl)`: Changing the Parent ACL

`Acl.getParentAcl()` is a **navigation relationship** from a child ACL to a parent ACL. It is not inferred automatically from `Document.folderId`: the application must set and update the parent ACL whenever business hierarchy changes.

```java
ObjectIdentity childId =
    new ObjectIdentityImpl("demo.Document", 42L);
ObjectIdentity folderId =
    new ObjectIdentityImpl("demo.Folder", 10L);

MutableAcl child =
    (MutableAcl) mutableAclService.readAclById(childId);
Acl folderAcl = mutableAclService.readAclById(folderId);

child.setParent(folderAcl);
mutableAclService.updateAcl(child);
```

This is an integration snippet. The parameter to `setParent` is an **`Acl`**, not an `ObjectIdentity`, `Long`, or SID. You must load the parent ACL from the service before attaching it. To remove a parent link, call `child.setParent(null)` followed by `updateAcl(child)`, handling any business consequences.

### 4.1. Moving a Child from Parent A to Parent B

```text
BEFORE:
  Document #42 -> Folder A ACL
                    Alice READ GRANT

AFTER:
  Document #42 -> Folder B ACL
                    Bob READ GRANT
```

If the child ACL has inheritance enabled and no matching local ACE of its own, switching parents can cause Alice to **lose** inherited access from A while Bob **gains** inherited access from B.

If the child ACL has inheritance disabled, the new parent link is still persisted in `parent_object`, yet does not automatically grant permissions from parent B. That is why **two states** must be checked: the parent link and the inheritance flag.

### 4.2. Preventing Cycles and Cross-Tenant Links

Parent ACL links should form an **acyclic graph**. Never do `child.setParent(child)` or create A → B → C → A. A self-referencing SQL foreign key alone cannot prevent multi-hop cycles; if a cycle exists, permission queries risk infinite recursion or ACL-loading errors.

Before moving:

- Verify the new parent exists and belongs to the **same tenant/administrative boundary** as the child.
- Starting from the new parent, walk `getParentAcl()` or query trusted hierarchy tables; if the child is encountered, reject the move.
- Enforce depth bounds, track `visited ObjectIdentity` entries, and guard concurrent tree moves against race-induced cycles.
- Define clear rules when a domain object moves folders, moves organizations, or deletes a folder: the parent ACL must update at the right time within the transaction.
- Changing a parent often alters permissions for **multiple descendant layers** if they inherit; assess the blast radius beyond the immediate child.

**Never copy ACEs from the old parent onto the child** as a default part of "changing parent." Copying ACEs is a different policy (materializing permissions), which may preserve old grants the organization intended to revoke.

## 5. Operation 3 — `setEntriesInheriting(boolean)`: Enabling or Disabling Inheritance

`Acl.isEntriesInheriting()` is the flag governing whether the child ACL consults the parent's ACEs during permission evaluation. `setParent` merely establishes the link; **only when inheritance is enabled can parent ACEs affect outcomes** per the granting strategy.

```java
MutableAcl child =
    (MutableAcl) mutableAclService.readAclById(childIdentity);

// Keep parent but temporarily detach inherited permissions.
child.setEntriesInheriting(false);
mutableAclService.updateAcl(child);

// After auditing parent permissions, inheritance can be re-enabled:
child = (MutableAcl) mutableAclService.readAclById(childIdentity);
child.setEntriesInheriting(true);
mutableAclService.updateAcl(child);
```

This snippet assumes `childIdentity` and `mutableAclService` exist; outside tests, changes must go through an authorized admin service. Never automatically turn inheritance back on just because a parent link exists: the parent ACL may have changed and affect many users.

### 5.1. Parent/Inheritance Matrix

| Parent ACL exists? | `entriesInheriting` | Local ACE matches? | Typical outcome under default strategy |
| --- | --- | --- | --- |
| No | `false` | Yes | Decided by child ACEs |
| No | `true` | No | No parent to inherit from; usually no-match |
| Yes | `false` | No | Parent ACEs ignored |
| Yes | `true` | No | Consults parent, continuing up ancestors that also enable inheritance |
| Yes | `true` | Matching grant | Local grant can decide without falling back |
| Yes | `true` | Explicit local deny | Local deny can decide before parent grant ACEs |
| Yes | `false` | Local ACEs exist | Local ACEs remain active; disabling inheritance **does not delete** local ACEs |

Matching and ACE/SID/permission ordering are governed by `PermissionGrantingStrategy`. With custom strategies or different SID/permission lists, never assume dogmatically that "deny always wins" or "grant always wins" in every scenario.

### 5.2. Grant, Explicit Deny, and No Matching Rule

Suppose Folder A's ACL grants Alice READ. For a child ACL with inheritance enabled:

- **Child has no READ ACE for Alice:** falls back to parent, and Alice is granted READ.
- **Child has a READ/deny ACE for Alice:** default strategy can return `false`; parent grant does not override the child's decision.
- **Child disables inheritance and has no READ ACE:** there is no fallback path to parent; `Acl.isGranted` may throw `NotFoundException`, which **differs** from an explicit deny ACE.
- **Child has a local READ/grant ACE for Alice:** Alice can still read even when inheritance is disabled.

In application policies, a `NotFoundException` due to no matching rule must be handled as **fail closed**. Never convert a missing-decision exception into allow.

### 5.3. Multiple Levels

```text
Organization (READ for ROLE_EMPLOYEE)
  |
  | Folder-A: entriesInheriting=true
  v
Folder-A (READ for Alice)
  |
  | Document: entriesInheriting=true
  v
Document
```

If Folder-A disables inheritance, organization permissions stop propagating through Folder-A under standard inheritance logic, yet **Folder-A's local ACEs can still be inherited by Document** if Document enables inheritance. If Document disables inheritance, it uses no ACEs from any parent. That is why the flag lives **on each child ACL**, rather than being a single global tree switch.

## 6. Administrative Service Pattern: Updating All Three States and Persisting

Administrative operations should be centralized in a Spring service rather than written directly in controllers:

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AclAdministrationService {

    private final MutableAclService aclService;

    public AclAdministrationService(MutableAclService aclService) {
        this.aclService = aclService;
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_MANAGE')")
    public void changeOwner(long documentId, String newUsername) {
        ObjectIdentity id =
            new ObjectIdentityImpl("demo.Document", documentId);

        MutableAcl acl = (MutableAcl) aclService.readAclById(id);

        // Before production use: verify tenant, actor,
        // document existence/state, and validity of newUsername.
        acl.setOwner(new PrincipalSid(newUsername));
        aclService.updateAcl(acl);
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_MANAGE')")
    public void switchParent(long documentId, long folderId) {
        ObjectIdentity childId =
            new ObjectIdentityImpl("demo.Document", documentId);
        ObjectIdentity parentId =
            new ObjectIdentityImpl("demo.Folder", folderId);

        MutableAcl child = (MutableAcl) aclService.readAclById(childId);
        Acl parent = aclService.readAclById(parentId);

        // Production: enforce same tenant, no parent
        // cycles, and permissions on both resources.
        child.setParent(parent);
        aclService.updateAcl(child);
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_MANAGE')")
    public void changeInheritance(long documentId, boolean inherit) {
        ObjectIdentity id =
            new ObjectIdentityImpl("demo.Document", documentId);

        MutableAcl acl = (MutableAcl) aclService.readAclById(id);
        acl.setEntriesInheriting(inherit);
        aclService.updateAcl(acl);
    }
}
```

**This Spring service code compiles once the project provides the corresponding dependencies/imports**, yet the domain/tenant/cycle checks noted in comments are **mandatory before production**. The `ACL_MANAGE` authority only guards the entry point; `AclAuthorizationStrategy` inside the ACL can still require specific permissions for the actor. When using `AclAuthorizationStrategyImpl` with `ROLE_ACL_ADMIN`, ensure both policies align cleanly.

Never call `this.changeOwner()` from another method assuming `@PreAuthorize`/`@Transactional` advice will always run: in Spring proxy mode, self-invocation bypasses interceptors on the internal call. Administrative services should be invoked through Spring-managed beans/proxies.

### 6.1. Use `updateAcl` Instead of `createAcl`

`createAcl(ObjectIdentity)` is for **nonexistent** ACLs, whereas changing owner/parent/inheritance operates on **persisted ACLs**. The right sequence:

```text
readAclById(identity)
     |
     v
MutableAcl.setOwner / setParent / setEntriesInheriting
     |
     v
MutableAclService.updateAcl(acl)
     |
     v
read back and verify actual state + permissions
```

`MutableAclService.updateAcl` does not merely mutate an in-memory object; it writes to persistence. With `JdbcMutableAclService`, the implementation may **delete and recreate ACE rows** when updating an ACL, even if you only changed owner/parent/inheritance; therefore never assume ACE row IDs stay constant or that repeated updates are free. Use transactions to guarantee consistency.

### 6.2. Do Not Confuse the Parent Object

`setParent` expects an `Acl`, not an `ObjectIdentity`. If you only have a folder ID, do:

```java
ObjectIdentity parentIdentity =
    new ObjectIdentityImpl("demo.Folder", folderId);
Acl parentAcl = aclService.readAclById(parentIdentity);
childAcl.setParent(parentAcl);
```

This snippet assumes variables exist and is not a standalone program. If the parent has no ACL yet, apply your policy to provision or reject it; never synthesize an empty parent ACL while neglecting inherited permissions.

## 7. ACL Modification Rights, Transactions, and Caching

### 7.1. Permission to Change Owner Differs from Permission to Read the Object

`AclAuthorizationStrategyImpl` can be configured with one shared authority or three authorities per change type:

```java
@Bean
AclAuthorizationStrategy aclAuthorizationStrategy() {
    return new AclAuthorizationStrategyImpl(
        new SimpleGrantedAuthority("ROLE_ACL_OWNER_ADMIN"),
        new SimpleGrantedAuthority("ROLE_ACL_AUDIT_ADMIN"),
        new SimpleGrantedAuthority("ROLE_ACL_RULE_ADMIN")
    );
}
```

This is a **bean fragment**, not a standalone configuration class. Order in the three-argument constructor: permission to change **ownership**, permission to edit **auditing**, and permission to modify **other ACE/ACL data**. With a single authority, the implementation uses that authority for all three groups. Always pair this with checks that the actor is authorized to edit the ACL of **that specific resource**, not merely holding a system role.

### 7.2. Transactions and Concurrency

Changing owner, moving parent, and toggling inheritance typically involve one or more `acl_object_identity` rows and may insert new `acl_sid` rows. `@Transactional` should span the relevant business unit of work. If another transaction updates domain tables (e.g., moving a document to another folder), keep `Document.folder_id` and `acl_object_identity.parent_object` consistent.

Race conditions to watch for:

- Two administrators move the same child to two different parents simultaneously; the last update may overwrite the first.
- Admin A checks that a parent causes no cycle; Admin B edits the tree before A commits, forming a cycle.
- One thread deletes a parent ACL while another attaches a child to that parent.
- An admin revokes access while an in-flight request reads an ACL from stale cache or an older transaction.

Consider **optimistic locking/versioning**, locking relevant domain rows/ACL relations, proper transaction isolation, and conditional retry policies. The default ACL schema does not automatically supply every concurrency-control mechanism an application needs.

### 7.3. Caching When Changing Parent/Owner/Inheritance

`AclCache` (e.g., `SpringCacheBasedAclCache`) cuts down SQL queries, yet new permission decisions are only trustworthy when cached data stays synchronized. `JdbcMutableAclService.updateAcl` in the standard implementation handles invalidation and reloads; verify the impact on descendant ACLs when changing a parent, editing an ancestor ACE, or toggling inheritance.

**Never treat a single-JVM local cache as safe across multiple nodes.** With `ConcurrentMapCache`, node A updates owner/parent while node B can keep serving the stale ACL. Design distributed invalidation/TTLs or consistent reads aligned with your product's risk level.

When changing a subtree's parent, consider caches for children, grandchildren, and previous relationships. Updating the DB correctly alone does not prove authorization on every node sees the change.

## 8. Java 17+ Project Testing Owner, Parent, and Inheritance with JDBC

This example uses an in-memory HSQLDB database and real classes from `spring-security-acl`. It creates three ACLs:

- `Folder-A`: grants `READ` to `PrincipalSid("alice")`.
- `Folder-B`: grants `READ` to `PrincipalSid("bob")`.
- `Document`: no local ACEs, initial parent Folder-A, `entriesInheriting=true`.

Each test then modifies **owner**, **parent**, **inheritance**, adds local ACEs, or updates a parent ACE and verifies state read back from the JDBC service. This proves the three operations persist rather than merely changing in-memory properties.

### 8.1. Project Structure and Dependencies

```text
acl-hierarchy-demo/
├── settings.gradle
├── build.gradle
└── src/test/
    ├── java/demo/AclHierarchyTest.java
    └── resources/schema.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'acl-hierarchy-demo'
```

`build.gradle` — Java 17 and Spring Security 6.5.x via the Boot BOM:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-acl'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.hsqldb:hsqldb'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

The test suite uses HSQLDB because JDBC ACL's default ID query `call identity()` targets HSQLDB. For production PostgreSQL, use the PostgreSQL schema and configure `JdbcMutableAclService.setClassIdentityQuery`/`setSidIdentityQuery` appropriately. Never copy HSQLDB DDL verbatim onto PostgreSQL.

### 8.2. The `schema.sql` File

Create `src/test/resources/schema.sql` using the HSQLDB schema from the official documentation:

```sql
CREATE TABLE acl_sid (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT acl_sid_unique UNIQUE(sid, principal)
);

CREATE TABLE acl_class (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    class VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT acl_class_unique UNIQUE(class)
);

CREATE TABLE acl_object_identity (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    object_id_class BIGINT NOT NULL,
    object_id_identity VARCHAR_IGNORECASE(36) NOT NULL,
    parent_object BIGINT,
    owner_sid BIGINT,
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT acl_object_unique
        UNIQUE(object_id_class, object_id_identity),
    CONSTRAINT acl_parent_fk
        FOREIGN KEY(parent_object) REFERENCES acl_object_identity(id),
    CONSTRAINT acl_class_fk
        FOREIGN KEY(object_id_class) REFERENCES acl_class(id),
    CONSTRAINT acl_owner_fk
        FOREIGN KEY(owner_sid) REFERENCES acl_sid(id)
);

CREATE TABLE acl_entry (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL,
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL,
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT acl_entry_unique
        UNIQUE(acl_object_identity, ace_order),
    CONSTRAINT acl_entry_object_fk
        FOREIGN KEY(acl_object_identity) REFERENCES acl_object_identity(id),
    CONSTRAINT acl_entry_sid_fk
        FOREIGN KEY(sid) REFERENCES acl_sid(id)
);
```

This is the **HSQLDB schema** with the four standard ACL tables and corresponding foreign-key/unique constraints. In the demo, Spring Boot tests initialize it via `spring.sql.init.mode=always`. Production uses controlled migrations rather than dropping/recreating schemas on deploy.

### 8.3. Java Integration Test

Create `src/test/java/demo/AclHierarchyTest.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.LookupStrategy;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = AclHierarchyTest.Config.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:schema.sql"
    }
)
@WithMockUser(username = "acl-admin", roles = "ACL_ADMIN")
public class AclHierarchyTest {

    private static final AtomicLong IDS = new AtomicLong(20000L);

    @Autowired JdbcMutableAclService service;
    @Autowired DataSource dataSource;
    @Autowired AclCache cache;
    @Autowired DocumentService documents;

    private ObjectIdentity folderA;
    private ObjectIdentity folderB;
    private ObjectIdentity document;
    private Long docId;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    public static class Config {
        @Bean
        static MethodSecurityExpressionHandler expressionHandler(
                AclPermissionEvaluator evaluator) {
            DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
            handler.setPermissionEvaluator(evaluator);
            return handler;
        }

        @Bean
        static AclPermissionEvaluator evaluator(
                JdbcMutableAclService service) {
            return new AclPermissionEvaluator(service);
        }

        @Bean
        JdbcMutableAclService aclService(
                DataSource source, LookupStrategy lookup,
                AclCache cache) {
            return new JdbcMutableAclService(source, lookup, cache);
        }

        @Bean
        LookupStrategy lookupStrategy(
                DataSource source, AclCache cache,
                AclAuthorizationStrategy adminStrategy,
                PermissionGrantingStrategy grantStrategy) {
            return new BasicLookupStrategy(
                source, cache, adminStrategy, grantStrategy);
        }

        @Bean
        AclCache aclCache(
                PermissionGrantingStrategy grantStrategy,
                AclAuthorizationStrategy adminStrategy) {
            Cache springCache = new ConcurrentMapCache("aclCache");
            return new SpringCacheBasedAclCache(
                springCache, grantStrategy, adminStrategy);
        }

        @Bean
        AclAuthorizationStrategy adminStrategy() {
            return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
        }

        @Bean
        PermissionGrantingStrategy grantStrategy() {
            return new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger());
        }

        @Bean
        DocumentService documentService() {
            return new DocumentService();
        }
    }

    public static class DocumentService {
        @PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
        public String read(@P("id") Long id) {
            return "DOC:" + id;
        }
    }

    @BeforeEach
    void prepareHierarchy() {
        long base = IDS.getAndAdd(10L);
        folderA = new ObjectIdentityImpl("demo.Folder", base);
        folderB = new ObjectIdentityImpl("demo.Folder", base + 1L);
        docId = base + 2L;
        document = new ObjectIdentityImpl("demo.Document", docId);

        MutableAcl a = service.createAcl(folderA);
        a.insertAce(0, BasePermission.READ, new PrincipalSid("alice"), true);
        service.updateAcl(a);

        MutableAcl b = service.createAcl(folderB);
        b.insertAce(0, BasePermission.READ, new PrincipalSid("bob"), true);
        service.updateAcl(b);

        MutableAcl child = service.createAcl(document);
        child.setParent(service.readAclById(folderA));
        child.setEntriesInheriting(true);
        service.updateAcl(child);
    }

    @AfterEach
    void cleanup() {
        // Delete child before parent to avoid violating the parent_object foreign key.
        service.deleteAcl(document, false);
        service.deleteAcl(folderA, false);
        service.deleteAcl(folderB, false);
    }

    private MutableAcl currentChild() {
        return (MutableAcl) service.readAclById(document);
    }

    private boolean canRead(ObjectIdentity oid, String username) {
        Acl acl = service.readAclById(oid);
        Sid sid = new PrincipalSid(username);
        try {
            return acl.isGranted(
                List.of(BasePermission.READ), List.of(sid), true);
        } catch (NotFoundException missingRule) {
            // Test treats no-match as deny; this is not an explicit deny ACE.
            return false;
        }
    }

    @Test
    void parentAndInheritancePersist() {
        Acl child = service.readAclById(document);
        assertThat(child.getParentAcl()).isNotNull();
        assertThat(child.getParentAcl().getObjectIdentity())
            .isEqualTo(folderA);
        assertThat(child.isEntriesInheriting()).isTrue();
        assertThat(child.getEntries()).isEmpty();
    }

    @Test
    @WithMockUser(username = "alice", roles = "ACL_ADMIN")
    void aliceReadsThroughInheritedFolderGrant() {
        assertThat(canRead(document, "alice")).isTrue();
        assertThat(AopUtils.isAopProxy(documents)).isTrue();
        assertThat(documents.read(docId)).isEqualTo("DOC:" + docId);
    }

    @Test
    @WithMockUser(username = "bob", roles = "ACL_ADMIN")
    void bobHasNoReadGrantFromFolderA() {
        assertThat(canRead(document, "bob")).isFalse();
        assertThatThrownBy(() -> documents.read(docId))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void changingAclOwnerDoesNotAutomaticallyGrantRead() {
        MutableAcl child = currentChild();
        Sid bob = new PrincipalSid("bob");

        child.setOwner(bob);
        service.updateAcl(child);

        assertThat(currentChild().getOwner()).isEqualTo(bob);
        assertThat(canRead(document, "bob")).isFalse();
        assertThat(canRead(document, "alice")).isTrue();
    }

    @Test
    void movingToFolderBChangesInheritedReadGrant() {
        assertThat(canRead(document, "alice")).isTrue();
        assertThat(canRead(document, "bob")).isFalse();

        MutableAcl child = currentChild();
        child.setParent(service.readAclById(folderB));
        service.updateAcl(child);

        assertThat(currentChild().getParentAcl().getObjectIdentity())
            .isEqualTo(folderB);
        assertThat(canRead(document, "alice")).isFalse();
        assertThat(canRead(document, "bob")).isTrue();
    }

    @Test
    void disablingInheritanceKeepsParentLinkButStopsGrant() {
        MutableAcl child = currentChild();
        child.setEntriesInheriting(false);
        service.updateAcl(child);

        Acl fresh = service.readAclById(document);
        assertThat(fresh.getParentAcl().getObjectIdentity())
            .isEqualTo(folderA);
        assertThat(fresh.isEntriesInheriting()).isFalse();
        assertThat(canRead(document, "alice")).isFalse();
    }

    @Test
    void enablingInheritanceAgainRestoresParentGrant() {
        MutableAcl child = currentChild();
        child.setEntriesInheriting(false);
        service.updateAcl(child);
        assertThat(canRead(document, "alice")).isFalse();

        child = currentChild();
        child.setEntriesInheriting(true);
        service.updateAcl(child);

        assertThat(currentChild().isEntriesInheriting()).isTrue();
        assertThat(canRead(document, "alice")).isTrue();
    }

    @Test
    void detachingParentStopsInheritedGrant() {
        MutableAcl child = currentChild();
        child.setParent(null);
        service.updateAcl(child);

        assertThat(currentChild().getParentAcl()).isNull();
        assertThat(canRead(document, "alice")).isFalse();
    }

    @Test
    void localGrantStillWorksWithoutParentInheritance() {
        MutableAcl child = currentChild();
        child.setEntriesInheriting(false);
        child.insertAce(0, BasePermission.READ,
            new PrincipalSid("bob"), true);
        service.updateAcl(child);

        assertThat(canRead(document, "bob")).isTrue();
        assertThat(canRead(document, "alice")).isFalse();
        assertThat(currentChild().getEntries()).hasSize(1);
    }

    @Test
    void localDenyTakesPriorityOverInheritedGrantForSameSid() {
        MutableAcl child = currentChild();
        child.insertAce(0, BasePermission.READ,
            new PrincipalSid("alice"), false);
        service.updateAcl(child);

        assertThat(canRead(document, "alice")).isFalse();
        assertThat(currentChild().getEntries()).hasSize(1);
        assertThat(currentChild().getEntries().get(0).isGranting()).isFalse();
    }

    @Test
    void changingParentAceIsVisibleForPreviouslyReadChild() {
        assertThat(canRead(document, "alice")).isTrue();

        MutableAcl parent = (MutableAcl) service.readAclById(folderA);
        parent.deleteAce(0);
        service.updateAcl(parent);

        assertThat(canRead(document, "alice")).isFalse();
    }

    @Test
    void databaseColumnsReflectOwnerParentAndInheritance() {
        MutableAcl child = currentChild();
        child.setOwner(new PrincipalSid("bob"));
        child.setParent(service.readAclById(folderB));
        child.setEntriesInheriting(false);
        service.updateAcl(child);

        var jdbc = new JdbcTemplate(dataSource);
        var row = jdbc.queryForMap(
            "select o.entries_inheriting as inherit_flag, " +
            "s.sid as owner_name, p.object_id_identity as parent_object " +
            "from acl_object_identity o " +
            "join acl_sid s on s.id = o.owner_sid " +
            "left join acl_object_identity p on p.id = o.parent_object " +
            "join acl_class c on c.id = o.object_id_class " +
            "where c.class = ? and o.object_id_identity = ?",
            "demo.Document", docId.toString()
        );

        assertThat(row.get("OWNER_NAME")).isEqualTo("bob");
        assertThat(row.get("INHERIT_FLAG")).isEqualTo(false);
        assertThat(String.valueOf(row.get("PARENT_OBJECT")))
            .isEqualTo(String.valueOf(
                ((ObjectIdentity) folderB).getIdentifier()));
    }
}
```

### 8.4. Design Explanation and Expected Outcomes

`@BeforeEach` creates two Folder ACLs and one Document ACL. Mutators are invoked on existing ACLs and then **persisted via `updateAcl`**. Each test uses fresh identities; `@AfterEach` deletes the Document before the two Folders to avoid self-referencing foreign-key errors.

**Test authentication:** defaults to `@WithMockUser(username="acl-admin", roles="ACL_ADMIN")` so fixture ACL administration succeeds. Alice/Bob tests override the username while keeping `ROLE_ACL_ADMIN` so `@BeforeEach` can set up the tree. The ACL admin role **is not a READ ACE**, so authorization outcomes still come from Alice/Bob's grants on the right Folder ACL.

**`canRead` helper:** calls `Acl.isGranted(...)` and intentionally turns `NotFoundException` (no matching rule) into `false` at the **test** level without confusing no-match with an explicit deny ACE. Applications need fail-closed policies and proper error handling rather than swallowing unrelated database errors.

**HTTP/service test:** `DocumentService.read` carries `@PreAuthorize("hasPermission(#id,'demo.Document','READ')")`, invoked through a Spring proxy. Alice's test should succeed, while Bob's should throw `AccessDeniedException`.

**JDBC verification:** tests changing owner, parent, and inheritance all read back via the service. The final test queries the actual `acl_object_identity` and `acl_sid` columns in HSQLDB, proving database persistence rather than just checking Java object state.

| Test | Behavior verified |
| --- | --- |
| `parentAndInheritancePersist` | Parent A link and `inheritance=true` were saved |
| `aliceReadsThroughInheritedFolderGrant` | Alice inherits READ via parent A |
| `bobHasNoReadGrantFromFolderA` | Bob has no matching rule; service is blocked |
| `changingAclOwnerDoesNotAutomaticallyGrantRead` | Owner becomes Bob, yet Bob does not automatically get READ |
| `movingToFolderBChangesInheritedReadGrant` | Alice loses inherited READ from A; Bob gains READ from B |
| `disablingInheritanceKeepsParentLinkButStopsGrant` | With parent present and `inheritance=false`, parent ACEs are not used |
| `enablingInheritanceAgainRestoresParentGrant` | Re-enabling inheritance restores the parent grant |
| `detachingParentStopsInheritedGrant` | `setParent(null)` removes the inheritance path |
| `localGrantStillWorksWithoutParentInheritance` | Local grant still applies when inheritance is disabled |
| `localDenyTakesPriorityOverInheritedGrantForSameSid` | Explicit local deny blocks matching parent grant |
| `changingParentAceIsVisibleForPreviouslyReadChild` | Updating parent ACL affects a previously read/cached child |
| `databaseColumnsReflectOwnerParentAndInheritance` | Owner/parent/inheritance columns are persisted in SQL |

Run:

```bash
gradle test --tests demo.AclHierarchyTest
```

If using the Gradle Wrapper: Linux/macOS `./gradlew test --tests demo.AclHierarchyTest`; Windows `gradlew.bat test --tests demo.AclHierarchyTest`.

**Expected outcome:** 12 JUnit tests pass and Gradle reports `BUILD SUCCESSFUL` when the project and dependencies are set up properly. This is an **expectation based on the sample design**, not stdout captured from an actual run. Full test report: `build/reports/tests/test/index.html`. If a test fails, check Spring Security ACL version, SQL identity/schema, cache invalidation, SIDs, proxies, and query aliases before changing assertions.

## 9. Distinguishing the Three Operations via a Scenario Matrix

Example: Document initially has parent A; A grants Alice READ, B grants Bob READ; Document has no local ACEs.

| Change | Document owner | Parent | Inherit | Alice READ | Bob READ |
| --- | --- | --- | --- | --- | --- |
| Initial state | acl-admin | A | true | Allow | No matching rule |
| Change owner to Bob | bob | A | true | **Allow** | **Not auto-allowed** |
| Switch parent to B | acl-admin | B | true | No matching rule | **Allow** |
| Disable inheritance | acl-admin | A | false | Parent ACEs ignored | Parent ACEs ignored |
| Switch to parent B with inheritance off | acl-admin | B | false | Parent ACEs ignored | Parent ACEs ignored |
| Detach parent | acl-admin | null | true | No inheritance source | No inheritance source |
| Disable inheritance and grant local READ to Bob | acl-admin | A | false | Parent ACEs ignored | **Allowed by local ACE** |
| Local deny READ for Alice while inheriting from A | acl-admin | A | true | **Locally denied** | No matching rule |

This table reflects `DefaultPermissionGrantingStrategy` and the hypothetical ACEs. If an ACL has multiple matching SIDs/permissions or a custom strategy, outcomes can vary with ordering and evaluation rules; always write integration tests for your real system.

## 10. Especially Dangerous Mistakes

### 10.1. Assuming the New Owner Automatically Receives Read Permission

`acl.setOwner(new PrincipalSid("bob"))` does not add `BasePermission.READ` for Bob. If business rules require transferring read/write rights, use `insertAce`/`deleteAce` or your defined policy and save. Conversely, the previous owner may retain a READ ACE after ownership transfer unless revoked.

### 10.2. Assuming Having a Parent Means Automatic Inheritance

`setParent(folderAcl)` stores the link, yet with `entriesInheriting=false`, folder permissions never flow down to the child. Test **both `getParentAcl()` and `isEntriesInheriting()`** along with a principal before and after the change.

### 10.3. Mutating the Java Object and Forgetting `updateAcl`

`MutableAcl` is an in-memory mutable object; after calling `setOwner`, `setParent`, or `setEntriesInheriting`, you must call `MutableAclService.updateAcl(acl)` to sync persistence. Verify with a **fresh read** from the service and, where needed, SQL queries.

### 10.4. Confusing Local ACEs with Inherited ACEs

`acl.getEntries()` returns only **local** ACEs; parent ACEs do not necessarily appear in that list. Never conclude "the child has 0 ACEs, so everyone is denied" when the child has a parent and `inheritance=true`. Conversely, do not manually flatten all ancestor ACEs to write custom policies when `Acl.isGranted` already enforces the configured strategy.

### 10.5. Moving a Parent ACL Across Tenants

Moving a Document into Folder B in a different tenant can leak data through inherited `READ` rights if validation is missing. Verify both child and newParent tenants, confirm the actor is permitted to move, validate the target, review whether scope widens or narrows as intended, and update business records in tandem.

### 10.6. Ignoring Cycles and Tree Depth

A cyclic parent graph can cause ACL lookups to fail or recurse indefinitely. **Never create a cycle** hoping a database foreign key will catch it; implement graph validation and concurrent-move controls.

### 10.7. Trusting a Single-JVM Cache in a Multi-Node System

One instance may see the new owner/parent while another keeps serving the stale ACL. Implement broadcast invalidation, TTLs, monitoring, and multi-node revocation tests. For sensitive permissions, stale-cache lifetimes must comply with security policy SLAs.

### 10.8. Assuming Transactions Automatically Guarantee Everything

Updating an ACL and domain tables across two DataSources is not atomic merely from a single `@Transactional`. Across multiple services/DBs, design explicit transactions, outbox, or compensation, and define behavior on partial failure.

### 10.9. Forgetting Separate Administrative Authorization

`@PreAuthorize("hasAuthority('ACL_MANAGE')")` is a method-level guard, not a replacement for `AclAuthorizationStrategy` on ACL mutators. Nor should a user with `ROLE_ACL_ADMIN` in ACL infrastructure automatically be able to move any document into any folder: enforce tenant/ownership/resource constraints too.

## 11. Production Testing Procedure

Scenarios to include in your integration test suite:

1. **Change owner:** verify the new `acl_sid` value, proper change of admin rights, and that READ/WRITE ACEs are neither accidentally kept nor dropped.
2. **Change parent:** test moving from parent A to parent B, checking both newly granted users and users losing access when no local ACE exists.
3. **Toggle inheritance:** verify the parent link stays intact while permissions stop inheriting when false; re-enable only when policy allows.
4. **Local deny vs. parent grant:** ensure conflict resolution matches the real strategy.
5. **Ancestor update:** update an ACE on a grandparent and verify children/grandchildren reflect the change accurately.
6. **Null parent:** upon detaching parent, inherited permissions vanish while local ACEs remain active.
7. **Missing data:** `readAclById` for an object without an ACL may throw `NotFoundException`; admin services must fail closed.
8. **Unloaded SIDs:** `UnloadedSidException` can occur when loading an ACL with a subset of SIDs and evaluating another; never treat it as allow.
9. **Concurrency:** two concurrent requests changing parent/owner; guard against lost updates and cycles.
10. **Transactions:** if updating the business `folderId` fails, parent ACL changes must roll back/compensate per contract.
11. **Caching:** test permissions after changes on both the writing node and peer nodes; verify no stale grant outlives its SLA.
12. **Auditing:** log actor, resource, old/new owner, old/new parent, old/new inheritance, reason, and outcome; avoid logging tokens or sensitive payloads.

## 12. Practice Exercises

**Exercise A — Owner is not a domain permission:** Change a Document's ACL owner to Carol while leaving ACEs untouched. Predict whether Carol receives READ, then verify with `Acl.isGranted` and `@PreAuthorize`.

**Exercise B — Three-level ACL:** Build Organization → Folder → Document. Organization grants READ to `ROLE_STAFF`; toggle inheritance at each level and identify where propagation stops.

**Exercise C — Switching folders:** Add parent C granting WRITE to Alice; move Document from A to C and prove WRITE changes via inheritance. Add a local deny WRITE to observe conflict resolution.

**Exercise D — Cache revocation:** Read a Document to populate the cache, switch the parent's grant to deny, and re-check on the same instance and another instance. Write acceptance criteria for permission revocation.

**Exercise E — Race/cycle:** Two admins concurrently move A under B and B under A. Propose graph validation and locking/optimistic-version strategies preventing cycles.

**Exercise F — Different resource types:** Try reparenting `demo.Document#42` to `demo.Folder#10` in the same tenant and to `demo.Folder#10` in another tenant. Which database fields/information are needed to prevent `ObjectIdentity` collisions?

## 13. Implementation Checklist

- [ ] Operate via **`MutableAcl` and `MutableAclService.updateAcl`**, never raw SQL updates bypassing caches.
- [ ] Store **owner** with a non-null `Sid`; changing owner neither grants nor revokes domain ACEs automatically.
- [ ] Load **parent** via `AclService.readAclById`; never pass a `Long` or domain entity to `setParent`.
- [ ] Test **inheritance** independently from the parent link; include false/true/null-parent and multi-level cases.
- [ ] Verify the actor holds both ACL management rights and tenant-scoped resource permissions; never give ACL admin to all users.
- [ ] Keep the parent graph acyclic and free of unintended cross-tenant links; guard concurrent updates.
- [ ] Wrap updates in proper transactions consistent with domain data.
- [ ] Evict/invalidate caches across **all** relevant instances after owner/parent/inheritance/ancestor updates.
- [ ] Test grants, explicit denies, no-match, local vs. inherited, and `NotFoundException`.
- [ ] Audit owner/parent/inheritance changes, especially whenever access expands.
- [ ] Verify DB engine/schema and identity queries match the deployed Spring Security ACL version.

## 14. Conclusion

The three APIs `setOwner`, `setParent`, and `setEntriesInheriting` modify **three distinct aspects** of an ACL:

- **`setOwner`**: who administers the ACL per the configured strategy; **does not transfer READ/WRITE ACEs**.
- **`setParent`**: which parent ACL is referenced; **does not enable inheritance**.
- **`setEntriesInheriting`**: whether permission evaluation checks the parent ACL; **does not delete local ACEs**.

Use `MutableAclService.updateAcl` to persist changes and verify **JDBC read-back**, `Acl.isGranted`/`hasPermission` enforcement, caching, transactions, and administrative policies. Whenever these operations alter permissions across an entire resource tree, evaluate user and tenant impact before committing.

## Official References

- Spring Security 6.5 — Domain Object Security (ACLs): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- Spring Security 6.5 — ACL schema (HSQLDB and database dialects): https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html
- Spring Security 6.5 API — `MutableAcl`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/MutableAcl.html
- Spring Security 6.5 API — `Acl`, parent, and `isEntriesInheriting`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/Acl.html
- Spring Security 6.5 API — `AclImpl`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclImpl.html
- Spring Security 6.5 API — `AclAuthorizationStrategyImpl`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclAuthorizationStrategyImpl.html
- Spring Security 6.5 API — `JdbcMutableAclService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html
- Spring Security 6.5 API — `AclCache`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/AclCache.html
