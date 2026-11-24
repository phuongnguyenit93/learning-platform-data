# Isolating Data Between Two Tenants and Testing Identity Switching

## 1. Objectives and Practice Scenario

In a SaaS application using Spring Security, **successful authentication does not mean the caller may access all data**. A user in tenant A may hold valid `ROLE_ADMIN` or `SCOPE_documents.read` and still **must not read tenant B's documents**. Object-level access flaws (Broken Object Level Authorization/IDOR) often appear when code checks only that a user is logged in, checks only functional roles/scopes, or uses `tenantId` from a URL/header/body without verifying it belongs to the current principal's scope.

This practice creates two tenants with colliding document IDs, switches caller identities and tenant selections, and tests both valid paths and deliberate boundary violations. The hard part is verifying **which entity was accessed and what changed in the database**, not just HTTP status codes. Safe behavior must hold when `Authentication` switches from Alice to Bob, when a multi-tenant user selects another tenant, when membership is revoked, and when threads/sessions/caches are reused.

**Target outcomes:**

1. Build a **two-tenant A/B** fixture sharing the same local document ID with distinct contents to expose missing tenant predicates.
2. Distinguish **authenticated identity (issuer + subject)**, **selected tenant**, **membership/role in the tenant**, and **resource permission**.
3. Write routes, services, and repositories that use only a **verified** tenant context, never treating a client-declared tenant directly as authority.
4. Test **identity switching**: swapping access tokens/principals across requests, switching to valid and invalid tenants, changing membership after login, and logging out/back in.
5. Cover read, write, delete, list, search, bulk/export, parent-child relations, caches, and background jobs to prevent secondary leaks.
6. Establish an allow/deny matrix, positive controls, before-and-after DB state checks, and boundary tests at JWT, MVC, service, and repository layers.

**Scope:** examples apply to Spring Boot 3+ / Spring Security 6.x/7.x on the Servlet stack; tenant-isolation concepts are version-independent. The Spring snippets are integration fragments requiring real application beans/repositories. The standalone Java 17 program in section 10 runs without Spring to verify invariant logic.

## 2. Setting Up the Two-Tenant Model

A tenant is a data and policy boundary. In a shared-database model, which tenant each record belongs to must be reliably determined; a tenant is not necessarily synonymous with a user, organization, or subdomain. A user can belong to multiple tenants, hold different roles in each tenant, or temporarily lose membership.

| Entity | Tenant A | Tenant B |
| --- | --- | --- |
| Regular user | `alice` is a member of A | `bob` is a member of B |
| Member of both | `casey` is a member of A | `casey` is also a member of B |
| Tenant-scoped admin | `admin-a` has `TENANT_ADMIN` **in A** | Holds no role in B |
| Document with colliding local ID | `D-7`: `"alpha-secret"`, owner Alice | `D-7`: `"bravo-secret"`, owner Bob |
| Other documents | `A-9` | `B-9` |
| Related project | `P-1` in A | `P-1` in B, same ID but distinct record |

Choosing the same code `D-7` in both tenants is **intentional**: if a repository calls `findById("D-7")` without scoping by tenant, tests may accidentally read or mutate the wrong record. Global UUIDs still require authorization, yet colliding local IDs expose bugs faster.

Assumed functional permissions:

- `documents.read`: permitted to attempt reading/listing/searching documents within the tenant on objects the caller has rights to.
- `documents.write`: permitted to attempt creating/editing valid documents within the tenant.
- `documents.delete`: permitted to attempt deleting valid documents within the tenant.
- `documents.export`: permitted to attempt exporting authorized documents, not all system-wide data.
- `TENANT_ADMIN`: administrative role **only within the assigned tenant**, not a global `SUPER_ADMIN`.
- Shared document recipients may view via ACL; membership **alone may be insufficient** if the system further restricts by owner/team/project.

Minimal authorization decision definition:

~~~text
ALLOW(actor, action, requestedTenant, resource)
  = authenticatedAndTrusted(actor)
  AND hasFunctionalPermission(actor, action)
  AND activeMembership(actor, requestedTenant, action)
  AND resource.tenantId == requestedTenant
  AND objectPolicyAllows(actor, action, resource)
~~~

For `CREATE` before a resource exists, replace the resource check with the verified parent/container tenant and validate all input references. For cross-tenant system operations, define a dedicated service principal and scope rather than bypassing the conditions above.

## 3. Execution Identity Is Not the Selected Tenant

### 3.1. Authentication: Who Is Calling?

In a JWT resource server, identity should have a contractually stable key, such as `(issuer, sub)`: the same `sub=alice` issued by two different issuers does **not automatically** mean the same internal user. Spring Security must validate token signature, expiration, issuer, and **this API's audience** per configuration; a decoded JWT string or client-sent `X-User-Id` is not valid authentication.

`JwtAuthenticationToken#getName()` defaults to `sub`, though a custom `JwtAuthenticationConverter` may pick another name claim. When implementing, decide the `PrincipalRef` source explicitly and uniformly (issuer + stable subject/internal user ID), rather than relying on email/display name since those can change or collide.

Example JSON token showing **illustrative claims** (not a real signed JWT):

~~~json
{
  "iss": "https://login.example.test",
  "aud": ["documents-api"],
  "sub": "alice",
  "scope": "documents.read documents.write",
  "tenant_id": "A"
}
~~~

When a token is validly signed, a `tenant_id=A` claim can represent a default tenant **if the issuer contract defines it that way**. Yet a valid claim does not always reflect live membership after revocation; depending on risk, services must re-check server-side membership, token expiry/refresh/revocation, or permission versions.

