# @Secured, @RolesAllowed, and Choosing Based on Supported Configuration

## 1. Core Question: Which Annotations Does Spring Security Actually Enforce?

In Spring Security, **method security** checks permissions when code calls a method on a Spring-managed bean. This complements HTTP endpoint protection: a service can be called from a controller, scheduler, consumer, or another business flow, so method-level policies help block unauthorized calls right at the processing boundary.

There are three common ways to write rules:

~~~java
@Secured("ROLE_ADMIN")                     // Spring Security, legacy style
@RolesAllowed("ADMIN")                    // Jakarta/Jakarta Security (JSR-250)
@PreAuthorize("hasRole('ADMIN')")         // Spring Security, SpEL
~~~

**The most common misconception:** merely placing an annotation on a method is **not enough**. The application must activate the corresponding method-security interceptor group. With the modern `@EnableMethodSecurity` configuration:

- `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` are supported **by default** once `@EnableMethodSecurity` is enabled, unless disabled via `prePostEnabled = false`.
- `@Secured` is **not enabled by default**. It requires `securedEnabled = true`.
- The JSR-250/Jakarta annotations `@RolesAllowed`, `@PermitAll`, and `@DenyAll` are **not enabled by default**. They require `jsr250Enabled = true`.
- The Spring Security or Spring Boot Starter Security dependency **does not automatically enable method security**. You must activate `@EnableMethodSecurity` or equivalent configuration.

Consequently, a method with `@Secured("ROLE_ADMIN")` can still execute **without any check from that annotation** if the application only declares default `@EnableMethodSecurity`. Other rules (such as an HTTP filter or another enabled annotation) may still block the request, so you must test along the actual call path to confirm which mechanism is enforcing access.

## 2. Comparing the Three Annotation Families

| Criterion | `@Secured` | `@RolesAllowed` | `@PreAuthorize` |
| --- | --- | --- | --- |
| API source | Spring Security, `org.springframework.security.access.annotation.Secured` | Jakarta/JSR-250, `jakarta.annotation.security.RolesAllowed` in Spring Boot 3+/Spring Security 6+ | Spring Security, `org.springframework.security.access.prepost.PreAuthorize` |
| Enabled by | `securedEnabled = true` | `jsr250Enabled = true` | `prePostEnabled = true` (default when using `@EnableMethodSecurity`) |
| Typical syntax | `@Secured("ROLE_ADMIN")` | `@RolesAllowed("ADMIN")` | `@PreAuthorize("hasRole('ADMIN')")` |
| Condition style | List of required authorities; mostly used for roles | List of roles per Jakarta/JSR-250 contract | SpEL expressions, authorities, roles, parameters, policy beans |
| Multiple values | `@Secured({"ROLE_ADMIN", "ROLE_EDITOR"})`: requires **at least one** matching authority | `@RolesAllowed({"ADMIN", "EDITOR"})`: requires **at least one** matching role | `hasAnyRole`, `and`, `or`, bean/custom policies |
| Checking owner, tenant, or object state | Cannot be expressed directly in the annotation | Cannot be expressed directly in the annotation | Can use parameters and policy beans, e.g. `@policy.canRead(authentication, #p0)` |
| Supported family | `@Secured` only | `@RolesAllowed`, `@PermitAll`, `@DenyAll` | `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` |
| Selection guidance | Mainly for maintaining legacy systems and simple policies | Use when a project prefers standard Jakarta/JSR-250 annotations | Usually the preferred choice for new Spring Security code |

**There is no "automatic" conversion between annotation styles.** Migrating from `@Secured("ROLE_ADMIN")` to `@RolesAllowed("ADMIN")` requires checking role prefixes and config flags. Migrating to `@PreAuthorize` requires attention to SpEL syntax, method scope, and access tests.

Although `@Secured` is often called *legacy*, it remains supported when explicitly activated. "Legacy" here refers to design direction: Spring Security now recommends `@PreAuthorize` because it can express richer policies.

## 3. Enabling the Right Annotation Group with @EnableMethodSecurity

A modern Spring Security Java configuration class can enable all three groups:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfiguration {
}
~~~

