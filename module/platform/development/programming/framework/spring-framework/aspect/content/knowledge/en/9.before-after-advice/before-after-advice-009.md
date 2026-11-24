# Advice Method Signatures and `returning` / `throwing` Configuration in Spring AOP

## 1. The Problem and Key Takeaways

With **Spring AOP using `@AspectJ` syntax**, an `@Aspect` class declares advices such as `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`, and `@Around`. The Java signature of the **advice method** determines what data Spring can pass to the advice: `JoinPoint` metadata, target arguments, return value, exception, or `proceed()` control.

Two special attributes:

- **`returning = "result"`** on `@AfterReturning`: passes the **return value when the target completes normally** into an advice parameter named `result`; the **parameter type** also constrains which results match.
- **`throwing = "error"`** on `@AfterThrowing`: passes the **exception exiting the target method execution** into an advice parameter named `error`; the **parameter type** constrains which exception types match.

These are not arbitrary names. They participate in Spring `@AspectJ`'s **binding and matching**; missing names or mismatched names/types can prevent the advice from applying or cause an error when creating the advisor.

**Core point:** `returning` and `throwing` do not belong to the *target*'s Java method signature; they are metadata on the *advice*'s annotation and must match the **advice's Java parameter**.

This lesson focuses strictly on Spring Aspect: registering Spring-managed aspect beans, Spring proxies, advice syntax, parameter binding, practical outcomes, configuration errors, and testing. It does not repeat general AOP theory or use AspectJ bytecode weaving.

## 2. Distinguishing the Target Method from the Advice Method

The two methods below perform two different roles:

```java
// Method on the Spring target bean
public String find(String id) {
    return "found:" + id;
}
```

```java
// Advice method inside a Spring-managed @Aspect
@AfterReturning(
    pointcut = "execution(public String com.example.advice.OutcomeService.find(..))",
    returning = "result",
    argNames = "result"
)
public void afterFind(String result) {
    System.out.println("result=" + result);
}
```

These are concise illustrative snippets; running them in practice requires proper packages/imports, configuration, and bean registration.

| Component | Where is it? | Meaning |
| --- | --- | --- |
| `String find(String id)` | Target service | Business declaration: input `id`, output `String`. |
| `execution(...)` | Pointcut on the advice | Selects target method executions that can be intercepted by a Spring proxy. |
| `returning = "result"` | Attribute of `@AfterReturning` | Binds the returned value to the advice parameter named `result`. |
| `String result` | Advice Java signature | Spring passes a `String`-compatible return value; this type also narrows matching. |
| `void afterFind(...)` | Advice Java signature | Observation advice; returning a value from the advice does not replace the target's return value. |
| `argNames = "result"` | Advice annotation | Makes the binding variable name explicit when needed. |

The purpose of `@AfterReturning` is to run **after normal return**; the advice method name does not have to match the target method name. The advice method can be named `observeResult`, `recordSuccess`, `afterFind`, or any valid Java identifier.

### 2.1. Two Sources of Matching Constraints

For an advice to run, it must satisfy **both**:

1. **Pointcut expression**: selects the right method execution on a Spring-managed target.
2. **Binding condition** (if present): `returning`/`throwing` and the advice parameter type must be compatible with the outcome.

Therefore, **two advices using the same pointcut** can run a different number of times if one uses `returning = "text"` with `String text`, while the other does not bind the result or uses `Object result`.

## 3. Table of Common Advice Signatures in Spring

| Annotation | Common Java advice signature | Bound data | Execution condition |
| --- | --- | --- | --- |
| `@Before("...")` | `public void before()` | No parameters needed | Right before a matching invocation. |
| `@Before("...")` | `public void before(JoinPoint jp)` | Method/args metadata, proxy/target | When the join point is about to be invoked. |
| `@After("...")` | `public void afterFinally()` | Can accept `JoinPoint` | After the join point exits, normally or with an exception. |
| `@AfterReturning("...")` | `public void afterNormal()` | Does not bind return value | Method exits normally. |
| `@AfterReturning(pointcut="...", returning="value")` | `public void afterReturn(String value)` | Return value compatible with `String` | Normal return and matching type binding. |
| `@AfterThrowing("...")` | `public void afterThrow()` | Does not bind exception | Method exits via exception. |
| `@AfterThrowing(pointcut="...", throwing="error")` | `public void afterThrow(IllegalArgumentException error)` | Exception compatible with `IllegalArgumentException` | Throwing exit matching the exception type. |
| `@Around("...")` | `public Object around(ProceedingJoinPoint pjp) throws Throwable` | Authority to call `proceed()` and decide the result | Surrounds the invocation. |

These signatures are **common patterns**, not claims that only a single valid signature exists per advice. Spring `@AspectJ` supports binding arguments, annotations, `this`/`target`, and `JoinPoint` when the expression and parameters align.

**Important:** the Spring docs recommend using the **least powerful advice form sufficient for the requirement**. If you only read exceptions, use `@AfterThrowing`; if you only read return values, use `@AfterReturning`. Do not turn every advice into `@Around` unless you need to control when/how the target executes.