### 3.2. Tenant Selection: Which Scope Are We Operating In?

A tenant can be selected via `/api/tenants/{tenantId}/...`, subdomain, or `X-Tenant-Id`. All of these are merely **selectors**, never proof that the user belongs to that tenant. Standard verification sequence:

1. Extract the actor from the framework-verified `Authentication`/JWT.
2. Read `requestedTenant` from the URL/header or application selection.
3. Look up the actor's **active membership/role/permissions** on that exact selected tenant.
4. Construct `VerifiedTenantContext(actorId, tenantId, allowedActions)` on the server; the context must never be client-constructed or hold unverified permissions.
5. Use the verified `tenantId` in **every query**, cache key, file path, data relationship, and job.
6. When switching tenants, re-check membership; never retain context A from a previous request and apply it to request B.

If Casey belongs to A and B, switching from A to B **can succeed** after checking membership. If Alice belongs only to A, changing `X-Tenant-Id` from A to B does **not** make her a member of B. If Alice holds `ROLE_TENANT_ADMIN` in A, that role grants zero permissions in B.

### 3.3. What Does Testing “Identity Switching” Mean?

There are **at least three distinct change axes** to separate:

| Axis | Example | Correct Decision |
| --- | --- | --- |
| **Switch principal** | Request 1 Alice's token, request 2 Bob's token | Request 2 has only Bob's permissions; no sticky Alice principal/tenant |
| **Same principal, switch tenant** | Casey A to B; Alice tries A to B | Casey switches per B membership; Alice is denied |
| **Identity/relationship changes over time** | Alice locked; Casey loses B membership; email changes | Permissions update per policy, never relying indefinitely on stale data/cached authorities |

Another attack vector is modifying `sub` or `tenant_id` in a JWT to impersonate someone. With signed tokens, tampering with the payload without re-signing with the issuer's key must be rejected by the authentication layer (typically 401). MockMvc tests using `jwt()` with `sub=bob` only **simulate a request from Bob**; they do not prove an attacker forged Alice's token.

## 4. Threat Model: Cross-Tenant Data Leak Points

### 4.1. Direct Document Read by ID (IDOR/BOLA)

Wrong:

~~~java
// Wrong: the same local ID can exist in two tenants.
Document doc = repository.findById(documentId).orElseThrow();
return mapper.toDto(doc);
~~~

Right in a shared-table model:

~~~java
Document doc = repository
    .findByTenantIdAndDocumentId(verifiedTenant, documentId)
    .orElseThrow(NotFoundException::new);
policy.requireCanRead(verifiedActor, doc);
return mapper.toDto(doc);
~~~

`verifiedTenant` is bound from verified identity/membership, not by reading `request.getHeader("X-Tenant-Id")` directly and skipping verification. If the repository uses a composite primary key `(tenantId, documentId)`, lookups must pass both components.

### 4.2. Checking Only `hasRole`/`hasAuthority` and Forgetting Object Policy

~~~java
// Wrong if ROLE_ADMIN is only a tenant-scoped admin role.
@PreAuthorize("hasRole('ADMIN')")
public Document read(String documentId) {
    return repository.findById(documentId).orElseThrow();
}
~~~

An actor with an admin role in A can access B's record if there is no tenant predicate. Combine functional authority, tenant membership, and object-level authorization. If a global `ROLE_ADMIN` exists, it must have an explicit contract/capability, auditing, and dedicated tests.

### 4.3. Unscoped Lists and Searches

`GET /documents?tenant=B`, full-text search, autocomplete, counts, pagination, sorting, and facets can all leak document counts or filenames even when single-document GET is protected. Queries must push the tenant predicate **into the DB/search backend**, rather than fetching everything and filtering in Java afterward. Apply this to `SELECT COUNT(*)`, exports, result caches, and joins.

### 4.4. Cross-Tenant Writes/Moves via DTOs

Client sends body:

~~~json
{
  "title": "updated",
  "tenantId": "B",
  "ownerId": "bob",
  "projectId": "P-1"
}
~~~

If the backend auto-maps JSON onto entities via setters and calls `save(entity)`, Alice could try changing tenant/owner or linking B's project P-1. Design DTOs exposing only editable fields; keep tenant immutable or changeable only via a **transfer workflow** checking permissions at both source and target; validate target tenant on all foreign keys to projects/customers/invoices.

### 4.5. Repositories/Caches/Storage/Jobs Ignoring Tenant

A cache key `document:D-7` is insufficient when IDs collide; use `tenant:A:document:D-7` or keys including tenant + principal/action/version when responses depend on user permissions. File `exports/J-100.csv` must not be downloadable merely because a client knows `jobId`; verify owner/tenant on download. A queue message carrying `tenantId=B` does not prove the runner has B rights; re-establish policy in the consumer.

### 4.6. Thread/Session Switches Principal Yet Old Context Persists

If a singleton bean stores `currentUser` in a field, a thread pool fails to clear `SecurityContextHolder`, or a mutable `TenantContext` `ThreadLocal` is not cleared in `finally`, Bob's request might accidentally run under tenant A/identity Alice. Spring Security's filter chain normally manages per-request context, yet custom filters/caches/async code must still guarantee lifecycle cleanup. Test **A→B→A sequence** on the same pool and after exceptions, not just A and B in isolated tests.

## 5. Layered Control Architecture

