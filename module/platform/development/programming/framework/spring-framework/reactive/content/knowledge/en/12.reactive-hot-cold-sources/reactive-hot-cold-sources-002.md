# Data Created at Assembly Time vs. Subscription Time

**Module:** Spring Framework – reactive  
**Parent topic:** Hot and cold sources

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish two key moments in Reactor: **pipeline assembly time** and **subscription time**.
2. Explain why `Mono.just(expensiveCall())` invokes the method immediately when creating the publisher, whereas `Mono.defer`, `Mono.fromSupplier`, and `Mono.fromCallable` defer value creation to each subscribe.
3. Properly understand cold and hot `Flux`/`Mono`, including that `Mono.just` holds the value captured at assembly and replays that value to subscribers.
4. Identify state shared via closures versus state created individually per subscription.
5. Distinguish `defer`, `cache`, and `share`; understand how they affect source execution, side-effect invocation counts, replay, and connection lifecycle.
6. Apply these concepts in Spring WebFlux, avoiding accidental retention of stale data, blocking I/O during pipeline assembly, or repeated side effects across multiple subscriptions/retries.

## 1. Two Milestones in a Reactive Sequence

When writing Reactor code, we typically create a `Mono<T>` or `Flux<T>` variable by chaining operators. This action is called **assembly**: the application builds a description of the source and processing pipeline. A pipeline only starts being consumed when a subscriber subscribes, directly or through a framework like Spring WebFlux.

Three stages must be separated:

1. **Assembly time:** Java executes normal expressions, creates publisher objects, and connects operators into a pipeline.
2. **Subscription time:** a subscriber subscribes; the source and operators initialize state needed for the subscription and begin coordinating demand.
3. **Signal time:** `onNext` data, `onError` errors, or `onComplete` completion signals flow through the pipeline.

```text
Java calls method / creates publisher
            |
            v
     ASSEMBLY TIME
  - evaluates arguments of just(...)
  - creates objects / chains operators
  - may run Java side effects immediately
            |
            |  publisher is held
            |  (may not have a subscriber yet)
            v
   subscribe(subscriber)
            |
            v
   SUBSCRIPTION TIME
  - defer/supplier is invoked
  - creates per-subscription state
  - source begins to be consumed
            |
            v
       SIGNAL TIME
  onNext(value) / onError(error) / onComplete()
```

**Lazy** means work is deferred until needed, usually when a subscription occurs. Reactor cannot automatically make every Java expression lazy: if you call a method before passing its result to `Mono.just`, that method has already run.

### 1.1. Common Trap: Mono.just Calls the Method Early

```java
Mono<User> user = Mono.just(userRepository.findByIdBlocking(id));
```

This is an **intentional illustrative snippet**, assuming `findByIdBlocking` returns `User`. Java evaluates the argument to `Mono.just(...)` before calling `just`, so the repository call already happened when the pipeline-building method ran. The publisher merely captures the already-obtained result. If the repository returns `null`, `Mono.just(null)` is invalid and can throw `NullPointerException` right at assembly.

If the controller method runs once per request, the blocking call may happen during request handling, but it still happens **before subscribing to the returned publisher**. If you create this publisher in a constructor or field of a singleton bean, the call may happen once at bean initialization, causing every subsequent request to use the same stale value.

### 1.2. Deferring Value Creation with defer

```java
Mono<User> user = Mono.defer(() ->
        Mono.just(userRepository.findByIdBlocking(id)));
```

`Mono.defer` takes a supplier that creates a publisher. The supplier is only invoked when each subscriber subscribes. Therefore, `findByIdBlocking(id)` executes at subscription time, once per subscription to `user`. However, this call is still **blocking**. `defer` only changes when it runs; it does not move the call to another thread and does not turn synchronous JDBC into nonblocking I/O.

If a reactive API is available, prefer returning the publisher from the repository instead of wrapping a blocking call. If you must use a blocking API, offload the work to an appropriate scheduler and manage resource bounds.

## 2. Mono.just, fromSupplier, fromCallable, and defer

These factory methods look similar but differ in when the value is computed and how null/errors are represented.

