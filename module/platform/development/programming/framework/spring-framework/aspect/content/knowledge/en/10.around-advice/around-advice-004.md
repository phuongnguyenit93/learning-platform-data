# Behavior When Calling `proceed()` Multiple Times in Spring AOP

## 1. The Core Answer

In **Spring AOP**, an `@Around` method receives a `ProceedingJoinPoint` and has the authority to decide **whether to forward the call to the rest of the interceptor chain, how many times to forward it, and what result to return**.

The Spring Framework documentation confirms: inside the body of `@Around`, calling `proceed()` **zero times, once, or many times is valid**. Calling it multiple times is the foundation of certain policies such as **retrying on transient failures**. However, it is **not** a harmless observation operation: each forwarding call can cause **the target method and any advice sitting inside the current advice to execute an additional time**.

```java
@Around("execution(* com.example.service.PaymentService.charge(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    Object first = pjp.proceed();   // One pass into the inner chain.
    Object second = pjp.proceed();  // Another pass into the inner chain.
    return second;                  // Caller receives only the result returned by the advice.
}
```

This is an **illustrative fragment**, requiring imports and a Spring-registered `@Aspect` class. If both `proceed()` calls actually reach the target and the target does not fail, `charge()` may be invoked **twice**, creating **two charges** if the business logic is not safely designed.

Therefore, the right answer is not merely "calling it multiple times is allowed," but also requires answering:

- Which advice runs once, and which advice runs again?
- If the first pass throws an exception, can the next pass still run?
- Which pass's return value does the caller receive?
- Does it recreate the Spring bean, proxy, or transaction?
- Does it repeat side effects such as database writes, sending emails, publishing events, or charging money?
- Can **new arguments** be passed to each `proceed` call?
- When should this technique not be used?

This lesson focuses only on **Spring Aspect / proxy-based Spring AOP**, without covering standalone AspectJ weaving theory as a separate topic.

## 2. Execution Model: Repeating the **Inner** Chain, Not Restarting Everything

Suppose the same Spring service is wrapped by two `@Around` advices:

- **RetryAspect** has higher precedence, so it sits **outside**.
- **TraceAspect** has lower precedence, so it sits **inside**.
- The target bean is `WorkService`.

```text
Caller
  |
  v
Spring AOP proxy
  |
  v
RetryAspect.around()            <-- entered ONCE from caller
  |
  +---- proceed() pass 1 -----> TraceAspect.around()
  |                              |
  |                              +--> target.execute() call 1
  |                              |
  |                          return or throw
  |
  +---- proceed() pass 2 -----> TraceAspect.around()
  |                              |
  |                              +--> target.execute() call 2
  |                              |
  |                          return or throw
  |
  +---- RetryAspect chooses final result/exception
  |
  v
Caller
```

When `RetryAspect` calls `proceed()`, Spring advances to **the portion of the invocation chain after that advice**. If `TraceAspect` and the target sit inside it, they are re-executed on each forwarding pass.

**Do not infer that a second `proceed()` automatically re-invokes outer advice or the entire caller.** `RetryAspect.around()` continues executing within **the same Java invocation** initiated by the caller; local variables such as `attempt` still belong to that invocation.

Distinguish clearly:

1. **One proxy call from the caller:** `service.execute("retry")`.
2. **One entry into outer around advice:** `RetryAspect.around(...)`.
3. **Two `proceed()` calls:** may enter downstream advices twice.
4. **Two target method executions:** if each `proceed` reaches the target without being short-circuited by another downstream advice.

The phrase "may reach the target" is crucial: an inner advice also has the right **not to call `proceed()`**, for example to return a cached value. Thus, the number of `proceed()` calls by an outer advice is **the number of forwards into the downstream chain**, not a mathematical guarantee that the target always executes that exact number of times.

## 3. Behavior Table for Calling `proceed()` 0, 1, or Multiple Times

