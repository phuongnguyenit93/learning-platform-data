# AuthorizationManagerBeforeMethodInterceptor and AuthorizationManagerAfterMethodInterceptor

## 1. Lesson Objectives

In Spring Security Method Security, the two interceptors **`AuthorizationManagerBeforeMethodInterceptor`** and **`AuthorizationManagerAfterMethodInterceptor`** connect authorization decision logic (`AuthorizationManager`) to Spring AOP method invocations.

- **Before**: decides whether the caller is allowed to **execute the method**, before the method body begins.
- **After**: decides whether the caller is allowed to **receive the return value**, after the method body has run.

This is the underlying mechanism behind `@PreAuthorize` and `@PostAuthorize`, and it can also be used directly with a **custom AuthorizationManager** and a **custom Pointcut**.

After reading, you will be able to:

1. Explain the AOP flow, input object, and outcome of each interceptor.
2. Distinguish `MethodInvocation` from `MethodInvocationResult`.
3. Understand factory methods `preAuthorize(...)` / `postAuthorize(...)`, as well as constructors taking a `Pointcut`.
4. Register custom `Advisor`s while avoiding unintended overlap with default interceptors.
5. Write a Java `AuthorizationManager` instead of SpEL, checking properly before/after and handling `null` data.
6. Test Spring beans/proxies to prove **before-deny skips the body**, while **after-deny happens after the body**.

**Scope:** Spring Security 6.5.x, Spring Framework 6.2.x, Java 17+, standard Spring AOP proxies. Version 7.x makes minor changes to the `AuthorizationManager` interface; cross-check the exact version's Javadoc when upgrading. Examples primarily use synchronous method security on Spring-managed beans and do not apply directly to reactive method security.

## 2. Two Control Points on the Same Call

Suppose a service has a document-reading method protected on both input and output:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
@PostAuthorize("returnObject.owner == authentication.name")
public Document findDocument(String id) {
    return repository.findDocument(id);
}
```

This is an **illustrative snippet**, not a standalone Java program. With `@EnableMethodSecurity` and calls passing through a Spring proxy, the conceptual flow is:

```text
Caller
   |
   v
Spring AOP proxy
   |
   v
BeforeMethodInterceptor
   |-- Pointcut matches @PreAuthorize?
   |-- AuthorizationManager<MethodInvocation>
   |-- DENY --> AccessDeniedException (method body not invoked)
   |
   | ALLOW
   v
Service.findDocument(id)  --> resulting Document
   |
   v
AfterMethodInterceptor
   |-- Pointcut matches @PostAuthorize?
   |-- AuthorizationManager<MethodInvocationResult>
   |-- DENY --> AccessDeniedException (Document not returned to caller)
   |
   | ALLOW
   v
Caller receives Document
```

Both are typically Spring AOP `Advisor`s: an advisor consists of a **Pointcut** to select methods and an **Advice/MethodInterceptor** to execute the check.

**Crucial point:** the after interceptor runs after the method body and can inspect the return value; it **does not roll back** queries, data mutations, or side effects already performed by the method body. Policies that block write operations must be checked **before** side effects occur, never relying solely on after authorization.

## 3. Exact Comparison Table

| Criterion | `AuthorizationManagerBeforeMethodInterceptor` | `AuthorizationManagerAfterMethodInterceptor` |
| --- | --- | --- |
| Timing | Before invoking the method body | After the method returns, before returning to caller |
| Data inspected by manager | `MethodInvocation` | `MethodInvocationResult` |
| Key generic type | `AuthorizationManager<MethodInvocation>` | `AuthorizationManager<MethodInvocationResult>` |
| Readable data | Method, target, arguments | `MethodInvocation` **and** result via `getResult()` |
| Common factories | `preAuthorize()`, `preAuthorize(manager)` | `postAuthorize()`, `postAuthorize(manager)` |
| Related default annotation | `@PreAuthorize` | `@PostAuthorize` |
| On denial | Body does not run; typically throws `AccessDeniedException` | Body already ran; result is withheld; typically throws `AccessDeniedException` |
| Well suited for | Command execution rights, ID access rights, role, tenant before action | Checking owner/tenant/status on a **loaded result** |
| What it is not | `@PreFilter` automatically filtering a collection | `@PostFilter` automatically filtering collection elements |

`MethodInvocation` (AOP Alliance) exposes `getMethod()`, `getArguments()`, and `getThis()`. It does **not** yet have a return value at the before stage. Conversely, Spring Security's `MethodInvocationResult` contains `getMethodInvocation()` and `getResult()`; the result may be `null` and needs explicit handling in policy.

Specifically, **`@PostAuthorize` evaluates the entire return value**, without removing individual items from a list. Element-by-element collection filtering is a separate job for `@PostFilter` and `PostFilterAuthorizationMethodInterceptor`.

## 4. Default Interceptors Created by Spring Security

Enable method security in configuration:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {
}
```

