# Spring Security ACL: Sid, ObjectIdentity, Permission, and AccessControlEntry

In a Spring Security Servlet application, users Alice and Bob both have `ROLE_USER`. Checking `hasRole("USER")` confirms that they belong to the user group, but **is not enough to guarantee Alice can read only Alice's documents**. If an API accepts a document ID from the URL and immediately queries and returns it, changing the ID in the URL can lead to **Broken Object Level Authorization (BOLA/IDOR)**.

**Spring Security ACL (Access Control List)** is an authorization model for **individual business objects**, such as individual documents, invoices, tasks, or folders. An ACL lets you express which user or role holds which permissions on a specific object and, where necessary, which permissions are denied.

Four central concepts:

- **Sid (Security Identity):** the subject to whom a permission applies. For example, user `alice` or authority `ROLE_REVIEWER`.
- **ObjectIdentity:** which object is protected. For example, type `com.example.acl.Document`, ID `101`.
- **Permission:** the action to protect, such as READ, WRITE, DELETE, represented as a bit mask.
- **AccessControlEntry (ACE):** a record pairing a Sid and a Permission inside an object's ACL, along with **grant/deny** status, ordering, and audit flags.

ACEs are collected inside an `Acl` object. `AclService` loads ACLs, `MutableAclService` manages ACL data, and `AclPermissionEvaluator` can wire ACL lookups into method security through `hasPermission(...)` expressions.

This lesson belongs to **Resource Authorization**, using **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet**. We will cover concepts, ACL evaluation mechanics, the four-table JDBC schema, granting/revoking permissions, method security, tenant boundaries, caching, inheritance, testing, and a standalone Java 17 example. Spring ACL content in code-fragment form requires the library and persistence configuration; any snippets that are not standalone runnable programs are clearly noted.

**Important limitation:** adding the `spring-security-acl` dependency does not automatically enable object authorization for every URL. The application must create ACLs properly, enforce permission checks on all access paths to protected resources, and resolve discrepancies among object data, tenants, identities, and caches.

## 1. Difference Between Roles and Object Permissions

Consider three documents:

| Resource | Tenant | Owner | Who Can READ? | Who Can WRITE? |
| --- | --- | --- | --- | --- |
| Document#101 | north | alice | alice, auditor per policy | alice |
| Document#102 | north | bob | bob | bob |
| Document#201 | south | carol | carol | carol |

