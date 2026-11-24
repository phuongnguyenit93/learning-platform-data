# Spring AOP: `null` Results and Primitive-Returning Methods

## 1. Why does a `null` result become an error at the Spring AOP proxy boundary?

In Spring Aspect, an `@Around` advice can **change the final result** that a consumer receives from a method execution. This is useful when handling caching or fallbacks, but it also creates a signature pitfall: **an advice returning `null` for a method with a primitive return type**.

```java
@Around("execution(* demo.results.ResultService.count(..))")
public Object incorrect(ProceedingJoinPoint pjp) throws Throwable {
    pjp.proceed();
    return null; // WRONG: count() is declared to return int.
}
```

This is an **erroneous fragment for analysis**, not a recommended implementation. Even if `count()` actually returned `int 7`, the Spring AOP proxy receives `null` from the advice and cannot convert it into a valid `int` for the caller.

In Spring Framework 6.x, both proxy families perform this type check:

- `JdkDynamicAopProxy` checks the result when a method has a primitive return type (excluding `void`).
- `CglibAopProxy` also checks the result while processing the return value.
- When the result is `null` but the method signature requires a primitive such as `int`, Spring can throw `org.springframework.aop.AopInvocationException`. The typical message states that a null return value from advice does not match the primitive return type.

**Do not confuse `int 0` with `null`:** `0` is a valid `int` value; `null` is not an `int`. A Spring proxy does not invent default values like `0`, `false`, or `0.0` to rescue advice that returns the wrong thing.

This lesson focuses exclusively on **Spring Aspect/Spring AOP**, calls through proxies, outcomes returned by advice, and Java return-contract boundaries. It does not cover general AOP or AspectJ weaving outside Spring.

## 2. Distinguishing three "result types"

### 2.1. Declared return type of the target

A Java method defines a return contract:

```java
public int count() { return 7; }
public Integer boxedCount() { return null; }
public String nullableName() { return null; }
public void complete() { System.out.println("done"); }
```

- `int` is a primitive; there is no null.
- `Integer` is a reference type; it can be null.
- `String` is also a reference type; it can be null in Java terms, even if the business contract forbids it.
- `void` indicates the method **has no return value**; it is different from "a method with a null value".

### 2.2. Return type of `ProceedingJoinPoint.proceed()`

Spring AOP `@Around` accesses the result from the rest of the interceptor chain via `Object`:

```java
Object result = pjp.proceed();
```

For a method returning `int 7`, inside the advice `result` is an `Integer(7)`-compatible object (boxing). For a reference-type method returning null, `result == null`. For `void`, `proceed()` normally also returns null, though the API-level meaning is different.

Because `Object` does not directly carry primitive type information, **you must inspect the method signature** to know whether null is valid. You cannot deduce from `result == null` alone that a method definitely returns `String`, `Integer`, or `void`.

### 2.3. Actual return value of around advice

```java
@Around("execution(* demo.results.ResultService.*(..))")
public Object preserving(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    return result;
}
```

**This is the default form to use when advice is only observing:** the value from `proceed()` is forwarded untouched (unless another advice in the chain intentionally transformed it). The caller ultimately receives a result matching the return contract advertised by the proxied method.

Conversely, if advice writes `return null`, `return "OK"`, or `return 0`, that is a **decision to alter the result**, not a harmless action. With primitives, returning a different type can trigger an exception; with reference types, returning a different value can break the semantic contract.

## 3. Matrix of null, primitive, wrapper, and void in a Spring proxy

| Target method | Result from target | Advice return | Expected outcome |
| --- | --- | --- | --- |
| `int count()` | `7` | `Integer(7)` via `proceed()` | Caller receives `int 7` |
| `int count()` | `7` | `null` | **Error** because null is incompatible with primitive |
| `int count()` | `7` | `Integer(0)` | Caller receives `0`: valid type, but **value was changed** |
| `boolean active()` | `true` | `Boolean.TRUE` | Caller receives `true` |
| `boolean active()` | `true` | `null` | **Error**; null is incompatible with primitive |
| `long total()` | `9L` | `Long(9L)` | Caller receives `9L` |
| `long total()` | `9L` | `Integer(9)` | Not guaranteed valid; mismatched wrapper type |
| `Integer boxedCount()` | `null` | `null` | Valid per Java reference type |
| `String nullableName()` | `null` | `null` | Allowed in Java; caller must handle nullability |
| `Optional<String> find()` | `Optional.empty()` | `Optional.empty()` | Valid and distinct from null |
| `Optional<String> find()` | `Optional.empty()` | `null` | Java accepts it, but it breaks the Optional contract |
| `void complete()` | No value | `null` from `proceed()` | Valid `void` invocation |

