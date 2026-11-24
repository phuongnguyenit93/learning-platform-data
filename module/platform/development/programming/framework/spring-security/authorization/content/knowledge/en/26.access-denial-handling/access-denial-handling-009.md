# MethodAuthorizationDeniedHandler and @HandleAuthorizationDenied by Spring Security Version

`MethodAuthorizationDeniedHandler` and `@HandleAuthorizationDenied` are Spring Security's mechanism for **handling denied results at the method level**. Instead of always throwing an error when `@PreAuthorize`/`@PostAuthorize` denies access, the application can specify a handler to return a fallback value (`null`, a masked string, a filtered DTO, etc.) or continue throwing an exception. This is especially useful when returning data with sensitive fields without discarding the entire object.

**Key point about versions:** Both the `MethodAuthorizationDeniedHandler` interface and the `@HandleAuthorizationDenied` annotation carry `@since 6.3` in Spring Security's Javadoc. These two APIs cannot be used on Spring Security 6.2 or earlier. Some built-in implementations appeared later; you must check the Javadoc against the **library version actually on your classpath**.

## 1. Version Matrix: Which APIs Are Available?

| Spring Security Version | `MethodAuthorizationDeniedHandler` | `@HandleAuthorizationDenied` | Appropriate Implementation Approach |
| --- | --- | --- | --- |
| 5.x, 6.0–6.2 | **Not available** | **Not available** | Keep default denial; if fallback values are needed, design DTO/redaction at the application layer or explicit AOP with tests |
| 6.3.x | **Available** (`since 6.3`) | **Available** (`since 6.3`) | Create the application's own handler bean; use `handlerClass` |
| 6.4.x | **Available** | **Available** | Same model for handling denied invocation/denied result |
| 6.5.x | **Available** | **Available** | Can use both custom handlers and `NullReturningMethodAuthorizationDeniedHandler` (Javadoc: `since 6.5.0`) |
| 7.0.x, 7.1.x | **Available** | **Available** | Continues the handler mechanism; check Javadoc and configuration on the 7.x branch |

**Distinguishing Spring Boot from Spring Security:** Spring Boot manages the Spring Security version via dependency management/BOM. Do not determine API availability solely from the `spring-boot-starter-security` line or from the Boot version name alone. In a Maven project, check the actual version:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

On Windows, you can run `mvnw.cmd dependency:tree -Dincludes=org.springframework.security`. With Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
~~~

If `@HandleAuthorizationDenied` or `MethodAuthorizationDeniedHandler` reports `cannot find symbol` / `ClassNotFoundException` in a Spring Security 6.2 or older project, the cause is that **the API does not exist yet**, not merely a missing import. When upgrading, verify the version of *all* `spring-security-*` modules and use a consistent BOM.

## 2. How It Works

Method security must be enabled with `@EnableMethodSecurity`. Spring Boot Starter Security **does not automatically enable method security** just because the dependency is present. Checks are enforced via Spring AOP on Spring-managed beans.

~~~text
Call through the service's Spring proxy
  |
  +-- @PreAuthorize: checked before calling the method
  |       |
  |       +-- allowed -> run method -> return actual result
  |       |
  |       '-- denied -> MethodAuthorizationDeniedHandler
  |                         handleDeniedInvocation(...)
  |                         -> fallback / exception
  |                         (method has not run)
  |
  '-- @PostAuthorize: method runs first
          |
          +-- allowed -> return original result
          |
          '-- denied -> MethodAuthorizationDeniedHandler
                            handleDeniedInvocationResult(...)
                            -> masked result / fallback / exception
                            (method has already run)
~~~

`@HandleAuthorizationDenied(handlerClass = MyDeniedHandler.class)` specifies the **handler class**, not a bean name or a callback function; that handler must be registered as a Spring bean (for instance via `@Component` or `@Bean`). The annotation can be declared on a method or type, and can be used as a meta-annotation.

