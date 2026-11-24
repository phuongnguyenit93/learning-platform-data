# @WithMockUser, @WithUserDetails, and @WithSecurityContext in Spring Security Testing

## 1. Lesson goal

When testing applications with Spring Security, we often need to construct three situations: an unauthenticated request, a regular user request, and a request from a user with special permissions/principal types. With JUnit 5 and Spring Security Test, three very useful annotations are:

- **`@WithMockUser`**: creates a mock user with a specified username and authorities/roles, **without needing that user to exist in the database or UserDetailsService**.
- **`@WithUserDetails`**: retrieves a real `UserDetails` from the `UserDetailsService` in the test ApplicationContext and places that user into the SecurityContext.
- **`@WithSecurityContext`**: the foundation for custom annotations, allowing you to create **any SecurityContext/Authentication**, such as a custom principal containing a tenant ID, service identity, or a specialized authentication type.

They help test **authorization** and how the application uses `SecurityContext`, but **do not automatically execute a real login flow**. A test annotated with `@WithMockUser` that accesses a protected page does not prove the password was checked by `PasswordEncoder.matches`, that a JWT signature was verified, or that MFA succeeded.

### Learning outcomes

After completing this lesson, you can:

1. Explain the `SecurityContext` lifecycle in Spring Test and MockMvc.
2. Properly use `@WithMockUser(username, roles, authorities)`.
3. Use `@WithUserDetails` to test principals and permissions loaded from `UserDetailsService`.
4. Create a `@WithTenantUser` annotation based on `@WithSecurityContext` along with `WithSecurityContextFactory`.
5. Distinguish `hasRole("ADMIN")` from `hasAuthority("ROLE_ADMIN")` and `docs:write`.
6. Combine `@SpringBootTest`, `@AutoConfigureMockMvc`, `spring-security-test`, `csrf()`, and `httpBasic()`.
7. Write **negative tests** as well: 401, 403, missing CSRF, missing permission, wrong principal type.
8. Distinguish mocked authentication tests from tests that actually pass through `AuthenticationManager`/PasswordEncoder.
9. Avoid pitfalls around setupBefore, bean naming, test slices, context leakage, and fabricated security claims.

> **Focus:** The three annotations are tools to *set up the authentication context for a test*. They do not replace testing credential verification, sessions, OAuth2/OIDC, MFA, or production mechanisms.

## 2. Core objects in Spring Security Test

A logged-in request is represented by an `Authentication`, held in a `SecurityContext`, and accessed via `SecurityContextHolder` in the Servlet stack.

~~~text
JUnit 5 + Spring TestContext Framework
       |
       | WithSecurityContextTestExecutionListener
       | reads annotation on test method/class
       v
SecurityContextHolder / TestSecurityContextHolder
       |
       +--> Authentication
       |       |
       |       +--> principal: User/UserDetails/CustomPrincipal
       |       +--> authorities: ROLE_USER, docs:write...
       |       +--> authenticated: true/false
       |
       v
MockMvc integrated with Spring Security filters
       |
       +--> SecurityFilterChain
       +--> AuthorizationManager / hasRole / hasAuthority
       +--> Controller / @PreAuthorize / service
       |
       v
Result: 200, 401, 403, or business error
~~~

Spring Security provides `WithSecurityContextTestExecutionListener` to prepare `SecurityContext` before each test and **clear the context afterward**. In MockMvc, Spring Security must be integrated properly: Spring Boot's `@AutoConfigureMockMvc` normally registers the filter chain automatically; with a manually built MockMvc, use `.apply(springSecurity())`.

### 2.1. Are Authentication and principal the same thing?

No. `Authentication` contains:
- **principal**: represents the user/service (can be `User`, custom `UserDetails`, `Jwt`, `OAuth2User`, a custom record, etc.);
- **credentials**: data used for authentication, depending on the mechanism; should never be logged or included in responses;
- **authorities**: the `GrantedAuthority` instances used by authorization to decide access;
- **authenticated**: flag representing whether the object is authenticated.

A test using `@WithMockUser` typically creates an already-authenticated `UsernamePasswordAuthenticationToken` with principal `org.springframework.security.core.userdetails.User`. That is different from a browser successfully submitting a login POST.

### 2.2. Two test layers to distinguish

| Testing layer | What we want to know | Appropriate tool |
|---|---|---|
| **Authorization / controller/service** | Can a user with role/scope X call endpoint Y? | `@WithMockUser`, `@WithUserDetails`, `@WithSecurityContext`, MockMvc |
| **Authentication flow** | Is a real password/token checked, rejected, and creating a session properly? | MockMvc `httpBasic()`, `formLogin()`, OIDC/JWT integration tests, browser E2E |
| **Business principal** | Does the app extract the right tenant/user ID from the principal? | `@WithUserDetails` with custom UserDetails; custom `@WithSecurityContext` |
| **Infrastructure** | Are SecurityFilterChain/CSRF/AuthenticationProvider actually running? | `@SpringBootTest`, `@AutoConfigureMockMvc`, integration tests |

Do not report a test as "login is secure" just because `@WithMockUser` returned HTTP 200.

## 3. Direct comparison of the three annotations

| Criterion | `@WithMockUser` | `@WithUserDetails` | `@WithSecurityContext` |
|---|---|---|---|
| Must the user exist? | No | **Yes**, must be loadable from `UserDetailsService` | Not required, depends on factory |
| Default principal | Spring Security `User` | `UserDetails` object returned by the service | Any object created by the factory |
| Typical Authentication | `UsernamePasswordAuthenticationToken` | `UsernamePasswordAuthenticationToken` | Up to you |
| How permissions are specified | `roles` or `authorities` in the annotation | From `UserDetails.getAuthorities()` | Factory builds authorities itself |
| Tests DB/UDS mapping? | No | Loads test data via UDS | Only if the factory does so |
| Tests real password? | No | **No** | **No**, unless the factory intentionally runs the flow |
| Fits custom principals? | Usually no | Yes, if UDS returns custom UserDetails | Yes, most flexible |
| Setup cost | Low | Needs ApplicationContext and UDS | Needs annotation + factory |
| Primary use case | Unit/slice authorization tests | Testing rules based on loaded user data | Testing tenants, custom principals, and special authentications |