| Creation Method | When Does the Expression/Supplier Run? | Null and Exceptions |
| --- | --- | --- |
| `Mono.just(value)` | `value` is already evaluated before calling `just` (assembly) | `null` is rejected; exceptions in the expression occur before the publisher is created. |
| `Mono.fromSupplier(supplier)` | Supplier runs when each subscription requests a value | If supplier returns `null`, the Mono completes empty; exceptions become `onError`. |
| `Mono.fromCallable(callable)` | Callable runs when each subscription requests a value | If callable returns `null`, the Mono completes empty; exceptions are converted to `onError`. |
| `Mono.defer(factory)` | Factory creates a new `Mono` for each subscription | If factory throws, the subscription receives `onError`; if factory returns an empty publisher, the result is empty. |
| `Flux.defer(factory)` | Factory creates a `Publisher`/`Flux` for each subscription | Factory errors become `onError`; factory can return a cold, hot, or shared source. |

### 2.1. Mono.fromSupplier: Deferring a Value

```java
Mono<String> name = Mono.fromSupplier(() -> loadName());
```

The supplier is called when a subscriber needs a value. Each independent subscription can invoke the supplier once and receive a fresh value. If the supplier returns `null`, Reactor represents the result as `Mono.empty()`, without emitting `onNext(null)`.

### 2.2. Mono.fromCallable: When a Method Can Throw Checked Exceptions

```java
Mono<String> contents = Mono.fromCallable(() -> Files.readString(path));
```

`Callable` can throw checked exceptions, making it convenient for wrapping Java APIs such as file reading. Exceptions are turned into reactive error signals instead of having to be caught and rethrown during assembly. However, `Files.readString` is still a blocking operation; to use it in a WebFlux application, move it off the event-loop, for example via `subscribeOn(Schedulers.boundedElastic())`, or use an appropriate asynchronous file/I/O API.

### 2.3. Mono.defer: Deferring Creation of the Entire Publisher

```java
Mono<Account> account = Mono.defer(() -> {
    String requestId = createRequestId();
    return accountService.find(requestId);
});
```

`defer` is useful when the **publisher to return itself** depends on subscription time: generating a request ID, choosing a branch, reading the current configuration value, or creating a new source. For each subscription, the factory is called again.

If you only need a simple value, `fromSupplier`/`fromCallable` is usually shorter and clearer. If you need to construct a different publisher or compose source-creation logic, use `defer`.

### 2.4. Calling the Factory per Subscription Does Not Mean Everything Inside Is Fresh

```java
Mono<String> shared = Mono.just(loadOnce());
Mono<String> deferredButShared = Mono.defer(() -> shared);
```

Both publishers above emit the precomputed value. `deferredButShared` invokes the factory on each subscription, but the factory returns **the same `shared` publisher**. It does not invoke `loadOnce()` again. This is an important point: `defer` defers the factory, but only creates new state/sources if the code inside the factory actually creates them.

## 3. Runnable Java 17+ Example: Observing Execution Timing

The CLI example below uses **Java 17+**, **Maven**, and **Project Reactor Core 3.8.8**. It compares a value evaluated at assembly, a supplier executed per subscription, and a publisher caching its result.

Structure:

```text
assembly-subscription-demo/
├── pom.xml
└── src/main/java/demo/
    └── AssemblySubscriptionDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>assembly-subscription-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
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

### src/main/java/demo/AssemblySubscriptionDemo.java

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public final class AssemblySubscriptionDemo {
    private static final AtomicInteger sequence = new AtomicInteger();

    private static String load(String label) {
        int id = sequence.incrementAndGet();
        System.out.println("load " + label + " #" + id);
        return label + "-" + id;
    }

    public static void main(String[] args) {
        System.out.println("== just ==");
        Mono<String> just = Mono.just(load("just"));
        System.out.println("after assembly");
        System.out.println("A=" + just.block());
        System.out.println("B=" + just.block());

        System.out.println("== defer ==");
        Mono<String> deferred = Mono.defer(
                () -> Mono.just(load("defer")));
        System.out.println("after assembly");
        System.out.println("A=" + deferred.block());
        System.out.println("B=" + deferred.block());

        System.out.println("== fromSupplier ==");
        Mono<String> supplier = Mono.fromSupplier(
                () -> load("supplier"));
        System.out.println("after assembly");
        System.out.println("A=" + supplier.block());
        System.out.println("B=" + supplier.block());

        System.out.println("== cache ==");
        Mono<String> cached = Mono.fromSupplier(
                () -> load("cached")).cache();
        System.out.println("after assembly");
        System.out.println("A=" + cached.block());
        System.out.println("B=" + cached.block());

        Mono<String> empty = Mono.fromSupplier(() -> null);
        System.out.println("supplier null empty=" +
                empty.blockOptional().isEmpty());
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.AssemblySubscriptionDemo
```