| Number of `proceed()` calls in one `@Around` | Downstream chain | Target method | What does the caller receive? |
| --- | --- | --- | --- |
| **0 times** | Not forwarded from this advice. | Does not run via this path. | Value returned by `@Around` or exception it throws; e.g., cache hit. |
| **1 time** | Forwarded for one pass. | Usually runs once unless short-circuited. | Value `@Around` chooses to return; usually the value from `proceed()`. |
| **2 times** | Two independent forwarding passes. | May run twice; all side effects may repeat. | Does not automatically receive "both"; caller receives **one** value returned by the advice. |
| **N times conditionally** | Loops per the advice's loop/branch logic. | May run up to N times if attempts continue and reach target. | Result of the successful pass returned, fallback value, or final exception per code. |
| **First call throws exception** | First pass interrupted by exception. | Target may already have executed partially. | If `@Around` catches and retries, caller may see next pass's result; if uncaught, exception propagates. |

**`proceed()` does not automatically retry, roll back, or decide return values.** Your code inside `@Around` must choose the loop condition, attempt limit, retryable exception types, and returned value.

## 4. Does Calling `proceed()` Multiple Times Re-Invoke Other Advice?

Yes, **if those advices sit inside** the current around advice and still match the invocation.

Example with explicit ordering via `@Order`:

```java
@Aspect
@Order(0)
public class OuterRetryAspect {
    @Around("execution(* com.example..WorkService.execute(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        try {
            return pjp.proceed();
        } catch (TemporaryFailure ex) {
            return pjp.proceed();
        }
    }
}
```

```java
@Aspect
@Order(10)
public class InnerTraceAspect {
    @Around("execution(* com.example..WorkService.execute(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("trace-in");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("trace-out");
        }
    }
}
```

These are **illustrative fragments** needing imports, the `WorkService`/`TemporaryFailure` types, and Spring configuration; the complete runnable version is in section 7.

In Spring, `@Order` uses **lower values for higher precedence**. A higher-precedence aspect sits outside: it runs earlier on entry and later on exit. Hence with `@Order(0)` and `@Order(10)`, `InnerTraceAspect` can print **two log pairs** even though the caller called the service **once** and `OuterRetryAspect` was entered once.

If the order is reversed so trace sits **outside** retry, trace normally prints one log pair per proxy invocation; the inner retry may invoke the target multiple times. When explaining how many times an advice runs, always ask **where the advice sits in the chain**, rather than just counting annotations.

Do not rely on **source-code declaration order** between aspects. Across multiple aspects, use `@Order` or `Ordered` and verify the chain in an integration test. Advisors created by transactions, security, or caching also have their own ordering.

## 5. What If the First Pass Succeeds Yet a Second Pass Is Still Called?

This is the difference between **retry** and **replay**:

### Conditional Retry

```java
Object result;
try {
    result = pjp.proceed();
} catch (TemporaryFailure ex) {
    result = pjp.proceed();
}
return result;
```

If the first pass succeeds, the second pass **does not occur**. If the first pass throws the caught failure type, the call is retried. This fragment applies when the error **can be safely retried** and the call properly goes through the Spring proxy.

### Intentional Replay, Even on Success

```java
Object first = pjp.proceed();
Object second = pjp.proceed();
return second;
```

If both passes succeed, the inner method can still run **twice**. The caller sees the second result because `@Around` returns `second`, yet side effects from **the first pass are not automatically erased**.

If changed to `return first`, the caller receives the first result even though the target may have executed a second time. If `return new SomeResult(...)`, the caller receives a value constructed entirely by the aspect, as long as it matches the method return type. `@Around` has the right to **choose the return value**; there is no rule forcing it to return the value from the last `proceed` call.

### What If the Second Pass Fails?

```java
Object first = pjp.proceed();
Object second = pjp.proceed(); // If this throws, the return statement below does not run.
return second;
```

A failure on the second pass can cause the caller to receive an exception, **even though the first pass completed successfully and produced side effects**. Do not treat multiple `proceed` calls as an automatic transaction wrapping all passes.

## 6. `proceed(Object[] args)`: Changing Parameters on Each Pass

Spring AOP provides two overloads:

```java
Object proceed() throws Throwable;
Object proceed(Object[] args) throws Throwable;
```

