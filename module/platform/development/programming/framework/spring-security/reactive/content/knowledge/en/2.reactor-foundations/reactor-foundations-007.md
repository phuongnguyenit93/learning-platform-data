# Deferring Execution with `Mono.defer` and `Mono.fromCallable` When Integrating Synchronous Code

## 1. Why Defer Execution?

In Reactor/WebFlux applications, **creating** a `Mono` does not mean **running** the work inside it. We usually assemble a pipeline first, and Reactor executes it only when a subscriber arrives—for example, when WebFlux subscribes to send an HTTP response.

This is especially important when a reactive system must invoke legacy synchronous code: blocking JDBC/DAO calls, SDKs that only expose synchronous APIs, blocking file reads, or imperative user-verification services. If invoked directly while assembling the pipeline, the work happens too early. If invoked inside the pipeline on an event-loop thread, the application can still stall.

After this lesson, you should be able to distinguish three questions:
1. **When** is the synchronous code invoked: at pipeline assembly or at subscription time?
2. Does **each subscription** trigger a fresh computation?
3. **On which thread** does the work run, and can that work block the thread?

> Scope: focuses on `Mono.defer`, `Mono.fromCallable`, and patterns for wrapping synchronous code with Reactor. Details of authentication, authorization, or data-store design are outside this lesson.

## 2. Three Timings to Distinguish

- **Assembly:** creating the `Mono` object and chaining operators. Typically, work is described rather than executed.
- **Subscription:** a subscriber requests to observe the publisher. For ordinary cold sources, this is when the source starts producing signals.
- **Execution:** the actual code runs on a thread determined by the source/operator/scheduler. *Lazy* does not automatically mean *non-blocking* or running on a different thread.

Easy-to-misunderstand example:

```java
String user = legacyService.loadUser(); // runs IMMEDIATELY here
Mono<String> mono = Mono.just(user);     // only wraps an already-computed value

// Equivalent in eagerness:
Mono<String> alsoEager = Mono.just(legacyService.loadUser());
```

`Mono.just(value)` takes a value that has already been computed. Java must evaluate the argument `legacyService.loadUser()` before calling `just`, so even if nobody subscribes, the synchronous call has already happened.

Moving the expression to `fromCallable` changes execution timing:

```java
Mono<String> lazy = Mono.fromCallable(legacyService::loadUser);
// loadUser is not called when creating lazy.
// Each time this source is subscribed to, the Callable executes once.
```

That solves only the **timing** question. If `loadUser` blocks, you still need to pick an appropriate scheduler in Section 6.

## 3. `Mono.fromCallable`: Deferring a Value-Returning Computation

Conceptual signature: `Mono.fromCallable(Callable<? extends T>)`. Reactor holds the `Callable` and invokes it when a subscription reaches this source. A `Callable` can return a value, return `null`, or throw an exception.

```java
Mono<User> source = Mono.fromCallable(() -> legacyUserDao.findById(userId));
```

Here `User`, `legacyUserDao`, and `userId` are application types/variables, so this **illustrative** snippet runs only once they are defined. Source behavior is:

| Result of `Callable.call()` | Signal from `Mono` |
| --- | --- |
| Returns non-`null` `user` object | `onNext(user)` then `onComplete()` |
| Returns `null` | `onComplete()` without emitting an element |
| Throws an exception | `onError(exception)` |

Do not use `Mono.just(null)`: `just` rejects null values. If a synchronous API returns null to signify "not found", `fromCallable` turns that result into a valid `Mono.empty()`.

```java
Mono<String> missing = Mono.fromCallable(() -> null);
Mono<String> withFallback = missing.defaultIfEmpty("not-found");

// Callable allows checked exceptions; Reactor converts errors into onError.
Mono<String> failure = Mono.fromCallable(() -> {
    throw new java.io.IOException("legacy service unavailable");
});
```

**Every subscription is a fresh invocation** with a standard cold `Mono.fromCallable`. Two `subscribe()` or `block()` calls can re-run the query; `retry` can also cause the source to be re-subscribed. Do not implicitly assume the result is cached or that a write happens only once.

`Mono.fromSupplier` is also lazy and fits when the input is a `Supplier<T>`, whereas `Callable<T>` is more convenient when the API may throw checked exceptions. For operations with no return value, see `Mono.fromRunnable` in Section 8.

## 4. `Mono.defer`: Deferring **Choosing/Creating the Entire Publisher**

Conceptual signature: `Mono.defer(Supplier<? extends Mono<? extends T>>)`. On each subscription, Reactor invokes the supplier to obtain **a new `Mono`**, then subscribes to that `Mono`. The difference with `defer` is that the lambda returns a **publisher**, not merely a value.

