# Conditions for Choosing Spring AOP for a Specific Requirement

## Objectives and Scope

This article answers a practical question: **when faced with a requirement in a Spring application, what conditions make Spring AOP a suitable choice, when should you use built-in Spring mechanisms, and when must you choose another approach?**

Spring AOP is a mechanism for intercepting **method calls on Spring beans through proxies**. For a call matching a pointcut, the proxy executes advice before/after/around the target method. That is the technical boundary governing the choice, because Spring AOP does not automatically intercept every running piece of Java code. The content below focuses on selection criteria, limitations, and verification methods in a Spring environment; general AOP concepts are not repeated as a separate chapter.

## 1. The Decision Criteria

For each requirement, check the following questions in order.

| Condition | What to Verify in the Spring Application | Conclusion If Not Met |
| --- | --- | --- |
| **C1. The interception point is a method** | Behavior must be triggered when a bean method executes, e.g. `OrderService.submit()`. | If you need to catch field access, constructors, all internal calls, or arbitrary statements: Spring AOP proxy does not satisfy it. |
| **C2. The object is managed by Spring** | The target object is created/managed by ApplicationContext and can be proxied. | A manually instantiated `new OrderService()` outside the container does not automatically receive Spring AOP advice. |
| **C3. The call passes through the proxy** | The caller uses a bean injected/looked up from the container, typically another bean or a Spring integration class. | `this.method()` / internal calls on the target bypass the proxy; the called method's advice may not run. |
| **C4. The method is actually interceptable** | Check proxy type, visibility, `final`, and target object; design clear public APIs. | `private`/`final` do not work with subclass proxies; JDK proxies only intercept public calls via proxied interfaces. |
| **C5. The rule is reusable with clear boundaries** | The requirement applies the same policy across multiple services/methods without needing case-by-case business flow details. | If the rule is a specific business step, calling directly via a service/helper is clearer and easier to test. |
| **C6. Spring does not already offer a better solution** | Check `@Transactional`, Spring Security method security, `@Cacheable`, `@Async`, validation, Micrometer/Observation, MVC interceptor/filter, `@ControllerAdvice`. | Prefer the dedicated feature; do not write a custom aspect mimicking a built-in mechanism. |
| **C7. The advice's consequences are controllable** | Determine ordering, exceptions, return types, threads, latency, sensitive data, and testability. | If business correctness depends on hard-to-control ordering, async contexts, or uncertain interception, redesign. |

**Choose custom Spring AOP only when C1–C5 are met, C6 does not provide a more suitable option, and C7 is verified.** Key point: a requirement "appearing in many places" is not enough; it must also cross a proxy boundary supported by Spring.

## 2. Classifying Common Requirements in Spring

| Practical Requirement | What to Choose First | Should You Write a Custom Spring Aspect? |
| --- | --- | --- |
| Open/commit/rollback a service transaction | `@Transactional` and Spring transaction management | Usually **no**; custom aspects easily get propagation, rollback, and advisor order wrong. |
| Check user permissions on a method | Spring Security with `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize` where appropriate | Usually **no**; security requires standardized context, policy, and control ordering. |
| Cache service results | Spring Cache (`@Cacheable`, `@CacheEvict`, …) | Usually **no**; leverage standard keys, eviction, and cache managers. |
| Run a method asynchronously | `@Async` with a configured executor | Usually **no**; keep in mind similar proxy limitations and return/exception semantics. |
| Measure HTTP requests and analyze request/response | Servlet Filter, Spring MVC `HandlerInterceptor`, Micrometer/Observation, Actuator | Do not use service aspects as the default replacement for the HTTP pipeline. |
| Centralized HTTP exception handling | `@ControllerAdvice` / `@RestControllerAdvice` | No; that is the web response boundary. |
| Enforce domain invariants, such as checking credit limits before approving an order | Domain service, policy object, validation in the proper layer | Usually **no**; meaning and ordering are business logic that should stay explicitly visible. |
| Attach logging/auditing under a uniform policy for selected service methods | Existing logging/observation; if custom logic is needed, custom Spring Aspect | **Possibly**, if the pointcut is tightly scoped and handles failure/PII thoroughly. |
| Time calls to a set of Spring bean methods marked by an internal annotation | Micrometer/Observation or custom advice if specialized aggregation is needed | **Possibly**, especially when reusing a genuinely shared rule. |
| Catch field access, constructor calls, private methods, or objects created outside Spring | Redesign the extension point, explicit decorator, or AspectJ weaving if truly necessary | **Not possible using proxy-based Spring AOP alone**. |

