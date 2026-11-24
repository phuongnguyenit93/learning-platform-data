# ContextStartedEvent in the Spring ApplicationContext Lifecycle

## 1. What is ContextStartedEvent?

`ContextStartedEvent` is a **built-in lifecycle event of the Spring Framework**, belonging to the `org.springframework.context.event` package. It is published when a `ConfigurableApplicationContext` is **explicitly started** via `start()`.

For example:

```java
ConfigurableApplicationContext context = ...;
context.start(); // Spring controls Lifecycle beans, then publishes ContextStartedEvent.
```

The snippet above only illustrates the API; a standalone runnable Java example is in section 5.

The meaning of the word "started" here is very specific: the context sends a **start signal** to beans participating in the `Lifecycle` contract. The event does not mean "the JVM just started", "Spring Boot is ready to receive requests", or "all beans were just initialized for the first time".

Most important point:

> **Merely initializing/refreshing a context does not automatically publish `ContextStartedEvent`.** In normal usage, this event is tied to a `context.start()` call, not to a `refresh()` call or to Spring Boot starting up an application on its own.

`ContextStartedEvent` is appropriate when an application has a **start / stop / restart** workflow for components managed via `Lifecycle` and needs a signal after the start step to trigger coordination, observe state, or record activity.

## 2. Placing ContextStartedEvent in the lifecycle picture

Spring Framework has these common context lifecycle events:

| Event | Typical emission source | Meaning |
| --- | --- | --- |
| `ContextRefreshedEvent` | Context is initialized or finishes `refresh()` | Bean factory, singletons, and context infrastructure are ready after refresh |
| **`ContextStartedEvent`** | Calling `ConfigurableApplicationContext.start()` | Context has executed the start step for relevant `Lifecycle` beans |
| `ContextStoppedEvent` | Calling `ConfigurableApplicationContext.stop()` | Context has executed the stop step for relevant `Lifecycle` beans |
| `ContextClosedEvent` | Calling `close()` or a shutdown hook leading to closing the context | Context is being closed; beans will be destroyed according to the close procedure |

An *intentional* sequence of operations might be:

```text
new AnnotationConfigApplicationContext(Config.class)
                  |
                  v
              refresh()
                  |
                  v
        ContextRefreshedEvent
                  |
                  | context.start()
                  v
        Lifecycle beans: start()
                  |
                  v
         ContextStartedEvent
                  |
                  | context.stop()
                  v
         Lifecycle beans: stop()
                  |
                  v
         ContextStoppedEvent
                  |
                  | context.start()
                  v
        Lifecycle beans: start()
                  |
                  v
         ContextStartedEvent
                  |
                  | context.close()
                  v
         ContextClosedEvent
                  |
                  v
         close/destroy context beans
```

This is a **diagram of explicit calls**, not a mandatory sequence for every Spring application. An application that only calls `refresh()` and then `close()` may never see `ContextStartedEvent`. Having `close()` stop still-running components is part of the context closing procedure; it is **not equivalent** to proactively calling `stop()` to publish a `ContextStoppedEvent` while keeping the context active.

### Distinguishing start, stop, and close

- `start()`: sends the start signal to eligible `Lifecycle` beans; the context remains active and can be `stop()`-ed later.
- `stop()`: sends the stop signal, but **does not destroy singleton beans** and can normally be `start()`-ed again.
- `close()`: ends the context lifecycle, releasing/destroying beans; do not use `start()` to revive a closed context.

Therefore, "stopped" does not mean "the entire Spring container has shut down"; whereas "closed" is the end-of-lifecycle state.

## 3. How does Spring create and publish ContextStartedEvent?

`ContextStartedEvent` extends `ApplicationContextEvent`, which extends `ApplicationEvent`. It holds the source as the started `ApplicationContext`:

```java
import org.springframework.context.event.ContextStartedEvent;

ContextStartedEvent event = ...;
var startedContext = event.getApplicationContext();
long eventTimestamp = event.getTimestamp();
```

This is an illustrative snippet about event data, not a standalone runnable program. `getApplicationContext()` helps identify the context that published the event, which is especially useful in applications with parent/child contexts.

In standard context implementations based on `AbstractApplicationContext`, the flow is understood as:

1. The application calls `ConfigurableApplicationContext.start()`.
2. The context asks `LifecycleProcessor.start()` to coordinate `Lifecycle` beans.
3. After the start step completes normally, the context publishes `new ContextStartedEvent(this)` via the application event mechanism.
4. Any `ApplicationListener<ContextStartedEvent>` or `@EventListener` method accepting the matching event type is notified.

`Lifecycle` beans are managed according to phase rules, dependencies, and the `isRunning()` state of the corresponding `LifecycleProcessor`. Do not assume "every Spring bean" has a start method called: only beans participating in the lifecycle contract have start/stop semantics at this step.

If a `Lifecycle.start()` throws an error preventing the start call from completing, **do not assume by default** that `ContextStartedEvent` was published. Conversely, if a `ContextStartedEvent` listener throws an error in synchronous mode, `start()` may throw an exception **after** some beans have already started running. Both types of failure must be monitored.

### The event is not generated automatically just by declaring a listener

The following snippet **does not** force Spring to publish the event when the application boots:

```java
@EventListener
public void afterStarted(ContextStartedEvent event) {
    System.out.println("Context explicitly started");
}
```

The method is only called if the context actually publishes `ContextStartedEvent`. Placing the annotation alone does not trigger an extra `start()` call.

## 4. How do Lifecycle and SmartLifecycle differ?

To understand when `ContextStartedEvent` is needed, you must distinguish between the two bean lifecycle contracts.

### 4.1. Lifecycle

`org.springframework.context.Lifecycle` declares:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

The snippet above describes the API contract. Beans implementing regular `Lifecycle` receive start/stop when the context is explicitly controlled. When `start()` is called, the bean should enter a "running" state and report `isRunning() == true`; when `stop()` succeeds, switch back to false.

Methods should be **idempotent in effect**: receiving a start command when already running or stop when already stopped should not accidentally open extra resources, create two duplicate consumers, or throw an error simply because the state is already right.

### 4.2. SmartLifecycle

`org.springframework.context.SmartLifecycle` extends `Lifecycle`, adding features such as:

- `isAutoStartup()`: whether to start automatically during `refresh()`.
- `getPhase()`: relative phase/priority during start/stop.
- `stop(Runnable callback)`: asynchronous stop coordination mechanism; implementations must invoke the callback when done so the container does not wait needlessly.

**Key difference:** A `SmartLifecycle` with `isAutoStartup() == true` can be triggered during the **refresh step**, before `ContextRefreshedEvent`, via the lifecycle processor. This auto-start **does not turn refresh into a `ConfigurableApplicationContext.start()` call**, so by itself it does not publish `ContextStartedEvent`.

When the application later calls `context.start()` explicitly, `ContextStartedEvent` can still be published; already-running beans are skipped or handled according to their state by the coordinator. The event represents the **context's start operation**, not proof that a specific bean just transitioned from stopped to running.

| Case | Can the bean run? | Is there a ContextStartedEvent from that operation alone? |
| --- | --- | --- |
| `refresh()`, regular `Lifecycle` bean | Usually not started by lifecycle processor | **No** |
| `refresh()`, `SmartLifecycle.isAutoStartup() == true` | Yes, if start succeeds | **No** |
| `context.start()` | `Lifecycle` beans are asked to start | **Yes**, if the operation completes normally |
| `context.stop()` | `Lifecycle` beans are asked to stop | **No**; there is `ContextStoppedEvent` |
| `context.close()` | Context resources are closed/destroyed | **No**; there is `ContextClosedEvent` |

When the goal is to run a consumer or an adapter right during container initialization, an appropriate `SmartLifecycle` can be used. When the goal is to **observe an explicit start operation**, use `ContextStartedEvent`.

## 5. Runnable Java 17+ example: refresh, start, stop, start again

This example uses **Spring Framework 6.2.12**, Maven, and Java 17+. A `WorkerService` bean implements `Lifecycle`; another bean listens to lifecycle events. The program explicitly calls `start()` then `stop()` twice to show that the event does not happen only once in an application's lifetime.

Project structure:

```text
context-started-demo/
├── pom.xml
└── src/main/java/demo/ContextStartedDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-started-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
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
                    <mainClass>demo.ContextStartedDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ContextStartedDemo.java`:

```java
package demo;

import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;
import org.springframework.context.event.EventListener;

public class ContextStartedDemo {

    public static class WorkerService implements Lifecycle {
        private boolean running;

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("WORKER START");
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("WORKER STOP");
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }
    }

    public static class LifecycleEvents {
        private final WorkerService worker;

        public LifecycleEvents(WorkerService worker) {
            this.worker = worker;
        }

        @EventListener
        public void onRefresh(ContextRefreshedEvent event) {
            System.out.println("EVENT REFRESHED");
        }

        @EventListener
        public void onStart(ContextStartedEvent event) {
            System.out.println("EVENT STARTED running=" + worker.isRunning());
        }

        @EventListener
        public void onStop(ContextStoppedEvent event) {
            System.out.println("EVENT STOPPED running=" + worker.isRunning());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public WorkerService workerService() {
            return new WorkerService();
        }

        @Bean
        public LifecycleEvents lifecycleEvents(WorkerService worker) {
            return new LifecycleEvents(worker);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            context.start();
            context.stop();
            context.start();
            context.stop();
        }
    }
}
```

From the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java
```

Output from the program's `System.out.println` statements (excluding environment-dependent internal logs):

```text
EVENT REFRESHED
WORKER START
EVENT STARTED running=true
WORKER STOP
EVENT STOPPED running=false
WORKER START
EVENT STARTED running=true
WORKER STOP
EVENT STOPPED running=false
```

Stage-by-stage explanation:

1. The constructor `new AnnotationConfigApplicationContext(Config.class)` registers the configuration and then calls `refresh()`. The `@EventListener` listeners are registered in time to receive `ContextRefreshedEvent`. `WorkerService` is only a regular `Lifecycle`, not an auto-starting `SmartLifecycle`, so `WORKER START` is not printed yet.
2. `context.start()` invokes the lifecycle processor. `WorkerService.start()` switches `running` to true and prints `WORKER START`. Afterward `ContextStartedEvent` is published; the listener observes `running=true`.
3. `context.stop()` stops the bean, then publishes `ContextStoppedEvent`. The listener sees `running=false`. The bean has not been destroyed.
4. Repeating `start()`/`stop()` produces another pair of events and log lines; this proves the event is tied to **start/stop operations**, not an event published strictly once in a lifetime.
5. `try-with-resources` calls `close()` upon finishing. Because in the example the bean was already stopped, closing does not print an extra `WORKER STOP`. The program does not register a listener for `ContextClosedEvent`.

The output above assumes the default **synchronous** multicaster as configured in the example. If an application configures an asynchronous executor, the timing order of listener log prints may change.

## 6. Two ways to listen for ContextStartedEvent

### Approach 1: @EventListener

This is usually the most readable approach in Spring beans:

```java
@Component
public class ContextStartObserver {
    @EventListener
    public void onContextStarted(ContextStartedEvent event) {
        System.out.println(
                "Started context: " + event.getApplicationContext().getId());
    }
}
```

This snippet is meant to be placed in a Spring project with component scanning; you need to import `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener`, and `ContextStartedEvent`.

Advantage: no need to implement a listener interface; a single bean can contain multiple `@EventListener` methods for different events.

### Approach 2: ApplicationListener<ContextStartedEvent>

```java
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextStartedEvent;

public final class ContextStartAudit
        implements ApplicationListener<ContextStartedEvent> {

    @Override
    public void onApplicationEvent(ContextStartedEvent event) {
        System.out.println(
                "Started context: " + event.getApplicationContext().getId());
    }
}
```

This is a syntactically standalone class, but it must be **registered as a bean or listener in the ApplicationContext** for Spring to invoke it. For example, declare a `@Bean` returning `ContextStartAudit`, or register an `ApplicationListener` with the appropriate context before the event is published.

| Criterion | `@EventListener` | `ApplicationListener<ContextStartedEvent>` |
| --- | --- | --- |
| Declaration style | Annotation on a bean method | Generic interface on a class |
| Event type | Inferred from method parameter | Specified in the generic type |
| Multiple handlers in one bean | Convenient | Requires considering multiple interfaces/delegation |
| Suitable use cases | Application services, audits, observers | Pure listener classes, programmatic or infrastructure registration |

Both approaches rely on the **same Spring Application Events mechanism**. There is no need to manually call `publishEvent(new ContextStartedEvent(...))` to simulate the real lifecycle; manually publishing the event only sends the notification and **does not run `LifecycleProcessor.start()`**.

## 7. ContextStartedEvent is not the "Spring Boot application is ready" event

This is one of the most common points of confusion.

In Spring Boot, there is a similarly named type:

`org.springframework.boot.context.event.ApplicationStartedEvent`

It is published by **Spring Boot** during `SpringApplication.run(...)`, after the application context has refreshed but before `ApplicationRunner` and `CommandLineRunner` run. `ApplicationReadyEvent` is a later milestone, after the runners, signaling that the application is ready to serve according to the Boot startup process.

Three distinct meanings:

| Signal | Belongs to | When it typically occurs | Used for |
| --- | --- | --- | --- |
| `ContextStartedEvent` | Spring Framework | Explicit call to `ConfigurableApplicationContext.start()` | Observing start/restart of Lifecycle beans |
| `ApplicationStartedEvent` | Spring Boot | After refresh, before runners | Observing the Boot startup stage |
| `ApplicationReadyEvent` | Spring Boot | After runners, end of Boot startup flow | Work requiring the application to be ready |

**You cannot substitute one type for another.** They are different classes with different publishing conditions.

For example, if you want to log when a Spring Boot application is ready:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;

@EventListener
public void ready(ApplicationReadyEvent event) {
    // Perform lightweight work appropriate for the Boot ready milestone.
}
```

