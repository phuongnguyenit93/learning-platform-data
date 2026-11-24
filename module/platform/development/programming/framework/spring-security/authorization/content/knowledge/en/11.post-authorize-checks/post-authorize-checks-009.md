# DTOs, Data Mapping, and the Risk of Losing the Authorization Layer

> **Module:** Spring Security - authorization  
> **Category:** Post-method checks  
> **Goal:** Understand the boundary between entity, DTO, projection, mapper, and method-security interceptor; know exactly which object is checked by `@PostAuthorize`/`returnObject`; recognize situations where owner/tenant/ACL metadata or getter security is lost after data conversion; design a flow that **authorizes before mapping/serializing/returning results**; and test against IDOR/BOLA, sensitive field leaks, proxy bypasses, and side effects.

## 1. Problem: DTO contains only return data, while permission depends on data absent from the DTO

Suppose the database has an entity:

```java
public class Document {
    private Long id;
    private String title;
    private String content;
    private String ownerUserId;
    private String tenantId;
    private boolean confidential;
    // getters and business methods...
}
```

The API does not want to expose `ownerUserId` and `tenantId` in the JSON response, so the mapper outputs only:

```java
public record DocumentDto(Long id, String title, String content) {}
```

A service initially used `@PostAuthorize`:

```java
@PostAuthorize("returnObject.ownerUserId == authentication.name")
public Document readEntity(Long id) {
    return repository.findById(id).orElseThrow();
}
```

After refactoring, the developer changes the return type to the DTO:

```java
@PostAuthorize("returnObject.ownerUserId == authentication.name")
public DocumentDto readDto(Long id) {
    Document entity = repository.findById(id).orElseThrow();
    return mapper.toDto(entity);
}
```

The problem: **`returnObject` is now `DocumentDto`**, no longer `Document`. It has no `ownerUserId` property. The expression above can raise a SpEL evaluation error because the property does not exist; never assume Spring silently skips it and permits access. “Quick fixes” like deleting the annotation or replacing it with `isAuthenticated()` are what introduce **IDOR/BOLA** vulnerabilities, since callers can guess IDs of other documents.

**Core principle:** converting entity → DTO is not purely a presentation decision. If authorization relies on properties of the returned object, **the return object's type and contents are part of the security contract**. Any change to DTOs, mappers, projections, or service boundaries requires reviewing the corresponding authorization policy.

## 2. Execution order determines what gets seen

```text
Request / caller
       |
       v
Spring service proxy
       |
       v
@PreAuthorize (if present)
       |
       +--- DENY: method body does not run
       |
       v
Service method body
   1. Repository loads Document
   2. Mapper builds DocumentDto
   3. May log/cache/event/side effect
   4. Method returns DocumentDto
       |
       v
@PostAuthorize on returnObject = DocumentDto
       |
       +--- DENY: do not return normal DTO to caller
       |
       v
Controller / JSON serializer / GraphQL...
       |
       v
Client receives result
```

Key principles:
- `@PostAuthorize` checks **the return value of the method actually intercepted by Spring AOP**, without automatically reverting to the original entity that the mapper discarded.
- The mapper already ran **before** `@PostAuthorize` if the mapper sits inside the method body.
- A post-check denial can stop the return value from reaching the caller, **yet cannot undo** what the mapper/log/cache/external service already did.
- The same object may pass through several stages: JPA entity → projection → domain model → DTO → HTTP response. Where the security gate sits must be defined clearly.
- Permission to read **the whole document** and permission to view **each field** are two distinct decisions. Owner-only `@PostAuthorize` does not automatically filter sensitive fields out of an allowed DTO.

For DB-writing methods, using `@PostAuthorize` as the primary ownership gate is dangerous because the body already executed the mutation. The right pattern is usually **load entity → check policy → mutate or map → return result**.

## 3. How does Spring Security evaluate `returnObject`?

Enable method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {}
```

In Spring Security Servlet 6.5, `@PostAuthorize` is handled by `AuthorizationManagerAfterMethodInterceptor` and `PostAuthorizeAuthorizationManager`. Once the service method returns a result, the SpEL expression is evaluated with `returnObject` bound to the returned object. If unauthorized, `AccessDeniedException` is normally raised; in HTTP, proper exception handling typically returns 403 for an authenticated actor.

Official documentation illustrates:

```java
@PreAuthorize("hasAuthority('account:read')")
@PostAuthorize("returnObject.owner == authentication.name")
public Account readAccount(Long id) {
    return repository.findById(id).orElseThrow();
}
```

Here `returnObject` is `Account`, so `owner` must resolve on the `Account` type or its matching accessor. If you change the return type to a DTO, **re-verify the expression and policy**. Changing the signature can alter post-check semantics even when method name, route, and authentication stay identical.

**Do not assume `@EnableMethodSecurity` is enabled:** Spring Boot Security starter does not activate method security automatically. Never assume an annotated method will be blocked if called via `this.method()`, an object created with `new`, or a call path bypassing the proper proxy.

## 4. When the mapper drops the authorization field: three different outcomes

Suppose legacy code had:

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentEntity getDocument(long id) { ... }
```

After migration, the mapper produces:

```java
public record DocumentDto(long id, String title, String content) {}
```

There are three ways people react:

| Approach | Result | Assessment |
| --- | --- | --- |
| Keep `@PostAuthorize` accessing non-existent `ownerId` | Can throw SpEL error at post-check | Not success; must fix method/policy contract |
| Remove `@PostAuthorize` “to get the API working again” | Endpoint risks returning any document with a valid ID | **Unsafe** without another gate |
| Use `@PostAuthorize("isAuthenticated()")` | Only checks login, drops ownership | **Insufficient** for private documents |
| Keep verified metadata inside an inspectable return type | Post-check has required data | Can work, yet must control serialization and source data |
| Move object-policy into service **after loading entity and before mapping** | No need to expose sensitive metadata in DTO | **Usually easiest to verify and safest** |
| Use a secured loader via bean proxy, then map afterward | `@PostAuthorize` evaluates entity/secured view before mapper | Viable if all call paths go through the proxied loader |

