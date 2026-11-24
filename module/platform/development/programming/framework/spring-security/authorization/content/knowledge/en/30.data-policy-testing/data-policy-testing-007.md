# Testing Direct, Inherited, Cached, and Revoked ACL Permissions

## 1. Objective and Scope

This lesson focuses on **testing object-level authorization decisions** using Spring Security ACL. After this lesson, you will be able to design test suites proving that: directly assigned permissions work; permissions from a parent ACL are inherited only when configuration allows; cached entries never expose revoked permissions; and revocation takes effect for the right user, the right object, at the right time.

An ACL (Access Control List) attaches to **a specific business object**, such as document 2002, rather than just an HTTP path. An ACL contains ACEs (Access Control Entries). Each ACE pairs a **SID** (principal or authority), a **Permission** (READ/WRITE/...), and a **grant/deny** flag. Decisions must evaluate the accessing identity, target object, and requested permission together.

Distinguish four concerns that are often conflated:

- **Direct permission:** an ACE residing directly on the ACL of the object being accessed.
- **Inheritance:** a child object's ACL references a parent ACL and enables the inheriting flag.
- **Caching:** ACLs and ACE lists may be held in memory to reduce queries; the cache must reflect accurate data after changes.
- **Revocation:** deleting/modifying ACEs or blocking direct/inherited permissions; must be verified at the enforcement point, not only on an admin UI screen.

**Scope limits:** This lesson covers testing ACLs in Spring Security and their integration with method security. Authentication mechanisms, filter chain configuration, and URL authorization policies are mentioned only where they affect result verification.

## 2. Core Model to Understand Before Writing Tests

| Component | Responsibility | What to Verify |
| --- | --- | --- |
| **ObjectIdentity** | Identifies an object by type + business ID | Document 2002 never picks up Document 2003's ACL |
| **Sid** | User identity (**PrincipalSid**) or group/authority (**GrantedAuthoritySid**) | Exact username/authority; permissions never leak to another user |
| **Permission** | Bitmask permission, e.g., **BasePermission.READ/WRITE** | Exact permission; READ does not implicitly mean WRITE |
| **AccessControlEntry** | Single grant/deny rule tied to a SID and Permission | Correct ACE matched, correct grant/deny state |
| **Acl / MutableAcl** | Object's ACE set, parent link, inheritance flag | Direct rights, parent rights, inheritance on/off |
| **AclService / MutableAclService** | Reads, creates, updates, deletes persistent ACLs | Post-write state re-read from storage |
| **AclCache** | Caches ACLs by internal ID/ObjectIdentity | Cache hits, eviction, and no stale permissions returned |
| **AclPermissionEvaluator** | Connects ACLs to **hasPermission(...)** expressions | ACL decision genuinely blocks/allows business calls |

With the default JDBC setup, data typically lives in four tables: **ACL_CLASS**, **ACL_SID**, **ACL_OBJECT_IDENTITY**, and **ACL_ENTRY**. The primary key ID in ACL_OBJECT_IDENTITY differs from the business ID: always identify the right object type and ID pair. **The ACL owner does not automatically hold all READ/WRITE permissions**; never infer business access permissions from the owner property.

Inheritance requires two simultaneous conditions: **getParentAcl() != null** and **isEntriesInheriting() == true**. Having a parent link alone does not mean entries are inherited. To test this, re-read the ACL configuration and execute an access decision on the child object.

### How Permission Evaluation Works

With Spring Security ACL's **DefaultPermissionGrantingStrategy**, the order of the **Permission list** and the **Sid list** affects evaluation. The strategy looks for a matching ACE by permission and SID on the current ACL. A matching granting ACE can allow access; a matching denying ACE yields a concrete denial result. Only when **no matching ACE is found on the child ACL** does the strategy check the parent ACL if inheritance is enabled. If the entire parent chain still yields no matching ACE, **Acl.isGranted(...)** may throw **NotFoundException**; this differs from a **false** returned by a denying ACE. When an ACL loads only a subset of SIDs, **UnloadedSidException** can also occur. Neither missing permission rules nor missing SID data may ever default to allow.

Do not apply an oversimplified "deny always beats every grant" rule across all cases: permission/SID ordering, ACE position, granting strategy, and loaded SIDs determine the outcome. When multiple conflicting ACEs exist, fix input order and test the exact running configuration.

