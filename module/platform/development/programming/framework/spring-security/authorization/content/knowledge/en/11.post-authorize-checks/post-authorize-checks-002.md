# Checking Ownership When the Object Is Only Available After Querying

> **Module:** Spring Security - authorization  
> **Knowledge area:** Post-method checks  
> **Goal:** Understand when authorization must be evaluated after a query returns an object, how `@PostAuthorize` and `returnObject` work in Spring Security Servlet, how to combine roles/authorities with owner–tenant–ACL, why post-authorization is unsuitable as the sole gate for write commands, and how to test so you do not introduce IDOR/BOLA vulnerabilities.

## 1. The problem: without the object, you do not yet know who owns it

Consider a document reading API:

```http
GET /api/documents/42
Authorization: Bearer <access-token>
```

The controller passes the number `42` down to the service:

```java
public DocumentView readDocument(long documentId) {
    return repository.findViewById(documentId)
        .orElseThrow(DocumentNotFoundException::new);
}
```

At the moment parameters arrive, the application only knows the **ID**. To determine the owner of document 42, it must query the database or a trusted data source to learn:
- who the actual `ownerUserId` is;
- the `tenantId`/organization containing the document;
- whether the document is locked or archived;
- whether there is an ACL/delegation allowing someone else to view it.

One Spring Security approach is to let the method run to load the object and then use `@PostAuthorize` to compare a property of the result against the actor:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentView readDocument(long documentId) {
    return repository.findViewById(documentId)
        .orElseThrow(DocumentNotFoundException::new);
}
```

The condition `returnObject.ownerId == authentication.name` is only a **simple illustration**: it works when `ownerId` on the DTO is a trustworthy property using the same ID system as `authentication.name`. In most real systems, you should use a policy bean that checks a normalized actor ID, tenant, ACL, and state.

**The most important point:** `@PostAuthorize` lets you **decide whether the result may be returned to the caller**, but **the method body has already run** before that check takes place.

## 2. Distinguishing three protection checkpoints

```text
HTTP request / message / bean call
          |
          v
Spring-managed service proxy
          |
          v
[1] @PreAuthorize
    Has required authority/capability?
          |
          | DENY -> method body DOES NOT run
          v
    Method body: query DB to build DocumentView
          |
          v
[2] @PostAuthorize
    Does returnObject belong to permitted actor/tenant?
          |
          | DENY -> do not return result to caller
          v
    Caller receives result
          |
          v
[3] Use cases that mutate data
    must have an object policy BEFORE side effects
```

| Component | Timing | Available data | Best protects |
| --- | --- | --- | --- |
| `@PreAuthorize` | Before the method runs | Authentication and method arguments | Blocking missing permission, checking ID via policy service if needed |
| `@PostAuthorize` | After the method produces a result | Authentication, arguments, and `returnObject` | Checking owner/tenant/ACL on a single object read from a trusted source |
| `@PostFilter` | After the method returns a supported collection/stream | Each `filterObject` in the returned set | Filtering unauthorized elements; must consider performance/pagination |
| Domain policy in service | At the point of using the entity, usually inside a transaction | Real entity, actor, consistent state | Write/approve/delete and complex owner/tenant rules |
| Scoped query | Right when fetching data | Tenant ID, actor ID, grants, visibility | Avoiding loading unauthorized data altogether; lists/exports |

`@PostAuthorize` and `@PostFilter` are not the same. One **allows/denies the entire method result**, while the other **filters elements** of the result. For a single document, `@PostAuthorize` is a clear option when ownership is only known after querying.

## 3. How does @PostAuthorize work internally?

When Spring method security is enabled:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Spring Security installs method-security advisors via Spring AOP. For `@PostAuthorize` in the modern `AuthorizationManager` architecture:
- `AuthorizationManagerAfterMethodInterceptor` receives the completed invocation and its return value.
- `PostAuthorizeAuthorizationManager` uses an expression handler to evaluate the SpEL expression.
- `returnObject` represents the value returned by the method.
- If the decision denies, the framework normally throws `AccessDeniedException`; in a properly configured HTTP flow, the web layer can translate it to 403 for an authenticated user.
- If allowed, the result proceeds to the caller.

The description above is the common default path in Spring Security 6.5 Servlet; an application can customize advisors, exception handling, method security, and fallback behavior. When calling a service outside HTTP, such as a job or message listener, the exception may need to be handled separately; do not assume there will be an “HTTP 403” when there is no HTTP request.

**Spring Boot Starter Security does not automatically enable method security**. You must verify that `@EnableMethodSecurity` exists in the application context used at runtime.

## 4. Official example and proper interpretation

Spring Security illustrates the rule:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Account readAccount(Long id) {
    return accountRepository.findById(id).orElseThrow();
}
```

Assuming the method returns an `Account` with an `owner` property, SpEL evaluates:
- `returnObject`: the `Account` fetched from a trusted source;
- `returnObject.owner`: the owner property of Account;
- `authentication.name`: the current principal's name.

If the two values are equal, the result can proceed; if different, method security denies it. This is one way to prevent **Insecure Direct Object Reference (IDOR)**: someone who can guess an account ID does not automatically receive someone else's account.

However, do not apply it blindly:
- `authentication.name` might be an email/username/OIDC sub, while `Account.ownerId` is a UUID.
- The owner might be a team or organization, not a single username.
- The actor might have an ACL READ grant even if not the owner.
- The owner might belong to a different tenant or the document might be locked.
- A DTO might be built from untrusted input rather than a real entity.
- A 403 response does not prove that data was not logged/cached before the post-check.

**Therefore, move from a single-property comparison to a policy object with an explicit contract when business requirements demand it.**

## 5. A realistic read setup: functional pre-check and object post-check

Spring Security Servlet service example:

```java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentQueryService {

    private final DocumentRepository documents;

    public DocumentQueryService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize(
        "returnObject != null and "
        + "@documentAccess.canRead(authentication, returnObject)"
    )
    public DocumentView readDocument(long id) {
        return documents.findViewById(id)
            .orElseThrow(DocumentNotFoundException::new);
    }
}
```

