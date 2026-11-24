# ACL Owner vs Object Permissions: Two Concepts That Must Stay Separate

## 1. The Scenario: Owner of the Permission List Who Cannot Read the Document

A `Document #42` has three independent pieces of information:

- **Business owner of the document** (`documents.owner_id`): `carol`.
- **Owner of the ACL** (`Acl.getOwner()` or `acl_object_identity.owner_sid`): `alice`.
- **Access permissions on the document** (`AccessControlEntry`, abbreviated ACE): `bob` has `READ`, `erin` has `WRITE`, `dave` has `ADMINISTRATION`.

A common trap: since `alice` is the ACL owner, is she automatically allowed to `READ` the document content? **Never jump to that conclusion.** Under Spring Security ACL's default mechanism, data read/write permissions are evaluated against effective ACEs for the requested SID and permission; the ACL owner property serves a different purpose—specifically controlling **who may administer the ACL** according to the configured strategy.

Similarly, `carol` is the business owner of `Document #42`, yet that fact **does not automatically make `carol` the ACL owner** or automatically create a `READ` ACE. If the business wants document owners to always read their documents, express that as an **explicit permission rule** and ensure consistent updates.

This lesson belongs to the **ACL Foundation** section of Spring Security. The focus is distinguishing **ACL ownership**, **domain object ownership**, and **object permissions**, then keeping them separated across design, code, and tests.

After this lesson, you will be able to:

1. Explain accurately how `Acl.getOwner()` and `AccessControlEntry` solve two different problems.
2. Distinguish `PrincipalSid`, `GrantedAuthoritySid`, `ObjectIdentity`, `Permission`, and `MutableAclService`.
3. Understand the two check paths: **ACL administration** and **data access**.
4. Avoid confusing `BasePermission.ADMINISTRATION` with `READ`/`WRITE`, or confusing ACL owner with business owner.
5. Write and run a Java 17 example proving someone with ACL administration rights cannot necessarily read data.
6. Connect the concepts to Spring Security ACL APIs and `hasPermission(...)`.
7. Prevent privilege escalation, cross-tenant data leaks, misassigned grants, and stale permissions after ownership transfers.

**Context:** Spring Security ACL APIs follow the Spring Security 6.5.x line. The pure Java simulation runs standalone without Spring; Spring ACL integration snippets are marked as **illustrative snippets**, requiring configured ACL beans and database tables before production use.

## 2. Three Kinds of "Owner" and "Permission" That Must Not Be Merged

| Concept | What Does It Describe? | Typical Data Source | Automatically Grants `READ`? |
| --- | --- | --- | --- |
| **Domain owner** | Who owns the record in business terms? | `documents.owner_id`, user/tenant directory | No, unless business policy grants it |
| **ACL owner** | Which SID is recorded as the owner of the access control list? | `Acl.getOwner()`, `acl_object_identity.owner_sid` | No default guarantee that owner has `READ` |
| **Object permission** | Which SID is granted or denied an action on the object? | ACEs in `acl_entry` or another policy | Effective ACEs/policies must be evaluated |

These three concepts may happen to belong to the same person, though not necessarily. A company might assign compliance (`alice`) to administer a document's permission list, while an employee (`carol`) created the document and only an approved reviewer (`bob`) has read permission. That design is **completely valid** if the application enforces policies accurately.

### 2.1. Domain Object Owner

An entity might define:

```java
public record Document(
        Long id,
        String ownerUserId,
        String tenantId,
        String title) {
}
```

`ownerUserId` is a **business** attribute. It can govern billing, costs, reporting, transfer workflows, or edit eligibility, yet **it is not a field on the `Acl` interface**.

If a controller accepts `Document` JSON, `ownerUserId`/`tenantId` fields in the request are **not trustworthy for authorization**. Load the real record by ID from the repository and obtain the caller's identity/tenant from the authenticated security context.

### 2.2. ACL Owner

`Acl.getOwner()` returns a `Sid` object (or `null` if an implementation does not use ownership). SID stands for **Security Identity**: it can represent a principal (`PrincipalSid`) or an authority/role (`GrantedAuthoritySid`).

In the standard ACL implementation, the owner is stored alongside object identity metadata in `acl_object_identity`. With `AclAuthorizationStrategyImpl`, being the ACL owner is **one of the bases** for allowing administrative operations on the ACL structure; administrative access can also be allowed via a system authority or an `ADMINISTRATION` ACE. The exact scope of administrative actions still depends on strategy configuration and application guards.

**Key point:** the `Acl.getOwner()` API explicitly notes that ownership semantics depend on the implementation. Never turn one implementation's interpretation into an assumed automatic rule for every ACL system.

### 2.3. Permissions on the Object: ACEs

Each typical `AccessControlEntry` (ACE) binds:

- A specific `Acl`/`ObjectIdentity`.
- A `Sid` receiving the entry's effect.
- A `Permission` such as `READ` or `WRITE`.
- A `granting` flag: `true` for grant, `false` for deny.
- Audit success/failure flags if used.

Conceptual example:

```text
ObjectIdentity = Document#42
ACL owner      = alice

ACE[0]  bob     READ             GRANT
ACE[1]  erin    WRITE            GRANT
ACE[2]  dave    ADMINISTRATION   GRANT
ACE[3]  guest   READ             DENY
```

Here the ACL owner is not an automatic `READ` ACE. Only `bob` is listed with direct `READ`; `erin` having `WRITE` does not imply `READ`; `dave` having `ADMINISTRATION` does not automatically equal reading document content.

If role-based ACEs, inherited ACLs, or other custom policies exist, final outcomes can change. The table above describes only the entries shown in the example, assuming no hidden permissions.

