# Binding Return Values with `returning` and Exceptions with `throwing` in Spring AOP

## 1. Goal and scope

In Spring Framework, when declaring advice with `@Aspect`, two important attributes are **`returning`** on `@AfterReturning` and **`throwing`** on `@AfterThrowing`. Not only do they tell Spring which Java parameter should receive the **return value** or **exception exiting the method**, but the advice parameter type also affects **which invocations are eligible to trigger the advice**.

This lesson focuses on **Spring Aspect / proxy-based Spring AOP** and answers these questions:

1. How do you access a Spring bean method's return value using `returning = "result"`?
2. How do you receive an exception via `throwing = "error"`?
3. Why do `String result`, `Object result`, `IllegalArgumentException error`, and `Throwable error` have different matching scopes?
4. How does Spring determine advice parameter names, and when do you use `argNames` or `javac -parameters`?
5. When does advice not run: `void` methods, incompatible types, exceptions caught inside the target, invocations via `this`, objects outside Spring?
6. How do you write runnable Maven/Java 17+ code, predict stdout, and test both matching and non-matching cases?

This is **not** a general AOP theory article. The content targets the practical conditions for **Spring to create advisors, select methods, and pass contextual data into a Spring-managed `@Aspect` bean**.

## 2. Two basic binding styles

### 2.1. `returning`: result from a method completing normally

Example:

~~~java
@Aspect
public class ResultAspect {

    @AfterReturning(
        pointcut = "execution(* example.PaymentService.find(..))",
        returning = "result",
        argNames = "result"
    )
    public void afterFind(String result) {
        System.out.println("payment result: " + result);
    }
}
~~~

This is a **snippet**, assuming `example.PaymentService.find(..)` exists, the aspect is registered as a Spring bean, and Spring AOP is enabled.

- `pointcut` selects the matching **method execution**.
- `returning = "result"` instructs Spring to **bind the return value** to the advice parameter named `result`.
- The `String result` parameter both lets code read the result as a `String` and restricts the advice to compatible `String` results.
- `argNames = "result"` explicitly specifies the binding name so it does not rely entirely on the compiler retaining parameter names.
- This advice runs only when the method **returns normally** through a call intercepted by Spring AOP.

You **cannot** use `@AfterReturning` to return a new reference replacing the value already returned by the method. The advice can inspect the received value; if the object is mutable and you invoke a mutating method on that object itself, its internal state can change — a side effect to strictly avoid if you only want logging or auditing.

### 2.2. `throwing`: exception exiting the method

Example:

~~~java
@Aspect
public class FailureAspect {

    @AfterThrowing(
        pointcut = "execution(* example.PaymentService.pay(..))",
        throwing = "error",
        argNames = "error"
    )
    public void afterFailedPayment(IllegalArgumentException error) {
        System.out.println("invalid payment: " + error.getMessage());
    }
}
~~~

This is also a **snippet**, not a complete project.

- `throwing = "error"` binds the throwable thrown out of the method execution to the parameter named `error`.
- The `IllegalArgumentException` type makes the advice apply only to throwables **compatible with this type**; an `IllegalStateException` will not be received by this advice.
- Spring runs `@AfterThrowing` only when the join point takes an **exceptional exit**, not wherever code creates and then catches an exception internally.
- The advice does not automatically turn an exception into a normal return. If it only logs and returns `void`, the original exception continues propagating through the proxy as usual.

An `@AfterThrowing` advice is also **not a global exception handler** for all exceptions from other advice methods. Per Spring documentation, it applies to exceptions coming from the advised method join point, **not automatically receiving exceptions thrown by another `@After` or `@AfterReturning` advice**.

## 3. Exact semantic comparison