This is only a method snippet to place inside a Spring bean of a **Spring Boot** application; it does not run standalone with `spring-context` as in the example in section 5.

If you register `@EventListener(ContextStartedEvent.class)` in a Boot application but nothing calls `context.start()`, do not expect the listener to run when Boot finishes starting up.

## 8. When should you use ContextStartedEvent?

### 8.1. Observing an intentional start cycle

An application might allow pausing and resuming data ingestion by controlling `Lifecycle` beans. If you need to record logs/metrics after every context start, a `ContextStartedEvent` listener is a reasonable choice.

### 8.2. Coordinating components after the start step

Suppose several components participate in `LifecycleProcessor`. After start completes, an observer can record "the context has received and completed the start command" to update operational state or emit internal monitoring signals.

However, if you must **guarantee another bean is actually ready to process requests**, a generic event is not enough. Check the actual health/readiness of the bean or model appropriate dependencies and `SmartLifecycle` phases.

### 8.3. Counting restart occurrences

Because a context can be stopped and restarted, a listener can count how many times `ContextStartedEvent` is received. Distinguish between **calling start** and **a worker actually changing state**: a context start does not mean every bean changed state.

### 8.4. When not to use it

Do not use `ContextStartedEvent` as a default replacement for:

- Initializing data after the bean factory is ready: consider `ContextRefreshedEvent` and appropriate initialization mechanisms.
- Tasks that need to run when Spring Boot is ready: consider `ApplicationReadyEvent`.
- Starting/stopping resources tied to a bean: prefer implementing `Lifecycle` / `SmartLifecycle` or appropriate init/destroy callbacks.
- Strictly executing work once only: the event can appear multiple times when the context is started multiple times; an explicit idempotency marker is required.
- Controlling a multi-instance system or one with process restarts: the event exists only within the scope of one process's application context, not as a durable coordination message.

## 9. Parent/child context lifecycles and filtering events by the right source

In applications with a **parent/child ApplicationContext**, an event from a child context can propagate to a listener in the parent context. Thus, a listener in the parent may see a `ContextStartedEvent` whose source is the **child context**, even if a code reader assumes the listener only cares about the parent context.

Use `event.getApplicationContext()` to check the source when needed:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.EventListener;

public class LocalContextObserver {

    private final ApplicationContext ownContext;