## 3. ACL Structure in Spring Security

Spring Security includes the `spring-security-acl` module. In the classic JDBC implementation, the core tables are:

| Table | Purpose | Relevant Columns |
| --- | --- | --- |
| `ACL_SID` | List of recipient principals/authorities | `sid`, `principal` |
| `ACL_CLASS` | Domain object types using ACLs | `class` |
| `ACL_OBJECT_IDENTITY` | Each object instance tied to an ACL | `object_id_identity`, `object_id_class`, `owner_sid`, `parent_object`, `entries_inheriting` |
| `ACL_ENTRY` | ACEs attached to objects and SIDs | `acl_object_identity`, `sid`, `mask`, `granting`, `ace_order` |

`owner_sid` and ACEs are not the same column. Reading `owner_sid` and inferring `READ=1` bypasses real authorization design. When creating an ACL, the application must decide who can administer the ACL and which ACEs are granted, rather than expecting the framework to copy the business owner into every permission.

### 3.1. Interfaces and Classes to Know

- `Acl`: provides `getOwner()`, `getEntries()`, `getObjectIdentity()`, `getParentAcl()`, `isEntriesInheriting()`, and `isGranted(...)`.
- `MutableAcl`: allows changing owner, adding/deleting/updating ACEs, and configuring ACL relationships per API; actions are governed by the authorization strategy.
- `AclService`: reads an ACL by `ObjectIdentity`; supports batch reads to avoid N+1.
- `MutableAclService`: creates, updates, and deletes ACLs when authorized.
- `ObjectIdentity`: conceptual pair of object type and ID; commonly `ObjectIdentityImpl`.
- `Sid`: interface identifying a recipient; commonly `PrincipalSid` and `GrantedAuthoritySid`.
- `Permission`: represents permissions as bitmasks; basic constants live in `BasePermission`.
- `AccessControlEntry`: binds SID, permission, and grant/deny state.
- `AclPermissionEvaluator`: uses the ACL service to evaluate `hasPermission(...)` expressions.
- `AclAuthorizationStrategy`: checks **permission to perform ACL administration**, not ordinary data `READ` checks.
- `PermissionGrantingStrategy`: evaluates **object permissions** from the list of permissions and SIDs in an ACL.

Those last two strategies are the easiest to confuse. One checks **who may modify the ACL**; the other checks **who may access the domain object**.

### 3.2. Basic Permissions Are Bitmasks, Not an Owner Boolean

`BasePermission` provides five basic rights:

| Constant | Mask | Meaning |
| --- | ---: | --- |
| `BasePermission.READ` | 1 | Read |
| `BasePermission.WRITE` | 2 | Write |
| `BasePermission.CREATE` | 4 | Create |
| `BasePermission.DELETE` | 8 | Delete |
| `BasePermission.ADMINISTRATION` | 16 | Administer per ACL policy |

A permission is stored as a bitmask. Never infer that `WRITE` includes `READ`, or that `ADMINISTRATION` implies all other permissions. **The bits are distinct rights**; composite mask and grant/deny semantics depend on `PermissionGrantingStrategy`/policy.

Under the default `DefaultPermissionGrantingStrategy`, the order of permissions, SIDs, and ACEs affects the result; if no matching ACE is found, the ACL may check the parent ACL if inheritance is enabled. Thus you cannot decide access by arbitrarily scanning entries with `anyMatch(ACE.granting)`.

## 4. How Does ACL Administration Differ from Reading Data?

### 4.1. When Checking ACL Administration Rights

`AclAuthorizationStrategyImpl` is an implementation of `AclAuthorizationStrategy`. It authorizes an administrative action based on `changeType` when an appropriate basis holds, such as:

1. The caller is the **ACL owner**.
2. The caller holds a **system authority** configured in the constructor.
3. The caller has a **`BasePermission.ADMINISTRATION` ACE** on the ACL, per that strategy.

Details of each change type—such as `CHANGE_GENERAL`, `CHANGE_OWNERSHIP`, `CHANGE_AUDITING`, and configuration—must be verified during implementation. Never assume holding `ROLE_USER` allows administering ACLs.

This governs **changing permission configuration**: adding or removing grants, changing recipients, changing ACL owner, and similar metadata, depending on policy. It does not automatically grant permission to call repositories to fetch confidential document content.

### 4.2. When Checking Domain Object Permissions

For a call like:

```java
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
public Document readDocument(Long id) {
    // Load data after access is granted.
}
```

Spring Method Security evaluates the expression, and `AclPermissionEvaluator` (if registered) looks up the ACL for the object ID and checks permissions against the `Authentication`'s SIDs.

It does not ask **"is the caller the ACL owner?"** as a shortcut to grant `READ`. It asks **"based on the ACL/ACEs/policy, does the caller have `READ` on this object?"**. ACL ownership matters for ACL administration, not as a wildcard for reading data.

### 4.3. Scenario Matrix

Assuming **no inherited ACEs and no other special grants**:

| User | Domain owner? | ACL owner? | ACE on `Document#42` | Read? | Administer ACL? |
| --- | --- | --- | --- | --- | --- |
| `alice` | No | Yes | No `READ` | No | Yes, per example admin policy |
| `bob` | No | No | `READ` | Yes | No |
| `carol` | Yes | No | None | No | No |
| `dave` | No | No | `ADMINISTRATION` | No | Yes, per example admin policy |
| `erin` | No | No | `WRITE` | No | No |

The matrix intentionally separates the three roles. In production, one person might simultaneously be domain owner, ACL owner, and hold several ACEs. What matters is that **every granted right must have an explicit source**, never collapsing three columns into one implicitly.

### 4.4. Consequences of Changing Ownership

