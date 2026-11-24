# SimpleAsyncTaskExecutor: One Thread per Task, No Thread Reuse

**SimpleAsyncTaskExecutor** is an implementation of **TaskExecutor** in Spring Framework. When it receives a task, it launches that task on **a new thread**. It **does not maintain a pool of workers to reuse threads** for subsequent tasks. This is the defining characteristic when choosing an executor: submitting tasks is very simple, but thread-creation overhead and concurrency levels can become large if there are many calls.

This lesson belongs to the **Spring Framework - concurrency** topic, under the **Executor Selection** group. The focus is on accurately understanding SimpleAsyncTaskExecutor's thread-per-task mechanism, concurrency limits, operational impact, usage with **@Async**, differences from **ThreadPoolTaskExecutor**, and the **virtual threads option on JDK 21+** when appropriate.

## 1. TaskExecutor Is a Contract; It Does Not Mean a Thread Pool

Spring defines **TaskExecutor** to run a **Runnable**. Because this interface extends the **java.util.concurrent.Executor** contract, the core call is:

~~~java
void execute(Runnable task);
~~~

The key point: the interface specifies **submitting a task for execution**, without mandating a pool. Two implementations can accept the same Runnable yet schedule it completely differently:

| Executor | Where the task runs | Reuses threads? |
| --- | --- | --- |
| **SyncTaskExecutor** | Directly on the thread calling execute | Does not create new workers |
| **SimpleAsyncTaskExecutor** | A new thread for each execution | **No** |
| **ThreadPoolTaskExecutor** | Workers belonging to a thread pool | **Yes**, according to pool configuration |
| **ConcurrentTaskExecutor** | Delegates to another java.util.concurrent.Executor | Depends on the wrapped executor |

Therefore, the word **Async** describes that a task can run decoupled from the caller; it **does not guarantee** bounded execution, queuing, or lifecycle management like a thread pool.

## 2. How Does the Thread-Per-Task Mechanism Work?

In the default configuration using platform threads, on each call to **execute(task)**, SimpleAsyncTaskExecutor creates a new Thread and runs the task inside it. When the Runnable finishes, that thread terminates. The next execute call will use **a different thread**, even if the previous task has already completed.

~~~text
Calling thread / HTTP request
  |
  +-- execute(task A) --> create thread A --> run A --> thread A terminates
  |
  +-- execute(task B) --> create thread B --> run B --> thread B terminates
  |
  +-- execute(task C) --> create thread C --> run C --> thread C terminates

There is no idle-worker loop -> picking the next task from a pool queue.
~~~

Three practical consequences:

1. **Thread identity is not reused across two tasks.** If two tasks run sequentially, they still use two different threads. Do not infer reuse merely from the thread name prefix; check the Thread object or the executor's behavior.
2. **By default there is no limit on the number of concurrently running tasks** enforced by SimpleAsyncTaskExecutor. Actual platform-thread creation is still bounded by memory, the operating system, and process resources.
3. **There is no ThreadPoolExecutor-style task queue.** Tasks are not placed in a queue for an idle worker to pick up later; if a concurrency limit is enabled, waiting happens on the **submitter** side via throttling, as explained below.

Creating a new platform thread is not free: it requires a stack and JVM/OS management structures, incurring startup, context-switching, and memory costs. For many very short tasks, total thread overhead can exceed the cost of the task itself. For long-blocking I/O tasks, creating many platform threads can increase memory consumption without corresponding CPU utilization.

**Not reusing threads** is different from **not running in parallel**. If many tasks are submitted within a short time, they can coexist concurrently on different threads. How many tasks actually run on the CPU at the same time still depends on the core count, scheduler, and blocking state.

## 3. Runnable Example Using Java 17 and Spring Core

We will observe two tasks **submitted sequentially** to the same SimpleAsyncTaskExecutor. Each task records its Thread object. The result does not depend on how the JVM names threads or schedules CPU time.

Create a minimal Maven project with this structure:

~~~text
simple-executor-demo/
├── pom.xml
└── src/main/java/example/ExecutorIdentityDemo.java
~~~

**pom.xml** — Spring Core 6.2.12 running on Java 17+:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>simple-executor-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.2.12</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.ExecutorIdentityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/ExecutorIdentityDemo.java**:

~~~java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

public class ExecutorIdentityDemo {
    public static void main(String[] args) throws InterruptedException {
        try (SimpleAsyncTaskExecutor executor =
                     new SimpleAsyncTaskExecutor("lesson-")) {

            AtomicReference<Thread> first = new AtomicReference<>();
            AtomicReference<Thread> second = new AtomicReference<>();

            CountDownLatch firstStarted = new CountDownLatch(1);
            CountDownLatch secondStarted = new CountDownLatch(1);

            executor.execute(() -> {
                first.set(Thread.currentThread());
                firstStarted.countDown();
            });
            firstStarted.await();

            executor.execute(() -> {
                second.set(Thread.currentThread());
                secondStarted.countDown();
            });
            secondStarted.await();

            System.out.println("Both tasks ran: "
                    + (first.get() != null && second.get() != null));
            System.out.println("Reused same thread: "
                    + (first.get() == second.get()));
        }
    }
}
~~~

Run in the directory containing pom.xml:

~~~bash
mvn -q compile exec:java
~~~

**Program stdout** (excluding Maven messages if the environment prints any):

~~~text
Both tasks ran: true
Reused same thread: false
~~~

**Explanation:**

- **firstStarted** and **secondStarted** ensure main waits until each task has stored its Thread reference; there is no need to sleep for a guessed duration.
- Both **execute** calls share the same executor, but each runs on a new thread. The **==** comparison checks exact Thread object identity.
- **try-with-resources** is used because SimpleAsyncTaskExecutor in the illustrated version implements **AutoCloseable**. Every task in the example reaches its signal point before exiting the scope; handling unfinished tasks when closing the executor is explained separately.
- The example relies on **Spring Core**; you cannot simply run javac on this file without Spring libraries on the classpath. Maven manages the dependencies and compilation.

If you print **Thread.currentThread().getName()**, you may see names like lesson-1, lesson-2. That is a useful observation tool, but **you should not assert that every environment produces the same thread-name numbering** or use the name as the sole proof of thread identity.

## 4. What Does Unbounded Concurrency by Default Mean?

According to the SimpleAsyncTaskExecutor API, the default concurrency limit is **UNBOUNDED_CONCURRENCY** (value -1). In platform-thread mode, if hundreds of calls submit tasks nearly simultaneously, the executor can create hundreds of new threads; if thousands of tasks block on network I/O, it can create even more threads.

Illustrative reasoning:

~~~text
100 requests arrive at once
    |
    +--> each request calls execute(5-second blocking I/O task)
    |
    +--> nearly 100 task threads can exist during that wait window
    |
    +--> if load spikes uncontrollably:
          more stacks, context switching, OS resources
~~~

This is a behavioral diagram, **not a guarantee of a specific thread count**: submission rate, task duration, and system resource limits affect how many threads exist concurrently.

In particular, **SimpleAsyncTaskExecutor does not provide a mechanism to buffer tasks in a queue with a preconfigured capacity** like ThreadPoolTaskExecutor. To protect resources, you must design concurrency/submission-rate limits and rejection policies at the appropriate layer.

## 5. setConcurrencyLimit: Caps Active Tasks, Does Not Create a Pool

You can set **setConcurrencyLimit(n)** so that at most n tasks are allowed to execute concurrently. Example declaration in Spring:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

@Configuration
public class SimpleExecutorConfig {
    @Bean(destroyMethod = "close")
    public SimpleAsyncTaskExecutor perTaskExecutor() {
        SimpleAsyncTaskExecutor executor =
                new SimpleAsyncTaskExecutor("per-task-");
        executor.setConcurrencyLimit(8);
        executor.setTaskTerminationTimeout(5_000);
        return executor;
    }
}
~~~

