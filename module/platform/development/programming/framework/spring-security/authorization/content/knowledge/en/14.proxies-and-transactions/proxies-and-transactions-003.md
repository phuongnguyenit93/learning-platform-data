# Self-invocation: When Internal Calls Bypass Spring Security and Transaction Proxies

## 1. Objective

In a Spring Security application, you may annotate a method with `@PreAuthorize` yet still see that method execute when a user lacks permission. One major cause is **self-invocation**: a method on a bean calls another method **on the same object**, such as `this.adminAction()` or `adminAction()`.

In standard Spring AOP proxy mode, this internal call does not pass back through the proxy. Consequently, advice attached to the internally called method—such as **method security** (`@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`) or **transactions** (`@Transactional`)—may **fail to trigger for the internal call**.

This lesson belongs to the **Proxies and Transactions** topic of Spring Security Authorization. After completing it, you will be able to:

1. Explain external calls going through a proxy versus `this.method()` calls bypassing the proxy.
2. Identify the consequences for `@PreAuthorize` and `@Transactional`, especially `REQUIRES_NEW`.
3. Distinguish between disabled annotations, unproxyable methods, and self-invocation.
4. Fix the design by moving the protected boundary to another bean and calling it via Spring injection.
5. Write Java 17+ integration tests proving one dangerous path and one safe path, rather than trusting that an annotation merely appears in source code.

**Scope:** Spring Framework AOP and Spring Security Method Security in **default proxy mode**, with Spring Boot 3.x / Spring Security 6.x examples. AspectJ weaving modes are discussed as conditional exceptions, not as the default.

## 2. How Does a Proxy Protect a Method?

When `@EnableMethodSecurity` is active, Spring Security creates advisors/interceptors that process authorization annotations on Spring-managed beans. A service method:

```java
@PreAuthorize("hasRole('ADMIN')")
public String adminAction() {
    return "secret";
}
```

is not enforced merely because Java sees the annotation. Only when a **client calls through the Spring proxy** do the relevant interceptors get a chance to check authorization before reaching the method body.

Illustrative flow:

```text
Call from another bean / controller
           |
           v
       Spring proxy
           |
           +--> Method Security interceptor: @PreAuthorize
           |        |
           |        +-- insufficient permissions --> AccessDeniedException
           |        |
           |        +-- sufficient permissions ----+
           |                                       |
           v                                       v
     relevant advice                        target.adminAction()
           |
           v
     result to caller
```

In practice, multiple advice layers may apply to a bean (authorization, transactions, logging...). The diagram only illustrates the concept; **the ordering between authorization and transactions depends on advisor configuration**, and a single fixed order should not be assumed. The decisive point here is that **the call must enter the advice chain through the proxy**.

### Self-invocation Skips the Called Method's Advice Chain

```java
public class ReportService {

    public String buildReport() {
        return this.adminAction(); // self-invocation
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String adminAction() {
        return "secret";
    }
}
```

If a controller calls `reportService.buildReport()` through the proxy, the proxy intercepts **the `buildReport` call**. Once execution enters the target, `buildReport()` calls `this.adminAction()` directly on the target itself. There is no second entry through the proxy to trigger `@PreAuthorize` on `adminAction()`.

The two call patterns can behave completely differently:

| Call pattern | Goes through proxy for `adminAction`? | Consequence when user lacks ADMIN |
| --- | --- | --- |
| `reportService.adminAction()` from bean/client holding proxy reference | Yes | `@PreAuthorize` blocks the call |
| `reportService.buildReport()` then `this.adminAction()` | **No** on internal step | `@PreAuthorize` on `adminAction` is skipped |
| `buildReport()` then `adminAction()` without `this` | **No** | Same self-invocation behavior |
| `coordinator.run()` calls `securedService.adminAction()` via Spring-injected dependency | Yes | `@PreAuthorize` is checked |

Note: if **`buildReport()` is also annotated** and called through the proxy, the advice on `buildReport` still takes effect. Only **the internal transition to `adminAction()`** is not intercepted by the proxy. You should not say "all security is lost" when other checks exist at executed boundaries.

## 3. Consequences for Method Security