`proceed()` forwards using the join point's current arguments. `proceed(Object[] args)` allows forwarding with **a new set of arguments** to the inner method.

Example for a service with `String send(String value)`:

```java
Object originalResult = pjp.proceed();

Object[] newArgs = {"normalized"};
Object replacementResult = pjp.proceed(newArgs);

return replacementResult;
```

This is a fragment inside an `@Around` of a Spring `@Aspect`. If both passes reach the target:

- The first pass receives the invocation's current arguments.
- The second pass receives the argument `"normalized"`.
- The caller sees the value that the advice `return`s; it does not automatically receive both results.

**Constraints:**

- The array must match the **number and types** of the underlying method's arguments; wrong types or wrong length can cause an invocation error.
- `null` is invalid for primitive parameters that the invocation mechanism must unbox.
- If you intend to retry with **the same data**, take a safe snapshot of the arguments if needed; do not silently mutate a shared `Object[]` and assume both passes are identical.
- When arguments contain **mutable objects**, `proceed()` does not deep-copy those objects. If the target mutates an argument on the first pass, the next pass can observe the new state even though the array reference did not change.
- Spring docs note that the semantics of `proceed(Object[])` in Spring proxy AOP **differ in detail** from pure AspectJ weaving; this lesson follows Spring's rule: the array corresponds to the **underlying method's arguments**.

Do not call `proceed` to "test-run" what the target returns and then call it again "for real" unless the operation genuinely allows repetition without harm.

## 7. Runnable Java 17+ Example: Retry Once on Failure and Call Twice on Success

This example uses only **Spring Framework 6.1.14**, `aspectjweaver 1.9.22.1`, **JDK 17+**, and Maven. This is a fixed set of versions for illustration, not a claim of being the latest releases.

Observation goals:

1. A caller invokes `service.execute("retry")` **once**.
2. Outer `ReplayAspect` calls `proceed()` the first time; target **throws `TemporaryFailure`**.
3. The aspect catches the error and calls `proceed()` a second time; target succeeds.
4. Inner `TraceAspect` runs **twice** for the two attempts.
5. Caller invokes `service.execute("twice")` **once**, yet the advice intentionally calls `proceed()` **twice even though both succeed**.
6. Total target method execution count: **4**, despite only **two** caller calls.

The `"twice"` example is used solely to expose the risk of **duplicate successful execution**, not as a recommended pattern for production writes.

### 7.1. Project Structure

```text
spring-multiple-proceed/
├── pom.xml
└── src/main/java/com/example/replay/
    ├── WorkService.java
    ├── ReplayAspect.java
    ├── TraceAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-multiple-proceed</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` brings in the container and required Spring AOP dependencies per the example's dependency tree; `aspectjweaver` is needed for Spring to parse `@Aspect`/pointcuts. This remains **proxy-based Spring AOP**, requiring no AspectJ weaving agent.

### 7.3. `src/main/java/com/example/replay/WorkService.java`

```java
package com.example.replay;

import java.util.concurrent.atomic.AtomicInteger;

public class WorkService {
    private final AtomicInteger calls = new AtomicInteger();

    public static class TemporaryFailure extends RuntimeException {
        public TemporaryFailure(String message) {
            super(message);
        }
    }

    public String execute(String label) {
        int n = calls.incrementAndGet();
        System.out.println("[TARGET] " + label + " call=" + n);

        if ("retry".equals(label) && n == 1) {
            throw new TemporaryFailure("once");
        }

        return label + "#" + n;
    }

    public int invocationCount() {
        return calls.get();
    }
}
```

The target deliberately throws a `TemporaryFailure` **only on the first execution of `execute("retry")`**. The `calls` state can be inspected via `invocationCount()`.

`AtomicInteger` avoids data races when counting; however, `execute` runs sequentially in the example. All stdout results below assume a single `DemoApp` uses the instance and executes calls in the exact order shown.

### 7.4. `src/main/java/com/example/replay/ReplayAspect.java`

