# Testing Direct Permissions, Inherited Permissions, and Deny ACEs in Spring Security ACL

## 1. What the Tests Must Prove

In a document management system, a folder may grant read permission to a group. Child documents can inherit that permission, yet a sensitive document may disable inheritance or hold a deny **Access Control Entry (ACE)**. If you only test "Alice can read her own document," it is easy to miss authorization bugs across all three cases.

This lesson focuses on exactly three behaviors:

1. **Direct permissions:** the ACE sits directly on the requested resource's ACL.
2. **Inherited permissions:** the child ACL has no matching ACE, has a parent ACL, and enables `entriesInheriting`, so it can receive a decision from the parent.
3. **Deny ACEs:** a matching ACE with `granting=false` causes the request to be denied under the active `PermissionGrantingStrategy`.

Example requirements:

- Folder 10 grants `READ` to Alice.
- Document 42 lives inside Folder 10 with no direct READ ACE; with inheritance enabled, Alice has READ.
- Document 43 also has parent Folder 10 yet disables inheritance; having no READ ACE, access is denied.
- Document 44 has parent Folder 10 yet carries a `granting=false` READ ACE for Alice; READ access must be denied.
- Bob cannot read merely because Alice has access: checks must always evaluate the **caller's SID**.

**Testing principle:** never assert only a bare boolean; prove **which ACE produced the result**, distinguish explicit denies from missing ACEs, and test the execution path through ACL services, evaluators, and method security.

## 2. Objects and Terminology Used

```text
Authentication (caller)
  |
  v
Sid: PrincipalSid("alice") or GrantedAuthoritySid("ROLE_EDITOR")
  |
  v
ObjectIdentity("demo.Document", documentId)
  |
  v
ACL of Document
  |-- direct ACEs: Permission, Sid, granting
  |-- parent Acl (if any)
  |-- entriesInheriting: true/false
  |
  v
PermissionGrantingStrategy
  |
  +--> true: grant
  +--> false: explicit deny per strategy
  +--> NotFoundException: lacking authoritative decision
```

| Concept | Spring Security ACL API | What tests must verify |
| --- | --- | --- |
| Resource | `ObjectIdentity`, `ObjectIdentityImpl` | Exact type and ID, no tenant mixing |
| Subject | `Sid`, `PrincipalSid`, `GrantedAuthoritySid` | Same resource with different user/role may differ |
| Permission | `Permission`, `BasePermission.READ/WRITE` | Exact permission mask; READ does not imply WRITE |
| ACE | `AccessControlEntry` | `getSid()`, `getPermission()`, `isGranting()` |
| ACL | `Acl`, `AclImpl`, `MutableAcl` | Direct entries, parent, inheritance flag |
| Read/save | `AclService`, `MutableAclService` | Persist and reload the exact same policy |
| Strategy | `PermissionGrantingStrategy` | ACE matching rules and grant/deny semantics |
| Expression integration | `AclPermissionEvaluator` | `hasPermission(...)` hits the right ACL |
| Method mechanism | `@EnableMethodSecurity`, `@PreAuthorize` | Invocations pass through the Spring AOP proxy |

Three distinct outcomes when calling `acl.isGranted(...)` directly:

- `true`: grant evidence found.
- `false`: a matching deny decision applies.
- `NotFoundException`: insufficient ACL information to reach an authoritative decision. This is **not** `true`; at the service boundary, handle it per fail-closed rules or the defined error contract.

In addition, `UnloadedSidException` indicates the ACL was loaded for only a subset of SIDs while the caller queried an unloaded SID. Never convert this exception into "that user definitely has no ACE" during test coverage; it signals incomplete loaded data.

## 3. Data Model for the Three Scenarios

Suppose:

```text
Folder #10
  ACE(PrincipalSid("alice"), READ, granting=true)
        |
        +-- Document #42: parent #10, entriesInheriting=true
        |      direct ACEs: no READ for Alice
        |
        +-- Document #43: parent #10, entriesInheriting=false
        |      direct ACEs: no READ for Alice
        |
        +-- Document #44: parent #10, entriesInheriting=true
               ACE(PrincipalSid("alice"), READ, granting=false)
```

With `DefaultPermissionGrantingStrategy`, requesting only `READ` for one SID Alice:

| Object | Direct READ ACE | Has parent? | Inherit? | Low-level API result |
| --- | --- | --- | --- | --- |
| Folder 10 | Grant READ/Alice | No | — | `true` |
| Document 42 | No | Yes | `true` | `true` via parent |
| Document 43 | No | Yes | `false` | `NotFoundException` if no other ACE |
| Document 44 | Deny READ/Alice | Yes | `true` | `false`; parent cannot "rescue" this READ check |
| Document 42 for Bob | No grant for Bob | Yes | `true` | No Bob ACE found → `NotFoundException` in this model |

