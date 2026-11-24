# Risks of Storing JoinPoint, Current User, or Start Time in a Spring Aspect Field

## 1. A Data Error Worse Than Timing Skew

When an audit aspect stores a `ProceedingJoinPoint`, current actor, or start timestamp in mutable instance fields, request A can **record request B's username or arguments** even though A's business result is still correct. In Spring AOP, an `@Aspect` is a Spring bean that typically has a single singleton instance in the context; those fields do not represent any individual invocation.

```java
@Aspect
public class UnsafeAuditAspect {
    private ProceedingJoinPoint currentJoinPoint;
    private String currentActor;

    @Around("execution(* com.example..service.*.*(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        currentJoinPoint = pjp;
        currentActor = currentActorId(); // hypothetical helper
        try {
            return pjp.proceed();
        } finally {
            auditSink.write(currentActor, currentJoinPoint); // hypothetical helper
        }
    }
}
```

This is an **illustrative anti-pattern**, not a standalone runnable example. The mistake can also retain sensitive data in memory for too long, especially when storing the whole `JoinPoint`/arguments/target. This lesson focuses on **`JoinPoint` lifetime boundaries, controlled identity snapshots, and cross-request audit risks**; the preceding local-variables lesson explains stack frames and timers in general.

## 2. What Is Allowed to Outlive the Invocation?

| Value | Proper usage | Risk when stored on a singleton aspect |
| --- | --- | --- |
| `ProceedingJoinPoint` | Read signature/args and call `proceed()` within the current advice | Invocation mix-up, retaining references to target/proxy/arguments |
| Actor from `SecurityContextHolder` | Capture an **audit-approved ID** into a local | Retaining security principal or token across requests |
| Start time | Local `long started = System.nanoTime()` to measure elapsed | Request B's timestamp overwrites A's |
| `Throwable`/result | Handle in the invocation's `catch/finally` | Leaking another request's error/result |
| `AuditSink` or `MeterRegistry` | Inject dependency with clear concurrency and retention contracts | The sink itself could still be non-thread-safe |

Do not treat `JoinPoint` as a background command that can arbitrarily call `proceed()` after the advice ends. If information must be passed to a queue or audit storage, extract an allowed scalar snapshot and pass it to a thread-safe sink; `pjp.getArgs().clone()` only creates a shallow copy and does not freeze the object graph.

## 3. Timeline Proving Identity Mix-Up

```text
T1 (Alice): currentActor = "alice"; currentJoinPoint = jpAlice
T1 (Alice): enters target and waits on I/O
T2 (Bob):   currentActor = "bob";   currentJoinPoint = jpBob
T1 (Alice): target returns; finally reads actor "bob" and jpBob
```

This is a valid interleaving schedule, sufficient to prove that shared fields **cannot express the identity of a single invocation**. `volatile` or `AtomicReference` can improve visibility or atomic reference operations, yet still hold only the most recently updated invocation's data. Locking individual assignments does not protect the lifetime of the target call. Locking the entire `@Around` serializes business logic and does not handle async callbacks, multiple contexts, or proxy-bypassed advice.

The demo in section 7 creates the Alice/Bob timeline with `CountDownLatch`, then compares `unsafe(alice)=bob` against the local snapshot `safe(alice)=alice`. You do not need to log real credentials or user data to test this phenomenon.

## 4. Keeping `ProceedingJoinPoint` in a Field Also Carries Lifecycle and Security Risks

`ProceedingJoinPoint` lets you read the signature, arguments, proxy, and target, and forward the invocation via `proceed()`. It is bound to the **currently advised call**.

```java
@Aspect
public class BadJoinPointCache {
    private ProceedingJoinPoint saved;

    @Around("execution(* com.example..service.*.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        saved = pjp;         // Wrong: stores invocation in a shared field.
        return pjp.proceed();
    }
}
```

This is a counterexample fragment. Three problems:

1. **Wrong invocation:** another request overwrites `saved`; callbacks/logs read the wrong method name, target, or arguments.
2. **Retaining the object graph too long:** the join point can reference arguments, proxy, target, and the invocation chain; holding it too long can retain PII, credentials, mutable DTOs, and memory.
3. **Misusing `proceed()`:** do not store `pjp` so another thread or event callback can call `saved.proceed()` after the advice has returned. `pjp` is not a general-purpose background command; it carries the invocation context/interceptor chain of the call moment.

