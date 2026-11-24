# Adding `spring-security-test` and Loading the Right Security Configuration When Testing Spring Security

> **Scope:** Testing **Spring MVC (Servlet stack)** applications with Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit 5, and MockMvc. Focuses on declaring `spring-security-test` and ensuring each test uses the right `SecurityFilterChain`, authentication provider, users/roles, CSRF, and related security beans. For WebFlux, the corresponding reactive tools and configuration are required.

## 1. Why adding the dependency alone is not enough

A controller test can pass "green" while the real application returns 401 or 403, or vice versa. The usual cause is that **the test context does not load the right security configuration**: security filters are disabled, a test slice pulls in only a subset of beans, a mock user bypasses the real login flow, or a different default `SecurityFilterChain` is active.

For example: production requires `ROLE_ADMIN` for `/api/admin`, yet the test uses `@AutoConfigureMockMvc(addFilters = false)` and only asserts the controller returns 200. That test **does not prove** the endpoint is protected. Conversely, if `@WebMvcTest` loads a default chain requiring login for all URLs instead of the application chain permitting `/api/public`, a 401 test also **does not prove** the production configuration is correct.

Lesson objectives:

1. Declare `spring-security-test` in **test scope**, alongside `spring-boot-starter-test`.
2. Choose properly between **`@SpringBootTest` + `@AutoConfigureMockMvc`** and **`@WebMvcTest` + `@Import`**.
3. Ensure security filters actually run in `MockMvc`.
4. Distinguish `@WithMockUser`, `@WithUserDetails`, `user(...)`, `httpBasic(...)`, and `csrf()`.
5. Cover anonymous, invalid credentials, valid credentials, insufficient permissions, and CSRF cases.
6. Know how to diagnose test-context misconfigurations instead of blindly changing `SecurityConfig`.

## 2. Adding the test dependency properly

In a Gradle project using the Spring Boot plugin and dependency management, declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- `spring-boot-starter-test` provides the foundation for Spring Boot testing, Spring Test, JUnit Jupiter, MockMvc, and common assertion/mocking tools.
- `spring-security-test` provides specialized utilities such as `@WithMockUser`, `@WithUserDetails`, `SecurityMockMvcRequestPostProcessors.httpBasic(...)`, `csrf()`, `user(...)`, `springSecurity()`, and security request/result matchers.
- `spring-boot-starter-security` is a **runtime/application dependency**; `spring-security-test` is a **test dependency**. Adding the test dependency **does not automatically create users, activate a new SecurityFilterChain, or alter runtime policy**.
- When using the Spring Boot BOM/dependency management, **do not pin a separate version** for `spring-security-test`: use the compatible version managed by Spring Boot. Avoid mixing an arbitrary `spring-security-test` version with different runtime security artifacts.

With Maven, the key dependency is:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

A Maven application also needs `spring-boot-starter-test` in `test` scope and `spring-boot-starter-security` as an application dependency.

### 2.1. Common imports

```java
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;

import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;
```

This is an **illustrative import list**; not every class needs all of them. After adding the dependency, run `./gradlew test` so Gradle resolves and checks the test classpath.

## 3. What must be loaded to test security properly?

An HTTP test flow using MockMvc requires two things:

1. **The right security configuration beans:** the actual `SecurityFilterChain` applying to the URL/method under test, together with `UserDetailsService`, `AuthenticationProvider`, `PasswordEncoder`, custom filters, or any required security dependencies.
2. **Security filter integration with MockMvc:** requests must pass through `FilterChainProxy` so authentication/authorization/CSRF behave like the normal Servlet path.

Model:

```text
MockMvc.perform(request)
        |
        v
Spring Security FilterChainProxy (if registered properly)
        |
        +--> Authentication filter (HTTP Basic/form/Bearer...)
        |
        +--> SecurityContext / AuthorizationFilter / CsrfFilter
        |
        +--> Controller / Service / Method Security
        |
        v
MockHttpServletResponse -> status / headers / body / redirect
```

If (1) is missing, the test may run through a **default security chain** different from the application. If (2) is missing, the controller can be invoked **without passing through any authorization filter**. These two failures are independent: having a `SecurityFilterChain` bean in the context **is not enough to prove** MockMvc registered the filter; and having filters in MockMvc **is not enough to prove** it is the intended policy.

