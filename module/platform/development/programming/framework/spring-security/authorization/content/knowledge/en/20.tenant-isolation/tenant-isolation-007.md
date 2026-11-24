# Enforcing Tenant Conditions in Repositories and Data Queries

## 1. The problem: authenticating the right user yet returning the wrong tenant's data

A SaaS system serves multiple organizations sharing one database. Every document carries a `tenant_id`; a user is allowed to read documents belonging to the tenant they are a member of. For example:

| Document ID | Tenant | Owner | Title |
| ---: | --- | --- | --- |
| 11 | `T1` | `u-alice` | Alpha |
| 12 | `T1` | `u-bob` | Beta |
| 13 | `T2` | `u-carol` | Gamma |
| 14 | `T1` | `u-alice` | Locked |

Alice belongs to `T1`, Carol belongs to `T2`. If the repository calls:

```java
documentRepository.findById(13L);
```

and the service has no other protection, Alice can read Carol's document simply by guessing ID `13`. `@PreAuthorize("hasAuthority('document:read')")` **cannot fix that bug**, because it checks functional authority rather than automatically injecting `tenant_id = 'T1'` into SQL.

This flaw is a form of **Broken Object Level Authorization (BOLA/IDOR)** and **cross-tenant data leakage**. It affects more than single-document reads: `findAll`, search, pagination, `COUNT`, `EXISTS`, JOINs, aggregations, exports, updates, and deletes can all open paths to access or modify cross-tenant data.

This Knowledge article belongs to **Spring Security – authorization**, **Tenant Isolation** group. Focus: **enforcing tenant predicates directly in repositories and data queries**, instead of over-fetching rows and filtering in Java or trusting `tenantId` from the request.

After this lesson, you will:

1. Distinguish authentication, functional authorization, **tenant membership**, and object-level authorization.
2. Determine **trusted tenant scope** from verified identity.
3. Write SQL/JPQL always carrying a tenant predicate for **single objects, lists, searches, COUNT, EXISTS, UPDATE, and DELETE**.
4. Use Spring Data JPA derived queries, `@Query`, `@Modifying`, paging, and version checks properly.
5. Build a runnable **Java 17 + Spring Boot 3.5.8 + Spring Security + Spring Data JPA + H2** example.
6. Test that Alice cannot see tenant T2's documents and Carol cannot see tenant T1's; even within the same tenant, writes require owner/permission checks.
7. Prevent common bugs across JOINs, `OR`, native SQL, caches, async, tenant-local IDs, and lazy loading.
8. Understand PostgreSQL **Row-Level Security (RLS)** as defense-in-depth along with its limitations.
9. Design fail-closed behavior safe with transactions, locking, data migrations, and revoked permissions.

**Core invariant:** all data returned to or modified by a caller must belong to **a server-verified tenant scope** and satisfy additional business permissions. The tenant condition is a mandatory security boundary, not merely a UI filter.

## 2. Three independent authorization layers

A `canRead(document)` decision is typically a logical AND:

```text
canRead(actor, doc) =
    authenticated(actor)
    AND hasAuthority(actor, "document:read")
    AND isActiveMember(actor, doc.tenantId)
    AND objectPolicyAllows(actor, doc)
```

In the demo, to spotlight tenant filtering, the `READ` rule lets any verified member of the corresponding tenant holding `document:read` view documents in that tenant. The `WRITE` rule is stricter: besides matching tenant, the caller must be `ownerId` and the document must still be `DRAFT`.

Real organizations often also require ACLs, project roles, security classifications, status checks, or share permissions. **A tenant predicate is necessary, not sufficient for all data.**

| Layer | Question | Example mechanism |
| --- | --- | --- |
| Authentication | Who really is the caller? | Verified JWT/OIDC/session |
| Functional permission | May the caller use read/edit APIs? | `@PreAuthorize("hasAuthority(...)")` |
| Tenant scope | Which tenant is the caller in, and do they hold membership? | Server directory or verified tenant claim |
| Object permission | May they read/write this specific record? | `tenant_id` + owner/ACL/state |
| Field permission | May they edit `ownerId`, `tenantId`, `state`? | DTO allowlists and domain services |
| DB-layer protection | What if a query accidentally omits tenant? | Repository contract, tests, optional PostgreSQL RLS |

**Never substitute functional authority for tenant scope.** `ROLE_EDITOR` or `document:read` does not imply membership in every organization.

## 3. Tenant ID must come from a trusted source

An endpoint might receive:

```http
GET /api/documents/13?tenantId=T2
Authorization: Bearer <alice-token>
```

If the backend uses the query parameter directly:

```java
repository.findByIdAndTenantId(id, requestedTenantId);
```

then the `tenant_id` condition is **syntactically present** yet still broken for security: Alice can request `T2`. A tenant predicate only protects when **the tenant value is verified**.

### 3.1. Single active tenant model

The application can resolve the tenant from:

- Verified `Authentication`, if the token holds a trusted tenant claim and policy permits it.
- Server-side membership directory: mapping the token's `subject` to permitted tenants.
- A tenant chosen via URL/header, **after** verifying membership and active status in the database/server.
- A server-side session holding a verified active tenant.

A simple model for this lesson:

```text
Authentication.getName() -> UserDirectory (server)
  alice -> userId=u-alice, tenantId=T1
  bob   -> userId=u-bob,   tenantId=T1
  carol -> userId=u-carol, tenantId=T2
```

A `tenantId` in request body, query, cookie, or custom header is **not trusted on its own**. When a user belongs to multiple tenants, verify permission to switch active tenant; only afterward pass the trusted tenant into queries.

### 3.2. Never conflate user identity and tenant identity

`ownerId` identifies the record owner. `tenantId` identifies the organizational boundary. Ownership can transfer to another user in the same tenant without moving the tenant; conversely, migrating tenants impacts file storage, encryption keys, indexes, ACLs, and related resources.

Never alter `tenant_id` through a generic update API; use a dedicated tenant-migration workflow with checks and auditing. A repository update for renaming a title must never accept a tenant from the client.

### 3.3. Fail closed when no trusted tenant exists

If `Authentication` is missing, the token is anonymous, the user is locked, or no valid tenant exists, **deny**—never fall back to a default tenant.

```java
// SNIPPET illustrating what NOT to do:
String tenant = currentTenantOrNull();
return tenant == null
    ? repository.findAll()             // dangerous: drops tenant filter
    : repository.findByTenantId(tenant);
```

The safe policy is to deny or return an empty set per contract when tenant is absent, never opening the entire table.

## 4. Enforce tenant conditions in **SQL before returning data**

### 4.1. Reading a single record

Unsafe:

```sql
SELECT id, tenant_id, owner_id, title
FROM documents
WHERE id = :id;
```

Recommended:

```sql
SELECT id, tenant_id, owner_id, title
FROM documents
WHERE id = :id
  AND tenant_id = :trustedTenant;
```

Here `:id` and `:trustedTenant` are named parameters bound by the query library, never string-concatenated. When no row matches, the API can return `404` to avoid revealing whether a document exists in another tenant.

### 4.2. Lists and searches

