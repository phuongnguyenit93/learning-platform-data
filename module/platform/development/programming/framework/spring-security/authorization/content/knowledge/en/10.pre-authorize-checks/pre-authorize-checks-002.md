# Checking Roles, Authorities, and Authentication State with SpEL in Spring Security

## 1. Objectives and real-world scenario

A business service has multiple permission levels: unauthenticated guests may read public news; logged-in users may view their profile page; users with role REVIEWER may review documents; users with the `report:export` permission may export reports; and money-transfer operations must require full authentication, rejecting sessions restored merely via remember-me.

Spring Security provides `@PreAuthorize` to check **before the method executes** using a **SpEL** (*Spring Expression Language*) expression. The expression can reference roles, authorities, authentication state, method parameters, the principal, or invoke a policy bean.

Examples:

```java
@PreAuthorize("hasRole('REVIEWER')")
public ReviewResult review(String documentId) { /* ... */ }

@PreAuthorize("isAuthenticated() and hasAuthority('report:read')")
public ReportView read(String reportId) { /* ... */ }

@PreAuthorize("isFullyAuthenticated() and hasAuthority('payment:approve')")
public void approvePayment(String paymentId) { /* ... */ }
```

These are **Spring service fragments**: the classes `ReviewResult`, `ReportView`, and implementations depend on the application. The value of `@PreAuthorize` is **a SpEL expression**, not a plain Java boolean expression; Spring Security evaluates it using the method invocation context.

This lesson helps you:

1. Distinguish `hasRole` from `hasAuthority`, the `ROLE_` prefix convention, and the “any” variants.
2. Clearly understand `isAuthenticated()`, `isFullyAuthenticated()`, `isRememberMe()`, `isAnonymous()`, `permitAll`, and `denyAll`.
3. Know how to write expressions with `and`, `or`, `!`, parentheses, and parameter-based conditions.
4. Use `authentication`, `principal`, `#parameter`, and policy beans with reliable semantics.
5. Enable `@EnableMethodSecurity`, manage AOP proxies, and avoid self-invocation.
6. Avoid confusing method authorization with HTTP authorization, CSRF, MFA, or per-resource permissions.
7. Test accounts with roles, with permissions, missing permissions, anonymous, and remember-me.
8. Design clear, auditable rules and avoid over-granting permissions in modern Java/Spring Boot.

**Scope:** Spring Security Servlet/Spring MVC, Java 17+, common Spring Security 6.x/7.x APIs. `@PreAuthorize` is also used in some other environments, but the filter/HTTP examples here belong to Servlet. When applying, cross-check the actual API and version resolved by Maven/Gradle via the BOM.

## 2. Where and when does @PreAuthorize operate?

### 2.1. Method invocation lifecycle

```text
HTTP request or call from another bean
           │
           ▼
Spring-managed service proxy
           │
           ▼
AuthorizationManagerBeforeMethodInterceptor
           │
           ▼
PreAuthorizeAuthorizationManager
           │
           ▼
MethodSecurityExpressionHandler
    ├─ SecurityContext / Authentication
    ├─ GrantedAuthorities / RoleHierarchy (if configured)
    ├─ method parameters (#id, #request, ...)
    ├─ principal, authentication, expression root
    └─ policy bean (@policyBean)
           │
           ▼
SpEL returns authorization decision
    ├─ GRANT ──> invoke method body
    └─ DENY  ──> block method body / access denied
```

Here “before method” actually means **before the body of the advised method**. Method security is enforced by a Spring AOP interceptor when the invocation passes through a proxy or an appropriate weaving mechanism. An annotated method called directly on an object created with `new` or via `this.method()` may **not** be intercepted.

Typically, `@PreAuthorize` is evaluated at the service boundary and can protect the same use case whether called from an HTTP controller, scheduled task, or message consumer — provided every call path goes through the method-security mechanism and has an appropriate identity.

### 2.2. Enabling method security

In modern Spring Security:

```java
package com.example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` enables support for pre/post method annotations such as `@PreAuthorize` by default. Simply adding `spring-boot-starter-security` **does not automatically enable** method-level authorization. For older Spring Security code using `@EnableGlobalMethodSecurity(prePostEnabled = true)`, treat it as a legacy configuration path that should be migrated per version, and do not mix both styles in one project without review.

### 2.3. No annotation does not automatically mean DENY

If a bean has some `@PreAuthorize` methods and some unannotated methods, the method-security framework **does not deny every unannotated method by default**. Organize clear service boundaries, use an HTTP `denyAll()` fallback for undeclared URLs, and test different business call paths. Do not treat one protected method as proof that the entire class is protected.

## 3. Authority: permission strings that AuthorizationManager can check

### 3.1. What is GrantedAuthority?

`Authentication` represents the authenticated principal and holds a collection of `GrantedAuthority`. A user might have:

```text
Authentication:
  principal: linh
  authenticated: true
  authorities:
    - ROLE_USER
    - ROLE_REVIEWER
    - report:read
    - report:export
```

Each common authority can be represented by a `SimpleGrantedAuthority` containing a string. `hasAuthority('report:read')` compares against the authority with that name using an exact string match. Spring Security **does not automatically treat** `report:read` and `REPORT:READ` or `SCOPE_report.read` as identical.