```java
package com.example.replay;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(0)
public class ReplayAspect {

    @Around("execution(public * com.example.replay.WorkService.execute(..))")
    public Object replay(ProceedingJoinPoint pjp) throws Throwable {
        String label = (String) pjp.getArgs()[0];

        if ("retry".equals(label)) {
            for (int attempt = 1; attempt <= 2; attempt++) {
                System.out.println("[OUTER] attempt " + attempt);
                try {
                    return pjp.proceed();
                } catch (WorkService.TemporaryFailure ex) {
                    System.out.println("[OUTER] caught " + ex.getMessage());
                    if (attempt == 2) {
                        throw ex;
                    }
                }
            }
            throw new IllegalStateException("Unreachable retry branch");
        }

        if ("twice".equals(label)) {
            System.out.println("[OUTER] call A");
            Object first = pjp.proceed();

            System.out.println("[OUTER] call B");
            Object second = pjp.proceed();

            System.out.println("[OUTER] first=" + first
                    + "; return=" + second);
            return second;
        }

        return pjp.proceed();
    }
}
```

This aspect illustrates **two distinct policies solely to teach `proceed()` invocation counts**:

- For `"retry"`, it tries up to **twice**, retrying only on `TemporaryFailure`; if an early attempt succeeds, `return` exits the loop immediately.
- For `"twice"`, it **intentionally invokes the target twice** even when the first pass succeeds. That is valid at the API level, yet very dangerous for methods with side effects.
- For any other label, it calls `proceed()` once.

Because the aspect has `@Order(0)`, it is placed **outside** `TraceAspect` with `@Order(10)` in the demo's Spring advisor chain.

### 7.5. `src/main/java/com/example/replay/TraceAspect.java`

```java
package com.example.replay;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class TraceAspect {

    @Around("execution(public * com.example.replay.WorkService.execute(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[INNER] before");
        try {
            Object result = pjp.proceed();
            System.out.println("[INNER] after=" + result);
            return result;
        } catch (Throwable ex) {
            System.out.println("[INNER] threw="
                    + ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
```

`TraceAspect` only needs to call `proceed()` **once per advice activation**. Yet it can be activated **twice** if an outer aspect calls `proceed()` twice.

This is a common source of confusion: **an advice with only a single `pjp.proceed()` statement can still run multiple times for one external proxy call**, when a higher-precedence around advice loops over its inner chain.

### 7.6. `src/main/java/com/example/replay/AppConfig.java`

```java
package com.example.replay;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public WorkService workService() {
        return new WorkService();
    }

    @Bean
    public ReplayAspect replayAspect() {
        return new ReplayAspect();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

`@EnableAspectJAutoProxy` enables the Spring auto-proxy creator. `proxyTargetClass = true` uses a CGLIB class proxy for `WorkService`, which does not implement a business interface. Both `@Aspect` classes are registered **as Spring beans** via `@Bean`. Placing `@Aspect` alone without registering a bean will not let Spring discover the advice.

### 7.7. `src/main/java/com/example/replay/DemoApp.java`

```java
package com.example.replay;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            WorkService service = context.getBean(WorkService.class);
            System.out.println("isAopProxy="
                    + AopUtils.isAopProxy(service));

            String retryResult = service.execute("retry");
            System.out.println("caller.retry=" + retryResult);

            String twiceResult = service.execute("twice");
            System.out.println("caller.twice=" + twiceResult);

            System.out.println("targetCalls=" + service.invocationCount());
        }
    }
}
```

The caller obtains the bean from `ApplicationContext`, rather than instantiating `new WorkService()` directly. That is required for calls to enter the Spring AOP proxy where the two aspects form an advisor chain.

### 7.8. Running and Expected Stdout

With JDK 17+ and Maven able to download dependencies, in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.replay.DemoApp
```

Lines printed by the example code itself in exact order (excluding environment-dependent Maven/Spring/SLF4J messages):

