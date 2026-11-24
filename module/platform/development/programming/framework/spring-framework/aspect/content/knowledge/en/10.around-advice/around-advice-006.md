# Spring AOP `@Around`: Preserving Return Values and Target Method Data Types

## 1. The Problem: The Method Runs Correctly, Yet the Caller Receives the Wrong Result

In **proxy-based Spring AOP**, `@Around` is the advice type capable of wrapping a method call on a Spring-managed bean. The advice decides whether to call `ProceedingJoinPoint.proceed()`, and **the value returned by the advice becomes the final value seen by the caller**, provided that value is compatible with the method contract.

An easy mistake to make:

```java
@Around("execution(* demo.returns.PricingService.label(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    System.out.println("result = " + result);
    return null; // WRONG: loses the value the target method just returned.
}
```

The target may have returned `"LABEL-A1"`, yet the caller receives `null`. A single `return null` inside the advice is enough to change the API's meaning, even though the target's code never changed.

The safe default when you only need timing, logging, or telemetry:

```java
@Around("execution(* demo.returns.PricingService.label(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    System.out.println("result = " + result);
    return result; // Preserve the target method's result.
}
```

Both snippets above are **illustrative fragments**, not standalone runnable files. In a real example, you need `@Aspect`, the aspect registered as a Spring bean, AOP infrastructure, and a Spring-managed target bean.

**The single most important rule:** in an observation-only `@Around` advice, use `return pjp.proceed()` or store the result in a variable and then `return result`. Never alter the result unless the requirement explicitly calls for changing the contract.

This lesson focuses strictly on **Spring Aspect / Spring AOP proxies** and the boundaries for preserving method types and results. It is not a general introduction to AOP or AspectJ bytecode weaving.

## 2. Which Path Does the Return Value Take?

```text
Caller
  |
  | PricingOperations.priceInCents(3)
  v
Spring AOP proxy (JDK or CGLIB)
  |
  | pointcut match
  v
@Around advice
  |
  | Object value = pjp.proceed()
  v
Remaining interceptors / target.priceInCents(3)
  |
  | int 450
  v
proceed() returns Integer(450) due to boxing in the Object API
  |
  | advice returns that exact value
  v
Spring AOP proxy checks/returns the type per method contract
  |
  v
Caller sees int 450
```

Key points to understand accurately:

1. `ProceedingJoinPoint.proceed()` has a Java return type of `Object` in order to support all kinds of target methods.
2. The return type **in the target method signature** remains the contract the caller uses, such as `String`, `int`, `void`, `Optional<String>`, or `List<String>`.
3. If the target returns a primitive such as `int`, the value is represented as a wrapper `Integer` in the `Object` result. The proxy must pass a compatible value back to the caller.
4. For `void`, `proceed()` normally returns `null`; the caller does not consume a return value. That does **not** mean you should return `null` for **every** method.
5. Returning an object of the wrong type can fail at runtime; the fact that the target method finished running does not guarantee the caller receives the right value.
6. If the target throws an exception, `proceed()` throws that exception and returns no value. The advice must propagate it or handle it intentionally; never accidentally swallow errors with a `finally return`.

### Why Does Spring Recommend That the Advice Method Return `Object`?

The Spring Framework documentation on `@Around` clearly states that the advice method should return `Object` and its first parameter must be `ProceedingJoinPoint`. If **the advice method itself is declared with return type `void`**, Spring passes **`null`** back to the caller, discarding the real result of `proceed()`. Therefore, `void` on the advice method is a serious trap when the pointcut applies to non-void methods.

