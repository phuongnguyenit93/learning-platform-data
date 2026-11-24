# Isolating Blocking Calls with `Mono.fromCallable` and `Schedulers.boundedElastic()`

## 1. Why Must Blocking Operations Be Isolated in Spring WebFlux?

Spring WebFlux and Project Reactor support processing data streams with `Mono` and `Flux`. On event-loop servers such as Reactor Netty, a small number of threads must serve very many connections. If an event-loop thread is held while **waiting on a blocking operation** (synchronous JDBC, synchronous HTTP libraries, `Thread.sleep`, blocking file access, sync-only SDKs), other work sharing that thread is delayed as well.

A common example:

```java
// ANTI-EXAMPLE: synchronous/blocking right when the controller is called.
@GetMapping("/customers/{id}")
public Mono<CustomerDto> customer(@PathVariable long id) {
    Customer customer = blockingRepository.findById(id); // blocks current thread
    return Mono.just(toDto(customer));
}
```

This is **illustrative code inside an existing WebFlux application**, not a standalone runnable program. Even though the return type is `Mono`, `findById` **executes immediately** before `Mono.just(...)` is created. If the method runs on the event loop, the event loop itself must wait on I/O.

When forced to integrate a sync API, the common Reactor design pattern is:

```java
Mono<CustomerDto> result =
        Mono.fromCallable(() -> blockingRepository.findById(id))
            .subscribeOn(Schedulers.boundedElastic())
            .map(this::toDto);
```

The two parts of the pattern solve **two different problems**:

1. **`Mono.fromCallable(...)`** wraps the synchronous call inside a **lazy** `Mono` source: `Callable.call()` executes only when subscribed to and requested, instead of running right when assembling the pipeline.
2. **`.subscribeOn(Schedulers.boundedElastic())`** shifts upstream subscription/request activity and execution of the source `Callable` onto a scheduler intended for potentially blocking tasks, avoiding holding the subscribing thread (such as the event loop) while waiting on I/O.

`fromCallable` alone **does not switch threads**. `boundedElastic` alone **does not turn blocking I/O into non-blocking**. Combining both properly creates the appropriate execution boundary in this scenario.

## 2. `fromCallable`: Deferring Function Invocation

API shape sketch:

```java
static <T> Mono<T> Mono.fromCallable(
        java.util.concurrent.Callable<? extends T> supplier);
```

This is a **generic explanatory signature**, not a Java method you can declare verbatim in a user class. The point of `Callable<T>` is that it takes **no arguments**, returns a result `T`, and may throw `Exception`.

Compare:

```java
// Blocking call runs first, then Mono is created: NOT isolated.
Mono<User> wrong = Mono.just(blockingUserDao.load(id));

// Lazy source created: load(id) is not called yet during assembly.
Mono<User> lazy = Mono.fromCallable(() -> blockingUserDao.load(id));

// Lazy + execution scheduling isolation:
Mono<User> isolated = Mono.fromCallable(() -> blockingUserDao.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

`blockingUserDao`, `User`, and `id` are hypothetical application components. The second option avoids immediate invocation, yet if subscribed on an event loop **without an appropriate `subscribeOn`**, the blocking call can still run on the event loop.

Properties of `Mono.fromCallable` to remember:

- **Each subscription** to a cold source created with `fromCallable` can invoke the `Callable` again. Do not treat it as a result cache or an *exactly once* guarantee.
- If `Callable` returns a non-`null` object `T`, the source emits at most one `onNext(T)` followed by `onComplete`.
- If `Callable` returns `null`, `Mono.fromCallable` completes **empty**; it does not emit `onNext(null)`. This is Reactor's way of representing an absent value, though you must check whether business logic permits "not found."
- If `Callable` throws an exception, the source emits **`onError`**, not an error value of type `T`.
- `fromCallable` cannot make an inherently blocking operation asynchronous; it only lets Reactor **place** that operation's execution in the right context.

Example of a repository returning `null` when not found:

```java
Mono<User> user = Mono.fromCallable(() -> blockingDao.find(id))
        .subscribeOn(Schedulers.boundedElastic())
        .switchIfEmpty(Mono.error(
                new IllegalArgumentException("User not found")
        ));
