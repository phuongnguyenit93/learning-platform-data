# Distinguishing the Success Path, Exception Path, and Method Completion in Spring AOP

## 1. One Spring Method with Three Observable Outcomes

A Spring service can **return a result normally**, **throw an exception to the caller**, or **finish by either of those two paths and need cleanup/recording that it finished**. When using Spring Aspects for logging, metrics, auditing, or error tracking, you must choose the right advice type corresponding to the outcome the system genuinely wants to know about.

For example, a `checkout(String id)` method has these paths:

```text
Client
  |
  v
Spring AOP proxy
  |
  +-- @Before: when the call is about to execute
  |
  v
Target checkout(...)
  |
  +-- return "OK" ---------> normal completion path
  |                           +-- @AfterReturning
  |                           +-- @After (finally)
  |
  +-- throw Exception ------> exception exit path
                              +-- @AfterThrowing
                              +-- @After (finally)
```

`@After` is not an alias for `@AfterReturning`: it has semantics close to Java's `finally`, running when a **matching method execution finishes**, regardless of whether it completed normally or exited with an exception. `@AfterReturning` reflects only **normal completion**; `@AfterThrowing` reflects only **exceptional completion**.

In Spring AOP, these advices are chained into an **interceptor chain on a Spring-managed proxy**. One crucial condition: **even if a pointcut matches, if the call does not pass through the proxy, the advice still does not run**. Calls like `this.method()` between two methods on the same target, constructors, or objects created with `new` do not automatically receive Spring AOP advice.

**Lesson scope:** Advice mechanisms based on **method execution completion events in Spring Framework / Spring `@Aspect`**. It does not extend to AspectJ weaving of constructor or field join points outside Spring.

### Learning Objectives

After this lesson, you will be able to:

1. Accurately distinguish `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, and `@Around`.
2. Understand that "success" in `@AfterReturning` means **not throwing an exception**, which is not synonymous with achieving the business goal.
3. Understand that an exception **caught and handled inside the target** is not an "exceptional completion" of the proxy invocation.
4. Bind return values with `returning` and bind exceptions with `throwing` without unintentionally narrowing types.
5. Run a Java 17/Spring Framework example covering normal return, `null`, checked exceptions, and unchecked exceptions.
6. Diagnose why the same invocation triggers `@After` alongside only one of `@AfterReturning` or `@AfterThrowing`, and when `@Around` alters the outcome.

## 2. Semantics Table for Spring Advices

| Advice | When does it run? | Sees normal return? | Sees exception? | Primary role |
| --- | --- | --- | --- | --- |
| `@Before` | Before matching method execution, when the proxy chain reaches the advice | Result not yet known | Exception not yet known | Precondition checks, starting simple logging/metrics |
| `@AfterReturning` | Matching method execution **returns normally** | Yes, can bind the value | Does not run when an exception exits | Recording completion, reading the result, success metrics |
| `@AfterThrowing` | Matching method execution **exits with an exception** | Does not run on normal return | Yes, can bind the exception | Recording failures/exceptions, alerting |
| `@After` | When matching method execution finishes via either path | Runs | Runs | Cleanup, recording "completed", releasing state |
| `@Around` | Surrounds method invocation and controls whether `proceed()` is called | Can observe/modify the result | Can catch/rethrow/translate exceptions | Duration tracing, controlled retries, intentional fallback |

This table describes outcomes of a **method execution that has passed through the matching advisors**; it does not guarantee callbacks run during abrupt process termination, severe VM errors, or when *another* advisor short-circuits before the chain reaches the corresponding advice.

### A Quick Mnemonic

```text
Did target return normally?
    YES -> @AfterReturning; @After
    NO  -> if exception exited -> @AfterThrowing; @After

