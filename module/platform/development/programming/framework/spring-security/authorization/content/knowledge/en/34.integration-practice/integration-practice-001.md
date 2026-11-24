# Building a Permission Matrix for a Multi-User Document Management Application

## Learning Objectives and Practice Problem

A multi-user document management application cannot simply check `authenticated()` or a single global role and then allow opening every document. The decision also depends on **tenant, owner, shared users, document type, status, and action**. This practice builds a **testable permission matrix**, then maps it to Spring Security and data queries.

After this lesson, learners can: identify subject/resource/action/context; build a PERMIT/DENY table for each relationship to a document; establish the order of deny conditions; write a standalone Java 17 program that evaluates permissions; outline a Spring Security 6.x configuration; design tests for HTTP, database, sharing/revocation, and pagination; and evaluate IDOR, cross-tenant bypass, over-privileged access, and data leakage vulnerabilities.

**The following roles and policies are illustrative rules of a hypothetical application**, not built-in features of Spring Security. In a real system, they must be finalized with the business owner before writing code.

## 1. Designing the “Document Hub” Business Domain

The application serves multiple organizations (multi-tenant). Users must have a valid membership to access documents in that tenant. A document has one owner and can additionally share VIEWER/EDITOR permissions with members of the same tenant. A tenant has an ADMIN for administration; MEMBER users can create documents.

| Component | Data Fields | Security Meaning |
| --- | --- | --- |
| Principal | `userId`, authentication status, membership, per-tenant role | Identity must be verified by the server |
| Document | `id`, `tenantId`, `ownerId`, `visibility`, `classification`, `status` | Source of truth for document relationships and state |
| ACL | `documentId`, `granteeId`, `grant`, `expiresAt`, `revokedAt` | Additional per-document permissions |
| Action | `READ`, `DOWNLOAD`, `EDIT`, `DELETE`, `SHARE`, `RESTORE` | Each action has its own permission, not lumped into “can open” |
| Context | Current authenticated tenant, time, MFA/policy version if any | Used when actual policy requires it |

Two layers of roles/permissions must not be confused:

- **TENANT_ADMIN**: administrative role **within a single tenant**. In this example, an admin views and manages ACTIVE documents of the tenant, even if not the owner; the admin does **not** cross tenant boundaries.
- **MEMBER**: tenant member who can create documents; for each document, the permission level depends on owner relationship, ACL, or visibility.
- **Owner**: relationship `document.ownerId == user.id`, **not** a global `ROLE_OWNER`. Alice can be the owner of D101 while being a viewer of D102.
- **ACL EDITOR**: permitted to READ/DOWNLOAD/EDIT ACTIVE documents, **not** automatically permitted to DELETE or SHARE.
- **ACL VIEWER**: permitted to READ/DOWNLOAD, not permitted to EDIT/DELETE/SHARE.

Using `hasRole("MEMBER")` to allow editing any documentId is wrong: it only confirms membership/authority at one level, without proving the user is the owner or has been granted ACL EDITOR.

### 1.1. Visibility, Classification, and Status

The example establishes three independent dimensions:

1. `visibility = PRIVATE`: only the owner, ACL grantees, or an admin **in the same tenant** may read.
2. `visibility = TEAM`: tenant members may READ/DOWNLOAD if the document has `classification = INTERNAL`. TEAM does not grant EDIT/DELETE/SHARE permissions to every member.
3. `classification = CONFIDENTIAL`: only allowed with `PRIVATE`. The `CONFIDENTIAL + TEAM` pair is invalid: validation must reject it on create/update, and the read policy must also fail-safe deny if the database contains corrupted data.
4. `status = ACTIVE`: applies the normal action matrix.
5. `status = ARCHIVED`: users who already have read permission can still READ/DOWNLOAD; no one can EDIT/DELETE/SHARE before restore. Only a TENANT_ADMIN in the same tenant may RESTORE. The owner cannot self-restore in this illustrative policy.

