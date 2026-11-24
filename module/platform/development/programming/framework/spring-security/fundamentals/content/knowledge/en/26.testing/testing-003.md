# @WithMockUser, @WithAnonymousUser, and Identities Used in Spring Security Testing

> **Scope:** Spring Security fundamentals, **Testing** section. This lesson shows how to create test identities with `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, and Spring Security Test `RequestPostProcessor`s; test anonymous, authenticated, role/authority, method security, and the limits of mocks. Examples use **Java 17, Spring Boot 3.3.x, Spring Security 6.x, JUnit 5, MockMvc (Servlet/Spring MVC)**. The WebFlux differences are distinguished at the end.

## 1. Why does each test need its own identity?

In a secured application, the same URL or method can produce different outcomes depending on the caller:

- **Anonymous**: not logged in; usually required to authenticate when accessing private resources.
- **Authenticated, insufficient permissions**: authenticated, but lacks the required authority, usually receiving 403.
- **Authenticated, sufficient permissions**: permitted to execute the controller/service and receive the business result.
- **Custom principal**: carries not only a username, but also a tenant ID, customer ID, or profile details needed by business logic.

To test authorization rules, we need to establish a reliable `Authentication` in the **test environment**. Spring Security Test provides annotations and request post-processors for this without writing a login UI or hitting a user store in every test.

**Important limitation:** a *simulated* identity is an input to authorization checks; it **does not prove that password, JWT, OAuth2, or cookie authentication actually works**. To test real authentication, send credentials/tokens through the corresponding mechanism and verify the real filter/provider/decoder.

## 2. Foundations: SecurityContext, Authentication, and principal

Once a request is authenticated in a Servlet application, Spring Security normally places an `Authentication` into `SecurityContext`, and `SecurityContextHolder` exposes it during the request flow. An `Authentication` contains:

| Property | Example | Effect in tests |
| --- | --- | --- |
| `principal` | `UserDetails`, JWT claims, domain object | Represents the identity; its type affects code using `@AuthenticationPrincipal` |
| `name` | `"mai"` | Can be used in ownership checks |
| `authorities` | `ROLE_ADMIN`, `SCOPE_docs.read` | Direct input to `hasRole`/`hasAuthority` |
| `credentials` | Password or dummy value in tests | With mocks, not a credential verified by the backend |
| `authenticated` | State defined by Spring Security | Do not rely on this flag alone to detect anonymous in every situation |

During test execution, `spring-security-test`'s `WithSecurityContextTestExecutionListener` sets up and clears `SecurityContextHolder` according to annotations before and after tests. With standard `@SpringBootTest`/Spring Test, the listener integrates with Spring Test automatically; there is no need to write `ThreadLocal` code or manage state manually between tests.

**Note:** `AnonymousAuthenticationToken` is also an `Authentication` and may have `isAuthenticated() == true` depending on how the implementation sets the flag. Use `authenticated()`, `isAuthenticated()` in Spring Security expressions, or an appropriate `AuthenticationTrustResolver` to distinguish anonymous callers rather than inferring it from a single flag.

### Why use mocks instead of real login in every test?

- Test URL/method rules quickly and independently of real usernames/passwords.
- Easily construct many roles, scopes, and boundary identities.
- Avoid depending on an IdP, database, or token signing keys in focused authorization unit/integration tests.
- When a test requires an exact principal type or a real login flow, more specialized tools are available.

Still, you need **a separate layer of tests for the real authentication mechanism**. For example: testing HTTP Basic with right/wrong passwords; testing JWTs with a decoder/key; testing form login and session/CSRF handling; or testing OAuth2 callbacks or token exchanges within the scope you need to verify.

## 3. @WithMockUser: setting up a mock identity for tests

`@WithMockUser` belongs to `org.springframework.security.test.context.support`. It can be placed on a test method or class. The annotation creates a `SecurityContext` containing a `UsernamePasswordAuthenticationToken` whose principal is normally a Spring Security `User`.

Default configuration:

```java
@Test
@WithMockUser
void runsAsDefaultUser() {
    // username = "user"
    // password in principal = "password" (mock value)
    // authorities = ["ROLE_USER"]
}
```

This is a JUnit 5 **fragment** requiring `@Test` and `@WithMockUser` imports; it is not a standalone file.

Customizing username and roles:

```java
@Test
@WithMockUser(username = "mai", roles = {"USER", "ADMIN"})
void runsAsMaiWithTwoRoles() {
    // name = "mai"
    // authorities = ROLE_USER, ROLE_ADMIN
}
```

**Roles are not the same as authorities:**

- `@WithMockUser(roles = "ADMIN")` creates the `ROLE_ADMIN` authority under the default prefix convention.
- `@WithMockUser(authorities = "SCOPE_docs.read")` preserves the **exact string** `SCOPE_docs.read`, without adding `ROLE_`.
- `hasRole("ADMIN")` checks `ROLE_ADMIN` under the default role-prefix configuration.
- `hasAuthority("SCOPE_docs.read")` checks the exact string `SCOPE_docs.read`.
- When specifying `authorities`, do not simultaneously configure `roles` in a conflicting way. If you want both roles and scopes, pass them together in `authorities = {"ROLE_ADMIN", "SCOPE_docs.read"}`.
- Do not pass `roles = "ROLE_ADMIN"` trying to double-prefix; with `roles`, pass the role name without `ROLE_`.

Example setting authorities accurately:

```java
@Test
@WithMockUser(
    username = "reader",
    authorities = {"ROLE_READER", "SCOPE_docs.read"}
)
void hasRoleAndScope() {
    // Has both ROLE_READER and SCOPE_docs.read.
}
```

**No password verification occurs just because you set `@WithMockUser(password = "...")`.** Even if you pass an invalid password, the test still receives an authenticated mock identity. The `password` attribute populates the test principal, not an input checked by `PasswordEncoder.matches` or an `AuthenticationProvider`.

## 4. @WithAnonymousUser: testing when unauthenticated

`@WithAnonymousUser` also belongs to `org.springframework.security.test.context.support`. It creates an anonymous environment; in a test context, Spring Security uses `AnonymousAuthenticationToken`.

```java
@Test
@WithAnonymousUser
void anonymousCannotViewPrivatePage() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isUnauthorized());
}
```

This is a fragment: `mvc` must be a `MockMvc` integrated with Spring Security, and the route and HTTP Basic entry point must be configured accordingly. 401 is the expectation of the **example configuration below**, not every anonymous app behavior; form login may redirect with 302.

### Overriding a class-level default identity

You can place `@WithMockUser` at the class level so most tests run under a simulated account, then override it on a specific test:

```java
@WithMockUser(username = "staff", roles = "USER")
class ExampleIdentityTests {