**Program stdout** (excluding Maven logs):

```text
== just ==
load just #1
after assembly
A=just-1
B=just-1
== defer ==
after assembly
load defer #2
A=defer-2
load defer #3
B=defer-3
== fromSupplier ==
after assembly
load supplier #4
A=supplier-4
load supplier #5
B=supplier-5
== cache ==
after assembly
load cached #6
A=cached-6
B=cached-6
supplier null empty=true
```

### Explanation of Each Case

- **just:** `load("just")` is called by Java before `Mono.just` is created, so the log appears right during assembly. The publisher captures the string `"just-1"`; both A and B receive the same captured value without calling the method again.
- **defer:** pipeline assembly has not called `load("defer")` yet. Each `block()` creates a subscription, the factory runs, and a new value is computed: `defer-2` then `defer-3`.
- **fromSupplier:** the supplier has not run when the Mono is created. On each subscribe, it runs once and returns a fresh result.
- **cache:** the first subscriber triggers the supplier and caches the terminal value; the next subscriber receives the cached result without calling the supplier again.
- **null:** `fromSupplier` returns null so the Mono is empty; `blockOptional()` indicates there is no value. There is no `onNext(null)`.

`block()` in this example is only for demonstration at a synchronous CLI boundary. Each call to `block()` creates a separate subscription. Do not copy this waiting pattern into WebFlux controllers.

## 4. Flux Also Has Assembly Time and Subscription Time

The same rules apply to `Flux`. Example:

```java
Flux<Integer> eager = Flux.just(loadFirst(), loadSecond());
Flux<Integer> lazy = Flux.defer(() ->
        Flux.just(loadFirst(), loadSecond()));
```

This is an **illustrative snippet**: both `loadFirst` and `loadSecond` are called immediately when Java evaluates arguments for `Flux.just`. With `Flux.defer`, both methods are called when the factory runs for each subscription.

Different sources have distinct behaviors:

| Factory | When Data Is Created | Notes |
| --- | --- | --- |
| `Flux.just(a, b, c)` | Expressions `a`, `b`, `c` are evaluated at assembly | Captures available values and replays them to each subscriber. |
| `Flux.range(start, count)` | Sequence computed per subscription | Each subscription has its own emission progress. |
| `Flux.fromIterable(iterable)` | Obtains iterator upon subscribe | Typically creates a new iterator per run; the iterable must support multiple traversals for safe repeated subscriptions. |
| `Flux.defer(factory)` | Invokes factory per subscription | Factory can create a new source or return a shared source. |
| `Flux.generate(stateSupplier, generator)` | State supplier creates state per subscription | Useful when an independent per-subscriber state machine is needed. |
| `Flux.create(callback)` | Source callback executes per subscription | Must carefully manage listener registration/cancellation and backpressure strategy. |

Do not conclude every `Flux` is cold merely because its type is `Flux`. Semantics depend on the underlying publisher, transforming operators, and how connections are managed.

### 4.1. Per-Subscription State with defer

```java
Flux<Integer> isolated = Flux.defer(() -> {
    AtomicInteger counter = new AtomicInteger();
    return Flux.range(1, 3)
            .map(ignored -> counter.incrementAndGet());
});
```

This is an **illustrative snippet**; `AtomicInteger` must be imported. On each subscribe, the factory creates a new counter, so each subscriber can receive `1, 2, 3`. Conversely:

```java
AtomicInteger sharedCounter = new AtomicInteger();
Flux<Integer> sharedState = Flux.range(1, 3)
        .map(ignored -> sharedCounter.incrementAndGet());
```

The counter sits outside the factory, so it is captured and shared by all subscriptions. The first run may receive `1, 2, 3`; the next `4, 5, 6`. `AtomicInteger` only makes the increment operation thread-safe under contention; it does **not** turn shared state into per-subscription state. If data must be isolated per request/subscriber, create the state inside `defer` or the corresponding state supplier.

