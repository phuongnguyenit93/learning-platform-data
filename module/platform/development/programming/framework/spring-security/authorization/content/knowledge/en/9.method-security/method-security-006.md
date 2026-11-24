# `@RolesAllowed`, `@PermitAll`, `@DenyAll`, and JSR-250 Semantics in Spring Security

## 1. Objective: Three Short Annotations with Distinct Security Boundaries

A Java application using Spring Security wants to declare permissions on services without relying on SpEL syntax. The team has these operations:

- `listPublicNews()`: publish public content.
- `viewDashboard()`: `USER` role only.
- `reviewSubmission()`: `REVIEWER` **or** `ADMIN` role.
- `deleteUser()`: `ADMIN` role only, plus tenant and management-scope checks.
- `obsoleteDangerousOperation()`: completely locked during a business migration.

Java/Jakarta provides the JSR-250 / Jakarta Common Annotations set for situations like these:

```java
@RolesAllowed("ADMIN")                 // requires the allowed role
@RolesAllowed({"REVIEWER", "ADMIN"})   // any of the listed roles
@PermitAll                              // requires no role at the JSR-250 layer
@DenyAll                                // denies all roles at the JSR-250 layer
```

Spring Security can enforce them on Spring-managed beans **when JSR-250 method security is enabled**. However, placing an annotation does not automatically protect every request: HTTP filters, the security context, AOP proxies, role prefixes, and per-resource permissions remain independent parts of the design.

This lesson helps you:

1. Understand `@RolesAllowed`, `@PermitAll`, and `@DenyAll` accurately according to Jakarta/JSR-250 semantics.
2. Enable `@EnableMethodSecurity(jsr250Enabled = true)` and use the `jakarta.annotation.security` package in Spring Boot 3+/Spring Security 6+/7.
3. Distinguish role names from real `GrantedAuthority` strings and the `ROLE_` prefix.
4. Determine how annotations at the **class** and **method** levels interact.
5. Avoid confusing `@PermitAll` with HTTP `permitAll()`, and avoid using it to bypass CSRF, authentication, or other advisors.
6. Test with `@WithMockUser`, `@WithAnonymousUser`, `MockMvc`, and negative cases.
7. Recognize limitations: no SpEL for object-level authorization, self-invocation, asynchronous calls, conflicting annotations, stale authorities, and multiple filter chains.
8. Choose among JSR-250, `@Secured`, and `@PreAuthorize` based on policy complexity.

**Scope:** Spring Security Servlet/Spring MVC, Java 17+, JUnit 5, Spring Security Test. Snippets containing business type names are **integration fragments**; the standalone Java 17 example in section 13 simulates policy rules and is explicitly noted as not a Spring implementation.

## 2. What Is JSR-250? How Do Jakarta and `javax` Relate?

### 2.1. Origins and Packages

JSR-250 is *Common Annotations for the Java Platform*. In older Java EE ecosystems, security annotations were typically imported from:

```java
// Used in some legacy Java EE/Spring projects:
import javax.annotation.security.RolesAllowed;
import javax.annotation.security.PermitAll;
import javax.annotation.security.DenyAll;
```

After Jakarta EE changed namespaces, Spring Framework 6+/Spring Boot 3+/Spring Security 6+ applications use:

```java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
```

Do not confuse them with `jakarta.ws.rs` or `org.springframework.security.access.annotation.Secured`. Similar names are defined by different APIs.

**Java 17 does not automatically provide the entire Jakarta Annotations API just because the JDK is installed.** In a Spring Boot project, the dependency may be managed transitively; if the compiler reports `package jakarta.annotation.security does not exist`, inspect the dependency graph and add `jakarta.annotation-api` compatible with the BOM. Do not revert to `javax.annotation.security` to fix compile errors in a Spring 6/7 project.

### 2.2. They Are Metadata; Spring Security Decides Execution

The annotation:

```java
@RolesAllowed("ADMIN")
public void deleteUser(String id) { ... }
```

merely marks metadata in source code. If method security is not enabled or the invocation does not pass through the matching interceptor, the annotation **does not automatically check** `Authentication`. You cannot conclude a method is protected simply because the annotation shows up in an IDE.

Modern Spring Security uses `Jsr250AuthorizationManager` together with a method interceptor to evaluate `@RolesAllowed`/`@PermitAll`/`@DenyAll` when JSR-250 configuration is enabled. This mechanism belongs to **method security**, distinct from `SecurityFilterChain` protecting HTTP-level requests.

### 2.3. Declaration Locations

These Jakarta annotations have `@Target({TYPE, METHOD})` and `@Retention(RUNTIME)`:

- Placed on a **class**: establishes the default policy for methods in the class.
- Placed on a **method**: applies to the specific method and can override the class-level JSR-250 policy per specification rules.
- Placed on an **interface/service method**: Spring Security supports interface annotations in compatible method proxy configurations, though you must test with the real proxy, especially when multiple interfaces carry conflicting policies.

These annotations are not meant for *fields* or *method parameters*. For rules checking parameters/return values, use `@PreAuthorize`, `@PostAuthorize`, custom beans/policies, or other suitable mechanisms.

## 3. Semantics of `@RolesAllowed`

### 3.1. Single Role

```java
@RolesAllowed("ADMIN")
public String readAdminDashboard() {
    return "admin";
}
```

In Spring Security with the default prefix, `@RolesAllowed("ADMIN")` typically requires a `GrantedAuthority` with the string `ROLE_ADMIN`. A user with `ROLE_USER` fails; a user with `ROLE_ADMIN` can pass the **JSR-250 check**, provided no other rule denies it.

`@RolesAllowed("ADMIN")` does not automatically check the target user ID, tenant, target account status, or rules like "view only documents I own". It expresses only a role condition at method invocation time.

### 3.2. Multiple Roles Use OR, Not AND

```java
@RolesAllowed({"REVIEWER", "ADMIN"})
public String reviewSubmission(String id) {
    return "review-" + id;
}
```

A role list means **having any one of the allowed roles**:

```text
ROLE_REVIEWER -> passes the role condition
ROLE_ADMIN    -> passes the role condition
ROLE_USER     -> fails the role condition
```

Having both `REVIEWER` and `ADMIN` at the same time is not required. If business rules require **two permissions simultaneously**, e.g., `report:review` **and** `report:export`, `@RolesAllowed({"REVIEWER", "EXPORTER"})` is **not** an AND operation. Use `@PreAuthorize` with an AND expression or a domain authorization manager/policy bean.

### 3.3. Role Name vs Actual Authority String

Distinguish clearly:

| Annotation | Default Authority Application Must Grant | Note |
| --- | --- | --- |
| `@RolesAllowed("USER")` | `ROLE_USER` | `USER` role |
| `@RolesAllowed("ADMIN")` | `ROLE_ADMIN` | `ADMIN` role |
| `@RolesAllowed({"ADMIN", "AUDITOR"})` | `ROLE_ADMIN` **or** `ROLE_AUDITOR` | Either one |
| `@PreAuthorize("hasAuthority('report:read')")` | `report:read` | Exact permission, no automatic prefix |
| `@PreAuthorize("hasRole('ADMIN')")` | `ROLE_ADMIN` by convention | Spring expression, different from JSR-250 annotation |

