# `@AfterReturning` and Return Value Binding in Spring AOP

## 1. Objective and Scope

In **Spring AOP with `@AspectJ` syntax**, `@AfterReturning` is advice that executes **after a method execution selected by a pointcut finishes normally** and control is about to return to the caller. The advice can simply record the event, or receive the actual return value using the `returning` attribute.

Practical examples: recording a successful lookup result, updating a metric for a completed service call, or observing returned data when a Spring service is called **through an AOP proxy**.

The key points of this lesson are not only when the advice runs, but also:

1. **When is it considered "returning normally"?** The method returns normally (including `null` and `void` methods if the advice expression/conditions match), rather than exiting via an exception.
2. **How to write `@AfterReturning(pointcut = "...", returning = "result")`:** the name `result` must correspond to the advice parameter; the parameter type becomes a matching constraint.
3. **Can `@AfterReturning` change the result returned to the caller?** It does not replace the returned reference/value. To actively change the result, you must design an `@Around` advice or different business logic.
4. **Spring requirements:** the aspect and target must be managed by the container, auto-proxy infrastructure must be enabled, the pointcut must match, and the caller must go through the proxy. Even with the right annotation name, calling `this.method()` can still bypass the advice.

This lesson focuses on **Spring Aspect / Spring AOP**: Java configuration, Spring beans, proxy boundaries, how to bind return values, and common mistakes. It does not revisit general AOP concepts or switch to AspectJ bytecode weaving.

## 2. When `@AfterReturning` Runs

A simple call path when Spring AOP applies an advisor:

```text
Consumer / Controller / Another Service
         |
         | service.lookup("A")
         v
Spring AOP proxy
         |
         +-- Pointcut matches method?
         |       |
         |       +-- Yes: invocation goes through the interceptor chain
         |
         v
Target bean: ResultService.lookup("A")
         |
         +-- If it RETURNS normally
         |        |
         |        +-- @AfterReturning advice is called if return binding conditions are valid
         |        |
         |        +-- Original value continues back to the caller
         |
         +-- If it THROWS an exception
                  |
                  +-- @AfterReturning does NOT run for that error exit
                  |
                  +-- Exception continues through the proxy/interceptor chain

Note: Other advices in the chain can change the order and outcome.
```

This is a **general** diagram for a matching invocation; with multiple advisors, `@Around`, transactions, or asynchronous execution, when the caller observes the result also depends on the interceptor chain. The Spring docs define `@AfterReturning` by the **normal return of a join point**, without asserting that a data transaction has committed or that an asynchronous task has finished.

### 2.1. Brief Comparison of Related Spring Advice Types

| Annotation | When target method execution goes through proxy | Receives return value directly? |
| --- | --- | --- |
| `@Before` | Before the target call when the pointcut matches | No, because the target has not returned yet. |
| `@AfterReturning` | After the method completes normally | Yes, via `returning`. |
| `@AfterThrowing` | When the method throws an exception out of the join point | Can bind the exception via `throwing`, not the normal return value. |
| `@After` | With after-finally semantics: when the join point exits normally **or** abnormally | Does not use `returning` to bind a result. |
| `@Around` | Surrounds the invocation; can use `ProceedingJoinPoint.proceed()` | Can observe and decide the value returned to the caller when designed properly. |

**Two misconceptions to avoid:**

- `@AfterReturning` does **not** mean "always runs at the end of the method," because if the method throws an exception, this advice does not run.
- `@After` is **not** another name for `@AfterReturning`: `@After` has semantics similar to `finally`.

## 3. Minimal Configuration in Spring Framework

The annotations come from the AspectJ annotations API:

```java
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.AfterReturning;
```

The aspect class must be registered with Spring. Example **illustrative configuration snippets**, not a standalone runnable project yet:

```java
@Aspect
@Component
public class ResultAuditAspect {
    @AfterReturning(
        "execution(public * com.example.orders..*Service.*(..))"
    )
    public void afterNormalReturn() {
        System.out.println("service completed normally");
    }
}
```

```java
@Configuration
@ComponentScan("com.example.orders")
@EnableAspectJAutoProxy
public class AopConfiguration {
}
```

Conditions for the advice to actually run:

- `@Aspect` declares the class containing advice; `@Component` (within a scanned package) **or** a `@Bean` factory method registers that class as a Spring bean.
- `@EnableAspectJAutoProxy` in Spring Framework Java configuration enables auto-proxying for `@Aspect` beans; a compatible `aspectjweaver` is typically required on the classpath.
- A method **belonging to a Spring-managed target bean** and matching `execution(...)` must be called **through the Spring proxy**.
- With a JDK dynamic proxy, the caller invokes a method exposed on the interface; with a class-based proxy, the class/method must be proxyable (`final` has limitations).
- Code calling `new Service()` or `this.method()` inside the target is not intercepted by Spring AOP in the normal way.

Spring Boot provides AOP auto-configuration when the application includes the appropriate dependency; that does not change the requirement that `@Aspect` be a Spring bean. You do not need to enable a weaving agent just to use `@AfterReturning` with Spring AOP proxies.

## 4. Syntax 1 — Without Binding the Result

The shortest form:

```java
@AfterReturning(
    "execution(public * com.example.orders..*Service.*(..))"
)
public void afterSuccessfulServiceMethod() {
    // Record a service call that completed normally.
}
```

Here:

- `@AfterReturning` uses a pointcut expression via the annotation's `value` attribute.
- The advice method `afterSuccessfulServiceMethod()` **does not accept a result parameter**, so it cannot rely on a parameter signature to constrain the return value type.
- Methods returning `String`, `int`, an object, or `void` can all be selected if the **pointcut matches the method execution** and the execution exits normally.
- A method whose target call fails with an exception will not run this advice.
- A `void` return type on the advice is the natural choice because the advice itself does not transform the target's result.

An unbound `@AfterReturning` example fits a metric like `successfulMethodReturns++`. However, "the method returned normally" is **not synonymous** with "the business transaction succeeded," "HTTP response 2xx," or "the database commit definitely succeeded."

## 5. Syntax 2 — Binding the Return Value with the `returning` Attribute

To receive the value returned by the method:

```java
@AfterReturning(
    pointcut = "execution(public * com.example.orders..*Service.*(..))",
    returning = "result"
)
public void afterReturningValue(Object result) {
    System.out.println("result=" + result);
}
```

**The name `result` in `returning = "result"` must match the advice parameter name** `Object result`. Spring/AspectJ binding passes the returned value into this parameter. The key lesson is: `returning` is **not a field name**, not a variable name inside the target method, and not an arbitrary string.

When you want to ensure parameter mapping works across different compilation/metadata configurations, you can declare `argNames`:

```java
@AfterReturning(
    pointcut = "execution(public * com.example.orders..*Service.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterReturningValue(Object result) {
    // Read the result value received from a normal method return.
}
```

`argNames` belongs to the `@AfterReturning` annotation and is used by Spring when determining binding parameter names. It is especially helpful when building Java code without retaining parameter names in bytecode or when advice binds multiple variables. In simple examples Spring can infer the name, but do not rely on an implicit compiler configuration in standard lessons/test suites.

### 5.1. When `returning` Name Does Not Match

```java
// Invalid binding meaning: returning="value" while the advice only declares "data".
@AfterReturning(
    pointcut = "execution(* com.example.orders..*Service.*(..))",
    returning = "value",
    argNames = "data"
)
public void wrongBinding(Object data) {
}
```

This is an **error-illustration snippet**; do not copy it into a Spring context that needs to start successfully. In an actual configuration, the advisor may fail to initialize because the pointcut/binding is invalid. **The fix** is to make the names consistent: `returning="data"`, `argNames="data"`, and parameter `Object data`, or change all of them to `value`.

### 5.2. `returning` Also Acts as a Type Filter

**A very important point:** the declared type of the advice parameter is not only for reading the value; it also **restricts the set of method executions that match the advice**.

```java
@AfterReturning(
    pointcut = "execution(public * com.example.orders..*Service.*(..))",
    returning = "text",
    argNames = "text"
)
public void afterText(String text) {
    // Only returns whose type is compatible with String are bound.
}
```

If the same `execution(public * ...)` expression covers methods returning `String` and `Integer`:

- An advice with parameter `String text` applies to results compatible with `String`, not "every method in the package."
- An advice with parameter `Object result` is broader: it can receive many reference results and boxed primitive values where applicable.
- A `void` method **has no result value to bind as `String`**; if you want to count `void` methods completing normally, use an advice **without return binding**.

The Spring docs state clearly: adding `returning` restricts the advice to match only method executions returning values of the type specified in the advice parameter. This easily causes confusion when two advices share a pointcut and one counts fewer invocations than the other.

### 5.3. What If the Result Is `null`?