Spring Security then provides advisor infrastructure for `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` with default settings. Conceptually, the before/after portion is equivalent to:

```java
// Illustrates equivalent advisors; DO NOT add duplicates when already using
// @EnableMethodSecurity with prePostEnabled = true.
Advisor pre = AuthorizationManagerBeforeMethodInterceptor.preAuthorize();
Advisor post = AuthorizationManagerAfterMethodInterceptor.postAuthorize();
```

In standard configuration, `preAuthorize()` uses `PreAuthorizeAuthorizationManager` to evaluate `@PreAuthorize` expressions via `MethodSecurityExpressionHandler`. Likewise, `postAuthorize()` uses `PostAuthorizeAuthorizationManager` to evaluate `@PostAuthorize` with `returnObject`.

Other annotations have specialized interceptors or dedicated factories:

| Annotation | Default handler |
| --- | --- |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor.preAuthorize(...)` |
| `@PostAuthorize` | `AuthorizationManagerAfterMethodInterceptor.postAuthorize(...)` |
| `@Secured` (requires `securedEnabled = true`) | `AuthorizationManagerBeforeMethodInterceptor.secured(...)` |
| JSR-250 like `@RolesAllowed` (requires `jsr250Enabled = true`) | `AuthorizationManagerBeforeMethodInterceptor.jsr250(...)` |
| `@PreFilter` / `@PostFilter` | `PreFilterAuthorizationMethodInterceptor` / `PostFilterAuthorizationMethodInterceptor` |

Do not write code assuming `AuthorizationManagerBeforeMethodInterceptor.preFilter()` and `AuthorizationManagerAfterMethodInterceptor.postFilter()` are the APIs to register filters across all versions: Spring Security has **separate filter interceptor classes**.

### 4.1. When Replacing the Manager of Default Annotations

If you want to replace authorization logic for `@PreAuthorize` and `@PostAuthorize` with Java code, the official documentation recommends **disabling default pre/post configuration**, then declaring advisors you control:

```java
@Configuration
@EnableMethodSecurity(prePostEnabled = false)
class CustomMethodSecurityConfig {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor customBefore(
            AuthorizationManager<MethodInvocation> beforeManager) {
        return AuthorizationManagerBeforeMethodInterceptor
            .preAuthorize(beforeManager);
    }

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor customAfter(
            AuthorizationManager<MethodInvocationResult> afterManager) {
        return AuthorizationManagerAfterMethodInterceptor
            .postAuthorize(afterManager);
    }
}
```

**This is an illustrative configuration example** requiring the two beans `beforeManager` and `afterManager` and corresponding imports. The `preAuthorize(manager)` / `postAuthorize(manager)` factories use **the respective annotation's pointcut**. When substituting a custom manager for the default SpEL manager, **do not assume annotation expression strings are still evaluated by Spring automatically**: your manager decides the actual policy. Preserve or migrate old conditions deliberately.

If your goal is simply adding a policy for **one specific group of methods**, you can keep `@EnableMethodSecurity` as normal, build a narrow **custom pointcut**, and register a separate advisor. When a method matches multiple advisors, decisions apply sequentially; understand which rule denies and the advice order to avoid surprises.

## 5. Custom Pointcut: Attaching Both Interceptors to a Business Annotation

An easily testable pattern is creating a `@DocumentRead` annotation for methods returning a `Document`, and registering:

- Before manager: verifies the caller has authority `DOC_READ`.
- After manager: once the method has run, returns `Document` only if `owner` matches the principal.
- Both advisors share `AnnotationMatchingPointcut.forMethodAnnotation(DocumentRead.class)`.

This way, Java policy code is the source of truth for decisions, independent of SpEL strings or reflection-discovered parameter names.

### 5.1. Self-Contained Gradle Build for the Example

Create a small test project:

```text
interceptors-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/InterceptorMethodSecurityTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'interceptors-demo'
```

`build.gradle` (Java 17, Spring Boot 3.5.0 BOM managing Spring Security 6.5.x):

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

The entire example lives in `src/test/java`, so test dependencies suffice. In a real application, put the Spring Security starter in `implementation`, add test dependencies per project lifecycle, and use your project's managed BOM version. Never manually mix incompatible Spring Security/Spring Framework versions.

### 5.2. Complete Java Class with Six Tests

Create `src/test/java/demo/InterceptorMethodSecurityTest.java`:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.concurrent.atomic.AtomicInteger;

import org.aopalliance.intercept.MethodInvocation;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.Advisor;
import org.springframework.aop.support.annotation.AnnotationMatchingPointcut;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerAfterMethodInterceptor;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.authorization.method.MethodInvocationResult;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(InterceptorMethodSecurityTest.Config.class)
@WithMockUser(username = "alice", authorities = "DOC_READ")
public class InterceptorMethodSecurityTest {

    @Autowired
    DocumentService service;

    @Autowired
    Probe probe;

    @BeforeEach
    void clearProbe() {
        probe.reset();
    }

    @Target(ElementType.METHOD)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface DocumentRead {
    }

    public record Document(String id, String owner) {
    }

    public static class Probe {
        private final AtomicInteger calls = new AtomicInteger();

        void recordCall() {
            calls.incrementAndGet();
        }

        int calls() {
            return calls.get();
        }

        void reset() {
            calls.set(0);
        }
    }

    public static class DocumentService {
        private final Probe probe;

        public DocumentService(Probe probe) {
            this.probe = probe;
        }

        @DocumentRead
        public Document read(String id) {
            probe.recordCall();
            return switch (id) {
                case "A" -> new Document("A", "alice");
                case "B" -> new Document("B", "bob");
                default -> null;
            };
        }

        public String ping() {
            return "pong";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity(prePostEnabled = false)
    public static class Config {

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        DocumentService service(Probe probe) {
            return new DocumentService(probe);
        }

        @Bean
        @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
        static Advisor beforeDocumentRead() {
            AuthorizationManager<MethodInvocation> manager =
                (authenticationSupplier, invocation) -> {
                    Authentication authentication = authenticationSupplier.get();
                    boolean granted = authentication != null
                        && authentication.isAuthenticated()
                        && authentication.getAuthorities().stream()
                            .anyMatch(a -> "DOC_READ".equals(a.getAuthority()));
                    return new AuthorizationDecision(granted);
                };

            return new AuthorizationManagerBeforeMethodInterceptor(
                AnnotationMatchingPointcut.forMethodAnnotation(
                    DocumentRead.class),
                manager
            );
        }

        @Bean
        @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
        static Advisor afterDocumentRead() {
            AuthorizationManager<MethodInvocationResult> manager =
                (authenticationSupplier, invocationResult) -> {
                    Authentication authentication = authenticationSupplier.get();
                    Object value = invocationResult.getResult();
                    boolean granted = authentication != null
                        && authentication.isAuthenticated()
                        && value instanceof Document document
                        && document.owner().equals(authentication.getName());
                    return new AuthorizationDecision(granted);
                };

            return new AuthorizationManagerAfterMethodInterceptor(
                AnnotationMatchingPointcut.forMethodAnnotation(
                    DocumentRead.class),
                manager
            );
        }
    }

    @Test
    void aliceCanReadHerDocument() {
        assertThat(service.read("A"))
            .isEqualTo(new Document("A", "alice"));
        assertThat(probe.calls()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_READ")
    void bobCanReadHisDocument() {
        assertThat(service.read("B"))
            .isEqualTo(new Document("B", "bob"));
        assertThat(probe.calls()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER")
    void missingAuthorityIsDeniedBeforeBody() {
        assertThatThrownBy(() -> service.read("A"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.calls()).isZero();
    }

    @Test
    void wrongOwnerIsDeniedAfterBody() {
        assertThatThrownBy(() -> service.read("B"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.calls()).isEqualTo(1);
    }

    @Test
    void nullResultIsDeniedAfterBody() {
        assertThatThrownBy(() -> service.read("missing"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.calls()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "guest", authorities = "OTHER")
    void methodOutsidePointcutIsNotCheckedByTheseAdvisors() {
        assertThat(service.ping()).isEqualTo("pong");
        assertThat(probe.calls()).isZero();
    }
}
```