    @Test
    void authenticatedByDefault() {
        // Runs as staff / ROLE_USER.
    }

    @Test
    @WithAnonymousUser
    void explicitlyAnonymous() {
        // This method uses anonymous instead of staff.
    }
}
```

This snippet only illustrates **annotation scope**; add real test classes/methods and Spring Test configuration when applying it. Method-level annotations take precedence for that method. Explicit test annotations help avoid accidentally testing public resources as an authenticated user.

### Anonymous is not the same as USER role

Do not assume anonymous has `ROLE_USER` or resource access merely because the security context holds a token. With `@WithAnonymousUser`, test `permitAll`, `authenticated`, `hasRole` resources, and the application's login challenge behavior explicitly.

## 5. Runnable example: Spring Boot 3.3 + MockMvc + Method Security

The following example uses HTTP Basic to test real credentials alongside mock annotations. It exposes four resources:

- `GET /api/public` is accessible to everyone.
- `GET /api/me` requires authentication and returns `Authentication.getName()`.
- `GET /api/admin` allows only `ROLE_ADMIN`.
- `GET /api/scoped` requires authority `SCOPE_docs.read` via `@PreAuthorize`.

Each path clearly separates **authentication**, **URL-level authorization**, and **method-level authorization**.

### 5.1 Project structure

```text
security-test-identities/
├── pom.xml
└── src/
    ├── main/java/com/example/securitytest/
    │   └── SecurityTestDemoApplication.java
    └── test/java/com/example/securitytest/
        └── SecurityTestDemoApplicationTest.java