@After: does not pick one path; observes general completion.
@Around: can shape its own path via proceed / return / throw.
```

Within a single invocation that reached these advices, `@AfterReturning` and `@AfterThrowing` represent two mutually exclusive termination conditions; they are **not two hooks expected to run simultaneously**.

## 3. `@AfterReturning`: Normal Completion, Not Necessarily "Business Success"

Definition:

```java
@Aspect
public class CompletionAspect {

    @AfterReturning(
        pointcut = "execution(* com.example.app.service..*.*(..))"
    )
    public void completedNormally() {
        // Method execution returned normally.
    }
}
```

### 3.1. Three Outcomes That Are Still Normal Returns

For example, a method might do:

```java
public String evaluate(String mode) {
    if ("ok".equals(mode)) {
        return "OK";
    }
    if ("missing".equals(mode)) {
        return null;
    }
    return "DECLINED";
}
```

All three cases above **return normally**:
- `"OK"` is success under the business contract;
- `null` may mean "no data," yet it still returns normally;
- `"DECLINED"` may mean "payment declined," yet it is still not an exception.

`@AfterReturning` runs for all three when the invocation matches and goes through the proxy. Therefore, naming a metric `technical_normal_completion` is usually more accurate than treating every `@AfterReturning` execution as `business_success`.

If a `void` method finishes without throwing an exception, that is also a **normal completion**; an `@AfterReturning` advice without a `returning` binding can still run.

### 3.2. Binding the Return Value with `returning`

```java
@AfterReturning(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    returning = "result",
    argNames = "result"
)
public void captureResult(Object result) {
    System.out.println("return=" + result);
}
```

This is an illustrative snippet inside an `@Aspect` class; imports and real configuration are required to run it. The name `result` in `returning` must match the advice parameter name. `argNames` makes the binding name explicit when Java compilation does not retain parameter names as expected.

Because the advice parameter is `Object`, it accepts most return values; changing it to `String` can **narrow the advice's scope** to results/methods compatible with `String`. Do not accidentally constrain the type just to print a value.

**Limitation:** `@AfterReturning` can observe or interact with the returned object, but **cannot be used to replace the reference returned** to the caller by `return`-ing another value from the advice. If the requirement is to transform the result returned to the caller, use `@Around` with `ProceedingJoinPoint.proceed()` and return the desired value.

## 4. `@AfterThrowing`: The Exception Must Exit the Join Point

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void captureFailure(Throwable error) {
    System.out.println("exception=" +
        error.getClass().getSimpleName());
}
```

In Spring AOP, `@AfterThrowing` runs when a matching method execution **terminates by throwing an exception outward**. `throwing` can bind the exception object to the advice.

### 4.1. Checked and Unchecked Exceptions

Example:

```java
public String load(String mode) throws IOException {
    if ("checked".equals(mode)) {
        throw new IOException("offline");
    }
    if ("unchecked".equals(mode)) {
        throw new IllegalStateException("broken");
    }
    return "OK";
}
```

If these exceptions actually exit the method execution and the call passes through the proxy, an `@AfterThrowing` with `Throwable error` can observe **both `IOException` and `IllegalStateException`**. The exception does not have to be a `RuntimeException`.

