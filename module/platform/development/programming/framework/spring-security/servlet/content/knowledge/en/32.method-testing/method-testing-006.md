# Setup Timing, SecurityContext Cleanup, and Test Case Isolation

**Module:** Spring Security – Servlet  
**Parent topic:** Method Testing

## 1. Problem: Same Method, Different Test Outcomes Due to Context

When writing unit or integration tests for a service with `@PreAuthorize`, `@PostAuthorize`, or using `Authentication`, outcomes depend not only on input data. They also depend on the **`SecurityContext` bound to the execution thread**.

Example:

~~~java
@PreAuthorize("hasAuthority('DOCUMENT_READ')")
public String readDocument() {
    return "document-visible";
}
~~~

This method must be invoked through a **Spring-managed proxy** with method security enabled. If the test has authority `DOCUMENT_READ`, the call succeeds; if it lacks permission, it is denied. Yet several subtle scenarios arise:

- Does `@BeforeEach` run **before** or **after** Spring Security Test sets the mock identity?
- Is `@AfterEach` guaranteed to observe that the context has already been cleared?
- Test A sets an authentication manually and forgets to clear it: Test B can be affected when the runner reuses the thread.
- Running tests in parallel, changing the global `SecurityContextHolderStrategy`, or using thread pools: the identity can land on the wrong thread or linger unexpectedly.
- Does using `@WithMockUser` on a method test prove the real HTTP filter/login configuration is correct?

This article distinguishes the **Spring TestContext and JUnit Jupiter lifecycles**, walks through **setup - usage - cleanup**, and presents Java 17/Spring Boot 3/Spring Security 6 tests so cases run **independently and order-agnostically**.

**Ultimate goal:** A test for `@PreAuthorize` must represent the exact user/authorities under test, never borrow context from another test, and never leave behind state that affects subsequent tests.

## 2. SecurityContext, SecurityContextHolder, and Threads

### 2.1. What Is SecurityContext?

In Spring Security:

- `Authentication` represents the current identity, authentication status, and `GrantedAuthority` list.
- `SecurityContext` is the container holding `Authentication`.
- `SecurityContextHolder` is the access point for the active context via a **strategy**.
- By default, the strategy usually uses **ThreadLocal**, meaning each thread has its own context. It is not a single global variable shared by all threads by default.

~~~text
JUnit test thread A
  SecurityContextHolder
    -> context A
       -> Authentication(username=alice, DOCUMENT_READ)

JUnit test thread B
  SecurityContextHolder
    -> context B
       -> Authentication(username=bob, ROLE_EDITOR)
~~~

Inside a test:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

String username = auth.getName();  // Only when auth is non-null
~~~

This is an **illustrative snippet inside a method**, not a standalone runnable Java file.

**Key takeaway:** `SecurityContextHolder.getContext()` can return an empty context; `getAuthentication()` can be `null`. Never treat "having a `SecurityContext` object" as proof that a user is logged in.

### 2.2. Why Can ThreadLocal Cause Leaks?

JUnit may reuse worker threads across cases. If a test manually calls:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

without cleaning up, a later call on **the same thread** can read the stale authentication depending on the strategy and lifecycle in use. This causes:

1. **False positives:** a test that sets no permissions still inherits permissions from an earlier test.
2. **False negatives:** a test checking anonymous behavior sees a logged-in user from another case.
3. **Flaky tests:** changing execution order or enabling parallelism makes tests randomly pass or fail.
4. **Inaccurate production simulation:** tests no longer measure access rules for an independent request.

Never share a mutable `SecurityContext` as a `static` field across tests. If you must set authentication manually, create a new context, **clean up in `finally`**, and prefer `spring-security-test` support rather than manual manipulation in every test.

## 3. When Does Spring Security Test Set Up Context?

Spring Security Test provides **`WithSecurityContextTestExecutionListener`** (part of the TestContext Framework). The listener recognizes annotations such as:

- `@WithMockUser`: creates a mock principal and authorities.
- `@WithAnonymousUser`: creates anonymous authentication for the targeted case.
- `@WithUserDetails`: loads `UserDetails` from the test application's `UserDetailsService`.
- Custom annotations using `@WithSecurityContext`.

