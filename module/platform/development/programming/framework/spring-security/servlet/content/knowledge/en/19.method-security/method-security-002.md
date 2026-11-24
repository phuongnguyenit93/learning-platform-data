# @EnableMethodSecurity and Enabled Annotation Groups — Spring Security Servlet

In a Spring Security application, a user passing the URL protection layer **does not mean they are allowed to perform every business operation that a controller invokes**. A `GET /api/docs/42` controller might only require "logged in", but the service reading the document must still check the user's permissions on that specific document. Spring Security supports placing authorization decisions at the **method boundary** through annotations such as `@PreAuthorize`, `@PostAuthorize`, `@Secured`, and `@RolesAllowed`.

For these annotations to actually take effect, the application must enable **method security** with `@EnableMethodSecurity` and select the right **annotation groups** to use. This is an easy place to misconfigure: in Spring Security 6.x, the **pre/post annotations group is enabled by default** when using `@EnableMethodSecurity`, whereas the **@Secured** and **JSR-250** groups require **opt-in** via two separate flags. Writing `@Secured("ROLE_ADMIN")` on a service without enabling the corresponding group can create a false sense of security because the annotation is not executed by that group's method-security advisor.

This lesson belongs to the **Method Security** section in the **Spring Security – servlet** module, using Java 17+, Spring Security 6.x, and a Spring Boot 3.3.5 example. The focus is on **which annotations are enabled, what each group does, the AOP proxy conditions for interception to occur, and how to verify with real tests**.

## 1. Learning Objectives

After this lesson, you should be able to:

1. Explain the difference between **HTTP request authorization** and **method authorization**.
2. Know the exact default state of `prePostEnabled`, `securedEnabled`, and `jsr250Enabled` in `@EnableMethodSecurity`.
3. Use annotations from all three groups: `@PreAuthorize`/`@PostAuthorize`/`@PreFilter`/`@PostFilter`; `@Secured`; `@RolesAllowed`/`@PermitAll`/`@DenyAll`.
4. Distinguish **role** from **authority**; understand the `ROLE_` prefix, SpEL, `Authentication`, method parameters, and `returnObject`.
5. Know why `@PostAuthorize` should not be used to protect an operation that already causes side effects.
6. Describe **proxy-based AOP** limitations: self-invocation, private/final methods, method calls that do not go through the proxy, and non-Spring-managed beans.
7. Enable annotation groups with `@EnableMethodSecurity(prePostEnabled = true, securedEnabled = true, jsr250Enabled = true)` and write tests covering **both allow and deny**.
8. Detect missing annotation group bugs, authorization at the wrong layer, turning method security config into HTTP bypasses, or hiding AOP behind test mocking.

## 2. What Problem Does Method Security Solve?

Consider a business call chain:

~~~text
GET /api/docs/42
       |
       v
Spring Security Servlet FilterChain
  -> authentication: principal/authorities?
  -> HTTP authorization: endpoint requires authenticated?
       |
       v
Spring MVC Controller
       |
       v
DocumentService.findById("42")
       |
       +-- Method security checks:
       |     Does this user have permission to read document 42?
       |
       +-- Allowed -> method runs / returns data
       +-- Denied  -> AccessDeniedException
~~~

HTTP authorization is typically suited for conditions on **URL + method + coarse role/scope**. However, permissions at the service layer also depend on **parameters or returned data**, for example: "only view records belonging to the current tenant", "only update invoices owned by oneself", or "only admin may invoke this operation even when multiple controllers use it".

Two-level check example:

~~~java
// HTTP: only requires being logged in for the namespace.
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())

// Method: requires matching principal or administrator.
// Placed on a Spring service bean method:
@PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
public String profileOf(String username) {
    return "Profile of " + username;
}
~~~

The snippet above consists of **two code fragments** belonging to two different configuration layers, not a standalone class. If reader tries to access admin's profile, HTTP authorization may let it through because reader is logged in, but the **service proxy rejects it** before running the method.

**Method security does not replace authentication.** Annotations require an `Authentication` established from a trusted source (session/form login, HTTP Basic, JWT decoder, etc.). If a custom filter blindly assigns `ROLE_ADMIN` from an unverified header, method security will evaluate against forged authorities and grant access erroneously.

## 3. Enabling @EnableMethodSecurity: Flags to Remember

### 3.1. Minimal Configuration

In a Spring configuration class:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

When Spring Security method security is enabled as above, the **pre/post annotations** group is supported by default. However, that does **not** automatically mean `@Secured` and JSR-250 are enabled.

### 3.2. Annotation Group Matrix

| Group | Main Annotations | @EnableMethodSecurity Flag | Default When Writing Only @EnableMethodSecurity |
| --- | --- | --- | --- |
| Pre/Post annotations | `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` | `prePostEnabled` | **true — enabled** |
| Secured annotations | `@Secured` | `securedEnabled` | **false — disabled** |
| JSR-250 annotations | `@RolesAllowed`, `@PermitAll`, `@DenyAll` | `jsr250Enabled` | **false — disabled** |

Explicitly enable all three groups:

~~~java
@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfiguration {
}
~~~

Do not enable every group by default and scatter overlapping annotations on the same method. **Choose one primary convention for the codebase**, and enable additional groups only when genuinely needed for compatibility with existing projects/libraries. When multiple authorization annotations apply simultaneously to the same call, multiple advisors may all take effect; do not treat `@PermitAll` as "overriding every other @PreAuthorize".

### 3.3. Configuration Variants Worth Remembering

**Pre/post only (usually the default choice):**

~~~java
@EnableMethodSecurity
~~~

**Pre/post and @Secured:**

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

**Pre/post and JSR-250:**

~~~java
@EnableMethodSecurity(jsr250Enabled = true)
~~~

**@Secured only, without pre/post:**

~~~java
@EnableMethodSecurity(
    prePostEnabled = false,
    securedEnabled = true
)
~~~

**JSR-250 only:**

~~~java
@EnableMethodSecurity(
    prePostEnabled = false,
    jsr250Enabled = true
)
~~~

The lines above are **independent options**; do not paste multiple `@EnableMethodSecurity` annotations into one application hoping they combine implicitly. Set one consistent configuration and test each annotation actually in use.

### 3.4. What If an Annotation Belongs to a Disabled Group?

If the application only uses default `@EnableMethodSecurity` and a developer adds:

~~~java
@Secured("ROLE_ADMIN")
public void deleteAllReports() { ... }
~~~

then the advisor handling `@Secured` **is not registered under the default configuration**. Spring Security method security does not automatically convert this annotation into `@PreAuthorize`. If the HTTP layer only requires `authenticated()`, requests can escalate privileges because the expected service-level check **does not run**.

