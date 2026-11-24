# PrincipalSid, GrantedAuthoritySid, and Permission Scope

> **Topic:** Spring Security – authorization → **ACL Foundation**. This lesson distinguishes the two Security Identity (SID) forms in Spring Security ACL, clarifies **who receives a permission** and **which object that permission applies to**, how `Authentication` is converted into a set of SIDs, and critical boundaries around ACEs, ACL inheritance, multi-tenancy, and permission lifecycle. The main example uses Java 17+ and the `spring-security-acl` module; JDBC/Method Security integration snippets are clearly distinguished from the standalone program.

## 1. Why Do We Need SIDs When We Already Have Usernames and Roles?

Suppose a document management application has three users:

- **alice**: has `ROLE_REVIEWER`.
- **bob**: also has `ROLE_REVIEWER`.
- **carol**: only has `ROLE_VIEWER`.

The system needs to express two policies simultaneously:

1. Only **alice** is allowed to read `Document#101`.
2. Anyone **currently holding** the `ROLE_REVIEWER` authority is allowed to read `Document#202`.

An ACL entry can specify the recipient either by **user identity** or by **authority identity**. Spring Security ACL uses the `Sid` (Security Identity) interface to represent both forms:

~~~text
Document#101
  └── READ → PrincipalSid("alice")

Document#202
  └── READ → GrantedAuthoritySid("ROLE_REVIEWER")
                         │
             +-----------+-----------+
             │                       │
      Authentication alice    Authentication bob
       ROLE_REVIEWER           ROLE_REVIEWER
~~~

In this example, bob shares the same role as alice yet is **not** granted permission on `Document#101` just for having the same role; meanwhile, both alice and bob fall within the recipient scope of the ACE attached to `Document#202`. Carol does not belong to the `ROLE_REVIEWER` recipient.

**A SID is not a session ID**, nor is it a permission. A SID answers "**who** receives an ACE?", `Permission` answers "**what can be done**?", and `ObjectIdentity` answers "**on which specific object**?".

## 2. An ACL Decision Has Four Dimensions

Read an ACL as a set of grant/deny rules:

~~~text
         ObjectIdentity
              |
              v
            ACL
              |
      +-------+-------+
      |               |
  ACE #0            ACE #1
      |               |
      +-- Sid          +-- Sid
      +-- Permission   +-- Permission
      +-- Grant/Deny   +-- Grant/Deny
~~~

Illustrative example:

| ObjectIdentity | Recipient SID | Permission | Granting? | Meaning |
| --- | --- | --- | --- | --- |
| `Document#101` | `PrincipalSid("alice")` | `READ` | `true` | Grants read permission specifically on document 101 to alice |
| `Document#202` | `GrantedAuthoritySid("ROLE_REVIEWER")` | `READ` | `true` | Grants read permission on document 202 to holders of authority ROLE_REVIEWER |
| `Document#202` | `PrincipalSid("bob")` | `WRITE` | `false` | A rule **denying WRITE**, not equivalent to denying READ |
| `Document#303` | `GrantedAuthoritySid("ROLE_EDITOR")` | `WRITE` | `true` | Only holders of authority ROLE_EDITOR are recipients of the write ACE for document 303 |

This is **illustrative rule data**, not output computed from an existing SQL table. When overlapping ACEs exist across multiple SIDs or multiple permissions, never compute `(at least one grant) -> allow` yourself while ignoring deny entries, evaluation order, and inheritance. Spring ACL uses `Acl.isGranted(...)` together with `PermissionGrantingStrategy` to make the real decision.

### Core Concepts

| Type / Interface | Role |
| --- | --- |
| `Sid` | Abstraction for a permission recipient identity |
| `PrincipalSid` | SID of **a principal**, typically from `Authentication.getName()` |
| `GrantedAuthoritySid` | SID of **an authority** in `Authentication.getAuthorities()` |
| `Permission` / `BasePermission` | READ, WRITE, CREATE, DELETE, ADMINISTRATION rights; represented as bitmasks |
| `ObjectIdentity` / `ObjectIdentityImpl` | Key consisting of **object type and ID** |
| `AccessControlEntry` (ACE) | A rule containing ACL, SID, permission, grant/deny, and audit flags |
| `Acl` | Set of ACEs attached to **one** ObjectIdentity; may have a parent ACL |
| `AclService` | Reads an object's ACL from storage |
| `MutableAclService` | Creates/updates/deletes ACLs |
| `SidRetrievalStrategy` | Produces the SIDs that the current `Authentication` can represent |
| `PermissionGrantingStrategy` | Strategy evaluating a list of permissions and SIDs against an ACL |

A permission check can evaluate multiple SIDs for the same logged-in user. For example, alice has both `PrincipalSid("alice")` and `GrantedAuthoritySid("ROLE_REVIEWER")`. That **does not** turn a principal SID into an authority SID: they are two distinct recipients with different administrative semantics.

## 3. `PrincipalSid`: Granting Permission to Exactly One Principal

Spring Security defines:

~~~java
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Sid;

// Two ways to construct the same SID for the principal named "alice":
Sid byName = new PrincipalSid("alice");
Sid fromAuthentication = new PrincipalSid(authentication);
~~~

In the snippet above, `authentication` is assumed to be a valid `Authentication` whose `getName()` returns `"alice"`; therefore this is a syntax example, not a standalone compilable file.

Key constructors and methods:

- `new PrincipalSid(String principal)`: creates a SID from an identifier string.
- `new PrincipalSid(Authentication authentication)`: extracts identity from authentication info; the default implementation relies on how Spring represents the principal name.
- `getPrincipal()`: returns the SID's identifier string.
- `equals/hashCode`: compares SID type and string value, not Java object reference identity.

### Scope of `PrincipalSid`

If the ACE is:

~~~text
ObjectIdentity = Document#101
Sid = PrincipalSid("alice")
Permission = READ
Granting = true
~~~

then the recipient is **principal "alice"**, and the ACE belongs strictly to `Document#101`'s ACL. It does not automatically allow alice to read all documents, nor does it allow everyone with `ROLE_REVIEWER` to read document 101.

`PrincipalSid` fits scenarios such as:

- Sharing a specific document with one individual.
- Granting read permission on a record to its assignee.
- Granting management permission on an object to a well-defined service account.
- Revoking personal access when a user leaves a project.

### Crucial Note on Identifiers

`PrincipalSid` defaults to using a **string** to identify the principal. If an account changes its username or email, or if two tenants share the same username, matching SID strings can cause lost access or unintended grants.

Risk example:

~~~text
Tenant A has user: alice
Tenant B has user: alice

Both Authentications have getName() = "alice".
If PrincipalSid("alice") is used without tenant distinction:
  -> both users can match the exact same SID.
~~~

In a multi-tenant system, design identities that are **stable and globally unique** (e.g., `tenantA:user-17` by authentication convention) or implement a SID/persistence mechanism that consistently supports tenants. Simply calling `new PrincipalSid("alice")` adds no tenant boundary; the default ACL schema does not enforce tenancy in SID values either.

Avoid using mutable emails as durable SIDs without a migration strategy. If a username is reused after an account is deleted, a new user could accidentally inherit leftover ACEs from the previous owner if permissions are not cleaned up.

## 4. `GrantedAuthoritySid`: Granting Permission to Holders of an Authority

Spring Security defines:

~~~java
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.acls.model.Sid;

// Two ways to represent the same authority in the demo:
Sid byString = new GrantedAuthoritySid("ROLE_REVIEWER");
Sid byAuthority = new GrantedAuthoritySid(
        new SimpleGrantedAuthority("ROLE_REVIEWER"));
~~~

Key constructors and accessor:

- `new GrantedAuthoritySid(String grantedAuthority)`.
- `new GrantedAuthoritySid(GrantedAuthority grantedAuthority)`.
- `getGrantedAuthority()`: the authority string stored in the SID.

The ACE:

~~~text
ObjectIdentity = Document#202
Sid = GrantedAuthoritySid("ROLE_REVIEWER")
Permission = READ
Granting = true
~~~

means **anyone holding `ROLE_REVIEWER` in their `Authentication` at evaluation time** can be a recipient for READ on `Document#202`. When a user gains or loses that authority in the authentication system, the set of users matching the ACE changes without necessarily rewriting individual ACL entries.

### This Is Authority-Scoped, Not Automatically Global

If only `Document#202` has an ACE for `GrantedAuthoritySid("ROLE_REVIEWER")`, the reviewer role does **not** automatically receive READ on `Document#101` or `Document#999`. It applies only to ACL objects containing a matching entry, or to child ACLs **permitted to inherit** that entry.

This differs from:

~~~java
@PreAuthorize("hasRole('REVIEWER')")
~~~

That expression checks the role at the **method interception point**; it does not attach an ACE to individual documents. By contrast, authority-based ACL checks still evaluate `ObjectIdentity`, `Permission`, ACEs, and grant/deny mechanics.

### `ROLE_REVIEWER` Differs from `REVIEWER`

`GrantedAuthoritySid("ROLE_REVIEWER")` and `GrantedAuthoritySid("REVIEWER")` are **two different SIDs**. Spring Security's `hasRole('REVIEWER')` normally matches authority `ROLE_REVIEWER` via the default role prefix; however, the `GrantedAuthoritySid(String)` constructor does not prepend `ROLE_`.

If a user has:

~~~text
GrantedAuthority.getAuthority() = "ROLE_REVIEWER"
~~~

then an entry using `GrantedAuthoritySid("REVIEWER")` will not match automatically. Never change authority naming conventions in ACLs without migrating all stored data and checking role hierarchy configurations.

### Authorities Can Represent Groups, Capabilities, or Permissions

`GrantedAuthoritySid` is not limited to names starting with `ROLE_`. A system might use:

~~~text
ROLE_REVIEWER
PROJECT_42_EDITOR
DOC_SHARED_READ
TENANT_7_AUDITOR
~~~

These are **string naming conventions**, not distinct Spring SID classes. For them to carry security meaning, the authentication layer must issue authorities from trusted sources, and the ACL must hold ACEs with exact matching names. Never trust a client-supplied `X-Role` header or query string as a `GrantedAuthority`.

If authority assignment is overly broad (users receive incorrect roles), every ACL recipient matching that role is affected. This is the **blast radius** of authority-based permissions and why membership lifecycles must be tightly controlled.

## 5. Comparing PrincipalSid and GrantedAuthoritySid

| Question | `PrincipalSid` | `GrantedAuthoritySid` |
| --- | --- | --- |
| Who does it represent? | One specific principal | Every principal currently holding a specific authority |
| Comparison key | Principal string, usually username | Authority string, e.g., `ROLE_EDITOR` |
| When to use? | Per-person exception sharing | Shared permissions for a group/capability |
| Automatically applies to new group members? | No, unless granted a dedicated ACE | Yes, if their authentication receives that authority |
| Loses access when leaving the group? | Does not affect personal ACEs already granted | Typically stops matching the group SID once authority is revoked and authentication updates |
| Object-scoped? | Yes, ACE belongs to an ObjectIdentity/ACL | Yes, same as PrincipalSid |
| Main risk | Principal collisions/renames, deleted users leaving stale ACEs | Misassigned authorities, overly broad groups, role hierarchy expansion |
| Automatically grants all objects? | No | No |
| Automatically enforces tenancy? | No | No |

### Do Not Confuse Two SIDs Just Because Their Strings Match

~~~java
Sid a = new PrincipalSid("ROLE_REVIEWER");
Sid b = new GrantedAuthoritySid("ROLE_REVIEWER");

// false: one is a principal, the other is an authority.
boolean same = a.equals(b);
~~~

Never store SID types in a single string column without preserving the `principal` flag. The same `sid = "ROLE_REVIEWER"` in the database can represent **two completely different recipients** if the SID type flag differs.

## 6. How Is `Authentication` Converted into SIDs?

Spring Security provides `SidRetrievalStrategy` and its implementation `SidRetrievalStrategyImpl`.

~~~java
import java.util.List;
import org.springframework.security.acls.domain.SidRetrievalStrategyImpl;
import org.springframework.security.acls.model.Sid;

List<Sid> applicableSids =
        new SidRetrievalStrategyImpl().getSids(authentication);