```sql
SELECT id, tenant_id, owner_id, title
FROM documents
WHERE tenant_id = :trustedTenant
  AND state = 'DRAFT'
  AND LOWER(title) LIKE :normalizedSearchPattern
ORDER BY id
LIMIT :pageSize OFFSET :offset;
```

The `documents` query must apply `tenant_id` before database pagination. Escape search patterns appropriately for the DB if literal `%` or `_` characters are searched; bound parameters prevent SQL injection, not wildcard semantics.

### 4.3. COUNT, EXISTS, and aggregations must also filter by tenant

```sql
SELECT COUNT(*)
FROM documents
WHERE tenant_id = :trustedTenant
  AND state = 'DRAFT';
```

```sql
SELECT CASE WHEN COUNT(*) > 0 THEN TRUE ELSE FALSE END
FROM documents
WHERE id = :id
  AND tenant_id = :trustedTenant;
```

```sql
SELECT state, COUNT(*) AS total
FROM documents
WHERE tenant_id = :trustedTenant
GROUP BY state;
```

If an API returns only T1's rows while `totalElements` or dashboards count across the whole system, it still leaks metadata and breaks pagination. **Every query supporting a feature must share the same tenant policy.**

### 4.4. Writes and deletes also need tenant guards

```sql
UPDATE documents
SET title = :newTitle
WHERE id = :id
  AND tenant_id = :trustedTenant
  AND owner_id = :trustedActor
  AND state = 'DRAFT';
```

```sql
DELETE FROM documents
WHERE id = :id
  AND tenant_id = :trustedTenant
  AND owner_id = :trustedActor;
```

After `UPDATE` or `DELETE`, inspect the affected row count. **0 rows** can mean nonexistent, wrong tenant, non-owner, wrong state, or concurrent change; avoid revealing details to unauthorized callers. Critical mutations also need transactions, version/lock checks, and field-level policies.

## 5. Spring Data JPA: core repository patterns

A Spring Data repository can derive queries automatically from method names:

```java
// SNIPPET illustrating methods in a JpaRepository.
Optional<DocumentEntity> findByIdAndTenantId(
    Long id, String tenantId);

Page<DocumentEntity> findByTenantIdAndState(
    String tenantId, DocumentState state, Pageable pageable);

long countByTenantIdAndState(
    String tenantId, DocumentState state);
```

`findByIdAndTenantId` constrains both ID and tenant. Similarly, `Page` places the tenant predicate into both the row query and the derived count query; verify actual predicates for complex custom `@Query`/join methods.

**Yet repositories do not validate the `tenantId` value itself.** Every method must receive a trusted tenant from the service/directory, never from an unverified client input.

### 5.1. Avoid inherited unscoped `findById`/`findAll`

`JpaRepository<T, ID>` exposes convenient methods like `findById`, `findAll`, `findAllById`, `deleteById`, `findAll(Pageable)`, and `count()`. They **do not automatically add a tenant predicate**.

If controllers/services can call those methods freely, a developer can easily bypass policy by accident. In larger codebases, consider:

- Exposing only tenant-scoped methods through an **application data-access service**.
- Using a custom `Repository<T, ID>` interface declaring only approved queries.
- Separating internal admin repositories from normal request repositories and locking down real admin rights.
- Architecture tests or static analysis to detect sensitive services calling unscoped repository methods.
- Adding PostgreSQL RLS or another DB isolation control as defense-in-depth.

The demo below extends `JpaRepository` for simplicity, **but the application service calls only tenant-predicated methods**. Tests may inspect unscoped state through the repository because they run in an internal verification harness, not as a caller-facing API.

### 5.2. JPQL with `@Query`

When derived method names grow long or involve ACLs/shares, declare:

```java
@Query("""
    select d from DocumentEntity d
    where d.tenantId = :tenantId
      and d.state = :state
      and (d.ownerId = :userId or d.isPublicWithinTenant = true)
    order by d.id
    """)
List<DocumentEntity> findVisible(
    @Param("tenantId") String tenantId,
    @Param("state") DocumentState state,
    @Param("userId") String userId);
```

**Illustrative snippet:** field `isPublicWithinTenant` does not exist on the demo entity; it merely illustrates an extended policy. Notice the tenant predicate sits **outside and encloses the entire OR condition**.

A dangerous query:

```sql
WHERE d.tenant_id = :tenant
  AND d.owner_id = :actor
   OR d.public = TRUE
```

Because `AND` binds tighter than `OR`, `d.public = TRUE` can return documents from **other tenants**. Correct form:

```sql
WHERE d.tenant_id = :tenant
  AND (d.owner_id = :actor OR d.public = TRUE)
```

During repository reviews, explicitly verify that **every OR branch remains under the tenant predicate**.

### 5.3. Specifications and Criteria API

When queries have many dynamic filters, write a tenant-scoped specification:

```java
// SNIPPET when DocumentRepository implements JpaSpecificationExecutor.
static Specification<DocumentEntity> inTenant(String tenantId) {
    return (root, query, cb) ->
        cb.equal(root.get("tenantId"), tenantId);
}
```

Combining conditions:

```java
Specification<DocumentEntity> spec =
    inTenant(trustedTenant)
    .and((root, query, cb) ->
        cb.equal(root.get("state"), DocumentState.DRAFT));

Page<DocumentEntity> page = repository.findAll(spec, pageable);
```

Note: `Specification` protects only when callers **always** compose the tenant spec. Avoid exposing `findAll(specFromClient)` if client-driven specs could drop the tenant. Apply the tenant constraint inside an internal query wrapper before appending optional filters.

### 5.4. Native SQL and JDBC

With `@Query(nativeQuery=true)` or `JdbcTemplate`, the ORM does not inject tenant predicates automatically. Write the tenant condition explicitly, bind parameters safely, and test separate count queries as well.

```java
// SNIPPET with NamedParameterJdbcTemplate:
var sql = """
    select id, tenant_id, title
    from documents
    where tenant_id = :tenant
      and id = :id
    """;

var params = Map.of(
    "tenant", trustedTenant,
    "id", requestedId
);

List<DocumentView> rows = namedJdbc.query(sql, params, rowMapper);
```

Never build SQL via `"where tenant_id='" + clientTenant + "'"`—that lacks tenant verification and introduces SQL injection.

## 6. Runnable example: Spring Boot 3.5.8 + Java 17 + JPA + H2

This demo illustrates tenant guards **directly inside the Spring Data repository** alongside Method Security on the service.

**Demo policy:**

- Authenticated accounts holding `document:read` can view documents inside their server-determined tenant.
- `alice`/`bob` are in T1; `carol` is in T2.
- Only the owner holding `document:write` in the right tenant may rename a `DRAFT` document.
- `UPDATE` verifies `id`, `tenantId`, `ownerId`, `state`, and `version` in **a single JPQL DML statement**.
- Requests cannot choose `tenantId`/`ownerId` to bypass policy.
- Lists include tenant-scoped pagination/counts and return `DocumentView` instead of entities.
- If an ID belongs to another tenant, `view` returns `404` so out-of-scope existence is not confirmed.
- Uses in-memory H2 seeded via `schema.sql`/`data.sql`. Production PostgreSQL/MySQL setups need migrations/indexes and database-specific tests.

