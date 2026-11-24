# @WithMockUser and the difference between roles and authorities in method testing

> **Context:** Spring Security on Servlet, testing **method security** (`@PreAuthorize`) with JUnit 5 and `spring-security-test`. This lesson focuses on creating mock users, checking the authorities actually present in `Authentication`, and proving that a method runs only with the right privileges. Examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x, with the default role prefix convention `ROLE_`.

## 1. Three concepts to distinguish

**Authentication** answers "who is making the call?". In Spring Security, the answer lives in `SecurityContextHolder.getContext().getAuthentication()`.

**GrantedAuthority** is an authority value held by `Authentication`, usually represented by `SimpleGrantedAuthority` and an exact string such as `ROLE_ADMIN`, `invoice:read`, or `SCOPE_invoices.read`. Spring Security does not automatically turn a string `ADMIN` into `ROLE_ADMIN` when checking `hasAuthority`.

**Role** is a naming and checking convention for a group of authorities. With the default prefix `ROLE_`:

- `hasRole('ADMIN')` checks for the actual authority `ROLE_ADMIN`.
- `hasAuthority('ROLE_ADMIN')` checks for exact `ROLE_ADMIN`, so it usually gives the same result as `hasRole('ADMIN')`.
- `hasAuthority('ADMIN')` checks for exact `ADMIN`; it differs from the two above.
- `hasAuthority('invoice:read')` checks for a specific permission; no `ROLE_` needs to be added.

`@WithMockUser` is a **tool for preparing the SecurityContext for a test**. It does not invoke a login service, verify a password, or look up a real account. Therefore, testing with `@WithMockUser` proves the **authorization** rules for the granted principal/authorities, not that real login data or tokens are converted into the right authorities.

### Practice goals

Upon completing this lesson, you should be able to:

1. Read accurately the authorities produced by default `@WithMockUser`, `roles`, and `authorities`.
2. Write **allowed / denied** test pairs for `hasRole` and `hasAuthority`.
3. Understand why `@WithMockUser(roles = "ADMIN")` and `@WithMockUser(authorities = "ADMIN")` are not equivalent.
4. Test rules that require **both** a role and a permission at the same time.
5. Know when to use `@WithUserDetails`, `@WithSecurityContext`, or send credentials over HTTP instead of using a mock user.

## 2. What object does @WithMockUser actually create?

`@WithMockUser` works with `WithSecurityContextTestExecutionListener` in Spring Test. It creates a `SecurityContext` for the test thread containing an authenticated `UsernamePasswordAuthenticationToken`. The default principal is a mock `org.springframework.security.core.userdetails.User`. This user **does not need to exist in a database or `UserDetailsService`**.

Default values of the annotation:

```java
@WithMockUser
// Equivalent in terms of default user data to:
// username = "user"
// password = "password"
// roles = {"USER"}  --> actual authority: "ROLE_USER"
```

Common configurations:

| Annotation | `Authentication.getName()` | Granted `GrantedAuthority.getAuthority()` |
| --- | --- | --- |
| `@WithMockUser` | `user` | `ROLE_USER` |
| `@WithMockUser("mai")` | `mai` | `ROLE_USER` |
| `@WithMockUser(username = "mai", roles = "ADMIN")` | `mai` | `ROLE_ADMIN` |
| `@WithMockUser(roles = {"USER", "ADMIN"})` | `user` | `ROLE_USER`, `ROLE_ADMIN` |
| `@WithMockUser(authorities = "ADMIN")` | `user` | `ADMIN` |
| `@WithMockUser(authorities = "ROLE_ADMIN")` | `user` | `ROLE_ADMIN` |
| `@WithMockUser(authorities = {"invoice:read", "invoice:write"})` | `user` | Two literal strings `invoice:read`, `invoice:write` |
| `@WithMockUser(authorities = "SCOPE_invoices.read")` | `user` | `SCOPE_invoices.read` |

Common pitfall: when passing only `authorities`, the `roles` attribute at its default `{"USER"}` **does not generate an extra `ROLE_USER`**. `authorities` replaces the default role with the exact list of authorities you supply. When you want both `ROLE_ADMIN` and `invoice:read`, write:

```java
@WithMockUser(authorities = {"ROLE_ADMIN", "invoice:read"})
```

