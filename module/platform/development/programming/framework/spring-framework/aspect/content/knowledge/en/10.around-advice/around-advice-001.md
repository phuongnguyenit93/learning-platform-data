# @Around and the Role of ProceedingJoinPoint in Spring AOP

## 1. What Does @Around Solve in Spring Aspect?

In Spring AOP, an `@Aspect` can run code before or after a method of a **proxied Spring bean**. If you only need to log before a method runs, `@Before` is usually enough. If you only need to inspect a normal result, there is `@AfterReturning`. But when you want to **wrap the entire invocation**, retain local before-and-after state, decide whether to let the target run, replace arguments, replace the return value, or handle exceptions under an explicit policy, you use **`@Around`**.

For example, for a Spring service with a `find(String key)` method:
- You can measure the duration of the entire call and print the elapsed time in `finally`.
- You can directly return a cached result **without calling** the target service.
- You can normalize arguments before calling the target using `proceed(newArgs)`.
- You can let an exception propagate as-is or, when business rules allow, turn the exception into a fallback result.
- You can apply controlled retries, although in practice you should evaluate a dedicated retry mechanism.

The **core difference** of `@Around` lies in the **`ProceedingJoinPoint`** object and the **`proceed()`** call. Without `proceed()`, the inner Spring AOP interceptor chain will not automatically continue just because the target method is declared.

However, `@Around` is also the advice type with the strongest intervention power, and therefore the easiest to introduce bugs with. The Spring documentation recommends **choosing the least powerful advice type that still meets your needs**. This lesson focuses solely on `@Around` in **Spring Framework, Spring `@AspectJ`, and the proxy mechanism**, without extending to bytecode weaving or join points beyond method execution.

### Learning Objectives

After this lesson, you will be able to:
1. Explain the position of `@Around` in the Spring AOP interceptor chain.
2. Write an advice method with `ProceedingJoinPoint` as the first parameter, returning `Object` and declaring `throws Throwable`.
3. Distinguish between `proceed()`, `proceed(Object[])`, and `getArgs()`.
4. Understand the consequences of calling `proceed()` **0 times, 1 time, or multiple times**.
5. Distinguish between target completion and the final result received by the proxy's client.
6. Use `try/catch/finally` properly when measuring timing, logging, catching, and propagating exceptions.
7. Run a Java 17 + Spring Framework example to observe normal flow, argument replacement, short-circuiting, throwing, and self-invocation.
8. Avoid critical mistakes when combining `@Around` with transactions, caching, retries, and other Spring advisors.

## 2. Where Does @Around Sit in Spring AOP?

Spring AOP applies advice to **method-execution join points** of Spring-managed beans using a JDK dynamic proxy or a CGLIB proxy. A simplified call path looks like this:

```text
Client
  |
  v
Spring AOP proxy
  |
  v
@Around advice
  |
  +-- code BEFORE proceed()
  |
  +-- pjp.proceed() ------------------------------+
  |                                               |
  |                                        inner advisors
  |                                               |
  |                                               v
  |                                         target.method(...)
  |                                               |
  |                               return value or exception
  |                                               |
  +<----------------------------------------------+
  |
  +-- code AFTER proceed() (on normal return)
  +-- catch (when an exception propagates)
  +-- finally (both paths)
  |
  v
Client sees the value/exception that the advice lets pass out
```

This diagram illustrates two meanings of "around":

- **Wrapping in time:** the advice can run before, and then run after the invocation.
- **Wrapping in control:** the advice decides whether to invoke the inner part of the interceptor chain, with what arguments, and what result to return.

Calling `proceed()` is **not** Java syntax for directly calling `target.method()`. In Spring, it continues the rest of the **AOP interceptor chain**, which may include multiple other advisors before reaching the target method. Therefore, the result or exception from `proceed()` may already have been modified or short-circuited by an inner interceptor.

### 2.1. Prerequisites

For `@Around` to take effect in a plain Spring Framework application:

- The class declaring the advice must be annotated with `@Aspect` and **registered as a Spring bean** (via `@Component`, `@Bean`, or equivalent).
- `@EnableAspectJAutoProxy` must be applied in the `ApplicationContext` that creates the target bean, or the corresponding Spring Boot AOP auto-configuration must be used.
- The AspectJ libraries required for Spring to parse pointcuts must be on the classpath (typically provided via `spring-boot-starter-aop` or `aspectjweaver`).
- The target bean must be managed by Spring, have a method matching the pointcut, and be invoked **through the AOP proxy**.
- The JDK/CGLIB proxy must be able to intercept the corresponding method; self-invocation and `final`/`private` methods can cause the advice not to behave as expected.

