# Calling Policy Beans from Expressions with @beanName in Spring Security

In Spring Security **method security**, `@PreAuthorize` often starts with a short condition such as `hasRole('ADMIN')` or `hasAuthority('DOCUMENT_READ')`. Yet real-world business rules are usually more complex: a user may only read documents **belonging to the current tenant**, orders must not be locked, ownership or sharing must exist, and permissions must **not have been revoked**. Writing all of that logic inside a long SpEL string is hard to test, hard to reuse, and prone to relying on untrusted client data.

Spring Security allows **invoking a Spring bean directly inside a security expression**:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentView read(long documentId) { /* ... */ }
~~~

In this SpEL string, **`@documentPolicy` references the bean named `documentPolicy` in the Spring ApplicationContext**, **`.canRead(...)` is a Java method on that bean**, and `authentication` and `#documentId` are values supplied by Spring Security into the expression evaluation environment. If the policy returns `true`, the method is permitted to run; if it returns `false`, pre-authorization denies before the method body executes.

This lesson belongs to **Pre-method checks**, using **Spring Boot 3 / Spring Security 6.x, Java 17+, and the Servlet stack** to explain the `@beanName` mechanism, how to define policy beans, obtaining the right principal/parameters, designing fail-closed policies, handling multi-tenancy, check ordering, and testing. Spring snippets require framework dependencies and real application beans; at the end of the lesson, a standalone Java 17 program demonstrates policy logic and blocking before the body runs.

## 1. What is the `@beanName` syntax in SpEL?

Spring Expression Language (**SpEL**) supports **bean references** using `@` followed by the bean name. Inside `@PreAuthorize`, common forms include:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
@PreAuthorize("hasAuthority('DOC_READ') and @documentPolicy.canRead(authentication, #id)")
@PreAuthorize("@approvalPolicy.mayApprove(authentication, #orderId)")
@PreAuthorize("@tenantPolicy.canAccess(authentication, #tenantId)")
~~~

These are **four separate annotation examples**, not four `@PreAuthorize` annotations stacked on the same method. `@beanName` is not a new Java annotation; it sits **inside the SpEL string** evaluated by `MethodSecurityExpressionHandler`. The `@` here is bean-lookup syntax, **different** from the `@` prefix on Java annotations like `@Component` or `@PreAuthorize`.

Breaking down the expression:

| Component | Meaning | Example |
| --- | --- | --- |
| `@documentPolicy` | Bean named `documentPolicy` looked up from ApplicationContext. | `@Component("documentPolicy")` or `@Bean("documentPolicy")`. |
| `.canRead(...)` | Calls the matching public method on the bean. | `boolean canRead(Authentication, long)`. |
| `authentication` | Variable/root property of the Spring Security context. | User principal and authorities. |
| `#id` | **Method parameter** variable resolved by name. | `read(long id)`. |
| `#root` | Method security expression root object. | Used with `@authz.decide(#root)` per official docs. |
| `and` | SpEL boolean logic; right-hand side is skipped if left-hand side is false. | Avoids DB policy queries when lacking authority. |
| `true`/`false` | Boolean policy allow/deny result. | `true` permits running; `false` denies. |

For example, `@documentPolicy.canRead(authentication, #id)` **does not automatically invoke** `canRead` on the annotated service itself, and **does not invoke an HTTP controller**. Spring fetches the named bean from the context and calls its Java method. The policy bean can also be reused by other services or unit-tested directly like any ordinary Java class.

The benefit of `@beanName`: it turns complex decisions into **business-named Java methods** that are easy to unit test, support dependency injection for repositories/permission services, are easy to log, and keep expressions concise. This is also an approach recommended by Spring Security documentation instead of subclassing a custom expression root just to add a few authorization checks.

## 2. Call path before the method body runs

You must understand the exact **evaluation timing** to apply policies effectively:

~~~text
HTTP controller / scheduler / listener / another bean
    |
    v
Call Spring-managed service through AOP proxy
    |
    v