Rather, extract minimal metadata in local scope:

```java
final String methodName = pjp.getSignature().getName();
final String actorId = actorProvider.currentActorId();
final long startedNanos = System.nanoTime();
```

This is a **fragment** requiring `actorProvider`. Afterward, send only `methodName`, the permitted `actorId`, and elapsed duration to the audit/metrics sink. Do not retain the raw `pjp` or the entire `Object[] args` longer than needed.

### Copying the arguments array is not copying all the data

```java
Object[] arguments = pjp.getArgs().clone();
```

This operation only **shallow-copies** the array; if an element is a mutable object, its contents can continue changing. You should not log the entire argument graph or store unbounded arrays. If an immutable snapshot is needed for auditing, define a DTO recording **permitted scalar fields** with a clear redaction policy.

## 5. Safe Design: Local Variables Inside `@Around`

```java
@Around("execution(public * com.example..service.*.*(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    final String method = pjp.getSignature().getName();
    final String actor = actorProvider.currentActorId();
    final long startedNanos = System.nanoTime();
    String outcome = "SUCCESS";

    try {
        return pjp.proceed();
    } catch (Throwable error) {
        outcome = "FAILURE";
        throw error;
    } finally {
        long elapsed = System.nanoTime() - startedNanos;
        auditRecorder.record(actor, method, outcome, elapsed);
    }
}
```

This is a **production-style fragment**, not a standalone program because it requires injected `actorProvider` and `auditRecorder`. What is right:

- `actor` and `startedNanos` belong to the stack frame of the **current invocation**.
- `pjp` is used within the executing advice scope and not copied to a singleton field.
- `auditRecorder` can be a shared dependency, provided its implementation handles concurrency and manages data retention.
- `finally` observes both normal returns and synchronous exceptions.
- Rethrowing the original error preserves method exception semantics; do not accidentally swallow `Throwable`.

**Note:** If `auditRecorder.record(...)` itself throws an exception in `finally`, it can mask the original exception. A clear telemetry failure policy is needed—for instance, handling logging sink failures in a controlled way so they do not break business operations, if system requirements permit.

### `System.nanoTime()` is right for elapsed duration

Use `System.nanoTime()` to measure elapsed intervals within the same JVM; do not use it as an epoch timestamp. `System.currentTimeMillis()` or `Instant.now()` is appropriate for recording historical timestamps, whereas wall clocks can be adjusted and are not ideal for short latency measurements.

Avoid `private long startNanos` on a singleton aspect. If A and B overlap, `now - startNanos` can belong to B and fail to reflect A's duration.

**If the target returns a Future/Publisher:** the time from before to after `pjp.proceed()` measures **when the Java method returns the handle/publisher**, not automatically Future completion or reactive terminal signals. To measure completion, attach callbacks/Publisher operators using **local snapshot data**, without retaining `ProceedingJoinPoint` for asynchronous use.

## 6. Getting the Current User in Spring: Read Once, Snapshot Locally

In a Spring Security servlet stack, an application might read:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

String actorId =
        authentication == null ? "anonymous" : authentication.getName();
```

This is a Spring Security fragment; it requires imports for `Authentication` and `SecurityContextHolder`. The default strategy typically uses a thread-bound security context, though applications can configure it differently. Do not assume the current principal can always be read from an arbitrary thread.

Do not do:

```java
private Authentication currentAuth;

@Before("serviceOperation()")
public void capture() {
    currentAuth = SecurityContextHolder.getContext().getAuthentication();
}

