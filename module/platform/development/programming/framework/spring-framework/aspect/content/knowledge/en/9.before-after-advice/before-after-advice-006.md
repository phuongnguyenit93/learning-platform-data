# Choosing the Least Powerful Advice That Meets Requirements in Spring AOP

## 1. Design Principle

In Spring AOP, an aspect can attach behavior to **method executions of Spring beans** using different advice types: `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, and `@Around`.

**The design rule recommended by Spring Framework: choose the least powerful advice type that still satisfies the requirement.** For example, if you only need to log before a method runs, use `@Before` rather than using `@Around` to call `proceed()` manually. If you only need to record a successful return value, use `@AfterReturning` rather than writing a wrapper around the entire call.

Why? The greater an advice's power to intervene, the greater the chance of introducing bugs:

- Forgetting `proceed()`, causing the business method not to run.
- Calling `proceed()` multiple times, causing duplicate data writes or event emissions.
- Returning the wrong type or swallowing exceptions, breaking the service contract.
- Overwriting the method's result or causing surprises with transactions/caching.
- Using one advice for too many concerns, making ordering hard to manage and easily violating single responsibility.

However, **"least powerful" is not a strict linear ranking** across the five annotations. Each corresponds to the **timing and data** it needs to observe. The choice depends first on the requirement: before execution, after success, on exception, on completion regardless of outcome, or needing active control over execution.

**Lesson scope:** choosing the right advice in **Spring Framework AOP**, where Spring beans are wrapped with JDK/CGLIB proxies and advice runs when a method call passes through the proxy. It does not revisit standalone AspectJ weaving theory.

## 2. Advice Selection Decision Table

| Requirement | Preferred Advice | Corresponding Intervention Power | What to Avoid |
| --- | --- | --- | --- |
| Write audit/logs before calling a service method | `@Before` | Runs before, observes method/arguments; does not control `proceed()` | Do not use `@Around` just to print a line before the method |
| Validate input and **reject by throwing an error** before processing | `@Before` can suffice | Can throw an exception, preventing the method from continuing | Do not think `@Before` can never alter execution flow |
| Record metrics when a method **returns normally** | `@AfterReturning` | Receives return status and observes after success | Do not expect it to run when the method throws an exception |
| Log the actual returned value | `@AfterReturning(returning = "...")` | Binds the return value by type | Do not try to return another reference from advice to replace the result |
| Record metrics/errors when target **throws an exception** | `@AfterThrowing` | Observes the exception thrown by the target | Do not treat it as a `catch` block that swallows the target's error |
| Release resources / update state when a method finishes in any way | `@After` | `finally`-like behavior at the join point | Do not use when you only want to run after success |
| Measure duration with a start variable and end variable **within the same call** | `@Around` is justified | Wraps before and after; can hold per-invocation safe local state | Must call `proceed()`, usually paired with `finally` |
| Return a cached result **without calling the target** | `@Around`, or better yet Spring's caching infrastructure if appropriate | Can skip the target or replace the result | Do not hand-roll caching unless standard infrastructure falls short |
| Modify arguments/return value, perform controlled retries, or short-circuit | `@Around` if truly required | Strongest intervention in method invocation | Do not overlook idempotency, exceptions, and transactions |
| Standard transaction/caching/security behavior already supported by the framework | Prefer `@Transactional`/`@Cacheable`/appropriate built-in mechanism | Let Spring manage specialized advisors | Do not re-implement a transaction manager or cache using `@Around` |

A quick decision question:

> **Do you need to decide yourself when the original method is called, how many times, with what arguments, and what it returns?** If **no**, prefer a more specific advice (`@Before`, `@AfterReturning`, `@AfterThrowing`, or `@After`). If **yes**, `@Around` may be necessary, but you must be able to explain why a narrower kind cannot meet the need.

## 3. Understanding the Five Advice Types in Spring Accurately

### 3.1. `@Before`: Only Processing Before the Method

~~~java
@Before("execution(* demo.OrderService.begin(..))")
public void beforeBegin() {
    System.out.println("BEFORE: begin");
}
~~~

This advice runs **before** a method execution matching the pointcut on a Spring proxy. Use it for audit markers, tracing context, observing method names, or checking preconditions that may throw an exception to reject the call.

Important rules:

- Has no `ProceedingJoinPoint` or authority to call `proceed()` itself.
- If `@Before` completes normally, Spring AOP continues the call to the next advice/target.
- **If `@Before` throws an exception**, the target method may not run; therefore this type is not "completely unable to alter behavior." Use it for intentional validation, and do not let logging accidentally throw errors.
- To read arguments, you can accept `JoinPoint` as the first parameter or bind with `args(...)`; no need to switch to `@Around` just to read arguments.
- Logging before execution alone is never a valid reason to wrap the result or exception.

For example, an unreliable audit logger might throw an exception from a formatter/remote sink; if that must not fail the business request, define a dedicated handling policy inside the advice instead of letting a logging failure become a business failure.

### 3.2. `@AfterReturning`: Processing Only When the Method Succeeds

~~~java
@AfterReturning(
    pointcut = "execution(String demo.OrderService.quote(..))",
    returning = "result",
    argNames = "result"
)
public void afterQuote(String result) {
    System.out.println("AFTER_RETURNING: " + result);
}
~~~

The advice method is invoked only when the target method **returns normally**, including when the result is `null` if the type binding permits. In the example, `returning = "result"` binds the method's returned value to the advice variable named `result`. `argNames` makes parameter-name binding explicit.

This is the right choice when:

- You need to count successful completions;
- You want to observe the return value for auditing or updating metrics;
- You need to log a result code after business logic has executed.

Key limitation: **you cannot replace the returned reference with a new reference via `@AfterReturning`'s `return` value**. Advice methods of this kind usually return `void`. If it receives a **mutable object**, in Java it can mutate the state of the object being returned (risk of side effects), which is not the same as swapping the object reference returned to the caller. If **transforming the return value** is strictly required, consider redesigning the service or using `@Around` where appropriate.

`@AfterReturning` does not run when the target method exits with an exception. If all outcomes must be observed, choose or combine another appropriate advice type.

### 3.3. `@AfterThrowing`: Processing Only When the Target Throws an Exception

~~~java
@AfterThrowing(
    pointcut = "execution(* demo.OrderService.fail(..))",
    throwing = "error",
    argNames = "error"
)
public void afterFailure(IllegalStateException error) {
    System.out.println("AFTER_THROWING: " + error.getMessage());
}
~~~

The advice runs when the advised target method **exits with a matching exception**. The `throwing` attribute binds the exception to the advice method parameter, and **the parameter's type also filters exceptions**. In the example, only exceptions of type `IllegalStateException` (or subtypes) are bound; to catch multiple types solely for logging, you can use `Throwable`, while remaining clear about your intent.

Common misconceptions:

- `@AfterThrowing` is **not equivalent** to a `catch` block that makes the exception disappear. After the advice completes normally, the target's exception still propagates to the caller.
- If you want to **recover and return an alternative result**, `@AfterThrowing` does not have the authority to do so; consider catching exceptions at the business/service boundary or `@Around` if cross-bean handling is truly required.
- According to the Spring documentation, `@AfterThrowing` is defined to receive exceptions emitted from the **target join point**; do not treat it as a listener for every exception thrown by companion `@After`/`@AfterReturning` advices.
- If the target method uses `try/catch` internally and does not rethrow, Spring AOP observes a normal return, not a thrown exit.

Distinguish "recording a failure" from "handling a failure": an advice should only be granted the authority the requirement genuinely demands.

### 3.4. `@After`: `finally`-Style Cleanup for All Exit Paths

~~~java
@After("execution(* demo.OrderService.release(..))")
public void afterRelease() {
    System.out.println("AFTER: release");
}
~~~

`@After` (after-finally advice) runs when a matching method execution **exits by returning or throwing an exception**. This type is suitable for:

- Stopping a tracking marker or performing cleanup independent of success/failure;
- Updating the count of how many times a method completed regardless of outcome;
- Releasing a resource managed under a well-defined contract.

**Do not use `@After` just to log successful transactions.** If the method throws an error, `@After` still runs; logging `SUCCESS` in this advice produces false data. Use `@AfterReturning` for successful outcomes and `@AfterThrowing` for failure outcomes when you need to distinguish them.

`@After` is similar to a Java `finally` block, yet it remains Spring AOP advice and applies only through a proxy. If the advice's own cleanup throws an exception, it can alter the outcome observed by the caller; keep cleanup safe and do not confuse having `@After` with a guarantee that every resource is released under all JVM/process failures.

### 3.5. `@Around`: Use Only When Invocation Control Is Needed

~~~java
@Around("execution(* demo.OrderService.guard(..))")
public Object aroundGuard(ProceedingJoinPoint point) throws Throwable {
    boolean allowed = (Boolean) point.getArgs()[0];
    if (!allowed) {
        return "blocked";
    }
    return point.proceed();
}
~~~

`@Around` wraps the matching method execution; its first parameter is `ProceedingJoinPoint`. It has the ability to:

- Run work before and after the target;
- **Skip calling `proceed()`**, bypassing the target;
- Call `proceed()` once or multiple times (enabling retries); side effects must be understood;
- Replace arguments passed to the target via `proceed(Object[])` under appropriate API conditions;
- Catch/rethrow/change exceptions or return a different result to the caller;
- Maintain local state across before/after within the same invocation, such as start/end timestamps.

In exchange, risk rises sharply. To **preserve the business contract unchanged**, a wrapper-style `@Around` typically must:

1. Initialize data before the call (e.g., a timer);
2. **Execute `point.proceed()` exactly once** when the target should run normally;
3. Return the **exact `Object`** returned by `proceed()`;
4. Avoid accidentally swallowing or altering exceptions;
5. Use `finally` when cleanup must run even if the method throws.

Example measuring duration with proper cleanup on both paths:

~~~java
@Around("execution(* demo..service..*.*(..))")
public Object measure(ProceedingJoinPoint point) throws Throwable {
    long started = System.nanoTime();
    try {
        return point.proceed();
    } finally {
        long elapsedNanos = System.nanoTime() - started;
        // Record metric here; do not alter the target's result or exception.
    }
}
~~~

This is an **illustrative snippet**, not a direct addition to the runnable example below; it requires an `@Aspect` bean and matching package. `System.nanoTime()` measures elapsed duration, not wall-clock timestamps. When a timer only needs start/end for a method in the same context, `@Around` is justified because separate before/after advices cannot pass per-invocation local state simply and safely.

Do not write an `@Around` returning `void` for a method with a return value if you intend to preserve the result; around advice should return `Object` and return the result of `proceed()` to preserve the contract. If intentionally returning a replacement value, ensure the result type matches the method's return type and caller expectations.

## 4. Why Does the "Smallest Kind" Make Code Safer?

An `@Around` can express every condition in the table above, yet it also carries responsibilities that narrower kinds do not require:

~~~java
@Around("execution(* demo.OrderService.begin(..))")
public Object tooPowerful(ProceedingJoinPoint point) throws Throwable {
    System.out.println("BEFORE: begin");
    return point.proceed();
}
~~~

Whereas for simply logging before a method:

~~~java
@Before("execution(* demo.OrderService.begin(..))")
public void sufficient() {
    System.out.println("BEFORE: begin");
}
~~~

These two snippets are **mutually exclusive alternatives** for the same need; do not add both to the same aspect or logs will duplicate. The `@Before` form makes intent clear and avoids managing return values, exceptions, or calling `proceed()`.

The same applies to `@AfterReturning`: an `@Around` can call the target and print the return value, but it must assume responsibility for forwarding the exact result/exception. An `@AfterReturning` runs only on the success branch and lets the framework handle the rest.

This principle aligns closely with **least privilege** at the API level: each advice is granted only the observation and modification hooks it needs, rather than extra power merely because a stronger API is convenient to overuse.

## 5. Java 17+ Spring Framework Example Covering All Five Advice Types

This project demonstrates **five distinct needs** across five separate methods. We deliberately design **non-overlapping** pointcuts so output is predictable and independent of cross-kind advice ordering. The program also counts advice invocations to prove the logic works correctly.

Requirements: Java 17+, Maven 3.9+, Spring Framework 6.2.0, AspectJ Weaver 1.9.22. These are pinned versions for illustration (not claimed to be the latest), running plain Spring Framework without Spring Boot or AspectJ weaving.

Project structure:

~~~text
spring-advice-least-power/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── OrderService.java
    └── ChoiceAspect.java
~~~

### 5.1. Maven Dependencies

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-advice-least-power</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides the Spring container/Java configuration; `spring-aop` provides AOP proxies/`AopUtils`; `aspectjweaver` supplies the library for `@AspectJ` pointcut syntax parsed by Spring. **The `aspectjweaver` dependency does not automatically enable the AspectJ compiler or load-time weaving.**

### 5.2. Target with Success, Failure, and Controllable Methods

Create `src/main/java/demo/OrderService.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public class OrderService {
    private final AtomicInteger guardExecutions = new AtomicInteger();

    public void begin() {
        System.out.println("TARGET: begin");
    }

    public String quote() {
        System.out.println("TARGET: quote");
        return "USD-10";
    }

    public void fail() {
        System.out.println("TARGET: fail");
        throw new IllegalStateException("declined");
    }

    public void release(boolean failure) {
        System.out.println("TARGET: release " +
                (failure ? "failure" : "success"));
        if (failure) {
            throw new IllegalArgumentException("release-failed");
        }
    }

    public String guard(boolean allowed) {
        guardExecutions.incrementAndGet();
        System.out.println("TARGET: guard");
        return "accepted";
    }

    public int getGuardExecutions() {
        return guardExecutions.get();
    }
}
~~~