SpEL example:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView view(String reportId) {
    return reportService.loadVisibleReport(reportId);
}
```

This is a fragment; `reportService` and `ReportView` do not exist on their own. In a real project, reading a report also requires a tenant/owner policy, not just the functional `report:read` permission.

### 3.2. hasAuthority is an exact permission match

| Actual authority | `hasAuthority('report:read')` | Why |
| --- | --- | --- |
| `report:read` | True | String matches |
| `report:write` | False | Different action |
| `ROLE_ADMIN` | False without relevant mapping/hierarchy | A role is not automatically a permission |
| `SCOPE_reports.read` | False | Scope name differs from permission |
| `REPORT:READ` | False | Different casing |
| `report:read` + `ROLE_USER` | True | One matching authority is enough |

When `RoleHierarchy` is configured in the expression handler, `hasAuthority` can evaluate reachable authorities instead of only the direct set; thus a case with only `ROLE_ADMIN` can satisfy a permission due to **configured hierarchy edges**. No permission inference exists by default without building the graph and verifying the actual handler.

### 3.3. hasAnyAuthority is OR

```java
@PreAuthorize("hasAnyAuthority('report:read', 'report:manage')")
public ReportView preview(String reportId) { /* ... */ }
```

Meaning: having **either one** of the corresponding authorities is enough. This is not AND.

If the business logic requires both:

```java
@PreAuthorize(
    "hasAuthority('report:read') and hasAuthority('report:export')"
)
public byte[] export(String reportId) { /* ... */ }
```

The AND policy checks both permissions simultaneously. For long expressions, consolidate them into a meaningful permission name or policy bean instead of duplicating permissions in many places.

## 4. Role: hasRole differs from hasAuthority by prefix convention

### 4.1. hasRole('ADMIN') defaults to ROLE_ADMIN

By Spring Security's default convention, role rules use the `ROLE_` prefix. Therefore:

```java
@PreAuthorize("hasRole('ADMIN')")
public void approveConfiguration() { /* ... */ }
```

normally checks for the `GrantedAuthority` `ROLE_ADMIN`, equivalent in meaning to:

```java
@PreAuthorize("hasAuthority('ROLE_ADMIN')")
public void approveConfiguration() { /* ... */ }
```

It does **not** check the bare authority `ADMIN` by default. When encountering “user already has ADMIN but is still denied”, print/log the authority list **sanitized of sensitive information** in a test environment, and compare `ROLE_ADMIN` against `ADMIN` and the authentication provider's mapper.

Prefer writing `hasRole('ADMIN')` instead of `hasRole('ROLE_ADMIN')` to keep the role-prefix contract consistent; some managers/APIs handle or restrict role names that already contain the prefix differently.

### 4.2. hasAnyRole is OR

```java
@PreAuthorize("hasAnyRole('EDITOR', 'ADMIN')")
public void publishDraft(String id) { /* ... */ }
```

It accepts a user with `ROLE_EDITOR` **or** `ROLE_ADMIN`, not requiring both roles simultaneously. If both are needed, write:

```java
@PreAuthorize("hasRole('EDITOR') and hasRole('ADMIN')")
public void highlyRestrictedAction() { /* ... */ }
```

But ask whether the business policy truly requires two job titles at once or should use a **business permission** like `document:publish:restricted`. Requiring two roles simultaneously is usually less flexible than RBAC/permission modeling.

### 4.3. Role names and permission names

| Expression | Typical meaning |
| --- | --- |
| `hasRole('ADMIN')` | Has `ROLE_ADMIN` under the default prefix |
| `hasAuthority('ROLE_ADMIN')` | Exact authority `ROLE_ADMIN` |
| `hasAuthority('admin:manage')` | Exact permission `admin:manage` |
| `hasAnyRole('USER','ADMIN')` | Has one of `ROLE_USER`, `ROLE_ADMIN` |
| `hasAnyAuthority('invoice:read','invoice:manage')` | Has one of the two permissions |
| `hasRole('read')` | Requires role `ROLE_read` by default; **not** `read` |

Do not turn every permission into a role just because the project uses `hasRole`. Roles group users by responsibility; permissions usually describe actions on resources. A user with `ROLE_ADMIN` does not automatically possess `report:export` without an explicit mapping (at authentication time or via `RoleHierarchy`).

### 4.4. The prefix can be customized

A project can change the role prefix using `GrantedAuthorityDefaults`/expression handler configuration or an appropriate factory for its version. In that case, “`hasRole('ADMIN')` requires `ROLE_ADMIN`” only holds under the **default**.

If you are using Spring Security 7, authorization-manager factories help customize the role prefix/hierarchy centrally; in older configurations, expression handlers have different setters. **Always test with a principal carrying real authorities**, rather than relying on variable names called “role” in code.

## 5. Authentication state: four important expressions

### 5.1. Checking Authentication.isAuthenticated() alone is not enough

An `AnonymousAuthenticationToken` in Spring Security often has `isAuthenticated() == true` as a token property, yet is still classified as anonymous by `AuthenticationTrustResolver`. Therefore, in SpEL use the dedicated expressions:

```java
@PreAuthorize("isAuthenticated()")
@PreAuthorize("isFullyAuthenticated()")
@PreAuthorize("isRememberMe()")
@PreAuthorize("isAnonymous()")
```

They are provided by Spring Security through `SecurityExpressionRoot`/`SecurityExpressionOperations` backed by authentication trust resolution, and should not all be replaced manually by checking the `authentication.authenticated` property.

### 5.2. Semantics matrix

| User state | `isAnonymous()` | `isAuthenticated()` | `isRememberMe()` | `isFullyAuthenticated()` |
| --- | --- | --- | --- | --- |
| Anonymous created by Spring Security | True | False | False | False |
| User logged in via remember-me token | False | True | True | False |
| User fully logged in (form/session, Basic, Bearer…) | False | True | False | True |
| No valid Authentication | Should not be assumed anonymous by default | Not granted access | No | No |

**The last row** is a conceptual safety classification: a request with no Authentication supplied to the interceptor may be rejected/handled by the framework before the expression runs; a null context must not be treated identically to a valid `AnonymousAuthenticationToken`. The goal is **never granting access due to an absent context**.

#### isAuthenticated()

`isAuthenticated()` permits an authenticated user (including remember-me mechanisms when enabled), excluding anonymous. Use it for actions that do not require fresh authentication:

```java
@PreAuthorize("isAuthenticated()")
public UserView currentProfile() { /* ... */ }
```

**Note:** being “authenticated” does not imply the user has permission on every resource. If the method accepts an arbitrary `userId`, an owner/tenant check is still required.

#### isFullyAuthenticated()

`isFullyAuthenticated()` requires the user not to be anonymous **and not merely authenticated via remember-me**. Useful for operations demanding a full login instead of automatic restoration:

```java
@PreAuthorize("isFullyAuthenticated() and hasAuthority('payment:approve')")
public void approvePayment(String id) { /* ... */ }
```

**Not synonymous with MFA or recent re-authentication.** A Bearer token or session can be considered fully authenticated without proving the user completed MFA/step-up under the product's policy. Those requirements need additional factor/session freshness mechanisms and version-specific tests.

#### isRememberMe()

`isRememberMe()` is True only for an authentication recognized by `AuthenticationTrustResolver` as **remember-me**; it does not mean “the browser has a cookie”. Distinguish between:

- An ordinary session cookie can represent a full login.
- A `RememberMeAuthenticationToken` created by the remember-me mechanism has its own trust level.
- A JWT is not automatically classified as remember-me merely because the token has a long lifetime.

Example fragment allowing only remember-me users to view a re-login prompt page:

```java
@PreAuthorize("isRememberMe()")
public ReauthenticationPrompt promptForFullLogin() { /* ... */ }
```

This is a specialized policy; typically a notification page should be open to a wider range of users. Do not use `isRememberMe()` as an alias for `isAuthenticated()`.

#### isAnonymous()

`isAnonymous()` matches only users considered anonymous by Spring Security:

```java
@PreAuthorize("isAnonymous()")
public String anonymousLanding() {
    return "Welcome, guest";
}
```

**Not synonymous with public for everyone:** users logged in fully or via remember-me can be denied at this method. If every user should be allowed in, see `permitAll` below.

### 5.3. permitAll and denyAll in SpEL

```java
@PreAuthorize("permitAll")
public String publicAnnouncement() { return "public"; }

@PreAuthorize("denyAll")
public String removedOperation() { return "disabled"; }
```

`permitAll` and `denyAll` are expressions meaning always allow / always deny **at the @PreAuthorize layer** (with an active method-security interceptor). Newer APIs also offer corresponding operations like `permitAll()`/`denyAll()`; the core semantics remain unchanged.

`permitAll` **does not**:
- Bypass HTTP endpoint security filters.
- Bypass CSRF for POST/PUT/PATCH/DELETE.
- Bypass `@PostAuthorize`, `@Secured`, JSR-250, or other custom advisors if active.
- Guarantee the controller exists or the service does not throw domain errors.

`denyAll` on a method **does not** mean removing the code path; self-invocation can bypass the proxy. When an operation must be shut down completely, block all entrypoints and test that no side effects occur.

## 6. Combining SpEL: AND, OR, NOT, and parentheses

SpEL supports word logical operators `and`, `or`, `not` or equivalent symbols `&&`, `||`, `!`. Inside Java annotation strings, word operators are usually easier to read and avoid confusion with other syntax.

### 6.1. A single permission as a simple condition

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView view(String reportId) { /* ... */ }
```

