# Using `completedFuture()` for Values Computed Inside the Execution Flow

## Goal

In Spring Framework, an `@Async` method returning `CompletableFuture<T>` often ends with:

```java
return CompletableFuture.completedFuture(result);
```

Why does an **asynchronous** method return an **already completed** future? You must distinguish two objects: the **temporary future** created by the target method inside the worker after computing `result`, and the **actual future** returned by the Spring proxy to the caller to track the entire submitted work. `completedFuture()` does not schedule execution; `@Async` and the executor are what move work off the caller when configured and invoked properly.

After studying this lesson, you can:

1. Accurately explain the contract of `CompletableFuture.completedFuture(value)` in the JDK.
2. Understand why an `@Async` target method uses a completed future to pass a computed value back to Spring infrastructure.
3. Distinguish the moment **the value is ready in the worker** from the moment **the caller's future completes**.
4. Choose properly among `completedFuture`, `failedFuture`, `supplyAsync`, `new CompletableFuture<>()`, and composition operators.
5. Write and run a Java 17+ example with Spring Framework proving the temporary future is done while the proxy future is still pending.
6. Avoid pitfalls around self-invocation, blocking, async errors, cancellation, timeouts, context, and mutable state.

**Core takeaway:** `completedFuture(value)` says "I **already have** value"; it does not say "compute value on another thread." In an `@Async` method, thread selection happens at the **Spring proxy/executor**, not in `CompletableFuture`'s static factory.

## 1. What Does `completedFuture()` Create in Java?

According to Java SE, `CompletableFuture.completedFuture(U value)` returns a new `CompletableFuture<U>`, **already completed normally** with the passed value. It is a synchronous factory method and submits no task.

```java
CompletableFuture<Integer> ready =
    CompletableFuture.completedFuture(42);

System.out.println(ready.isDone()); // true
System.out.println(ready.join());   // 42
```

The example above is a Java snippet using `java.util.concurrent.CompletableFuture`, without Spring. It opens no new thread, does not use `ForkJoinPool.commonPool()`, and creates no pending computation. `join()` here returns immediately because the result is already ready.

In particular, Java evaluates **the argument expression before the call**:

```java
int answer = expensiveCalculation();
return CompletableFuture.completedFuture(answer);
```

`expensiveCalculation()` runs **before** the future is created, on whichever thread is executing that code. Writing:

```java
return CompletableFuture.completedFuture(expensiveCalculation());
```

does not by itself make the calculation async: Java still executes `expensiveCalculation()` to obtain the argument before calling the factory method. If `expensiveCalculation()` blocks for three seconds, the caller of a regular Java method may be blocked for three seconds. To change where it runs, a separate scheduling mechanism is needed, such as `@Async`, `ExecutorService.submit`, or `CompletableFuture.supplyAsync`.

**States and characteristics:**

- A future created by `completedFuture(value)` has `isDone() == true` and `isCompletedExceptionally() == false`.
- `get()` and `join()` have the result ready; there is no waiting on a background task.
- You can use `completedFuture(null)` if the contract permits a `null` value; this is a **valid future** holding null, not the same as a method returning a `null` future reference itself.
- For a mutable value object, `completedFuture` does not turn that object into an immutable or thread-safe one.
- `completedFuture(error)` when `error` is a `Throwable` can still be a **success holding a Throwable value**, unlike a failed future.

Synchronous example returning a completion handle:

```java
public CompletableFuture<String> greeting(String name) {
    String message = "Hello " + name;
    return CompletableFuture.completedFuture(message);
}
```

Without an outer async AOP proxy or executor, both building `message` and creating the future happen on the caller. **A `CompletableFuture` return type does not by itself guarantee an asynchronous call.**

## 2. Why Does `@Async` Use a Temporary Future?

Spring `@Async` supports methods with a return type of `void` or `Future` (including `CompletableFuture`). For result-returning types, the Spring proxy submits the invocation to the executor and hands the caller a handle to wait for or compose the result.

Look at an illustrative method in a Spring bean:

```java
@Async("reportExecutor")
public CompletableFuture<String> buildReport(String id) {
    String report = calculateReport(id); // work in worker
    return CompletableFuture.completedFuture(report);
}
```

This is not yet a standalone program: it requires `calculateReport`, `@EnableAsync`, a bean named `reportExecutor`, and invocation **through the Spring proxy**. Under proper conditions:

1. The caller invokes `buildReport("A")` on the Spring-managed proxy.
2. The async interceptor selects `reportExecutor` and submits the method invocation.
3. The caller receives **the proxy's future**, typically while the task has not completed yet.
4. The worker runs `calculateReport("A")` and obtains a `String report`.
5. Because the method signature requires `CompletableFuture<String>`, the worker returns a **completed temporary future** via `completedFuture(report)`.
6. The async infrastructure processes the target method's return value and completes **the future the caller received** with `report`.

Spring's `@Async` Javadoc states this distinction clearly: the future returned by the proxy is the actual asynchronous handle, while the target method can use `CompletableFuture.completedFuture` as a temporary handle to pass the computed value within the execution thread.

```text
Caller thread                 Spring proxy                  Worker thread
   |                               |                              |
   +-- service.buildReport("A") -->|                              |
   |                               +--- submit to executor ------>|
   |<-- proxyFuture ---------------+                              |
   |                                                      calculateReport
   |                                                            |
   |                                                  String report ready
   |                                                            |
   |                                           completedFuture(report)
   |                                                    tempFuture = DONE
   |                                                            |
   |                               <---- target returns tempFuture
   |                               |                              |
   |<---- proxyFuture completed ---+                              |
   |
   +-- thenApply/get/join/whenComplete depending on caller
```

**You cannot infer** that the proxy future will always be pending right after the method call: the task may run extremely fast, or the chosen executor may execute on the caller. A complete example in section 4 deliberately uses synchronization latches to observe both states without relying on scheduler timing.

### Who Is Responsible for What?

| Component | Responsibility | Does NOT do on its own |
| --- | --- | --- |
| `@EnableAsync` | Registers annotation-driven async infrastructure in the Spring context. | Does not generate business results. |
| `@Async("reportExecutor")` | Marks the method and specifies the executor. | Does not work automatically across all direct Java call styles. |
| Spring proxy/interceptor | Intercepts invocation, chooses executor, submits, and provides completion handle to caller. | Does not guarantee the task always runs on another thread under every executor config. |
| `Executor`/`TaskExecutor` | Dispatches/runs tasks, manages queues and workers per policy. | Does not make shared data thread-safe. |
| `completedFuture(result)` in target | Wraps a result **already computed in the worker** into a completed temporary future. | Does not submit another task or start a new worker. |
| Future returned to caller | Allows waiting with timeout, observing errors, transforming, or coordinating results. | Does not automatically unblock caller if caller calls `join()` immediately. |

## 3. Conditions for the Spring Example to Work Properly

Merely adding `@Async` to source code does not make a method run in the background. You must check:

- **Spring-managed bean:** the object must come from `ApplicationContext`, not an instance manually created with `new`.
- **Async enabled:** `@EnableAsync` or equivalent infrastructure configuration is required in the right application context.
- **Call through proxy:** in default proxy mode, `this.asyncMethod()` inside the same target is **self-invocation**, bypassing the proxy and not submitted by the interceptor like an external call.
- **Interceptable method:** class-based proxies cannot override `final` or `private` methods; `final` classes cannot be subclassed. With JDK proxies, the caller must invoke a method exposed on an appropriate interface.
- **Valid signature:** `@Async` supports `void`, `Future`, and `CompletableFuture`; do not arbitrarily substitute `String` expecting the interceptor to turn it into a future.
- **Selected executor exists:** `@Async("lessonExecutor")` requires a bean of that name. A direct executor like `Runnable::run` or a `CallerRunsPolicy` under overload can run the task on the caller, even though the proxy still takes effect.
- **Caller does not block accidentally:** calling `get()` or `join()` immediately waits for the result; `@Async` does not guarantee the HTTP request thread is automatically freed.

When `@EnableAsync` is missing in a manually configured app like an example, `@Async` may not be processed; `return completedFuture(value)` is then just a regular Java statement. Therefore, distinguish **completion API** from **scheduling configuration** when diagnosing issues.

## 4. Java 17 Practice: The Factory Does Not Create a Background Task

The following example verifies the behavior of `completedFuture` with plain JDK. The experiment with Spring's two target/proxy Futures is covered in the dedicated async-bridge lesson; here we focus only on **value computation timing and submission**.