## 4. `@AfterReturning`: Two Distinct Signatures

### 4.1. Without `returning`: Only Observing Normal Completion

```java
@AfterReturning(
    "execution(public * com.example.advice.OutcomeService.*(..))"
)
public void afterAnyNormalReturn() {
    normalReturns.incrementAndGet();
}
```

- `@AfterReturning` runs when a selected method **finishes normally**.
- Without `returning`, the advice **receives no value** to inspect.
- The matched method set is broad: a `void` method can also complete normally and be counted.
- If the target throws an exception out of the method, this advice does not run.

With `@AfterReturning`, "returning normally" is a **method-execution outcome**; it does not automatically mean "order accepted," "HTTP status 2xx," "transaction committed," or "future succeeded."

### 4.2. With `returning`: Receiving the Return Value

```java
@AfterReturning(
    pointcut = "execution(public * com.example.advice.OutcomeService.*(..))",
    returning = "value",
    argNames = "value"
)
public void afterString(String value) {
    System.out.println("text=" + value);
}
```

- `value` in `returning` **points to** the advice's Java parameter `String value`.
- `String` acts as a **type constraint**; the advice will not receive `Integer` or `void` results as if they were `String`.
- Using `Object value` broadens matching to normal return values compatible with `Object`.
- `argNames` makes name mapping explicit, avoiding reliance on build flags or Java parameter-name metadata.
- To also receive `JoinPoint`, declare it **first in the parameter list** per Spring convention; do not use `ProceedingJoinPoint` in non-around advice.

### 4.3. The `returning` Name Must Match the Parameter Name

Incorrect example:

```java
@AfterReturning(
    pointcut = "execution(* com.example.advice.OutcomeService.*(..))",
    returning = "data",
    argNames = "result"
)
public void wrongAdvice(String result) {
}
```

This is a **misconfiguration illustration**; do not add it to a context that must start cleanly. `returning` specifies `data`, while the declaration/`argNames` provide `result`; Spring/AspectJ has no valid binding for `data`, and advisor/advice initialization may fail.

A valid version looks like:

```java
@AfterReturning(
    pointcut = "execution(* com.example.advice.OutcomeService.*(..))",
    returning = "result",
    argNames = "result"
)
public void correctAdvice(String result) {
    // ...
}
```

Do not put the target method's name, a field name, or an arbitrary alias into `returning`. Use the **name of the advice parameter** that will receive the return value.

## 5. `@AfterThrowing`: Two Distinct Signatures

### 5.1. Without `throwing`: Exceptional Exit Event

```java
@AfterThrowing(
    "execution(public * com.example.advice.OutcomeService.*(..))"
)
public void afterAnyThrownExit() {
    failures.incrementAndGet();
}
```

This parameterless advice can record a failure event when the selected target method execution **exits via an exception**. It does not know what the exception object is unless bound.

It **does not run** when the target catches the error internally and returns a fallback normally. `@AfterThrowing` observes **errors exiting the join point**, not every exception thrown deeper in the call stack.

### 5.2. With `throwing`: Receiving the Exception and Filtering by Subtype

```java
@AfterThrowing(
    pointcut = "execution(public * com.example.advice.OutcomeService.*(..))",
    throwing = "problem",
    argNames = "problem"
)
public void afterIllegalArgument(IllegalArgumentException problem) {
    System.out.println("badArg=" + problem.getMessage());
}
```

- `throwing="problem"` binds the exception to **`problem`** on the advice method.
- `IllegalArgumentException` restricts matching to instances of that type (or subtypes).
- To match more error types, you can use `RuntimeException`, `Exception`, or `Throwable`, depending on semantics and testing.
- In Java, `IllegalArgumentException extends RuntimeException`; a method throwing `IllegalStateException` will not match an `IllegalArgumentException` binding.
- The advice's exception parameter is **not** an error response object and not a return value type. `throwing` does not substitute for `returning`.

### 5.3. `@AfterThrowing` Is Not a General `try/catch` Handler

`@AfterThrowing` **observes** an exceptional exit. It does not receive a `ProceedingJoinPoint` to call `proceed()` or turn an error into a normal return simply by returning a value.

If it only logs the exception and completes normally, the original exception keeps propagating to the caller. If the advice **throws another exception itself**, the caller may receive the new exception instead of the original one—a dangerous behavioral change that should not be used as "error handling."

According to the Spring documentation, `@AfterThrowing` focuses on errors from the **user-declared target join point**, not as a callback catching exceptions raised by companion `@After`/`@AfterReturning` advices in the same aspect.

**If you want to recover or return a fallback to the caller**, handle it at the business boundary or use `@Around` with an actual `try/catch` and clear contract. Do not attach `@AfterThrowing` expecting an advice return value to replace the error.

## 6. Java Method Signature Characteristics to Understand

### 6.1. Return Type of Advice Methods

