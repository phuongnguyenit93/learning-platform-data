# Asynchronous Work Spawned by Runners Is Not Automatically Awaited

When a Spring Boot application starts up, `ApplicationRunner` and `CommandLineRunner` are two extension points for running logic **after the ApplicationContext has refreshed** yet **before normal startup is considered complete**. Spring Boot invokes and awaits **each runner's `run(...)` method returning**. However, if a runner merely submits work to an executor, launches a `CompletableFuture`, invokes an `@Async` method, or spawns its own thread and returns immediately, Spring Boot **does not automatically wait for that asynchronous work to finish**.

This is a crucial distinction:

- **Runner finishes**: the `run(...)` method has returned and is no longer running synchronously on the runner-invoking thread.
- **Asynchronous work finishes**: the thread or task launched by the runner has completed execution, handled results/errors, and released any required resources.
- **Application is reported ready**: Spring Boot has passed through normal startup steps, including invoking runners; by default, this **does not guarantee** that background work initiated by runners has completed.

If a background task is actually a **mandatory precondition** for the service to accept traffic safely, you must explicitly design waiting, readiness state, or a coordination mechanism. Never treat `ApplicationReadyEvent` as a signal that all async tasks have finished.

## 1. Where Do Runners Sit in the Startup Sequence?

Spring Boot supports two common interfaces:

~~~java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

~~~java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

Both interfaces have a method named `run`, though `ApplicationRunner` receives a parsed `ApplicationArguments` object while `CommandLineRunner` receives the original command-line string array.

After context refresh succeeds, Boot handles the major milestones in order:

~~~mermaid
flowchart TD
    A["SpringApplication.run(args)"] --> B["Create and refresh ApplicationContext"]
    B --> C["ApplicationStartedEvent"]
    C --> D["Invoke ApplicationRunner and CommandLineRunner beans"]
    D --> E{"Runner returns or throws?"}
    E -->|"Returns"| F["Continue remaining runners if any"]
    F --> G["ApplicationReadyEvent"]
    G --> H["SpringApplication.run returns context"]
    E -->|"Throws unhandled error"| I["Handle startup failure"]
    D -.-> J["Runner submits task to executor"]
    J -.-> K["Task runs on another thread"]
    K -.-> L["Task finishes or fails later"]
~~~

The dashed path represents the asynchronous task branch: Spring Boot **does not automatically wire** that branch into the condition for publishing `ApplicationReadyEvent`. If `runner.run(...)` throws an exception synchronously, startup can fail. Yet if an exception occurs **after the runner has returned**, inside a background task, that error does not automatically become an exception from `SpringApplication.run(...)`.

The `ApplicationReadyEvent` step marks that Boot has completed the normal startup flow and runners have returned. The default readiness state is also updated by Boot according to its lifecycle. There is no default guarantee that every task spawned by runners is awaited to completion.

## 2. Distinguishing Synchronous and Asynchronous Calls

**Synchronous runner:**

~~~java
@Bean
ApplicationRunner synchronousRunner() {
    return args -> {
        System.out.println("Starting work");
        performRequiredWork(); // Synchronous call.
        System.out.println("Work finished");
    };
}
~~~

The snippet above **is illustrative only**, assuming `performRequiredWork()` is defined and actually runs synchronously. In that case, Boot cannot move past the runner until the method returns or throws an exception.

**Runner submitting an async task:**

~~~java
@Bean
ApplicationRunner backgroundRunner(ExecutorService executor) {
    return args -> {
        executor.submit(() -> performRequiredWork());
        System.out.println("Task submitted, runner about to finish");
    };
}
~~~

This is also an **illustrative snippet**, requiring an `ExecutorService` and a `performRequiredWork()` method. `submit(...)` returns a `Future` as soon as the task is accepted, without waiting for the result. If the `Future` is ignored, the runner ends right after `submit(...)` and the print statement. The task may not have started yet, may be running, may have finished, or may fail later.

Core point: **calling an async API does not mean Boot will track or await that task**. The application author must decide whether waiting is necessary, how long to wait, and what the application should do if the task fails.