**Note:** a missing property on the DTO must not be interpreted as “Spring Security fails open”; the real risk is usually **humans removing/misplacing the checkpoint** or **the mapper dropping data needed by the expression** and then picking an overly broad fix. Tests must catch this change before deployment.

## 5. Preferred solution: check the real entity before mapping to DTO

Read-only service example:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    private final DocumentRepository repository;
    private final DocumentPolicy policy;
    private final ActorResolver actors;
    private final DocumentMapper mapper;

    public DocumentQueryService(DocumentRepository repository,
                                DocumentPolicy policy,
                                ActorResolver actors,
                                DocumentMapper mapper) {
        this.repository = repository;
        this.policy = policy;
        this.actors = actors;
        this.mapper = mapper;
    }

    @PreAuthorize("hasAuthority('document:read')")
    @Transactional(readOnly = true)
    public DocumentDto getDocument(long id) {
        Actor actor = actors.requireAuthenticatedActor();

        Document document = repository
            .findByIdAndTenantId(id, actor.activeTenantId())
            .orElseThrow(DocumentNotFoundException::new);

        policy.requireCanRead(actor, document);

        // Run mapper ONLY AFTER entity permission is verified.
        return mapper.toDto(document);
    }
}
```

**Integration snippet, not a standalone `javac` program:** `DocumentRepository`, `DocumentPolicy`, `ActorResolver`, `Document`, `DocumentMapper`, `DocumentDto`, `Actor`, and exceptions must be defined by the application. `@Transactional(readOnly=true)` does not enforce security itself, but manages transaction/persistence context as designed.

Sequence:
1. `@PreAuthorize` checks functional permission.
2. `ActorResolver` retrieves canonical user ID and tenant from trusted Authentication/membership.
3. Repository restricts the query to the verified tenant.
4. `policy.requireCanRead` checks owner/ACL/delegation/state on the real entity.
5. **Only after ALLOW** does the mapper construct the response DTO with only permitted fields.
6. The framework then serializes the DTO to the HTTP response.

This pattern keeps owner/tenant out of public DTOs **without losing data needed for authorization**. It also avoids mapping sensitive content and logging DTOs before an ownership decision is made.

One trade-off to manage: when loading the object and deciding inside the service, it is no longer a `@PostAuthorize` on the DTO. That is **not a loss of security**, provided the policy genuinely runs on every call path and transaction/proxy boundaries are sound. Choose the enforcement point based on data permissions and architecture, rather than forcing the annotation everywhere.

## 6. Option that keeps `@PostAuthorize`: return type with trusted metadata

In some projects wanting to keep declarative post-checks, you can design a return type holding metadata for internal authorization use:

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

public record SecuredDocumentView(
    long id,
    String title,
    String content,
    @JsonIgnore String ownerUserId,
    @JsonIgnore String tenantId
) {}
```

Service:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize(
    "returnObject != null and "
    + "@documentAccess.canRead(authentication, returnObject)"
)
public SecuredDocumentView read(long id) {
    Document document = repository.findById(id).orElseThrow();
    return mapper.toSecuredView(document);
}
```

Policy bean:

```java
@Component("documentAccess")
public class DocumentAccess {
    private final ActorResolver actorResolver;

    public DocumentAccess(ActorResolver actorResolver) {
        this.actorResolver = actorResolver;
    }

    public boolean canRead(Authentication auth,
                           SecuredDocumentView dto) {
        if (auth == null || dto == null || !auth.isAuthenticated()) {
            return false;
        }
        Actor actor = actorResolver.requireActor(auth);
        if (!actor.activeTenantId().equals(dto.tenantId())) {
            return false;
        }
        return actor.id().equals(dto.ownerUserId());
    }
}
```

These are **three integration snippets** needing Spring Security, Jackson, and project types. `@JsonIgnore` is a Jackson serialization annotation; it can hide properties from JSON in the corresponding configuration, **yet it is not a universal security boundary**. The DTO still holds `ownerUserId`/`tenantId` in memory and other serializers/loggers may behave differently. You must test the exact final JSON.

Conditions for this approach to be safe:
- `mapper.toSecuredView` must populate owner/tenant **from the trusted entity**, never from the HTTP request body.
- The method must return `SecuredDocumentView` directly through the `@PostAuthorize` proxy.
- The `documentAccess` bean must verify tenant and ACL/state per real policy.
- The DTO must not be logged/cached/serialized before the post-check.
- JSON must not leak owner/tenant if those fields should stay private.
- Changing mapper or DTO field names must have regression tests.

**When a post-check on the DTO is unnecessary, checking before mapping is usually easier to audit.**

## 7. Post-checking the entity in a separate service, then mapping: clean bean boundaries

Another architecture:

```java
@Service
public class SecuredDocumentLoader {
    private final DocumentRepository repository;

    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize(
        "returnObject != null and "
        + "@documentPolicy.canRead(authentication, returnObject)"
    )
    public Document load(long id) {
        return repository.findById(id)
            .orElseThrow(DocumentNotFoundException::new);
    }
}
```

DTO facade:

```java
@Service
public class DocumentFacade {
    private final SecuredDocumentLoader loader;
    private final DocumentMapper mapper;

    public DocumentFacade(SecuredDocumentLoader loader,
                          DocumentMapper mapper) {
        this.loader = loader;
        this.mapper = mapper;
    }