~~~

Given a hypothetical authentication:

~~~text
principal = "alice"
authorities = ["ROLE_REVIEWER", "DOC_EXPORT"]
~~~

the corresponding SID list is typically:

~~~text
PrincipalSid("alice")
GrantedAuthoritySid("ROLE_REVIEWER")
GrantedAuthoritySid("DOC_EXPORT")
~~~

The default implementation places the `PrincipalSid` before the `GrantedAuthoritySid` entries; the order of authorities depends on the collection/strategy. Spring ACL uses this recipient list to match against the ACEs of the checked `ObjectIdentity`.

**Never inject ungranted authorities** into the SID list just to make a check succeed. In particular, never synthesize `GrantedAuthoritySid("ROLE_ADMIN")` for users manually inside a service. SIDs must originate from verified `Authentication` and controlled grants.

A `SidRetrievalStrategyImpl(RoleHierarchy)` can also include authorities expanded via a role hierarchy if configured by the application. Confirm whether hierarchy expansion in ACLs matches your intent; never assume role prefixes or identity provider groups automatically imply role relationships inside ACLs.

### PrincipalSid Appearing First Does Not Mean "Always Beats Every Role"

In `DefaultPermissionGrantingStrategy`, **permission order, SID list order, and ACE order** affect evaluation. A specific grant/deny ACE for a principal may be inspected before an authority ACE in certain checks. However, never assert rigid rules like "deny always wins" or "role grant overrides every deny"; actual behavior depends on the strategy, queried permissions, ordering, and existing ACEs.

When entries overlap, **test against the real ACL** with the configured strategy rather than writing `anyMatch(grant)` in place of the framework.

## 7. Levels of Scope: SID, Object, Permission, and Inheritance Tree

A common misconception is thinking `PrincipalSid("alice")` carries a list of permissions independent of objects. In ACL, decisions involve additional axes:

~~~text
              Who?
              |
       PrincipalSid / GrantedAuthoritySid
              |
              v
           ACE
           /  \
    Permission  ObjectIdentity
       |               |
    READ/WRITE     Document#101
                       |
                 Parent ACL?
                       |
              entriesInheriting?
~~~

### 7.1. ObjectIdentity Identifies a Unique Resource

An `ObjectIdentityImpl` is constructed from resource type and ID:

~~~java
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.ObjectIdentity;

ObjectIdentity a = new ObjectIdentityImpl("demo.Document", 101L);
ObjectIdentity b = new ObjectIdentityImpl("demo.Document", 202L);
ObjectIdentity c = new ObjectIdentityImpl("demo.Folder", 101L);
~~~

These three object identities are distinct: document 101, document 202, and folder 101. ID `101` alone is insufficient when an application has multiple domain object types.

Advice: use stable identifiers that are never arbitrarily reused, and follow a consistent type naming convention. For domain objects, `new ObjectIdentityImpl(domainObject)` relies on accessing the ID via a conventional getter (typically `getId()`); it is not automatically compatible with Java records that only expose `id()`.

### 7.2. Permission Is an Action, Not a SID

`BasePermission` defines several common permissions:

| Permission | Default Mask | Description |
| --- | --- | --- |
| `BasePermission.READ` | `1` | Read |
| `BasePermission.WRITE` | `2` | Write |
| `BasePermission.CREATE` | `4` | Create |
| `BasePermission.DELETE` | `8` | Delete |
| `BasePermission.ADMINISTRATION` | `16` | Administer ACL / object per policy |

A user with a `READ` ACE on `Document#101` **does not automatically get WRITE**. An authority `ROLE_EDITOR` granted WRITE on `Document#202` **does not automatically get WRITE** on every object of the same type.

Bitmasks encode permission types, not 32 slots for 32 documents; each domain object has its own ACL, so the system can hold vast numbers of object identities.

Some systems use `CumulativePermission` or custom `Permission` types; in those cases, mask semantics and strategy matching must be thoroughly understood. Never assume a combined mask is automatically equivalent to individual bits under every strategy configuration.

### 7.3. Parent ACL and Inheritance

An ACL can reference `getParentAcl()`. Under the default mechanism, for parent ACEs to be consulted on the child, `isEntriesInheriting() == true` and a valid parent must be set:

~~~text
Folder#8 ACL:
  GrantedAuthoritySid("ROLE_REVIEWER") → READ (grant)

Document#202 ACL:
  parent = Folder#8
  entriesInheriting = true
  (no matching local entry)
  => Can inherit READ permission from Folder#8's ACL
~~~

If `entriesInheriting = false`, merely having a parent link **is not enough** for the child to inherit ACEs. If the child ACL already has a matching grant/deny entry, the strategy can decide right at the child before consulting the parent.

Therefore, granting an authority SID on a folder can propagate across many child documents **if inheritance is enabled**. Before opening a broad role on a folder, audit the entire subtree and any sensitive documents underneath.

### 7.4. ACL Owner Does Not Automatically Mean READ/WRITE on All Data

`Acl.getOwner()` indicates the SID recorded as the **ACL owner**. `AclAuthorizationStrategy` can grant the owner special privileges to **administer/edit the ACL** per its rules, but that is no guarantee that `Acl.isGranted(READ,...)` returns true for the owner.

Distinguish three concerns:

1. **ACL ownership**: who may administer policies/ACEs per `AclAuthorizationStrategy`.
2. **Domain permissions on the object**: READ/WRITE/DELETE... per `Acl.isGranted`.
3. **System permissions outside the ACL**: e.g., SUPERADMIN privileges, tenant constraints, legal holds, workflow states.

An ACL owner may require an explicit READ ACE if design dictates; never conflate the person allowed to administer permissions with someone always allowed to read content.

## 8. Database Storage: The Four ACL Tables

Spring Security ACL uses these default table groups:

| Table | Key Data | Role with SIDs |
| --- | --- | --- |
| `ACL_SID` | `id`, `principal`, `sid` | Identifies recipients, distinguishing principal from authority |
| `ACL_CLASS` | `id`, `class` | Identifies domain object types |
| `ACL_OBJECT_IDENTITY` | `id`, `object_id_class`, `object_id_identity`, `parent_object`, `owner_sid`, `entries_inheriting` | Identifies object, ACL owner, parent/inheritance |
| `ACL_ENTRY` | `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting`, audit flags | One ACE binding SID and permission to **one object ACL** |