**Explanation of design points in the tests:**

1. `@SpringJUnitConfig` creates the Spring `ApplicationContext`; `@EnableMethodSecurity(prePostEnabled = false)` still enables AOP infrastructure while disabling default `@PreAuthorize`/`@PostAuthorize` advisors. Two custom advisors are registered as `@Bean`s with role `ROLE_INFRASTRUCTURE`.
2. `@DocumentRead` merely marks methods where both rules apply. `AnnotationMatchingPointcut` checks the annotation on the **method**; `ping()` falls outside this pointcut.
3. The before manager uses `AuthorizationManager<MethodInvocation>`; in the example, it only needs authorities from `Authentication`. For complex policies, it can read `invocation.getArguments()`, `getMethod()`, and `getThis()` to enforce rules by ID, tenant, or target.
4. The after manager uses `AuthorizationManager<MethodInvocationResult>`; `getResult()` is the `Document` returned by the method. The `instanceof Document` guard protects against `null` or unexpected types, failing closed.
5. `Probe` is a separate bean counting **how many times the method body executes**. Do not read a CGLIB proxy field as though it always reflects target state. Before-deny gives 0 calls; after-deny gives 1 call.
6. `@WithMockUser` on the test class creates Alice with `DOC_READ`. Bob, guest, and missing-authority tests override the principal/authorities individually. `DOC_READ` is an **exact authority**, without an implicit `ROLE_` prefix.
7. In Spring Security 6.5, `AuthorizationManager` remains a functional interface with abstract `check(...)` (though deprecated), while default `authorize(...)` delegates to it. Therefore, lambdas returning `AuthorizationDecision` fit 6.5 cleanly. When moving to Spring Security 7.x or another API, re-verify the abstract method and generic signatures for that version.