## 3. Controlled Test Dataset

Assume a parent folder **Folder:100**, a child document **Document:2002**, an independent document **Document:2003**, users **alice**, **bob**, and **eve**, and group **ROLE_REVIEWER**.

Initial state:

1. Folder:100 has ACE **bob → READ → grant**.
2. Document:2002 has parent Folder:100, **entriesInheriting=true**, and no dedicated READ ACE for bob.
3. Document:2003 is unrelated to Folder:100 and has no READ ACE for bob.
4. A direct ACE **alice → WRITE → grant** is assigned on Document:2002.
5. If testing authorities, assign bob to ROLE_REVIEWER and test a separate authority ACE; always keep principal names and authority names distinct in fixtures.

Assumption when testing "no ACE exists": the calling application layer fails **closed**; depending on the API and resource-hiding policy, HTTP may return 403 or 404. Never assume **Acl.isGranted(...)** returns false in every missing-ACE case.

| Test ID | Object | SID | Permission | Variant | Expected |
| --- | --- | --- | --- | --- | --- |
| D1 | Document:2002 | alice | WRITE | Direct granting ACE | Allow |
| D2 | Document:2002 | alice | READ | No matching ACE | Not allowed; NotFound handled safely |
| D3 | Document:2003 | alice | WRITE | Different ObjectIdentity | Not allowed |
| I1 | Document:2002 | bob | READ | Has parent, inheritance=true | Allow via parent ACL |
| I2 | Document:2002 | bob | READ | inheritance=false | Not allowed |
| I3 | Document:2002 | bob | READ | Child has direct deny READ ACE | Denied at child, ignores parent grant |
| I4 | Document:2002 | bob | READ | Remove deny on child; parent still grants | Allow via restored inheritance |
| I5 | Document:2002 | eve | READ | Same object, different SID | Not allowed |
| R1 | Document:2002 | bob | READ | Delete bob's READ grant on parent; child has no own ACE | Not allowed after commit + fresh read |
| R2 | Document:2002 | bob | READ | Child has direct READ grant; revoke only parent | Still allowed on child: direct grant must also be revoked |
| C1 | Document:2002 | bob | READ | Cache warmed then parent revoked | Post-revocation result is no longer allow |
| C2 | Document:2002 | bob | READ | 2 application instances | Other instance must not serve stale cache either |

For each row, record **setup → action → checkpoint → expected**. Isolate fixtures between tests so there is no order dependency; a single test may deliberately mutate state to prove before and after.

## 4. Testing Direct Permissions

Start with a fresh ACL for Document:2002, with no parent or with inheritance disabled. Insert a READ grant ACE for alice and call **isGranted([READ], [PrincipalSid("alice")], true)**: it must allow. Switch to WRITE without a WRITE ACE: there must be no permission, never inferred from READ. Switch SID to eve and ObjectIdentity to Document:2003: neither may receive alice's permission on 2002.

Next, create a deny ACE for **another permission** (e.g., WRITE) or a separate test for the same SID/Permission pair. Verify **false** when a deny actually matches, whereas having no matching ACE produces **NotFoundException** at the ACL layer. The exact behavior of **hasPermission(...)** expressions needs additional testing because it wraps ACL-layer outcomes/exceptions.

Key assertions: test **both positive and negative cases**, ensure permissions never spill to other SIDs or objects, never conflate READ/WRITE, and ensure each test knows exactly which ACE drives the decision.

## 5. Testing Inheritance from a Parent ACL

Create a parent ACL with ACE bob:READ=grant. Create a child ACL with **setParent(parent)** and **setEntriesInheriting(true)**; the child has no READ ACE for bob. Querying READ on the child should allow via the parent. Then sequentially:

1. Call **setEntriesInheriting(false)** and re-evaluate: the child no longer receives READ from the parent.
2. Re-enable inheritance; insert ACE **bob:READ=deny** directly on the child: expected deny, despite the parent grant.
3. Delete the deny ACE on the child while the parent still grants: expected allow again.
4. Revoke the grant from the parent; the child still inherits, yet there is no permission to inherit: expected not allowed.
5. Add a direct READ grant on the child and revoke the parent again: the child still allows via its own permission; this is a critical check when users report "I revoked it, yet they still have access."

Do not miss multi-level parent chains (Organization Folder → Team Folder → Document) and test disabling inheritance on an intermediate level. Prevent parent cycles and restrict ACL tree updates to authorized administrative users/roles.