### 3.1. Two main choices in Spring Boot

| Goal | Test type | What gets loaded |
| --- | --- | --- |
| Test HTTP security with full application config: real login, encoder, filters, roles, CSRF | `@SpringBootTest` + `@AutoConfigureMockMvc` | Full application `ApplicationContext` with auto-configuration and real beans under the test profile. |
| Test MVC/controller and HTTP rules in isolation without loading the whole system | `@WebMvcTest(Controller.class)` + `@Import(SecurityConfig.class)` as needed | MVC slice, MockMvc, and **explicitly imported** security config; other services/repositories typically must be mocked or imported. |
| Build MockMvc manually from `WebApplicationContext` | `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity())` | Test-created web context with Spring Security properly integrated. |
| Unit-test a service without Servlet | Appropriate JUnit/Spring method-security test | Does not prove HTTP `SecurityFilterChain`; testing `@PreAuthorize` requires loading method security and proxied beans. |

**By default**, `@AutoConfigureMockMvc` has `addFilters = true`. `@WebMvcTest` also auto-configures MockMvc and Spring Security basics for the MVC slice, but a slice is not guaranteed to pull in **all custom security beans** with dependencies outside the slice; therefore you must explicitly inspect and import the actual configuration used. When you want to verify the whole system from HTTP down to the database, choose a full context instead of accidentally turning a slice test into a mock exercise.

## 4. Runnable Java 17+ application example for testing

The example below uses Spring Boot **3.3.5** (an illustrative pinned version, not a claim about the latest release), HTTP Basic, two in-memory users, role rules, and default CSRF. All tests use the application's **actual configuration**. To run it, create a Gradle project with the directory structure as instructed.

### 4.1. Complete Gradle configuration

`settings.gradle`:

```groovy
rootProject.name = 'security-test-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
```

### 4.2. Application, controller, and SecurityFilterChain

Create `src/main/java/demo/securitytest/SecurityTestDemoApplication.java`:

```java
package demo.securitytest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityTestDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTestDemoApplication.class, args);
    }
}

@RestController
class DemoController {
    @GetMapping("/api/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/admin")
    String adminEndpoint() {
        return "admin";
    }

    @PostMapping("/api/messages")
    ResponseEntity<String> createMessage() {
        return ResponseEntity
            .status(HttpStatus.CREATED)
            .body("created");
    }
}

@Configuration
class DemoSecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("USER", "ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/messages")
                    .hasRole("USER")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
```

Configuration intent:

- `/api/public` allows anonymous access.
- `/api/me` requires an authenticated user and returns the principal name.
- `/api/admin` requires the `ROLE_ADMIN` authority.
- `POST /api/messages` requires `ROLE_USER` **and** a valid CSRF token under default Servlet CSRF settings.
- User `reader` only has `ROLE_USER`; user `admin` has both `ROLE_USER` and `ROLE_ADMIN`.
- `httpBasic` enables testing real credentials with `httpBasic(...)` in MockMvc. `formLogin(...disable)` prevents login-page redirects from interfering with API results.
- **CSRF is not disabled** in the example so write requests missing/providing a CSRF token can be tested.
- Passwords are BCrypt-hashed when creating users. Credentials in the example are for learning only and must be replaced by a secure source in real deployments.

`DemoController` and `DemoSecurityConfig` are **package-private classes** in the same file as the public application class, which is valid Java. Tests placed in the same `demo.securitytest` package can reference them.

### 4.3. Expected behavior table

| Request | Credentials / CSRF | Expected result |
| --- | --- | --- |
| `GET /api/public` | None sent | **200**, body `public`. |
| `GET /api/me` | None sent | **401**, HTTP Basic authentication challenge. |
| `GET /api/me` | `reader` / wrong password | **401**, authentication fails. |
| `GET /api/me` | `reader:reader123` | **200**, body `reader`. |
| `GET /api/admin` | Valid reader | **403**, missing `ROLE_ADMIN`. |
| `GET /api/admin` | Valid admin | **200**, body `admin`. |
| `POST /api/messages` | Valid reader, missing CSRF | **403**, rejected by `CsrfFilter`. |
| `POST /api/messages` | Valid reader, valid CSRF | **201**, body `created`. |