`@RolesAllowed("ADMIN")` is intuitive when the application follows the `ROLE_` prefix standard. Do not mix `ADMIN`, `ROLE_ADMIN`, `SCOPE_admin`, and `admin:read` assuming they are synonymous; they are distinct strings unless explicitly mapped.

### 3.4. The `ROLE_` Prefix Can Be Customized

`Jsr250AuthorizationManager` provides `setRolePrefix(String)`, defaulting to `ROLE_`. A legacy project might change the prefix or grant roles using another convention. When doing so, keep consistency across:

- The source of `Authentication.getAuthorities()`.
- JSR-250 method rules.
- HTTP `hasRole`/`hasAuthority`.
- `@Secured`/`@PreAuthorize` and role hierarchies if used together.
- JWT/OAuth converters, user directories, and test fixtures.

Do not assume changing `GrantedAuthorityDefaults` or one bean automatically updates **every** custom authorization manager in every Spring Security version. Read the JavaDoc for your resolved dependency and test both HTTP and method paths.

## 4. Semantics of `@PermitAll`

### 4.1. No Role Required at the JSR-250 Checkpoint

```java
@PermitAll
public String publicCatalog() {
    return "public catalog";
}
```

`@PermitAll` states that the method requires no specific role **under JSR-250 policy**. In a proper method security configuration, even a principal without special roles can pass the JSR-250 interceptor for this method.

However, it does **not** mean "bypass every security layer of the application". If an HTTP filter requires role `ADMIN` for `GET /api/catalog`, a guest's request is still blocked before the controller calls the service, even though the service method has `@PermitAll`.

### 4.2. `@PermitAll` Is Not HTTP `permitAll()`

Compare:

```java
// SecurityFilterChain rule (HTTP)
.requestMatchers(HttpMethod.GET, "/api/catalog").permitAll()
```

and:

```java
// Method security rule (service)
@PermitAll
public List<CatalogItem> publicCatalog() { ... }
```

The first rule applies to the **HTTP request**. The second annotation applies to the **method invocation** via the interceptor. They often work together when exposing a public API, but do not replace each other.

Example:

| HTTP rule | Method annotation | Guest GET to endpoint | Conclusion |
| --- | --- | --- | --- |
| `permitAll()` | `@PermitAll` | May enter controller/service | Other layers may still handle/deny |
| `authenticated()` | `@PermitAll` | Blocked if unauthenticated | Method-level public does not drop HTTP rule |
| `hasRole("ADMIN")` | `@PermitAll` | Blocked if not admin | HTTP is stricter on that request path |
| `permitAll()` | `@RolesAllowed("ADMIN")` | May pass HTTP but denied at service | Method rule remains in effect |
| `permitAll()` | `@DenyAll` | May pass HTTP but denied at service | `@DenyAll` blocks invocation |

"May" is the key word: the application still has `CsrfFilter`, other security advisors, validation, and domain policies.

### 4.3. `@PermitAll` Does Not Disable CSRF

For a state-changing method:

```java
@PermitAll
public String submitFeedback(String text) { ... }
```

if it is invoked from `POST /api/feedback` in a session/cookie application with CSRF protection, the request can be rejected for lacking a CSRF token even though JSR-250 permits the method. `@PermitAll` does not disable `CsrfFilter`, bypass rate limits, or validate input trustworthiness.

### 4.4. `@PermitAll` Does Not Bypass Other Advisors

If a method carries both:

```java
@PermitAll
@PreAuthorize("hasAuthority('report:read')")
public String readReport() { ... }
```

and both JSR-250 and pre/post method security are enabled, the method-security checks run independently through their interceptors; `@PermitAll` **does not turn `@PreAuthorize` into allow**. Simply put, all active conditions must allow the method to execute.

Avoid placing multiple different policy annotation types on a single method unless **it is an intentional AND** and has been tested; code reviewers can easily miss it by seeing `@PermitAll` and assuming the method is public.

## 5. Semantics of `@DenyAll`

### 5.1. Denies at the JSR-250 Method-Security Checkpoint

```java
@DenyAll
public String deprecatedAdministrationOperation() {
    return "should not execute";
}
```

When JSR-250 method security is active and the invocation goes through the interceptor, `@DenyAll` denies even a principal holding `ROLE_ADMIN` or broad permissions. It is a useful **method-level barrier** when retiring dangerous functionality, temporarily locking a use case, or defensively guarding an unused method.

It does not automatically remove the endpoint, delete the method implementation, or guarantee that a call **bypassing the proxy** cannot execute. For truly forbidden actions, **remove call paths** from the API, disable feature flags, or delete unnecessary code rather than relying solely on an annotation.

### 5.2. `@DenyAll` Is Not HTTP `denyAll()`

```java
.requestMatchers("/api/internal/**").denyAll()
```

forbids HTTP requests matching the rule. `@DenyAll` forbids method invocations seen by the JSR-250 interceptor. A background job can call the service without passing through HTTP filters, making method-level protection valuable; however, if the job calls the raw object/`this` method bypassing the AOP proxy, the annotation can also be rendered ineffective.

### 5.3. Do Not Treat `@DenyAll` as State-Based Authorization

"Feature under maintenance" or "locked account" may require dynamic policy evaluation. `@DenyAll` is a static annotation decision and does not check runtime maintenance state. To allow access dynamically when approved or toggled by feature flags, use rules with clear business semantics instead of editing annotations outside the deploy cycle.

### 5.4. Test Side Effects, Not Just Exceptions

Tests should verify the method is blocked **before** writing data or emitting events. If calling a `@DenyAll` method throws `AccessDeniedException`, also verify database rows, message queues, business audit actions, or counters remain unchanged.

Note that custom authorization-denied handlers in some newer Spring Security versions can convert an exception into an alternate response/value; if the project enables them, test that exact contract. By default, calls are denied with an exception before running the body.

## 6. Explicitly Enabling JSR-250 Method Security

### 6.1. Configuration in Modern Spring Security

Create a Spring `@Configuration` class:

```java
package com.example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(jsr250Enabled = true)
public class MethodSecurityConfig {
}
```

From `@EnableMethodSecurity`, Spring Security registers method-security advisors. `jsr250Enabled = true` explicitly opts into support for `@RolesAllowed`, `@PermitAll`, and `@DenyAll`; in modern Spring Security configurations, JSR-250 **is not enabled automatically just by having `spring-boot-starter-security`**. Support for `@PreAuthorize`/`@PostAuthorize` is typically enabled by default when `@EnableMethodSecurity` is active, whereas `@Secured` needs `securedEnabled = true` if used.

Do not mix new `@EnableMethodSecurity` calls with legacy `@EnableGlobalMethodSecurity` docs in the same module without understanding migration: `@EnableGlobalMethodSecurity` is the legacy/deprecated configuration path.

### 6.2. Required Dependencies and Imports

In Spring Boot 3+/Spring 6+/Security 6+ projects, use:

```java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
```

If the build lacks the Jakarta annotations dependency, the project needs `jakarta.annotation:jakarta.annotation-api` at a compatible version. Maven **fragment** example, normally version-managed by the Spring Boot BOM:

```xml
<dependency>
    <groupId>jakarta.annotation</groupId>
    <artifactId>jakarta.annotation-api</artifactId>
</dependency>
```

Add it only if the dependency is not already present. Do not pin arbitrary versions against the application's dependency management. With Spring Boot 2/older Spring Security, package and annotation migration needs its own plan; never replace `javax` with `jakarta` across the project without upgrading Spring Framework accordingly.