With a general rule:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/**").hasRole("USER")
    .anyRequest().denyAll());
~~~

Alice only needs ROLE_USER to pass the HTTP gate, **regardless of document ID**. If the controller lacks an object-level check, the API has a vulnerability. A policy must verify:

~~~text
1. Is the request authenticated?
2. Does the user belong to the document's tenant?
3. Which action is the user requesting: READ or WRITE?
4. Does Document#101's own ACL grant Permission to the user/role Sid?
5. If there is no valid grant, or data is missing: DENY.
~~~

An ACL can express:

~~~text
Document#101
    PrincipalSid("alice")         READ  GRANT
    PrincipalSid("alice")         WRITE GRANT
    GrantedAuthoritySid("ROLE_AUDITOR") READ GRANT

Document#102
    PrincipalSid("bob")           READ  GRANT
    PrincipalSid("bob")           WRITE GRANT
~~~

ACL is not the only way to solve object-level security. For simple owner-and-tenant policies, database queries constrained by `tenant_id` and `owner_id` may be a better fit. ACLs are useful when **sharing resources with specific individuals, groups, or exception permissions**, and the application is prepared to manage the permission lifecycle.

## 2. Sid — To Whom Does the Permission Apply?

`Sid` is the Security Identity abstraction in ACL. Main implementations:

- `PrincipalSid`: a specific principal, usually a username or server-managed user identifier.
- `GrantedAuthoritySid`: a GrantedAuthority, usually shared by multiple users, such as `ROLE_AUDITOR`.

~~~java
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;

Sid alice = new PrincipalSid("alice");
Sid auditTeam = new GrantedAuthoritySid("ROLE_AUDITOR");
~~~

This is a Java fragment depending on `spring-security-acl`. A Sid differs from a full `Authentication`: Authentication carries principal, credentials/authorities/authenticated status; a Sid is **an identity key suited for an ACE**.

When a user makes a request, the ACL permission evaluator can derive a list of Sids from Authentication:

~~~text
Authentication:
  principal = alice
  authorities = [ROLE_USER, ROLE_AUDITOR]

Derived Sids:
  PrincipalSid("alice")
  GrantedAuthoritySid("ROLE_USER")
  GrantedAuthoritySid("ROLE_AUDITOR")
~~~

**Never trust a client-supplied Sid.** For instance, sending `?user=admin`, `X-Role: ROLE_ADMIN`, or a payload containing `tenantId` does not prove authentication. The subject used for permission checks must come from the identity provider and trusted server-side membership data.

### Usernames and Multi-Tenancy

If usernames can be renamed or collide across tenants, storing Sids by display username is risky. Production should use **unique, durable** identity keys or explicit namespacing/migration rules; identical Sid strings in two tenants could accidentally collide permissions without a tenant boundary.

### PrincipalSid and GrantedAuthoritySid Do Not Replace Each Other

| Sid Type | Scope | Example |
| --- | --- | --- |
| PrincipalSid | Specific individual | alice can READ Document#101 |
| GrantedAuthoritySid | Any Authentication holding this authority | ROLE_REVIEWER can READ Document#101 |

If Bob is granted ROLE_REVIEWER in an active session, Bob can gain access through a role ACE. When an authority is revoked in the identity store, the current Authentication may retain the old authority until refreshed/reauthenticated, unless the application implements real-time revocation.

## 3. ObjectIdentity — Which Object Is Protected?

`ObjectIdentity` carries an **object type (type/class)** and an **ID**:

~~~java
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.domain.ObjectIdentityImpl;

ObjectIdentity document =
    new ObjectIdentityImpl(Document.class, 101L);

ObjectIdentity invoice =
    new ObjectIdentityImpl(Invoice.class, 101L);
~~~

These two identities are distinct despite having the same numeric ID 101. This is a fragment; `Document` and `Invoice` are defined by the application domain.

A common mapping:

~~~text
ObjectIdentity(Document.class, 101L)
    |
    +--> acl_class.class = "com.example.acl.Document"
    |
    +--> acl_object_identity.object_id_identity = "101"
~~~

When refactoring a class's package, changing ID types from Long to UUID, or changing identity serialization, verify ACL migrations. If the database still holds the old type name, permissions may not be found or may apply incorrectly.

### ObjectIdentity in Multi-Tenancy

If two tenants both have `Document#101` with independently generated IDs, using only `Document.class + 101L` can cause an **identity collision**. Design options include globally unique IDs, tenant-namespaced canonical identities, or tenant-separated ACL repositories; regardless of choice, **the tenant boundary must be enforced by business policy**, not merely by role Sids.

## 4. Permission — The Protected Action

`Permission` in Spring ACL typically uses a **bit mask** instead of storing only a String label. `BasePermission` provides common permissions:

| Permission | Mask | Typical Purpose |
| --- | ---: | --- |
| `BasePermission.READ` | 1 | Read |
| `BasePermission.WRITE` | 2 | Edit |
| `BasePermission.CREATE` | 4 | Create |
| `BasePermission.DELETE` | 8 | Delete |
| `BasePermission.ADMINISTRATION` | 16 | Administer per ACL policy |

~~~java
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.domain.BasePermission;

Permission read = BasePermission.READ;
Permission write = BasePermission.WRITE;

System.out.println(read.getMask());  // 1
System.out.println(write.getMask()); // 2
~~~

This is a fragment. A Permission is an **action on an object**, not `ROLE_ADMIN`. `ADMINISTRATION` mask 16 **does not automatically grant** ROLE_ADMIN on all URLs.

**Do not assume WRITE implicitly includes READ.** If business logic requires WRITE users to READ, grant the corresponding ACE or design a PermissionGrantingStrategy expressing inheritance. Do not assume OR-ing bits to 3 forms a composite permission understood identically by every framework configuration; mask matching depends on the actual strategy.

Custom permissions such as EXPORT/APPROVE can use additional non-overlapping masks. For `hasPermission(..., 'EXPORT')` to work, you need a matching `PermissionFactory`/resolver mapping; merely creating a domain enum EXPORT is insufficient.

## 5. AccessControlEntry — Grant or Deny Record

An `AccessControlEntry` (ACE) resides inside an `Acl` and contains:

- `getSid()` — who?
- `getPermission()` — which permission?
- `isGranting()` — grant or deny?
- `getAcl()` — which ACL does it belong to?
- `getId()` — ACE ID if persisted.
- `isAuditSuccess()` / `isAuditFailure()` — audit-related flags.

A sample ACE:

~~~text
ObjectIdentity = (com.example.acl.Document, 101)
Sid            = PrincipalSid("alice")
Permission     = READ (mask=1)
Granting       = true
ACE order      = 0
Audit flags    = per policy
~~~

Important: **ACE grant/deny differs from the ACL owner**. The `owner_sid` field in ACL metadata serves the ACL management model; it does not automatically become a granted READ/WRITE permission in every configuration.

### Structure of an Acl

~~~text
Acl(Document#101)
  ownerSid = PrincipalSid("alice")
  entriesInheriting = false
  parentAcl = null

  Ordered ACEs:
    [0] PrincipalSid("alice")          READ  GRANT
    [1] PrincipalSid("alice")          WRITE GRANT
    [2] GrantedAuthoritySid(ROLE_AUDITOR) READ GRANT
~~~

An ACL also holds the owner, ObjectIdentity, optional parent, and `entriesInheriting` flag.

| Concept | Question |
| --- | --- |
| Sid | Who? |
| ObjectIdentity | Which object? |
| Permission | What action? |
| ACE | Grant or deny for this Sid/Permission on that ACL? |
| Acl | Which ACEs belong to an object, who manages it, and does it inherit? |

## 6. Checking Permissions: From Request to ACE

A GET request for document 101 can flow through:

~~~text
GET /api/documents/101
       |
       v
Spring Security Authentication filter
       | -> Authentication alice / ROLE_USER
       v
AuthorizationFilter: route requires authenticated
       |
       v
Controller -> DocumentService.read(101)
       |
       v
@PreAuthorize("hasPermission(...)") if method security enabled
       |
       v
AclPermissionEvaluator
       |-- ObjectIdentity(Document,101)
       |-- Sids from Authentication
       |-- AclService.readAclById(...)
       |-- Permission READ
       |-- PermissionGrantingStrategy checks ACEs/parent
       |
       +-- ALLOW -> execute method
       +-- DENY / missing ACL -> do not execute method
~~~

**This mechanism requires configuration.** Writing `@PreAuthorize("hasPermission(...)")` alone does not guarantee it queries the ACL store if `PermissionEvaluator` is not wired into method security.

### NotFound and UnloadedSid

`AclService.readAclById(...)` may not find an ACL and throw `NotFoundException`. `Acl.isGranted(...)` may report no matching ACE or insufficiently loaded Sids per contract/implementation. Some lookups can encounter `UnloadedSidException`. In every case lacking proof of permission, never **fall back to allow**.

Distinguish HTTP responses clearly: a server/database failure may need to return 5xx per contract rather than pretending 403, yet **sensitive operations must not execute** when permissions cannot be verified.

### 401, 403, and 404

- Unauthenticated user: HTTP Basic/Bearer typically returns 401; form login may redirect 302 to login.
- Authenticated user lacking ACL permission: typically 403 via method-security exception handling.
- Non-existent resource or existence hidden per policy: may return 404, but must be designed intentionally.
- A 404 from Spring MVC because a route does not exist **does not prove ACL ran**.

## 7. ACE Ordering, Deny, and Inheritance

### ACE Order Can Affect Effective Permissions

Example:

~~~text
[0] PrincipalSid("bob")     READ DENY
[1] ROLE_AUDITOR             READ GRANT
[2] PrincipalSid("alice")   READ GRANT
~~~

If Bob holds ROLE_AUDITOR, he matches both the personal deny ACE and the authority grant ACE. **Never assume** every Spring ACL setup prioritizes deny or prioritizes principal: the outcome depends on `PermissionGrantingStrategy`, how ACEs/permissions/Sids are iterated, and entry ordering. If your policy requires "personal deny always overrides role grant", define and **test conflicts** before deploying.

Entries have positions in the list; `MutableAcl.insertAce(index,...)` can shift ordering. When deleting or updating an entry, never use a stale index without loading and verifying the exact entry.

### Parent ACL and entriesInheriting

A folder's ACL can act as a parent:

~~~text
Folder#10
  ROLE_TEAM_A READ GRANT
       |
       | child entriesInheriting = true
       v
Document#101
  Alice WRITE GRANT
~~~

Actual behavior depends on `parentAcl`, the `entriesInheriting` flag, child entries, the granting strategy, and loaded Sids. Separately test local grant/deny, inherited grant/deny, and ordering conflicts. Never assume parent always overrides child or child always overrides parent.

**Important on deletion:** deleting a parent ACL or moving an object can affect numerous child ACLs. `MutableAclService.deleteAcl(objectIdentity, deleteChildren)` requires an explicit policy; deleting an ACL does not delete the domain object.

## 8. JDBC ACL: Four Relational Tables

Spring ACL JDBC typically uses:

1. `acl_sid` — stores Security Identities (principals/authorities).
2. `acl_class` — stores object types.
3. `acl_object_identity` — each protected object, owner, parent, inheritance.
4. `acl_entry` — each ACE, ordering, mask, grant/deny, audit.

~~~text
acl_sid                      acl_class
  id                           id
  principal                    class
  sid                          |
    |                          |
    +-------------+------------+
                  |
           acl_object_identity
             id
             object_id_class -> acl_class.id
             object_id_identity
             owner_sid -> acl_sid.id
             parent_object -> acl_object_identity.id
             entries_inheriting
                  |
                  v
              acl_entry
                id
                acl_object_identity -> acl_object_identity.id
                ace_order
                sid -> acl_sid.id
                mask
                granting
                audit_success
                audit_failure
~~~

| Field | Meaning |
| --- | --- |
| `acl_sid.principal` | Distinguishes a principal SID from an authority SID |
| `acl_class.class` | Type/class used as ObjectIdentity |
| `acl_object_identity.object_id_identity` | Business object key |
| `acl_object_identity.owner_sid` | ACL owner |
| `acl_object_identity.parent_object` | Parent ACL if any |
| `acl_object_identity.entries_inheriting` | Whether parent ACL is evaluated per policy |
| `acl_entry.ace_order` | Order of the ACE within an ACL |
| `acl_entry.mask` | Permission bit mask |
| `acl_entry.granting` | True for grant, false for deny |
| `acl_entry.audit_success/audit_failure` | Audit metadata per strategy |

### Reference PostgreSQL DDL Example

This is an illustrative schema **for understanding relationships**. Before running migrations on a real project, cross-check the SQL schema and JDBC identity queries for your **pinned Spring Security ACL/DB version**. Some versions/dialects add columns, identity generation settings, or different sequence/query names.

~~~sql
CREATE TABLE acl_sid (
    id BIGSERIAL PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR(255) NOT NULL,
    CONSTRAINT uq_acl_sid UNIQUE (principal, sid)
);

CREATE TABLE acl_class (
    id BIGSERIAL PRIMARY KEY,
    class VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE acl_object_identity (
    id BIGSERIAL PRIMARY KEY,
    object_id_class BIGINT NOT NULL
        REFERENCES acl_class(id),
    object_id_identity VARCHAR(255) NOT NULL,
    parent_object BIGINT
        REFERENCES acl_object_identity(id),
    owner_sid BIGINT REFERENCES acl_sid(id),
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_object UNIQUE
        (object_id_class, object_id_identity)
);

CREATE TABLE acl_entry (
    id BIGSERIAL PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL
        REFERENCES acl_object_identity(id),
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL REFERENCES acl_sid(id),
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_ace_order
        UNIQUE (acl_object_identity, ace_order)
);
CREATE INDEX idx_acl_entry_object
    ON acl_entry (acl_object_identity);
CREATE INDEX idx_acl_entry_sid
    ON acl_entry (sid);
~~~

You must also review generated key queries, `AclAuthorizationStrategy`, parent FKs, collations, ID lengths, migrations on class renames, tenant partitioning, transactions/locking, and cache invalidation. Do not treat this SQL DDL as a guarantee that `JdbcMutableAclService` will run immediately on every PostgreSQL/schema version.

### Never Edit ACLs Ad-Hoc via a SQL Client

When `MutableAclService` is available, use it to create ObjectIdentity, bind Sids, manage entries, and update caches. Editing `acl_entry` directly while forgetting caches or ordering can cause new requests to continue using stale authorization decisions. Data migrations require a maintenance plan, invalidation, and verification.

## 9. Spring ACL APIs to Know

Reference imports:

~~~java
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.AccessControlEntry;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.model.Permission;

import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
~~~

### Reading an Acl

~~~java
// Fragment: aclService is an injected Spring bean.
ObjectIdentity identity =
    new ObjectIdentityImpl(Document.class, 101L);

Acl acl = aclService.readAclById(identity);
System.out.println(acl.getEntries().size());
~~~

If no ACL record exists, the service may throw NotFoundException; never return `true` because a record is missing.

### Checking with Acl.isGranted

~~~java
// Fragment with valid acl and authentication variables.
Sid alice = new PrincipalSid(authentication);
Sid auditor = new GrantedAuthoritySid("ROLE_AUDITOR");

boolean granted = acl.isGranted(
    java.util.List.of(BasePermission.READ),
    java.util.List.of(alice, auditor),
    false
);
~~~

Real applications must consider **all trusted authorities on Authentication** rather than hardcoding ROLE_AUDITOR; handle missing ACL / NotFound / UnloadedSid and tenant boundaries. The final parameter `administrativeMode` is not a switch to "turn on admin rights". For normal requests, pass false per standard contract.

### Creating an ACL and Granting READ/WRITE

~~~java
// Fragment inside a transactional Spring service.
// mutableAclService is a bean, Document.class is the real type.
ObjectIdentity identity =
    new ObjectIdentityImpl(Document.class, 101L);

MutableAcl acl = mutableAclService.createAcl(identity);
Sid alice = new PrincipalSid("alice");

acl.insertAce(acl.getEntries().size(),
              BasePermission.READ, alice, true);
acl.insertAce(acl.getEntries().size(),
              BasePermission.WRITE, alice, true);

mutableAclService.updateAcl(acl);
~~~

**Do not treat createAcl as an upsert.** If the identity already has an ACL, create can fail; business code must manage lifecycle and idempotency. A new ACL also needs an appropriate owner SID, transaction, and rules governing who can manage the ACL.

### Granting to a Role

~~~java
Sid reviewers = new GrantedAuthoritySid("ROLE_REVIEWER");
acl.insertAce(acl.getEntries().size(),
              BasePermission.READ, reviewers, true);
mutableAclService.updateAcl(acl);
~~~

A role ACE applies to users holding that authority per SidRetrievalStrategy. Never put a global `ROLE_ADMIN` into a multi-tenant ACL assuming "any tenant admin is in scope"; verify tenant separately.

### Revoking by Deleting an ACE

~~~java
// Fragment: index is determined after inspecting the exact
// Sid + Permission + grant/deny of the current ACL.
acl.deleteAce(index);
mutableAclService.updateAcl(acl);
~~~

Never delete `index=0` assuming entry 0 will always be Alice. Entry order can change. Locate the exact SID/mask and verify effective permissions **after** the change, including role grants or parent inheritance.

### Deleting an Object's ACL

~~~java
ObjectIdentity identity =
    new ObjectIdentityImpl(Document.class, 101L);

mutableAclService.deleteAcl(identity, false);
~~~

This deletes ACL data per implementation/child-policy, not the business Document record. Define `deleteChildren` semantics and parent-child relationships. When an object is deleted, clean up its ACL to avoid orphans or reused IDs inheriting stale permissions.

## 10. Connecting Spring Security ACL with hasPermission

A common method-security expression:

~~~java
@PreAuthorize(
    "hasPermission(#id, 'com.example.acldemo.Document', 'READ')")
public Document read(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

This is a **fragment**, requiring a Spring-managed bean, `@EnableMethodSecurity`, annotation imports, and a PermissionEvaluator bean. The type string must **match the ObjectIdentity type** used when creating the ACL; if a class package changes without migration, ACL lookups can fail.

### MethodSecurityExpressionHandler

A Spring Security 6.x configuration:

~~~java
package com.example.acldemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.model.AclService;

@Configuration
@EnableMethodSecurity
public class AclMethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclService aclService) {

        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(
            new AclPermissionEvaluator(aclService));
        return handler;
    }
}
~~~

This class requires version-matched dependencies and a **fully wired AclService bean**; it is not a standalone application. It wires `hasPermission(...)` to ACL lookups. In Spring Security 6, pre/post method security is enabled by default with `@EnableMethodSecurity`; `@Secured` and Jakarta `@RolesAllowed` have separate flags and are **not the focus of ACL**.

### Two Forms of PermissionEvaluator

~~~java
// PermissionEvaluator contract, condensed form:
boolean hasPermission(Authentication authentication,
                      Object targetDomainObject,
                      Object permission);

boolean hasPermission(Authentication authentication,
                      java.io.Serializable targetId,
                      String targetType,
                      Object permission);
~~~

The `id + type` form is clear when a controller only has the Document ID. The object form relies on IdentityRetrievalStrategy and object type/id extraction; do not use it without configuring and testing it properly.

### What Does Persistence Configuration Require?

Beyond the DataSource/JDBC schema, you typically need:

~~~text
DataSource
  + AclCache
  + PermissionGrantingStrategy
  + AclAuthorizationStrategy
  + LookupStrategy (e.g., BasicLookupStrategy)
       |
       + JdbcAclService / JdbcMutableAclService
                  |
                  + AclPermissionEvaluator
                         |
                         + MethodSecurityExpressionHandler
~~~

Common implementations: `BasicLookupStrategy`, `JdbcAclService`, `JdbcMutableAclService`, `DefaultPermissionGrantingStrategy`, `AclAuthorizationStrategyImpl`. This is a **bean graph diagram**, not a promise that they are auto-configured solely by adding a dependency. Wire them appropriately for your cache, audit logger, JDBC identity queries, and SQL dialect.

### Typical Maven Dependencies

In a Spring Boot 3.x project with a suitable parent/BOM:

~~~xml
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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-acl</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
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
~~~

Add a JDBC driver and version-compatible schema/configuration. Spring files require the framework classpath; only the pure-JDK program in Section 15 runs with Java 17 alone.

## 11. Service Layer Example: Reading an ACL-Protected Document

A domain record:

~~~java
package com.example.acldemo;

public record Document(long id, String title) {}
~~~

A service with method security, demonstrating immutable data:

~~~java
package com.example.acldemo;

import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final Map<Long, Document> data = Map.of(
        101L, new Document(101L, "Project plan"),
        102L, new Document(102L, "Meeting notes")
    );

    @PreAuthorize(
        "hasPermission(#documentId, 'com.example.acldemo.Document', 'READ')")
    public Document readDocument(long documentId) {
        Document doc = data.get(documentId);
        if (doc == null) {
            throw new IllegalArgumentException("Document missing");
        }
        return doc;
    }
}
~~~

Execution prerequisites:

1. ACLs for Document#101 / Document#102 must be created and stored in the ACL service; a Map holding Documents **does not create ACLs automatically**.
2. `@EnableMethodSecurity` is enabled, and the expression handler uses the ACL evaluator.
3. `#documentId` must resolve from the Java method parameter name or corresponding annotation mapping; verify compiler `-parameters` and build configuration.
4. Callers must go through the Spring method-security proxy. Calling `this.readDocument(...)` inside the same service can bypass interception.
5. The demo uses an immutable Map; with a concurrently modified DB, handle TOCTOU and transactions.
6. If sensitive data belongs to tenants, the method/policy must verify the tenant boundary independently rather than assuming an ACL role string is tenant-scoped.

A controller outside the service:

~~~java
// Fragment inside @RestController with injected DocumentService service.
@GetMapping("/api/documents/{id}")
public Document get(@PathVariable long id) {
    return service.readDocument(id);
}
~~~

If HTTP security lets the request through but method ACL denies it, the request **must not return the document**. Test both a granted user and a non-granted user on **the same real object**. Never test only that a non-existent route returns 404.

### Proxy and Self-Invocation Limitations

~~~java
@Service
class UnsafeService {
    public Document outer(long id) {
        return this.protectedRead(id); // usually bypasses the Spring proxy
    }

    @PreAuthorize("hasPermission(#id, 'com.example.acldemo.Document', 'READ')")
    public Document protectedRead(long id) {
        // ...
        throw new UnsupportedOperationException();
    }
}
~~~

This is a risk example, not a production service. If an unprotected method calls a protected method via `this`, the Spring AOP proxy may not intercept it. To prevent bypasses, move the protected service into another bean, constructor-inject it, and test real invocations. Never assume annotations on private/static/final methods behave like public methods through a proxy.

## 12. Resource Sharing and Revocation Lifecycle

### Creating a Document

~~~text
Alice authenticated -> requests CREATE document in tenant north
  1. Business service checks CREATE policy and tenant.
  2. Transaction creates Document#101.
  3. Create ObjectIdentity(Document, 101).
  4. Create ACL with trusted owner SID.
  5. Insert READ/WRITE GRANT for Alice per product policy.
  6. Commit both domain data and ACL, or use a reconciliation mechanism.
  7. Verify Alice can READ and Bob cannot READ.
~~~

If ACL persistence fails after the document already exists, **never expose the object before its ACL is provisioned**. If the domain DB and ACL store do not share a transaction, use an outbox/saga and default pending/deny state.

### Sharing a Document with Bob

When Alice wants to grant Bob READ:

- Authenticate Alice.
- Verify Alice actually holds permission to **manage sharing/ACL**, not merely READ.
- Load the Document and verify the grantor's and recipient's tenants.
- Identify Bob via a server-side user identifier, not merely trusting a payload username.
- Read the current ACL, insert ACE `PrincipalSid("bob"), READ, GRANT`, avoiding duplicates/conflicts.
- Update the ACL in a transaction and invalidate caches.
- Verify Bob can READ and still cannot WRITE.

**Never let a READ-only user grant themselves ADMINISTRATION or edit someone else's ACL.** Separate object-action permissions from permission-management rights. `AclAuthorizationStrategy` plays a role in ACL administration; business permissions for sharing/revoking must still be explicit.

### Revoking Permissions

To revoke Bob's READ:

1. Authorize the actor performing the revocation.
2. Locate the exact ACE by Sid and Permission in the current ACL.
3. Delete/update the ACE and save via `MutableAclService.updateAcl`.
4. Invalidate caches and broadcast events to other nodes if needed.
5. Ensure Bob has no remaining grant via a role SID or parent inheritance.
6. Issue a new request as Bob and confirm denial.

**Deleting a single ACE does not guarantee effective access is revoked.** Another role ACE may still grant access. Test effective permissions rather than merely asserting a database row was deleted.

### Transferring Ownership

When a document transfers Alice → Bob, handle separately: owner in the domain record, ACL owner_sid, old/new READ/WRITE ACEs, tenant membership, inherited entries, and auditing/caches. `MutableAcl.setOwner(newSid)` (when used by the API/implementation) **does not automatically transfer all grant entries** per business contracts.

## 13. Multi-Tenancy, SID, and ObjectIdentity Collisions

Suppose two tenants both have document ID 101 and a user named Alice. If the application uses:

~~~text
ObjectIdentity = (Document, 101)
Sid = PrincipalSid("alice")
~~~

the two identities can collide without global namespacing. Similarly, `GrantedAuthoritySid("ROLE_ADMIN")` can represent admin across **every tenant**, not one specific tenant.

**Safe design:**

- Use globally unique document IDs or tenant-scoped canonical ObjectIdentities.
- Use immutable principal IDs or proper Sid namespacing.
- Check tenant membership from trusted identity/DB sources independently of ACL.
- Avoid granting a global ROLE_ADMIN READ on all documents if the role is really tenant-admin.
- Test users with the same role across different tenants, colliding local IDs, and owner transfers.

Sample rule:

~~~text
ALLOW =
    user is authenticated
    AND trustedUserTenant == trustedResourceTenant
    AND ACL grants requested Permission for trusted Sids
~~~

Never write `sameTenant OR ACLgrants` if tenant isolation is mandatory; the OR branch lets a global role grant cross tenants. If a product has cross-tenant superadmins, enforce dedicated policies, logging, approvals, and tests—never infer it from ROLE_ADMIN.

## 14. Caching, Inheritance, and Consistency

### Caching ACLs

Caching reduces queries, but **stale permissions** are a security issue:

- Node A calls `updateAcl`; Node B still holds the old ACL in cache.
- A script updates `acl_entry` directly and forgets cache eviction.
- Parent ACL changes while children still inherit old cached grants.
- Authentication still carries authorities revoked externally in the identity provider.

The application needs a caching strategy aligned with `AclService`/`MutableAclService`, cross-node invalidation, TTL/revocation SLAs, and tests. Never cache `allowed=true` keyed solely by ObjectIdentity without principal/permission/tenant/policy version; that creates cross-user permission leaks.

### N+1 ACL Lookups

An API returning 100 documents that calls DB ACL per item can incur N+1 queries. Use batch ACL lookups or query-level filtering by permission/tenant where appropriate while keeping pagination accurate. Never load out-of-scope documents and hide them in the browser: data already leaked in the response.

### Time-of-Check / Time-of-Use

~~~text
T1: Alice passes ACL READ for Document#101
T2: Admin revokes Alice's READ
T3: Service reads Document#101 and returns response
~~~

This can be TOCTOU. For sensitive operations, enforce checks close to data access/commit, use transactions/isolation, permission versions, or suitable consistency mechanisms. `@PreAuthorize` **does not automatically combine every ACL lookup and document query into a single atomic transaction**.

### Parent Inheritance

When a parent ACL grants access and child `entriesInheriting=true`, verify how local ACE grants/denies interact with inherited entries under your strategy. Deleting a parent or changing group permissions can alter child access. Do not treat inheritance as a simple OR of grants, as that can ignore local denies.

## 15. Standalone Java 17: Four Objects Collaborating on a Decision

The following program **runs with JDK 17 alone**. It models Sid, ObjectIdentity, Permission, and ACE using Java records, plus an `ObjectAcl`. Example policy: scan entries in order, take the first entry matching Sid and mask; missing entry or tenant mismatch yields DENY.

**This is not a full replica of Spring Security ACL's DefaultPermissionGrantingStrategy.** It illustrates connecting the four objects and an **explicitly defined strategy for the demo**. In real Spring ACL, conflict/ordering/inheritance must be tested against your configured PermissionGrantingStrategy.

Save file `AclFourObjectsDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AclFourObjectsDemo {
    static final int READ = 1;
    static final int WRITE = 2;

    record ObjectIdentity(String type, long id) {}
    record Sid(String value) {}
    record Permission(int mask, String name) {}
    record AccessControlEntry(
        Sid sid, Permission permission, boolean granting) {}
    record ObjectAcl(
        ObjectIdentity identity,
        String tenant,
        List<AccessControlEntry> entries) {}

    static boolean allowed(
            ObjectAcl acl,
            String principal,
            String userTenant,
            Set<String> authorities,
            Permission requested) {

        if (acl == null || principal == null ||
                userTenant == null || requested == null ||
                !userTenant.equals(acl.tenant())) {
            return false;
        }

        Sid principalSid = new Sid("P:" + principal);
        for (AccessControlEntry ace : acl.entries()) {
            boolean userMatch = ace.sid().equals(principalSid);
            boolean roleMatch = ace.sid().value().startsWith("R:")
                && authorities.contains(
                    ace.sid().value().substring(2));
            boolean permissionMatch =
                (ace.permission().mask() & requested.mask())
                    == requested.mask();

            if ((userMatch || roleMatch) && permissionMatch) {
                return ace.granting();
            }
        }
        return false;
    }

    static String label(boolean value) {
        return value ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Permission read = new Permission(READ, "READ");
        Permission write = new Permission(WRITE, "WRITE");
        ObjectIdentity id =
            new ObjectIdentity("Document", 101L);

        ObjectAcl acl = new ObjectAcl(id, "north", List.of(
            new AccessControlEntry(
                new Sid("P:bob"), read, false),
            new AccessControlEntry(
                new Sid("P:alice"), read, true),
            new AccessControlEntry(
                new Sid("R:ROLE_AUDITOR"), read, true),
            new AccessControlEntry(
                new Sid("P:bob"), write, true)
        ));

        Map<ObjectIdentity, ObjectAcl> aclStore =
            Map.of(id, acl);

        System.out.println("alice READ: " + label(
            allowed(acl, "alice", "north",
                Set.of("ROLE_USER"), read)));
        System.out.println("bob READ: " + label(
            allowed(acl, "bob", "north",
                Set.of("ROLE_AUDITOR"), read)));
        System.out.println("auditor READ: " + label(
            allowed(acl, "carol", "north",
                Set.of("ROLE_AUDITOR"), read)));
        System.out.println("bob WRITE: " + label(
            allowed(acl, "bob", "north",
                Set.of("ROLE_USER"), write)));
        System.out.println("alice WRITE: " + label(
            allowed(acl, "alice", "north",
                Set.of("ROLE_USER"), write)));
        System.out.println("cross-tenant READ: " + label(
            allowed(acl, "carol", "south",
                Set.of("ROLE_AUDITOR"), read)));

        ObjectIdentity missing =
            new ObjectIdentity("Document", 999L);
        System.out.println("unknown object READ: " + label(
            allowed(aclStore.get(missing), "alice", "north",
                Set.of("ROLE_USER"), read)));
    }
}
~~~

Compile and run:

~~~bash
javac AclFourObjectsDemo.java
java AclFourObjectsDemo
~~~

**Exact** stdout:

~~~text
alice READ: ALLOW
bob READ: DENY
auditor READ: ALLOW
bob WRITE: ALLOW
alice WRITE: DENY
cross-tenant READ: DENY
unknown object READ: DENY
~~~

Why is Bob READ DENY despite having ROLE_AUDITOR? The model uses first-match ordering and Bob's personal READ DENY ACE comes before the role grant. This is the behavior **of the demo program**, not a guarantee about every Spring ACL strategy.

Why is Bob WRITE ALLOW? A dedicated WRITE grant ACE matches Bob, whereas the READ deny ACE has a different mask; the demo evaluates permissions independently.

Why is Alice WRITE DENY? There is no WRITE grant ACE for Alice; missing grant yields deny.

Why is cross-tenant READ DENY? The tenant check applies before ACEs. In a real product, tenant must come from trusted data, not from a client-submitted String.

## 16. Testing Spring Security ACL

Three testing layers:

1. **Policy unit tests:** Sid/principal, authority SID, masks, deny/grant, ordering, missing ACL.
2. **JDBC integration:** schema, MutableAclService create/update/delete, lookup, owner, cache invalidation, inheritance.
3. **HTTP/method security integration:** requests passing through authentication filters, controller/service proxy, and real `AclPermissionEvaluator`; 200, 401, 403/404 per contract.

### Test Matrix

| User | Document | Permission | ACL/Setup | Expected |
| --- | --- | --- | --- | --- |
| alice | 101 | READ | Grant Alice READ | Allow |
| bob | 101 | READ | No grant for Bob | Deny |
| bob | 101 | READ | Grant Bob READ | Allow |
| bob | 101 | WRITE | Grant READ only | Deny |
| auditor | 101 | READ | Grant ROLE_AUDITOR | Allow |
| user with role+principal conflict | 101 | READ | Explicit deny + role grant | Per verified strategy |
| alice | 999 | READ | ObjectIdentity has no ACL | Deny/fail closed |
| south tenant admin | north doc | READ | Role grant but different tenant | Deny |
| member | child | READ | Parent grant, inheriting on | Per inheritance policy |
| member | child | READ | Parent grant, inheriting off | Deny without local grant |
| bob after revoke | 101 | READ | ACE deleted, cache invalidated | Deny |
| anonymous | 101 | READ | No Authentication | Deny/entry point |

### Testing Service Bean via @WithMockUser

~~~java
// Fragment in @SpringBootTest with DocumentService bean and ACL fixtures.
// Requires @EnableMethodSecurity and proper AclPermissionEvaluator.
@Autowired DocumentService documents;

@Test
@WithMockUser(username = "alice", roles = "USER")
void ownerCanRead() {
    Document d = documents.readDocument(101L);
    assertEquals(101L, d.id());
}

@Test
@WithMockUser(username = "bob", roles = "USER")
void otherUserCannotRead() {
    assertThrows(
        org.springframework.security.access.AccessDeniedException.class,
        () -> documents.readDocument(101L));
}
~~~

Requires JUnit/Spring Security Test imports, seeded Alice READ ACL, and no grant for Bob. This fragment **cannot run by itself** without an AclService bean, DB schema, ACL fixtures, and method-security expression handler.

`@WithMockUser` does not prove real authentication; it provides a trusted mock principal **in tests** to verify permissions. For end-to-end tests, use real HTTP Basic/form login/Bearer through MockMvc against an object with a real ACL.

### Testing with MockMvc

~~~java
// Integration fragment with SpringBootTest + AutoConfigureMockMvc,
// with httpBasic users and prepared ACL fixtures.
mvc.perform(get("/api/documents/101")
        .with(httpBasic("alice", "demo-password")))
    .andExpect(status().isOk());

mvc.perform(get("/api/documents/101")
        .with(httpBasic("bob", "demo-password")))
    .andExpect(status().isForbidden());
~~~

Status 403 depends on the app entry point/error handling. Most importantly, use **the exact same real resource**, grant one principal, and deny another. A GET to a URL with no controller returning 404 does not prove ACL is working.

### Testing Revocation, Inheritance, and Caching

After granting Bob READ, test that Bob can read; delete the ACE, update the ACL, and test that Bob is denied on a new request. If using multiple nodes, test from a node that did not directly write the ACL. Also test when Bob holds another role READ grant: revoking only the principal ACE may not suffice; test real effective access.

With inheritance, test all combinations of child grant/deny, parent grant/deny, and entriesInheriting true/false. With a role hierarchy, verify whether the evaluator receives Sids from expanded authorities and whether role hierarchy applies in the SID retrieval layer; do not infer it solely from `hasRole`.

### Performance Testing

For GET lists, test more than single-object permissions. Measure ACL query counts, batch lookups, pagination, and database-level filtering. Never render/return out-of-scope documents and merely hide them in JavaScript.

## 17. Distinguishing Authorization Mechanisms

| Tool | Level | When Useful |
| --- | --- | --- |
| `authorizeHttpRequests(...).hasRole(...)` | HTTP URL/method | Gate for an entire endpoint group |
| `@PreAuthorize("hasRole(...)")` | Service method call | Static roles |
| `@PreAuthorize("hasPermission(...)")` | Method + domain object | Per-resource ACL |
| Custom `AuthorizationManager<RequestAuthorizationContext>` | HTTP request context | Complex rules before the controller |
| Business policy + repository condition | Data and transaction | Owner/tenant, consistency, filtering |
| Spring Security ACL/JDBC | Persistent per-object ACLs | Individual/group sharing, multi-object grant/revoke |

Do not mix role-only checks with object ACLs assuming one automatically compensates for the other. For instance, `ROLE_ADMIN` on an API filter only proves a role; it does not mean the user has READ on every object and every tenant.

### Why Can an HTTP Request Still Be Blocked Without an ACL Grant?

Because enforcement may run on the service method rather than the URL matcher. A request can pass the HTTP layer yet be rejected by the method-security interceptor before the service returns data. Conversely, if a service is invoked outside HTTP and bypasses proxies/policies, ACLs may **not be evaluated at all**.

## 18. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Checking only ROLE_USER for all objects | IDOR/BOLA | ACL/owner/tenant checks |
| Taking Sid from client parameter | Sid spoofing | Trusted Authentication and identity store |
| ObjectIdentity with ID only, no type | Cross-domain object confusion | Canonical Type + ID |
| Tenants with colliding local IDs | ACL collisions | Global IDs or namespaced identities |
| Renaming class package without migrating ACL | Lookup miss | Migrate acl_class/identity |
| Treating owner_sid as READ/WRITE | Wrong permissions | Explicit ACE/policy |
| Assuming WRITE implies READ | Missing/excess grants | Test per-permission |
| Treating ADMINISTRATION as ROLE_ADMIN | Mixing permissions and roles | Separate models |
| Ignoring ACE order/strategy | Grant/deny conflicts | Test conflicts and real strategy |
| Forgetting to set AclPermissionEvaluator | hasPermission ignores ACLs | Configure expression handler |
| Creating ACL without updateAcl | ACEs not persisted | MutableAclService.updateAcl |
| Revoking by hardcoded index | Deletes wrong entry | Look up by SID/mask |
| Revoking principal entry while role grant remains | Access still works | Test effective ACL |
| Returning allow on ACL DB error | Fail-open | Fail closed, proper error contract |
| Delayed ACL provisioning | Object exposed during gap | Transaction/pending-deny |
| Editing acl_entry directly without clearing cache | Stale permissions | Invalidation/reconciliation |
| Skipping ACL on list endpoints | Bulk record leak | Query-level filtering |
| @PreAuthorize self-call `this.method()` | Proxy bypass | Separate bean, test call paths |
| Method authz missing on queues/cron | HTTP bypass | Policy at service boundary |
| Caching allow by ObjectIdentity alone | Cross-user leakage | Principal/permission/tenant-aware cache |
| Testing only admin returning 200 | Does not prove denial | Test positive + negative on same object |

## 19. Self-Check Exercises

**Exercise 1.** Alice and Bob both have ROLE_USER, yet Document#101 belongs only to Alice. Why is hasRole USER insufficient?

**Answer:** It only checks a general role; Document#101 requires object-level READ permission or a trusted owner/tenant rule.

**Exercise 2.** How does `PrincipalSid("alice")` differ from `GrantedAuthoritySid("ROLE_USER")`?

**Answer:** One identifies a single principal; the other represents an authority that multiple principals can hold simultaneously.

**Exercise 3.** Do Document#101 and Invoice#101 share the same ObjectIdentity?

**Answer:** No, when their types differ. Identity combines type/class and ID so ACL domains never collide.

**Exercise 4.** What are the default masks for READ and WRITE?

**Answer:** READ=1, WRITE=2. Other permissions are CREATE=4, DELETE=8, ADMINISTRATION=16 per BasePermission.

**Exercise 5.** What does ACE `alice, READ, granting=false` mean?

**Answer:** Deny READ for principal Alice on that ACL. If Alice also matches a role grant, the effective result must be checked against ordering and PermissionGrantingStrategy.

**Exercise 6.** Does the ACL owner automatically get READ/WRITE?

**Answer:** Not identically by default. ACL owner governs ACL administration; object actions require explicit policies/ACEs.

**Exercise 7.** Is writing `@PreAuthorize("hasPermission(...)")` enough for Spring ACL JDBC to work?

**Answer:** No. You need method security enabled, AclPermissionEvaluator, AclService/LookupStrategy, JDBC schema, ACL records, and bean wiring.

**Exercise 8.** Should a missing ACL return allow?

**Answer:** No. Fail closed or fall back to an explicitly designed and tested business policy.

**Exercise 9.** Why can renaming the Document class cause ACL lookups to fail?

**Answer:** ObjectIdentity type typically maps to acl_class; the class/type string changes while legacy DB ACL identities remain unmigrated.

**Exercise 10.** Bob has a principal READ deny and a role READ grant. What does the result depend on?

**Answer:** PermissionGrantingStrategy, ACE ordering, and SID matching. Never assume deny or role always wins by default.

**Exercise 11.** Deleting Bob's principal READ ACE still lets Bob read. Why?

**Answer:** There may still be a role SID grant, parent inheritance, another ACE, or a stale cache. Inspect the effective decision.

**Exercise 12.** A north admin gets a role grant for READ on a south document. What if policy forbids cross-tenant access?

**Answer:** It must be denied by an independent tenant boundary, never treating a global role grant as cross-tenant access.

**Exercise 13.** A service method has an ACL check, yet a method in the same bean calls `this.method()`. What is the risk?

**Answer:** Self-invocation can bypass the Spring AOP proxy, causing the method-security annotation not to run.

**Exercise 14.** Creating the document succeeds, but creating the ACL fails. What is the safe handling?

**Answer:** Roll back if in the same transaction; otherwise keep the document inaccessible/pending and reconcile rather than exposing it publicly.

**Exercise 15.** What happens if GET list loads 10,000 documents and calls ACL per row?

**Answer:** N+1 queries, poor performance, broken pagination, and leak risks. Use ACL-aware queries/batch strategies and tenant filters.

**Exercise 16.** Node B still grants access after revocation on Node A. What is the first investigation step?

**Answer:** Check ACL cache invalidation, distributed sync, remaining parent/role grants, and whether updateAcl committed.

**Exercise 17.** Does an HTTP 404 because no controller exists prove ACL works?

**Answer:** No. You must test the same real object with both a granted principal and an ungranted principal.

**Exercise 18.** Does the ADMINISTRATION mask automatically turn a user into ROLE_ADMIN for all APIs?

**Answer:** No. One is an ACL Permission; the other is a GrantedAuthority; any link exists only if explicitly designed by business policy.

## 20. Pre-Deployment Checklist

- [ ] Genuine need for per-object sharing; do not use ACL merely to replace a simple owner condition.
- [ ] Clear understanding of Sid, ObjectIdentity, Permission, ACE, and Acl.
- [ ] Principal/authority Sids come from verified Authentication or a trusted identity store.
- [ ] ObjectIdentity type + ID are canonical, with no cross-tenant/domain collisions.
- [ ] Permission masks are stable; never assume WRITE implies READ.
- [ ] GRANT/DENY rules, ACE ordering, and inheritance are tested under the actual strategy.
- [ ] ACL owner/management is separated from business READ/WRITE permissions.
- [ ] Schema acl_sid/acl_class/acl_object_identity/acl_entry matches the Spring ACL JDBC version and database.
- [ ] AclService, MutableAclService, LookupStrategy, AclCache, and AclAuthorizationStrategy are wired properly.
- [ ] When using hasPermission, @EnableMethodSecurity and AclPermissionEvaluator are configured and tested.
- [ ] Spring-managed services are invoked through proxies without self-invocation bypasses.
- [ ] ACL provisioning and domain object creation use fail-closed transactions/reconciliation.
- [ ] Sharing/revoking ACLs requires proper ACL management rights; no arbitrary privilege escalation.
- [ ] Revocation checks all Sid grants and inherited rights, not just one ACE.
- [ ] Tenant membership is verified separately when role SIDs have broad scope.
- [ ] Missing ACLs, unknown Sids/permissions, and DB errors never result in allow.
- [ ] Same object is tested with owner/non-owner, READ/WRITE, anonymous, cross-tenant, and conflict cases.
- [ ] Post-revocation cache invalidation/propagation is tested across nodes if deployment requires.
- [ ] Collection APIs filter permissions server-side with sound pagination and performance.
- [ ] Never log raw session IDs, passwords, JWTs, or sensitive document contents in ACL audits.

**Conclusion:** Spring Security ACL models authorization via **Sid (who) + ObjectIdentity (which object) + Permission (which action) + AccessControlEntry (grant or deny)**. Acl aggregates entries and metadata; AclService/MutableAclService handle lookup/management; PermissionEvaluator connects them to method security. Truly protecting resources requires maintaining proper ACL lifecycles, tenant boundaries, caching, proxy invocations, and grant/revoke tests **on the actual business objects**.