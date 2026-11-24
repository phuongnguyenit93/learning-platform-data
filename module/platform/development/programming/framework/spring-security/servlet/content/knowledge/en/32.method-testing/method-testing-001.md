# spring-security-test and Related TestExecutionListeners

> **Scope:** Testing method security on **Spring Security Servlet**, Spring Boot 3.x, Spring Security 6.x, JUnit Jupiter, and Java 17+. This article focuses on how `spring-security-test` coordinates with Spring TestContext, especially `WithSecurityContextTestExecutionListener`, how to create a principal in tests, when `SecurityContext` is populated/cleared, and how not to confuse mock authentication with real authentication over HTTP.

## 1. Why Is the spring-security-test Library Needed?

Applications using `@EnableMethodSecurity` and `@PreAuthorize` often have requirements such as:

```java
@PreAuthorize("hasAuthority('REPORT_READ')")
public String readReport() {
    return "report-visible";
}
```

To test this method, you need to determine **which caller Spring Security considers authenticated** and which authorities that caller has. In a real HTTP request, the filter chain may authenticate via Basic, form login, JWT, or OIDC and then create an `Authentication` in `SecurityContextHolder`. However, in a test that calls a Spring bean directly, **there is not necessarily an HTTP request or authentication filter running beforehand**.

`spring-security-test` provides specialized tools:

- Annotations `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, and `@WithSecurityContext` to create an appropriate security context for tests.
- A Spring `TestExecutionListener` that automatically sets up/cleans up test state, typically `WithSecurityContextTestExecutionListener`.
- Request post-processors for MockMvc such as `user(...)`, `httpBasic(...)`, `csrf()`, `jwt(...)`, and `oauth2Login()` (depending on module/usage).
- `SecurityMockMvcConfigurers.springSecurity()` to integrate security into MockMvc when manually building a builder.
- MVC security test assertions/helpers, enabling verification of both endpoints and security mechanisms in requests.

**Key point:** The `@WithMockUser` annotation only **simulates `Authentication`**; it does not verify passwords, JWT signatures, client secrets, or whether the user exists in the database. To verify the full pipeline, you need additional tests that pass through real filters and appropriate integration/E2E tests.

## 2. Spring TestContext, JUnit, and Listeners: Who Does What?

There are **three groups of components** that are easily confused:

1. **JUnit Jupiter**: runs `@Test`, `@BeforeEach`, `@AfterEach`, assertions, and extensions.
2. **Spring TestContext Framework**: manages `ApplicationContext`, dependency injection, transactions, test instances, and invokes `TestExecutionListener`s.
3. **Spring Security Test**: plugs security listeners and annotations into TestContext to populate/clean up `SecurityContext` before/after each test.

Simple flow:

```text
JUnit starts running a test
          |
SpringExtension / SpringBootTestContextBootstrapper
          |
Spring TestContext creates or reuses the ApplicationContext
          |
Spring TestExecutionListeners execute according to the lifecycle
          |
WithSecurityContextTestExecutionListener
   +-- reads @WithMockUser / @WithUserDetails / @WithSecurityContext
   +-- creates Authentication and sets SecurityContext for the test thread
          |
@Test calls Spring service bean / MockMvc
          |
Spring Method Security interceptor checks @PreAuthorize
          |
Assertion on result or AccessDeniedException
          |