Tenant isolation is a stronger boundary than ACL: even if D101's ACL accidentally contains a grantee in tenant B, that grantee is still denied. Every decision must enforce all agreed constraints.

### 1.2. Specific Rules for CREATE

`CREATE` does not yet have a document to compare owner/ACL, so it checks that the authenticated user has role MEMBER or TENANT_ADMIN in the target tenant. The server assigns `ownerId` and `tenantId` based on the principal/membership, never allowing the client to send `ownerId=alice` or `tenantId=otherTenant` to claim permissions. A MEMBER role in tenant A cannot create data in tenant B.

## 2. Standard Permission Matrix by Relationship to the Document

Notation **Y** = permit; **N** = deny. The following table applies when the document is **ACTIVE**, tenant/identity are valid, and there is no data violating classification/visibility.

| Caller Relationship to Document | READ | DOWNLOAD | EDIT | DELETE | SHARE | RESTORE |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| TENANT_ADMIN in same tenant | Y | Y | Y | Y | Y | N |
| Owner in same tenant | Y | Y | Y | Y | Y | N |
| ACL EDITOR in same tenant | Y | Y | Y | N | N | N |
| ACL VIEWER in same tenant | Y | Y | N | N | N | N |
| MEMBER without ACL, TEAM + INTERNAL document | Y | Y | N | N | N | N |
| MEMBER without ACL, PRIVATE document | N | N | N | N | N | N |
| User from another tenant | N | N | N | N | N | N |
| Anonymous/unauthenticated | N | N | N | N | N | N |

For **ARCHIVED** documents, the rules are:

| Relationship within Tenant for ARCHIVED | READ | DOWNLOAD | EDIT | DELETE | SHARE | RESTORE |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| TENANT_ADMIN | Y | Y | N | N | N | Y |
| Owner | Y | Y | N | N | N | N |
| ACL EDITOR or VIEWER | Y | Y | N | N | N | N |
| MEMBER viewing TEAM + INTERNAL document | Y | Y | N | N | N | N |
| MEMBER without read access / other tenant / anonymous | N | N | N | N | N | N |

**Decision precedence** (deny before permit): check authentication and active tenant membership → document tenant must match → data/visibility/classification must be valid → check status → evaluate admin/owner/ACL/TEAM per action → unknown actions or missing attributes are **DENY by default**.

Do not interpret “already has a grant” as bypassing tenant, status, or classification constraints. A revoked or expired ACL EDITOR grant is no longer valid, even if caches have not been updated yet. The exact effective time of an ACL must be clearly defined if the product supports expiry.

## 3. Multi-User Fixture for Testing

Create two tenants t-a and t-b; the actors:

| Actor | Authenticated Tenant | Role | Test Purpose |
| --- | --- | --- | --- |
| `alice` | t-a | MEMBER | Owner of D101, D105; VIEWER of D102; EDITOR of D104 |
| `bob` | t-a | MEMBER | Owner of D102–D104 |
| `dave` | t-a | TENANT_ADMIN | Admin permission scoped to the tenant |
| `erin` | t-a | MEMBER | No ACL, only views TEAM |
| `mallory` | t-b | MEMBER | Owner of D201; attempts cross-tenant requests |
| anonymous | No verified membership | — | Proves TEAM is not a public Internet document |

Create documents:

| ID | Tenant | Owner | Visibility | Classification | Status | Specific ACL |
| --- | --- | --- | --- | --- | --- | --- |
| D101 | t-a | alice | PRIVATE | INTERNAL | ACTIVE | none |
| D102 | t-a | bob | PRIVATE | CONFIDENTIAL | ACTIVE | alice = VIEWER |
| D103 | t-a | bob | TEAM | INTERNAL | ACTIVE | none |
| D104 | t-a | bob | PRIVATE | INTERNAL | ACTIVE | alice = EDITOR |
| D105 | t-a | alice | PRIVATE | INTERNAL | ARCHIVED | none |
| D201 | t-b | mallory | PRIVATE | INTERNAL | ACTIVE | none |

**Concrete expected result matrix** for the fixture:

| Actor / Document | READ | DOWNLOAD | EDIT | DELETE | SHARE | RESTORE | Reason |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | --- |
| alice / D101 | Y | Y | Y | Y | Y | N | Owner, ACTIVE |
| alice / D102 | Y | Y | N | N | N | N | ACL VIEWER |
| alice / D103 | Y | Y | N | N | N | N | TEAM + INTERNAL |
| alice / D104 | Y | Y | Y | N | N | N | ACL EDITOR |
| alice / D105 | Y | Y | N | N | N | N | ARCHIVED |
| alice / D201 | N | N | N | N | N | N | Different tenant |
| dave / D102 | Y | Y | Y | Y | Y | N | ADMIN in same tenant, ACTIVE |
| dave / D105 | Y | Y | N | N | N | Y | Only ADMIN can RESTORE |
| erin / D103 | Y | Y | N | N | N | N | TEAM, no ACL |
| erin / D101 | N | N | N | N | N | N | PRIVATE |
| mallory / D201 | Y | Y | Y | Y | Y | N | Owner in tenant B |
| mallory / D101 | N | N | N | N | N | N | Tenant B differs from A |
| anonymous / D103 | N | N | N | N | N | N | Not logged in |

In a real project, the matrix should be version-controlled alongside policies and test fixtures. When business requirements add `APPROVE`, `PUBLISH`, `TRANSFER_OWNERSHIP` permissions or a `SECRET` classification, add columns/conditions and tests before exposing endpoints.

## 4. Standalone Java 17 Program Simulating the Matrix

This program **does not require Spring**. It shows how to take an actor, document, and action and return a deny-by-default decision. This is a model for learning; hardcoded data in `main` must be replaced by verified claims, DB, and ACL in a real application.

Save with the exact filename `DocumentMatrixDemo.java`:

```java
import java.util.Map;
import java.util.Objects;

public class DocumentMatrixDemo {
    enum Action { READ, DOWNLOAD, EDIT, DELETE, SHARE, RESTORE }
    enum Visibility { PRIVATE, TEAM }
    enum Classification { INTERNAL, CONFIDENTIAL }
    enum Status { ACTIVE, ARCHIVED }
    enum Grant { VIEWER, EDITOR }

    record Actor(String id, String tenant, boolean admin,
                 boolean authenticated) {}

    record Document(long id, String tenant, String owner,
                    Visibility visibility, Classification classification,
                    Status status, Map<String, Grant> acl) {}

    static boolean permitted(Actor actor, Document doc, Action action) {
        if (actor == null || doc == null || action == null
                || !actor.authenticated()
                || !Objects.equals(actor.tenant(), doc.tenant())) {
            return false;
        }

        if (doc.classification() == Classification.CONFIDENTIAL
                && doc.visibility() == Visibility.TEAM) {
            return false; // Do not PERMIT when policy data is invalid
        }

        boolean admin = actor.admin();
        boolean owner = actor.id().equals(doc.owner());
        Grant grant = doc.acl().get(actor.id());

        boolean readable = admin || owner || grant != null
                || (doc.visibility() == Visibility.TEAM
                    && doc.classification() == Classification.INTERNAL);

        if (doc.status() == Status.ARCHIVED) {
            return switch (action) {
                case READ, DOWNLOAD -> readable;
                case RESTORE -> admin;
                default -> false;
            };
        }

        if (doc.status() != Status.ACTIVE) return false;

        return switch (action) {
            case READ, DOWNLOAD -> readable;
            case EDIT -> admin || owner || grant == Grant.EDITOR;
            case DELETE, SHARE -> admin || owner;
            case RESTORE -> false;
        };
    }

    static void print(String label, Actor actor, Document doc) {
        System.out.print(label + ":");
        for (Action action : Action.values()) {
            System.out.print(" " + action + "="
                    + (permitted(actor, doc, action) ? "Y" : "N"));
        }
        System.out.println();
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "t-a", false, true);
        Actor dave = new Actor("dave", "t-a", true, true);
        Actor erin = new Actor("erin", "t-a", false, true);
        Actor mallory = new Actor("mallory", "t-b", false, true);
        Actor anonymous = new Actor("anonymous", "t-a", false, false);

        Document d101 = new Document(101, "t-a", "alice",
                Visibility.PRIVATE, Classification.INTERNAL,
                Status.ACTIVE, Map.of());
        Document d102 = new Document(102, "t-a", "bob",
                Visibility.PRIVATE, Classification.CONFIDENTIAL,
                Status.ACTIVE, Map.of("alice", Grant.VIEWER));
        Document d103 = new Document(103, "t-a", "bob",
                Visibility.TEAM, Classification.INTERNAL,
                Status.ACTIVE, Map.of());
        Document d104 = new Document(104, "t-a", "bob",
                Visibility.PRIVATE, Classification.INTERNAL,
                Status.ACTIVE, Map.of("alice", Grant.EDITOR));
        Document d105 = new Document(105, "t-a", "alice",
                Visibility.PRIVATE, Classification.INTERNAL,
                Status.ARCHIVED, Map.of());
        Document d201 = new Document(201, "t-b", "mallory",
                Visibility.PRIVATE, Classification.INTERNAL,
                Status.ACTIVE, Map.of());

        print("alice D101", alice, d101);
        print("alice D102", alice, d102);
        print("alice D103", alice, d103);
        print("alice D104", alice, d104);
        print("alice D105", alice, d105);
        print("alice D201", alice, d201);
        print("dave D105", dave, d105);
        print("erin D103", erin, d103);
        print("erin D101", erin, d101);
        print("mallory D201", mallory, d201);
        print("mallory D101", mallory, d101);
        print("anonymous D103", anonymous, d103);
    }
}
```

