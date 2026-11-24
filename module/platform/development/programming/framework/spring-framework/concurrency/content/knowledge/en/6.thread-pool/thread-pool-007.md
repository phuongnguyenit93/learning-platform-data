# keepAliveSeconds and allowCoreThreadTimeOut in ThreadPoolTaskExecutor

## 1. Learning Objectives

When handling asynchronous work in a Spring application, a **thread pool** reuses worker threads instead of creating a new platform thread for every task. Two critical parameters governing what happens **after traffic drops** are `keepAliveSeconds` and `allowCoreThreadTimeOut`.

After this lesson, you will be able to:

- Explain the meaning of `ThreadPoolTaskExecutor.setKeepAliveSeconds(int)` and `setAllowCoreThreadTimeOut(boolean)`.
- Distinguish **core threads** from **non-core threads**, and configure "retain core threads" versus "allow core threads to be reclaimed."
- Predict the interaction among `corePoolSize`, `maxPoolSize`, `queueCapacity`, and keep-alive as the pool scales up and down.
- Properly configure a `ThreadPoolTaskExecutor` in Spring, knowing when to keep workers warm for lower latency and when to conserve resources during idle periods.
- Avoid pitfalls such as setting keep-alive to 0 when enabling core timeout, confusing idle timeout with task execution timeout, or assuming `maxPoolSize` always drives worker count as soon as load rises.
- Observe the pool with runtime metrics and verify behavior through a Java 17+ example.

**Scope:** This lesson focuses on Spring Framework's `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`, which manages a JDK `java.util.concurrent.ThreadPoolExecutor`. Timing remarks apply to **platform thread pools** of this kind. Do not apply them indiscriminately to every `TaskExecutor` implementation or executors creating a **virtual thread per task**.

## 2. What Are the Two Parameters?

### 2.1. `keepAliveSeconds` — How Long a Worker May Wait for Work

~~~java
executor.setKeepAliveSeconds(30);
~~~

The snippet above merely illustrates a setter call on an existing `ThreadPoolTaskExecutor`. A value of `30` means **30 seconds of idleness** is used as the threshold before an eligible worker can be reclaimed; it is not the maximum time allowed to run a task. When a worker finishes a task and receives no new task within this window, the pool may terminate that worker.

**Spring's `ThreadPoolTaskExecutor` defaults to 60 seconds.** Under `ThreadPoolExecutor`'s default rules, keep-alive applies only to workers **exceeding** `corePoolSize`. Thus, if `corePoolSize = 2`, `maxPoolSize = 6`, and the pool temporarily scales to 5 workers, the excess workers above core can terminate after the idle window; core workers do not automatically terminate from lack of work unless core timeout is enabled.

The keep-alive timer only begins counting while a **worker is waiting for work**, not from application startup, worker creation, or task start. A task running for 5 minutes is **not interrupted** because `keepAliveSeconds = 30`.

### 2.2. `allowCoreThreadTimeOut` — May Core Workers Terminate Too?

~~~java
executor.setAllowCoreThreadTimeOut(true);
~~~

The default is **`false`**. When `false`, a created core worker normally remains alive even while idle. When `true`, **core workers are subject to the same keep-alive policy as non-core workers**. Consequently, if no tasks arrive for long enough, the actual worker count can drop to **0**, even though `corePoolSize` remains greater than 0. When new tasks arrive, the executor creates workers again on demand.

Mandatory JDK constraint when enabling core timeout: **`keepAliveTime > 0`**. Enabling `ThreadPoolExecutor.allowCoreThreadTimeOut(true)` while keep-alive is 0 causes the JDK to throw `IllegalArgumentException`. In Spring, set a positive keep-alive before initializing the executor if you intend to enable this flag.

### 2.3. Quick Comparison Table

| Configuration | Core workers when idle | Workers above core when idle | When work resumes |
| --- | --- | --- | --- |
| `keepAliveSeconds=60`, `allowCoreThreadTimeOut=false` (default) | Retained once created | Reclaimed after roughly 60 seconds idle | Reuses surviving core workers or spawns more as needed |
| `keepAliveSeconds=10`, `allowCoreThreadTimeOut=false` | Still retained | Reclaimed sooner after roughly 10 seconds idle | Surviving core workers handle new bursts |
| `keepAliveSeconds=10`, `allowCoreThreadTimeOut=true` | Also reclaimed when idle long enough | Reclaimed | Pool can recreate workers starting from 0 |
| `keepAliveSeconds=0`, `allowCoreThreadTimeOut=true` | **Invalid** | — | JDK rejects core timeout with zero keep-alive |

