# Refactoring to route a call through a collaborator bean in Spring AOP

## 1. Goal: creating a call boundary that genuinely passes through a Spring proxy

When a Spring service calls another method **on the same target instance** using `this.method()`, that call does not go back through the proxy created by Spring AOP. `@Aspect` advice on the internally called method may **not run**, even though the same method is intercepted when another bean calls it through the proxy.

A straightforward fix with minimal infrastructure coupling is to **extract the work requiring interception into a collaborator Spring bean**, then have the original service **inject** that bean and invoke the method through the Spring-managed reference.

```text
BEFORE (no proxy boundary for the internal method)

Caller --> OrderService Spring proxy --> target OrderService.place()
                                               |
                                               +--> this.validate() --X--> proxy
                                                  (advice for validate does not run)

AFTER (collaborator proxy boundary)

Caller --> Spring bean OrderApplicationService.place()
                         |
                         +--> injected ValidationService proxy
                                      |
                                      +--> advice for ValidationService.validate()
                                      |
                                      +--> target ValidationService.validate()
```

**The crucial condition is not merely having two classes.** The collaborator bean must be created/managed by Spring, the caller must hold **the proxy reference injected by Spring**, the method must be interceptable by that proxy type, the pointcut must match, and the aspect must be registered/enabled in the appropriate context.

This lesson focuses solely on **Spring AOP @AspectJ and calls through Spring beans/proxies**, as that is the scope of the Spring Aspect topic. Splitting beans is a code organization technique, but the motivation and verification here are about **fixing Spring's interception boundary**, not introducing general AOP theory.

## 2. Diagnosing self-invocation accurately before refactoring

Initial example:

```java
@Service
public class OrderService {
    public String place(String id) {
        return validate(id); // equivalent to this.validate(id)
    }

    public String validate(String id) {
        return "validated:" + id;
    }
}
```

Suppose Spring has an aspect:

```java
@Aspect
@Component
public class ValidationAspect {
    @Before("execution(public * com.example.orders.OrderService.validate(..))")
    public void beforeValidation() {
        System.out.println("audit:validate");
    }
}
```

These two snippets are **illustrative**, not a standalone runnable application because they require the right packages, Spring context, `@EnableAspectJAutoProxy` or Boot AOP auto-configuration, and corresponding dependencies.

If `OrderService` is already Spring-proxied and the pointcut matches:

- Another bean calling `orderService.validate("A")` through the injected proxy → **can** print `audit:validate`.
- Calling `orderService.place("A")` through the proxy → the target executes `place`, yet inside the target the `this.validate("A")` call goes **directly**, without returning to the proxy; advice targeting only `validate` **does not run** for that call.
- `AopUtils.isAopProxy(orderService) == true` does not prove `validate` is intercepted on every call path.
- Making `validate` `public` or enabling `proxyTargetClass=true` does not route self-invocation back through the proxy.
- Adding `@Transactional`, `@Cacheable`, `@Async`, or other proxy-based annotations to the internal method does not substitute for calling through a proxy either; those features also have their own activation mechanisms.

**Why refactor instead of adding an annotation?** In the Spring AOP proxy model, interceptors apply when a caller invokes **through a proxy reference**. `this` inside the target is a reference to the executing object, not a loopback through the Spring proxy. The Spring documentation refers to this as self-invocation bypassing advice.

## 3. Refactoring pattern: moving a responsibility to a collaborator

Keep the business API `place(..)` on the orchestrating service, and move the method needing advice to a `ValidationService` bean:

```java
@Service
public class ValidationService {
    public String validate(String id) {
        return "validated:" + id;
    }
}
```

```java
@Service
public class OrderApplicationService {
    private final ValidationService validationService;

    public OrderApplicationService(ValidationService validationService) {
        this.validationService = validationService;
    }

    public String place(String id) {
        return validationService.validate(id);
    }
}
```

These two illustrative snippets assume they are in a package covered by component scanning. Key changes:

1. `ValidationService` is a **separate bean**, eligible for Spring to apply advisors and create a proxy.
2. `OrderApplicationService` receives the dependency via **constructor injection**; it does not call `new ValidationService()` manually.
3. `place(..)` invokes `validationService.validate(..)` on the injected reference; if that reference is a Spring AOP proxy, advice for `ValidationService.validate(..)` is evaluated before the target.
4. The application's entry API does not have to change because validation is now delegated to the collaborator.
5. Rules around data, exceptions, and transaction boundaries must be reviewed against actual responsibilities, rather than assuming a structural refactor preserves all semantics automatically.

Spring does not need a separate Spring bean for **every** private helper. Extract only when a method has a clear responsibility, serves as an entry point requiring proxy advice, needs independent reuse/testing, or defines the right boundary for transactions, validation, auditing, metrics, and security.

### 3.1. Pointing the advice at the right class after splitting

The old pointcut targeting the `OrderService` method must be updated if the advice should follow the relocated responsibility:

```java
@Aspect
@Component
public class ValidationAspect {
    @Before(
        "execution(public * com.example.orders.ValidationService.validate(..))"
    )
    public void beforeValidation() {
        System.out.println("audit:validate");
    }
}
```

**Do not treat changing the class name as an optional detail.** With pointcuts using `execution(...)` on a fully-qualified class, after refactoring the method belongs to a different type; without updating the pointcut, the advisor will not match the new collaborator. Similarly, if using `within(..)`, `bean(..)`, or annotations on the old service, confirm whether the expression still targets the intended bean/method.

You can use a **dedicated annotation** on the collaborator method to reduce coupling to class names, though that annotation must still be matched by a Spring AOP pointcut on the actual executed method and callers must still go through the proxy. Avoid widening a pointcut excessively just to "catch it somehow", as that may intercept unintended beans.

## 4. Runnable demo: before and after in the same Spring ApplicationContext

The demo uses **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, Gradle, and plain Java configuration. One context holds both the legacy service and the collaborator version to compare them with the same aspect. Spring Boot is not used to auto-enable proxying implicitly: `@EnableAspectJAutoProxy` itself demonstrates the Spring-specific requirement.

### 4.1. Project structure

```text
spring-aop-collaborator-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/boundary/
    ├── Main.java
    ├── AppConfig.java
    ├── LegacyOrderService.java
    ├── ValidationService.java
    ├── OrderApplicationService.java
    └── TraceAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aop-collaborator-demo'
```

**`build.gradle`**

```gradle
plugins {
    id 'java'
    id 'application'
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
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.boundary.Main'
}
```

Spring Framework 6.x runs on Java 17+. In a real Spring Boot project, let the BOM/dependency management select compatible versions rather than copying demo versions into a project using a different Boot major version.

### 4.2. Legacy service — internal call

**`LegacyOrderService.java`**

```java
package com.example.boundary;

public class LegacyOrderService {
    public String place(String id) {
        return validate(id); // self-invocation: bypasses advice on validate
    }

    public String validate(String id) {
        return "validated:" + id;
    }
}
```

In this class, both `place` and `validate` are public so Spring's proxy is permitted to intercept based on method signature. **The missing advice is caused by the call path, not visibility.**

### 4.3. Collaborator bean — advised method gets its own entry point

**`ValidationService.java`**

```java
package com.example.boundary;

public class ValidationService {
    public String validate(String id) {
        return "validated:" + id;
    }
}
```

### 4.4. Orchestrating service — inject collaborator instead of self-call

**`OrderApplicationService.java`**

```java
package com.example.boundary;

public class OrderApplicationService {
    private final ValidationService validationService;

    public OrderApplicationService(ValidationService validationService) {
        this.validationService = validationService;
    }

    public String place(String id) {
        return validationService.validate(id);
    }
}
```

`OrderApplicationService` has no `validate` method; every path through `place` uses solely the dependency Spring injects into the constructor.

### 4.5. Aspect counting which join points are actually intercepted

**`TraceAspect.java`**

```java
package com.example.boundary;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before(
        "execution(public * com.example.boundary.LegacyOrderService.validate(..))"
        + " || execution(public * com.example.boundary.ValidationService.validate(..))"
    )
    public void beforeValidation(JoinPoint point) {
        System.out.println(
            "advice:" + point.getSignature().getDeclaringType().getSimpleName()
            + "." + point.getSignature().getName()
        );
    }
}
```