## 6. Sample Unit Test Running on Spring Security ACL

The example below tests **in-memory ACL evaluation logic**, without a database, HTTP, or distributed cache. Place the file at **src/test/java/example/AclDecisionTest.java** in a Java 17+ project with **spring-security-acl** and **spring-boot-starter-test** dependencies (managed by the project BOM). The **(acl, changeType) -> {}** lambda intentionally skips *ACL modification* authorization checks in the unit fixture; real applications must configure an appropriate AclAuthorizationStrategy and test administrative permissions separately.

~~~java
package example;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;

import static org.junit.jupiter.api.Assertions.*;

class AclDecisionTest {
    private static AclImpl acl(String type, long id) {
        return new AclImpl(
                new ObjectIdentityImpl(type, id),
                id,
                (ignoredAcl, ignoredChangeType) -> { },
                new ConsoleAuditLogger());
    }

    private static boolean granted(AclImpl acl, Sid sid, Permission permission) {
        return acl.isGranted(List.of(permission), List.of(sid), true);
    }

    @Test
    void directGrantDenyAndIsolation() {
        Sid alice = new PrincipalSid("alice");
        Sid eve = new PrincipalSid("eve");
        AclImpl doc = acl("example.Document", 2002);

        doc.insertAce(0, BasePermission.READ, alice, true);
        assertTrue(granted(doc, alice, BasePermission.READ));
        assertThrows(NotFoundException.class,
                () -> granted(doc, alice, BasePermission.WRITE));
        assertThrows(NotFoundException.class,
                () -> granted(doc, eve, BasePermission.READ));

        doc.insertAce(1, BasePermission.WRITE, alice, false);
        assertFalse(granted(doc, alice, BasePermission.WRITE));
        assertThrows(NotFoundException.class,
                () -> granted(acl("example.Document", 2003),
                              alice, BasePermission.READ));
    }

    @Test
    void inheritanceLocalDenyAndSwitch() {
        Sid bob = new PrincipalSid("bob");
        AclImpl parent = acl("example.Folder", 100);
        AclImpl child = acl("example.Document", 2002);

        parent.insertAce(0, BasePermission.READ, bob, true);
        child.setParent(parent);
        child.setEntriesInheriting(true);
        assertTrue(granted(child, bob, BasePermission.READ));

        child.setEntriesInheriting(false);
        assertThrows(NotFoundException.class,
                () -> granted(child, bob, BasePermission.READ));

        child.setEntriesInheriting(true);
        child.insertAce(0, BasePermission.READ, bob, false);
        assertFalse(granted(child, bob, BasePermission.READ));

        child.deleteAce(0);
        assertTrue(granted(child, bob, BasePermission.READ));
    }

    @Test
    void revokeInheritedGrantAndKeepDirectGrant() {
        Sid bob = new PrincipalSid("bob");
        AclImpl parent = acl("example.Folder", 100);
        AclImpl child = acl("example.Document", 2002);
        parent.insertAce(0, BasePermission.READ, bob, true);
        child.setParent(parent);
        child.setEntriesInheriting(true);

        assertTrue(granted(child, bob, BasePermission.READ));
        parent.deleteAce(0);
        assertThrows(NotFoundException.class,
                () -> granted(child, bob, BasePermission.READ));

        child.insertAce(0, BasePermission.READ, bob, true);
        assertTrue(granted(child, bob, BasePermission.READ));
    }

    @Test
    void cacheEntryCanBeFoundAndEvicted() {
        AclCache cache = new SpringCacheBasedAclCache(
                new ConcurrentMapCache("acl-tests"),
                new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger()),
                (ignoredAcl, ignoredChangeType) -> { });
        AclImpl doc = acl("example.Document", 2002);

        cache.putInCache(doc);
        assertNotNull(cache.getFromCache(doc.getObjectIdentity()));
        cache.evictFromCache(doc.getObjectIdentity());
        assertNull(cache.getFromCache(doc.getObjectIdentity()));
    }
}
~~~

These are **in-memory** tests: the revocation case verifies that modifying ACEs changes decisions on an ACL instance, while the cache case only exercises the **put/get/evict** API. **They do not prove** that the JDBC service committed, properly invalidated child ACLs, or that other nodes stopped holding stale values. Those assertions belong in the integration tests below.

