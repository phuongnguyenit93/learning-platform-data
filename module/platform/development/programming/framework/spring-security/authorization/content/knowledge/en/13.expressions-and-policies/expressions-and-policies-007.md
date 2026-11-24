# Expressions for Null Data, Missing Data, and Indeterminate Conditions

## 1. Why is this a security issue?

An authorization expression often reads data from the principal, token claims, method arguments, database records, or a permission service. Any of those sources can lack a value for many reasons: the user is not logged in, a tenant claim is absent, the request omitted an ID, an object field is `null`, data is out of sync, or the permission service failed.

If an expression is written assuming every value exists, the result can be a SpEL evaluation error, unexpected behavior, or worse, **granting access without grounds**.

Semantically wrong example:

~~~java
@PreAuthorize("#documentId == null or hasAuthority('document:read')")
~~~

When `documentId == null`, the left side is true and the whole expression evaluates to true, even if the user **lacks** read permission. Missing data accidentally became a reason to allow access.

Clearer example:

~~~java
@PreAuthorize("#documentId != null and hasAuthority('document:read')")
~~~

The latter only illustrates a necessary condition; holding `document:read` still does not prove the user may read **that specific document**. For private resources, add actual owner, tenant, or ACL checks.

**Core rule:** grant access only when sufficient valid evidence exists to conclude **ALLOW**. Missing values, `null`, unverifiable data, or evaluation errors **must never turn into ALLOW**. You may deny or return a controlled technical error per your API contract, but never proceed with the privileged action.

## 2. Three cases that must be distinguished

| Case | Meaning | Example | How to handle in authorization conditions |
|---|---|---|---|
| `null` | Variable/field exists, yet its Java value is `null` | `request.ownerId() == null` | Check explicitly; deny when required attribute is missing |
| **Missing** data | No key, claim, bound parameter, or record exists | JWT lacks `tenant_id` claim; map lacks key | Distinguish absent from present-null for logging/validation if needed, but never infer permission |
| **Indeterminate** condition | Cannot conclude authorization because a dependency is unavailable or errored | Permission service timeout; ACL source unreachable | Do not grant; pick DENY or controlled failure per policy |

These are not a single concept:

- `null` is a reference value in Java and SpEL.
- "Missing" may mean a SpEL parameter binding failure, an absent `Map` key, a missing token claim, or a resource not found. Some APIs map "missing" to `null`; others throw an exception.
- "Indeterminate" is a **domain decision state** when evidence is insufficient. Spring Security does not provide a default three-valued SpEL operator `ALLOW/DENY/UNKNOWN`; the application must define handling explicitly.

Do not confuse "does not have permission" with "unknown whether user has permission." Both are **insufficient to grant access**, yet distinguishing them helps return accurate HTTP codes, monitor operational failures, and write proper tests.

## 3. How does SpEL handle null?

In method security, annotations like `@PreAuthorize` and `@PostAuthorize` use Spring Expression Language (SpEL). SpEL supports the `null` literal, comparisons, boolean logic, the ternary operator, Elvis `?:`, and safe navigation `?.`.

### 3.1. Check presence before using data

~~~spel
#documentId != null and hasAuthority('document:read')
~~~

If the ID is mandatory, reject early when missing. For integers, also validate bounds (e.g., positive ID); for strings, check empty or whitespace-only if policy requires.

Nested condition example:

~~~spel
#request != null and #request.owner != null
    and #request.owner.id != null
    and #request.owner.id == authentication.name
~~~

Logical `and`/`or` operators use **short-circuit evaluation**: if the left side of `and` is false, the right side is not evaluated. This avoids null property dereferences when guards are ordered properly.

Conversely, writing:

~~~spel
#request.owner.id == authentication.name and #request != null
~~~

is ordered wrong: `#request.owner` is accessed **before** `#request != null` is checked.

### 3.2. Safe navigation with ?.

~~~spel
#request?.owner?.id
~~~

If `request` or `owner` is `null`, this chain evaluates to `null` instead of throwing on dereference at positions guarded by `?.`.

**Important:** `?.` does not automatically "cascade" across the rest of an expression. For example:

~~~spel
#request?.owner.id
~~~

can still fail when `request` is `null`: `#request?.owner` returns `null`, and then `.id` is still evaluated on `null`. Use `#request?.owner?.id` or full explicit guards.

`?.` only guards against **null references at that specific property access**. It does not solve non-existent properties on an object type, getters throwing exceptions, missing permissions, invalid data, or remote service failures.

For security conditions, prefer producing an explicit boolean result:

~~~spel
#request?.owner?.id != null
    and #request.owner.id == authentication.name
~~~

Here the first comparison eliminates null chains; the second runs only when data is present. For complex policies, writing in a Java bean is easier to maintain and test.

### 3.3. Elvis ?: and default values

~~~spel
#displayName ?: 'Anonymous'
~~~

SpEL's Elvis operator returns the right-hand value when the left-hand side is `null` **or an empty string**. It is handy for display text, yet highly dangerous when used as an **authorization value**.

Dangerous example:

~~~spel
#tenantId ?: 'public'
~~~

If the tenant has not been verified, defaulting the tenant can cause cross-boundary access. Similarly, defaulting to `true` or a "reader" role when a claim is missing is a **fail-open** flaw.

Use defaults only when the business specification explicitly defines that default as valid, independently controlled, and **non-privilege-escalating**. For data required by authorization, missing values should result in denial or appropriate validation/authentication errors.

### 3.4. Relational comparisons with null do not replace validation

SpEL has ordering rules for `null`: `null` represents "nothing", distinct from the number 0. Thus, for a non-null value, `value > null` can evaluate to `true`; never use `> null` to mean "meets requirement."

If a policy requires an age, threshold, or priority level, write a meaningful check:

~~~spel
#minimumAge != null and #minimumAge >= 18
~~~

Never write `#minimumAge > null` or rely on implicit type coercion. For dates, money, longs, or enums, normalize and validate exact types before evaluating.

### 3.5. Ternary can be used, but the missing branch must be explicit

~~~spel
#request?.ownerId != null
    ? #request.ownerId == authentication.name
    : false
~~~

The `false` branch encodes the policy: **no owner ID means no access**. For long multi-branch expressions, replace them with `@policyBean.can...(...)` to reduce structural mistakes.

## 4. "No Authentication" differs from "anonymous user"

An unauthenticated request can flow through Spring Security mechanisms in multiple ways:

- `Authentication` may be absent from the security context on certain call paths.
- Applications enabling anonymous authentication may populate an `AnonymousAuthenticationToken` with a principal such as `anonymousUser`. Therefore, checking only `authentication != null` or `principal != null` is **not sufficient** to conclude the user is logged in.
- Some applications use remember-me; sensitive operations may require full authentication rather than remember-me recognition.

In Spring Security's expression root:

~~~java
@PreAuthorize("isAuthenticated() and hasAuthority('document:read')")
~~~

`isAuthenticated()` means the user is authenticated according to Spring Security rules, unlike a Java non-null check. For use cases that must exclude remember-me as well, consider `isFullyAuthenticated()` matching your application's authentication setup.

When accessing custom claims or properties of `principal`, never assume `principal` is always a `Jwt`, `UserDetails`, or custom class. The principal varies across JWT, session, OAuth2 login, anonymous, or test security contexts.

Brief example illustrating the risk:

~~~spel
principal.tenantId == #tenantId
~~~

If `principal` lacks a `tenantId` property or its type changes, SpEL evaluation can fail. A resilient solution is normalizing the principal into an **access scope** in Java or using a policy bean that checks type, claims, and trust before comparing.

## 5. Method parameters can be null or "lose their names"

In `@PreAuthorize`, `#documentId` is the **method parameter name discovered by Spring Security**, which does not always appear automatically. Name discovery depends on metadata like `-parameters`, `@P` annotations, or supported parameter name discoverers.

To keep expressions unambiguous at compile time, specify names explicitly:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentCommandService {
    @PreAuthorize("#documentId != null and hasAuthority('document:read')")
    public String read(@P("documentId") Long id) {
        return "document-" + id;
    }
}
~~~