@AfterReturning("serviceOperation()")
public void log() {
    // currentAuth may belong to a different call.
}
```

This is an **anti-pattern**. `@Before` and `@AfterReturning` are two separate advice invocations; a shared field is not a reliable per-request channel. Even when identity does not change within one request, requests can interleave.

Instead, snapshot the **audit-permitted actor ID** into a local variable of **a single `@Around`**, then pass it to the audit sink. Do not retain `Authentication` or raw principals/tokens unless truly required.

### Users do not come only from HTTP requests

A Spring Aspect can be triggered by scheduled jobs, message listeners, batch executors, integration tests, or CLI runners. Those calls may have no servlet request or authenticated user. `actorProvider` needs an explicit fallback such as `system-job`/`anonymous` depending on policy, instead of implicitly assuming `SecurityContextHolder.getContext().getAuthentication()` is always non-null.

In multi-tenant systems, do not use a `currentTenant` field on an aspect as a policy source of truth. A tenant A request tagged with tenant B's ID can turn an observability issue into a serious data isolation failure.

## 7. Runnable Java 17+ Demo: Two Concurrent Calls, Deterministic Output

This demo proves field-sharing corruption on **one Spring singleton aspect**, without relying on random races.

Steps:

1. Thread Alice calls `service.process("alice")` through the Spring proxy; the aspect writes `alice` fields and the target waits at a gate.
2. Main confirms Alice has reached the target.
3. Thread Bob calls `service.process("bob")` through the **same proxy**; the aspect overwrites the fields with `bob`, and the target waits.
4. Main confirms Bob has reached the target before opening the gate.
5. Both calls finish; main prints **after awaiting both `Future.get()` calls**, so output order is deterministic.

The aspect saves both an **unsafe** snapshot (read from shared fields) and a **safe** snapshot (read from local variables) into a `ConcurrentHashMap` strictly for comparison. This is an educational example, **not a recommendation** to store raw request data in an aspect map in production.

Pinned environment: **JDK 17+, Spring Framework 6.1.14, AspectJ Weaver 1.9.22.1, Maven**. These are illustrative versions, not claimed to be the latest.

### 7.1. Project Structure

```text
spring-aop-invocation-scope/
├── pom.xml
└── src/main/java/com/example/scope/
    ├── GatedService.java
    ├── SnapshotAspect.java
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
    <artifactId>spring-aop-invocation-scope</artifactId>
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

`spring-context` provides the Spring application context and Spring AOP dependencies transitively; `aspectjweaver` supports parsing/matching `@AspectJ` expressions. No web server or AspectJ weaving agent is required.

### 7.3. `src/main/java/com/example/scope/GatedService.java`

```java
package com.example.scope;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class GatedService {
    private final CountDownLatch aliceEntered = new CountDownLatch(1);
    private final CountDownLatch bobEntered = new CountDownLatch(1);
    private final CountDownLatch releaseGate = new CountDownLatch(1);

    public String process(String user) {
        if ("alice".equals(user)) {
            aliceEntered.countDown();
        } else if ("bob".equals(user)) {
            bobEntered.countDown();
        } else {
            throw new IllegalArgumentException("Unknown demo user");
        }

        try {
            releaseGate.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }

        return "ok:" + user;
    }

    public void awaitAlice() throws InterruptedException {
        if (!aliceEntered.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout waiting for alice");
        }
    }

    public void awaitBob() throws InterruptedException {
        if (!bobEntered.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout waiting for bob");
        }
    }

    public void release() {
        releaseGate.countDown();
    }
}
```

`CountDownLatch` enforces the sequence **Alice enters target first, Bob enters target second, then both are allowed to leave the target**. The control methods `awaitAlice`/`awaitBob`/`release` do not match the pointcut, so they do not overwrite aspect fields.

### 7.4. `src/main/java/com/example/scope/SnapshotAspect.java`

```java
package com.example.scope;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class SnapshotAspect {
    // INTENTIONALLY WRONG: per-invocation state in singleton fields.
    private volatile String sharedUser;
    private volatile ProceedingJoinPoint sharedJoinPoint;
    private volatile long sharedStartNanos;

    // Used only in DEMO for thread-safe snapshot recording.
    private final ConcurrentMap<String, String> unsafe =
            new ConcurrentHashMap<>();
    private final ConcurrentMap<String, String> safe =
            new ConcurrentHashMap<>();

    @Around(
        value = "execution(public java.lang.String "
              + "com.example.scope.GatedService.process(..))"
              + " && args(user)",
        argNames = "user"
    )
    public Object around(ProceedingJoinPoint pjp, String user)
            throws Throwable {
        // RIGHT: each invocation has its own local snapshot.
        final String localUser = user;
        final ProceedingJoinPoint localJoinPoint = pjp;
        final long localStarted = System.nanoTime();

        // WRONG: each call overwrites the shared slot.
        sharedUser = user;
        sharedJoinPoint = pjp;
        sharedStartNanos = localStarted;

        try {
            return pjp.proceed();
        } finally {
            unsafe.put(user,
                    "fieldUser=" + sharedUser
                    + ", fieldJoinArg=" + sharedJoinPoint.getArgs()[0]);

            safe.put(user,
                    "localUser=" + localUser
                    + ", localJoinArg=" + localJoinPoint.getArgs()[0]);

            // Measure timing with localStarted, NOT sharedStartNanos.
            long elapsed = System.nanoTime() - localStarted;
            // elapsed is intentionally not printed to keep stdout deterministic.
        }
    }

    public String unsafeFor(String user) {
        return unsafe.get(user);
    }

    public String safeFor(String user) {
        return safe.get(user);
    }
}
```

