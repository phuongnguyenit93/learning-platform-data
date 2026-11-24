# Parent Resource, Child Resource, and Nested Path Permissions in Spring Security

## 1. The Problem: A Valid URL Does Not Guarantee Only Permitted Resources Are Targeted

A document management application organizes data as a tree:

```text
Organization 10 (North)
├── Project 100 (public to organization members)
│   ├── Document 1000 (owner: alice, shared VIEWER to bob)
│   ├── Document 1001 (owner: alice, shared EDITOR to bob)
│   └── Document 1002 (owner: manager, not shared)
└── Project 110 (private: only alice and manager)
    └── Document 1100 (owner: alice, still shared EDITOR to bob)

Organization 20 (South)
└── Project 200
    └── Document 2000 (owner: carol)
```

The API uses nested paths:

```http
GET /api/orgs/10/projects/100/documents/1000
GET /api/orgs/10/projects/100/documents
PUT /api/orgs/10/projects/100/documents/1001
```

These are **illustrative HTTP requests**, not shell commands. When Bob calls `/orgs/10/projects/100/documents/1000`, **three separate questions** must be answered:

1. Does Bob belong to **Organization 10**?
2. Does Project 100 **actually belong to Organization 10** and is Bob allowed to traverse into that project?
3. Does Document 1000 **actually belong to Project 100** and does Bob have **read** permission on this document?

If you only check `hasAuthority("document:read")` or only check `projectId` in the URL, a user can swap the trailing ID to access another document—a **Broken Object Level Authorization (BOLA/IDOR)** flaw. Conversely, checking only the child document can miss that the parent project has restricted access.

**Central principle:** Parent permissions, child permissions, and path traversal permissions are distinct policies. Never assume "can view organization = can view every project = can view every document". Client-sent paths must be checked against **the canonical parent–child relationship in the database**, never trusted just because the URL holds three parameters.

This lesson presents the tree authorization model, nested REST paths, explicit inheritance when designed, checks at the Spring Security and repository layers, security pitfalls, and a **Java 17/Spring Boot 3.5.6/Spring Security 6.5.x example** with integration tests.

## 2. Three Permission Dimensions: Scope, Traversal, and Operation

### 2.1. Parent Access Does Not Imply Child Access

A user can:
- **View organization**: know the basic name/metadata of the organization.
- **Traverse project**: enter the project and view metadata or list documents they have rights to.
- **Read document**: read the contents of a specific document.
- **Edit document**: modify content after verifying owner, grant, or scoped role.

A policy may require **both parent and child permissions**:

```text
canReadDocument(user, org, project, document)
  = authenticated(user)
    AND memberOf(user, org)
    AND parentOf(project, org)
    AND canTraverseProject(user, project)
    AND parentOf(document, project)
    AND canReadSpecificDocument(user, document)
```

This is **pseudo-code**. Here `parentOf` means the real foreign-key relationship from server data, not URL string comparison. If any condition is false or unknown, return **deny**.

### 2.2. Illustrative Matrix

| Scenario | GET document | Reason |
|---|---|---|
| Alice reads Document 1000 via Org 10 / Project 100 | Allow | Right tenant/project, Alice is owner |
| Bob reads Document 1000 via Org 10 / Project 100 | Allow | Org member, open project, shared VIEWER |
| Bob edits Document 1000 | Deny | VIEWER cannot edit |
| Bob edits Document 1001 | Allow | Shared EDITOR, valid chain |
| Bob reads Document 1002 | Deny | Same project, yet not owner/share/admin |
| Bob reads Document 1100 | Deny | Even with EDITOR share on document, Project 110 is private |
| Bob reads Document 1000 via Org 10 / Project 110 | Deny | Document 1000 does not belong to Project 110 |
| Bob reads Document 1000 via Org 20 / Project 100 | Deny | Project 100 does not belong to Org 20 |
| Org 10 Manager reads Document 1002 | Allow | Role + admin binding matches Org 10 |
| Org 10 Manager reads Document 2000 | Deny | Does not belong to Org 20 |

**The demo's policy** intentionally requires traversal through the parent project even when a document is shared directly. Some systems allow share links to bypass parent folder view permissions; if choosing that design, document the exception, prevent leaking parent metadata, and test it. Spring Security does not impose a single rule across all tree models.

### 2.3. Three Different Types of Inheritance

| Mechanism | Purpose | What Does Not Happen Automatically |
|---|---|---|
| **Role hierarchy** (e.g., ROLE_ADMIN includes ROLE_USER) | Expands `GrantedAuthority` | Does not verify which project a document belongs to |
| **Spring Security ACL parent/child** | Can inherit ACEs via `parentAcl` and `entriesInheriting` | Does not establish URLs or domain FK relationships |
| **Business resource hierarchy** | Organization → Project → Document, based on DB relations | Does not become a Spring Security policy without code |

Do not mislabel it "role hierarchy" when you mean data-tree authorization. Roles, ACL inheritance, and business-parent scope are three independent concepts.

## 3. Nested Paths: Path Variables Are Client-Chosen Data

Examples:

```http
GET /api/orgs/10/projects/100/documents/1000
GET /api/orgs/10/projects/110/documents/1000
GET /api/orgs/20/projects/100/documents/1000
```