```

`switchIfEmpty` handles the **no-value case**; it does not handle exceptions thrown by the DAO. In a WebFlux controller, "not found" can be mapped to HTTP 404 via `ResponseStatusException` per project conventions.

## 3. `boundedElastic`: Moving Blocking Operations to Bounded Resources

`Schedulers.boundedElastic()` is a shared scheduler in Project Reactor suited for **unavoidable blocking tasks or synchronous I/O**. The word "bounded" reminds us that worker/thread counts and queued work are **capped and configurable**, unlike assuming unbounded threads are spawned as requests grow.

Diagram:

```text
HTTP event-loop thread
     |
     | subscribe(result)
     v
Mono.fromCallable(blockingCall)
     |
     | subscribeOn(boundedElastic)
     v
boundedElastic worker ── calls blockingCall ── waits on I/O ── receives T
     |
     | onNext(T) or onError
     v
Downstream operators (unless another scheduler boundary exists)
     |
     v
Subscriber / WebFlux response-writing mechanism
```

This is a **logical diagram** and does not claim every downstream callback runs on the same thread in every pipeline. `publishOn`, other async Publishers, and the runtime can change the actual thread.

Practical limits:

- A scheduler **cannot make a blocking call faster**. It keeps that wait time from holding an event-loop thread and lets other requests keep being served.
- `boundedElastic()` **does not provide infinite capacity**. As blocking tasks and queues grow, latency still rises, work can wait for workers, and tasks will eventually be rejected once configured limits are exceeded.
- `boundedElastic` does not create connection pools, network timeouts, or concurrency limits for target APIs. If a database has only 10 connections, launching thousands of blocking tasks can still leave many waiting on a connection.
- Use the **shared scheduler** `Schedulers.boundedElastic()` in normal scenarios; do not create a new dedicated scheduler per HTTP request.
- If you create a custom lifecycle-managed scheduler, such as `Schedulers.newBoundedElastic(...)`, the application must **dispose** of it at shutdown to avoid resource leaks. Do not dispose the global shared scheduler after each request.

In a system with genuinely non-blocking I/O APIs (such as a reactive database driver or reactive HTTP client), you should generally keep those reactive APIs; wrapping a non-blocking task in `fromCallable` can distort types or create an unnecessary `Mono<Mono<T>>`.

## 4. How `subscribeOn` and `publishOn` Differ at a Blocking Boundary

This is the easiest part to implement wrongly.

**Correct:**

```java
Mono<Result> result = Mono.fromCallable(() -> blockingService.fetch())
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::convert);
```

`subscribeOn` affects upstream subscription, allowing the source `Callable` to run on `boundedElastic`. Without a subsequent `publishOn` or other async boundary, trailing `map` operators on this simple source typically run on that worker too.

**Wrong intent if using `publishOn` alone after the source:**

```java
Mono<Result> result = Mono.fromCallable(() -> blockingService.fetch())
        .publishOn(Schedulers.boundedElastic())
        .map(this::convert);
