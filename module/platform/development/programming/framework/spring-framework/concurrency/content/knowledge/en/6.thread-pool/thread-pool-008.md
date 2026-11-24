# Prestarting Core Threads with prestartAllCoreThreads

In Java, a `ThreadPoolExecutor` typically **does not create all core threads immediately upon construction**. Under the default policy, the pool adds workers on demand when initial tasks arrive. If you want core threads pre-created and waiting for work, you can call `prestartAllCoreThreads()`. In Spring Framework, `ThreadPoolTaskExecutor` provides the corresponding setting: `setPrestartAllCoreThreads(true)`.

This technique mainly shifts **when threads are created**: moving part of the creation overhead from the first task submission to pool preparation. It does not raise `corePoolSize`, execute business logic on its own, guarantee tasks never wait in the queue, or give the system more CPU resources.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the differences among `corePoolSize`, `maximumPoolSize`, existing workers, and workers currently executing tasks.
- Describe what `prestartAllCoreThreads()` does, what it returns, and when to call it.
- Distinguish `prestartCoreThread()` (one worker) from `prestartAllCoreThreads()` (all missing core workers).
- Use the Java 17+ API via `ThreadPoolExecutor` and properly configure `ThreadPoolTaskExecutor` in Spring.
- Analyze the effects of `queueCapacity`, `allowCoreThreadTimeOut`, `ThreadFactory`, and application lifecycle.
- Measure startup overhead and first-batch task latency, and recognize cases where prestarting brings no benefit.

## 2. What Is a Core Thread?

`ThreadPoolExecutor` manages a set of **worker threads** to execute `Runnable` or `Callable` tasks. Two key settings:

- `corePoolSize`: the baseline worker count the pool aims to maintain, unless core timeout is enabled or configuration/state changes.
- `maximumPoolSize`: the worker ceiling the pool can use when workload grows and the queue strategy permits scaling.

Beyond those two settings, live runtime state also includes:

| Term / API | Meaning |
| --- | --- |
| `getCorePoolSize()` | Configured core level; **not** the number of already created threads |
| `getMaximumPoolSize()` | Configured worker ceiling; not a mandatory target to create immediately |
| `getPoolSize()` | Number of workers currently in the pool; can be less than core if not yet started or timed out |
| `getActiveCount()` | Approximate number of workers actively executing tasks; threads waiting on the queue are not counted as active |
| `getLargestPoolSize()` | Largest number of workers that have ever coexisted in the pool |
| `getQueue().size()` | Number of tasks currently waiting in the queue at observation time; this value can change immediately |

For example, a pool with `corePoolSize=3` and `maximumPoolSize=8` may start right after construction with `getPoolSize()==0`. That is normal: the pool creates workers as tasks arrive. After prestarting, assuming successful creation, three core workers exist and wait for work even though `getActiveCount()==0`.

**Existing workers** differ from **workers running tasks**. Pre-creating three workers does not mean three tasks have started.

## 3. Default Lifecycle of a ThreadPoolExecutor

For a typical pool with a queue:

1. When constructing `ThreadPoolExecutor`, the constructor saves configuration without creating all core threads by default.
2. When submitting a task and total workers are below `corePoolSize`, the pool can create a new worker with that task.
3. Once enough core workers exist, the pool prioritizes placing subsequent tasks into the queue.
4. If the queue cannot accept more and capacity remains below `maximumPoolSize`, the pool can add workers.
5. If there is still no way to accept the task, `RejectedExecutionHandler` handles rejection.
6. Workers pull work from the queue, execute it, and either keep waiting for new work or terminate per lifecycle policy.

This is the **task acceptance decision order**, not a strict guarantee on task start order. Existing workers can pull tasks from the queue immediately upon insertion; OS scheduling and worker completion times still govern completion order.

For example, with `corePoolSize=3`, `maximumPoolSize=8`, `queueCapacity=100`: even if you enable prestarting, the pool only pre-creates **3 core workers**. While the spacious queue still accepts tasks, rising load enters the queue before expanding beyond core. Thus prestarting **does not replace** choosing appropriate pool and queue sizes.

## 4. What Does prestartAllCoreThreads() Actually Do?

`ThreadPoolExecutor.prestartAllCoreThreads()` has the signature:

~~~java
public int prestartAllCoreThreads()
~~~