**Changing the domain owner** (`Document.ownerUserId` from `carol` to `bob`) does not automatically transfer `acl_object_identity.owner_sid` to `bob`. Nor does Spring Security ACL automatically create a `READ` ACE for `bob`, revoke the previous owner's grants, or recompute group memberships.

**Changing the ACL owner** (`MutableAcl.setOwner`) does not automatically change `documents.owner_id`, nor does it automatically create read/write ACEs on the document. Only an application policy that explicitly synchronizes the two concepts updates them together.

Therefore, ownership transfer workflows must clearly specify: which data changes, which permissions are revoked, which new permissions are granted, who is audited as initiator, consistency guarantees, and commit timing.

## 5. Standalone Java 17 Example: An ACL Owner May Lack READ

The following example **needs no Spring**. Its goal is observing the conceptual separation and verifying stdout with `javac/java`. This is a **minimal simulation**, not a clone of the ACL framework algorithm: it omits role SIDs, ACE inheritance, ACL caching, transactions, and Spring Security auditing.

A single file **`AclOwnershipDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class AclOwnershipDemo {

    enum Permission {
        READ, WRITE, ADMINISTRATION
    }

    record Document(long id, String businessOwner, String title) {
    }

    record Ace(String sid, Permission permission, boolean granting) {
    }

    static final class SimpleAcl {
        private final long objectId;
        private final String aclOwnerSid;
        private final List<Ace> entries = new ArrayList<>();

        SimpleAcl(long objectId, String aclOwnerSid) {
            this.objectId = objectId;
            this.aclOwnerSid = Objects.requireNonNull(aclOwnerSid);
        }

        String aclOwnerSid() {
            return aclOwnerSid;
        }

        void seed(Ace ace) {
            entries.add(Objects.requireNonNull(ace));
        }

        boolean permits(String sid, Permission permission) {
            if (sid == null || permission == null) {
                return false;
            }

            // Illustrative only: single direct ACE match, no parent ACL.
            for (Ace ace : entries) {
                if (ace.sid().equals(sid)
                        && ace.permission() == permission) {
                    return ace.granting();
                }
            }
            return false;
        }

        boolean mayAdminister(String sid) {
            return sid != null
                && (sid.equals(aclOwnerSid)
                    || permits(sid, Permission.ADMINISTRATION));
        }

        void replaceAce(String actor, Ace newAce) {
            if (!mayAdminister(actor)) {
                throw new SecurityException(
                    "User cannot change ACL for object " + objectId);
            }

            entries.removeIf(ace ->
                ace.sid().equals(newAce.sid())
                && ace.permission() == newAce.permission());

            entries.add(newAce);
        }
    }

    public static void main(String[] args) {
        Document document =
            new Document(42L, "carol", "Confidential report");
        SimpleAcl acl = new SimpleAcl(document.id(), "alice");

        acl.seed(new Ace("bob", Permission.READ, true));
        acl.seed(new Ace("erin", Permission.WRITE, true));
        acl.seed(new Ace("dave", Permission.ADMINISTRATION, true));

        System.out.println("DOMAIN_OWNER: " + document.businessOwner());
        System.out.println("ACL_OWNER: " + acl.aclOwnerSid());
        System.out.println("ALICE_READ: "
            + acl.permits("alice", Permission.READ));
        System.out.println("ALICE_MANAGE: "
            + acl.mayAdminister("alice"));
        System.out.println("BOB_READ: "
            + acl.permits("bob", Permission.READ));
        System.out.println("BOB_MANAGE: "
            + acl.mayAdminister("bob"));
        System.out.println("CAROL_READ: "
            + acl.permits("carol", Permission.READ));
        System.out.println("DAVE_MANAGE: "
            + acl.mayAdminister("dave"));
        System.out.println("DAVE_READ: "
            + acl.permits("dave", Permission.READ));
        System.out.println("ERIN_WRITE: "
            + acl.permits("erin", Permission.WRITE));
        System.out.println("ERIN_READ: "
            + acl.permits("erin", Permission.READ));

        // ACL owner alice revokes bob's READ permission.
        acl.replaceAce(
            "alice",
            new Ace("bob", Permission.READ, false));
        System.out.println("BOB_AFTER_DENY: "
            + acl.permits("bob", Permission.READ));

        // dave has ADMINISTRATION ACE so he can edit the ACL in the simulation.
        acl.replaceAce(
            "dave",
            new Ace("carol", Permission.READ, true));
        System.out.println("CAROL_AFTER_GRANT: "
            + acl.permits("carol", Permission.READ));

        try {
            acl.replaceAce(
                "bob",
                new Ace("bob", Permission.READ, true));
            System.out.println("BOB_CHANGE_ACL: UNEXPECTED");
        } catch (SecurityException denied) {
            System.out.println("BOB_CHANGE_ACL: DENIED");
        }

        // Transferring business owner does not automatically change aclOwnerSid.
        Document transferred = new Document(
            document.id(), "bob", document.title());
        System.out.println("TRANSFERRED_DOMAIN_OWNER: "
            + transferred.businessOwner());
        System.out.println("ACL_OWNER_STILL: " + acl.aclOwnerSid());
    }
}
```

### 5.1. Compiling and Running

Requires JDK 17 or newer. In the directory containing the file:

```bash
javac AclOwnershipDemo.java
java AclOwnershipDemo
```

On Windows PowerShell, the same two commands work if `javac`/`java` are on PATH.

**Exact stdout from the source above:**