**Correct:**

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object preserveResult(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

**Wrong when applied to a non-void target:**

```java
@Around("execution(* demo.returns..*Service.*(..))")
public void discardResult(ProceedingJoinPoint pjp) throws Throwable {
    pjp.proceed(); // Target method runs, yet its result is not passed back to the caller.
}
```

An `@Around` advice targeting methods with return types like `String`, `int`, or `List` while declaring `void` on the advice itself can cause the caller to receive `null` or trigger type-compatibility errors. Always declare `Object` and return the value per contract.

## 3. Matrix of Important Return Types

| Target signature | `proceed()` returns via `Object` | Value advice should return when not transforming | If advice returns the wrong value |
| --- | --- | --- | --- |
| `String label()` | `String` or `null` | Exact original `String` | Returning `Integer`: wrong type; `null` may violate business rules |
| `int total()` | Boxed `Integer` | Exact `Integer` from proceed | `null` cannot unbox to `int`; `"42"` is not an `int` |
| `long amount()` | Boxed `Long` | `Long` | `Integer` does not become `Long` merely because values look equivalent |
| `boolean allowed()` | Boxed `Boolean` | `Boolean` | `null` or `"true"` is incompatible |
| `void notifyUser()` | Normally `null` | `null` from `proceed()` | Never depend on a return value from a void method |
| `Optional<String> find()` | `Optional<String>` | Same `Optional` | `null` differs from `Optional.empty()`; `String` violates contract |
| `List<String> list()` | `List<String>` at object level | Same `List` | Returning `Set` breaks API; wrong generic element fails later |
| `CompletableFuture<String> loadAsync()` | `CompletableFuture<String>` | Same future | Returning `String` directly breaks the method contract |
| `Mono<String> stream()` if using Reactor | `Mono<String>` publisher | Same publisher | Returning payload `String` instead of publisher is invalid |

In the table, method names are illustrative only; asynchronous/reactive APIs apply only when those dependencies are in use. Not every error kind throws the exact same exception across all proxy implementations: **`ClassCastException`**, unboxing exceptions, or **Spring's `AopInvocationException`** may occur depending on the mismatch site/type. What matters is that **the final returned type must be compatible**.

### 3.1. Reference Types and Nullability

`String`, domain DTOs, and reference types can return `null` at the Java language level, yet a business API may forbid null. Returning `null` because the advice forgot `return result` **breaks the contract** even if it does not throw an exception immediately.

When the target returns `Optional.empty()`, the advice must preserve an **empty `Optional`**, not replace it with `null`. Callers reasonably invoke `result.isPresent()` without null-checking because the `Optional` contract expects an `Optional` object.

### 3.2. Primitives and Boxed Types

```java
public int calculate() {
    return 450;
}
```

Inside the advice:

```java
Object result = pjp.proceed(); // Typically Integer(450).
return result;                  // Spring returns int 450 to the caller.
```

These are fragments. If changed to `return null;`, `int` has no null value. Spring AOP may raise an exception on a null return for a primitive method. If changed to `return "450";`, a string is not an `Integer` compatible with primitive `int`; Java does not auto-parse strings.

Avoid hardcoding `return 0` in place of the target's value just to prevent caller crashes: that can silently replace real data with an incorrect result.

### 3.3. `void` Has Its Own Characteristics

```java
public void announce(String id) {
    System.out.println("announce " + id);
}
```

The advice should still be written consistently:

```java
@Around("execution(* demo.returns.PricingService.announce(..))")
public Object preserveVoid(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed(); // For void: the result is null.
    return result;                 // Valid for a void method.
}
```

An `Object`-returning advice can apply to both `void` and non-`void` methods. **Do not** write `return "DONE"` just to report success to the caller: a `void` method has no return value under its Java interface. Work outcomes should be reflected through side effects or an explicitly designed domain API.

## 4. Common `@Around` Return Mistakes

### 4.1. Forgetting `return result`

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object broken(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    logResult(result);
    return null; // Wrong for any non-void method needing a value.
}
```

This is a fragment with a hypothetical `logResult`. The bug is not necessarily in the target; you must inspect the stack trace and aspect chain to spot that the advice **overwrote** the return value.

### 4.2. Using `finally` to `return`

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object veryDangerous(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } finally {
        return null; // Wrong: overrides both valid return values and target exceptions.
    }
}
```

In Java, a `return` in `finally` **overrides** the `try` block's return and **swallows exceptions**. This is an especially dangerous bug for transactions and security checks.

Use `finally` only for cleanup/logging:

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object safeCleanup(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } finally {
        clearTemporaryContext();
    }
}
```

Here `clearTemporaryContext()` is a hypothetical fragment; if cleanup itself throws an exception, it can still mask the prior error or return value. Cleanup code should be designed not to accidentally alter the business outcome.

### 4.3. Using the Wrong Advice Type

```java
@AfterReturning(
    pointcut = "execution(* demo.returns.PricingService.label(..))",
    returning = "value"
)
public String tryReplace(String value) {
    return "NEW-" + value;
}
```

This fragment illustrates a **semantically wrong idea**: Spring's `@AfterReturning` can bind the return value for observation, yet it does not use this advice method's return value to replace the reference the caller receives. If the goal is to replace the return value, use `@Around` with the proper contract. In practice, `@AfterReturning` should return `void` when only logging or collecting metrics.

### 4.4. Casting a Value Not Guaranteed by `proceed()`

```java
Object result = pjp.proceed();
String text = (String) result; // Wrong if the pointcut also matches int/List/void.
return text;
```

With a broad pointcut, targets may have return types other than `String`. Do not hard-cast unless the pointcut expression and method signature guarantee it. The safest default is to **directly return the result of `proceed()`**.

### 4.5. Calling `proceed()` Twice Unintentionally

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object duplicateCall(ProceedingJoinPoint pjp) throws Throwable {
    Object first = pjp.proceed();
    pjp.proceed(); // Calls target a second time if the chain allows.
    return first;
}
```