The `sharedUser`/`sharedJoinPoint`/`sharedStartNanos` fields are written **intentionally wrong** to demonstrate the race; `volatile` lets threads see updates but provides no isolation. When Bob enters the target, the shared fields end up holding Bob's values. The gate opens only **after** that event, so at the end both invocations read Bob's fields.

`localUser`, `localJoinPoint`, and `localStarted` remain private to the executing call. `ConcurrentHashMap` only lets main print snapshots after completion without introducing another data race in the test; do not copy it into unbounded production storage of user data.

### 7.5. `src/main/java/com/example/scope/AppConfig.java`

```java
package com.example.scope;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public GatedService gatedService() {
        return new GatedService();
    }

    @Bean
    public SnapshotAspect snapshotAspect() {
        return new SnapshotAspect();
    }
}
```

`@EnableAspectJAutoProxy(proxyTargetClass=true)` enables Spring proxy-based AOP; a CGLIB class proxy is used because `GatedService` does not implement an interface. `SnapshotAspect` is registered as a Spring bean with `@Bean`; `@Aspect` alone does not register a bean.

### 7.6. `src/main/java/com/example/scope/DemoApp.java`

```java
package com.example.scope;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            GatedService service = context.getBean(GatedService.class);
            SnapshotAspect aspect = context.getBean(SnapshotAspect.class);
            System.out.println("isAopProxy=" + AopUtils.isAopProxy(service));

            ExecutorService executor = Executors.newFixedThreadPool(2);
            try {
                Future<String> alice =
                        executor.submit(() -> service.process("alice"));
                service.awaitAlice();

                Future<String> bob =
                        executor.submit(() -> service.process("bob"));
                service.awaitBob();
                service.release();

                String aliceResult = alice.get(10, TimeUnit.SECONDS);
                String bobResult = bob.get(10, TimeUnit.SECONDS);

                System.out.println("resultAlice=" + aliceResult);
                System.out.println("resultBob=" + bobResult);
                System.out.println("unsafe(alice)=" + aspect.unsafeFor("alice"));
                System.out.println("unsafe(bob)=" + aspect.unsafeFor("bob"));
                System.out.println("safe(alice)=" + aspect.safeFor("alice"));
                System.out.println("safe(bob)=" + aspect.safeFor("bob"));
            } finally {
                service.release();
                executor.shutdownNow();
            }
        }
    }
}
```

Both threads call the **same Spring-managed proxy**. Main waits for future results before printing, so whichever worker A/B finishes first does not change the **order of stdout lines printed by main**. If a timeout occurs on an overly slow environment, the example fails with an error instead of producing a false conclusion.

### 7.7. Running and Expected Stdout

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.scope.DemoApp
```

Without a timeout, the lines produced by the code are:

```text
isAopProxy=true
resultAlice=ok:alice
resultBob=ok:bob
unsafe(alice)=fieldUser=bob, fieldJoinArg=bob
unsafe(bob)=fieldUser=bob, fieldJoinArg=bob
safe(alice)=localUser=alice, localJoinArg=alice
safe(bob)=localUser=bob, localJoinArg=bob
```

Interpretation:

1. Spring returns an AOP proxy for `GatedService`, not a raw object instantiated by the caller with `new`.
2. Alice enters the advice, assigns shared fields, then waits inside the target.
3. Bob enters the **same singleton aspect**, overwrites fields with Bob's data, and also waits.
4. Main opens the gate; Alice's and Bob's targets may exit in either order depending on the scheduler, yet both return the correct business result.
5. Both unsafe snapshots see the **same last slot** containing Bob, so Alice gets assigned the wrong identity and join point.
6. Both safe snapshots use **local variables**, so each call records the right identity.

This is an intentional example demonstrating **cross-invocation data contamination**, not a recommendation to log or store real user IDs in a map in production. Code and stdout have been statically reviewed; Maven has not been run on the target machine.

## 8. Production-Style Organization

A production aspect should hold **shared-safe dependencies**, not mutable current-invocation fields:

```java
@Aspect
public class SafeAuditAspect {
    private final ActorProvider actors;
    private final AuditSink sink;