`@Aspect` **does not automatically register a Spring component**, and a method merely annotated with `@Around` without Spring AOP infrastructure will not run on its own.

## 3. Standard Structure of @Around Advice

Common template:

```java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TimingAspect {

    @Around("execution(* com.example.service..*.*(..))")
    public Object measure(ProceedingJoinPoint pjp) throws Throwable {
        long started = System.nanoTime();

        try {
            return pjp.proceed();
        } finally {
            long elapsedNanos = System.nanoTime() - started;
            System.out.println("elapsedNs=" + elapsedNanos);
        }
    }
}
```

This is an **illustrative snippet**, not a standalone application. Appropriate Spring beans and AOP configuration are required; `elapsedNs` will differ on each run and must not be treated as fixed stdout.

### 3.1. Why Is the First Parameter ProceedingJoinPoint?

Spring requires the first parameter of an `@Around` advice method to have the type **`org.aspectj.lang.ProceedingJoinPoint`**. It extends `JoinPoint` and adds the `proceed()` capability. Advice types such as `@Before` can accept `JoinPoint` to read context, but do not have the ability to proceed in the way `ProceedingJoinPoint` does.

### 3.2. Why Return Object?

The Spring documentation recommends that around advice return `Object` because the value **returned by the advice** becomes the value seen by the caller of the proxied method. For example:

```java
Object result = pjp.proceed();
return result;
```

is the way to preserve the original return value when no transformation is needed.

**Do not declare an around advice method as `void` if the target method needs a return value:** Spring notes that an advice method with a `void` return type causes the caller to receive `null`, even when the target returned a value. This can cause confusing errors when the caller expects a `String`, `Integer`, or another object.

An `Object` advice method can also wrap a `void` target method; in that case, the effective result when using `proceed()` is typically represented as `null` in the interceptor. Code should keep `return pjp.proceed();` intact and not infer a business value from it.

### 3.3. Why throws Throwable?

`proceed()` declares `throws Throwable`. The advice method usually also declares `throws Throwable` to propagate exceptions untouched:

```java
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

Declaring only `throws Exception` cannot cover all of `Throwable` as required by the compiler signature, unless you catch/handle the rest yourself.

### 3.4. What Does the Method Return or Throw?

In `@Around`, distinguish these cases:

| Advice behavior | Target or inner interceptor chain | Caller outside the proxy |
| --- | --- | --- |
| `return pjp.proceed();` | Runs the inner chain, unless another advisor short-circuits | Receives the propagated value/exception |
| `return "CACHED";` without calling `proceed()` | Does not enter the inner chain | Receives `"CACHED"` if compatible with the return contract |
| `throw ex;` inside advice | Target may not have run or may have thrown `ex` | Caller sees the exception thrown by the advice |
| `return transform(pjp.proceed());` | Chain may run, then advice changes the result | Caller receives the transformed result |
| Catch exception then `return fallback` | Chain ran up to where the exception was thrown; advice converts the outcome | Caller may see a normal return instead of an exception |

**Preserve the Java method contract:** If the target method returns `int`, returning `null` from the advice can cause an unboxing error. If the target method returns `String`, returning an incompatible object can cause a `ClassCastException`. Spring does not automatically guarantee that your fallback has a valid business type.

## 4. What Does ProceedingJoinPoint Provide?

### 4.1. Commonly Used APIs

| API | Meaning in Spring AOP | Notes |
| --- | --- | --- |
| `pjp.proceed()` | Continues the invocation with the original arguments | Call when you want the inner chain to run |
| `pjp.proceed(Object[] args)` | Continues with the **provided argument array** | In Spring AOP, argument count and positions must match the method execution |
| `pjp.getArgs()` | Current arguments of the method invocation | No reflection needed to inspect arguments |
| `pjp.getSignature()` | Method signature information | Can call `getName()`, or cast to `MethodSignature` |
| `pjp.getThis()` | The Spring AOP proxy object | Differs from `getTarget()`, especially for JDK proxies |
| `pjp.getTarget()` | The target object behind the proxy | Do not invoke methods directly on it if you want to preserve advice |
| `pjp.getStaticPart()` | Static join point information | Useful when object context does not need to be retained |
| `pjp.toShortString()` / `toString()` | Join point description | For diagnostics; do not depend on an immutable log format |

In Spring, `getThis()` is the **proxy object** and `getTarget()` is the **target object**. They can differ in both identity and runtime class. For example, a JDK proxy only implements interfaces, while the target is an instance of the implementation class.

### 4.2. Reading Method Name and Arguments

```java
@Around("execution(* com.example.service..*.*(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    String name = pjp.getSignature().getName();
    Object[] args = pjp.getArgs();

    System.out.println("method=" + name + ", args=" + args.length);
    return pjp.proceed();
}
```

This snippet must be placed inside an `@Aspect` class and registered in the context. `getArgs()` lets you read data, but **you should not log sensitive data** such as tokens, passwords, personal information, payment cards, or objects containing large payloads. For systems handling sensitive data, log safe identifiers or data types instead of printing full argument values.

### 4.3. Reading Typed Signature Information

```java
import org.aspectj.lang.reflect.MethodSignature;

