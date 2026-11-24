# Wrapping Success and Exception Paths With try/catch/finally in Spring @Around

## 1. The Problem: An Invocation Can Return, Throw, or Recover

When a Spring service is wrapped by an `@Around` advice, a method call can have several outcomes:

- **Normal return:** the method finishes and returns a value, including `null`.
- **Exceptional completion:** the method or an inner interceptor throws an exception outward.
- **Recovered completion:** the inner portion threw an exception, yet `@Around` catches it and intentionally returns a valid fallback value.
- **Early return:** `@Around` decides not to call `proceed()`; the target and inner interceptors do not run for that invocation.

Using `try/catch/finally` properly inside `@Around` lets you **observe each path, preserve results/exceptions by default, and always perform cleanup** when execution exits the advice under standard Java rules.

This is **Spring Aspect** knowledge: `@Around` sits inside the interceptor chain of a **Spring AOP proxy**, not a `try` block wrapping arbitrary Java calls everywhere in the program.

### Core Pattern

```java
@Around("execution(* com.example.app.service..*.*(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();

    try {
        Object result = pjp.proceed();
        return result;
    } catch (Throwable failure) {
        throw failure;
    } finally {
        long duration = System.nanoTime() - started;
        // Record duration or clean up advice-managed state.
    }
}
```

This is an **illustrative snippet** that must sit inside a Spring `@Aspect` bean with appropriate imports and AOP configuration. It demonstrates three key points:

1. `pjp.proceed()` asks **the rest of the Spring interceptor chain** to continue; only when the chain reaches the target does the business method actually execute.
2. `catch` can observe and handle exceptions escaping from `proceed()`; unless you intentionally transform the outcome, **rethrow** the exception.
3. `finally` runs when control flow exits `try` via return or throw, regardless of whether the caller ultimately receives a normal value or an exception. It does not run only on the error path.

**Scope:** Spring Framework, Spring `@AspectJ` annotation style, proxy-based AOP, `ProceedingJoinPoint`, and outcomes observed by the proxy's caller. Does not extend to AspectJ compile-time weaving or join points unsupported by Spring AOP such as constructors or field access.

## 2. Proper Flow Diagram of Spring @Around

```text
Client
  |
  v
Spring AOP proxy
  |
  v
@Around advice
  |
  +-- Code before try/proceed
  |
  +-- try {
  |      pjp.proceed() ---------> Inner advisors
  |                                  |
  |                                  v
  |                              Target method
  |                                  |
  |                         +--------+--------+
  |                         |                 |
  |                      return              throw
  |                         |                 |
  |                         v                 v
  |               try receives result   catch receives exception
  |                         |                 |
  |                   return result     rethrow or fallback
  |                         |                 |
  |                         +--------+--------+
  |                                  |
  +-- finally: clean up state / record total duration
  |
  v
Caller receives value or exception emitted by the advice
```

Two outcome layers must be distinguished:

- **Outcome of `proceed()`:** the inner interceptor chain returns a normal result or throws an exception.
- **Outcome of the invocation seen from outside the advice:** may differ if `catch` returns a fallback, the advice modifies the result, or the advice throws a new exception.

For example, the target throws `IllegalStateException`, yet an outer `@Around` catches the exception and returns `"FALLBACK"`: the caller may **not receive an exception**, even though the target failed. If a Spring transaction interceptor sits inside and already processed rollback, returning a fallback in an outer advice **does not undo the rollback**. Conversely, when the transaction interceptor sits outside and sees only a normal return, the rollback behavior can differ. Thus, handling exceptions in an aspect is never merely a logging decision.

### A Spring Proxy Is a Required Condition

`@Around` does not run if:
- You instantiate the target directly with `new Service()` outside Spring.
- The target calls `this.otherMethod()`: self-invocation goes straight to the target.
- The method does not match the pointcut or the target is not AOP-proxied.
- The method cannot be intercepted by the proxy due to visibility/type constraints, such as `private`/`final` under CGLIB.
- An **outer** interceptor short-circuits before reaching your `@Around`.

Therefore, when debugging "finally did not run," check **whether the advice was entered at all**, not just `finally` syntax.

## 3. Exact Roles of try, catch, and finally

### 3.1. try: Run the Chain and Hold the Result

```java
Object result = pjp.proceed();
return result;
```