```text
isAopProxy=true
[OUTER] attempt 1
[INNER] before
[TARGET] retry call=1
[INNER] threw=TemporaryFailure
[OUTER] caught once
[OUTER] attempt 2
[INNER] before
[TARGET] retry call=2
[INNER] after=retry#2
caller.retry=retry#2
[OUTER] call A
[INNER] before
[TARGET] twice call=3
[INNER] after=twice#3
[OUTER] call B
[INNER] before
[TARGET] twice call=4
[INNER] after=twice#4
[OUTER] first=twice#3; return=twice#4
caller.twice=twice#4
targetCalls=4
```

**Explanation by execution counts:**

- The caller calls `execute("retry")` **once**, yet `ReplayAspect` performs two `proceed()` calls because the first attempt failed. `TraceAspect` enters twice and the target executes twice.
- On the first attempt, the target increments `calls` to 1 **before throwing the exception**; retrying does not automatically undo that counter increment. The second attempt increments it to 2 and succeeds.
- The caller receives only `retry#2`; the first exception was caught by the outer aspect and propagated no further.
- The caller calls `execute("twice")` **once**, the outer aspect calls `proceed()` twice even though the first succeeded, so the target increments `calls` to 3 and then 4.
- The first pass of `"twice"` returns `twice#3`; the second returns `twice#4`. The outer aspect **returns `second`**, so the caller sees only `twice#4`, even though the counter-increment side effect ran on both passes.
- `targetCalls=4` proves **caller invocations (2)** do not equal **target executions (4)**.

This example verifies **Spring AOP behavior on a managed proxy**, not AspectJ compile-time weaving. Stdout is the expected output from the presented source code; in a real project, run integration tests against the exact Spring/JDK versions deployed.

## 8. Practical Application: Retries Must Have Clear Bounds and Conditions

Spring Framework uses retrying concurrency failures as a classic example of `@Around` calling `proceed()` multiple times. However, production applications need far more safeguards than a bare `for` loop.

A sound retry policy must answer:

1. **Which errors are retryable?** Catch only well-defined transient failures; never blindly retry `IllegalArgumentException`, validation errors, or permanent logic errors.
2. **What is the maximum attempt count?** Enforce an explicit bound; never write an unbounded `while (true)`.
3. **How long to wait between attempts?** Apply appropriate backoff/jitter for the system; do not force sleeping on every error.
4. **Is the operation idempotent?** If re-invoking can double-charge or send duplicate emails, retries require idempotency keys, transactional/outbox mechanisms, or deduplication-capable protocols.
5. **What did the previous attempt already do?** A failure **after** writing to the DB or calling a remote API can leave side effects behind before the exception reaches the around advice.
6. **Where does the final exception go?** Once attempts are exhausted, propagate it or convert it into a well-defined error contract; never swallow it silently.
7. **Is a retry likely to succeed?** Permanent failures should not be repeated.
8. **How are metrics tracked?** Count caller requests, retry attempts, target executions, and final outcomes **separately**.
9. **What about cancellation/timeouts?** If the invocation is cancelled or its deadline expires, stop retrying.
10. **Is it thread-safe?** Store attempt counters in local variables inside the advice method, not in mutable fields of a singleton aspect when state must be per-request.

A retry structure fragment:

```java
@Around("execution(* com.example.service.SomeService.retryableOperation(..))")
public Object retry(ProceedingJoinPoint pjp) throws Throwable {
    int maxAttempts = 3;
    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return pjp.proceed();
        } catch (TransientBusinessException ex) {
            if (attempt == maxAttempts) {
                throw ex;
            }
            // Apply backoff/cancellation policy if needed.
        }
    }
    throw new IllegalStateException("Unreachable");
}
```

This is a **fragment**; it does not run standalone because `SomeService` and `TransientBusinessException` must be defined. It illustrates retrying a method **verified to be safe to retry**; do not apply an overly broad pointcut across all `service.*` methods just because the code compiles.

### 8.1. Retries and Unsafe Side Effects

Dangerous example:

```java
public Receipt charge(String paymentId) {
    remotePaymentGateway.charge(paymentId);
    database.saveAudit(paymentId);
    return new Receipt(paymentId);
}
```

Suppose the remote gateway already succeeded, yet the database save fails and the method throws an error. If an `@Around` retries **the whole method**, the next pass may call the remote gateway **a second time**.

