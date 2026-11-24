# Keeping Per-Call Data in Local Variables of a Spring Aspect

## 1. Practical Problem: Matching Before and After Data for One Call

An aspect needs to record the **duration, outcome, and error** of `OrderService.submit(id)`. The same singleton aspect can handle two concurrent invocations: A succeeds, B throws an exception. The goal is not only to avoid wrong timestamps, but also to ensure A's `outcome` is not overwritten with B's state.

For state tied to a single invocation, keep the entire **capture → `proceed()` → observe → cleanup** flow inside one `@Around`:

```java
@Around("execution(* com.example.orders.OrderService.submit(..))")
public Object measure(ProceedingJoinPoint pjp) throws Throwable {
    final long startedNanos = System.nanoTime();
    String outcome = "THROWN";
    try {
        Object result = pjp.proceed();
        outcome = "RETURNED";
        return result;
    } finally {
        record(outcome, System.nanoTime() - startedNanos);
    }
}
```

This is a fragment: `record(...)` is an application helper and must have a policy if the sink fails. When A and B call the advice concurrently, each execution frame holds its own `startedNanos`/`outcome`; `final` is not the source of thread safety — **local variable scope** is the core point. `proceed()` can throw `Throwable`; `finally` still observes synchronous failure and the exception continues propagating outward, unless the recorder itself throws.

This lesson practices keeping per-invocation state in Spring AOP, covering return/throw, shared metrics, nested calls, and future/reactive boundaries. The demo in section 7 uses two latched threads to confirm **A→RETURNED** and **B→THROWN** regardless of scheduler ordering.

## 2. Choosing the Right Lifetime for Each Value

A Spring `@Aspect` is a singleton bean by default in the `ApplicationContext`, yet an advice method has a **separate execution frame each time it is called**. Aspect fields live across advice invocations; `@Around` locals live only for that invocation.

| Data | Right lifetime | Design |
| --- | --- | --- |
| `startedNanos`, `outcome`, `Throwable`, method name | One advice invocation | Local variables in `@Around` |
| ID of the current call | One invocation | Local `String`/immutable snapshot from an argument or provider |
| Execution count / aggregate latency | Multiple invocations | `LongAdder`, atomic counter, or metrics backend |
| Audit results for later lookup | Multiple invocations | Concurrent sink/map with unique key and retention policy |
| Config or dependencies | Aspect bean lifecycle | `final` reference, separately evaluating the dependency's thread safety |
| Context across threads/subscriptions | Per async/reactive contract | Propagation/Reactor Context, not relying on a "current request" field |

`local Object[] args = pjp.getArgs()` only isolates the **array reference** from an aspect field; mutable objects inside can still be shared. When a reliable snapshot is needed, copy the required scalar data according to audit policy. A thread-safe `LongAdder` also does not automatically make multi-field check-then-update operations atomic.

More important than scope is **how it completes**: local state remains usable inside the same `finally` of `@Around`; two separate advice methods `@Before` and `@After` do not share Java locals. The following sections analyze return/exception handling and run the demo.

## 3. Why Is @Around Particularly Suited to Holding Single-Invocation State?

The Spring reference recommends around advice when state needs to be shared from **before** to **after** a method execution in a thread-safe manner, such as a timer.

An `@Around` wraps `ProceedingJoinPoint.proceed()`:

```text
Client -> Spring AOP proxy
          |
          v
        @Around
          |
          +-- local started = now
          |
          +-- try {
          |      pjp.proceed()
          |         |
          |         +-- other advisors
          |         +-- target method
          |    }
          |
          +-- catch Throwable: local outcome = failure
          |
          +-- finally: local elapsed = now - started
          |
          v
        return / rethrow to caller
```

Whether the target returns normally, returns `null`, or throws an exception, once control flow enters `try` and unwinds normally, `finally` can access the **same local `started`** of that invocation.

### 3.1. Timing-only example