```java
AtomicBoolean useCache = new AtomicBoolean(false);

Mono<String> selected = Mono.defer(() ->
    useCache.get()
        ? cacheLookup()   // method returning Mono<String>
        : remoteLookup()  // method returning Mono<String>
);

// If useCache changes before the next subscribe,
// the chosen branch can also differ.
```

The snippet above is **illustrative**: `cacheLookup` and `remoteLookup` must be defined. With `defer`, the source-selection decision is made at subscription time, which is very useful when state/configuration can change between subscriptions.

`Mono.defer(() -> Mono.just(legacyService.loadUser()))` also defers calling `loadUser` because the entire `Mono.just(...)` expression sits *inside* the supplier. However, when you only have a synchronous computation returning a value, writing `Mono.fromCallable(legacyService::loadUser)` is simpler and handles `null` more naturally.

Keep in mind:
- `defer` **does not automatically switch threads**; the supplier can still block the subscribing thread.
- Do not return `null` as the publisher from a `defer` supplier; return `Mono.empty()` when an empty publisher is needed.
- `defer` does not cache or share results by default.
- If you need to choose a source based on each subscriber's Reactor `Context`, the appropriate API is `Mono.deferContextual(...)`; this differs from reading `ThreadLocal`.

## 5. Quick Selection Table

| Need | Suitable operator | Reason |
| --- | --- | --- |
| Already have a valid value, no recomputation needed | `Mono.just(value)` | Wraps an existing value eagerly |
| Need to call a synchronous method returning 0 or 1 value on subscribe | `Mono.fromCallable(callable)` | Lazy, catches exceptions, turns `null` into empty |
| Need to create/choose a fresh `Mono` from state on each subscription | `Mono.defer(() -> someMono)` | Defers creating the publisher itself |
| Synchronous computation that throws no checked exceptions | `Mono.fromSupplier(supplier)` | Lazy with `Supplier<T>` |
| Synchronous action with no return value | `Mono.fromRunnable(runnable)` | Emits complete/error, emits no `onNext` |
| Possibly null value already computed beforehand | `Mono.justOrEmpty(value)` | Empty if null, but does not make computation lazy |

**Pragmatic rule:** "Return a value from legacy code" usually starts with `fromCallable`; "decide which publisher to run" usually starts with `defer`.

## 6. Wrapping **Blocking Calls**: Combining `fromCallable` with `boundedElastic`

`fromCallable` only postpones work until subscription time. If there is blocking I/O, socket waits, synchronization locks, or `Thread.sleep`, the call can still hold the event-loop thread and reduce capacity for other requests.

Reactor's recommended pattern:

```java
Mono<User> userMono = Mono
    .fromCallable(() -> legacyUserDao.findById(userId))
    .subscribeOn(Schedulers.boundedElastic());
```

This is an **illustrative snippet in an application** that already has `User` and `legacyUserDao`. Required imports: `reactor.core.publisher.Mono` and `reactor.core.scheduler.Schedulers`.

Execution proceeds as follows:
1. Pipeline assembly does not invoke `findById`.
2. When subscribed, `subscribeOn(boundedElastic())` schedules subscribing to the source on a worker of a scheduler suited for blocking work.
3. The `Callable` invokes `findById` on that worker and emits a value, empty, or error.
4. Subsequent operators process signals according to Reactor's scheduling rules.

Place `subscribeOn` **immediately after the blocking source** so readers see the scheduler boundary clearly. `subscribeOn` itself **does not subscribe**, and `boundedElastic` **does not turn blocking code into non-blocking code**: it isolates waiting away from event-loop threads, with bounded worker and queued-task counts.

Do not confuse `publishOn` with `subscribeOn`. `publishOn` switches the execution context **downstream** from that operator's position; if a blocking source runs upstream, placing `publishOn` after the source does not protect the event loop from that blocking call.

### When the blocking source sits inside `flatMap`

Suppose `tokenMono` is a `Mono<String>` already in the reactive flow:

```java
// WRONG: legacyVerifier.verify(token) is called directly in the mapper,
// potentially on the thread processing the reactive pipeline.
Mono<Boolean> unsafe = tokenMono.flatMap(
    token -> Mono.just(legacyVerifier.verify(token))
);

// CORRECT: defer verify and offload only the blocking branch to boundedElastic.
Mono<Boolean> safe = tokenMono.flatMap(token ->
    Mono.fromCallable(() -> legacyVerifier.verify(token))
        .subscribeOn(Schedulers.boundedElastic())
);
```

`legacyVerifier` is an illustrative object and `verify` is a synchronous method returning a boolean. If `verify` throws, `safe` emits `onError`. For methods returning `void`, you can use `Mono.fromRunnable(() -> legacyAudit.write(event)).subscribeOn(Schedulers.boundedElastic())`.