### 6.1. Directory structure

```text
tenant-repository-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── TenantRepositoryApplication.java
    │   │   ├── DocumentState.java
    │   │   ├── DocumentEntity.java
    │   │   ├── DocumentRepository.java
    │   │   ├── ActorDirectory.java
    │   │   ├── DocumentView.java
    │   │   └── DocumentService.java
    │   └── resources/
    │       ├── application.properties
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/
        └── TenantRepositorySecurityTest.java
```

### 6.2. Gradle and SQL initialization setup

**`settings.gradle`:**

```groovy
rootProject.name = 'tenant-repository-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-data-jpa` provides JPA, Spring Data repositories, and the corresponding transaction manager; H2 is the embedded DB for the demo. Since the example does not use Spring MVC, `starter-web` is not needed.

**`src/main/resources/application.properties`:**

```properties
spring.jpa.hibernate.ddl-auto=none
spring.sql.init.mode=always
spring.jpa.open-in-view=false
```

We **explicitly create the schema** with `schema.sql` and seed via `data.sql`, so Hibernate DDL auto is disabled. Do not let Hibernate DDL auto alter production schemas; production typically uses Flyway/Liquibase.

### 6.3. Creating the table with tenant and indexes

**`src/main/resources/schema.sql`:**

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(40) NOT NULL,
    owner_id VARCHAR(64) NOT NULL,
    state VARCHAR(30) NOT NULL,
    title VARCHAR(150) NOT NULL,
    version BIGINT NOT NULL
);

CREATE INDEX idx_documents_tenant_state_id
    ON documents (tenant_id, state, id);

CREATE INDEX idx_documents_tenant_owner
    ON documents (tenant_id, owner_id, id);
```

**`src/main/resources/data.sql`:**

```sql
INSERT INTO documents (
    id, tenant_id, owner_id, state, title, version
) VALUES
    (11, 'T1', 'u-alice', 'DRAFT', 'Alpha', 1),
    (12, 'T1', 'u-bob',   'DRAFT', 'Beta',  1),
    (13, 'T2', 'u-carol', 'DRAFT', 'Gamma', 1),
    (14, 'T1', 'u-alice', 'APPROVED', 'Locked', 1);
```

`id` in this demo is a global ID, preventing two tenants from sharing `Document#11`. If a product uses **tenant-local IDs**, design a composite key `(tenant_id, local_id)` or a globally unique surrogate ID, and apply tenant guards consistently across all join tables, ACLs, and caches.

### 6.4. State enum

**`src/main/java/demo/DocumentState.java`:**

```java
package demo;

public enum DocumentState {
    DRAFT,
    APPROVED
}
```

### 6.5. JPA entity: carries tenant, never populated from client

**`src/main/java/demo/DocumentEntity.java`:**

```java
package demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "documents")
public class DocumentEntity {

    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "owner_id", nullable = false)
    private String ownerId;

    @Enumerated(EnumType.STRING)
    @Column(name = "state", nullable = false)
    private DocumentState state;

    @Column(name = "title", nullable = false)
    private String title;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected DocumentEntity() {
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOwnerId() {
        return ownerId;
    }

    public DocumentState getState() {
        return state;
    }

    public String getTitle() {
        return title;
    }

    public long getVersion() {
        return version;
    }
}
```

The entity has no public setters and is never used as a `@RequestBody`. However, **omitting setters alone does not protect the whole application**: the ORM still hydrates fields via reflection, and other services can run bulk JPQL/SQL. Security is enforced by repository contracts, service policies, and DB controls.

`@Version` provides optimistic locking for managed-entity updates. For JPQL bulk `UPDATE`s, the JPA provider **does not automatically apply version checks/increments like a managed-entity save**, so the repository below includes `version` and `version + 1` explicitly.

### 6.6. Repository: tenant predicates for read, page, count, and write

**`src/main/java/demo/DocumentRepository.java`:**

```java
package demo;

import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {

    // Always look up by ID + tenant; never use unscoped findById in services.
    Optional<DocumentEntity> findByIdAndTenantId(
        Long id,
        String tenantId
    );

    // Both data query and Page count query enforce tenant/state.
    Page<DocumentEntity> findByTenantIdAndState(
        String tenantId,
        DocumentState state,
        Pageable pageable
    );

    long countByTenantIdAndState(
        String tenantId,
        DocumentState state
    );

    // Bulk update requires explicit tenant/owner/state/version policy.
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update DocumentEntity d
        set d.title = :title,
            d.version = d.version + 1
        where d.id = :id
          and d.tenantId = :tenantId
          and d.ownerId = :ownerId
          and d.state = :state
          and d.version = :expectedVersion
        """)
    int changeTitleIfOwner(
        @Param("id") Long id,
        @Param("tenantId") String tenantId,
        @Param("ownerId") String ownerId,
        @Param("state") DocumentState state,
        @Param("expectedVersion") long expectedVersion,
        @Param("title") String title
    );
}
```

**Method-by-method explanation:**

- `findByIdAndTenantId`: cannot see IDs belonging to another tenant, even if the ID exists in the DB.
- `findByTenantIdAndState`: returns a `Page` with tenant in its predicate; the repository's derived count query also includes tenant + state.
- `countByTenantIdAndState`: dashboards/metadata never count across tenants.
- `changeTitleIfOwner`: updates only when **tenant, owner, state, and version all match**. Returns affected rows; the service rejects anything other than `1`.
- `@Modifying`: tells Spring Data this is JPQL DML rather than `SELECT`. `flushAutomatically/clearAutomatically` keeps the persistence context consistent around bulk updates, though it **may flush/clear other managed entities**—evaluate in real transactions.
- Bulk updates bypass JPA entity lifecycle callbacks and automatic version checks; the statement explicitly increments and checks `version` by design.

**Warning:** extending `JpaRepository` still exposes unscoped `findAll()` and `findById()`. Not calling them in the **application service** does not prevent calls elsewhere in the codebase. In production, use a **tenant-aware repository facade** or a narrower interface plus architecture tests.

### 6.7. Trusted actor directory

**`src/main/java/demo/ActorDirectory.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

record Actor(String userId, String tenantId) {
}

@Component
public class ActorDirectory {

    private final Map<String, Actor> actors = Map.of(
        "alice", new Actor("u-alice", "T1"),
        "bob",   new Actor("u-bob", "T1"),
        "carol", new Actor("u-carol", "T2")
    );

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public Actor requireCurrent() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)) {
            throw new AccessDeniedException("No trusted user");
        }

        Actor actor = actors.get(authentication.getName());
        if (actor == null) {
            throw new AccessDeniedException("No trusted tenant");
        }

        return actor;
    }
}
```

`Actor` is used strictly server-side. In production, map from JWT/OIDC stable subject IDs and issuer/memberships, rather than assuming `getName()` is globally unique if usernames collide across tenants. For multi-tenant users, add an active-tenant selection policy backed by membership verification.