`null` is **not an exception**: a method returning `null` still completes normally. If you use an advice **without binding the result**, it can still run according to the pointcut. If you use a returning-bound advice with a reference type, the code should **handle null**:

```java
@AfterReturning(
    pointcut = "execution(public java.lang.String com.example.orders..*Service.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterString(String result) {
    if (result == null) {
        System.out.println("returned:null");
        return;
    }
    System.out.println("returned:length=" + result.length());
}
```

This is an illustrative snippet, not a standalone project. With typed binding, whether the advisor is selected also depends on the declared/matched return type according to Spring AOP. **Do not** call `result.length()` directly without a null-check just because the method declares a `String` return type. If a method has generic bridge/covariant returns or an `Object` return type whose runtime value varies, run an integration test on your exact Spring version instead of inferring from the signature alone.

## 6. Runnable Demo: Unbound vs. `String`-Bound on the Same Pointcut

The Java 17+ demo below demonstrates:

1. An **unbound** `@AfterReturning` counts normal returns across multiple method types.
2. `@AfterReturning(returning="result")` with parameter `String result` only counts matching result types.
3. A `void` method completing normally is counted by the unbound advice.
4. A method throwing an exception **is not counted** by `@AfterReturning`.
5. `@AfterReturning` does not alter the value seen by the caller.

Environment: **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, **Java 17+**, Gradle. Plain Spring Framework is used to make the role of `@EnableAspectJAutoProxy` transparent.

### 6.1. Project Structure

```text
spring-after-returning-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/returning/
    ├── Main.java
    ├── AppConfig.java
    ├── ResultService.java
    └── ReturnAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-after-returning-demo'
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
    mainClass = 'com.example.returning.Main'
}
```

Spring Framework 6.x requires Java 17 or newer. `spring-context` provides the container infrastructure; `spring-aop` and `aspectjweaver` support Spring `@AspectJ` proxy-based configuration. When moving to Spring Boot, use the dependency management of the corresponding Boot major version.

### 6.2. Target Spring Service with Multiple Outcome Types

**`ResultService.java`**

```java
package com.example.returning;

public class ResultService {
    public String lookup(String id) {
        return "found:" + id;
    }

    public Integer available() {
        return 7;
    }

    public void warmUp() {
        System.out.println("target:warmUp");
    }

    public String fail() {
        throw new IllegalStateException("missing");
    }
}
```

All four methods are public/non-final and the class is non-final. Thus, this scenario **is not confounded by CGLIB `final`/`private` issues**. The `fail()` method declares return type `String` but actually throws an exception; normal-return advice does not run for that invocation.

### 6.3. One Aspect, Two `@AfterReturning` Advices

**`ReturnAspect.java`**

```java
package com.example.returning;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class ReturnAspect {
    private final AtomicInteger normalReturns = new AtomicInteger();
    private final AtomicInteger stringReturns = new AtomicInteger();

    @AfterReturning(
        "execution(public * com.example.returning.ResultService.*(..))"
    )
    public void afterAnyNormalReturn() {
        normalReturns.incrementAndGet();
    }

    @AfterReturning(
        pointcut = "execution(public * com.example.returning.ResultService.*(..))",
        returning = "result",
        argNames = "result"
    )
    public void afterStringReturn(String result) {
        stringReturns.incrementAndGet();
    }

    public int normalCount() {
        return normalReturns.get();
    }

    public int stringCount() {
        return stringReturns.get();
    }
}
```

The `AtomicInteger` counters are for demo purposes, not a production metrics system. The advices do not print logs, so output **does not depend on execution ordering between the two advices**. Spring does not promise a fixed order between multiple advices of the same kind within the same aspect unless appropriate ordering is declared/applied.

**Counter logic:**

- `lookup("A")`: returns `String` normally → both `normalReturns` and `stringReturns` increment.
- `available()`: returns `Integer` normally → `normalReturns` increments; `stringReturns` does not increment because `String` type binding is incompatible.
- `warmUp()`: `void` completes normally → the **unbound** advice increments `normalReturns`; the `String`-bound advice does not increment.
- `fail()`: throws `IllegalStateException` → no normal return; neither `@AfterReturning` advice increments.

### 6.4. Spring AOP Configuration

**`AppConfig.java`**

```java
package com.example.returning;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    ResultService resultService() {
        return new ResultService();
    }

    @Bean
    ReturnAspect returnAspect() {
        return new ReturnAspect();
    }
}
```