## 5. Cold and Hot Publishers: Relation to Data Creation Timing

### 5.1. Cold Publisher: Work Is Performed per Subscriber

A cold publisher typically begins creating or reading data when a subscriber subscribes. Each independent subscription can usually receive the entire logical sequence from the beginning:

```java
Flux<Integer> cold = Flux.defer(() -> {
    System.out.println("create source for subscriber");
    return Flux.range(1, 3);
});
```

This is an **illustrative snippet**. On each subscribe, the factory logs and creates a new range source. Subscriber A receives `1, 2, 3`; B subscribing later also starts from `1`. Database queries, HTTP calls, or computations in a cold source may repeat for each subscription.

**Cold does not mean it automatically runs on a separate thread.** A synchronous cold publisher can execute its work right on the thread calling subscribe/request. Asynchronous/nonblocking behavior requires an appropriate source and operators.

### 5.2. Hot Publisher: A Source That Can Operate Independently of Subscribers

A hot publisher can emit data independently of when a subscriber subscribes. Late subscribers may miss already-emitted events unless the source has buffering/replay/caching. Typical examples are event streams from sensors, message buses, or multicast `Sinks.Many`.

In Reactor, `Mono.just(value)` is a subtle case: it **captures the value at assembly time**, then emits that value to subscribers. Reactor documentation classifies `just` as a hot example in the sense that the value is fixed from assembly, even though the `onNext` signal is only sent when subscribed. It is not like a live multicast event source continuously emitting on its own.

### 5.3. Quick Comparison

| Property | Cold | Hot |
| --- | --- | --- |
| When the source creates/emits data | Usually upon subscription | Can be before or independent of subscription |
| Late subscriber | Usually receives from the beginning | May only receive events from the time of joining |
| Side effects | May repeat per subscription | May share one upstream/side effect |
| Progress | Usually separate per subscription | May be the shared progress of the source |
| Replay | Usually re-emitted via re-execution | Only when the source/operator has a replay/cache policy |
| Examples | `Flux.range`, `Mono.defer` returning a cold source | Multicast `Sinks.Many`, `share` while connected, `cache` replay |

There is no simplistic rule such as “a Flux object is always cold” or “every Mono.just emits immediately”. Ask: **when is the value computed, when does the source actually start, and which part does a late subscriber receive?**

## 6. How Do cache, share, and defer Change Semantics?

### 6.1. cache: Execute the Source Then Replay Cached Signals

`cache()` turns a source into a publisher that retains signals for later subscribers to receive. With `Mono.cache()`, the terminal result (value, empty, or error) is cached per the API's semantics; subsequent subscribers do not normally re-invoke upstream. There are TTL overloads to limit how long results are kept. With `Flux.cache()`, check history/TTL policies and memory bounds: caching the entire history of an infinite stream can cause unbounded memory growth.

```java
Mono<Config> config = configClient.fetch()
        .cache(Duration.ofMinutes(1));
```

This is an **illustrative snippet**; `java.time.Duration` must be imported. The first subscriber triggers the source; within the cache duration, subsequent subscribers receive the cached result. Caching is a choice about data freshness and sharing, not just a speed optimization. For authorized or per-user data, ensure the cache key/scope is right; a cache that does not distinguish users can leak data.

### 6.2. share: Multiple Subscribers Sharing One Connected Upstream

`share()` allows multiple subscribers to share one source during a common connection window. It is commonly understood via the `publish().refCount(1)` model: upstream connects when a subscriber needs it and may disconnect when no subscribers remain. Subscribers joining later may miss previously emitted elements; `share()` does not replay history by default.

```java
Flux<Long> sharedTicks = Flux.interval(Duration.ofSeconds(1))
        .share();
```

This is an **illustrative snippet**; `Duration` and `Flux` must be imported. Two simultaneously active subscribers can observe the same tick cadence from the moment they join, instead of each having an independent timer. Late subscribers are not guaranteed to receive past ticks. Reconnect lifecycle after zero subscribers depends on the specific operator/version semantics and source state.

### 6.3. defer Does Not Mean Cold

```java
Flux<Event> deferred = Flux.defer(() -> sharedEventBus);
```

This is an **illustrative snippet**; `sharedEventBus` is a shared hot source. `defer` invokes the factory per subscription, but the factory returns the same hot source. Thus, subscriptions still join a shared event source; it does not create a new bus.