AuthorizationManagerBeforeMethodInterceptor
  (evaluates @PreAuthorize)
    |
    +-- SpEL: hasAuthority('DOC_READ')
    |        AND
    |        @documentPolicy.canRead(authentication, #id)
    |                     |
    |                     +-- bean from ApplicationContext
    |                     +-- checks owner/tenant/status from DB
    |
    +-- FALSE -> AccessDeniedException
    |            METHOD BODY HAS NOT RUN
    |
    +-- TRUE  -> enter service method body
                    |
                    v
             DB/query or mutation
~~~

With `@EnableMethodSecurity`, Spring Security registers the interceptor for `@PreAuthorize`. The interceptor provides the expression context, evaluates the condition **before invoking the method**, and never enters the body if the decision denies. A policy bean may execute queries to decide, yet those queries belong to the **authorization phase**, not the protected method body.

If `canRead` returns false, the method does not run. If the bean is missing, the expression has a syntax error, parameter names cannot be resolved, or the policy throws an exception, that **does not equate to a clean authorization denial**: runtime may encounter a SpEL/bean/service error and return 5xx or be translated by an exception handler per design. Therefore test both **valid false** and **technical failures**; avoid catch-alls returning true when the database fails.

**Method-security checks only happen when invoked through a Spring AOP proxy.** `new DocumentService(...)` or calling `this.read(...)` inside the same bean can bypass the interceptor under default proxy mode. Never assume safety merely because `@PreAuthorize` appears in source code.

## 3. Minimal complete configuration: enabling method security

Enable in a Spring Boot configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Spring Boot Starter Security **does not enable method security automatically**. In Spring Security 6.x, `@EnableMethodSecurity` enables `@PreAuthorize` by default (unless pre/post is explicitly disabled). HTTP `SecurityFilterChain` and method security are two separate boundaries. An API may require `authenticated()` at HTTP, yet even after passing the HTTP filter, the service still denies if `@PreAuthorize` fails the domain policy.

Gradle Groovy dependencies example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is **only the dependencies block**, not a complete `build.gradle`; use the Spring Security version managed by the Spring Boot BOM. Do not use legacy `WebSecurityConfigurerAdapter` or `@EnableGlobalMethodSecurity` to start a new Boot 3 project.

Example request-level configuration showing both layers:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/documents/**").authenticated()
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

This is a **Spring bean snippet**, requiring imports, authentication config, and real URL controllers. `.authenticated()` only requires the caller to be authenticated at HTTP; whether the caller has permission on **Document 10** is still verified by the method's policy bean. You can also place a coarse authority at HTTP like `hasAuthority('DOC_READ')`, yet service protection remains necessary if non-HTTP entry points exist.

## 4. Declaring a clearly named policy bean

There are two common ways to name the bean.

### Approach A: @Component with an explicit name

~~~java
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    public boolean canRead(/* Authentication auth, long id */) {
        // Perform safe verification in Java.
        return false;
    }
}
~~~

This illustrates **how to declare the name**, with commented parameters to avoid tying it to specific business code. A real implementation must include full parameters and logic. `@Component("documentPolicy")` decouples the bean name from whether the `DocumentPolicy` class name changes.

### Approach B: @Bean with an explicit name

~~~java
@Configuration
class PolicyBeans {

    @Bean("documentPolicy")
    DocumentPolicy documentPolicy(DocumentRepository repository) {
        return new DocumentPolicy(repository);
    }
}
~~~

This is an **alternative approach**; do not define both this and `@Component("documentPolicy")` in the same context without explicit intent and override rules. With Approach B, the `DocumentPolicy(DocumentRepository)` constructor and dependencies must be defined accordingly. Both bean-creation approaches enable the `@documentPolicy.canRead(...)` expression.

If you write only `@Component` (unnamed), Spring typically derives the bean name from the class name via decapitalization, e.g., `documentPolicy`. Still, do not rely on inference during refactoring, especially with acronyms, nested beans, custom bean naming strategies, or multiple contexts. For security expressions, **explicit naming is easier to maintain**.

Bean names are **case-sensitive in reference resolution**. `@DocumentPolicy`, `@documentpolicy`, and `@documentPolicy` must not be assumed to refer to the same bean. If a bean lies outside component-scan scope or in another context, SpEL will not find it. That is a bean-configuration bug, not “admin lacks role”.

## 5. Policy bean example reading server data and checking multi-tenancy

Consider an application with documents belonging to different stores. A caller may read a document if **authenticated**, holding `DOC_READ`, the document exists, the caller is an **active member of the tenant**, and is **the owner or has team read access**. Such a design shows why checking roles alone is insufficient.

One way to express this in Spring Boot:

~~~java
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentRepository documents;
    private final TenantMembershipService memberships;

    public DocumentPolicy(DocumentRepository documents,
                          TenantMembershipService memberships) {
        this.documents = documents;
        this.memberships = memberships;
    }

    public boolean canRead(Authentication authentication, long documentId) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        boolean hasRead = authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("DOC_READ"));
        if (!hasRead) {
            return false;
        }

        Document doc = documents.findById(documentId).orElse(null);
        if (doc == null) {
            return false;
        }

        String actor = authentication.getName();
        boolean tenantAllowed =
            memberships.isActiveMember(actor, doc.getTenantId());
        if (!tenantAllowed) {
            return false;
        }

        boolean owner = actor.equals(doc.getOwnerUsername());
        boolean teamRead = authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("DOC_READ_TEAM"));
        return owner || teamRead;
    }
}
~~~

This is **Spring application code with project-provided dependencies**: `DocumentRepository`, `TenantMembershipService`, `Document` with `getTenantId()`/`getOwnerUsername()`, and principal-name verification must exist in the real codebase. `DocumentRepository.findById` returns `Optional<Document>` per the illustrative contract. Because there is no repository/database implementation yet, it cannot run standalone with JDK.

**Intentional security points:**

