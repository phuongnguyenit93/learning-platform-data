# Tenant as a Data and Authorization Boundary in Multi-Tenant Applications

> **Topic:** Spring Security – authorization · **Group:** Tenant Isolation. This Knowledge article explains why a tenant (a customer/organization sharing a SaaS platform) must serve as **the boundary for both data and authorization decisions**, rather than just a display label or UI filter parameter. The article focuses on Spring Boot Servlet + Spring Security 6.x, Java 17+, JPA/JDBC, and data security design; the PostgreSQL Row-Level Security (RLS) section serves as an optional infrastructure-dependent defense-in-depth layer. Code snippets using Spring are explicitly noted as running inside a project with dependencies already configured, whereas plain JDK examples can be run standalone.

## 1. What should you be able to do after this lesson?

1. Define tenant, membership, active tenant, principal, resource owner, authority, and object-level permission; distinguish the tenant boundary from permissions within a tenant.
2. Explain the trust chain from HTTP/JWT → principal authentication → membership verification → active tenant selection → action check → tenant-scoped resource query → business/ACL check.
3. Never trust `X-Tenant-ID`, the `/tenants/{id}` path, or `tenantId` in JSON as proof of authorization; treat them solely as **tenant selection requests** that must be verified against a trusted server-side source.
4. Design queries/inserts/updates/deletes to always include a tenant scope; understand why calling `findById(id)` and checking afterward can cause data leaks or race conditions.
5. Compare three storage models: shared schema with a `tenant_id` column, separate schema per tenant, and separate database per tenant; understand the role and limits of PostgreSQL RLS.
6. Apply Spring Security URL/method security, membership policy, and scoped repositories; enforce tenant authorization across every invocation path (HTTP, scheduled jobs, async, queues).
7. Prevent leaks across caches, search, exports, object storage, file uploads, audit logs, events, correlation, bulk operations, and multi-table joins.
8. Write cross-tenant GRANT/DENY/NOT_FOUND tests, list queries, write operations, tenantless data, connection reuse, and nested resources.
9. Identify pitfalls such as “having feature permission on the wrong tenant”, “client-declared tenant used directly”, “tenant context leaking across thread pools”, “unbounded global admin”, and “RLS bypassed by DB role”.

## 2. A tenant is not just a data column

A document management system serves two enterprise customers:

~~~text
SaaS platform
  |
  +-- Tenant alpha (Company A)
  |     +-- Alice: document:read, document:write
  |     +-- Document 101: "Plan A"
  |     +-- Project 20: "Project A"
  |
  +-- Tenant beta (Company B)
        +-- Bob: document:read
        +-- Document 201: "Plan B"
        +-- Project 30: "Project B"
~~~

If Alice knows or guesses the ID of Document 201, the application **must not** return beta's data simply because Alice is logged in and holds the `document:read` authority. The following statement alone is **not sufficient**:

~~~java
@PreAuthorize("hasAuthority('document:read')")
public Document find(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

`document:read` represents a general capability; it does not state **which tenant**, **which resource**, or **when**. To allow a request, all of the following are typically required simultaneously:

~~~text
ALLOW =
  actor is validly authenticated
  AND actor is an authorized member in the active tenant
  AND action is permitted by policy in that tenant
  AND the object truly belongs to the verified tenant
  AND ACL/ownership/business state (if any) also permits it
~~~

If any mandatory condition lacks proof, **do not grant access**. Error messages sent to the client must follow the API contract and avoid disclosing the existence of another tenant's document.

### 2.1. A user can belong to multiple tenants

Alice may be an employee of Company A and a collaborator at Company B. **Principal Alice does not imply a fixed active tenant.** When operating in alpha, the application must read/write against alpha; when switching to beta, it must verify membership and permissions for beta **at the time of the switch / on the corresponding request**.

~~~text
Alice authenticated (stable principal ID = user-17)
  memberships:
    alpha -> role EDITOR
    beta  -> role VIEWER
  active tenant selected: beta
  effective action: READ on beta, NOT WRITE on beta
~~~

You must not take the EDITOR role from alpha and apply it to beta. Simply having a generic authority name like `ROLE_EDITOR` does not mean it applies unconditionally across all tenants. This can be modeled using tenant-scoped roles/memberships or a custom `AuthorizationManager` that looks up policies per tenant.

### 2.2. Separating four concepts

| Concept | Example | Who verifies it? |
| --- | --- | --- |
| `principalId` | `user-17` | Authentication provider/identity directory |
| `requestedTenantId` | `alpha` in URL or header | Client **proposal**, not proof |
| `membership` | `user-17` is EDITOR of alpha, VIEWER of beta | Server-trusted identity/membership store |
| `resource.tenantId` | Document 101 belongs to alpha | DB/resource store with integrity constraints |

The **active tenant** is the tenant chosen **after** verifying membership, not an arbitrary string field assigned into a `ThreadLocal` from the client.

### 2.3. Tenant boundary differs from object authorization

Two users both belong to alpha, but Document 101 only has a READ ACL entry for Alice. Even though Bob is also a member of alpha, Bob **can still be denied** access to Document 101 if the policy includes object-level ACL/ownership. Tenant scope is a necessary condition, not a replacement for intra-tenant rules.

Conversely, an ACL ACE that mistakenly grants READ to an alpha user on a beta Document must **never** override the tenant boundary. For sensitive resources, combine the mandatory tenant check with ACL, for example:

~~~text
allOf(
    authenticated,
    membershipInResourceTenant,
    actionAllowedInActiveTenant,
    resourceAclAllowsAction
)
~~~

When using `AuthorizationManagers.allOf(...)` with a custom manager that can return `null` (abstain), remember fallback behavior and evaluation order. A mandatory tenant condition must return DENY when it cannot verify, **never** abstain and accidentally let other checks GRANT.

## 3. Threat model: how does “cross-tenant leakage” happen?

### 3.1. IDOR / Broken Object Level Authorization

A beta user sends:

~~~http
GET /api/tenants/beta/documents/101
Authorization: Bearer [Bob's token]
~~~

Document 101 actually belongs to alpha. If the controller ignores the tenant in the URL and calls `repository.findById(101)`, alpha's data may be leaked. Even if subsequent code checks the tenant, an exception message or log entry emitted before the check can already disclose the title or owner.

### 3.2. Mass assignment and forged tenant

~~~json
{
  "title": "Secret",
  "tenantId": "victim-tenant",
  "ownerId": "someone-else"
}
~~~

If a Document creation API simply executes `new Document(body.tenantId, ...)`, an attacker can insert a document into an unauthorized tenant or create an unauthorized association. For creation requests, select the tenant from the **verified context**; derive owner/creator from the authenticated principal or a valid delegation policy.

### 3.3. Cross-tenant query in export/search

The list endpoint may filter by `tenant_id`, while an export job uses a different unfiltered query; the search index returns all tenants; backup/report files are accessed with a global token. Correct authorization in one controller does not protect every data path.

### 3.4. Connection/thread reuse

An alpha request sets `tenantContext.set(alpha)` in a `ThreadLocal`, but the code fails to clear it; the servlet/async worker reuses that thread for beta. Subsequent queries mistakenly read alpha. Similarly, an RLS tenant session variable that is not reset in a connection pool can retain the old context.

### 3.5. Cross-tenant reference

A Comment belongs to tenant beta, yet `document_id` points to a Document belonging to alpha. If the foreign key only references ID, the DB may still allow cross-tenant linking even when each table has its own `tenant_id`. That is why tenant-aware constraints are needed, not just repository filters.

### 3.6. Elevated administrator

A support agent with global privileges may need to assist a customer, but break-glass privileges **must not be the default on every request**. There should be a workflow with explicit tenant confirmation, time bounds, reason/ticket, auditing, least privilege, and pre-access checks before viewing data.

## 4. Trust chain for a request

~~~text
Request GET /api/tenants/alpha/documents/101
    |
    v
(1) Authentication filter:
    validate Basic/OIDC/JWT/session credential
    -> principal user-17, valid issuer/audience/signature
    |
    v
(2) Tenant selection:
    requested tenant "alpha" from route
    -> ONLY a selector, not yet trusted
    |
    v
(3) Membership/tenant policy:
    does user-17 have an active membership in alpha?
    does user-17 have document:read permission in alpha?
    -> trusted ActiveTenantContext(alpha, user-17, read)
    |
    v
(4) Repository:
    SELECT ... WHERE id=101 AND tenant_id='alpha'
    -> only alpha data can be returned
    |
    v
(5) Object/business policy:
    owner/ACL, publish state, retention, classification
    |
    v
(6) Response:
    only permitted information; no cross-tenant resource leakage
~~~

**Do not invert the order in a dangerous way:** running a global query, loading a beta Document, logging all its fields, and only then performing the membership check. Likewise, do not check alpha membership only in the controller while leaving a public service callable from a scheduler without tenant enforcement.

### 4.1. Header, subdomain, path, and token

A tenant can be selected from:
- Path: `/api/tenants/{tenantId}/...`.
- Host: `alpha.example.com`.
- Header: `X-Tenant-ID: alpha`.
- A token claim containing the active tenant.
- A server-side session active tenant after a verified switch step.

**Every client-controlled value is untrusted input until verified.** The Host header must also be validated by the reverse proxy/ingress; avoid blindly trusting `X-Forwarded-Host`. Signed JWT claims require verifying the signature, `iss`, `aud`, expiration, and a trusted issuer source. A token carrying a tenant claim does not automatically grant access to every object in that tenant.

### 4.2. Multi-issuer authentication is not data isolation

Spring Security OAuth2 Resource Server can use `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` for multiple **already trusted** issuers. This is the layer that selects the token authentication strategy; it **does not automatically guarantee** that queries always filter by tenant. Never read a self-declared issuer from a token and fetch an arbitrary JWK URL; always validate against an allow-list / trusted tenant configuration.

Similarly, one issuer may issue tokens for multiple tenants; do not assume `iss` = `tenant_id` in your domain. The mapping contract among issuer, principal, tenant, and membership belongs to the application/identity provider and must be tested.

## 5. Choosing a multi-tenant storage model

| Model | Strengths | Risks and protection requirements |
| --- | --- | --- |
| **Single DB, single schema, every table has `tenant_id`** | Simple operations, shared migrations, cost management | Must filter all access paths; risk of missing WHERE tenant; RLS can be added as reinforcement |
| **Single DB, separate schema per tenant** | Clear namespace boundary, per-schema backup/migration | Select the right schema, never trust schema strings from requests; prevent connection pool leaks, manage schema migrations |
| **Separate DB per tenant** | Stronger storage/credential/backup isolation, easier to satisfy certain compliance rules | Datasource routing, secret rotation, migrations across many DBs, cost, cross-tenant jobs/admin; does not automatically guarantee app authorization |
| **Hybrid** | Sensitive tenants get dedicated DBs, majority shared | Complex routing and observability; tenant moves must be consistently controlled |

No storage model automatically makes an API secure. A dedicated DB reduces blast radius if credentials leak, but code can route to the wrong datasource; a shared DB with RLS can be very strong if the DB role and tenant session context are right. The decision depends on isolation requirements, tenant scale, cost, compliance, and operational expertise.

### 5.1. Shared tables must include tenant_id in the data

Example:

~~~sql
CREATE TABLE tenant (
    id VARCHAR(40) PRIMARY KEY,
    display_name VARCHAR(160) NOT NULL
);

CREATE TABLE document (
    tenant_id VARCHAR(40) NOT NULL,
    id BIGINT NOT NULL,
    title VARCHAR(180) NOT NULL,
    owner_id VARCHAR(120) NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id) REFERENCES tenant(id)
);

CREATE TABLE document_comment (
    tenant_id VARCHAR(40) NOT NULL,
    id BIGINT NOT NULL,
    document_id BIGINT NOT NULL,
    content VARCHAR(1000) NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, document_id)
        REFERENCES document(tenant_id, id)
);
~~~

A **composite foreign key** prevents a beta Comment from pointing to an alpha Document **directly in the DB**. If you want a globally unique `id` rather than a per-tenant ID, you can still add `UNIQUE(tenant_id, id)` to establish a composite FK and scoped queries. Do not create a FK solely on `document.id` and assume the tenants of both rows will naturally match.

### 5.2. Indexes and uniqueness must also be tenant-aware

Email, slug, project code, or invoice number may only need to be unique **within the same tenant**. In that case:

~~~sql
CREATE UNIQUE INDEX document_title_unique_per_tenant
    ON document(tenant_id, title);
~~~

This is merely an example if the business genuinely requires unique titles; typically titles are allowed to duplicate. For catalog keys, use `UNIQUE(tenant_id, local_key)` instead of an unnecessary global unique constraint. Conversely, a stable global principal ID may need to be unique across tenants depending on the identity model.

Indexes should support `WHERE tenant_id = ? AND id = ?` and tenant list queries; never run a query that scans a large dataset and filters in Java memory.

### 5.3. Tenant lifecycle

When onboarding a tenant:
- Create the tenant identity with status PENDING/ACTIVE/SUSPENDED.
- Grant initial membership through a trusted flow; never accept an arbitrary owner ID in the request body.
- Provision quotas, namespace, encryption keys/secrets, and retention policies according to design.
- Mark ACTIVE only after schemas/ACLs/policies/resources are ready.
- Suspending a tenant must block HTTP, background jobs, and data exports alike—not just lock the UI.
- Tenant deletion/offboarding requires deciding retention, backups, audit legal hold, object storage, and cache purging per contract.