    public DocumentDto read(long id) {
        Document authorized = loader.load(id); // Through bean proxy.
        return mapper.toDto(authorized);
    }
}
```

**These are architectural snippets**, not complete Java files (needing constructor/DI for loader, domain types, imports, transaction semantics). Purpose:
- `SecuredDocumentLoader.load` returns `Document`, so `@PostAuthorize` sees the real owner/tenant.
- Calling `loader.load` traverses a Spring bean proxy; if DENY, the facade never receives the entity to map.
- The public DTO does not need to retain owner metadata.

**Boundaries to guarantee:**
- Do not self-invoke `this.load(...)` inside the same class, as self-invocation can bypass Spring AOP.
- Never instantiate the loader with `new`; inject the real bean.
- No other controller/mapper calls the repository directly to bypass the loader.
- Only expose permitted DTO fields; an object-level post-check is not a field sanitizer.
- With JPA lazy relations, mapping after loading may require a live transaction; otherwise return a **materialized secured view** and check policy before mapping to the public DTO.
- If the loader bean returns a managed entity and callers can mutate it, keep the contract read-only and avoid letting callers obtain an entity and write outside policy.

This is a good pattern when you genuinely want **entity post-checks** in method security, though not necessarily better than in-service policy checks. The first requirement is **zero bypass paths**.

## 8. What does `@PostAuthorize` inspect if the service returns Optional, List, or Page?

Not all return types share the same semantics:

| Return type | Actual `returnObject` | Risks |
| --- | --- | --- |
| `Document` | A single entity | Owner/tenant may be lazy-loaded, metadata from DB |
| `DocumentDto` | DTO after mapper | Metadata needed for check may have been dropped |
| `Optional<Document>` | May be a wrapper or a result handled specially by version | Cannot guess `returnObject.ownerId` will resolve properly |
| `List<DocumentDto>` | A collection | `returnObject.ownerId` is not a property of individual elements |
| `Page<DocumentDto>` | Page containing items/metadata | Never use `@PostFilter` as a pagination cure if source isn't scoped |
| `Stream<Document>` | May be lazy/deferred | Loading/serialization can occur after the expected boundary |
| `ResponseEntity<DocumentDto>` | HTTP wrapper and body | Expression must handle wrapper, not assume body directly |
| `byte[]` / file stream | Already-built payload or active stream | Ownership is absent from return value |

**Never build policies on untested shape assumptions.** In many cases, the policy should inspect the object before the mapper strips metadata, then return the exact API contract.

For lists:
- `@PostAuthorize` makes a single decision on the entire list `returnObject`, not iterating item by item like a single object.
- `@PostFilter("filterObject.ownerId == authentication.name")` evaluates each item for supported collections/arrays/Maps/Streams.
- Yet post-filtering after DB reads can be expensive, break counts/pagination, and risk putting unauthorized data into memory/logs/caches.
- For large lists and exports, **querying by tenant, actor, and ACL directly in the DB** is usually better.

## 9. `@PostFilter` when the DTO no longer has `ownerId`

Original example:

```java
@PostFilter("filterObject.ownerId == authentication.name")
public List<DocumentEntity> listDocuments() {
    return repository.findAll();
}
```

After switching to:

```java
@PostFilter("filterObject.ownerId == authentication.name")
public List<DocumentDto> listDocuments() {
    return repository.findAll().stream()
        .map(mapper::toDto)
        .toList();
}
```

Same bug: `filterObject` is now `DocumentDto`; if the DTO lacks `ownerId`, the expression is no longer valid. Never remove the filter “to clear the error” and return the whole list.

Better options:
1. Query only documents the actor is allowed to access, with tenant/ACL scoping in the DB, then map.
2. Filter a collection of **entities/secured views** by policy **before mapping** (only suitable for small sets with acceptable performance).
3. Use a policy bean `@docPolicy.canRead(authentication, filterObject)` if each DTO retains sufficient trusted metadata, while still evaluating performance.
4. Use a guarded loader service/facade with full-flow tests.

**Do not confuse `@PostFilter` with `@PreFilter`**: one filters output after the method, the other filters an input collection before the body. Neither knows the real owner if elements are caller-supplied DTOs.

## 10. DTO refactoring can strip away getter-level security

Suppose a domain object has a method:

```java
public class AccountView {
    private final String email;

    @PreAuthorize("hasAuthority('account:email:read')")
    public String getEmail() {
        return email;
    }
}
```

A developer creates a DTO:

```java
public record AccountDto(long id, String email) {}
```

If a mapper calls `entity.getEmail()` on an unadvised path, or uses direct field access during mapping, and copies email into the DTO, **the annotation on the entity getter does not automatically transfer to the DTO accessor**. Jackson serializes `AccountDto.email()` normally; it does not look back at `AccountView.getEmail()`'s annotation.

Distinguish:
- `@PostAuthorize` on a method returning an entity/DTO gates **the entire result**.
- Method-security annotations on getters gate **specific getter calls**, taking effect only when the proper proxy/advice executes.
- DTOs are usually plain records/beans without security proxies by default.
- Mappers (MapStruct, ModelMapper, manual mapping, reflection...) do not automatically invoke authorization checkpoints unless you design and test them that way.

**Anti-pattern:** believing a `@PreAuthorize` on an entity getter or repository method “follows the data” through every DTO, JSON payload, and cache. Security annotations guard **method invocations** under runtime conditions, not immutable taint labels attached to every byte of data.

## 11. `@AuthorizeReturnObject` differs from `@PostAuthorize`

Spring Security 6.5 provides `@AuthorizeReturnObject` to proxy a return object and apply method-security annotations to methods on that object. The official architecture example allows protecting a return object's getter:

```java
public class User {
    private String email;

    @PreAuthorize("hasAuthority('user:email:read')")
    public String getEmail() {
        return email;
    }
}
```

A bean returning `User` can use:

```java
@AuthorizeReturnObject
public User findUser(long id) {
    return repository.loadUser(id);
}
```

The two ideas **are not equivalent**:
- `@PostAuthorize("...returnObject...")`: a post-method check that can DENY the entire return value.
- `@AuthorizeReturnObject`: attempts to proxy the returned object to guard calls to its methods/getters per annotations on those methods.

If you switch from `User` to `UserDto` without protected getters, or a mapper copies email into a plain DTO, **never assume the entity proxy or old annotations still protect DTO serialization**.

With `@AuthorizeReturnObject`, verify version, proxyable types, `final`/record constraints, nested return types, AOT runtime hints, and JSON serialization; Spring Security docs note the framework may attempt to proxy value types like `String`/`Integer` if applied too broadly at class level. Never sprinkle `@AuthorizeReturnObject` onto every DTO assuming field-level security is solved.

For sensitive APIs, it is usually easier to audit when **the service checks policy and builds a DTO containing only permitted fields** before the serializer ever sees it.

## 12. Serializing to JSON is not an authorization step

A DTO:

```java
public record UserProfileDto(
    String name,
    String email,
    String phone,
    String nationalId
) {}
```

An actor might be allowed to view the basic profile yet **not** `nationalId` or `phone`. An owner-only `@PostAuthorize` permits **the entire DTO**, without trimming unauthorized fields.

Separate:
- **Object-level authorization:** may the actor view User 42?
- **Field-level authorization:** may the actor view User 42's email, phone, and national ID?
- **Serialization allowlist:** JSON emits only fields permitted by policy.
- **Response shaping:** different roles/relationships may need different DTOs.

Example:

```java
public record PublicProfileDto(String displayName) {}

