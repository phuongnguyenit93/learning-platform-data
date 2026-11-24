# Avoiding Waiting for Child Tasks on an Exhausted Thread Pool

## 1. The Problem: Parent Holds a Worker Waiting for a Child That Needs That Same Worker

A subtle concurrency bug when using Java `CompletableFuture` with Spring `ThreadPoolTaskExecutor` is **a parent task running on a pool worker, submitting a child task to the same pool, and calling `Future.get()` or `CompletableFuture.join()` to wait for the child**. If all workers are held by parents, children sit in the queue with no worker to run them. Parents cannot finish before their children finish; children cannot start before parents yield a worker.

This is **thread-pool starvation deadlock**: no progress can occur because execution resources are completely occupied by work waiting on other work that needs those exact resources. It does not require `synchronized`, `ReentrantLock`, high CPU, or an immediate JVM error.

**Core principle:** while holding an executor worker, avoid blocking it to wait on a `Future` whose completion depends on an unstarted task in the same executor. Instead, **express dependencies with completion stages** such as `thenApply`, `thenCompose`, and `thenCombine`, so the worker can return to picking up tasks instead of waiting synchronously.

This lesson focuses on parent–child dependencies, queue/core/max mechanics, how Spring `@Async` can introduce a hidden wait layer, and prevention techniques verifiable with Java 17+.

## 2. Deadlock Mechanism via a Single-Worker Diagram

Suppose an executor has one worker and a queue with capacity. Caller submits parent, and parent submits child:

```text
Caller thread
    |
    +--- pool.submit(Parent) -----------+
                                         |
                                    Worker #1 runs Parent
                                         |
                                         +-- submit(Child)
                                         |       |
                                         |       +--> Queue: [Child]
                                         |
                                         +-- Child.get() / Child.join()
                                                 |
                                                 +--> Worker #1 blocked
                                                         |
Child needs Worker #1 <----------------------------------+
    |
    +-- Child cannot start, Parent cannot yield the worker
```

This is a structural wait cycle. If Parent merely performs a long computation, the worker can still finish on its own. Yet if Parent requires a queued Child that only this worker can execute, **increasing wait timeouts will not make Child run on its own**.

With N workers:

```text
Worker #1 = Parent A  --> waits for Child A
Worker #2 = Parent B  --> waits for Child B
...
Worker #N = Parent N  --> waits for Child N

Queue = [Child A, Child B, ... Child N]
No idle worker left to process the queue.
```

That is why a design that looks fine under light load (while idle workers exist) can stall when **concurrent parents reach N**. It can be reproduced with 1, 2, or many workers—not only in tiny pools.

## 3. Waiting Inside vs. Outside the Pool Is Not the Same

`Future.get()` waits for a result, and `CompletableFuture.join()` can block too. The decisive question is **whether the waiting thread is a worker needed by the child**.

| Case | Assessment |
| --- | --- |
| Main/test thread outside the pool calls `future.get()`, while pool workers are free to complete the task | Can be valid at a bounded wait boundary; still blocks main/test thread |
| HTTP thread calls `get()` right after submit | Can make the request wait long; does not necessarily starve the pool, though SLOs must be watched |
| Parent inside the pool calls `child.join()`, and child runs in the same full pool | Starvation deadlock risk |
| Parent calls `join()` on an **already completed** `Future` | Not waiting on an unstarted child; normally returns immediately |
| Parent in pool A waits on a task in pool B | Does not form a single-pool cycle, yet can still cause resource exhaustion or cross-pool cycles between A and B |
| A callback registered with `thenCompose` that **calls no blocking API** | Worker is not held solely waiting for the child stage |

There is no rule that "all `join()` calls are wrong." The real rule is **never turn a worker needed for forward progress into a thread waiting on a `Future` of a dependent task that lacks a worker**.

## 4. Runnable Java 17+ Example That Does Not Hang Forever