The handler may be invoked in the scenarios documented by Spring Security: denial by `@PreAuthorize`, `@PostAuthorize`, or an `AuthorizationDeniedException` thrown during a method invocation. **Do not assume the behavior generalizes to every kind of interceptor, exception, or HTTP handler**.

Distinguish the two branches:

- `@PreAuthorize` denies **before** invocation: the method has not run, the handler receives `MethodInvocation`, and there is no real method return value to mask. The handler should return a fallback of a compatible type.
- `@PostAuthorize` denies **after** invocation: the method has already run, and the handler receives `MethodInvocationResult`, allowing `getResult()` to mask/filter the output. Do not use this to prevent DB writes, sending emails, or other side effects, because the operation may have already occurred.
- If no replacement handler is provided (or a handler that throws an exception is chosen), the default denial is preserved. In an HTTP Servlet flow, Spring Security/the application may translate the error into 403 or an authentication challenge depending on context; **the annotation itself does not determine the HTTP status**.

## 3. Two Methods of the Interface

In package `org.springframework.security.authorization.method`:

~~~java
public interface MethodAuthorizationDeniedHandler {
    Object handleDeniedInvocation(
        MethodInvocation methodInvocation,
        AuthorizationResult authorizationResult
    );

    default Object handleDeniedInvocationResult(
        MethodInvocationResult methodInvocationResult,
        AuthorizationResult authorizationResult
    ) {
        return handleDeniedInvocation(
            methodInvocationResult.getMethodInvocation(),
            authorizationResult
        );
    }
}
~~~

This is a **simplified form to explain the contract**; nullability/annotation signatures may be expressed differently across Javadoc versions. The key point is that `handleDeniedInvocation(...)` is the method to implement, while `handleDeniedInvocationResult(...)` has a default implementation delegating to the first method. To mask based on the **actual value** after `@PostAuthorize`, you must override the second method.

| Parameter | What It Is Used For |
| --- | --- |
| `MethodInvocation` | Information about the invoked method, call arguments, and method metadata; useful for determining an appropriate fallback |
| `AuthorizationResult` | Information about the authorization decision result; do not assume a concrete type when the framework only promises the interface |
| `MethodInvocationResult` | Wraps `MethodInvocation` and the value returned by the method via `getResult()` |
| Return value `Object` | Must be compatible with the actual return type that the Spring proxy passes to the caller; may be `null` if valid, or throw an exception |

**Note on fallbacks:** A handler can return `null`, return a mock value of an appropriate type, or throw `AuthorizationDeniedException`. Using `null` for methods returning primitives like `int`/`boolean` easily causes unboxing errors; types like `Optional<T>`, collections, and DTOs require explicitly designed fallbacks. The handler only changes **the result of the protected invocation**, and does not grant extra authorities to the user.

## 4. Complete Example: Pre-Invocation Fallback and Post-Invocation Email Masking

The example is based on **Java 17+, a Spring Boot project with Spring Security 6.3+** (such as Spring Security 6.5.x). The following files use package `com.example.demo`. The Spring Boot/Maven project must include `spring-boot-starter-security`; to run tests, add `spring-boot-starter-test` and `spring-security-test` in `test` scope. Dependencies should get their versions from the Spring Boot BOM rather than manually mixing incompatible versions.

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

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
~~~

`@EnableMethodSecurity` enables interceptors for `@PreAuthorize` and `@PostAuthorize`. You do not need to manually register interceptors just to use these two annotations in standard configurations.

**`src/main/java/com/example/demo/RedactingDeniedHandler.java`**

~~~java
package com.example.demo;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.method.MethodAuthorizationDeniedHandler;
import org.springframework.security.authorization.method.MethodInvocationResult;
import org.springframework.stereotype.Component;