public record OwnProfileDto(
    String displayName,
    String email,
    String phone
) {}
```

Once service policy determines trusted relationships and authorities, the mapper picks the right DTO. Never accept `?includeSensitive=true` from the client and blindly expose all fields; query flags only express **intent** and must have matching permissions.

**`@JsonIgnore`, `@JsonView`, and Jackson filters can help serialize the right shape**, yet they do not replace source-of-truth authorization. Test JSON as well as export/GraphQL endpoints because one DTO may be serialized through multiple adapters.

## 13. A minimal DTO approach and minimal policy

A design adhering to data minimization:

```text
Document entity:
    id, ownerId, tenantId, title, content, secretMetadata, status

DocumentPolicy:
    canRead(actor, document)
    canReadSecretMetadata(actor, document)

Public DocumentDto:
    id, title, permittedContent
```

Service pattern:

```java
@PreAuthorize("hasAuthority('document:read')")
@Transactional(readOnly = true)
public DocumentDto read(long documentId) {
    Actor actor = actorResolver.requireAuthenticatedActor();
    Document doc = documents.findByIdInTenant(
        documentId, actor.activeTenantId()
    ).orElseThrow(DocumentNotFoundException::new);

    policy.requireCanRead(actor, doc);

    return new DocumentDto(
        doc.getId(),
        doc.getTitle(),
        policy.canReadContent(actor, doc)
            ? doc.getContent() : null
    );
}
```

**Integration snippet:** `Actor`, `Document`, repo, and policy are domain contracts. If content cannot be read, using a different DTO or omitting the property may be better than returning `null`; shape choices must follow the API contract.

A test must verify **unauthorized fields do not appear in JSON**, not just status 200. Even an owner's document may hold sensitive data belonging to someone else, so “owner allowed” does not mean “show every DB column”.

## 14. MapStruct, manual mappers, and mapping libraries are not authorizers

MapStruct is a mapping code generator; other mappers rely on reflection/conventions. They do not automatically turn field copying into an authorization decision.

Hypothetical mapping example:

```java
@Mapper(componentModel = "spring")
public interface DocumentMapper {
    DocumentDto toDto(Document entity);
}
```

The annotation above only requests a Spring mapper bean when using MapStruct with the right dependency/annotation processor. It **does not** say “map only when principal is authorized”.

Bugs to catch when reviewing mappers:
- A target field maps from a different property than the post-check expected.
- `tenantId`/`ownerId` is omitted, leaving the security expression without data.
- `source.userId` is mapped as owner when the true owner lives in another relation.
- Child entity collections containing confidential information are mapped.
- Lazy relations are mapped directly, triggering SQL outside transactions.
- Mapper calls a protected getter where the call **bypasses the proxy** so method-security annotations never run.
- A mapping function is invoked from another endpoint before policy guards.
- Default DTO includes more fields than the contract and Jackson serializes all of them.
- An update mapper accidentally lets clients overwrite `ownerId`/`role` when a DTO is used for input.

**Prevention:** treat mappers as data-transformation code, not authority checks. Place policies at service/repository boundaries, and test mappings/JSON payloads after authorization checks.

## 15. JPA projections and native queries alter post-check data

A Spring Data repository can return a projection:

```java
public interface DocumentSummaryProjection {
    Long getId();
    String getTitle();
}
```

Service:

```java
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
public DocumentSummaryProjection getSummary(long id) {
    return repository.findSummaryById(id).orElseThrow();
}
```

If the projection has no `ownerId`, the post-check lacks required inputs. Never try accessing a missing property and then “drop the rule”. Instead:
- Return an internal projection containing `ownerId`/`tenantId` for policy inspection, then map to a public DTO after authorizing;
- Refactor the query to `findReadableSummaryById(id, actorId, tenantId)` scoped directly in the DB;
- Load a minimal entity with policy metadata, run the guard, then map;
- Use an owner/ACL policy bean querying the exact resource with clear DB cost.

**Open projections / nested projections** may involve SpEL/lazy access; do not assume they behave like full entities or materialized DTOs. Runtime tests against a real DB and mappings are required.

A query-optimized projection containing only `id, title` can be great for performance, **provided the query already scopes permissions**, eliminating the need for an owner property at post-check.

## 16. Query scoping is usually better than altering DTOs to retain `ownerId`

Instead of loading by ID and checking afterward:

```sql
SELECT *
FROM documents
WHERE id = :document_id;
```

Push tenant/owner/ACL directly into the query:

```sql
SELECT d.id, d.title, d.content
FROM documents d
WHERE d.id = :document_id
  AND d.tenant_id = :authorized_tenant
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

Parameters `authorized_tenant` and `actor_id` must come from **verified** Authentication/membership, never from self-declared JSON/body/query values. If an actor has tenant-wide read permission, add an explicit conditional branch per policy; never use a global `ROLE_ADMIN` to skip tenant checks.

Advantages:
- Out-of-scope entities never reach the service via this query path.
- DTOs can remain minimal (no need to carry `ownerId` for post-checks).
- Paging, sorting, and counting naturally align with permissions.
- Reduces risk of logging/caching data for the wrong actor.
- Avoids duplicate queries if a post-authorizer would otherwise look up ACLs again.

This is **authorization enforced at the data access scope**; review SQL/ORM queries carefully so other queries do not omit conditions. It can be paired with a service-layer domain policy for defense in depth.

## 17. Pagination: DTO lists + post-filtering often produce wrong results

Suppose:
- DB contains 1,000 documents.
- Alice only has permission to view 10 documents.
- Repository returns the first 20 documents and the service maps them to DTOs.
- `@PostFilter` drops 18 documents not belonging to Alice.

The API returns 2 items even though more items belonging to Alice exist on later pages. `totalElements` in `Page` may not match the filtered count. When using `Page<DocumentDto>` and external filtering, behavior must also be checked per version/collection type.