**Note on errors:** `AopInvocationException` is a common outcome explicitly enforced by Spring when **the proxy sees null for a primitive**, not a promise that every type mismatch throws this exact exception. Returning `String` for `int` can lead to `ClassCastException` or a type conversion error elsewhere. In Kotlin/coroutines or custom proxy stacks, other mechanisms may apply; this lesson examines Java 17 and standard Spring AOP proxies.

### 3.1. Can boxing and unboxing solve null?

No. Java can box `int 7` into `Integer.valueOf(7)` and unbox `Integer(7)` back to `int 7`, but `null` has no corresponding primitive state.

```java
Integer boxed = null;
// int primitive = boxed; // If executed, throws NullPointerException on unboxing.
```

That is a **Java language error at the unboxing site**. Spring AOP adds a check **at the proxy return boundary**, so when advice returns null for a primitive target, the error can be `AopInvocationException` right at the proxy, before caller code attempts to unbox.

### 3.2. `void` differs from `Void`

- `void complete()`: has no return value; Spring AOP represents the result inside advice as null.
- `java.lang.Void completeReference()`: this is a **reference type**, which can return null in Java terms, even though `Void` has no ordinary values to instantiate.
- `CompletableFuture<Void> asyncComplete()`: returns a **future object**; a future completed with a null value is still a future, not advice returning null in place of the future.

Do not use `Void` as a way to treat `void` as exempt from contract preservation. In Spring `@Around`, good advice still returns the exact result from `proceed()`.

### 3.3. Primitives `char`, `byte`, `short`, `float`, and `double` also do not accept null

The rule applies to all value-bearing primitives: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. Wrappers must match; do not assume Spring always performs primitive widening when advice returns a wrapper of a different type.

## 4. Why should `@Around` return `Object` instead of `void`?

The Spring Framework guide states that an `@Around` method **should declare `Object` as its return type**, and its first parameter must be `ProceedingJoinPoint`.

**Correct for a logging advice applied to multiple return types:**

```java
@Around("execution(* demo.results..*Service.*(..))")
public Object logResult(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    System.out.println("completed " + pjp.getSignature().getName());
    return result;
}
```

**Wrong when the target has non-void methods:**

```java
@Around("execution(* demo.results..*Service.*(..))")
public void logResultWrong(ProceedingJoinPoint pjp) throws Throwable {
    pjp.proceed(); // The target's return value is discarded.
}
```

Spring documentation notes that an `@Around` advice declared with a `void` return type causes the caller to see `null`, **regardless** of what the target returned. For `int`, `boolean`, etc., this can cause the Spring proxy to throw a null-primitive error; for `String`, it can silently turn the result into null.

Do not write a `void` advice method just because it "only logs". For `@Before`, a `void` advice method is normal, because it is not responsible for passing a return value to the caller. `@Around`, however, directly controls the outcome, so it must return explicitly.

### 4.1. `return` inside `finally` can break both returns and exceptions

```java
@Around("execution(* demo.results..*Service.*(..))")
public Object dangerous(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } finally {
        return null; // Wrong: overrides both inner return values and exceptions.
    }
}
```

In Java, a `finally` block with a `return` statement can suppress a thrown exception, leaving the proxy seeing only null. This is a dangerous bug if `@Transactional` is in use or callers rely on exceptions for rollback/retry.

**Correct:**

```java
@Around("execution(* demo.results..*Service.*(..))")
public Object safe(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } finally {
        System.out.println("end");
    }
}
```

Whether the target returns null or throws, cleanup/final logging still runs; the advice does not silently alter the outcome. Design cleanup so it does not arbitrarily throw exceptions that mask the original error.

## 5. How to determine the declared return type inside a Spring Aspect

Inside `@Around`, you can use `MethodSignature`:

```java
import org.aspectj.lang.reflect.MethodSignature;
import java.lang.reflect.Method;

MethodSignature signature = (MethodSignature) pjp.getSignature();
Class<?> declaredReturnType = signature.getReturnType();
Method method = signature.getMethod();

System.out.println("returnType=" + declaredReturnType.getName());
```