`begin()` represents a case needing only pre-execution logging. `quote()` returns a `String` successfully. `fail()` intentionally throws `IllegalStateException` to test `@AfterThrowing`. `release(boolean)` is called twice (normal return and throwing an exception) to verify `finally`-style `@After`. `guard(boolean)` lets `@Around` decide whether to call the target; the `guardExecutions` counter **inside the target** confirms the short-circuit branch truly skips the target.

This is a complete Java class; `@Service` is unnecessary when registering via `@Bean` in configuration. The class is non-`final` and its methods are overridable, allowing Spring to create a CGLIB class proxy.

### 5.3. Aspect with Dedicated Pointcuts for Each Requirement

Create `src/main/java/demo/ChoiceAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ChoiceAspect {
    private final AtomicInteger beforeCalls = new AtomicInteger();
    private final AtomicInteger returningCalls = new AtomicInteger();
    private final AtomicInteger throwingCalls = new AtomicInteger();
    private final AtomicInteger finallyCalls = new AtomicInteger();
    private final AtomicInteger aroundCalls = new AtomicInteger();

    @Before("execution(* demo.OrderService.begin(..))")
    public void beforeBegin() {
        beforeCalls.incrementAndGet();
        System.out.println("BEFORE: begin");
    }

    @AfterReturning(
        pointcut = "execution(String demo.OrderService.quote(..))",
        returning = "result",
        argNames = "result"
    )
    public void afterQuote(String result) {
        returningCalls.incrementAndGet();
        System.out.println("AFTER_RETURNING: " + result);
    }

    @AfterThrowing(
        pointcut = "execution(* demo.OrderService.fail(..))",
        throwing = "error",
        argNames = "error"
    )
    public void afterFail(IllegalStateException error) {
        throwingCalls.incrementAndGet();
        System.out.println("AFTER_THROWING: " + error.getMessage());
    }

    @After("execution(* demo.OrderService.release(..))")
    public void afterRelease() {
        finallyCalls.incrementAndGet();
        System.out.println("AFTER: release");
    }

    @Around("execution(* demo.OrderService.guard(..))")
    public Object aroundGuard(ProceedingJoinPoint point) throws Throwable {
        aroundCalls.incrementAndGet();
        boolean allowed = (Boolean) point.getArgs()[0];
        if (!allowed) {
            System.out.println("AROUND: short-circuit");
            return "blocked";
        }
        System.out.println("AROUND: proceed");
        return point.proceed();
    }

    public int getBeforeCalls() {
        return beforeCalls.get();
    }

    public int getReturningCalls() {
        return returningCalls.get();
    }

    public int getThrowingCalls() {
        return throwingCalls.get();
    }

    public int getFinallyCalls() {
        return finallyCalls.get();
    }

    public int getAroundCalls() {
        return aroundCalls.get();
    }
}
~~~

Points to observe:

1. **`@Before`** only marks before the `begin` method; it does not hold return values or exceptions.
2. **`@AfterReturning`** only runs for `quote` on normal return, binds `result` as a `String`, and only reads/prints the value.
3. **`@AfterThrowing`** only runs for `fail` when a matching exception occurs; it does not catch/swallow the exception from the caller.
4. **`@After`** runs for `release` on both the normal call and the throwing call.
5. **`@Around`** applies only to `guard` because the requirement here is to be able to **skip the target and return `"blocked"`** when input is disallowed. For `true` input, it calls `point.proceed()` and returns the exact result from the target.
6. The pointcuts are **separated by method name**, so they do not depend on the ordering of multiple advices matching one join point. This is intentional to keep stdout reliable and help learners see each kind's power.
7. Each advice has its own counter; beyond stdout, the program verifies invocation counts. No `ThreadLocal` or global state is needed in this sequential demo.

If you only wanted to **check permission and reject with an exception before the method**, `@Before` could suffice. `@Around` in the `guard` example was chosen because the requirement is to **return `"blocked"` without running the target**, intentionally altering flow/return value. That is the key difference between picking an advice "for convenience" and picking an advice driven by requirements.

### 5.4. Initializing the Spring Context and Verifying

Create `src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public ChoiceAspect choiceAspect() {
        return new ChoiceAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            OrderService service = context.getBean(OrderService.class);
            ChoiceAspect aspect = context.getBean(ChoiceAspect.class);

            boolean proxied = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxied);

            service.begin();

            String quote = service.quote();
            System.out.println("RESULT_QUOTE: " + quote);

            try {
                service.fail();
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT: " + ex.getMessage());
            }

            service.release(false);
            try {
                service.release(true);
            } catch (IllegalArgumentException ex) {
                System.out.println("CAUGHT: " + ex.getMessage());
            }

            String blocked = service.guard(false);
            System.out.println("RESULT_BLOCKED: " + blocked);

            String allowed = service.guard(true);
            System.out.println("RESULT_ALLOWED: " + allowed);

            int before = aspect.getBeforeCalls();
            int returning = aspect.getReturningCalls();
            int throwing = aspect.getThrowingCalls();
            int finished = aspect.getFinallyCalls();
            int around = aspect.getAroundCalls();
            int actualGuards = service.getGuardExecutions();

            System.out.println("COUNTS: before=" + before
                    + ",returning=" + returning
                    + ",throwing=" + throwing
                    + ",finally=" + finished
                    + ",around=" + around
                    + ",targetGuard=" + actualGuards);

            if (!proxied || before != 1 || returning != 1
                    || throwing != 1 || finished != 2
                    || around != 2 || actualGuards != 1
                    || !"USD-10".equals(quote)
                    || !"blocked".equals(blocked)
                    || !"accepted".equals(allowed)) {
                throw new IllegalStateException(
                        "Unexpected Spring AOP advice behavior");
            }

            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Part-by-part explanation:

- `@EnableAspectJAutoProxy(proxyTargetClass = true)` registers Spring's auto-proxy creator, enabling a class proxy for `OrderService`. A bean receives a proxy only if a matching advisor applies—not every bean is proxied.
- `@Bean choiceAspect()` registers `ChoiceAspect` in the context; **`@Aspect` alone does not make a class a Spring bean**.
- `service` is retrieved from `ApplicationContext`, so normal calls to methods matching pointcuts pass through the Spring AOP proxy.
- The `try/catch` blocks in the **caller** prove that exceptions from the target still propagate to the caller after `@AfterThrowing`/`@After` run.
- `service.getGuardExecutions()` measures how many times target `guard` actually ran: the caller called twice through the proxy, yet the target ran only once because `@Around` short-circuited on the first call.
- Each counter in `ChoiceAspect` verifies each advice's semantics rather than relying solely on log order.
- The final `if` check ensures the program **throws an error if results are wrong**, and only otherwise prints `CHECK: PASS`.

### 5.5. Run Command and Output

From the `spring-advice-least-power` directory:

~~~bash
mvn -q compile exec:java
~~~

Lines printed explicitly by the Java code in the example:

~~~text
PROXY: true
BEFORE: begin
TARGET: begin
TARGET: quote
AFTER_RETURNING: USD-10
RESULT_QUOTE: USD-10
TARGET: fail
AFTER_THROWING: declined
CAUGHT: declined
TARGET: release success
AFTER: release
TARGET: release failure
AFTER: release
CAUGHT: release-failed
AROUND: short-circuit
RESULT_BLOCKED: blocked
AROUND: proceed
TARGET: guard
RESULT_ALLOWED: accepted
COUNTS: before=1,returning=1,throwing=1,finally=2,around=2,targetGuard=1
CHECK: PASS
~~~

