# Spring AOP: Singleton Aspects Used Concurrently by Multiple Calls

## 1. Nature of the Problem

In the Spring Framework, an aspect declared with `@Aspect` and registered as a Spring bean (for example `@Component`) **uses the singleton instantiation model by default**: essentially there is **one instance of the aspect per ApplicationContext**. This same instance can handle advice for **multiple calls and multiple threads** concurrently.

```java
@Aspect
@Component
public class AuditAspect {
    @Before("execution(* demo.concurrent.WorkerService.process(..))")
    public void before(JoinPoint jp) {
        System.out.println(jp.getSignature().getName());
    }
}
```

This is a **fragment**: it requires imports, Spring configuration, a target bean, and a caller going through an AOP proxy. There is no rule saying Spring will create a new `AuditAspect` for each invocation of `process()`. If a web application receives multiple requests or two worker threads call the service simultaneously, advice invocations can **overlap in time** on the same aspect object.

Three questions must be distinguished:

1. **How many aspect instances are there?** By default, one singleton aspect per corresponding bean/application context.
2. **How many times is the advice invoked?** Corresponding to invocations that match the pointcut and actually go through the Spring AOP proxy.
3. **How many threads can execute the same advice?** Potentially multiple threads simultaneously; Spring does not automatically make the entire advice method `synchronized` just because the aspect is a singleton.

**Conclusion:** Singleton **does not mean** single-threaded, is not a mutex, and does not automatically guarantee thread safety. The most important issue is **which state resides in the aspect's fields** and **which state exists only locally within each advice invocation**.

This lesson focuses entirely on **Spring Aspect / Spring AOP proxies**, aspect instance concurrency, where to place state, and proxy/lifecycle boundaries. It does not go into AOP in general or AspectJ compile-time/load-time weaving.

## 2. Spring's Singleton Is Per-Container, Not JVM-Wide

Spring IoC defines singleton scope per **bean definition within a container**:

- The same Spring bean name in the same ApplicationContext usually returns the same managed object.
- Having **two independent ApplicationContexts** can result in two corresponding aspect instances, if each context creates the aspect bean.
- Do not equate Spring singleton scope with the GoF singleton based on a JVM/classloader-wide `static instance`.
- A singleton aspect is **distinct** from a singleton target service: they can be two separate bean definitions, initialized and managed independently.

A familiar configuration:

```java
@Configuration
@ComponentScan("demo.concurrent")
@EnableAspectJAutoProxy
public class AppConfig {}
```

Within the scanned package, Spring finds `@Aspect @Component` and registers the aspect bean. The Spring AOP infrastructure creates advisors from the advice methods and attaches them to Spring proxies for matching target beans.

One might call:

```java
var context = new AnnotationConfigApplicationContext(AppConfig.class);
AuditAspect first = context.getBean(AuditAspect.class);
AuditAspect second = context.getBean(AuditAspect.class);
System.out.println(first == second); // true within the same singleton context.
```

This is a **fragment**; the context should be closed when finished. It proves that two bean lookups return the same reference; **it does not prove that the advice executes only once**. One object can have a million method calls, including many running in parallel.

### When is the aspect created?

- Spring creates beans/registers advisors during context initialization according to the bean lifecycle and configuration.
- When an invocation passes through the proxy and the pointcut matches, the advice method is invoked on the aspect instance already managed by Spring.
- Advice is not newly instantiated per request just because a new HTTP request arrives.
- `@PostConstruct` (if used) on an aspect pertains to **bean initialization**, not a "before each invocation" hook.

**Do not store request data in a field of a singleton aspect** merely because the field is assigned inside a before advice.

## 3. Diagram of Two Parallel Calls on the Same Aspect

```text
                     Spring ApplicationContext
                              |
                       singleton AuditAspect
                         shared fields
                         /          \
                        /            \
               Thread A             Thread B
                  |                    |
       Spring proxy.process("A")  Spring proxy.process("B")
                  |                    |
          advice invocation A   advice invocation B
          local variables A     local variables B
                  |                    |
                  +---- same aspect object ----+
                  |                    |
              Target A             Target B
                  |                    |
           return "done-A"       return "done-B"
```

Things that **can be shared**:

- Instance fields of the aspect: `currentId`, `startTime`, counters, caches, maps, collections...
- Collaborator objects injected into the aspect: repositories, metrics registries, logger wrappers, services...
- Static fields/global state created by the application itself.
- State of the **singleton target bean** if the target is also a singleton.

Things that are **separate for each invocation**:

- Advice method parameters, such as `JoinPoint jp`, `ProceedingJoinPoint pjp`.
- Local variables created inside the advice, such as `String id`, `long startedAt`.
- The result of `proceed()` and exceptions of a specific invocation (unless you intentionally assign them to shared state).

There is no need to create an aspect object per invocation to protect local variables: **each Java call has its own stack frame**. However, if a local variable references **a shared mutable object**, that object can still suffer from race conditions.

## 4. Counterexample: Storing Per-Request Data in a Field

```java
@Aspect
@Component
public class UnsafeAuditAspect {
    private String currentRequestId; // SHARED across calls.

    @Before("execution(* demo.concurrent.WorkerService.process(..))"
          + " && args(requestId)")
    public void before(String requestId) {
        currentRequestId = requestId; // Overwrites singleton state.
    }

    @AfterReturning("execution(* demo.concurrent.WorkerService.process(..))")
    public void after() {
        System.out.println("completed request=" + currentRequestId);
    }
}
```

This is an **intentionally unsafe counterexample** and is not part of the runnable program in section 8. Even though the `currentRequestId` field holds only a single String, the logic of writing and then reading across two different advice calls binds data from **invocation A** to a shared field of the **aspect bean**.

One valid interleaving:

```text
Thread A: before("A") -> currentRequestId = "A"
Thread B: before("B") -> currentRequestId = "B"
Thread A: target A returns
Thread A: after() -> reads currentRequestId as "B" (WRONG)
Thread B: after() -> may also read "B"
```

There is no separate invocation-A binding created by Spring for the field. `@Order` or different method names do not prevent two threads from interleaving. **The "enter before, exit after" advice behavior applies to a single invocation chain**, and does not turn the entire singleton aspect into a critical section.

### 4.1. Is adding `volatile` enough?

```java
private volatile String currentRequestId;
```

**Not enough.** `volatile` can provide visibility of the latest value, but it does not tie value A to invocation A. In the example, thread A is even more likely to see the newly updated value B. The goal is not "reading the latest value", but **reading the exact data belonging to the current request**.

### 4.2. Is `synchronized` advice a solution?

If you only place `synchronized` on `before()` and `after()`, the two method calls are locked separately, **with no lock held across the target execution**. Call A can yield to before B and then enter after A, so it is still wrong.

Even locking the entire `@Around`:

```java
@Around("execution(* demo.concurrent.WorkerService.process(..))")
public synchronized Object serializeAll(ProceedingJoinPoint pjp)
        throws Throwable {
    return pjp.proceed();
}
```

the snippet above is only a **fragment**, not a recommendation. It makes invocations sharing the same aspect instance run sequentially, which can create a bottleneck and impact latency/throughput; using `synchronized` does not automatically cover call paths that bypass the proxy, async callbacks, or other bean contexts. For per-invocation data, **local variables** are far better than locking the entire business operation.

### 4.3. Does `AtomicReference<String>` fix "current request"?

No. `AtomicReference` makes updates/reads of the reference atomic and provides memory visibility; it still represents **one shared value slot**. When A writes and then B writes, A has no way to know which later value belongs to A. Use atomic references for **shared coordination state**, not as a replacement for per-invocation context.

## 5. Safest Approach: Per-Invocation Data Lives in Local Variables

For requirements like logging/timing before and after a method, Spring recommends `@Around` because it can keep both values on the **same stack frame of a single advice invocation**:

```java
@Aspect
@Component
public class SafeAuditAspect {
    @Around("execution(* demo.concurrent.WorkerService.process(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String requestId = (String) pjp.getArgs()[0]; // Local.
        long started = System.nanoTime();             // Local.

        try {
            Object result = pjp.proceed();
            System.out.println("finished " + requestId
                    + " in " + (System.nanoTime() - started) + " ns");
            return result;
        } catch (Throwable ex) {
            System.out.println("failed " + requestId);
            throw ex;
        }
    }
}
```