Similarly, writing `@RolesAllowed("ADMIN")` while forgetting `jsr250Enabled=true` does not produce the intended JSR-250 enforcement. **This is why negative-case tests are mandatory**: have an authenticated user lacking permissions call the exact method and assert a 403/AccessDeniedException result.

## 4. The Pre/Post Group: Strongest for Expressions and Data

This group uses **Spring Expression Language (SpEL)** expressions and built-in values such as `authentication`, `principal`, `hasRole(...)`, `hasAuthority(...)`, method parameters, `returnObject`, or `filterObject` depending on the annotation.

### 4.1. @PreAuthorize — Check Before Running the Method

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void rebuildIndex() {
    // Executes only when ROLE_ADMIN is present.
}
~~~

Use it to protect actions **with side effects**: creating, editing, deleting, changing state, sending emails, processing payments. When the rule denies access, the business method is not allowed to execute through the proxy.

With parameters:

~~~java
@PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
public String readProfile(String username) {
    return "profile:" + username;
}
~~~

`#p0` references the first method parameter and does not depend on whether the compiler preserves parameter name metadata. If you want to use `#username`, ensure parameter names can be discovered by Spring Security (for example, the `-parameters` compiler option or a supporting annotation). Do not let an expression work in the IDE yet deny/fail in production builds due to missing parameter names.

**Note:** Checking `username == authentication.name` is only an identity illustration. When data spans multiple tenants or resources have owners in the DB, permissions must rely on real business authorization; do not trust a self-declared owner id from the client.

### 4.2. @PostAuthorize — Check After Obtaining returnObject

~~~java
@PostAuthorize(
    "returnObject.owner == authentication.name or hasRole('ADMIN')")
public Document findDocument(String id) {
    return repository.findById(id).orElseThrow();
}
~~~

This is an **illustrative code snippet**: `Document` has a `getOwner()` getter and `repository` is a real repository object. After the method returns a result, the method-security advisor checks `returnObject` before letting the caller receive the result.

Advantage: it can check permissions based on **information known only after loading the object**. Disadvantage: **the method has already run**. If the method writes to the DB, sends an email, or calls an external API before `@PostAuthorize` denies access, side effects may already have occurred or fail to roll back as expected. Therefore:

- Prefer `@PreAuthorize` or check policy **before** mutation.
- Use `@PostAuthorize` for read-only operations where the output needs ownership inspection.
- Do not treat a post-check as a wall preventing execution of a sensitive operation.
- When a method is transactional, explicitly note AOP advisor ordering and transaction boundaries if relying on rollback.

### 4.3. @PreFilter — Filter Input Collections Before Running the Method

~~~java
@PreFilter("filterObject == authentication.name or hasRole('ADMIN')")
public List<String> keepAllowedUsers(List<String> usernames) {
    return List.copyOf(usernames);
}
~~~

When the proxy receives the list of usernames, `@PreFilter` evaluates each element before invoking the body. In the example, a regular user keeps only their own name; admin can keep all. Typically used with `Collection`/array/map/stream depending on version capabilities and data types; when there are multiple collection parameters, use `filterTarget` to specify the target explicitly.

Do not treat input filtering as a replacement for object-level authorization at the persistence layer: callers can bypass logic if another path reaches the database, and mutating collections can cause issues with immutable inputs. In the runnable example below, the controller creates a mutable `ArrayList` so the filter can process it safely.

### 4.4. @PostFilter — Filter Output Collections

~~~java
@PostFilter(
    "filterObject.owner == authentication.name or hasRole('ADMIN')")
public List<Document> listDocuments() {
    return new ArrayList<>(repository.findAll());
}
~~~

This is a code snippet. After obtaining a result collection, Spring Security evaluates each element via `filterObject`. Regular users only see permitted documents; admin can see all.

**Do not replace conditional queries with @PostFilter when data is large or sensitive.** The service may have already loaded thousands of records before filtering; DB/CPU/memory overhead and the risk of data passing through logs/caches/side effects remain. For real products, prefer tenant/owner-scoped queries directly in the DB, and add method security as a policy-enforcing layer.

### 4.5. Pre/Post: When to Use Which Annotation?

| Scenario | Annotation to Consider | What to Verify |
| --- | --- | --- |
| Only admin may delete data | `@PreAuthorize("hasRole('ADMIN')")` | Check before side effect |
| User views own profile | `@PreAuthorize("#p0 == authentication.name")` | Trusted parameter and owner policy |
| Read object then verify real owner | `@PostAuthorize` | Read-only, data already loaded |
| Remove inputs not belonging to user | `@PreFilter` | Mutable collection, filterTarget, no leak via other paths |
| Return only permitted subset of records | `@PostFilter` | Performance, query filtering, paging |
| Check exact scope from JWT/OAuth2 | `@PreAuthorize("hasAuthority('SCOPE_docs.read')")` | JWT authority converter mapping |

## 5. The @Secured Group: Static Role/Authority, Easy to Read

The `@Secured` annotation belongs to the Spring Security namespace and **is not enabled by default** with `@EnableMethodSecurity`. To use it:

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

Example:

~~~java
@Secured("ROLE_ADMIN")
public String administratorReport() {
    return "only-admin";
}
~~~

`@Secured` uses a list of roles/authorities and **does not support arbitrary SpEL** like `@PreAuthorize`. If you need to compare parameters against Authentication, tenant/owner policies, or call a policy bean, `@PreAuthorize` is usually a better fit.

Example allowing multiple authorities:

~~~java
@Secured({"ROLE_ADMIN", "ROLE_AUDITOR"})
public String auditReport() {
    return "audit";
}
~~~

The values are role authorities by convention. **Do not confuse** the syntax between `@Secured("ROLE_ADMIN")` and `@PreAuthorize("hasRole('ADMIN')")`. With the default role prefix:

- `@Secured("ROLE_ADMIN")` checks for an authority with the value `ROLE_ADMIN`.
- `hasRole('ADMIN')` looks up `ROLE_ADMIN` by default.
- `hasAuthority('ROLE_ADMIN')` checks the exact string `ROLE_ADMIN`.
- `hasAuthority('SCOPE_docs.read')` checks the exact OAuth2 scope authority convention if the converter has granted that authority.

A `@Secured("ADMIN")` rule is not automatically equivalent to `@Secured("ROLE_ADMIN")` across all configurations; use a consistent convention.

## 6. The JSR-250 Group: @RolesAllowed, @PermitAll, @DenyAll

With Java 17/Spring Boot 3, use the **`jakarta.annotation.security`** package, not the old `javax.annotation.security` from Java EE out of habit. Main annotations:

~~~java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
~~~

Enable:

~~~java
@EnableMethodSecurity(jsr250Enabled = true)
~~~

### 6.1. @RolesAllowed

~~~java
@RolesAllowed("MANAGER")
public String approveReport() {
    return "approved";
}
~~~

With the usual role prefix, `@RolesAllowed("MANAGER")` requires the `ROLE_MANAGER` authority. It is not a SpEL expression for a dynamic parameter. If your organization changes the role-prefix policy, test the concrete behavior rather than concatenating strings by assumption.

### 6.2. @PermitAll

~~~java
@PermitAll
public String publicCatalog() {
    return "public";
}
~~~

Allows method invocation through the JSR-250 advisor, including anonymous callers if no other layer blocks them. However:

**`@PermitAll` does not bypass HTTP authentication/authorization and does not disable CSRF, the filter chain, or other policies.** If the endpoint's HTTP rule is `hasRole("ADMIN")`, an anonymous user is still blocked before the controller calls the method even if the service has `@PermitAll`. If the class/method simultaneously carries other method-security annotations, do not assume `@PermitAll` overrides every advisor.

### 6.3. @DenyAll

~~~java
@DenyAll
public void dangerousOperation() {
    throw new IllegalStateException("Must never be reached");
}
~~~

When the JSR-250 advisor is enabled, every call **going through the proxy** to this method must be denied per JSR-250 policy, even for users with high roles. This is a useful mechanism when intentionally closing off a method or an incomplete migration.

If `jsr250Enabled=false`, this annotation is not an active barrier by default. Therefore testing that an admin is denied by `@DenyAll` is a way to prove the JSR-250 group is truly active.

### 6.4. Quick Comparison

| Annotation | From Package | Enable Flag | Check Style |
| --- | --- | --- | --- |
| `@PreAuthorize("hasRole('ADMIN')")` | Spring Security | prePostEnabled | SpEL, before method |
| `@PostAuthorize("returnObject.owner == ...")` | Spring Security | prePostEnabled | SpEL, after method |
| `@PreFilter / @PostFilter` | Spring Security | prePostEnabled | Filter input/output |
| `@Secured("ROLE_ADMIN")` | Spring Security | securedEnabled | Static authority/role |
| `@RolesAllowed("ADMIN")` | Jakarta JSR-250 | jsr250Enabled | Static role, usually ROLE_ prefix |
| `@PermitAll` | Jakarta JSR-250 | jsr250Enabled | Allow per JSR advisor |
| `@DenyAll` | Jakarta JSR-250 | jsr250Enabled | Deny per JSR advisor |

## 7. Method-Security Interceptors and AOP Proxies

This is the most important section for avoiding the situation where "annotations are enabled yet the method still runs".

### 7.1. What Infrastructure Does @EnableMethodSecurity Activate?

Spring Security 6 uses an **AuthorizationManager** approach to implement method security. The infrastructure registers method-security advisors/interceptors on eligible Spring beans. As a result, a call through the proxy can be evaluated:

~~~text
Controller bean (Spring-managed)
      |
      v
ProtectedService proxy
      |
      +--- Before-method authorization (e.g. @PreAuthorize)
      |       | allowed?
      |       +--- No  -> AccessDeniedException
      |       +--- Yes -> run target method
      |
      +--- After-method authorization (@PostAuthorize)
      |       | allowed for returnObject?
      |       +--- No  -> AccessDeniedException
      |       +--- Yes -> return result
      |
      +--- Filter input/output if annotated with @PreFilter/@PostFilter
~~~

This is a conceptual flow and does not represent the exact ordering of every advisor when transactions, caching, async, or other annotations are present. What to remember: **a method is protected when the call actually passes through the security proxy/advice**.

### 7.2. Self-Invocation Can Bypass Checks

An example with **wrong expectations**:

~~~java
@Service
public class PaymentService {

    public void batch() {
        // Internal call on this, may not go through the proxy.
        refund(); 
    }

    @PreAuthorize("hasRole('FINANCE')")
    public void refund() {
        // Sensitive financial operation.
    }
}
~~~

In default proxy-based mode, calling `refund()` from `batch()` on the same instance **does not pass through the method security proxy**, so the annotation on `refund()` may not execute. This does not prove `@PreAuthorize` is broken; **the call path bypassed the proxy**.

Safe design approaches usually include:

- Moving the protected method into **another Spring bean**, so the caller injects that bean and calls through the proxy.
- Or checking authorization at the entry point before the business action runs, without relying on an internal call expected to trigger AOP interception.
- Not using self-injection/proxy exposure as a default solution when clean boundaries can be redesigned.
- If AspectJ mode is genuinely needed, configuring weaving and corresponding deployment verification rather than just flipping a flag.

### 7.3. Methods Not Intercepted by Proxies

Be careful with:

- `private` methods: not normal AOP proxy boundaries.
- `final` methods/classes in subclass-based proxies: cannot be overridden for interception.
- Beans instantiated with `new` outside the Spring container: no Spring AOP proxy.
- Calling methods in a constructor or before the bean is fully initialized: may occur before the proxy boundary.
- Interface vs class proxy configuration, method visibility, Kotlin's compile-time `final`, or internal calls on the same target instance.
- Async threads, scheduled jobs, message consumers: must have proper `SecurityContext`/identity propagation; never assume an HTTP request context exists.

Therefore place method annotations on **public service methods in Spring-managed beans**, called from other beans via dependency injection, accompanied by integration tests proving advisors execute.

### 7.4. Proxy Mode and AspectJ Mode

`@EnableMethodSecurity` supports configuring the advice mode, typically:

~~~java
@EnableMethodSecurity(
    mode = AdviceMode.PROXY,
    proxyTargetClass = false
)
~~~

This is an illustrative snippet; it requires importing `org.springframework.context.annotation.AdviceMode` and the corresponding annotation. In proxy mode, Spring may use interface-based proxies or class-based proxies depending on configuration/infrastructure. `proxyTargetClass = true` generally requests class-based proxies, though final methods/classes and self-invocation still need attention.

AspectJ weaving is another option when architecture demands interception beyond proxy limits. **It requires separate weaving configuration, dependencies, and tests**; do not just change `mode = AdviceMode.ASPECTJ` and assume every internal call is protected.

### 7.5. Do Not Put Security Rules on a Method Without a Real Caller Path

An annotation written on an interface or a class not brought into the proxy path by the Bean Factory may not be applied as you expect. In large codebases, audit the invocation architecture: request/controller → injected service proxy → annotated method. Testing a method directly on an object created with `new` does not prove method security is active.

