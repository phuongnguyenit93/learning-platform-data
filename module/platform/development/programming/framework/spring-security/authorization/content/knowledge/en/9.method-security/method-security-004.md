# `securedEnabled`, `jsr250Enabled`, and the Scope of Activated Annotations

## 1. Why Can an Annotated Method Still Execute?

In Spring Security, placing a security annotation on a service is **not enough** to conclude that the method is already protected by authorization checks. An annotation only takes effect when **method security is enabled**, that annotation type **is configured as active**, the invocation **passes through the interception mechanism**, and the authentication context/policy matches.

For example, suppose an application has two methods:

```java
@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceView read(long id) { ... }

@Secured("ROLE_ADMIN")
public void rebuildAllIndexes() { ... }
```

If the application only declares `@EnableMethodSecurity` with default settings:

- `@PreAuthorize` is enabled and can block users lacking `invoice:read`.
- `@Secured` **is not enabled yet**: this annotation alone creates no method security check.
- If `rebuildAllIndexes()` is invoked through a path with no other guard, it can execute even if the user is not an admin.

Similarly, if a service has `@RolesAllowed("ADMIN")` or `@DenyAll` while `jsr250Enabled=false`, those JSR-250 annotations are not processed by their corresponding interceptor. This is an especially dangerous bug in code migrated from a Java EE/Jakarta EE system or an older Spring Security configuration.

**Core lesson:** `securedEnabled` and `jsr250Enabled` are not permissions granted to users. They are **switches that turn on groups of annotation-checking mechanisms** in Spring Security. Turning a switch off means *the corresponding checker is not registered*, not that the method becomes "deny by default".

## 2. Exact Table of the Three Flag Groups of `@EnableMethodSecurity`

For `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity` in Spring Security 6.5, the default values confirmed by JavaDoc are:

| Flag | Default | Annotation Group Enabled When True | Effect When False |
| --- | --- | --- | --- |
| `prePostEnabled` | `true` | `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` | Does not register standard interceptors for the pre/post group |
| `securedEnabled` | `false` | `@Secured` | Does not register the standard interceptor for `@Secured` |
| `jsr250Enabled` | `false` | `@RolesAllowed`, `@PermitAll`, `@DenyAll` | Does not register the standard interceptor for the JSR-250 group |

Two other important attributes:

- `mode` defaults to `AdviceMode.PROXY`: method security uses the Spring AOP proxy model, so call boundaries matter greatly.
- `proxyTargetClass` defaults to `false`: selects proxy creation per Spring's rules; enabling CGLIB class proxies does not automatically solve all internal calls.

Common configuration for new projects:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Equivalent for the three main flags to:

```java
@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = false,
    jsr250Enabled = false
)
public class MethodSecurityConfig {
}
```

If the project uses both `@Secured` and JSR-250:

```java
@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfig {
}
```

**Distinction:** Spring Boot Starter Security **does not automatically enable method security just because the dependency is present**. You must explicitly declare `@EnableMethodSecurity` (or a supported equivalent activation mechanism). If the application does not enable method security, do not assume any method authorization annotation acts as a default guard.

### 2.1. Four Predictable Configurations

| Declaration | `@PreAuthorize` | `@Secured` | `@RolesAllowed`/`@DenyAll` |
| --- | --- | --- | --- |
| `@EnableMethodSecurity` | Active | Not enabled | Not enabled |
| `@EnableMethodSecurity(securedEnabled = true)` | Active | Active | Not enabled |
| `@EnableMethodSecurity(jsr250Enabled = true)` | Active | Not enabled | Active |
| `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)` | Active | Active | Active |
| `@EnableMethodSecurity(prePostEnabled = false, securedEnabled = true)` | Standard pre/post interceptors not registered | Active | Not enabled |
| Method security not enabled | No corresponding default method guard | None | None |

In the "Not enabled" cells, that **does not mean the request is guaranteed to be allowed**: HTTP security, another enabled annotation group, data policies, or manual checks can still deny it. However, **the disabled annotation itself will not block**.

### 2.2. Why Was Pre/Post Chosen as the Default?

`@PreAuthorize` supports SpEL expressions and can check permissions, roles, method parameters, and policy beans. It is more flexible than classic role-based annotations. Spring Security recommends `@PreAuthorize` for most new use cases; `@Secured` and JSR-250 are useful for legacy compatibility or system annotation conventions.

Enabling all three groups can make sense during migration, though it increases the number of policy styles to review. Any group no longer used should be phased out of code and tests along a plan; **never turn off a switch before locating every annotation depending on it**.

## 3. How Does Method Security Actually Work?

In standard Servlet/Spring configurations, `@EnableMethodSecurity` registers Spring AOP advisors/interceptors. When a call to a **Spring-managed bean** passes through the proxy/advice, the appropriate interceptor retrieves `Authentication` from `SecurityContextHolder`, evaluates the policy, and invokes the real method only if permitted.

```text
Controller / Service / Job
          |
          v
Spring-managed bean proxy
          |
          +-- Is there an advisor for the annotation in use?
          |        |
          |       No -> no method guard for that group
          |        |
          |        v
          |    Before the method:
          |      @PreAuthorize / @Secured / @RolesAllowed /
          |      @DenyAll / @PermitAll
          |        |
          |        +-- DENY -> method body does not run
          |        |
          |        v
          |     Execute method
          |        |
          |        v
          |     After the method:
          |      @PostAuthorize / @PostFilter
          |
          v
     Result or error
```

The diagram above is a **conceptual model**, not a guarantee of exact ordering among all custom interceptors. In Spring Security, the pre/post group and the Secured/JSR-250 groups are handled by their respective `AuthorizationManager`s/interceptors.

### 3.1. Interceptor Map by Group