This is a **configuration snippet for an application that already has a Spring Context**, not a standalone javac program. **The limit of 8 is just an example**; you must choose a number suited to CPU, I/O, downstream resources, and latency requirements. If 8 tasks are running and a 9th task is submitted to **execute**, the default behavior is to **block the task-submitting thread** until a slot opens and then create a new thread to run the 9th task.

~~~text
concurrencyLimit = 2

execute(A)  -> thread A runs ----------- finishes
execute(B)  -> thread B runs ----- finishes
execute(C)  -> caller must wait for a slot
                        |
                        +-- B finishes -> create new thread C -> C runs

C does not reuse thread B. There is no worker pool taking C from a queue.
~~~

| Configuration | Core behavior |
| --- | --- |
| Default (-1) | Does not throttle the number of running tasks on the executor side |
| setConcurrencyLimit(8) | Allows at most 8 concurrent tasks; extra submissions may block the submitter |
| setConcurrencyLimit(1) | Allows only one active task at a time, yet still creates a **new thread** for each task |
| setConcurrencyLimit(0) | Does not allow any task to start; not a configuration for normal use |
| setRejectTasksWhenLimitReached(true) | On Spring Framework **6.2.6+**, chooses to reject immediately when full instead of blocking the submitter by default |

**Distinguishing backpressure from a task queue:** when the submitter is blocked inside execute, web request threads can also become blocked. This can increase latency or exhaust request threads under overload. You can choose to **reject early** and return a clear overload response if your Spring version supports it, or use an executor with a bounded queue and a dedicated rejection policy.

If **setRejectTasksWhenLimitReached(true)** is enabled, Spring throws **TaskRejectedException** for an unaccepted submission. Callers must handle the rejection; it does not mean the task is saved to run later. If using a Spring Framework version older than 6.2.6, do not assume this method is available.

**Important:** the executor limit only governs the number of tasks *executing through that executor*; it does not limit total HTTP requests, DB connections, file descriptors, or calls across all application instances. Downstream resources still need their own limits.

## 6. SimpleAsyncTaskExecutor vs. ThreadPoolTaskExecutor

A common decision in Spring applications is choosing between **one thread per task** and **a pool of reused workers**.

| Criterion | SimpleAsyncTaskExecutor | ThreadPoolTaskExecutor |
| --- | --- | --- |
| Thread per task | Created fresh, terminates after task | Uses a worker from the pool |
| Thread reuse | No | Yes |
| Overhead with many short tasks | Increases due to continuous thread creation/destruction | Usually more efficient thanks to reuse |
| Concurrency control | concurrencyLimit; unbounded by default | corePoolSize, maxPoolSize, queueCapacity |
| Buffering waiting tasks in pool queue | No equivalent queue | Can have a configured queue |
| On overload | Blocks submitter by default with limit; newer versions support immediate reject | Depends on queue, pool, and rejection configuration |
| Shutdown/lifecycle | Has close API and optional wait for tasks; lacks pool-style coordinated lifecycle | Richer lifecycle/pause/shutdown controls |
| Suitable workloads | Deliberate task-per-thread use, moderate volume, or virtual-thread mode | Broadly suitable for high, frequent volume on platform threads |

Example of a bounded pool:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class PoolConfig {
    @Bean("boundedPool")
    public ThreadPoolTaskExecutor boundedPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(40);
        pool.setThreadNamePrefix("pool-");
        return pool;
    }
}
~~~

This is a **Spring configuration snippet** for comparison, not the result of a benchmark. When `ThreadPoolTaskExecutor` is created as a Spring bean, the container automatically calls `initialize()` during its lifecycle; calling it manually here could initialize the pool twice unnecessarily. With ThreadPoolTaskExecutor, the queue affects when the pool creates additional workers beyond the core size. You cannot look only at maxPoolSize and conclude there are always 8 workers for every load.