**This is an integration snippet**, requiring `DocumentRepository`, `DocumentView`, `DocumentNotFoundException`, and the `documentAccess` bean built by the application; it does not yet include the controller, authentication, DB, or error handler.

Step-by-step explanation:

1. `@PreAuthorize("hasAuthority('document:read')")` prevents anyone lacking functional read permission from calling into the repository.
2. The method queries the document by ID, constructing `DocumentView`.
3. `@PostAuthorize` inspects `returnObject`; if the object is null or the policy denies, the result is rejected.
4. `documentAccess.canRead` evaluates the principal against **owner/tenant/ACL/state of the real object**.
5. Only after both gates ALLOW does the caller receive `DocumentView`.

**Why use both pre and post?** The post-check handles object-level permission known only after querying; the pre-check is cheap and avoids loading data for an actor completely lacking the capability. Because `@PostAuthorize` runs after the body, the body must not perform writes or external side effects.

## 6. Policy bean checking owner, tenant, and organization-level permission

An illustrative policy bean:

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentAccess")
public class DocumentAccess {

    private final ActorResolver actorResolver;

    public DocumentAccess(ActorResolver actorResolver) {
        this.actorResolver = actorResolver;
    }

    public boolean canRead(
            Authentication authentication, DocumentView document) {
        if (authentication == null || document == null
                || !authentication.isAuthenticated()) {
            return false;
        }

        Actor actor = actorResolver.requireActor(authentication);

        // Reject documents belonging to another tenant.
        if (!actor.activeTenantId().equals(document.tenantId())) {
            return false;
        }

        // Business policy may forbid reading locked documents.
        if (document.readLocked()) {
            return false;
        }

        // Owner is allowed to read if prior conditions are satisfied.
        if (actor.id().equals(document.ownerId())) {
            return true;
        }

        // Specific permission, only allowing reads within the same tenant.
        return actor.hasAuthority("document:read:tenant")
            && actor.canUseTenantWideRead();
    }
}
```

`Actor`, `ActorResolver`, `DocumentView`, and their methods are **illustrative domain contracts**, not built-in Spring Security classes. A real implementation may need to check ACL READ, delegation, classification, project membership, expiry, and business state.

A few invariants:
- `actorResolver` must derive identity/active tenant from Authentication **and verified membership**, not from a client-sent `X-Tenant-Id` trusted blindly.
- `document.ownerId`/`document.tenantId` should come from the loaded server record, not from a client-declared request DTO.
- `document:read:tenant` is an intentionally granted capability, not implied by `ROLE_ADMIN`.
- If an actor has a role hierarchy, `actor.hasAuthority` must have a clear contract on whether it checks direct or expanded authorities; a custom policy bean does not automatically consult every `RoleHierarchy` bean.
- For a non-existent object, the service may throw not-found before the post-check; you must decide how 404/403 is represented consistently with anti-enumeration.

## 7. Why is an ID from the URL not proof of ownership?

HTTP:

```http
GET /api/documents/42
GET /api/documents/43
```

If the controller passes the ID straight down:

```java
DocumentView read(long id) {
    return repository.findViewById(id)
        .orElseThrow();
}
```

Knowing or guessing ID 43 does not mean the client has permission to read it. IDOR/BOLA occurs when the system only checks authentication or general read permission, without checking against the object.

Compare two approaches:

**Wrong: checking a caller-declared owner**

```java
@PreAuthorize("#ownerId == authentication.name")
public DocumentView readDocument(
        long id, String ownerId) {
    return repository.findViewById(id).orElseThrow();
}
```

The caller can send `ownerId` equal to their own name while `id` belongs to someone else.

**Better in read-only use cases: checking the real owner after querying**

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("@documentAccess.canRead(authentication, returnObject)")
public DocumentView readDocument(long id) {
    return repository.findViewById(id)
        .orElseThrow();
}
```

Thus `returnObject` is the object fetched from the DB, and the policy can read the real owner. Still, note that **the object has already been loaded**, so for highly sensitive data systems you should still scope the query before building the result.

## 8. Trustworthiness of returnObject

`returnObject` is only as trustworthy as **the source that produced it**.

Unsafe example:

```java
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
public DocumentView unsafeRead(
        long id, String claimedOwnerId) {
    // DTO owner is taken from the client parameter, not from the DB!
    return new DocumentView(id, claimedOwnerId, "content");
}
```

If `ownerId` is not a field taken from the real entity, the post-check only verifies the caller's **self-declared** name; it can still allow leaking content fetched by another ID. An “after-method” gate does not automatically turn forged data into trusted data.

In a sound design:
- The entity is queried by ID with tenant scoping.
- Owner/tenant/ACL come from the DB or a trusted service.
- DTO mapping never takes `ownerId` from the HTTP body.
- Policy never treats client-populated cache entries or mocks as ground truth.
- Owner info is a canonical ID with a consistent type; principal name might not share the same type.

With database projections or DTO views, ensure the query maps all security-sensitive fields. If a query intentionally omits `ownerId` for optimization, the post-check cannot guess the owner; you must update the query/policy.

## 9. Single owner versus multiple shared readers

A document may have:
- a direct owner;
- an owning group;
- ACL READ for other users;
- read access via project membership;
- tenant-wide access for support roles;
- a PUBLIC state;
- classification-based read blocks;
- expired or revoked grants.

`@PostAuthorize("returnObject.ownerId == authentication.name")` only solves an **owner-only** rule. If the business supports sharing, it can wrongly deny users with valid shared access. When the policy is complex:

```java
@PostAuthorize(
    "@documentAccess.canRead(authentication, returnObject)"
)
```

At that point `documentAccess` evaluates **the same policy** as other entry points and can be unit-tested independently.

A possible model:

```text
canRead(actor, document)
  = actor has document:read
    AND document belongs to authorized tenant
    AND document state permits read
    AND (
      document is public under policy
      OR actor is owner
      OR ACL READ for actor
      OR membership-based project grant
      OR explicit tenant-wide read permission
    )
```

**The tenant and state conditions belong outside the OR group** if every read path must obey them. Misplaced parentheses can let “owner OR admin” bypass the tenant boundary.

## 10. Tenant must be checked before allowing the owner

Suppose:
- Bob has `document:read`, active tenant A.
- Document 44 has `ownerId=bob` but belongs to tenant B.

A check comparing only `ownerId` will let it through:

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
```

This can violate the active-tenant policy. A safer version:

```java
@PostAuthorize(
    "@documentAccess.canRead(authentication, returnObject)"
)
```

And inside the policy bean:
1. Verify the active tenant from the trusted actor.
2. Compare the queried document's tenant against the active tenant.
3. Check data classification/state.
4. Check owner/ACL/tenant-wide grant.

Not every product needs the exact same rule: some systems intentionally let users read data they own across multiple tenants through an explicit grant. However, **a cross-tenant allowance must be an explicit policy**, never an accidental side effect of a name comparison.

## 11. 404, 403, and non-existent data

With:

```java
return repository.findViewById(id)
    .orElseThrow(DocumentNotFoundException::new);
```

If the ID does not exist, the method throws an exception **before producing returnObject**. `@PostAuthorize` has no normal object to inspect. Error mapping determines whether the response may be 404.

If the ID exists but the user is not the owner, the post-check can throw `AccessDeniedException`, usually resulting in 403 via HTTP security exception handling.

This can reveal the difference between:
- ID does not exist;
- ID exists but belongs to someone else.

For APIs that must resist ID probing/enumeration, consider:
- Querying within the actor/tenant scope so non-existent and unauthorized look identical.
- Mapping errors according to a safe contract, without leaking owner or private metadata.
- Not disclosing “owner is alice” in deny messages.
- Rate limiting/auditing anomalous ID queries.
- Not using a fake response value from the post-check to mask all errors without reviewing endpoint behavior.

**Do not conclude that every unauthorized resource must return 404.** That is a product and security policy choice; it must be consistent and tested. What matters is not leaking data unintentionally.

## 12. Null returnObject and Optional

A method can return `null`, `Optional<Document>`, or throw an exception. The pattern:

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
```

is not null-safe; accessing `ownerId` when `returnObject==null` can cause a SpEL error. If the contract returns `null` for “not found”, you can write explicitly:

```java
@PostAuthorize(
    "returnObject == null or "
    + "@documentAccess.canRead(authentication, returnObject)"
)
```

But that expression means **allowing a null result through**; make sure that is a valid contract. If you want to fail closed, `returnObject != null and ...` denies null, which can turn “not found” into “access denied” instead of the error the API expects.

**Recommendation for a GET by ID:** return a DTO when found, throw `DocumentNotFoundException` when not found, then post-authorize the non-null DTO. The result keeps logic easy to test and unambiguous.

For `Optional<Document>`, Spring Security has different return object/proxy handling APIs across versions, but **do not assume** `returnObject.ownerId` will automatically unbox `Optional` as intended. Verify the object type in the expression or use a policy helper accepting the full typed result; better yet, avoid Optional at boundaries with complex owner post-checks if unnecessary.

### Null-safe is not authorization

An expression using null-safe operators/guards only avoids exceptions or decides the null case; it does not verify owner/tenant. Do not treat `returnObject != null` as a permission test.

## 13. @PreAuthorize and @PostAuthorize can be used together

Example:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize(
    "returnObject != null and "
    + "@documentAccess.canRead(authentication, returnObject)"
)
public DocumentView readDocument(long id) {
    return repository.findViewById(id).orElseThrow();
}
```

The two annotations are **two distinct interceptor types**, not the same annotation overriding itself. In the default flow:
- Pre-check DENY ⇒ method body does not run, no normal result post-check occurs.
- Pre-check ALLOW ⇒ method body runs.
- Post-check DENY ⇒ result is not returned to the caller.
- Both ALLOW ⇒ caller receives the result.

A read method can legitimately fetch the entity and then decide at post-check. For methods with side effects, this arrangement **is insufficient** if the pre-check only validates a general permission while the post-check checks ownership after an update.

A performance note: because a pre-check can prevent querying upfront for users lacking the authority, placing a cheap and clear pre-check is usually beneficial. Still, the post-check may have to evaluate resource-specific permissions.

## 14. Why shouldn't post-authorization be the primary gate for writes?

**Dangerous** code:

```java
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
@Transactional
public Document renameDocument(long id, String title) {
    Document doc = repository.findById(id).orElseThrow();
    doc.rename(title);
    return doc;
}
```

The method can mutate a managed entity before the security expression is evaluated. Depending on the ordering of the transaction advisor and post-authorization advisor:
- The DB transaction might not yet have committed at post-check time, or it might already have committed.
- Rollback depends on transaction boundaries, exception configuration, and how the mutation is persisted.
- External side effects (HTTP calls, emails, message publishing) are not automatically undone even if the DB rolls back.
- Logs, caches, or events may already have received the changed data.
- There is no guarantee that a post-method exception always restores the entire system to its previous state.

Spring Security documentation **does not recommend `@PostAuthorize` for database-writing classes** and notes that coordinating `@Transactional` with method security requires understanding advisor ordering. Do not rely on advisor order as a “default safeguard” instead of pre-checking the object.

**Safe pattern:** load the entity, check authorization before mutating, update inside a transaction with appropriate isolation/locking. When ownership is only known after a DB query, checking ownership **inside the method after querying but before writing** is the standard choice.

## 15. Read first, verify permission, then write

Rename command example:

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {

    private final ActorResolver actors;
    private final DocumentRepository repository;
    private final DocumentPolicy policy;

    public DocumentCommandService(
            ActorResolver actors,
            DocumentRepository repository,
            DocumentPolicy policy) {
        this.actors = actors;
        this.repository = repository;
        this.policy = policy;
    }

    @PreAuthorize("hasAuthority('document:rename')")
    @Transactional
    public void renameDocument(long id, String newTitle) {
        Actor actor = actors.requireAuthenticatedActor();

        Document document = repository
            .findForUpdateWithinTenant(id, actor.activeTenantId())
            .orElseThrow(DocumentNotFoundException::new);

        if (!policy.canRename(actor, document)) {
            throw new AccessDeniedException("Not permitted");
        }

        document.rename(newTitle);
    }
}
```

