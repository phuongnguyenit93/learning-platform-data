# Stopping with Completion Callbacks and Timeouts in Spring Framework

## Learning objectives

A Spring application may contain an HTTP server, message consumers, schedulers, executors, network connections, or background processes that need time to stop accepting work and finish in-flight tasks. When closing an `ApplicationContext`, calling `close()` on resources immediately sometimes loses work; conversely, waiting indefinitely for a worker can cause shutdown to hang.

Spring Core Container handles **context lifecycle coordination** using `Lifecycle`, `SmartLifecycle`, `LifecycleProcessor`, and the default implementation `DefaultLifecycleProcessor`. Specifically, `SmartLifecycle.stop(Runnable callback)` lets a component begin stopping, complete asynchronously, and then **report that it has stopped via callback**. The container waits for callbacks of **each shutdown phase** within a configured duration.

After this lesson, you will be able to:

- Understand why `stop(Runnable)` takes a callback and differs from plain `stop()`.
- Write a `SmartLifecycle` that auto-starts, stops asynchronously, and always reports completion at the right time.
- Order shutdown by `getPhase()` and dependencies.
- Configure a global timeout or per-phase timeouts via `DefaultLifecycleProcessor`.
- Understand accurately that timeouts govern container **waiting**, not a forced command to kill threads.
- Distinguish stop phases from `@PreDestroy`, `DisposableBean.destroy()`, and Spring Boot HTTP graceful shutdown.
- Test success, error, timeout, race condition, and forced shutdown paths.

## 1. Where does lifecycle stop sit when closing ApplicationContext?

In a normal context close, the flow can be summarized as:

~~~text
ApplicationContext.close()
       |
       v
Publish ContextClosedEvent
       |
       v
LifecycleProcessor.onClose()
       |
       +-- Identify running SmartLifecycle/Lifecycle beans
       +-- Group by phase and dependency relationships
       +-- Stop phases from highest to lowest
       +-- For SmartLifecycle: invoke stop(Runnable callback)
       +-- Wait for callbacks of components in the phase up to timeout
       |
       v
Destroy singletons (destruction callbacks)
       |
       +-- @PreDestroy
       +-- DisposableBean.destroy()
       +-- @Bean(destroyMethod = "...")
       |
       v
Finish closing context
~~~

**This is the normal shutdown workflow.** In certain abnormal scenarios, such as a failed context refresh or a bean destroyed outside the context-closing path, destruction methods may be called without a prior stop signal. Therefore, a bean holding resources must ensure cleanup is safe even if `stop()` never ran.

The terms "stop" and "destroy" carry different responsibilities:

| Operation | Purpose | Common mechanism |
| --- | --- | --- |
| Stop | Stop accepting work; give running work a chance to finish | `Lifecycle.stop()` / `SmartLifecycle.stop(Runnable)` |
| Wait for completion | Coordinate components before moving to another phase | `DefaultLifecycleProcessor` + callback/timeout |
| Destroy | Close final resources, release bean | `@PreDestroy`, `DisposableBean`, `destroyMethod` |
| Process exit | OS/runtime terminates JVM | SIGTERM, shutdown hook, container orchestration |

Not every Spring bean needs `SmartLifecycle`. For an object that only has a fast `close()` method, `@PreDestroy` or `@Bean(destroyMethod = "close")` may be enough. `SmartLifecycle` is especially useful when **coordinated halting**, **phases**, and **completion reporting for asynchronous work** are required.

## 2. Three lifecycle coordination interfaces

### 2.1. Lifecycle: basic synchronous start/stop

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

This is a simplified signature of `org.springframework.context.Lifecycle` for reference; it is not a file to create in the project.

- `start()` instructs the component to begin operating.
- `stop()` instructs the component to stop; per contract, when the method returns, the implementation should have finished the stopping work it is responsible for.
- `isRunning()` reflects the component's actual operational state.

A regular `Lifecycle` does not auto-start by default on context refresh. Spring can drive it via `context.start()/stop()` and the lifecycle processor. When closing the context, the processor handles running `Lifecycle` beans.

### 2.2. SmartLifecycle: phases, auto-start, and callbacks

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
    // getPhase() comes from Phased.
}
~~~

