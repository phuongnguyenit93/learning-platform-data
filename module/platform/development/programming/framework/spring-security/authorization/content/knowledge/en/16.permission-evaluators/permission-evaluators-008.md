# Ownership, Sharing, and Administrative Permissions with Spring Security PermissionEvaluator

## 1. The problem: one document, three distinct access paths

Suppose an application manages documents across multiple tenants. Document `101` belongs to tenant `t1` and was created by `alice`. Alice can read, edit, share, or delete the document; Bob may only view it if Alice shares it at the `VIEWER` level; a `TENANT_ADMIN` can administer documents within their assigned tenant, yet does not automatically gain access in another tenant.

These three permission sources are **different**:

1. **Ownership**: who owns the **specific record**.
2. **Sharing / ACL**: other users or groups granted an access level on the **specific record**.
3. **Administrative privilege**: expanded rights within a **defined scope** (tenant/project/organization or system-wide).

A simple check such as:

```java
@PreAuthorize("hasAuthority('document:edit')")
public Document rename(Long documentId, String title) {
    // ...
}
```

is a **method snippet**, not a standalone application. It only asks whether the user holds the `document:edit` authority; it does not know which document the user is editing, whether they are the owner, whether it was shared with them, or whether they belong to the right tenant. When per-record authorization is required, you need an **object-level authorization decision**.

Spring Security provides `PermissionEvaluator` to perform this decision through `hasPermission(...)` in Method Security expressions. This lesson builds an explicit policy for owners, share recipients, and tenant admins, explains common vulnerabilities, and includes a testable Spring Boot + Java 17 example.

**Key takeaway to remember:** holding `ROLE_ADMIN` or `document:edit` does not mean permission to edit every record. Policy must establish **object, action, identity, scope, and trusted data sources**.

## 2. Permission model and decision matrix

### 2.1. Resources and principals

Assume the domain has:

```text
Document:
  id         : 101
  tenant     : t1
  owner      : alice
  title      : "Alice draft"

Membership:
  t1: alice, bob, manager1
  t2: carol, dave, manager2

Access grants (per document):
  document_id | username | access_level
  101         | bob      | VIEWER

Authentication:
  alice    → authority tenant:t1
  bob      → authority tenant:t1
  manager1 → authorities tenant:t1, ROLE_TENANT_ADMIN
```

This is **illustrative data**, not mandatory Spring Security table names or token formats. In real systems, membership, owner, and grants must come from verified server-side sources; never accept client-declared owner/role data and use it to grant access.

For a document, we define two sharing levels:

- `VIEWER`: allowed to **read**.
- `EDITOR`: allowed to **read** and **edit**.

Share recipients are not automatically granted `share`, `revoke`, or `delete`. Only the owner or an administrator in the right tenant may manage those actions. This is the **example's** policy, not an immutable Spring Security rule.

### 2.2. Explicit decision matrix

| Principal category in matching tenant | Read | Edit | Share | Revoke | Delete |
|---|---:|---:|---:|---:|---:|
| Document owner | Yes | Yes | Yes | Yes | Yes |
| Shared as `VIEWER` | Yes | No | No | No | No |
| Shared as `EDITOR` | Yes | Yes | No | No | No |
| `ROLE_TENANT_ADMIN` | Yes | Yes | Yes | Yes | Yes |
| Tenant member **without** document permission | No | No | No | No | No |
| User in another tenant or not in trusted directory | No | No | No | No | No |

The matrix assumes **both** tenant conditions hold: the username is a tenant member in the server-side directory and `Authentication` holds the matching `tenant:<tenantId>` authority. If either condition is missing, the outcome is deny—even if the user holds `ROLE_TENANT_ADMIN` or appears in the share table.

**Why check both conditions?** The example uses the `tenant:t1` authority to verify the scope was placed into `Authentication`, while also checking the directory to prevent stale or mis-mapped token authorities. A real application may choose a different source of truth, provided it clearly specifies how memberships are granted, updated, and revoked.

### 2.3. Combined rule

Expressed as a formula:

```text
allowed(user, document, action)
  = authenticated(user)
  AND activeTenantMembership(user, document.tenant)
  AND tenantAuthorityMatches(user, document.tenant)
  AND (
       isOwner(user, document) AND action ∈ ownerActions
       OR isTenantAdmin(user, document.tenant) AND action ∈ adminActions
       OR sharedLevel(user, document) permits action
  )
```

This is a **logical model**, not runnable Spring syntax. Exceptions or nulls at security check points must never turn into allow. An explicit `false` (fail-closed) is the safe choice when action, resource type, id, or membership is invalid.

### 2.4. Administrative privileges must be scoped

Distinguish clearly:

- `ROLE_TENANT_ADMIN`: administrative privilege within the tenant assigned to the user.
- `ROLE_SYSTEM_ADMIN`: system-wide administrative privilege, if genuinely defined by the business.
- `ROLE_SUPPORT`: support role; does not automatically grant access to read private documents.
- Owner: permission on **one document**, not on all documents in the same tenant.