**Resources are not the same as processing capacity:** using more threads than CPU cores does not speed up CPU-bound computation indefinitely. For I/O-bound work, extra concurrency can help hide wait times, but must be balanced against connection pools, rate limits, and timeouts.

## 7. Virtual Threads Option on Java 21+

Starting in Spring Framework **6.1**, SimpleAsyncTaskExecutor can use **JDK 21 virtual threads** via:

~~~java
SimpleAsyncTaskExecutor executor =
        new SimpleAsyncTaskExecutor("virtual-task-");
executor.setVirtualThreads(true);
~~~

This is a **configuration snippet for JDK 21+ and a supported Spring Framework version**. On Java 17, do not enable this option.

**What does not change:** it is still a model of **one new virtual thread per task**, with no pool reusing virtual threads. What changes is the per-thread cost: virtual threads are managed by the JVM and are lighter than platform threads for many supported blocking I/O tasks. Saying “one thread per task” does not mean “each task occupies one platform thread for its entire lifetime” when running in virtual mode.

**Boundaries to keep in mind:**

- Lightweight virtual threads **do not make DB connections, RAM, file descriptors, or external API quotas infinite**.
- For CPU-bound work, the number of cores remains the limit on parallel execution.
- If tasks hold locks, perform unsupported blocking, or hit specific pinning/mounting scenarios, benefits may be lower than expected; measure on the actual runtime.
- You may still need **setConcurrencyLimit** or a semaphore to protect downstream resources. Virtual threads by themselves are not a rate limiter.
- You cannot take platform thread-pool sizing formulas and apply them directly to virtual-thread-per-task. Decisions must be based on workload type and the resources actually held.

**Selection guidance example:** a Java 21 application with thousands of short or medium independent I/O tasks can consider virtual threads; a CPU-heavy system should control execution concurrency according to CPU capacity rather than growing running tasks unboundedly.

## 8. Specific Usage with @Async in Spring

**@Async** marks a method so Spring can invoke it via an executor rather than running it entirely on the caller's thread. You can choose a named executor to avoid relying on the application's default configuration.

Spring configuration (assuming the application has a Spring Context and dependencies for @Async):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration {
    @Bean(name = "perTaskExecutor", destroyMethod = "close")
    public SimpleAsyncTaskExecutor perTaskExecutor() {
        SimpleAsyncTaskExecutor executor =
                new SimpleAsyncTaskExecutor("async-task-");
        executor.setConcurrencyLimit(12);
        executor.setTaskTerminationTimeout(5_000);
        return executor;
    }
}
~~~