### 5.3. Run Command and Verifiable Expectations

From the project directory containing `build.gradle`:

```bash
gradle test --tests demo.InterceptorMethodSecurityTest
```

If using a Gradle Wrapper, run `./gradlew test --tests demo.InterceptorMethodSecurityTest` (Linux/macOS) or `gradlew.bat test --tests demo.InterceptorMethodSecurityTest` (Windows).

When dependencies, method security, and Spring proxies are configured properly, **six tests are expected to pass** and Gradle finishes with `BUILD SUCCESSFUL`. This describes **expected behavior**, not copied stdout from an actual run.

| Test | Before | Body | After | Caller outcome |
| --- | --- | --- | --- | --- |
| Alice reads A/Alice | Allow | Runs once | Allow | Receives A |
| Bob reads B/Bob | Allow | Runs once | Allow | Receives B |
| Alice lacks `DOC_READ` | Deny | **Does not run** | Not reached | `AccessDeniedException` |
| Alice reads B/Bob | Allow | Runs once | **Deny** | `AccessDeniedException` |
| Alice reads non-existent ID | Allow | Runs once, returns `null` | **Deny** per example policy | `AccessDeniedException` |
| Guest calls `ping()` | No match | Runs | No match | `"pong"` |

The final test only proves **the two custom advisors do not apply** to an unannotated method; it does not mean everyone should be allowed to call it in a real application. HTTP security, service boundaries, and default-deny principles must still be designed separately.