This example has **no** “superuser bypassing every check.” If `ROLE_SYSTEM_ADMIN` must cross tenants, design it separately with documented intent, tight access bounds, auditing, tests, and strict role-assignment controls. Never mechanically write `hasRole('ADMIN') or hasPermission(...)`, because the admin branch can bypass every tenant and ACL check.

A subtle point: pairing a global string role `ROLE_TENANT_ADMIN` with membership is a simple learning setup. In real applications, if someone belongs to multiple tenants yet administers only **one** tenant, store tenant-scoped `role binding`s (such as `user_role(user, tenant, role)`) rather than granting a role that makes them admin of every tenant they belong to.

## 3. PermissionEvaluator is where permissions attach to specific resources

Interface:

```java
package org.springframework.security.access;

public interface PermissionEvaluator {
    boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission
    );

    boolean hasPermission(
        Authentication authentication,
        Serializable targetId,
        String targetType,
        Object permission
    );
}
```

This is an **abbreviated API signature summary** for explanation; the real interface lives in Spring Security with the framework's own imports/superinterfaces. Do not recreate the interface in that package yourself.

Two common expressions:

```java
@PreAuthorize("hasPermission(#id, 'Document', 'edit')")
public Document rename(@P("id") Long id, String title) {
    return store.rename(id, title);
}

@PostAuthorize("returnObject != null and hasPermission(returnObject, 'read')")
public Document findOne(Long id) {
    return store.require(id);
}
```

These are **illustrative method snippets**; they need a class, imports, and `store` to form a program. Key distinctions:

- **ID overload**: the evaluator receives the id, `targetType = "Document"`, and `permission = "edit"`. Suitable for `@PreAuthorize` **before write operations**.
- **Object overload**: the evaluator receives a `Document` instance and `permission = "read"`. Suitable for deciding whether a **read result may be returned** in `@PostAuthorize`.
- `targetType` **is only a string**; Spring does not automatically look up owners or ACLs from the name `Document`. The evaluator defines the mapping and queries the data source.
- `@PostAuthorize` runs **after** the method returns a result; if the method already sent an email or wrote to the DB, denying afterward does not undo those side effects.
- `@PreAuthorize` normally blocks the method at the proxy before the target runs. When data and resource ID are available, it is the right choice to protect mutations.

Never assume Spring Security comes with built-in ownership/sharing policies for you. `hasPermission` is only an **extension point**. Without a properly configured evaluator, the application does not infer ACLs or sharing permissions.

### 3.1. Evaluation flow

```text
Caller → Spring-managed DocumentService proxy
   ↓
@PreAuthorize("hasPermission(#id, 'Document', 'edit')")
   ↓
MethodSecurityExpressionHandler
   ↓
DocumentPermissionEvaluator.hasPermission(authentication, id, type, action)
   ├─ Check Authentication is not anonymous
   ├─ Validate targetType/action/id
   ├─ Load canonical Document by id
   ├─ Check membership + tenant scope
   ├─ Check owner / share grant / tenant admin
   └─ Return boolean
   ↓
true  → run method
false → AccessDeniedException (or subclass), target does not run
```

Note that `@PreAuthorize` still relies on a **Spring AOP proxy**. Calling a method on the same bean via `this` or instantiating `new DocumentService(...)` will bypass the interceptor in standard proxy mode.

## 4. Designing safe sharing permissions

### 4.1. Grants are server-side data, not client-editable “owner” fields

A minimal ACL table could include:

```text
document_share(
  document_id,
  grantee_user_id,
  access_level,      -- VIEWER | EDITOR
  granted_by,
  granted_at,
  expires_at,        -- as required
  revoked_at         -- as required
)
```

These fields illustrate business semantics, not complete DDL. They must reside on a trusted store and reference the real resource ID. Never treat client-sent JSON `{"owner":"alice","sharedWith":["bob"]}` as an approved ACL.

**Granting:** only the owner/tenant admin may grant; the recipient must belong to the tenant and have a valid account. You may disallow sharing to the owner themselves, distinguish pending invitations, enforce expiration, and audit who granted access.

**Revoking:** only the owner/tenant admin may revoke; the recipient's tokens/sessions or caches must reflect revocation within your SLA. For public share links, a dedicated mechanism is needed: unguessable tokens, expiration, minimal scope, revocation, rate limiting, and keeping share links out of public logs.

### 4.2. Shared permissions are not transitive by default

An `EDITOR` must not be able to grant `EDITOR` to another user; if desired, add a separate `delegate` or `share` action with depth limits and explicit rules. Never assume “has edit ⇒ has share” unless the domain explicitly specifies it.

A `VIEWER` also does not automatically gain `export`, `download-original`, or `publish`. In multi-tier systems, you may need distinct `read-metadata`, `download`, `export`, and `comment` actions; keep the matrix compact for demos and expand it according to risk.

### 4.3. Decisions must consider current state

Grants can expire, documents can be locked, users can leave tenants, or documents can move to `ARCHIVED`. `PermissionEvaluator` must evaluate these conditions per policy. **Deny when uncertain**, especially when a membership/ACL service fails. Returning `true` simply because the DB is unreachable is a dangerous fail-open bug.

## 5. Runnable Java 17 project with Spring Boot 3.5.6

