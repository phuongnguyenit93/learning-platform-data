# @WithMockUser, Anonymous, and Custom Identities in Spring Boot Testing

## 1. Why test by identity?

A Spring Boot endpoint protected by Spring Security does not depend solely on the request path and body. The outcome also depends on **who is calling**, their authentication state, and the permissions they hold.

Consider a multi-tenant resource management system:

- Anonymous callers are allowed to invoke `GET /api/public` but are blocked on `GET /api/me`.
- Regular users access public or their own resources, but cannot access `/api/admin`.
- Admins with `ROLE_ADMIN` can access `/api/admin`.
- A service reading tenant data only accepts a principal containing `tenantId` and authority `TENANT_READ`.
- A valid user's `POST` request can still receive `403` due to a missing CSRF token.

If all tests run under an ADMIN account or disable filters to make controller tests “green”, these critical boundaries go untested.

Spring Security Test provides three essential groups of tools:

1. **`@WithMockUser`**: simulates a user with username, roles, and authorities without requiring an account in the DB.
2. **`@WithAnonymousUser`**: creates an anonymous identity to test unauthenticated policies and override class-level users.
3. **`@WithUserDetails` / `@WithSecurityContext`**: creates a custom principal containing a tenant ID or specific `Authentication` type required by the real application.

These annotations suit **method-security tests** and **MockMvc tests configured with Spring Security**. They **do not** automatically send credentials over a real HTTP request to a server running on another thread.

### Learning objectives

After this lesson, you will be able to:

- Explain `Authentication`, `SecurityContext`, principal, roles, authorities, and anonymous tokens.
- Distinguish authentication (identity verified) from authorization (whether the action is permitted).
- Assert `401`, `403`, and `200` according to the active authentication entry point/policy.
- Write `@WithMockUser(username=...,roles=...)` and `@WithMockUser(authorities=...)` accurately.
- Use `@WithAnonymousUser` at class/method level and the `anonymous()` request postprocessor.
- Understand why `@WithMockUser` usually **does not** return the application's custom `AppPrincipal` type.
- Use `@WithUserDetails` to load a principal from a real `UserDetailsService` bean.
- Build a custom `@WithTenantIdentity` using `@WithSecurityContext` and `WithSecurityContextFactory`.
- Run MockMvc with security filters, CSRF, and request-level users.
- Run real HTTP tests with Basic credentials without relying on the JUnit thread's `SecurityContext`.
- Avoid false positives when testing JWT, passwords, role/tenant authorization, and async/reactive security.

## 2. Authentication is not Authorization

**Authentication** answers: “Who is calling?”. Spring Security stores an `Authentication` in `SecurityContext`, such as a `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken`, or `AnonymousAuthenticationToken`.

**Authorization** answers: “Does this identity have permission to perform this action?”. Rules may check `hasRole("ADMIN")`, `hasAuthority("TENANT_READ")`, resource ownership, tenant, scope, or `@PreAuthorize` annotations.

~~~text
SecurityContextHolder
        |
        +-- SecurityContext
                |
                +-- Authentication
                        |-- principal: User / AppPrincipal / Jwt ...
                        |-- name: alice
                        |-- authorities:
                        |      ROLE_USER
                        |      TENANT_READ
                        |-- credentials
                        |-- authenticated
~~~

Two distinct rules:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public String adminOnly() {
    return "admin";
}

@PreAuthorize("hasAuthority('TENANT_READ')")
public String tenantInfo() {
    return "tenant";
}
~~~

These methods are **illustrative samples**, not yet part of a complete project. `hasRole("ADMIN")` usually checks authority `ROLE_ADMIN`; `hasAuthority("TENANT_READ")` checks the exact string `TENANT_READ`.

**Do not infer from a single successful login test that every resource is properly authorized.** Negative tests are required for missing roles, missing authorities, anonymous callers, and cross-tenant access.

## 3. Anonymous does not mean authentication == null

When the servlet security filter chain enables anonymous authentication, an unauthenticated request can be represented by an `AnonymousAuthenticationToken`. This token may return `isAuthenticated() == true` by implementation, yet Spring Security still treats it as anonymous through `AuthenticationTrustResolver`.

Therefore:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

boolean reallyLoggedIn =
        authentication != null && authentication.isAuthenticated();
~~~

is **not a reliable way** to determine whether a user is truly logged in in all cases.

Use Spring Security's own authorization rules such as `authenticated()`/`anonymous()`, or when manual inspection is needed:

~~~java
AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

boolean anonymous = resolver.isAnonymous(authentication);
~~~

These snippets are Java samples requiring appropriate imports and context.

### 3.1 Distinguishing three states

| State | Example | Possible consequence |
| --- | --- | --- |
| No `Authentication` | Calling a secured service directly in a test without setting an identity | `AuthenticationCredentialsNotFoundException` |
| `AnonymousAuthenticationToken` present | `@WithAnonymousUser` or anonymous filter | Most protected operations are denied |
| Authenticated user/token present | `@WithMockUser`, `@WithUserDetails`, real Basic/Bearer | Still subject to authorization checks |

