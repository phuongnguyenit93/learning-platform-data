# corePoolSize and maxPoolSize

## 1. Context: Why Does a Thread Pool Need Two Limits?

In a Spring Framework application, `ThreadPoolTaskExecutor` often receives many tasks from controllers, services, listeners, or `@Async` methods. Each task needs a thread to run, yet the number of executing threads must not grow without bound. The two most important pool properties are:

- **`corePoolSize`**: the baseline worker threshold that the pool prioritizes creating when receiving tasks. Under normal policy, core threads are retained while idle unless `allowCoreThreadTimeOut` is enabled.
- **`maxPoolSize`**: the **upper bound** on workers the pool is allowed to create to handle load; it only comes into play for scaling when the queuing mechanism refuses to accept more tasks.

Both numbers must be understood together with **`queueCapacity`**. Without considering the queue, it is easy to assume `corePoolSize=2, maxPoolSize=10` means that under heavy task load the pool will automatically run up to 10 threads concurrently. When the queue still has space, `ThreadPoolExecutor` typically **prefers queuing once core is reached**, so it does not create extra threads up to max.

This lesson focuses on Spring's `ThreadPoolTaskExecutor` and the underlying `java.util.concurrent.ThreadPoolExecutor` mechanism. Those rules do not apply verbatim to every other `TaskExecutor`: for instance, `SyncTaskExecutor` has no thread pool for configuring these two properties.

## 2. Exact Meaning of Each Property

| Property | Role | Common Misconception |
| --- | --- | --- |
| `corePoolSize` | Core worker threshold: when receiving a task and worker count is below core, the pool prefers creating a worker | Does not mean that many threads already exist at bean startup |
| `maxPoolSize` | Maximum number of workers the pool may have at a time | Does not mean the pool will immediately reach max when core threads are busy |
| `queueCapacity` | Number of tasks that can wait in the queue (excluding currently running tasks) | Not the limit on running tasks or total tasks in the entire system |
| `keepAliveSeconds` | Time a worker **above core** may remain idle before being reclaimed | Not a per-task timeout |
| `allowCoreThreadTimeOut` | When enabled, allows core workers to retire after idle time as well | Does not increase `maxPoolSize` or change queue rules |

Key points to remember:

1. `0 <= corePoolSize <= maxPoolSize`, and `maxPoolSize >= 1` in the JDK `ThreadPoolExecutor`. Configuring `core > max` is invalid.
2. `corePoolSize` is **not the number of threads always existing from the start**. Core workers are normally created on demand when tasks arrive; `prestartAllCoreThreads` is a separate option to pre-create them.
3. `maxPoolSize` is a thread ceiling, **not a queue length ceiling** and not a target thread count to aim for.
4. Idle workers above `corePoolSize` can be reclaimed after `keepAliveSeconds`. Core workers are kept while idle by default, unless `allowCoreThreadTimeOut=true`.

According to Spring's `ThreadPoolTaskExecutor` JavaDoc, the defaults for **this class itself** are `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE`, and `queueCapacity=Integer.MAX_VALUE`. Because the queue is practically huge, the default setup usually behaves almost like an executor running one task at a time. **Do not confuse these defaults with the executor auto-configured by Spring Boot**: Boot may use different values depending on its version and application configuration.

## 3. Core and Max Must Be Read Together with queueCapacity

The two worker limits do not operate independently: when below core workers, the executor prefers creating a worker; once at core, it tries to enqueue the task; only when the queue rejects it does it try expanding up to max, and then applies the rejection policy if it cannot expand either. With a sufficiently large queue, many tasks may wait without the pool ever reaching max.

This lesson uses the rule above to **compute worker counts across the two thresholds**. The full submission algorithm, shutdown checks, and scenarios where later tasks run ahead of older ones are covered in the lesson "Task Acceptance Order: Core Thread Creation, Queuing, Expansion, Then Rejection". The simulation table and program below verify the impact of core/max.

## 4. Simulation with core=2, max=4, queueCapacity=2

Suppose tasks keep threads busy and do not finish while seven tasks are submitted one after another. Set:

```text
corePoolSize  = 2
maxPoolSize   = 4
queueCapacity = 2
```

The acceptance sequence proceeds as follows:

| Incoming task | Workers after acceptance | Queued tasks | Explanation |
| --- | ---: | ---: | --- |
| Task 1 | 1 | 0 | Below core, so create first worker |
| Task 2 | 2 | 0 | Below core, so create second worker |
| Task 3 | 2 | 1 | Core reached, queue has space |
| Task 4 | 2 | 2 | Queue is full |
| Task 5 | 3 | 2 | Queue is full, still below max, so add worker |
| Task 6 | 4 | 2 | Add final worker up to max |
| Task 7 | 4 | 2 | Both pool and queue are full; rejected under default policy |