**Note on Spring annotations:** several capabilities such as transactions, caching, async, and method security often use proxies/interceptors under the hood. That does not mean you should implement similar aspects yourself. Follow each Spring feature's contract and check its own activation configuration.

## 3. Applying the Criteria to Three Concrete Requirements

**Case A — permission check before `PaymentService.pay()`.** C1–C4 may pass if `pay()` is a Spring bean method called through a proxy, but **C6** directs us to prefer Spring Security method security over a custom `@Before`: permission policies need proper authentication, testing, and protection mechanisms.

**Case B — custom auditing on a group of methods annotated with `@TrackBusiness`.** When the service is injected via Spring, the public method can be intercepted, and the pointcut is scoped by the annotation, C1–C5 can pass. If existing observability tools do not cover the custom record and C7 allows preserving exceptions/return values, custom advice becomes a reasonable option. The example in section 5 implements this exact case.

**Case C — requirement to intercept every `this.charge()` call and every `new CheckoutService()` object.** C2/C3 are not met with the Spring AOP proxy model. Switching to CGLIB does not change internal call paths. Review bean boundaries, write explicit collaborator calls, or evaluate AspectJ weaving if out-of-container application is mandatory.

Thus, questions C1–C4 are **technical conditions**, C5–C6 decide where the responsibility belongs, and C7 decides whether the advice is safe regarding ordering, errors, asynchrony, and operational cost.

## 4. Selection Process for a Concrete Requirement

Suppose the prompt is: "Whenever certain critical service operations complete or raise an error, the system needs to record a trace according to a uniform policy."

**Step 1 — identify where to observe.** We want to track processing outcomes of service methods, not entire HTTP requests or repository accesses. Each service is a Spring bean and is called from other beans via DI: C1–C3 are satisfied.

**Step 2 — check built-in options.** If only standard traces/spans/metrics are needed, prefer Micrometer/Observation and logging infrastructure. If it is security/transactions, use the corresponding dedicated module. If a custom record with domain event fields after each eligible use case is truly needed, consider a dedicated aspect.

**Step 3 — define exact scope.** Use an explicit `@TrackBusiness` annotation for selected business methods instead of an overly broad pattern like `execution(* com.example..*(..))`, which can unintentionally match controllers, infrastructure, or unintended methods.

**Step 4 — decide timing.** If only a signal *before* the call is needed, `@Before` is enough. When recording only normal completion, use `@AfterReturning`; recording failure, `@AfterThrowing`; cleanup regardless of outcome, `@After`. Use `@Around` only when you must wrap the call, measure duration, transform results, or control continuation; `@Around` must handle `proceed()` accurately.

**Step 5 — check consequences.** Do not log sensitive payloads; preserve business return values/exceptions; review interactions with `@Transactional`, `@Async`, and advisor order. "Method returned" does not necessarily mean the transaction committed or the async task completed.

**Step 6 — confirm with integration tests.** Test calls through real beans, cases with/without the annotation, failures, self-invocation, and the configured proxy mode. If any criterion cannot be guaranteed, stop choosing Spring AOP for that requirement.

## 5. Runnable Example: Marking Only Service Methods Needing Audit

