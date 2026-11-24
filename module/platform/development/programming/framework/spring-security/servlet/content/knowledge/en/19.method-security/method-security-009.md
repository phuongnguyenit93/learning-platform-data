# Composed Annotations for Reusing Authorization Policies in Spring Security Servlet

## 1. Why Do We Need Composed Annotations?

A Spring Security Servlet application has multiple services handling different resources. For example:

- Only `ROLE_ADMIN` may view administrative reports.
- Users may only read reports they own; administrators may read more per system policy.
- An audit endpoint requires **both** the admin role and full authentication, not merely remember-me.
- The same report-reading policy applies to methods in both `ReportService` and `ArchiveService`.
- These rules must be enforced whether the service is called from a controller, another service, or a task with a valid authentication mechanism.

The direct approach is repeating annotations on every method:

```java
@PreAuthorize("hasRole('ADMIN')")
public String adminSummary() {
    return "admin:summary";
}
```

With many methods, repeating long SpEL expressions easily causes **policy drift**: one place uses `hasRole('ADMIN')`, another only checks `authenticated()`, or typos a bean name. Spring Security supports **meta-annotations** (composed annotations): you define a custom Java annotation and place `@PreAuthorize` on that annotation definition itself.

Example:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN')")
public @interface RequiresAdmin {
}
```

When a method is annotated with `@RequiresAdmin`, Spring Security method security discovers `@PreAuthorize` on the composed annotation and enforces the corresponding policy. Thus the annotation name expresses business intent while the rule body has a single maintainable definition.

**Learning objectives:**

1. Distinguish composed annotations, repeatable annotations, and SpEL expressions in method security.
2. Create `@RequiresAdmin`, `@CanReadReport`, and `@RequiresAdminFull` with proper `@Target`, `@Retention`, and `@Documented`.
3. Enable `@EnableMethodSecurity` and place annotations on **public methods of Spring-managed beans**.
4. Understand method arguments in SpEL, `@P("reportId")`, and `@reportPermission` bean calls.
5. Know proxy/self-invocation limits, HTTP authorization vs method authorization ordering, and how to write tests.
6. Avoid confusing reusable annotations with creating new permissions or bypassing authentication.

The main example uses **Java 17, Spring Boot 3.3.5, and Spring Security 6.3.x (Servlet/MVC)**. Annotation templating features or newer APIs in other versions must be verified against the documentation for the version in use; this lesson does not assume identical syntax across all versions.

## 2. Method Security and HTTP Security Are Two Separate Layers

With HTTP authorization, `authorizeHttpRequests` applies rules by request path. With **method security**, Spring Security applies rules when invoking **a Java method** carrying the corresponding annotation through an appropriate interception/proxy mechanism.

```text
HTTP request GET /reports/r101
       |
       v
Servlet SecurityFilterChain
       |
       +-- Authentication (Basic/session/bearer/form)
       +-- authorizeHttpRequests(...) allows request to proceed
       |
       v
ReportController
       |
       v
Spring bean proxy of ReportService
       |
       +-- Before-method authorization interceptor
       |        reads @CanReadReport
       |        finds meta-annotation @PreAuthorize
       |        evaluates SpEL with Authentication + method args
       |
       +-- GRANT: invoke target service method
       |
       +-- DENY: throw AccessDeniedException
       |
       v
