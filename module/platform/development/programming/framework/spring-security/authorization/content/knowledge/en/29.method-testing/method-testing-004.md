# `@WithUserDetails` and user data in `ApplicationContext` when testing method security

When testing a method with `@PreAuthorize`, `@PostAuthorize`, or another Spring Security rule, we need to place an appropriate `Authentication` into `SecurityContext`. For simple test cases, `@WithMockUser` is usually sufficient. However, if the business logic uses a **custom principal type**, **real authorities returned by `UserDetailsService`**, or user data provided through a Spring bean in **`ApplicationContext`**, use `@WithUserDetails`.

The goal of this lesson: understand exactly where `@WithUserDetails` obtains data, why it differs from `@WithMockUser`, how to configure beans and test data fixtures, how to check method-level privileges, and how to handle the test lifecycle when users are created in `@BeforeEach`.

## 1. Distinguishing `ApplicationContext` and `SecurityContext`

These two contexts handle two different responsibilities:

- **`ApplicationContext`**: Spring's container, managing beans such as `UserDetailsService`, repositories, business services, and method security configuration. The `UserDetailsService` bean may read users from memory, a database, or another source; `ApplicationContext` itself is not a user database.
- **`SecurityContext`**: holds the `Authentication` of the call under test, including the principal and `GrantedAuthority` instances. Spring Security reads this context to evaluate authorization expressions, such as `@PreAuthorize("hasRole('ADMIN')")`.
- **`SecurityContextHolder`**: the access point for `SecurityContext` in the current execution context. In ordinary tests, Spring Security Test prepares the context for the test execution thread and cleans it up afterward.

Data flow when using the annotation:

```text
ApplicationContext
  └── UserDetailsService bean ("accounts")
        └── loadUserByUsername("alice")
              └── UserDetails (can be CustomPrincipal)
                       |
                       v
        @WithUserDetails test listener
                       |
                       v
             Authentication
                       |
                       v
             SecurityContextHolder
                       |
                       v
    Spring-managed service proxy
                       |
                       v
        @PreAuthorize / @PostAuthorize
                       |
                 allowed / denied
```

**`@WithUserDetails` does not log in over HTTP, does not verify passwords, and does not automatically create user records.** It fetches an already retrievable `UserDetails` through a Spring-managed bean and builds an `Authentication` for the test. Under the standard implementation, the authentication type placed in context is `UsernamePasswordAuthenticationToken`, and the principal is the `UserDetails` object returned by the service.

If `loadUserByUsername("alice")` does not find the user, the security context setup step will fail before the test body runs. Therefore, you must provide a valid data fixture, either in memory or seeded as test data at the right time.

## 2. Choosing `@WithMockUser` or `@WithUserDetails`

| Criterion | `@WithMockUser` | `@WithUserDetails` |
| --- | --- | --- |
| Where does the principal come from? | Built directly by Spring Security Test from annotation attributes | Returned by a `UserDetailsService` bean obtained from `ApplicationContext` |
| Does the username need to actually exist? | No | Yes, in the data source read by `UserDetailsService` |
| Is `loadUserByUsername(...)` called? | No | Yes |
| Can the principal be a custom type like `AccountPrincipal`? | No via standard `@WithMockUser` attributes | Yes, if the service returns that type |
| Where do the user's authorities come from? | `roles` / `authorities` in the annotation | `getAuthorities()` of the loaded `UserDetails` |
| When is it convenient? | Quickly testing `hasRole`, `hasAuthority` rules without domain data | Testing rules and business code that depend on a custom principal or real test user source |

Annotation examples:

```java
@WithMockUser(username = "alice", roles = "ADMIN")

@WithUserDetails("alice")

@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "accounts"
)
```

These snippets illustrate syntax placed **on a test method or test class**, not three standalone Java statements. `@WithUserDetails` defaults to looking up username `"user"` if unspecified; the value `"alice"` is passed as input to `UserDetailsService.loadUserByUsername("alice")`.

Note when comparing roles: `roles = "ADMIN"` on `@WithMockUser` grants authority `ROLE_ADMIN` by default convention. `hasRole("ADMIN")` also checks for `ROLE_ADMIN`. If a custom service returns an unprefixed authority `"ADMIN"`, it will not match the `hasRole("ADMIN")` rule under the default prefix configuration.

## 3. Complete Java 17+ example: custom principal and testing `@PreAuthorize`