| Annotation | Typical Interceptor/Manager | Timing |
| --- | --- | --- |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor.preAuthorize()`, `PreAuthorizeAuthorizationManager` | Before the method runs |
| `@PostAuthorize` | `AuthorizationManagerAfterMethodInterceptor.postAuthorize()`, `PostAuthorizeAuthorizationManager` | After the method runs |
| `@PreFilter` | Method security pre-filter interceptor | Before the method processes input collection |
| `@PostFilter` | Method security post-filter interceptor | After the method returns output collection |
| `@Secured` | `AuthorizationManagerBeforeMethodInterceptor.secured()`, `SecuredAuthorizationManager` | Before the method |
| `@RolesAllowed`, `@PermitAll`, `@DenyAll` | `AuthorizationManagerBeforeMethodInterceptor.jsr250()`, `Jsr250AuthorizationManager` | Before the method |

When a group is turned off, the corresponding **standard** interceptors are not registered by that switch. If the application registers custom advisors or AspectJ advice of its own, inspect the actual configuration; do not assume the entire system lacks other checks.

### 3.2. What Is the Scope of "Annotation Activated"?

The flags apply at the **ApplicationContext / method security configuration** level, not per class or per HTTP route. A service does not automatically enable `@Secured` simply by importing the annotation class. Another controller does not get JSR-250 enabled on its own without the corresponding configuration in the application.

Whether a call is intercepted also depends on:

1. Whether the class/method has an annotation belonging to an enabled group.
2. Whether the bean is Spring-managed and has matching advice.
3. Whether the call actually goes through the proxy/weaving.
4. Whether an appropriate `Authentication`/security context exists, or how the manager handles missing identity per policy.
5. Whether no other mechanism intentionally replaces/disables the advisor.
6. Whether annotation inheritance across interfaces, classes, and methods is resolved unambiguously by the framework.

The switch enables the **applicability** of an annotation group, not a promise that every method in the app is protected. A public method without an annotation and without another pointcut/guard can still be called normally.

## 4. `@Secured`: Classic Role/Authority Checking

### 4.1. Import and Syntax

`@Secured` belongs to Spring Security:

```java
import org.springframework.security.access.annotation.Secured;