`ResultService` is a Spring-managed target via `@Bean`; `ReturnAspect` is a Spring-managed `@Aspect` bean, also via `@Bean`. `@EnableAspectJAutoProxy(proxyTargetClass=true)` enables advisor scanning and class proxying. `@ComponentScan` is unnecessary because all required beans are explicitly declared.

### 6.5. Bootstrapping and Printing Advice Execution Counts

**`Main.java`**

```java
package com.example.returning;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            ResultService service = context.getBean(ResultService.class);
            ReturnAspect aspect = context.getBean(ReturnAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("lookup=" + service.lookup("A"));
            System.out.println("available=" + service.available());
            service.warmUp();

            try {
                service.fail();
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println("normalReturns=" + aspect.normalCount());
            System.out.println("stringReturns=" + aspect.stringCount());
        }
    }
}
```

Run in the project directory after installing JDK 17+ and Gradle:

```bash
gradle run --quiet
```

If using the Gradle Wrapper: `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

**Program `System.out` lines in order** (excluding separate JVM/Spring/Gradle logging):

```text
proxy=true
lookup=found:A
available=7
target:warmUp
caught=missing
normalReturns=3
stringReturns=1
```

### 6.6. Why Do the Two Counters Differ?

**The exact same pointcut** `execution(public * com.example.returning.ResultService.*(..))` is used for both advices. However:

| Target call | Outcome | Unbound advice | `String`-bound advice |
| --- | --- | --- | --- |
| `lookup("A")` | `String`, normal return | Yes | Yes |
| `available()` | `Integer`, normal return | Yes | No |
| `warmUp()` | `void`, normal return | Yes | No |
| `fail()` | Exception exits method | No | No |

After the calls, `normalReturns=3` and `stringReturns=1`. **It is not that the `String` advisor failed**; it is the parameter type in the returning-bound advice that narrows matching.

The values returned from the target remain unchanged: `lookup=found:A`, `available=7`. `@AfterReturning` in the example only observes and increments counters without modifying the return value.

If you do not see matching lines in a real application, check the Spring proxy and bean registration first, and only then examine the `returning` name/type.

## 7. Combining Return Binding and Method Argument Binding

With Spring `@AspectJ`, you may need both the **input arguments** and the **output result** of a service call. Use `args(...)` inside the pointcut together with `returning` to bind both.

**Standalone illustrative example** — do not add it to the section 6 demo project if you want to keep the counters/stdout unchanged:

```java
@Aspect
public class LookupAuditAspect {
    @AfterReturning(
        pointcut =
            "execution(public java.lang.String com.example.returning.ResultService.lookup(..))"
            + " && args(id)",
        returning = "result",
        argNames = "id,result"
    )
    public void afterLookup(String id, String result) {
        System.out.println("lookup:" + id + "=" + result);
    }
}
```

Here:

- `args(id)` binds the input parameter of the selected method to `String id`.
- `returning="result"` binds the return value to `String result`.
- `argNames="id,result"` makes the binding order and names explicit; if you add a `JoinPoint` parameter, check the parameter-naming rules in the Spring documentation.
- The parameter type `String id` also constrains the argument type; methods with incompatible signatures will not match.
- The demo's `ResultService.lookup("A")` returns `"found:A"`, so if this aspect **is registered instead/independently in an appropriate context**, it prints:

```text
lookup:A=found:A
```

This snippet is not yet a standalone runnable Java file: it needs a package, imports, `@Bean`/`@Component` to register the aspect, and the target/result service in the context.

**Do not store raw passwords/tokens/sensitive data** in logs just because `args` and `returning` grant access to them. Apply a data-masking policy and avoid excessive logging on hot paths.

### 7.1. When Using `JoinPoint`

An advice can declare `JoinPoint` to read the method signature along with the result:

```java
@AfterReturning(
    pointcut = "execution(public java.lang.String com.example.returning.ResultService.lookup(..))",
    returning = "result",
    argNames = "result"
)
public void afterLookup(JoinPoint joinPoint, String result) {
    System.out.println(joinPoint.getSignature().getName() + "=" + result);
}
```

This is an **illustrative snippet** requiring an import for `org.aspectj.lang.JoinPoint` and placement inside a Spring-managed `@Aspect` class. A leading `JoinPoint` parameter has special binding handling in `@AspectJ`. Use it only when metadata is needed; if you only observe the result type, a simpler advice method is easier to test.

## 8. Can `@AfterReturning` Change the Target's Return Value?

**You cannot use the advice's own return value to replace the reference/value returned by the target method.**

Example of a **wrong expectation**:

```java
@AfterReturning(
    pointcut = "execution(public java.lang.String com.example.returning.ResultService.lookup(..))",
    returning = "result",
    argNames = "result"
)
public String tryReplace(String result) {
    return "other:" + result;
}
```

This is an **anti-pattern snippet**; do not place it into the demo context as a way to alter results. A normal `@AfterReturning` advice should be `void`; even if you write logic computing another string in its body, it **does not make that string the value the caller receives**. The Spring docs clearly state that `@AfterReturning` cannot return a completely different reference to alter the result already chosen by the target.

Even if you reassign the local parameter:

```java
@AfterReturning(
    pointcut = "execution(public java.lang.String com.example.returning.ResultService.lookup(..))",
    returning = "result",
    argNames = "result"
)
public void assignLocally(String result) {
    result = "replacement"; // Only changes the advice's local variable!
}
```

The caller still receives the string returned by the target. Assigning to the local variable `result` in Java does not change the reference held by the interceptor chain.

### 8.1. With Mutable Objects: Distinguishing Observation from Mutation

If the target returns a mutable object and `@AfterReturning` binds that object:

```java
@AfterReturning(
    pointcut = "execution(* com.example.orders..*Service.load(..))",
    returning = "result",
    argNames = "result"
)
public void observe(AccountDto result) {
    // You can read fields of result, but should not silently mutate the DTO.
}
```

This snippet is **illustrative only**, assuming `AccountDto` exists. If code mutates `result` via setters, because multiple references can point to the same object, the caller **may observe the object's contents changed**. That is different from replacing the returned reference; it is a side effect on a shared object and can cause hard-to-control bugs.

**Spring recommendation:** use `@AfterReturning` for observation/auditing/metrics after a normal return; if business logic intentionally needs to transform the result, use `@Around` explicitly or better yet let the business method return the desired data directly.

### 8.2. Using `@Around` to Decide the Return Value

The following snippet illustrates structure only; do not add it to the demo if you want to preserve its output:

```java
@Around(
    "execution(public java.lang.String com.example.returning.ResultService.lookup(..))"
)
public Object decorateReturn(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    return "wrapped:" + result;
}
```

`ProceedingJoinPoint` comes from `org.aspectj.lang.ProceedingJoinPoint`. For an eligible method, `@Around` has the authority to return a different value to the caller, provided it adheres to the actual return type/contract. If the method can return `null` or throw an exception, production code must handle both cases with proper semantics.

**Do not switch to `@Around` just to count normal returns:** `@AfterReturning` is simpler and more accurate for observation.

## 9. `@AfterReturning` with `void`, `null`, and Special Types

### 9.1. `void` Methods

```java
public void refreshCache() {
    // completes normally with no return value
}
```

An `@AfterReturning("execution(* ...refreshCache(..))")` **without return binding** can run when the method completes normally. However, `@AfterReturning(returning="result")` with a `String result` parameter has no `String` value to bind for a `void` invocation.

If you need to audit "execution finished" for a `void` method, use the **unbound** form like `afterAnyNormalReturn()` in the demo.

### 9.2. `null` from a Reference-Returning Method

```java
public String findOptionalText() {
    return null;
}
```

This is a normal return, not an exception. An **unbound** advice can run. When binding the result to a reference type, the code must be null-safe. If generic return types / type erasure differ or binding has additional constraints, test directly on your Spring version. Do not assume "returning `null` means `@AfterReturning` doesn't run."

### 9.3. Primitives / Wrappers

`int`, `long`, `boolean`, and their wrappers can be represented as boxed `Object` at the appropriate reflection/interceptor layer; however, a `String result` advice is **not** compatible with an `Integer` result. When you need to measure multiple result types, you can choose `Object result` with confirmed matching conditions, or split pointcuts/advices by explicit return type.

Do not cast `Object` to `String` if the same pointcut covers `Integer`, DTOs, and `null`. If runtime branching is required, use `instanceof` and proper null-checks.

### 9.4. `Optional`

If the target returns `Optional<User>`, what the advice receives is the `Optional` object, **not automatically unwrapped** to `User`. An `Optional.empty()` is still a normal return; it does not imply an exception or business success. If you care about "data present," inspect `Optional.isPresent()` in your observation code or design an appropriate result policy.

### 9.5. `CompletableFuture`, `CompletionStage`, `Mono`, and `Flux`

If a method returns `CompletableFuture<T>`, `CompletionStage<T>`, `Mono<T>`, or `Flux<T>`, a Spring proxy's `@AfterReturning` is typically triggered when the **method returns the wrapper/handle normally**, **not** when the asynchronous computation or publisher completes. A return-binding advice will see the **future or publisher**, not automatically the final data `T`.

- For `CompletableFuture`: to observe successful/failed completion, intentionally use APIs like `whenComplete`/`handle` with proper threading/context design.
- For Reactor `Mono`/`Flux`: creating a publisher differs from subscribing/completing; observing reactive signals requires appropriate Reactor operators/instrumentation.
- Do not name an `@AfterReturning` metric "businessSuccess" when the return value is an async handle.

## 10. `@AfterReturning` and Exceptions: Practical Cases

### 10.1. Target Throws an Exception

```java
public String load(String id) {
    throw new IllegalArgumentException("not found");
}
```

If an invocation of `load` goes through the proxy and throws an exception out of the join point, `@AfterReturning` does not run. To track exceptions, use `@AfterThrowing`:

```java
@AfterThrowing(
    pointcut = "execution(public * com.example.orders..*Service.*(..))",
    throwing = "failure",
    argNames = "failure"
)
public void afterFailure(Throwable failure) {
    // Log/metric the error; does not turn the failure into a normal result.
}
```

This is an illustrative snippet requiring an `AfterThrowing` import and a Spring-bean aspect class. `throwing` works like `returning` in that the name must bind properly to the advice parameter; the parameter type can narrow which exception types are matched.

### 10.2. Method Catches an Exception and Returns a Fallback

```java
public String findOrFallback() {
    try {
        return repositoryLookup();
    } catch (RuntimeException ex) {
        return "fallback";
    }
}
```

This is an illustrative snippet assuming `repositoryLookup()` exists. If the method **catches the error internally and actually returns `"fallback"`**, `@AfterReturning` sees a **normal return**. That does not mean the underlying operation never failed—only that the error did not exit the **advised join point**.

To distinguish "fallback due to error" from "full success," you can design a return type carrying domain status (`Result<T>`, error code) or emit metrics in the error-handling layer. Do not turn Spring AOP normal-return into an absolute measure of business success.

### 10.3. `@AfterReturning` Advice Itself Throws an Exception

```java
@AfterReturning(
    "execution(public * com.example.orders..*Service.lookup(..))"
)
public void audit() {
    throw new IllegalStateException("audit unavailable");
}
```

This is a **risk-illustration snippet**; do not add it to the demo project. The target may have just completed normally, yet the **advice throws an exception**, causing the caller to **receive an error** through the interceptor chain instead of the result. Spring AOP does not automatically swallow an advice's exception just because it runs after the target.

Therefore, for non-critical auditing/metrics, define a clear error policy: log/record safely without unexpectedly breaking transactions or API contracts unless required. If auditing must succeed for a result to be returned, consider explicit business/transaction semantics rather than arbitrary side effects inside advice.

### 10.4. Transaction Commit Is Not Synonymous with `@AfterReturning`

If a method has `@Transactional`, the ordering of the transaction interceptor and a custom aspect can change when `@AfterReturning` runs relative to the commit depending on advisor order/propagation. "Target method normal return" is **not sufficient proof** that the DB transaction committed. If you need to trigger an action **after a successful commit**, use transaction synchronization / `@TransactionalEventListener(phase = AFTER_COMMIT)` according to your actual transaction configuration.

Reminder: `@Transactional` requires its own transaction management / transaction manager; `@EnableAspectJAutoProxy` alone does not enable transactional behavior.

## 11. When a Method Has Multiple Advisors

A target bean can have:

- Custom `@Around` transforming return values or catching exceptions;
- Spring transaction/cache/security advisors;
- `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After` from the same or other aspects;
- Interceptors from observability/monitoring libraries.

Therefore, when debugging you must ask **where in the chain is `@AfterReturning` observing the join point's normal return?**, and **is an outer interceptor altering the result or error?**

According to the Spring documentation, the execution order of advices within one aspect is coordinated by advice kind; `@After` has after-finally semantics; advices of the **same kind** within the same aspect have no guaranteed order solely from appearing earlier or later in the source file.

If the application needs ordering across **different aspects**, you can use `@Order` or `Ordered` and run integration tests on real service methods. Do not design **two `@AfterReturning` advices of the same kind** to rely on a specific order based merely on method name or source position.

In the demo, the two advices use independent counters and do not depend on ordering; that is why stdout is deterministic.

## 12. Spring Boot and the Difference Between Declaring an Aspect and Enabling AOP

In Spring Boot, when an appropriate AOP starter/auto-configuration is present, you typically do not need to write `@EnableAspectJAutoProxy` manually. However, you must ensure:

1. The `@Aspect` class is a Spring bean—usually `@Aspect` + `@Component` in a scanned package, or returned from a `@Bean` method.
2. The target service is also inside the Spring container.
3. The pointcut expression actually matches an interceptable method.
4. The caller goes through the Spring proxy; it does not call `this.method()`.
5. The `returning` name and type match the method outcomes being inspected.

Choose the Gradle dependency according to the **Boot major version** and Boot's dependency management, without using both at the same time:

```gradle
// Spring Boot 3.x
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