Advices such as `@Before`, `@After`, `@AfterReturning`, and `@AfterThrowing` **should be declared `void`** because any return value from the advice itself is not used by Spring to replace the business method's result.

`@Around` is different: it typically uses an `Object` return type, accepts `ProceedingJoinPoint`, and calls `proceed()`. The `return` value from `@Around` is the value the caller can observe once the interceptor chain finishes.

```java
@Around("execution(* com.example.advice.OutcomeService.find(..))")
public Object aroundFind(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    return result;
}
```

This is an illustrative snippet requiring an import for `org.aspectj.lang.ProceedingJoinPoint` inside a Spring-managed `@Aspect`. If the value returned by `@Around` is incompatible with the target method's declared return type, the application can fail at runtime.

### 6.2. Visibility of Advice Methods

Advice methods in the examples are `public`, making them easy to read and reducing access issues when Spring invokes them via framework infrastructure. This is the **visibility of the method containing advice logic**, **not** the visibility of the Spring target method in `execution(public * ...)`.

Do not confuse this with the visibility of a **named `@Pointcut` method** used to reuse expressions. A `@Pointcut` method can be `private`/`protected`/`public` depending on reuse scope; that does not make target methods private or public.

### 6.3. `JoinPoint` Can Come First in the Advice Method

```java
@Before("execution(public * com.example.advice.OutcomeService.*(..))")
public void beforeCall(JoinPoint jp) {
    System.out.println(jp.getSignature().getName());
}
```

`JoinPoint` comes from `org.aspectj.lang.JoinPoint`. Spring can supply metadata for the intercepted method execution, target, and arguments.

Example combining `JoinPoint` and `returning`:

```java
@AfterReturning(
    pointcut = "execution(public String com.example.advice.OutcomeService.find(..))",
    returning = "result",
    argNames = "result"
)
public void afterFind(JoinPoint jp, String result) {
    System.out.println(jp.getSignature().getName() + "=" + result);
}
```

**Note:** a leading `JoinPoint` parameter has special binding handling; when specifying `argNames`, the Spring docs permit omitting the leading `JoinPoint` parameter name from the `argNames` list. Do not treat `JoinPoint` as a business method argument.

`JoinPoint.getArgs()` returns the arguments passed to the invocation; that data may include sensitive details. Log using whitelists/redaction, and never log passwords/tokens simply because they are accessible.

### 6.4. `ProceedingJoinPoint` Is Only for `@Around`

```java
@Around("execution(* com.example.advice.OutcomeService.*(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

Advices other than `@Around` should not declare `ProceedingJoinPoint` expecting to call `proceed()`. The purpose of `@Before`/`@AfterReturning`/`@AfterThrowing` is observation at a defined moment, not replacing the call flow.

### 6.5. One Advice Method Cannot Use Both `returning` and `throwing`

`@AfterReturning` has `returning`, and `@AfterThrowing` has `throwing`. They are **two distinct annotations** with **mutually exclusive outcomes for a single execution**: either the method finishes normally or an exception exits.

There is no `@AfterReturning(returning="result", throwing="error")` configuration in Spring `@AspectJ`. When both branches must be handled, use **two advice methods** or `@Around` depending on the goal.

## 7. Complete Java 17+ Demo: 6 Calls, 6 Advice Counters

This demo uses **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, **Java 17+**, Gradle, and plain Spring Java configuration. It verifies the same pointcut across multiple methods with different bindings.

For reliable output, the advices **only increment counters** (no printing inside advices). Thus the program does not depend on execution order among advices sharing a join point.

Goals:

- `@Before` counts all six method executions through the proxy.
- `@After` counts all six completions under after-finally semantics.
- Unbound `@AfterReturning` counts four normal returns.
- `String`-bound `@AfterReturning` counts two text returns.
- `IllegalArgumentException`-bound `@AfterThrowing` counts one error of that matching subtype.
- `Throwable`-bound `@AfterThrowing` counts two exceptional exits.

### 7.1. Project Directory

```text
spring-advice-signatures-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/advice/
    ├── Main.java
    ├── AppConfig.java
    ├── OutcomeService.java
    └── OutcomeAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-advice-signatures-demo'
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
    mainClass = 'com.example.advice.Main'
}
```

Spring Framework 6.x requires Java 17+. In Spring Boot production projects, let Boot's BOM/dependency management select synchronized Spring versions rather than manually pinning the demo versions.

### 7.2. Target Bean: Distinct Outcomes

**`OutcomeService.java`**

```java
package com.example.advice;

public class OutcomeService {
    public String find(String id) {
        return "found:" + id;
    }

    public Integer count() {
        return 3;
    }

    public void refresh() {
        System.out.println("target:refresh");
    }

    public String rejected() {
        throw new IllegalArgumentException("bad-id");
    }

    public String crashed() {
        throw new IllegalStateException("storage-down");
    }