To create independent sources, the factory must create independent sources:

```java
Flux<Integer> perSubscriber = Flux.defer(() ->
        Flux.range(1, 3));
```

The snippet above creates a new `Flux.range` per subscription. What decides is **the object and semantics returned by the factory**, not merely the keyword `defer`.

### 6.4. Sinks: Application-Emitted Hot Sources

Reactor `Sinks.Many<T>` lets the application actively emit events. Variants like `multicast()`, `unicast()`, and `replay()` have different subscriber/buffering policies. Choose a sink based on requirements: a single consumer, multiple active consumers, or history replay. Emission results such as `OK`, `FAIL_OVERFLOW`, and `FAIL_NON_SERIALIZED` must be handled; do not ignore overflow or emit concurrently against the rules.

Sinks do not automatically make any stream durable. If you need zero message loss when a process crashes, you need a broker/durable queue or persistence; an in-memory sink does not replace that mechanism.

## 7. Multiple Subscriptions and Side Effects

A cold publisher can re-run upstream logic on every subscribe. This is often desirable when fresh data is needed, but dangerous if the side effect writes an order, sends an email, or charges money.

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> request = Mono.fromSupplier(() -> {
    calls.incrementAndGet();
    return "result";
});

request.subscribe();
request.subscribe();
```

This is an **illustrative snippet**; proper subscriber/error handling is required. The supplier is called twice because there are two subscriptions. With side effects, each subscription can perform the action once; do not assume a publisher runs only once just because it is assigned to a variable.

### 7.1. Retries Also Create New Subscriptions

```java
Mono<Result> result = remoteCall()
        .retry(2);