MethodSignature signature = (MethodSignature) pjp.getSignature();
String methodName = signature.getMethod().getName();
Class<?> returnType = signature.getReturnType();
Class<?>[] parameterTypes = signature.getParameterTypes();
```

The snippet above sits inside an `@Around` advice; these values are used for diagnostics when signature details are needed. When a method is declared on an interface while annotations sit on the implementation, keep Spring method resolution and proxy type in mind; do not assume the method reflected from the proxy is always the implementation method with all annotations from source code.

## 5. proceed(): Proceeding Once, Never, or Multiple Times

`ProceedingJoinPoint.proceed()` **continues the part of the interceptor chain inside the currently executing advice**. It does not necessarily invoke the target immediately: an inner advice may still return a result early or throw an exception.

| Call count | What happens to the inner chain | Important notes |
| --- | --- | --- |
| **Once** | Forwards one pass; usually reaches the target unless blocked by another interceptor | Default pattern when you only want to observe or measure |
| **Zero times** | Does not proceed down this invocation branch | Advice must return a value matching the contract or explicitly throw an exception; e.g., cache hit/authorization gate |
| **Multiple times** | May re-run inner interceptors and the target on each pass | Suitable only for bounded retry/replay with clear error conditions and safe side effects |

Example of an advice that only observes without altering business logic:

~~~java
@Around("execution(* demo.GreetingService.greet(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("enter");
    return pjp.proceed();
}
~~~

This is a fragment that must sit inside a Spring-managed `@Aspect`. If the target throws an exception, `proceed()` propagates the error to the caller; it does not silently convert it into a default result. The lesson on continuing the chain dives deep into a single pass; the lessons on short-circuiting and multiple passes separately explain the effects on advisors, the target, and side effects.

## 6. proceed(Object[]): Replacing Arguments on Invocation

The `pjp.proceed(Object[] replacement)` overload allows Spring AOP to **forward the invocation with new arguments**. In proxy-based Spring AOP, this array corresponds in full to the target method's parameters, in the exact order and with compatible types; it is not an array of variables bound in the advice signature.

Example in an `@Around` advice specifically targeting methods whose first parameter is `String`:

~~~java
Object[] oldArgs = pjp.getArgs();
Object[] nextArgs = oldArgs.clone();
nextArgs[0] = ((String) oldArgs[0]).trim();
return pjp.proceed(nextArgs);
~~~

If the method takes `(String, int)`, the forwarded array still needs **two elements**, and the second element must be compatible with `int` (typically a boxed `Integer`). `clone()` performs only a shallow copy of the array; it does not copy mutable objects inside. AspectJ compiler/weaver argument binding rules can differ from Spring proxy AOP, so do not carry examples across the two mechanisms without verification. The dedicated `proceed(Object[])` lesson covers arity, binding, and type-mismatch cases.

## 7. return, throw, catch, and finally in @Around

The value returned by `@Around` becomes the result observed by the caller at the proxy boundary. For pure observation, **returning the exact value from `proceed()` and letting exceptions propagate** is the safe choice; do not accidentally return `null` for an `int` method or lose error details.

When cleanup or latency measurement is needed for both success and failure paths, wrap `proceed()` in `try/finally`:

~~~java
long start = System.nanoTime();
try {
    return pjp.proceed();
} finally {
    long elapsedNs = System.nanoTime() - start;
    System.out.println("elapsedNs=" + elapsedNs);
}
~~~

This is a timing fragment; the nanosecond count is not fixed. `finally` runs once the `try` block has been entered and `proceed()` returns or throws an exception, yet the code inside `finally` itself must also be designed not to corrupt the business outcome.

`catch` should convert an error into a fallback only when **the method contract permits it** and that error category is explicitly specified. Returning a fallback causes outer interceptors to see a normal return instead of an exception. The lessons on return contracts, `try/catch/finally`, and avoiding swallowed exceptions examine the consequences for primitives, checked exceptions, and transactions in turn.

## 8. Standalone Runnable Example: Five Clear Scenarios

### 8.1. Goals and Environment

The following project uses **Java 17+**, **Spring Framework 6.1.14**, **AspectJ Weaver 1.9.22.1**, and Gradle; no Spring Boot or database is needed. One aspect handles a single `GreetingService` bean with these cases:

1. `greet("Bob")`: calls `proceed()` normally.
2. `greet("alias")`: replaces the input with `"Alice"` when calling `proceed(Object[])`.
3. `greet("skip")`: returns `"SKIPPED"` without calling the target.
4. `fail()`: target throws `IllegalStateException`, the aspect logs and rethrows.
5. `outer()`: internally calls `this.greet("inside")`, so no second `@Around` invocation occurs for the inner call.

The log output is designed to be **deterministic**, without printing environment-dependent durations, making it easy to compare against expected stdout.

### 8.2. Project Structure

```text
spring-around-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/around/
    ├── GreetingService.java
    ├── AroundAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 8.3. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'spring-around-demo'
