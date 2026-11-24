# Managing Exceptions, Missing Data, and Safe Default Decisions

## 1. Goal

A custom Spring Security `AuthorizationManager<T>` does more than decide which authorities a user holds. It must also respond when permission data is missing, when a principal is unauthenticated, when an ACL service returns `null`, when a query fails, or when multiple managers participate in one decision.

**Core principle:** allow a sensitive operation only when there is an **explicit ALLOW decision backed by trusted data and identity**. Missing evidence or evaluation errors must never default to allow.

Yet "fail closed" does not mean catching every exception and returning HTTP 403. An account **denied by policy** and an authorization system **currently unavailable** are both blocked from performing the action, yet they must be distinguished in error messages, logging, retries, auditing, and operations.

This lesson focuses on designing the contract of a custom `AuthorizationManager`: ALLOW/DENY/ABSTAIN outcomes, exceptions, missing data, defaults when composing managers, version-specific Spring Security examples, and tests proving no fail-open branches exist.

## 2. Distinguishing ALLOW, DENY, ABSTAIN, and ERROR

| State | Meaning | Representation in Spring Security | Perform sensitive action? |
|---|---|---|---|
| **ALLOW** | Policy has sufficient data and permits | `new AuthorizationDecision(true)` | Yes, if other mandatory conditions also pass |
| **DENY** | Policy has grounds to deny or a mandatory condition is missing | `new AuthorizationDecision(false)` | No |
| **ABSTAIN** | Manager **makes no decision**, potentially deferring to another component | `null` | Never infer ALLOW or DENY directly; check caller/composition |
| **ERROR** | Check did not complete due to infrastructure or programming failure | Categorized exception | No; handle failure in a controlled manner |

In an `AuthorizationManager`, `null` **is not equivalent** to `AuthorizationDecision(false)`. It means "abstain." If the manager is the sole guard on a mandatorily protected use case, returning null when tenant is missing, owner mismatches, or a backend times out is usually a dangerous choice.

Examples of the three alternative outcomes:

~~~java
return new AuthorizationDecision(true);   // ALLOW
return new AuthorizationDecision(false);  // DENY
return null;                              // ABSTAIN, use intentionally only
~~~

These three lines illustrate three distinct branches, **not** a Java method written sequentially like this.

**Infrastructure failures are not business abstentions.** A policy engine timeout does not mean the manager "does not care" about this resource. Execution must halt; the system may throw an exception to signal failure or fall back to a denial decision per an agreed fallback policy.

## 3. Version Contract Before Writing Code

The Java signature of `AuthorizationManager<T>` varies across Spring Security releases. Always check the version of `spring-security-core` **on the actual module's compile classpath and runtime classpath**, rather than guessing from a Spring Boot starter name.

| Version | Abstract method to implement | Additional methods | Result |
|---|---|---|---|
| Spring Security 6.3 | `check(Supplier<Authentication>, T)` | default `verify(...)` | `AuthorizationDecision` or `null` |
| Spring Security 6.4–6.5 | `check(Supplier<Authentication>, T)` **still abstract despite deprecation** | default `authorize(...)`, default `verify(...)` | `authorize` uses `AuthorizationResult` |
| Spring Security 7.x | abstract `authorize(Supplier<? extends Authentication>, T)` | default `verify(...)`; `check` removed from interface | `AuthorizationResult` or `null` |

The 7.x Javadoc may show `Supplier<? extends @Nullable Authentication>` due to nullability annotations. When implementing in Java, the `? extends` wildcard must match the API; in 6.5, the `Supplier<Authentication>` signature differs. `AuthorizationDecision` implements `AuthorizationResult`, so `new AuthorizationDecision(granted)` can be returned from 7.x methods.

**Never delete `@Override` to hide version errors.** If the compiler reports "does not override," read the Javadoc for the exact version being built. A Java method not called by Spring's interceptor can leave real enforcement broken.

See the official Javadocs:
- [AuthorizationManager 6.3](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/AuthorizationManager.html).
- [AuthorizationManager 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html).
- [AuthorizationManager 7.x](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html).

## 4. Missing Data Matrix and Safe Decisions

