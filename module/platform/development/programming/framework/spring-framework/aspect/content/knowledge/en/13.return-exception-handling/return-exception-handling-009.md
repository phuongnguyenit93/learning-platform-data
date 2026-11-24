# Distinguishing Method Return of a Future/Publisher from Actual Work Completion in Spring Aspect

## 1. The problem: `@AfterReturning` has run, but is the work actually complete?

In **Spring AOP**, `@AfterReturning` runs when a **Java method call intercepted by a Spring proxy has returned normally**. If the return type is `Future<T>`, `CompletableFuture<T>`, `CompletionStage<T>`, `Mono<T>`, `Flux<T>`, or a `Publisher<T>`, the method can easily **return a handle/work descriptor** before the asynchronous result or reactive stream completes.

Example:

```java
@AfterReturning(
    pointcut = "execution(* com.example.jobs.JobService.start(..))",
    returning = "result",
    argNames = "result"
)
public void afterReturn(Object result) {
    System.out.println("Method returned: " + result.getClass().getName());
}
```

This is a **fragment inside a Spring `@Aspect` bean**, not a standalone Java program. That log line says the proxied call **`start(..)` had a normal return**. It **does not by itself prove** that:

- The `CompletableFuture` has completed.
- The Future succeeded rather than completing exceptionally or being cancelled.
- The `Mono`/`Flux` has been subscribed to.
- The Publisher has emitted `onNext`, `onComplete`, or `onError`.
- All data has been written to the HTTP client.
- The transaction, remote call, message processing, or entire external workflow has finished.

This is a fundamental difference between Spring Aspect's **method-execution lifecycle** and the return value's **asynchronous/reactive processing lifecycle**.

**Scope:** Focuses on `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around`, `ProceedingJoinPoint`, and observation order in **proxy-based Spring AOP**. Future/Reactive Streams concepts are used to explain Spring Aspect behavior, not to turn this into a general guide on concurrency or Reactor.

## 2. Three distinct milestones to name accurately

### 2.1. Method invocation ends

Call through a Spring proxy:

```text
Caller
  -> Spring AOP proxy
     -> advice / target.method()
     <- target returns a Future or Publisher
     -> @AfterReturning may run
  <- caller receives Future or Publisher
```

The condition for `@AfterReturning` is **the method returns normally**. It does not wait for a value `T` inside `Future<T>` or a Publisher to appear later.

### 2.2. Future/CompletionStage completes

```text
method startFuture()
  |
  +--> creates still-pending CompletableFuture<T>
  +--> return future                <-- Spring @AfterReturning runs here
                                      caller now holds the handle
...
executor / event / callback executes
  |
  +--> complete(value)
      or completeExceptionally(error)
      or cancel()
                                      <-- Future transitions to completed state
```

A `Future` may already be complete when the method returns, may complete much later, or may never complete. **Do not assume all Futures are always pending at return time**; for instance, `CompletableFuture.completedFuture(value)` returns an **already-completed** object. Still, `@AfterReturning` remains **tied only to the method's normal return**, not a listener watching future state.

### 2.3. Publisher is subscribed to and emits a terminal signal

With a typical **cold Reactor `Mono`**:

```text
method makeMono()
  |
  +--> creates Mono describing pipeline
  +--> return Mono                  <-- Spring @AfterReturning runs here
                                     (data may not be processed yet)
...
consumer subscribe()
  |
  +--> onSubscribe / request
  +--> onNext(value) if data exists
  +--> onComplete() or onError(error)
                                     <-- Terminal signal when emitted
```

With `Flux` there may be **multiple `onNext` signals**, and the terminal signal may arrive much later. With a **hot publisher**, work or emissions can happen **before a new subscriber subscribes**; never describe all Publishers as cold. A subscription can also be **cancelled**, emitting neither a normal terminal success nor error to the subscriber.

**Summary milestone table:**

| Concept | Milestone it actually refers to | Synonymous with work completion? |
| --- | --- | --- |
| `@AfterReturning` | Spring-advised Java method returned normally | **No**, if the result is a Future/Publisher still in progress. |
| `@AfterThrowing` | Advised method **exited by throwing an exception** | **Does not automatically catch** errors emitted later via Future or `onError`. |
| `@After` | Advised method exited normally or with an exception | **Not** a Future/Publisher terminal callback. |
| `future.isDone()` | Future completed/cancelled state | May be success, error, or cancellation; **not synonymous with success**. |
| `future.join()` / `get()` | Waits for/reads the Future result | Can block; exception wrapping needs handling. |
| `CompletionStage.whenComplete` | Callback when the stage completes | Observes success **or** error of the stage. |
| Reactor `doOnSuccess` | Success of a `Mono` subscription | Can be an empty success; receives `null` when `Mono` completes empty. |
| Reactor `doOnError` | Publisher emits an error signal | A reactive error, not necessarily a Java method throw. |
| Reactor `doFinally` | After termination/cancellation per Reactor semantics | Can observe `ON_COMPLETE`, `ON_ERROR`, `CANCEL`. |