    public String recovered() {
        try {
            throw new IllegalArgumentException("transient");
        } catch (IllegalArgumentException ex) {
            return "fallback";
        }
    }
}
```

All methods are `public` and non-final, and the class is non-final. Thus the test cases isolate **outcome** and **binding** rather than being mixed with CGLIB `final`/`private` restrictions.

`recovered()` illustrates an exception caught **inside the target**: the final outcome of the method execution is the normal return `"fallback"`, so `@AfterThrowing` on `recovered` does **not** run.

### 7.3. Aspect: Different Signatures on the Same Pointcut

**`OutcomeAspect.java`**

```java
package com.example.advice;

import java.util.concurrent.atomic.AtomicInteger;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class OutcomeAspect {
    private static final String SERVICE =
            "execution(public * com.example.advice.OutcomeService.*(..))";

    private final AtomicInteger before = new AtomicInteger();
    private final AtomicInteger afterFinally = new AtomicInteger();
    private final AtomicInteger normal = new AtomicInteger();
    private final AtomicInteger textReturn = new AtomicInteger();
    private final AtomicInteger illegalArgument = new AtomicInteger();
    private final AtomicInteger anyThrowable = new AtomicInteger();

    @Before(SERVICE)
    public void beforeMethod(JoinPoint jp) {
        before.incrementAndGet();
    }

    @After(SERVICE)
    public void afterMethod() {
        afterFinally.incrementAndGet();
    }

    @AfterReturning(SERVICE)
    public void afterNormal() {
        normal.incrementAndGet();
    }

    @AfterReturning(
        pointcut = SERVICE,
        returning = "value",
        argNames = "value"
    )
    public void afterString(String value) {
        textReturn.incrementAndGet();
    }

    @AfterThrowing(
        pointcut = SERVICE,
        throwing = "failure",
        argNames = "failure"
    )
    public void afterBadArgument(IllegalArgumentException failure) {
        illegalArgument.incrementAndGet();
    }

    @AfterThrowing(
        pointcut = SERVICE,
        throwing = "error",
        argNames = "error"
    )
    public void afterAnyFailure(Throwable error) {
        anyThrowable.incrementAndGet();
    }

    public int beforeCount() { return before.get(); }
    public int afterCount() { return afterFinally.get(); }
    public int normalCount() { return normal.get(); }
    public int textCount() { return textReturn.get(); }
    public int argumentErrorCount() { return illegalArgument.get(); }
    public int throwableCount() { return anyThrowable.get(); }
}
```

The counter variables are **instance fields on an aspect bean**, so `AtomicInteger` prevents lost updates if multiple threads call the service. This is only single-JVM demo instrumentation and does **not** replace a production multi-instance metric registry/telemetry system.

All pointcuts share the `SERVICE` string, so differences among the counters reflect **event semantics** and **`returning`/`throwing` type constraints**.

**Why doesn't `JoinPoint jp` appear in `argNames` on `@Before`?** It is a special parameter provided by Spring/AspectJ according to advice signature rules. In the example, `jp` is not yet used to print the signature, but passing it shows an advice can access join point metadata. If your code style enables compiler warnings for unused parameters, you can remove the parameter and `JoinPoint` import without changing any counts; the demo keeps it to illustrate the signature.

### 7.4. Registering Spring Beans and Enabling `@AspectJ`

**`AppConfig.java`**

```java
package com.example.advice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    OutcomeService outcomeService() {
        return new OutcomeService();
    }

    @Bean
    OutcomeAspect outcomeAspect() {
        return new OutcomeAspect();
    }
}
```

`@Aspect` does not automatically create a Spring bean; `@Bean` on `AppConfig` creates the Spring-managed `OutcomeAspect` instance. `@EnableAspectJAutoProxy` detects advice metadata and builds AOP proxies for target beans matching advisors.

`proxyTargetClass=true` lets `Main` look up `OutcomeService` by its concrete type. This is a choice for the demo, not a requirement for `returning`/`throwing` to work; JDK interface proxies can be used if the target exposes a suitable interface and Spring is configured accordingly.

### 7.5. Running Calls and Verifying Advice Counts

**`Main.java`**

```java
package com.example.advice;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            OutcomeService service = context.getBean(OutcomeService.class);
            OutcomeAspect aspect = context.getBean(OutcomeAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("find=" + service.find("X"));
            System.out.println("count=" + service.count());
            service.refresh();

            try {
                service.rejected();
            } catch (IllegalArgumentException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            try {
                service.crashed();
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println("recovered=" + service.recovered());

            System.out.println("before=" + aspect.beforeCount());
            System.out.println("normal=" + aspect.normalCount());
            System.out.println("string=" + aspect.textCount());
            System.out.println("illegalArgument=" + aspect.argumentErrorCount());
            System.out.println("anyThrowable=" + aspect.throwableCount());
            System.out.println("afterFinally=" + aspect.afterCount());
        }
    }
}
```

Run with Gradle installed and JDK 17+:

```bash
gradle run --quiet
```

If using the Gradle Wrapper, run `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

**Stdout printed by the program, in order** (excluding JVM/Spring/Gradle logs enabled by the environment):