`proceed()` is not simply calling an ordinary Java method; in Spring AOP, it advances through the remaining advisors before reaching the target unless an interceptor short-circuits.

On the normal path:
- `proceed()` returns a value compatible with the target method contract.
- `return result` preserves the reference seen by the proxy's caller.
- `finally` still runs **before** the caller receives the result.

On the exceptional path:
- `proceed()` throws an exception.
- Statements after it inside `try` are skipped.
- Java searches for a matching `catch`; `finally` still runs when leaving the block.

### 3.2. catch: Classify Exceptions and Decide Intentionally

```java
try {
    return pjp.proceed();
} catch (IOException ex) {
    // I/O failure case.
    throw ex;
} catch (RuntimeException ex) {
    // Unchecked failure case.
    throw ex;
}
```

This snippet requires importing `java.io.IOException` and belongs inside an `@Around` method declaring `throws Throwable`. Choosing the catch type is a meaningful decision:
- `catch(IOException ex)` catches only `IOException` or its subtypes.
- `catch(RuntimeException ex)` catches runtime exceptions.
- `catch(Throwable ex)` catches `Error` and all throwables as well; it is very broad, so it fits observation + **rethrow intact**, not swallowing all errors.

**Best practice for tracing/metrics:** without an explicit recovery policy, `catch` only records the exception and executes `throw ex`, keeping the original exception type, stack trace, and cause intact. Do not wrap it in `new RuntimeException(ex)` because that alters the error contract.

### 3.3. finally: Does It Run Even When Returning From catch?

Yes. Java executes `finally` whenever control leaves a `try`/`catch` block via `return` or `throw` during normal stack unwinding.

```java
try {
    return pjp.proceed();
} catch (IllegalStateException ex) {
    return "FALLBACK";
} finally {
    System.out.println("cleanup");
}
```

When `proceed` throws `IllegalStateException`, the advice enters `catch`, selects `"FALLBACK"`, **runs `finally`**, and only then returns that result to the caller.

### 3.4. Which Path Triggers Which Callback?

| Situation inside `@Around` | `catch` | `finally` | Caller observes |
| --- | --- | --- | --- |
| `proceed()` returns `"OK"` | No | Yes | `"OK"` |
| `proceed()` returns `null` | No | Yes | `null` |
| `proceed()` throws `IOException`, advice rethrows | Matching catch | Yes | `IOException` |
| `proceed()` throws `IllegalStateException`, advice rethrows | Matching catch | Yes | `IllegalStateException` |
| `proceed()` throws `IllegalStateException`, advice returns fallback | Matching catch | Yes | Fallback value |
| Advice returns right inside `try` without calling `proceed()` | No | Yes | Advice-created result |
| Advice throws inside `try` before `proceed()` | Matching catch if present | Yes | Exception or fallback |
| Outer interceptor does not forward to this advice | Advice not entered | No | Depends on outer interceptor |

These outcomes are **from the perspective of the advice under consideration**. If other advices exist outside and inside, they may observe different outcomes.

## 4. Proper Timing and Logging Recipes

### 4.1. Use finally, Avoid Logging Only After proceed

Incomplete approach:

```java
long started = System.nanoTime();
Object result = pjp.proceed();
System.out.println("elapsed=" + (System.nanoTime() - started));
return result;
```

If `proceed()` throws an exception, the duration log line is skipped. Metrics then include only normal invocations; failed calls (which often take longer) are missing.

Proper approach:

```java
long started = System.nanoTime();
try {
    return pjp.proceed();
} finally {
    long elapsed = System.nanoTime() - started;
    System.out.println("elapsedNs=" + elapsed);
}
```

If you need to distinguish normal vs. failed calls, you can add a local flag and `catch`:

```java
long started = System.nanoTime();
boolean failed = false;
try {
    return pjp.proceed();
} catch (Throwable ex) {
    failed = true;
    throw ex;
} finally {
    record(pjp.getSignature().getName(),
           failed,
           System.nanoTime() - started);
}
```

Here `record(...)` is a hypothetical helper, not a Spring API; it must be defined in the aspect or an appropriate helper. **Use per-invocation local variables**, never a mutable singleton field such as `boolean failed` inside a Spring `@Aspect`; the same aspect instance can be shared across concurrent request threads.

### 4.2. Measuring Outside or Inside Cache/Transaction?