This is also a high-level signature. Spring Framework 6.x provides **default methods** for some methods in `SmartLifecycle`: `isAutoStartup()` defaults to `true`, `getPhase()` defaults to `SmartLifecycle.DEFAULT_PHASE`, and `stop(Runnable)` has a default implementation delegating to `stop()` and then calling the callback.

You can override them for explicit control:

~~~java
@Override
public boolean isAutoStartup() {
    return true;
}

@Override
public int getPhase() {
    return 100;
}
~~~

When context refresh finishes, Spring automatically calls `start()` for `SmartLifecycle` beans with `isAutoStartup() == true` in phase/dependency order. On shutdown, the processor uses `stop(Runnable)` to be notified that the component has ceased operating.

### 2.3. LifecycleProcessor: the coordinator

`org.springframework.context.LifecycleProcessor` supports `onRefresh()` and `onClose()` hooks alongside the `Lifecycle` contract. Spring typically uses `DefaultLifecycleProcessor` as the default implementation.

The processor knows all lifecycle beans in the context, sorts them by phase and dependencies, and invokes stop accordingly. For a group of beans in a phase, it waits for completion signals up to the phase deadline.

Crucial point: **the application does not invent the callback Spring passes in from outside**. The bean is passed a `Runnable callback` when the processor invokes `stop(Runnable)`, and the bean is responsible for invoking `callback.run()` exactly once **after stop work finishes**. That is how the processor knows it may proceed.

## 3. How exactly does SmartLifecycle.stop(Runnable) work?

Contract:

~~~java
@Override
public void stop(Runnable callback) {
    // 1. Stop accepting new work.
    // 2. Request existing work to finish.
    // 3. When the stopping process genuinely completes:
    callback.run();
}
~~~

This is **Java pseudocode**, not standalone runnable code. The callback is a signal to the container; it does not stop the worker for you.

### Synchronous stop

If stopping is fast:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stopSynchronously();
    } finally {
        callback.run();
    }
}
~~~

This is an illustrative snippet with an application-defined `stopSynchronously()` method; this method must actually bring the component to a stopped state. Do not call the callback after merely issuing a "please stop" command while resources are still working if the contract requires waiting for completion.

### Asynchronous stop

If the component needs time to drain queues/wait for work:

~~~java
@Override
public void stop(Runnable callback) {
    rejectNewWork();
    stopExecutor.execute(() -> {
        try {
            waitForActiveWorkToFinish();
            releaseActivity();
        } finally {
            markStopped();
            callback.run();
        }
    });
}
~~~

This is an **architectural snippet**; `rejectNewWork()`, `waitForActiveWorkToFinish()`, `releaseActivity()`, `markStopped()`, and `stopExecutor` are illustrative only. In a real system, you must also handle cases where the executor **rejects the task**, stopping throws an error, the callback could be invoked twice, and deadlines apply.

**Significance of the callback:**

1. It is not an end-user callback; it is a signal from the bean back to `LifecycleProcessor`.
2. It must be invoked **after the component has actually stopped**, not immediately after submitting a cleanup task.
3. Invoking the callback too early makes Spring think the phase is done and begin destroying dependencies still used by the worker.
4. Forgetting the callback forces the processor to wait until the phase timeout.
5. After timeout, the processor may proceed with shutdown steps; **it does not automatically force your threads to terminate**.
6. Ideally invoked **exactly once**, even if the stop path runs again or encounters errors.
7. `SmartLifecycle.stop()` without a callback can still be called directly by application code, whereas the processor during normal shutdown uses **the overload with the callback**. If overriding both, do not put critical logic in only one overload and forget to delegate.

### Default implementation does not create async behavior automatically

In modern Spring, `SmartLifecycle.stop(Runnable)` has a default implementation that calls `stop()`, then calls the callback on the current thread. This behavior is only appropriate if `stop()` genuinely **stops synchronously**. A `stop()` that merely sets a "stopping" flag and returns is not sufficient to report completion. If shutdown takes time and must run asynchronously, override `stop(Runnable)` properly.

## 4. Phase: stop order is not simply bean registration order

Each `SmartLifecycle` component has an integer phase from `getPhase()`. General rules:

- **Startup:** lower phases start first; higher phases start later.
- **Shutdown:** higher phases stop first; lower phases stop later.
- Components in the same phase can begin stopping during the same stage; the processor waits for completion before moving to the next phase.
- A plain `Lifecycle` bean not implementing `SmartLifecycle` belongs to default phase **0**.
- Default `SmartLifecycle` has a very high `DEFAULT_PHASE` (`Integer.MAX_VALUE`), so it typically auto-starts late and stops early unless configured otherwise.
- `depends-on`/dependency relationships can **take precedence over phase ordering**: a dependent must stop before the bean it depends on.

Example:

| Bean | Phase | Order |
| --- | ---: | --- |
| `ClientListener` | 200 | Starts last; stops first |
| `MessageProcessor` | 100 | Starts middle; stops middle |
| `SharedTransport` | 0 | Starts first; stops last |

For a pipeline receiving messages → processing → sending over transport, high-to-low stop order allows the listener to stop accepting work first, the processor to finish running work, and only then the transport to close. Even so, **phases do not replace draining design and dependencies**. If the listener stops while jobs are still running in the processor, the processor still needs to wait for jobs to finish before invoking its callback.

**Real dependencies must be represented:** If A uses B, A must finish before B is closed, regardless of intended phases. Constructor injection and the bean dependency graph help Spring capture this relationship.

## 5. What is the timeout for each shutdown phase?

`DefaultLifecycleProcessor` waits for callbacks from `SmartLifecycle` beans in each phase. If all callbacks arrive before the deadline, the phase finishes and shutdown moves to lower phases. If a bean fails to call the callback or takes too long to stop, the processor waits only **up to that phase's timeout** and then continues shutdown processing.

~~~text
Phase 200: stop listener ---------------- callback ✅
                                        |
                                        v
Phase 100: stop worker --------- callback ✅ (within limit)
                                        |
                                        v
Phase   0: stop transport -------------- callback ✅
                                        |
                                        v
                Run bean destruction
~~~

If the phase-100 worker exceeds the deadline:

~~~text
Phase 100 starts: t=0
  worker.stop(callback) → begins async shutdown
  ...
  t = timeoutPerShutdownPhase: callback not yet invoked
  → LifecycleProcessor records timeout / continues shutdown
  → async worker may still be running!
  → bean destruction may occur while worker is not finished
~~~

**Timeout is not a "kill switch."** It bounds how long the container **waits for completion signals** from a phase group; Spring does not automatically interrupt, cancel `Future`s, close sockets, force GC, or kill component threads after timeout. Bean implementations must support bounded-deadline stopping, cancellation, and idempotent cleanup if business behavior requires it.

### Timeouts are per phase, not per bean

Suppose phase 100 has three beans, where one needs 4 seconds, another 5 seconds, and the third 6 seconds; if all three stop concurrently, a 10-second timeout is the **shared wait budget for the phase**, not `4 + 5 + 6` seconds summed, nor 10 seconds stacked per bean.

However, total shutdown should not be assumed equal to the exact sum of phase timeouts: synchronous operations inside `stop`, bean destruction callbacks, event listeners, and other frameworks can take extra time. If a `stop(Runnable)` **blocks directly** before returning, it can even delay the coordination process itself. To benefit from callback/time-bound asynchronous stopping, the method should return after triggering the stop, with completion reported later from an appropriate execution thread.

### Note differences across versions

In **Spring Framework 6.2**, `DefaultLifecycleProcessor`'s Javadoc states a default timeout of **10,000 ms (10 seconds) per phase**. Some reference pages from older branches/versions mention **30 seconds**. Because defaults and APIs can change across versions, check the running `spring-context` version; it is best to **configure timeouts explicitly** rather than relying on implicit defaults.

Starting in Spring 6.2, per-phase timeouts can be set via `setTimeoutForShutdownPhase(...)` or `setTimeoutsForShutdownPhases(...)`. Applications using Spring Framework 6.1 do not have the exact same full per-phase API as 6.2.

## 6. How to configure DefaultLifecycleProcessor

### 6.1. Same limit for every phase

~~~java
@Bean(name = "lifecycleProcessor")
static DefaultLifecycleProcessor lifecycleProcessor() {
    DefaultLifecycleProcessor processor = new DefaultLifecycleProcessor();
    processor.setTimeoutPerShutdownPhase(20_000L); // milliseconds
    return processor;
}
~~~

This snippet belongs to a `@Configuration` class; import `org.springframework.context.annotation.Bean` and `org.springframework.context.support.DefaultLifecycleProcessor`.