HTTP `401` and `403` are not immutable constants across every security config. The `httpBasic()` application in this lesson returns `401` for unauthenticated requests to protected URLs and typically `403` when authenticated without sufficient permissions. Form-login may redirect, while a resource server may return an appropriate `WWW-Authenticate` header.

## 4. Where does Spring Security Test operate?

Spring Security Test integrates with Spring TestContext via `WithSecurityContextTestExecutionListener`. The listener sets up `SecurityContextHolder` before each test and cleans it up afterward. For reactive method security, integration with `ReactorContextTestExecutionListener` and reactive security context is also needed.

~~~text
Spring TestContext
     |
     +-- WithSecurityContextTestExecutionListener
     |       |
     |       +-- reads @WithMockUser / @WithUserDetails
     |       +-- creates SecurityContext for test thread
     |       +-- runs test code / MockMvc
     |       +-- clears test SecurityContext after test
     |
     +-- test method / assertions
~~~

**The test thread's `SecurityContext` ≠ a real HTTP server session or token.** When `@SpringBootTest(RANDOM_PORT)` processes a request over TCP on a server thread, the request must carry the required Basic/Bearer/cookie itself.

### 4.1 Tool scope

| Tool | Principal created | When to use |
| --- | --- | --- |
| `@WithMockUser` | Spring Security `User` | Basic username, role, and authority tests |
| `@WithAnonymousUser` | Anonymous token | Testing anonymous access, overriding class-level user |
| `@WithUserDetails` | `UserDetails` from `UserDetailsService` bean | When the application's exact custom principal is needed |
| `@WithSecurityContext` | Factory-defined | When tenant ID, claims, or custom `Authentication` type is needed |
| `with(user(...))` | Identity per single MockMvc request | A single test needing multiple users |
| `with(anonymous())` | Anonymous per request | Testing public/protected routes |
| `with(authentication(...))` | Custom `Authentication` per request | Testing manually constructed tokens |
| `with(csrf())` | Valid test CSRF token | POST/PUT/PATCH/DELETE when CSRF is enabled |
| `with(jwt())` | Mocked JWT Authentication | Testing resource-server authorization, not JWT signature |

## 5. @WithMockUser: defaults and variants

Example:

~~~java
@Test
@WithMockUser
void defaultMockUser() {
    // username "user"
    // mock password "password"
    // authority ROLE_USER
}
~~~

`@WithMockUser` creates a `UsernamePasswordAuthenticationToken` with a principal of type `org.springframework.security.core.userdetails.User`. The user **does not need to exist in a database or `UserDetailsService`**; the password also **does not pass through login or `PasswordEncoder`**.

### 5.1 Username

~~~java
@WithMockUser(username = "minh")
~~~

The authentication name observed by the test is typically `minh`.

### 5.2 roles vs authorities

~~~java
@WithMockUser(roles = "ADMIN")
~~~

Creates authority `ROLE_ADMIN`.

~~~java
@WithMockUser(authorities = "ADMIN")
~~~

Creates authority `ADMIN` **without** adding `ROLE_`. Thus, if a URL uses `hasRole("ADMIN")`, the first case PASSES while the second is typically denied. You can declare:

~~~java
@WithMockUser(authorities = "ROLE_ADMIN")
~~~

to grant the prefixed authority directly.

**Do not** specify `roles="ROLE_ADMIN"` when using the default prefix: the `roles` parameter accepts role names **without** `ROLE_`. If the application customizes the role prefix, double-check the exact configuration.

### 5.3 Custom principal limitation

If production code casts:

~~~java
AppPrincipal p = (AppPrincipal) SecurityContextHolder
        .getContext().getAuthentication().getPrincipal();
~~~

then default `@WithMockUser` can throw `ClassCastException` because the actual principal is `User`, not `AppPrincipal`. For services that read `tenantId`, use `@WithUserDetails` or an appropriate `@WithSecurityContext`.

## 6. @WithAnonymousUser, class-level overrides, and meta-annotations

~~~java
@WithMockUser(username = "default-member")
class ExampleTests {

    @Test
    void usesDefaultMember() {
        // default-member
    }

    @Test
    @WithAnonymousUser
    void methodIsAnonymous() {
        // Method annotation overrides class-level user.
    }
}
~~~

This is a pattern requiring an appropriate Spring test context. `@WithAnonymousUser` is useful when most tests run as a user but a few cases test “not logged in”.

You can create meta-annotations to reduce repetition:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@WithMockUser(username = "auditor", authorities = "REPORT_READ")
public @interface WithAuditor {
}
~~~

The snippet above is an illustrative sample. A meta-annotation using `@WithMockUser` still creates a `User` principal; if a tenant ID or domain principal is required, the meta-annotation must use a custom factory or `@WithUserDetails`.

**Do not** place `@WithMockUser(roles="ADMIN")` on every test, as that makes it easy to miss the principle of least privilege. Always include at least one test with insufficient permissions.

## 7. @WithUserDetails: when identity must come from UserDetailsService

`@WithUserDetails` invokes `UserDetailsService.loadUserByUsername(...)` to load the exact `UserDetails` instance returned by the bean.