Suppose the same method is advised by logging `@Around` and caching:

```text
Client -> logging @Around -> cache interceptor -> target
```

If `@Around` sits outside the cache, it can record cache hits even when the target does not run. If the cache interceptor sits outside, a cache hit can return immediately and **never enter the inner logging advice**.

Similarly, duration outside a transaction interceptor can include transaction handling overhead; duration inside measures a narrower scope. Name metrics according to their boundary, e.g., `service_proxy_duration` vs. `target_method_duration`.

Do not assume "@Around is always outside transaction/cache" without verifying **advisor precedence** via `@Order`/`Ordered` or corresponding configuration.

## 5. Catch Then Rethrow: Observing Errors Without Altering Contracts

An observability aspect should follow this default policy:

```java
@Around("execution(* com.example.app.service..*.*(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (Throwable ex) {
        System.out.println("errorType="
            + ex.getClass().getSimpleName());
        throw ex;
    } finally {
        System.out.println("invocationFinished");
    }
}
```

This example observes both checked and unchecked exceptions from `proceed()`. Never do this:

```java
catch (Throwable ex) {
    System.out.println("error");
    return null;
}
```

because this **swallows every throwable**, including critical system errors, and returns `null` even when the caller expects a primitive or another required result.

### Checked and Unchecked Exceptions in Spring Proxies

- `IOException` is a checked exception; the interface/target method should declare `throws IOException` if it is part of the contract.
- `IllegalStateException` is unchecked; no `throws` clause is needed.
- With JDK dynamic proxies, a checked exception not declared in the interface method's `throws` clause can be wrapped in `UndeclaredThrowableException` when leaving the proxy. This is one reason to uphold Java contracts and inspect exception causes when using JDK proxies.
- Do not confuse `@AfterThrowing`'s ability to bind `Throwable` with a guarantee that every checked exception always reaches the caller in its original type under every proxy setup.

## 6. Catch Then Return Fallback: When Is It Justified?

A fallback can be valid when:
- The method is a **read-only query** permitted to return backup data.
- A remote service is temporarily unreachable yet the business domain has a safe cached value.
- The caller contract allows a substitute value and has a way to indicate it is not the freshest result.
- There is an explicit policy covering recoverable exception types, data staleness limits, logging, and alerting.

Example:

```java
@Around("execution(public String com.example.app.service.LookupService.lookup(..))")
public Object fallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return "NOT_AVAILABLE";
    } finally {
        System.out.println("lookupFinished");
    }
}
```

This illustrative snippet is **valid only for a `String`-returning method when the business accepts `"NOT_AVAILABLE"`**. If the method returns `int`, returning a string violates the return contract. If the method updates a database or transfers money, swallowing the exception can trick the caller into thinking the operation succeeded.

An intentional fallback should be measured as two distinct counters:
- `inner_failure_count`: `proceed()` threw an exception.
- `proxy_normal_return_count`: the advice converted the exception into a normal return for the caller.

Both may **increment in a single invocation**. Do not collapse them into a naive success/failure label that hides this distinction.

### What Happens to @AfterReturning and @AfterThrowing?

In a Spring AOP proxy, advice at **different positions** observes the outcome at its own point in the interceptor chain:

```text
Outer @AfterReturning / @AfterThrowing
         |
         v
Fallback @Around
         |
         v
Inner @AfterReturning / @AfterThrowing
         |
         v
Target
```

When the target throws, inner `@AfterThrowing` can observe the exception. If the fallback around catches it and returns, outer `@AfterReturning` can observe a normal completion instead of an exception.

Therefore, never state "whenever the target throws, every `@AfterThrowing` runs"; always specify where the advisor sits and whether the chain passed through it.

### Never Use return Inside finally

The following example is a severe anti-pattern:

```java
try {
    return pjp.proceed();
} finally {
    return "OVERRIDDEN";
}
```

A `return` inside `finally` **overrides** both the return value and any exception being propagated out. It can swallow `IOException` or `IllegalStateException`, erase the root cause, break rollbacks, and fabricate fake results. If cleanup also throws an exception, the cleanup exception can mask the original exception.

To preserve semantics, perform only flow-safe cleanup/logging inside `finally`; when cleanup can fail, design explicit error/suppressed-exception handling rather than silently altering the business method's outcome.

## 7. Runnable Example: Normal, Null, Checked, Unchecked, and Fallback