The following example provides complete Java, Maven, and JUnit 5 files using Spring Security 6.5.x managed by Spring Boot 3.5.6. No database or HTTP server is needed; `ConcurrentHashMap` storage and a fixed directory let the tests verify `PermissionEvaluator`'s exact decisions.

The demo's goal is **policy enforcement**, not replacing ACID transactions, row locks, IAM systems, or ACL databases. Production limitations are analyzed in later sections.

### 5.1. File tree

```text
ownership-share-admin-demo/
  pom.xml
  src/main/java/com/example/ownership/
    OwnershipApplication.java
    MethodSecurityConfig.java
    Document.java
    ShareAccess.java
    TenantDirectory.java
    DocumentStore.java
    DocumentPermissionEvaluator.java
    DocumentService.java
  src/test/java/com/example/ownership/
    DocumentServiceTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>ownership-share-admin-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

### 5.3. Spring Boot application

**`src/main/java/com/example/ownership/OwnershipApplication.java`**

```java
package com.example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OwnershipApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }
}
```

### 5.4. Domain and share access levels

**`src/main/java/com/example/ownership/Document.java`**

```java
package com.example.ownership;

public record Document(
        Long id,
        String tenant,
        String owner,
        String title) {
}
```

**`src/main/java/com/example/ownership/ShareAccess.java`**

```java
package com.example.ownership;

public enum ShareAccess {
    VIEWER,
    EDITOR
}
```

Do not use a boolean `isShared`: a boolean cannot distinguish viewing from editing, nor store recipient, expiration, and grantor. Level `EDITOR` **does not include** share/delete under this policy.

### 5.5. TenantDirectory: trusted membership list

**`src/main/java/com/example/ownership/TenantDirectory.java`**

```java
package com.example.ownership;

import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {
    private final Map<String, Set<String>> memberships = Map.of(
        "t1", Set.of("alice", "bob", "manager1"),
        "t2", Set.of("carol", "dave", "manager2")
    );

    public boolean isMember(String username, String tenant) {
        Set<String> members = memberships.get(tenant);
        return username != null
            && members != null
            && members.contains(username);
    }
}
```

This immutable fixture acts as a “trusted membership data source” for testing. In real applications, memberships must live in a DB/IAM with a revocation strategy rather than being hardcoded in Java. Holding a `tenant:t1` authority in a token **does not replace** membership checks if the token can be stale or mis-mapped.

### 5.6. DocumentStore: in-memory documents and ACLs

**`src/main/java/com/example/ownership/DocumentStore.java`**

```java
package com.example.ownership;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {
    private final ConcurrentMap<Long, Document> documents =
        new ConcurrentHashMap<>();

    private final ConcurrentMap<Long, ConcurrentMap<String, ShareAccess>> grants =
        new ConcurrentHashMap<>();

    public DocumentStore() {
        reset();
    }

    public synchronized void reset() {
        documents.clear();
        grants.clear();

        documents.put(101L,
            new Document(101L, "t1", "alice", "Alice draft"));
        documents.put(102L,
            new Document(102L, "t1", "bob", "Bob notes"));
        documents.put(201L,
            new Document(201L, "t2", "carol", "Carol plan"));
    }

    public Document find(Long id) {
        return id == null ? null : documents.get(id);
    }

    public Document require(Long id) {
        Document document = find(id);
        if (document == null) {
            throw new NoSuchElementException("Document not found");
        }
        return document;
    }

    public ShareAccess sharedLevel(Long documentId, String username) {
        Map<String, ShareAccess> entries = grants.get(documentId);
        return entries == null ? null : entries.get(username);
    }

    public void grant(Long id, String username, ShareAccess access) {
        if (find(id) == null || username == null || access == null) {
            throw new IllegalArgumentException("Invalid share");
        }
        grants.computeIfAbsent(id, ignored -> new ConcurrentHashMap<>())
            .put(username, access);
    }

    public void revoke(Long id, String username) {
        Map<String, ShareAccess> entries = grants.get(id);
        if (entries != null) {
            entries.remove(username);
        }
    }

    public Document rename(Long id, String title) {
        return documents.computeIfPresent(id, (key, old) ->
            new Document(old.id(), old.tenant(), old.owner(), title)
        );
    }

    public boolean delete(Long id) {
        if (documents.remove(id) == null) {
            return false;
        }
        grants.remove(id);
        return true;
    }
}
```

We separate documents and grants to model shared permissions that can be granted/revoked independently. `ConcurrentHashMap` only supports individual concurrent operations; it **does not** guarantee atomicity of the entire “check permission → edit document → update ACL” sequence across multiple maps. Real systems must protect invariants with transactions, data constraints, and appropriate locking.

### 5.7. PermissionEvaluator: owner OR share OR tenant admin, never crossing tenants

**`src/main/java/com/example/ownership/DocumentPermissionEvaluator.java`**

```java
package com.example.ownership;