```java
@Around("execution(public * com.example.service..*.*(..))")
public Object time(ProceedingJoinPoint pjp) throws Throwable {
    final long start = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        final long elapsed = System.nanoTime() - start;
        System.out.println(pjp.getSignature().getName() + "=" + elapsed);
    }
}
```

This is an **illustrative snippet**, not standalone: it requires `@Aspect`, imports, and Spring AOP configuration. The timestamp is stored in a Java local primitive, not in a Spring bean field. The duration stdout is **nondeterministic** across runs.

### 3.2. Observing normal/exception outcomes with local state

```java
@Around("execution(public * com.example.service..*.*(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    final long start = System.nanoTime();
    String outcome = "THROWN";

    try {
        Object result = pjp.proceed();
        outcome = "RETURNED";
        return result;
    } finally {
        long elapsed = System.nanoTime() - start;
        record(pjp.getSignature().getName(), outcome, elapsed);
    }
}
```

In this snippet `record(...)` is a hypothetical helper, not a Spring API. If `proceed()` returns (even `null`), `outcome` changes to `"RETURNED"`. If `proceed()` throws an exception, that assignment does not run, so `outcome` remains `"THROWN"` and `finally` receives the failure state.

**Limitation:** If `record` in `finally` throws an exception itself, it can mask the original exception from `proceed()`. Instrumentation must avoid breaking business flow; use safely configured metrics/logging backends and have a policy for backend failures.

### 3.3. Does try/catch/finally alter the proxy outcome?

An `@Around` using only `try/finally` and `return pjp.proceed()` preserves the normal result or exception exiting the inner chain. Adding `catch(Throwable ex) { throw ex; }` for observation also preserves the exception when **rethrowing the same object**.

By contrast:

```java
catch (IllegalStateException ex) {
    return "FALLBACK";
}
```

**changes the outcome**: the inner chain threw, yet the outer caller sees a normal return. If you record outcome `"THROWN"` in finally before returning a fallback, you must name the metric **inner failure**, not **caller-visible failure**. With Spring transactions/caching/retry, the position of advisors in the chain affects where the outcome is observed.

## 4. Anti-Pattern: A Field Holding the In-Flight Request's Outcome

```java
@Aspect
public class UnsafeTraceAspect {
    private String currentId;
    private long startedNanos;

    @Around("execution(* com.example.service..*.*(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        currentId = String.valueOf(pjp.getArgs()[0]);
        startedNanos = System.nanoTime();
        try {
            return pjp.proceed();
        } finally {
            System.out.println(currentId + ":" +
                    (System.nanoTime() - startedNanos));
        }
    }
}
```

This is a counterexample, not an implementation pattern. After A sets `currentId="A"` and enters the target, B can set `currentId="B"`; A exits `finally` and logs B by mistake. Adding `volatile` only changes visibility of the shared field; making the entire advice `synchronized` serializes business logic, hurts throughput, and complicates nested calls.

Fix it by declaring `String currentId` and `long startedNanos` **inside the advice method**, like the pattern in section 1. A local value referencing a mutable DTO can still be modified elsewhere; if reporting requires an exact snapshot, use an immutable snapshot instead of retaining the entire argument graph.

## 5. Use Locals for Per-Invocation Values, Thread-Safe Structures for Aggregates

An application typically needs two layers of data:

1. **Within the invocation**: `start`, `id`, `outcome`, `Throwable error`, `Object result` — should be local.
2. **After the invocation**: total requests, latency metrics, audit records — need to be stored where multiple threads write concurrently.

Just because `private long completed` sits in an `@Aspect` does not mean Spring manages concurrency for it. If counting with:

```java
private long completed;

public void increment() {
    completed++; // Non-atomic read-modify-write.
}
```

updates can be lost when two threads increment together.

A better shared counter example:

```java
private final LongAdder completed = new LongAdder();

public long completedCount() {
    return completed.sum();
}
```