**Recommended pattern:** query within the permission scope **before applying LIMIT/OFFSET or keyset pagination**, then map each record and return count metadata calculated in the same scope. If business logic allows multiple ACL branches, the SQL/query specification must express all of them:
- same tenant;
- owner or valid ACL grant;
- classification/state;
- audience/project relationship;
- READ permission;
- ordering and page limits.

A proper list query also prevents leaking unauthorized record counts through totals/search suggestions.

## 18. Caching: before or after authorization checks?

Dangerous example:

```java
@Cacheable(cacheNames = "documents", key = "#id")
@PostAuthorize(
    "@documentPolicy.canRead(authentication, returnObject)"
)
public DocumentDto read(long id) {
    return mapper.toDto(repository.findById(id).orElseThrow());
}
```

Depending on the ordering of `@Cacheable`, method-security advisors, and the cache key, an object may be cached before policy applies, or a cached DTO may be served to another actor. If the DTO contains decrypted/unminimized fields, the risk is even higher.

**Do not infer AOP advisor order** from annotation placement in source code. Inspect runtime configuration and test.

Safe strategies:
1. Cache raw documents inside a service/repository with dedicated ACL/tenant rules and **always** authorize on every access before returning/mapping data.
2. Or cache by keys incorporating actor/tenant/permission version with complete invalidation (harder).
3. Never cache a permanent “ALLOW” just because an actor used to be the owner.
4. Never serve a DTO filtered for actor A to actor B if field visibility differs.
5. Revalidate permissions when roles, ownership, ACLs, or tenant membership change per business rules.
6. Audits/traces must not record sensitive DTOs before authorization.

Caching is a performance optimization, **not a place to create or transfer permissions**.

## 19. `@Transactional` and mappers: matching real timing

Suppose:

```java
@Transactional(readOnly = true)
@PostAuthorize(
    "@documentPolicy.canRead(authentication, returnObject)"
)
public DocumentDto read(long id) {
    Document doc = repository.findById(id).orElseThrow();
    return mapper.toDto(doc);
}
```

If the mapper touches lazy properties, that may execute SQL while the transaction is open (depending on proxy nesting). `@PostAuthorize` evaluates the DTO after the body returns; JPA lazy relations may still have or may have lost the persistence context depending on advisor ordering and transaction boundaries. `@PostAuthorize` reading lazy entity owners directly is also prone to `LazyInitializationException` when the after-method interceptor runs outside the session.

Practical points:
- Do not rely on `Open Session in View` to mask architectural flaws.
- Materialize every property needed by policy **inside an explicit transaction**.
- Avoid returning lazy entities directly as JSON responses.
- Test with OSIV disabled if production runs that way.
- Never let a mapper call external services or write data before ownership checks.
- For writes, authorize on the real entity **before mutation**, using versioning/locking against TOCTOU.

There is no single default order you can use as proof that “post-check definitely runs inside the transaction in every project”. Advisor configuration and tests decide.

## 20. `@PostAuthorize` does not solve side-effect protection

Dangerous code:

```java
@PostAuthorize(
    "@documentPolicy.canEdit(authentication, returnObject)"
)
public DocumentDto rename(long id, String title) {
    Document doc = repository.findById(id).orElseThrow();
    doc.rename(title);
    repository.save(doc);
    return mapper.toDto(doc);
}
```

If the policy denies at post-check, the database **may already have changed**, messages/emails may already have been sent, and logs/caches may already have written data. Transaction rollback depends on boundaries and advisor order and cannot be assumed by default; external side effects do not automatically roll back either.

Proper command pattern:

```java
@PreAuthorize("hasAuthority('document:rename')")
@Transactional
public DocumentDto rename(long id, String title) {
    Actor actor = actors.requireActor();
    Document doc = documents.findForUpdateInTenant(
        id, actor.activeTenantId()
    ).orElseThrow(DocumentNotFoundException::new);

    policy.requireCanRename(actor, doc);
    doc.rename(title);
    return mapper.toDto(doc);
}
```

In the command:
1. Load entity **within the verified tenant**.
2. Check permissions on the entity before mutation.
3. Manage version/locking or conditional SQL updates.
4. Only map and return the DTO after authorization passes.
5. Do not dispatch external side effects until consistency is controlled (transactional outbox when needed).

This is an integrated domain snippet; custom methods must be implemented. Never grant edit permission from a client-declared `ownerId`.

## 21. Standalone Java 17: a mapper dropping owner plus a weak post-check leaks data

The following example is **plain Java**, without Spring Framework, Spring Security, JPA, or JSON serializers. Its goal is illustrating **the logical mechanism**: a public DTO omits owner/tenant; if the mapper already built the DTO and only general permission remains checked, an actor can receive someone else's data. The safe flow verifies entity permissions before mapping.

Save **`DtoAuthorizationDemo.java`**:

```java
import java.util.Map;
import java.util.Set;

public class DtoAuthorizationDemo {

    record Actor(String id, String tenant, Set<String> rights) {}
    record Document(long id, String owner, String tenant,
                    String title, boolean locked) {}
    record PublicDto(long id, String title) {}

    private static final Map<Long, Document> DB = Map.of(
        42L, new Document(42, "alice", "A", "Alice plan", false),
        43L, new Document(43, "bob", "A", "Bob plan", false),
        44L, new Document(44, "bob", "B", "Other tenant", false),
        45L, new Document(45, "alice", "A", "Locked", true)
    );

    private static int mapped = 0;

    static PublicDto toDto(Document doc) {
        mapped++;
        return new PublicDto(doc.id(), doc.title());
    }

    static String unsafeRead(Actor actor, long id) {
        Document doc = DB.get(id);
        if (doc == null) return "NOT_FOUND";

        // Convert to DTO first; owner/tenant are no longer in DTO.
        PublicDto result = toDto(doc);

        // Anti-pattern: skipping owner check because DTO lacks property.
        if (!actor.rights().contains("document:read")) {
            return "DENY capability";
        }
        return "ALLOW dto#" + result.id();
    }

    static String safeRead(Actor actor, long id) {
        if (!actor.rights().contains("document:read")) {
            return "DENY capability";
        }

        Document doc = DB.get(id);
        if (doc == null) return "NOT_FOUND";
        if (!actor.tenant().equals(doc.tenant())) {
            return "DENY tenant";
        }
        if (doc.locked()) return "DENY locked";

        boolean owner = actor.id().equals(doc.owner());
        boolean tenantGrant =
            actor.rights().contains("document:read:tenant");

        if (!owner && !tenantGrant) return "DENY owner";

        PublicDto dto = toDto(doc); // Map only after ALLOW.
        return "ALLOW dto#" + dto.id();
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "A", Set.of("document:read"));
        Actor bob = new Actor(
            "bob", "A", Set.of("document:read"));
        Actor manager = new Actor(
            "manager", "A", Set.of(
                "document:read", "document:read:tenant"));
        Actor guest = new Actor("guest", "A", Set.of());

        System.out.println("Unsafe Bob reads Alice: "
            + unsafeRead(bob, 42));
        System.out.println("Safe Bob reads Alice: "
            + safeRead(bob, 42));
        System.out.println("Safe Alice own: "
            + safeRead(alice, 42));
        System.out.println("Safe manager same tenant: "
            + safeRead(manager, 42));
        System.out.println("Safe Bob cross tenant: "
            + safeRead(bob, 44));
        System.out.println("Safe Alice locked: "
            + safeRead(alice, 45));
        System.out.println("Safe guest: "
            + safeRead(guest, 42));
        System.out.println("Safe missing: "
            + safeRead(alice, 999));
        System.out.println("DTO mappings performed: " + mapped);
    }
}
```

Run with JDK 17 or higher:

```bash
javac DtoAuthorizationDemo.java
java DtoAuthorizationDemo
```

**Exact** stdout:

```text
Unsafe Bob reads Alice: ALLOW dto#42
Safe Bob reads Alice: DENY owner
Safe Alice own: ALLOW dto#42
Safe manager same tenant: ALLOW dto#42
Safe Bob cross tenant: DENY tenant
Safe Alice locked: DENY locked
Safe guest: DENY capability
Safe missing: NOT_FOUND
DTO mappings performed: 3
```

Explanation:
1. Bob has general read permission, yet does not own Document 42. `unsafeRead` still ALLOWs because it **intentionally skipped the owner check after the DTO lost metadata**.
2. `safeRead` denies Bob before building the DTO.
3. Alice is the owner in the right tenant, so ALLOW.
4. Manager has explicit `document:read:tenant`, so ALLOW within the same tenant; this is a capability **explicitly granted by the model**, not a default manager/admin privilege.
5. Bob cannot read a tenant B document even if the owner of document B is also named “bob”.
6. The LOCKED document is DENYed per the demo business contract.
7. Guest lacks functional read permission.
8. Non-existent ID returns NOT_FOUND.
9. Exactly **3 mappings** occurred: once in the unsafe flow, and twice for the two ALLOW cases in the safe flow. Requests denied by the safe flow never mapped data.

**Limitations:** this snippet only simulates a bug caused by a developer omitting authorization; it **does not simulate Spring Security failing open when SpEL misses a property**. Java records/Maps are fake data; there is no Authentication, proxy, Jackson, DB, transaction, or real ACL. Never copy `unsafeRead` into production.

## 22. Mapper unit tests must not replace policy unit tests

With DTO mapping, two separate test groups are needed.

### A. Testing mapper shape

```java
@Test
void mapsOnlyPublicFields() {
    Document entity = documentWithSensitiveFields();

    DocumentDto dto = mapper.toDto(entity);

    assertThat(dto.id()).isEqualTo(entity.getId());
    assertThat(dto.title()).isEqualTo(entity.getTitle());
    // Verify DTO does not leak secrets per contract.
}
```

### B. Testing policy on the entity

```java
@Test
void sameRoleButDifferentOwnerIsDenied() {
    Actor bob = actor("bob", "tenant-A", "document:read");
    Document aliceDoc = document(
        42L, "alice", "tenant-A", false);

    assertThat(policy.canRead(bob, aliceDoc)).isFalse();
}

@Test
void sameOwnerButDifferentTenantIsDenied() {
    Actor alice = actor("alice", "tenant-A", "document:read");
    Document doc = document(
        44L, "alice", "tenant-B", false);

    assertThat(policy.canRead(alice, doc)).isFalse();
}
```

These are **JUnit 5/AssertJ snippets and domain fixtures**, not standalone Java. `documentWithSensitiveFields`, `actor`, `document`, and `policy` must be defined by the test project.

Passing mapper tests **do not** prove the service authorized before calling the mapper. Passing policy tests **do not** prove the service actually invokes the policy. Integration tests are also required.

## 23. Integration test verifying policy → mapper ordering

In a Spring integration test with the service injected through a proxy, policy and mapper spies/stubs can verify:

```java
@Test
@WithMockUser(authorities = {"document:read"})
void nonOwnerIsDeniedBeforeMapping() {
    // Repository fixture: Document 42 owned by Alice, actor Bob.
    assertThatThrownBy(() -> service.read(42L))
        .isInstanceOf(AccessDeniedException.class);

    verify(mapper, never()).toDto(any());
}

@Test
@WithMockUser(authorities = {"document:read"})
void ownerIsMappedAfterAuthorization() {
    // Fixture: actor Alice, Document 42 belongs to Alice/tenant A.
    DocumentDto dto = service.read(42L);

    assertThat(dto.id()).isEqualTo(42L);
    verify(mapper).toDto(any(Document.class));
}
```

These are snippets requiring Spring Boot Test, JUnit 5, AssertJ/Mockito, an actor resolver matching the test principal, repository fixtures, real service/proxy beans, and proper exception setup. If an integration test uses `@PostAuthorize` on a returned DTO instead of guarding before mapping, `verify(mapper, never())` **cannot pass** because the mapper in the body already ran. In that case, test according to the real contract:
- Return is DENYed when the actor lacks object permission.
- Data is not serialized/returned to the client.
- Logs/caches/external side effects do not occur before denial, or are controlled by design.

**Never write tests to reinforce wrong assumptions about Spring AOP post-check timing.**

## 24. Regression tests when DTO properties are renamed or removed