Illustrative service:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    @Async("perTaskExecutor")
    public CompletableFuture<Integer> calculate(int basePrice) {
        int result = basePrice + 10;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

When **another bean** calls **priceService.calculate(100)** through the Spring proxy, the call executes on a thread created by perTaskExecutor. The caller receives a future object to wait on or chain steps, for example:

~~~java
CompletableFuture<Integer> price = priceService.calculate(100);
CompletableFuture<String> text =
        price.thenApply(value -> "Price: " + value);
String result = text.join();
~~~

This is an **illustrative snippet inside a method**, assuming priceService has been injected. Upon successful completion, **result** has the value **"Price: 110"**. The **join()** call blocks if the result is not yet ready; there is no automatic guarantee that the caller always proceeds without waiting.

Why does the @Async method return **completedFuture**? The method body has already been invoked asynchronously on the executor by the Spring interceptor; it can return a future representing the newly computed result. Spring bridges the asynchronous facility for the caller at the proxy boundary. Unnecessarily wrapping another **CompletableFuture.supplyAsync** inside the method can cause the task to hop onto yet another executor and complicate management.

**Integration points not to confuse:**

- **@EnableAsync** (or an equivalent configuration) must be enabled.
- In standard proxy mode, calling **this.calculate(...)** from the same bean bypasses the interceptor; it is not guaranteed to move to a new thread.
- **@Async("perTaskExecutor")** selects the executor explicitly; do not assume every Spring Boot application uses SimpleAsyncTaskExecutor by default. Executor resolution depends on Spring/Boot config and existing beans.
- **@Async void** does not give the caller a future to retrieve exceptions; see the **AsyncUncaughtExceptionHandler** mechanism if needed. With **Future/CompletableFuture**, the caller can observe success or failure.
- You must account for **rejection and blocking at task-submission time** if the concurrency limit is reached, even though the method is named @Async.

## 9. New Threads and Thread-Bound Data: Watch Out for Context

Values such as **MDC logging**, **SecurityContext**, transactions, or request attributes are often bound to the current thread. A new thread from SimpleAsyncTaskExecutor is **not automatically guaranteed** to carry all caller values according to request semantics.

For example, an HTTP call attaches requestId to log MDC. If the task runs on a new thread, logs inside the task may lose requestId without a context-transfer mechanism. Do not solve this by stuffing request data into a singleton field so “any thread can read it”: that causes cross-request data leaks.

Instead:

1. **Pass business data** that is needed via parameters or an immutable request snapshot.
2. Use Spring's **TaskDecorator** mechanism for appropriate logging/tracing context needs. The wrapper must copy and clear context within a well-defined scope of work; in particular, do not blindly transfer the entire security context.
3. If transferring **SecurityContext** is necessary, use the Spring Security integration class appropriate for your authorization model and task lifecycle.
4. Do not assume an open transaction on the caller will automatically follow across threads; define transaction boundaries where actual execution occurs.

**Not reusing threads** can reduce one class of bugs (“thread pool reusing a thread with stale ThreadLocal”), but it **does not solve context propagation** and does not replace proper cleanup. Request data must still have a clear owner.

## 10. Task Exception Management

With SimpleAsyncTaskExecutor:

- When running via **execute(Runnable)**, exceptions occur on the task thread; a caller that already returned from execute generally cannot catch that exception with a try/catch wrapping the submission call after the task starts. Appropriate logging/error handling for the environment is needed.
- When running via the **submit(Callable/T)** API returning a Future, the caller can retrieve the result with get() and handle ExecutionException. A Future does not make the task synchronous; the get call can block.
- With **@Async returning CompletableFuture**, the caller can use **exceptionally**, **handle**, or **whenComplete** to process or observe errors under CompletableFuture semantics.
- If a limit is configured and the executor **rejects at submission time**, that is a **submission** failure rather than a worker execution error. Distinguish these two error paths when returning responses and logging.

Example chaining a future in the illustrative service section:

~~~java
CompletableFuture<String> safeText = priceService.calculate(100)
        .thenApply(price -> "Price: " + price)
        .exceptionally(error -> "Price temporarily unavailable");
~~~

This is an **illustrative snippet** of a recovery branch after a future has been returned. **If calling calculate already threw an error immediately when submission was rejected**, the exceptionally stage has no future to attach to; it must be handled separately at the call site. In production, fallbacks should only be applied when business rules permit, while still recording the underlying cause.

## 11. Shutdown and Lifecycle: No Pool to Drain Like a Pool

Each task creates a new thread and there is no long-lived set of workers to retain. Consequently, SimpleAsyncTaskExecutor's lifecycle has distinct traits:

- It provides **close()** in modern Spring versions. **Closing the executor does not mean every task automatically finishes with an infinite wait.**
- **setTaskTerminationTimeout(milliseconds)** requests a wait duration for tasks to finish upon close. The default is **0**, meaning no wait. When a positive timeout is enabled, the executor must **track active threads**, which adds overhead worth considering when task counts are very large.
- Do not treat SimpleAsyncTaskExecutor as a **pool with a coordinated start/stop lifecycle** similar to ThreadPoolTaskExecutor. It provides no mechanism to pause/resume a worker pool; already handed-off running threads cannot be centrally managed like pooled workers.
- A long-running task that does not respond to interrupts or I/O cancellation can continue existing even when the system wants to shut down; deadlines and cancellation mechanisms are required at the task/I/O-tool layer.

In the earlier configuration example, **@Bean(destroyMethod = "close")** tells Spring to call close when the bean is destroyed. **setTaskTerminationTimeout(5_000)** is a policy to wait at most 5 seconds during close; it does not replace timeouts on HTTP clients or DB queries.

If you need shutdown tightly coordinated with application lifecycle, queue control, and rejection policies, **ThreadPoolTaskExecutor** is generally the more flexible choice.

## 12. Overhead, High Load, and When Not to Choose It

Consider tasks of type A and B:

**A — thousands of small computations, each running under a few milliseconds.** A SimpleAsyncTaskExecutor on platform threads creates a new thread for each computation. Startup/teardown, scheduling, and context-switching overhead can make up a large fraction of the work. A bounded fixed pool may be more sensible, though throughput and latency must be measured.

**B — many I/O calls that can block for several seconds.** With platform threads, each task can hold a thread while waiting. If submitted unboundedly, thread counts swell with traffic. Virtual threads on JDK 21 can improve thread overhead for this scenario, but request concurrency, connection pools, and target service limits can still be exhausted.

**C — a small number of independent, short tasks, or tasks with a clear testing goal.** The simple, easy-to-observe per-task-thread model may suffice. When this component becomes the executor for large, sustained workloads, it should be re-evaluated.

### Signs You Should Revisit the Configuration

- Live thread counts rise with traffic, accompanied by increased JVM/OS memory or native thread pressure.
- Latency at the task-submission point increases because **setConcurrencyLimit** blocks the submitter.
- Many request threads wait to submit tasks; this wait is outside task execution time and is easy to overlook when measuring.
- Tasks are rejected or the JVM struggles to create threads as request volume rises.
- Long I/O tasks without timeouts cause threads/resources to pile up.
- There is no mechanism limiting tasks calling databases/external services.
- Tests only measure average throughput without measuring p95/p99 latency, active task counts, and overload behavior.

**Optimization is not just swapping executors.** You must reduce unnecessary blocking, batch where sensible, protect downstreams, and control queues and total workload; select an executor based on CPU-bound/I/O-bound characteristics alongside operational requirements.

## 13. Testing and Observing Executor Characteristics Accurately

To verify **no thread reuse**, the example in section 3 compared the **Thread identity** of two sequentially submitted tasks. You can expand tests to:

1. Submit multiple tasks, recording **Thread.currentThread()** and the number of started/finished tasks.
2. Verify that each task runs on its own thread rather than concluding from log order or thread names.
3. With concurrency limit N, create N tasks holding a **CountDownLatch** and then submit task N+1 from **another submitter thread**. Verify that the caller blocks or rejects as configured; then release the latch so the test does not deadlock.
4. With a Spring context, confirm that the **@Async("perTaskExecutor")** bean is actually invoked through the proxy; if a test calls new Service() directly, the annotation is not applied.
5. Test failure, overload, and shutdown paths, not just the happy path.

However, concurrency tests relying solely on **Thread.sleep** are very flaky due to scheduler jitter. Use CountDownLatch/Barrier for coordination; always set test timeouts to catch hangs, and clean up the executor in finally/try-with-resources.

### Useful Metrics

| Metric group | Question to answer |
| --- | --- |
| Task submitted / started / completed | Are any tasks backing up or failing? |
| Execute duration on the submitter side | Are callers blocked due to concurrencyLimit? |
| Task execution duration | Is the task slow due to business logic or I/O? |
| Thread counts / memory | Is load causing platform threads to grow dangerously? |
| Rejections / exceptions | Does overload happen at submission or in the worker? |
| Downstream pool / rate limit | Are the database or target APIs bottlenecking before the executor? |

Do not rely on an “active threads in pool” metric that does not exist in the pool-worker sense for SimpleAsyncTaskExecutor. If you need the count of running tasks, record it with explicit instrumentation or a wrapper; do not assume this API provides all ThreadPoolTaskExecutor metrics.

## 14. Important Misconceptions

**“SimpleAsyncTaskExecutor is a simple thread pool.”** False. It creates a new thread for each task and does not reuse workers like a pool.

**“Not reusing threads means only one task runs at a time.”** False. By default, multiple tasks can run concurrently on multiple new threads.

**“Setting concurrencyLimit(10) means 10 workers are always kept ready.”** False. The limit caps how many tasks can be active concurrently; the executor still creates a new thread per task and does not keep 10 workers for reuse.

**“When the limit is full, the next task sits in a queue.”** Not via a pool queue mechanism. With the default configuration when a limit is set, the submitting thread blocks until a slot is free. Spring 6.2.6+ also offers an option to reject immediately.

**“Submitting a task with @Async guarantees the request thread never blocks.”** False. Even though task execution moves to another thread, the submission point can block when the executor throttles, and a subsequent get()/join() call still blocks.

**“Virtual threads are a new pool and remove all resource limits.”** False. Virtual threads are still per-task; database connections, memory, and external service throughput remain finite.

**“If the task's thread is brand new, there is no need to pass request context.”** False. A brand new thread is even less able to know the caller's business data unless passed via parameters or managed context propagation.

**“Closing the executor waits for all tasks to finish by default.”** Do not assume this. Read the close/termination timeout policy of the version you use and make an explicit choice.

## 15. Self-Check Questions

1. **Task A finishes before B is submitted. Does SimpleAsyncTaskExecutor reuse thread A for B?** No. B gets a new thread.
2. **If concurrencyLimit=2 is configured and two tasks are running, how is a third task submitted?** By default, the caller blocks until a slot frees up; there is no worker-pool queue.
3. **To reuse workers across many short tasks, what should you use?** Consider ThreadPoolTaskExecutor with properly configured core/max/queue/rejection settings.
4. **Does enabling setVirtualThreads(true) on Java 21 use a thread pool?** No. It still creates a new virtual thread for each task.
5. **What if @Async fails to work because one method in the same bean calls itself?** Because self-invocation bypasses the Spring proxy in normal proxy mode, not because SimpleAsyncTaskExecutor fails to create threads.
6. **How do a task exception and a submission-time exception differ?** A task error occurs after the worker starts; a submission rejection error occurs immediately on the caller when the task is not accepted.
7. **Does capping concurrent tasks replace DB connection limits?** No. You still need to control downstream resources and separate retry/timeout behavior.
8. **How do you confirm two tasks did not use the same thread?** Store and compare the Thread.currentThread() objects inside the tasks, rather than just looking at logs that do not guarantee ordering.

## 16. How to Make the Choice

When evaluating SimpleAsyncTaskExecutor, answer in order:

1. **Is the workload CPU-bound or I/O-bound?** How many tasks/sec, what is the p95/p99 duration per task, and what is the primary blocking point?
2. **Do you need to reuse platform threads?** If there are many small, repetitive jobs, a pool is usually beneficial.
3. **Can you limit active tasks and control submission?** If setting a limit, do you accept blocking callers or want early rejection?
4. **Which Java version are you running?** JDK 21+ and Spring virtual-thread support can change the choice, though they do not change downstream limits.
5. **Who manages lifecycle, errors, and context?** Are coordinated shutdown, propagation, metrics, and overload policies required?

**Conclusion:** SimpleAsyncTaskExecutor genuinely **creates a new thread for each task and does not reuse threads**. This is an intentional design trait to understand before using it, not an implementation bug. It fits when a thread-per-task model is chosen deliberately and concurrency is controlled; for high-volume, short, repetitive platform-thread workloads, **ThreadPoolTaskExecutor** is usually more appropriate. On Java 21+, **virtual threads** are worth evaluating for I/O workloads, while still protecting finite resources.

**Recommended references:** Spring Framework Reference — *Task Execution and Scheduling*; Javadoc for *org.springframework.core.task.SimpleAsyncTaskExecutor* and *org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor*; Java 21 documentation on virtual threads.