The bean name **`lifecycleProcessor`** is the name the Spring context looks up when initializing its lifecycle processor. In Java configuration, a `static` method is a clean way to create an infrastructure bean early; Spring needs this component at the completion step of `refresh()`.

Calling `setTimeoutPerShutdownPhase(20_000L)` applies a common wait limit of **20 seconds per phase**, not a total deadline for the entire JVM shutdown.

### 6.2. Setting a custom timeout for a specific phase (Spring 6.2+)

~~~java
@Bean(name = "lifecycleProcessor")
static DefaultLifecycleProcessor lifecycleProcessor() {
    DefaultLifecycleProcessor processor = new DefaultLifecycleProcessor();
    processor.setTimeoutPerShutdownPhase(10_000L);
    processor.setTimeoutForShutdownPhase(100, 25_000L);
    processor.setTimeoutForShutdownPhase(200, 5_000L);
    return processor;
}
~~~

Meaning:

- Default 10 seconds for every phase not overridden.
- Phase 100 has 25 seconds to complete callbacks.
- Phase 200 has 5 seconds.
- When phase 100 exceeds its limit, the processor moves to the next phase even though the component may not have stopped yet.

You can pass a `Map<Integer, Long>` to `setTimeoutsForShutdownPhases(...)` when multiple phases need tuning. **Do not confuse startup timeouts with shutdown timeouts**: `setConcurrentStartupForPhase(...)` (in some recent 6.2 releases) configures startup behavior, not the method for stopping.

### 6.3. Spring Boot property

With Spring Boot's lifecycle processor auto-configuration, common configuration is:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Or YAML:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

This is the **timeout per shutdown phase**. If you define your own `lifecycleProcessor` bean, check the Spring Boot configuration of your exact version because a custom bean may affect how Boot applies properties automatically; avoid assuming properties always override any manually created processor.

This setting is especially important for Spring Boot web server **graceful shutdown**. In modern Spring Boot versions, embedded web server graceful shutdown is triggered during lifecycle shutdown; the application continues processing in-flight requests during a grace period and stops accepting new requests per each server's behavior. This is related to, yet **does not replace**, stop durations for workers, queue consumers, and custom `SmartLifecycle` beans.

## 7. Runnable Java 17 example: asynchronous stop and completion callback

The example below intentionally simplifies background work into a short simulated stop using `Thread.sleep(80)` so you clearly see **the stop command sent first and the completion callback reported later**. This is not a production implementation for real queue draining.

### 7.1. Structure

~~~text
graceful-stop-demo/
├── pom.xml
└── src/main/java/demo/
    └── SmartStopDemo.java
~~~

### 7.2. pom.xml

Uses JDK 17 and Spring Framework 6.2.19:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>graceful-stop-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. src/main/java/demo/SmartStopDemo.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.DefaultLifecycleProcessor;

public class SmartStopDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            System.out.println("context active");
        }

        System.out.println("context closed");
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean(name = "lifecycleProcessor")
        static DefaultLifecycleProcessor lifecycleProcessor() {
            DefaultLifecycleProcessor processor = new DefaultLifecycleProcessor();
            processor.setTimeoutPerShutdownPhase(2_000L);
            return processor;
        }

        @Bean(destroyMethod = "release")
        public AsyncWorker asyncWorker() {
            return new AsyncWorker();
        }
    }

    public static class AsyncWorker implements SmartLifecycle {
        private final AtomicBoolean running = new AtomicBoolean();

        @Override
        public void start() {
            if (running.compareAndSet(false, true)) {
                System.out.println("worker started");
            }
        }

        @Override
        public void stop(Runnable callback) {
            if (!running.get()) {
                callback.run();
                return;
            }

            System.out.println("stop requested");

            Thread stoppingThread = new Thread(() -> {
                try {
                    Thread.sleep(80L); // Simulate work finishing.
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    running.set(false);
                    System.out.println("worker stopped");
                    callback.run();
                }
            }, "worker-stop");

            stoppingThread.start();
        }

        @Override
        public void stop() {
            running.set(false);
        }

        @Override
        public boolean isRunning() {
            return running.get();
        }

        @Override
        public int getPhase() {
            return 100;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        public void release() {
            System.out.println("resource released");
        }
    }
}
~~~

### 7.4. Run command and stdout

In the `graceful-stop-demo` directory:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.SmartStopDemo
~~~