```text
DOMAIN_OWNER: carol
ACL_OWNER: alice
ALICE_READ: false
ALICE_MANAGE: true
BOB_READ: true
BOB_MANAGE: false
CAROL_READ: false
DAVE_MANAGE: true
DAVE_READ: false
ERIN_WRITE: true
ERIN_READ: false
BOB_AFTER_DENY: false
CAROL_AFTER_GRANT: true
BOB_CHANGE_ACL: DENIED
TRANSFERRED_DOMAIN_OWNER: bob
ACL_OWNER_STILL: alice
```

Key takeaways:

- `alice` is the ACL owner and has admin rights in the simulation, yet has no `READ` ACE.
- `bob` has a `READ` ACE so he can read; reading does not grant ACL admin rights.
- `carol` is the domain owner yet has no `READ` ACE until `dave` grants it.
- `dave` has an `ADMINISTRATION` ACE, allowing ACL edits per simulation policy without implicitly reading the document.
- `erin` has `WRITE` without `READ`; no permission hierarchy is assumed automatically.
- Revoking `bob`'s grant via a `DENY` ACE prevents `bob` from reading.
- Transferring domain owner from `carol` to `bob` leaves `aclOwnerSid` unchanged as `alice`.

**Security limitation of the simulation:** actor names are plain strings passed to methods, not authenticated identities. In real Spring Security, identity comes from a trusted `Authentication`. Never turn a request-body `actor` into admin authority, and never copy `SimpleAcl.permits` to replace `Acl.isGranted`.

## 6. Spring Security ACL API: Reading Owner and Evaluating Permissions Separately

In Spring ACL, `Acl` separates owner and entries:

```java
// ILLUSTRATIVE SNIPPET inside a Spring service with AclService.
ObjectIdentity oid = new ObjectIdentityImpl(Document.class, 42L);
Acl acl = aclService.readAclById(oid);

Sid ownerSid = acl.getOwner();
List<AccessControlEntry> entries = acl.getEntries();
```

Key imports:

```java
import java.util.List;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AccessControlEntry;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
```

`Acl.getOwner()` returns ACL owner metadata; `getEntries()` returns loaded ACEs. Never compare `ownerSid.equals(new PrincipalSid(authentication))` yourself to automatically permit reading data.

### 6.1. Checking `READ` with the Right API

```java
// ILLUSTRATIVE SNIPPET, assuming acl was loaded with all required SIDs.
Sid bobSid = new PrincipalSid("bob");

boolean canBobRead;
try {
    canBobRead = acl.isGranted(
        List.of(BasePermission.READ),
        List.of(bobSid),
        false
    );
} catch (org.springframework.security.acls.model.NotFoundException ex) {
    canBobRead = false;
}
```

This check asks **whether a matching ACE/inherited rule exists for `bob` and `READ`**. It does not treat `acl.getOwner()` as a wildcard.

In real data, a principal may require multiple SIDs—such as `PrincipalSid` plus `GrantedAuthoritySid`s for groups/roles. `Acl.isGranted(...)` can throw `NotFoundException` when no decision can be found and `UnloadedSidException` when SIDs were not loaded properly; handle them appropriately and never convert an undetermined state into `allowed=true`.

`administrativeMode` as the last parameter of `Acl.isGranted(...)` **does not mean "grant `ADMINISTRATION`."** It indicates an administrative check affecting strategy audit behavior; the evaluated permissions still come from the `Permission` list (here `READ`).

### 6.2. Adding an ACE Does Not Mean Changing the ACL Owner

Suppose an administrator **authorized** to update the ACL wants to grant `READ` to `bob`:

```java
// ILLUSTRATIVE SNIPPET in an ACL admin service with MutableAclService.
ObjectIdentity oid = new ObjectIdentityImpl(Document.class, 42L);
MutableAcl acl = (MutableAcl) mutableAclService.readAclById(oid);

Sid bobSid = new PrincipalSid("bob");
acl.insertAce(
    acl.getEntries().size(),
    BasePermission.READ,
    bobSid,
    true
);

mutableAclService.updateAcl(acl);
```

Additional import:

```java
import org.springframework.security.acls.model.MutableAcl;
```

This operates on `bob`'s `READ` ACE, **not** on `Acl.getOwner()`. An ACE with `granting=false` means deny. Creating, modifying, and deleting ACEs must be governed by administrative policy, transactions, auditing, and duplicate/ACE-order handling.

Because Spring Security **does not automatically synchronize ACLs with DAO/entity lifecycles**, the application is responsible for creating or deleting ACLs when objects are created/deleted, updating ACEs when sharing, and handling ownership transfers.

### 6.3. Changing the ACL Owner Is a Separate Operation

```java
// ILLUSTRATIVE SNIPPET; caller must hold appropriate admin permissions.
MutableAcl acl =
    (MutableAcl) mutableAclService.readAclById(
        new ObjectIdentityImpl(Document.class, 42L));

acl.setOwner(new PrincipalSid("alice"));
mutableAclService.updateAcl(acl);
```

`setOwner` updates the ACL's owner metadata; it **does not** create a `READ` or `WRITE` ACE or change `documents.owner_id`. When implementing this, verify the authorization strategy permits owner changes and the business workflow specifies what permissions the new owner receives. Never rely on changing the owner to implicitly grant data read rights.

### 6.4. `AclAuthorizationStrategy` and `PermissionGrantingStrategy`

Both APIs interact with an ACL yet serve distinct purposes:

| Component | Question It Resolves | Example |
| --- | --- | --- |
| `AclAuthorizationStrategy` | Who is allowed to **modify the ACL**? | ACL owner, system authority, or admin ACE per strategy |
| `PermissionGrantingStrategy` | Does this SID have permission on the **domain object**? | `isGranted(READ, SID)` based on ACEs and parent ACL |

A typical configuration:

```java
// CONFIGURATION SNIPPET, requiring appropriate ACL infrastructure beans.
AclAuthorizationStrategy aclAuthorizationStrategy =
    new AclAuthorizationStrategyImpl(
        new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));

PermissionGrantingStrategy permissionGrantingStrategy =
    new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger());
```

Additional imports:

```java
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.model.AclAuthorizationStrategy;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
```

`AclAuthorizationStrategyImpl` supports checking whether the caller is the ACL owner, holds a configured system authority, or has an `ADMINISTRATION` ACE when authorizing admin operations. This configuration **does not automatically grant `READ` to everyone holding `ROLE_ACL_ADMIN`**; reading data requires a separate policy granting and checking read permissions.

Never build an `/acl/change` endpoint that trusts a client-supplied `actorUserId` for admin checks. Administrative layers must pull `Authentication` from Spring Security and validate the exact ACL, tenant, and requested mutation.

## 7. `AclPermissionEvaluator` in Method Security

An expression by object ID:

```java
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
public Document getDocument(@P("id") Long id) {
    return documentRepository.findById(id).orElseThrow();
}
```

Typical imports:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
```

This is an **illustrative method snippet**, assuming your project's real repository and `Document`. `targetType='demo.Document'` must match the `ObjectIdentity` stored in `ACL_CLASS` or the active `ObjectIdentityGenerator` convention. Do not invent arbitrary names expecting JDBC ACL to find the right row.

To route expressions to ACLs, register `AclPermissionEvaluator` on `DefaultMethodSecurityExpressionHandler`:

```java
@Configuration
@EnableMethodSecurity
class AclMethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(AclService service) {
        return new AclPermissionEvaluator(service);
    }
}
```

Key imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

**This is not yet a standalone Spring Boot application.** The configuration also requires a real `AclService`—such as `JdbcMutableAclService`, `LookupStrategy`, `AclCache`, database ACL schema, and corresponding strategies. The ACL module must be declared in dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-acl'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
}
```

This is an **illustrative Gradle dependency snippet** inside a Spring Boot project with plugin versions and Maven repository configured; it excludes the JDBC driver/database. Adding the dependency alone does not generate Method Security, ACL schemas, or ACL rows.

`AclPermissionEvaluator` takes `Authentication` from Method Security and resolves the object's SIDs and permissions. `'READ'` in SpEL must be known to the permission factory to map to `BasePermission.READ` (the default factory registers public constants on `BasePermission`). When using custom permissions or formats, register an appropriate factory and test names/masks.

### When Not Using the ACL Framework

You can also write a custom `PermissionEvaluator` checking permissions against a repository:

```java
@Override
public boolean hasPermission(
        Authentication authentication,
        Object target,
        Object permission) {

    if (!(target instanceof Document doc)) {
        return false;
    }

    return policy.canRead(authentication, doc.id(), permission);
}
```

This is a snippet inside a class implementing `PermissionEvaluator` (`policy` types/beans must be supplied). If `Document` comes from a client, trust only the ID to load the server-side record; never trust an owner field from a DTO. Both the ACL framework approach and custom evaluators must keep **data read permissions** separate from **ACL edit permissions**.

## 8. What Does the `ADMINISTRATION` ACE Grant?

Another misconception is: "If a SID has `BasePermission.ADMINISTRATION`, it definitely gets all of `READ`, `WRITE`, and `DELETE`." That is **not a universal guarantee**.

- `ADMINISTRATION` is an independent permission bit, mask `16`.
- `READ`, `WRITE`, `CREATE`, and `DELETE` have distinct masks.
- `AclAuthorizationStrategyImpl` can use an `ADMINISTRATION` ACE as one basis for **ACL editing rights**.
- `Acl.isGranted(READ, sids, false)` evaluates **READ** per the permission granting strategy. Never test `isGranted(ADMINISTRATION)` yourself and allow arbitrary data operations unless business policy explicitly mandates it.
- An organization may deliberately define "administrators can read everything" via an extra rule; in that case it is an **organizational design choice**, not an automatic consequence of the owner field or ADMINISTRATION mask.

For example, `dave` can be delegated to edit a report's sharing list without needing to read the report's sensitive medical or financial contents. Separating the two permission meanings satisfies **least privilege** and separation of duties.

### Why Avoid Creating "Implicit Rights" via Roles?

If code reads:

```java
// DO NOT USE unless business intentionally grants read access:
boolean canRead = isAclOwner(authentication, acl)
    || hasPermission(authentication, documentId, "READ");
```

then every ACL owner can read the object regardless of ACEs. If policy truly requires that, document the `owner -> READ` rule clearly, add tests, auditing, and tenant checks. Otherwise it is an accidental privilege escalation bug.

Likewise, passing `ROLE_ADMIN` to `AclAuthorizationStrategyImpl` for ACE management **does not mean** the rest of the application must grant `ROLE_ADMIN` view access to all data.

## 9. SID, Authority, and Owner in the Authentication Context

### 9.1. `PrincipalSid` Differs from `GrantedAuthoritySid`

An ACL can grant `READ` to:

```java
Sid userSid = new PrincipalSid("bob");
Sid roleSid = new GrantedAuthoritySid("ROLE_AUDITOR");
```

Imports:

```java
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
```

`PrincipalSid` represents a principal, while `GrantedAuthoritySid` represents an authority/role. If the current `Authentication` holds principal `"bob"` and authority `"ROLE_AUDITOR"`, the corresponding SIDs can be used during ACE evaluation depending on `SidRetrievalStrategy`.

**Common mistake:** comparing `"ROLE_AUDITOR"` and `"bob"` strings as the same kind of identity, or storing a role as the ACL owner and assuming it refers to a single user. `Acl.getOwner()` returns a `Sid`, so preserve both **SID type** and **SID value**.