This configuration is **for use in a Spring/Spring Boot project** with the appropriate dependencies on the classpath; it is not a standalone plain Java file compiled directly with `javac`. In Spring Boot 3+ and Spring Security 6+, JSR-250 annotations use the `jakarta.annotation.security` package rather than the older Java EE `javax.annotation.security` import.

Common configurations:

| Configuration | `@PreAuthorize` | `@Secured` | `@RolesAllowed` and JSR-250 |
| --- | --- | --- | --- |
| `@EnableMethodSecurity` not enabled | No method-security interceptor provided by this annotation | No | No |
| `@EnableMethodSecurity` | **Enabled** | Disabled | Disabled |
| `@EnableMethodSecurity(securedEnabled = true)` | **Enabled** | **Enabled** | Disabled |
| `@EnableMethodSecurity(jsr250Enabled = true)` | **Enabled** | Disabled | **Enabled** |
| `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)` | **Enabled** | **Enabled** | **Enabled** |
| `@EnableMethodSecurity(prePostEnabled = false, securedEnabled = true)` | Disabled | **Enabled** | Disabled |
| `@EnableMethodSecurity(prePostEnabled = false, jsr250Enabled = true)` | Disabled | Disabled | **Enabled** |

Keep two things in mind:

1. **Annotation flags apply across the entire application context**, not per service. When turning on `securedEnabled` in a large project, pre-existing `@Secured` annotations may immediately start blocking calls. Inventory and test before deploying.
2. Do not enable all three groups "just in case" if there is no need: each group adds interceptors and semantics to maintain. Choose the annotation set your team actually uses and enforce it with tests.

### Example Configurations by Goal

**New project using only `@PreAuthorize`:**

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

**Existing project using `@Secured`, not yet ready to migrate everything to SpEL:**

~~~java
@Configuration
@EnableMethodSecurity(securedEnabled = true, prePostEnabled = false)
class MethodSecurityConfig {
}
~~~

In the second example, `prePostEnabled = false` is a **deliberate choice** to keep only `@Secured`. If any `@PreAuthorize` annotations are still needed, do not disable that flag.

**Project using standard JSR-250 while keeping `@PreAuthorize` for complex exceptions:**

~~~java
@Configuration
@EnableMethodSecurity(jsr250Enabled = true)
class MethodSecurityConfig {
}
~~~

`@PreAuthorize` remains enabled by default; JSR-250 is added alongside it. There is no requirement to also use `@Secured`.

## 4. Mechanism: How Does an Annotation Become an Authorization Decision?

Modern Spring Security uses interceptors/`AuthorizationManager` components corresponding to each annotation group:

| Annotation | Decision-making component |
| --- | --- |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor#preAuthorize` and `PreAuthorizeAuthorizationManager` |
| `@Secured` | `AuthorizationManagerBeforeMethodInterceptor#secured` and `SecuredAuthorizationManager` |
| `@RolesAllowed`, `@PermitAll`, `@DenyAll` | `AuthorizationManagerBeforeMethodInterceptor#jsr250` and `Jsr250AuthorizationManager` |
| `@PostAuthorize` | After-method interceptor with `PostAuthorizeAuthorizationManager` |

Typical flow for a method annotated with `@Secured("ROLE_ADMIN")` when `securedEnabled` is enabled:

~~~text
A Spring bean calls a protected bean's method through its proxy
    |
    v
Method-security advisor/interceptor sees @Secured
    |
    v
Reads Authentication / GrantedAuthority from SecurityContext
    |
    v
SecuredAuthorizationManager evaluates ROLE_ADMIN policy
    |
    +-- Insufficient permissions --> denies (method body not called)
    |
    +-- Authorized --------------> allows method body execution
~~~

JSR-250 and pre/post annotations are enforced via their respective interceptors as well. When the caller lacks permission, the call may raise `AccessDeniedException`/`AuthorizationDeniedException` depending on version and handling path. In HTTP requests, Spring Security can map this to 401/403 based on authentication state and exception handling; in scheduled tasks or message handlers, the application must handle the exception appropriately.

**A method with no annotation and no matching policy is generally not protected automatically by method security.** To stay fail-closed, design request-protection boundaries, business policies, and tests for sensitive methods instead of assuming `@EnableMethodSecurity` makes every service require permission by default.

## 5. Roles and GrantedAuthority: The Most Frequent Source of Bugs

