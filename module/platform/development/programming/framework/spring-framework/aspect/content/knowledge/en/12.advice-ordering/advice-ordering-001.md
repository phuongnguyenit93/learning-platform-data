# Multiple Aspects Matching the Same Method in Spring AOP

## 1. The Problem and What You Need to Understand

A Spring service method can simultaneously match multiple pointcuts coming from **multiple `@Aspect` beans**. For example, when `OrderService.submit(..)` is called by a caller through a Spring proxy, the application may apply logging, timing, auditing, transactions, or custom validation through different advisors.

With **Spring AOP using @AspectJ syntax**, Spring builds an **interceptor/advisor chain** for each matching proxy invocation, rather than creating a separate copy of the target method for each aspect. A single target call can cause multiple pieces of advice to execute in a governed order.

Questions to resolve:

1. When two or more Spring `@Aspect` beans match the same method, **which advice is invoked first**?
2. Why can `@Order(10)` run **before entering** the target but **after exiting** the target compared to `@Order(20)`?
3. With `@Around`, what happens if an aspect does not call `proceed()`, throws its own error, catches an error, retries, or changes the return value?
4. If one aspect only has `@Before` while another uses `@AfterReturning` or `@AfterThrowing`, what outcome semantics must be distinguished?
5. How does ordering between **different aspects** differ from ordering **multiple advice methods of the same type within the same aspect**?
6. How do you verify this using a Spring `ApplicationContext`, rather than guessing from the order methods appear in a Java file?

This lesson focuses on **Spring Aspect/Spring AOP proxies**, combining multiple `@Aspect` beans, `@Order`/`Ordered`, the invocation chain, and testing. General AOP concepts are only mentioned when needed to explain Spring.

## 2. One Spring Method, Multiple Aspects, One Proxy Boundary

Suppose three aspects all have expressions matching:

```java
public String submit(String id) {
    return "submitted:" + id;
}
```

Conceptual diagram when the Spring AOP proxy receives an invocation:

```text
External caller
     |
     | service.submit("A")     (reference returned by the Spring container)
     v
Spring AOP proxy
     |
     +--> Aspect Outer / @Around / @Order(10)
     |      enter
     |         |
     |         +--> Aspect Gate / @Before / @Order(15)
     |                   |
     |                   +--> Aspect Inner / @Around / @Order(20)
     |                             enter
     |                               |
     |                               +--> target.submit("A")
     |                               |
     |                             exit
     |      exit
     v
Caller receives result or exception
```

**Points to distinguish:**

- `@Aspect` is a class that declares advice/pointcuts; **the aspect must be registered as a Spring bean** for Spring AOP to use it.
- Spring creates one **proxy** (a JDK dynamic proxy or CGLIB class proxy) for an eligible target bean and combines the applicable advisors. You should not assume each aspect creates a separate proxy in every application.
- A target method can be advised by multiple aspects, but `@Around` has the ability to prevent or repeat the target call; therefore, **the number of times the target body runs does not always equal the number of proxy entries**.
- `@Order` controls **aspect precedence in Spring**, not whether a pointcut matches more or fewer join points.
- Spring transaction/cache/security advisors can coexist with custom aspects, but a lesson on `@Order` for custom aspects does not automatically dictate the order of all infrastructure advisors.

**The right mental model:** an external call enters the Spring proxy, where Spring selects the applicable advisor chain. If the caller bypasses the proxy (`new` object, `this.inner()` on the target), having ten aspects match the method signature still does not create interception.

## 3. Default Order: Without @Order, Do Not Rely on Accidental Ordering

The Spring Framework documentation explicitly states: when **two pieces of advice in two different aspects** both want to run at a join point, if **no precedence is specified**, the execution order is **undefined**.

Do not infer order from:

- Alphabetical Java file names;
- Aspect class names;
- The order of `@Bean` factory methods;
- Typical component-scanning order;
- The order of methods within an `@Aspect` class;
- The idea that a "logging" or "security" aspect sounds like it should come first;
- The result of a single local run without assertions or regression tests.

If behavior **depends on ordering**, you must use explicit precedence and then verify it with tests on the **actual Spring version, proxy mode, and advisor configuration**.

Some tracing/logging may not require a fixed order; however, masking secrets before logging, authorization before business effects, and transaction boundaries with auditing and metrics usually require careful ordering.

## 4. @Order and Ordered in Spring AOP

In Spring, there are two common ways to set precedence:

**Annotation on the aspect class:**

```java
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterAspect {
    // Advice in this aspect has precedence 10.
}
```

**Or implementing `Ordered`:**

```java
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.Ordered;

@Aspect
public class OuterAspect implements Ordered {
    @Override
    public int getOrder() {
        return 10;
    }
}
```