The method attempts to start all **missing core workers** so they wait for work from the queue. Its return value is the **number of new workers actually started during this call**. It is not the number of tasks run, the final total thread count, or `maximumPoolSize`.

Suppose a fresh pool has core 4, zero workers, and a normal `ThreadFactory`:

~~~text
Before call:  poolSize = 0
prestartAllCoreThreads() -> 4
After call:   poolSize = 4
Called again: prestartAllCoreThreads() -> 0
~~~

If two core workers already exist, calling it can create two more to reach 4. If the pool already has full core workers, the return value is typically 0. If `corePoolSize=0`, no core workers need starting and it returns 0. Actual created count also depends on pool state, `ThreadFactory`, and concurrent configuration or lifecycle changes.

### Difference from prestartCoreThread()

`prestartCoreThread()` returns `boolean` and attempts to start **one** missing core worker. If core workers are already full, it returns `false`.

| Method | Purpose | Return type |
| --- | --- | --- |
| `prestartCoreThread()` | Attempts to start one additional core worker | `boolean`: whether a worker was started |
| `prestartAllCoreThreads()` | Attempts to start all missing core workers | `int`: number of workers started in this call |

Neither method **takes a `Runnable` argument**, submits a dummy task to the queue, waits for a business operation, or automatically runs application initialization logic. Created workers simply sit ready to receive work.

If you need to warm caches, open connections, or JIT-compile a hot code path, you need a dedicated warm-up procedure; prestarting does none of those.

## 5. Standalone Java 17+ Example

The example below creates a pool with `corePoolSize=3`, `maximumPoolSize=5`, and a queue holding up to 8 tasks. It checks worker counts before and after prestarting, calls prestart a second time, and submits three small tasks. `CountDownLatch` ensures the completed count prints only after all three finish.

File **PrestartDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class PrestartDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                3,
                5,
                30,
                TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(8));

        CountDownLatch finished = new CountDownLatch(3);

        try {
            System.out.println("before=" + executor.getPoolSize());

            int started = executor.prestartAllCoreThreads();
            System.out.println("started=" + started);
            System.out.println("poolSize=" + executor.getPoolSize());

            int startedAgain = executor.prestartAllCoreThreads();
            System.out.println("startedAgain=" + startedAgain);

            for (int i = 0; i < 3; i++) {
                executor.execute(finished::countDown);
            }

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Tasks did not finish");
            }

            System.out.println("completed=" + (3 - finished.getCount()));
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac PrestartDemo.java
java PrestartDemo
~~~

Output of a successful run with the default `ThreadFactory` and no other tasks:

~~~text
before=0
started=3
poolSize=3
startedAgain=0
completed=3
~~~

Line-by-line explanation:

- `before=0`: the pool was just created, received no tasks, and has no workers.
- `started=3`: the first prestart created three core workers, not all five workers up to `maximumPoolSize`.
- `poolSize=3`: three workers exist in the pool; threads may be waiting for work, not necessarily busy.
- `startedAgain=0`: enough core workers already exist, so none are added.
- `completed=3`: the **three `execute` calls and `CountDownLatch`** prove three tasks completed. `prestartAllCoreThreads` itself never increments any task counter.

The code uses two timeout bounds to avoid hanging indefinitely if the environment hits an error; state verification does not depend on `Thread.sleep()` or scheduler wakeup timing.

### Example: Calling Single-Thread Prestart Then Prestart All

This is an **illustrative snippet**, placed inside a method with a `ThreadPoolExecutor pool` created with `corePoolSize=4`, zero workers, no tasks, and core timeout disabled:

~~~java
boolean first = pool.prestartCoreThread();  // true
int remaining = pool.prestartAllCoreThreads(); // 3
int repeat = pool.prestartAllCoreThreads();    // 0
~~~

In the scenario above, the three variables take values `true`, `3`, and `0` respectively. If the pool previously processed tasks or was reconfigured concurrently, the number of added workers will differ. Avoid using `remaining == corePoolSize` as a rigid success condition in environments where multiple actors mutate the pool.

## 6. Integration in Spring ThreadPoolTaskExecutor

`org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` is Spring's common adapter over `ThreadPoolExecutor`. Since Spring Framework 5.3.14, it supports:

~~~java
public void setPrestartAllCoreThreads(boolean prestartAllCoreThreads)
~~~

This is a **configuration setter**, not the JDK method itself:

- `ThreadPoolExecutor.prestartAllCoreThreads()`: acts immediately on an existing pool and returns `int`.
- `ThreadPoolTaskExecutor.setPrestartAllCoreThreads(true)`: instructs Spring to start core workers during **executor initialization**; returns `void`.
- The Spring setter defaults to `false`, creating threads on demand.

For a Spring-managed bean, the container invokes the required initialization steps during the bean lifecycle. Set this property **before the bean finishes initializing**.

### @Bean Configuration

File **WorkerExecutorConfig.java** in a Spring application with the `spring-context` dependency:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class WorkerExecutorConfig {

    @Bean(name = "workerExecutor")
    public ThreadPoolTaskExecutor workerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(50);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("worker-");

        executor.setPrestartAllCoreThreads(true);
        executor.setAllowCoreThreadTimeOut(false);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        return executor;
    }
}
~~~

This is a **Spring configuration class**, with no standalone `main` method and not compilable with plain `javac` without Spring libraries. The container initializes the bean; under normal conditions three core workers are created during pool initialization. With `setPrestartAllCoreThreads(false)` (default), worker count grows with actual work.

`setAllowCoreThreadTimeOut(false)` preserves the core behavior: core threads are not discarded merely for being idle. This suits cases where you want them ready for tasks, though you must account for the resource cost of those three threads.

**`@Bean` does not require `@EnableAsync` just to create a pool.** `@EnableAsync` is only needed when activating `@Async` infrastructure per the corresponding configuration. If using `@Async("workerExecutor")`, specify the `workerExecutor` bean name and invoke the method through Spring's proxy; self-calls within the same bean under default proxy mode are not intercepted.

### Using TaskExecutor in a Service

File **JobDispatcher.java** (Spring integration code):

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class JobDispatcher {
    private final TaskExecutor executor;

    public JobDispatcher(@Qualifier("workerExecutor") TaskExecutor executor) {
        this.executor = executor;
    }

    public void dispatch(String jobId) {
        executor.execute(() -> process(jobId));
    }

    private void process(String jobId) {
        System.out.println("Processing " + jobId);
    }
}
~~~

This pattern illustrates task submission, **without promising the work has completed when `dispatch()` returns**. `process` simply prints output to study execution threads. Real applications must handle exceptions, job state, idempotency, shutdown, and durability if required by business rules.

### Creating an Executor Manually Outside Spring

When calling `new ThreadPoolTaskExecutor()` outside the container, you must manage initialization and shutdown yourself:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(4);
executor.setQueueCapacity(10);
executor.setPrestartAllCoreThreads(true);

executor.initialize();
try {
    // executor is initialized; work can be submitted.
} finally {
    executor.shutdown();
}
~~~

This is a **condensed lifecycle pattern** for use in a method/test with Spring libraries, not a standalone program. Never call `initialize()` repeatedly on an already Spring-managed bean just to "warm it up again."

## 7. What If the Pool Is Already Initialized?

In Spring, enable the setter before initialization. If you need to actively prestart **after** `ThreadPoolTaskExecutor` has already initialized, you can access the underlying JDK executor:

~~~java
ThreadPoolExecutor nativePool = springExecutor.getThreadPoolExecutor();
int newlyStarted = nativePool.prestartAllCoreThreads();
~~~

This is an **illustrative snippet** inside a method with an already initialized `springExecutor` variable of type `ThreadPoolTaskExecutor`. Before initialization, `getThreadPoolExecutor()` does not return a ready pool. Do not enable the setter after initialization expecting new threads to appear immediately; the setter primarily controls behavior at initialization time. Call the JDK API directly only when you genuinely need immediate action on the live pool.

If you raise `corePoolSize` at runtime and want to pre-create the new core threads, ensure you own that pool's configuration, verify the lifecycle is still valid, and measure memory/thread impact. Depending on queue state, changing `corePoolSize` itself may cause the pool to spawn workers to drain waiting work; do not assume only prestart calls increase thread count.

Reaching directly for the native pool couples code more tightly to `ThreadPoolTaskExecutor`, since not every `TaskExecutor` wraps a `ThreadPoolExecutor`. Prefer Spring configuration when the goal is simply "core workers ready from startup."

## 8. Interaction with queueCapacity, maxPoolSize, and Core Timeout

### queueCapacity Governs Expansion Behavior