Exact table/column names must be verified against the schema script for your Spring Security ACL version. Data example:

~~~text
ACL_SID
id=10, principal=true,  sid="alice"
id=11, principal=false, sid="ROLE_REVIEWER"

ACL_CLASS
id=1, class="demo.Document"

ACL_OBJECT_IDENTITY
id=1001, class=1, object_id_identity=101, owner_sid=10
id=1002, class=1, object_id_identity=202, owner_sid=10

ACL_ENTRY
acl_object_identity=1001, sid=10, mask=1, granting=true  (alice reads 101)
acl_object_identity=1002, sid=11, mask=1, granting=true  (reviewer reads 202)
~~~

This is strictly a **conceptual value diagram for learning**, not runnable seed SQL; required columns, IDs, foreign key constraints, ID generation strategies, and update semantics must match your actual database schema.

**Key takeaway:** the system does not look up ACEs by `sid` alone. It looks up the ACL of the **`ObjectIdentity`** and then checks the recipient SIDs within that ACL. `ACL_SID` is not a "role -> all resources" mapping table.

### The `principal` Flag Carries Security Meaning

A user named `ROLE_REVIEWER` could have `PrincipalSid("ROLE_REVIEWER")`, which differs from `GrantedAuthoritySid("ROLE_REVIEWER")`. The `principal` column in `ACL_SID` separates them. If data sync/migration drops this flag, policies can grant access to the wrong recipient.

### Never Mutate ACL Tables with Uninformed SQL

To keep caches and ACL state consistent, use `MutableAclService` for create/update/delete operations instead of manually INSERTing ACE rows and forgetting the cache. When direct DB edits are unavoidable (controlled migrations), ensure you invalidate caches and verify parent/inheritance, SID rows, `ace_order`, audit flags, unique constraints, and transactions.

## 9. Standalone Runnable Java 17+ Example: Distinguishing SIDs and Object Scope

To verify both SID types **without needing JDBC**, let us write a small program using the actual `PrincipalSid`, `GrantedAuthoritySid`, `SidRetrievalStrategyImpl`, `ObjectIdentityImpl`, and `BasePermission` classes from Spring Security ACL.

The program uses a **simulated list of grants** to illustrate how recipients match objects. `hasIllustrativeDirectGrant` **is not** the real ACL algorithm: it only models grants, without deny entries, auditing, inheritance, or a permission granting strategy. In real applications, use `AclService`/`Acl.isGranted(...)`.

### 9.1. Standalone Java Gradle Build