**Do not rely on the app starting up successfully to conclude tests are right**: you need negative tests for 401/403 and positive tests for 200/201. Nor should you treat a 403 from missing CSRF as a missing role; distinguish them by request conditions.

## 5. Testing with the full configuration: `@SpringBootTest`

Create `src/test/java/demo/securitytest/SecurityFullContextTest.java`:

```java
package demo.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityFullContextTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousUserReceives401ForProtectedEndpoint() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidPasswordIsRejectedByRealAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validPasswordAuthenticatesThroughHttpBasic() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }

    @Test
    void readerIsForbiddenFromAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminIsAllowed() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfIsCreated() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("reader", "reader123"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created"));
    }
}
```

**Why does this test exercise the real HTTP path?**

- `@SpringBootTest` initializes the full application context based on `@SpringBootApplication`, including `DemoSecurityConfig`, the user service, and the password encoder.
- `@AutoConfigureMockMvc` creates `MockMvc` and registers the context filters by default. You do not need to call `.apply(springSecurity())` manually on a `MockMvc` auto-configured this way.
- `httpBasic("reader", "...")` adds an HTTP Basic Authorization header; credentials pass through the filter and provider to verify the real password.
- Negative tests distinguish unauthenticated, wrong password, missing role, and missing CSRF.
- `csrf()` injects a valid token using Spring Security Test support; if you only test POST with `@WithMockUser` and forget the token, you can still get a 403 **due to CSRF**, regardless of having the right role.
- No TCP port needs to be opened: `MockMvc` runs the Spring MVC pipeline in-process using mock requests and responses.

`@SpringBootTest` carries a higher execution cost than slice tests because it loads more beans. It is the right choice when your goal is **verifying the application's exact security configuration**, especially when providers, services, and filters depend on multiple modules.

### 5.1. Running the tests

In the project directory with Gradle Wrapper:

```bash
./gradlew test
```

Windows PowerShell/CMD:

```bat
gradlew.bat test
```

To run only the suite just created:

```bash
./gradlew test --tests demo.securitytest.SecurityFullContextTest
```

If all assertions match, Gradle reports the `test` task succeeded; **do not hardcode expected stdout** because log format depends on Gradle/IDE versions. A test failure indicates a mismatch with expectations (e.g., `Expected: 403`, `Actual: 401`), which is a signal to inspect filters, context, and credentials before changing policy.

## 6. Testing the controller slice: `@WebMvcTest` and `@Import`

`@WebMvcTest` loads only Spring MVC-related components and relevant auto-configurations. It **typically auto-configures security**, yet custom security beans or dependencies outside the MVC slice may be excluded from the context. Therefore, when testing the application's exact HTTP rules, **explicitly import the real security configuration** and provide needed dependencies.

Create `src/test/java/demo/securitytest/SecurityMvcSliceTest.java`:

```java
package demo.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@WebMvcTest(DemoController.class)
@Import(DemoSecurityConfig.class)
class SecurityMvcSliceTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicRuleFromImportedSecurityConfigIsActive() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousCannotAccessProfile() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void basicAuthenticationUsesImportedUserService() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }

    @Test
    void readerCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void mockUserCanTestAuthorizationWithoutPassword() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }
}
```

**Why does `@Import(DemoSecurityConfig.class)` matter?** It tells the slice to load the `SecurityFilterChain` we want to test, along with the `UserDetailsService` and `PasswordEncoder` declared in that config. Without the import, the test may fall back to default security behavior or miss beans needed for custom mechanisms. In real projects with multiple chains, profiles, and dependent beans, import the exact classes required and verify requests hit the intended chain.

**Do not turn a slice test into a "mock everything" test and still claim full integration:** if a controller injects `OrderService`, `AccountRepository`, or policies outside MVC, `@WebMvcTest` usually does not load them. When testing a controller in isolation, mock its collaborators appropriately (for example `@MockBean` in Spring Boot 3.3) or `@Import` the real adapter when justified. If your goal is testing the DB, providers, and full filter interactions, prefer a full-context test.

### 6.1. When there are multiple `SecurityFilterChain` beans

An application may have chains for `/api/**`, `/admin/**`, and web forms. A test that merely confirms "some security bean exists" can still hit the wrong chain.