Spring's `ThreadPoolTaskExecutor` uses a bounded capacity queue when `queueCapacity > 0` and `SynchronousQueue` when `queueCapacity <= 0`. With a positive queue, the pool normally places tasks in the queue once core is reached; only when the queue fills does it consider scaling workers toward `maxPoolSize`.

Therefore:

- `core=3, max=6, queue=50, prestart=true`: creates roughly three core workers at startup. With gradual load while the queue absorbs tasks, it may never use six workers.
- `core=3, max=6, queue=0, prestart=true`: no ordinary buffer; when core workers are busy and direct handoff fails, the pool can scale to six workers and then reject if out of room.
- `core=0, max=6, queue=50, prestart=true`: zero core workers exist to prestart. Understand this setup clearly if you intend workers to be pre-ready.

Prestarting does not alter the queue or `maximumPoolSize`. It only shifts when **core workers** are created.

### allowCoreThreadTimeOut(true) Can Make Core Workers Disappear

By default, core workers do not die merely from idleness. If `allowCoreThreadTimeOut(true)` and `keepAliveTime > 0` are set, core workers can also terminate after sitting idle without work. Result:

1. Startup runs prestart to create workers.
2. The application stays quiet long enough that core workers time out and leave the pool.
3. The next wave of tasks must create new workers again.

This is not a prestart bug. The two settings serve different goals: prestart reduces first-batch overhead; core timeout conserves idle resources. They can be combined, though latency gains for later waves become inconsistent once workers have been reclaimed.

### Actual Thread Count Depends on ThreadFactory and Environment

`ThreadPoolExecutor` obtains workers from a `ThreadFactory`. A `ThreadFactory` can configure names, priorities, uncaught exception handlers, or thread types; if it cannot supply a thread, fewer than expected may start. Exhausting native threads/memory or shutdown also affects startup. `prestartAllCoreThreads()` returns only how many were started in that call, never promising the result always equals `corePoolSize`.

Waiting for workers to become genuinely ready to pull tasks still depends on scheduling. Never use `getPoolSize() == corePoolSize` as a synchronization barrier proving every dependency inside tasks is ready.

## 9. What Benefits Does Prestarting Offer, and at What Cost?

### Potential Benefits

- Shaves off part of initial submission/task latency caused by **allocating `Thread` objects and native threads** when the first burst arrives.
- Surfaces core worker creation overhead earlier and more visibly during startup.
- Helpful for fixed pools, services with a latency-sensitive initial traffic wave, or pipelines receiving a batch of jobs right when marked ready.

Real-world gains depend on the application and may be tiny. Thread creation is typically only one fraction of total processing time alongside I/O, TLS, databases, GC, locks, and business logic.

### Costs and Risks

- Increases startup time/cost by creating all core workers before real work arrives.
- Holds idle thread resources (stacks, native handles, metadata, and related structures); noticeable if many beans/replicas each have large core sizes.
- Introduces concurrency early during startup, interacting with `ThreadFactory`, monitoring, or lifecycle hooks.
- Does not solve full queues, rejections, starvation, deadlocks, task errors, or multi-replica scaling needs.
- If a bean is rarely used, prestarting allocates resources the application barely touches.

**Do not use prestart to "increase throughput" without data.** Once a pool is warmed by real traffic, core/max worker counts and task execution times govern parallel capacity far more than whether workers were created a few milliseconds earlier.

## 10. Prestarting Is Not Application Warm-Up

Four operations are commonly confused:

| Operation | Pre-creates workers? | Runs business code? | Guarantee |
| --- | --- | --- | --- |
| `prestartAllCoreThreads()` | Yes, for missing core workers | No | Starts workers to wait for work; returns newly started count |
| Submitting warm-up tasks via `execute` | Potentially, per pool demand | Yes, runs submitted tasks | Depends on completion, errors, and how results are awaited |
| Warming JIT/caches/connection pools | Depends on implementation | Potentially | Only components actually exercised are warmed |
| Raising `corePoolSize` or `maxPoolSize` | May spawn workers depending on state | Runs no business tasks | Raises configured capacity bounds; does not improve latency on its own |

For example, if the first task must connect to a database and load a large model, prestarting eliminates only worker-creation overhead; connecting to the database and loading data still happen when the task executes unless you warm them up separately.