These two snippets **are two separate options**, not two classes with the same name defined in the same project. You still need Spring bean registration (`@Component` or `@Bean`) and actual advice to affect runtime behavior.

**Spring's rule: a lower order number means higher precedence.** For example, `@Order(10)` is higher than `@Order(20)`; `Ordered.HIGHEST_PRECEDENCE` (extremely small value) and `Ordered.LOWEST_PRECEDENCE` (extremely large value) are two reference bounds.

| Precedence | Order on the way in | Order on the way out |
| --- | --- | --- |
| Aspect A, `@Order(10)` | Enters **before** aspect B | Exits **after** aspect B |
| Aspect B, `@Order(20)` | Enters **after** aspect A | Exits **before** aspect A |

Think in terms of **nested parentheses**:

```text
A.enter
    B.enter
        target
    B.exit
A.exit
```

Do not use a simplistic statement like "lower order means the aspect always runs first" to describe both enter and exit. That is only true **on the way in**; the way out has the reversed order.

### 4.1. @Order on the Aspect Class, Not "Order of Every Method"

In Spring `@AspectJ`, placing `@Order` on the **aspect type** is the intuitive way to define precedence between aspects. If a single aspect has two `@Before` methods matching the same join point, adding `@Order` on the class **does not determine which of those two advice methods runs first**.

Do not slap `@Order(1)` onto each advice method assuming Spring will guarantee it becomes a global order as desired. Use **two separate aspect classes**, a single advice method with explicit sequential logic, or an appropriate orchestration pointcut.

### 4.2. Two Aspects with the Same Order Value

If A and B both have `@Order(10)`, do not assume Spring will consistently process A before B across all environments. If the order is business-critical, **assign intentionally distinct values** and write a regression test instead of relying on registration order.

### 4.3. Ordered Can Come from the Bean Instance

`Ordered.getOrder()` allows the order value to live on the aspect bean instance. When multiple Spring beans and auto-proxy behavior are involved, make sure Spring actually obtains the intended value from the aspect bean; if using dynamic configuration, test at runtime rather than only reading class annotations.

Do not abuse dynamic ordering to change business policies per request: advisor chain precedence is a proxy infrastructure property, not per-invocation data context to mutate arbitrarily.

## 5. @Around Shows the Nested Chain Most Clearly

When A (`@Order(10)`) and B (`@Order(20)`) both use `@Around` on the same Spring target method:

```java
@Around("execution(* com.example.orders.OrderService.submit(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    before();
    try {
        Object value = pjp.proceed();
        afterSuccess();
        return value;
    } catch (Throwable error) {
        afterFailure(error);
        throw error;
    } finally {
        cleanup();
    }
}
```

This snippet is **illustrative**, not a standalone Java file (missing class, imports, helper methods). It shows that an aspect can run **both on the way in and on the way out**.

The result with two aspects can usually be described as:

```text
A.before        (Order 10)
B.before        (Order 20)
target.submit
B.afterSuccess  (Order 20)
B.cleanup       (Order 20)
A.afterSuccess  (Order 10)
A.cleanup       (Order 10)
```

If the target throws an exception:

```text
A.before
B.before
target.submit -> throw
B.afterFailure
B.cleanup
A.afterFailure
A.cleanup
Caller receives exception
```

This is a **logical diagram** when both `@Around` advice methods always call `proceed()` exactly once and rethrow the original exception. The surest way to learn and verify this is to run the actual Spring AOP demo in section 7.

### 5.1. There Is No Guarantee the Target Always Runs

`@Around` has the authority to **not call `proceed()`**, or to call it multiple times. If the outermost aspect short-circuits, advisors behind it and the target **may not run**, even when their pointcuts fully match the method.

Illustrative example not to use without an explicit contract:

```java
@Around("execution(* com.example.orders.OrderService.submit(..))")
public Object unsafeSkip(ProceedingJoinPoint pjp) {
    return "ok"; // Never calls the target or downstream interceptors!
}
```

An aspect with higher precedence does not merely "log earlier": it can decide whether downstream advice enters the chain at all. This directly relates to the ordering of security, transaction, retry, and cache interceptors in Spring.

## 6. Two Questions to Keep Separate: Matching and Ordering

An aspect only participates in an invocation if:

1. It is a **Spring-managed `@Aspect` bean** with advice recognized by the infrastructure;
2. Its pointcut matches the method execution/bean in the Spring context;
3. The caller goes through the Spring proxy and the method is within the interception scope of JDK/CGLIB;
4. Higher-precedence interceptors **allow the chain to continue** to it;
5. If the advice has dynamic conditions (`args`, `@annotation`, `@target`, `@within`, etc.), those conditions hold for that invocation.