Compile and run:

```bash
javac DocumentMatrixDemo.java
java DocumentMatrixDemo
```

Exact stdout:

```text
alice D101: READ=Y DOWNLOAD=Y EDIT=Y DELETE=Y SHARE=Y RESTORE=N
alice D102: READ=Y DOWNLOAD=Y EDIT=N DELETE=N SHARE=N RESTORE=N
alice D103: READ=Y DOWNLOAD=Y EDIT=N DELETE=N SHARE=N RESTORE=N
alice D104: READ=Y DOWNLOAD=Y EDIT=Y DELETE=N SHARE=N RESTORE=N
alice D105: READ=Y DOWNLOAD=Y EDIT=N DELETE=N SHARE=N RESTORE=N
alice D201: READ=N DOWNLOAD=N EDIT=N DELETE=N SHARE=N RESTORE=N
dave D105: READ=Y DOWNLOAD=Y EDIT=N DELETE=N SHARE=N RESTORE=Y
erin D103: READ=Y DOWNLOAD=Y EDIT=N DELETE=N SHARE=N RESTORE=N
erin D101: READ=N DOWNLOAD=N EDIT=N DELETE=N SHARE=N RESTORE=N
mallory D201: READ=Y DOWNLOAD=Y EDIT=Y DELETE=Y SHARE=Y RESTORE=N
mallory D101: READ=N DOWNLOAD=N EDIT=N DELETE=N SHARE=N RESTORE=N
anonymous D103: READ=N DOWNLOAD=N EDIT=N DELETE=N SHARE=N RESTORE=N
```

**How to read this:** D104 gives Alice EDIT=Y because of ACL EDITOR, yet SHARE=N and DELETE=N. D105 still has READ=Y for the owner, but blocks EDIT because it is ARCHIVED. D201 is blocked for Alice even if the ID is guessed correctly; never rely on the client “knowing the ID” to grant access. The standalone program does not verify data sources: production must reject null ACLs, disabled accounts, revoked/expired grants, and any unrecognized states before granting permission.

## 5. Integrating the Policy with Spring Security

### 5.1. Restricting Requests Before Per-Document Authorization

An **illustrative configuration for Spring Boot 3.x, Spring Security 6.x, Servlet MVC**. The snippets below are integration snippets, not a complete Java project; specific imports/beans and endpoints are supplied by the application.