## 3. Runnable Example: Ready and run Return While Task Is Unfinished

This example uses **Java 17+ and Spring Boot 3.3.5** for concrete, easily reproducible dependency versions. It uses a `CountDownLatch` as an intentional "gate": the task cannot complete before `SpringApplication.run(...)` returns. As a result, the observed line ordering is deterministic, independent of CPU speed.

### Project Structure

~~~text
async-runner-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/runner/AsyncRunnerDemo.java
        └── resources/
            └── application.properties
~~~

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>async-runner-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Create `src/main/resources/application.properties` to reduce extra logs while learning:

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
~~~

Create `src/main/java/com/example/runner/AsyncRunnerDemo.java`:

~~~java
package com.example.runner;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AsyncRunnerDemo {

    public static void main(String[] args) throws InterruptedException {
        SpringApplication app = new SpringApplication(AsyncRunnerDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            JobState state = context.getBean(JobState.class);

            System.out.println(
                    "4. run returned; completed=" + state.completed.get());

            // main itself releases the task, not Spring Boot.
            try {
                state.allowCompletion.countDown();
                state.finished.await();
                System.out.println(
                        "6. main observed; completed="
                                + state.completed.get());
            } finally {
                state.allowCompletion.countDown();
            }
        }
    }

    @Bean
    JobState jobState() {
        return new JobState();
    }

    @Bean(destroyMethod = "shutdown")
    ExecutorService jobExecutor() {
        return Executors.newSingleThreadExecutor();
    }

    @Bean
    ApplicationRunner startBackgroundJob(
            JobState state, ExecutorService jobExecutor) {

        return args -> {
            System.out.println("1. runner: submitting job");

            jobExecutor.execute(() -> {
                try {
                    state.allowCompletion.await();
                    state.completed.set(true);
                    System.out.println("5. background: job completed");
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    System.out.println("5. background: interrupted");
                } finally {
                    state.finished.countDown();
                }
            });

            System.out.println(
                    "2. runner: returned, completed="
                            + state.completed.get());
        };
    }

    @Bean
    ApplicationListener<ApplicationReadyEvent> readyListener(
            JobState state) {
        return event -> System.out.println(
                "3. ApplicationReadyEvent; completed="
                        + state.completed.get());
    }

    static final class JobState {

        final CountDownLatch allowCompletion = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(1);
        final AtomicBoolean completed = new AtomicBoolean(false);
    }
}
~~~

### Running and Results

