# Per-Tenant Administration vs. System-Wide Administration

> **Topic:** Spring Security – authorization → **Tenant Isolation**. This lesson distinguishes a **tenant administrator** (an administrator scoped to a single organization/customer) from a **system administrator** (a platform operations administrator), how to express permission scopes, and how to prevent cross-tenant access. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring Data JPA, and H2. Database Row-Level Security (RLS) defense-in-depth is covered separately with warnings regarding privileged accounts and tenant contexts.

## 1. The problem: same word “admin”, but administering what?

Suppose a shared SaaS platform serves multiple customers:

~~~text
                      SaaS PLATFORM
        +----------------+----------------+
        |                |                |
     Tenant ACME      Tenant BETA     System Ops
        |                |                |
     Alice: admin      Bob: admin     Root: system admin
     Carol: member     David: member  Operations / billing
        |                |
     ACME documents    BETA documents
~~~

Business requirements:

- Alice can administer users and documents belonging to **ACME**, but must not modify BETA's data.
- Bob can administer BETA, and must not view ACME documents simply for holding the same `TENANT_ADMIN` role.
- One person may administer **multiple tenants** if they hold independent memberships in each tenant.
- Root holds platform operational rights (e.g., monitoring health, creating tenants, configuring billing), but **does not automatically have access to read/modify every tenant's confidential content**.
- If tenant data intervention is genuinely required during an incident, there must be a **dedicated privileged path** with scope, justification, approval or step-up authentication, auditing, and revocation.

A common hazard is writing:

~~~java
// WRONG in many multi-tenant systems:
@PreAuthorize("hasRole('ADMIN')")
public void updateDocument(long id, String newTitle) {
    repository.findById(id).orElseThrow().rename(newTitle);
}
~~~

`hasRole('ADMIN')` only answers whether the user holds authority `ROLE_ADMIN` under the default prefix; **it does not state which tenant the user administers**, and `findById(id)` is not tenant-constrained. If every tenant admin holds `ROLE_ADMIN`, Alice can edit a BETA document by guessing its ID.

**Core principle:** administrative privilege is the combination of **actor + action + resource + scope + conditions**, not merely a role string.

## 2. Four conceptual layers not to conflate

| Concept | Question | Example |
| --- | --- | --- |
| **Identity** | Who is calling? | Authenticated subject `user-17` |
| **Role/authority** | Which group of actions is allowed? | `ROLE_TENANT_ADMIN`, `ROLE_SYSTEM_ADMIN` |
| **Scope/membership** | In which tenant is the privilege active? | `user-17` is tenant admin of `acme`, not `beta` |
| **Resource ownership** | Which tenant actually owns the resource? | Document#202 has `tenant_id = beta` |
| **Conditions** | Are there additional constraints? | Recent MFA, support ticket, legal hold, locked state |

If an actor holds `ROLE_TENANT_ADMIN` without an administrative membership in the target tenant, that is **insufficient**. If an actor is a tenant member holding only VIEWER, that is **also insufficient for administration**. Access is granted only when all elements align.

Notation:

~~~text
ALLOW tenant action when:
  authenticated(actor)
  AND hasAuthority(actor, "ROLE_TENANT_ADMIN")
  AND activeMembership(actor, targetTenant, "ADMIN")
  AND resource.tenantId == targetTenant
  AND satisfiesBusinessConditions(resource, action)
~~~

For system actions:

~~~text
ALLOW system operation when:
  authenticated(actor)
  AND hasAuthority(actor, "ROLE_SYSTEM_ADMIN")
  AND operation belongs to the defined system-operation set
  AND stepUp / approval / audit if the operation requires it
~~~

These two expressions are **different**. Never tack `OR hasRole('SYSTEM_ADMIN')` onto every tenant endpoint out of habit. System operations privileges can be separated from customer data access to enforce **least privilege**.

## 3. Permission matrix: tenant admin vs. system admin

| Action | ACME tenant admin | BETA tenant admin | Default system admin |
| --- | --- | --- | --- |
| View documents belonging to ACME | Per ACME policy | No | **Not by default** |
| Rename documents belonging to ACME | Yes if policy permits | No | **Not by default** |
| Manage ACME memberships | Yes, within grant limits | No | Via separate workflow |
| Manage BETA memberships | No | Yes | Via separate workflow |
| Grant `ROLE_SYSTEM_ADMIN` | **No** | **No** | Only via privileged control plane |
| Create a new tenant | No (by default) | No (by default) | Yes if assigned |
| Read system-wide infrastructure metrics | No | No | Yes per operational role |
| View BETA document contents for incident support | No | Per BETA policy | Only with controlled **break-glass** |
| Change a resource's tenantId | Never arbitrarily | Never arbitrarily | Only controlled migration workflow |
| View anonymized aggregate reports | Per tenant if allowed | Per tenant if allowed | Yes per assignment |
| Delete an entire tenant | No by default | No by default | Special verified workflow only |

This is a **recommended SaaS policy**, not automatic Spring Security behavior. The framework enforces decisions; your application must precisely define who may do what within which scope.

### 3.1. Same role does not mean same permissions

~~~text
Alice: ROLE_TENANT_ADMIN + adminMembership(ACME)
Bob:   ROLE_TENANT_ADMIN + adminMembership(BETA)

hasRole("TENANT_ADMIN") is true for both.
canAdministerTenant("acme") is true only for Alice.
canAdministerTenant("beta") is true only for Bob.
~~~

`ROLE_TENANT_ADMIN` is a **capability class**; specific membership determines **scope**.

### 3.2. One user can administer multiple tenants

For example, Sam:

~~~text
Sam: ROLE_TENANT_ADMIN
Membership:
  (sam, acme, ADMIN, active=true)
  (sam, beta, ADMIN, active=true)
~~~

Sam can switch administrative contexts between ACME and BETA, yet each request must still specify the target tenant and the system verifies the corresponding membership. Administering two tenants **does not** permit copying data between them without an explicit business policy.

### 3.3. A system admin is not “tenant admin of all tenants”

A system admin may handle infrastructure maintenance, billing, provisioning, or incident response without needing access to individual document contents. Granting wildcard `tenant=*` to every system admin expands the blast radius if an account is compromised. A safe pattern separates:

- **Control plane**: APIs managing infrastructure, tenants, pricing, and service health.
- **Data plane**: APIs reading/modifying/deleting a specific tenant's data.
- **Break-glass plane**: special data-support paths enabled with time bounds, approval, and auditing.

This is a logical separation; it can be deployed as microservices or inside a modular monolith. What matters is enforcing the right policy at each boundary.

## 4. TenantId in the URL is a selector, not proof of permission

A common endpoint:

~~~text
PATCH /api/tenants/acme/documents/101
Authorization: Bearer <token>
Body: {"title":"Reviewed"}
~~~

A user can edit the path to:

~~~text
PATCH /api/tenants/beta/documents/202
~~~

`tenantId=beta` is only **the target the caller asks to act upon**. It does not prove the caller belongs to BETA.

Right:

~~~text
1. Authenticate token/session → trusted principal ID.
2. Read tenantId from path to know the target.
3. Verify actor holds ADMIN membership in the target tenant.
4. Load document by (id, tenantId), not by id alone.
5. Verify state/business rules, then mutate inside a transaction.
6. Audit actor, target tenant, object, and action.
~~~

Wrong:

~~~java
// COUNTEREXAMPLE: trusting self-declared request inputs.
String tenantId = request.getHeader("X-Tenant");
if (request.getRole().equals("TENANT_ADMIN")) {
    repository.findById(documentId).orElseThrow().rename(title);
}
~~~

Client-supplied headers, queries, bodies, and paths are **untrusted selectors** unless cross-checked against an authoritative source. Even when tenant is embedded in a signed JWT, check that the caller still holds active membership in the target tenant; tokens can go stale after membership revocation.

## 5. Multi-layered architecture: check permissions, then constrain data

~~~text
HTTP Request
    |
    v
Authentication (verified JWT/session)
    |
    v
Controller / request routing
    |
    v
Method Security (@PreAuthorize)
    |
    v
TenantPolicy
  |-- ROLE_TENANT_ADMIN?
  |-- active ADMIN membership in target tenant?
    |
    v
Application Service (@Transactional)
    |
    v
Repository query constrained by tenant_id
    |
    v
Database (tenant_id + optional RLS)
~~~

A secure system must prevent this situation:

~~~text
Method Security checked ACME membership
yet Repository calls findById(202) without tenant filter
→ still risks reading/modifying a BETA row.
~~~

**Defense in depth:** service authorization and query tenant constraints are two independent locks. With PostgreSQL, Row-Level Security can act as a DB-layer barrier when properly configured, though it never replaces identity and request-scope controls.

### 5.1. Place the gate at the service layer, not solely in the controller

If REST controllers, GraphQL resolvers, message consumers, scheduled jobs, or CLI admin tasks all call repositories, a controller-only gate leaves other entrypoints unprotected. Place tenant authorization at the **application service boundary** so every entrypoint passes through it.

### 5.2. Never rely on a `ThreadLocal tenantId` from an unverified request

Some ORM filters or `CurrentTenantIdentifierResolver` implementations use a tenant context. If that context is populated from an unverified header, the system can filter into another tenant's data. Every request/job must establish tenant context from an **authorized** selection and clean up in `finally` / context boundaries to prevent leaking into subsequent requests.

### 5.3. Never use another tenant's ID to infer existence

If an ACME admin asks for BETA's Document#202, the service should return a generic “not available / denied” per contract so neither tenant name nor owner is disclosed. Mapping to HTTP 403 or 404 must align consistently with your anti-enumeration policy. Never return unauthorized resource metadata in error messages.

## 6. Spring Boot 3.x, Java 17+ example: checking both role and membership

We build a small application featuring:
- Tenant memberships for Alice, Bob, and Sam in a **demo** server-side directory.
- Documents stored in H2 with `tenantId`.
- A method editing a tenant's document, restricted to that tenant's admin.
- A separate system-wide reporting method restricted to system admins.
- Integration tests via Spring proxies proving tenant admins cannot cross tenants and system admins do not automatically edit tenant documents.

This app needs no HTTP endpoints. Tests invoke Spring-managed services directly to exercise Method Security, repositories, and transactions. Java code uses package `demo.tenancy`.

### 6.1. Dependencies

In a Spring Boot Gradle project already configured with the Java plugin, Spring Boot plugin, and compatible dependency management, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Never force a Security version incompatible with Boot 3.x. `@EnableMethodSecurity` will be declared on the application class; the Security starter alone **does not automatically** enable method authorization.

### 6.2. H2 configuration for integration tests

**`src/test/resources/application.properties`**

~~~properties
spring.datasource.url=jdbc:h2:mem:tenant_scope;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

`create-drop` and in-memory H2 are for demos/tests only. Production needs schema migrations, target-database row isolation/transactions/locking, and tenant-scoped indexes such as `(tenant_id, id)` for scoped lookups.

### 6.3. Main application

**`src/main/java/demo/tenancy/TenantAdminApplication.java`**

~~~java
package demo.tenancy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class TenantAdminApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantAdminApplication.class, args);
    }
}
~~~

