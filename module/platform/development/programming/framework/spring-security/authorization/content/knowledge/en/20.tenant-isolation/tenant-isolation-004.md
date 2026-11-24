# Combining Tenant, Subject, Role, and Resource in Authorization Decisions

## 1. The problem: a valid role does not guarantee permission on the right data

Multi-tenant Spring Security applications often start with `ROLE_READER`, `ROLE_EDITOR`, or `ROLE_ADMIN`. Yet a role may only be valid within a specific organization (tenant); the same user might be EDITOR in tenant north, READER in tenant south, and hold no membership in tenant east. Meanwhile, each document has its own tenant, owner, state, and sharing permissions.

Suppose Alice is EDITOR in north and READER in south. Document #42 resides in south, owned by Bob, and Alice was only granted READ. When Alice invokes WRITE on document 42, the system must DENY. You cannot rely on her EDITOR role from north to write data in south.

**A sound decision must combine at least four dimensions: tenant, subject, role, and resource**, while distinguishing READ/WRITE/DELETE/SHARE actions and business constraints. Each dimension adds a distinct boundary: choosing the right tenant, identifying the right actor, determining tenant-scoped functional permissions, and verifying the specific resource.

Goals of this lesson:
- Model multi-tenant authorization decision inputs using trusted data.
- Avoid confusing a tenant in URL/header with verified membership.
- Avoid colliding subject IDs across issuers.
- Separate per-tenant roles from per-object permissions.
- Use Spring Security and Spring Data JPA to protect services/queries, including non-HTTP paths.
- Understand fail-closed behavior, exception handling, caching, permission changes, and adversarial testing.

## 2. Conceptual formula for a decision

Model:

~~~text
Request:
  subject = verified identity (issuer + subject id)
  tenant  = requested workspace / organization
  action  = DOCUMENT_READ | DOCUMENT_WRITE | DOCUMENT_DELETE
  object  = document id and actual database attributes
  context = current time, delegation, device or business state

Decision:
  ALLOW only when every mandatory guard is satisfied.
~~~

A typical formula for a private document:

~~~text
ALLOW =
    authenticated(subject)
    AND tenantIsTrustedAndActive(tenant)
    AND activeMember(subject, tenant)
    AND tenantRoleAllows(subject, tenant, action)
    AND resource.id == requestedId
    AND resource.tenantId == tenant
    AND (
        isOwner(subject, resource)
        OR hasValidObjectGrant(subject, resource, action)
        OR approvedTenantAdminException(subject, tenant, resource, action)
    )
    AND resourceStateAllows(action)
~~~

This is a **logical specification**, not a built-in Java method or SpEL expression. Depending on the product, public resources or global support may be allowed, but they must be written as **explicit policies** and thoroughly tested rather than adding a broad `OR isAdmin` branch that skips tenant/resource checks.

Distinguish three questions:
1. **Capability:** Does the actor hold DOCUMENT_WRITE permission in tenant north?
2. **Object:** Does the actor hold WRITE permission on Document #42 belonging to north?
3. **State:** Is Document #42 locked or under legal hold?

A `true` answer to question 1 does not automatically make questions 2 and 3 `true`.

## 3. Which data sources are trusted?

| Dimension | Example | Valid source | Must not be treated as proof |
|---|---|---|---|
| Subject | issuer + sub | Verified Authentication/JWT, trusted identity provider | `userId` in JSON body |
| Tenant | north | Target tenant matched against server-side membership/verified claims | Self-asserted `X-Tenant-Id` header |
| Role | EDITOR in north | Tenant-bound, active, currently valid role mapping | Global `ROLE_EDITOR` when it actually belongs to south |
| Action | DOCUMENT_WRITE | Use case/endpoint defining the operation being checked | Client-chosen action string trusted blindly |
| Resource | document id 42, tenant north | Scoped DB query, ACL, and server-side state | `owner=true`/`resourceTenant=north` in payload |
| Context | time, project, classification | Server clock, trusted gateway/domain policy | Client-declared time/clearance |

A tenant ID in path, query, or header can help select the **target**, but does not verify access to that tenant. Only after checking trusted membership/entitlements may the tenant be used to route DB/schemas or query data.

The subject must come from verified authentication. If a background job calls a service without a user token, it requires a workload identity with an explicit scope and policy; never hardcode a fixed user ID to impersonate a tenant admin.

## 4. Authentication does not replace resource authorization

The Spring Security authentication pipeline can:
- Verify the JWT's signature, issuer, audience, expiry, and other constraints.
- Create an `Authentication` containing principal and authorities.
- Store authentication in `SecurityContext` for the current request.

However, a valid JWT does not prove the user owns Document #42 or still holds membership in tenant south. Object permissions can change after token issuance; roles inside a token can also be revoked.