The pointcut uses an **OR operator** to compare the exact same advice across two specific methods. `getSignature().getDeclaringType().getSimpleName()` identifies which class's method triggered the advice. There is no advice on `place(..)`, because the test targets **`validate(..)` across two call paths**.

### 4.6. Spring config — defining beans and proxies

**`AppConfig.java`**

```java
package com.example.boundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    LegacyOrderService legacyOrderService() {
        return new LegacyOrderService();
    }

    @Bean
    ValidationService validationService() {
        return new ValidationService();
    }

    @Bean
    OrderApplicationService orderApplicationService(
            ValidationService validationService) {
        return new OrderApplicationService(validationService);
    }
}
```

Having the factory method accept `ValidationService` causes Spring to inject the container-processed bean. The target method `validate` matches the aspect, so `ValidationService` is normally wrapped by Spring in a class-based proxy. There is no `new ValidationService()` inside `OrderApplicationService`.

`TraceAspect` is a **Spring-managed `@Aspect` bean** created via `@Bean`. `@EnableAspectJAutoProxy` enables Spring to inspect advice and auto-proxy matching targets. Setting `proxyTargetClass=true` allows targets without interfaces to be accessed by concrete class in the example.

### 4.7. Main — observing both call paths

**`Main.java`**

```java
package com.example.boundary;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            LegacyOrderService legacy =
                    context.getBean(LegacyOrderService.class);
            ValidationService validation =
                    context.getBean(ValidationService.class);
            OrderApplicationService refactored =
                    context.getBean(OrderApplicationService.class);

            System.out.println("legacyProxy=" + AopUtils.isAopProxy(legacy));
            System.out.println(
                    "collaboratorProxy=" + AopUtils.isAopProxy(validation)
            );

            System.out.println("legacyInternal=" + legacy.place("A"));
            System.out.println("legacyExternal=" + legacy.validate("B"));
            System.out.println("afterRefactor=" + refactored.place("C"));
        }
    }
}
```

In the project directory, run:

```bash
gradle run --quiet
```

If using a Gradle Wrapper: `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

**Lines printed by `System.out` in the demo, in exact order:**

```text
legacyProxy=true
collaboratorProxy=true
legacyInternal=validated:A
advice:LegacyOrderService.validate
legacyExternal=validated:B
advice:ValidationService.validate
afterRefactor=validated:C
```

This is the application code's output, excluding unexpected JVM/build tool warnings/logs or logging configuration.

### 4.8. Why stdout demonstrates both the problem and the fix accurately

| Call | Actual Spring proxy entry | Advice result on `validate(..)` |
| --- | --- | --- |
| `legacy.place("A")` | Caller goes through `LegacyOrderService` proxy for `place`, then target uses `this.validate` | **No** `advice:LegacyOrderService.validate` for this case |
| `legacy.validate("B")` | Caller enters `LegacyOrderService` proxy directly on `validate` | `advice:LegacyOrderService.validate` runs |
| `refactored.place("C")` | Caller enters `OrderApplicationService` (not necessarily proxied); service calls **injected proxy** `ValidationService.validate` | `advice:ValidationService.validate` runs |

Both checks `legacyProxy=true` and `collaboratorProxy=true` prove **proxies exist**, but they **do not replace** checking advice execution on the specific call path. The fact that advice appears only on the external call (legacy) and the collaborator call (refactored) proves the difference.

`OrderApplicationService.place` in the demo **does not need an AOP proxy** because no advisor matches it. What matters is that it holds a **dependency reference** to `ValidationService`'s Spring proxy. That is why "extracting a collaborator bean" works without self-injection or `AopContext.currentProxy()`.

## 5. Why moving to a plain Java class is usually not enough

This example is **still wrong** if the collaborator is instantiated manually:

```java
public class OrderApplicationService {
    private final ValidationService validationService =
            new ValidationService(); // not managed by Spring