The snippet above is an **illustrative fragment**, assuming the `process(String)` method matches the signature and has one String argument. If the pointcut is broad across multiple signatures, you must check `getArgs().length` and types. In production, `requestId` might be sensitive: apply an appropriate logging/redaction policy.

**Why is this more correct?**

- Each call to `around(...)` has its own `requestId` and `started`.
- Thread B cannot directly assign to a local variable in thread A's stack frame.
- `pjp.proceed()` can run other interceptors or the target, and then return to the **same** frame containing `started`.
- Exceptions are rethrown and the result is preserved. It does not accidentally swallow exceptions or alter the return value.
- The aspect can still have only **one instance** in the Spring context; there is no need to create a new aspect.

**One limitation:** `@Around` measures the duration of the synchronous invocation inside `proceed()`. If the method returns an incomplete `CompletableFuture<T>` or reactive publisher, this elapsed time may only be the wrapper creation time, not the completion time of the async task. Completion duration must be measured using the corresponding completion/reactive API.

## 6. When Shared Metrics Are Truly Needed, Use Thread-Safe Structures

Not **every field** is bad. A Spring aspect can hold immutable configuration or **intentional, thread-safe shared state**.

### 6.1. Immutable dependencies and config

```java
@Aspect
@Component
public class PolicyAspect {
    private final String environment = "demo";
    private final AuditPort auditPort;

    public PolicyAspect(AuditPort auditPort) {
        this.auditPort = auditPort;
    }
}
```

This is a fragment; `AuditPort` is a hypothetical interface. `final` fixes the reference after initialization, but if `auditPort` points to a mutable object that is not thread-safe, injecting it into a singleton aspect **does not automatically make that collaborator thread-safe**.

Spring is responsible for the lifecycle and safe publication of singleton bean state completed during normal initialization. If a config field is mutated **after** the bean has been published, appropriate concurrency control such as `volatile` or locks must be applied; Spring does not automatically synchronize your runtime mutations.

### 6.2. Counters: `AtomicInteger` / `LongAdder`

```java
private final AtomicInteger active = new AtomicInteger();
private final AtomicInteger peak = new AtomicInteger();
private final LongAdder completed = new LongAdder();

int now = active.incrementAndGet();
peak.accumulateAndGet(now, Math::max);

try {
    return pjp.proceed();
} finally {
    active.decrementAndGet();
    completed.increment();
}
```

This is a fragment intended for `@Around`, requiring imports from `java.util.concurrent.atomic`. These counters are **shared aggregate state**, not request-specific data:

- `active`: the number of invocations currently inside the `try/finally` block as observed by the aspect.
- `peak`: the highest concurrent count observed via atomic accumulation.
- `completed`: the number of times the advice exited, including exceptional exits if `finally` runs.
- `LongAdder` is often suitable for high-contention counters, but `sum()` during concurrent updates is not a strictly linearizable snapshot; observed metrics may be approximate at the time of reading.
- Counter metrics do not prove the target method succeeded; separate naming/logic is needed if you only want to count successes.

**Do not** use an unsynchronized `int count++` on a singleton aspect to accurately count every call: incrementing involves read-modify-write, so concurrent updates can be lost.

### 6.3. Shared maps/caches

If you need to look up or cache metrics by method name or a stable tag, you can use `ConcurrentHashMap` or a caching library with an appropriate concurrency policy. However, a thread-safe map does not automatically protect **mutable value objects** inside the map. You need expiration/eviction rules, cardinality control, and to avoid keys containing PII.

Brief example:

```java
private final ConcurrentHashMap<String, LongAdder> counts =
        new ConcurrentHashMap<>();

void countByMethod(String name) {
    counts.computeIfAbsent(name, key -> new LongAdder()).increment();
}
```

This fragment is suitable for keys with bounded cardinality; raw request IDs should not be used as permanent keys, as this easily causes memory growth. In real applications, a metrics system like Micrometer/Observation can reduce manual counter lifecycle management.

## 7. When State Must Outlive a Single Advice Invocation

### 7.1. `ThreadLocal` only isolates by thread

A `ThreadLocal<String>` can serve synchronous code deep inside the **same thread**, but it is not a request scope: thread pools reuse threads, nested proxy calls can overwrite the context, and executors do not automatically propagate values to other threads. If you must use it, save the previous value and restore/remove it in `finally`:

```java
String previous = operationContext.get();
operationContext.set(operationId);
try {
    return pjp.proceed();
} finally {
    if (previous == null) operationContext.remove();
    else operationContext.set(previous);
}
```

This is a fragment requiring `operationContext`, `operationId`, and `pjp`. When only measuring duration for a single `@Around`, a local `long started` is still simpler; the subsequent ThreadLocal lesson will test nesting, MDC, and thread reuse with tests.

### 7.2. A request-scoped dependency does not make the aspect per-request

A singleton aspect can use a request-scoped collaborator via a scoped proxy or provider in a web-aware context. The scope determines **how the target dependency is resolved**; the aspect instance itself does not change scope. Callbacks running when the request context is no longer active require separate handling, especially in background tasks. Do not change `@Aspect` to `@RequestScope` and assume all concurrency risks are gone.

### 7.3. Async/reactive completion differs from method return

A regular `@Around` finishes after `pjp.proceed()`. If the target returns an incomplete `CompletableFuture` or an unsubscribed `Mono`, the duration only measures the synchronous boundary. To record completion time, attach measurement to the completion callback or reactive subscription/terminal operator, with separate state and a clear lifecycle. The subsequent `@Async` and Reactor lessons analyze how context propagates across threads and subscriptions.

## 8. Runnable Example: One Singleton Aspect Handling Two Concurrent Invocations

The following project uses **Java 17, Maven, and Spring Framework 6.2.x** (no Spring Boot required). It intentionally avoids logging inside the two worker threads so stdout **has a deterministic order**. The two calls are still proven to **truly overlap** via a `CountDownLatch` in the target.

Observation goals:

1. Two `getBean(MonitorAspect.class)` calls in the same context return the same instance.
2. The consumer receives a Spring AOP proxy via `WorkerPort`.
3. Two threads can enter the **same advice method** in parallel; `peak=2` confirms the overlap.
4. Per-invocation data `id` lives in a local variable, not in a field.
5. The `AtomicInteger` counter is safe during increment/decrement; after both calls, `activeAfter=0`.
6. Results from the two requests are not mixed up: after sorting, `[done-A, done-B]`.

### 8.1. Directory Structure

```text
spring-aop-concurrent-aspect/
├── pom.xml
└── src/main/java/demo/concurrent/
    ├── AppConfig.java
    ├── WorkerPort.java
    ├── WorkerService.java
    ├── MonitorAspect.java
    └── Main.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-concurrent-aspect</artifactId>
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

### 8.3. `AppConfig.java`

```java
package demo.concurrent;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

Spring component scan registers the service and the aspect. With `WorkerService implements WorkerPort` and `proxyTargetClass=false`, plain Spring Framework prefers a **JDK dynamic proxy** for the service.

### 8.4. `WorkerPort.java`

```java
package demo.concurrent;

public interface WorkerPort {
    String process(String id);
}
```

The consumer only needs the interface. The JDK proxy implements this interface; do not cast it to the concrete target service.

### 8.5. `WorkerService.java`

```java
package demo.concurrent;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class WorkerService implements WorkerPort {
    private final CountDownLatch bothEntered = new CountDownLatch(2);

    @Override
    public String process(String id) {
        bothEntered.countDown();

        try {
            if (!bothEntered.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Expected two concurrent calls");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Worker interrupted", ex);
        }

        return "done-" + id;
    }
}
```

`CountDownLatch(2)` holds the first call inside the target until the second call also enters. Therefore, it does not rely on how the scheduler prints interleaved logs to **prove two invocations ran concurrently**.

The target only serves this demo for exactly **two invocations within one context**; the latch does not auto-reset and would not represent every request pair in a real application. Using `synchronized` on the target would cause the example to deadlock/timeout; that is also why you do not lock the entire call just to collect metrics.

### 8.6. `MonitorAspect.java`