Conversely, if the advice declares:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void captureIllegalState(IllegalStateException error) {
    // Only matches compatible exception types.
}
```

then the `IllegalStateException` constraint prevents the advice from running for `IOException`. This is **type-based exception filtering**; it does not mean Spring only supports unchecked exceptions.

### 4.2. An Exception Caught by the Target Is Not Exceptional Completion

```java
public String loadSafely() {
    try {
        return fetchRemote();
    } catch (IOException ex) {
        return "FALLBACK";
    }
}
```

This snippet assumes `fetchRemote()` can throw `IOException`. If the target catches the exception internally and returns `"FALLBACK"`, from the method execution perspective observed by the proxy, the outcome is a **normal return**:
- `@AfterReturning` can run;
- `@AfterThrowing` on `loadSafely` does not run because `IOException` did not exit the method;
- `@After` still runs.

If business logic needs to observe every exception **caught internally**, a Spring AOP proxy does not intercept individual `throw`/`catch` statements inside a method. Log in the catch block or design appropriate instrumentation.

### 4.3. `@AfterThrowing` Is Not a General Exception Handler

It only receives exceptions belonging to the corresponding method execution call. The Spring documentation explicitly states that `@AfterThrowing` is not a general callback for exceptions thrown by other `@After`/`@AfterReturning` advices. Nor can a `void` advice of this kind be used to **swallow an exception** and return a new result like a regular fallback.

To change the exception and result seen by the caller, use `@Around` when truly necessary, taking care to consider the impact on transactions and other advices.

## 5. `@After`: Both Normal Return and Exception Must Pass Through

```java
@After("execution(* com.example.app.service..*.*(..))")
public void afterAnyCompletion() {
    System.out.println("completed");
}
```

`@After` in `@AspectJ` corresponds to the idea of **finally**:

```java
try {
    // target method execution
} finally {
    // cleanup
}
```

It is suitable for:
- Clearing local tracing state;
- Recording a total-completions metric;
- Releasing resources scoped to the advice, when ownership is clear;
- Removing an "in-progress" flag set beforehand.

### 5.1. Not the Place to Conclude Method "Success"

If you increment a `completed` counter in `@After`, that counter can include **both methods that returned normally and methods that threw exceptions**. Do not name it `successfulRequests` if the value comes from `@After`.

A logical sanity check:

```text
totalCompleted ≈ normalReturns + thrownCompletions
```

This equality makes sense when the three counters observe the **same set of method invocations**, all advices apply, there are no short-circuits or advice errors, and no code alters outcomes outside the observed boundary. In a complex proxy chain or concurrent system, calculate according to the actual design.

### 5.2. Neither `@After` Nor Java `finally` Is an Absolute Guarantee

`@After` runs when execution reaches the advice and finishes along the return/throw paths. If the JVM hits `System.exit`, the process is killed, the thread dies from a fatal event, or an **outer** advisor skipped calling `proceed()`, the callback may not be invoked. Likewise, if there is no AOP proxy or the pointcut does not match, there is no hook to run.

Use `try/finally` directly inside the code that owns the resource when release must be guaranteed within an internal method scope; do not assume `@After` replaces all resource management rules.

## 6. Advice Ordering: Something Easily Misunderstood

Within a single `@Aspect`, Spring applies precedence by advice kind. The Spring Framework documentation lists advice types from highest to lowest precedence: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`. **However, `@After` is actually called *after* `@AfterReturning` or `@AfterThrowing` of the same aspect**, matching "finally" semantics.

Do not read the precedence table and conclude that `@After` logs always print **before** `@AfterReturning` logs: that confuses interceptor chain order with callback execution order during unwinding.

If advices reside in **two different aspects**, when both match the same join point, order is not guaranteed unless `@Order`/`Ordered` is configured. The aspect with the lower order value typically has higher precedence: it enters earlier and exits later.

### Illustrating the Normal Completion Path

```text
proxy.method()
    |
    +-- @Before            [entry path]
    |
    +-- target returns     [normal completion]
    |
    +-- @AfterReturning    [normal branch]
    |
    +-- @After             [finally, same aspect]
    |
    +-- caller sees return
```

### Illustrating the Exceptional Completion Path

```text
proxy.method()
    |
    +-- @Before
    |
    +-- target throws
    |
    +-- @AfterThrowing     [exception branch]
    |
    +-- @After             [finally, same aspect]
    |
    +-- caller receives exception
```

These two flows help distinguish **event semantics** in Spring AOP; they do not replace inspecting advisor ordering when multiple aspects, transactions, caching, retries, or specialized `@Around` advices are present.

## 7. Runnable Spring Framework Example: Four Termination Paths

The following example uses:
- **Java 17+**;
- **Spring Framework 6.1.14**;
- **AspectJ Weaver 1.9.22.1**;
- **Gradle**;
- An `@Aspect` recording advice counters.