**This is an integration snippet**, not a standalone Java 17 program. `Actor`, `ActorResolver`, `Document`, `DocumentRepository`, `DocumentPolicy`, and exceptions are application contracts. The repository must actually implement `findForUpdateWithinTenant` with JPA/SQL and proper transaction/locking; the method name alone does not create a lock.

Safe structure:
1. Pre-check functional capability before the body.
2. Read the object scoped by the verified tenant from the actor.
3. Evaluate owner/ACL/state policy on **the real entity**.
4. Only after ALLOW call `rename`.
5. Commit transaction and audit as designed.

Do not replace the policy block with `if (hasRole("ADMIN")) return;` unless there is an explicit tenant-wide capability with proper boundaries/approval; `ROLE_ADMIN` does not inherently prove permission on every document.

## 16. TOCTOU: protecting at time of data use

Even if you do:

```text
T1: read document, see owner is Alice
T2: policy ALLOWs Alice
T3: another transaction transfers ownership to Bob
T4: execute write based on stale owner
```

the system still faces **time-of-check/time-of-use (TOCTOU)** risk. `@PostAuthorize` on a prior read does not hold locks across requests/transactions and does not guarantee permissions remain valid for a subsequent write.

Mitigations:
- Check owner/tenant/state on the entity inside the write transaction.
- Appropriate pessimistic locking or `@Version` optimistic locking.
- Conditional SQL update containing actor/tenant/owner/status/version in `WHERE`.
- Check affected-row count; 0 rows must lead to deny/conflict/not-found per contract.
- For financial commands, consider separation of duties and approval state.
- External side effects should use outbox/transactional messaging when consistency is required.
- Ownership/ACL caches need versioning/invalidation.

Illustrative SQL when only the owner may rename:

```sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :trusted_tenant
  AND owner_id = :authenticated_actor
  AND status = 'DRAFT'
  AND version = :expected_version;
```

`trusted_tenant` and `authenticated_actor` must come from the verified security context/server membership; never from the request body. If the business supports ACL WRITE/delegated permission, the query must expand to match the policy rather than rigidly remaining owner-only.

## 17. When should data be filtered directly in the repository?

`@PostAuthorize` is convenient for a single object read after querying. However, it does not prevent the DB from reading an unauthorized object. When data is especially sensitive, a scoped query can be safer and more efficient:

```java
public Optional<DocumentView> findReadableById(
        long documentId, UUID tenantId, UUID actorId);
```

SQL:

```sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND (
       d.owner_id = :actor_id
       OR EXISTS (
           SELECT 1
           FROM document_grants g
           WHERE g.document_id = d.id
             AND g.user_id = :actor_id
             AND g.permission = 'READ'
       )
  );
```

With a query already constrained by owner/ACL, unauthorized documents never enter service-layer DTOs along this path. You can still keep a post-check as defense in depth if appropriate, but avoid duplicate DB reads and mismatches between query policy and bean policy.

**Choices:**
- Simple system, single-object read: `@PostAuthorize` after load is a reasonable pattern once pre-query risks are accounted for.
- Multi-tenant or sensitive-data systems: constrain tenant/ownership directly in the DB query, adding domain policy where needed.
- Write commands: mandatory check before side effects; `@PostAuthorize` is not the primary final gate.
- Large lists and pagination: scoped queries are usually better than loading everything and filtering.

There is no rule that “post-check is always wrong”. It fits **read objects whose ownership is only known after querying**, provided the method creates no sensitive side effects before the decision.

## 18. Result sets other than a single object: @PostFilter

Suppose a method returns `List<DocumentView>`:

```java
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
public List<DocumentView> listDocuments() {
    return repository.findAllViews();
}
```

This expression **is semantically invalid**: `returnObject` is a List, not a DocumentView with an `ownerId` property. Do not assume `@PostAuthorize` iterates over every element.

For supported collections/streams, Spring Security provides `@PostFilter`:

```java
@PostFilter(
    "filterObject.ownerId == authentication.name"
)
public List<DocumentView> listDocuments() {
    return repository.findAllViews();
}
```

In `@PostFilter`:
- `filterObject` is each element being evaluated.
- Elements that fail are removed from the result.
- The method still ran and fetched the list before filtering.
- If `ownerId` and Authentication ID use different reference systems, results can be wrong.
- Tenant/ACL need explicit policy; comparing owner alone can be too strict or too loose depending on business rules.

**Why is it discouraged for large lists?** Loading 1 million documents and filtering out 999,990 items in memory wastes DB/network/memory, breaks pagination/total counts, and risks logging/caching before filtering. Scoped queries with pagination should be preferred. Use `@PostFilter` when the set is small, semantics are clear, and performance is acceptable.

If a bulk operation requires all-or-nothing semantics, do not let post-filtering silently drop some items and return the rest so the caller thinks the entire request succeeded.

## 19. Difference from @AuthorizeReturnObject

Spring Security 6.3+ provides `@AuthorizeReturnObject` to **proxy returned objects** and apply method security on methods of the proxied object itself; this is a different capability from `@PostAuthorize`.

Conceptual example:

```java
@AuthorizeReturnObject
public UserProfile profile() {
    return repository.loadProfile();
}
```

If `UserProfile` has a getter annotated with `@PreAuthorize("hasAuthority('profile:private:read')")`, the returned proxy can check permission when the getter is called, depending on version/config. This does not mean an object is automatically owner-checked with the same `@PostAuthorize` rule.