**`@Order` only resolves precedence after the advisors have already been selected.** Changing `@Order(5)` to `@Order(50)` does not make an `@AuditAction` annotation suddenly appear on the target method.

### An Expression Matching Both Service Methods

```java
@Around("execution(public * com.example.chain.TaskService.*(..))")
public Object aroundEveryPublicTaskMethod(
        ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

If the target has `run()` and `fail()`, both can be advised when a caller invokes them through the Spring proxy. The order between aspects is a separate question, governed by `@Order`/`Ordered`.

If a pointcut only selects `run()`, the advice does not run when the caller invokes `fail()`, regardless of `@Order`. Therefore, when logs are missing, check **matching first** before investigating ordering.

## 7. Runnable Spring Framework Demo: Three Aspects Matching Two Methods

The demo uses Java 17+, Spring Framework **6.2.19**, AspectJ Weaver **1.9.25.1**, and Gradle. This is plain Spring Framework without Spring Boot auto-configuration, so that `@Order` precedence and the `@EnableAspectJAutoProxy` requirement are clearly visible.

Components:

- `OuterAspect`: `@Order(10)`, `@Around`, enters first and exits last.
- `GateAspect`: `@Order(15)`, `@Before`, runs after `OuterAspect.enter` but before `InnerAspect.enter`.
- `InnerAspect`: `@Order(20)`, `@Around`, wraps the target more closely than `OuterAspect`.
- `TaskService`: one method that succeeds and one method that throws an exception to observe the exit path.
- `Main`: retrieves the Spring proxy from the context, calls both methods, and prints deterministic stdout.

### 7.1. Directory Tree

```text
spring-multiple-aspects-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/chain/
    ├── TaskService.java
    ├── OuterAspect.java
    ├── GateAspect.java
    ├── InnerAspect.java
    ├── AppConfig.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-multiple-aspects-demo'
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
    mainClass = 'com.example.chain.Main'
}
```

Spring Framework 6.x supports Java 17+; `spring-context` provides `ApplicationContext`/`@Configuration`; `spring-aop` and `aspectjweaver` serve Spring proxy `@AspectJ` configuration. Having `aspectjweaver` on the classpath for parsing pointcuts **does not mean** AspectJ load-time weaving is enabled.

### 7.2. Spring Target Bean

**`TaskService.java`**

```java
package com.example.chain;

public class TaskService {
    public String run(String id) {
        System.out.println("target:run");
        return "ok:" + id;
    }

    public String fail() {
        System.out.println("target:fail");
        throw new IllegalStateException("boom");
    }
}
```

Both the class and methods are public/non-final with no interface, so a class-based proxy can intercept them. The two methods do not call each other so self-invocation is not mixed up with aspect ordering.

### 7.3. Aspect Order 10: Outermost Wrapper

**`OuterAspect.java`**

```java
package com.example.chain;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterAspect {
    @Around("execution(public * com.example.chain.TaskService.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String name = pjp.getSignature().getName();
        System.out.println("outer:enter:" + name);
        try {
            Object result = pjp.proceed();
            System.out.println("outer:return:" + name);
            return result;
        } catch (Throwable error) {
            System.out.println(
                    "outer:throw:" + name + ":"
                    + error.getClass().getSimpleName()
            );
            throw error;
        } finally {
            System.out.println("outer:finally:" + name);
        }
    }
}
```

Note:

- `@Order(10)` has higher precedence than `@Order(15)` and `@Order(20)`.
- `pjp.proceed()` transfers control down to the remaining advisors, and then to the target.
- `throw error;` preserves the exceptional outcome of the downstream invocation.
- `finally` runs on both normal return and throw.
- The advice does not invent a fallback or retry. If you try returning a fake value in `catch`, caller output and downstream behavior can change.

### 7.4. Aspect Order 15: A @Before

**`GateAspect.java`**

```java
package com.example.chain;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;