TestContext cleans up security context
```

`@SpringBootTest` already integrates JUnit 5 via `SpringExtension`; normally **you do not need to declare `@ExtendWith(SpringExtension.class)` separately**. If using a minimal Spring TestContext configuration (`@ContextConfiguration`), make sure the test runs with SpringExtension.

`WithSecurityContextTestExecutionListener` belongs to the **`spring-security-test`** module, not `spring-security-web` or `spring-security-config`. Therefore, having only the application security starter while **forgetting the test dependency** means these annotations and this listener will be missing from the test classpath.

### 2.1. TestExecutionListener Is Not an HTTP Servlet Filter

| Component | Where It Runs | Responsibility |
|---|---|---|
| `WithSecurityContextTestExecutionListener` | Spring TestContext lifecycle of the test | Builds/sets/cleans up `SecurityContext` for `@WithMockUser`, `@WithUserDetails`, or custom annotations |
| `DependencyInjectionTestExecutionListener` | Spring TestContext | Injects beans, prepares the test instance |
| `TransactionalTestExecutionListener` | Spring TestContext when test transactions are present | Manages test transactions and rollback per configuration |
| `SecurityFilterChain` | HTTP request in the Servlet application | Receives requests, runs authentication/authorization filters |
| `WithSecurityContextFactory` | Called by the listener in tests | Creates `SecurityContext` from a custom annotation |
| `AuthenticationManager` / `AuthenticationProvider` | App authentication mechanism | Verifies credentials through a real provider |
| Method-security interceptor | Call to a proxied/advised bean | Enforces `@PreAuthorize`/`@PostAuthorize` |

A `@WithMockUser` test **does not send a request by itself**, does not invoke `AuthenticationProvider`, does not open a browser session, and does not guarantee that the Spring security filter chain is configured properly.

### 2.2. Distinguishing Related TestExecutionListeners

In Spring Security Test, there are listeners related to the security context:

- **`WithSecurityContextTestExecutionListener`**: handles annotations that create a test security context based on TestContext, loading according to `setupBefore` timing and cleaning up after the test. This is the core listener for **Servlet method-security tests**.
- **`ReactorContextTestExecutionListener`**: supports Reactor security context when reactive security and a suitable environment are present. For this article on **Servlet/MVC**, do not mistake it for a filter or a mandatory prerequisite for `@WithMockUser` to work in ordinary services.

Spring TestContext also has many default listeners used by Spring Framework or Spring Boot (for example, dependency injection, transactions, test database). They have their own lifecycles/priorities. Do not replace the entire default listener set just to "enable Spring Security Test".

## 3. Dependencies and Minimal Configuration

With Gradle, use `spring-security-test` in the **test** scope and keep its version synchronized with the application's Spring Security version:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

In Maven, typically:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

The XML snippet illustrates a project already using Spring Boot dependency management. Do not manually pin a `spring-security-test` version different from `spring-security-core`/`config`/`web` without verifying compatibility.

Check the resolved versions in Gradle:

```bash
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
```

With Spring Security 6 on the Servlet stack, Java code typically uses `jakarta.servlet.*` instead of `javax.servlet.*`. Pure service tests do not need to launch a browser; full application context tests require all necessary beans and `@EnableMethodSecurity` configuration.

## 4. @WithMockUser: Creates Simulated Authentication, Does Not Check Passwords

`@WithMockUser` lets you declare a principal and granted authorities at the class or method level.

Example:

```java
@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void adminCanApprove() {
    // In the test, SecurityContext holds an Authentication
    // with principal "alice" and authority "ROLE_ADMIN".
}
```

Important properties:

- By default, `@WithMockUser` has username `user` and role `USER`, corresponding to authority `ROLE_USER`.
- `roles = "ADMIN"` creates authority `ROLE_ADMIN`. Do not pass the `ROLE_` prefix in `roles` elements: use `roles = "ADMIN"`, **not** `roles = "ROLE_ADMIN"`.
- `authorities = "REPORT_READ"` creates the exact authority `REPORT_READ`, without automatically adding `ROLE_`. If you want to test `hasAuthority("REPORT_READ")`, using `authorities` is the most direct approach.
- Avoid combining `roles` and `authorities` in the same annotation when unsure how the attributes are handled; use only one transparent authority configuration.
- `@WithMockUser` can be placed on the class to apply broadly and then overridden on a method for special cases; check precedence rules when combining annotations.
- There is no need to create user `alice` in `UserDetailsService`. This is an advantage for testing authorization in isolation, but also a **limitation** when testing login/credential verification.

### 4.1. Testing Allowed and Denied Cases

Suppose a service bean has:

```java
@Service
public class ReportService {
    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String readReport() {
        return "report-visible";
    }
}
```

Both `@Service` and `@PreAuthorize` must be imported, and the bean must go through the method security proxy when called. Tests:

```java
@Test
@WithMockUser(authorities = "REPORT_READ")
void readerCanRead() {
    assertEquals("report-visible", reportService.readReport());
}