The example below uses **Java 17+, Spring Framework 6.1.14, AspectJ Weaver 1.9.22.1, and Gradle**. Plain Spring Framework is used so proxy and advice mechanics are clear without depending on Spring Boot AOP auto-configuration.

### 7.1. Project Structure

```text
spring-around-flow/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/flow/
    ├── TaskService.java
    ├── FlowAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 7.2. Gradle Configuration

`settings.gradle`:

```groovy
rootProject.name = 'spring-around-flow'
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
    mainClass = 'demo.flow.DemoApplication'
}
```

`spring-context` provides the IoC container; `spring-aop` holds the Spring AOP proxy infrastructure; `aspectjweaver` provides components Spring needs to parse pointcuts. No web server or database is needed.

### 7.3. Target Returning Results or Throwing Two Exception Types

`src/main/java/demo/flow/TaskService.java`:

```java
package demo.flow;

import java.io.IOException;

public class TaskService {

    public String execute(String mode) throws IOException {
        System.out.println("target:" + mode);

        if ("ok".equals(mode)) {
            return "SAVED";
        }
        if ("empty".equals(mode)) {
            return null;
        }
        if ("checked".equals(mode)) {
            throw new IOException("offline");
        }
        if ("unchecked".equals(mode)) {
            throw new IllegalStateException("broken");
        }
        if ("recover".equals(mode)) {
            throw new IllegalStateException("retryable");
        }
        return "UNKNOWN";
    }

    public void selfCall() throws IOException {
        System.out.println("target:selfCall");
        String value = execute("ok");
        System.out.println("target:selfResult:" + value);
    }
}
```

`TaskService` is the Spring target bean, not yet a proxy when instantiated with `new` inside `@Bean`. `execute` is a public non-final method declaring checked `IOException` per contract. `selfCall()` is also public, yet `execute("ok")` inside it is a direct **self-invocation** on the target.

### 7.4. Aspect Wrapping Five Paths With try/catch/finally

`src/main/java/demo/flow/FlowAspect.java`:

```java
package demo.flow;

import java.io.IOException;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class FlowAspect {

    @Around(
        "execution(public String demo.flow.TaskService.execute(String))"
    )
    public Object aroundExecute(ProceedingJoinPoint pjp) throws Throwable {
        String mode = (String) pjp.getArgs()[0];
        System.out.println("around:enter:" + mode);

        try {
            Object result = pjp.proceed();
            System.out.println("around:normal:" + mode
                    + ":" + String.valueOf(result));
            return result;

        } catch (IOException ex) {
            System.out.println("around:checked:" + mode
                    + ":" + ex.getMessage());
            throw ex;

        } catch (IllegalStateException ex) {
            System.out.println("around:unchecked:" + mode
                    + ":" + ex.getMessage());

            if ("recover".equals(mode)) {
                System.out.println("around:fallback:" + mode);
                return "FALLBACK";
            }
            throw ex;

        } finally {
            System.out.println("around:finally:" + mode);
        }
    }
}
```

Meaning of each branch:
- `try` calls `proceed()` **exactly once**. This call advances into the inner chain and then to the target.
- `"ok"` returns `"SAVED"`, the advice logs `around:normal:ok:SAVED`, and returns that exact result.
- `"empty"` returns `null`, the advice logs `around:normal:empty:null`, and returns `null`. This is still normal completion.
- `"checked"` throws `IOException`, the advice enters the checked catch block, logs, and **rethrows**.
- `"unchecked"` throws `IllegalStateException`, the advice logs and **rethrows** because it is not in recover mode.
- `"recover"` throws `IllegalStateException`, the advice logs and returns `"FALLBACK"` per the demo policy. The caller **does not receive** this `IllegalStateException`.
- `finally` logs for all five cases that entered the advice, including returning from catch.
- `mode`/`result` exist strictly per invocation; there is no mutable state shared across threads in the singleton aspect.

This catch structure is **pedagogical**. In production, do not decide fallbacks from a generic string mode unless business policy calls for it; use distinct exception types, marker annotations, narrower pointcuts, or explicit retry/fallback abstractions.

### 7.5. Configuring ApplicationContext and Enabling AOP

`src/main/java/demo/flow/AppConfig.java`:

```java
package demo.flow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TaskService taskService() {
        return new TaskService();
    }

    @Bean
    public FlowAspect flowAspect() {
        return new FlowAspect();
    }
}
```

`@Aspect` only marks the class containing advice; `@Bean` registers the aspect instance in the Spring container. `@EnableAspectJAutoProxy` activates the auto-proxy creator. `proxyTargetClass=true` requests a class-based proxy so the client can retrieve the bean by `TaskService.class`. Component scanning is not needed.

### 7.6. Main Calling Through the Proxy and Catching Exceptions to Print Results

`src/main/java/demo/flow/DemoApplication.java`:

```java
package demo.flow;

