# Sequence of Close Notification, Lifecycle Stop, and Singleton Destruction in Spring Boot

## 1. Why Must We Distinguish Three Shutdown Steps?

When a Spring Boot application is stopped normally, not all "cleanup" callbacks happen at the same time. Spring Framework distinguishes three mechanisms with different purposes:

1. **Notifying that the context is closing** via `ContextClosedEvent`: registered listeners learn that context closure **has begun**.
2. **Stopping components with an operational lifecycle** via `LifecycleProcessor.onClose()`: running `Lifecycle` and `SmartLifecycle` beans are asked to stop, potentially coordinating order by phase and asynchronous callbacks.
3. **Destroying singletons owned by the container** via `destroyBeans()`: Spring invokes `@PreDestroy`, `DisposableBean.destroy()`, and configured destroy methods for eligible beans.

For a **normal close of a Spring Framework 6.1-style `ConfigurableApplicationContext`**, the high-level sequence is:

```text
Request to close context
    |
    v
ContextClosedEvent
    |
    v
LifecycleProcessor.onClose()
    |-- stop lifecycle beans in descending phase order
    |-- coordinate SmartLifecycle.stop(Runnable callback)
    v
destroyBeans()
    |-- destroy cached singletons / invoke destruction callbacks
    v
closeBeanFactory()
    |
    v
context subclass onClose() and context cleanup
    |
    v
close() completes
```

This is the **order of phases**, not an assertion that all callbacks in every phase always run on the same thread in every configuration, or that every bean in an application implements all three mechanisms. For example, a regular bean with `@PreDestroy` that does not implement `Lifecycle` participates only in the destruction phase; a `SmartLifecycle` bean may receive `stop(Runnable)` first and `@PreDestroy` afterward.

**Key takeaway:** `ContextClosedEvent` is the **closing started** signal, `stop` is the **halt operations** step, and `destroy` is the **release bean/resource** step. Do not treat the three mechanisms as synonymous callbacks.

Lesson scope: **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**, covering normal shutdown and limits to keep in mind when running under an orchestrator/container.

## 2. Starting Point: What Triggers the Closing Process?

A context can be asked to close in several ways.

### 2.1. Explicit Close

```java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

context.close();
```

This is an **illustrative snippet** requiring a `MyApplication` class and corresponding Spring imports. `ConfigurableApplicationContext` extends `Closeable`; `close()` triggers the Spring-managed context closing sequence.

### 2.2. try-with-resources

```java
try (ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args)) {
    // Perform work.
}
// Exiting the block: Java calls context.close().
```

This is also an illustrative snippet. For a **CLI/batch job or non-web exercise**, this ensures closure on normal completion or when an exception exits the block.

However, for a **long-running web service**, do not put the context in a try-with-resources block that finishes immediately after `run()`, because it will shut down the server before the application has a chance to serve requests. Web applications normally keep the context alive until a stop signal arrives.

### 2.3. JVM Shutdown Hook

Spring Boot normally registers a shutdown hook so the context is closed when the JVM performs a normal shutdown (for example, when the process receives a stop signal that allows hooks to run). Therefore, a **SIGTERM** request in a container can lead into the same context-closing path as `close()`.

Distinguish carefully:

- **`context.close()`**: an operation on the context object while application code is still executing.
- **Shutdown hook**: the JVM's opportunity to run cleanup code during JVM shutdown.
- **`System.exit(...)`**: explicitly requests JVM termination, entering the shutdown process if the runtime permits.
- **`SIGKILL`, severe crash, power loss**: does not allow relying on hooks/`@PreDestroy` as an absolute guarantee.

`ContextClosedEvent` is **not** an event reporting an OS SIGTERM result; it is a Spring `ApplicationContext` event published when the context closes via Spring's mechanism.

### 2.4. Closing a Context Does Not Mean Starting the Shutdown Hook

If you explicitly call `context.close()` in a running process, Spring executes context closure. The JVM **does not necessarily** exit right away: non-daemon threads may still exist elsewhere. Conversely, the JVM can terminate abruptly before the context finishes all cleanup. Do not conflate process lifecycle with context lifecycle.

## 3. Why Is ContextClosedEvent Published Before Stop/Destroy?

`ContextClosedEvent` belongs to `org.springframework.context.event`. When `AbstractApplicationContext.doClose()` enters the normal closing path, it publishes this event **before** calling the lifecycle processor and destroying cached singletons.

A simple listener:

```java
@EventListener
public void onClosing(ContextClosedEvent event) {
    System.out.println("Context is closing");
}
```

This is an **illustrative method snippet**, not a standalone program. It must live inside a Spring-managed bean, with imports for `org.springframework.context.event.EventListener` and `org.springframework.context.event.ContextClosedEvent`.

### 3.1. What Is a Listener Allowed to Do When Receiving This Event?

At the moment the event is published, lifecycle stop and singleton destruction **have not completed**. A listener can:

- Mark an application state as "closing" for fast, controlled coordination.
- Record shutdown metrics/logs, timestamps, and non-sensitive correlation IDs.
- Signal to stop accepting work **if that is its designated responsibility**, while avoiding duplication with `SmartLifecycle.stop`.
- Notify existing components that the close process has begun.

Do not:

- Assume workers/consumers have already stopped merely because `ContextClosedEvent` was sent.
- Spawn new threads, register many long-running tasks, or instantiate complex beans while the context is closing.
- Block indefinitely inside the listener, because with the default synchronous multicaster this can **delay both lifecycle stop and bean destruction**.
- Call `context.close()` recursively inside the listener.
- Use this listener to assert that data has been committed or completely flushed.

### 3.2. Can @Order Change the Order of the Three Phases?

**No.** `@Order` on `@EventListener` methods can help order multiple **listeners for the same `ContextClosedEvent`** by dispatch ordering. It cannot alter Spring's built-in sequence:

```text
ContextClosedEvent -> LifecycleProcessor.onClose() -> destroyBeans()
```

You cannot place `@Order(-1000)` on a `@PreDestroy` method and force it to run before `ContextClosedEvent`. `@PreDestroy` is not an `ApplicationEvent` listener.

### 3.3. Synchronous vs. Asynchronous

The default `SimpleApplicationEventMulticaster` normally invokes listeners synchronously. In that case, the `ContextClosedEvent` listener body has a chance to run before `doClose()` moves on to lifecycle stop.

If an application uses a custom event multicaster backed by an executor, or a listener has async behavior, **do not rely on when that async callback finishes** to conclude it completes before Spring destroys beans. A job scheduled inside the listener may still be running when dependent beans are closed. For mandatory shutdown work, `SmartLifecycle.stop(Runnable)` and timeout/ack have a clearer contract.

## 4. LifecycleProcessor.onClose(): Stopping Operations Before Destroying Beans

Spring defines `org.springframework.context.Lifecycle`:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

This is a condensed signature for explanation, not a class to redeclare. `Lifecycle` describes **an object capable of transitioning between running and stopped**; that is distinct from the object existing on the heap.

`SmartLifecycle` adds:

- `isAutoStartup()`: allows auto-starting on context refresh when conditions match; the interface default in Spring 6.1 is `true`.
- `getPhase()`: assigns a phase so Spring can order start/stop.
- `stop(Runnable callback)`: supports signaling shutdown completion, especially for asynchronous stopping.

In a normal `doClose()`, Spring invokes `LifecycleProcessor.onClose()` **after `ContextClosedEvent`**. The standard implementation `DefaultLifecycleProcessor` gathers eligible lifecycle beans and coordinates stopping them.

**Not every singleton has `stop()` called.** Only beans following the `Lifecycle`/`SmartLifecycle` contract and considered running by the processor participate. A plain bean with `@PreDestroy` and no `stop` receives only its destruction callback in the later step.

### 4.1. Phase: Ascending Start, Descending Stop

For registered `SmartLifecycle` beans, the standard rule is:

| Phase | During start | During shutdown |
| --- | --- | --- |
| `-100` | Starts very early | Stops relatively late |
| `0` | After -100, before 100 | After 100, before -100 |
| `100` | After 0, before 200 | Before 0, after 200 |
| `200` | After 100 | Stops before phase 100 |
| `Integer.MAX_VALUE` | Among the last phases to start | Among the first phases to stop |

In Spring Framework 6.1, `SmartLifecycle.DEFAULT_PHASE == Integer.MAX_VALUE`, while a plain `Lifecycle` without `Phased` is treated as phase `0` by the default processor.

Example with two components:

```text
Startup:
    connector phase=100 -> consumer phase=200

Shutdown:
    consumer phase=200 -> connector phase=100
```

This makes sense when the consumer needs the connector alive while stopping/draining work. If the consumer stopped after the connector, the consumer could send requests to an already closed resource.

**Do not use phase to infer bean creation order**: constructors, `@PostConstruct`, and dependency injection follow bean factory rules. `getPhase()` coordinates **start/stop**.

### 4.2. @DependsOn Can Take Precedence Over Phase

If bean B depends on A, Spring can ensure B **stops before** A even if their declared phases are reversed. `@DependsOn` expresses an explicit relationship at the bean definition level, whereas phase coordinates lifecycle when no explicit dependency exists.

Do not try to use phases to break a dependency constraint. If a consumer genuinely requires a producer, express that relationship through injection or `@DependsOn`.

### 4.3. Beans in the Same Phase Have No Guaranteed Business Order

If two listeners/workers both have phase `100`, do not rely on whatever log order happened to appear in one run to assume which stops first. You may need distinct phases, declared dependencies, or an explicit orchestrator owner.

### 4.4. What Does isRunning() Mean?

`isRunning()` is the state reported by the implementation. When the processor stops running beans, this method can be used to decide whether to call stop. If a component sets `running=false` before actually finishing draining, or returns an inaccurate flag, shutdown coordination can go wrong.

Do not treat the container calling `stop()` as proof that **all async tasks of the component have finished**. Each component must design its own stop boundary.


## 5. SmartLifecycle.stop(Runnable): Why Is the Callback Important?

The `SmartLifecycle.stop(Runnable callback)` contract exists to signal when a component **has genuinely stopped**, especially if shutdown happens asynchronously.

Synchronous stop pattern:

```java
@Override
public void stop(Runnable callback) {
    try {
        stop(); // Truly stop, do not just flip an arbitrary flag.
    } finally {
        callback.run();
    }
}
```

This is an illustrative method inside a class implementing `SmartLifecycle`; the full code appears in section 7.

### 5.1. If Stopping Asynchronously

A component can:

1. Stop accepting new tasks.
2. Wait for in-flight tasks to finish or reach a deadline.
3. Send corresponding acknowledgements / cancel subscriptions.
4. Close resources it owns.
5. **Then** invoke `callback.run()`.

Conceptual pattern:

```java
@Override
public void stop(Runnable callback) {
    stopExecutor.execute(() -> {
        try {
            stopAcceptingTasks();
            drainWithinDeadline();
            closeOwnedResources();
        } finally {
            running = false;
            callback.run();
        }
    });
}
```

This is **Java pseudo-code** and does not compile standalone: `stopExecutor` and the helper methods must be actually defined. In practice you must also handle `stopExecutor.execute(...)` rejecting the task, ensure the callback is invoked **only once**, and avoid leaving resources half-stopped.

**Calling the callback too early** lets the processor move on to stopping the next dependency while the worker is still running. **Forgetting to call the callback** forces the processor to wait out the entire phase timeout. That is why `stop(Runnable)` cannot simply be replaced by a `System.out.println("stopping")` line.

### 5.2. Timeout per Shutdown Phase

`DefaultLifecycleProcessor` in **Spring Framework 6.1** has a default timeout of **30 seconds per phase** when waiting for `SmartLifecycle.stop(Runnable)` completions. Spring Boot 3.3 lets you configure:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

This caps **the processor's wait time for a single phase**, not a guarantee that the entire process ends in 20 seconds. Multiple phases, web server graceful shutdown, JVM hooks, and the container's termination grace period can lengthen or shorten actual duration.

If a phase times out, the processor may proceed to the next step even though the component has not truly finished. Applications therefore still need I/O timeouts, cooperative cancellation, and safeguards against bad side effects after resources close.

### 5.3. stop(Runnable) Does Not Replace @PreDestroy

`stop` is for halting **operations** coordinated by phase. `@PreDestroy` is for cleanup **when the bean is destroyed**. A bean can receive both if it implements `SmartLifecycle` and also defines a destruction callback.

Example of a message consumer:

```text
ContextClosedEvent
    |
    +--> SmartLifecycle.stop(callback)
    |       +--> stop polling / stop accepting messages
    |       +--> process in-flight within deadline
    |       +--> callback.run()
    |
    +--> @PreDestroy
            +--> final cleanup if resources remain
```

Avoid closing **the exact same resource** twice in an uncontrolled way. Make `close` idempotent or cleanly separate responsibilities across phases. If using a final shutdown callback defensively when startup was incomplete, do not assume `stop` always ran beforehand on every failure path.

## 6. destroyBeans(): Destroying Singletons per Container Contract

After normal lifecycle stop, `AbstractApplicationContext` calls `destroyBeans()`. The default implementation invokes destruction for **cached singleton beans** managed by the `BeanFactory`. This step is separate from `LifecycleProcessor.onClose()`.

For a bean eligible for container destruction, Spring supports:

- `@PreDestroy` (in Spring Boot 3.x, `jakarta.annotation.PreDestroy`).
- `org.springframework.beans.factory.DisposableBean.destroy()`.
- Custom destroy methods, such as `@Bean(destroyMethod = "close")`.
- Certain `@Bean` definitions may infer `close()` or `shutdown()` methods on destruction under standard configuration.

### 6.1. Order of Destruction Mechanisms on the **Same Bean**

If a bean declares **all three callbacks with three different names**, Spring Framework documents the order:

1. Method annotated with `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Configured custom destroy method.

Illustration:

```java
public class ResourceOwner implements DisposableBean {
    @PreDestroy
    public void beforeDestroy() {
        System.out.println("A. @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("B. DisposableBean.destroy");
    }

    public void closeResource() {
        System.out.println("C. custom destroy");
    }
}
```

This is an **illustrative class** requiring imports for `DisposableBean` and `PreDestroy` along with a bean definition registering the custom method `closeResource`, e.g., `@Bean(destroyMethod="closeResource")`. Complete runnable code is in section 7.

**Note:** This is the **intra-bean** order. Do not infer that independent beans will always be destroyed in class-name order, `@Order`, or declaration order in a Java file. To enforce destruction ordering between singletons, express valid dependencies; a dependent singleton is destroyed before its dependency singleton in a `depends-on` relationship.

### 6.2. Which Beans Are Not Automatically Destroyed Like Singletons?

| Object/scope | On normal context close | Who is responsible for cleanup? |
| --- | --- | --- |
| Spring-managed singleton with a destruction callback | Spring invokes callback via bean destruction mechanism | Spring coordinates; callback is responsible for releasing resource |
| Singleton holding no resources and having no destroy callback | No special cleanup call needed | No need to invent a pointless `close()` |
| `prototype` bean | Spring creates/initializes it, but **does not automatically run destruction callbacks per instance on context close** | Caller/owner of each instance |
| Object created with `new` outside container | No automatic Spring bean lifecycle | Code owning the object |
| Object created with `new` **inside `@Bean` and returned as a singleton bean** | Can have Spring destruction callbacks since the object is a managed bean | Check scope and destroy method, not just how the constructor was called |
| Resource stored in a singleton field without being registered as a bean | Container destroys the owner bean, not implicitly aware of child resources | Owner bean closes the resource in an appropriate callback |

Spring Framework has other scopes like request/session that can have destruction callbacks matching their scope lifecycle. Do not lump every non-singleton into the default prototype rule.

### 6.3. Why Isn't @PreDestroy Something to Call Manually to Stop a Worker?

`@PreDestroy` is merely metadata for the destruction phase, **not a public "stop component now" API**. If you need to pause a worker while the context stays alive, use the `Lifecycle.stop()`, `SmartLifecycle` contract, or a dedicated service operation. Nor does `context.stop()` destroy all beans, so it does not invoke every `@PreDestroy`.

If you need to release a resource right when a short-lived request or job ends, use `try-with-resources` or scope-bound ownership rather than waiting for JVM shutdown.

## 7. Runnable Example: Observing All 8 Milestones with Spring Boot 3.3.13

We will create a small **non-web** Spring Boot app so web servers and startup tasks from other starters do not clutter stdout. The program has:

- A `ContextClosedEvent` listener.
- Two `SmartLifecycle` beans with phases `200` and `100`.
- A singleton bean having `@PreDestroy`, `DisposableBean.destroy()`, and a custom `destroyMethod`.
- A `try-with-resources` block explicitly closing the context once startup succeeds.

**Prediction:** the close event fires first; `SmartLifecycle` phase 200 stops before phase 100; then the singleton's three destruction callbacks execute in exact order.

### 7.1. build.gradle

Create a Gradle Groovy project with Gradle Wrapper and **Java 17**. File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

File `settings.gradle`:

```groovy
rootProject.name = 'shutdown-stages-lab'
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

This is a non-web project: there is no embedded Tomcat/Netty, so lifecycle demonstration output is not interleaved with web server logs.

### 7.2. Complete Java File

Create at the exact path **`src/main/java/com/example/shutdown/ShutdownStagesApplication.java`**:

```java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ShutdownStagesApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(ShutdownStagesApplication.class, args)) {
            System.out.println("01 main: request context close");
        }
        System.out.println("08 main: close finished");
    }

    @EventListener
    public void contextClosing(ContextClosedEvent event) {
        System.out.println("02 ContextClosedEvent");
    }

    @Bean
    PhaseWorker lowPhaseWorker() {
        return new PhaseWorker("LOW", 100);
    }

    @Bean
    PhaseWorker highPhaseWorker() {
        return new PhaseWorker("HIGH", 200);
    }

    @Bean(destroyMethod = "closeResource")
    CleanupSentinel cleanupSentinel() {
        return new CleanupSentinel();
    }

    public static final class PhaseWorker implements SmartLifecycle {
        private final String label;
        private final int phase;
        private volatile boolean running;

        public PhaseWorker(String label, int phase) {
            this.label = label;
            this.phase = phase;
        }

        @Override
        public void start() {
            running = true;
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                if (phase == 200) {
                    System.out.println("03 stop HIGH phase=200");
                } else {
                    System.out.println("04 stop LOW phase=100");
                }
            }
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                callback.run();
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return phase;
        }
    }

    public static final class CleanupSentinel implements DisposableBean {

        @PreDestroy
        public void beforeDestroy() {
            System.out.println("05 singleton @PreDestroy");
        }

        @Override
        public void destroy() {
            System.out.println("06 singleton DisposableBean.destroy");
        }

        public void closeResource() {
            System.out.println("07 singleton custom closeResource");
        }
    }
}
```

### 7.3. Explaining the Code Decisions

- `@SpringBootApplication` initializes a non-web application and scans the required beans.
- `@EventListener` on the application class listens for `ContextClosedEvent` in that context; with the default synchronous multicaster, it prints **02** before stop.
- `lowPhaseWorker()` and `highPhaseWorker()` are two `SmartLifecycle` singletons. `isAutoStartup() == true`, so they start during refresh; `isRunning()` returns true before context closure.
- Both workers use `getPhase()` values 100 and 200. When `LifecycleProcessor.onClose()` runs, the higher phase **200 stops before 100**.
- `stop(Runnable)` calls the real `stop()` and always invokes the callback in `finally`. Because the stop method is synchronous with no background tasks, the callback is signaled right after stopping.
- `CleanupSentinel` is a singleton registered via `@Bean(destroyMethod="closeResource")`. It defines three callbacks with **different names**, suitable for verifying Spring's order: `@PreDestroy` → `DisposableBean.destroy` → custom method.
- `try-with-resources` closes the context at the end of the block. After `close()` finishes completely, `main` prints **08**.
- There is no external software, message broker, or network I/O; the numbered lines have no scheduling contention.

### 7.4. Running the Program

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Lines **printed by this Java code itself**, in exact order under the described default configuration:

```text
01 main: request context close
02 ContextClosedEvent
03 stop HIGH phase=200
04 stop LOW phase=100
05 singleton @PreDestroy
06 singleton DisposableBean.destroy
07 singleton custom closeResource
08 main: close finished
```

Additional Gradle/task output or system error logs may appear if the runtime environment hits issues; they are not part of the numbered list.

**Comparison:**

- Line **02 before 03**: the close notification is not confirmation that workers have stopped.
- Line **03 before 04**: lifecycle shutdown phases are processed in **descending** order.
- Line **05 after 04**: singleton destruction starts after the normal lifecycle stop phase.
- Lines **05, 06, 07**: order of destruction mechanisms **on the same bean**.
- Line **08 after 07**: the `context.close()` call has completed.

If you introduce an exception inside one of the callbacks, the output will **no longer match the success milestone table above**; in that case investigate the shutdown failure path rather than hardcoding tests assuming every milestone always appears in all situations.

### 7.5. Modifying the Experiment for Deeper Understanding

**Experiment A — change phase:** Change HIGH's phase from 200 to 50. During shutdown, the LOW phase 100 bean stops before HIGH phase 50. Remember to update the log labels so readers are not misled. `ContextClosedEvent` still precedes the stop section.

**Experiment B — remove @PreDestroy:** Remove the annotation and `beforeDestroy()` method from `CleanupSentinel`. The remaining two callbacks `DisposableBean.destroy()` and custom `closeResource()` still run as configured.

**Experiment C — remove DisposableBean:** Remove `implements DisposableBean` and `destroy()` from the sentinel; `@PreDestroy` and custom `closeResource` remain valid cleanup paths when the singleton is destroyed.

**Experiment D — alter stop(Runnable):** Omitting `callback.run()` is an anti-pattern. The processor may wait until the shutdown phase timeout expires before moving on; never do this in production.

**Experiment E — context.stop():** Try replacing `close()` with `context.stop()` in an application that keeps the context alive. That is a **lifecycle pause** command, not full singleton destruction and not `ContextClosedEvent`. Plan to call `context.start()` or `context.close()` afterward to avoid resource leaks.

**Experiment F — add @DependsOn:** If one worker is declared dependent on another worker, stop order can be governed by the dependency relationship even when phases differ. This is intentional Spring behavior, not a phase comparator bug.


## 8. How Does context.stop() Differ from context.close()?

Both methods are often confused because both imply stopping, yet their contracts differ:

| Operation | Event | Lifecycle processor | Singleton destruction | Can context be reused? |
| --- | --- | --- | --- | --- |
| `context.stop()` | Normally `ContextStoppedEvent` after calling processor stop | Stops running `Lifecycle` beans | **Does not** destroy all beans | Can call `context.start()` again if context remains valid |
| `context.close()` | Publishes `ContextClosedEvent` on normal close path | Then stops lifecycle components | **Yes**, destroys eligible singletons | No: context is closed |
| `context.start()` | Normally `ContextStartedEvent` | Calls start on lifecycle components | Does not recreate all beans | Only valid while context is active |

**Do not equate `ContextStoppedEvent` and `ContextClosedEvent`**. `close()` is not simply "call `stop()` and publish `ContextStoppedEvent`"; on the normal `doClose()` path, Spring **publishes `ContextClosedEvent` and then calls `LifecycleProcessor.onClose()`**, without turning it into a `ContextStoppedEvent`.

Another example:

```java
context.stop();  // Stops Lifecycle beans; context is not destroyed.
context.start(); // Can restart eligible Lifecycle beans.
context.close(); // Closes context, stops and then destroys singletons.
```

This is an illustrative snippet **where a `ConfigurableApplicationContext` variable `context` already exists**, not a standalone program. Do not call `start()` after the context has closed. For workers that open non-reusable resources, `stop()/start()` still requires a safe implementation rather than assuming Spring guarantees it automatically.

## 9. A Successful Lifecycle Stop Does Not Mean Every Background Task Finished

A `SmartLifecycle` bean might start an executor or message consumer. If `stop(Runnable)` merely sets `running=false` and invokes the callback while background tasks still need the database or connections, the lifecycle processor can move on to stopping lower phases and **close dependencies before those tasks finish**.

Separate the states:

```text
stop requested
    |
    +--> refusing new work
    +--> draining in-flight tasks
    +--> releasing owned resource
    +--> stop callback acknowledged
    +--> bean destroy callback(s)
```

The danger point is **reporting stop complete too early**. A solid contract must answer:

- Can the worker still accept new jobs?
- Have accepted jobs completed or been durably checkpointed?
- Are any transactions committing or messages awaiting acknowledgement?
- Have Futures/consumer acknowledgements been awaited within a deadline?
- Are shared resources closed only after all dependent components have stopped?

### 9.1. Recommendations for Executors

For a bean-owned executor, stopping usually involves:

1. Stopping submission of new tasks.
2. Calling `shutdown()` on the executor to initiate shutdown per pool contract.
3. Waiting via `awaitTermination(timeout, unit)` or bounded futures/acks.
4. If the deadline expires, triggering an appropriate cancellation/checkpoint policy and reporting an operational error.
5. Never assuming that `shutdown()` returning means all tasks are done.

`shutdownNow()` is a best-effort interruption attempt, not a guarantee that active I/O stopped or side effects rolled back. For critical tasks that must survive crashes, use durable queues/checkpoints/idempotency instead of relying solely on JVM hooks.

### 9.2. Recommendations for Message Consumers

Consumers should stop receiving new messages, drain in-flight work, ack/nack per broker protocol, and only then release connections. If a consumer has a higher phase than a connector, stopping the consumer before the connector works naturally.

However, ordering phases **does not perform draining by itself**; each component's `SmartLifecycle.stop(Runnable)` must implement it fully. `@PreDestroy` can serve as defensive cleanup for leftover resources, but it should not be the sole coordinator for a shutdown sequence with complex dependencies.

## 10. Web Server Graceful Shutdown in Spring Boot 3.3

Spring Boot 3.3 supports graceful shutdown for embedded web servers in servlet/reactive applications. You must **explicitly enable** the property in Boot 3.3 configuration:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Per Boot 3.3 documentation, graceful shutdown occurs **during application context closure**, at the **earliest phase when stopping `SmartLifecycle` beans**. It gives in-flight requests a window to complete and stops accepting new requests according to the web server's mechanism.

Distinguish clearly:

- `ContextClosedEvent` arrives when the context starts closing; it does not guarantee in-flight HTTP requests have finished.
- Inside `LifecycleProcessor.onClose()`, web server graceful shutdown participates in lifecycle stop with an appropriate phase.
- After lifecycle stop, singleton destruction callbacks are processed on the normal closing path.
- How new requests are rejected varies by server and network; do not assume every new request gets the exact same HTTP status.
- Boot's graceful timeout is the **wait duration per shutdown phase**, not a guarantee that the entire JVM shutdown finishes within that limit.

In Boot 3.3, Jetty, Reactor Netty, Tomcat, and Undertow each have their own mechanism. Jetty/Reactor Netty/Tomcat may refuse new requests at the network layer; Undertow may return `503` for new connections. This describes Boot 3.3 documentation behavior, not a fixed contract across all versions or proxy configurations.

### 10.1. Graceful Shutdown and Readiness

In a load-balanced or Kubernetes environment, you normally need to **remove the Pod/instance from traffic** before or during shutdown while giving in-flight requests time to finish.

Readiness and shutdown work together but are distinct mechanisms:

- `ReadinessState.REFUSING_TRAFFIC` indicates the application does not want new requests.
- Kubernetes readiness probes affect routing endpoints, though with probe intervals and propagation delay.
- `ContextClosedEvent` is a Spring context event and does not directly manipulate Kubernetes Endpoints.
- Web server graceful shutdown stops accepting requests according to the embedded server's capability.
- JVM shutdown hooks provide a chance to run cleanup, but offer no guarantee under forced kills.

Do not use a `@PreDestroy` method that sleeps for several seconds "waiting for the load balancer to drain routes" in place of a proper drain plan. Tune readiness, `preStop`/`terminationGracePeriodSeconds`, graceful timeouts, and ingress/server settings for the real environment.

### 10.2. Boot 3.3 Differs from Newer Version Defaults

Do not take documentation from a newer major Spring Boot version and assume Boot 3.3 enables graceful shutdown by default. Within the Boot 3.3 scope of this lesson, **explicitly configure `server.shutdown=graceful`** when that behavior is desired, and test with the actual embedded server.

## 11. Risks of Starting New Tasks in ContextClosedEvent

Suppose a listener does:

```java
@EventListener
public void onClosing(ContextClosedEvent event) {
    backgroundExecutor.submit(() -> sendFinalReport());
}
```

This is an **anti-pattern**, where `backgroundExecutor` and `sendFinalReport` are merely illustrative symbols. Calling `submit(...)` does not wait for the task to complete; right after the listener returns, Spring proceeds to lifecycle stop and singleton destruction. Executors, HTTP clients, or connection pools may be shut down before the task completes.

If the final report is **mandatory**, you need a bounded shutdown mechanism with Future/ack and clear ownership. Better options are:

- A `SmartLifecycle` worker that stops accepting new work, drains, and invokes the callback only after finishing.
- An in-app shutdown orchestrator with explicit dependency ordering.
- Durable outbox/job state so messages can still be retried after a restart.
- Avoiding untimed network calls inside a JVM shutdown hook.

If the notification is only best-effort telemetry, you can emit a brief metric/log in `ContextClosedEvent`. Never hinge data correctness on whether an event listener finishes sending an outbound request in time.

## 12. Exceptions and Imperfect Shutdown Paths

The sequence in section 1 is the **normal closing path** when Spring can execute every phase cleanly. Several situations produce different observed orders:

### 12.1. Context Refresh Failure

If bean initialization or `SmartLifecycle.start()` throws an error during refresh, Spring may clean up already created singletons without traversing a normal `ContextClosedEvent → LifecycleProcessor.onClose()` path. Spring Framework documentation warns that **stop notifications are not guaranteed to occur before destruction** when a refresh is aborted or in special refresh scenarios.

Therefore, destruction callbacks must tolerate components that **never started** or only partially started. Do not write `@PreDestroy` assuming `stop()` ran on every failure path.

### 12.2. Context Close Listener Throws an Error

Spring handles exceptions thrown while publishing `ContextClosedEvent` in `doClose()` and logs them so cleanup can continue. However, this does not mean every exception in every callback is swallowed identically or that shutdown remains clean under severe failures.

Listeners should have minimal side effects and explicit timeouts. If you must report an error, log/emit a metric with enough context without breaking cleanup for other beans.

### 12.3. Stop Callback Fails to Run or Phase Times Out

If a `SmartLifecycle.stop(Runnable)` implementation forgets `callback.run()`, the processor may wait until the timeout expires before moving on. Bean state may not truly be stopped; resources get destroyed while workers are still using them.

This is a lifecycle design bug, not `@PreDestroy` "running too early". Fix the callback invocation and deadline-bounded drain logic.

### 12.4. Destruction Callback Throws an Exception

A failing `DisposableBean.destroy()` or destroy method should not be used as primary shutdown control flow. Spring attempts to log cleanup errors and continue destroying remaining beans where possible.

Design cleanup to be idempotent, non-blocking without bounds, and supportive of retries/recovery in external systems if side effects fail. Never guarantee financial transactions or durable notifications solely on a callback running for a few seconds before JVM exit.

### 12.5. SIGKILL, OOM, Crash, or Power Loss

No Java/Spring mechanism guarantees `ContextClosedEvent`, `SmartLifecycle.stop()`, and `@PreDestroy` will run if the process is forcibly killed. Design idempotency, lease timeouts, transaction timeouts, broker redelivery, and reconciliation for cases where callbacks never execute.

### 12.6. Unmanaged Objects/Scopes

If a worker is instantiated with `new` outside the container, Spring has no way to know to call its stop/destroy methods. For prototype beans, even though Spring initializes the instance, the container by default does not track destruction callbacks for every prototype until context close. The owner must explicitly close the resource.

## 13. Common Misconceptions

| Statement or symptom | Why is it wrong/incomplete? | How to handle |
| --- | --- | --- |
| "ContextClosedEvent means all workers have stopped" | The event is published **before** lifecycle stop | Wait for stop callbacks/acks as needed |
| "Singleton @PreDestroy runs before SmartLifecycle.stop" | Contradicts the normal close sequence | Check lifecycle phases and failure paths |
| "context.stop() and context.close() are the same" | stop does not destroy cached singletons | Choose the API based on pausing vs. closing |
| "ContextClosedEvent and ContextStoppedEvent are the same" | Two events for two distinct operations | Use the proper event type |
| "@Order(-100) makes @PreDestroy run before ContextClosedEvent" | @Order does not change phase order | Use the proper lifecycle extension point |
| "Lower getPhase() stops first" | At shutdown, **higher** phases stop first | Give dependent consumers higher phases |
| "Every singleton gets stop() called" | Only beans implementing Lifecycle participate in stop | Use destruction callbacks for non-Lifecycle beans |
| "Phase also controls bean creation order" | Phase does not replace dependency/initialization order | Use injection/depends-on for bean creation |
| "stop(Runnable) does not need the callback" | Processor may wait until timeout | Call callback exactly once when truly stopped |
| "Callback running means every Future finished" | Implementation may signal stopped too early | Drain and await with a deadline |
| "@PreDestroy is how to pause a worker" | Destruction callbacks are not for runtime pausing | Use Lifecycle.stop / business API |
| "Singletons are destroyed by name" | Bean destruction follows dependency/lifecycle ordering | Do not rely on bean names or file order |
| "Every prototype is auto-destroyed on context close" | Prototype destruction is not automatically tracked by Spring | Caller/owner takes responsibility |
| "ContextClosedEvent is guaranteed after SIGKILL" | Process gets no chance to clean up | Design crash recovery |
| "server.shutdown=graceful is the default in Boot 3.3" | Must be explicitly configured within Boot 3.3 scope | Verify property and server |
| "Graceful timeout is an SLA for the whole JVM" | Wait time is per phase, plus other steps | Tune app/container budgets |
| "Listener onClosing submitting an async job means it succeeded" | submit does not ensure completion/durability | Await ack, use outbox when critical |
| "Once started, shutdown cannot fail" | Shutdown callbacks can error or time out | Monitor duration and error metrics |

## 14. Operational Shutdown Verification Checklist

1. **Who initiated shutdown?** `context.close()`, JVM shutdown hook, SIGTERM, deployment rollout, IDE stop, or SIGKILL?
2. **Did `ContextClosedEvent` fire?** If not, check for refresh errors, process crashes, or unregistered hooks.
3. **Did any listener block or throw?** Shutdown notifications themselves must not stall the shutdown pipeline.
4. **Which beans implement Lifecycle/SmartLifecycle?** List phases, `isRunning()`, and ownership.
5. **Is phase order appropriate?** Which resources do workers depend on, and which resources must stop later?
6. **Are there @DependsOn/injected dependencies?** Dependency relationships can affect stop and destruction order.
7. **Does stop(Runnable) invoke its callback?** Does it signal after actual draining or immediately after submitting a stop task?
8. **Is there a per-phase timeout?** Check `spring.lifecycle.timeout-per-shutdown-phase` and whether real durations fit.
9. **Do singleton @PreDestroy callbacks release resources cleanly?** Any double-close, deadlock, or untimed blocking I/O?
10. **How are prototypes and `new`-created objects cleaned up?** Spring does not track them by default.
11. **Is there a web server?** Is `server.shutdown=graceful` enabled and are new requests drained from routing properly?
12. **What readiness and termination budgets do Kubernetes/LoadBalancers use?** Avoid closing resources while requests remain in flight.
13. **Are there durable jobs or uncommitted transactions?** Shutdown hooks do not replace transactions/acks/recovery.
14. **Are there multiple ApplicationContexts or a context hierarchy?** An event can propagate across contexts; log the context ID accurately.
15. **Are failure paths tested?** Test stop timeouts, destroy exceptions, startup failures, SIGTERM, and forced kills as appropriate for the environment.
16. **Are logs sufficient and safe?** Record milestones, bean names, phases, durations, request counts, and root causes; avoid secrets/tokens/sensitive data.

### 14.1. Measure Three Distinct Intervals

```text
T0: context.close requested
T1: ContextClosedEvent listeners completed
T2: LifecycleProcessor stop phase(s) completed / timed out
T3: singleton destruction completed
T4: context.close returned
```

- `T0→T1`: close notification and listener execution time.
- `T1→T2`: lifecycle component stop and in-flight draining time.
- `T2→T3`: destruction callback duration.
- `T3→T4`: final context cleanup.

Do not rely on a single "shutdown took X seconds" metric to diagnose root causes when these phases behave very differently. These timestamps are an observation model, not an API where Spring automatically emits all four markers for every application.

## 15. Self-Check

**Q1.** During a normal `context.close()`, does `ContextClosedEvent` arrive before or after `SmartLifecycle.stop()`?

**A:** Before. The event signals closing has begun; lifecycle stop is invoked after the event is published on the standard path.

**Q2.** Why is a bean with `@PreDestroy` but without `SmartLifecycle` still cleaned up?

**A:** Because it participates in singleton destruction; it does not need to implement Lifecycle to have a destruction callback.

**Q3.** In what order are two SmartLifecycle beans with phases 20 and 100 stopped?

**A:** In descending phase order: 100 before 20, unless an explicit dependency relationship takes precedence.

**Q4.** When should `callback.run()` be called inside `stop(Runnable)`?

**A:** After the stop operation has truly completed. When stopping asynchronously, invoke the callback when the stop task finishes, not merely when scheduled.

**Q5.** Does `ContextStoppedEvent` replace `ContextClosedEvent` during close?

**A:** No. `context.stop()` and `context.close()` are two distinct lifecycle operations.

**Q6.** What is the order of `@PreDestroy`, `DisposableBean.destroy()`, and a custom destroy method on the **same bean**?

**A:** `@PreDestroy` → `DisposableBean.destroy()` → custom destroy method, when all three callbacks are validly configured with distinct names.

**Q7.** Does every bean in the context get `stop()` called before destruction?

**A:** No. Only beans participating in `Lifecycle`/`SmartLifecycle` belong to the lifecycle stop protocol; other singletons may only have destruction callbacks.

**Q8.** If a ContextClosedEvent listener submits an async task and returns, does Spring wait for that task before destroying beans?

**A:** Not automatically. You must await/ack with a deadline or place shutdown responsibility in the appropriate lifecycle contract.

**Q9.** Does `context.stop()` automatically invoke every `@PreDestroy`?

**A:** No. It does not perform bean destruction.

**Q10.** If refresh fails when a SmartLifecycle.start() throws, is the exact event→stop→destroy sequence guaranteed?

**A:** No. Cleanup during an aborted refresh follows a different path; stop notifications may not occur before destruction.

**Q11.** In Spring Boot 3.3, which property enables graceful HTTP shutdown?

**A:** `server.shutdown=graceful`, optionally paired with `spring.lifecycle.timeout-per-shutdown-phase` to tune phase wait times.

**Q12.** Under SIGKILL, is `@PreDestroy` guaranteed to run?

**A:** No. Data and work queues must be designed to tolerate crashes.

**Q13.** Is a prototype bean with `@PreDestroy` automatically destroyed per instance by Spring on context.close()?

**A:** No, per default prototype rules. The caller/owner is responsible for cleanup.

**Q14.** If a singleton resource is used by a dependent consumer, which one should stop first?

**A:** The consumer should stop accepting work and drain first, followed by stopping the resource/connector. Express the constraint with phases and dependencies.

## 16. Summary and Official Documentation

Key points:

- **ContextClosedEvent**: published when the context begins closing, **before** Lifecycle stop and singleton destruction on the normal close path.
- **LifecycleProcessor.onClose()**: stops running `Lifecycle`/`SmartLifecycle` beans; **higher** `SmartLifecycle` phases **stop first**.
- **SmartLifecycle.stop(Runnable)**: the callback must be invoked after actual stopping completes; the processor enforces timeouts **per phase**.
- **destroyBeans()**: after lifecycle stop, the container destroys cached singleton beans. On the **same bean**: `@PreDestroy` → `DisposableBean.destroy()` → custom destroy method, when all three are configured.
- **context.stop() is not context.close()**: do not confuse `ContextStoppedEvent` with `ContextClosedEvent`.
- **Exceptions**: startup refresh failures, prototypes, unmanaged objects, async callbacks, SIGKILL, and timeouts may bypass parts of the three standard steps.
- **Spring Boot 3.3 web graceful shutdown**: enable `server.shutdown=graceful`; web server stop has its own phase/lifetime, and ContextClosedEvent must not be treated as proof that draining finished.
- **Proper shutdown** means stopping new work intake, completing or checkpointing in-flight tasks, releasing resources according to ownership, and having recovery strategies when the JVM stops abnormally.

References:

1. [Spring Framework 6.1 — AbstractApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): `doClose()`, `destroyBeans()`, and `close()`.
2. [Spring Framework 6.1 — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): `onClose()`, lifecycle stop phases, and default timeout.
3. [Spring Framework 6.1 — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html): `stop(Runnable)`, `getPhase()`, `isAutoStartup()`.
4. [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): initialization/destruction order and stop not being guaranteed on failed refreshes.
5. [Spring Framework — Using depends-on](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html): dependent beans are destroyed before dependency beans.
6. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): graceful web shutdown in an early SmartLifecycle phase and timeout configuration.
7. [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): event lifecycle, ready/readiness, and shutdown hooks.

**Conclusion:** A "closing" notification does not mean "already stopped". A `stop` call does not mean "beans already destroyed". For safe shutdown, use **ContextClosedEvent**, **LifecycleProcessor**, and **singleton destruction** for their respective roles, while clearly defining who owns each resource and what must finish before dependencies are closed.
