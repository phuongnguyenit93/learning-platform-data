# Acl, AccessControlEntry, ObjectIdentity, Sid, and Permission in Spring Security ACL

## 1. What Problem Does ACL Solve?

Role-Based Access Control (RBAC) usually answers: *Does the user have the EDITOR role?* However, a document management application often needs to answer more specific questions: *Is Alice allowed to read document 42? Is Bob denied from reading that exact same document? Can the REVIEWER group read this document without being able to delete it?*

**Access Control List (ACL)** is a model that attaches permissions to **individual business objects**. Instead of applying one coarse role across all documents, the system stores rule entries specifying which user/group has which permission on a specific document.

In Spring Security ACL, five core concepts connect together:

- **`Acl`**: the list of access rules for **a single object**.
- **`AccessControlEntry` (ACE)**: **one rule entry** inside an ACL, representing granting or denying a permission.
- **`ObjectIdentity`**: the key identifying the **exact object** being protected, typically a `type + identifier` pair.
- **`Sid`** (*Security Identity*): the subject receiving permission, such as a principal or a `GrantedAuthority`.
- **`Permission`**: the type of operation/right on the object, such as `READ`, `WRITE`, `DELETE`.

This lesson belongs to the **ACL Foundation** group in Spring Security Authorization. The goal is to understand **data relationships, API semantics, and decision mechanics**, not merely memorize interface names.

After this lesson, you will be able to:

1. Explain accurately what ACEs an ACL contains and why `ObjectIdentity` differs from `Sid`.
2. Distinguish between `grant=true`, `grant=false`, and **no matching ACE**.
3. Use `PrincipalSid`, `GrantedAuthoritySid`, `ObjectIdentityImpl`, and `BasePermission`.
4. Understand bitmask permissions, ACE/SID ordering, and parent ACL inheritance.
5. Run Java 17+ tests using the actual `spring-security-acl` interfaces/implementations.
6. Know how these objects are persisted in the four standard tables and wired to `AclService`/`PermissionEvaluator`.

**Version scope:** API examples use Spring Security ACL 6.5.x and Java 17+; the Gradle project uses Spring Boot BOM 3.5.0 for dependency management. When using Spring Security 7.x or another project version, check the corresponding API/Javadoc.

## 2. A Running Example

Suppose we have a business document `Document(id=42, title="Budget")`. Desired rules:

| User or Group | Action | Decision |
| --- | --- | --- |
| `alice` | `READ` | Grant |
| `alice` | `WRITE` | Grant |
| `bob` | `READ` | Explicit deny |
| `ROLE_REVIEWER` | `READ` | Grant |
| `charlie` | `DELETE` | No matching rule |

Conceptual model:

```text
ObjectIdentity
  type       = "demo.Document"
  identifier = 42
       |
       v
Acl (rules specifically for document #42)
  owner = PrincipalSid("acl-admin")
  parentAcl = null
  entriesInheriting = false
       |
       +---- ACE 0: PrincipalSid("alice")        READ   GRANT
       +---- ACE 1: PrincipalSid("alice")        WRITE  GRANT
       +---- ACE 2: PrincipalSid("bob")          READ   DENY
       +---- ACE 3: GrantedAuthoritySid(REVIEWER) READ  GRANT
```

Note that the string in code will be `"ROLE_REVIEWER"`, while `REVIEWER` in the diagram is shortened for readability.

**Each ACE combines three core elements:** *which object's ACL* + *which SID* + *which Permission*, along with a **`granting`** flag indicating grant or deny. An ACL can have multiple ACEs for the same SID with different permissions.

Pitfall to avoid: `Document.owner` in the business table **does not automatically mean** `Acl.getOwner()`. The ACL owner governs ACL administration permissions according to the strategy, whereas document read/write access is evaluated via ACEs and the granting strategy; the two concepts may coincide or differ.

## 3. Concept 1: `ObjectIdentity` — Identifying the Exact Object

Interface:

```java
package org.springframework.security.acls.model;

public interface ObjectIdentity extends java.io.Serializable {
    java.io.Serializable getIdentifier();
    String getType();
}
```

This is an abridged view of the essential members for learning, **not the verbatim full interface source**.

Implementation example:

```java
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.ObjectIdentity;

ObjectIdentity document42 =
    new ObjectIdentityImpl("demo.Document", 42L);

ObjectIdentity invoice42 =
    new ObjectIdentityImpl("demo.Invoice", 42L);
```

- `getType()`: object type string, usually the Java domain class name.
- `getIdentifier()`: unique ID **within the object type scope**. `42L` is a `Long` ID.
- `document42` **differs from** `invoice42` even though both have ID 42.
- `new ObjectIdentityImpl("demo.Document", 42L)` and another instance with the same type/ID represent the same identity under the default implementation.