In `@WithMockUser`, do not set a non-default `roles` together with `authorities`: Spring Security Test does not allow combining the two attributes that way. The two examples below are **misconfigurations used only to recognize errors**, not to be placed into a running test:

```java
// WRONG: roles automatically adds ROLE_; do not pass an already-prefixed value.
@WithMockUser(roles = "ROLE_ADMIN")

// WRONG: roles is set to a non-default value at the same time as authorities.
@WithMockUser(roles = "ADMIN", authorities = "invoice:read")
```

If you need authorities mixing multiple naming styles, use `authorities = {...}` and list every value explicitly; do not rely on `roles` and `authorities` merging.

## 3. Matching rules: roles and authorities

Treat `Authentication.getAuthorities()` as the **actual input data** of the check, and `hasRole` and `hasAuthority` as the **condition**. With the default prefix:

| Mock user | Rule on method | Result | Explanation |
| --- | --- | --- | --- |
| `roles = "ADMIN"` | `hasRole('ADMIN')` | Allowed | `roles` produces `ROLE_ADMIN` |
| `roles = "ADMIN"` | `hasAuthority('ROLE_ADMIN')` | Allowed | Matches authority `ROLE_ADMIN` |
| `roles = "ADMIN"` | `hasAuthority('ADMIN')` | Denied | String `ADMIN` is absent |
| `authorities = "ADMIN"` | `hasRole('ADMIN')` | Denied | `ROLE_ADMIN` is absent |
| `authorities = "ADMIN"` | `hasAuthority('ADMIN')` | Allowed | Matches exact string `ADMIN` |
| `authorities = "ROLE_ADMIN"` | `hasRole('ADMIN')` | Allowed | `hasRole` rule requires `ROLE_ADMIN` |
| `authorities = "invoice:read"` | `hasAuthority('invoice:read')` | Allowed | Permission matches literally |
| `roles = "ADMIN"` | `hasAuthority('invoice:read')` | Denied | Role `ADMIN` does not automatically grant permission |
| `authorities = "SCOPE_invoices.read"` | `hasAuthority('invoice:read')` | Denied | `SCOPE_invoices.read` and `invoice:read` are two different strings |

**There is no default rule that "ADMIN is stronger than every permission".** If the policy wants admins to read all invoices, state it explicitly in the expression (`hasRole('ADMIN') or hasAuthority('invoice:read')`), or define and test the application's `RoleHierarchy` or `AuthorizationManager`. The examples in this lesson do **not** declare a role hierarchy.

Authority names are compared by exact string, including case and colons; `report:read`, `REPORT:READ`, and `SCOPE_report:read` are all different. `@WithMockUser(roles = "USER")` does not automatically grant `ROLE_ADMIN` or permission to read a resource.

### Custom prefix rules

Spring Security allows configuring the role prefix via `GrantedAuthorityDefaults` or the version's corresponding authorization mechanism. If an application changes the prefix from `ROLE_` to `PRIV_`, the expression `hasRole('ADMIN')` may expect `PRIV_ADMIN`, while `@WithMockUser(roles = "ADMIN")` **still generates `ROLE_ADMIN`** per the annotation's contract. In that case, build a mock principal with `authorities = "PRIV_ADMIN"` or use an equivalent real fixture, and verify that the rule uses the right prefix. Do not change the prefix just to make a test pass.

## 4. Runnable example: method security and testing with JUnit 5

### 4.1. Prepare dependencies

The example is based on **a Spring Boot 3.x application using Java 17 or later**, with the Spring Boot/Dependency Management plugins and Maven Central repository already configured. In `build.gradle` (Groovy), add:

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

This is an **additional declaration snippet for an existing Spring Boot project**, not a full `build.gradle`. `spring-security-test` provides `@WithMockUser`, `@WithAnonymousUser`, and related listeners. `spring-boot-starter-test` provides JUnit 5 and support for running tests with a Spring Context.

### 4.2. Enable method security

File **`src/main/java/demo/roles/MethodRoleDemoApplication.java`**:

```java
package demo.roles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodRoleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodRoleDemoApplication.class, args);
    }
}
```

`@EnableMethodSecurity` allows Spring Security to intercept calls to Spring beans with `@PreAuthorize`. Without this annotation and without an equivalent method security configuration, placing `@PreAuthorize` on a method is not enough to enforce rules. In the example, tests always invoke **the Spring-injected bean** so that calls go through the protecting proxy/AOP; do not use `new InvoiceService()` and draw conclusions about security.

