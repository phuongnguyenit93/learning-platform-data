# @WithUserDetails with a Real UserDetailsService in Spring Security Servlet Testing

## 1. Problem: Testing Method Security with an Application-Loaded Identity

When a business method is protected by Spring Security, we often want to verify that authorized users can invoke it while unauthorized users are blocked. For example, a report-generation service that only permits users with role `ADMIN`:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public String exportReport() {
    return "export-ok";
}
~~~

This is an illustrative method that must reside in a Spring-managed service, and method security must be enabled for the annotation to take effect.

One quick way to test it is attaching **@WithMockUser(username = "alice", roles = "ADMIN")**. However, that annotation creates a **simulated** user without calling the application's `UserDetailsService`. If production reads roles, account status, or user details from a database, a `@WithMockUser` test may pass even while the real user-loading logic is broken.

**@WithUserDetails** is designed for a different need: it looks up the **UserDetailsService** bean in the test's Spring `ApplicationContext`, calls **loadUserByUsername** to retrieve the **actual `UserDetails` returned by that bean**, and places a matching `Authentication` into `SecurityContext` before the test runs. This enables testing method authorization based on authorities and principals loaded by the system, rather than hardcoding roles in a test annotation.

**Limitation to understand:** `@WithUserDetails` does not perform HTTP login, does not send a password to `AuthenticationManager`, does not verify BCrypt, and does not perform OAuth/JWT token validation. It uses `UserDetailsService` to **prepare the security context for tests**. Thus it fits integration tests for principal loading and method protection, rather than replacing every test of the authentication flow.

This article applies to **Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit 5, and the Spring MVC/Servlet stack**. The focus is **method testing** (method security), not merely checking an endpoint's status code.

## 2. Comparing @WithMockUser and @WithUserDetails

| Criterion | @WithMockUser | @WithUserDetails |
| --- | --- | --- |
| Source of UserDetails | Spring Security Test creates a simulated principal | Calls a `UserDetailsService` bean in `ApplicationContext` |
| UserDetailsService.loadUserByUsername | **Not called** | **Called** |
| username | Defined directly in the annotation | Used to look up the user via the service |
| authorities/roles | Declared directly in the annotation | Taken from the `UserDetails` returned by the service |
| Requires user in repository | No | Yes, if your `UserDetailsService` queries a repository |
| Requires `UserDetailsService` bean in `ApplicationContext` | Not required just to create a mock user | Yes |
| Checks real login password | No | No |
| Best suited for | Fast, isolated tests of a single authorization rule | Integration tests across user loader, authorities, and method security |

Example test with a mock user:

~~~java
@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void adminCanExportUsingMockUser() {
    assertEquals("export-ok", reportService.exportReport());
}
~~~

Role `ADMIN` here is **assigned by the test itself**; it does not prove the application's `UserDetailsService` actually returns `ROLE_ADMIN` for Alice.

Conversely:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService"
)
void adminCanExportUsingLoadedUser() {
    assertEquals("export-ok", reportService.exportReport());
}
~~~

In the second example, Spring Security Test must locate the `realUserDetailsService` bean and load username `alice`. If the service returns a `UserDetails` without `ROLE_ADMIN`, the method will be denied even if the test expected success.

**Do not call `@WithUserDetails` a real login test.** The annotation creates an authenticated `Authentication` from `UserDetails`; it **does not** send a password in an HTTP request and does not verify whether an input password matches the password hash.

## 3. Prerequisites: Enable Method Security and Test the Right Spring Bean

Spring Security 6 uses **@EnableMethodSecurity** to enable interceptors handling `@PreAuthorize`, `@PostAuthorize`, and related method authorization expressions.

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

This is a complete configuration class once the corresponding imports are added and Spring component scan discovers it. In the sample application below, the annotation is placed in the active security configuration.

A protected method:

~~~java
@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String exportReport() {
        return "export-ok";
    }
}
~~~

**The method must be invoked through a Spring-managed proxy.** If you instantiate `new ReportService()` manually in a test, `@PreAuthorize` will have no interceptor running. If a method in the same class calls `this.exportReport()`, standard proxy interception can also be bypassed on self-invocation. A test verifying method security must **`@Autowired` the service bean** and call it from outside the bean.