In a Spring Boot application supporting Java 17+, this example prints a message before an annotated method. It illustrates choosing Spring AOP when the requirement is a custom policy applied at Spring service boundaries.

The project needs Spring Boot and the AOP dependency matching the **exact major version**:

- Spring Boot **3.x**: `org.springframework.boot:spring-boot-starter-aop`.
- Spring Boot **4.x**: the starter was renamed to `org.springframework.boot:spring-boot-starter-aspectj`. Having "aspectj" in the name is the dependency supporting `@Aspect`-style pointcut/advice declarations; the example below still uses **Spring AOP proxies**, and does not perform AspectJ bytecode weaving.

Gradle example for a **Spring Boot 4.x project with plugins and dependency management already configured**:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

For a Boot 3.x project, change the dependency line to `spring-boot-starter-aop`. Do not add `@EnableAspectJAutoProxy` just to run the example when Boot already auto-configures AOP and `spring.aop.auto` is not disabled; in a self-configured Spring Framework application, you must explicitly enable `@EnableAspectJAutoProxy` and supply the required dependencies.

The following Java files live in `src/main/java/com/example/demo/`.

**File `TrackBusiness.java` — declares tracked methods:**

```java
package com.example.demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackBusiness {
}
```

**File `CheckoutService.java` — Spring bean performing business logic:**

```java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    @TrackBusiness
    public String placeOrder(String id) {
        return "created:" + id;
    }

    public String status() {
        return "ok";
    }
}
```

**File `BusinessAuditAspect.java` — advice matching only the selected annotation:**

```java
package com.example.demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class BusinessAuditAspect {
    @Before("@annotation(com.example.demo.TrackBusiness)")
    public void beforeTrackedCall(JoinPoint joinPoint) {
        System.out.println("AOP:" + joinPoint.getSignature().getName());
    }
}
```

**File `DemoApplication.java` — retrieving `CheckoutService` via Spring DI:**

```java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CheckoutService checkoutService) {
        return args -> {
            System.out.println(checkoutService.placeOrder("ORD-1"));
            System.out.println(checkoutService.status());
        };
    }
}
```