We intentionally **do not print logs inside the advices**, instead incrementing counters and printing a snapshot after each method invocation. This proves all three outcome categories without depending on log-printing order details between advices.

Four inputs:
1. `"ok"` → returns `"OK"`;
2. `"empty"` → returns `null`;
3. `"unchecked"` → throws `IllegalStateException`;
4. `"checked"` → throws `IOException`.

### 7.1. Directory Structure

```text
spring-aop-outcomes/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/outcomes/
    ├── OutcomeService.java
    ├── OutcomeAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 7.2. Gradle Configuration

File `settings.gradle`:

```groovy
rootProject.name = 'spring-aop-outcomes'
```

File `build.gradle`:

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
    mainClass = 'demo.outcomes.DemoApplication'
}
```

`spring-context` provides IoC/configuration; `spring-aop` contains the proxy infrastructure; `aspectjweaver` supports pointcut parsing in `@Aspect`.

### 7.3. Target Method with Four Outcomes

File `src/main/java/demo/outcomes/OutcomeService.java`:

```java
package demo.outcomes;

import java.io.IOException;

public class OutcomeService {

    public String evaluate(String mode) throws IOException {
        System.out.println("target:" + mode);

        if ("ok".equals(mode)) {
            return "OK";
        }
        if ("empty".equals(mode)) {
            return null;
        }
        if ("unchecked".equals(mode)) {
            throw new IllegalStateException("broken");
        }
        if ("checked".equals(mode)) {
            throw new IOException("offline");
        }
        return "UNKNOWN";
    }
}
```

`OutcomeService.evaluate` is a public non-final method, so it can be intercepted by a CGLIB proxy. The method declares `throws IOException` so the checked exception is **allowed to exit**; `IllegalStateException` is unchecked.

`return null` is still a normal completion. Code outside `evaluate` (the caller) is responsible for distinguishing exceptions from return values.

### 7.4. Aspect Counting Before, After-Returning, After-Throwing, and After

File `src/main/java/demo/outcomes/OutcomeAspect.java`:

```java
package demo.outcomes;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class OutcomeAspect {
    private final AtomicInteger before = new AtomicInteger();
    private final AtomicInteger normal = new AtomicInteger();
    private final AtomicInteger failed = new AtomicInteger();
    private final AtomicInteger finished = new AtomicInteger();

    @Before("execution(public * demo.outcomes.OutcomeService.evaluate(..))")
    public void onEnter() {
        before.incrementAndGet();
    }

    @AfterReturning(
        pointcut = "execution(public * demo.outcomes.OutcomeService.evaluate(..))",
        returning = "result",
        argNames = "result"
    )
    public void onNormalReturn(Object result) {
        normal.incrementAndGet();
        // result can be null; do not assume return == business success.
    }

    @AfterThrowing(
        pointcut = "execution(public * demo.outcomes.OutcomeService.evaluate(..))",
        throwing = "error",
        argNames = "error"
    )
    public void onException(Throwable error) {
        failed.incrementAndGet();
        // error can be a checked or unchecked exception.
    }

    @After("execution(public * demo.outcomes.OutcomeService.evaluate(..))")
    public void onAnyCompletion() {
        finished.incrementAndGet();
    }

    public String counts() {
        return "before=" + before.get()
            + " returned=" + normal.get()
            + " thrown=" + failed.get()
            + " after=" + finished.get();
    }
}
```

Explanation of design decisions:
- `onEnter()` runs when the proxy passes the invocation through `@Before`.
- `onNormalReturn(Object result)` uses `Object` to avoid overly narrowing to a specific return class; `null` is still normal.
- `onException(Throwable error)` uses `Throwable` to cover both `IOException` and `IllegalStateException`. If changed to `IllegalStateException`, the counter would no longer represent all exceptions.
- `onAnyCompletion()` counts all invocations that finished via `@After` advice.
- Counters are `AtomicInteger` to prevent lost increments when multiple threads use the same singleton aspect; the demo calls sequentially for deterministic stdout.