This example targets **Spring Boot 3.x / Spring Security 6.x, JUnit Jupiter, and Java 17+**. In a Spring Boot Gradle project with dependency management, include:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create the file **`src/test/java/example/WithUserDetailsMethodTest.java`**:

```java
package example;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.stereotype.Service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(classes = WithUserDetailsMethodTest.TestApplication.class)
class WithUserDetailsMethodTest {

    @Autowired
    ReportService reports;

    @Test
    @WithUserDetails(
        value = "alice",
        userDetailsServiceBeanName = "accounts"
    )
    void adminLoadsCustomPrincipalAndCanExport() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertInstanceOf(
            UsernamePasswordAuthenticationToken.class,
            authentication
        );

        AccountPrincipal principal =
            assertInstanceOf(
                AccountPrincipal.class,
                authentication.getPrincipal()
            );

        assertEquals("alice", authentication.getName());
        assertEquals(101L, principal.accountId());
        assertEquals("report-ready", reports.export());
    }

    @Test
    @WithUserDetails(
        value = "bob",
        userDetailsServiceBeanName = "accounts"
    )
    void viewerLoadsSuccessfullyButCannotExport() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        AccountPrincipal principal =
            assertInstanceOf(
                AccountPrincipal.class,
                authentication.getPrincipal()
            );

        assertEquals(202L, principal.accountId());
        assertThrows(
            AccessDeniedException.class,
            () -> reports.export()
        );
    }

    @Test
    @WithMockUser(username = "shadow", roles = "ADMIN")
    void mockUserCanPassRoleCheckWithoutExistingInUserService() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertEquals("shadow", authentication.getName());
        assertFalse(
            authentication.getPrincipal() instanceof AccountPrincipal
        );
        assertEquals("report-ready", reports.export());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @Import({TestUsers.class, ReportService.class})
    static class TestApplication {
    }

    @Configuration(proxyBeanMethods = false)
    static class TestUsers {

        @Bean("accounts")
        UserDetailsService accounts() {
            Map<String, UserDetails> users = Map.of(
                "alice",
                new AccountPrincipal("alice", 101L, "ROLE_ADMIN"),
                "bob",
                new AccountPrincipal("bob", 202L, "ROLE_VIEWER")
            );

            return username -> {
                UserDetails user = users.get(username);
                if (user == null) {
                    throw new UsernameNotFoundException(
                        "Unknown test user: " + username
                    );
                }
                return user;
            };
        }
    }

    static class AccountPrincipal extends User {

        private final long accountId;

        AccountPrincipal(
            String username,
            long accountId,
            String authority
        ) {
            super(
                username,
                "{noop}test-only",
                List.of(new SimpleGrantedAuthority(authority))
            );
            this.accountId = accountId;
        }

        long accountId() {
            return accountId;
        }
    }

    @Service
    static class ReportService {

        @PreAuthorize("hasRole('ADMIN')")
        public String export() {
            return "report-ready";
        }
    }
}
```

Run in a Spring Boot Gradle project:

```bash
./gradlew test --tests example.WithUserDetailsMethodTest
```

If using Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.WithUserDetailsMethodTest
```

With the dependencies and configuration above, **all three tests are expected to PASS**. JUnit does not automatically print the string `"report-ready"` to stdout; it is the **return value** compared with `assertEquals`.

### Why is each test meaningful?

**Test 1 — `alice`:** the annotation resolves the bean named `accounts`, calls `loadUserByUsername("alice")`, and receives an `AccountPrincipal` with `accountId=101` and `ROLE_ADMIN`. Because method security is enabled, calling `reports.export()` goes through the Spring AOP proxy and is permitted by `@PreAuthorize("hasRole('ADMIN')")`. The test verifies both **the right principal type** and **the right privileges**.

**Test 2 — `bob`:** `bob` is a valid user and loads successfully, but only has `ROLE_VIEWER`. Therefore the test verifies that the principal object is set up properly first, then checks that `reports.export()` throws `AccessDeniedException`. This is a method-layer **authorization** denial, not a user-not-found or bad-password error.

**Test 3 — `shadow`:** username `"shadow"` is not in the `accounts` bean's `Map`, yet `@WithMockUser` still creates an authentication with `ROLE_ADMIN`. The method call succeeds because the rule only checks the role, while the principal is not an `AccountPrincipal`. This test highlights when `@WithMockUser` is enough and when it can miss business code needing a custom principal type.

In the example, `{noop}test-only` is just a dummy password **inside the test fixture**; `@WithUserDetails` does not verify this value. Do not use `{noop}` configuration to store real passwords in production.

The example places `UserDetailsService` and `ReportService` in the same test file so it can be read, run, and verified standalone. In a real application, you should **test the real service bean**, use the real `UserDetailsService` or a controlled fixture, and avoid test configurations that accidentally replace the rules under evaluation.

## 4. Role of `ApplicationContext` and bean names

`@WithUserDetails` looks up a bean of type `UserDetailsService` in the **Spring Test `ApplicationContext`**. Because the example uses:

```java
@Bean("accounts")
UserDetailsService accounts() {
    // Returns a service that reads users in the test fixture.
}
```

the annotation specifies:

```java
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "accounts"
)
```

These two snippets simply extract the configuration part of the full example above. When only one matching `UserDetailsService` exists, you can use the shorthand:

```java
@WithUserDetails("alice")
```

When there are **multiple `UserDetailsService` beans** (such as `internalUsers`, `customerUsers`), you must identify the right bean via `userDetailsServiceBeanName` or ensure the bean selection mechanism is clearly configured. Do not rename beans arbitrarily if you want the test to run against the exact user data source the business logic needs.

For applications storing users in a database, the accurate diagram is:

```text
Spring Test ApplicationContext
  └── UserDetailsService bean
        └── UserRepository bean
              └── database / fixture
                    └── user record
