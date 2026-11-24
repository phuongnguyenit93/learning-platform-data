# @WithSecurityContext for Building Custom Test Identities in Spring Security Servlet

## 1. Why Is @WithMockUser Not Always Enough?

When testing Spring Security, we often want to invoke a `@PreAuthorize` method or send a `MockMvc` request as a logged-in user. `@WithMockUser` is very convenient:

~~~java
@Test
@WithMockUser(username = "alice", roles = "READER")
void readerCanRead() {
    // Test logic protected by hasRole("READER").
}
~~~

However, in real-world applications, a principal may carry more than just a username:

- **Local account ID**: `user-100`, stable even if username/email changes.
- **Tenant / workspace ID**: `tenant-a`, needed to prevent cross-tenant data reads.
- **Roles and permissions**: `ROLE_READER`, `ROLE_MANAGER`, `PROJECT_EXPORT`.
- **Business state and context**: information attached to the session/identity after authentication.
- **Custom principal class**: for example `TenantPrincipal` used by the application in `@PreAuthorize`, services, or `@AuthenticationPrincipal`.

By default, `@WithMockUser` creates a principal of type `org.springframework.security.core.userdetails.User`. If the application's policy requires a custom principal with `tenantId`, username and roles alone are not enough. Casting the principal blindly can trigger `ClassCastException`; or a properly written policy will deny access because the principal lacks the required data.

`@WithSecurityContext` from **spring-security-test** lets us declare a **test-only** annotation and a `WithSecurityContextFactory` to construct the exact `SecurityContext`, `Authentication`, principal, and authorities needed for the test scenario.

Goals of this article: create `@WithMockTenantUser`, test a `@PreAuthorize` service directly and test with `MockMvc`; understand how the listener attaches/cleans up the context, context creation timing, boundaries of simulated tests, and common security mistakes.

**Scope:** Spring Security 6, Spring Boot 3.3.5, Java 17, **Servlet**, and JUnit 5. This is a **test fixture** mechanism, not a production authentication provider.

## 2. Properly Separating Three Things: SecurityContext, Authentication, and Principal

Spring Security distinguishes:

| Component | Role | Common API |
| --- | --- | --- |
| `SecurityContextHolder` | Supplies the context for the current thread/strategy | `SecurityContextHolder.getContext()` |
| `SecurityContext` | Holds the security context's `Authentication` | `getAuthentication()`, `setAuthentication()` |
| `Authentication` | Represents identity, authenticated status, authorities, and credentials | `getPrincipal()`, `getAuthorities()`, `isAuthenticated()` |
| Principal | Application-specific authenticated user model | `getName()`, `tenantId()`, `accountId()` |
| `GrantedAuthority` | Permissions used by Spring Security for `hasRole`, `hasAuthority` | `getAuthority()` |

In a real application, authentication filters and `AuthenticationManager` construct `Authentication` after verifying a password, session, or token. With `@WithSecurityContext` tests, we **pre-populate a trusted `Authentication` within test scope**, skipping credential verification to focus solely on authorization/business behavior.

Testing flow:

~~~text
JUnit 5 + Spring TestContext
        |
        v
WithSecurityContextTestExecutionListener
        |
        v
Detects @WithMockTenantUser on method/class
        |
        v
WithMockTenantUserFactory.createSecurityContext(annotation)
        |
        +--> Creates TenantPrincipal(username, accountId, tenantId)
        +--> Creates ROLE_READER or matching authorities
        +--> Creates authenticated Authentication
        +--> Places Authentication into empty SecurityContext
        |
        v
SecurityContextHolder for current test thread
        |
        +--> Direct call to service proxy with @PreAuthorize
        |
        +--> MockMvc integrated with Spring Security filter chain
        |
        v
Spring Test listener cleans up context after test
~~~

**Do not call `SecurityContextHolder.setContext(...)` inside the factory unless necessary**: the factory contract is to **return** a new `SecurityContext`; the test listener handles installing and cleaning it up. This reduces the risk of context leaking into another test.

The test annotation does not materialize a valid JWT, does not run OAuth2 authorization code exchange, does not verify passwords, and does not open a production session. It only sets up **controlled input conditions** to check policies.

## 3. How Do @WithSecurityContext and the Factory Work?

APIs from the test dependency:

~~~java
import org.springframework.security.test.context.support.WithSecurityContext;
import org.springframework.security.test.context.support.WithSecurityContextFactory;
import org.springframework.security.test.context.support.TestExecutionEvent;
~~~

You can create an annotation meta-annotated with `@WithSecurityContext`:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = MyFactory.class)
public @interface WithMyIdentity {
    String userId() default "user-100";
}
~~~