The tenant ID should be stable and free of confusing or unsuitable data for an identifier; the display name can change without changing the tenant ID.

## 6. Authorization must be bound to the active tenant

### 6.1. Global vs. per-tenant authorities

For example, Alice holds `document:read` globally on her account, while her memberships grant:
- alpha → EDITOR
- beta → VIEWER

In alpha, Alice can read/write if the ROLE_EDITOR policy allows it. In beta, Alice can only read. If the system only checks a generic `hasAuthority('document:write')`, it could accidentally permit WRITE in beta. Therefore, either:
1. Store roles/permissions per membership and query by active tenant at the authorization point; or
2. Issue tokens containing tenant-scoped permissions with update/revocation verification workflows, while still checking resource tenant; or
3. Combine global feature authorities with per-tenant membership and action policy (the simplified pattern below).

**The demo uses option (3):** authorities act as feature gates; membership acts as the tenant gate. The demo lets members of the same tenant read all documents if they hold the global read authority; production systems can add per-object ACLs.

### 6.2. Contract of TenantMembershipPolicy

A policy reusable across services might expose:

~~~java
void requireAccess(Authentication authentication,
                   String requestedTenant,
                   String requiredAction);
~~~

It must:
- Verify the principal is authenticated and not anonymous.
- Verify the requested tenant has valid syntax/ID and is ACTIVE.
- Retrieve membership from a server-side identity directory/repository.
- Compare roles/permissions **within the requested tenant**, without mixing other tenants.
- If membership has expired, tenant is suspended, the record is missing, or a remote policy service fails → fail closed / throw a clearly handled exception.
- Return a **verified** context or throw `AccessDeniedException`.
- Write minimal audit records for sensitive actions without leaking metadata of other tenants.

Do not use `@PreAuthorize("hasAuthority('ROLE_USER')")` alone as proof that a user belongs to a tenant. Role authorities may be global or session-wide and cannot prove “the right tenant” unless modeled to do so.

### 6.3. Roles of URL and method security

`SecurityFilterChain` can enforce authentication and route-level conditions. `@PreAuthorize` protects services at the method level; domain services require tenant scope whether invoked from a controller, message listener, or batch job. To reduce bypass risk, place tenant policy in application services and data access, not solely in MVC argument resolvers.

If you have a custom `AuthorizationManager<RequestAuthorizationContext>`, it can verify the tenant path before the request reaches the controller. However, **resource filtering is still required** during queries; an alpha member must not load a beta row using a guessed ID.

## 7. Spring Boot example: membership + scoped repository + method security

This example intentionally uses an **in-memory repository** to focus on authorization without mixing in transactions/JPA/RLS. It is a complete Spring Boot Servlet application when placed in a project with the proper dependencies; data and passwords are for demonstration only. API:

~~~text
GET  /api/tenants/{tenantId}/documents
GET  /api/tenants/{tenantId}/documents/{id}
POST /api/tenants/{tenantId}/documents
~~~

- `alice` has `document:read` + `document:write`, member of alpha and beta.
- `bob` has `document:read`, member of beta only.
- `viewer` lacks `document:read`, member of alpha.
- Document 1 belongs to alpha, Document 2 belongs to beta.
- The URL tenant is a selector that **must pass the membership check**.
- The repository returns only records whose `tenantId` matches.

Save as `src/main/java/demo/tenant/TenantBoundaryApplication.java`:

~~~java
package demo.tenant;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class TenantBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantBoundaryApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(a -> a
                        .requestMatchers("/api/tenants/**").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        // CSRF is not disabled; POST requires CSRF when policy demands it.
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("document:read", "document:write")
                    .build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("document:read")
                    .build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("profile:read")
                    .build());
        // {noop} is for learning only; production requires a secure encoder.
    }
}

record Document(long id, String tenantId,
                String creatorId, String title) {
}

record NewDocument(@NotBlank @Size(max = 100) String title) {
}

@Component
class TenantMemberships {
    // Server-side fixture: clients cannot tamper with this Map.
    private final Map<String, Set<String>> members = Map.of(
            "alice", Set.of("alpha", "beta"),
            "bob", Set.of("beta"),
            "viewer", Set.of("alpha"));

    void requireMember(Authentication actor, String tenant) {
        if (actor == null || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken) {
            throw new AccessDeniedException("Authentication required");
        }
        if (tenant == null
                || !tenant.matches("[a-z][a-z0-9-]{0,31}")
                || !members.getOrDefault(actor.getName(), Set.of())
                            .contains(tenant)) {
            throw new AccessDeniedException("Tenant access denied");
        }
    }
}

@Component
class DocumentStore {
    private final ConcurrentMap<Long, Document> rows =
            new ConcurrentHashMap<>(Map.of(
                    1L, new Document(1L, "alpha", "alice", "Budget A"),
                    2L, new Document(2L, "beta", "bob", "Budget B")));
    private final AtomicLong nextId = new AtomicLong(10L);

    Optional<Document> findWithinTenant(String tenant, long id) {
        Document row = rows.get(id);
        return Optional.ofNullable(row)
                .filter(d -> d.tenantId().equals(tenant));
    }

    List<Document> listWithinTenant(String tenant) {
        return rows.values().stream()
                .filter(d -> d.tenantId().equals(tenant))
                .sorted(Comparator.comparingLong(Document::id))
                .toList();
    }

    Document insertWithinTenant(String trustedTenant,
                                String creator, String title) {
        long id = nextId.getAndIncrement();
        Document row = new Document(id, trustedTenant, creator, title);
        rows.put(id, row);
        return row;
    }
}

@Service
class DocumentService {
    private final TenantMemberships memberships;
    private final DocumentStore store;

    DocumentService(TenantMemberships memberships, DocumentStore store) {
        this.memberships = memberships;
        this.store = store;
    }