**Do not use** `block()`, `blockFirst()`, or `blockLast()` to bridge into a WebFlux/Spring Security reactive pipeline. Those methods block the caller and can throw errors or hang execution when called on threads that forbid blocking. In reactive HTTP handlers, **return `Mono`/`Flux`** and let the framework manage subscriptions.

## 7. Runnable Java 17+ Example: Proving Exact Invocation Timing

This standalone example uses Reactor Core; `block()` is used only from `main` to demonstrate sequential subscriptions, not as a pattern for WebFlux handlers.

Create these files:

```text
lazy-mono-demo/
├── build.gradle
└── src/main/java/demo/LazyMonoDemo.java
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

application {
    mainClass = 'demo.LazyMonoDemo'
}
```

Contents of `src/main/java/demo/LazyMonoDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class LazyMonoDemo {
    private static final AtomicInteger CALLS = new AtomicInteger();

    private static String readSync() {
        int n = CALLS.incrementAndGet();
        System.out.println("readSync=" + n);
        return "user-" + n;
    }

    public static void main(String[] args) {
        Mono<String> eager = Mono.just(readSync());
        System.out.println("eager assembled");
        eager.block();
        eager.block();

        Mono<String> lazy = Mono.fromCallable(LazyMonoDemo::readSync);
        System.out.println("lazy assembled");
        System.out.println("lazy first=" + lazy.block());
        System.out.println("lazy second=" + lazy.block());

        AtomicInteger choices = new AtomicInteger();
        Mono<String> branch = Mono.defer(() ->
            choices.incrementAndGet() % 2 == 1
                ? Mono.just("A")
                : Mono.just("B")
        );
        System.out.println("branch first=" + branch.block());
        System.out.println("branch second=" + branch.block());
    }
}
```

Run from the `lazy-mono-demo` directory with a compatible Gradle installation:

```bash
gradle --quiet run
```

Program `stdout`:

```text
readSync=1
eager assembled
lazy assembled
readSync=2
lazy first=user-2
readSync=3
lazy second=user-3
branch first=A
branch second=B
```

Explanation:
- `readSync=1` appears **before** `eager assembled`: `Mono.just`'s argument was evaluated during assembly. Both `eager.block()` calls only read the same value without calling `readSync` again.
- `lazy assembled` appears **before** `readSync=2`: `fromCallable` did not run during assembly. Two `lazy.block()` calls create two subscriptions and execute `readSync=2`, `readSync=3` in turn.
- `branch` builds a new publisher on each subscribe, picking `A` then `B` because the counter changes.

The example performs no real I/O wait, so `boundedElastic` is omitted here to observe stdout ordering deterministically.

## 8. Applying in Spring Security Reactive and Legacy Synchronous Code

In a system using Spring Security reactive, a practical integration point may be an adapter calling a legacy repository/SDK to fetch data for authentication, token checking, or account lookup. Blocking code should be isolated inside an **adapter returning a Mono**, then composed with reactive operators:

```java
// Illustrative example inside a service/adapter with legacyUserDao:
Mono<User> findUser(String username) {
    return Mono.fromCallable(() -> legacyUserDao.findByUsername(username))
        .subscribeOn(Schedulers.boundedElastic());
}

// In a pipeline that has usernameMono:
// usernameMono.flatMap(this::findUser)
```

If the DAO returns `null` when no account is found, `findUser` results in `Mono.empty()`. The authentication layer must explicitly decide what empty means (e.g., mapping it to an appropriate authentication error), rather than assuming it equals a valid user. Do not log tokens, passwords, credentials, or sensitive data when handling errors.

In reactive security, do not rely on Servlet-style `ThreadLocal` `SecurityContextHolder` to read context after switching threads. Reactive security context propagates through Reactor `Context` and corresponding APIs such as `ReactiveSecurityContextHolder`. Switching schedulers and deferring execution are two independent concerns.

When genuinely non-blocking libraries are available (R2DBC, reactive WebClient, reactive SDKs), prefer using those reactive APIs directly. `boundedElastic` is a **bridge** for blocking code that cannot be replaced immediately; it still consumes threads while waiting and has bounded capacity.

## 9. Nulls, Errors, Retries, and Subscription Cancellation

### Nulls and empty streams

```java
Mono<String> loaded = Mono.fromCallable(() -> legacyLookup("alice"));
Mono<String> required = loaded.switchIfEmpty(
    Mono.error(new IllegalStateException("No matching record"))
);
```

`legacyLookup` is an illustrative method. `switchIfEmpty` distinguishes "no data" from "data present"; only use an error type appropriate for your real domain. For authentication data, choose proper security errors at the corresponding handling layer.