With `import java.util.concurrent.atomic.LongAdder`, `completed.increment()` calls can be executed safely by multiple threads, suited for high-concurrency statistics. `sum()` is a snapshot **not atomic with respect to all concurrent increments in progress**; when requests are in flight, it should not be treated as an absolute invariant without extra synchronization.

For per-invocation data that must be queried later, you can use:

```java
private final ConcurrentMap<String, Observation> observations =
    new ConcurrentHashMap<>();
```

where `Observation` is an immutable record. However, you need a **unique key per invocation** and a policy to prevent memory leaks: evict/bound entries or push to a tracing/metrics backend. The runnable example below uses keys `A` and `B` that are **unique within the demo**, which is not a suitable contract if production can receive multiple concurrent calls with the same business ID.

## 6. Why Can't @Before and @After Normally Share Local Variables?

Two advice methods are **two separate Java method invocations**:

```java
@Before("execution(* com.example.service..*.*(..))")
public void before() {
    long started = System.nanoTime();
}

@After("execution(* com.example.service..*.*(..))")
public void after() {
    // Cannot access the local variable "started" of before().
}
```

`started` exists only in the execution frame of `before()`. `after()` cannot retrieve it simply by matching the same pointcut, and Spring has no built-in mechanism to "pair local variables" between two advice methods.

If the goal is measuring duration from before to after of the **same method invocation**, use a single `@Around` with `try/finally`. This is a simpler design than creating a `ThreadLocal` and manually pairing `@Before`/`@After`.

### When should you still use @Before/@After?

- `@Before` is appropriate when you only need to check preconditions/log before the method, **without** keeping variables across the execution.
- `@AfterReturning` is appropriate when you only need the normal result.
- `@AfterThrowing` is appropriate when you only need to record an exception.
- `@After` is appropriate for cleanup that does not depend on state created by `@Before`.
- `@Around` is appropriate when you need **one local scope spanning both before and after**.

The Spring reference recommends using the **least powerful advice** that meets your needs; there is no need to use `@Around` for everything. But for a start/stop timer needing a per-invocation `start`, `@Around` provides the best scope.

## 7. Runnable Project: Two Concurrent Calls, No State Contamination

To prove isolation, the following Java 17 example creates a Spring target bean, a singleton aspect, and calls the target method **concurrently on two threads**. `CountDownLatch` holds both calls inside the target before allowing them to finish.

The aspect records:
- `id` taken from arguments, stored in a local;
- `startedNanos` stored in a local;
- `outcome` as a local updated after `proceed()`;
- `elapsedNanos` as a local in `finally`;
- the final result placed in a `ConcurrentHashMap` safe for concurrent writes.

**Stdout is printed after both `Future`s complete**, so it does not depend on whether thread A or B runs first. The demo intentionally makes `A` return normally and `B` throw an unchecked exception; we verify both record the right outcome.

### 7.1. Environment and Structure

- Java **17+**;
- Spring Framework **6.1.14**;
- AspectJ Weaver **1.9.22.1**;
- Gradle with Java 17 support;
- No Spring Boot, web server, or database required.

```text
spring-aop-local-state/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/local/
    ├── Gate.java
    ├── WorkService.java
    ├── TraceAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 7.2. Gradle project

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-local-state'
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
    mainClass = 'demo.local.DemoApplication'
}
```

`spring-context` provides the container/configuration; `spring-aop` provides the proxying infrastructure; `aspectjweaver` supports parsing Spring `@AspectJ` pointcut expressions.

### 7.3. Synchronizing Two Invocations with CountDownLatch

`src/main/java/demo/local/Gate.java`:

```java
package demo.local;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class Gate {
    private final CountDownLatch entered = new CountDownLatch(2);
    private final CountDownLatch release = new CountDownLatch(1);

    public void waitInsideTarget() {
        entered.countDown();

        try {
            if (!release.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("release timeout");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", ex);
        }
    }

    public void awaitBothEntered() throws InterruptedException {
        if (!entered.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("workers did not enter");
        }
    }

    public void open() {
        release.countDown();
    }
}
```