```

`publishOn` shifts **downstream signals after its position** to the scheduler, yet **does not move execution of the preceding `fromCallable` source** there. If subscription arrives from the event loop, `blockingService.fetch()` can still block the event loop before `publishOn` receives any data.

**A practical rule:** for a **blocking source** wrapped in `Mono.fromCallable`, place `.subscribeOn(Schedulers.boundedElastic())` right next to the source so intent is clear. In a simple chain, `subscribeOn` still affects the source even after `map`, but placing it near the source avoids hiding the blocking boundary and simplifies code review.

Comparison table:

| Component | Primary effect | Does not guarantee by itself |
|---|---|---|
| `Mono.fromCallable` | Defers synchronous call until subscribe | Does not pick another thread |
| `subscribeOn(scheduler)` | Chooses scheduler for subscription and upstream | Does not turn blocking into non-blocking |
| `publishOn(scheduler)` | Switches downstream signal processing from its position | Does not move a preceding blocking source to the scheduler |
| `Schedulers.boundedElastic()` | Provides bounded workers suited for blocking | Does not grant infinite capacity or set external API timeouts |

If a pipeline contains multiple `subscribeOn` calls, subscriptions can be scheduled across layers, though the effective `subscribeOn` closest to the source typically governs the source's execution context. Avoid scattering multiple `subscribeOn` calls arbitrarily, as it makes execution flow hard to analyze.

## 5. Standalone Runnable Java 17+ Example

For clear observation, this example uses `Thread.sleep(...)` to **simulate blocking I/O**. `block(Duration)` is used **only in `main()` of the console program** to wait for results and produce deterministic stdout; in WebFlux handlers/controllers, never use this wait style to assemble data.

Project structure:

```text
reactor-blocking-isolation/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-blocking-isolation</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.io.IOException;
import java.time.Duration;
import java.util.Locale;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class Main {
    public static void main(String[] args) {
        Thread caller = Thread.currentThread();

        // Create lazy source. At this point Callable has not run yet.
        Mono<String> isolated = Mono.fromCallable(() -> {
                    System.out.println(
                            "callable-on-main: "
                                    + (Thread.currentThread() == caller)
                    );
                    Thread.sleep(40); // simulate blocking I/O
                    return "  hello reactor  ";
                })
                .subscribeOn(Schedulers.boundedElastic())
                .map(String::trim)
                .map(s -> s.toUpperCase(Locale.ROOT));

        System.out.println("assembled");

        // block only in console demo program; do not use in WebFlux.
        String value = isolated.block(Duration.ofSeconds(5));
        System.out.println("result: " + value);

        Mono<String> recovered =
                Mono.<String>fromCallable(() -> {
                            throw new IOException("backend offline");
                        })
                        .subscribeOn(Schedulers.boundedElastic())
                        .onErrorResume(
                                IOException.class,
                                error -> Mono.just("fallback")
                        );

        System.out.println(
                "error result: "
                        + recovered.block(Duration.ofSeconds(5))
        );
    }
}
```

From `reactor-blocking-isolation/`, with Maven and JDK 17+:

```bash
mvn -q compile exec:java
```

Program stdout during normal execution:

```text
assembled
callable-on-main: false
result: HELLO REACTOR
error result: fallback
```

Line-by-line explanation:

1. `assembled` appears first because `Mono.fromCallable` **has not run `Callable`** when building the pipeline.
2. `callable-on-main: false` shows the blocking function ran on a `boundedElastic` worker, different from the `main` thread.
3. `result: HELLO REACTOR` proves `map` received the value after `Callable` returned and transformed it. Downstream operators do not call the blocking logic again.
4. `IOException` is converted into `onError`; `onErrorResume(IOException.class, ...)` turns that error signal into the fallback value `fallback`.

The example uses `Thread.sleep` **only for learning**. In a real project, place synchronous calls with realistic time limits inside the Callable, such as JDBC or sync SDKs.

**Conditions for this output:** the machine is not overloaded beyond the five-second timeout and the scheduler works normally. Under heavy load, `.block(Duration)` in the demo could throw a timeout error; that is necessary behavior to avoid waiting indefinitely, not a guaranteed alternate stdout order.

## 6. Reading Events Accurately at Each Stage

Suppose an endpoint receives a request:

```text
T0: event loop calls controller; controller returns Mono describing the work
T1: server subscribes to Mono when preparing the response
T2: subscribeOn moves source subscription to boundedElastic
T3: boundedElastic runs Callable, waiting on blocking I/O
T4: result is emitted via onNext(T), map(T->R)
T5: server consumes R and completes response, or handles onError
```

**Benefit:** from T3 to T4, the event loop does not sit waiting on this blocking call. It keeps serving other work. However, if too many Callables wait simultaneously, boundedElastic and the target API can still stall; the model does not erase resource limits.

**Subscription lifecycle:** if the same cold `Mono.fromCallable(...)` is subscribed to twice, the Callable can run **twice**. If `.retry(2)` is added, an error can cause multiple retries of the synchronous operation; consider idempotency when operations have side effects, especially writes or payments. If results must be shared, that is a separate decision requiring evaluation of cache lifecycle, errors, and per-user data.

## 7. Usage Pattern in a Spring WebFlux Service

Suppose a `LegacyCustomerClient` only provides a synchronous method:

```java
Customer findCustomer(long id); // may wait on I/O and throw an exception
```

A WebFlux service can **return a Publisher** instead of blocking in the controller:

```java
// Illustrative code depending on project Customer, CustomerDto, LegacyCustomerClient.
@Service
class CustomerService {
    private final LegacyCustomerClient legacyClient;

    CustomerService(LegacyCustomerClient legacyClient) {
        this.legacyClient = legacyClient;
    }