Notably, `AnonymousAuthenticationToken` can have `isAuthenticated() == true`; `AuthenticationTrustResolver` prevents mistaking anonymous callers for real principals.

### 6.8. Response DTO: never return the raw entity unnecessarily

**`src/main/java/demo/DocumentView.java`:**

```java
package demo;

public record DocumentView(
        Long id,
        String title,
        String state,
        long version) {

    public static DocumentView from(DocumentEntity d) {
        return new DocumentView(
            d.getId(),
            d.getTitle(),
            d.getState().name(),
            d.getVersion()
        );
    }
}
```

`DocumentView` omits `ownerId`/`tenantId` and any sensitive fields unnecessary for the client. Depending on the API, admin views may return tenant labels, but avoid serializing arbitrary associations and ACL metadata.

### 6.9. Service: authority + tenant-scoped repository + owner guard

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository repository;
    private final ActorDirectory directory;

    public DocumentService(
            DocumentRepository repository,
            ActorDirectory directory) {
        this.repository = repository;
        this.directory = directory;
    }

    @PreAuthorize("hasAuthority('document:read')")
    @Transactional(readOnly = true)
    public DocumentView view(Long id) {
        Actor actor = directory.requireCurrent();

        DocumentEntity document = repository
            .findByIdAndTenantId(id, actor.tenantId())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document unavailable"));

        return DocumentView.from(document);
    }

    @PreAuthorize("hasAuthority('document:read')")
    @Transactional(readOnly = true)
    public Page<DocumentView> listDraft(int page, int size) {
        Actor actor = directory.requireCurrent();

        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid page");
        }

        var pageable = PageRequest.of(
            page,
            size,
            Sort.by(Sort.Direction.ASC, "id")
        );

        return repository
            .findByTenantIdAndState(
                actor.tenantId(),
                DocumentState.DRAFT,
                pageable
            )
            .map(DocumentView::from);
    }

    @PreAuthorize("hasAuthority('document:write')")
    @Transactional
    public DocumentView changeTitle(
            Long id, String newTitle, long expectedVersion) {

        Actor actor = directory.requireCurrent();

        if (newTitle == null || newTitle.isBlank()
                || newTitle.length() > 150) {
            throw new IllegalArgumentException("Invalid title");
        }

        // Single JPQL update with tenant/owner/state/version predicates.
        int changed = repository.changeTitleIfOwner(
            id,
            actor.tenantId(),
            actor.userId(),
            DocumentState.DRAFT,
            expectedVersion,
            newTitle
        );

        if (changed != 1) {
            // Do not reveal whether ID exists in another tenant or who owns it.
            throw new AccessDeniedException(
                "Document cannot be updated"
            );
        }

        return repository
            .findByIdAndTenantId(id, actor.tenantId())
            .map(DocumentView::from)
            .orElseThrow(() -> new IllegalStateException(
                "Updated document was not found"));
    }
}
```

**Why does the tenant predicate appear twice on writes?** First inside `UPDATE` to enforce authorization **at the exact moment of mutation**; second inside `SELECT` to re-read only within the verified tenant. Checking tenant solely in a prior read followed by an unscoped update invites TOCTOU races or wrong-resource edits as code evolves.

`@PreAuthorize` checks functional authority, while `ActorDirectory` and the repository protect the tenant. **Authority and tenant form a logical AND**, never OR. For writes, `ownerId` and `state` tighten it further.

**The HTTP status of `ResponseStatusException`** only takes effect when called through MVC/controllers with an exception resolver; in the CLI demo, we catch the exception and print `NOT_FOUND`. Using the same path to return 404 for both nonexistent IDs and cross-tenant IDs curbs enumeration.

`DocumentService` is a Spring-managed bean, so Method Security and `@Transactional` apply when callers invoke through the proxy. Never invoke `this.changeTitle(...)` inside the same bean assuming annotations will intercept.

### 6.10. Bootstrap and scenario runner

**`src/main/java/demo/TenantRepositoryApplication.java`:**

```java
package demo;

