# Authorization at HTTP, Method, and Individual Data Object Levels

## Learning Objectives

After this lesson, you will be able to distinguish the three places to put authorization policies in a Spring Security application on the Servlet stack; know what each layer decides, how they combine, and why checking access to a URL is still not enough to protect a specific record. The running example is a document management API: users have permission to read/edit documents in general, yet may only operate on documents they own or that are shared with them.

## 1. What Does Authorization Check?

**Authentication** determines who the caller is; **authorization** determines whether the caller is allowed to perform an action on a specific resource. In Spring Security, `Authentication` typically holds the identity (`principal`), authentication status, and `GrantedAuthority` values such as `ROLE_ADMIN` or `doc:read`. A logged-in user is not automatically permitted to access every document.

An authorization decision may depend simultaneously on:

- **Subject**: current user, roles, authorities, tenant, groups.
- **Action**: read, create, edit, delete, approve.
- **Resource**: API, business operation, document with `id=42` and owner `alice`.
- **Context**: time, document state, sharing relationship, organizational rules.

For example, `bob` has authority `doc:edit`, yet document 42 belongs to `alice` and does not allow others to edit it: the request to rename document 42 **must be denied**. An authority only expresses a functional-level permission; permission on an individual object requires additional conditions.

### Three layers that should work together

| Layer | Control Point | Example Question | Strengths | Limitations |
| --- | --- | --- | --- | --- |
| HTTP/request | `SecurityFilterChain` and `authorizeHttpRequests` | Does `PATCH /api/documents/42` require `doc:edit`? | Fails fast by URL, HTTP method, and coarse-grained authority | Does not inherently know who owns record 42 |
| Method/business | `@PreAuthorize`, `@PostAuthorize` on Spring beans | Who can call `DocumentService.rename(42, ...)`? | Protects business logic even when called from a controller, message consumer, or another component | Requires enabling method security and going through a Spring AOP proxy |
| Individual data object | Owner/tenant/ACL policy, constrained queries | Does record 42 belong to this user's tenant and permissions? | Prevents cross-data access, even through the same API | Must check against trusted server-side data, including list queries |

Typical flow: **request → authentication → HTTP rules → controller → method rules → query/record-level permission check → business logic/response**. A valid request must pass through *all* applicable gates. Separating layers improves maintainability; they complement rather than replace each other.

## 2. Authorization at the HTTP Level

