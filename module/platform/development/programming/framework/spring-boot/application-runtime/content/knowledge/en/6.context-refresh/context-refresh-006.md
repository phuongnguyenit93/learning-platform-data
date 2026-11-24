# The Role of `LifecycleProcessor` in Context Refresh and Close

In Spring Boot, many components need not only to **be created as beans**, but also to **start operating**, **stop accepting new work**, and **release resources** in the proper order. Examples include a connection to an external system, a message consumer from a queue, a scheduler, or a background task processor. To coordinate **starting/stopping operations** of these components when the `ApplicationContext` is refreshed or closed, Spring Framework uses **`LifecycleProcessor`**.

This lesson focuses on `LifecycleProcessor` across the **`refresh()` → run application → `close()`** cycle of `ApplicationContext`, under Spring Framework 6.1/Spring Boot 3.3 on Java 17 or higher. The key points are: where it runs, which beans it manages, how `phase` determines ordering, how `SmartLifecycle.stop(Runnable)` works, and why **stop** differs from **destroy**.

## 1. Initial Mental Model: A Bean Has Three Distinct Types of State

Suppose an application has a component that receives jobs from a queue:

1. Spring **creates the bean** and injects dependencies; the bean exists in the container.
2. The component **starts**: opens connections, registers consumers, begins processing.
3. The component **stops**: stops accepting new work, finishes or hands off in-flight work.
4. When the context closes, Spring can **destroy** the bean: invokes destruction callbacks to release remaining resources.

Do not lump all of these into "Spring creates the bean" or "the JVM exits." Three behaviors must be separated:

| Behavior | Typical Spring mechanism | Meaning |
| --- | --- | --- |
| Create/initialize bean | Constructor, dependency injection, `BeanPostProcessor`, `@PostConstruct` | Turns a bean definition into a configured object |
| Start/stop operation | `Lifecycle`, `SmartLifecycle`, coordinated by `LifecycleProcessor` | Determines when the component **runs** and **stops running** |
| Destroy bean | `@PreDestroy`, `DisposableBean.destroy()`, destroy method | Releases resources when the container destroys singletons |

A bean can already be created and initialized successfully yet still not have called `start()`. Conversely, after `stop()`, the bean object **still exists** until the destroy step. That distinction enables controlled shutdown.

## 2. What Is `LifecycleProcessor`?

`org.springframework.context.LifecycleProcessor` is an interface extending `Lifecycle` and adding two methods:

~~~java
void onRefresh();
void onClose();
~~~

Meaning:

- **`onRefresh()`**: called by the context when finishing the refresh phase to coordinate auto-starting eligible components.
- **`onClose()`**: called by the context during the closing phase to request stopping components that are still running.

`LifecycleProcessor` also has the behaviors inherited from `Lifecycle`: `start()`, `stop()`, and `isRunning()`. They allow the context to support explicit start/stop operations without necessarily closing the context.

Spring Framework provides **`org.springframework.context.support.DefaultLifecycleProcessor`** as the default implementation. When refreshing the context, Spring looks for a bean named **`lifecycleProcessor`**. If the application does not define that bean, Spring creates the default implementation to use.

Point to remember: `LifecycleProcessor` is the **coordinator**, not each individual business component. It locates and invokes beans implementing `Lifecycle`/`SmartLifecycle` according to the appropriate rules. Therefore, developers typically implement `SmartLifecycle` on components needing controlled lifecycles, rather than writing a new `LifecycleProcessor`.

## 3. Two Key Positions Inside `refresh()` and `close()`

### Inside `ApplicationContext.refresh()`

With `AbstractApplicationContext` as the base, the final part of the refresh sequence can be understood as follows:

~~~text
ApplicationContext.refresh()
    |
    +-- Prepare BeanFactory and process BeanDefinitions
    +-- Register BeanPostProcessors
    +-- Instantiate singletons needing early creation
    |
    +-- finishRefresh()
          |
          +-- initLifecycleProcessor()
          |     Obtain bean "lifecycleProcessor" if present,
          |     otherwise create DefaultLifecycleProcessor
          |
          +-- lifecycleProcessor.onRefresh()
          |     Auto-start eligible SmartLifecycle beans
          |
          +-- publish ContextRefreshedEvent
    |
    v