## 3. What value does `@AfterReturning` bind?

Spring docs allow using `returning` to receive the object returned by the target invocation:

```java
@AfterReturning(
    pointcut = "execution(* com.example.jobs.JobService.startFuture(..))",
    returning = "future",
    argNames = "future"
)
public void returned(java.util.concurrent.CompletableFuture<?> future) {
    System.out.println("done=" + future.isDone());
}
```

If `startFuture()` returns an incomplete `CompletableFuture`, the advice prints `done=false` and **finishes**. When the future completes later, **there is no second `@AfterReturning` invocation just because of completion**.

The same applies to:

```java
@AfterReturning(
    pointcut = "execution(* com.example.jobs.JobService.makePublisher(..))",
    returning = "publisher",
    argNames = "publisher"
)
public void returned(reactor.core.publisher.Mono<?> publisher) {
    System.out.println("Created/returned a Mono");
}
```

The advice receives the **`Mono` object**, not the `T` element that the `Mono` might emit later upon subscription.

**The two snippets above are fragments, not standalone projects.** The formal parameter type in advice also **restricts return-value matching**: `CompletableFuture<?>` will not match when the method actually returns another value type. For `void`/null/primitives or multiple subtypes, test actual binding in a Spring context.

### Reassigning the advice parameter does not replace the Future/Publisher the caller receives

```java
@AfterReturning(
    pointcut = "execution(* com.example.jobs.JobService.startFuture(..))",
    returning = "future",
    argNames = "future"
)
public void incorrect(CompletableFuture<String> future) {
    future = CompletableFuture.completedFuture("replacement");
}
```

This is an **illustrative anti-pattern**. `future = ...` only reassigns the advice's local variable; Spring `@AfterReturning` has no contract to replace the **reference** returned to the caller. If you must replace the caller-visible result, use `@Around` returning an appropriate stage/publisher or design the transformation in the service/adapter.

## 4. `@AfterThrowing` does not automatically observe errors occurring after return

Distinguish four cases:

| Scenario | Java method call | Subsequent work status | Does `@AfterThrowing` targeting that method run? |
| --- | --- | --- | --- |
| Method executes `throw new IllegalStateException(...)` before returning | Exceptional exit | No handle returned | **Yes**, if pointcut and type match. |
| Method returns a pending `CompletableFuture`, which later completes exceptionally | **Normal return** | Future fails later | **Not solely because** the future failed. |
| Method returns `Mono.error(ex)` normally | **Normal return** | Subscription emits `onError` | **Not solely because** of `onError`. |
| Method throws while constructing the Publisher before `return` | Exceptional exit | Publisher not returned | **Yes**, if advisor and exception type match. |

Example:

```java
public CompletableFuture<String> start() {
    CompletableFuture<String> result = new CompletableFuture<>();
    // Another thread or callback will call:
    // result.completeExceptionally(new IllegalStateException("late"));
    return result;
}
```

This is a fragment. The target method does not throw when returning the future; Spring AOP sees a **normal return**. When the future transitions to an exceptional state later, the caller sees the error at `join()` or `get()` (or when a callback runs), not as a **method-execution exception** automatically "looping back" into `@AfterThrowing` of `start()`.

Similarly:

```java
public Mono<String> fetch() {
    return Mono.error(new IllegalStateException("stream-error"));
}
```

`fetch()` can perfectly well return a `Mono` normally. The reactive error is emitted **when the publisher is subscribed to**, not as a Java exception from `fetch()` in this case.

**Note:** if an inner `@Around` advice or other Spring infrastructure converts an error into a **synchronous throw** before returning outward, what each advice observes depends on the advisor chain. The conclusions above address the method-execution boundary of **standard Spring AOP**, without ruling out adjustments made by other interceptors.

## 5. Differences with Spring's `@Async`

In Spring, `@Async` uses task execution infrastructure and is typically proxy-based. For a service:

```java
@Async
public CompletableFuture<String> compute() {
    return CompletableFuture.completedFuture("done");
}
```

this is a **fragment**; it requires `@EnableAsync` and an appropriate executor. There are two layers to think about:

1. **Method/service invocation** dispatched to an executor by `@Async` infrastructure.
2. **Future** received by the caller representing the executed work's result.

When the same method also has a custom `@Aspect`, the order between the **async interceptor** and the **custom advisor** determines which thread the advice runs on and **which Future wrapper** it sees. If the custom advice sits outside the async interceptor, `@AfterReturning` can observe the Future returned to the caller before the worker finishes executing. If the advice sits inside the invocation slice executed by the executor, it may observe a different return value at a different point in time.

**Do not infer from annotation source order** that a custom aspect's `@AfterReturning` always runs on the executor thread or always runs after the `@Async` task completes. To know for sure, inspect ordering/the proxy chain and test against the real configuration.