In Spring AOP, `proceed()` can be called multiple times; however, for a method that writes data, sends emails, or processes payments, the second call can produce **duplicate side effects**. An advice that only measures/logs results must call `proceed()` **once**, never inadvertently doubling the operation.

### 4.6. Using `return null` to "Skip" Execution

`@Around` may intentionally **omit `proceed()`**, such as on a cache hit. Yet if the target call is skipped, the advice must return **a value compatible with the method**:

```java
@Around("execution(* demo.returns.PricingService.label(..))")
public Object cacheHit(ProceedingJoinPoint pjp) throws Throwable {
    String cached = lookupCache(pjp.getArgs()[0]); // Fragment, hypothetical helper.
    if (cached != null) {
        return cached; // Right String type; must ensure valid semantics.
    }
    return pjp.proceed();
}
```

Skipping the target is not automatically safe with `@Transactional`, logging, authorization, or side effects inside the method. Caching fits only operations whose contract permits reusing results; the policy must handle cache keys, invalidation, and sensitive data.

## 5. Transform Return Values Only When Explicitly Required

An `@Around` advice has the authority to wrap or replace a return value. Yet this is **intentional** behavior, never a side effect of tracing advice.

### 5.1. Transforming a String Into a String

```java
@Around("execution(String demo.returns.PricingService.label(..))")
public Object uppercaseLabel(ProceedingJoinPoint pjp) throws Throwable {
    String result = (String) pjp.proceed();
    return result.toUpperCase(java.util.Locale.ROOT);
}
```

This is a fragment where the pointcut restricts the return type to `String`. If the business contract allows transforming the string, the caller still gets a valid `String`. However, preserving the **right type** does not guarantee preserving the **right value/semantics**; write tests confirming that is the expected outcome.

### 5.2. Fallbacks Must Match the Type When Catching Exceptions

```java
@Around("execution(* demo.returns.PricingService.maybeLookup(..))")
public Object fallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return java.util.Optional.empty();
    }
}
```

If the target has an `Optional<String>` contract, returning `Optional.empty()` is valid. Returning `null` or `"NOT_FOUND"` breaks the API. For `int calculate()`, a type-valid fallback is an `Integer` matching `int`, yet **choosing the fallback number** must make business sense; never silently return `0` if that is a wrong answer.

### 5.3. Do Not Lose Object Identity When Only Observing

If a service returns a mutable domain object, `return result` preserves **the exact same reference**. Returning a newly created DTO or copy can break identity, lazy relations, entity proxies, or state expected by the caller, even when field values look identical.

A logging advice **must not** map the result to a String or JSON and accidentally return that String instead of the business object. If you need to serialize for logging, serialize into a separate variable and still `return result`.

### 5.4. Generic Return Types

Suppose a method returns `List<String>`. At runtime, Java generics undergo type erasure; a raw `List<Integer>` can pass a `List` cast and then fail later when the caller reads an element as a `String`. Therefore, checking only `result instanceof List` does not guarantee preserving the **generic contract**. The safe choice for cross-cutting advice is to pass the exact object returned by `proceed()` without altering collection contents.