There is also the constructor `new ObjectIdentityImpl(Document.class, 42L)`; the class-based constructor uses that class's name as the type. **Be consistent in how you construct types** between ACL writes and permission reads: `"demo.Document"`, `Document.class`, or a proxy class can produce different type strings if used carelessly.

Avoid using mutable business identifiers like document titles or slugs as long-term ACL identifiers when a stable primary key is available. In a multi-tenant system, type and identifier must uniquely distinguish the object/tenant; never assume overlapping auto-increment IDs across two tenants refer to the same resource.

`ObjectIdentity` **is not** the full `Document` entity, does not hold document contents, and does not decide permissions by itself. It is the **linking key** binding an ACL to the right record.

## 4. Concept 2: `Sid` — Who Is Granted or Blocked?

`Sid` stands for *Security Identity*. It abstracts the subject so ACLs do not have to store full `Authentication`, `UserDetails`, or token objects directly. Two common implementations:

```java
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.model.Sid;

Sid alice = new PrincipalSid("alice");
Sid reviewerRole = new GrantedAuthoritySid("ROLE_REVIEWER");
```

**`PrincipalSid`** represents a principal, usually identified by `Authentication.getName()`. When the logged-in user is Alice, the corresponding principal SID can be `PrincipalSid("alice")`. By default, Spring Security also provides a constructor accepting `Authentication`.

**`GrantedAuthoritySid`** represents an authority granted to an authentication, such as `ROLE_REVIEWER`. Multiple users can share an authority; a single ACE attached to an authority avoids creating separate ACEs for every member when application policy permits.

Examples:

| Authentication | Typical SID List Evaluated |
| --- | --- |
| Alice with `ROLE_REVIEWER` | `PrincipalSid("alice")`, `GrantedAuthoritySid("ROLE_REVIEWER")` |
| Bob with `ROLE_EDITOR` | `PrincipalSid("bob")`, `GrantedAuthoritySid("ROLE_EDITOR")` |
| Anonymous | Needs its own policy; do not assume an authenticated principal with rights |

SIDs must match the **same type and value** stored in the ACL. `PrincipalSid("ROLE_REVIEWER")` **is not equivalent to** `GrantedAuthoritySid("ROLE_REVIEWER")`, because one is a principal name and the other is an authority.

`SidRetrievalStrategy` can build the list of SIDs from `Authentication` (typically principal plus authorities). If you have specialized identity types such as tenant groups or organizations, you need a strategy to map/maintain valid SIDs and ensure they never cross tenant boundaries.

**Warning:** `Sid` is not a session ID, token ID, or role hierarchy policy. It is an identity representation **for matching ACEs**.

## 5. Concept 3: `Permission` — What Operation Is Allowed?

`Permission` in Spring Security ACL primarily represents a **bitmask** and a display symbol. Standard constants in `BasePermission`:

| `BasePermission` Constant | Bit | Decimal Mask | Common Meaning |
| --- | ---: | ---: | --- |
| `READ` | 0 | 1 | Read content |
| `WRITE` | 1 | 2 | Modify content |
| `CREATE` | 2 | 4 | Create resource |
| `DELETE` | 3 | 8 | Delete resource |
| `ADMINISTRATION` | 4 | 16 | Administer permissions |

Example:

```java
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.model.Permission;

Permission read = BasePermission.READ;
Permission write = BasePermission.WRITE;

System.out.println(read.getMask());  // 1
System.out.println(write.getMask()); // 2
```

These values are **permission masks**, not document or user sequence numbers. 32 bits do not limit the system to 32 objects; each object can have its own ACL and many ACEs, while the bitmask represents **permission types**.

Furthermore, mask `READ=1` **does not grant READ to anyone by itself**. An ACE must bind that permission to a SID on the right object, with `granting=true` or `false`. Nor does a permission define business semantics automatically: the system must agree on what `READ` means regarding drafts, file downloads, or data exports.

`BasePermission` provides five default permissions, but applications can define custom `Permission` instances. When using combined bitmasks, test the matching strategy (`PermissionGrantingStrategy`) rather than assuming "any mask containing a bit is definitely granted" across all implementations.

## 6. Concept 4: `AccessControlEntry` — A Grant/Deny Rule Entry

`AccessControlEntry` (ACE) is a single rule entry inside an ACL. Core getters:

```java
AccessControlEntry ace = ...; // Obtained from acl.getEntries()

ace.getAcl();          // ACL owning the ACE
ace.getSid();          // Principal or authority receiving permission
ace.getPermission();   // For example BasePermission.READ
ace.isGranting();      // true = grant, false = deny
ace.getId();           // ACE ID, may be null before saving
```