    Mono<CustomerDto> find(long id) {
        return Mono.fromCallable(() -> legacyClient.findCustomer(id))
                .subscribeOn(Schedulers.boundedElastic())
                .map(customer -> new CustomerDto(
                        customer.getId(),
                        customer.getName()
                ));
    }
}
```

The controller simply returns `Mono<CustomerDto>`:

```java
// Illustrative code in a Spring WebFlux application; requires appropriate imports.
@RestController
class CustomerController {
    private final CustomerService service;

    CustomerController(CustomerService service) {
        this.service = service;
    }

    @GetMapping("/customers/{id}")
    public Mono<CustomerDto> get(@PathVariable long id) {
        return service.find(id);
    }
}
```

Both snippets are **application-dependent integration code**, not standalone runnable files; Spring Web annotations, `Mono`, and `Schedulers` imports are required. Here the controller does not call `.subscribe()` or `.block()`: Spring WebFlux manages Publisher subscription and HTTP output. If the DAO returns `null` for a missing ID, `Mono.fromCallable` completes empty; define an explicit **404 policy** if required by business rules, such as `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)))`.

An easily overlooked point: if `legacyClient.findCustomer(id)` spawns its own threads, uses asynchronous callbacks, or returns a `CompletableFuture`, integration differs. `fromCallable` fits best when a **sync function directly returns a result `T`**. Do not wrap an already-reactive `Mono` in `fromCallable` creating an unnecessary `Mono<Mono<T>>`.

## 8. Concurrency: Why Must the Number of Blocking Calls Be Bounded?

Suppose 100 items must be loaded via a sync library. Use `flatMap` with an explicit concurrency bound:

```java
// Illustrative code: legacyClient.load(id) is a blocking call returning Item.
Flux<Item> items = Flux.range(1, 100)
        .flatMap(
                id -> Mono.fromCallable(() -> legacyClient.load(id))
                        .subscribeOn(Schedulers.boundedElastic()),
                4
        );
```

In this setup, `flatMap` strives to keep at most 4 **active inner Publishers** at a time, thereby limiting how many blocking calls execute concurrently within this chain. The value `4` is an example, not a universally optimal setting.

Factors to weigh:

- **Concurrency** must fit the sync JDBC/HTTP pool size, traffic, I/O duration, CPU capacity, and target service limits.
- If results must stay in exact ID order, `flatMap` can emit in completion order, so use `concatMap` (sequential) or consider `flatMapSequential` with controlled concurrency.
- `flatMap` and `boundedElastic` can schedule multiple tasks together; do not assume there are always exactly four threads or four connections at every instant.
- Even if a single request uses concurrency 4, total concurrent HTTP requests can cause the **whole application** to issue many sync calls. Control load at the service and target-API level, not just in one local pipeline.

Example observation via logging:

```java
Mono<Item> source = Mono.fromCallable(() -> {
            System.out.println("thread: " + Thread.currentThread().getName());
            return legacyClient.load(id);
        })
        .subscribeOn(Schedulers.boundedElastic());
```

Actual worker names are not fixed; do not write tests asserting an exact string like `boundedElastic-1`. This is observation code, not an API guaranteeing thread-naming conventions.

## 9. Error Handling, Timeouts, and Cancellation

### 9.1. Errors Are Reactive Signals

Exceptions inside a Callable automatically become `onError`. Example:

```java
Mono<Response> result = Mono.fromCallable(() -> syncClient.get())
        .subscribeOn(Schedulers.boundedElastic())
        .onErrorResume(ExternalUnavailableException.class,
                error -> Mono.just(Response.cached()));