| Aspect | `@AfterReturning(..., returning = "x")` | `@AfterThrowing(..., throwing = "x")` |
| --- | --- | --- |
| Timing | Advised method execution **returns normally** | Advised method execution **throws a Throwable out** |
| Bound value | Return value | Thrown Throwable |
| Matching parameter name required | `x` must match the advice parameter's binding name | `x` must match the advice parameter's binding name |
| Parameter type affects matching | E.g., `String` receives only String-compatible results | E.g., `IllegalArgumentException` receives only compatible exceptions |
| How to express a broad scope | `Object x` when the result is needed as `Object`, subject to compatible values | `Throwable x` when many throwable types are needed |
| If target catches error and returns | Runs if the return value matches | **Does not run** because no exception exits the join point |
| If target returns `void` normally | Can use `@AfterReturning` **without binding** | Does not run because there is no throwable |
| If target throws an exception | Does not run | Runs when the exception type matches |
| Replacing caller's return directly | Returning from advice does not replace the returned reference | Returning `void` does not turn an exceptional exit into success |

**Key point:** `returning` and `throwing` both serve as **names to bind context** and activate **type-sensitive matching** based on the advice parameter's type. Simply changing the Java type of the parameter can alter the set of invocations to which the advice applies.

## 4. Binding name must match the advice parameter name

Correct configuration:

~~~java
@AfterReturning(
    pointcut = "execution(* example.ReportService.read(..))",
    returning = "value",
    argNames = "value"
)
public void afterRead(String value) {
    // The name "value" is consistent across the annotation attribute and advice parameter.
}
~~~

Erroneous configuration:

~~~java
// WRONG example; do not copy as runnable code.
@AfterReturning(
    pointcut = "execution(* example.ReportService.read(..))",
    returning = "result",
    argNames = "value"
)
public void afterRead(String value) {
    // "result" does not match binding name "value".
}
~~~

When misconfigured, Spring may throw an exception while parsing/creating the advisor or resolving parameters; **do not rely on a single exception class name** across all Spring versions.

Verification steps:

1. Identify the value of `returning = "..."` or `throwing = "..."`.
2. Check that the advice method has a matching parameter.
3. If `argNames` is used, the names in it must match the bound variables.
4. Verify the exact parameter **type**: `String`, `Object`, a specific exception type, or `Throwable`.
5. Verify the expression does not miss the target method or get excluded by another pointcut.
6. Verify Spring AOP recognized the advice method and created the appropriate proxy.

If the advice method has multiple parameters, you can combine `JoinPoint`, `args(...)`, `target(...)`, `@annotation(...)`, and `returning`/`throwing` values, but keep names conflict-free and declare them accurately.

## 5. How does Spring find advice parameter names?

`returning = "value"` and `throwing = "error"` are **binding names** that must map to advice parameters of compatible types. For example, `@AfterReturning(pointcut = "execution(* example.PaymentService.find(..))", returning = "value", argNames = "value")` can pair with `afterFind(JoinPoint jp, String value)`; `jp` is omitted from `argNames` because `JoinPoint` comes first.

In Java, use explicit `argNames` when there are multiple bindings, or compile with `-parameters` to retain parameter names for Java reflection. Spring also has inference strategies in clear cases; do not treat legacy debug symbols as a guaranteed substitute. `ProceedingJoinPoint` is only for calling `proceed()` inside `@Around`, not in `@AfterReturning` or `@AfterThrowing`.

The dedicated section **`argNames`, parameter names, and compiler option `-parameters`** covers Maven/Gradle, named pointcuts, name discovery order, and resolving ambiguity. This lesson focuses specifically on **when result/error is bound by data type**, independent of name discovery.

## 6. How does parameter type restrict which calls are selected?

### 6.1. `String` vs. `Object` in `returning`

~~~java
// Observe only return values compatible with String.
@AfterReturning(
    pointcut = "execution(* example.CatalogService.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterString(String result) {
    // ...
}
~~~

A target method returning a compatible `String` is advised. A method returning `Integer` is not within a `String` binding's scope merely because both are `Object` in Java.

If you change the advice to:

~~~java
@AfterReturning(
    pointcut = "execution(* example.CatalogService.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterAnyResult(Object result) {
    // ...
}
~~~

