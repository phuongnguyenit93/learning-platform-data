# Naming Permissions by Action on Resource Type — Spring Security PermissionEvaluator

## 1. The problem: a “permission” needs a clear enough name for consistent enforcement

A system has many resource types: documents (`document`), invoices (`invoice`), purchase orders (`purchase-order`), and reports (`report`). Each resource type supports different actions: view, create, edit, delete, approve, export. Writing generic strings like `READ`, `WRITE`, or `ADMIN` does not tell you “read what,” whereas an overly specific string like `read-document-482-for-alice-in-tenant-7` is hard to manage and easily causes an explosion of authorities.

A useful convention is:

```text
<resource>:<action>

document:read
document:create
document:edit
document:delete
invoice:read
invoice:approve
report:export
purchase-order:approve
```

This is a **convention chosen by the application**, **not a mandatory syntax** of Spring Security. The key point is to clearly separate:

1. **Resource type**: `document`, `invoice`, `purchase-order`.
2. **Action/permission**: `read`, `create`, `edit`, `delete`, `approve`, `export`.
3. **Identity/context**: who is logged in, which tenant do they belong to, are they the owner or an approver?
4. **Resource instance**: for example, document id 42 belonging to tenant A and owner alice.

An authority such as `document:edit` states that the user has the **capability to edit the document resource type**. It does **not yet** assert that the user may edit **every** document. To check permission on a specific document, you must combine the authority with owner, tenant, record state, and business policy.

In Spring Security, **`PermissionEvaluator`** is an extension point for object-level permission checks. This article focuses on how to **name permissions by action and resource type** so they can be used consistently across `GrantedAuthority`, `hasPermission(...)`, permission databases, annotations, audit logs, and tests.

## 2. Distinguishing five easily confused concepts

| Concept | Example | Meaning |
|---|---|---|
| Role | `ROLE_DOC_ADMIN` | Principal's role; typically mapped to a `GrantedAuthority` prefixed with `ROLE_` |
| Authority | `document:edit` | Permission string granted to `Authentication`; `hasAuthority` matches the exact string |
| Resource type | `Document` | Object type checked by `PermissionEvaluator`; can be an application-defined alias |
| Action/permission | `edit` | Operation being requested on a specific resource |
| Resource instance | `Document(id=42, tenant=t1, owner=alice)` | Concrete record used to evaluate owner, tenant, state, and constraints |

The core difference appears in two expressions:

```java
@PreAuthorize("hasAuthority('document:edit')")
public void editAnyDocument(long documentId) { /* ... */ }

@PreAuthorize("hasPermission(#documentId, 'Document', 'edit')")
public void editOneDocument(@P("documentId") Long documentId) { /* ... */ }
```

The two methods above are **illustrative snippets** and do not run standalone because they lack a class, imports, and business body. In the first expression, Spring only checks for `GrantedAuthority("document:edit")`. In the second expression, Spring **delegates** to `PermissionEvaluator`, passing the id, targetType, and action so the application decides based on the actual resource. If your evaluator is written properly, it can require **both** `document:edit`, tenant membership, and an appropriate owner/role.

**Do not confuse:** `hasPermission(#id, 'Document', 'edit')` does **not automatically** translate to `hasAuthority('document:edit')`. Authority names and action names are compatible only when **you yourself define and enforce the mapping rule** inside the evaluator.

## 3. Extensible naming rules

### 3.1. Type names: stable nouns, not UI labels

Choose one canonical name for each domain resource:

| Canonical name | Meaning | Avoid mixing with |
|---|---|---|
| `document` | Document | `doc`, `documents`, `file` if referring to the same type |
| `invoice` | Invoice | `bill` if there is no domain distinction |
| `purchase-order` | Purchase order | `po`, `purchaseOrder` |
| `report` | Report | `reports`, `export-file` |

This value should remain **stable in the authorization system**. If you rename the Java object from `Document` to `KnowledgeDocument`, you do not necessarily have to rename the `document:read` authority if the domain resource is still a document. Conversely, if the domain splits object types, plan permission name migration and versioning.

**Recommendation for authority strings:** lowercase ASCII, kebab-case for multi-word resources, and `:` separating resource and action, such as `purchase-order:approve`. A system may adopt a different standard, but do not accidentally mix two standards. Spring Security matches authorities **case-sensitively**.

### 3.2. Action names: clear verbs, avoid overly broad “write”

An action set may include:

| Action | Meaning | Business question |
|---|---|---|
| `read` | View content | Is this person allowed to read the document? |
| `list` | View list/search results | Are they allowed to list documents in this tenant? |
| `create` | Create a new record | Are they allowed to create a document in this project/tenant? |
| `edit` | Modify content | Are they allowed to change the title/body of this document? |
| `delete` | Delete or mark as deleted | Are they allowed to delete this document? |
| `approve` | Approve | Are they allowed to approve this invoice/purchase order? |
| `publish` | Publish | Are they allowed to make a reviewed document public? |
| `export` | Export/download data | Are they allowed to export data in bulk? |
| `assign` | Grant access or assign owner | Are they allowed to assign a resource to someone else? |