Comparison:
- `@PostAuthorize`: evaluates **a single post-method decision** based on `returnObject` and an expression.
- `@PostFilter`: evaluates each element after the method to filter supported results.
- `@AuthorizeReturnObject`: applies security advice when calling methods on **the return object proxy**; requires understanding proxy types, AOT/runtime hints, and nested objects.

Do not swap them mechanically. Choose by permission boundary: whole document, collection of documents, or getters on an object. For highly sensitive data, it is easier to audit returning a DTO already filtered by domain policy rather than relying on every client serializer traversing proxies properly.

## 20. Ownership from the principal must be normalized

The official example compares:

```java
returnObject.owner == authentication.name
```

This is only reliable if:
- owner in the DB has the same semantic type as `authentication.name`;
- name does not change across email renames;
- Authentication is built from a trusted source;
- the user is in the right tenant/context;
- there is no ambiguous mapping of multiple usernames to one user ID.

In modern systems:
- `authentication.name` may be an email, OIDC `sub`, or username.
- DB owner may be a UUID or numeric ID.
- APIs may use service identities or delegated users.
- Tenant membership may change independently of tokens.

Normalize into an `Actor` with canonical `userId`/`tenantId` after verifying Authentication, and compare against `Document.ownerUserId` in the same ID system. Never compare email against UUID or treat a client-supplied `ownerId` as ground truth.

If using JWT, claims must be verified and mapped properly; a string present in a JWT payload does not automatically become trustworthy before verifying signature/issuer/audience/expiry.

## 21. Role hierarchy does not replace object ownership

Suppose:

```text
ROLE_ADMIN > ROLE_EDITOR
ROLE_EDITOR > ROLE_VIEWER
```

Someone with `ROLE_ADMIN` can satisfy `hasRole('VIEWER')` when the authorization component has the hierarchy wired. Yet `ROLE_ADMIN` **does not automatically make the principal the owner** of Document 42.

Example:

```java
@PreAuthorize("hasRole('VIEWER')")
@PostAuthorize("@documentAccess.canRead(authentication, returnObject)")
public DocumentView readDocument(long id) {
    return repository.findViewById(id).orElseThrow();
}
```

An admin can pass the VIEWER pre-check and still be DENYed by the post-check if:
- the document belongs to another tenant;
- they are not the owner/ACL reader;
- they lack an explicit tenant-wide grant;
- state forbids viewing.

If you want support admins to read team documents within the same tenant, define a dedicated capability like `document:read:tenant` and a tenant-scoped policy, rather than using `hasRole('ADMIN') or owner` as an unconditional bypass.

## 22. What does a post-check achieve once the method has queried sensitive data?

A post-check prevents **a normal result** from returning to the caller through the interceptor-protected invocation. Yet data may already have passed through:
- JDBC/JPA and memory;
- mappers building DTOs;
- logging/tracing;
- caches storing results;
- audits/events;
- external calls;
- lazy loading and serialization preparing responses.

A buggy example:

```java
@PostAuthorize("@documentAccess.canRead(authentication, returnObject)")
public DocumentView readDocument(long id) {
    DocumentView view = repository.findViewById(id).orElseThrow();

    // Wrong: logging the entire document before the post-check
    logger.info("Document loaded: {}", view);

    return view;
}
```

Even when the interceptor later DENYs, the logs already contain private data.

Safer practices:
- Do not log full payloads/secrets.
- Only cache results if keys and policies ensure no cross-user/tenant leakage; consider checking permissions before caching.
- Do not publish events containing data before authorization.
- Do not initiate lazy streams whose side effects read further past the proxy while bypassing checks.
- For sensitive PII, prefer scoped queries/authorization before constructing DTOs.

**Post-authorize is not general-purpose data-loss prevention for every side channel**. It is a checkpoint at the method boundary.

## 23. Proxies, self-invocation, and non-HTTP entry points

Method security uses Spring AOP by default. If a service has:

```java
@Service
public class DocumentFacade {

    public DocumentView facade(long id) {
        return this.readSecured(id);
    }

    @PostAuthorize(
        "@documentAccess.canRead(authentication, returnObject)"
    )
    public DocumentView readSecured(long id) {
        return repository.findViewById(id).orElseThrow();
    }
}
```

`this.readSecured` is self-invocation inside the same bean; with standard AOP proxies, the call **does not go through the proxy**, and `@PostAuthorize` may not run. A controller calling `facade` through a proxy does not automatically protect internal self-calls with method security.

Mitigations:
- Extract the protected operation into another bean and call it through a Spring-injected proxy.
- Enforce mandatory policies in use cases/repository scopes rather than relying solely on a proxied getter.
- Write tests exercising public methods and real call paths.
- If using AspectJ weaving, understand it differs from Spring AOP proxies; do not assume every app uses weaving.
- Never instantiate a bean needing method security via `new` and expect advisors to run.
- Test final/private methods, Kotlin final classes, and interface/proxy types in your actual project.

In particular, message listeners, batch jobs, and GraphQL can also invoke services. If those paths use proper bean proxies, post-checks can apply; however, **403 responses are an HTTP concept**, and outside HTTP `AccessDeniedException` must be handled according to the respective execution model.

## 24. @Transactional and advisor ordering

The most critical issue is not merely “whether there is a transactional annotation”, but **in what order the transaction advisor and method-security advisors are nested**.

If you write:

```java
@Transactional
@PostAuthorize("@documentAccess.canRead(authentication, returnObject)")
public Document updateThenReturn(long id) {
    // DB writes might happen here...
}
```

there are two dangerous design possibilities:
- The post-check happens inside a transaction after mutation occurred, requiring proper rollback and ensuring no external side effects were emitted.
- The transaction has already completed before the post-check, so DENY does not undo the write.

Official Spring Security documentation notes `@EnableTransactionManagement` and `@EnableMethodSecurity` when they must be coordinated. **Relying on advisor order to turn a post-check into a write guard is not recommended**; interpretation and order tuning vary across codebases/versions.