- Check each chain's `securityMatcher(...)`, `@Order` precedence, and `requestMatchers(...)` inside the chain.
- Load the chains matching the test's target; if a slice imports only one chain, explicitly note it **does not represent the entire application**.
- Test at least one URL belonging to each chain, plus one URL outside the matchers to verify fallback/default behavior.
- `@ActiveProfiles("test")` can alter configuration, and **does not guarantee** the production chain remains unchanged. Inspect `@Profile`, `@ConditionalOnProperty`, `@TestConfiguration` beans, and overrides.
- Never create a "test-only" `permitAll()` chain when the test is supposed to verify that production endpoints enforce authorization.

### 6.2. When should you mock a service?

If a controller requires a collaborator:

```java
@RestController
class ReportController {
    private final ReportService service;

    ReportController(ReportService service) {
        this.service = service;
    }
}
```

A `@WebMvcTest(ReportController.class)` should only mock `ReportService` to verify request mapping, validation, status codes, and controller HTTP authorization. **The snippet above only illustrates the dependency** and is not a standalone file. To test method security on the real service, mocking the service bypasses the real proxy call; write an integration test that loads the method-security bean/proxy.

## 7. How do `@WithMockUser`, `@WithUserDetails`, `user(...)`, and `httpBasic(...)` differ?

| Tool | What does it do? | Verifies real password? | When to use |
| --- | --- | --- | --- |
| `@WithMockUser(username="...", roles="...")` | Spring Security Test puts a mock authentication into `SecurityContext` for the test. | **No** | Testing role/authorization rules with a test identity. |
| `.with(user("reader").roles("USER"))` | Attaches a mock principal to a **specific MockMvc request**. | **No** | A single test making multiple requests as different identities. |
| `@WithUserDetails(value="reader")` | Loads `UserDetails` from a `UserDetailsService` bean to build the test security context. | **No**; looks up the user without matching raw passwords | Testing rules that rely on the real fixture user's principal/authorities. |
| `.with(httpBasic("reader","reader123"))` | Adds an HTTP Basic header to the request. Filters/providers process credentials if security filters are active. | **Yes, via the configured Basic flow** | Testing authentication, encoder, provider, and filters via HTTP requests. |
| `.with(csrf())` | Adds a valid CSRF token to the test request; `.with(csrf().useInvalidToken())` tests an invalid token. | Unrelated to passwords | Testing POST/PUT/PATCH/DELETE when CSRF is enabled. |

**Example testing authorization without touching passwords:**

```java
@Test
@WithMockUser(username = "admin", roles = {"USER", "ADMIN"})
void adminIsAuthorizedWithSimulatedPrincipal() throws Exception {
    mvc.perform(get("/api/admin"))
        .andExpect(status().isOk());
}
```

This snippet can be added as a method in one of the MockMvc-configured test classes above. It **does not prove** the `admin` account exists, the password is valid, or the provider works. `@WithMockUser` uses annotations on the test method/class; the Spring Test listener creates and clears `SecurityContext` around the test lifecycle.

**Example loading a fixture user through the service:**

```java
@Test
@WithUserDetails(
    value = "reader",
    userDetailsServiceBeanName = "userDetailsService"
)
void userDetailsFixtureCanReadProfile() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(content().string("reader"));
}
```

This snippet also belongs in a test class with `MockMvc`; it requires a `userDetailsService` bean and user `reader` to actually exist in the test source. Do not use `@WithUserDetails` to assert **a wrong password is rejected**: the annotation loads the principal directly from the service without sending a wrong password to any provider.

**Example of a request-scoped mock principal:**

```java
mvc.perform(get("/api/admin").with(user("reader").roles("USER")))
    .andExpect(status().isForbidden());
```

For `user(...)` and `@WithMockUser` to interact properly with the MVC security context, `MockMvc` must be integrated with Spring Security as shown in the examples above.

### 7.1. Role prefix

`roles = "ADMIN"` in `@WithMockUser` creates the authority `ROLE_ADMIN`. Likewise, `.with(user("reader").roles("USER"))` creates `ROLE_USER`. If a rule uses `hasAuthority("SCOPE_read")`, use `authorities = "SCOPE_read"` instead of assuming every permission is a role. Assert the exact set of authorities that production principals receive.