```java
package demo.concurrent;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class MonitorAspect {
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();
    private final LongAdder elapsedNanos = new LongAdder();

    @Around("execution(* demo.concurrent.WorkerService.process(..))")
    public Object monitor(ProceedingJoinPoint pjp) throws Throwable {
        String id = (String) pjp.getArgs()[0]; // Separate per invocation.
        long started = System.nanoTime();       // Separate per invocation.

        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);

        try {
            Object result = pjp.proceed();

            if (!("done-" + id).equals(result)) {
                throw new IllegalStateException("Mismatched result for " + id);
            }
            return result;
        } finally {
            elapsedNanos.add(System.nanoTime() - started);
            active.decrementAndGet();
        }
    }

    public int active() {
        return active.get();
    }

    public int peak() {
        return peak.get();
    }

    public long elapsedNanos() {
        return elapsedNanos.sum();
    }
}
```

Key points:

- The aspect has three **shared fields**, but they belong to the thread-safe aggregate/metrics group; it does not store `id` or `started` in a field.
- Each advice execution calls `proceed()` exactly **once**.
- `id` and `started` are local, so two threads do not overwrite each other's data.
- `finally` brings `active` back to 0 when both invocations complete, even if one invocation throws an exception.
- `peak.accumulateAndGet(now, Math::max)` maintains the max concurrent count atomically.
- `elapsedNanos.sum()` can be used for aggregate timing, though the demo does not print the duration because nanoseconds depend on the machine and scheduling.
- The `"done-" + id` validation is only to prove **per-invocation identity**; in a production logging aspect, do not hardcode the target result contract like this.

### 8.7. `Main.java`

```java
package demo.concurrent;

import java.util.List;
import java.util.concurrent.Executors;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            WorkerPort port = context.getBean(WorkerPort.class);
            MonitorAspect aspect = context.getBean(MonitorAspect.class);

            System.out.println("singletonAspect="
                    + (aspect == context.getBean(MonitorAspect.class)));
            System.out.println("jdkProxy="
                    + AopUtils.isJdkDynamicProxy(port));

            var pool = Executors.newFixedThreadPool(2);
            try {
                var a = pool.submit(() -> port.process("A"));
                var b = pool.submit(() -> port.process("B"));

                List<String> results = List.of(a.get(), b.get())
                        .stream().sorted().toList();

                System.out.println("results=" + results);
                System.out.println("peak=" + aspect.peak());
                System.out.println("activeAfter=" + aspect.active());
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
```