This example intentionally uses an executor with **one worker**. Parent submits child and waits on child with a 100 ms timeout. Because child cannot run yet, parent times out. Once parent exits, child gets to run. At the end of the program, a `thenCompose` workflow succeeds on **that exact same single-worker pool** without nested blocking.

Create `PoolStarvationDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public final class PoolStarvationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        AtomicReference<Future<Integer>> childRef = new AtomicReference<>();

        try {
            Future<String> parent = pool.submit(() -> {
                Future<Integer> child = pool.submit(() -> 21 * 2);
                childRef.set(child);

                try {
                    child.get(100, TimeUnit.MILLISECONDS);
                    return "unexpected";
                } catch (TimeoutException ex) {
                    return "timed out";
                }
            });

            System.out.println("parent = " + parent.get());
            System.out.println("child = " + childRef.get().get());

            CompletableFuture<Integer> start =
                    CompletableFuture.supplyAsync(() -> 21, pool);

            CompletableFuture<Integer> composed =
                    start.thenCompose(n ->
                            CompletableFuture.supplyAsync(() -> n * 2, pool));

            System.out.println("composed = " + composed.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Run with JDK 17 or newer:

```bash
javac PoolStarvationDemo.java
java PoolStarvationDemo
```

Stdout:

```text
parent = timed out
child = 42
composed = 42
```

Step-by-step explanation:

1. `Executors.newSingleThreadExecutor()` has only one worker. Parent runs first.
2. Parent submits child to the same pool. Child sits in the queue because the worker is busy running Parent.
3. Parent calls `child.get(100, TimeUnit.MILLISECONDS)`; since no worker is available to run child, this wait times out. Parent finishes and returns `"timed out"`.
4. Once the worker is free, child is dequeued and returns `42`. `childRef.get().get()` is called on the **main thread**, not holding a pool worker.
5. Finally, `start` returns 21. `thenCompose` registers a child stage on the same pool and returns the completion relationship **without forcing the worker running the continuation to block waiting for child**. Child runs afterward and produces 42. Main thread reads the result with `composed.get()`.

This example was executed via JShell on an available JDK, confirming all three output lines. In a standalone program, `shutdownNow()` stops the executor on exit; in Spring, do not shut down shared executor beans after each request.

**Counter-example:** if you remove the timeout and replace it with an unbounded `child.get()` inside Parent, both Parent and Child can wait forever. Do not run that variant in CI without an external termination mechanism.

## 5. Identifying Deadlocks via a Wait-and-Resource Graph

To analyze a workflow, write out:

```text
Parent P holds worker W
P --------- waits for ---------> Child C's Future
C --------- needs -------------> worker from Executor E
E --------- assigned ----------> W to P
```

If E has assigned **all** workers to parents waiting on children, there is no path forward. This differs from tasks running slowly due to CPU or I/O: with starvation deadlock, children may not even have **started**.

| Symptom | Distinction |
| --- | --- |
| **Pool starvation** | Tasks are queued with no available worker |
| **Pool-starvation deadlock** | Workers are occupied by tasks waiting on work that cannot start because those exact workers are occupied |
| **CPU saturation** | Workers are actively computing; CPU/quotas are nearly exhausted |
| **Blocking I/O** | Workers may be waiting on DB/APIs; progress resumes when I/O completes |
| **Lock deadlock** | Threads hold locks and wait for each other's locks; the JVM can detect certain monitor/ownable synchronizer cycles |
| **Rejection** | Pool/queue refuses new tasks and may throw an exception, rather than hanging forever |

Do not rely solely on `Thread.State.WAITING`. Determine **which thread completes that Future, which executor holds the task, and what condition grants it a worker**.

## 6. ThreadPoolTaskExecutor: Why maxPoolSize Won't Rescue You Automatically

Spring's `ThreadPoolTaskExecutor` uses JDK `ThreadPoolExecutor`. Standard task-submission rules are:

1. While worker count is below `corePoolSize`, add a worker.
2. Once at core and the queue can accept the task, prefer **enqueueing**.
3. Only when the queue cannot accept the task, create additional workers up to `maxPoolSize`.
4. If the queue cannot accept and max is reached, reject the task per policy.

Example **configuration snippet**:

```java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(20);
executor.setQueueCapacity(1000);
```

If the two core workers are running two parents and both submit children and wait, the spacious queue accepts the children rather than forcing the pool to expand to 20 workers. Therefore, **`maxPoolSize=20` does not guarantee 20 workers will appear to rescue the parents**.

Configurations affecting the symptom:

| Configuration | When core workers are busy | Effect on child |
| --- | --- | --- |
| `core=max=1`, queue has space | Child waits in queue | A single parent waiting on child can stall |
| `core=max=N`, queue has space | All N parents can hold N workers | N children wait and can stall |
| `core<max`, very large queue | System prefers enqueueing | Max may rarely be reached |
| `queueCapacity=0`, bounded max | Attempts direct handoff or spawns worker | Child may run if workers remain; if at max, may be rejected |
| Unbounded/huge queue | Many tasks continue to be accepted | Growing backlog, memory/latency spikes, hiding worker exhaustion |

Increasing `corePoolSize`, `maxPoolSize`, or shrinking `queueCapacity` may delay when the issue appears or turn it into rejections, yet **does not fix a design where parents hold workers waiting on children**. With N workers, N concurrent parents can still recreate the wait cycle.

## 7. CompletableFuture Expresses Dependencies Without Blocking Workers

Instead of creating a child and immediately calling `get()` inside the parent, build a **completion graph**. Stages trigger once completion conditions are satisfied, without needing a worker sitting idle waiting on another stage.

### thenApply: Transforming a Value

```java
CompletableFuture<Integer> doubled =
        CompletableFuture.supplyAsync(() -> 21, executor)
                .thenApply(number -> number * 2);