For write use cases, a clear, reviewable solution is:
1. `@PreAuthorize` for functional permission.
2. Inside the transaction, load the object and its current owner/ACL/state.
3. Domain policy confirms permission **before mutation**.
4. Perform the write; commit and publish side effects per architecture.
5. Do not use a post-check as the sole owner verification step.

For read use cases with lazy JPA relations, if the post-check needs `returnObject.owner` after the transaction/read session has closed, the expression can trigger a lazy loading exception. Returning a DTO with needed policy fields, materialized inside the transaction, and post-checking the DTO gives stable semantics.

## 25. Standalone Java 17+: checking owner after querying

This is a **plain Java** program simulating querying a record and then deciding whether to return it. It does not use Spring Security, AOP, JWT, or a real database, so it does not prove production interceptors. It illustrates:
- Pre-checking functional authority.
- Knowing owner/tenant/state only after querying.
- Non-owners being DENYed.
- Tenant-wide grant being an **explicit** exception still constrained to the same tenant.
- Non-existent resources handled separately.
- The query having already occurred before the object decision step.

Save as `PostOwnershipDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class PostOwnershipDemo {

    record Actor(String name, String tenant, Set<String> rights) {}
    record Document(long id, String owner, String tenant, boolean locked) {}

    private static final Map<Long, Document> DB = Map.of(
        42L, new Document(42, "alice", "A", false),
        43L, new Document(43, "bob", "A", false),
        44L, new Document(44, "bob", "B", false),
        45L, new Document(45, "alice", "A", true)
    );

    private static int queries = 0;

    static Document load(long documentId) {
        queries++;
        return DB.get(documentId);
    }

    static String authorize(Actor actor, Document doc) {
        if (doc == null) {
            return "NOT_FOUND";
        }
        if (!actor.rights().contains("document:read")) {
            return "DENY capability";
        }
        if (!actor.tenant().equals(doc.tenant())) {
            return "DENY tenant";
        }
        if (doc.locked()) {
            return "DENY locked";
        }
        if (actor.name().equals(doc.owner())) {
            return "ALLOW owner";
        }
        if (actor.rights().contains("document:read:tenant")) {
            return "ALLOW tenant-grant";
        }
        return "DENY owner";
    }

    static String readThenAuthorize(Actor actor, long documentId) {
        Document loaded = load(documentId);
        return authorize(actor, loaded);
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "A", Set.of("document:read"));
        Actor bob = new Actor(
            "bob", "A", Set.of("document:read"));
        Actor manager = new Actor(
            "manager", "A", Set.of(
                "document:read", "document:read:tenant"));
        Actor guest = new Actor(
            "guest", "A", Set.of());

        System.out.println("Alice own: "
            + readThenAuthorize(alice, 42));
        System.out.println("Bob other document: "
            + readThenAuthorize(bob, 42));
        System.out.println("Manager same tenant: "
            + readThenAuthorize(manager, 42));
        System.out.println("Bob cross tenant: "
            + readThenAuthorize(bob, 44));
        System.out.println("Manager locked: "
            + readThenAuthorize(manager, 45));
        System.out.println("Guest missing authority: "
            + readThenAuthorize(guest, 42));
        System.out.println("Unknown document: "
            + readThenAuthorize(alice, 999));
        System.out.println("Bob own: "
            + readThenAuthorize(bob, 43));
        System.out.println("Repository queries: " + queries);
    }
}
```

Compile and run with JDK 17+:

```bash
javac PostOwnershipDemo.java
java PostOwnershipDemo
```

**Exact** stdout:

```text
Alice own: ALLOW owner
Bob other document: DENY owner
Manager same tenant: ALLOW tenant-grant
Bob cross tenant: DENY tenant
Manager locked: DENY locked
Guest missing authority: DENY capability
Unknown document: NOT_FOUND
Bob own: ALLOW owner
Repository queries: 8
```

Analysis:
1. Alice has read permission and is the owner of Document 42, so she is allowed.
2. Bob has the same functional permission but is not the owner of Document 42, so DENY.
3. Manager is explicitly granted `document:read:tenant`, reading within tenant A without bypassing state.
4. Bob may match the owner of Document 44, but active tenant A differs from tenant B, so blocked.
5. Document 45 is read-locked; manager cannot bypass.
6. Guest lacks authority; object decision is DENY even though the document exists.
7. Non-existent ID returns NOT_FOUND per the demo contract.
8. Bob reading his own Document 43 gets ALLOW.
9. There are **8 lookups**: the program still loaded the object before evaluating ownership (and the demo even simplified the authority pre-check). That is why post-authorization does not replace security-scoped queries when you need to avoid loading data upfront.

**Limitations:** `DB` is a fake `Map`, `authorize` is illustrative domain logic, there is no real Spring AOP/`@PostAuthorize`; the program produces no side effects. In production, actors must come from trusted authentication, repositories must enforce tenant/query scoping, and owner/ACL must come from canonical sources.

## 26. Unit testing the policy: owner, tenant, ACL, state

When using `@documentAccess.canRead(...)`, test the domain policy bean independently:

```java
@Test
void userCannotReadAnotherOwnersPrivateDocument() {
    Actor bob = actor("bob", "org-A", "document:read");
    DocumentView aliceDoc = document(
        42L, "alice", "org-A", false);

    assertThat(documentAccess.canRead(bob, aliceDoc)).isFalse();
}

@Test
void adminCannotReadCrossTenantWithoutExplicitPermission() {
    Actor admin = actor("admin", "org-A", "document:read:tenant");
    DocumentView otherTenantDoc = document(
        44L, "someone", "org-B", false);

    assertThat(documentAccess.canRead(admin, otherTenantDoc))
        .isFalse();
}

@Test
void ownerCannotReadLockedDocumentWhenPolicyForbidsIt() {
    Actor alice = actor("alice", "org-A", "document:read");
    DocumentView lockedDoc = document(
        45L, "alice", "org-A", true);

    assertThat(documentAccess.canRead(alice, lockedDoc)).isFalse();
}
```