import java.io.Serializable;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {
    private static final String DOCUMENT_TYPE = "Document";

    private final DocumentStore documents;
    private final TenantDirectory tenants;
    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public DocumentPermissionEvaluator(
            DocumentStore documents,
            TenantDirectory tenants) {
        this.documents = documents;
        this.tenants = tenants;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {
        if (!(targetDomainObject instanceof Document document)) {
            return false;
        }

        // Use only the ID; do not trust owner/tenant on a client-constructible object.
        return hasPermission(
            authentication,
            document.id(),
            DOCUMENT_TYPE,
            permission
        );
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)) {
            return false;
        }

        if (!(targetId instanceof Long id)
                || !DOCUMENT_TYPE.equals(targetType)
                || !(permission instanceof String action)) {
            return false;
        }

        Document document = documents.find(id);
        if (document == null) {
            return false;
        }

        String username = authentication.getName();

        // Both tenant membership and tenant authority must match accurately.
        if (!tenants.isMember(username, document.tenant())
                || !hasAuthority(
                    authentication, "tenant:" + document.tenant())) {
            return false;
        }

        boolean owner = document.owner().equals(username);
        boolean tenantAdmin = hasAuthority(
            authentication, "ROLE_TENANT_ADMIN");
        ShareAccess shared = documents.sharedLevel(id, username);

        return switch (action) {
            case "read" ->
                owner || tenantAdmin
                    || shared == ShareAccess.VIEWER
                    || shared == ShareAccess.EDITOR;

            case "edit" ->
                owner || tenantAdmin || shared == ShareAccess.EDITOR;

            case "share", "revoke", "delete" ->
                owner || tenantAdmin;

            default -> false;
        };
    }

    private static boolean hasAuthority(
            Authentication authentication, String expected) {
        for (GrantedAuthority authority : authentication.getAuthorities()) {
            if (expected.equals(authority.getAuthority())) {
                return true;
            }
        }
        return false;
    }
}
```

**Analyzing the key guards:**

1. `Authentication` must exist, be validly authenticated, and not be anonymous.
2. Target ID must be `Long`, type must be `Document`, and permission must be `String`.
3. The evaluator loads the **canonical document by ID from the server-side store**, never trusting owner/tenant stuffed into a forged instance by the caller.
4. Both membership and the `tenant:<id>` authority must match the record's tenant.
5. Only after passing the tenant boundary are owner, share grant, or `ROLE_TENANT_ADMIN` evaluated.
6. `VIEWER` only allows read; `EDITOR` adds edit; only owner/admin may share/revoke/delete.
7. Unknown actions, nonexistent IDs, wrong types, nulls, or missing memberships all return `false`.

This is the **example's** policy. If the business requires that owners cannot delete approved records, add a state condition; if admins only get read support, narrow `adminActions`. Never let the word “admin” become an unaudited blanket license.

#### Why not use only hasRole or hasAuthority?

`hasRole('TENANT_ADMIN')` under default config checks for the `ROLE_TENANT_ADMIN` authority, yet **does not know which tenant**. `hasAuthority('tenant:t1')` knows the scope granted to the caller, yet **does not know which tenant the document ID belongs to**. The evaluator combines both pieces of data with the specific owner and share grants.

#### Why does the object overload also look up the document?

Suppose Bob sends a forged object `new Document(101L, "t1", "bob", "...")` claiming to be the owner. If the evaluator trusted `document.owner()` on the client-created object, Bob could grant himself access. Here the object overload extracts only `id` and delegates to the ID overload to look up the real record. If not found, it denies.

## 6. Enabling Method Security and wiring the evaluator

**`src/main/java/com/example/ownership/MethodSecurityConfig.java`**

```java
package com.example.ownership;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator permissionEvaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }
}
```

This is the integration pattern illustrated by Spring Security 6.5: declare `@EnableMethodSecurity` and publish a `static MethodSecurityExpressionHandler` early so the framework uses the evaluator when evaluating `hasPermission(...)`.

Spring Boot Security **does not automatically enable Method Security solely from the dependency**. If you forget `@EnableMethodSecurity`, annotations still compile without creating the needed interceptors. If your project already has a custom expression handler, do not accidentally replace it and lose role hierarchy, default role prefix, or existing evaluator settings; merge the configuration into one consistent handler.

## 7. Service: separating read, edit, share, and admin actions

**`src/main/java/com/example/ownership/DocumentService.java`**

```java
package com.example.ownership;