import java.io.IOException;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) throws IOException {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            TaskService service = context.getBean(TaskService.class);
            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            invoke(service, "ok");
            invoke(service, "empty");
            invoke(service, "checked");
            invoke(service, "unchecked");
            invoke(service, "recover");

            service.selfCall();
        }
    }

    private static void invoke(TaskService service, String mode) {
        try {
            String result = service.execute(mode);
            System.out.println("caller:" + mode + ":" + result);
        } catch (IOException | IllegalStateException ex) {
            System.out.println("caller:" + mode + ":throws:"
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
        }
    }
}
```

The `invoke(...)` calls go through the Spring-managed `service` proxy. `selfCall()` does not match `FlowAspect`'s pointcut (which selects only `execute`), and inside that method the `execute("ok")` call does not go through the proxy.

### 7.7. Run Command and Exact Stdout

From the directory containing `build.gradle`:

```bash
gradle run
```

If the project has Gradle Wrapper, use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows).

**Lines from the Java code**, excluding Gradle or environment logs:

```text
proxy=true
around:enter:ok
target:ok
around:normal:ok:SAVED
around:finally:ok
caller:ok:SAVED
around:enter:empty
target:empty
around:normal:empty:null
around:finally:empty
caller:empty:null
around:enter:checked
target:checked
around:checked:checked:offline
around:finally:checked
caller:checked:throws:IOException:offline
around:enter:unchecked
target:unchecked
around:unchecked:unchecked:broken
around:finally:unchecked
caller:unchecked:throws:IllegalStateException:broken
around:enter:recover
target:recover
around:unchecked:recover:retryable
around:fallback:recover
around:finally:recover
caller:recover:FALLBACK
target:selfCall
target:ok
target:selfResult:SAVED
```

### 7.8. Reading the Results by Outcome

| Input | Outcome of `proceed()` | `catch` | `finally` | Outcome seen by caller |
| --- | --- | --- | --- | --- |
| `ok` | Returns `"SAVED"` | No | Yes | `"SAVED"` |
| `empty` | Returns `null` | No | Yes | `null` |
| `checked` | Throws `IOException("offline")` | `catch IOException`, rethrows | Yes | `IOException` |
| `unchecked` | Throws `IllegalStateException("broken")` | `catch IllegalStateException`, rethrows | Yes | `IllegalStateException` |
| `recover` | Throws `IllegalStateException("retryable")` | `catch IllegalStateException`, returns fallback | Yes | `"FALLBACK"` |

The line `caller:recover:FALLBACK` shows that an exception genuinely occurred inside the target/inner chain, yet was converted by `@Around` into a normal return at the proxy boundary. This is **not equivalent** to the target never having thrown an exception.

At the end of the program:

```text
target:selfCall
target:ok
target:selfResult:SAVED
```

there are no extra `around:enter:ok`/`around:finally:ok` lines. This illustrates that the internal `this.execute(...)` call bypassed the Spring AOP proxy. Changing `try/catch/finally` does not fix self-invocation; for advice to run, the call must go through a suitable Spring-managed proxy.

## 8. Comparison With @AfterReturning, @AfterThrowing, and @After

Three simpler Spring advice types are useful when flow control is unnecessary:

| Goal | Suitable advice type | Notes |
| --- | --- | --- |
| Observe normal method return | `@AfterReturning` | Returning `null` is still a normal return |
| Observe exception escaping method execution | `@AfterThrowing` | `throwing` can bind `Throwable`/subtypes |
| Clean up or record completion on both paths | `@After` | Equivalent to after-finally; cannot alter return or swallow exceptions |
| Share measurement variables before & after, or control outcome | `@Around` | Has `proceed`/short-circuit/catch/rethrow power |

Examples:

```java
@AfterReturning(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    returning = "value",
    argNames = "value"
)
public void afterNormal(Object value) {
    // Normal completion, including null.
}
```

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterThrown(Throwable error) {
    // Exceptional completion, checked or unchecked.
}
```