~~~mermaid
flowchart TD
  A[HTTP: token + tenant selector + resource ID] --> B[Spring Security: validate JWT, issuer, audience]
  B --> C{Authenticated?}
  C -->|No| X[401 or equivalent authentication error]
  C -->|Yes| D[PrincipalRef: issuer + stable subject]
  D --> E[Check functional scope/role]
  E --> F{Is actor a member of selected tenant?}
  F -->|No| Y[403 or 404 consistent with policy]
  F -->|Yes| G[VerifiedTenantContext]
  G --> H[Service checks object action/ACL]
  H --> I[Repository query with tenant predicate]
  I --> J{Record in tenant and allowed by policy?}
  J -->|No| Z[403/404, no side effects]
  J -->|Yes| K[Return data or tenant-scoped write transaction]
~~~

Protection layers:

- **SecurityFilterChain**: ensures API requests are authenticated and enforce functional policies; routes never fall into `permitAll` due to mis-matched patterns.
- **Method security**: `@PreAuthorize` checks functional authority and can invoke parameter-based policy beans. Enable `@EnableMethodSecurity`. Calls must traverse the Spring proxy, avoiding self-invocation bypasses.
- **Tenant membership service**: confirms actor, tenant, and active permissions from a trusted source; tenant-scoped roles are never promoted to global roles.
- **Domain/object policy**: ownership, ACLs, document state, project membership, and action. Client-chosen inputs never replace the source of truth.
- **Persistence/DB**: queries require tenant scoping; optionally add composite keys, tenant-scoped foreign keys, RLS, or schema/DB separation for defense in depth.
- **Output layers**: responses, caches, events, search indexes, exports, object storage, and logs all preserve the tenant boundary.

No single annotation guarantees every layer. In particular, `@PreAuthorize("hasAuthority('SCOPE_documents.read')")` only confirms the scope exists in `Authentication`; it **does not** verify whether the user belongs to A/B or which tenant owns the record.

## 6. Spring Security: Design Patterns to Test Directly

The snippets below are **Spring Security Servlet Java integration fragments**, not a standalone compilable project. You need real `JwtDecoder`, `IdentityResolver`, `TenantMembershipService`, `DocumentRepository`, `DocumentPolicy`, and DTO/controller implementations. Examples use `@AuthenticationPrincipal Jwt` for a JWT resource server; if using sessions/OIDC, swap the identity resolver while preserving all invariants.

### 6.1. Protecting the Request Entrypoint