refresh() completes
~~~

Easy-to-miss detail: **`onRefresh()` runs before `ContextRefreshedEvent`** in the default `AbstractApplicationContext` flow. Therefore, a `SmartLifecycle` bean auto-started inside `onRefresh()` may already be in the running state when a `ContextRefreshedEvent` listener is invoked.

`onRefresh()` is not the "first bean creation." Most non-lazy singletons were already created earlier during `finishBeanFactoryInitialization`. However, `SmartLifecycle` can cause related beans to be instantiated when the coordinator resolves beans or prepares to start them, even if marked lazy.

In a typical Spring Boot application, `SpringApplication.run(...)` executes the context refresh pipeline and only then moves on to `ApplicationStartedEvent`, runners, and `ApplicationReadyEvent`. Consequently, `SmartLifecycle` auto-startup occurs **before** runners on a successful startup path.

### Inside `ApplicationContext.close()`

When the context is closed in a controlled manner, the core of `AbstractApplicationContext.doClose()` follows this order:

~~~text
context.close()
    |
    +-- publish ContextClosedEvent
    |
    +-- lifecycleProcessor.onClose()
    |     Stop running Lifecycle beans
    |     In descending phase order, respecting dependencies
    |
    +-- destroyBeans()
    |     Invoke @PreDestroy / DisposableBean / destroy callbacks
    |
    +-- closeBeanFactory() and context close finalization
    |
    v
context is no longer active
~~~

Therefore, **`ContextClosedEvent` is published before `onClose()`**, and regular bean destruction callbacks execute **after the stop step**. A listener receiving `ContextClosedEvent` should not assume all `SmartLifecycle` beans have already stopped at the exact moment the listener begins executing.

This sequence describes the normal close path. If the process is killed forcibly, terminated with `kill -9`, or suffers a critical crash, the JVM may fail to run shutdown hooks and Spring cannot guarantee every stop/destroy callback runs.

## 4. How Do `Lifecycle` and `SmartLifecycle` Differ?

### `Lifecycle`: Basic Run/Stop Control Interface

~~~java
package org.springframework.context;

public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Implementing `Lifecycle` provides start/stop hooks that can be called explicitly. **A bean implementing only plain `Lifecycle` does not auto-start merely because the context refreshes.** It can be started when `context.start()` is called or when another component/dependency requires the coordinator to start it.

### `SmartLifecycle`: Auto-Startup, Phased Ordering, and Async Stop Support

`SmartLifecycle` extends `Lifecycle` and `Phased`. Its key methods:

~~~java
boolean isAutoStartup();
int getPhase();
void stop(Runnable callback);
~~~

Meaning:

- **`isAutoStartup()`**: indicates whether to auto-start during `onRefresh()`; the default on `SmartLifecycle` is `true`.
- **`getPhase()`**: startup/shutdown ordering group. Lower values generally start earlier and stop later.
- **`stop(Runnable callback)`**: allows the bean to signal **it has truly stopped** by calling `callback.run()`. This is the method the coordinator invokes when stopping a `SmartLifecycle` bean.

| Criterion | Plain `Lifecycle` | `SmartLifecycle` |
| --- | --- | --- |
| Has `start()`, `stop()`, `isRunning()` | Yes | Yes |
| Auto-starts on context refresh | Not by default | Yes if `isAutoStartup() == true` |
| Default phase used by coordinator | `0` if not `Phased` | `Integer.MAX_VALUE` |
| Has callback confirming stop completion | Not in interface | Yes, via `stop(Runnable)` |
| Best suited for | Components needing explicit start/stop only | Listeners/consumers/workers needing auto-startup or ordered shutdown |