Run from the directory containing `pom.xml`; the machine needs JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.concurrent.Main
```

**Expected stdout if both worker threads run within the 10-second timeout** (excluding separate Maven/Spring logs):

```text
singletonAspect=true
jdkProxy=true
results=[done-A, done-B]
peak=2
activeAfter=0
```

This example is **deterministic in print order** because only the main thread prints; the workers execute in parallel without printing to stdout. If the environment is extremely slow, the 10-second deadline could cause `CountDownLatch.await(...)` to time out and the program to fail instead of producing the stdout above. That is an environmental constraint of the demo, not normal Spring AOP behavior.

### 8.8. Explaining why `peak=2`

1. Main retrieves the `WorkerPort` bean through the context, so the calls go through the AOP proxy. The aspect is registered as a Spring singleton.
2. Thread A enters `MonitorAspect.monitor(...)`, increments `active` to 1, then proceeds to `WorkerService.process("A")` and waits on the latch.
3. Thread B enters the **same MonitorAspect instance**, increments `active` to 2, updates `peak` to 2, and then proceeds to the target.
4. Both target invocations meet at the latch and both can return; there is no sequential locking inside the aspect.
5. Each around advice invocation keeps `id`/`started` in local variables, preserving the corresponding results A and B.
6. Both advice invocations exit `finally` and decrement the counter. When Main calls `Future.get()` successfully for both, `activeAfter=0`.
7. Task completion order is nondeterministic, but the results are sorted so `[done-A, done-B]` is printed consistently.

**Verification contrast:** if `synchronized` is added to the `monitor(...)` method, thread A may hold the lock and wait for B at the latch, while B cannot enter the advice to reach the target; the result is a timeout. This is why local state and thread-safe metrics are used instead of serializing the entire business execution.

## 9. Advanced Aspect Instantiation Models Do Not Mean Per-Invocation

Spring's documentation for `@AspectJ` style also mentions several instantiation models other than singleton:

| Model in Spring @AspectJ | General meaning | Guarantees one instance per invocation? |
| --- | --- | --- |
| Default singleton | One aspect instance reused within the context | **No** |
| `perthis(...)` | Associates an aspect instance with a matching proxy object per expression | **No** — multiple invocations on the same proxy can share it |
| `pertarget(...)` | Associates an aspect instance with a matching target object | **No** — a target can serve multiple concurrent invocations |
| `pertypewithin(...)` | Associates an aspect instance with a matching type | **No** — not per-call |
| `percflow(...)` / `percflowbelow(...)` | Not supported by Spring AOP proxies according to docs | Do not use as a concurrency fix |

These models are **advanced topics**; they are not the primary solution for per-invocation state. Do not mistakenly claim that Spring AOP only supports singleton with no per-object models at all — the official documentation confirms `perthis`, `pertarget`, and `pertypewithin` are supported in @AspectJ configuration.

Fragment example:

```java
@Aspect("pertarget(execution(* demo.concurrent.WorkerService.process(..)))")
public class TargetScopedAspect {
    // State is still shared across calls on the same target.
}
```

This only illustrates syntax; do **not** put it into the runnable program in section 8. With `pertarget`, aspect instance creation is based on target identity when the pointcut matches, and it does not automatically isolate per-thread/per-request data. Before using these advanced models, check the Spring version, aspect registration configuration, and integration tests.

**Important note:** Spring bean scope `@Scope("prototype")` and AspectJ-style per-clause instantiation **are not the same model**. Do not change a bean scope annotation and deduce that an advice method instance is created for each invocation.

## 10. Common Pitfalls and How to Fix Them

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Request A's log shows request B's ID | Singleton field `currentId` overwritten | Use a local variable in `@Around`, or a clearly designed context |
| Start time/duration mixed between two calls | Storing `startedAt` in an aspect instance field | Place `long started` in the advice local frame |
| Counter lower than actual call count | Non-atomic `count++` | Use `AtomicInteger`/`LongAdder`/metrics registry |
| Adding `volatile` still gives wrong request | Visibility does not create per-invocation isolation | Do not store request context in a shared field |
| `synchronized @Before`/`@After` still mismatches data | Lock only wraps each advice method, not across an invocation | Redesign to local state/around |
| `synchronized @Around` bottlenecks the service | Serializes the entire chain/target | Do not lock if only measuring/logging; use a thread-safe aggregator |
| `ThreadLocal` retains data from previous request | Worker thread pool reuses threads, forgot `remove()` | Cleanup/restore in finally; prefer explicit context |
| Nested advice clears outer ThreadLocal | Inner call runs `remove()` after overwriting old value | Save old, restore in finally or use an appropriate context API |
| `@Async` does not see ThreadLocal | Task switches threads, does not auto-propagate | Task decoration/context propagation depending on Spring module |
| `@Around` elapsed lower than async processing | Method returns future/publisher early | Measure completion using async/reactive API |
| Singleton aspect injects singleton mutable service and hits race | Collaborator is not thread-safe | Fix state ownership/concurrency in the collaborator |
| Using `@Order` to guarantee two threads don't interleave | `@Order` only sets precedence in one interceptor chain | Choose appropriate concurrency control |
| `perthis` still has races | Multiple threads call the same proxy | Use local state or purposeful atomics/locks |
| `pertarget` still has races | Multiple threads call the same target instance | Do not treat per-target as per-thread/per-request |
| Object created with `new` has no advice | No Spring proxy | Use a Spring-managed dependency |
| `this.process()` skips advice | Self-invocation bypasses Spring proxy | Extract the operation to another Spring bean if advice is needed |
| Aspect has no effect | `@Aspect` not registered as a bean or auto-proxy not enabled | `@Component`/`@Bean` and `@EnableAspectJAutoProxy`/Boot AOP |
| JDK proxy does not expose implementation-only method | Interface surface is limited | Use a public interface method or configure CGLIB thoughtfully |
| CGLIB does not intercept `final`/`private` methods | Cannot be overridden | Adjust method/bean boundary appropriately |
| Multiple ApplicationContexts have multiple singleton aspects | Singleton is per-container/bean | Check context ownership and actual configuration |

## 11. Checklist for Designing Safe Singleton Spring Aspects

1. **Identify the actual scope:** which context the aspect is a Spring bean in, and whether it uses any special per-clause instantiation model.
2. **Check target and proxy:** is the target Spring-managed, does the pointcut match, and do callers go through the proxy?
3. **List all aspect fields:** immutable config, collaborator references, shared aggregate state, or per-invocation data?
4. **Move per-invocation state into local variables** of the advice; use `@Around` when you need to connect before/after `proceed()`.
5. **Shared aggregates must be thread-safe:** atomics/LongAdder or a metrics library; consider snapshot consistency and cardinality.
6. **Do not overuse `volatile`/`synchronized`:** they solve visibility/mutual exclusion, not request identity.
7. **Do not store `JoinPoint` or `ProceedingJoinPoint` in singleton fields** for later reuse; these belong to the current invocation's state.
8. **Check collaborator thread safety:** a `final` dependency reference does not make mutable internals inside the collaborator safe.
9. **Check ThreadLocal lifecycle:** cleanup, nested calls, async hops, executor reuse, and context propagation.
10. **Preserve outcomes:** the advice calls `proceed()` as needed, preserves the return value, and propagates exceptions properly.
11. **Test real concurrency:** use latches/barriers to force overlap and verify races/correctness, rather than guessing from one lucky log run.
12. **When transactions/cache/security/async are involved:** check advisor ordering and execution boundaries; do not treat a singleton aspect as a global lock.

### Useful Test Cases

| Test | Expectation |
| --- | --- |
| Look up `getBean(Aspect.class)` twice in the same context | Same reference if default singleton |
| Two threads call the same Spring proxy concurrently | Advice runs concurrently unless explicitly serialized |
| Requests A/B have different arguments | Local request data preserves A/B accurately |
| Atomics counting active/peak | No lost increments, peak reflects overlap |
| Shared field `currentId` | Can fail under interleaving; do not use in production |
| Method calls `this.inner()` | No new interception for self-invocation |
| Object created via `new` | Not advised by Spring AOP |
| Error from target | `finally` cleans up metrics properly, exception still propagates |
| Call returning a future | Do not interpret synchronous elapsed as full async duration |
| Multiple contexts | Do not assume a single JVM-wide singleton aspect |

## 12. Review Questions

**1. Does a Spring `@Aspect @Component` singleton mean advice runs only once?** No. One aspect instance serves many matched invocations; multiple threads can enter the advice simultaneously.

**2. Why is storing `currentRequestId` in a field dangerous?** Two concurrent calls overwrite shared state, causing after advice to read data from another invocation.

**3. Can `volatile` fix the "request A reads B's ID" race?** No. It provides visibility, not per-invocation data isolation.

**4. Why is `@Around` local `started` safer than a field `started`?** Local variables belong to each invocation's stack frame; when `proceed()` returns, the same frame receives the corresponding result and duration.

**5. When should an aspect have mutable fields?** When it is genuine shared state such as aggregate metrics and is protected by appropriate concurrency primitives/structures.

**6. Does `@Order(1)` guarantee Thread B waits for Thread A to finish?** No. It adjusts advisor precedence within a single invocation chain, not as a mutex across requests.

**7. Why does `ThreadLocal` need `remove()` or restore?** Thread pools reuse threads and nested calls can overwrite context; cleanup prevents data leaks and cross-request contamination.

**8. Does `perthis` or `pertarget` mean one aspect instance per call?** No. They associate an aspect instance with a proxy/target object, and one object can have many concurrent calls.

**9. Has an `@Around` timer around `proceed()` finished measuring a CompletableFuture?** Not necessarily; the future may complete after the synchronous method invocation returns.

**10. Is Spring singleton scope strictly one aspect instance in the entire JVM?** No; it is typically per bean definition/per ApplicationContext, unlike a GoF static singleton.

## Official Spring Framework Documentation

- [Spring Framework 6.2 — Aspect Instantiation Models: singleton, perthis, pertarget, pertypewithin](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/instantiation-models.html)
- [Spring Framework — Bean Scopes: container-level singleton](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework — Declaring Advice: Around Advice and local state for timing](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework — Bean Initialization / thread-safe publication and mutable runtime fields](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Proxying Mechanisms: JDK/CGLIB and self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — @AspectJ support and aspect beans](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