To prevent refactors from dropping security, write tests for:
1. Actor with `document:read` who is not owner → DENY.
2. Actor with right role, right owner, right tenant → ALLOW.
3. Actor matching owner in wrong tenant → DENY.
4. Granted ACL READ works; ACL WRITE does not imply READ unless policy specifies.
5. LOCKED/ARCHIVED documents handled per contract.
6. Output DTO omits `ownerUserId`/`tenantId`/`secretMetadata` if non-public.
7. If using a secured DTO with `@PostAuthorize`, expression resolves properties on **the current return type**.
8. When migrating from entity to projection/DTO, tests run against the new return type.
9. When adding another mapper for GraphQL/export, tests still enforce policy.
10. When queries return lists/pages, no out-of-scope items or counts leak.
11. Methods are invoked through Spring AOP beans, not via `new` or `this.method`.
12. On DENY, the controller has not serialized JSON and returns no sensitive error details.

A single test saying “logged-in user gets HTTP 200” has almost zero value proving object authorization. You must include negative cases with authenticated users who hold functional authority yet **lack** resource permission.

## 25. MockMvc testing both HTTP status and JSON payload

Example:

```java
@Test
void ownerGetsSafeDto() throws Exception {
    mvc.perform(get("/api/documents/42")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("document:read")
            )))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.ownerUserId").doesNotExist())
        .andExpect(jsonPath("$.tenantId").doesNotExist());
}

@Test
void nonOwnerCannotReceiveDto() throws Exception {
    mvc.perform(get("/api/documents/42")
            .with(user("bob").authorities(
                new SimpleGrantedAuthority("document:read")
            )))
        .andExpect(status().isForbidden());
}
```

**MockMvc snippets**, needing controller, route, fixtures, actor resolver, exception mapping, `spring-security-test`, and matching imports. If the contract hides existence with 404, adjust the expectation while still verifying **zero private data**. A 404 from a non-existent route does not prove authorization.

Additional tests to include:
- JSON contains no unauthorized email, token, or secret fields.
- Response Content-Type, HTTP status, and error body do not reveal the real owner.
- User with object permission lacking field-level permission receives only allowed fields.
- Guest lacking read permission never reaches the repository if a pre-check can block.
- If mapping runs before post-check, test that no data leaks into logs/caches.
- GraphQL and download/export paths enforce the same level of protection.

An HTTP 403 on POST/PATCH may come from CSRF rather than policy; for write tests, submit a valid CSRF token when required by security config and verify DB remains unchanged.

## 26. GraphQL and nested resolvers make mapping risks subtler

In REST, a service typically builds a DTO and Jackson serializes it. In GraphQL:
- Queries can select arbitrary fields in the schema.
- Child resolvers can run after parent resolvers.
- Permission to view a parent object does not imply permission to view child fields.
- DataLoaders can batch/cache results by keys lacking actor/tenant.
- DTOs/projections can pass from one resolver to another.

For example, a resolver returns a `DocumentDto` whose `ownerId` was stripped, and a child `attachments` resolver loads all files by document ID without checking the actor — that is another **BOLA** path. A post-check on the parent object does not automatically prove permission for attachments in the child resolver.

Solutions:
- Use domain policies in application services invoked by every resolver.
- Query/scope by actor + tenant for every protected resource.
- Never share DataLoader caches across actors/tenants unless keys and invalidation guarantee isolation.
- Enforce field-level policies on sensitive data.
- Test varied GraphQL selections with the same document ID and an unauthorized actor.

**Do not rely on DTO shape as an authorization policy**, because schemas/resolvers can expose additional fields that the original mapper never anticipated.

## 27. Relationship with `RoleHierarchy`

A hierarchy:

```text
ROLE_ADMIN > ROLE_EDITOR
ROLE_EDITOR > ROLE_VIEWER
```

lets an ADMIN actor satisfy `hasRole('VIEWER')` if components are configured with `RoleHierarchy`. However, a DTO omitting `ownerId` is not magically protected just because an actor holds a high role. Roles are functional permissions; document ownership, tenant, ACL, and classification are resource permissions.

Complete rule example:

```text
ALLOW readDocument(id)
    = actor has document:read
      AND document tenant is authorized
      AND (
        document.ownerId == actor.userId
        OR ACL READ grant for actor
        OR explicit tenant-wide READ capability
      )
      AND document state permits read
```

A hierarchy may grant `document:read` to `ROLE_VIEWER` and `document:read:tenant` to `ROLE_ADMIN` **if business approves**. Still, queries/policies need to see the underlying entity or canonical metadata; a minimal response DTO is not a trustworthy place to infer all security invariants.

Never try to “fix” a mapper dropping `ownerId` by broadening roles for everyone.

## 28. 403, 404, 500 when the security property disappears

Three situations:
- **403:** security expression or policy evaluates to DENY, typically for an authenticated actor in an HTTP flow.
- **404:** resource does not exist, or the application intentionally conceals existence of unauthorized resources.
- **500 or expression evaluation error:** post-check expression accesses a property missing from the DTO or a getter throws a runtime exception, depending on exception handling.

Do not equate a 500 from a broken expression with a 403 from a policy DENY, nor catch all SpEL errors and return ALLOW/`permitAll` to keep responses “clean”. When a mapper changes types, tests/builds must catch the error before production; when policy/DB errors are ambiguous, design fail-closed error handling that leaks no secrets.

For anti-enumeration, consider matching responses for “non-existent” and “unauthorized” per threat model; scoped queries can help. Never disclose owner email, tenant ID, or shared user names in error bodies.

## 29. When to choose which solution?

| Scenario | Suitable solution | What to verify |
| --- | --- | --- |
| Read-only entity, owner known only after query | `@PostAuthorize` on entity/secured view with metadata | Proxy, exact return type, trusted source, no side effects |
| REST returning public DTO without owner metadata | Guard entity in service before mapper | Policy executes before mapping/serialization |
| DTO needing to retain post-check | Internal secured DTO metadata + policy bean | Jackson output hides metadata, mapper populates from DB |
| Wanting method annotation on entity reader | Proxied secured loader bean, facade maps after ALLOW | No self-invocation/direct repo bypass |
| Large lists / pagination | Scoped repository query before paging | Accurate counts, owner/tenant/ACL |
| Field-level PII | Per-field permissions + DTO allowlist | JSON/export/GraphQL leak no fields |
| Mapped JPA relations/lazy | Materialize fields inside transaction per policy | No lazy errors, no out-of-scope SQL |
| Write commands | Functional pre-check + domain policy before mutation | Transactions, locking, zero side effects after DENY |
| Using `@AuthorizeReturnObject` | Test proxy and getter annotations on real objects | Never assume plain DTOs carry security advice |
| Caching DTO by document ID | Authorize on every read, proper keys/invalidation | Zero cross-user/tenant leaks |
| Migrating service from entity to projection | Regression-test expressions and shapes | Never drop security to silence property errors |