Likewise, `ThreadPoolTaskExecutor` defaults to traditional **platform thread** pooling. Thread-per-task virtual threads in Java 21+ operate differently; never mechanically apply this method to a `TaskExecutor` that has no core pool.

## 11. Coordinating with Spring Lifecycle and Readiness

### Bean Initialization

When Spring initializes a `ThreadPoolTaskExecutor` bean, it applies configured properties and initializes the executor. Enabling `setPrestartAllCoreThreads(true)` typically triggers thread creation during this step. With multiple pool beans, each pool has its own core and spawns its own workers; sum total thread counts before enabling it across the board.

In applications with readiness probes, **an initialized bean does not mean every external dependency is ready**, nor does prestarting prove the whole application can serve requests. Distinguish clearly:

- The executor is initialized.
- Core workers exist.
- Initial tasks can be submitted.
- Dependencies, data, and subsystems are ready for business operations.

If the app must verify dependencies before declaring ready, use proper health/readiness contracts. Never treat `getPoolSize() > 0` as the sole health check.

### Shutdown

Prestarting does not alter the shutdown contract: a pool that has begun shutting down does not become active again from a prestart call. When closing `ApplicationContext`, Spring manages bean lifecycles and pending/running tasks per configuration. Prestarting idle threads may leave more workers to clean up at shutdown, which is never a reason to skip proper shutdown.

Only invoke `shutdown()`/`shutdownNow()` on self-managed executors or within a designed lifecycle. Never shut down a bean shared by multiple components right when one request finishes.

## 12. How to Observe and Test

### Inspecting State

After Spring initializes a `ThreadPoolTaskExecutor executor`, you can read:

~~~java
int configuredCore = executor.getCorePoolSize();
int currentPool = executor.getPoolSize();
int activeTasks = executor.getActiveCount();
int queuedTasks = executor.getQueueSize();
~~~

This is an **illustrative snippet**, not standalone source. For a newly created pool with `core=3`, prestart enabled, and no tasks, observed state is typically `configuredCore=3`, `currentPool=3`, `activeTasks=0`, `queuedTasks=0`. Runtime values can shift immediately under concurrent submissions; never build race-sensitive business decision protocols on top of them.

For metrics in Spring Boot, use Micrometer/Actuator as configured for your environment. Track pool size, active count, queue size, rejections, and latency distributions, avoiding concluding "warm-up succeeded" from a single worker-count snapshot.

### Testing Latency Impact

A fair experiment should:

1. Build two pools identical in core, max, queue, `ThreadFactory`, and workload; differ only on prestart.
2. Measure **startup time**, time from submission until the first task begins, and total completion time.
3. Test both the very first burst after startup and subsequent bursts after the pool has processed work.
4. Repeat multiple iterations, controlling for JIT/GC/OS noise, measure p50/p95/p99, and compare memory/thread cost.
5. Repeat under realistic load with queues and task durations similar to production.

Never use `Thread.sleep(...)` to prove threads are ready. When coordinating tasks and measuring timings, use `CountDownLatch`, `Phaser`, or suitable synchronization primitives. Measurements should never rely on staging races with arbitrary millisecond sleeps.

### Verifying the Mechanism in Unit Tests

With a `ThreadPoolExecutor` configured with core 2 and zero submitted tasks:

~~~java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 4, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(4));
try {
    if (pool.getPoolSize() != 0) {
        throw new AssertionError("Expected a fresh pool");
    }
    int newlyStarted = pool.prestartAllCoreThreads();
    if (newlyStarted != 2 || pool.getPoolSize() != 2) {
        throw new AssertionError("Core threads were not prestarted");
    }
} finally {
    pool.shutdownNow();
}
~~~

This is an **illustrative snippet inside a method**, requiring `import java.util.concurrent.*`. With the default factory and no concurrent actors, this assertion is deterministic. Tests should shut down the executor in `finally` to avoid leaving non-daemon worker threads alive and hanging the test process.

For a Spring bean, inject the `ThreadPoolTaskExecutor` and inspect configuration and pool size after initialization. Do not call `initialize()` again on a live bean just to test worker counts. If testing the `@Async` path, verify both proxy invocation and task completion via `Future`/`CompletableFuture` or a latch.

## 13. Common Confusions and Mistakes