## 8. HTTP Security and Method Security Are Two Cooperating Layers

An application having both:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public").permitAll()
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
~~~

and:

~~~java
@Secured("ROLE_ADMIN")
public String administratorOperation() {
    return "admin-only";
}
~~~

must pass **both layers** where they apply:

- No authentication: the HTTP layer typically returns 401 with HTTP Basic or redirects to login with form login.
- Regular user: the HTTP layer accepts `authenticated()`, service `@Secured` denies for lacking ROLE_ADMIN → typically 403.
- Admin: the HTTP layer accepts, service rule can accept → controller returns response.

An HTTP policy such as `permitAll()` does not disable method-security advisors, and conversely: a `@PermitAll` method does not open a route blocked by HTTP `denyAll()` or `hasRole(...)`.

### 8.1. Avoid Confusing @EnableMethodSecurity with @EnableWebSecurity

- `@EnableWebSecurity` relates to web/security filter chain configuration.
- `@EnableMethodSecurity` activates method-call protection infrastructure.
- In Spring Boot using the security starter, you can configure `SecurityFilterChain` as a bean and separately use `@EnableMethodSecurity` without necessarily adding `@EnableWebSecurity` manually as in older pure-Spring examples.

**Do not assume Spring Boot Starter Security automatically enables full method security** just because a `SecurityFilterChain` is working. Check annotations and tests for each group.

### 8.2. When Is 401 Returned vs 403?

| Scenario | Common HTTP Result | Interpretation |
| --- | --- | --- |
| Anonymous calls route requiring authenticated | 401 with HTTP Basic in the example | Missing authentication |
| Valid user calls method requiring different role | 403 | Method authorization deny |
| Invalid JWT/opaque bearer | 401 in typical resource server | Authentication failed |
| User with right role and method allows | 200/201/... | Passed both HTTP and method |
| User calls @DenyAll through proxy | 403 when already authenticated | Denied by JSR-250 policy |
| POST missing CSRF token in cookie-based app | May be 403 before entering method | Do not infer missing role |

Exact status codes depend on `AuthenticationEntryPoint`, `AccessDeniedHandler`, controller advice, and filters. In tests, verify status per the **project's configuration**; do not assert 401/403 as a universal contract for every application.

## 9. Runnable Example: Spring Boot 3.3.5 + Java 17 Enabling All Three Groups

This example intentionally enables:

~~~java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

Sample endpoints:

- `GET /api/public`: service has `@PermitAll`, HTTP route also uses `permitAll`.
- `GET /api/me/{name}`: `@PreAuthorize` for the user themselves or admin.
- `GET /api/admin/pre`: `@PreAuthorize("hasRole('ADMIN')")`.
- `GET /api/admin/secured`: `@Secured("ROLE_ADMIN")`.
- `GET /api/manager/jsr`: `@RolesAllowed("MANAGER")`.
- `GET /api/denied`: `@DenyAll` blocks even admin.
- `GET /api/docs/{id}`: `@PostAuthorize` compares ownership of the loaded object.
- `GET /api/docs`: `@PostFilter` removes documents not belonging to the user (except admin).
- `GET /api/names?name=reader&name=admin`: `@PreFilter` filters the input list before the service runs.

### 9.1. File Structure

~~~text
method-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/example/methodsecurity/
    │       ├── MethodSecurityApplication.java
    │       ├── SecurityConfiguration.java
    │       ├── Document.java
    │       ├── ProtectedOperations.java
    │       └── DemoController.java
    └── test/java/example/methodsecurity/
        └── MethodSecurityTests.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'method-security-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'jakarta.annotation:jakarta.annotation-api'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management selects compatible Spring Security/Jakarta versions. Do not mix old `javax.annotation.security` (legacy Java EE) with Spring Boot 3/Jakarta out of habit.

### 9.2. Main Class

File `src/main/java/example/methodsecurity/MethodSecurityApplication.java`:

~~~java
package example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityApplication.class, args);
    }
}
~~~

### 9.3. SecurityConfiguration: Enabling All Three Annotation Groups

File `src/main/java/example/methodsecurity/SecurityConfiguration.java`:

~~~java
package example.methodsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            // The demo endpoints only use GET, so CSRF does not need to be disabled.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        UserDetails manager = User.withUsername("manager")
            .password(encoder.encode("manager-pass"))
            .roles("MANAGER")
            .build();

        return new InMemoryUserDetailsManager(reader, admin, manager);
    }
}
~~~

With `roles("ADMIN")`, Spring Security creates the `ROLE_ADMIN` authority by convention. `roles("MANAGER")` corresponds to `ROLE_MANAGER`. HTTP Basic is for simple authentication testing in a local lab, not a recommendation to use Basic for every system. Production requires HTTPS and an appropriate user store/identity provider.

**Why does HTTP only require `authenticated()` for `/api/**`?** The demo's goal is to prove that **method security still rejects an authenticated user who lacks permission**. If HTTP already required ROLE_ADMIN for the admin endpoint, you could not use the HTTP 403 result to be sure the `@Secured` annotation ran.

### 9.4. Document Model

File `src/main/java/example/methodsecurity/Document.java`:

~~~java
package example.methodsecurity;

public class Document {

    private final String id;
    private final String owner;
    private final String title;

    public Document(String id, String owner, String title) {
        this.id = id;
        this.owner = owner;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }

    public String getTitle() {
        return title;
    }
}
~~~

The `getOwner()` getter allows SpEL to use `returnObject.owner` or `filterObject.owner`. Do not trust an `owner` coming from a request body without persistence/business verification; the demo creates objects in server code.

### 9.5. ProtectedOperations: All Three Groups

File `src/main/java/example/methodsecurity/ProtectedOperations.java`:

~~~java
package example.methodsecurity;

import java.util.ArrayList;
import java.util.List;