then `Object` covers a broader range of results. From a Java reflection/Spring AOP perspective, primitive results are boxed at the boundary when passed to the advice. However, if your goal is to receive a callback for **every normal method completion including `void`**, use the `@AfterReturning` form **without declaring `returning`**, rather than trying to force a return value onto a method that has none.

**Avoid ambiguous assumptions about `null` or methods declared `Object` returning a runtime `String`:** static/dynamic matching semantics, declared types, and runtime values can depend on the matching mechanism. For important checks, test against a **real Spring context and real methods** rather than reasoning solely from source types.

### 6.2. `IllegalArgumentException` vs. `Throwable` in `throwing`

~~~java
@AfterThrowing(
    pointcut = "execution(* example.CatalogService.*(..))",
    throwing = "problem",
    argNames = "problem"
)
public void whenInvalidInput(IllegalArgumentException problem) {
    // ...
}
~~~

The scope is limited to exceptions compatible with `IllegalArgumentException`, including its subclasses. Conversely:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.CatalogService.*(..))",
    throwing = "problem",
    argNames = "problem"
)
public void whenAnyThrowable(Throwable problem) {
    // ...
}
~~~

`Throwable` covers throwables exiting matched methods. If a narrower scope is desired, use `Exception`, `RuntimeException`, or a custom exception type. Do not use `Throwable` just to log **every exception from every bean**; the expression should constrain package/operation scope appropriately.

**Specifically:** `throwing` **does not depend** on whether the method declares `throws IllegalArgumentException` in its signature. Unchecked runtime exceptions can still exit the method and be observed by Spring AOP if the invocation goes through the proxy and matches the pointcut and throwable type.

### 6.3. You cannot infer the outcome branch from callback name alone

An `@AfterReturning` callback does not run when a method throws; an `@AfterThrowing` callback does not run if the target catches the exception and returns. Do not write business logic assuming both callbacks always appear as a pair for every call. For any single invocation, normal exit and exceptional exit are distinct branches.

## 7. Combining `JoinPoint` with bound data

Example advice observing method signature and return value:

~~~java
@AfterReturning(
    pointcut = "execution(* example.InvoiceService.load(..))",
    returning = "invoice",
    argNames = "invoice"
)
public void recordLoadedInvoice(JoinPoint jp, Invoice invoice) {
    String operation = jp.getSignature().getName();
    // Log the operation name and an allowed identifier.
}
~~~

This is a **snippet**; `Invoice` and `InvoiceService` are illustrative domain types, not a standalone runnable project. It shows:

- `JoinPoint.getSignature()` provides the description of the advised method.
- The `invoice` value is the **bound return value**, not an element of `jp.getArgs()`.
- `jp.getArgs()` provides the **input arguments** of the invocation, not the returned result.
- `jp.getThis()` is the Spring AOP proxy and `jp.getTarget()` is the target object; they may not be the same object (especially with JDK proxies).
- Do not log the entire `invoice` object via `toString()` if it contains sensitive information.

Similar usage for errors:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.InvoiceService.load(..))",
    throwing = "failure",
    argNames = "failure"
)
public void recordFailure(JoinPoint jp, RuntimeException failure) {
    String operation = jp.getSignature().getName();
    String type = failure.getClass().getSimpleName();
    // Log the operation and exception type per policy.
}
~~~

Advice can inspect the error to categorize it, but **should not put full exception messages or stack traces into metric labels** or assume they are safe for public exposure.

## 8. When does a callback not run even with a valid expression?

In Spring AOP, having `@AfterReturning` or `@AfterThrowing` in source code is not enough to guarantee the callback runs. You need:

1. **The aspect bean registered in the Spring container.** `@Aspect` alone is not synonymous with `@Component`; `@Component` within component scan or `@Bean` is required.
2. **Active Spring AOP infrastructure.** Either `@EnableAspectJAutoProxy` in plain Spring Framework or Spring Boot's AOP auto-configuration when enabled.
3. **A pointcut matching the exact method execution** on the bean to be advised.
4. **The call actually passing through the Spring AOP proxy.**
5. **The outcome matching the annotation:** normal return for `@AfterReturning`, exception exit for `@AfterThrowing`.
6. **Value/exception type compatible** with the bound Java parameter.