In Spring Security, `Authentication#getAuthorities()` returns `GrantedAuthority` instances, typically strings like `ROLE_ADMIN`, `ROLE_REVIEWER`, or `invoice:read`. **A role is a convention for representing an authority**, usually prefixed with `ROLE_`; which authorities exist depends on where accounts/JWTs/sessions are mapped to authorities.

With the **default role prefix configuration**:

| Annotation/expression | Required authority | Explanation |
| --- | --- | --- |
| `@Secured("ROLE_ADMIN")` | `ROLE_ADMIN` | Declares authority using `@Secured`'s standard string |
| `@Secured("ADMIN")` | `ADMIN` | Does not infer `ROLE_ADMIN` from `ADMIN` in default `@Secured` usage |
| `@RolesAllowed("ADMIN")` | `ROLE_ADMIN` | JSR-250 applies the default role prefix |
| `@RolesAllowed({"ADMIN", "REVIEWER"})` | Either `ROLE_ADMIN` or `ROLE_REVIEWER` | Role list has OR semantics |
| `@PreAuthorize("hasRole('ADMIN')")` | `ROLE_ADMIN` | `hasRole` applies the default role prefix |
| `@PreAuthorize("hasAuthority('ROLE_ADMIN')")` | `ROLE_ADMIN` | Exact authority match |
| `@PreAuthorize("hasAuthority('invoice:read')")` | `invoice:read` | Plain permission string, no `ROLE_` added |

Do not think of `@RolesAllowed("ADMIN")` as checking some `user.role == "ADMIN"` DB column; it checks the `Authentication` normalized by Spring Security into granted authorities. Your application's stored role value might be `ADMIN`, but mapping it to `ROLE_ADMIN` must be designed consistently.

The role prefix **can be configured differently from the default**. If a project customizes `GrantedAuthorityDefaults`, `RoleHierarchy`, `AuthorizationManager`, or authority mapping, verify the exact semantics in your version. Do not mix prefixed and unprefixed role names without clear rules; different managers may handle prefixes differently.

### Multiple Roles: OR or AND?

~~~java
@Secured({"ROLE_EDITOR", "ROLE_ADMIN"})
public String edit() { return "ok"; }

@RolesAllowed({"EDITOR", "ADMIN"})
public String review() { return "ok"; }

@PreAuthorize("hasRole('EDITOR') and hasAuthority('document:publish')")
public String publish() { return "ok"; }
~~~

These are **illustrative Spring method snippets**, not a standalone Java program. The first two annotations allow users holding **either** listed role/authority. The third `@PreAuthorize` expression requires **both conditions** because it uses `and` in SpEL.

To require multiple distinct permissions—such as being a manager, holding `document:publish`, and owning the resource—use `@PreAuthorize` (or a policy bean) instead of trying to force AND semantics into an `@Secured`/`@RolesAllowed` value array.

## 6. Service Example Using All Three Annotation Families

This is an **illustrative class integrated into a Spring application** with `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)`. The app must have Spring Security and Jakarta Annotations on the classpath. Do not compile this example standalone with `javac` without libraries.

~~~java
import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;

import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Secured("ROLE_ADMIN")
    public String adminSummary() {
        return "Admin summary";
    }

    @RolesAllowed({"ANALYST", "ADMIN"})
    public String analystSummary() {
        return "Analyst summary";
    }

    @PreAuthorize("hasAuthority('report:download')")
    public String downloadReport(String id) {
        return "Report " + id;
    }

    @PermitAll
    public String publicDescription() {
        return "Public report description";
    }

    @DenyAll
    public String retiredExport() {
        return "Should never be returned when JSR-250 is enforced";
    }
}
~~~

Meaning of each method:

1. `adminSummary` can only be invoked when `@Secured` is **enabled** and the principal holds `ROLE_ADMIN`.
2. `analystSummary` allows principals with `ROLE_ANALYST` or `ROLE_ADMIN` under the default JSR-250 convention when `jsr250Enabled` is active.
3. `downloadReport` requires the exact authority `report:download`; this snippet **does not yet** check access on the specific report `id`. With real data, add tenant/owner/ACL checks in the service/policy and scope repositories by tenant.
4. `publicDescription` is allowed by JSR-250 `@PermitAll` at the **method layer**; this does not mean the HTTP route calling this method is public. HTTP filters may require authentication beforehand.
5. `retiredExport` is blocked by `@DenyAll` when JSR-250 is enabled; the string return in the body does not execute through calls guarded by the Spring proxy.

