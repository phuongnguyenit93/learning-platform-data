# Method testing: calling a Spring bean through its proxy to verify security annotations take effect

## 1. Goal and scope

When placing `@PreAuthorize` on a method, seeing the annotation in source code **does not prove** that access control is being checked. The test must invoke the method through a **Spring-managed bean**, so that the call goes through the Spring Security proxy and interceptor.

After this lesson, you will be able to:

- Enable method security with `@EnableMethodSecurity`.
- Obtain a real bean from `ApplicationContext` with `@Autowired` and verify that it is proxied.
- Use `@WithMockUser`/`@WithAnonymousUser` to test both **allowed** and **denied** cases.
- Distinguish real security testing from calling `new Service()`, plain Mockito, or self-invocation that bypasses the proxy.
- Diagnose a test that still passes green even when the annotation is not executed.

The scope is **Spring Security servlet/method security** on Java 17+, using Spring Boot 3.5.7 and JUnit Jupiter examples. There is no need to start an HTTP server or call an endpoint: the method boundary of a Spring bean is the object under test.

## 2. Mechanism to understand before writing tests

`@EnableMethodSecurity` registers the authorization components for methods, with `@PreAuthorize` supported by default. Simply adding `spring-boot-starter-security` **does not automatically enable** method security.

For the default Spring AOP proxy mechanism, the correct call flow is:

```text
JUnit test
    |
    | @Autowired ReportService
    v
Spring-managed proxy
    |
    | @PreAuthorize -> read Authentication from SecurityContext
    |     + sufficient privileges: proceed
    |     + insufficient privileges: throw AccessDeniedException
    v
ReportService executes the real method
```

Because the check resides in the proxy, the two calls below are not equivalent:

- `reportService.readReport()` with `reportService` **injected by Spring**: the security mechanism has a chance to intercept.
- `new ReportService().readReport()`: merely invokes a plain Java object, with no Spring AOP advice.

When testing with `@WithMockUser`, Spring Security Test creates an `Authentication` in the test thread's `SecurityContextHolder`. Username and authorities are simulated; no real account in a database is needed. This is suitable for testing **method-level authorization rules**, though it does not prove that the full login flow, JWT, or HTTP filters work properly.

**Both assertion groups are necessary:** the authorized case must return the expected result; the unauthorized case must be denied. Checking only the success outcome can leave tests green even when `@PreAuthorize` is disabled.

## 3. Complete runnable example

Create a Maven project with the following structure:

```text
method-security-proxy-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/methodsecurity/
    │   ├── DemoApplication.java
    │   └── ReportService.java
    └── test/java/com/example/methodsecurity/
        └── ReportServiceTest.java
```

### 3.1. Declare dependencies

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>method-security-proxy-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
```

Purpose: the security starter provides the authorization mechanism; the test starter provides JUnit 5 and AssertJ; `spring-security-test` provides `@WithMockUser`, `@WithAnonymousUser`, and the listener that populates the security context for tests. `spring-boot-starter-web` is not needed because the example tests the service directly.

### 3.2. Enable method security in the Spring context

File `src/main/java/com/example/methodsecurity/DemoApplication.java`:

```java
package com.example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@SpringBootApplication` scans for `@Service` in the same package and subpackages. `@EnableMethodSecurity` activates the interceptor for `@PreAuthorize`. In a real project, this annotation can also be placed on an appropriate `@Configuration` class.

### 3.3. Create a bean with clear authorization rules

File `src/main/java/com/example/methodsecurity/ReportService.java`:

```java
package com.example.methodsecurity;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "NOI_DUNG_BAO_CAO";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String approveReport() {
        return "APPROVED";
    }
}
```

Explanation of the two expressions:

- `hasAuthority('report:read')` requires an authority with the **exact** name `report:read`.
- `hasRole('ADMIN')` checks for the `ROLE_ADMIN` authority by default convention. With `@WithMockUser(roles = "ADMIN")`, the test is granted the corresponding authority; there is no need to write `ROLE_` in the `roles` parameter.

Both methods are `public` and non-`final` to align with how Spring AOP proxies work. The return values are fixed strings so we can focus on whether the method is permitted to execute or not.

### 3.4. Call the Spring-created bean in a JUnit test

File `src/test/java/com/example/methodsecurity/ReportServiceTest.java`:

```java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(classes = DemoApplication.class)
class ReportServiceTest {
    @Autowired
    private ReportService reportService;

