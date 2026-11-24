# Behavior When Not Calling proceed() in Spring AOP @Around Advice

## 1. The Most Important Point

In **Spring AOP**, an advice declared with `@Around` has the authority to decide **whether to continue the intercepted call**. The `ProceedingJoinPoint.proceed()` method is the step that continues **the rest of the interceptor/advice chain** toward the target method. If a branch of `@Around` **does not call `proceed()`**, that branch **short-circuits** the call: it does not transfer control down to the rest of the chain inside that advice, so **the target business method does not run on that call path**.

This is **valid behavior under the Spring AOP API**, not inherently an error. However, it carries major business implications: the target method is not executed, expected side effects do not occur, and the caller may receive **a value returned by the aspect itself** or **an exception thrown by the aspect**.

Lesson objectives:

1. Understand precisely what role `proceed()` plays in Spring `@Around`.
2. Distinguish between **not calling proceed**, **calling it once**, and **calling it multiple times**.
3. Know what the caller receives when the advice performs `return` or `throw` on its own.
4. Write fallbacks compatible with methods returning `String`, primitive `int`, and `void`.
5. Recognize consequences for auditing, transactions, persistence, caching, external APIs, exceptions, and interceptor ordering.
6. Verify with a runnable example on **plain Spring Framework** using Java 17+, Maven, and Spring AOP proxies.

**Scope:** Focuses only on `@Around` and `ProceedingJoinPoint` in **Spring-managed `@Aspect`**, without turning into a lesson on general AspectJ weaving.

## 2. Call Flow With and Without proceed

A Spring service bean can be exposed as a proxy:

~~~text
Client
  |
  v
Spring AOP proxy
  |
  v
@Around advice
  |
  +-- BRANCH A: pjp.proceed()
  |                 |
  |                 v
  |       Remaining interceptors
  |                 |
  |                 v
  |           Target method
  |                 |
  |                 v
  |        Result or exception
  |                 |
  |                 v
  |        @Around continues running
  |                 |
  |                 v
  |               Caller
  |
  +-- BRANCH B: return fallback, no proceed
  |                 |
  |                 v
  |     Skips inner chain and target
  |                 |
  |                 v
  |               Caller
  |
  +-- BRANCH C: throw exception, no proceed
                    |
                    v
         Exception propagates to caller
         (unless outer layer handles it)
~~~

Minimal example:

~~~java
@Around("execution(* demo.CheckoutApi.checkout(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("Before");

    if (maintenanceMode) {
        return "temporarily-unavailable";
    }

    Object result = pjp.proceed();
    System.out.println("After");
    return result;
}
~~~

This is a **fragment inside an aspect class**; it requires the `maintenanceMode` field, `@Around` and `ProceedingJoinPoint` imports, Spring AOP configuration, and matching beans. In the maintenance branch:

- The advice still runs, so `Before` is printed.
- `proceed()` is not called.
- There is no call to the target's `checkout(...)` method through that continuation.
- `After` is not executed because of the early `return` branch.
- The caller receives the string `temporarily-unavailable`, provided that value fits the method's return signature.

In the normal branch, `proceed()` continues to invoke the method, the result travels back to the advice, and the advice forwards the result to the caller.

## 3. proceed() Is Not an Ordinary Business Method

`ProceedingJoinPoint` is the mandatory parameter by Spring `@Around` convention. Example:

~~~java
@Around("execution(* demo.CheckoutApi.checkout(..))")
public Object intercept(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
~~~

In Spring AOP:

- `pjp.proceed()` **continues the current invocation** with the original arguments.
- `pjp.proceed(new Object[] { ... })` can be used to continue with a different argument array matching the target method's count, types, and order.
- `pjp.getArgs()` provides the current arguments.
- `pjp.getSignature()` describes the advised method/join point.
- `pjp.getThis()` returns the Spring AOP proxy; `pjp.getTarget()` returns the target object, yet **calling a method directly on the target does not substitute for calling proceed**.

Important: `proceed()` is not simply equivalent to `target.method()`. It passes execution **down the chain** that the proxy prepared. If other interceptors/advisors sit inside, they also get a chance to run when `proceed()` is called. An early `return` can bypass them as well.

The Spring documentation explicitly states that `proceed()` may be called **zero times, once, or many times** inside `@Around`. All three cases are valid mechanically; **valid does not mean reasonable for every business operation**.

## 4. Comparison Table of the Three Cases

| Inside @Around | Target runs? | Value caller receives | Risk |
| --- | --- | --- | --- |
| `return pjp.proceed();` | Yes, if inner chain also continues | Usually the target's value | Normal behavior |
| `return fallback;` without calling proceed | No, on this branch | Fallback provided by the aspect | Skips side effects, hides unexecuted work |
| `throw new IllegalStateException(...);` without calling proceed | No, on this branch | Caller receives the exception | Alters the method's exception contract |
| Calling `pjp.proceed()` twice | May execute target twice | Determined by advice code | Duplicates transactions or side effects |
| No proceed and `return null;` | No | null, if the return contract permits | For primitives, may fail when proxy unboxes/restores return |
| No proceed and `return 0;` for int-returning method | No | Integer unboxed by proxy to `int` | Easily turns "not executed" into a fake valid result |

Do not conclude that "no proceed means **no advice runs at all**." That around advice itself ran; interceptors **wrapping outside it** can still run before/after the call returns or throws. Only the steps **sitting inside at the skipped continuation point** and the target method are not reached on that branch.

When multiple advisors exist, the observed outcome depends on chain order. Do not infer that all `@Before` advice is skipped or all `@AfterReturning` advice will run without checking which side an advisor sits on.

## 5. Return Contract When Skipping the Target

### 5.1. Object-Returning Method

Suppose the service interface is:

~~~java
String checkout(String orderId);
~~~

The aspect can return:

~~~java
if (orderId.startsWith("SKIP-")) {
    return "skipped:" + orderId;
}
~~~

The caller receives this `String` instead of the target's result. Nothing in the Java compiler automatically verifies that an `@Around` branch returns the exact `String` type for every method matched by the pointcut, because `@Around` methods normally declare **Object**.

If the pointcut is too broad and the same `return "skipped"` branch applies to a method returning `int`, you may hit a runtime error due to an incompatible return type.

### 5.2. Primitive-Returning Method

Suppose:

~~~java
int fee(String orderId);
~~~

The aspect should return a value convertible to `int`, for example:

~~~java
if (shouldSkip(orderId)) {
    return 0;
}
~~~

With an advice returning `Object`, the value `0` is boxed into an `Integer` and then returned by the proxy to the caller according to the `int` signature.

**Do not return null** for a method with a primitive return type. Because null cannot be converted to a primitive, completing the invocation can fail (Spring AOP has checks for null on primitives, and depending on the proxy there is also the risk of an unboxing error).

Also consider the business meaning: `fee = 0` may mean "valid zero fee," **not** "fee not calculated." If those are two distinct states, design a return type that expresses the difference, such as a result with a status, or throw an appropriate exception.

### 5.3. Void-Returning Method

Suppose:

~~~java
void notifyCustomer(String orderId);
~~~

An advice declared with return type `Object` can use:

~~~java
if (shouldSkip(orderId)) {
    return null;
}
return pjp.proceed();
~~~

For a target method returning `void`, the caller receives no meaningful Java value. `return null` from the advice simply ends the continuation through the proxy.

**However, returning void does not mean skipping arbitrarily is harmless.** If notification is mandatory, the caller will still assume the call completed normally. Establish a clear convention that skipping is acceptable, or represent the outcome via a return type/exception.

### 5.4. Why Should @Around Return Object Instead of void?

Spring recommends that `@Around` methods **declare `Object` as the return type** and typically `return` the result of `proceed()`. If the advice method instead declares `void`, the caller will not receive the value returned from the continuation as expected.

To make one aspect apply to `String`, `int`, and `void` methods, use `public Object around(ProceedingJoinPoint pjp) throws Throwable`, and ensure each branch honors the contract of each method. When logic grows complex, split into **multiple pointcuts/advices with clear types and responsibilities** rather than writing a switch covering hundreds of methods.

## 6. Complete Example: Skipping Three Method Types With Verification

We build an application using **Spring Framework 6.2.12**, **Java 17+**, and **Maven 3.9+**. No Spring Boot or database is needed.

A Spring `CheckoutService` provides three methods:

- `String checkout(String orderId)`: executes checkout and returns a result.
- `int fee(String orderId)`: calculates a fee.
- `void notifyCustomer(String orderId)`: sends a notification.

A Spring `GateAspect` applies `@Around` to all three. If `orderId` starts with `SKIP-`, the advice **does not call proceed** and supplies the corresponding fallback; otherwise, the advice calls `proceed()` exactly once.

An `ExecutionProbe` is injected into the target to count how many times **the target method actually executes**. This clearly verifies that `AOP bypass` is not merely a log line while the target still runs silently behind the scenes.

### 6.1. Directory Structure

~~~text
spring-aop-around-shortcircuit/
├── pom.xml
└── src/main/java/demo/
    ├── CheckoutApi.java
    ├── CheckoutService.java
    ├── ExecutionProbe.java
    ├── GateAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-around-shortcircuit</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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

`spring-context` provides `ApplicationContext` and the required Spring AOP modules. `aspectjweaver` provides the annotation/pointcut types Spring uses for `@AspectJ` style. The example operates via **Spring proxy**, with no compile-time or load-time weaving.

### 6.3. Interface Exposing Three Methods

**src/main/java/demo/CheckoutApi.java**

~~~java
package demo;

public interface CheckoutApi {
    String checkout(String orderId);
    int fee(String orderId);
    void notifyCustomer(String orderId);
}
~~~

Having an interface allows plain Spring Framework by default to choose a **JDK dynamic proxy**. The app retrieves the bean by `CheckoutApi`, without casting the proxy to the implementation.

### 6.4. Probe Counting Target Executions

**src/main/java/demo/ExecutionProbe.java**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class ExecutionProbe {

    private final AtomicInteger targetCalls = new AtomicInteger();

    public void increment() {
        targetCalls.incrementAndGet();
    }

    public int count() {
        return targetCalls.get();
    }
}
~~~

This is a **supporting bean**, not a target of the `CheckoutApi` pointcut. It is not matched by `GateAspect` merely because it is also Spring-managed. `AtomicInteger` makes counter increments/reads concurrency-safe for the demonstration.

### 6.5. Target Executing Business Logic

**src/main/java/demo/CheckoutService.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService implements CheckoutApi {

    private final ExecutionProbe probe;

    public CheckoutService(ExecutionProbe probe) {
        this.probe = probe;
    }

    @Override
    public String checkout(String orderId) {
        probe.increment();
        System.out.println("TARGET checkout " + orderId);
        return "paid:" + orderId;
    }

    @Override
    public int fee(String orderId) {
        probe.increment();
        System.out.println("TARGET fee " + orderId);
        return 25;
    }

    @Override
    public void notifyCustomer(String orderId) {
        probe.increment();
        System.out.println("TARGET notifyCustomer " + orderId);
    }
}
~~~

The target increments the counter at the start of each method. If `GateAspect` does not call `proceed()`, the `probe.increment()` statements **are not executed by the target**. The observed outcome does not rely solely on log output from the advice.

In a real application, the target might write to a database, call an external API, or emit events; skipping proceed means those side effects **do not occur on the intercepted invocation**, aside from any work outside the target already executed elsewhere beforehand.

### 6.6. GateAspect: Three Fallback Types, No proceed

**src/main/java/demo/GateAspect.java**

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class GateAspect {

    @Around("execution(* demo.CheckoutApi.*(..))")
    public Object aroundCheckoutApi(ProceedingJoinPoint pjp)
            throws Throwable {

        String methodName = pjp.getSignature().getName();
        String orderId = (String) pjp.getArgs()[0];

        System.out.println("AOP enter " + methodName + " " + orderId);

        if (orderId.startsWith("SKIP-")) {
            System.out.println("AOP bypass " + methodName);

            return switch (methodName) {
                case "checkout" -> "skipped:" + orderId;
                case "fee" -> 0;
                case "notifyCustomer" -> null;
                default -> throw new IllegalStateException(
                        "No fallback for " + methodName);
            };
        }

        Object result = pjp.proceed();
        System.out.println("AOP proceeded " + methodName);
        return result;
    }
}
~~~

This is the core:

1. `@Aspect @Component` both declares the aspect and registers the class as a Spring bean.
2. `@Around("execution(* demo.CheckoutApi.*(..))")` selects method executions matching the `CheckoutApi` interface handled by the Spring proxy.
3. `pjp.getArgs()[0]` reads the first `orderId`; the demo assumes all three methods share the `(String)` signature. **Do not copy this mechanically** to an interface with zero-arg methods or a non-String first parameter.
4. When `orderId` has the `SKIP-` prefix, the `return switch` branch **does not call proceed**.
5. `checkout` returns the `String` `"skipped:" + orderId` matching its contract.
6. `fee` returns literal `0` (boxed to `Integer`), compatible with the primitive `int` return type.
7. `notifyCustomer` returns `null` at the advice layer, suitable for a `void` target method.
8. Other `orderId` values call `pjp.proceed()` **exactly once**, returning the target result.
9. `System.out.println("AOP proceeded ...")` after proceed runs only if the continuation completes normally; if the target throws and the advice does not catch it, that line does not appear.

**Design note:** Choosing fallbacks by method name is a concise way to demonstrate three return types. In production, split into advices with narrower pointcuts or a separate tested policy, so adding a method to the interface does not accidentally yield a missing or mistyped fallback.

### 6.7. Enabling Spring AOP

**src/main/java/demo/AppConfig.java**

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

`@ComponentScan` registers `CheckoutService`, `ExecutionProbe`, and `GateAspect`. `@EnableAspectJAutoProxy` enables the infrastructure that reads `@Aspect` and builds Spring AOP proxies when matching advisors exist. `@Aspect` **does not register a bean by itself without component registration or `@Bean`**.

### 6.8. Main: Invoking Both Normal and Skipped Branches

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    private static void invokeAll(CheckoutApi checkout, String orderId) {
        String result = checkout.checkout(orderId);
        System.out.println("CALLER checkout=" + result);

        int fee = checkout.fee(orderId);
        System.out.println("CALLER fee=" + fee);

        checkout.notifyCustomer(orderId);
        System.out.println("CALLER notified");
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            CheckoutApi checkout = context.getBean(CheckoutApi.class);
            ExecutionProbe probe = context.getBean(ExecutionProbe.class);

            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(checkout));

            System.out.println("=== NORMAL ===");
            invokeAll(checkout, "OK-1");

            System.out.println("=== SKIP ===");
            invokeAll(checkout, "SKIP-9");

            System.out.println("TARGET_CALLS " + probe.count());
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

### 6.9. Expected Logical Stdout

~~~text
IS_PROXY true
=== NORMAL ===
AOP enter checkout OK-1
TARGET checkout OK-1
AOP proceeded checkout
CALLER checkout=paid:OK-1
AOP enter fee OK-1
TARGET fee OK-1
AOP proceeded fee
CALLER fee=25
AOP enter notifyCustomer OK-1
TARGET notifyCustomer OK-1
AOP proceeded notifyCustomer
CALLER notified
=== SKIP ===
AOP enter checkout SKIP-9
AOP bypass checkout
CALLER checkout=skipped:SKIP-9
AOP enter fee SKIP-9
AOP bypass fee
CALLER fee=0
AOP enter notifyCustomer SKIP-9
AOP bypass notifyCustomer
CALLER notified
TARGET_CALLS 3
~~~

**Output analysis:**

- In the `NORMAL` group, there are three `TARGET` lines, corresponding to three `proceed()` calls executed.
- In the `SKIP` group, there are `AOP enter` and `AOP bypass` lines, yet **no `TARGET` lines**.
- Each caller continues running: receiving a String fallback, an int fallback, or completing a void method without exceptions.
- `TARGET_CALLS 3` confirms that only the three calls on the normal branch reached the target. The three calls on the SKIP branch **did not** increment the counter.
- `IS_PROXY true` only proves the bean is Spring-proxied; the advice/target output and probe prove the specific `@Around` behavior.

This lesson describes **logical stdout** from the program, excluding Maven or Spring logging messages. The example uses a single aspect and a fixed set of advisors, so guessing ordering across multiple aspects is not required.

## 7. What Still Runs When the Target Is Skipped?

A common misconception is thinking "not proceeding means the entire application does nothing." That is incorrect.

When an advice skips the target:

- **Code that already ran inside the advice before `return`** still produces side effects, such as logging `AOP enter`, incrementing metrics, or reading cache.
- **Caller code before invoking the service** already executed.
- **Caller code after the proxy call returns normally** continues running.
- **Outer interceptors/advices in the chain** can still execute and observe results/exceptions according to actual ordering.
- **The target and interceptors sitting inside the short-circuit point** are not reached by the continuation along that branch.

For example, an outer `@Around` records proxy call duration while an inner `@Around` returns a fallback. The outer around still receives a result when it calls proceed to hand control to the inner around, even though the target does not run. You cannot deduce from the absence of `TARGET` logs that "no transaction/security/logging advice ran."

When multiple advisors exist, determining which aspect is outer or inner depends on actual ordering. You can use `@Order` or `Ordered` to set precedence across applicable aspects/advisors; test whenever short-circuit logic has business significance.

## 8. Throwing an Exception Instead of Returning a Fallback

Another option is to block the call and throw an exception:

~~~java
@Around("execution(* demo.CheckoutApi.checkout(..))")
public Object guard(ProceedingJoinPoint pjp) throws Throwable {
    String orderId = (String) pjp.getArgs()[0];

    if (orderId.startsWith("DENY-")) {
        throw new IllegalStateException("Denied: " + orderId);
    }

    return pjp.proceed();
}
~~~

This is an **alternative aspect fragment**; do not add it alongside `GateAspect` in the main demo if you want to preserve section 6's stdout. The `DENY-` branch **does not call proceed**, the target is not executed on that branch, and the caller receives `IllegalStateException`, unless an outer interceptor/caller catches or converts the exception.

Compare:

~~~java
return "skipped:" + orderId;
~~~

with:

~~~java
throw new IllegalStateException("Denied: " + orderId);
~~~

The first signals **success at the Java call level** to the caller with a substitute value; the second **signals failure through the exception contract**. Which direction to choose must be based on real business requirements, not merely to make the method run "quietly."

If the application has an outer transaction interceptor, an escaping exception can affect rollback according to transaction rules. If the around advice swallows the exception or returns a normal result, transaction behavior changes. Therefore, Spring AOP short-circuiting must be reviewed alongside the advisor chain—never assume that "skipping the target means any existing transaction does not exist either."

## 9. Cache Hit Is a Common Case of Not Proceeding

A valid use case for `@Around` is caching:

~~~java
@Around("execution(* demo.LookupService.find(..)) && args(key)")
public Object aroundFind(ProceedingJoinPoint pjp, String key)
        throws Throwable {

    Object cached = cache.getIfPresent(key);
    if (cached != null) {
        return cached; // No proceed: return cached result directly
    }

    Object result = pjp.proceed();
    cache.put(key, result);
    return result;
}
~~~

This is an **illustrative fragment**, assuming `cache`, `LookupService`, and suitable Spring AOP configuration; it is not a standalone runnable file. A cache hit skips the target; a cache miss invokes the target and stores the result.

Things to verify when applying this in practice:

1. Cached values **must be compatible** with the advised return type.
2. `null` in a cache may mean "no data," or it may be a valid cached result; distinguish a **cache miss** from a **cached null**.
3. If callers expect side effects on every invocation, do not silently return a cached result and skip side effects.
4. If multiple threads hit a cache miss simultaneously, multiple proceeds may occur; cache concurrency policy must be designed.
5. Use Spring's built-in cache annotations when appropriate instead of hand-rolling AOP caching when no custom behavior is needed.

A standalone cache aspect must still exclude appropriate cache-support beans from its pointcut to avoid re-entering the advice through its own collaborators.

## 10. Authorization and Maintenance: Short-Circuiting Should Be Explicit

For operations denied due to permissions or maintenance, **not calling the target** may be the exact goal. However, do not default to returning a "success-looking" value if the action was blocked.

Example:

~~~java
if (!permissionService.allowed(user, operation)) {
    throw new SecurityException("Operation not allowed");
}

return pjp.proceed();
~~~

This is a **code fragment**; `permissionService`, `user`, and `operation` beans/variables must be declared in an appropriate context. Denying via an exception sends a clearer signal than `return true` on a method that did not actually complete.

If this is Spring Security, consider built-in method-security mechanisms rather than creating hard-to-audit custom permission advice. For maintenance mode, standardize error/status responses at the API layer. Never use `@Around` to silently skip payment recording or mandatory data updates.

**Business rule:** Short-circuiting can be a sound mechanism, but you must always explicitly define **which action is not performed** and **how the caller is notified**.

## 11. Risk of Returning a Substitute Result of the Wrong Type

An `Object`-returning advice is not enforced by the Java compiler to match every method covered by the pointcut on all branches:

~~~java
@Around("execution(* demo.CheckoutApi.*(..))")
public Object bad(ProceedingJoinPoint pjp) {
    return "SKIPPED";
}
~~~

This is a **bad-design illustrative fragment**; do not combine it with the main demo. It may return a `String` for `fee(String)` returning `int` or `notifyCustomer(String)` returning `void`. For `fee`, the incompatible return type can cause a runtime error when the proxy tries to return the result under an `int` signature.

Ways to avoid this:

- Use narrow pointcuts targeting **a single method or a group sharing the same return contract**.
- Design a dedicated result type such as `OperationResult` if callers need to distinguish `EXECUTED`, `SKIPPED`, or `DENIED`.
- For primitive-returning methods, return a matching wrapper and never `null`.
- For `void` methods, remember callers cannot read a fallback value; choose an explicit exception/event when skipping is not a valid outcome.
- Test **return types** on both the proceed branch and the non-proceed branch.

## 12. Not Calling proceed Does Not Mean the Target Was Destroyed

Not calling proceed **blocks a single specific invocation**. It does not:

- Destroy the bean in `ApplicationContext`.
- Prevent the target from being instantiated or having dependencies injected at startup.
- Automatically roll back operations that already ran earlier.
- Stop async work already scheduled elsewhere beforehand.
- Block other methods on the same bean if those methods do not match the pointcut.
- Turn private/internal self-invocations into proxied calls.
- Force outer interceptors to stop running.
- Guarantee that external data already written before the call will be restored.

In the example, Spring created one `CheckoutService` bean even though none of the three `SKIP` calls ran the target body. `ExecutionProbe` remained alive and kept its count from the three normal calls.

If a method both writes to a database and publishes a message, skipping proceed bypasses **the entire target method body** on that call path. Yet if another part of the workflow already wrote to the database before entering the proxy, short-circuiting does not automatically undo that prior work.

## 13. Proceeding Multiple Times: Totally Different From Not Proceeding

Spring allows `proceed()` to be called multiple times:

~~~java
@Around("execution(* demo.TaskApi.run(..))")
public Object retry(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (TransientFailureException first) {
        return pjp.proceed();
    }
}
~~~

This is a **fragment illustrating a retry idea**; it will not compile standalone without defining `TaskApi` and `TransientFailureException`, and requires AOP configuration. It can execute the target **twice**, along with repeated side effects, so use it only for tasks with appropriate retry/idempotency policies.

Distinguish the three policies:

~~~text
proceed 0 times -> bypass target
proceed 1 time  -> normal execution
proceed 2 times -> may re-execute target (if chain completes)
~~~

Retry also depends on where in the chain an exception is thrown and on advisor ordering; do not infer the target ran once just because an exception was caught.

If a method returns transaction details, running twice can cause double charges or double publishes. Consider a dedicated retry framework, verify idempotency, and lock transactions; do not treat multiple `proceed` calls as "harmless."

## 14. Advice Ordering: Short-Circuiting Can Affect Other Advice

Suppose two aspects exist:

- `MetricsAspect` measures duration.
- `GateAspect` decides not to proceed for `SKIP-`.

If `MetricsAspect` is an advisor **wrapping outside** `GateAspect`, it can still log metrics after `GateAspect` returns a fallback. If `GateAspect` wraps outside `MetricsAspect` and does not proceed, `MetricsAspect` is never called via continuation.

Key points to remember:

| Position relative to short-circuit | Likelihood of running |
| --- | --- |
| Around advice making the bypass decision | Already ran to make the decision |
| Advice sitting outside that already called proceed into the short-circuiting advice | Can complete its before/after logic normally |
| Advice sitting inside the short-circuiting advice | Not reached if proceed is not called |
| Target method | Does not run on the bypassed invocation |
| Caller after proxy | Continues if proxy returns normally; handles error if exception |

**There is no rule saying "every @Before runs even when @Around skips" or "no @After ever runs."** Chain order is the deciding factor.

Spring supports ordering between aspects/advisors via `@Order` and related ordering mechanisms. When business requirements involve transactions, security, or auditing, test actual runtime order rather than guessing from source method declaration order.

## 15. Self-Invocation Is a Separate Issue

If a method on the target calls:

~~~java
public void outer() {
    this.inner();
}
~~~

Spring AOP **normally does not intercept the `this.inner()` call** because it does not pass through the proxy. That is a **proxy limitation**, different from an `@Around` that intercepted `inner` and intentionally chose not to call proceed.

Two scenarios:

1. **No interception:** no proxied call occurs for `inner`, so `inner`'s advice never executes.
2. **Intercepted then skipped:** `inner`'s `@Around` advice ran, yet did not call the continuation.

The distinction is whether logs or side effects **inside the advice** appear. If you do not see an `AOP enter` log, do not jump to the conclusion that the advice short-circuited; the pointcut might not match or the call bypassed the proxy altogether.

## 16. How to Test Non-Proceed Behavior

### 16.1. Positive/Negative Tests by Side Effect

For the section 6 demo, assert:

~~~java
int before = probe.count();
String skipped = checkout.checkout("SKIP-T1");

if (!"skipped:SKIP-T1".equals(skipped)) {
    throw new AssertionError("Wrong fallback");
}

if (probe.count() != before) {
    throw new AssertionError("Target should not have executed");
}

String executed = checkout.checkout("OK-T2");

if (!"paid:OK-T2".equals(executed)) {
    throw new AssertionError("Wrong target result");
}

if (probe.count() != before + 1) {
    throw new AssertionError("Target should have executed once");
}
~~~

This is an **additional test fragment** needing `checkout` (of type `CheckoutApi`) and `probe` (of type `ExecutionProbe`) obtained from the context. It is not a standalone Java file.

Checking only the `AOP bypass` log line is insufficient; verify **actual target execution was skipped** using a counter, spy, or appropriate persistence state.

### 16.2. Testing Return Contracts Per Signature

- `checkout("SKIP-...")` must return a valid String fallback.
- `fee("SKIP-...")` must return a valid primitive `int`, with no unboxing error.
- `notifyCustomer("SKIP-...")` must complete normally if skipping is permitted.
- When denying by exception, the caller must receive the **designed exception**.
- `checkout("OK-...")` must execute the target exactly once.
- When multiple aspects exist, test under the **real advisor ordering configuration**.

### 16.3. Testing Whether the Pointcut Is Too Broad

If `@Around` uses `execution(* demo..*.*(..))` and the advice invokes Spring beans like `ExecutionProbe`, `AuditRecorder`, or `GateService`, those beans also risk being matched by the advisor, causing advice re-entry or unexpected behavior. In the demo, the pointcut is scoped to the `CheckoutApi` interface, keeping `ExecutionProbe` out of range.

Do not rely on Spring excluding `@Aspect` classes from auto-proxying to assume all aspect collaborators are excluded too.

## 17. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| No target log, yet caller receives a result | Around advice returned a fallback without calling proceed | Check return branches in `@Around` and verify contract |
| Caller receives unexpected `null` | Advice short-circuited without returning a proper fallback | Define return type and intentional substitute value |
| `int`-returning method fails on bypass | Advice returned null or incompatible String | Return a valid `Integer` or redesign the return type |
| `void` method didn't run while caller assumes it succeeded | Advice returned null and hid skipped status | Design an explicit status/exception or event |
| Expected audit/transaction advice missing | An outer around advisor short-circuited before reaching inner chain | Check advisor order and continuation |
| Some advice still runs when target is skipped | They sit outside the short-circuit point | Analyze chain order; do not assume all advice is skipped |
| Advice causes more side effects than target | Advice executed logic itself even without proceed | Audit advice code and its collaborators |
| Call creates duplicate payment | Retry called proceed multiple times on non-idempotent method | Design controlled idempotency/retry |
| `AOP enter` is missing | Method doesn't match pointcut, bean isn't proxied, or self-invocation | Check bean, pointcut, and caller path |
| Returned fallback violates API contract | Aspect uses one return value across multiple signatures | Narrow pointcut or split advice per method |
| Missing exception when business operation was rejected | Advice returned a success-like fallback | Return a status indicating skip or throw an appropriate exception |
| Target bean/dependencies created yet method didn't run | Bean lifecycle happens before invocation | Distinguish bean construction from method execution |
| Advice calls recorder and loops infinitely | Recorder also matches the pointcut | Exclude collaborators from pointcut or use a business allowlist |
| `@Around` with `void` return type loses result | Advice fails to propagate proceed's return value | Use `Object` and return the appropriate result |

## 18. Checklist Before Intentionally Skipping proceed()

1. **Why shouldn't the method run?** Cache hit, maintenance, authorization denial, or another intentional policy?
2. **How is the caller informed?** Cached/fallback value, explicit status, or exception?
3. **Is the return type accurate?** Especially primitives, void, nullable types, and generics?
4. **Which side effects are skipped?** Database writes, message sends, state updates, metrics?
5. **Did any side effects happen before calling the proxy?** If so, short-circuiting does not undo them.
6. **Is advisor ordering right?** Where do transactions, security, auditing, and tracing sit?
7. **Should this responsibility move to a dedicated Spring feature?** Such as caching, security, or retry?
8. **Is the pointcut scoped strictly to business methods?** Avoid accidentally matching recorders or infra beans.
9. **Does the call path definitely go through the Spring proxy?** Do not confuse with self-invocation.
10. **Are both proceed and skip branches tested?** Verify real side effects and outputs, not just logs.
11. **If proceed is called multiple times, is the target idempotent?** Do not retry operations with non-repeatable side effects.
12. **Is the fallback semantics unambiguous?** Do not assume `0`, `null`, or `"OK"` accurately represents the business state.

## 19. Self-Check Questions

**1. If an `@Around` advice does not call proceed, does the target run?**

Not through that short-circuited invocation. The advice may do other work directly, but continuation to the target is not executed.

**2. Is not calling proceed a Spring AOP error?**

No. Spring allows calling `proceed()` 0, 1, or many times. That is the power of around advice, though it must be used intentionally.

**3. Who supplies the result to the caller when around does not proceed?**

The value that the advice itself `return`s, or the exception the advice `throw`s. The value must comply with the method return contract.

**4. If the target method returns void, what should around return when skipping?**

`@Around` should still declare return type `Object` and can `return null`. However, the application must treat this as an intentional skip, not assume business work completed.

**5. What happens if the target method returns int and the advice returns null?**

The result is incompatible with primitive `int`, which can trigger an error as the proxy completes the invocation. Return an appropriate `Integer` or design a clearer result type.

**6. Can an outer advice still run when an inner advice skips the target?**

Yes. The outer advice may have already entered and will continue processing the inner advice's return value or exception. Never assume all advice is skipped.

**7. How does this differ from self-invocation?**

Self-invocation can bypass the proxy from the start so `@Around` is never entered. Short-circuiting means `@Around` was entered and chose not to call `proceed()`.

**8. Can `proceed()` be used twice?**

Mechanically yes. However, it can execute the target and side effects repeatedly and must be managed as a retry, with proper idempotency and transaction boundaries.

**9. Why is a `0` fallback for a payment fee easily misunderstood?**

Because `0` can mean "actual fee is zero" instead of "fee was not calculated." Results should express state accurately.

**10. What is the best proof that the target was skipped?**

Use a counter, spy, or system state to compare target execution counts between the proceed and skip branches, alongside verifying the caller result.

## 20. Official Spring Documentation

- **Spring Framework — Declaring Advice / Around Advice**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- **Spring Framework — AOP Concepts / Around Advice**: https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- **Spring Framework — Advice API / MethodInterceptor**: https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html
- **Spring Framework — Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Framework — @AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html

**Conclusion:** In Spring `@Around`, **not calling `proceed()` is a deliberate decision to bypass the continuation and target method for the current invocation**. The advice may return a fallback or throw an exception instead of the target, provided it preserves the return contract, keeps business state transparent, and verifies side effects. Use this approach only when you genuinely need control over "whether the target runs"; if you only need before/after processing, prefer a simpler advice type.
