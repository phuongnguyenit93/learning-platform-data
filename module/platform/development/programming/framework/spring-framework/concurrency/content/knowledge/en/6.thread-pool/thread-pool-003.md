# queueCapacity and Internal Queue Selection in ThreadPoolTaskExecutor

## 1. Why Does queueCapacity Matter?

In Spring Framework, `ThreadPoolTaskExecutor` lets you submit `Runnable` tasks to a thread pool rather than manually spawning a new thread per task. When existing workers are busy and new work keeps arriving, the executor must decide whether to **enqueue**, **create another worker**, or **reject the task**.

The `queueCapacity` property directly determines the backing queue implementation inside `ThreadPoolTaskExecutor` and strongly shapes that behavior. It is not merely a memory limit: the queue choice alters when the pool scales from `corePoolSize` to `maxPoolSize`, the delay before a task starts, backlog accumulation risk, and when rejections begin.

For example, two applications both configure `corePoolSize=2` and `maxPoolSize=8`, but one sets `queueCapacity=1000` while the other sets `queueCapacity=0`. The first application typically queues many waiting tasks as soon as 2 workers are busy, whereas the second tries to hand off immediately to an idle worker or create additional workers (up to 8). Changing `queueCapacity` alone can produce completely different thread count and latency graphs.

**Lesson scope:** the internal queue for *unexecuted tasks* inside `ThreadPoolTaskExecutor`, how it interacts with core/max threads, and its operational implications in Spring applications. This is not a durable queue like Kafka/RabbitMQ: if the process crashes, tasks sitting solely in the executor's memory can be lost.

## 2. Which Queue Type Does queueCapacity Select?

For `ThreadPoolTaskExecutor` in Spring Framework 6.x, queue selection essentially corresponds to:

```java
// Simulation of ThreadPoolTaskExecutor's createQueue(int) logic:
BlockingQueue<Runnable> queue = queueCapacity > 0
        ? new LinkedBlockingQueue<>(queueCapacity)
        : new SynchronousQueue<>();
```

This snippet **illustrates the logic**, not the entire executor creation method. Specific breakdown:

| `queueCapacity` | Internal queue | Can tasks wait in the queue? | Notable behavior |
| --- | --- | --- | --- |
| Positive integer, e.g. `1`, `50`, `500` | `LinkedBlockingQueue<Runnable>` with the specified capacity | Yes, up to the configured element limit | Once core threads are filled, tasks are queued before creating non-core threads |
| `0` | `SynchronousQueue<Runnable>` | No; no storage slots for tasks | Tasks must be handed directly to an available worker, or the pool creates another worker if room remains |
| Negative number | `SynchronousQueue<Runnable>` | No | Follows the same "no buffering queue" branch; use `0` to express intent clearly |
| Setter not called | `LinkedBlockingQueue` with `Integer.MAX_VALUE` | Theoretically huge, bounded practically by RAM | Can build large backlogs; `maxPoolSize` is rarely reached because the queue seldom fills |

**Does not automatically select `ArrayBlockingQueue`:** the `queueCapacity` setter does not make Spring allocate a fixed-capacity ring array; the default queue for any positive value is `LinkedBlockingQueue`. The two implementations have distinct allocation characteristics and behavior, so never assume from the property name that all queues behave identically.

### 2.1. LinkedBlockingQueue: Storing Tasks for Later Execution

With `queueCapacity > 0`, the queue holds `Runnable` instances not yet picked up by a worker. When submission outpaces processing, the waiting count grows up to the capacity bound.

- The queue is FIFO on the waiting side, yet **does not guarantee completion order** when multiple workers execute concurrently.
- `queueCapacity=100` means at most 100 elements waiting in the queue; it **does not mean** the pool accepts only 100 tasks total, nor does it create 100 threads automatically.
- Tasks currently executing on threads **do not count** toward the queue element count.
- The queue holds references to tasks and their captured state, which can retain payloads/request objects. Large queues risk high memory usage and long waits before execution.

### 2.2. SynchronousQueue: Direct Handoff, Zero Storage

With `queueCapacity=0`, `SynchronousQueue` acts as a *handoff* mechanism: a task can only be inserted when a worker is ready to receive it, or the executor must spawn a new worker if the pool can still expand. It **does not** retain a backlog for later retrieval.

A confusing detail: `SynchronousQueue.size()` is always 0. Therefore, a metric chart showing "queue size = 0" **does not prove** the pool is not overloaded. Always inspect `activeCount`, `poolSize`, rejection counts, and latency as well.

