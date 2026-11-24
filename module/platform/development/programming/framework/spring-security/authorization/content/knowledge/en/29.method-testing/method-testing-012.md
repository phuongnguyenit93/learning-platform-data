# Testing a custom method-level AuthorizationManager: grant, deny, abstain, and error

## 1. Objectives and scope

This lesson tests a **custom authorization manager for method invocations** in Spring Security: when to allow execution, when to block, when to abstain from deciding, and when the policy errors. The focus is on `AuthorizationManager<MethodInvocation>`, `AuthorizationResult`/`AuthorizationDecision`, and `AuthorizationManagerBeforeMethodInterceptor` in a synchronous Java application using Spring AOP.

After this lesson, you will be able to:
- Distinguish the four outcomes **grant**, **deny**, **abstain** (returning `null`), and **error** (throwing an exception); do not conflate abstain with deny or error.
- Write unit tests checking results directly from the manager, as well as proxy-based tests proving the method actually runs or is blocked.
- Verify authorities in `Authentication`, method execution count, exact exception types, and `SecurityContext` isolation between tests.
- Detect the risk when a critical policy returns `null` without another policy guarding the method.

**Assumptions for the runnable example:** Java 17+, JUnit Jupiter 5, Spring AOP, Spring Security 6.4–6.5 (such as Spring Boot 3.5). Writing the manager as a lambda is also compatible with Spring Security 7 changes, though dependency versions and application configuration must align. This is a **method security** test; no assumptions are made about HTTP statuses or WebFlux testing.

## 2. The manager's decision contract

`AuthorizationManager` receives two inputs: a `Supplier<Authentication>`, invoked when user information is needed, and the protected target object. For pre-invocation method security, the target is a `MethodInvocation`, providing the method, arguments, and invocation target.

| Scenario | Manager returns / throws | Outcome to test at pre-method interceptor |
| --- | --- | --- |
| Grant | `new AuthorizationDecision(true)` | Call proceeds to the method, returning business result |
| Deny | `new AuthorizationDecision(false)` | Throws `AccessDeniedException` (may be subclass `AuthorizationDeniedException`); method does not run |
| Abstain | `null` | Manager renders no verdict; **not automatically equivalent to deny**. In the example with only one interceptor, the call proceeds; in real apps the entire advisor/policy chain matters |
| Policy error | e.g. `IllegalStateException` | Exception propagates; method does not run. This is a processing/decision failure, distinct from a deny verdict |

Pre-method flow in the example:

~~~text
Client → Spring AOP proxy → AuthorizationManagerBeforeMethodInterceptor
                                   │
                                   ├─ grant ────→ proceed() → service method
                                   ├─ deny ─────→ AccessDeniedException
                                   ├─ null ─────→ not blocked by this interceptor → proceed()
                                   └─ error ────→ policy exception, does not proceed()
~~~

`verify(...)` uses the result of `authorize(...)` to throw `AccessDeniedException` when denied; `authorize(...)` is used to directly observe grant/deny/abstain. Since Spring Security 6.4, `authorize(...)` is the preferred API; in 6.x, the older `check(...)` still exists as deprecated, while Spring Security 7 changes the abstract contract. **Use a lambda in the example** so you do not have to manually write different overridden method signatures across branches.

**Security point to understand:** suppose the sole manager returns `null` for a sensitive method. If no other advisor denies it, the call can slip through. For mandatory permissions, a safe approach is returning an explicit negative decision when unable to evaluate; do not rely on `null` as a default-deny mechanism.

## 3. Project setup and dependencies

The example runs in a Spring Boot Java project configured with JUnit 5. With Gradle Groovy DSL, the relevant dependencies are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Choose a Spring Boot version managing Spring Security 6.4+ (for example Boot 3.5 uses the Security 6.5 line). The snippet above is the `dependencies` section of a project that already has the Spring Boot plugin and BOM; it is not a standalone `build.gradle`. JUnit 5 and Mockito are pulled in by `spring-boot-starter-test`.

Create the file **`src/test/java/example/security/DocumentMethodAuthorizationTest.java`** with all of the following contents. No HTTP server or ApplicationContext needs to start: the test builds a real Spring AOP proxy to test the interceptor. The privilege and error branches are **intentional teaching fixtures**, not a template for connecting to a remote production authorization service.