Maven, SLF4J, or a logging framework may emit extra lines outside the example. The listing above covers only `System.out.println` statements in the code. If output differs, verify the aspect is registered as a bean, Spring AOP is enabled, pointcuts match, the caller goes through the proxy, and the advice does not throw unexpected exceptions.

From the output, **five distinct traits** are verified:

- `BEFORE` appears before `TARGET: begin`.
- `AFTER_RETURNING` appears after `TARGET: quote` and receives `USD-10`.
- `AFTER_THROWING` appears after `TARGET: fail`, yet the caller still catches `declined`.
- `AFTER: release` appears both when `release(false)` succeeds and when `release(true)` throws an exception.
- `AROUND: short-circuit` keeps `guard(false)` from printing `TARGET: guard`; `guard(true)` calls `proceed()` and prints `TARGET: guard`. The `targetGuard=1` counter confirms the target executed exactly once.

This proves **matching the advice type to the requirement**, rather than simply writing the same behavior with `@Around` for every case.

## 6. Choosing Advice for Real-World Requirements

### 6.1. Writing Audit/Tracing Before an Operation

**Requirement:** "Every time `OrderService.submit(...)` is called through the Spring proxy, record who called it and its parameters."

Choice: `@Before` with `JoinPoint` if arguments/signature are needed:

~~~java
@Before("execution(* demo.OrderService.submit(..))")
public void beforeSubmit(JoinPoint point) {
    String method = point.getSignature().getName();
    Object[] args = point.getArgs();
    // Log filtered data; do not arbitrarily log tokens/secrets/PII.
}
~~~

This snippet belongs inside an `@Aspect` and requires importing `org.aspectj.lang.JoinPoint`; `OrderService.submit` is an illustrative method name not present in the section 5 runnable project. It uses `JoinPoint` (read-only info), **not `ProceedingJoinPoint`**.

### 6.2. Counting Successful Results

**Requirement:** "Only increment `successfulCounter` if the service actually returns a result."

Choice: `@AfterReturning`. `@After` would also count failures; `@Before` would also count calls that later throw an exception. If you need to log the return value, bind `returning`. This is a classic example where **exit semantics dictate the advice type**.

### 6.3. Recording Errors Without Altering Exceptions

**Requirement:** "When a service throws a business error, record the error code for dashboard visibility; the caller still handles the exception."

Choice: `@AfterThrowing` with typed `throwing` binding. Ensure the logging logic does not throw a new error that changes the caller's flow. Do not use `@Around` to `catch` and accidentally `return null`, losing the original exception.

### 6.4. Cleanup Regardless of Success or Failure