The listener supports the **`setupBefore`** attribute with values `TestExecutionEvent.TEST_METHOD` and `TestExecutionEvent.TEST_EXECUTION`.

### 3.1. TEST_METHOD (Default)

Example:

~~~java
@Test
@WithMockUser(username = "alice", authorities = "DOCUMENT_READ")
void canReadDocument() {
    // Spring Security Test already set up the user before the test method.
}
~~~

When `setupBefore` is omitted, `@WithMockUser` uses **`TEST_METHOD`**. With JUnit Jupiter + `SpringExtension`, the listener sets the security context during **`beforeTestMethod`**, which is **before JUnit `@BeforeEach`**.

~~~text
SpringExtension / TestContextManager.beforeTestMethod
    -> WithSecurityContextTestExecutionListener sets up Authentication
JUnit @BeforeEach
JUnit @Test
JUnit @AfterEach
SpringExtension / TestContextManager.afterTestMethod
    -> WithSecurityContextTestExecutionListener cleans up SecurityContext
~~~

Consequence: if `@BeforeEach` needs to call a `@PreAuthorize`-protected service, **the default setting is usually right** because the identity already exists during test fixture setup.

### 3.2. TEST_EXECUTION: Only After @BeforeEach

Example:

~~~java
@Test
@WithMockUser(
    username = "bob",
    authorities = "DOCUMENT_READ",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void canReadAsBob() {
    // Context is set up right before @Test starts.
}
~~~

With `TEST_EXECUTION`, the listener sets up the context during **`beforeTestExecution`**:

~~~text
SpringExtension / TestContextManager.beforeTestMethod
JUnit @BeforeEach
SpringExtension / TestContextManager.beforeTestExecution
    -> WithSecurityContextTestExecutionListener sets up Authentication
JUnit @Test
SpringExtension / TestContextManager.afterTestExecution
JUnit @AfterEach
SpringExtension / TestContextManager.afterTestMethod
    -> listener cleanup
~~~

Consequence: inside `@BeforeEach`, **the authentication created by this annotation does not exist yet**. This can be desirable when setup must run unauthenticated without accidentally receiving permissions or touching `SecurityContext`. However, if setup calls a protected service, the test may fail in `@BeforeEach` before the test body ever runs.

**Do not misunderstand:** `TEST_EXECUTION` does not mean `SecurityContext` is created after `@Test` starts. It is set up **right before** the test method executes, after `@BeforeEach` callbacks in the standard lifecycle.

### 3.3. Timing Table

| Phase | `TEST_METHOD` (default) | `TEST_EXECUTION` |
| --- | --- | --- |
| `@BeforeAll` | Do not expect mock user from method annotations. | Do not expect mock user. |
| `@BeforeEach` | Can access authentication created by annotation. | Does not yet have authentication created by annotation. |
| `@Test` body | Has authentication. | Has authentication. |
| `@AfterEach` | Authentication is usually still present while hook runs. | Authentication is usually still present while hook runs. |
| After `TestContextManager.afterTestMethod` | Listener cleans up context. | Listener cleans up context. |

**Order note:** `@AfterEach` belongs to JUnit, whereas `WithSecurityContextTestExecutionListener` cleanup normally happens in **`afterTestMethod`**, after the `@AfterEach` hook. Therefore, asserting "context must already be empty inside `@AfterEach`" is a **wrong assumption**. To prove isolation, test initial state without an annotation, rely on listener cleanup, and never depend on test order.

Never use `@BeforeAll` to read method-level `@WithMockUser`. `@BeforeAll` can execute before per-method context setup events.

## 4. Automatic Cleanup: Who Is Responsible and Its Limits

### 4.1. WithSecurityContextTestExecutionListener

When running with `SpringExtension` / Spring TestContext and `spring-security-test`:

1. The listener detects matching annotations.
2. It constructs the test security context according to `setupBefore`.
3. The context is exposed via `TestSecurityContextHolder` and `SecurityContextHolder` per Spring Security Test mechanics.
4. After the test, the listener cleans up the context (via `TestSecurityContextHolder.clearContext()`) at the proper lifecycle phase.

This makes `@WithMockUser` tests independent without needing manual `@AfterEach` hooks just to clear mock users. Still, **tests can leak other state**: static fields, DB records, caches, mutable singleton beans, thread pool tasks, or unreset mocks.

Never use `@DirtiesContext` solely to clear `SecurityContextHolder`: that annotation marks the **Spring `ApplicationContext`** for recreation, wasting resources without changing `ThreadLocal` management rules.

### 4.2. How Does TestSecurityContextHolder Differ from SecurityContextHolder?

`SecurityContextHolder` is the API used in application code. **`TestSecurityContextHolder`** is a utility in `spring-security-test`; it assists test context management and integrates with web testing tools.

When proactively setting context in a test:

~~~java
TestSecurityContextHolder.setContext(context);
~~~

When cleaning up:

~~~java
TestSecurityContextHolder.clearContext();
~~~

`TestSecurityContextHolder.clearContext()` clears both the test context **and** the `SecurityContextHolder` context. Calling only `SecurityContextHolder.clearContext()` after setting a context via `TestSecurityContextHolder` can leave behind another copy of the test context referenced by Spring Security Test helpers.

**Preference:** use `@WithMockUser`/listener annotations for standard tests; if forced to set test context manually, use **one consistent mechanism** and clean up with `finally`.

### 4.3. Cleanup Does Not Solve Every Form of Isolation

Cleanup occurs inside the test lifecycle managed by the listener. Do not rely on it to:

- Clean up a `SecurityContext` manually installed onto **another thread** without controlled propagation/copying.
- Restore a **global `SecurityContextHolderStrategy`** mutated by a test without restoring it.
- Delete persistent database rows or singleton store entries.
- Reset a static `Authentication` held manually by a test.
- Prevent side effects from a background task still running **after** the test finishes.

Spring test cleanup is a **necessary condition for security context isolation**, not magic that wipes out all shared state.

## 5. Java 17 / Spring Boot 3.3.5 Project: Method Security and JUnit Jupiter

The example is complete enough to run with Maven and Spring Security 6.x included in Spring Boot 3.3.5. This version is chosen to illustrate syntax; production should use a supported release with security patches applied.

**Functionality:** a service allowing reads only with `DOCUMENT_READ` and edits only with `ROLE_EDITOR`, plus tests for authorized/denied/timing/cleanup behavior. No IdP or database is required.

Layout:

~~~text
method-context-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── MethodContextApplication.java
    │   └── DocumentService.java
    └── test/java/demo/
        ├── DocumentServiceSecurityTest.java
        └── SecurityContextTimingTest.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>method-context-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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

`spring-boot-starter-security` brings in the required security modules. `spring-boot-starter-test` includes JUnit Jupiter, Spring Test, AssertJ, and test utilities; `spring-security-test` supplies `@WithMockUser`, `TestSecurityContextHolder`, and the corresponding `TestExecutionListener`.

### 5.2. src/main/java/demo/MethodContextApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodContextApplication.class, args);
    }
}
~~~