1. `authentication == null` and anonymous → **false**; never assume the caller is admin or “system”.
2. Missing `DOC_READ` → **false**, before needing to query the record.
3. Missing record → **false**, without disclosing owner/tenant details to unauthorized callers.
4. Tenant membership is queried from a **server-side verified source**, never trusting an `X-Tenant-Id` header sent by the client.
5. Ownership or team permissions are applied **only after** verifying the tenant. Having `DOC_READ_TEAM` in tenant A does not grant access to tenant B documents.
6. The policy returns a **boolean**, mutates no data, sends no emails, and performs no business writes; suitable for the pre-method authorization phase.

For tighter design, you can verify the document is not deleted/archived, or check time-bounded sharing and specific scopes. Never assume `isAuthenticated()` alone proves a user has rights to the data.

## 6. Using the policy bean in @PreAuthorize

A concise service can be written as:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #id)")
    public DocumentView read(@P("id") long documentId) {
        return documents.loadViewById(documentId);
    }
}
~~~

This is **Spring code depending on project-defined `DocumentRepository` and `DocumentView`**. Notice `@P("id")` maps SpEL name `#id` to Java parameter `documentId`. In a project configured with `-parameters`, `#documentId` can be used directly if parameter names are retained; here `@P` demonstrates explicit naming.

Walkthrough:

~~~text
caller -> DocumentService Spring proxy
  |
  v