**Requirement:** "Always mark the end of an advised operation, even when the method throws an exception."

Choice: `@After`. Distinguish this from resources whose lifecycle began before the invocation: if `@After` sees a resource whose creation source is unclear, do not assume it can safely release it. For resources created inside the advice itself, an `@Around` with `try/finally` **may be needed** to hold a local handle; for resources owned by the business method, let the business method or container manage lifecycle at the right layer.

### 6.5. Blocking the Target and Returning a Fallback Instead of an Exception

**Requirement:** "If the access policy returns false, do not call the target; return a fallback object of a valid type."

Choice: `@Around` has a clear justification. `@Before` can throw an exception to block, **but cannot return a fallback value in place of the target**. When a fallback is required, `@Around` can decide not to call `proceed()`. Still, evaluate framework-supported security/caching mechanisms before rolling your own cross-cutting policy.

### 6.6. Retrying on Failure

**Requirement:** "An idempotent call can be retried up to two times according to policy."

Only `@Around` can directly call `proceed()` multiple times in one wrapper, yet **that does not mean you should always hand-write a retry aspect**. Methods writing to DBs, sending notifications, or processing payments are often non-idempotent; retries can cause double writes or double charges. Consider dedicated retry mechanisms (such as Spring Retry), transaction boundaries, backoff, timeouts, and idempotency keys; you must define which exceptions are retryable. If the requirement does not need retries, never grant the power to re-invoke the target.