### 4.3. Create a service with independent rules

File **`src/main/java/demo/roles/InvoiceService.java`**:

```java
package demo.roles;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {
    @PreAuthorize("hasRole('ADMIN')")
    public String approveInvoice() {
        return "APPROVED";
    }

    @PreAuthorize("hasAuthority('ROLE_ADMIN')")
    public String checkExplicitRoleAuthority() {
        return "ROLE_ADMIN_OK";
    }

    @PreAuthorize("hasAuthority('ADMIN')")
    public String checkBareAdminAuthority() {
        return "ADMIN_OK";
    }

    @PreAuthorize("hasAuthority('invoice:read')")
    public String readInvoice() {
        return "INVOICE_READ";
    }

    @PreAuthorize("hasAuthority('invoice:write')")
    public String writeInvoice() {
        return "INVOICE_WRITE";
    }

    @PreAuthorize("hasAuthority('SCOPE_invoices.read')")
    public String readWithScopeAuthority() {
        return "SCOPE_READ";
    }

    @PreAuthorize("hasRole('ADMIN') and hasAuthority('invoice:read')")
    public String auditInvoice() {
        return "AUDITED";
    }

    @PreAuthorize("isAuthenticated()")
    public String currentUsername() {
        return SecurityContextHolder.getContext()
                .getAuthentication().getName();
    }
}
```

The eight methods create distinct conditions: role `ADMIN`, pre-prefixed authority `ROLE_ADMIN`, bare authority `ADMIN`, `invoice:read`/`invoice:write` permissions, OAuth2-style scope, an **AND** combination, and an authenticated check. They return simple strings to test authorization rules without needing a database or HTTP controller.

### 4.4. Test suite with both allowed and denied cases

File **`src/test/java/demo/roles/InvoiceServiceSecurityTest.java`**:

```java
package demo.roles;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class InvoiceServiceSecurityTest {
    @Autowired
    private InvoiceService service;

    private static Set<String> currentAuthorities() {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        return auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());
    }

    @Test
    @WithMockUser
    void defaultUserHasOnlyRoleUser() {
        assertEquals("user", service.currentUsername());
        assertEquals(Set.of("ROLE_USER"), currentAuthorities());
        assertThrows(AccessDeniedException.class, service::approveInvoice);
    }

    @Test
    @WithMockUser(username = "mai", roles = "ADMIN")
    void customUsernameAndAdminRoleAreAvailable() {
        assertEquals("mai", service.currentUsername());
        assertEquals(Set.of("ROLE_ADMIN"), currentAuthorities());
        assertEquals("APPROVED", service.approveInvoice());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void rolesAutomaticallyAddRolePrefix() {
        assertTrue(currentAuthorities().contains("ROLE_ADMIN"));
        assertEquals("ROLE_ADMIN_OK",
                service.checkExplicitRoleAuthority());
        assertEquals("APPROVED", service.approveInvoice());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void rolesDoNotAlsoGrantBareAdminAuthority() {
        assertThrows(AccessDeniedException.class,
                service::checkBareAdminAuthority);
    }

    @Test
    @WithMockUser(authorities = "ROLE_ADMIN")
    void exactRoleAuthorityAlsoSatisfiesHasRole() {
        assertEquals(Set.of("ROLE_ADMIN"), currentAuthorities());
        assertEquals("APPROVED", service.approveInvoice());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void bareAuthoritySatisfiesHasAuthorityButNotHasRole() {
        assertEquals(Set.of("ADMIN"), currentAuthorities());
        assertEquals("ADMIN_OK", service.checkBareAdminAuthority());
        assertThrows(AccessDeniedException.class,
                service::approveInvoice);
    }

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readPermissionDoesNotNeedRolePrefix() {
        assertEquals(Set.of("invoice:read"), currentAuthorities());
        assertEquals("INVOICE_READ", service.readInvoice());
    }

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readPermissionDoesNotImplyWritePermission() {
        assertThrows(AccessDeniedException.class, service::writeInvoice);
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleDoesNotAutomaticallyGrantReadPermission() {
        assertThrows(AccessDeniedException.class, service::readInvoice);
    }

    @Test
    @WithMockUser(authorities = {"ROLE_ADMIN", "invoice:read"})
    void mixedAuthoritiesCanSatisfyCombinedRule() {
        assertEquals(Set.of("ROLE_ADMIN", "invoice:read"),
                currentAuthorities());
        assertEquals("AUDITED", service.auditInvoice());
    }

    @Test
    @WithMockUser(authorities = "ROLE_ADMIN")
    void combinedRuleRejectsMissingReadPermission() {
        assertThrows(AccessDeniedException.class, service::auditInvoice);
    }

    @Test
    @WithMockUser(roles = {"ADMIN", "EDITOR"})
    void multipleRolesBecomeMultiplePrefixedAuthorities() {
        assertEquals(Set.of("ROLE_ADMIN", "ROLE_EDITOR"),
                currentAuthorities());
        assertEquals("APPROVED", service.approveInvoice());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_invoices.read")
    void scopeNamedAuthorityIsComparedLiterally() {
        assertEquals("SCOPE_READ", service.readWithScopeAuthority());
        assertThrows(AccessDeniedException.class, service::readInvoice);
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotCallAuthenticatedMethod() {
        assertThrows(AccessDeniedException.class, service::currentUsername);
    }
}
```