This is only a **syntax illustration snippet**, since `MyFactory` and imports are not declared yet. The complete example in section 7 is named `WithMockTenantUser`.

`WithSecurityContextFactory<A>` has one core method:

~~~java
SecurityContext createSecurityContext(A annotation);
~~~

The factory receives **the annotation instance on the running test**. From the annotation's attributes, the factory can:

1. Validate fixture values.
2. Construct the principal and `GrantedAuthority` collection expected by the application.
3. Create a new `SecurityContext`.
4. Assign an authenticated `Authentication`.
5. Return the context to `Spring Security TestExecutionListener`.

Example creating authentication using the three-argument constructor:

~~~java
Authentication authentication =
        new UsernamePasswordAuthenticationToken(
                principal,
                "N/A",
                authorities);

SecurityContext context =
        SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
return context;
~~~

`UsernamePasswordAuthenticationToken` with the **three-argument** constructor creates an authentication marked as authenticated, because the caller in the **test** already determined the principal and permissions. The two-argument constructor `(principal, credentials)` creates an **unauthenticated** token used for initial authentication request flows. The two constructors do not carry the same semantics.

The `"N/A"` string is only a test placeholder, **not a real password**. Never put production credentials into fixtures or logs. If the application uses a custom `Authentication` (e.g., a domain-specific class carrying claims), the factory can construct that exact type instead of `UsernamePasswordAuthenticationToken`; however, it must preserve the `getPrincipal`, `getAuthorities`, and `isAuthenticated` contracts relied upon by method security.

## 4. When to Choose @WithSecurityContext Over Built-In Tools?

| Testing Approach | Identity Created | When to Use |
| --- | --- | --- |
| `@WithMockUser` | Default `UserDetails` and test-specified roles/authorities | Policy depends only on standard username, roles, authorities |
| `@WithUserDetails` | Loads `UserDetails` via `UserDetailsService` from application context | Need the principal returned by `UserDetailsService` and fixture data from the service |
| `@WithSecurityContext` | **Any `SecurityContext`/`Authentication`/principal** built by a factory | Custom principals, tenants, account IDs, permission claims, composite identities, reusable variants |
| `mockMvc.perform(...with(user(...)))` | Principal applied to **a single request** | Need different identity variants within the same test/request |
| `mockMvc.perform(...with(authentication(...)))` | `Authentication` applied to a specific request | Need request-level testing with custom authentication |
| Full authentication integration test | Real login / full IdP simulation, tokens/credentials processed | Password verification, JWT validation, sessions, OAuth2/OIDC callbacks, failure paths |

`@WithSecurityContext` keeps tests short, readable, and **free of repeated context-building code in every method**. However, it is unsuitable when the test's primary goal is proving a login provider authenticates properly: for that, use authentication integration tests.

Important distinction: `@WithUserDetails` depends on a `UserDetailsService` bean and existing user data; `@WithSecurityContext` can construct test principals purely **from the annotation**, without connecting to a database or external directory.

For **`@PreAuthorize`**, test the Spring-proxied method directly. With **MockMvc**, verify request responses/statuses through the security chain and MVC. Both test levels complement each other.

## 5. Designing Fixtures: Describe Only What Needs Testing

Suppose a `ProjectService` allows reading a project if:

- The user is authenticated.
- Has authority `ROLE_READER`.
- `tenantId` in the principal matches the requested project's `tenantId`.

A custom test principal will have three fields:

~~~java
public record TenantPrincipal(
        String username,
        String accountId,
        String tenantId
) implements Principal, Serializable {
    @Override
    public String getName() {
        return username;
    }
}
~~~

This is a **code snippet**; in section 7 this record will live inside a complete application class with required imports and beans.

Because Spring Security interprets `hasRole('READER')` as matching authority **`ROLE_READER`**, the annotation lets you declare `roles = {"READER"}` and the factory adds the `ROLE_` prefix automatically. Do not pass `"ROLE_READER"` into an API that already prepends the prefix.

A well-designed annotation should have:

- Sensible default values for common tests.
- Separate `username`, `accountId`, and `tenantId`, never treating email as a local ID.
- `roles` supporting an empty array to test failure paths.
- A factory granting only the permissions explicitly listed in the fixture.
- Validation of annotation inputs so test errors surface **early** if a tenant or role is mistyped.

Avoid creating annotations with dozens of unrelated attributes, and avoid calling servers or DBs inside the factory when plain data suffices. For complex policies, domain-oriented fixtures (`@WithMockTenantUser`, `@WithMockServiceAccount`) are usually clearer than one mega-generic annotation.

## 6. Maven Demo Structure: Java 17 + Spring Boot 3.3.5

We will build a Spring MVC app with a GET endpoint to read a project and a POST endpoint illustrating CSRF. `ProjectService` is protected by method security:

~~~java
@PreAuthorize(
    "hasRole('READER') and " +
    "@tenantAccess.sameTenant(authentication, #p0)")
~~~

`#p0` is the first method parameter, independent of whether Java parameter names are preserved via `-parameters`. `@tenantAccess` references a Spring bean named `tenantAccess`, not a Java variable in the controller.

Layout:

~~~text
tenant-security-test-demo/
├── pom.xml
├── src/main/java/example/securitytest/SecurityTestApplication.java
├── src/test/java/example/securitytest/WithMockTenantUser.java
├── src/test/java/example/securitytest/WithMockTenantUserFactory.java
└── src/test/java/example/securitytest/TenantSecurityTests.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>tenant-security-test-demo</artifactId>
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
~~~

Notice `spring-security-test` has **`scope=test`**. Keep custom annotations and factories in `src/test/java` so they **never** become authentication components of the production system.

## 7. Complete Code Example: Application and Custom Mock Identity

### 7.1. Protected Application

**src/main/java/example/securitytest/SecurityTestApplication.java**:

~~~java
package example.securitytest;

import java.io.Serializable;
import java.security.Principal;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityTestApplication.class, args);
    }

    @Bean
    UserDetailsService userDetailsService() {
        // Local demo data for HTTP Basic. Do not use {noop} in production.
        return new InMemoryUserDetailsManager(
                User.withUsername("demo")
                        .password("{noop}demo-pass")
                        .roles("READER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/projects/**")
                        .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean("tenantAccess")
    TenantAccess tenantAccess() {
        return new TenantAccess();
    }

    @Bean
    ProjectService projectService() {
        return new ProjectService();
    }

    // Domain principal that the real application can put into Authentication.
    public record TenantPrincipal(
            String username,
            String accountId,
            String tenantId
    ) implements Principal, Serializable {
        @Override
        public String getName() {
            return username;
        }
    }

    public record Project(String tenantId, String title) {}

    public static class TenantAccess {

        public boolean sameTenant(
                Authentication authentication, String tenantId) {
            return authentication != null
                    && authentication.isAuthenticated()
                    && authentication.getPrincipal()
                            instanceof TenantPrincipal principal
                    && principal.tenantId().equals(tenantId);
        }
    }

    public static class ProjectService {

        @PreAuthorize(
                "hasRole('READER') and " +
                "@tenantAccess.sameTenant(authentication, #p0)")
        public Project readProject(String tenantId) {
            return new Project(tenantId, "Internal project");
        }
    }

    @RestController
    public static class ProjectController {
        private final ProjectService service;

        public ProjectController(ProjectService service) {
            this.service = service;
        }

        @GetMapping("/api/projects/{tenantId}")
        public Project getProject(@PathVariable String tenantId) {
            return service.readProject(tenantId);
        }

        @PostMapping("/api/projects/{tenantId}/confirm")
        public ResponseEntity<Void> confirmProject(
                @PathVariable String tenantId) {
            // Illustrates POST subject to CSRF and the same service policy.
            service.readProject(tenantId);
            return ResponseEntity.noContent().build();
        }
    }
}
~~~

**Important protection conditions:**

1. `@EnableMethodSecurity` enables `@PreAuthorize` on Spring-managed services; never omit this annotation and assume `@PreAuthorize` runs on its own.
2. `ProjectService` is a Spring-managed bean invoked via the controller or injected into tests. Calling `new ProjectService()` outside Spring or calling `this.readProject(...)` from another method on the same instance can bypass the AOP proxy and **not** enforce method security.
3. The URL rule requires `authenticated()`, while the method rule requires **role + tenant**. HTTP Basic user `demo` has role `READER`, yet its principal is the default `UserDetails`, **not** `TenantPrincipal`: the policy intentionally denies access because the tenant context is missing.
4. `TenantAccess.sameTenant` uses `instanceof TenantPrincipal` to fail closed. **Never cast blindly** or skip the tenant check just because the request is authenticated.
5. `#p0` ensures the expression references the `tenantId` passed to the service, even when parameter name metadata is stripped. `@PreAuthorize` expressions must be tested with negative permission/tenant cases, not just the happy path.
6. POST in this example has an `authenticated()` URL yet is still guarded by **`CsrfFilter`** by default because it is an unsafe HTTP method. Creating a principal via `@WithSecurityContext` **does not** automatically attach a valid CSRF token to a `MockMvc` request.
7. `{noop}` is only for the HTTP Basic fixture and is unsuitable for storing production passwords. Real local identity sources must pass through an authentication provider, never trusting a `tenantId` supplied by the client in a form or header.

### 7.2. Custom Annotation @WithMockTenantUser

**src/test/java/example/securitytest/WithMockTenantUser.java**:

~~~java
package example.securitytest;

import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@Inherited
@WithSecurityContext(
        factory = WithMockTenantUserFactory.class,
        setupBefore = TestExecutionEvent.TEST_METHOD
)
public @interface WithMockTenantUser {

    String username() default "alice";

    String accountId() default "user-100";

    String tenantId() default "tenant-a";

    String[] roles() default {"READER"};
}
~~~

`@Retention(RUNTIME)` allows the test listener to read the annotation via reflection. `@Target(METHOD, TYPE)` allows use on test methods or entire test classes. `@Inherited` supports certain class-level inheritance cases; it **does not** make every annotation on interfaces or superclass methods automatically inherited under all Java rules.

`setupBefore = TEST_METHOD` is the default timing: `Spring Security TestExecutionListener` prepares the context **before** JUnit 5 `@BeforeEach` callbacks. If you want the context created after `@BeforeEach`, consider `TestExecutionEvent.TEST_EXECUTION` (section 10). Choose based on the test's purpose.

In the example we declare roles without the `ROLE_` prefix. The factory constructs `SimpleGrantedAuthority("ROLE_" + role)`. If tests need non-role permissions, add a separate `authorities()` attribute and map it verbatim; **do not** silently alter the semantics of `roles`.

### 7.3. WithSecurityContextFactory Creating Principal and Authentication

**src/test/java/example/securitytest/WithMockTenantUserFactory.java**:

~~~java
package example.securitytest;

import java.util.Arrays;
import java.util.Collection;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public final class WithMockTenantUserFactory
        implements WithSecurityContextFactory<WithMockTenantUser> {

    @Override
    public SecurityContext createSecurityContext(
            WithMockTenantUser annotation) {

        if (annotation.username().isBlank()
                || annotation.accountId().isBlank()
                || annotation.tenantId().isBlank()) {
            throw new IllegalArgumentException(
                    "Mock identity fields must not be blank");
        }

        Collection<GrantedAuthority> authorities = Arrays.stream(
                annotation.roles())
                .map(role -> {
                    if (role == null || role.isBlank()
                            || role.startsWith("ROLE_")) {
                        throw new IllegalArgumentException(
                                "roles must be names without ROLE_ prefix");
                    }
                    return (GrantedAuthority)
                            new SimpleGrantedAuthority("ROLE_" + role);
                })
                .toList();

        var principal =
                new SecurityTestApplication.TenantPrincipal(
                        annotation.username(),
                        annotation.accountId(),
                        annotation.tenantId());

        var authentication = new UsernamePasswordAuthenticationToken(
                principal, "N/A", authorities);

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
~~~

Here `Collection<GrantedAuthority>` accepts the simulated set of permissions built from `roles`. `Arrays.stream(...).map(...).toList()` is Java 17-compatible syntax.

Key points to understand:

- `annotation.roles()` is each test's explicit input; it does not query production data or grant unintended permissions.
- `TenantPrincipal` uses **the exact model expected by application code**; `accountId` and `tenantId` are fixture data independent of `username`.
- `UsernamePasswordAuthenticationToken(principal, "N/A", authorities)` builds an authenticated token within test scope.
- `SecurityContextHolder.createEmptyContext()` creates a fresh context rather than reusing an old one. The factory **returns the context** without touching the global holder itself.
- `roles = {}` produces an empty authority set; the test must be denied by `hasRole("READER")`.
- The factory only validates fixture inputs and builds the context; it does not send HTTP requests, call password encoders, or create real cookies/sessions.

If the real project's principal uses a custom `Authentication` type (e.g., holding verified internal claims), replace the `UsernamePasswordAuthenticationToken` line with that exact class. Ensure `getAuthorities`, `isAuthenticated`, and `getPrincipal` still maintain consistent semantics.

**Never copy this annotation/factory into `src/main/java` to let production requests pick roles/tenants.** In tests, annotations are trusted because the test author controls them. At runtime, identity and roles must come from a validated authentication provider/identity service.

### 7.4. Testing with MockMvc and Method Security

**src/test/java/example/securitytest/TenantSecurityTests.java**:

~~~java
package example.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantSecurityTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    SecurityTestApplication.ProjectService projectService;

    @Test
    @WithMockTenantUser(
            username = "alice",
            accountId = "user-100",
            tenantId = "tenant-a",
            roles = {"READER"})
    void matchingTenantAndRoleCanRead() throws Exception {
        mvc.perform(get("/api/projects/tenant-a"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenantId").value("tenant-a"))
                .andExpect(jsonPath("$.title").value("Internal project"));
    }

    @Test
    @WithMockTenantUser(tenantId = "tenant-a")
    void otherTenantIsForbiddenEvenWithReaderRole()
            throws Exception {
        mvc.perform(get("/api/projects/tenant-b"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockTenantUser(tenantId = "tenant-a", roles = {})
    void missingRoleIsForbiddenEvenWithMatchingTenant()
            throws Exception {
        mvc.perform(get("/api/projects/tenant-a"))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousRequestRequiresAuthentication()
            throws Exception {
        mvc.perform(get("/api/projects/tenant-a"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void defaultMockUserCannotPretendToHaveTenantContext()
            throws Exception {
        mvc.perform(get("/api/projects/tenant-a"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockTenantUser(tenantId = "tenant-a", roles = {"READER"})
    void serviceProxyEnforcesTenantWithoutHttp() {
        var allowed = projectService.readProject("tenant-a");
        assertThat(allowed.tenantId()).isEqualTo("tenant-a");

        assertThatThrownBy(
                () -> projectService.readProject("tenant-b"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockTenantUser(tenantId = "tenant-a")
    void postRequiresCsrfIndependentlyOfMockIdentity()
            throws Exception {
        mvc.perform(post("/api/projects/tenant-a/confirm"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/api/projects/tenant-a/confirm")
                        .with(csrf()))
                .andExpect(status().isNoContent());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Expected outcomes** when using the exact example structure:

| Test | Goal | Expected Outcome |
| --- | --- | --- |
| `matchingTenantAndRoleCanRead` | Custom principal with matching tenant and role | HTTP 200, valid JSON |
| `otherTenantIsForbiddenEvenWithReaderRole` | Right role but different tenant | HTTP 403 |
| `missingRoleIsForbiddenEvenWithMatchingTenant` | Right tenant but missing `ROLE_READER` | HTTP 403 |
| `anonymousRequestRequiresAuthentication` | No principal | HTTP 401 from HTTP Basic |
| `defaultMockUserCannotPretendToHaveTenantContext` | Default principal lacks tenant | HTTP 403 |
| `serviceProxyEnforcesTenantWithoutHttp` | Method security runs when calling Spring bean | Valid result; calling another tenant throws `AccessDeniedException` |
| `postRequiresCsrfIndependentlyOfMockIdentity` | Authenticated does not exempt CSRF | POST without CSRF gets 403; with CSRF gets 204 |

These tests prove that **the principal and permissions in context affect authorization**. They **do not prove** HTTP Basic passwords are actually verified in the annotation scenarios, because `@WithMockTenantUser` bypasses the authentication entry point. Add real-login integration tests when testing passwords, JWTs, OAuth2/OIDC, or sessions.

## 8. Test Listener Mechanism, SpringExtension, and Context Creation Timing

`@WithSecurityContext` works only when the test environment supports Spring TestContext and `Spring Security TestExecutionListener`. With `@SpringBootTest`, Spring Boot integrates JUnit 5/`SpringExtension` and the appropriate listener. In a plain unit test with `new ProjectService()` and no Spring context, do not expect method security or `@WithSecurityContext` to work automatically.

### 8.1. TEST_METHOD and TEST_EXECUTION

Spring Security supports `TestExecutionEvent` for `@WithSecurityContext`:

| Value | When SecurityContext Is Set | When Helpful |
| --- | --- | --- |
| `TEST_METHOD` (default) | Before test-method preparation, including JUnit `@BeforeEach` | Want `@BeforeEach` to access authentication |
| `TEST_EXECUTION` | Right before running the `@Test` body, **after** `@BeforeEach` | Want `@BeforeEach` setup unaffected by mock identity |

To use `TEST_EXECUTION`, update the meta-annotation (illustrative snippet; do not modify the example file without deciding):

~~~java
@WithSecurityContext(
    factory = WithMockTenantUserFactory.class,
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
~~~

If a `@BeforeEach` calls a service requiring authentication, using `TEST_EXECUTION` can leave `@BeforeEach` without a principal. That is a timing error, not a `@PreAuthorize` bug.

### 8.2. Where Does the Context Live and When Is It Cleaned Up?

By default, `SecurityContextHolder` uses a strategy binding the context to the current thread. `Spring Security TestExecutionListener` installs the context for the test and cleans it up afterwards. You do not need to call `clearContext()` manually in every test when using the standard lifecycle.

However, `@Async`, manually spawned threads, scheduled jobs, or reactive boundaries **do not inherit the test thread's context by default**. If you need to test propagation, use Spring Security-supported propagation mechanisms (such as `DelegatingSecurityContextRunnable` or appropriate executor wrappers) and write dedicated tests. Do not enable `MODE_INHERITABLETHREADLOCAL` across the whole JVM just to make one test pass, as that risks leaking context between tasks.

**Parallel test execution:** using the default context limits cross-thread sharing, yet does not guarantee safety if other fixtures use mutable singleton state, static fields, user caches, or global session stores. Isolate test data, avoid mutable global `Authentication`, and use resource isolation when needed.

### 8.3. Class-Level vs. Method-Level Annotations

You can place a default identity on the test class:

~~~java
@WithMockTenantUser(
        username = "alice",
        tenantId = "tenant-a",
        roles = {"READER"})
class TenantPolicyTests {

    @Test
    void testWithDefaultIdentity() {
        // Uses identity from the class-level annotation.
    }

    @Test
    @WithMockTenantUser(
            username = "bob",
            tenantId = "tenant-b",
            roles = {"READER"})
    void testWithOtherIdentity() {
        // Method-level annotation customizes identity for this case.
    }
}
~~~

This is a **test-structure illustration snippet**, not a complete test class with assertions. Putting the annotation on the class reduces repetition, though important tests should explicitly state permissions and tenant so readers see **the security condition under test**.

## 9. Avoiding Bad Tests When Code Depends on a Custom Principal

### 9.1. Never Cast the Default Principal Directly

Dangerous code:

~~~java
TenantPrincipal principal =
        (TenantPrincipal) authentication.getPrincipal();
~~~

If a default `UserDetails` or anonymous `String` principal arrives, the cast throws `ClassCastException`, easily turning an access denial into an HTTP 500. Unless the application contract strictly guarantees the type, check the type first and deny safely:

~~~java
if (!(authentication.getPrincipal()
        instanceof TenantPrincipal principal)) {
    throw new AccessDeniedException("Unsupported principal");
}
~~~

In the section 7 example, `TenantAccess.sameTenant` checks `instanceof` and returns `false`, causing `@PreAuthorize` to deny instead of throwing a type error. A 403 result from a `@WithMockUser` test proves fail-closed behavior.

### 9.2. Never Grant More Permissions Than the Test Intends

With `@WithSecurityContext` tests, roles in the annotation are **input conditions**. If a factory always attaches `ROLE_ADMIN` for convenience, every low-privilege test becomes invalid as verification. Test all of:

- Principal with right type, right tenant, sufficient role.
- Principal with right type but wrong tenant.
- Principal with right tenant but missing role.
- Different principal type with a similar role.
- Anonymous.
- Multiple roles, authorities without `ROLE_` prefix, disabled accounts, or non-existent tenants where applicable to the domain.

Do not use one test method to prove multiple distinct security decisions without independent assertions. When role mappings change, negative tests catch **privilege escalation** bugs.

### 9.3. Never Confuse accountId with Username

In a real application, `accountId` is stable whereas username/email may change. If a resource's owner is an `accountId`, the policy should compare against `principal.accountId()`, not arbitrarily against `Authentication.getName()`. In multi-tenant systems, ownership typically involves **tenant ID + account ID + resource permissions**. Section 7 checks only tenant to isolate one policy aspect; real systems may also need to check document/project owner and visibility.

### 9.4. Never Test Unmanaged Objects Directly

A method with `@PreAuthorize` is only checked if the call goes through the appropriate method-security interceptor/proxy. Example:

~~~java
// WRONG when testing AOP method security:
ProjectService service = new ProjectService();
service.readProject("tenant-b");

// RIGHT: obtain bean from application context:
@Autowired ProjectService service;
~~~

If code calls `this.readProject()` internally on the same object, **self-invocation** occurs without passing through the proxy. Write realistic tests at boundaries where controllers/other beans call the Spring-managed service.

## 10. Differences Between Identity Tests, HTTP Tests, and Real Login Tests

The same endpoint can be tested at three levels:

### 10.1. Testing the Service Directly

~~~java
@Autowired
SecurityTestApplication.ProjectService projectService;

@Test
@WithMockTenantUser(tenantId = "tenant-a")
void denyOtherTenantAtMethodBoundary() {
    assertThatThrownBy(() ->
            projectService.readProject("tenant-b"))
        .isInstanceOf(AccessDeniedException.class);
}
~~~

This is an **illustrative snippet** similar to the complete test in section 7: the method-security proxy runs without HTTP, Servlet dispatcher, URL filters, or CSRF.

### 10.2. Testing the MVC Request

~~~java
@Test
@WithMockTenantUser(tenantId = "tenant-a")
void mvcDeniesOtherTenant() throws Exception {
    mvc.perform(get("/api/projects/tenant-b"))
        .andExpect(status().isForbidden());
}
~~~

`MockMvc` executes a request through the MVC/security filters configured in the test context and returns an HTTP response. It checks URL rules, controller routing, and method security together. When the Spring Security filter chain is not attached to `MockMvc`, assertions can mislead; with `@AutoConfigureMockMvc` + `spring-security-test` per the demo config, filters are integrated. If building `MockMvc` manually, apply the `springSecurity()` configurer.

### 10.3. Testing Real Authentication

To prove a wrong password yields 401 or a bad Bearer token signature is rejected, **never rely on `@WithSecurityContext`** to draw that conclusion. The fixture pre-builds `Authentication`, skipping credential verification. Use integration tests with an HTTP client, authentication provider, JWT decoder/test IdP, sessions/cookies, and proper failure paths.

A `MockMvc` test with `.with(httpBasic("demo", "demo-pass"))` sends real Basic credentials through the chain, unlike `@WithMockTenantUser`. In the demo, Basic user `demo` has role `READER` yet lacks the custom tenant principal, so **method security** denies it; that proves role alone does not satisfy the tenant policy.

### 10.4. Testing POST and CSRF

`@WithMockTenantUser` creates an authenticated identity without creating a CSRF token. When `CsrfFilter` is enabled, tests for state-changing requests must explicitly supply the token:

~~~java
mvc.perform(post("/api/projects/tenant-a/confirm")
            .with(csrf()))
    .andExpect(status().isNoContent());
~~~

Without `with(csrf())`, POST may be blocked with 403 **before** controller/method security runs. When debugging a 403 test failure, distinguish CSRF from role/tenant denial. Never disable CSRF application-wide just to test POST business authorization.

## 11. When You Need More Complex Factories: Dependency Injection and Custom Authentication

A factory might need to fetch a default tenant or user profile fixture from a bean. Spring Security Test supports interacting with the Spring test application context when building a security context factory; however, coupling factories to real repositories slows tests down, hurts repeatability, and easily masks failure branches. Use dependency injection in a factory only when it provides clear value.

Example **code snippet** for a custom principal with authorities separate from roles:

~~~java
Collection<GrantedAuthority> authorities = List.of(
    new SimpleGrantedAuthority("ROLE_READER"),
    new SimpleGrantedAuthority("PROJECT_EXPORT")
);

Authentication authentication =
    new UsernamePasswordAuthenticationToken(
        tenantPrincipal, "N/A", authorities);
~~~

In `@PreAuthorize` configuration:

~~~java
@PreAuthorize(
    "hasRole('READER') and hasAuthority('PROJECT_EXPORT')")
~~~

`hasRole` prepends the role prefix by default; `hasAuthority` matches the exact authority string. If the app uses complex permission objects, you can build an appropriate custom principal/authentication, while still never passing unverified mock JWTs into production handlers.

If you need to inspect `Authentication.getDetails()` or request metadata, the factory can construct authentication with matching details; remember to distinguish **client-provided request data** from **server-verified identity data**. Method-level authorization should never trust a `tenantId` from a request header without binding it to the verified identity.

When using OAuth2 Login or OIDC, test helpers like `oauth2Login()`/`oidcLogin()` are typically suitable for simulating OAuth2/OIDC principals. When the target is a principal **already converted by the app into a local identity with tenant/roles added**, `@WithSecurityContext` remains helpful. Still, it does not test calling the UserInfo endpoint or verifying real ID token signatures.

## 12. Common Errors and Troubleshooting

| Error | Symptom | Resolution |
| --- | --- | --- |
| Missing `spring-security-test` | `@WithSecurityContext` or `WithSecurityContextFactory` not found | Add test-scope dependency |
| Spring TestContext not running | Annotation does not populate authentication | Use `@SpringBootTest`, `SpringExtension`, or proper test listener config |
| Using `@WithMockUser` when policy needs `TenantPrincipal` | 403 or `ClassCastException` | Custom factory creating the right principal type |
| Using 2-arg `UsernamePasswordAuthenticationToken` constructor | `isAuthenticated()` is false | Use the 3-arg constructor with authorities in test fixtures |
| Factory calls global `setContext` without clearing | Tests can affect one another | Return a new `SecurityContext`; let the listener manage lifecycle |
| `roles={"ROLE_READER"}` when factory adds prefix | Produces `ROLE_ROLE_READER` or fixture error | Follow unprefixed `roles` convention; use exact strings for `authorities` |
| Missing `@EnableMethodSecurity` | `@PreAuthorize` is not enforced | Enable method security and call the Spring bean |
| Calling `new ProjectService()` | Invalid-permission test still succeeds | Inject the Spring-proxied bean |
| Testing only happy paths | Fails to catch tenant/role check bugs | Add negative tests for wrong tenant, missing role, anonymous |
| POST test only asserts 403 | Unclear whether CSRF or policy denied it | Attach `with(csrf())` when testing POST authorization |
| `@WithSecurityContext` used as a JWT test | Test passes despite broken decoder | Write separate real authentication integration tests |
| `TEST_EXECUTION` when `@BeforeEach` needs principal | Setup sees null authentication | Use `TEST_METHOD` or relocate setup |
| Fixture data stored in static mutable fields | Parallel tests become flaky | Fresh context per test, immutable fixtures, data isolation |
| Custom principal grants too many permissions | Tests mask privilege escalation bugs | Grant least privilege; assert denied cases |
| App checks tenant only in UI | Direct HTTP requests can read across tenants | Enforce tenant/ownership checks in the service/method-security layer |

Specifically with `MockMvc`, if `@WithMockTenantUser` constructs the right principal yet the request still returns 401, inspect integration between `MockMvc` and the security filters, security matchers, test listeners, and URL rules. If a POST gets 403, check CSRF first; if a GET gets 403, check role/tenant or method security handlers.

## 13. Self-Check Exercises

**Question 1.** What is the core difference between `@WithSecurityContext` and `@WithMockUser`?  
**Answer:** It can create a **fully customized `SecurityContext`/Authentication/principal** via a factory instead of using the default mock `UserDetails`.

**Question 2.** What should `WithSecurityContextFactory` return?  
**Answer:** A new `SecurityContext` containing an `Authentication` matching the test annotation.

**Question 3.** `@WithMockTenantUser(roles={"READER"})` is declared, yet `hasRole('READER')` fails. What should be checked?  
**Answer:** Check whether the factory creates `ROLE_READER`, whether `Authentication` is authenticated, whether method security is enabled, and whether the tenant policy is denying access.

**Question 4.** Two tenants both have a user named `alice`. Can username alone be used to check ownership?  
**Answer:** No; verified tenant/account identity and resource-level permissions are required.

**Question 5.** A `@WithMockTenantUser` GET call succeeds. Does that prove the Basic password or JWT signature is valid?  
**Answer:** No; the test pre-populated authentication and bypassed the authentication provider.

**Question 6.** `@PreAuthorize` works on an injected bean but not when using `new ProjectService()`. Why?  
**Answer:** Calls outside Spring do not pass through the method-security interceptor/proxy.

**Question 7.** With `TEST_METHOD`, can `@BeforeEach` read authentication?  
**Answer:** Usually yes, because the listener installs the context before `@BeforeEach` callbacks in the standard lifecycle.

**Question 8.** With `TEST_EXECUTION`, does `@BeforeEach` already have the mock identity?  
**Answer:** No under the described timing; the context is set up right before the test method, after `@BeforeEach`.

**Question 9.** Does `@WithSecurityContext` automatically attach a CSRF token to `MockMvc` POSTs?  
**Answer:** No. Use `with(csrf())` or an appropriate client flow when testing POSTs through `CsrfFilter`.

**Question 10.** You want to check permission `PROJECT_EXPORT` without granting `ROLE_ADMIN`. What should you do?  
**Answer:** Configure the factory/annotation to create exact `SimpleGrantedAuthority("PROJECT_EXPORT")`, use `hasAuthority('PROJECT_EXPORT')`, and also test missing the permission.

## 14. Checklist Before Applying to a Project

1. **Define the real principal**: class, internal ID fields, tenant, roles/permissions; never equate email/username with account ID.
2. **Define the test annotation**: domain-specific name, sensible defaults on attributes, unambiguous roles vs. authorities.
3. **Write the factory**: validate inputs, build principal and `GrantedAuthority`, create an authenticated `Authentication`, return a new context; never mutate the global holder arbitrarily.
4. **Pick test lifecycle**: `TEST_METHOD` or `TEST_EXECUTION` depending on whether setup needs authentication.
5. **Ensure method security**: `@EnableMethodSecurity`, proper Spring proxy bean, avoid self-invocation.
6. **Test security layers independently**: URL authorization, `@PreAuthorize`, tenant/ownership policy, CSRF on POST; never treat a generic 403 as proof of one specific layer.
7. **Write negative tests**: user lacking role, wrong tenant, anonymous, wrong principal type, disabled account, insufficient permissions, cross-tenant resources.
8. **Separate mock identity from real login**: `@WithSecurityContext` tests post-authentication behavior; separate integration tests verify passwords/tokens/IdPs.
9. **Isolate data and clean up context**: rely on Spring Test listener, avoid mutable static state, test parallel runs and threads with complex propagation.
10. **Keep annotations in test sources**: never ship factories supplying fake roles/tenants in production execution paths.

**Remember:** `@WithSecurityContext` helps simulate an **authenticated identity matching your exact domain structure** to test authorization logic deliberately. The factory builds test context; it **does not** replace authentication providers or real authentication integration tests. With Spring Security Servlet, combining service-proxy tests and `MockMvc` catches both method-security bugs and request routing/CSRF mistakes.