    @Test
    void injectedServiceIsAnAopProxy() {
        assertThat(AopUtils.isAopProxy(reportService)).isTrue();
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanReadReport() {
        assertThat(reportService.readReport())
                .isEqualTo("NOI_DUNG_BAO_CAO");
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void userWithoutReadAuthorityIsDenied() {
        assertThatThrownBy(() -> reportService.readReport())
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithAnonymousUser
    void anonymousUserIsDenied() {
        assertThatThrownBy(() -> reportService.readReport())
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanApproveReport() {
        assertThat(reportService.approveReport())
                .isEqualTo("APPROVED");
    }

    @Test
    @WithMockUser(roles = "USER")
    void nonAdminCannotApproveReport() {
        assertThatThrownBy(() -> reportService.approveReport())
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

**Key point:** the `reportService` field is received from `@Autowired`, not instantiated with `new`, and not replaced by a mock. Because the test runs with a real Spring context, calls pass through the bean's proxy.

Meaning of each test group:

1. `injectedServiceIsAnAopProxy` verifies that the injected object is an AOP proxy. This is a necessary check in the example; it is **not sufficient** to assert who a specific annotation blocks.
2. `readerCanReadReport` proves that a valid authority is not falsely blocked.
3. `userWithoutReadAuthorityIsDenied` proves that a different authority is insufficient to pass `@PreAuthorize`.
4. `anonymousUserIsDenied` proves that an anonymous user cannot read.
5. The two `approveReport` tests properly distinguish the `ADMIN` and `USER` role rules.

`AccessDeniedException` is an appropriate superclass for assertions: Spring Security versions may use subtypes to represent a denied decision. The test above uses `@WithAnonymousUser` to create an explicit anonymous state; if `Authentication` is omitted completely, the failure path may differ, such as `AuthenticationCredentialsNotFoundException`.

### 3.5. Run and interpret the results

In the directory containing `pom.xml`, use JDK 17+ and Maven:

```bash
java -version
mvn test
```

Expected result: Maven Surefire runs **6 tests**, with no failures or errors. The summary line typically looks like:

```text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
```

This is the expected outcome of the example, not a log copied from an actual run. There is no need to run a web application, send tokens, or log in to execute these six tests.

To prove to yourself that the tests are sensitive enough, try **temporarily** removing `@EnableMethodSecurity` and re-running `mvn test`: the assertions expecting denial will fail because there is no longer an authorization interceptor. Then restore the annotation. Similarly, if you temporarily remove `@PreAuthorize` from `readReport`, the missing-authority test must fail. This is how to avoid "false green" tests.

## 4. Why do direct calls often produce wrong results?

### 4.1. `new` bypasses the Spring proxy

The snippet below **only illustrates a test design flaw** and does not replace the tests in section 3:

```java
// Illustration: this code lives inside a Java method.
ReportService manuallyCreated = new ReportService();
String result = manuallyCreated.readReport();
// The call above does not go through the Spring Security AOP proxy.
```

An annotation by itself does not execute automatically when the JVM invokes a method. `new` creates a plain instance; Spring has no opportunity to apply an interceptor, so a test that only asserts `result` will not detect missing security.

### 4.2. Self-invocation also bypasses advice

Suppose we add an unprotected method to `ReportService`:

```java
// Illustration snippet inside ReportService only; DO NOT add to the real application.
public String insecureInternalCall() {
    return this.readReport();
}
```

If external code calls `reportService.insecureInternalCall()`, the initial call goes through the proxy. However, `this.readReport()` runs **inside the target object** and does not go back through the proxy to apply `@PreAuthorize` on `readReport`. This can become an authorization vulnerability if the outer method can be called by someone without sufficient privileges.

The most controllable design is to move the protected operation into **a separate bean** and let the calling bean invoke it through a Spring-injected dependency. For example, `ReportFacade` injects `ReportService` and calls `reportService.readReport()`; at the boundary between the two beans, the call goes through `ReportService`'s proxy. Do not try to fix self-invocation merely by adding `@WithMockUser` to the test.

### 4.3. Mocks and pure unit tests serve a different purpose

If you use Mockito's `@Mock`/`@InjectMocks` to test internal logic, you usually only exercise Java code or stubbed behavior without building Spring's security configuration. Those tests are valuable for verifying business logic, but **cannot replace** method security tests through a Spring context.

If you mock **the protected service itself** in the context, calls may not pass through the real method or annotation. To test authorization annotations, keep the bean carrying the annotation as a real bean; mock repositories or underlying dependencies when needed. In this example, no mocks are required.

## 5. Common conditions and pitfalls

| Symptom | Possible cause | How to check or fix |
| --- | --- | --- |
| Unauthorized user still receives data | Forgot `@EnableMethodSecurity` or instantiated object with `new` | Check configuration, use `@Autowired`, assert denied and check proxy |
| Test with only allowed cases always passes | Missing denial branch check | Add `@WithMockUser` without required privilege + `assertThatThrownBy` |
| Annotation is present but self-invocation passes through | `this.method()` bypasses proxy | Move protected call to another injected bean |
| `hasRole('ADMIN')` does not match | Confusing role and authority, wrong `ROLE_` prefix | Use `roles = "ADMIN"` for `hasRole`; use `authorities` for `hasAuthority` |
| Security context error or test annotation has no effect | Missing `spring-security-test` or test lacks Spring Test integration | Add test dependency and use appropriate `@SpringBootTest`/`@ContextConfiguration` |
| Bean is not injected or not proxied | Service not in component scan, mocked, or annotation not enabled | Check package, `@Service`, `@EnableMethodSecurity`, `AopUtils.isAopProxy` |
| JDK-style proxy cannot be cast to implementation class | Bean implements an interface, proxy may only expose interface | Inject by appropriate interface type; consider class proxy mode when genuinely needed |
| `final`/`private` is not intercepted as expected | Limitations of subclass-based proxies and visibility | Place policy on proxyable public methods; avoid final/private at interception points |

Additional notes:

- Spring AOP usually uses a **JDK dynamic proxy** for beans with interfaces and a **class-based proxy** for beans without interfaces; details also depend on configuration. Do not write tests that hardcode proxy class names (such as names containing `$$SpringCGLIB$$`). `AopUtils.isAopProxy` is more stable for our learning goal.
- `@WithMockUser` sets the security context on the **test thread**. It does not automatically authenticate an HTTP request running on another thread (for example, `@SpringBootTest(webEnvironment = RANDOM_PORT)`); when testing over HTTP, you must supply credentials/tokens for that request.
- `@PreAuthorize` checks before the method body runs. If using `@PostAuthorize`, the logic may execute first before returning the result is denied; tests must be designed according to the corresponding interception point.
- If the project intentionally configures AspectJ weaving instead of Spring AOP proxies, how advice is applied and how proxies are checked may differ; this lesson focuses on standard proxy configuration.

## 6. Testing workflow for real code

1. Identify the exact bean/method carrying the annotation to test, and the expected privilege expression.
2. Start a Spring Test context with `@EnableMethodSecurity`; inject the bean from the context.
3. If using proxy mode, verify that the injected object is proxied or check an equivalent characteristic; **do not treat this step as a replacement for behavioral assertions**.
4. Create at least one **allowed** test and one **denied** test with explicit principal/authorities, such as `@WithMockUser`.
5. Run a control check by disabling the annotation or method security configuration (only in the test environment) to make sure the test genuinely catches the issue.

A valuable test must fail when you accidentally drop the authorization rule. That is the practical criterion for knowing that the annotation is **active on the Spring bean call path**, rather than merely existing in the source code.

## 7. Self-check exercises

1. Change the expression of `readReport` to `hasAnyAuthority('report:read', 'report:audit')`. Add a test with `@WithMockUser(authorities = "report:audit")` and a test lacking both authorities; explain the results.
2. Create a Spring-managed `ReportFacade`, inject `ReportService`, and call `readReport()` from the facade. Write an unauthorized test calling through the facade and verify it is still denied. Compare with the `this.readReport()` example to see the proxy boundary.

## Reference documentation

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): enabling `@EnableMethodSecurity`, `@PreAuthorize` expressions, and interceptor flow.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`, and security context in tests.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxies and the self-invocation bypass phenomenon.