    public SafeAuditAspect(ActorProvider actors, AuditSink sink) {
        this.actors = actors;
        this.sink = sink;
    }

    @Around("execution(public * com.example..service.*.*(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        final String actorId = actors.currentActorId();
        final String method = pjp.getSignature().getName();
        final long started = System.nanoTime();
        String outcome = "SUCCESS";

        try {
            return pjp.proceed();
        } catch (Throwable ex) {
            outcome = "FAILURE";
            throw ex;
        } finally {
            long duration = System.nanoTime() - started;
            sink.write(actorId, method, outcome, duration);
        }
    }
}
```

This is a fragment requiring `ActorProvider` and `AuditSink` interfaces. A thread-safe `AuditSink` can record independent events; do not store "current actor" in a field of the aspect itself. `actorId` should be a permitted identifier, redacted/normalized according to policy.

If `sink.write` risks throwing an exception, decide on a handling policy so logging/telemetry errors do not mask business errors unless required. If the operation returns a Future/Publisher, measure **method return** and **asynchronous completion** separately.

### Which fields make sense?

| Aspect field | Assessment |
| --- | --- |
| `private final AuditSink sink` | Valid if the implementation handles concurrency safely |
| `private final MeterRegistry registry` | Appropriate per library contract |
| `private final String serviceName` | Immutable config |
| `private final AtomicLong totalCalls` | Valid if intentionally counting total calls |
| `private String currentUser` | Wrong for a singleton aspect across multiple invocations |
| `private ProceedingJoinPoint lastJoinPoint` | Wrong if used as current invocation state or retained long-term |
| `private long startTime` | Wrong as a timestamp for the current invocation |
| `private Throwable lastException` | Easily mixes exceptions across requests |
| `private Map<String, Object> requests` without cleanup | Retention, PII, and memory growth risk |

Distinguish **shared aggregate state** (such as counters) from **shared per-request state** (wrong). A thread-safe counter can use `LongAdder` or a Micrometer registry, but never use a counter-like field to store user or start time.

## 9. ThreadLocal Is Not a Universal Fix

`ThreadLocal` has one slot **per thread**, not per Spring AOP invocation:

```java
private static final ThreadLocal<Long> STARTED = new ThreadLocal<>();

@Before("serviceOperation()")
public void before() {
    STARTED.set(System.nanoTime());
}

@After("serviceOperation()")
public void after() {
    long elapsed = System.nanoTime() - STARTED.get();
    STARTED.remove();
}
```

This is a **risky fragment**, requiring a named pointcut. Problems:

- **Thread pool reuse:** forgetting `remove()` causes another request on the same worker thread to see stale data.
- **Nested proxy calls:** the same thread enters outer advice then inner advice; inner's `STARTED.set` **overwrites** outer's start time before outer finishes.
- **Async callbacks:** Future completion may run on another thread that cannot see the caller's ThreadLocal.
- **Reactive Reactor:** can switch schedulers/threads and have multiple subscriptions; requires `Reactor Context`/appropriate framework context propagation.
- **Exceptions:** must clean up in `finally`, not relying on normal return.
- **Ordering/matching:** two separate advice methods may not run symmetrically in every configuration; do not stitch lifecycle via ThreadLocal when an `@Around` local is simpler.

`InheritableThreadLocal` also does not safely propagate into pre-created worker pools. If ThreadLocal is mandatory to interact with a legacy API, design **stack push/pop**, cleanup in `finally`, and handle nested invocations and thread hops. For start time/actor within **a single `@Around`**, local variables are far less error-prone.

### MDC: restoring the previous context

If an aspect attaches an operation ID to MDC, save the previous value in a local and restore it:

```java
String previous = MDC.get("operationId");
try {
    MDC.put("operationId", safeOperationId);
    return pjp.proceed();
} finally {
    if (previous == null) {
        MDC.remove("operationId");
    } else {
        MDC.put("operationId", previous);
    }
}
```

This is a fragment requiring SLF4J `MDC`, `pjp`, and `safeOperationId`. Restoring helps nested calls, yet does not automatically solve propagation across other threads. Do not keep raw security context/principals in a singleton aspect field.

## 10. Even a Single Thread Can Overwrite a Field: Reentrancy

```text
Thread 1:
  around(OuterService.run)  -> sharedStart = t1
     target outer
        -> calls InnerService through Spring proxy
           around(InnerService.work) -> sharedStart = t2
           target inner
           inner finally reads t2
     outer finally reads sharedStart=t2  <-- wrong, should be t1