**Never parse unverified claims to make authorization decisions.** A claim such as `tenant="north"` in a JWT is only trustworthy after the token validation pipeline passes and the application understands that claim's semantics. Even a signed claim may describe only a default tenant, rather than membership across every tenant the user wishes to access.

Keep two concepts separate:
- Tenant/issuer used to **select how to authenticate** a token in Resource Server.
- Tenant used to **determine permissions and data** for the requested resource.

One issuer may manage many tenants, and one tenant may use multiple issuers depending on architecture. Do not assume the two values are always equal.

## 5. Subject IDs must be namespaced by issuer

The `sub` claim may be unique within one issuer, yet collide across multiple issuers:

~~~text
iss=https://idp-a.example, sub=123 --> Alice
iss=https://idp-b.example, sub=123 --> Bob
~~~

If membership or ACL tables store only `subject_id="123"`, Bob risks receiving Alice's permissions by mistake. Use a composite key such as:

~~~text
SubjectKey(
  issuer = "https://idp-a.example",
  subject = "123"
)
~~~

Or map the verified issuer/subject pair to a globally unique internal actor ID. Java 17 value object example:

~~~java
public record SubjectKey(String issuer, String subject) {
    public SubjectKey {
        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("Invalid subject identity");
        }
    }
}
~~~

**Note:** the constructor validates null/blank values; **it does not verify the issuer itself**. The token-ingestion layer must authenticate the issuer and map identity before constructing a policy-trusted subject key.

Email/name should not serve as the primary subject key if they can change, be recycled, or collide across issuers. If account linking is needed, linking two subjects requires a dedicated verification and auditing workflow.

## 6. Tenant selection differs from tenant membership

A request:

~~~text
GET /tenants/north/documents/42
X-Workspace: north
~~~

shows that the client selects tenant north. It **does not prove** the actor is a member of north.

Processing flow:
1. Authenticate caller, obtain a trusted issuer+subject key.
2. Identify the requested tenant from the route or a valid context.
3. Verify the tenant exists and is active.
4. Check the actor's membership/entitlement in this tenant and confirm it is still valid.
5. Retrieve roles in **that exact tenant**.
6. Query Document #42 with a tenant filter and evaluate object permissions.
7. Only after an ALLOW result may data be returned or mutated.

Table model:

~~~text
tenant_memberships(
    subject_key,
    tenant_id,
    role_code,
    status,
    valid_from,
    valid_until
)
~~~

If a subject holds multiple roles in one tenant, store multiple rows or a separate `membership_role` table. Explicitly define expiration, suspension, revocation, project memberships, and how roles are updated.

When a request omits a tenant, an endpoint requiring a tenant should error/deny; never auto-pick the first tenant and treat that as authorization. An application using a server-side “current tenant” must verify that the previously chosen current tenant remains valid, especially if the user's membership was revoked.

## 7. Roles must be scoped by tenant

| Subject | Tenant | Role | DOCUMENT_READ | DOCUMENT_WRITE |
|---|---|---|---|---|
| Alice | north | EDITOR | Yes | Yes |
| Alice | south | READER | Yes | No |
| Bob | north | READER | Yes | No |
| Chi | south | TENANT_ADMIN | Yes | Yes |

The roles in this table are **illustrative policies**, not enums built into Spring Security. An editor may still be denied WRITE on an object because it is unshared or locked.

Ways to structure roles:
- **Per-tenant DB mapping:** query `(subject, tenant)`, filtering by active status and expiry.
- **Per-tenant scoped claims:** token carries a list of memberships with tenant IDs, verified with explicit revocation/TTL policy.
- **Current-tenant-bound authorities:** translate roles into authorities once `currentTenant` is verified; prevent reuse for another tenant.

Never use a global `ROLE_TENANT_ADMIN` to unlock all tenants when the privilege only applies in south. Distinguish `TENANT_ADMIN` from global support/system admins, and define break-glass privileges separately.

A tenant-prefixed role string like `TENANT_north_EDITOR` can encode tenant scope, yet does not replace membership validation or object permissions; such strings can also bloat authority lists when users join many workspaces.

## 8. Both role gate and object gate must pass

A design for private documents:

~~~text
tenantRoleAllows(action)
AND resource.tenantId == verifiedTenant
AND (
  subjectIsOwner(resource)
  OR activeObjectGrant(subject, resource, action)
  OR approvedTenantAdminRule
)
AND resourceStateAllows(action)
~~~

Examples:
- Alice (EDITOR in north) owns Document north #42 (status ACTIVE) → WRITE can be ALLOW.
- Alice (EDITOR in north) neither owns Document #43 nor holds a share → WRITE DENY.
- Bob (READER in north) holds a READ grant on Document #43 → READ ALLOW, WRITE DENY.
- Chi (TENANT_ADMIN in south) → cannot READ a north document without a dedicated cross-tenant policy.
- Alice holds a WRITE grant, but the document is LOCKED → DENY due to business constraint.