### 7.2. CSRF in context

With Spring Security Servlet CSRF enabled by default, state-changing requests such as POST typically require a token:

```java
mvc.perform(post("/api/messages")
        .with(httpBasic("reader", "reader123"))
        .with(csrf()))
    .andExpect(status().isCreated());

mvc.perform(post("/api/messages")
        .with(httpBasic("reader", "reader123"))
        .with(csrf().useInvalidToken()))
    .andExpect(status().isForbidden());
```

The token in tests is **simulated via the Spring Security test API**, not proof that the production UI client obtains and submits tokens properly. For stateless applications using only Bearer token headers, CSRF may be configured differently; tests must **follow the application's real CSRF policy** rather than blindly attaching `csrf()` or disabling CSRF just to get 200.

## 8. When building `MockMvc` manually, integrate `springSecurity()`

There are two common ways to initialize MockMvc:

**Approach A — Spring Boot auto-configured:** `@SpringBootTest` + `@AutoConfigureMockMvc` or `@WebMvcTest` already provides MockMvc. No manual builder call is needed to register filters.

**Approach B — manual setup from `WebApplicationContext`:** create `MockMvc` and call `.apply(springSecurity())`. Standalone test class example, reusing the application code from section 4:

```java
package demo.securitytest;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
class ManualSecurityMockMvcTest {
    @Autowired
    WebApplicationContext context;

    MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders
            .webAppContextSetup(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void anonymousCannotReadProfile() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
```

`springSecurity()` attaches `FilterChainProxy` along with the test post-processors required by Spring Security. Using pure `MockMvcBuilders.standaloneSetup(controller)` means MVC handles the controller **without necessarily loading the real SecurityFilterChain**. You can register filters manually in standalone setup, but if the goal is testing security integration, using a web application context is easier to configure accurately.

**Do not inject an auto-configured MockMvc and also add duplicate filters manually**: running filters twice can corrupt session, CSRF, and exception translation behavior and produce confusing results.

## 9. Testing method security and the limits of MVC tests

`SecurityFilterChain` protects HTTP paths. Annotations like `@PreAuthorize`/`@PostAuthorize` protect **methods**, typically requiring `@EnableMethodSecurity` and proper Spring proxying. An MVC test that only tests a controller may not exercise method security on a service if that service is mocked.

**Illustrative** code snippet, which must be placed in a registered service bean with `@EnableMethodSecurity` configured:

```java
@Service
class ApprovalService {
    @PreAuthorize("hasAuthority('approve:request')")
    public String approve() {
        return "approved";
    }
}
```

To test such a method:

1. Load a context with `@EnableMethodSecurity` and a real Spring-managed `ApprovalService` bean.
2. Call **through the Spring proxy**—do not invoke `new ApprovalService()` directly or rely on self-invocation expecting annotations to apply.
3. Use `@WithMockUser(authorities = "approve:request")` for the allowed case, and `@WithMockUser(authorities = "read:request")` for the unauthorized case.
4. If the result matters at the API boundary, add an HTTP integration test that loads the real service. Method-security proxies are skipped when a controller calls a mocked service.

Do not assume `@EnableMethodSecurity` is enabled automatically by `spring-security-test`. The test dependency provides tools to populate `SecurityContext`; **the application itself** must configure method security as needed.

## 10. Common pitfalls when loading security configuration

### Pitfall 1. `@AutoConfigureMockMvc(addFilters = false)` when testing Security

```java
// Wrong if the goal is to test authentication/authorization over HTTP.
@SpringBootTest
@AutoConfigureMockMvc(addFilters = false)
class InsecureTestSetup {
}
```

This setting removes filters from MockMvc; many endpoints become directly callable. For security tests, keep the default `addFilters = true`, then verify 401/403 actually occur when permissions are missing.

### Pitfall 2. `@WebMvcTest` tests the controller but omits custom `SecurityConfig`

If the slice uses a default chain instead of the application chain, public endpoints may unexpectedly return 401. Import the real configuration with `@Import(DemoSecurityConfig.class)` and all needed beans. In large applications with many dependencies, use a full context to verify the real policy.

### Pitfall 3. Using only `@WithMockUser` and concluding passwords/providers work