**Run tests** from the project root directory:

```bash
./gradlew test --tests 'demo.roles.InvoiceServiceSecurityTest'
```

On Windows PowerShell use `.\gradlew.bat test --tests "demo.roles.InvoiceServiceSecurityTest"`. **Expected result:** all 14 tests pass when run against the sample configuration with the default `ROLE_` prefix. Return values from methods like `APPROVED`, `INVOICE_READ`, or `AUDITED` are values asserted in the tests, not lines automatically printed to stdout. Gradle summary lines depend on the build configuration, so do not assume a fixed console transcript.

### Why are these tests meaningful?

- `@SpringBootTest` creates a Spring application context; the service is injected by Spring so the `@EnableMethodSecurity` interceptor has the opportunity to enforce `@PreAuthorize`.
- The tests assert the **actual authorities** via `currentAuthorities()`. Asserting only the allowed result makes it easy to miss a test that was accidentally granted more privileges than intended.
- `assertThrows(AccessDeniedException.class, ...)` verifies that a direct call to the service is blocked when privileges are missing. For method security, do not expect a `MockMvc` object or HTTP status to appear if the test does not send an HTTP request.
- The pair `roles = "ADMIN"` ↔ `authorities = "ADMIN"` proves they create different authorities; the pair `roles = "ADMIN"` ↔ `authorities = "ROLE_ADMIN"` proves both ways can satisfy `hasRole('ADMIN')`.
- The combined test uses `authorities = {"ROLE_ADMIN", "invoice:read"}` instead of attempting to pass both `roles` and `authorities` in the annotation.

If `@PreAuthorize("hasRole('ADMIN')")` is changed to `hasAuthority('ADMIN')` without changing the tests, the corresponding allowed/denied cases will flip results. That is a useful regression signal: the **effective policy** has changed.

## 5. What happens if @WithMockUser is misused?

### 5.1. Mixing roles and authorities

Do not write:

```java
@WithMockUser(roles = {"ADMIN"}, authorities = {"invoice:read"})
```

Spring Security Test does not merge the two lists this way: if `authorities` is specified, `roles` must not be changed from its default value. The test can fail **at the SecurityContext setup step**, before method security is ever evaluated. Use:

```java
@WithMockUser(authorities = {"ROLE_ADMIN", "invoice:read"})
```

to grant both authorities accurately.

### 5.2. Passing ROLE_ into roles

Do not write `@WithMockUser(roles = "ROLE_ADMIN")`. `roles` takes **role names without the prefix**, because the factory adds `ROLE_` automatically and validates the input. Write `roles = "ADMIN"` or `authorities = "ROLE_ADMIN"`.

### 5.3. Seeing 403 and assuming the method rule ran

When calling over HTTP, `403 Forbidden` may come from HTTP authorization, CSRF, method security, or another handler. When calling a bean directly with JUnit, you typically assert `AccessDeniedException` or a subtype; when going through `MockMvc`, add assertions on both the status **and** the body of the allowed case to confirm that the controller and service were actually called. Identify which layer is under test rather than inferring backwards from an HTTP status code.

### 5.4. Not enabling method security or bypassing the proxy

The following example **does not properly test the interceptor**:

```java
var service = new InvoiceService(); // Object created with new, does not go through Spring proxy.
service.approveInvoice();           // No proxy to enforce @PreAuthorize.
```