This snippet is a **Spring integration example**. It illustrates only parameter binding and operation authority checks, and is **not sufficient** for per-record authorization. If a parameter name cannot be discovered for an expression, the variable may fail to resolve as intended or the expression may behave incorrectly; never "fix" missing data by turning it into an allow.

Cases to test separately:

1. The actual argument passed is `null` and the expression evaluates `#documentId == null`.
2. Parameter name cannot be discovered; the expression references the wrong name or wrong casing.
3. Parameter is an unexpected object type or a nested property does not exist.
4. Annotation is bypassed via internal `this.method()` self-invocation instead of going through the Spring proxy.
5. Policy bean is unregistered or the expression's bean reference is misspelled.

Do not lump all of these under "user lacks permission"; configuration or expression bugs may need to surface as system errors via logging/monitoring, while the privileged operation still must not execute.

## 6. Missing data in Maps, JSON, and JWT claims

A map has at least three important states:

~~~java
Map<String, String> claims = new HashMap<>();
// 1. claims.containsKey("tenant_id") == false: missing key
claims.put("tenant_id", null);
// 2. claims.containsKey("tenant_id") == true, get(...) == null
claims.put("tenant_id", "north");
// 3. key present with value "north"
~~~

`Map.get(key) == null` does not distinguish case 1 from case 2. If a policy needs metrics, validation, or data migration, use `containsKey` and check the value separately. For authorization decisions, both states lacking a valid tenant value must be **insufficient to grant access**.

Illustrative expression when `claims` is a trusted Map placed into the evaluation context:

~~~spel
#claims != null
    and #claims.containsKey('tenant_id')
    and #claims['tenant_id'] != null
    and #claims['tenant_id'] == #trustedTenant
~~~

This is **illustrative SpEL syntax**; `#claims` and `#trustedTenant` only exist if code explicitly binds them into the evaluation context. Do not assume both variables exist in every `@PreAuthorize`. Beyond presence, the claim source must have verified signature, issuer/audience, and claim semantics per application configuration.

For JWTs, never use **unverified** header or payload data as authority/tenant scope. When a tenant claim is missing, never fall back to a client-sent query parameter without verifying membership/permissions.

For JSON trees, libraries may distinguish "missing node", "null node", and empty strings. Those are differences in **source data representation**, not three default permission tiers. Normalize into a domain model with required fields validated before computing permissions.

## 7. Optional, empty strings, and sentinel values

### Optional is not the same as null

In Java, `Optional.empty()` is an existing object holding no value, distinct from a `null` reference. Never write expressions calling `#maybeOwner.get()` without ensuring presence; it can throw `NoSuchElementException`.

Safe navigation behavior on `Optional` depends on Spring Framework version: automatic unwrapping of `Optional` in null-safe operations was introduced in Spring Framework 7.0. If your application runs Spring Framework 6.x, **do not assume** `#optional?.name` behaves as if `Optional` were automatically unwrapped. For critical authorization checks, unwrap and check explicitly in Java or a policy bean, returning a clear `boolean`.

~~~java
Optional<String> owner = repository.findOwnerName(documentId);
boolean ownerMatches = owner
        .map(name -> name.equals(authenticatedUsername))
        .orElse(false);
~~~

This Java snippet illustrates logic once `repository` and `authenticatedUsername` are verified; it is not a standalone program. Matching the owner suffices only if the policy is genuinely owner-only and tenant/resource scope are fully verified too.

### Empty strings do not mean absent in every context

Values like `null`, `""`, `"   "`, and `"unknown"` may require distinct handling:

- `null` and empty strings: usually represent no valid ID/tenant.
- Whitespace-only strings: also not valid identifiers without normalization rules.
- `"unknown"`, `"N/A"`, `"guest"`: may be **real data values**, not null; handle them per explicit contract to avoid colliding with a valid principal or tenant.

Never use generic sentinels like `"public"` or `"default"` to grant read access when tenant/owner is missing. If a resource is truly public, enforce a **governed public flag/policy**, never infer "public" from a null owner field.

## 8. Do not confuse SpEL with SQL three-valued logic

In SQL, expressions involving `NULL` can yield `UNKNOWN` under **three-valued logic**:

| SQL expression | Result |
|---|---|
| `5 = NULL` | `UNKNOWN` |
| `NULL = NULL` | `UNKNOWN` |
| `NULL IS NULL` | `TRUE` |
| `UNKNOWN AND FALSE` | `FALSE` |
| `UNKNOWN OR TRUE` | `TRUE` |
| `NOT UNKNOWN` | `UNKNOWN` |

In a `WHERE` clause, SQL retains only rows where the predicate evaluates to `TRUE`; both `FALSE` and `UNKNOWN` are excluded. For example:

~~~sql
SELECT id, title
FROM documents
WHERE tenant_id = :trusted_tenant
  AND owner_username = :authenticated_user;
~~~

If a row's `tenant_id` or `owner_username` is NULL, standard equality checks do not match and the row is omitted. This can support fail-closed filtering, **provided** the bound parameters themselves represent verified authorization scope.

However, SQL `UNKNOWN` is **not** a permission service's `INDETERMINATE` decision. One is an SQL operator outcome on NULL; the other is missing evidence or a query/policy decision failure at the application layer.

Never casually add:

~~~sql
WHERE owner_username = :authenticated_user
   OR owner_username IS NULL
~~~

unless the specification explicitly defines **NULL-owner documents as public** with other protective rules in place. "Belongs to nobody (NULL)" does not mean "everyone may read it."

## 9. Common annotations and null checking

### 9.1. @PreAuthorize: pre-action check

~~~java
@PreAuthorize(
    "isAuthenticated() and #request != null " +
    "and #request.documentId != null " +
    "and hasAuthority('document:write') " +
    "and @documentPolicy.canWrite(authentication, #request)"
)
public void update(@P("request") UpdateDocumentRequest request) {
    documentService.update(request);
}
~~~

This is an integration pattern depending on the application's domain beans/classes. Ensure the policy bean **does not trust** client-entered tenant/owner values from the request and checks the real resource at the source. SpEL `and` short-circuits, so the bean is not called if earlier required conditions fail.

When policies grow complex, move nested property, identity, tenant, and ACL checks into a Java method to reduce duplication and improve testability.

### 9.2. @PostAuthorize: null return values

~~~java
@PostAuthorize(
    "returnObject != null " +
    "and returnObject.ownerUsername == authentication.name"
)
public DocumentView findOne(Long id) {
    return documentService.findOne(id);
}
~~~

`returnObject` is the value after the method runs. Guarding before reading properties prevents null access errors. Still, distinguish **record not found** from **not authorized to view** per your API contract, and consider putting tenant/ACL predicates into the detail query so out-of-scope data is never loaded in the first place. `@PostAuthorize` can deny the entire result; it does not filter individual fields.

### 9.3. @PostFilter: null elements in lists

~~~java
@PostFilter(
    "filterObject != null " +
    "and filterObject.ownerUsername != null " +
    "and filterObject.ownerUsername == authentication.name"
)
public List<DocumentView> findSmallPreview() {
    return previewService.loadBoundedPreview();
}
~~~

This guard prevents null elements from causing dereference errors. It does not make a collection safe if sensitive data was already cached or logged upstream, nor does it adjust query totals or pagination. Use only after confirming collection mutability and that the dataset is **bounded and small**.

### 9.4. @PreFilter: collection arguments containing null elements

~~~java
@PreFilter(
    "filterObject != null " +
    "and filterObject.ownerUsername == authentication.name"
)
public void process(List<DocumentInput> inputs) {
    // inputs contains only elements matching the expression per the interceptor
}
~~~

This snippet illustrates an annotation at the Spring method security boundary, not a standalone runnable app. Verify collection type, mutability, and method contract; filtering can mutate or recreate collections depending on framework behavior. For batch writes, **silently filtering out** rejected items is not always appropriate: many APIs must reject **the entire request** if any item is unauthorized so callers are not misled into thinking the whole batch succeeded.

## 10. Moving complex policies into beans with clear boolean results

When nullable data arrives from multiple systems, long expressions like `#request?.user?.membership?.tenant?.id` become hard to control. A policy bean separates **structural checks**, **trusted sources**, **business permissions**, and **error handling**.

