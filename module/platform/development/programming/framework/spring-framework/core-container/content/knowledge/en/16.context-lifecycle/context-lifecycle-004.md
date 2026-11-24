# Lifecycle for Components Requiring Active Start and Stop in Spring Core Container

## 1. The problem: finishing bean initialization does not mean the component is running

A Spring bean can be created successfully, have all dependencies injected, and finish its initialization callback while still **not permitted to start working**. This applies to message consumers, polling workers, internal schedulers, stream listeners, queue processors, embedded auxiliary servers, or services maintaining long-lived connections.

For example, a worker receiving messages has three distinct operational states:

1. **Created and configured:** already has client, endpoint, credentials, and runtime parameters.
2. **Running:** has started receiving messages or running the polling loop.
3. **Stopped:** stops accepting new work, with in-flight tasks stopped/completed per policy.

Putting all of this logic inside a constructor or `@PostConstruct` makes controlling start/stop via the application context unclear. Spring Core Container provides the `org.springframework.context.Lifecycle` protocol so beans expose state and **active start/stop** operations. When auto-startup on context refresh, phase-based ordering, or asynchronous shutdown is needed, Spring provides `SmartLifecycle`.

After this lesson, you will be able to:

- Write a bean that accurately implements `Lifecycle.start()`, `stop()`, and `isRunning()`.
- Distinguish `context.refresh()`, `context.start()`, `context.stop()`, and `context.close()`.
- Understand `SmartLifecycle`, `isAutoStartup()`, `getPhase()`, and `stop(Runnable callback)`.
- Choose between active start/stop, auto-startup on refresh, and destruction callbacks.
- Coordinate ordering across interdependent components, avoiding wrong-order stopping or blocking shutdown.
- Run a Java 17 + Spring Framework 6.2 program to observe lifecycle execution and deterministic stdout results.

The scope is the `ApplicationContext` lifecycle in Spring Framework Core Container. It does not assume the application must use Spring Boot, Web MVC, or a message broker system.

## 2. The `Lifecycle` interface

The interface belongs to package `org.springframework.context`:

~~~java
package org.springframework.context;

public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

This is an **illustrative API contract signature**; you do not need to create source for the interface yourself as it is included in the Spring library.

The three methods have distinct meanings:

| Method | Meaning | Contract to implement |
| --- | --- | --- |
| `start()` | Transition component to running state, begin active operation | Safe if called again while already running; report running only when startup succeeds |
| `stop()` | Instruct component to stop operating | Stop accepting new work, release operational resources appropriately; safe if called again |
| `isRunning()` | Report whether component is currently active | Reflect **actual state**, not merely that the bean's constructor was called |

**A bean implementing `Lifecycle` is not automatically started by Spring merely because the bean was created.** For plain `Lifecycle`, the container by default does not auto-start it at refresh time; `context.start()` or an appropriate orchestration flow can be called. This is how it differs from `SmartLifecycle`.

### How does Lifecycle differ from bean initialization?

- Constructor, dependency injection, `@PostConstruct`, or `InitializingBean.afterPropertiesSet()` serve to **prepare the bean**.
- `Lifecycle.start()` serves to **begin running**, which can occur after initialization and be invoked again after a stop.
- `Lifecycle.stop()` serves to **stop running**, not necessarily synonymous with destroying the bean or closing the context.
- `@PreDestroy` and custom destroy methods serve to **end the bean's lifecycle**, typically when the context closes for singletons.

Therefore, a bean can have finished `@PostConstruct` while `isRunning() == false`.

## 3. Minimal `Lifecycle` example for a worker

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.Lifecycle;

public final class PollingWorker implements Lifecycle {
    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("worker started");
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("worker stopped");
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }
}
~~~

This class **compiles when `spring-context` is on the classpath**, though it only flips state for illustration; a real worker must register listeners or control its corresponding executor. `AtomicBoolean` helps the example read/write state safely across threads, but by itself it is **insufficient** for managing lifecycles of multiple resources, handling in-flight tasks, or handling startup failures.

If created with `new PollingWorker()` and `start()` is called manually, it is just a Java object. For Spring to orchestrate it, register the class as a bean via `@Component` or `@Bean`.

A design principle: `start()` and `stop()` should be **state-idempotent**. Calling `start()` when the component is already running must not open another identical listener; calling `stop()` twice must not dangerously try to close the same socket again.

## 4. `ApplicationContext` lifecycle and invocation timing

In `ConfigurableApplicationContext`, four actions serve different purposes:

| Action | Purpose | Effect on lifecycle components |
| --- | --- | --- |
| `refresh()` | Build/refresh context, initialize infrastructure and required singletons | `LifecycleProcessor.onRefresh()` can auto-start `SmartLifecycle` beans |
| `start()` | Send start signal to `Lifecycle` beans via the lifecycle processor | Starts not-yet-running components, ordered by phase/dependencies |
| `stop()` | Send stop signal to running components | Stops in organized phase/dependency order; context stays open |
| `close()` | Close context, halt lifecycle components, and destroy managed singletons | Stops still-running components, then runs bean destruction |

### 4.1. Refresh does not mean starting every `Lifecycle` bean

Example:

~~~java
try (var context =
         new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Context is refreshed and getBean() can be used.
    context.start(); // Request Lifecycle beans to start.
    context.stop();  // Request stop; context can still be used.
}
~~~

The snippet above **depends on `AppConfig`** shown in the complete example section. In `AnnotationConfigApplicationContext(AppConfig.class)`, the constructor has already executed `refresh()`. Do not call `refresh()` again on this context as an arbitrary "restart" operation; `GenericApplicationContext`/`AnnotationConfigApplicationContext` typically support only a single refresh.

### 4.2. Stop is not yet close

After `context.stop()`, bean definitions and many singletons still remain; `context.start()` can be called again to start eligible components. When `context.close()` runs, Spring executes shutdown and destroys beans per lifecycle; do not assume a closed context can be restarted.

For a resource-managing component, `stop()` might cancel a subscription or halt a polling loop while keeping configuration for restart; `destroy()`/`@PreDestroy` might close the client or pool permanently. Which design is appropriate depends on resource ownership.

### 4.3. Context also implements `Lifecycle`

`ConfigurableApplicationContext` extends `Lifecycle`; the context's `start()`, `stop()`, and `isRunning()` delegate through `LifecycleProcessor`. Calling `context.start()` **does not** mean Spring recreates all singletons. Bean creation and starting operational components are two distinct phases.

## 5. What does `LifecycleProcessor` do?

Spring uses the `LifecycleProcessor` interface to coordinate the lifecycle of beans registered in the context. The default implementation is typically `DefaultLifecycleProcessor`.

Key roles:

1. Upon refresh completion, invoke `onRefresh()` to decide starting auto-start `SmartLifecycle` beans.
2. When the application calls `context.start()`, start eligible `Lifecycle` beans.
3. When `context.stop()` is called, stop running beans.
4. When the context closes, invoke `onClose()` to stop lifecycle components before destroying beans.
5. Handle ordering via `phase` and bean dependency relationships.

A normal program does not need to create `DefaultLifecycleProcessor` manually. Only configure a custom processor if you genuinely need to alter policies such as shutdown timeout or advanced orchestration behavior.

Important: `LifecycleProcessor` callbacks belong to the **context lifecycle**; bean init/destroy callbacks belong to **a bean instance's lifecycle**. They can relate to one another, yet they do not substitute for each other.

## 6. `SmartLifecycle`: auto-startup and phase-based orchestration

`org.springframework.context.SmartLifecycle` extends both `Lifecycle` and `Phased`. It is meant for components needing:

- Auto-start after context refresh.
- Phase-based startup/shutdown orchestration.
- Reporting completion of asynchronous shutdown via `stop(Runnable callback)`.

Relevant methods:

~~~java
import org.springframework.context.SmartLifecycle;

public final class MessageConsumer implements SmartLifecycle {
    // Must implement start(), stop(), isRunning() and
    // may override isAutoStartup(), getPhase(), stop(Runnable).
}
~~~

This is only an illustrative skeleton; valid implementations of the abstract methods are required for the class to compile.

| Method | Default in `SmartLifecycle` | When commonly overridden |
| --- | --- | --- |
| `isAutoStartup()` | `true` | Want component to run only on explicit start |
| `getPhase()` | `Integer.MAX_VALUE` in Spring 6.2 | Need to establish proper startup/shutdown ordering |
| `stop(Runnable callback)` | Delegates to `stop()`, then invokes callback | Component stops asynchronously and must signal when done |

The default `isAutoStartup() == true` is precisely why a `SmartLifecycle` singleton can run right after `refresh()` without calling `context.start()`.

### 6.1. Phase ordering

With `DefaultLifecycleProcessor`:

- **Start:** **lower phase first, higher phase later**.
- **Stop:** **higher phase first, lower phase later**.
- Plain `Lifecycle` defaults to phase `0` if it does not implement `Phased`.
- `SmartLifecycle` defaults to phase `Integer.MAX_VALUE`, usually starting late and stopping early compared to plain `Lifecycle`.