Required conditions:

1. Spring TestContext or Spring Boot test builds an `ApplicationContext` containing a **real `UserDetailsService`**.
2. The Spring Security test listener is registered (typically integrated automatically by Spring Test/Spring Boot when `spring-security-test` is present).
3. `@EnableMethodSecurity` is active in the context.
4. The service is created by Spring and wrapped in a proxy as needed.
5. `UserDetailsService` can find the user by the name provided in the annotation.
6. How test data is stored aligns with when `@WithUserDetails` calls `loadUserByUsername`.

The last point is often the trickiest failure mode and is explained specifically in section 6.

## 4. At Which Test Phase Does @WithUserDetails Run?

An example:

~~~java
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService"
)
~~~

Its attributes:

- **value:** username passed to `UserDetailsService.loadUserByUsername`. If omitted, the annotation uses its default value (typically `"user"`), rather than inferring a name from the test method.
- **userDetailsServiceBeanName:** specifies a particular `UserDetailsService` bean name, useful when the context has multiple beans or you want to guarantee the right implementation is called. If there is only one `UserDetailsService`, this attribute can be omitted.
- **setupBefore:** specifies the phase in which `SecurityContext` is built: defaults to **`TestExecutionEvent.TEST_METHOD`**; the other commonly used choice is **`TEST_EXECUTION`**.

Spring Security Test uses **`WithSecurityContextTestExecutionListener`** and the corresponding factory for `@WithUserDetails`. At the setup phase, the factory retrieves the `UserDetailsService` bean from `ApplicationContext`, calls `loadUserByUsername`, builds an `Authentication` from the returned `UserDetails`, and places it into `SecurityContextHolder`.

General flow:

~~~text
JUnit / Spring TestContext
         |
         v
WithSecurityContextTestExecutionListener
         |
         v
@WithUserDetails annotation
         |
         +--> locate UserDetailsService bean
         |
         +--> loadUserByUsername("alice")
         |      |
         |      +--> UserDetails with username, password, authorities...
         |
         +--> create authenticated Authentication
         |
         +--> place Authentication into SecurityContext
         |
         v
test method calls Spring-managed service
         |
         +--> @PreAuthorize checks authorities
         |
         +--> allow or AccessDeniedException
~~~

A critical point: **`SecurityContext` is cleaned up after every test** by the test infrastructure so one test does not pollute another. Never hold `Authentication` in a static field or assume the context persists indefinitely on other threads.

Common failures during setup:

- Bean name does not exist -> the test context/factory cannot select a `UserDetailsService`.
- `loadUserByUsername` throws `UsernameNotFoundException` -> test fails **before running the test body**.
- `UserDetails` is loaded but lacks expected permissions -> test runs and `@PreAuthorize` denies it.
- Repository/DB does not yet have the user at setup time -> test fails early even though `@BeforeEach` intended to create the user.

## 5. Distinguishing Username, Role, Authority, and Real Principal

`UserDetailsService` has only one core contract:

~~~java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
~~~

`UserDetails` holds username, password (usually hashed), authorities, and account status attributes. Whether account status attributes directly govern access control depends on the configured policy.

Example returned by a loader:

~~~text
username: alice
password: {bcrypt}...
authorities:
  - ROLE_ADMIN
accountNonLocked: true
enabled: true
~~~

When `@WithUserDetails` builds `Authentication`, the principal is typically the **`UserDetails` returned by the service**. That may be `org.springframework.security.core.userdetails.User` or a `CustomUserDetails` class.

For the method:

~~~java
@PreAuthorize("hasRole('ADMIN')")
~~~

Spring Security uses the **`ROLE_`** role prefix convention in typical configurations. If `UserDetails` has `ROLE_ADMIN`, the method is permitted. If it only has `SCOPE_reports.read` or authority `"ADMIN"` without a prefix under the default policy, results may differ from expectations.

With `@WithMockUser(roles="ADMIN")`, the mock test synthesizes `ROLE_ADMIN`. With `@WithUserDetails`, authorities must come from the **real service**. This is precisely the benefit when you want to test role mapping from the DB.