For `@Async void`, the caller receives no Future to call `get()` on; Spring provides `AsyncUncaughtExceptionHandler` for uncaught async exceptions. `@AfterThrowing` on a custom aspect is not an automatic substitute for `@Async`'s exception-handling configuration.

### A commonly overlooked distinction

`CompletableFuture.supplyAsync(...)` inside a target method and Spring `@Async` **are not the same technique**. Both can execute asynchronously, yet their executors, proxy chains, bean boundaries, and error routing differ. The demo in section 9 intentionally **avoids `@Async` and thread races**: it creates a pending Future, returns immediately, and completes it later via a method called from `main` so stdout can be verified deterministically.

## 6. Use Future callbacks to observe completion; do not block inside advice

With `CompletableFuture<T>` or `CompletionStage<T>`, when the goal is tracking the **final outcome**, you can register a completion callback.

Example inside Spring `@Around`:

```java
@Around("execution(* com.example.jobs.JobService.start(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    CompletionStage<?> stage = (CompletionStage<?>) pjp.proceed();

    return stage.whenComplete((value, failure) -> {
        if (failure == null) {
            metrics.incrementSuccess();
        } else {
            metrics.incrementFailure();
        }
    });
}
```

This is a **fragment** requiring the target method to return `CompletionStage`, `metrics` to exist, and `CompletionStage` to be imported. `@Around` returns the stage after attaching the callback; the callback may run on the thread **completing the stage**, not necessarily the same thread as the method advice.

Other options:

- `whenComplete`: observes success/error, and in principle preserves the original result/exception unless the callback itself throws.
- `handle`: can **transform** either success or failure into another value.
- `thenApply`: transforms the **success value**.
- `exceptionally`: handles certain exceptional completions.
- `whenCompleteAsync`, `thenApplyAsync`: schedule callbacks on a potentially different executor; avoid assuming `ThreadLocal`/MDC/SecurityContext propagate automatically.

Do not write:

```java
@AfterReturning(
    pointcut = "execution(* com.example.jobs.JobService.start(..))",
    returning = "future"
)
public void waitForResult(CompletableFuture<?> future) {
    future.join(); // Can block the proxy caller thread.
}
```

This is an **anti-pattern**. `join()` can block indefinitely if the Future never completes, defeats asynchrony, increases latency, and can cause deadlock/starvation if completion needs a resource held by the caller thread. If you only need metrics, attaching a non-blocking callback is better.

### Plain `Future` and `CompletionStage` are not equivalent

The `java.util.concurrent.Future` interface only provides operations like `isDone()`, `get()`, and `cancel()`. It **has no `whenComplete` callback API**.

If a method returns plain `Future<T>`, observing completion may require library-specific support, an appropriate adapter, or handling completion where the Future is created. Never force a generic aspect to poll continuously or call `get()` on a request thread just to collect metrics.

### Exception wrapping

- `CompletableFuture.join()` typically throws unchecked `CompletionException` wrapping the cause when the future completed exceptionally.
- `Future.get()` uses checked `ExecutionException` when the task threw an error.
- `CancellationException` is a distinct state and must not be counted as a success.
- Callbacks may receive the `Throwable` representing the failure or a wrapper; logging/metrics policies should normalize the cause properly without swallowing details.

`future.isDone()==true` only states that the future **has completed in some state**; distinguish normal, exceptional, and cancelled if business logic requires it.

## 7. Reactive `Mono`/`Flux`: method return, subscription, signals, and cancellation

### 7.1. Cold publisher

A Reactor example:

```java
public Mono<String> load() {
    return Mono.defer(() -> {
        System.out.println("Executing work");
        return Mono.just("value");
    });
}
```

This is a method fragment inside a bean. When `load()` is called:

- The Java method constructs the `Mono` and **returns**.
- Spring `@AfterReturning` may run right after the normal return.
- The `Mono.defer` supplier **is only invoked upon subscription**.
- If nobody subscribes, the supplier never runs.
- If there are **two subscriptions** to the cold publisher, the supplier can run **twice** even though target `load()` was called **once**.

Therefore, distinguish the counters:

```text
methodInvocations = 1
afterReturningInvocations = 1
subscriptions = 2
workExecutions = 2   (in the cold Mono.defer example)
```

### 7.2. Hot publishers and sources that already started work

Never state unconditionally that "a Publisher never does anything before subscription." With hot sources, data can be emitted before a subscriber arrives. `Mono.just(value)` captures the value eagerly at assembly time; `Mono.fromFuture(future)` can wrap an already-running Future; results may already be computed before `Mono` is returned.

Thus `@AfterReturning` tells you only that **the Java method returned normally**. It does not tell you whether the publisher is cold/hot, already running/idle, or still active/already completed.

### 7.3. Terminal signals

In Reactive Streams, a subscriber typically sees:

```text
onSubscribe
request(...)
onNext(value)   (0..N times depending on Publisher)
onComplete()    (normal completion)
```