`proceed()` does not provide distributed transactions, cannot infer whether a prior pass had side effects, and does not generate idempotency keys. Design retries to align with business rules, transaction boundaries, and external system behavior.

## 9. Position of Retry Advice Relative to `@Transactional` Matters Greatly

If a method has both a retry interceptor and a transaction interceptor applied, ordering affects transaction scope.

### Case A: Retry **Outside** Transaction

```text
Caller
  -> RetryAround
       -> proceed attempt #1
            -> TransactionInterceptor (begin tx #1)
                 -> target
            -> rollback/commit tx #1
       -> proceed attempt #2
            -> TransactionInterceptor (begin tx #2)
                 -> target
            -> rollback/commit tx #2
```

When properly configured and **no outer existing transaction is joined**, each attempt can receive a fresh transaction. This is how the Spring documentation illustrates retrying concurrency failures so each retry runs in an independent transaction.

### Case B: Transaction **Outside** Retry

```text
Caller
  -> TransactionInterceptor (begin tx)
       -> RetryAround
            -> proceed attempt #1 -> target
            -> proceed attempt #2 -> target
  -> commit/rollback one enclosing tx
```

All attempts sit under a single outer transaction boundary. For an exception that already marked the transaction rollback-only, retrying within that same transaction may not allow the transaction to commit. Therefore, **never treat the two diagrams as equivalent**.

**Things to verify in Spring:**

- Does the retry aspect have high enough precedence to sit **outside** the transaction advisor?
- What order does `@EnableTransactionManagement(order = ...)` or the application's transaction infrastructure have?
- Is there already an active transaction from the caller before entering the service?
- Is the propagation mode `REQUIRED`, `REQUIRES_NEW`, or another mode?
- Do any callbacks, DB connections, or resources retain stale state after a failed attempt?
- Is an exception caught in a place where the transaction interceptor cannot observe it?

Even when retry sits outside the transaction advisor, if the caller already opened an outer transaction and transaction propagation joins it, you cannot assume each attempt gets an isolated transaction. Test transaction IDs/commits/rollbacks under the real configuration.

Spring offers specialized abstractions such as Spring Retry or other resilience patterns depending on your stack; when your application needs complex policies, do not hand-roll a `proceed()` loop lacking backoff, timeouts, and failure observability.

## 10. Calling `proceed()` Multiple Times Does Not Replay the Whole HTTP Request

In a Spring MVC/REST application:

```text
HTTP request -> Filter chain -> DispatcherServlet
              -> Controller -> Spring service proxy
                                  |
                                  +-- Around.proceed() #1 -> target
                                  +-- Around.proceed() #2 -> target
```

When around advice is applied to a **service bean**, calling `proceed()` again typically repeats only the **service's** method invocation chain, not:

- The entire Servlet filter chain.
- `DispatcherServlet` from the beginning.
- Controller-layer mapping/authentication/request binding that already completed.
- Operations performed before the caller invoked the service proxy.

Similarly, a transaction interceptor or inner logging aspect **can** sit inside the method chain and repeat, while middleware **outside** the method advice does not automatically re-run.

This is why **request-level metrics** must be separated from **attempt-level metrics**: one HTTP request may generate one service proxy call, yet four target executions if retry/replay performs four attempts.

## 11. Asynchronous or Reactive Return Types

If the advised method returns `CompletableFuture<T>`, `CompletionStage<T>`, `Mono<T>`, or `Flux<T>`, `proceed()` forwards the **Java method invocation**; it does not automatically become a command that waits for all async work to finish.

Example:

```java
CompletableFuture<Result> first =
        (CompletableFuture<Result>) pjp.proceed();
CompletableFuture<Result> second =
        (CompletableFuture<Result>) pjp.proceed();
return second;
```

This is a fragment. It can spawn **two futures / two async pipelines**, depending on the method's implementation, rather than "retrying after the first future failed." The first future may still be running when the caller receives the second future.