This is a **fragment** inside advice, not a standalone Java file. For a Spring-managed bean with method `int count()`, `declaredReturnType == int.class`. If the method is `void complete()`, the result type is `void.class`.

You can check null-primitive compatibility explicitly when advice intends to alter the result:

```java
Object result = pjp.proceed();
Class<?> returnType =
        ((MethodSignature) pjp.getSignature()).getReturnType();

if (result == null && returnType.isPrimitive()
        && returnType != void.class) {
    throw new IllegalStateException(
            "null is incompatible with primitive return type " + returnType);
}
return result;
```

This is a **defensive fragment**, not required when you do not modify the result of `proceed()`; the Spring proxy already checks the null–primitive case. A Java target method with a primitive return type that completes normally cannot itself return null, so null appearing there usually means an inner advice/interceptor corrupted the result.

### 5.1. Method on a JDK proxy may be an interface method

With a JDK dynamic proxy, `MethodSignature.getMethod()` may represent the method on the interface rather than the implementation. When you need annotations or the concrete return type on the implementation, use:

```java
MethodSignature signature = (MethodSignature) pjp.getSignature();
Method invoked = signature.getMethod();
Object target = pjp.getTarget();

if (target != null) {
    Method specific = AopUtils.getMostSpecificMethod(
            invoked, target.getClass());
    System.out.println(specific.getReturnType().getName());
}
```

This fragment requires importing `org.springframework.aop.support.AopUtils`. With bridge/generic methods, metadata and `BridgeMethodResolver` also need to be considered. However, null–primitive compatibility is still evaluated against the **method invocation's return contract**, not inferred solely by looking at a generic DTO.

### 5.2. Is a method returning `Integer` necessarily allowed to be null?

In the **Java type system**, yes. But the business API may require non-null. The Spring proxy simply has no basis to treat a `null Integer` as invalid the way it does `null int`. If you want to guarantee a non-null reference, enforce validation at the appropriate boundary (such as validation annotations with an active enforcement mechanism) or check explicitly in the service/around advice.

## 6. How null results in `@AfterReturning` differ from null results in `@Around`

Spring `@AfterReturning` runs when a method execution finishes **normally**, including when a reference-type method returns null. There are two advice styles to distinguish:

**Without binding the return value:**

```java
@AfterReturning("execution(* demo.results.ResultService.nullableName(..))")
public void afterNormal() {
    System.out.println("completed normally");
}
```

**Binding the return value with a specific type:**

```java
@AfterReturning(
    pointcut = "execution(* demo.results.ResultService.nullableName(..))",
    returning = "value"
)
public void inspect(String value) {
    System.out.println("value=" + value);
}
```

These snippets are interchangeable **fragments**. When `returning="value"` is present, Spring uses the advice parameter type to restrict matching/binding of the return value. Understand the matching semantics for `null` and specific parameter types across versions/configurations; do not assume `String value` is always invoked only with a non-null String. If your goal is solely to know the method completed, `@AfterReturning` **without binding** is the simplest option.

**Crucially:** an `@AfterReturning` method is not the place to return a new reference to replace the target result. Even if the advice method returns `String`, the return value from the advice does not become the new result for the caller. When you need to replace a result, use `@Around` and ensure a compatible return type.

### 6.1. `null` does not necessarily mean an exception

If a method returns `String null` through a proxy and no advisor forbids null, the invocation still completes **normally**. `@AfterThrowing` does not run just because the return value is null. Conversely, when advice returns null for `int` and causes the Spring proxy to throw an exception, that error occurs **at the proxy/advice boundary**, not as a natural exception thrown by the target method.

### 6.2. `@AfterThrowing` is not a monitor for every error in the interceptor chain

An `@AfterThrowing` advice is defined for an exceptional exit from the advised method execution; Spring documentation notes it is **not a general exception callback** catching every error from other advice. When the Spring proxy itself throws `AopInvocationException` for a null–primitive at an outer layer of the chain, do not assume an `@AfterThrowing` targeting the business method will see that error. Observe at the caller or use an appropriate outer `@Around`, paying attention to advisor precedence.

## 7. Java 17 + Spring Framework 6.2 example: valid null and invalid null