@Test
@WithMockUser(authorities = "OTHER")
void unrelatedAuthorityCannotRead() {
    assertThrows(AccessDeniedException.class,
            reportService::readReport);
}
```

The methods above are illustrative snippets inside a test class that has a Spring-injected `reportService` field; section 8 provides a **complete program with real files**. If you directly call `new ReportService()` instead of using a Spring-proxied bean, `@PreAuthorize` may not run; the test gives a false PASS.

## 5. @WithUserDetails: Loads a User from the Test's Real UserDetailsService

`@WithUserDetails("reader")` differs from `@WithMockUser(username = "reader")`:

- `@WithMockUser` creates a mock principal without calling `UserDetailsService`.
- `@WithUserDetails` requires a `UserDetailsService` in `ApplicationContext` and **loads `UserDetails` by username**. It uses authorities/principal information from the real fixture.
- Both set up the security context for the test; **neither invokes a password authentication provider to check the password**.
- If the user does not exist in the fixture or there is no suitable `UserDetailsService` bean, `@WithUserDetails` may fail during test preparation **before the `@Test` body runs**.
- If there are multiple `UserDetailsService` beans, use the `userDetailsServiceBeanName` attribute to specify which bean to load from.

Example:

```java
@Test
@WithUserDetails(value = "reader")
void loadedReaderHasPermission() {
    assertEquals("report-visible", reportService.readReport());
}
```

In cases where a real user in the data store is **disabled, locked, or password expired**, `@WithUserDetails` still does not replace testing the authentication manager's enforcement of credential/account status policies: it prepares an already-authenticated principal for the test. If you need to verify credential rejection for a disabled account, go through a real provider/filter.

**Note on test data:** use dedicated fixture accounts, do not use a production database, and do not store real passwords or sensitive permissions in test logs.

## 6. When Does TestExecutionListener Set and Clear SecurityContext?

### 6.1. setupBefore = TEST_METHOD

By default, `@WithMockUser`/`@WithUserDetails` annotations use `TestExecutionEvent.TEST_METHOD` timing. `WithSecurityContextTestExecutionListener` sets up the context during the **beforeTestMethod** phase of Spring TestContext, which is typically **before JUnit `@BeforeEach`**.

That means test setup like the following can observe the simulated principal:

```java
@BeforeEach
void prepare() {
    Authentication a = SecurityContextHolder.getContext().getAuthentication();
    // With @WithMockUser setupBefore=TEST_METHOD,
    // Authentication usually already exists here.
}
```

This is a snippet inside a test class that has imported `Authentication` and `SecurityContextHolder`. It does not prove system-wide state, only showing the context on the **test thread**.

### 6.2. setupBefore = TEST_EXECUTION

Sometimes you need `@BeforeEach` to run **before the security context is installed**: for example, you want to prepare test data, reset fixtures, or modify `UserDetailsService` before loading the user.

```java
@Test
@WithUserDetails(
    value = "reader",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void readerLoadedAfterBeforeEach() {
    // Context is set up in beforeTestExecution,
    // right before the @Test method body, after @BeforeEach.
}
```

`TestExecutionEvent` is in package `org.springframework.security.test.context.support.TestExecutionEvent`. This timing can be useful when the user is created in `@BeforeEach`. However, if the fixture resides in a transaction managed by a test listener, you need to evaluate transaction boundaries and actual lookup visibility; do not assume all repository/DB operations share the same context and are already committed.

**Do not use `setupBefore=TEST_EXECUTION` if `@BeforeEach` relies on the principal already being created.** If setup must check permissions before the test method, the default `TEST_METHOD` is more appropriate.

### 6.3. Cleaning Up SecurityContext to Prevent State Leakage

After the test, the listener cleans up the test security context so the next method does not accidentally inherit stale principals/authorities. That is why using the standard mechanism is better than manually calling:

```java
SecurityContextHolder.getContext().setAuthentication(...);
```

without corresponding cleanup.

Some limitations to keep in mind:

- `SecurityContextHolder` uses thread-local storage by default; on the same test thread, uncleaned state can affect the next test.
- `@Async`, thread pools, or schedulers may run on different threads and **do not automatically receive the test context** unless proper propagation is configured; do not conclude the framework is broken just because a test does not propagate the security context across a thread boundary.
- If you manually modify `TestSecurityContextHolder` or change the security context strategy, you must restore state and avoid race conditions between tests running in parallel.
- Setting a principal in `@BeforeAll` or expecting method-level annotations to take effect in `@BeforeAll` is a lifecycle mismatch: the listener sets the context **for each test method**.
- If a test uses transactions, Spring's transaction listener has its own lifecycle/order; distinguish DB rollback from authentication cleanup.

## 7. Custom TestExecutionListeners: How to Avoid Losing Security Listeners

Spring TestContext provides `@TestExecutionListeners` to attach listeners to the test lifecycle. A common mistake:

```java
@TestExecutionListeners(MyAuditListener.class)
class ReportMethodSecurityTest {
    // Risks replacing the default listener set.
}
```

When declaring a custom listener set without specifying how to merge, you can accidentally replace the default listeners. Consequences include losing dependency injection, transaction setup, or `WithSecurityContextTestExecutionListener`; in that case `@WithMockUser` will not be applied as expected.

A safer way when adding a listener:

```java
import org.springframework.test.context.TestExecutionListeners;

@TestExecutionListeners(
    listeners = MyAuditListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class ReportMethodSecurityTest {
    // Keeps the default listener set and adds MyAuditListener.
}
```

This is an illustrative snippet; `MyAuditListener` is a custom application-defined listener, **not a built-in class** in Spring Security. Do not paste it into the section 8 demo without creating this class. When customizing the lifecycle:

1. Implement `TestExecutionListener` or extend `AbstractTestExecutionListener`.
2. Choose the appropriate callbacks (`beforeTestMethod`, `beforeTestExecution`, `afterTestExecution`, `afterTestMethod`).
3. Keep `MERGE_WITH_DEFAULTS` unless you truly want to replace the default set and understand all consequences.
4. If the new listener reads auth, pay attention to its **order** relative to `WithSecurityContextTestExecutionListener`; a listener running before auth is set may see an empty context.
5. Avoid listeners that initialize a global principal or log sensitive data.

**A TestExecutionListener is not a JUnit Extension.** `@ExtendWith(...)` attaches a JUnit 5 extension; `@TestExecutionListeners(...)` attaches Spring TestContext listeners. With `@SpringBootTest`, SpringExtension is usually already present; do not modify the listeners list just to "register Spring".

### 7.1. Example of a Principal-Independent Custom Listener

If you need to collect test name metadata in a test environment, an illustrative listener could be:

```java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public final class TestNameListener extends AbstractTestExecutionListener {
    @Override
    public void beforeTestMethod(TestContext testContext) {
        String testName = testContext.getTestMethod().getName();
        // Record the testName metric via the configured reporter (if needed).
        // Do not log passwords, session IDs, or tokens.
    }
}
```

This snippet is an **illustrative Java class** and needs to be saved in a file named `TestNameListener.java` in an appropriate package; the `testName` variable demonstrates when metadata is captured, not production telemetry. Do not use a custom listener to grant admin privileges to the test suite.

## 8. Complete Example: Spring Boot 3.3.x, Java 17, Method Security, and MockMvc

This section provides a sample Gradle project to verify at the same time:

- `@PreAuthorize` actually applies to a Spring bean.
- `@WithMockUser` builds the security context for method tests.
- `@WithUserDetails` loads a user from an in-memory `UserDetailsService`.
- `MockMvc` with security filters demonstrates the difference between a **mock principal** and **real HTTP Basic credentials**.
- CSRF remains active on POST, avoiding confusion between HTTP 403 due to CSRF and missing roles.

### 8.1. Project Structure and Gradle

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create the `demo.securitytest` package following this file tree:

```text
src/
  main/java/demo/securitytest/
    SecurityTestApplication.java
    SecurityConfig.java
    ReportService.java
    ReportController.java
  test/java/demo/securitytest/
    ReportMethodSecurityTest.java
    ReportMvcSecurityTest.java
```

This is a **local** demo with fixed accounts for testing purposes, not a production user system. For a project with the Gradle Wrapper, the examples use `./gradlew test`.

### 8.2. Main Application

`src/main/java/demo/securitytest/SecurityTestApplication.java`:

```java
package demo.securitytest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTestApplication.class, args);
    }
}
```

### 8.3. Configuring SecurityFilterChain, UserDetailsService, and Method Security

`src/main/java/demo/securitytest/SecurityConfig.java`:

```java
package demo.securitytest;

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
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("local-read-pass"))
            .authorities("REPORT_READ")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("local-admin-pass"))
            .authorities("ROLE_ADMIN", "REPORT_READ")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