```

Here `thenApply` transforms 21 into 42. This is a **code snippet** assuming an `Executor executor` variable exists. The callback may run on the thread completing the prior Future or another completion caller per Java's contract; never assume it runs on the caller.

Use `thenApplyAsync(fn, executor)` when you want explicit callback scheduling. **Do not** bury a `join()` waiting on an unstarted child inside that callback.

### thenCompose: Next Step Returns a Future

```java
CompletableFuture<Integer> doubled =
        CompletableFuture.supplyAsync(() -> 21, executor)
                .thenCompose(number ->
                        CompletableFuture.supplyAsync(
                                () -> number * 2, executor));
```

`thenCompose` flattens nested Futures and creates a stage representing the child's result. The first stage completes and can free its worker, while the child stage executes afterward. It needs no `child.join()` inside the callback.

**Wrong way:**

```java
CompletableFuture<Integer> wrong =
        CompletableFuture.supplyAsync(() -> 21, executor)
                .thenApply(number ->
                        CompletableFuture.supplyAsync(
                                () -> number * 2, executor).join());
```

This is a **counter-example**: `thenApply` runs a callback containing `join()`. If the callback runs on a single-thread pool's worker, the child is queued while the callback holds the worker waiting—repeating starvation. Hiding `join` deep inside a lambda does not eliminate blocking behavior.

### thenCombine: Two Independent Tasks

```java
CompletableFuture<Integer> base =
        CompletableFuture.supplyAsync(() -> 40, executor);
CompletableFuture<Integer> extra =
        CompletableFuture.supplyAsync(() -> 2, executor);

CompletableFuture<Integer> total =
        base.thenCombine(extra, Integer::sum);