For `Optional<User>`, `ResponseEntity<DTO>`, `Page<T>`, or wrappers with metadata, keep both the wrapper and its contents intact unless a specific policy requires a type-safe transformation.

## 6. Complete Example: One `@Around` Preserving Multiple Return Types

The following project uses **Java 17, Spring Framework 6.2.x, and Maven** without Spring Boot. A single advice matches several methods with different return types, calls `proceed()` exactly once, and returns the exact object. The example verifies:

- `String` does not become null.
- `int` stays an `int` to the caller even though `proceed()` returns a boxed `Integer`.
- A `void` method still executes its side effects; `proceed()` produces null.
- `Optional.empty()` remains an `Optional` object, not replaced by null.
- `List<String>` is not mapped to a different object type.
- The proxy ensures Spring manages both target and aspect; consumers retrieve the bean from the context.

### 6.1. Project Structure

```text
spring-around-return-values/
├── pom.xml
└── src/main/java/demo/returns/
    ├── AppConfig.java
    ├── PricingOperations.java
    ├── PricingService.java
    ├── ReturnTraceAspect.java
    └── Main.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-around-return-values</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. `AppConfig.java`

```java
package demo.returns;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` discovers `@Service` and `@Aspect @Component` in the package. `@EnableAspectJAutoProxy` enables proxying. Because the target implements an interface and `proxyTargetClass=false`, plain Spring Framework uses a JDK interface proxy in this example.

### 6.4. `PricingOperations.java`

```java
package demo.returns;

import java.util.List;
import java.util.Optional;

public interface PricingOperations {
    String label(String id);
    int priceInCents(int quantity);
    void announce(String id);
    Optional<String> maybeLookup(String id);
    List<String> codes();
}
```

The methods are declared on the interface so callers holding the JDK proxy can invoke them. Each method returns a different type, matching our focus on `@Around` return preservation.

### 6.5. `PricingService.java`

```java
package demo.returns;

import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class PricingService implements PricingOperations {
    @Override
    public String label(String id) {
        System.out.println("[target] label " + id);
        return "LABEL-" + id;
    }

    @Override
    public int priceInCents(int quantity) {
        System.out.println("[target] priceInCents " + quantity);
        return quantity * 150;
    }

    @Override
    public void announce(String id) {
        System.out.println("[target] announce " + id);
    }

    @Override
    public Optional<String> maybeLookup(String id) {
        System.out.println("[target] maybeLookup " + id);
        return "NONE".equals(id)
                ? Optional.empty()
                : Optional.of("SKU-" + id);
    }

    @Override
    public List<String> codes() {
        System.out.println("[target] codes");
        return List.of("A", "B");
    }
}
```

The service contains no advice logic and creates no proxy itself. Spring registers the bean via `@Service` and component scanning.

### 6.6. `ReturnTraceAspect.java`

```java
package demo.returns;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ReturnTraceAspect {
    @Around("execution(* demo.returns.PricingService.*(..))")
    public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
        String name = pjp.getSignature().getName();
        System.out.println("[around] enter " + name);

        Object result = pjp.proceed();

        String display = result == null ? "<null>" : result.toString();
        System.out.println("[around] exit " + name + " -> " + display);

        return result; // Intentionally preserves both return value and object identity.
    }
}
```

`@Aspect` marks the aspect, `@Component` registers it as a Spring bean, and `@Around` matches methods on `PricingService`. The advice uses `Object` so results are not forced to `String`. It **does not return `display`**, using `display` solely for printing logs. For the `null` result of a `void` method, `<null>` is logged and `return result` is valid.

This is a type-observation demo, not a production logging recipe: calling `result.toString()` on sensitive, lazy-loaded, or expensive objects can cause side effects or data leaks. In real systems, log method names and safe metadata rather than full values.

### 6.7. `Main.java`

```java
package demo.returns;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            PricingOperations port = context.getBean(PricingOperations.class);

            System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(port));
            System.out.println("[caller] label=" + port.label("A1"));
            System.out.println("[caller] price=" + port.priceInCents(3));
            port.announce("B1");
            System.out.println("[caller] lookup=" + port.maybeLookup("NONE"));
            System.out.println("[caller] codes=" + port.codes());
        }
    }
}
```

From the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.returns.Main
```