```gradle
// Spring Boot 4.x
implementation 'org.springframework.boot:spring-boot-starter-aspectj'
```

In Boot, class-based proxies are typically chosen via `spring.aop.proxy-target-class=true`. If using JDK interface proxies (`spring.aop.proxy-target-class=false`), the method must be exposed on the interface. If the target has a `final` method with CGLIB, Spring cannot intercept that method. Regardless of proxy type, self-invocation still does not route back through the proxy under standard Spring AOP.

## 13. Proper Testing Approaches

### 13.1. Checking Whether a Bean Has a Spring Proxy

```java
ResultService bean = context.getBean(ResultService.class);
System.out.println(AopUtils.isAopProxy(bean));
```

This illustrative snippet uses `context` and imports `AopUtils` as in `Main.java`. A `true` result confirms Spring returned a proxy, **it does not by itself prove `@AfterReturning` matched**. You also need a recorder/counter.

### 13.2. Separating Pointcut and Type-Binding Tests

An integration test for the demo should assert:

- Calling `lookup("A")` through the proxy increments both **normal** and **string** counters.
- Calling `available()` increments **normal** but does not increment **string**.
- Calling `warmUp()` increments **normal**.
- Calling `fail()` throws an exception without incrementing either counter.
- The return value received by the caller equals the target's return value; `@AfterReturning` does not alter it.
- A call via `new ResultService()` outside Spring does not change the Spring aspect's counters.