    public String place(String id) {
        return validationService.validate(id);
    }
}
```

The code has two separate classes, yet the reference is not a Spring-managed proxy. Spring `@Aspect` does not automatically intercept objects created with `new`; moving a method to a new file while still instantiating it manually only changes structure, **not the AOP boundary**.

**The right way** is constructor injection from the container:

```java
public class OrderApplicationService {
    private final ValidationService validationService;

    public OrderApplicationService(ValidationService validationService) {
        this.validationService = validationService;
    }

    public String place(String id) {
        return validationService.validate(id);
    }
}
```

Register `ValidationService` with `@Component`/`@Service` and proper package component scanning, or with `@Bean`. The caller should also obtain `OrderApplicationService` from the context instead of manually `new`-ing an object and wiring dependencies itself, staying consistent with application lifecycle and configuration.

### 5.1. Two valid ways to register a collaborator

**Component scan:**

```java
@Service
public class ValidationService {
    public String validate(String id) {
        return "validated:" + id;
    }
}
```

```java
@Service
public class OrderApplicationService {
    private final ValidationService validationService;

    public OrderApplicationService(ValidationService validationService) {
        this.validationService = validationService;
    }

    public String place(String id) {
        return validationService.validate(id);
    }
}
```

With component scan, `@Service` creates bean candidates. If the aspect class uses `@Aspect`, it also needs `@Component` or `@Bean` so it is itself a Spring bean.

**Registering via `@Bean`:** as in `AppConfig` in the full demo, classes do not need `@Service` and beans are wired via factory method parameters. Pick one clear registration approach, avoiding simultaneous component-scanning and `@Bean` definitions that create two instances of the same type and cause injection ambiguity or unexpected advisor side effects.

### 5.2. Scope and context must match

The collaborator bean must exist in the right context. In applications with root/child `ApplicationContext`s, proxy infrastructure and advisors are scoped to their context; do not assume enabling AOP in one context proxies every target in another context.

A singleton collaborator can be shared across many callers; you do not need a separate copy per caller just for advice to run. If the collaborator holds mutable request state, becoming a singleton bean introduces **its own concurrency risks** and must be designed as stateless or receive state via parameters. Never store the current user/order in a field of a singleton aspect or collaborator.

## 6. Preserving semantics when changing bean boundaries

Refactoring is only safe when you examine the **business contract** before and after, rather than just moving lines of code between classes.

### 6.1. Inputs, outputs, and exceptions

- Preserve the business signatures callers rely on or plan API changes explicitly.
- Do not accidentally swallow or alter exceptions just from adding a wrapper bean.
- If the advice is `@Around` with `proceed()`, preserve the exact number of target invocations and argument/return/exception propagation semantics. A refactor that causes advice to run where it did not before may make retry, timeout, or logging logic execute **for real** for the first time; review side effects carefully.
- If the helper previously used private fields of the old class, **do not automatically expose mutable fields**; instead pass required data to the collaborator via method arguments or an explicit dependency.

### 6.2. Transaction boundaries may change

Spring `@Transactional` is a classic example of proxy interception. Distinguish carefully:

```java
@Service
public class ImportService {
    public void runBatch() {
        savePart(); // self-call: savePart's transaction advice does not run
    }