The goal is not “keep `@PostAuthorize` everywhere”, but **never lose authorization decisions** when changing data shapes.

## 30. Security review checklist for DTOs / mappers

1. Does the method return an entity, DTO, projection, collection, Page, Optional, or wrapper?
2. What exact type is `returnObject` at `@PostAuthorize`?
3. Where does the post-check expression get `ownerId`, `tenantId`, ACL, and state?
4. Does the mapper drop or alter that metadata?
5. If a property is missing, does code fail or did someone relax the policy to “fix” it?
6. Do DTO fields come from the real entity or copied from client requests?
7. Are the sources of truth for owner and tenant trustworthy?
8. Are canonical actor ID/active tenant verified from Authentication/membership?
9. Are `@EnableMethodSecurity` and Spring bean proxies genuinely active?
10. Is there any self-invocation or direct repository access bypassing secured loaders?
11. Does `@PostAuthorize` sit **before or after the mapper** in runtime flow?
12. Does the mapper trigger side effects, logs, or DTO caching before policy runs?
13. Do JPA lazy relations or transaction advisor ordering interfere?
14. Does the DTO contain PII/secret fields beyond the actor's permissions?
15. Are `@JsonIgnore` or Jackson filters bypassed by another export path?
16. Are getters annotated with method security actually invoked through a proxy?
17. After migrating to record DTOs, do old getter annotations still have any effect?
18. If using `@AuthorizeReturnObject`, is the return type proxyable with right AOT hints?
19. For List/Page, does policy check objects before pagination/counts?
20. Do queries constrain tenant/owner/ACL properly?
21. Do GraphQL/download/export paths share the same policy?
22. Do cache keys include actor/tenant/rights or recheck on every read?
23. For writes, are permissions verified before mutations and side effects?
24. Are actors with valid roles yet wrong owner/tenant tested for DENY?
25. Is the DTO tested to emit zero metadata/PII in JSON?
26. Are mapper/return-type changes tested not to break expressions?
27. Do SpEL errors fail closed without exposing data?
28. Do logs strip sensitive raw entities/DTOs?
29. Do owner/ACL/membership changes properly invalidate caches/policies?
30. Is security review required when altering mappings or API projections?

### Self-check questions

**1.** A service returned `Document` with `ownerId`; after refactoring it returns `DocumentDto` without `ownerId`. Is `@PostAuthorize("returnObject.ownerId ...")` still valid?  
→ **No.** `returnObject` is now the DTO; the property may fail to resolve, requiring updating the gate/return type and testing—not deleting the policy.

**2.** Does a missing field on the DTO mean Spring automatically skips `@PostAuthorize` and ALLOWs?  
→ **No.** It can cause a SpEL error. Vulnerabilities usually arise when guards are deleted/loosened too broadly or mapping drops another gate.

**3.** What is a simple way for a public DTO to omit `ownerId` while still checking ownership?  
→ Load the real entity, verify tenant/owner/ACL in the service, and **only then map the DTO**.

**4.** Can `@JsonIgnore` hide `ownerId` on a secured DTO for post-checks?  
→ It can under properly configured Jackson, yet `@JsonIgnore` is not a security boundary. Test serialization/other serializers and populate owner metadata from the DB.

**5.** An entity getter has `@PreAuthorize`; a mapper copies values into a record DTO. Does the getter annotation automatically protect the DTO?  
→ **Not by default.** Method security guards calls through proxies/advice, rather than migrating annotations onto record accessors.

**6.** Is `@AuthorizeReturnObject` equivalent to `@PostAuthorize`?  
→ **No.** One proxies methods on the returned object; the other evaluates the entire result after the method runs.

**7.** Is `@PostFilter` good on a list of 1 million records before pagination?  
→ Usually not; use permission-scoped queries before paging, since post-filtering is expensive and breaks counts/pages.

**8.** Does a post-check DENY mean the mapper did not run?  
→ **No.** If the mapper is in the method body, it runs before `@PostAuthorize`. Avoid mappers with sensitive side effects/caching.

**9.** An actor owns a document yet lacks permission to read a PII field; does an object-level post-check ALLOW automatically hide the PII?  
→ **No.** You need field-level policies and DTO allowlist/serialization tests.

**10.** Does an HTTP 403 test when an actor lacks functional permission prove the owner check works?  
→ **No.** You must use an actor holding the general permission yet wrong owner/tenant and verify the real DENY point.

## Conclusion

**DTOs and mappers are data-shape transformations, not default authorization components.** `@PostAuthorize` evaluates the method's actual `returnObject`; when a mapper converts an entity to a DTO and strips `ownerId`, `tenantId`, or ACL metadata, the post-check expression may no longer hold. Safest in many use cases is **authorizing on the entity/secured view from a trusted source before mapping to a public DTO**, or using a genuinely proxied secured loader before mapping. For sensitive data, large lists, field-level PII, and commands with side effects, use scoped queries, actor–resource policies, mapper/serializer controls, and regression tests. **Never delete/relax a security rule just because a new DTO broke SpEL.**

## Official references

1. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — `@PostAuthorize`, `returnObject`, `@PostFilter`, `@AuthorizeReturnObject`, AOP, and transactions.
2. [Spring Security 6.5 — Method Security Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html) — `@WithMockUser` and testing method-level permissions.
3. [Spring Security 6.5 — Domain Object Security (ACL)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html) — per-object ACLs/permissions.
4. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — HTTP security vs. method checks.
5. [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html) — verifying per-user object access, preventing IDOR/BOLA.
6. [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — boundaries, proxies, and rollback semantics.