If `jsr250Enabled = false`, `@RolesAllowed`, `@PermitAll`, and `@DenyAll` are not enforced by the JSR-250 interceptor. This is especially dangerous with `@DenyAll`: the code looks locked down, yet is not actually protected by that annotation.

### Checking at Which Layer?

- HTTP filters can block `/reports/admin` early by role; method security remains valuable when the service is invoked from multiple entry points.
- `@Secured` and `@RolesAllowed` primarily check coarse roles/permissions at the method boundary.
- **Record-level** permissions such as "only the report owner or shared member may view this ID" require inspecting the real object. Use `@PreAuthorize` with a policy bean or controlled checks in the service, and scope repositories by tenant.
- Placing an annotation on a controller does not protect service calls from schedulers, queues, or other beans. Place rules at the business boundary that needs protection.

## 7. When to Choose @Secured, @RolesAllowed, or @PreAuthorize?

Instead of asking which annotation is "stronger" in the abstract, evaluate the **policy contract**, configurability, and project direction.

| Context | Typical reasonable choice | Reason |
| --- | --- | --- |
| New Spring Security codebase with fine-grained permissions | `@PreAuthorize` | Supports authorities/roles, SpEL, parameters, and policy bean delegation |
| Legacy system already using `@Secured` extensively | Keep `@Secured`, enable `securedEnabled`, and plan migration if needed | Avoids risky big-bang migration; verify method by method |
| Codebase favoring standard Jakarta/JSR-250 | `@RolesAllowed` + `jsr250Enabled` | Clear role syntax familiar across frameworks |
| Simple role-only authorization needed | `@Secured` or `@RolesAllowed` if standardized | Concise, minimal expressions |
| Policy depends on parameters/owner/tenant/state | `@PreAuthorize` calling a policy bean or service | The two simple role annotations cannot express these conditions |
| Need Jakarta-level method denial | `@DenyAll` + `jsr250Enabled` | Explicit block when JSR-250 is active; verify with tests |
| Want to open a method publicly | `@PermitAll` (JSR-250) or equivalent policy design | Opens only the method boundary; still check HTTP |
| Need to strip elements from collections or check results | `@PreFilter`/`@PostFilter`/`@PostAuthorize` as appropriate | Pre/post family supports these, though data leakage and performance need care |

**Design recommendation:** pick **one primary convention** for the project, e.g. `@PreAuthorize` for new policies; keep `@Secured`/`@RolesAllowed` in tested legacy areas. Coexistence is possible, but document why and which flags are active.

Avoid overly long `@PreAuthorize` expressions with hidden DB queries inside SpEL. When logic grows complex, calling a bean like `@invoicePolicy.canApprove(authentication, #p0)` keeps code clean and lets you unit test the policy independently.

## 8. Mixing Multiple Annotations on One Method: Do Not Guess Precedence

You may encounter code like:

~~~java
@Secured("ROLE_MANAGER")
@PreAuthorize("hasAuthority('invoice:approve')")
public void approve(String invoiceId) {
    // ...
}
~~~

If both interceptor groups are enabled, **both decisions must grant access** for the method to run (AND semantics across different annotation families). A user with `ROLE_MANAGER` lacking `invoice:approve` is still blocked, and vice versa.

Important caveats:

- **Do not mix them just for "two-layer defense"** without documenting the policy: maintainers easily overlook one of the active conditions.
- **Do not repeat the same `@PreAuthorize` on one method.** Write a single expression with `and`/`or`, or delegate to a policy bean.
- JSR-250 `@PermitAll` **is not a command to "ignore all other annotations."** If another `@PreAuthorize` also applies, it can still deny access.
- Annotations may sit on methods, classes, or interfaces. Method-level annotations of the same type often override class-level rules; do not assume parent and child annotations always AND together. With conflicting declarations across multiple interfaces, the framework may fail to resolve a policy and require resolution on the concrete method.
- Different advisors have different execution orders. Never rely on exception/log ordering as a business rule definition; test the final outcome.
- If `prePostEnabled = false` while a method has both `@Secured` and `@PreAuthorize`, only the actually enabled family decides. You cannot assert both protect the method simply by reading source code.