~~~java
package example.security;

import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import org.aopalliance.intercept.MethodInvocation;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.Pointcut;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DocumentMethodAuthorizationTest {

    interface DocumentService {
        String read();
        String delete();
        String legacy();
        String unavailable();
    }

    static final class CountingDocumentService implements DocumentService {
        final AtomicInteger calls = new AtomicInteger();

        @Override
        public String read() {
            calls.incrementAndGet();
            return "read-ok";
        }

        @Override
        public String delete() {
            calls.incrementAndGet();
            return "delete-ok";
        }

        @Override
        public String legacy() {
            calls.incrementAndGet();
            return "legacy-ok";
        }

        @Override
        public String unavailable() {
            calls.incrementAndGet();
            return "unavailable-ok";
        }
    }

    // Lambda compatible with AuthorizationManager SAM type in 6.5/7.
    private static AuthorizationManager<MethodInvocation> manager() {
        return (authentication, invocation) ->
                switch (invocation.getMethod().getName()) {
                    case "read" -> new AuthorizationDecision(
                            hasAuthority(authentication.get(), "document:read"));
                    case "delete" -> new AuthorizationDecision(
                            hasAuthority(authentication.get(), "document:delete"));
                    case "legacy" -> null; // Only for testing abstain.
                    case "unavailable" ->
                            throw new IllegalStateException("policy service unavailable");
                    default -> new AuthorizationDecision(false);
                };
    }

    private static boolean hasAuthority(Authentication authentication, String required) {
        return authentication != null
                && authentication.isAuthenticated()
                && authentication.getAuthorities().stream()
                    .anyMatch(a -> required.equals(a.getAuthority()));
    }

    private static Authentication userWith(String... authorities) {
        return new UsernamePasswordAuthenticationToken(
                "alice",
                "n/a",
                Arrays.stream(authorities)
                        .map(SimpleGrantedAuthority::new)
                        .toList());
    }

    private CountingDocumentService target;
    private DocumentService service;

    @BeforeEach
    void setUp() {
        target = new CountingDocumentService();

        ProxyFactory factory = new ProxyFactory(target);
        factory.setInterfaces(DocumentService.class);
        factory.addAdvisor(new AuthorizationManagerBeforeMethodInterceptor(
                Pointcut.TRUE, manager()));
        service = (DocumentService) factory.getProxy();

        SecurityContextHolder.getContext()
                .setAuthentication(userWith("document:read"));
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    // Mockito only creates MethodInvocation for direct manager unit tests.
    private MethodInvocation invocation(String methodName) throws NoSuchMethodException {
        MethodInvocation invocation = mock(MethodInvocation.class);
        when(invocation.getMethod())
                .thenReturn(DocumentService.class.getMethod(methodName));
        return invocation;
    }

    @Test
    void unitTestObservesGrantDenyAndAbstainExactly() throws Exception {
        AuthorizationManager<MethodInvocation> policy = manager();
        Supplier<Authentication> currentUser =
                () -> SecurityContextHolder.getContext().getAuthentication();

        AuthorizationResult grant = policy.authorize(currentUser, invocation("read"));
        AuthorizationResult deny = policy.authorize(currentUser, invocation("delete"));
        AuthorizationResult abstain = policy.authorize(currentUser, invocation("legacy"));

        assertTrue(grant.isGranted());
        assertFalse(deny.isGranted());
        assertNull(abstain);
        assertEquals(0, target.calls.get()); // Calling manager does not call service.
    }

    @Test
    void unitTestObservesPolicyErrorExactly() throws Exception {
        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> manager().authorize(
                        () -> userWith("document:read"),
                        invocation("unavailable")));

        assertEquals("policy service unavailable", error.getMessage());
        assertEquals(0, target.calls.get());
    }

    @Test
    void grantRunsProtectedMethodOnce() {
        assertEquals("read-ok", service.read());
        assertEquals(1, target.calls.get());
    }

    @Test
    void denyBlocksMethodBeforeSideEffect() {
        assertThrows(AccessDeniedException.class, () -> service.delete());
        assertEquals(0, target.calls.get());
    }

    @Test
    void abstainProceedsWithOnlyThisAdvisorInstalled() {
        assertEquals("legacy-ok", service.legacy());
        assertEquals(1, target.calls.get());
    }

    @Test
    void policyErrorPropagatesBeforeSideEffect() {
        IllegalStateException error =
                assertThrows(IllegalStateException.class, () -> service.unavailable());
        assertEquals("policy service unavailable", error.getMessage());
        assertEquals(0, target.calls.get());
    }

    @Test
    void explicitDeleteAuthorityChangesDenyIntoGrant() {
        SecurityContextHolder.getContext()
                .setAuthentication(userWith("document:delete"));

        assertEquals("delete-ok", service.delete());
        assertEquals(1, target.calls.get());
    }
}
~~~