Example:

~~~java
public String outer() {
    return this.find();
}
~~~

If `outer()` is called through the proxy, advice targeting `outer` can still run. However, `this.find()` inside the target does not go back through the proxy, so advice specifically for `find()` **is skipped for the internal call**. This applies to both JDK proxies and CGLIB proxies in Spring AOP.

**One special outcome to remember:** If `outer()` returns a `String` by calling `this.find()`, an `@AfterReturning` whose pointcut **also matches `outer`** can still receive `outer`'s `String`, **even though the internal `find` call was not advised separately**. The runnable example below demonstrates this exact scenario.

## 9. Complete Maven + Java 17+ example

### 9.1. Verification goals

The project uses **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, Java **17+**, and Maven. Scenarios:

- `find()` returns `String`: triggers `@AfterReturning` with a `String` parameter.
- `count()` returns `int`: does **not** trigger the `String`-returning advice.
- `ping()` is `void` and completes normally: triggers a **non-binding** `@AfterReturning` dedicated to that method.
- `failInput()` throws `IllegalArgumentException`: triggers `@AfterThrowing` bound to `IllegalArgumentException`.
- `failState()` throws `IllegalStateException`: does **not** trigger the `IllegalArgumentException`-restricted advice, yet triggers a `Throwable`-bound advice with its own pointcut.
- `recover()` catches `IllegalArgumentException` internally and returns `String`: triggers `String` after-returning, does **not** trigger after-throwing.
- `selfCall()` calls `this.find()`: the callback receives only **the result of `selfCall`** observed by the proxy, without an extra invocation for the inner `find`.

The advice methods do not alter return values, do not swallow exceptions, and never have two callbacks **of the same kind on the same join point**, preventing non-deterministic stdout ordering.

### 9.2. Structure

~~~text
spring-binding-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── DemoService.java
    ├── BindingAspect.java
    └── Main.java
~~~

### 9.3. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The BOM keeps Spring dependencies on consistent versions. In a real Spring Boot project, prefer Boot's starter/BOM rather than copying demo versions over dependencies managed by Boot.

### 9.4. `DemoService.java`

~~~java
package example;

public class DemoService {

    public String find() {
        System.out.println("target: find");
        return "FOUND";
    }

    public int count() {
        System.out.println("target: count");
        return 3;
    }

    public void ping() {
        System.out.println("target: ping");
    }

    public void failInput() {
        System.out.println("target: failInput");
        throw new IllegalArgumentException("invalid");
    }

    public void failState() {
        System.out.println("target: failState");
        throw new IllegalStateException("state");
    }

    public String recover() {
        System.out.println("target: recover begin");
        try {
            throw new IllegalArgumentException("invalid");
        } catch (IllegalArgumentException ignored) {
            System.out.println("target: handled invalid");
            return "RECOVERED";
        }
    }

    public String selfCall() {
        System.out.println("target: selfCall");
        return this.find();
    }
}
~~~

Key takeaway: `recover()` has an **internally caught** exception, so it returns normally. `selfCall()` uses `this.find()`, which does not create a new invocation through the Spring AOP proxy for `find`.

### 9.5. `BindingAspect.java`

~~~java
package example;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class BindingAspect {

    @AfterReturning(
        pointcut = "execution(* example.DemoService.*(..))",
        returning = "value",
        argNames = "value"
    )
    public void whenStringReturned(JoinPoint jp, String value) {
        System.out.println("returning String: "
            + jp.getSignature().getName() + " -> " + value);
    }

    @AfterReturning("execution(* example.DemoService.ping(..))")
    public void afterVoidPing() {
        System.out.println("returning ping: normal exit");
    }

    @AfterThrowing(
        pointcut = "execution(* example.DemoService.*(..))",
        throwing = "error",
        argNames = "error"
    )
    public void whenIllegalArgument(JoinPoint jp, IllegalArgumentException error) {
        System.out.println("throwing IAE: "
            + jp.getSignature().getName() + " -> " + error.getMessage());
    }

    @AfterThrowing(
        pointcut = "execution(* example.DemoService.failState(..))",
        throwing = "failure",
        argNames = "failure"
    )
    public void whenFailState(Throwable failure) {
        System.out.println("throwing Throwable: failState -> "
            + failure.getClass().getSimpleName());
    }
}
~~~