**Quick rule of thumb:** if you only care about roles/permissions, choose `@WithMockUser`; if the application depends on `UserDetailsService` data, choose `@WithUserDetails`; if the principal/authentication has a custom structure, choose `@WithSecurityContext`.

## 4. @WithMockUser: fast and independent of the user repository

The annotation belongs to package:

~~~java
import org.springframework.security.test.context.support.WithMockUser;
~~~

Basic example:

~~~java
@Test
@WithMockUser
void hasDefaultUser() {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

    assertEquals("user", authentication.getName());
    assertTrue(authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
}
~~~

`@WithMockUser` with no parameters creates by default:
- username: `user`;
- password in mock user: `password` (belongs only to the test object; not checked against a DB);
- role: `ROLE_USER`;
- authentication type: `UsernamePasswordAuthenticationToken`.

**The user `user` does not need to exist in the database.** This is useful when testing authorization logic without initializing account records.

### 4.1. Custom username

~~~java
@Test
@WithMockUser(username = "alice")
void showsAlice() {
    assertEquals("alice",
        SecurityContextHolder.getContext()
            .getAuthentication().getName());
}
~~~

`value="alice"` is also a corresponding alias for username on this annotation.

### 4.2. `roles` and `authorities` are different

~~~java
@WithMockUser(username = "admin", roles = {"USER", "ADMIN"})
~~~

Equivalent to authorities `ROLE_USER` and `ROLE_ADMIN`. Spring applies the default role prefix `ROLE_`.

If you want permissions with literal names, use:

~~~java
@WithMockUser(username = "writer", authorities = {"docs:read", "docs:write"})
~~~

Here `ROLE_` is **not automatically added**. `hasAuthority("docs:write")` checks the exact string `docs:write`; `hasRole("ADMIN")` under default configuration requires `ROLE_ADMIN`.

**Do not configure `roles` and `authorities` together arbitrarily** to "cover both"; use one intentional form (or declare all authorities in the `authorities` list).

### 4.3. Common confusion

~~~java
// Role-based authorization:
.requestMatchers("/api/admin").hasRole("ADMIN")

// CORRECT test with role name:
@WithMockUser(roles = "ADMIN")

// If using authorities directly, must use the exact full string:
@WithMockUser(authorities = "ROLE_ADMIN")

// NOT equivalent to ROLE_ADMIN:
@WithMockUser(authorities = "ADMIN")
~~~

If a test gets 403 even though "ADMIN was set", check whether the code requires `hasRole("ADMIN")` or `hasAuthority("ADMIN")`. The two expressions mean different strings.

### 4.4. Class level and override

You can place the annotation on a class to apply across multiple tests:

~~~java
@WithMockUser(username = "tester", roles = "USER")
class ProfileTests {

    @Test
    void loggedInAsTester() { }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void testAdminOverride() { }

    @Test
    @WithAnonymousUser
    void anonymousScenario() { }
}
~~~

This illustrates class structure; JUnit/Spring Test setup and imports are needed if placed in a separate project. Use `@WithAnonymousUser` to override the class-level mock for negative tests. `@Nested` scenarios are supported per Spring Test's annotation mechanism.

### 4.5. When should you NOT use @WithMockUser?

- The controller casts `authentication.getPrincipal()` to a custom `TenantPrincipal` or `CustomUserDetails`; the default `User` principal does not match.
- You need to test loading a user from the repository or the real `enabled/locked/expired` policies of `UserDetailsService`.
- You need to test password hashing, `DaoAuthenticationProvider`, form login, JWT signatures, session fixation, OAuth2 callbacks, or WebAuthn assertions.
- You need to assert that the browser completed MFA/passkeys. A mock does not prove this.

`@WithMockUser` creates a **mocked authenticated context** without running any credential verification sequence.

## 5. @WithUserDetails: loading a user from UserDetailsService

Package:

~~~java
import org.springframework.security.test.context.support.WithUserDetails;
~~~

Example:

~~~java
@Test
@WithUserDetails("alice")
void usesStoredUserDetails() {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();
    assertEquals("alice", authentication.getName());
}
~~~

Unlike `@WithMockUser`, this annotation requires the Spring ApplicationContext to provide **at least one matching `UserDetailsService` bean**, and `loadUserByUsername("alice")` to return the requested user.

If the application has multiple `UserDetailsService` beans, specify the bean name:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "demoUsers")
void loadsFromNamedService() {
    // Principal is the exact object returned by demoUsers.
}
~~~

### 5.1. Does @WithUserDetails actually log in with a password?

**No.** The test listener calls `UserDetailsService` to fetch the principal and builds an already-authenticated authentication. It does not send a login request, does not call `PasswordEncoder.matches(raw, encoded)`, and does not run MFA. Therefore, it is suitable for testing:
- custom `UserDetails` with `tenantId`, `accountId`, and profile state;
- authorities loaded from test fixtures/repositories;
- business authorization using `UserDetails`;
- code reading `@AuthenticationPrincipal` or `SecurityContextHolder`.

If you want to verify right/wrong passwords, send **a real request** through the authentication filter in an integration test (section 11).

### 5.2. Fixture and bean lifecycle risks

- User not created yet: the listener may throw `UsernameNotFoundException` **before the test method runs**; `assertThrows` inside the method cannot catch this setup error.
- Multiple UDS beans without specifying `userDetailsServiceBeanName`: Spring may not know which bean to pick.
- Test context only has `@WebMvcTest` without importing/mocking UDS: the annotation cannot load the user.
- Data created in `@BeforeEach` may arrive **after** the default listener load point; use `setupBefore = TestExecutionEvent.TEST_EXECUTION` when appropriate.
- If UDS reads a real DB, fixtures must be isolated across tests, with proper transaction handling and cleanup.
- If UserDetails is cached, reset/invalidate state when tests change roles.

### 5.3. When the user is a custom UserDetails

Domain application example:

~~~java
public final class AccountUserDetails
        implements UserDetails {

    private final String username;
    private final long accountId;
    private final String tenantId;
    private final Collection<? extends GrantedAuthority> authorities;
    private final String passwordHash;

    // Constructor, getUsername/getPassword/getAuthorities,
    // isEnabled, and the required interface methods.
}
~~~