Configuring `queueCapacity=0` with a very high `maxPoolSize` can cause many threads to be created rapidly during traffic bursts. Thus, when choosing handoff mode, pay close attention to max thread bounds, downstream capacity, and thread creation overhead.

## 3. Queue Type Shifts When Expansion and Rejection Occur

In `ThreadPoolExecutor`, when worker count is below `corePoolSize`, tasks are normally assigned to a new worker. Once core is reached, the executor tries `workQueue.offer(task)`: if the queue accepts it, the task waits; if rejected and the pool is below `maxPoolSize`, it tries adding another worker; finally, it falls back to rejection. During shutdown, pool state can also cause early rejection.

The key takeaway is that **the same `offer` call yields different outcomes across the two queues**: `LinkedBlockingQueue` has storage for tasks, whereas `SynchronousQueue` accepts only when a worker is waiting for handoff. The next table contrasts this behavior. The full four-step algorithm, races, and shutdown branches are covered in detail in the lesson "Task Acceptance Order: Core Thread Creation, Queuing, Expansion, Then Rejection".

## 4. Progression Example with Same Core and Max, Varying queueCapacity

Suppose:

- `corePoolSize=2`.
- `maxPoolSize=4`.
- Every task runs long enough that all workers remain occupied while 7 tasks arrive consecutively.
- The executor starts empty, and no task completes between submissions.

| Incoming task | `queueCapacity=2` | `queueCapacity=0` |
| --- | --- | --- |
| T1 | Core worker 1 executes | Core worker 1 executes |
| T2 | Core worker 2 executes | Core worker 2 executes |
| T3 | Enters queue (1/2) | Non-core worker 3 executes |
| T4 | Enters queue (2/2) | Non-core worker 4 executes |
| T5 | Non-core worker 3 executes | Rejected (4 workers busy, no queue space) |
| T6 | Non-core worker 4 executes | Rejected |
| T7 | Rejected (4 workers busy, queue full) | Rejected |

State at the moment T7 is submitted:

- **Capacity 2:** 4 tasks running, 2 tasks waiting, one task rejected.
- **Capacity 0:** 4 tasks running, zero tasks held in the queue, three tasks rejected.

This table is a simulation assuming tasks have not finished yet. In real runtime, workers may finish early and pick up other tasks; observed counts will differ. The core point is not "queue 0 is faster," but that **queue 0 prioritizes opening threads/handoff or rejecting immediately, while a positive queue adds waiting space before scaling**.

## 5. Runnable Experiment with Java 21 + Spring Framework

The following program intentionally holds workers on a `CountDownLatch` to deterministically reproduce a full queue without relying on `Thread.sleep()` and lucky timing. It creates two `ThreadPoolTaskExecutor` instances with capacity 1 and capacity 0, keeping `corePoolSize=1` and `maxPoolSize=2`.

**Project structure:**

