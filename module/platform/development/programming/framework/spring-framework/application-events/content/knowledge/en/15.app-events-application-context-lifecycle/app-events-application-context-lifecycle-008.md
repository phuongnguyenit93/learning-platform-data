# Events When Starting and Stopping `ApplicationContext` in Spring Framework

## 1. Concept: start, stop, refresh, and close are not the same operation

`ApplicationContext` is the IoC container managing beans, dependency injection, and Application Events. A context can be **initialized (`refresh`)**, receive a **start signal (`start`)**, receive a **stop signal (`stop`)**, and then **close and destroy beans (`close`)**. Spring publishes different events for these milestones. Understanding them properly helps you control workers, consumers, schedulers, long-lived connections, and background resources according to the application lifecycle.

In Spring Framework, the two events directly covered by this topic are:

- **`ContextStartedEvent`**: published when `start()` is called on `ConfigurableApplicationContext`. Spring delivers the start signal to eligible `Lifecycle` beans.
- **`ContextStoppedEvent`**: published when `stop()` is called on `ConfigurableApplicationContext`. Spring delivers the stop signal to running `Lifecycle` beans.

These two events **do not** appear by default every time an application starts up or shuts down. `AnnotationConfigApplicationContext` typically calls `refresh()` right inside the constructor used in examples, publishing `ContextRefreshedEvent`, and **does not automatically publish `ContextStartedEvent` merely because it refreshed**. When `close()` is called, Spring publishes **`ContextClosedEvent`** and then handles stopping/destroying beans; **do not assume by default that you will receive `ContextStoppedEvent` when only `close()` is called**.

An important detail: `stop()` does not destroy beans or close the context. After `stop()`, the context can still be `start()`-ed again. Conversely, a `close()`-d context cannot be started/restarted as before; a new context must be created.

## 2. Comparison table of the four lifecycle events

| Event | Common trigger | Primary meaning | Can the context still be used? |
| --- | --- | --- | --- |
| `ContextRefreshedEvent` | `refresh()` / auto-refreshing constructor | Bean definitions processed, context finished initializing or refreshing | Yes |
| `ContextStartedEvent` | `ConfigurableApplicationContext.start()` | Asks `Lifecycle` beans to start or resume running | Yes |
| `ContextStoppedEvent` | `ConfigurableApplicationContext.stop()` | Asks `Lifecycle` beans to stop operating | Yes; can `start()` again |
| `ContextClosedEvent` | `close()` or an appropriate shutdown hook | Context enters closing procedure, stops components, and destroys singletons | No |

These classes reside in the `org.springframework.context.event` package. They extend `ApplicationContextEvent`, allowing the publishing context to be retrieved via `event.getApplicationContext()`.

**Do not equate names:** `ContextStartedEvent` belongs to **Spring Framework**, whereas `ApplicationStartedEvent` belongs to **Spring Boot**. These are two different event types with different publishing conditions and lifecycle positions. A Boot application can receive `ApplicationStartedEvent` without ever calling `applicationContext.start()`.

## 3. Internal processing flow in Spring

With `AbstractApplicationContext` and the default `LifecycleProcessor`, the main flow can be visualized as follows:

```text
Create / refresh context
  ├─ create and initialize beans
  ├─ register ApplicationListener / @EventListener methods
  ├─ LifecycleProcessor.onRefresh()
  │    └─ auto-start SmartLifecycle beans with isAutoStartup() = true
  └─ publish ContextRefreshedEvent

context.start()
  ├─ LifecycleProcessor.start()
  │    └─ start Lifecycle beans that need to run
  └─ publish ContextStartedEvent

context.stop()
  ├─ LifecycleProcessor.stop()
  │    └─ stop running Lifecycle beans
  └─ publish ContextStoppedEvent

context.start()        (can be called again if context is not closed)
  ├─ LifecycleProcessor.start()
  └─ publish ContextStartedEvent

context.close()
  ├─ publish ContextClosedEvent
  ├─ LifecycleProcessor.onClose()
  │    └─ stop still-running Lifecycle beans
  └─ destroy singletons / close container resources
```

This describes the normal path of a single context and several key steps, not the entire implementation. Listener order can be affected by multicaster configuration, listener ordering, bean dependencies, and asynchronous listeners.

`ContextStartedEvent` is published **after the lifecycle start command completes according to the processor's mechanism**; similarly `ContextStoppedEvent` is published after the stop call on the processor. However, if `SmartLifecycle.stop(Runnable callback)` stops asynchronously on its own, you must ensure the completion callback is invoked properly; a listener should not arbitrarily infer that all resources across external systems are completely ready or halted.