```

`ApplicationContext` holds service/repository beans; **user records may reside outside the context**. If the service relies on real application data, seed the test data before `@WithUserDetails` runs. Do not assume that merely adding a validly named bean automatically creates the corresponding user.

### What is needed when testing only the method layer?

- `spring-security-test` on the test classpath for `@WithUserDetails`, `@WithMockUser`, and test listeners.
- A Spring Test Context (`@SpringBootTest` in the example) to provide `ApplicationContext` and the `UserDetailsService` bean.
- `@EnableMethodSecurity` in the configuration applied to the test context if you want to verify `@PreAuthorize`/`@PostAuthorize`. Spring Boot Starter Security does not enable method security automatically.
- Calls passing through a **Spring-managed bean/proxy**. Instantiating `new ReportService()` yourself or calling `this.export()` internally within the same instance may bypass AOP advice, rendering the authorization check meaningless.
- Authorities and domain fields on the `UserDetails` object must match the business policy. If the system uses a role hierarchy or custom expressions, the test must load that configuration.

`MockMvc` is not needed when the target under test is a **service method**. For HTTP controllers, MockMvc and the Security Filter Chain are a separate testing scope; having authentication in a test thread's context does not mean an HTTP request running on a server in another thread is authenticated.

## 5. Timing: does `@WithUserDetails` run before or after `@BeforeEach`?

This is a very common pitfall when user fixtures are inserted in a JUnit setup method.

By default, Spring Security Test sets up `SecurityContext` at the `beforeTestMethod` event, **before** JUnit Jupiter's `@BeforeEach`. Therefore, the sequence can become:

```text
1. Spring Test context is ready
2. @WithUserDetails -> loadUserByUsername("late-user")
3. JUnit @BeforeEach -> creates "late-user" in repository
4. @Test -> runs body
```

If the user is only added in step 3, step 2 has already failed and the test will not run as expected.

The solution is to shift the security context setup timing to `TEST_EXECUTION`:

```java
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithUserDetails;