## 6. Inspecting Input and Output in Java Managers

### Before: `MethodInvocation`

A custom manager commonly uses method parameters to check resource access before processing:

```java
AuthorizationManager<MethodInvocation> byDocumentId =
    (authentication, invocation) -> {
        Object[] arguments = invocation.getArguments();
        String methodName = invocation.getMethod().getName();
        // Validate argument type contract for the exact method/pointcut.
        // Custom policy decides using trusted server-side data.
        return new AuthorizationDecision(
            "read".equals(methodName) && arguments.length == 1
        );
    };
```

**This is only an illustrative snippet**, not a complete authorization rule: it checks neither user nor owner and **must never be used as a production policy**. In a real application, check `authentication.get()` and permissions for the ID/tenant against verified data; never trust a client-supplied `owner`.

### After: `MethodInvocationResult`

Once the method finishes, the manager can inspect `result.getResult()` and trace back to the invocation if needed:

```java
AuthorizationManager<MethodInvocationResult> ownerCheck =
    (authentication, invocationResult) -> {
        Object returned = invocationResult.getResult();
        boolean allowed = returned instanceof Document document
            && document.owner().equals(authentication.get().getName());
        return new AuthorizationDecision(allowed);
    };
```

In the example, `Document` is the lesson's record; this assumes authentication is non-null. If unauthenticated/anonymous callers or `null` results must be handled, handle them explicitly. `getMethodInvocation()` allows inspecting the method/args when needed.

Good design: **before checks permission to request the operation** (especially with side effects), **after checks details of the returned data**. Never push an entire policy into after if confidential data could be logged or side effects triggered before the after check runs.

## 7. Pointcuts and `Advisor` Lifecycle

Both interceptors have constructors accepting:

```java
new AuthorizationManagerBeforeMethodInterceptor(
    pointcut, beforeManager);

new AuthorizationManagerAfterMethodInterceptor(
    pointcut, afterManager);
```

- `pointcut`: specifies classes/methods to guard, such as `AnnotationMatchingPointcut` for a custom annotation or `AspectJExpressionPointcut` for a group of services.
- `beforeManager`: must be `AuthorizationManager<MethodInvocation>`.
- `afterManager`: must be `AuthorizationManager<MethodInvocationResult>`.

This is the **Spring AOP proxy** API, not a claim that AspectJ bytecode weaving is enabled. `AspectJExpressionPointcut` uses AspectJ expression syntax while still applying via proxies.

For built-in annotations, you can use `preAuthorize(...)` and `postAuthorize(...)` factories so Spring picks pointcuts from `@PreAuthorize`/`@PostAuthorize`. For custom annotations, the constructor + pointcut makes the target explicit and avoids assuming SpEL still runs after replacing the manager.

**Ordering:** `AuthorizationInterceptorsOrder` defines order constants for Method Security advisors. If you have multiple advisors, transactions, or logging, configure `setOrder(int)` only when genuinely needed and write integration tests verifying call order; never treat guessed order numbers as a fixed contract across all framework versions.

**Duplicate advisors:** `@EnableMethodSecurity` registers default before/after advisors for pre/post annotations. If you add two more advisors sharing **the same pointcut** without disabling or accounting for defaults, a call can be checked multiple times. If two rules are independent, treat them as cumulative conditions and test cases where one allows while the other denies; if **replacing**, use `prePostEnabled = false` with your replacement advisors.

## 8. Authorization Decisions: Allow, Deny, Abstain, and Exceptions

In Spring Security 6.5, managers return `AuthorizationDecision` or a suitable `AuthorizationResult`:

```java
return new AuthorizationDecision(true);  // Allow
return new AuthorizationDecision(false); // Deny
```

Returning `null` in the manager contract means **abstain/no decision** on APIs that support it, **not deny**. For sensitive boundaries you own, design **explicit allow or explicit deny** according to policy; never rely on `null` to fail closed.

When a manager returns deny, interceptors normally throw `AccessDeniedException` (or subtype `AuthorizationDeniedException` on supporting versions) and may publish authorization events if an event publisher is configured. In the HTTP stack, Spring Security typically translates the exception into 403 for authenticated callers lacking permission, depending on `ExceptionTranslationFilter`, entry point, and exception handling. When calling a service from batch/schedulers or non-HTTP tests, the caller must handle the exception per application contract.

Never default to `true` when authentication is missing, the result type is wrong, or policy queries fail. Technical errors should be categorized, safely logged, and explicitly tested; never accidentally turn failures into granted access.

## 9. Characteristic Pitfalls

### 9.1. Tests Calling `new Service()` Directly

Spring AOP interceptors do not run on an instance instantiated directly in a test without a proxy. Use `@SpringJUnitConfig`/Spring Boot Test, inject the bean, and write tests where one user is denied **before body** and another is denied **after body**. Testing only allow cases can hide missing proxies.

### 9.2. Self-Invocation

`this.read(id)` called inside the same target can bypass interceptors on `read` in proxy mode. Move the protected boundary into a separate bean or use an intentional mechanism, and test real call paths. Never assume `@EnableMethodSecurity` or switching from JDK proxies to CGLIB automatically protects self-calls.

### 9.3. `@PostAuthorize` Does Not Filter Lists

An after manager normally makes **one decision for the whole return value**. If a method returns `List<Document>`, `result.getResult()` being a `List` does not create `filterObject` or remove items element-by-element. Choose `@PostFilter` or data-layer queries for element filtering; for multi-tenant or paginated data, prefer enforcing permission predicates directly in the query.

### 9.4. After Denial Is Too Late for Write Operations

A method may have already updated a repository, emitted an event, or sent an email before the after manager rejects returning the result. If the policy forbids the operation, place a before rule or a policy check at the right transaction boundary. Never assume a late exception automatically undoes every side effect. When combining with `@Transactional`, verify ordering and rollback with real database tests.

### 9.5. Null and Result Types

`MethodInvocationResult.getResult()` can be `null`. Check types with `instanceof` before casting or accessing fields. If a method specifies "return null when not found" and the product wants 404 instead of deny, the after policy must distinguish legitimate null from unauthorized data; the lesson's example intentionally **denies null** to demonstrate fail-closed policy.

### 9.6. Role Names, Tenants, and Untrusted Data

`hasRole("ADMIN")` usually checks `ROLE_ADMIN`, whereas checking a literal authority `DOC_READ` requires an exact match. For tenant-based permissions, verify ID/owner against trusted server-side records rather than relying solely on a client-supplied `owner` string. Complex rules belong in standalone policy services that can be unit-tested case by case.

### 9.7. Sync Differs from Reactive

The two classes in this lesson take synchronous `MethodInvocation`/`MethodInvocationResult`. Reactive method security has dedicated **reactive** interceptors and managers, such as `AuthorizationManagerBeforeReactiveMethodInterceptor` and `ReactiveAuthorizationManager`. Do not apply synchronous code directly to `Mono`/`Flux` without accounting for publisher emission timing, context, and permissions.

### 9.8. API Interfaces Across Versions

Spring Security 6.5 still has deprecated abstract `check(Supplier<Authentication>, T)` and default `authorize(...)`; the examples here use lambdas returning `AuthorizationDecision`, compatible with 6.5. Newer versions shift focus to `authorize(...)` as the abstract method using `AuthorizationResult`. Check your exact version's API before copying an `implements AuthorizationManager<...>` class with `@Override`.

## 10. Diagnostic Workflow When an Interceptor Does Not Run