Meaning: `report:read` must be present in effective authorities.

### 6.2. Two permissions simultaneously

```java
@PreAuthorize(
    "hasAuthority('report:read') and hasAuthority('report:export')"
)
public byte[] export(String reportId) { /* ... */ }
```

Having `report:export` without `report:read` is insufficient. In real business logic, a dedicated `report:export` permission might already imply reading the report, but that is a permission-modeling choice, not a fact the framework infers on its own.

### 6.3. Role or permission

```java
@PreAuthorize(
    "hasRole('ADMIN') or hasAuthority('report:read')"
)
public ReportView inspect(String reportId) { /* ... */ }
```

Only **one** condition needs to be true. If ADMIN must still be subject to tenant scope or separate auditing, do not permit overly broad ORs that create an unapproved “superuser bypass”.

### 6.4. Expression order and parentheses

Suppose the policy is: **authenticated**, and **has ROLE_REVIEWER or ROLE_ADMIN**.

Correct:

```java
@PreAuthorize(
    "isAuthenticated() and (hasRole('REVIEWER') or hasRole('ADMIN'))"
)
public void review(String id) { /* ... */ }
```

The following expression:

```java
@PreAuthorize(
    "isAuthenticated() and hasRole('REVIEWER') or hasRole('ADMIN')"
)
```

can turn `hasRole('ADMIN')` into a separate OR branch due to operator precedence. If every principal with ROLE_ADMIN is fully authenticated in the model, the difference sometimes stays hidden in tests; logically, the policy still does not match the requirement “every path must be authenticated”. **Use parentheses to express intent**, especially when combining multiple AND/OR conditions.

### 6.5. NOT and exclusions

```java
@PreAuthorize(
    "isAuthenticated() and !hasAuthority('account:suspended')"
)
public void uploadDocument(String id) { /* ... */ }
```

The example illustrates blocking a user who has the `account:suspended` authority. However, if the system fails to assign that authority properly or a session/JWT is stale, the expression will permit a suspended user. Account/lock status in the database should generally be verified against a trusted source, not merely “flag absent from token”.

### 6.6. Do not cram an overly long policy into one annotation

When an expression becomes:

```java
@PreAuthorize(
    "isFullyAuthenticated() and " +
    "(hasRole('REVIEWER') or hasRole('ADMIN')) and " +
    "hasAuthority('document:approve') and " +
    "@approvalPolicy.canApprove(authentication, #documentId)"
)
```

consider extracting the business logic into a clearly named bean while keeping only the core functional conditions on the annotation. A policy bean can be thoroughly unit-tested against resource data and state, instead of a long expression that is hard to audit.

## 7. authentication and principal: two distinct objects in SpEL

### 7.1. authentication references the current Authentication

```java
@PreAuthorize("authentication.name == #username")
public String getOwnProfile(String username) { /* ... */ }
```

`authentication` is an `Authentication`, and the `name` property usually corresponds to `getName()`. The expression only allows the user to call with a `username` matching the name in the authentication. This is a simple owner-check example **if username is a trusted/unique identifier**; for sensitive data, verify owner ID/tenant from a trusted source rather than relying on a mutable name.

### 7.2. principal is Authentication.getPrincipal()

```java
@PreAuthorize("principal.username == #username")
public String getProfile(String username) { /* ... */ }
```

This expression only works when the principal actually has a `username` property (such as certain `UserDetails`). With JWT, the principal may be a `Jwt` or another type without `username`; and an anonymous principal is typically a string like `anonymousUser`. **Do not assume principal is always a UserDetails**.

A less principal-type-dependent form is:

```java
@PreAuthorize("authentication.name == #username")
```

Still, you must verify that authentication name is the entity key the system uses for authorization.

### 7.3. Avoid logging principal, credentials, or raw tokens

Do not write logs like:

```java
logger.info("Auth object: {}", authentication);
```

unconditionally in production; Authentication/details can contain internal data, claims, or information not meant for logs. When authorization diagnostics are needed, log only permitted user IDs, permission names, and correlation IDs safely, without outputting access tokens or passwords.

### 7.4. Principals from JWT and OAuth2

When Spring Resource Server validates a JWT, the converter typically maps scopes into authorities of the form `SCOPE_xxx`. For example:

```text
scope claim: reports.read
authority:   SCOPE_reports.read
```

Then:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public ReportView getReport(String id) { /* ... */ }
```

matches the corresponding default authority, **not** `hasRole('reports.read')` or `hasAuthority('report:read')` unless the converter renames them. Do not guess: test `JwtAuthenticationConverter` and the actual authorities for your application version.

## 8. Using method parameters in SpEL expressions

### 8.1. The #parameterName notation

`@PreAuthorize` receives the method invocation and can access method arguments:

```java
@PreAuthorize(
    "hasAuthority('invoice:read') and " +
    "@invoicePolicy.canRead(authentication, #invoiceId)"
)
public InvoiceView readInvoice(String invoiceId) {
    return invoiceService.read(invoiceId);
}
```

`#invoiceId` is the argument value. `@invoicePolicy` references a bean in the Spring context; `canRead` is an **application-implemented** method, not a built-in Spring Security API. The `InvoiceView` type and service are also domain code.

### 8.2. Parameter name discovery

Spring Security uses parameter name discovery; depending on the project/compiler, real names can be retained via the Java `-parameters` flag, or via the `@P` annotation:

```java
import org.springframework.security.access.method.P;

@PreAuthorize(
    "hasAuthority('invoice:read') and " +
    "@invoicePolicy.canRead(authentication, #targetId)"
)
public InvoiceView readInvoice(@P("targetId") String invoiceId) {
    return invoiceService.read(invoiceId);
}
```

This form lets SpEL use `#targetId` even though the Java parameter name is `invoiceId`. In some contexts positional parameters (`#p0` or `#a0`) can also be accessed, but explicit names are easier to read and test. For interface methods, check that annotations are placed properly and visible to the proxy.

### 8.3. A parameter is not trustworthy just because it appears in SpEL

A client can send any `invoiceId` or `tenantId`. If a policy uses:

```java
@PreAuthorize("#requestedTenantId == authentication.name")
```

it fails to check whether the actual invoice belongs to that tenant. An attacker can supply both the ID and the tenant ID to satisfy the condition.

In the policy bean, load the resource from a trusted source, check tenant/owner/membership/state, and then decide:

```text
ALLOW =
  hasAuthority("invoice:read")
  AND invoice.tenantId == user.tenantId
  AND invoice is visible under business policy
```

This is a pseudo-policy; depending on the use case it should run under an appropriate transaction to avoid data changing between the check and the action (*TOCTOU*). Without object-level checks, a user with the right role can still read another tenant's data.

### 8.4. Null safety and expression errors

A SpEL accessing `#request.ownerId` when `request == null` can throw an evaluation error. Do not rely on that exception as an intentionally designed deny policy.