`@EnableMethodSecurity` activates processing of annotations like `@PreAuthorize`. Without this annotation, tests can call the service successfully even when it ought to be forbidden, creating **false positives** if tests only assert return values without checking the deny branch.

### 5.3. src/main/java/demo/DocumentService.java

~~~java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize("hasAuthority('DOCUMENT_READ')")
    public String readDocument() {
        return "document-visible";
    }

    @PreAuthorize("hasRole('EDITOR')")
    public String editDocument() {
        return "document-edited";
    }
}
~~~

**Important:** tests must inject the **Spring-managed bean** `DocumentService`. Calling `new DocumentService()` directly bypasses the method-security proxy, so `@PreAuthorize` may not run. Likewise, **self-invocation** from one method on the bean calling another protected method on itself can bypass the proxy depending on configuration; design services and tests along real call paths.

### 5.4. src/test/java/demo/DocumentServiceSecurityTest.java

~~~java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.TestSecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class DocumentServiceSecurityTest {

    @Autowired
    DocumentService documents;

    @Test
    @WithMockUser(username = "reader", authorities = "DOCUMENT_READ")
    void readerMayRead() {
        assertThat(documents.readDocument())
            .isEqualTo("document-visible");
    }

    @Test
    @WithMockUser(username = "editor", roles = "EDITOR")
    void editorMayEdit() {
        assertThat(documents.editDocument())
            .isEqualTo("document-edited");
    }

    @Test
    @WithMockUser(username = "writer", authorities = "DOCUMENT_WRITE")
    void insufficientAuthorityIsDenied() {
        assertThatThrownBy(documents::readDocument)
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void noAnnotationStartsWithoutAuthentication() {
        assertThat(
            SecurityContextHolder.getContext().getAuthentication()
        ).isNull();
    }

    @Test
    void manualContextMustBeClearedInFinally() {
        try {
            var context = SecurityContextHolder.createEmptyContext();
            var authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                    "manual-reader",
                    "N/A",
                    List.of(
                        new SimpleGrantedAuthority("DOCUMENT_READ")
                    )
                );

            context.setAuthentication(authentication);
            TestSecurityContextHolder.setContext(context);

            assertThat(documents.readDocument())
                .isEqualTo("document-visible");

            assertThat(
                SecurityContextHolder.getContext()
                    .getAuthentication().getName()
            ).isEqualTo("manual-reader");
        } finally {
            // Clean up both test holder and application holder.
            TestSecurityContextHolder.clearContext();
        }

        assertThat(
            SecurityContextHolder.getContext().getAuthentication()
        ).isNull();
    }
}
~~~