or:

```text
onSubscribe
request(...)
onError(error)  (error completion)
```

A `Mono<T>` can succeed **with no elements** (`Mono.empty()`), while `Flux<T>` can emit multiple elements before terminating. **Do not use `doOnNext` alone to count all successful completions**, because an empty Publisher emits no `onNext`.

Cancellation is also a subscription-management outcome to monitor for timeouts/client disconnects; it is not identical to `onComplete` or `onError`.

### 7.4. `@AfterThrowing` is not `doOnError`

`@AfterThrowing` is a Spring AOP advice for **Java method exceptions**. `Mono.doOnError` and `Flux.doOnError` run inside the **reactive signal pipeline** when a subscriber receives an error.

An `@AfterThrowing` does not automatically listen to `onError` on every `Mono`/`Flux` returned by the target. For completion metrics tied to Publisher lifecycles, use reactive hooks/operators inside the service or use `@Around` **returning the decorated Publisher**, making sure not to alter behavior unintentionally.

## 8. `@Around` can decorate a Publisher, but must return it

Example:

```java
@Around("execution(* com.example.jobs.JobService.stream(..))")
public Object observePublisher(ProceedingJoinPoint pjp) throws Throwable {
    Mono<?> source = (Mono<?>) pjp.proceed();

    // Pipeline is decorated; callbacks only run along the reactive lifecycle.
    return source
        .doOnSubscribe(subscription -> metrics.onSubscribe())
        .doOnSuccess(value -> metrics.onSuccess())
        .doOnError(error -> metrics.onError(error))
        .doFinally(signal -> metrics.onFinally(signal));
}
```

This is a **fragment** for methods returning `Mono`, not generic code to apply blindly to `Flux` or any arbitrary `Publisher` type.

Key points:

1. `pjp.proceed()` runs the **Java method body**, returning `Mono`.
2. `doOn...` produces a **decorated publisher chain**; for the caller to use that chain, `@Around` must **return the new publisher**.
3. Callbacks attach to the **subscription lifecycle**, not the Java method's return lifecycle.
4. `doOnSuccess` is a `Mono` hook; for `Flux`, use `doOnComplete` to observe terminal success and `doOnNext` for each element.
5. `doFinally` receives a signal type such as `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`; it suits per-subscription cleanup/metrics, though callback timing relative to certain downstream operations should be tested.
6. Multiple subscriptions to a cold publisher can trigger hooks multiple times for **one** method invocation.
7. If the `Mono` is shared, cached, or hot, semantics can differ. Do not assume one subscription always equals one fresh upstream job.

**Do not do the following inside `@Around`:**

```java
Mono<?> source = (Mono<?>) pjp.proceed();
source.subscribe();  // Triggers an extra side subscription itself.
return source;        // Caller may subscribe again.
```

This is an **illustrative anti-pattern**. Calling `subscribe()` manually inside an aspect can trigger work, HTTP calls, DB access, or side effects **before the caller intentionally subscribes**, and then the caller triggers it a second time. It breaks subscription ownership, complicates error/cancellation propagation, and can cause duplicate processing.

When you need to transform values, use `map`/`flatMap` per contract; when you need to observe terminal states, use `doOnSuccess`/`doOnComplete`/`doOnError`/`doFinally` appropriately. Never block with `block()` inside an aspect just to "wait for completion," especially on WebFlux non-blocking threads.

## 9. Runnable Java 17+ example: method returns before Future completion and Mono subscription

The example below is designed **for deterministic stdout**. It avoids scheduler races:

- `startFuture()` creates a **pending CompletableFuture** and returns immediately. The caller completes the future later via another method.
- A second future is completed **exceptionally** after return; `@AfterThrowing` does not run for that late error.
- `failImmediately()` **throws before returning**, so `@AfterThrowing` runs.
- `coldPublisher()` returns `Mono.defer`, so work runs only on subscription; two subscriptions to the same `Mono` run the work twice.
- `observedPublisher()` and `errorPublisher()` are decorated by `@Around` to count **reactive success/error signals**, rather than relying on `@AfterReturning`.

The project uses **Java 17+, Spring Framework 6.1.14, AspectJ Weaver 1.9.22.1, Reactor Core 3.6.11, and Maven**. This is a fixed illustrative version set, with no claim of being the latest. Only **proxy-based Spring AOP** is used, with no AspectJ weaving agent configured.

### 9.1. Directory structure