**Caution regarding account status:** `@WithUserDetails` does not invoke the full `AuthenticationProvider`/`PasswordEncoder` login pipeline. Having `enabled=false` or `accountLocked` on `UserDetails` may not automatically fail the annotation in the same way real authentication would. If you need to prove a locked account cannot log in, test the authentication pipeline separately. Use `@WithUserDetails` to verify principal loading and authorization, not as a substitute for testing `UserDetailsChecker`.

## 6. Ordering @BeforeEach and setupBefore: The Detail That Decides Whether Tests Run

Suppose user `alice` is inserted into the database inside **`@BeforeEach`**:

~~~java
@BeforeEach
void seedUsers() {
    repository.save(new AppUser("alice", "...", "ADMIN"));
}
~~~

If the test annotation uses the default `setupBefore` of `TEST_METHOD`, `SecurityContext` is normally set up during Spring TestContext's **`beforeTestMethod`** phase, **before** JUnit's `@BeforeEach` callback. In that case the loader queries the repository too early; the DB does not have `alice` yet; the test fails with `UsernameNotFoundException`.

To ensure the user is created **before** `@WithUserDetails` looks up the user, use:

~~~java
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
~~~

With `TEST_EXECUTION`, `SecurityContext` is set up during **`beforeTestExecution`**, meaning after standard JUnit `@BeforeEach` callbacks and right before executing the test method.

Comparison:

~~~text
setupBefore = TEST_METHOD (default)

Spring beforeTestMethod:
  @WithUserDetails -> loadUserByUsername("alice")
JUnit @BeforeEach:
  seedUsers()
JUnit @Test:
  method security assertion

If DB is initially empty: user is loaded TOO EARLY.


setupBefore = TEST_EXECUTION

Spring beforeTestMethod
JUnit @BeforeEach:
  seedUsers()
Spring beforeTestExecution:
  @WithUserDetails -> loadUserByUsername("alice")
JUnit @Test:
  method security assertion

User exists before the loader runs.
~~~

Note that lifecycle details also depend on `TestExecutionListener` ordering, custom extensions, and transaction configuration. A safe approach is keeping `@BeforeEach` explicit, avoiding test-level `@Transactional` unless needed, and verifying DB state at load time. In the repository-backed test below, repository `save` calls execute/commit in repository transactions because the test class has no `@Transactional`.

**Another option** is seeding data before the default phase, such as using `@Sql` with an appropriate phase, Testcontainers fixtures, or stable initialization data. However, `@Sql` `BEFORE_TEST_METHOD` and test transactions also require checking `TestExecutionListener` ordering. When fixtures live in `@BeforeEach`, using `TEST_EXECUTION` is the most direct and transparent choice.

## 7. Real Integration Example: UserDetailsService Reading a JPA Repository in H2

To avoid "testing a fake mock service" while remaining self-contained, the application below uses **Spring Data JPA + an in-memory H2 database**. `UserDetailsService` is a real service bean executing repository queries. Method security runs on the Spring-created Service bean.

### 7.1. Dependencies

In `build.gradle` (Groovy) of a project already configured with a compatible Spring Boot plugin/BOM, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This example tests the service directly and **does not need** `spring-boot-starter-web` or `MockMvc`. It illustrates method authorization rather than HTTP endpoints. If the real app uses Spring MVC, you can keep `starter-web`; other configs/filters can be tested separately.

Assume the Java package is **demo.withuserdetails**. The files below must reside in the proper package so Spring Boot component scan detects the repository, service, configuration, and entity.

### 7.2. Main Spring Boot Class

File `src/main/java/demo/withuserdetails/WithUserDetailsApplication.java`:

~~~java
package demo.withuserdetails;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WithUserDetailsApplication {

    public static void main(String[] args) {
        SpringApplication.run(WithUserDetailsApplication.class, args);
    }
}
~~~

### 7.3. JPA Entity Representing the User

File `src/main/java/demo/withuserdetails/AppUser.java`:

~~~java
package demo.withuserdetails;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "app_users")
public class AppUser {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String username;

    @Column(nullable = false)
    private String passwordHash;