Do not automatically treat `edit` as implying `delete` or `approve`. Those are actions with different risk levels and workflows. The name `write` may be acceptable in a simple API, but business applications usually need to separate `create`, `edit`, `delete`, and `approve`.

**Distinguish `list` and `read`:** permission to view a list can differ from permission to view specific content. A list endpoint must apply scoping in the query and also control metadata/total counts; you cannot rely on checking permissions item-by-item only after querying and paginating.

### 3.3. Do not put object ID or tenant ID into global permission names unnecessarily

Keep authorities relatively stable:

```text
document:read
document:edit
document:delete
```

Then check context:

```text
Authentication.authorities = [
  "document:edit",
  "tenant:t1"
]

Document {
  id = 42
  tenant = "t1"
  owner = "alice"
}
```

This is a **design example**: the `document:edit` permission and `tenant:t1` membership are two distinct attributes. Do not build millions of authorities like `document:42:edit` when permissions can be looked up via DB/ACL; the number of authorities in tokens/sessions will bloat, revocation becomes difficult, and scoping becomes hard to enforce accurately.

Sometimes permissions need to be scoped by tenant, such as `tenant:t1:document:read`. In that case, the convention must be clearly **designed and enforced**; do not use `startsWith("tenant:t1")` because it can accidentally match `tenant:t10`. Split into typed fields or perform exact string matching after canonicalization.

### 3.4. Separate roles from actions

The role `ROLE_DOC_ADMIN` is not the action `document:approve`. If an admin role is allowed to approve invoices, policy can map that role to capabilities in security configuration or explicitly check the role branch. Never assume any role is allowed across all tenants; system-wide admin and tenant-scoped admin are **two different models**.

In the runnable example in section 6, the `ROLE_DOC_ADMIN` role permits operations according to rules **only while still belonging to the resource's tenant**. This is a business decision of the sample, not a Spring Security default.

## 4. How does PermissionEvaluator receive permission names?

The `org.springframework.security.access.PermissionEvaluator` interface defines **two overloads**:

```java
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
```

These signatures are **API excerpts**; to compile, they must be placed in an appropriate interface/class with `Authentication` and `Serializable` imported.

### 4.1. Object form: hasPermission(target, permission)

```java
@PostAuthorize("returnObject != null and hasPermission(returnObject, 'read')")
public Document read(Long id) {
    return repository.findById(id).orElseThrow();
}
```

The example above is a **service snippet**. The method executes first, and then `@PostAuthorize` inspects the actual returned object. The evaluator receives:
- the current `Authentication`;
- `targetDomainObject` as a `Document`;
- `permission` as the string `"read"`.

This form is suitable for **trusted server-side read results**. Because post-authorization runs after the method, avoid using `@PostAuthorize` as the sole protection for write operations or irreversible side effects.

For client-submitted objects, **do not trust owner/tenant fields on an unverified object**. The evaluator should reload the canonical record from the repository by id or ensure the input was retrieved and verified at a trusted layer. The sample code below intentionally reloads the canonical record.

### 4.2. ID + type + permission form

```java
@PreAuthorize("hasPermission(#id, 'Document', 'edit')")
public Document edit(@P("id") Long id, String title) {
    return repository.rename(id, title);
}
```

This is a **service snippet**. The evaluator receives:
- `targetId`: the document's id, typically `Long` or an appropriate `Serializable` type;
- `targetType`: the string `"Document"`;
- `permission`: the string `"edit"`.

**`'Document'` is not automatically a Java class lookup.** The API only provides the targetType string; the evaluator/ACL strategy decides whether this string is an alias or a fully qualified class name. In a custom-built system, publish canonical aliases and use them consistently. If integrating Spring Security ACL, check the `ObjectIdentity`/permission mapping rules of the ACL implementation being used rather than making generic assumptions.

The ID form is very useful for **`@PreAuthorize` on write operations**: the method has not run yet while the evaluator can already look up trusted data and decide authorization. However, checking permission before writing can still suffer from a race condition if the record changes owner/tenant between the two steps; sensitive operations should use transactions, locks/rechecks, or conditional SQL updates.

### 4.3. Clear conventions between the two invocation styles

This article intentionally chooses two distinct naming layers:

```text
GrantedAuthority: "document:edit"
targetType:       "Document"
permission:       "edit"
targetId:         42L
```

The evaluator maps:

```text
hasPermission(42L, "Document", "edit")
    ↓
load Document #42 from trusted storage
    ↓
check Membership on Document #42's tenant
    ↓
check "document:edit" authority
    ↓
check owner or ROLE_DOC_ADMIN
    ↓
true / false
```

Advantage: permission actions can stay short and uniform across resources, while authority names still distinguish resources. Risk: if a caller invokes `hasPermission(#id,'Document','document:edit')` while the evaluator only understands `"edit"`, it will be denied. A **fail-closed** policy for unknown actions is right; fix the caller rather than blindly loosening the evaluator.

### 4.4. No built-in business PermissionEvaluator by default

Spring Security provides the `hasPermission` hook, but it **does not automatically infer** owner, tenant, database permissions, or application-named actions like `read`/`edit`. With `@EnableMethodSecurity`, you must register and configure an actual evaluator; without an appropriate policy configured, the system must never implicitly grant object-level permissions.

If you only need to check a global capability without an object, `hasAuthority('document:read')` may be sufficient and simpler. When evaluating owner/tenant/resource-state, `hasPermission` or a policy bean is more appropriate.

## 5. Reference policy: document:action plus tenant and owner

To make the example realistic enough yet testable, define:

- Resource type `Document` with `id`, `tenantId`, `owner`, `title`.
- Three documents: id 1 in tenant `t1`/owner `alice`; id 2 in `t1`/owner `bob`; id 3 in `t2`/owner `carol`.
- The caller must have authority `tenant:<tenantId>` **matching exactly** the document's tenant.
- `read`: requires tenant membership and `document:read` **or** `ROLE_DOC_ADMIN`.
- `edit`: requires tenant membership, authority `document:edit`, and must be the **owner** or have `ROLE_DOC_ADMIN`.
- `delete`: requires tenant membership, authority `document:delete` **and** `ROLE_DOC_ADMIN`.
- Unsupported action/type/id or nonexistent object: **deny**.

| Action | Required authority | Additional constraints |
|---|---|---|
| `read` | `document:read` or `ROLE_DOC_ADMIN` | Must belong to the right tenant |
| `edit` | `document:edit` | Must belong to tenant and be owner or `ROLE_DOC_ADMIN` |
| `delete` | `document:delete` | Must belong to tenant and have `ROLE_DOC_ADMIN` |

This is a **sample policy**, not a framework standard policy. Read permission is allowed on any document in the same tenant with `document:read`, even for a different owner; that is intentional to distinguish read permission from the edit owner restriction.

Important invariant: even someone holding `ROLE_DOC_ADMIN` for tenant t1 does **not** implicitly cross into tenant t2 under this policy. A system-wide role, if any, requires a separate explicitly documented and tested policy.

## 6. Runnable Java 17 project: Spring Boot 3.5.6 + Method Security

The demo is a plain Spring Boot application without an HTTP server or database. In-memory storage simulates a repository so we can focus on permission naming and `PermissionEvaluator`. Tests use `@SpringBootTest` with `@WithMockUser` to go through the real Method Security proxy.

Project tree:

```text
permission-names-demo/
  pom.xml
  src/main/java/com/example/permissions/
    PermissionNamesApplication.java
    MethodSecurityConfig.java
    Document.java
    DocumentStore.java
    DocumentPermissionEvaluator.java
    DocumentService.java
  src/test/java/com/example/permissions/
    DocumentServiceTest.java
```

### 6.1. pom.xml

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
    <artifactId>permission-names-demo</artifactId>
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

The example picks Boot 3.5.6 (which manages Spring Security 6.5.x) without pinning a separate Spring Security version. For newer versions or Gradle, check the dependency tree and API compatibility before applying.

### 6.2. Spring Boot application

**`src/main/java/com/example/permissions/PermissionNamesApplication.java`**

```java
package com.example.permissions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PermissionNamesApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionNamesApplication.class, args);
    }
}
```

### 6.3. Enable Method Security and wire PermissionEvaluator into the expression handler

**`src/main/java/com/example/permissions/MethodSecurityConfig.java`**

```java
package com.example.permissions;

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

**Why are two steps needed?**
- `@EnableMethodSecurity` turns on the interceptor that enforces `@PreAuthorize`/`@PostAuthorize` on Spring-managed beans. Merely adding the Security dependency does not automatically enable method authorization.
- `setPermissionEvaluator(...)` allows the `hasPermission(...)` function in SpEL to invoke your implementation.
- `@Bean static` ensures the expression handler is published early before the Method Security infrastructure is created, matching the pattern recommended by official Spring Security 6.5 documentation.

**Do not** create a new `DefaultMethodSecurityExpressionHandler` per request expecting Spring-managed annotations to automatically switch handlers; it must be configured at the infrastructure level. If you already have a custom handler (role hierarchy, default role prefix, etc.), combine the settings on **the same handler** to avoid accidentally overwriting properties currently in use.

### 6.4. Domain record

**`src/main/java/com/example/permissions/Document.java`**

```java
package com.example.permissions;