```text
spring-aop-completion-boundary/
├── pom.xml
└── src/main/java/com/example/completion/
    ├── JobService.java
    ├── CompletionAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-completion-boundary</artifactId>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.11</version>
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

`spring-context` provides `ApplicationContext` and pulls in the needed Spring AOP dependencies transitively; `aspectjweaver` provides Spring's `@AspectJ` pointcut parser. `reactor-core` provides `Mono` and signal operators. No web server is needed to test the distinction between method return and publisher lifecycle.

### 9.3. `src/main/java/com/example/completion/JobService.java`

```java
package com.example.completion;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class JobService {
    private CompletableFuture<String> pending;
    private final AtomicInteger coldSubscriptions = new AtomicInteger();

    public CompletableFuture<String> startFuture() {
        pending = new CompletableFuture<>();
        System.out.println("[TARGET] returned pending Future");
        return pending;
    }

    public void completeFuture(String value) {
        pending.complete(value);
    }

    public void failFuture() {
        pending.completeExceptionally(
                new IllegalArgumentException("late-future"));
    }

    public CompletableFuture<String> failImmediately() {
        System.out.println("[TARGET] throwing before return");
        throw new IllegalStateException("early");
    }

    public Mono<String> coldPublisher() {
        System.out.println("[TARGET] returned cold Publisher");
        return Mono.defer(() -> {
            coldSubscriptions.incrementAndGet();
            System.out.println("[WORK] cold subscription");
            return Mono.just("M-OK");
        });
    }

    public Mono<String> observedPublisher() {
        System.out.println("[TARGET] returned observed Publisher");
        return Mono.defer(() -> Mono.just("OBS-OK"));
    }

    public Mono<String> errorPublisher() {
        System.out.println("[TARGET] returned error Publisher");
        return Mono.error(new IllegalArgumentException("late-mono"));
    }

    public int coldSubscriptions() {
        return coldSubscriptions.get();
    }
}
```

**Design explanation:** `pending` is merely a helper field for sequential demo execution, not how to organize job state in production. In multi-request applications, use per-request job IDs and proper state ownership rather than storing an overwritable `pending` field on a singleton service.

`completeFuture` and `failFuture` are invoked by the caller after `startFuture` has returned. They **are not selected by any pointcuts in the demo**, so they emit no extra advice events into the output.

`coldPublisher` creates `Mono.defer`: `[WORK]` prints only upon subscription. `observedPublisher` and `errorPublisher` have return type `Mono<String>` so `@Around` can attach reactive operators.

### 9.4. `src/main/java/com/example/completion/CompletionAspect.java`

```java
package com.example.completion;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import reactor.core.publisher.Mono;

@Aspect
public class CompletionAspect {
    private final AtomicInteger futureReturns = new AtomicInteger();
    private final AtomicInteger syncThrows = new AtomicInteger();
    private final AtomicInteger publisherReturns = new AtomicInteger();
    private final AtomicInteger monoSuccesses = new AtomicInteger();
    private final AtomicInteger monoErrors = new AtomicInteger();

    @AfterReturning(
        pointcut = "execution(* com.example.completion.JobService.startFuture(..))",
        returning = "future",
        argNames = "future"
    )
    public void afterFutureReturned(CompletableFuture<?> future) {
        futureReturns.incrementAndGet();
        System.out.println("[AOP after-return] Future done=" + future.isDone());
    }

    @AfterThrowing(
        pointcut = "execution(* com.example.completion.JobService.startFuture(..))"
                 + " || execution(* com.example.completion.JobService.failImmediately(..))",
        throwing = "error",
        argNames = "error"
    )
    public void afterSynchronousThrow(Throwable error) {
        syncThrows.incrementAndGet();
        System.out.println("[AOP after-throw] "
                + error.getClass().getSimpleName());
    }

    @AfterReturning(
        pointcut = "execution(* com.example.completion.JobService.coldPublisher(..))",
        returning = "publisher",
        argNames = "publisher"
    )
    public void afterPublisherReturned(Mono<?> publisher) {
        publisherReturns.incrementAndGet();
        System.out.println("[AOP after-return] Publisher returned");
    }

    @Around(
        "execution(* com.example.completion.JobService.observedPublisher(..))"
        + " || execution(* com.example.completion.JobService.errorPublisher(..))"
    )
    public Object monitorPublisher(ProceedingJoinPoint pjp) throws Throwable {
        Mono<?> source = (Mono<?>) pjp.proceed();
        System.out.println("[AOP around] returned Publisher: "
                + pjp.getSignature().getName());

        return source
                .doOnSuccess(value -> monoSuccesses.incrementAndGet())
                .doOnError(error -> monoErrors.incrementAndGet());
    }

    public int futureReturns() {
        return futureReturns.get();
    }

    public int syncThrows() {
        return syncThrows.get();
    }

    public int publisherReturns() {
        return publisherReturns.get();
    }

    public int monoSuccesses() {
        return monoSuccesses.get();
    }