**Deterministic stdout from the example's `System.out` statements** (excluding Maven/Spring logs if any):

```text
jdkProxy=true
[around] enter label
[target] label A1
[around] exit label -> LABEL-A1
[caller] label=LABEL-A1
[around] enter priceInCents
[target] priceInCents 3
[around] exit priceInCents -> 450
[caller] price=450
[around] enter announce
[target] announce B1
[around] exit announce -> <null>
[around] enter maybeLookup
[target] maybeLookup NONE
[around] exit maybeLookup -> Optional.empty
[caller] lookup=Optional.empty
[around] enter codes
[target] codes
[around] exit codes -> [A, B]
[caller] codes=[A, B]
```

### 6.8. Why Does the Output Follow This Exact Order?

1. The context retrieves the Spring-managed `PricingOperations` bean; the aspect matches the service and a JDK proxy fits the interface, so `jdkProxy=true`.
2. `port.label("A1")` goes through the advice: prints `enter`, target returns `"LABEL-A1"`, advice prints `exit` and **returns the exact String**, and caller prints the right value.
3. `port.priceInCents(3)`: target returns primitive `int 450`; via `proceed()`'s `Object` it is boxed to `Integer(450)`, returned by the advice, and the caller receives `int 450`.
4. `port.announce("B1")`: target is `void`, so `proceed()` yields `null`; advice logs `<null>` and caller receives no business return.
5. `port.maybeLookup("NONE")`: target returns `Optional.empty()`; advice preserves the `Optional` rather than null.
6. `port.codes()`: target returns `List.of("A","B")`, advice preserves the `List`; the List's `toString()` yields `[A, B]`.
7. The advice does not call `proceed()` multiple times, does not alter values, and does not perform contract-breaking error recovery.

## 7. Checking Return Types When Intentionally Transforming Data

If business requirements **allow** an `@Around` advice to alter the value, base it on the target method's actual return type. From `ProceedingJoinPoint.getSignature()` you can inspect method details; Spring provides helpers to resolve methods/target methods for JDK proxies and bridge methods.

A basic check for method execution:

```java
MethodSignature signature = (MethodSignature) pjp.getSignature();
Class<?> returnType = signature.getReturnType();
System.out.println("Declared return type: " + returnType.getName());
```

This is a fragment inside `@Around` requiring `import org.aspectj.lang.reflect.MethodSignature`. It reads the **declared** return type, though it is not complete validation of generics, nullability, custom serialization, transaction state, or object identity.

### 7.1. Primitive-Returning Methods

```java
if (returnType == int.class && result == null) {
    throw new IllegalStateException("Null result for primitive int");
}
```

This fragment catches an obvious error, yet a proxy framework may already throw its own exception when advice returns null for a primitive. **Do not** assign a `0` fallback merely to turn a failure into a success.

### 7.2. Optional-Returning Methods

```java
Object result = pjp.proceed();
if (result instanceof java.util.Optional<?> optional) {
    System.out.println("present=" + optional.isPresent());
}
return result;
```

Do not unwrap `Optional` and return a `String`: the caller expects `Optional<String>`. If a fallback is needed, return `Optional.empty()` or a contract-compliant `Optional`, never null.

### 7.3. Argument Replacement Cases

Spring supports `pjp.proceed(Object[] args)`. In Spring AOP, the new array must **match the count, positions, and compatible types of the target method's parameters**:

```java
Object[] original = pjp.getArgs();
Object[] replacement = original.clone();
replacement[0] = "NORMALIZED";
return pjp.proceed(replacement);
```

This fragment suits only methods whose first argument is a `String`. Changing inputs must not alter the return contract; the method still returns/throws per its signature. Never pass `proceed(new Object[0])` to a method expecting parameters, and do not assume replacing args automatically guarantees a valid return type.

### 7.4. Future/Reactive Return Types

If a method returns `CompletableFuture<String>`, `proceed()` may return an **incomplete** future. A synchronously running `@Around` does not yet hold the future's `String` payload; returning `"ready"` instead of the future violates the return type.

When transforming asynchronous results is needed, you can use:

```java
Object result = pjp.proceed();
if (result instanceof java.util.concurrent.CompletableFuture<?> future) {
    return future.thenApply(value -> value); // Preserve the Future wrapper.
}
return result;
```

This is an illustrative fragment, not a universal solution for all futures/generics; for `CompletableFuture<T>`, transformations must preserve `T` and completion/error semantics. For Reactor `Mono<T>`/`Flux<T>`, use matching operators and types rather than returning raw payloads instead of the publisher.

## 8. Exceptions and Return Values: You Cannot Preserve Them Mechanically

An advice can preserve normal return values while ensuring exceptions **are not swallowed**:

```java
@Around("execution(* demo.returns..*Service.*(..))")
public Object preserveOutcome(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        System.out.println("elapsed ns=" + elapsed);
    }
}
```

This advice does not supply a fallback when the target throws an exception. `throws Throwable` allows exceptions from `proceed()` to propagate onward. Note that `System.nanoTime()` is only for measuring relative elapsed time, not wall-clock timestamps.

If recovery is desired:

```java
@Around("execution(* demo.returns.PricingService.maybeLookup(..))")
public Object recoverOptional(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return java.util.Optional.empty();
    }
}
```

This is an **intentional outcome-changing** decision, appropriate only when the business API permits converting that specific error into a not-found state. Never catch `Throwable` and return null on a broad pointcut: it can hide critical failures, turn exceptions into invalid results, and corrupt transactions.

### 8.1. Right Return Type, Wrong Transaction State

Spring's `@Transactional` typically uses another advisor/interceptor. An `@Around` sitting outside the transaction interceptor can catch an exception after the transaction has already been marked rollback-only. Returning a "success" DTO from the outer advice does not clear rollback-only status. Therefore, **having the right return type is not enough** to guarantee the transaction commits.

### 8.2. Retries Can Produce a Final Return Different From the First

Calling `proceed()` two or more times to retry is a separate business concern, not logging. Which execution's result goes to the caller, whether side effects repeat, and how final exceptions propagate must all be explicitly defined. Consider retries only for idempotent methods; transaction boundaries, timeouts, and logging must be tested.

### 8.3. Other Advice May Transform the Return Before You

The interceptor chain may contain caching, security, transactions, async proxies, or multiple `@Around` advices. `pjp.proceed()` returns the result of **the rest of the chain**, not always "the raw unmodified return directly from target code." If an inner interceptor proactively returns a cached value, the outer advice receives that cached value too. Always check actual ordering/chain behavior when observed results differ from running the target method standalone.

## 9. JDK Proxies, CGLIB, and Invocation Boundaries

Preserving return values in `@Around` matters only when the advice is actually invoked.

- **JDK dynamic proxy:** callers invoke public methods on the interface implemented by the proxy. If the implementation has additional methods not on the interface, a JDK proxy does not expose them.
- **CGLIB class-based proxy:** can intercept methods that a generated subclass proxy can override; cannot override `final` or `private` methods; cannot subclass a `final class`.
- **Self-invocation:** `this.someMethod()` inside the target bypasses the proxy, even for public methods; advice matching that method does not run on internal calls.
- **Objects created with `new` outside the container:** receive no Spring AOP proxy; advice never triggers.
- **Non-matching pointcut:** the method runs normally, yet `@Around` is not applied.
- **Aspect not registered as a bean:** `@Aspect` alone does not cause Spring component scanning to register it; `@Component` or `@Bean` is required.

Never flip `proxyTargetClass=true` just to work around a `return null` bug in advice; proxy type does not replace `@Around`'s duty to return the proper value.

## 10. Diagnostic Checklist When Post-Aspect Values Are Wrong