Do not assume `WRITE` implies `DELETE` or `SHARE`; declare permission hierarchies explicitly. Nor does an object grant automatically authorize calling tenant-administration APIs.

## 9. Resources must be fetched by ID **and** tenant

A document may have:

~~~text
Document {
  id,
  tenantId,
  ownerSubjectKey,
  projectId,
  classification,
  status,
  version
}
~~~

The same local ID 42 can appear across multiple tenants; even if IDs are globally unique, tenant scope is still needed to prevent unauthorized queries.

Safe owner-only query:

~~~sql
SELECT d.id, d.title, d.status
FROM documents d
WHERE d.id = :document_id
  AND d.tenant_id = :verified_tenant
  AND d.owner_subject_key = :verified_subject;
~~~

**The ID in the URL alone is never proof of access.** Never return `repository.findById(id)` directly to any user holding `document:read`. That is a BOLA/IDOR flaw when object authorization is missing.

If the request body carries `ownerId`, `tenantId`, or `isAdmin`, the server must verify them against the DB and identity; never treat client metadata as an authorization source.

## 10. Per-object sharing: tenant AND (owner OR grant)

A simple grant table:

~~~text
document_grants(
    tenant_id,
    document_id,
    subject_key,
    permission,
    expires_at,
    revoked_at
)
~~~

SQL query for READ:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND d.status = 'ACTIVE'
  AND (
      d.owner_subject_key = :subject
      OR EXISTS (
          SELECT 1 FROM document_grants g
          WHERE g.tenant_id = d.tenant_id
            AND g.document_id = d.id
            AND g.subject_key = :subject
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
            AND (g.expires_at IS NULL OR g.expires_at > :now)
      )
  );
~~~

Notes:
- `d.id`, `d.tenant_id`, and status sit **outside the OR parentheses**; they apply to every authorization branch.
- The grant must match tenant, ID, subject, permission, and validity.
- `EXISTS` checks whether a valid grant exists without multiplying rows.
- `:now` comes from the server clock.
- The service-level role/action gate remains mandatory. This SQL resolves object scope; **it does not know the actor's role in the tenant**.

An operator-precedence bug:

~~~sql
WHERE d.id = :id AND d.tenant_id = :tenant
  AND d.owner_subject_key = :subject
  OR EXISTS (SELECT 1 FROM document_grants g
             WHERE g.document_id = d.id
               AND g.subject_key = :subject)
~~~

Because `AND` binds tighter than `OR`, the share branch can bypass both ID and tenant checks. Tests must include a grant on another resource and a resource with the same ID in another tenant to catch this.

## 11. Spring Data JPA: derived queries by actor and tenant

Given a `Document` entity with properties `id`, `tenantId`, `ownerSubjectKey`:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository extends JpaRepository<Document, Long> {
    Optional<Document> findByIdAndTenantIdAndOwnerSubjectKey(
            Long id, String tenantId, String subjectKey);
}
~~~

This is a **Spring Data JPA integration snippet**, not standalone Java; the entity and persistence configuration must exist. Spring Data JPA builds predicates from property names.

For shared-object READ, JPQL:

~~~java
import java.time.Instant;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ReadableDocumentRepository
        extends JpaRepository<Document, Long> {

    @Query("""
        select d from Document d
        where d.id = :id
          and d.tenantId = :tenant
          and d.status = 'ACTIVE'
          and (
              d.ownerSubjectKey = :subject
              or exists (
                  select g.id from DocumentGrant g
                  where g.document = d
                    and g.tenantId = :tenant
                    and g.subjectKey = :subject
                    and g.permission = 'READ'
                    and g.revokedAt is null
                    and (g.expiresAt is null or g.expiresAt > :now)
              )
          )
        """)
    Optional<Document> findVisibleById(
            @Param("id") Long id,
            @Param("tenant") String tenant,
            @Param("subject") String subject,
            @Param("now") Instant now);
}
~~~

This code assumes `DocumentGrant` has a `document` relation and matching property names; in production, FKs/constraints must also prevent grants from referencing another tenant. JPQL `@Query` uses entity property names, not raw SQL column names.

The repository receives tenant/subject strings; ensuring those are **verified strings** is the service/resolver's responsibility. If a policy needs WRITE/DELETE, use a predicate for **that exact action** rather than reusing the READ query.

## 12. Structuring service boundaries with Spring Security

A service can verify:
- Authentication is verified.
- Actor holds active membership in the target tenant.
- Role in the target tenant permits DOCUMENT_READ.
- Document has matching tenant, owner/share permission, and valid state.

Integration example:

~~~java
import java.time.Clock;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    private final TenantActorResolver actors;
    private final TenantRolePolicy roles;
    private final ReadableDocumentRepository documents;
    private final Clock clock;
    private final DocumentMapper mapper;

    public DocumentQueryService(
            TenantActorResolver actors, TenantRolePolicy roles,
            ReadableDocumentRepository documents,
            Clock clock, DocumentMapper mapper) {
        this.actors = actors;
        this.roles = roles;
        this.documents = documents;
        this.clock = clock;
        this.mapper = mapper;
    }

    @PreAuthorize("isAuthenticated()")
    @Transactional(readOnly = true)
    public DocumentView read(String requestedTenant, Long id) {
        VerifiedTenantActor actor = actors.requireMember(requestedTenant);

        if (id == null || id <= 0
                || !roles.allows(actor.subjectKey(),
                        actor.tenantId(), "DOCUMENT_READ")) {
            throw new AccessDeniedException("Document access denied");
        }

        Document document = documents.findVisibleById(
                id, actor.tenantId(), actor.subjectKey(),
                clock.instant()
        ).orElseThrow(ResourceNotFoundException::new);

        return mapper.toView(document);
    }
}
~~~

This is **integration code**; `TenantActorResolver`, `TenantRolePolicy`, `VerifiedTenantActor`, `DocumentMapper`, `DocumentView`, `ResourceNotFoundException`, and the `Document` entity are supplied by the application.

`actors.requireMember` must extract issuer/subject from the authenticated principal and verify active tenant membership; it **must never** merely wrap the `requestedTenant` string into a “verified actor.” `roles.allows` must check roles within **actor.tenantId()**, not unconditional global roles.

`@EnableMethodSecurity` must be enabled. Calls must flow through the Spring-managed proxy so `@PreAuthorize` and transaction advice apply; self-invocation can bypass annotations in proxy mode. For resource-level policies, a maintainable approach keeps critical checks in the service and scoped queries so non-HTTP entrypoints are equally protected.

## 13. Using @PreAuthorize with a policy bean when needed

An alternative approach:

~~~java
@PreAuthorize(
    "isAuthenticated() and " +
    "@documentAccess.canRead(authentication, #tenantId, #documentId)")
public DocumentView read(String tenantId, Long documentId) {
    return documentService.readInVerifiedScope(tenantId, documentId);
}
~~~

This is an integration snippet without full classes/imports. The `documentAccess` bean must:
1. Verify authentication/issuer/subject.
2. Verify actor membership/roles in `tenantId`.
3. Look up the document by ID + tenant, then check owner/share/status.
4. Return true only when all proof is present.

Pay attention to how SpEL resolves parameter names: typically via the `-parameters` compiler flag, `@P`, or equivalent configuration. A unit test returning true from the bean does not prove the service method proxy actually invokes the bean.

Moreover, checking in `@PreAuthorize` and then updating by bare ID in the method body introduces a TOCTOU window if owner/grants change; use transactions, conditional UPDATEs, or re-checks at the mutation boundary.

## 14. HTTP filters are only the first layer