The following complete example uses Maven, Java 17, Spring Framework 6.2, and a **Spring AOP proxy** (no Spring Boot required). It uses the `ResultPort` interface so a JDK dynamic proxy clearly demonstrates the return contract.

The project contains a Spring-managed service with:

- `nullableName()` returning a **Java-valid** null String;
- `count()` returning primitive `int 7`;
- `zero()` returning **valid** primitive `int 0`, not null;
- `boxedCount()` returning `Integer null`;
- `emptyResult()` returning `Optional.empty()` (distinct from null);
- `complete()` returning `void`;
- `brokenPrimitive()` returning primitive `int 9`, while **an advice intentionally returns null**, causing the proxy to throw an error.

The pointcuts for the preserving case and the broken case **do not overlap**, so predicting stdout does not depend on advisor precedence.

### 7.1. Directory structure

```text
spring-aop-null-primitive/
├── pom.xml
└── src/main/java/demo/results/
    ├── AppConfig.java
    ├── ResultPort.java
    ├── ResultService.java
    ├── ResultAspect.java
    └── Main.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-null-primitive</artifactId>
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

### 7.3. `AppConfig.java`

```java
package demo.results;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` discovers the service and aspect in package `demo.results`. `@EnableAspectJAutoProxy` enables Spring AOP proxying. The target implements an interface; `proxyTargetClass=false` prefers a JDK dynamic proxy.

### 7.4. `ResultPort.java`

```java
package demo.results;

import java.util.Optional;

public interface ResultPort {
    String nullableName();
    int count();
    int zero();
    Integer boxedCount();
    Optional<String> emptyResult();
    void complete();
    int brokenPrimitive();
}
```

The method `int brokenPrimitive()` has a primitive return; it cannot return null in the target's Java source. The error will come from the advice returning `Object null`.

### 7.5. `ResultService.java`

```java
package demo.results;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class ResultService implements ResultPort {
    @Override
    public String nullableName() {
        System.out.println("[target] nullableName");
        return null;
    }

    @Override
    public int count() {
        System.out.println("[target] count");
        return 7;
    }

    @Override
    public int zero() {
        System.out.println("[target] zero");
        return 0;
    }

    @Override
    public Integer boxedCount() {
        System.out.println("[target] boxedCount");
        return null;
    }

    @Override
    public Optional<String> emptyResult() {
        System.out.println("[target] emptyResult");
        return Optional.empty();
    }

    @Override
    public void complete() {
        System.out.println("[target] complete");
    }

    @Override
    public int brokenPrimitive() {
        System.out.println("[target] brokenPrimitive");
        return 9;
    }
}
```

The target demonstrates valid Java outcomes. `null` in `nullableName()` and `boxedCount()` is a null reference. `emptyResult()` returns **an empty Optional object**, not null. `zero()` returns a valid `0`.

### 7.6. `ResultAspect.java`

```java
package demo.results;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ResultAspect {
    @Around(
        "execution(* demo.results.ResultService.*(..))"
      + " && !execution(* demo.results.ResultService.brokenPrimitive(..))"
    )
    public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
        String name = pjp.getSignature().getName();
        Object result = pjp.proceed();

        String kind = result == null
                ? "null"
                : result.getClass().getSimpleName();

        System.out.println("[advice] " + name + " kind=" + kind);
        return result;
    }

    @Around("execution(* demo.results.ResultService.brokenPrimitive(..))")
    public Object breakPrimitive(ProceedingJoinPoint pjp) throws Throwable {
        Object result = pjp.proceed();
        System.out.println("[advice] brokenPrimitive discarded=" + result);
        return null; // Intentionally demonstrates the Spring proxy error.
    }
}
```

Two advice methods with disjoint expressions:

- `preserve(...)` handles the remaining methods of `ResultService`, calls `proceed()` once, logs the runtime kind when the result is non-null, and **returns the original value**.
- `breakPrimitive(...)` matches only `brokenPrimitive()`, still calls the target so the target log appears, and then **returns null** despite the declared `int`.
- `@Aspect @Component` creates the aspect bean; target methods must also go through the Spring proxy for these advice methods to run.
- `result.getClass()` is guarded by the `result == null` check so it does not cause an NPE on null reference or void returns.

Note that `@Around` must declare `Object` to ensure the result is returned. If an advice has a `void` return, the caller receives null even though the target method ran.

### 7.7. `Main.java`

```java
package demo.results;