This snippet **only illustrates the API**; it is not a standalone program because `ace` is uninitialized.

Alice's READ ACE on document #42 can be visualized as:

```text
ACL   : Document#42
SID   : PrincipalSid("alice")
PERM  : READ (mask = 1)
GRANT : true
```

Bob's ACE is:

```text
ACL   : Document#42
SID   : PrincipalSid("bob")
PERM  : READ (mask = 1)
GRANT : false
```

**Explicit denial** (`granting=false`) is not the same as **having no ACE**. With `DefaultPermissionGrantingStrategy`, a matching deny ACE results in `isGranted(...) == false`. Finding no matching ACE in the current ACL or eligible parent ACL causes `Acl.isGranted` to throw `NotFoundException` — the caller must decide how to handle it, typically **deny/fail closed** in the authorization policy. <https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html>

**ACE order can matter.** The Spring ACL model includes `ace_order`, and the default strategy checks permissions in permission/SID/ACE sequence. If a principal also holds `ROLE_REVIEWER`, or if there are duplicate/conflicting ACEs, the outcome depends on the strategy and ordering; do not claim "deny always wins" or "grant always wins" for every policy without dedicated tests.

Do not mutate an `AccessControlEntry` obtained from `getEntries()` directly: the ACE interface represents an immutable record. To modify a `MutableAcl`'s rules, use `insertAce`, `updateAce`, `deleteAce`, then persist via `MutableAclService.updateAcl(...)` if backed by a store. Controlling **who may modify an ACL** is the responsibility of `AclAuthorizationStrategy`, distinct from `PermissionGrantingStrategy` used when **checking domain object access**.

## 7. Concept 5: `Acl` — The Rule Set for an Object

`Acl` is bound to **one `ObjectIdentity`** and holds the ACEs needed to evaluate permissions. Key methods to remember:

```java
Acl acl = ...; // For example, read from AclService

ObjectIdentity identity = acl.getObjectIdentity();
Sid aclOwner = acl.getOwner();
java.util.List<AccessControlEntry> localEntries = acl.getEntries();
Acl parent = acl.getParentAcl();
boolean inherit = acl.isEntriesInheriting();
boolean granted = acl.isGranted(
    java.util.List.of(BasePermission.READ),
    java.util.List.of(new PrincipalSid("alice")),
    false
);
```

This is an **API illustration snippet** and cannot run standalone since `acl` is uninitialized.

- `getObjectIdentity()` states **which object** the ACL protects.
- `getOwner()` returns the ACL owner SID. The owner's administrative meaning depends on the implementation; **the owner does not automatically get READ/WRITE** on every domain object without a grant per the strategy.
- `getEntries()` returns the ACEs **in the current ACL**, not an aggregated list of all parent ACEs. Use it for inspecting/editing the ACL; **do not iterate this list yourself to make authorization decisions in business code**.
- `getParentAcl()` and `isEntriesInheriting()` enable linking to and inheriting rules from a parent ACL when enabled.
- `isGranted(List<Permission>, List<Sid>, boolean administrativeMode)` is the permission decision API. `administrativeMode=true` indicates an administrative query to suppress audit logging where supported by the strategy, **not** a "bypass security / allow admin" flag.

The core of `isGranted` is executed by `PermissionGrantingStrategy`, which defaults to `DefaultPermissionGrantingStrategy`.

When no matching ACE exists, an implementation may throw `NotFoundException` instead of returning `false`. When an ACL loads only **a subset of SIDs**, calling `isGranted` with an unloaded SID can throw `UnloadedSidException`. Policy code must classify these outcomes properly and prefer **denying whenever no reliable grant decision is obtained**.

### 7.1. Parent ACL and Inheritance

Suppose folder #10 has an ACL granting `ROLE_STAFF` READ. Document #42 has `parentAcl` pointing to folder #10's ACL:

- If `entriesInheriting=true`, parent rules **can be consulted** when the child ACL has no matching ACE per the implementation's strategy.
- If `entriesInheriting=false`, the child ACL does not inherit parent permissions merely because a parent link exists.
- A matching **explicit deny** in the child ACL is not treated as "no rule": the default strategy typically evaluates the decision on the child before trying the parent.

Verify ACE ordering, inheritance rules, and tenant relationships in integration tests. Never allow users to arbitrarily assign parent links to inherit permissions from another tenant.

### 7.2. Decision Sequence at a Glance