```

Without multithreading, **nested advice invocations on the same thread** can also overwrite a singleton field. A single `ThreadLocal<Long>` is likewise overwritten in nested calls.

**Right:** local `long started = System.nanoTime()` in **each** `@Around` invocation.

Note the Spring AOP proxy boundary: if the target calls `this.otherMethod()`, that is the familiar proxy-bypassing self-invocation and does not create a new advisor invocation. Yet that does not make field state safe, because nested **cross-bean calls through Spring proxies** still happen.

## 11. Is Changing Aspect Instantiation Enough to Protect Auditing?

`perthis` and `pertarget` can bind an aspect instance to a corresponding proxy/target under supported Spring configuration, yet **two calls to the same proxy/target can still happen concurrently**. Prototype scope also does not promise creating a new aspect per method invocation. Therefore, do not replace a `currentActor` field with a field on a per-target aspect and assume auditing is isolated. Local snapshots and a sink with a clear concurrency contract remain the right solution here.

## 12. Future, @Async, and Reactive Publishers

A Spring service call may return:

- `CompletableFuture<T>` while a background task is still running.
- `Mono<T>` or `Flux<T>` before subscription, especially cold publishers.
- A handle from an already-completed task, depending on implementation.

If `@Around` only measures `System.nanoTime()` around `pjp.proceed()`, it measures **Java method invocation/assembly**, not automatically Future completion or Publisher terminal signals.

If completion must be measured:

```java
@Around("execution(* com.example.jobs.JobService.start(..))")
public Object monitor(ProceedingJoinPoint pjp) throws Throwable {
    final String methodName = pjp.getSignature().getName();
    final long started = System.nanoTime();

    CompletionStage<?> stage = (CompletionStage<?>) pjp.proceed();
    return stage.whenComplete((value, error) -> {
        long duration = System.nanoTime() - started;
        metrics.record(methodName, duration, error);
    });
}
```

This is a **fragment** for `CompletionStage` only and requires `metrics`, not for every raw `Future`. The callback captures only **methodName/start** (scalar local values), not the raw `pjp` to access after the original advice has returned.

With Reactor, `@Around` can return a publisher decorated with `doOnSubscribe`/`doOnError`/`doFinally`, noting that **one method return can have multiple subscriptions**. Do not call `subscribe()` inside the aspect just to log, as that can trigger work an extra time. Do not capture `ProceedingJoinPoint` in a long-lived lambda merely to read the method name; snapshot scalar metadata before returning.

Propagation of Spring Security context, Reactor `Context`, MDC, and tracing must also be evaluated when callbacks execute on other threads. Do not try to use a shared `currentUser` field to "pass context" to async workers.

## 13. Testing and Diagnostics

A reliable integration test for this topic should:

1. Enable Spring AOP, register the aspect as a Spring bean, and retrieve the target via `ApplicationContext`.
2. Use `AopUtils.isAopProxy(bean)` to verify the proxy is present, while still asserting the advice actually runs.
3. Call the **same proxy** from two threads with distinct inputs/actor IDs.
4. Use `CountDownLatch`/`CyclicBarrier` to create intentional overlap; do not rely on `Thread.sleep()` hoping a race shows up "occasionally".
5. Assert A's event keeps A's method/user/arguments, and likewise for B.
6. Test nested calls: service A proxy → service B proxy → same aspect on **one thread**.
7. Test exception paths so cleanup/timing is not skipped.
8. If using ThreadLocal/MDC, verify cleanup after requests and executor thread reuse.
9. For Future/Publisher, test that method return **differs** from async completion/reactive terminal signals.
10. Verify data retention: the audit sink does not retain `JoinPoint` or raw request payloads indefinitely.
11. If recording timing, assert reasonable durations rather than hardcoding an exact nanosecond number.
12. Ensure test output does not print real credentials/tokens or full user data.

**Do not confuse `AopUtils.isAopProxy(bean)` returning true with a specific aspect matching every method.** A bean may be proxied by another advisor; you must check the pointcut and events.

## 14. Common Pitfalls and How to Fix Them

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Alice's audit tagged with Bob | Shared `currentUser` singleton field | Snapshot actor into a local variable per advice call |
| Logs another request's args/method | Shared `ProceedingJoinPoint` field overwritten | Keep `pjp` local, extract only needed metadata |
| Duration too short/long or wrong | Shared `startedNanos` overwritten | Local `final long start` and elapsed in `finally` |
| Adding `volatile` still fails | Visibility does not create isolation | Remove per-call fields |
| Using `AtomicReference` still mixes calls | One shared slot holds "last invocation" | Pass scalar metadata explicitly |
| `synchronized` lock causes bottleneck | Serializes business calls | Keep locals, do not lock around `proceed()` |
| Aspect holds request references too long | Storing JoinPoint/args in a field/map | Do not retain raw requests; use a bounded/approved audit sink |
| ThreadLocal wrong on nested invocation | Single slot per thread is not a stack | `@Around` local or push/pop with cleanup if needed |
| Logs retain previous request data in pool | Forgot `ThreadLocal.remove()`/MDC cleanup | `finally` + restore previous state |
| Future metric recorded before job completion | Measured method return instead of completion | CompletionStage callbacks or reactive operators |
| Async callback misses user/MDC | Context switched threads | Framework context propagation/ID snapshot |
| Prototype/per-proxy aspect still races | Does not mean per invocation | Keep state only in advice locals |
| `@Before` writes start, `@After` reads wrong field | Two separate advice methods share singleton state | Use one `@Around` and locals |
| Advice does not run | Bean not Spring-managed, AOP disabled, self-invocation | Check context/proxy/invocation path |

## 15. Review Checklist

- [ ] No fields meaning invocation-level `currentUser`, `currentJoinPoint`, `currentRequest`, `startTime`.
- [ ] Shared dependencies are thread-safe by contract; configuration is immutable.
- [ ] `JoinPoint`/`ProceedingJoinPoint` are used in invocation scope, never cached long-term.
- [ ] Actor ID is snapshotted locally and is permitted audit data.
- [ ] Timing uses local `System.nanoTime()`, with `finally` for sync success/failure.
- [ ] Method-return timing and Future/Publisher completion are distinguished.
- [ ] `volatile`/`AtomicReference` are not used as substitutes for per-call isolation.
- [ ] If ThreadLocal/MDC is used, cleanup is proper and nested calls are supported.
- [ ] Do not assume perthis/pertarget/prototype means per request.
- [ ] Test two overlapping threads on the same Spring proxy with different actors.
- [ ] Test cross-bean nested invocation on a single thread.
- [ ] Do not retain raw requests/credentials/arguments in unbounded fields/maps.
- [ ] Spring bean registration, proxy boundaries, and pointcuts are all verified.

### Official Spring Framework Documentation

- **Aspect Instantiation Models** — default singleton, perthis, and pertarget: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html
- **Declaring Advice / Around Advice** — `ProceedingJoinPoint`, `proceed()`: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- **AOP Concepts** — Spring proxies and advice execution: https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- **Proxying Mechanisms** — JDK/CGLIB, self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Security concurrency support** — context propagation: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- **Spring scheduling and @Async**: https://docs.spring.io/spring-framework/reference/integration/scheduling.html

**Conclusion:** A singleton Spring `@Aspect` can handle multiple join points concurrently. Storing **`JoinPoint`, current user, or start timestamp in fields** easily causes races, identity mix-ups, wrong durations, and prolonged retention of sensitive data. Keep state in the **local scope of each advice invocation**, pass minimal metadata to a thread-safe sink, and use lifecycle-appropriate async/reactive context propagation.