Visualize the state right before Task 7:

```text
Running:        [worker-1: task-1] [worker-2: task-2]
                [worker-3: task-5] [worker-4: task-6]
Waiting queue:  [task-3] [task-4]
Incoming task:  [task-7]  --> REJECTED (default)
```

Total **instantaneous capacity in this scenario** is at most 4 tasks occupying threads plus 2 waiting tasks = 6 tasks, assuming all tasks block and none finish during submission. **There is no `max + queue` formula for throughput or fixed capacity at all times**: tasks can finish, workers pick up new work, the queue shrinks, and new batches of tasks can be accepted again.

When the two extra workers above core run out of work and remain idle long enough, they can be reclaimed back toward core. You cannot conclude `poolSize` is always 4 solely from `maxPoolSize=4`.

## 5. Runnable Java 17+ Example with Deterministic Results

To observe each threshold clearly, the program below uses JDK's `ThreadPoolExecutor` with the same scheduling strategy that `ThreadPoolTaskExecutor` wraps. A `CountDownLatch` prevents the first six tasks from completing, so the printed numbers do not depend on CPU speed.

Create file `PoolSizingDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class PoolSizingDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 4, 30, TimeUnit.SECONDS, new ArrayBlockingQueue<>(2));

        CountDownLatch release = new CountDownLatch(1);
        List<Future<?>> accepted = new ArrayList<>();

        try {
            for (int i = 0; i < 6; i++) {
                accepted.add(pool.submit(() -> {
                    release.await(); // Keep worker busy until main allows.
                    return null;
                }));
            }

            System.out.println("poolSize = " + pool.getPoolSize());
            System.out.println("queued = " + pool.getQueue().size());

            try {
                pool.submit(() -> {
                    release.await();
                    return null;
                });
                System.out.println("rejected = false");
            } catch (RejectedExecutionException ex) {
                System.out.println("rejected = true");
            }
        } finally {
            release.countDown(); // Do not leave workers blocked forever.
            pool.shutdown();
        }

        for (Future<?> future : accepted) {
            future.get(); // Proceed only after all six tasks finish.
        }
        System.out.println("completed = " + accepted.size());

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }
    }
}
```

Run:

```bash
javac PoolSizingDemo.java
java PoolSizingDemo
```

Exact stdout of the example:

```text
poolSize = 4
queued = 2
rejected = true
completed = 6
```

Explanation:

- All six initial `submit` calls are accepted. The first two tasks create core workers, the next two enter the queue, and the last two expand the pool to 4 workers.
- Because `release` has not been counted down yet, **no worker finishes**, so at measurement time there are always 4 workers and 2 queued items.
- The seventh task is rejected with `RejectedExecutionException` per the JDK's default `AbortPolicy`.
- The `finally` block releases the latch and initiates pool shutdown. `Future.get()` confirms that all six accepted tasks finished before the last line.

This example uses standalone JDK classes to avoid booting Spring just to observe the algorithm. In Spring, `ThreadPoolTaskExecutor` uses the corresponding `ThreadPoolExecutor`, though the exception thrown on task rejection under Spring's contract is typically `TaskRejectedException`.

## 6. Configuration in Spring Framework

In a Spring-managed application, you can define a bean whose three parameters jointly govern behavior:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class WorkerPoolConfig {
    @Bean("workerPool")
    public ThreadPoolTaskExecutor workerPool() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(2);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("worker-");
        return executor;
    }
}
```

This is a **Spring configuration class**; it requires a project with `spring-context` compatible with your JDK and must be scanned/registered by the container. This class cannot be compiled standalone with plain JDK alone. When the bean is Spring-managed, the container runs the proper initialization and destruction lifecycle callbacks; there is no need to call `initialize()` inside the `@Bean` method.

A service can inject it via the interface:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final TaskExecutor workerPool;

    public ReportService(@Qualifier("workerPool") TaskExecutor workerPool) {
        this.workerPool = workerPool;
    }

    public void requestReport(String id) {
        workerPool.execute(() -> generateReport(id));
    }

    private void generateReport(String id) {
        // Example: process report by id.
    }
}
```

This is a **Spring integration snippet**; business code calls `TaskExecutor.execute`, while thread count policies are configured in `WorkerPoolConfig`. `execute` does not return a `Future` and may return before the task finishes. To capture an async task's result or error, use a `Future`-returning API such as `AsyncTaskExecutor.submit` or design an explicit completion mechanism.