@Component
public class RedactingDeniedHandler
        implements MethodAuthorizationDeniedHandler {

    // @PreAuthorize denies before the method runs:
    // there is no original result to read.
    @Override
    public Object handleDeniedInvocation(
            MethodInvocation invocation,
            AuthorizationResult authorizationResult) {
        return "[HIDDEN]";
    }

    // @PostAuthorize denies after the method runs:
    // mask the local-part, keeping only the domain in the demo.
    @Override
    public Object handleDeniedInvocationResult(
            MethodInvocationResult invocationResult,
            AuthorizationResult authorizationResult) {
        Object result = invocationResult.getResult();
        if (!(result instanceof String email)) {
            return "[HIDDEN]";
        }
        int at = email.lastIndexOf('@');
        return at > 0 ? "***" + email.substring(at) : "[HIDDEN]";
    }
}
~~~

Because the handler is a Spring bean, necessary dependencies can be injected to determine the data-masking policy. However, **avoid logging or caching the original content** just because the handler sees the post-invocation value. Keeping the domain in the example illustrates `getResult()`; in a real system, if the domain is also sensitive, return a completely fixed value, `null`, or a DTO free of sensitive information.

**`src/main/java/com/example/demo/ContactService.java`**

~~~java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authorization.method.HandleAuthorizationDenied;
import org.springframework.stereotype.Service;

@Service
public class ContactService {

    private final AtomicInteger noteInvocations = new AtomicInteger();

    @PreAuthorize("hasAuthority('note:read')")
    @HandleAuthorizationDenied(handlerClass = RedactingDeniedHandler.class)
    public String internalNote() {
        noteInvocations.incrementAndGet();
        return "INTERNAL-42";
    }

    @PostAuthorize("hasAuthority('email:read')")
    @HandleAuthorizationDenied(handlerClass = RedactingDeniedHandler.class)
    public String contactEmail() {
        return "alice@example.org";
    }

    @PreAuthorize("hasAuthority('note:read')")
    public String defaultDenied() {
        return "NEVER-EXPOSED";
    }

    public int noteInvocationCount() {
        return noteInvocations.get();
    }
}
~~~

Points to observe:
- Without `note:read`: `internalNote()` returns `[HIDDEN]` and **the counter does not increment**, proving the method did not execute.
- With `note:read`: the method runs and returns `INTERNAL-42`.
- Without `email:read`: `contactEmail()` ran, but the caller only receives `***@example.org`.
- With `email:read`: the caller receives `alice@example.org`.
- `defaultDenied()` does not have `@HandleAuthorizationDenied`, so it still throws an exception when lacking permission.

Placing `@HandleAuthorizationDenied` alongside `@PreAuthorize`/`@PostAuthorize` is an **intentional per-method decision**: enabling method security does not turn every denied request into a redacted result.

## 5. Testing Behavior with JUnit and Spring Security Test

The following file requires `spring-security-test` and `spring-boot-starter-test` dependencies. Use `@WithMockUser` to place an `Authentication` with specific authorities in `SecurityContext`; call the bean through the Spring proxy so interceptors run.

**`src/test/java/com/example/demo/ContactServiceTests.java`**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ContactServiceTests {

    @Autowired
    ContactService service;

    @Test
    @WithMockUser
    void preAuthorizeDeniedReturnsFallbackWithoutCallingMethod() {
        int before = service.noteInvocationCount();
        assertEquals("[HIDDEN]", service.internalNote());
        assertEquals(before, service.noteInvocationCount());
    }

    @Test
    @WithMockUser(authorities = "note:read")
    void preAuthorizeAllowedReturnsRealValue() {
        int before = service.noteInvocationCount();
        assertEquals("INTERNAL-42", service.internalNote());
        assertEquals(before + 1, service.noteInvocationCount());
    }

    @Test
    @WithMockUser
    void postAuthorizeDeniedMasksActualResult() {
        assertEquals("***@example.org", service.contactEmail());
    }

    @Test
    @WithMockUser(authorities = "email:read")
    void postAuthorizeAllowedReturnsOriginalValue() {
        assertEquals("alice@example.org", service.contactEmail());
    }

    @Test
    @WithMockUser
    void withoutHandlerDenialStillThrows() {
        assertThrows(AccessDeniedException.class, service::defaultDenied);
    }
}
~~~