The advice methods **do not return results on behalf of the target**, nor do they swallow exceptions. They only measure events.

### 7.5. Registering Beans and Enabling Spring AOP

File `src/main/java/demo/outcomes/AppConfig.java`:

```java
package demo.outcomes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OutcomeService outcomeService() {
        return new OutcomeService();
    }

    @Bean
    public OutcomeAspect outcomeAspect() {
        return new OutcomeAspect();
    }
}
```

`@Aspect` **does not automatically** register a Spring bean. In the example, `@Bean` supplies the aspect instance; `@EnableAspectJAutoProxy` enables the advisor-parsing infrastructure. `proxyTargetClass=true` selects a class-based proxy so the service can be retrieved by `OutcomeService.class`.

### 7.6. Main Calling Four Scenarios Through the Proxy

File `src/main/java/demo/outcomes/DemoApplication.java`:

```java
package demo.outcomes;

import java.io.IOException;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            OutcomeService service = context.getBean(OutcomeService.class);
            OutcomeAspect aspect = context.getBean(OutcomeAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            invoke(service, aspect, "ok");
            invoke(service, aspect, "empty");
            invoke(service, aspect, "unchecked");
            invoke(service, aspect, "checked");
        }
    }

    private static void invoke(
            OutcomeService service, OutcomeAspect aspect, String mode) {

        try {
            String result = service.evaluate(mode);
            System.out.println("caller:" + mode + "=" + result);
        } catch (IOException | IllegalStateException ex) {
            System.out.println(
                "caller:" + mode + " threw "
                + ex.getClass().getSimpleName()
                + ":" + ex.getMessage()
            );
        }
        System.out.println("counts " + aspect.counts());
    }
}
```

Run command from the `spring-aop-outcomes` directory:

```bash
gradle run
```

If the project includes the Gradle Wrapper, you can use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

### 7.7. Expected Stdout

The lines below are **stdout from Java code**, excluding Gradle logs:

```text
proxy=true
target:ok
caller:ok=OK
counts before=1 returned=1 thrown=0 after=1
target:empty
caller:empty=null
counts before=2 returned=2 thrown=0 after=2
target:unchecked
caller:unchecked threw IllegalStateException:broken
counts before=3 returned=2 thrown=1 after=3
target:checked
caller:checked threw IOException:offline
counts before=4 returned=2 thrown=2 after=4
```

The results are interpreted as follows:

| After input | Total `@Before` | Total `@AfterReturning` | Total `@AfterThrowing` | Total `@After` |
| --- | ---: | ---: | ---: | ---: |
| `ok` | 1 | 1 | 0 | 1 |
| `empty` | 2 | 2 | 0 | 2 |
| `unchecked` | 3 | 2 | 1 | 3 |
| `checked` | 4 | 2 | 2 | 4 |

- `empty` still increments `returned` because `null` is not an exception.
- `unchecked` and `checked` both increment `thrown` because the advice binds `Throwable`.
- `after` increments on all four calls because every invocation finishes via one of the two paths.
- The caller only prints `caller:mode=...` on normal completion; on exception it enters `catch`. The aspect does not block or alter exceptions.
- `proxy=true` confirms calls from `main` go through the Spring-managed proxy; if using `new OutcomeService()` outside Spring, the counters will not increment.

This counter-based observation avoids misunderstandings about advice precedence when reading consecutive log lines.

## 8. `@Around`: The Advice Type That Can Alter the Termination Path

`@Around` has broader power than the other four advices because it controls `ProceedingJoinPoint.proceed()`.

An `@Around` used for timing while **preserving** the outcome:

```java
@Around("execution(* com.example.app.service..*.*(..))")
public Object measure(ProceedingJoinPoint pjp) throws Throwable {
    long start = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println("durationNanos=" + elapsed);
    }
}
```