To avoid relying on logs, you can write tests with direct assertions:

```java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    ResultService service = context.getBean(ResultService.class);
    ReturnAspect aspect = context.getBean(ReturnAspect.class);

    service.lookup("X");
    service.available();
    service.warmUp();

    try {
        service.fail();
    } catch (IllegalStateException expected) {
        // Target threw an error; @AfterReturning must not count this call.
    }

    if (aspect.normalCount() != 3 || aspect.stringCount() != 1) {
        throw new AssertionError("Wrong @AfterReturning counters");
    }
}
```

This is an **illustrative test snippet** usable in the demo's package with an `AnnotationConfigApplicationContext` import; it creates a new context, does not replace `Main`, and is not meant to produce the stdout in section 6.5. In production tests, replace manual try/catch with JUnit `assertThrows` and a dependency-managed test assertion framework.

### 13.3. Why You Should Not Test Only with Mocks or `new`

`new ReturnAspect()` + calling `afterStringReturn("x")` directly only tests the aspect's Java method; it does not prove Spring read `@AfterReturning` and bound the result with the right type. `new ResultService()` does not go through the proxy; even if the method returns normally, the Spring advice never gets a chance to run.

**On target:** an integration test must initialize the context with the aspect bean, auto-proxy support, and the Spring target bean, invoke the method through the Spring reference, and assert events/counters.