Conceptual example:

~~~text
START:
phase -100 (Infrastructure) -> phase 0 (Core) -> phase 100 (Consumer)

STOP:
phase 100 (Consumer) -> phase 0 (Core) -> phase -100 (Infrastructure)
~~~

Because the consumer needs infrastructure before accepting work, infrastructure should start first and stop last. However, **declared dependencies between beans can take precedence over phase**; a dependent bean must start after its dependency and stop before its dependency, even if defined phases differ. Do not use phase as the sole way to express real dependency relationships.

### 6.2. `isAutoStartup() == false`

If a `SmartLifecycle` returns `false` from `isAutoStartup()`, the container will not auto-start it at `refresh()` merely due to this interface. The component can be started via `context.start()` or an appropriate explicit operation.

Specifying `@Lazy` **does not guarantee** an auto-start `SmartLifecycle` will avoid initialization during refresh. The lifecycle processor may need to detect and instantiate `SmartLifecycle` beans to decide auto-startup; Spring documentation warns that lazy-init has very limited effect on this category of beans.

## 7. Runnable Java 17 example: active lifecycle and auto-start

The following program uses pure Java Spring Framework 6.2.x, without Spring Boot or servlets. It registers:

- `ManualWorker` implementing `Lifecycle`, starting only when `context.start()` is called.
- `AutoConsumer` implementing `SmartLifecycle`, auto-starting at refresh, phase 100.
- Both components track state using `AtomicBoolean` and log state transitions.
- `AutoConsumer`'s `stop(Runnable)` **always invokes the callback after stopping**.

### 7.1. Project structure

~~~text
spring-lifecycle-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── lifecycle/
                        └── LifecycleDemo.java
~~~

### 7.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-lifecycle-demo</artifactId>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.lifecycle.LifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. `src/main/java/com/example/lifecycle/LifecycleDemo.java`

~~~java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.Lifecycle;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class LifecycleDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            ManualWorker manual = context.getBean(ManualWorker.class);
            AutoConsumer auto = context.getBean(AutoConsumer.class);

            System.out.println("after refresh: manual=" + manual.isRunning()
                    + ", auto=" + auto.isRunning());

            context.start();
            System.out.println("after start: manual=" + manual.isRunning()
                    + ", auto=" + auto.isRunning());

            context.stop();
            System.out.println("after stop: manual=" + manual.isRunning()
                    + ", auto=" + auto.isRunning());

            context.start();
            System.out.println("after restart: manual=" + manual.isRunning()
                    + ", auto=" + auto.isRunning());
        } // close() stops components that are still running.
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        ManualWorker manualWorker() {
            return new ManualWorker();
        }

        @Bean
        AutoConsumer autoConsumer() {
            return new AutoConsumer();
        }
    }

    public static class ManualWorker implements Lifecycle {
        private final AtomicBoolean running = new AtomicBoolean();

        @Override
        public void start() {
            if (running.compareAndSet(false, true)) {
                System.out.println("manual.start");
            }
        }

        @Override
        public void stop() {
            if (running.compareAndSet(true, false)) {
                System.out.println("manual.stop");
            }
        }

        @Override
        public boolean isRunning() {
            return running.get();
        }
    }

    public static class AutoConsumer implements SmartLifecycle {
        private final AtomicBoolean running = new AtomicBoolean();

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 100;
        }

        @Override
        public void start() {
            if (running.compareAndSet(false, true)) {
                System.out.println("auto.start");
            }
        }

        @Override
        public void stop() {
            if (running.compareAndSet(true, false)) {
                System.out.println("auto.stop");
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
            return running.get();
        }
    }
}
~~~

Configuration uses `@Bean` on methods in `Config`; `ManualWorker` and `AutoConsumer` are registered as default singletons. Both nested classes are declared `static`, so they do not depend on an outer instance. The program creates no threads or network connections, so logs are deterministic with no asynchronous race conditions.

### 7.4. Run command and output

Requires JDK 17+ and Maven 3.9+. From the `spring-lifecycle-demo` directory, run:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by `System.out.println` in the program:

~~~text
auto.start
after refresh: manual=false, auto=true
manual.start
after start: manual=true, auto=true
auto.stop
manual.stop
after stop: manual=false, auto=false
manual.start
auto.start
after restart: manual=true, auto=true
auto.stop
manual.stop
~~~

Maven plugins or Spring logging may produce extra log lines depending on configuration; the lines above are solely the explicit output of the example code.

**Why this exact order?**