Similarly, calling a `@PreAuthorize`-annotated method from another method **in the same object** can be a self-invocation that does not pass through the AOP proxy; the annotation on the target method may then not execute in proxy mode. Test through a Spring bean and keep relevant call sites crossing the proxy; for special requirements, choose an appropriate security design and test the real flow.

## 6. Class-level, method-level, and SecurityContext setup timing

The annotation can be placed on the **test class** so that all tests inherit the same user, and then overridden on specific methods. Illustrative example (not an addition to the test suite above):

```java
@WithMockUser(roles = "USER")
class ExampleTests {
    @Test
    void normalUserCase() {
        // ROLE_USER.
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminOverrideCase() {
        // Method's ROLE_ADMIN; does not accumulate ROLE_USER from the class.
    }

    @Test
    @WithAnonymousUser
    void anonymousOverrideCase() {
        // Does not use the class-level ROLE_USER mock user.
    }
}
```

In Spring Test, `@WithMockUser` sets up the context at the `TEST_METHOD` event by default, before `@BeforeEach`. If you need `@BeforeEach` to run **before** the mock security context is established, you can use:

```java
@WithMockUser(
    username = "mai",
    roles = "ADMIN",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
```

A test file using this option must import `org.springframework.security.test.context.support.TestExecutionEvent`. In this mode, the context is built after `@BeforeEach` and before the `@Test` body. Use this option only when initialization order truly matters; a `@BeforeEach` that calls a protected service will not see the mock user if the context has not been created yet.

The SecurityContext is normally bound to the current test thread. If code runs on another thread such as `@Async` or a test sends an HTTP request to a real server with `webEnvironment = RANDOM_PORT`, the context on the test thread **does not automatically become the authentication of the server thread**. For end-to-end tests, requests must be authenticated with cookies/sessions, HTTP Basic, bearer tokens, or another appropriate mechanism.

## 7. When to use @WithMockUser, @WithUserDetails, or @WithSecurityContext?

| Tool | Best suited for | Does not prove on its own |
| --- | --- | --- |
| `@WithMockUser` | Testing method/MockMvc rules with explicitly declared username and roles/authorities | Real account exists, password is valid, JWT contains matching claims |
| `@WithUserDetails("mai")` | Tests needing a real principal loaded by a `UserDetailsService` bean | The full login flow outside HTTP |
| `@WithSecurityContext` | Custom principals, custom `Authentication` types, or complex security fixtures | Correctness of external protocols/tokens if not tested |
| `MockMvc` with `user(...)` or `jwt(...)` | Attaching principal/claims/authorities to **a single request** to test the HTTP layer | Real authentication if still using mocked request attributes |
| HTTP integration test sending real credentials/tokens | Testing filters, token parsers, claim-to-authority conversion, and application together | Every object-level privilege case unless separate tests are written |

If the application casts `authentication.getPrincipal()` to a `CustomUserDetails` class, `@WithMockUser`'s standard `User` principal may cause a cast error even when the authorization logic is correct. Use `@WithUserDetails` with a real fixture or a custom `@WithSecurityContext` to test with the application's actual principal type.

In an OAuth2 Resource Server, the `SCOPE_invoices.read` authority is usually derived from the bearer token's scope via an appropriate converter. Supplying `@WithMockUser(authorities = "SCOPE_invoices.read")` only verifies that **the method accepts that authority**; it does not verify a valid JWT or that the converter maps scopes correctly. Add converter/filter tests using `jwt()` or real bearer token requests as needed.

## 8. QA matrix for a protected method

Suppose the system has:

```java
@PreAuthorize("hasRole('ADMIN') and hasAuthority('invoice:read')")
public Invoice detailForAudit(String id) { /* business logic */ }
```

This is an **illustrative signature and rule**, not a standalone program; `Invoice` and the business logic must be defined by the application.

| Mock principal | Actual authority | Expected | Why |
| --- | --- | --- | --- |
| `@WithMockUser(roles = "ADMIN")` | `ROLE_ADMIN` | Denied | Missing `invoice:read` |
| `@WithMockUser(authorities = "invoice:read")` | `invoice:read` | Denied | Missing `ROLE_ADMIN` |
| `@WithMockUser(authorities = "ADMIN")` | `ADMIN` | Denied | Missing both |
| `@WithMockUser(authorities = {"ROLE_ADMIN", "invoice:read"})` | Both | Allowed | Matches both conditions |
| `@WithMockUser(authorities = {"ROLE_ADMIN", "invoice:write"})` | `ROLE_ADMIN` + `invoice:write` | Denied | Write does not substitute for read |
| `@WithAnonymousUser` | Anonymous authority, if any | Denied | Satisfies neither role nor permission |