## 4. Runnable Java 17+ example: start, stop, restart, close

This example uses **Spring Framework 6.2.12**, Java 17+, and Gradle 8+; no Spring Boot or database is required. A simple `Lifecycle` bean represents a background worker; a listener bean receives all four lifecycle event types.

Structure:

```text
context-lifecycle-events-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ContextLifecycleDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'context-lifecycle-events-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.ContextLifecycleDemo'
}
```

**`src/main/java/demo/ContextLifecycleDemo.java`**

```java
package demo;

import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;
import org.springframework.context.event.EventListener;

public class ContextLifecycleDemo {

    public static class Worker implements Lifecycle {
        private boolean running;

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("worker: start");
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("worker: stop");
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }
    }

    public static class ContextEvents {

        @EventListener
        public void onRefreshed(ContextRefreshedEvent event) {
            System.out.println("event: refreshed");
        }

        @EventListener
        public void onStarted(ContextStartedEvent event) {
            System.out.println("event: started");
        }

        @EventListener
        public void onStopped(ContextStoppedEvent event) {
            System.out.println("event: stopped");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            System.out.println("event: closed");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        Lifecycle worker() {
            return new Worker();
        }

        @Bean
        ContextEvents contextEvents() {
            return new ContextEvents();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            Lifecycle worker = context.getBean("worker", Lifecycle.class);

            System.out.println("after refresh: running=" + worker.isRunning());

            context.start();
            System.out.println("after start: running=" + worker.isRunning());

            context.stop();
            System.out.println("after stop: running=" + worker.isRunning());
            System.out.println("after stop: active=" + context.isActive());

            context.start();
            System.out.println("after restart: running=" + worker.isRunning());

        } // try-with-resources calls context.close().
    }
}
```

Run with JDK 17+ and Gradle installed:

```bash
gradle -q run
```

Lines printed by the program in exact order:

```text
event: refreshed
after refresh: running=false
worker: start
event: started
after start: running=true
worker: stop
event: stopped
after stop: running=false
after stop: active=true
worker: start
event: started
after restart: running=true
event: closed
worker: stop
```

### Why does it have that order?

1. `new AnnotationConfigApplicationContext(AppConfig.class)` automatically registers the configuration and runs `refresh()`; Spring creates `Worker`, registers the `@EventListener` methods, and then publishes `ContextRefreshedEvent`. A bean implementing only regular `Lifecycle` **does not auto-start at refresh**, so `running=false`.
2. `context.start()` asks `LifecycleProcessor.start()` to call `worker.start()` first, and then publishes `ContextStartedEvent`. Hence `worker: start` appears before `event: started`.
3. `context.stop()` calls `worker.stop()` first, and then publishes `ContextStoppedEvent`. `isActive()` remains `true`: the context is not closed, still holds beans, and can operate again.
4. Calling `context.start()` again starts the stopped worker and publishes another `ContextStartedEvent`.
5. Upon exiting `try`, `close()` is invoked. Spring publishes `ContextClosedEvent` and then calls the lifecycle processor to close/stop still-running beans, so `event: closed` precedes `worker: stop`. **There is no new `event: stopped` line caused by the close operation alone.**

This log pattern is reliable with the **default synchronous multicaster** and a single context as in the example. When adding an executor to the event multicaster, threads and handler completion order can change; do not turn log line order into a general contract of an asynchronous system.

`@EventListener` relies on **Spring-managed beans**. If you manually call `new ContextEvents()`, the new object is not registered as a listener of the context. `@EventListener` does not automatically wire objects outside the Spring container.

## 5. `Lifecycle` and `SmartLifecycle`: why do some beans run right at refresh?

### 5.1. Regular `Lifecycle`

The `org.springframework.context.Lifecycle` interface consists of:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

Beans implementing this interface receive `start()` and `stop()` signals from the lifecycle processor. **Regular `Lifecycle` does not auto-start after refresh by default.** This is why `Worker` in the example is stopped right after context creation, and only runs when `context.start()` is called.

`start()`/`stop()` methods should behave safely when invoked repeatedly according to state. The stop signal should normally return once the component has halted; if the stop operation is genuinely asynchronous, look at `SmartLifecycle.stop(Runnable)`.

### 5.2. `SmartLifecycle` supports auto-start and phase ordering

`SmartLifecycle` extends `Lifecycle` and `Phased`:

- `isAutoStartup()` enables auto-starting inside `LifecycleProcessor.onRefresh()`; **the default for `SmartLifecycle` is `true`**.
- `getPhase()` selects startup/shutdown order by phase; **lower phases start first**, **higher phases stop first**. `Lifecycle` is normally treated as phase 0.
- `stop(Runnable callback)` supports asynchronous shutdown per phase. **You must call `callback.run()` when stopped**; if forgotten, the lifecycle processor may have to wait until timeout.
- A `SmartLifecycle` may already be running when `ContextRefreshedEvent` is published, **even though `ContextStartedEvent` has never appeared**.

Illustrative `SmartLifecycle` snippet (not a standalone program, assumed to be placed in a Spring-managed bean):

```java
public final class MessageConsumer implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public boolean isAutoStartup() {
        return true; // auto-start on context refresh
    }

    @Override
    public int getPhase() {
        return 100; // start after phase 0; stop before phase 0
    }

    @Override
    public void start() {
        if (!running) {
            // Start the consumer; this example only illustrates state.
            running = true;
        }
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run(); // signal the lifecycle processor that stop finished
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

You need to import `org.springframework.context.SmartLifecycle`. This is minimal illustrative code; in a real application, call `callback.run()` only when the consumer has **actually stopped**, after closing connections, canceling subscriptions, or waiting for in-flight messages to finish according to policy. If shutting down asynchronously, pass the callback into the branch triggered after resources are released.

**Note:** Do not use `ContextStartedEvent` to infer that every `SmartLifecycle` was just started; many beans auto-started right at context refresh. When stopping a component via `component.stop()` directly, that also **does not automatically cause the context to publish `ContextStoppedEvent`**.

## 6. Choosing `@EventListener` or `ApplicationListener`?

Two common ways to handle lifecycle events are method annotations and interfaces.

### Approach 1: `@EventListener`

```java
@Component
public class ContextStatusObserver {

    @EventListener
    public void onStarted(ContextStartedEvent event) {
        // After context.start() call.
    }

    @EventListener
    public void onStopped(ContextStoppedEvent event) {
        // After context.stop() call.
    }
}
```

This is an illustrative snippet requiring imports for `Component`, `EventListener`, `ContextStartedEvent`, and `ContextStoppedEvent`. The bean must belong to the context with registered listeners; the annotation is processed by Spring when configuring the container.

### Approach 2: `ApplicationListener<T>`

```java
@Component
public class StartedObserver
        implements ApplicationListener<ContextStartedEvent> {

    @Override
    public void onApplicationEvent(ContextStartedEvent event) {
        // Receive typed event from Spring context.
    }
}
```

This is also illustrative code; import `org.springframework.context.ApplicationListener`, `org.springframework.context.event.ContextStartedEvent`, and `org.springframework.stereotype.Component`.

For the main example, `@EventListener` is convenient for placing multiple handlers for specific events in a single bean. `ApplicationListener<T>` is suitable when you want an explicit listener type, easy programmatic registration, or usage in infrastructure parts. Both participate in the context's event multicaster mechanism.

Do not confuse **`ApplicationEventPublisher.publishEvent(...)`** with `start()/stop()`: you can publish a custom event yourself using the publisher, but standard `ContextStartedEvent`/`ContextStoppedEvent` reflect operations executed by the context. **Do not manually `publishEvent(new ContextStartedEvent(context))` to pretend it started**; that does not call `LifecycleProcessor.start()` and can mislead listeners about state.

## 7. `close()` is not `stop()`: differences in resources and reuse

| Aspect | `context.stop()` | `context.close()` |
| --- | --- | --- |
| Standard event | `ContextStoppedEvent` | `ContextClosedEvent` |
| `Lifecycle` bean | Receives stop if running per lifecycle processor | Stopped on shutdown per lifecycle processor, if applicable |
| Singleton | Normally remains in the container | Destroyed during context closing |
| `context.isActive()` | Normally still `true` | `false` after close |
| Can `start()` again? | Yes, if context is still active | No |
| When to use? | Pausing/restarting background components | Ending the container/application lifecycle |

On `close()`, the normal order of `AbstractApplicationContext` is to publish `ContextClosedEvent`, call `LifecycleProcessor.onClose()` to stop lifecycle beans, and then destroy singletons. Consequently, a listener handling `ContextClosedEvent` **should not assume by default that all workers have completely stopped** at the moment the event is received.

Clear cleanup example:

```java
@Component
public class ShutdownObserver {

    @EventListener
    public void onClosing(ContextClosedEvent event) {
        // Stop accepting new requests / log / switch to shutdown state.
        // Do not assume all Lifecycle beans have finished stopping.
    }