@Aspect
@Order(15)
public class GateAspect {
    @Before("execution(public * com.example.chain.TaskService.*(..))")
    public void before(JoinPoint jp) {
        System.out.println("gate:before:" + jp.getSignature().getName());
    }
}
```

`@Before` here is used to **observe entry**, not to return a result itself. It runs between `OuterAspect.enter` and `InnerAspect.enter` when those advisors participate in the chain as configured.

If `@Before` throws an exception itself, subsequent interceptors and the target may not be called. Do not use `@Before` to turn a valid error into a fallback return; if authorization is needed, use Spring Security infrastructure with properly tested precedence.

### 7.5. Aspect Order 20: Wrapper Closest to the Target

**`InnerAspect.java`**

```java
package com.example.chain;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(20)
public class InnerAspect {
    @Around("execution(public * com.example.chain.TaskService.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String name = pjp.getSignature().getName();
        System.out.println("inner:enter:" + name);
        try {
            Object result = pjp.proceed();
            System.out.println("inner:return:" + name);
            return result;
        } catch (Throwable error) {
            System.out.println(
                    "inner:throw:" + name + ":"
                    + error.getClass().getSimpleName()
            );
            throw error;
        } finally {
            System.out.println("inner:finally:" + name);
        }
    }
}
```

`InnerAspect` has the lowest precedence of the three aspects yet still **wraps the target**: `inner:enter` before `target`, `inner:return` or `inner:throw` after target, then `inner:finally`. It completes its exit phase **before** `OuterAspect`.

### 7.6. Spring Java Configuration

**`AppConfig.java`**

```java
package com.example.chain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    TaskService taskService() {
        return new TaskService();
    }

    @Bean
    OuterAspect outerAspect() {
        return new OuterAspect();
    }

    @Bean
    GateAspect gateAspect() {
        return new GateAspect();
    }

    @Bean
    InnerAspect innerAspect() {
        return new InnerAspect();
    }
}
```

`@Aspect` **does not automatically register a Spring bean**. Here, the three aspect beans are declared with `@Bean`, without needing `@Component` or component scanning. `@EnableAspectJAutoProxy(proxyTargetClass=true)` enables Spring @AspectJ auto-proxying and allows retrieving `TaskService` by its concrete type in the demo.

**You do not need three proxy objects** to run three aspects. Spring can combine the matching advisors within the AOP proxy of the `taskService` bean.

### 7.7. Main and Run Command

**`Main.java`**

```java
package com.example.chain;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService service = context.getBean(TaskService.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("case=normal");
            System.out.println("result=" + service.run("A"));

            System.out.println("case=exception");
            try {
                service.fail();
            } catch (IllegalStateException error) {
                System.out.println("caught=" + error.getMessage());
            }
        }
    }
}
```

In the project root directory, with Java 17+ and Gradle installed:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper: `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

**Stdout from the `System.out` statements in the project** in exact order (excluding environmental JVM/Spring/Gradle logging):

```text
proxy=true
case=normal
outer:enter:run
gate:before:run
inner:enter:run
target:run
inner:return:run
inner:finally:run
outer:return:run
outer:finally:run
result=ok:A
case=exception
outer:enter:fail
gate:before:fail
inner:enter:fail
target:fail
inner:throw:fail:IllegalStateException
inner:finally:fail
outer:throw:fail:IllegalStateException
outer:finally:fail
caught=boom
```

### 7.8. Line-by-Line Explanation of Key Output

**Normal case:**

1. `outer:enter:run`: the `@Order(10)` outer aspect enters first.
2. `gate:before:run`: `@Order(15)` is called as the chain progresses inward.
3. `inner:enter:run`: the `@Order(20)` aspect enters later, right before the target.
4. `target:run`: **the target body runs exactly once**.
5. `inner:return:run` and `inner:finally:run`: the innermost wrapper completes its exit phase first.
6. `outer:return:run` and `outer:finally:run`: the outermost wrapper completes afterward.
7. `result=ok:A`: the caller receives the original value returned by the target, unaltered by the aspects.

**Exception case:**

1. The entry chain preserves the order `outer → gate → inner → target`.
2. `target:fail` throws `IllegalStateException("boom")`.
3. `InnerAspect` receives the exception first, prints `inner:throw` and `inner:finally`, and rethrows it.
4. `OuterAspect` receives the same exceptional flow, prints `outer:throw` and `outer:finally`, and rethrows it.
5. The caller catches the exact `IllegalStateException` and prints `caught=boom`.

**Key distinction:** Each `@Around` prints **two or three lines** for a single invocation, but those **are not multiple target calls**. The same exception travels through two layers so it is observed twice; there is no evidence the target ran twice.

### 7.9. Why Not Use Two @Before Aspects Without @Order?

If both aspects had `@Before` and no `@Order`, the application could still print two logs before the target, but **the order of the two logs would not be a contract**. The demo intentionally uses **three distinct `@Order` values** so stdout has a clear, deterministic reason.

## 8. When Two Advice Methods in the Same @Aspect Match the Same Method

This is a **different** question from ordering across multiple aspect classes.

Illustrative example:

```java
@Aspect
public class TwoBeforeAdvices {
    @Before("execution(* com.example.chain.TaskService.run(..))")
    public void first() {
        System.out.println("first");
    }

    @Before("execution(* com.example.chain.TaskService.run(..))")
    public void second() {
        System.out.println("second");
    }
}
```

Inside a single `@Aspect` class, **two advice methods of the same kind (`@Before`)** matching the same join point **have no guaranteed order** merely because `first` appears above `second` in the Java source. Java reflection does not provide a stable declaration order that Spring can rely on as a contract.

**Solutions when guaranteed order is required:**