Expected output of the program (ignoring environment-specific Maven/Spring logs if logging is enabled):

~~~text
worker started
context active
stop requested
worker stopped
resource released
context closed
~~~

Explanation:

1. During `refresh()`, `DefaultLifecycleProcessor` receives the `AsyncWorker` bean and calls `start()` due to `isAutoStartup() == true`. Prints `worker started`.
2. After the context finishes creating, `main` prints `context active`.
3. Upon exiting `try-with-resources`, `context.close()` is called. Spring sees `AsyncWorker` running at phase 100 and invokes `stop(Runnable)`, printing `stop requested`.
4. `stop(Runnable)` spawns a thread to perform the stop work and returns early. `DefaultLifecycleProcessor` waits for the callback within the **2-second timeout of phase 100**.
5. The thread simulates 80 ms, sets `running=false`, prints `worker stopped`, and then invokes `callback.run()`. The processor receives the signal and can conclude the phase.
6. Moving to destruction, Spring invokes `release()` because of `@Bean(destroyMethod = "release")`. Prints `resource released`.
7. Finishing context close, `main` prints `context closed`.

**Why does output have a stable order in this example?** `main` prints `context closed` only after `close()` returns, and the processor waits for the callback; the simulated stop time is shorter than the configured timeout under normal execution conditions. If the CPU stalls or scheduling slows past the 2-second deadline, a timeout scenario could change observations; in that case check timeout logs and do not assume the thread has stopped.

### 7.5. Intentionally simplified details

- `Thread.sleep(80)` does not represent real draining work; in production, stop new input, wait for current work, enforce timeouts, and handle cancellation.
- `stop()` does not participate in the async path used by the processor. In production applications, share a common stopping mechanism so `stop()` and `stop(Runnable)` do not create two conflicting semantics.
- The example does not fully protect against concurrent `stop(Runnable)` calls; production needs STOPPING/STOPPED states, storing a callback list or shared completion signal so multiple stop threads are not spawned and callbacks are not called redundantly.
- `release()` in the sample only prints a line. Real resources must ensure they are not destroyed while the worker is still using them and clean up safely if a timeout occurs.
- The new thread in the example is not pooled. If using an executor for shutdown, handle `RejectedExecutionException`: never drop the completion callback without a mechanism that eventually transitions the component to a stopped state.

## 8. Timeout scenario: why "wait expired" does not mean "stopped"?

Suppose the bean in the example waits 5 seconds while `timeoutPerShutdownPhase = 2_000L`. After two seconds, the processor may log a timeout warning and move on to subsequent phases/destruction callbacks while the stopping thread is still running.

Potential consequences:

- `release()` may close resources that the worker has not yet stopped using.
- Beans in lower phases stop earlier than desired because the higher phase timed out.
- `Context.close()` may return while non-container threads remain alive.
- If the stopping thread is **non-daemon** and never finishes, the JVM may still fail to exit even after Spring's wait expires.
- A callback sent **after the phase has timed out** cannot "turn back time" to restore skipped shutdown ordering.

Therefore **the lifecycle processor's timeout is a wait guardrail**, not a hard-kill deadline for the entire process. A solid component still needs its own strategy:

1. Upon receiving stop, immediately **reject new work**.
2. Give in-flight work a clear grace period with a real deadline.
3. If the grace period expires, actively cancel/interrupt/close I/O as safely supported by the library.
4. Determine when resources genuinely have no remaining users.
5. Update `isRunning()` state consistently.
6. Invoke the callback only when the component reaches the stopped state per contract.
7. Log/emit metrics on timeout; never fake completion merely to "make Spring stop waiting."

For resources that cannot guarantee stopping within the deadline, applications must design idempotency, retries, durable queues, or restart recovery. Do not handle potential data loss merely by stretching timeouts indefinitely.

## 9. Avoiding race conditions when implementing stop(Runnable)

A production component typically has states:

~~~text
NEW → RUNNING → STOPPING → STOPPED

                STOPPING ──(worker completes)──> STOPPED
                     |
                     └──(grace period expires)──> force/cancel path
                                                   └──> STOPPED or FAILED
~~~

Scenarios that must be handled:

| Scenario | Rule to satisfy |
| --- | --- |
| `stop(callback)` called when not yet running | Callback is invoked so the processor does not wait pointlessly |
| Two `stop(callback)` calls arrive closely together | Do not spawn two competing stop paths; callbacks receive valid completion signals |
| Worker stops right as stop begins | State reads/writes must have visibility (`AtomicBoolean`/lock) |
| Executor rejects shutdown task | Provide fallback path or clear error reporting, avoiding dropped callbacks |
| Worker throws exception | Clean up appropriately and never leave state stuck in STOPPING forever |
| Callback itself throws exception | Log/contain responsibly; do not let exception break resource cleanup |
| Stop finishes after processor timeout | Do not assume dependent beans are still alive |
| Restart after stop | Support only if component's lifecycle contract/resources permit; reset state safely |
| Context destroyed before stop received a signal | Cleanup tolerates abnormal paths too |

An anti-pattern:

~~~java
@Override
public void stop(Runnable callback) {
    executor.shutdown();
    callback.run(); // Wrong if executor still has running tasks.
}
~~~

`ExecutorService.shutdown()` only stops accepting new tasks and initiates orderly shutdown; it **does not wait** for all tasks to finish before returning. If the callback is invoked immediately, Spring may close dependencies while tasks are still using them.

The required pattern waits on `awaitTermination(...)` or a completion signal, has a timeout/interrupt policy, and invokes the callback only after the worker has genuinely stopped. Do not block synchronously indefinitely on the thread calling stop.

## 10. Example integrating a real ExecutorService (explanatory snippet)

In a component managing an executor, the stopping concept might look like:

~~~java
public void stop(Runnable callback) {
    accepting.set(false);
    workerExecutor.shutdown();

    shutdownCoordinator.execute(() -> {
        try {
            boolean completed =
                    workerExecutor.awaitTermination(15, TimeUnit.SECONDS);
            if (!completed) {
                workerExecutor.shutdownNow();
                // Policy-dependent: continue bounded wait if you must verify
                // workers genuinely terminated before reporting completion.
            }
        } catch (InterruptedException ex) {
            workerExecutor.shutdownNow();
            Thread.currentThread().interrupt();
        } finally {
            // Invoke callback only after confirming required stop state.
            // This logic depends on the application's actual contract.
        }
    });
}
~~~

This is an **integration snippet**, requiring `AtomicBoolean accepting`, `ExecutorService workerExecutor`, `Executor shutdownCoordinator`, and appropriate `TimeUnit`, `InterruptedException` imports. It intentionally **does not invoke callback** in the code because `shutdownNow()` alone does not guarantee running tasks have terminated; you must add proper completion state/await policy. The complete runnable example in section 7 demonstrates a finite stop path, whereas this section highlights the design difficulty with a real executor.

If you cannot wait for resources to stop completely, do not report fake completion just to "make logs look clean." Decide clearly which timeout belongs to the coordinator, which belongs to the worker, and how in-flight data will be recovered.

## 11. Distinguishing Spring Boot graceful HTTP shutdown from SmartLifecycle callbacks

Spring Boot web apps usually need to stop accepting new HTTP requests, give running requests time to finish, and then release the server. With embedded servers and modern Boot versions, graceful shutdown is integrated into lifecycle phases.

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

In Spring Boot versions where graceful shutdown is the default, `server.shutdown=graceful` may be unnecessary yet expresses intent; check your specific Boot version. The `spring.lifecycle.timeout-per-shutdown-phase` property controls the lifecycle processor's per-phase wait limit, used by Spring Boot for graceful shutdown.

**Two independent points to note:**

- Stopping the HTTP listener does not mean background message consumers or scheduled jobs have also stopped. They need their own lifecycles if coordinated shutdown is required.
- Spring's graceful shutdown timeout is not the total timeout of Kubernetes/OS/runtime. If the container orchestrator gives the app too little time before sending SIGKILL, Spring may not get to enjoy the full grace period.

Example budget allocation:

~~~text
Runtime termination grace period
   ├─ preStop hook execution time (if any)
   ├─ HTTP listener stop phase
   ├─ consumers/workers completion phase
   ├─ bean destruction/flush
   └─ safety buffer time
~~~

This is a **budget diagram**, not a mandatory formula. Actual total time depends on phase ordering and callbacks; design should use a system-level deadline larger than the time needed for Spring cleanup.

Some IDE environments send "terminate" signals in ways that make shutdown abrupt or forced; test real deploy/runtime workflows rather than only observing the IDE's Stop button.