For example, an API for regular staff might call `buildReport`; inside that method, `this.deleteAllReports()` is annotated with `@PreAuthorize("hasRole('ADMIN')")`. Without additional checks, the internal call path can reach the deletion logic even though the user lacks ADMIN permission. This is an **authorization boundary bypass** in service design, not merely a UI visibility bug.

Annotations affected if the call to the annotated method itself does not go through the proxy:

- `@PreAuthorize`: the decision to allow entry into the method body may not run.
- `@PostAuthorize`: the return-value check may not run.
- `@PreFilter`: input parameters may not be filtered.
- `@PostFilter`: returned data may not be filtered.

If an internal method reads sensitive data, bypassing `@PostFilter` can return **all results** instead of only the subset the user is allowed to view. If `@PreFilter` is skipped, a batch task may process elements that should have been excluded. Never design policies assuming "having an annotation makes every Java call safe."

Nor should HTTP endpoint controls be treated as sufficient protection for all paths. Services may be reused by scheduled jobs, listeners, batch workers, or other APIs. Those entry points need proper authentication, authorization contracts, and proxied calls.

## 4. Consequences for `@Transactional`

`@Transactional` in proxy mode shares **the exact same AOP boundary**. An internal method annotated with `@Transactional` yet called via `this.inner()` will not be handled by transaction advice for that call itself.

```java
@Service
public class BillingService {

    public void process() {
        this.saveInvoice(); // Does not go through transactional proxy for saveInvoice.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveInvoice() {
        // Internal call does not start a REQUIRES_NEW transaction on its own.
    }
}
```

**Scenario A — outer method has no transaction:** `process()` calls `saveInvoice()` directly; `REQUIRES_NEW` on `saveInvoice` is not applied, so no separate transaction is opened for this method. If repository methods inside open individual transactions, that is the behavior of **those repositories/other calls**, not proof that the annotation on `saveInvoice` ran.

**Scenario B — outer method already has a transaction:** if `process()` was called through the proxy and is already inside a transaction, `this.saveInvoice()` still executes **within the existing transaction**. In that case `TransactionSynchronizationManager.isActualTransactionActive()` can be `true`, yet `saveInvoice`'s `REQUIRES_NEW` was still **never applied**. To verify `REQUIRES_NEW` semantics properly, confirm a new/isolated transaction is created, such as with a rollback/commit integration test against a real database.

When a method carries both `@PreAuthorize` and `@Transactional`, an external call through the proxy can trigger **both** pieces of advice. A self-invocation call can bypass both pieces of advice on the target method. Never use whether a transaction is active to infer that authorization definitely ran: test both policies independently.

## 5. Runnable Java 17+ Example: Proving the Bug and the Fix

The following test suite uses Spring Boot 3.x, an H2 in-memory database to provide a transaction manager, Spring Security Method Security, and JUnit Jupiter. It demonstrates two setups:

- **Unsafe:** `BrokenService.unsafeEntry()` calls `this.adminAction()`. Neither `@PreAuthorize` nor `@Transactional` on `adminAction` is applied on the internal call.
- **Safe:** `Coordinator.safeEntry()` calls `SecuredService.adminAction()` through a **Spring-injected bean** reference. `SecuredService`'s proxy enforces authorization and opens a transaction when the user is authorized.

### 5.1. Project Structure and Dependencies

```text
self-invocation-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/SelfInvocationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'self-invocation-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

`spring-boot-starter-security` and `@EnableMethodSecurity` provide method security; `spring-boot-starter-jdbc` and H2 let Spring Boot auto-configure a `DataSource`/transaction manager. The Spring test context runs without a web server. The example does not persist real data to H2; H2 is used to observe **transaction boundaries**. In a real application, use the transaction manager appropriate for your project's data source.

### 5.2. Complete Test Class

Create `src/test/java/demo/SelfInvocationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = SelfInvocationTest.TestConfig.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
public class SelfInvocationTest {

    @Autowired BrokenService brokenService;
    @Autowired SecuredService securedService;
    @Autowired Coordinator coordinator;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @EnableTransactionManagement
    public static class TestConfig {

        @Bean
        BrokenService brokenService() {
            return new BrokenService();
        }

        @Bean
        SecuredService securedService() {
            return new SecuredService();
        }

        @Bean
        Coordinator coordinator(SecuredService securedService) {
            return new Coordinator(securedService);
        }
    }