`Gate` serves only **concurrency testing**, not as an AOP component. Each worker calling `waitInsideTarget()` signals it has entered the method and waits. `main` waits for both to reach the gate before releasing them to continue. Timeouts protect the demo from waiting forever if the environment fails.

### 7.4. Spring target service

`src/main/java/demo/local/WorkService.java`:

```java
package demo.local;

public class WorkService {
    private final Gate gate;

    public WorkService(Gate gate) {
        this.gate = gate;
    }

    public String handle(String id) {
        gate.waitInsideTarget();

        if ("B".equals(id)) {
            throw new IllegalStateException("failed-B");
        }
        return "OK-" + id;
    }
}
```

The `handle` method is public non-final and the target class is also non-final; Spring can create a CGLIB class-based proxy. With `id="A"` it returns `"OK-A"`, and with `id="B"` it throws `IllegalStateException("failed-B")`. Both executions pass through a shared `Gate` solely to prove they truly overlap.

### 7.5. Safe Aspect: Local State + ConcurrentHashMap

`src/main/java/demo/local/TraceAspect.java`:

```java
package demo.local;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TraceAspect {
    private final ConcurrentMap<String, Observation> records =
        new ConcurrentHashMap<>();

    public record Observation(String outcome, long elapsedNanos) {}

    @Around(
        value = "execution(public String demo.local.WorkService.handle(String))"
              + " && args(id)",
        argNames = "id"
    )
    public Object observe(ProceedingJoinPoint pjp, String id)
            throws Throwable {

        // Per-invocation locals:
        final String invocationId = id;
        final long startedNanos = System.nanoTime();
        String outcome = "THROWN";

        try {
            Object result = pjp.proceed();
            outcome = "RETURNED";
            return result;
        } finally {
            final long elapsedNanos =
                System.nanoTime() - startedNanos;

            // Only the cross-invocation aggregation step writes to shared state.
            records.put(invocationId,
                new Observation(outcome, elapsedNanos));
        }
    }

    public String outcomeFor(String id) {
        Observation found = records.get(id);
        return found == null ? "MISSING" : found.outcome();
    }

    public int recordedCount() {
        return records.size();
    }
}
```

**Variable-by-variable breakdown:**
- `pjp` is the current `ProceedingJoinPoint`. `ProceedingJoinPoint` must come first in the `@Around` signature.
- `id` is bound by Spring from `args(id)`; `argNames="id"` intentionally omits `pjp` since it is the first `ProceedingJoinPoint` parameter.
- `invocationId` copies the **immutable `String` reference** into its own local. If the actual argument is a mutable object, snapshotting data requires an immutable representation/copy.
- `startedNanos`, `outcome`, and `elapsedNanos` are locals belonging to the execution frame of this specific advice run.
- If `proceed()` returns, `outcome` changes to `"RETURNED"`; if it throws, it stays `"THROWN"`.
- `finally` puts the final result into `ConcurrentHashMap`. `Observation` is an immutable Java record.
- The demo uses unique `id` values `A`/`B` as keys. In production you **must use a truly unique invocation id** or a different aggregation design; two calls with the same business ID should not accidentally overwrite each other.
- `records` is a **shared field** but safe when multiple threads `put` concurrently thanks to `ConcurrentHashMap`; it holds completed results, not in-flight timestamps.
- The advice **does not alter the exception/result**: it returns `result` as-is, and when `proceed()` throws, after `finally` runs, the exception continues propagating.
- `elapsedNanos` is stored but **not printed** because actual duration varies by environment.

**Key verification point:** When A and B overlap in the target, both run on the **same `TraceAspect` instance** without locals overwriting each other. After both futures complete, the map contains `A→RETURNED` and `B→THROWN`.

### 7.6. Spring AOP Configuration

`src/main/java/demo/local/AppConfig.java`:

```java
package demo.local;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public Gate gate() {
        return new Gate();
    }

    @Bean
    public WorkService workService(Gate gate) {
        return new WorkService(gate);
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

`@Aspect` alone **does not register a bean**. `@Bean traceAspect()` creates the aspect in the Spring container; `@EnableAspectJAutoProxy(proxyTargetClass = true)` enables Spring AOP and forces a class-based proxy for the `WorkService` target, which declares no service interface.

`Gate` is a shared Spring bean using thread-safe `CountDownLatch` primitives. `TraceAspect` is a shared bean holding a concurrent map, while each `observe(...)` call has its own local state.

### 7.7. Main Executing Two Threads and Printing Deterministic Results

`src/main/java/demo/local/DemoApplication.java`:

```java
package demo.local;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            WorkService service = context.getBean(WorkService.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);
            Gate gate = context.getBean(Gate.class);

            ExecutorService pool = Executors.newFixedThreadPool(2);

            try {
                Future<String> a =
                    pool.submit(() -> service.handle("A"));

                Future<String> b = pool.submit(() -> {
                    try {
                        return service.handle("B");
                    } catch (IllegalStateException ex) {
                        return ex.getClass().getSimpleName()
                            + ":" + ex.getMessage();
                    }
                });

                // Ensure both calls have entered the target before opening the gate.
                gate.awaitBothEntered();
                gate.open();

                String aValue = a.get();
                String bValue = b.get();

                System.out.println("proxy="
                    + AopUtils.isAopProxy(service));
                System.out.println("overlapped=true");
                System.out.println("A=" + aValue);
                System.out.println("B=" + bValue);
                System.out.println("traceA="
                    + aspect.outcomeFor("A"));
                System.out.println("traceB="
                    + aspect.outcomeFor("B"));
                System.out.println("recorded="
                    + aspect.recordedCount());

            } finally {
                gate.open();
                pool.shutdownNow();
            }
        }
    }
}
```

**Why doesn't stdout depend on a race?**
- `CountDownLatch entered` waits until **both invocations** have reached the target code.
- Main opens `release` after both have entered, guaranteeing overlap in time.
- Nothing is printed directly from the target, advice, or worker threads; printing happens **only after `a.get()` and `b.get()` finish**.
- Because `Future.get()` completes after the advice has finished running `finally`, the entries are already in the concurrent map when main reads them.
- `A`/`B` are distinct keys so `put` order does not affect the values read.
- `pool.shutdownNow()` runs in `finally` to release resources even on failure; `gate.open()` ensures no worker waits at the gate indefinitely.

### 7.8. Running with Gradle

From the project directory containing `build.gradle`:

```bash
gradle run
```

If Gradle Wrapper is installed, use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows).

**Stdout printed by the Java code** when tasks finish within the configured timeout:

```text
proxy=true
overlapped=true
A=OK-A
B=IllegalStateException:failed-B
traceA=RETURNED
traceB=THROWN
recorded=2
```

Gradle lines or system logs are not part of this stdout block. If the machine cannot start two workers or hangs longer than 10 seconds, the demo reports a timeout rather than claiming results under unmet environmental conditions.

### 7.9. Proof Explanation

| Factor | Invocation A | Invocation B |
| --- | --- | --- |
| Target call | `service.handle("A")` | `service.handle("B")` |
| Outcome of `proceed()` | Returns `"OK-A"` | Throws `IllegalStateException("failed-B")` |
| Local `invocationId` | `"A"` | `"B"` |
| Local `outcome` after proceed | `"RETURNED"` | `"THROWN"` |
| `finally` runs | Yes | Yes |
| Aggregate data | `records["A"] = Observation("RETURNED", ...)` | `records["B"] = Observation("THROWN", ...)` |

Both A and B share **one `TraceAspect` instance**, yet there is no `currentId` or `startedNanos` field for them to contend over. Using locals means there is no shared field to leak B's identifier or timestamp to A.

### 7.10. What if @Around Is Bypassed and Target Is Called Directly?

Calling:

```java
WorkService service = new WorkService(new Gate());
```

creates an object outside the Spring container; it is not a proxy so `TraceAspect.observe` **does not run automatically**. The snippet above only illustrates proxy boundaries and is **not runnable standalone like the project in section 7** because `Gate` and threads must be coordinated properly.

Internal calls like `this.handle("A")` from a method inside `WorkService` itself also bypass the Spring AOP proxy; the advice method and its locals **are not created** for that internal call. You cannot solve self-invocation merely by changing fields to locals.

## 8. `ThreadLocal` Is Not the Default Choice for Timers

`@Before` and `@After` are two separate method calls and cannot directly share a local `started`; that is why `@Around` is more convenient. Using `ThreadLocal<Long>` to pass a timestamp between them adds extra obligations: remove/restore in `finally`, preserve outer state when nested advice runs on the same thread, watch for thread pool reuse, and handle cases where an advisor is skipped due to pointcuts/ordering.

When per-thread context is strictly required, preserve the previous value to return it to the outer scope:

```java
String previous = traceId.get();
traceId.set(currentId);
try {
    return pjp.proceed();
} finally {
    if (previous == null) traceId.remove();
    else traceId.set(previous);
}
```

This is a fragment requiring `traceId`, `currentId`, and `pjp`. State for a single advice invocation should still be local; the dedicated ThreadLocal lesson covers cleanup, MDC, nested calls, and thread hops in full.

## 9. Local State When Moving to `@Async`, `CompletableFuture`, or Reactor

Local variables continue to **isolate individual advice invocations**, but the lifetime they describe depends on the interception point. If `@Async` places an async advisor outside `@Around`, the target/advice code on the worker may run on a different thread from the caller. If `@Around` measures on the caller side, it may only see the submission time and the returned future. Inspect actual advisor ordering and proxy paths before naming metrics.

```java
@Around("execution(* com.example.service..*.loadAsync(..))")
public Object measureCall(ProceedingJoinPoint pjp) throws Throwable {
    long start = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        System.out.println("method-boundary-ns=" + (System.nanoTime() - start));
    }
}
```

This snippet accurately measures the **method execution boundary**, and does not promise to measure completion of a still-pending `CompletableFuture`. With Reactor `Mono`/`Flux`, returning a publisher can happen before subscription; to measure each subscription, create the timestamp inside `defer` and use `doFinally` appropriately. Neither case gives any reason to turn a single invocation's timestamp into a mutable singleton field.

Later lessons on `@Async` and reactive pipelines address thread/context propagation, completion, errors, and cancellation separately.

## 10. Nested Invocations and Retries: Is Local State Still Correct?

### 10.1. Nested invocation through a proxy

If service method A calls method B **through a Spring-managed proxy** and both match the same `@Around`, Spring invokes the advice twice:

```text
A advice frame:
  local startedA
  proceed A
    -> B advice frame:
         local startedB
         proceed B
         finally elapsedB
  finally elapsedA