```

### 5.2 Maven dependencies

Create `pom.xml` using Java 17 and Spring Boot 3.3.5. `spring-security-test` is required for `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, and security `RequestPostProcessor`s.

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>com.example</groupId>
    <artifactId>security-test-identities</artifactId>
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

### 5.3 Application and authorization rules

Create `src/main/java/com/example/securitytest/SecurityTestDemoApplication.java`:

```java
package com.example.securitytest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityTestDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityTestDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails actualAdmin = User.withUsername("real-admin")
            .password(encoder.encode("demo123"))
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(actualAdmin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/api/public")
        public String publicPage() {
            return "public ok";
        }

        @GetMapping("/api/me")
        public String currentUser(Authentication authentication) {
            return authentication.getName();
        }

        @GetMapping("/api/admin")
        public String adminOnly() {
            return "admin ok";
        }

        @PreAuthorize("hasAuthority('SCOPE_docs.read')")
        @GetMapping("/api/scoped")
        public String scopedOnly() {
            return "scope ok";
        }
    }
}
```

**How to reason about the outcomes:**

1. `/api/public` is always `permitAll`, including for anonymous callers.
2. `/api/me` only requires being authenticated and responds with the `Authentication` username.
3. `/api/admin` uses `hasRole("ADMIN")`, which requires `ROLE_ADMIN` by default.
4. `/api/scoped` passes the URL `authenticated` rule, and then `@PreAuthorize` checks the exact `SCOPE_docs.read` authority. `@EnableMethodSecurity` is required for method-security annotations to be processed in this demo.
5. `httpBasic` provides a 401 authentication entry point for missing or wrong credentials; authenticated requests lacking permissions normally receive 403. `formLogin` is disabled so the demo does not redirect to a login page.
6. User `real-admin` is an **actual account in the demo app's in-memory store**. Usernames `mai`, `reader`, and `staff` do not exist in this store, yet `@WithMockUser` can still create those identities in tests. That is the exact difference to verify.
7. The password `demo123` is for learning only; `BCryptPasswordEncoder` hashes stored passwords, while production needs proper secret management, policies, permissions, and identity stores.

### 5.4 Complete tests with JUnit 5 and MockMvc

Create `src/test/java/com/example/securitytest/SecurityTestDemoApplicationTest.java`:

```java
package com.example.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityTestDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser
    void defaultMockUserHasUsernameUser() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("user"));
    }

    @Test
    @WithMockUser(username = "mai", roles = "USER")
    void namedMockUserIsAuthenticated() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("mai"));
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotReadPrivateEndpoint() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithAnonymousUser
    void anonymousCanReadPublicEndpoint() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public ok"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void regularUserCannotOpenAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "fake-admin", roles = "ADMIN")
    void mockAdminCanOpenAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin ok"));
    }

    @Test
    @WithMockUser(authorities = "SCOPE_docs.read")
    void scopeAuthorityPassesMethodSecurity() throws Exception {
        mvc.perform(get("/api/scoped"))
            .andExpect(status().isOk())
            .andExpect(content().string("scope ok"));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleDoesNotAutomaticallyGrantScope() throws Exception {
        mvc.perform(get("/api/scoped"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithUserDetails("real-admin")
    void realUserDetailsPrincipalCanBeLoaded() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("real-admin"));
    }

    @Test
    void requestScopedMockIdentity() throws Exception {
        mvc.perform(get("/api/me")
                .with(user("request-user").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("request-user"));
    }

    @Test
    void actualHttpBasicCredentialSucceeds() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("real-admin", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin ok"));
    }

    @Test
    void incorrectHttpBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("real-admin", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
```

The test suite contains **12 cases**: default/renamed mock users, anonymous on private/public endpoints, USER/ADMIN roles, `SCOPE_docs.read` authority, `@WithUserDetails`, request-scoped identity, and valid/invalid HTTP Basic credentials. It covers all **200/401/403** outcomes matching the declared configuration.

Notable point: test `mockAdminCanOpenAdminEndpoint` uses `fake-admin`, an account that **does not exist** in `InMemoryUserDetailsManager`. The test still returns 200 because its purpose is testing **authorization based on a test-supplied Authentication**. By contrast, `actualHttpBasicCredentialSucceeds` and `incorrectHttpBasicPasswordIsRejected` send credentials through the HTTP Basic filter, so they check the demo's real password.