### 6.3. Method Security Applies Only to Managed Beans/Proxies

`@EnableMethodSecurity` uses Spring AOP interceptors by default. Therefore:

- The class/method must be Spring-managed and the advice must see the invocation.
- Calls through a bean proxy from another bean are normally checked.
- `this.someSecuredMethod()` self-calls within the same object usually **bypass the proxy**.
- `private`/`final`/non-proxyable methods are not reliable method security boundaries.
- Methods without a security annotation are not automatically denied by method security; explicit HTTP/service fallback rules are required.
- If using AspectJ mode, weaving semantics differ and require separate configuration/testing.

**Implementation principle:** place method authorization at the **public service boundary** and test using real Spring-managed beans. Controller authentication does not replace service protection when use cases are also called from scheduled jobs, message listeners, or other APIs.

## 7. Complete Configuration and Service Example at the Spring Layer

### 7.1. Demo Service with Class- and Method-Level Policies

Create `PolicyService.java` in package `com.example.security`. This **class compiles when the project has Jakarta Annotations + Spring Context + Spring Security method configuration**:

```java
package com.example.security;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import org.springframework.stereotype.Service;

@Service
@RolesAllowed("USER")
public class PolicyService {

    private final AtomicInteger deniedBodyCalls = new AtomicInteger();

    // Method overrides class-level USER rule with PermitAll.
    @PermitAll
    public String publicNotice() {
        return "public";
    }

    // Inherits class-level rule: requires role USER.
    public String privateDashboard() {
        return "dashboard";
    }

    // Overrides class-level USER rule: EDITOR or ADMIN.
    @RolesAllowed({"EDITOR", "ADMIN"})
    public String editDraft() {
        return "edited";
    }

    // Never invoke the body through the JSR-250 interceptor.
    @DenyAll
    public String disabledOperation() {
        deniedBodyCalls.incrementAndGet();
        return "disabled-body-ran";
    }

    // Test-only: reads counter without requiring a role.
    @PermitAll
    public int disabledBodyCallCount() {
        return deniedBodyCalls.get();
    }
}
```

Meaning:

1. At the class level, `@RolesAllowed("USER")` is the default policy for methods without their own JSR-250 annotation.
2. `publicNotice` has `@PermitAll`: in JSR-250, the method-level declaration replaces the class rule for this method.
3. `privateDashboard` has no separate annotation: requires `ROLE_USER`.
4. `editDraft` has `@RolesAllowed({"EDITOR","ADMIN"})`: role EDITOR **or** ADMIN, **not automatically requiring USER as well** because the JSR-250 policy was overridden. If business rules require ADMIN to also hold USER and EDITOR, express that in an explicit policy rather than inferring it from the class.
5. `disabledOperation` has `@DenyAll`: the body must never execute when the method interceptor is active.
6. `disabledBodyCallCount` helps tests confirm no side effects occur on denial.

**Caution:** if the application has other advisors, interface annotations, custom AOP, or role hierarchies, those can also affect results. When conflicts or overrides exist, do not guess by reading a single annotation in isolation; test with the real proxy/context.

### 7.2. HTTP Configuration for That Service

Suppose a REST controller calls `PolicyService`. HTTP configuration fragment:

```java
http.authorizeHttpRequests(auth -> auth
        // Explicit public route, do not open every API with a wildcard.
        .requestMatchers(HttpMethod.GET, "/api/notices").permitAll()
        .requestMatchers("/api/dashboard/**").authenticated()
        .requestMatchers("/api/drafts/**").authenticated()
        .requestMatchers("/api/internal/**").denyAll()
        .anyRequest().denyAll()
);
```

This is a **Spring Security Servlet fragment**, not a standalone class. It illustrates defense in depth: HTTP routes are categorized, and the service also enforces JSR-250 role policies. If a route is public while the service has `@RolesAllowed("ADMIN")`, callers lacking the role are still denied at the service; if the service has `@PermitAll` while the HTTP route requires auth, guests still do not pass the HTTP rule.

POST/PATCH routes must handle CSRF properly in session/cookie apps. Permissions on specific resources (tenant, owner, draft status) cannot be inferred solely from URLs or JSR-250 roles.

## 8. Class-Level vs Method-Level: Override Rules and Conflicts

### 8.1. Class-Level Defaults

```java
@RolesAllowed("USER")
public class AccountService {

    public String profile() {
        return "profile";
    }

    @RolesAllowed("ADMIN")
    public String lockAccount() {
        return "locked";
    }

    @PermitAll
    public String systemStatus() {
        return "up";
    }

    @DenyAll
    public String legacyDanger() {
        return "forbidden";
    }
}
```

Under Jakarta annotations semantics, a method-level policy **overrides** the class-level role policy within the same JSR-250 group:

| Method | Effective JSR-250 Rule | Must Not Be Assumed |
| --- | --- | --- |
| `profile` | USER | ADMIN does not automatically substitute for USER without hierarchy/direct role |
| `lockAccount` | ADMIN | Does not automatically require both USER and ADMIN |
| `systemStatus` | PermitAll | Does not require USER at the JSR-250 layer |
| `legacyDanger` | DenyAll | Nobody passes the JSR-250 interceptor |

**However:** do not apply this "overrides class" rule as a universal rule across **different kinds of method security annotations**. For example, if a class has `@PreAuthorize(...)` and a method has `@PermitAll`, both the pre/post advisor and the JSR-250 advisor may participate; in that case `@PermitAll` does not cancel `@PreAuthorize`'s condition.

### 8.2. Do Not Place Conflicting JSR-250 Annotations on the Same Method

Avoid:

```java
// Anti-pattern: two conflicting policy declarations.
@PermitAll
@DenyAll
public String ambiguousMethod() {
    return "ambiguous";
}
```

An auditable pattern is **one clear JSR-250 access policy per method**. If you want to combine complex conditions, move to `@PreAuthorize`/a policy bean rather than relying on precedence that is insufficiently documented or tested in your project.

With annotations inherited from multiple interfaces, Spring Security may reject conflicting configurations. Place the rule on the concrete method to remove ambiguity, and test application startup/invocation.

### 8.3. A Broad Class-Level `@PermitAll`

```java
@PermitAll
public class SharedService {
    public String publicRead() { return "public"; }
    public String privateRead() { return "sensitive"; }
}
```

Without a separate method policy and with JSR-250 enabled, both methods are treated as public **at the JSR-250 layer**. This is a trap when adding a new method to a class previously marked public. Prefer placing `@PermitAll` on **truly public methods**, or manage the class strictly as a public-only service with clear boundaries.

### 8.4. Interface Annotations and Inheritance Conflicts

Annotations can be placed on service interfaces, yet when an implementation inherits **two interfaces** carrying different security annotations for the same method, Spring Security has no unambiguous way to prioritize. Documentation recommends adding an explicit annotation on the **concrete method** to resolve it.

During implementation:

- Avoid repeating conflicting permission definitions across interfaces/classes/methods.
- Test public methods through interface proxies and class proxies per your real setup.
- If controllers/services depend on interfaces, ensure AOP intercepts the exact invoked method.
- Do not assume interface annotations are inherited via Java reflection the same way as classes; Spring has its own lookup, and testing is the best proof.