- Combine the logic into **a single `@Before` method** with explicit statement order;
- Or split them into **two `@Aspect` classes**, apply different `@Order` values, and test;
- If it is a single flow with complex entry/exit behavior, consider one `@Around` method with `try/finally` under a clear contract.

The snippet above is **illustrative** and is not added to the demo project in section 7 because it would alter stdout.

### 8.1. Different Advice Types Within the Same Aspect

Spring Framework 6.2 describes precedence by **advice type** within the same `@Aspect`, from highest to lowest:

```text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
```

However, `@After` has **after-finally** semantics: in practice it is invoked **after `@AfterReturning` or `@AfterThrowing`** in the same aspect when the join point finishes. Do not turn the type precedence table into a simple left-to-right linear logging order; consider **the entry/exit directions of the interceptor chain**.

Two advice methods **of the same type within the same aspect** still have no source-order guarantee. This is an important Spring-specific detail when refactoring multiple handlers into a shared `@Aspect`.

### 8.2. Advice in the Same @Aspect Can Have Different Pointcuts

An `@Aspect` containing multiple `@Before` methods does not mean **all** of them run for every method. Each expression must be evaluated individually:

```java
@Before("execution(* com.example.chain.TaskService.run(..))")
public void onRun() {}

@Before("execution(* com.example.chain.TaskService.fail(..))")
public void onFail() {}
```

If the caller invokes `run()`, the advice targeting only `fail()` does not match. Do not mistake a missing event for an ordering issue when the pointcut never selected the join point.

## 9. Multiple @AfterReturning and @AfterThrowing: Distinguishing Normal vs. Exception

When different aspects use different advice types, the **outcome** itself determines which advice is eligible to be invoked:

| Advice | Normal return of target execution | Exceptional exit of target execution |
| --- | --- | --- |
| `@Before` | Can run before target | Can run before target |
| `@Around` | Can run before and after; can alter outcome | Can catch/propagate/transform error |
| `@AfterReturning` | Runs if pointcut and return binding match | Does not run when join point exits via exception |
| `@AfterThrowing` | Does not run on normal return | Runs if exception and binding match |
| `@After` | Has finally semantics when execution exits | Has finally semantics when execution exits |

**Do not assume "high aspect priority" makes `@AfterReturning` run when the target throws an error.** Order does not change the event an advice type listens for.

### 9.1. Advice Signatures with returning/throwing Narrow the Match Set

```java
@AfterReturning(
    pointcut = "execution(* com.example.chain.TaskService.*(..))",
    returning = "text",
    argNames = "text"
)
public void afterText(String text) {
    // ...
}
```

```java
@AfterThrowing(
    pointcut = "execution(* com.example.chain.TaskService.*(..))",
    throwing = "problem",
    argNames = "problem"
)
public void afterIllegalArgument(IllegalArgumentException problem) {
    // ...
}
```

These two illustrative snippets share the same `execution` scope but have different **type constraints**. `afterText` requires a normal return compatible with `String`; `afterIllegalArgument` only runs for exceptions of type `IllegalArgumentException` or subtypes and **does not** run for `IllegalStateException` in the demo. Not every case of "advice did not run" is related to `@Order`.

### 9.2. @AfterThrowing Is Not a Catch Block for Other Advice

Spring docs emphasize that distinct advice types of an aspect conceptually apply to the **target join point**; `@AfterThrowing` should not be understood as a global catch handler for exceptions thrown by **another `@After`/`@AfterReturning` method in the same aspect**.

If different advisors throw or transform errors, propagation also depends on interceptor position in the chain. Do not automatically "fix" this by catching `Throwable` in an outer aspect and returning `null`, because that can alter transaction/security semantics and swallow the original error.

## 10. Relationship with Spring Transaction, Security, Cache, and Async

Spring has many infrastructure interceptors beyond custom `@Aspect` beans. When they act together on a method, inspect the **actual advisor chain** rather than equating "business aspects order" with "every framework component will always obey these three example order numbers."

### 10.1. @Transactional and Ordering with Custom Aspects

A method:

```java
@Transactional
public void save(Order order) {
    // ...
}
```

This is **illustrative code**; `Order` is a domain type that needs to be defined, and transaction management must be enabled separately. Suppose a custom `@Around` logs "success" when `pjp.proceed()` returns normally:

- If the aspect **wraps outside the transaction advisor**, its `proceed()` can encompass the transaction interception (commit/rollback) as well.
- If the aspect **sits inside the transaction advisor**, it may see the target return normally while the transaction commit happens after it exits.
- Propagation, rollback rules, transaction manager, and advisor ordering can change the outcome.
- **Do not use stdout `target:return` as proof that the DB committed.**