    private Authentication actor() {
        return SecurityContextHolder.getContext().getAuthentication();
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Document read(String tenant, Long id) {
        memberships.requireMember(actor(), tenant);
        // Tenant-scoped lookup. Wrong tenant or nonexistent record both yield 404.
        return store.findWithinTenant(tenant, id)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PreAuthorize("hasAuthority('document:read')")
    public List<Document> list(String tenant) {
        memberships.requireMember(actor(), tenant);
        return store.listWithinTenant(tenant);
    }

    @PreAuthorize("hasAuthority('document:write')")
    public Document create(String tenant, NewDocument command) {
        Authentication authenticated = actor();
        memberships.requireMember(authenticated, tenant);
        // No tenantId/creatorId taken from request body.
        return store.insertWithinTenant(
                tenant, authenticated.getName(), command.title());
    }
}

@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Document get(@PathVariable("tenantId") String tenant,
                 @PathVariable("id") Long id) {
        return service.read(tenant, id);
    }

    @GetMapping
    List<Document> list(@PathVariable("tenantId") String tenant) {
        return service.list(tenant);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    Document create(@PathVariable("tenantId") String tenant,
                    @Valid @RequestBody NewDocument request) {
        return service.create(tenant, request);
    }
}
~~~

### 7.1. Dependencies for Spring Boot 3.x

Place in `build.gradle` of a project that already has the Spring Boot Gradle plugin, dependency management, and Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is only a `dependencies` block, **not a complete build.gradle file**. You can generate a project via Spring Initializr. On Unix run `./gradlew bootRun`, and on Windows run `gradlew.bat bootRun`. If using Spring Boot 4, re-check test/MockMvc packages and dependencies for that version; this article targets Spring Boot 3.x.

### 7.2. Why separate into three layers?

- `SecurityFilterChain` authenticates routes so unauthenticated users cannot gain access.
- `DocumentService` is a **Spring bean protected by a method-security proxy**. `@PreAuthorize` checks feature permissions before entering the method body; `TenantMemberships` verifies the caller-selected tenant, and then the repository filters by tenant.
- `DocumentStore` is the data boundary; both `read` and `list` accept `tenant`; `create` uses the verified tenant rather than taking it from the request body.

In the demo, `TenantMemberships` only stores membership and does not yet model per-tenant roles. Because Alice holds global `document:write`, she can write in both alpha and beta. If Alice's policy in beta is VIEWER only, replace `requireMember` with `requirePermission(actor, tenant, "document:write")` or a custom `AuthorizationManager` using action-scoped membership. **Do not copy this demo into production when tenant-scoped roles are required.**

### 7.3. Why must lookups stay within tenant scope?

~~~java
// RIGHT PATH: query/resource scope is constrained by tenant.
store.findWithinTenant(tenant, id);

// WRONG PATH: load data across all tenants and hope to check later.
store.findById(id);
~~~

A JPA repository typically defines:

~~~java
// Spring Data JPA snippet; requires defined entity/repository.
Optional<DocumentEntity> findByTenantIdAndId(
        String tenantId, Long id);

Page<DocumentEntity> findByTenantId(
        String tenantId, Pageable pageable);
~~~

For bulk updates/deletes, include the tenant condition and check the affected row count:

~~~java
// SQL pattern - only update resources within the verified tenant.
UPDATE document
SET title = :title
WHERE tenant_id = :tenantId AND id = :documentId;
~~~

If 0 rows are updated, it may be the wrong tenant or nonexistent; do not retry `UPDATE WHERE id = ?` without the tenant predicate. With `@Modifying`/JPA, inspect the returned row count and transaction. If a mutation requires owner/ACL verification, add the predicate or check under an appropriate transaction/lock to avoid TOCTOU.

### 7.4. Points intentionally omitted from the demo

The in-memory store lacks persistent transactions, DB tenant constraints, per-document ACLs, time-varying role memberships, auditing, pagination, and rate limiting. For a real application, add:
- A persistent member registry by tenant/action, tenant ACTIVE state, and stable IDs.
- Owner/ACL/classification/state checks when resources are sensitive.
- Transactions + SQL tenant predicates on every read/write path.
- Unique keys, composite foreign keys, and RLS/database permissions where appropriate.
- Auditing + monitoring for cross-tenant access and repeated 403/404 probing.
- Tenant-scoped cache keys, file storage policies, and scheduled job contexts.

## 8. MockMvc integration tests: proving zero data leakage

Tests must pass through the Spring context and Security Filter Chain; do not merely call `new DocumentService(...)` because that bypasses `@PreAuthorize`. For Spring Boot 3.x tests, create `src/test/java/demo/tenant/TenantBoundaryApplicationTest.java`:

~~~java
package demo.tenant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.everyItem;
import static org.hamcrest.Matchers.is;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantBoundaryApplicationTest {
    @Autowired MockMvc mvc;

    @Test
    void aliceReadsAlphaDocument() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/1")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenantId").value("alpha"))
                .andExpect(jsonPath("$.title").value("Budget A"));
    }

    @Test
    void bobCannotSelectAlpha() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/1")
                    .with(httpBasic("bob", "demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void bobCannotReadAlphaIdViaBetaRoute() throws Exception {
        mvc.perform(get("/api/tenants/beta/documents/1")
                    .with(httpBasic("bob", "demo")))
                .andExpect(status().isNotFound());
    }

    @Test
    void bobReadsDocumentWithinBeta() throws Exception {
        mvc.perform(get("/api/tenants/beta/documents/2")
                    .with(httpBasic("bob", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenantId").value("beta"));
    }

    @Test
    void alphaListContainsOnlyAlphaRows() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[*].tenantId",
                        everyItem(is("alpha"))));
    }

    @Test
    void missingFeatureAuthorityIsDenied() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/1")
                    .with(httpBasic("viewer", "demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousIsRejectedByBasicEntryPoint() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/1"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void bobCannotCreateWithoutWriteAuthority() throws Exception {
        mvc.perform(post("/api/tenants/beta/documents")
                    .with(httpBasic("bob", "demo"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Attempt\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void aliceCanCreateOnlyInSelectedMemberTenant()
            throws Exception {
        mvc.perform(post("/api/tenants/alpha/documents")
                    .with(httpBasic("alice", "demo"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"New Alpha Doc\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.tenantId").value("alpha"))
                .andExpect(jsonPath("$.creatorId").value("alice"));
    }

    @Test
    void aliceCannotSelectUnknownTenantForCreate()
            throws Exception {
        mvc.perform(post("/api/tenants/gamma/documents")
                    .with(httpBasic("alice", "demo"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Forbidden Doc\"}"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Test notes:** `@AutoConfigureMockMvc` in Spring Boot 3.x integrates the filters under standard configuration. `httpBasic(...)` sends Basic credentials, and `csrf()` attaches a CSRF token for POST per Spring Security Test mechanics. These tests **do not** prove production SQL row-scoping or database RLS: they prove the HTTP → service → in-memory scoped store path.

To run:

~~~bash
./gradlew test
~~~

Or `gradlew.bat test` on Windows.

### 8.1. An important security distinction between 403 and 404

- Bob selects `alpha` without membership → 403 in the demo, because the tenant selector is rejected.
- Bob is a beta member querying Document 1 (owned by alpha) via `/beta/documents/1` → 404, because the scoped lookup finds no record in beta.
- An unauthenticated caller → 401 via the Basic entry point.
- Bob lacks `document:write` → 403.

There is no single rigid HTTP rule for every product; an application may intentionally return 404 instead of 403 to deter resource/tenant enumeration, provided it is consistent and leaks no metadata. **What must never change is that another tenant's data is never returned.**

### 8.2. Regression testing for missing tenant filters

A useful mutation test: temporarily change `findWithinTenant` to `rows.get(id)` and run `bobCannotReadAlphaIdViaBetaRoute`. The test must turn red because Bob would receive alpha's data from the beta route. If it does not fail, the test suite is not yet protecting the data boundary.

Similarly, removing `memberships.requireMember(actor(), tenant)` must turn `bobCannotSelectAlpha` red. Removing `@PreAuthorize` or omitting `@EnableMethodSecurity` must turn `missingFeatureAuthorityIsDenied` and the POST missing-write test red. This is how you verify authorization test quality, rather than merely checking “HTTP 200”.

## 9. PostgreSQL RLS: an additional line of defense at the database

The shared-table model can use PostgreSQL Row-Level Security so the DB automatically enforces predicates on each row. This is a **defense-in-depth layer**, not a substitute for authentication, membership, ACLs, domain validation, or proper DB role provisioning.

Separate schema example to illustrate RLS:

~~~sql
CREATE TABLE document_rls (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL
);

ALTER TABLE document_rls ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_rls FORCE ROW LEVEL SECURITY;

CREATE POLICY document_rls_select
ON document_rls FOR SELECT
USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY document_rls_insert
ON document_rls FOR INSERT
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY document_rls_update
ON document_rls FOR UPDATE
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY document_rls_delete
ON document_rls FOR DELETE
USING (tenant_id = current_setting('app.tenant_id', true));
~~~

`current_setting('app.tenant_id', true)` returns the DB session's tenant context or NULL if not yet set (in relevant configurations/versions); comparing against NULL never evaluates to true, so data is not exposed by default. If the tenant context is set incorrectly, RLS **can return wrong results** because the DB trusts the supplied value—which is why the app must verify context before setting it.

### 9.1. Set tenant context per transaction, avoid connection pool leaks

~~~sql
BEGIN;
SELECT set_config('app.tenant_id', 'alpha', true);
SELECT id, tenant_id, title FROM document_rls ORDER BY id;
COMMIT;
~~~

The third parameter `true` in `set_config` means **local to the current transaction**. In Java/JDBC, use a PreparedStatement/bind parameter to pass the tenant already verified by the membership policy; never concatenate an unverified tenant ID into a SQL string. Do not use session-level `SET` and then return the connection to the pool with the old tenant intact.

If a transaction begins after the tenant context was set, or a JDBC call executes on a different connection, RLS may not see the context—this typically causes deny/empty results, which must never be fixed by disabling RLS. Integrate tenant setting with the transaction manager and test on the same connection.

### 9.2. RLS only works with appropriate roles and policies

PostgreSQL documentation emphasizes:
- Superusers or roles with `BYPASSRLS` **bypass** row-level policies.
- Table owners normally bypass them unless `FORCE ROW LEVEL SECURITY` is enabled.
- `TRUNCATE` and certain schema operations are not governed by row policies in the same way as `SELECT/UPDATE/DELETE/INSERT`.
- Appropriate SQL `GRANT` privileges must be given; RLS does not grant table operation rights.

Therefore, the production application DB role should not be a superuser or hold BYPASSRLS. Separate migration/admin DB roles from the runtime role. Test using **actual runtime DB credentials**, rather than running tests as owner/admin and assuming RLS protects you.

### 9.3. Key limitations of a tenant session variable

If an attacker can execute arbitrary SQL under the app DB role, they could attempt `set_config('app.tenant_id', 'beta', true)` before querying. An application-set custom GUC is not cryptographic proof that “the user belongs to beta.” RLS in this example is defense-in-depth against code omitting WHERE tenant when the **application trusted context** is properly set, not protection against all forms of SQL injection if the DB role is allowed to switch its own tenant context.

Use prepared statements, avoid arbitrary SQL execution, enforce least privilege, review SECURITY DEFINER functions, and choose a stronger architecture when your threat model assumes an attacker can control SQL execution.

### 9.4. WITH CHECK prevents inserts/updates into another tenant

`USING` governs which rows can be seen/touched in SELECT/UPDATE/DELETE; `WITH CHECK` validates the row state **after INSERT/UPDATE** to decide whether creation/modification is allowed. Omitting WITH CHECK on the appropriate policy can allow an account updating `tenant_id` to move a row unintentionally, depending on policy combinations. Always test that `UPDATE ... SET tenant_id='beta'` from an alpha transaction is rejected.

### 9.5. RLS does not replace composite foreign keys

A beta comment referencing an alpha document by ID does not become valid merely because RLS shows the beta comment. Tenant-aware data constraints are still needed, and note that PostgreSQL foreign key checks have special semantics with respect to row policies. Composite FK schema design remains essential to prevent cross-tenant links.

## 10. Hibernate @Filter and schema routing: avoiding confusion

You can use Hibernate filters, multi-tenancy support, or Spring Data query methods to attach the tenant. However:
- `@Filter` must be enabled on the right session and relevant mappings/queries; do not assume every native SQL query or bulk DML statement is filtered.
- Custom repositories, JDBC templates, native queries, search DSLs, and stored procedures can bypass ORM query scoping.
- Datasource/schema routing based on ThreadLocal requires safe cleanup whenever connections, pools, or async execution change.
- `@Where` or soft-delete predicates do not replace a user-context-aware tenant policy.
- Any temporary privilege elevation for migrations/admin jobs must be tightly controlled—never open a global “bypass tenant filter” for regular requests.

**Layering:** method/`AuthorizationManager` determines **who may do what**; repository/RLS determines **which data actually enters scope**. Use both when leakage risk is significant.

## 11. Standalone Java 17: proving the tenant boundary without Spring

The following program uses plain JDK to simulate membership, action authority, tenant-scoped resource lookup, and an owner rule. Its purpose is to demonstrate the difference between:
- DENY_TENANT: actor does not belong to the selected tenant.
- DENY_ACTION: actor lacks feature read authority.
- NOT_FOUND: ID does not exist in the permitted tenant (it may exist in another tenant).
- DENY_OBJECT: within the same tenant, but the object owner policy denies access.
- ALLOW: all conditions are met together.

Save as `TenantBoundaryDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class TenantBoundaryDemo {
    record User(String name, Set<String> tenants,
                Set<String> authorities) {}

    record Document(long id, String tenant, String owner, String title) {}

    static final Map<Long, Document> DATA = Map.of(
            1L, new Document(1L, "alpha", "alice", "Budget A"),
            2L, new Document(2L, "beta", "bob", "Budget B"),
            3L, new Document(3L, "alpha", "carol", "Plan C"));

    static String read(User user, String requestedTenant, long id) {
        if (user == null || requestedTenant == null
                || !user.tenants().contains(requestedTenant)) {
            return "DENY_TENANT";
        }
        if (!user.authorities().contains("document:read")) {
            return "DENY_ACTION";
        }

        Document doc = DATA.get(id);
        if (doc == null || !doc.tenant().equals(requestedTenant)) {
            // Do not leak the real title/owner/tenant of a cross-tenant record.
            return "NOT_FOUND";
        }
        if (!doc.owner().equals(user.name())) {
            return "DENY_OBJECT";
        }
        return "ALLOW:" + doc.title();
    }

    static int countWithinTenant(String tenant) {
        return (int) DATA.values().stream()
                .filter(d -> d.tenant().equals(tenant))
                .count();
    }

    public static void main(String[] args) {
        User alice = new User("alice",
                Set.of("alpha", "beta"), Set.of("document:read"));
        User bob = new User("bob",
                Set.of("beta"), Set.of("document:read"));
        User viewer = new User("viewer",
                Set.of("alpha"), Set.of("profile:read"));

        System.out.println("alice-alpha-1=" +
                read(alice, "alpha", 1L));
        System.out.println("alice-beta-2=" +
                read(alice, "beta", 2L));
        System.out.println("bob-alpha-1=" +
                read(bob, "alpha", 1L));
        System.out.println("bob-beta-1=" +
                read(bob, "beta", 1L));
        System.out.println("bob-beta-2=" +
                read(bob, "beta", 2L));
        System.out.println("viewer-alpha-1=" +
                read(viewer, "alpha", 1L));
        System.out.println("alice-alpha-99=" +
                read(alice, "alpha", 99L));
        System.out.println("missing-tenant=" +
                read(alice, null, 1L));
        System.out.println("alpha-document-count=" +
                countWithinTenant("alpha"));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 TenantBoundaryDemo.java
java TenantBoundaryDemo
~~~

**Exact stdout:**

~~~text
alice-alpha-1=ALLOW:Budget A
alice-beta-2=DENY_OBJECT
bob-alpha-1=DENY_TENANT
bob-beta-1=NOT_FOUND
bob-beta-2=ALLOW:Budget B
viewer-alpha-1=DENY_ACTION
alice-alpha-99=NOT_FOUND
missing-tenant=DENY_TENANT
alpha-document-count=2
~~~

**Note:** The plain Java demo adds an owner policy, so Alice cannot read Bob's beta Document despite having beta membership. The Spring Boot demo in section 7 **only checks membership + authority** (no owner ACL) and will let Alice read the beta Document; the two demos explicitly have **different policy levels**, not contradictory outputs from the same implementation. In production, decide whether object-level ACLs are needed and keep the policy consistent across all paths.

## 12. Tenant must not be lost outside request processing

### 12.1. @Async and ThreadLocal

`SecurityContextHolder` in a Servlet application normally holds context on the executing thread. `@Async` switches executor threads and does not automatically transfer every state; if the app uses a custom `ThreadLocal`-based `TenantContextHolder`, treat this as an explicit boundary as well.

Do not use `MODE_INHERITABLETHREADLOCAL` with a thread pool as an automatic “patch”: reused threads can carry another caller's tenant. When needed, use controlled executor/context propagation—capture on submit, install in the worker, and **clear/restore in finally**. Even when context is propagated, the worker should re-verify tenant/membership and job validity against the current contract, especially for long-queued tasks.

### 12.2. Queue, scheduled job, and outbox

A message/job needs minimal metadata:

~~~json
{
  "jobType": "GENERATE_REPORT",
  "tenantId": "alpha",
  "requestedBy": "user-17",
  "resourceId": "project-20",
  "correlationId": "job-821"
}
~~~

This is server-generated job data produced after authorization, **not** a serialized raw `SecurityContext`. A worker in another process must verify the message publisher, ACTIVE tenant status, actor/service identity, and permitted action; never trust an arbitrary tenantId in a message arriving from a client or low-trust queue.

Scheduled batches running across multiple tenants need an explicit routing loop:
- Select tenants from a trusted registry.
- Bind resource scope/DB connection to **one tenant at a time**.
- Avoid using a global admin token for all queries when a least-privilege service identity can be used.
- At the end of each task, reset context/caches/connections.
- Audit tenant, actor/service identity, resource, outcome, and correlation ID.

### 12.3. Tenant offboarding in async jobs

If tenant alpha is suspended after a job is enqueued but before it executes, a stale snapshot does not guarantee permissions remain valid. Place a re-check before reading/writing sensitive data; queue retries/dead-letter handling must never fall back to a default tenant when the tenant ID is missing.

## 13. Caches, files, search, and observability are also tenant boundaries

### 13.1. Cache keys must include scope

Counterexample:

~~~java
@Cacheable("document")
public Document getDocument(Long id) { ... }
~~~

If IDs overlap across tenants or permissions depend on tenant, keying on `id` is insufficient. Conceptual key example:

~~~text
document:v2:tenant=alpha:id=101
document:v2:tenant=beta:id=101
~~~

When caching **authorization decision results**, you also need actor, permission/action, and an appropriate policy version or invalidation; never cache “allowed=true for document 101” and reuse it for Bob. In Spring Cache, design method signatures to accept an explicit **trustedTenantId** and key by tenant, rather than using a raw unverified path value as the sole identity.

### 13.2. File/object storage

File storage paths may include a tenant prefix:

~~~text
tenants/alpha/documents/101/report.pdf
tenants/beta/documents/201/report.pdf
~~~

However, a prefix **is not authorization by itself**. Verify the DB resource's tenant + ACL before issuing a presigned URL, configure IAM/storage ACLs by least privilege, keep URL lifetimes short, and prevent clients from choosing arbitrary object keys. Never accept a `fileKey` from a request and concatenate it into a path without checking tenant/ownership.

### 13.3. Search indexes and analytics

Queries against Elasticsearch/OpenSearch, search/vector stores, or analytics warehouses must filter by tenant inside the query or a supported security layer; never fetch the top 100 global results and drop wrong-tenant items in Java, because that can:
- Leak document IDs/titles via logs/metrics.
- Return counts/hit totals/timings that imply the existence of other tenants.
- Break pagination/recall.
- Leak data through highlights/embeddings/chunk metadata.

When using vector retrieval for RAG, every chunk/document must carry tenant scope and an authorization filter; do not rely on a prompt saying “only return tenant alpha data” as a guardrail.

### 13.4. Logs, traces, and audit

Audit events should record the trusted tenant ID, stable actor ID, object type+ID, action, decision, and correlation ID. Never log tokens, raw credentials, or sensitive document contents. In multi-tenant ops dashboards, the audit/search UI itself must enforce tenant scope, except for users with controlled investigative privileges.

Logs containing only `userId` without tenant make investigations unable to distinguish whether Alice read Document 101 in alpha or beta. However, do not log an unverified `requestedTenantId` as though it were the authenticated tenant; separate `requestedTenant` and `authorizedTenant` if forensic tracing is needed.

### 13.5. Webhooks and callbacks

Outbound webhook payloads must verify that the target subscription belongs to the tenant, that the URL is safely stored/approved, and that data is scoped. A “notify all tenants” endpoint must never reuse cache/output from a previous tenant; include tenant ID in events/outbox records and dedupe keys, and control replay/correlation.

## 14. Tenant scope in mutations and transactions

### 14.1. Reading before writing does not guarantee atomicity

An anti-pattern:

~~~java
Document doc = repository.findById(id).orElseThrow();
if (!doc.getTenantId().equals(tenant)) throw new AccessDeniedException(...);
doc.setTitle(newTitle);
repository.save(doc);
~~~

Between read and write, tenant/ownership could change or the actor's permission could be revoked. For high-risk mutations, use transactions, optimistic/pessimistic locking, or an UPDATE statement carrying both tenant and policy predicates:

~~~sql
UPDATE document
SET title = :newTitle,
    version = version + 1
WHERE tenant_id = :trustedTenant
  AND id = :documentId
  AND version = :expectedVersion;
~~~

Inspect the affected row count; 0 rows means either nonexistent in the tenant or a concurrent update. If owner/ACL is mandatory, protect it at the same access/write boundary or check under appropriate locking; do not rely solely on a controller check at t1.

### 14.2. Unique constraints and foreign keys must preserve tenant

A cross-tenant insert can occur from a CSV import flow or background task even if the REST controller is safe. Composite unique/FK constraints as in section 5 provide defense-in-depth. Across multiple tables, the proper join condition is:

~~~sql
SELECT d.id, c.content
FROM document d
JOIN document_comment c
  ON c.tenant_id = d.tenant_id
 AND c.document_id = d.id
WHERE d.tenant_id = :trustedTenant;
~~~

Never join solely on `document_id` when IDs are not globally unique or when business rules require the same tenant; that risks a cross-tenant join.

### 14.3. Tenant-aware events and outbox

An outbox event must record the tenant alongside the object/action, rather than reading the tenant from a thread-local when the consumer runs after commit. Both publisher and consumer must verify ACL/tenant at the appropriate point, ensuring an alpha message is never processed against a beta datasource/namespace.

### 14.4. Intentional cross-tenant authorization cases

Valid use cases exist, such as vendor support or sharing a resource across organizations:
- Design an **explicit sharing object** or delegation specifying provenance, source/target tenants, permissions, expiration, consent/approval, and auditing.
- Do not “cheat” by dropping `WHERE tenant_id=?` or granting a user multi-tenant membership to read the entire DB.
- If a record moves between tenants, treat it as a dedicated workflow checking both source and destination, transactional consistency, ACL migration, caches, and auditing.
- Never allow child resources or parent ACLs of another tenant to be referenced simply because a client sent an ID.

## 15. Common design mistakes

### Mistake 1 — Treating tenant as display metadata

`tenant_id` appears in JSON, yet queries by `id` omit the tenant predicate. Fix this at the repository/data layer and test cross-tenant lookups.

### Mistake 2 — Trusting URL/header tenant immediately

Client changes `/alpha/` to `/beta/`. If the server treats it as `trustedTenantId` without checking membership, a leak occurs. Verify that the user is a member, the tenant is ACTIVE, and the action policy permits it.

### Mistake 3 — Generic roles only, no tenant-scoped permission check

Alice is ADMIN of alpha but VIEWER of beta. `hasRole('ADMIN')` does not answer in which tenant. Use per-tenant role memberships, resource tenant, and action.

### Mistake 4 — Filtering only in the UI or controller

Hidden buttons or controller checks do not protect schedulers, exports, or repositories called from other code. Place enforcement in services and data access.

### Mistake 5 — Loading a global entity and rejecting after checking

`repository.findById(id)` across the whole DB can leak metadata, logs, and timing, and makes predicates easy to forget. Query `findByTenantIdAndId` and design consistent 404/403 behavior.

### Mistake 6 — Updating/deleting by id alone

`DELETE FROM document WHERE id=:id` or `UPDATE ... WHERE id=:id` can affect another tenant. Always include the trusted tenant, ACL/policy, and row count verification.

### Mistake 7 — Joins/FKs without tenant

A beta comment points to an alpha document, or a join mixes data. Design composite FKs/unique constraints and tenant-aware joins.

### Mistake 8 — “RLS is enabled so nobody can bypass it”

DB owners/superusers/BYPASSRLS can bypass it; runtime roles and transaction tenant settings can be misconfigured. Test with real DB credentials, appropriate `FORCE ROW LEVEL SECURITY`, and a non-bypassing role.

### Mistake 9 — Using session-level SET with a connection pool

An alpha request sets the tenant and returns the connection to the pool; beta reuses that connection. Choose transaction-local settings, cleanup, and reuse tests.

### Mistake 10 — Failing to clear tenant ThreadLocal

Servlet/executor threads retain the tenant from a previous task. Use scoped/finally blocks, explicit tenant parameters, or verified context propagation; avoid global static current tenant state.

### Mistake 11 — Cache keys missing tenant

The same document ID or authority snapshot is reused between alpha and beta. Scope cache keys and invalidation; never cache authorization decisions globally.

### Mistake 12 — Export/search omits predicates

The GET-by-ID API is safe, but export/analytics/search does not filter. Test all data-reading paths, including file storage and search indexes.

### Mistake 13 — Uncontrolled cross-tenant reparenting/moving

Changing a Document's tenant ID without updating ACLs, parents, FKs, search/cache, and object storage leads to broken permissions. Design a dedicated migration workflow with auditing and rollback/compensation.

### Mistake 14 — Returning 403 for cross-tenant but logging the real title

The server reads a beta Document and logs it before denying Alice; data still leaks into logs or traces. Scope queries and minimize data across every layer.

### Mistake 15 — Trusting a JWT tenant claim without verifying signature/issuer

Unverified claim data or an `iss` outside the trusted issuers list can be forged. Use proper JWT validation, `aud`/expiry checks, and membership policies.

### Mistake 16 — Inactive tenants still running queued jobs

HTTP has locked the tenant, yet jobs from an older queue still run. Verify tenant status and identity in the worker rather than relying indefinitely on context snapshots.

### Mistake 17 — Uncontrolled internal admin bypass

A support endpoint has `permitAll` or an omnipotent admin token without reason, tenant selection, and audit. Use scoping, approval/break-glass workflows, and monitoring.

### Mistake 18 — Confusing 404 with global nonexistence

A scoped query cannot find Document ID 101 in beta; it may exist in alpha. Do not run a global query to “explain the 404” to the client; return a consistent response without revealing cross-tenant existence.

## 16. QA and safe performance testing matrix

| Test case | Expected outcome |
| --- | --- |
| Alice authenticated, alpha member, alpha Document, READ permission | Allowed if object policy also agrees |
| Alice authenticated, beta has no membership | DENY tenant |
| Bob beta member, queries alpha ID via beta | 404/no data; no leak of real owner/title/tenant |
| User missing feature authority in valid tenant | DENY action |
| Alice editor in alpha, viewer in beta | WRITE in alpha allowed, WRITE in beta blocked |
| Requested tenant null, unknown, suspended | Fail closed |
| Resource.tenantId null or wrong type | Excluded/access denied, controlled data repair |
| Client attempts to POST different tenantId/ownerId | Server ignores/rejects, no cross-tenant insert |
| List/search/export/bulk APIs | Every row belongs to the verified tenant |
| UPDATE/DELETE with another tenant's id | 0 rows, no data modified |
| Composite FK comment/doc across tenants | DB rejects |
| User with multiple memberships | Tenant switching changes only after separate permission check |
| Approved cross-tenant share | Only explicitly delegated resource/action/expiration |
| Role/tenant status changes | Cache and tokens follow freshness policy, revocation takes effect properly |
| Cache key missing tenant (mutation test) | Suite must detect contamination |
| Async worker reuse | Previous user's tenant is not retained after task |
| DB connection pool reuse | SET LOCAL/transaction setting does not leak alpha→beta |
| RLS policy missing, runtime app role | Default deny and no BYPASSRLS per design |
| SQL injection/arbitrary operations | Cannot alter trusted tenant context or read out of scope |
| File download/presigned URL | Only URLs for objects in authorized tenant |
| Search/vector index | Tenant filter before retrieval, no leak of highlights/counts |
| Audit log | Actor + trusted tenant + resource + action, no tokens |
| Monitoring | 403/404 probing and access anomalies detected |
| Concurrency | Tenant reassignment/role revocation causes no TOCTOU leak |
| Backup/restore/offboarding | No mixing/wrong-tenant restore, proper retention |

### 16.1. Negative testing matters more than happy paths alone

A suite that only tests Alice reading an alpha Document **does not test the tenant boundary**. You must deliberately test:
- A beta user with a valid alpha ID.
- An alpha user with a valid beta ID.
- A multi-tenant user's token with a lower role in the currently selected tenant.
- A tenant suspended after token issuance.
- Cross-tenant comment→document relationships and arbitrary file storage keys.
- Cache warmed in alpha first, followed by a beta request with the same ID.
- Connection pool usage in alpha→beta→alpha order.
- An alpha async job failing midway before the worker picks up a beta job.

Ensure these tests run in CI, especially after adding new repositories, native queries, caches, or migrations.

## 17. Self-check exercises

**Question 1 — Is having the document:read authority enough?**

Alice has `document:read` and is a member of alpha. When Alice sends `/api/tenants/beta/documents/201`, should she be allowed to view it?

**Answer:** No, if Alice lacks membership/permission in beta. Feature authority does not replace tenant and resource conditions.

**Question 2 — Can modifying the URL tenant grant access?**

Bob belongs only to beta and changes `X-Tenant-ID` or the path to alpha. Should the server use alpha as the trusted tenant context?

**Answer:** No. Tenant selectors are untrusted; membership must be looked up in a server-side source, along with tenant status and scoped actions.

**Question 3 — With RLS enabled, does code still need membership checks?**

RLS uses `tenant_id = current_setting('app.tenant_id', true)`. A controller takes a client header and calls `set_config` without checking membership. Is that secure enough?

**Answer:** No. RLS is using an untrusted context; an attacker can pick another tenant. The app must verify first and use an appropriate DB role/transaction.

**Question 4 — Bob is a beta member requesting GET beta/101, where 101 belongs to alpha in the DB. What should be returned?**

**Answer:** The query `WHERE tenant_id='beta' AND id=101` finds nothing and typically returns 404; never return alpha's metadata. The HTTP contract may choose another code, but must not disclose cross-tenant resources.

**Question 5 — Does tenant scope replace ACLs?**

Alice and Carol are both members of alpha. Document 101 is shared only with Alice. Can Carol read it simply by being an alpha member?

**Answer:** No, if the policy requires object ACL/ownership. Tenant scope is a necessary condition, not automatic access to every object.

**Question 6 — Why are composite foreign keys important?**

A comment has `tenant_id='beta'` and `document_id=101`, while Document 101 belongs to alpha. Can a FK on `document_id` alone succeed?

**Answer:** It can succeed if the ID exists and the FK only references ID. A composite FK `(tenant_id,document_id)` to `(tenant_id,id)` prevents cross-tenant links when keys/constraints are declared consistently.

**Question 7 — An async worker processing beta sees tenant alpha; what bug is this?**

**Answer:** Context leakage across threads/tasks or misrouting. Capture/validate the tenant per task, install the proper scope, clean up in finally, and inspect connection caches and downstream clients as well.

**Question 8 — Is querying 100 global DB results and filtering in Java acceptable?**

**Answer:** Unsuitable as a boundary. It can leak data via logs/counts/highlights, break pagination, and miss/over-fetch results. Scope queries at the data source/search index.

## 18. Architecture summary

A secure multi-tenant application requires **an unbroken verification chain**:

~~~text
Verified principal
  -> verified membership and active tenant
  -> action authorization for that tenant
  -> tenant-scoped resource lookup and data integrity constraints
  -> object ACL/business-state policy
  -> correctly scoped response, cache, file, search and event
  -> audit with trusted tenant context
~~~

Tenant is **not** merely a UI filter, route prefix, claim, or session variable. It is a data and policy scope enforced consistently across **every** execution path, including background jobs and non-HTTP components. If one layer fails, the other layers (repository predicates, composite keys, DB RLS, storage IAM, audit) must contain the blast radius rather than trusting the same spoofed input.

**Check question for every API:** “If I swap the principal for a user in tenant B while keeping the resource ID from tenant A, can this API return a single byte of A's data, modify a row of A, or create a link to A?” If the answer could be yes, the tenant boundary is not adequately protected.

## Official references

- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request authorization, authentication supplier, `AuthorizationManager`, and DSL.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, Spring proxies, and method interception.
- [Spring Security – Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): resolving issuers/tenants via trusted issuers, `JwtIssuerAuthenticationManagerResolver`, and trade-offs.
- [Spring Security – Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): HTTP security integration tests, `httpBasic`, and `csrf` post-processors.
- [PostgreSQL – Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, `USING`/`WITH CHECK`, and role bypass.
- [PostgreSQL – Configuration Functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADMIN-SET): `current_setting` and `set_config`, including local transaction settings.
- [Spring Framework – Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy/transaction boundaries, concurrency boundaries, and data integrity.