~~~java
@Test
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "demoUsers")
void worksWithActualAppPrincipalType() {
    // AppPrincipal returned from demoUsers.
}
~~~

Requirements:

- The context has an appropriate `UserDetailsService` bean.
- The test username exists; otherwise setup fails in the test listener.
- If multiple `UserDetailsService` beans exist, specify `userDetailsServiceBeanName`.
- The real `UserDetailsService` returns `AppPrincipal` if code expects `AppPrincipal`.
- The factory initializes the identity before the test runs; this is not a network login.

**Does not verify passwords.** Even though `UserDetailsService` loads a real account, `@WithUserDetails` skips password/Basic/token authentication. To test the login provider, include tests that send credentials over HTTP or go through the real `AuthenticationManager`.

### 7.1 Users seeded in @BeforeEach: watch out for setupBefore

By default, the security test listener creates the context at `TestExecutionEvent.TEST_METHOD`, which is **before JUnit `@BeforeEach`**. If a user is only seeded into the database inside `@BeforeEach`, `@WithUserDetails` may look up the user too early.

You can use:

~~~java
@WithUserDetails(
    value = "alice",
    setupBefore = TestExecutionEvent.TEST_EXECUTION)
~~~

to set up the context after `@BeforeEach` and before `@Test`. You must also check fixture transaction visibility if the service reads the database from another connection. Do not use `@BeforeAll` assuming per-method `SecurityContext` is already established.

## 8. @WithSecurityContext: custom annotation with tenant and authorities

A multi-tenant application might use a principal containing `username`, `tenantId`, and `authorities`. Do not want every test calling the user store? Create an annotation:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(factory = WithTenantIdentityFactory.class)
public @interface WithTenantIdentity {
    String username() default "tenant-user";
    String tenantId() default "tenant-default";
    String[] authorities() default {"ROLE_USER", "TENANT_READ"};
}
~~~

The factory creates a new `SecurityContext` and `Authentication` with the right principal:

~~~java
@Override
public SecurityContext createSecurityContext(
        WithTenantIdentity config) {

    SecurityContext context =
            SecurityContextHolder.createEmptyContext();

    AppPrincipal principal = new AppPrincipal(
            config.username(),
            config.tenantId(),
            "not-used-for-login",
            config.authorities());

    Authentication authentication =
            UsernamePasswordAuthenticationToken.authenticated(
                    principal, "N/A", principal.getAuthorities());

    context.setAuthentication(authentication);
    return context;
}
~~~

Both snippets above are provided as complete Java files in the hands-on section.

**Never retain a static mutable `SecurityContext`**: identity can leak from one test to another, especially with concurrency. A test factory only represents an **assumed identity**; it does not prove a real user can obtain those authorities from an IdP or user store.

## 9. MockMvc and security filters: conditions for meaningful tests

`MockMvc` dispatches mock servlet requests to MVC controllers without opening a TCP socket. However, to test security, the Spring Security filter chain and test support are required.

Two common setups:

~~~java
// Full app context in Spring Boot tests:
@SpringBootTest
@AutoConfigureMockMvc
class SecurityMvcTest {
    @Autowired MockMvc mvc;
}
~~~

Or manual MockMvc configuration:

~~~java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
~~~

These are illustrative samples requiring imports and context. Using `MockMvcBuilders.standaloneSetup(controller)` **without attaching Security filters** can allow a controller to return 200 where production would return 401/403.

### 9.1 Request-scoped users

A single test can simulate two users across two requests:

~~~java
mvc.perform(get("/api/me")
        .with(user("alice").roles("USER")))
        .andExpect(status().isOk());

mvc.perform(get("/api/me")
        .with(anonymous()))
        .andExpect(status().isUnauthorized());
~~~

These request postprocessors reside in `SecurityMockMvcRequestPostProcessors`. `with(user(...))` does not verify a password or user existence; it only sets the identity for that MockMvc request. `with(authentication(authentication))` and `with(securityContext(context))` support manually constructed tokens.

## 10. CSRF: a 403 is not always a wrong role

With Spring Security servlet CSRF protection enabled, an authenticated user sending a `POST` without a CSRF token may be blocked with `403` even if their permissions are valid.

~~~java
@Test
@WithMockUser
void postWithoutCsrfFails() throws Exception {
    mvc.perform(post("/api/write"))
            .andExpect(status().isForbidden());
}

@Test
@WithMockUser
void postWithCsrfPasses() throws Exception {
    mvc.perform(post("/api/write").with(csrf()))
            .andExpect(status().isOk());
}
~~~

`csrf()` only generates a **test CSRF token** for the MockMvc request; it does not test how a browser receives cookies/sessions or how the frontend transmits the token. You can use `csrf().useInvalidToken()` to test invalid tokens.

**Do not disable security filters/CSRF just to make tests PASS** when the test's goal is security behavior. For stateless APIs using bearer tokens, the CSRF policy may differ and must follow the real threat model/configuration.

## 11. Structure of the Java 17+ / Spring Boot 3.5.x example suite