**Note:** these results apply when querying a single `READ` permission and one SID (Alice or Bob) under the default strategy. When passing **multiple permissions** or **multiple SIDs**, the algorithm applies precedence ordering; never overgeneralize the table to "deny always wins."

## 4. Direct Permissions: What to Test?

A direct ACE resides on the resource's own ACL:

```text
Document #50
  ACE: alice + READ  + granting=true
  ACE: alice + WRITE + granting=false
```

Desired tests:

- Alice checks READ on Document 50 → `true`.
- Alice checks WRITE on Document 50 → `false`.
- Bob checks READ on Document 50 with no Bob/parent ACE → no decision (`NotFoundException`).
- Document 51 has no ACE for Alice → Document 50's grant **does not apply** to 51.
- `ROLE_EDITOR` having READ on a document does not grant access to callers lacking that authority.

Core idea code:

```java
Acl acl = aclService.readAclById(
        new ObjectIdentityImpl("demo.Document", 50L));

boolean canRead = acl.isGranted(
        List.of(BasePermission.READ),
        List.of(new PrincipalSid("alice")),
        false);
```

This is an **integration snippet**; `aclService` must be configured by the application. The final argument `administrativeMode=false` enables configured auditing. Pure logic tests can pass `true` to skip audit logging, though that boolean **does not** mean "bypass authorization."

Tests should verify *both permission and scope* using resource type+ID, SID, and permission mask. Never use `hasRole` as a substitute for per-object ACL checks.

## 5. Inherited Permissions: Two Conditions Must Both Hold

A child ACL can point to a parent ACL, yet **having a parent is not enough to inherit ACEs**. Per `AclImpl`, both are required:

1. `getParentAcl() != null`.
2. `isEntriesInheriting() == true` on the child ACL.

```text
child.getParentAcl() = folderAcl
child.isEntriesInheriting() = false
      |
      +--> Parent is navigation-only; not used for permission decisions
```

When enabled:

```text
child.getParentAcl() = folderAcl
child.isEntriesInheriting() = true
child has no matching ACE
      |
      +--> Strategy may inspect parentAcl, then parent's parent...
```

Under the default strategy model, **having no matching ACE on the child** triggers falling back to the parent. If the child already has a matching **deny** ACE for that exact permission/SID, never assume a parent grant overrides it.

### Required Inheritance Matrix

| Parent | Child has direct READ? | `entriesInheriting` | Expectation |
| --- | --- | --- | --- |
| Grant Alice READ | No | `true` | Alice gets READ via parent |
| Grant Alice READ | No | `false` | Not inherited |
| Grant Alice READ | Deny Alice READ | `true` | Explicit deny |
| Deny Alice READ | No | `true` | Denied via parent |
| No ACE | No | `true` | No grant; may raise `NotFoundException` |
| Grant ROLE_EDITOR READ | No | `true` | Only callers holding matching ROLE_EDITOR SID |
| Grant Alice WRITE | No | `true` | Does not imply Alice READ |
| Grandparent grants READ, parent has no match, child inherits | No | `true` on both edges | Can read via grandparent |

In a multi-level hierarchy, inheritance flags at **every hop** must be tested, not just the leaf.

### Updating Parent and Inheritance

`MutableAcl` supports:

```java
MutableAcl child =
        (MutableAcl) aclService.readAclById(childObjectIdentity);

Acl parent = aclService.readAclById(folderObjectIdentity);

child.setParent(parent);
child.setEntriesInheriting(true);
aclService.updateAcl(child);
```

This is an integration snippet requiring `MutableAclService`, matching identities, and ACL admin rights. `setParent` expects an `Acl` object, not a raw folder ID string. Parent and flag changes must be persisted, then the ACL **reloaded** for testing rather than asserting solely on the in-memory object.

## 6. Deny ACEs: Do Not Confuse "Not Granted" with "Explicit Deny"

A deny ACE looks like:

```text
objectIdentity: demo.Document#44
sid: PrincipalSid("alice")
permission: BasePermission.READ (mask 1)
granting: false
```

It is completely different from **having no ACE**. For a single `READ` permission and Alice's SID, the default strategy returns `false` when it hits the matching deny ACE. If no matching ACE is found, it may check the parent; if still missing, it throws `NotFoundException`.

Cases to separate:

- **Direct explicit deny:** child has a matching `granting=false` ACE.
- **Inherited explicit deny:** parent has a deny ACE, child has no matching ACE, inheritance is enabled.
- **Missing permission:** no matching ACE; not an explicit deny.
- **Grant ACE for another SID:** Alice does not inherit Bob's grant.
- **ACE for another mask:** denying WRITE does not automatically deny READ, unless another policy requires it.

**Never invent a custom rule** like "if any deny ACE exists for the user, block every action." Denies bind to specific permissions/SIDs/resources and are applied by the strategy algorithm.

### Watch Out When Passing Multiple Permissions

Example call:

```java
acl.isGranted(
        List.of(BasePermission.WRITE, BasePermission.READ),
        List.of(new PrincipalSid("alice")),
        true);
```

Under `DefaultPermissionGrantingStrategy`, the permission list represents **ordered alternatives**, not an implicit AND ("must have both WRITE and READ"). If WRITE is denied while READ is granted and the strategy moves on to the next permission, the result **can still be true**.

When business rules require **both**:

```java
boolean canRead = acl.isGranted(
        List.of(BasePermission.READ), sids, true);

boolean canWrite = acl.isGranted(
        List.of(BasePermission.WRITE), sids, true);

boolean canReadAndWrite = canRead && canWrite;
```

This is an illustrative snippet; handle `NotFoundException`/`UnloadedSidException` explicitly and never treat missing rules as grants. At the service API layer, build a reusable fail-closed wrapper.

## 7. Understanding SID, Permission, and ACE Ordering

The `DefaultPermissionGrantingStrategy` Javadoc stresses that **the order of the permissions and SIDs lists is critically important**. The default algorithm iterates permissions in order; within each permission, it iterates SIDs in order; it finds the first ACE matching that permission/SID pair and either acts on `granting` or tries the next permission depending on the decision.

A caller may hold:

```text
PrincipalSid("alice")
GrantedAuthoritySid("ROLE_EDITOR")
```

For example, a READ deny ACE for Alice and a READ grant ACE for `ROLE_EDITOR` on the same object. **Never rely on slogans** like "deny always wins" or "role grant always wins." SID and ACE order can flip the result; therefore tests must use the exact `SidRetrievalStrategy` and ordering produced in production.

Regression matrix:

| ACEs | `sids` argument | What to lock down with tests |
| --- | --- | --- |
| Alice grant READ, role has no ACE | [Alice, ROLE_EDITOR] | READ granted |
| Alice deny READ, role grant READ | [Alice, ROLE_EDITOR] | Outcome matches chosen strategy/precedence |
| Alice deny READ, role grant READ | [ROLE_EDITOR, Alice] | Does the outcome differ? |
| Grant READ, deny WRITE | [Alice] | READ and WRITE evaluated separately |
| Deny WRITE, grant READ | [Alice], permissions [WRITE, READ] | Does another grant let the request pass? |
| Two ACEs for same SID + permission, opposite granting | [Alice] | Which ACE takes effect first? |

With multi-SID/multi-ACE setups, test the **real ACL path**, not just bitwise AND checks on masks. Granting precedence must be documented as an explicit contract before writing tests.

## 8. Permission-Checking API and Exception Handling

Low-level entry point:

```java
boolean granted = acl.isGranted(
        List.of(BasePermission.READ),
        List.of(new PrincipalSid("alice")),
        true);
```

`Acl.isGranted` may:

- Return `true` on a grant decision.
- Return `false` on a deny decision.
- Throw `NotFoundException` when no authoritative decision can be reached due to missing matching ACEs.
- Throw `UnloadedSidException` when the ACL loaded only a SID subset and the caller queried an unloaded SID.

A **fail-closed** helper at the application layer:

```java
boolean allowed(Acl acl, Permission permission, List<Sid> sids) {
    try {
        return acl.isGranted(List.of(permission), sids, true);
    } catch (NotFoundException | UnloadedSidException missingDecision) {
        return false;
    }
}
```

This is an integration snippet (requiring imports for `Acl`, `Permission`, `Sid`, `NotFoundException`, `UnloadedSidException`, and `List`). Never write `catch (Exception) { return true; }`. On DB/network failures, production may return HTTP 503 or an internal error instead of 403, yet **must never default to allowing** access.

**Note:** `AclPermissionEvaluator`, `PermissionEvaluator`, or the web layer may translate missing ACL/deny into a boolean or `AccessDeniedException` depending on the implementation. Unit tests for `Acl.isGranted` and integration tests for `hasPermission` may need to assert **different output types** for the same deny policy. Never conflate the two API layers in test names.

## 9. Java 17 Test Suite with Real `AclImpl`, Without a Database

This section uses **Spring Security's real `AclImpl`** and real `DefaultPermissionGrantingStrategy`, mocking `AclAuthorizationStrategy` only to skip **ACL-management permission checks when building fixtures**. Because the goal is testing read authorization, it does not test who may modify ACLs; test that separately at the integration level.

The JUnit 5 suite runs via Maven on Java 17. It covers direct grants, direct denies, parent inheritance on/off, child deny blocking parent grant, inheriting a different permission, missing ACEs, and multiple permissions.

### 9.1. Directory Structure

```text
acl-test-lab/
├── pom.xml
└── src/test/java/demo/
    └── AclDecisionTest.java
```

No `@SpringBootApplication` class is needed. This is a **direct unit test of the ACL model**, requiring neither H2 nor the four database tables.

### 9.2. The `pom.xml` File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>acl-test-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-acl</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