```java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/documents")
                    .hasAnyRole("MEMBER", "TENANT_ADMIN")
                .requestMatchers("/api/documents/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

`authenticated()` only blocks anonymous users; a member of tenant A can still send GET `/api/documents/201` to the filter. **Authorization checks by documentId must continue at the service layer**. `hasAnyRole` assumes authority `ROLE_MEMBER`/`ROLE_TENANT_ADMIN`; if using a different JWT converter, verify the actual `GrantedAuthority` values. `httpBasic` is only for illustrating authentication; applications using sessions/JWT need the corresponding configuration. If using sessions/cookies, state-changing requests must go through CSRF; never disable CSRF just to make POST/PUT tests pass.

### 5.2. A Policy Service Sharing a Single Decision Contract

You can use `@PreAuthorize` on a Spring-managed service; for example:

```java
@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentAccessRepository access;
    private final TenantIdentity tenantIdentity;

    public DocumentPolicy(
            DocumentAccessRepository access,
            TenantIdentity tenantIdentity) {
        this.access = access;
        this.tenantIdentity = tenantIdentity;
    }

    public boolean permits(Authentication principal,
                           long documentId, String action) {
        if (principal == null || !principal.isAuthenticated()) return false;
        String tenant = tenantIdentity.verifiedTenant(principal);
        if (tenant == null || tenant.isBlank()) return false;

        // access must use trusted tenant, identity, and DB/ACL;
        // unknown action, missing doc, policy error -> DENY.
        return access.isAllowed(tenant, principal.getName(), documentId, action);
    }
}
```

`TenantIdentity.verifiedTenant` must verify membership in the actual tenant; a tenant string sent by the client must never be used instead. `DocumentAccessRepository.isAllowed` is an application interface that must be implemented according to the finalized matrix. In a multi-membership model, pass the exact role **bound to the tenant under evaluation**; do not rely on a global admin boolean. If a remote policy client fails and there is no trusted PERMIT result, do not execute the operation.

Service with method security:

```java
@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("@documentPolicy.permits(authentication, #id, 'READ')")
    @Transactional(readOnly = true)
    public DocumentDto read(@P("id") long id) {
        DocumentEntity doc = documents.findById(id)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
        return DocumentDto.from(doc);
    }

    @PreAuthorize("@documentPolicy.permits(authentication, #id, 'EDIT')")
    @Transactional
    public void edit(@P("id") long id, UpdateDocument body) {
        // Modify content via consistent tenant/owner/grant/status conditions
        // inside the transaction; do not write if status/ACL changed.
    }

    @PreAuthorize("@documentPolicy.permits(authentication, #id, 'SHARE')")
    @Transactional
    public void share(@P("id") long id, ShareCommand command) {
        // Verify recipient is still a member in the same tenant,
        // document is still ACTIVE, grant is only VIEWER/EDITOR;
        // persist ACL and audit success/failure.
    }
}
```

This is an **API illustration snippet**; you must implement the types `DocumentRepository`, `DocumentEntity`, `DocumentDto`, `UpdateDocument`, `ShareCommand`, `DocumentAccessRepository`, and the corresponding imports; `@P` marks the parameter name for SpEL. Do not treat the comments in EDIT/SHARE methods as complete implementations. Real handlers and queries must be tested.

Be careful with Spring AOP: `@PreAuthorize` works when calls go through a proxy; do not rely on internal `this.edit(...)` calls within the same bean. Controllers, scheduled jobs, message listeners, and other APIs must enforce authorization at the appropriate boundary.

**TOCTOU:** method-level checks run before business logic; between checking ACL/status and executing UPDATE, another request might revoke permission or archive the document. Use transactions/locking or a conditional UPDATE with tenant + permission + ACTIVE predicates and check the updated row count; never treat a prior check as permanent permission.

### 5.3. Sharing and Revoking Are Independent Permissions

A `POST /api/documents/{id}/share` endpoint must check simultaneously: the caller has SHARE on an ACTIVE document; the grantee is a member **in the same tenant**; the grant is only VIEWER/EDITOR; a shared user cannot change owner/tenant or self-grant ADMIN; duplicate ACLs are prevented, and auditing is recorded. EDITOR permission does **not** imply SHARE in this policy.

When revoking an ACL, read and download permissions must change; old URLs, download links, share links, PERMIT caches, WebSockets/subscriptions, and export APIs must not continue returning data past the effective expiration. Cache keys need subject + tenant + resource + action + ACL/policy version, with TTL/invalidation matching the sensitivity level. A cache miss or unresponsive policy service does not mean PERMIT.

## 6. The Permission Matrix Must Also Apply to Lists and Counts

Do not protect only `GET /api/documents/{id}` while returning all metadata in `GET /api/documents` or search results. In the fixture above:

| Caller | IDs Permitted to Appear in List | `totalElements` |
| --- | --- | ---: |
| alice/t-a | [101,102,103,104,105] | 5 |
| dave/t-a | [101,102,103,104,105] | 5 |
| erin/t-a | [103] | 1 |
| mallory/t-b | [201] | 1 |
| anonymous | No API access | No count returned |

For paginated queries, **filter permissions before `LIMIT/OFFSET`**, and `COUNT` must use the exact same predicate. If the database returns [101,102] and the application filters for Erin afterward, the first page could be empty even though D103 is permitted; the total must not be computed across all tenant documents.

Guiding SQL example for listing. The `verified_*` parameters must come from server-verified authentication/membership; the admin role must be verified within the corresponding tenant. Update conditions if ACLs have time validity or new statuses:

```sql
SELECT d.id, d.title, d.status
FROM documents d
WHERE d.tenant_id = :verified_tenant
  AND d.status IN ('ACTIVE', 'ARCHIVED')
  AND NOT (d.classification = 'CONFIDENTIAL'
           AND d.visibility = 'TEAM')
  AND (
       :is_tenant_admin = TRUE
       OR d.owner_id = :verified_actor
       OR EXISTS (
           SELECT 1 FROM document_acl a
           WHERE a.document_id = d.id
             AND a.tenant_id = d.tenant_id
             AND a.grantee_id = :verified_actor
             AND a.grant IN ('VIEWER', 'EDITOR')
             AND a.revoked_at IS NULL
       )
       OR (d.visibility = 'TEAM'
           AND d.classification = 'INTERNAL')
  )