Run from a project directory with Gradle wrapper:

~~~bash
./gradlew test --tests 'example.security.DocumentMethodAuthorizationTest'
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "example.security.DocumentMethodAuthorizationTest"
~~~

Expected result: **7 tests pass** when the project has the right dependencies and no external test configuration altering proxies/security context. JUnit does not mandate a fixed stdout string; check the test report generated by Gradle to verify each case.

## 4. Understanding each testing layer

### 4.1. Manager unit tests: verifying the decision contract

`unitTestObservesGrantDenyAndAbstainExactly` calls `manager.authorize(...)` directly with a Mockito-mocked `MethodInvocation`. It verifies explicitly:

- `read` + authority `document:read` → `AuthorizationResult.isGranted() == true`.
- `delete` + only `document:read` → non-`null` result and `isGranted() == false`.
- `legacy` → exact `null`, not `new AuthorizationDecision(false)`.
- No service method executed when evaluating only the policy.

`unitTestObservesPolicyErrorExactly` forces the broken-policy branch to throw `IllegalStateException` and preserves the error message; this is not an access-denial test. Writing `assertFalse(result.isGranted())` for the error branch would wrongly collapse two distinct outcome classes.

### 4.2. Proxy-based tests: verifying real impact

The tests use `ProxyFactory` and `AuthorizationManagerBeforeMethodInterceptor`, then call **`service`, which is the proxy**, rather than calling `target` directly. The `target.calls` counter observes whether the method body executed:

| Test | Call through proxy | Primary assertion | Target run count |
| --- | --- | --- | --- |
| `grantRunsProtectedMethodOnce` | `service.read()` | Returns `"read-ok"` | 1 |
| `denyBlocksMethodBeforeSideEffect` | `service.delete()` | Throws `AccessDeniedException` | 0 |
| `abstainProceedsWithOnlyThisAdvisorInstalled` | `service.legacy()` | Returns `"legacy-ok"` | 1 |
| `policyErrorPropagatesBeforeSideEffect` | `service.unavailable()` | Throws `IllegalStateException` | 0 |
| `explicitDeleteAuthorityChangesDenyIntoGrant` | `service.delete()` with different authority | Returns `"delete-ok"` | 1 |

Key point about the **abstain** case: a `null` result proves the manager made no decision; the method continuing to run is the behavior of a test setup installing **only one advisor**. If an application also has `@PreAuthorize`, `@Secured`, or another advisor, those policies can still block the call. Therefore, never turn this test observation into a claim that `null` always permits in every application.

Key point about the **deny/error** cases: asserting a count of **0** proves the business action had no chance to cause side effects, rather than only checking the exception. When a service writes to a database, sends messages, or calls APIs, verify side effects via mocks or test database state.

### 4.3. Testing authority changes

`explicitDeleteAuthorityChangesDenyIntoGrant` calls the same `delete` method while switching the current user to authority `document:delete`. This verifies that the manager inspects actual authorities in `Authentication`, avoiding tests that merely hardcode outcomes by method name and ignore the subject.

Authorities match by exact string. `document:delete` is not automatically equivalent to `ROLE_document:delete`. `roles` in `@WithMockUser` adds the `ROLE_` prefix automatically, whereas `authorities` preserves the string verbatim; choose the matching style when moving to Spring TestContext.

### 4.4. Managing SecurityContext

`@BeforeEach` sets an authenticated `Authentication` so the interceptor sees a user; `@AfterEach` calls `SecurityContextHolder.clearContext()` to prevent one test's user from leaking into the next test. Each test gets a fresh target, proxy, and counter so tests are order-independent. Calling a method on a manually created `new` object without going through the proxy skips the interceptor and produces misleading results.