For potentially null inputs:

```java
@PreAuthorize(
    "#request != null and " +
    "hasAuthority('document:create') and " +
    "@documentPolicy.canCreate(authentication, #request)"
)
```

This is a fragment with an application-provided `documentPolicy` bean. The service still needs Bean Validation, data validation, and protection against leaking exception details in HTTP responses. Use SpEL's null-safe operator where appropriate and version-supported, but **do not** treat null-safe navigation as a substitute for data-validation policies.

## 9. Calling policy beans instead of embedding all business logic in SpEL

### 9.1. A policy bean has one clear responsibility

Example:

```java
package com.example.security;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentAccessRepository accessRepository;

    public DocumentPolicy(DocumentAccessRepository accessRepository) {
        this.accessRepository = accessRepository;
    }

    public boolean canRead(Authentication actor, String documentId) {
        if (actor == null || documentId == null || documentId.isBlank()) {
            return false;
        }
        if (!actor.isAuthenticated()) {
            return false;
        }
        // Repository must fetch verified membership/owner/tenant from DB.
        return accessRepository.userCanRead(actor.getName(), documentId);
    }
}
```

This is an **architecture fragment**, requiring a project-defined `DocumentAccessRepository`; `actor.isAuthenticated()` is **not sufficient** to distinguish anonymous users per Spring Security's trust resolver. In production, ensure the request/method invocation already passed `isAuthenticated()` in the expression or use `AuthenticationTrustResolver` inside the policy bean if it can be called from other paths. The policy still needs exception handling, caching, and transactional consistency when appropriate.

How to place the annotation:

```java
@PreAuthorize(
    "isAuthenticated() and hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentView readDocument(String documentId) {
    return documentService.read(documentId);
}
```

`DocumentView` and `documentService` are domain code undeclared in the fragment. Spring Security will invoke the `documentPolicy` bean within the expression context. When a policy becomes complex, avoid putting SQL/HTTP calls directly inside the SpEL string.

### 9.2. Using @PreAuthorize as a gate before write actions

```java
@PreAuthorize(
    "isFullyAuthenticated() and " +
    "hasAuthority('document:approve') and " +
    "@documentPolicy.canApprove(authentication, #documentId)"
)
public void approve(String documentId) {
    documentService.approve(documentId);
}
```

Ensure `canApprove` checks the **actual object**: the report/document belongs to the tenant, is in pending-approval status, the approver is not the creator if business rules forbid it, and any required delegation rules hold. For concurrently changing data, use transactions/optimistic locking or update-time checks to prevent policy state from drifting since the check.

### 9.3. When shouldn't you use SpEL for everything?

- Rules requiring access across multiple tables, transactions, or locks.
- Policies that must be reused across HTTP, queues, and batch jobs.
- Rules varying by time, version, or tenant policy.
- Complex branching of exceptions/approval workflows.
- Calling beans from expressions causes N+1 queries or unstable performance.

In such cases, use a permission-oriented service/domain policy and keep the method annotation as an entry gate. Do not force every policy into a long SpEL string.

## 10. Role hierarchy and SpEL

### 10.1. A higher role does not automatically include a lower role

Suppose a user only has:

```text
ROLE_ADMIN
```

and a method requires:

```java
@PreAuthorize("hasRole('USER')")
public String readDashboard() { return "dashboard"; }
```

By default, **merely having ROLE_ADMIN does not grant the user ROLE_USER**. If ADMIN should imply USER, either assign direct `ROLE_USER` at the authentication source, or configure a `RoleHierarchy`:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
```

The `>` symbol represents one-way inclusion and is transitive.

### 10.2. Configuring a hierarchy-aware method-security expression handler

Per Spring Security guidance, use the appropriate `RoleHierarchy` and `MethodSecurityExpressionHandler` beans:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Configuration
public class RoleHierarchyConfig {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
                ROLE_ADMIN > ROLE_MANAGER
                ROLE_MANAGER > ROLE_USER
                ROLE_MANAGER > report:read
                """);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }
}
```

This is a Spring configuration class, requiring method security enabled as in section 2; using the expression handler as shown is documented for 6.x. For Spring Security 7.x, factory APIs may be preferred/customized differently; consult the actual version's Javadoc. `static @Bean` lets the method security infrastructure see the handler before initialization.

### 10.3. Test direct and inferred authorities separately

With the graph above:

- Direct `ROLE_ADMIN` can reach `ROLE_MANAGER`, `ROLE_USER`, and `report:read`.
- Direct `ROLE_USER` **does not** imply `ROLE_MANAGER` in reverse.
- Direct `ROLE_MANAGER` reaches `report:read` if the handler uses the hierarchy.
- Direct permission `report:read` does not automatically give the user role MANAGER.

`Authentication.getAuthorities()` may still contain only direct authorities. Testing `getReachableGrantedAuthorities` checks the graph; testing `@PreAuthorize("hasRole('USER')")` on a Spring bean checks that the manager **actually uses** the graph. The two test types do not replace each other.

### 10.4. Be careful when granting admin access via OR

```java
@PreAuthorize(
    "hasRole('ADMIN') or hasAuthority('document:delete')"
)
```

allows two independent paths. When using a hierarchy, a role can imply the `document:delete` permission along the graph. If an edge is added by mistake, even a low role might be able to delete documents. Test not only that high roles are permitted, but also that **low roles are definitely denied**.

## 11. Comparing SpEL with HTTP authorization

### 11.1. Two protection boundaries

Servlet SecurityFilterChain example:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/news").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/reports/**").authenticated()
    .anyRequest().denyAll()
);
```

In the service:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView loadVisibleReport(String id) { /* ... */ }

@PreAuthorize("isFullyAuthenticated() and hasRole('ADMIN')")
public void disableAccount(String accountId) { /* ... */ }
```

Both rule types have distinct roles:

1. HTTP route filters decide whether a request may enter an endpoint by method/path.
2. Service method security checks right before invocation.
3. Domain policies additionally check tenant/owner/record state.
4. CSRF/CORS/authentication filters can also block before the method runs.

Thus `@PreAuthorize("permitAll")` does not open `GET /api/admin/...` to guests if the HTTP rule still says `hasRole("ADMIN")`. Conversely, HTTP `permitAll()` does not bypass a `@PreAuthorize` requiring a permission in the service.

### 11.2. Do not force every method through one controller

If the policy lives only in a controller, the same use case could be called from a queue, scheduler, or new GraphQL/gRPC endpoint that forgets the rule. Placing policies at the service boundary provides deeper defense, but you must ensure every call path goes through the Spring proxy and carries the right actor identity.

### 11.3. SpEL cannot compensate for a weak authentication provider

An `isAuthenticated()` expression only knows the context established by the authentication mechanism. If the identity provider, JWT converter, or session handling is wrong, SpEL cannot fix it automatically. Test with real tokens/cookies at the integration level, not only mocked principals via `@WithMockUser`.

## 12. Limitations of @PreAuthorize and Spring AOP

### 12.1. Self-invocation bypasses the method-security proxy

```java
@Service
public class UnsafeService {

    public void outer(String id) {
        deleteSensitive(id); // this.deleteSensitive(id)
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void deleteSensitive(String id) {
        // Sensitive action
    }
}
```