### 9.2. `Authentication` Is the Caller's Identity Source

Method Security uses the system-authenticated `Authentication`, never a caller ID self-declared in body/query/headers. Principal representations across JWT, OIDC, and username/password can differ; maintain a stable mapping from principal to SID.

In multi-tenant systems, username `"bob"` may collide between organization A and B. Using a global `PrincipalSid("bob")` when user IDs are not globally unique risks misassigning ACEs. Derive SIDs from a **verified stable user ID**, tenant-scoped per your storage model, or a collision-free namespace convention. All reads, ACE writes, owner transfers, and audits must follow the same convention.

### 9.3. Anonymous Is Not a Valid Owner Merely Because `isAuthenticated()`

`AnonymousAuthenticationToken` can return `isAuthenticated() == true` depending on token setup; never rely on that property alone to infer rights. In custom policies, use `AuthenticationTrustResolver` or trusted authentication mechanisms while requiring valid SIDs/permissions. If authentication, SID, or ACL is missing, fail closed.

## 10. ACL Inheritance and ACE Ordering Change Effective Permissions

Spring ACL allows an object's ACL to have a **parent ACL**. If `isEntriesInheriting()` is `true`, parent permissions can be evaluated when the child ACL lacks a conclusive decision, per `PermissionGrantingStrategy`.

```text
Folder#7 ACL
   ownerSid = alice
   ACE: ROLE_READER -> READ GRANT

      |
      | parent ACL (entriesInheriting=true)
      v

Document#42 ACL
   ownerSid = bob
   ACE: carol -> WRITE GRANT
```

If `Document#42` has no matching `READ` ACE and enables inheritance, `ROLE_READER` can read via the folder's ACL even though the document's ACL owner is `bob`. This is why you should never assume "owner is `bob`, so `bob` can read" or "no child ACE means definitely denied" without inspecting parent configuration.

**Ordering and deny ACEs:** the default algorithm traverses permission lists and SID lists in order, and ACE order can affect decisions when multiple entries match. Never replace the entire logic with `entries.stream().anyMatch(AccessControlEntry::isGranting)`. A `DENY` ACE must be understood in terms of permission/SID, combination policy, and SID loading.

**Missing ACEs:** `Acl.isGranted(...)` can throw `NotFoundException` if insufficient data exists to decide, rather than always returning `false`. That is why exceptions must be handled properly at authorization boundaries and never turned into grants when info is missing.

### Does the Parent ACL Owner Automatically Own Child ACLs?

Never assume so. Each ACL has its own owner field; inheriting **ACEs** does not mean inheriting `owner_sid` or `documents.owner_id`. If the application wants folder owners to administer child ACLs, define an explicit administration policy or synchronize ownership explicitly.

## 11. Common Privilege Escalation Scenarios

### 11.1. Self-Granting by Changing Document Owner

A controller receives:

```json
{
  "documentId": 42,
  "ownerUserId": "attacker"
}
```

If the backend trusts the new `ownerUserId` and grants `READ` immediately based on the request's owner field, an attacker can hijack read access. Always check permission to **transfer ownership**, load the authoritative record from the server, verify the actor's identity, and update only via an authorized workflow.

### 11.2. Using ACL Owner to Bypass ACEs

Writing `if (acl.getOwner().equals(currentSid)) return true` inside `canRead` turns ACL owner into an implicit read right. Separate them:

```text
canManageAcl = policyForAclChange(...)
canReadData  = policyForObjectRead(...)
```

Never substitute `canManageAcl` for `canReadData` unless business specifications require it and it is thoroughly tested.

### 11.3. Forgetting to Revoke Old Permissions After Ownership Transfer

Changing `Document.ownerUserId` from `carol` to `bob` while leaving `carol`'s old `READ` ACE intact lets the former owner keep viewing data. That might be intended (co-owner/shared) or a security flaw. Specify exactly which ACEs are kept, revoked, or added, and verify after update.

### 11.4. Checking Permissions Only on Endpoints, Not Services

An ACL admin endpoint is URL-protected, yet the underlying service remains callable from schedulers, message listeners, or elsewhere. Enforce `@PreAuthorize`/`AuthorizationManager` at critical service boundaries with **ACL admin permissions**, not merely read rights. Changing owners, adding ACEs, and deleting ACEs are sensitive actions requiring auditing.

### 11.5. ACL Administration Bypassed via Self-Invocation

In proxy mode, an internal call `this.securedChangeAcl()` within the same bean can bypass method-security advice. Extract the ACL administration service from calling workflows or test through a Spring-managed proxy; never rely blindly on annotations alone.

### 11.6. Failing to Separate Viewing ACL Metadata from Viewing Content

A security admin may need to view the list of principals/ACEs to fix settings without viewing document contents; conversely, a user with `READ` on a document is not necessarily permitted to list everyone else it is shared with. Separate permissions for **view ACL metadata**, **modify ACL**, **read object**, and **write object** per use case.

## 12. Safe Permission Creation and Update Workflows

### 12.1. Creating a Domain Object

A controlled workflow typically performs:

1. Authenticate user/tenant and check object creation permission.
2. Create the domain object in the database; server assigns the ID.
3. Create an ACL for the exact `ObjectIdentity(class, id)` if policy uses Spring ACL.
4. Set `owner_sid` per governance rules, not defaulting blindly to `domainOwner`.
5. Insert necessary ACEs—e.g., `READ` for permitted users, `WRITE` for editors, `ADMINISTRATION` for delegated admins.
6. Commit/sync changes, ensuring no state exists where an object exists without its ACL ready while an endpoint grants access due to a lax fallback.
7. Log audit: actor, timestamp, object identity, before/after permissions, and request source.