Testing all six cases helps catch errors such as changing `and` to `or`, mis-granting roles by prefix, conflating read/write, and mock users accidentally carrying unintended privileges. For methods accessing an invoice by `id`, add rules checking **ownership/tenant/resource** if required by the business contract: `@WithMockUser` only grants authorities and does not restrict specific resources on its own.

### Checklist when testing a new method

1. Identify the **method to protect** and the `@PreAuthorize` expression upfront; note whether you are verifying a role, a permission, or both.
2. Write out the **literal** authority table that will exist in `Authentication`, including prefixes and casing.
3. Create at least one allowed case, one missing-role case, one missing-permission case, and one unauthenticated case, when those cases apply.
4. Invoke the method on a Spring-managed bean and ensure `@EnableMethodSecurity` is enabled.
5. Assert the **actual return value** on the allowed case and `AccessDeniedException` on blocked cases; do not merely check whether the test ran without throwing.
6. Add tests with a real principal or JWT/HTTP when business logic depends on a user repository, claims, scopes, tenants, or login.
7. If the application has a `RoleHierarchy` or changes the `ROLE_` prefix, configure a matching test fixture and re-run the test matrix.

## 9. Self-check questions

**Question 1.** A method has `@PreAuthorize("hasRole('ADMIN')")`. Do the two annotations below produce the same result?

```java
@WithMockUser(roles = "ADMIN")
@WithMockUser(authorities = "ROLE_ADMIN")
```

**Explanation:** in two independent tests, both grant the actual authority `ROLE_ADMIN` with the default prefix, so both satisfy the rule. Do not put both annotations on the same test; these are two distinct mocking options.

**Question 2.** Why does `@WithMockUser(authorities = "ADMIN")` fail `hasRole('ADMIN')`?

Because `hasRole('ADMIN')` looks for `ROLE_ADMIN` by default while `authorities = "ADMIN"` grants the exact string `ADMIN`. To keep the role rule, use `roles = "ADMIN"` or `authorities = "ROLE_ADMIN"`.

**Question 3.** Why does a test with `@WithMockUser(roles = "ADMIN")` not prove that an admin can read `invoice:read`?

Because roles and permissions are independent authorities unless the application policy adds a role hierarchy or mapping logic. You must either declare the rule for admin, or grant the exact permission the method requires.

**Question 4.** Why does a `@WithMockUser` test pass while a real JWT request returns 403?

Possible causes include the JWT not being converted into `ROLE_ADMIN`/`invoice:read` as the fixture assumed, HTTP rules differing from method rules, or a different principal/tenant. Test the method separately and test the converter/filter/HTTP layer separately to pinpoint the cause.

## 10. Practice exercises

1. Change `approveInvoice()` from `hasRole('ADMIN')` to `hasAuthority('ADMIN')`. Predict which tests will fail; run the tests and explain using actual authorities, then restore the policy.
2. Add `@PreAuthorize("hasAnyRole('ADMIN', 'AUDITOR')")` to a new method. Test `roles = "AUDITOR"`, `authorities = "AUDITOR"`, and `authorities = "ROLE_AUDITOR"`.
3. Change `auditInvoice()` from `and` to `or` in a temporary experiment. Confirm that the matrix in section 8 catches the loosened access control.
4. Create a meta-annotation `@WithMockInvoiceReader` using `@WithMockUser(authorities = "invoice:read")`, then apply it to the relevant tests; ensure missing-privilege tests remain.
5. If the project uses a custom `UserDetailsService`, write a test with `@WithUserDetails` and compare the principal type/authorities with `@WithMockUser`. Do not assume an account already exists; create a real fixture in the test environment.

## References

- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, `@WithSecurityContext`, and context setup timing.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `hasRole`, and `hasAuthority`.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `GrantedAuthority` and the default `ROLE_` prefix.
- [Spring Security — @WithMockUser API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithMockUser.html): exact definition of `roles`, `authorities`, `username`, and `setupBefore`.
- [Spring Security — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): when moving from direct service testing to HTTP request testing.