**Explanation:** `@EnableMethodSecurity` enables method authorization; `hasAuthority('REPORT_READ')` matches an exact authority, while `hasRole('ADMIN')` typically expects `ROLE_ADMIN`. `SecurityFilterChain` only requires authentication for `/reports/**`, while specific permissions are controlled by `@PreAuthorize` on the service. This layering shows that **authentication at HTTP** and **authorization at the method** are two distinct layers.

CSRF remains enabled by default, so POST `/reports/approve` requires `csrf()` in MockMvc when using session-like requests; tests missing CSRF yield 403 **before checking service permissions**. Do not disable CSRF just to make tests easier.

### 8.4. Service Protected with @PreAuthorize

`src/main/java/demo/securitytest/ReportService.java`:

```java
package demo.securitytest;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String readReport() {
        return "report-visible";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String approve() {
        return "approved";
    }
}
```

Note that `ReportService` must be injected from Spring. If created with `new ReportService()` or if a protected method is called via **internal self-invocation** without going through the proxy, tests may bypass method security advice. That is a wiring error rather than a fault with `@WithMockUser`.

### 8.5. MVC Controller to Test the Filter Chain

`src/main/java/demo/securitytest/ReportController.java`:

```java
package demo.securitytest;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping(value = "/public", produces = MediaType.TEXT_PLAIN_VALUE)
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping(value = "/reports/read",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String readReport() {
        return reports.readReport();
    }

    @PostMapping(value = "/reports/approve",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public String approve() {
        return reports.approve();
    }
}
```