## 14. Common Troubleshooting Table

| Symptom | Likely Cause | How to Verify in Spring |
| --- | --- | --- |
| No advice runs after normal return | Aspect is not a Spring bean, AOP enable/config missing, pointcut does not match, or caller bypasses proxy | List beans, check `AopUtils.isAopProxy`, call public method via Spring reference. |
| Parameterless advice runs, `returning` advice does not | Binding parameter type is incompatible with returned value / declared return type | Compare `Object` vs `String`, check method signatures, test each type. |
| Startup error when adding `returning` | `returning` name differs from parameter name, wrong `argNames`, conflicting pointcut bindings | Inspect root cause of Spring/AspectJ binding, align names and types. |
| `@AfterReturning` still runs despite business fallback error | Method caught the exception and returned normally | Inspect actual join point and business outcome; do not equate normal return with domain success. |
| Advice does not run on a method that throws | Expected behavior of `@AfterReturning` | Use `@AfterThrowing` to track exceptions; `@After` for after-finally. |
| Advice does not run for a `void` method | Advice binds `String` when method returns nothing, or pointcut does not match | Use the unbound form, check interception. |
| `@AfterReturning` logs, but client return value is unchanged | `@AfterReturning` does not replace the returned reference | If transformation is truly needed, see `@Around` or the business method. |
| Advice receives `null` and throws NPE | Code dereferences result without null safety | Null-check; test methods declaring reference return types. |
| Advice invocation count differs from HTTP request count | Caching/async/retries, multiple methods, self-calls, or pointcut only matches some beans | Count invocations at method entry; do not use request count as a proxy. |
| `@AfterReturning` runs when future is returned, but task later fails | Advice observes the wrapper return, not async completion | Observe future completion / Reactive signals with their respective APIs. |
| Method is `final` and Spring uses CGLIB | Proxy cannot override/intercept the method | Change entry method/class, or use JDK interface proxy if design allows. |
| Called from the same service via `this.method()` | Self-invocation bypasses the proxy | Extract to a collaborator Spring bean and inject the proxy, or advise the right entry operation. |
| Metrics/audit inside advice throws | Caller may receive an exception even though the target returned normally | Define a clear error policy, and test advice failures too. |