The Spring Boot BOM manages Spring Security and test dependency versions. When using this in another project, keep `spring-security-acl` aligned with the rest of your Spring Security modules. Never mix ACL 6.x with core 7.x without verifying compatibility.

### 9.3. The `AclDecisionTest.java` File

```java
package demo;

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
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.acls.model.Sid;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

class AclDecisionTest {

    private final Sid alice = new PrincipalSid("alice");
    private final Sid bob = new PrincipalSid("bob");
    private final Sid owner = new PrincipalSid("acl-owner");

    // Only mock ACL fixture EDIT rights; real READ evaluation uses Spring's strategy.
    private final AclAuthorizationStrategy mutationAuthorization =
            mock(AclAuthorizationStrategy.class);

    private final PermissionGrantingStrategy decisionStrategy =
            new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger());

    private AclImpl acl(long id, Acl parent, boolean inherit) {
        return new AclImpl(
                new ObjectIdentityImpl("demo.Document", id),
                id,
                mutationAuthorization,
                decisionStrategy,
                parent,
                null,           // null means do not restrict the set of loaded SIDs
                inherit,
                owner
        );
    }

    private boolean check(Acl acl, Sid sid,
                          org.springframework.security.acls.model.Permission p) {
        return acl.isGranted(List.of(p), List.of(sid), true);
    }

    @Test
    void directGrantIsScopedToOneObject() {
        AclImpl first = acl(50L, null, false);
        AclImpl second = acl(51L, null, false);

        first.insertAce(0, BasePermission.READ, alice, true);

        assertTrue(check(first, alice, BasePermission.READ));

        assertThrows(NotFoundException.class,
                () -> check(second, alice, BasePermission.READ));
    }

    @Test
    void explicitDenyDiffersFromMissingPermission() {
        AclImpl doc = acl(52L, null, false);
        doc.insertAce(0, BasePermission.READ, alice, true);
        doc.insertAce(1, BasePermission.WRITE, alice, false);

        assertTrue(check(doc, alice, BasePermission.READ));
        assertFalse(check(doc, alice, BasePermission.WRITE));

        // Bob has no ACE; this is not an explicit deny for Bob.
        assertThrows(NotFoundException.class,
                () -> check(doc, bob, BasePermission.READ));
    }

    @Test
    void parentGrantIsInheritedWhenEnabled() {
        AclImpl folder = acl(10L, null, false);
        folder.insertAce(0, BasePermission.READ, alice, true);

        AclImpl child = acl(42L, folder, true);

        assertTrue(check(child, alice, BasePermission.READ));
    }

    @Test
    void parentLinkWithoutInheritingDoesNotGrant() {
        AclImpl folder = acl(11L, null, false);
        folder.insertAce(0, BasePermission.READ, alice, true);

        AclImpl child = acl(43L, folder, false);

        assertThrows(NotFoundException.class,
                () -> check(child, alice, BasePermission.READ));
    }

    @Test
    void childDenyPreventsInheritedGrantForSamePermission() {
        AclImpl folder = acl(12L, null, false);
        folder.insertAce(0, BasePermission.READ, alice, true);

        AclImpl child = acl(44L, folder, true);
        child.insertAce(0, BasePermission.READ, alice, false);

        assertFalse(check(child, alice, BasePermission.READ));
    }

    @Test
    void childDenyForWriteDoesNotDenyInheritedRead() {
        AclImpl folder = acl(13L, null, false);
        folder.insertAce(0, BasePermission.READ, alice, true);

        AclImpl child = acl(45L, folder, true);
        child.insertAce(0, BasePermission.WRITE, alice, false);

        assertFalse(check(child, alice, BasePermission.WRITE));
        assertTrue(check(child, alice, BasePermission.READ));
    }

    @Test
    void directDenyInParentCanBeInherited() {
        AclImpl folder = acl(14L, null, false);
        folder.insertAce(0, BasePermission.READ, alice, false);

        AclImpl child = acl(46L, folder, true);

        assertFalse(check(child, alice, BasePermission.READ));
    }

    @Test
    void permissionListIsAlternativesNotAutomaticallyAnd() {
        AclImpl doc = acl(47L, null, false);
        doc.insertAce(0, BasePermission.WRITE, alice, false);
        doc.insertAce(1, BasePermission.READ, alice, true);

        assertTrue(doc.isGranted(
                List.of(BasePermission.WRITE, BasePermission.READ),
                List.of(alice),
                true));
    }
}
```

Fixture breakdown:

- `AclImpl`'s full constructor takes `ObjectIdentity`, ACL ID, `AclAuthorizationStrategy`, `PermissionGrantingStrategy`, parent ACL, loaded SIDs list, inheritance flag, and owner.
- With `loadedSids=null` here, data is not restricted to a SID subset. In JDBC integrations, you may load only a SID subset; in that case test `UnloadedSidException`.
- `mutationAuthorization` is mocked so `insertAce` is not blocked by ACL-admin checks; use that only in unit tests to build fixtures. Never replace the real authorization strategy with a mock in production.
- `check` invokes Spring's real `Acl.isGranted`; no custom bitwise check replaces the framework.
- `administrativeMode=true` only disables auditing for the check, never bypassing permission evaluation.

### 9.4. Running and Verifying Results

In the `acl-test-lab` directory with JDK 17+ and Maven:

```bash
mvn -q clean test
```

Expected result: **8 tests passing, 0 failures, and 0 errors**. Because `-q` is passed, Maven may omit the summary table shown in verbose mode; inspect the Surefire report files in `target/surefire-reports/`.

Verbose run:

```bash
mvn test
```

This test suite was designed against the Spring Security 6.x API and Javadoc-verified behavior; **no claim is made that Maven was executed in this authoring environment**. If outcomes differ after changing versions or strategies, diagnose the root cause instead of weakening assertions to make tests green.

### 9.5. Limitations of This Unit Test

It verifies **in-memory ACL algorithm behavior**, not:

- That the four JDBC ACL tables are created properly.
- That `JdbcMutableAclService` persists and reloads ACEs/inheritance properly.
- That `AclCache` is invalidated after granting/revoking.
- That `AclPermissionEvaluator` translates `hasPermission` expressions properly.
- That `@PreAuthorize` executes through a Spring proxy or returns the right HTTP status.
- That real users' **ACL modification rights** are guarded.

That is why the integration test layers in the next sections are essential.

## 10. Integration Testing with `JdbcMutableAclService` and a Database

Once the application configures a `DataSource`, the four ACL tables, `AclCache`, `BasicLookupStrategy`, and `JdbcMutableAclService`, tests must create resources and ACLs in the database and read them back from the service.

ACL creation fixture:

```java
ObjectIdentity folderOid =
        new ObjectIdentityImpl("demo.Folder", 10L);

ObjectIdentity docOid =
        new ObjectIdentityImpl("demo.Document", 42L);

Sid alice = new PrincipalSid("alice");

MutableAcl folder = aclService.createAcl(folderOid);
folder.insertAce(folder.getEntries().size(),
        BasePermission.READ, alice, true);
aclService.updateAcl(folder);

MutableAcl child = aclService.createAcl(docOid);
child.setParent(aclService.readAclById(folderOid));
child.setEntriesInheriting(true);
aclService.updateAcl(child);

// Read back from persistence layer, not just using the newly mutated instance.
Acl reloaded = aclService.readAclById(docOid);
boolean inherited = reloaded.isGranted(
        List.of(BasePermission.READ),
        List.of(alice),
        true);
```

This is an **integration snippet** with imports and `aclService` provided by app configuration; ACL admin privileges are required to call `insertAce` or `setParent`. DB object IDs and type strings must match `ACL_CLASS` mappings. Tests should manage transactions and fixture teardown to avoid affecting other data.

Steps to perform in integration tests:

1. Build the folder ACL with a direct READ grant.
2. Build the child ACL and parent relationship.
3. Enable `entriesInheriting=true`; save both.
4. Clear/evict the cache as appropriate or reload per contract to avoid asserting on stale object references.
5. Read the child ACL via `AclService.readAclById` and assert the READ grant.
6. Disable `entriesInheriting`; save, reload, and assert the inherited grant is gone.
7. Re-enable inheritance and add a deny READ ACE on the child; save, reload, and assert the explicit deny.
8. Flip deny to grant or delete the ACE; save, reload, and assert the new effective permission.

**Do not forget cleanup:** since `createAcl` inserts `ACL_OBJECT_IDENTITY` rows, concurrent tests using identical IDs can violate uniqueness constraints. Use per-test IDs, schema isolation, or rollbacks per `JdbcMutableAclService` semantics, never modifying production ACLs.

### Separating JDBC Results from Mock Results

`AclImpl` unit tests prove in-memory semantics. JDBC integration tests prove:

- ACEs persisted with exact `MASK` and `GRANTING`.
- `ACL_OBJECT_IDENTITY.PARENT_OBJECT` and `ENTRIES_INHERITING` are accurate.
- `ACL_CLASS` and `ACL_SID` preserve exact types/identities.
- After reloading from the DB, the strategy reaches the same decision.
- Caches reflect new policies after updates/deletions.

If an update transaction rolls back, the ACL must never unexpectedly retain rolled-back changes on reload. Outcomes depend on your application's transaction manager and cache integration, so test against a real database when strong consistency is required.

## 11. Testing `AclPermissionEvaluator` and Method Security

`AclPermissionEvaluator` brings ACL permissions into Method Security SpEL:

```java
@PreAuthorize("hasPermission(#p0, 'demo.Document', 'READ')")
public DocumentView getDocument(long documentId) {
    return repository.loadView(documentId);
}
```

