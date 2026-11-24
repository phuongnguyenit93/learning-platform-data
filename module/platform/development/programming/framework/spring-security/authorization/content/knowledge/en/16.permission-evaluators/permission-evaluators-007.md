# Nonexistent Objects, Missing Permissions, and Error-Response Policies with PermissionEvaluator

## 1. The problem: “nonexistent” differs from “unauthorized”

When a user calls `GET /api/documents/42`, the system can encounter three very different situations:

1. Document 42 **does not exist** in the system or has been deleted.
2. Document 42 **exists**, but the caller does not belong to the tenant, does not own it, or has not been shared the document.
3. Document 42 exists and the caller **is permitted** to read it.

At the business layer, we want to recognize each situation accurately. At the API layer, however, not every application should tell the caller whether a forbidden object actually exists. A differing response between `403 Forbidden` and `404 Not Found` can help outsiders enumerate IDs, projects, accounts, or confidential records.

Spring Security provides `PermissionEvaluator` as an extension point to answer the question: **does this user have a specific permission on this object/ID?** It **returns a boolean** and does not directly decide HTTP status codes. Policies for returning `401`, `403`, `404`, or `5xx` live in other application layers and must be designed deliberately.

Lesson objectives:

- Accurately understand both overloads of `PermissionEvaluator.hasPermission(...)`.
- Distinguish “nonexistent object,” “unauthorized,” “unauthenticated,” and “infrastructure error.”
- Know when returning `false` is safe and when an exception must be thrown.
- Choose a `403` or `404` policy that avoids leaking resource existence.
- Implement a Spring Security example and the alternative of principal/tenant-scoped queries.
- Test behavior using MockMvc, method security, database checks, and ID-probing scenarios.

## 2. Two overloads of PermissionEvaluator

The `org.springframework.security.access.PermissionEvaluator` interface defines two ways to check permissions:

```java
boolean hasPermission(
    Authentication authentication,
    Object targetDomainObject,
    Object permission
);

boolean hasPermission(
    Authentication authentication,
    Serializable targetId,
    String targetType,
    Object permission
);
```

### Domain-object form

`hasPermission(authentication, targetDomainObject, permission)` is used when the call already has **the object**. Example:

```java
@PreAuthorize("hasPermission(#document, 'read')")
public void process(Document document) {
    // ...
}
```

`#document` is the method parameter. If it comes from a client-sent body, fields like `ownerId` and `tenantId` in the object could be forged; never allow access merely because the client put its own username in owner. For entities loaded from a database, consider within what protection boundary they were loaded and whether they might change during evaluation.

According to the Javadoc, `targetDomainObject` **may be null**; implementations are recommended to return `false` when the target is null. If a business method needs to distinguish “null” from “unauthorized,” handle that separately in the data/error layer rather than letting the evaluator throw `NullPointerException`.

### ID and resource-type form

`hasPermission(authentication, targetId, targetType, permission)` is used when the method only has the ID:

```java
@PreAuthorize("hasPermission(#documentId, 'Document', 'read')")
public Document readDocument(Long documentId) {
    // ...
}
```

Here Spring Security passes `documentId` as a `Serializable`, the literal string `"Document"` as `targetType`, and `"read"` as `permission`. **`targetType` does not automatically instantiate or fetch an entity**; evaluator code must decide how to map this value to the right repository. Never use `Class.forName(targetType)` or dynamic SQL table names from an untrusted string.

Both overloads return:

- `true`: permission is granted to the caller on the target under evaluation.
- `false`: permission is not granted — possibly due to nonexistence, missing rights, wrong target, invalid ID, or fail-closed policy.
- There is no third “not found” value in the boolean contract.

**Important:** `false` carries no HTTP status code. When used in `@PreAuthorize`, returning `false` causes method security to **reject the call before the method body runs**. On the HTTP path, the result is normally translated into `403` for authenticated users, not automatically `404`.

## 3. Status table: internal state vs. external response