Run tests in the Maven project configured with Spring Boot and the dependencies listed above:

~~~bash
./mvnw test
~~~

On Windows use `mvnw.cmd test`. **The expected outcome** is that all five test cases pass; this is the expected result per the code, not an observed test run log. HTTP testing with `MockMvc` is an additional step if you want to verify mapping to 401/403/200; direct service tests verify the handler mechanism itself, independent of HTTP configuration.

## 6. When Should You Use a Fallback vs. Deny Outright?

| Problem | Recommendation | Reason |
| --- | --- | --- |
| Property not sensitive when partially hidden (e.g., returning a policy-masked email) | `@PostAuthorize` + output-filtering handler | Actual result is available to construct a safe variant |
| Expensive computation/read, yet unauthorized callers may receive a fixed label | `@PreAuthorize` + fallback-returning handler | Avoids running the method before deciding |
| DB writes, money transfers, data deletion, sending emails | **Deny before invocation**; usually keep the exception | `@PostAuthorize` does not reverse side effects |
| Resource must not be disclosed even by domain or metadata | Return `null`/full mask or exception | A partially masked result can still leak data |
| API requires the client to distinguish missing permissions to request access | Keep exception/403 per API policy | Fallbacks can turn responses into 200 and cause confusion |
| Spring Security 6.2 or older | Design data handling in service/DTO layer or upgrade BOM | These annotation/interface APIs do not exist yet |

**Do not treat fallbacks as "bypassing security".** Allowing a caller to receive a substitute result is also a security policy requiring approval, permission tests, tenant tests, and data-leak tests. In particular, if a controller serializes a fallback into HTTP 200, clients might treat it as real data: document the contract clearly (`null`, masked string, `redacted` flag, etc.) to avoid breaking client business logic.

## 7. Handling Version Differences When Returning Null

If the requirement is simply to return `null` instead of an exception when denied, you can write a small custom handler applicable from Spring Security **6.3+**:

~~~java
package com.example.demo;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.method.MethodAuthorizationDeniedHandler;
import org.springframework.stereotype.Component;

@Component
public class NullDeniedHandler implements MethodAuthorizationDeniedHandler {
    @Override
    public Object handleDeniedInvocation(
            MethodInvocation invocation,
            AuthorizationResult result) {
        return null;
    }
}
~~~

Apply to a method with a return type accepting `null`:

~~~java
@PreAuthorize("hasAuthority('profile:read')")
@HandleAuthorizationDenied(handlerClass = NullDeniedHandler.class)
public String readProfile() {
    return "visible";
}
~~~

The method snippet above **only illustrates how to attach the annotation in a Spring bean**; it must be placed in a Spring-managed class with `@EnableMethodSecurity` enabled as in the full example. Starting in Spring Security **6.5.0**, Javadoc also includes the built-in `NullReturningMethodAuthorizationDeniedHandler`. When supporting multiple 6.3/6.4/6.5 branches, use a custom handler as above to avoid importing a class not yet present in 6.3/6.4.

Do not use a `null` fallback if the method returns a primitive, or if the caller immediately dereferences the value. For DTOs or JSON, the serialization policy (keeping the field as `null` or omitting the field) must also be defined and tested separately.

## 8. Common Errors and How to Diagnose Them