With Gradle in a project declaring the dependencies above, run from the project directory:

~~~bash
./gradlew test --tests "example.AclDecisionTest"
~~~

On Windows, use **gradlew.bat** instead of **./gradlew**. No fixed stdout line is guaranteed because output depends on Gradle/JUnit and log levels; the pass condition is all four tests passing. If application code uses a custom granting strategy, adjust expectations to match the configured implementation.

## 7. Integration Tests: Persistence, Method Security, and Database

Pure ACL unit tests are necessary, but insufficient for system correctness. For real applications, run integration tests with **JdbcMutableAclService**, **BasicLookupStrategy**, **AclCache**, a real **DataSource** (or H2/Testcontainers with the matching ACL schema), configured **AclPermissionEvaluator**, and method security. With annotation-based Spring Security, a typical setup uses **@EnableMethodSecurity** paired with **DefaultMethodSecurityExpressionHandler.setPermissionEvaluator(new AclPermissionEvaluator(aclService))**. This wires ACL decisions into **hasPermission(...)**; test through the protected method itself rather than calling test helpers directly.

Illustrative business expression (must match method names, object types, and project configuration):

~~~java
@PreAuthorize("hasPermission(#documentId, 'example.Document', 'READ')")
public Document readDocument(long documentId) {
    return repository.findById(documentId).orElseThrow();
}
~~~

Mandatory end-to-end test steps:

1. In a setup transaction, create an ACL for Folder:100, add bob's READ grant ACE, and call **updateAcl(parent)**; create an ACL for Document:2002, set its parent and inheriting flag, and call **updateAcl(child)**. Commit the fixture before testing access in a new transaction. **createAcl(...)** only creates an empty ACL; modifying ACEs in memory does not persist them to the database.
2. Under bob's Authentication, invoke the protected service/method for Document:2002 and assert success. Under eve or for Document:2003, assert denial. When testing APIs, use MockMvc/WebTestClient matching your web stack and assert HTTP status per API policy.
3. Re-read the parent via **aclService.readAclById(parentOid)**, locate the exact ACE index by SID + Permission + granting flag, call **deleteAce(index)**, then call **mutableAclService.updateAcl(parent)**. Commit. Avoid hardcoding ACE indexes when multiple ACEs exist.
4. Using a **fresh Authentication** and a fresh transaction/EntityManager, call the same method on Document:2002 again. Expect denial. Re-read the child ACL through the service after the update to catch stale cached entries. Never reuse the **AclImpl** variable mutated during setup as proof.
5. Repeat tests with a direct grant on the child, with inheritance=false, and with multi-level parents. Step 3 only revokes the parent grant; if the child has an independent grant, access is still expected.

Revocation snippet via the service (**non-standalone** excerpt illustrating part of a test/service method; **mutableAclService**, **parentOid**, and **bob** must come from the fixture):

~~~java
MutableAcl fresh = (MutableAcl) mutableAclService.readAclById(parentOid);
int aceIndex = -1;
for (int i = 0; i < fresh.getEntries().size(); i++) {
    AccessControlEntry ace = fresh.getEntries().get(i);
    if (ace.getSid().equals(bob)
            && ace.getPermission().getMask() == BasePermission.READ.getMask()
            && ace.isGranting()) {
        aceIndex = i;
        break;
    }
}
if (aceIndex < 0) {
    throw new IllegalStateException("Expected parent READ grant is missing");
}
fresh.deleteAce(aceIndex);
mutableAclService.updateAcl(fresh);
~~~

Never check ACE rows in a table and assume permission was revoked: verify the **final access decision**, because permission could still come from another ACE or from the child ACL. Also define transaction boundaries explicitly in tests so uncommitted data is never read.

## 8. Testing Caching: Warm → Mutate → Fresh Read

**SpringCacheBasedAclCache** is an adapter for Spring Cache. The cache may store ACLs keyed by ObjectIdentity or internal ID. With the default JDBC service, **JdbcMutableAclService.updateAcl(...)** includes logic to evict the modified ACL and related child ACLs from cache; still verify this with integration tests on your project's version and setup. With a custom MutableAclService, lookup strategy, distributed cache, or multi-layer application caches, never assume identical behavior without testing.

Test design:

- **Cold read:** clear the fixture's cache, call READ → expect allow; confirm the ACL is loaded.
- **Warm read:** invoke again with the same SID/ObjectIdentity/Permission → expect allow; if measuring query/cache hits, use controlled spies/metrics rather than brittle execution timings.
- **Mutation:** revoke the parent ACE via **MutableAclService.updateAcl(...)** and commit the transaction.
- **Post-mutation:** re-read the child ACL via **AclService**, invoke hasPermission/protected method in a fresh request → expect denial. This is what detects **stale authorization** bugs.
- **Child invalidation:** when modifying a parent ACL, also test at least one child object cached beforehand. If a custom policy requires automatic descendant eviction, tests must prove that path runs.
- **Cross-node:** in environments with two or more instances, warm the cache on node B, revoke on node A, and call B again. Define whether immediate consistency or an approved propagation window is expected; for sensitive revocations, design to minimize or eliminate stale allow windows.

Minimal matrix:

| Time | Parent ACL in DB | Child Cache | Test Expectation |
| --- | --- | --- | --- |
| T0 | bob READ grant | Not loaded | bob can READ |
| T1 | bob READ grant | Loaded | bob can READ |
| T2 | grant deleted and committed | Risk of staleness | System must invalidate/ensure fresh result |
| T3 | no matching grant remains | Fresh read | bob is denied |
| T4 | grant re-added cleanly | cache refreshed | bob can READ again, not stuck on stale deny |

**Never use Thread.sleep hoping a cache expires on its own** as sole proof. Trigger the real invalidation mechanism, use a fake clock if TTL applies, observe events, and verify access decisions. For distributed Spring Caches, confirm evictions propagate everywhere and test failure paths when events are dropped or retried.

## 9. Permission Revocation: Three Common Forms

| Change Type | Example | Behavior to Understand and Test |
| --- | --- | --- |
| **Delete granting ACE** | Remove bob READ from parent | If child has no other grant: READ is gone; may trigger NotFound |
| **Add direct deny ACE** | Child denies bob READ while parent grants | Child returns deny from its ACE; does not fall back to parent grant for that decision |
| **Disable inheritance** | Child entriesInheriting=false | Drops all grants coming solely from parent; direct grants on child remain |

Revoking access **does not mean deleting the document** and does not mean **deleteAcl(...)**. **deleteAcl(objectIdentity, deleteChildren)** deletes ACL structures and can affect children; use it only with explicit intent. For a single permission, typically modify the ACE/parent/inheritance at the right level and call **updateAcl(...)**.

Test both directions: **grant → revoke → deny** and **deny → re-grant → allow**. Test post-revocation using the old principal on existing sessions/tokens as well as new sessions if product requirements demand it; object-level ACL permissions can change independently of tokens, yet decision caches or token claims can cause staleness. Record who modified what, which object, which permission, commit time, and post-commit verification results.

## 10. Completeness and Safety Testing

**Identity and isolation:** use at least two principals, two objects of the same class, and two permissions. Prove zero cross-tenant permission leaks, even when objectIds collide across tenants (if multi-tenant, tenant must be part of ACL lookup/authorization). Cover both PrincipalSid and GrantedAuthoritySid. Test explicit SID ordering when a user holds multiple authorities.

**Errors and edge cases:** missing ACL, null parent, inheritance off, deny ACE, unloaded SID, lacking permission to edit ACLs, multi-level parents, deleting a non-existent ACE, two concurrent updates, transaction rollbacks, and DB/cache failures. The safe expectation is **never granting permission based on unverified state**; distinguish infrastructure errors from legitimate denials for accurate logging and monitoring.

**ACL administration permissions:** regular users must not invoke unauthorized create/update/delete ACL operations. Test modifying ownership, parent, ACEs, and auditing under an insufficiently privileged Authentication; note that the unit fixture in Section 6 disabled modification authorization strategy, so integration tests with the real strategy are mandatory.

**Enforcement points:** test the method security or API where permissions are enforced. If list/search endpoints return multiple records, verify returned items are also permission-filtered so objects do not leak through another endpoint; never test only single-ID read endpoints.

**Concurrency:** concurrent revocations and requests require a consistent rule. Pin down the effective boundary (e.g., post-commit) and assess race/TOCTOU risks. If decisions require stronger guarantees than eventual consistency, design and test caching/transactions accordingly.