```java
@After("execution(* com.example.app.service..*.*(..))")
public void afterFinally() {
    // When matched method execution finishes.
}
```

These are **illustrative snippets** that must be placed in an `@Aspect` and registered in the context; do not paste them alongside the demo without considering precedence across multiple advisors.

A practical distinction:
- `@AfterReturning` must not be used to replace the reference returned to the caller via a new return value from the advice.
- `@AfterThrowing` is not a general mechanism to catch and return a fallback.
- `@After` does not distinguish "success" from "failure."
- `@Around` can control returns/throws, so it must preserve contracts when business logic should not change.

### Why Don't @AfterReturning and @AfterThrowing Necessarily Measure the Exact Same "Target Outcome"?

When advisors are nested, an inner `@Around` can turn an exception into a fallback. An outer `@AfterReturning` observes only a normal return; an inner `@AfterThrowing` may have observed the exception earlier. Conversely, an outer cache/retry interceptor may never enter an inner advice at all.

To count "successes," decide whether you are measuring **target attempts** or **caller-visible proxy calls**. If two metric systems measure different layers, their counts will not necessarily match.

## 9. Common Mistakes With finally

### 9.1. Throwing Inside finally Masks the Original Exception

```java
try {
    return pjp.proceed();
} finally {
    throw new IllegalStateException("logging failed");
}
```

This is an anti-pattern: whether the target returned normally or threw `IOException`, the caller receives `IllegalStateException("logging failed")`, losing the original outcome. If logging, tracing, or cleanup can fail, design secondary failures **not to hide business errors**; selectively catch logging errors, use safe loggers/counters, or record suppressed causes per policy.

### 9.2. Returning Inside finally Discards the Result

```java
try {
    return pjp.proceed();
} finally {
    return "ALWAYS";
}
```

Likewise, this code overrides every return value and exception. Never use `return` inside `finally` of an around advice unless an extraordinary, thoroughly reviewed policy demands it; in almost all cases, it is a bug.

### 9.3. Putting Code Both After proceed and in finally Double-Counts

```java
Object result = pjp.proceed();
incrementCompleted();
return result;
```

counts only normal returns, whereas:

```java
try {
    Object result = pjp.proceed();
    incrementCompleted();
    return result;
} finally {
    incrementCompleted();
}
```

**counts twice on normal returns** and once on exceptions. To count total completions, increment only inside `finally`; if you want two separate metrics, name them clearly as `normal_count` and `total_completed_count`.

These snippets use `incrementCompleted()` as a hypothetical helper, not a standard Spring API.

### 9.4. Using a Singleton Field to Hold Per-Invocation State

Wrong:

```java
@Aspect
public class UnsafeAspect {
    private long started;

    @Around("execution(* com.example.app.service..*.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        started = System.nanoTime();
        try {
            return pjp.proceed();
        } finally {
            System.out.println(System.nanoTime() - started);
        }
    }
}
```

If the aspect is a singleton (the norm in Spring), concurrent threads overwrite `started`. Use a **local variable** `long started` inside the advice method or properly scoped per-invocation context, never unsynchronized shared mutable state.

### 9.5. Putting Preparatory Logic Outside try

If you want cleanup for all branches **inside the advice**, place fallible setup inside `try`. For example:

```java
Object[] args = pjp.getArgs();
String first = ((String) args[0]).trim(); // May throw before try.
try {
    return pjp.proceed(new Object[] { first });
} finally {
    cleanup();
}
```

If argument handling before `try` throws `ClassCastException` or `ArrayIndexOutOfBoundsException`, this `finally` **does not run**, because control flow never entered `try`. Place `try` boundaries around all operations that cleanup should cover and validate argument arity/types before accessing them.

## 10. Interactions With Transactions, Caching, Retries, and Exception Handlers

### 10.1. Spring Transactions Do Not Equal catch/rethrow Semantics

With Spring `@Transactional` in proxy mode, rollback is decided by the transaction interceptor, exception type, and rollback configuration. Under Spring Framework's standard default rules, unchecked `RuntimeException` and `Error` trigger rollback; checked exceptions do not roll back by default unless configured via `rollbackFor` or equivalent mechanisms.