    public static class BrokenService {

        public String unsafeEntry() {
            return this.adminAction(); // Internal: bypasses proxy.
        }

        @PreAuthorize("hasRole('ADMIN')")
        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public String adminAction() {
            return "txActive=" +
                TransactionSynchronizationManager.isActualTransactionActive();
        }
    }

    public static class SecuredService {

        @PreAuthorize("hasRole('ADMIN')")
        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public String adminAction() {
            return "txActive=" +
                TransactionSynchronizationManager.isActualTransactionActive();
        }
    }

    public static class Coordinator {
        private final SecuredService securedService;

        public Coordinator(SecuredService securedService) {
            this.securedService = securedService;
        }

        public String safeEntry() {
            // Different bean: goes through SecuredService's Spring proxy.
            return securedService.adminAction();
        }
    }

    @Test
    void servicesReallyAreSpringProxies() {
        assertThat(AopUtils.isAopProxy(brokenService)).isTrue();
        assertThat(AopUtils.isAopProxy(securedService)).isTrue();
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void directCallToRestrictedMethodIsDenied() {
        assertThatThrownBy(brokenService::adminAction)
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void selfInvocationUnexpectedlyBypassesAuthorizationAndTransaction() {
        // Example exposing bug, NOT desired safe behavior.
        assertThat(brokenService.unsafeEntry())
            .isEqualTo("txActive=false");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void differentBeanEnforcesAuthorization() {
        assertThatThrownBy(coordinator::safeEntry)
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void directAuthorizedCallStartsTransaction() {
        assertThat(securedService.adminAction())
            .isEqualTo("txActive=true");
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void differentBeanStartsTransactionForAuthorizedCaller() {
        assertThat(coordinator.safeEntry())
            .isEqualTo("txActive=true");
    }
}
```

**Why does the example test both security and transactions?** `@EnableMethodSecurity` registers method authorization advisors; `@EnableTransactionManagement` enables transaction proxies; `@EnableAutoConfiguration` together with the JDBC/H2 starter creates a transaction manager. The tests inject **the actual Spring beans** into `@Autowired` fields rather than instantiating services with `new` at the call site.

`BrokenService` and `SecuredService` are public concrete classes with public methods, so in this example configuration Spring can create class-based proxies. `AopUtils.isAopProxy(...)` proves at least that the beans are proxied; it **does not by itself prove every call path** goes through the proxy. The remaining tests verify that behavior.

### 5.3. Run Command and Expected Output

From the directory containing `build.gradle` (requires compatible Gradle and JDK 17+):

```bash
gradle test --tests demo.SelfInvocationTest
```

If the project includes a Gradle Wrapper, use `./gradlew test --tests demo.SelfInvocationTest` on Linux/macOS, or `gradlew.bat test --tests demo.SelfInvocationTest` on Windows.

**Expected outcome:** **6 JUnit tests pass** and Gradle finishes with `BUILD SUCCESSFUL`. This is the **expected result under the illustrative configuration**, not a log copied from an actual run. HTML test report: `build/reports/tests/test/index.html`.

| Test | Principal | Call path | Expected |
| --- | --- | --- | --- |
| `servicesReallyAreSpringProxies` | No user needed | Proxy check | Both services are AOP proxies |
| `directCallToRestrictedMethodIsDenied` | USER | Proxy → `BrokenService.adminAction` | `AccessDeniedException` |
| `selfInvocationUnexpectedlyBypassesAuthorizationAndTransaction` | USER | Proxy → `unsafeEntry` → `this.adminAction` | `"txActive=false"` — exposes vulnerability |
| `differentBeanEnforcesAuthorization` | USER | Coordinator → `SecuredService` proxy | `AccessDeniedException` |
| `directAuthorizedCallStartsTransaction` | ADMIN | Proxy → `SecuredService` | `"txActive=true"` |
| `differentBeanStartsTransactionForAuthorizedCaller` | ADMIN | Coordinator → `SecuredService` proxy | `"txActive=true"` |

Note that the self-invocation test **deliberately asserts dangerous behavior** so learners can observe the bug. Never adopt a test expecting "USER slips through" as a production acceptance criterion; after fixing a real service, the right assertion must be that **USER is denied** on every protected entry point.

## 6. Why Does Splitting Beans Solve the Bug?

The recommended approach is to place the sensitive action in a bean with clear responsibility and let the orchestrator call that bean through Spring dependency injection:

```java
@Service
public class AdminOperationService {

    @PreAuthorize("hasRole('ADMIN')")
    @Transactional
    public void runAdminOperation() {
        // Runs only after authorization is granted.
    }
}

@Service
public class OperationCoordinator {
    private final AdminOperationService adminOperationService;

    public OperationCoordinator(AdminOperationService adminOperationService) {
        this.adminOperationService = adminOperationService;
    }

    public void runWorkflow() {
        adminOperationService.runAdminOperation();
    }
}
```

This is an **illustrative architectural code snippet**, not a complete standalone application. When `OperationCoordinator` is a Spring bean receiving `AdminOperationService` from the container, the reference it invokes is the proxied bean. The `runAdminOperation()` call passes through both the security and transaction interception points.

Practical benefits:

- The authorization boundary becomes explicit: all callers reach the sensitive action through `AdminOperationService`.
- The transaction boundary becomes explicit: the annotation on `runAdminOperation()` takes effect when called through the proxy.
- Tests can invoke the same public method from a controller, coordinator, or another bean and verify the same policy.
- Avoids relying on a class re-invoking its own proxy.

If a workflow needs a transaction **spanning multiple operations**, you can place the transaction on the **entry-point method called through the proxy**, instead of overusing `REQUIRES_NEW` on internally called methods. However, transaction decisions must follow data consistency requirements; never alter propagation merely to make a test pass.

## 7. Alternatives and Limitations

### 7.1. Self-Injecting the Bean's Own Proxy

You can configure a reference to the bean/proxy itself and call through that reference instead of `this`, but this easily causes **circular dependencies**, complicates bean lifecycles, hurts readability, and creates risks when configuration changes. If forced to keep a single class, you must prove that reference is the proper proxy and maintain integration tests for security/transaction boundaries. Splitting beans is usually simpler.

### 7.2. `AopContext.currentProxy()`

Spring AOP offers `AopContext.currentProxy()` when proxies are configured to expose the proxy; this couples business logic directly to AOP infrastructure, fails easily if called outside a proxied context, and is discouraged in the Spring documentation. Never use it as a default "quick fix" for security logic.

### 7.3. AspectJ Weaving

Spring Security can be configured with `@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)`, and Spring transactions support AspectJ transaction weaving. Because advice is **woven into bytecode**, self-invocation can be intercepted differently than in proxy mode. However, that is an architectural change requiring dependencies, compile-time/load-time weaving, and dedicated tests; merely changing one annotation without full weaving setup **is not enough**. The main examples in this lesson **do not** use AspectJ.

### 7.4. JDK Dynamic Proxies, CGLIB, `final`/`private`

- **JDK dynamic proxy:** uses an interface to represent the bean; normally only calls arriving through the proxied interface are intercepted.
- **Class-based proxy (CGLIB):** generates a subclass to intercept overridable methods. A `final` class cannot be subclassed this way, a `final` method cannot be overridden, and a `private` method cannot be advised by standard proxy mechanisms.
- **Self-invocation:** exists with **both** JDK proxies and class-based proxies. Setting `proxyTargetClass=true` does not turn `this.someMethod()` into a proxied call.
- For special method visibilities, interfaces, and framework versions, verify behavior **against your specific Spring configuration**. The safest security boundary pattern in this lesson is a public method invoked from another bean through a Spring proxy, backed by denial tests.

## 8. Misconceptions That Cause Production Bugs

**Misconception 1: "If a bean has a proxy, every method call is safe."** Just because a bean is a proxy does not mean calls **from inside the target** pass through the proxy. `AopUtils.isAopProxy(...)` is only a supporting check; you must test real call paths.

**Misconception 2: "Adding `@EnableMethodSecurity` fixes self-invocation."** This annotation enables method security advisors, not a change in `this.method()` semantics. Without `@EnableMethodSecurity`, even direct external calls via a Spring bean may lack method security. That is a separate issue to verify independently.

**Misconception 3: "CGLIB intercepts internal calls too."** Class-based proxies do not solve self-invocation on the target. Never swap proxy types as a substitute for splitting beans.

**Misconception 4: "No exception means the user is authorized."** If a call path skips `@PreAuthorize`, no `AccessDeniedException` is thrown even though permissions were never checked. When investigating authorization bugs, check proxy traversal before concluding roles or SpEL are wrong.

**Misconception 5: "`@Transactional(REQUIRES_NEW)` still opens a transaction because the annotation is there."** On `this.inner()`, the inner method's propagation is not applied. If an outer transaction already exists, seeing `isActualTransactionActive() == true` still **does not prove** inner `REQUIRES_NEW` created a new transaction.

**Misconception 6: "Testing controllers is enough."** An endpoint may be well protected, while another code path invokes the service differently. Service-level integration tests should check authorization across real entry points and ensure sensitive actions have no self-invocation backdoors.

## 9. Inspection and Troubleshooting Checklist

When suspecting an annotation is being ignored, check in order:

1. **Origin:** is the object Spring-injected or created in code with `new`? Is `@EnableMethodSecurity` enabled, and does `@Transactional` have a valid transaction manager?
2. **Call shape:** is there `this.securedMethod()`, `securedMethod()` (implicit `this`), a call from a constructor or `@PostConstruct`, or an annotated private helper?
3. **Proxy path:** what does `AopUtils.isAopProxy(bean)` return? Is it a JDK proxy or class proxy? Is the method public/overridable?
4. **Permissions:** calling the secured method directly through the bean proxy as an unauthorized user must throw `AccessDeniedException`. Calling the workflow entry point as the same user must also be denied if required by the contract.
5. **Transactions:** does a direct external call open a transaction? If the method requires `REQUIRES_NEW`, verify isolation via commit/rollback behavior, not merely a boolean "is a transaction active."
6. **Design:** move sensitive actions into a separate bean, inject it, and invoke via proxy; re-test both allowed and denied behavior.
7. **Other defense layers:** enforce authorization at service/data-access layers as needed; never assume HTTP authorization or hidden UI buttons cover every code path.

A very strong telltale sign is **the exact same method**: when called from another bean an unauthorized user is blocked, yet when called from another method in the same class it runs. When you see this symptom, check for self-invocation before changing SpEL expressions or role configurations.

## 10. Practice Exercises

**Exercise 1 — Detect the bypass:** Using `BrokenService` above, add `public String report() { return adminAction(); }` without writing `this`. Under `@WithMockUser(roles = "USER")`, compare `brokenService.adminAction()` with `brokenService.report()`. Explain why the second call is still self-invocation.

**Exercise 2 — Fix the entry point:** Replace `BrokenService` with `Coordinator` and `SecuredService`. Write tests under role `USER` asserting that **every supported entry point** is denied. Write tests under role `ADMIN` asserting the business action executes and the transaction is active.

**Exercise 3 — Nested transactions:** Give an outer method `@Transactional` and an inner method `@Transactional(propagation = REQUIRES_NEW)`; compare calling `this.inner()` versus calling through a separate bean. Verify rollback/commit in both scopes on H2 instead of only `isActualTransactionActive()`. Predict which path genuinely gets an independent transaction.

**Exercise 4 — Method filtering:** Put `@PostFilter("filterObject.owner == authentication.name")` on a method returning a list of sensitive items. Write two tests: an external call through the proxy returns only the user's items, while self-invocation risks returning all items; fix it with a clear bean boundary. Never use the unsafe example as a production code path.

## 11. Summary

- **Spring AOP proxies** intercept calls entering **through the proxy**; `this.method()` and `method()` calls on the same target bypass the target method's advice.
- With **Spring Security Method Security**, self-invocation can bypass `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` on the internally called method.
- With **`@Transactional` proxy mode**, self-invocation can skip both transaction opening and propagation semantics of the inner method; an existing outer transaction (if present) is a separate situation.
- The easily verifiable design solution is **extracting sensitive actions to a separate bean**, injecting it, and calling through the Spring proxy.
- Always test **both call paths** with the same principal: direct proxy invocation and workflow invocation through another bean. Tests should also demonstrate the unsafe self-invocation path before fixing so you do not fix the wrong root cause.

## References

- Spring Security Reference — Method Security, advisors/proxies, and AspectJ: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Framework Reference — AOP Proxying Mechanisms and self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — `@Transactional` and proxy mode boundaries: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