~~~java
@Configuration
@EnableMethodSecurity
class DocumentSecurityConfig {
    @Bean
    SecurityFilterChain documentsSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/tenants/**").authenticated()
            .anyRequest().denyAll()
        ).oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        );
        return http.build();
    }
}
~~~

Add imports for `@Configuration`, `@EnableMethodSecurity`, `@Bean`, `SecurityFilterChain`, `HttpSecurity`, and `Customizer`. Applications must configure an appropriate JWT decoder and `issuer`/`audience` validators. Configure CSRF according to authentication type: bearer-token APIs without cookies/sessions have a different threat model than cookie auth; **never disable CSRF system-wide just to make POST tests easier**. `authenticated()` is only the outer gate; services underneath must enforce tenant/action/object checks. For all other routes, `denyAll` is a cautious default in this example.

### 6.2. Controller: Tenant Path Is a Request, Not a Permission

~~~java
@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
class DocumentController {
    private final DocumentService documents;

    DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/{documentId}")
    DocumentView get(@AuthenticationPrincipal Jwt jwt,
                     @PathVariable String tenantId,
                     @PathVariable String documentId) {
        return documents.read(jwt, tenantId, documentId);
    }

    @PatchMapping("/{documentId}")
    DocumentView rename(@AuthenticationPrincipal Jwt jwt,
                        @PathVariable String tenantId,
                        @PathVariable String documentId,
                        @RequestBody RenameDocument request) {
        return documents.rename(jwt, tenantId, documentId, request.title());
    }
}

record RenameDocument(String title) {}
~~~

The controller **never** accepts arbitrary `requestedBy`, `role`, `ownerId`, or `tenantId` from the JSON body as authority. URL `tenantId` is a selector; entering B requires passing membership/policy. `@AuthenticationPrincipal Jwt` is available only after valid JWT authentication in the pipeline.

### 6.3. Service: Actor and Tenant Checked Before Lookup

~~~java
@Service
class DocumentService {
    private final IdentityResolver identities;
    private final TenantMembershipService memberships;
    private final DocumentRepository repository;
    private final DocumentPolicy policy;

    DocumentService(IdentityResolver identities,
                    TenantMembershipService memberships,
                    DocumentRepository repository,
                    DocumentPolicy policy) {
        this.identities = identities;
        this.memberships = memberships;
        this.repository = repository;
        this.policy = policy;
    }

    @Transactional(readOnly = true)
    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    public DocumentView read(Jwt verifiedJwt, String tenantId, String id) {
        PrincipalRef actor = identities.fromVerifiedJwt(verifiedJwt);
        memberships.requireActive(actor, tenantId, "documents.read");

        Document doc = repository.findByTenantIdAndDocumentId(tenantId, id)
            .orElseThrow(NotFoundException::new);

        policy.requireCanRead(actor, tenantId, doc);
        return DocumentView.from(doc);
    }

    @Transactional
    @PreAuthorize("hasAuthority('SCOPE_documents.write')")
    public DocumentView rename(Jwt verifiedJwt, String tenantId,
                               String id, String newTitle) {
        PrincipalRef actor = identities.fromVerifiedJwt(verifiedJwt);
        memberships.requireActive(actor, tenantId, "documents.write");

        Document doc = repository.findByTenantIdAndDocumentId(tenantId, id)
            .orElseThrow(NotFoundException::new);
        policy.requireCanRename(actor, tenantId, doc);

        doc.renameTitle(newTitle); // Do not allow changing tenantId via request.
        return DocumentView.from(doc);
    }
}
~~~

This is a **business skeleton**; `PrincipalRef`, `IdentityResolver`, `TenantMembershipService`, `DocumentPolicy`, `DocumentView`, and `NotFoundException` must be implemented per project. `Document#renameTitle` must validate input inside the transaction; JPA dirty checking persists changes if the entity is managed. `identities.fromVerifiedJwt` accepts only pipeline-verified JWTs; never forge raw unsigned tokens in tests and call production services directly.

**Important note:** `@PreAuthorize` evaluates the current `Authentication` from `SecurityContext`, not trusting `verifiedJwt` merely because it was passed as an argument. If a collaborator calls the method through the bean proxy under another principal, controllers/services must keep identity consistent; integration tests must test the real behavior. Never call `this.rename(...)` when expecting AOP method security to run.

To mitigate TOCTOU when membership/ownership changes concurrently with writes, sensitive projects can use `UPDATE ... WHERE tenant_id = ... AND ...` queries with version/ACL predicates, proper locks, DB RLS, and affected-row verification. You cannot check membership once before a long transaction and assume permissions stay valid forever.

### 6.4. Repository and Database Constraints

Shared-table example with per-tenant local IDs:

~~~sql
CREATE TABLE tenant_documents (
    tenant_id   VARCHAR(80) NOT NULL,
    document_id VARCHAR(80) NOT NULL,
    owner_id    VARCHAR(120) NOT NULL,
    project_id  VARCHAR(80),
    title       VARCHAR(255) NOT NULL,
    version     BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, document_id)
);

CREATE INDEX idx_tenant_documents_owner
    ON tenant_documents (tenant_id, owner_id);
~~~

The composite key prevents overwriting another tenant's record with the same `document_id`. If the `projects` table is also keyed by `(tenant_id, project_id)`, a composite foreign key helps prevent linking tenant A's document to tenant B's project:

~~~sql
-- Assumes projects has PRIMARY KEY (tenant_id, project_id).
ALTER TABLE tenant_documents
ADD CONSTRAINT fk_tenant_documents_project
FOREIGN KEY (tenant_id, project_id)
REFERENCES projects (tenant_id, project_id);
~~~

If the database uses global surrogate UUIDs, tenant predicates and composite indexes/constraints are still required for every tenant-scoped relation; UUID uniqueness does **not** replace authorization.

Scoped query:

~~~sql
SELECT d.tenant_id, d.document_id, d.title, d.owner_id
FROM tenant_documents AS d
WHERE d.tenant_id = :authorizedTenant
  AND d.document_id = :documentId;
~~~

Write constrained concurrently by tenant and version:

~~~sql
UPDATE tenant_documents
SET title = :newTitle, version = version + 1
WHERE tenant_id = :authorizedTenant
  AND document_id = :documentId
  AND version = :expectedVersion;
~~~

Verify updated row count equals `1` before reporting success; `0` may mean nonexistent, wrong tenant, or version conflict, handled per error contract. Even with the tenant predicate in SQL, `:authorizedTenant` must come from a **verified** membership/policy context. For owner-only editing, queries/updates must also enforce actual owner/ACL predicates per design.

### 6.5. PostgreSQL Row Level Security and DB Separation

Three common patterns exist: separate DBs, separate schemas, and shared tables with `tenant_id`. None is automatically safe if the app runs with overly broad DB privileges. With PostgreSQL RLS, a conceptual policy example:

~~~sql
ALTER TABLE tenant_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON tenant_documents
USING (
    tenant_id = current_setting('app.current_tenant', true)
)
WITH CHECK (
    tenant_id = current_setting('app.current_tenant', true)
);
~~~

This setup requires the application to set `app.current_tenant` **after** verifying identity/membership, inside an appropriate transaction. With connection pooling, **prefer transaction-local settings** (such as `SET LOCAL` or `set_config(..., true)` inside a transaction) so context never bleeds into the next connection borrow. Ensure the request DB role is neither superuser nor granted `BYPASSRLS`; table owners can bypass RLS unless `FORCE ROW LEVEL SECURITY` is set. Test policies individually for `SELECT/INSERT/UPDATE/DELETE` across all tenant-owned tables. RLS is defense in depth, not a replacement for HTTP/service authorization.

## 7. Two-Tenant Integration Test Matrix

Standardize fixture baselines and contract statuses: unauthenticated or invalid tokens typically return `401`; authenticated users lacking authority/membership typically return `403`; many APIs return `404` for out-of-scope resources to hide existence. **Pick one consistent approach** and assert it; never mix `403` and `404` based on tenant ID in a way that lets attackers infer resource existence.

| ID | Principal / Membership | Request or Operation | Expectation | DB Effect |
| --- | --- | --- | --- | --- |
| T01 | Alice → A | `GET /tenants/A/documents/D-7` | 200, body `alpha-secret` | Unchanged |
| T02 | Bob → B | `GET /tenants/B/documents/D-7` | 200, body `bravo-secret` | Unchanged |
| T03 | Alice → A | `GET /tenants/B/documents/D-7` | Deny (403/404 per contract) | No B leaked |
| T04 | Bob → B | `GET /tenants/A/documents/D-7` | Deny | No A leaked |
| T05 | Alice, admin role in A | Delete or list B documents | Deny | B unchanged |
| T06 | Casey → A and B | Select A, then B | 200 with corresponding data | No mixed cache/context |
| T07 | Casey's B membership revoked | Select B with old token | Deny per revocation policy | No B leaked |
| T08 | Alice has read, lacks write | PATCH/DELETE in A | Deny | A unchanged |
| T09 | Alice has write in A | PATCH A document with body `tenantId=B` | Tenant unchanged; field rejected or ignored per contract | B unchanged |
| T10 | Alice has write in A | POST A referencing `projectId=P-1` belonging only to B | Deny / validation error | No cross-tenant link created |
| T11 | Alice → A | `GET /tenants/A/documents`, search, count, export | Returns only permitted A records | No B metadata leaked |
| T12 | Request 1 Alice, request 2 Bob | Same pool / session after identity switch | Request 2 sees only Bob's data | No leftover tenant A |
| T13 | Tampered JWT `sub`/`tenant_id` with invalid signature | Call API | 401 at authentication | No data queried |
| T14 | Valid signature yet wrong issuer/audience | Call API | 401 per validation contract | No data queried |
| T15 | User knows B's object ID / B download URL | GET, bulk, download | Deny | No side effects |
| T16 | Tenant B shares `D-7` with A | Update/Delete A `D-7` | Only A's record changes | B `D-7` intact |

If B uses different IDs from A, an unscoped `findById` repository might still pass every test. Therefore **colliding local IDs** in fixtures are essential; also include IDs unique to B to catch enumeration/IDOR.

## 8. MockMvc Tests: Switching Principal Per Request

Spring Security Test provides `jwt()` for request authorization tests with a JWT principal. It creates a mock `Jwt` and `Authentication` without signing real tokens. The test below assumes the project already has `GET /api/tenants/{tenantId}/documents/{documentId}`, membership fixtures/beans, and the controller from section 6.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TwoTenantHttpIsolationTest {
    @Autowired MockMvc mvc;

    @Test
    void switchingIdentityMustNotLeakOtherTenant() throws Exception {
        mvc.perform(get("/api/tenants/A/documents/D-7")
                .with(jwt().jwt(j -> j
                    .subject("alice").claim("scope", "documents.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("A"));

        mvc.perform(get("/api/tenants/B/documents/D-7")
                .with(jwt().jwt(j -> j
                    .subject("alice").claim("scope", "documents.read"))))
            .andExpect(status().isForbidden());

        // Next request has a different principal, not reusing Alice's old context.
        mvc.perform(get("/api/tenants/B/documents/D-7")
                .with(jwt().jwt(j -> j
                    .subject("bob").claim("scope", "documents.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("B"));

        mvc.perform(get("/api/tenants/A/documents/D-7")
                .with(jwt().jwt(j -> j
                    .subject("bob").claim("scope", "documents.read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

This is an **integration test skeleton**, not a standalone compilable class. Key imports include JUnit `@Test`; Spring Boot Test `@SpringBootTest` and `@AutoConfigureMockMvc`; Spring `@Autowired`/`MockMvc`; static `get`, `jwt`, `status`, `jsonPath`. The test assumes unauthorized membership returns **403** and JSON contains `tenantId`. If the app intentionally returns 404 out of scope, update assertions per contract and still assert no B data leaks.

**Limitations of `jwt()`:** it injects a mock `JwtAuthenticationToken` to test authorization. It can exercise test support's claim/authority handling yet **does not verify signature, issuer, or audience via the production `JwtDecoder`**; moreover, using `.authorities(...)` directly sets authorities and can bypass custom runtime converters. Test token validators and converters separately (or use signed JWT fixtures + a test decoder) to verify the real authentication pipeline works.

### Avoiding Confusing “Mock Token Switching” with “Successful Spoofing”

Above, a request with `sub=bob` in `jwt()` means **Bob is already authenticated** in the test. It **does not mean** Alice can send a body `{"sub":"bob"}` or tamper with a signed token to become Bob. Write two categories of tests:

- **Legitimate identity switching:** real Bob logs in / receives Bob's token; subsequent requests evaluate as Bob.
- **Forgery/spoofing:** client sends `X-User-Id:bob`, tampers with JWT payload breaking signature, adds JSON field `owner=bob`, or sends a wrong-audience token; backend rejects or ignores all untrusted values.

If the application uses session cookies instead of JWT, test logout/re-login with session rotation and context replacement; the old session must never retain a signed-out principal. In stateless apps, never use a singleton `currentTenant` field or an un-cleared `ThreadLocal` to cache the prior request's tenant.

## 9. Unit/Integration/E2E: Required Assertions

### 9.1. Unit Testing Tenant Policy

Separate `hasMembership(actor, tenant)`, `hasScope(actor, action)`, and `objectPolicy(actor, doc)` into independently testable decisions. Mandatory cases: no membership, inactive membership, role in A absent in B, disabled user, owner in B, nonexistent document, token missing permission, and Casey allowed to select B yet lacking rights on Bob's personal record if not granted by ACL.

Never mock `membershipService.requireActive(...)` to always succeed inside the very test called “tenant isolation”; doing so bypasses the exact component under proof. Use a fake repository with an explicit dataset for unit tests, then integration tests with a real database to verify query scoping.

### 9.2. Integration Testing Against a Real Database

- Seed A `D-7` and B `D-7` with distinct contents, plus A-9/B-9 to catch broken filters.
- Before each test, snapshot the DB or use intentional transaction rollback; prevent one test's mutations from making subsequent tests order-dependent.
- For Alice patching A, assert only `tenant=A,id=D-7` changes; `tenant=B,id=D-7` retains title/version/owner/ACL.
- For unauthorized DELETE, assert **row count, soft-delete flag, audit/event/outbox** remain unchanged; a bare 403 response is insufficient.
- Search/filter/count/export/bulk must return **tenant A's exact ID set** or ACL-permitted documents; never check only `results.size()`, because A and B datasets may have the same size.
- For joins like `tenant_documents.project_id`, seed `P-1` in both A and B and verify foreign keys/tenant predicates; missing them can join into B's project.
- Use a database truly matching production (e.g., PostgreSQL when relying on RLS); H2 cannot prove PostgreSQL RLS policies.

### 9.3. Testing Identity Switching in the Same Session/Pool

A test should run sequentially, not just as two isolated tests:

~~~text
1. Alice (A) reads A/D-7 -> alpha-secret
2. Alice tries selecting B -> DENY
3. Bob (B) reads B/D-7 -> bravo-secret
4. Bob tries selecting A -> DENY
5. Casey selects A -> alpha-secret
6. Casey selects B -> bravo-secret
7. Revoke Casey's B membership; Casey selects B -> DENY
8. Re-grant B membership (via server flow); Casey selects B -> bravo-secret
9. Alice still in A, switch token/log in as Bob; next request -> only Bob's data
~~~

To test thread pooling and `ThreadLocal` tenant context, use a real executor with few workers to force thread reuse, run A→B→A, and run a task throwing an exception mid-flight; assert tenant/Authentication are set and restored/cleared at the right lifecycle points. Use `CountDownLatch`/`Future.get(timeout)` for deterministic tests rather than `Thread.sleep`. Spring Security manages context per request by default, while custom `TenantContextHolder` or async handoffs must be tested separately.

### 9.4. Testing Tokens and Identity Sources

- Generate real bearer tokens signed by a test issuer/JWK valid for the API; test `iss`, `aud`, `exp`, signature, and `sub`. Test bad signatures/audiences and assert 401.
- Check the JWT claim mapper: `scope` normally yields `SCOPE_...`, never turning `tenantId` automatically into a global role. Role in A and role in B must be distinguished via server-side data when using per-tenant roles.
- For old tokens after membership revocation, define whether the system revalidates immediately or within an approved TTL/token lifetime; test per concrete requirement instead of assuming every signed JWT has instant revocation checks.
- If a user changes email while `issuer+sub` stays unchanged, do not erroneously drop permissions; if two issuers issue the same `sub`, never merge them into one principal without explicit federation mapping.

### 9.5. Testing Side Channels, Caches, Async, and File Downloads

Even when detail GET is blocked, cross-tenant leaks can occur via:

- `GET /documents/count` and search suggestions; filenames, totals, first/last pages, `ETag`, lastModified, error messages.
- `@Cacheable(key = "#documentId")` missing tenant causes A/B to share cached records; keys must include tenant and required policy factors.
- Queued export jobs creating files under a broad service principal when the requester cannot export tenant B; test submit, run, and download.
- Signed URLs with valid expiry/object that get shared? Check permissions before issuing URLs and enforce revocation appropriate to sensitivity.
- Batch APIs receiving a list with A/D-7 and B/D-7; one unauthorized item must never execute silently. Define clear all-or-nothing or per-item failure contracts and verify side effects.
- WebSocket/SSE subscriptions, events, search indexes, object storage, backups, and logs all preserve tenant association; debug logs must never leak B's secret content to user A.

## 10. Standalone Java 17: Two-Tenant and Principal-Switching Test

The program below simulates the policy and data store in Java 17+ (no Spring or database needed). It simulates an already authenticated principal with `issuer` and `subject`; **it does not validate JWT signatures**, so never use the `Principal` constructor as a production authentication API. The focus is passing actor/tenant into every call and checking membership, functional permissions, and composite keys before reading/writing.

Save as `TwoTenantIsolationDemo.java` and run:

~~~bash
javac TwoTenantIsolationDemo.java
java TwoTenantIsolationDemo
~~~

Complete code:

~~~java
import java.util.*;

public class TwoTenantIsolationDemo {
    record Principal(String issuer, String sub, Set<String> scopes) {}
    record Key(String tenant, String id) {}

    static final class Denied extends RuntimeException {}
    static final class NotFound extends RuntimeException {}

    static final class Store {
        private final String issuer = "https://login.example.test";
        private final Map<String, Set<String>> memberships = new HashMap<>();
        private final Map<Key, String> documents = new HashMap<>();

        void setMembership(String subject, Set<String> tenantIds) {
            memberships.put(subject, Set.copyOf(tenantIds));
        }

        void put(String tenant, String id, String value) {
            documents.put(new Key(tenant, id), value);
        }

        private void require(Principal actor, String tenant, String scope) {
            if (actor == null
                    || !issuer.equals(actor.issuer())
                    || !actor.scopes().contains(scope)
                    || !memberships.getOrDefault(actor.sub(), Set.of())
                        .contains(tenant)) {
                throw new Denied();
            }
        }

        String read(Principal actor, String tenant, String id) {
            require(actor, tenant, "documents.read");
            String value = documents.get(new Key(tenant, id));
            if (value == null) throw new NotFound();
            return value;
        }

        void rename(Principal actor, String tenant, String id, String title) {
            require(actor, tenant, "documents.write");
            Key key = new Key(tenant, id);
            if (!documents.containsKey(key)) throw new NotFound();
            documents.put(key, title);
        }
    }

    static void denied(Runnable action) {
        try {
            action.run();
        } catch (Denied expected) {
            return;
        }
        throw new AssertionError("Expected access denial");
    }

    public static void main(String[] args) {
        String issuer = "https://login.example.test";
        Principal alice = new Principal(
            issuer, "alice", Set.of("documents.read", "documents.write"));
        Principal bob = new Principal(
            issuer, "bob", Set.of("documents.read"));
        Principal casey = new Principal(
            issuer, "casey", Set.of("documents.read"));

        Store store = new Store();
        store.setMembership("alice", Set.of("A"));
        store.setMembership("bob", Set.of("B"));
        store.setMembership("casey", Set.of("A", "B"));
        store.put("A", "D-7", "alpha-secret");
        store.put("B", "D-7", "bravo-secret");

        System.out.println("Alice/A=" + store.read(alice, "A", "D-7"));
        System.out.println("Bob/B=" + store.read(bob, "B", "D-7"));

        denied(() -> store.read(alice, "B", "D-7"));
        System.out.println("DENY Alice/B");
        denied(() -> store.read(bob, "A", "D-7"));
        System.out.println("DENY Bob/A");

        System.out.println("Casey/A=" + store.read(casey, "A", "D-7"));
        System.out.println("Casey/B=" + store.read(casey, "B", "D-7"));

        store.setMembership("casey", Set.of("A"));
        denied(() -> store.read(casey, "B", "D-7"));
        System.out.println("DENY Casey/B after revoke");

        // Sequential execution with a different principal: no leftover context.
        System.out.println("Switch-to-Bob=" + store.read(bob, "B", "D-7"));

        denied(() -> store.rename(alice, "B", "D-7", "tampered"));
        System.out.println("DENY Alice write B");

        store.rename(alice, "A", "D-7", "alpha-v2");
        System.out.println("Updated A=" + store.read(alice, "A", "D-7"));
        System.out.println("Unchanged B=" + store.read(bob, "B", "D-7"));
    }
}
~~~

Expected stdout:

~~~text
Alice/A=alpha-secret
Bob/B=bravo-secret
DENY Alice/B
DENY Bob/A
Casey/A=alpha-secret
Casey/B=bravo-secret
DENY Casey/B after revoke
Switch-to-Bob=bravo-secret
DENY Alice write B
Updated A=alpha-v2
Unchanged B=bravo-secret
~~~

The line `Unchanged B=bravo-secret` matters more than a 403 response: it proves Alice's write operation affected only A. When Casey's membership is removed, Casey's simulated token/identity did not change yet the policy still denies B, underscoring live membership verification. In production, you need principal authentication, DB transactions, object ACLs, multi-tenant caching, auditing, and real JWT tests as outlined above.

## 11. Create/Edit/Delete/Search/Export Scenarios and Invariant Checks

### 11.1. CREATE

Alice calls `POST /api/tenants/A/documents` with `projectId=P-1` and a payload containing `tenantId=B`. The server must use verified tenant A, ignoring `tenantId` in the body. If the client sends `ownerId=bob` or a `projectId` belonging to B, enforce role/ownership policy and tenant foreign keys. After the request, assert A created one record and B added zero records; verify audited owner/tenant.

### 11.2. UPDATE / PATCH

Rename A/D-7 under principal Alice, then try renaming B/D-7 by swapping path/header/body. Assert B's document content/version remain unchanged. For multi-field or bulk updates, policy must block changing `tenant_id`/`owner_id`/`project_id` outside permitted workflows. Version-predicated writes prevent concurrent overwrites; write-time permission scoping must apply per transaction/risk model.

### 11.3. DELETE

Alice with `documents.delete` in A can delete A's record per object policy, never B's record with the same ID. Test hard deletes, soft-delete flags, cascade relations, audit/outbox events, and file attachments. Never accept merely asserting HTTP 403 if a delete background job was already enqueued or a delete event emitted before denial.

### 11.4. SEARCH / LIST / COUNT

With A holding 2 documents and B holding 3 documents, Alice searching `"report"` must see only permitted A documents. Test offsets, cursors, filters, sorting, totalElements/totalPages, faceted counts, and autocomplete. Never mix A/B and return `totalElements=5` even if `content` has 2 rows; metadata is also another tenant's data.

### 11.5. EXPORT / DOWNLOAD

Alice requests an export of A: the job records `requestedBy=Alice`, `authorizedTenant=A`, and approved filters. Workers run under a service identity yet re-verify Alice/tenant A permissions before querying; CSV/Excel/JSON rows belong only to A, never adding B because the service has broad DB rights. On download, re-verify actor and output object. Signed URLs and cached files carry appropriate scopes/expiries; tenant B cannot guess an ID and download A's file.

### 11.6. Data Relationships

Document A/D-7 referencing `projectId=P-1` must resolve **A/P-1**, not B/P-1. For joins, always scope both tables or use composite foreign keys. For legitimate cross-tenant sharing, use an explicit `ShareGrant`/`AccessPolicy` entity permitting **exact objects and actions**, rather than removing tenant boundaries across all queries. Administrative roles in A never default to administrative roles in B.

## 12. Process for Running This Practice in a Real Project

1. **Declare the contract:** define issuer/audience, principal key, tenant selector, membership lifecycle, per-tenant roles, and 401/403/404 policies; document functional and object permissions needed per endpoint.
2. **Create database fixtures:** A/B sharing `D-7` with different titles and owners; Casey in both A/B; admin A absent from B; A-9/B-9; same `P-1` in both tenants to catch join bugs.
3. **Enable security chain/method security:** authenticate requests, enforce scopes, `@EnableMethodSecurity`, service membership and ACL checks; undeclared endpoints must fail closed.
4. **Enforce persistence constraints:** every query, count, update, delete, join, and export uses the verified tenant context; composite keys/FKs/RLS where appropriate for architecture.
5. **Run positive matrix:** Alice→A; Bob→B; Casey→A/B. Verify exact contents via distinct fields, not just status codes or item counts.
6. **Run negative matrix:** Alice→B, Bob→A, admin A→B, missing scope, forged header/body, wrong issuer/audience, revoked token/permission, B project reference, mixed bulk IDs.
7. **Run identity switches:** A→B→A on the same test/worker pool and session logout/login if applicable; test exception paths and separate cache keys.
8. **Compare DB/side effects:** snapshot B before Alice's tests, and after each write/denial verify records, versions, soft-delete flags, audits, queues, and export artifacts remain intact.
9. **Check secondary surfaces:** search/count, events, caches, file URLs, logs, async; the same API can still leak through side paths.
10. **Integrate into CI:** regression suite runs with a suitable database and auth stack; any change to converters, memberships, multi-tenant repositories, role hierarchy, or caches must re-run isolation tests.

Never declare success merely because “requests without tokens return 401” or “Alice can read A.” A system that always denies also passes negative tests; a system that reads A properly yet leaks B in counts/searches has not achieved isolation. Both positive and negative cases **on the same dataset** plus side-effect checks are required.

## 13. Common Mistakes and Fixes

| Mistake | Symptom | Fix |
| --- | --- | --- |
| Trusting `tenantId` in header | Alice swaps header to B and gets B | Treat header as selector; check membership via authenticated principal |
| Querying only by `id` | A/B share `D-7` and wrong one is read | Use `(tenantId, id)` in queries, indexes, and relations |
| Unscoped admin role | A's `TENANT_ADMIN` manages B | Always scope roles/permissions by tenant or explicit scope |
| Treating client-sent JSON `sub` as principal | Caller can impersonate Bob | Derive identity from verified token/session; validate issuer/audience |
| Mixing tenants on cache key `D-7` | B response returns A's content | Namespace caches by tenant plus required actor/policy |
| Checking only routes, not services | Scheduler/worker paths bypass HTTP rules | Enforce policy at service/query boundaries; explicit service identity |
| Using `findAll()` then filtering in Java | Counts, logs, caches, and memory hold B | Filter in DB/search, verify metadata |
| Running `jwt().authorities(...)` and treating it as prod JWT test | Custom converter/issuer bypassed | Test signed tokens/decoders/converters and request authorization separately |
| Testing only one user and one tenant | Misses stale context on switch | Run A→B→A on same pool/session, including exception paths |
| Revoking membership without cache invalidation | Casey keeps reading B | Policy freshness/TTL/revocation + regression tests |
| Allowing `tenantId` updates via entity DTO | Unauthorized move of document from A to B | Immutable tenant; dedicated transfer workflow checking both sides |
| Returning `403` after writing DB | Policy ran after side effect | Authorize before mutating, transaction/DB predicate, and assert state |
| Relying on hard-to-guess UUIDs | IDOR persists if ID leaks | Object-level authorization on every operation |
| Unscoped signed export URLs | Alice downloads Bob's file via URL | Authorize URL issuance/file download, expiry, and revocation |

## 14. Final Lesson Acceptance Checklist

- [ ] Two real tenants share the **same local ID** with distinct data; fixtures are isolated between tests.
- [ ] Actor key uses verified identity, never trusting `sub`/`userId`/`tenantId` from headers/body.
- [ ] Per-tenant roles are not promoted to global permissions; functional scopes do not replace membership/ACL.
- [ ] Alice→A, Bob→B, Casey→A/B all succeed; Alice→B and Bob→A are denied.
- [ ] Switching principals A→B→A leaves no stale `SecurityContext`/tenant context/cache.
- [ ] Revoking membership or locking an account causes subsequent operations to be denied per freshness contract.
- [ ] Repository read/write/delete/query/count/join include tenant predicates or equivalent isolation boundaries.
- [ ] Clients cannot alter tenant/owner/foreign keys outside policy; A's relations never link to B's projects.
- [ ] Negative requests cause zero unauthorized DB, cache, event, outbox, file/export, or audit side effects.
- [ ] Search/list/count/pagination/export/bulk/file downloads leak no records or metadata from another tenant.
- [ ] Every deny test has a positive control with valid permissions and data, rather than only testing errors.
- [ ] JWT integration tests distinguish mock `jwt()` from real signed/issuer/audience tokens; CSRF and status codes are properly handled.
- [ ] Background workers use explicit service identities and requester/tenant policies; caches/connection pools/thread pools never stick tenants.
- [ ] Operational data/logs are tenant-scoped without logging raw tokens or secrets; cross-tenant anomalies are safely monitored.

**Conclusion:** Tenant isolation is an **end-to-end invariant** across authenticated identity, tenant selection, role/membership, object policy, queries, and outputs. A solid two-tenant test proves both sides: **authorized in-scope users succeed** and **no change in principal, tenant selector, ID, session, or permissions over time leaks or mutates another tenant's data**.

### References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and requiring calls through Spring proxies.
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()`, mock principal/claims/authorities, and limitations of test authentication.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests` and URL managers.
- [OWASP — Multi Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): data boundaries, tenant verification, caches/queues/storage, and RLS.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): object authorization, preventing IDOR/BOLA when swapping IDs.
