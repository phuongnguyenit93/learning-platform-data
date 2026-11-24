# Unannotated Methods and Default Coverage Policies

> **Module:** Spring Security - authorization  
> **Knowledge group:** Method security  
> **Objective:** Understand precisely what happens to methods without security annotations in Spring Security; recognize when a method **is already protected via class/interface/pointcut** even without an annotation on the method itself; design default coverage policies toward deny-by-default without breaking valid call flows; and write tests proving every critical execution path has appropriate authorization.

## 1. The Question to Answer Before Writing Code

A project added:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {}
```

Then it has a service:

```java
@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public ReportView readReport(long reportId) {
        return repository.readReport(reportId);
    }

    public void deleteReport(long reportId) {
        repository.deleteById(reportId);
    }
}
```

Does Spring Security automatically block `deleteReport` because this method **has no annotation**?

**No.** `@EnableMethodSecurity` activates method protection via interceptors, yet annotation-based interceptors by default only apply when a matching security annotation is found on the method, class, interface, or meta-annotation. If a call has no effective security rule and is not covered by another custom pointcut/advisor, **there is no default DENY decision simply because the method lacks an annotation**.

This does not mean anyone on the internet can call the method directly; HTTP rules, controllers, authentication, business policies, Java visibility, and real call paths may restrict it. However, **you must not infer that a method not called via HTTP is safe**: it can be called by a new controller, GraphQL resolver, job, message listener, or another Spring bean.

Core principle of this lesson:

> **The absence of an annotation on a method line is not equivalent to the presence of a DENY policy. To get "deny by default", design and verify a rule that truly covers the calls needing protection.**

## 2. Four Similar-Looking Scenarios with Different Outcomes

| Scenario | Annotation Directly on Method? | Effective Method-Security Rule? | Assessment |
| --- | --- | --- | --- |
| Unannotated method, unannotated class/interface, no custom advisor | No | Usually no | Not blocked by annotation-based method security |
| Unannotated method, class has `@PreAuthorize("hasRole('USER')")` | No | Yes | Method **inherits the class rule** |
| Unannotated method, parent interface has valid rule | No | Possibly yes | Must verify annotation inheritance and proxy/interface resolution |
| Unannotated method, custom `Advisor` has matching pointcut | No | Yes | Protected via **pointcut**, no method annotation needed |
| Method has `@PreAuthorize("denyAll()")` | Yes | Yes | Denied when the interceptor actually runs |
| Method has `@PreAuthorize("permitAll()")` | Yes | Yes | Has an allow rule at this checkpoint, though other checkpoints may still DENY |
| Method has `@Secured` while `securedEnabled=false` | Yes | Uncertain | Annotation exists, yet that interceptor group may not be enabled |
| Annotated method called directly via `this.method()` | Yes | Advice may **not run** | Self-invocation in standard proxies is not blocked |
| Method on object created via `new` outside Spring | Yes or no | Not guaranteed | No Spring proxy to apply method security |
| Method has annotation while app has not enabled `@EnableMethodSecurity` | Yes | No interceptor guaranteed | Must not be treated as protected just because the annotation is in source |

**Effective protection must be verified at runtime**, not simply by counting annotations.

## 3. What Does `@EnableMethodSecurity` Actually Activate?

Spring Security Servlet 6.5 uses:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {}
```

This enables protection via `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` in default configuration. `Spring Boot Starter Security` **does not automatically enable method-level authorization**; verify your project's actual beans/configuration.

Execution flow when `@PreAuthorize` is present:

```text
Spring bean through proxy
       |
       v
Method invocation
       |
       v
Does an annotation-aware pointcut see @PreAuthorize
on method/class/interface/meta-annotation?
       | NO
       |   -> @PreAuthorize interceptor has no reason to block
       | YES
       v
AuthorizationManagerBeforeMethodInterceptor
       |
       v
PreAuthorizeAuthorizationManager
       |
       +--- DENY -> exception / denied handler
       |
       +--- ALLOW -> method body executes
```

Distinguish clearly:
- `@PreAuthorize` decides **before** running the method body.
- `@PostAuthorize` inspects the result **after** the body has executed.
- `@PreFilter`/`@PostFilter` filter matching inputs/outputs; they do not replace command-level authorization policies.
- `@Secured` and `@RolesAllowed` (JSR-250) require enabling their corresponding flags.

There is no default interceptor that "sweeps every method and DENIES if no annotation is found" upon enabling `@EnableMethodSecurity`.

Source: official Spring Security 6.5 documentation explicitly states *unannotated methods are not secured* in the annotation-based model, and recommends having a catch-all HTTP authorization rule to protect request ingress.

## 4. "No Annotation" Requires Inspecting the Whole Hierarchy

A method without an annotation right above it can still be protected by a class-level annotation:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
@PreAuthorize("hasAuthority('finance:read')")
public class FinanceService {

    public String summary() {
        return "financial summary";
    }

    public String details() {
        return "financial details";
    }
}
```

In a proper method security setup, both `summary` and `details` inherit `hasAuthority('finance:read')` from the class; they are not "unsecured" simply for lacking per-method annotations.

If class-level and method-level both carry the **same `@PreAuthorize` annotation type**, method-level **overrides/takes precedence over** class-level:

```java
@Service
@PreAuthorize("hasRole('USER')")
public class CatalogService {