| System condition | Internal meaning | Typical HTTP consideration | Notes |
| --- | --- | --- | --- |
| No valid Authentication | Unauthenticated | `401 Unauthorized` or login redirect | Depends on authentication entry point |
| Authenticated, missing general action authority | Insufficient authority | `403 Forbidden` | May be denied at filter/method before looking up ID |
| Valid ID, resource does not exist | Not found | `404 Not Found` | Do not imply authorization on something that does not exist |
| Valid ID, resource exists but unreadable | Forbidden | `403` **or concealing `404`** | Choose based on anti-existence-leak requirements |
| Resource exists, authorized | Granted | `200 OK`, `204 No Content`, etc. | Endpoint-dependent |
| Malformed ID | Invalid request | `400 Bad Request` or `404` per routing/API | This is an input error, not a PermissionEvaluator outcome |
| Database error, timeout, connection drop | Infrastructure failure | `500`/`503` depending on case | Do not treat as 404 and never allow access |

`401`, `403`, and `404` are HTTP protocol codes, **not return values of PermissionEvaluator**. Spring Security uses `AuthenticationEntryPoint` for many unauthenticated scenarios and `AccessDeniedHandler` for authenticated-but-unauthorized scenarios; `ExceptionTranslationFilter` bridges security exceptions to HTTP responses in the filter chain.

Do not apply a single rigid table to every protocol: a service invoked from a batch job, message listener, or scheduled task can receive `AccessDeniedException` with no HTTP status at all. For REST APIs, design HTTP mapping at the application boundary and write integration tests with the real security configuration.

## 4. The 403 policy vs. the existence-hiding 404 policy

### Policy A: distinguish “nonexistent” from “unauthorized”

Appropriate when an object's existence is **allowed to be public**. Examples include public products, public events, or resources whose metadata everyone already has permission to view.

```text
GET /public-documents/42
         |
         v
   Look up document 42
      |       |
   absent   present
      |       |
     404     check permission
                 |       |
                DENY    GRANT
                 |       |
                403     200
```

**Risk:** two different status codes can become an “existence oracle.” If ID 42 returns `403` while 43 returns `404`, an outsider deduces 42 exists, even without reading its contents. In multi-tenant or private-data environments, that existence itself may be sensitive information worth protecting.

### Policy B: “not visible” is treated as “does not exist”

Appropriate for private records, internal projects, cross-tenant data, or objects whose existence the caller **has no right to know**.

```text
GET /documents/42
        |
        v
  Query within data scope the caller may read
        |
        +-- Visible record found -> 200
        |
        +-- No visible record found -> 404
             (covers both genuinely absent and forbidden)
```

This is **resource hiding**: the exact same neutral message for “ID does not exist” and “ID exists outside permitted scope.” Not every `403` must turn into `404`. For example, a user lacking the basic `document:read` authority may receive `403` prior to querying, since that reveals nothing about whether a specific ID exists.

**Selection principle:** publish a consistent policy per endpoint category. Never let services over the same data layer return `403` in one place and `404` in another based on an accidental branch; never vary response codes by exception message.

## 5. How should PermissionEvaluator return false?

The following example only illustrates **component classes in a Spring Boot application** and does not run standalone. It assumes the project has a `DocumentRepository`, `Document` entity, and `TenantScopeService` with application-implemented data contracts.

An evaluator for read permission on Document by ID:

```java
import java.io.Serializable;
import java.util.Optional;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final DocumentRepository documents;
    private final TenantScopeService scopes;

    public DocumentPermissionEvaluator(
            DocumentRepository documents, TenantScopeService scopes) {
        this.documents = documents;
        this.scopes = scopes;
    }

    @Override
    public boolean hasPermission(
            Authentication auth, Object target, Object permission) {
        if (!(target instanceof Document document)) {
            return false; // includes null target, wrong type
        }

        // Use only the ID from the object to check policy at a trusted source.
        // Do not trust client-sent owner/tenant fields.
        return hasPermission(
            auth, document.getId(), "Document", permission);
    }

    @Override
    public boolean hasPermission(
            Authentication auth,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || !(targetId instanceof Long id)
                || id <= 0
                || !"Document".equals(targetType)
                || !"read".equals(permission)) {
            return false;
        }

        boolean hasOperationPermission = auth.getAuthorities().stream()
            .anyMatch(a -> "document:read".equals(a.getAuthority()));
        if (!hasOperationPermission) {
            return false;
        }

        Optional<String> tenantId = scopes.authorizedTenantId(auth);
        if (tenantId.isEmpty()) {
            return false;
        }

        return documents.existsByIdAndTenantIdAndOwnerUsernameAndDeletedFalse(
            id, tenantId.get(), auth.getName());
    }
}
```

With Spring Data JPA, the example requires a repository with the corresponding derived query method and an entity having properties `id`, `tenantId`, `ownerUsername`, and `deleted`. `scopes.authorizedTenantId(auth)` is **not a built-in Spring Security API**; it is a custom application service verifying the tenant from server-side data rather than blindly reading a request header.

The implementation checks:

1. Caller is a validly authenticated user, not anonymous.
2. ID is a positive `Long`, and `targetType`/`permission` belong to the allowed set.
3. Holds the `document:read` authority.
4. Has an authorized tenant from a trusted source.
5. Repository confirms a record matching ID, tenant, owner, and non-deleted status **simultaneously**.

Whether the record genuinely does not exist, belongs to another tenant, or has a different owner, `existsBy...` returns `false`. This yields a boolean policy that **discloses no reason** through the evaluator.

### Never arbitrarily hide database errors as false

If the database disconnects, the repository may throw `DataAccessException`. **Do not** do:

```java
try {
    return documents.existsByIdAndTenantIdAndOwnerUsernameAndDeletedFalse(
        id, tenantId, username);
} catch (Exception ignored) {
    return false; // DO NOT DO: conflates an outage with "does not exist"
}
```

Defaulting to allow on error is a grave bug; yet coercing every error into `false` also masks outages, misleading operators and clients into thinking resources do not exist. Let infrastructure failures be handled by the proper error-management layer and return a safe 5xx status. **Fail closed** means never exposing data when permissions cannot be verified—not that every exception must become HTTP 404.

### What is wrong with receiving objects from the client?

If a controller accepts `Document document` from JSON and calls `hasPermission(auth, document, "read")`, the user can supply `ownerUsername = "alice"` or `tenantId` themselves. The implementation above intentionally **distrusts** those fields, using only the ID to look up permissions in the repository. For an entity already loaded on the server, trusted metadata may be reused to optimize, provided transaction boundaries and entity state are managed properly.

Do not overlook IDOR risks: a caller sending a valid `documentId` **does not prove** permission on that document.

## 6. Wiring PermissionEvaluator into Method Security