import java.util.Arrays;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class TenantRepositoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantRepositoryApplication.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner scenario(DocumentService documents) {
        return args -> {
            try {
                login("alice", "document:read", "document:write");
                var aliceDrafts = documents.listDraft(0, 10);
                System.out.println("ALICE_DRAFT_IDS: "
                    + ids(aliceDrafts));
                System.out.println("ALICE_DRAFT_TOTAL: "
                    + aliceDrafts.getTotalElements());

                notFound("ALICE_READ_13", () -> documents.view(13L));

                System.out.println("ALICE_UPDATE_11: "
                    + documents.changeTitle(
                        11L, "Alpha revised", 1L).title());

                login("bob", "document:read", "document:write");
                System.out.println("BOB_DRAFT_IDS: "
                    + ids(documents.listDraft(0, 10)));
                denied("BOB_UPDATE_11", () ->
                    documents.changeTitle(11L, "Stolen", 2L));

                login("carol", "document:read", "document:write");
                System.out.println("CAROL_DRAFT_IDS: "
                    + ids(documents.listDraft(0, 10)));
                notFound("CAROL_READ_11", () -> documents.view(11L));

                login("alice", "document:write");
                denied("ALICE_WITHOUT_READ", () ->
                    documents.listDraft(0, 10));

                login("alice", "document:read");
                var finalRow = documents.view(11L);
                System.out.println("FINAL_TITLE_11: "
                    + finalRow.title());
                System.out.println("FINAL_VERSION_11: "
                    + finalRow.version());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static List<Long> ids(
            org.springframework.data.domain.Page<DocumentView> page) {
        return page.getContent().stream()
            .map(DocumentView::id)
            .toList();
    }

    private static void login(
            String username, String... authorities) {

        var grants = Arrays.stream(authorities)
            .map(SimpleGrantedAuthority::new)
            .toList();

        var auth = new UsernamePasswordAuthenticationToken(
            username, "demo-only", grants);

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);
    }

    private static void denied(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }

    private static void notFound(
            String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (ResponseStatusException expected) {
            System.out.println(label + ": NOT_FOUND");
        }
    }
}
```

`@EnableMethodSecurity` enables `@PreAuthorize`. The example has no web controller; it invokes the Spring-managed service from `CommandLineRunner`.

**Warning:** Constructing `UsernamePasswordAuthenticationToken` directly with usernames and authorities is strictly for **CLI/test simulation**. Production must verify tokens/credentials via Spring Security filters/providers. Never expose a `login(...)` helper as an endpoint letting clients pick users or roles.

### 6.11. Running and checking output

In the project directory, using the Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell:

```bash
.\gradlew.bat bootRun
```

If the project lacks a Gradle Wrapper, install a compatible Gradle version or generate the Wrapper first before running. Ignoring Spring Boot/Gradle startup logs, the program's `System.out.println` lines are expected to be:

```text
ALICE_DRAFT_IDS: [11, 12]
ALICE_DRAFT_TOTAL: 2
ALICE_READ_13: NOT_FOUND
ALICE_UPDATE_11: Alpha revised
BOB_DRAFT_IDS: [11, 12]
BOB_UPDATE_11: DENIED
CAROL_DRAFT_IDS: [13]
CAROL_READ_11: NOT_FOUND
ALICE_WITHOUT_READ: DENIED
FINAL_TITLE_11: Alpha revised
FINAL_VERSION_11: 2
```

**Explaining the results:**

- Alice and Bob in tenant T1 see DRAFT documents `11` and `12`, total 2. Document `14` is `APPROVED`, so it is excluded from the Draft list.
- Document `13` belongs to T2; Alice cannot read it despite knowing ID 13.
- Alice owns document 11 with the right tenant, authority, and expectedVersion 1, so the update succeeds; version increments 1 -> 2.
- Bob belongs to **the same tenant** yet **is not the owner** of document 11. The update is denied even with the right expectedVersion 2.
- Carol belongs to T2 and sees only document 13; she cannot read T1's document 11.
- Alice lacks `document:read` on the second-to-last call; Method Security denies access even though the directory still maps her to T1.
- After restoring read authority, the service reads record 11; title is `Alpha revised`, version 2.

**The lines above are expected output from reading the source code, not a claim that the program was executed in this environment.** Actual execution depends on Spring Boot/H2 initializing the schema and Method Security proxies running properly.

## 7. Integration tests: proving zero cross-tenant data leakage

**`src/test/java/demo/TenantRepositorySecurityTest.java`:**

```java
package demo;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.Page;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.server.ResponseStatusException;

@SpringBootTest
@ActiveProfiles("test")
@DirtiesContext(classMode =
    DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class TenantRepositorySecurityTest {

    @Autowired
    DocumentService service;

    @Autowired
    DocumentRepository repository;

    private static List<Long> ids(Page<DocumentView> page) {
        return page.getContent().stream()
            .map(DocumentView::id).toList();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"document:read", "document:write"}
    )
    void listAndCountApplyTenantBeforePagination() {
        Page<DocumentView> first = service.listDraft(0, 1);
        Page<DocumentView> second = service.listDraft(1, 1);

        assertEquals(List.of(11L), ids(first));
        assertEquals(List.of(12L), ids(second));
        assertEquals(2L, first.getTotalElements());
        assertEquals(2L, second.getTotalElements());
        assertEquals(2L, repository.countByTenantIdAndState(
            "T1", DocumentState.DRAFT));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "document:read")
    void tenantT2CannotViewT1() {
        assertEquals(List.of(13L), ids(service.listDraft(0, 10)));
        assertEquals("Gamma", service.view(13L).title());

        assertThrows(
            ResponseStatusException.class,
            () -> service.view(11L));
        assertTrue(repository.findByIdAndTenantId(11L, "T2").isEmpty());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void tenantT1CannotViewT2EvenWithKnownId() {
        assertThrows(
            ResponseStatusException.class,
            () -> service.view(13L));

        assertTrue(repository.findByIdAndTenantId(13L, "T1").isEmpty());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:write")
    void sameTenantIsNotEnoughToEditNonOwnerRecord() {
        DocumentEntity before = repository.findById(11L).orElseThrow();

        assertThrows(
            AccessDeniedException.class,
            () -> service.changeTitle(11L, "Stolen", 1L));

        DocumentEntity after = repository.findById(11L).orElseThrow();
        assertEquals(before.getTitle(), after.getTitle());
        assertEquals(before.getVersion(), after.getVersion());
        assertEquals("T1", after.getTenantId());
        assertEquals("u-alice", after.getOwnerId());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:write")
    void validOwnerUpdateKeepsTenantAndIncrementsVersion() {
        DocumentView updated =
            service.changeTitle(11L, "Revised", 1L);

        assertEquals("Revised", updated.title());
        assertEquals(2L, updated.version());

        DocumentEntity stored = repository.findById(11L).orElseThrow();
        assertEquals("T1", stored.getTenantId());
        assertEquals("u-alice", stored.getOwnerId());
        assertEquals("Revised", stored.getTitle());
        assertEquals(2L, stored.getVersion());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:write")
    void staleVersionCannotOverwrite() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.changeTitle(11L, "Wrong", 99L));

        DocumentEntity stored = repository.findById(11L).orElseThrow();
        assertEquals("Alpha", stored.getTitle());
        assertEquals(1L, stored.getVersion());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void readAuthorityDoesNotGrantWrite() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.changeTitle(11L, "Wrong", 1L));
    }

    @Test
    @WithMockUser(username = "ghost", authorities = "document:read")
    void missingTrustedTenantFailsClosed() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.listDraft(0, 10));
    }

    @Test
    @WithAnonymousUser
    void anonymousIsDenied() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.listDraft(0, 10));
    }
}
```

Run:

```bash
./gradlew test
```

**Why use `@SpringBootTest`?** The tests spin up ApplicationContext, Spring Data repositories, H2, `@EnableMethodSecurity`, Spring AOP proxies, and the transaction manager. `@WithMockUser` supplies authentication for test calls; `@ActiveProfiles("test")` disables the CLI runner. `@DirtiesContext` guarantees each test starts with freshly seeded data.

**Note:** the tests call `repository.findById(...)` directly **solely to inspect DB state as verification** after a request is denied. In production, caller-facing services must never invoke unscoped repository methods like that.

### 7.1. Verification matrix

| Caller and authority | Action | Expectation | Deciding condition |
| --- | --- | --- | --- |
| Alice/T1 + `document:read` | List Drafts | IDs 11, 12; count 2 | Tenant T1 + state DRAFT |
| Alice/T1 + `document:read` | Read ID 13 (T2) | Not found in scope | `id AND tenant_id` |
| Carol/T2 + `document:read` | List Drafts | ID 13 only | Tenant T2 |
| Carol/T2 + `document:read` | Read ID 11 (T1) | Not found in scope | `id AND tenant_id` |
| Bob/T1 + `document:write` | Edit Alice's ID 11 | Denied | Right tenant, wrong owner |
| Alice/T1 + `document:write` | Edit ID 11, version 1 | Success, version 2 | Tenant + owner + state + version |
| Alice/T1 + `document:write` | Edit ID 11 with version 99 | Denied | Stale version |
| Alice/T1 with only `document:read` | Edit ID 11 | Denied | Function-level authority |
| Ghost with no directory tenant | List | Denied | Fail closed |
| Anonymous | List | Denied | Method Security |

Asserting only HTTP 403/404 is insufficient in web applications. For writes, re-read the DB to verify `tenantId`, `ownerId`, title, version, and ACLs/grants were not unlawfully modified.

## 8. JOINs, subqueries, and relationships across multi-tenant tables

### 8.1. JOINs must guard joined tables too

Suppose there is a `projects` table and `documents.project_id`. Weak query:

```sql
SELECT d.id, d.title
FROM documents d
JOIN projects p ON p.id = d.project_id
WHERE d.tenant_id = :tenant;
```

If the database or app contains bad relational data, the JOIN can pair a T1 document with a T2 project. Safer:

```sql
SELECT d.id, d.title
FROM documents d
JOIN projects p
  ON p.id = d.project_id
 AND p.tenant_id = d.tenant_id