This is an illustrative snippet inside an `@Aspect` class; it requires `@Around`/`ProceedingJoinPoint` imports and matching Spring bean/service methods. `proceed()` is called **exactly once**; if the target returns, the value is returned to the caller, and if it throws an exception, the exception still propagates outward after `finally`.

### 8.1. Returning a Different Result

```java
@Around("execution(* com.example.app.service..*.load*(..))")
public Object fallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return "FALLBACK";
    }
}
```

This snippet **deliberately transforms the outcome**: to the proxy's caller, an `IllegalStateException` thrown by the inner chain/target has been caught and converted into a **normal return**. This can change how advices **outside** `@Around` classify the call. Advices **inside** that already saw the exception from the target before `@Around` caught it may still record a failure.

Do not drop the `fallback` snippet into the runnable project in section 7 unless you also update the method types, aspect configuration, and expected stdout accordingly. It illustrates an alternative policy choice, not the default usage.

### 8.2. Not Calling `proceed()`

```java
@Around("execution(* com.example.app.service..*.load*(..))")
public Object shortCircuit(ProceedingJoinPoint pjp) {
    return "CACHED";
}
```

If this advice is actually applied and **does not call `proceed()`**, the inner target method does not execute. Inner advisors may also not execute. For instance, logging, transaction, and caching placed at different positions in the interceptor chain will observe different outcomes.

**Technical conclusion:** "What the target returned/threw" and "what the proxy caller sees returned/thrown" are not always identical when `@Around` or short-circuiting interceptors are present. Always specify **at which position in the chain observation occurs**.

### 8.3. Prefer the Least Powerful Advice

If you only need to count normal returns, use `@AfterReturning`. If you only need to log exiting exceptions, use `@AfterThrowing`. If you only need cleanup, use `@After`. Use `@Around` only when you need both before and after access **within one scope** or need to control whether the chain continues; forgetting `proceed()` once can silently skip running the target.

## 9. Impact of Spring Transactions, Caching, and Retries

When a service has multiple advisors, outcomes depend on interceptor ordering.

### 9.1. Transactions

If a `@Transactional` method encounters an exception and the exception exits outside the transaction interceptor, Spring's transaction rollback rules apply based on **exception type and rollback configuration**. Default rollback typically occurs for `RuntimeException`/`Error`, and not by default for checked exceptions without an appropriate `rollbackFor`.

**Do not infer** that whenever `@AfterThrowing` runs, the database transaction is guaranteed to roll back: the two mechanisms have different rules. If an `@Around` catches an exception and returns a fallback **before** the transaction interceptor observes it, the transaction may treat the invocation as normal depending on advisor ordering. That is why you should not arbitrarily swallow exceptions in a tracing aspect.

### 9.2. Caching

A cache interceptor sitting outside an advice can return a cache hit without running the target or inner advices. In that case:
- You may not see `@AfterReturning` from an inner aspect on a cache hit, because that advisor is never reached.
- If the advice sits outside caching, it can see a normal return from the cache.
- The same method signature and target bean do not guarantee that all advices run the same number of times when other advisors short-circuit.

### 9.3. Retries

With a retry interceptor or an `@Around` that intentionally calls `proceed()` multiple times, a single call from the caller can correspond to **multiple target attempts**. An advice outside vs. inside the retry will differently observe "one final success" vs. "several preceding throws."

For metrics to be meaningful, define them clearly:
- `attempt_failure`: a target attempt threw an exception;
- `request_failure`: the final call exiting the proxy still failed;
- `request_completed`: the call finished regardless of outcome;
- `business_rejected`: the target returned a rejection result without throwing an exception.

Spring `@AfterReturning`/`@AfterThrowing` alone does not decide which category a metric belongs to if you have not established advisor ordering.

## 10. Outcome Classification Matrix for the Same Spring Method