**Choosing a single explicit policy** is usually far better than stacking annotations ad hoc. For complex rules, a policy bean can evaluate all conditions and return an explainable, testable decision.

## 9. Runtime Pitfalls Related to Spring AOP/Proxies

In standard setups, Method Security works via Spring AOP. Thus, annotations take effect only when calls genuinely travel through the advice wrapping that bean.

### 9.1. Self-Invocation

~~~java
@Service
class InvoiceService {

    public void outer() {
        approveInvoice("inv-1"); // this.approveInvoice(...): internal call
    }

    @Secured("ROLE_ADMIN")
    public void approveInvoice(String id) {
        // business logic
    }
}
~~~

This is a **mechanism illustration**, not a standalone runnable program. When `outer()` calls `approveInvoice()` on the same instance, the call can **bypass the proxy**, so `@Secured` is not checked by the interceptor at this boundary.

The proper fix is having another bean call the public method through the Spring proxy, extracting the protected use case to a separate bean, or enforcing explicit domain policy checks in the service. Do not try to "fix" this merely by adding `@EnableMethodSecurity(securedEnabled = true)` if the call path still bypasses the proxy.

### 9.2. Not Every Object Is a Spring Bean

- An object instantiated with `new InvoiceService()` is not Spring-managed → no method-security proxy applies.
- Private/final methods or final classes under certain proxy strategies may not be advised as expected. Check proxy mode, bean types, public visibility, and integration tests rather than guessing.
- Calling helpers or other repositories directly can bypass annotated methods. Define business boundaries that **all entry points** traverse.
- Async calls, background jobs, or consumers typically lack an HTTP request `SecurityContext`; establish a trusted service principal and propagated context, or apply a dedicated system policy.

### 9.3. Method Level and HTTP Endpoints Are Independent Layers

A method with `@RolesAllowed("ADMIN")` does not mean the outer controller has proper request authorization or CSRF configured. An HTTP endpoint with `hasRole("ADMIN")` does not mean the service is protected when invoked outside HTTP. Design both layers for business needs, especially for tenant/ownership-scoped data.

## 10. Standalone Java 17 Demo: Self-Verifying Authority Names and Role Prefixes

To observe the difference between `@Secured`'s **exact authority string** and `@RolesAllowed`'s **prefixed role** under default config, the following pure Java program simulates the matching rules. This is a **learning model**, using no Spring libraries and not replacing real interceptors/`AuthorizationManager`s. It illustrates authority string semantics alone.