## 5. Moving from fixtures to application testing

In a real application, `@EnableMethodSecurity` activates method security; then you register an advisor with a **pointcut scoped precisely to the protected services/annotations** and the right manager. Never apply the fixture's `Pointcut.TRUE` across the entire ApplicationContext, as it would apply the test policy to unrelated beans. When replacing the default `@PreAuthorize` interceptor, configure default interceptors intentionally to prevent overlapping policies.

An integration test should obtain the service from the Spring container, call through the bean proxy, and use `@WithMockUser(authorities = "document:read")` or `@WithUserDetails` if the application requires a custom principal. Continue testing grant/deny/abstain/error scenarios and verifying side effects. `testImplementation 'org.springframework.security:spring-security-test'` is required for Spring Security test support annotations. Verify advisor ordering if the application combines `@PreAuthorize`/`@PostAuthorize`; a manager returning `null` does not disable another advisor's guard.

Suggested matrix extensions when applying production logic:

| Boundary to test | Expected outcome |
| --- | --- |
| User has exact authority | Grant |
| User lacks authority or only has a similar authority | Deny |
| Resource not owned by user | Deny; do not invoke write operation |
| Invalid authentication/principal info | Policy handles clearly, typically deny instead of NPE |
| Unmatched policy branch | Abstain **only when** another policy takes responsibility |
| External policy service times out/errors | Surface controlled error; never accidentally allow |
| Multiple advisors present | Final decision and side effects match configured order |
| Internal `this.method()` call, non-public method, or unmanaged bean | Evaluate risk of proxy bypass; do not assume interceptor still runs |

A synchronous `AuthorizationManager` should never swallow all errors with `catch (Exception) { return new AuthorizationDecision(true); }`. If the system requires **fail closed**, design explicit safe denial when the policy service is unavailable and separate infrastructure errors from missing privileges so logs/metrics remain diagnosable.

## 6. Common testing mistakes and fixes

1. **Mocking the manager to return only true/false.** This checks the interceptor minimally without testing real manager logic; keep direct manager unit tests alongside proxy tests.
2. **Equating `null` with false.** Write two separate assertions: `assertNull(abstain)` and `assertFalse(deny.isGranted())`; add proxy-level tests to verify the configured consequence.
3. **Catching every exception as AccessDenied.** Policy errors must be tested for their exact exception type and cause; `AccessDeniedException` is for denied access.
4. **Calling `new ServiceImpl()` in integration tests.** That call bypasses Spring AOP; obtain the proxied bean or explicitly construct a `ProxyFactory` like the fixture.
5. **Asserting only the exception without checking side effects.** Always prove the method did not run in deny/error branches, via counters or `verify(dependency, never())`.
6. **Forgetting to clear `SecurityContextHolder`.** Tests can pass or fail depending on order, especially when runners reuse threads.
7. **Not verifying authority format.** `ROLE_ADMIN` and `ADMIN` are two different strings; write tests with the exact authority read by the policy.
8. **Using version-incompatible APIs.** In 6.4–6.5, `authorize` is available while `check` remains deprecated abstract; in 7.x, `authorize` becomes abstract and `check` is removed. The lambda in this lesson avoids implementation differences, while calling `authorize` in tests requires at least 6.4.

## 7. Completion checklist

- [ ] All **four distinct states** covered: grant, deny, null-abstain, exception-error.
- [ ] Unit tests directly inspect `AuthorizationResult`/`null`, without coercing errors into deny.
- [ ] Proxy tests prove the method executes on grant and is blocked on deny/error.
- [ ] Null-abstain tests explicitly account for the full advisor chain rather than assuming safe defaults.
- [ ] Tests switch authorities, assert zero side effects when blocked, and clean up `SecurityContext`.
- [ ] APIs and dependencies match the Spring Security version line; Java/tests run on the configured project.
- [ ] If a critical production policy has an undecided branch, an explicit fallback/deny is designed.

## 8. API reference documentation

- [Authorization Architecture – Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): meaning of grant, deny, and abstain in `AuthorizationManager`.
- [Method Security – Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): Spring AOP proxies, interceptors, custom managers, multiple advisors.
- [Testing Method Security – Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser` and testing with authentication.
- [Javadoc AuthorizationManager (6.5)](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize`, `check`, `verify`, and version compatibility.