WHERE d.tenant_id = :trustedTenant
  AND p.tenant_id = :trustedTenant;
```

This is **illustrative SQL for a schema with `project_id`**, not a runnable query in the demo schema, since the demo has no `projects` table. At the data layer, design a **composite foreign key `(tenant_id, project_id)`** where appropriate so the database also enforces same-tenant links.

### 8.2. Intra-tenant document sharing via `EXISTS`

A system with per-user grants:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :trustedTenant
  AND (
       d.owner_id = :trustedUser
       OR EXISTS (
           SELECT 1
           FROM document_grants g
           WHERE g.document_id = d.id
             AND g.tenant_id = d.tenant_id
             AND g.grantee_id = :trustedUser
             AND g.permission = 'READ'
       )
  )
ORDER BY d.id;
```

The `document_grants` table is an **illustrative extension** absent from the JPA demo. What matters is binding both document and grant to the tenant, never picking up a grant from another tenant just because IDs match.

If rules involve **DENY overriding ALLOW**, role hierarchies, share expiration, or ACL inheritance, a simple `EXISTS READ` SQL check **may not** express the full policy. For such policies, use an authorization service model or appropriate joins/CTEs backed by contract tests comparing outputs.

### 8.3. Avoiding duplicates when JOINing multiple grants

A document with multiple ACEs or tags can multiply rows on a JOIN. If the query returns a `Page`, total row counts can inflate and break pagination. Use `EXISTS` when you only need to test whether a matching row exists, or `DISTINCT`/counting aligned with actual semantics.

For JPA queries combining `JOIN FETCH` on collections with pagination, the ORM may paginate differently from expected SQL. Consider a two-step fetch (paginate tenant-scoped IDs first, then fetch details by ID set and tenant) and verify the separate count query.

## 9. Pagination, counts, aggregations, and cursors must share the same tenant

### 9.1. Never load all tenants and filter in Java

Unsafe:

```java
// Bad design: over-fetching then filtering.
return repository.findAll(PageRequest.of(page, size))
    .map(DocumentEntity::getTenantId)
    .stream()
    .filter(tenantId::equals)
    .toList();
```

Drawbacks:

- Data from other tenants is already loaded before filtering.
- A page of `size=20` may yield only 3 rows for the current tenant.
- `totalElements` can reveal the system-wide document count.
- Unnecessary DB queries and memory consumption.
- Another code path might serialize/log objects before filtering.

The right way is `findByTenantIdAndState(trustedTenant, state, pageable)` so the DB filters **before LIMIT/OFFSET**.

### 9.2. `Page` vs. `Slice`

`Page` can run an extra count query to populate `totalElements`, so that count must also be tenant-scoped. `Slice` checks only whether a next page exists, avoiding expensive counts. For very large lists, keyset pagination can outperform OFFSET.

Whichever you choose, **the tenant predicate must appear in the query determining the next page**, and sort keys must be deterministic (`created_at`, `id` tie-breaker). Never let clients pass raw SQL `ORDER BY` or arbitrary column names; allowlist sortable fields only.

### 9.3. Aggregations/exports are often-forgotten leak paths

Dashboard `groupByState` endpoints, CSV exports, background reports, and GraphQL resolvers must all apply tenant predicates. Adding a `count()` method without tenant looks harmless, yet still leaks another organization's total document count.

Test **both counts and contents** for each tenant: never check only the first row while ignoring secondary metrics.

## 10. UPDATE, DELETE, bulk imports, and transactions

### 10.1. Put guards directly inside DML

A TOCTOU hazard:

```text
1. findByIdAndTenantId(id, tenant)
2. check owner
3. permission/owner changed by another transaction
4. updateById(id, title) WITHOUT tenant/owner guard
```

That is why in the demo, JPQL `changeTitleIfOwner` embeds **tenant, owner, state, and version inside the UPDATE itself**. If write policies depend on a separate grants/ACL table, use a DB-appropriate conditional UPDATE or lock and re-check permissions within a transaction also respected by grant/revoke operations.

A grant-based SQL update:

```sql
UPDATE documents
SET title = :newTitle,
    version = version + 1
WHERE id = :id
  AND tenant_id = :trustedTenant
  AND version = :expectedVersion
  AND EXISTS (
      SELECT 1
      FROM document_grants g
      WHERE g.document_id = documents.id
        AND g.tenant_id = documents.tenant_id
        AND g.grantee_id = :trustedUser
        AND g.permission = 'WRITE'
  );
```

**This SQL is illustrative**—it does not run against the demo schema (which lacks grants), and exact syntax/lock semantics depend on the DB. One statement alone does not guarantee real-time permission revocation across multiple data sources; define isolation and transaction protocols explicitly.

### 10.2. DELETE must protect tenant and relationships

Never call `repository.deleteById(id)` directly from a user endpoint if IDs could belong to another tenant. Replace with conditional deletion:

```java
@Modifying
@Query("""
    delete from DocumentEntity d
    where d.id = :id
      and d.tenantId = :tenantId
      and d.ownerId = :ownerId
    """)
int deleteOwned(
    @Param("id") Long id,
    @Param("tenantId") String tenantId,
    @Param("ownerId") String ownerId);
```

This is a **repository snippet**, not a method in the complete demo. JPA bulk deletes bypass in-memory entity lifecycle callbacks/cascades, so if documents have file storage or ACLs needing cleanup, use a proper domain workflow with transactions/outbox.

### 10.3. INSERT must not take tenant from arbitrary JSON

When creating a document:

```java
// Service SNIPPET:
Actor actor = directory.requireCurrent();

DocumentEntity newDocument = factory.create(
    actor.tenantId(),
    actor.userId(),
    command.title()
);
```

Tenant and owner are server-determined. If a multi-tenant user selects a tenant from the UI, the server must verify membership **before** creating data. Input DTOs should contain only fields the user is allowed to supply.

### 10.4. @Version, transactions, and changing grants

`@Version` on a document catches concurrent edits **to the document entity**, whereas changes in an ACL/grants table do not automatically increment that version. If rights are revoked between check and write, use re-checks, locks, or an authorization version aligned with your model. Never use `@Transactional(readOnly=true)` for DML, and never rely on `@PostAuthorize` as the sole guard for commands with side effects.

## 11. Row-Level Security (PostgreSQL): DB-layer defense-in-depth

When using PostgreSQL, **Row-Level Security (RLS)** enforces tenant isolation at the database level, reducing the impact if an application query omits `tenant_id`. It is a strong supplementary tool, provided **DB roles, connection pools, session/transaction contexts, and bypass privileges** are configured properly.

### 11.1. Illustrative RLS policy

For a `documents` table with a text/varchar `tenant_id`:

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_policy
ON documents
FOR ALL
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);