```

This is illustrative code with application types. Only fall back when it is a meaningful business decision; do not swallow every exception into "no data." If downstream needs error information, let `onError` propagate and use Spring's error-handling mechanisms.

### 9.2. Reactor Timeouts Do Not Replace Sync Library Timeouts

```java
Mono<Response> result = Mono.fromCallable(() -> syncClient.get())
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(2));
```

When waiting exceeds the duration, `timeout` can cancel the upstream subscription and emit a timeout error downstream. Yet **canceling a subscription does not guarantee** immediately aborting every blocking native call, socket, or sync library. Some operations support interruption; others do not.

Configure timeouts inside the **sync library itself** (connection timeout, socket/read timeout, statement timeout, etc.) aligned with the HTTP deadline, while also considering Reactor-side timeouts to control client experience.

### 9.3. `cancel()` Is Not `Thread.stop()`

When an HTTP client disconnects, downstream may cancel. Reactor attempts to cancel related work per contract, but there is no guarantee that blocking calls ignoring interruption stop immediately. Therefore:

- Do not assume `cancel()` rolls back a started transaction or undoes already-completed side effects.
- Design write operations to be idempotent when retries or client reconnects occur.
- Ensure DB/HTTP resources are properly closed using safe libraries and patterns, even on timeout or error.
- Avoid holding blocking workers indefinitely by enforcing real timeouts inside the client/DAO.

### 9.4. Can `onErrorMap`, `retryWhen`, and `doFinally` Be Used?

Yes, under the right conditions:

- `onErrorMap` translates technical errors into clear business errors.
- `retryWhen` can **re-subscribe and re-run the Callable**, so limit retries, apply proper backoff, and verify idempotency.
- `doFinally` is useful for observing termination via complete/error/cancel. It does not replace resource cleanup if the blocking source does not manage its own resources properly.

## 10. Distinguishing from Similar Alternatives

| Need | Approach | Why |
|---|---|---|
| Synchronous function returning `T` that may block | `Mono.fromCallable(...).subscribeOn(boundedElastic())` | Lazy + runs call on an appropriate scheduler |
| Run synchronous task with no return value | `Mono.fromRunnable(...).subscribeOn(boundedElastic())` | Represents completion/error without emitting a `T` value |
| API already returning non-blocking `Mono<T>` | Keep `Mono<T>` and compose with operators | Avoid wrapping a Publisher inside a Publisher |
| API returning `CompletionStage<T>`/`CompletableFuture<T>` | Check `Mono.fromFuture(...)` and future lifecycle | Bridges async types; completion follows the future's mechanism |
| Create a fresh Publisher per subscription context | `Mono.defer(() -> publisherFactory())` | Defers **Publisher creation**, unlike `fromCallable` returning `T` |
| Move downstream signal processing to a scheduler | `publishOn(scheduler)` | Switches context after placement; does not fix a preceding blocking source |
| Database I/O with a reactive driver | True reactive API, e.g., R2DBC | Avoids tying up workers waiting on I/O if stack supports non-blocking |

**Special distinction with `Mono.just`:**

```java
Mono<String> eager = Mono.just(syncClient.read()); // syncClient.read() runs immediately

Mono<String> deferred = Mono.fromCallable(syncClient::read)
        .subscribeOn(Schedulers.boundedElastic()); // runs on subscribe
```

`Mono.just(value)` works great when `value` is already in memory; it is not inherently wrong. The issue lies in **evaluating a blocking expression before creating the Mono**.

## 11. Implementation Pitfalls and Self-QA

### Pitfall 1: `fromCallable` Without `subscribeOn`

```java
Mono<Data> mono = Mono.fromCallable(() -> syncDao.read());
```

Reading is lazy, yet if subscribed directly on the event loop, the Callable can run on and block the **event loop**. Attach `.subscribeOn(Schedulers.boundedElastic())` to blocking sources.

### Pitfall 2: Using `publishOn` After Callable and Assuming Isolation

```java
Mono<Data> mono = Mono.fromCallable(() -> syncDao.read())
        .publishOn(Schedulers.boundedElastic());
```

The source still runs in the upstream subscription context; only signals after `publishOn` are scheduled. For blocking sources, use `subscribeOn`.

### Pitfall 3: Switching to boundedElastic Then Calling `.block()` in a Controller

```java
@GetMapping("/data")
public Data get() {
    return service.readOnBoundedElastic().block(); // ANTI-EXAMPLE
}
```

Even though the sync call runs on a worker, `block()` still holds the controller thread waiting for the result; on an event-loop thread, Reactor may also throw an error for calling a forbidden blocking API. Return `Mono<Data>` directly so the framework manages subscription and response.

### Pitfall 4: Using an Unbounded Scheduler or Creating One per Request

Creating a dedicated thread/pool per request can exhaust system resources as traffic rises. Use the shared `Schedulers.boundedElastic()` and place limits at appropriate layers. When a truly dedicated scheduler is needed, manage its lifecycle and bounds.

### Pitfall 5: Assuming `boundedElastic` Eliminates the Need for Timeouts and Concurrency Limits

A JDBC call can hang too long; many such calls exhaust workers and/or the connection pool. Library-level timeouts and admission/concurrency policies are needed; a Reactor scheduler cannot guarantee external APIs stop on time.

### Pitfall 6: Duplicate Side Effects After Retry or Re-Subscription

```java
Mono<Receipt> write = Mono.fromCallable(() -> blockingPayment.charge())
        .subscribeOn(Schedulers.boundedElastic())
        .retry(1);