1. **Verify configuration:** Is `@EnableMethodSecurity` present, is there an `Advisor` bean with `@Bean @Role(ROLE_INFRASTRUCTURE)`, and were needed default advisors not disabled?
2. **Check the pointcut:** Does the class/method carry the `@Retention(RUNTIME)` annotation, is visibility interceptable by the proxy, and is there no mismatch between interface and implementation? For expression pointcuts, verify the pattern actually matches.
3. **Check the call path:** Does the call go through a Spring-injected bean rather than `this.method()` or a `new` instance?
4. **Inspect the AuthorizationManager:** Does before receive `MethodInvocation` with the expected method/args? Does after see the actual `MethodInvocationResult.getResult()`? Does `authentication.get()` have the expected principal/authorities?
5. **Verify denials:** Test a user lacking authority confirming **the body does not run**; test a mismatched owner confirming **the body runs yet the caller does not receive the result**.
6. **Check overlapping policies:** Do default `@PreAuthorize`/`@PostAuthorize` advisors and custom advisors share the same pointcut? If so, how do their decisions combine?
7. **Check transactions/HTTP:** Where is the exception handled—service, controller, exception translator, or scheduler? Did side effects occur before after denial?
8. **Check upgrades:** Generic signatures, `AuthorizationDecision`/`AuthorizationResult`, `check`/`authorize`, role naming, and changes in your actual Spring Security version.

## 11. Reinforcement Exercises

**Exercise A — change the before policy:** Replace `DOC_READ` with `DOC_AUDIT` in the before manager, keep the test principal with only `DOC_READ`, and observe that the method body does not run. Update the test fixture authority and re-run.

**Exercise B — after with tenant:** Extend `Document` to `Document(String id, String owner, String tenant)`; have the after manager compare the tenant from a trusted identity against the record's tenant. Test that matching owner with a different tenant must deny.

**Exercise C — different pointcut:** Add a `readSummary()` method without `@DocumentRead`; prove the custom advisors do not apply. Then annotate the method and ensure the result type matches the policy (avoid assuming every result is a `Document`).

**Exercise D — testing side effects:** Replace `Probe` with a fake repository counting read/write calls. Test that before-deny never calls the repository, while after-deny already called read before being blocked. Explain why an after rule must not serve as the sole gate before writes.

**Exercise E — replacing default annotations:** Use `@EnableMethodSecurity(prePostEnabled = false)` with `preAuthorize(customManager)` and `postAuthorize(customManager)`, and add a test proving `@PreAuthorize`/`@PostAuthorize` expressions are not automatically evaluated if your new manager does not interpret them. Decide explicitly whether to keep SpEL or move all policies to Java.

## 12. Takeaways

- **Before interceptor** = checks permission **before the body**, taking `AuthorizationManager<MethodInvocation>`.
- **After interceptor** = checks **the result after the body**, taking `AuthorizationManager<MethodInvocationResult>` with `getResult()`.
- **Pointcuts select scope**, `AuthorizationManager` makes decisions; advisors must be properly registered with Spring AOP.
- `@EnableMethodSecurity` already enables default advisors; when **replacing** them, manage `prePostEnabled` to avoid duplicates or lost checks.
- **After authorization is not filtering** and does not roll back side effects.
- At minimum, test **allow**, **before-deny/body skipped**, **after-deny/body executed**, **null result**, **method outside pointcut**, and **different principals** through a Spring proxy.

## Official References

- Spring Security 6.5 — Method Security, custom AuthorizationManager, advisors/pointcuts, and pre/post flow: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 API — AuthorizationManagerBeforeMethodInterceptor: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizationManagerBeforeMethodInterceptor.html
- Spring Security 6.5 API — AuthorizationManagerAfterMethodInterceptor: https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authorization/method/AuthorizationManagerAfterMethodInterceptor.html
- Spring Security API — MethodInvocationResult: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/MethodInvocationResult.html
- Spring Framework — AnnotationMatchingPointcut: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aop/support/annotation/AnnotationMatchingPointcut.html