Enable method authorization and set `PermissionEvaluator` on `DefaultMethodSecurityExpressionHandler`. In modern Java configuration, you can publish the handler bean via a `static` method so it is created early when Spring Security sets up infrastructure:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {

        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

In an application, ensure **only the right handler is configured** and verify it is actually active in the context. With multiple evaluator/handler beans, resolution rules must be explicit. `@EnableMethodSecurity` is not always active merely by adding the security dependency.

Service:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("hasPermission(#documentId, 'Document', 'read')")
    public Document read(@P("documentId") Long documentId) {
        return documents.findById(documentId).orElseThrow();
    }
}
```

`@P("documentId")` supplies an explicit parameter name for SpEL. This snippet illustrates invoking the evaluator and is intentionally **not the final optimal solution**:

- When the evaluator returns `false` because of **nonexistence** or **missing permission**, the method does not run; for authenticated users, the HTTP layer usually returns **403** without distinguishing the cause.
- If the evaluator returns `true` and data/permissions change before `findById` executes, a race condition (time-of-check/time-of-use) can occur.
- `existsBy...` followed by `findById` issues two queries, and the second query lacks tenant/owner constraints. In sensitive systems, fetch data via a permission-scoped query within an appropriate transaction rather than relying on an earlier check.
- If `DocumentRepository.findById` finds no record, no-arg `orElseThrow()` throws `NoSuchElementException`. Which HTTP status results from this exception **must not be guessed**; there must be an explicit mapping mechanism.

**Remember:** You cannot ask `PermissionEvaluator` to return a boolean so `@PreAuthorize` blocks before the method while also automatically returning `404` for “not found” and `403` for “forbidden.” To distinguish both causes, you need **a coordinated design of policy + lookup + error mapping**.

## 7. Two ways to build a service around error policies

### Approach 1 — Hide out-of-scope resources: conditional queries and 404

This is usually the best choice for sensitive tenant/owner-scoped resources. Instead of a broad `findById(id)` that partially leaks existence, query only **records the user is allowed to see**.

Example service class **in a Spring application**:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PrivateDocumentService {
    private final DocumentRepository documents;
    private final TenantScopeService scopes;

    public PrivateDocumentService(
            DocumentRepository documents, TenantScopeService scopes) {
        this.documents = documents;
        this.scopes = scopes;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Document readVisible(Long id, Authentication auth) {
        if (id == null || id <= 0) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found");
        }

        // Scope derived from server-verified information.
        String tenantId = scopes.authorizedTenantId(auth)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found"));

        return documents.findByIdAndTenantIdAndOwnerUsernameAndDeletedFalse(
            id, tenantId, auth.getName()
        ).orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Document not found"));
    }
}
```

This class assumes `auth` is an `Authentication` **already provided by the framework/controller**, not an object deserializable from client JSON. In real applications, obtain identity from the security context or controlled injection rather than letting untrusted callers construct `Authentication`. Calls must go through the Spring proxy so `@PreAuthorize` executes.

Whether the document truly does not exist or exists with a different owner/tenant, the query returns empty and the API responds `404 Not Found` with the same message. A user holding `document:read` who does not own the document **cannot tell whether the document exists** from the HTTP status code.

Notes:

- Users **lacking the `document:read` authority** may still be blocked by `@PreAuthorize` with `403`. That can still be appropriate if the policy only hides per-ID existence after passing coarse-grained feature permissions.
- If **every unauthorized user** must see the exact same `404`, design an explicit entry policy/handler for that route; never blindly turn every `403` in the application into `404`.
- Querying by owner only illustrates an **owner** policy; ACLs, groups, shares, and admin roles must be incorporated into the query/policy if the business actually allows them.
- For writes, update with `UPDATE ... WHERE id = ? AND tenant_id = ? AND owner_id = ?` or appropriate locking/transactions; permissions can change between check and write.

### Approach 2 — Intentionally distinguish 404 and 403 when existence is public

If the product allows disclosing resource existence, code can check existence first and then check permission:

```java
public Document readPublicMetadataVisible(Long id, Authentication actor) {
    Document doc = documents.findById(id)
        .orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Document not found"));

    if (!documentPolicy.canRead(actor, doc.getId())) {
        throw new org.springframework.security.access.AccessDeniedException(
            "Forbidden");
    }
    return doc;
}
```

This is an **illustrative method** using application beans/variables. This policy **discloses existence**: an existing resource without sufficient permission triggers `AccessDeniedException` instead of 404. Apply this only when product and security reviews confirm disclosing existence is acceptable. `AccessDeniedException` can become HTTP 403 via Spring Security or other configured exception handling.

If a repository serves private multi-tenant data, **do not** use a broad `findById` pattern like this just to choose between 403 and 404. It lets outsiders enumerate IDs. Return to **Approach 1** instead.

### Which approach should you choose?