When testing MVC, all requests must pass through the configured filter chain. If you use `@AutoConfigureMockMvc(addFilters = false)` or build `MockMvcBuilders.standaloneSetup(...)` without attaching Spring Security, you can get false positives/negatives for authentication/authorization.

### 8.6. Method-Security Tests Using @WithMockUser and @WithUserDetails

`src/test/java/demo/securitytest/ReportMethodSecurityTest.java`:

```java
package demo.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ReportMethodSecurityTest {
    @Autowired
    ReportService reports;

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void mockReaderIsAllowed() {
        assertEquals("report-visible", reports.readReport());
    }

    @Test
    @WithMockUser(authorities = "OTHER")
    void wrongAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
                reports::readReport);
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void mockAdminCanApprove() {
        assertEquals("approved", reports.approve());
    }

    @Test
    @WithUserDetails("reader")
    void realUserDetailsFixtureHasReportAuthority() {
        assertEquals("report-visible", reports.readReport());
    }

    @Test
    @WithUserDetails("reader")
    void loadedReaderCannotApprove() {
        assertThrows(AccessDeniedException.class,
                reports::approve);
    }
}
```

These tests **do not send HTTP requests** and do not verify passwords. `@WithUserDetails` uses the `reader` user in `InMemoryUserDetailsManager` to verify the fixture's real authority mapping; `@WithMockUser` directly creates the principal and authorities per the annotation. Method security works because `ReportService` is a proxied bean and `@EnableMethodSecurity` is enabled.

### 8.7. MockMvc Tests Using Mock Principal, CSRF, and Real HTTP Basic

`src/test/java/demo/securitytest/ReportMvcSecurityTest.java`:

```java
package demo.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportMvcSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointWorks() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousReportRequestIsChallengedByBasicAuth()
            throws Exception {
        mvc.perform(get("/reports/read"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void mockReaderCanReadOverMvc() throws Exception {
        mvc.perform(get("/reports/read"))
            .andExpect(status().isOk())
            .andExpect(content().string("report-visible"));
    }

    @Test
    @WithMockUser(authorities = "OTHER")
    void mockUserWithoutAuthorityGets403() throws Exception {
        mvc.perform(get("/reports/read"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminNeedsCsrfForPost() throws Exception {
        mvc.perform(post("/reports/approve"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminWithCsrfCanApprove() throws Exception {
        mvc.perform(post("/reports/approve").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("approved"));
    }

    @Test
    void validBasicCredentialsUseRealAuthenticationProvider()
            throws Exception {
        mvc.perform(get("/reports/read")
                .with(httpBasic("reader", "local-read-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-visible"));
    }

    @Test
    void invalidBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/reports/read")
                .with(httpBasic("reader", "not-the-password")))
            .andExpect(status().isUnauthorized());
    }
}
```

The last two tests differ fundamentally from `@WithMockUser`: `httpBasic(...)` simply attaches an **HTTP Authorization header** to the request. The Spring Security HTTP Basic filter must actually verify the username/password through `AuthenticationManager` and `UserDetailsService`; thus this is a check closer to real authentication in the demo app.

Even so, MockMvc does not open a network socket, does not test TLS/proxy/browser behavior, and `InMemoryUserDetailsManager` is only a fixture. E2E requires additional tests targeting the deployment environment.

### 8.8. Running and Reading Results

In a project with the Gradle Wrapper:

```bash
./gradlew test
```

The expected result is **all tests complete with PASS**, including tests intentionally expecting exceptions or HTTP 403/401. Because Gradle output depends on the wrapper version, logging configuration, and cache state, do not assume every console line will match another machine identically.

You can run individual classes:

```bash
./gradlew test --tests demo.securitytest.ReportMethodSecurityTest
./gradlew test --tests demo.securitytest.ReportMvcSecurityTest
```

If you encounter `UnsatisfiedDependencyException`, inspect the bean configuration. If `@PreAuthorize` does not block calls, check `@EnableMethodSecurity`, bean proxying, and self-invocation before changing test annotations. If the HTTP Basic test fails, check `PasswordEncoder` and the user fixture rather than arbitrarily changing 401/403 expectations.

## 9. Creating a Custom Security Context with @WithSecurityContext

When `@WithMockUser` is not expressive enough for your domain's principal type or authorities, you can use the `@WithSecurityContext` meta-annotation with a custom factory. The mechanism is:

```text
@WithReportReader on test
     |
WithSecurityContextTestExecutionListener reads annotation
     |
WithReportReaderFactory.createSecurityContext(...)
     |
SecurityContext containing simulated Authentication
     |
Spring method-security interceptor reads authorities
```

Below are **two standalone files for `src/test/java`** in package `demo.securitytest`. They can be added to the section 8 project if you need to simulate a reader with a custom username.

**`src/test/java/demo/securitytest/WithReportReader.java`:**

```java
package demo.securitytest;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = WithReportReaderFactory.class)
public @interface WithReportReader {
    String username() default "domain-reader";
}
```

**`src/test/java/demo/securitytest/WithReportReaderFactory.java`:**

```java
package demo.securitytest;

import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public final class WithReportReaderFactory
        implements WithSecurityContextFactory<WithReportReader> {
    @Override
    public SecurityContext createSecurityContext(WithReportReader annotated) {
        var auth = new UsernamePasswordAuthenticationToken(
            annotated.username(),
            "N/A",
            List.of(new SimpleGrantedAuthority("REPORT_READ"))
        );
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        return context;
    }
}
```

This part **only creates a simulated principal/authorities**, does not verify the `"N/A"` password at all, and does not automatically load users from the database. Example usage in the method test class:

```java
@Test
@WithReportReader(username = "tenant-a-reader")
void readerAnnotationAllowsReading() {
    assertEquals("report-visible", reports.readReport());
}
```

The advantage is reduced duplication and clearer business meaning for fixtures. When the application requires a custom principal containing tenant, department, or subject ID, the factory must construct the right principal type along with controlled authorities. Do not automatically assign `ROLE_ADMIN` to every custom annotation; thorough tests need **unauthorized** cases and **different-tenant** cases.

## 10. MockMvc and Listeners: Use Annotations or Request Post-Processors?

Both approaches are useful, though not completely equivalent.

### 10.1. Using @WithMockUser on the Test Method