    @Transactional
    public void savePart() {
        // update data
    }
}
```

If you move `savePart()` to an `ImportWriter` Spring bean and inject it into `ImportService`, calling it from `runBatch()` through the injected proxy can trigger the transaction interceptor **when transaction management is enabled** and a matching `PlatformTransactionManager` is present.

That causes **real semantic changes**, not just fixing advice logs:

- With `Propagation.REQUIRED`, if an outer transaction exists, the inner call normally joins it; otherwise, the transaction interceptor can start a new transaction.
- With `REQUIRES_NEW`, going through the proxy can open a separate transaction with independent commit/rollback; before refactoring, the self-call may have skipped this requirement.
- `@Transactional` on a collaborator method works only when Spring transaction activation/configuration is complete, the method is interceptable, and callers go through the proxy. `@EnableAspectJAutoProxy` alone **does not activate** `@Transactional`.
- Exception translation, checked exceptions, and rollback rules depend on transaction configuration; do not assume every exception triggers rollback.

This is an **illustrative snippet** without DB configuration and is not a runnable project. If a transaction boundary changes, write integration tests against an appropriate database/test container to verify rollback/commit behavior as required, rather than merely counting console advice output.

### 6.3. Security, caching, and async also have boundaries

| Spring capability | When original self-call bypassed proxy | After moving to injected collaborator |
| --- | --- | --- |
| Spring `@Aspect` audit/metrics | Advice did not run on internal method | Advisor can run on collaborator entry method if pointcut matches |
| `@Transactional` | Inner transaction interceptor could be skipped | Can start/join transaction per actual propagation |
| `@Cacheable`/`@CacheEvict` | Cache advice on inner method was bypassed | Cache advice can execute, changing cache hits/misses/evictions |
| `@Async` | Inner method could run on caller thread instead of executor | Method called via proxy can be submitted to executor; watch exception handling/context propagation |
| Method security such as `@PreAuthorize` | Inner authorization advice was bypassed | Can be enforced when method-level security is enabled and policy matches |

The capabilities in the table **have their own enablement/configuration** and are not turned on collectively by a single `@Aspect` annotation. When a new boundary causes interception to run for real, inspect changes in transactions, threads, latency, retries, audit logs, and security. In particular, never treat "tests passed previously" as sufficient if those tests accidentally bypassed policy.

### 6.4. When pointcuts use bean names or types

When moving code from bean `orderService` to `validationService`:

- `bean(orderService)` does not automatically match the new bean; update the bean name expression if advice should follow the collaborator.
- `within(com.example.orders.OrderService)` or `execution(* OrderService.*(..))` may no longer match.
- `@annotation(...)` matches annotations on the actual method: if the annotation moved to the collaborator method, verify the annotation type, visibility, and corresponding interface proxy.
- `this(...)` refers to the proxy type; `target(...)` refers to the target type; JDK proxies and class proxies can yield different type-matching results.
- If intercepting an interface contract, the public method must belong to a proxied interface when using a JDK dynamic proxy.

Keep pointcuts tightly scoped; after refactoring, avoid loosening an expression overly wide merely to avoid updating a class name.

## 7. Designing clean collaborator boundaries

A sensible split looks like:

```text
OrderApplicationService (orchestrator)
  - invokes business steps and preserves the use-case API
  - coordinates results/exceptions
  - contains only necessary orchestration logic
          |
          +--> ValidationService (Spring-managed collaborator)
                 - single responsibility easily called through a proxy
                 - public validation operation
                 - properly scoped pointcut/advisor
                 - explicit dependency
```

Criteria:

1. **Cohesion:** the collaborator should represent a genuine named responsibility/sub-use-case (validate, charge, persist, applyRule), not a meaningless `AopWorkaroundService`.
2. **Constructor injection:** dependencies are explicit, easy to swap with test doubles, and avoid hidden dependency cycles.
3. **Public entry contract:** in typical designs, methods needing interception are public and non-final for reliable compatibility with class proxies. With JDK proxies, the method must be on an interface.
4. **No cyclic dependencies:** A → B is clear; if B also needs A, consider extracting another responsibility rather than using circular proxies or self-injection.
5. **Do not move every private helper just for AOP:** helpers that do not need advice can stay private and be called directly.
6. **Appropriate scope:** usually stateless singletons; never store request-sensitive mutable data inside a singleton collaborator.
7. **Do not miss legacy callers:** update every call path needing the policy, not just the new path in a demo.
8. **Preserve error handling:** retain exception/return-value contracts unless a change was explicitly decided and tested.

### When the original service still needs advice on its own method

Not every piece of advice has to move to a collaborator. If a concern applies to **the entire `place()` operation**, rather than `validate()` alone, consider attaching the pointcut to the public entry method `place()`, which external callers already invoke through the proxy. That can be a more natural boundary when the policy covers the whole workflow.

However, if the requirement is that **only the validation step** has its own transaction/cache/audit, moving that step to a collaborator guarantees an explicit proxy entry point. Decide based on desired semantics, not a default proxy trick.

## 8. Alternatives to avoid self-invocation and why a collaborator is usually better

### 8.1. Self-injection

Some codebases try injecting the proxy into the bean itself:

```java
@Service
public class RiskyService {
    @Autowired
    private RiskyService self;