Service result -> Controller response
```

The two protection layers answer different questions:

| Layer | Subject Inspected | Example |
| --- | --- | --- |
| HTTP filter security | URL, method, request, and authentication | `GET /reports/**` requires login |
| Method security | Java method call and arguments | User may only view report IDs they own |
| Domain/data policy | Real resource, tenant, state, and ownership | Report `r101` belongs to user `lan` |
| Business transaction | Checks when executing data writes | Do not change owner after authorization without matching policy |

HTTP security does not always protect service calls from message listeners, schedulers, or tests; method security can apply when calls **pass through the proxy properly** with an appropriate security context. Yet method security also does not replace analyzing all HTTP entry points and CSRF.

### 2.1. Enabling Method Security

In a Spring Security 6 Servlet application, declare:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    // Beans and SecurityFilterChain...
}
```

`@EnableMethodSecurity` activates the method-security infrastructure, supporting `@PreAuthorize` and `@PostAuthorize` by default. Having `@PreAuthorize` without enabling the appropriate interception mechanism means annotations may not execute as expected.

Older applications may show `@EnableGlobalMethodSecurity`; in Spring Security 6, prefer `@EnableMethodSecurity`. If you want `@Secured` or `@RolesAllowed`, check flags such as `securedEnabled` and `jsr250Enabled`; do not assume they are enabled by default.

### 2.2. A Composed Annotation Is Not an HTTP Filter

`@RequiresAdmin` does not add a filter or verify passwords. It lets method security discover an authorization expression declared via `@PreAuthorize`. Authentication typically comes from a request that passed through the security filter chain, or from a security context established reliably in another task type.

## 3. Meta-Annotations in Java: Syntax and Discovery

In Java, annotations can be placed on **other annotation definitions**. For custom authorization annotations, you typically need:

- `@Target`: selects where the annotation can be used; in this example `ElementType.METHOD`. `TYPE` may also be allowed when a policy truly applies to every method of a class.
- `@Retention(RetentionPolicy.RUNTIME)`: preserves metadata at runtime so the framework can inspect it.
- `@Documented`: allows Javadoc tools to include the annotation in API documentation.
- `@PreAuthorize("...")`: the security condition Spring Security finds and enforces when method security is enabled.

Complete example of a parameterless annotation:

```java
package example.meta.policy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN')")
public @interface RequiresAdmin {
}
```

Then use it:

```java
@RequiresAdmin
public String adminSummary() {
    return "admin:summary";
}
```

**Meaning:** the annotation names a fixed policy so multiple methods share it, reducing SpEL copy-paste mistakes. It does not invent a new role, grant privileges to callers, or populate Authentication in SecurityContext.

### 3.1. Why Is RetentionPolicy.RUNTIME Required?

Method security inspects annotations via runtime metadata. Using `SOURCE` or `CLASS` without keeping runtime metadata as the framework requires means custom meta-annotations may not be detected when making decisions.

`@Documented` is only for documentation; it does **not** enable authorization. Nor is `@Inherited` a universal solution for method-level inheritance because Java's annotation inheritance rules differ from Spring's merged annotation search; test on interfaces, overrides, and proxies directly.

### 3.2. METHOD or TYPE?

An annotation with only `@Target(ElementType.METHOD)` can be placed on methods, not classes. If the policy is identical across every method in a service, you can consider:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN')")
public @interface AdminOnly {
}
```

However, a class-level policy is a broad decision: a newly added `public` method later might also inherit that policy depending on inheritance/override rules. If the annotation uses variables like `#reportId`, placing it on a class is only safe when every protected method actually has that matching argument. The runnable example chooses **METHOD-only** to keep contracts explicit.

### 3.3. Do Not Confuse Composed Annotations with Repeating Annotations

A meta-annotation like `@RequiresAdmin` **defines one named rule**. That is different from stacking multiple `@PreAuthorize` annotations on the same method hoping they automatically combine.

Spring Security **does not support arbitrarily repeating `@PreAuthorize`** on the same method as a list of conditions. To require both a role and full trust, write **one expression** `hasRole('ADMIN') and isFullyAuthenticated()`, or use an explicit composite authorization manager/policy.

## 4. Composed Annotations with Reusable SpEL Expressions

For fixed rules, simple SpEL suffices:

```java
@PreAuthorize("hasRole('ADMIN')")
public @interface RequiresAdmin {
}
```

For resources identified by method arguments, you can reference parameters:

```java
@PreAuthorize("@reportPermission.canRead(authentication, #reportId)")
public @interface CanReadReport {
}
```

In this expression:

- `@reportPermission` is a Spring bean named `reportPermission`, not a Java annotation.
- `canRead(...)` is a public method on that bean returning an authorization boolean.
- `authentication` is the Authentication object in the evaluation context.
- `#reportId` is the argument of the protected method.
- The expression returns `true` to allow, `false` to deny.

This is an **illustrative meta-annotation fragment**; complete files are provided in the sample project in section 9.

### 4.1. Ensuring Argument Names in SpEL

Expressions like `#reportId` depend on Spring Security resolving parameter names. This can come from compiler metadata such as `-parameters` or a dedicated annotation.

In the runnable code, use:

```java
@CanReadReport
public String read(@P("reportId") String reportId) {
    return "report:" + reportId;
}
```

`@P` belongs to package `org.springframework.security.core.parameters.P`. Using `@P("reportId")` forms an explicit contract, helpful when methods are compiled without parameter names or invoked via certain proxy/interface setups.

Do not copy SpEL `#id` from another method if the argument is exported as `reportId`. If the name fails to resolve, the expression may receive null or throw an evaluation error; policies should deny explicitly rather than failing open.

### 4.2. The Permission Bean Must Be Spring-Managed

If the expression writes `@reportPermission.canRead(...)`, there must be a bean:

```java
@Component("reportPermission")
public class ReportPermission {
    public boolean canRead(Authentication authentication, String reportId) {
        // Authorization rule backed by trusted server data.
        return false; // Placeholder fragment illustrating syntax only.
    }
}
```

This snippet **only illustrates structure**; the full implementation is in section 9. At runtime, code must use server data such as owner/tenant, never trusting a browser-supplied `?owner=lan` query parameter.

### 4.3. Why Not Put Long DB Queries Directly in SpEL?

An expression like `@reportPermission.canRead(authentication, #reportId)` acts as *delegation*. It keeps annotations concise and centralizes ownership/tenant logic in a unit-testable bean.

Writing multi-table DB policies, time windows, account status checks, and exception handling directly in SpEL makes code hard to review, hard to maintain, and prone to subtle null semantics. Keep annotations expressive of "which permission is required", while business policies reside in a well-scoped Java class.

## 5. Composed Annotations and Policy Maintenance Principles

### 5.1. One Policy, Multiple Usage Sites

`@CanReadReport` can be placed on:

```java
@CanReadReport
public String read(@P("reportId") String reportId) {
    return "report:" + reportId;
}
```

and:

```java
@CanReadReport
public String archived(@P("reportId") String reportId) {
    return "archive:" + reportId;
}
```

If both services genuinely share the exact same report-ownership policy, updating the **annotation definition** or the permission bean keeps all callers in sync. If archives have separate permission rules, never force them onto the same annotation merely because both names contain "report".

### 5.2. Name After Business Intent

Consider names such as:

- `@RequiresAdmin`: when requiring a role.
- `@CanReadReport`: when permission depends on `reportId`.
- `@RequiresAdminFull`: when admin and full authentication are both required.

Names like `@SecuredThing` or `@AllowEverythingExceptGuests` fail to communicate a clear contract; when policies evolve, confusion follows. Widely used annotations should carry Javadoc describing required arguments/data and protection guarantees.

### 5.3. Prevent Policy Drift When Adding Endpoints

The same URL pattern may route to multiple service methods. A new method missing an annotation can be invoked without the corresponding method-security check; HTTP authorization might or might not cover that path.

Maintain code-review checklists and integration tests for new service entry points. Never treat meta-annotations as proof that every method in a package is automatically protected.

## 6. Combining Multiple Conditions in One Annotation

A policy requiring **admin role AND full authentication** can be written:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN') and isFullyAuthenticated()")
public @interface RequiresAdminFull {
}
```

This differs from:

```java
// Do not rely on this to automatically AND two conditions:
@RequiresAdmin
@PreAuthorize("isFullyAuthenticated()")
public String auditSummary() {
    return "audit:summary";
}
```

The second approach introduces multiple overlapping `@PreAuthorize` rule sources and can cause ambiguity/configuration errors. **Define a dedicated meta-annotation** with an explicit AND expression, or use a composite policy manager for complex conditions.

### 6.1. hasRole Does Not Replace isFullyAuthenticated

A remember-me authenticated user can still hold `ROLE_ADMIN`. If a method only checks `hasRole('ADMIN')`, that alone does not require full authentication. Conversely, `isFullyAuthenticated()` does not prove `ROLE_ADMIN`. They are two orthogonal axes.

**Security note:** "fully authenticated" in Spring Security mainly distinguishes from anonymous and remember-me; it **does not prove recent MFA**. Truly sensitive operations may need recent re-authentication, trusted devices, or dedicated MFA.

### 6.2. Do Multiple Annotation Attributes Automatically Become Expressions?

Do not expect this hypothetical syntax to work automatically in Spring Security 6.3.x:

```java
// NOT an implementation automatically compatible across versions:
@PreAuthorize("hasRole('{role}')")
public @interface RequiresRole {
    String role();
}
```

Merely declaring `String role()` does not guarantee Spring Security substitutes `{role}` with the attribute value. Some newer Spring Security versions provide **annotation expression templates** given matching beans/config. If a project needs parameterized annotations, follow the exact version's documentation and write integration tests; never assume literal `{role}` interpolates automatically.

In the runnable example we use **fixed annotations** to ensure clarity and compatibility with the pinned versions.

## 7. @PreAuthorize, @PostAuthorize, and Other Annotations

### 7.1. @PreAuthorize: Check Before Calling the Method

`@PreAuthorize` enforces policy before the method body (when interception is active). If denied, the target method **does not execute** on that call. Ideal for actions with side effects because it blocks early before mutation.

For instance, `@CanReadReport` checks owner/role before `ReportService.read` returns data.

### 7.2. @PostAuthorize: Check the Return Value

`@PostAuthorize` can evaluate SpEL **after** the method runs, e.g. referencing `returnObject`:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PostAuthorize(
    "returnObject != null and " +
    "(returnObject.owner() == authentication.name or hasRole('ADMIN'))"
)
public @interface CanSeeReturnedReport {
}
```

This is an **illustrative** example; import `org.springframework.security.access.prepost.PostAuthorize`. The returned object needs a method like `owner()`, e.g. Java record `record Report(String id, String owner) {}`. When role/trust/return object checks fail, the interceptor prevents returning the result to the caller.

**Warning:** the method has already executed before `@PostAuthorize` runs. Never use it as the sole safeguard for operations that write to a DB, transfer money, or send emails; side effects can happen prior to denial. For mutations, `@PreAuthorize` and transaction/domain-layer checks are usually far more appropriate.

### 7.3. @PreFilter, @PostFilter

Spring Security also provides `@PreFilter`/`@PostFilter` to filter collections/arrays or supported structures per version semantics. They can be placed in composed annotations when suitable.

Test collection types, null handling, performance, and semantics on large datasets. Never load all reports from the DB and then filter with `@PostFilter` thinking you have efficient query-level authorization: sensitive data retrieval already happened before filtering and can consume massive resources.

### 7.4. @Secured and @RolesAllowed

`@Secured` relies primarily on roles/authorities, while `@RolesAllowed` comes from JSR-250/Jakarta in compatible environments. Depending on version and `@EnableMethodSecurity` flags, they may need explicit opt-in.

This lesson uses `@PreAuthorize` because it can express both roles and business policies using beans and method arguments. Avoid mixing multiple annotation families on the same method without understanding rule precedence/ambiguity.

## 8. Proxy Limitations: When Annotations May Not Run

### 8.1. Spring-Managed Beans and Calls Through Proxies

Method security in standard configurations works via Spring AOP proxies. A call **from another bean through the proxy** to a public annotated method is intercepted. Conversely, manually creating `new ReportService()` is not wrapped by a Spring method-security proxy.

Therefore the runnable example registers services via `@Service`, injects them into the controller, and calls methods from the controller. Tests also call the directly injected service bean to confirm the interceptor truly runs.

### 8.2. Self-Invocation

Consider:

```java
@Service
public class ExampleService {
    public String facade(String id) {
        return this.protectedOperation(id);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String protectedOperation(String id) {
        return "protected:" + id;
    }
}
```

This is an **illustrative snippet**, not a file in the runnable project below. In proxy-based AOP, calling `this.protectedOperation(...)` from the same object can **bypass the method-security proxy**, meaning the annotation is not enforced on that internal call.

The cleaner solution is moving the protected method to another bean and calling it through the proxy, or structuring policies at another appropriate service boundary. Never "fix" this by putting annotations on private methods hoping proxies intercept them.

### 8.3. Private/Final Methods and Proxy Types

Most proxy-based method interception does not protect private methods, and some proxy strategies have limitations on final classes/final methods. With interface proxies, whether a method belongs to the interface can also affect proxy selection and annotation lookup.

Test beans in the real runtime environment, especially with Kotlin (final by default), Java records/final classes, package-private methods, and Spring AOT setups. If using AspectJ weaving instead of proxies, interception semantics may differ; do not extrapolate identical self-invocation behavior across every weaving mode.

### 8.4. Methods Called Outside HTTP

If a scheduled job or message listener calls a method-secured Spring bean without a suitable `Authentication` in `SecurityContextHolder`, the policy may deny even though there is no HTTP request. That can be correct by design.

Do not "fix" it by fabricating a fake ROLE_ADMIN Authentication from unverified data. System tasks need an explicit trust model, service identity, and dedicated policy when legitimately authorized.

## 9. Complete Spring Boot 3.3.5 + Java 17 Project

This is a self-contained Servlet/MVC application with **three composed annotations**:

| Annotation | Meta-Annotation | Condition |
| --- | --- | --- |
| `@RequiresAdmin` | `@PreAuthorize("hasRole('ADMIN')")` | Has admin role |
| `@CanReadReport` | `@PreAuthorize("@reportPermission.canRead(authentication, #reportId)")` | Report exists and user is owner or admin |
| `@RequiresAdminFull` | `@PreAuthorize("hasRole('ADMIN') and isFullyAuthenticated()")` | Admin and full authentication |

Both `ReportService` and `ArchiveService` use `@CanReadReport`. The HTTP layer only requires authentication for private routes; **detailed policies are enforced on service methods**.

### 9.1. Directory Structure

```text
method-meta-authorization/
  pom.xml
  src/
    main/
      java/example/meta/
        MetaAuthorizationApplication.java
        SecurityConfig.java
        ReportPermission.java
        ReportService.java
        ArchiveService.java
        DemoController.java
        policy/
          RequiresAdmin.java
          RequiresAdminFull.java
          CanReadReport.java
    test/
      java/example/meta/
        MetaAuthorizationTest.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>method-meta-authorization</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven `spring-boot-starter-security` pulls in the appropriate method-security/Spring AOP dependencies for Spring Boot 3.3.x. `spring-security-test` helps test SecurityContext and form/Basic mechanisms at the test layer.

### 9.3. MetaAuthorizationApplication.java

```java
package example.meta;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetaAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetaAuthorizationApplication.class, args);
    }
}
```

### 9.4. Annotation @RequiresAdmin

File `src/main/java/example/meta/policy/RequiresAdmin.java`:

```java
package example.meta.policy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN')")
public @interface RequiresAdmin {
}
```

By default `hasRole('ADMIN')` checks authority `ROLE_ADMIN` by convention. In the example, Spring Security's `roles("ADMIN")` creates this authority.

### 9.5. Annotation @RequiresAdminFull

File `src/main/java/example/meta/policy/RequiresAdminFull.java`:

```java
package example.meta.policy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN') and isFullyAuthenticated()")
public @interface RequiresAdminFull {
}
```

This annotation bundles two conditions inside **one** clear expression. With valid HTTP Basic authentication in the sample, user admin is recognized as fully authenticated by the standard trust resolver; do not confuse with remember-me tokens.

### 9.6. Annotation @CanReadReport

File `src/main/java/example/meta/policy/CanReadReport.java`:

```java
package example.meta.policy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("@reportPermission.canRead(authentication, #reportId)")
public @interface CanReadReport {
}
```

This is the core point of the lesson: methods annotated with `@CanReadReport` must export an argument named `reportId` into the SpEL context. The services below use `@P("reportId")`.

### 9.7. ReportPermission: Ownership Retrieved from Server

File `src/main/java/example/meta/ReportPermission.java`:

```java
package example.meta;

import java.util.Map;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportPermission")
public class ReportPermission {

    private final Map<String, String> owners = Map.of(
        "r101", "lan",
        "r202", "minh"
    );

    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public boolean canRead(Authentication current, String reportId) {
        if (reportId == null) {
            return false;
        }

        String owner = owners.get(reportId);
        if (owner == null) {
            return false;
        }

        if (current == null || !trust.isAuthenticated(current)) {
            return false;
        }

        boolean isOwner = owner.equals(current.getName());
        boolean isAdmin = current.getAuthorities().stream()
            .anyMatch(authority ->
                "ROLE_ADMIN".equals(authority.getAuthority()));

        return isOwner || isAdmin;
    }
}
```

Points to remember:

- Reader `lan` may view `r101` but not `minh`'s `r202`.
- Admin may view existing reports under the demo policy. In multi-tenant products, admins may still be scoped within a tenant.
- Missing report ID → deny; never `return true` or "abstain" leaving another layer to grant.
- Ownership comes from a **server-side** map, not from a client-supplied `?owner=lan` query parameter.
- `AuthenticationTrustResolver` excludes anonymous callers even when `AnonymousAuthenticationToken.isAuthenticated()` may return true.
- The map is strictly for the demo; in real products use repositories/authorization domain services and check permissions when loading/committing data.

### 9.8. ReportService.java

```java
package example.meta;

import example.meta.policy.CanReadReport;
import example.meta.policy.RequiresAdmin;
import example.meta.policy.RequiresAdminFull;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @CanReadReport
    public String read(@P("reportId") String reportId) {
        return "report:" + reportId;
    }

    @RequiresAdmin
    public String adminSummary() {
        return "admin:summary";
    }

    @RequiresAdminFull
    public String auditSummary() {
        return "audit:summary";
    }
}
```

This is a Spring-managed bean; calls from the controller through the injected `ReportService` pass through the appropriate method-security proxy. Never place password verification inside service method bodies.

### 9.9. ArchiveService.java: Reusing the Same Annotation

```java
package example.meta;

import example.meta.policy.CanReadReport;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class ArchiveService {

    @CanReadReport
    public String archived(@P("reportId") String reportId) {
        return "archive:" + reportId;
    }
}
```

`ReportService.read` and `ArchiveService.archived` differ in output yet share the **same authorization contract**. If archive policy differs from standard report policy, create a separate annotation; reuse is only right when business rules genuinely align.

### 9.10. SecurityConfig.java: Enabling Method Security and HTTP Basic

```java
package example.meta;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
            .password(encoder.encode("lan-demo"))
            .roles("USER")
            .build();

        UserDetails minh = User.withUsername("minh")
            .password(encoder.encode("minh-demo"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(lan, minh, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        // Demo only has GET endpoints; keep default CSRF protection intact.
        return http.build();
    }
}
```

**Why does the HTTP layer only use authenticated?** The example intentionally places owner/admin policies **on methods** so you can observe method security operating. This is not advice to use `anyRequest().authenticated()` for every product: a new route missing a method annotation could be left open to all authenticated users. Production requires reviewing route coverage, least privilege, and using detailed HTTP policies, `denyAll` fallbacks, and domain/service checks as appropriate.

**HTTP Basic** is only for testing authorization without an HTML form. Base64 is not encryption; production requires HTTPS and proper secret storage. `STATELESS` does not exempt APIs with write operations from CSRF evaluation; this GET-only example does not disable CSRF.

### 9.11. DemoController.java

```java
package example.meta;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ReportService reports;
    private final ArchiveService archive;

    public DemoController(ReportService reports, ArchiveService archive) {
        this.reports = reports;
        this.archive = archive;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/reports/{reportId}")
    public String report(@PathVariable("reportId") String reportId) {
        return reports.read(reportId);
    }

    @GetMapping("/archive/{reportId}")
    public String archived(@PathVariable("reportId") String reportId) {
        return archive.archived(reportId);
    }

    @GetMapping("/admin/summary")
    public String adminSummary() {
        return reports.adminSummary();
    }

    @GetMapping("/audit/summary")
    public String auditSummary() {
        return reports.auditSummary();
    }
}
```

The controller does not repeat SpEL or owner checks. Every call to protected service methods goes **through the proxy**, so the composed annotations are enforced.

## 10. JUnit 5 and MockMvc Testing

File `src/test/java/example/meta/MetaAuthorizationTest.java`:

```java
package example.meta;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MetaAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportService reports;

    @Autowired
    ArchiveService archive;

    @Test
    void publicRouteIsAvailableWithoutAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousPrivateRouteGetsBasicChallenge() throws Exception {
        MvcResult response = mvc.perform(get("/reports/r101"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        String challenge =
            response.getResponse().getHeader("WWW-Authenticate");
        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Basic"));
    }

    @Test
    void lanCanReadOwnReport() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r101"));
    }

    @Test
    void lanCannotReadMinhReport() throws Exception {
        mvc.perform(get("/reports/r202")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void minhCanReadHisReport() throws Exception {
        mvc.perform(get("/reports/r202")
                .with(httpBasic("minh", "minh-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r202"));
    }

    @Test
    void adminCanReadBothReports() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk());
        mvc.perform(get("/reports/r202")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk());
    }

    @Test
    void missingReportIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(get("/reports/missing")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void samePolicyWorksOnArchiveService() throws Exception {
        mvc.perform(get("/archive/r101")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("archive:r101"));
        mvc.perform(get("/archive/r202")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void normalUserCannotAccessAdminSummary() throws Exception {
        mvc.perform(get("/admin/summary")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminSummary() throws Exception {
        mvc.perform(get("/admin/summary")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:summary"));
    }

    @Test
    void normalUserCannotAccessAdminFullAudit() throws Exception {
        mvc.perform(get("/audit/summary")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminFullAudit() throws Exception {
        mvc.perform(get("/audit/summary")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("audit:summary"));
    }

    @Test
    void wrongPasswordGetsUnauthorized() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("lan", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void directSpringBeanCallIsProtectedByMethodProxy() {
        // No HTTP: call the injected Spring bean via the method proxy.
        assertThrows(AccessDeniedException.class,
            () -> reports.read("r202"));

        assertThrows(AccessDeniedException.class,
            () -> archive.archived("r202"));
    }

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void directSpringBeanCallAllowsOwnedReport() {
        // Test the granted side as well, not only denials.
        String output = reports.read("r101");
        org.junit.jupiter.api.Assertions.assertEquals(
            "report:r101", output
        );
    }
}
```

**Fifteen tests** exercise both HTTP integration and direct calls to Spring beans:

- Anonymous → HTTP 401 + Basic challenge for routes requiring authentication.
- `lan` → reads `r101` yet cannot read `minh`'s `r202`.
- `minh` → reads `r202`.
- Admin → reads valid existing reports; non-existent IDs are still denied.
- `ArchiveService` reuses `@CanReadReport` identically to `ReportService`.
- `@RequiresAdmin` protects the admin page; `@RequiresAdminFull` protects audit.
- Wrong Basic password → HTTP 401.
- `@WithMockUser` is only used for **direct service call tests** to build a test SecurityContext; **never** use it to claim real passwords were tested. HTTP tests use `httpBasic(...)`.

### 10.1. Why Are Direct Call Tests Valuable?

`directSpringBeanCallIsProtectedByMethodProxy` does not call any controller. It injects the `ReportService` bean and calls the method through the proxy; if `@EnableMethodSecurity` were omitted or the meta-annotation went undiscovered, calling `reports.read("r202")` would return data instead of throwing `AccessDeniedException` and the test would fail.

Combining HTTP tests and service tests helps distinguish layers: the HTTP layer stops anonymous requests, while method security enforces fine-grained owner and admin rules.

### 10.2. Why Is Testing Only One User Insufficient?

Testing only that admin can read reports does not prove anti-BOLA/IDOR protection. A validly authenticated user like `lan` must have tests proving **reading someone else's resource** is denied. Conversely, testing only denials without testing allowed owners risks a broken SpEL expression accidentally denying everyone.

### 10.3. What Happens When the Permission Bean Returns False?

`@PreAuthorize` is evaluated before the service body. When false, the Spring Security method interceptor denies the call and typically throws `AccessDeniedException`. On an HTTP request, `ExceptionTranslationFilter` translates the exception according to the entry point/handler. With authenticated HTTP Basic lacking permission, the response is typically **403 Forbidden** in the sample.

Do not assume every false result always yields 403: anonymous callers typically receive a 401 Basic challenge, form login may 302 redirect, and custom handlers may produce other responses.

### 10.4. Check CSRF Independently

The demo only has GET endpoints. If you add `POST /reports/{id}/approve`, analyze CSRF based on credentials and client type, and check role/owner/action and transactions. Never blindly add global `.csrf(csrf -> csrf.disable())` just to make tests pass easily.

## 11. Running the Program and Expected Results

In the `method-meta-authorization` directory, with JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

If dependencies and environment match, **15 tests are expected to pass**. This is a static evaluation of the source, not a report of Maven execution output.

Test HTTP Basic **only with demo accounts on localhost**:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/reports/r101
curl -i -u lan:lan-demo http://localhost:8080/reports/r101
curl -i -u lan:lan-demo http://localhost:8080/reports/r202
curl -i -u minh:minh-demo http://localhost:8080/reports/r202
curl -i -u admin:admin-demo http://localhost:8080/admin/summary
curl -i -u lan:lan-demo http://localhost:8080/audit/summary
curl -i -u admin:admin-demo http://localhost:8080/audit/summary
```

**Never** use unencrypted HTTP for real credentials. `curl -u` can expose passwords in command history or process listings. Use HTTPS, secret management, and appropriate client auth in production.

| Scenario | Expected Result | Why |
| --- | --- | --- |
| Anonymous `GET /public` | 200 `public` | HTTP permitAll |
| Anonymous `GET /reports/r101` | 401 + Basic challenge | Unauthenticated at HTTP layer |
| Lan reads `r101` | 200 `report:r101` | Real owner per server store |
| Lan reads `r202` | 403 | Not owner and lacks ROLE_ADMIN |
| Minh reads `r202` | 200 `report:r202` | Owner |
| Admin reads existing report | 200 | Admin granted under demo policy |
| Admin reads report missing from store | 403 | Explicit deny, never allows missing |
| Lan accesses `/admin/summary` | 403 | Lacks ROLE_ADMIN |
| Admin accesses `/admin/summary` | 200 `admin:summary` | @RequiresAdmin |
| Lan accesses `/audit/summary` | 403 | Insufficient role/full auth |
| Admin accesses `/audit/summary` | 200 `audit:summary` | @RequiresAdminFull |
| Basic wrong password | 401 | Authentication fails before policy service runs |

In applications using form login instead of Basic, anonymous access may redirect to `/login` instead of HTTP 401. That does not change the meaning of meta-annotations on services.

## 12. Standalone Java 17: Observing Composed Annotations via Reflection

Spring Security has its own meta-annotation discovery mechanism, yet first you can use Java Reflection to see **annotations placed on other annotations**. This program does **not** run Spring, has no authentication, and does not evaluate SpEL. It merely reads runtime metadata.

Create `MetaAnnotationReflectionDemo.java`:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public class MetaAnnotationReflectionDemo {

    @Target(ElementType.ANNOTATION_TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Rule {
        String value();
    }

    @Target(ElementType.METHOD)
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @Rule("ADMIN")
    @interface RequiresAdmin {
    }

    static class Service {

        @RequiresAdmin
        public String adminSummary() {
            return "admin:summary";
        }
    }

    public static void main(String[] args) throws Exception {
        Method method = Service.class.getMethod("adminSummary");

        RequiresAdmin composed = method.getAnnotation(
            RequiresAdmin.class
        );
        System.out.println("method has RequiresAdmin: " +
            (composed != null));

        Rule meta = RequiresAdmin.class.getAnnotation(Rule.class);
        System.out.println("meta rule: " + meta.value());

        // This is reading metadata, not making an authorization decision.
        System.out.println("result: " +
            new Service().adminSummary());
    }
}
```

Compile and run with Java 17:

```bash
javac MetaAnnotationReflectionDemo.java
java MetaAnnotationReflectionDemo
```

**Exact** stdout:

```text
method has RequiresAdmin: true
meta rule: ADMIN
result: admin:summary
```

**Lesson:** reflection reads the composed annotation and meta-annotation `@Rule("ADMIN")`, yet `new Service().adminSummary()` still runs without logging in because the program has no Spring method-security interception. In a Spring Security application, `@EnableMethodSecurity` and calls through an appropriate Spring proxy are what enforce `@PreAuthorize`.

## 13. Reusable Annotations Do Not Solve Every Permission Automatically

An important architectural point: **reusing policy syntax** does not mean all resources share the same policy.

Examples:

- `@CanReadReport` checks report permission by owner or admin.
- `@CanReadAuditLog` may require an auditor role, access purpose, and retention policy.
- `@CanExportReport` may require full authentication, quotas, licenses, or consent.
- `@CanDeleteReport` may require an approver and verifying the report state is unlocked.

Using one shared annotation because all four relate to reports can make permissions too broad or too narrow. Give **each annotation a consistent business contract** and version/test it when changing.

### 13.1. Policy Changes Affect Multiple Call Sites

Changing `@CanReadReport` from owner-only to owner OR admin changes behavior across every service method using it. That is both the strength **and** risk of reuse: a small change can widen permissions across many endpoints.

Code reviews must inspect annotation usages, evaluate the threat model, and run corresponding integration/regression tests. Never assume "editing one file" means a small blast radius.

### 13.2. HTTP and Service Policies Can Accumulate

Suppose an HTTP rule requires `ROLE_READER` for `GET /reports/**` while `@CanReadReport` allows owner OR admin. If admin lacks `ROLE_READER`, they are blocked at the HTTP layer before the method runs. That may be the intended policy or an unintended misconfiguration.

Because check layers can **stack**, test the combined end-to-end behavior. Do not assume a manager/annotation "is broken" just because the request did not pass earlier HTTP authorization.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Forgetting `@EnableMethodSecurity` | Meta-annotations may not execute | Enable method security and test direct bean calls |
| Using only `@Retention(SOURCE)` | Framework lacks runtime metadata | Use `RetentionPolicy.RUNTIME` |
| Using `@Target(TYPE)` when annotation belongs on one method | Protection scope mismatches contract | Use METHOD-only or design explicit class-level scope |
| Composed annotation lacks `@PreAuthorize`/meta policy | Decorative metadata only | Declare the proper meta-annotation |
| Defining `@RequiresRole(role="ADMIN")` expecting `{role}` auto-substitution | Literal/template may not be processed | Use fixed rules or enable version-supported templating with tests |
| Putting two `@PreAuthorize`/meta rules on one method expecting auto-AND | Ambiguous or unexpected behavior | Single AND expression or composite policy manager |
| Putting annotation on private/final methods without proxy tests | Interception may not happen | Public/proxy-compatible service boundary |
| Calling `this.securedMethod()` in the same bean | Bypasses proxy in standard mode | Extract bean or design proper interception |
| Instantiating service via `new` outside Spring | No method-security proxy | Inject Spring bean |
| Wrong variable name `#reportId` | Expression cannot find argument | `@P("reportId")` or proper build metadata |
| Calling unregistered `@reportPermission` bean | Evaluation fails to run as expected | Define bean and test SpEL |
| Permission bean returns true on null/missing ID | Grants unauthorized access, BOLA | Fail closed, test missing IDs |
| Reading owner from client-sent request query | Client forges owner | Compare against server-side resource store |
| Using only hasRole for all reports | User with role reads other users' reports | Combine owner/tenant |
| Using `fullyAuthenticated` and assuming MFA ran | No proof of recent MFA | Add recent auth/MFA policy |
| Using `@PostAuthorize` on DB-writing methods | Denial arrives after side effects | Use pre-checks and domain transaction checks |
| Forgetting to protect scheduled/background callers | No HTTP security context | Design suitable service identity & policy |
| Missing non-owner tests | Misses IDOR/BOLA bugs | Test owner, non-owner, admin, unknown |
| Assuming 403 always comes from SpEL | CSRF/HTTP rules can also block | Inspect filter chain/exceptions |
| Testing with `@WithMockUser` and claiming Basic passwords work | Does not test Basic authentication | HTTP tests must send real Basic headers |
| Setting `anyRequest().authenticated()` and forgetting new annotation | New endpoint may be overly broad | Audit coverage, use deny fallback where suitable |
| Logging annotations containing sensitive tenant data | Operational data leak | Log minimal decisions, never secrets |
| Repeating SpEL expressions across dozens of services | Policy drift | Named meta-annotations with tests |
| Upgrading from 6.3 to another version without testing | Templating/API behavior changes | Check version docs and integration tests |

## 15. Debugging When Composed Annotations Fail to Block Requests

If an unauthorized user can still invoke a service method:

1. **Is the bean Spring-managed?** Does it have `@Service`, `@Component`, or proper bean registration?
2. **Was `@EnableMethodSecurity` scanned?** Confirm the configuration is active.
3. **Did the call pass through a proxy?** Did the controller inject the service or use `new`? Any `this.method()` self-invocation?
4. **Can the method be intercepted?** Check visibility, `final`, proxy type, and interfaces.
5. **Does the annotation have Runtime retention?** Are `@Retention(RUNTIME)` and `@Target(METHOD)` correct?
6. **Does the meta-annotation carry a valid `@PreAuthorize`?** Was it placed elsewhere by mistake?
7. **Are there duplicate or conflicting annotations?** Do method, class, and interface have conflicting rules?
8. **Does SpEL find the bean?** Are `@reportPermission`, `canRead`, and its return type right?
9. **Does `#reportId` have a value?** Test `@P("reportId")` and compile metadata.
10. **What are principal/authorities in SecurityContext?** Any anonymous/remember-me? Right role prefix?
11. **Did the request pass the HTTP layer?** If blocked at a filter, the service never ran; 401/403 may originate elsewhere.
12. **Was the service called directly from a background job?** Is that SecurityContext trustworthy?
13. **Does the policy get owner from a server store?** Never use query params to decide owner.
14. **Spring Security version?** Verify support for composed annotations and expression templating.
15. **Were there side effects before the check?** `@PostAuthorize` or self-invocation may fail to protect at the right moment.

Use logging in development when needed:

```properties
logging.level.org.springframework.security=DEBUG
```

Never log passwords, cookies, session IDs, bearer tokens, or private report contents. Use unit tests for permission beans and integration tests through Spring proxies/MockMvc to trace where denials originate.

## 16. Security, Performance, and Multi-Tenancy

### 16.1. Avoid Privilege Escalation When Modifying Annotations

A name like `@CanReadReport` may be used widely across modules. Changing its policy from owner-only to owner OR admin could accidentally let a global admin view another tenant's resources. Enforce explicit tenant boundaries, such as same-tenant owner or tenant-scoped admin, and write cross-tenant tests.

### 16.2. Limit Expensive Policy Queries

A `@PreAuthorize` calling a permission bean can trigger a DB lookup on every service call. Measure cost, avoid N+1, cache with proper keys (principal/tenant/action/resource), and synchronize revocations. Never cache by report ID alone and reuse a `true` result for another user.

### 16.3. TOCTOU and Transactions

A pre-method policy may check the owner at T1 while the report changes owner before the DB update at T2. For sensitive operations, services must verify permissions near data usage using owner/tenant-scoped queries, transactions/versions, or database row-level controls.

A `@PreAuthorize` meta-annotation does not guarantee transactional consistency across all business steps.

### 16.4. Never Use Annotations as the Sole Audit Proof

A method carrying `@RequiresAdmin` does not prove every call was intercepted, especially when self-invocation or non-proxied code exists. Auditing should observe runtime decisions and entry points, backed by tests covering critical paths.

### 16.5. Defense in Depth

- The HTTP layer blocks unnecessary requests.
- Method security protects service boundaries.
- Domain services check owner, tenant, and action.
- DB queries/transactions enforce control at operation time.
- CSRF, TLS, safe logging, and secret management protect the remaining layers.

Layers must **reinforce** one another rather than conflict or leave every `ROLE_USER` able to access everyone else's resources.

## 17. Self-Check Exercises and Answers

**Question 1.** Why create `@RequiresAdmin` instead of repeating `@PreAuthorize("hasRole('ADMIN')")` across many methods?

**Answer:** To reuse a named policy, reduce policy drift, and centralize edits/reviews; call sites still need tests because changes impact multiple methods.

**Question 2.** Do composed annotations require `RetentionPolicy.RUNTIME`?

**Answer:** Yes for runtime annotation inspection as in this example; metadata must be present when Spring Security evaluates it.

**Question 3.** What happens if you define `@RequiresAdmin` yet forget `@EnableMethodSecurity`?

**Answer:** There is a risk that no method-security interceptor enforces `@PreAuthorize`. Direct tests on the injected service bean will catch it.

**Question 4.** `ReportService` calls `this.read("r202")` from another method in the same bean; is `@CanReadReport` guaranteed to run?

**Answer:** No under typical proxy-based interception; self-invocation can bypass the proxy. Extract the protected method into another bean or redesign.

**Question 5.** Why place `@P("reportId")` on the method argument?

**Answer:** So SpEL expression `#reportId` has an explicit parameter name without relying entirely on compiler metadata.

**Question 6.** A `GET /reports/r202` request is made by `lan` with valid Basic credentials. Why might it receive 403?

**Answer:** The HTTP layer authenticates successfully, then method policy `@CanReadReport` checks ownership and sees `r202` belongs to Minh while `lan` lacks ROLE_ADMIN, so it denies.

**Question 7.** A user has ROLE_ADMIN and a remember-me Authentication; does `@RequiresAdminFull` pass?

**Answer:** No, per `hasRole('ADMIN') and isFullyAuthenticated()`, because remember-me is not fully authenticated. Since the HTTP Basic sample does not enable remember-me, test that token type separately if implemented.

**Question 8.** Can you write `@RequiresRole(role="MANAGER")` and `@PreAuthorize("hasRole('{role}')")` expecting placeholder substitution in every version?

**Answer:** No. Annotation attribute templates depend on version support/configuration. The 6.3.x sample uses fixed rules or custom policies rather than assuming interpolation.

**Question 9.** Do two `@PreAuthorize` annotations or two composed annotations containing `@PreAuthorize` on one method automatically AND together?

**Answer:** Do not assume so; ambiguity can occur. To AND conditions, use one explicit expression or a composite policy manager.

**Question 10.** Is `@PostAuthorize` suitable as the sole protection for a `transferMoney` method?

**Answer:** No. Post-checks run **after** money may have been transferred; use pre-checks and proper transaction/domain authorization.

**Question 11.** Why are both the test allowing `lan` to read `r101` and the test denying `r202` important together?

**Answer:** The allowed case proves the rule does not block everything; the authenticated-non-owner denial catches IDOR/BOLA bugs.

**Question 12.** In a test using `@WithMockUser` calling a bean directly, can you claim HTTP Basic passwords were verified?

**Answer:** No. `@WithMockUser` constructs a synthetic SecurityContext. Basic tests must send real headers via MockMvc or an HTTP client.

**Question 13.** With `@CanReadReport` on the service, are message consumers calling `new ReportService()` protected?

**Answer:** Not automatically. Objects not created/proxied by Spring do not pass through method security. Design entry points and dependency injection properly.

**Question 14.** Should tenant A's admin automatically read all of tenant B's reports when using `@CanReadReport`?

**Answer:** Not unless cross-tenant access is intended by policy. Use owner/tenant data sources and explicit rules rather than unconditional global roles.

## 18. Pre-Deployment Checklist

**Annotation Design:**

- Does the annotation name clearly describe the action and resource?
- Is the policy fixed or does it need method parameters?
- Are `@Target` and `@Retention(RUNTIME)` set properly?
- Does each annotation carry one clear `@PreAuthorize` rule or security mechanism?
- Have multiple conflicting `@PreAuthorize` rules on one method been avoided?
- Is there Javadoc documenting `#reportId` contract, roles/tenancy, and denial behavior?

**Framework Setup:**

- Is `@EnableMethodSecurity` enabled in the right Spring context?
- Are service methods public, non-final, and called through Spring proxies?
- Are there any self-invocation bypasses along sensitive call paths?
- Does the `@reportPermission` SpEL bean exist?
- Are arguments exported accurately via `@P` or compiler metadata?
- Do HTTP filter policies avoid leaving routes without method annotations exposed?

**Testing:**

- Are authenticated owner, non-owner, admin, and non-existent report tested?
- Does the same annotation work across different beans?
- Are service beans tested directly outside HTTP?
- Are 200/401/403 tested per entry point?
- Is Basic/authentication tested separately rather than inferred from `@WithMockUser`?
- Are policy changes tested not to impact unintended routes?
- Are CSRF and HTTP methods tested when adding mutations?

**Production:**

- Owner/tenant data comes from trusted sources.
- No hardcoded passwords, signing keys, or tokens.
- Authorization DB/cache enforces performance bounds and revocation.
- Step-up/MFA controls exist for sensitive operations if required.
- Safe logging/auditing without recording secrets.
- Review all usages before changing shared annotation contents.

## 19. Key Takeaways

- A **composed annotation** is a Java annotation carrying a meta-annotation like `@PreAuthorize` to **reuse a named authorization policy**.
- Enable **`@EnableMethodSecurity`**, place annotations on **Spring-managed public service methods**, and ensure calls go **through proxies**.
- `@Target(METHOD)`, `@Retention(RUNTIME)`, and `@Documented` define and expose annotations consistently.
- For expressions needing method arguments, use `@P("reportId")` or compatible parameter-name metadata so `#reportId` resolves accurately.
- `@PreAuthorize("@reportPermission.canRead(authentication, #reportId)")` delegates ownership decisions to a Java bean, **never** trusting client-declared data.
- To combine role **AND** full authentication, write **one** policy such as `hasRole('ADMIN') and isFullyAuthenticated()`; never stack multiple `@PreAuthorize` annotations expecting implicit combination.
- **Self-invocation**, private/final methods, `new`-instantiated objects, and custom proxies are key boundaries where annotations may fail to execute.
- Test both **HTTP requests** (MockMvc/Basic) and **direct Spring bean calls** (@WithMockUser), including non-owner cases to prevent BOLA/IDOR bugs.
- Policy reuse reduces duplication, yet any change to a shared annotation impacts multiple methods; maintain owner/tenant checks, regression tests, and defense in depth.