```text
Authentication
  -> corresponding SIDs (principal + authorities)
          |
          v
ObjectIdentity(type, id)
  -> AclService.readAclById(...)
          |
          v
Acl (current ACEs + parent/inheritance info)
          |
          v
Acl.isGranted(permissions, sids, administrativeMode)
  -> PermissionGrantingStrategy
      -> MATCH GRANT   -> true
      -> MATCH DENY    -> false
      -> NO MATCH      -> check parent ACL if eligible
                          or NotFoundException
```

This is a **conceptual flow**: an implementation may optimize caching, batch loading, and lookup order. Always rely on the configured `PermissionGrantingStrategy`, rather than assuming every strategy uses identical ordering.

## 8. How Do the Five Concepts Map to the Four Standard ACL Tables?

Spring Security ACL provides a standard relational schema to persist rules. Common table names:

| Table | Primary Object / Data | Example Use |
| --- | --- | --- |
| `ACL_CLASS` | Domain object type (class/type) | Stores one row representing `demo.Document` |
| `ACL_SID` | Principal or authority | Distinguishes `alice` from `ROLE_REVIEWER`; SID type flag |
| `ACL_OBJECT_IDENTITY` | One instance per `ACL_CLASS` + object ID, owner SID, parent, and inheritance | ACL of document #42 |
| `ACL_ENTRY` | Individual ACE: object identity, SID, mask, granting, order, audit | Alice READ grant, Bob READ deny |

Relationship diagram:

```text
ACL_CLASS (type)
     |
     v
ACL_OBJECT_IDENTITY (ObjectIdentity instance, owner, parent, inheritance)
     |                                              |
     |                                              v
     |                                        ACL_SID (owner)
     v
ACL_ENTRY (ACE: permission mask, granting, ace_order, audit)
     |
     v
ACL_SID (recipient: principal or authority)
```

An ACL can have many ACEs; an ACE belongs to **one** ACL and **one** SID. Rules for multiple distinct permissions are usually multiple ACEs, though bitmasks allow representing permissions as chosen by the implementation. The object identifier key in the schema must be stable and consistent with how `ObjectIdentity` is created.

**Illustrative** data example (not a standalone SQL migration):

```text
ACL_CLASS:
  id=1, class="demo.Document"

ACL_SID:
  id=11, principal=true, sid="alice"
  id=12, principal=true, sid="bob"
  id=13, principal=false, sid="ROLE_REVIEWER"
  id=14, principal=true, sid="acl-admin"

ACL_OBJECT_IDENTITY:
  id=100, object_id_class=1, object_id_identity=42,
  owner_sid=14, parent_object=NULL, entries_inheriting=false

ACL_ENTRY:
  ace_order=0, acl_object_identity=100, sid=11, mask=1, granting=true
  ace_order=1, acl_object_identity=100, sid=11, mask=2, granting=true
  ace_order=2, acl_object_identity=100, sid=12, mask=1, granting=false
  ace_order=3, acl_object_identity=100, sid=13, mask=1, granting=true
```

**Do not confuse three layers of IDs:** business ID `42` identifies the Document, ACL ID `100` identifies the `ACL_OBJECT_IDENTITY` row, and SID ID `11` identifies the row in `ACL_SID`. They serve different purposes.

Actual SQL migrations vary by database, dialect, key/column types, and Spring Security version. Do not substitute the illustrative table above for the official schema or omit unique constraints, foreign keys, indexes, and required audit columns.

## 9. Runnable Java 17+ Example: Creating an In-Memory ACL and Testing Permissions

To learn **the exact five Spring ACL types** without standing up a database right away, you can construct `AclImpl` directly in a test with `ObjectIdentityImpl`, `PrincipalSid`, `GrantedAuthoritySid`, and `BasePermission`, then add ACEs via `MutableAcl.insertAce`.

**Intentional limitation:** this tests the **ACL model and permission granting strategy**, with no JDBC and without demonstrating persisting/reading ACLs from a database. Production systems should create/update ACLs via `MutableAclService` rather than instantiating `AclImpl` inside business controllers or services.

### 9.1. Layout and Dependencies

```text
acl-foundations-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/AclFoundationsTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'acl-foundations-demo'
```

`build.gradle`:

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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    implementation 'org.springframework.security:spring-security-acl'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

`spring-security-acl` contains the ACL interfaces and implementations; the module pulls in required Spring Security dependencies. JUnit Jupiter runs tests without needing `@SpringBootTest` or a database. The build uses a BOM to avoid mixing versions arbitrarily. **Note:** calling the `AclImpl` constructor directly is suitable for learning/testing; use `MutableAclService.createAcl` in applications with persistence.

### 9.2. Complete Test Code

Create `src/test/java/demo/AclFoundationsTest.java`:

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.AccessControlEntry;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.security.acls.model.NotFoundException;