Spring Security example with a policy bean:

~~~java
import java.util.UUID;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final TrustedTenantResolver tenantResolver;
    private final DocumentPermissionService permissionService;

    public DocumentPolicy(
            TrustedTenantResolver tenantResolver,
            DocumentPermissionService permissionService) {
        this.tenantResolver = tenantResolver;
        this.permissionService = permissionService;
    }

    public boolean canWrite(
            Authentication authentication, UpdateDocumentRequest request) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken
                || request == null
                || request.documentId() == null
                || request.documentId() <= 0) {
            return false;
        }

        UUID tenantId = tenantResolver.resolveVerifiedTenant(authentication);
        if (tenantId == null) {
            return false;
        }

        Boolean granted = permissionService.canWrite(
                tenantId, authentication.getName(), request.documentId());
        return Boolean.TRUE.equals(granted);
    }
}
~~~

This is integration code for a Spring project, assuming `TrustedTenantResolver`, `DocumentPermissionService`, and `UpdateDocumentRequest` are defined by the app. If the request is a Java record, `request.documentId()` is valid; for a POJO, switch to the corresponding accessor.

Mandatory contract:

- `TrustedTenantResolver` reads the tenant only from a verified identity/token or trusted server mapping; missing tenant returns null or raises an error per contract.
- `DocumentPermissionService.canWrite(...)` must check permission for **the exact document in the exact tenant**, not just a general user role.
- `Boolean.TRUE.equals(granted)` grants access only when the result is `Boolean.TRUE`; `false` and `null` do not grant access.
- On I/O errors, timeouts, or permission service disconnects, never catch all exceptions and return `true`. Return a denial or surface an appropriate system error, but the write must never proceed without affirmative evidence.
- Prevent internal calls from bypassing the proxy when relying on `@PreAuthorize`: test through a Spring-managed bean or enforce the policy as an explicit guard on non-proxied paths.

At endpoints, controller/service code should validate request schemas and separate missing required input errors from permission denials. Policies must never "guess" user or tenant from incomplete data.

## 11. Three-state decisions at the domain layer

With external permission services, a boolean is sometimes insufficient to explain an outcome. The domain layer can model states:

- **ALLOW:** sufficient evidence present; policy grants access.
- **DENY:** clear evidence violates policy or required fields are missing.
- **INDETERMINATE:** no decision possible because a dependency failed or did not respond.

The enforcement layer must still map this to "grant access?" using a single rule: **only ALLOW proceeds**. Record `INDETERMINATE` reasons in safe logs/metrics (without tokens or sensitive data), and consider returning 503/5xx for permission-service outages instead of falsely claiming the user is forbidden. Regardless, technical errors must never become an authorization **bypass**.

**Standalone** Java 17 example, needing no Spring, to illustrate:

File `NullPolicyDemo.java`:

~~~java
public class NullPolicyDemo {
    enum Decision { ALLOW, DENY, INDETERMINATE }

    record Input(
            String actor,
            String tenant,
            String owner,
            Boolean permissionVerified) {
    }

    static Decision decide(Input input) {
        if (input == null
                || input.actor() == null || input.actor().isBlank()
                || input.tenant() == null || input.tenant().isBlank()
                || input.owner() == null || input.owner().isBlank()) {
            return Decision.DENY;
        }

        if (!input.actor().equals(input.owner())) {
            return Decision.DENY;
        }

        if (input.permissionVerified() == null) {
            return Decision.INDETERMINATE;
        }
        return input.permissionVerified()
                ? Decision.ALLOW
                : Decision.DENY;
    }

    static void printDecision(String label, Input input) {
        Decision decision = decide(input);
        System.out.println(label + ": " + decision
                + ", grant=" + (decision == Decision.ALLOW));
    }