### Exceptions and recovery

```java
Mono<String> source = Mono.fromCallable(() -> legacyLookup("alice"))
    .subscribeOn(Schedulers.boundedElastic());

Mono<String> recovered = source.onErrorResume(
    java.io.IOException.class,
    ex -> Mono.just("temporary-fallback")
);
```

This illustrative snippet assumes `legacyLookup` can throw `IOException`. Reactor routes the exception to `onError`; `onErrorResume` applies the fallback only for the specified error group. Do not turn all authentication/authorization errors into success, and do not swallow exceptions to mask infrastructure outages.

### Resubscribe and side effects

Ordinary `fromCallable`/`defer` sources run again on new subscriptions; `retry` re-subscribes after an error. Therefore, if a Callable writes data, sends emails, deducts money, mutates state, or calls APIs with side effects, you must evaluate idempotency and re-execution risk. `Mono.cache()` can alter this behavior by storing signals to share with subsequent subscriptions, but apply caching only after reviewing lifecycle and data correctness.

### Cancellation

Cancelling a subscription does not guarantee stopping an in-flight blocking JDBC/SDK call. Stoppability depends on the library and its interrupt/cancel handling. Configure client/driver timeouts, bound concurrency, monitor `boundedElastic` queues, and handle traffic spikes. Do not treat Reactor-level `timeout` as a guarantee that underlying I/O work has halted.

## 10. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `Mono.just(blockingCall())` | Executes the blocking call immediately when building the Mono | `Mono.fromCallable(() -> blockingCall())` |
| Thinking `fromCallable` automatically runs in the background | Can block the subscriber's thread | For genuinely blocking calls, attach `subscribeOn(Schedulers.boundedElastic())` |
| Using `publishOn` after a blocking source thinking upstream is protected | Blocking source can still run on the event loop | Place `subscribeOn` right against the source |
| `Mono.defer(() -> Mono.just(syncCall()))` everywhere | Verbose and easy to forget null handling | Use `fromCallable` when only a single value is needed |
| `Mono.justOrEmpty(syncCall())` to "make it lazy" | `syncCall()` is still evaluated eagerly | `fromCallable(syncCall)` or a lambda |
| Calling `block()` from a reactive handler | Blocks thread, can throw errors or stall processing | Return a Mono and compose with `flatMap` |
| Assuming every Mono executes at most once | New subscriptions/retries can repeat side effects | Assess idempotency, retries, and caching |
| Moving everything onto `boundedElastic` | Wastes threads when work is already non-blocking | Offload only genuinely blocking work |

**Syntax note:** `fromCallable(syncCall)` in the table is shorthand for a valid callable (such as `() -> syncCall()`), not valid standalone Java syntax if `syncCall` is a method.

## 11. Self-Check Knowledge

1. Put `Mono.just(dao.load())` in a method returning a Mono and do not subscribe: does `dao.load()` run? **Yes**, because Java must evaluate the argument before calling `just`.
2. Change it to `Mono.fromCallable(dao::load)`: when does it run? **When the source is subscribed to**, typically once per subscription.
3. The DAO returns null: what does the `fromCallable` source signal? **Empty completion**, without emitting `null`.
4. When do you choose `defer`? **When you want to create/choose a different Mono at each subscription time**, e.g., based on current state.
5. Do `defer` or `fromCallable` make a blocking source non-blocking? **No**; to protect the event loop, apply `subscribeOn(Schedulers.boundedElastic())` to the blocking source.
6. Can two subscriptions to `fromCallable` plus one retry invoke the DAO again? **Yes**; control side effects and data changing between runs.

### Mini Exercise

Write an adapter `Mono<String> loadLegacyProfile(String id)` around the blocking method `legacyClient.loadProfile(id)` such that:
- It does not call the client when creating the Mono.
- Each subscription can reload data.
- The blocking work runs on `boundedElastic`.
- Null is represented as empty, and exceptions are emitted as errors.

Reference solution (inside a class with `legacyClient` declared and Reactor types imported):

```java
Mono<String> loadLegacyProfile(String id) {
    return Mono.fromCallable(() -> legacyClient.loadProfile(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

Test it with a fake client counting calls: before subscription the counter is 0, after the first subscription it is 1, and after the next it is 2. Add cases returning null and throwing an exception to confirm all three possible signals.

## Official Documentation

- [Reactor Core Reference — FAQ: How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html)
- [Reactor Core `Mono` API — `fromCallable`, `defer`, `deferContextual`](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Reactor Core `Schedulers` API](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html)

Remember: **`fromCallable` defers a value-producing computation; `defer` defers creating/choosing a publisher; `subscribeOn(boundedElastic)` is the proper thread boundary when the computation is blocking.**