Distinguish normal completion, exceptional completion, and total completion using three counters applied to the same invocation set, same proxy boundary, and same pointcut. The values below represent one call that matched all advices:

| Target outcome | Normal return | Throwing | Finally |
| --- | ---: | ---: | ---: |
| Returns string `OK` | 1 | 0 | 1 |
| Returns `null` | 1 | 0 | 1 |
| Returns `DECLINED` | 1 | 0 | 1 |
| Catches `IOException` and returns fallback | 1 | 0 | 1 |
| Throws `IllegalStateException` outward | 0 | 1 | 1 |
| Throws `IOException` outward | 0 | 1 | 1 |

Returning `DECLINED` is a business refusal, yet still a normal method completion. If the `@AfterThrowing` advice only binds `RuntimeException`, the `IOException` branch alone will not be counted by it; if `@AfterReturning` only binds `String`, `void` methods and other return types may be excluded.

## 11. When Does `completed = normal + throwing` Break Down?

The formula is only useful when all three advices observe the same invocation boundary, there are no short-circuits or advice-thrown errors, and the two classification advices are not narrowed by differing type bindings. If transactions, caching, retries, or `@Around` are involved, inspect interceptor ordering: a fallback in an around advice can turn an inner exception into a normal return at the outer layer.

Verification workflow: confirm the target's actual outcome; verify proxy and pointcut; verify `returning` or `throwing` names/types; and finally reconcile business metrics with method completion. Do not use normal return as proof that a transaction committed or a `Future` completed.

## 12. Checklist When Designing a Spring Aspect to Measure Outcomes

- [ ] Use `@AfterReturning` only to record **normal completion**; do not treat every returned value as business success.
- [ ] Use `@AfterThrowing` for exceptions exiting method execution; choose `Throwable` or a specific subtype intentionally.
- [ ] Use `@After` for cleanup or total completed counts, not to assert request success.
- [ ] Use `@Before` for pre-call steps; do not conclude outcomes there.
- [ ] Use `@Around` only when you need to intervene in flow or hold before/after scope within one invocation, and control `proceed()` carefully.
- [ ] Test outcomes: `return null`, returning an object, checked exceptions, and unchecked exceptions.
- [ ] Test cases where the target catches an exception internally and returns a fallback.
- [ ] Check differences between the target's outcome and the outcome seen by the **proxy caller** when caching/retry/fallback is present.
- [ ] Test through the Spring-managed proxy; do not use `new`/`this` to claim AOP behavior.
- [ ] If the aspect is used concurrently, use per-invocation local data or thread-safe primitives for counters.
- [ ] Avoid having advices throw unnecessary exceptions, as this can alter the exception/result seen by business code.
- [ ] With transactions, separate rollback rules and business status from the concept of "after throwing."

## 13. Conclusion

In Spring Aspect, the three "post-method events" carry distinct semantics:

- **`@AfterReturning`:** the method finished normally; the result may be an object, `null`, a rejection status code, or no value for a `void` method.
- **`@AfterThrowing`:** the method terminated with an exception exiting outward; both checked and unchecked exceptions can be observed if type binding matches.
- **`@After`:** the method finished via any path and this advice was applied; semantics mirror `finally`.

`@Around` is the stronger tool: it can proceed, skip, repeat, or transform results/exceptions, changing outcomes at different points in the Spring interceptor chain. Therefore, **clearly define the measurement point and business policy** before labeling success or failure.

To apply these properly, check the **pointcut**, the **Spring-managed proxy boundary**, and the **actual invocation outcome** together. No single advice annotation replaces understanding all three factors.

### Official Spring Documentation

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around`, binding, and ordering.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): advice types and how Spring applies method-execution join points.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): registering `@Aspect` beans and enabling Spring auto-proxying.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, self-invocation, proxy boundaries.
- [Spring Framework — Declarative Transaction Rolling Back](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): exception types and rollback rules, independent of advice measuring throwing completion.