Save as `CompletedFutureSemanticsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletedFutureSemanticsDemo {
    static int compute(AtomicInteger calls) {
        calls.incrementAndGet();
        return 21 * 2;
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        // compute runs on the caller before the factory receives the argument.
        int result = compute(calls);
        CompletableFuture<Integer> ready =
                CompletableFuture.completedFuture(result);
        System.out.println("computedBeforeFactory=" + calls.get());
        System.out.println("readyDone=" + ready.isDone());
        System.out.println("readyValue=" + ready.join());

        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch release = new CountDownLatch(1);
        try {
            CompletableFuture<Integer> scheduled =
                    CompletableFuture.supplyAsync(() -> {
                        try {
                            release.await();
                            return 42;
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                    }, pool);
            // Latch is still closed, so the task cannot finish.
            System.out.println("scheduledPending=" + !scheduled.isDone());
            release.countDown();
            System.out.println("scheduledValue=" + scheduled.join());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 CompletedFutureSemanticsDemo.java
java CompletedFutureSemanticsDemo
```

Output:

```text
computedBeforeFactory=1
readyDone=true
readyValue=42
scheduledPending=true
scheduledValue=42
```

`compute()` is invoked before the factory so the counter is already 1, and `ready` is immediately completed. `supplyAsync` submits the supplier to the worker, while the latch holds the computation unfinished so the `scheduledPending` check is deterministic; after opening the latch, 42 is received. In a Spring `@Async` method, the proxy has already handled submission; the target only needs to compute the result on the worker and return `completedFuture(result)`.

## 5. Using `completedFuture` Correctly in a Real Spring Service

Suppose a service queries a repository synchronously:

```java
@Service
public class UserService {
    private final UserRepository repository;

    public UserService(UserRepository repository) {
        this.repository = repository;
    }

    @Async("ioExecutor")
    public CompletableFuture<UserDto> findUser(long id) {
        User user = repository.loadRequired(id);
        UserDto dto = new UserDto(user.id(), user.name());
        return CompletableFuture.completedFuture(dto);
    }
}
```

This is a **non-standalone structural pattern**; the types `UserRepository`, `User`, and `UserDto` must be defined, appropriate annotations/imports must exist, and the `ioExecutor` bean must exist.

Calling `service.findUser(id)` from another bean **through the Spring proxy** dispatches the entire repository read and DTO construction onto `ioExecutor`. By the time `completedFuture(dto)` is reached, the synchronous work inside the worker is finished. This future merely wraps the already obtained result for Spring.

Without `@Async` or when calling the target directly via self-invocation, `repository.loadRequired(id)` happens on the caller, potentially blocking the caller for a long time; a completed future at the end cannot rescue the lost time.

### When Should You Use It?

- An `@Async` target method computes a result synchronously inside the worker and needs to return a matching `CompletableFuture<T>` signature.
- A cache-hit branch or already available static data wants to conform to a unified Future API.
- A test stub immediately returns a ready value without needing a scheduler.
- An adapter wants to provide an already completed stage without spawning an extra worker.

### When Is It Unsuitable?

- Wanting to start computation on another pool: use `ExecutorService.submit`, Spring `@Async`, or `CompletableFuture.supplyAsync(..., executor)`.
- Wanting to represent work that completes when a callback/event arrives: create an incomplete future and call `complete` or `completeExceptionally` at the right time.
- Wanting to turn a pending Future into a value: compose instead of calling `join` on another Future inside the worker and wrapping the result.
- Wanting to report a known error: use `failedFuture(error)` instead of treating `completedFuture(error)` as a failed completion.

## 6. Comparing the APIs in a Table

| API | Immediate result after call | Schedules a new task? | Purpose |
| --- | --- | --- | --- |
| `CompletableFuture.completedFuture(value)` | Successfully completed Future | **No** | Bring an already computed value into the completion API. |
| `CompletableFuture.failedFuture(error)` | Exceptionally completed Future | **No** | Bring a known error into the completion API. |
| `new CompletableFuture<T>()` | Incomplete Future | **No** | External callback completes it later. |
| `CompletableFuture.supplyAsync(supplier)` | Future that may still be pending or finished very fast | **Yes** via default executor | Run async computation without specifying a pool. |
| `CompletableFuture.supplyAsync(supplier, executor)` | Similar, per provided executor policy | **Yes** via chosen executor | Explicitly select a pool. |
| `CompletableFuture.runAsync(runnable, executor)` | `Void`-typed Future | **Yes** | Work with no return value. |
| `future.thenApply(transform)` | Stage dependent on prior future result | Does not necessarily spawn a new worker | Transform the result. |
| `future.thenApplyAsync(transform, executor)` | Dependent stage executed via executor | **Yes** | Need to choose thread/pool for the transformation step. |
| `future.thenCompose(function)` | Flattened stage from a future-returning function | Does not inherently require a new pool | Chain asynchronous computations. |