ORDER BY d.id ASC
LIMIT :page_size OFFSET :offset;
```

`SELECT COUNT(*)` must use the exact tenant/status/classification/ACL/owner/TEAM conditions above while omitting ORDER BY/LIMIT/OFFSET. Do not take the total from the base table or apply filters after pagination. If the app supports multiple tenants per user or `expiresAt`/soft-delete, both the data query and count query must be updated together. Verify that response DTOs do not leak `content`, file download paths, full ACLs, document titles, or out-of-scope counts.

Download, preview, file versions, exports, and thumbnails also need permission checks at the point bytes are served. A signed URL is a separate credential that must have a clear scope/expiration/revocation contract; do not issue perpetual URLs merely because the user once had READ access.

## 7. Designing Multi-Layer Matrix Testing

### 7.1. The Test Matrix Must Include Both Positive and Negative Cases

| Test | Principal / Action | Expected | What Needs Protection |
| --- | --- | --- | --- |
| AUTH-01 | anonymous READ D103 | DENY | TEAM is not public to anonymous |
| TENANT-01 | alice/t-a READ D201 | DENY | Block cross-tenant IDOR |
| TENANT-02 | mallory/t-b SHARE D101 | DENY | Do not grant ACL across tenants |
| OWNER-01 | alice EDIT D101 | PERMIT | ACTIVE owner has edit permission |
| ACL-01 | alice READ D102 | PERMIT | VIEWER can read shared CONFIDENTIAL doc |
| ACL-02 | alice EDIT D102 | DENY | VIEWER cannot edit |
| ACL-03 | alice EDIT D104 | PERMIT | EDITOR can edit |
| ACL-04 | alice SHARE D104 | DENY | EDITOR cannot self-grant/share permissions |
| TEAM-01 | erin READ D103 | PERMIT | TEAM + INTERNAL |
| TEAM-02 | erin READ D101 | DENY | Unshared PRIVATE |
| ADMIN-01 | dave DELETE D102 | PERMIT | ADMIN in tenant, ACTIVE |
| ARCH-01 | alice EDIT D105 | DENY | Owner cannot bypass ARCHIVED state |
| ARCH-02 | dave RESTORE D105 | PERMIT | Only admin can restore |
| CLASS-01 | Create CONFIDENTIAL+TEAM | DENY/400 | Block invalid visibility combination |
| SHARE-01 | alice share D101 to mallory | DENY | Grantee in another tenant |
| LIST-01 | erin GET list | [103], total=1 | Do not leak private docs in list/count |
| REVOKE-01 | Alice READ D102 after revoking VIEWER | DENY | Do not use stale ACL |
| DEFAULT-01 | Null/unrecognized action | DENY | Fail closed |

When testing HTTP, authenticated but unauthorized requests usually receive **403**, while anonymous requests usually receive **401** in an API configured with the corresponding authentication entry point. A product may return **404** instead of 403 to hide a document's existence; the contract must be consistent and not leak differences through the response body. For denied requests, verify the DB is not modified, no ACL is created, and no private bytes appear in the response.

### 7.2. Spring Security + MockMvc Integration Testing

Example Spring Boot 3.x/Security 6.x integration skeleton (requires Spring/JUnit/Mockito imports, endpoints, tenant context bean, database fixture, and application class):

```java
@SpringBootTest
@AutoConfigureMockMvc
@Sql("/fixtures/documents-matrix.sql")
class DocumentPermissionsIT {
    @Autowired MockMvc mvc;