1. Creating `AnnotationConfigApplicationContext(Config.class)` refreshes the context automatically; `AutoConsumer` auto-starts because `SmartLifecycle.isAutoStartup() == true`. `ManualWorker` is not running yet.
2. `context.start()` sees `ManualWorker` is not running and calls `manual.start`. `AutoConsumer` is already running so it does not start again.
3. `context.stop()` stops running lifecycle beans in descending phase order: auto phase 100 first, manual phase 0 later.
4. The second `context.start()` starts manual phase 0 first, auto phase 100 later.
5. `try-with-resources` closes the context and stops still-running components: auto first, manual later.

This sequence verifies the differences of **refresh vs start**, **stop can restart**, and **`SmartLifecycle` phase**.

### 7.5. Limitations of the example

The example only manages flags to illustrate the contract, not a real worker thread. When production involves multiple threads:

- `start()` must ensure listeners/loops are ready before reporting running.
- `stop()` must stop accepting work and handle in-flight work per policy.
- `stop(Runnable callback)` invokes the callback only **after shutdown is genuinely complete**.
- Races between start and stop must be resolved; a standalone `AtomicBoolean` does not manage STARTING, STOPPING, FAILED states and partially initialized resources.
- Do not use an infinite daemon thread as a way of "implementing Lifecycle."

## 8. `stop(Runnable callback)`: coordinating asynchronous shutdown

A `SmartLifecycle` may need to complete a stopping procedure longer than a synchronous call: stop receiving messages, wait for in-flight tasks, close channels, flush buffers. `stop(Runnable callback)` lets the lifecycle processor know **when the component has actually stopped**.

Specifically:

- For `SmartLifecycle`, `DefaultLifecycleProcessor` uses the **`stop(Runnable callback)`** overload; it is not guaranteed to automatically call no-arg `stop()`.
- If you override `stop(Runnable callback)` yourself, you must execute the stop logic or delegate to `stop()`, and then **invoke `callback.run()` when finished stopping**.
- If not overridden, `SmartLifecycle`'s default method delegates to `stop()` and calls the callback right afterward; only suitable when `stop()` finishes synchronously.
- Forgetting the callback can force the lifecycle processor to wait for the phase timeout, slowing shutdown or breaking the desired order.
- Do not invoke the callback **before** resources actually stop, because the next phase could be closed prematurely.

Illustrative example for a class implementing `SmartLifecycle` with its own executor and asynchronous stop:

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            stopAcceptingNewWork();
            awaitInFlightWork();
            releaseResources();
            running.set(false);
        } finally {
            callback.run();
        }
    });
}
~~~

This is an **illustrative snippet inside a class that already defines** the `executor`, `stopAcceptingNewWork()`, `awaitInFlightWork()`, `releaseResources()`, and `running` fields/methods; it is not a standalone Java file. In real usage, ensure the executor running shutdown **is still alive** and has not been shut down before the callback is submitted. You must handle rejected submissions, exceptions thrown during cleanup, timeouts, interrupts, and cases where the component is already stopped.

If shutdown is very complex, design a clear separate state machine and have `stop(Runnable)` coordinate via that state machine. The callback belongs to the contract Spring uses to confirm completion; it must be invoked exactly once on every completion path per policy.

### Safer synchronous stop example for most components

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

This pattern invokes the callback after `stop()` returns or throws an exception. It suits synchronous shutdown, yet if `stop()` fails before genuinely finishing, you must consider how to report error status and clean up; do not treat the callback as proof that infrastructure stopped cleanly in all cases. Applications needing timeouts/recovery must manage explicit failure states.

## 9. Phase and dependency: starting infrastructure before consumers

Suppose there are two components:

- `ConnectionTransport` creates/maintains the communication channel.
- `EventSubscriber` begins subscribing and receiving events on that channel.

If both implement `SmartLifecycle` and transport is needed before consumer, use phases:

~~~java
@Override
public int getPhase() {
    return -100; // ConnectionTransport: start early, stop late.
}
~~~

~~~java
@Override
public int getPhase() {
    return 100; // EventSubscriber: start late, stop early.
}
~~~

These are two illustrative method snippets belonging to **two different classes**. Sequence:

~~~text
Startup:   ConnectionTransport → EventSubscriber
Shutdown:  EventSubscriber → ConnectionTransport
~~~

Besides phase, declare **real dependencies** if the consumer strictly requires the transport, for instance via constructor injection:

~~~java
public EventSubscriber(ConnectionTransport transport) {
    this.transport = transport;
}
~~~