This is an **anti-pattern**. `outer` makes an internal call to `deleteSensitive` on the same instance, typically bypassing the Spring AOP proxy so `@PreAuthorize` is not enforced at that boundary.

The usual fix is to extract the sensitive method into another Spring-managed bean, invoke it through the injected bean proxy, and let the domain policy enforce itself in the service. Do not use `self-injection` as an unreviewed trick.

### 12.2. Final/private/non-Spring objects

A private method or an object created with `new` is not a reliable AOP proxy protection point. With Kotlin (where classes/methods are final by default) or Java final methods, verify the proxying strategy and configuration; if using AspectJ weaving instead of proxies, characteristics differ and must be tested separately.

### 12.3. SpEL does not automatically follow every thread

`SecurityContextHolder` in Servlet usually relies on `ThreadLocal`. Inside a raw `Executor`, `CompletableFuture.supplyAsync`, or `@Async` without a context-aware executor, method security may not see the request user. Spring MVC `Callable` has dedicated integration, but nested tasks do not propagate automatically. Use `DelegatingSecurityContextExecutor`/`DelegatingSecurityContextAsyncTaskExecutor` or mechanisms supported by your Spring Security version, and verify cleanup.

**Do not** grant ADMIN to a worker just to fix missing context errors. Workers need an appropriate identity or least-privilege service account, plus re-authorization if tasks wait a long time.

### 12.4. Class-level and method-level annotations

```java
@PreAuthorize("hasRole('USER')")
public class ProfileService {

    public String view() { return "view"; }

    @PreAuthorize("hasRole('ADMIN')")
    public String delete(String id) { return "deleted"; }
}
```

Under Spring method security, an annotation on a **method can override an annotation of the same type on the class**. In the example above, `delete` uses the method's ADMIN rule and **is not automatically ANDed** with the class's USER role. Annotations of **different types**, such as `@PreAuthorize` alongside `@PostAuthorize`, run as separate checks and can create an overall AND effect.

When conflicting annotations on multiple interfaces cause ambiguity, Spring Security may fail startup; place annotations clearly on concrete methods and test.

### 12.5. Do not repeat two @PreAuthorize annotations on the same method

`@PreAuthorize` cannot be repeated twice on the same method expecting an AND check. Use a single combined expression:

```java
@PreAuthorize("hasRole('ADMIN') and isFullyAuthenticated()")
public void rotateCredential() { /* ... */ }
```

or call a policy bean.

## 13. Testing with Spring Security Test and JUnit 5

### 13.1. @WithMockUser(roles=...) and authorities=...

```java
@WithMockUser(roles = "ADMIN")
```

normally creates a user with authority `ROLE_ADMIN`. Whereas:

```java
@WithMockUser(authorities = "ADMIN")
```

grants the **exact string `ADMIN`**, without automatically adding `ROLE_`.

When permissions are needed:

```java
@WithMockUser(authorities = {"ROLE_USER", "report:read"})
```

Do not grant the inferred authority in the test fixture if the goal is testing role hierarchy: such a test would still pass when the hierarchy is broken.

`@WithMockUser` creates an authentication for tests and does not verify a real password provider/JWT converter. To test production authority sources, use integration tests with the actual authentication mechanism.

### 13.2. @WithAnonymousUser and missing-auth scenarios

`@WithAnonymousUser` simulates an anonymous principal handled by Spring Security. Use it to verify:

- `isAnonymous()` can pass.
- `isAuthenticated()` denies.
- `isFullyAuthenticated()` denies.
- Business roles/permissions are not granted automatically.
- `permitAll` still passes at the method layer.

For a denied method invocation, modern Spring Test/Spring Security typically throws `AccessDeniedException`, while handling through HTTP may result in 401, 403, or a redirect depending on the entry point.

### 13.3. Testing a proxied service bean

Suppose we have a test service:

```java
package com.example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ExpressionProbe {

    @PreAuthorize("permitAll")
    public String publicData() {
        return "public-ok";
    }

    @PreAuthorize("isAuthenticated()")
    public String profile() {
        return "profile-ok";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String admin() {
        return "admin-ok";
    }

    @PreAuthorize("hasAuthority('report:read')")
    public String report() {
        return "report-ok";
    }

    @PreAuthorize(
        "isFullyAuthenticated() and hasAuthority('payment:approve')")
    public String sensitive() {
        return "sensitive-ok";
    }

    @PreAuthorize("isAnonymous()")
    public String anonymousOnly() {
        return "anonymous-ok";
    }
}
```

This class compiles in a Spring Security/Spring Context project with `@EnableMethodSecurity`, serving as a simple probe **without a database**.

Sample JUnit 5/AssertJ fragments inside a Spring context test:

```java
@Autowired
ExpressionProbe probe;

@Test
@WithAnonymousUser
void anonymousCannotAccessProfile() {
    assertThatThrownBy(() -> probe.profile())
        .isInstanceOf(AccessDeniedException.class);
}

@Test
@WithAnonymousUser
void anonymousCanCallAnonymousAndPublic() {
    assertThat(probe.anonymousOnly()).isEqualTo("anonymous-ok");
    assertThat(probe.publicData()).isEqualTo("public-ok");
}

@Test
@WithMockUser(roles = "USER")
void ordinaryUserCannotCallAdmin() {
    assertThatThrownBy(() -> probe.admin())
        .isInstanceOf(AccessDeniedException.class);
}

@Test
@WithMockUser(roles = "ADMIN")
void adminRoleMatchesDefaultPrefix() {
    assertThat(probe.admin()).isEqualTo("admin-ok");
}

@Test
@WithMockUser(authorities = {"ROLE_USER", "report:read"})
void permissionWorksIndependentlyOfRole() {
    assertThat(probe.report()).isEqualTo("report-ok");
}

@Test
@WithMockUser(authorities = "payment:approve")
void fullyAuthenticatedMockUserCanPerformSensitiveTask() {
    assertThat(probe.sensitive()).isEqualTo("sensitive-ok");
}
```

These snippets require `@SpringBootTest` or `@SpringJUnitConfig` with method security, JUnit/AssertJ/Spring Security Test dependencies, bean injection, and imports. A `@WithMockUser` test represents a common fully authenticated token, yet **does not** test real remember-me behavior.

### 13.4. Testing a wrong role prefix

```java
@Test
@WithMockUser(authorities = "ADMIN")
void unprefixedAuthorityIsNotAdminRole() {
    assertThatThrownBy(() -> probe.admin())
        .isInstanceOf(AccessDeniedException.class);
}
```

When the default prefix is `ROLE_`, the string `ADMIN` does not satisfy `hasRole('ADMIN')`. If the project uses a custom prefix, update expected tests to match the actual policy.

### 13.5. Testing remember-me is not like @WithMockUser

A test using only `@WithMockUser` cannot prove that `isFullyAuthenticated()` distinguishes remember-me. You must construct an appropriate `RememberMeAuthenticationToken` and place it in the `SecurityContext` in the test, for instance using `@WithSecurityContext` with a custom factory.

This is a **Spring Security Test fragment**, showing the factory structure:

```java
import java.util.List;

import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

final class RememberedUserFactory
        implements WithSecurityContextFactory<WithRememberedUser> {

    @Override
    public SecurityContext createSecurityContext(WithRememberedUser ann) {
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();

        var authentication = new RememberMeAuthenticationToken(
                "test-remember-me-key",
                ann.username(),
                List.of(new SimpleGrantedAuthority("payment:approve"))
        );
        context.setAuthentication(authentication);
        return context;
    }
}
```

The `WithRememberedUser` annotation can be defined in the test suite:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(factory = RememberedUserFactory.class)
public @interface WithRememberedUser {
    String username() default "remembered-user";
}
```

These are **two fragments** for a test suite, not standalone Java; imports, package visibility, and Spring test configuration must be properly arranged in the project. `RememberMeAuthenticationToken` uses a key for integrity checks in some mechanisms, while the example factory does not perform real cookie login.

Test:

```java
@Test
@WithRememberedUser
void rememberMeCanBeAuthenticatedButNotFullyAuthenticated() {
    assertThat(probe.profile()).isEqualTo("profile-ok");

    assertThatThrownBy(() -> probe.sensitive())
        .isInstanceOf(AccessDeniedException.class);
}
```

Even though the remember-me principal holds `payment:approve`, the `sensitive` method still denies access because `isFullyAuthenticated() == false`. That is the key result to prove.

### 13.6. Summary test matrix

| Test principal | isAnonymous | isAuthenticated | isFullyAuthenticated | hasRole('ADMIN') | hasAuthority('report:read') |
| --- | --- | --- | --- | --- | --- |
| Anonymous | True | False | False | False | False |
| @WithMockUser(roles="USER") | False | True | True | False | False |
| @WithMockUser(roles="ADMIN") | False | True | True | True | False without mapping |
| @WithMockUser(authorities="report:read") | False | True | True | False | True |
| Custom remember-me with report:read | False | True | False | Per granted roles | True |
| @WithMockUser(authorities="ADMIN") | False | True | True | False under default prefix | False |

Policy tests should include **deny cases** for every sensitive action, plus an unauthenticated case for public methods, avoiding the trap where “almost every test runs as ADMIN so nobody notices regular users are over-privileged”.

## 14. Testing HTTP and method security together

### 14.1. A valid method does not mean the HTTP route is valid

Suppose:

```java
// In Servlet SecurityFilterChain:
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .authenticated()
.anyRequest().denyAll()
```

while in controller/service it calls:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView read(String reportId) { /* ... */ }
```

A client lacking the permission can pass HTTP `authenticated` yet be denied at the service. Conversely, a `@PreAuthorize("permitAll")` method does not open an HTTP URL blocked by `denyAll`. This is intentional defense-in-depth.

### 14.2. MockMvc negative test

```java
@Test
@WithMockUser(authorities = "report:write")
void writerWithoutReadPermissionCannotRead() throws Exception {
    mockMvc.perform(get("/api/reports/r1"))
        .andExpect(status().isForbidden());
}
```

This **fragment** only holds when HTTP lets the authenticated user through, the real controller invokes the Spring-managed service annotated with `hasAuthority('report:read')`, and no custom exception handler alters the status. If a test runs without CSRF on a POST, a 403 status does not prove method-security denied it; supply a valid CSRF token where appropriate.

### 14.3. HTTP tests do not replace service tests

An unmapped controller can return 404 before the test reaches the service. A misconfigured HTTP matcher can block at the filter while the service method remains untested. Therefore, include:

1. **Service-level tests** calling the proxied bean with `@WithMockUser`/`@WithAnonymousUser`.
2. **MockMvc/integration tests** through `SecurityFilterChain`.
3. **Domain tests** verifying tenant/owner/row state.
4. **Token/session tests** for real production authorities.

### 14.4. Authentication entry point and status

A guest calling an auth-required HTTP endpoint may receive **401 Unauthorized**, a login redirect, or another response configured by `AuthenticationEntryPoint`. An authenticated user lacking an authority typically receives **403 Forbidden**. A method invocation denied outside HTTP mainly produces **an exception or method-denial handling**, rather than automatically “returning an HTTP status”.

Do not hard-assert a single status across all projects; verify where the failure actually happens.

## 15. Standalone Java 17 example: roles, authorities, and trust levels

The following program simulates the **meaning** of common expressions without loading Spring. It intentionally separates:

- `Trust.ANONYMOUS`: anonymous.
- `Trust.REMEMBER_ME`: remembered user, not fully authenticated.
- `Trust.FULL`: fully authenticated user in the demo model.
- Authority set: `ROLE_*` strings or specific permissions.
- Policies for public, profile, review, export, approve.

This is an **educational simulation**, not Spring's SpEL parser, `AuthenticationTrustResolver`, or `AuthorizationManager`. It does not handle JWT, sessions, CSRF, MFA, token freshness, or object-level authorization.

Create `SpelAuthConceptDemo.java`:

```java
import java.util.Set;

public class SpelAuthConceptDemo {

    enum Trust {
        ANONYMOUS,
        REMEMBER_ME,
        FULL
    }

    record Caller(
            String name,
            Trust trust,
            Set<String> authorities) {

        Caller {
            authorities = authorities == null
                    ? Set.of() : Set.copyOf(authorities);
        }
    }

    static boolean isAnonymous(Caller c) {
        return c != null && c.trust() == Trust.ANONYMOUS;
    }

    static boolean isAuthenticated(Caller c) {
        return c != null && c.trust() != Trust.ANONYMOUS;
    }

    static boolean isRememberMe(Caller c) {
        return c != null && c.trust() == Trust.REMEMBER_ME;
    }

    static boolean isFullyAuthenticated(Caller c) {
        return c != null && c.trust() == Trust.FULL;
    }

    static boolean hasAuthority(Caller c, String authority) {
        return c != null && c.authorities().contains(authority);
    }

    static boolean hasRole(Caller c, String role) {
        return hasAuthority(c, "ROLE_" + role);
    }

    static boolean hasAnyAuthority(Caller c, String a, String b) {
        return hasAuthority(c, a) || hasAuthority(c, b);
    }

    static String decision(boolean allowed) {
        return allowed ? "ALLOW" : "DENY";
    }

    static void print(String label, boolean allowed) {
        System.out.println(label + "=" + decision(allowed));
    }

    public static void main(String[] args) {
        Caller guest = new Caller(
                "anonymousUser",
                Trust.ANONYMOUS,
                Set.of("ROLE_ANONYMOUS"));

        Caller remembered = new Caller(
                "mai",
                Trust.REMEMBER_ME,
                Set.of("ROLE_REVIEWER", "report:read"));

        Caller manager = new Caller(
                "linh",
                Trust.FULL,
                Set.of("ROLE_MANAGER", "report:approve", "report:export"));

        Caller admin = new Caller(
                "an",
                Trust.FULL,
                Set.of("ROLE_ADMIN", "report:read"));

        Caller wrongPrefix = new Caller(
                "unprefixed-admin",
                Trust.FULL,
                Set.of("ADMIN"));

        print("guest-public", true);
        print("manager-public", true);

        print("guest-profile", isAuthenticated(guest));
        print("remember-profile", isAuthenticated(remembered));
        print("manager-profile", isAuthenticated(manager));

        print("guest-anonymous-only", isAnonymous(guest));
        print("manager-anonymous-only", isAnonymous(manager));
        print("remember-is-remember-me", isRememberMe(remembered));

        print("remember-full", isFullyAuthenticated(remembered));
        print("manager-full", isFullyAuthenticated(manager));

        print("remember-review",
                isAuthenticated(remembered)
                    && (hasRole(remembered, "REVIEWER")
                        || hasRole(remembered, "ADMIN")));
        print("admin-review",
                isAuthenticated(admin)
                    && (hasRole(admin, "REVIEWER")
                        || hasRole(admin, "ADMIN")));

        print("remember-read",
                hasAnyAuthority(remembered, "report:read", "report:manage"));
        print("guest-read",
                hasAnyAuthority(guest, "report:read", "report:manage"));

        print("remember-export",
                isFullyAuthenticated(remembered)
                    && hasAuthority(remembered, "report:export"));
        print("manager-export",
                isFullyAuthenticated(manager)
                    && hasAuthority(manager, "report:export"));
        print("admin-export",
                isFullyAuthenticated(admin)
                    && hasAuthority(admin, "report:export"));

        print("manager-approve",
                isFullyAuthenticated(manager)
                    && hasRole(manager, "MANAGER")
                    && hasAuthority(manager, "report:approve"));
        print("admin-approve",
                isFullyAuthenticated(admin)
                    && hasRole(admin, "MANAGER")
                    && hasAuthority(admin, "report:approve"));

        print("unprefixed-admin-role",
                hasRole(wrongPrefix, "ADMIN"));
    }
}
```