| Criterion | Approach 1: query only permitted records | Approach 2: check existence then check permission |
| --- | --- | --- |
| Leaks out-of-scope resources? | Normally no, if responses are uniform | Potentially, via 403 vs. 404 |
| Queries | Single query by ID + tenant + owner/ACL | Usually lookup first, then check |
| Fits private multi-tenant data | **Preferred** | Unsuitable if existence must stay secret |
| Fits resources with public metadata | Usable, though limits information | Can be suitable |
| Interaction with `@PreAuthorize("hasPermission(...)")` | Often favors coarse permission + scoped query over separate evaluator | Requires explicit policy/error flow so annotations do not swallow the distinction |
| What must be tested? | Nonexistent **and** unauthorized produce identical responses | 403 vs. 404 difference is intentional and permitted |

## 8. Choosing HTTP status codes at the right layer, not inside the evaluator

### How does Spring Security handle AccessDeniedException?

In Servlet applications, `ExceptionTranslationFilter` handles `AuthenticationException` and `AccessDeniedException` thrown inside the filter chain:

- Unauthenticated/anonymous: may trigger `AuthenticationEntryPoint` for login, returning 401 or a redirect.
- Authenticated but denied: `AccessDeniedHandler` typically handles the 403 case.
- `PermissionEvaluator` is **not** the place to call `HttpServletResponse.sendError(...)` or set status codes; it may be called from services **with no HTTP request**.

Illustrative handler configuration for an authenticated REST API:

```java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.exceptionHandling(errors -> errors
        .accessDeniedHandler((request, response, denied) -> {
            response.sendError(403, "Forbidden");
        })
        .authenticationEntryPoint((request, response, authError) -> {
            response.sendError(401, "Authentication required");
        })
    );
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll()
    );
    return http.build();
}
```

The snippet above is a **config fragment** requiring imports and your application's authentication mechanism; in systems with a resource server, Basic authentication, or custom login, a proper `AuthenticationEntryPoint` may require a `WWW-Authenticate` header or standard redirect flow. Never copy the example to replace existing authentication configuration without testing.

If an API chooses a resource-hiding policy, handle `404` in domain-specific scoped lookups or targeted exception translation. Avoid a global handler converting **every** `AccessDeniedException` into 404: it can mask operational bugs, change the semantics of public endpoints, break 401/403 handling, or make responses inconsistent across routes.

### ResponseStatusException, @ControllerAdvice, and ProblemDetail

In Spring MVC, you can use `ResponseStatusException(HttpStatus.NOT_FOUND, "...")` or a domain exception mapped through `@RestControllerAdvice` / `@ExceptionHandler`. When following RFC 9457 Problem Details, the response body may include `type`, `title`, `status`, `detail`, and `instance`. External content must remain **neutral** toward hidden resources.

Example uniform response for both not-found and unauthorized-on-resource:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Document not found"
}
```

The body above is an **application-designed example payload**, not a guaranteed default output across all Spring Boot versions. Never include `ownerUsername`, `tenantId`, `actualStatus = FORBIDDEN`, or stack traces in the body when the goal is concealing existence.

### Do not let HTTP status depend on unexpected exceptions

Exceptions that need intentional mapping:

- `NoSuchElementException` / `EntityNotFoundException`: not automatically mapped to 404 without a handler.
- `DataAccessException` / timeouts: must not be swallowed to return `false` or 404.
- `IllegalArgumentException` from malformed ID parsing: validate early; return `400` or routing 404 per API contract.
- `AccessDeniedException` from method security: typically 403 for authenticated callers; without an HTTP layer, it is a Java invocation exception.

Write tests across the full stack: `MockMvc`, `SecurityFilterChain`, controller, service proxy, and repository. Never evaluate correctness solely from unit tests calling `PermissionEvaluator.hasPermission(...)`.

## 9. Leaking existence through side channels even when returning 404

Using the same HTTP status code alone is not enough. If an existing-but-forbidden resource and a nonexistent resource produce different signals, outsiders can still enumerate IDs.

Channels to examine:

- **Response body:** differing `title`/`detail`/error code or JSON payload size.
- **Headers:** differing `ETag`, `Last-Modified`, `Content-Length`, tenant metadata, cache keys, or redirects.
- **Timing:** the existing branch runs complex DB/ACL queries while the missing branch returns immediately. Identical nanosecond timing is not always necessary, yet large repeatable differences should be avoided.
- **Rate limiting:** 403 and 404 counted in separate buckets leaking internal state; evaluate against your threat model.
- **List/count/search:** listing endpoints may expose IDs or counts that detail endpoints try to hide.
- **Client-visible logs/traces:** correlation IDs should be opaque; never expose internal reasons on public debug endpoints.
- **Cache/CDN:** public caches might serve a response meant for another principal; use proper cache scoping and HTTP caching headers.

Do not claim complete protection against enumeration merely because both branches return `404`. Inspect the whole endpoint: headers, body, query timing, and repeatability under realistic conditions.

## 10. Logging and auditing: keep reasons internal, never expose externally

Even though an API may return the same 404 externally, internal systems still need to know what happened for investigations:

```text
Public: 404 "Document not found"
Internal event (do not expose externally):
  request_id: <correlation-id>
  actor: <safe identifier>
  resource_type: Document
  decision: DENY
  reason: CROSS_TENANT   (or ABSENT, NO_ACL, SOFT_DELETED...)