Dependencies known to Spring influence start/stop ordering: the dependent bean starts **after** its dependency and stops **before** its dependency, even when declared phases might conflict. Therefore:

1. Use **constructor injection** to express object dependencies.
2. Use **phase** to coordinate groups of components needing operational ordering.
3. Avoid turning phases into an undocumented "manual numbering" system obscuring who depends on whom.

If you need to guarantee infrastructure is **truly ready** after `start()`, define an explicit readiness/health contract, because a `start()` method that launches asynchronously and returns immediately does not necessarily indicate the transport has connected successfully.

## 10. Distinguishing `Lifecycle` from init and destroy callbacks

| Mechanism | Timing | Can run multiple times in same context? | Purpose |
| --- | --- | --- | --- |
| Constructor / `@Bean` factory method | When bean is created | For prototype: each new instance; for singleton: typically once | Create object, assign dependencies |
| `@PostConstruct` | Initialization of each bean instance | Per number of bean instances created | Post-injection preparation |
| `InitializingBean.afterPropertiesSet()` | Initialization of each bean instance | Per number of instances | Validate/initialize internal state |
| Custom `@Bean(initMethod = "...")` | Initialization of each bean instance | Per number of instances | Call configured init method |
| `Lifecycle.start()` | On start request / lifecycle processor | **Yes**, possible after stop then restart | Begin operation |
| `Lifecycle.stop()` | On stop request / lifecycle processor | **Yes**, per start/stop cycle | Stop operation |
| `@PreDestroy` / destroy method | When instance is actually destroyed by Spring | Typically at end of bean lifetime | End-of-lifecycle cleanup |

A common flawed design calls worker `start()` inside `@PostConstruct` **and** declares the bean as an auto-start `SmartLifecycle`. That can cause the worker to start twice. Instead, init callbacks should only prepare configuration; the lifecycle processor owns when to start.

### Why not use `@PreDestroy` instead of `stop()`?

`@PreDestroy` is solely a cleanup step when the bean is genuinely destroyed. Meanwhile, `context.stop()` does not destroy the context; the application can **restart** the same bean instance. A worker with operational stop/start needs `Lifecycle` so it does not force destroying/recreating the whole bean or context just to pause accepting work.

For prototypes handed to callers, Spring does not track them to invoke destruction callbacks when the context closes; implementing `Lifecycle` on a prototype also does not automatically turn it into a container-orchestrated singleton lifecycle component like common beans. Background components needing context-driven start/stop should generally be designed as appropriate singletons.

## 11. Choosing `Lifecycle` or `SmartLifecycle`?

### 11.1. Use `Lifecycle` when start must occur explicitly

Example needs:

- An application only starts polling when an operator enables the feature.
- A group of workers is started conditionally after the system allocates resources.
- A component wants stop/start support via `context.start()`, `context.stop()` without auto-starting at refresh.

Plain `Lifecycle` is usually sufficient if special phases, auto-start, or asynchronous shutdown callbacks are not required.

### 11.2. Use `SmartLifecycle` when start is part of context startup

Example needs:

- A consumer needs to auto-subscribe when the application context is ready.
- The system must stop consumers before transport or infrastructure.
- Multiple services need phase-based ordering together.
- A component stops asynchronously and wants organized completion reporting.

In these cases, implement `SmartLifecycle` with consistent state, clear phases, and accurate callbacks.

### 11.3. If a resource only needs closing once when the context closes

A singleton connection pool may only need a custom `destroyMethod` or `AutoCloseable.close()`, **not necessarily `Lifecycle`**. Add the start/stop protocol only when the component genuinely has active operational behavior, pause/restart support, or needs coordinated shutdown.

## 12. Lifecycles of threads, executors, and message consumers

### 12.1. Do not start threads in a constructor if lifecycle coordination is required

~~~java
public MessagePoller() {
    // Do not start a worker thread here if you want
    // Spring to control start/stop timing.
}
~~~

This is an illustrative constructor snippet. If a thread starts before the container finishes injection and refresh, the worker might run with unready dependencies. Create/prepare state in constructor/init and start the loop appropriately in `start()`.

### 12.2. Stopping accepting work differs from finishing running work

A consumer may have several steps on stop:

1. Stop polling/subscribing so it **accepts no new work**.
2. Wait for in-flight jobs to complete within a time limit, or proactively cancel per policy.
3. Commit/acknowledge completed work if infrastructure requires it.
4. Close channels, sockets, or resources owned by the component.
5. Update `running` state after actually stopping.
6. If using `SmartLifecycle.stop(Runnable)`, invoke the callback **after finishing**.