```

`build.gradle`:

```groovy
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
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.around.DemoApplication'
}
```

`spring-context` provides IoC, `AnnotationConfigApplicationContext`, `@Bean`, and `@Configuration`; `spring-aop` contains the proxying infrastructure; `aspectjweaver` is the library Spring needs to parse `@AspectJ` pointcuts.

### 8.4. Target Service

File `src/main/java/demo/around/GreetingService.java`:

```java
package demo.around;

public class GreetingService {

    public String greet(String name) {
        System.out.println("target:greet:" + name);
        return "Hello " + name;
    }

    public void fail() {
        System.out.println("target:fail");
        throw new IllegalStateException("boom");
    }

    public void outer() {
        System.out.println("target:outer");
        greet("inside");
    }
}
```

`greet`, `fail`, and `outer` are all public and non-final, so they can be advised by a class-based proxy if called through the proxy. The line `greet("inside")` inside `outer` is a **self-invocation** of the target; it does not go back through the proxy.

### 8.5. @Around Aspect and ProceedingJoinPoint

File `src/main/java/demo/around/AroundAspect.java`:

```java
package demo.around;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class AroundAspect {

    @Around("execution(public * demo.around.GreetingService.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        System.out.println("around:before:" + method);

        try {
            if ("greet".equals(method)
                    && "skip".equals(pjp.getArgs()[0])) {
                System.out.println("around:short-circuit:greet");
                return "SKIPPED";
            }

            Object result;
            if ("greet".equals(method)
                    && "alias".equals(pjp.getArgs()[0])) {

                Object[] newArgs = pjp.getArgs().clone();
                newArgs[0] = "Alice";
                result = pjp.proceed(newArgs);
            } else {
                result = pjp.proceed();
            }

            System.out.println("around:after:" + method);
            return result;
        } catch (Throwable ex) {
            System.out.println("around:throw:" + method
                    + ":" + ex.getClass().getSimpleName());
            throw ex;
        } finally {
            System.out.println("around:finally:" + method);
        }
    }
}
```

**Why this code is safe within the demo's scope:**
- `method.equals("greet")` is written as `"greet".equals(method)` with a short-circuiting `&&` condition, so the code accesses `pjp.getArgs()[0]` only for `greet`, a method with one parameter. `fail`/`outer` do not access a nonexistent index.
- `"skip"` returns directly before `proceed`; `finally` still runs due to Java semantics.
- `"alias"` clones the argument array and calls `proceed(newArgs)`; the target receives `"Alice"` even though the caller passed `"alias"`.
- The normal case calls `proceed()` once and preserves the result.
- The target-throw case catches to log, then rethrows; the advice does not swallow the exception.
- `finally` prints one line for every return/throw path that the advice actually entered.
- The pointcut applies only to `GreetingService` and does not advise `AroundAspect` or Spring infrastructure.

In production, do not branch on string method names like this demo to implement different policies; use **named pointcuts, method annotations, or separate advisors**. The demo intentionally combines these branches in one advice so learners can see each capability of `ProceedingJoinPoint`.

### 8.6. Registering Spring Beans and Enabling AOP

File `src/main/java/demo/around/AppConfig.java`:

```java
package demo.around;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public GreetingService greetingService() {
        return new GreetingService();
    }

    @Bean
    public AroundAspect aroundAspect() {
        return new AroundAspect();
    }
}
```

`@Bean aroundAspect()` registers the aspect as a Spring bean; `@Aspect` tells Spring how to interpret the advice. `@EnableAspectJAutoProxy(proxyTargetClass=true)` enables the auto-proxy creator and prefers class-based proxies, allowing us to retrieve the service by `GreetingService.class`. This is plain Spring Framework, so it does not rely on Spring Boot defaults.

### 8.7. Main Running All Branches

File `src/main/java/demo/around/DemoApplication.java`:

```java
package demo.around;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            GreetingService service =
                    context.getBean(GreetingService.class);

            System.out.println(
                    "proxy=" + AopUtils.isAopProxy(service));

            System.out.println("result=" + service.greet("Bob"));
            System.out.println("result=" + service.greet("alias"));
            System.out.println("result=" + service.greet("skip"));

            try {
                service.fail();
            } catch (IllegalStateException ex) {
                System.out.println(
                    "caller:fail:" + ex.getMessage());
            }

            service.outer();
        }
    }
}
```

### 8.8. Run Command and Exact Stdout

From the directory containing `build.gradle`:

```bash
gradle run
```

If Gradle Wrapper is present, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

The lines below are the **output printed by the Java program itself**, excluding Gradle or system logging:

```text
proxy=true
around:before:greet
target:greet:Bob
around:after:greet
around:finally:greet
result=Hello Bob
around:before:greet
target:greet:Alice
around:after:greet
around:finally:greet
result=Hello Alice
around:before:greet
around:short-circuit:greet
around:finally:greet
result=SKIPPED
around:before:fail
target:fail
around:throw:fail:IllegalStateException
around:finally:fail
caller:fail:boom
around:before:outer
target:outer
target:greet:inside
around:after:outer
around:finally:outer
```

### 8.9. Mapping Each Call to proceed

| Caller invocation | Advice action | Did target run? | Caller observes |
| --- | --- | --- | --- |
| `greet("Bob")` | `proceed()` with original args | Yes: `target:greet:Bob` | `Hello Bob` |
| `greet("alias")` | `proceed(new Object[]{"Alice"})` | Yes: `target:greet:Alice` | `Hello Alice` |
| `greet("skip")` | Early return, no `proceed` | **No** | `SKIPPED` |
| `fail()` | `proceed()` then log/rethrow | Yes, target throws | `IllegalStateException("boom")` |
| `outer()` | `proceed()`, target calls `this.greet` | Both `outer` and `greet` run in target | No nested around advice for `greet("inside")` |

**Note on the `outer()` path:** The Spring AOP proxy advice matches the `outer` method called by the caller. However, the `greet("inside")` call originates **inside the target**, so there is no second `around:before:greet` line. It is not that `@Around` is unaware of `greet`; the internal call path bypassed the proxy.

**Note on the `skip` path:** Even though `greet` is a Spring bean method with a matching pointcut, Spring does not force the target to run. The advice returned a result before `proceed()`, demonstrating `@Around`'s control authority.

## 9. How Does @Around Differ from @Before, @AfterReturning, @AfterThrowing, and @After?

| Need | Advice type to consider first | Why |
| --- | --- | --- |
| Only log before the method runs | `@Before` | No need to manage `proceed()` yourself |
| Only read normal return value | `@AfterReturning` | Has `returning` binding without wrapping the invocation |
| Only log escaping exceptions | `@AfterThrowing` | Has `throwing` binding, clearly indicating failure outcome |
| Cleanup on normal completion/exception | `@After` | After-finally semantics without altering flow |
| Measure duration of a single invocation in one scope | `@Around` | Local `started` variable spans before–after, using `finally` |
| Replace input before target runs | `@Around` | `proceed(newArgs)` |
| Return cache/fallback instead of target | `@Around` | Can short-circuit |
| Controlled retry | `@Around` or a dedicated retry interceptor | Can call `proceed()` multiple times |

Spring principle: **use the least powerful advice that meets the requirement**. There is no reason to use `@Around` just for `System.out.println("before")` when `@Before` is enough.

## 10. Combining @Around with Spring Transactions, Caching, and Retry

A Spring bean can be simultaneously affected by application-declared `@Around` advice and interceptors provided by transaction, caching, or retry infrastructure. **Position in the chain determines what is measured and what gets re-executed.**

- **Cache:** if an inner cache interceptor returns a cache hit without proceeding, an outer `@Around` still runs, but the target does not run. If the cache is on the outside and short-circuits, inner advice may not be called at all.
- **Transaction:** when retry sits outside transaction advice, each attempt *may* pass through its own transaction interceptor depending on propagation/transaction configuration; a transaction outside retry can wrap multiple attempts in a single transaction. Do not assume every attempt always gets a new transaction.
- **Retry:** calling `proceed()` multiple times can repeat DB writes, message sends, or payment service calls. An exception occurring after a side effect does not prove the earlier operation failed.
- **Ordering:** `@Order`/advisor order affects who enters first and which result is observed. Source annotation order is not evidence of runtime order.

When testing an aspect, measure separately **how many times the caller calls the proxy**, **how many times the advice is entered**, and **how many times the target or side effect executes**. The lessons on multiple-`proceed()`, retry side effects, and preserving business contracts expand on these scenarios with concrete tests.

## 11. Common Spring @Around Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Target method does not run, yet caller gets a value | Advice returned a result without calling `proceed()` | Check early return branches; short-circuit only intentionally |
| Caller receives `null` even though target returns `String` | Around advice declared `void` or omitted returning the result | Use `Object`, `return pjp.proceed()` |
| Exception disappears | Accidental `catch` returning a fallback | Rethrow the exception unless a fallback policy applies |
| Log after `proceed()` is missing when target throws | Code after proceed runs only on normal return | Move cleanup/total-time metrics into `finally` |
| `ArrayIndexOutOfBoundsException` in advice | Accessing `pjp.getArgs()[0]` on a zero-parameter method | Narrow pointcut/arity or check args first |
| `IllegalArgumentException` on `proceed(newArgs)` | Wrong number of args or incompatible types | Supply all arguments in the right order and types |
| `ClassCastException` in caller | Advice returns an object incompatible with target return type | Preserve the return contract |
| Duplicate side effects | Calling `proceed()` multiple times | Evaluate idempotency and retry boundaries |
| Aspect does not run on `this.method()` | Self-invocation bypasses the Spring proxy | Extract a collaborating bean and call through the proxy |
| Aspect does not run on beans created with `new` | No Spring AOP post-processing | Inject the bean from the context |
| `final`/`private` method is not advised by CGLIB | Cannot be overridden | Choose an appropriate method/proxy design |
| Timing suddenly includes retry/cache | Advisor order changed the measured scope | Define metric boundaries and test ordering |
| `@Around` method never triggers | Aspect is not a Spring bean or AOP is not enabled | Check `@Bean`/`@Component` and `@EnableAspectJAutoProxy` |
| Pointcut is too broad | `execution(* *(..))` without type/package bounds | Combine with `within`/service patterns |
| AspectJ weaving behaves differently on `proceed(Object[])` | Spring proxy and compiled AspectJ advice have different args rules | Consult docs on ordered binding if portability is needed |

### Do Not Log All Arguments Unchecked

`pjp.getArgs()` returns the actual objects; many service arguments may contain passwords, bearer tokens, personal content, or large structures. Do not automatically run `Arrays.toString(pjp.getArgs())` across the entire service layer in production. Use allowlists, masking, and minimal metadata, while also considering serialization/`toString` overhead.

## 12. Debugging Checklist When @Around Appears Not to Work

1. **Is the aspect registered by Spring?** Does the class have `@Aspect` and is it created via `@Component`/`@Bean`? `@Aspect` alone does not register a bean.
2. **Is AOP enabled in the context owning the target?** Is `@EnableAspectJAutoProxy` or proper Boot AOP auto-configuration present?
3. **Does a proxy actually exist?** Check `AopUtils.isAopProxy(bean)` and, if needed, `isJdkDynamicProxy`/`isCglibProxy`.
4. **Does the pointcut match the method?** Are `execution(...)`, package/type/visibility/overloads accurate?
5. **Does the call path go through the proxy?** Is the client calling the Spring-managed bean or creating it with `new`? Does the target use `this.otherMethod()`?
6. **Is the method validly proxyable?** Are a `final` class, `private`/`final` method, or an interface not exposing the method causing limits?
7. **Did the advice call `proceed()`?** Was there an earlier `return` branch or an exception from before-code?
8. **Are the types and count of `proceed(newArgs)` correct?** Especially when the method has multiple parameters or varargs.
9. **Does the advice return the right result / throw the right exception?** Avoid `void` around advice or unintentional exception swallowing.
10. **Could advisor order/caching/transactions change the outcome?** Is an outer interceptor short-circuiting so the around advice is never called?
11. **Is there multiple proceed or retry?** Check how many times the target runs and its side effects.
12. **Do integration tests use a real Spring context?** Unit tests calling the target directly via `new` do not prove whether AOP works.

Example diagnostic snippet (assuming `ApplicationContext context` and a bean named `greetingService`):

```java
Object bean = context.getBean("greetingService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Requires importing `org.springframework.aop.support.AopUtils`. Having a proxy is not enough to prove that **every method** or **every call** passes through the advice; you still must verify the pointcut and the call path.

## 13. Safe @Around Design Rules

- **Keep it simple:** if you only need pre/post events, consider `@Before`, `@AfterReturning`, `@AfterThrowing`, or `@After`.
- **Default to proceeding once:** change to 0/n times only with clear goals and tests.
- **Preserve results and exceptions:** `return pjp.proceed()` on the normal path; `throw ex` after logging unless fallback is intentional.
- **Use `finally` for cleanup:** ensure the advice does not skip timing measurement when a method throws.
- **Follow the API:** first parameter `ProceedingJoinPoint`, return `Object`, `throws Throwable`.
- **Replace arguments carefully:** clone the array, match arity/types, and test impacts on cache/transactions/advisors.
- **Avoid non-thread-safe state:** use local variables per invocation; if a singleton aspect has mutable fields, manage concurrency.
- **Protect data:** do not log sensitive payloads from `getArgs()` or unbounded results/exceptions.
- **Define observation points:** timing outside cache/retry differs from timing a target attempt.
- **Test both normal and error paths:** return values, null, exceptions, short-circuiting, replacement, and self-invocation.
- **Do not instantiate targets with `new`:** let Spring bean proxies manage cross-cutting behavior.

## 14. Conclusion

In Spring Aspect, **`@Around` is the advice that wraps a method invocation, and `ProceedingJoinPoint` is the tool for controlling the inner chain**. The three operations that define its semantics are:

- `proceed()`: continue with the original arguments;
- `proceed(Object[])`: continue with valid replaced arguments;
- **not calling `proceed()`**: intentionally skip the target and return an advice-created result or throw an exception.

The advice can observe both returns and throws and use `finally` for cleanup, yet it can also introduce subtle bugs if it accidentally swallows exceptions, returns the wrong type, alters arguments unexpectedly, or repeats targets with side effects.

With Spring AOP, always ask **“does the call go through a Spring-managed proxy?”** before analyzing `@Around`. `ProceedingJoinPoint` does not replace the proxy boundary, does not fix self-invocation, and does not turn constructors or `private`/`final` methods into join points intercepted by Spring AOP.

### Official Spring Documentation

- [Spring Framework — Declaring Advice: Around Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@Around` method signatures, `ProceedingJoinPoint`, `proceed()`/`proceed(Object[])`, return values, zero/one/many proceed semantics, advice ordering.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): advice types and the control role of around advice.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): enabling proxies and registering Spring `@Aspect` beans.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation, and limitations.
- [Spring Framework — Advice API](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html): `MethodInterceptor` and how `proceed` advances through the interceptor chain.