Java 17+ and Maven must be installed. In the directory containing `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

If the project has a Maven wrapper, replace with `./mvnw -q spring-boot:run` (Windows PowerShell: `.\mvnw.cmd -q spring-boot:run`).

With exactly these three files and no other application components, **stdout printed by this class on success** is:

~~~text
1. runner: submitting job
2. runner: returned, completed=false
3. ApplicationReadyEvent; completed=false
4. run returned; completed=false
5. background: job completed
6. main observed; completed=true
~~~

Ignore Maven/JVM-specific messages if your environment prints any. `logging.level.root=ERROR` and `banner-mode=off` reduce routine Boot logs; the output above describes solely the lines intentionally printed by the example.

**Line-by-line explanation:**

1. The runner starts and submits a `Runnable` to `ExecutorService`. The worker thread may start very early, yet pauses at `state.allowCompletion.await()`.
2. The runner prints `completed=false` and returns. There is no `Future.get()` or `CountDownLatch.await()` call inside the runner.
3. Boot proceeds to publish `ApplicationReadyEvent` even though the background task has not completed.
4. `SpringApplication.run(...)` returns an active `ConfigurableApplicationContext`. At this moment, the task is still waiting at the "gate."
5. **Code inside `main` itself** calls `allowCompletion.countDown()` after line 4; only then is the task permitted to finish and print line 5.
6. `main` explicitly calls `finished.await()` to observe task completion, prints line 6, and then closes the context. This is behavior we wrote into the example, **not an automatic waiting feature of Boot**.

The example uses `AtomicBoolean` to share state safely across threads and `CountDownLatch` to enforce predictable ordering. This is a learning verification tool, **not a recipe to copy into every production application**. In real applications, tasks usually receive work via queues, services, or executors under explicit operational policies.

`@Bean(destroyMethod = "shutdown")` tells Spring to call `shutdown()` on the executor when the context closes. However, `ExecutorService.shutdown()` **does not automatically await completion of all tasks**; hence the example awaits `finished` before closing the context. Closing the context and having finished all work are two separate things to distinguish.

## 4. What Spring Boot Actually Waits For

During normal startup:

- **Waited on:** synchronous execution of `ApplicationRunner.run(ApplicationArguments)` or `CommandLineRunner.run(String...)`, including calls that the runner itself explicitly awaits.
- **Not automatically waited on:** a `Thread` after `start()`, a task submitted via `executor.submit(...)`, an unjoined `CompletableFuture`, or `@Async` work dispatched through a proxy.
- **Can fail startup:** an unhandled exception thrown synchronously out of the runner, including an exception from `Future.get()` if the runner calls it.
- **Does not automatically fail startup:** an exception occurring solely inside a background task **after the runner returns**. The task needs its own error-recording and handling path.

One easily overlooked detail: `ExecutorService.execute(...)` can throw `RejectedExecutionException` immediately at submission time if the executor rejects the task. That is a **synchronous error inside the runner** and can fail startup. Conversely, an exception thrown inside code accepted by the executor for later execution does not automatically travel back to the runner-calling thread.

## 5. When Should You Wait for a Task Right Inside the Runner?

Some tasks **must complete before the application accepts traffic**: for instance, loading critical configuration with no fallback, verifying schema compatibility, or initializing internal data guaranteed to be needed by the very first request.

If completion time is reasonable and measurable, the runner can **wait explicitly**:

~~~java
@Bean
ApplicationRunner requiredInitialization(ExecutorService executor) {
    return args -> {
        Future<?> future = executor.submit(() -> {
            // Perform a mandatory initialization step.
            initializeRequiredData();
        });

        try {
            future.get(30, TimeUnit.SECONDS);
        } catch (TimeoutException ex) {
            future.cancel(true);
            throw new IllegalStateException(
                    "Initialization exceeded 30 seconds", ex);
        } catch (InterruptedException ex) {
            future.cancel(true);
            Thread.currentThread().interrupt();
            throw ex;
        }
    };
}
~~~

The snippet above is an **illustrative pattern to place in a Spring configuration class**, not a standalone program. It requires imports for `java.util.concurrent.Future`, `TimeUnit`, `TimeoutException`, `InterruptedException`, and an application-defined `initializeRequiredData()` method. Execution exceptions from the task may also be wrapped in `ExecutionException` and thrown from `Future.get(...)`. `ApplicationRunner.run(...)` permits throwing `Exception`.

Outcome of this design:

- If the task completes, `future.get(...)` returns, the runner ends, and only then does Boot advance to ready.
- If the task throws an error, the runner receives the exception via `Future.get(...)`; startup can be marked failed.
- If the task does not finish within 30 seconds, the runner proactively reports an error instead of waiting forever.
- `future.cancel(true)` only **requests** cancellation/interruption; it does not guarantee running code actually stops, especially when I/O or libraries ignore interrupts.

This is an example of a background task **with explicit waiting**; it does not contradict the rule "Boot does not automatically await async." Boot is simply waiting on the runner, while the runner itself decided to await the `Future`.

**Never wait indefinitely** on a task depending on a network, queue, or external service. If the task is a consumer intended to run forever (e.g., continuously polling Kafka), waiting for it to terminate prevents startup from ever reaching ready. For continuous services, distinguish "started and ready to receive work" from "finished processing all work."

## 6. `CompletableFuture`: Very Easy to Write Fire-and-Forget

Example:

~~~java
@Bean
ApplicationRunner warmupRunner(Executor executor) {
    return args -> {
        CompletableFuture<Void> job =
                CompletableFuture.runAsync(
                        () -> warmUpLocalCache(), executor);

        // No join/get/handle: the runner can return immediately.
        System.out.println("Warm-up requested");
    };
}
~~~

This illustrative snippet requires `java.util.concurrent.CompletableFuture`, `Executor`, and a defined `warmUpLocalCache()` method. The `job` variable is created, yet nothing awaits or inspects its outcome. An exception inside `warmUpLocalCache()` usually causes the future to complete **exceptionally**; if nothing reads the future, the failure can go unnoticed by startup coordination.

There are two ways to handle this depending on requirements:

**A. The work is a startup precondition:**

~~~java
CompletableFuture<Void> job =
        CompletableFuture.runAsync(() -> warmUpLocalCache(), executor);

// Intentionally wait; task errors are wrapped and propagated to caller.
job.join();
~~~

`join()` can throw `CompletionException` when the task fails; if awaited without a bound, the runner can also block forever. With Java 17, you can enforce deadlines using `orTimeout(...)` or `get(timeout, unit)` APIs, along with exception handling and task cancellation policies. Avoid calling `join()` indiscriminately on tasks intended to live for the entire application lifetime.

**B. Background work that should not block startup:**

~~~java
CompletableFuture.runAsync(() -> warmUpLocalCache(), executor)
        .whenComplete((unused, error) -> {
            if (error != null) {
                log.error("Warm-up failed", error);
            } else {
                log.info("Warm-up completed");
            }
        });
~~~

This snippet requires a logger `log` and a `warmUpLocalCache()` method in the enclosing class. It lets you observe success/failure, yet **does not automatically make startup wait or fail**. If startup is already ready when warm-up fails, the system needs appropriate retry, degraded mode, or alerting mechanisms.

If no executor is passed to `CompletableFuture.runAsync(...)`/`supplyAsync(...)`, Java typically uses `ForkJoinPool.commonPool()`. That is a shared pool, not an executor owned by the Spring context. Do not rely on it for graceful shutdown, load bounding, or keeping the JVM alive for critical work. Choose an explicitly managed executor.

## 7. `@Async` Does Not Change the Runner Contract Either

Spring supports `@Async` when async execution is enabled, for instance:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

A service invoked through a Spring proxy can be written as:

~~~java
@Service
public class ReportWarmupService {

    @Async
    public CompletableFuture<String> prepare() {
        // Illustrative work.
        return CompletableFuture.completedFuture("ready");
    }
}
~~~

Then another runner bean calls it:

~~~java
@Bean
ApplicationRunner reportRunner(ReportWarmupService service) {
    return args -> {
        CompletableFuture<String> result = service.prepare();
        // Not calling result.get()/join(): the runner does not await the task.
    };
}
~~~

The three snippets above are **illustrative configurations**, requiring imports for Spring `@Configuration`, `@EnableAsync`, `@Service`, `@Bean`, `@Async`, and Java `CompletableFuture`. In real usage, replace the placeholder work with business logic and configure a suitable executor.

**Key points:**

- `@Async` operates through Spring's proxy/interceptor mechanism. Calling `this.prepare()` inside **the same object** typically bypasses the proxy and does not run asynchronously as intended.
- `@EnableAsync` or equivalent configuration must be enabled for `@Async` to be processed.
- Calling an `@Async` method through a proxy normally returns quickly, yet there is no rule requiring Spring Boot to await the future before `ApplicationReadyEvent`.
- For `@Async` methods returning `void`, there is no future for callers to collect errors; configure appropriate logging and an `AsyncUncaughtExceptionHandler` for unhandled exceptions.
- With `CompletableFuture<T>` or `Future<T>`, callers can actively track or await results/errors. Distinguish exceptions returned via the future from synchronous exceptions occurring when a call is rejected.
- Name and configure your executor explicitly. If using a default executor, understand its thread/queue bounds and how Spring manages it on your version.

Do not slap `@Async` onto a runner and assume Boot will somehow know when that work completes. The startup contract must be designed explicitly rather than inferred from annotation names.

## 8. `ApplicationReadyEvent` and Readiness Do Not Guarantee Background Jobs Are Done

In Spring Boot, `ApplicationStartedEvent` is published before startup runners execute, and `ApplicationReadyEvent` is published after runners finish synchronously. However:

~~~text
Startup:
  context refresh
  ApplicationStartedEvent
  runner submits task to queue --------> background task starts
  runner returns
  ApplicationReadyEvent                  background task still running
  SpringApplication.run returns          background task still running
                                         background task finishes
~~~

If a service uses readiness probes to decide when to send traffic, you must answer the question: **"Ready" means which initialization tasks must already have finished?**

There are three common design patterns:

| Requirement | Approach |
|---|---|
| Task must finish before receiving requests | Run synchronously or have runner explicitly await future with timeout, failing startup on error. |
| Task is helpful yet optional | Run in background, let app become ready, with logs/metrics/retries; requests must not strictly require unready results. |
| Task runs in background yet must report "not ready" until finished | Manage a dedicated readiness state wired into a health indicator/probe or lifecycle-coordinated availability mechanism. |

Spring Boot has states such as `ReadinessState.ACCEPTING_TRAFFIC` and `ReadinessState.REFUSING_TRAFFIC`. Boot itself publishes readiness states during the startup sequence, so if an application emits a readiness change event too early and Boot subsequently publishes `ACCEPTING_TRAFFIC`, the earlier state can be overwritten. Do not design task-dependent readiness around a single arbitrary state-change call inside a runner assuming it persists forever; verify the exact event-publication timing and health mechanism in use.

For critical jobs, consider defining a dedicated health indicator based on the job's successful completion state. Readiness then reflects an explicit business condition rather than inferring it merely from the runner having been called.

## 9. Executors, the JVM, and Resource Shutdown Responsibility

A task not automatically awaited by Boot still has real effects on process lifecycle. Several cases:

**Manually created unmanaged executor:**

~~~java
Executors.newSingleThreadExecutor().submit(this::runLongJob);
~~~

This is an illustrative snippet assuming `runLongJob()` and importing `Executors`. With the default thread factory, this type of executor typically creates **non-daemon threads**. Without calling shutdown, the Java process can stay alive even after main tasks finish; this issue is easily mistaken for "Spring Boot won't shut down."

**Tasks on daemon/common pools:** daemon threads do not keep the JVM alive. If no non-daemon threads remain, the JVM can exit before the task finishes. Hence you cannot assume a task submitted to the common pool will always finish in time after `main` returns.

**Executor registered as a Spring bean:**

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService jobExecutor() {
    return Executors.newFixedThreadPool(2);
}
~~~

The bean has an explicit destroy callback, so when Spring closes the context it calls `shutdown()`. Yet `shutdown()` only stops accepting new tasks and lets already-accepted tasks execute per the executor's contract; by itself it **does not mean awaiting completion**. If a bounded wait is required, the executor owner must implement logic such as `awaitTermination(timeout, unit)` or configure an executor/lifecycle component with an appropriate shutdown-wait policy.

With Spring's `ThreadPoolTaskExecutor`, you can configure thread counts, queue capacity, and shutdown wait settings (depending on version). More important than API names is the operational contract: **stop accepting new work, await in-flight work within a permitted bound, handle unfinished work, and close resources**. Critical tasks still need idempotency/retry policies in case the application is killed abruptly or loses power, because graceful shutdown is not an absolute guarantee.

Never create a new executor on every runner invocation without a clear shutdown and monitoring path. Never store an executor in a local variable and lose the reference while tasks are still running.

## 10. Background Exceptions Do Not Automatically Become Startup Failures

One of the hardest scenarios to diagnose:

~~~java
@Bean
ApplicationRunner example(ExecutorService executor) {
    return args -> {
        executor.submit(() -> {
            throw new IllegalStateException("remote index unavailable");
        });
    };
}
~~~

This is an illustrative example. `executor.submit(...)` returns a `Future`, yet the runner ignores it. If the task throws an exception, the `Future` completes in a failed state; the exception does not jump across to the runner's thread to fail `SpringApplication.run(...)`.

To detect failures, retain the future:

~~~java
Future<?> result = executor.submit(this::buildIndex);
try {
    result.get(20, TimeUnit.SECONDS);
} catch (ExecutionException ex) {
    throw new IllegalStateException(
            "Index build failed", ex.getCause());
}
~~~

This snippet belongs inside a method that already has `executor`, `buildIndex()`, and appropriate imports. In practice you also need to handle `InterruptedException` and `TimeoutException`; if choosing to fail startup, define task cancellation, deadlines, and cleanup policies.

In applications that do not block startup, at least monitor the future's status, log errors with causes, track metrics/duration, and use controlled retries. If the task updates state relied upon by HTTP requests, synchronize visibility across threads using `volatile`, `AtomicReference`, synchronized blocks, or thread-safe data structures.

## 11. Multiple Runners and `@Order` Do Not Serialize Async Tasks

Spring Boot allows registering multiple runner beans. Runner invocation order can be controlled with `@Order` or `Ordered`. Yet this order applies to **synchronous runner invocations**, not to queuing and awaiting all tasks submitted by each runner.

Example:

~~~text
Runner A (@Order(1)):
    executor.submit(taskA)
    return

Runner B (@Order(2)):
    readDataCreatedByTaskA()
    return
~~~

If `taskA` has not finished, runner B may read unready data even though `@Order(1)` is smaller than `@Order(2)`. When B depends on A's output, you should:

- Express dependencies between beans or initialization steps explicitly.
- Move the same mandatory synchronous flow into an orchestrating runner and wait accordingly.
- Or compose futures via `thenCompose(...)`, `allOf(...)`, `join()`, or a proper orchestration mechanism with deadlines and error handling.

Similarly, two separate `ApplicationContext` instances may each run runners and spawn their own background tasks. Context A's `ApplicationReadyEvent` does not mean context B's background tasks are done; nor does a sibling or parent event equate to system-wide business readiness.

## 12. Avoiding Deadlocks Caused by Improper Waiting

Explicit waiting is not always safe. A classic bug:

~~~text
Executor has only one worker thread
    |
    +-- Task A runs on the worker
           |
           +-- Task A submits Task B to THAT SAME executor
           |
           +-- Task A calls Future.get() waiting for Task B
                  |
                  +-- Task B cannot run:
                      the sole worker is held by Task A
~~~

That is a form of **thread-starvation deadlock**. Likewise, a startup bean callback or runner can wait on a task that itself waits on a bean, lock, resource, or event only published after the runner returns.

Protective principles:

- Never block inside a single-threaded executor's task waiting on another task that needs that same single-threaded executor.
- Set timeouts and inspect stack/thread dumps when startup appears hung.
- Never wait for an event Spring only publishes **after runners complete**—for instance, awaiting `ApplicationReadyEvent` inside a current runner causes a circular wait.
- Avoid using `Thread.sleep(...)` to "guarantee other work is done"; sleep only alters timing and establishes no reliable completion contract.
- For tasks needing results, consider composing an async pipeline and blocking only at an appropriate boundary, or using a matching startup mechanism.

A service that must continuously process messages should report "consumer registered/active" status appropriately rather than calling `join()` on an endless consumer loop hoping to reach ready.

## 13. Choosing a Strategy by Requirement Pattern

| Kind of Work Spawned by Runner | Should Startup Wait? | How to Control |
|---|---|---|
| Mandatory, fast, bounded config checks | Usually **yes** | Run synchronously or await `Future.get(timeout)`, failing startup on error. |
| Minimal data initialization strictly needed by endpoints | Usually **yes**, or mark readiness unready | Timeouts, clear errors, readiness reflecting actual state. |
| Optional cache warming | Not necessarily | Run in background, track completion, and allow fallback while cache is absent. |
| Multi-minute external data sync | Usually **do not block whole startup**, unless required by business | Separate job, persistence/checkpoints, retries, metrics, API tolerating in-progress state. |
| Continuously running consumer/scheduler | **Do not wait for termination** | Manage lifecycle, base readiness on registration/health state, shut down cleanly. |
| Generating reports or sending optional events | Possibly no | Durable queue or worker, retries/idempotency; avoid in-memory fire-and-forget if data must be preserved. |
| Mandatory migration/schema upgrade | Usually needs completion before serving requests | Dedicated migration tool, time bounds, handle multi-instance contention. |

The key choice is not "async vs. sync" but **the application's readiness contract**. State clearly what must finish, when the deadline is, where error visibility goes, and how the system behaves while the task is still incomplete.

## 14. Common Mistakes

**Mistake 1 — "`ApplicationRunner.run(...)` is awaited by Boot, so tasks it spawns are awaited too."**

False. Boot awaits **the runner invocation**, not the entire task tree created by the runner. `submit(...)`/`runAsync(...)` usually returns before the task finishes.

**Mistake 2 — "Seeing `ApplicationReadyEvent` means all warm-up tasks are complete."**

Not guaranteed. If a runner submits a background task and returns, the ready event can fire while the task is still executing.

**Mistake 3 — "An exception inside a future automatically causes a startup failure."**

Not when the runner ignores the future. Task errors must be propagated via `get/join` or handled asynchronously, depending on the goal.

**Mistake 4 — "`@Async` in the same class automatically runs on another thread."**

With standard Spring proxies, self-invocation bypasses the interceptor; to trigger async via proxy, invoke the method on a Spring bean across a properly configured proxy boundary.

**Mistake 5 — "Using `@Order` guarantees runner B sees data created by runner A's task."**

`@Order` orders runner invocations, with no guarantee about when A's background task finishes.

**Mistake 6 — "`ExecutorService.shutdown()` blocks until all tasks finish."**

No. To wait, add a mechanism like `awaitTermination(...)` or an appropriate lifecycle management policy.

**Mistake 7 — "While a background task exists, the JVM definitely stays alive."**

Not in all cases. Daemon threads do not keep the JVM alive; an un-shut-down non-daemon executor can instead prevent the process from exiting. Outcomes depend on thread factories, context lifecycle, and remaining threads.

**Mistake 8 — "Just call `Thread.sleep(1000)` before returning from the runner."**

A fixed wait proves nothing about task completion. Use `Future`, `CountDownLatch`, health state, or a synchronization mechanism with an explicit contract.

**Mistake 9 — "A task failing after ready doesn't matter because the app is still active."**

If data produced by the task is a mandatory request dependency, the service may stay active yet return wrong results or errors. Readiness/fallback/error reporting must match business requirements.

## 15. Self-Verification Lab

Starting from the Maven example in section 3, try one change at a time:

1. Remove `state.finished.await()` from `main`, while still releasing `allowCompletion`. Observe that `main` may close the context before you inspect completion status; log order outside remaining constraints must be treated as racing.
2. Move `allowCompletion.countDown()` inside the runner **before returning**. The task may complete before or after `ApplicationReadyEvent` depending on scheduling; there is no ordering guarantee like with the "gate."
3. Inside the runner, wait on `state.finished.await()` while the task still waits on `allowCompletion` which `main` only opens **after `app.run(...)` returns**. This is a **deadlock** example, because `main` cannot reach the latch release while the runner is waiting. Only try this variant once you understand it and have a way to terminate the test process.
4. Replace the executor in the example with `CompletableFuture.runAsync(...)` while keeping the completion logic. Confirm no default wait is added to startup.
5. Make the task throw an exception, retain `Future<?>` from `submit(...)`, and compare **not reading the future** versus **calling `get()` in the runner**. Compare whether Boot receives the exception during the startup flow.
6. Add a second runner with a larger `@Order` than the first runner. Confirm **submission order** can be controlled while **task completion order** still needs separate coordination.

### References

- Spring Boot 3.3 — SpringApplication, runners, and startup events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Application availability, liveness, and readiness: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability
- Java 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java 17 — `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html

**Remember:** Spring Boot waits for `ApplicationRunner.run(...)` / `CommandLineRunner.run(...)` methods to return; it **does not automatically wait for asynchronous tasks** launched by those methods. If work is mandatory before ready, the runner must explicitly wait with a deadline or the application must coordinate readiness according to real state. If work can run in the background, design executors, error visibility, retries, and shutdown explicitly—never treat fire-and-forget as a completion contract.