With Reactor publishers, calling a `Mono<T>`-returning method twice can create two publishers; **subscription** later triggers the work for cold publishers, whereas hot publishers behave differently. Thus, do not equate two `proceed()` calls with two subscriptions or two final outcomes.

If retries must react to **async completion failures**, use the proper mechanism such as `CompletionStage` composition, Reactor `retryWhen`, or a suitable retry/resilience library, while accounting for idempotency and reactive transaction semantics. Do not wrap `pjp.proceed()` in a synchronous `for` loop assuming it catches errors occurring later.

## 12. Spring Proxy Limitations Still Apply

The fact that `proceed()` supports multiple calls **does not overcome the limitations of proxy-based Spring AOP**:

- Applies only when the caller uses the **Spring-managed proxy**. `new WorkService().execute(...)` is not auto-proxied just because an `@Aspect` exists.
- **Self-invocation** such as `this.execute()` inside the target bypasses the Spring AOP proxy; an internal method's pointcut is not invoked through the proxy merely because `proceed()` ran in another method.
- With JDK dynamic proxies, the method must be called through the appropriate proxied interface. With CGLIB, `final`/`private` methods are not intercepted via subclass proxying like public overridable methods.
- `@Aspect` classes must be **Spring beans**; `@Aspect` alone does not register a bean.
- Auto-proxy creators and aspects are **ApplicationContext-scoped**; enabling AOP in a different context does not guarantee the current bean is proxied.
- A singleton aspect can serve multiple concurrent requests; avoid storing `attempt`, `lastError`, or `ProceedingJoinPoint` in shared mutable fields.
- Do not retain `ProceedingJoinPoint` to invoke `proceed()` **after the advice has returned**, or pass it to another thread expecting all interceptor/transaction/thread-local context to remain valid. It represents an in-flight invocation, not an arbitrary long-lived "callback" to re-run at will.

A test that calls the target directly with `new` proves nothing about Spring AOP's multiple-proceed behavior. Calls must go through the bean/proxy in `ApplicationContext`.

## 13. Testing and Diagnosing Execution Counts

An integration test can separate at least three types of counters:

| Counter | What does it count? | `retry` demo result | `twice` demo result |
| --- | --- | --- | --- |
| Caller invocation count | How many times external code calls the service proxy | 1 | 1 |
| Outer around invocation count | How many times the retry/replay advice itself is entered from the proxy | 1 | 1 |
| `proceed()` attempt count | How many times outer around forwards into the chain | 2 | 2 |
| Inner trace count | How many times inner advice runs | 2 | 2 |
| Target execution count | How many times the target actually executes its body | 2 | 2 |
| Caller-visible result | Value returned by outer around | `retry#2` | `twice#4` |

This table applies to the **demonstrated project**, where each `proceed()` reaches the target. If an inner cache/short-circuit exists, counts may differ.

Tests should cover:

1. **No error:** retry policy returns `pjp.proceed()` immediately on attempt 1; target runs once.
2. **Transient failure then success:** target runs twice; caller receives a single success.
3. **Persistent failure:** stops at max attempts and propagates the exact exception type.
4. **Non-allowlisted failure:** does not retry.
5. **Methods with side effects:** verify idempotency/deduplication and actual write/send counts.
6. **Multiple aspects:** verify `@Order` and expected inner/outer logs or metrics.
7. **Arguments:** `proceed()` preserves inputs; `proceed(newArgs)` passes the intended arguments.
8. **Return type:** caller receives a valid value, with no primitive/generic cast failures.
9. **Transactions:** verify each attempt commits/rolls back as expected when a Spring transaction advisor is present.
10. **Concurrency:** each invocation keeps its own attempt counter without leaking across concurrent calls.
11. **Proxy boundary:** `AopUtils.isAopProxy(bean)` and real calls through the Spring bean.
12. **Timeouts/cancellations:** stops retrying when the request or deadline expires per business policy.

When diagnosing "one API call produced repeated target logs," check **whether an outer `@Around` is calling `pjp.proceed()` multiple times** before assuming the HTTP client sent duplicate requests. Logging request IDs alongside **attempt numbers** helps distinguish replays within one request from a genuine second request.