Points to verify:

- `whenStringReturned` has **matching names** `returning = "value"`, `String value`, and `argNames = "value"`.
- `whenIllegalArgument` has **matching names** `throwing = "error"`, `IllegalArgumentException error`, and `argNames = "error"`.
- `whenFailState` has `Throwable failure`, so it receives the `IllegalStateException` thrown by the target from `failState()`.
- `afterVoidPing()` binds no return value, so it can run after the `void` method completes normally.
- `JoinPoint` is the first parameter in two advice methods and does not need to be included in `argNames`.
- `@Aspect` does not register itself as a Spring bean; `AppConfig` declares a `@Bean` for `BindingAspect`.
- No advice alters a return value or exception into a different outcome.

### 9.6. `AppConfig.java`

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public DemoService demoService() {
        return new DemoService();
    }

    @Bean
    public BindingAspect bindingAspect() {
        return new BindingAspect();
    }
}
~~~

Spring AOP detects `BindingAspect` as an aspect bean, builds advisors for its annotated methods, and applies them to `DemoService`. `proxyTargetClass = true` uses a class-based CGLIB proxy so the demo retrieves the bean by `DemoService.class`. This does not cause self-invocation to trigger advice.

### 9.7. `Main.java`

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            DemoService service = context.getBean(DemoService.class);

            System.out.println("spring AOP proxy: " + AopUtils.isAopProxy(service));

            System.out.println("-- string return --");
            System.out.println("caller: " + service.find());

            System.out.println("-- primitive return --");
            System.out.println("caller: " + service.count());

            System.out.println("-- void normal return --");
            service.ping();

            System.out.println("-- illegal argument --");
            try {
                service.failInput();
            } catch (IllegalArgumentException e) {
                System.out.println("caller caught: " + e.getMessage());
            }

            System.out.println("-- other exception --");
            try {
                service.failState();
            } catch (IllegalStateException e) {
                System.out.println("caller caught: " + e.getMessage());
            }

            System.out.println("-- exception caught in target --");
            System.out.println("caller: " + service.recover());

            System.out.println("-- self invocation --");
            System.out.println("caller: " + service.selfCall());
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 9.8. Expected stdout

Lines printed by the example code itself in order, excluding configuration-dependent Maven/JVM logs:

~~~text
spring AOP proxy: true
-- string return --
target: find
returning String: find -> FOUND
caller: FOUND
-- primitive return --
target: count
caller: 3
-- void normal return --
target: ping
returning ping: normal exit
-- illegal argument --
target: failInput
throwing IAE: failInput -> invalid
caller caught: invalid
-- other exception --
target: failState
throwing Throwable: failState -> IllegalStateException
caller caught: state
-- exception caught in target --
target: recover begin
target: handled invalid
returning String: recover -> RECOVERED
caller: RECOVERED
-- self invocation --
target: selfCall
target: find
returning String: selfCall -> FOUND
caller: FOUND
~~~

**Why is the output deterministic?** Each case is designed so that only one advice **of the matching kind actually logs** per invocation, avoiding undefined ordering between two advice methods of the same kind matching the same join point. Specific generated proxy class names are not logged because JDK/Spring can vary generated names dynamically.

### 9.9. Reading each case's result

**1) `find()`:** the method returns `String "FOUND"`. The advice taking `String value` runs; the caller still receives `FOUND` because `@AfterReturning` does not replace the returned reference.

**2) `count()`:** the method returns primitive `int 3`. The return type is incompatible with `String`; no `returning String` line appears. The caller receives `3`.

**3) `ping()`:** the `void` method finishes normally; the `@AfterReturning` without `returning` dedicated to `ping` runs and prints `returning ping: normal exit`. There is no return value to bind.