If the application uses `@Async`, ensure the method actually uses the intended executor bean (for example `@Async("workerPool")` and the call goes through the proxy). Changing a bean does not affect an `@Async` method pointing to a different executor.

## 7. The Queue Determines When maxPoolSize Takes Effect

`ThreadPoolTaskExecutor.setQueueCapacity` selects the backing queue based on its value:

### Queue with Positive Capacity

With `queueCapacity > 0`, Spring uses a bounded `LinkedBlockingQueue` of that size. For example, `core=2, max=8, queue=100`: when the 2 core threads are busy, new tasks normally enter the queue; only when the 100-element queue cannot accept more tasks does the pool have a reason to scale workers to 3...8. A large queue absorbs short bursts but can increase wait times.

### Very Large Default Queue

According to the JavaDoc, `queueCapacity=Integer.MAX_VALUE` is the default of `ThreadPoolTaskExecutor`. Under practical conditions, this queue rarely fills up before system resources run out, so `maxPoolSize` is seldom used for scaling. If you write:

```java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(20);
// queueCapacity not set: still uses very large default.
```

then you *cannot* expect the pool to normally spawn 20 workers even with hundreds of pending tasks. This is a common reason behind "raising max did not increase thread count." The snippet above **illustrates configuring an already created executor**.

### queueCapacity Equal to 0

With `queueCapacity=0`, Spring uses `SynchronousQueue`, a **direct handoff** mechanism that stores no backlog in a queue. When no worker is ready to receive a task and max has not been reached, the pool can create extra workers sooner. Thus `maxPoolSize` has a more direct effect on concurrent task execution.

This also makes the system hit the thread ceiling and reject tasks sooner under sustained load; set the max limit and overload strategy deliberately.

| Configuration | Once `core` workers are busy | Scaling behavior |
| --- | --- | --- |
| Very large queue | Tasks continue waiting in the queue | Usually stays near core |
| Positive queue, small limit | Tasks wait until the queue fills | Then gradually scales workers up to max |
| Queue equal to 0 | Attempts direct handoff | Can scale workers up to max faster |

## 8. How Do Changing Core and Max Affect Performance?

**Increasing `corePoolSize`** can allow more concurrent processing sooner and reduce queue wait times under steady load. However, too many threads for CPU-heavy work increase context switching, contention, and latency. Core threads also consume resources while idle.

**Increasing `maxPoolSize`** only helps if the queuing policy actually permits scaling and the system still has resources for extra execution. If each task must wait for a JDBC connection from a 10-connection pool, raising workers to 100 typically just creates more threads waiting on connections and can slow the system down.

**Decreasing `queueCapacity`** generally makes the pool scale earlier, while also causing saturation/rejection earlier once max is reached. **Increasing the queue** absorbs bursts but can turn wait time into a hidden problem. Both must be evaluated against real throughput, latency, and resource metrics.

To choose a configuration:

1. Identify whether tasks are primarily CPU-bound, blocking I/O, waiting on a database, or calling external services. No single `core`/`max` pair fits every workload.
2. Measure task arrival rate, processing time, queue wait time, p95/p99 latency, active workers, and rejected tasks under realistic load.
3. Bound threads to match CPU, memory, connection pools, external service quotas, and task lifetimes.
4. Choose a queue large enough to absorb brief fluctuations without masking prolonged overload. Add admission limits/retries or a durable queue when needed.
5. Load test with both bursts and sustained load, observing stability rather than measuring throughput in a single run.

A meaningful example: a CPU-heavy task cannot speed up indefinitely with more threads than CPU cores; an I/O-waiting task can use more workers but must respect connection limits and external services. Final decisions should rely on measurement.

## 9. Interaction with keepAlive, Timeouts, and Runtime Reconfiguration

`ThreadPoolTaskExecutor` allows changing `corePoolSize`, `maxPoolSize`, and `keepAliveSeconds` at runtime through appropriate management APIs, subject to `ThreadPoolExecutor`'s validity constraints.

Points to keep in mind:

- Workers **above core** can retire after `keepAliveSeconds` of idleness; scaling down from max to core does not require restarting the application.
- Enabling `setAllowCoreThreadTimeOut(true)` lets core workers also expire after sufficient idle time; it does not increase task acceptance beyond max.
- Changing `corePoolSize` or `maxPoolSize` does not mean that exact number of workers immediately exists or is running tasks. Inspect `getPoolSize()`, `getActiveCount()`, and `getQueueSize()` to understand current state.
- **Do not treat `queueCapacity` as an ordinary runtime knob.** The work queue is created during executor initialization; changing the property on an already running bean does not automatically replace the existing queue.
- When changing both limits together, always maintain `core <= max`. For instance, to raise core above the current max, raise max first; to lower max below the current core, lower core first.