These thresholds are **maximum idle wait policies**, not precision clocks guaranteeing termination at exactly second 10 or 60. OS scheduling, tasks arriving mid-wait, and pool state affect observed timing. Always distinguish **`getCorePoolSize()` (configured bound)** from **`getPoolSize()` (actual live workers at read time)**.

## 3. ThreadPoolExecutor Mechanics: Create Workers, Enqueue, Then Expand

These two timeout settings can only be understood accurately alongside the other properties of `ThreadPoolTaskExecutor`:

- `corePoolSize`: target baseline workers; Spring default is **1**.
- `maxPoolSize`: maximum worker limit; default is **`Integer.MAX_VALUE`**.
- `queueCapacity`: tasks allowed in the queue; default is **`Integer.MAX_VALUE`**.
- `keepAliveSeconds`: idle window making a worker eligible for termination; default **60**.
- `allowCoreThreadTimeOut`: whether core workers use keep-alive too; default **false**.

In `ThreadPoolTaskExecutor`, `queueCapacity > 0` creates a bounded `LinkedBlockingQueue` of that size; `queueCapacity <= 0` uses `SynchronousQueue` (handoff queue with zero waiting-task storage).

### 3.1. Sequence When a Task Arrives

When `execute` or `submit` is called:

1. If current workers are **below `corePoolSize`**, the executor prefers creating a worker to run the new task.
2. Once at least core workers exist, the executor prioritizes **inserting the task into the queue**.
3. Only when **queuing fails** and worker count is below `maxPoolSize` does it create a non-core worker.
4. If workers have reached max and the queue rejects the task, it is **rejected** via `RejectedExecutionHandler`.

Diagram:

~~~text
New task
   |
   +-- workers < corePoolSize? -- Yes --> create core worker
   |                              
   +-- No --> queue has space? --- Yes --> enqueue and wait
                    |
                    +-- No --> workers < maxPoolSize? -- Yes --> add worker
                                                |
                                                +-- No --> reject task
~~~

**Crucial consequence:** `maxPoolSize` normally **does not grow the pool** simply because core workers are busy, as long as `queueCapacity` still has space. With a nearly unbounded queue, the executor typically just runs at core level and keeps queuing. Non-core workers are rarely created then, so tuning `keepAliveSeconds` for non-core workers may produce virtually no observable effect.

### 3.2. Theoretical Example with a Finite Queue

Suppose the configuration is:

~~~java
executor.setCorePoolSize(1);
executor.setMaxPoolSize(3);
executor.setQueueCapacity(1);
executor.setKeepAliveSeconds(5);
executor.setAllowCoreThreadTimeOut(false);
~~~

This is an illustrative configuration, not a standalone program. Suppose tasks run long enough that none finishes before the fifth task is submitted:

| Submitted task | Pool action | Workers / waiting tasks in this hypothetical state |
| --- | --- | --- |
| Task 1 | Create core worker | 1 worker / 0 waiting |
| Task 2 | Put into queue | 1 worker / 1 waiting |
| Task 3 | Queue full, create worker #2 | 2 workers / 1 waiting |
| Task 4 | Queue still full, create worker #3 | 3 workers / 1 waiting |
| Task 5 | Max 3 reached and queue full, apply rejection policy | 3 workers / 1 waiting |

Once all finish and the pool goes idle, with `allowCoreThreadTimeOut=false`, the two workers above core can be reclaimed after the idle period; **1 core worker** can remain. If `true` is enabled with positive keep-alive, even the final core worker can be reclaimed.

The table above is a **hypothetical schedule with held tasks**, not a claim that ordinary submissions always yield those exact counts: real tasks can finish between submissions.

### 3.3. Why Is "Allowing Core Timeout" Still Useful When queue > 0?

Per Spring's Javadoc, enabling `allowCoreThreadTimeOut` lets the pool **grow on demand and shrink when idle** even with a positive-capacity queue. Reason: core workers are ordinarily kept alive forever while idle, whereas this flag permits reclaiming them.

However, this flag **does not reverse task acceptance order**: the pool still prioritizes the queue once core workers exist and the queue has space. To scale workers aggressively during bursts, you must evaluate `queueCapacity`, arrival rate, and `maxPoolSize` together.

## 4. Complete Spring Example: Configuring and Inspecting Policy