The hands-on project contains **five production classes**, **two test-support classes**, and **four test classes**, testing MockMvc, method security, and real HTTP.

~~~text
security-testing-demo/
  settings.gradle
  build.gradle
  src/
    main/java/example/security/
      SecurityDemoApplication.java
      AppPrincipal.java
      SecurityConfiguration.java
      TenantService.java
      IdentityController.java
    test/java/example/security/
      WithTenantIdentity.java
      WithTenantIdentityFactory.java
      SecurityMvcTest.java
      MethodSecurityTest.java
      ClassLevelIdentityTest.java
      LiveHttpIdentityTest.java
~~~

All Java files belong to `package example.security`. The example requires no DB/Docker and uses a demo in-memory `UserDetailsService`. Fixed credentials in the demo **must never be used in production**.

### 11.1 settings.gradle

~~~groovy
rootProject.name = 'security-testing-demo'
~~~

### 11.2 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is the complete `build.gradle` with the plugins/dependencies needed for the mini-project. A compatible Gradle or Gradle wrapper is needed to run it. Versions are pinned for the example and **are not claimed to be the latest releases**. The test suite uses Servlet MVC + Spring Security 6.5.x, not WebFlux.

## 12. Production Java: SecurityDemoApplication.java

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
~~~

The root package ensures components, `SecurityFilterChain`, and services are scanned properly by Spring Boot.

## 13. Production Java: AppPrincipal.java

~~~java
package example.security;

import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.userdetails.UserDetails;

public final class AppPrincipal implements UserDetails {

    private final String username;
    private final String tenantId;
    private final String password;
    private final List<GrantedAuthority> authorities;

    public AppPrincipal(
            String username,
            String tenantId,
            String password,
            String... authorities) {
        this.username = Objects.requireNonNull(username);
        this.tenantId = Objects.requireNonNull(tenantId);
        this.password = Objects.requireNonNull(password);
        this.authorities = List.copyOf(
                AuthorityUtils.createAuthorityList(authorities));
    }

    public String tenantId() {
        return tenantId;
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public String getPassword() {
        return password;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }
}
~~~

`AppPrincipal` has the domain field `tenantId`. In a real application, you might add an immutable `userId` and real enabled/locked flags. Returning `isEnabled()==true` only simplifies the demo and must not be treated as a production account management pattern.

## 14. Production Java: SecurityConfiguration.java

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .requestMatchers(
                                "/api/me",
                                "/api/tenant",
                                "/api/write").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean("demoUsers")
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        // DEMO-ONLY: Do not use these accounts in production.
        String hash = encoder.encode("demo-pass");

        return username -> switch (username) {
            case "alice" -> new AppPrincipal(
                    "alice", "tenant-blue", hash,
                    "ROLE_USER", "TENANT_READ");
            case "root" -> new AppPrincipal(
                    "root", "tenant-ops", hash,
                    "ROLE_ADMIN", "TENANT_READ");
            default -> throw new UsernameNotFoundException(
                    "User not found");
        };
    }
}
~~~

- `httpBasic()` configures the authentication mechanism used for live HTTP tests.
- `/api/public` is public, `/api/admin` requires `ROLE_ADMIN`, and the remaining endpoints require `authenticated`.
- `@EnableMethodSecurity` enables `@PreAuthorize` on services.
- `demoUsers` returns the **demo's real `AppPrincipal`**, not Spring Security's `User`.
- Passwords are encoded; no plaintext production store is used.
- CSRF remains enabled per servlet security defaults, so POST tests require a token.

### 14.1 Do not treat in-memory demo users as a production solution

The goal is to illustrate how `@WithUserDetails` and HTTP Basic share the same user service. Production requires a trusted user store/IdP, secure secrets management, account status, login throttling, token validity, and auditing.

## 15. Production Java: TenantService.java

~~~java
package example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class TenantService {

    @PreAuthorize("hasAuthority('TENANT_READ')")
    public String currentTenant() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (!(authentication.getPrincipal()
                instanceof AppPrincipal principal)) {
            throw new IllegalStateException(
                    "AppPrincipal required");
        }

        return principal.tenantId();
    }
}
~~~

`@PreAuthorize` checks permissions before the method body. The method then requires the principal to be an `AppPrincipal` to return `tenantId`.

Therefore:

- `@WithMockUser(roles="USER")`: lacks `TENANT_READ` -> denied before the method body.
- `@WithMockUser(authorities="TENANT_READ")`: passes the authority check, but the principal is still `User` -> `IllegalStateException`.
- `@WithUserDetails("alice")` or `@WithTenantIdentity`: the principal is `AppPrincipal` and has `TENANT_READ` -> succeeds.

This is how you write negative tests that catch both permission errors and identity-type errors.

## 16. Production Java: IdentityController.java

~~~java
package example.security;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    private final TenantService tenants;

    public IdentityController(TenantService tenants) {
        this.tenants = tenants;
    }

    @GetMapping("/api/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/api/me")
    public String currentUser(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }

    @GetMapping("/api/tenant")
    public String tenant() {
        return tenants.currentTenant();
    }

    @PostMapping("/api/write")
    public String write() {
        return "saved";
    }
}
~~~