Create a **new Java Gradle project** to practice, rather than modifying an active application repository unless requested. `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'demo'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-acl:6.5.4'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.aclscope.SidScopeDemo'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Version `spring-security-acl:6.5.4` is used to **pin a specific API line for the example**. In a Spring Boot project with dependency management, use the Security version managed by Boot instead of forcing an isolated version that might clash with the rest of the stack.

### 9.2. Complete Code

**`src/main/java/demo/aclscope/SidScopeDemo.java`**

~~~java
package demo.aclscope;

import java.util.Arrays;
import java.util.List;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SidRetrievalStrategyImpl;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class SidScopeDemo {

    private SidScopeDemo() {
    }

    // Illustrates simple ACE GRANT only to teach SID/object scope.
    // Does not replace Acl.isGranted(...) and does not handle DENY/INHERITANCE.
    public record DemoGrant(
            ObjectIdentity object,
            Sid recipient,
            Permission permission) {
    }

    public static Authentication auth(String principal, String... authorityNames) {
        var authorities = Arrays.stream(authorityNames)
                .map(SimpleGrantedAuthority::new)
                .toList();

        return new UsernamePasswordAuthenticationToken(
                principal, "demo-only", authorities);
    }

    public static List<Sid> sidsOf(Authentication authentication) {
        return new SidRetrievalStrategyImpl().getSids(authentication);
    }

    public static boolean hasIllustrativeDirectGrant(
            List<DemoGrant> grants,
            ObjectIdentity object,
            Permission permission,
            Authentication authentication) {

        List<Sid> recipients = sidsOf(authentication);

        return grants.stream().anyMatch(grant ->
                grant.object().equals(object)
                && grant.permission().equals(permission)
                && recipients.contains(grant.recipient()));
    }

    public static void main(String[] args) {
        Authentication alice = auth("alice", "ROLE_REVIEWER");
        Authentication bob = auth("bob", "ROLE_REVIEWER");
        Authentication carol = auth("carol", "ROLE_VIEWER");

        ObjectIdentity doc101 = new ObjectIdentityImpl("demo.Document", 101L);
        ObjectIdentity doc202 = new ObjectIdentityImpl("demo.Document", 202L);

        var grants = List.of(
                new DemoGrant(
                        doc101, new PrincipalSid("alice"), BasePermission.READ),
                new DemoGrant(
                        doc202, new GrantedAuthoritySid("ROLE_REVIEWER"),
                        BasePermission.READ));

        System.out.println("PrincipalSid alice matches alice: "
                + sidsOf(alice).contains(new PrincipalSid("alice")));
        System.out.println("PrincipalSid alice matches bob: "
                + sidsOf(bob).contains(new PrincipalSid("alice")));
        System.out.println("AuthoritySid REVIEWER matches alice: "
                + sidsOf(alice).contains(
                        new GrantedAuthoritySid("ROLE_REVIEWER")));
        System.out.println("AuthoritySid REVIEWER matches bob: "
                + sidsOf(bob).contains(
                        new GrantedAuthoritySid("ROLE_REVIEWER")));
        System.out.println("Principal/Authority same text equal: "
                + new PrincipalSid("ROLE_REVIEWER").equals(
                        new GrantedAuthoritySid("ROLE_REVIEWER")));

        System.out.println("alice doc101 READ: "
                + hasIllustrativeDirectGrant(
                        grants, doc101, BasePermission.READ, alice));
        System.out.println("bob doc101 READ: "
                + hasIllustrativeDirectGrant(
                        grants, doc101, BasePermission.READ, bob));
        System.out.println("alice doc202 READ: "
                + hasIllustrativeDirectGrant(
                        grants, doc202, BasePermission.READ, alice));
        System.out.println("bob doc202 READ: "
                + hasIllustrativeDirectGrant(
                        grants, doc202, BasePermission.READ, bob));
        System.out.println("carol doc202 READ: "
                + hasIllustrativeDirectGrant(
                        grants, doc202, BasePermission.READ, carol));

        System.out.println("READ mask: " + BasePermission.READ.getMask());
        System.out.println("WRITE mask: " + BasePermission.WRITE.getMask());
    }
}
~~~

In this program, `auth(...)` builds a `UsernamePasswordAuthenticationToken` for **demo/test purposes**, not a production authentication flow. `SidRetrievalStrategyImpl` takes an `Authentication` and returns the corresponding SIDs. Each `DemoGrant` binds **exactly one ObjectIdentity + recipient + permission**. Nothing here derives permissions from an unauthenticated request username as would be dangerous in a real app.

### 9.3. Running and Expected Stdout

Run in the Gradle project directory with wrapper:

~~~text
./gradlew run
~~~

On Windows:

~~~text
gradlew.bat run
~~~

The program prints these exact application lines (Gradle may print additional task/build lines):

~~~text
PrincipalSid alice matches alice: true
PrincipalSid alice matches bob: false
AuthoritySid REVIEWER matches alice: true
AuthoritySid REVIEWER matches bob: true
Principal/Authority same text equal: false
alice doc101 READ: true
bob doc101 READ: false
alice doc202 READ: true
bob doc202 READ: true
carol doc202 READ: false
READ mask: 1
WRITE mask: 2
~~~

Explanation:

1. Alice and Bob have different principals.
2. Both carry the `ROLE_REVIEWER` authority.
3. A `PrincipalSid` with the same string as a `GrantedAuthoritySid` remains a distinct SID type.
4. The grant on `doc101` is strictly for alice; Bob does not receive it despite being a reviewer.
5. The grant on `doc202` targets the reviewer authority, so both Alice and Bob match.
6. Carol lacks the reviewer SID and thus does not match the `doc202` grant.
7. `READ` has mask 1 and `WRITE` has mask 2; permission is an axis independent of object and SID.

**Important boundary:** `hasIllustrativeDirectGrant` is named that way to avoid confusing it with `Acl.isGranted` when deny entries, multiple ACEs, inheritance, auditing, or custom granting strategies exist. Never copy this helper into production to replace real ACL decisions.

### 9.4. JUnit Test Verifying Scope Is Not Over-Expanded

**`src/test/java/demo/aclscope/SidScopeDemoTest.java`**

~~~java
package demo.aclscope;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.core.Authentication;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SidScopeDemoTest {

    @Test
    void principalIdentityIsNotAnAuthorityIdentity() {
        assertFalse(new PrincipalSid("ROLE_REVIEWER")
                .equals(new GrantedAuthoritySid("ROLE_REVIEWER")));
        assertEquals(new PrincipalSid("alice"), new PrincipalSid("alice"));
    }

    @Test
    void principalSidMatchesOnlyTheNamedUser() {
        Authentication alice = SidScopeDemo.auth("alice", "ROLE_REVIEWER");
        Authentication bob = SidScopeDemo.auth("bob", "ROLE_REVIEWER");

        assertTrue(SidScopeDemo.sidsOf(alice)
                .contains(new PrincipalSid("alice")));
        assertFalse(SidScopeDemo.sidsOf(bob)
                .contains(new PrincipalSid("alice")));
    }

    @Test
    void authoritySidMatchesEachCurrentHolder() {
        Authentication alice = SidScopeDemo.auth("alice", "ROLE_REVIEWER");
        Authentication bob = SidScopeDemo.auth("bob", "ROLE_REVIEWER");
        Authentication carol = SidScopeDemo.auth("carol", "ROLE_VIEWER");

        var reviewer = new GrantedAuthoritySid("ROLE_REVIEWER");
        assertTrue(SidScopeDemo.sidsOf(alice).contains(reviewer));
        assertTrue(SidScopeDemo.sidsOf(bob).contains(reviewer));
        assertFalse(SidScopeDemo.sidsOf(carol).contains(reviewer));
    }

    @Test
    void grantIsConstrainedByObjectAndPermission() {
        ObjectIdentity doc101 =
                new ObjectIdentityImpl("demo.Document", 101L);
        ObjectIdentity doc202 =
                new ObjectIdentityImpl("demo.Document", 202L);

        var grants = List.of(new SidScopeDemo.DemoGrant(
                doc101, new PrincipalSid("alice"), BasePermission.READ));

        Authentication alice = SidScopeDemo.auth("alice", "ROLE_REVIEWER");

        assertTrue(SidScopeDemo.hasIllustrativeDirectGrant(
                grants, doc101, BasePermission.READ, alice));
        assertFalse(SidScopeDemo.hasIllustrativeDirectGrant(
                grants, doc202, BasePermission.READ, alice));
        assertFalse(SidScopeDemo.hasIllustrativeDirectGrant(
                grants, doc101, BasePermission.WRITE, alice));
    }

    @Test
    void sameIdInDifferentTypeIsDifferentObject() {
        ObjectIdentity doc101 =
                new ObjectIdentityImpl("demo.Document", 101L);
        ObjectIdentity folder101 =
                new ObjectIdentityImpl("demo.Folder", 101L);

        assertFalse(doc101.equals(folder101));
    }
}
~~~

Run:

~~~text
./gradlew test --tests demo.aclscope.SidScopeDemoTest
~~~

When the tests pass, JUnit verifies the **exact SID type**, user/role recipients, object scope, permission scope, and the distinction between two object types sharing an ID. These tests only check the demo grant selection; add integration tests with real JDBC ACLs to verify grant/deny/inheritance behavior.

## 10. Persisting Real Grants with `MutableAclService`: Illustrative Integration Snippet

The hands-on example above uses no database. When real ACL administration is needed, applications typically have:

- `spring-security-acl` in dependencies.
- `DataSource` and the four tables `ACL_SID`, `ACL_CLASS`, `ACL_OBJECT_IDENTITY`, `ACL_ENTRY` created with the proper schema.
- `JdbcMutableAclService`, `BasicLookupStrategy`, `AclCache`, `PermissionGrantingStrategy`, and `AclAuthorizationStrategy` appropriately configured.
- An ACL administration service with **its own authorization gate** so callers cannot arbitrarily grant permissions to others.

Once `MutableAclService aclService` is injected and ACL modification is authorized, adding ACEs looks like this:

~~~java
// ILLUSTRATIVE CODE IN A SERVICE WITH EXISTING ACL INFRASTRUCTURE.
// Not standalone runnable; do not call from a public API lacking administrative permission checks.

ObjectIdentity object = new ObjectIdentityImpl("demo.Document", 101L);

MutableAcl acl;
try {
    acl = (MutableAcl) aclService.readAclById(object);
} catch (NotFoundException missing) {
    acl = aclService.createAcl(object);
}

// Share READ strictly to user "alice".
acl.insertAce(
        acl.getEntries().size(),
        BasePermission.READ,
        new PrincipalSid("alice"),
        true
);

// Grant READ to holders of authority ROLE_REVIEWER on THIS OBJECT.
acl.insertAce(
        acl.getEntries().size(),
        BasePermission.READ,
        new GrantedAuthoritySid("ROLE_REVIEWER"),
        true
);

aclService.updateAcl(acl);
~~~

Required imports for this snippet:

~~~java
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
~~~

The snippet intentionally **does not pretend to be a standalone program**: Spring Context, DataSource, SQL schema, and ACL service/configuration are omitted. When adding this to a real service, protect administrative endpoints with authentication, verify permission to grant ACEs, ensure idempotency, avoid duplicate entries, and handle concurrency.

### Grants and Denies Should Never Be Calculated Manually

`insertAce(position, permission, sid, granting)` takes:

- `position`: index in ACE order (usually appended via `acl.getEntries().size()`).
- `permission`: e.g., `BasePermission.READ`.
- `sid`: `PrincipalSid` or `GrantedAuthoritySid`.
- `granting = true`: grant; `false`: deny.

When the same object has overlapping ACEs, do not assume the last-added ACE always takes precedence. The ordering of ACEs, SIDs, and permissions used by `PermissionGrantingStrategy` affects the outcome. After ACL updates, include tests verifying **an authorized user is granted**, **an unauthorized user is denied**, and conflicting deny/group grant scenarios behave as expected before rolling out broadly.

### Do Not Equate ACL Admin with Object Permission

`AclAuthorizationStrategyImpl` governs who is **allowed to modify the ACL**. Depending on configuration, it may check the ACL owner, an administrative authority, or `ADMINISTRATION` permission. Being able to edit ACEs differs from `Acl.isGranted(READ,...)` on the document. A "grant READ to alice" service is a sensitive operation: only actors authorized to manage ACLs may execute it.

## 11. Evaluating Real Permissions with `Acl.isGranted(...)`

An ACL may load only the needed SIDs to optimize queries. API:

~~~java
boolean allowed = acl.isGranted(
        List.of(BasePermission.READ),
        sids,
        false
);
~~~

Three parameters:

1. `List<Permission>`: permissions that satisfy the check; if multiple are passed, order matters per the strategy.
2. `List<Sid>`: SIDs of the user being evaluated.
3. `administrativeMode`: administrative check mode, normally bypassing audit logging when true; it is **not** a "user is admin" flag.

A more complete integration snippet for read checks:

~~~java
// ILLUSTRATIVE: assumes aclService and Authentication are securely provided.
ObjectIdentity object = new ObjectIdentityImpl("demo.Document", 101L);

List<Sid> sids = new SidRetrievalStrategyImpl().getSids(authentication);

boolean allowed;
try {
    Acl acl = aclService.readAclById(object, sids);
    allowed = acl.isGranted(List.of(BasePermission.READ), sids, false);
} catch (NotFoundException missingPermissionOrAcl) {
    // No grant decision -> fail closed.
    allowed = false;
}
~~~

Additional imports:

~~~java
import java.util.List;
import org.springframework.security.acls.domain.SidRetrievalStrategyImpl;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.Sid;
~~~

In real applications, `UnloadedSidException` can also be thrown if an ACL was only partially loaded and you query a SID outside the loaded subset. That indicates incomplete data loading, **not a grant**; fix the retrieval logic or handle the error safely rather than returning true.

### Crucial Distinction: Matching ACE, Explicit Deny, and Missing ACE

Under the default strategy:

- A matching grant ACE can allow access.
- A matching deny ACE can deny access depending on permission/SID evaluation order.
- Finding no conclusive ACE can throw `NotFoundException`, never "default allow."
- Having a parent ACL with `entriesInheriting == true` can continue evaluation on the parent when no direct matching entry exists.

Never write production code like `return acl.getEntries().stream().anyMatch(ace -> ace.isGranting())`. That ignores SIDs, permissions, ordering, `loadedSids`, and inheritance.

### When to Use `hasPermission(...)`?

Spring Security ACL includes `AclPermissionEvaluator`, which can plug into `DefaultMethodSecurityExpressionHandler` so `hasPermission` annotations query ACLs without repeating `aclService.readAclById` in every service.

~~~java
// Configuration excerpt; requires a properly configured AclService bean.
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        AclService aclService) {

    var handler = new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(new AclPermissionEvaluator(aclService));
    return handler;
}
~~~

Once `@EnableMethodSecurity` is enabled and the handler bean exists, services can use:

~~~java
// Illustration on a method; target type and ACL ObjectIdentity must match.
@PreAuthorize("hasPermission(#documentId, 'demo.Document', 'READ')")
public Document read(long documentId) {
    // ...
}
~~~

If using `hasPermission(returnObject, 'READ')`, the returned object must expose its ID in a way compatible with `ObjectIdentityRetrievalStrategy`. `ObjectIdentityImpl(Object)` defaults to getters like `getId()`; a Java record exposing only `id()` does not automatically match that convention. Moreover, the stored ACL `ObjectIdentity` must match both type name and ID produced by the evaluator.

This is an illustrative integration section, not a full JDBC configuration guide. The goal of this lesson is understanding **recipient SIDs and ACE scope** before wiring into a real project's ACL persistence and Method Security.

## 12. Roles, Groups, Resource Permissions, and Effective Scope

### Distinguishing Three Authorization Questions

| Question | Example Mechanism |
| --- | --- |
| Is Alice authenticated? | `Authentication.isAuthenticated()` / authentication layer |
| Does Alice hold authority `ROLE_REVIEWER`? | `hasAuthority('ROLE_REVIEWER')` or authorities on Authentication |
| Is Alice allowed to READ **Document#202**? | `Acl.isGranted(READ, SID list)` on Document#202's ACL |

Only the third question combines **recipient + action + object**. Thus, ACL and RBAC do not exclude one another: RBAC supplies authorities, and ACLs can use those authorities as recipients for specific objects.

### Individual and Group Scopes Can Coexist

Example:

~~~text
Document#101:
    PrincipalSid("alice")          → READ:grant
    GrantedAuthoritySid("ROLE_EDITOR") → WRITE:grant

Document#202:
    GrantedAuthoritySid("ROLE_REVIEWER") → READ:grant
    PrincipalSid("bob")            → DELETE:deny
~~~

Never misread the example above as "bob can never delete any document" or "editors can always edit every document." Each ACE belongs to one ACL, one specific permission, and the configured inheritance rules. If another object lacks an equivalent ACE, the outcome can differ.

### When to Choose Which SID?

Prefer `PrincipalSid` when:
- Granting an exception to a specific person.
- Sharing an object individually.
- Needing to revoke a specific recipient without altering group memberships.

Prefer `GrantedAuthoritySid` when:
- Granting permissions to a stable group or capability.
- Wanting users joining or leaving the group to be governed by their current authorities.
- Having many objects where the same group policy is applied **per ACL** or intentionally through an inheritance tree.

Never use an overly broad group (like `ROLE_USER`) in place of tenant/owner checks on confidential documents. If every account holds that role, a single role-based ACE on an object exposes that object to **every account holding the role**, even outside the project team unless another tenant boundary blocks it.

## 13. Multi-Tenancy, Permission Hierarchies, and Access Lifecycle

### 13.1. Tenant Is Not a Built-In Property of SID

By default, `PrincipalSid` and `GrantedAuthoritySid` have no dedicated tenant field. Thus:

~~~text
Tenant A: username=alice, authority=ROLE_REVIEWER
Tenant B: username=alice, authority=ROLE_REVIEWER
~~~

risks matching the same SID if the system shares ACL tables without tenant isolation. Safeguards must be layered:

- Use immutable, globally unique principal identifiers in `Authentication`.
- Enforce tenant boundaries in `ObjectIdentity`/repository lookups and use cases.
- If using tenant-scoped authorities, names must be issued/verified by trusted systems, never taken from requests.
- Test collisions of usernames, object IDs across tenants, cross-tenant folder inheritance, and shared roles.

Do not rely on a string prefix like `TENANT_7_` alone if an attacker can request that authority or if ACL queries omit tenant filtering. In particular, `ObjectIdentityImpl("demo.Document", 101L)` carries only type and ID; if two tenants' databases both have document ID 101, normalize IDs globally or partition ACLs accordingly.

### 13.2. Role Hierarchy Can Expand the Recipient Set

If an application configures a hierarchy on `SidRetrievalStrategyImpl`, a user declared only with `ROLE_ADMIN` may be treated as also holding `ROLE_REVIEWER` per the hierarchy. Consequently, a `GrantedAuthoritySid("ROLE_REVIEWER")` ACE can apply to the admin even when the token does not list `ROLE_REVIEWER` directly.

This may make sense in RBAC, but ACL setups require testing the **actual SID retrieval strategy** to ensure privilege expansion does not cross tenant or group boundaries. Never assume a hierarchy is automatically part of every `SidRetrievalStrategyImpl()` instance.

### 13.3. When Does Role Revocation Take Effect?

Removing `ROLE_REVIEWER` in the authorization database does not immediately update every previously issued `Authentication`. With sessions or JWTs containing snapshotted authorities, a user may continue carrying the old role SID until the session/token is refreshed, revoked, or expires. If immediate revocation is required, implement token revocation, server-side authority lookup, or controlled ACL updates.

### 13.4. Deleted Users, Renamed Usernames, Renamed Roles

Define a lifecycle for `ACL_SID` and `ACL_ENTRY`:

- When a user is deleted, decide whether to retain ACE history or revoke/delete rights; prevent orphaned SIDs from being reassigned later.
- When usernames or canonical principal IDs change, synchronize SIDs if the identifier stored in ACLs changes.
- When renaming a role, migrations must update both authorities issued at authentication **and** `ACL_SID`/ACE rows using the old role.
- When project membership changes, verify when tokens reflect the new membership.
- When deleting a domain object, clean up its corresponding ACL to avoid leftover permissions if IDs are reused.

### 13.5. ACL Cache and Permission Updates

Spring ACL commonly uses `AclCache` to reduce query overhead. Adding/removing ACEs via `MutableAclService` keeps persistence and cache synchronized per the implementation. Bypassing the service with raw SQL can leave stale ACLs in cache and continue granting unintended access. In distributed systems, account for cross-node invalidation, consistency windows, and revocation tests.

## 14. Common Bugs to Catch with Tests

| Symptom | Common Root Cause | Fix |
| --- | --- | --- |
| Granted permission to one person, but others with the same role also access it | Used `GrantedAuthoritySid` instead of `PrincipalSid` | Target the right recipient; test peers sharing the role |
| Granted reviewer role, yet cannot read the object | ACE does not belong to that object's ACL or inheritance is off | Check ObjectIdentity, parent ACL, and entriesInheriting |
| A user in tenant B receives tenant A permissions | Principal string/authority collision across tenants | Use global user IDs and enforce tenancy in lookups/policies |
| `GrantedAuthoritySid("REVIEWER")` does not match | Authentication contains `ROLE_REVIEWER` | Store the exact authority string; do not assume prefixing |
| Permission works only for a specific user | ACE uses PrincipalSid instead of authority SID | Use the right SID type for the requirement |
| WRITE permission appears on another document | Overly broad ACL inheritance/grant or wrong object identity | Inspect tree structure and each object's type/id |
| ACL owner can access admin controls but cannot read content | ACL edit permission differs from object READ permission | Check dedicated READ ACE and business policy |
| Simple membership test passes, real ACL denies | Missed deny entry, ACE ordering, or strategy behavior | Use `Acl.isGranted` and grant/deny integration tests |
| `NotFoundException` on permission check | No conclusive ACE found; ACL may be missing | Fail closed; create ACL/ACE in the proper workflow |
| `UnloadedSidException` | ACL loaded only a partial set of SIDs | Load all required SIDs or fail safely |
| ACL updated, permissions unchanged | Stale cache, session, or JWT | Verify invalidation and authentication lifecycle |
| User changes email and loses personal ACEs | PrincipalSid used mutable email | Use stable subject IDs or run migrations |
| `READ` permission confused with `WRITE` | Inferred from role instead of checking bitmasks | Use `BasePermission` properly and test each action |
| Manual SQL sync causes errors | Stale cache / foreign keys / `ace_order` mismatch | Use `MutableAclService` or controlled migrations |
| Custom Sid saves in Java, not found via JDBC | Default persistence/lookup only understands standard SID types | Extend JDBC strategy and schema; test E2E |

## 15. Practical Testing Strategy

To prevent an ACL from silently over-granting access, test across the **four-dimensional matrix**:

| User and Authority | Object | Permission | Expected |
| --- | --- | --- | --- |
| Alice, reviewer | Document#101 | READ | Allow via PrincipalSid |
| Bob, reviewer | Document#101 | READ | Deny unless another ACE applies |
| Alice, reviewer | Document#202 | READ | Allow via GrantedAuthoritySid |
| Bob, reviewer | Document#202 | READ | Allow via GrantedAuthoritySid |
| Carol, viewer | Document#202 | READ | Deny unless another ACE applies |
| Alice, reviewer | Document#101 | WRITE | Deny unless a WRITE ACE exists |
| Tenant B Alice with colliding principal | Tenant A Document#101 | READ | Deny per tenant policy |
| Reviewer role revoked in new auth | Document#202 | READ | Deny unless another matching SID applies |
| Bob reviewer, but has personal deny ACE | Document#202 | READ | Must follow configured strategy/ACE order |
| Alice, ACL owner lacking READ ACE | Document#303 | READ | Do not infer allow solely from ACL owner |

Notes saying "unless another ACE applies" remind us that real ACLs can hold **multiple entries** and inheritance. Never use a single example row to claim universal outcomes across every configuration.

When writing integration tests:

1. Initialize the ACL SQL schema on the test database.
2. Create two `Authentication` instances with different principals sharing an authority, plus a principal with a different authority.
3. Create ACLs for two distinct `ObjectIdentity` instances, adding user and authority ACEs.
4. Call `Acl.isGranted` with real SIDs extracted from `Authentication`.
5. Add deny entries, change `ace_order`, and toggle `entriesInheriting` to confirm observed mechanics.
6. Revoke an authority, build a fresh `Authentication`, and test the updated permission.
7. Test two tenants with identical names/IDs and verify zero cross-tenant reads.
8. Verify cache behavior and ACE deletion effects on subsequent decisions.

## 16. Hands-On Exercises

**Exercise 1 – Individual and group sharing.** Create an ACL for `Document#101` granting READ to `PrincipalSid("alice")`. Create an ACL for `Document#202` granting READ to `GrantedAuthoritySid("ROLE_REVIEWER")`. Write tests for alice, bob (also reviewer), and carol (viewer) explaining why scopes differ.