`@WithMockUser` provides a mock principal and does not execute `UserDetailsService.loadUserByUsername()` or `PasswordEncoder.matches(...)`. To test real authentication, send Basic/form login requests or test the appropriate provider against the real chain.

### Pitfall 4. POST returns 403, immediately adding `ROLE_ADMIN`

CSRF can reject a POST **before** business authorization runs. Test with `.with(csrf())` for valid cases and test missing/invalid tokens separately. If production only requires role USER, granting ADMIN unnecessarily widens permissions.

### Pitfall 5. Using `@WithMockUser` when the request lacks `SecurityContext`

If you build MockMvc manually without attaching Spring Security, the test listener may populate the context, yet the HTTP request won't carry the expected security context. Use `@AutoConfigureMockMvc` or `.apply(springSecurity())` with a web application context.

### Pitfall 6. Test profile replaces the production security chain

`@ActiveProfiles("test")` activates profiles that might swap datasources, password encoders, or `SecurityConfig`. Tests must know **which policy** is under test and include an integration test verifying the chain that will actually be deployed. Never use `permitAll()` just to make tests green when asserting security guarantees.

### Pitfall 7. Wrong matcher order or multiple filter chains

In `authorizeHttpRequests`, rules are evaluated in order; a broad rule like `"/api/**"` placed before a specific admin rule can make the later rule unreachable. With multiple `SecurityFilterChain` beans, check both `securityMatcher` and `@Order` to know which chain handles a request.

### Pitfall 8. Overriding the authentication bean or missing dependencies in a slice

If an authentication service uses a repository, `@WebMvcTest` may lack that repository and fail startup. Do not accidentally mock `AuthenticationManager` to always return authenticated and conclude the password flow works. Only mock collaborators when testing a well-defined boundary; authentication integration tests should use real providers and appropriate user fixtures.

### Pitfall 9. Confusing `401` and `403`

HTTP Basic APIs without credentials or with wrong credentials normally return **401**. Authenticated callers lacking an authority usually receive **403**. However, 403 can also come from CSRF; with form login, unauthenticated requests may redirect instead of returning 401. Write assertions matching the **actual authentication mechanism**, rather than assuming one status code for all apps.

### Pitfall 10. Tests pass even when security rules are removed

A trustworthy security test should **fail if a protection rule is deleted**. For instance, if removing `.requestMatchers("/api/admin").hasRole("ADMIN")` leaves all tests green, the tests are likely bypassing filters, hitting only the controller, or missing a negative test where a reader is denied. Negative tests are essential to catch permission regressions.

## 11. Diagnostic sequence for unexpected 401/403 in tests

When a test returns an unexpected 401 or 403, proceed step by step:

1. Check dependencies: ensure `spring-security-test` is in `testImplementation`/`test` scope and test imports are right.
2. Identify the test type: full context, MVC slice, or standalone MockMvc; **which security config is actually loaded**?
3. Check whether `MockMvc` runs `FilterChainProxy`; verify `addFilters=false` is not set.
4. Determine which chain/matcher matches the URL and HTTP method. With multiple chains, inspect `@Order` and `securityMatcher`.
5. Check the test principal: `@WithMockUser`/`user(...)` is fake auth, whereas `httpBasic(...)` passes credentials to the provider; `@WithUserDetails` loads a fixture user without checking the password.
6. Check exact authorities (`ROLE_ADMIN` vs `ADMIN`), account flags, encoder, and provider when using real credentials.
7. For POST/PUT/PATCH/DELETE, check CSRF tokens according to the application's policy.
8. For method security, check `@EnableMethodSecurity`, bean proxies, and ensure service calls are not bypassed by mocks or self-invocation.
9. Compare against a full-context HTTP integration test to spot slice configurations drifting from production.
10. Inspect assertions/logs safely: never log raw passwords, Bearer tokens, or session secrets.

### A minimal test matrix