This is an **integration snippet**: `DocumentView` and `repository` belong to the application, and `@EnableMethodSecurity` plus the evaluator-configured handler must exist.

Proper tests must call the **Spring bean through its proxy**:

```java
@SpringBootTest
class DocumentSecurityIntegrationTest {

    @Autowired DocumentService service;

    @Test
    @WithMockUser(username = "alice")
    void inheritedReadIsAllowed() {
        assertDoesNotThrow(() -> service.getDocument(42L));
    }

    @Test
    @WithMockUser(username = "bob")
    void missingOrDeniedAclCannotRead() {
        assertThrows(AccessDeniedException.class,
                () -> service.getDocument(44L));
    }
}
```

This is **integration code requiring app fixtures**: `DocumentService`, evaluator, method-security config, documents, and ACLs matching the test data must exist. Never drop this snippet into section 9's unit-test project expecting it to run, as that project lacks Spring Boot, a DB, and domain services.

### Two Different Error Types to Assert

At the low-level ACL layer, a missing ACE can throw `NotFoundException`. Passing through `AclPermissionEvaluator` and method security, that turns into "no permission," and the interceptor rejects with `AccessDeniedException`. Tests should verify security behavior at the right layer.

With an HTTP controller, 401/403/404 responses also depend on authentication entry points and exception handlers. Never equate ACL `NotFoundException` with HTTP 404: they are two distinct concepts. Avoid leaking the existence of unauthorized resources when designing APIs.

## 12. Comprehensive Matrix for Direct, Inherited, and Deny Permissions

| Case | Caller/SID | Direct ACL | Parent | Inherit | Queried permission | Expected |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Alice | Grant READ | No | — | READ | `true` |
| 2 | Alice | Grant READ | No | — | WRITE | Missing ACE → `NotFoundException` |
| 3 | Bob | Grant READ to Alice | No | — | READ | No grant for Bob |
| 4 | Alice | None | Grant READ Alice | On | READ | `true` |
| 5 | Alice | None | Grant READ Alice | Off | READ | No grant |
| 6 | Alice | Deny READ | Grant READ Alice | On | READ | `false` |
| 7 | Alice | Deny WRITE | Grant READ Alice | On | READ | `true` via parent |
| 8 | Alice | None | Deny READ Alice | On | READ | `false` |
| 9 | Alice | Grant WRITE | Parent grants READ | On | WRITE | `true` directly |
| 10 | Alice | Grant WRITE | Parent grants READ | On | READ | `true` inherited |
| 11 | Alice | None | Grandparent READ, parent has no ACE | On at each hop | READ | `true` |
| 12 | Alice | None | Grandparent READ, parent inheritance Off | On at child | READ | No grant |
| 13 | ROLE_EDITOR | Grant READ to role | No | — | READ | Granted to callers with that role SID |
| 14 | Alice + role | One SID denies, other grants | Yes or no | Any | READ | Depends on SID order; test explicitly |
| 15 | Alice | Deny WRITE, grant READ | No | — | [WRITE, READ] | May be `true` due to permission alternatives |
| 16 | Alice | None | No | — | READ | Low-level `NotFoundException` |
| 17 | Unloaded SID | Partial-SID ACL | Any | Any | READ | `UnloadedSidException` |
| 18 | Tenant B | Grant on tenant A ObjectIdentity | No | — | Tenant B READ | Must never use tenant A's ACL |

The "Expected" column for several cases reflects low-level `DefaultPermissionGrantingStrategy` behavior. With custom strategies, update expectations to match your system's contract and include regression tests.

## 13. Multiple SIDs and Precedence Issues

Systems commonly use `SidRetrievalStrategy` to derive a SID list from `Authentication`:

```text
PrincipalSid("alice")
GrantedAuthoritySid("ROLE_EDITOR")
GrantedAuthoritySid("ROLE_EMPLOYEE")
```

A document may contain:

```text
ACE(ROLE_EDITOR, READ, true)
ACE(alice, READ, false)
```

Never check simply with:

```java
boolean anyGrant = acl.getEntries().stream()
        .anyMatch(ace -> ace.isGranting());
```

This is an **anti-pattern**: it ignores permission, SID, parent, entry order, and deny flags, and overlooks partially loaded SIDs.

Instead:

- Verify the exact SID ordering produced in production.
- Verify the permission list ordering passed to `isGranted`.
- Verify the ACE order stored in the ACL, especially when multiple entries share a SID+permission.
- Avoid overlapping grants and denies without a defined precedence policy.
- Test allow/deny combinations per type and per individual permission; never claim "deny always wins" unconditionally.
- If policy dictates "principal deny always beats role grant," verify your strategy actually enforces it; otherwise customize or normalize entries under a tested contract.

Prefer **avoiding duplicate/conflicting ACEs** unless business rules explicitly demand them. A clear ACL design beats saving a few lines of tests.