```

The content above is an **illustrative event sample**, not a structure automatically generated by Spring Security. Audit records must comply with storage, access control, retention, and sensitivity rules; avoid logging access tokens, session cookies, full entities, or unnecessary personal data.

When a database outage occurs, record `DEPENDENCY_ERROR` rather than pretending `ABSENT`. Internal metrics should track 5xx rates, permission denials, unusual ID-probing sequences, and audits of administrative actions. Disclosing detailed reasons to clients should be allow-listed and apply only when the caller is already authorized to know that context.

## 11. Standalone Java 17: identical external status, distinct internal reason

The program below simulates a document store and two response policies. It is **plain Java** with no Spring Security, database, or HTTP server; its purpose is to compare existence hiding (`404` for both missing and forbidden) against explicit responses (`403` when the resource exists without permission).

Save as `ResourceVisibilityDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class ResourceVisibilityDemo {

    record Actor(String name, String tenant, Set<String> authorities) {}
    record Document(long id, String tenant, String owner) {}

    enum Decision {
        ALLOW, MISSING, FORBIDDEN, UNAUTHENTICATED
    }

    static Decision decide(
            Actor actor, long id, Map<Long, Document> documents) {
        if (actor == null) {
            return Decision.UNAUTHENTICATED;
        }

        Document document = documents.get(id);
        if (document == null) {
            return Decision.MISSING;
        }

        boolean permitted = actor.authorities().contains("document:read")
            && actor.tenant().equals(document.tenant())
            && actor.name().equals(document.owner());

        return permitted ? Decision.ALLOW : Decision.FORBIDDEN;
    }

    static String concealedResponse(Decision decision) {
        return switch (decision) {
            case ALLOW -> "200 OK";
            case UNAUTHENTICATED -> "401 Unauthorized";
            case MISSING, FORBIDDEN -> "404 Not Found";
        };
    }

    static String explicitResponse(Decision decision) {
        return switch (decision) {
            case ALLOW -> "200 OK";
            case UNAUTHENTICATED -> "401 Unauthorized";
            case MISSING -> "404 Not Found";
            case FORBIDDEN -> "403 Forbidden";
        };
    }

    static void printCase(String label, Decision decision) {
        System.out.println(label + ": " + decision
            + " | conceal=" + concealedResponse(decision)
            + " | explicit=" + explicitResponse(decision));
    }

    public static void main(String[] args) {
        Map<Long, Document> documents = Map.of(
            42L, new Document(42L, "tenant-a", "alice"),
            77L, new Document(77L, "tenant-b", "carol")
        );

        Actor alice = new Actor("alice", "tenant-a",
            Set.of("document:read"));
        Actor bob = new Actor("bob", "tenant-a",
            Set.of("document:read"));

        printCase("Alice own", decide(alice, 42L, documents));
        printCase("Bob other owner", decide(bob, 42L, documents));
        printCase("Alice missing", decide(alice, 99L, documents));
        printCase("Alice other tenant", decide(alice, 77L, documents));
        printCase("Anonymous", decide(null, 42L, documents));
    }
}
```

Compile and run with JDK 17+:

```bash
javac ResourceVisibilityDemo.java
java ResourceVisibilityDemo
```

Exact stdout:

```text
Alice own: ALLOW | conceal=200 OK | explicit=200 OK
Bob other owner: FORBIDDEN | conceal=404 Not Found | explicit=403 Forbidden
Alice missing: MISSING | conceal=404 Not Found | explicit=404 Not Found
Alice other tenant: FORBIDDEN | conceal=404 Not Found | explicit=403 Forbidden
Anonymous: UNAUTHENTICATED | conceal=401 Unauthorized | explicit=401 Unauthorized
```

In this example, `Decision` is a rich **internal** state; `concealedResponse` and `explicitResponse` simulate **different** HTTP contracts. If replaced with `PermissionEvaluator`, the permission check yields a boolean; looking at `false` alone cannot distinguish missing from forbidden.

The `decide` function looks up the entire `Map` before checking owner/tenant to illustrate the distinction. **Do not copy that ordering into a private-data API** if policy requires concealing existence: prefer scoped queries and never return internal reasons to the client.

## 12. Mandatory testing matrix

### Evaluator tests

| Case | Expected `hasPermission` result | What to verify |
| --- | --- | --- |
| User's document, same tenant, has authority | `true` | Scoped repository query works properly |
| Document does not exist | `false` | Does not throw null error |
| Document exists in another tenant | `false` | Does not leak owner/tenant via response |
| Same tenant, different owner, no ACL | `false` | Does not rely on role alone |
| Lacks `document:read` | `false` | Avoids expensive queries if short-circuitable |
| Null/anonymous `Authentication` | `false` | Does not accept anonymous due to `isAuthenticated` alone |
| Null, negative, or wrong-type ID | `false` | No unexpected ClassCastException |
| Unknown `targetType` or unsupported permission | `false` | Never trusts arbitrary type/action strings |
| DB outage/timeout | **Exception** for upper layer to handle safely | Does not mistake outage for “not found” |

### Tests for intentionally concealing APIs

| Identity and ID | Internal | Expected HTTP |
| --- | --- | --- |
| Valid user, readable ID | ALLOW | 200 |
| Valid user, nonexistent ID | ABSENT | 404 |
| Valid user, forbidden ID (other owner) | DENY | 404, identical body/header contract to absent case |
| Valid user, other-tenant ID | DENY | 404, does not leak tenant |
| Unauthenticated user | UNAUTHENTICATED | 401 or designed auth flow |
| Missing route-level authority | DENY | 403 per route-protection policy |
| Database error | DEPENDENCY_ERROR | 5xx, no stack trace leaked |

With an **explicit-error** policy, “nonexistent” and “forbidden” may expect different 404/403 responses. Tests should document why that distinction is permitted.

### Integration tests

- Use `MockMvc` going through `SecurityFilterChain` and controllers, not only unit tests on the evaluator.
- Enable `@EnableMethodSecurity` and obtain services from the Spring context. Calling `this.securedMethod()` or `new Service()` can bypass the AOP proxy.
- Document behavior when `@PreAuthorize("hasPermission(...)")` denies: the method does not run; for authenticated users, HTTP is usually `403`. If the API intentionally needs `404` for unauthorized resources too, test the **scoped lookup** flow instead of expecting the evaluator to pick HTTP responses.
- Test body, content-type, headers, cache behavior, and verify no existence hints leak through response metadata.
- Test valid-format nonexistent IDs, oversized IDs, null, Unicode/encoding edge cases, soft deletes, concurrent deletes, revoked access, and ACL/tenant changes.
- If permissions can change between the evaluator query and the service read/write, use appropriate transactions, locking, and scoped queries so unauthorized data is never returned.
- Test real `DataAccessException` scenarios to ensure outages never become false/404 and no data leaks.
- Test method-security failures from both HTTP and non-HTTP callers; non-HTTP code must handle authorization exceptions according to its own contract.

## 13. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `hasPermission` returning false automatically yields 404 | Method security normally produces access denied, not not-found | Design response policy in service/controller |
| Returning `true` when document not found to avoid 403 | Fail-open, allows unauthorized reads/writes | Missing must deny; never bypass policy |
| Catching all DB errors and returning false | Outages look like 404/403, hard to detect | Fail closed and map infrastructure failures to 5xx |
| Throwing `AccessDeniedException` inside evaluator when missing | Mixes boolean decision with error mapping; breaks contract | Return false; use higher layer for distinguishing policies |
| Calling `findById` and returning different 403/404 on private resources | Leaks ID existence to outsiders | Use scoped queries, return uniform 404 |
| Using only `@PreAuthorize` followed by broad `findById` | Race/TOCTOU; second query may lack scoping | Constrain actual queries by permissions and transactions |
| Using client-sent owner/tenant in domain objects | Users spoof fields to gain access | Verify against server/database |
| Returning full entity from `@PostAuthorize` to block after writes | Side effects may already commit before denial | Check permissions before write operations |
| Converting every `AccessDeniedException` globally to 404 | Breaks permission semantics on other endpoints | Mask selectively per resource/policy |
| 404 body saying “document exists but private” | Leaks existence despite 404 status | Use neutral messages and metadata |
| Sharing cached responses across two users/tenants | Leaks data or existence signals | Partition caches by principal/tenant and enforce authorization |
| Checking only HTTP status, ignoring audit/DB | Tests miss unauthorized side effects | Assert DB, queries, events, responses, and logs |
| Logging detailed deny reasons publicly | Exposes owners/tenants/tokens | Separate internal audits from API errors |

## 14. Design checklist

1. **May the resource disclose its existence?** If not, prefer scoped lookup + neutral 404.
2. **Does PermissionEvaluator return a pure boolean?** `false` must mean not granted, without trying to carry HTTP codes.
3. **Are unauthenticated, unauthorized, and missing distinguished?** `401` differs from `403` and `404`.
4. **Is a path defined for database failures?** Never return true, and never use 404 to hide outages.
5. **Do owner/tenant/ACL come from trusted sources?** Never trust client-sent IDs, headers, forms, JSON, or entities.
6. **Are scoped queries and transaction consistency in place?** Especially critical when updating resources.
7. **Are `@EnableMethodSecurity` and the handler configured properly?** Unit-testing the evaluator does not prove annotations execute.
8. **Is 403/404 consistent across the same resource group?** Including body, headers, caching, and side channels.
9. **Is internal logging/auditing appropriate?** Keep reasons internal for investigation without exposing them to clients.
10. **Have both forbidden and nonexistent cases been tested?** Compare them directly rather than testing only the happy path.

**Conclusion:** `PermissionEvaluator` answers “**does this user have permission on this object/ID?**” with `true/false`. It does **not** directly answer “**should the API return 403 or 404?**”. To avoid leaking resource existence, design explicit error contracts, favor permission-scoped queries on real data, fail closed on permission checks, and handle infrastructure failures separately.

## Official references

- [Spring Security — PermissionEvaluator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): both overloads, boolean return type, and null-target guidance.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `hasPermission`, `@EnableMethodSecurity`, `@PreAuthorize`, expression handlers, and pre-method denial.
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): security filters and per-request authentication/access-denied handling.
- [Spring Security — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html): translating `AccessDeniedException` / `AuthenticationException` into HTTP handling.
- [Spring Framework — ResponseStatusException](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): producing explicit-status error responses in Spring MVC.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): semantics of 401, 403, and 404, and using 404 to conceal forbidden resources.