Create **`MethodRolesDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Set;

public class MethodRolesDemo {
    static boolean secured(Set<String> granted, String... required) {
        return Arrays.stream(required).anyMatch(granted::contains);
    }

    static boolean rolesAllowed(Set<String> granted, String... roles) {
        return Arrays.stream(roles)
                .map(role -> role.startsWith("ROLE_") ? role : "ROLE_" + role)
                .anyMatch(granted::contains);
    }

    static boolean hasAuthority(Set<String> granted, String authority) {
        return granted.contains(authority);
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of("ROLE_ADMIN", "invoice:read");
        System.out.println("@Secured ROLE_ADMIN: " + secured(granted, "ROLE_ADMIN"));
        System.out.println("@Secured ADMIN: " + secured(granted, "ADMIN"));
        System.out.println("@RolesAllowed ADMIN: " + rolesAllowed(granted, "ADMIN"));
        System.out.println("@RolesAllowed USER: " + rolesAllowed(granted, "USER"));
        System.out.println("hasAuthority invoice:read: "
                + hasAuthority(granted, "invoice:read"));
        System.out.println("hasAuthority invoice:write: "
                + hasAuthority(granted, "invoice:write"));
    }
}
~~~

Run with **JDK 17 or newer**:

~~~bash
javac --release 17 MethodRolesDemo.java
java MethodRolesDemo
~~~

**Exact stdout:**

~~~text
@Secured ROLE_ADMIN: true
@Secured ADMIN: false
@RolesAllowed ADMIN: true
@RolesAllowed USER: false
hasAuthority invoice:read: true
hasAuthority invoice:write: false
~~~

Outcome:

1. The principal has `ROLE_ADMIN`, so the `@Secured("ROLE_ADMIN")` simulation returns `true`.
2. The string `ADMIN` is absent from the granted set, so `@Secured("ADMIN")` simulates `false`; no prefix is inferred.
3. The `@RolesAllowed("ADMIN")` model converts the role to `ROLE_ADMIN` using the default prefix and returns `true`.
4. The principal lacks `ROLE_USER`, so `@RolesAllowed("USER")` returns `false`.
5. The permission `invoice:read` matches an entry in the set, so `hasAuthority` returns `true`; `invoice:write` is absent, returning `false`.

**Example limitation:** this program does not determine whether `securedEnabled` or `jsr250Enabled` is active, does not read Spring `Authentication`, does not simulate `RoleHierarchy`/custom prefixes, and does not execute Spring AOP. Proving a real annotation works requires **integration tests with ApplicationContext and Spring Security**.

## 11. Testing Enabled Configuration: Don't Just Look at Annotations in Source

Assume the app contains the `ReportService` bean from section 6. To confirm the config is valid, test **through the real Spring bean** with a mock principal instead of calling methods on a manually instantiated object.

Using Spring Test, JUnit Jupiter, and `spring-security-test`, you can illustrate:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ReportServiceSecurityTest {

    @Autowired
    ReportService service;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadSecuredReport() {
        assertEquals("Admin summary", service.adminSummary());
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotReadSecuredReport() {
        assertThrows(AccessDeniedException.class, service::adminSummary);
    }

    @Test
    @WithMockUser(roles = "ANALYST")
    void analystCanReadJsr250Report() {
        assertEquals("Analyst summary", service.analystSummary());
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotReadJsr250Report() {
        assertThrows(AccessDeniedException.class, service::analystSummary);
    }
}
~~~

This test snippet is **integration code inside a Spring Boot project** configured with `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)` and the service above; it requires test dependencies and cannot run with plain `javac` alone. `@WithMockUser(roles = "ADMIN")` builds authority `ROLE_ADMIN` per helper convention, matching the authority setup described earlier.

One especially valuable test during migration is: **before turning on a flag, the legacy annotation does not block; after turning it on, the same call from an unauthorized user must be denied**. However, never deliberately leave a "security disabled" configuration in your main application tests. You can spin up an isolated test context for flag verification while keeping production config locked down.

### Complete Test Matrix

| Enabled config | Method called | Caller | Expected outcome |
| --- | --- | --- | --- |
| `securedEnabled = true` | `@Secured("ROLE_ADMIN")` | Holds `ROLE_ADMIN` | Allow |
| `securedEnabled = true` | `@Secured("ROLE_ADMIN")` | Holds only `ROLE_USER` | Deny |
| `jsr250Enabled = true` | `@RolesAllowed("ANALYST")` | Holds `ROLE_ANALYST` | Allow |
| `jsr250Enabled = true` | `@RolesAllowed("ANALYST")` | Holds only `ROLE_USER` | Deny |
| `prePostEnabled = true` | `@PreAuthorize("hasAuthority('report:download')")` | Holds `report:download` | Allow |
| `prePostEnabled = true` | Same method above | Missing `report:download` | Deny |
| `jsr250Enabled = true` | `@DenyAll` | Admin or any user | Deny |
| `jsr250Enabled = true` | `@PermitAll` (no other rule) | Context-appropriate principal/anonymous | Not blocked by JSR-250 annotation |
| `prePostEnabled = true` and `securedEnabled = true` | Both `@PreAuthorize` and `@Secured` | Satisfies only one condition | Deny |

For a web request, HTTP status codes can also be shaped by authentication/CSRF filters and may not show whether the annotation itself denied access. Testing direct bean invocations with `spring-security-test` verifies method authorization; `MockMvc` tests verify the full HTTP chain.

An important **regression test** is intentionally calling the service from another bean or message handler, since that scenario exposes protections that existed only on controllers. If a method accesses tenant-scoped data, add tenant A vs. tenant B, self-invocation, and side-effect-free denied-path tests.

## 12. Migrating from @EnableGlobalMethodSecurity to @EnableMethodSecurity

In older applications you may find:

~~~java
@EnableGlobalMethodSecurity(securedEnabled = true)
class LegacySecurityConfig {
}
~~~

Modern Spring Security recommends migrating to `@EnableMethodSecurity`. The two annotations do not share the **same defaults**: `@EnableMethodSecurity` enables the pre/post group by default. So to preserve behavior that enables only `@Secured`, the migrated config can be:

~~~java
@EnableMethodSecurity(
    securedEnabled = true,
    prePostEnabled = false
)
class MigratedSecurityConfig {
}
~~~

If `jsr250Enabled = true` was previously used, set the matching flag on `@EnableMethodSecurity`. Do not overlook updating `javax.annotation.security` → `jakarta.annotation.security` imports when upgrading to Spring Security 6+/Spring Boot 3+ and Jakarta EE. Namespace migration requires aligning dependencies, compiler, and related libraries—not just string-replacing imports.

### Safe Migration Sequence

1. **Inventory annotations in use** (`@Secured`, `@RolesAllowed`, `@PermitAll`, `@DenyAll`, `@PreAuthorize`, etc.). Lock down expected decisions with unit/integration tests.
2. **Record current settings:** `securedEnabled`, `jsr250Enabled`, `prePostEnabled`, role prefixes, and where `GrantedAuthority` instances are populated.
3. **Choose the target configuration** and decide whether to preserve exact semantics or intentionally revise policies. Never silently shift from role-OR to role-AND.
4. **Upgrade API imports** appropriately, verifying required Jakarta dependencies and authority mapping from tokens/sessions/databases.
5. **Test on real Spring beans**, covering denied paths, class/interface-level annotations, combined annotations, self-invocation, and schedulers/consumers if applicable.
6. **Deploy with runtime verification:** confirm unprotected methods did not accidentally turn public and sensitive endpoints were not opened by flag changes.

XML configuration also has an equivalent option:

~~~xml
<sec:method-security secured-enabled="true" jsr250-enabled="true" />
~~~

This XML snippet applies only when an application actually uses the Spring Security XML namespace; with Java config, `@EnableMethodSecurity` is simpler.

## 13. Common Errors and Symptom-Based Troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `@Secured` does not block ordinary users | `securedEnabled` not enabled | Audit `@EnableMethodSecurity` and test denied paths |
| `@RolesAllowed` has no effect | `jsr250Enabled` not enabled, wrong imports/dependencies | Check config, Jakarta package, and test through bean |
| `@DenyAll` appears "ignored" | JSR-250 interceptor not enabled or call bypasses proxy | Enable `jsr250Enabled`, test direct bean invocation |
| Admin denied despite seemingly having role | Principal has `ADMIN` instead of `ROLE_ADMIN`, or broken role mapping | Log authorities in a safe test environment; check prefixes |
| `@Secured("ADMIN")` rejects admin | `@Secured` matches exact declared authority name | Use the actual granted authority string, usually `ROLE_ADMIN` |
| `@PreAuthorize` stops running after migration | `prePostEnabled = false` | Verify migration intent and new flags |
| Multiple annotations cause unexpected denials | Different interceptors all apply; AND semantics | Write a unified policy and test each permission |
| Blocked from controller, yet internal calls still run | Self-invocation bypasses proxy | Split bean, call via Spring proxy, or use domain policy |
| HTTP route public despite annotated method | Endpoint skips protected method/bean or method advice disabled | Test HTTP → controller → service flow |
| Annotation only on interface behaves oddly at runtime | Proxy, inheritance, or conflict between interfaces/classes | Check how Spring resolves annotations and test concrete implementation |
| Job/consumer reports missing `Authentication` | No HTTP SecurityContext exists | Design a principal/service identity and policy for background work |
| Dependency update breaks `javax`/`jakarta` imports | Incomplete Jakarta EE upgrade | Align dependencies, source imports, and tests |

### Concise Debugging Workflow

1. Identify **which exact method**, bean, and proxy type are being called.
2. Inspect **annotations** on the actual method/class/interface, including annotations from other families that may apply together.
3. Read the exact **activation flags** on `@EnableMethodSecurity`. Do not infer enforcement just from seeing Spring Security dependencies in Gradle/Maven.
4. Inspect `Authentication#getAuthorities()` on the test principal and active role prefix.
5. Write tests with both an authorized user and an unauthorized user; observe whether the method body runs on denial.
6. Check non-HTTP call paths, self-invocation, and whether an HTTP filter blocked the request before reaching the method.
7. After fixing, re-run regression tests for enabled annotation families and sensitive services.

