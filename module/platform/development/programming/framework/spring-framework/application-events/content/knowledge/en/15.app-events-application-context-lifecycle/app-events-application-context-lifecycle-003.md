# ContextStoppedEvent in the Spring Framework ApplicationContext Lifecycle

## 1. What is ContextStoppedEvent?

`ContextStoppedEvent` is a Spring system event, belonging to the `org.springframework.context.event` package. It is published when an `ApplicationContext` receives an **explicit stop command** via `ConfigurableApplicationContext.stop()`. This is a signal about the **context** lifecycle, unlike a business event such as `OrderCreated` or `PaymentSucceeded`.

This class extends `ApplicationContextEvent`, so a listener can call `event.getApplicationContext()` to retrieve the exact context that published the event. The event also carries a timestamp via `ApplicationEvent.getTimestamp()`. You do not need to construct a `ContextStoppedEvent` object manually in the normal path: Spring creates and publishes the event when the `stop()` operation is invoked.

Why is this event useful? An application might want to know that `Lifecycle` components have received the stop signal, for instance to write operational logs, update monitoring state, or finalize information for a run session. However, one fundamental boundary must be clearly understood:

**`stop()` is not equivalent to `close()`.** A stopped context remains active and can be started again. Stopping does not mean all singleton beans have been destroyed or that the JVM has exited.

## 2. Where does ContextStoppedEvent appear in the lifecycle?

With an `ApplicationContext` managed by `AnnotationConfigApplicationContext` or standard `ConfigurableApplicationContext` implementations, you can visualize it as:

```text
new/refresh()
  |
  +-- initialize beans and the ApplicationEvent mechanism
  +-- auto-start eligible SmartLifecycle beans
  +-- publish ContextRefreshedEvent
  |
context.start()
  +-- LifecycleProcessor.start(): send start signal to Lifecycle beans
  +-- publish ContextStartedEvent
  |
context.stop()
  +-- LifecycleProcessor.stop(): send stop signal to Lifecycle beans
  +-- publish ContextStoppedEvent
  |       \-- @EventListener / ApplicationListener receives event
  |
context.start()       <-- can run again after stop
  +-- LifecycleProcessor.start()
  +-- publish ContextStartedEvent
  |
context.close()
  +-- publish ContextClosedEvent during closing
  +-- stop still-running Lifecycle beans, destroy singleton beans
  +-- context reaches end of lifecycle
```

The two events `ContextStartedEvent` and `ContextStoppedEvent` normally accompany explicit `start()`/`stop()` calls. `ContextRefreshedEvent` is the initialization/refresh signal. `ContextClosedEvent` is tied to closing the context and destroying resources.

A normally shutting-down application might call `close()` **without ever explicitly calling `stop()` beforehand**. In that case, do not assume by default that `ContextStoppedEvent` will always occur. In Spring Boot or server applications, many shutdown flows rely on `ContextClosedEvent`, `SmartLifecycle`, and the context closing procedure; the stopped event is not a universal signal replacing every JVM shutdown.

## 3. Relationship with Lifecycle, SmartLifecycle, and LifecycleProcessor

`ContextStoppedEvent` describes the *event after the context stop signal*, while the bean-stopping operation is coordinated by `LifecycleProcessor` (by default `DefaultLifecycleProcessor`).

### Lifecycle

A bean implementing `org.springframework.context.Lifecycle` has three primary methods:

```java
void start();
void stop();
boolean isRunning();
```

When the context receives `start()`, the lifecycle processor starts managed beans. When `stop()` is called, the processor asks running beans to stop. `isRunning()` helps Spring check the current state.

**A bean implementing only `Lifecycle` is normally not auto-started during the refresh step**; it receives the start signal when the context is explicitly started. This makes the example in section 5 produce easily verifiable output.

### SmartLifecycle

`SmartLifecycle` extends `Lifecycle` and supports advanced coordination:

- `isAutoStartup()`: defaults to returning `true`, allowing auto-start when context refresh completes.
- `getPhase()`: a phase number controlling startup and shutdown order. On start, lower phases normally run first; on stop, higher phases normally stop first.
- `stop(Runnable callback)`: supports asynchronous stopping; the bean must invoke `callback.run()` after actually stopping so the lifecycle processor knows it is done. If the callback is not called, the shutdown stage may have to wait until timeout.
- Dependency relationships between beans can take precedence over phase, because a dependent bean needs to stop before the bean it depends on.

By default in Spring Framework 6.x, `SmartLifecycle` has a high phase, so it is normally processed for stop before `Lifecycle` beans at phase 0. Do not infer order from bean names or class declaration order.

### When do listeners receive ContextStoppedEvent?

In the normal `AbstractApplicationContext.stop()` path, Spring calls `LifecycleProcessor.stop()` and then **publishes** `ContextStoppedEvent`. Consequently, with the default synchronous event publisher, the event-receiving callback runs after the processor has finished its stop call.

Two things must be distinguished:

1. **The stop order of beans** is controlled by the lifecycle processor, phases, and dependencies.
2. **The execution order of listeners receiving ContextStoppedEvent** is controlled by the event multicaster and can use `@Order`.

An `@Order(-100)` listener receiving `ContextStoppedEvent` does not cause it to run before `Lifecycle.stop()` of all beans. It is only prioritized relative to other listeners receiving the same event.

If a `SmartLifecycle` bean performs an asynchronous stop and does not finish within the deadline, the processor may handle a timeout. Therefore, do not treat this event as an absolute guarantee that all external resources were released successfully; observe the actual shutdown status.

## 4. Two ways to listen for ContextStoppedEvent

**Using @EventListener**: convenient when working with Spring-managed beans.

```java
@Component
class StopAudit {
    @EventListener
    void whenStopped(ContextStoppedEvent event) {
        System.out.println("Stopped context: " +
                event.getApplicationContext().getId());
    }
}
```

This is an illustrative snippet: you need to import `@Component`, `@EventListener`, `ContextStoppedEvent` and place the bean in the application context. The full code in section 5 does not require component scanning.

**Using ApplicationListener**: suitable when you want to make the event type explicit at the interface level.

```java
@Component
class StopAuditListener implements ApplicationListener<ContextStoppedEvent> {
    @Override
    public void onApplicationEvent(ContextStoppedEvent event) {
        System.out.println("Context stopped");
    }
}
```

Both approaches can be used. In a minimal example, `@EventListener` is chosen for readability. Do not register the same object via multiple mechanisms if doing so causes the logic to be invoked redundantly.

Because the event is an `ApplicationContextEvent`, it carries the **source context**. In systems with parent/child contexts, events can propagate to the parent and cause a listener in the parent to see events published from the child. If handling is intended only for a specific context, check `event.getApplicationContext()` rather than silently assuming every received event originated from the context owning the listener.

## 5. Runnable Maven + Java 17 example

The example below demonstrates:

- After initialization, a regular `Lifecycle` bean is not running yet.
- `context.start()` calls `worker.start()` and publishes `ContextStartedEvent`.
- `context.stop()` calls `worker.stop()` then publishes `ContextStoppedEvent`; the listener sees `worker.isRunning() == false`.
- After stop, the context remains active and can be started again.
- `close()` at the end publishes `ContextClosedEvent`, after which the context ends its lifecycle.

File structure:

```text
spring-context-stopped/
├── pom.xml
└── src/main/java/demo/ContextStoppedDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-context-stopped</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                    <mainClass>demo.ContextStoppedDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ContextStoppedDemo.java`:

```java
package demo;

import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;
import org.springframework.context.event.EventListener;

public class ContextStoppedDemo {

    public static class Worker implements Lifecycle {
        private boolean running;

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("worker.start");
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("worker.stop");
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }
    }

    public static class Observers {
        private final Worker worker;

        public Observers(Worker worker) {
            this.worker = worker;
        }

        @EventListener
        public void onStarted(ContextStartedEvent event) {
            System.out.println("event.started; workerRunning=" + worker.isRunning());
        }

        @EventListener
        public void onStopped(ContextStoppedEvent event) {
            System.out.println("event.stopped; workerRunning=" + worker.isRunning());
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            System.out.println("event.closed");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Worker worker() {
            return new Worker();
        }

        @Bean
        Observers observers(Worker worker) {
            return new Observers(worker);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Worker worker = context.getBean(Worker.class);

            System.out.println("after refresh: running=" + worker.isRunning());

            context.start();
            context.stop();

            System.out.println("after stop: active=" + context.isActive()
                    + ", running=" + worker.isRunning());

            context.start();
            context.stop();
        }

        System.out.println("after try: context closed");
    }
}
```

Run in the `spring-context-stopped` directory with JDK 17+ and Maven available:

```bash
mvn -q clean compile exec:java
```

Output from the program's `System.out.println` statements (excluding external logs):

```text
after refresh: running=false
worker.start
event.started; workerRunning=true
worker.stop
event.stopped; workerRunning=false
after stop: active=true, running=false
worker.start
event.started; workerRunning=true
worker.stop
event.stopped; workerRunning=false
event.closed
after try: context closed
```

Explanation:

1. `Worker` implements regular `Lifecycle`, not auto-starting `SmartLifecycle`, so after refresh it is still `running=false`.
2. `context.start()` triggers the lifecycle processor: it calls `Worker.start()`, then Spring publishes `ContextStartedEvent`. The listener receiving the event prints status `true`.
3. `context.stop()` calls `Worker.stop()`, then publishes `ContextStoppedEvent`. The listener prints status `false`. Subsequent code still accesses the bean because the context has not closed.
4. `context.isActive()` remains `true` after stop, and both `start()`/`stop()` cycles work.
5. `try-with-resources` calls `close()` upon exiting the block. `ContextClosedEvent` is received by the listener before the context is completely released; that is a different event from `ContextStoppedEvent`. There is no additional explicit stop call in the example.

If `Worker` is replaced with a `SmartLifecycle` having `isAutoStartup() == true`, the state right after refresh and the output lines will differ because the worker may have been started automatically. That is why the example intentionally uses `Lifecycle`.

## 6. Comparing ContextStoppedEvent with other lifecycle events

| Event | Mechanism typically triggering it | Meaning | Context after operation |
| --- | --- | --- | --- |
| `ContextRefreshedEvent` | `refresh()` or successful context initialization | Bean factory and context mechanisms are ready | Active |
| `ContextStartedEvent` | `start()` | `Lifecycle` beans have received the start signal | Active, runnable |
| `ContextStoppedEvent` | `stop()` | `Lifecycle` beans have received the stop signal | **Still active, can be started again** |
| `ContextClosedEvent` | `close()`, shutdown hook | Context is closing, singletons are destroyed during shutdown | Cannot be reused after closing |

Do not use `ContextStoppedEvent` as another name for `ContextClosedEvent`: the two events do not share the same trigger or lifecycle guarantees.

Methods that must also be distinguished:

- `context.isActive()`: reflects that the context has been refreshed and not yet closed, so it can be **true after stop**.
- `context.isRunning()`: reflects the state of the lifecycle processor and managed components. This is not a check for "whether the bean factory is still usable".
- `worker.isRunning()`: the bean's own state, managed by the implementer.
- `context.close()`: ends the lifecycle and destroys beans; do not use `start()` to revive the same context after close.

## 7. Situations to watch out for in production

### 7.1. Event listeners can run synchronously, slowing down stop

With the default `SimpleApplicationEventMulticaster`, `@EventListener` methods are usually invoked directly on the thread executing `context.stop()`. A `ContextStoppedEvent` listener performing slow I/O can prolong stop duration. `@Order` can specify the order of listeners receiving the event, but does not change `LifecycleProcessor`'s bean-stopping order.

If the multicaster is configured to use an asynchronous executor or the method uses `@Async`, callbacks may run on another thread and the caller of `stop()` is no longer guaranteed to wait for listeners to finish. Do not use this async event as a synchronization barrier for shutdown.