    @PreDestroy
    public void onDestroy() {
        // Clean up resources owned by this bean itself before destruction.
    }
}
```

This is illustrative code requiring imports for `ContextClosedEvent`, `EventListener`, `Component`, and `jakarta.annotation.PreDestroy` (on Java 17 the `jakarta.annotation-api` dependency may be needed if the project does not already have it). `@PreDestroy` is a bean destruction callback, not equivalent to context stop; it runs when the bean is destroyed. Do not blindly rely on event listeners to replace all resource management.

When a background resource must be kept safe, place start/stop logic in the resource-owning bean via `Lifecycle` or `SmartLifecycle`; use event listeners for **auxiliary reactions** like logging, telemetry, or state transitions.

## 8. Spring Boot: avoid confusing `ApplicationStartedEvent`

Spring Boot uses `SpringApplication` to run the application and publishes **SpringApplication events** in addition to Spring Framework's standard events. Some meaningful events:

- **`ApplicationStartedEvent` (Spring Boot):** published after `ApplicationContext` has refreshed, before `ApplicationRunner`/`CommandLineRunner` are called.
- **`ApplicationReadyEvent` (Spring Boot):** published when the application has finished runners and is ready to accept work per the Boot lifecycle.
- **`ContextRefreshedEvent` (Spring Framework):** belongs to the context refresh process.
- **`ContextStartedEvent` (Spring Framework):** reflects an explicit `ConfigurableApplicationContext.start()` call; **not** the default way to know Spring Boot just finished starting.
- **`ContextStoppedEvent` (Spring Framework):** reflects an explicit `stop()` call; **not** the standard shutdown event replacing `ContextClosedEvent`.

To run tasks once Boot is ready, typically consider `ApplicationReadyEvent` or `ApplicationRunner` per specific requirements. To manage start/stop of a consumer or worker, prefer `SmartLifecycle`. To know the context is closing, use `ContextClosedEvent` or the corresponding lifecycle shutdown callback.

Do not confuse the word "started" in Spring Boot with the word "started" in Spring Framework. Same word, but different lifecycle, event type, and timing.

## 9. Synchronicity, asynchronicity, and processing order

By default, `SimpleApplicationEventMulticaster` processes listeners **synchronously**, on the event-publishing thread. That is why the example in section 4 has an easily observable log order.

If you attach `@Async` to a listener method, or configure an executor on the multicaster, the handler can run on another thread. Then:

- `context.start()` has sent the start signal to the lifecycle processor, yet an **async listener** receiving `ContextStartedEvent` may not have finished.
- An asynchronous listener receiving `ContextStoppedEvent` may run after another operation or while the application is preparing to close.
- You should not rely on `@EventListener` ordering across multiple threads to decide which worker starts/stops first.
- `@Async` configuration requires enabling `@EnableAsync`, proxies, and an appropriate executor. A multicaster configured with an executor and `@Async` on a listener method are two different mechanisms.
- Exceptions in synchronous listeners can propagate to the event publisher depending on multicaster/error handler; async listeners need their own error-tracking mechanism.

For **resource-dependent** start/stop, use the lifecycle processor, `SmartLifecycle.getPhase()`, `depends-on`, and stop callbacks — do not use a set of asynchronous event listeners to replace that coordination mechanism.

Example of a conditional logging listener:

```java
@EventListener
public void onStarted(ContextStartedEvent event) {
    System.out.println("started context id="
            + event.getApplicationContext().getId());
}
```

This is an illustrative snippet; `getApplicationContext()` returns the source context of the event. In systems with parent/child contexts, child events can propagate up to the parent; a listener in the parent may see multiple events. If you only want to react to one context, check the **source context or ID** carefully instead of assuming there is only one container in the process.

## 10. Testing the application and troubleshooting

### 10.1. Cases to test

1. **Refresh:** create a new context; confirm `ContextRefreshedEvent` is received, regular `Lifecycle` has not auto-started, and `SmartLifecycle` with `isAutoStartup=true` may already be running.
2. **Start:** call `start()`; confirm `Lifecycle.start()` is called and `ContextStartedEvent` is published.
3. **Stop:** call `stop()`; confirm `Lifecycle.stop()` is called and `ContextStoppedEvent` is published; context is not destroyed.
4. **Restart:** call `start()` after `stop()`; confirm beans can restart without retaining invalid old state/resources.
5. **Close:** call `close()`; confirm `ContextClosedEvent`, bean destruction, and resource shutdown; do not assume `ContextStoppedEvent` is counted as well.
6. **Auto-start:** replace `Lifecycle` with `SmartLifecycle`, toggle `isAutoStartup=true/false`; verify the difference right after refresh.
7. **Multiple beans/phases:** check dependent beans start/stop in the right sequence; include timeout/callback for async shutdown.
8. **Async listeners:** await via `CountDownLatch`/future/Awaitility instead of relying on arbitrary sleep, since completion order is not fixed.
9. **Parent/child contexts:** check that listeners do not accidentally handle the same event multiple times due to propagation.

You can test events with a listener bean storing counters, for example:

```java
@EventListener
public void onStarted(ContextStartedEvent event) {
    startedCount.incrementAndGet();
}