```

This is a **business-risk anti-example**: if an error occurs after the external system already recorded the charge, retrying can duplicate side effects. Ensure idempotency keys and a sound retry policy before applying retries to write operations.

### Pitfall 7: Blocking Nested Inside `map`/`doOnNext` Outside a Scheduler Boundary

```java
Mono<Item> item = reactiveSource
        .map(id -> syncDao.load(id)); // May block the thread emitting onNext.
```

If `reactiveSource` runs on the event loop, this risks blocking that thread. Use `flatMap(id -> Mono.fromCallable(() -> syncDao.load(id)).subscribeOn(Schedulers.boundedElastic()))`, and bound concurrency if the input is a `Flux`.

### Pitfall 8: Believing boundedElastic Forces the Entire Pipeline onto One Scheduler

`subscribeOn` governs the relevant upstream execution path; `publishOn`, `flatMap` with inner sources having their own schedulers, timers, and network I/O can continue signals on different threads. Always check the scheduler boundary of **each source** and use logs/metrics/traces to verify blocking parts never run on the event loop.

## 12. Self-Check Questions

**Question 1.** Why does `Mono.just(blockingDao.load(id))` fail to isolate the blocking operation?

**Answer:** Java evaluates the argument `blockingDao.load(id)` before calling `Mono.just(...)`; the blocking operation happens immediately on the current thread.

**Question 2.** Is `Mono.fromCallable(() -> blockingDao.load(id))` already safe for the event loop?

**Answer:** Not yet. It only makes the call lazy; you must choose an execution context for the blocking source, usually `.subscribeOn(Schedulers.boundedElastic())`.

**Question 3.** Why does `publishOn(boundedElastic)` placed after `fromCallable` fail to solve a blocking source?

**Answer:** `publishOn` switches downstream signal processing, whereas the upstream Callable runs in the subscription context. `subscribeOn` is the operator typically used to move source execution to an appropriate scheduler.

**Question 4.** If `Mono.fromCallable` is subscribed to twice, how many times can the DAO be called?

**Answer:** Twice—once per subscription of the cold source—unless a separate sharing/caching mechanism is used.

**Question 5.** Does a Reactor `timeout(Duration)` guarantee immediately halting a stuck JDBC library?

**Answer:** No. It can emit an error and cancel the subscription, but halting physical I/O depends on the library, interruption support, and driver/DB timeouts.

**Question 6.** When loading 200 items through a sync API, why limit `flatMap` concurrency in addition to using boundedElastic?

**Answer:** Because connection pools, workers, queues, memory, and target API capacity are all bounded. A bounded scheduler does not automatically ensure every request flow stays within resource budgets.

**Question 7.** In WebFlux, after using `fromCallable(...).subscribeOn(boundedElastic())`, what should the controller return?

**Answer:** Return `Mono<T>` (or `Flux<T>`) so Spring WebFlux subscribes and sends the response; avoid manual `.block()`/`.subscribe()` in controllers for result-returning flows.

## 13. Production Adoption Checklist

1. Pinpoint **which exact call** is blocking, its latency, and its current thread.
2. Put that blocking call inside `Mono.fromCallable` (or `Mono.fromRunnable` if returning no value).
3. Attach `subscribeOn(Schedulers.boundedElastic())` near the source to isolate.
4. Return the Publisher to the framework; avoid blocking the event loop in controllers/handlers.
5. Configure sync library timeouts, concurrency limits, and resource pools; measure queues, workers, and error rates.
6. Handle `null` → empty, exceptions → errors, and HTTP statuses per business rules; check whether retries are safe.
7. Verify with thread logs, metrics/traces, and load tests; do not infer thread switching merely because a method returns `Mono`.
8. Prefer switching to a non-blocking API long term, since isolated blocking still consumes a worker while waiting.

**Takeaway:** **`fromCallable` makes a blocking call lazy; `subscribeOn(boundedElastic)` moves that call onto suitable execution resources**. This pattern is a controlled bridge between synchronous Java code and Spring WebFlux; it protects the event loop while still requiring timeouts, concurrency limits, error handling, and resource-lifecycle management.