import java.util.NoSuchElementException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentStore documents;
    private final TenantDirectory tenants;

    public DocumentService(
            DocumentStore documents,
            TenantDirectory tenants) {
        this.documents = documents;
        this.tenants = tenants;
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'read')")
    public Document read(@P("id") Long id) {
        return documents.require(id);
    }

    // Post-authorization is suitable for pure read results, never for protecting writes.
    @PostAuthorize(
        "returnObject != null and hasPermission(returnObject, 'read')"
    )
    public Document readAfter(@P("id") Long id) {
        return documents.require(id);
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'edit')")
    public Document rename(@P("id") Long id, String newTitle) {
        Document result = documents.rename(id, newTitle);
        if (result == null) {
            throw new NoSuchElementException("Document not found");
        }
        return result;
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'share')")
    public void share(
            @P("id") Long id,
            String recipient,
            ShareAccess access) {
        Document document = documents.require(id);

        if (access == null
                || recipient == null
                || recipient.isBlank()
                || !tenants.isMember(recipient, document.tenant())
                || document.owner().equals(recipient)) {
            throw new IllegalArgumentException(
                "Recipient/access not allowed"
            );
        }

        documents.grant(id, recipient, access);
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'revoke')")
    public void revoke(@P("id") Long id, String recipient) {
        Document document = documents.require(id);

        if (recipient == null || document.owner().equals(recipient)) {
            throw new IllegalArgumentException(
                "Cannot revoke the owner"
            );
        }

        documents.revoke(id, recipient);
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'delete')")
    public boolean delete(@P("id") Long id) {
        return documents.delete(id);
    }
}
```

Pre-authorization annotations **only** decide whether the caller has permission to perform the action given the current resource state. `share` additionally verifies that the **recipient** belongs to the tenant; otherwise an owner could accidentally share with someone outside the tenant. Even though the evaluator still blocks cross-tenant access, constraining share creation upfront prevents invalid grants, reduces junk ACL rows, and improves auditability.

**There is no “share to owner”** in this example, because the owner already holds permissions via ownership; if real ownership transfer is needed, design a dedicated **transferOwnership** operation with reauthentication/approval/auditing if business rules require it. Never disguise an ownership change as `share(…, EDITOR)`.

When ownership changes or a document moves tenants, real systems must decide what happens to existing grants. The example does not implement transfers, so there are no hidden transfer rules in the code.

## 8. Integration tests: not just allow, prove deny too

Create the test file:

**`src/test/java/com/example/ownership/DocumentServiceTest.java`**

```java
package com.example.ownership;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class DocumentServiceTest {
    @Autowired DocumentService service;
    @Autowired DocumentStore store;
    @Autowired DocumentPermissionEvaluator evaluator;

    @BeforeEach
    void reset() {
        store.reset();
    }

    private Authentication currentUser() {
        return SecurityContextHolder.getContext().getAuthentication();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCanReadWithoutExplicitShare() {
        assertEquals("Alice draft", service.read(101L).title());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCanEdit() {
        assertEquals("Updated", service.rename(101L, "Updated").title());
        assertEquals("Updated", store.require(101L).title());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCanShareWithTenantMember() {
        service.share(101L, "bob", ShareAccess.VIEWER);
        assertEquals(ShareAccess.VIEWER,
            store.sharedLevel(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCanRevokeSharing() {
        store.grant(101L, "bob", ShareAccess.EDITOR);
        service.revoke(101L, "bob");
        assertNull(store.sharedLevel(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCanDelete() {
        assertTrue(service.delete(101L));
        assertNull(store.find(101L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void unsharedMemberCannotReadOthersDocument() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void viewerCanReadSharedDocument() {
        store.grant(101L, "bob", ShareAccess.VIEWER);
        assertEquals("Alice draft", service.read(101L).title());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void viewerCannotEdit() {
        store.grant(101L, "bob", ShareAccess.VIEWER);
        assertThrows(AccessDeniedException.class,
            () -> service.rename(101L, "Forbidden"));
        assertEquals("Alice draft", store.require(101L).title());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void viewerCannotShareFurther() {
        store.grant(101L, "bob", ShareAccess.VIEWER);
        assertThrows(AccessDeniedException.class,
            () -> service.share(101L, "manager1", ShareAccess.VIEWER));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void viewerCannotDelete() {
        store.grant(101L, "bob", ShareAccess.VIEWER);
        assertThrows(AccessDeniedException.class,
            () -> service.delete(101L));
        assertEquals("Alice draft", store.require(101L).title());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void editorCanReadAndEdit() {
        store.grant(101L, "bob", ShareAccess.EDITOR);
        assertEquals("Alice draft", service.read(101L).title());
        assertEquals("Edited", service.rename(101L, "Edited").title());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void editorCannotDelegate() {
        store.grant(101L, "bob", ShareAccess.EDITOR);
        assertThrows(AccessDeniedException.class,
            () -> service.share(101L, "manager1", ShareAccess.EDITOR));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void editorCannotDelete() {
        store.grant(101L, "bob", ShareAccess.EDITOR);
        assertThrows(AccessDeniedException.class,
            () -> service.delete(101L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void revokedShareStopsFurtherAccess() {
        store.grant(101L, "bob", ShareAccess.EDITOR);
        assertEquals("Alice draft", service.read(101L).title());
        store.revoke(101L, "bob");
        assertThrows(AccessDeniedException.class,
            () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "manager1",
        authorities = {"tenant:t1", "ROLE_TENANT_ADMIN"})
    void tenantAdminReadsUnsharedDocument() {
        assertEquals("Alice draft", service.read(101L).title());
    }

    @Test
    @WithMockUser(username = "manager1",
        authorities = {"tenant:t1", "ROLE_TENANT_ADMIN"})
    void tenantAdminCanEditAndDeleteWithinTenant() {
        assertEquals("Managed", service.rename(101L, "Managed").title());
        assertTrue(service.delete(102L));
    }

    @Test
    @WithMockUser(username = "manager1",
        authorities = {"tenant:t1", "ROLE_TENANT_ADMIN"})
    void tenantAdminMayManageShares() {
        service.share(101L, "bob", ShareAccess.EDITOR);
        assertEquals(ShareAccess.EDITOR,
            store.sharedLevel(101L, "bob"));
        service.revoke(101L, "bob");
        assertNull(store.sharedLevel(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "manager1",
        authorities = {"tenant:t1", "ROLE_TENANT_ADMIN"})
    void tenantAdminCannotCrossTenantBoundary() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(201L));
        assertThrows(AccessDeniedException.class,
            () -> service.delete(201L));
    }

    @Test
    @WithMockUser(username = "manager1",
        authorities = "ROLE_TENANT_ADMIN")
    void tenantAdminWithoutTenantAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "mallory",
        authorities = {"tenant:t1", "ROLE_TENANT_ADMIN"})
    void forgedTenantAuthorityCannotReplaceMembership() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void crossTenantGrantDoesNotBypassTenantRule() {
        store.grant(201L, "bob", ShareAccess.EDITOR);
        assertThrows(AccessDeniedException.class,
            () -> service.read(201L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void ownerCannotShareToAnotherTenant() {
        assertThrows(IllegalArgumentException.class,
            () -> service.share(101L, "carol", ShareAccess.VIEWER));
        assertNull(store.sharedLevel(101L, "carol"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void forgedDomainObjectCannotMakeBobOwner() {
        Document forged = new Document(
            101L, "t1", "bob", "Fake owner"
        );
        assertFalse(evaluator.hasPermission(
            currentUser(), forged, "edit"
        ));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void unknownActionAndTypeAreDenied() {
        assertFalse(evaluator.hasPermission(
            currentUser(), 101L, "Document", "transfer"
        ));
        assertFalse(evaluator.hasPermission(
            currentUser(), 101L, "Invoice", "read"
        ));
        assertFalse(evaluator.hasPermission(
            currentUser(), 101L, "Document", null
        ));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void missingDocumentIdIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(999L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "tenant:t1")
    void postAuthorizeAllowsOwnerRead() {
        assertEquals("Alice draft", service.readAfter(101L).title());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "tenant:t1")
    void postAuthorizeRejectsUnsharedRead() {
        assertThrows(AccessDeniedException.class,
            () -> service.readAfter(101L));
    }

    @Test
    void nullAuthenticationCannotBeGranted() {
        assertFalse(evaluator.hasPermission(
            null, 101L, "Document", "read"
        ));
    }
}
```

The tests use the **Spring-injected service bean**, so annotations run through the real Spring AOP proxy. `@WithMockUser` builds a mock Authentication to test **authorization**, not a real password/JWT login. Data resets before each test; nothing relies on execution order.

Run from the directory containing `pom.xml`:

```bash
mvn test
```

**Expected result based on the source code:** 28 tests, all passing, 0 failures/errors. Test counts and Maven/Surefire output may change if you extend the suite. This is the **expected result by design**, not a claim that Maven was executed in this lesson.

Important invariants verified by the tests:

- The owner always has permissions on their own document in the **right tenant**.
- Viewer and editor permissions differ; an editor **does not automatically get share permission**.
- Revoking a grant takes effect on the very next check in the simulated storage.
- A tenant admin only administers within their own tenant; holding the admin role without the tenant authority still denies.
- An authority string that looks valid without the username being in the trusted directory does not grant access.
- A share grant mistakenly stored across tenants does not open cross-tenant access.
- Objects with a forged owner do not elevate permissions because the evaluator looks up the canonical record.
- Invalid actions, types, or document IDs are denied; there is no fallback to allow.
- Post-authorization works on read results, yet never replaces pre-write protection.

## 9. Production: ACLs, tenants, and ownership require transactions

The example uses two maps so every policy branch stays readable, whereas a real application must maintain consistency between permissions and data.

### 9.1. Reference schema

```sql
CREATE TABLE document (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    owner_user_id VARCHAR(80) NOT NULL,
    title VARCHAR(500) NOT NULL
);

CREATE TABLE document_share (
    document_id BIGINT NOT NULL,
    grantee_user_id VARCHAR(80) NOT NULL,
    access_level VARCHAR(20) NOT NULL,
    granted_by VARCHAR(80) NOT NULL,
    granted_at TIMESTAMP NOT NULL,
    PRIMARY KEY (document_id, grantee_user_id),
    FOREIGN KEY (document_id) REFERENCES document(id)
);

CREATE TABLE tenant_membership (
    tenant_id VARCHAR(80) NOT NULL,
    user_id VARCHAR(80) NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE tenant_role_binding (
    tenant_id VARCHAR(80) NOT NULL,
    user_id VARCHAR(80) NOT NULL,
    role_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, user_id, role_name)
);
```

This is an **illustrative schema**, omitting indexes/foreign keys for users, document types, version columns, grant expiration, soft deletes, business audits, and database-specific constraints. In real systems, role bindings should carry an **explicit `tenant_id`** so an admin in t1 does not automatically become an admin in t2 when belonging to both tenants.

### 9.2. TOCTOU risk: checking permission before editing, yet permissions change in between

Consider one call:

```text
T1  PermissionEvaluator: Bob currently holds EDITOR share on document 101
T2  Alice revokes Bob's permission
T3  Bob's method executes UPDATE document 101
```

If transactions or isolation do not preserve the invariant between T1 and T3, Bob can still edit after being revoked. `@PreAuthorize` **does not automatically prevent** this race condition, even though it blocks many unauthorized calls upfront.

Options depending on business needs:
- Check permission and write in the **same transaction** with row locks or optimistic versioning; pay attention to advisor ordering so the transaction actually wraps the check.
- Put owner/ACL/tenant conditions into the SQL update statement so the operation becomes a conditional update and check the affected row count.
- Enforce resource versions, tenant conditions, and permission versions; test concurrent conflicts and revocations.
- Accept a documented revocation window if data is low-sensitivity, decided explicitly based on risk.

Example owner-protecting SQL:

```sql
UPDATE document
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :current_tenant_id
  AND owner_user_id = :current_user_id;
```

This is a **SQL snippet** with named parameters bound by the data layer; tenant/user must come from a verified security context. For EDITOR shares or admins, include equivalent ACL/role-binding predicates; never accidentally drop the tenant condition when adding an admin branch.

### 9.3. Revocation, caching, and JWTs

If access grants live in the DB while the evaluator caches results:
- Cache keys must include user, tenant, document id, action, and critical permission versions/expirations.
- Changing owners, revoking grants, removing memberships, and removing tenant-admin roles must invalidate affected entries.
- If a JWT embeds roles or tenant memberships, old tokens can remain valid after revocation; design expiration/revocation strategies or online lookups per security requirements.
- On permission-server timeout or cache miss, never use `catch (Exception ex) { return true; }`. Flag the error/deny and monitor the system.

Never treat `ROLE_TENANT_ADMIN` inside a still-unexpired token as proof the role remains valid if policy demands immediate revocation.

### 9.4. Administrative privileges and least privilege

You can separate:
- `TENANT_CONTENT_ADMIN`: manages content, does not manage users.
- `TENANT_USER_ADMIN`: manages members/roles, does not implicitly read private content.
- `SYSTEM_AUDITOR`: read-only log access, no edits.
- `SUPPORT_BREAK_GLASS`: emergency access requiring approval, short expiration, and dedicated auditing.

Never grant a generic `ROLE_ADMIN` that bypasses every policy across all business flows. When “break glass” access exists, require a reason, reauthentication/step-up, audit logging, and abuse-detection mechanisms.

### 9.5. Sharing via groups or public links

When sharing with a **group**, the evaluator must know current group memberships and scope limits, preventing overlapping groups from causing privilege escalation. When sharing via link, access is no longer simply `Authentication#getName()`'s permission; you must validate capability tokens, expiry, scope, revocation, and potential client URL leakage.

Never turn a URL `/document/101?share=true` into an access grant. A client-selected boolean flag cannot prove they were granted a share.

## 10. Choosing where to check: HTTP, service, and database

There are three layers:

| Layer | What can it protect? | What must not be assumed |
|---|---|---|
| HTTP `authorizeHttpRequests` | Who can call a URL group, with which roles/authorities | Does not automatically know every document ID and owner in the DB |
| Method Security `@PreAuthorize`/`@PostAuthorize` | Permissions over method arguments or results, invoking `PermissionEvaluator` | Does not automatically provide transaction/race protection or block self-invocation |
| Database query/row policy | Locks down data scope, tenant, owner, and ACL at read/write time | Does not replace service-level business rules and auditing |

A well-designed API can combine:

```java
@PreAuthorize("hasPermission(#id, 'Document', 'edit')")
public void updateDocument(@P("id") Long id, String title) {
    // After passing Method Security, DB still updates with a
    // tenant predicate and checks version/row count.
}
```

This is a **structural pattern**; it requires appropriate service, repository, and transaction setup for production. Never rely on UI permissions (hiding an Edit button) as the sole protection layer. HTTP rules protect routes, while services can also be invoked by schedulers, message consumers, or other endpoints.

### 10.1. Post-authorization on read results and list-level permissions

`@PostAuthorize("hasPermission(returnObject, 'read')")` can be helpful when owner/ACL is only known after loading the object. However, it runs **after the method executes**, so it is not the right choice to guard mutations or email sending.

`@PostFilter("hasPermission(filterObject, 'read')")` filters each item of a result collection; querying first and filtering afterward can cause N+1 queries, skewed pagination, sensitive total counts, or high overhead. With real datasets, it is better to apply tenant/ACL filters **in the query** before pagination or build an access-controlled repository.

## 11. Common mistakes and fixes

| Mistake | Consequence | Fix |
|---|---|---|
| `hasRole('ADMIN') or isOwner(...)` ignoring tenant | Admins can access across tenants | Place the tenant boundary outside the OR branch; use tenant-scoped role bindings |
| Using client-sent `document.owner` | Clients claim ownership themselves | Look up the canonical record by ID on the server |
| `VIEWER` granted `edit` because “it was shared” | Privilege escalation | Use an explicit matrix per access level and action |
| `EDITOR` allowed to re-share to others | Unauthorized viral sharing | Make `share` a separate action restricted to owner/admin |
| Having `ROLE_TENANT_ADMIN` makes user admin of every tenant | Cross-tenant data exposure | Bind admin roles to explicit scope |
| Using `@PostAuthorize` for delete operations | Deletion completes before denial | Use `@PreAuthorize` and conditional DB updates |
| Checking permissions only at token creation | Revocation takes effect late | Token policies, membership lookups / cache invalidation |
| Unknown action returns true | Unintended default grant | `default -> false`, write negative tests |
| Cache key omits tenant or resource ID | Wrongly reuses another record's decision | Include full scope/version in cache keys, add invalidation |
| Calling same-bean method via `this` | Bypasses Method Security proxy | Separate beans or invoke through Spring proxy |
| Identifying tenant via arbitrary request header | Clients choose any tenant they like | Match server-side memberships and resources |
| Missing grant/revoke/admin logs | Cannot trace who granted access | Audit actor, target, before/after, reason, and timestamp |
| Changing owner while leaving grants unchecked | Recipients shared by old owner keep access | Define transfer rules + ACL revocation/migration inside transaction |
| Wrong ID type check or action casing | Sporadic denials or over-grants | Standardize interface, handle id/type/action fail-closed |

### 11.1. Must an owner always have every permission?

Not necessarily. Ownership is a **policy component**, not absolute supremacy. For instance, a `LOCKED` document may forbid owner edits; a document under legal hold may forbid deletion; an approved invoice may forbid owner cancellation. Separate status, action, and compliance conditions directly inside the evaluator or policy service.

### 11.2. Can you use only roles and authorities without PermissionEvaluator?

Yes, if the system only requires coarse capabilities like `report:export` over all data or has no per-record permissions. But for per-document sharing/ownership/tenant rules, `PermissionEvaluator` or a custom authorization bean/manager is a better fit. The `PermissionEvaluator` interface is a hook; not every system must use it if another policy engine enforces controls properly.

### 11.3. Can a shared EDITOR change the owner?

Not under this policy. Changing owner is **transfer ownership**, which impacts ACLs, audits, billing, and tenant constraints; give it a dedicated action, validate the recipient, handle timing, clearly revoke or retain grants, write negative tests, and audit it.

### 11.4. Why check membership in both service.share and the evaluator?

They serve different goals: the evaluator checks whether **the caller has permission to act**; `service.share` checks whether **the recipient is eligible to receive a grant**. Those are two distinct invariants. Being an owner does not make every recipient name valid.

### 11.5. Does revoking a share strip an owner's or admin's access?

No. These are **independent** permission sources; revoking a grant removes only the permission from that grant. If Bob is also a tenant admin, revoking Bob's EDITOR share does not strip Bob's admin role. When auditing or explaining permissions in the UI, show whether access stems from owner, share, or admin to prevent confusion.

## 12. Checklist for ownership, sharing, and admin policies

- [ ] Domain has canonical resource ID, tenant, and owner from a trusted server source.
- [ ] Clearly distinguishes owner, shared viewer, shared editor, tenant admin, and system admin (if any).
- [ ] Policy is documented as an explicit action matrix; never infer share/delete from edit.
- [ ] Tenant boundary is enforced **before** owner/share/admin branches.
- [ ] Tenant-admin roles are properly scoped; do not rely solely on a global role in real multi-tenant apps.
- [ ] `PermissionEvaluator` implements both required overloads, returning false on unknown input.
- [ ] Object overload reloads the canonical resource; never trusts client-constructed objects.
- [ ] Grant/revoke verifies both caller and recipient; includes auditing and expiration handling.
- [ ] Method Security is enabled, expression handler has `PermissionEvaluator` wired, and callers go through the proxy.
- [ ] `@PreAuthorize` guards writes/deletes/shares; `@PostAuthorize` is used only for read results where appropriate.
- [ ] Write queries include tenant/ACL predicates or transactional checks to mitigate TOCTOU.
- [ ] Token/permission caches define refresh/invalidation policies on revocation, tenant moves, or owner changes.
- [ ] Integration tests cover owner, viewer, editor, tenant admin, cross-tenant, non-directory user, revoked share, forged object, unknown action, and nonexistent ID.
- [ ] Access is denied on policy/ACL service errors, with logging to investigate denied decisions.

## 13. Official documentation

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`/`@PostAuthorize`, method parameters, and `MethodSecurityExpressionHandler` configuration.
- [Spring Security 6.5 — PermissionEvaluator API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/PermissionEvaluator.html): both overloads for checking objects or ID/type/action.
- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): ACL model and `AclPermissionEvaluator` integration.
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `Authentication`, `GrantedAuthority`, and authorization layers.
- [Spring Security 6.5 — SecurityExpressionRoot API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/expression/SecurityExpressionRoot.html): `hasPermission(...)` methods on the SpEL root.

**Remember:** Ownership, sharing permissions, and administrative privileges are **three permission sources** with distinct scopes. `PermissionEvaluator` combines them to return a decision on **one specific resource**; admin rights must never become a shortcut across tenants, EDITOR access does not imply re-sharing rights, and owners must still respect business state. Every decision must rely on trusted data, fail closed when information is missing, and be tested thoroughly for denial cases too.