-- Optionally force table owners to obey RLS as well.
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
```

`USING` governs **existing rows allowed to be read/modified/deleted**; `WITH CHECK` governs **new rows allowed to be inserted/updated**. When `app.tenant_id` is unset, `current_setting(..., true)` returns NULL and tenant comparisons never evaluate to true (fail closed in the policy above).

This is a **PostgreSQL configuration snippet**, not SQL executed in the demo's H2 DB. PostgreSQL table owners normally bypass RLS without `FORCE`; **superusers and `BYPASSRLS` roles always bypass**. Never run the application as a superuser or bypass role while assuming policies protect every query.

### 11.2. Passing tenant into the DB transaction properly

Inside a transaction after verifying the tenant, a PostgreSQL application can run:

```sql
SELECT set_config('app.tenant_id', :trustedTenant, true);
```

The final argument `true` scopes the setting **locally to the transaction**, curbing the risk of connection pools carrying tenant context to another request. Use SQL parameter binding; never concatenate the tenant into query strings.

Yet this pattern is trustworthy only when:

- Every DB transaction needing a tenant sets the context **before the first query**.
- The tenant is verified from server identity, never client-supplied directly.
- The connection pool does not rely on arbitrary `SESSION` settings or leak across requests.
- All DB entrypoints (jobs, async, migrations, admin) follow dedicated policies.
- The app role does not bypass RLS, and `SECURITY DEFINER` functions are audited.
- Every tenant-owned table has policies, not just the documents table.
- Tests execute under a production-like DB role and verify missing tenant results in denial.

**RLS does not replace object or field permissions.** A `tenant_id = current_setting(...)` policy still exposes every record in the tenant unless the app adds owner/ACL rules.

### 11.3. Should queries keep explicit tenant filters when RLS is active?

Keeping **tenant-scoped repositories** is usually worthwhile: code expresses policy clearly, aids indexes/query plans, preserves portability, and simplifies unit/integration tests. RLS serves as **another defensive barrier**—never an excuse to drop authority/owner/status checks in services. Review application and RLS policies together so they never conflict or widen access.

## 12. Tenant scope, caching, and background jobs

### 12.1. Cache keys must never omit tenant

If a cache uses:

```text
key = documentId
```

and IDs are unique only per tenant, T1.Document#11 and T2.Document#11 collide on the same entry. Even with globally unique IDs, responses still depend on caller permissions and read/field-redaction policies.

Typical keys to consider:

```text
(tenantId, documentId, projection, policyVersion)
```

or add `(principalId, action)` when caching user-authorized outcomes. Never cache a system-wide `canRead(id)=true` boolean without user/tenant context.

Cache invalidation must fire when a document changes tenants, ACLs/grants are revoked, owners change, role memberships update, or field-level policies shift. Short TTLs do not equal instant revocation.

### 12.2. ThreadLocal tenant context does not cross threads automatically

Some codebases use a `ThreadLocal`-backed `TenantContextHolder`. Failing to clear it in `finally` lets another request on the same thread inherit the old tenant; with `@Async`, tenant context may **fail to propagate** to the worker thread.

Ways to mitigate risk:

- Prefer passing **trusted tenant** explicitly from application services to repository methods.
- If context is unavoidable, enforce strict set/clear lifecycles and validate before every query.
- For scheduled jobs, pass explicit tenant scope and use an appropriately authorized identity.
- With WebFlux/reactive, do not assume Servlet ThreadLocal semantics apply; use Reactor Context and appropriate security mechanisms.

### 12.3. Batch jobs spanning multiple tenants

An internal reporting job may need to process all tenants, yet it must never call `findAll()` on a normal API and “temporarily skip the tenant filter.” Build a dedicated `TenantAdminJob` flow with explicit authz, per-tenant pagination, access-reason auditing, and data minimization.

A pattern:

```text
authorizedAdminJob
  -> list permitted tenant IDs to process
  -> for each tenant:
       verify job scope
       query repository for that exact tenant ID
       emit results/metrics within that tenant's namespace