**These are JUnit/AssertJ snippets**, using app-defined `actor`/`document` fixtures; an overload `canRead(Actor, DocumentView)` may differ from how `canRead(Authentication, DocumentView)` integrates. In real tests, choose one consistent contract or an explicit adapter.

Important cases:
- Owner in correct tenant, sufficient permissions, allowed state → ALLOW.
- User other than owner, sufficient functional permission but lacking ACL → DENY.
- Owner in a different tenant → DENY if active-tenant policy is enforced.
- Tenant-wide grant in a different tenant → DENY.
- ACL READ grant still does not permit DELETE.
- ARCHIVED/LOCKED states per business rule.
- Null result and non-existent resource.
- Changing `ownerId` or revoked ACL between requests.
- Missing Authentication or actor resolver failure → fail closed.

Policy unit tests alone do not prove `@PostAuthorize` is wired properly by Spring; you must have integration tests through the Spring proxy.

## 27. Integration testing @PostAuthorize via Spring-managed bean

Spring Security Test provides `@WithMockUser` to invoke methods with a mock Authentication.

Example of a real service `readAccount` returning an Account with an owner:

```java
@Autowired
BankService bankService;

@Test
@WithMockUser(username = "alice",
              authorities = {"account:read"})
void ownerMayRead() {
    Account account = bankService.readAccount(42L);
    assertThat(account.getOwner()).isEqualTo("alice");
}

@Test
@WithMockUser(username = "bob",
              authorities = {"account:read"})
void otherUserIsDeniedAfterQuery() {
    assertThatThrownBy(() -> bankService.readAccount(42L))
        .isInstanceOf(AccessDeniedException.class);
}
```

These are **test snippets**, requiring JUnit 5, AssertJ, Spring Security Test, `@SpringBootTest` or `@ContextConfiguration`, a DB fixture for Account 42 owned by Alice, and a genuinely configured `@PostAuthorize` method. Do not call `new BankService(...)` as that bypasses Spring AOP; inject the bean from the context.

Add a test proving **the method body ran** before the post-check, such as a repository spy counting `findById(42L)` = 1 for the DENY case. This helps the whole team understand the exact limitation of post-authorization. Do not log full Account objects in tests/production tracing.

For a method with both `@PreAuthorize` and `@PostAuthorize`:
- User lacking capability → repository is **not** called.
- User with capability but wrong owner → repository is read, then DENY.
- User with capability and ownership → read + ALLOW.

Do not only assert 403 in HTTP: 403 can come from a filter/CSRF/role/domain, which does not prove any post-check ran.

## 28. MockMvc: requires a real controller and control tests

REST scenario:

```java
@Test
void ownerReadsDocument() throws Exception {
    mvc.perform(get("/api/documents/42")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("document:read"))))
        .andExpect(status().isOk());
}

@Test
void userWithReadPermissionButNotOwnerIsDenied() throws Exception {
    mvc.perform(get("/api/documents/42")
            .with(user("bob").authorities(
                new SimpleGrantedAuthority("document:read"))))
        .andExpect(status().isForbidden());
}
```

The snippets above require:
- `MockMvc` with Spring Security filters;
- a real `GET /api/documents/{id}` controller;
- a proxied service with `@PostAuthorize`;
- Document 42 owned by Alice in the test DB;
- properly mapped authentication/permissions;
- exception mapping per contract.

If the app chooses to return 404 when the user lacks permission to prevent enumeration, update the expectation and test that no document leaks. If the route does not exist, 404 does not prove the owner policy works. If GET redirects to login/401 before reaching the service, the `@PostAuthorize` test was not exercised.

Outside HTTP, method-security DENY can throw `AccessDeniedException` for the caller to handle. Direct service bean tests complement MockMvc tests and pinpoint the exact blocking checkpoint.

## 29. What to do with lazy JPA entities?

Example:

```java
@PostAuthorize("returnObject.owner.id == authentication.name")
public Document readDocument(long id) {
    return repository.getReferenceById(id);
}
```

Risks:
- `getReferenceById` can return a lazy proxy; owner has not been loaded yet.
- If the persistence context has closed, SpEL property access can trigger a lazy loading exception.
- If `owner` is an entity relation, touching the property can issue unintended extra SQL.
- `authentication.name` may not equal the owner ID.
- Returning a JPA entity directly to the controller/serializer can accidentally expose fields or trigger lazy fetches outside security checks.

Better:
- Load required policy data with an explicit query.
- Map to a `DocumentView` containing only allowed fields and security metadata needed for checks.
- Post-check on the DTO with materialized `ownerId`/`tenantId`.
- In the service, do not log the full entity or write unauthorized cache entries before the post-check.
- If DB security is complex, query by tenant/grants upfront.

Merely adding `@Transactional(readOnly = true)` does not always guarantee the post-check expression runs **inside the transaction**; AOP advisor ordering affects the lifecycle. Run integration tests against your real Spring/JPA configuration and do not mask bugs with indiscriminate Open Session in View.