@EventListener
public void onStopped(ContextStoppedEvent event) {
    stoppedCount.incrementAndGet();
}
```

This is an illustrative snippet requiring `AtomicInteger startedCount`, `AtomicInteger stoppedCount` fields, and a Spring-managed bean. The test reads the counters after each `context.start()/stop()` call with the default synchronous multicaster, without needing to wait on another thread.

### 10.2. Common mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| No `ContextStartedEvent` seen when app runs | Only created/refreshed context; never called `start()` | Use `ContextRefreshedEvent` or Boot `ApplicationReadyEvent` per need; call `start()` only when lifecycle signal is needed |
| No `ContextStoppedEvent` seen when closing app | Only called `close()`; that is a different lifecycle event | Use `ContextClosedEvent` or `LifecycleProcessor` stop callbacks |
| Worker already running before started event | Bean implements `SmartLifecycle` auto-starting on refresh | Check `isAutoStartup`, `getPhase`, and refresh flow |
| `@EventListener` is not invoked | Handler is not in a Spring bean, wrong event type, or registered too late | Register Spring-managed listener before refresh/start/stop |
| Listening for `ApplicationStartedEvent` but never receiving it | Confused Boot event with Framework event, or running plain context | Check imports/packages and Spring Boot lifecycle |
| Cannot recover worker after `stop()` | Bean does not support restart or resources were unintentionally destroyed | Write re-callable `start()/stop()`; reserve permanent resource destruction for `close()`/destroy |
| Listener receives event twice | Parent/child contexts, multiple listeners, or multiple start/stop calls | Check source context, registrations, and call counts |
| Shutdown drags on | `SmartLifecycle.stop(Runnable)` forgot callback or task did not stop | Complete callback after stop, set timeouts, and monitor resources |
| Event logs arrive late/out of order | Listener uses an executor / `@Async` | Test via synchronization signals, do not assume ordering across worker threads |
| Manually published `ContextStartedEvent` yet worker stays stopped | Publishing the event does not trigger `LifecycleProcessor.start()` | Call `context.start()` or the appropriate lifecycle API |

## 11. Design principles in real projects

- **`ContextStartedEvent` and `ContextStoppedEvent` are events for explicit start/stop operations**, not generic names for startup/shutdown.
- If you need to manage a restartable background service, write `Lifecycle` or `SmartLifecycle`; place resource opening/closing in `start()`, `stop()`, and `stop(Runnable)` as required.
- Use `ContextRefreshedEvent` for situations needing to know the container refreshed, while avoiding heavy tasks that impact startup time; in Boot, the "application ready" event serves a different purpose.
- Use `ContextClosedEvent` to react to the container closing; do not assume every bean has already stopped at the time the event is received.
- If multiple components have start/stop dependencies, declare phase/dependencies via the lifecycle processor rather than organizing order with uncoordinated event listeners.
- Keep listeners synchronous by default; if enabling async, define explicit error, timeout, and shutdown policies.
- With parent/child contexts, always think about the **event source** and the possibility of events forwarding up to the parent.
- If a temporary pause is needed: `stop()` then `start()` again. If ending the lifecycle: `close()` and create a new context when needed.

**Summary:** `ContextStartedEvent` is published by `context.start()`, `ContextStoppedEvent` by `context.stop()`. `refresh()` and `close()` have their own events. `LifecycleProcessor` coordinates lifecycle-aware beans, while event listeners react to milestones that have occurred. Clearly distinguishing these two roles is key to avoiding startup/shutdown bugs in Spring Framework.

## Official references

- [Spring Framework 6.2 — ApplicationContext Events: built-in events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — Startup and Shutdown Callbacks / `Lifecycle`, `SmartLifecycle`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html)
- [Spring Framework — `ConfigurableApplicationContext` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [Spring Framework — `ContextStartedEvent` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ContextStartedEvent.html)
- [Spring Framework — `ContextStoppedEvent` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ContextStoppedEvent.html)
- [Spring Framework — `SmartLifecycle` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/SmartLifecycle.html)