If you need a post-commit side effect, use Spring transaction synchronization or `@TransactionalEventListener(phase=AFTER_COMMIT)` with proper configuration. Do not arbitrarily change `@Order` to "guarantee commit" without checking the actual transaction advisor order.

### 10.2. Method Security and Short-Circuiting Aspects

If a high-precedence custom `@Around` **does not call `proceed()`**, a **downstream** method security interceptor may not run. Depending on order, this could unintentionally bypass `@PreAuthorize` or another policy. Security-sensitive paths need end-to-end tests for access denied, including cache, fallback, and short-circuit branches.

Do not assign an arbitrary `@Order` number to a custom security aspect and conclude it protects the entire application. Spring Security has its own configuration and advisors; check actual method security activation and proxy semantics.

### 10.3. Cache Advisors

`@Cacheable` can return a cached value without invoking the target method. If a custom metrics aspect sits outside the cache advisor, it may see a **proxy invocation** even when the target did not run; if it sits inside, it may not be called when a cache hit short-circuits. This is why aspect log counts can **legitimately** differ from target body execution counts.

If a custom `@Around` implements its own caching or fallback, be careful not to cache a fake "success" value produced from a backend error if the contract forbids it.

### 10.4. @Async and Future/Publisher

`@Async`, `CompletableFuture`, and reactive `Mono`/`Flux` complicate execution timing and threads. Observed log order across threads can interleave, even when advisor precedence on **a single invocation chain** is clear. `@Around` may see the **future/publisher wrapper return** before the computation or subscription completes.

Do not use a synchronous example like `TaskService.run()` to claim global log ordering across multiple threads or final success of asynchronous tasks.

## 11. Self-Invocation and Spring Proxy Limitations

`@Order` only matters when Spring AOP actually intercepts the invocation.

### 11.1. Self-Invocation Still Bypasses the Proxy

```java
public class TaskService {
    public String outer() {
        return this.run("A"); // internal call on target
    }

    public String run(String id) {
        return "ok:" + id;
    }
}
```

If the target received the `outer()` call through the proxy, the internal `this.run()` call inside the target **does not go back through the proxy**. Therefore, advice targeting `run(..)` does not run automatically, even if every aspect has an explicit `@Order`. To apply advice on `run`, call it through the Spring proxy from another bean or refactor the intercepted piece into a collaborator bean.

### 11.2. JDK Proxy and CGLIB

- With a **JDK dynamic proxy**, callers use interface methods exposed by the proxy; the implementation class can be final if an appropriate interface proxy is chosen.
- With **CGLIB**, the class must be subclassable and advised methods must be overridable; `final` classes or methods impose limitations.
- `@EnableAspectJAutoProxy(proxyTargetClass=true)` selects a class proxy for the demo; it **does not fix self-invocation**.
- `private` methods are not normal interceptable entries for a Spring AOP proxy.
- Constructors, field read/write, and AspectJ compiler weaving join points are not automatically supported by Spring proxy AOP.
- Spring `@AspectJ` uses AspectJ annotation syntax, but runtime interception remains a Spring proxy.

### 11.3. Do Not Use `new` on the Target When Testing

```java
TaskService service = new TaskService();
service.run("A");
```

This is a plain Java object, not a Spring AOP proxy; no advice runs. When testing Spring aspect ordering, always obtain the target bean from `ApplicationContext` or dependency injection and call through the proxy.

## 12. Common Diagnostic Pitfalls

| Symptom | Common Misconception | Explanation in Spring |
| --- | --- | --- |
| Two aspects both have `@Before` | "Follows source declaration order" | No guarantee when no precedence is set. |
| `@Order(10)` logs last | "Order is inverted so config is wrong" | On the **way out**, higher-precedence aspects run **after** lower-precedence ones. |
| Three log entries but one target log | "Target ran three times" | One target execution can pass through multiple advice methods; logs are not target call counts. |
| Aspect A prints nothing | "Spring ignored @Order" | Pointcut may not match, aspect is not a bean, caller bypassed proxy, or outer aspect short-circuited. |
| `@AfterReturning` does not run on exception | "Advice order is too low" | There is no normal return; use `@AfterThrowing` for exceptional exits. |
| Two `@Before` methods in the same aspect swap order randomly | "Need to rename Java methods" | Same advice type has no source-order guarantee; split aspects or merge logic. |
| Cache hit has no target log | "Spring broke target/aspect" | Cache interceptor can short-circuit; check advisor precedence. |
| Outer `@Around` returns null on error | "Logging still succeeded" | May have swallowed exception, altering contract and transaction/security behavior. |
| Aspect prints success before DB commit | "DB transaction surely succeeded" | Timing depends on transaction advisor position; success log does not guarantee commit. |
| One request produces multiple log lines | "Multiple HTTP requests arrived" | One invocation passing through multiple aspects produces multiple events. |
| Bean is a proxy but method is not advised | "AOP proxy is broken" | Check pointcut, final/private, interface visibility, and self-calls. |
| Aspects share the same order and work locally | "Order is guaranteed" | Equal precedence is not a contract across all Spring setups. |