## 30. List of common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Only `@PreAuthorize("authenticated()")` on getById | Users guessing IDs can fetch others' documents | Authority + owner/tenant/ACL |
| Comparing `returnObject.ownerId` with username in a different ID system | Wrong ALLOW/DENY | Normalize canonical actor ID |
| `returnObject` taking owner from caller's declaration | Fake post-check, IDOR still happens | Owner from trusted database |
| `@PostAuthorize` on a money-transfer method | Side effect happens before deny | Check object before write |
| Assuming rollback always undoes every side effect | Message/email/payment already sent | Transaction/outbox and pre-check |
| Defaulting ADMIN role to read all tenants | Cross-tenant data leak | Dedicated capability and tenant scope |
| Not handling null | SpEL error or contract-violating response | NotFound/explicit null policy |
| Returning `Optional` while expression accesses properties directly | Wrong type or null semantics | Test exact type or return DTO/non-null |
| Using `@PostAuthorize` on `List` as if single object | Fails to check each element | `@PostFilter` or scoped query |
| Using `@PostFilter` for million-row lists | Broken performance/pagination | Repository-level filtering |
| Querying then logging the full document | Data leak before post-check | Never log/cache PII before authorizing |
| Self-invocation via `this` | AOP advisor does not run | Call proxied bean/domain guard |
| JPA lazy owner with closed session | LazyInitializationException in SpEL | Materialized DTO/appropriate query |
| Only testing users lacking permission | Fails to catch users with permission but wrong owner | BOLA negative tests |
| Only testing HTTP 403 | Unclear which filter denied | Service proxy test + spy |
| Not constraining tenant in query | Reads excessive unnecessary data | Scoped query and policy |
| Relying on @PostFilter for bulk writes | Silent partial update/side effect | All-or-nothing policy before command |
| Method security config not enabled | Annotation does not run | `@EnableMethodSecurity` and tests |
| Instantiating objects with `new` | Bypasses Spring proxy | Bean from Spring context |
| Treating post-check as permanent ownership | Owner/ACL may change before next write | Recheck inside transaction |

## 31. Checklist for deploying ownership-checking @PostAuthorize

1. Is this method a **side-effect-free read** or is it writing data?
2. Is `@EnableMethodSecurity` enabled in the real context?
3. Does the caller pass through the Spring proxy/advisor?
4. Is there a functional `@PreAuthorize` to block before DB reads?
5. Is `returnObject` the exact non-null/DTO type SpEL expects?
6. Do `ownerId`/`tenantId` come from a trusted server record?
7. Does actor identity use a canonical ID in the same system as `ownerId`?
8. Are tenant/membership verified before comparing against the document?
9. Does the policy support ACLs, delegation, project grants, or tenant-wide capabilities if the business permits?
10. Do states like LOCKED/ARCHIVED result in DENY?
11. Is someone with a high role but lacking an object grant DENYed?
12. Is someone with the same owner name but a different tenant DENYed when required?
13. Do null/missing resources follow 404 or 403 per contract?
14. Is there an enumeration risk from differing responses/timing?
15. Is sensitive data logged/cached/published before the post-check?
16. Are there lazy JPA properties causing SQL after the transaction closes?
17. For lists, should `@PostFilter` or a scoped query be used instead of `@PostAuthorize`?
18. For writes, is the object checked **before mutation** inside a transaction?
19. Is there TOCTOU between read and update requiring locking/versioning?
20. Do the HTTP chain and non-HTTP entry points share the same use case/policy?
21. Are there integration tests for owner ALLOW and non-owner DENY?
22. Is there a test proving a user lacking authority does not query the DB?
23. Is there a test proving a user with authority but wrong owner **does query and is then DENYed**?
24. Are methods tested against self-invocation bypass?
25. Are endpoint/controller/response handling tested for the exact version?

### Self-check questions

**Q1.** Why does `@PostAuthorize` fit `readDocument(id)` when ownership is only known after querying?  
→ It has `returnObject` containing the real owner after the method runs to check before the result reaches the caller.

**Q2.** Bob has `document:read`, but Document 42 belongs to Alice. Is Bob allowed?  
→ No. Bob passes functional permission, but the owner/tenant/ACL post-check must DENY when no grant exists.

**Q3.** Does `@PostAuthorize("returnObject.owner == authentication.name")` protect all multi-tenant documents?  
→ Not automatically. You must compare tenant, normalize actor ID, and consider other permissions.

**Q4.** Does a post-check DENY mean the document was never read from the DB?  
→ No. The method body already read it and may have mapped/logged/cached it before the post-check.

**Q5.** Should a post-check be the sole gate for `renameDocument`, which writes to the DB?  
→ No. Check ownership before writing and manage transactions/locking.

**Q6.** Can a null `returnObject` safely have `returnObject.ownerId` accessed?  
→ No. Null/missing must be handled with a clear contract, usually throwing not-found before any return object exists.

**Q7.** If a method returns `List<DocumentView>`, does `@PostAuthorize` automatically loop through each item?  
→ No. Use `@PostFilter` for supported sets, or better yet a scoped query if the list is large.

**Q8.** Why can calling `this.readSecured(id)` be dangerous?  
→ Self-invocation bypasses Spring AOP proxy method-security interceptors in standard proxy configurations.

**Q9.** Why is merely receiving HTTP 403 insufficient to prove an owner post-check?  
→ 403 can come from an HTTP filter, CSRF, or a pre-check; you must test the service bean/spy and pinpoint the checkpoint.

**Q10.** An actor was owner at read time and wants to update in a later request; can the old post-check result be reused for the write?  
→ No. Permissions and state can change; rechecking at write time is required.

## Conclusion

**When ownership is only known after querying, `@PostAuthorize` is the right tool for read-only methods**: the method builds `returnObject` from a trusted source, and Spring Security decides whether to return the result to the caller. To be safe, combine a functional pre-check, an owner/tenant/ACL/state post-check, normalized actor IDs, and direct service invocation tests. Because the body runs before the post-check, **never use `@PostAuthorize` as the sole permission gate for writes/side effects**; write commands must verify permissions on the real entity inside a transaction before mutation. For highly sensitive data or large sets, queries already scoped by permissions in the repository are usually more efficient and reduce leak surface.

## Official references

1. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — `@PostAuthorize`, `returnObject`, interceptors, IDOR, and transaction coordination.
2. [Spring Security 7.0 — Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html) — method authorization architecture and return-object support in the new line.
3. [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html) — `@WithMockUser` and testing protected beans.
4. [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html) — Authentication, authorities, RoleHierarchy.
5. [Spring Security 6.5 — ACL/Domain Object Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html) — per-object permission policies.
6. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — HTTP request authorization vs. method authorization.
7. [OWASP — Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html) — per-object permission checks, preventing IDOR.