    @Test
    @WithMockUser(username = "erin", roles = "MEMBER")
    void teamIsReadableButPrivateIsForbidden() throws Exception {
        // Test TenantIdentity must map erin -> t-a.
        mvc.perform(get("/api/documents/103"))
                .andExpect(status().isOk());
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "MEMBER")
    void viewerCannotEditAndEditorCannotShare() throws Exception {
        mvc.perform(put("/api/documents/102")
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"changed\"}"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/api/documents/104/share")
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"granteeId\":\"erin\",\"grant\":\"VIEWER\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "mallory", roles = "MEMBER")
    void tenantBDoesNotReadTenantA() throws Exception {
        // Test TenantIdentity must map mallory -> t-b.
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/documents/101/download"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "erin", roles = "MEMBER")
    void listCountContainsOnlyPermittedDocuments() throws Exception {
        mvc.perform(get("/api/documents").param("size", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content.length()").value(1))
                .andExpect(jsonPath("$.content[0].id").value(103))
                .andExpect(jsonPath("$.totalElements").value(1));
    }
}
```

The tests above **only run when the application fully implements** `DocumentPolicy`, endpoints/DTOs, the SQL fixture, and a test `TenantIdentity`. `@WithMockUser` only creates a username/authorities, **not automatically a tenant claim**; never read the tenant from arbitrary query/header parameters just to “make tests green.” Separate JWT/session tests must confirm that membership and claims are properly validated. If the app returns 404 to hide IDs, adjust expected statuses consistently with the policy.

For edit/delete/ACL-grant tests, re-read the DB after the request to prove **there are no side effects**. Using `@MockBean` to return pre-filtered repository results prevents the test from catching missing security predicates in SQL/COUNT; real repository integration tests with fixtures containing interleaved unauthorized records are needed.

### 7.3. Testing Permission Updates and Concurrency Conditions

Additional tests should cover:

- Revoke Alice's VIEWER grant on D102 → subsequent READ/DOWNLOAD requests are denied; list/count shrink accordingly.
- Archive D104 while Alice still holds EDITOR → EDIT is denied; READ continues per the example policy.
- Change D101 owner inside a transaction → old owner loses DELETE/SHARE if no ACL remains; new owner gains permissions.
- Concurrent SHARE request and revoke/tenant-transfer request → only a decision satisfying conditions at write time is committed.
- Pass `tenantId=t-a` in a request from Mallory in tenant B → does not escalate permissions; the server verifies membership.
- Corrupted data `CONFIDENTIAL + TEAM`, unrecognized action, or policy service timeout → DENY, never fall back to permitting.

## 8. Common Mistakes and How to Address Them

| Mistake | Consequence | Fix/Verification |
| --- | --- | --- |
| Mapping owner to global `ROLE_OWNER` | Owner of one document can edit other documents | Owner is a relationship to a document ID, checked per request |
| Using `authenticated()` instead of an object policy | Any member can guess IDs and read documents | Service guard combining tenant/owner/ACL |
| Allowing tenant B's ADMIN to view tenant A | Cross-tenant data exposure | Tenant-scoped role, tenant gate before any grant |
| Giving EDITOR SHARE due to shared permission | Privilege escalation via ACL granting | Separate SHARE action, only ACTIVE owner/admin |
| Treating TEAM as anonymous/public | Internal data leaked to the Internet | TEAM is only for authenticated tenant members |
| Not checking classification when changing visibility | CONFIDENTIAL becomes TEAM | Validate on write and deny on corrupted data |
| Still allowing edits on ARCHIVED | Lifecycle bypass | Check state before action |
| ACL revoked but PERMIT cache still used | Revoked user still views/downloads | TTL, invalidation, ACL version, revoke tests |
| Filtering content after `PageRequest` | Missing IDs on page, wrong/leaked total | Visibility predicate before paging, COUNT with same scope |
| Only hiding the Delete button on the frontend | Direct HTTP DELETE still executes | Enforce at API/service/database |
| Skipping export/preview paths | Bytes leaked via secondary endpoints | Use the same policy per action/scope |
| Mock tests bypassing security chain | Tests pass while `@PreAuthorize` never runs | HTTP integration with real filter chain and proxy |
| Policy check first, database changes later | TOCTOU, unauthorized writes | Conditional UPDATE/locking/revalidate in transaction |

## 9. Handoff Checklist

A complete permission matrix must answer:

1. **Who?** Identity, membership, and per-tenant roles verified from a trusted source.
2. **Which document?** Tenant, owner, visibility, classification, status, and ACL read from trusted data; guessable IDs do not create permissions.
3. **Which action?** READ/DOWNLOAD/EDIT/DELETE/SHARE/RESTORE/CREATE have separate definitions; the more sensitive the permission, the more explicit it is.
4. **Which blocking conditions?** Wrong tenant, anonymous, invalid metadata, ARCHIVED, and revoked/expired grants are all handled before PERMIT.
5. **Does the test matrix cover enough?** Includes owner, VIEWER, EDITOR, ADMIN, nonmember, cross-tenant, TEAM, PRIVATE, CONFIDENTIAL, ARCHIVED, and malformed input.
6. **Are all surfaces covered?** Detail, list/count/search, download, preview, export, versions, background jobs, share and revoke endpoints.
7. **Is writing safe?** Share within tenant, conditional write/transaction/locking, audit, no side effects on 403/404.
8. **Is there real execution evidence?** Unit policy + repository integration + HTTP filter/method security integration + post-revocation verification.
9. **Is it maintainable?** When adding actions or document types, update the matrix and tests before deployment.

**Practical conclusion:** writing the policy as a **“subject – tenant – document – action – state – result”** table before coding helps uncover permission gaps early. In Spring Security, filters and annotations are only enforcement points; what determines correctness is a consistent policy from HTTP down to the database, verified with both positive and negative cases.

## References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): enabling `@EnableMethodSecurity`, using `@PreAuthorize` and interceptors.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `SecurityFilterChain`, matchers, and request-level authorization.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager` and authorities.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, validate authorization on each request.