### 6.7. Transactions and Caching

Spring Framework provides dedicated modules/annotations configuring transactions and caching via appropriate advisors. If the goal is purely standard `@Transactional` or `@Cacheable` behavior, **use the corresponding Spring integration** rather than using `@Around` to rebuild transaction lifecycles, key semantics, or cache invalidation.

`@Around` is appropriate when a specialized cross-cutting requirement is not covered by existing extension points/framework features—not when you merely want "one generic annotation."

## 7. Ordering Multiple Advices and Unintended Interactions

The main example deliberately uses **separate pointcuts per advice type**. In large applications, one join point may match multiple advices simultaneously, including across multiple aspects.

- If advices belong to **different aspects**, when precedence is unspecified, order may be undefined. Use `@Order` or `Ordered` to configure aspect-level ordering.
- Higher-precedence advice generally runs **earlier on entry** to the target and **later on exit**; therefore source-code appearance order does **not** guarantee runtime order.
- Spring/AspectJ has internal rules for advice kinds within the same aspect; `@After` has *after finally* semantics, so even with specific internal precedence it normally runs after returning/throwing advices on a shared match. **Do not rely on method declaration order in a Java file.**
- Two advices of the same kind matching in one aspect do not have a guaranteed order merely from appearing above or below each other in source code.
- `@AfterThrowing` is not designed as a catch-all callback for exceptions thrown by companion `@After`/`@AfterReturning` advices; keep exception scope focused on the **target method**.

When strong ordering is required, write an **integration test** calling the actual bean proxy, assert the event trace, and configure ordering explicitly; do not infer order from annotation names or declaration positions.

Do not create extra advices "just in case" when the business need actually requires only one kind. The more advices there are, the harder it becomes to reason about effects on returns, exceptions, and transactions.

## 8. Checking Applicability Conditions Before Locking In an Advice Type

Picking the right annotation does not guarantee the advice runs: Spring applies it only to method invocations received through a proxy where the pointcut matches. `@Around` cannot fix self-invocation via `this`, objects outside the container, `final`/`private` methods on class-based proxies, constructors, or field access.

Place the desired event at the right boundary: if you need post-transaction-commit execution, use transaction synchronization or appropriate transactional events; if you need `Future`/Reactive completion, use completion callbacks/signals. `@AfterReturning` only indicates that the invocation returned normally. If transformation or fallback is needed, consider an explicit service/mapper or controlled `@Around`. Transactions, security, and caching should favor Spring's official extension points.

## 9. Reviewing Requirements, Choices, and Risks