```

`startedA` and `startedB` are distinct locals even when both calls occur **on the same thread**. This is an advantage over a single `ThreadLocal<Long>` that gets overwritten in B.

If A calls `this.B()` inside the same target and bypasses the proxy, there will be **no B advice frame**, which is not evidence of locals mixing — Spring AOP simply did not intercept B.

### 10.2. Retries with multiple proceed() calls

A Spring `@Around` is allowed to call `pjp.proceed()` multiple times. If an invocation creates a local `started` before a loop and performs three attempts, that timestamp measures the **entire retry scope**, not the duration of each attempt.

To give each attempt its own timing:

```java
for (int attempt = 1; attempt <= 3; attempt++) {
    long attemptStart = System.nanoTime();
    try {
        Object result = pjp.proceed();
        recordAttempt(attempt, System.nanoTime() - attemptStart);
        return result;
    } catch (RetryableException ex) {
        recordAttempt(attempt, System.nanoTime() - attemptStart);
        if (attempt == 3) {
            throw ex;
        }
    }
}
throw new AssertionError("unreachable");
```

This **algorithmic snippet** requires defining `RetryableException`/`recordAttempt(...)` and placing it in an `@Around` with `throws Throwable`. It is not production code: retries need backoff, idempotency, timeouts, and transaction semantics. The main point: local `attemptStart` is **per-attempt**, whereas a local `started` outside the loop is **per-around-invocation**. You must pick the right scope to measure.

A single caller invocation can encompass multiple attempts and multiple target executions. Do not assume `one @Around invocation = exactly one target execution` if your own advice or a retry advisor calls `proceed()` multiple times.

## 11. Exceptions That Local State Alone Does Not Solve

### 11.1. Mutable target arguments

```java
Object[] args = pjp.getArgs();
SomeMutableDto dto = (SomeMutableDto) args[0];
```

The variables `args` and `dto` are local **references**, yet the DTO object could be a shared mutable argument passed by multiple threads. If the advice mutates `dto` without synchronization, races still occur.

To snapshot data for auditing, store only the needed fields as immutable values, or make a defensive copy according to the DTO's semantics.

### 11.2. Shared aspect dependencies

```java
private final SimpleDateFormat formatter = new SimpleDateFormat("...");
```

If multiple advice invocations concurrently call a shared non-thread-safe formatter, making the timestamp local **does not fix the problem in the dependency**. Use a thread-safe API such as `java.time.format.DateTimeFormatter`, immutable configuration, or proper synchronization inside the dependency.

### 11.3. Advice logging or metrics itself can throw exceptions

If `finally` misuses a mutable logger/sink or throws an exception, the business outcome can be altered. Local variables prevent state interleaving; they do not guarantee the logging backend is always safe. Define an explicit instrumentation-failure policy: can metrics be dropped? Should audit failure roll back? Who observes sink failures?

### 11.4. Sensitive data must not enter logs

`pjp.getArgs()` can contain passwords, tokens, or PII. Taking a local snapshot does not make data privacy-safe. Log only allowlisted metadata, redact secrets, and avoid retaining large object graphs in singleton maps that cause memory retention.

### 11.5. Context boundaries and multiple ApplicationContexts

Aspect singleton status is per actual **container scope**; an application with multiple `ApplicationContext`s can create multiple aspect instances. Do not infer from "singleton Spring bean" that every app in the JVM shares one object. Conversely, one singleton aspect in one context still serves multiple threads, so per-invocation locals are always beneficial.

## 12. Error Matrix and Remediation

| Symptom | Cause | Remediation |
| --- | --- | --- |
| Request A's log prints B's ID | `currentRequestId` field overwritten by threads | Move ID to a local in `@Around` |
| Wrong duration under concurrent calls | Shared `startedNanos` field overwritten | Place `startedNanos` in invocation scope |
| Adding `volatile` still fails | Visibility does not create per-invocation copies | Use locals; choose proper shared-state design |
| `synchronized` sharply drops throughput | Serializes the entire advice/target invocation | Remove shared-state dependency instead of locking the method |
| Completed count lower than actual | `counter++` on singleton aspect loses updates | `AtomicLong`/`LongAdder` or metrics backend |
| Previous request's ThreadLocal appears on new request | Forgot `remove()` on pooled thread | Use `try/finally` and proper restore/remove |
| Nested method B corrupts A's duration | `ThreadLocal<Long>` overwritten by B | Use nested `@Around` locals or a properly designed stack/context |
| Async future still running yet around prints completed | Measured method return instead of async task completion | Instrument completion stage / tracing framework |
| Reactor Mono freshly created already shows "duration" | Method returned publisher before subscription executed | Use Reactor operators/context per subscription |
| Aggregate map overwrites on same business ID | Key not unique per invocation | Use unique invocation ID, avoid silent overwrites |
| Observation map grows forever | No eviction/retention policy | Evict/TTL/metrics backend, do not retain every invocation indefinitely |
| Aspect does not run when calling `this.method()` | Self-invocation bypasses proxy | Extract to another Spring collaborator, call via proxy |
| Local holds DTO yet data still races | Local reference points to shared mutable DTO | Immutable snapshot/copy or synchronize dependency |
| Advice does not run due to missing proxy | Aspect not a bean, AOP disabled, pointcut mismatch | Check registration, `AopUtils.isAopProxy`, and method signature |
| Logging exception masks original error | `finally` throws on its own | Separate instrumentation failure policy and preserve cause |
| Concurrency test passes intermittently | Test depends on thread scheduling | Use `CountDownLatch`/deterministic coordination and assert after `Future.get()` |

## 13. Checklist for Reviewing a Stateful Spring Aspect

- [ ] Every value tied to **a single invocation** (`started`, `id`, `error`, `result`) is stored as a local.
- [ ] No singleton mutable fields serving only as "current request" or "current method invocation".
- [ ] `@Around` returns `pjp.proceed()` properly and rethrows exceptions when there is no fallback policy.
- [ ] `finally` performs cleanup/timing for both normal and throwing completions, without unintended `return`/`throw`.
- [ ] Mutable shared counters use appropriate thread-safe primitives/implementations.
- [ ] Shared maps use concurrent collections, unique keys, and have a retention policy.
- [ ] Do not mistake a `final` reference for deep immutability of the object it points to.
- [ ] Do not use `ThreadLocal` for anything easily solved by `@Around` local variables.
- [ ] If using ThreadLocal, restore/remove in finally and test nested invocations/thread reuse.
- [ ] Async/reactive boundaries are identified: do you need to measure the method call or the entire task/subscription?
- [ ] Nested calls, retries, and multiple `proceed()` calls have explicit measurement scopes.
- [ ] Advice does not log sensitive data or retain large object graphs in singleton state.
- [ ] Spring `@Aspect` is actually a Spring bean; target goes through a Spring-managed proxy and the pointcut matches.
- [ ] Real concurrency tests exist, not only sequential tests; tests do not depend on thread order in stdout.
- [ ] Both normal return and thrown exception paths are tested to verify per-invocation state is not mixed.

## 14. Conclusion

For a **Spring Aspect**, the safest and simplest way to hold data private to a single call is **local variables inside an `@Around` advice**:

```java
@Around("execution(* com.example.service..*.*(..))")
public Object measure(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        // elapsed belongs to exactly one advice invocation.
    }
}
```

From there, clearly separate:
- **Local state per invocation:** timestamps, argument snapshots, outcomes, failures, temporary buffers.
- **Shared state across invocations:** aggregate metrics, counters, audit storage — requiring thread-safe mechanisms and clear lifecycles.
- **Thread-bound/reactive context:** used only when requirements extend beyond one advice invocation, with proper context propagation and cleanup.

Spring AOP only applies advice when calls pass through a **Spring-managed proxy**. Local variables protect the data of an **actual advice invocation**; they do not make self-invocation advised, do not isolate shared mutable DTOs on their own, and do not turn a synchronous `@Around` into a full asynchronous task duration timer.

### Official Spring Documentation

- [Spring Framework — Declaring Advice, Around Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): Spring recommends around advice when state needs to be shared before and after an invocation in a thread-safe way, `ProceedingJoinPoint.proceed()`, and return/throw semantics.
- [Spring Framework — Aspect Instantiation Models](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html): default singleton aspect, `perthis`/`pertarget`/`pertypewithin`, and `percflow` limitations.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, call paths, self-invocation.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): registering and enabling aspects in a Spring context.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): scope of method-execution join points and advice semantics.
- [Spring Framework — Asynchronous Execution](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): execution context of `@Async` and task scheduling.