| Symptom | Typical cause | Fix |
| --- | --- | --- |
| Target prints right result, caller gets null | Around advice forgot `return result` or declared `void` | Return `Object` + `return pjp.proceed()` or `return result` |
| `int` method errors after advice returns null | Primitives cannot hold null | Return the boxed value from `proceed()` |
| `String`-returning method hits type error | Advice returned a different type, e.g., `Integer` | Narrow pointcut or preserve original value |
| Caller of `Optional<String>` hits NPE | Advice replaced `Optional.empty()` with null | Preserve the `Optional` object |
| Generic List throws `ClassCastException` on element read | Advice replaced List contents with wrong generic type | Avoid altering collections unless permitted by contract |
| `void` method prints no return value | Normal Java `void` behavior | Log side effects inside advice; do not expect a return |
| Target runs twice | Advice called `proceed()` twice | Default to calling once |
| Exception disappears | Overly broad `catch` or `return` inside `finally` | Propagate exceptions; never return inside finally |
| Caching advice returns wrong DTO | Cache holds an object incompatible with method contract | Design cache keys/types and validate before returning |
| Returned `String` instead of `CompletableFuture<String>` | Confused payload with wrapper | Preserve future/publisher and transform via its API |
| Right type yet caller sees stale/wrong state | Logging advice copied or mutated object | Preserve reference/immutability policy |
| Failures appear only after adding logging | `result.toString()` had side effects or threw | Log safe metadata; never let logging break flow |
| `@Around` does not run on internal method | Self-invocation bypassed Spring proxy | Call through another DI-injected Spring bean |
| Advice runs in wrong order relative to transaction/cache | Advisor ordering and nested chain | Test chain and configure precedence |
| Target throws exception yet advice returns "success" | Advice caught and swallowed error | Use fallbacks only when business-approved |
| Some methods receive no advice | Pointcut, proxy type, or aspect bean registration | Inspect Spring context, method visibility, proxy type |

**Systematic review workflow:**

1. Verify target and aspect are Spring beans and Spring AOP infrastructure is enabled.
2. On the actual reference injected by DI or retrieved from the context, check `AopUtils.isAopProxy(bean)` and identify JDK vs. CGLIB proxy.
3. Verify the pointcut selects the right method and callers go through the proxy.
4. Inspect the target signature: return type, primitive vs. reference, nullability, wrappers/generics, exceptions.
5. Check that the advice declares `Object`, how many times it calls `proceed()`, and whether every branch performs `return result` properly.
6. Inspect `catch`/`finally` branches; avoid returning inside `finally` and avoid swallowing exceptions outside policy.
7. If transforming results, thoroughly test success/failure/empty/null/async cases against the type contract.
8. Check other advisors such as cache/transaction/security to determine the chain outcome.

## 11. Review Questions

**1. Why should `@Around` declare return type `Object`?** Because `proceed()` returns `Object` and target methods have varying return types. Capturing and returning that exact result lets the proxy uphold the caller's contract.

**2. What happens if a method returns `int 42` yet the advice returns `null`?** Primitives cannot hold null; proxy/unboxing can fail at runtime. Never return null for a primitive.

**3. If a method returns `Optional.empty()`, may the advice change it to `null`?** Under normal business contracts, no. Callers expect an `Optional` object; preserve the `Optional` or transform per an explicit policy.

**4. Once `pjp.proceed()` finishes running, is the caller guaranteed to receive the target's result?** No. The final value is **the advice's return value**. If the advice fails to return it or returns something else, the caller receives a different value.

**5. For a `void` target, what does `proceed()` return?** Typically `null` through the `Object` API; the advice can return that exact null and the caller sees a normal `void` invocation.

**6. Why is `return result` better than `return result.toString()`?** The new value is a `String`, which may not match the declared return type; even when `String` matches, it can alter semantics or throw from `toString()`.

**7. Can `proceed()` be called multiple times?** Spring AOP allows it technically, yet each call can re-execute the operation. Unless intentionally retrying, call it once.

**8. Can `@AfterReturning` substitute a completely new reference as the target's result?** Not under the standard contract; `@Around` is what can actively select a different return value.

**9. When a method returns `CompletableFuture<T>`, should the advice return `T` or the Future?** It must return a type compatible with the method—namely the corresponding future, not the raw payload directly.

**10. Does returning the right type guarantee the transaction commits?** No. A transaction interceptor may have already rolled back or marked rollback-only before an outer advice catches the exception; you must consider ordering and transaction boundaries.

## Official Spring Documentation

- [Spring Framework — Declaring Advice: Around Advice, proceeds and return value](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Declaring Advice / Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework — Spring AOP Advice API / MethodInterceptor](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html)
- [Spring Framework — AOP Concepts and role of Around Advice](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html)
- [Spring Framework — Proxying Mechanisms: JDK/CGLIB/self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