Three requests use the **same document ID**, yet the latter two describe **non-existent** parent–child chains.

If the controller merely executes:

```java
Document doc = repository.findById(documentId).orElseThrow();
return doc;
```

then `orgId` and `projectId` in the URL go unverified; callers can probe arbitrary IDs to read without authorization. Proper verification requires a query or policy verifying:

```sql
SELECT d.id, d.title
FROM document d
JOIN project p ON p.id = d.project_id
WHERE d.id = :document_id
  AND d.project_id = :project_id
  AND p.organization_id = :organization_id;
```

This is **illustrative SQL for the canonical relationship**: it does not yet check user membership, ACLs, owner, or private projects. A complete policy must also check **who** is calling and **what action** is permitted. Use bind parameters in JDBC/ORM, never concatenating strings directly from the URL.

### 3.1. Choosing HTTP Status on Mismatch

When the user is logged in yet unauthorized, you can return **403 Forbidden**. For sensitive resources, many APIs intentionally return **404 Not Found** for both non-existent and unauthorized IDs to reduce existence disclosure. Both approaches require a consistent policy; never leak "another tenant's project exists" via detailed error messages before authorizing.

The example below chooses 403 for authenticated cases with wrong paths or missing permissions because test outcomes are easy to read; anonymous access to authenticated routes gets 401 via HTTP Basic. This is the **demo's response convention**, not Spring Security's sole mandate.

### 3.2. Matcher Order and Limits of HTTP Authorization