## 14. Testing Policy Changes: Grant → Deny and Deny → Grant

Permissions are not static; admins can change them.

Scenario A:

```text
t0: Document 42 has Alice READ grant ACE  -> allowed
t1: Admin revokes/deletes ACE or flips to deny
t2: Alice calls again                      -> denied
```

Scenario B:

```text
t0: Document 44 has Alice READ deny ACE   -> denied
t1: Admin edits/deletes deny ACE and adds grant
t2: Alice calls again                       -> allowed (if policy permits)
```

Test at the **storage + cache layer**:

1. Create and commit the ACL/ACE.
2. Read via the evaluator/service just like production and assert initial outcome.
3. Update the ACE via `MutableAclService` and commit the transaction.
4. End the old transaction and **re-read** the ACL from a fresh service call/path.
5. Assert the post-change outcome.
6. Verify the cache does not retain revoked grants; test across multiple app instances if applicable.
7. If an ACL update rolls back, the decision must remain unchanged after the rolled-back transaction.

`MutableAcl` offers `updateAce(int, Permission)`, `deleteAce(int)`, and `insertAce(...)`. Depending on version, flipping `granting` may require deleting and reinserting the ACE or rebuilding entries; **never assume `updateAce` takes a `granting` boolean**, as its signature updates only `Permission`. Check the real API and keep entry ordering intact.

## 15. Testing Multi-Level ACLs and Mid-Chain Inheritance Breaks

Consider:

```text
Root Project
  ACE Alice READ grant
      |
      v
Folder A, entriesInheriting=true
  (no READ ACE)
      |
      v
Document B, entriesInheriting=true
  (no READ ACE)
```

Alice can read via Root. Yet if **Folder A sets `entriesInheriting=false`**, lookup walks from Document B up to Folder A and stops, so Root's grant no longer propagates down. Tests should build at least three levels and disable the flag at:

- The immediate child.
- The intermediate parent.
- The root parent (if it also has a parent).

If Folder A has an Alice READ deny ACE while Document B inherits with no local ACE, the outcome must be deny under the standard strategy. If Document B has a direct READ grant, test whether the child grant takes effect before the parent deny in that model; under the default strategy for a single permission/SID, a direct matching child grant decides without falling back to the parent.

**Note:** ACL inheritance is a **policy hierarchy**, not Java class inheritance, ORM entity inheritance, or filesystem inheritance automatically. Parent ACLs must be wired explicitly.

## 16. Resource Scope and Multi-Tenancy in Tests

A typical `ObjectIdentity` consists of type + ID, for example:

```java
new ObjectIdentityImpl("demo.Document", 42L);
```

If tenant A and tenant B both have a document with ID 42, they **must never accidentally share an ACL**. Use globally unique IDs or tenant-scoped resource identity mappings. In tests, create two resources with identical local IDs in different tenants and verify:

- Granting READ in tenant A does not grant READ in tenant B.
- A parent ACL in tenant A cannot be attached as parent of a document in tenant B.
- SIDs/authorities are tenant-scoped when business rules require it.
- Cache keys never let tenant A's permissions apply to tenant B.
- Copying or moving documents across parents updates ACLs/inheritance transactionally.

Never trust a tenant from a client-supplied header without authenticated verification. Unit-testing ACL grants/denies does not replace full tenant-isolation testing.

## 17. Testing Concurrency, Caching, and Transactions

Document operations can interleave between two permission checks:

```text
T1: Alice has READ
T2: Admin revokes READ
T3: Alice continues long-running request and reads data
```

An ACL cache can hold the old grant. If your application requires revocations to take effect immediately, define:

- Cache eviction during `updateAcl`.
- Cache synchronization across multiple instances.
- Transaction scope and isolation.
- Maximum window a revoked permission may persist in caches/sessions.
- Re-verification rules before returning ultra-sensitive data or writing.
- Anti-TOCTOU protections such as locks, optimistic versioning, or conditional repository updates.

Tests can use two independent transactions/threads and latches to deterministically order permission checks and updates. Never treat an in-memory `AclImpl` unit test as proof that a distributed system handles revocation properly.

**DB/ACL service failures** must also be tested. Fail-closed does not always mean HTTP 403 for every error; APIs may return 503 per contract, yet must never grant access simply because the authorization backend timed out.

## 18. Choosing the Right Test Layer

| Layer | Tools | What it proves | What it does not prove |
| --- | --- | --- | --- |
| Unit model | `AclImpl` + default strategy + JUnit | Direct/inherited/deny semantics | DB schema, cache, Spring proxy |
| Unit wrapper | Mockito `AclService` + `AclPermissionEvaluator` | Type/ID mapping, SID, permission, missing ACL | Real DB |
| JDBC integration | H2/PostgreSQL + `JdbcMutableAclService` | Persist/reload/parent/entries/granting/cache | HTTP/method pointcut |
| Method security integration | `@SpringBootTest`, `@WithMockUser` | `@PreAuthorize(hasPermission...)` invoked via proxy | Full HTTP response |
| HTTP integration | Runtime-appropriate `MockMvc`/WebTestClient | Authentication, authorization, status, endpoint wiring | Production DB races |
| Concurrency/contract | Production-like DB, multiple transactions | Revocation consistency, races/locking | All distributed network states |