public class AclFoundationsTest {

    private final Sid alice = new PrincipalSid("alice");
    private final Sid bob = new PrincipalSid("bob");
    private final Sid reviewer =
        new GrantedAuthoritySid("ROLE_REVIEWER");

    private MutableAcl acl;

    @BeforeEach
    void createAcl() {
        // ACL mutation requires an identity with ACL administration permission.
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                "acl-admin",
                "unused",
                List.of(new SimpleGrantedAuthority("ROLE_ACL_ADMIN"))
            )
        );
        SecurityContextHolder.setContext(context);

        ObjectIdentity objectId =
            new ObjectIdentityImpl("demo.Document", 42L);

        AclAuthorizationStrategyImpl mutationPolicy =
            new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
            );

        acl = new AclImpl(
            objectId,
            100L, // Fake ID of the ACL record, not the Document ID.
            mutationPolicy,
            new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger()
            ),
            null,  // No parent ACL.
            null,  // Not restricted to a subset of loaded SIDs.
            false, // Do not inherit ACEs from parent.
            new PrincipalSid("acl-admin") // ACL owner.
        );

        acl.insertAce(0, BasePermission.READ, alice, true);
        acl.insertAce(1, BasePermission.WRITE, alice, true);
        acl.insertAce(2, BasePermission.READ, bob, false);
        acl.insertAce(3, BasePermission.READ, reviewer, true);
    }

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void objectIdentityUsesTypeAndIdentifier() {
        ObjectIdentity anotherDocument42 =
            new ObjectIdentityImpl("demo.Document", 42L);
        ObjectIdentity differentType =
            new ObjectIdentityImpl("demo.Invoice", 42L);

        assertThat(acl.getObjectIdentity())
            .isEqualTo(anotherDocument42)
            .isNotEqualTo(differentType);
        assertThat(acl.getObjectIdentity().getType())
            .isEqualTo("demo.Document");
        assertThat(acl.getObjectIdentity().getIdentifier())
            .isEqualTo(42L);
    }

    @Test
    void sidDistinguishesPrincipalFromAuthority() {
        assertThat(alice).isEqualTo(new PrincipalSid("alice"));
        assertThat(alice).isNotEqualTo(
            new GrantedAuthoritySid("alice")
        );
        assertThat(reviewer).isEqualTo(
            new GrantedAuthoritySid("ROLE_REVIEWER")
        );
    }

    @Test
    void basicPermissionMasksAreDistinct() {
        assertThat(BasePermission.READ.getMask()).isEqualTo(1);
        assertThat(BasePermission.WRITE.getMask()).isEqualTo(2);
        assertThat(BasePermission.CREATE.getMask()).isEqualTo(4);
        assertThat(BasePermission.DELETE.getMask()).isEqualTo(8);
        assertThat(BasePermission.ADMINISTRATION.getMask())
            .isEqualTo(16);
    }

    @Test
    void aceRecordsItsSidPermissionAndGrantFlag() {
        List<AccessControlEntry> entries = acl.getEntries();

        assertThat(entries).hasSize(4);
        AccessControlEntry first = entries.get(0);
        AccessControlEntry denial = entries.get(2);

        assertThat(first.getAcl()).isSameAs(acl);
        assertThat(first.getSid()).isEqualTo(alice);
        assertThat(first.getPermission())
            .isEqualTo(BasePermission.READ);
        assertThat(first.isGranting()).isTrue();

        assertThat(denial.getSid()).isEqualTo(bob);
        assertThat(denial.getPermission())
            .isEqualTo(BasePermission.READ);
        assertThat(denial.isGranting()).isFalse();
    }

    @Test
    void aliceHasReadAndWritePermission() {
        assertThat(acl.isGranted(
            List.of(BasePermission.READ), List.of(alice), true
        )).isTrue();

        assertThat(acl.isGranted(
            List.of(BasePermission.WRITE), List.of(alice), true
        )).isTrue();
    }

    @Test
    void bobHasExplicitReadDenial() {
        assertThat(acl.isGranted(
            List.of(BasePermission.READ), List.of(bob), true
        )).isFalse();
    }

    @Test
    void reviewerAuthorityCanRead() {
        assertThat(acl.isGranted(
            List.of(BasePermission.READ), List.of(reviewer), true
        )).isTrue();
    }

    @Test
    void missingRuleThrowsNotFoundInsteadOfReturningFalse() {
        assertThatThrownBy(() -> acl.isGranted(
            List.of(BasePermission.DELETE), List.of(alice), true
        )).isInstanceOf(NotFoundException.class);
    }

    @Test
    void aclOwnerAndContentPermissionAreDifferentConcepts() {
        assertThat(acl.getOwner())
            .isEqualTo(new PrincipalSid("acl-admin"));
        assertThat(acl.getObjectIdentity())
            .isEqualTo(new ObjectIdentityImpl("demo.Document", 42L));
        assertThat(acl.getParentAcl()).isNull();
        assertThat(acl.isEntriesInheriting()).isFalse();
    }
}
```

**Explanation of key choices:**

1. This is a **complete Java 17 test class** containing nine `@Test` cases. `@BeforeEach` creates a fresh ACL for each test, so changes in one test do not affect another.
2. `AclImpl` is a concrete implementation of `MutableAcl`, allowing ACEs to be added via `insertAce(index, permission, sid, granting)`. Having only `Acl` serves reading/checking without exposing mutation APIs.
3. `AclAuthorizationStrategyImpl` controls **permission to modify the ACL**. The test sets an `acl-admin` authentication with `ROLE_ACL_ADMIN` so `insertAce` is authorized; this role is **not** itself a READ permission on the document.
4. `DefaultPermissionGrantingStrategy` decides the result of `isGranted`; `ConsoleAuditLogger` is passed to the constructor. `administrativeMode=true` in tests suppresses query auditing where supported by the strategy, keeping test logs clean.
5. `ObjectIdentityImpl("demo.Document",42L)` is the document identity; `100L` in the ACL constructor is the ID of the test ACL record itself, not the document ID.
6. `getEntries()` is used **solely to inspect ACE metadata**, while all grant/deny decisions use `isGranted`. This follows the `Acl` contract properly.
7. `NotFoundException` when checking `DELETE` for Alice means **no matching ACE**, distinct from the `bob/READ/deny` ACE returning `false`.
8. `@AfterEach` clears `SecurityContextHolder` to avoid polluting authentication across tests. Real applications should restrict ACL update permissions to administrative services, not expose ACE editing publicly.

### 9.3. Running Tests and Checking Results

In the directory containing `build.gradle`:

```bash
gradle test --tests demo.AclFoundationsTest
```

If using the Gradle Wrapper: on Linux/macOS `./gradlew test --tests demo.AclFoundationsTest`; on Windows `gradlew.bat test --tests demo.AclFoundationsTest`.

**Expected result in a valid environment:** all **9 tests** pass and Gradle finishes with `BUILD SUCCESSFUL`. This is **expected from the example code**, not recorded stdout from an execution. Detailed JUnit results are in `build/reports/tests/test/index.html`.

| Test | What It Verifies |
| --- | --- |
| `objectIdentityUsesTypeAndIdentifier` | Type + ID properly distinguish resources |
| `sidDistinguishesPrincipalFromAuthority` | Principal SID and authority SID are distinct |
| `basicPermissionMasksAreDistinct` | Standard permission masks |
| `aceRecordsItsSidPermissionAndGrantFlag` | ACE accurately stores SID, permission, and granting |
| `aliceHasReadAndWritePermission` | Alice READ/WRITE grants |
| `bobHasExplicitReadDenial` | Bob READ explicit denial |
| `reviewerAuthorityCanRead` | REVIEWER group grant |
| `missingRuleThrowsNotFoundInsteadOfReturningFalse` | No matching ACE differs from explicit deny |
| `aclOwnerAndContentPermissionAreDifferentConcepts` | ACL owner, ObjectIdentity, parent/inherit |

If tests fail due to a different Spring Security version, verify the resolved `spring-security-acl` version via `gradle dependencies --configuration testRuntimeClasspath`; never alter assertions just to fit an unverified security behavior.

## 10. Connecting to Services and SpEL `hasPermission`

Normally, you do not construct `AclImpl` on every request. The components wired together in practice:

```text
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
              |
              v