public record Document(
        Long id,
        String tenantId,
        String owner,
        String title) {
}
```

The Java 17 record guarantees the data is not mutated in place; changing the title makes storage replace the instance. To the evaluator, `Document` is the **actual Java type** in the object overload, whereas the string `"Document"` is the **application-defined alias** in the id overload.

### 6.5. Trusted in-memory storage

**`src/main/java/com/example/permissions/DocumentStore.java`**

```java
package com.example.permissions;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {
    private final Map<Long, Document> documents = new ConcurrentHashMap<>();

    public DocumentStore() {
        reset();
    }

    public synchronized void reset() {
        documents.clear();
        documents.put(1L, new Document(1L, "t1", "alice", "Alice notes"));
        documents.put(2L, new Document(2L, "t1", "bob", "Bob notes"));
        documents.put(3L, new Document(3L, "t2", "carol", "Carol notes"));
    }

    public Optional<Document> findById(Long id) {
        return Optional.ofNullable(documents.get(id));
    }

    public Document rename(Long id, String title) {
        return documents.computeIfPresent(id,
            (key, previous) -> new Document(
                previous.id(),
                previous.tenantId(),
                previous.owner(),
                title
            )
        );
    }

    public boolean delete(Long id) {
        return documents.remove(id) != null;
    }
}
```

This is simulated storage, without transactions or distributed synchronization. It enables deterministic tests based on three known records. In a real system, use a repository/SQL, tenant filters, locks, or permission-conditioned queries; `ConcurrentHashMap` does not represent a transactional database.

### 6.6. PermissionEvaluator enforcing the naming convention

**`src/main/java/com/example/permissions/DocumentPermissionEvaluator.java`**

```java
package com.example.permissions;

import java.io.Serializable;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {
    private static final String TYPE_DOCUMENT = "Document";
    private final DocumentStore store;
    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public DocumentPermissionEvaluator(DocumentStore store) {
        this.store = store;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {
        if (!(targetDomainObject instanceof Document document)) {
            return false;
        }

        // Do not trust owner/tenant in an externally supplied object.
        // Always re-verify the real Document by ID from trusted storage.
        return hasPermission(
            authentication, document.id(), TYPE_DOCUMENT, permission
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

        // Fail-closed when ID/type/action does not match the permission naming contract.
        if (!(targetId instanceof Long id)
                || !TYPE_DOCUMENT.equals(targetType)
                || !(permission instanceof String action)) {
            return false;
        }

        Document document = store.findById(id).orElse(null);
        if (document == null) {
            return false;
        }

        // Every action is restricted to the exact tenant of the resource.
        if (!hasAuthority(authentication, "tenant:" + document.tenantId())) {
            return false;
        }

        boolean admin = hasAuthority(authentication, "ROLE_DOC_ADMIN");
        return switch (action) {
            case "read" ->
                hasAuthority(authentication, "document:read") || admin;
            case "edit" ->
                hasAuthority(authentication, "document:edit")
                    && (document.owner().equals(authentication.getName())
                        || admin);
            case "delete" ->
                hasAuthority(authentication, "document:delete") && admin;
            default -> false;
        };
    }

    private static boolean hasAuthority(
            Authentication authentication, String required) {
        for (GrantedAuthority authority : authentication.getAuthorities()) {
            if (required.equals(authority.getAuthority())) {
                return true;
            }
        }
        return false;
    }
}
```

**Reading the logic in order:** valid authentication → valid arguments and target type → record exists → matching tenant → known permission action → authority + owner/admin condition. Every unexpected branch **returns false**. Spring Security denies access when `@PreAuthorize`/`@PostAuthorize` receives `false`.

Several details here are design choices worth stating explicitly:
- `"Document"` (capital D) is the **official alias**; `"document"` is not accepted by this evaluator.
- `permission = "read"` (lowercase) is the **action**, not `"document:read"`.
- `"document:read"` is the `GrantedAuthority` name that must match exactly, with no auto-prefixing rule.
- `"tenant:t1"` is only considered trustworthy if an authentication provider/converter populates it after verifying membership; **never** trust arbitrary client-sent headers.
- `ROLE_DOC_ADMIN` does **not** bypass tenant membership. It allows bypassing the owner check in the `edit` branch without dropping the `document:edit` requirement; the `read` branch accepts the admin role in place of `document:read`; the `delete` branch requires both the admin role and `document:delete`.
- The object overload reloads `Document` from storage instead of trusting the input object's owner/tenant; this prevents spoofing metadata fields in objects passed from clients.
- The id form does not automatically return 404: it returns deny for a nonexistent record. A controller may choose how to map to 403/404 according to a policy that avoids leaking resource existence.
- The example uses exact case matching, not `contains`, `startsWith`, or unbounded wildcard permissions.

### 6.7. Service with both hasPermission syntaxes

**`src/main/java/com/example/permissions/DocumentService.java`**

```java
package com.example.permissions;

import java.util.NoSuchElementException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'read')")
    public Document readById(@P("id") Long id) {
        return store.findById(id)
            .orElseThrow(NoSuchElementException::new);
    }

    @PostAuthorize(
        "returnObject != null and hasPermission(returnObject, 'read')"
    )
    public Document readByObject(Long id) {
        return store.findById(id)
            .orElseThrow(NoSuchElementException::new);
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'edit')")
    public Document rename(@P("id") Long id, String title) {
        Document updated = store.rename(id, title);
        if (updated == null) {
            throw new NoSuchElementException();
        }
        return updated;
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'delete')")
    public boolean delete(@P("id") Long id) {
        return store.delete(id);
    }
}
```

`@P("id")` ensures the `#id` variable in SpEL binds to the right parameter, even when the program does not retain parameter-name metadata at compile time. The `rename` and `delete` methods use **pre-authorization** so mutations do not execute when denied. `readByObject` uses **post-authorization** solely for pure read operations, since the evaluator needs the object fetched from storage.