**4) `failInput()`:** the target throws `IllegalArgumentException("invalid")` out. `@AfterThrowing` with `IllegalArgumentException error` is called. The caller still catches the original exception after the advice.

**5) `failState()`:** the target throws `IllegalStateException("state")`. The advice accepting only `IllegalArgumentException` **does not run** for this exception; the advice with `Throwable failure` and its own pointcut matching `failState` runs. The caller still catches `IllegalStateException`.

**6) `recover()`:** `IllegalArgumentException` is **caught inside the target method itself**, which then returns `String "RECOVERED"`. Spring AOP sees a normal return, so the `String`-bound advice runs; `@AfterThrowing` does not see the internally caught exception.

**7) `selfCall()`:** the caller invokes `selfCall` through the proxy. Inside the target, `this.find()` bypasses the proxy, yet `selfCall`'s result `FOUND` still returns through the proxy, so `@AfterReturning` prints **once** for `selfCall`. There is no separate returning line for the internal `find` method.

## 10. What if you want both arguments and result/error?

Spring AOP supports binding method arguments via `args(...)` combined with `returning` or `throwing`. Illustrative example for `lookup(String key)`:

~~~java
@AfterReturning(
    pointcut = "execution(* example.KeyService.lookup(..)) && args(key)",
    returning = "result",
    argNames = "key,result"
)
public void afterLookup(String key, String result) {
    System.out.println("lookup completed");
}
~~~

This is a **snippet**, not part of the demo project. Both `key` and `result` can be bound if the expression and signature match. `args(key)` binds the input argument; `returning = "result"` binds the **output** value.

Similarly:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.KeyService.lookup(..)) && args(key)",
    throwing = "failure",
    argNames = "key,failure"
)
public void afterLookupFailed(String key, RuntimeException failure) {
    System.out.println("lookup failed");
}
~~~

However:

- Do not put full `key` values, return objects, exception messages, or stack traces into logs if they contain secrets.
- The `String key` type restricts matches to invocations with a compatible argument.
- `String result` and `RuntimeException failure` further constrain the bound result/exception.
- When overloads, generics, or interfaces exist, test bindings against a **real context**, rather than guessing from method names alone.
- If `JoinPoint` leads the signature, `JoinPoint`'s name may be omitted from `argNames`.

## 11. Why is `@AfterReturning` not used to change the result?

Misguided example:

~~~java
// The advice method may execute, yet a String from this method
// does NOT become a replacement return value for the caller.
@AfterReturning(
    pointcut = "execution(* example.DemoService.find(..))",
    returning = "value",
    argNames = "value"
)
public void changeResult(String value) {
    value = "OVERRIDDEN";
}
~~~

Reassigning the local variable `value` does not change what the caller receives. If you genuinely must alter a result under an explicit policy, consider `@Around`:

~~~java
@Around("execution(* example.DemoService.find(..))")
public Object transform(ProceedingJoinPoint pjp) throws Throwable {
    Object original = pjp.proceed();
    return transformUnderBusinessContract(original);
}
~~~

This is an **illustrative snippet**; `transformUnderBusinessContract(...)` must be defined by the application. Using `@Around` with a replacement `return` can alter the contract and should not be used just for auditing or logging.

Note: if `@AfterReturning` receives a **mutable object**, calling a mutating method on that object can produce an observable change for the caller even without changing the reference. That is still a **mutation side effect** and may violate a "read-only observation advice" requirement.

## 12. Why is `@AfterThrowing` not a global `catch`?

An advice like:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.DemoService.failInput(..))",
    throwing = "error",
    argNames = "error"
)
public void logError(IllegalArgumentException error) {
    System.out.println("invalid input");
}
~~~

does not turn throwing an exception into a normal return. When the advice returns `void`, the original exception keeps propagating. It only observes **exceptions exiting matched method executions**.

If the advice itself throws a new exception, that exception can **replace the exception the caller sees**. Do not throw a new error from logging/metrics logic just because a log backend is unavailable. If you want to actively catch, translate, or provide a fallback, design it at the appropriate handling layer or use `@Around` with a clear `try/catch` and return contract.