## 9. JSR-250, `@Secured`, and `@PreAuthorize`: Choosing the Right API

| Capability | `@RolesAllowed` | `@Secured` | `@PreAuthorize` |
| --- | --- | --- | --- |
| Annotation source | Jakarta Common Annotations/JSR-250 | Spring Security | Spring Security |
| Enable flag | `jsr250Enabled = true` | `securedEnabled = true` | Enabled by default with `@EnableMethodSecurity` |
| Express roles | Yes | Yes | Yes via SpEL |
| OR role list | Yes | Yes | Yes via `hasAnyRole` |
| Check literal permissions | Via matching authority/prefix config, though JSR-250 targets roles | Passes authority strings per API | Explicit `hasAuthority` |
| AND multiple conditions | Cannot express directly as a list | Cannot express directly as a list | Yes, using `and`/`&&` in SpEL |
| Parameter-based owner/tenant checks | Not directly | Not directly | Can call policy beans with parameters |
| Check return value | No | No | Commonly uses `@PostAuthorize` |
| Annotation portability | Standardized via Jakarta | Spring-specific | Spring-specific |
| Flexibility | Simple | Simple | High |

**Selection guidelines:**

- Stable role-only rules using Jakarta annotations in a module: `@RolesAllowed`.
- Clearly public/disabled methods: `@PermitAll`/`@DenyAll` when JSR-250 is already enabled.
- Rules needing specific permissions, multiple conditions, tenant/owner, or parameters: `@PreAuthorize` calling a policy bean is usually easier to express and test.
- `@Secured` often appears in older codebases; no need to rewrite to JSR-250 merely because the annotation names look similar.

Spring Security docs describe `@PreAuthorize` as more expressive than JSR-250 and generally recommend it for complex logic.

### 9.1. `@RolesAllowed` Does Not Support SpEL

Incorrect:

```java
@RolesAllowed("hasAuthority('report:approve')")
public String approve() { return "approved"; }
```

In JSR-250, that string is interpreted as a **role name**, not a SpEL expression. If you need a permission-based check:

```java
@PreAuthorize("hasAuthority('report:approve')")
public String approve() { return "approved"; }
```

Or if owner checks are also needed:

```java
@PreAuthorize(
        "hasAuthority('report:approve') and " +
        "@reportPolicy.mayApprove(authentication, #reportId)"
)
public void approve(String reportId) {
    reportService.approve(reportId);
}
```

`reportPolicy` is an **application-defined bean** and the parameter name `#reportId` must be discoverable by Spring Security (e.g., compiled with `-parameters`). The example is a fragment, not a standalone runnable program. Method/domain checks must operate at a boundary with trustworthy resource data.

## 10. `RoleHierarchy`, Implied Authorities, and JSR-250

### 10.1. Direct Authorities Do Not Automatically Contain Implied Authorities