```java
@Test
@WithMockUser(authorities = "REPORT_READ")
void test() throws Exception {
    mvc.perform(get("/reports/read"))
        .andExpect(status().isOk());
}
```

The annotation sets up the context for the test method via the listener, which is convenient when a test case uses the same identity across multiple calls. It does not force the endpoint to use real credentials. It must run with Spring TestContext and MockMvc properly integrated with filters.

### 10.2. Using Request Post-Processors Per Request

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;

mvc.perform(get("/reports/read")
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("REPORT_READ"))))
    .andExpect(status().isOk());
```

This is a **snippet** inside a test method that has `mvc` and imports `SimpleGrantedAuthority`. Request post-processors are suitable when a single test needs to compare multiple identities across separate requests. If configuring `MockMvcBuilders` manually, you must integrate `springSecurity()` properly; otherwise a user fixture placed on the request may not pass through the right filters/contexts.

### 10.3. When Must You Go Through Real Authentication Filters?

- Testing **password encoder/account lockout**: send `httpBasic(...)` or `formLogin(...)` with real credentials in the test fixture; do not use `@WithMockUser` as proof.
- Testing **JWT signature, issuer, audience**: the `jwt()` post-processor creates a simulated context and normally bypasses the JWT decoder; you need real tests through `JwtDecoder` or tokens signed with a test key when verifying validation.
- Testing **OIDC login protocol/state/nonce/redirect**: the `oauth2Login()` helper creates a simulated authentication for test purposes; real integration tests must verify the client/IdP callback contract.
- Testing **CSRF**: `with(csrf())` sets a valid request token to test deeper logic; intentionally test with a missing or wrong token to verify protection. HTTP 403 from CSRF does not mean `@PreAuthorize` denied the request.

## 11. Failure Modes in Method-Security Tests

**1. Missing `spring-security-test`.** Annotations fail to compile, or custom fixtures/listeners do not exist. Add the dependency under `testImplementation`/`test` with a version matching Spring Security.

**2. Tests do not run through Spring TestContext.** Calling methods on an object created with `new` in a plain JUnit test has no listener and no method-security proxy. Use SpringExtension + Spring context when testing AOP security.

**3. Forgetting `@EnableMethodSecurity`.** `@PreAuthorize` on a service is not enforced automatically in a configuration where method security is not enabled. Verify the actual security configuration.

**4. Creating services with `new` or self-invocation.** Calls do not go through the Spring proxy and may bypass advice. Inject the bean into the test and adjust service/authorization design.

**5. Confusing `roles` and `authorities`.** `roles = "ADMIN"` typically creates `ROLE_ADMIN`; `authorities = "ADMIN"` only creates `ADMIN`. A `hasRole('ADMIN')` rule means something different from `hasAuthority('ADMIN')`.

**6. Trusting `@WithMockUser` to test login.** A mock principal is already authenticated. Wrong/right passwords, account status, sessions, JWT decoders, and IdPs are not tested by this annotation.

**7. `@WithUserDetails` reports user not found before the test runs.** The listener loads the user by exact name from `UserDetailsService`; the fixture is missing or created too late. Use `setupBefore = TEST_EXECUTION` if data needs to be created in `@BeforeEach`, after reviewing transaction boundaries.

**8. `@TestExecutionListeners` drops default listeners.** A custom annotation missing `MERGE_WITH_DEFAULTS` can replace the listener set, causing bean injection or `WithSecurityContextTestExecutionListener` to stop working. Check the test bootstrap config.

**9. Method test SecurityContext differs from request context.** TestContext, MockMvc, and thread-local must be integrated properly. For async/multithread code, propagation or separate-layer testing is needed.

**10. Authorization masked by CSRF.** POST without CSRF returns 403 before reaching the controller. Use `with(csrf())` for permission tests and add a separate negative test to verify CSRF.

**11. Tests pass even without security filters.** `@AutoConfigureMockMvc(addFilters = false)` or standalone MockMvc without `springSecurity()` causes tests not to reflect the real `FilterChainProxy`.

**12. Parallel execution leaks state.** Direct manipulation of `SecurityContextHolder`, global mutable state, or static context without cleanup causes tests to interfere with one another; prefer listeners and isolated fixtures.

**13. Testing the wrong layer of the system.** Unit method tests verifying `@PreAuthorize` do not prove UI, reverse proxy, gateway, session fixation, or authorization on a different endpoint. Separate test goals by layer.

## 12. Designing a Meaningful Test Matrix

| Case | Fixture/Test Path | Expected Assertion |
|---|---|---|
| Allowed by authority | `@WithMockUser(authorities="REPORT_READ")` calling injected service | Method returns valid data |
| Denied by authority | `@WithMockUser(authorities="OTHER")` | `AccessDeniedException` |
| `ROLE_` permission | `@WithMockUser(roles="ADMIN")` | `hasRole('ADMIN')` allows |
| Real user fixture | `@WithUserDetails("reader")` | Authorities from `UserDetailsService` apply properly |
| Unauthenticated HTTP | MockMvc GET protected path without credentials | 401 or challenge per configured entry point |
| Authorized MockMvc | `@WithMockUser` + request to controller | 200, correct data, does not bypass Method Security |
| POST missing CSRF | `@WithMockUser(roles="ADMIN")` without token | 403 at CSRF filter |
| POST with CSRF | `with(csrf())` and ADMIN | 200, method executes |
| HTTP Basic right password | `httpBasic("reader", validPassword)` | 200, real authentication provider runs |
| HTTP Basic wrong password | `httpBasic("reader", invalidPassword)` | 401, does not return data |
| Custom annotation | `@WithSecurityContext` + custom factory | Principal/authorities created properly |
| Custom listener | `@TestExecutionListeners(...MERGE_WITH_DEFAULTS)` | Security listener and dependency injection still work |
| Context timing | `setupBefore=TEST_METHOD/TEST_EXECUTION` | State in `@BeforeEach` matches the contract |
| Async method | Thread pool/`@Async` | Does not rely on implicit thread-local propagation; propagation test exists |
| Test cleanup | Two consecutive tests with different users | Does not inherit auth from previous case |

For complex rules (tenant ownership, ACL, organization-scoped data), add fixtures for **a user with sufficient authority who does not own the resource**. Just using `hasRole` on a mock user is usually not enough to prove object-level authorization.

## 13. Checklist and Takeaways

- [ ] `spring-security-test` dependency is on the test classpath, with its version aligned with Spring Security.
- [ ] Tests use Spring TestContext; `WithSecurityContextTestExecutionListener` gets a chance to run.
- [ ] When using custom `@TestExecutionListeners`, default listeners are preserved with the appropriate merge mode.
- [ ] The application context enables `@EnableMethodSecurity` and tests invoke a Spring-proxied bean.
- [ ] Choose `@WithMockUser` for isolated authorization tests and `@WithUserDetails` for loading user fixtures; do not confuse either with credential authentication.
- [ ] Distinguish `roles`/`ROLE_` from direct `authorities`.
- [ ] Choose `setupBefore` matching `@BeforeEach` and user fixture lifecycles.
- [ ] Include **allow** and **deny** cases, low/high roles, cross-tenant principals, and unowned resources where appropriate.
- [ ] MockMvc has the filter chain attached; POST authorization tests include valid CSRF, alongside an independent negative CSRF test.
- [ ] For real password/JWT/OIDC tests, go through the real authentication provider/decoder/client rather than just creating a mock principal.
- [ ] SecurityContext is cleaned up between methods and does not leak across async/thread pools.
- [ ] Test outcomes explain the right layer: listener, method interceptor, MVC filter, or IdP/proxy.

**Summary:** `spring-security-test` is a toolkit that makes **`SecurityContext` testable**, not a miniature login system. `WithSecurityContextTestExecutionListener` prepares and cleans up the context according to the Spring TestContext lifecycle; `@WithMockUser` creates a simulated principal, `@WithUserDetails` loads a user fixture, and `@WithSecurityContext` creates custom fixtures. For method security, `@EnableMethodSecurity` must be enabled and a Spring-proxied bean must be called; for MockMvc, the filter chain must be attached and mock auth must be distinguished from real credentials. Only with both the right listener and properly targeted assertions do you get a reliable test suite.