`stop()` is not merely setting `running = false` while threads are still using resources. For long-running tasks, handle interrupts, timeouts, and executor shutdown to avoid hanging stops.

### 12.3. Resource ownership

If `EventSubscriber` **borrows** a singleton HTTP client or connection pool from `ConnectionTransport`, the subscriber should generally stop its subscription first and avoid closing the shared pool itself. Transport or the true owner closes the pool in its own lifecycle.

Some shutdown bugs arise because one component closes a shared dependency before another component stops using it. Phases/dependencies and ownership must align to reflect the desired shutdown order.

### 12.4. Thread-safety of running state

If `start()`/`stop()` can be called from multiple threads:

- `volatile boolean` or `AtomicBoolean` helps publish the flag, but **does not make the entire start/stop operation atomic**.
- `synchronized`/locks/state machines may be needed to protect multi-step lifecycles.
- Distinguish `NEW`, `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `FAILED` states when necessary.
- Do not let `isRunning()` return `true` merely because the flag was flipped when listener creation failed.
- Ensure shutdown callbacks are not skipped on error paths.

Using Spring's protocol lets the container orchestrate, but **does not automatically make your implementation thread-safe**.

## 13. Mistake: forgetting to invoke the shutdown callback

This is an anti-pattern for `SmartLifecycle`:

~~~java
@Override
public void stop(Runnable callback) {
    stop();
    // Wrong: callback.run() is not called.
}
~~~

This snippet belongs to a `SmartLifecycle` implementation class, not a standalone file. Spring may wait out the phase shutdown timeout because it never receives the completion signal.

Fix for synchronous shutdown:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

For asynchronous shutdown, invoke the callback **from the actual completion side** rather than immediately after submitting the task. Do not send the callback early to "avoid timeouts": doing so tricks the lifecycle processor into thinking the consumer has stopped and can cause dependent resources to close while still in use.

## 14. Mistake: confusing negative and positive phases

Some developers assign an "important" component a large phase to make it start early. In Spring lifecycle, that does the opposite of the intention:

- `getPhase() = -100`: **start early**, **stop late**.
- `getPhase() = 100`: **start late**, **stop early**.

Phase is not CPU priority or thread priority; it is strictly **lifecycle orchestration order**. Direct dependencies between beans can affect order beyond phase.

Do not use arbitrary unexplained phase numbers. Define domain constants, e.g., `TRANSPORT_PHASE = -100` and `CONSUMER_PHASE = 100`, in the system's own configuration.

## 15. Mistake: `SmartLifecycle` and `@Lazy`

Code:

~~~java
@Bean
@Lazy
SmartLifecycle consumer() {
    return new MyConsumer();
}
~~~

This is an illustration; Spring imports and a `MyConsumer` class implementing `SmartLifecycle` are needed. It is easy to mistakenly assume `@Lazy` guarantees the consumer is never created at startup. However, `DefaultLifecycleProcessor` may need to initialize `SmartLifecycle` beans to auto-start them; Spring documentation notes that the lazy-init flag has very limited effect for this group.

If the goal is **not running at refresh**, consider `isAutoStartup() = false` together with an explicit start policy, rather than just adding `@Lazy`. If the goal is **not creating the bean until genuinely requested**, design an appropriate lifecycle and registration approach, avoiding reliance on auto-start.

## 16. Mistake: calling `start()` manually on an unmanaged bean

~~~java
var worker = new PollingWorker();
worker.start();
~~~

This Java call may work because the interface is public, yet Spring does not know this is a bean for the lifecycle processor to orchestrate, does not inject the worker's dependencies, and does not automatically call `stop()` when the context closes. If container management is needed, register the bean via `@Bean` or component scanning and retrieve it from the context.

Similarly, objects created dynamically outside the container or prototypes handed to callers require explicit lifecycle ownership policies; context shutdown does not track down every live Java object.

## 17. Interaction with Spring Boot

In a Spring Boot application, the context is also a Spring `ApplicationContext`; `SmartLifecycle` can auto-start during refresh. However, **auto-start is not a guarantee that the application is ready to accept all requests or that all startup hooks have run**.

Distinguish:

| Mechanism | Meaning |
| --- | --- |
| `@PostConstruct` | Initialization callback of a bean |
| `SmartLifecycle.start()` | Start via lifecycle processor, usually during refresh |
| `ApplicationRunner` / `CommandLineRunner` | Logic running after the application context is created, part of Spring Boot's startup workflow |
| `ApplicationReadyEvent` | Spring Boot event when the application finishes runners and is about to be considered ready |
| `@PreDestroy` | Destruction callback when a bean is destroyed |

No single hook automatically replaces all the others. A consumer needing to operate right from refresh can use `SmartLifecycle`; one-time work after Boot startup can fit a runner. If operations involve Kubernetes readiness probes or load balancers, consider readiness policies and halting incoming traffic synchronously with shutdown.

In Spring Boot 3.3, web server graceful shutdown configuration has its own lifecycle mechanism. Do not guess the web server's built-in phase or manually stop the server from a lifecycle bean; use framework-supported mechanisms and add application components only when genuinely needed.

## 18. Configuring shutdown phase timeout

`DefaultLifecycleProcessor` allows configuring the shutdown wait time per phase. In Spring 6.2.x, the `setTimeoutPerShutdownPhase(long)` API is available. When a `SmartLifecycle` stops asynchronously without invoking the callback, the lifecycle processor cannot know it finished, and waiting for the timeout can prolong shutdown.

Illustrative configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.DefaultLifecycleProcessor;

@Configuration(proxyBeanMethods = false)
public class LifecycleProcessorConfig {

    @Bean(name = "lifecycleProcessor")
    public DefaultLifecycleProcessor lifecycleProcessor() {
        DefaultLifecycleProcessor processor = new DefaultLifecycleProcessor();
        processor.setTimeoutPerShutdownPhase(10_000);
        return processor;
    }
}
~~~

This is a **standalone example configuration**. Do not add the same bean name if the application already has its own lifecycle processor; the Spring context uses the bean with standard name `lifecycleProcessor` for coordination.

The value `10_000` represents 10,000 ms = 10 seconds per shutdown phase and is a **configuration example**, not a claim about defaults across all Spring versions.

Notes to keep in mind:

1. Shutdown timeout does not automatically kill a thread or forcibly close all resources.
2. Measure actual completion times and set timeouts appropriate for the domain.
3. The callback must still run when stopping finishes, even if asynchronous work must be awaited.
4. Avoid applying an overly long wait time to every phase without observation.
5. On abnormal shutdown or forced JVM kill, lifecycle callbacks cannot be guaranteed to run.

## 19. Testing active lifecycles

The `LifecycleDemo` example checks common flows via stdout. For automated tests, assert state and event order instead of merely grepping logs:

~~~java
try (var context =
         new AnnotationConfigApplicationContext(LifecycleDemo.Config.class)) {

    var manual = context.getBean(LifecycleDemo.ManualWorker.class);
    var auto = context.getBean(LifecycleDemo.AutoConsumer.class);

    if (manual.isRunning()) {
        throw new AssertionError("Manual worker should be stopped after refresh");
    }
    if (!auto.isRunning()) {
        throw new AssertionError("SmartLifecycle should auto-start");
    }

    context.start();
    if (!manual.isRunning()) {
        throw new AssertionError("Manual worker did not start");
    }

    context.stop();
    if (manual.isRunning() || auto.isRunning()) {
        throw new AssertionError("Lifecycle components did not stop");
    }
}
~~~

This is an **auxiliary execution snippet** that can be placed in another `main` method or test with dependencies from section 7. In real test cases, add assertions for idempotency (start when already running, stop when already stopped), phase ordering, failure paths, and asynchronous shutdown callbacks. You do not need to spin up a real server or thread just to test the core lifecycle contract.

### Testing asynchronous stop callbacks

For custom `SmartLifecycle.stop(Runnable)`, design tests with a `CountDownLatch`:

1. Trigger lifecycle stop through the context.
2. When the background task signals completion, invoke the callback.
3. Assert the callback was invoked once.
4. Assert shutdown of the depended-upon phase did not happen before completion.
5. Use a finite timeout so tests do not hang forever when the implementation is buggy.

Note that testing concurrency with long `Thread.sleep(...)` or relying on arbitrary timing easily produces flaky tests. Use latches or more deterministic synchronization mechanisms.

## 20. Common operational issues

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| Implements `Lifecycle` yet component does not run at refresh | Plain `Lifecycle` does not auto-start by default | Call `context.start()` or consider `SmartLifecycle` |
| Implements `SmartLifecycle` yet still does not auto-start | `isAutoStartup() == false` or bean is not managed by context | Check bean registration and auto-start flag |
| Worker starts twice | Calling start in `@PostConstruct` and letting lifecycle processor start | Pick one startup mechanism |
| Shutdown hangs until timeout | `stop(Runnable)` fails to call callback or stop never completes | Always report completion on time; check executor and timeout |
| Consumer stops after transport | Wrong phase or dependency not declared properly | Consumer phase higher than transport; make dependency explicit |
| `@Lazy` consumer still created at refresh | `SmartLifecycle` must be discovered and auto-started by processor | Use `isAutoStartup()`/other design instead of only `@Lazy` |
| Called `context.stop()` yet beans still exist | Stop only halts operations, does not destroy context | Call `close()` when truly ending context lifecycle |
| `isRunning()` true when client not yet connected | Flag does not reflect real readiness | Explicitly manage STARTING/READY/FAILED |
| Stop closes resources while tasks still run | Missing drain/cancel/in-flight tracking | Stop accepting work, wait/cancel properly before cleanup |
| Destroy callback does not run on worker created via `new` | Object is not Spring-managed | Register bean or manage ownership in Java |
| Spring shuts down yet process does not exit | User-created non-daemon thread/executor not stopped | Shut down/interrupt/join properly in lifecycle |
| Lifecycle callback invoked before operational dependencies are ready | Treating `start()` as entire app ready | Define readiness contract and component ordering |

## 21. Design checklist

When defining a component that needs start/stop, answer:

- Does the component have **continuous operational work** needing start/stop, or does it only need initialization and destruction?
- Should it **auto-start on context refresh**? If yes, `SmartLifecycle` is usually appropriate.
- Which phase should it sit at and which components does it depend on?
- Is `start()` idempotent? If startup fails, does state return to a consistent condition?
- Does `stop()` stop accepting new work and complete/cancel in-flight work per policy?
- If using `stop(Runnable)`, is the callback invoked when actually finished?
- Are resources closed in `stop()` or only at destroy, and can the component restart after stop?
- Can lifecycle operations execute concurrently, and is state protected?
- How do you test start/stop/restart, phase ordering, failure, and timeout without relying on incidental logs?
- Is readiness/liveness needed separately from `isRunning()`?

A sound design allows the context to **start → stop → start → close** without leaking resources, without accepting work after stop, and without shutting down dependencies before the component finishes its work.

## 22. Knowledge check questions

**Question 1.** A bean implements `Lifecycle`, is registered as a singleton, and is created by Spring at context refresh. Why can `isRunning()` still be false?

**Answer:** Because bean initialization does not automatically mean lifecycle start. Plain `Lifecycle` does not auto-start at refresh by default. Only `context.start()` or an appropriate start call transitions the component to running.

**Question 2.** A bean implements `SmartLifecycle` returning `isAutoStartup() == true`. When does it typically begin?

**Answer:** When `ApplicationContext` refresh finishes the appropriate stage and `LifecycleProcessor.onRefresh()` orchestrates auto-startup. This does not require the caller to invoke `context.start()` manually.

**Question 3.** Two components A (phase -10) and B (phase 20), with no explicit dependency. What is the usual order?

**Answer:** Start A then B; stop B then A. If a direct dependency exists between the two beans, dependency ordering can take precedence over phase.

**Question 4.** Does `context.stop()` automatically destroy singletons and close the context?

**Answer:** No. It asks lifecycle components to stop while the context remains open. Only `context.close()` performs context shutdown and bean destruction per policy.

**Question 5.** If `SmartLifecycle.stop(Runnable)` finishes stopping without calling `callback.run()`, what is the harm?

**Answer:** The lifecycle processor never receives the completion signal, may have to wait for the phase timeout, and delays shutdown, affecting the stopping order of other components.

**Question 6.** A singleton client only needs `close()` when the application shuts down, with no pause/restart support. Is implementing `Lifecycle` mandatory?

**Answer:** No. A custom `destroyMethod`, `AutoCloseable`, or an appropriate destruction callback can suffice. `Lifecycle` is only useful when active operational behavior is needed.

**Question 7.** Why is `@PostConstruct` unsuitable for directly opening an infinite polling loop?

**Answer:** The initialization callback must finish so the bean/context can initialize properly; an infinite loop will block startup. Prepare configuration at init and start the worker via lifecycle, with clear thread/executor and stop mechanisms.

## 23. Official documentation

- [Spring Framework 6.2 — `Lifecycle` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/Lifecycle.html): `start`, `stop`, and `isRunning` contract.
- [Spring Framework 6.2 — `SmartLifecycle` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html): auto-start, phase, shutdown callback, and interface defaults.
- [Spring Framework 6.2 — `DefaultLifecycleProcessor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): coordinating phases, start/stop, refresh/close, and timeouts.
- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): distinguishing lifecycle callbacks and bean management behavior.
- [Spring Framework — `ConfigurableApplicationContext` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): `refresh`, `start`, `stop`, `close`, and context contract.