| Need | Preferred Tool | Common Mistake |
| --- | --- | --- |
| Log before a call | `@Before` | Using `@Around` and forgetting `proceed` |
| Observe normal return results | `@AfterReturning` | Expecting advice to swap the returned reference |
| Measure exceptions by subtype | `@AfterThrowing` | Expecting advice to swallow exceptions |
| Cleanup on both return and throw | `@After` | Confusing `finally` with successful commit |
| Measure per-invocation duration | `@Around` + local `try/finally` | Storing start time in a singleton aspect field |
| Retry / fallback | Business policy or tested `@Around` | Re-executing side effects without idempotency |
| Intercept internal calls | Extract bean and inject proxy | Merely switching JDK to CGLIB |
| Track async tasks | `Future`/Reactive completion hooks | Treating wrapper return as task completion |

Every decision should explicitly document the invocation point, proxy mode, pointcut, return/exception contract, and ordering relative to infrastructure advisors. Those review criteria matter far more than picking an advice by annotation name.

## 10. Advice-Type Selection Exercises

For each requirement, pick the **narrowest type** and explain why:

1. "Log the method name before execution on a service bean."  
   **`@Before`.** No need to retain results or invoke the target manually.
2. "Increment the counter only when the call finishes successfully."  
   **`@AfterReturning`.** `@After` would also count exceptions.
3. "Report error metrics with the `IllegalStateException` message; preserve the exception for the caller."  
   **`@AfterThrowing(throwing="error")`** with a matching typed parameter.
4. "Clear a marker/metric on both return and exception."  
   **`@After`.** If you must retain a local handle created before the invocation, `@Around` with `try/finally` may be better suited.
5. "Read an argument and reject with an exception if policy forbids it."  
   **`@Before` can suffice.** Controlling `proceed()` is unnecessary.
6. "Return a cache hit without calling the target; on cache miss, call the target."  
   **`@Around`** may be needed, though prefer `@Cacheable` and framework configuration if they fit.
7. "Record the exact duration of each invocation, including exceptions, using a local start time."  
   **`@Around`** with `try/finally` is the direct way; ensure `proceed()` runs once.
8. "When a method throws an exception, return a valid fallback value instead of rethrowing."  
   **`@Around`** if this is truly a cross-cutting boundary requirement; `@AfterThrowing` cannot turn an exception into a normal return.
9. "Log the returned result object without modifying it."  
   **`@AfterReturning`** with `returning` binding.
10. "Intercept constructors and field accesses on any object."  
    **No Spring AOP advice satisfies this.** This is a proxy method-execution boundary limit; evaluate other requirements/mechanisms rather than choosing `@Around` simply because it is strongest.

## 11. Pre-Review Checklist for Spring Aspect Code

- [ ] Requirements on **timing and outcome** are clearly documented before choosing an advice annotation.
- [ ] `@Before` is preferred when only pre-method execution is needed, without wrapping `proceed()`.
- [ ] `@AfterReturning` is used for success; `@AfterThrowing` for thrown exceptions; `@After` for finally semantics.
- [ ] `@Around` is avoided unless per-invocation before/after local state or explicit invocation/return/fallback modification is required.
- [ ] With `@Around`, all branches maintain consistent policies for `proceed()`, return type, side effects, and exceptions.
- [ ] Advice does not throw unexpected errors that break the business contract.
- [ ] Both the aspect and target are registered as Spring beans, and calls go through the Spring AOP proxy.
- [ ] Pointcuts are narrow enough not to accidentally match other methods or beans.
- [ ] Tests cover normal return, thrown exception, non-matching cases, and self-invocation where relevant.
- [ ] Code does not rely on source-code order of multiple advices; explicit ordering is configured when genuinely needed.
- [ ] Built-in Spring APIs are preferred for transactions, caching, and security instead of hard-to-maintain custom `@Around` wrappers.

## 12. Official Spring Framework Documentation

- [Spring Framework 6.2 — AOP Concepts](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-defn.html): advice types and the principle of using the **least powerful advice** that meets requirements.
- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): semantics of `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around`, return/exception binding, and precedence.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): enabling `@AspectJ`-style Spring AOP support.
- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): selecting method executions on Spring beans.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation, and method limitations.