`isDone()` does not prove a step executed on another worker. A task via `supplyAsync` may finish before the caller checks, or a custom executor may execute directly on the caller. You must inspect the scheduling mechanism, not just future state.

### Contrasting with `supplyAsync`

```java
ExecutorService pool = Executors.newSingleThreadExecutor();
try {
    int number = 7;
    CompletableFuture<Integer> immediate =
        CompletableFuture.completedFuture(number * 2);
    CompletableFuture<Integer> scheduled =
        CompletableFuture.supplyAsync(() -> number * 2, pool);

    System.out.println("immediate=" + immediate.join());
    System.out.println("scheduled=" + scheduled.join());
} finally {
    pool.shutdown();
}
```

This is a snippet placed inside a method, requiring imports for `ExecutorService`, `Executors`, and `CompletableFuture`. When run successfully, the output is:

```text
immediate=14
scheduled=14
```

Same output, different execution boundaries: the `number * 2` expression of `immediate` is evaluated immediately on the caller; the expression inside `scheduled`'s supplier is dispatched through `pool`.

### Avoiding Unintentional "Double Scheduling"

```java
@Async("ioExecutor")
public CompletableFuture<String> load(String id) {
    return CompletableFuture.supplyAsync(() -> blockingLookup(id));
}
```

This snippet needs a bean/executor and `blockingLookup`, and is not standalone. Here `@Async` has already moved the `load` method onto the chosen executor, and then `supplyAsync` **without passing an executor** dispatches another task to the JDK's default executor (usually `ForkJoinPool.commonPool()`). This can cause two scheduling layers, complicate thread/context/metrics management, and add blocking when Spring needs the child stage's result.

If `blockingLookup` is synchronous work meant to execute on an `ioExecutor` worker, the idiom is usually simpler:

```java
@Async("ioExecutor")
public CompletableFuture<String> load(String id) {
    String value = blockingLookup(id);
    return CompletableFuture.completedFuture(value);
}
```

If the logic genuinely completes asynchronously in another system, there may be reason to compose a stage from that API; decide ownership and executor explicitly, rather than automatically choosing `supplyAsync` merely because `CompletableFuture` is present.

## 7. Handling Exceptions in the Target and Caller

### Target Throws an Error Before Creating the Completed Future

```java
@Async("ioExecutor")
public CompletableFuture<UserDto> findUser(long id) {
    User user = repository.loadRequired(id);
    return CompletableFuture.completedFuture(
        new UserDto(user.id(), user.name())
    );
}
```

This snippet uses the domain types from the previous section. If the repository throws `RuntimeException`, the `completedFuture` line will not run. When the invocation goes through the Spring async proxy, infrastructure reflects the error from the worker onto the caller's completion handle.

The caller can use `get()` (typically receiving `ExecutionException` with `cause`), `join()` (typically `CompletionException`), or `whenComplete`/`handle` callbacks.

### Error Determined in Code

```java
@Async("validationExecutor")
public CompletableFuture<String> validate(String input) {
    if (input == null || input.isBlank()) {
        return CompletableFuture.failedFuture(
            new IllegalArgumentException("Input is blank")
        );
    }
    return CompletableFuture.completedFuture(input.trim());
}
```

This snippet assumes a `validationExecutor` bean, imports, and a Spring async context. `failedFuture` creates a future completed **exceptionally**, while `completedFuture` creates a future completed **successfully**. The word "completed" only refers to the terminal state; you must distinguish success from failure.

If declared `@Async void`, the caller has no future to receive exceptions from the worker; `AsyncUncaughtExceptionHandler` or deliberate logging/metrics are required. For critical business operations whose outcome must be tracked, prefer a Future return type or job status.

### Caller Observes Errors

```java
CompletableFuture<String> answer = validationService.validate(input);
answer.whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Failed: " + error.getMessage());
    } else {
        System.out.println("Valid: " + value);
    }
});
```

This is an illustrative snippet with `validationService` and `input`. `whenComplete` is an **observation** operation, not necessarily error recovery. If you want to return a fallback, consider `exceptionally`/`handle` and business policy. Do not ignore futures when tasks can fail.

## 8. Composition After Receiving the Result