**Exception to know:** explicit bean dependencies take precedence over phase and individual auto-start choices. Therefore, do not claim a `Lifecycle` or `SmartLifecycle` bean with `isAutoStartup=false` "cannot" be started during refresh in all cases; it may need to be started because it is a dependency of another bean being started.

`SmartLifecycle` has a bean-lookup mechanism for auto-startup even when the bean is marked lazy. Hence, merely adding `@Lazy` is not a reliable way to stop a `SmartLifecycle` from auto-starting. To control auto-startup, use `isAutoStartup()` and design appropriate dependencies.

## 5. The `phase` Rule: Start Ascending, Stop Descending

Suppose there are three components:

- `connection` has phase **-100**, establishing the underlying connection.
- `consumer` has phase **0**, reading data over the connection.
- `publisher` has phase **100**, depending on the consumer's activity.

If all three are eligible to start:

~~~text
REFRESH / START:
connection (-100) --> consumer (0) --> publisher (100)

CLOSE / STOP:
publisher (100) --> consumer (0) --> connection (-100)
~~~

This is the rule of **starting from lowest phase to highest, stopping from highest phase to lowest**. Within the same phase, **do not rely on an exact order** unless other constraints exist.

Several important details:

1. Phase can be negative, zero, or positive. It is not a fixed enum and does not need to be contiguous.
2. `SmartLifecycle` defaults to `Integer.MAX_VALUE`, meaning it normally starts quite late and stops quite early compared to phase-0 beans.
3. Beans implementing only `Lifecycle` are normally assigned phase 0 by the coordinator.
4. **`depends-on`/container-known dependencies can take priority over phase**. Dependent beans must start after their dependencies and stop before their dependencies, even if phases were declared in reverse.
5. Use phase to express operational requirements. For example, a consumer should stop receiving messages before closing the connection it uses.

Phase **does not replace bean creation order**, nor is it the order of `ApplicationRunner`s. It is the coordination axis for **starting/stopping Lifecycle beans**.

## 6. `stop()` and `stop(Runnable)`: The Easiest Place to Make a Mistake

A `SmartLifecycle` implementation must care about both ways of stopping:

~~~java
@Override
public void stop() {
    // Stop synchronously if appropriate
}

@Override
public void stop(Runnable callback) {
    // Stop operation, then report completion
    stop();
    callback.run();
}
~~~

This is a simple illustrative snippet. For **asynchronous** shutdown, the right approach is calling the callback only after stop work actually finishes, for example:

~~~java
@Override
public void stop(Runnable callback) {
    stopAcceptingNewMessages();

    backgroundExecutor.execute(() -> {
        try {
            awaitInFlightMessages();
        } finally {
            running = false;
            callback.run();
        }
    });
}
~~~

The snippet above is **mechanism-illustrating code**, assuming the class already has `stopAcceptingNewMessages()`, `backgroundExecutor`, `awaitInFlightMessages()`, and `running` state; it is not a standalone compilable program.

When stopping by phase, `DefaultLifecycleProcessor` needs to know when beans in the current phase finish so it can move to subsequent phases. **If a `SmartLifecycle` bean forgets to call `callback.run()`, the processor may have to wait until the phase timeout expires**, dragging out shutdown. Do not call the callback right after merely issuing a stop command if the component still has active work that must finish.

Key contract points:

- `SmartLifecycle` beans are stopped by the processor via **`stop(Runnable)`**, not necessarily via the zero-argument `stop()`.
- For synchronous stop implementations, you can call `stop()` and then `callback.run()` in `finally` to guarantee completion signaling even if an error occurs.
- For asynchronous stop, guarantee the callback is invoked **exactly once when work completes**, and handle cases where the task cannot be scheduled.
- `isRunning()` should reflect actual operational state. An inaccurate running flag can cause the processor to mishandle the component.
- Design `start()` and `stop()` to be safely idempotent: calling `start()` on an already-running object and `stop()` on an already-stopped object should not cause duplicate side effects.

### Shutdown Timeout Per Phase