    public LocalContextObserver(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onStarted(ContextStartedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return; // Event from another context, such as a child context.
        }
        // Handle only the context this bean belongs to.
    }
}
```

The snippet above is an illustrative pattern; `LocalContextObserver` must be registered as a bean and supplied with the exact `ownContext` containing the bean. If a context has multiple observers or context names can easily collide, object reference comparison as in the example is more reliable than comparing the `getId()` string alone.

Event propagation in a hierarchy does not mean Spring will automatically start/stop the parent context when starting/stopping a child context. Each context's lifecycle must be managed according to the system in use.

## 10. Error handling and asynchronicity when receiving ContextStartedEvent

### 10.1. Synchronous is the usual default

With the default `SimpleApplicationEventMulticaster`, listeners usually run synchronously on the thread calling `start()`. If a listener throws a `RuntimeException` and the multicaster has no error-handling mechanism to suppress it, the exception can propagate out of `start()`.

This situation is delicate because the `LifecycleProcessor.start()` step may have already started beans before the listener failed. Do not treat an exception from a listener as a guarantee that the container automatically rolled back everything it just started.

Handling guidelines:

1. Only perform lightweight, time-bounded work in lifecycle listeners.
2. For recoverable errors, record logs/metrics with appropriate correlation.
3. If the listener is an essential step for components to run safely, design that work into the start/dependency contract itself or an explicit orchestration workflow.
4. Do not arbitrarily suppress errors to hide an inaccurate readiness state.

### 10.2. Async listeners behave differently

Spring can use an executor in the multicaster or `@Async` to process certain listeners asynchronously. In that case:

- `ContextStartedEvent` is still published by the start operation, but the time the **listener completes** may come after `context.start()` returns.
- Do not read a log saying "event was published" as proof that all async tasks inside the listener have finished.
- Errors in async tasks may not propagate back to the caller in the same way as synchronous listeners.
- Passing the context in the event does not automatically carry the publisher thread's transaction/security/MDC context to the new thread.

If an observer requires strict synchronization with start, evaluate whether asynchronicity is appropriate, or build a barrier/await with a timeout according to real needs.

### 10.3. No automatic transaction semantics attached

`ContextStartedEvent` is not an automatic post-commit `@TransactionalEventListener`. It belongs to the Spring context lifecycle; receiving the event does not prove a transaction just committed. If the listener logic writes to a database, transactions must be managed where that work occurs.

## 11. SmartLifecycle is more suitable when resource control is needed

When the requirement is to open or close a message consumer, scheduler, socket, or long-lived connection, use `Lifecycle`/`SmartLifecycle` to manage the **resource**, and `ContextStartedEvent` to observe the **context lifecycle milestone**.

A condensed `SmartLifecycle` pattern:

```java
import org.springframework.context.SmartLifecycle;

public final class MessageConsumerLifecycle implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        if (!running) {
            // Open the consumer in the way appropriate for the application.
            running = true;
        }
    }

    @Override
    public void stop() {
        running = false;
        // Stop the consumer in the way appropriate for the application.
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run(); // Notify the lifecycle processor that completion occurred.
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
        return 0;
    }
}
```

This is an **illustrative implementation pattern**; comments mark where to open/stop the consumer, without integrating a real broker. When async stop is needed, call `callback.run()` only after the stop task has completed; the example above assumes synchronous stop. A real implementation must guard state, handle timeouts, exceptions, and concurrent start/stop commands.

Important note: With `isAutoStartup() == true`, Spring may call `start()` during refresh. In that case `MessageConsumerLifecycle` is already running yet **no `ContextStartedEvent` has occurred at all**. Using `ContextStartedEvent` to infer whether the consumer is active will be wrong in this case. To know, query `isRunning()` or the consumer's health.

## 12. Designing safe and testable listeners

### 12.1. Do not assume the event is published only once

Any place calling `context.start()` can lead to another event. If a listener creates a job, registers a resource, or sends a notification, duplication must be controlled:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.EventListener;

public class OncePerContextObserver {
    private final AtomicBoolean completed = new AtomicBoolean();

    @EventListener
    public void onStarted(ContextStartedEvent event) {
        if (!completed.compareAndSet(false, true)) {
            return;
        }
        // Work intended to be attempted only once in this bean's lifecycle.
    }
}
```

This is an illustrative snippet for a **run-once flag within a single bean instance**, not an exactly-once guarantee across multiple processes. If the work can fail and needs retry, flipping the flag before completion must also be redesigned. Especially do not use this flag if the real requirement is to execute **on every restart**.

### 12.2. Some important test cases

| Scenario | Operation | What to verify |
| --- | --- | --- |
| Refresh only | Create `AnnotationConfigApplicationContext(Config.class)` | Receives `ContextRefreshedEvent` but **not yet** `ContextStartedEvent` |
| First start | `context.start()` | `Lifecycle.start()` is called and `ContextStartedEvent` is received |
| Stop | `context.stop()` | `Lifecycle.stop()` is called, `ContextStoppedEvent` is received |
| Start after stop | `context.start()` again | A new `ContextStartedEvent` occurs |
| Close | `context.close()` | Receives `ContextClosedEvent` if registered; context lifecycle has ended |
| SmartLifecycle auto startup | `refresh()` with an autoStartup bean | Bean can be running without `ContextStartedEvent` |
| Listener throws exception | Using default synchronous multicaster | Verify whether the exception propagates out of `start()` and what state running beans are in |
| Parent/child contexts | Start child context separately | Parent listener may see child-sourced event; filter using `getApplicationContext()` |