    public void outer() {
        self.inner();
    }

    public void inner() {
        // expecting advice to run
    }
}
```

This is **illustrative code**, not part of the runnable demo. Self-injection can introduce circular dependencies, obscure wiring timing, depend on Boot/Spring configuration, and fail to separate responsibilities. While it can invoke the proxy once the bean is initialized, it is **not a recommended choice** for long-term design.

### 8.2. `AopContext.currentProxy()`

```java
((RiskyService) AopContext.currentProxy()).inner();
```

This is also just an illustrative snippet: it requires `@EnableAspectJAutoProxy(exposeProxy=true)`, being inside a proxied call, a compatible cast type (potentially an interface for JDK proxies), and importing `org.springframework.aop.framework.AopContext`. It couples business code to Spring's AOP API, cannot be called freely inside constructors/`@PostConstruct`, and does not propagate across async threads automatically.

**Key difference:** a collaborator keeps business code largely unaware that AOP is enabled; it only knows about an injected dependency interface/class. This is also the refactoring approach recommended by the Spring documentation ahead of manual proxy workarounds.

### 8.3. Calling ApplicationContext.getBean on itself

```java
MyService proxy = applicationContext.getBean(MyService.class);
proxy.inner();
```

When a class must know about `ApplicationContext` just to call itself, the design increases container coupling and can trigger initialization/circular-dependency errors. During startup code, the proxy may not even be finalized yet. Unless infrastructure genuinely needs a service locator, prefer constructor injection of a collaborator.

### 8.4. AspectJ weaving

AspectJ compile-time/load-time weaving uses a different mechanism and can handle calls that do not traverse a Spring proxy in certain cases. However, `@EnableAspectJAutoProxy` **does not enable weaving**. When requirements fit method calls through proxies, refactoring to a collaborator is usually simpler than deploying weaving agents/compilers. Evaluate weaving separately only when you truly need to intercept behavior beyond proxy capabilities, such as constructors/field access or internal calls whose structure cannot be changed.

## 9. Common Spring issues after refactoring

| Symptom | Possible cause | How to inspect and resolve |
| --- | --- | --- |
| Advice still does not run after splitting class | Collaborator created with `new`, not a Spring bean | Register via `@Component`/`@Service` + scan, or `@Bean`; inject from context |
| Spring bean exists yet advice still does not run | Aspect is not a bean, missing `@EnableAspectJAutoProxy`/Boot AOP auto-config, or stale pointcut | List aspect beans, check config, match new method/target |
| `AopUtils.isAopProxy(collaborator)==false` | No matching advisor, target ineligible for proxy, or wrong context | Check pointcut and auto-proxy infrastructure |
| Proxy is true yet no advice appears | Caller still calls helper on target or advice targets a different method | Trace call path, run test calling collaborator directly via Spring reference |
| Final class or final method | Class-based Spring proxy cannot subclass/override | Refactor entry method or use JDK interface proxy if appropriate |
| Injecting concrete implementation fails under JDK proxy | Proxy only implements interfaces | Inject by interface, or consider class proxy if the class is eligible |
| Spring reports circular dependency | Bean A injects B and B injects A, or self-injects | Break the cycle, split responsibilities, keep dependency graph acyclic |
| Advice runs twice | Pointcut matches both outer and inner, or multiple aspects/advisors/bean registrations apply | Check join-point logs, aspect bean count, advisor order, and scope |
| Transaction/caching/async behaves differently than before | Refactor caused a previously unproxied method to be intercepted | Test desired semantics, propagation/cache keys/thread context |
| Logging disappeared after renaming/moving class | Pointcut depended on old type/bean/annotation name | Update and test expression against collaborator |
| Call from `@PostConstruct` still has no advice | Callback during target initialization has not passed through proxy | Choose an appropriate startup hook and call collaborator via injected proxy after init |
| Test creates object with `new` yet expects AOP | Test bypasses Spring container | Write integration test with a real ApplicationContext |

### 9.1. How to verify the collaborator itself is genuinely a proxy

```java
ValidationService bean = context.getBean(ValidationService.class);
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