In Spring Framework **6.1**, `DefaultLifecycleProcessor.setTimeoutPerShutdownPhase(long)` configures the maximum wait time per phase group; the default value per the 6.1 API is **30,000 ms (30 seconds)**. This is a wait limit for stop callbacks of a phase group, **not a lifetime limit for the entire JVM** or a mandatory duration every shutdown must take.

In Spring Boot 3.3, the related timeout can be configured via:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Setting 20 seconds is just a configuration example; choose based on the real stop duration of your components. Also consider **the external container/orchestrator timeout**, because if the external system sends a kill signal before Spring finishes, beans can still be cut short.

## 7. Runnable Example: Observing Two Phases During Refresh and Close

This example uses **Java 17 + Spring Boot 3.3.13 + Gradle**. To keep output focused on Lifecycle ordering, the program runs **without opening a web server**, disables the banner and startup info logged by `SpringApplication`. `LifecycleProcessor` itself still performs all its work.

### Project Structure

~~~text
lifecycle-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/lifecycle/LifecycleDemoApplication.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'lifecycle-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    // Gradle native BOM manages versions for Spring Boot starters.
    implementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Because the BOM is declared, `spring-boot-starter` does not need an explicit version. You need a Gradle version compatible with the Spring Boot 3.3 plugin and network access to download dependencies on the first build. If working inside an existing Spring Boot project, use the project's dependency configuration instead of adding duplicate plugins.

File `src/main/java/com/example/lifecycle/LifecycleDemoApplication.java`:

~~~java
package com.example.lifecycle;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class LifecycleDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(LifecycleDemoApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            System.out.println("MAIN contextActive=" + context.isActive());
        }
        System.out.println("MAIN after close");
    }

    @Bean
    SmartLifecycle receiver() {
        return new PhasedWorker("receiver", -100);
    }

    @Bean
    SmartLifecycle processor() {
        return new PhasedWorker("processor", 100);
    }

    @Bean
    ApplicationRunner runner() {
        return args -> System.out.println("RUNNER");
    }

    @Bean
    DisposableBean cleanupResource() {
        return () -> System.out.println("DESTROY resource");
    }

    @EventListener
    public void afterRefresh(ContextRefreshedEvent event) {
        System.out.println("EVENT ContextRefreshedEvent");
    }

    @EventListener
    public void afterStarted(ApplicationStartedEvent event) {
        System.out.println("EVENT ApplicationStartedEvent");
    }

    @EventListener
    public void afterReady(ApplicationReadyEvent event) {
        System.out.println("EVENT ApplicationReadyEvent");
    }

    @EventListener
    public void beforeStop(ContextClosedEvent event) {
        System.out.println("EVENT ContextClosedEvent");
    }

    static final class PhasedWorker implements SmartLifecycle {
        private final String name;
        private final int phase;
        private volatile boolean running;

        PhasedWorker(String name, int phase) {
            this.name = name;
            this.phase = phase;
        }

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("START " + name + " phase=" + phase);
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("STOP " + name + " phase=" + phase);
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
        public int getPhase() {
            return phase;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }
    }
}
~~~

The code uses `DisposableBean` to highlight the difference between **stopping `SmartLifecycle` components** and **destroying resources at the end of context closing**. The two beans `receiver` and `processor` only log start/stop. The `cleanupResource` bean logs destroy and does **not** implement `Lifecycle`.

### Running

From the project directory with Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If you do not have a wrapper yet but have a compatible Gradle installed, run `gradle bootRun`. Lines from Gradle or the logging system may also appear; **the lines produced by `System.out.println` in the example code** on a successful run appear in this order:

~~~text
START receiver phase=-100
START processor phase=100
EVENT ContextRefreshedEvent
EVENT ApplicationStartedEvent
RUNNER
EVENT ApplicationReadyEvent
MAIN contextActive=true
EVENT ContextClosedEvent
STOP processor phase=100
STOP receiver phase=-100
DESTROY resource
MAIN after close
~~~

Explaining each group:

1. `receiver` has phase -100 so it starts before `processor` at phase 100, even though both are auto-starting `SmartLifecycle` beans.
2. `ContextRefreshedEvent` appears **after** `onRefresh()` has started the components.
3. `ApplicationStartedEvent` appears after refresh; `ApplicationRunner` runs next; `ApplicationReadyEvent` appears after the runner.
4. When `run` returns, the context is still active. The `try-with-resources` block then calls `context.close()`.
5. `ContextClosedEvent` is published before the lifecycle processor stops the beans.
6. Stop goes in reverse phase order: 100 then -100.
7. `DESTROY resource` appears when Spring starts destroying singletons after the stop phase. It demonstrates that destroy callbacks are a separate mechanism.
8. `MAIN after close` appears only after `close()` returns.

**Note on output:** the system may emit additional Spring/Gradle logs; the example does not predict every line from libraries. The output above accurately describes the lines produced by `System.out.println` in the example when there are no errors and no other custom components intervening in the lifecycle chain.

### Try Changing a Phase

Change the `processor` bean to:

~~~java
@Bean
SmartLifecycle processor() {
    return new PhasedWorker("processor", -200);
}
~~~

When re-running, `processor` at phase -200 will **start before** `receiver` (-100), and **stop after** `receiver`. Only `phase` changes, with no manual ordering in `main`.

### Try `isAutoStartup()`

Change `return true;` in `isAutoStartup()` of `PhasedWorker` to `return false;`. With no special dependency constraints and without calling `context.start()`, these two beans **do not auto-start during refresh**. They are still created as beans, can receive injection, and wait for an explicit start command.

To test separately, you can call:

~~~java
context.start();
~~~

inside the example's `try` block, after printing the active status. This is an **explicit operation on an active context**; the coordinator will start eligible `Lifecycle` beans that are not yet running, and when `context.close()` occurs it will continue stopping them.

## 8. Relationship with `@PostConstruct`, `@PreDestroy`, and `DisposableBean`

For example, a connection bean might have these callbacks:

~~~java
@PostConstruct
public void initialize() {
    // Prepare data, validate initial configuration
}

@Override
public void start() {
    // Start consumer or worker threads
}

@Override
public void stop() {
    // Stop accepting work and halt processing
}

@PreDestroy
public void release() {
    // Close sockets, release remaining resources
}
~~~

This is **illustrative code showing methods within a single class implementing the proper interfaces**, not a complete Java class. Annotations `@PostConstruct`/`@PreDestroy` require the corresponding `jakarta.annotation.*` imports in Spring Boot 3.x.

Typical sequence observed for a non-lazy singleton with auto-start `SmartLifecycle`:

~~~text
Create bean, inject, @PostConstruct
             |
             v
LifecycleProcessor.onRefresh() -> start()
             |
             v
ContextRefreshedEvent -> Started -> Ready
             |
             v
ContextClosedEvent
             |
             v
LifecycleProcessor.onClose() -> stop(Runnable)
             |
             v
Destroy bean: @PreDestroy / DisposableBean / destroy-method
~~~

Do not take the sequence above as a promise for **all lazy beans**, or for a bean created late after refresh. Furthermore, when multiple types of destroy callbacks exist on the same bean, Spring also defines an ordering among them; this lesson simply emphasizes that **stop coordinated by LifecycleProcessor precedes singleton destruction on the normal context-closing path**.

**Design principle:** `@PostConstruct` is suited for initializing a single bean's state; `SmartLifecycle.start()` is suited for issuing start commands in order relative to other components; `stop(Runnable)` is suited for coordinated stopping; `@PreDestroy`/`DisposableBean` finishes resource cleanup.

## 9. `context.start()` and `context.stop()` Are Not `refresh()` and `close()`

You can invoke directly:

~~~java
context.stop();   // Stop running Lifecycle beans
context.start();  // Ask eligible Lifecycle beans to start again
context.close();  // Close the container and destroy singletons
~~~

Differences:

| Call | Scope | Can the context continue operating? |
| --- | --- | --- |
| `context.refresh()` | Builds/refreshes the container per the context type's contract | Yes, if refresh succeeds |
| `context.start()` | Invokes processor `start()` on eligible Lifecycle beans | Yes |
| `context.stop()` | Invokes processor `stop()` on running lifecycle beans | Yes; `start()` can be called again if design supports it |
| `context.close()` | Publishes close event, stops Lifecycle beans, then destroys beans and closes container | No; you cannot simply call `start()` to revive a closed context |

Not every context type supports repeated refreshes after the first refresh; for example, `GenericApplicationContext` only supports a single refresh. Do not treat `refresh()` as a safe restart command for every Spring Boot application.

`ContextStartedEvent` and `ContextStoppedEvent` are tied to explicit `context.start()/stop()` calls; they are **not equivalent** to Spring Boot's `ApplicationStartedEvent`/`ApplicationReadyEvent`. The names look similar, but when they are published and their lifecycle meanings differ.

## 10. Connecting to Spring Boot Graceful Shutdown

When a Spring Boot application runs a web server, Spring Boot can arrange to stop accepting HTTP requests and wait for in-flight requests via **graceful shutdown**, depending on server version/configuration. It uses lifecycle extension points to participate in ordered shutdown.

Example configuration:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

These values only govern the **controlled context-closing** process. They do not automatically turn every external connection into a graceful shutdown. If the application manages its own consumers, workers, or sockets, you must implement logic to stop accepting new work and await in-flight work inside `SmartLifecycle.stop(Runnable)` or an appropriate resource-management mechanism.

Some principles:

- Set phases intentionally to **stop work-producing sources before stopping the underlying resources those sources need**.
- Ensure stop never hangs indefinitely: use internal timeouts, valid callbacks, and error tracking.
- Ensure Spring's timeout value and the shutdown deadline of Kubernetes/systemd/containers do not conflict.
- Do not assume the `ContextClosedEvent` means all requests/consumers have stopped; this event may fire before bean stopping runs.
- If the application is killed forcibly, Java callbacks may not finish running. For critical workloads, data guarantees belong at the queue, transaction, or storage layer.

## 11. Choosing `phase` When Components Depend on Each Other

Suppose an application processing messages has three components:

| Component | Role | Illustrative phase |
| --- | --- | --- |
| `connectionManager` | Connects to an external service | -100 |
| `messageConsumer` | Receives messages over the connection | 0 |
| `reportingWorker` | Processes final results | 100 |

By phase, start is `connectionManager → messageConsumer → reportingWorker`, and stop is the reverse. **However**, that is just one example design. Phase by itself does not prove that order is right for every system. If `reportingWorker` must continue processing until the consumer has completely stopped, you might need to **stop the consumer before the worker**. In that case, redesign phases and dependencies around the real data flow instead of copying numbers mechanically.

When components have firm bean-level dependencies, declaring explicit dependencies via Spring's mechanism can help the coordinator order start/stop. Even so, phases must still be read and verified to avoid conflicts with other framework beans.

For beans in the same phase, treat their relative order as unspecified. If strict ordering is required, use distinct phases and appropriate dependencies.

## 12. Configuring Timeout or Replacing the Default Processor

In most Spring Boot applications, you do not need to declare a `LifecycleProcessor` bean yourself. The default implementation already supports phases and callbacks.

When you need to adjust the wait time in Spring Boot 3.3, prefer configuring:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

At the Spring Framework level, `DefaultLifecycleProcessor` has the method:

~~~java
processor.setTimeoutPerShutdownPhase(30_000L);
~~~

This line is **illustrative code** when you already have a `DefaultLifecycleProcessor processor` variable; it is not a call to add to every application.

You can replace the processor by defining a bean named `lifecycleProcessor`, but doing so replaces a critical context-wide coordinator. If you only want to change the timeout, use Spring Boot configuration whenever possible. When replacing it, you must preserve the full `LifecycleProcessor` contract, including `onRefresh`, `onClose`, start/stop coordination, and dependency handling.