`/api/write` performs no DB write; it exists to test CSRF. If a production system works with tenant data, the real service/repository must filter by the tenant from the verified principal rather than unconditionally trusting a `tenantId` from a request parameter.

## 17. Test-only custom annotation and factory

### 17.1 WithTenantIdentity.java

~~~java
package example.security;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.test.context.support.WithSecurityContext;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(factory = WithTenantIdentityFactory.class)
public @interface WithTenantIdentity {
    String username() default "tenant-user";
    String tenantId() default "tenant-default";
    String[] authorities() default {"ROLE_USER", "TENANT_READ"};
}
~~~

### 17.2 WithTenantIdentityFactory.java

~~~java
package example.security;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public final class WithTenantIdentityFactory
        implements WithSecurityContextFactory<WithTenantIdentity> {

    @Override
    public SecurityContext createSecurityContext(
            WithTenantIdentity config) {

        AppPrincipal principal = new AppPrincipal(
                config.username(),
                config.tenantId(),
                "not-used-for-login",
                config.authorities());

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        principal, "N/A", principal.getAuthorities());

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
~~~

The factory creates a fresh `SecurityContext` each time and does not share a static `Authentication`. It grants authorities from the annotation **only to test authorization**. Simulating an identity this way does not prove a production provider can authenticate passwords, JWTs, or tenant claims.

## 18. SecurityMvcTest.java: 14 JUnit methods

File `src/test/java/example/security/SecurityMvcTest.java`:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityMvcTest {

    @Autowired MockMvc mvc;

    @Test
    void publicWithoutLogin() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void protectedWithoutLogin() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithAnonymousUser
    void anonymousCanReadPublic() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk());
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotReadPrivate() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "mika")
    void mockUsernameAppearsInResponse() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isOk())
                .andExpect(content().string("mika"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotReadAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void roleAdminCanReadAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
                .andExpect(status().isOk())
                .andExpect(content().string("admin"));
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void plainAuthorityIsNotRoleAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithUserDetails(
        value = "alice",
        userDetailsServiceBeanName = "demoUsers")
    void withUserDetailsLoadsTenantPrincipal() throws Exception {
        mvc.perform(get("/api/tenant"))
                .andExpect(status().isOk())
                .andExpect(content().string("tenant-blue"));
    }

    @Test
    @WithTenantIdentity(tenantId = "tenant-red")
    void customAnnotationProvidesTenant() throws Exception {
        mvc.perform(get("/api/tenant"))
                .andExpect(status().isOk())
                .andExpect(content().string("tenant-red"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void missingTenantReadIsForbidden() throws Exception {
        mvc.perform(get("/api/tenant"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void postWithoutCsrfFails() throws Exception {
        mvc.perform(post("/api/write"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void postWithCsrfPasses() throws Exception {
        mvc.perform(post("/api/write").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("saved"));
    }

    @Test
    @WithMockUser(username = "annotation-user")
    void requestLevelIdentityOverridesTestAnnotation()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(user("per-request").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("per-request"));
    }
}
~~~

**14 `@Test` methods**, using `@SpringBootTest` and `@AutoConfigureMockMvc` to retain the real filter chain and method-security proxy. No filters are disabled, `TenantService` is not mocked, and no real network is needed.

### 18.1 Results to understand

- No auth/anonymous to a private URL -> `401` under the HTTP Basic config.
- Role `USER` to the admin URL -> `403`.
- Role `ADMIN` to the admin URL -> `200`.
- Authority `ADMIN` does not automatically become `ROLE_ADMIN` -> `403`.
- `@WithUserDetails` and custom annotation provide `AppPrincipal` -> return the expected tenant.
- Authenticated user missing `TENANT_READ` -> `403` from method security.
- POST missing CSRF -> `403` even with a mock user.
- POST with valid CSRF -> `200`.
- Request-specific `user("per-request")` overrides the identity for that request.

If a test fails differently than expected, inspect the entry point and security configuration rather than changing expected statuses blindly.

## 19. MethodSecurityTest.java: 7 JUnit methods

File `src/test/java/example/security/MethodSecurityTest.java`:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class MethodSecurityTest {

    @Autowired TenantService tenants;

    @Test
    void noAuthenticationFails() {
        assertThrows(
                AuthenticationCredentialsNotFoundException.class,
                () -> tenants.currentTenant());
    }

    @Test
    @WithAnonymousUser
    void anonymousFailsAuthorization() {
        assertThrows(AccessDeniedException.class,
                () -> tenants.currentTenant());
    }

    @Test
    @WithMockUser(roles = "USER")
    void roleUserLacksTenantRead() {
        assertThrows(AccessDeniedException.class,
                () -> tenants.currentTenant());
    }

    @Test
    @WithMockUser(authorities = "TENANT_READ")
    void authorityIsNotEnoughWithoutCustomPrincipal() {
        assertThrows(IllegalStateException.class,
                () -> tenants.currentTenant());
    }

    @Test
    @WithUserDetails(
        value = "alice",
        userDetailsServiceBeanName = "demoUsers")
    void withUserDetailsSuppliesAppPrincipal() {
        assertEquals("tenant-blue",
                tenants.currentTenant());
    }

    @Test
    @WithTenantIdentity(tenantId = "tenant-violet")
    void withSecurityContextSuppliesAppPrincipal() {
        assertEquals("tenant-violet",
                tenants.currentTenant());
    }

    @Test
    @WithAnonymousUser
    void anonymousTokenIsNotRealLogin() {
        Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();

        assertInstanceOf(AnonymousAuthenticationToken.class, auth);
        assertTrue(auth.isAuthenticated());
        assertTrue(new AuthenticationTrustResolverImpl()
                .isAnonymous(auth));
    }
}
~~~

**7 `@Test` methods**. These methods invoke the **Spring-managed `TenantService` proxy**, so `@PreAuthorize` is actually enforced. If `@EnableMethodSecurity` is removed, the negative tests will no longer exhibit the same behavior.

## 20. ClassLevelIdentityTest.java: 3 JUnit methods

File `src/test/java/example/security/ClassLevelIdentityTest.java`:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@WithMockUser(username = "baseline", roles = "USER")
class ClassLevelIdentityTest {

    @Autowired MockMvc mvc;

    @Test
    void inheritsDefaultUser() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isOk())
                .andExpect(content().string("baseline"));
    }

    @Test
    @WithMockUser(username = "root-mock", roles = "ADMIN")
    void methodOverridesClassRole() throws Exception {
        mvc.perform(get("/api/admin"))
                .andExpect(status().isOk());
    }

    @Test
    @WithAnonymousUser
    void anonymousOverridesClassUser() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

**3 `@Test` methods** showing that method-level annotations take precedence over class-level identity. Do not apply class-level `ADMIN` broadly because it can accidentally let under-privileged routes PASS.

## 21. LiveHttpIdentityTest.java: 4 real HTTP tests

`@WithMockUser` applies to the **JUnit test thread**. With `@SpringBootTest(RANDOM_PORT)`, the servlet handles requests on a **server thread**; identities on the test thread do not cross TCP automatically. Requests must send real credentials (Basic/Bearer/session cookie).

File `src/test/java/example/security/LiveHttpIdentityTest.java`:

~~~java
package example.security;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpIdentityTest {

    @LocalServerPort int port;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @Test
    @WithMockUser(username = "pretend-admin", roles = "ADMIN")
    void mockAnnotationDoesNotAuthenticateLiveRequest()
            throws Exception {
        HttpResponse<String> response =
                get("/api/admin", null);

        assertEquals(401, response.statusCode());
    }

    @Test
    void validBasicLoadsCustomPrincipal() throws Exception {
        HttpResponse<String> response =
                get("/api/tenant", "alice:demo-pass");

        assertEquals(200, response.statusCode());
        assertEquals("tenant-blue", response.body());
    }

    @Test
    void userWithoutAdminRoleIsForbidden() throws Exception {
        HttpResponse<String> response =
                get("/api/admin", "alice:demo-pass");

        assertEquals(403, response.statusCode());
    }

    @Test
    void adminWithBasicCredentialsIsAllowed() throws Exception {
        HttpResponse<String> response =
                get("/api/admin", "root:demo-pass");

        assertEquals(200, response.statusCode());
        assertEquals("admin", response.body());
    }

    private HttpResponse<String> get(
            String path, String credentials)
            throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(10))
                .GET();

        if (credentials != null) {
            String encoded = Base64.getEncoder().encodeToString(
                    credentials.getBytes(StandardCharsets.UTF_8));
            builder.header("Authorization", "Basic " + encoded);
        }

        return http.send(
                builder.build(),
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }
}
~~~

**4 `@Test` methods**. HTTP Basic requests pass through the demo application's real filter chain and authentication provider. Demo accounts are supplied by `UserDetailsService`, and passwords are verified by `PasswordEncoder`. This still does not test JWT/OAuth2 because the demo app does not use those mechanisms.

**Security note:** Basic over HTTP is acceptable only for temporary localhost tests; production must protect credentials with HTTPS and never log raw `Authorization` headers. Do not use fixed lecture passwords in real systems.

## 22. Total of 28 tests and run commands

| Test class | `@Test` methods | What is tested |
| --- | ---: | --- |
| `SecurityMvcTest` | 14 | Anonymous, mock user, roles/authorities, CSRF, request identity |
| `MethodSecurityTest` | 7 | `@PreAuthorize`, principal type, anonymous token |
| `ClassLevelIdentityTest` | 3 | Class-level vs method-level overrides |
| `LiveHttpIdentityTest` | 4 | Basic login over real HTTP, 401/403/200, thread boundary |
| **Total** | **28** | Servlet Security and custom `AppPrincipal` |

Linux/macOS:

~~~bash
./gradlew test --tests example.security.SecurityMvcTest --tests example.security.MethodSecurityTest --tests example.security.ClassLevelIdentityTest --tests example.security.LiveHttpIdentityTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.security.SecurityMvcTest --tests example.security.MethodSecurityTest --tests example.security.ClassLevelIdentityTest --tests example.security.LiveHttpIdentityTest
~~~

To run everything:

~~~bash
./gradlew clean test
~~~

**Expected result:** JUnit Jupiter discovers 28 test methods and all PASS on Java 17+/Spring Boot 3.5.x/Security 6.5.x with the lesson's exact source code and dependencies. This is an **expectation from structural review, not stdout from an actually executed Gradle build**. Gradle reports are located at `build/reports/tests/test/index.html` once the build completes; the random HTTP port and startup logs are not fixed.

## 23. @WebMvcTest or @SpringBootTest?

**`@WebMvcTest`** is an MVC slice: fast, focused on controllers, validation, and filters. It does not by default load all application services or custom security configurations; `@Import` and mocks/fakes are needed as appropriate. If you mock `TenantService`, the real service's `@PreAuthorize` method security **is not tested**. Add a separate service authorization test.

**`@SpringBootTest + @AutoConfigureMockMvc`** loads the full context and sends MockMvc through `SecurityFilterChain` and Spring beans. It fits well when you want to test controllers, filters, method security, and principal injection together without TCP.

**`@SpringBootTest(RANDOM_PORT)`** runs a real HTTP server. `@WithMockUser` on a test **does not authenticate live requests**. Send real Basic/Bearer/cookie headers on the request to verify authentication mechanisms, entry points, and server threads.

**Direct method tests** invoke `@Autowired` services in tests with `@WithMockUser`/`@WithUserDetails`; they test `@PreAuthorize` and custom principals, not the HTTP pipeline.

Do not pick full context for every test if pure domain logic does not use Spring. Keep unit tests fast while maintaining an integration security suite that never disables filters or advice.

## 24. How do JWT, OAuth2, WebFlux, and async differ?

### 24.1 JWT and OAuth2

If production uses an OAuth2 Resource Server, the principal may be `Jwt` or `JwtAuthenticationToken`, and authorities may carry `SCOPE_`. Use the appropriate `spring-security-test` request postprocessor `jwt()`/`oauth2Login()` to **simulate identity and test authorization**.

~~~text
Access token claim "scope": "invoice:read"
    |
    v
JwtAuthenticationConverter
    |
    v
GrantedAuthority: SCOPE_invoice:read
    |
    v
hasAuthority("SCOPE_invoice:read")
~~~

This is an illustrative flow, not included in the mini-project. `with(jwt())` **does not** prove token signatures, issuer, audience, expiry, or JWK fetching actually work. Add dedicated decoder/validator tests when those are security requirements.

### 24.2 WebFlux

With WebFlux, `SecurityContext` propagates via Reactor Context rather than simply a servlet `ThreadLocal`. Use `WebTestClient` security support, for example:

~~~java
webTestClient
        .mutateWith(mockUser().roles("ADMIN"))
        .get()
        .uri("/api/admin")
        .exchange()
        .expectStatus().isOk();
~~~

This is an illustrative snippet for a **reactive app**, requiring `SecurityMockServerConfigurers.mockUser`, `WebTestClient`, and reactive security configuration. Do not swap it directly into the `MockMvc` sample expecting identical semantics.

### 24.3 @Async and thread pools

In servlet tests, `SecurityContextHolder` is typically thread-bound. `@Async`, executors, scheduled tasks, and HTTP server threads do not automatically inherit the identity. When propagation is needed, use `DelegatingSecurityContextExecutor` or a properly configured/tested context-propagation mechanism.

Do not enable `MODE_INHERITABLETHREADLOCAL` globally without care: thread pools reuse threads, which can leak user context if cleanup is wrong.

## 25. Common pitfalls

**1. Missing `spring-security-test`.**  
Annotations and MockMvc postprocessors will not compile. Add the test-scope dependency.

**2. Treating `@WithMockUser` as a real login.**  
It does not compare passwords or call an authentication provider. To test providers, send real credentials.

**3. `@WithMockUser(roles="ROLE_ADMIN")`.**  
Wrong prefix. Use `roles="ADMIN"`.

**4. `@WithMockUser(authorities="ADMIN")` while expecting `hasRole("ADMIN")`.**  
That authority lacks the `ROLE_` prefix.

**5. Using `@WithMockUser` for a service requiring `AppPrincipal`.**  
The default mock principal is Spring `User`; use `@WithUserDetails` or a custom factory.

**6. Confusing no `Authentication` with an anonymous token.**  
A null context and an anonymous context behave differently.

**7. Believing `auth.isAuthenticated()==true` means real login.**  
`AnonymousAuthenticationToken` can also return `true`; check the trust resolver/policy.

**8. Missing `@EnableMethodSecurity`.**  
`@PreAuthorize` does not execute; negative tests must catch this.

**9. `@AutoConfigureMockMvc(addFilters=false)` in security tests.**  
Bypasses filters; 401/403/CSRF outcomes lose meaning.

**10. User has `@WithMockUser` but POST lacks CSRF.**  
A 403 may come from `CsrfFilter`, not a missing role.

**11. `@WithUserDetails` runs lookup before `@BeforeEach` seeds the user.**  
Use the appropriate `setupBefore` or seed committed fixtures earlier.

**12. Multiple `UserDetailsService` beans without specifying the bean name.**  
Lookup ambiguity; specify the exact `userDetailsServiceBeanName`.

**13. Custom `@WithSecurityContext` factory using a static mutable context.**  
Leaks identity across tests; create a new context every time.

**14. Custom annotation missing `@Retention(RUNTIME)`.**  
The listener cannot read metadata at runtime.

**15. Testing only `ROLE_ADMIN`.**  
Fails to verify least privilege or anonymous access; add negative cases.

**16. `@WithMockUser` on `RANDOM_PORT` without credentials on the HTTP request.**  
The test thread does not pass security context over TCP; the server rightly returns 401.

**17. Treating MockMvc `user()` as a user database test.**  
The request postprocessor does not query the account store.

**18. Treating mock JWT as signature verification.**  
Separate decoder/validation tests are required.

**19. Treating test `AppPrincipal` `tenantId` as proof of tenant isolation.**  
Cross-tenant/DB filtering integration tests are required; never trust client-supplied `tenantId`.

**20. Testing 403 without distinguishing CSRF from authorization failure.**  
Test with/without CSRF, role, status, security events, and logs.

**21. Parallel tests using a static `SecurityContext`.**  
Can leak identities; avoid cross-thread mutation and ensure proper cleanup.

**22. Controller authentication lacks `Principal` because filters are disabled.**  
Restore the security filter chain instead of hard-coding a `Principal`.

**23. Not testing disabled/locked accounts.**  
`@WithMockUser` skips login providers; real authentication tests are needed.

**24. Not testing negative tenant/ownership cases.**  
An authenticated user can still read the wrong resource; test ABAC/data scoping.

## 26. Test design checklist

1. Identify whether the target is authentication, authorization, principal mapping, or object-level access.
2. Pick the test layer: direct service, MockMvc, WebMvc slice, live HTTP, or reactive `WebTestClient`.
3. Use `@WithMockUser` for simple roles/authorities; do not expect `AppPrincipal`.
4. Use `@WithAnonymousUser` for anonymous access and class-level overrides.
5. Use `@WithUserDetails` when a `UserDetailsService` bean and domain principal exist.
6. Use `@WithSecurityContext` when custom tenant/claims are needed without hitting a DB.
7. Create a fresh `SecurityContext`, granting only the authorities the test truly requires.
8. Check the `ROLE_` prefix and exact authority names.
9. Keep the filter chain and method-security proxy enabled in security integration tests.
10. Assert `401`/`403` matching the app's entry point; `403` can come from CSRF.
11. Use MockMvc `with(csrf())` when CSRF is enabled and the method is unsafe.
12. Live HTTP tests must carry real credentials/tokens, never relying on `@WithMockUser`.
13. Run both positive and negative cases for roles/authorities/tenants.
14. Separate mocked-identity tests from password/JWT signature validation tests.
15. Verify async/reactive context propagation if code crosses threads.
16. Never use demo users/passwords/keys in real environments.
17. Run tests against the project's exact Spring Boot/Security versions.

### Final checklist

- [ ] Tests cover anonymous, no-auth, under-privileged user, and authorized user.
- [ ] `@WithMockUser` roles/authorities use the right prefix.
- [ ] Principal type is verified when services require custom fields.
- [ ] `@WithUserDetails` looks up the right bean/user at the right lifecycle phase.
- [ ] `@WithSecurityContext` factory creates a separate context per test.
- [ ] Class-level users do not mask negative authorization cases.
- [ ] `SecurityFilterChain` and `@EnableMethodSecurity` are genuinely active.
- [ ] MockMvc filters are not disabled just to make tests green.
- [ ] CSRF tests reflect the active security configuration.
- [ ] `RANDOM_PORT` tests send real HTTP credentials/tokens.
- [ ] Authentication-provider/JWT validation has dedicated tests where needed.
- [ ] Tenant ownership/data isolation is tested at the repository/service layer.
- [ ] No user context leaks between tests or threads.

**Conclusion:** `@WithMockUser` is fast and convenient for role/authority tests; `@WithAnonymousUser` helps verify unauthenticated access; `@WithUserDetails` and `@WithSecurityContext` help construct proper domain principals when an application needs `tenantId` or custom `Authentication` types. However, tests must run at the **right boundary**: method security, MockMvc filters, or a real HTTP server. Only by testing thorough negative cases, CSRF, principal types, tenant isolation, and authentication entry points do you obtain trustworthy evidence for Spring Boot security.

### Official references

- [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, `@WithSecurityContext`, and lifecycle.
- [Spring Security 6.5 — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): filter chain and `springSecurity()`.
- [Spring Security 6.5 — MockMvc Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html): `user()`, `anonymous()`, `authentication()`, and `securityContext()`.
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()` and invalid tokens.
- [Spring Security 6.5 — Method Authorization](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and role/authority checks.
- [Spring Security — Reactive Test Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `WebTestClient` `mockUser` and Reactor context.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, and `RANDOM_PORT`.