**Run:** with the Gradle wrapper and Spring Boot plugin configured in the project, use `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). On Maven/Spring Boot Maven Plugin, use `mvn spring-boot:run`. With Spring Boot 3/4, adhere to the compatible JDK and Gradle/Maven versions of the chosen Boot release.

In the application's log, the three lines printed by the demo in order are:

```text
AOP:placeOrder
created:ORD-1
ok
```

Other Spring Boot startup lines are omitted in this output snippet. `placeOrder()` is advised because it has `@TrackBusiness` and is called through the injected proxy. `status()` lacks the annotation, so `AOP:status` does not appear. If you create `new CheckoutService()` and call `placeOrder()` directly, that object has no container-applied proxy, so there is no `AOP:placeOrder` line.

**From need to decision:** for a custom audit policy on a group of service methods, this is a case where Spring AOP can be chosen. If the requirement shifts to "every HTTP request must have an access log," the proper solution should be re-evaluated at Servlet Filter/MVC/Micrometer rather than blindly broadening an application-wide pointcut.

## 6. When `@Around` Must Be Used: Additional Safety Conditions

Choose `@Around` only if the requirement truly needs measuring around the method or actively intervening in execution. This is an illustrative snippet, **not a standalone file**, replacing the advice method in the example above when timing is desired:

```java
@Around("@annotation(com.example.demo.TrackBusiness)")
public Object measure(ProceedingJoinPoint point) throws Throwable {
    long started = System.nanoTime();
    try {
        return point.proceed();
    } finally {
        long elapsedNanos = System.nanoTime() - started;
        System.out.println("elapsed-ns=" + elapsedNanos);
    }
}
```

The snippet above requires importing `org.aspectj.lang.ProceedingJoinPoint` and `org.aspectj.lang.annotation.Around` in the `@Aspect` class; `elapsed-ns` changes on each run so there is no fixed numeric stdout. `finally` ensures measurement occurs even when the method throws an exception, while `return point.proceed()` preserves the original return value and exception. Do not swallow exceptions, do not forget `proceed()`, and do not call `proceed()` multiple times unless the business requirement genuinely allows re-execution.

If the method returns `CompletableFuture`/`Mono`/`Flux` or starts background processing, measuring around the call may only measure **the time to create/return the async handle**, not the completion time of processing. To measure true completion, use a mechanism tied to the return type's lifecycle or appropriate observability. With transactions, advisor position determines whether measurement wraps around or sits inside the transaction boundary; do not assume advice execution time equals successful commit time.

## 7. Verification Checklist Before Approving Spring AOP

- **Boundaries:** have you listed the methods to intercept, callers, and Spring beans owning those methods? Are there `this`/`new` calls that lose interception?
- **Proxy type:** have you confirmed JDK or class-based proxy and checked `final`, `private`, method visibility, and interface methods?
- **Pointcut:** have you used `@annotation`, `within`, `execution`, or `bean(...)` scoped properly to Spring beans? Is there risk of matching unintended methods?
- **Ordering:** if combined with transactions/security/caching/async, have you verified advisor order and where logic runs?
- **Semantics:** does advice preserve return values/exceptions? Does it distinguish success/failure, rollback, and async completion? Is there personal data/tokens to exclude from logs?
- **Operations:** have you evaluated proxy/pointcut/logging cost, avoided loops from advice calling a bean matched by advice, and ensured observability via tests?
- **Alternatives:** would Spring Security, `@Transactional`, caching, `@Async`, Micrometer/Observation, Filter/Interceptor, or explicit code fit better?

At minimum, write integration tests with a real ApplicationContext for (a) a selected method called from another bean getting advised, (b) an unselected method not getting advised, (c) exceptions still propagating, and (d) internal calls and objects created outside Spring behaving according to proxy limits. Use `org.springframework.aop.support.AopUtils.isAopProxy(bean)` to aid diagnostics when needed, but **a proxy existing does not prove every method matches the pointcut**: verify each call's effect.

## 8. Misconceptions That Easily Lead to Wrong Choices

1. **"Having `@Aspect` means every method gets intercepted."** False: the aspect class must be a Spring bean, AOP infrastructure must be enabled, the pointcut must match, and the call must go through the proxy.
2. **"Using CGLIB handles `this.method()`/private."** False: self-invocation still executes on the target; private cannot be overridden.
3. **"Cross-cutting always means writing a custom aspect."** False: many Spring capabilities already have dedicated modules with complete semantics and better operational tooling.
4. **"`@Around` and `@Before` are freely interchangeable."** False: `@Around` decides whether to call the target and can alter results/exceptions; pick the least powerful advice that meets the requirement.
5. **"AOP can time completion of every async task."** False: distinguish invocation time from completion of a future/reactive stream.
6. **"Advice running after a method returns means the transaction committed."** Not necessarily: proxy/advisor order and transaction boundaries must be checked separately.
7. **"Enabling `@EnableAspectJAutoProxy` means AspectJ weaving is active."** False: Spring AOP's proxy mechanism remains the foundation; weaving is a different deployment mode.

**Closing rule:** choose Spring AOP when you need shared behavior at **method boundaries of Spring-managed beans**, calls **actually pass through proxies**, visibility/proxy/advisor limitations are **acceptable**, and no dedicated Spring component fits better. When any foundational condition is not met, adjust design boundaries or use another mechanism before writing an aspect.

## Official Reference Documentation

- [Spring Framework — Spring AOP capabilities](https://docs.spring.io/spring-framework/reference/core/aop/introduction-spring-defn.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Declaring Pointcuts](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Boot — AOP auto-configuration](https://docs.spring.io/spring-boot/reference/features/aop.html)
- [Spring Boot 4.0 Migration Guide — AOP starter rename](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)