### 12.3. Testing with a plain ApplicationContext

In tests, keep a recorder that can count events rather than asserting only a log line. A recorder for `ContextStartedEvent` can be written as follows:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextStartedEvent;

public final class StartRecorder
        implements ApplicationListener<ContextStartedEvent> {

    private final AtomicInteger count = new AtomicInteger();

    @Override
    public void onApplicationEvent(ContextStartedEvent event) {
        count.incrementAndGet();
    }

    public int count() {
        return count.get();
    }
}
```

This snippet is a test helper class; it must be registered as a listener/bean before starting the context. With a synchronous multicaster, an appropriate check is:

```java
// Assumes recorder was already registered in the context beforehand.
context.start();
assertEquals(1, recorder.count()); // Illustrative JUnit assertion.
context.stop();
context.start();
assertEquals(2, recorder.count());
```

The two `assertEquals` lines only illustrate a JUnit test and are not part of the standalone runnable program in section 5. If the multicaster is configured asynchronously, use a bounded wait mechanism instead of assuming the event has been processed by the listener immediately when `start()` returns.

## 13. Common mistakes

1. **Listening to ContextStartedEvent to know when Spring Boot has finished starting.** Boot has its own lifecycle events; this kind of listener typically does not run unless `context.start()` is called.
2. **Confusing refresh with start.** `ContextRefreshedEvent` can occur when creating a context; `ContextStartedEvent` requires an explicit start operation.
3. **Seeing SmartLifecycle run without seeing ContextStartedEvent and thinking Spring has a bug.** SmartLifecycle auto startup during refresh is a different flow.
4. **Using ContextStartedEvent to start the core component itself.** Start/stop should usually go into `Lifecycle`/`SmartLifecycle`, letting the lifecycle processor coordinate the proper order.
5. **Not protecting against repeated events.** Stop then start can lead to additional events; the listener must decide whether to run every time or only once.
6. **Confusing stop with close.** `stop()` allows restarting; `close()` destroys the context and ends the lifecycle.
7. **Not distinguishing parent/child contexts.** A parent listener can see events from the child; if handling per specific context is needed, use the event's source.
8. **Assuming ContextStartedEvent guarantees all external services are healthy.** A Lifecycle bean can set running=true before downstream is truly ready; separate readiness checks are required.
9. **Swallowing listener errors during a start operation.** This can create an inconsistent state between bean execution and observation/auxiliary parts.
10. **Assuming internal events have retries and durable storage.** Spring Application Events are not a message broker; restarting the JVM loses in-memory state.
11. **Manually creating a ContextStartedEvent to "start the context".** Manually publishing only sends a notification; it does not call `Lifecycle.start()` on beans.
12. **Assuming the onStart callback always runs on the publisher thread.** This holds under the default synchronous multicaster, but must be checked when configuring an executor or `@Async`.

## 14. Checklist for choosing the right lifecycle tool

Before using `ContextStartedEvent`, answer:

- Is what I want to know really whether **`start()` was just called on the context**?
- Or do I want to know that the bean factory just refreshed, or that Spring Boot is ready?
- Should the component needing start/stop control implement `Lifecycle` or `SmartLifecycle` itself?
- Should the listener run on every restart, or only once per instance?
- Does the system have parent/child contexts requiring filtering via `event.getApplicationContext()`?
- Does the listener have heavy work that must avoid blocking `start()`? If async, do results need to be awaited?
- Is the event only for observation, or is it being used as a business transaction guarantee mechanism?
- Have `refresh -> start -> stop -> start -> close` and listener failure cases been tested?

**Practical conclusion:** `ContextStartedEvent` is the signal **after an explicit start call on a Spring ApplicationContext**. Use it to monitor or coordinate with intentional start/stop operations. When the need is to auto-start a bean, control resources, or confirm a Boot application is ready, choose the right `SmartLifecycle`, `ContextRefreshedEvent`, or corresponding Boot event contract.

## References

- [Spring Framework Reference — Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Customizing the Nature of a Bean (Lifecycle and SmartLifecycle)](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [ContextStartedEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/context/event/ContextStartedEvent.html)
- [AbstractApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [Spring Boot ApplicationStartedEvent Javadoc](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