| Case | Cause | Proper behavior when permission is mandatory |
|---|---|---|
| `Authentication` is null | No identity yet or call path did not propagate context | Do not grant; require authentication or flag call-path error |
| `AnonymousAuthenticationToken` | Authentication object exists yet is anonymous | Do not grant private resource access |
| Missing authority | Authenticated actor lacks operation permission | DENY |
| Tenant claim null/absent/empty | Token lacks required scope | DENY; never substitute tenant from a query parameter |
| Resource ID null, negative, or 0 when positive ID required | Invalid request | DENY or input error before reading |
| Resource not in actor's tenant | Data scope mismatch | DENY or NOT_FOUND per anti-enumeration policy |
| Owner/ACL on record is null | Missing object-level permission evidence | Do not grant; distinguish corrupt data from truly public resources |
| Permission service returns false | Valid policy denial | DENY |
| Permission service returns null | No meaningful decision | Do not grant; DENY or infrastructure error per contract |
| Permission service timeout/503 | Dependency outage | Do not grant; report controlled error / record metric |
| Backend result fails schema validation | Decision cannot be trusted | Do not grant; report error |
| `ClassCastException`, `NullPointerException` in policy | Bug or type mismatch | Do not grant; fix the bug, never swallow and allow |
| No rule matches the object | Incomplete policy configuration | Safe default is DENY |
| Manager designed only for a different object group | Intentionally uninvolved | May ABSTAIN if composition is guarded and tested |

**Never infer "public" when owner/tenant/ACL is null.** Public resources require an explicit, properly governed public attribute and policy.

**Never treat `authentication != null` or `isAuthenticated()` alone as confirming a real user.** Some anonymous tokens can carry an authenticated state. For private permissions, distinguish anonymous callers using trusted mechanisms; use `AuthenticatedAuthorizationManager` or `AuthenticationTrustResolver` as required.

## 5. Trusted Data Boundaries

Different pieces of data carry different levels of trust:

~~~text
Client-asserted HTTP/JWT/message metadata
        |
        v
Source verification: signature, issuer, audience, session, workload identity
        |
        v
Trusted actor + verified tenant + authority
        |
        v
Resource in storage: query by tenant + ID, check owner/ACL
        |
        v
AuthorizationManager --> ALLOW / DENY / check error
~~~

When a token lacks a tenant, never fall back to `request.getParameter("tenant")` as the verified tenant. In multi-tenant systems, ID-based lookups must include tenant scoping at the repository or an equivalently protective policy.

Distinguish two questions:
1. Does the actor have an action permission such as `document:read`?
2. Is the actor allowed to view **this specific document inside the active tenant**?

A general role or authority cannot answer the second question alone. If checking ACLs from an external service, the result must bind to the right actor, tenant, resource, operation, and policy version.

Sentinel values like `"public"`, `"default"`, or `"guest"` must never be substituted automatically when a mandatory claim is missing. Those may be valid values in another domain, yet never substitute for authorization evidence.

## 6. Boolean.TRUE.equals: Useful, Yet Never Mask Outages

Suppose a permission gateway returns `Boolean`:

~~~java
Boolean granted = permissionGateway.canRead(actorId, documentId);
return new AuthorizationDecision(Boolean.TRUE.equals(granted));
~~~

Advantage: `Boolean.TRUE.equals(granted)` returns true only when the backend genuinely returned `Boolean.TRUE`; both false and null refuse access. It avoids `NullPointerException` from unboxing. This fits if the gateway contract defines null as **not granted**.

If the gateway uses null to mean **unable to decide**, preserve that meaning:

~~~java
Boolean granted = permissionGateway.canRead(actorId, documentId);
if (granted == null) {
    throw new PermissionLookupUnavailableException(
            "Permission backend returned no decision");
}
return new AuthorizationDecision(granted);
~~~

This is an **application integration snippet**: `permissionGateway` and the exception are application-defined. Crucially, upper layers must not handle that exception by letting the operation run.

Dangerous:

~~~java
Boolean granted = permissionGateway.canRead(actorId, documentId);
return new AuthorizationDecision(
        granted == null || granted.booleanValue());
~~~

When the backend returns null, that expression grants access. Likewise, `catch (Exception ex) { return new AuthorizationDecision(true); }` is **fail-open**, even if written under the excuse of "improving availability."

No fallback can fabricate authorization proof when the backend cannot supply a result. If an authorization cache is genuinely used during backend outages, it must be explicitly designed around validity, actor, tenant, resource, expiry/revocation, and stale-decision risk; never "cache ALLOW forever."