This is an **illustrative design skeleton**, not a standalone runnable Java file (constructors/method implementations omitted). If the real `UserDetailsService` returns `AccountUserDetails`, `@WithUserDetails` will carry the same principal type and enable business tests based on `accountId/tenantId`. The data placed in `SecurityContext` is still a **test identity** and does not prove password authentication.

## 6. @WithSecurityContext: taking control of Authentication and principal

`@WithSecurityContext` is a **meta-annotation** used to create a custom annotation, such as `@WithTenantUser`. It requires:
- An annotation with `@Retention(RUNTIME)`.
- A `factory=...class` attribute pointing to a class implementing `WithSecurityContextFactory<AnnotationType>`.
- The factory creates a **new** `SecurityContext` via `SecurityContextHolder.createEmptyContext()`.
- The factory builds the right `Authentication`: principal, credentials (no real secret needed in a mock), authorities, and authenticated status.
- Returning the context with the authentication attached.

Example usage in a test:

~~~java
@Test
@WithTenantUser(
    username = "alice",
    tenantId = "tenant-a",
    authorities = {"tenant:read"})
void verifiesTenantPrincipal() {
    // SecurityContext contains TenantPrincipal("alice", "tenant-a")
}
~~~

There is no built-in `@WithTenantUser` in Spring Security. It is a **project-defined annotation** built on `@WithSecurityContext`. Section 9 provides the full class, annotation, and factory.

### 6.1. When is a custom factory needed?

- Principal from JWT/OIDC has custom claims or roles.
- `Authentication` is not `UsernamePasswordAuthenticationToken`.
- The application requires `tenantId`, `organizationId`, `accountId`, `actorType`, or a custom permission set.
- A group of tests repeats the same combination of authorities/principal.
- You want to use `@Autowired` inside the factory to read fixtures/test beans (Spring Security supports Spring-managed factories).

**Avoid inflating confidence:** if the factory sets `isMfaVerified=true` or `JWT_AUTHENTICATED`, that is just test-fabricated data. It is used to test *post-authentication* policy, not to prove real OTP/JWT verification protocols are secure.

## 7. SecurityContext setup lifecycle in JUnit 5

The Spring Security Test listener prepares the context during Spring TestContext execution:

~~~text
beforeTestMethod (default)
    |
    +--> WithSecurityContextTestExecutionListener reads annotation
    +--> creates Authentication and SecurityContext
    v
JUnit @BeforeEach
    v
beforeTestExecution (if setupBefore=TEST_EXECUTION is chosen)
    |
    v
@Test method
    |
    v
@AfterEach and Spring TestContext cleanup
    |
    v
SecurityContextHolder is cleared for the next test
~~~

### 7.1. When is setupBefore needed?

Default:

~~~java
@WithMockUser(setupBefore = TestExecutionEvent.TEST_METHOD)
~~~

The context already exists when `@BeforeEach` runs. If a test creates a user in `@BeforeEach` and `@WithUserDetails` needs to load the user after that point, use:

~~~java
@WithUserDetails(
    value = "newlyCreatedUser",
    setupBefore = TestExecutionEvent.TEST_EXECUTION)
~~~

`TEST_EXECUTION` occurs after `@BeforeEach` and before the test method. Depending on the annotation/custom meta-annotation, `setupBefore` may also be configured via `@WithSecurityContext`.

**Important:** `@WithMockUser` creates the context before `@BeforeEach` by default; do not assume the test user only appears when entering the first line of `@Test`.

### 7.2. Do not share SecurityContext across threads arbitrarily

In the Servlet stack, `SecurityContextHolder` uses a ThreadLocal strategy by default. Tests using `@Async`, `CompletableFuture`, thread pools, or reactive WebFlux cannot assume context propagation across threads by default. Appropriate delegation/context propagation mechanisms or `ReactorContextTestExecutionListener` (for reactive security tests) are needed.

Never create a shared static `SecurityContext` across all tests; that makes tests order-dependent and can leak principals/authorities between tests.

## 8. Building a runnable test project with Java 17 and Spring Security 6.5

To compare all three annotations in the same test suite, we build a demo API:
- `GET /api/whoami`: requires login, returns the name and principal type.
- `GET /api/admin`: requires role `ADMIN`.
- `POST /api/docs`: requires authority `docs:write` and a CSRF token.
- `GET /api/tenant`: requires authority `tenant:read` **and** a custom `TenantPrincipal`.

The test project has **a `UserDetailsService` fixture** providing Alice and Bob. The test class uses all three annotations and compares them against real HTTP Basic requests.

### 8.1. Project structure

~~~text
security-annotations-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/securitytest/
    │   ├── SecurityTestDemoApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── ApiController.java
    │   └── TenantPrincipal.java
    └── test/java/com/example/securitytest/
        ├── TestUsersConfiguration.java
        ├── WithTenantUser.java
        ├── WithTenantUserSecurityContextFactory.java
        └── AuthenticationAnnotationsTest.java
~~~

The code below is compatible with JDK 17+, Spring Boot 3.5.x/Spring Security 6.5.x. The examples **do not connect to the Internet to authenticate**, call no external APIs, and need no database.

### 8.2. `pom.xml`: spring-security-test is an essential dependency

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>security-annotations-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

**Dependency distinctions:**
- `spring-boot-starter-security` provides the Spring Security runtime.
- `spring-security-test` provides `@WithMockUser`, `@WithUserDetails`, `@WithSecurityContext`, MockMvc post-processors `csrf`, `httpBasic`, `user`, and matchers.
- `spring-boot-starter-test` provides JUnit Jupiter, Spring Test, MockMvc, and common assertion libraries.
- Spring Boot parent/BOM manages compatible versions; do not force a Spring Security Test version different from the runtime.

### 8.3. Main class

File `src/main/java/com/example/securitytest/SecurityTestDemoApplication.java`:

~~~java
package com.example.securitytest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityTestDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTestDemoApplication.class, args);
    }
}
~~~

### 8.4. Real SecurityFilterChain for testing

File `src/main/java/com/example/securitytest/SecurityConfiguration.java`:

~~~java
package com.example.securitytest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .requestMatchers(
                                HttpMethod.POST, "/api/docs")
                            .hasAuthority("docs:write")
                        .requestMatchers(
                                HttpMethod.GET, "/api/tenant")
                            .hasAuthority("tenant:read")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

- `anyRequest().authenticated()` protects `GET /api/whoami`.
- `hasRole("ADMIN")` requires `ROLE_ADMIN` per the default role prefix.
- `hasAuthority("docs:write")` requires that exact string.
- `httpBasic()` only serves to test **real authentication** in the demo; production browser logins should choose an appropriate mechanism (session/OIDC/passkey).
- **CSRF protection remains enabled by default**. For POST, an authenticated test user is still rejected if missing a valid CSRF token.
- The demo does not design account persistence, production authorizations, or rate limiting; do not deploy it as a production authentication system.

### 8.5. Custom principal containing tenant

File `src/main/java/com/example/securitytest/TenantPrincipal.java`:

~~~java
package com.example.securitytest;

import java.security.Principal;

public record TenantPrincipal(
        String username,
        String tenantId) implements Principal {

    @Override
    public String getName() {
        return username;
    }
}
~~~

`TenantPrincipal` implements `java.security.Principal`, so `Authentication.getName()` can return `username` when `Authentication` holds this object as principal. It does not implement `UserDetails`, because the demo uses it as an identity after the test factory has created the authentication.

### 8.6. Controller receiving the authenticated Authentication

File `src/main/java/com/example/securitytest/ApiController.java`:

~~~java
package com.example.securitytest;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/whoami")
    public Map<String, String> whoami(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "principalType",
                authentication.getPrincipal().getClass().getSimpleName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("result", "admin-only");
    }

    @PostMapping("/docs")
    public Map<String, String> createDocument() {
        return Map.of("result", "document-created");
    }

    @GetMapping("/tenant")
    public Map<String, String> tenant(Authentication authentication) {
        if (!(authentication.getPrincipal()
                instanceof TenantPrincipal principal)) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Tenant principal required");
        }
        return Map.of(
                "name", principal.getName(),
                "tenantId", principal.tenantId());
    }
}
~~~

A production system should check tenant/resource at the service/repository layer using the authenticated ID. The demo controller only demonstrates **access permissions and principal type**, not a complete implementation of multi-tenant authorization.

### 8.7. Real test fixture with UserDetailsService

File `src/test/java/com/example/securitytest/TestUsersConfiguration.java`:

~~~java
package com.example.securitytest;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@TestConfiguration(proxyBeanMethods = false)
public class TestUsersConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean("demoUsers")
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        var alice = User.withUsername("alice")
                .password(encoder.encode("local-only-alice-password"))
                .authorities("ROLE_USER", "docs:write")
                .build();

        var bob = User.withUsername("bob")
                .password(encoder.encode("local-only-bob-password"))
                .authorities("ROLE_ADMIN", "docs:read")
                .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
~~~

This is **fake data in test sources**:
- Alice has `ROLE_USER`, `docs:write`.
- Bob has `ROLE_ADMIN`, `docs:read`.
- Both have passwords hashed via `PasswordEncoder` so HTTP Basic tests can perform **real password verification**.
- `@WithUserDetails` loads the principal from the bean named `demoUsers`, but **does not call matches**.
- The class resides under `src/test` and must not be used as a production identity service.

**Reason for declaring the bean name:** avoids ambiguity when the application has multiple `UserDetailsService` beans. Tests use `@Import(TestUsersConfiguration.class)` to load the fixture into the ApplicationContext.

## 9. Creating a custom @WithSecurityContext with TenantPrincipal

### 9.1. Defining the annotation

File `src/test/java/com/example/securitytest/WithTenantUser.java`:

~~~java
package com.example.securitytest;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.test.context.support.WithSecurityContext;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(
        factory = WithTenantUserSecurityContextFactory.class)
public @interface WithTenantUser {

    String username() default "tenant-user";

    String tenantId() default "tenant-a";

    String[] authorities() default {"tenant:read"};
}
~~~

### 9.2. Factory building a fresh SecurityContext

File `src/test/java/com/example/securitytest/WithTenantUserSecurityContextFactory.java`:

~~~java
package com.example.securitytest;

import java.util.Arrays;
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public class WithTenantUserSecurityContextFactory
        implements WithSecurityContextFactory<WithTenantUser> {

    @Override
    public SecurityContext createSecurityContext(
            WithTenantUser annotation) {

        TenantPrincipal principal = new TenantPrincipal(
                annotation.username(), annotation.tenantId());

        List<GrantedAuthority> authorities =
                Arrays.stream(annotation.authorities())
                    .map(name ->
                        (GrantedAuthority) new SimpleGrantedAuthority(name))
                    .toList();

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        principal, null, authorities);

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
~~~

Points to verify:
- `WithSecurityContextFactory<WithTenantUser>` matches the annotation's generic type.
- The factory is referenced by `@WithSecurityContext(factory=...)`; it **is not a runtime AuthenticationProvider**.
- A fresh context is created for each test; static contexts are never reused.
- Credentials are set to `null`; never fabricate fake secret passwords/tokens and accidentally log them.
- Authorities come from the test annotation, so the test **only proves authorization after identity has been established**.
- `TenantPrincipal` is a real object with `username` and `tenantId`, so the controller can check `instanceof TenantPrincipal`.

A factory can use Spring dependency injection when fixture data is needed, though the more a test depends on external backends/data stores the more it should be classified as an integration test; avoid having factories call external systems.

## 10. JUnit 5 + MockMvc: testing the three annotations and real login

File `src/test/java/com/example/securitytest/AuthenticationAnnotationsTest.java`:

~~~java
package com.example.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestUsersConfiguration.class)
class AuthenticationAnnotationsTest {

    @Autowired
    MockMvc mvc;