MethodSecurityExpressionHandler
   + PermissionEvaluator / AclPermissionEvaluator
              |
              v
AclService.readAclById(ObjectIdentity, Sids)
              |
              v
LookupStrategy + AclCache + JDBC database
              |
              v
Acl.isGranted(permissions, sids, administrativeMode)
```

This is a **conceptual diagram**. How the string `'READ'` maps to `BasePermission.READ`, and how `'demo.Document'` maps to `ObjectIdentity`, depends on the configured evaluator/`PermissionFactory`. Do not assume every SpEL literal automatically maps to a `BasePermission` constant.

### 10.1. Reading an ACL

Illustrative API example:

```java
// Depends on AclService configured by the application.
ObjectIdentity objectId =
    new ObjectIdentityImpl("demo.Document", 42L);

Acl acl = aclService.readAclById(objectId);
boolean allowed = acl.isGranted(
    List.of(BasePermission.READ),
    List.of(new PrincipalSid("alice")),
    false
);
```

This is an **integration snippet**, not a standalone program: you must configure `AclService`, database, schema, lookup strategy, caching, and exception handling before use. `AclService` is the **ACL read** API, while `MutableAclService` supports persistent ACL creation, updates, and deletion. `JdbcAclService` and related implementations use `LookupStrategy`/SQL to read ACLs efficiently.

### 10.2. Updating an ACL via Administrative Paths

General flow example:

```java
ObjectIdentity objectId =
    new ObjectIdentityImpl("demo.Document", 42L);