import org.springframework.aop.framework.AopInvocationException;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            ResultPort port = context.getBean(ResultPort.class);
            System.out.println("[main] jdkProxy="
                    + AopUtils.isJdkDynamicProxy(port));

            System.out.println("[caller] name=" + port.nullableName());
            System.out.println("[caller] count=" + port.count());
            System.out.println("[caller] zero=" + port.zero());
            System.out.println("[caller] boxed=" + port.boxedCount());
            System.out.println("[caller] optional=" + port.emptyResult());

            port.complete();
            System.out.println("[caller] complete returned void");

            try {
                System.out.println("[caller] broken="
                        + port.brokenPrimitive());
            } catch (AopInvocationException ex) {
                System.out.println("[caller] primitive null rejected");
            }
        }
    }
}
```

Compile and run command:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.results.Main
```

**Expected stdout** from the application's `System.out` statements (ignoring Maven/Spring-specific logs if any are emitted by the environment):

```text
[main] jdkProxy=true
[target] nullableName
[advice] nullableName kind=null
[caller] name=null
[target] count
[advice] count kind=Integer
[caller] count=7
[target] zero
[advice] zero kind=Integer
[caller] zero=0
[target] boxedCount
[advice] boxedCount kind=null
[caller] boxed=null
[target] emptyResult
[advice] emptyResult kind=Optional
[caller] optional=Optional.empty
[target] complete
[advice] complete kind=null
[caller] complete returned void
[target] brokenPrimitive
[advice] brokenPrimitive discarded=9
[caller] primitive null rejected
```

### 7.8. Reading the output case by case

1. `jdkProxy=true`: the `ResultService` bean is proxied by Spring via the `ResultPort` interface.
2. `nullableName()`: the target returns a null reference, around advice sees null and returns it unchanged; the caller prints `name=null`. This is a **normal return**, not a primitive error.
3. `count()`: the target returns primitive 7. When `proceed()` finishes, the advice receives the `Integer` wrapper, logs `kind=Integer`, and returns the wrapper; the caller receives primitive 7.
4. `zero()`: the target returns `int 0`. The advice logs `Integer`, and the caller receives 0; **0 differs from null**.
5. `boxedCount()`: declared `Integer` permits null, the advice returns null, so the proxy accepts it. The caller prints `boxed=null`.
6. `emptyResult()`: the value is an Optional object. `getClass().getSimpleName()` in a typical JDK prints `Optional`, and the caller prints `Optional.empty`.
7. `complete()`: void target; `proceed()` represents the result as null; returning null from the advice is valid because the declared type is `void`.
8. `brokenPrimitive()`: the target returned `int 9`; the advice deliberately **discarded** `Integer(9)` and returned null. The Spring proxy detects the declared primitive type and throws `AopInvocationException`. The caller catches it and prints `primitive null rejected`.
9. All invocations from `Main` go through the Spring-managed reference; if `new ResultService()` were used instead of DI/context, the advice would not run and `brokenPrimitive()` would return 9 normally.

**Warning:** item 8 is an error created **intentionally for learning**. In production, fix the advice rather than catching the proxy error and returning a fake success.

## 8. When the goal is a fallback, choose a compatible and meaningful value

An `@Around` advice can catch an exception and return a fallback:

```java
@Around("execution(int demo.results.ResultService.count(..))")
public Object fallbackCount(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return 0; // Integer(0) via Object, compatible with int.
    }
}
```

This is a **separate fragment** and must not be added to the project in section 7 without designing ordering between multiple around advice. At the Java type level, `0` can pass through the proxy to `int`. However, **being type-valid does not guarantee being business-valid**: for order counts or monetary amounts, `0` can be severely wrong data.

If the method actually returns `Optional<String>`, a more appropriate fallback is usually `Optional.empty()` (per the contract). If the method returns `CompletableFuture<String>`, the fallback must be a compatible future, not a String payload. If a method returning `String` has a `@NonNull` contract, returning null is still a business violation even though Java allows it.

### 8.1. Rules to prevent silent data corruption