    public int monoErrors() {
        return monoErrors.get();
    }
}
```

**Meaning of each advice:**

- `afterFutureReturned` receives the **Future reference** when `startFuture` returns normally. `isDone=false` is deterministic in the demo because the caller has not called `completeFuture` yet.
- `afterSynchronousThrow` observes only **Java exceptions from the corresponding method execution**. A future later completing exceptionally **does not call back into** this advice.
- `afterPublisherReturned` counts **a single Mono return**, not subscriptions.
- `monitorPublisher` uses `@Around` to **return a decorated Mono**, so `monoSuccesses`/`monoErrors` increment when a subscriber receives the matching signal.
- Pointcuts in the example do not overlap `@Around` and `@AfterReturning` on the same method; hence stdout does not depend on ordering across multiple advice methods on one join point.

### 9.5. `src/main/java/com/example/completion/AppConfig.java`

```java
package com.example.completion;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public JobService jobService() {
        return new JobService();
    }

    @Bean
    public CompletionAspect completionAspect() {
        return new CompletionAspect();
    }
}
```

`@EnableAspectJAutoProxy` enables the Spring AOP auto-proxy infrastructure. `proxyTargetClass=true` selects CGLIB class proxies for `JobService`, which implements no business interface. `CompletionAspect` is a Spring bean via `@Bean`; `@Aspect` alone does not register a bean.

### 9.6. `src/main/java/com/example/completion/DemoApp.java`

```java
package com.example.completion;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import reactor.core.publisher.Mono;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            JobService jobs = context.getBean(JobService.class);
            CompletionAspect aspect = context.getBean(CompletionAspect.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(jobs));

            CompletableFuture<String> success = jobs.startFuture();
            System.out.println("futureBeforeComplete=" + success.isDone());
            jobs.completeFuture("F-OK");
            System.out.println("futureValue=" + success.join());

            CompletableFuture<String> failure = jobs.startFuture();
            jobs.failFuture();
            try {
                failure.join();
            } catch (CompletionException error) {
                System.out.println("futureFailure="
                        + error.getCause().getClass().getSimpleName());
            }

            try {
                jobs.failImmediately();
            } catch (IllegalStateException error) {
                System.out.println("syncFailure=" + error.getMessage());
            }
            System.out.println("futureReturns=" + aspect.futureReturns());
            System.out.println("syncThrows=" + aspect.syncThrows());

            Mono<String> cold = jobs.coldPublisher();
            System.out.println("coldBeforeSubscribe="
                    + jobs.coldSubscriptions());

            System.out.println("coldValue1=" + cold.block());
            System.out.println("coldValue2=" + cold.block());
            System.out.println("coldAfterSubscribe="
                    + jobs.coldSubscriptions());
            System.out.println("publisherReturns=" + aspect.publisherReturns());

            Mono<String> monitored = jobs.observedPublisher();
            System.out.println("monoSuccessBefore=" + aspect.monoSuccesses());
            System.out.println("monitoredValue=" + monitored.block());
            System.out.println("monoSuccessAfter=" + aspect.monoSuccesses());

            try {
                jobs.errorPublisher().block();
            } catch (IllegalArgumentException error) {
                System.out.println("monoError=" + error.getMessage());
            }

            System.out.println("monoSignalErrors=" + aspect.monoErrors());
            System.out.println("syncThrowsFinal=" + aspect.syncThrows());
        }
    }
}
```

The demo uses no background threads in `JobService` and its `Mono`s use synchronous cold sources, so the order of `System.out.println` lines produced by the code **can be compared directly**. In production, thread scheduling and Reactor schedulers can interleave timestamps and logs; that is a separate concern.

### 9.7. Running Maven and expected stdout

With JDK 17+ and Maven able to fetch dependencies, in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.completion.DemoApp
```

Program output lines (excluding extra Maven/SLF4J messages):

```text
isAopProxy=true
[TARGET] returned pending Future
[AOP after-return] Future done=false
futureBeforeComplete=false
futureValue=F-OK
[TARGET] returned pending Future
[AOP after-return] Future done=false
futureFailure=IllegalArgumentException
[TARGET] throwing before return
[AOP after-throw] IllegalStateException
syncFailure=early
futureReturns=2
syncThrows=1
[TARGET] returned cold Publisher
[AOP after-return] Publisher returned
coldBeforeSubscribe=0
[WORK] cold subscription
coldValue1=M-OK
[WORK] cold subscription
coldValue2=M-OK
coldAfterSubscribe=2
publisherReturns=1
[TARGET] returned observed Publisher
[AOP around] returned Publisher: observedPublisher
monoSuccessBefore=0
monitoredValue=OBS-OK
monoSuccessAfter=1
[TARGET] returned error Publisher
[AOP around] returned Publisher: errorPublisher
monoError=late-mono
monoSignalErrors=1
syncThrowsFinal=1
```

### 9.8. Reading the results accurately