### 6.4. Entity storing tenant explicitly

**`src/main/java/demo/tenancy/TenantDocument.java`**

~~~java
package demo.tenancy;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "tenant_documents")
public class TenantDocument {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 32, updatable = false)
    private String tenantId;

    @Column(nullable = false, length = 160)
    private String title;

    @Version
    private Long version;

    protected TenantDocument() {
        // JPA constructor
    }

    public TenantDocument(String tenantId, String title) {
        this.tenantId = tenantId;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getTitle() {
        return title;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
~~~

`tenantId` is assigned on document creation via an authorized use case. `updatable=false` in this demo prevents changing tenant via normal entity updates; it does **not** substitute for a formal tenant migration policy. `@Version` supports optimistic locking for entity lifecycles, without guaranteeing bulk JPQL updates obey version checks.

### 6.5. Repository always includes tenant predicate on the data plane

**`src/main/java/demo/tenancy/TenantDocumentRepository.java`**

~~~java
package demo.tenancy;

import java.util.List;
import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface TenantDocumentRepository
        extends JpaRepository<TenantDocument, Long> {

    List<TenantDocument> findAllByTenantIdOrderByIdAsc(String tenantId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select d from TenantDocument d
             where d.id = :id and d.tenantId = :tenantId
            """)
    Optional<TenantDocument> lockByIdAndTenant(
            @Param("id") Long id,
            @Param("tenantId") String tenantId);
}
~~~

`lockByIdAndTenant` combines object ID and tenant ID in the **same query**; if Alice operates in ACME yet sends a BETA document ID, zero rows are returned. `PESSIMISTIC_WRITE` reduces the chance of data changing between read and write inside a transaction, depending on the database.

`JpaRepository.findById(id)` remains callable elsewhere; **do not** assume the repository is automatically safe system-wide. Review rule: data-plane code must specify tenant predicates or use a controlled RLS/tenant-filter mechanism backed by tests catching missing predicates.

### 6.6. Server-trusted membership directory

**`src/main/java/demo/tenancy/TenantMemberships.java`**

~~~java
package demo.tenancy;

import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class TenantMemberships {

    // Demo: ADMIN membership is provisioned server-side.
    // Production: query membership table/IAM with active/revoked status.
    private final Map<String, Set<String>> adminTenants = Map.of(
            "alice", Set.of("acme"),
            "bob", Set.of("beta"),
            "sam", Set.of("acme", "beta"));

    public boolean isAdminOf(String subjectId, String tenantId) {
        return adminTenants
                .getOrDefault(subjectId, Set.of())
                .contains(tenantId);
    }
}
~~~

This fixed dataset is **not** a production membership management system. It lets JUnit verify both “user holds role without membership” and “user holds membership without role.” In real systems, `subjectId` should be a globally immutable ID from the verified token/identity provider; memberships should include status, valid-from/to, scope, auditing, and a revocation strategy.

### 6.7. Policy bean checking both role type and scope

**`src/main/java/demo/tenancy/TenantPolicy.java`**

~~~java
package demo.tenancy;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("tenantPolicy")
public class TenantPolicy {

    private final TenantMemberships memberships;

    public TenantPolicy(TenantMemberships memberships) {
        this.memberships = memberships;
    }

    public boolean canManageTenant(
            Authentication authentication,
            String tenantId) {

        return validActor(authentication)
                && validTenantId(tenantId)
                && hasAuthority(authentication, "ROLE_TENANT_ADMIN")
                && memberships.isAdminOf(
                        authentication.getName(), tenantId);
    }

    public boolean canOperateSystem(Authentication authentication) {
        return validActor(authentication)
                && hasAuthority(authentication, "ROLE_SYSTEM_ADMIN");
    }

    private boolean validActor(Authentication authentication) {
        return authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }

    private boolean validTenantId(String tenantId) {
        return tenantId != null
                && tenantId.matches("[a-z][a-z0-9-]{1,31}");
    }

    private boolean hasAuthority(Authentication authentication, String name) {
        return authentication.getAuthorities().stream()
                .anyMatch(a -> name.equals(a.getAuthority()));
    }
}
~~~

**Two completely separate decisions:**

- `canManageTenant(auth, tenantId)` requires `ROLE_TENANT_ADMIN` **and** membership in that exact target tenant. There is no “if system admin, return true” shortcut.
- `canOperateSystem(auth)` requires `ROLE_SYSTEM_ADMIN` for control-plane actions. This method takes no tenantId and grants zero access to tenant records.

`validTenantId` validates only the **canonical format** of the sample tenant ID; it **does not** verify a tenant exists or prove caller authorization. Membership is an essential part of the authorization decision.

Production roles/authorities must come from a verified `Authentication`, never client-declared JSON bodies or headers. You may use `RoleHierarchy`, but test carefully: letting `ROLE_SYSTEM_ADMIN` imply `ROLE_TENANT_ADMIN` **must not** turn system admins into admins of every tenant, and membership checks remain mandatory.

### 6.8. Service mutates only within the verified tenant

**`src/main/java/demo/tenancy/TenantDocumentService.java`**

~~~java
package demo.tenancy;

import java.util.List;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TenantDocumentService {

    public record DocumentView(Long id, String tenantId, String title) {
    }

    private final TenantDocumentRepository repository;

    public TenantDocumentService(TenantDocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
            "@tenantPolicy.canManageTenant(authentication, #tenantId)")
    @Transactional(readOnly = true)
    public List<DocumentView> listWithinTenant(
            @P("tenantId") String tenantId) {

        return repository.findAllByTenantIdOrderByIdAsc(tenantId)
                .stream()
                .map(d -> new DocumentView(
                        d.getId(), d.getTenantId(), d.getTitle()))
                .toList();
    }

    @PreAuthorize(
            "@tenantPolicy.canManageTenant(authentication, #tenantId)")
    @Transactional
    public void renameWithinTenant(
            @P("tenantId") String tenantId,
            Long documentId,
            String title) {

        if (title == null || title.isBlank() || title.length() > 160) {
            throw new IllegalArgumentException("Invalid title");
        }

        TenantDocument document = repository.lockByIdAndTenant(
                documentId, tenantId)
                .orElseThrow(() ->
                        new AccessDeniedException("Document not available"));

        document.rename(title);
        repository.flush();
    }
}
~~~

**Path analysis:**

1. `@PreAuthorize` invokes `TenantPolicy` via bean name `tenantPolicy`, passing the Spring Security-provided `Authentication` and `#tenantId`.
2. `@P("tenantId")` lets SpEL resolve the parameter without depending on the `-parameters` compiler flag.
3. If the caller is not an admin of the target tenant, Method Security throws `AccessDeniedException` before entering the method body.
4. The service method further queries by **both** `documentId` and `tenantId`. If the ID belongs to another tenant, nothing is returned.
5. `@Transactional` wraps the write. `@Version` helps detect concurrent entity changes; `PESSIMISTIC_WRITE` requests a DB lock on the selected row.
6. Data returned via `DocumentView` contains only tenant-scoped rows. Never return lazy JPA entity graphs that could expose cross-tenant relationships.

In this demo, `title` is low-sensitivity and there are no external side effects. If a service adds sharing, notifications, or file deletion, enforce per-action permissions and coordinate side effects after commit/outbox. A READ check does not grant DELETE.

### 6.9. System operations live in a separate service

**`src/main/java/demo/tenancy/SystemOperationsService.java`**

~~~java
package demo.tenancy;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SystemOperationsService {

    private final TenantDocumentRepository repository;

    public SystemOperationsService(TenantDocumentRepository repository) {
        this.repository = repository;
    }

    // Example operational metric permitted in the control plane.
    @PreAuthorize("@tenantPolicy.canOperateSystem(authentication)")
    @Transactional(readOnly = true)
    public long globalDocumentCount() {
        return repository.count();
    }
}
~~~

`globalDocumentCount()` is an action granted specifically to system admins, returning an **aggregate count** without granting permission to view individual documents or modify any document. In production, even aggregate metrics can be sensitive; apply appropriate policies and auditing.

**Do not do this**:

~~~java
// COUNTEREXAMPLE: any system admin accidentally bypasses tenant checks.
@PreAuthorize("""
    hasAuthority('ROLE_SYSTEM_ADMIN') or
    @tenantPolicy.canManageTenant(authentication, #tenantId)
    """)
public void changeTenantDocument(String tenantId, Long id) {
    repository.findById(id).orElseThrow().rename("changed");
}
~~~

If a system administrator **genuinely** needs to edit a document to resolve an incident, create a separate method/endpoint such as `emergencyChangeForTenant(...)` with approval, expiration, ticket, MFA, and auditing—never hide an out-of-scope bypass inside an `OR` expression on a normal API.

## 7. Integration tests: same role across tenants and system admin cannot bypass

Tests use `@SpringBootTest` with H2, real Spring Security Method Security, and real JPA. `@WithMockUser` assigns principal/authorities per test; it does not perform password authentication or JWT signing. Services are obtained from the Spring Context so annotations/proxies apply.

**`src/test/java/demo/tenancy/TenantAuthorizationTest.java`**

~~~java
package demo.tenancy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(classes = TenantAdminApplication.class)
class TenantAuthorizationTest {

    @Autowired TenantDocumentRepository repository;
    @Autowired TenantDocumentService tenantService;
    @Autowired SystemOperationsService systemService;

    private Long acmeId;
    private Long betaId;

    @BeforeEach
    void seed() {
        repository.deleteAll();
        repository.flush();

        acmeId = repository.saveAndFlush(
                new TenantDocument("acme", "ACME-original")).getId();
        betaId = repository.saveAndFlush(
                new TenantDocument("beta", "BETA-original")).getId();
    }

    private String title(Long id) {
        return repository.findById(id).orElseThrow().getTitle();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ROLE_TENANT_ADMIN")
    void tenantAdminCanManageOwnTenant() {
        tenantService.renameWithinTenant("acme", acmeId, "ACME-reviewed");

        assertEquals("ACME-reviewed", title(acmeId));
        assertEquals(1, tenantService.listWithinTenant("acme").size());
        assertEquals("BETA-original", title(betaId));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ROLE_TENANT_ADMIN")
    void tenantAdminCannotSelectAnotherTenant() {
        assertThrows(AccessDeniedException.class, () ->
                tenantService.renameWithinTenant(
                        "beta", betaId, "Hacked"));

        assertEquals("BETA-original", title(betaId));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ROLE_TENANT_ADMIN")
    void tenantAdminCannotUseForeignIdInOwnTenant() {
        assertThrows(AccessDeniedException.class, () ->
                tenantService.renameWithinTenant(
                        "acme", betaId, "Hacked"));

        assertEquals("BETA-original", title(betaId));
    }

    @Test
    @WithMockUser(username = "mallory", authorities = "ROLE_TENANT_ADMIN")
    void authorityWithoutMembershipCannotManageTenant() {
        assertThrows(AccessDeniedException.class, () ->
                tenantService.listWithinTenant("acme"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void membershipWithoutAdminAuthorityCannotManageTenant() {
        assertThrows(AccessDeniedException.class, () ->
                tenantService.listWithinTenant("acme"));
    }

    @Test
    @WithMockUser(username = "root", authorities = "ROLE_SYSTEM_ADMIN")
    void systemAdminDoesNotImplicitlyBecomeTenantAdmin() {
        assertThrows(AccessDeniedException.class, () ->
                tenantService.renameWithinTenant(
                        "acme", acmeId, "Hacked"));

        assertEquals("ACME-original", title(acmeId));
    }

    @Test
    @WithMockUser(username = "root", authorities = "ROLE_SYSTEM_ADMIN")
    void systemAdminCanCallExplicitSystemMetric() {
        assertEquals(2L, systemService.globalDocumentCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ROLE_TENANT_ADMIN")
    void tenantAdminCannotCallSystemMetric() {
        assertThrows(AccessDeniedException.class,
                () -> systemService.globalDocumentCount());
    }

    @Test
    @WithMockUser(username = "sam", authorities = "ROLE_TENANT_ADMIN")
    void membershipInTwoTenantsPermitsTwoExplicitContexts() {
        tenantService.renameWithinTenant("acme", acmeId, "A");
        tenantService.renameWithinTenant("beta", betaId, "B");

        assertEquals("A", title(acmeId));
        assertEquals("B", title(betaId));
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotManageAnyTenant() {
        assertThrows(AccessDeniedException.class,
                () -> tenantService.listWithinTenant("acme"));
    }
}
~~~

### 7.1. What must be proven

| Test | Security meaning |
| --- | --- |
| Alice edits ACME | Right role + membership + tenant row |
| Alice selects BETA | Generic role does not open another tenant |
| Alice passes BETA document ID under ACME route | Repository `id + tenantId` blocks IDOR |
| Mallory has role without membership | Blocks privilege escalation from generic authority |
| Alice has membership without role | Membership does not auto-grant admin rights |
| Root has SYSTEM_ADMIN without ACME membership | No default data-plane bypass |
| Root reads system metric | Control-plane action defined separately |
| Alice cannot call system metric | Tenant admin does not become system admin |
| Sam administers two tenants | Memberships may span tenants, but scope is explicit |
| Anonymous is blocked | Authentication required before action |

### 7.2. Running the tests

On macOS/Linux:

~~~text
./gradlew test --tests demo.tenancy.TenantAuthorizationTest
~~~

On Windows:

~~~text
gradlew.bat test --tests demo.tenancy.TenantAuthorizationTest
~~~

There is no `System.out.println`, so there is no fixed business stdout. In a properly configured environment, the expected verification is all assertions passing and Gradle completing the `test` task. The code was statically reviewed in this article; execute it in your real project and test against a production-compatible database before using real policies.

Do not mechanically annotate the entire test class with `@Transactional`: the test may auto-roll back at method end and mask commit/transaction boundary bugs in the service. In this example, the test only seeds and reads back via the repository, while the service is called through its proxy.

## 8. Why distinguish “can administer a tenant” from “can grant permissions to others”?

A tenant admin can typically manage user memberships and roles within their tenant. However, if an admin can arbitrarily grant `ROLE_SYSTEM_ADMIN`, compromising one tenant escalates into **platform-wide compromise**.

### 8.1. Scoped role-granting rules

| Caller | Grant/revoke target | Permitted? |
| --- | --- | --- |
| ACME tenant admin | Grant VIEWER role in ACME | Yes per policy |
| ACME tenant admin | Grant TENANT_EDITOR in ACME | Yes per policy and permission ceiling |
| ACME tenant admin | Grant tenant admin in ACME | May require owner approval / 2-person rule |
| ACME tenant admin | Grant admin in BETA | No |
| ACME tenant admin | Grant SYSTEM_ADMIN | **No** |
| System admin | Grant SYSTEM_ADMIN to a user | Privileged control-plane workflow only |
| System admin | Grant read access to customer documents | Not by default; requires break-glass |

A dangerous example:

~~~java
// COUNTEREXAMPLE: requested role is an arbitrary string.
@PreAuthorize("@tenantPolicy.canManageTenant(authentication,#tenantId)")
public void grantRole(
        String tenantId, String targetUser, String role) {
    membershipRepository.grant(targetUser, tenantId, role);
}
~~~

If `role` can be `SYSTEM_ADMIN`, the tenant admin has been handed **out-of-scope privilege**. Policy must validate **the role being granted too**:

~~~text
allowGrant(actor, targetTenant, requestedRole)
  = canManageTenant(actor, targetTenant)
    AND requestedRole is in TENANT_GRANTABLE_ROLES
    AND targetTenant == membership.tenantId
    AND caller is not self-escalating against policy
    AND sufficient approval exists for sensitive grants
~~~

Whitelist example:

~~~java
// ILLUSTRATIVE policy helper, not a standalone service method.
private static final Set<String> TENANT_GRANTABLE_ROLES = Set.of(
        "TENANT_VIEWER", "TENANT_EDITOR");

// SYSTEM_ADMIN is intentionally omitted from the whitelist.
boolean canGrantByTenantAdmin(String role) {
    return TENANT_GRANTABLE_ROLES.contains(role);
}
~~~

In production, store roles via a server-managed enum/permission catalog instead of trusting arbitrary strings; tenant admins must also be blocked from changing tenant ownership, altering billing plans, deleting audits, or escalating privileges by guessing role names.

### 8.2. Self-service membership must never become self-promotion

Watch out for privilege escalation paths:

~~~text
Member Alice calls POST /tenants/acme/memberships
Body: {"userId":"alice","role":"TENANT_ADMIN"}
~~~

If the API merely checks that Alice is an ACME member and allows changing roles, Alice can promote herself to admin. Granting memberships must belong to a distinct permission group checking both actor and `requestedRole`; some systems also require a tenant owner or security approver.

### 8.3. A tenant admin cannot arbitrarily move data across tenants

An API `moveDocument(sourceTenant, destinationTenant, id)` spans **two scopes**. You must verify export rights in the source, import rights in the destination, data residency and legal hold policies, and an atomic migration workflow. “Admin in source” is **never** automatically “admin in destination.”

## 9. System admin: control-plane actions, support access, and break-glass

### 9.1. Classifying system-level actions

Authorities can be split:

~~~text
ROLE_SYSTEM_OPERATOR      - safe restart/health/config
ROLE_SYSTEM_TENANT_ADMIN  - tenant provisioning/disable
ROLE_SYSTEM_BILLING_ADMIN - billing config
ROLE_SECURITY_AUDITOR     - view audits within approved scope
ROLE_SUPPORT_BREAK_GLASS  - time-bounded emergency data access
~~~

This is **one design option**, not built-in Spring Security roles. Splitting roles prevents a single account from holding every privilege. In many organizations, infrastructure operators have no need for daily access to customer data.

### 9.2. Break-glass is not a “skip all checks” button

If support needs to view a tenant's data to handle a P1 incident, a safe workflow might look like:

~~~text
Authenticated system operator
    |
    +-- requests support access for Tenant ACME
    +-- incident ticket, specific target
    +-- step-up MFA / approval
    +-- 15-minute limit and READ-only (example)
    +-- issue short-lived capability/entitlement
    +-- verify capability on every request
    +-- tamper-evident audit + alert to tenant/security
    +-- auto-expire/revoke and re-verify
~~~

A user holding `ROLE_SYSTEM_ADMIN` without a ticket or break-glass entitlement **does not** bypass data-plane policy. The 15-minute duration is only an example; the actual limit depends on risk level and internal regulations.

### 9.3. Special flows must have separate endpoints and auditing

Conceptual example:

~~~java
// ILLUSTRATIVE ONLY: SupportEntitlementService and AuditService must
// be fully implemented; does not run standalone.
@PreAuthorize("@supportPolicy.canUseBreakGlass(authentication,#tenantId,#ticket)")
@Transactional(readOnly = true)
public DocumentView supportRead(
        @P("tenantId") String tenantId,
        String ticket,
        Long documentId) {

    // Even under break-glass, still query by (tenantId, documentId).
    TenantDocument document = repository
            .findByIdAndTenantId(documentId, tenantId)
            .orElseThrow(() -> new AccessDeniedException("Not available"));

    auditService.recordSupportRead(
            authentication.getName(), tenantId, ticket, documentId);

    return toView(document);
}
~~~

The method above is only a design **shape**; without `supportPolicy`, `auditService`, and `toView`, it is not presented as a buildable file. In practice, auditing needs a durable strategy so a transaction rollback does not erase the audit entry; reliable event recording may require an outbox.

Never rely on `@PostAuthorize` as the sole gate for actions that already caused side effects. When support requires writing data, authorize before mutating within the same transaction and SQL tenant conditions.

## 10. Tenant isolation in the database: shared schema, schema-per-tenant, DB-per-tenant

| Storage layout | Strengths | Risks/costs |
| --- | --- | --- |
| Shared schema, `tenant_id` column | Easy operations, fewer DBs | Easy to omit tenant predicate in a query |
| Schema-per-tenant | Clearer logical/schema separation | Schema routing, bulk migrations, connection context |
| Database-per-tenant | Stronger infra boundary, separate backups | Higher cost/orchestration/partitioning complexity |
| PostgreSQL RLS in shared schema | Database can filter rows by policy | Must control DB roles/session context and bypass cases |
| Hybrid | Tailored to scale and data sensitivity | Multiple code/migration paths to test |

No storage layout automatically guarantees authorization if request tenant selectors or database credentials are untrusted. Even DB-per-tenant leaks data if the router takes `tenantId` from an unverified header and connects to the wrong database.

### 10.1. Queries must include tenant predicates

Right in normal services:

~~~sql
SELECT id, title
FROM tenant_documents
WHERE tenant_id = :authorized_tenant
  AND id = :document_id;
~~~

On update:

~~~sql
UPDATE tenant_documents
SET title = :new_title
WHERE tenant_id = :authorized_tenant
  AND id = :document_id;
~~~

When running raw SQL UPDATE/DELETE, check affected row counts and transactions; zero rows may mean nonexistent or out of scope—do not infer the caller “lost tenant access” without additional proof. For batch updates, if one row lacks access, define an explicit all-or-nothing vs. best-effort contract.

### 10.2. PostgreSQL Row-Level Security is a supplementary layer, not magic

Illustrative policy example:

~~~sql
ALTER TABLE tenant_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_document_isolation
ON tenant_documents
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
~~~

In an app using a connection pool, ensure `app.tenant_id` is set **per transaction** from the server-authorized tenant and cleared without leaking context to other requests. If arbitrary code can change that setting to another tenant, an RLS policy relying on it ceases to be an independent enforcement boundary.

**Crucial PostgreSQL rule:** superusers and roles with `BYPASSRLS` always bypass Row-Level Security; table owners also normally bypass RLS unless `FORCE ROW LEVEL SECURITY` is appropriately enabled. Therefore, normal application traffic must not run under a DB superuser or bypassing table owner when relying on RLS to protect tenant data. Test `USING`/`WITH CHECK` policies with the actual runtime database role and session context.

We do **not** run that PostgreSQL SQL on the H2 database in the main example; the RLS snippet is strictly for PostgreSQL architecture.

### 10.3. Background jobs and system reports also need policies

A job aggregating across tenants may need to read many rows, yet it should never reuse a tenant-scoped data path and arbitrarily turn off tenant filters. Build dedicated cross-tenant analytics repositories/services returning minimal aggregates and running under a privileged principal/service account with auditing and an action allowlist.

In async processing, `SecurityContextHolder` and request-scoped contexts do not automatically flow across threads/messages. Consumers must authenticate the system identity, the command's tenant scope, and required permissions—never trusting a `tenantId` sent by an unauthenticated producer.

## 11. Membership lifetimes, statuses, and stale token risks

A realistic membership record might include:

~~~text
subject_id | tenant_id | role         | status | valid_until
-----------+-----------+--------------+--------+------------
user-17    | acme      | TENANT_ADMIN | ACTIVE | ...
user-17    | beta      | VIEWER       | ACTIVE | ...
user-42    | beta      | TENANT_ADMIN | REVOKED| ...
~~~

What to test:

- When membership is revoked, the service denies access on the very next check within the published consistency guarantee.
- When a user leaves ACME, they cannot access it using an old `tenantId` lingering in local context.
- Sessions/JWTs previously issued with `ROLE_TENANT_ADMIN` may still exist; **effective tenant permissions** must stay synced via fresh memberships/entitlements.
- If memberships are cached, enforce proper invalidation/revisions/TTLs; never rely solely on stale roles inside JWTs.
- Temporary memberships must auto-expire and be revoked upon user offboarding.
- Tenant administrators may be suspended or tenants disabled; check both states during authorization.

The Spring `TenantPolicy` example queried the server-side (mock) directory **on every call**; production may use caching, but must measure and accept revocation lag. For sensitive data permissions, prefer the source of truth or revision checks.

### 11.1. Switching tenant context in the UI

An account with memberships in ACME and BETA may select “working in ACME.” That selection determines only the **target scope** for requests. The server must re-verify membership on every sensitive operation. Never check only “Sam belongs to both tenants” and let hidden UI `tenantId` state trigger execution in the wrong scope.

### 11.2. User IDs must be immutable and tenant-distinct

Do not use mutable emails or usernames as the sole membership key if names can collide across tenants. Use a stable subject ID alongside an explicit tenant ID in memberships, and never let a new account inherit old permissions simply because a username was recycled.

## 12. Severe common authorization mistakes

| Symptom | Root cause | Fix |
| --- | --- | --- |
| Alice (ACME admin) edits BETA documents | Checked only `ROLE_TENANT_ADMIN` | Add membership scope + repository tenant predicate |
| Root system admin views all documents | Added `or hasRole('SYSTEM_ADMIN')` to data endpoints | Separate system ops and break-glass |
| Changing `tenantId` in URL switches data | Trusted client-sent tenant selector | Bind target tenant to verified membership |
| Membership without role still acts as admin | Checked membership existence only | Check role/action + membership status |
| Admin role without membership still granted | Checked authority only | Check active ADMIN membership |
| Tenant admin grants themselves SYSTEM_ADMIN | `grantRole` accepts arbitrary role string | Role allowlist and grant-scope policy |
| ACME admin grants role in BETA | Grant API lacks tenant predicate | Check actor/target tenant in same transaction |
| Revoked user still retains access | Stale JWT or membership cache | Appropriate revocation/version/TTL |
| Spring annotation present but not blocking | Missing `@EnableMethodSecurity` or self-invocation | Enable Method Security, test via bean proxy |
| SpEL `#tenantId` is null | Parameter name mismatch, missing `-parameters` | Use `@P("tenantId")` |
| `findById` returns another tenant's row | Missing tenant scope | `id + tenantId` repository methods / RLS |
| IDOR via export, search, attachments | Protected only update endpoints | Audit all read/export/delete/list paths |
| RLS has no effect | App role is superuser/table owner/BYPASSRLS | Use restricted DB role, FORCE RLS where needed |
| Tenant context bleeds to next request | Uncleaned ThreadLocal/session state | Strict context lifecycle, concurrency tests |
| Background job skips authorization | Job calls privileged service/repo arbitrarily | System principal/tenant scope + explicit policy |
| Tenant switch leaks over connection pool | Session variable/schema not reset | Transaction-local SET LOCAL, test connection reuse |
| Cross-tenant reporting leaks PII | System role reads all raw rows | Minimal aggregates, purpose limitation, auditing |
| Root incident access unlogged | Break-glass lacks ticket/MFA/audit | Dedicated path, short-lived entitlement, alerts |
| Role hierarchy opens unintended privileges | SYSTEM_ADMIN implies TENANT_ADMIN | Still enforce membership and explicit action checks |

## 13. Extended testing matrix for real systems

| Actor | Role | Active membership | Target | Operation | Expectation |
| --- | --- | --- | --- | --- | --- |
| Alice | TENANT_ADMIN | ACME | ACME | Rename document | Allow |
| Alice | TENANT_ADMIN | ACME | BETA | Rename document | Deny |
| Alice | TENANT_ADMIN | ACME | ACME route + BETA ID | Rename document | Deny |
| Bob | TENANT_ADMIN | BETA | ACME | List documents | Deny |
| Mallory | TENANT_ADMIN | None | ACME | List documents | Deny |
| Alice | DOC_READ | ACME admin membership | ACME | Rename document | Deny |
| Sam | TENANT_ADMIN | ACME, BETA | Each tenant separately | Rename | Allow within scope |
| Root | SYSTEM_ADMIN | None | ACME | Normal tenant rename | Deny |
| Root | SYSTEM_ADMIN | None | System | Aggregate report | Allow |
| Alice | TENANT_ADMIN | ACME | System | Aggregate report | Deny |
| Alice | TENANT_ADMIN | ACME | ACME | Grant SYSTEM_ADMIN | Deny |
| Root | SYSTEM_ADMIN | None | BETA sensitive data | Emergency read without ticket | Deny |
| Root | SUPPORT_BREAK_GLASS | Expired entitlement | BETA | Emergency read | Deny |
| Alice (revoked) | TENANT_ADMIN in old JWT | ACME REVOKED | ACME | Rename document | Deny per revocation policy |
| System job | Service principal | Specific report scope | All tenants | Aggregate | Allowlisted operations only |

Beyond API tests, test every path:
- HTTP REST, GraphQL, WebSocket, exports/reports, file downloads, search/autocomplete.
- Background workers, message consumers, scheduled tasks, CLI migrations.
- Bulk updates/deletes, ACL and membership management, support tools.
- Database RLS with connection pools and the real application role.
- Auditing, events, and revocation lag after membership changes.

**Highest-value negative tests:** same role across different tenants; foreign tenant ID inside a valid route; system admin hitting tenant endpoints; tenant admin attempting to grant high-privilege roles; altered tenant selector in headers/bodies; old sessions after revocation.

## 14. Design and operations checklist

A multi-tenant Spring Security system can apply this checklist:

1. Are **control plane**, **data plane**, and **break-glass** actions clearly separated?
2. Are actors identified by a verified subject ID?
3. Is `tenantId` in requests cross-checked against active memberships?
4. Does the policy check authority + tenant admin membership + resource tenant?
5. Are system admins denied by default on tenant data endpoints?
6. Do repositories enforce `tenant_id` on reads, updates, deletes, searches, and exports?
7. Are there IDOR tests passing another tenant's document ID on a valid tenant route?
8. Are tenant admins blocked from granting system roles or changing roles outside their tenant?
9. Are self-promotion and uncontrolled ownership/migration transfers prevented?
10. Do memberships track active/revoked/expired states with an invalidation mechanism?
11. If using RLS, is it tested under the real DB role without superuser/owner bypass?
12. Is tenant context cleaned up whenever connections or threads are reused?
13. Do cross-tenant commands require reason, target, timeout, audit, and alerts?
14. Does system analytics return minimal aggregates without leaking PII outside policy?
15. Do security tests run through Spring proxies rather than calling policies directly?
16. When incident support access expires, is revocation verified across all caches and nodes?

## 15. Practice exercises

**Exercise 1 – Tenant admin cannot cross tenants.** Run the Alice/Bob tests. Temporarily remove `tenantId` from `lockByIdAndTenant` in a scratch branch and write a test catching the IDOR. Restore the type+ID+tenant constraint.

**Exercise 2 – Admin of two tenants.** Make Sam admin of ACME and BETA. Add tenant GAMMA outside Sam's memberships. Test that Sam administers the two tenants, yet cannot administer GAMMA despite holding `ROLE_TENANT_ADMIN`.

**Exercise 3 – Revoked membership.** Replace the demo Map with a membership table tracking `ACTIVE/REVOKED`. Revoke Alice from ACME; keep `ROLE_TENANT_ADMIN` on `Authentication` and verify rename is denied.

**Exercise 4 – Restricted role granting.** Build `grantTenantRole` with whitelist `TENANT_VIEWER` and `TENANT_EDITOR`, restricted to the target tenant's admin. Test that Alice cannot grant BETA roles or `ROLE_SYSTEM_ADMIN` in any tenant.

**Exercise 5 – Break-glass.** Build a `supportRead` use case requiring a dedicated system role, ticket, reason, recent MFA, approval, and time-bounded entitlement. Test that omitting any condition denies access—including a system admin without a ticket—and verify auditing and expiration.

**Exercise 6 – PostgreSQL RLS.** On a PostgreSQL test database, enable RLS on tenant documents. Test that the runtime app DB role under ACME context cannot read BETA; then separately verify owner role, `BYPASSRLS`, and `FORCE ROW LEVEL SECURITY`. Never set tenant from an unverified header.

**Exercise 7 – Data export and background jobs.** Design a per-tenant document export endpoint and a system-level reporting job; prove queries/repositories cannot return raw data of other tenants simply because the job runs as a system service account.

**Exercise 8 – Role hierarchy.** Configure a system role higher than tenant role in a test setup. Verify `TenantPolicy.canManageTenant` still denies Root when membership in the target tenant is absent.

**Completion criteria:** distinguish tenant admin from system admin; understand roles alone do not define scope; use `@PreAuthorize` with `@P("tenantId")` and trusted memberships; enforce tenant constraints in repositories and prove cross-tenant negative tests; isolate system operations in the control plane and design break-glass workflows; recognize limits of JWT/session caches, PostgreSQL RLS, and connection contexts.

## Official references

- Spring Security – **Method Security**, `@EnableMethodSecurity`, `@PreAuthorize`, custom beans, and `@P` parameter annotations: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security – **Authorization Architecture** and `AuthorizationManager`: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security – **Authorize HTTP Requests** (request-level authorization and ordering): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security – **Testing Method Security**, `@WithMockUser`, and `@WithAnonymousUser`: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Data JPA – **Locking**, `@Lock` on repository queries: https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html
- Spring Framework – **Declarative Transaction Management**, `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- PostgreSQL – **Row Security Policies**, `ENABLE/FORCE ROW LEVEL SECURITY`, table owners, and `BYPASSRLS`: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