**Exercise 2 – Changing roles.** Change Bob's authority from `ROLE_REVIEWER` to `ROLE_VIEWER`. Build a new `Authentication`, recompute SIDs, and verify Bob no longer matches the reviewer ACE. Explain why old JWTs/sessions may not yet reflect the change.

**Exercise 3 – Distinguishing principal and authority with the same name.** Create `PrincipalSid("ROLE_EDITOR")` and `GrantedAuthoritySid("ROLE_EDITOR")`. Explain why they are distinct SIDs in `ACL_SID` despite identical strings; write a test proving they are not conflated.

**Exercise 4 – Inheritance.** Create a folder ACL granting READ to the reviewer role; link a child document ACL. Toggle `entriesInheriting` and compare `Acl.isGranted` outcomes. Then add a deny ACE on the child and observe the effect under the real strategy.

**Exercise 5 – Tenant-scoped permissions.** Create two documents sharing numeric ID `101` in tenant A and tenant B. Design non-colliding `ObjectIdentity` and principal IDs, add tenant validation, and test that tenant A users cannot read tenant B data.

**Exercise 6 – Checking ACL administration rights.** Distinguish ACL owner, authorities allowed to modify ACEs, and READ/WRITE rights on domain objects. Test that someone with READ cannot automatically edit the ACL, and someone who can edit the ACL does not automatically gain all business permissions.

**Exercise 7 – Revocation and caching.** Grant READ via `PrincipalSid`, read the ACL once to warm the cache, then delete the ACE with `MutableAclService`. Verify subsequent checks do not continue allowing access from a stale cache.

**Completion criteria:** distinguish personal SIDs from authority SIDs; identify recipient/object/permission/grant completely when reading an ACE; understand `ACL_SID` and `ACL_ENTRY`; recognize when role membership broadens scope; use `Acl.isGranted` instead of manually scanning grant lists; understand impacts of parent links, tenants, caching, unstable identities, and revocation timing.

## Official References

- Spring Security – **Domain Object Security (ACLs)**: https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html
- Spring Security API – **PrincipalSid**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/PrincipalSid.html
- Spring Security API – **GrantedAuthoritySid**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/GrantedAuthoritySid.html
- Spring Security API – **SidRetrievalStrategyImpl**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/SidRetrievalStrategyImpl.html
- Spring Security API – **Acl / isGranted**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html
- Spring Security API – **DefaultPermissionGrantingStrategy**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html
- Spring Security API – **MutableAclService**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAclService.html