The following example is a runnable standalone Java program using **JDK 17+**, Maven, and **Spring Framework 6.1.3**. It manually initializes `ThreadPoolTaskExecutor`, reads the effective policy on the underlying `ThreadPoolExecutor`, and executes a task returning a result.

Structure:

~~~text
keepalive-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── KeepAliveDemo.java
~~~

### 4.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>keepalive-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
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
                <configuration>
                    <mainClass>demo.KeepAliveDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `spring-context` dependency suffices for `ThreadPoolTaskExecutor` in this example. In real Spring Boot applications, keep the Spring Framework version managed by your project's BOM/parent rather than pinning another version just for an illustrative snippet.

### 4.2. `src/main/java/demo/KeepAliveDemo.java`

~~~java
package demo;

import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class KeepAliveDemo {

    public static void main(String[] args) throws Exception {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(2);
        executor.setKeepAliveSeconds(3);           // idle timeout: 3 seconds
        executor.setAllowCoreThreadTimeOut(true);   // core workers can expire too
        executor.setThreadNamePrefix("lesson-");
        executor.initialize();

        try {
            System.out.println("core=" + executor.getCorePoolSize());
            System.out.println("max=" + executor.getMaxPoolSize());
            System.out.println("keepAliveSeconds="
                    + executor.getKeepAliveSeconds());
            System.out.println("coreTimeout="
                    + executor.getThreadPoolExecutor()
                              .allowsCoreThreadTimeOut());
            System.out.println("effectiveKeepAliveSeconds="
                    + executor.getThreadPoolExecutor()
                              .getKeepAliveTime(TimeUnit.SECONDS));

            Future<Integer> answer = executor.submit(() -> 21 * 2);
            System.out.println("answer=" + answer.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Run in the `keepalive-demo` directory:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the program (excluding Maven's own logs, if any):

~~~text
core=2
max=4
keepAliveSeconds=3
coreTimeout=true
effectiveKeepAliveSeconds=3
answer=42
~~~

**Interpretation:** `initialize()` builds the internal executor with the supplied properties. Calling `getThreadPoolExecutor()` after initialization reveals the **effective JDK policy**: `allowsCoreThreadTimeOut()` returns `true` and `getKeepAliveTime(...)` is 3 seconds. `submit` and `Future.get()` verify the pool accepts and executes tasks. The example intentionally **avoids printing instantaneous worker counts** because those numbers depend on scheduling and observation timing, offering no reliable deterministic stdout.

When creating an executor manually outside a Spring container as above, the application must manage its lifecycle explicitly. `shutdown()` terminates the pool—**completely different** from keep-alive reclaiming idle workers while the pool stays open to new tasks.

## 5. Experiment to Observe Worker Reclamation Without Inferring from Short Sleeps

You can verify worker lifetimes in plain Java before bringing the principles into Spring. The snippet below uses JDK's `ThreadPoolExecutor`, ensuring the task finishes before observing. It **has no Spring dependency** and uses only JDK 17+.

Save as `CoreTimeoutExperiment.java`:

~~~java
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class CoreTimeoutExperiment {

    public static void main(String[] args) throws Exception {
        observe(false);
        observe(true);
    }

    private static void observe(boolean allowCoreTimeout)
            throws Exception {

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 1, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>()
        );
        pool.allowCoreThreadTimeOut(allowCoreTimeout);

        try {
            pool.submit(() -> 42).get(); // wait for task to finish
            System.out.println("coreTimeout=" + allowCoreTimeout);
            System.out.println("poolSizeAfterTask=" + pool.getPoolSize());

            // Wait longer than the 1-second keepAlive to observe.
            // Do not use this result as a strict assertion.
            Thread.sleep(1500);
            System.out.println("poolSizeAfterIdle=" + pool.getPoolSize());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac CoreTimeoutExperiment.java
java CoreTimeoutExperiment
~~~

**A commonly observed output** on a lightly loaded machine is:

~~~text
coreTimeout=false
poolSizeAfterTask=1
poolSizeAfterIdle=1
coreTimeout=true
poolSizeAfterTask=1
poolSizeAfterIdle=0
~~~

This is an **illustrative observation**, not immutable stdout. A worker might not yet be reclaimed at the exact instant `Thread.sleep(1500)` ends if the machine is busy, paused, or scheduled differently. The goal is to contrast the **trend**: when retaining core, the worker persists; when allowing core timeout, it can disappear. Avoid writing pass/fail tests based on a single `getPoolSize()` read after a short `sleep()`. For automated tests, poll with an adequate deadline and avoid assuming millisecond-exact termination timing.

Note: the experiment uses `corePoolSize=maxPoolSize=1` to eliminate non-core workers; thus the observed difference comes **purely from the core timeout flag**.

## 6. Configuration When Spring Manages the Bean

In an application using component scanning and Spring configuration, define **one shared bean** rather than creating a new pool per request.

Configuration example in `WorkerPoolConfig.java` (a class integrated into an existing Spring application; not a standalone project):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class WorkerPoolConfig {

    @Bean("workerTaskExecutor")
    public ThreadPoolTaskExecutor workerTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(60);
        executor.setAllowCoreThreadTimeOut(true);
        executor.setThreadNamePrefix("worker-");
        return executor;
    }
}
~~~

When Spring manages the bean, the container handles initialization and shutdown according to the bean lifecycle. This configuration **does not automatically force every `@Async` method in the app to use this bean**: if multiple executors exist, you must specify the matching name/`@Qualifier` or configure the default executor for asynchronous method invocation.

Example selecting the executor by name once async processing is enabled:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    @Async("workerTaskExecutor")
    public void notifyLater(String message) {
        System.out.println(message);
    }
}
~~~

This service snippet illustrates integration, not a standalone program. `@Async` operates through a proxy when async configuration is enabled; self-calls within the same instance may bypass the proxy and fail to offload to the worker pool as expected. To submit directly, inject the corresponding `ThreadPoolTaskExecutor`/`AsyncTaskExecutor` and call `execute` or `submit`.

### When Does This Flag Have No Effect?

- `SimpleAsyncTaskExecutor` is not a worker-reusing `ThreadPoolTaskExecutor`; do not apply core-worker retention/reclamation rules to it.
- Virtual-thread-per-task executors in Java 21+ do not share the same core/max worker structure tuned by these two setters. JVM carrier threads are likewise not controlled through `ThreadPoolTaskExecutor.setKeepAliveSeconds`.
- An `@Async` method routed to a different executor bean will not inherit the parameters of the bean configured here.

Therefore, before analyzing the effect of `allowCoreThreadTimeOut`, verify **which executor is actually running the task**.

## 7. Performance Trade-offs: Save Resources or Reduce Cold-Start Latency?

Choose `allowCoreThreadTimeOut` based on traffic shape.

| Workload / goal | Starting suggestion | Rationale and trade-offs |
| --- | --- | --- |
| Steady traffic, short tasks arriving continuously | `false`, keep a reasonable core worker count | Workers remain warm, avoiding frequent thread-creation overhead |
| Infrequent jobs with occasional traffic spikes | `true` with moderate positive keep-alive | Long idle spells can shrink workers to 0, at the cost of thread creation on the next burst |
| Frequent bursts spaced seconds apart | Avoid tiny keep-alive values; try `false` or longer windows | Prevents continuous worker creation/destruction churn (thread churn) |
| Blocking I/O tasks, high parallel requests | Measure pool size, queue wait, max, downstream capacity | Keep-alive only governs **idle** workers; it does not solve blocked tasks |
| Need memory savings during inactivity | Try `true` while bounding core/max/queue to load | Lowers idle resource usage, without guaranteeing lower peak usage |

**No single keep-alive value is optimal for every service.** Good tuning depends on task duration, arrival frequency, latency sensitivity, scaling behavior, CPU/memory limits, and thread creation cost. Raising worker retention generally lowers thread churn while consuming more resources during quiet periods; lowering retention saves idle resources while potentially adding startup latency when traffic returns.

### Metrics to Monitor

- **`poolSize`:** total live workers at measurement time; distinct from configured `corePoolSize`.
- **`activeCount`:** workers actively executing tasks, generally an approximate metric.
- **`queue.size()`:** waiting tasks; long queues raise latency risk.
- **`completedTaskCount` and throughput:** completed tasks, indicating service capacity.
- **Rejection count, task duration, queue waiting time, p95/p99 latency, CPU, and memory:** reflect real system impact.

With `ThreadPoolTaskExecutor`, several readings are directly accessible:

~~~java
// Fragment in an application that already has an executor variable of type ThreadPoolTaskExecutor.
int workers = executor.getPoolSize();
int running = executor.getActiveCount();
int waiting = executor.getThreadPoolExecutor().getQueue().size();
boolean coreTimeout =
        executor.getThreadPoolExecutor().allowsCoreThreadTimeOut();
~~~

These reads are **snapshots** that can change immediately afterward; they suit monitoring/diagnostics, not task-orchestration logic. Never write business logic like "if queue equals 0, the next task will definitely run immediately."

### Runtime Reconfiguration

Spring's Javadoc notes that `setKeepAliveSeconds(...)` supports runtime adjustment, such as via JMX. However, when updating a live pool, check validity against `allowCoreThreadTimeOut`: you cannot set keep-alive to 0 while core timeout is enabled. Changes to `corePoolSize`/`maxPoolSize` can also affect how many workers are retained or reclaimed.

If runtime updates are required, manage changes through a controlled, observable configuration mechanism; do not assume editing a properties file automatically updates an already initialized bean. Structural setters like `queueCapacity` mainly take effect when creating the queue; never assume they dynamically resize an existing queue.

## 8. Common Misconceptions

1. **"`keepAliveSeconds=30` forces every task to finish within 30 seconds."** False. It is the **idle worker wait limit**, not a task deadline. Business, HTTP, and DB timeouts must be configured separately.
2. **"`corePoolSize=4` means 4 threads exist as soon as the bean is created."** False. By default core workers are created on demand; pre-creation requires `setPrestartAllCoreThreads(true)`. Even when prestarted, enabling core timeout still allows idle reclamation.
3. **"`allowCoreThreadTimeOut=true` removes `corePoolSize` from the pool."** False. The core threshold still governs task acceptance and expansion rules; only idle core retention changes.
4. **"`maxPoolSize=100` guarantees 100 workers under heavy load."** False. The pool prioritizes queuing after reaching core; if the queue never fills, non-core workers may never be created.
5. **"`keepAliveSeconds=0` with core timeout true releases threads instantaneously."** False. The JDK **rejects** `allowCoreThreadTimeOut(true)` with zero keep-alive.
6. **"A worker terminated by keep-alive cancels its task."** False. Only **idle** workers are eligible for reclamation; running tasks are never stopped by this setting.
7. **"Enabling core timeout acts as a service shutdown mechanism."** False. The pool stays active and recreates workers for new tasks; shutdown is a separate lifecycle action.
8. **"`ThreadPoolTaskExecutor` and all Spring `TaskExecutor` types share these properties."** False. Different implementations have different thread management models.
9. **"Just running `Thread.sleep(500)` and checking `getPoolSize()` proves absolute correctness."** False. Dynamic state depends on scheduling; observe over adequate durations with latency-tolerant checks.

## 9. Self-Check Questions

**Question 1.** A pool has `corePoolSize=3`, `maxPoolSize=8`, `keepAliveSeconds=20`, and `allowCoreThreadTimeOut=false`. Once traffic stops, how are workers reclaimed?  
**Answer:** Workers above core can expire after roughly 20 seconds of idleness. Created core workers are retained when idle.

**Question 2.** With the same settings except `allowCoreThreadTimeOut=true`, what can the final worker count drop to?  
**Answer:** It can drop to **0** if all workers sit idle long enough; `corePoolSize=3` remains the configuration parameter for future tasks.

**Question 3.** Does a pool with `corePoolSize=2`, `maxPoolSize=20`, `queueCapacity=Integer.MAX_VALUE` necessarily scale to 20 workers under high load?  
**Answer:** No. Once 2 core workers exist, new tasks normally enter the nearly unbounded queue, so the pool rarely needs to create workers beyond core.

**Question 4.** Is enabling `allowCoreThreadTimeOut=true` while `keepAliveSeconds=0` valid?  
**Answer:** No. The JDK requires a positive keep-alive for core threads to be allowed to time out.

**Question 5.** Will a task making an HTTP call longer than the keep-alive duration be interrupted?  
**Answer:** Not by keep-alive. The worker is actively executing a task; you need separate HTTP client or business timeouts.

**Question 6.** Why does enabling core timeout save resources during low traffic while potentially increasing latency for the first request after an idle spell?  
**Answer:** The pool may have reclaimed all workers and must create a new thread when the next task arrives.

## 10. Official References

- [Spring Framework 6.2.14 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): `setKeepAliveSeconds`, `setAllowCoreThreadTimeOut`, `corePoolSize`, `maxPoolSize`, `queueCapacity`, and defaults.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor Javadoc](https://www.springframework.org/spring/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): API matching the version used in the Maven example.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): worker/queue growth rules, idle keep-alive, core timeout, rejection, and monitoring.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor` implementations, configuration, and executor selection for asynchronous processing.