**An exception not seen by advice** does not mean no exception occurred: the target may have caught it internally, an inner interceptor may have handled it and returned a fallback, or the caller may not have gone through the Spring AOP proxy.

## 13. Specific limitations of Spring AOP proxies

### 13.1. JDK proxy and CGLIB

- **JDK dynamic proxy**: interface-based; callers should inject via the exposed interface.
- **CGLIB class-based proxy**: subclasses the target; cannot proxy `final` classes, and `final`/`private` methods are not advised via overriding.
- **Both** share the self-invocation limitation in Spring AOP. Switching to CGLIB does not make `this.method()` go through the proxy.

### 13.2. Aspect bean must be a Spring bean

An `@Aspect` class can be registered with `@Component` under component scan, or returned from a `@Bean` method. If the aspect exists merely as a class on the classpath, Spring has no obligation to pick up its advice.

In plain Spring Framework, `@EnableAspectJAutoProxy` is the standard setup. In Spring Boot, AOP auto-configuration can supply this infrastructure depending on dependencies and settings; an actual aspect bean is still required.

### 13.3. Methods bypassing the proxy

- `new DemoService().find()` outside the container receives no Spring advice.
- `this.find()` inside the target creates no additional invocation through the proxy.
- Extracting the underlying target from `Advised.getTargetSource()` and calling it directly can bypass advice.
- An outer around interceptor returning early without `proceed()` can prevent the call from reaching inner advice.

### 13.4. Async/reactive results

If a method returns a `CompletableFuture` or a reactive publisher, `@AfterReturning` can run when **the method returns the Future/Publisher object**, which does not mean the async work or pipeline has finished. `@AfterThrowing` at the method boundary does not automatically catch errors emitted **later** inside the future or stream.

Track completion via Future callbacks/lifecycle hooks or appropriate reactive operators when you want to observe the final async outcome; do not treat `returning` as a mechanism that awaits future completion.

## 14. Common errors and diagnostic methods

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Spring reports parameter-name binding error | `returning`/`throwing` does not match parameter name, wrong `argNames`, or missing name metadata | Compare annotation attributes and Java parameter names; use `argNames` or compile with `-parameters` |
| `@AfterReturning` does not run for an `int` method | Advice takes `String`; incompatible type | Change type if business goal allows, or use a different pointcut |
| `void` method does not trigger advice with specific `returning` | No return value to bind | Use non-binding `@AfterReturning` for normal completion |
| `@AfterThrowing(IllegalArgumentException)` does not run for `IllegalStateException` | Typed `throwing` binding restricts throwables | Choose matching type or `Throwable` if broad coverage is needed |
| `@AfterThrowing` advice misses an error that was caught | Target returned normally | Check which exception actually exits the method |
| Exception still reaches caller after `@AfterThrowing` | This is normal behavior | If handling/translation is needed, design separately; do not treat after-throwing as `catch` |
| Bean has a proxy yet method runs no advice | Pointcut/`returning`/`throwing` does not match, or advisor comes from another feature | Inspect eligible advisors and method signature |
| Advice runs on direct service call but not inside `this.method()` | Self-invocation does not pass through proxy | Extract the advised method to another Spring bean when appropriate |
| JDK proxy cannot be cast to implementation | Runtime proxy type is interface-based | Inject the interface or verify whether class-based proxying is usable |
| Using `JoinPoint.getArgs()` to find return value | `getArgs()` holds **input arguments** | Use `returning` to receive the return value |
| Reassigning bound `String` value has no effect on caller | `@AfterReturning` does not replace the reference | If result transformation is needed, consider controlled `@Around` |
| Advice has two bound parameters but `argNames` lists only one | Missing or ambiguous binding | List all bound variable names and verify leading `JoinPoint` |
| Sensitive exception details leaked in logs | Printing messages/stack traces or objects without policy | Restrict data, normalize labels, and govern logging |
| Advice runs in unexpected order | Multiple advisors/aspects, `@Order`/infrastructure order | Check precedence and write specific integration tests |