1. `startFuture()` **returned twice**, so `futureReturns=2`, and `done=false` at both `@AfterReturning` calls. That says nothing about whether the futures will succeed or fail.
2. The first future is completed by the caller **after** the method and `@AfterReturning` already ran, and then `join()` returns `F-OK`.
3. The second future completes exceptionally after returning. `join()` throws `CompletionException` with cause `IllegalArgumentException`, yet **`@AfterThrowing` does not run** for that late completion event.
4. `failImmediately()` **throws before returning a Future**, so `@AfterThrowing` runs once: `syncThrows=1`.
5. `coldPublisher()` was **called once**, so `publisherReturns=1`. Yet calling `cold.block()` twice creates two **subscriptions**; `[WORK]` appears twice and `coldAfterSubscribe=2`.
6. `monitorPublisher` executes when `observedPublisher()` returns, yet `monoSuccessBefore=0`. Only after `monitored.block()` subscribes and the `Mono` succeeds does `monoSuccessAfter=1`.
7. `errorPublisher()` returns normally and `@Around` returns the decorated Publisher. The error appears when `block()` subscribes, incrementing `monoSignalErrors=1` while **not incrementing** `syncThrowsFinal` because no synchronous Java throw came from `JobService.errorPublisher()`.
8. Every target call goes through the Spring bean proxy, not `new JobService()` outside the context.

This demo intentionally separates **method return**, **Future completion**, and **reactive subscription/signal**. Expected output is derived from the presented source code; Java/Maven must be run in a real environment to check build artifacts or dependency mirror compatibility.

## 10. Measuring duration in Spring Aspect: which interval are you measuring?

A traditional `@Around`:

```java
@Around("execution(* com.example.jobs.JobService.*(..))")
public Object measure(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        metrics.record(elapsed);
    }
}
```

This is a **fragment**. For services returning a `Future` or `Publisher` immediately, `elapsed` is **Java method invocation/assembly time**, **not automatically** the time until Future completion or Publisher terminal signal.

To distinguish accurately, name your metrics:

| Metric | Start | End | What does it measure? |
| --- | --- | --- | --- |
| `method.return.latency` | Entering Spring advice | Java method return/throw | Invocation/Publisher assembly. |
| `future.completion.latency` | Task start/callback registration | Future completion/cancellation | The work represented by the Future, per start definition. |
| `publisher.subscription.duration` | Subscription starts | Terminal/cancel signal | Duration of **one subscription**, not necessarily the publisher object's lifetime. |
| `request.duration` | HTTP request begins | HTTP response/cancellation completes | Requires HTTP/web instrumentation, not inferred from service `@AfterReturning`. |

A `Mono` can be subscribed to multiple times. If you record **one timestamp** at method assembly and measure until multiple subscription completions, metrics can include **wait time before subscription** and yield misleading numbers. To measure the subscriber lifecycle, capture the start time **at subscription** using `Mono.defer`, `doOnSubscribe`, or instrumentation with per-subscription context.

### ThreadLocal/MDC and Reactor Context

In Spring AOP, advice initially runs on the thread invoking the Java method. Completion callbacks may run on **another thread**. Reactor signals may traverse different schedulers.

- Never assume `ThreadLocal`, MDC, transaction context, or `SecurityContextHolder` from advice execution time automatically appears inside a future callback.
- Reactor provides `Context` for subscription-bound data; use built-in context propagation mechanisms matching your Spring/Reactor version.
- Prefer attaching correlation IDs/trace context via framework-supported mechanisms rather than storing `ProceedingJoinPoint` or request-specific state in fields of a singleton aspect.
- If sensitive logging is a concern, do not dump full Future results or Publisher elements into logs by default.

## 11. Spring WebFlux: method completion does not mean the response has been sent

Suppose a Spring WebFlux controller or service method returns:

```java
public Mono<ResponseDto> get(String id) {
    return service.fetch(id).map(ResponseDto::from);
}
```

This is a fragment requiring `ResponseDto` and `service` to exist. `@AfterReturning` targeting `get` or `fetch` can see the **`Mono` reference** when the Java method returns. However:

1. Dispatcher/HTTP handling may not even have subscribed to the pipeline yet at that moment.
2. `fetch` may execute later.
3. The `Mono` can complete empty, with an error, or be cancelled.
4. The HTTP server still has to encode and write the response; a reactive terminal signal **is not automatically synonymous** with "the client received every byte."
5. A controller/service method with `@Transactional` or Spring transaction facilities can follow specialized reactive transaction behavior; do not assume every transaction commits right when the Java method returns.

When you need observability for the **HTTP request lifecycle**, use WebFlux filters, observation, or tracing facilities at the web layer; when you need observability for **publisher subscriptions**, use Reactor operators or Spring-compatible reactive instrumentation. Service-layer Spring AOP `@AfterReturning` measures **method return**, and does not replace those facilities.

## 12. Common reasoning mistakes