```

`retry(2)` can re-subscribe to upstream up to two times after errors, in addition to the initial attempt. If `remoteCall` is cold, the upstream call can be executed up to three times. Consider timeouts, backoff, idempotency, and which error types are retried. With non-idempotent writes, blind retries can cause duplicate side effects.

### 7.2. Creating Only One Subscription for a Shared Result

If a stream needs to be consumed in multiple places, decide explicitly whether they need the same single execution or one execution each:

- **Each subscriber executes on its own:** keep the source cold and accept repeated side effects/cost.
- **Share while running:** use `share`/`publish().refCount(...)` with an appropriate lifecycle policy.
- **Replay a completed result:** use `cache` with an appropriate bounded TTL/history.
- **An independently owned background job:** start it in a component with a clear lifecycle, managing `Disposable`/shutdown and errors; do not spawn random background subscriptions inside a controller.

Do not use `cache()` merely to “patch” multiple subscribe calls without understanding how stale the data can be and whether the cache is safe across users.

## 8. Assembly Time in Spring WebFlux

### 8.1. Creating Publishers in Controllers

A handler can create a publisher when invoked for a request:

```java
@GetMapping("/profile")
public Mono<ProfileDto> profile(@RequestParam String id) {
    return profileService.findById(id);
}
```

This is an **illustrative controller snippet**; Spring imports and `ProfileDto`/`profileService` definitions are needed. The controller creates and returns a publisher; WebFlux then consumes the publisher to write the response. If `profileService.findById(id)` returns a cold publisher, subscribing for that request triggers the read operation.

### 8.2. Using defer for Values That Must Be Read at Subscription Time

```java
@GetMapping("/request-time")
public Mono<String> requestTime() {
    return Mono.defer(() ->
            Mono.just(Instant.now().toString()));
}
```

This is an **illustrative controller snippet**; `Instant` must be imported. The time is read when the subscriber subscribes. If written as `Mono.just(Instant.now().toString())`, the time is fixed when the publisher-creating method runs. The difference matters when a publisher is constructed early and held before subscribing, or shared across multiple consumers.

### 8.3. Avoiding Request-Specific State in Singleton Publisher Fields

Dangerous example:

```java
@Component
class BadService {
    private final Mono<String> startupValue =
            Mono.just(loadConfigurationNow());
}
```

If the singleton bean is created at startup, `loadConfigurationNow()` runs once during bean initialization; every later subscriber receives the same captured value. This may be intended if it is immutable startup configuration, but wrong if the value must be fresh per request or refreshed.

If current configuration must be retrieved:

```java
@Component
class ConfigService {
    Mono<String> currentValue() {
        return Mono.defer(() -> Mono.just(loadCurrentConfiguration()));
    }
}
```

This is an **illustrative snippet**. If `loadCurrentConfiguration` is blocking, handle schedulers/I/O properly. If the data should be cached for a period, use a cache with TTL and a refresh policy instead of re-calling without bounds.

### 8.4. Request Context and Per-Request Data

Correlation/request ID data should be attached to the request lifecycle, typically via Reactor `Context` or integrated tracing mechanisms. Do not capture a mutable singleton field to hold the current request's ID: concurrent requests can overwrite each other. `deferContextual` lets you read context per subscription:

```java
Mono<String> requestId = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "unknown")));
```

This is an **illustrative snippet**; context is provided upstream via `contextWrite`. `Context` is attached per subscription, not a ThreadLocal shared across requests.

## 9. Lazy Does Not Mean Nonblocking

Three concepts must be separated:

- **Lazy:** work only starts upon subscription or when the supplier is invoked.
- **Asynchronous:** the caller does not have to wait for work to finish on the same call stack; results arrive later via callbacks/signals.
- **Nonblocking:** threads are not held waiting on I/O; the runtime can use that thread for other work while waiting.

`Mono.fromCallable(() -> jdbcTemplate.queryForObject(...))` may be lazy, but JDBC is still blocking when the callable runs. `Mono.defer(() -> Mono.just(blockingCall()))` also defers the call without making it nonblocking. For blocking APIs that must be used, they can be isolated:

```java
Mono.fromCallable(() -> legacyClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
```

This is an **illustrative snippet**; Reactor imports and `legacyClient` definition are needed. `boundedElastic` is for bounded blocking work, not an excuse to wrap the entire application in blocking calls. Prefer WebClient, R2DBC, or reactive APIs whenever possible.

### 9.1. Supplier Runs Only When Appropriate Demand Exists

With `Mono.fromSupplier`, the supplier is not necessarily called just because you created a Mono variable. It runs when the subscription starts consuming the value according to demand. If the subscriber cancels before the supplier executes, the supplier may not run. For simple synchronous sources, the supplier usually runs right during subscribe/request; with asynchronous operators, execution timing depends on the pipeline.

## 10. Choosing a Factory by Goal

| Need | Consider | Reason |
| --- | --- | --- |
| Already have an immutable value and want to replay it | `Mono.just(value)` / `Flux.just(values)` | Value is captured at assembly time. |
| Want to call a supplier per subscription | `Mono.fromSupplier` | Simple factory producing a single value. |
| Method can throw a checked exception or return null | `Mono.fromCallable` | Turns exceptions into onError, null into empty. |
| Want to create/choose a new publisher per subscription | `Mono.defer` / `Flux.defer` | Defers source/pipeline creation. |
| Want a separate state machine per subscription | `Flux.generate(stateSupplier, generator)` | State supplier is invoked for each subscription. |
| Want multiple subscribers to share a running source | `share` / `publish().refCount(...)` | Shares upstream over the connection lifecycle. |
| Want to replay emitted results/signals | `cache` / replay sink | Later subscribers receive retained data; TTL/history must be managed. |
| Want to emit application-controlled hot events | `Sinks.Many` | Application actively emits, with multicast/unicast/replay policies. |

## 11. Common Pitfalls

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Thinking `Mono.just(methodCall())` is lazy | Java calls the method before calling `just` | Use `fromSupplier`, `fromCallable`, or `defer`. |
| Using `Mono.just(null)` | Reactor does not allow null as onNext | Use `justOrEmpty`/`fromSupplier` null semantics and handle empty. |
| Thinking `defer` always creates a new cold source | The factory may return the same hot/cached publisher | Check what publisher is actually created/returned inside the supplier. |
| Placing a mutable counter outside defer and expecting per-subscriber state | All subscribers capture the same object | Create the counter inside the factory/state supplier. |
| Using `fromCallable` and concluding I/O is now nonblocking | Callable may still call blocking JDBC/file/network | Use reactive APIs or isolate on an appropriate scheduler. |
| Creating a publisher in a singleton field with a value needing refresh | Value is captured at startup/assembly and becomes stale | Create the publisher per request or cache with explicit TTL/refresh. |
| Subscribing twice and thinking the source runs only once | A cold publisher can execute upstream twice | Control subscription boundaries; use share/cache only when semantics permit. |
| Using `cache()` for per-user data without key/scope | Can return the wrong user's data or stale data | Cache by key, permissions, TTL, and safe scope. |
| Using `share()` and expecting late subscribers to get history | Share does not replay history by default | Choose cache/replay if needed, with memory bounds. |
| Treating `Mono.just` as a live event bus | It captures an assembly value, not a continuous multicast event source | Use an appropriate sink/broker/hot Flux. |
| Thinking retry only re-invokes an operator without rerunning the source | Retry resubscribes to upstream | Verify idempotency and side effects. |
| Using a mutable field in a singleton to store the current request | Concurrent requests can overwrite each other's data | Use method parameters and Reactor Context. |
| Calling `block()` inside a WebFlux controller | Blocks HTTP handling threads | Return the publisher for WebFlux to consume. |

## 12. Self-Check Questions

**Question 1.** When does `load()` run in `Mono.just(load())`?  
**Answer:** Immediately when Java assembles the expression, before `Mono.just` is called. The computed value is captured into the publisher.

**Question 2.** If the same `Mono.defer(() -> Mono.just(load()))` is subscribed to twice, how many times does `load()` run?  
**Answer:** Twice, once for each executed subscription, unless an external operator/cache alters semantics or a subscription is cancelled before the supplier runs.

**Question 3.** What does `Mono.fromSupplier(() -> null)` emit?  
**Answer:** It emits no `onNext`; it completes empty (`Mono.empty()`).

**Question 4.** Does `Mono.defer(() -> sharedHotPublisher)` automatically turn the publisher into a cold one?  
**Answer:** No. The factory runs per subscription, but the returned publisher is still the shared hot source.

**Question 5.** Do two subscribers sharing `Mono.just(value)` receive two newly computed objects?  
**Answer:** No. The expression producing `value` runs at assembly; both receive the captured value. If value is mutable, they may reference the same object.

**Question 6.** How does `cache()` differ from `share()` in its primary goal?  
**Answer:** Cache retains and replays signals per its caching policy; share coordinates subscribers with a connected upstream without replaying history to latecomers by default.

**Question 7.** Is `fromCallable(() -> jdbcCall())` nonblocking?  
**Answer:** No. It only defers the call and converts exceptions into signals. JDBC remains blocking; a reactive API or appropriate scheduler is needed.

**Question 8.** What timestamp will a publisher created in a singleton constructor via `Mono.just(Instant.now())` emit?  
**Answer:** The time when the constructor/assembly ran, typically bean initialization time, not the time each request subscribes.

**Question 9.** Why can `retry(2)` cause an HTTP call to be executed multiple times?  
**Answer:** Retry resubscribes to upstream. If the source is cold, the supplier or per-subscription request runs again. Idempotency and a clear retry policy are needed.

## Key Takeaways

- **Assembly time:** Java evaluates arguments and builds publishers. `Mono.just(methodCall())` calls the method immediately; the value is already captured.
- **Subscription time:** `defer`, `fromSupplier`, and `fromCallable` execute the deferred part when the publisher is consumed. Each subscription can create fresh values/state.
- **Cold/hot are semantics of the source and connection:** `just` captures at assembly; `defer` does not itself turn a hot publisher cold; `share` shares a connected source; `cache` replays stored signals.
- **State in closures can be shared:** for per-subscriber isolation, create state inside the factory/state supplier. Multiple subscriptions or retries can repeat side effects.
- **Lazy does not mean nonblocking:** defer only changes execution timing; blocking I/O remains blocking.
- In Spring WebFlux, return the publisher and let the framework manage HTTP subscriptions. Choose cache/share/defer based on data freshness, request scope, access permissions, and source lifecycle.

### References

1. [Project Reactor – Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html): distinguishing hot/cold, `just`, and `defer`.
2. [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `just`, `defer`, `fromSupplier`, `fromCallable`, `cache`.
3. [Project Reactor – Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): Flux sources, `defer`, `generate`, `share`, and `cache`.
4. [Project Reactor – Creating and Subscribing to a Flux or Mono](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html): assembly, subscription, and ways to subscribe.
5. [Project Reactor – Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): hot sources and sink policies.
6. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive HTTP handling and publisher integration.
