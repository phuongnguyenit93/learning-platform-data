# Querying by ID Combined with Owner or Permitted Scope

## 1. Goal: ID Identifies the Target, It Does Not Prove Permission

In a Spring Security application, a request like `GET /documents/42` only indicates which object is being requested. If the service calls `findById(42)` and returns the entity, a user can guess or swap IDs to access someone else's document. This is a form of **Broken Object Level Authorization (BOLA)**, commonly manifested as IDOR.

For private data, the question is not just "does document 42 exist?", but **does document 42 belong to the set of resources the current actor is allowed to access?**. A query with a permission predicate expresses this directly at the data layer:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :requested_id
  AND d.tenant_id = :verified_tenant
  AND d.owner_user_id = :verified_actor;
~~~

When sharing or group permissions exist, the owner portion can expand to `(owner OR valid share OR verified project membership)`. However, mandatory conditions on ID, tenant, data state, and action authority must never drop out of scope.

**Design invariant:** a query-by-ID request may only return the exact requested object **and** only if it falls within the caller's permitted scope. Knowing or guessing the right ID is not enough. If authentication, tenant, owner, or required grant evidence is missing, the system must deny—never falling back to client-claimed data.

This Knowledge unit covers the owner-only query model, extensions with shares/ACLs/groups, Spring Data JPA syntax, READ/WRITE/DELETE distinctions, atomic conditional updates, 404/403 handling, concurrency, pagination, a Java 17 example, and a testing matrix.

## 2. Distinguishing Permission Layers

| Layer | Example | Why Is It Insufficient Alone? |
|---|---|---|
| Authentication | Actor is An, authenticated | An can still guess Binh's document ID |
| Function-level authority | `document:read` | Allows calling the read feature, not reading every document |
| Tenant scope | Actor belongs to tenant north | Within north there are multiple owners and groups |
| Ownership | `document.ownerUserId = an` | Sufficient for an owner-only policy, but cannot represent sharing |
| Object grant/ACL | Binh has READ on document 42 | Must check exact object, action, tenant, and validity |
| Project membership | An has READ permission in the document's project | Membership can be revoked or restricted |
| Business state | Document is not under embargo/legal hold | State conditions do not automatically follow authority or owner |

A common specification:

~~~text
ALLOW_READ =
  isAuthenticated(actor)
  AND hasAuthority(actor, "document:read")
  AND resource.id == requestedId
  AND resource.tenantId == actor.verifiedTenant
  AND (
      resource.ownerId == actor.id
      OR validShare(actor, resource, READ)
      OR validProjectScope(actor, resource, READ)
  )
  AND resource.isReadable()
~~~

This is **conceptual logic**, not standalone Java code. The decisive point is `ID AND tenant AND (owner OR allowedScope)`, not `ID AND tenant AND owner OR allowedScope`.

A separate design is needed if a super-admin is genuinely permitted to cross a scope. An `isAdmin=true` flag sent from the request is not proof of authorization.

## 3. Dangerous Pattern: Finding an Object and Returning Immediately

~~~java
@GetMapping("/documents/{id}")
public DocumentDto view(@PathVariable Long id) {
    return mapper.toDto(repository.findById(id).orElseThrow());
}
~~~

The Spring MVC integration code above **has no per-object protection**. An HTTP rule like `authenticated()` or `hasAuthority('document:read')` does not check owner or tenant.

Another style:

~~~java
Document document = repository.findById(id).orElseThrow();
if (!actor.userId().equals(document.getOwnerUserId())) {
    throw new AccessDeniedException("Forbidden");
}
return mapper.toDto(document);
~~~

Checking ownership after loading can be correct if the guard is strictly enforced, but out-of-scope data has already been fetched into the persistence context, and other code paths easily forget the guard. Scoped queries offer clear advantages: filtering right at the database, never returning unauthorized objects to the caller, repository code clearly expressing intent, easy testing for wrong ID/tenant/owner, and easy extension to list queries.

That does not mean every application must force every complex policy into a single SQL statement. When a policy requires computation outside the DB, you must still structure safe service authorization; however, for ownership and relational-table permissions, scoped queries are usually strong and easy to review.

## 4. Simplest Level: ID + tenant + owner

Illustrative schema:

~~~sql
CREATE TABLE documents (
    id            BIGINT PRIMARY KEY,
    tenant_id     VARCHAR(64) NOT NULL,
    owner_user_id VARCHAR(128) NOT NULL,
    title         VARCHAR(255) NOT NULL,
    status        VARCHAR(32) NOT NULL,
    version       BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_documents_tenant_owner
    ON documents (tenant_id, owner_user_id, id);
~~~

If IDs are unique only **within each tenant** rather than globally unique, you must use appropriate primary/unique keys and queries like `(tenant_id, id)`; do not assume `id` alone uniquely identifies a document system-wide.

Owner-only query:

~~~sql
SELECT d.id, d.tenant_id, d.owner_user_id, d.title
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND d.owner_user_id = :actor;
~~~

Actor An in tenant north requests Binh's document, also in north: zero rows. An requests a document in tenant south: zero rows. When no data is returned, the service cannot conclude the document does not exist anywhere in the DB; it only knows it is **not present in the set the actor is permitted to see**.

Never take `:actor` or `:tenant` from a client-supplied payload and treat it as identity. They must come from the security context or a trusted authentication resolver layer.

### Spring Data Derived Query

If the Java entity has properties `id`, `tenantId`, `ownerUserId`:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository extends JpaRepository<Document, Long> {

    Optional<Document> findByIdAndTenantIdAndOwnerUserId(
            Long id, String tenantId, String ownerUserId);
}
~~~

Spring Data JPA builds predicates from property names and `And` keywords. `Optional.empty()` takes the place of fetching out-of-scope objects.

Note that the inherited `findById` repository method is a specially handled identifier method. Do not try to override it to add permissions and expect every caller to automatically inherit the same scope; create a scoped method with its own clear name and contract.

## 5. Requiring a Verified Actor

A data type to pass scope through services:

~~~java
public record VerifiedActor(String userId, String tenantId) {
    public VerifiedActor {
        if (userId == null || userId.isBlank()
                || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing actor identity");
        }
    }
}
~~~

**Naming it VerifiedActor does not make the data trustworthy.** Only a controlled infrastructure layer may construct this record from an authentication/session/JWT whose issuer, audience, signature, and required constraints have been verified. Do not build it from `request.userId()` or `request.tenantId()` and pass it into the repository as if it were verified.

Owner-only service pattern:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    private final DocumentRepository repository;
    private final CurrentActorResolver actorResolver;
    private final DocumentMapper mapper;

    public DocumentQueryService(DocumentRepository repository,
            CurrentActorResolver actorResolver, DocumentMapper mapper) {
        this.repository = repository;
        this.actorResolver = actorResolver;
        this.mapper = mapper;
    }

    @PreAuthorize("isAuthenticated() and hasAuthority('document:read')")
    @Transactional(readOnly = true)
    public DocumentDto readOwned(Long id) {
        VerifiedActor actor = actorResolver.requireCurrentActor();

        if (id == null || id <= 0) {
            throw new IllegalArgumentException("Invalid ID");
        }

        Document document = repository
                .findByIdAndTenantIdAndOwnerUserId(
                        id, actor.tenantId(), actor.userId())
                .orElseThrow(ResourceNotFoundException::new);
        return mapper.toDto(document);
    }
}
~~~

This is a **Spring project snippet**, not a standalone Java 17 file: it requires the application's `Document`, `CurrentActorResolver`, `DocumentMapper`, `DocumentDto`, and exception types.

Three protection layers:
1. `@PreAuthorize` checks action authority before the method body **when the call passes through a Spring-managed proxy** and method security is enabled.
2. `CurrentActorResolver` obtains the verified user/tenant, never accepting scope choices from the request body.
3. The repository only returns objects matching ID, tenant, and owner; the service only maps objects returned by the query.

`@Transactional(readOnly=true)` declares a read transaction and can optimize queries, **not automatically grant or restrict permissions**. For HTTP controllers, keep the adapter thin and call this exact use-case bean.

## 6. Adding Share Permissions: ID + tenant + (owner OR grant)

When documents allow sharing, a grant table may suffice:

~~~sql
CREATE TABLE document_grants (
    id              BIGINT PRIMARY KEY,
    document_id     BIGINT NOT NULL,
    grantee_user_id VARCHAR(128) NOT NULL,
    permission      VARCHAR(30) NOT NULL,
    revoked_at      TIMESTAMP NULL,
    expires_at      TIMESTAMP NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX idx_document_grant_read
    ON document_grants (document_id, grantee_user_id, permission);
~~~

This is an illustrative schema. In a multi-tenant system, ensure foreign keys/constraints or business guards prevent attaching grants across tenants. A product with simple READ grants does not necessarily need to deploy the full Spring Security ACL module.

Query:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :verified_tenant
  AND (
      d.owner_user_id = :verified_actor
      OR EXISTS (
          SELECT 1
          FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee_user_id = :verified_actor
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
            AND (g.expires_at IS NULL OR g.expires_at > :now)
      )
  );
~~~

Reading the conditions from outside in:
- `d.id=:id` applies to every permission branch.
- `d.tenant_id=:verified_tenant` also applies to both owner and share.
- Inside the parentheses, owner **or** valid READ grant.
- `EXISTS` does not duplicate documents if multiple grants exist.
- Grant expiration is evaluated using the server clock, never a client-supplied timestamp parameter.
- READ permission does not automatically imply WRITE/DELETE; if the business defines a permission hierarchy, express it explicitly.

Grants must bind to the exact object, actor, action, and validity; do not merely check whether the actor has ever held a permission on *any* document.

## 7. Spring Data JPA `@Query` with `EXISTS`

Assuming entity `DocumentGrant` has properties `document` linking to `Document`, `granteeUserId`, `permission`, `revokedAt`, and `expiresAt`:

~~~java
import java.time.Instant;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentRepository extends JpaRepository<Document, Long> {

    @Query("""
        select d
        from Document d
        where d.id = :id
          and d.tenantId = :tenant
          and (
              d.ownerUserId = :actor
              or exists (
                  select g.id from DocumentGrant g
                  where g.document = d
                    and g.granteeUserId = :actor
                    and g.permission = 'READ'
                    and g.revokedAt is null
                    and (g.expiresAt is null or g.expiresAt > :now)
              )
          )
        """)
    Optional<Document> findReadableById(
            @Param("id") Long id,
            @Param("tenant") String tenant,
            @Param("actor") String actor,
            @Param("now") Instant now);
}
~~~

JPQL uses **Java entity/property names**, not table/column names. In a real project, the `DocumentGrant.document` mapping and properties must actually exist, the method returns `Optional`, and parameters consistently use `@Param`. This is a JPA integration snippet, not standalone Java.

Service call:

~~~java
@PreAuthorize("isAuthenticated() and hasAuthority('document:read')")
@Transactional(readOnly = true)
public DocumentDto readVisible(Long id) {
    VerifiedActor actor = actorResolver.requireCurrentActor();
    if (id == null || id <= 0) {
        throw new IllegalArgumentException("Invalid ID");
    }
    Document d = repository.findReadableById(
            id, actor.tenantId(), actor.userId(), clock.instant())
            .orElseThrow(ResourceNotFoundException::new);
    return mapper.toDto(d);
}
~~~

The snippet assumes the service has `clock: Clock`, `repository`, `actorResolver`, and `mapper` injected. Using an explicit server clock makes testing expired grants easier. `EXISTS` suits detail lookups because we only need to know whether a matching grant exists; using JOIN can duplicate rows when multiple grants exist and requires care with DISTINCT/counts.

## 8. `OR` Parentheses Are Part of the Security Mechanism

Wrong snippet:

~~~sql
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND d.owner_user_id = :actor
  OR EXISTS (
      SELECT 1 FROM document_grants g
      WHERE g.document_id = d.id
        AND g.grantee_user_id = :actor
  )
~~~

Because `AND` has higher precedence than `OR`, the condition is equivalent to:

~~~text
(id=requested AND tenant=verified AND owner=actor)
OR (hasSomeGrantForActorOnThisRow)
~~~

The share branch is no longer constrained by ID or tenant. The query may return documents with **a different ID than requested**, or even from a different tenant if grant data and guards are insufficient.

Correct snippet:

~~~sql
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND (
      d.owner_user_id = :actor
      OR EXISTS (...)
  )
~~~

With an admin branch, a sound condition might be:

~~~text
id AND verifiedTenant AND
    (owner OR validShare OR trustedTenantAdminPermission)
~~~

Do not write `id AND tenant OR admin`, because the admin branch would bypass both the ID and tenant barriers. Admin flags must be determined by the security context/policy service, never read from the request like `?admin=true`.

During code review, draw the logic tree or write adversarial tests to prove every OR branch sits inside the mandatory constraints.

## 9. Project, Group, or Organization Permissions

If a document belongs to a project where the user has READ permission, scope can be determined via membership:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND (
      d.owner_user_id = :actor
      OR EXISTS (
          SELECT 1 FROM project_memberships m
          WHERE m.project_id = d.project_id
            AND m.tenant_id = d.tenant_id
            AND m.user_id = :actor
            AND m.can_read_documents = TRUE
            AND m.revoked_at IS NULL
      )
  );
~~~

The `project_memberships` table is an illustrative domain model, not a default Spring table. Membership rules must be verified at query time; do not accept a self-declared list of project IDs in the request and treat it as authorization.

If a project has roles like VIEWER/EDITOR while a specific document has a legal hold or confidential override, add business predicates. When group hierarchies nest across multiple levels with complex relationships, you can use an ACL or policy engine/ReBAC, while still keeping tenant and ID boundaries clear.

You must align on: if an actor leaves a project, how long until the membership cache updates? A token carrying stale project roles can cause stale decisions; expiry/revocation must match the risk.

## 10. Public Access Is an Explicit Policy Branch

Documents can be allowed to become public via a managed flag:

~~~sql
AND (
    d.owner_user_id = :actor
    OR EXISTS (...validShare...)
    OR d.visibility = 'PUBLIC'
)
~~~

However, a public document may still be restricted by status PUBLISHED, expiry, or tenant constraints. If the product allows cross-tenant public access, design a dedicated boundary rather than blindly adding `OR visibility='PUBLIC'` to every private query.

**Do not equate null with public.** Anti-patterns like treating `owner_user_id IS NULL` or `tenant_id IS NULL` as public conditions can turn data errors into open access.

Shared links via secret tokens are another policy: tokens need sufficient entropy, expiry, revocation, and replay protection as required; a client-sent string carries no inherent permission unless verified.

## 11. 404, 403, and Avoiding Resource Existence Leaks

When `findReadableById` returns empty, it could be because:
- The ID does not exist.
- The ID exists in another tenant.
- The ID belongs to the tenant, but the actor is not the owner.
- No valid share exists.
- The share is expired/revoked.
- The document state does not allow reading.

For private data APIs, it is common to return **404** for resources outside the visible set so the existence of an ID is not confirmed. `403` is appropriate if the policy intentionally denies and revealing the object/group poses no risk; standardization requirements vary by product.

Common cases:
- Unauthenticated → 401/challenge or login redirect depending on the authentication stack.
- Missing functional authority → 403.
- ID not found within the **permitted scope** → 404.
- Database/permission backend failure → appropriate infrastructure error (typically 5xx), **do not perform the action**.

Do not run an unscoped `repository.findById(id)` again just to return a message saying "document exists but belongs to Binh", because that reply itself leaks data.

If operations need to know why access was denied, audit with the actor/correlation ID and a safe reason code; never expose unauthorized owner/tenant or content details in the API response.

## 12. READ Query Does Not Imply WRITE Permission

A user with a READ grant must not automatically gain edit permission. Do not use `findReadableById` in a write service and then call `document.rename(...)`.

For owner-only WRITE:

~~~java
@PreAuthorize("isAuthenticated() and hasAuthority('document:write')")
@Transactional
public void renameOwned(Long id, String newTitle) {
    VerifiedActor actor = actorResolver.requireCurrentActor();

    if (newTitle == null || newTitle.isBlank()) {
        throw new IllegalArgumentException("Invalid title");
    }

    Document d = repository.findByIdAndTenantIdAndOwnerUserId(
            id, actor.tenantId(), actor.userId())
            .orElseThrow(ResourceNotFoundException::new);

    d.rename(newTitle);
}
~~~

This is a Spring/JPA integration snippet. `Document.rename` is domain logic, and JPA dirty checking relies on a managed entity within a transaction. If non-owners are granted WRITE, create a matching query/policy **for WRITE** rather than reusing the READ permission predicate.

Beyond object policy, you may need to check LOCKED or DRAFT status, or delegated permissions, even for the owner.

## 13. Conditional UPDATE: Checking Permission Within the Write Statement

One owner-only approach is performing an UPDATE with the predicate `ID + tenant + owner + version` in the same statement. Spring Data JPA:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentWriteRepository
        extends JpaRepository<Document, Long> {

    @Modifying
    @Query("""
        update Document d
           set d.title = :title,
               d.version = d.version + 1
         where d.id = :id
           and d.tenantId = :tenant
           and d.ownerUserId = :actor
           and d.version = :expectedVersion
        """)
    int renameOwnedIfVersionMatches(
            @Param("id") Long id,
            @Param("tenant") String tenant,
            @Param("actor") String actor,
            @Param("title") String title,
            @Param("expectedVersion") long expectedVersion);
}
~~~

Assuming `Document.version` is a numeric version with matching property mapping. This is **integration repository code** and must run inside a write transaction in the service.

- Return `int` represents the number of updated rows.
- `1` indicates one document satisfied all conditions.
- `0` may mean missing ID, wrong tenant/owner, or stale version; never treat as success.
- `>1` is abnormal for a unique ID and requires error/query integrity handling.
- JPQL bulk updates do not automatically apply optimistic-lock checking and lifecycle callbacks like a managed entity update; the example explicitly uses `d.version = :expectedVersion` and `d.version = d.version+1`.
- `@Modifying` only applies to query methods annotated with `@Query`; bulk queries can leave currently managed entities stale. Do not enable `clearAutomatically` indiscriminately if the persistence context holds unflushed changes.

In the service:

~~~java
int updated = writeRepository.renameOwnedIfVersionMatches(
        id, actor.tenantId(), actor.userId(), title, expectedVersion);

if (updated != 1) {
    throw new ResourceNotFoundOrConflictException();
}
~~~

The exception here is an application type. Returning an accurate 404/409 without leaking data requires its own policy: `0` alone does not prove only a stale version. Crucially, never return 204 success when zero rows changed.

## 14. Shared WRITE Must Have Its Own Predicate

When the policy allows users granted WRITE to edit a document:

~~~sql
UPDATE documents
SET title = :title
WHERE id = :id
  AND tenant_id = :tenant
  AND (
      owner_user_id = :actor
      OR EXISTS (
          SELECT 1 FROM document_grants g
          WHERE g.document_id = documents.id
            AND g.grantee_user_id = :actor
            AND g.permission = 'WRITE'
            AND g.revoked_at IS NULL
            AND (g.expires_at IS NULL OR g.expires_at > :now)
      )
  );
~~~

This is illustrative SQL; table names, parameter types, and aliases may need adjustment for the actual database dialect. If optimistic concurrency is needed, add a version guard/increment.

Never use `permission='READ'` for UPDATE just because the user can open the edit page. If WRITE implies READ by business contract, define the inheritance direction explicitly; never assume DELETE/SHARE also follow WRITE.

If permissions are stored in an external ACL service outside the DB, you cannot use the same `EXISTS` SQL unless a permission index exists in the DB. In that case, you need a service guard before mutation, transactional consistency/capability expiry, and fail-closed behavior when the permission backend is unavailable.

## 15. TOCTOU: Between Check and Execution

Time-of-check/time-of-use:
~~~text
T1: user has WRITE permission on document 42
T2: admin revokes the grant
T3: user updates document 42
~~~

If checked at T1 but updated at T3 via an unscoped `save(entity)`, there is a risk that permission was revoked in between.

An UPDATE statement with `EXISTS` permission in the same DB narrows the check–write window, though isolation levels and concurrent transactions still need evaluation. If permissions live outside the database, in caches, or in an IAM service, this constraint is harder.

Mitigations by risk level:
1. Check permissions close to write time within the appropriate transaction.
2. Use conditional UPDATE with scoped predicates, expected versions, or locking when needed.
3. Ensure grant/revoke has proper invalidation and auditing.
4. For highly sensitive tasks, re-verify before irreversible side effects or use capabilities with explicit expiry/revocation.
5. Never swallow `AccessDeniedException` and allow the transaction to keep committing other changes.

`@Transactional` is not authorization, nor does it guarantee consistency across an external permission service; choose isolation/constraints based on actual impact.

## 16. Deleting by ID Must Have a DELETE Policy

Calling `repository.deleteById(id)` from an endpoint accepting an arbitrary ID is dangerous without guards. DELETE may require:
- Authority `document:delete`.
- ID, tenant, owner, or explicit DELETE grant.
- Legal hold, lifecycle, and retention checks.
- Transaction/cascade/outbox/file cleanup, ACL/cache invalidation.
- Auditing the actor.

One approach is loading the entity via a **deletable-scope** query, checking state, and removing the managed entity. Another is conditional DELETE with `WHERE id AND tenant AND owner/version`, checking the row count, and handling lifecycle according to DB behavior.

Bulk JPQL deletes can skip entity callbacks and managed-remove cascade semantics. If documents have attachments/audit/outbox records, do not choose bulk delete merely for fewer SQL statements.

## 17. Null or Missing Scope: Never Make Guards Optional

A common anti-pattern in search forms:

~~~sql
WHERE d.id = :id
  AND (:tenant IS NULL OR d.tenant_id = :tenant)
  AND (:actor IS NULL OR d.owner_user_id = :actor)
~~~

Writing optional filters like this may suit a separately protected admin UI, but it is **unsuitable** as an authorization guard for user data. When actor/tenant is null, the predicate loses effect and may return any record matching the ID.

For data authorization, mandatory scopes must be **required**:
- No actor → deny/challenge, not "all users".
- No tenant → deny, not default tenant.
- Missing owner → do not automatically make the document public.
- Permission backend error/null → do not grant access, handle errors in a controlled manner.
- Invalid resource ID → validate input before querying.
- Self-declared owner/tenant in header/body → never replace verified identity.

SQL NULL has three-valued logic; do not rely on `NULL = NULL` behavior as a primary policy. Validate explicitly and keep predicates safe.

## 18. Standalone Java 17: Checking ID + tenant + (owner OR share)

The following example **runs on JDK 17+, without Spring**. It simulates the result of a scoped query: every document must match ID and tenant before checking owner or grant list. In production, shares must come from the database or a trusted policy, not the client.

Create file `ScopedLookupDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.Set;

public class ScopedLookupDemo {
    record Actor(String id, String tenant, Set<Long> sharedIds) { }
    record Document(long id, String tenant, String owner, String title) { }

    static Optional<Document> findReadable(
            List<Document> docs, Actor actor, long requestedId) {

        if (actor == null || requestedId <= 0
                || actor.id() == null || actor.id().isBlank()
                || actor.tenant() == null || actor.tenant().isBlank()
                || actor.sharedIds() == null) {
            return Optional.empty();
        }

        return docs.stream()
                .filter(d -> d.id() == requestedId)
                .filter(d -> d.tenant().equals(actor.tenant()))
                .filter(d -> d.owner().equals(actor.id())
                        || actor.sharedIds().contains(d.id()))
                .findFirst();
    }

    static String lookup(List<Document> docs, Actor actor, long id) {
        return findReadable(docs, actor, id)
                .map(Document::title)
                .orElse("NOT_FOUND");
    }

    public static void main(String[] args) {
        List<Document> docs = List.of(
                new Document(1, "south", "thao", "SouthSecret"),
                new Document(1, "north", "an", "NorthDraft"),
                new Document(2, "north", "chi", "SharedReport"),
                new Document(3, "north", "chi", "PrivateNote"),
                new Document(4, "south", "thao", "SouthOnly")
        );
        Actor an = new Actor("an", "north", Set.of(2L));
        Actor afterRevoke = new Actor("an", "north", Set.of());

        System.out.println("owner=" + lookup(docs, an, 1L));
        System.out.println("shared=" + lookup(docs, an, 2L));
        System.out.println("unshared=" + lookup(docs, an, 3L));
        System.out.println("wrong-tenant=" + lookup(docs, an, 4L));
        System.out.println("missing-actor=" + lookup(docs, null, 1L));
        System.out.println("after-revoke="
                + lookup(docs, afterRevoke, 2L));
    }
}
~~~

Commands:

~~~bash
javac ScopedLookupDemo.java
java ScopedLookupDemo
~~~

Exact stdout:

~~~text
owner=NorthDraft
shared=SharedReport
unshared=NOT_FOUND
wrong-tenant=NOT_FOUND
missing-actor=NOT_FOUND
after-revoke=NOT_FOUND
~~~

Document ID 1 appears in both south and north. Although `SouthSecret` appears earlier in the list, the tenant predicate correctly selects `NorthDraft`. An can READ document 2 thanks to the share; unshared document 3, ID 4 in another tenant, missing actor, or revoked grant all return no data.

The demo uses lists/streams to illustrate logic, without actor/tenant verification, persistence, concurrency, or grant expiry. Real applications must take actor/tenant IDs from verified authentication sources and use database queries to filter before loading/serializing.

## 19. Why Query-Level Filtering Beats `@PostFilter` for Detail/List

Method security provides `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`, yet none of them automatically injects `tenant_id=:tenant AND owner_id=:actor` into every repository query.

- `@PreAuthorize` enforces authority/function checks before calling the method; for object policies it can call a policy bean. The call must pass through a Spring proxy.
- `@PostAuthorize` evaluates after the method runs; for writes, side effects may have already occurred.
- `@PostFilter` filters collections after data has been loaded; it is not a SQL WHERE clause and can break pagination/counts.
- Query-time scoping makes the database return only permitted rows, keeping detail/list/export and counts aligned on the same predicate.

Multiple layers can be combined: HTTP authentication, method authority, trusted service actor, scoped repository, domain ACL, and database RLS if configured. **Defense in depth** is better than relying on a single annotated controller.

If using PostgreSQL RLS or an equivalent DB feature, set/reset tenant/user context safely with connection pools and transactions to avoid context leakage between requests. Never assume RLS is active just because the schema defines a policy.

## 20. List, Count, and Search Need the Same Permission Conditions

Common mistake:

~~~text
GET /documents/42 --> scoped, safe
GET /documents    --> findAll(), data leak
GET /documents/export --> raw query, data leak
GET /documents/count  --> counts unauthorized records too
~~~

For lists, use the same predicate:

~~~sql
SELECT d.*
FROM documents d
WHERE d.tenant_id = :tenant
  AND (
      d.owner_user_id = :actor
      OR EXISTS (
          SELECT 1 FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee_user_id = :actor
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
      )
  )
ORDER BY d.id
LIMIT :size OFFSET :offset;
~~~

In practice, add expiry/status if the policy requires it. `countQuery` must use **the exact same conditions**; do not fetch 20 records, filter down to 3 in Java, and return a total count from the whole DB.

You can reuse predicates via `Specification`/Criteria API or a tested query builder instead of copy-pasting SQL into every endpoint. Optimize indexes for owner, tenant, grants, and membership, and check `EXPLAIN` on a real DB. Never remove a scope filter just because a query is slow.

## 21. Role of Indexes and Performance

- With a global PK, an index on `documents(id)` may suffice for detail lookup while the DB checks tenant/owner on the row.
- With tenant-local keys, a unique/index on `(tenant_id, id)` is critical.
- For owner-based lists, consider `(tenant_id, owner_user_id, id)`.
- For grants, index on `document_id, grantee_user_id, permission` and revoked/expiry conditions depending on workload.
- For project memberships, index appropriately by project/user/tenant.

`EXISTS` helps avoid duplicate rows from multiple grants. At large data volumes, use query plans and real metrics (latency, row counts, cardinality) to choose indexes. Do not add indexes indiscriminately to every column without measuring write cost.

An external permission service doing N+1 lookups per document may be too slow for lists; in that case you need batch policies or an authorized-view index with proper invalidation. Performance is never an excuse to skip permission checks.

## 22. State Transitions and Scope Changes

Owner transfer: does the old owner retain READ via a share, what permissions does the new owner get, and must old grants be revoked? Tenant transfer: requires permissions in both source and target tenants, and old ACLs/caches/grants/memberships must be migrated or revoked per policy.

Do not just change `tenant_id` while leaving cross-tenant grants intact when business rules forbid it. For a moved resource, queries scoped to the old tenant must stop returning data after a successful change. This is a security event that requires auditing and testing.

Deletion/restore/copy also have implications: a new copy should not automatically inherit the old object's grants unless permitted. Reusing an ID after deletion can resurrect old ACLs/grants if lifecycle is not managed.

## 23. Testing Matrix for ID and Scope Queries

| Case | Expectation |
|---|---|
| Owner in same tenant, right authority | Data returned |
| Non-owner, no share | No data returned |
| Right ID, different tenant | No data returned |
| Two tenants with colliding local IDs | Returns actor's tenant resource only, no leak from other tenant |
| Valid READ grant on the exact object | Data returned |
| Has READ but calls WRITE | Denied, no mutation |
| Grant on a different object ID | Does not mistakenly return the granted object |
| Grant expired/revoked | No data returned |
| Right group but membership revoked | No data returned |
| Missing actor or tenant | Access denied |
| Wrong functional authority | Method boundary rejects |
| Wrong OR parentheses | Test must catch leaks of other IDs/tenants |
| User-controlled owner/tenant present | Never used instead of verified scope |
| Owner-only UPDATE with wrong scope | Row count 0, DB unchanged |
| UPDATE with stale version | Row count 0 or conflict per contract |
| Permission backend outage | No side effects |
| List/count/export | Same scope as detail |
| Direct service call/message consumer | Query/service authorization still applies |

Test through Spring Data repositories and integration tests against a production-equivalent database; do not assert only HTTP status. Verify actual data remains unchanged when denied, page/count totals are accurate, and no event/download leaks data.

Tests can use `@SpringBootTest`/appropriate test slices, a custom principal for tenant claims, and Testcontainers when SQL dialect matters. `@WithMockUser` alone does not automatically create application tenant claims. Test services through the real Spring bean proxy—not just objects instantiated with `new`—when relying on method security.

## 24. Common Bugs to Eliminate

**1. `findById` and return immediately.** Right ID does not mean right permission. Replace with a scoped query or mandatory object policy check before outputting data.

**2. Trusting client-sent `ownerId`/`tenantId`.** A user can impersonate an owner. Derive scope from verified authentication.

**3. `AND/OR` without parentheses.** Share/admin branches can bypass ID/tenant barriers. Test with grants on other documents and other tenants.

**4. Reusing READ for WRITE/DELETE.** Permission names must match the action; never infer WRITE from having READ.

**5. Share permissions without checking expiry/revocation.** Old grants become permanent permissions. Use server time and active status.

**6. `(:tenant IS NULL OR ...)` in security queries.** Missing scope widens the query. For actor/user data, scope is required.

**7. Returning 200/204 when UPDATE affects 0 rows.** Caller assumes the edit succeeded; check row count and handle security/concurrency.

**8. Bulk updates ignoring version/lifecycle.** Design version predicates and mutations explicitly rather than assuming dirty checking applies.

**9. Protecting only detail while forgetting list/export/count/download.** Every data path must enforce the same scope.

**10. Relying solely on HTTP filters.** Messages, async tasks, schedulers, and direct service calls may bypass HTTP; services/queries must still protect.

**11. `@PostFilter` instead of SQL predicates.** Data is already loaded, and pagination/counts break. Use query-time scoping whenever possible.

**12. Allowing access when the ACL service is unavailable.** Fail-open. Halt the action and report a controlled error.

## 25. Pre-Merge Checklist

- [ ] ID queries always bind the verified tenant.
- [ ] Owner or allowed scope is computed from server data, not self-declared request input.
- [ ] `OR` parentheses are placed inside mandatory ID/tenant conditions.
- [ ] Action authorities and object permissions are clearly separated.
- [ ] Shares/grants bind to the exact object/action and remain valid.
- [ ] Missing actor/tenant/ACL/backend failures all fail closed.
- [ ] Out-of-scope records are never serialized or logged before the guard.
- [ ] READ/WRITE/DELETE have appropriate predicates; never mistakenly reused.
- [ ] UPDATE/DELETE enforce row counts, transactions, and version guards as required.
- [ ] List/count/search/export/download share the same scope policy.
- [ ] Tests cover wrong ID, wrong owner, wrong tenant, expired/revoked grants, and OR precedence.
- [ ] Method security is enabled and calls go through Spring proxies.
- [ ] Performance/indexes and permissions on owner/tenant transfers have been evaluated.
- [ ] Status codes 401/403/404/5xx do not leak out-of-scope objects.

**Conclusion:** For private resources, the predicate `ID = requestedId AND tenant = verifiedTenant AND (owner = verifiedActor OR validAllowedScope)` is an essential data-protection layer against BOLA/IDOR. Combine it with authentication, method security, per-action permission checks, conditional transactions, and testing across all entry points so you protect every object, not just one controller.

## References

- [Spring Data JPA – JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived queries, `@Query`, binding parameters, modifying queries.
- [Spring Data JPA – Query Methods Details](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): method naming syntax and reserved methods.
- [Spring Data JPA – Modifying](https://docs.spring.io/spring-data/data-jpa/reference/api/java/org/springframework/data/jpa/repository/Modifying.html): bulk UPDATE/DELETE and the persistence context.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and interceptors.
- [OWASP API Security Top 10 (2023) – BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): authorization by object ID.
- [PostgreSQL – Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): complementary RLS if using PostgreSQL.