### 5.5 How to run and expected results

In the project directory containing `pom.xml`, requiring Java 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

Four manual requests illustrate testing outside annotations:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u real-admin:demo123 http://localhost:8080/api/admin
curl -i -u real-admin:wrong-password http://localhost:8080/api/admin
```

| Request | Expected status | Main body |
| --- | --- | --- |
| `GET /api/public` anonymous | 200 | `public ok` |
| `GET /api/me` anonymous | 401 | Body depends on entry point; includes Basic challenge |
| `GET /api/admin` with valid password | 200 | `admin ok` |
| `GET /api/admin` with wrong password | 401 | Controller must not execute |

`mvn test` should run the tests if sources and dependencies are right; the example states **expected results per configuration**, without claiming it was run in the reader's environment.

## 6. @WithUserDetails: when the principal must come from UserDetailsService

`@WithMockUser` generates a generic Spring Security principal and **does not require the username to exist** in the store. That can be unsuitable if application code expects a custom principal with fields like `tenantId`, `employeeId`, or a specific type in `@AuthenticationPrincipal`.

`@WithUserDetails` is different:

- Uses a `UserDetailsService` bean from the Spring Test application context to load the account by username.
- The username **must exist** when setting up the security context.
- The principal has the type returned by `UserDetailsService`, making it suitable for testing code that uses `CustomUserDetails`.
- Still **does not invoke password validation** merely because the user is loaded by the annotation; it populates the context directly.
- If multiple `UserDetailsService` beans exist, you can specify `userDetailsServiceBeanName`.

Fragment example:

```java
@Test
@WithUserDetails(
    value = "real-admin",
    userDetailsServiceBeanName = "users"
)
void loadedUserUsesSelectedService() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(content().string("real-admin"));
}
```

In the complete project in section 5, the `users` bean is the declared `UserDetailsService`; this fragment runs when added to the test class. When the application uses a custom principal, the returned method/field must actually be built by your custom `UserDetailsService`—do not cast a default `User` hoping domain fields are present.

### When @BeforeEach creates fixtures

By default, `WithSecurityContextTestExecutionListener` sets up the identity at `TestExecutionEvent.TEST_METHOD`, i.e. **before JUnit 5's `@BeforeEach`**. If you need to create a user in `@BeforeEach` before loading it with `@WithUserDetails`, change the timing:

```java
@Test
@WithUserDetails(
    value = "fixture-user",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void userCreatedByBeforeEachCanBeLoaded() {
    // Test uses the user created by @BeforeEach.
}
```

This fragment requires importing `org.springframework.security.test.context.support.TestExecutionEvent` and creating the real fixture in `@BeforeEach`. With `TEST_EXECUTION`, the context is set after `@BeforeEach` and before the test method; therefore `@BeforeEach` code must not assume it already sees the annotation's `Authentication`.

The same timing option also applies to `@WithMockUser` and `@WithAnonymousUser`. After the test, the test listener clears the context to limit identity leaks between tests; never use a static `SecurityContext` or invent shared state that is hard to control.

## 7. When do you need @WithSecurityContext and a custom principal?

`@WithSecurityContext` lets you build a custom annotation/`WithSecurityContextFactory` when you need an `Authentication` that `@WithMockUser` or `@WithUserDetails` cannot represent well—for instance, an application principal carrying a tenant ID and organization-scoped permissions.

Idea for building a factory (fragment; `TenantPrincipal` is a project-defined type):

```java
// Custom annotation declared by the project:
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(factory = WithTenantIdentityFactory.class)
public @interface WithTenantIdentity {
    String username() default "mai";
    String tenantId() default "tenant-a";
}
```

```java
// Factory is a separate class in test sources.
public final class WithTenantIdentityFactory
        implements WithSecurityContextFactory<WithTenantIdentity> {

    @Override
    public SecurityContext createSecurityContext(WithTenantIdentity data) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        TenantPrincipal principal = new TenantPrincipal(
            data.username(), data.tenantId());
        Authentication auth = UsernamePasswordAuthenticationToken.authenticated(
            principal,
            "N/A",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
        context.setAuthentication(auth);
        return context;
    }
}
```

These are **two intentional fragments**, not two standalone Java files: you must import `java.lang.annotation`, `java.util.List`, the corresponding Spring Security classes, and implement `TenantPrincipal` per your application. A proper factory must create a **new SecurityContext** per invocation rather than reusing a global instance, and grant only required authorities rather than over-privileging to make tests pass.

If you only need a username/role/scope, `@WithMockUser` is simpler. If you need a principal type from a repository, consider `@WithUserDetails`. Only build a custom annotation when the domain genuinely requires attributes that built-in options cannot represent.

### Meta-annotations for repeated permission sets

Mock annotations can be reused:

```java
@Retention(RetentionPolicy.RUNTIME)
@WithMockUser(username = "reviewer", roles = "REVIEWER")
public @interface WithReviewer {
}
```

This is a fragment requiring imports; it lets tests write `@WithReviewer` instead of repeating role strings. Name it clearly and avoid helper annotations that silently grant `ROLE_ADMIN` to every test.

## 8. RequestPostProcessor: per-request identities

Alongside annotations on test methods, Spring Security Test provides helpers in `SecurityMockMvcRequestPostProcessors`:

| MockMvc helper | Meaning |
| --- | --- |
| `user("mai").roles("USER")` | Attaches a mock user to a **specific request** |
| `user(userDetails)` | Attaches a principal from an already-constructed `UserDetails` |
| `anonymous()` | Sends the request as anonymous |
| `authentication(authentication)` | Attaches an existing `Authentication` object |
| `securityContext(context)` | Uses an existing context for the request |
| `httpBasic("real-admin", "demo123")` | Adds an HTTP Basic header so **real authentication filters** verify credentials |
| `csrf()` | Attaches a valid CSRF token to the test request when needed |
| `jwt()`/`oauth2Login()` | Simulates OAuth2/Bearer components suited to authorization tests |

For `user(...)`/`authentication(...)` helpers, Spring Security MockMvc must be properly integrated so the context attached to the request is used by the filter chain. With default `@SpringBootTest` + `@AutoConfigureMockMvc`, the application configures the filters; if you build `MockMvcBuilders` manually, use `.apply(springSecurity())` or integrate `FilterChainProxy` properly.

Request-scoped example:

```java
mvc.perform(get("/api/me")
        .with(user("first").roles("USER")))
    .andExpect(status().isOk())
    .andExpect(content().string("first"));

mvc.perform(get("/api/me")
        .with(user("second").roles("ADMIN")))
    .andExpect(status().isOk())
    .andExpect(content().string("second"));
```

This fragment shows that **each request has its own identity** within the same test. There is no need to place `@WithMockUser` on the method when using per-request helpers. To test anonymous even when a default user exists in setup, use `.with(anonymous())` where appropriate.

**Warning about `jwt()`:** the helper creates a mock `Authentication` for tests; it **does not validate signature, issuer, audience, or expiry of a real JWT**. Those responsibilities require separate tests with an active decoder/filter. Likewise, `oauth2Login()` does not replace testing real redirects, authorization codes, or token exchanges.

### CSRF is an independent variable

`@WithMockUser` handles **identity**, not CSRF tokens. If testing POST/PUT/DELETE in an app with CSRF enabled, you may need:

```java
mvc.perform(post("/api/action")
        .with(user("mai").roles("USER"))
        .with(csrf()))
    .andExpect(status().is2xxSuccessful());
```

This is only a **syntax fragment**: `/api/action` and its authorization rules/handler must actually exist to expect 2xx. If a CSRF token is missing, a 403 status can occur **before** roles are even checked; do not jump to concluding `@WithMockUser` is wrong.

## 9. Distinguishing test levels: security context vs real authentication

| What the test needs to prove | Right tool | What remains unproven |
| --- | --- | --- |
| Controller returns the right principal name | `@WithMockUser(username = "...")` | Whether that user exists in the database |
| `hasRole("ADMIN")` rejects USER | `@WithMockUser(roles = "USER")` | Whether passwords passed through `PasswordEncoder` |
| `@PreAuthorize("hasAuthority('SCOPE_x')")` | `@WithMockUser(authorities = "SCOPE_x")` | Whether real tokens have the right scope from the issuer |
| Unauthenticated users cannot access private routes | `@WithAnonymousUser` or `anonymous()` | Full OAuth2 redirect flow |
| Domain principal from `UserDetailsService` | `@WithUserDetails` | Whether the user submitted valid credentials |
| Valid/invalid HTTP Basic passwords | `httpBasic(...)` with real filter/provider | Other login mechanisms |
| JWT signature, claims, and expiry | Request with real Bearer token + decoder/key test | Do not substitute `jwt()` when testing cryptography |
| End-to-end server, cookies, sessions | Real web server test with an HTTP client | MockMvc uses mock servlets and opens no socket |

**Important for full HTTP tests:** `@WithMockUser`, `@WithUserDetails`, and `@WithSecurityContext` normally set `SecurityContextHolder` on the **test thread**. When `@SpringBootTest(webEnvironment = RANDOM_PORT)` sends HTTP over a socket to a server running on another thread, the server does not automatically read the test's `ThreadLocal`. For such end-to-end tests, **authenticate the HTTP request itself**; do not expect method annotations to log in for the client. MockMvc simulates servlet request processing inside the test process with security test integration, which is why annotations work in the section 5 tests.

### When using @WebMvcTest

`@WebMvcTest` loads only the MVC slice and related beans/auto-configs; it may omit services, user stores, method security, or the application's security config. If a test fails due to missing beans or unexpected 401/403 results, verify the slice imported the appropriate config. Never disable all filters just to make a test pass when the goal is testing security.

`@SpringBootTest` in the full example loads a broader context and lowers the risk of missing security rules. When optimizing suites, you can use slice tests as long as you configure them intentionally.

### Reactive/WebFlux tests differ from Servlet

In WebFlux, the security context uses Reactor Context; integration tests can use `WebTestClient` with `SecurityMockServerConfigurers.mockUser()` or an appropriate mock authentication. When testing reactive method security, Spring Security provides `ReactorContextTestExecutionListener`. Do not use Servlet `MockMvc` or assume test `ThreadLocal` state propagates automatically across event loops/`WebClient`.

## 10. Common mistakes and how to fix them

### Mistake 1 — Using a mock and concluding login is secure

`@WithMockUser(password = "wrong")` does not check the password. A test returning 200 only proves **access rules against a pre-populated context**. Fix this with a separate group of tests sending real HTTP Basic/form credentials or JWTs through filters/providers to verify authentication.

### Mistake 2 — Confusing ROLE_ADMIN and ADMIN

`@WithMockUser(roles = "ADMIN")` creates `ROLE_ADMIN`; `@WithMockUser(authorities = "ADMIN")` does not. Tests may return 403 because the authority string does not match `hasRole("ADMIN")`. Be explicit about the role prefix, use `hasAuthority` for exact strings, and avoid granting broader roles than required.

### Mistake 3 — Thinking a mock username must exist

Mock users can carry usernames absent from the database. If the application truly needs a custom profile, use `@WithUserDetails` or a custom context instead of casting `@AuthenticationPrincipal` to a class that does not exist in a mock.

### Mistake 4 — Testing anonymous with a leftover context

If a class carries `@WithMockUser`, a test without its own annotation still uses the class's mock user. Use `@WithAnonymousUser` to override it explicitly. Never depend on test execution order or state from a previous test.

### Mistake 5 — MockMvc not integrated with Spring Security filters

Building `MockMvcBuilders.standaloneSetup(controller)` without security integration can prevent `@WithMockUser` from reaching the request properly or skip filter rules altogether. Use `.apply(springSecurity())` with a proper setup or `@AutoConfigureMockMvc` with filters enabled.

### Mistake 6 — Misunderstanding 401 and 403

Unauthenticated requests normally receive 401 with HTTP Basic, while form login may return 302. Authenticated callers lacking permissions normally receive 403. 403 can also come from a missing CSRF token; inspect the request and configuration before altering roles.

### Mistake 7 — Skipping @EnableMethodSecurity

`@PreAuthorize` has no effect in a configuration without method security enabled. A test that only checks `authorizeHttpRequests` and concludes method permissions are safe is insufficient. The example enabled `@EnableMethodSecurity` and wrote `scopeAuthorityPassesMethodSecurity` and `adminRoleDoesNotAutomaticallyGrantScope` to prove this branch.

### Mistake 8 — Granting overly broad permissions in tests

Tests that put `@WithMockUser(roles = "ADMIN")` on every request can miss USER or anonymous authorization flaws. Maintain a matrix of **anonymous, authenticated without permission, sufficient permission**, and when using scopes/tenants, include out-of-tenant or missing-scope identities.

### Mistake 9 — Principal type differs from runtime

`@WithMockUser` typically creates a Spring Security `User` principal; if a controller accepts `@AuthenticationPrincipal TenantPrincipal`, casting or accessing fields can fail or yield null in tests. Use `@WithUserDetails` returning custom `UserDetails` or `@WithSecurityContext` creating the right principal type.

### Mistake 10 — Mixing annotations and request identities ambiguously

`@WithMockUser` sets identity for the test, while `.with(user(...))` sets it per request. Mixing both requires knowing the precedence of the environment, default requests, and filters; it is best to **pick one clear identity source per test case**. When switching users multiple times in one test, use request post-processors explicitly.

### Mistake 11 — Evaluating policy solely by HTTP status

A `permitAll` endpoint can still return 200 under a mock ADMIN, leaving you unaware whether anonymous is wrongly blocked. Assert both response bodies and appropriate status branches. For sensitive resources, verify the underlying service **is not invoked** on denial (using an appropriate mock service/spy).

### Mistake 12 — Running a full server and expecting annotations to cross a socket

The test thread's mock security context does not automatically propagate into requests against a running server. With `RANDOM_PORT`/a real HTTP client, send valid headers/cookies/tokens from the client and exercise real filters, encoders, and decoders. Choose the right test scope before concluding "annotations don't work."

## 11. Checklist before finishing an authorization test suite

1. **Boundary:** is this an authorization test with a mock context or an authentication test with real credentials? Both goals need separate test cases.
2. **Identity:** are username, principal type, authorities, and anonymous state clearly specified?
3. **Roles/scopes:** is `ROLE_` confused with exact authorities? Are users tested with *just below* and *exact* required permissions?
4. **Security hooks:** are the filter chain, method security, and `@PreAuthorize` properly enabled in the test context?
5. **Fixtures:** for `@WithUserDetails`, does the user actually exist in the test `UserDetailsService`? How is fixture creation ordered relative to security context setup?
6. **HTTP semantics:** does anonymous return 401 or 302 per config; does insufficient permission return 403; is CSRF 403 tested separately?
7. **Separating results:** are mock-identity test results mistakenly reported as proving passwords, JWT signatures, token expiry, or session login?
8. **Isolation:** do tests depend on execution order, stale ThreadLocals, or a class-level default role?
9. **Stack type:** Servlet/MockMvc or reactive/WebTestClient, using the matching listener/mutator?
10. **Negative checks:** sensitive endpoints do not execute business logic when denied; tests blocking anonymous and low-privilege roles are always present.

## 12. Key takeaways

- **`@WithMockUser`** sets up a mock authenticated user, ideal for testing **authorization and principal-based logic**. Default is `user` with `ROLE_USER`; roles and authorities follow different prefix rules.
- **`@WithAnonymousUser`** reproduces anonymous callers explicitly, especially when a class-level mock user is present. HTTP 401/302 behavior depends on the login mechanism.
- **`@WithUserDetails`** loads principals from `UserDetailsService`, useful when a custom `UserDetails` is needed, though it does not verify a request's password.
- **`@WithSecurityContext`** targets custom domain principals/authentications; grant only necessary permissions and create a fresh context per test.
- **Request post-processors** set different users per request; specifically, `httpBasic(...)` sends credentials through filters to test real authentication.
- **MockMvc + spring-security-test** tests the security chain inside a simulated servlet request model; full HTTP server tests must send real credentials rather than relying on the test ThreadLocal.
- For solid coverage, always include **anonymous, insufficient permission, sufficient permission**, plus at least one test of the application's real authentication path.

## References

- Spring Security — Testing Method Security (`@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, `@WithSecurityContext`): https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Spring MVC Test Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — Running as a User in Spring MVC Test: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — Setting up MockMvc and Spring Security: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Spring Security API — `WithMockUser`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html
- Spring Security API — `WithAnonymousUser`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithAnonymousUser.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html