```text
queue-capacity-demo/
├── pom.xml
└── src/main/java/example/QueueCapacityDemo.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>queue-capacity-demo</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
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
        <version>3.5.0</version>
        <configuration>
          <mainClass>example.QueueCapacityDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**File `src/main/java/example/QueueCapacityDemo.java`:**

```java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class QueueCapacityDemo {
    public static void main(String[] args) throws InterruptedException {
        demonstrate(1);
        demonstrate(0);
    }

    private static void demonstrate(int capacity) throws InterruptedException {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(capacity);
        pool.setThreadNamePrefix("demo-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(5);
        pool.afterPropertiesSet();

        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch bothStarted = new CountDownLatch(2);
        CountDownLatch queuedDone = new CountDownLatch(1);

        Runnable holdWorker = () -> {
            firstStarted.countDown();
            bothStarted.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        try {
            pool.execute(holdWorker);
            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First worker did not start");
            }

            if (capacity > 0) {
                pool.execute(queuedDone::countDown);
            }
            pool.execute(holdWorker);

            if (!bothStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Second worker did not start");
            }

            boolean rejected = false;
            try {
                pool.execute(() -> { });
            } catch (TaskRejectedException ex) {
                rejected = true;
            }

            System.out.printf(
                    "capacity=%d queue=%s pool=%d waiting=%d rejected=%b%n",
                    capacity,
                    pool.getThreadPoolExecutor().getQueue().getClass().getSimpleName(),
                    pool.getPoolSize(),
                    pool.getQueueSize(),
                    rejected);

            release.countDown();
            if (capacity > 0 && !queuedDone.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Queued task was not executed");
            }
        } finally {
            release.countDown();
            pool.shutdown();
        }
    }
}
```

**Compile and run** in the project directory:

```bash
mvn -q -DskipTests compile exec:java
```

**Verified output:**

```text
capacity=1 queue=LinkedBlockingQueue pool=2 waiting=1 rejected=true
capacity=0 queue=SynchronousQueue pool=2 waiting=0 rejected=true
```

The program compiles with `maven.compiler.release=21` and has been verified on a JDK supporting Java 21. Meaning of the two lines:

1. With capacity 1: the first task holds the core worker; the second sits in `LinkedBlockingQueue`; the third expands the pool to 2 workers; the next task is rejected.
2. With capacity 0: the first task holds the core worker; the second expands the pool to 2 workers; the next task is rejected immediately because `SynchronousQueue` cannot buffer a backlog.

`firstStarted` and `bothStarted` guarantee workers have actually started before measuring. `release` unblocks workers; `queuedDone` confirms the queued task was processed. The `finally` block ensures the latch is released and the pool is shut down, preventing lingering threads if an assertion fails.

Here `afterPropertiesSet()` is called manually because we instantiated the executor outside a Spring container. When `ThreadPoolTaskExecutor` is declared as a Spring-managed bean, the container invokes the corresponding initialization callback; manual calls are normally unnecessary.

If the latch-holding mechanism is removed, `poolSize` and `waiting` may vary depending on execution scheduling; that is normal concurrent behavior, not a queue bug.

## 6. Combining queueCapacity with corePoolSize and maxPoolSize

The three parameters form a single task-acceptance policy and should not be tuned in isolation.

### 6.1. corePoolSize

This is the core worker threshold: when fewer than `corePoolSize` workers exist, the pool prefers creating a worker before queuing tasks. By default, `ThreadPoolTaskExecutor` has a core size of 1.

That **does not mean** core threads are always pre-created at initialization; under standard configuration, threads are created on demand when tasks arrive unless prestart is explicitly configured.

### 6.2. maxPoolSize

This is the pool's total worker cap. While the queue can still accept tasks, the pool normally does not expand beyond core merely due to backlog. Only when the queue is full or cannot hand off does the pool attempt to grow up to max.

For example, setting `core=2, max=100, queueCapacity=10000` can still keep only two workers running for a long time while thousands of tasks queue up. `max=100` does not mean 100 workers immediately drain the backlog.

### 6.3. keepAliveSeconds and allowCoreThreadTimeOut

Workers above core can retire after `keepAliveSeconds` of idle time (commonly 60 seconds by default). Enabling `allowCoreThreadTimeOut` allows core workers to also expire when idle according to `ThreadPoolExecutor` rules. These affect how the pool shrinks, **not the queue type** chosen by `queueCapacity`.

### 6.4. Changing queueCapacity While the Program Is Running

The queue is created during executor initialization. Simply calling `setQueueCapacity(...)` on an **already initialized** executor does not automatically replace the existing queue or migrate queued tasks. Treat queue capacity/type as pool-creation configuration; if you must change it, plan a safe lifecycle-aware executor recreation/reconfiguration.

Do not assume every setter on `ThreadPoolTaskExecutor` supports runtime updates equally. `corePoolSize` and `maxPoolSize` support dynamic changes on the underlying executor, whereas queue selection is fixed at initialization.

## 7. Configuration in a Spring Application

A configuration using a bounded queue and explicit bean name:

```java
// Fragment inside a @Configuration class of a Spring application.
@Bean("businessExecutor")
public ThreadPoolTaskExecutor businessExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("business-");
    return executor;
}
```

This is a **fragment** requiring imports for `org.springframework.context.annotation.Bean` and `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` in a Spring configuration class. The numbers 4/8/100 are purely illustrative, not presets suitable for all systems. The bean must be created and managed by Spring so initialization and shutdown callbacks run according to lifecycle.

When using `@Async`, you must enable async processing (in plain Spring Framework, typically `@EnableAsync`) and specify the executor:

```java
// Fragment inside a Spring-managed service, invoked via @Async proxy.
@Async("businessExecutor")
public void processAsync(String id) {
    // Background work.
}
```

`@Async` routes the method to the matching executor when the call passes through the Spring proxy; `this.processAsync(...)` calls within the same bean typically bypass async execution under default proxy mode. Moreover, `@Async` **does not bypass the queue**, as tasks are still submitted to the executor and subject to the same limits/saturation.

With Spring Boot's auto-configured task executor, `spring.task.execution.pool.queue-capacity` can be used per Boot's configuration, for example:

```properties
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=100
```

The scope of these properties depends on the executor Boot actually auto-configures. If your application defines its own `@Bean ThreadPoolTaskExecutor` as above, do not assume these properties automatically apply to the custom bean; configure via an appropriate builder or setters and verify the live state after initialization.

## 8. What queueCapacity Should You Choose?

There is no single value suitable for every application. Start from task characteristics, latency requirements, downstream limits, and backlog tolerance.

| Choice | Pros | Cost/risk | When to consider |
| --- | --- | --- | --- |
| `queueCapacity=0` | No queued task accumulation, early saturation visibility, pool scales quickly up to max | Bursts spawn extra threads; immediate rejection once all workers are busy; can surge load onto DB/APIs | Direct handoff desired, with strict `maxPoolSize` and downstream limits |
| Small positive queue, e.g. 10–100 | Absorbs short bursts; makes backlog limits explicit | Still incurs queue latency and rejections; requires load-based sizing | Short-to-medium tasks needing bounded memory/latency |
| Large positive queue | Fewer rejections during bursts, avoids spawning extra threads early | Long waits, memory retention, masks overload, `maxPoolSize` rarely utilized | Only when large backlogs are genuinely acceptable and monitored |
| Default `Integer.MAX_VALUE` | Convenient for experiments or very low load | Uncontrolled backlog growth under sustained load; risk of exhausting RAM | Should not be treated as safe backpressure for production |

### 8.1. Setting a Limit Using a Wait Budget

Suppose tasks are processed at a steady throughput of roughly 40 tasks/s, and the target time **spent in the queue** should not exceed 0.5 seconds under the load condition of interest. Simple reasoning suggests allowing around `40 × 0.5 = 20` queued tasks at that level.

This is a back-of-the-envelope estimate for thinking, **not a guaranteed formula**: service-time distributions, traffic bursts, mixed short/long tasks, multithreaded scheduling, and downstream saturation alter actual latency. Measure p95/p99 queue wait and rejections in load tests to confirm. If task submission consistently exceeds processing rate, **any finite queue will eventually fill up over time**.

### 8.2. CPU-Bound vs. I/O-Bound

- For **CPU-bound** work, adding workers beyond available CPU cores usually increases context switching and CPU contention. Finite queues and admission throttling often matter more than "spawning more threads."
- For **I/O-bound** work, more workers can sustain higher concurrency while threads wait on network/DB. Still, too many concurrent tasks can exhaust connection pools or trigger downstream timeouts; bound downstream concurrency accordingly.
- When task durations vary widely, a shared FIFO queue can stall short tasks behind long ones. Consider separating executors by workload type when backed by measurements.

## 9. When the Queue Is Full: Rejection and Backpressure

By default, the underlying executor uses an abort-style rejection policy. Spring's `ThreadPoolTaskExecutor` surfaces rejections as `TaskRejectedException` when calling `execute(...)`. Distinguish between **a task rejected at submission** and **an accepted task that throws an exception while running on a worker**.

Several policies can be configured via `setRejectedExecutionHandler(...)`:

- **AbortPolicy:** rejects with an exception; the caller decides whether to report an error, perform bounded retries, or persist work to a durable mechanism.
- **CallerRunsPolicy:** provided the executor has not shut down, the caller executes the task itself when the pool rejects it, creating throttling by slowing the caller down. Do not use indiscriminately on latency-sensitive request threads, event loops, or tasks that may block for long periods.
- **DiscardPolicy/DiscardOldestPolicy:** can drop tasks; appropriate only after analyzing semantics and accepting dropped/evicted tasks. Never use silently for mandatory business work.

A finite `queueCapacity` paired with explicit rejection helps the system **acknowledge capacity limits**. However, if callers retry endlessly without backoff, or buffer unboundedly in another queue, overload is merely shifted elsewhere.

If business requirements demand survival across restarts, use a durable mechanism like a transactional outbox or an appropriate message broker; `ThreadPoolTaskExecutor`'s internal queue provides no durability, acknowledgements, or persistent retries.

## 10. Observe Properly Before Changing queueCapacity

Useful metrics to track over time:

1. **Pool size, active count, core/max:** how many workers exist and how many are currently busy; note metrics can be fast-changing snapshots.
2. **Queue size/capacity:** how many tasks are waiting; for `SynchronousQueue`, size=0 is a structural property and does not indicate saturation.
3. **Queue wait time:** measured from submission until the task starts running. You can wrap tasks at the submission layer to record timestamps; separate queue wait from execution time.
4. **Task execution time:** measure runtime after a worker picks up the task; correlate with throughput and wait/CPU ratio.
5. **Rejections, timeouts, errors, cancellations:** reflect acceptance limits and reliability. Do not look only at aggregate CPU.
6. **Downstream limits:** DB connection pool, HTTP client concurrency, network latency, GC/memory, and container CPU quota.

In the Java example, `getThreadPoolExecutor().getQueue()` is used **solely to verify queue type and observe state**. Avoid manually mutating the queue, draining `Runnable` items directly, or relying on internal structures in business services; doing so easily breaks the executor's concurrency assumptions.

You can attach Micrometer/Actuator metrics to application-managed executors when supported by your stack; verify that the right bean is instrumented and dashboards reflect the pool actually in use. Never judge from a single point-in-time metric reading.

## 11. Common Mistakes

1. **Thinking `queueCapacity=0` is a zero-capacity queue that still buffers a few tasks:** in practice Spring uses `SynchronousQueue`, which stores no backlog.
2. **Assuming positive queue capacity selects `ArrayBlockingQueue`:** Spring uses `LinkedBlockingQueue` by default.
3. **Raising `maxPoolSize` while keeping an unbounded queue:** tasks continue queuing after core; the pool rarely scales to max.
4. **Interpreting queueCapacity as total accepted tasks:** the queue counts only **waiting** tasks, excluding those currently running on workers.
5. **Setting a massive queue to avoid errors:** trades early rejection for high latency and out-of-memory risk.
6. **Setting queue to 0 without capping max:** can spawn excessive threads during bursts, overwhelming downstream dependencies.
7. **Looking only at `getQueueSize() == 0`:** with `SynchronousQueue`, this metric is always 0 even when every worker is busy.
8. **Calling `setQueueCapacity` after initialization expecting the queue to change:** the queue was already created; safe reconfiguration requires proper lifecycle handling.
9. **Ignoring `TaskRejectedException`:** callers may report success even though the executor never accepted the task; overload handling must be defined.
10. **Believing a FIFO queue guarantees FIFO completion:** with multiple workers, completion order depends on task duration and scheduling.
11. **Testing only with no load:** queue capacity, max pool, and rejections usually surface only when all workers are busy; run controlled tests under representative load.

## 12. Self-Check Exercises

**Scenario A.** A pool has `core=3, max=6, queueCapacity=2`; all 3 workers are busy and none finish. Three new tasks arrive sequentially. What happens?

- The first and second new tasks enter `LinkedBlockingQueue`.
- The third new task causes the pool to attempt opening a fourth worker because the queue is full.
- The pool **does not** wait until all 6 workers are created before queuing tasks.

**Scenario B.** Same pool, but `queueCapacity=0`. What happens when three new tasks arrive while the 3 core workers are busy?

- There is no queue storage for tasks; the pool can spin up workers 4, 5, and 6 to run the three new tasks.
- If all 6 workers remain busy, the next task cannot be handed off and is rejected per the rejection policy.

**Scenario C.** An application has 2 workers, 500 waiting tasks, and only 15% CPU utilization. Should you increase `queueCapacity` further?

You cannot decide from low CPU alone. Check whether workers are blocked on I/O/locks, DB connection pool exhaustion, queue wait times, producer/consumer rates, and timeouts. Increasing the queue does not make tasks run faster; it only allows a larger backlog.

## 13. Key Takeaways

- `queueCapacity > 0` → Spring creates a `LinkedBlockingQueue` with the specified capacity.
- `queueCapacity <= 0` → Spring creates a `SynchronousQueue` that buffers no backlog.
- Standard acceptance rule: **create core worker → try queue → scale up to max if queue rejects → reject if out of room**.
- Large queues can increase latency and retain memory; queue 0 makes the pool open threads early but can reject early. Tune together with `corePoolSize`, `maxPoolSize`, traffic profile, and downstream resources.
- Monitor queue wait, active threads, saturation, and rejections; queue size alone is insufficient, especially with `SynchronousQueue`.
- `ThreadPoolTaskExecutor` is an in-memory executor, not a durable queuing system.

### References

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java 21 — ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java 21 — SynchronousQueue API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html)