## 13. Debugging a Spring AOP Chain When Order Differs from Expectations

### 13.1. Confirm the Proxy Type

```java
TaskService bean = context.getBean(TaskService.class);
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

This illustrative snippet uses the demo's context and imports `org.springframework.aop.support.AopUtils`. In the demo, both are `true` because `proxyTargetClass=true` and the method pointcut matches.

**The existence of a proxy does not prove a specific advice matches.** Use an event recorder or logs containing aspect/method names to confirm each advice executes.

### 13.2. Inspect Order Values at Runtime

You can log or inspect `@Order` on aspect classes or `Ordered.getOrder()` when aspects implement the interface. When infrastructure adds multiple advisors, to view the advisor list you can usually inspect the Spring `Advised` proxy:

```java
import org.springframework.aop.framework.Advised;

Object bean = context.getBean("taskService");
if (bean instanceof Advised advised) {
    for (var advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

This is an **illustrative diagnostic snippet**; do not add it to `Main` if you want to preserve the stdout in section 7.7. The advisor list helps investigate the proxy chain and infrastructure, but does not by itself prove all dynamic pointcut conditions match a given invocation. An advisor may match a method by static filter and require runtime checks for advice to run. Do not mutate the advisor list in production just to test ordering.

### 13.3. Use an Event Recorder Instead of Interleaved Multithreaded Logs

A recorder for the synchronous demo:

```java
public final class EventRecorder {
    private final java.util.List<String> events =
            new java.util.concurrent.CopyOnWriteArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public java.util.List<String> snapshot() {
        return java.util.List.copyOf(events);
    }
}
```

This is **a standalone illustrative Java class**; if wired into the demo project, register the recorder as a Spring bean and inject it into the aspects. Using a recorder makes testing order more accurate than reading console output from multiple sources.

In an async/multithreaded environment, each invocation should carry its own **correlation ID**; `CopyOnWriteArrayList` is thread-safe for writes, but does not turn event ordering across concurrent invocations into a globally guaranteed order.

### 13.4. Check Pointcut Matching

Review `execution(...)`, `within(...)`, `@annotation(...)`, and `bean(...)` expressions; note that `bean(...)` is a Spring AOP extension and not all of the AspectJ language is supported. For pointcuts relying on annotations/args, the invoked method must actually carry the corresponding metadata/arguments.

If an aspect is not registered by Spring, adding `@Aspect` is not enough: use `@Component` with component scanning on the right package, or `@Bean` in configuration. With Spring Framework Java config, enable `@EnableAspectJAutoProxy` on the right context and include `aspectjweaver`.

## 14. Integration Testing Workflow for Multiple Aspects

### 14.1. Assertions to Include

A good integration test should prove:

1. Spring returns a **proxy** for the target.
2. All three aspects are registered by Spring and their pointcuts actually match.
3. The normal return path has the order `outer enter → gate before → inner enter → target → inner return/finally → outer return/finally`.
4. The exceptional exit path has the order `outer enter → gate before → inner enter → target throw → inner catch/finally → outer catch/finally`.
5. The caller sees the original result/exception when advice is not permitted to alter the outcome.
6. When `@Order` is changed intentionally, the expected order changes per contract.
7. Non-proxy calls or self-invocations do not trigger extra interception.
8. Aspects with non-matching pointcuts do not run unexpectedly.
9. Tests run on the same Spring Framework/Boot version and proxy mode as production.

### 14.2. Comparing Against Sample Output

In the demo code, `Main` prints detailed stdout. A test can replace `System.out` in the advice with a recorder to assert the list of events. **Do not rely on a substring like "outer" or total log line count**, because both `@Around` aspects emit multiple exit events.

Example expectation for a normal call:

```java
List<String> expected = List.of(
    "outer:enter:run",
    "gate:before:run",
    "inner:enter:run",
    "target:run",
    "inner:return:run",
    "inner:finally:run",
    "outer:return:run",
    "outer:finally:run"
);
```

This snippet **illustrates assertion data**; it requires importing `java.util.List`, a recorder, and a target method using the recorder instead of `System.out`. Do not copy it blindly into the running `Main` without using the `expected` variable and binding it to actual events.

### 14.3. Testing Exception Identity When Required by Contract

With both `OuterAspect` and `InnerAspect` executing `throw error;`, an exception from the target can preserve its identity across the chain when no other interceptor wraps it. A separate Spring test fixture can have the target throw a pre-created `IllegalStateException` and assert the caller catches the exact same object (`==`), while also asserting the event order.

Remember, however: in production, JDK interface proxies, transactions, or other library interceptors may wrap or map exceptions per their contracts; tests must reflect reality rather than claiming every Spring AOP scenario preserves object identity regardless of chain.

### 14.4. Testing with Transactions or Method Security

If a method has `@Transactional` or `@PreAuthorize`, add integration tests with real activation configurations rather than only loading `@EnableAspectJAutoProxy`. Test both success/failure, rollback/commit, unauthorized callers, cache hits, and short-circuits. Observe actual advisor ordering rather than extrapolating from 10, 15, and 20 in the pure AOP example.

## 15. Spring Boot and Coordinating Multiple Aspects

In Spring Boot, when the appropriate AOP starter/auto-configuration is present, you usually do not need to declare `@EnableAspectJAutoProxy` manually. However:

- Each `@Aspect` class containing advice must be a **Spring bean** (typically via `@Component` or `@Bean`).
- Use `@Order` on aspect classes when precedence between multiple aspects is needed.
- Keep pointcuts narrow enough so you do not accidentally proxy infrastructure beans or add system-wide overhead.
- `spring.aop.proxy-target-class` configuration can affect JDK vs. CGLIB proxies, especially with final methods or interface injection.
- Transaction, caching, async, and method security have their own infrastructure, activation, and advisor precedence; do not assume a custom aspect will always wrap "outside" or sit "inside" them simply by picking an arbitrary order value.
- Under concurrent requests, event ordering across **different invocations** must not be inferred from advisor ordering within **a single invocation**.

Gradle dependency choices by Boot major version and dependency management (the two lines are separate options):

```gradle
// Spring Boot 3.x
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

```gradle
// Spring Boot 4.x
implementation 'org.springframework.boot:spring-boot-starter-aspectj'
```

Do not add both simultaneously without a specific dependency design. When Boot provides a BOM, let Boot select compatible Spring module versions instead of mixing `6.2.19` with incompatible versions.

### Using @Order vs. @Priority

For Spring AOP aspects, Spring documentation specifies `@Order` or `Ordered` for precedence. Do not confuse it with Java/Jakarta `@Priority` without checking how the specific Spring infrastructure reads the annotation. When testing, the most reliable proof remains **observing the actual advisor chain and event order**.

## 16. Pre-Production Review Checklist

- [ ] Are there genuinely **multiple Spring `@Aspect` beans** whose advice matches the same target method?
- [ ] Is the target method called **through the Spring proxy**, not via `new` or self-invocation?
- [ ] Is each aspect registered as a bean via `@Component`/`@Bean`, with Spring AOP @AspectJ support enabled in the right context?
- [ ] Do pointcut expressions target the right package/type/method without matching too broadly?
- [ ] If order matters, do aspects have distinct `@Order` values or explicit `Ordered` implementations?
- [ ] Is it understood that **lower number means higher precedence**—entering first but exiting last when using `@Around` wrappers?
- [ ] Is ordering not inferred from source declaration order, bean registration order, or class names?
- [ ] Are two advice methods of the same type within the same aspect not assumed to have a fixed order?
- [ ] Do downstream `@Around` advice methods call `proceed()` the exact contracted number of times, without unintended short-circuiting or retries?
- [ ] Does `@AfterReturning` only observe normal returns, and `@AfterThrowing` only observe matching exceptional exits?
- [ ] When advice throws errors or transforms return values, have semantics been tested with transaction/security/cache advisors?
- [ ] Has actual infrastructure interceptor precedence been inspected rather than mechanically applying the 10/15/20 rule?
- [ ] For JDK/CGLIB proxies, is the method entry exposed/overridable, with compatible class finality and visibility?
- [ ] Does each invocation have event correlation to avoid confusing concurrency interleaving with precedence?
- [ ] Do integration tests cover both returns and exceptions, event ordering, and return/throw contracts?
- [ ] Is the number of advice executions not mistaken for the number of times target business logic executed?

**Key takeaway:** In **Spring AOP**, multiple aspects matching the same method are placed by Spring into **a single proxy invocation chain**. When you need to control ordering between aspects, **a lower `@Order` number has higher precedence**: it runs earlier on the way into the target and **later on the way out**. That ordering does not make pointcuts match more broadly, does not force `@Around` to call `proceed()`, does not solve self-invocation, and does not change normal vs. exception outcome semantics. All ordering assumptions must be verified against the **actual Spring proxy and advisors**.

## Official References

- [Spring Framework 6.2 — Declaring Advice: Advice Ordering and Multiple Advice at the Same Join Point](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Declaring Pointcuts](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 — Proxying Mechanisms, JDK/CGLIB, and Self-Invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Schema-based AOP Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html)
- [Spring Framework 6.2 — Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