## 14. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Target runs twice while caller called the service once | Outer `@Around` called `proceed()` twice | Count attempts, check branches and idempotency. |
| Trace `@Around` runs twice for a single caller invocation | Trace sits **inside** retry/replay around | Check `@Order` and chain nesting. |
| Target does not run even though call entered the proxy | `@Around` didn't call `proceed()` or inner advice short-circuited | Check cache/guard/early-return policies. |
| Caller receives second pass's value while first pass still wrote to DB | Return value and side effects are separate concerns | Ensure rollback/compensation/idempotency; don't just switch to `return first`. |
| First error vanishes | Around caught the exception and retried successfully | Intentional retry; add attempt logging/metrics and final failure policy. |
| Retries exhausted yet caller gets `null` | Advice returned null or swallowed exception after the loop | Propagate the exception or return a contract-compliant fallback. |
| `void` advice around value-returning method loses return value | `@Around` does not return `Object` per contract | Use `Object` return type and `return pjp.proceed()` or valid replacement. |
| Retrying inside a transaction still rolls back | Transaction advisor is outside or current tx is marked rollback-only | Review ordering/propagation and test transaction boundaries. |
| Duplicate email/charge | Operation is non-idempotent or fails after side effect | Use idempotency keys, dedupe/outbox/compensation; limit retries. |
| `proceed(newArgs)` throws error | Arguments array has wrong length, type, or null primitive | Check underlying method signature and runtime types. |
| Future retry misses async errors | `proceed()` returned the future before the async task failed | Retry via async/reactive operators or completion handlers. |
| No `@Around` runs despite matching pointcut | Caller bypassed Spring proxy or aspect is not registered as a bean | Check `@EnableAspectJAutoProxy`, context, bean refs, self-invocation. |
| Outer logger prints once while target prints twice | Outer logger sits outside the replay advice | Distinguish caller, outer advice, downstream chain, and target counts. |

## 15. Checklist Before Using Multiple-`proceed()` in Production

- [ ] Concrete reason exists to use `@Around` instead of `@Before`/`@AfterReturning`.
- [ ] Target operations selected by a **narrow, explicit** pointcut, not accidentally retrying the entire service layer.
- [ ] Only confirmed recoverable transient failures are retried.
- [ ] Explicit attempt limits, backoff, and deadline/cancellation policies exist.
- [ ] Idempotency and all side effects per attempt have been evaluated.
- [ ] Request-level metrics are separated from attempt-level metrics.
- [ ] `@Order`/transaction advisor ordering has been verified when transactions are present.
- [ ] No ambient transaction causes attempts to inadvertently share an unwanted transaction.
- [ ] Arguments and mutable payloads have snapshot/restoration strategies if needed.
- [ ] Final exceptions are not swallowed; return values match method contracts.
- [ ] Neither `ProceedingJoinPoint` nor per-call retry state is stored in mutable singleton aspect fields.
- [ ] Integration tests run through the Spring proxy and verify actual target execution counts.
- [ ] For async/reactive methods, retries are placed at the proper completion/subscription lifecycle.
- [ ] Observability exists for attempts and side effects in production.

### Official Spring Documentation

- Spring Framework — **Declaring Advice / Around Advice** (confirms `proceed()` may be called 0, 1, or many times): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **An AOP Example** (retrying concurrency failures with multiple `proceed()` calls, ordering with transaction advice): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/example.html
- Spring Framework — **Schema-based AOP Support** (around advice and retry example in XML): https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring Framework — **Proxying Mechanisms** (limits of calls through proxies): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — **AOP Concepts** (around advice's control over method invocation): https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html

**Conclusion:** In Spring AOP, calling `proceed()` multiple times **repeats the remaining portion of the invocation chain** at `@Around`'s position, rather than automatically re-running the entire request or outer proxy. This technique enables retries, yet can also re-run downstream advice and the target multiple times, each with its own side effects, transaction boundaries, exceptions, and return values. Use it only after thoroughly verifying that the business operation can be retried safely.