@Secured("ROLE_ADMIN")
public void rebuildIndexes() {
    // Admin role only per policy.
}
```

For that annotation to work with `@EnableMethodSecurity`:

```java
@Configuration
@EnableMethodSecurity(securedEnabled = true)
class SecuredConfiguration {
}
```

The keyword `securedEnabled` **does not mean** "all services are secured"; it only activates the interceptor for `@Secured`.

### 4.2. Single or Multiple Authorities

Example:

```java
@Secured({"ROLE_ADMIN", "ROLE_SUPPORT"})
public String readSupportOverview() {
    return "support-overview";
}
```

Values in `@Secured` are typically evaluated so that **having one of the listed authorities is sufficient** (OR), rather than requiring the user to hold all of them. A user with `ROLE_SUPPORT` is allowed even without `ROLE_ADMIN`, provided no other guard denies it.

Keep in mind:

- `@Secured` takes **string authority names**, not SpEL expressions.
- Writing `@Secured("hasRole('ADMIN')")` is wrong intent: it does not evaluate `hasRole` as an expression.
- By Spring Security convention, `ROLE_ADMIN` differs from the plain string `ADMIN`; do not assume the role prefix if the project customizes it.
- `@Secured` does not automatically check `invoice.tenantId` or object ownership. It is typically suited for simple functional permission rules.
- If a role hierarchy is used, verify the manager for `@Secured` is configured with the corresponding graph in your version; do not merely check that a `RoleHierarchy` bean exists.

### 4.3. Why Can `@Secured` Still "Have No Effect"?

Common reasons:

1. `securedEnabled=false` (default).
2. `@EnableMethodSecurity` is not enabled.
3. Calling the method via `this.method()` inside the same bean, bypassing the Spring AOP proxy.
4. Instantiating the object with `new` instead of using the Spring bean.
5. Placing the annotation on a private/final method or a proxy type that cannot intercept it properly.
6. Another HTTP rule allows or denies first, so tests do not actually prove method security.
7. The principal carries `ROLE_USER` while the annotation requires `ROLE_ADMIN`.
8. Class/interface annotation configuration is overridden or ambiguous; test the actual method invoked.

Distinguish between **annotation not activated** and **annotation activated and properly denying due to missing permission**. Both situations require different fixes.

## 5. JSR-250: `@RolesAllowed`, `@PermitAll`, and `@DenyAll`

### 5.1. Enabling the Whole Group with `jsr250Enabled`

With Jakarta-based Spring Boot 3.x / Spring Security 6.x:

```java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
```

Enable the group:

```java
@Configuration
@EnableMethodSecurity(jsr250Enabled = true)
class Jsr250Configuration {
}
```

Spring Security then registers the interceptor for all three JSR-250 annotations. **There are no three separate switches** like `rolesAllowedEnabled`, `permitAllEnabled`, `denyAllEnabled` in `@EnableMethodSecurity`. The shared flag is `jsr250Enabled`.

Legacy Java EE / Spring Security 5 projects may contain `javax.annotation.security.*` imports. In Spring Boot 3/Jakarta systems, use `jakarta.annotation.security.*` with compatible dependencies; **do not mix package names across generations** and expect Spring to recognize the annotations.

### 5.2. `@RolesAllowed`

```java
@RolesAllowed({"ADMIN", "MANAGER"})
public List<String> listTeamMetrics() {
    return List.of("team:summary");
}
```

Meaning:

- Either of the two listed roles satisfies the rule (OR).
- With `Jsr250AuthorizationManager`'s default `ROLE_` prefix, `"ADMIN"` maps to `ROLE_ADMIN`, and `"MANAGER"` maps to `ROLE_MANAGER`.
- If the application changes the role prefix, verify the real `GrantedAuthority` names and manager configuration. Do not guess prefixes from a tutorial for a different version.
- `@RolesAllowed` cannot express owner, tenant, or method-parameter conditions like a SpEL expression.

Example user authorities:

```text
Authentication authorities = [ROLE_MANAGER]
@RolesAllowed({"ADMIN", "MANAGER"})
=> Allowed at this JSR-250 guard if enabled and no other guard denies.
```

However, if `jsr250Enabled=false`, the issue is not "denied due to missing role"; **the JSR-250 guard is not registered**, and remaining behavior is decided by other mechanisms.

### 5.3. `@PermitAll`

```java
@PermitAll
public String publicCatalogBanner() {
    return "Welcome";
}
```

When `jsr250Enabled=true` and the call passes through the interceptor, `@PermitAll` means **permitted at that method's JSR-250 check**. It does **not** mean:

- Automatically turning all HTTP `/public/**` routes into `permitAll()`.
- Bypassing another active `@PreAuthorize`.
- Bypassing CSRF, authentication filters, or URL authorization.
- Automatically making sensitive data queried inside the service public.
- Allowing calls through any route in every `SecurityFilterChain`.

In particular, in a web application, if the HTTP path has `denyAll()`, the call will not reach the method even if the method has `@PermitAll`.

If `jsr250Enabled=false`, `@PermitAll` is not processed by the JSR-250 interceptor. Whether the method runs then depends on other protection layers; it must not be recorded as an effective JSR-250 permit.

### 5.4. `@DenyAll`

```java
@DenyAll
public void permanentlyDisabledOperation() {
    throw new IllegalStateException("Should not be invoked");
}
```

When JSR-250 is enabled and the call goes through the proxy, `@DenyAll` denies the call at this interceptor, even for a user with `ROLE_ADMIN`. It is useful for locking an operation or marking an entry point that must not be called yet, except:

- If `jsr250Enabled=false`, **the annotation is no longer a guard**; the method can run if no other check exists.
- If the method is invoked internally via self-invocation without going through the proxy, the guard can be bypassed.
- `@DenyAll` should not be treated as a substitute for completely removing a dangerous feature or closing the HTTP endpoint.

**The most important test when toggling JSR-250:** a method with `@DenyAll` must deny when the flag is on; a test using only an unprivileged user on an HTTP route does not prove that.

### 5.5. Avoid Placing Conflicting JSR-250 Annotations in the Same Location

Do not attach both `@PermitAll` and `@DenyAll` to the same method expecting the framework to guess precedence. Do not put different `@RolesAllowed` on multiple parent interfaces to implicitly "merge permissions". Keep one clear policy source for the same annotation type and test inheritance behavior.

## 6. Pre/Post Annotations and the `prePostEnabled` Flag

### 6.1. `@PreAuthorize`: More Powerful Because It Knows Method Context

```java
@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceView readInvoice(long invoiceId) {
    // Can continue checking tenant/owner in the repository.
}
```

`@PreAuthorize` evaluates a permission expression before the method runs. Besides authorities, it can reference parameters or policy beans for object-level authorization, for example:

```java
@PreAuthorize(
    "hasAuthority('invoice:read') and @invoicePolicy.canRead(authentication, #invoiceId)"
)
public InvoiceView readInvoice(long invoiceId) {
    // Only return data verified by tenant.
}
```

This is an **integration fragment**, assuming an `invoicePolicy` bean is defined and `canRead(...)` has an appropriate contract/performance/security guarantees. Using parameter names in expressions depends on parameter-name discovery at compile time; `-parameters` or a naming annotation may be needed.

If `prePostEnabled=false`, neither snippet above is **executed by the default pre/post interceptor**. Setting `securedEnabled=true` does not bring `@PreAuthorize` back to life.

### 6.2. `@PostAuthorize`: The Return Value Also Participates in the Decision

```java
@PostAuthorize("returnObject.owner == authentication.name")
public InvoiceView findInvoice(long id) {
    return repository.loadView(id);
}
```

`@PostAuthorize` can inspect data **after the method returns a result**. Use it only when running the method before the check is acceptable: data may already have been read or external operations may have occurred.

**Do not use `@PostAuthorize` alone to protect a money transfer, record deletion, or email send**: by the time denial is decided, the side effect may already have executed. For state-changing actions, use pre-checks together with transactions/appropriate data conditions.

### 6.3. `@PreFilter` and `@PostFilter`

```java
@PreFilter("filterObject.owner == authentication.name")
public void submitOwnedInvoices(List<InvoiceCommand> commands) {
    // Non-matching elements may be filtered out beforehand.
}
```

```java
@PostFilter("filterObject.owner == authentication.name")
public List<InvoiceView> listVisibleInvoices() {
    return repository.findAllVisibleCandidates();
}
```

This is **conceptual integration code**, requiring real types, supported collections, and proper Spring Security configuration. Both annotations are only processed when `prePostEnabled=true`.

With large datasets or multiple tenants, filtering collections in memory after querying **should not be the sole data-protection guard**; database queries must restrict tenant/owner/scope. `@PostFilter` can be expensive and still loads out-of-scope data into memory.

### 6.4. When Should `prePostEnabled` Be Turned Off?

Only disable it intentionally when:

- The project replaces standard interceptors with verified custom advisors/managers.
- A migrating application only permits a specific annotation group and has already handled all legacy `@PreAuthorize`/`@PostAuthorize`.
- Security tests confirm every sensitive action still has another guard.

A configuration such as:

```java
@EnableMethodSecurity(
    prePostEnabled = false,
    securedEnabled = true,
    jsr250Enabled = false
)
```

activates `@Secured` without activating pre/post or JSR-250 annotations. This is an **application-wide** policy change, not a harmless performance tweak.

## 7. Spring Boot 3 and Spring Security 6 Integration Sample Configuration

The example shows all three annotation groups working on different methods. These examples are **integration code**, not a standalone file run with `javac`; they require Spring Boot, Spring Security, Jakarta Annotation API dependencies, and real authentication configuration.

### 7.1. A Single Class Enabling Every Needed Group

```java
package demo.security;

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
```

This is the easiest place to review: methods using `@Secured` and JSR-250 **are explicitly enabled** rather than silently omitted by default.

### 7.2. A Service Containing Different Annotation Types

```java
package demo.security;

import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class InvoiceSecurityExamples {

    @PreAuthorize("hasAuthority('invoice:read')")
    public String readInvoice() {
        return "invoice-readable";
    }

    @Secured("ROLE_ADMIN")
    public String adminReindex() {
        return "admin-reindex";
    }

    @RolesAllowed({"MANAGER", "ADMIN"})
    public String managerSummary() {
        return "manager-summary";
    }

    @PermitAll
    public String publicBanner() {
        return "public-banner";
    }

    @DenyAll
    public String disabledLegacyAction() {
        return "should-never-run";
    }

    @Secured("ROLE_ADMIN")
    @PreAuthorize("hasAuthority('invoice:approve')")
    public String approveInvoice() {
        return "invoice-approved";
    }
}
```

Explanation of each method:

1. `readInvoice()` requires `invoice:read` via the pre/post group.
2. `adminReindex()` requires `ROLE_ADMIN` via `securedEnabled=true`.
3. `managerSummary()` allows `ROLE_MANAGER` **or** `ROLE_ADMIN` via JSR-250 and the default role prefix.
4. `publicBanner()` is allowed by its JSR-250 guard, yet an HTTP route or another independent interceptor can still block it.
5. `disabledLegacyAction()` is denied by JSR-250 when called through the proxy; safe only when `jsr250Enabled=true` and the call path is actually intercepted.
6. `approveInvoice()` carries two enabled groups: both `ROLE_ADMIN` and `invoice:approve` must be satisfied. Having only the admin role is insufficient; having only the approve permission is also insufficient.

The last example intentionally illustrates **multiple interceptors applying together**. In production code, you may prefer a single `@PreAuthorize("hasRole('ADMIN') and hasAuthority('invoice:approve')")` so expressions are easier to read and less prone to divergence during migration.

### 7.3. HTTP Security Is a Different Layer, Not a Substitute for Method Switches

An illustrative HTTP configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpRules {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/banner")
                .permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Suppose a controller calls `InvoiceSecurityExamples` via a Spring bean. When a request enters `/api/**`, it must pass both the HTTP rule **and** the corresponding method rule. The fact that HTTP only requires `authenticated()` does not disable `@Secured` or `@RolesAllowed` when those groups are enabled.

Conversely, you cannot fix a `securedEnabled=false` bug by assuming every API currently requires `hasRole("ADMIN")`: a service can be called from a job, a message consumer, or a new HTTP route.

### 7.4. Dependencies and Packages by Version

In Spring Boot 3 / Spring Security 6:

- `@EnableMethodSecurity`: `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity`.
- `@PreAuthorize`: `org.springframework.security.access.prepost.PreAuthorize`.
- `@Secured`: `org.springframework.security.access.annotation.Secured`.
- `@RolesAllowed`, `@PermitAll`, `@DenyAll`: `jakarta.annotation.security.*`, requiring the matching Jakarta Annotation API in dependencies.
- `@WithMockUser` for tests: `org.springframework.security.test.context.support.WithMockUser` from `spring-security-test`.

In Spring 5 documentation or older Java EE code, you may see `javax.annotation.security.*`. Do not copy old imports into a project already moved to Jakarta without verifying dependencies/versions.

## 8. Standalone Java 17: Which Guards Do the On/Off Switches Change?

To clearly see **the difference between an annotation being present and its interceptor being enabled**, the following program simulates group-activation logic without depending on Spring Framework.

Warning: this is **a learning model specific to this lesson**; it does not use real Spring annotations, does not create proxies, and does not explain the application's full HTTP/security context. When a group is off, the model shows **the guard belonging to that group does not check permissions**; in a real application other guards may still exist.

Save the file as `MethodSecurityFlagsDemo.java`:

```java
import java.util.Set;

public class MethodSecurityFlagsDemo {

    enum Rule {
        PRE_READ,
        SECURED_ADMIN,
        JSR_MANAGER,
        JSR_DENY,
        MIXED
    }

    record Flags(
        boolean prePostEnabled,
        boolean securedEnabled,
        boolean jsr250Enabled
    ) {}

    record Actor(
        boolean authenticated,
        Set<String> authorities
    ) {}

    static boolean has(Actor actor, String authority) {
        return actor != null
            && actor.authenticated()
            && actor.authorities() != null
            && actor.authorities().contains(authority);
    }

    static boolean allowed(Flags flags, Rule rule, Actor actor) {
        return switch (rule) {
            case PRE_READ ->
                !flags.prePostEnabled()
                    || has(actor, "invoice:read");

            case SECURED_ADMIN ->
                !flags.securedEnabled()
                    || has(actor, "ROLE_ADMIN");

            case JSR_MANAGER ->
                !flags.jsr250Enabled()
                    || has(actor, "ROLE_MANAGER")
                    || has(actor, "ROLE_ADMIN");

            case JSR_DENY ->
                !flags.jsr250Enabled();

            // Two annotations from two groups both enabled:
            // all active guards must pass.
            case MIXED ->
                (!flags.prePostEnabled()
                    || has(actor, "invoice:read"))
                && (!flags.securedEnabled()
                    || has(actor, "ROLE_ADMIN"));
        };
    }

    static void show(String label, boolean value) {
        System.out.println(label + ": " + value);
    }

    public static void main(String[] args) {
        Flags defaults = new Flags(true, false, false);
        Flags all = new Flags(true, true, true);
        Flags securedOnly = new Flags(false, true, false);

        Actor admin = new Actor(
            true, Set.of("ROLE_ADMIN", "invoice:read")
        );
        Actor manager = new Actor(
            true, Set.of("ROLE_MANAGER", "invoice:read")
        );
        Actor viewer = new Actor(
            true, Set.of("invoice:read")
        );
        Actor anonymous = new Actor(
            false, Set.of()
        );

        show("default pre viewer",
            allowed(defaults, Rule.PRE_READ, viewer));
        show("default pre anonymous",
            allowed(defaults, Rule.PRE_READ, anonymous));
        show("default secured ignored",
            allowed(defaults, Rule.SECURED_ADMIN, viewer));
        show("default jsr roles ignored",
            allowed(defaults, Rule.JSR_MANAGER, viewer));
        show("default jsr deny ignored",
            allowed(defaults, Rule.JSR_DENY, viewer));

        show("all secured viewer",
            allowed(all, Rule.SECURED_ADMIN, viewer));
        show("all secured admin",
            allowed(all, Rule.SECURED_ADMIN, admin));
        show("all jsr manager",
            allowed(all, Rule.JSR_MANAGER, manager));
        show("all jsr viewer",
            allowed(all, Rule.JSR_MANAGER, viewer));
        show("all jsr deny admin",
            allowed(all, Rule.JSR_DENY, admin));
        show("all mixed admin",
            allowed(all, Rule.MIXED, admin));
        show("all mixed manager",
            allowed(all, Rule.MIXED, manager));

        show("secured only pre ignored",
            allowed(securedOnly, Rule.PRE_READ, viewer));
        show("secured only admin",
            allowed(securedOnly, Rule.SECURED_ADMIN, admin));
    }
}
```

Compile and run:

```bash
javac MethodSecurityFlagsDemo.java
java MethodSecurityFlagsDemo
```

Expected stdout:

```text
default pre viewer: true
default pre anonymous: false
default secured ignored: true
default jsr roles ignored: true
default jsr deny ignored: true
all secured viewer: false
all secured admin: true
all jsr manager: true
all jsr viewer: false
all jsr deny admin: false
all mixed admin: true
all mixed manager: false
secured only pre ignored: true
secured only admin: true
```

**Important analysis:**

- With default flags, `PRE_READ` remains active, while `SECURED_ADMIN` and `JSR_MANAGER/JSR_DENY` are ignored in the model.
- The line "default jsr deny ignored: true" **does not recommend allowing** an action marked `@DenyAll`. It exposes the danger: if `jsr250Enabled=false`, the JSR-250 guard does not block on its own.
- When all three flags are on, a user with only `invoice:read` fails `SECURED_ADMIN`; the manager user passes `JSR_MANAGER`; `JSR_DENY` blocks even admin.
- In rule `MIXED`, admin needs **both** `ROLE_ADMIN` and `invoice:read`; a manager with only read permission is not enough.
- The `securedOnly` configuration enables `@Secured` while disabling pre/post: rule `PRE_READ` is ignored in the model.
- The program does not simulate role hierarchies, JSR-250 `@PermitAll`, AOP, 401/403, CSRF, or object security. It only illustrates the effect of **enabling/disabling interceptor groups**.

## 9. Scope of Annotations on Classes, Methods, and Interfaces

### 9.1. Class-Level Annotations

Spring Security method security supports class-level annotations. For example:

```java
@PreAuthorize("hasRole('USER')")
@Service
public class UserOperations {

    public String readOwnSummary() {
        return "own-summary";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String resetAnotherUser() {
        return "reset-done";
    }
}
```

Within the `@PreAuthorize` group, a method-specific annotation **overrides** the class-level rule of the same type: `resetAnotherUser()` uses the admin condition instead of the user default. Therefore, if **both** requirements are wanted, state them explicitly in the expression or policy; do not expect the framework to automatically combine class and method annotations of the same type.

### 9.2. Interfaces and Multiple Annotation Sources

Spring Security can process annotations placed on interfaces/classes/methods; with proxies, inheritance rules must align with the invocation style and how the framework resolves metadata. Documentation notes that when a class inherits conflicting annotations from **two different interfaces**, policy resolution can become ambiguous and startup may fail. The solution is to specify the annotation explicitly on the concrete method.

Do not rely on multiple interfaces with different roles as a way of "merging" permissions:

```java
interface Readable {
    @PreAuthorize("hasAuthority('doc:read')")
    String view();
}

interface AdminOnly {
    @PreAuthorize("hasRole('ADMIN')")
    String view();
}
```

If a class implements both, declare an unambiguous policy on the implementation. Prefer a single policy bean or combined expression when multiple conditions are truly required.

### 9.3. Multiple Annotation Groups on the Same Method

Example:

```java
@Secured("ROLE_ADMIN")
@PreAuthorize("hasAuthority('invoice:approve')")
public void approve(long invoiceId) {
    // Verify creator differs from approver and status is DRAFT.
}
```

If `securedEnabled=true` and `prePostEnabled=true`, both interceptor types can evaluate and execution proceeds only if **neither denies**. Do not assume `@Secured` "wins" over `@PreAuthorize` or vice versa according to an implicit priority order.

If `securedEnabled=false`, only the `@PreAuthorize` part is active. This can **unintentionally widen permissions**: someone with `invoice:approve` but without `ROLE_ADMIN` will no longer be blocked by `@Secured`. Before disabling a flag, audit methods carrying multiple annotation groups and write regression tests.

If `@PermitAll` and `@PreAuthorize` appear together, do not treat `@PermitAll` as a way to override other conditions. Better yet, avoid ambiguous policies and choose one clear expression for one purpose.

### 9.4. Proxies, Self-Invocation, `private`/`final`, and Manually Instantiated Objects

With standard `mode=PROXY`:

```java
@Service
class BillingService {

    public void runBatch() {
        cancelAll(); // Internal call within the same instance.
    }

    @Secured("ROLE_ADMIN")
    public void cancelAll() {
        // Sensitive action.
    }
}
```

The call from `runBatch()` to `cancelAll()` on the same instance can **bypass the Spring AOP proxy**, so `@Secured` is not enforced as intended even when `securedEnabled=true`.

Similarly:

- Objects created with `new BillingService()` do not automatically have Spring interceptors attached.
- `private` methods cannot serve as reliable proxy boundaries for method security; an intercepted public/accessible entry point is needed.
- `final` classes/`final` methods have limitations with class-based proxies; interface proxies and class proxies also have different constraints.
- Kotlin classes/methods can be final by default; check appropriate open/proxy mechanisms or AspectJ.
- `@Async`, background tasks, or message consumers do not automatically carry `SecurityContext` from HTTP requests; establish principal/service identity explicitly.

If intercepting self-invocation is required, Spring Security provides an AspectJ mode via `@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)` when weaving and dependencies are configured properly. **Merely switching the flag to ASPECTJ does not add weaving by itself.**

### 9.5. Enabling Any Annotation Does Not Replace Data Protection

A method with `@Secured("ROLE_ADMIN")` that simply calls `repository.findById(id)` can expose another tenant's data if that admin is actually scoped only to tenant A. Method guards must be complemented by owner/tenant checks, state checks, and query scoping. Functional roles are not object authorization.

## 10. Practical Testing: Confirming Which Group Is Enforced

### 10.1. Test Matrix for the Three Flags

| Configuration | Method | Principal | Expected Method Guard Behavior Alone |
| --- | --- | --- | --- |
| Default | `@PreAuthorize("hasAuthority('invoice:read')")` | Has `invoice:read` | Allowed |
| Default | Same method | Missing permission | Denied |
| Default | `@Secured("ROLE_ADMIN")` | Not admin | This annotation creates no guard |
| Default | `@DenyAll` | Has admin | JSR-250 annotation creates no guard |
| `securedEnabled=true` | `@Secured("ROLE_ADMIN")` | `ROLE_USER` | Denied |
| `securedEnabled=true` | Same method | `ROLE_ADMIN` | Allowed |
| `jsr250Enabled=true` | `@RolesAllowed("MANAGER")` | `ROLE_MANAGER` | Allowed |
| `jsr250Enabled=true` | Same method | `ROLE_USER` | Denied |
| `jsr250Enabled=true` | `@DenyAll` | `ROLE_ADMIN` | Denied |
| All three enabled | `@Secured` + `@PreAuthorize` | Has only one of the two | Denied |
| `prePostEnabled=false` | `@PreAuthorize` | Missing permission | No standard pre/post guard |
| All flags on, self-invocation | Sensitive method called internally | Any | Can bypass proxy; redesign required |

**Note:** "Annotation creates no guard" must not be translated as "HTTP allows it". Test the method directly through the Spring bean/proxy, and build fixtures distinguishing the HTTP layer from the service layer.

### 10.2. Method Integration Testing with JUnit 5 and Spring Security Test

A complete test should load the `@EnableMethodSecurity` configuration and the real service bean, then invoke **through the Spring bean**:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class InvoiceMethodSecurityTest {

    @Autowired
    InvoiceSecurityExamples invoices;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanRunSecuredMethod() {
        assertEquals("admin-reindex", invoices.adminReindex());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotRunSecuredMethod() {
        assertThrows(
            AccessDeniedException.class,
            () -> invoices.adminReindex()
        );
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void deniedForEveryone() {
        assertThrows(
            AccessDeniedException.class,
            () -> invoices.disabledLegacyAction()
        );
    }

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readerCanUsePreAuthorize() {
        assertEquals("invoice-readable", invoices.readInvoice());
    }
}
```

This is **integration test code requiring a real Spring Boot project**, not a standalone Java file. The first test assumes `InvoiceSecurityExamples` and the configuration class enabling all groups are imported. When testing `@RolesAllowed`, add `@WithMockUser(roles="MANAGER")` and a user with only `ROLE_USER` to verify allow/deny.

Note that `@WithMockUser(roles="ADMIN")` creates authority `ROLE_ADMIN`, while `@WithMockUser(authorities="invoice:read")` uses the exact authority name. Test helpers **do not prove** that real JWT/password/IdP authentication mechanisms work. Write separate authentication tests.

### 10.3. Testing That a Disabled Annotation Truly Is Not Checked

Create a dedicated test configuration enabling only defaults:

```java
@Configuration
@EnableMethodSecurity
class DefaultOnlyMethodSecurityConfig {
}
```

Then invoke a bean carrying `@Secured("ROLE_ADMIN")` with a user having only `ROLE_USER`; if there is no other method guard, the call can still run. This test serves as a **negative control** demonstrating how dangerous missing `securedEnabled` is. The same applies to `@DenyAll` and `jsr250Enabled=false`.

Do not mix multiple conflicting `@EnableMethodSecurity` configurations into the same `ApplicationContext` and guess at the outcome. Separate test contexts/profiles per variant, or use integration tests booting the application with one clear configuration.

### 10.4. MockMvc Proving HTTP and Method Layers Work Together

In an MVC application:

- Use `MockMvc` to prove unauthenticated callers cannot access protected routes.
- Use a logged-in user lacking the role to prove the service's `@Secured` blocks even when the HTTP matcher only requires `authenticated()`.
- Use a user with the role but lacking tenant/owner permission to prove the object policy blocks.
- For POST/PATCH/DELETE when CSRF is enabled, provide a valid CSRF token when testing **method authorization**; otherwise, a 403 may come from CSRF before the service is ever called.
- Verify **no side effects** occurred when the method is denied: data is unchanged, no messages/payments are triggered.

Do not claim a 403 response proves method security ran. Observe or test the service directly to know which guard actually denied the request.

## 11. Migrating from `EnableGlobalMethodSecurity` and Legacy JSR-250

### 11.1. The Two Activation Annotations Are Not Identical

Spring Security 5 and legacy code may use:

```java
@EnableGlobalMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
```

In modern Spring Security, the documentation recommends switching to:

```java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
```

`@EnableMethodSecurity` uses the `AuthorizationManager` architecture, Spring AOP, and modern configuration mechanisms; do not simply rename the annotation and skip testing. In particular, **pre/post is enabled by default** in the new configuration, while `securedEnabled` and `jsr250Enabled` default to false. During migration, explicitly preserve the annotation groups the old codebase actually uses.

### 11.2. Safe Migration Plan

1. Inventory every `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`, `@Secured`, `@RolesAllowed`, `@PermitAll`, and `@DenyAll` in **the codebase being migrated**.
2. Inspect old `@EnableGlobalMethodSecurity` configurations, expression handler beans, custom voters, pointcuts, or AspectJ setups.
3. Choose the right flags for the new `@EnableMethodSecurity`. If `@Secured`/JSR-250 are used, explicitly set their flags to `true`.
4. Switch `javax.annotation.security.*` imports to `jakarta.annotation.security.*` when upgrading to Spring Boot 3/Spring Framework 6 with compatible dependencies.
5. Check how role prefixes, authorities from IdP/JWT, and role hierarchies map into the active managers.
6. Write tests for sufficient/missing roles, anonymous, class-level vs method-level, and overlapping annotations.
7. Test self-invocation, proxies, and methods called from background jobs or message consumers.
8. Verify HTTP filter chains and object-level authorization independently.
9. Run regression tests before and after version upgrades; never turn off a flag just to silence a startup error without understanding the impact.
10. Document enabled/disabled annotation groups in architecture docs so future engineers do not infer behavior solely from annotations in source code.

### 11.3. Spring Security 6.x and 7.x

Both Spring Security 6.x and 7.x support the method authorization model with `@EnableMethodSecurity` and the annotation groups. However, internal/custom manager APIs and customizations such as `AuthorizationManagerFactory` can change across versions.

This lesson uses the flags `prePostEnabled`, `securedEnabled`, and `jsr250Enabled` confirmed by Spring Security 6.5 JavaDoc. When moving to Spring Security 7.x or advanced customization, check the locked version's JavaDoc, especially if writing custom interceptors or managers. Avoid mixing old `@EnableGlobalMethodSecurity` configuration examples with 7.x managers without checking compatibility.

## 12. Troubleshooting: Unexpected 403 or Missing 403

### 12.1. Diagnostic Checklist

```text
Is the method called on a Spring bean or a new object?
  |
  v
Is @EnableMethodSecurity enabled?
  |
  v
Which group does the annotation belong to?
  |
  +-- @PreAuthorize / @PostAuthorize / @PreFilter / @PostFilter
  |        requires prePostEnabled=true
  |
  +-- @Secured
  |        requires securedEnabled=true
  |
  +-- @RolesAllowed / @PermitAll / @DenyAll
           requires jsr250Enabled=true
  |
  v
Does the call go through proxy / advice?
  |
  v
Do multiple annotations/classes/interfaces interact?
  |
  v
Which authority/role prefix does Authentication have?
  |
  v
Are RoleHierarchy/ExpressionHandler applied properly?
  |
  v
Do HTTP matchers/CSRF or object policies deny before/after?
  |
  v
Check result + side effects, not just response code
```

### 12.2. Issue and Resolution Table

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `@Secured("ROLE_ADMIN")` is ignored | `securedEnabled=false` | Inspect `@EnableMethodSecurity` |
| `@RolesAllowed` does not block | `jsr250Enabled=false` or wrong generation import | Check flag and `jakarta.annotation.security.*` |
| `@DenyAll` still enters method body | JSR-250 disabled, self-invocation, or unproxied | Test method via Spring bean |
| `@PreAuthorize` does not block | Method security not enabled or `prePostEnabled=false` | Check config/test context |
| `@Secured` denies a user with the role | Actual authority differs from `ROLE_ADMIN` or hierarchy not applied | Print secret-filtered authority list |
| `@RolesAllowed("ADMIN")` fails to match | Prefix or mapper mismatch | Check `ROLE_ADMIN` in Authentication |
| Only one method in class behaves differently | Method-level overrides class-level of same group | Review annotation placement |
| Two interfaces have conflicting annotations | Ambiguous metadata; startup may fail | Put policy on concrete method |
| Public method safe externally, bypassed internally | Self-invocation via `this` | Refactor proxy boundary |
| `@PostAuthorize` denies after writing | Used after-check on side-effecting operation | Move check before + use transaction |
| Test returns 403 for unclear reason | CSRF, HTTP rule, method, or data | Test each guard separately |
| Enabling all flags causes more user denials | Multiple interceptors active together | Review combined conditions |
| Disabling JSR-250 reduces 403s | Disabled `@RolesAllowed/@DenyAll` | Restore and fix root policy |
| Method called from job has no principal | Context not propagated or task identity missing | Design job/service identity |
| Upgraded Boot 2→3 and annotations stop working | `javax`/`jakarta` not migrated | Check imports/dependencies |
| Expecting `@PermitAll` to open a `denyAll` HTTP route | Confusing protection layers | Separate HTTP and method security |

### 12.3. Safe Logging

In debug/staging environments, you can trace the method, active interceptor, verified principal, relevant authorities, and decision. Do not log raw passwords/JWTs/cookies, full financial data, or private records. Log correlation IDs and rule types enough to connect HTTP logs with service logs; avoid exposing expression contents carrying sensitive data.

When explaining 401/403:

- 401 usually relates to an unauthenticated request.
- 403 usually relates to missing permission or possibly CSRF.
- Method security exceptions may be converted by HTTP handlers into corresponding statuses.
- A call from a job has no HTTP response, so an exception is observed instead of an HTTP status code.

Do not infer "the annotation works" solely from status codes; observe which guard ran and the actual outcome.

## 13. Hands-On Exercises

### Exercise 1 — Fill Out the Switch Table

With default `@EnableMethodSecurity`, predict the effect of `@PreAuthorize`, `@Secured`, `@RolesAllowed`, `@PermitAll`, and `@DenyAll`. Then enable `securedEnabled` and `jsr250Enabled` one by one, using tests on a Spring bean to prove the differences.

### Exercise 2 — Run Java 17

Compile `MethodSecurityFlagsDemo.java` and predict every stdout line before running. Add a `JSR_PERMIT` rule; explain why even when that guard permits, another HTTP rule or data policy can still deny.

### Exercise 3 — Fix an Unactivated Annotation Gap

Given a service containing `@Secured("ROLE_ADMIN")` on a data-deletion operation, where the app only has default `@EnableMethodSecurity`, write a test where a `ROLE_USER` user can still call it (in a test setup with no other guard), then enable `securedEnabled=true` and assert `AccessDeniedException`.

### Exercise 4 — Jakarta Migration

A legacy project has `@RolesAllowed("ADMIN")` importing `javax.annotation.security.RolesAllowed`. Upgrade to Boot 3, choose the Jakarta dependency and matching import, enable `jsr250Enabled=true`, and test a principal with `ROLE_ADMIN`. Prove the method is protected when invoked through the Spring bean.

### Exercise 5 — Overlapping Annotations

A method has `@Secured("ROLE_ADMIN")` and `@PreAuthorize("hasAuthority('invoice:approve')")`. Test an admin without approve, an approver who is not admin, and an admin with both. Then turn off `securedEnabled` in a separate test context and explain why the allowed set can widen.

### Exercise 6 — Find the Proxy Bypass Path

Write a service with `public run()` calling `this.deleteAll()` protected by `@DenyAll`. Test a direct call through the bean proxy and the internal call. Redesign so the sensitive action cannot be invoked without service/data guards.

### Exercise 7 — Tenant Protection

Create two tenants. A user with `ROLE_ADMIN` in tenant A calls a service with `@Secured("ROLE_ADMIN")` to edit tenant B's document. Add an object policy based on the verified tenant and test denial. Prove that turning on method security flags does not automatically enforce cross-tenant boundaries.

## 14. Implementation Checklist

- [ ] One clear `@EnableMethodSecurity` configuration exists, verified in the right `ApplicationContext`.
- [ ] `prePostEnabled`/`securedEnabled`/`jsr250Enabled` match the annotations actually present in the codebase.
- [ ] If `@Secured` is used, `securedEnabled=true` and role strings are verified.
- [ ] If `@RolesAllowed/@PermitAll/@DenyAll` are used, `jsr250Enabled=true` and Jakarta imports match the version.
- [ ] "Disabled annotation" is never treated as "deny by default".
- [ ] Tests go through Spring beans/proxies, not only objects instantiated with `new`.
- [ ] Self-invocation, private/final methods, and interface metadata have been checked.
- [ ] Methods carrying multiple annotation groups do not unintentionally widen permissions when a flag is turned off.
- [ ] `@PostAuthorize` is not the sole guard before sensitive side effects.
- [ ] HTTP request authorization, CSRF, and object/data policies are tested independently.
- [ ] Role prefixes and `GrantedAuthority` sources from IdP/JWT/session are standardized.
- [ ] Jobs/background tasks have explicit principal and execution-permission models.
- [ ] Both allow and deny cases are tested while observing side effects.
- [ ] `@EnableGlobalMethodSecurity` and `javax→jakarta` migrations have regression tests.
- [ ] Flag changes are reviewed as security policy changes, not minor configuration tweaks.

## 15. Self-Check Questions

1. **Which group does `@EnableMethodSecurity` enable by default?** The pre/post group: `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`.
2. **Default value of `securedEnabled`?** False.
3. **Default value of `jsr250Enabled`?** False.
4. **What is required for `@Secured` to be evaluated?** Method security enabled, `securedEnabled=true`, and calls passing through the matching interceptor.
5. **Which three annotations belong to the `jsr250Enabled` group?** `@RolesAllowed`, `@PermitAll`, `@DenyAll`.
6. **What happens if `@DenyAll` is in code while JSR-250 is disabled?** That annotation creates no JSR-250 method guard; other checks may exist, but you must not rely on it alone.
7. **Does `@Secured({"ROLE_ADMIN","ROLE_SUPPORT"})` require both?** No; holding one of the accepted authorities is enough for this guard.
8. **Which authority does `@RolesAllowed("ADMIN")` normally compare against?** `ROLE_ADMIN` when using the default `ROLE_` prefix.
9. **Can SpEL be used inside `@Secured("hasRole('ADMIN')")`?** No; `@Secured` does not evaluate SpEL expressions like `@PreAuthorize`.
10. **Does `@PermitAll` override HTTP `anyRequest().denyAll()`?** No.
11. **Why can enabling `securedEnabled=true` cause the app to start producing new 403s?** Previously inactive `@Secured` guards begin enforcing; inspect the real policies.
12. **Why is self-invocation dangerous?** Internal calls within the same instance can bypass the proxy and security interceptors.
13. **Is `@PostAuthorize` suitable as the sole guard for a money transfer operation?** No; checking afterward can be too late.
14. **What happens if a method has both `@PreAuthorize` and `@Secured` enabled?** All active conditions must pass; disabling one group can leave a guard missing.
15. **Does enabling method security automatically protect every service method?** No; appropriate annotations/pointcuts and intercepted calls are required.
16. **Why test the service directly outside HTTP?** To prove method advice actually runs, without confusion with HTTP matchers/CSRF.
17. **In Spring Boot 3, which package do JSR-250 imports normally use?** `jakarta.annotation.security.*`.
18. **Can an admin user edit every tenant because of `@RolesAllowed("ADMIN")`?** Not by default; tenant/object policies remain independent.

**Remember:** the three flags of `@EnableMethodSecurity` decide **which annotation groups Spring Security actually registers interceptors for**. `prePostEnabled=true` is the default; `securedEnabled=false` and `jsr250Enabled=false` are defaults. Therefore, `@Secured`, `@RolesAllowed`, or even `@DenyAll` appearing in source code **is not proof that permissions are checked**. Enable the groups you need, understand Spring AOP boundaries, test every guard, and continue protecting actions and resources at the business layer.

### Official Documentation

- [Spring Security 6.5 – EnableMethodSecurity JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html)
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security – Method Security (current)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Servlet Authorization and HTTP rules](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Jakarta Annotations – @RolesAllowed, @PermitAll, @DenyAll](https://jakarta.ee/specifications/annotations/)