```text
proxy=true
find=found:X
count=3
target:refresh
caught=bad-id
caught=storage-down
recovered=fallback
before=6
normal=4
string=2
illegalArgument=1
anyThrowable=2
afterFinally=6
```

### 7.6. Invocation-by-Invocation Explanation

| Call through Spring proxy | Target method outcome | `@Before` | Unbound `@AfterReturning` | `String`-bound `@AfterReturning` | `IllegalArgumentException`-bound `@AfterThrowing` | `Throwable`-bound `@AfterThrowing` | `@After` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `find("X")` | Returns `"found:X"` | 1 | 1 | 1 | 0 | 0 | 1 |
| `count()` | Returns `Integer(3)` | 1 | 1 | 0 | 0 | 0 | 1 |
| `refresh()` | `void`, normal exit | 1 | 1 | 0 | 0 | 0 | 1 |
| `rejected()` | Throws `IllegalArgumentException` | 1 | 0 | 0 | 1 | 1 | 1 |
| `crashed()` | Throws `IllegalStateException` | 1 | 0 | 0 | 0 | 1 | 1 |
| `recovered()` | Catches internally, returns `"fallback"` | 1 | 1 | 1 | 0 | 0 | 1 |
| **Total** | Six method executions | **6** | **4** | **2** | **1** | **2** | **6** |

These are **totals after all calls complete**, not bean instance counts, HTTP request counts, or transaction commit counts. A single execution throwing `IllegalArgumentException` can be observed by **both `@AfterThrowing` advices** because `IllegalArgumentException` is also a `Throwable`. The second advice is not a retry of the target invocation.

Note: ordering between the two `@AfterThrowing` advices is not locked; they only update independent counters, so the chosen stdout does not depend on order.

## 8. Binding Additional Method Arguments with `args(...)`

Many applications want to log both input and result—or input and exception—of the **same call**. Spring `@AspectJ` supports binding target arguments in the pointcut using `args(...)`.

### 8.1. Input and Return Value

```java
@AfterReturning(
    pointcut =
        "execution(public String com.example.advice.OutcomeService.find(..))"
        + " && args(id)",
    returning = "result",
    argNames = "id,result"
)
public void afterFind(String id, String result) {
    System.out.println("find(" + id + ")=" + result);
}
```

This is an **illustrative snippet** inside a Spring-managed `@Aspect`. `args(id)` binds the target argument to `String id`. `returning="result"` binds the normal return to `String result`. `argNames="id,result"` explicitly names the two advice parameters.

For `find("X")`, if added to its own bean or swapped into the demo to run independently, it would print:

```text
find(X)=found:X
```

**Do not add this advice as-is to a demo whose stdout from section 7.5 must stay unchanged.** It produces extra output.

If a method has multiple arguments, you can use `args(id,..)` to bind the first parameter or `args(first,second)` for a method with exactly two arguments, depending on desired matching. The count and types of the Java advice parameters must match the bound names.

### 8.2. Input and Exception

```java
@AfterThrowing(
    pointcut =
        "execution(public String com.example.advice.OutcomeService.find(..))"
        + " && args(id)",
    throwing = "error",
    argNames = "id,error"
)
public void afterFindFailure(String id, RuntimeException error) {
    System.out.println("failed:" + id + ":" + error.getClass().getSimpleName());
}
```

This is also **illustrative**. `find(..)` in the demo does not throw an error for input `"X"`, so this advice **does not run** in that case. Only if the target is modified to throw a matching exception and the expression matches does Spring bind `RuntimeException error`.

Key point: **`returning`** and **`throwing`** bind two different kinds of outcomes. To use both data sources, write two advices sharing `args` with different outcome annotations, or use `@Around` when a single interception body truly must handle both paths.

## 9. Binding Parameter Types Create Matching Constraints

### 9.1. `Object`, `String`, `Number`, and `void`

```java
// Selects normal returns whose type is compatible with Object.
@AfterReturning(
    pointcut = "execution(* com.example.advice.OutcomeService.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterObject(Object result) {
    // ...
}
```

```java
// Selects normal returns whose type is compatible with String.
@AfterReturning(
    pointcut = "execution(* com.example.advice.OutcomeService.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterText(String result) {
    // ...
}
```

The two separate snippets above should **not** be merged into the demo's `OutcomeAspect` if you want to preserve its counters. They show that **`String` is a stricter condition than `Object`** for return binding. A `void` method has no `String` value; if you only need to count `void` normal completions, use an unbound `@AfterReturning`.

With generic/covariant return types, bridge methods, `null`, or targets declaring `Object` while varying runtime values, matching details can depend on how Spring/AspectJ checks types. **Test your specific Spring version** before relying on typed-returning advice for critical business policy.

### 9.2. `Throwable`, `Exception`, and `RuntimeException`

```java
@AfterThrowing(
    pointcut = "execution(* com.example.advice.OutcomeService.*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterFailure(Throwable error) {
    // Can observe RuntimeException, checked Exception, or Error per matching.
}
```