1. **Confusing `corePoolSize=5` with "5 threads exist immediately."** By default workers initialize on demand; prestart is what requests pre-creation.
2. **Confusing prestart with submitting five tasks.** Prestarting only makes workers wait; it never runs user-supplied `Runnable`s.
3. **Using `maximumPoolSize` to infer prestart count.** Only missing core workers are pre-created; max is not the prestart count.
4. **Calling prestart repeatedly thinking each call adds new core threads.** Once core is reached, subsequent calls return 0.
5. **Calling `setPrestartAllCoreThreads(true)` after initialization expecting immediate effect.** On an already running pool, use the JDK method on the native pool if immediate execution is truly required.
6. **Forgetting `initialize()` on a `ThreadPoolTaskExecutor` created manually outside the container.** Setters only configure; without initialization, no native executor exists yet.
7. **Thinking enabling prestart makes max pool engage sooner.** The queue still dictates expansion after core.
8. **Using a nearly unbounded queue and huge max, expecting prestart to cure backlogs.** Prestart does not fix queue growth or missing backpressure.
9. **Enabling core timeout while expecting core workers to always stay alive.** Workers can terminate after idle timeout.
10. **Creating too many core workers per replica.** CPU, memory, and native threads are shared; multiply pool count by replica count.
11. **Treating `getPoolSize()` as active thread count.** Active count has its own API, and both are snapshots/estimates.
12. **Treating first-run timing as absolute proof.** JIT, caches, disk, network, OS, and thread startup all affect latency together.
13. **Trying to call JDK methods on every `TaskExecutor`.** Not every Spring executor wraps `ThreadPoolExecutor`; for instance, virtual-thread executors work differently.
14. **Forgetting cleanup in demos or tests.** Core workers can stay alive and prevent the JVM from exiting without shutdown.
15. **Treating prestart as whole-system readiness.** Workers ready for tasks do not prove databases or external services are healthy.

## 14. Decision Guide

Enable prestart only when there is a clear need. A practical breakdown:

| Context | Recommendation | Rationale |
| --- | --- | --- |
| Service receives critical traffic burst right after startup; small fixed core | Test `prestartAllCoreThreads`, measure before/after latency | Can eliminate thread-creation overhead for the initial wave |
| Long-running batch worker with continuous tasks | Likely unnecessary | After a few tasks, core workers are already created |
| Service rarely runs tasks, many replicas | Consider keeping lazy | Avoids allocating many idle threads |
| First task slow due to DB/JIT/cache | Prestart alone won't solve it | Need proper dependency and code-path warm-up |
| Full queue / overload rejections | Prioritize capacity planning and backpressure | Prestart does not raise acceptance capacity |
| Want lower idle resource usage with `allowCoreThreadTimeOut(true)` | Re-evaluate warm-pool goal | Pre-created core workers may vanish after idle periods |
| Executor runs virtual-thread-per-task | Do not apply core-pool formula directly | Thread creation model differs from `ThreadPoolExecutor` |

In Spring applications, initial configuration should be concise and deliberate: specify core/max, finite queues where appropriate, thread names, rejection policies, lifecycle, and monitoring. Then evaluate prestart separately, measuring real latency before keeping it.

## 15. Self-Check Questions

1. A `ThreadPoolExecutor(core=4,max=10)` was just constructed with no tasks submitted. Must `getCorePoolSize()` and `getPoolSize()` both equal 4?
2. Why can `prestartAllCoreThreads()` returning 0 on a second call still be completely valid?
3. A pool already has two workers and `corePoolSize=5`. Under normal conditions, what can `prestartAllCoreThreads()` return?
4. How does Spring's `setPrestartAllCoreThreads(true)` differ from JDK's `prestartAllCoreThreads()` in timing of application and return value?
5. Why doesn't prestarting three workers cause `maximumPoolSize=20` to immediately create 20 threads?
6. If `allowCoreThreadTimeOut(true)` is enabled and the service sits idle for a long time, how can the benefit of prestart change?
7. How can you verify whether prestart genuinely improves p99 of the first request wave without confusing it with database connection time?
8. Why doesn't a pool with three idle workers prove the application is ready to serve all business functionality?

## 16. Official References

- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — ThreadFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadFactory.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)

**Takeaway:** `prestartAllCoreThreads()` is a tool to **pre-initialize core workers**. It can shift thread-creation timing to optimize initial burst latency, yet does not change capacity limits, run business warm-up, or replace sound pool/queue/rejection/shutdown design.