@PreAuthorize expression
  @documentPolicy.canRead(authentication, #id)
  |
  +-- looks up bean named "documentPolicy"
  +-- #id = invocation's documentId
  +-- authentication = caller's principal/authorities
  +-- returns false? -> DENY; read(...) is not called
  +-- returns true?  -> calls read(...)
                     |
                     v
                documents.loadViewById(documentId)
~~~

If a user holds `DOC_READ` and is the owner in an allowed tenant → policy returns true, service executes. If the user lacks permission, passes another user's document ID, or targets another tenant → false, body does not run.

A shorter expression variant taking advantage of **short-circuiting**:

~~~java
@PreAuthorize(
    "hasAuthority('DOC_READ') and @documentPolicy.canRead(authentication, #id)")
public DocumentView read(@P("id") long documentId) {
    return documents.loadViewById(documentId);
}
~~~

Without `DOC_READ`, the left-hand side is false and SpEL **skips calling** `@documentPolicy.canRead` to query the DB. The policy code in the previous section should still check the authority itself: another caller might invoke the bean directly, or another rule might call the policy without the `hasAuthority` clause. Never rely solely on one method's expression structure to keep the policy safe everywhere.

### Parameter names: #id differs from @documentPolicy

- `@documentPolicy`: looks up a **Spring bean** by name.
- `#id`: looks up a **variable in the evaluation context**, here a method argument.
- `authentication`: built-in property/variable provided by the expression root.
- `#root`: the root object, commonly used when a policy wants access to multiple method-security helpers at once.

A common mistake is writing `@documentPolicy.canRead(authentication, @id)`. `@id` means look up a bean named `id`, **not read parameter `id`**. Likewise, `#documentPolicy.canRead(...)` does not look up a Spring bean via this mechanism; it expects a **variable** named `documentPolicy` in the evaluation context, which usually does not exist.

## 7. Passing Authentication: what is trustworthy, what is not?

In method security expressions, `authentication` is supplied from the current Spring Security context, bound to the execution/thread and security setup. It helps avoid scattering `SecurityContextHolder.getContext()` calls throughout policy beans.

The advantage of the signature:

~~~java
public boolean canRead(Authentication authentication, long documentId)
~~~

is **explicitly stating the inputs** (identity and target resource), making unit testing with mock/stub Authentication easy and reducing thread-local coupling inside domain policies. However, a policy must never return true just because `authentication != null` or `authentication.getName()` resembles some string. It must check permissions, membership, state, and server data.

`Authentication.getPrincipal()` may be `UserDetails`, `Jwt`, `OAuth2User`, or a custom principal depending on the mechanism. Never blindly cast `(AppUser) authentication.getPrincipal()` without certainty of runtime type. With JWTs, a converter must map claims to valid authorities, and the tenant source must be validated/accepted. If `authentication.getName()` is an ID that does not match the DB username column, the policy must use a **stable identifier** (subject/userId) instead of mismatched username strings.

Anonymous case: Spring Security can place an `AnonymousAuthenticationToken` in context, so `authentication` **is not necessarily null** for unauthenticated requests. Never rely solely on `authentication.isAuthenticated()` to verify a real user. Use an `AuthenticationTrustResolver`-backed helper when logic must distinguish anonymous, or check token types and authorities per the authentication mechanism.

**Spoofing defense:** HTTP clients can forge `X-User-Id` headers, submit `ownerUserName` in JSON bodies, or alter `tenantId`. Those values never replace server-verified `Authentication` and the tenant permissions database. Policies checking client-supplied `#owner` can be bypassed unless verified against the real record.

## 8. Passing #root to a policy bean: advanced scenario

Besides passing `Authentication` and individual parameters, official Spring Security 6.5 documentation shows passing the **method security expression root** to a bean:

~~~java
import org.springframework.security.access.expression.method.MethodSecurityExpressionOperations;
import org.springframework.stereotype.Component;

@Component("authz")
public class AuthorizationLogic {

    public boolean decide(MethodSecurityExpressionOperations operations) {
        return operations.hasAuthority("DOC_READ");
    }
}
~~~

In the service:

~~~java
@PreAuthorize("@authz.decide(#root)")
public DocumentView readDocument(long id) {
    return repository.loadViewById(id);
}
~~~

These two snippets are **code requiring a Spring context and application repository**, not a standalone Java file. `#root` here is **`MethodSecurityExpressionOperations`**, allowing the policy to use expression-root helpers (such as `hasAuthority`) instead of iterating `GrantedAuthority` manually. Spring Security also describes returning `AuthorizationDecision`/richer results in corresponding extension APIs; exact signatures must match the active version.

A variant also allows passing both root and method arguments if desired:

~~~java
@PreAuthorize("@documentAuthorization.mayRead(#root, #id)")
public DocumentView read(@P("id") long documentId) {
    return repository.loadViewById(documentId);
}
~~~

`documentAuthorization` must be a **bean with a public method matching that signature**, e.g., accepting `MethodSecurityExpressionOperations` and `long`. This differs from `DocumentPolicy.canRead(Authentication,long)`; do not mix signatures between the two patterns expecting SpEL to coerce types automatically.

**Which approach to choose?**

| Passing style | Advantages | Notes |
| --- | --- | --- |
| `@policy.canRead(authentication, #id)` | Easy to unit test with Authentication; resource is explicit. | Policy must verify authorities/trust itself and use domain repositories. |
| `@authz.decide(#root)` | Uses `MethodSecurityExpressionOperations` API and method-security helpers. | Policy couples more to Spring Security expression interfaces; needs method context tests. |
| `hasAuthority('...') and @policy.canRead(authentication, #id)` | Short-circuits coarse authority before querying domain. | Policy itself must still fail closed if called elsewhere. |
| `@policy.canRead(#id)` | Shortest if policy pulls actor from context itself. | Relies on hidden thread-local/bean context; harder to test. |

You do not need to write a custom `MethodSecurityExpressionHandler` or subclass the expression root just to add a `canRead` helper. **Calling a policy bean from SpEL is usually sufficient**; customize the handler only for genuine framework-level needs after checking the API contract for your active version.

### Boolean, null, and abstain

For policy beans returning `boolean`, return **`false` for any case lacking data or permission**. In higher extension APIs, Spring Security 6.5 docs describe nullable `Boolean` policies to represent **abstain**, as well as `AuthorizationDecision`/result types to convey reasons. **Do not return `null` as an arbitrary error code** when a policy ought to deny; abstain has different semantics depending on how managers/interceptors combine decisions. For business rules requiring fail-closed behavior, return an explicit boolean and test thoroughly.

## 9. Reusing a policy across multiple methods

A well-scoped policy bean can be called from multiple service methods:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
public DocumentView read(@P("id") long documentId) {
    return repository.loadViewById(documentId);
}

@PreAuthorize("@documentPolicy.canApprove(authentication, #id)")
public void approve(@P("id") long documentId) {
    documentWriter.approveAfterStateValidation(documentId);
}

@PreAuthorize("hasAuthority('DOC_DOWNLOAD') and @documentPolicy.canRead(authentication, #id)")
public byte[] download(@P("id") long documentId) {
    return documentExporter.generateFile(documentId);
}
~~~

These are **three method snippets inside a Spring service**, requiring a policy bean implementing both `canRead` and `canApprove`, plus `documentWriter`, `documentExporter`, and the application repository. A good policy uses clear names like `canRead`, `canApprove`, `mayDelete`, rather than lumping everything into an action-blind `isAllowed` boolean.

An `approve` operation might require:

- Holding `DOC_APPROVE` and being logged in.
- The document belongs to a tenant where the actor is an active member.
- The document is in `PENDING` status.
- Under the **four-eyes** rule, the approver must not be the document creator.
- Limits, time windows, feature flags, and business constraints are satisfied.

**Do not infer** that `canRead` true implies `canApprove` true. Viewing and changing resource state are distinct actions requiring distinct checks.

For `approve`, `@PreAuthorize` is a **pre-body gate**, yet data can change between the policy query and the write transaction. The method must re-verify invariants close to the update (optimistic version checks or conditional SQL); state/tenant constraints cannot live solely in the pre-check policy.

## 10. Example policy bean for approve with domain state

Extending the policy class from section 5:

~~~java
public boolean canApprove(Authentication authentication, long documentId) {
    if (authentication == null
            || !authentication.isAuthenticated()
            || authentication instanceof AnonymousAuthenticationToken) {
        return false;
    }
    boolean hasPermission = authentication.getAuthorities().stream()
        .anyMatch(a -> a.getAuthority().equals("DOC_APPROVE"));
    if (!hasPermission) {
        return false;
    }

    Document doc = documents.findById(documentId).orElse(null);
    if (doc == null || !"PENDING".equals(doc.getStatus())) {
        return false;
    }

    String actor = authentication.getName();
    return memberships.isActiveMember(actor, doc.getTenantId())
            && !actor.equals(doc.getOwnerUsername());
}
~~~

This is a **Java method added to the previously defined `DocumentPolicy`**, not a standalone class/file. It demonstrates **fail-closed logic, role/permission, tenant, state, and separation of duties**. When a document does not exist or permissions are insufficient, it **reveals no details** about the tenant or creator.

For reliable operation, configure appropriate transaction isolation/locking. For example, if document status moves from PENDING to CLOSED right after the policy check, `approveAfterStateValidation` must reject the update. If external side effects exist (emails, webhooks), apply outbox/idempotency and dispatch only after the transaction commits; `@PreAuthorize` alone does not guarantee rolling back external side effects.

## 11. Bean names, lifecycle, and dependency injection: common failures

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| SpEL reports bean `documentPolicy` not found | Class not component-scanned, wrong bean name, or bean in another context. | Check `@Component("documentPolicy")`/`@Bean("documentPolicy")`, package scan, and application context. |
| Bean exists but `canRead` cannot be called | Method not public, signature/types mismatch, or wrong method name. | Use a public method with a clear signature and unit test it. |
| `#documentId` is null even though caller passed a number | Spring could not discover the parameter name. | Enable `-parameters` or use `@P("id")` and `#id`. |
| Policy returns false for everyone | Different authority prefix, invalid tenant membership, or wrong principal name mapping. | Inspect real auth data; test owner/tenant/permissions. |
| Service runs even though policy returns false | Method security not enabled or call bypasses proxy. | `@EnableMethodSecurity`, inject bean, test for self-invocation. |
| 500 error instead of 403 | Bean exception, DB/SpEL/type-conversion error, not a normal boolean deny. | Separate technical errors from authorization decisions; fail closed with controlled exception handling. |
| Policy queries are very slow | DB query per invocation, N+1, missing index/tenant filter. | Optimize repository, existence queries, indexes, and measure latency. |
| User reads another tenant's data | Tenant taken from forged header or policy only checks role/owner. | Verify membership server-side; include tenant in DB predicates. |
| Policy tests pass yet HTTP still returns 403 | HTTP filter, CSRF, auth entry point, or another chain blocks before method. | Test HTTP and methods separately to isolate the failing layer. |

If a bean has special characters like hyphens, SpEL supports quoted bean reference syntax; however, for readability and fewer bugs, **prefer normal alphanumeric camelCase names** like `documentPolicy`.

**Never put entire policies in static methods or store current-user state in singletons.** `@Component` beans are singletons by default, serving many users concurrently; never store `currentUser`, `lastDocument`, or a request's `Authentication` in **mutable singleton fields**. Each call must rely only on the passed-in Authentication/ID, repositories, and properly scoped services.

## 12. Policy reliability: fail closed and server data

Because policy beans can query DBs, call services, and combine many conditions, design **safe denial rules**:

1. **Unauthenticated or missing authority → false.**
2. **Resource missing or not permitted to be disclosed → false** or a handled error that leaks no out-of-scope resource; policy responses must not disclose owner/tenant to unauthorized callers.
3. **Invalid tenant membership → false**, even if a system-wide role looks sufficient.
4. **Cannot read permission data due to outage → do not allow.** Technical errors may yield 5xx, yet never fall back to ALLOW.
5. **Never use client inputs as the source of truth for ownership.** Document IDs must be resolved on the server.
6. **Never grant access from URL alone.** A URL matching `/api/documents/**` only identifies endpoint type, not that the caller can read document 42.
7. **Minimize sensitive data in logs**: log decision types/request correlation IDs, never JWTs, cookies, or full PII objects.
8. **Avoid side effects inside policies**: before method execution, a policy should read and decide, not send emails, write records, or mutate state.
9. **Use meaningful permission names**: `DOC_READ`, `DOC_APPROVE`, `DOC_DOWNLOAD` instead of a coarse role that hides actions.
10. **Account for time races**: a pre-check policy passes at T1 while the record changes at T2; writes must re-verify under transaction.

A common risk is “skipping policy because it's only a read endpoint”. If an endpoint returns invoices, addresses, reports, or private files, **reading is also an action requiring authorization**. `@PreAuthorize` blocks before the service loads objects; combining it with query-scoped data access avoids fetching unauthorized records from the database altogether.

## 13. Performance and authorization when calling policies from SpEL

Every proxied method call can **evaluate the expression** and invoke the policy bean. If a policy calls `repository.findById`, a request listing 1000 records and invoking `canRead` per record can trigger thousands of DB queries. Consider:

- **Check coarse permissions at the method** first, e.g., `hasAuthority('DOC_READ')`, then query **tenant/owner-scoped data** in the repository.
- For a single object ID, use `existsByIdAndOwner...` or tenant-scoped queries when sufficient to minimize fetched data. Add proper indexes.
- For lists/pages, **filter inside the DB** by tenant, owner, and sharing scope so pagination and total counts remain accurate; avoid invoking a policy bean per item when server-side query predicates are more efficient.
- Cache decisions only when you account for **permission revocation**, membership/role/state changes, and include actor, tenant, action, resource, version, or proper TTL in the cache key. Caching `canRead(documentId)` without actor/tenant is a vulnerability.
- If a policy calls an external service, configure timeouts and fail-closed circuit breakers so system errors never become ALLOW.
- In boolean conditions, write `hasAuthority(...) and @policy...` to avoid DB queries when clearly unauthorized; yet keep full checks inside the policy itself for reuse.
- When tenant + owner + state must hold right before writing, let the transaction/domain method enforce **update-time invariants**, not only cached pre-checks.

Important trade-off: extracting a policy bean makes logic easy to test, yet **does not magically fix N+1 queries or transactional consistency**. `@PreAuthorize` outside a `@Transactional` method can execute under a different transaction boundary. Measure/verify advice ordering if strict snapshot consistency is required; typically, keep pre-checks for authorization gating and enforce write-time invariants inside the transaction.

## 14. Testing policy beans in isolation: input → boolean

A strength of `@beanName` is that policy logic can be tested without starting a full HTTP server. For `DocumentPolicy`, use mock/fake repositories and membership services to cover scenarios:

| Actor / resource | Permission | Membership/owner | Expected `canRead` |
| --- | --- | --- | --- |
| Alice reads her own document in tenant A | Has `DOC_READ` | Active membership A, owner Alice | `true`. |
| Alice reads Bob's document in same tenant A | Has `DOC_READ` | No team read | `false`. |
| Tenant A manager reads Bob's doc in tenant A | `DOC_READ` + `DOC_READ_TEAM` | Valid membership A | `true`. |
| Tenant A manager reads doc in tenant B | Has `DOC_READ_TEAM` | No membership B | `false`. |
| Guest reads public-looking document by mistake | Missing `DOC_READ` | Even if ID exists | `false`. |
| Nonexistent document ID | Has permission | Repository returns empty | `false`. |
| Anonymous/null Authentication | Invalid | Document not checked | `false`. |
| Revoked permission | No longer has `DOC_READ` | Owner still Alice | `false`. |

For `canApprove`, also test `PENDING` status, actor not equal to creator (four-eyes), different tenant, missing `DOC_APPROVE`, and closed/deleted records.

**Policy unit tests** should verify **no side effects**, no data leakage in decisions, and no queries executed when authority is missing. Use a mock repository with `verifyNoInteractions` for missing-authority cases if short-circuited. Still, pure policy tests **do not prove `@PreAuthorize` is wired by Spring**; add method-security integration tests as well.

## 15. Testing real annotations: @WithMockUser and service proxies

A Spring Boot integration test with `spring-security-test` calls the service bean through its proxy:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class DocumentServiceSecurityIT {

    @Autowired DocumentService documents;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void ownerCanReadDocument() {
        DocumentView view = documents.read(10L);
        assertNotNull(view);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void ownerCannotReadOtherTenant() {
        assertThrows(AccessDeniedException.class,
            () -> documents.read(12L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER_PERMISSION")
    void missingPermissionDenied() {
        assertThrows(AccessDeniedException.class,
            () -> documents.read(10L));
    }
}
~~~

This is a **test framework skeleton**, requiring DB fixtures or mock repositories/memberships, real `DocumentView`/`DocumentService` beans, `@EnableMethodSecurity`, and a Spring Test context. IDs 10/12 are **example IDs** and do not exist automatically in a database. `@WithMockUser` populates the security context with the specified username and authorities, while tenant membership must be set up in fixtures so the policy logic returns accurately.

To prove `@PreAuthorize` **actually blocks the body**, use a spy/counter on `loadViewById` or in the service body: when policy returns false, the method body **must not be called**. Testing only that `@documentPolicy.canRead(...)` returns false verifies the policy bean, not that the expression resolved the bean or that the interceptor ran.

A diagnostic test for a wrong bean name can intentionally omit `documentPolicy` from a test context, causing invocation to fail SpEL evaluation. Never write tests expecting 403 from a misconfigured bean, as that is not a normal false policy decision.

### Testing the HTTP → service path as well

Alongside direct service tests, use `MockMvc` or real Servlet container tests to verify HTTP endpoints:

- Anonymous calling a private API: may return 401 or redirect depending on the authentication entry point.
- Has `DOC_READ`, same tenant/owner document: policy permits, valid response.
- Has `DOC_READ` but different owner/tenant: method security denies, typically 403 with standard web exception handling.
- Missing `DOC_READ`: HTTP filter or method may block; verify **which layer** blocked if needed.
- Nonexistent ID: do not return out-of-scope owner/tenant info.
- Service invoked from job or message listener: method security still runs through proxy, yet workers need valid identity/service context.

An HTTP 403 response **does not suffice** to prove the SpEL bean works: CSRF, HTTP `AuthorizationFilter`, or authentication filters can block before the controller. Testing **pure policy bean → direct method proxy → HTTP integration** in order pinpoints failures accurately.

## 16. Standalone Java 17: simulating policy invocation before method body

The program below **uses no Spring libraries** and performs no real SpEL parsing/AOP. It mirrors `@PreAuthorize("@documentPolicy.canRead(authentication, #id)")`: a policy method **is invoked before the service body**, uses the actor/permissions and server data, and runs the body only when permitted. Another policy checks four-eyes for approval.

Save with the exact name **`PolicyBeanDecisionDemo.java`**:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

public class PolicyBeanDecisionDemo {
    record Actor(String name, String tenant, Set<String> authorities) {}
    record Document(int id, String owner, String tenant, String state) {}

    static final class DocumentRepository {
        private final Map<Integer, Document> documents = Map.of(
                10, new Document(10, "alice", "shop-a", "PENDING"),
                11, new Document(11, "bob", "shop-a", "PENDING"),
                12, new Document(12, "alice", "shop-b", "PENDING"),
                13, new Document(13, "bob", "shop-a", "CLOSED"));

        Document find(int id) { return documents.get(id); }
    }

    static final class DocumentPolicy {
        private final DocumentRepository repository;
        DocumentPolicy(DocumentRepository repository) {
            this.repository = repository;
        }

        boolean canRead(Actor actor, int id) {
            if (actor == null || !actor.authorities().contains("DOC_READ")) {
                return false;
            }
            Document doc = repository.find(id);
            if (doc == null || !actor.tenant().equals(doc.tenant())) {
                return false;
            }
            return actor.name().equals(doc.owner())
                    || actor.authorities().contains("DOC_READ_TEAM");
        }

        boolean canApprove(Actor actor, int id) {
            if (actor == null || !actor.authorities().contains("DOC_APPROVE")) {
                return false;
            }
            Document doc = repository.find(id);
            return doc != null
                    && actor.tenant().equals(doc.tenant())
                    && doc.state().equals("PENDING")
                    && !actor.name().equals(doc.owner());
        }
    }

    static String readWithGuard(DocumentPolicy policy, Actor actor,
                                int id, AtomicInteger bodyRuns) {
        if (!policy.canRead(actor, id)) {
            throw new SecurityException("Access denied");
        }
        bodyRuns.incrementAndGet();
        return "document-" + id;
    }

    public static void main(String[] args) {
        DocumentPolicy policy = new DocumentPolicy(new DocumentRepository());
        Actor alice = new Actor("alice", "shop-a", Set.of("DOC_READ"));
        Actor manager = new Actor("manager", "shop-a",
                Set.of("DOC_READ", "DOC_READ_TEAM", "DOC_APPROVE"));
        Actor bob = new Actor("bob", "shop-a", Set.of("DOC_APPROVE"));
        Actor guest = new Actor("guest", "shop-a", Set.of());
        AtomicInteger bodyRuns = new AtomicInteger();

        System.out.println("Alice read own: " + policy.canRead(alice, 10));
        System.out.println("Alice read Bob: " + policy.canRead(alice, 11));
        System.out.println("Manager read Bob: " + policy.canRead(manager, 11));
        System.out.println("Manager cross tenant: " + policy.canRead(manager, 12));
        System.out.println("Guest read: " + policy.canRead(guest, 10));
        System.out.println("Missing document: " + policy.canRead(alice, 999));
        System.out.println("Null actor: " + policy.canRead(null, 10));
        System.out.println("Bob approve Alice: " + policy.canApprove(bob, 10));
        System.out.println("Bob approve own: " + policy.canApprove(bob, 11));
        System.out.println("Manager approve closed: " + policy.canApprove(manager, 13));

        boolean denied = false;
        try {
            readWithGuard(policy, alice, 11, bodyRuns);
        } catch (SecurityException ex) {
            denied = true;
        }
        System.out.println("Denied before method body: " + denied);
        System.out.println("Body runs after denial: " + bodyRuns.get());
        System.out.println("Allowed method result: "
                + readWithGuard(policy, alice, 10, bodyRuns));
        System.out.println("Body runs after allow: " + bodyRuns.get());
    }
}
~~~

Compile/run with **JDK 17 or later**:

~~~bash
javac --release 17 PolicyBeanDecisionDemo.java
java PolicyBeanDecisionDemo
~~~

Exact output (verified against JDK 17 target):

~~~text
Alice read own: true
Alice read Bob: false
Manager read Bob: true
Manager cross tenant: false
Guest read: false
Missing document: false
Null actor: false
Bob approve Alice: true
Bob approve own: false
Manager approve closed: false
Denied before method body: true
Body runs after denial: 0
Allowed method result: document-10
Body runs after allow: 1
~~~

Key lines: `Manager cross tenant: false` proves team permission alone cannot cross tenants; `Missing document: false` and `Null actor: false` demonstrate fail-closed behavior; `Denied before method body: true` and `Body runs after denial: 0` illustrate pre-authorization blocking execution. `Bob approve own: false` enforces four-eyes, while `Manager approve closed: false` reflects resource state.

**This is a plain Java model**: `Actor`/`Document` are demo-defined records rather than Spring `Authentication`, `DocumentRepository` is an in-memory map, and `readWithGuard` does not actually run AOP. The purpose is testing logic before moving it into a real `@Component("documentPolicy")` and `@PreAuthorize`.

## 17. Common mistakes and solutions

1. **Writing `@beanName` outside a SpEL string.** → This syntax goes **inside** `@PreAuthorize("...")`, not as a Java annotation.
2. **Confusing `#id` with `@id`.** → `#id` is a parameter; `@id` is a bean reference.
3. **Missing a bean named `documentPolicy`.** → Use explicit naming and verify component scanning/context.
4. **Non-public policy method or wrong signature.** → Write a public Java method taking the right Authentication/ID and returning a clear boolean.
5. **`@EnableMethodSecurity` not enabled.** → Enable the configuration and test that an under-privileged case is actually blocked.
6. **Service self-invocation or instantiating with `new`.** → Invoke via the Spring proxy and add negative body-not-run tests.
7. **Unresolved `#documentId` name.** → Enable `-parameters` or `@P("id")` and update the expression.
8. **Policy only compares owner from a client DTO.** → Query the server DB by ID and check tenant and ownership.
9. **Policy allows when record is missing or DB errors.** → Fail closed; technical errors must never auto-ALLOW.
10. **Singleton policy storing Authentication in a mutable field.** → Never mix request identities; pass context per invocation.
11. **Role prefix mismatch.** → `hasRole('ADMIN')` usually needs `ROLE_ADMIN`, whereas JWT authorities may be `SCOPE_admin`.
12. **User with permission still gets ALLOW on another tenant.** → Verify server-side membership and the real resource's tenant.
13. **Calling `canRead` 1000 times for a 1000-item list.** → Design scoped queries/existence checks/indexes and batch policies.
14. **Caching decisions without actor/tenant/action in key.** → Can leak permissions across users; cache keys and invalidation must be exact.
15. **Using `@PreAuthorize` instead of transactional invariants.** → Add conditional updates/locking in the body.
16. **Equating SpEL 500 errors with 403 permission denials.** → Separate configuration/technical failures from boolean deny.
17. **Using policy beans to send emails or write DB before authorization.** → Policies must have no side effects; decide only.
18. **Testing only HTTP 403 without testing bean/method.** → Test each layer to avoid false positives from early CSRF/HTTP filter rejections.
19. **Assuming `principal.tenantId` always exists.** → Verify the auth mechanism and actual custom principal type; never cast blindly.
20. **Assuming permissions captured at job submission remain valid at run time.** → For async/background work, verify identity, expiration, and domain permissions at execution time.

## 18. Checklist for adding a new protected method

Before merging a `@PreAuthorize("@policy...")`, verify:

- [ ] Policy bean has an explicit name and exists in the right application context.
- [ ] `@EnableMethodSecurity` is enabled and the method is called through a Spring AOP proxy.
- [ ] SpEL properly uses `@beanName`, `#argument`, `authentication`, or `#root`.
- [ ] Policy method accepts the right types and returns boolean **false** whenever permission cannot be verified.
- [ ] Owner/tenant/status data comes from trusted server sources, never arbitrary client inputs.
- [ ] Auth is checked accurately, including anonymous, role/authority prefixes, and principal types.
- [ ] Policy causes no side effects and fails closed on dependency timeouts/errors.
- [ ] Queries are optimized if called in loops or large lists; caching never omits actor/tenant.
- [ ] Data writes still re-check invariants inside the transaction when state can change.
- [ ] Pure policy tests cover ALLOW/DENY and tenant/owner/missing/anonymous cases.
- [ ] Service proxy tests prove false blocks the body; do not test only the policy method directly.
- [ ] Integration tests cover HTTP→service and non-HTTP entry points.
- [ ] Error handling never leaks documents/tenants belonging to others.
- [ ] Regression tests cover changes to bean names, method signatures, parameter names, JWT converters, or Spring Security versions.

**Conclusion:** `@beanName` in `@PreAuthorize` is **SpEL syntax to invoke a Spring policy bean**, not an automatic authorization mechanism. It lets you move authorization logic out of long expressions into **testable Java**, combining `Authentication`, method arguments, and server data to decide **before the body runs**. Safe policies must fail closed, enforce owner/tenant/state constraints, have no side effects, and be tested across **three layers: policy bean, method AOP proxy, and HTTP integration**.

### Official references

- [Spring Security 6.5 — Method Security: Using a Custom Bean in SpEL](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Method Security: Method Parameters and Expression Handling](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — PreAuthorize API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PreAuthorize.html)
- [Spring Framework — SpEL Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/beanref.html)
- [Spring Framework — AOP Proxying and Self Invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