```

If business requirements call for a cross-tenant report, treat it as a **dedicated use case** with separate authorities, auditing, and aggregated-data access controls.

## 13. Tenant-safe relationships and constraints

### 13.1. Global ID vs. composite key

Two common models:

1. **Globally unique ID:** `documents.id` is global, and `tenant_id` is an independent constraint. Easy ID lookup, though the application must still filter by tenant.
2. **Tenant-local ID:** the same `id=11` exists across multiple tenants. Primary key can be `(tenant_id, id)`; every JOIN, foreign key, cache, and URL mapping must carry both.

With tenant-local IDs, never use a `Map<Long, Document>` or cache keyed by `id` alone. Use a key pairing tenant and document:

```java
record TenantDocumentKey(String tenantId, Long documentId) {
}
```

In JPA, use `@EmbeddedId` or `@IdClass` when modeling composite primary keys; `findByIdAndTenantId` in the demo assumes a globally unique `id` and does not automatically fit every composite-key entity.

### 13.2. Foreign keys must preserve tenant integrity too

A FK pointing only `documents.project_id -> projects.id` does not guarantee document and project share a tenant. Where schemas fit, a composite FK `(tenant_id, project_id)` locks that invariant in the DB. Depending on product rules, approved cross-tenant links may exist; model them as explicit sharing records rather than arbitrary joins.

### 13.3. Per-tenant unique constraints

For instance, document names or customer codes unique **within a tenant**, not across the entire DB:

```sql
CREATE UNIQUE INDEX uq_documents_tenant_code
ON documents(tenant_id, business_code);
```

**Illustrative SQL** for a schema with `business_code` (absent from the demo). Per-tenant uniqueness enforces data integrity, not automatic authorization. A user must still hold access within the tenant to query that code.

## 14. Performance: tenant predicates also optimize queries

A tenant-scoped query enables the database to leverage indexes:

```sql
CREATE INDEX idx_documents_tenant_state_id
ON documents(tenant_id, state, id);
```

An index on `(tenant_id, state, id)` helps `WHERE tenant_id=? AND state=? ORDER BY id` across many data models. Index design must still rely on **EXPLAIN/ANALYZE, cardinality, tenant skew, status distribution, and workload**. One tenant holding 90% of a table may yield a different query plan than thousands of small tenants.

For large datasets:

- Use properly scoped pagination; avoid `findAll` or unbounded materialization.
- Watch for N+1 queries over associations after filtering the root entity; lazy loading can still trigger extra queries.
- If using `JOIN FETCH`, verify its impact on pagination and count queries.
- Use projections/DTOs for needed fields instead of returning full entity graphs.
- Use tenant-aware caching with invalidation.
- Inspect query plans for both `SELECT` **and** `COUNT`.
- Never inject a client-supplied `OR tenant = ...` that can bypass indexes or policies.

**When optimizing, never drop the tenant predicate because a query looks slow.** Fix indexes, partitioning, or query shapes rather than removing the security boundary.

## 15. Common bugs and how to diagnose them

| Symptom | Root cause | Fix |
| --- | --- | --- |
| Alice reads T2's Document#13 | `findById(id)` omits tenant | `findByIdAndTenantId(id, trustedTenant)` |
| Tenant predicate exists, yet client picks T2 | Tenant taken from unverified query/header | Resolve from trusted membership directory |
| `findAll` returns every tenant's docs | Unscoped inherited repository method | Tenant-scoped service/facade, query guard |
| `Page` holds only 3/20 items | Filtered tenant after pagination | Place tenant in DB query before LIMIT |
| `totalElements` counts system-wide data | Count query omitted tenant | Count with identical tenant filter |
| JOIN returns another tenant's project data | JOIN only on ID | Check tenant on both tables, composite FKs where appropriate |
| OR branch exposes public doc of another tenant | Missing parentheses around `owner OR public` | `tenant = ? AND (owner = ? OR public)` |
| Bob in same tenant edits Alice's doc | Tenant treated as sufficient for WRITE | Check owner/ACL/state inside DML |
| UPDATE succeeds for another tenant's ID | DML had only `WHERE id = ?` | `WHERE id AND tenant AND owner/version` |
| ID missing so service falls back to `findAll` | Fail-open | Deny/404, never drop scope |
| Anonymous token accepted | Raw `isAuthenticated()` check | `AuthenticationTrustResolver` / `isAuthenticated` expression |
| `@PreAuthorize` present, yet query leaks | Authority does not add tenant filter | Guard directly in repository |
| Cache leaks data across tenants | Key omits tenant/identity | Tenant-aware cache keys and invalidation |
| Thread reuse retains previous tenant | Uncleaned tenant ThreadLocal | Scope lifecycle and explicit tenant parameters |
| RLS has no effect | App DB role is superuser/BYPASSRLS | Proper DB role, FORCE if needed, tests |
| RLS tenant setting leaks across pool | Unreset session setting | Transaction-local context, connection tests |
| Tests cover only tenant T1 | Misses cross-tenant flaws | Seed at least T1+T2, positive/negative tests |
| Entity adds public field without updating queries | Policy/DTO drift | Contract tests, review schema & API |
| System uses local IDs while cache keys by ID only | Cross-tenant collision | Composite key `(tenant, id)` |
| Bulk update skips JPA callbacks/version | `@Modifying` JPQL DML semantics | Explicit version predicate and transaction |
| RLS enabled, yet API leaks cached counts | Cache/report bypasses DB RLS | Tenant scope on every output path |

### Code review checklist for a multi-tenant endpoint

1. Identify `Authentication` and user ID from a verified provider.
2. Determine tenant scope / active tenant from server membership and check its status.
3. Verify functional authority before touching data.
4. For `findById`, ensure SQL/JPQL enforces `id AND tenant`.
5. For list/search, ensure **every OR branch** stays under the tenant filter.
6. For pagination/count/aggregation/export, use the exact same tenant predicate.
7. For JOINs/subqueries, check tenant on every involved table.
8. For UPDATE/DELETE, embed tenant and object/owner/version guards in DML.
9. Never bind `tenantId` from unverified JSON/client inputs.
10. Never call inherited `findAll`/`deleteById` on user endpoints.
11. Audit response DTOs, caches, background jobs, and async contexts.
12. Seed at least two tenants in integration tests and assert **invisible** cross-tenant data stays hidden.
13. With RLS, verify the DB role cannot bypass and session tenant is set/reset properly.
14. When grants/ACLs change concurrently, define transactions, locks, and re-check policies.

## 16. Self-check exercises

1. **Does `@PreAuthorize("hasAuthority('document:read')")` automatically add `tenant_id` to SQL?**  
   No. It checks functional authority; repositories must still enforce tenant predicates.

2. **Why is `findByIdAndTenantId(id, request.getTenantId())` insufficient?**  
   Because a client-supplied `tenantId` may belong to a victim tenant. Verify membership or obtain trusted tenant from the server.

3. **Which query properly filters owner and public docs within a tenant?**  
   `WHERE tenant_id = :tenant AND (owner_id = :user OR public = TRUE)`. Never let OR escape the tenant scope.

4. **Can you call `findAll(pageable)` and filter in Java?**  
   Unsuitable for tenant-isolated APIs: over-fetches, breaks pagination/counts, and risks leaking data.

5. **To display only the total count of DRAFTs, what does the count query need?**  
   `WHERE tenant_id = :trustedTenant AND state='DRAFT'`.

6. **Why include the tenant predicate inside the UPDATE statement?**  
   So the DB cannot modify another tenant's document even if the caller knows the ID or a race happens after a pre-check.

7. **Bob in T1 holds `document:write`; can he automatically edit Alice's Document#11?**  
   No under the demo policy. Owner and state conditions must also match.

8. **Does a JPQL bulk update automatically increment `@Version`?**  
   Never rely on that. The demo explicitly sets `d.version = d.version + 1` and checks `expectedVersion`.

9. **What happens if a JOIN matches only `project_id` and omits tenant?**  
   It can join cross-tenant relationships, especially if data/FKs do not block it. Enforce same-tenant joins/constraints.

10. **Does PostgreSQL RLS replace `@PreAuthorize`?**  
    No. RLS filters DB rows; functional, object, and field policies are still required.

11. **Why use a transaction-local tenant context for RLS?**  
    Because pooled connections are reused across requests, and stale session settings can leak tenants.

12. **If IDs are unique only per tenant, what must cache keys include?**  
    At least tenant ID and local ID; if responses depend on permissions, include identity/policy scope too.

13. **How do you test that Carol in T2 cannot read T1?**  
    Seed T1/T2, call the service with `@WithMockUser(carol)`, and assert T1 lookups are denied/not found while lists contain only T2 IDs.

14. **Is a Page with total `2` containing a row from another tenant safe?**  
    No. Assert **all contents** belong to the right tenant and zero forbidden rows appear.

15. **If the app needs a system-wide report, can a normal API drop the tenant filter?**  
    No. Create a dedicated admin/job flow with explicit authorities, scope, auditing, and purpose-built queries.

## 17. Official references

1. [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived queries, `@Query`, `@Param`, native queries, and `@Modifying`.
2. [Spring Data JPA — Defining Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): reserved methods, `Pageable`, `Page`/`Slice`, sorting, and counting records.
3. [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html): composing tenant predicates with dynamic criteria.
4. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, authentication, and proxies.
5. [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): datasources, JPA/JDBC, and SQL initialization.
6. [Spring Framework — Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): `@Transactional`, transaction boundaries, self-invocation, and rollback.
7. [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS, ENABLE/FORCE, bypasses, and row policies.
8. [PostgreSQL — CREATE POLICY](https://www.postgresql.org/docs/current/sql-createpolicy.html): `USING` and `WITH CHECK` semantics.
9. [OWASP API Security — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): unauthorized resource access by ID.
10. [OWASP Cheat Sheet — Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, checking permissions on every request, and least privilege.

**Conclusion:** tenant isolation must be enforced **directly inside repositories and all data queries**. `tenant_id = :trustedTenant` is meaningful only when the tenant is verified from server-side identity/membership. Apply that predicate to `SELECT`, `Page`, `COUNT`, JOINs, `EXISTS`, `UPDATE`, `DELETE`, and exports; layer on functional authorities, owner/ACL/state checks, and version/transaction guards. Use integration tests with at least two tenants and, where appropriate, PostgreSQL RLS to mitigate the risk of a query omitting tenant.