## 7. Spring Security 7.x Example: A Safe-Denying Manager

The following example uses `AuthorizationManager<DocumentReadManager.Access>` and an explicit contract for missing data. It targets **projects already on Spring Security 7.x** and compiles once the appropriate dependencies are declared. Single file `DocumentReadManager.java`:

~~~java
import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;

public final class DocumentReadManager
        implements AuthorizationManager<DocumentReadManager.Access> {

    public record Access(long documentId, String requestedTenant) { }

    public interface TenantResolver {
        String verifiedTenant(Authentication authentication);
    }

    public interface PermissionGateway {
        Boolean canRead(String tenant, String actorName, long documentId);
    }

    public static final class PermissionUnavailableException
            extends RuntimeException {
        public PermissionUnavailableException(String message) {
            super(message);
        }
    }

    private final TenantResolver tenantResolver;
    private final PermissionGateway gateway;

    public DocumentReadManager(TenantResolver tenantResolver,
                               PermissionGateway gateway) {
        this.tenantResolver = tenantResolver;
        this.gateway = gateway;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<? extends Authentication> supplier, Access access) {

        if (access == null || access.documentId() <= 0
                || access.requestedTenant() == null
                || access.requestedTenant().isBlank()) {
            return new AuthorizationDecision(false);
        }

        Authentication actor = supplier.get();
        if (actor == null || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        boolean authorizedForAction = actor.getAuthorities().stream()
                .anyMatch(a -> "document:read".equals(a.getAuthority()));
        if (!authorizedForAction) {
            return new AuthorizationDecision(false);
        }

        String trustedTenant = tenantResolver.verifiedTenant(actor);
        if (trustedTenant == null
                || !trustedTenant.equals(access.requestedTenant())) {
            return new AuthorizationDecision(false);
        }

        Boolean result = gateway.canRead(
                trustedTenant, actor.getName(), access.documentId());

        if (result == null) {
            throw new PermissionUnavailableException(
                    "Authorization backend did not provide a decision");
        }
        return new AuthorizationDecision(result);
    }
}
~~~

**Conditions for proper use:**

- `TenantResolver` must extract the tenant from verified identity, never trusting `requestedTenant` as authoritative. `Access` is only the requested context to compare against; if the API request specifies a different tenant, deny.
- `PermissionGateway.canRead` must verify the exact document, tenant, owner/ACL, and status. Return false on policy denial, null when the contract indicates undecided.
- The gateway may throw specific timeout exceptions. Never catch and turn them into ALLOW. When no valid result arrives, the operation must not proceed.
- `Authentication.getAuthorities()` and `actor.getName()` must align with the active authentication mechanism.
- This is a **manager for the `Access` context type**, not an HTTP `RequestAuthorizationContext` manager. It only runs when wired into the corresponding boundary or invoked via proper enforcement. Creating a bean without registering an interceptor **does not automatically protect APIs**.
- Returning DENY for missing ID/scope fields differs from handling permission backend outages. One is policy/validation; the other is an operational error requiring monitoring.

For Spring Security **6.3 or 6.4–6.5**, do not copy the 7.x signature verbatim. When directly implementing `AuthorizationManager<T>` on 6.x, the mandatory method is:

~~~java
@Override
public AuthorizationDecision check(
        Supplier<Authentication> authentication,
        Access access) {
    return evaluateWithSharedPolicy(authentication.get(), access);
}
~~~

This is a **signature snippet**, not a standalone class: helper `evaluateWithSharedPolicy` has a contract returning `AuthorizationDecision`. On 6.4–6.5, `authorize(...)` is default while `check(...)` remains abstract despite deprecation. On 7.x, `check` is removed from the interface and `authorize` is abstract. Never let 6.x and 7.x adapters diverge in decision policy.

## 8. Which Exceptions Are DENY vs. Infrastructure Errors?

A custom manager may interact with authentication, repositories, ACL services, or OPA. Classification:

**Policy denial**: actor lacks authority, wrong tenant, missing ID, ACL returns false, resource state disallows reading. Return a negative decision. When executed through the framework, interceptors can raise `AccessDeniedException` or the version's corresponding subtype.

**Authentication error**: invalid token, missing credentials, or invalid session. This belongs to the authentication pipeline; typically it triggers a challenge/login via `AuthenticationEntryPoint`, rather than a custom manager inventing roles or tenants.

**Dependency error**: permission database/service timed out, returned malformed responses, policy server unavailable. Do not grant; depending on contract, throw a clearly typed infrastructure exception or map to DENY with metrics. Avoid catching and ignoring.

**Code/config error**: `ClassCastException`, missing bean, wrong generic context, `NullPointerException` from dereferencing, method security not enabled. Treat these as bugs to fix, never turning them into ALLOW decisions.

### Two Fail-Closed Strategies Have Trade-offs

| Strategy | What the client sees | Pros | Trade-offs |
|---|---|---|---|
| Return `AuthorizationDecision(false)` on backend error | Typically denied/403 after HTTP mapping | Blocks operation, simple enforcement | Masks outages if metrics are missing; users mistake outages for missing permissions |
| Throw a controlled infrastructure exception | 5xx/503 when properly mapped by adapter | Distinguishes operational incidents from denied permissions | Requires exception mapping, monitoring, and ensuring no side effects |

No single choice fits every system. Yet **both must block side effects** and never fall back to permit. Decide upfront in design rather than letting any individual developer catch and improvise.

Anti-pattern example:

~~~java
try {
    return new AuthorizationDecision(remotePolicy.canWrite(actor, object));
} catch (Exception exception) {
    return new AuthorizationDecision(true);
}
~~~

Conversely, an error-propagating pattern (integration snippet):

~~~java
try {
    Boolean grant = remotePolicy.canWrite(actor, object);
    if (grant == null) {
        throw new PermissionUnavailableException("Missing decision");
    }
    return new AuthorizationDecision(grant);
} catch (PermissionBackendTimeoutException exception) {
    throw new PermissionUnavailableException("Backend unavailable");
}
~~~

In a real application, custom exceptions should accept a `cause` constructor to preserve root causes; never leak tokens/ACLs to clients or logs. Never broadly catch `RuntimeException` and swallow programming bugs arbitrarily.

## 9. verify Is Not a "null = deny" Policy

By default, `AuthorizationManager.verify(...)` invokes the manager and throws `AccessDeniedException` on a **negative decision**. With a `null` result from the manager, the framework treats it as **abstain** and does not necessarily throw like DENY.

Easily misunderstood snippet:

~~~java
AuthorizationManager<Object> abstain = (auth, object) -> null;
abstain.verify(() -> authenticatedUser, new Object());
~~~

This is a Spring Security 7.x integration snippet with an existing `authenticatedUser` fixture. It demonstrates why `verify` must not be used as a forced "null → 403" guard on mandatory use cases.

If calling a manager manually and requiring an explicit positive decision:

~~~java
AuthorizationResult result =
        manager.authorize(() -> authenticatedUser, access);
if (result == null || !result.isGranted()) {
    throw new AccessDeniedException("Authorization required");
}
// Only after this point may the sensitive action run.
~~~

The snippet above is a 7.x fragment requiring the right variables and imports. However, in Spring applications it is generally better to configure **interceptors/HTTP DSL** so the framework enforces rules rather than scattering manual manager calls throughout business code.

**Never catch `AccessDeniedException` and continue mutating.** The exception is a stop signal; if caught for logging, halt/rethrow or map to another failure without proceeding.

## 10. Composition: allOf and anyOf Can Surprise You

Spring Security provides `AuthorizationManagers.allOf(...)` and `anyOf(...)` to compose managers. If a sub-policy returns `null`, the composite manager can pass it instead of treating null as DENY. Specifically, Javadoc documents that `allOf(managers...)` grants when every manager grants **or abstains**, and an empty manager list is also treated as granted.

Thus, if a tenant manager, owner manager, and authority manager all return null when data is missing, a configuration without a safe all-abstain default can void protection.

Overloads exist to explicitly specify the default when all delegates abstain:

~~~java
AuthorizationManager<RequestAuthorizationContext> combined =
        AuthorizationManagers.allOf(
                new AuthorizationDecision(false),
                tenantManager,
                authorityManager,
                resourceManager);
~~~

This is an integration snippet; all managers must share the same generic context and be initialized. It does not turn a weak policy into a strong one: a mandatory manager should still return **DENY** when its condition fails. The overload with `AuthorizationDecision(false)` sets **all-abstain** to DENY, yet you still must test mixed grant/deny/abstain combinations. Verify your exact version before applying the API.

With `anyOf`, a grant from another branch can suffice to open access even when the tenant rule fails, depending on configuration semantics. Never configure "tenant OR authority" when the true intent is "tenant AND (owner OR shared) AND authority."

**Rule for mandatory policies:** missing tenant → DENY; missing object permission → DENY; no backend result → ERROR or deliberate DENY; use ABSTAIN only when managers have explicitly partitioned responsibilities.

## 11. ExceptionTranslationFilter and HTTP Status Codes

`AuthorizationManager` decides permissions; it does not directly choose HTTP status codes. In Spring Security Servlet, `ExceptionTranslationFilter` translates certain security exceptions in the filter chain into responses via `AuthenticationEntryPoint` and `AccessDeniedHandler`.

| Situation | Typical code/flow | What to watch out for |
|---|---|---|
| Unauthenticated, credentials needed | 401/challenge or login redirect | Depends on the application's authentication mechanism |
| Authenticated yet insufficient permissions | 403 | HTTP adapter determines response body |
| Resource not found or existence hidden | 404 per API policy | Do not reveal IDs existing in other tenants |
| Authorization backend failure | 5xx/503 when propagating infrastructure exception | Do not permit action; record metrics |
| Request missing required field | 400/422 depending on API | Validation does not replace authorization |

`ExceptionTranslationFilter` does not automatically turn **every** runtime exception into 403; it primarily handles `AuthenticationException` and `AccessDeniedException` caught within the filter chain. For MVC exception handlers, servlet error dispatches, async tasks, or message consumers, verify the actual exception path of your running stack.

For permission backend failures, avoid throwing `AuthenticationException` as though the user entered a wrong password. That scenario needs operational visibility into dependency unavailability; halt the action without conflating it with authentication failure.

If using `@ControllerAdvice` to return JSON, never write a catch-all `Exception` handler returning `200 OK` with a "warning" body when a write operation was denied. Preserve statuses, transactions, and auditing without exposing JWTs, ACLs, internal responses, or stack traces.

## 12. Exceptions and Transactions: Block Before Side Effects

For write operations, place authorization **before** mutations. Never rely solely on `@PostAuthorize` to catch missing permissions after a method has already produced side effects.

Ideal flow:

~~~text
Verified actor/scope
  -> manager checks authority
  -> read resource within trusted tenant
  -> object-level policy / ACL
  -> only on ALLOW: mutate / persist / publish event
  -> commit transaction properly
~~~

When the permission backend fails, halt before writing. If an exception happens mid-transaction, rollback behavior depends on exception type, advice order, and transaction settings; in Spring, runtime exceptions escaping the transaction interceptor normally trigger rollback by default. If code **catches and swallows** the exception, an outer transaction can still commit earlier changes.

For message consumers/batches, distinguish all-or-nothing from partial success; every item must be checked explicitly, and retries must never open bypasses. Also ensure idempotency and verify permissions at **execution time**, not only when the message was published.

## 13. Standalone Java 17 Demo: Execute Only on ALLOW

Runnable on JDK 17+ without Spring. The goal is illustrating **DENY on missing data** and **UNAVAILABLE when the backend has not decided**, allowing execution only on ALLOW.

Create `SafeDecisionDemo.java`:

~~~java
public class SafeDecisionDemo {
    enum Decision { ALLOW, DENY, UNAVAILABLE }

    record Access(String actor, String verifiedTenant,
                  String resourceTenant, long documentId) { }

    interface PermissionLookup {
        Boolean canRead(Access access);
    }

    static final class BackendUnavailable extends RuntimeException { }

    static Decision evaluate(Access access, PermissionLookup lookup) {
        if (access == null
                || access.actor() == null || access.actor().isBlank()
                || access.verifiedTenant() == null
                || access.verifiedTenant().isBlank()
                || access.resourceTenant() == null
                || access.resourceTenant().isBlank()
                || access.documentId() <= 0
                || !access.verifiedTenant().equals(access.resourceTenant())) {
            return Decision.DENY;
        }

        try {
            Boolean permission = lookup.canRead(access);
            if (permission == null) {
                return Decision.UNAVAILABLE;
            }
            return permission ? Decision.ALLOW : Decision.DENY;
        } catch (BackendUnavailable exception) {
            return Decision.UNAVAILABLE;
        }
    }

    static void show(String label, Access access, PermissionLookup lookup) {
        Decision result = evaluate(access, lookup);
        System.out.println(label + ": " + result
                + ", execute=" + (result == Decision.ALLOW));
    }

    public static void main(String[] args) {
        Access ok = new Access("an", "north", "north", 7L);
        Access otherTenant = new Access("an", "north", "south", 7L);

        show("allowed", ok, a -> true);
        show("denied", ok, a -> false);
        show("missing-tenant",
                new Access("an", null, "north", 7L), a -> true);
        show("wrong-tenant", otherTenant, a -> true);
        show("no-decision", ok, a -> null);
        show("outage", ok, a -> { throw new BackendUnavailable(); });
    }
}
~~~

Run:

~~~bash
javac SafeDecisionDemo.java
java SafeDecisionDemo
~~~

Exact stdout:

~~~text
allowed: ALLOW, execute=true
denied: DENY, execute=false
missing-tenant: DENY, execute=false
wrong-tenant: DENY, execute=false
no-decision: UNAVAILABLE, execute=false
outage: UNAVAILABLE, execute=false
~~~

Analysis: missing or mismatched tenant is blocked before calling the backend. The backend returning null or throwing a recognized exception never permits the action. Only `ALLOW` produces `execute=true`. The demo assumes `verifiedTenant` comes from a trusted source; plain Java does not prove identity itself. In a real application, never catch all `RuntimeException`s and treat them as ordinary business outcomes; catch only dependency exceptions with clear contracts or let errors propagate to the error-handling layer.

## 14. Testing to Prove Fail-Closed Behavior

Minimum test table:

| Input / condition | Expected |
|---|---|
| Real principal, valid authority, matching tenant, ACL true | ALLOW |
| Missing authority | DENY |
| Non-null anonymous principal | Do not grant |
| Supplier returns null | Do not grant |
| Missing, null, or blank tenant claim | Do not grant |
| Invalid or out-of-scope resource ID | Do not grant |
| Actor in tenant A, resource in tenant B | DENY even if mock backend returns true |
| ACL false | DENY |
| ACL null | Do not grant; handle per error or deny contract |
| ACL timeout/5xx | Do not grant, emit operational signal |
| Manager returns null | ABSTAIN; **do not** assume verify will deny |
| All delegates abstain | Default DENY if resource requires protection |
| One delegate DENY, another ALLOW | Follows intended AND/OR; test against unintended grants |
| Exception caught in service | No unintended mutation or commit outside contract |
| Spring Security version changed | Right signature and interceptor are invoked |

A 7.x integration unit test snippet (fixtures and AssertJ supplied by the project):

~~~java
AuthorizationResult result =
        manager.authorize(() -> authenticatedUser, accessContext);

assertThat(result).isNotNull();
assertThat(result.isGranted()).isFalse();
~~~

For 6.3/6.5, use `check(...)` per contract. Do not only unit-test the manager directly: if it is not wired into the HTTP DSL or an interceptor, the policy may never run at all.

### Mandatory End-to-End Tests

1. Send HTTP requests through the real `SecurityFilterChain`; test unmatched routes and `denyAll()` fallback.
2. Call Spring methods through real bean proxies; never rely on annotations on private methods or self-invocation.
3. For unauthenticated requests, verify 401 challenge or corresponding login behavior.
4. For authenticated requests lacking permission, confirm denial and zero database changes.
5. Simulate a permission backend timeout; verify no updates or side effects are published even if HTTP maps the exception to 503.
6. Test the same user against another tenant, another owner, and a record whose ACL was revoked.
7. Test `verify` with negative and null; test `AuthorizationManagers.allOf/anyOf` with grant/deny/abstain.
8. Test message consumers/scheduled jobs too if the same use case is invoked outside HTTP.
9. After upgrading Spring Security major versions, rebuild extension classes and run integration tests to catch `NoSuchMethodError`/`AbstractMethodError`.

## 15. Logging, Metrics, and Auditing: Observable Without Leaking

Every critical decision should carry traceable metadata:

- Operation (e.g., `document:read`), resource type, and ID per safe logging policy.
- **Verified** actor and tenant; never log raw JWTs or credentials.
- Outcome ALLOW/DENY/ABSTAIN/ERROR, policy version, and correlation ID.
- For backend failures: error category (timeout, unavailable, invalid response), duration, and bounded retry count.
- For denials: log a safe general reason; never expose detailed ACLs or other tenants' resource info in responses.

Never log full principal objects, `Authorization` headers, token contents, database secrets, or sensitive stack traces in API bodies. Increment backend-error metrics and alerts so an outage is never hidden behind a wave of 403s.

**Authorization caching** (if any) must be keyed by actor, tenant, resource, action, and active policy. Caching ALLOW with the wrong scope or too long after permission revocation creates privilege-escalation bugs; never use a resource-ID-only cache key in multi-tenant environments.

## 16. Anti-Patterns to Eliminate

**1. Returning null when data is missing.** Null means ABSTAIN, not DENY; composition may grant. **Fix:** for mandatory policies, return a negative decision or an intentionally handled exception.

**2. Using permitAll on timeout.** Fail-open. **Fix:** refuse access and preserve the backend-unavailable signal.

**3. Treating `Boolean null` permission as true.** Breaks three-valued logic. **Fix:** `Boolean.TRUE.equals(permission)` if null means not granted, or throw an error if null means backend indeterminate.

**4. Checking only `authentication != null`.** Anonymous can be non-null. **Fix:** verify real trust/authorities.

**5. Reading missing tenant from a request parameter.** Trusts client-supplied data. **Fix:** use verified tenant only.

**6. Catching `AccessDeniedException` to log and letting the update proceed.** Disables protection. **Fix:** halt and rethrow/handle safely.

**7. Assuming `verify(null)` always throws.** Misunderstands abstain semantics. **Fix:** explicit DENY or fail-closed caller.

**8. Allowing composition when all managers abstain.** Bad default. **Fix:** use default-deny where needed and test it.

**9. Manager bean exists in context without being wired to a matcher/interceptor.** Does not guard actions. **Fix:** integration-test real entry points.

**10. Mixing 6.x and 7.x APIs.** Signature mismatch, compile or linkage exceptions. **Fix:** check versions and use accurate `@Override`.

**11. Turning backend errors into 403 without metrics.** Not fail-open, yet hides operational outages. **Fix:** separate DENY from ERROR with alerts/correlation.

**12. Using `@PostAuthorize` on write operations to patch authorization.** Checking after side effects can be too late. **Fix:** guard before mutations with proper transactions.

## 17. Pre-Merge Design Checklist

- [ ] `AuthorizationManager<T>` contract matches 6.x or 7.x accurately.
- [ ] ALLOW, DENY, ABSTAIN, and infrastructure errors are clearly distinguished.
- [ ] Missing authentication/authority/tenant/resource ID denies access.
- [ ] Identity and tenant come from verified sources.
- [ ] ACL/owner/resource scope is verified against the exact target resource.
- [ ] Backend returning null/timing out never becomes ALLOW.
- [ ] Usage of `verify` does not assume null equals deny.
- [ ] `AuthorizationManagers.allOf/anyOf` defaults have been tested.
- [ ] `AccessDeniedException` is never swallowed before running side effects.
- [ ] HTTP statuses properly reflect unauthorized/forbidden/unavailable per contract.
- [ ] Transactions, retries, caching, auditing, and logging create no bypasses.
- [ ] The manager is genuinely invoked by the HTTP/method/message interceptor.
- [ ] Tests cover anonymous, null, missing, wrong tenant, backend outage, and no side effects.
- [ ] Tokens, credentials, ACLs, and unauthorized sensitive details are never logged.

**Conclusion:** a safe custom `AuthorizationManager` never guesses permissions when data is missing and never opens access when exceptions occur. It returns **explicit DENY** when policy conditions fail, preserves **explicit ERROR** when checks cannot run, uses **ABSTAIN** only under tested composition policies, and blocks side effects until ALLOW is proven.

## References

- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, positive/negative/null decisions, and `verify`.
- [Spring Security 6.5 API – AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `check` and `authorize` in 6.x.
- [Spring Security 7.x API – AuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize` and `verify` signatures.
- [Spring Security API – AuthorizationManagers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagers.html): `allOf`, `anyOf`, abstain defaults.
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler`.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): registering and enforcing method authorization.