Spring Security **does not automatically create ACLs in JPA repositories or DAOs** just because an entity was saved. The application must manage the ACL lifecycle explicitly.

### 12.2. Transferring Domain Owner

Suppose business owner transfers from `carol` to `bob`. Document explicitly:

- Does `Acl.getOwner()` transfer too?
- Should `READ`/`WRITE` ACEs be granted to `bob`?
- Should `carol`'s ACEs be revoked?
- Who is authorized to perform the transfer?
- Does the document's tenant change?
- Must parent ACLs, group grants, and permission caches be updated?
- If domain DB and ACL DB are separate, which transaction/outbox/saga ensures consistency?

There is no single default answer for every app. What is wrong is **merging all three ownership/permission concepts with no explicit policy**.

### 12.3. Separating Service Use Cases

A clean separation of responsibilities might look like:

```text
DocumentQueryService
    readDocument(id)            -- requires READ on object

DocumentEditingService
    updateDocument(id, changes) -- requires WRITE on object

AclAdministrationService
    grantPermission(id, sid, p)  -- requires ACL edit permission
    revokePermission(id, sid,p)  -- requires ACL edit permission
    transferAclOwner(id, sid)    -- requires ACL owner change permission

DocumentOwnershipService
    transferBusinessOwner(...)  -- requires business owner transfer right
```

This diagram is **purely interface design**, not runnable code. An ACL admin service must not automatically grant callers permission to view contents. Conversely, a user with `READ` must never be allowed to call `grantPermission` just because they can read the object.

## 13. Testing ACL Owner and Object Permissions Separately

In a Spring Security system with full ACL data, maintain separate tests for both APIs:

- `canReadDocument(authentication, objectId)`
- `canAdministerAcl(authentication, objectId, changeType)`

### 13.1. Test Matrix

| Scenario | Data `READ` | ACL Admin | Expectation |
| --- | --- | --- | --- |
| ACL owner without READ ACE | Deny | Allow per admin policy | Never implicitly grant read |
| User with READ ACE, not ACL owner | Allow | Deny | Never implicitly grant ACL editing |
| Domain owner without ACE | Deny, unless separate policy | Not auto-granted | Never implicitly sync owners |
| User with ADMINISTRATION ACE, no READ | Not auto-granted | Can allow per strategy | Admin rights differ from data rights |
| User with WRITE ACE, no READ | Not auto-granted | Not auto-granted | Do not assume permission hierarchy |
| User with explicit READ deny | Deny per strategy | Independent | Do not bypass deny via owner check |
| READ ACE revoked | Deny after update | Independent | Invalidation takes effect |
| ACL owner changed, domain owner unchanged | READ unchanged | Owner metadata changes | Do not alter business owner unintentionally |
| Domain owner changed, ACL owner unchanged | READ per ACE/policy | ACL owner unchanged | Do not auto-update ACL |
| Wrong tenant or object ID | Deny | Deny | Never leak cross-tenant data |
| Anonymous / unknown principal | Deny | Deny | Fail closed |

The most important tests are **negative cases**, because over-permissioning bugs are invisible to tests that only confirm admins can act.

### 13.2. Testing Through Spring Proxies

With Method Security, use `@SpringBootTest` and `spring-security-test`'s `@WithMockUser`/`@WithAnonymousUser`. Invoke the Spring-injected service; never instantiate `new Service()` assuming annotations apply. When testing `Acl.isGranted(...)`, construct or seed SID/ACE/ACL inheritance data accurately per scenario.

In ACL owner transfer tests, assert **all three**:

1. `Acl.getOwner()` changes as requested.
2. `Document.ownerUserId` changes only if the workflow specifies.
3. The ACE set and `hasPermission(READ/WRITE)` outcomes change only if rules actually modified them.

In ACE update tests, assert the ACL owner **does not spontaneously change** just because a new grant was added.

### 13.3. Testing Fail-Closed Defaults

Never grant permission when: the ACL does not exist, the object is outside the verified tenant, SIDs are not fully loaded, the permission is unrecognized, ACL lookup fails, or the principal is unauthenticated. Distinguish authorization failures (403), missing resources (404 per anti-enumeration policy), and infrastructure failures (5xx) at the HTTP layer, and never turn infrastructure errors into `allow=true`.

## 14. Performance, Transactions, and Caching: Preserving Boundaries

### 14.1. Per-Object ACL Lookups Can Cause N+1

With `@PostFilter("hasPermission(filterObject, 'READ')")`, the evaluator can read an ACL per element; a list of N records can trigger N ACL lookups. `AclService`/`LookupStrategy` supports batch loading; for large collections, prefer DB-level permission filtering or batch ACL lookups.

Optimizations must never bypass deny ACEs, ACL inheritance, principal SIDs, or authority SIDs. The same object can yield different results for different users; caches must never key an `allowed` boolean solely on object ID.

### 14.2. Caching ACEs and ACL Owner Changes

If ACLs are cached in Redis/Caffeine or `AclCache`, changing `owner_sid`, granting/revoking ACEs, or changing parent ACLs must invalidate caches properly. Furthermore, decisions cached by `(user, object, permission)` can turn stale after revocations or group membership changes.

**Owner cache != permission decision cache.** Reading owner metadata for admin decisions and reusing that result for `READ` is both semantically wrong and a data leak risk.

### 14.3. Races Between Permission Checks and Writes

`@PreAuthorize` may check permission at `t1`, while the database updates at `t2`. If the ACL/tenant/owner changes in between, **TOCTOU** risks arise.