`Throwable` is a broad type, suitable when telemetry needs all exceptional exits. `Exception` excludes `Error`s like `OutOfMemoryError`; `RuntimeException` matches only unchecked runtime exceptions and subclasses. `IllegalArgumentException` is one concrete subclass.

**Do not abuse catch-all metrics to swallow errors.** `@AfterThrowing` advice is not the place to fix `OutOfMemoryError` or turn fatal exceptions into normal business outcomes.

### 9.3. `null` from the Target

A method:

```java
public String optionalName() {
    return null;
}
```

completes **normally**, so an unbound `@AfterReturning` runs if the pointcut matches. With a returning-bound reference type, **read `result` with null-safe logic** because an invocation can produce `null`. Never call `result.length()` unconditionally.

If the concept you need to check is "data present" rather than "method finished normally," use `Optional`, a business result object, or service-level policy; do not equate `@AfterReturning` with business success by default.

### 9.4. `Future` and Reactive Returns

Spring `@AspectJ` advice looks at the **proxied method execution**. With `CompletableFuture<T>` or `Mono<T>`, the target can **return a future/publisher wrapper normally** even when the underlying task or subscription later fails.

In that situation:

- `@AfterReturning(returning="value")` binds the **future/publisher object** (if the parameter type matches), not `T` once computation finishes.
- `@AfterThrowing` on the proxied method **does not run** for asynchronous errors occurring after the method already returned the wrapper successfully.
- When completion semantics are needed, use completion callbacks like `whenComplete` for futures or appropriate Reactor operators/instrumentation; do not equate wrapper return with eventual result.

## 10. Signature Determines Bound Data, Not Permission to Alter Outcomes

| Advice signature | What Spring can provide |
| --- | --- |
| `void onReturn(String value)`, `returning=value` | `String`-compatible normal result; does not replace the reference returned to caller |
| `void onFailure(IOException error)`, `throwing=error` | `IOException`-compatible exception; does not return a fallback |
| `Object around(ProceedingJoinPoint pjp) throws Throwable` | Authority to `proceed()` and return a result or throw an error matching the contract |

Analysis of object identity, mutable state, and replacement belongs to the dedicated `@AfterReturning` lesson; exception recovery belongs to the dedicated `@AfterThrowing` lesson. Changing a regular advice's return type to `String` or `Object` does not turn it into `@Around`.

## 11. Separating Binding-Name Errors from Type-Matching Errors

With `returning="result"`, `argNames="result"`, and advice parameter `String result`, all three must align. Changing only `argNames` to `"value"` creates a name-mapping mismatch even when the pointcut is valid; this can cause advisor/binding creation errors.

Similarly, `throwing="failure"` with `Throwable failure` accepts a broad range of exceptions, whereas `IOException failure` accepts only `IOException` or subtypes. When testing, isolate three conditions: right target/pointcut, right parameter names, and right return/exception types. In a throwing call, returning advice does not run even if its return parameter type matches the method's declared return type.

## 12. `JoinPoint` and Annotation Binding

Spring `@AspectJ` also supports binding annotations, receivers/targets, and method arguments.

### 12.1. Advice Only Needing the Method Name

```java
@Before("execution(public * com.example.advice.OutcomeService.*(..))")
public void before(JoinPoint jp) {
    String name = jp.getSignature().getName();
    System.out.println("enter:" + name);
}
```

A leading `JoinPoint` is valid for non-around advices. Do not use `ProceedingJoinPoint` here because `@Before` does not control `proceed()`.

### 12.2. Advice Needing an Annotation on the Target Method