**Do not deduce that "catching and rethrowing a checked exception" always triggers rollback.** Spring transaction rules still apply independently.

If an `@Around` sits **inside** the transaction interceptor and catches an exception to return a fallback, the outer transaction interceptor can treat the call as a normal completion. If `@Around` sits **outside**, the transaction interceptor may have already triggered rollback from the inner method's exception before outer around returns a fallback. Actual behavior depends on advisor order.

### 10.2. Cache Hits Are Also Normal Completions at Certain Layers

A cache interceptor can return a cache hit **without forwarding to the target**. An `@Around` outside the cache still sees `proceed()` return normally (even though the target did not run). An `@Around` inside the cache may not run at all on a cache hit.

Therefore `around:normal` in a logging aspect means "the proxy invocation returned normally," not necessarily "the target method just ran successfully." Name logs and metrics to match the observation point.

### 10.3. Retries Can Cause Multiple Exceptions Within One Caller Invocation

When a retry interceptor or `@Around` calls `proceed()` multiple times, the target may fail twice and succeed on the third attempt. An advice outside retry observes one normal return; advice inside observes the throwing attempts. Decide clearly whether you are measuring **request outcomes** or **attempt outcomes**.

To retry safely, consider:
- Attempt limits, backoff, and timeouts;
- Idempotency to avoid double writes or double sends;
- Which exceptions are retryable;
- Transaction boundaries per attempt;
- Interactions with logging/tracing and metric counters.

Never replace a retry policy with a catch-all and an unbounded `proceed()` loop.

### 10.4. Spring MVC Exception Handlers Are a Different Layer

Spring MVC's `@ControllerAdvice`/`@ExceptionHandler` can handle exceptions **after** the controller/service proxy throws outward. They do not make exceptions "disappear" for a service's `@Around` if the service interceptor chain already observed and rethrew the exception earlier.

Conversely, if the service's `@Around` catches and returns a fallback, the web layer may see no exception for its handler to process. Distinguish clearly:
- **Spring AOP @Around:** controls a method invocation across a proxy.
- **Spring MVC exception handling:** handles exceptions in the request dispatch/web handler flow.

Do not conflate the two mechanisms by saying "catching in AOP is ControllerAdvice."

## 11. Diagnostic Table for Success/Failure Paths

| Symptom | Possible cause | Check/fix |
| --- | --- | --- |
| `finally` does not appear when calling service | Call bypassed Spring AOP proxy; pointcut didn't match; outer advisor short-circuited | Check `AopUtils.isAopProxy`, bean registration, call path, advisor chain |
| `finally` does not appear when exception thrown before `try` | Failing code ran outside the try block | Wrap all code requiring cleanup inside `try` |
| Catch does not run for an exception swallowed by target | Target caught it itself and returned normally | Log in target catch or redesign advice |
| Catch sees `IllegalStateException` yet misses `IOException` | Catching a specific subtype | Add matching catch or `Throwable` + rethrow for observability |
| Caller does not receive exception thrown by target | Advice caught and returned a fallback | Review fallback policy and advisor order |
| Caller receives strange exception from logging | `finally`/`catch` threw a new error masking original | Isolate instrumentation errors; preserve original failure |
| Caller receives `null` though target returned non-null | Advice declared `void` or explicitly returned `null` | Use `Object` and `return pjp.proceed()` |
| Duration recorded only on success | Logging placed after `proceed()` instead of `finally` | Measure inside `finally` |
| Success counter increments when returning `null` | `null` is still a normal return | Separate normal completion from business success |
| Counter increments twice on return | Incremented in both `try` and `finally` | Separate normal/total or increment in one place |
| Self-invocation gets no advice | `this.method()` bypassed proxy | Extract collaborating bean or call via proper proxy |
| `final`/`private` method receives no advice | CGLIB cannot override it | Redesign API/proxy approach |
| Catch misses exception created by an outer advisor | Advice sits inside; outer exceptions never pass this catch | Inspect advisor position/precedence |
| Checked exception gets wrapped under JDK proxy | Interface method does not declare checked exception | Fix method contract and inspect cause |
| Aspect logs sensitive data | Printing `pjp.getArgs()`/exception payloads unfiltered | Mask/allowlist; avoid logging credentials/PII |