    @Column(nullable = false)
    private String roleName;

    protected AppUser() {
        // Constructor for JPA.
    }

    public AppUser(String username,
                   String passwordHash,
                   String roleName) {
        this.username = username;
        this.passwordHash = passwordHash;
        this.roleName = roleName;
    }

    public String getUsername() {
        return username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public String getRoleName() {
        return roleName;
    }
}
~~~

`roleName` in the demo stores **ADMIN** or **READER**, without the `ROLE_` prefix. In a real system, role/permission entities can be modeled with relationships and authority mapping tested separately. The example uses one role per user to keep the `@WithUserDetails` mechanism clear.

### 7.4. Real Repository

File `src/main/java/demo/withuserdetails/AppUserRepository.java`:

~~~java
package demo.withuserdetails;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AppUserRepository extends JpaRepository<AppUser, Long> {

    Optional<AppUser> findByUsername(String username);
}
~~~

This is a real Spring Data repository: the `findByUsername` query executes against the entity and database without Mockito. In the integration test, H2 is a real in-memory database and Hibernate creates tables from the JPA mappings.

### 7.5. UserDetailsService with an Explicit Bean Name

File `src/main/java/demo/withuserdetails/RealUserDetailsService.java`:

~~~java
package demo.withuserdetails;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service("realUserDetailsService")
public class RealUserDetailsService implements UserDetailsService {

    private final AppUserRepository users;

    public RealUserDetailsService(AppUserRepository users) {
        this.users = users;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AppUser appUser = users.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException(
                    "Unknown username: " + username
                )
            );

        return User.withUsername(appUser.getUsername())
            .password(appUser.getPasswordHash())
            .roles(appUser.getRoleName())
            .build();
    }
}
~~~

**`@Service("realUserDetailsService")`** both registers a real bean and lets tests target it explicitly via `userDetailsServiceBeanName`. The method calls the repository to fetch the user. `UserDetails` is constructed with the `User` builder, and `roles("ADMIN")` converts to `GrantedAuthority` `ROLE_ADMIN`.

If multiple `UserDetailsService` beans exist, specifying the bean name prevents selecting the wrong one. Do not give a mock bean in tests the same name if the goal is testing the repository-backed implementation.

Do not expect the user's `passwordHash` to be checked against a password in `@WithUserDetails`: the annotation **does not** run password login. The password hash is present because the `UserDetails` contract requires it; password checking is `AuthenticationProvider`'s job in separate authentication tests.

### 7.6. Enabling Method Security and Password Encoder

File `src/main/java/demo/withuserdetails/SecurityConfig.java`:

~~~java
package demo.withuserdetails;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
~~~

In a service-level application with no servlet web dependency, no `SecurityFilterChain` is required to invoke enabled method security directly. In a real Spring MVC app, `SecurityFilterChain` also handles authentication and authorization for HTTP requests, separate from direct service testing.

### 7.7. Service with Annotation-Protected Methods

File `src/main/java/demo/withuserdetails/ReportService.java`:

~~~java
package demo.withuserdetails;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String exportReport() {
        return "export-ok";
    }

    @PreAuthorize("hasAnyRole('ADMIN', 'READER')")
    public String readReport() {
        return "read-ok";
    }
}
~~~

The export rule allows only `ROLE_ADMIN`; the read rule allows `ADMIN` or `READER`. Because `@EnableMethodSecurity` is active, Spring applies the method security interceptor through a proxy for calls from tests to the Spring bean.

### 7.8. Test Properties for H2