A Servlet configuration:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/tenants/*/documents/**").authenticated()
        .anyRequest().denyAll());
    return http.build();
}
~~~

This is a **Spring configuration snippet**, not a standalone Java program. It requires authentication on the endpoint without verifying whether the user belongs to the URL tenant, holds the right role, or has an ACL on the document.

Spring Security HTTP offers `hasAuthority(...)`, `hasRole(...)`, and `.access(AuthorizationManager<RequestAuthorizationContext>)` for request-level checks, yet query/resource policies usually belong at the service boundary. Do not assume an arbitrary `AuthorizationManager<String>` automatically fits `RequestAuthorizationContext`.

A clear layered architecture:

~~~text
HTTP / message / job adapter
     |
     v
Authentication + trusted subject
     |
     v
Tenant membership + tenant role
     |
     v
Resource-specific scope / ACL / business rule
     |
     v
Query / action / DTO / commit
~~~

The HTTP `SecurityFilterChain` does not protect code invoked from schedulers, message consumers, CLIs, or direct internal service calls. Those entrypoints must pass through the same policy or use a service identity with a dedicated contract.

## 15. Multiple JWT issuers: allowlist before verification

Spring Security Resource Server multi-tenancy provides `JwtIssuerAuthenticationManagerResolver`. Example from the official docs:

~~~java
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp.example.com/realm-a",
                "https://idp.example.com/realm-b");

http.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver));
~~~

This is an integration snippet requiring Spring Security Resource Server, imports, `HttpSecurity` setup, and real production issuers configured. The domains shown are illustrative only.

**Key reminders:**
- Trust only allowlisted issuers. Never construct an AuthenticationManager/decoder for an arbitrary issuer supplied by the client.
- JWTs must be verified for signature, issuer, audience, expiration, and token validity per application config.
- After validation, subject keys must include the issuer or map to a durable internal principal.
- Authenticating an issuer **does not equate to** tenant data scope; never treat the issuer directly as the resource tenant.
- Role claims inside an issuer may be organized per tenant. Never merge roles across all tenants into global authorities.
- For dynamic tenant/issuer onboarding, issuer registration must come from a trusted source, never from a self-declared `iss`.

## 16. One actor, many tenants: avoid a global current tenant

A user may switch tenants continuously. Approaches:
- Target tenant in the route, checking membership on every request.
- Server session storing `currentTenant`, verified upon switching.
- Short-lived tokens scoped to a single tenant and re-issued on context switch.

Never store a static field such as:

~~~java
static String currentTenant = "north";
~~~

and use it across requests; static variables are shared across users and threads. A `ThreadLocal` tenant context does not prove authorization either; if used, populate it from a trusted source and clear it in `finally` along every exit path, testing with connection pools and async execution.

With database-per-tenant or schema-per-tenant, routing must rely on the verified tenant. Never concatenate schema names straight from unverified headers into SQL or query strings.

## 17. When projects/groups also grant access

A document may belong to a project in which the actor is a member with READ access:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND (
      d.owner_subject_key = :subject
      OR EXISTS (
          SELECT 1
          FROM project_memberships m
          WHERE m.project_id = d.project_id
            AND m.tenant_id = d.tenant_id
            AND m.subject_key = :subject
            AND m.role_code IN ('PROJECT_VIEWER','PROJECT_EDITOR')
            AND m.status = 'ACTIVE'
      )
  );
~~~

This is a domain SQL model, not a default Spring Security table. Add business constraints if documents do not inherit project permissions or carry special classifications. For WRITE, require the appropriate project role; never copy the READ predicate verbatim.

When group memberships change, group-based grants must expire within a clear SLA. If memberships are cached inside JWTs, permissions can stay stale until expiration; provide revocation/re-check mechanisms for sensitive operations.

## 18. Resource state and explicit deny

Example policies:
- Owner has READ/WRITE, but not DELETE while the document is under legal hold.
- Tenant admin can read normal documents, whereas SECRET requires independent clearance.
- Project viewer reads only documents inheriting permissions from the project.
- A WRITE share has an expiration; after expiry, writes are blocked.
- An ARCHIVED resource forbids edits while still allowing READ.

Place mandatory conditions **outside** the `owner OR grant OR admin` branches:

~~~text
ALLOW =
  tenantValid
  AND roleAllowsAction
  AND resourceTenantMatches
  AND resourceStateAllowsAction
  AND (owner OR directGrant OR approvedAdminRule)
~~~

Do not write `owner OR (grant AND resourceStateAllows)` if the owner must also be blocked when locked. Placing `OR globalAdmin` outside the whole expression can bypass tenant, resource ID, status, and MFA when not intentionally permitted.

With Spring ACL, `ACE` grant/deny semantics and inheritance must be tested against your evaluator. Do not assume “deny always wins” for every custom implementation without checking its contract.

## 19. Public data and cross-tenant sharing are controlled exceptions

Some applications have PUBLIC documents or share links outside a tenant. These are valid use cases, but require dedicated policies:
- Resources are explicitly marked public/published.
- Never default to public if owner, tenant, or ACL is null.
- Share links use high-entropy random tokens, expiration, revocation, and explicit READ scope.
- Clients must never be able to pass `isPublic=true` to unlock a document.
- Cross-tenant access requires a valid capability rather than dropping tenant predicates system-wide.

A global support role is also an exception: it requires managed entitlements, time limits, reason codes, auditing, and potentially stronger authentication. Never confuse `TENANT_ADMIN` with `SYSTEM_ADMIN`.

## 20. Fail closed when any dimension is missing

| Missing/invalid component | Correct behavior |
|---|---|
| Authentication | Do not grant; challenge/deny |
| Unverifiable issuer or subject ID | Do not grant |
| Invalid tenant request | Never default to a broader scope |
| Revoked/expired tenant membership | DENY |
| Role does not permit action | DENY |
| Object belongs to another tenant | DENY or 404 per API |
| Object grant missing/expired/revoked | DENY |
| Owner field null violating schema | Never infer public |
| Business state LOCKED | DENY locked operation |
| ACL backend timeout/no decision | Do not execute; return technical error or controlled deny |
| Permission cache miss | Query trusted source or deny, never assume allow |

A SQL anti-pattern:

~~~sql
WHERE id = :id
  AND (:tenant IS NULL OR tenant_id = :tenant)
  AND (:subject IS NULL OR owner_subject_key = :subject)
~~~

If tenant/subject is null, the security guard turns into an optional filter, easily returning out-of-scope data. For data authorization, scope is **never optional**.

Custom `AuthorizationManager`s can return `null` to abstain; **abstain is not a negative decision**. For mandatory rules, avoid returning null when membership/ACL is absent unless composition is explicitly designed and tested to fail closed.

## 21. API responses and avoiding tenant leaks

Typically:
- **401/challenge** when unauthenticated.
- **403** when authenticated, lacking functional permissions or denied by policy where disclosure is appropriate.
- **404** for resources absent from the actor's permitted set, avoiding confirming a cross-tenant document exists.
- **5xx/503** when the permission/backend service is unavailable, with zero side effects.

These are API design choices, not HTTP codes Spring automatically assigns to every exception. `ExceptionTranslationFilter` handles security exceptions within its scope; infrastructure failures need dedicated exception mapping.

Never call an unscoped `findById(id)` just to return a message like “document belongs to tenant south, owned by Bob”; that message itself leaks data. Internal audits should log verified subject, tenant, action, permitted ID, result, policy version, and correlation ID; never log raw tokens, ACLs, or unauthorized content.

## 22. Standalone Java 17: deciding across all four dimensions

The following program runs on JDK 17 without Spring. It models **issuer-namespaced subjects**, per-tenant roles, object ownership, document/action READ grants, locked state, and default deny.

Create `TenantDecisionDemo.java`:

~~~java
import java.util.Set;
import java.util.stream.Collectors;

public class TenantDecisionDemo {
    enum Role { READER, EDITOR, TENANT_ADMIN }
    enum Action { READ, WRITE, DELETE }

    record Membership(String tenant, Role role) { }

    record Actor(
            String issuer, String subject,
            Set<Membership> memberships) {
        String key() { return issuer + "|" + subject; }
    }

    record Document(
            long id, String tenant, String ownerKey, boolean locked) { }

    record Grant(
            String tenant, long documentId,
            String subjectKey, Action action) { }

    static boolean roleAllows(Role role, Action action) {
        return switch (role) {
            case READER -> action == Action.READ;
            case EDITOR -> action == Action.READ || action == Action.WRITE;
            case TENANT_ADMIN -> true;
        };
    }

    static boolean allowed(
            Actor actor, Document document,
            Action action, Set<Grant> grants) {

        if (actor == null || document == null || action == null
                || grants == null || actor.memberships() == null
                || actor.issuer() == null || actor.issuer().isBlank()
                || actor.subject() == null || actor.subject().isBlank()
                || document.id() <= 0
                || document.tenant() == null || document.tenant().isBlank()
                || document.ownerKey() == null) {
            return false;
        }

        Set<Role> roles = actor.memberships().stream()
                .filter(m -> m != null
                        && document.tenant().equals(m.tenant()))
                .map(Membership::role)
                .filter(r -> r != null)
                .collect(Collectors.toSet());

        if (roles.stream().noneMatch(r -> roleAllows(r, action))) {
            return false;
        }

        if (document.locked() && action != Action.READ) {
            return false;
        }

        boolean owner = document.ownerKey().equals(actor.key());
        boolean admin = roles.contains(Role.TENANT_ADMIN);
        boolean shared = grants.contains(new Grant(
                document.tenant(), document.id(), actor.key(), action));

        return owner || admin || shared;
    }

    public static void main(String[] args) {
        Document document =
                new Document(42, "north", "issuerA|an", false);
        Document locked =
                new Document(43, "north", "issuerA|an", true);

        Actor an = new Actor("issuerA", "an",
                Set.of(new Membership("north", Role.EDITOR)));
        Actor binh = new Actor("issuerA", "binh",
                Set.of(new Membership("north", Role.READER)));
        Actor chi = new Actor("issuerA", "chi",
                Set.of(new Membership("north", Role.EDITOR)));
        Actor southAdmin = new Actor("issuerA", "admin",
                Set.of(new Membership("south", Role.TENANT_ADMIN)));
        Actor otherIssuerAn = new Actor("issuerB", "an",
                Set.of(new Membership("north", Role.EDITOR)));

        Set<Grant> grants = Set.of(
                new Grant("north", 42, "issuerA|binh", Action.READ));

        System.out.println("owner-write="
                + allowed(an, document, Action.WRITE, grants));
        System.out.println("shared-read="
                + allowed(binh, document, Action.READ, grants));
        System.out.println("shared-write="
                + allowed(binh, document, Action.WRITE, grants));
        System.out.println("unshared-editor="
                + allowed(chi, document, Action.WRITE, grants));
        System.out.println("other-tenant-admin="
                + allowed(southAdmin, document, Action.READ, grants));
        System.out.println("same-sub-other-issuer="
                + allowed(otherIssuerAn, document, Action.WRITE, grants));
        System.out.println("locked-owner-write="
                + allowed(an, locked, Action.WRITE, grants));
        System.out.println("after-revoke-read="
                + allowed(binh, document, Action.READ, Set.of()));
        System.out.println("missing-actor="
                + allowed(null, document, Action.READ, grants));
    }
}
~~~

Run:

~~~bash
javac TenantDecisionDemo.java
java TenantDecisionDemo
~~~

Exact stdout:

~~~text
owner-write=true
shared-read=true
shared-write=false
unshared-editor=false
other-tenant-admin=false
same-sub-other-issuer=false
locked-owner-write=false
after-revoke-read=false
missing-actor=false
~~~

Reading the output:
- An is the owner and EDITOR in north, so WRITE succeeds while the document is ACTIVE/unlocked.
- Binh holds a READ share and READER role in north; WRITE remains blocked.
- Chi holds EDITOR, but is neither owner nor grantee, so Chi cannot edit An's document.
- The south tenant admin has no matching role in north.
- `issuerB|an` differs from `issuerA|an` despite sharing `sub="an"`.
- A locked document blocks WRITE even for the owner under this example policy.
- Revoking a grant or missing an actor both yield DENY.

**Limitations:** This is an in-memory simulation without JWT validation, databases, transactions, role expiration, ACL inheritance, or caching. Real domain code must source actors/memberships/grants from verified origins and define a revocation policy.

## 23. Time-of-use permission consistency: TOCTOU

A role/ACL decision valid at T1 may no longer hold at T2:

~~~text
T1: Alice has EDITOR in north and a WRITE grant on document 42.
T2: Admin revokes membership/grant or moves the document's tenant.
T3: Alice uses the stale cached decision to UPDATE document 42.
~~~

For owner-only updates, use a guarded UPDATE:

~~~sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :id
  AND tenant_id = :verified_tenant
  AND owner_subject_key = :verified_subject
  AND status = 'ACTIVE'
  AND version = :expected_version;
~~~

Check affected rows: 1 indicates one updated record; 0 means no record simultaneously matched ID/tenant/owner/status/version, and **must never return success**.

When permissions live in a separate `document_grants` table or remote policy service, read/lock/version/re-check as needed for your consistency guarantee. `@Transactional` does not automatically span external non-DB services. Nor does `@Version` on the document increment when a grant row in another table is revoked. Test concurrency interleaving with real locks/latches to prove UPDATE/DELETE paths do not act on out-of-contract stale permissions.

## 24. Caching, stale tokens, and revocation

A permission cache should key on every relevant dimension, for example:

~~~text
(issuer, subject, tenant, resourceType, resourceId,
 action, policyVersion)
~~~

This is an **illustrative model**, not a Spring API class. Depending on the domain, you may also need group/ACL revision, resource state, token expiry, and other context. Keying a cache solely by `resourceId` or `subject` is dangerous in multi-tenant/multi-issuer systems.

Events that may require invalidation:
- User leaves a tenant, is suspended, or is downgraded.
- Document owner, project membership, or resource tenant changes.
- Grants are issued/revoked, or a document is locked.
- Business policies or issuer trust change.
- Sessions/tokens are revoked.

If a JWT carries old roles and has not expired, instant revocation cannot be guaranteed when relying solely on tokens. Define a **revocation SLA**, TTL, revision check, and which operations must re-evaluate permissions against a trusted source.

Cache misses or permission backend timeouts must never turn into ALLOW; fail closed and report operational errors appropriately.

## 25. Tenant isolation in the database and non-HTTP paths

Common architectures:
- Shared DB/shared schema, every row carries a tenant ID and every query is scoped.
- Shared DB/separate schemas, datasource/schema routing based on trusted tenant.
- Database per tenant, with dedicated routing, migrations, and cache isolation.
- Database Row-Level Security (RLS) as a defense-in-depth layer when properly configured.

Whichever architecture you choose:
- Validate membership before routing datasource/schema.
- Read resource tenant from the DB, never the client body.
- Namespace owner/grant subjects by issuer.
- Authorize per action rather than using an ambiguous `canAccess` boolean.
- Keep caches/search indexes/lists/counts/exports/downloads within the same tenant scope.
- Reset connection pool/session context properly between requests when using RLS/schema routing.

A classic bug: the detail API is scoped, yet an export job calls `findAllByStatus("ACTIVE")` and returns every tenant's data. Protection must live in services/repositories and asynchronous/message/batch paths, not merely HTTP controllers.

## 26. Testing the tenant, subject, role, and resource matrix

| Scenario | Expectation |
|---|---|
| Owner, right tenant, role allows, valid state | ALLOW |
| User has right role, but neither owner nor grantee | DENY |
| User is EDITOR in tenant A, resource belongs to B | DENY |
| User is READER in B, requests WRITE | DENY |
| User is READER in B with READ grant on the object | READ ALLOW |
| Role TENANT_ADMIN of A, document in B | DENY |
| Two issuers share the same subject string | Never confuse actors |
| Role/membership revoked/expired | DENY within SLA |
| Resource changes tenant/owner | Inaccessible via old scope |
| READ-only grant, caller requests DELETE | DENY |
| Grant for a different document ID | Does not authorize requested object |
| Grant expired, revoked, or wrong tenant | DENY |
| Document LOCKED, owner requests WRITE | DENY |
| Missing authentication/tenant/subject | Do not grant |
| Permission backend null/timeout | No side effects |
| Mis-parenthesized SQL OR | Tests must catch cross-ID/cross-tenant leaks |
| Global support with valid capability | Strictly within designed scope/time/audit |

Write **integration tests** with real Spring Security:
1. HTTP SecurityFilterChain has proper matchers and fallback.
2. `@EnableMethodSecurity` is enabled and services are called via Spring-managed proxies.
3. Test principals include issuer + subject + tenant membership per contract; default `@WithMockUser` does not create custom tenant claims.
4. JPA queries verify tenant and resource ID rather than relying on client DTOs.
5. Test duplicate tenant-local IDs and colliding subject IDs across issuers.
6. Role, ACL, owner, project, and resource status independently produce the right outcomes.
7. Revoked grants/roles do not produce cached ALLOWs beyond SLA.
8. List/count/search/export/download enforce the same scope as detail endpoints.
9. Denied WRITE/DELETE leaves databases, events, and files untouched.
10. Message workers and direct service invocations also traverse valid policies.

Do not assert only HTTP 403. Inspect post-request state, audit records, caches, and returned record counts to prove zero data leakage.

## 27. Common mistakes

**1. Using a global ADMIN role for tenant admins.** Local privilege opens other tenants. **Fix:** tenant-bound roles, separate global capabilities.

**2. Treating X-Tenant-Id as membership.** Clients can swap tenants. **Fix:** validate target tenant against trusted memberships.

**3. Using sub without issuer namespace.** Subjects collide across identity providers. **Fix:** validated issuer+subject or internal principal.

**4. Checking only role while skipping owner/ACL.** An EDITOR modifies someone else's object. **Fix:** explicit object permissions.

**5. Valid role, wrong resource tenant.** Cross-tenant access. **Fix:** query ID AND tenant.

**6. Using a READ share for WRITE.** Lower privileges trigger mutations. **Fix:** action-specific policies.

**7. Missing parentheses in SQL AND/OR.** The grant branch skips tenant/ID checks. **Fix:** place all mandatory guards outside OR.

**8. Null tenant/subject acting as an optional SQL filter.** Expands scope when identity is missing. **Fix:** mandatory scope, fail closed.

**9. Caching solely by document ID.** Another tenant/subject's ALLOW gets reused. **Fix:** complete keys + invalidation.

**10. Protecting only HTTP while forgetting jobs/exports.** Services lack data authorization. **Fix:** enforce policy at service/query boundaries.

**11. Assuming valid JWT expiry means unchanged membership.** Tokens go stale after revocation. **Fix:** TTL/revision/re-check per risk.

**12. Assuming @Transactional prevents all permission races.** External ACL backends can still change. **Fix:** consistency protocols or guarded mutations.

**13. Allowing access when the permission service fails.** Fail-open. **Fix:** refuse actions unless full authorization is verified.

**14. Inferring public when owner/ACL is null.** Corrupted data becomes public access. **Fix:** explicit public policies.

## 28. Pre-merge design checklist

- [ ] Subject is authenticated and issuer-namespaced if needed.
- [ ] Target tenant is checked against active membership, not just headers/paths.
- [ ] Roles/actions are tenant-scoped; TENANT_ADMIN is not confused with global admin.
- [ ] Resource ID, tenant, owner, and state come from trusted server sources.
- [ ] Both role gate and object gate are enforced.
- [ ] READ/WRITE/DELETE/SHARE use separate permissions.
- [ ] SQL/JPQL enforces ID + tenant + (owner OR grant) with proper parentheses.
- [ ] Expired/revoked grants, stale group roles, and tenant moves are tested.
- [ ] Missing authentication/membership/ACL or backend errors fail closed.
- [ ] Client-declared `userId`, `ownerId`, `tenantId`, or `isAdmin` are never trusted.
- [ ] Method security runs through proxies, and policies cover non-HTTP entrypoints.
- [ ] List/count/export/download and caches isolate tenants properly.
- [ ] Side effects are guarded and tested not to occur when denied.
- [ ] Cache invalidation/revocation SLA and token-free auditing are in place.
- [ ] Tests cover colliding IDs across tenants, colliding subs across issuers, and varying roles across tenants.
- [ ] Global/public/cross-tenant access is an explicitly scoped and audited exception.

**Conclusion:** Base every decision on **the right authenticated subject**, **the right tenant the subject is allowed to join**, **roles permitting the action in that tenant**, and **the specific resource with its current owner/ACL/state**. Spring Security provides authentication and interception; your application must provide tenant membership, role scoping, object policies, query guards, and tests so cross-tenant access is never opened.

## References

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, method interceptors, and policy beans.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request authorization, `AuthorizationManager`, `hasAuthority`.
- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): manager decisions and boundaries.
- [Spring Security – OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): issuer resolvers, trusted issuers, and multi-tenant authentication.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT verification and issuer validation.
- [Spring Data JPA – JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived queries, `@Query`, and parameter binding.
- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): per-object permissions.
- [OWASP API Security Top 10 (2023) – BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): preventing unauthorized data access via object IDs.