Suppose there is an annotation:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditedOperation {
    String category();
}
```

This illustrative snippet requires Java imports for `ElementType`, `Retention`, `RetentionPolicy`, and `Target`, placed in an appropriate package.

Binding:

```java
@Before(
    value = "@annotation(marker)",
    argNames = "marker"
)
public void beforeAudited(AuditedOperation marker) {
    System.out.println(marker.category());
}
```

The advice receives the `AuditedOperation` from the method's annotation. `argNames` matches the `marker` parameter. This is **not** `returning`/`throwing`, yet it follows the same name/type binding model in Spring `@AspectJ`. Do not mix class-level annotations (`@within`/`@target`) with method-level annotations (`@annotation`) if the pointcut calls for one specifically.

### 12.3. When Is `argNames` Needed?

Spring discovers argument names from:

- Explicit `argNames` on the advice/`@Pointcut` annotation when declared.
- Java parameter-name metadata if the build preserves the relevant info.
- Spring `@AspectJ` binding inference rules in certain cases.

For standalone READMEs/demos, `argNames` makes code less dependent on build flags. However, `argNames` cannot **rescue** a syntactically invalid pointcut or type mismatch. When multiple parameters exist, the order of names must correspond to the advice's bound parameters.

Spring specially recognizes a leading `JoinPoint` parameter without requiring it to be listed in `argNames`. For `@Around`, `ProceedingJoinPoint` is the corresponding leading parameter.

## 13. Multiple Advices on the Same Target: Ordering and Exceptions

A service method may simultaneously be advised by:

- Spring-managed custom audit/metrics aspects;
- Transaction/cache/security proxy interceptors;
- Two or more advices belonging to one `@Aspect`;
- `@Around` advices from other frameworks.

**Advice ordering can affect which outcome an advisor observes.** `@Order`/`Ordered` sets precedence across aspects, but you should not assume source-file declaration order determines execution order between two advices of the same kind.

The Spring docs note:

- On a single join point, precedence determines "entry" and "exit" order.
- `@After` means after-finally; it can run after `@AfterReturning`/`@AfterThrowing` per cleanup semantics.
- Two advices **of the same kind in the same aspect** have no guaranteed fixed order based solely on source position.
- An aspect's `@AfterThrowing` is not a callback that catches exceptions thrown by a companion `@AfterReturning`/`@After`.

The demo intentionally uses **counters instead of logging inside advices** to avoid locking execution order between the two `@AfterThrowing` advices. When a strict sequence is required for business policy, separate aspects with explicit precedence or use a single advice body with transparent control flow, backed by integration tests.

## 14. Spring Boot: Similarities and What to Verify

With Spring Boot AOP auto-configuration when the right dependencies are present, you typically do not need to add `@EnableAspectJAutoProxy` yourself. However, advice signature rules **do not change**:

1. The aspect has `@Aspect` **and** must be registered as a Spring bean via `@Component` (within component-scan scope) or `@Bean`.
2. The target service is a Spring-managed bean.
3. Advice annotations and `returning`/`throwing` names match the advice parameters.
4. Type bindings match the normal returns or thrown exceptions.
5. Callers actually use the Spring proxy, not `new` or self-invocation `this.method()`.
6. Spring Boot's JDK vs. CGLIB proxy settings do not make `final` methods interceptable under CGLIB.

Example dependencies by Boot major version (assuming the project uses Boot's dependency management):

```gradle
// Boot 3.x
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

```gradle
// Boot 4.x
implementation 'org.springframework.boot:spring-boot-starter-aspectj'
```

These are **two options by major version**—do not copy both into the same project. Boot 3 and 4 may differ in transitive starter packaging, yet `@AfterReturning` and `@AfterThrowing` remain in `org.aspectj.lang.annotation` under Spring `@AspectJ` support.

If Boot sets `spring.aop.proxy-target-class=true`, Spring typically uses class proxies; check `final` methods/classes, package scanning, and overall AOP configuration.

## 15. Common Errors with Advice Signatures and Binding

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Startup error after adding `returning` | `returning` string does not match advice parameter name, or wrong `argNames` | Use identical names and valid types. |
| Startup error after adding `throwing` | No parameter name bound, or invalid annotation/pointcut | Use `throwing="error"` and `Throwable error`/compatible subtype. |
| Unbound `@AfterReturning` runs, `String`-bound does not | Target returns a non-`String` type, `void`, or has a mismatch | Check declared/actual result types, bind intentionally, and integration-test. |
| `@AfterThrowing(IllegalArgumentException)` does not run for `IllegalStateException` | Incompatible exception type | Use subtype matching matching requirements, or broader `RuntimeException`/`Throwable`. |
| Method throws internally, yet `@AfterThrowing` does not run | Target caught the error before exiting the join point | Observe final outcome; returning a fallback is a normal return. |
| Both exception advices run for one method | `IllegalArgumentException` is also a `Throwable` | Not a duplicate advice bug; both advisors/bindings validly matched. |
| `@AfterReturning` does not change result even when returning/assigning a new string | This advice does not replace the returned reference | Use `@Around` or modify the business method to change results. |
| `@AfterThrowing` logs, yet caller still gets the exception | Expected semantics | If recovery is needed, use an explicit handler or `@Around` with proper contract. |
| Advice only sees a future/publisher instead of final data | Interception happens when wrapper returns, not async completion | Observe completion/reactive signals using their respective APIs. |
| `JoinPoint` in wrong position or wrong `argNames` order | Binding violates convention | Place `JoinPoint` first; list names for remaining bound variables. |
| `ProceedingJoinPoint` used on `@Before` | `proceed()` is exclusive to `@Around` | Switch to `JoinPoint` or actually use `@Around`. |
| Aspect bean exists, yet advice is never called | AOP not enabled, pointcut mismatch, target bypassed proxy, or `final`/`private` | Verify bean/proxy/method boundary and actual outcome. |
| Advice on inner method does not run when called from outer | `this.inner()` bypasses the proxy | Extract to a collaborator bean with an injected proxy if interception is truly required. |
| Transaction rollback/commit differs from expectation | Advice ordering and exception handling affect the chain | Test transactions with real config; do not infer from normal-return logs. |
| Advice throws an exception and business calls start failing | Error inside advice propagates through proxy to caller | Define a clear error policy for telemetry/auditing; avoid unexpected outcome changes. |

## 16. A Meaningful Spring AOP Testing Workflow

### 16.1. Configure a Real Context