In the demo, both results are `true`. This is an **illustrative snippet** requiring a context and imports as in `Main.java`. Add a recorder to the advice to verify that calling `bean.validate(..)` emits an event. **Proxy being true does not guarantee advice runs on arbitrary methods.**

For interface proxies, use `AopUtils.isJdkDynamicProxy(bean)` and look up by interface. Avoid casting to a concrete class when the runtime bean is a JDK proxy.

## 10. Before/after testing to ensure no unintended business changes

Checking stdout alone is not enough for production. A solid test suite covers:

1. **Business baseline:** with identical valid and invalid inputs, both legacy and refactored versions return expected outputs/exceptions per contract.
2. **Bean wiring:** context contains `ValidationService` and `OrderApplicationService` as intended single beans; dependencies are Spring beans.
3. **Target proxy:** `AopUtils.isAopProxy(validationService)` is true when required advisors are registered.
4. **Interception:** a recorder test confirms `refactored.place(..)` triggers exactly one event from the collaborator, whereas legacy self-invocation emits no `validate` event.
5. **Pointcut precision:** other methods on the collaborator are not advised if out of scope; prevent unintended advisor matches.
6. **Exception paths:** errors from the collaborator propagate/translate per contract rather than being swallowed by advice.
7. **Transactions/security/caching:** if present, test real business effects (rollback/deny/cache hit), not just console log assertions.
8. **Concurrent calls:** singleton collaborators/aspects store no per-request mutable state; test thread safety if dependencies are shared.
9. **Context startup:** no circular dependencies or premature calls before proxies are finalized.
10. **Regression:** legacy callers still route through the proper public API; no bypass path skips the collaborator to violate policy.

### 10.1. Integration testing with Spring context instead of `new`

To test AOP for real, use `AnnotationConfigApplicationContext` as in the demo or, when using Spring Test, `@SpringJUnitConfig` with the right configuration. `new ValidationService()` tests the business method but **cannot** prove advice execution because no auto-proxy infrastructure is present.

A test sink/recorder can replace `System.out`:

```java
public final class EventRecorder {
    private final java.util.List<String> events =
            new java.util.concurrent.CopyOnWriteArrayList<>();

    public void record(String value) {
        events.add(value);
    }

    public java.util.List<String> events() {
        return java.util.List.copyOf(events);
    }
}
```

This is an **illustrative Java snippet** not automatically wired into the demo; to test with it, add an `EventRecorder` bean, inject it into `TraceAspect`, and assert event counts and order in synchronous flows. If calls run via `@Async`/multiple threads, cross-thread event ordering is non-deterministic and requires synchronization/awaiting completion before asserting.

### 10.2. Avoid tests that hide production configuration bugs

Sometimes unit tests pass a mock `ValidationService` directly into `OrderApplicationService`'s constructor. That is great for testing orchestration, yet mocks **do not reflect Spring proxies**. Combine unit tests and integration tests to verify both business logic and advisor behavior.

A practical test should fail if someone "optimizes" by replacing the injected collaborator with `new` or moving the method back to a self-call without realizing AOP would be bypassed.

## 11. Applying in Spring Boot

With Spring Boot's AOP auto-configuration and matching dependencies, you usually do not need to write `@EnableAspectJAutoProxy` manually, though the refactoring pattern stays the same:

```java
@Service
public class OrderApplicationService {
    private final ValidationService validator;

    public OrderApplicationService(ValidationService validator) {
        this.validator = validator;
    }

    public String place(String id) {
        return validator.validate(id);
    }
}
```

```java
@Service
public class ValidationService {
    public String validate(String id) {
        return "validated:" + id;
    }
}
```

With the corresponding `@Aspect` class annotated with `@Component`, Spring Boot needs the matching AOP dependency to activate proxying. Gradle examples (choose by major version, using Boot dependency management):

```gradle
// Spring Boot 3.x
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

```gradle
// Spring Boot 4.x
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

These two blocks **are separate alternatives**, do not copy both at once. Having a Spring AOP starter does not create aspect beans automatically: `@Aspect` must be discovered by component scanning via `@Component` or registered via `@Bean`. Place classes under `@SpringBootApplication`'s scan package or import the appropriate configuration.