// Requires MutableAclService dependency configured by the application,
// authentication with permission to modify ACL, and an appropriate transaction.
MutableAcl acl = mutableAclService.createAcl(objectId);

acl.insertAce(
    acl.getEntries().size(),
    BasePermission.READ,
    new PrincipalSid("alice"),
    true
);

mutableAclService.updateAcl(acl);
```

This is also an **integration snippet**, assuming the ACL does not yet exist (if it already exists, `createAcl` can fail on duplicate); updating an existing ACL requires reading it first. All ACL changes must go through **administrative authorization**, transactions, auditing, and proper cache invalidation. Never allow clients to supply arbitrary SIDs/permissions/target types to write into ACLs without authorization.

### 10.3. `@PreAuthorize` and Enforcement Timing

Example of a method reading a document:

```java
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
public Document read(@P("id") Long id) {
    return repository.findById(id).orElseThrow();
}
```

This illustrative snippet requires `Document`, `repository`, `@P`, evaluator/handler, and `@EnableMethodSecurity` configured in a real application. If the policy permits, Spring AOP enters the body; if denied, the body never runs. Crucially, `hasPermission` works only if **the right PermissionEvaluator is registered with the expression handler** and can load the right ACL.

For data writes/deletions, prioritize checking permissions **before side effects**. With `@PostAuthorize`, which checks the object after the method returns, note that the method body **has already executed**; do not rely on after-invocation checks as the sole guard against state mutation.

## 11. Common Learning and Implementation Mistakes

| Symptom / Misconception | Why It Is Wrong | How to Verify |
| --- | --- | --- |
| "`Acl` is the `Document` entity itself" | ACL only carries identity and rules, not document data | Compare `ObjectIdentity` and entity |
| "`Sid` is a session ID" | SID is the security identity of a principal/authority | Use `PrincipalSid`/`GrantedAuthoritySid` |
| "`ObjectIdentity` is just a numeric ID" | Type + ID are needed to distinguish document and invoice ID 42 | Test same ID with different types |
| "`getOwner()` always gets READ" | ACL owner mainly governs admin rights per strategy, not an automatic READ ACE | Test both owner and ACE where needed |
| "Having role VIEWER means every document is readable" | ACL must have a matching ACE for that exact ObjectIdentity | Test a granted document vs another |
| "No ACE = deny ACE" | No match may throw `NotFoundException`; matching deny ACE returns false | Test both scenarios separately |
| "`getEntries()` is enough to write custom policy" | Misses ordering, caching, inheritance, partial SID load, and strategy | Use `Acl.isGranted`/`PermissionEvaluator` |
| "ACE order doesn't matter" | Default strategy may honor the first matching entry in sequence | Test conflicting SID/permission entries |
| "Having a parent ACL automatically inherits" | `isEntriesInheriting()` controls inheritance | Test both true and false |
| "Mask 1 is document ID 1" | Mask represents the READ permission, not resource ID | Inspect `getMask()` and `ObjectIdentity` |
| "Saving ACLs needs no admin permission" | Modifying ACLs must be separately protected | Check `AclAuthorizationStrategy` |
| "ACL lookup not found means allow" | Could indicate missing rules, sync/cache error, or wrong ObjectIdentity | Fail closed; log appropriate audit |
| "Adding `hasPermission` is enough" | Requires evaluator, handler, AclService, proxy, and proper scope | Integration test direct + denied paths |
| "Changing a role updates ACL permissions immediately" | SID/authority and ACL caches must be refreshed/invalidated properly | Test grant/revoke changes and cache |

### 11.1. Specific Cases That Need Dedicated Tests

**Different document:** granting Alice READ on `demo.Document#42` does not grant it on `demo.Document#43`; the two objects have distinct `ObjectIdentity` values.

**Same ID across domain types:** `demo.Invoice#42` must not use the ACL of `demo.Document#42`.

**Role changes:** if a user is stripped of `ROLE_REVIEWER`, the SID list used during checks must reflect the updated authentication, and related caches must not serve stale permissions.