| Symptom / false conclusion | What is actually happening | How to verify |
| --- | --- | --- |
| "`@AfterReturning` ran, so the async job succeeded." | The method returned a Future normally; the job may still be pending or fail later. | Attach `whenComplete`/inspect terminal outcome. |
| "`@AfterThrowing` did not run, so the CompletableFuture had no errors." | The Future can complete exceptionally **after** method return. | `whenComplete`, `join()`/`get()`, exception cause. |
| "`@AfterReturning` ran, so the Mono pipeline was subscribed to." | The method may simply have returned a cold Publisher with no subscribers yet. | Use `doOnSubscribe` and pipeline observability. |
| "`Mono.error(ex)` causes Spring `@AfterThrowing` to run." | The method returns a Mono normally; `onError` is a later reactive signal. | Use `doOnError` or subscriber terminal hooks. |
| "One method invocation equals one `Flux` execution." | A cold Publisher can be subscribed to multiple times; hot publishers have different semantics. | Count method calls and subscriptions separately. |
| "Future `isDone=true` means success." | Future may be exceptional or cancelled. | Inspect classified completion state/outcome. |
| "Calling `join()` in `@AfterReturning` to measure completion is harmless." | Can block the caller, break asynchrony, and cause deadlocks. | Attach non-blocking callbacks or instrument task creation. |
| "`@Around` attached `doOnError`; no need to return the decorated Mono." | Reactor operators return a new publisher; discarding the wrapper means callers bypass the hooks. | `return source.doOnError(...)`. |
| "Subscribe inside the aspect just to log." | Can trigger an extra side subscription and duplicate side effects. | Avoid subscribing; return the decorated Publisher. |
| "`doOnNext` suffices to count every Mono success." | `Mono.empty()` succeeds without emitting `onNext`. | Use `doOnSuccess` or appropriate terminal hooks. |
| "`doFinally` always means success." | Receives `CANCEL`, `ON_ERROR`, or `ON_COMPLETE`. | Classify by `SignalType`. |
| "`@Async` and custom AOP advice always run on the same thread." | Depends on proxy/advisor ordering and executor. | Check `@EnableAsync`, `@Order`, advisor chain, and test realistically. |
| "`@AfterReturning` measures HTTP response duration." | It measures Java method return, not network write lifecycles. | Instrument WebFlux/HTTP request boundaries. |
| "Future callbacks automatically inherit MDC/transaction context." | Completion may run on a different thread. | Configure proper context propagation. |
| "`isAopProxy=true` proves advice observes terminal signals." | Proxy proves interception infrastructure exists, not that Future/Reactive callbacks are wired. | Assert counters after real completion/subscription. |

## 13. Checklist for reviewing a Spring Aspect handling Future/Publisher

- [ ] Clearly define whether you need to observe **method return** or **actual async/reactive completion**.
- [ ] Use `@AfterReturning` only to establish **normal method return**, not to infer task success.
- [ ] Apply `@AfterThrowing` only for **method exception paths**, not in place of `onError` or future exceptional completion.
- [ ] For plain `Future`, do not assume `whenComplete` exists; check the actual API type.
- [ ] For `CompletionStage`, attach callbacks properly without altering results or exceptions unintentionally.
- [ ] Never block with `join()`/`get()` inside advice on latency-sensitive call paths.
- [ ] For Publishers, distinguish cold vs. hot, and assembly/subscription/emission/terminal/cancellation phases.
- [ ] Never call `subscribe()` inside an aspect just to observe outcomes.
- [ ] When using `@Around` to decorate a Publisher, **return the new publisher** with the required operators attached.
- [ ] Measure per-subscription metrics when a Publisher can have multiple subscribers.
- [ ] Use `doOnSuccess`/`doOnComplete`/`doOnError`/`doFinally` suited to the Publisher type and semantics.
- [ ] When using `@Async`, verify advisor ordering, executor threads, and exception policies.
- [ ] Evaluate `ThreadLocal`/MDC/transaction/security context propagation to callbacks.
- [ ] Know proxy boundaries: Spring bean, `@EnableAspectJAutoProxy`, no self-invocation or raw `new` targets.
- [ ] Have integration tests for pending→success, pending→error, synchronous throw, empty/error Publisher, cancellation, and multiple subscriptions as applicable.
- [ ] Distinguish method duration from job/subscription/request duration in metric names.

### Official references

- Spring Framework — **Declaring Advice**, `@AfterReturning`/`@AfterThrowing`/`@Around`: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **Task Execution and Scheduling**, `@Async`/`Future`/`CompletableFuture`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — **Proxying Mechanisms** and self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Reactor Core — **Hot Versus Cold**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html
- Reactor Core — **Introduction to Reactive Programming** and subscription lifecycle: https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html
- Project Reactor — `Mono`/ `Flux` Javadoc: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html

**Conclusion:** When a Spring Aspect sees a method **returning a `Future` or `Publisher`**, the only certainty from `@AfterReturning` is that **the Java method normally returned a handle or publisher object**. The work that object represents has a **different lifecycle**, consisting of Future completion or Publisher subscription, signals, and cancellation. To audit or meter **actual completion**, attach `CompletionStage` callbacks or return a publisher decorated with Reactor operators (via `@Around` if needed), rather than inferring task completion from `@AfterReturning` having executed.