**Observability:** log business ID, SID, permission, outcome, direct/inherited ACE source, and cache traces (hit/miss/invalidate) safely; avoid logging tokens or sensitive data. Use correlation IDs when tracing revocation across multiple nodes.

## 11. QA Checklist per Test Case

| Question | Must Be Able to Answer |
| --- | --- |
| Which permission is tested? | READ, WRITE... and exact bitmask |
| Who is accessing? | PrincipalSid/GrantedAuthoritySid and actual SID list |
| Which object? | Object type, ID, and tenant if applicable |
| Where does permission come from? | Direct ACE, parent ACL, or multi-level hierarchy |
| What are the inheritance flag and parent? | Both conditions verified accurately |
| Is another ACE still granting permission? | Do not confuse revoking one ACE with revoking all grant paths |
| Is the DB state committed? | Verified via fresh read in a new transaction |
| Which cache is active? | ACL cache, custom cache, other nodes |
| What is the final checkpoint? | Acl.isGranted, hasPermission, or business request |
| What is the negative outcome? | Explicit deny, NotFound/UnloadedSid, or infrastructure error |
| What changes after revocation? | Before: allow; after: deny; re-grant: allow |
| Is the test independent? | Isolated fixture and cleanup, zero order dependency |

Given–When–Then template for a key regression test:

> **Given:** bob has READ from the parent ACL, and the child ACL is already loaded in cache.  
> **When:** an administrator revokes bob's READ ACE on the parent and the transaction commits.  
> **Then:** bob's next access to the child document is blocked, even via an instance with a previously warmed cache.  
> **And:** alice retains direct WRITE permission on the document, and unrelated documents are unaffected.

## 12. Common Mistakes and How to Fix Them

1. **Test only calls getEntries() and asserts permissions:** the child's ACE list excludes inherited ACEs. Use **isGranted(...)** or the real enforcement point to verify decisions.
2. **Confusing no-match with explicit deny:** **NotFoundException** is not the same state as **false**. Verify how your evaluator or application translates it to denial; never permit when data is missing.
3. **Mutating the in-memory ACL without updateAcl:** unit tests may pass while DB and cache remain stale. Integration tests must invoke the write service, commit, and re-read.
4. **Revoking parent grant while forgetting direct child grant:** access remaining valid is correct ACL behavior; inspect the entire grant path before blaming the cache.
5. **Evicting only the parent cache:** child caches may retain inherited effects; verify descendant invalidation and caches on other nodes.
6. **Testing cache via time delays:** produces flaky results and fails to prove event invalidation; use deterministic actions, spies/metrics, and post-mutation access assertions.
7. **Using one user and one document:** misses SID/ObjectIdentity mix-ups or tenant leaks. Every suite needs negative controls.
8. **Reusing SecurityContext/transactions across phases:** outcomes may reflect stale state; separate requests/transactions and recreate Authentication as needed.
9. **Guessing ACE/SID order or deny semantics:** verify **DefaultPermissionGrantingStrategy** for your exact version and inputs; avoid ambiguous overlapping grant/deny ACEs on the same pair.
10. **Testing cache in a single JVM only:** a shared DB does not guarantee another instance's cache sees changes automatically. Use multi-instance tests and proper event propagation.

## 13. Hands-On Exercises and Completion Criteria

**Exercise A – Direct ACL:** create two documents and two users; add a READ grant for alice on the first document and a WRITE deny for bob. Write assertions for allow, deny, no-match, and object isolation.

**Exercise B – Inherited ACL:** add a parent folder granting READ to bob and a child document with inheritance=true. Write tests for inheritance on/off, child deny, removing deny, and falling back to parent; add a grandparent level.

**Exercise C – Cached revocation:** load child permission into cache, revoke the READ ACE on the parent via **MutableAclService**, commit, re-check via **hasPermission(...)**, and measure cache hit/miss/eviction. Repeat across two instances and when the child has its own direct grant.

An implementation meets acceptance criteria when **every permission change has before–after checks at the real authorization layer**, zero stale allows remain after the committed effective point, direct/inherited/cached/revoked scenarios are fully covered, and unrelated SIDs or objects remain unaffected.

## References

- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html)
- [API – DefaultPermissionGrantingStrategy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html)
- [API – MutableAclService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAclService.html)
- [API – JdbcMutableAclService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html)
- [API – SpringCacheBasedAclCache](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/SpringCacheBasedAclCache.html)