Suppose:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
```

A user holds only direct `ROLE_ADMIN`. When a JSR-250 authorization manager **is configured to use `RoleHierarchy`**, it can treat ADMIN as having permissions equivalent to USER through the graph. Still, `Authentication.getAuthorities()` may contain only `ROLE_ADMIN`.

### 10.2. Verify Configuration on the Exact Authorization Consumer

Spring Security supports role hierarchies for JSR-250 methods via `Jsr250AuthorizationManager` and related configuration mechanisms, though auto-wiring levels and APIs vary by version and must be verified. **Do not treat creating a `RoleHierarchy` bean as proof that every custom manager in the project uses the graph.**

Example hierarchy:

```java
@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.fromHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_USER
            """);
}
```

This is a configuration fragment; it requires imports for `@Bean`, `RoleHierarchy`, and `RoleHierarchyImpl`. Testing:

- `@RolesAllowed("USER")`: direct USER is allowed.
- `@RolesAllowed("USER")`: ADMIN **holding only direct `ROLE_ADMIN`** is allowed **if** the JSR-250 manager has integrated the hierarchy.
- Without hierarchy / manager not using hierarchy: ADMIN can be denied on a method requiring USER.
- USER does not infer upward to ADMIN.
- Any graph change must be tested at the **actual consuming manager**, not merely unit-testing graph closure.

### 10.3. Do Not Add Hierarchy Edges to Mask Naming Convention Bugs

If role `ROLE_MANAGER` and permission `report:read` are two different authority concepts, do not assume every manager automatically has `report:read`. Only imply authorities when the graph expresses an explicit relationship and the authorization point actually evaluates the graph. Wrong edges can grant excessive privileges to higher roles via transitive closure.

### 10.4. `RoleHierarchy` Does Not Replace Object-Scope Checks

`@RolesAllowed("MANAGER")` does not guarantee a manager in tenant A can edit only users in tenant A. Even with a hierarchy, the service must verify:

```text
role allows entering function
AND target.tenantId == principal.tenantId
AND target.status permits action
AND separation-of-duties policy is satisfied
```

That is a **pseudo-policy**; implement it using service queries/policy beans backed by trustworthy data sources, never trusting client-declared tenant IDs without verification.

## 11. JSR-250 and the HTTP Layer: Do Not Use Annotations to Expose APIs

### 11.1. Defense in Depth

For endpoints:

```text
GET /api/public/catalog        -> public
GET /api/admin/users           -> ADMIN
POST /api/admin/users          -> ADMIN + user-creation business logic
POST /api/accounts/u7/disable  -> ADMIN + same-tenant policy
```

HTTP `authorizeHttpRequests` and method security can work together:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/public/catalog")
            .permitAll()
        .requestMatchers("/api/admin/**")
            .hasRole("ADMIN")
        .requestMatchers(HttpMethod.POST, "/api/accounts/*/disable")
            .authenticated()
        .anyRequest().denyAll()
);
```

In the service:

```java
@RolesAllowed("ADMIN")
public void disableAccount(String accountId) {
    accountPolicy.requireCanDisableCurrentUserTarget(accountId);
    repository.disable(accountId);
}
```

Both snippets above are **fragments** in a project. With the service method having an ADMIN rule and an object policy, the user must pass the HTTP matcher (if entering via HTTP), pass the JSR-250 role rule, and still be permitted on the target account.

### 11.2. `@PermitAll` Can Be Public in Java Yet Not Public from a Browser

A message consumer/service bean can call `@PermitAll` because no principal is required; yet an API reaching it over HTTP still depends on the filter chain. Conversely, `@RolesAllowed` can block a service invocation from a scheduler even though the scheduler does not go through HTTP. The method layer protects logic **where it is used**, without replacing request-ingress protection.

### 11.3. Anonymous, 401, 403, and Redirects

- A guest hitting an HTTP route requiring authentication is normally routed to the authentication entry point (e.g., 401 JSON or login redirect).
- An authenticated user lacking the role is normally denied (e.g., 403).
- Directly calling a JSR-250-denied method through a Spring proxy normally throws `AccessDeniedException`, rather than returning an HTTP status by itself.
- HTTP `ExceptionTranslationFilter` and web exception handling can translate exceptions into appropriate responses.
- `@PermitAll` on a service does not automatically produce `200 OK`; the method can still throw domain errors or the controller can return another status.

Never write a test that only observes `403` and concludes JSR-250 was the blocker: 403 can come from CSRF, HTTP authorization, or domain policy.

## 12. Spring Security Test: Verifying Annotations on the Proxy

### 12.1. `@WithMockUser` Grants Roles and Authorities Differently

Example:

```java
@WithMockUser(roles = "ADMIN")
```

normally creates a test principal with authority `ROLE_ADMIN`. That differs from:

```java
@WithMockUser(authorities = "ADMIN")
```

because the second form grants the exact string `ADMIN` without adding a prefix. With `Jsr250AuthorizationManager`'s default prefix, `@RolesAllowed("ADMIN")` is not satisfied solely by an unmapped `ADMIN` authority.

Test both the **correct prefix** and **wrong prefix** to catch mismatches between the authentication provider and method-security configuration.

### 12.2. Testing the Service in an Application Context

This is a JUnit 5 + AssertJ + Spring Security Test fragment; it requires `@SpringBootTest` or `@SpringJUnitConfig` and injecting the proxied `PolicyService` bean:

```java
@Autowired
PolicyService service;

@Test
@WithAnonymousUser
void anonymousCanCallPermitAllMethod() {
    assertThat(service.publicNotice()).isEqualTo("public");
}

@Test
@WithMockUser(roles = "USER")
void userCanCallClassLevelMethod() {
    assertThat(service.privateDashboard()).isEqualTo("dashboard");
}

@Test
@WithMockUser(roles = "ADMIN")
void adminCanCallMethodLevelOverride() {
    assertThat(service.editDraft()).isEqualTo("edited");
}

@Test
@WithMockUser(roles = "USER")
void userCannotEditDraft() {
    assertThatThrownBy(() -> service.editDraft())
        .isInstanceOf(AccessDeniedException.class);
}

@Test
@WithMockUser(roles = "ADMIN")
void adminIsDeniedWhenDenyAll() {
    int before = service.disabledBodyCallCount();

    assertThatThrownBy(() -> service.disabledOperation())
        .isInstanceOf(AccessDeniedException.class);

    assertThat(service.disabledBodyCallCount()).isEqualTo(before);
}
```

Purpose of each test:

1. Method `@PermitAll` overrides class-level `USER` at the JSR-250 layer.
2. Method without its own annotation inherits class-level `USER`.
3. `ADMIN` can enter method-level `@RolesAllowed({"EDITOR","ADMIN"})`.
4. `USER` is not granted `EDITOR`/`ADMIN` access just because the class carries `USER`.
5. `@DenyAll` does not execute the body, even for `ADMIN`.

### 12.3. Also Test the Misconfiguration Where JSR-250 Is Disabled

A test that only checks `publicNotice` succeeds **does not** prove the interceptor works, because a public method will run even when JSR-250 is turned off. The critical test must assert a **negative case**:

```java
@Test
@WithMockUser(roles = "USER")
void denyAllReallyBlocksExecution() {
    assertThatThrownBy(() -> service.disabledOperation())
        .isInstanceOf(AccessDeniedException.class);
}
```

If `jsr250Enabled = false` or the call bypasses the proxy, the body can run and the test fails. This is a useful "canary" test for method security setup.

### 12.4. Testing OR Roles

With:

```java
@RolesAllowed({"EDITOR", "ADMIN"})
public String editDraft() { return "edited"; }
```

matrix:

| Test Direct Authorities | Expected |
| --- | --- |
| `ROLE_EDITOR` | ALLOW |
| `ROLE_ADMIN` | ALLOW |
| `ROLE_USER` | DENY |
| `ROLE_REVIEWER` | DENY |
| `ROLE_EDITOR` + `ROLE_ADMIN` | ALLOW (though having both is not required) |
| Unprefixed `EDITOR` | DENY under default convention |
| Anonymous | Must not rely on non-existent roles |

### 12.5. `@WithAnonymousUser` Does Not Replace End-to-End HTTP Authentication

A service test called through the proxy under `@WithAnonymousUser` can verify JSR-250 `@PermitAll`, but does not prove `GET /api/public/catalog` is open from the internet if `SecurityFilterChain` is misconfigured. Add MockMvc or HTTP integration tests and check the right chain.

## 13. Standalone Java 17: Simulating Exact Class and Method Annotation Semantics

To understand precedence without Spring dependencies, the program below uses **custom demo annotations**. It does not use real `jakarta.annotation.security` classes; the goal is simulating the three rules and how method-level overrides class-level. In real implementations, you must use `jakarta.annotation.security` and Spring interceptors.

Create `Jsr250PolicyConceptDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Set;

public class Jsr250PolicyConceptDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface DemoRolesAllowed {
        String[] value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface DemoPermitAll {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface DemoDenyAll {}

    @DemoRolesAllowed({"USER"})
    static class ExampleService {

        String dashboard() {
            return "dashboard";
        }

        @DemoPermitAll
        String publicNews() {
            return "news";
        }

        @DemoRolesAllowed({"EDITOR", "ADMIN"})
        String edit() {
            return "edit";
        }

        @DemoDenyAll
        String disabled() {
            return "disabled";
        }
    }

    static boolean allowed(
            Class<?> serviceType,
            String methodName,
            Set<String> granted) throws ReflectiveOperationException {

        Method method = serviceType.getDeclaredMethod(methodName);

        // Use METHOD annotation if the method has a rule; otherwise
        // fall back to CLASS policy, simulating JSR-250 override.
        if (method.isAnnotationPresent(DemoDenyAll.class)) {
            return false;
        }
        if (method.isAnnotationPresent(DemoPermitAll.class)) {
            return true;
        }
        DemoRolesAllowed roles =
                method.getAnnotation(DemoRolesAllowed.class);

        if (roles == null) {
            if (serviceType.isAnnotationPresent(DemoDenyAll.class)) {
                return false;
            }
            if (serviceType.isAnnotationPresent(DemoPermitAll.class)) {
                return true;
            }
            roles = serviceType.getAnnotation(DemoRolesAllowed.class);
        }

        // Demo uses deny-by-default when completely unannotated;
        // real Spring does NOT automatically deny all unannotated methods.
        if (roles == null || granted == null) {
            return false;
        }

        for (String role : roles.value()) {
            if (granted.contains("ROLE_" + role)) {
                return true;  // ANY role is sufficient.
            }
        }
        return false;
    }

    static void print(
            String label,
            String method,
            Set<String> granted) throws ReflectiveOperationException {
        System.out.println(label + "="
                + (allowed(ExampleService.class, method, granted)
                    ? "ALLOW" : "DENY"));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Set<String> guest = Set.of();
        Set<String> user = Set.of("ROLE_USER");
        Set<String> editor = Set.of("ROLE_EDITOR");
        Set<String> admin = Set.of("ROLE_ADMIN");
        Set<String> unprefixed = Set.of("ADMIN");

        print("guest-news", "publicNews", guest);
        print("guest-dashboard", "dashboard", guest);
        print("user-dashboard", "dashboard", user);
        print("admin-dashboard", "dashboard", admin);
        print("user-edit", "edit", user);
        print("editor-edit", "edit", editor);
        print("admin-edit", "edit", admin);
        print("unprefixed-edit", "edit", unprefixed);
        print("user-disabled", "disabled", user);
        print("admin-disabled", "disabled", admin);
    }
}
```

JDK 17+ commands:

```bash
javac Jsr250PolicyConceptDemo.java
java Jsr250PolicyConceptDemo
```

Stdout per demo logic:

```text
guest-news=ALLOW
guest-dashboard=DENY
user-dashboard=ALLOW
admin-dashboard=DENY
user-edit=DENY
editor-edit=ALLOW
admin-edit=ALLOW
unprefixed-edit=DENY
user-disabled=DENY
admin-disabled=DENY
```

**Interpreting the results:**

- Guest enters `publicNews` because the method rule is `PermitAll`, even though the class has `USER`.
- `dashboard` has no separate annotation, so it takes the `USER` rule from the class.
- `ADMIN` is **not automatically** treated as `USER` in the demo: there is no role hierarchy, and ADMIN holds only direct `ROLE_ADMIN`.
- `edit` overrides class `USER` and accepts `EDITOR` **or** `ADMIN`; a user with only `USER` is denied.
- Unprefixed authority `ADMIN` does not satisfy the illustrated `ROLE_ADMIN` convention.
- `disabled` denies even admin.

**Mandatory limitation to remember:** the demo has no Spring proxies, HTTP filters, `MethodSecurityInterceptor`, `Jsr250AuthorizationManager`, tokens, CSRF, or object policies. Furthermore, the demo chose deny-by-default when no annotation is found; Spring method security **does not automatically lock every unannotated method**. Use this example to grasp JSR-250 logic, then verify with tests in a Spring context as in section 12.

## 14. MockMvc: Combining HTTP and JSR-250 in the Right Places

Suppose a controller has:

```java
@RestController
@RequestMapping("/api")
public class NoticeController {

    private final PolicyService policy;

    public NoticeController(PolicyService policy) {
        this.policy = policy;
    }

    @GetMapping("/notices")
    public String publicNotice() {
        return policy.publicNotice();
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return policy.privateDashboard();
    }
}
```

This is a Spring Web fragment with a controller/bean in context. The route `GET /api/notices` must have HTTP `permitAll`, while `GET /api/dashboard` must have an appropriate HTTP policy. If the controller lacks a handler, `@PermitAll` will not create one.

### 14.1. Testing a Public Service While HTTP Requires a Role

If the security config accidentally contains:

```java
.requestMatchers("/api/notices").hasRole("ADMIN")
```

then a `GET /api/notices` from a guest is still blocked at HTTP. This is not a `@PermitAll` bug. For an API to truly be public, all layers must share compatible contracts.

### 14.2. Testing HTTP Statuses for the Right Reason

MockMvc fragment:

```java
@Test
void guestCanGetPublishedNotices() throws Exception {
    mockMvc.perform(get("/api/notices"))
        .andExpect(status().isOk())
        .andExpect(content().string("public"));
}

@Test
@WithMockUser(roles = "USER")
void userCanGetDashboard() throws Exception {
    mockMvc.perform(get("/api/dashboard"))
        .andExpect(status().isOk())
        .andExpect(content().string("dashboard"));
}
```

Both tests are valid only if `SecurityFilterChain` lets guests through `/api/notices`, lets `USER` through `/api/dashboard`, the controller/service return the expected content, and no extra policy blocks them. Use `@SpringBootTest` + `@AutoConfigureMockMvc` or a test slice with full security configuration imported.

Do not test only 200. Add tests where guest is denied dashboard and `USER` is denied admin. If using form login, guests may be redirected instead of 401; if using a REST entry point, it may be 401. Test according to the project's **authentication entry point**.

### 14.3. Testing POST and CSRF Separately

`@RolesAllowed("ADMIN")` on an account-deletion service does not replace CSRF protection for HTTP POST/DELETE. With MockMvc:

```java
mockMvc.perform(post("/api/admin/users/u7/disable")
        .with(user("alice").roles("ADMIN"))
        .with(csrf()))
    .andExpect(/* response per controller contract */);
```

This is a **pseudocode fragment**, as the response depends on controller, resource, state, and tenant policy. In real tests, use a concrete `ResultMatcher` (e.g., `status().isNoContent()` if the handler returns 204). Never let a missing CSRF token cause 403 and then conclude `@RolesAllowed` blocked the user.

### 14.4. Testing Non-HTTP Paths

If `PolicyService` is called from a message consumer or scheduled task, HTTP filters do not run. JSR-250 method security enforces checks if calls go through the proxy and have an appropriate `Authentication`. Never manufacture `ROLE_ADMIN` for jobs just so every method runs; design proper service identities, authorities, and auditing.

## 15. Security Limitations to Plan Ahead For

### 15.1. Self-Invocation Bypasses the Proxy

```java
@Service
public class UnsafeExample {

    public void outer() {
        inner();  // this.inner(), can bypass the AOP proxy.
    }

    @RolesAllowed("ADMIN")
    public void inner() {
        // Sensitive side effect.
    }
}
```

This is an illustrative anti-pattern. If `outer()` is called from outside, calling `inner()` directly on the same object may **not pass through the JSR-250 interceptor**, so the rule on `inner()` is not applied. Avoid treating method annotations as an absolute barrier if the architecture still permits direct internal calls.

Common fix: move sensitive use cases into another Spring-managed service, inject the bean, and call through the proxy; or structure domain policies that the service must invoke from all paths.

### 15.2. Private, Final, and Non-Spring Objects

Spring AOP has proxy limitations. Do not put `@RolesAllowed` on a `private` method expecting external callers to be blocked; nor should you instantiate `new PolicyService()` and expect Spring Security advice to run. In Java/Kotlin, `final` classes/methods require checking the proxy strategy/AspectJ. Class-level configuration is merely metadata if runtime interception does not happen.

### 15.3. Async, `@Async`, and Schedulers

Default `SecurityContextHolder` relies on `ThreadLocal`. Tasks running on a raw `Executor` or `CompletableFuture.supplyAsync` do not automatically inherit the request principal. For `@Async`, `DeferredResult`, or job queues, you need appropriate context propagation or a service identity, and you should re-evaluate permissions if sensitive actions run with delay.

`@RolesAllowed` on a service may deny calls because the worker lacks `Authentication`; **never** fix this by removing the annotation or creating a shared `ADMIN` context for every task.

### 15.4. Multi-Tenant / Owner / ACL

A user granted `ROLE_ADMIN` in tenant A is not automatically allowed to delete users in tenant B. `@RolesAllowed("ADMIN")` is only a role condition. With client-supplied IDs, the service must load trustworthy resources, verify tenant/owner/membership/status, and enforce separation-of-duties conditions.

### 15.5. Stale JWTs / Sessions / Role Hierarchies

When a user's role is revoked in the database, active JWTs or sessions may still carry old authorities. Annotations do not automatically query the DB to refresh roles. Depending on the threat model, use short token TTLs, revocation/introspection, session invalidation, or live permission checks at action time.

If `RoleHierarchy` changes, verify whether managers/handlers use the updated graph. Do not assume updating text config means every JVM instance immediately reloads policies.

### 15.6. Unannotated Methods Are Not Automatically Denied

This is the biggest limitation of method security. If a service has 20 methods and only 10 have `@RolesAllowed`, Spring Security does not automatically deny the remaining 10. You need **deny-by-default at HTTP**, code reviews of service boundaries, well-organized classes with appropriate default policies, and tests for non-HTTP call paths.

A broad class-level `@PermitAll` is even riskier: new methods can inherit a public policy. Maintain an explicit allowlist and test negative cases.

## 16. Complete Test Matrix

| Scenario | Principal | Method/Policy | Expected Outcome |
| --- | --- | --- | --- |
| Public notice | Anonymous | `@PermitAll` | ALLOW at JSR-250 |
| Public notice | `ROLE_USER` | `@PermitAll` | ALLOW |
| Dashboard | `ROLE_USER` | Class `@RolesAllowed("USER")` | ALLOW |
| Dashboard | `ROLE_ADMIN` alone | Class `@RolesAllowed("USER")` | DENY unless hierarchy/direct USER |
| Edit draft | `ROLE_EDITOR` | Method `@RolesAllowed({"EDITOR","ADMIN"})` | ALLOW |
| Edit draft | `ROLE_ADMIN` | Method `@RolesAllowed({"EDITOR","ADMIN"})` | ALLOW |
| Edit draft | `ROLE_USER` | Method `@RolesAllowed({"EDITOR","ADMIN"})` | DENY |
| Edit draft | Unprefixed `EDITOR` authority | Method `rolesAllowed` | DENY under default prefix |
| Disabled operation | Anonymous | `@DenyAll` | DENY |
| Disabled operation | `ROLE_ADMIN` | `@DenyAll` | DENY, body does not run |
| Method `@PermitAll` + `@PreAuthorize(USER)` | Anonymous | Two active advisors | DENY due to `@PreAuthorize` |
| HTTP admin route + method `PermitAll` | Guest | HTTP `hasRole` ADMIN | DENY at HTTP |
| HTTP public route + method `RolesAllowed` ADMIN | Guest | Method requires ADMIN | DENY at method |
| Unannotated method | Any | No method-security rule | Not automatically denied by JSR-250 |
| Class USER, method PermitAll | Anonymous | Method-level override | ALLOW at JSR-250 |
| Class USER, method ADMIN | `ROLE_ADMIN` | Method-level override | ALLOW at JSR-250 |
| Class USER, method ADMIN | `ROLE_USER` | Method-level override | DENY |
| Class USER, method DenyAll | `ROLE_ADMIN` | Method-level override | DENY |
| Manager with `RoleHierarchy` ADMIN→USER | `ROLE_ADMIN` | Method requires USER | May ALLOW if JSR-250 manager uses hierarchy |
| POST via session, missing CSRF | `ROLE_ADMIN` | Method has `rolesAllowed` ADMIN | May be blocked before method by CSRF |
| Service private resource in another tenant | `ROLE_ADMIN` | JSR-250 ADMIN + domain policy | DENY by object scope |
| Internal call `this.method()` | `ROLE_USER` | Method `RolesAllowed` ADMIN | Risk of proxy bypass; must redesign |
| JSR-250 disabled | `ROLE_USER` | Method `DenyAll` | Must not assume blocked; test config |
| Async worker lacking `SecurityContext` | Prior caller was ADMIN | Method `RolesAllowed` ADMIN | Does not inherit role; needs propagation/policy |

**Testing mindset:** every security rule must have at least one case that is **properly allowed**, one case that is **properly denied**, and for write operations a case confirming **no side effects occur** on denial.

### 16.1. Mandatory Pre-Deploy Tests

- [ ] `@EnableMethodSecurity(jsr250Enabled=true)` is active in the real Spring context.
- [ ] `jakarta.annotation.security.*` imports match dependencies.
- [ ] Role prefixes/authority names from authentication sources match the contract.
- [ ] Multi-role `@RolesAllowed` is OR.
- [ ] Method annotations override class JSR-250 policies where intended.
- [ ] `@PermitAll` is public only at the JSR-250 layer; HTTP still has its own rules.
- [ ] `@DenyAll` denies even `ADMIN` and the body does not run.
- [ ] No "missed" policies on new service methods.
- [ ] AOP proxy/self-invocation and non-HTTP call paths are tested.
- [ ] `RoleHierarchy` tested if used: direct roles vs inherited roles behave as intended.
- [ ] CSRF tested with POST/PATCH/DELETE where applicable.
- [ ] Tenant/owner/state tested on real resource IDs.
- [ ] Stale bearer/session claims and user role revocation tested per threat model.

## 17. Common Mistakes and Fixes

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `@RolesAllowed` blocks nobody | `jsr250Enabled=true` not enabled | Check `@EnableMethodSecurity` and `@DenyAll` canary test |
| Annotated, yet method runs via `new` | Not a Spring-managed bean | Inject bean from application context |
| Calling ADMIN method from public method still runs | Self-invocation bypasses proxy | Move to another bean or guarded boundary |
| ADMIN has `ROLE_ADMIN` yet gets 403 | Another HTTP rule, `@PreAuthorize`, tenant/CSRF, or prefix mismatch | Isolate layers, inspect authorities |
| `@RolesAllowed("ADMIN")` rejects `ADMIN` | Default `ROLE_` prefix | Grant `ROLE_ADMIN` or configure consistent prefix |
| `@RolesAllowed({"A","B"})` allows role A alone | It is OR, not AND | Use `@PreAuthorize` for AND |
| `@PermitAll`, yet HTTP still returns 401 | HTTP chain requires authentication | Adjust HTTP policy if endpoint is truly public |
| `@PermitAll` + `@PreAuthorize` still gives 403 | Two independent method-security advisors | Review dual policy, never expect PermitAll to bypass |
| `@DenyAll` does not stop proxy bypass | Internal invocation/non-Spring object | Reinforce service boundary |
| `@RolesAllowed` SpEL does not work | JSR-250 value is a role name | Use `@PreAuthorize` |
| `@WithMockUser(roles="ADMIN")` passes, production JWT fails | Converter does not emit `ROLE_ADMIN` | Test `JwtAuthenticationConverter`/IdP mapping |
| Method-level ADMIN no longer requires USER | Method policy overrides class role | Add AND rule if business requires both |
| Class `@PermitAll` exposes new method | Inherits public class policy | Put PermitAll on methods or split public service |
| 403 on POST despite valid role | Missing CSRF token or another filter | Check `CsrfFilter` and `.with(csrf())` in tests |
| Interface has two different annotations | Spring cannot disambiguate inherited annotations | Place annotation on concrete method |
| Background task lacks `Authentication` | `ThreadLocal` does not propagate automatically | Context-aware executor/service identity |
| Tests call method directly in plain unit test | No Spring AOP | Test through Spring-managed proxy |
| `RoleHierarchy` bean exists yet has no effect | Manager does not use the graph | Configure/verify JSR-250 manager for version |

### Quick Debugging Procedure

1. **Verify method security is enabled:** `@EnableMethodSecurity(jsr250Enabled=true)`.
2. **Verify proxy:** does the invocation go through a Spring bean or via `this.method`/`new`?
3. **Verify resolved annotations:** which method/class/interface holds the rule; are there conflicts?
4. **Verify `Authentication`:** do principal and `GrantedAuthority` have the right names/prefixes (without logging credentials/tokens)?
5. **Verify other layers:** HTTP matchers, CSRF, `@PreAuthorize` advisor, object policy, transactions, and error handlers.
6. **Verify behavior with pass/deny tests:** distinguish HTTP status from method exceptions/side effects.

## 18. Adoption Workflow in a Project

**Step 1 — Categorize service use cases.** Mark every method as public, role-only, permission-based, object-level, or temporarily disabled. Never leave sensitive methods unannotated by default due to time pressure.

**Step 2 — Lock role conventions.** E.g., `USER`/`EDITOR`/`ADMIN` in `@RolesAllowed`, authorities `ROLE_USER`/`ROLE_EDITOR`/`ROLE_ADMIN`; document mappers from JWT/DB and role hierarchy if any.

**Step 3 — Enable JSR-250 with the right config.** Add `@EnableMethodSecurity(jsr250Enabled = true)`; confirm Jakarta annotations resolve properly in the build.

**Step 4 — Place rules at the service boundary.** Use `@RolesAllowed` for simple roles, `@PermitAll` only on genuinely public methods, and `@DenyAll` on locked methods. Avoid broad class-wide `PermitAll`.

**Step 5 — Use other policies for deeper conditions.** Owner/tenant/permission AND, resource state, or multi-step actions should use `@PreAuthorize`/domain services instead of forcing everything into `@RolesAllowed` strings.

**Step 6 — Configure HTTP authorization separately.** Public URLs and admin URLs need explicit `SecurityFilterChain` matching and fallback deny. Never rely on JSR-250 to replace authentication entry points, CSRF, or CORS.

**Step 7 — Test proxies and negative cases.** Include `@DenyAll` canaries, wrong-role `@RolesAllowed`, class/method overrides, and anonymous `PermitAll`; do not merely check that annotations exist in source code.

**Step 8 — Test object-level rules and side effects.** Lacking permission or wrong tenant must not create/delete resources; on denial, transactions/queues must produce no side effects.

**Step 9 — Evaluate concurrency/versioning.** Role revocation, stale JWTs/sessions, hierarchy updates, and contextless executors; test against resolved dependencies and real requests.

**Step 10 — Review periodically.** When adding new methods or changing business roles, update the access matrix, integration tests, and policy docs. Never relax permissions just to silence a 403 test.

## 19. Self-Check Questions

**Question 1.** Why does `@RolesAllowed("ADMIN")` not automatically block a method if `jsr250Enabled=true` is missing?

**Answer:** The annotation is Jakarta metadata; Spring Security enforces it only when the JSR-250 method interceptor is activated and the invocation goes through a matching proxy/interception point.

**Question 2.** Does `@RolesAllowed({"ADMIN","EDITOR"})` require one role or both?

**Answer:** **Either one** (OR). If both are required, use an explicit AND policy such as `@PreAuthorize`.

**Question 3.** Does `@PermitAll` on a service automatically make the corresponding HTTP endpoint public?

**Answer:** No. The HTTP `SecurityFilterChain` can still require authentication/roles and enforce CSRF/CORS filters. `PermitAll` only drops the role check at the JSR-250 method advisor.

**Question 4.** A `@RolesAllowed("USER")` class has a `@RolesAllowed("ADMIN")` method. Must callers have both `USER` and `ADMIN` at once?

**Answer:** No, per JSR-250 class/method override semantics; method-level `ADMIN` replaces class-level `USER` for that method. Other advisors or domain policies can still require additional conditions.

**Question 5.** Can `@DenyAll` block `ADMIN`?

**Answer:** Yes, if the JSR-250 interceptor is active and the invocation goes through it. Tests should verify the method body does not run. Do not treat it as an absolute barrier against unproxied self-invocation.

**Question 6.** Does `@RolesAllowed("hasAuthority('report:read')")` evaluate SpEL?

**Answer:** No. That is treated as a literal role name string. Use `@PreAuthorize("hasAuthority('report:read')")` for that expression.

**Question 7.** How do `@WithMockUser(roles="ADMIN")` and `@WithMockUser(authorities="ADMIN")` differ?

**Answer:** The `roles` form typically grants `ROLE_ADMIN`; the `authorities` form grants exact `ADMIN`. With the default role prefix, JSR-250 results can differ.

**Question 8.** Why does a passing test on a `PermitAll` method fail to prove JSR-250 is enabled?

**Answer:** A public method can still run when JSR-250 method security is disabled. Negative tests with `@DenyAll` or missing roles are required to prove the interceptor actually works.

**Question 9.** Does `@RolesAllowed("ADMIN")` automatically ensure an ADMIN of tenant A can delete only users of tenant A?

**Answer:** No. That is only a functional role check. The service must verify tenant/ownership/ACL/account state.

**Question 10.** If `@PreAuthorize` and `@PermitAll` are both present on one method, which annotation "wins"?

**Answer:** Do not think of one annotation as winning and disabling the other. When both types of method-security advisors are active, both checks apply; `@PermitAll` does not turn `@PreAuthorize` into allow.

**Question 11.** Why can class-level `@PermitAll` be dangerous?

**Answer:** New methods added to the class can inherit the public policy at JSR-250. Limit `PermitAll` to genuinely public methods or split services cleanly.

**Question 12.** When upgrading from Spring Boot 2 to Boot 3, where do JSR-250 import errors usually come from?

**Answer:** The namespace moved from legacy `javax.annotation.security` to `jakarta.annotation.security`. Check `jakarta.annotation-api` and compatible libraries, and never mix the two annotation namespaces unintentionally.

**Question 13.** Role `ADMIN` is accepted by `@RolesAllowed` on the method, yet POST returns 403 before reaching the controller. Why?

**Answer:** It could be CSRF, an HTTP rule, or another filter, not necessarily JSR-250. Test POST with proper CSRF, and check matchers/filter chains and method policies separately.

**Question 14.** A service method with JSR-250 is called via `this.method()` inside the same bean. Is protection guaranteed?

**Answer:** No, under standard Spring AOP proxy mode. Self-invocation can bypass the interceptor. Design calls across bean boundaries and test with real proxies.

**Question 15.** Should JSR-250 be used for the policy "`report:approve` AND same tenant AND no self-approval"?

**Answer:** It cannot express this directly. Use `@PreAuthorize`/a policy bean or checks in a domain service, backed by trustworthy data sources and integration tests.

**Conclusion:** `@RolesAllowed` answers "which role is allowed", `@PermitAll` says "no role required at the JSR-250 layer", and `@DenyAll` says "no role is allowed". For them to genuinely protect an application, you must enable `jsr250Enabled`, use the right version's Jakarta imports, ensure Spring AOP intercepts calls, keep HTTP security and object-level permissions independent, and test **allow, deny, overrides, role prefixes, and side effects**. A concise annotation is safe only when deployed inside a verifiable execution boundary.

## Official References

- Spring Security 6.5 — Method Security, JSR-250, multiple advisors, and class/method annotations: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 7.0 — Method Security: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- Spring Security 6.5 — Jsr250AuthorizationManager API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authorization/method/Jsr250AuthorizationManager.html
- Spring Security 7.0 — Jsr250AuthorizationManager API: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/method/Jsr250AuthorizationManager.html
- Jakarta Annotations — @RolesAllowed Javadoc: https://jakarta.ee/specifications/webprofile/11/apidocs/jakarta/annotation/security/rolesallowed
- Jakarta Annotations — @PermitAll Javadoc: https://jakarta.ee/specifications/platform/10/apidocs/jakarta/annotation/security/permitall
- Jakarta Annotations — @DenyAll Javadoc: https://jakarta.ee/specifications/annotations/2.1/apidocs/jakarta.annotation/jakarta/annotation/security/denyall
- Spring Security — Authorization Architecture and role naming: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — HTTP request authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — MockMvc security tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — Method security tests and @WithMockUser: https://docs.spring.io/spring-security/reference/servlet/test/method.html