- **Do not automatically turn null into 0** for primitives unless there is a business requirement.
- **Do not use a blanket `return null`** across all return types.
- **Do not use `Object.class`** as a workaround for typed contracts: public methods still have fixed declared return-type signatures.
- **Do not call `proceed()` twice** to "re-fetch the value" if the invocation can have side effects.
- **Do not return a mismatched wrapper type** hoping the runtime will automatically convert it into the target primitive.
- **Do not catch `Throwable` and `return null`** to hide all errors; this can swallow critical exceptions and mask rollback conditions.

## 9. Null, exceptions, and transactions in Spring AOP

### 9.1. A null reference return is normal completion

A method `String lookup()` returning null does not itself throw an exception; Spring treats the invocation as completing normally. Therefore `@AfterReturning` can run, while `@AfterThrowing` typically does not run solely because the result is null.

If the application treats null as an error, establish a well-grounded **validation policy** at the service/interface boundary; using `@NonNull`/validation requires a framework that actually enforces it, as annotation names alone do not make Spring AOP convert every null into an exception.

### 9.2. Null primitive is an error detected at the proxy boundary

If an inner `@Around` in the chain returns null for a primitive method, the outer Spring proxy can throw `AopInvocationException`. This error did not necessarily originate from the target method body; in the section 7 demo, the target finished running and returned the right `int`.

This matters when debugging:

```text
[target] brokenPrimitive
[advice] brokenPrimitive discarded=9
[caller] primitive null rejected
```

**Do not infer that the target threw an exception** just because the caller caught an error from the proxy call. Distinguish a target exception from a proxy/advice return-contract violation.

### 9.3. Transaction rollback does not fix a return mismatch

Spring `@Transactional` may use another advisor in the chain. If the transaction interceptor sees the target return normally, and an outer AOP layer later throws a null-primitive exception, commit/rollback may already have been decided at the inner boundary. If the error arises inside the transaction boundary, it may trigger a rollback depending on the exception type and rollback rules.

Therefore, do not claim "primitive null triggers transaction rollback" in every configuration. Inspect advisor ordering, the transaction interceptor's position, and test actual commit/rollback behavior.

### 9.4. Async return wrappers

A method `CompletableFuture<Integer> countAsync()` has a declared return type of **future**, not `int`. An `@Around` returning null may not be caught immediately by the null-primitive check because a future is a reference type, yet the caller can hit an NPE when calling `thenApply(...)`. The same applies to `Mono<Integer>` or `Flux<Integer>` when using Reactor.

A future completed with a null result is still a **future object**; the wrapper, completion/error behavior, and value all belong to the async API contract. Do not return the payload directly instead of the future.

## 10. Common mistakes

| Symptom | Root cause | How to resolve |
| --- | --- | --- |
| `AopInvocationException` stating null does not match primitive | Around advice (or advisor) returned null for `int`/`boolean`, etc. | `return pjp.proceed()` when only observing; fallbacks must match the type |
| Target printed the right value, yet caller still fails | Result was overwritten by advice after the target returned | Check every `return` path of `@Around` |
| `String` method returns null without a proxy error | Reference types allow null in the JVM | Check the business nullability contract |
| How does `Integer` returning null differ from `int`? | Wrapper is a reference; primitives do not accept null | Use the appropriate type/API |
| `void` method has `result == null` | No business return value | This is the normal representation from `proceed()` |
| `Optional.empty()` turned into null | Advice broke the wrapper contract | Return the original Optional unchanged |
| Advice declared `void` applied to a non-void target | Return value discarded per Spring `@Around` semantics | Declare `Object` and return the result |
| Catch error then `return null` | Masks exceptions and breaks primitive contracts | Only use a fallback when the contract permits it |
| `return null` inside `finally` | Overrides return values or exceptions | Never return inside `finally` |
| Returning `Integer(5)` for a `long` target | Wrapper does not match `Long` | Preserve the boxed value from proceed |
| `@AfterReturning` does not run as expected | Return binding type or pointcut mismatch | Check declared/actual type, normal completion, and annotations |
| Logging advice does not run on self-call | `this.method()` bypasses the proxy | Extract a bean or call across the Spring proxy boundary |
| Null return occurs on JDK proxy, still fails when switching to CGLIB | Both support primitive-null checking | Fix the advice; do not switch proxy mode to dodge the bug |
| Unit test instantiating service with `new` does not reproduce error | No Spring AOP proxy in the unit test | Write integration tests with a real `ApplicationContext` |
| Null primitive proxy exception yet transaction still commits | Error occurred outside the transaction boundary | Inspect the advisor chain and transaction ordering |
| Future/Reactive returning null causes errors at the caller | Reference wrapper was lost | Preserve the appropriate wrapper |