## 12. How does the stop callback differ from @PreDestroy?

~~~java
@Component
public class ListenerLifecycle implements SmartLifecycle {

    @Override
    public void stop(Runnable callback) {
        // Stop accepting work + wait for old work to finish;
        // report completion via callback.run().
    }

    @PreDestroy
    public void releaseResources() {
        // Close remaining resources.
    }
}
~~~

This is a **structural snippet**, not yet implementing all `SmartLifecycle` methods and requiring `jakarta.annotation.PreDestroy` and other imports. It is not standalone runnable code.

During normal context shutdown:

1. Spring invokes `stop(Runnable)` on running lifecycle beans by phase.
2. The processor waits for completion callbacks up to each phase's timeout.
3. Spring runs destruction callbacks such as `@PreDestroy`, `DisposableBean.destroy()`, or custom destroy methods.

However, if `refresh()` fails while the context is creating beans or an abnormal destruction path occurs, `@PreDestroy` may run without `stop(Runnable)` ever having been called. Hence destructors must tolerate "running", "stopping", "never started", and "stopped" states.

Do not call `callback.run()` inside `@PreDestroy` if the callback belonged to an expired or nonexistent stop invocation; completion callbacks must be tied to the exact stop invocation and actual completion state.

## 13. Testing and diagnostics

### Minimal tests

1. **Auto-start:** once context refresh finishes, `isAutoStartup() == true` causes `start()` to be called.
2. **Normal stop:** `context.close()` calls `stop(Runnable)`, with the callback running only after stop work finishes.
3. **Waiting for callback:** in the same phase, component A stops asynchronously; the processor does not transition to a lower phase before A's callback fires.
4. **Missing callback:** the processor waits only until the phase timeout, logs a warning, and proceeds. Ensure tests do not hang indefinitely.
5. **Premature callback:** simulate a component still using a dependency; test detects resources closing before the worker finishes.
6. **Multi-component same phase:** verify the timeout is a shared group deadline, not summed per bean.
7. **Order:** higher phases stop before lower phases; dependencies override if applicable.
8. **Stop failures:** executor rejects shutdown task, worker throws exception, timeout/cancellation.
9. **Idempotent stop:** repeated stop calls or stop when not running never drop callbacks or close resources twice.
10. **Startup failure:** destruction remains safe even if stop never occurred.
11. **Servlet graceful shutdown:** test in-flight HTTP requests and rejection of new requests on the embedded server in use.
12. **Runtime signals:** test SIGTERM and termination grace periods in real deployment environments.

### Practical observability

Logs should record: component, phase, timestamp stop requested, in-flight task count, completion callback timestamp, shutdown duration, timeouts, and cleanup errors. Metrics may include histogram `shutdown_duration_seconds`, gauge `inflight_tasks`, and counter `shutdown_timeouts_total`. Metric names are design suggestions only; Spring Core does not automatically generate these metrics merely because a bean implements `SmartLifecycle`.

**Distinguishing log statements:**

- "stop requested": stop command was dispatched.
- "running=false": component state reports stopped per contract.
- "callback invoked": container received the completion signal.
- "phase timed out": container stopped waiting; component may still be running.
- "context closed": context closing ran through its steps, yet does not prove all unmanaged tasks have fully terminated.

### Common issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Shutdown waits until timeout even though worker stopped | Forgot `callback.run()` | Invoke callback exactly once after confirming stop, including no-op paths |
| Container closes dependencies while tasks still run | Callback invoked too early, e.g., right after `executor.shutdown()` | Wait for in-flight tasks to finish before callback |
| Bean `stop()` has code yet does not run on close | `SmartLifecycle` processor uses `stop(Runnable)` overload | Override/delegate between both overloads properly |
| High phase waits long, lower phase has not received stop | Callback not yet received or large deadline | Check asynchronous stop and per-phase timeouts |
| Bean times out yet process still does not exit | Out-of-scope threads remain alive; timeout does not interrupt | Actively cancel/close resources and manage executors |
| After timeout, `@PreDestroy` closes resources while worker uses them | Stop callback did not arrive in time; uncoordinated cleanup | Design deadlines, cancellation, safe cleanup, and recovery |
| Component does not auto-start | `isAutoStartup() == false` or bean not registered in context | Configure auto-start/explicit start accurately |
| Stop order differs from expected phases | `depends-on` relationships take precedence | Inspect dependency graph, not just phase numbers |
| Boot property has no expected effect | Using custom lifecycle processor or different version | Check `lifecycleProcessor` bean and actual running Boot config |
| Logs show 30s while Javadoc says 10s | Reading docs for a different version | Pin framework version and configure timeouts explicitly |
| Shutdown tests pass yet production gets SIGKILL | Runtime grace period too short | Grant sufficient time on deployment platform and include recovery |
| Bean destroyed without having stopped | Startup error/hot refresh/abnormal destroy path | Destructor must be safe when no stop signal arrived |