    public static void main(String[] args) {
        printDecision("complete",
                new Input("an", "tenant-1", "an", true));
        printDecision("other-owner",
                new Input("an", "tenant-1", "binh", true));
        printDecision("missing-owner",
                new Input("an", "tenant-1", null, true));
        printDecision("unknown-permission",
                new Input("an", "tenant-1", "an", null));
        printDecision("no-input", null);
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac NullPolicyDemo.java
java NullPolicyDemo
~~~

Stdout:

~~~text
complete: ALLOW, grant=true
other-owner: DENY, grant=false
missing-owner: DENY, grant=false
unknown-permission: INDETERMINATE, grant=false
no-input: DENY, grant=false
~~~

The example intentionally simplifies the policy to owner + non-empty tenant + permission signal. Real systems must also verify the actor, user–tenant membership, document–tenant relation, permission source, and freshness. The core point is that **only the single ALLOW case maps to `grant=true`**.

## 12. Decision table: missing data across policy types

| Input data | Expected when authorizing | Interpretation |
|---|---|---|
| Unauthenticated user | Do not grant; web flows usually require login | Never treat `principal != null` as sufficient sign-in proof |
| Anonymous token with principal `anonymousUser` | Do not grant private access | Use proper authentication predicates |
| Missing required tenant claim | Do not grant | Never use client-supplied tenant as a default |
| Tenant claim present, yet signature/issuer/audience invalid | Do not grant | Token is untrusted even though the field exists |
| Resource ID argument null or invalid | Do not grant; may return input error | Validation and authorization are separate steps |
| Null owner in a private record | Do not grant under owner-only policy | Never treat null owner as public |
| ACL returns false | Do not grant | Explicit DENY decision |
| ACL returns null or cannot answer | Do not grant; handle error/INDETERMINATE | Never assume "probably allowed" |
| Permission service timeout | Do not execute operation | Use appropriate retries/circuit breakers, never fail-open |
| Validly governed `isPublic=true` flag | May grant per public policy | Public access must be explicit, never inferred from missing fields |
| Admin with proper authority | Grant only within defined scope | An admin in one tenant is not automatically admin everywhere |
| Null data in display-only field | Safe default acceptable | UI null differs from authorization-decision null |

For HTTP APIs, a common mapping is: malformed/missing structural request → 400; unauthenticated → 401; authenticated without permission → 403; resource not found → 404; permission service failure → appropriate 5xx. Exact status codes depend on API design and resource-enumeration policies. Do not assume every SpEL evaluation failure automatically maps to a single HTTP status; configure and test exception handling across your real stack.

## 13. Logic mistakes that turn missing data into permissions

### Wrong: OR condition with a "missing" branch

~~~spel
#documentId == null or hasAuthority('document:read')
~~~

If ID is null, the left side is true, so the entire expression grants access. **Fix:** use `#documentId != null and ...`.

### Wrong: defaulting the tenant when missing

~~~spel
#tenantId ?: 'public'
~~~

If this value directly sets read scope, a missing tenant can expose public or cross-tenant data. **Fix:** never build authorization scope defaults from unverified data.

### Wrong: checking principal != null to conclude signed in

~~~spel
principal != null
~~~

Anonymous authentication can still have a principal. **Fix:** use `isAuthenticated()` or verify against trusted domain authentication.

### Wrong: safe navigation only on the first segment

~~~spel
#request?.owner.id == authentication.name
~~~

If `request` is null, `.id` can still error. **Fix:** `#request?.owner?.id != null and ...` or full explicit guards.

### Wrong: always interpreting `Map.get(...) == null` as key absent

A present key with a null value produces the same `get` result as a missing key. **Fix:** use `containsKey` if distinguishing them matters, then validate value/trust.

### Wrong: using null to represent an "allow" decision

~~~java
return permissionService.check(id) == null;
~~~

If `null` means unknown, this grants access whenever no result is returned. **Fix:** grant only when the result is `Boolean.TRUE` or enum `ALLOW`.

### Wrong: catching all policy errors and letting through

~~~java
try {
    return policyService.canRead(resourceId);
} catch (Exception ignored) {
    return true;
}
~~~

This is **fail-open** on network outages, bugs, or missing data. **Fix:** deny or convert to a controlled operational error; never execute sensitive operations.

### Wrong: using null-safe operators to mask model bugs

`#request?.owner?.id` prevents a `NullPointerException`, yet does not prove owner or tenant are valid. If owner is business-mandatory, validate structure and surface upstream errors rather than silently falling back.

## 14. Testing with null and missing data

Build a test matrix over **input values** and **expected decisions**, rather than testing only a single happy path:

| Scenario | Expected security decision |
|---|---|
| Authenticated user, valid ID, matching tenant + owner + ACL | ALLOW |
| Null ID | DENY / input error |
| Zero or negative ID when positive required | DENY / input error |
| Null owner | DENY for owner-only policies |
| Tenant claim absent | DENY |
| Tenant claim present-null or empty | DENY |
| Anonymous non-null principal | DENY for private resources |
| Principal of unexpected type | DENY / clear config error |
| Policy bean returns `Boolean.FALSE` | DENY |
| Policy bean returns `null` | Do not grant |
| Dependency timeout | Do not grant; handle outage |
| SpEL binds wrong variable/parameter | Do not execute operation; flag config error |
| Resource deleted or moved to another tenant | Do not grant for old ID |
| One object in `@PostFilter` is null | Do not retain null element per policy |
| User in tenant A requests tenant B resource | DENY even if owner name matches |

In Spring Security, test annotations through real beans/proxies using security test contexts with different users and roles. Combine unit tests for nullable policy beans with integration tests to catch missing claims or tenant mismatches in the database.

Example annotation test skeleton (illustrative code inside a project with Spring Security Test, not a standalone Java program):

~~~java
@WithMockUser(username = "an", authorities = "document:read")
@Test
void shouldRejectMissingId() {
    assertThatThrownBy(() -> documentCommandService.read(null))
            .isInstanceOf(AccessDeniedException.class);
}
~~~

Imports and test fixtures depend on your project (JUnit 5, AssertJ, Spring Security Test, and a managed service); `@EnableMethodSecurity` must be configured. Because `read(null)` might be stopped earlier by request validation on another HTTP path, this test specifically targets the **method security interceptor** on the bean and makes no claim about HTTP status codes.

Also add tests for anonymous principals, missing claims, SpEL variable typos, null return values, `Optional.empty()` (matching your version's behavior), permission-service errors, and requests mutating state right between the permission check and execution.

## 15. Practical checklist

Before shipping an authorization expression to production:

1. List every nullable/missing source: method arguments, claims, principals, record fields, bean return values, remote permissions.
2. Classify each field as mandatory or optional. **Missing mandatory fields must deny access**.
3. Use `and` + properly ordered guards, or `?.` consistently across every level requiring protection.
4. Avoid `?:` defaults for owner, tenant, role, permission, or public flags without an explicit policy.
5. Verify principal and scope via a trusted security context; anonymous callers are not authenticated users merely because `principal` is non-null.
6. With maps/JWTs, distinguish missing keys, present-null values, and valid values as needed, and verify claim origin.
7. When expressions need many conditions, move logic into a policy bean returning a clear boolean or domain decision type where **only ALLOW grants**.
8. Never treat SpEL evaluation errors or permission service failures as "allow."
9. Check Spring Framework/Security versions, especially safe navigation support for `Optional`.
10. Test complete data, null, absent, wrong types, anonymous, timeouts, missing variables, self-invocation, and tenant boundaries.
11. Separate input validation errors, authorization denials, missing resources, and operational failures in telemetry/HTTP without leaking sensitive details.
12. Apply the same principles across queries, method security, detail APIs, batches, and non-HTTP paths.

A safe authorization policy requires **positive evidence to grant access**. `null`, missing data, or indeterminate outcomes are signals to handle explicitly, never shortcuts past a check.

## References

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): SpEL in `@PreAuthorize`/`@PostAuthorize`, expression root, `@P`, method parameters, and proxies.
- [Spring Framework 6.2 – Safe Navigation](https://docs.spring.io/spring-framework/reference/6.2/core/expressions/language-ref/operator-safe-navigation.html): using `?.` and compound expression chains.
- [Spring Framework 6.2 – Elvis Operator](https://docs.spring.io/spring/reference/6.2/core/expressions/language-ref/operator-elvis.html): `?:` with null and empty strings.
- [Spring Framework – SpEL Operators](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html): operators and comparisons with null.