## 15. Workflow for Applying in a Project

1. **Choose the right event:** do you need to observe **normal method return**, or business success / transaction commit / async completion? If not normal return, another mechanism may be required.
2. **Select the method set via pointcut:** constrain package, class, method, and proxy contract. Avoid overly broad `execution(* *(..))`.
3. **Decide whether to bind:** if you only count normal returns, use `@AfterReturning("...")`; if you need to read the data, use `returning`.
4. **If binding, choose the type intentionally:** `String` selects only text results; `Object` is more flexible but needs null/type checking.
5. **Keep parameter names consistent:** `returning="result"` matches `result` on the advice; add `argNames` when needed.
6. **Register the aspect with Spring:** `@Component` or `@Bean`, in the right scope/context; enable Spring AOP support.
7. **Check the proxy boundary:** target is a Spring bean, method is interceptable, external calls go through the proxy. Exclude self-invocation/`new`.
8. **Write tests for multiple outcomes:** successful return, wrong return type, `void`, `null`, exception, and async wrapper where relevant.
9. **Review side effects:** advice does not replace the returned reference; auditing/metrics can throw errors or affect performance/transactions.
10. **Claim success only in the accurate sense:** normal method return does not guarantee commit, delivery, authorization, or end-to-end success.

## 16. End-of-Lesson Checklist

- [ ] Does the pointcut expression select the exact Spring target bean/method to observe?
- [ ] Does the aspect have `@Aspect` and is it registered with Spring via `@Component`/`@Bean`?
- [ ] Is Spring `@AspectJ` proxy support enabled with a compatible AspectJ Weaver?
- [ ] Does the caller actually invoke the target through the Spring proxy, not via `new` or `this.method()`?
- [ ] Have normal return, caught exception, thrown exception, and async completion been distinguished?
- [ ] If using `returning`, does the name match the advice parameter name and `argNames` if declared?
- [ ] Is the advice parameter type intentional and compatible with the return values to match?
- [ ] Are `void`/`null`/primitives/`Optional` tested when present in the domain logic?
- [ ] Have you avoided trying to replace the returned reference via `@AfterReturning`'s own return value?
- [ ] Are side effects on mutable returned objects, audit logging, and exceptions inside advice controlled?
- [ ] If transaction/cache/security/async advisors exist, have their actual ordering and semantics been reviewed?
- [ ] Does an integration test verify the exact advice event/counter counts and unchanged business results?

**Key takeaway:** In Spring AOP, `@AfterReturning` is for **calls through a proxy that complete normally**. `returning="result"` lets the advice **receive the return value** and **further constrain matching by parameter type**, so an advice binding `String` may run fewer times than an unbound advice even when both share the same pointcut. It **does not alter the result**; if transformation is needed, use another design such as `@Around`. Always verify the Spring bean, proxy, method outcome, and business contract.

## Official Documentation References

- [Spring Framework 6.2 — Declaring Advice / After Returning Advice and Return Binding](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Proxying Mechanisms, Self-Invocation, JDK and CGLIB](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Advice API / AfterReturningAdvice](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/advice.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