```

With one worker, `base` and `extra` can run one after the other; the combining step is registered and runs **after both complete**. No parent holds a worker waiting on a child.

### allOf: The Mistake Lies in Where join Is Called

`CompletableFuture.allOf(a,b,c)` returns an aggregate Future without blocking itself. However, `allOf(a,b,c).join()` **can block** if called inside a worker needed for `a`/`b`/`c` to complete.

When member Futures are structured properly, you can use:

```java
CompletableFuture<Void> all = CompletableFuture.allOf(a, b);
CompletableFuture<Result> combined =
        all.thenApply(ignored -> merge(a.join(), b.join()));
```

This is an **illustrative snippet**, assuming `a` and `b` are `CompletableFuture` instances and `Result` and `merge` are defined. When `all` completes normally, `a` and `b` already have results; the two `join()` calls in the callback simply read **already-ready** values rather than waiting on unstarted tasks. If a stage fails, `thenApply` does not run; handle exceptional completion separately.

**Conclusion:** `thenCompose` and `allOf` do not magically resolve every dependency. They are safe in this regard when continuations do not hold a worker waiting on work that lacks a worker.

## 8. Spring: Orchestration Services Can Return CompletableFuture Without @Async

A clean structure is letting the service **build a `CompletionStage` chain**, while time-consuming steps are submitted with `CompletableFuture.supplyAsync(..., executor)`. The orchestrating method does not necessarily need `@Async`.

Executor bean (Spring Framework configuration snippet requiring imports and registration in an `ApplicationContext`):

```java
@Configuration(proxyBeanMethods = false)
public class WorkerConfig {
    @Bean("workerPool")
    public ThreadPoolTaskExecutor workerPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("worker-");
        return pool;
    }
}
```

Service (Spring integration snippet requiring `@Service`, `@Qualifier`, `Executor`, `CompletableFuture`, `ThreadPoolTaskExecutor` imports):

```java
@Service
public class CalculationService {
    private final Executor workerPool;

    public CalculationService(
            @Qualifier("workerPool") ThreadPoolTaskExecutor workerPool) {
        this.workerPool = workerPool;
    }

    // Do not attach @Async to a method that only builds a completion graph.
    public CompletableFuture<Integer> calculate() {
        return CompletableFuture.supplyAsync(() -> 21, workerPool)
                .thenApplyAsync(number -> number * 2, workerPool);
    }
}
```

`calculate()` schedules two stages and returns a `Future` to the caller. A worker can finish the first stage and then pick up the second stage. No parent occupies a worker merely to `join()` a child result.

When the next step is already a genuinely async API, such as an HTTP client returning `CompletionStage<Response>`, use `thenCompose`:

```java
public CompletableFuture<Report> build(long id) {
    return CompletableFuture.supplyAsync(
                    () -> loadBase(id), workerPool)
            .thenCompose(base ->
                    remote.fetchAsync(base.externalId())
                            .thenApply(extra -> merge(base, extra)));
}
```

This is an **illustrative snippet** requiring `loadBase`, `remote.fetchAsync`, `merge`, and `Report` in the application. The condition is that `fetchAsync` does not hide nested blocking on the same exhausted pool. Every API named Async must be checked for its actual implementation and executor.

**Note:** the code above needs no outer `@Async`. If an orchestration method calls `join()` inside a lambda, the bug can still occur even though the method returns `CompletableFuture`.

## 9. Spring @Async Pitfall: Hidden Future.get() Inside the Interceptor

A particularly important case: business code **never calls `join()`**, yet the structure still creates a wait cycle.

In Spring Framework **6.2.x** under `@Async` proxy mode, `AsyncExecutionInterceptor` executes the target invocation inside a `Callable` submitted to the executor. If the target call **returns a `Future`**, the interceptor retrieves that `Future`'s value via `get()` to complete the proxy-facing `Future`. This can force the worker handling `@Async` **to wait on an incomplete child `Future`**.

**Counter-example code** (Spring-managed bean snippet; do not use as a production design):

```java
@Service
public class BadWorkflow {
    private final Executor workerPool;