Compile with JDK 17 or later:

```bash
javac SpelAuthConceptDemo.java
java SpelAuthConceptDemo
```

Expected stdout:

```text
guest-public=ALLOW
manager-public=ALLOW
guest-profile=DENY
remember-profile=ALLOW
manager-profile=ALLOW
guest-anonymous-only=ALLOW
manager-anonymous-only=DENY
remember-is-remember-me=ALLOW
remember-full=DENY
manager-full=ALLOW
remember-review=ALLOW
admin-review=ALLOW
remember-read=ALLOW
guest-read=DENY
remember-export=DENY
manager-export=ALLOW
admin-export=DENY
manager-approve=ALLOW
admin-approve=DENY
unprefixed-admin-role=DENY
```

### 15.1. Reading the output concept by concept

- Public method is open to both guest and manager; this is only the demo's mock policy.
- Remember-me **is considered authenticated** but **not fully authenticated**.
- Users with role REVIEWER or ADMIN are both permitted into review; the role list is combined with OR.
- Having `report:read` allows reading, but does not automatically grant `report:export`.
- Manager FULL has `ROLE_MANAGER`, `report:approve`, and `report:export` to perform the two demonstrated operations.
- Admin FULL only has `ROLE_ADMIN` and `report:read`, so it **cannot automatically** export/approve; this is the difference between roles and permissions without a mapping/hierarchy.
- Unprefixed authority `ADMIN` does not satisfy `hasRole('ADMIN')` under the default demo convention.

### 15.2. Example limitations

- The demo uses a custom `Trust` enum and does not recognize Spring's `AnonymousAuthenticationToken`, `RememberMeAuthenticationToken`, or `JwtAuthenticationToken`.
- The demo does not evaluate SpEL strings, method parameters, or AOP interception.
- `hasAuthority` in the demo checks only direct authorities, without `RoleHierarchy`.
- No object/tenant checks, MFA, session state, or JWT revocation.
- Complete absence of Authentication requires a fail-closed policy; the demo simulates this with `c == null`.

**Next step to apply in practice:** write the Spring service probe from section 13 and test a real Spring context; do not turn demo helper methods into a homemade production authorization framework.

## 16. Common pitfalls and fixes

| Symptom or pitfall | Why it happens | Fix |
| --- | --- | --- |
| `@PreAuthorize` blocks nobody | `@EnableMethodSecurity` not enabled or not going through proxy | Enable method security, test proxied bean |
| `hasRole('ADMIN')` returns 403 even though principal has `ADMIN` | Default prefix requires `ROLE_ADMIN` | Inspect authority source/mapping |
| `hasAuthority('report:read')` returns 403 when only `ROLE_ADMIN` exists | Permission not granted or no hierarchy configured | Grant/map permission per policy |
| `hasAnyRole('ADMIN','EDITOR')` assumed to be AND | “Any” means OR | Use `and` or a dedicated permission if both are needed |
| `isAuthenticated()` written as `authentication.authenticated` | Anonymous tokens can carry an authenticated flag | Use trust-resolver-backed expressions |
| Remember-me user accesses sensitive actions | Policy only requires `isAuthenticated()` | Use `isFullyAuthenticated()` when appropriate, add MFA if needed |
| `isFullyAuthenticated()` treated as MFA | It only excludes anonymous/remember-me | Design separate MFA/step-up |
| `@PreAuthorize("permitAll")` yet HTTP returns 401 | HTTP rule requires login | Configure public HTTP if business logic requires |
| Annotated method runs from `this.method()` | Self-invocation bypasses Spring AOP | Separate bean boundaries and test |
| `@WithMockUser` test passes, production JWT fails | Converter grants different authorities than mock | Test real JWT/IDP mapping |
| User with `ROLE_MANAGER` deletes another tenant's file | Missing object authorization | Policy bean checks DB tenant/owner/ACL |
| SpEL reports `#id` not found | Java didn't preserve parameter names or `@P` missing | Enable `-parameters` or `@P` |
| SpEL throws error when principal is String/JWT | Assumed principal is UserDetails | Use `authentication.name` or type-aware handler |
| Expression has wrong AND/OR | Missing parentheses / operator precedence | Write clear policies and test truth table |
| Async task lacks authentication | ThreadLocal doesn't follow arbitrary executors | Context-aware executor / actor policy |
| RoleHierarchy test passes yet method doesn't enforce it | Handler doesn't use the graph | Configure `MethodSecurityExpressionHandler` and test proxy |
| POST returns 403 despite correct role | CSRF or HTTP filter blocks before method | Retry with valid CSRF, inspect filter chain |
| Class and method rules assumed to be AND | Method can override class `@PreAuthorize` | Test annotation resolution |
| Unannotated method still executes | Method security doesn't auto-deny every method | Service boundary / HTTP deny-by-default |
| HTTP 200 yet data leaks | Only tested functionality, not owner/tenant | Negative data access tests |

### Debugging workflow

1. **Identify the denial layer:** HTTP, CSRF, authentication, method-security, or domain policy? Do not guess from a single 403 status.
2. **Inspect verified authorities:** `Authentication.getAuthorities()` in tests and how mappers produce `ROLE_*`/`SCOPE_*`.
3. **Check trust level:** are anonymous, remember-me, fully authenticated, and custom tokens recognized properly by the resolver?
4. **Inspect the actual SpEL expression:** operators, parentheses, parameter names, bean references, and evaluation errors.
5. **Check proxy/async:** is the method called from another bean through AOP? Does the worker have the proper security context?
6. **Check resource policies:** are tenant/owner/row state/SoD checked against trusted data?
7. **Control test cases:** authorized user, under-privileged user, anonymous, remember-me, wrong role prefix, real JWT converter.