**Explanation of each test:**

1. `readerMayRead`: the annotation creates a mock principal with `DOCUMENT_READ`; the method security proxy permits the call.
2. `editorMayEdit`: `roles = "EDITOR"` creates authority `ROLE_EDITOR`, matching `hasRole("EDITOR")`.
3. `insufficientAuthorityIsDenied`: `DOCUMENT_WRITE` does not grant `DOCUMENT_READ`; verifies Spring method security truly denies access.
4. `noAnnotationStartsWithoutAuthentication`: no `@WithMockUser`; under the cleaned standard TestContext flow, the test expects no authentication. **Never rely on execution order** so that this test "runs after" a specific test.
5. `manualContextMustBeClearedInFinally`: shows the case where manual context setup is unavoidable; uses `createEmptyContext()` and `try/finally`, without sharing a `static` context.

`@WithMockUser` **does not verify passwords or call `UserDetailsService`**; it only creates a simulated authentication for authorization testing. To test real login, write integration tests with an authentication provider, `formLogin()`, and the corresponding HTTP filter chain.

### 5.5. src/test/java/demo/SecurityContextTimingTest.java

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class SecurityContextTimingTest {

    private String nameSeenDuringBeforeEach;

    @BeforeEach
    void capturePrincipalBeforeTest() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        nameSeenDuringBeforeEach =
            authentication == null ? null : authentication.getName();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOCUMENT_READ")
    void defaultTestMethodIsAlreadySetBeforeBeforeEach() {
        assertThat(nameSeenDuringBeforeEach).isEqualTo("alice");

        assertThat(
            SecurityContextHolder.getContext()
                .getAuthentication().getName()
        ).isEqualTo("alice");
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = "DOCUMENT_READ",
        setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void lateSetupHappensAfterBeforeEach() {
        assertThat(nameSeenDuringBeforeEach).isNull();

        assertThat(
            SecurityContextHolder.getContext()
                .getAuthentication().getName()
        ).isEqualTo("bob");
    }

    @Test
    void withoutAnnotationThereIsNoUser() {
        assertThat(nameSeenDuringBeforeEach).isNull();
        assertThat(
            SecurityContextHolder.getContext().getAuthentication()
        ).isNull();
    }
}
~~~

**Meaning:** both `@WithMockUser` tests have authentication inside the `@Test` body, yet only the default setup lets `@BeforeEach` observe `alice`. With `TEST_EXECUTION`, `@BeforeEach` does not see `bob` yet. The third test confirms no identity is inherited from other tests. **No `@TestMethodOrder` is needed** to force a particular order among these three tests.

### 5.6. Run Command and Expected Outcome

In the directory containing `pom.xml`:

~~~bash
mvn test
~~~

JUnit Jupiter is expected to run **8 tests** (5 in `DocumentServiceSecurityTest`, 3 in `SecurityContextTimingTest`) and report **0 failures, 0 errors** when configuration and dependencies match. This is the **expected result**, not output from an actual run.

To run a single class:

~~~bash
mvn -Dtest=SecurityContextTimingTest test
~~~

The Maven command above demonstrates checking setup order before/after `@BeforeEach`. On some shells, option values with special characters must be quoted; none appear here.

**Scope note:** these tests cover **Spring service method security**, not URL authorization, CSRF, Servlet filter order, or session behavior. Use separate `MockMvc` tests when testing HTTP requests.

## 6. @BeforeEach and @AfterEach: Common Design Mistakes

### 6.1. Test Fixtures Needing an Identity Before Setup

Example of a `@BeforeEach` calling a protected service:

~~~java
@BeforeEach
void createFixtures() {
    // Suppose fixtureService.prepareForCurrentUser() has @PreAuthorize.
    fixtureService.prepareForCurrentUser();
}
~~~

This is an **illustrative standalone snippet**, lacking the full classes/beans to run. With default `@WithMockUser` (`TEST_METHOD`), setup can call the protected method as the mock user. With `TEST_EXECUTION`, setup runs **before the mock user is installed**, so calling the service may be denied. Choose the timing based on the test's real requirements.

### 6.2. Setup Should Not Depend on Test Permissions

Sometimes test data must be created as an administrative step **outside the behavior of the user under test**. If `@BeforeEach` accidentally receives user permissions from the default setup, fixtures may inherit the wrong identity or fail to expose an authorization bug.

Two ways to handle this:

- Use `setupBefore = TEST_EXECUTION` so setup runs before the annotation sets the user, while keeping fixtures safe when unauthenticated.
- Seed fixtures through repositories/test data builders independent of the current user, then execute the action under the user declared for the `@Test` body.

Never use "every test is admin" just because fixtures require permissions: that easily hides real authorization bugs.

### 6.3. Do Not Assert Cleanup Inside @AfterEach

Example of a **wrong assumption**:

~~~java
@AfterEach
void assertContextAlreadyCleared() {
    // Do not enforce this condition when using @WithMockUser:
    // assertThat(SecurityContextHolder.getContext()
    //     .getAuthentication()).isNull();
}
~~~

Because the listener usually cleans up after `@AfterEach`, this assertion can fail even when cleanup works properly.

**If `@AfterEach` needs the identity to tear down fixtures**, verify the actual timing; prefer keeping fixture teardown independent of the principal when possible so security state does not affect teardown. Separate responsibilities: tear down data in JUnit hooks, and let the Spring Security Test listener handle `SecurityContext` teardown.

### 6.4. Do You Need to Add @AfterEach clearContext() Yourself?

For tests **using only `@WithMockUser` and Spring TestContext properly**, you usually **do not need** to add:

~~~java
@AfterEach
void cleanup() {
    SecurityContextHolder.clearContext();
}
~~~

The listener cleans up automatically during the lifecycle. If a test **manually sets** the context or runs code outside the listener lifecycle, use `try/finally`/proper teardown. When `TestSecurityContextHolder` is involved, prefer `TestSecurityContextHolder.clearContext()` so neither holder retains authentication.

**Never** place sloppy manual cleanup inside `@BeforeEach` alongside `TEST_METHOD`, as it can wipe out the mock user the listener just installed, causing the test to suddenly lose permissions.

## 7. @WithMockUser, @WithUserDetails, and @WithSecurityContext

### 7.1. @WithMockUser

~~~java
@WithMockUser(
    username = "auditor",
    authorities = {"DOCUMENT_READ", "AUDIT_VIEW"}
)
~~~

Creates a test authentication with a mock-style principal. Does not query DBs, does not check passwords, and does not automatically match custom application principals. When using `roles`, the framework prepends the default `ROLE_` prefix. Do not pass `ROLE_ADMIN` into `roles` when the annotation expects an unprefixed role name; use `roles = "ADMIN"` or `authorities = "ROLE_ADMIN"` as needed.

### 7.2. @WithUserDetails

If the system has a `UserDetailsService` configured in the test context, you can use:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void readsRealUserDetailsFromTestService() {
    // UserDetails is looked up from the UserDetailsService bean.
}
~~~

This is an **additional snippet**, not part of the complete project in section 5 (that example does not define a `UserDetailsService` with user `alice`). `@WithUserDetails` fits when methods depend on custom `UserDetails` or user attributes, yet it still **does not verify real password login**.

When setting up at `TEST_EXECUTION`, the listener looks up the user and builds the context after `@BeforeEach`. This is helpful if the fixture user is created in `@BeforeEach` and must exist before lookup. Conversely, if the user is created inside the test body, lookup still happens too early.

### 7.3. Custom @WithSecurityContext

When `@WithMockUser` cannot express the full authentication (such as a custom principal with `tenantId`), you can define an annotation using `@WithSecurityContext(factory = ...)` to build a custom security context. The factory must create a **fresh context per test** and an authentication with schema-accurate authorities. Never keep a mutable static context or share the same `Authentication` instance across cases.

Model:

~~~text
@WithTenantUser(tenant = "alpha", role = "READER")
        |
        v
WithSecurityContextFactory creates principal + authorities
        |
        v
SecurityContextHolder.createEmptyContext()
        |
        v
TestSecurityContextHolder.setContext(...)
        |
        v
Test method -> listener cleanup
~~~

This is an architectural diagram, not standalone API code. When creating an annotation, use the right `Retention(RUNTIME)`, `Target`, and imports. Even when a principal carries a tenant ID, the service must still verify **the resource belongs to that tenant**; merely holding a tenant attribute is not sufficient authorization on its own.

## 8. Method Security Tests vs. Servlet HTTP / MockMvc Tests

**Method tests** call the Spring-managed service directly:

~~~java
@WithMockUser(authorities = "DOCUMENT_READ")
@Test
void readAsAuthorizedUser() {
    assertThat(documents.readDocument())
        .isEqualTo("document-visible");
}
~~~

They verify AOP/method authorization. They **do not** run the entire HTTP filter chain.

**MockMvc tests** dispatch a simulated HTTP request through MVC and, when integrated with Spring Security, verify filters/sessions/CSRF/URL policies:

~~~java
// Illustrative snippet in a test with MockMvc mvc configured with Security.
// Endpoint /api/documents must exist; this is not part of the section 5 project.
mvc.perform(get("/api/documents")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("DOCUMENT_READ")
        )))
    .andExpect(status().isOk());