In a Spring MVC/Spring Boot application using Spring Security 6.x, declare access rules with `SecurityFilterChain` and `authorizeHttpRequests`. Complete example of a configuration class; requires the `spring-boot-starter-security` dependency along with an application-provided user/authentication source:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/actuator/health").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("doc:read")
            .requestMatchers(HttpMethod.POST, "/api/documents")
                .hasAuthority("doc:create")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/**")
                .hasAuthority("doc:edit")
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults()); // Illustrative authentication
        return http.build();
    }
}
```

**Reading the configuration:**

1. `/actuator/health` is public. For `GET /api/documents/42`, the caller needs the exact `doc:read` authority; for `PATCH` on the same URL, `doc:edit` is needed.
2. `hasRole("ADMIN")` under standard convention checks the `ROLE_ADMIN` authority. Meanwhile, `hasAuthority("doc:read")` checks the **exact string** `doc:read`; no prefix is added automatically.
3. `requestMatchers` rules are evaluated **in order**, and the first matching rule decides at the HTTP layer; place specific cases before broad ones. `anyRequest().denyAll()` denies undeclared endpoints: closed by default.
4. `@EnableMethodSecurity` in the example turns on processing for `@PreAuthorize`/`@PostAuthorize`; merely adding the Security starter does not automatically enable this feature.

`httpBasic` is only used to illustrate the authorization layer and does not dictate the system's authentication model. Production APIs may use sessions or OAuth2 Resource Server/JWT and must configure the `Authentication` source and appropriate authority mappings. When using HTTP Basic/cookies for state-changing requests, **CSRF remains a separate control**: a `PATCH` may receive 403 due to a missing CSRF token even with the right authority. Do not disable CSRF just to make an example run; choose configuration based on application type and real threat model.

**What HTTP does not solve:** both `alice` and `bob` with `doc:read` pass the `GET /api/documents/42` rule, yet only the record and sharing rules determine whether `bob` can actually read document 42. Never treat matching a URL as proof of document ownership.

## 3. Authorization at the Method Level

Method security protects business entry points via Spring AOP. `@PreAuthorize` evaluates an expression **before** running the method; `@PostAuthorize` evaluates the result **after** the method returns. Common expressions:

| Expression | Meaning |
| --- | --- |
| `hasAuthority('doc:read')` | Has exact authority `doc:read` |
| `hasRole('ADMIN')` | Has corresponding role `ROLE_ADMIN` per default prefix |
| `authentication.name` | Name/identifier of the authenticated user provided by authentication |
| `#id` | Method argument named `id` (requires parameter name metadata or `@P` annotation) |
| `@documentAccess.canEdit(authentication, #id)` | Invokes a bean checking object-access policy |
| `returnObject` | Return value used in `@PostAuthorize` |

Suppose `Document` has getters `getOwnerUsername()`, `isShared()`, and `setTitle(String)`; and `DocumentRepository` has `findById(long)` returning `Optional<Document>`. These are two application domain types, **not** classes provided by Spring Security. The sample below shows two Spring beans with realistic business logic; to compile it, declare the two domain/repository types mentioned.

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentAccess")
public class DocumentAccess {
    private final DocumentRepository documents;

    public DocumentAccess(DocumentRepository documents) {
        this.documents = documents;
    }

    public boolean canRead(Authentication actor, long id) {
        if (actor == null || !actor.isAuthenticated()) return false;
        return documents.findById(id)
            .map(doc -> doc.getOwnerUsername().equals(actor.getName())
                     || doc.isShared())
            .orElse(false);
    }

    public boolean canEdit(Authentication actor, long id) {
        if (actor == null || !actor.isAuthenticated()) return false;
        return documents.findById(id)
            .map(doc -> doc.getOwnerUsername().equals(actor.getName()))
            .orElse(false);
    }
}
```

```java
import java.util.NoSuchElementException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "hasAuthority('doc:read') and " +
        "@documentAccess.canRead(authentication, #id)"
    )
    public Document read(@P("id") long id) {
        return documents.findById(id)
            .orElseThrow(() -> new NoSuchElementException("Document not found"));
    }

    @Transactional
    @PreAuthorize(
        "hasAuthority('doc:edit') and " +
        "@documentAccess.canEdit(authentication, #id)"
    )
    public Document rename(@P("id") long id, String title) {
        Document document = documents.findById(id)
            .orElseThrow(() -> new NoSuchElementException("Document not found"));
        document.setTitle(title);
        return document;
    }
}
```

**Mechanism:** calling `DocumentService.read(42)` through the Spring proxy causes `@PreAuthorize` to check **both** the `doc:read` authority and `documentAccess.canRead(...)`. Only when both are true does the method read the document. The `@P("id")` annotation declares the parameter name for SpEL, avoiding dependence on compiler flags; if using `#id` without `@P`, you must compile Java with `-parameters` so Spring Framework 6.1+ can see parameter names. The ownership check executes on the server against the actual record, without trusting any client-sent `ownerId`.

**AOP limitations:** annotations take effect on methods of Spring-managed beans when calls go through the proxy. A `this.rename(...)` call from another method **in the same bean** typically bypasses the interceptor; instantiating via `new DocumentService(...)` also has no proxy. Place policies at the service boundary and write tests calling the real bean from the Spring context—do not only call methods directly on a manually constructed object.

`@PostAuthorize("returnObject.ownerUsername == authentication.name")` can be suitable for **read** operations, since it inspects the returned object; do not use it as the sole gate for write/delete operations: side effects can occur before denial. For update operations, prefer pre-checks and enforce writes at the data layer.

## 4. Authorization for Individual Data Objects

### 4.1. Why must the actual ID be checked?

When an API receives `GET /api/documents/42`, the client only chooses **the ID to request**, and has no authority to dictate `owner`. **IDOR/BOLA** risk arises when the server checks only `doc:read`, runs `findById(42)`, and returns data to anyone who knows the ID. Changing `42` to `43` must never leak another user's data.

Example policy for a single-tenant system:

| Caller | Authority | Document | Decision |
| --- | --- | --- | --- |
| Alice | `doc:read` | Document 42 owned by Alice | Allow read |
| Bob | `doc:read` | Alice's document 42, not shared | Deny read |
| Bob | `doc:read` | Alice's document 42, shared for reading | Allow read |
| Bob | `doc:edit` | Alice's document 42, even if shared for reading | Deny edit |
| Alice | `doc:edit` | Document 42 owned by Alice | Allow edit |
| Unauthenticated user | None | Any private document | Deny |

This is an **example policy**, not a Spring Security default. Real systems may use ACLs (lists of shared users), project roles, document statuses, or tenant conditions. Every condition must be enforced server-side across all business entry paths.

### 4.2. Embedding conditions directly in queries when appropriate

For private data, queries with ownership constraints are often clearer and reduce the risk of forgetting checks:

```java
// Example Spring Data JPA repository method.
// Document has property ownerUsername; field name must match the actual entity.
Optional<Document> findByIdAndOwnerUsername(long id, String ownerUsername);
```

In the service, take `ownerUsername` from the authenticated identity and call `findByIdAndOwnerUsername(id, actorName)`. In multi-tenant systems, include `tenantId` in both query criteria and uniqueness/permission checks; identical usernames in two tenants must never be treated as the same owner. For complex permissions, replace the owner filter with queries/policies checking ACLs or membership against real data.

For **critical data writes**, checking the owner first and updating afterward can introduce a race window (TOCTOU) if permissions/ownership change between the two steps. Choose appropriate transactions/locking, or conditional update statements such as `UPDATE ... WHERE id = ? AND tenant_id = ? AND owner_id = ?` and check the affected row count. A service-level annotation does not by itself make DB operations atomic.

For **lists, search, pagination, and exports**, permission filters must be applied **before paginating or returning data**, typically right inside the query. Fetching everything and then filtering with `@PostFilter` can waste resources, distort total counts/pages, and leak unintended metadata. Both read-by-ID and list endpoints must enforce the same policy.

### 4.3. When should `hasPermission` be used?

Spring Security provides `hasPermission(target, 'read')` or `hasPermission(id, 'Document', 'read')`, delegating evaluation to a custom application `PermissionEvaluator`. It fits when multiple services share a unified ACL/policy. However, **never assume ownership is automatically checked just by calling `hasPermission`**: you must provide the corresponding implementation, data, and permission mapping. For small examples, a bean like `documentAccess` is easier to read and test.

## 5. Distinguishing 401, 403, 404, and Other Errors

- **401 Unauthorized**: typically indicates missing valid authentication when an endpoint requires login and the authentication mechanism responds with a 401 challenge.
- **403 Forbidden**: authenticated but lacking sufficient permissions, or blocked by a protection layer such as CSRF. Do not immediately conclude a wrong role upon seeing 403.
- **404 Not Found**: when no record exists; an API may intentionally return 404 for out-of-scope data to avoid disclosing existence, following a consistent product policy. Do not rely on status codes as a substitute for permission checks.
- **500**: unexpected configuration/mapping errors should not silently become 403; log safely for investigation.

In Servlet web requests, Spring Security typically converts `AccessDeniedException` into a denial response through the filter chain's exception-handling mechanism. For service calls from background jobs or consumers without an HTTP request, the application must handle exceptions and establish an appropriate execution identity itself.

## 6. Designing Tests Across All Three Layers

Verify each boundary and interaction:

| Scenario | Expectation | Layer to Observe |
| --- | --- | --- |
| Unauthenticated guest calls private endpoint | Denied, usually 401 per entry point | HTTP |
| User with `doc:read` calls `PATCH` requiring `doc:edit` | 403 | HTTP |
| User with `doc:edit` calls service directly to edit someone else's document | `AccessDeniedException`; data unchanged | Method + object |
| User allowed to read document 42 swaps ID to secret document 43 | Cannot retrieve document 43 data | Object |
| User in tenant A knows a tenant B document ID | Cannot read/edit/count/find via API | Object/query |
| Owner edits their own document | Succeeds, state is persisted | End-to-end |
| List query has 1000 documents but caller may only view 7 | Results, pagination, and count reflect only the 7 permitted documents | Query |
| Method called via non-HTTP entry points | Business rules still apply | Method |
| `PATCH` request has authority but lacks CSRF token when CSRF is required | Blocked due to CSRF; do not blame authority | Web security |

For HTTP, use `MockMvc` and `spring-security-test` (e.g., `@WithMockUser`, `csrf()`) to verify 401/403 and matchers. For object-level checks, use the real service bean with sample data across different owners/tenants; mocking the entire service forfeits the chance to verify annotations on that service. In update tests, verify **the database does not change** on denial, not merely the status code. For paginated queries, check both the item list and total/count.

## 7. Common Mistakes

1. **Protecting only the URL:** an authenticated `/api/documents/{id}` endpoint can still return someone else's data. Always check owner/ACL/tenant by the actual ID.
2. **Confusing role with authority:** `hasRole("ADMIN")` differs from `hasAuthority("ADMIN")` if the actual authority is `ROLE_ADMIN`. OAuth2 scopes may map to `SCOPE_xxx` depending on config; do not assume a token scope automatically becomes `doc:read`.
3. **Wrong matcher order or overly broad rules:** an `/api/**` rule declared before a specific rule can swallow later routes. Define an explicit fallback with `anyRequest()`.
4. **Forgetting `@EnableMethodSecurity`, self-invoking inside a bean, or calling objects outside the container:** annotations appear in code yet are not executed by any interceptor.
5. **Using `@PostAuthorize` for writes:** the check runs after side effects. Replace with pre-checks and atomic write conditions.
6. **Trusting client-supplied owner/tenant IDs:** identity and tenant must come from authenticated/verified sources, and permissions must be checked against server data.
7. **Filtering permissions after returning lists or after pagination:** risks data leaks, wrong counts, and wasted memory. Push conditions down into queries consistently with single-item endpoints.
8. **Ignoring races or stale permission caches:** when a document changes owner/tenant or ACLs change, permissions must be updated/checked at the right time; critical writes must ensure atomicity.
9. **Assuming every 403 means missing authority:** CSRF, method policy, object policy, and HTTP rules can all be causes. Diagnose layer by layer instead of disabling protections blindly.

## 8. Workflow for New Endpoints

1. Write down the desired decision in **subject – action – object – context** form; choose deny by default.
2. Protect URLs and HTTP methods with coarse-grained rules. Place specific matchers before broad matchers.
3. Place business permission checks at the service boundary; enable method security and verify calls go through the proxy.
4. Check owner/ACL/tenant using real records or conditional queries; protect write operations and list queries specifically.
5. Design return status codes, non-sensitive logging, and negative test cases—especially **knowing someone else's ID**, permission changes mid-flight, and calling the service from non-HTTP paths.

**Self-check:** If Alice and Bob both have `doc:read`, and URL `GET /api/documents/42` passes the HTTP layer, yet document 42 belongs to Alice and is not shared, can Bob view it? **No.** The HTTP rule proves permission to read *the resource type*; the policy bean or query must deny Bob for lacking permission on *that specific record*.

## References

- Spring Security, *Authorize HttpServletRequests*: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security, *Method Security*: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security, *PermissionEvaluator API*: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/access/PermissionEvaluator.html