The caller often does not need to call `get()`/`join()` immediately; stages can be chained:

```java
CompletableFuture<String> display =
    workService.compute("A", 7)
        .thenApply(value -> "Result: " + value.value());
```

This snippet uses `WorkService` from the main example, though it is not standalone. `thenApply` may execute on the thread completing the stage or the thread registering the callback when the future is already completed. It **does not guarantee** creating another worker.

If you want to explicitly choose an executor for the next step:

```java
CompletableFuture<String> display =
    workService.compute("A", 7)
        .thenApplyAsync(value -> "Result: " + value.value(), cpuExecutor);
```

Here an `Executor cpuExecutor` is needed. Do not assume `thenApplyAsync(...)` without passing an executor will use Spring's `lessonExecutor`; overloads without an executor typically use the JDK's default executor.

For a function returning `CompletionStage<U>`:

```java
CompletableFuture<String> chained =
    workService.compute("A", 7)
        .thenCompose(value -> anotherService.lookup(value.value()));
```

This snippet assumes `anotherService.lookup(...)` returns `CompletionStage<String>` or `CompletableFuture<String>`. `thenCompose` avoids creating nested futures. Avoid calling `join()` on another Future inside the worker just to `return completedFuture(...)`: if that other future needs the blocked worker itself to proceed, a small pool can stall or deadlock.

## 9. Thread Context, Mutable Data, and Side Effects

**Thread context:** `@Async` is a boundary between the caller thread and the worker. `ThreadLocal`, MDC, request attributes, security context, and transactions bound to the caller do not automatically transfer to the worker. `completedFuture` does not change this rule. When context is needed, propagate it in a controlled manner via `TaskDecorator` or an equivalent mechanism, and clean up/restore in `finally` because workers are reused. If the async task needs a transaction, define the transaction on the worker using appropriate Spring configuration.

**Returned object:** A completed `CompletableFuture<List<Order>>` does not automatically make `List<Order>` immutable. If multiple threads keep mutating the object, race risks remain. Prefer immutable DTOs, defensive copies, or clear ownership:

```java
List<String> snapshot = List.copyOf(items);
return CompletableFuture.completedFuture(snapshot);
```

This snippet needs `List` imported and an `items` variable. `List.copyOf` prevents structural modification through the returned list, though it does not guarantee deep immutability of mutable elements; copying from a concurrently modified source still requires proper synchronization.

**Side effects:** Completing a method's future does not by itself prove a message was processed by a consumer, an email reached a mailbox, or another system's database transaction committed. Clearly define which business milestone `result` represents; when durability is needed, use appropriate acknowledgements, job statuses, or transactions.

## 10. Timeouts and Cancellation Must Not Be Confused with completedFuture

```java
Result value = service.compute("A", 7)
    .get(500, TimeUnit.MILLISECONDS);
```

This snippet uses the service from the example. `get(timeout)` bounds **the caller's wait for the result**. On timeout, the worker may still be running; caller timeout does not create a `completedFuture` or automatically stop the task.

`CompletableFuture.orTimeout(...)` can make the future finish exceptionally if still pending after the deadline; `completeOnTimeout(...)` can complete with a fallback. These APIs change the completion state of the invoked future rather than guaranteeing worker interruption. For futures returned by a Spring proxy, cancellation and interruption have semantics depending on the future/infrastructure type; do not infer that `cancel(true)` definitely stops I/O or rolls back side effects.

In an HTTP request, if the controller calls `join()` immediately, the controller thread itself still waits. Achieving true async HTTP requires using the appropriate Spring MVC/WebFlux contract, independent of whether the target method has `@Async`.

Configure real timeouts on HTTP clients, JDBC, connection pools, and business deadlines; bound queues/workers so resources are not held indefinitely. If a task must continue after client disconnect or restart, you need job status and a durable queue/store; `completedFuture` does not solve durability.

## 11. Common Mistakes