### 7.2. ContextStoppedEvent does not replace implementing stop()

If a component owns threads, schedulers, consumers, or connections, the actual stopping logic must be placed in `Lifecycle.stop()` or `SmartLifecycle.stop(Runnable)` (or a corresponding shutdown mechanism). A listener receiving `ContextStoppedEvent` is suited for observation or optional supplementary tasks.

Putting core resource shutdown exclusively inside a listener can lead to situations where the system closes the context via `close()` without the stopped listener running, or where the stop listener runs after other beans have already stopped, when resources are no longer available.

### 7.3. stop() and shutdown hooks

`context.registerShutdownHook()` registers closing the context on JVM shutdown, following the close mechanism. `@PreDestroy`, `DisposableBean.destroy()`, and destruction callbacks handle resource cleanup on close. A `ContextStoppedEvent` is only tied to the appropriate stop path; do not assume a shutdown hook publishes both started/stopped events.

### 7.4. Repeated stop(), multiple contexts, and event observation

Application code should guard itself against stop commands occurring more than once. `Lifecycle.stop()` should be idempotent, and listeners should not assume an event always corresponds to stopping new work. If there are parent/child contexts, check `event.getApplicationContext()` to distinguish which context actually stopped.

A listener can use:

```java
@EventListener
public void onStopped(ContextStoppedEvent event) {
    String contextId = event.getApplicationContext().getId();
    // Record contextId in logs or metrics.
}
```

This is an illustrative snippet that can be placed in a Spring-managed bean; full runnable code is in section 5.

### 7.5. The event does not guarantee external-to-process resources have stopped

Receiving `ContextStoppedEvent` means the context is going through a stop operation, but does not confirm external tasks have finished processing, queues have drained, or all async callbacks have been acknowledged. With `SmartLifecycle`, write `stop(Runnable callback)` properly, configure reasonable stop timeouts, and actually monitor resources.

If a `ContextStoppedEvent` listener throws an exception in the default synchronous mode, the error can impact the stop call and other listeners backward. Design an appropriate error policy for logs/metrics and avoid making lifecycle listeners depend on fragile external systems.

## 8. When should it be used?

Use `ContextStoppedEvent` when you need to **observe and react supplementally** to an explicit `stop()` of an `ApplicationContext`: recording the stop timestamp, updating health/metrics, or preventing new work generation in a component that only cares about the lifecycle milestone.

If you want to stop a stateful task processor, prefer `Lifecycle`/`SmartLifecycle`. If you want to clean up resources when the application truly terminates, prefer destruction callbacks and `ContextClosedEvent` handling. If you want to react to order/payment business events, create your own application events.

Self-check questions:

1. **When does `ContextStoppedEvent` occur?** When the context receives a `stop()` operation via Spring's mechanism.
2. **Can `start()` be called again after stop?** Yes, if the context has not been closed and the implementation supports the normal lifecycle.
3. **Does `ContextStoppedEvent` automatically destroy singleton beans?** No; destruction belongs to the close path.
4. **Does `@Order(-10)` on a stopped listener make a `SmartLifecycle` stop earlier?** No; listener ordering is distinct from lifecycle phase.
5. **If a shutdown hook only calls close, can you rely on ContextStoppedEvent?** No; listen to `ContextClosedEvent` or use appropriate lifecycle/destruction callbacks.
6. **How do you know which context stopped in a multi-context application?** Use `event.getApplicationContext()`.
7. **Why shouldn't a stopped listener do heavy I/O?** It can hold up the thread calling stop and make the shutdown path slow or encounter unintended errors.

## References

- [Spring Framework 6.2 — ApplicationContext Standard Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [ContextStoppedEvent API (Spring 6.2.8)](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/ContextStoppedEvent.html)
- [AbstractApplicationContext API (Spring 6.2.8)](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [SmartLifecycle API (Spring 6.2.8)](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [DefaultLifecycleProcessor API (Spring 6.2.8)](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html)