~~~

With MVC tests:

- `@AutoConfigureMockMvc` + Spring Boot Security test integration normally configures filters; if using `MockMvcBuilders.standaloneSetup(...)`, you must explicitly integrate `springSecurity()` and the proper filter chain.
- `@WithMockUser` sets the identity in TestContext; `.with(user(...))` sets the principal for **a specific `MockMvc` request**. Never mistake either for real login.
- `csrf()` from `SecurityMockMvcRequestPostProcessors` creates a valid test CSRF token for POSTs when needed; never use it to mint tokens in production clients.
- `@WithMockUser` by itself does not prove Servlet session lifecycle, login redirects, token repositories, or logout.

To test controller and service together, write `@SpringBootTest` + `@AutoConfigureMockMvc` or an appropriate test slice; ensure security config and filters actually participate. Do not mock the `@PreAuthorize`-annotated service itself and assume the test verified method interception: mocks can bypass method-security advice.

## 9. Parallel Execution and Thread Switching: Two Different Isolation Layers

### 9.1. JUnit Parallel Execution

If JUnit is configured for parallel execution, tests may run across multiple threads. Under the default `ThreadLocal` strategy, thread A's context does not automatically appear on thread B. This helps, yet **does not replace cleanup**: thread pools can reuse threads.

Never switch `SecurityContextHolder.setStrategyName(SecurityContextHolder.MODE_GLOBAL)` in a test to "stop losing permissions" during parallel runs. `MODE_GLOBAL` shares context JVM-wide and can leak authentication across tests and requests.