Spring Boot typically defaults to class proxies via `spring.aop.proxy-target-class=true`; if using interfaces and preferring JDK proxies, consider `spring.aop.proxy-target-class=false`. Results can also be affected by other proxy settings. Always verify the actual runtime proxy, especially when refactoring to final classes, Kotlin classes (final by default), or injecting exclusively via interfaces.

## 12. Refactoring workflow applicable to a real codebase

### Step 1 — Identify the call path missing advice

Diagram the call path **from caller to target** and mark whether each reference is a Spring bean/proxy or a manually created instance. Capture a reproducible case: calling through an external Spring bean produces advice, whereas calling internally does not.

### Step 2 — Identify the method and concern needing interception

Do not split every helper by default. Select the piece of work that genuinely needs a **Spring proxy boundary**: audit for a validation step, an independent transaction for a write, caching for a lookup, or a security policy on a public operation.

### Step 3 — Extract the method with a clear contract

Create a collaborator with a domain-meaningful name and a proxiable public method. Pass needed inputs as parameters; preserve output/exception contracts and avoid sharing mutable state casually.

### Step 4 — Register the collaborator in Spring

Use `@Service`/`@Component` inside scanned packages or `@Bean` in a loaded Spring configuration. Verify the context holds the expected instance and scope.

### Step 5 — Inject via constructor

Update the orchestrator to receive the dependency from Spring, call the collaborator reference, and never instantiate with `new`; avoid reverse dependencies that introduce cycles.

### Step 6 — Update pointcuts and AOP configuration

Adjust pointcuts to target the new method/type/bean/annotation location; ensure the aspect is a Spring bean and Spring AOP support is enabled in the right context.

### Step 7 — Run behavior and advice tests

Reproduce before and after using `AopUtils` and a recorder. Prove advice runs through the collaborator and does not fire unnecessarily on unrelated methods; verify transaction/security/caching/async semantics if used.

### Step 8 — Review performance and release

Refactoring may add a proxy hop, usually negligible compared to I/O; still, measure if the hot path is extremely sensitive. More importantly, **interception that was previously skipped now actually executes**, so logging, transaction, cache/remote call, or retry costs may change. Roll out with regression tests and observability to catch new side effects.

## 13. Final checklist

- [ ] Proved the old behavior was **self-invocation** (`this.method()` on target), not a missing aspect bean/pointcut/enablement config?
- [ ] Moved the method needing advice to a **collaborator Spring bean** with a clear responsibility?
- [ ] Collaborator is created by Spring (`@Component`/`@Service` + scan or `@Bean`); orchestrator does not use `new`?
- [ ] Collaborator reference is **constructor-injected**, without self-injection or `ApplicationContext.getBean(self)`?
- [ ] Entry method is public/non-final or on a compatible interface; JDK/CGLIB proxy type is appropriate?
- [ ] Aspect is a Spring bean; `@EnableAspectJAutoProxy`/Boot auto-config is enabled in the right context?
- [ ] Pointcut matches the new type/method/bean and does not intercept out-of-scope targets?
- [ ] Integration tests show advice runs **once in the right place** on the refactored call path?
- [ ] Business outputs/exceptions are compatible before and after; no unintended transaction/cache/security semantic shifts?
- [ ] No mutable request state added to singleton collaborators/aspects and no circular dependencies introduced?
- [ ] If the flow occurs at startup, the proxy is finalized rather than relying on calls from the target's own constructor or `@PostConstruct`?
- [ ] Checked all legacy entry points so no bypass path violates policy?

**Remember:** The most natural fix for self-invocation in **Spring AOP proxies** is usually **extracting the work needing advice into a collaborator Spring bean and calling it through a Spring-injected dependency**. Creating a separate class alone is not enough; you must establish a **real proxy boundary**. Refactoring should preserve business contracts, update pointcuts, and test new side effects once advice begins executing.

## Official Spring references

- [Spring Framework 6.2 — Proxying Mechanisms, self-invocation and refactoring guidance](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — Annotation-based Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)