**One user with multiple SIDs:** a principal can receive grants/denies through both personal SID and roles. When rules conflict, check `PermissionGrantingStrategy`, **SID/permission list ordering**, and ACE entries. Do not assume "deny-overrides" is an immutable law without configuring and verifying it.

**Incomplete SID loading:** `Acl.isSidLoaded(sids)` indicates whether the current ACL holds entries for the checked SIDs. If not fully loaded, never interpret `UnloadedSidException` as "allow."

**ACL inheritance:** if the parent grants READ but the child ACL has an explicit deny, test against the specific strategy. If inheritance is disabled, parent rules alone cannot grant access to the child.

**Performance:** checking permissions for thousands of objects can cause many ACL lookups. `BasicLookupStrategy`, batch loading, and `AclCache` help optimize; however, caching must have an invalidation policy whenever ACEs/ACLs or related SIDs change.

## 12. Reinforcement Exercises

1. **Read the diagram:** Using document #42 and the four ACEs from the start of the lesson, write down the `READ/WRITE/DELETE` outcomes for Alice, Bob, and REVIEWER. Distinguish `false` from `NotFoundException`.
2. **Switch objects:** Create another ACL for `ObjectIdentityImpl("demo.Document", 43L)` granting only Bob READ. Prove this does not alter Document #42's permissions.
3. **Grant and revoke:** Try `deleteAce` or `updateAce` via `MutableAcl` on an ACE and re-check `isGranted`. In a database-backed environment, save through `MutableAclService` and verify cache updates.
4. **Role and principal:** Create a user holding both `PrincipalSid("bob")` and `GrantedAuthoritySid("ROLE_REVIEWER")`. Read the default strategy and write a test for SID ordering when grant/deny conflict.
5. **Parent ACL:** Create a parent ACL granting READ to `ROLE_STAFF`, attach it to a child, and toggle `setEntriesInheriting(true/false)`. Test fallback behavior when the child lacks an ACE.
6. **Multi-tenant:** Propose an ObjectIdentity/type/ID, ownership, database query, and cache key strategy ensuring tenant A's document ID 42 cannot be confused with tenant B's.
7. **Custom permission:** Create an `APPROVE` permission by implementing `Permission` with a non-overlapping mask, add an ACE, and verify the strategy interprets the mask correctly.

## 13. Pre-Design Checklist for ACL in a Real Application

- [ ] **ObjectIdentity:** stable type/ID, consistent between write and read, never confuses tenants.
- [ ] **Sid:** clearly identifies principal/role/group; never trusts client-supplied identity claims.
- [ ] **Permission:** clear READ/WRITE/DELETE semantics, non-overlapping masks, custom permissions tested if used.
- [ ] **ACE:** explicit grant or deny, order, auditing, and conflict rules tested.
- [ ] **Acl:** owner, parent/inheritance, and ACL administration permissions governed by independent policies.
- [ ] **Persistence:** schema/migrations, transactions, `AclService`/`MutableAclService`, `LookupStrategy`, cache, and invalidation in place.
- [ ] **Method security:** `PermissionEvaluator` properly registered, `hasPermission` tested directly through Spring proxies with different principals.
- [ ] **Fail closed:** no rule / not found / unloaded SID / database error never silently turns into allow.
- [ ] **Audit:** logs who changed an ACL, when, and why; avoids leaking sensitive data in logs.
- [ ] **Performance:** load-tested with many objects, many ACEs, many SIDs, and large pagination.

## 14. Summary

You can remember the model in one sentence:

> **`ObjectIdentity`** specifies *which object*; **`Sid`** specifies *who*; **`Permission`** specifies *what action*; **`AccessControlEntry`** binds those three into a *grant/deny* rule; **`Acl`** aggregates the rules for an object and uses a strategy to decide access.

To check permissions accurately, start from the exact object identity, retrieve the right ACL, build the right SIDs and permissions, and call `Acl.isGranted(...)` or a `PermissionEvaluator` wired to your ACL infrastructure. **No rule**, **explicit deny**, and **grant** must be clearly distinguished in both design and tests.

## Official References

- Spring Security 6.5 — Domain Object Security (ACLs), model and four tables: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- Spring Security 6.5 API — `Acl`, `isGranted`, parent, loaded SID: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/Acl.html
- Spring Security 6.5 API — `AclImpl`, `insertAce`, and constructors: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclImpl.html
- Spring Security 6.5 API — `DefaultPermissionGrantingStrategy`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html
- Spring Security API — `AccessControlEntry`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/AccessControlEntry.html
- Spring Security API — `ObjectIdentity`, `Sid`, `Permission`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/package-summary.html