## 14. Production design checklist

- Define "stopped" unambiguously: no new work accepted, no remaining in-flight tasks using resources about to be destroyed.
- Model RUNNING/STOPPING/STOPPED with thread-safe state.
- Ensure `stop(Runnable)` returns fast enough after triggering async stop; emit callback only when genuinely complete.
- Never omit the callback on not-running, error, cancellation, or rejected-scheduling paths.
- Choose `getPhase()` reflecting sensible dependency order; check `depends-on`.
- Configure `DefaultLifecycleProcessor` per version; Spring 6.2 defaults to 10 seconds/phase and offers per-phase APIs.
- Never treat processor timeout as thread termination; components manage deadlines/interrupts/force-cancellation themselves.
- Coordinate `@PreDestroy` to release resources after stop and handle paths where stop never happened.
- With Spring Boot web, verify graceful shutdown and `spring.lifecycle.timeout-per-shutdown-phase`.
- Ensure orchestrator-allowed time exceeds actual application shutdown needs.
- Log completed/timeout/aborted per component and phase; test on real runtimes.

## 15. Self-check

**1. What is the purpose of the `SmartLifecycle.stop(Runnable)` callback?**  
To let `LifecycleProcessor` know the component has genuinely stopped and it can stop waiting for the same-phase group. It does not stop the component itself.

**2. If a worker invokes the callback immediately after `ExecutorService.shutdown()`, is that correct?**  
Not necessarily. `shutdown()` only stops accepting new tasks and does not wait for running tasks. If tasks are still using dependencies, the callback was invoked too early.

**3. Does a 10-second/phase timeout mean each bean individually gets up to 10 seconds?**  
No. The processor applies a shared wait limit per phase. Total shutdown duration also depends on other operations.

**4. When a phase timeout occurs, does Spring forcibly interrupt every worker?**  
No. Timeout is a limit on waiting for completion, not a mechanism for forcibly cancelling tasks.

**5. Which phase stops first, phase 200 or phase 100?**  
Normally phase 200 stops before phase 100. Dependency relationships can take precedence over phase.

**6. Why might `SmartLifecycle.stop()` not be called on shutdown even when overridden?**  
Because the lifecycle processor normally invokes `stop(Runnable callback)`. Implementations must override the right overload or delegate consistently.

**7. How do stopping a worker and `@PreDestroy` differ?**  
Stop coordinates the worker to cease accepting work and await tasks, whereas destruction callbacks close final resources. You cannot always rely on stop occurring before destruction when startup fails.

**8. Does `spring.lifecycle.timeout-per-shutdown-phase=20s` guarantee the JVM always stops under 20 seconds?**  
No. It limits the wait time **per phase**, excluding other shutdown activities or unmanaged threads. The runtime has its own deadline.

**9. Why choose a custom timeout for a critical phase?**  
Because a listener may only need a couple of seconds to stop accepting work, whereas a processor may need extra time to drain tasks before transport/DB resources close. Spring Framework 6.2 supports `setTimeoutForShutdownPhase(...)`.

**10. If a component finishes stopping after its phase timed out, does the callback restore shutdown order?**  
No. Spring may already have moved to another phase or destroyed dependencies; a late callback does not reverse completed steps.

## Official documentation

- Spring Framework Reference: [Customizing the Nature of a Bean — Startup and Shutdown Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html).
- Spring Framework Javadoc: [SmartLifecycle (Spring 6.2.7)](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/context/SmartLifecycle.html).
- Spring Framework Javadoc: [DefaultLifecycleProcessor (Spring 6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html).
- Spring Boot Reference: [Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html).
- Java SE API: [ExecutorService.shutdown() and awaitTermination()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).