Never fix incidents by granting `ROLE_ADMIN` to all users, changing all annotations to `permitAll`, or disabling CSRF.

## 17. Secure implementation checklist

**Configuration:**

- [ ] `@EnableMethodSecurity` is active and bean annotations go through proxies.
- [ ] The project has identified its Spring Security version, authentication mechanism, and role prefix.
- [ ] HTTP authorization is a separate layer with an appropriate deny fallback.
- [ ] Conventions for `ROLE_*`, `SCOPE_*`, and business permissions are consistent.
- [ ] If RoleHierarchy is used, the SpEL handler actually uses the graph.

**Expressions:**

- [ ] `hasRole` is used for roles, `hasAuthority` for exact authority strings.
- [ ] `hasAnyRole`/`hasAnyAuthority` are understood as OR; AND is written explicitly.
- [ ] `isAuthenticated` is not misinterpreted as “fully authenticated”.
- [ ] `isFullyAuthenticated` only guarantees not anonymous/remember-me, **not** MFA/fresh login automatically.
- [ ] Parentheses are used explicitly when AND/OR appear in the same expression.
- [ ] No assumption that principal is always `UserDetails`.
- [ ] `#parameter` names are discovered reliably; `@P` or `-parameters` is used where needed.
- [ ] Complex logic is placed into policy beans with trusted data sources.

**Testing:**

- [ ] Use `@WithAnonymousUser` for anonymous scenarios.
- [ ] Use `@WithMockUser(roles=...)` to test role prefixes and `authorities=...` for permissions.
- [ ] Construct real remember-me Authentication in tests to verify `isFullyAuthenticated`.
- [ ] Include negative tests for mismatched roles/authorities and cross-tenant data.
- [ ] Include MockMvc or HTTP integration tests with filter chain/CSRF/entry point.
- [ ] Test self-invocation and nested/async tasks where relevant.
- [ ] Test JWT/session stale authorities and role revocation according to sensitivity.
- [ ] For data-writing actions, assert **no side effects** occur when denied.

**Operations:**

- [ ] Do not put raw tokens/credentials in logs.
- [ ] Ensure permissions/tokens have TTL/revocation strategies.
- [ ] Review whenever adding a new method or opening a new role.
- [ ] Audit sensitive actions with actor and appropriate resource scope.
- [ ] Plan re-testing when upgrading Spring Security/method expression handlers.

## 18. Self-check questions

**Q1.** What authority does `@PreAuthorize("hasRole('ADMIN')")` require by default?

**Answer:** `ROLE_ADMIN`. Bare `ADMIN` or `SCOPE_ADMIN` is not automatically equivalent.

**Q2.** Does `hasAnyAuthority('a','b')` require both permissions?

**Answer:** No, it is OR. Use `hasAuthority('a') and hasAuthority('b')` if both are needed at once.

**Q3.** For an anonymous principal, `Authentication.isAuthenticated()` can be true. Should it be used instead of `isAuthenticated()` in SpEL?

**Answer:** No. Use `isAuthenticated()` from Spring Security's expression root/trust resolver to distinguish anonymous users properly.

**Q4.** What do `isAuthenticated()` and `isFullyAuthenticated()` return for a remember-me user?

**Answer:** Typically true and false, because remember-me does not meet fully authenticated under Spring Security's trust model.

**Q5.** Does `isFullyAuthenticated()` prove a user completed MFA within the last 5 minutes?

**Answer:** No. It only distinguishes from anonymous/remember-me; MFA and freshness require separate mechanisms.

**Q6.** Does `@PreAuthorize("permitAll")` open an HTTP route configured with `hasRole('ADMIN')`?

**Answer:** No. HTTP filters can block the request before the method runs.

**Q7.** Does `@PreAuthorize("isAnonymous()")` let a logged-in user through?

**Answer:** No under the normal trust model; the expression is specifically for anonymous callers.

**Q8.** Does a user with `ROLE_ADMIN` automatically have `report:export`?

**Answer:** No. They need the permission granted directly, a role→permission mapping at authentication, or a hierarchy graph used by the handler.

**Q9.** Does `authentication.name == #username` always prove permission to read an object?

**Answer:** No. Only reasonable if username is truly a trusted owner identifier; for other resource IDs, database/tenant/ACL policies are still needed.

**Q10.** When the Java compiler strips parameter names, `#invoiceId` can fail. How do you fix it?

**Answer:** Enable `-parameters` or annotate with `@P("invoiceId")` per Spring Security's mechanism; test expression resolution in the application context.

**Q11.** Is `@PreAuthorize("hasRole('ADMIN')")` on a private method or called via `this.method()` guaranteed to protect it?

**Answer:** No under the usual Spring AOP proxy model; the call may not pass through the interceptor. Place security at a testable Spring-managed service boundary.

**Q12.** Are two `@PreAuthorize` annotations on the same method valid to create an AND?

**Answer:** That is not a supported approach. Write a single expression with `and`/`or` or invoke a policy bean.

**Q13.** A `@WithMockUser(roles="ADMIN")` test passes, yet production JWT gets 403 even though the token contains scope admin. Why?

**Answer:** Mock user has `ROLE_ADMIN`, whereas the JWT converter may map the scope to `SCOPE_admin`. Check the actual naming/mapping.

**Q14.** If a service has `@PreAuthorize("hasAuthority('file:read')")`, can a user read every file?

**Answer:** No. Object-level, tenant, and owner permissions still must be checked.

**Q15.** At the method layer, can someone reach the body of `@PreAuthorize("denyAll")` via a call inside the same bean?

**Answer:** If self-invocation bypasses the proxy there is a risk, because the interceptor does not run. Do not treat the annotation as the sole barrier if the architecture does not guarantee enforcement.

**Q16.** When should a policy bean be used in SpEL?

**Answer:** When conditions depend on parameters, resources, tenants, state, or reusable logic; do not cram excessive SQL/logic into the annotation.

**Conclusion:** `@PreAuthorize` combined with SpEL expresses pre-method policies clearly: **roles**, **authorities**, **authentication states**, and **domain conditions**. To use it safely, you must understand the `ROLE_` prefix, the difference between authenticated and fully authenticated, true authority sources, AOP proxy mechanics, method parameters, independent HTTP/CSRF layers, and per-resource permissions. Always test both **allowed** and **denied** cases with appropriate principals, not only happy-path admin cases.

## Official references

- Spring Security — Method Security, @PreAuthorize, SpEL, expression root, method parameters, RoleHierarchy, proxies: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 7.0 — Method Security: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- Spring Security — Authorization Architecture, GrantedAuthority and role prefix: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Servlet Authentication Architecture, SecurityContextHolder and Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Anonymous Authentication and AuthenticationTrustResolver: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security — SecurityExpressionRoot Javadoc (authentication states, hasRole, permitAll): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/SecurityExpressionRoot.html
- Spring Security — AuthenticationTrustResolver Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html
- Spring Security — Role hierarchy and expression handler: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html#authz-hierarchical-roles
- Spring Security — HTTP request authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Spring MVC/MockMvc test: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — Method security test annotations: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework — Spring Expression Language reference: https://docs.spring.io/spring-framework/reference/core/expressions.html