`getActiveCount()` and queue size are point-in-time observations that can change while being read. They are suited for metrics/trends, not as the sole basis for an exact cross-thread synchronization algorithm.

## 10. When the Pool Reaches Its Limit: Rejection and Error Handling

When the queue is full, workers are at max, and the executor cannot accept more, Spring's `ThreadPoolTaskExecutor` under its default policy raises **`TaskRejectedException`** on the `execute`/`submit` caller side. This reflects a **task submission failure**, distinct from exceptions thrown *inside a task after it was accepted*.

Spring caller illustration:

```java
try {
    workerPool.execute(() -> process(data));
} catch (org.springframework.core.task.TaskRejectedException rejected) {
    // Respond with overload, bounded retry, or offload to a durable mechanism.
}
```

This is an **illustrative snippet** assuming `workerPool` and `process(data)` are already defined. When an asynchronously running `Runnable` throws an exception, that exception does not jump back into the `catch` block on the thread that called `execute`. To capture results, use a `Future` or a dedicated notification/state-persistence mechanism.

Do not automatically pick `CallerRunsPolicy` to "never lose tasks" while ignoring consequences: that policy can make the calling thread (such as a request thread) execute the task and extend latency; when the pool has shut down, behavior also depends on the policy contract. Likewise, an in-memory queue does not retain tasks if the process crashes suddenly. For business operations requiring durable delivery, consider messaging/persistent queues.

## 11. Common Configuration Mistakes

1. **Increasing only `maxPoolSize` without changing the queue.** If the queue is still huge, the pool will not scale; you must evaluate `queueCapacity` as well.
2. **Assuming `corePoolSize` is the number of threads pre-created at startup.** Core workers can be created lazily; prestarting requires explicit configuration.
3. **Confusing `maxPoolSize` with the maximum tasks in the system.** The pool also has a queue; waiting tasks do not occupy workers, yet still consume memory and incur latency.
4. **Setting `corePoolSize > maxPoolSize`.** Invalid configuration; runtime updates must preserve the `core <= max` invariant.
5. **Setting a huge queue to avoid rejections.** Can hide backlogs, raise latency, and risk running out of memory.
6. **Setting `maxPoolSize` too high for database/API-dependent tasks.** Adding workers does not expand downstream capacity; it only increases contention.
7. **Believing every Spring `TaskExecutor` shares the same parameters.** `SyncTaskExecutor`, `SimpleAsyncTaskExecutor`, and virtual-thread executors work differently.
8. **Load testing without keeping tasks busy and concluding the pool does not scale.** Fast tasks may finish before the queue fills, so reproducible test scenarios are needed.
9. **Ignoring queue and rejection metrics.** Looking only at CPU or thread counts misses backlogs and service degradation.
10. **Confusing thread timeout with task timeout.** `keepAliveSeconds` applies to idle workers; it does not abort long-running tasks.
11. **Overlooking which executor `@Async` actually uses.** Verify the selected bean before explaining why config changes did not change execution threads.

## 12. Self-Check and Retention

**Question 1.** `core=2, max=12, queueCapacity=1000`, with 20 tasks simultaneously keeping threads busy. How many workers does the pool normally create right away?  
**Answer:** Around 2 core workers; the remaining 18 tasks can wait in the spacious queue. There is no basis to claim the pool will immediately create 12 workers.

**Question 2.** `core=2, max=4, queue=2`; six tasks are accepted and none have finished. What happens to the seventh task under the default policy?  
**Answer:** The pool has 4 active workers and 2 queued items; the seventh task is rejected.

**Question 3.** Does reducing `queueCapacity` from 100 to 0 make the pool always run at `maxPoolSize`?  
**Answer:** No. A queue of 0 triggers direct handoff and extra worker creation sooner when needed, yet actual thread count still depends on task volume, idle workers, max, and pool state.

**Question 4.** Does increasing `maxPoolSize` always make CPU-heavy tasks faster?  
**Answer:** No. Excessive workers can cause contention, heavy context switching, and latency, especially beyond CPU capacity.

**Question 5.** After a high-load burst finishes, why might `poolSize` drop from 4 back to 2?  
**Answer:** The two workers above core can retire after `keepAliveSeconds` of idle time under the default policy.

When analyzing a Spring configuration, read **the three values in order: `corePoolSize` → `queueCapacity` → `maxPoolSize`**. Only after understanding the queuing threshold can you accurately reason about when the pool scales and when it rejects tasks.

### References

- [Spring Framework — ThreadPoolTaskExecutor JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java SE 17 — ThreadPoolExecutor JavaDoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