## 11. Code review and testing checklist

1. Confirm the target is a Spring-managed bean and the aspect is registered; without a proxy, there is no advice.
2. Identify the method's **declared return type**, especially primitives, wrappers, `void`, `Optional`, and async wrappers.
3. For logging/metrics-only `@Around`, use `Object result = pjp.proceed(); return result;`, calling proceed exactly once.
4. Inspect every `return`, `catch`, and `finally` branch; never return null outside policy.
5. Verify boxed primitives have the right wrapper type and value.
6. Check null references against the business contract; `String null` is not automatically a proxy error.
7. Confirm `@AfterReturning` and `@AfterThrowing` are used with the right outcome semantics.
8. If multiple advisors, caching, transactions, retries, or async exist, verify actual ordering and where errors originate.
9. Write integration tests against the **actual Spring AOP proxy**, covering values, null, zero, void, Optional, and primitive violations.
10. Keep exception logs clear about the source: target throw, advice throw, or proxy return-type check.
11. With JDK proxies, invoke via interface methods; with CGLIB, check `final`/`private` restrictions and self-invocation.
12. Do not fix primitive-null errors by inserting a fake zero return or swallowing exceptions.

### Recommended test case table

| Case | Expected result |
| --- | --- |
| `String nullableName()` → null | Caller sees null if contract permits |
| `Integer boxedCount()` → null | Caller sees null |
| `int count()` → 7 | Caller sees 7 |
| `int zero()` → 0 | Caller sees 0, not treated as null |
| `void complete()` | Method runs, no business return value |
| `Optional.empty()` | Caller sees an empty Optional |
| `@Around` intentionally returns null for `int` | Proxy throws a primitive-null mismatch error |
| Target throws a real exception | Advice does not auto-heal the error unless intentionally handled |
| Self-invocation `this.count()` | No separate interception for internal call |

## 12. Self-assessment questions

**1. Why can `Object result = pjp.proceed()` be an `Integer` for a method returning `int`?** Because `proceed()` uses type `Object`; primitives are boxed on the path through advice.

**2. Does returning null from `@Around` for `int` make the caller receive 0?** No. In a standard Spring AOP proxy, null is incompatible with primitives and can raise `AopInvocationException`.

**3. Is `Integer boxedCount()` returning null the same error?** No. `Integer` is a reference type, so null is valid in Java. Business code may still disallow it.

**4. If `void complete()` has `proceed()` return null, is there a primitive-null error?** No. Spring excludes `void` from null checks for value-bearing primitives.

**5. Why can `@Around public void log(...)` break `String` or `int` methods?** Because Spring will return null to the caller, discarding the result of `proceed()`.

**6. Can `@AfterReturning` return a new `String` to replace the result?** Not under this advice's contract. Use `@Around` if you intentionally need to replace values.

**7. If `Optional<String>` returns `Optional.empty()`, should advice turn it into null?** Not under standard Optional contracts; that changes the API and can cause NPEs.

**8. Why is using `return` inside `finally` dangerous?** It overrides return values and can swallow exceptions in Java, causing the proxy to see the wrong outcome.

**9. Does switching from JDK proxy to CGLIB fix an advice returning null for `int`?** No. Both Spring proxy types enforce the null-primitive restriction.

**10. If the target returns the right value but the caller receives an error, where should you check?** Inspect `@Around`, advisors outside the target, return paths after `proceed()`, and the proxy return-type contract before blaming the target method.

## Official documentation

- [Spring Framework 6.2 — Declaring Advice: Around Advice and return contracts](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework — AOP Concepts and Advice types](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html)
- [Spring Framework 6.2 — Proxying Mechanisms: JDK/CGLIB, self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework source — JdkDynamicAopProxy null-primitive check](https://github.com/spring-projects/spring-framework/blob/main/spring-aop/src/main/java/org/springframework/aop/framework/JdkDynamicAopProxy.java)
- [Spring Framework source — CglibAopProxy null-primitive check](https://github.com/spring-projects/spring-framework/blob/main/spring-aop/src/main/java/org/springframework/aop/framework/CglibAopProxy.java)
- [Spring Framework — @AspectJ support, registration, and advisors](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html)