1. **Import does not exist even though current documentation shows it:** open the dependency tree and check whether Spring Security is at least **6.3**. Do not copy 7.x examples into a 6.2 project.
2. **Annotation is present yet still throws an exception:** verify the handler has `@Component`/`@Bean`, method security is enabled, the call goes through a Spring proxy, the annotation is on the right method/type, and the interceptor is able to handle that denial.
3. **Called from another method in the same class:** self-invocation via `this.method()` normally **bypasses the Spring AOP proxy**, causing `@PreAuthorize` and the handler not to run. Split into two Spring beans or use an appropriate design.
4. **Using `handleDeniedInvocation` to mask `@PostAuthorize` results:** the default method does not use `getResult()`. Override `handleDeniedInvocationResult` if you want to depend on the actual result.
5. **Returning a value of the wrong type:** e.g., returning the string `"denied"` for a method declared as `List<Order>` can cause type errors. Use an empty collection or an appropriate fallback DTO, provided the policy allows it.
6. **Assuming `@PostAuthorize` prevents data writes:** the method already executed before the check; critical authorization for mutations must happen **before side effects**.
7. **Relying on the handler to mask all errors:** the handler targets method authorization denials. `NullPointerException`, database errors, or `AccessDeniedException` outside framework-supported points are **not automatically** converted to fallbacks.
8. **Forgetting to align HTTP status:** a fallback replacing an exception can lead to 200 in the controller instead of 403. If the API contract requires reporting missing permissions, pick a throwing handler or design responses intentionally.
9. **Testing a raw `new ContactService()` instance:** bypasses the proxy so annotations are not applied. Test the `@Autowired` Spring bean with `@WithMockUser`, verifying both denied and allowed cases.
10. **Email masking not strict enough:** domain, string length, message differences, or response timing can leak information. Use a fixed fallback if policy forbids disclosing existence.

## 9. Checklist for Choosing APIs in Your Project

- [ ] Accurately identified the version of `spring-security-core` and related modules in the dependency tree.
- [ ] Projects on 6.2 or lower: do not use these two new APIs; evaluate upgrading or older alternatives.
- [ ] Projects on 6.3+: enable `@EnableMethodSecurity`, create a Spring bean implementing `MethodAuthorizationDeniedHandler`.
- [ ] Specify `@HandleAuthorizationDenied(handlerClass = ...)` on the right method/type needing a fallback.
- [ ] If actual post-invocation data is needed: override `handleDeniedInvocationResult`.
- [ ] Choose a fallback compatible with the return type, especially primitives/`Optional`/reactive types.
- [ ] Do not rely on `@PostAuthorize` as the layer preventing side effects of write operations.
- [ ] Test through the proxy: allowed, denied, default handler throwing exceptions, and safely masked data.
- [ ] Check the API/HTTP contract when fallbacks alter exception propagation paths.
- [ ] Consult the Javadoc for the **exact version branch** before adopting new built-in handlers.

## Official Documentation for Version Cross-Reference

1. [Spring Security 6.5 — Method Security / Providing Fallback Values When Authorization is Denied](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
2. [`MethodAuthorizationDeniedHandler` — Spring Security 6.5 API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/MethodAuthorizationDeniedHandler.html) (Javadoc: `since 6.3`).
3. [`@HandleAuthorizationDenied` — Spring Security 7.1 API](https://docs.spring.io/spring-security/reference/7.1/api/java/org/springframework/security/authorization/method/HandleAuthorizationDenied.html) (Javadoc: `since 6.3`, `handlerClass` parameter).
4. [`NullReturningMethodAuthorizationDeniedHandler` — Spring Security 7.1 API](https://docs.spring.io/spring-security/reference/7.1/api/java/org/springframework/security/authorization/method/NullReturningMethodAuthorizationDeniedHandler.html) (Javadoc: `since 6.5.0`).
5. [Spring Security 7.1 — Method Security](https://docs.spring.io/spring-security/reference/7.1/servlet/authorization/method-security.html).

**Key takeaway:** API version support is determined by the actual Spring Security version in the build; `@PreAuthorize` and `@PostAuthorize` decide **when** to deny, while `MethodAuthorizationDeniedHandler` and `@HandleAuthorizationDenied` decide **what to return or throw when denied**.