@Test
@WithUserDetails(
    value = "late-user",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void shouldLoadUserCreatedInBeforeEach() {
    // When the test starts, UserDetailsService can already read "late-user".
}
```

This is a **lifecycle illustration snippet**, assuming a Spring-configured test class where `@BeforeEach` has already created `"late-user"` in the data source backed by the `UserDetailsService` bean. This snippet is not a standalone runnable Java class.

With this setting, the sequence becomes:

```text
1. Spring Test context is ready
2. JUnit @BeforeEach -> creates user
3. @WithUserDetails -> loadUserByUsername(...)
4. @Test -> runs body
```

For data created using `@Sql`, repositories, or test transactions, verify when the fixture is committed/visible to `UserDetailsService`. `TEST_EXECUTION` only resolves **callback ordering**; it does not automatically solve transaction isolation, caching, or database connectivity. In practice, prefer fixtures stably created at the right context/test preparation phase; change `setupBefore` only when needed.

## 6. Distinguishing three categories of test failures

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| Test fails before entering body, reporting username not found | `@WithUserDetails` calls the service but user fixture does not exist yet or queries wrong source | Check `loadUserByUsername`, username, fixture data, `setupBefore` timing |
| `UserDetailsService` not found or wrong one selected | Correct bean not loaded into `ApplicationContext`, multiple beans of same type, wrong `userDetailsServiceBeanName` | Check context configuration and exact bean name |
| Test runs but `@PreAuthorize` denies | Principal loaded but authorities insufficient or expression/rule mismatch | Check `getAuthorities()`, `ROLE_` prefix, method security config |
| Wrong principal type (`ClassCastException`) | Used `@WithMockUser` in code requiring a custom domain principal | Use `@WithUserDetails` with a service returning the proper `UserDetails` |
| `@PreAuthorize` appears to have no effect | `@EnableMethodSecurity` not enabled, object is not a Spring bean, or method called without proxy | Check configuration and how the bean is obtained in the test |
| Test passes but real HTTP request is denied | Annotation only supplies `SecurityContext` to test environment; server requests are not authenticated the same way | Separately test HTTP login/token/cookie and real filter chain |

`@WithUserDetails` does not turn a valid principal into a principal **with sufficient privileges**. A user can exist while lacking `ROLE_ADMIN`, in which case denial in `@PreAuthorize` is the right test outcome.

Nor should `AccessDeniedException` from method security be treated as equivalent to **HTTP 403** in every scenario. In tests calling the service directly, we assert the exception; HTTP statuses only appear when there is an HTTP layer, filter/exception translation, or matching exception handler.

## 7. Test design mistakes to avoid

**Assuming only a matching username is needed:** the annotation calls `loadUserByUsername`; if the service lacks the user or data is unavailable, the test fails during setup. Only `@WithMockUser` lets you fabricate a mock principal without a record.

**Using a mock principal for logic depending on a custom principal:** if code accesses `((AccountPrincipal) authentication.getPrincipal()).accountId()`, `@WithMockUser` does not represent the type returned by the service. Tests should use `@WithUserDetails` and verify the data type.

**Bypassing authorities loaded from the service:** `@WithMockUser`'s `.roles("ADMIN")` may make a test pass without testing that `UserDetailsService` actually assigns `ROLE_ADMIN` to the user; use `@WithUserDetails` when that distinction matters.

**Letting fixture data mutate across tests:** Spring contexts may be cached between test classes; shared in-memory stores or databases can create execution-order dependencies. Create deterministic data, clean up properly, and do not share mutable users across tests if tests modify state.

**Confusing mocked authentication with password testing:** `@WithUserDetails` builds an authenticated context for tests; it does not run `DaoAuthenticationProvider`, password encoders, or login endpoints. To test real authentication, write dedicated tests for the authentication flow.

**Self-calling methods in the same service class:** Spring AOP proxies normally intercept only calls passing through the proxy. Self-invocation can bypass `@PreAuthorize`; a test that only runs `new` or calls internally can yield misleading conclusions.

**Assuming `@WithUserDetails` propagates to every thread:** the test context is usually bound to the thread executing the test. Asynchronous tasks and HTTP calls to a server run on other threads and need explicit `SecurityContext` propagation or separate request authentication; the annotation does not guarantee this automatically.

**Assuming `@SpringBootTest` enables method security:** verify `@EnableMethodSecurity` and the presence of the bean behind an AOP proxy. If you want to test custom rules as well, load the proper security configuration.

## 8. Checklist for testing method security with context-backed users

- [ ] A valid `UserDetailsService` bean exists in the test `ApplicationContext`.
- [ ] The username in `@WithUserDetails` actually exists in the source accessed by that bean.
- [ ] If multiple services exist, `userDetailsServiceBeanName` points to the exact bean.
- [ ] If the fixture is created in `@BeforeEach`, consider `setupBefore = TEST_EXECUTION`.
- [ ] Verify `Authentication.getPrincipal()` has the expected custom principal type and domain properties to test.
- [ ] Test both **allowed** and **denied** users; for service calls, assert the corresponding value or exception.
- [ ] `@EnableMethodSecurity` is enabled and calls go through a Spring-managed bean/proxy.
- [ ] Understand clearly that the test verifies method authorization; do not interpret it as a login, password, or HTTP response test.
- [ ] Fixture data is independent, repeatable, and free of test-order dependencies.

## Official documentation

- [Spring Security — Testing Method Security (`@WithMockUser`, `@WithUserDetails`)](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — Method Security (`@EnableMethodSecurity`, `@PreAuthorize`)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authentication in MockMvc Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