**Do not assume `@PostAuthorize` is a form of rollback.** If `readByObject` performs a write, sends an email, or publishes an event before returning, those side effects may already have occurred before access is denied.

## 7. Testing Spring Security: right names, right permissions, right resource

Simply unit-testing a function that returns true/false is not enough: you must verify that the `@PreAuthorize` annotation passes through the AOP proxy and calls the right evaluator. Use `@SpringBootTest` along with `@WithMockUser` to establish a security context for the tests.

**`src/test/java/com/example/permissions/DocumentServiceTest.java`**

```java
package com.example.permissions;

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
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class DocumentServiceTest {
    @Autowired
    DocumentService service;

    @Autowired
    DocumentStore store;

    @Autowired
    DocumentPermissionEvaluator evaluator;

    @BeforeEach
    void reset() {
        store.reset();
    }

    private Authentication currentAuthentication() {
        return SecurityContextHolder.getContext().getAuthentication();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void readInOwnTenantIsAllowed() {
        assertEquals(1L, service.readById(1L).id());
        assertEquals(2L, service.readById(2L).id());
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void crossTenantReadIsDenied() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.readById(3L)
        );
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"tenant:t1"})
    void missingReadAuthorityIsDenied() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.readById(1L)
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:edit"}
    )
    void ownerCanEdit() {
        Document updated = service.rename(1L, "New title");
        assertEquals("New title", updated.title());
        assertEquals("New title", store.findById(1L).orElseThrow().title());
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = {"tenant:t1", "document:edit"}
    )
    void nonOwnerCannotEdit() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.rename(1L, "Forbidden")
        );
        assertEquals("Alice notes", store.findById(1L).orElseThrow().title());
    }

    @Test
    @WithMockUser(
        username = "manager",
        authorities = {"tenant:t1", "document:edit", "ROLE_DOC_ADMIN"}
    )
    void adminCanEditSameTenant() {
        assertEquals("Managed", service.rename(1L, "Managed").title());
    }

    @Test
    @WithMockUser(
        username = "manager",
        authorities = {"tenant:t1", "document:edit", "ROLE_DOC_ADMIN"}
    )
    void adminCannotBypassTenantBoundary() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.rename(3L, "Cross tenant")
        );
    }

    @Test
    @WithMockUser(
        username = "manager",
        authorities = {"tenant:t1", "document:delete", "ROLE_DOC_ADMIN"}
    )
    void adminWithDeleteAuthorityMayDelete() {
        assertTrue(service.delete(2L));
        assertTrue(store.findById(2L).isEmpty());
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:delete"}
    )
    void nonAdminCannotDelete() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.delete(1L)
        );
        assertTrue(store.findById(1L).isPresent());
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void objectBasedPostAuthorizeAllowsTrustedDocument() {
        assertEquals(1L, service.readByObject(1L).id());
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void objectBasedPostAuthorizeRejectsCrossTenantDocument() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.readByObject(3L)
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void unknownIdIsDeniedBeforeRead() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.readById(999L)
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void unknownActionIsFailClosed() {
        assertFalse(evaluator.hasPermission(
            currentAuthentication(), 1L, "Document", "share"
        ));
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void uppercaseActionDoesNotMatchCanonicalAction() {
        assertFalse(evaluator.hasPermission(
            currentAuthentication(), 1L, "Document", "READ"
        ));
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void inconsistentPermissionNameIsDenied() {
        assertFalse(evaluator.hasPermission(
            currentAuthentication(), 1L, "Document", "document:read"
        ));
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void unknownTargetTypeIsDenied() {
        assertFalse(evaluator.hasPermission(
            currentAuthentication(), 1L, "Invoice", "read"
        ));
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"tenant:t1", "document:read"}
    )
    void forgedObjectTenantIsNotTrusted() {
        Document forged = new Document(
            3L, "t1", "alice", "Fake metadata"
        );
        assertFalse(evaluator.hasPermission(
            currentAuthentication(), forged, "read"
        ));
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

**Expected result:** 17 tests pass, 0 failures/errors. This result is deduced from the policy and fixtures in the code; Maven/JUnit logs may vary by environment. This lesson **does not claim to have executed Maven**.

Points worth checking:
- `@WithMockUser(authorities = {...})` creates the exact specified authority names; it does not automatically prepend `ROLE_` to `document:read`.
- `@WithMockUser(roles = "DOC_ADMIN")` creates the authority `ROLE_DOC_ADMIN`, but when you need to combine tenant and specific actions, use `authorities` explicitly in the test.
- The `forgedObjectTenantIsNotTrusted` test proves a forged object with id 3 and tenant `t1` **is still disallowed**: the evaluator reloads the canonical record id 3 belonging to tenant `t2`.
- The `inconsistentPermissionNameIsDenied` test proves `"document:read"` is **not** the action `"read"` in this evaluator API.
- The `unknownIdIsDeniedBeforeRead` test demonstrates the ID-form failure mode when a record does not exist; the target service method is not entered.
- State changes in `rename`/`delete` tests are reset before each test to avoid execution-order dependencies.

In a real system, similar tests should run against a real database and real role/tenant mappings; mock Authentication only verifies authorization and does not replace token validation or end-to-end login tests.

## 8. Naming for create, list, export, and result-set permissions

### 8.1. CREATE: when a resource does not exist yet, there is no ID to look up

When creating a document in tenant t1, there is usually **no document id yet** and no owner saved in the DB. Therefore the following expression is a reasonable business pattern:

```java
@PreAuthorize(
    "hasAuthority('document:create') and " +
    "@tenantPolicy.canCreate(authentication, #tenantId)"
)
public Document create(
        @P("tenantId") String tenantId, String title) {
    // Create the record after verifying permission on the tenant.
}
```

This is a **non-standalone integration snippet**: it requires a `tenantPolicy` bean, imports, a service, and a repository. Meaning: both the global `document:create` capability and create permission within the tenant must hold. Do not assume `hasPermission(#newId,'Document','create')` will work when the resource does not exist yet and the current evaluator returns false for unknown IDs.

Similarly, creating an invoice may be restricted by organization/project, quota, and workflow; the policy needs a verified parent object or request scope, not just an action string.

### 8.2. LIST and sensitive data in aggregates

`document:list` may allow querying records belonging to a tenant, but that does not automatically mean viewing all contents. When writing the query:

```sql
SELECT id, owner_id, title
FROM document
WHERE tenant_id = :authenticated_tenant_id
ORDER BY id
LIMIT :page_size;
```

This is a **SQL snippet** with bind parameters, not a complete schema. The tenant id must come from a verified security context, never unconditionally from a header or query string. Row counts, total counts, facets, and metadata can all be sensitive data; they need the same scope condition.

`@PostFilter("hasPermission(filterObject, 'read')")` filters results item-by-item, but it happens after data has already been loaded and can cause N+1 queries, inaccurate pagination, or immutable collection issues. For large volumes, pushing permission predicates into the SQL/ACL query before pagination is more efficient.

### 8.3. EXPORT, APPROVE, and DELETE should have distinct actions

`report:export` is usually riskier than `report:read` because data is taken outside the system. `invoice:approve` differs from `invoice:edit` because it may require separation of duties (the creator cannot approve their own invoice). `document:delete` differs from `document:edit` because of recoverability and retention.

Do not lump all three into `write` when the business needs accurate auditing. For a sensitive action, beyond authority and owner/tenant, you may also need:
- Workflow state, e.g. only `PENDING` invoices can be `approve`d.
- Verifying the approver is different from the creator.
- Amount limits and time windows.
- Fully authenticated/MFA/step-up depending on risk level.
- Audit decision including user, resource type, resource id, action, outcome, and policy version.

## 9. Permission storage plan and role/authority mapping

A permission management system can store a permission catalog:

```text
permission_definition
  resource_type | action  | authority_name
  --------------+---------+-----------------------
  document      | read    | document:read
  document      | edit    | document:edit
  document      | delete  | document:delete
  invoice       | approve | invoice:approve
  report        | export  | report:export
```

Roles and permissions have a many-to-many relationship:

```text
role
role_permission(role_id, permission_id)
user_role(user_id, role_id, scope_id)
resource_acl(resource_id, principal_id, action)
```

This is only a **conceptual diagram**, not concrete DDL. Depending on infrastructure, you can use a database, IAM, OPA, Spring Security ACL, or policy beans; do not assume `PermissionEvaluator` requires these exact tables.

When a user logs in, the authentication provider can aggregate roles into authorities, or the evaluator can query a permission service at check time. Consider the trade-offs:
- **JWT pre-loaded with authorities**: fast checks, but permissions can become stale until the token expires; requires a revocation/versioning strategy.
- **DB lookup every time**: reflects fresher permissions, but adds latency and N+1 risk when filtering collections; needs indexing/caching, invalidation, and fault-handling tests.
- **Per-resource ACL**: precise, but data/cache size can grow large and become hard to manage without standardized resource identities.
- **Attribute-based policy (ABAC)**: tenant, owner, state, and time may matter more than a static permission list.

In all cases, **the source of authorities must be trusted**. Never turn client-supplied `X-Role: admin` or `X-Permission: document:delete` into a `GrantedAuthority` without server-side authentication and authorization.

## 10. Permission naming convention as an internal API contract

A permission catalog can be managed with constants or enums in Java:

```java
package com.example.permissions;

public final class PermissionNames {
    public static final String DOCUMENT_READ = "document:read";
    public static final String DOCUMENT_EDIT = "document:edit";
    public static final String DOCUMENT_DELETE = "document:delete";

    public static final String TARGET_DOCUMENT = "Document";
    public static final String ACTION_READ = "read";
    public static final String ACTION_EDIT = "edit";
    public static final String ACTION_DELETE = "delete";

    private PermissionNames() {
    }
}
```

**This is an optional Java file** (not included in the runnable demo tree above because the sample code intentionally uses readable literals); you can add it to a project to avoid typos in Java code. Note that the `@PreAuthorize("...")` annotation requires a compile-time constant string literal expression; you cannot simply pass a runtime variable into an annotation. To reference constants in SpEL, you can use `T(com.example.permissions.PermissionNames).ACTION_EDIT` when SpEL configuration permits, though that makes annotations verbose; a fixed meta-annotation or policy bean may be clearer.

**Versioning:** Replacing `"document:edit"` with `"document:update"` can break permissions for users/JWTs already issued under the old name. When changing names:
1. Publish the new naming catalog and authorization constraints.
2. Inventory every consumer: token converters, service annotations, UI permission hints, batch jobs, gateways, DBs, and integration tests.
3. Migrate authorization data according to plan and track alongside policy version.
4. Maintain short-term backward compatibility if required, without unintentionally widening access; clean up old permissions after cutover.
5. Run positive/negative tests, especially for old tokens and users lacking permissions.

In logging/auditing, record the **canonical action name** and resource type/id rather than copying a long raw SpEL string; this makes it easy to analyze events such as “who was denied `invoice:approve` on invoice 123” without tying logic to implementation details.

## 11. Risks: standardized names are not enough if permission checks are wrong

### 11.1. Failing to check IDOR/BOLA

An endpoint with `hasAuthority('document:read')` that lets a request read `/documents/42` without checking tenant/owner/ACL can still suffer from **Broken Object Level Authorization (BOLA/IDOR)**. The `resource:action` convention is only a capability name and does not protect a specific instance without instance-level conditions.

### 11.2. Defaulting to deny when no permission matches

If new code calls `hasPermission(#id,'Document','archive')` while the evaluator does not yet support the `archive` action, the right outcome is **false**. Do not default unknown actions to `edit` or `read`. Only add a new action after defining a clear policy, granting permissions, and writing tests.

### 11.3. Inconsistent string matching

`Document`, `document`, and `DOCUMENT` are three different strings in the demo evaluator. `read` is not `READ`. If the system wants to allow aliases or normalization, perform it at a trusted entry point, validate strictly against an allowlist, and test malformed inputs as well. Never blindly lowercase case-sensitive identifiers.

### 11.4. SQL queries bypassing tenant checks

Even when the evaluator checks the tenant before an operation, a race condition can occur between check and update, or another code path may bypass the evaluator. For critical write operations, consider conditional SQL:

```sql
UPDATE document
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :authenticated_tenant_id
  AND owner_id = :authenticated_user_id;
```

Check the affected row count to detect when no matching record was updated. If admins are allowed to edit any document in the tenant, the owner condition should be relaxed only according to a **verified** admin policy—never drop the tenant restriction.

### 11.5. Confusing role hierarchy with record-level permission

A role hierarchy may make `ROLE_ADMIN` imply `document:read`, but it does **not** prove the user is allowed to read documents from another tenant. Role hierarchy resolves relationships between authorities; resource-level policy must still inspect the data.

### 11.6. Self-invocation bypassing the proxy

`@PreAuthorize` in Spring normally runs through an AOP proxy. If `service.outer()` calls `this.rename(...)` on the same bean, the interceptor may not be triggered. Do not instantiate services with `new` when you want annotation protection. Test real entry points, separate service boundaries, and consider method security at the business API layer.

### 11.7. Imbalance between policy cache and revoked permissions

If an evaluator caches `hasPermission` results but the cache key omits tenant, action, or resource id, it can return another request's authorization decision. At a minimum, the cache key must reflect principal/role version, tenant, resource id, action, and critical state factors. When owner/ACL changes, design invalidation or use a short TTL commensurate with the risk.

### 11.8. PostAuthorize and side effects

Because `@PostAuthorize` runs after the target method, it is better suited for checking **read results**. If the target creates/modifies data, sends an email, or calls an external API before access is denied, throwing `AccessDeniedException` does not automatically undo those effects. For write actions, prefer `@PreAuthorize`/in-transaction checks and guard updates with trusted data.

### 11.9. Tenant membership can become stale

The demo example uses `tenant:t1` as an authority on Authentication. In a real system, membership can change after a JWT is signed or a session is created; you need a revocation strategy, appropriate token lifetime, permission version, or DB lookup depending on sensitivity. Decisions based on membership scope must be paired with a permission refresh policy.

### 11.10. Do not leave the UI as the final permission check

An SPA hiding the Delete button based on `document:delete` improves UX, but a client can still call the API directly. The server must enforce the exact same policy across every access path, including batch jobs and message consumers.

## 12. Required QA matrix for every new permission

When adding an action such as `invoice:approve`, test at least:

| Input | What must be proven |
|---|---|
| Right resource + action + authority + tenant | Allow if all business conditions are met |
| Wrong authority | Deny |
| Missing tenant membership | Deny |
| Right authority but different tenant | Deny |
| Right tenant but wrong owner/role | Deny if policy requires owner/role |
| Nonexistent ID | Deny or handle not-found per contract; never accidentally allow |
| Unsupported targetType | Deny |
| Unsupported action / wrong case | Deny |
| Object parameter with forged owner/tenant | Deny based on canonical storage |
| Revoked permission | Deny once revocation/invalidation takes effect |
| Multiple simultaneous roles/authorities | Access is not widened beyond policy |
| Invoked from another entry point | Does not bypass AOP/authorization |
| Downstream system error/timeout | Does not grant access by default on lookup failure |

Documentation for a new permission should answer five questions: **what is the canonical name, who is granted it, which resource does it apply to, what owner/tenant/state conditions apply, and which deny tests guard the boundary?**

## 13. Adoption checklist

- [ ] Catalog resource types and actions using consistent canonical names.
- [ ] Clearly distinguish `GrantedAuthority("document:edit")`, `targetType="Document"`, and `permission="edit"`.
- [ ] Roles prefixed with `ROLE_` are not conflated with action permissions.
- [ ] Unknown type/action/id and null inputs are rejected (fail-closed).
- [ ] `@EnableMethodSecurity` is enabled; the evaluator is wired into `MethodSecurityExpressionHandler`.
- [ ] `hasPermission(#id,'Document','edit')` is applied **before** side effects; the object overload is used only with trusted data or canonical reload.
- [ ] Tenant/owner come from the resource and trusted security context, not arbitrary request fields.
- [ ] Create/list/export/approve/delete permissions are defined separately according to risk level.
- [ ] Permissions on large lists are filtered in queries when performance/accurate pagination matters.
- [ ] Role mapping, JWT authority converter, DB ACL, and annotations share the same naming catalog.
- [ ] Integration tests go through Spring-managed proxies and cover allow/deny, cross-tenant records, unknown actions, wrong casing, and forged objects.
- [ ] Permission renames include migration/versioning and do not over-grant during the transition period.

## 14. Official documentation

- [Spring Security 6.5 — Method Security: Expressing Authorization with SpEL](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — `hasPermission`, method parameters with `@P`, and configuring `MethodSecurityExpressionHandler`.
- [Spring Security 6.5 — PermissionEvaluator API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/PermissionEvaluator.html) — the two overloads for domain object or (targetId, targetType, permission).
- [Spring Security 6.5 — SecurityExpressionOperations API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/expression/SecurityExpressionOperations.html) — `hasPermission(Object,Object)` and `hasPermission(Object,String,Object)`.
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html) — authorities, authentication, and how authorization is modeled.

**Remember:** `resource:action` is a **consistent capability name**, while `PermissionEvaluator` turns the question “does the caller have `action` permission on this `resource instance`?” into a decision backed by **trusted data**. Clear names help management, auditing, and testing; actual authorization is only safe when the evaluator also properly checks **tenant, owner, record state, and execution timing**.