In servlet security, `AuthorizationFilter` evaluates `requestMatchers` in order; **the first matching rule** wins. For example:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/orgs/**").authenticated()
    .anyRequest().denyAll()
);
```

This is a **configuration** snippet, not standalone compilable. It checks for Authentication, yet **cannot verify** that `orgId`, `projectId`, and `documentId` belong together. Therefore the demo enables `@EnableMethodSecurity` and verifies data relationships at the **service layer**. If there are multiple servlets, custom context paths, dispatchers, or path matchers, test exact routes in `SecurityFilterChain`.

Another trap is placing a broad `/api/**` rule before a narrower admin rule, causing the admin rule never to be reached. For nested endpoints, keep the HTTP layer as the authentication/routing gate and let service policies decide object-level access.

## 4. Designing a Policy for Data Trees

### 4.1. Start from the Canonical Record

Never derive a document's organization solely from a query parameter. Relational model:

```text
organization(id)
project(id, organization_id, is_private)
document(id, project_id, owner_id, title)
organization_membership(organization_id, user_id)
organization_admin(organization_id, user_id)
private_project_membership(project_id, user_id)
document_share(document_id, user_id, level)
```

In a real application, foreign keys:
- `project.organization_id → organization.id`.
- `document.project_id → project.id`.
- Membership/share tables use foreign keys to user, project, and document.
- If `tenant_id` appears in multiple tables, use composite FKs or constrained queries to prevent creating documents mismatched across tenants.

Never allow clients to edit `project_id`/`tenant_id` through unchecked payloads. If moving a document to another project, verify permissions on **both source and destination**, handle ACL/share grants, and update the canonical parent inside a transaction.

### 4.2. Private Projects: Parent Permission Is a Gate

In the demo:
- Project 100: every member of Organization 10 can **traverse**.
- Project 110: only users in `private_project_membership` or tenant admins with a valid binding can **traverse**.
- Project 200: similar to Project 100, but under Organization 20.

Bob is shared as EDITOR on Document 1100, yet Project 110 is private and Bob lacks project membership, so Bob **cannot** read/edit Document 1100. Only when policy explicitly decides "direct link sharing bypasses parent" should it behave differently—implemented as an intentional branch, never an accidental bug from a missing check.

### 4.3. Permissions on an Individual Document

Along a valid path, the demo grants:
- **READ** if caller is owner, holds VIEWER/EDITOR share, or is an org admin bound to that organization.
- **EDIT** if caller is owner, holds EDITOR share, or is a properly scoped org admin.
- **LIST documents of a project** if caller can traverse the project **and** holds `project:list` (or is a properly scoped org admin); then return only documents the caller **can READ individually**.

This separates **list** from **read**. Allowing project listing does not mean returning all child contents. Some products have `list-metadata` separate from `read-content`; if needed, separate metadata and aggregate counts as well.

### 4.4. Admins Must Be Scoped

A principal holding `ROLE_ORG_ADMIN` authorized only for Org 10 must not read Org 20 documents. The demo requires simultaneously:
1. Caller is an org member in the trusted directory.
2. Authentication holds `ROLE_ORG_ADMIN`.
3. Database holds an admin binding for **that exact `orgId`**.

Never use `hasRole('ADMIN') OR canRead(...)` as a blanket policy, because the OR branch can bypass tenant boundaries. If a system administrator is needed, create a dedicated use case and permission, with auditing/approval and strict tests.

## 5. Can a Parent Resource Grant Permissions to Children?

Three common options:

**A. Strict intersection (default in the demo):**
```text
canAccessChild = canTraverseParent AND canAccessChildDirectly
```

Pros: fewer surprising privileges, easy to explain. Cons: sharing a child to a user not in the parent has no effect.

**B. Explicit inheritance:**
```text
canAccessChild =
    parentBoundarySatisfied
    AND (directChildGrant OR inheritedGrantFromParent)
```

Define which parent grants may inherit; e.g., `project:read-children` can flow down to documents, whereas `project:edit` should not automatically imply deleting documents. Document depth, privilege levels, exceptions, revocation, and caching clearly.

**C. Share-link exception:**
```text
canAccessChild =
    (validScopedShareTokenWithNoParentMetadataLeak)
    OR (ordinaryParentAndChildPolicy)
```

Requires unguessable tokens, expiry, revocation, permission scoping, and preventing parent information leaks. Never infer from `?shared=true` or a client-picked URL that the user bypasses parent authorization.

### 5.1. With Spring Security ACL Inheritance

Spring Security ACL stores `parent_object` and `entries_inheriting` in `acl_object_identity`. A conceptual setup (placed inside a service with proper ACL configuration):

```java
ObjectIdentity parentId =
    new ObjectIdentityImpl(Project.class, 100L);
ObjectIdentity childId =
    new ObjectIdentityImpl(Document.class, 1000L);

Acl parentAcl = aclService.readAclById(parentId);
MutableAcl childAcl =
    (MutableAcl) aclService.readAclById(childId);

childAcl.setParent(parentAcl);
childAcl.setEntriesInheriting(true);
mutableAclService.updateAcl(childAcl);
```

This is an **integration pattern**, requiring Spring Security ACL classes/imports, DB schema, ACL admin policies, and transactions. It allows the child ACL to consider ACEs inherited from the parent (depending on granting strategy); it does **not** verify canonical `document.project_id` or automatically add `tenant_id` to policies. To stay safe:
- Never link a parent ACL from another tenant unless an explicit policy permits it.
- Test deny ACEs, ordering, local ACEs vs inherited ACEs, and revoking parent rights.
- When moving a document to a new project, review parent ACLs, old grants, and caches.
- Never confuse `roleHierarchy` with `parentAcl`.

The runnable demo below **does not use the ACL module** so learners clearly see parent path relationships, tenant membership, role scoping, and child-level sharing. ACL inheritance here is an extension option, not an "automatically enabled feature".

## 6. Runnable Demo: Java 17, Spring Boot 3.5.6, Spring Security 6.5.x

The application stores fixtures in `Map`s, has a REST controller with nested paths, a policy bean enforcing canonical relationships, `@PreAuthorize` services, and JUnit + MockMvc tests. It requires no DB and is easy to run. Section 8 shows how to replace this with constrained JDBC/JPA queries.

### 6.1. File Tree

```text
nested-resource-authorization/
  pom.xml
  src/main/java/com/example/nested/
    NestedAuthorizationApplication.java
    SecurityConfig.java
    Catalog.java
    TreeAuthorization.java
    DocumentService.java
    DocumentController.java
  src/test/java/com/example/nested/
    NestedAuthorizationTest.java
```

### 6.2. pom.xml

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
  <artifactId>nested-resource-authorization</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

`spring-boot-starter-security` supports Method Security but **does not enable it automatically**; `@EnableMethodSecurity` is declared in `SecurityConfig`. Tests use `@WithMockUser` without implementing real passwords or JWTs.

### 6.3. Spring Boot Entrypoint

**`src/main/java/com/example/nested/NestedAuthorizationApplication.java`**

```java
package com.example.nested;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NestedAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(NestedAuthorizationApplication.class, args);
    }
}
```

### 6.4. HTTP Security and Method Security

**`src/main/java/com/example/nested/SecurityConfig.java`**

```java
package com.example.nested;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

`SecurityFilterChain` requires authentication on all `/api/**` routes and denies everything else. It **does not grant** document permissions itself. That logic lives in `DocumentService`, so calls from services/batches/jobs must still pass object-level authorization when invoked through a Spring proxy.

The demo keeps Spring Security's default CSRF protection: HTTP PUT tests must supply `csrf()`. Do not disable CSRF just to make tests easier to write; in pure stateless bearer-token REST APIs without cookies, CSRF strategy differs and must be configured based on the real authentication mechanism.

### 6.5. Catalog: Server-Side Parent–Child Relations and Grants

**`src/main/java/com/example/nested/Catalog.java`**

```java
package com.example.nested;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class Catalog {
    public record Project(Long id, Long orgId, boolean privateProject) {}
    public record Document(
            Long id, Long projectId, String owner, String title) {}
    public enum ShareLevel { VIEWER, EDITOR }

    private final Map<Long, Project> projects = Map.of(
        100L, new Project(100L, 10L, false),
        110L, new Project(110L, 10L, true),
        200L, new Project(200L, 20L, false)
    );

    private final Set<String> orgMembers = Set.of(
        "10:alice", "10:bob", "10:manager",
        "20:carol", "20:dave"
    );

    private final Set<String> adminBindings = Set.of(
        "10:manager", "20:carol"
    );

    private final Set<String> privateProjectMembers = Set.of(
        "110:alice", "110:manager"
    );

    private final Map<String, ShareLevel> documentShares = Map.of(
        "1000:bob", ShareLevel.VIEWER,
        "1001:bob", ShareLevel.EDITOR,
        "1100:bob", ShareLevel.EDITOR
    );

    private final ConcurrentMap<Long, Document> documents =
        new ConcurrentHashMap<>();

    public Catalog() {
        reset();
    }

    public synchronized void reset() {
        documents.clear();
        documents.put(1000L,
            new Document(1000L, 100L, "alice", "Alice notes"));
        documents.put(1001L,
            new Document(1001L, 100L, "alice", "Team draft"));
        documents.put(1002L,
            new Document(1002L, 100L, "manager", "Manager plan"));
        documents.put(1100L,
            new Document(1100L, 110L, "alice", "Private strategy"));
        documents.put(2000L,
            new Document(2000L, 200L, "carol", "South report"));
    }

    public Project project(Long id) {
        return id == null ? null : projects.get(id);
    }

    public Document document(Long id) {
        return id == null ? null : documents.get(id);
    }

    public boolean isOrgMember(Long orgId, String username) {
        return orgId != null
            && username != null
            && orgMembers.contains(orgId + ":" + username);
    }

    public boolean isOrgAdminBinding(Long orgId, String username) {
        return orgId != null
            && username != null
            && adminBindings.contains(orgId + ":" + username);
    }

    public boolean isPrivateProjectMember(
            Long projectId, String username) {
        return projectId != null
            && username != null
            && privateProjectMembers.contains(projectId + ":" + username);
    }

    public ShareLevel shareLevel(Long id, String username) {
        if (id == null || username == null) {
            return null;
        }
        return documentShares.get(id + ":" + username);
    }

    public List<Document> documentsForProject(Long projectId) {
        return documents.values().stream()
            .filter(d -> d.projectId().equals(projectId))
            .sorted(Comparator.comparing(Document::id))
            .toList();
    }

    public Document rename(Long projectId, Long id, String newTitle) {
        Document updated = documents.computeIfPresent(id, (key, old) ->
            old.projectId().equals(projectId)
                ? new Document(old.id(), old.projectId(),
                    old.owner(), newTitle)
                : old
        );

        if (updated == null || !updated.projectId().equals(projectId)) {
            throw new IllegalStateException("Path relation changed");
        }
        return updated;
    }
}
```

This is **demo storage**, not a production security database. `Catalog` holds only server-seeded relationships and shares; its methods never accept an arbitrary client-claimed `owner`/`role` string as proof.

Observe:
- Project 100 belongs to Org 10.
- Project 110 belongs to Org 10, yet is private.
- Documents 1000/1001/1002 belong to Project 100.
- Document 1100 belongs to Project 110; despite Bob's EDITOR share, Bob is not in the private project.
- Document 2000 belongs to Project 200 of Org 20.
- Manager has an admin binding in Org 10; the role in Authentication is checked as well.
- `reset()` resets state before each test; in production, replace with repository/JPA, FKs, and transactions.

### 6.6. TreeAuthorization: Level-by-Level Check, Fail-Closed

**`src/main/java/com/example/nested/TreeAuthorization.java`**

```java
package com.example.nested;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("treeAuth")
public class TreeAuthorization {
    private final Catalog catalog;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public TreeAuthorization(Catalog catalog) {
        this.catalog = catalog;
    }

    private boolean hasAuthority(Authentication auth, String expected) {
        for (GrantedAuthority a : auth.getAuthorities()) {
            if (expected.equals(a.getAuthority())) {
                return true;
            }
        }
        return false;
    }

    private boolean isOrgAdmin(Authentication auth, Long orgId) {
        return hasAuthority(auth, "ROLE_ORG_ADMIN")
            && catalog.isOrgAdminBinding(orgId, auth.getName());
    }

    private boolean canTraverse(
            Authentication auth, Long orgId, Long projectId) {

        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)
                || orgId == null || projectId == null) {
            return false;
        }

        Catalog.Project project = catalog.project(projectId);

        // Check CANONICAL project -> organization relationship.
        if (project == null || !orgId.equals(project.orgId())) {
            return false;
        }

        if (!catalog.isOrgMember(orgId, auth.getName())) {
            return false;
        }

        // Private project requires parent traversal permission.
        return !project.privateProject()
            || catalog.isPrivateProjectMember(projectId, auth.getName())
            || isOrgAdmin(auth, orgId);
    }

    public boolean canList(
            Authentication auth, Long orgId, Long projectId) {
        return canTraverse(auth, orgId, projectId)
            && (hasAuthority(auth, "project:list")
                || isOrgAdmin(auth, orgId));
    }

    public boolean canRead(
            Authentication auth, Long orgId,
            Long projectId, Long documentId) {

        if (!canTraverse(auth, orgId, projectId)) {
            return false;
        }

        Catalog.Document doc = catalog.document(documentId);

        // Check CANONICAL document -> project relationship.
        if (doc == null || !projectId.equals(doc.projectId())) {
            return false;
        }

        return auth.getName().equals(doc.owner())
            || catalog.shareLevel(documentId, auth.getName())
                == Catalog.ShareLevel.VIEWER
            || catalog.shareLevel(documentId, auth.getName())
                == Catalog.ShareLevel.EDITOR
            || isOrgAdmin(auth, orgId);
    }

    public boolean canWrite(
            Authentication auth, Long orgId,
            Long projectId, Long documentId) {

        if (!canTraverse(auth, orgId, projectId)) {
            return false;
        }

        Catalog.Document doc = catalog.document(documentId);
        if (doc == null || !projectId.equals(doc.projectId())) {
            return false;
        }

        return auth.getName().equals(doc.owner())
            || catalog.shareLevel(documentId, auth.getName())
                == Catalog.ShareLevel.EDITOR
            || isOrgAdmin(auth, orgId);
    }
}
```

**Critical deny flow:**
1. Authentication null, anonymous, or unauthenticated → deny.
2. Project ID does not exist or does not belong to `orgId` in URL → deny.
3. Caller is not a member of that Org → deny.
4. Project is private and caller is not a private member / bound admin → deny.
5. Document ID does not exist or does not belong to `projectId` in URL → deny.
6. Caller is neither owner, valid share recipient, nor bound org admin → deny.

This checker **never** uses `startsWith("/orgs/10")` to decide the tenant; it compares IDs against trusted records. Even someone holding `ROLE_ORG_ADMIN` without an admin binding for that org cannot bypass the parent check.

### 6.7. DocumentService: Object-Level Authorization Lives in the Service

**`src/main/java/com/example/nested/DocumentService.java`**

```java
package com.example.nested;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {
    public record DocumentView(Long id, String title) {}

    private final Catalog catalog;
    private final TreeAuthorization policy;

    public DocumentService(Catalog catalog, TreeAuthorization policy) {
        this.catalog = catalog;
        this.policy = policy;
    }

    private static DocumentView view(Catalog.Document d) {
        return new DocumentView(d.id(), d.title());
    }

    @PreAuthorize(
        "@treeAuth.canRead(authentication, " +
        "#orgId, #projectId, #documentId)"
    )
    public DocumentView read(
            @P("orgId") Long orgId,
            @P("projectId") Long projectId,
            @P("documentId") Long documentId) {
        return view(catalog.document(documentId));
    }

    @PreAuthorize(
        "@treeAuth.canList(authentication, #orgId, #projectId)"
    )
    public List<DocumentView> list(
            @P("orgId") Long orgId,
            @P("projectId") Long projectId) {

        Authentication caller =
            SecurityContextHolder.getContext().getAuthentication();

        // LIST is authorized, yet each element must pass READ individually.
        return catalog.documentsForProject(projectId).stream()
            .filter(d -> policy.canRead(
                caller, orgId, projectId, d.id()))
            .map(DocumentService::view)
            .toList();
    }

    @PreAuthorize(
        "@treeAuth.canWrite(authentication, " +
        "#orgId, #projectId, #documentId)"
    )
    public DocumentView rename(
            @P("orgId") Long orgId,
            @P("projectId") Long projectId,
            @P("documentId") Long documentId,
            String title) {

        if (title == null || title.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Title required"
            );
        }

        Authentication caller =
            SecurityContextHolder.getContext().getAuthentication();

        // Recheck in service. Production needs row lock/version/SQL predicate.
        if (!policy.canWrite(caller, orgId, projectId, documentId)) {
            throw new AccessDeniedException("Permission changed");
        }

        return view(catalog.rename(projectId, documentId, title));
    }
}
```

`@P` fixes the SpEL variable names `#orgId`, `#projectId`, and `#documentId`. `@EnableMethodSecurity` lets the Spring AOP proxy intercept calls before the method body; if a caller uses `new DocumentService(...)` or self-invocation within the same bean, the annotation can be bypassed.

**Why protect the service instead of only the controller?** The same business logic can be called via HTTP, schedulers, message consumers, or other APIs. Service-level checks make permission boundaries reusable; however, ensure entry points do not bypass the proxy and repository/queries still enforce tenant predicates when moving to a real database.

**Why must LIST filter each document individually?** Viewing Project 100 does not allow returning manager's Document 1002. This is an in-memory example; with large databases, push READ/tenant/ACL conditions into SQL before pagination to avoid N+1 queries and metadata/count leaks.

### 6.8. DocumentController: Three Nested Endpoints

**`src/main/java/com/example/nested/DocumentController.java`**

```java
package com.example.nested;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orgs")
public class DocumentController {
    public record RenameBody(String title) {}

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{orgId}/projects/{projectId}/documents/{documentId}")
    public DocumentService.DocumentView read(
            @PathVariable("orgId") Long orgId,
            @PathVariable("projectId") Long projectId,
            @PathVariable("documentId") Long documentId) {
        return service.read(orgId, projectId, documentId);
    }

    @GetMapping("/{orgId}/projects/{projectId}/documents")
    public List<DocumentService.DocumentView> list(
            @PathVariable("orgId") Long orgId,
            @PathVariable("projectId") Long projectId) {
        return service.list(orgId, projectId);
    }

    @PutMapping("/{orgId}/projects/{projectId}/documents/{documentId}")
    public DocumentService.DocumentView rename(
            @PathVariable("orgId") Long orgId,
            @PathVariable("projectId") Long projectId,
            @PathVariable("documentId") Long documentId,
            @RequestBody RenameBody body) {
        return service.rename(
            orgId, projectId, documentId,
            body == null ? null : body.title()
        );
    }
}
```

The controller never infers permissions from the path. It forwards all three IDs straight to the service, where `TreeAuthorization` checks them against the canonical hierarchy. Read/list endpoints return JSON; the edit endpoint uses PUT and a JSON body such as:

```json
{"title":"Revised draft"}
```

The demo API omits DTO validators, audit logs, and optimistic locking; `DocumentService` rejects blank titles and checks permissions before updating.

## 7. Spring Security Integration Tests and Forged Paths

**`src/test/java/com/example/nested/NestedAuthorizationTest.java`**

```java
package com.example.nested;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class NestedAuthorizationTest {
    @Autowired MockMvc mvc;
    @Autowired Catalog catalog;
    @Autowired DocumentService service;

    @BeforeEach
    void reset() {
        catalog.reset();
    }

    private static String documentPath(
            long org, long project, long document) {
        return "/api/orgs/" + org
            + "/projects/" + project
            + "/documents/" + document;
    }

    @Test
    @WithMockUser(username = "bob")
    void viewerReadsSharedDocument() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1000)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(1000))
            .andExpect(jsonPath("$.title").value("Alice notes"));
    }

    @Test
    @WithMockUser(username = "bob")
    void editorAlsoReadsSharedDocument() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1001)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob")
    void sameProjectDoesNotGrantReadOnEveryChild() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1002)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void privateProjectBlocksDirectDocumentShare() throws Exception {
        mvc.perform(get(documentPath(10, 110, 1100)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void fakeProjectInUrlCannotMoveDocument() throws Exception {
        mvc.perform(get(documentPath(10, 110, 1000)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void fakeOrganizationInUrlCannotMoveProject() throws Exception {
        mvc.perform(get(documentPath(20, 100, 1000)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void userCannotReadDifferentOrganization() throws Exception {
        mvc.perform(get(documentPath(20, 200, 2000)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "project:list")
    void listingShowsOnlyReadableDocuments() throws Exception {
        mvc.perform(get("/api/orgs/10/projects/100/documents"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)))
            .andExpect(jsonPath("$[0].id").value(1000))
            .andExpect(jsonPath("$[1].id").value(1001));
    }

    @Test
    @WithMockUser(username = "bob")
    void documentReadDoesNotGrantProjectList() throws Exception {
        mvc.perform(get("/api/orgs/10/projects/100/documents"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "project:list")
    void privateProjectListStillDenied() throws Exception {
        mvc.perform(get("/api/orgs/10/projects/110/documents"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void viewerCannotEdit() throws Exception {
        mvc.perform(put(documentPath(10, 100, 1000))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
        assertEquals("Alice notes", catalog.document(1000L).title());
    }

    @Test
    @WithMockUser(username = "bob")
    void editorCanEditSharedDocument() throws Exception {
        mvc.perform(put(documentPath(10, 100, 1001))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Revised\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Revised"));
        assertEquals("Revised", catalog.document(1001L).title());
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerCanReadChildInPrivateProject() throws Exception {
        mvc.perform(get(documentPath(10, 110, 1100)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "manager", roles = "ORG_ADMIN")
    void boundOrgAdminReadsAnyChildInOwnOrg() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1000)))
            .andExpect(status().isOk());
        mvc.perform(get(documentPath(10, 110, 1100)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "manager", roles = "ORG_ADMIN")
    void orgAdminCannotCrossOrgScope() throws Exception {
        mvc.perform(get(documentPath(20, 200, 2000)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "ORG_ADMIN")
    void roleWithoutOrgAdminBindingIsNotEnough() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1002)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "mallory", roles = "ORG_ADMIN")
    void roleWithoutOrgMembershipIsNotEnough() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1000)))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedRequestIsChallenged() throws Exception {
        mvc.perform(get(documentPath(10, 100, 1000)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice")
    void unknownDocumentFailsClosed() throws Exception {
        mvc.perform(get(documentPath(10, 100, 9999)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void missingCsrfBlocksPutEvenForOwner() throws Exception {
        mvc.perform(put(documentPath(10, 100, 1000))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Cannot bypass CSRF\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void methodSecurityWorksWithoutHttpController() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(10L, 100L, 1002L));
    }

    @Test
    @WithMockUser(username = "alice")
    void methodSecurityRejectsForgedParentIds() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(20L, 100L, 1000L));
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

**Expected result:** 22 JUnit tests pass (no failures/errors) when using the exact dependencies and configuration above. This is an **expectation based on the code**, not a claim that Maven was executed. The tests use `@WithMockUser` to test authorization without simulating a real JWT or password login system.

Most valuable takeaways:
- **Wrong `orgId` or `projectId` in URL** → denied even if the document ID really exists.
- **Same project** does not imply reading every document.
- **EDITOR share on child** does not pierce a private parent project.
- **List permission** is separate from read permission: returns only documents with READ, not the entire tree.
- **Admin role without org binding** → denied.
- **Admin valid for Org 10 calling Org 20** → denied.
- **PUT missing CSRF** → denied by default web security config.
- **Direct service calls** still go through `@PreAuthorize` and are blocked when using the Spring bean.

### 7.1. Core Outcome Matrix

| Caller | URL / Action | Expected |
|---|---|---|
| bob | GET Org10/Project100/Document1000 | 200 |
| bob | GET Org10/Project100/Document1002 | 403 |
| bob | GET Org10/Project110/Document1100 | 403 |
| bob | GET Org20/Project100/Document1000 | 403 |
| bob with `project:list` | GET Project100 list | 200; only 2 documents |
| bob without `project:list` | GET Project100 list | 403 |
| bob | PUT Document1000 with CSRF | 403 |
| bob | PUT Document1001 with CSRF | 200 |
| manager/ROLE_ORG_ADMIN | GET document in Org10 | 200 |
| manager/ROLE_ORG_ADMIN | GET document in Org20 | 403 |
| anonymous | GET any protected `/api/**` | 401 |

HTTP 403 in denial scenarios reflects complete authentication followed by failed method authorization; 401 is HTTP Basic's challenge for unauthenticated requests. Changing login forms, exception handlers, or API gateways may alter HTTP status mappings.

## 8. Replacing Map with JDBC/JPA: Queries Must Protect Both Parent and Child

A simple Map example clarifies policy, whereas a production API often backs onto millions of documents. Loading all documents into RAM and calling `filter(d -> canRead(...))` can cause:
- **N+1 queries** checking shares/ACLs per row.
- Broken pagination: fetching 20 rows and filtering down to 3 while total pages/counts ignore permissions.
- Metadata leaks through total counts, facets, sorters, or unscoped aggregates.
- Races: between permission check and data fetch/edit, the project changed parent or the share was revoked.

### 8.1. Querying One Document with Canonical Parent Path

```sql
SELECT d.id, d.title
FROM document d
JOIN project p ON p.id = d.project_id
WHERE d.id = :documentId
  AND p.id = :projectId
  AND p.organization_id = :orgId;
```

Afterward, you must still verify caller membership, private-project access, and document read grant. Never treat the relationship query result as proof that every user may read that document.

### 8.2. List Query Pre-Filtered by Permissions Before Pagination

The SQL pattern below expresses the **predicate idea**, not a standalone migration file. `:userId` comes from the authenticated principal; `:isBoundOrgAdmin` is a boolean **computed server-side** from role and binding in that org—never taken from the client:

```sql
SELECT d.id, d.title
FROM document d
JOIN project p ON p.id = d.project_id
WHERE p.id = :projectId
  AND p.organization_id = :orgId
  AND EXISTS (
      SELECT 1 FROM org_membership om
      WHERE om.org_id = :orgId
        AND om.user_id = :userId
  )
  AND (
      p.is_private = FALSE
      OR :isBoundOrgAdmin = TRUE
      OR EXISTS (
          SELECT 1 FROM project_membership pm
          WHERE pm.project_id = p.id
            AND pm.user_id = :userId
      )
  )
  AND (
      d.owner_id = :userId
      OR :isBoundOrgAdmin = TRUE
      OR EXISTS (
          SELECT 1 FROM document_share ds
          WHERE ds.document_id = d.id
            AND ds.user_id = :userId
            AND ds.access_level IN ('VIEWER', 'EDITOR')
      )
  )
ORDER BY d.id
LIMIT :pageSize OFFSET :pageOffset;
```

Illustrative SQL must be adapted to the real schema and dialect. The `project:list` permission must still be enforced at the service/SQL policy **before** running the query. Count queries must apply the **exact same** scope and permission predicates; otherwise they can leak the count of documents the user cannot access.

### 8.3. Conditional Update with Affected Rows Check

```sql
UPDATE document
SET title = :newTitle
WHERE id = :documentId
  AND project_id = :projectId
  AND EXISTS (
      SELECT 1
      FROM project p
      WHERE p.id = :projectId
        AND p.organization_id = :orgId
  );
```

This checks only the **path** condition, not full user authorization yet. To prevent BOLA/TOCTOU, add membership/private-project/owner/share predicates matching EDITOR permission, use row locks or proper isolation/versioning, and require **affected rows = 1**. Passing `@PreAuthorize` on a service does not mean an SQL update may omit tenant and authorization predicates.

When moving a document to another project, verify both old and new parents, tenant, project privacy, and ACL inheritance; never allow changing `project_id` through an arbitrary rename endpoint.

## 9. Common Mistakes in Parent–Child Permissions

| Mistake | Consequence | Fix |
|---|---|---|
| `hasRole('ADMIN') OR canReadChild(...)` | Admin can bypass tenant | Check tenant/parent scope before any role branch |
| GET document by ID, ignoring org/project in URL | IDOR/BOLA via forged path | JOIN/verify canonical parent chain |
| Project view access returns all documents | Leaks unshared children | Check READ per child, filter in query |
| Child share automatically bypasses private project | Violates parent policy | Choose inheritance/exception explicitly and test |
| Trusting `organizationId` from JSON/header | Caller declares own tenant | Derive scope from auth + trusted DB data |
| Using `startsWith` on URLs to compare tenants | Prefix, encoding, and route matching bugs | Compare typed IDs from DB |
| Role hierarchy replacing resource hierarchy | Holding ROLE_ADMIN reads all records | Keep separate business object policies |
| Applying ACL inheritance automatically to domain trees | Parent rights cascade unintentionally | Configure parent/entriesInheriting intentionally |
| Checking only `@PostAuthorize` for mutations | Side effects occur before deny | `@PreAuthorize` and conditional DB updates |
| Only hiding buttons in the UI | Clients call APIs directly | Enforce checks in server and repository |
| Filtering after pagination | Missing items, total count leaks | Filter in SQL before paging/counting |
| Not checking on parent/project transfer | Old ACL/shares stay wrongly active | Transaction, verify source + destination |
| User leaves org while token roles remain valid | Stale permissions | Re-check membership/revocation/caching |
| Not testing service methods independently | Jobs/batches can bypass HTTP policies | Protect service boundaries and integration-test |
| Confusing organization admin with system admin | Privileges spill into other orgs | Per-org role bindings and auditing |
| Decision cache missing parent ID | Reuses permissions from another tree | Key includes principal/tenant/project/document/action/version |
| User knowing child ID probes parent existence | Enumeration via error differences | Consistent deny/404, limit metadata disclosure |

### 9.1. Changing Paths Is Not Proof of Inherited Rights

A route like `/api/orgs/10/projects/100/documents/1000` only expresses **access intent**. It does not alter the database or create an ACE. Even when APIs support path variables in `WebExpressionAuthorizationManager`, an expression comparing path parameters only evaluates values extracted from the URL; canonical data lookup is still required to prove parent/child relationships.

### 9.2. Disallow Escalation via Move/Clone

If a user can WRITE Document 1000 yet cannot administer Project 110, they must not be allowed to move the document into Project 110 and access it via a new path for extra privileges. Move/clone must check both source and destination, and resolve ownership, ACL grants, inheritance, and tenant boundaries for the new object. For clone, **never blindly copy all ACEs** if content is sensitive or ownership changes.

### 9.3. Explicit Decisions Required for Deny and Inheritance

Some ACL policies evaluate local deny/allow, inherited allow/deny, and `ace_order` sequentially. Never assume "parent has READ means child always has READ" when the child ACL has a deny ACE, `entries_inheriting=false`, or a custom strategy. When a user reports "I have project access yet cannot view the document", trace **effective permissions** across both parent and child instead of inspecting just one `acl_entry` row.

## 10. Implementation Checklist

- [ ] Canonical Organization → Project → Document model has trustworthy FKs/IDs.
- [ ] Policy clearly defines parent traversal, child permissions, and read/edit/list actions.
- [ ] Memberships and admin bindings are scoped to the exact organization; no global role bypass.
- [ ] When fetching a document by ID, verify `doc.projectId == URL.projectId` and `project.orgId == URL.orgId`.
- [ ] Private projects are checked before document grants, unless a share exception is formally designed.
- [ ] `@EnableMethodSecurity` is enabled; `@PreAuthorize` sits on Spring-managed service boundaries.
- [ ] Direct read, list, edit, batch, and background paths all have object-level guards.
- [ ] List queries apply permission predicates before paging/counting, leaking no out-of-scope aggregates.
- [ ] Updates carry tenant/project/authorization predicates, affected-row checks, and concurrency control.
- [ ] ACL parent/entriesInheriting/role hierarchy are kept distinct and tested separately if used.
- [ ] Non-existent paths, wrong parents, wrong orgs, and unauthorized actions deny safely without over-disclosing.
- [ ] Move/clone/reparent APIs verify both source and destination plus post-move ACL policy.
- [ ] Users removed from orgs/projects or with revoked shares are blocked within cache/token SLAs.
- [ ] Integration tests cover forged paths, unshared children, private parents, filtered lists, admin scoping, CSRF, and non-controller method calls.

## 11. Knowledge Self-Check

**Question 1.** Bob has `project:list` on Project 100. Can Bob read every Document in the project?

**Answer:** No. List permission grants opening the listing, yet each document still requires owner/share/admin READ conditions. If returning content or sensitive metadata, filter in the query.

**Question 2.** Bob has an EDITOR share on Document 1100. Why can he still not read it?

**Answer:** Project 110 is private and the demo requires traversing the parent first. Bob is not permitted to traverse Project 110; child grants do not bypass the parent.

**Question 3.** A user changes the URL from `/orgs/10/projects/100/documents/1000` to `/orgs/20/projects/100/documents/1000`. Is checking a role on the document alone sufficient?

**Answer:** No. Project 100 actually belongs to Org 10; the policy must compare canonical data rather than trusting the client-chosen `orgId`.

**Question 4.** Does ACL parent inheritance automatically validate `document.project_id`?

**Answer:** No. `parentAcl`/`entriesInheriting` is an ACE inheritance mechanism, not domain foreign-key or tenant verification.

**Question 5.** Holding `ROLE_ORG_ADMIN` without an admin binding for Org 20; can the user read Document 2000?

**Answer:** Not under the demo. Administrative privileges are bounded by server-side org membership and binding, not a global role string.

## 12. Official References

- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, matcher order, URI templates, and request authorization.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, policy beans, `@P`, and limits of `@PostAuthorize`.
- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): ACL object identities, parents, inheritance, and ACEs.
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `Authentication`, `GrantedAuthority`, and `AuthorizationManager`.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): checking object IDs at every endpoint accepting client-controlled IDs.

**Key takeaway:** Parent access does not automatically turn into child read/write rights; child permissions can be constrained by parent projects/organizations. Nested paths are merely client-submitted data. To prevent BOLA/IDOR, **verify every parent–child relationship from canonical data**, check memberships and admin scopes, enforce per-object permissions, and push predicates into SQL whenever paginating, mutating, or guarding against concurrency.