| Test | What it must prove |
| --- | --- |
| Anonymous calls protected API | Access denied; typically 401 with HTTP Basic/Bearer. |
| Wrong password | Real provider rejects; do not use `@WithMockUser`. |
| Correct password | Principal and `SecurityContext` are established. |
| Role USER calls ADMIN endpoint | 403 due to missing authority. |
| Role ADMIN calls ADMIN endpoint | Allowed. |
| POST missing/invalid CSRF | 403 when the app requires CSRF. |
| POST with valid CSRF and sufficient permission | Succeeds. |
| Public API without credentials | Accessible per `permitAll` policy. |
| Service-level authorization | `@PreAuthorize` is actually enforced via the Spring bean proxy if method security is used. |

Running both **positive and negative** tests distinguishes a properly enforced policy from a suite that only exercises allowed requests.

## 12. Self-check exercises

**Scenario A:** You added `spring-security-test`, yet `/api/admin` still returns 200 for a regular user in tests.  
**Analysis:** the dependency does not enable rules by itself. Check `@AutoConfigureMockMvc(addFilters=false)`, which chain is loaded, matcher order, and whether the test injects a mock authentication with the wrong authorities.

**Scenario B:** `@WebMvcTest(ReportController.class)` fails to start due to a missing `PermissionService` bean.  
**Analysis:** A slice loads only the MVC layer, while a collaborator lives outside the slice. Mock the service to test the controller/HTTP boundary, or use `@SpringBootTest` if the goal is testing security and service together; never replace rules with `permitAll()`.

**Scenario C:** A test with `@WithMockUser(username="alice", roles="ADMIN")` passes, yet calling HTTP Basic `alice:wrong` still returns 401.  
**Analysis:** expected behavior: the annotation simulates a principal without checking passwords; Basic forces the provider to verify the real password.

**Scenario D:** A POST by an authenticated admin returns 403, while GET to the same URL returns 200.  
**Analysis:** check CSRF tokens and method-specific authorization first instead of automatically assuming a missing ADMIN role.

**Scenario E:** A test uses `MockMvcBuilders.standaloneSetup(controller).build()` and never gets 401.  
**Analysis:** `FilterChainProxy` is not integrated. Use a `WebApplicationContext` with `.apply(springSecurity())` or Boot's auto-configured MockMvc.

**Scenario F:** `@WithUserDetails("reader")` passes even though `reader`'s password in the database changed and the test did not notice.  
**Analysis:** the annotation looks up the user without running password comparison; you need a real authentication test using credentials to verify the encoder/provider.

## 13. Checklist before considering security testing complete

- [ ] `testImplementation 'org.springframework.security:spring-security-test'` is declared using the Spring Boot-managed version.
- [ ] Full-context vs MVC slice is chosen appropriately for the goal.
- [ ] The application's real `SecurityFilterChain`/provider/user service is loaded; not accidentally using a default chain.
- [ ] `MockMvc` integrates `FilterChainProxy`; filters are not disabled in security tests.
- [ ] Cases exist for 401 on anonymous/wrong password and 403 on insufficient permissions.
- [ ] Positive cases exist with valid principals/authorities.
- [ ] POST tests explicitly check CSRF per real policy.
- [ ] Login/provider tests do not rely solely on `@WithMockUser` or `@WithUserDetails`.
- [ ] If using method security, `@EnableMethodSecurity` is present and tests call through real bean proxies.
- [ ] Test profiles, mocks, and chains do not alter the policy under verification.
- [ ] A change that breaks a rule causes at least one negative test to fail.

## 14. Takeaways and official documentation

**Two separate but equally mandatory requirements:** (1) `spring-security-test` supplies the tools for mocking principals/credentials/CSRF and assertions; (2) the right **Spring test context + filter integration** confirms the real application enforces the policy. `@SpringBootTest` + `@AutoConfigureMockMvc` fits end-to-end flow checks; `@WebMvcTest` fits MVC boundary tests when you import the exact `SecurityConfig` and required dependencies. Use `httpBasic(...)` to test passwords/providers; use `@WithMockUser` when intentionally testing authorization alone.

Reference sources:

- [Spring Security — Testing (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html)
- [Spring Security — MockMvc Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/)
- [Spring Security — Setting up `MockMvc` with `springSecurity()`](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — CSRF in MockMvc tests](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security — Testing with Mock Users](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html)
- [Spring Boot — `@WebMvcTest` and MVC test slices](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html)
- [Spring Boot — `@AutoConfigureMockMvc`, default `addFilters`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html)
- [Spring Framework — MockMvc setup options](https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html)