    @Test
    void noAuthenticationReturns401() throws Exception {
        mvc.perform(get("/api/whoami")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithAnonymousUser
    void anonymousOverrideReturns401() throws Exception {
        mvc.perform(get("/api/whoami")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void defaultMockUserHasUsernameUser() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("user"))
            .andExpect(jsonPath("$.principalType").value("User"));
    }

    @Test
    @WithMockUser(username = "root", roles = "ADMIN")
    void mockAdminHasRole() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("admin-only"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void mockOrdinaryUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "docs:write")
    void customAuthorityCanCreateDocument() throws Exception {
        mvc.perform(post("/api/docs").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value(
                    "document-created"));
    }

    @Test
    @WithMockUser(authorities = "docs:write")
    void missingCsrfIsStillRejected() throws Exception {
        mvc.perform(post("/api/docs"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithUserDetails(
            value = "alice",
            userDetailsServiceBeanName = "demoUsers")
    void userDetailsComesFromRealService() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.principalType").value("User"));

        mvc.perform(post("/api/docs").with(csrf()))
            .andExpect(status().isOk());
    }

    @Test
    @WithUserDetails(
            value = "bob",
            userDetailsServiceBeanName = "demoUsers")
    void loadedAdminPermissionsAreApplied() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk());
    }

    @Test
    @WithTenantUser(
            username = "alice",
            tenantId = "tenant-a",
            authorities = {"tenant:read"})
    void customSecurityContextProvidesTenantPrincipal()
            throws Exception {
        mvc.perform(get("/api/tenant"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.tenantId").value("tenant-a"));
    }

    @Test
    @WithMockUser(authorities = "tenant:read")
    void roleIsNotEnoughWithoutCustomPrincipal()
            throws Exception {
        mvc.perform(get("/api/tenant"))
            .andExpect(status().isForbidden());
    }

    @Test
    void realHttpBasicPasswordIsVerified() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic(
                    "alice", "local-only-alice-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void wrongHttpBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("alice", "incorrect")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

### 10.1. What does each test prove?

| Test | Mechanism | Meaning |
|---|---|---|
| No annotation | Anonymous/no credentials | Protected endpoint returns 401 |
| `@WithAnonymousUser` | Anonymous test context | Overrides authenticated context when needed |
| Default `@WithMockUser` | Mock context | Default username/role work |
| Mock admin | `roles="ADMIN"` | `hasRole("ADMIN")` returns 200 |
| Mock USER | Missing admin role | `hasRole` denies with 403 |
| Mock `docs:write` + CSRF | Authority + token | With permission and CSRF, POST returns 200 |
| Mock `docs:write` without CSRF | Authority but missing CSRF | POST returns 403, filter is not skipped |
| `@WithUserDetails("alice")` | UserDetailsService bean | Principal and permissions loaded from fixture |
| `@WithUserDetails("bob")` | Role loaded from fixture | Bob has `ROLE_ADMIN` |
| `@WithTenantUser` | Custom factory | TenantPrincipal and tenant ID are accurate |
| Mock user with tenant authority | Wrong principal type | Controller denies with 403 |
| HTTP Basic right password | Real filter/provider | Password hash is verified |
| HTTP Basic wrong password | Real filter/provider | Wrong credentials return 401 |

The strength of this matrix is **placing synthetic authentication side-by-side with actual credential authentication**. It clearly shows when a MockMvc 200 comes from a mock-user annotation versus an unannotated HTTP Basic request that must pass password verification.

### 10.2. Running the project

Requires JDK 17+ and Maven:

~~~bash
mvn clean test
~~~

**Expected:** JUnit Jupiter runs **13 test methods**, with zero failures/errors; corresponding surefire reports are under `target/surefire-reports/`. Tests require no browser, running server, or PostgreSQL. Elapsed time and cache paths depend on the Maven environment; there is no fixed byte-for-byte stdout for the `mvn test` command.

The assumption here is that the Maven/Spring Boot 3.5.x configuration and dependencies were downloaded successfully. When using a different Boot/Security version, check the Javadoc and behavior of that version rather than copying configuration mechanically.

### 10.3. Why do the tests use @SpringBootTest?

`@SpringBootTest` initializes the full ApplicationContext, including `SecurityFilterChain`, controllers, and the test `UserDetailsService`. `@AutoConfigureMockMvc` creates MockMvc with filters. `@Import(TestUsersConfiguration.class)` loads the test fixture.

With `@WebMvcTest(ApiController.class)`, Spring initializes only **a slice**; you must import/mock beans required by the controller/security, and verify the filter chain is not bypassed. Do not set `@AutoConfigureMockMvc(addFilters = false)` and then conclude "security allows it" from HTTP 200: disabling filters can strip out the very authorization/CSRF you intend to test.

### 10.4. Why choose HTTP Basic as the control baseline?

HTTP Basic easily triggers a real authentication request in MockMvc:

~~~java
mvc.perform(get("/api/whoami")
        .with(httpBasic("alice", "local-only-alice-password")))
    .andExpect(status().isOk());

mvc.perform(get("/api/whoami")
        .with(httpBasic("alice", "wrong")))
    .andExpect(status().isUnauthorized());
~~~

In this demo model, `httpBasic()` builds the appropriate Authorization header, `BasicAuthenticationFilter` calls the authentication manager/provider, and `PasswordEncoder` checks the password. That is **an important part of a real authentication flow**; however, it does not test form login, form CSRF, session fixation, OTP, OAuth2, or WebAuthn.

If the application uses form login, you can use `spring-security-test`'s `formLogin()` helper, **provided `.formLogin(...)` is configured in SecurityFilterChain**. Do not mix the `formLogin` helper with an application supporting only Basic and expect form login to work automatically.

## 11. Standalone Java 17 example: why role differs from authority

The following program has no Spring dependency to demonstrate **the permission string** being checked. It does not replace Spring's AuthorizationManager, but helps prevent confusion when writing test annotations.

File `AuthorityNameDemo.java`:

~~~java
import java.util.Set;

public final class AuthorityNameDemo {
    static boolean hasRole(Set<String> authorities, String role) {
        return authorities.contains("ROLE_" + role);
    }

    static boolean hasAuthority(
            Set<String> authorities, String authority) {
        return authorities.contains(authority);
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of(
                "ROLE_ADMIN", "docs:write");

        System.out.println("hasRole ADMIN="
                + hasRole(granted, "ADMIN"));
        System.out.println("hasAuthority ADMIN="
                + hasAuthority(granted, "ADMIN"));
        System.out.println("hasAuthority ROLE_ADMIN="
                + hasAuthority(granted, "ROLE_ADMIN"));
        System.out.println("hasAuthority docs:write="
                + hasAuthority(granted, "docs:write"));
    }
}
~~~

Command:

~~~bash
javac AuthorityNameDemo.java
java AuthorityNameDemo
~~~

**Exact stdout:**

~~~text
hasRole ADMIN=true
hasAuthority ADMIN=false
hasAuthority ROLE_ADMIN=true
hasAuthority docs:write=true
~~~

This snippet **intentionally models Spring Security's default role prefix**. If the application customizes the role prefix, actual rules may differ. Names like `docs:write` are system-defined authorities, not a set of scopes automatically granted by Spring from the client side.

## 12. Method Security: testing @PreAuthorize with the same annotations

The three annotations are also useful when testing methods protected by `@PreAuthorize`, not only HTTP endpoints. Service example:

~~~java
@Service
public class ReportService {
    @PreAuthorize("hasAuthority('reports:read')")
    public String readReport() {
        return "report";
    }
}
~~~

This is an **illustrative code snippet**, not a standalone Java file; `@Service`, `@PreAuthorize`, and `@EnableMethodSecurity` on configuration must be imported/enabled.

Testing:

~~~java
@Test
@WithMockUser(authorities = "reports:read")
void canReadReport() {
    assertEquals("report", reportService.readReport());
}

@Test
@WithMockUser(roles = "USER")
void missingReportPermissionIsDenied() {
    assertThrows(AccessDeniedException.class,
            () -> reportService.readReport());
}
~~~

Notes:
- Ensure the service is obtained **through a Spring bean/proxy**; `new ReportService()` will not have the method security interceptor.
- `@EnableMethodSecurity` is enabled in the test ApplicationContext.
- Permission checks only actually run if the annotation and proxy are applied.
- `@WithMockUser` does not create an account in the DB; method security only looks at the Authentication built by the listener.
- For permissions depending on real user/tenant data, use `@WithUserDetails` or a custom context + suitable fixture.

## 13. MockMvc post-processors vs. annotations

Within a single test, you may avoid class-level annotations and attach an identity to **a single HTTP request**:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.*;

mvc.perform(get("/api/admin").with(user("bob").roles("ADMIN")))
    .andExpect(status().isOk());
~~~

`user("bob").roles("ADMIN")` attaches a mock identity to a specific MockMvc request; `@WithMockUser` prepares `SecurityContext` for the test lifecycle. Which one fits depends on whether you are configuring multiple requests or a single request.

### 13.1. When testing multiple actors in one method

~~~java
mvc.perform(get("/api/admin")
        .with(user("alice").roles("USER")))
    .andExpect(status().isForbidden());

mvc.perform(get("/api/admin")
        .with(user("bob").roles("ADMIN")))
    .andExpect(status().isOk());
~~~

This is a clear approach when two principals are needed in **the same test**. You do not need to put `@WithMockUser` twice on one method.

### 13.2. Manually built MockMvc needs apply(springSecurity())

~~~java
MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .build();
~~~

Requires static import from `SecurityMockMvcConfigurers.springSecurity`. Calling `apply(springSecurity())` registers security filters and test post-processors so annotations/context interact properly with MockMvc. If you use Spring Boot's `@AutoConfigureMockMvc`, you do not need to rewrite this block.

### 13.3. @WithMockUser does not provide a CSRF token

Even when the test is already authenticated:

~~~java
@Test
@WithMockUser(authorities = "docs:write")
void csrfMatters() throws Exception {
    mvc.perform(post("/api/docs"))
        .andExpect(status().isForbidden());

    mvc.perform(post("/api/docs").with(csrf()))
        .andExpect(status().isOk());
}
~~~

A CSRF token **is not an access permission**. Conversely, `.with(csrf())` does not automatically create a principal or authority; if the user lacks permission, the request is still denied. These are two independent protection layers in a session-based web application.

## 14. Complex custom Authentication scenarios

### 14.1. JWT Resource Server

If the real application uses JWT access tokens, authentication is typically `JwtAuthenticationToken` along with issuer/audience/scope validation. `@WithMockUser(authorities="SCOPE_orders:read")` may work to test a `hasAuthority` rule, but:
- does not verify the JWT signature;
- does not check `iss`, `aud`, `exp`, `nbf`;
- does not prove the token converter maps scopes correctly;
- does not accurately simulate custom claim/tenant logic.

For a MockMvc Resource Server, use the `jwt()` request post-processor to test principals/claims/authorities at the web layer. For real JWT verification, write integration tests passing through the configured `JwtDecoder`, using trusted issuer/JWK test fixtures. Both test layers must be named clearly.

### 14.2. OAuth2 Login / OIDC

`@WithMockUser` does not turn the principal into an `OAuth2User` or `OidcUser`. If a controller requires an `OidcUser`, use `oidcLogin()` or `oauth2Login()` in MockMvc to establish the appropriate OAuth2 authentication, or a custom `@WithSecurityContext` when a specialized principal is needed.

To test the real Authorization Code Flow, state/nonce, ID Token signature, UserInfo, and redirect callbacks, IdP/test Authorization Server integration tests are required. Use mock annotations to test **post-login** authorization without concluding the entire OIDC flow is secure.

### 14.3. Pre-authentication or service accounts

An application may use `PreAuthenticatedAuthenticationToken` or a custom Authentication type to hold service identity. `@WithSecurityContext` can create that token type and corresponding principal; however, **trusted proxy/mTLS/header sanitization** must be tested in a separate integration layer to prove forged headers from the Internet are not accepted.

### 14.4. WebAuthn/passkeys

A mock authentication with `method="WEBAUTHN"` does not prove the authenticator signed the challenge or that the server checked `origin`, RP ID, and public key. To test passkey ceremonies, a WebAuthn verifier and corresponding test fixtures/E2E browser tests are needed. `@WithSecurityContext` only helps test logic **after** an assumed principal has authenticated.

## 15. @WithUserDetails and time-varying test data

### 15.1. Tests creating users in @BeforeEach

If `@BeforeEach` seeds user `alice` into the DB and `@WithUserDetails("alice")` loads before it by default, setup may fail. An intentional configuration:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    setupBefore = TestExecutionEvent.TEST_EXECUTION)
void accountLoadedAfterBeforeEach() {
    // Test data from @BeforeEach has already been created.
}
~~~

Requires importing `org.springframework.security.test.context.support.TestExecutionEvent`. This only solves **the ordering of SecurityContext preparation**, not transaction isolation between `@BeforeEach` and the test method; that depends on the Spring Test transaction lifecycle and data source.

### 15.2. A real UserDetailsService bean can return a custom principal

If the real application's UDS returns `CustomAccountUserDetails` (extending/implementing `UserDetails`), using `@WithUserDetails` helps test:
- accurate extraction of account ID/tenant ID from the principal;
- `GrantedAuthority` mapping per domain roles;
- proper loading of account state and flags;
- accurate data extraction by downstream services/SpEL expressions.

**However**, the annotation can bypass login provider checks such as passwords, MFA, or rejecting `disabled/locked` accounts in the real authentication flow. Test those states with separate authentication integration tests.

### 15.3. Be careful when changing roles between two tests

One test granting `ROLE_ADMIN` to Alice in the DB and the next test expecting Alice to be `ROLE_USER` may fail if:
- data cleanup has not run;
- the UDS cache has not been invalidated;
- context from the previous test was improperly reused;
- tests run in parallel on the same DB fixture.

Resolve this with isolated data/test transactions, explicit state resets, and never using a mutable singleton authentication as a fixture.

## 16. Positive and negative tests must go together

Having only `@WithMockUser(roles="ADMIN")` and asserting 200 is not enough, because the endpoint might be **accidentally open to every user**. At minimum, you need:

~~~text
Unauthenticated GET /api/admin → 401
USER role GET /api/admin       → 403
ADMIN role GET /api/admin      → 200
Valid token but wrong tenant   → 403
POST missing CSRF              → 403 (if CSRF enabled)
POST with permission + CSRF    → 200
~~~

### Recommended testing matrix

| Scenario | Annotation/tool | Verification |
|---|---|---|
| Anonymous hitting protected endpoint | No annotation / `@WithAnonymousUser` | 401 or login redirect per entry point |
| Mock USER accessing ADMIN | `@WithMockUser(roles="USER")` | 403 |
| Mock ADMIN accessing ADMIN | `@WithMockUser(roles="ADMIN")` | 200 |
| Wrong `authorities` for role | `@WithMockUser(authorities="ADMIN")` | Does not pass `hasRole("ADMIN")` |
| Has `docs:write` | `@WithMockUser(authorities="docs:write")` | Rule matches |
| Has role but missing CSRF | Mock user + POST without `csrf()` | 403 |
| Has role and CSRF | Mock user + `csrf()` | 200 |
| Real user from fixture | `@WithUserDetails("alice")` | Authorities from UDS |
| Missing fixture user | `@WithUserDetails("missing")` | Setup error, not HTTP 401 |
| Multiple UserDetailsServices | Annotation with `userDetailsServiceBeanName` | Picks the right bean |
| Custom principal with right tenant | `@WithTenantUser` | Body and authorization succeed |
| Missing custom principal | `@WithMockUser(authorities="tenant:read")` | Cannot fake TenantPrincipal |
| Right real password | `httpBasic("alice", goodPassword)` | 200 via BasicAuthenticationFilter |
| Wrong real password | `httpBasic("alice", badPassword)` | 401 |
| Mock JWT claim | `jwt()`/mock context | Policy works with mock claims |
| Invalid JWT signature | Decoder integration test | Token rejected |
| Disabled/locked UserDetails | Integration test through provider | Auth denied |
| Expired session | Browser/MockMvc session test | Access no longer allowed |
| Authentication context test isolation | Consecutive JUnit tests | Principal does not leak between tests |
| `@PreAuthorize` missing permission | Spring bean/proxy + annotation | AccessDeniedException |
| Factory creates different principal type | Custom `@WithSecurityContext` | Controller handles or denies properly |

HTTP codes are not always identical to the example: with form login, an unauthenticated request may **302 redirect** to the login page instead of 401; with Basic/Bearer APIs, it usually returns 401. Assert statuses according to the actual `AuthenticationEntryPoint`, rather than forcing 401 on every architecture.

## 17. Common errors and diagnosis

### Error 1: "UserDetailsService not found" or user not found

Causes:
- Test context lacks a `UserDetailsService` bean.
- Test configuration not imported in `@WebMvcTest`.
- Typo in `value` username.
- Multiple UDS beans without `userDetailsServiceBeanName`.
- User seeded after the listener reads it.

Resolution: inspect the ApplicationContext and bean names; use `setupBefore=TEST_EXECUTION` if the fixture is created in `@BeforeEach`; never add another mock user to hide the bug being tested.

### Error 2: ClassCastException when reading custom principal

`@WithMockUser` creates a Spring Security `User` principal, not `CustomAccountUserDetails` or `TenantPrincipal`. Choose `@WithUserDetails` if UDS returns a custom user, or a `@WithSecurityContext` factory to construct the right principal.

### Error 3: `@WithMockUser` is present but MockMvc request still returns 401

Possible causes:
- Manually built MockMvc missing `.apply(springSecurity())`.
- Security filters/listeners not properly integrated.
- Test dispatches the request on a different thread/async.
- Application handler requires a different authentication type/claim.
- Test slice omits SecurityConfig or replaces the security chain.

Do not fix by disabling filters; verify the security test integration mechanism.

### Error 4: Has permission yet POST returns 403

Check the CSRF token with `.with(csrf())`. If CSRF is already provided and it still returns 403, check exact authorities, `@PreAuthorize`, object-level permissions, tenant policies, and entry points/exception handling.

### Error 5: `roles="ADMIN"` but rule requires `hasAuthority("ADMIN")`

`roles="ADMIN"` creates `ROLE_ADMIN`, while `hasAuthority("ADMIN")` requires `ADMIN`. Use `roles` or `authorities` per the contract; do not alter production policy just to make a test pass if the original rule is right.

### Error 6: `@WithUserDetails` test passes so login is concluded to pass

Wrong conclusion: the annotation **does not verify passwords**. Add real request tests going through the filter/provider, including wrong passwords, disabled/locked accounts, sessions, and MFA if present.

### Error 7: Factory builds Authentication with arbitrary authorities

This is normal in **authorization unit tests**, but does not prove a real user would ever be granted those authorities. Separate tests are needed for role mapping from DB/JWT/IdP.

### Error 8: Using static SecurityContextHolder across multiple threads

The default context is thread-bound; async tasks may miss the context or get the wrong one if propagation is uncontrolled. Tests must verify proper thread/context strategies and delegation mechanisms, cleaning up the context after every test.

### Error 9: Isolated test PASSES but full suite FAILS

May be due to user fixture state, cached ApplicationContext, mutable repositories, context leakage, parallel test execution, or DB cleanup. Use isolated fixtures and avoid mutating global data.

### Error 10: Testing only admin success with no negative cases

A route accidentally open to all users still makes an admin-success test PASS. Always include anonymous/user-without-authority tests.

## 18. Comprehensive login testing strategy

Tests should generally be split into four layers:

### Layer A — Authorization unit logic

Use `@WithMockUser` / `@WithSecurityContext` in Spring TestContext to test service `@PreAuthorize`, tenant policies, and application-defined conditions. No real passwords/tokens need to be issued.

### Layer B — Web/security slice

Use MockMvc with the filter chain, `@WithMockUser`, `@WithUserDetails`, `@WithAnonymousUser`, and `csrf()`. Verify URLs, HTTP methods, statuses, and request authorization. The demo in section 10 sits primarily at this layer.

### Layer C — Authentication integration

Do not use mock annotations in these tests; invoke `httpBasic`, `formLogin`, or resource-server/SSO flows with controlled fixtures, and verify:
- PasswordEncoder/DaoAuthenticationProvider.
- UserDetailsService/locked/disabled/expired.
- JWT issuer/audience/signature/expiry or IdP callbacks.
- Session fixation, logout, cookies/CSRF.
- Real MFA/reauthentication/step-up.

### Layer D — End-to-end browser and system

Test browsers/IdP/gateways, HTTPS, redirects, CORS/CSRF, session cookies, passkeys/WebAuthn, and network trust boundaries. No Java annotation can replace these checks.

**Interpret test results by their proper layer.** When reporting "authorization test PASS", do not say "the entire login mechanism has been tested" without authentication integration/E2E tests.

## 19. Checklist before completing the module

- [ ] `spring-security-test` dependency is in test scope and matches Spring Security runtime.
- [ ] Spring TestContext/JUnit 5 and the SecurityContext test listener are present.
- [ ] MockMvc includes the filter chain; if built manually, `.apply(springSecurity())` is applied.
- [ ] `@WithMockUser` only creates a mock user; default username/role are properly understood.
- [ ] `roles` (adds `ROLE_`) is distinguished from `authorities` (kept verbatim).
- [ ] `@WithUserDetails` loads the right `UserDetailsService` bean and username.
- [ ] `@WithUserDetails` is never mistaken for password authentication.
- [ ] Custom `@WithSecurityContext` has `@Retention(RUNTIME)` and a matching generic factory.
- [ ] The factory creates a fresh context with accurate principal/authentication/authorities.
- [ ] Custom principals are consumed with the proper type in controllers/services.
- [ ] `setupBefore=TEST_EXECUTION` is used if fixtures are created in `@BeforeEach`.
- [ ] `SecurityContext` does not leak across tests or threads.
- [ ] Positive + negative tests include 401/403/200, missing permissions, and missing CSRF.
- [ ] Real password/token tests pass through filters/providers in a separate integration layer.
- [ ] Real JWT/OIDC/WebAuthn tests do not merely inject fake claims/roles and claim verification.
- [ ] SecurityFilterChain is not omitted and CSRF is not disabled just to make tests pass.
- [ ] `@WebMvcTest`/bean import failures are inspected rather than masked by test configs hiding production bugs.
- [ ] Production passwords/tokens are never placed into test logs or fixtures.
- [ ] Business authorization tests cover tenant/object level, not just roles.
- [ ] The test suite runs via `mvn clean test` and CI preserves reports for review.

## 20. Key takeaways

- **`@WithMockUser`:** creates a quick mock identity to test authorization. Does not require the user to exist and does not verify passwords.
- **`@WithUserDetails`:** uses a user loaded by `UserDetailsService`, ideal when principal/authorities depend on data; still skips login/password verification.
- **`@WithSecurityContext`:** builds custom annotations/factories for custom principals and Authentications. Very flexible, yet still a test-constructed context.
- **`roles="ADMIN"` differs from `authorities="ADMIN"`:** roles default to the `ROLE_` prefix.
- **`@WithMockUser` does not grant CSRF:** POST requests must still obey the security chain.
- **Testing real login** requires sending credentials through mechanisms like HTTP Basic/form login or integrating an IdP/token verifier, never using annotations to bypass verification.

These three annotations help test **"given principal X, does the application behave properly?"**. The question **"was principal X actually authenticated properly?"** requires a separate group of tests.

## 21. References

1. [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): official guide on `@WithMockUser`, `@WithUserDetails`, `@WithSecurityContext`, custom factories, and `setupBefore`.
2. [Spring Security 6.5 — MockMvc Security Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): SecurityFilterChain integration and `springSecurity()`.
3. [Spring Security 6.5 — MockMvc Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html): `user()`, annotation-based request identity, and custom authentication.
4. [Spring Security 6.5 — MockMvc Request PostProcessors](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/request-post-processors.html): `csrf()`, `httpBasic()`, `formLogin()`, `jwt()`, `oauth2Login()`, `oidcLogin()`.
5. [Spring Security 6.5 — @WithMockUser API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithMockUser.html): username, roles, authorities, setupBefore.
6. [Spring Security 6.5 — @WithUserDetails API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithUserDetails.html): userDetailsServiceBeanName and test listener.
7. [Spring Security 6.5 — @WithSecurityContext API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithSecurityContext.html): metadata and factory.
8. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and service-layer permission control.
9. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, web slices, and test configuration.
10. [Spring Security 6.5 — Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html): overview of Spring Security Test tools.