## 14. Self-Check Questions

**Question 1.** An application declares only `@EnableMethodSecurity`. A method has `@Secured("ROLE_ADMIN")`. Does this annotation automatically block users lacking the role?

**Answer:** There is no guarantee from `@Secured` because `securedEnabled` defaults to false. Other protective rules might still deny it. Enable `@EnableMethodSecurity(securedEnabled = true)` and test.

**Question 2.** An app has `@EnableMethodSecurity(jsr250Enabled = true)` and a principal with `ROLE_ANALYST`. Is a `@RolesAllowed("ANALYST")` method allowed at the JSR-250 layer?

**Answer:** Yes, under the default role prefix and assuming no other annotation/rule blocks it.

**Question 3.** A principal holds `ROLE_ADMIN`, and a method uses `@Secured("ADMIN")`. Is the result equivalent to `@RolesAllowed("ADMIN")`?

**Answer:** Not necessarily. With default authority matching, `@Secured("ADMIN")` does not automatically prepend `ROLE_`; `@RolesAllowed("ADMIN")` uses the role prefix convention. Always check actual authorities and prefix configuration.

**Question 4.** Both `@Secured("ROLE_ADMIN")` and `@PreAuthorize("hasAuthority('invoice:approve')")` sit on a method, with both interceptors enabled. Is holding only `ROLE_ADMIN` enough?