File `src/test/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:security_method_test;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
~~~

This is a **test-only database**, never used for production data. Hibernate creates the schema when the context starts and drops it on context shutdown per `ddl-auto create-drop`. In many real applications, use migration scripts and a test database matching production to test complex schemas/persistence.

### 7.9. @SpringBootTest: Seeding Data Before @WithUserDetails Runs

File `src/test/java/demo/withuserdetails/ReportServiceIntegrationTest.java`:

~~~java
package demo.withuserdetails;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.security.test.context.support.TestExecutionEvent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ReportServiceIntegrationTest {

    @Autowired
    AppUserRepository users;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    ReportService reports;

    @BeforeEach
    void seedDatabase() {
        users.deleteAll();

        users.saveAndFlush(new AppUser(
            "alice", encoder.encode("test-password"), "ADMIN"
        ));
        users.saveAndFlush(new AppUser(
            "bob", encoder.encode("test-password"), "READER"
        ));
    }

    @Test
    @WithUserDetails(
        value = "alice",
        userDetailsServiceBeanName = "realUserDetailsService",
        setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void aliceIsLoadedFromDatabaseAndCanExport() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertTrue(authentication.getPrincipal() instanceof UserDetails);

        UserDetails loaded =
            (UserDetails) authentication.getPrincipal();

        assertEquals("alice", loaded.getUsername());
        assertTrue(
            loaded.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch("ROLE_ADMIN"::equals)
        );

        assertEquals("export-ok", reports.exportReport());
        assertEquals("read-ok", reports.readReport());
    }

    @Test
    @WithUserDetails(
        value = "bob",
        userDetailsServiceBeanName = "realUserDetailsService",
        setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void bobHasReadRoleButCannotExport() {
        assertEquals("read-ok", reports.readReport());

        assertThrows(
            AccessDeniedException.class,
            () -> reports.exportReport()
        );
    }
}
~~~

**Step-by-step analysis of the test in order:**

1. `SpringBootTest` loads the full `ApplicationContext`, including the JPA repository, `RealUserDetailsService`, `ReportService`, and `@EnableMethodSecurity`.
2. JUnit `@BeforeEach` calls `users.deleteAll()`, `saveAndFlush` for `alice` and `bob`. There is no `@Transactional` on the test class, so repository methods execute in their own transactions; data is ready before `TestExecutionEvent.TEST_EXECUTION`.
3. The Spring Security Test listener sees each test's `@WithUserDetails`, retrieves the bean named `realUserDetailsService`, and calls `loadUserByUsername("alice")` or `("bob")` **after `@BeforeEach`**.
4. `RealUserDetailsService` queries `AppUserRepository`/H2 and builds `UserDetails` with `ROLE_ADMIN` or `ROLE_READER`.
5. The listener places the authenticated `Authentication` into `SecurityContext`; the test can inspect username and authorities.
6. `reports` is a **Spring-managed bean**, so `reports.exportReport()` passes through the method security interceptor. Alice is allowed; Bob receives `AccessDeniedException`.
7. After the test, Spring Security test infrastructure cleans up `SecurityContext`. The next test's `@BeforeEach` re-seeds the data, avoiding dependence on the previous test's outcome.

This example uses no `@MockBean` or fake `UserDetailsService`. It is an **integration test that genuinely invokes `UserDetailsService` and the repository**. However, it **does not verify passwords** because `@WithUserDetails` does not pass through HTTP login or `PasswordEncoder.matches`.

To run (in a project with Gradle wrapper and the dependencies above):

~~~bash
./gradlew test --tests demo.withuserdetails.ReportServiceIntegrationTest
~~~

The expected result is both tests passing with the role mappings shown in code; actual CLI output depends on build tool, database driver, Spring Boot version, and environment. There is no fixed stdout because this is a JUnit integration test, not a `println` program.

## 8. Proving the Value of a Real UserDetailsService vs. a Mock Principal

Suppose the actual database stores `alice` with role `READER`, yet a test writes:

~~~java
@WithMockUser(username = "alice", roles = "ADMIN")
~~~

That test still creates `ROLE_ADMIN` even though the DB does not hold that role. If the service has `@PreAuthorize("hasRole('ADMIN')")`, the test can pass and give the impression DB mapping is correct while production does not grant the expected permissions.

Conversely:

~~~java
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
~~~

will pull authorities from `RealUserDetailsService`. When the database changes Alice's role to `READER`, the test checking `ROLE_ADMIN` or `exportReport` will fail, signaling that test expectations no longer match **the real loaded data**.

That is why `@WithUserDetails` should be used when the goal is integration across:

- repository/entity mapping;
- `UserDetailsService`;
- username lookup;
- authorities constructed by the service;
- `SecurityContext` in tests;
- `@PreAuthorize` on a Spring-managed service.

Conversely, when only testing the rule "`ROLE_ADMIN` is allowed, `ROLE_READER` is blocked" without needing a DB, `@WithMockUser` is generally faster and more appropriate. Use both test styles to balance speed with confidence rather than assuming one annotation is always better.

## 9. A Real UserDetailsService Bean Does Not Automatically Mean Production DB

Here **real** means: `@WithUserDetails` calls **the `UserDetailsService` bean present in the test `ApplicationContext`** rather than synthesizing a mock `UserDetails`.

That bean may be:

- **`JdbcUserDetailsManager`** reading user/authorities tables in H2, PostgreSQL, or another test database.
- **A custom `UserDetailsService`** querying a JPA repository as in the example.
- **`InMemoryUserDetailsManager`** genuinely registered in the context to test a given policy.
- A `UserDetailsService` calling another service; the test environment might use a mock server to simulate external dependencies when the goal is not network testing.

Therefore, clarify which integration layer is being tested. `@WithUserDetails` running with `InMemoryUserDetailsManager` still calls a real `UserDetailsService`, yet **does not test JPA repository queries**. By contrast, `SpringBootTest` + JPA repository/H2 verifies the loading path from persistence to `UserDetails`.

Do not label a test "production-real authentication" simply because it uses `@WithUserDetails`. It **does not** verify whether wrong passwords are rejected, JWT signatures are valid, or controllers enforce CORS/CSRF.

## 10. Important Attributes of @WithUserDetails

### 10.1. value: username

By default, the annotation has a sample username, typically `user`. If the test environment only has `alice`, declare it explicitly:

~~~java
@WithUserDetails("alice")
~~~

If no matching user exists, calling `UserDetailsService` fails during setup. Do not rely on the default value unless the test data actually contains that default username.

### 10.2. userDetailsServiceBeanName

If the context contains multiple `UserDetailsService` beans, specify the bean by name:

~~~java
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService"
)
~~~

The name must match the bean name in `ApplicationContext`. In the example, `@Service("realUserDetailsService")` creates a bean with that exact name. If the bean does not exist or is not a suitable `UserDetailsService`, the test cannot set up `Authentication`.

Do not let a Mockito bean with the same name accidentally shadow the real bean if the goal is testing user loading from the repository. If in another test you intentionally mock `UserDetailsService`, clearly mark its scope as a unit test rather than calling it an integration test of the real loader.

### 10.3. setupBefore

~~~java
@WithUserDetails(
    value = "alice",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
~~~

`TEST_EXECUTION` allows fixtures created in `@BeforeEach` to exist before the loader accesses the DB. `TEST_METHOD` (default) fits when the user already exists prior to JUnit `@BeforeEach` running. Using the right lifecycle event is especially critical when the test database starts empty.

### 10.4. Class-Level vs. Method-Level

You can place `@WithUserDetails` on a class so every test uses a default identity, and on methods to use different users. However, when each test seeds the DB in `@BeforeEach`, control `setupBefore` on the **effective annotation** for each test. Do not let a class-level annotation load a user too early when a method needs newly seeded data.

### 10.5. Custom Principal

If `UserDetailsService` returns `CustomUserDetails`, tests can verify the real principal has the right type and properties:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

assertTrue(auth.getPrincipal() instanceof CustomUserDetails);
~~~

This is an illustrative snippet requiring the `CustomUserDetails` class and appropriate imports. Do not assume the principal of every authentication type is `UserDetails`; Resource Server JWTs typically use `JwtAuthenticationToken`/`Jwt` and require a different test strategy.

## 11. Common Mistakes in Lifecycle and Test Data

**Mistake A — `UsernameNotFoundException` occurs before `@BeforeEach`.** Usually caused by `@WithUserDetails` using default `TEST_METHOD` while the user is only created in `@BeforeEach`. Use `setupBefore=TEST_EXECUTION` or seed earlier via a verified mechanism.

**Mistake B — `UserDetailsService` bean not found.** You may be using a `@WebMvcTest` slice that only loads MVC beans without services/repositories. Use `@SpringBootTest` or `@Import` configuration matching your target; if testing the real loader, ensure repositories/datasources are loaded as well.

**Mistake C — Multiple `UserDetailsService` beans exist.** The factory does not know which bean to pick or picks the wrong one. Set the right `userDetailsServiceBeanName` and verify the actual beans in the test `ApplicationContext`.

**Mistake D — `@MockBean` or stub bean accidentally replaces the real loader.** Tests may still pass without executing repository queries. Define integration scope clearly and avoid mocking the exact component under test.

**Mistake E — Test data is rolled back or not yet visible.** With `@Transactional` on tests or fixtures, transaction ordering, repository saves, flushes, and listener setup can interact subtly. Do not assume flush equals commit. This article's example omits `@Transactional` on the test so repository writes commit before `TEST_EXECUTION` setup.

**Mistake F — Calling `new ReportService().exportReport()`.** Bypasses the Spring AOP proxy; `@PreAuthorize` may not run. Autowire the Spring-managed bean. Also check for self-invocation if an internal method calls a protected method on the same object.

**Mistake G — `@EnableMethodSecurity` not enabled.** `@PreAuthorize` annotations may have no effect, letting tests lacking roles execute freely. Ensure the configuration has the annotation and the test actually loads it.

**Mistake H — Role prefix mismatch.** `@PreAuthorize` `hasRole("ADMIN")` usually requires `ROLE_ADMIN`; if `UserDetailsService` returns authority `ADMIN` or `SCOPE_admin`, the policy may fail. Distinguish `roles(...)` from `authorities(...)` and inspect actual `GrantedAuthority` values.

**Mistake I — Confusing `@WithUserDetails` with login testing.** There is no request, no `PasswordEncoder.matches`, and no authentication failure for wrong passwords. Use MockMvc HTTP Basic/form login or real provider integration for credential tests.

**Mistake J — Context leaks between tests.** Never hold `SecurityContextHolder` in static/global fields; let Spring Security Test clean up and recreate the context per test. Remember async code running on another thread does not inherently share the same context.

**Mistake K — Test methods disabled or test class not discovered by the runner.** JUnit 5, Spring test integration, and the `spring-security-test` dependency are required; Boot's `@SpringBootTest` provides `SpringExtension` integration in standard setups.

**Mistake L — Tests relying on users from a real environment.** Never connect to a production database to create/modify users from integration tests. Use test DBs/schemas/fixtures and non-sensitive credentials; avoid leaking password hashes or customer details.

## 12. Why Are Direct Method Tests Often Better Than MockMvc Here?

When the target is `@PreAuthorize` on `ReportService` and authorities loaded by `UserDetailsService`, testing the Spring bean directly clarifies the path:

~~~text
Repository -> UserDetailsService
           -> @WithUserDetails -> SecurityContext
           -> method security proxy -> ReportService
~~~

Adding `MockMvc`, `DispatcherServlet`, HTTP routing, or CORS does not make checking service permissions any more accurate unless you explicitly want to test HTTP-layer authorization as well. Web endpoints may involve authentication filters, CSRF, servlet request matching, sessions, cookies, or JWTs separate from method tests.

A healthy system can include:

- **Unit method tests with `@WithMockUser`:** fast execution, testing role/authority rules.
- **Integration method tests with `@WithUserDetails`:** loading authorities from a real bean and testing the service proxy as shown.
- **Authentication integration tests:** verifying real password or token validation through providers/filters.
- **HTTP end-to-end tests:** verifying `SecurityFilterChain`, 401/403 status codes, CORS/CSRF, controllers, and business logic.

Do not cram all of those responsibilities into a single test: bloated tests make it hard to pinpoint which component failed.

## 13. When Test Data Already Exists Ahead of Time

If initialization data from SQL migrations or test fixtures already exists in the database **before Spring Security Test listener setup**, you can use the default:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService"
)
void canLoadExistingUser() {
    assertEquals("export-ok", reports.exportReport());
}
~~~

Condition: user `alice` must already exist when the listener runs. For example, if database setup occurs via startup migrations or an appropriate test fixture, this requirement can be satisfied.

However, do not switch back from `TEST_EXECUTION` to `TEST_METHOD` when the user is still created inside `@BeforeEach`. Lifecycle ordering does not change just because repository `saveAndFlush` is called in `@BeforeEach`; the `TEST_METHOD` event has already happened before that.

If the database retains leftover data from a previous test, a misconfigured test setup might "pass by accident". Avoid test-order dependence: clean/seed deliberately, keep tests independent, and clean up per your test isolation strategy.

## 14. Extended Scenario: Testing Authorities from Real Data

To increase the value of integration tests, do not only assert a method's return value. Prove the principal was loaded properly:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

UserDetails details = (UserDetails) auth.getPrincipal();

assertEquals("alice", details.getUsername());
assertTrue(details.getAuthorities().stream()
    .anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN")));
~~~

This is an illustrative snippet inside a test that imports `Assertions`, `Authentication`, `SecurityContextHolder`, and `UserDetails`.

If JPA role mapping is wrong or `UserDetailsService` lacks an authority, the assertion fails. This lets the test distinguish a **loader** bug from a **method policy** bug. Conversely, if the authorities assertion passes yet the method denies access, inspect `@EnableMethodSecurity`, proxying, and the expression.

Some systems also have enabled/locked states, organization-scoped permissions, or dynamic roles. Include those attributes in integration tests only when `UserDetailsService` actually returns them and policies reference them; if authorization requires querying resource state in another service, add tests for the business authorization layer as well.

## 15. Practice Questions and Checklist

**Question 1:** A test with `@WithMockUser(roles="ADMIN")` passes, yet the user in the DB only has `READER`. What does this tell us?

It proves the rule allows `ROLE_ADMIN` when a simulated `Authentication` has that permission; it **does not prove** the real loader grants `ROLE_ADMIN`. Use `@WithUserDetails` with a real `UserDetailsService` to test DB mapping.

**Question 2:** Why might `@WithUserDetails` report `alice` is not found even though `@BeforeEach` saves `alice`?

Because by default `TEST_METHOD` sets up `SecurityContext` before JUnit `@BeforeEach`. Choose `TEST_EXECUTION` to load after seeding.

**Question 3:** Does `@WithUserDetails` check the user's password?

No. It calls `UserDetailsService` to fetch the principal and build `Authentication` for the test; to verify passwords, go through the authentication pipeline separately.

**Question 4:** Why must `ReportService` be `@Autowired` instead of `new ReportService()`?

Because method security typically uses a Spring AOP interceptor/proxy. Calling a manually instantiated object bypasses the proxy.

**Question 5:** When there are two `UserDetailsService` beans, how do you ensure the test uses the right service?

Set `userDetailsServiceBeanName` to match the desired bean name and verify `ApplicationContext` actually contains that implementation.

Pre-merge test checklist:

- [ ] `spring-security-test` matches the Spring Security version, and Spring Test/JUnit 5 context is enabled.
- [ ] Method security is enabled via `@EnableMethodSecurity`.
- [ ] Tests load a **real `UserDetailsService` bean** and required repository/datasource.
- [ ] The username in `@WithUserDetails` exists at setup time.
- [ ] If seeding in `@BeforeEach`, `setupBefore=TEST_EXECUTION` is used.
- [ ] `UserDetailsService` itself is not mocked if the goal is testing the real loader.
- [ ] Tests invoke the Spring-managed service proxy, not `new` or self-invocation.
- [ ] Loaded principal/authorities are asserted, not just the method outcome.
- [ ] Both authorized and unauthorized users are tested.
- [ ] `@WithUserDetails` is not confused with password login or Bearer token validation tests.
- [ ] The test database is isolated from production, with independent test data per case.
- [ ] Credentials or password hashes are never logged while debugging the security context.

**Conclusion:** `@WithUserDetails` is a tool for building **`SecurityContext` from the application's `UserDetailsService`** to test method authorization. When paired with a real repository and test database, it catches lookup and authority-mapping bugs that `@WithMockUser` can miss. Success depends on the right context, `@EnableMethodSecurity`, Spring proxying, an existing username, and **`setupBefore` timing**. Keep the annotation's boundary clear: loading a principal and checking permissions, **not replacing real password or access token authentication**.