### Quick checklist

1. **Is the target a Spring bean?** Retrieve via context or dependency injection.
2. **Is the aspect a bean?** Check `@Component` scan or `@Bean` and AOP setup.
3. **Is the pointcut right?** Check package, class, method, visibility, JDK/CGLIB.
4. **Are binding names right?** `returning="value"` ↔ `value`, `throwing="error"` ↔ `error`.
5. **Are binding types right?** `String`, `Integer`, `Object`, `IllegalArgumentException`, `Throwable`.
6. **Is it the right branch?** Normal return vs. exceptional exit; was the exception caught inside the target?
7. **Does the call go through the proxy?** No `new` or self-invocation.
8. **Are there infrastructure advisors or around shortcuts?** Inspect the interceptor chain.
9. **Test negative cases?** `void` methods, different return types, different exception types, internal catches.
10. **Preserve the business contract?** Advice does not alter return references, mask exceptions, or log sensitive data.

## 15. Practice exercises

**Scenario A.** An aspect uses `@AfterReturning(returning="result")` and `public void audit(String result)`; the method returns `Integer`. Will the advice definitely run?

**Answer:** No. Typed `String` binding restricts matches to `String`-compatible results; `Integer` is not compatible with `String`.

**Scenario B.** `@AfterThrowing(throwing="failure")` binds `IllegalArgumentException failure`, but the method throws `IllegalStateException`. Does the advice run?

**Answer:** No, unless another compatible exception occurs. Both are `RuntimeException`, yet neither is a subtype of the other.

**Scenario C.** A method throws `IllegalArgumentException`, catches it immediately inside, and returns `"RECOVERED"`. Which branch does Spring AOP see?

**Answer:** Normal return. A type-compatible `@AfterReturning` will run; `@AfterThrowing` does not receive an exception already caught by the target.

**Scenario D.** The advice method parameter is named `value`, while the annotation specifies `returning="result"` and `argNames="value"`. Is this valid?

**Answer:** No. The `returning` name must match the parameter's binding name; declare them consistently.

**Scenario E.** An `@AfterReturning` without `returning` is configured specifically for a `void ping()` method that returns normally. Does it run?

**Answer:** Yes, when the pointcut matches, the Spring AOP proxy receives the invocation, and the method finishes normally. No return value binding is required.

**Scenario F.** A method `selfCall()` returns `String` and internally calls `this.find()`. A `String`-bound aspect matches both methods. The caller invokes `selfCall()` on the proxy. How many invocations pass through the proxy?

**Answer:** One invocation, for `selfCall()`. The internal `find()` is bypassed, yet `selfCall()`'s returned `String` can still be received by the advice.

**Scenario G.** `@AfterThrowing` logs an error and returns `void`. Has it "handled the exception" so the caller does not see the error?

**Answer:** No. After the advice, the original exception still propagates unless another layer actively handles it.

**Scenario H.** An `@Aspect` class has valid advice methods but is not registered as a Spring bean. Will all methods with matching signatures be advised?

**Answer:** No. Spring AOP needs an aspect bean to detect advisors; the annotation on the class alone is not enough.

**Scenario I.** `@AfterReturning` receives `String result` and assigns `result = "new"`. Does the caller receive the new string?

**Answer:** No. Reassigning a local variable in advice does not replace the reference returned by the method. To transform return values, consider `@Around`.

## 16. Official Spring documentation

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): explains `@AfterReturning` and `@AfterThrowing` with `returning`, `throwing`, typed binding, naming, `JoinPoint`, and advice ordering.
- [Spring Framework — Determining Argument Names](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html#_determining_argument_names): `argNames`, Java `-parameters`, and parameter-name discovery mechanisms.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): registering aspect beans and enabling `@EnableAspectJAutoProxy`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxy boundaries and self-invocation.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): pointcut syntax supported by Spring.
- [Spring Framework — Spring AOP Concepts](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-defn.html): normal and exceptional exits at the method join point level.