`MODE_INHERITABLETHREADLOCAL` can copy context to child threads created at a specific moment, yet it is unsuitable as a default with **thread pools**, because pool threads are long-lived and reused. Do not rely on it as a fix for `@Async`/executors.

If a test genuinely changes the global `SecurityContextHolderStrategy` to verify special behavior, it must **restore the previous strategy**, stay isolated from parallel tests, and account for side effects on running code. Prefer not changing the global strategy in unit tests.

### 9.2. @Async, CompletableFuture, and Executors

Suppose a test holds user `alice` on the JUnit thread, while the service submits work to a thread pool:

~~~text
JUnit thread: SecurityContext(alice)
    |
    +-> Executor worker thread: not guaranteed to have alice context
~~~

A raw `new Thread(...)` or `CompletableFuture.supplyAsync(...)` does not automatically propagate `SecurityContext` safely. Spring Security provides helpers such as `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, and `DelegatingSecurityContextExecutor` to **set and clean up context around tasks**.

Async tests must:

1. Determine whether context genuinely needs to propagate to the task.
2. Use executors/wrappers matching the contract instead of setting global context.
3. Wait for the task to finish inside the test and avoid letting it outlive the test.
4. Assert user/authorities inside the worker thread if required.
5. Clean up thread-bound state in `finally` when performing propagation manually.
6. Avoid relying on random timing or non-deterministic scheduling.

**Warning:** a test asserting context only on the JUnit thread **proves nothing** about how the service enforces authorization on another thread.

### 9.3. Distinguishing SecurityContext Leaks from Test Data Leaks

Even when `SecurityContext` is cleaned up, two tests sharing `@SpringBootTest` can share the **ApplicationContext cache**, database, filesystem, singletons, or in-memory repositories. For instance, if Test A inserts Alice's record without rolling back, Test B may observe that data.

Solutions depend on the state source:

- DB: transaction rollback/test cleanup or isolated fixtures.
- Stateful beans: reset via test/fixture APIs, create fresh beans, or structure separate contexts sensibly.
- Mockito mocks: reset or reinitialize via Spring Test integration.
- Static variables: minimize them, and reset explicitly if unavoidable.
- `SecurityContext`: use listeners + `TestSecurityContextHolder.clearContext()` when manipulating manually.
- Async work: await task completion and clean up context inside workers.

**`@DirtiesContext` is a last resort** when an `ApplicationContext` truly must be rebuilt; it is not a substitute for tests managing mutable state cleanly.

## 10. Anti-Patterns and Fixes

| Anti-pattern | Consequence | Right Approach |
| --- | --- | --- |
| Manually calling `SecurityContextHolder.getContext().setAuthentication(...)` without cleanup. | Leaks when threads are reused. | Use `@WithMockUser` or a new context + `try/finally`. |
| `@BeforeEach` calls a protected service while annotation sets `TEST_EXECUTION`. | Setup lacks the declared user. | Use `TEST_METHOD` or decouple fixtures from authentication. |
| Asserting empty context inside `@AfterEach` of a `@WithMockUser` test. | Misunderstands listener cleanup timing. | Respect real lifecycle; `TestExecutionListener` cleans up after the test. |
| Using `@TestMethodOrder` so Test B inherits Test A's identity. | Order-dependent tests and hidden bugs. | Each test declares its own identity. |
| Using `new DocumentService()` to test `@PreAuthorize`. | Bypasses proxy, false positive. | Autowire the Spring-managed service. |
| Testing only allowed cases without denied cases. | `@EnableMethodSecurity` disabled can still leave tests green. | Include `AccessDeniedException` tests for missing permissions. |
| Using `@WithMockUser` to claim login/password provider works. | Does not test real authentication. | Write separate login/filter integration tests. |
| Using `MODE_GLOBAL` or a static `SecurityContext` to share across a suite. | Identities bleed across cases/threads. | `ThreadLocal` + per-test context + cleanup. |
| Assuming `@WithMockUser` propagates into executor threads automatically. | Tasks may lack auth or read stale context. | Propagation wrapper with cleanup + async tests. |
| Putting `@DirtiesContext` on every test to "clear the user". | Slow tests, does not fix thread leaks properly. | Rely on listeners and clean specific state. |
| Using one overly broad role for every test. | Misses least-privilege verification. | Grant each test the minimum role/authorities for its scenario. |
| `@WithUserDetails` when the test context lacks the user. | Lookup fails before the `@Test` body runs. | Configure `UserDetailsService` and fixtures matching lifecycle timing. |

## 11. QA Checklist for Truly Independent Tests

Before merging a test class with method security:

1. `spring-security-test` is in **test scope**; TestContext/Extension is properly active.
2. `@EnableMethodSecurity` is enabled in the context when testing `@PreAuthorize`.
3. Services are called through **beans/proxies**, never instantiated with `new`.
4. Each test explicitly declares `@WithMockUser`, `@WithUserDetails`, or an appropriate authentication factory.
5. Choose `setupBefore` carefully: if context is needed in `@BeforeEach`, use default `TEST_METHOD`; if only needed in the test body, consider `TEST_EXECUTION`.
6. Do not assume context is already cleared inside `@AfterEach`; understand the Spring listener cleans up after this hook.
7. Never store shared `SecurityContext` or mutable `Authentication` in static fields.
8. Every manual setup has **`finally`** cleaning up the test holder too when needed.
9. Include both **allowed** and **denied** tests to catch false greens when method security is inactive.
10. No dependence on test order or execution thread.
11. If running async code, verify propagation and task completion; never change the global strategy casually.
12. If DBs/stateful services are present, isolate fixtures independently of the security context.
13. Use separate `MockMvc` tests for URL authorization/CSRF/session instead of inferring them from service tests.
14. Never log passwords, tokens, session IDs, or real secrets in test logs.
15. The test class and entire suite can run repeatedly in different orders without manual resets outside fixture contracts.

## 12. Self-Check Questions

**Question 1.** With default `@WithMockUser`, is the user set before or after `@BeforeEach`?

**Answer:** Before `@BeforeEach`, via TestContext `beforeTestMethod` (`TEST_METHOD`).

**Question 2.** If you want `@BeforeEach` to have no mock user while the `@Test` body has one, what should you do?

**Answer:** Set `setupBefore = TestExecutionEvent.TEST_EXECUTION`. The listener then sets up the context in `beforeTestExecution`, after JUnit setup.

**Question 3.** Why shouldn't you assert an empty `SecurityContext` right inside `@AfterEach`?

**Answer:** Spring Security Test's listener normally cleans up in `afterTestMethod`, after the `@AfterEach` hook in the JUnit/SpringExtension lifecycle.

**Question 4.** Does `@WithMockUser(username = "alice")` verify Alice's password against the DB?

**Answer:** No. It creates a simulated authentication for testing. To test real login, test the authentication provider/HTTP flow separately.

**Question 5.** Why must tests reading documents use `@Autowired DocumentService`?

**Answer:** `@PreAuthorize` is enforced by Spring method-security AOP/proxy. Manually instantiating the service with `new` bypasses the security advice.

**Question 6.** Is `SecurityContextHolder.clearContext()` always sufficient if a test used `TestSecurityContextHolder.setContext()`?

**Answer:** Do not rely on that. When using the test holder, call `TestSecurityContextHolder.clearContext()` to clear both holders per the utility's contract.

**Question 7.** If a test runs on the JUnit thread with user Alice, does a `CompletableFuture` on an executor automatically have Alice?

**Answer:** No. `ThreadLocal` context does not propagate safely across arbitrary executors by default; use propagation wrappers/context-aware executors and cleanup.

**Question 8.** How does `@DirtiesContext` differ from clearing `SecurityContext`?

**Answer:** `@DirtiesContext` tells Spring to rebuild the cached `ApplicationContext`. Clearing `SecurityContext` removes authentication bound to the thread/test; those are two completely different kinds of state.

---

**Conclusion:** Method testing in Spring Security Servlet requires controlling **when `Authentication` is set**, **when cleanup happens**, and **per-test isolation**. Default `@WithMockUser` runs **before `@BeforeEach`**; `TEST_EXECUTION` runs **after `@BeforeEach`, right before the `@Test` body**. Spring Security Test's listener cleans up after the test; for manual setup, use a fresh context and `finally`. Keep both authorized and denied tests, never share mutable context, stay order-independent, and test async/HTTP behavior at their respective layers.