## 12. Systematic Testing and Debugging Workflow

1. **Spring AOP registration:** is the `@Aspect` class a Spring bean? Is `@EnableAspectJAutoProxy` or Boot AOP auto-config enabled in the right context?
2. **Real proxy retrieval:** is the client calling `context.getBean(...)` or an injected dependency? Never use `new Target()` to test advice.
3. **Proxy type check:** `AopUtils.isJdkDynamicProxy` or `isCglibProxy`? Is the method proxyable and visible?
4. **Pointcut check:** does `execution(...)` match exact class/method/return type/parameters? Did package names change?
5. **Self-invocation check:** is there `this.otherMethod()` or a call from a constructor/init block?
6. **Try boundary check:** did the error occur **before** or **inside** `try`? Does the catch type match the exception?
7. **Result/exception check:** is the return type compatible? Is anything unnecessarily swallowing or wrapping exceptions?
8. **Finally check:** could a `return`/`throw` in `finally` mask the original outcome? Can cleanup throw?
9. **Interceptor order check:** could caching/transactions/retries skip the target or alter the outcome?
10. **Test all five cases:** object return, null return, checked exception, unchecked exception, catch→fallback.
11. **Test self-invocation:** invoke a method from another target method; confirm internal calls bypass the proxy.
12. **Test concurrency:** if the aspect is a singleton, all per-invocation state must be local or thread-safely managed.

A quick inspection snippet when you already have a Spring `context`:

```java
Object bean = context.getBean("taskService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Requires importing `org.springframework.aop.support.AopUtils`; this is a **diagnostic snippet**, not a standalone Java file. `isAopProxy=true` proves the bean is proxied, yet does not prove every method or call path goes through advice.

## 13. Design Checklist for try/catch/finally in @Around

- [ ] Advice takes `ProceedingJoinPoint` as first parameter, returns `Object`, and declares `throws Throwable` when propagating exceptions from `proceed()`.
- [ ] Default to calling `proceed()` once; use 0/n calls only with an explicit policy.
- [ ] `try` encloses all code whose cleanup/metrics you want managed.
- [ ] `catch` targets appropriate exception types; never swallow `Throwable` indiscriminately.
- [ ] Unless intentionally falling back, **rethrow the original exception**.
- [ ] `finally` does not accidentally `return`/`throw` or mask business exceptions.
- [ ] Never log sensitive data from `getArgs()` or uncontrolled error messages.
- [ ] Separate metrics for normal returns, exceptions, recovered fallbacks, and total completions.
- [ ] Choose and test aspect position relative to cache, transactions, and retries intentionally.
- [ ] Use per-invocation local variables; avoid unsynchronized mutable state in singleton aspects.
- [ ] Ensure fallbacks match return types and are business-approved.
- [ ] Test `null` returns, checked/unchecked exceptions, and self-invocation.
- [ ] For logic needing only after-return/after-throw/finally without flow control, consider simpler `@AfterReturning`, `@AfterThrowing`, or `@After`.

## 14. Conclusion

In Spring `@Around`, `try/catch/finally` lets you capture both **normal return** and **exceptional exit** paths while executing cleanup as the advice unwinds:

- **`try` + `proceed()`:** advances the Spring interceptor chain and receives the normal result or exception.
- **`catch`:** observes exceptions; rethrows unless an approved conversion policy applies.
- **`finally`:** records total metrics/cleans up state across normal returns, rethrows, and fallback returns.

Even more important than syntax is **precisely defining the outcome at the advice's position in the proxy chain**. The caller-visible result may differ from the target's outcome when fallbacks, caching, or retries wrap it. `@Around` can make a system more resilient, yet can also hide severe bugs if it swallows exceptions, alters return types, or breaks transaction semantics.

This mechanism belongs to Spring AOP only when the invocation passes through a **Spring-managed proxy** and matches the pointcut. A flawless `try/finally` cannot substitute for proxy requirements, fix self-invocation, or intercept arbitrary Java methods automatically.

### Official Spring Documentation

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): Spring `@Around`, `ProceedingJoinPoint.proceed()`, return values, throwing, `@After`, and advice ordering.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): advice types, normal/exceptional completion, and around advice.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): registering and enabling aspects on Spring beans.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation, and proxy boundaries.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules and exception handling, independent of how aspects log errors.