Write integration tests using `AnnotationConfigApplicationContext`, Spring Test `@SpringJUnitConfig`, or `@SpringBootTest` as fits the project. Unit tests calling `new OutcomeAspect().afterString(...)` directly **do not prove Spring binding works**.

### 16.2. Check the Proxy First

```java
OutcomeService service = context.getBean(OutcomeService.class);
System.out.println(AopUtils.isAopProxy(service));
```

In the demo, the result is `true`. However, **`proxy=true` does not guarantee every advice method matched**. Continue verifying specific events/counters for each outcome.

### 16.3. Verify All Branches

- Normal `String` return → `afterNormal` and `afterString`.
- Normal `Integer` return → `afterNormal`, not `afterString`.
- Normal `void` completion → `afterNormal`, not `afterString`.
- `IllegalArgumentException` → `afterBadArgument` and `afterAnyFailure`.
- `IllegalStateException` → only `afterAnyFailure`.
- Exception caught inside target returning a fallback → normal-return advice, **not** exceptional advice.
- External Spring proxy call vs. `new`/`this` internal call → verify boundary.

### 16.4. Write Assertions Independent of Advice Stdout

```java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    OutcomeService service = context.getBean(OutcomeService.class);
    OutcomeAspect aspect = context.getBean(OutcomeAspect.class);

    service.find("X");
    service.count();
    service.refresh();
    try { service.rejected(); } catch (IllegalArgumentException ignored) {}
    try { service.crashed(); } catch (IllegalStateException ignored) {}
    service.recovered();

    if (aspect.beforeCount() != 6
            || aspect.normalCount() != 4
            || aspect.textCount() != 2
            || aspect.argumentErrorCount() != 1
            || aspect.throwableCount() != 2
            || aspect.afterCount() != 6) {
        throw new AssertionError("Advice binding or outcome counts differ");
    }
}
```

This snippet uses the demo's classes and requires importing `AnnotationConfigApplicationContext`; it runs **on a fresh context** rather than merging into `Main` if you want to keep the sample output unchanged. In real projects, replace `if` checks with JUnit assertions.

### 16.5. Sensitive Data and Concurrency

- Do not log raw `JoinPoint.getArgs()` or result DTOs containing tokens, passwords, or payment details.
- Aspects are typically singleton Spring beans by default, so mutable fields must be thread-safe or preferably avoided (stateless).
- `AtomicInteger` protects only a single counter; it does not make multi-field compound updates atomic.
- If an advice calls IO or remote services, enforce timeouts/error policies and watch latency impact on method calls.
- With `@AfterThrowing`, do not catch broad `Throwable` and use it to decide "which errors to swallow." Observation binding is not a recovery policy.

## 17. Final Checklist

- [ ] Clearly distinguished that the **target method signature** and the **advice method signature** are two separate things?
- [ ] Aspect has `@Aspect` and is registered as a Spring bean via `@Component` or `@Bean`?
- [ ] Spring AOP `@AspectJ` infrastructure and AspectJ Weaver are configured properly?
- [ ] `@Before`/`@After`/`@AfterReturning`/`@AfterThrowing` are normally declared `void`?
- [ ] `@Around` takes `ProceedingJoinPoint` first, calls `proceed()` appropriately, and returns `Object` or a compatible type?
- [ ] If using `@AfterReturning(returning="value")`, is there a matching advice parameter `value`?
- [ ] If using `@AfterThrowing(throwing="error")`, is there a matching exception parameter `error`?
- [ ] Do parameter types (`String`/`Throwable`/subtypes) match the intended set of outcomes?
- [ ] If using `argNames`, do names and order align with bound parameters and `JoinPoint`'s special rule?
- [ ] Distinguished normal return, caught exception, thrown exception, `void`, `null`, and async-wrapper returns?
- [ ] Avoided using `@AfterReturning` to replace returned references or `@AfterThrowing` to swallow exceptions?
- [ ] Target calls actually pass through the Spring proxy, methods are proxy-interceptable, and calls are not self-invocations?
- [ ] When multiple advices exist, avoided relying on arbitrary ordering of two advices of the same kind?
- [ ] Integration tests confirm return bindings and exception bindings on actual Spring-managed calls?
- [ ] Telemetry/advice has clear null-safety, privacy, and error policies?

**Key takeaway:** In Spring AOP, `@AfterReturning`'s `returning` and `@AfterThrowing`'s `throwing` **must point to exact advice method parameters**. The parameter's Java type **filters matching results/exceptions**, while `argNames` helps Spring resolve bindings explicitly. `JoinPoint` provides metadata, and `ProceedingJoinPoint` is for `@Around`. Every advice takes effect only when **Spring beans, proxies, and pointcuts** are properly aligned—and observing an outcome does not grant permission to replace results or swallow errors.

## Official Spring Documentation

- [Spring Framework 6.2 — Declaring Advice: `@AfterReturning`, `@AfterThrowing`, `@Around`, Advice Parameters, and Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Proxying Mechanisms / Self-Invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Advice API (Distinguishing `@AspectJ` and Programmatic Advisors)](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/advice.html)