Never lump one test suite together as "unit tests" and claim it validates the entire ACL system. Test both sides: **correct algorithm** and **correct framework/persistence wiring**.

## 19. Easily Missed Mistakes

**1. Testing only direct permissions.** Ignoring inherited permissions and `entriesInheriting`; risks accidentally exposing or locking documents.

**2. Assuming having a parent means inheriting.** False: you must check `entriesInheriting` on the child.

**3. Treating a missing ACE as an explicit deny.** At the low-level API, missing throws `NotFoundException`, whereas explicit deny returns `false`.

**4. Assuming every deny ACE beats every grant.** Wrong without checking permission/SID ordering and strategy; test conflict cases.

**5. Passing only one SID in tests when production has principal + roles.** Misses overlapping grants and denies.

**6. Treating `List.of(READ, WRITE)` as requiring both.** In `Acl.isGranted` this usually acts as alternatives; check separately when business rules need AND.

**7. Inferring permission from mask numbers while ignoring `granting`.** Mask=1 can be either grant READ or deny READ depending on the ACE.

**8. Mocking `PermissionGrantingStrategy` and claiming ACLs are tested.** Mocking the strategy proves nothing about Spring's algorithm. Section 9's unit tests use the real strategy, mocking only fixture-edit checks.

**9. Not persisting/reloading after `setParent` or `insertAce`.** Asserting only on in-memory Java objects proves nothing about JDBC persistence.

**10. Forgetting cache invalidation after `updateAcl`.** Can leave stale grants after revocation.

**11. Extrapolating one object's test to all objects.** Each `ObjectIdentity` has its own ACL and possibly its own tenant.

**12. Using `@WithMockUser` while calling `new Service()`.** Bypasses AOP method security. Inject the Spring bean and invoke through its proxy.

**13. Forgetting `ObjectIdentity` type.** `"demo.Document"` and `"Document"` differ if `ACL_CLASS` stores one form; tests must share the exact convention.

**14. Swallowing `NotFoundException`/DB errors and returning true.** Creates a severe fail-open vulnerability.

**15. Using a deny ACE to "remove" a permission without understanding order.** With multiple ACEs for the same SID/permission or parent ACLs, test real semantics.

**16. Swapping `PermissionGrantingStrategy` without regression tests.** Direct rights, inheritance, conflicts, and composite masks can all change.

**17. Over-mocked Mockito tests.** Mocking `AclService.readAclById` and stubbing `isGranted()` to return true tests only call wiring, not ACL rules.

## 20. Pre-Production ACL Checklist

- [ ] Test direct GRANT, explicit DENY, and missing ACE for each permission.
- [ ] Test both principal SIDs and authority/role SIDs.
- [ ] Test `getParentAcl` with `entriesInheriting=true/false`.
- [ ] Test child deny against parent grant for the same permission/SID.
- [ ] Test that denying permission A does not unintentionally deny permission B.
- [ ] Test multi-level permissions: parent, grandparent, and mid-chain inheritance breaks.
- [ ] Test conflicts across multiple SIDs or multiple ACEs for the same permission.
- [ ] Test permission list ordering, never confusing the list with AND.
- [ ] Test `NotFoundException`/`UnloadedSidException` and fail-closed behavior.
- [ ] Test type+ID and multi-tenancy so one resource's ACL never leaks to another.
- [ ] Test create/grant/deny/revoke/parent changes over JDBC and then **reload**.
- [ ] Test cache updates and effective permissions after commit/rollback.
- [ ] Test `AclPermissionEvaluator` and Spring-managed method proxies.
- [ ] Test ACL administration permissions (who may edit ACEs) without mocking them in integration tests.
- [ ] Test concurrency/revocation races when handling sensitive data.
- [ ] Document the strategy contract, precedence rules, and auditing requirements.

**Conclusion:** A correct ACL system is not merely "having a grant ACE." It must distinguish **direct permissions**, **inheritance only when properly configured**, **deny ACEs**, **missing decisions**, **ordered SIDs and permissions**, and **effective policy after persisting/revoking**. Follow unit tests on real `AclImpl` with JDBC and method-security integration tests to prove behavior all the way to the application's entry points.

## Official References

- [Spring Security — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html)
- [Spring Security 6.5 — AclImpl JavaDoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclImpl.html)
- [Spring Security 6.5 — Acl interface JavaDoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/Acl.html)
- [Spring Security 6.5 — DefaultPermissionGrantingStrategy JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