**Answer:** No. Both the admin role and the `invoice:approve` authority are required because annotations from different families must all be satisfied.

**Question 5.** A service method uses `@PermitAll`, yet the HTTP filter enforces `authenticated()`. Will an anonymous user calling the endpoint definitely succeed?

**Answer:** No. `@PermitAll` at the method layer does not alter HTTP rules; the request can be rejected before reaching the method.

**Question 6.** Why does a test with `@WithMockUser(roles = "ADMIN")` pass while production using JWT returns 403?

**Answer:** The test helper creates authority `ROLE_ADMIN`, whereas the production JWT converter might emit `ADMIN`, `SCOPE_admin`, or another string. Inspect official authority mappings and prefixes in both environments; never fix by loosening permissions indiscriminately.

## 15. Annotation Selection Checklist

- [ ] Determined whether the policy is simple role-based or depends on resource/parameter/tenant.
- [ ] Selected the project's primary annotation family based on actual requirements.
- [ ] Enabled the **exact** flags needed: `securedEnabled`, `jsr250Enabled`, and/or `prePostEnabled`.
- [ ] Verified `jakarta.annotation.security` packages and dependencies when using JSR-250.
- [ ] Standardized the `ROLE_` prefix, `GrantedAuthority` naming, and mappings from tokens/user stores.
- [ ] Avoided accidentally mixing annotations that create undocumented AND policies.
- [ ] Tested security advice via Spring beans/proxies rather than manually instantiated objects.
- [ ] Added tests for both **ALLOW** and **DENY**, including methods locked down with `@DenyAll` if used.
- [ ] Reviewed HTTP filters, method security, and resource-level policies across every call path.
- [ ] When migrating, verified the change in default `prePostEnabled` behavior.
- [ ] Never opened sensitive endpoints just because an annotation was ignored or a role prefix mismatched.

**Takeaway:** `@Secured` is Spring Security's legacy option; `@RolesAllowed` belongs to JSR-250/Jakarta; `@PreAuthorize` is more flexible with authorization expressions. **Spring Security enforces an annotation only when its corresponding interceptor is enabled and the call crosses a protected boundary.** Choosing wisely requires matching config flags, accurate authority/role strings, and negative-path tests.

### Official References

- Spring Security — Method Security (configuration, `@Secured`, JSR-250, `@PreAuthorize`, interceptors): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — `@EnableMethodSecurity` Java API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html
- Spring Security — Method Security namespace/flags: https://docs.spring.io/spring-security/reference/servlet/appendix/namespace/method-security.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