    public BadWorkflow(@Qualifier("workerPool") Executor workerPool) {
        this.workerPool = workerPool;
    }

    @Async("workerPool")
    public CompletableFuture<Integer> calculateAsync() {
        return CompletableFuture.supplyAsync(() -> 42, workerPool);
    }
}
```

If `workerPool` has one worker, the queue accepts the child, the caller calls the method through the Spring proxy, and Spring async support is enabled:

```text
Caller -> @Async proxy -> submit wrapper
                                 |
                            Worker runs wrapper
                                 |
                         Target.calculateAsync()
                                 |
                          supplyAsync(child)
                                 |
                          child sits in queue
                                 |
                     target returns CompletableFuture
                                 |
                    interceptor waits on future.get()
                                 |
                     Worker is not free to run child
```

This structure can hang even though the method contains only `return CompletableFuture.supplyAsync(...)`. This behavior was **verified against Spring 6.2.9's `AsyncExecutionInterceptor` bytecode**: after `MethodInvocation.proceed()`, if the result is a `Future`, the callable invokes `Future.get()`. It is not a rule for every async mechanism outside Spring or every framework version.

Fixes:

- **Best for composition:** the orchestration method has no `@Async`, returns a `Future` composed of stages with explicit executors as in section 8.
- **If keeping `@Async`:** perform the computation directly on the method's worker, then return an **already completed** `Future`, such as `CompletableFuture.completedFuture(result)`. Do not spawn a pending child `Future` on the same pool and return it for the interceptor to wait on.

```java
@Async("workerPool")
public CompletableFuture<Integer> calculateAsync() {
    int result = doCalculation(); // Running inside the @Async worker.
    return CompletableFuture.completedFuture(result);
}
```

This is a **Spring method snippet**; `doCalculation()` must be defined and called via the bean proxy. Since `result` is already computed before the method returns, the interceptor does not wait on a workerless child.

**Two mechanisms to distinguish:** `@Async` schedules via **Spring proxy/advice**; `CompletableFuture.supplyAsync` schedules via a **JDK Executor**. Combining both without tracing the execution path can accidentally create **two submission layers and a hidden wait point**.

## 10. Decision Table When Existing Code Calls get/join

| What is it doing? | Risk | Adjustment |
| --- | --- | --- |
| Parent in pool calls `child.get()` on same pool | Very high when all workers are occupied | Return stage and chain with `thenCompose` |
| `thenApply` callback calls `child.join()` | May block on the stage-completing thread | Use `thenCompose`; do not wait on child inside callback |
| N independent tasks followed by `allOf(...).join()` inside that same worker pool | Can hold workers needed to run the N tasks | Return `allOf` stage and combine after completion |
| Controller calls `future.get(timeout)` on request thread | Does not directly hold worker pool, yet blocks the request | Consider async HTTP/SLOs; use explicit deadlines |
| `@Async` returns a pending child `Future` running on the same pool | Interceptor may wait on it implicitly | Remove `@Async` on orchestration or return a completed `Future` in target |
| Increasing max while queue is huge | Pool may not spawn additional workers | Inspect core, queue, and max in order |
| Splitting parent/child onto two bounded pools | Eliminates same-pool cycle, yet shifts bottlenecks | Watch queues, dependencies, overhead, and multi-tier load |
| Timing out and retrying infinitely | Can generate extra tasks/backlogs | Bounded retries, backoff, idempotency, and overload control |

Splitting executors can be a valid solution when an independent blocking operation is unavoidable (e.g., a blocking-only library), provided concurrency is sized across all dependencies: CPU, DB connections, memory, rate limits, and network. **Do not choose unbounded threads just to mask a flawed structure.**

## 11. Timeouts and Cancellation Do Not Automatically Untangle Wait Cycles

`future.get(1, SECONDS)` can unblock a parent after 1 second; the Java example in section 4 deliberately uses a timeout so the program exits. Yet it only **prevents an infinite hang**, without making the submit-child-and-wait-on-same-pool pattern healthy.

For `CompletableFuture`:

- `orTimeout(timeout, unit)` makes the `Future` complete exceptionally if not finished on time, yet **does not guarantee** that workers, I/O, or dependencies stopped.
- `completeOnTimeout(value, timeout, unit)` supplies a fallback value upon expiration, **which does not mean background work stopped**.
- `CompletableFuture.cancel(true)` does not use the flag to interrupt workers the way some `FutureTask` implementations can; cancelling a stage does not necessarily cancel all dependent tasks.
- `get(timeout)` only bounds **the caller's wait**, not the execution deadline of the whole workflow.

Any protocol with cancellation should account for held resources, side effects, idempotency, and DB/HTTP client deadlines. Do not rely on timeouts as the primary way to wait for children when all workers are exhausted.

## 12. ForkJoinPool, commonPool, and Virtual Threads: Exceptions to Understand

`CompletableFuture.supplyAsync(supplier)` **without specifying an executor** typically uses `ForkJoinPool.commonPool()` in JDK 17, subject to parallelism exceptions and framework/subclass customization. Having a child run on another pool sometimes makes a test sample "stop hanging," yet you may have **unintentionally shifted load onto the common pool**, losing queue/capacity/observability and context control.

`ForkJoinPool` has special mechanics like work stealing and can support certain managed-blocking cases; **do not conclude** that every blocking pattern or dependency will make the pool spawn enough workers to break cycles. A standard fixed `ThreadPoolTaskExecutor` has no such compensation policy.

Virtual threads (JDK 21+ in compatible environments) reduce the cost of many blocking tasks, yet cannot fix a logical result-dependency cycle, database quota, or semaphore limit. Identify **which resource is actually held** instead of hoping a new thread model guarantees progress by itself.

## 13. Diagnosing in Spring Production

Observe a set of metrics **within the same time window**:

| Symptom | Hint | What to do |
| --- | --- | --- |
| `activeCount ≈ poolSize` for long periods | Most workers busy or waiting | Take thread dumps checking `WAITING`, `TIMED_WAITING`, I/O |
| Queue grows while completion throughput nears 0 | Tasks wait in queue, workers make no progress | Look for parents waiting on Futures queued on the same executor |
| Low CPU, response timeouts | Possible blocking/locks/pool starvation | Inspect stacks for `FutureTask.get`, `CompletableFuture.join` |
| High `maxPoolSize`, pool never grows beyond core | Queue has room so core is not exceeded | Check actual `queueCapacity` |
| Rising `TaskRejectedException` | Pool/queue limit hit or executor shut down | Distinguish rejections from queued tasks |
| `@Async` method returns a pending child `Future` | Interceptor may be calling `get()` inside worker | Verify executors of both method and child |
| Logs show submitted yet missing started | Child has not been dequeued | Correlate parent-child traces and measure queue wait |

Use `ThreadPoolTaskExecutor.getActiveCount()`, `getPoolSize()`, and `getQueueSize()` alongside executor/Micrometer metrics where instrumented. These are snapshots, not sole proof. Combine **thread dumps**, trace/correlation IDs, and dependent `Future` graphs to see who waits on whom.

Note carefully: the JVM deadlock detector is primarily helpful for monitors and certain locks; **thread-pool starvation deadlock may not show up as a Java monitor deadlock**. Thread dumps still reveal workers waiting in `FutureTask.get` or `CompletableFuture.waitingGet` while queued children have not started.

## 14. Testing Reproduction Without Hanging the Test Suite

A good test intentionally creates worker exhaustion with a deadline:

1. Use a fixed executor with 1 or 2 workers and enough queue capacity for children.
2. Put a parent on every worker, confirming each parent has actually entered the task before submitting children; use `CountDownLatch` if ordering must be coordinated.
3. Wait on the child with a **short timeout** solely to verify the stall point without hanging the test forever. Record that the child was submitted yet not started.
4. Exit or cancel parents via an external mechanism; verify the child can run once a worker is yielded.
5. Replace the pattern with `thenCompose`/`thenApplyAsync`, rerun on **the same single-worker pool**, and verify the final workflow completes.
6. Repeat with parent counts equal to or exceeding worker counts, plus full-queue/rejection cases.
7. Put timeouts on the test harness and clean up in `finally`. Never use arbitrary `Thread.sleep()` to fake ordering instead of controlled latches/hooks.

Proper evaluation must cover **completion throughput**, queue wait time, busy workers, p95/p99 latency, errors, and recovery behavior. A test passing with just a few tasks is insufficient proof of structural safety.

## 15. Code Review Checklist

Before merging a `CompletableFuture` or `@Async` workflow, ask:

1. Which functions run **on an executor worker**?
2. Inside those functions, are there any `get`, `join`, `await`, or blocking calls waiting on another task?
3. On **which executor** will the awaited task run? Is it the same pool or a cyclic dependency chain of pools?
4. When every worker is occupied by a parent, can children still get a worker?
5. Does the queue have room preventing `maxPoolSize` from expanding?
6. Does any `@Async` method return a **still-pending** child `Future` running on the exact executor used by the async interceptor?
7. Can `thenCompose`/`thenCombine`/`allOf` be used to return the **Future of the entire workflow** instead of synchronous waiting?
8. Do callbacks perform heavy CPU/I/O or submit+join back onto the same pool?
9. Are queues, active workers, task started/completed counts, and exceptions/rejections measured?
10. Are timeouts/cancellation and resource cleanup designed properly, rather than used merely to mask starvation?

The rule is not "never wait on any Future": waiting at an **external orchestration boundary** or reading an already-completed `Future` can be valid. The goal is **never holding a resource required for a child's progress just to wait for that child**.

## 16. Self-Check Questions

**Question 1.** Single-worker pool; parent submits child to the same pool and calls unbounded `child.get()`. Why does it hang?  
**Answer:** Child is queued, yet the only worker is held by parent. Parent waits for child; child waits for worker.

**Question 2.** `core=2`, `max=20`, `queueCapacity=1000`; two parents wait on two children. Does `max=20` guarantee rescue?  
**Answer:** No. While the queue has space, the executor prefers enqueueing; the pool can remain stuck with two blocked workers.

**Question 3.** Does switching `get()` to `join()` eliminate blocking?  
**Answer:** No. `join` still blocks if the stage is incomplete; the difference is primarily exception types.

**Question 4.** The next step returns a `CompletableFuture<T>`. Choose `thenApply` or `thenCompose`?  
**Answer:** `thenCompose` to chain and flatten the async stage without `join` in the callback.

**Question 5.** Can an `@Async` method returning `CompletableFuture.supplyAsync(..., samePool)` deadlock even if the method never calls `join`?  
**Answer:** Yes. With Spring 6.2.x async proxies, the interceptor may call `Future.get()` on the returned target `Future` inside the pool worker.

**Question 6.** Does `CompletableFuture.allOf(a,b)` block the worker?  
**Answer:** No; it returns an aggregate stage. However, calling `allOf(a,b).join()` inside a worker needed for `a`/`b` to run can cause starvation.

**Question 7.** When parent has `get(timeout)` and child runs after parent times out, is the bug fixed?  
**Answer:** No. Timeout only makes parent yield the worker after failing; the resource dependency pattern remains unsafe.

**Takeaway:** **Workers execute work; Futures represent dependencies; completion stages coordinate results.** Never turn a worker into a thread waiting on a child task that needs that very worker to start. In Spring, inspect **implicit waits inside the `@Async` interceptor** as well, not just `get/join` written directly in code.

### References

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — AsyncExecutionInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncExecutionInterceptor.html)