    public String list() {
        return "normal catalog";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String deleteCatalog() {
        return "admin operation";
    }
}
```

For `deleteCatalog`, the method-level `hasRole('ADMIN')` rule replaces the class-level rule of the same annotation type. Do not interpret it as "USER AND ADMIN" merely because both class and method use `@PreAuthorize`.

However, **different annotation types have different interceptors**. For example, `@PreAuthorize` combined with `@PostAuthorize` on the same invocation typically runs sequentially, effectively requiring both rules to pass. Do not confuse **same-type** override with a method annotation replacing all other policy layers.

### Interfaces and Multiple Inheritance

Spring Security supports annotations on interfaces. An implementation without an annotation on a concrete method can still inherit the policy from an interface. If a class implements multiple interfaces with conflicting annotations and Spring cannot resolve a clear rule, startup may fail; resolve it with an explicit annotation on the concrete method.

When auditing coverage, inspect **method + class + interface + meta-annotations + advisors**, not just `method.isAnnotationPresent(PreAuthorize.class)`.

## 5. What Does a Default HTTP Rule Protect?

Example `SecurityFilterChain` using fallback deny:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain app(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/healthz")
                .permitAll()
            .requestMatchers("/api/admin/**")
                .hasRole("ADMIN")
            .requestMatchers("/api/**")
                .authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Here:
- `GET /healthz` is public at the HTTP checkpoint.
- `/api/admin/**` requires role `ADMIN` before the general API rule.
- Other `/api/**` requests require authentication.
- Remaining paths in the chain receive `denyAll`.

This prevents accidentally exposing a new HTTP endpoint outside `/api/**`, **if the request actually belongs to that `SecurityFilterChain`**. Still, `/api/**.authenticated()` only checks that the caller is logged in; if a controller invokes a dangerous method lacking a method guard/domain policy, a normal logged-in user can reach functionality meant only for `ADMIN`.

**More importantly:** `anyRequest().denyAll()` is only an **HTTP authorization** fallback. It does **not** block a `@Scheduled` job, message consumer, or bean calling `deleteReport` internally. Method/service policies are a separate layer.

If the application has multiple `SecurityFilterChain`s using narrow `securityMatcher`s, ensure a fallback chain exists so routes do not fall outside all filter chains. `anyRequest` in one chain does not protect URLs outside that chain.

## 6. Two Common "Default Coverage" Approaches

### Approach A — Ensure All HTTP Entry Points Are Authorized

Suitable when request-level policies are the primary outer coverage layer:

- Inventory every route and HTTP method.
- Place narrow rules before broad matchers.
- Have `anyRequest().denyAll()` or a design-approved `authenticated()` fallback.
- Test anonymous, regular user, privileged role, and cross-tenant resources.
- With multiple chains, verify routes are matched by an actual chain.
- Sensitive services must still have domain policies if callable from elsewhere.

Advantage: reduces risk of accidentally exposing new routes. Limitation: **does not cover service calls outside HTTP**.

### Approach B — Protect the Service Layer with a Default Policy

Suitable when services have multiple entry points or the organization wants an explicit service-level policy:

- Place annotations on **classes/interfaces** to cover normal methods.
- Or register a **custom pointcut + `AuthorizationManagerBeforeMethodInterceptor`** for a group of services.
- Permit specific methods via reviewed annotations/policies.
- Enforce object-level checks in use cases, not just role checks.
- Test calling beans directly through the Spring proxy, including methods with no annotation on the method line.

Advantage: a new controller/job calling an existing service still hits the service guard when calls pass through the proxy/pointcut. Limitation: **proxy boundaries, self-invocation, object instantiation, and non-Spring callers** still must be managed.

Both approaches **complement** each other rather than being mutually exclusive.

## 7. Class-Level Default Deny Pattern: `@PreAuthorize("denyAll()")`

If a service wants **to prevent new methods from being exposed unintentionally**, it can declare at the class level:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
@PreAuthorize("denyAll()")
public class DocumentCommandService {

    @PreAuthorize("hasAuthority('document:read')")
    public String readDocument(long id) {
        return "document:" + id;
    }

    @PreAuthorize("hasAuthority('document:delete')")
    public void deleteDocument(long id) {
        // Load resource in allowed tenant,
        // check ownership/ACL/state, then delete.
    }

    public void exportAllDocuments() {
        // No @PreAuthorize on the method:
        // class-level denyAll still takes effect when advice runs.
    }

    @PreAuthorize("permitAll()")
    public String publicMetadata() {
        return "public metadata";
    }
}
```

**Idea:**
- `@PreAuthorize("denyAll()")` on the class is an effective method-level policy for methods that do not declare an override.
- `readDocument` and `deleteDocument` have their own `@PreAuthorize`, so they **override** the same-type class-level rule.
- `exportAllDocuments` has no direct annotation, so it is denied by the class-level rule.
- `publicMetadata` overrides with `permitAll()` at the `@PreAuthorize` checkpoint; do this only if genuinely public, remembering other filters or domain rules can still deny.

This is a **structural example**, not a complete application: it lacks `@EnableMethodSecurity` configuration, authentication, real DB/policies, and exception handling. Returned strings are illustrative; never assume returning plain text makes a method safe.

**This is true default-deny for that class** — completely different from leaving a class unannotated and hoping the framework denies all new methods.

### Important Notes When Using Class-Level `denyAll`

1. Requires `@EnableMethodSecurity` and callers passing through the Spring proxy/appropriate advice.
2. Method-level `@PreAuthorize` **overrides** class-level `@PreAuthorize`, so include all required conditions in the override.
3. `@PreAuthorize("permitAll()")` is an exception requiring careful review; HTTP or other auth contexts can still impose requirements.
4. Never replace class-level `@PreAuthorize` with `@PostAuthorize("denyAll()")` for commands: post-checks run **after** the body, which can be too late for side effects.
5. Internal `this.method()` calls bypass standard proxies; do not rely on class-level deny as the sole defense against dangerous self-invocation.
6. Do not slap this policy onto utility classes or all repositories without checking call flows; it can accidentally block internal methods and cause regressions.
7. If methods are called outside beans/proxies, class-level annotations do not build a firewall.
8. If a method also carries another enabled security annotation type, consider that annotation's interceptor as well.
9. For APIs mixing public and private methods, separating public and private beans is often easier to review than overusing `permitAll()`.

## 8. Class-Level Authenticated Baseline Pattern

Not every service needs absolute default-deny. Some service groups have a policy that "all methods are only for authenticated actors":

```java
@Service
@PreAuthorize("isAuthenticated()")
public class CustomerService {

    public CustomerView profile() {
        return service.currentCustomer();
    }

    @PreAuthorize("hasAuthority('customer:write')")
    public void updateCustomer(String id) {
        // ...
    }
}
```

`profile()` has no separate annotation yet inherits `isAuthenticated()` from the class. `updateCustomer` has its own annotation of the same type, so **do not assume Spring always evaluates both expressions with AND**; a method-level rule of the same type overrides the class-level rule.

If `hasAuthority('customer:write')` satisfies the policy on a trusted `Authentication`, that may suffice; if the policy also requires MFA, tenant, ownership, or session assurance, state it explicitly in the method rule or domain policy.

**Choose the baseline by risk:**
- `denyAll()`: suited for services with sensitive commands where every public method must be explicitly reviewed/allowed.
- `isAuthenticated()`: suited for groups of methods sharing a common authentication requirement without dangerous commands exposed to ordinary users.
- `hasAuthority("...")`: suited when every method in the class genuinely requires the same permission.
- `permitAll()`: only for harmless/public methods with clear contracts.

Never make `isAuthenticated()` the default policy for every command just to make integration tests pass easily.

## 9. Notes on `@PermitAll`, `@Secured`, and `@RolesAllowed`

In default `@EnableMethodSecurity`:
- `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` are enabled.
- `@Secured` requires `securedEnabled = true`.
- JSR-250 annotations `@RolesAllowed`, `@PermitAll`, and `@DenyAll` require `jsr250Enabled = true`.

Example when enabling both groups:

```java
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
class MethodSecurityConfiguration {}
```

Do not assume a method carrying `@Secured("ROLE_ADMIN")` is protected in a new app simply because the annotation is in source code if the `securedEnabled` interceptor has not been turned on.

### Different Annotation Types Do Not Form One Override Hierarchy

If a class declares `@PreAuthorize("denyAll()")` while a method carries `@PermitAll`, **do not assume** `@PermitAll` replaces class-level `@PreAuthorize`. They belong to **two different annotation/advice types**, and both checks can run. To override class-level `@PreAuthorize`, use **method-level `@PreAuthorize`** of the same type, and test it.

Similarly, `@PostAuthorize("permitAll()")` does not cancel `@PreAuthorize("denyAll()")` before the body runs. When multiple security annotation types apply to one invocation, their decisions generally all have to pass.

## 10. Using Pointcuts to Protect Unannotated Methods

Spring Security builds method security on Spring AOP, so a group of methods can be protected via a **pointcut**, even without direct annotations. Official documentation provides an `Advisor` registration pattern using `AuthorizationManagerBeforeMethodInterceptor`.

Example requiring every method on `*Service` classes in package `com.example.service` to hold `ROLE_USER`:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Role;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class ServiceLayerPolicy {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor protectServiceMethods() {
        var pointcut = new AspectJExpressionPointcut();
        pointcut.setExpression(
            "execution(* com.example.service.*Service.*(..))"
        );

        return new AuthorizationManagerBeforeMethodInterceptor(
            pointcut,
            AuthorityAuthorizationManager.hasRole("USER")
        );
    }
}
```

**This is a Spring snippet**, requiring matching package/service names and Spring AOP/AspectJ dependencies. It is not standalone `javac`. In the example:
- `execution(* com.example.service.*Service.*(..))` targets only `*Service` classes directly in the named package; **it does not automatically cover subpackages**.
- The custom interceptor requires `ROLE_USER` for calls that **actually pass through the proxy** and match the pointcut.
- Unannotated methods still undergo the pointcut rule.
- If `@PreAuthorize` is also on the invocation, interceptors may **both run checks**; do not expect an annotation to automatically override a pointcut advisor.

**Major limitation:** a broad default `DENY ALL` advisor using a wide pointcut will block even methods annotated with ALLOW unless you carefully design exclusions in the pointcut. For "new methods in a class must deny, reviewed methods are opened", **class-level `@PreAuthorize("denyAll()")` + method-level overrides** is usually far clearer than a package-wide deny-all advisor.

## 11. Pointcuts Define Method Sets: Scope Must Be Complete

An AOP expression like:

```text
execution(* com.example.service.*Service.*(..))
```

can miss:
- Classes in `com.example.service.internal` instead of the direct package.
- Classes named `DocumentManager` rather than ending in `Service`.
- Methods not belonging to Spring beans.
- `private`/`final` methods and unproxied calls.
- A service interface/implementation outside the naming convention.
- Jobs/GraphQL calling objects or repositories directly.

A custom pointcut therefore **does not automatically mean "protect every method"**. Cross-check against the real list of service beans and entry points. If relying on naming conventions, CI needs naming/bean-discovery tests so new classes do not accidentally fall outside scope.

### Why Avoid "Blocking by Name `get*`/`delete*`"?

Method names are not trustworthy security policies:
- `deletePreviewCache` and `deleteCustomer` carry very different risks.
- A service may name methods `execute`, `process`, or `handle` while deleting data.
- A getter may export sensitive data.
- A handler may trigger side effects even if named `get...`.

Authorize by business operation/capability and real boundaries, not solely by name prefixes.

## 12. Key Point: An Annotation Does Not Protect Calls Bypassing the Proxy

With Spring AOP proxy-based method security, the typical call path is:

```text
Controller / another bean
     |
     v
Spring proxy
     |
     v
Method-security advisors
     |
     v
Target service method
```

Self-invocation bug:

```java
@Service
public class PaymentService {

    public void process(long paymentId) {
        this.approvePayment(paymentId);
    }

    @PreAuthorize("hasAuthority('payment:approve')")
    public void approvePayment(long paymentId) {
        // Side effect...
    }
}
```

In standard proxy-based configuration, `this.approvePayment(...)` is an internal call on the target object, **not passing through the proxy**, so `@PreAuthorize` advice may not execute. Adding a class-level annotation does not fix a call path that bypasses the proxy.

To reduce risk:
1. Place protected commands on **service bean boundaries** invoked through the Spring container.
2. Split distinct operations into clear beans when calls must go through proxies.
3. Enforce **mandatory domain authorization** inside application use cases before side effects if business rules require it.
4. Test both direct external bean calls and nested call flows.
5. Consider `AdviceMode.ASPECTJ` only when you understand weaving/bytecode, not as a magic fix for all bugs.
6. Never instantiate services with `new` expecting annotations to run.
7. Watch out for `private`/`final` methods, proxy types, Kotlin final classes, and visibility; verify behavior on the real framework/runtime.

**Conclusion:** coverage must be measured by **real execution paths**, not merely "an annotation appears somewhere in source code".

## 13. HTTP Fallbacks and Method Fallbacks Have Different Coverage

Two examples:

```text
Case A: GET /api/reports/42
   -> HttpSecurity requestMatchers
   -> Controller
   -> ReportService.readReport()
   -> Domain policy

Case B: @Scheduled job
   -> ReportService.readReport()
   -> Domain policy

Case C: Message listener
   -> ReportService.deleteReport()
   -> Domain policy
```

In A, HTTP security can block before the controller. In B/C, HTTP filters **do not participate**. If the service method has no annotation/class/pointcut rule and no domain policy exists, the business operation can execute with no authorization.

Jobs or service actors can be granted their own permissions, yet that must be **an intentional policy decision**: lacking an HTTP user does not mean "the system has full privileges". Background processes can carry tenant scopes, task scopes, and principal/service identities; audits must record the real actor and trusted context.

### Which Layer Is Responsible for What?

| Layer | Role | Should Not Expect |
| --- | --- | --- |
| HTTP `SecurityFilterChain` | Block unauthenticated/unauthorized requests by route | Protecting jobs, queues, direct bean calls |
| Method security | Block intercepted bean calls per annotations/pointcuts | Automatically protecting unannotated methods or self-invocation |
| Application service policy | Actor–action–object–context, tenant/owner/ACL | Automatically knowing `Authentication` if entry point passes no clear identity |
| DB/repository scope | Prevent reading/writing wrong tenant, version, or records | Replacing overall business decisions |
| Audit/monitoring | Track behavior and explain denials | Replacing enforcement |

Critical systems should design **defense in depth** without leaving any layer missing policies on the assumption another layer "probably blocked it".

## 14. When Is an Unannotated Method Still Safe?

A method without a direct annotation **is not automatically a vulnerability**. For example:

- Pure internal computation helpers that do not read/write sensitive resources.
- Helpers receiving already-validated data, called solely from a policy-checked use case — still ensuring no other entry point bypasses it.
- Getters for public constants.
- Methods protected by class/interface annotations.
- Methods covered by a tested pointcut advisor.
- Repositories called only from services enforcing tenant scope and domain policies; repositories should still maintain contracts preventing misuse.

The deciding factor is **call paths and executed functionality**, not the mere presence or absence of a `@PreAuthorize` line. Every method operating on sensitive data or triggering side effects needs a security checkpoint **that cannot be bypassed through valid architectural call paths**.

A project with thousands of helpers does not need annotations forced onto every helper at all costs. However, every **entry point into sensitive use cases** must be identified, assigned a policy, and tested.

## 15. `@PostAuthorize` Cannot Replace Pre-Method Default-Deny

Example:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public DocumentView read(long id) {
    return repository.loadView(id);
}
```

`@PostAuthorize` can be useful when the owner lives inside the returned object, though the body has already executed to produce it. For reads, this may be acceptable if queries and logging do not leak data prior to the post-check; for writes, never rely on it as the primary guard.

A dangerous command:

```java
@PostAuthorize("denyAll()")
public void transferMoney(long transferId) {
    paymentGateway.sendMoney(transferId);
}
```

The method may have already called the external API before post-checking denies. Even with `@Transactional`, database rollback does not undo external side effects. For writes, use `@PreAuthorize` or service guards **before** modifying data, with appropriate transactions/locking.

**Do not confuse** "method has an annotation" with "annotation protects at the right time".

## 16. Service Default-Deny Does Not Replace Ownership/Tenant Authorization

Example:

```java
@Service
@PreAuthorize("denyAll()")
public class DocumentService {

    @PreAuthorize("hasAuthority('document:read')")
    public DocumentView read(long documentId) {
        return repository.findViewById(documentId);
    }
}
```

Now `read` has an explicit rule; however, an actor with `document:read` can still fetch someone else's ID if `findViewById` ignores tenant/owner. **Default-deny for undeclared methods is not a solution to IDOR/BOLA.**

A sufficiently strict policy:

```java
@PreAuthorize("hasAuthority('document:read')")
public DocumentView read(long id) {
    Actor actor = actorResolver.requireAuthenticatedActor();
    Document doc = repository
        .findByIdAndTenantId(id, actor.activeTenantId())
        .orElseThrow(DocumentNotFoundException::new);

    if (!documentPolicy.canRead(actor, doc)) {
        throw new AccessDeniedException("Not accessible");
    }

    return mapper.toView(doc);
}
```

This is an **integration snippet**: `Actor`, repo, domain policy, mapper, and exception are app-defined. It illustrates three conditions: functional permission, tenant scope, and permission on the specific resource.

Even a method with `@PreAuthorize("hasRole('ADMIN')")` does not automatically bypass tenant/ACL boundaries. If an admin is supposed to read all documents within their tenant, require an explicit `document:read:tenant` capability and a tenant-scoped policy.

## 17. Tests Must Also Verify "Forgotten Annotation" Methods

If using class-level default-deny, test a method **without its own annotation**:

```java
// In a Spring Boot test with @EnableMethodSecurity,
// inject the Spring-managed DocumentCommandService.
@Test
@WithMockUser(authorities = {"document:read"})
void unreviewedExportRemainsDenied() {
    assertThatThrownBy(
        () -> documentCommandService.exportAllDocuments()
    ).isInstanceOf(AccessDeniedException.class);
}
```

The test must call **the bean through the Spring proxy**, not `new DocumentCommandService(...)`. Creating the object manually tests plain Java logic rather than method security interception.

To prove overrides work:

```java
@Test
@WithMockUser(authorities = {"document:read"})
void reviewedReadIsAllowed() {
    assertThat(documentCommandService.readDocument(42L))
        .isNotNull();
}

@Test
@WithMockUser(authorities = {"document:read"})
void readOnlyUserCannotDelete() {
    assertThatThrownBy(
        () -> documentCommandService.deleteDocument(42L)
    ).isInstanceOf(AccessDeniedException.class);
}
```

Snippets require JUnit 5, AssertJ, `@WithMockUser`/`spring-security-test`, method security configuration, domain fixtures, and proper exception mapping. For example, `readDocument` needs a real handler/fixture returning data; if the repository returns null or policy rejects, the ALLOW test fails elsewhere. Never treat a 403 test as complete proof when the real denial actually came from the DB or an HTTP filter.

### Negative Testing for Unannotated Methods

The most valuable test is:
- Create an unannotated public method inside a default-deny class.
- Call it through the bean proxy with an authenticated user lacking explicit grants.
- Verify **the method body did not run** and state did not change.
- Verify another properly allowlisted method still runs.
- Repeat with anonymous, low-privilege, and admin users.
- If a method is allowed by a class baseline, verify new methods inherit the baseline.

## 18. MockMvc Tests for Real HTTP Catch-All Rules

Suppose HTTP policies are:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/info").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
```

Matrix:

| Request | Actor | Expected HTTP |
| --- | --- | --- |
| `GET /api/public/info` | Anonymous | ALLOW |
| `POST /api/public/info` | Anonymous | DENY unless a public write rule exists |
| `GET /api/admin/users` | `ROLE_USER` | DENY |
| `GET /api/admin/users` | `ROLE_ADMIN` | ALLOW HTTP |
| `GET /api/documents/42` | Anonymous | DENY |
| `GET /api/documents/42` | Authenticated | ALLOW at HTTP rule, yet method/domain policy may DENY |
| `GET /private-new-route` | Authenticated | DENY via catch-all |
| `POST /api/documents/42/delete` | `ROLE_USER` | May pass HTTP `authenticated`, must be denied by method/domain policy if lacking permission |

Testing a new route:

```java
@Test
void unknownRouteIsNotPublic() throws Exception {
    mvc.perform(get("/private-new-route")
            .with(user("reader").roles("USER")))
        .andExpect(status().isForbidden());
}
```

This is a MockMvc snippet, not standalone `javac`. To distinguish `denyAll` from 404 due to a missing handler, test with a real route/controller fixture and verify the handler/interceptor was not invoked. For POST/PATCH using sessions/CSRF, supply a valid CSRF token so the test does not pass 403 at `CsrfFilter` before reaching authorization policy.

**HTTP tests alone do not prove** that methods invoked from event listeners, jobs, or service beans are protected.

## 19. Standalone Java 17+: Simulating No-Annotation, Class-Default, and Override

The following plain Java program defines its own `@Policy` annotation and a simple checker to simulate how **method policy overrides class policy**. It is **not an implementation of Spring Security or Spring AOP**, and does not prove framework proxying. Its goal is observing three states:
- No method/class policy → **NO_GUARD**.
- Class has DENY → unannotated method **is blocked**.
- Method has its own policy → overrides class default.

Save as `MethodDefaultPolicyDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Set;

public class MethodDefaultPolicyDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface Policy {
        String value();
    }

    record Actor(boolean authenticated, Set<String> authorities) {}

    static class UnprotectedService {
        public String export() {
            return "exported";
        }
    }

    @Policy("DENY")
    static class ProtectedService {
        @Policy("USER")
        public String read() {
            return "document";
        }

        public String purge() {
            return "deleted";
        }

        @Policy("PUBLIC")
        public String health() {
            return "ok";
        }
    }

    static String call(Object target, String operation, Actor actor)
            throws ReflectiveOperationException {
        Method method = target.getClass().getDeclaredMethod(operation);
        Policy methodPolicy = method.getAnnotation(Policy.class);
        Policy classPolicy = target.getClass().getAnnotation(Policy.class);

        String rule = methodPolicy != null
            ? methodPolicy.value()
            : classPolicy != null ? classPolicy.value() : "NO_GUARD";

        boolean allowed = switch (rule) {
            case "DENY" -> false;
            case "PUBLIC", "NO_GUARD" -> true;
            case "USER" -> actor.authenticated()
                && actor.authorities().contains("ROLE_USER");
            default -> throw new IllegalStateException(rule);
        };

        if (!allowed) {
            return "DENY " + operation + " via " + rule;
        }
        return "ALLOW " + operation + " via " + rule
            + " -> " + method.invoke(target);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Actor guest = new Actor(false, Set.of());
        Actor user = new Actor(true, Set.of("ROLE_USER"));
        UnprotectedService unsafe = new UnprotectedService();
        ProtectedService safe = new ProtectedService();

        System.out.println("Unsafe guest: "
            + call(unsafe, "export", guest));
        System.out.println("Safe guest purge: "
            + call(safe, "purge", guest));
        System.out.println("Safe guest read: "
            + call(safe, "read", guest));
        System.out.println("Safe user read: "
            + call(safe, "read", user));
        System.out.println("Safe guest health: "
            + call(safe, "health", guest));
        System.out.println("Safe user purge: "
            + call(safe, "purge", user));
    }
}
```

Compile and run on JDK 17 or newer:

```bash
javac MethodDefaultPolicyDemo.java
java MethodDefaultPolicyDemo
```

Exact stdout:

```text
Unsafe guest: ALLOW export via NO_GUARD -> exported
Safe guest purge: DENY purge via DENY
Safe guest read: DENY read via USER
Safe user read: ALLOW read via USER -> document
Safe guest health: ALLOW health via PUBLIC -> ok
Safe user purge: DENY purge via DENY
```

**Meaning:** `UnprotectedService.export` has no class/method policy, so the simulator does not block the guest. `ProtectedService.purge` has no individual annotation yet inherits the class `DENY` policy. `read` and `health` have their own annotations and override the baseline. When the user lacks the role, `read` is denied.

**Mandatory limitation:** `@Policy` in the demo is self-defined by this lesson, not a Spring annotation. `MethodDefaultPolicyDemo.call` uses reflection to simulate rule resolution; real Spring uses AOP advisors, annotation discovery, and `Authentication`. Do not copy this simulator into production.

## 20. Policies for Unannotated Methods by Method Category

Not every method needs the same protection level. A practical classification:

| Method Category | Example | Recommended Protection |
| --- | --- | --- |
| Public query exposing no private data | `getPublicVersion()` | Explicit public policy at appropriate HTTP/method layers |
| Logged-in user's own query | `getMyProfile()` | Authentication + server-side actor ID binding |
| Private document query | `readDocument(id)` | Read authority + tenant/owner/ACL |
| Write command | `renameDocument(id)` | Functional permission + policy inside transaction before side effects |
| Privileged command | `approvePayment(id)` | Strong permission + SoD, state, limits, MFA when needed |
| Background task | `expireSessions()` | Service actor/job scope, logging, and clear policy |
| Pure helper | `normalizeTitle()` | May not need annotation, yet must not be a public use case |
| Internal event handler | `onPaymentEvent(evt)` | Verify event origin/identity and domain invariants |
| Repository gateway | `findAllByTenant(...)` | Query scoping and contract, avoid service bypass |

When adding a new public method to a sensitive service, class-level default-deny architecture makes forgetting a policy surface immediately (the method is DENIED). However, if a developer adds direct repository access inside a controller, an **unrelated** service's class-level policy will not protect it. Architectural review remains mandatory.

## 21. Methods Inherited from Classes/Interfaces and Special Risks

Check carefully:
- Methods declared in an interface yet implemented in another class.
- Annotations on interface methods/classes.
- Annotations on parent classes with methods overridden in subclasses.
- Same method inheriting annotations from multiple interfaces.
- Java bridge methods/generics and proxy types.
- Application-defined meta-annotations.
- Which annotation groups are enabled in `@EnableMethodSecurity`.

Spring Security docs note that annotations can live on methods, classes, and interfaces; method-level can override class-level for the same type. With multi-interface conflicts, the framework can fail startup to prevent ambiguity.

Therefore, **never rely on a naive reflection scanner reading only declared method annotations to claim "every method is protected"**. Scanners assist reviews, yet runtime pointcuts/advisors and integration tests are the real proof of policy enforcement.

Code such as:

```java
method.isAnnotationPresent(PreAuthorize.class)
```

will miss annotations on classes/interfaces/meta-annotations or custom AOP rules. Tools like ArchUnit or custom static checks can flag public service methods lacking an **effective policy**, provided the check accounts for inheritance and allowlists rather than reporting "safe" just for seeing any random annotation.

## 22. Runtime Coverage Inventory: From Entry Point to Method Use Case

Build a matrix:

| Entry Point | Service Method | Effective Method Rule | HTTP Rule | Resource Policy | Negative Test |
| --- | --- | --- | --- | --- | --- |
| `GET /api/documents/{id}` | `read(id)` | `document:read` | Authenticated | Tenant + owner/ACL | Different owner DENY |
| `POST /api/documents/{id}/delete` | `delete(id)` | `document:delete` | Authenticated | Tenant + status | Read-only user DENY |
| `GET /api/public/version` | `getVersion()` | Explicit PUBLIC | Public GET | No private data | POST not public by default |
| `@Scheduled cleanup` | `cleanup()` | Service actor / explicit default | No HTTP | Data scope + audit | Job context lacking privilege DENY |
| Message listener | `process(event)` | Explicit command policy | No HTTP | Event origin, tenant, state | Forged event DENY |
| GraphQL mutation | `rename(id)` | `document:rename` | `POST /graphql` | Tenant + owner + status | Viewer DENY |
| New controller route | `exportAll()` | Class-level `denyAll` until reviewed | HTTP fallback | Export policy | No grant DENY |

For every use case, ask:
1. Who can call this entry point?
2. Does the caller pass through HTTP filters?
3. Does the service call pass through the Spring proxy?
4. Does the method have an effective class/interface/meta annotation or custom pointcut?
5. Is there an object/tenant/capability policy?
6. Is there an internal method or alternate path bypassing the guard?
7. Which negative test proves there is no bypass?

**Do not equate coverage with annotation count.** Coverage must be measured by policy behavior on actual call paths.

## 23. When Method Security Works Yet Permissions Are Still Wrong

A service:

```java
@PreAuthorize("hasRole('USER')")
public DocumentView readDocument(long id) {
    return repository.findById(id);
}
```

Even though the method is protected, every user with `ROLE_USER` can access arbitrary IDs without object authorization. With class-level default-deny, adding `hasRole('USER')` opens this method past the baseline, yet data policies are still needed.

Constraint:

```text
ALLOW readDocument
    = method policy hasAuthority("document:read")
      AND resource belongs to verified tenant
      AND (owner OR ACL READ OR explicit tenant-wide grant)
      AND state permits reading
```

Implementation choices:
- `@PreAuthorize` calling `@documentPolicy.canRead(authentication, #id)` for pre-method checking.
- Or loading the scoped entity and checking policy inside the service.
- Or combining both while avoiding duplicate DB reads and TOCTOU.
- `@PostAuthorize` can help on read `returnObject`, yet does not guard side effects before the body.

Never conclude "method has an annotation = safe" until data scoping is verified.

## 24. Without Default-Deny, What Must Code Reviews Check?

If a project chooses annotation-driven opt-in (without class-level deny), the review checklist should include:
- List of service methods considered public entry points.
- List of methods protected via HTTP and other call paths.
- Proof method annotations are enabled.
- Tests for sensitive use cases and under-privileged actors.
- Separate policies for owner/tenant/ACL and state.
- Checks for whether a new service can be called from batch/job/listener code.
- No self-invocation bypassing security.
- Alignment between controllers/resolvers/listeners and application services.
- Updated tests whenever a new method/endpoint is added.

For larger teams, add lint/ArchUnit rules:
- Public methods in `application.command` packages must carry an effective annotation or policy wrapper.
- Exceptions for pure helpers are explicitly documented.
- Controllers do not call sensitive repositories directly.
- Commands perform no side effects prior to authorization.
- Privileged methods must have negative tests.

A static scanner that does not understand full proxy semantics and security configuration cannot guarantee absolute coverage. Use it as a *guardrail*, not proof.

## 25. 401, 403, and Unclear Configuration Errors

A method denied by `@PreAuthorize` normally throws `AccessDeniedException` or a related subtype; when propagating through HTTP and matching `ExceptionTranslationFilter`/handlers, authenticated users lacking permission typically receive 403. Anonymous callers hitting routes requiring login usually get 401 (bearer) or a redirect (form login). Looking only at HTTP status does not reveal which pointcut denied.

Commonly confused test causes:
- 403 due to missing CSRF token on POST/PATCH, not default-deny.
- 404 due to missing controller, not proving a deny rule.
- 403 due to owner/tenant domain policy, not proving `@PreAuthorize` ran.
- 401 due to bearer authentication before the method.
- Unproxied method whose body throws `AccessDeniedException` manually; the annotation may not have participated at all.
- Test using an over-privileged user that ALLOWS even when the rule is too broad.

Use mocks/spies to verify **the method body did not run** when a pre-rule denies, and check that data/side effects remain unchanged. When debugging, inspect chain/advisor logs without logging credentials or private data.

## 26. Do Not Put `@DenyAll` "Everywhere" and Open Holes Ambiguously with Other Annotations

An error-prone design:

```java
@PreAuthorize("denyAll()")
public class SensitiveService {
    @PermitAll
    public String status() {
        return "OK";
    }
}
```

If JSR-250 is enabled, `@PermitAll` has its own interceptor; it does not override class-level `@PreAuthorize("denyAll()")` by default. Spring can evaluate both decisions per each advisor's semantics. This is **not** a reliable way to open an exception.

Use the same annotation family to override:

```java
@Service
@PreAuthorize("denyAll()")
public class SensitiveService {

    @PreAuthorize("permitAll()")
    public String status() {
        return "OK";
    }
}
```

Even when the override succeeds, the method can still be blocked by HTTP auth or another custom pointcut advisor. Test on the exact app version.

If you do not want public and private security policies mixed in one bean, split them into separate beans to simplify policies. Avoid overlapping or conflicting annotations just to force a test to pass.

## 27. Which Coverage Model Fits Each System?

| Model | Default Assurance Level | Risks and Requirements |
| --- | --- | --- |
| Per-method opt-in annotation | Unannotated methods usually have no corresponding method guard | Must inventory entry points; need HTTP catch-all and domain policies |
| Class-level `@PreAuthorize("denyAll()")` | Un-overridden methods deny when proxy advice runs | Must review overrides, test self-invocation, separate helpers |
| Class-level `@PreAuthorize("isAuthenticated()")` | Un-overridden methods require authentication | Insufficient for privileged commands; state owner/ACL explicitly |
| Custom service pointcut advisor | Matching methods get checked even without annotations | Can miss packages/beans, ANDs with annotations; version/proxy QA |
| HTTP default deny | Blocks undeclared routes in the chain | Does not protect jobs/queues/direct service calls; chain fallback needed |
| Domain service policy | Checks actor-resource-context right before use | Must be invoked from every entry point; manage transactions/concurrency |

There is no single switch that "denies every Spring method by default" while remaining safe and compatible with every bean. The best policy is chosen per **use-case boundaries**, backed by proper test evidence.

## 28. Checklist Before Marking a Service Fully Protected

1. Is `@EnableMethodSecurity` enabled in the real app context?
2. Are the annotation groups actually in use enabled (`@Secured`, JSR-250)?
3. For every critical method, does the effective annotation/pointcut live on the method, class, interface, or a custom advisor?
4. Do unannotated methods actually have a class-level default?
5. Do same-type method-level overrides include all required permission conditions?
6. Do cross-family `@PermitAll`/`@DenyAll` annotations create false override assumptions?
7. Does any custom pointcut match the real classes/packages/methods?
8. Are Spring beans/proxies used at every entry point?
9. Are there any self-invocation, `private`/`final` method, or `new`-object bypasses?
10. Does HTTP `anyRequest`/fallback chain block unlisted routes?
11. Are there non-HTTP paths (jobs, queues, GraphQL, events) invoking the operation?
12. Are roles/authorities enough, or are owner/tenant/ACL/state checks also needed?
13. Do any side effects execute before authorization?
14. Do transactions, locking, and policy updates prevent TOCTOU?
15. Have anonymous, low-privilege, authorized, and cross-tenant actors all been tested?
16. Are tests confirming a user with the right role but wrong object is DENIED?
17. Are tests confirming a newly added unannotated method in a default-deny class is DENIED?
18. Are tests confirming a new controller without HTTP rules is properly blocked?
19. Do error handling and auditing keep sensitive data confidential on DENY?
20. Does security configuration in staging/prod match tests (proxies/AOP/role mapping)?

### Self-Check Questions

**Question 1.** Only `@EnableMethodSecurity` is present; a public method in a Spring service has no effective security annotation. Does Spring deny it by default?  
→ **No.** Annotation-based interceptors only protect points matching their rules/pointcuts.

**Question 2.** A class has `@PreAuthorize("denyAll()")`, and a method declares no annotation of its own. When called through the proxy, can the body run?  
→ **No**, if the `@PreAuthorize` interceptor is enabled and executes properly.

**Question 3.** A class has `@PreAuthorize("denyAll()")`, and a method has `@PreAuthorize("hasRole('USER')")`. Are both ANDed or does the method override?  
→ For the **same `@PreAuthorize` type**, the method-level rule takes precedence/overrides class-level.

**Question 4.** Is using `@PermitAll` to open a method inside a `@PreAuthorize("denyAll()")` class always effective?  
→ **Never assume so.** Those are two different interceptor types; to override clearly, use method-level `@PreAuthorize("permitAll()")` and test it.

**Question 5.** HTTP has `anyRequest().denyAll()`. Will a job calling an unannotated service method directly be blocked by the HTTP rule?  
→ **No.** Jobs do not pass through the HTTP filter chain.

**Question 6.** An annotated method is called via `this.securedMethod()`. Is method security guaranteed to block it?  
→ **No** in standard proxy-AOP; self-invocation can bypass advice.

**Question 7.** A custom pointcut requires `ROLE_USER` on `*Service`. Does it protect every class under subpackages?  
→ Not by default. Inspect the exact pointcut expression and packages.

**Question 8.** `@PostAuthorize("denyAll()")` is placed on a money-transfer method. Does it guarantee no transfer occurs on DENY?  
→ **No.** Checking after the body can be too late.

**Question 9.** A method already has `@PreAuthorize("hasAuthority('document:read')")`; can callers read every document ID?  
→ **No.** You need an owner/tenant/ACL/status domain policy.

**Question 10.** Is a 403 from a controller for an unannotated method sufficient proof of method default-deny?  
→ **No.** The 403 could come from HTTP/CSRF/domain checks; test the service bean proxy directly and identify the denial source.

## Conclusion

In Spring Security, **a method lacking an effective security annotation is not automatically DENIED just for missing an annotation**. `@EnableMethodSecurity` enables interception for registered annotations/pointcuts; class/interface annotations or custom advisors can protect a method even when the method line itself has no annotation. To prevent missed operations, combine **HTTP catch-all rules**, **class-level default-deny or well-scoped service pointcuts**, **actor–resource domain policies**, and **negative integration tests across real call paths**. A policy that looks right in source code yet is bypassed via proxies, jobs, new controllers, or tenant queries is not complete protection.

## Official References

1. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — confirms unannotated methods, inheritance, pointcuts, and interceptors.
2. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — `anyRequest` fallbacks and HTTP authorization.
3. [Spring Security 6.5 — Method Security Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html#method-security-architecture) — `AuthorizationManagerBeforeMethodInterceptor`.
4. [Spring Security 6.5 — Spring AOP / Pointcut Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html#using-custom-pointcuts) — custom `Advisor`.
5. [Spring Security 6.5 — Test Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html) — `@WithMockUser` and method security tests.
6. [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html) — Spring Security filters and chain selection.