## 13. Common Mistakes When Implementing Lifecycle Yourself

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Bean was created, but `start()` does not run after refresh | Implemented only `Lifecycle`; or `isAutoStartup()` returns `false` | Use `SmartLifecycle` and the right auto-start setting; check dependencies |
| `start()` called before underlying resources are ready | Unsuitable phase or undeclared dependency | Give underlying resources a lower phase and declare required dependencies |
| Shutdown stalls for exactly the timeout before continuing | `stop(Runnable)` fails to call callback, calls it too late, or stop work is stuck | Ensure callback is invoked once stopped; add timeouts/logging to diagnose |
| `ContextClosedEvent` observed yet bean is still running | Close event is published **before** the lifecycle processor stops beans | Watch `stop` logs or stop callbacks instead of treating the close event as stop-complete |
| `@PreDestroy` runs without a `STOP` log | Bean is not among running Lifecycle beans; or app only uses destroy callbacks | Check interfaces/`isRunning()`/actual state |
| `SmartLifecycle` annotated `@Lazy` is still created at startup | Auto-start mechanism may need to instantiate the bean in order to start it | Use `isAutoStartup()` appropriately; do not rely on lazy-init as a lifecycle switch |
| Calling `context.stop()` expecting the whole app to shut down | `stop()` does not destroy beans or close the container | Call `close()`/valid shutdown when you want to release the context |
| High-phase stop runs before a bean it depends on, causing errors | Stop relationship not properly expressed or wrong phases used | Design phases around required stop order and declare dependencies explicitly |
| Sleeping too long with `Thread.sleep` inside stop callback | Blocks shutdown progress, potentially exceeding container limits | Stop conditionally, using callbacks and bounded timeouts instead of waiting forever |

## 14. Self-Check Questions

1. **Does `LifecycleProcessor.onRefresh()` happen before or after `ContextRefreshedEvent` in `AbstractApplicationContext`?** Before.
2. **Does a bean implementing only `Lifecycle` auto-start on refresh by default?** No; an exception can arise from dependency constraints of another auto-starting component.
3. **What value does a `SmartLifecycle` return by default from `isAutoStartup()`?** `true`.
4. **What default phase does a `SmartLifecycle` without an overridden `getPhase()` have in Spring 6.1?** `Integer.MAX_VALUE`.
5. **Given two beans with phases -10 and 20, which starts first?** -10; on normal close, 20 stops first.
6. **Why must `stop(Runnable)` invoke `callback.run()`?** So the coordinator knows stopping has finished and can continue phased shutdown without waiting for the timeout.
7. **Does `ContextClosedEvent` being published mean all beans have been destroyed?** No; the close event is published before stop and destroy.
8. **Does `context.stop()` destroy beans?** No. It coordinates stopping operations, whereas `close()` closes the context and destroys eligible beans.
9. **Can a bean that is running after refresh but is not a `SmartLifecycle` be stopped when the context closes?** Yes, if it is a running `Lifecycle` managed by the coordinator.
10. **Can `@PreDestroy` completely replace `SmartLifecycle`?** Not in all cases: `@PreDestroy` belongs to bean destruction; `SmartLifecycle` also controls auto-start, phases, stopping, and completion signaling.

When tracking startup and shutdown, separate the three paths: **bean initialization**, **start/stop coordinated by `LifecycleProcessor`**, and **bean destruction**. `refresh()` concludes by auto-starting eligible `SmartLifecycle` components; `close()` publishes the close event, coordinates ordered stopping, and only then destroys singletons. Understanding these boundaries helps you design more reliable consumers, background tasks, and shutdown behavior.

### References

- Spring Framework 6.1 — `LifecycleProcessor` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/LifecycleProcessor.html
- Spring Framework 6.1 — `SmartLifecycle` API (phase, auto-start, callback): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor` API (onRefresh/onClose, timeout): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — `AbstractApplicationContext` API (`finishRefresh`, `doClose`): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot Gradle — Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