import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProtectedOperations {

    @PermitAll
    public String publicMessage() {
        return "public-ok";
    }

    @PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
    public String profileOf(String name) {
        return "profile:" + name;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String adminPre() {
        return "pre-admin-ok";
    }

    @Secured("ROLE_ADMIN")
    public String adminSecured() {
        return "secured-admin-ok";
    }

    @RolesAllowed("MANAGER")
    public String managerJsr() {
        return "jsr-manager-ok";
    }

    @DenyAll
    public String neverAllowed() {
        return "must-not-return";
    }

    @PostAuthorize(
        "returnObject.owner == authentication.name or hasRole('ADMIN')")
    public Document readDocument(String id) {
        return allDocuments().stream()
            .filter(doc -> doc.getId().equals(id))
            .findFirst()
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PostFilter(
        "filterObject.owner == authentication.name or hasRole('ADMIN')")
    public List<Document> visibleDocuments() {
        // Mutable list so PostFilter can filter safely.
        return new ArrayList<>(allDocuments());
    }

    @PreFilter(
        "filterObject == authentication.name or hasRole('ADMIN')")
    public List<String> allowedNames(List<String> names) {
        // Input is filtered by method-security advice before the body runs.
        return List.copyOf(names);
    }

    private List<Document> allDocuments() {
        return List.of(
            new Document("doc-r", "reader", "Reader document"),
            new Document("doc-a", "admin", "Admin document")
        );
    }
}
~~~

**Look closely at where the methods live:** Each protected method is `public`, belongs to a `@Service` Spring bean, and is called by the controller through an **injected proxy**. The private helper `allDocuments()` only builds data; it carries no authorization annotation, so the internal call here does not create a bypass.

In production, documents must actually come from a repository and viewing/modifying must check tenant/ownership against server data; the code above only illustrates how the advisors operate.

### 9.6. Controller Calling Into the Service Proxy

File `src/main/java/example/methodsecurity/DemoController.java`:

~~~java
package example.methodsecurity;

import java.util.ArrayList;
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ProtectedOperations protectedOperations;

    public DemoController(ProtectedOperations protectedOperations) {
        this.protectedOperations = protectedOperations;
    }

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return protectedOperations.publicMessage();
    }

    @GetMapping("/api/me/{name}")
    public String profile(@PathVariable String name) {
        return protectedOperations.profileOf(name);
    }

    @GetMapping("/api/admin/pre")
    public String adminPre() {
        return protectedOperations.adminPre();
    }

    @GetMapping("/api/admin/secured")
    public String adminSecured() {
        return protectedOperations.adminSecured();
    }

    @GetMapping("/api/manager/jsr")
    public String manager() {
        return protectedOperations.managerJsr();
    }

    @GetMapping("/api/denied")
    public String denied() {
        return protectedOperations.neverAllowed();
    }

    @GetMapping("/api/docs/{id}")
    public Document doc(@PathVariable String id) {
        return protectedOperations.readDocument(id);
    }

    @GetMapping("/api/docs")
    public List<Document> docs() {
        return protectedOperations.visibleDocuments();
    }

    @GetMapping("/api/names")
    public List<String> names(@RequestParam("name") List<String> names) {
        return protectedOperations.allowedNames(
            new ArrayList<>(names));
    }
}
~~~

Because the controller injects the service from the Spring container, calls from the controller to `ProtectedOperations` go through the proxy once method-security infrastructure is enabled. This structure **intentionally avoids self-invocation**. All endpoints are GET and perform no mutations so the focus is not diverted to CSRF.

### 9.7. Full Allow/Deny Tests for Each Annotation Group

File `src/test/java/example/methodsecurity/MethodSecurityTests.java`:

~~~java
package example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void permitAllMethodAllowsAnonymousWhenHttpAlsoPermits()
            throws Exception {
        mockMvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public-ok"));
    }

    @Test
    void protectedRouteNeedsAuthentication() throws Exception {
        mockMvc.perform(get("/api/admin/secured"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void preAuthorizeAllowsSelf() throws Exception {
        mockMvc.perform(get("/api/me/reader")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:reader"));
    }

    @Test
    void preAuthorizeDeniesAnotherUser() throws Exception {
        mockMvc.perform(get("/api/me/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void preAuthorizeAllowsAdminOverride() throws Exception {
        mockMvc.perform(get("/api/me/reader")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void preAuthorizeAdminRuleDeniesReader() throws Exception {
        mockMvc.perform(get("/api/admin/pre")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void securedAnnotationDeniesReader() throws Exception {
        mockMvc.perform(get("/api/admin/secured")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void securedAnnotationAllowsAdmin() throws Exception {
        mockMvc.perform(get("/api/admin/secured")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("secured-admin-ok"));
    }

    @Test
    void jsr250RolesAllowedAllowsManager() throws Exception {
        mockMvc.perform(get("/api/manager/jsr")
                .with(httpBasic("manager", "manager-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("jsr-manager-ok"));
    }

    @Test
    void jsr250RolesAllowedDeniesOtherRole() throws Exception {
        mockMvc.perform(get("/api/manager/jsr")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void denyAllRejectsEvenAdmin() throws Exception {
        mockMvc.perform(get("/api/denied")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postAuthorizeAllowsOwner() throws Exception {
        mockMvc.perform(get("/api/docs/doc-r")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("reader"));
    }

    @Test
    void postAuthorizeDeniesNonOwnerAfterRead() throws Exception {
        mockMvc.perform(get("/api/docs/doc-a")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postAuthorizeAllowsAdmin() throws Exception {
        mockMvc.perform(get("/api/docs/doc-r")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void postFilterRemovesOtherUsersDocuments() throws Exception {
        mockMvc.perform(get("/api/docs")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].owner").value("reader"));
    }

    @Test
    void postFilterAllowsAdminToSeeAllDocuments() throws Exception {
        mockMvc.perform(get("/api/docs")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)));
    }

    @Test
    void preFilterRemovesUnauthorizedNames() throws Exception {
        mockMvc.perform(get("/api/names")
                .param("name", "reader", "admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0]").value("reader"));
    }

    @Test
    void preFilterAllowsAdminToKeepAllNames() throws Exception {
        mockMvc.perform(get("/api/names")
                .param("name", "reader", "admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)));
    }
}
~~~

**Why are these tests of the annotation groups rather than just the HTTP layer?** The HTTP policy only requires `authenticated()` for all protected endpoints under `/api/**`. User `reader` **is already authenticated** yet gets 403 on `@Secured`, `@RolesAllowed`, `@PreAuthorize`, and `@PostAuthorize`. Admin is denied on `@DenyAll`. Thus negative tests catch missing-advisor bugs far better than only testing that anonymous receives HTTP 401.

Some groups only take effect when conditions are met: `@PermitAll` needs JSR-250 enabled and HTTP must also permit anonymous; `@PreFilter` requires a compatible input collection; `@PostFilter` returns a mutable list so it can be filtered. These tests only demonstrate the example's behavior/mechanics; they do not replace a production transaction/security policy review.

### 9.8. Running the Example

With Java 17 and a compatible Gradle version:

~~~bash
gradle test
gradle bootRun
~~~

If the project has the Gradle Wrapper, use:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Windows: `gradlew.bat test` and `gradlew.bat bootRun`. Do not use bare `javac`/`java` to run a Spring Boot project when dependency classpaths are missing. The commands above are instructions for running, **not a claim that Gradle was executed in the environment where this lesson was written**.

Example HTTP requests when the application listens on localhost:8080:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/admin/secured
curl -i -u reader:reader-pass \
  http://localhost:8080/api/admin/secured
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin/secured
curl -i -u manager:manager-pass \
  http://localhost:8080/api/manager/jsr
curl -i -u reader:reader-pass \
  http://localhost:8080/api/docs/doc-r
curl -i -u reader:reader-pass \
  http://localhost:8080/api/docs/doc-a
~~~

In the demo, expected results: public 200; anonymous on admin/secured typically 401; reader on admin/secured 403; admin on admin/secured 200; manager on manager/jsr 200; reader reading doc-r 200 but doc-a 403.

**Only use sample credentials for localhost.** In production, do not leave passwords in shell history, do not run HTTP Basic over unencrypted networks, and use HTTPS with an appropriate identity provider.

## 10. Results Table by Annotation Group

| Request / Principal | HTTP Check | Method Annotation | Typical Result |
| --- | --- | --- | --- |
| GET /api/public, anonymous | permitAll | `@PermitAll` | 200 |
| GET /api/admin/secured, anonymous | authenticated | Never reaches method | 401 |
| GET /api/admin/secured, reader | authenticated | `@Secured("ROLE_ADMIN")` | 403 |
| GET /api/admin/secured, admin | authenticated | `@Secured("ROLE_ADMIN")` | 200 |
| GET /api/manager/jsr, manager | authenticated | `@RolesAllowed("MANAGER")` | 200 |
| GET /api/manager/jsr, reader | authenticated | `@RolesAllowed("MANAGER")` | 403 |
| GET /api/denied, admin | authenticated | `@DenyAll` | 403 |
| GET /api/me/reader, reader | authenticated | `@PreAuthorize` | 200 |
| GET /api/me/admin, reader | authenticated | `@PreAuthorize` | 403 |
| GET /api/docs/doc-r, reader | authenticated | `@PostAuthorize` | 200 |
| GET /api/docs/doc-a, reader | authenticated | `@PostAuthorize` | 403 |
| GET /api/docs, reader | authenticated | `@PostFilter` | 200, only 1 document |
| GET /api/names, reader | authenticated | `@PreFilter` | 200, only reader's name |

This table reflects the demo configuration and data. When changing `AuthenticationEntryPoint`, form login, JWT resource server, or controller error handling, **the specific HTTP status may differ**, while what still must be verified is whether access is correctly granted or denied.

## 11. What Happens When Each Group Is Disabled?

This is how to detect "dangling" unconfigured annotations on your own.

### 11.1. Not Enabling @Secured

~~~java
@EnableMethodSecurity
~~~

When using only this line, `@PreAuthorize`/`@PostAuthorize` are still enabled, but `@Secured` is not enabled by default. If the HTTP route only requires authenticated and there is no other protective layer, `reader` can pass through a method annotated only with `@Secured("ROLE_ADMIN")`. **This is a dangerous situation** because the source code makes reviewers think the method is protected.

### 11.2. Not Enabling JSR-250

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

`@RolesAllowed`, `@PermitAll`, and `@DenyAll` are still not enabled if `jsr250Enabled=true` is missing. In particular, a `@DenyAll` method will not be blocked by the JSR-250 method-security advisor as assumed.

### 11.3. Disabling prePostEnabled

~~~java
@EnableMethodSecurity(
    prePostEnabled = false,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

In that case, do not expect `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, or `@PostFilter` to run. If the codebase still uses those annotations, disabling the group **changes security behavior** and must be verified with negative-case tests.

### 11.4. Why Should You Not Test Disabling Groups Directly in Production?

Disabling an annotation group can silently open up permissions. To learn the mechanics, use a test fixture or an isolated sandbox configuration branch. In production, any change to `@EnableMethodSecurity` flags must be treated as a **security policy migration**, with an annotation inventory and tests proving no bypass is introduced.

## 12. Comparing @PreAuthorize with @Secured and @RolesAllowed

### 12.1. Same Role-Based Goal

Three ways that are roughly equivalent in goal when the default role prefix is `ROLE_`:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void adminA() {}

@Secured("ROLE_ADMIN")
public void adminB() {}

@RolesAllowed("ADMIN")
public void adminC() {}
~~~

**But they are not equivalent in activation mechanism:**

- `adminA` requires prePostEnabled.
- `adminB` requires securedEnabled.
- `adminC` requires jsr250Enabled.

Nor do they promise identical behavior if custom role hierarchies, role prefixes, expression handlers, or different authorization managers are configured. For large systems, pick one primary convention and test real authority/role mappings.

### 12.2. When Dynamic Conditions Are Needed

A single static role is often not enough:

~~~java
@PreAuthorize(
    "#p0 == authentication.name and hasAuthority('SCOPE_profile.write')")
public void updateProfile(String username, String value) {
    // ...
}
~~~

This is an illustrative snippet; the method body must perform the business update using server-verified data. `@PreAuthorize` allows combining parameters, authorities, boolean expressions, and calling policy beans; `@Secured`/`@RolesAllowed` do not offer the same expressive power as SpEL.

In real services, ownership often requires a DB query: you can write a bean `accessPolicy.canEdit(authentication, documentId)` and reference it in the expression, but never write a policy allowing access based solely on an ownerId passed by the client. Keep policy beans backed by trusted data sources and avoid side effects during authorization.

### 12.3. Choosing Fewer Annotations Is Usually Easier to Review

A codebase using `@Secured`, `@RolesAllowed`, and `@PreAuthorize` on the same logic easily drifts in policy during refactoring. Unless constrained by compatibility, choosing `@PreAuthorize` as the primary convention is common because it supports expressions and is enabled by default when method security is enabled. The other groups remain useful when integrating with legacy code, Jakarta annotations, or organizational standards.

## 13. Enabling Method Security in an Existing Project

### 13.1. Audit the Annotation Inventory

Before changing configuration, inventory which annotations the codebase actually uses:

- `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`.
- `@Secured`.
- `@RolesAllowed`, `@PermitAll`, `@DenyAll` from `jakarta.annotation.security`.
- Custom meta-annotations or custom AuthorizationManagers/advisors.
- Rules placed on interfaces, classes, methods, and whether interface/class proxies pick up the annotations.

If any group is in use but not yet enabled, do not just update configuration while skipping access-denied tests.

### 13.2. Migrating from @EnableGlobalMethodSecurity to @EnableMethodSecurity

In older Spring Security codebases you may encounter:

~~~java
@EnableGlobalMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

This is a **legacy** annotation, not the preferred configuration approach in Spring Security 6. On newer baselines, use:

~~~java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

Although the flag names look similar, the infrastructure and extension points changed toward AuthorizationManager. If older code customized `GlobalMethodSecurityConfiguration`, expression handlers, permission evaluators, or metadata sources, **do not assume renaming the annotation alone is enough**. Consult the migration guide for your version and run integration tests for every method policy.

### 13.3. Do Not Enable Method Security by Manually Constructing Security Objects

You do not need to manually instantiate `MethodSecurityInterceptor`, `AuthorizationManagerBeforeMethodInterceptor`, or custom AOP proxies for standard use cases. `@EnableMethodSecurity` registers the corresponding infrastructure. Only extend with custom advisors/managers when there is a clear requirement and tests proving application order.

### 13.4. Enabling Method Security Does Not Automatically Block Every Method

Simply configuring `@EnableMethodSecurity` **does not make the framework require admin for every method**. Methods without applicable annotations/advices can still be called, depending on HTTP rules and other security layers. Therefore place method-level annotations at the proper service boundaries and maintain default-deny/authorization policies at web/domain layers.

## 14. Common Implementation Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| @PreAuthorize has no effect | Method security not enabled, or call bypasses proxy | Check @EnableMethodSecurity, Spring bean, and call graph |
| @Secured lets regular users through | securedEnabled defaults to false | Enable securedEnabled and add negative tests |
| @RolesAllowed does not enforce permissions | jsr250Enabled defaults to false or wrong package | Enable jsr250Enabled, use Jakarta imports in Boot 3 |
| @PermitAll yet HTTP still returns 401 | HTTP filter chain requires authentication | Adjust HTTP policy intentionally; never drop the whole chain |
| @DenyAll does not block admin | JSR-250 not enabled or call bypasses proxy | Test enabled flag and proxy invocation |
| @PreAuthorize "#username" cannot find variable | Missing parameter name metadata | Use #p0/#a0 or explicit -parameters |
| @PreAuthorize denies user with ADMIN role | Wrong ROLE_ prefix or authorities mapping | Inspect Authentication.getAuthorities() safely |
| @PostAuthorize denies yet DB already changed | Method ran before post-check | Use pre-checks before side effects |
| @PostFilter makes requests slow | Loads entire collection before filtering | Scope query by owner/tenant in DB, paging, and policy layer |
| @PreFilter fails on immutable input | Advisor needs to mutate/filter collection | Use an appropriate mutable collection, test filterTarget |
| Calling annotated method from same class still runs | Self-invocation bypasses proxy | Extract bean / protect entry point |
| Unit test `new ProtectedService()` ignores annotation | Object outside Spring container | Integration test calling injected Spring bean/proxy |
| Private/final method is not intercepted | Proxy/AOP limitation | Move to public proxied boundary; review Kotlin/final |
| Admin allowed via URL yet service returns 403 | Method rule is stricter than web rule | This can be intended; verify both layers |
| @WithMockUser test passes yet real JWT still fails | Test mocks Authentication, skips decoder/authn | Add end-to-end auth tests |
| POST returns 403 before calling service | CSRF filter blocked it | Separate CSRF tests from method-security tests |
| Custom annotation does not work | Meta-annotation/advisor not recognized | Check Spring Security version, target, and proxy |
| Multiple advisors apply together | Combined annotations cause unexpected conditions | Use clear convention and test combinations |
| Refactoring internal method calls | Proxy boundary changed | Regression tests from controller/external bean |

### 14.1. Do Not Call Authentication.getName() Manually and Assume Method Security Is On

Having a service manually read `SecurityContextHolder.getContext().getAuthentication()` and check the username **is not the same** as method-security advice being active. It can be a valid business authorization check if done carefully, but it does not prove `@PreAuthorize` works. To confirm advisors are active, write negative tests for annotations **on the Spring-managed service**.

### 14.2. Do Not Rely Solely on @WithMockUser

`@WithMockUser` is useful for testing service method authorization with a simulated Authentication; however, it **does not verify form login, password encoders, JWT signatures, opaque introspection, or HTTP filters**. In this lab, MockMvc uses `httpBasic()` to exercise authentication and the method-security chain; in production, add tests for your actual authentication mechanism.

### 14.3. Distinguishing an Unexecuted Annotation from a Denied Annotation

If a user receives 403:

- Did execution reach method security?
- Which annotation is blocking? Is the SpEL expression correct?
- What are the user's authorities?
- Did the method body run (distinguish pre vs post)?
- Did the HTTP layer or CSRF block it beforehand?

If a user is **unexpectedly allowed**:

- Is that annotation group actually enabled?
- Did the call go through the proxy?
- Is the bean managed by Spring?
- Is there self-invocation, a final method, a custom proxy, or a direct call via constructor?
- Are method-level annotations bypassed by another code path?
- Were overly broad authentication/authorities granted earlier?

**A 200 result does not prove method security is enabled**, because the service might not be intercepted by any advisor at all. A **403 for an authenticated user lacking the required permission** is the critical discriminating test.

## 15. Multi-Layer Testing Strategy

### 15.1. Unit Testing the Policy

When business policies are complex, extract a permission-checking component backed by trusted data sources to unit-test logic: owner, tenant, scopes, account status. This test does not yet prove annotations or proxies are applied; it only proves the logic behaves properly given inputs.

### 15.2. Spring Method-Security Integration Tests

Autowire the **real service bean from the Spring context**, apply `@WithMockUser` for allow/deny cases, and use `assertThrows(AccessDeniedException.class, ...)` for negative cases. This proves advisors intercept calls from tests through the injected bean. Never instantiate the service with `new`.

Illustrative snippet:

~~~java
@Test
@WithMockUser(username = "reader", roles = "USER")
void readerCannotCallAdminService() {
    assertThrows(AccessDeniedException.class,
        () -> protectedOperations.adminSecured());
}
~~~

This requires importing JUnit `assertThrows`, `AccessDeniedException`, and `WithMockUser` along with a Spring test context; it is a **test snippet**, not a full test class. Do not use `@WithMockUser(roles="ADMIN")` as proof that HTTP Basic/passwords are genuinely verified.

### 15.3. MockMvc Controller-to-Service Integration

As in section 9, requests flow through HTTP Basic → controller → service proxy. This is a strong layer for catching:

- Overly broad HTTP routes.
- Disabled annotation groups.
- Service call graphs bypassing proxies.
- Role prefix/authority mismatches.
- Pre/post filter behavior.
- Public pages or endpoints still blocked by HTTP rules.

### 15.4. End-to-End Tests with Real Auth Sources

If production uses form login/sessions, test CSRF, sessions, and remember-me/re-auth appropriately. If using JWT, test signature, issuer, audience, expiration, and authorities converters. If using opaque access tokens, test introspection/invalid tokens/server failures. Method security **does not replace** input credential validation.

### 15.5. Essential Negative-Test Matrix

| Group | Positive | Critical Negative Case |
| --- | --- | --- |
| @PreAuthorize | Matching owner or role | Authenticated but wrong owner/role |
| @PostAuthorize | Own object | Object belonging to someone else |
| @PreFilter | List filtered properly | Does not let another user's items slip through |
| @PostFilter | List contains only permitted items | Does not return unfiltered list to user |
| @Secured | ROLE_ADMIN | ROLE_USER receives 403 |
| @RolesAllowed | ROLE_MANAGER | ROLE_USER/ROLE_ADMIN other role receives 403 |
| @PermitAll | Anonymous and HTTP permit | HTTP deny must still be able to reject |
| @DenyAll | No positive case | Even admin is denied |
| Proxy boundary | Controller calls service bean | Self-call/new object must not be relied upon as a security guarantee |

## 16. Self-Check Exercises

1. Why might an application that already has a SecurityFilterChain not have `@PreAuthorize` enabled on services?
2. With `@EnableMethodSecurity` alone, which annotation groups are enabled by default and which remain disabled?
3. Write a configuration enabling both `@Secured` and JSR-250 while keeping pre/post annotations active.
4. In Spring Boot 3, what is the right package import for `@RolesAllowed` and `@PermitAll`? Why must old `javax.annotation.security` code be reviewed?
5. A service only uses `@Secured("ROLE_ADMIN")`, but the config only has `@EnableMethodSecurity`. What bypass scenario can occur?
6. How does `@PreAuthorize("hasRole('ADMIN')")` differ from `@Secured("ROLE_ADMIN")` in syntax, SpEL capability, and activation flag?
7. Does `@RolesAllowed("MANAGER")` normally correspond to `ROLE_MANAGER` or `ROLE_ADMIN`?
8. Why can't a `@PermitAll` service open an HTTP endpoint if the URL policy requires `hasRole('ADMIN')`?
9. Why is `@DenyAll` worth testing with an authenticated admin user instead of only anonymous?
10. For an `updateInvoice()` method with side effects, what is the risk of using `@PostAuthorize` instead of `@PreAuthorize`?
11. What performance and data-minimization issues can `@PostFilter` over 100,000 records cause?
12. Why does `@PreFilter` require attention to mutable inputs, `filterTarget`, and collection types?
13. If an expression uses `#username` but the build lacks `-parameters`, what error can occur? How does using `#p0` differ?
14. When an annotated method is called from another method **in the same class**, does default proxy mode automatically intercept it?
15. Why does `new ProtectedOperations()` in a unit test fail to prove method security?
16. Describe the trade-offs between JDK dynamic proxies and class-based proxies for method interception.
17. If a `final` method carries `@PreAuthorize`, what must be examined before assuming it is protected by a proxy?
18. Use MockMvc tests to prove an authenticated `reader` is denied on `@Secured` and `@RolesAllowed`.
19. If `jsr250Enabled=true` is changed to false and the app still compiles, what kind of test will catch the lost protection?
20. With a JWT scope `docs.read` converted to `SCOPE_docs.read`, what expression checks the exact authority?
21. Why do two authorization annotations from different groups on the same method not necessarily follow "later annotation overrides earlier annotation" semantics?
22. Should method security be placed only on controllers while skipping services called from scheduled jobs, messaging consumers, or other internal callers?
23. A `@PostAuthorize` denies access after a `@Transactional` service has updated the DB; what must you verify regarding advisor order and rollback?
24. When enabling `@EnableMethodSecurity` during migration from `@EnableGlobalMethodSecurity`, which extension points and tests need review?
25. Build a checklist for a service protecting documents by owner/tenant: HTTP route, method annotation, persisted ownership, auth converter, and negative tests.

## 17. Pre-Production Checklist

- [ ] `@EnableMethodSecurity` is declared properly in Spring configuration.
- [ ] `prePostEnabled`, `securedEnabled`, and `jsr250Enabled` match the annotations actually used in the codebase.
- [ ] JSR-250 annotations come from `jakarta.annotation.security` in Spring Boot 3.
- [ ] Tests exist where authenticated users with the wrong role/scope/owner are blocked (not just anonymous 401).
- [ ] Every sensitive method sits at a Spring-managed bean boundary and is invoked through a proxy.
- [ ] Self-invocation, private/final methods, and beans instantiated outside Spring have been audited.
- [ ] Business actions with side effects are checked **before** execution, not only with @PostAuthorize.
- [ ] Owner/tenant/resource authorization relies on trusted data, never trusting request params.
- [ ] @PostFilter is not used in place of query filtering for large/sensitive datasets.
- [ ] @PreFilter handles collections/mutable inputs safely and is covered by tests.
- [ ] Role prefix/authorities mappings are consistent between HTTP auth and method authorization.
- [ ] The HTTP filter chain still properly blocks anonymous requests, CSRF, and invalid credentials.
- [ ] @PermitAll on a method is not treated as bypassing HTTP security.
- [ ] Annotations on interfaces/classes/overrides/meta-annotations have been tested through proxies.
- [ ] Interactions with @Transactional, @Async, @Cacheable, and exception handling have been reviewed.
- [ ] If multiple annotation groups are used, no overlapping rules create unpredictable policies.
- [ ] Migration/rollback tests exist when upgrading Spring Security versions and legacy method security configs.
- [ ] Sensitive Authentication/credentials/tokens are not logged when debugging.
- [ ] Security policy changes go through code review and regression testing.
- [ ] Tests cover blocking unauthorized calls on services invoked from jobs, message listeners, or non-HTTP entry points.

## 18. Conclusion

`@EnableMethodSecurity` is not a "turn on every annotation" switch. In Spring Security 6.x, it **enables the pre/post group by default**; `@Secured` requires `securedEnabled=true`, while `@RolesAllowed`/`@PermitAll`/`@DenyAll` require `jsr250Enabled=true`. These are three distinct groups that must be intentionally enabled and verified with tests.

Even when an annotation group is enabled, **rules only protect calls that method-security advice actually intercepts**, usually via a Spring AOP proxy. Therefore do not just check source code for `@PreAuthorize`; verify the controller → service bean/proxy call path, 403 outcomes for unauthorized users, and behavior with self-invocation/side effects.

A memorable implementation formula: **enable the right groups → place rules at business boundaries → build Authentication from trusted sources → test negative cases through proxies → keep HTTP authorization and method authorization as two cooperating layers**. Done thoroughly, method security becomes real business protection rather than a set of annotations that merely look safe.