| Incorrect claim | Correct understanding |
| --- | --- |
| "`completedFuture` creates a background task." | It creates an already completed future; it submits no task. |
| "Returning a completed future in `@Async` means the entire call is synchronous." | The target method can be running on a worker; the caller's proxy future tracks the full invocation. |
| "The future in the target and the caller's future are definitely the same object." | In Spring proxy mode, the caller usually receives a separate handle. |
| "`isDone() == true` proves it ran on another thread." | A synchronous future created with `completedFuture` also has `isDone() == true`. |
| "The argument in `completedFuture(slowQuery())` is evaluated in the background." | `slowQuery()` runs before the factory call, on the current thread. |
| "`this.asyncMethod()` also goes through the async proxy." | Self-invocation in proxy mode bypasses the advisor. |
| "You should nest `supplyAsync` inside every `@Async`." | It can add an unnecessary scheduling layer onto the default JDK executor. |
| "`completedFuture(exception)` represents a failed task." | It can be a successful future holding an exception value; use `failedFuture`. |
| "`get(timeout)` will cancel the task if the caller expires." | Timeout only bounds caller waiting; it does not auto-cancel the worker. |
| "A completed future makes its payload immutable and thread-safe." | Completion does not protect shared mutable objects. |
| "Returning a Future means the HTTP thread does not block." | A controller calling `join`/`get` still blocks; proper async HTTP design is required. |

## 12. Checklist for Reviewing `return completedFuture(result)`

1. **Where was the value computed?** Any computation/I/O happens **before** `completedFuture` and can block.
2. **Is there a proxy?** Is `@EnableAsync` enabled in the right context, is the bean Spring-managed, and is the call going through the proxy?
3. **Is the executor right?** Are the `@Async("...")` qualifier, thread-name prefix, queue/rejection, and pool bounds clear?
4. **Are there two future types?** The target's temporary future and the caller's proxy future must not be conflated in identity or lifecycle.
5. **Are exceptions handled?** Failures from `throw`, `failedFuture`, and submission errors must be observed, not treated as success.
6. **Is there double scheduling?** Does `supplyAsync` inside an `@Async` method unintentionally move the task to another executor?
7. **Is composition blocking?** Avoid `join()` on dependent futures in the same small pool.
8. **Is the payload mutable?** Check thread safety, ownership, and snapshots/DTOs before exposing.
9. **Are context and transactions handled?** Does the worker receive the right context and clean up after use?
10. **Timeout/cancel and late results?** A caller returning a fallback can leave the old task updating data; idempotency and side-effect bounds are needed.

## 13. Self-Check Questions

**1. Does `CompletableFuture.completedFuture(7)` use a new thread?**

No. It immediately creates an already completed future without needing an executor.

**2. Why can the caller still receive a pending future even when the `@Async` target method returns a completed future?**

Because the target computes the value inside the worker and returns a temporary future; the caller receives the future created by the Spring proxy to track **the entire invocation**, including queueing wait and computation.

**3. If there is only `return completedFuture(slowQuery())` with no scheduling, where does `slowQuery` run?**

It runs on the caller thread before the factory is invoked, potentially blocking the caller.

**4. In the demo example, what makes `temporaryFutureDone=true` yet `proxyFutureDoneBeforeReturn=false`?**

Because the worker created the temporary future and opened the `temporaryReady` latch, yet remained held at `allowReturn` before the target method returned. The proxy future was not completed yet.

**5. Is using `supplyAsync` inside `@Async("lessonExecutor")` necessarily better?**

No. It can create an extra task on the common pool or another executor, making scheduling and context harder to manage; if already computed synchronously in the worker, `completedFuture(result)` is usually more appropriate.

**6. When representing a known error, should you use `completedFuture(error)` or `failedFuture(error)`?**

Use `failedFuture(error)` for exceptional completion. `completedFuture(error)` may treat the error object as a success value.

**7. If the caller calls `proxyFuture.get()` immediately, does the caller continue doing other work?**

Not while waiting; the caller thread itself is blocked until the future completes or waiting is interrupted.

**8. Does a future completed with `List<Order>` automatically become deeply immutable?**

No. A future does not change an object's mutability; separate data and synchronization policies are required.

### Remember

`CompletableFuture.completedFuture(value)` only states that **value is already available and the future is completed successfully**. In a Spring `@Async` method invoked through a proxy, **asynchrony lives at the proxy/executor path**; the target can use a temporary completed future as a standard way to pass the value computed in the worker back to the caller. Always keep *where the value is computed*, *the submission path*, *the caller's actual future*, *exceptions*, and *task lifecycle* separate.

### Official References

- [Spring Framework — `@Async` Javadoc (6.2)](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/annotation/Async.html): proxy future and target temporary future contract.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@EnableAsync`, executors, `@Async`, and return types.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `completedFuture`, `failedFuture`, `supplyAsync`, composition, timeouts, and cancellation.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): results, waiting, and cancellation.