For sensitive mutations, use transactions, optimistic locking, or conditional UPDATE statements bound to verified identity/tenant/permissions, alongside proper commit/invalidation ordering. A request authorized to edit an ACL at check time must not blindly retain that right if the ACL owner changed mid-flight.

## 15. Common Mistakes

| Mistake | Why It Is Dangerous | Correct Approach |
| --- | --- | --- |
| Treating `Acl.getOwner()` as a `READ` ACE | ACL owner accidentally reads confidential data | Check `READ` via dedicated ACE/`PermissionGrantingStrategy` |
| Treating domain owner as ACL owner | Conflates two concepts incorrectly | Maintain business ownership and ACL metadata separately |
| Treating `ADMINISTRATION` as all permissions | ACL admin can read/write/delete outside policy | Grant each right only when business requires |
| Assuming `WRITE` implies `READ` | Write-only actor can view confidential content | Define explicit permission hierarchy via policy if needed |
| Ignoring deny ACEs and SID/ACE order | Grants access despite denial rules | Use `Acl.isGranted(...)` and proper strategy |
| Trusting user/tenant from JSON | Can forge ACEs or leak other tenants | Use server `Authentication` and directories/repositories |
| Changing business owner and forgetting ACEs | Former owner keeps access or new owner lacks it | Include explicit ACL steps in transfer workflows |
| Changing ACL owner assuming domain owner changed | Business data and ACL drift out of sync | Update each ownership type deliberately |
| Using URL security only for ACE changes | Internal services can bypass endpoints | Protect services with Method Security |
| Calling protected method via `this` | Self-invocation bypasses proxy | Extract beans / call through Spring-managed proxy |
| Missing ACL falls back to allow | Fail-open | Deny and handle infrastructure errors safely |
| Caching by object ID without user/tenant | Leaks permissions across principals | Key with full scope and invalidate properly |
| Forgetting ACL parent inheritance | Wrong effective permission conclusions | Account for parent and `isEntriesInheriting()` |
| Testing only one admin user | Fails to catch over-broad permissions | Test ACL owner, ACE reader, domain owner, anonymous, cross-tenant |

## 16. Self-Check Questions

1. **What does `Acl.getOwner()` return?**  
   A `Sid` representing the ACL's owner (may be null depending on implementation), not a `Permission.READ`.

2. **Does the domain owner automatically become the ACL owner?**  
   No. Only if the application explicitly builds and synchronizes that rule.

3. **Can someone with a `READ` ACE on a document edit its ACL?**  
   Not by default. ACL administration has its own strategy and policy.

4. **Can an ACL owner without a `READ` ACE read the object?**  
   Never assume so. Object permissions must be evaluated against real ACEs/policies.

5. **Does `BasePermission.ADMINISTRATION` equal `READ | WRITE | DELETE`?**  
   Not as a default rule. Permission bits are separate.

6. **What does `AclAuthorizationStrategyImpl` check?**  
   Who may perform administrative operations on the ACL, not automatic permission to read object content.

7. **What does `PermissionGrantingStrategy` check?**  
   Specific permissions for one or more SIDs on an ACL, evaluating ACEs and inheritance per implementation.

8. **Why is `setOwner(new PrincipalSid("bob"))` insufficient to let `bob` read?**  
   Because it changes ACL owner metadata without creating a `READ` ACE for `bob`.

9. **Does changing `Document.ownerUserId` automatically delete the old owner's ACEs?**  
   No. The application must decide whether to revoke or keep them and update the ACL accordingly.

10. **What must be checked for inherited ACLs?**  
    Parent ACL, `isEntriesInheriting()`, matching SIDs/permissions, and grant/deny logic.

11. **Why not take `"actor"` from JSON to authorize ACL edits?**  
    Because clients can spoof identity; authorization must rely on verified authentication.

12. **How do you prove there is no "ACL owner = READ" vulnerability?**  
    Test a principal who is the ACL owner without a `READ` ACE and assert `hasPermission(..., READ)` is denied under that policy.

13. **If the same person is both ACL owner and holds a `READ` ACE, what happens?**  
    They have two independent bases: ownership for ACL administration per strategy, and an ACE for reading the object. Never merge them into one unchecked right.

14. **What if an ACL admin needs to view the sharing list without reading the report?**  
    Separate the API/permission for viewing ACL metadata from the API for reading report content; never grant broad read access just for administration.

## 17. Official Documentation

- [Spring Security — Domain Object Security (ACLs), version 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): ACL model, SIDs, owner metadata, ACEs, bitmasks, and method security integration.
- [Spring Security — ACL database schema](https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html): `acl_sid`, `acl_class`, `acl_object_identity`, and `acl_entry` tables.
- [Spring Security — `Acl` API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/model/Acl.html): `getOwner`, `getEntries`, `isGranted`, inheritance, and ownership semantics.
- [Spring Security — `AclAuthorizationStrategyImpl` API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclAuthorizationStrategyImpl.html): owner/authority/administration ACEs in ACL modification policy.
- [Spring Security — `DefaultPermissionGrantingStrategy` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): permission, SID, deny/grant, and parent ACL rules.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, expression handlers, and proxies.
- [Spring Security — `AclPermissionEvaluator` API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/acls/AclPermissionEvaluator.html): evaluating ACL permissions by object or object ID.

**Summary:** In Spring Security ACL, the **ACL owner** is metadata governing **administration of the permission list**; **domain object access permissions** are decided by ACEs/permissions/strategy; and the **business owner** is an application-defined domain attribute. These three concepts may refer to the same person, yet they are **not equivalent**. When building an authorization system, always evaluate `canManageAcl`, `canReadObject`, and `businessOwner` separately, and document explicit transition rules between them whenever business requires.