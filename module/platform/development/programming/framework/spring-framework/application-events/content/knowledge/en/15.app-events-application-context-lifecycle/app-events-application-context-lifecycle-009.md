# Application Closing Events in Spring Framework Application Events

## 1. What is ContextClosedEvent?

`ContextClosedEvent` is a standard lifecycle event of the Spring Framework, published when an `ApplicationContext` is executing its closing process. In a typical application, this is the signal letting interested components know that the context is about to end its lifecycle: stop accepting new work, record final operational status, notify an orchestration unit, or coordinate cleanup steps.

For example, an order-processing system has components:

- A listener monitoring that the application is about to stop, to switch serving status to "draining".
- A `SmartLifecycle` component stopping intake of additional jobs and waiting for running jobs to finish.
- Beans holding connections or internal resources, releasing them in `destroy()` or `@PreDestroy`.
- A web application needing to complete in-flight requests under a graceful shutdown policy.

These responsibilities are related, yet **you should not lump all of them into a single listener**. `ContextClosedEvent` notifies that **the context is about to close**, whereas stopping and releasing resources according to bean lifecycle remains managed by Spring's lifecycle mechanisms.

This event type has the inheritance hierarchy:

```text
java.util.EventObject
    -> org.springframework.context.ApplicationEvent
        -> org.springframework.context.event.ApplicationContextEvent
            -> org.springframework.context.event.ContextClosedEvent
```

The main information lies in `event.getApplicationContext()`: the context that published the event. You do not need to manually instantiate `ContextClosedEvent` to trigger closing the application; close the context with the corresponding API so Spring properly coordinates the entire lifecycle.

## 2. When does Spring publish the close event?

Typical scenarios:

1. Application code calls `close()` on a `ConfigurableApplicationContext`.
2. A context registered a JVM shutdown hook via `registerShutdownHook()` and the JVM performs a normal shutdown.
3. An application managed by Spring Boot is asked to shut down through standard procedures, leading to closing the application context.

`ApplicationContext` is a read/access interface for the context; **not every variable declared with type `ApplicationContext` has a `close()` method**. The closing API belongs to `ConfigurableApplicationContext` and implementations like `AnnotationConfigApplicationContext`.

For example:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class);

// Program work...

context.close(); // Spring publishes ContextClosedEvent and closes the context.
```

Because `AnnotationConfigApplicationContext` supports `AutoCloseable`, `try-with-resources` can also be used to ensure `close()` is called upon exiting the block:

```java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Use the beans.
} // close() is called here.
```

The two snippets above are **API usage samples**, not standalone programs; a full example with concrete beans is in section 5.

### Cases where receiving the event is not guaranteed

`ContextClosedEvent` is only published if the context actually enters the close procedure. Forcibly killing the JVM (e.g., `SIGKILL`), process crashes, power loss, or immediate termination by the runtime environment **do not guarantee** that shutdown hooks, listeners, or destroy callbacks will run.

Even when a normal shutdown signal is sent, the process/container wait time may be limited. Therefore, do not use `ContextClosedEvent` as the sole place to persist critical business information.

## 3. Closing sequence in AbstractApplicationContext

In Spring Framework's common `AbstractApplicationContext` implementation, the closing flow at a conceptual level is:

```text
ConfigurableApplicationContext.close()
             |
             v
     Begin doClose() procedure
             |
             v
     Publish ContextClosedEvent
             |
             v
   LifecycleProcessor.onClose()
   (stop Lifecycle/SmartLifecycle beans)
             |
             v
   Destroy context-managed singleton beans
   (DisposableBean, @PreDestroy, destroy-method)
             |
             v
    Close BeanFactory/context
```

**With the default synchronous multicaster**, the `@EventListener(ContextClosedEvent.class)` callback is usually invoked **before** singleton beans are destroyed. Inside the callback, some dependencies may still exist; that does not mean starting long new work or relying on all infrastructure remains safe.

The sequence above describes `AbstractApplicationContext` in Spring 6.x and can be affected by custom multicasters, async listeners, or other context implementations. At the API level, rely on the **appropriate lifecycle contract** instead of writing logic tightly coupled to internal order without testing.

| Phase | Spring mechanism | Meaning |
| --- | --- | --- |
| Notify context is about to close | `ContextClosedEvent` | Observe or begin coordination |
| Stop lifecycle-aware components | `LifecycleProcessor`, `SmartLifecycle` | Coordinate ordered/phased stopping and completion callbacks |
| Clean up bean resources | `DisposableBean.destroy()`, `@PreDestroy`, `@Bean(destroyMethod=...)` | Release resources owned by the bean |
| End context | `close()` completes | Do not continue fetching beans or publishing events into the closed context |

**Do not confuse with `ContextStoppedEvent`:** calling `context.stop()` stops `Lifecycle` beans and publishes `ContextStoppedEvent`, yet the context can be `start()`-ed again. `context.close()` ends the context lifecycle; a closed context cannot be used to refresh or restart as before.

## 4. Registering a listener for ContextClosedEvent

### 4.1. Using `@EventListener`

Concise approach when the bean is already Spring-managed:

```java
@Component
public class ShutdownObserver {

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println("Context closing: "
                + event.getApplicationContext().getId());
    }
}
```

This is an integration snippet: you need to import `@Component`, `@EventListener`, and `ContextClosedEvent`; the class must be registered via component scanning or bean declaration. The method parameter tells Spring the exact event type it is interested in.

You can write the event type explicitly with `@EventListener(ContextClosedEvent.class)`, though if the method already has a `ContextClosedEvent` parameter, the concise form above is clear enough.

### 4.2. Using `ApplicationListener<ContextClosedEvent>`

```java
@Component
public class ShutdownListener
        implements ApplicationListener<ContextClosedEvent> {

    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        // Handle the signal that the context is preparing to close.
    }
}
```

A class using the interface is a valid option when you want the listener type expressed directly in the class declaration. Do not register the same listener via multiple mechanisms and accidentally create duplicate callbacks.

### 4.3. Identifying the event-publishing context

`event.getApplicationContext()` returns the context associated with the event; in a system with multiple parent/child contexts, this information is especially important.

```java
@EventListener
public void onContextClosed(ContextClosedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return; // Ignore close signals from other contexts.
    }
    // Handle specifically for the context this bean monitors.
}
```

This is an integration pattern; `ownContext` must be an injected `ApplicationContext` dependency. Spring can propagate events from a child context to a parent context; a listener placed in the parent context can see events published from the child context. If exact scoping is needed, compare the **context instance**, rather than assuming all `ContextClosedEvent`s belong to the listener's own context.

## 5. Complete runnable example with Java 17 + Spring Framework

The example below proves three points:

1. Inside `try-with-resources`, the context is closed automatically.
2. `@EventListener` receives `ContextClosedEvent` while the sample resource is still open.
3. `DisposableBean.destroy()` is called afterward to close the resource.

The example uses plain `AnnotationConfigApplicationContext`: no web server, database, or Spring Boot is needed.

### Project structure

```text
context-closed-event-demo/
├── pom.xml
└── src/main/java/example/ContextClosedEventDemo.java
```

### File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>context-closed-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <configuration>
                    <mainClass>example.ContextClosedEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### File `src/main/java/example/ContextClosedEventDemo.java`

```java
package example;

import java.util.ArrayList;
import java.util.List;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

public class ContextClosedEventDemo {

    // Hold evidence to print after the context has closed.
    public static final class Trace {
        private final List<String> events = new ArrayList<>();

        public void add(String event) {
            events.add(event);
        }

        public void printAll() {
            events.forEach(System.out::println);
        }
    }

    // Simulate a bean owning a resource that needs closing.
    public static final class TrackedResource implements DisposableBean {
        private final Trace trace;
        private boolean open = true;

        public TrackedResource(Trace trace) {
            this.trace = trace;
        }

        public boolean isOpen() {
            return open;
        }

        @Override
        public void destroy() {
            open = false;
            trace.add("DisposableBean.destroy: resourceOpen=" + open);
        }
    }

    // Only observes the close signal; the resource self-destructs when Spring
    // invokes DisposableBean.destroy().
    public static final class CloseObserver {
        private final Trace trace;
        private final TrackedResource resource;

        public CloseObserver(Trace trace, TrackedResource resource) {
            this.trace = trace;
            this.resource = resource;
        }

        @EventListener
        public void onContextClosed(ContextClosedEvent event) {
            trace.add("ContextClosedEvent: resourceOpen="
                    + resource.isOpen());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public TrackedResource trackedResource(Trace trace) {
            return new TrackedResource(trace);
        }

        @Bean
        public CloseObserver closeObserver(Trace trace,
                                            TrackedResource resource) {
            return new CloseObserver(trace, resource);
        }
    }

    public static void main(String[] args) {
        Trace trace;
        TrackedResource resource;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            trace = context.getBean(Trace.class);
            resource = context.getBean(TrackedResource.class);
            System.out.println("Before close: resourceOpen="
                    + resource.isOpen());
        }

        System.out.println("After close: resourceOpen="
                + resource.isOpen());
        trace.printAll();
    }
}
```

### Run the program

In the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

**Lines printed by the application:**

```text
Before close: resourceOpen=true
After close: resourceOpen=false
ContextClosedEvent: resourceOpen=true
DisposableBean.destroy: resourceOpen=false
```

The "After close" line is printed **before the lines stored in `Trace`** because the program explicitly prints the status after exiting the `try` block, and only then calls `trace.printAll()`. The actual order of the **two callbacks** is reflected in the last two lines: the `ContextClosedEvent` listener is called while the resource is still open; afterward Spring calls `DisposableBean.destroy()` and sets `open = false`.

In real applications, you should not continue calling services or using closed resources. Here the `resource` and `trace` variables are retained after the context closes only to read state and print verification data; both are simple in-memory Java objects. No external infrastructure is accessed after close.

**Why does the example work?** When initializing `AnnotationConfigApplicationContext(Config.class)`, Spring creates singleton beans and registers `CloseObserver`'s `@EventListener` method. When `try-with-resources` calls `close()`, `AbstractApplicationContext` publishes `ContextClosedEvent`, then stops lifecycle beans and destroys singletons. `TrackedResource` implements `DisposableBean`, so it receives the `destroy()` call.

### A variant to check events only from the observed context

If the code runs in a multi-context system, you can inject `ApplicationContext` into `CloseObserver` and record only when `event.getApplicationContext() == localContext`. The example in section 5 has only one context, so that condition is not needed.

## 6. JVM shutdown hooks and proactive closing

### 6.1. Proactively closing with `close()`

For command-line applications, integration tests, or lifecycle-controlling containers, `try-with-resources` or `context.close()` provides an explicit closing point. This is usually the **easiest way to test** to verify `ContextClosedEvent` and bean destruction callbacks.

### 6.2. Registering a shutdown hook

When an application stays alive until the JVM terminates, you can register a hook:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(Config.class);

context.registerShutdownHook();

// The program continues running. When the JVM shuts down normally,
// the hook will request closing the context.
```

This snippet illustrates the API and uses the `Config` class from the previous example; it is not a standalone long-running application. When the context has already been closed proactively, Spring handles the registered hook so it does not close redundantly.

**Limitation:** JVM shutdown hooks are not guaranteed to run in all scenarios. Forced termination commands like `kill -9`, certain OS crashes, or containers killed after exceeding their grace period can prevent callbacks from finishing. Treat shutdown hooks as **graceful shutdown** support, not a durable persistence mechanism.

### 6.3. When using Spring Boot

In a typical Spring Boot application, the framework manages the context and registers the shutdown procedure with the JVM. When the application is closed via standard procedures, `ContextClosedEvent` remains the Spring context's lifecycle event.

For web servers, distinguish between **closing the context** and **graceful shutdown** of the server: graceful shutdown focuses on stopping acceptance of new requests and giving in-flight requests a chance to finish within configured limits. Long tasks, internal queues, and event processing still require appropriate stopping policies.

Do not infer that because a `ContextClosedEvent` listener has finished, all requests, jobs, and notification dispatches have finished.

## 7. Choosing the right shutdown mechanism for each responsibility

| Need | Suitable mechanism | Reason |
| --- | --- | --- |
| Log/metrics for a context-closing signal | `@EventListener(ContextClosedEvent.class)` | Observing a context-wide event |
| Close connection/file/socket owned by a bean | `@PreDestroy`, `DisposableBean`, or `destroyMethod` | Cleanup resides with the resource owner |
| Stop task-accepting components, await completion by phase | `SmartLifecycle` | Supports phases, `stop(Runnable)`, and coordination by `LifecycleProcessor` |
| Close context in an application/test | `ConfigurableApplicationContext.close()` or try-with-resources | Proactively triggers the proper Spring procedure |
| Close on normal JVM termination | `registerShutdownHook()` if needed | Ties closing to JVM shutdown |
| Must not lose events/work if the process dies | Database/outbox/broker, durable checkpointing | Shutdown listeners are not guaranteed to run on crashes |

**For bean cleanup**, prefer the corresponding destroy callback rather than a context-wide listener having to know all resources. For example, datasource pools usually already have their own closing mechanism; calling `close()` a second time from `ContextClosedEvent` can cause races or hard-to-diagnose errors.

**For components needing ordered stopping**, `SmartLifecycle` supports phase ordering and the `stop(Runnable)` callback. This callback must be invoked when asynchronous stopping finishes; forgetting to call the callback can make shutdown wait until timeout. When an application has running queues/jobs, this is usually a clearer choice than an event listener that kicks off an async task and returns immediately.

## 8. Important limitations of ContextClosedEvent

### 8.1. Do not use as a final store for business events

Suppose a context-closing listener tries to send an email or flush metrics to an HTTP API:

```java
@EventListener
public void onClosing(ContextClosedEvent event) {
    remoteReporter.sendFinalMetrics();
}
```

This is an illustrative snippet requiring an injected `remoteReporter` bean. A synchronous network call can prolong shutdown; an async call may be rejected because the executor is also closing. If sending is critical, persist the data **while the application is still running**, then retry via a worker/broker or process with durable checkpoints. A close listener should only finish brief coordination with reasonable timeouts.

### 8.2. Be careful with `@Async` on close listeners

`@Async @EventListener` causes the callback to run later on the specified executor. While the context is closing, the executor, dependencies, and related beans may also be destroyed. Therefore, successfully **submitting** an async task does not prove the task finished before shutdown ended.

If a stopping step must complete before releasing resources, use `SmartLifecycle` or a synchronous/callback mechanism with explicit timeouts; do not rely on a fire-and-forget task.

### 8.3. Do not confuse with transactional listeners

`ContextClosedEvent` is a context lifecycle event, normally **not tied to a business transaction**. Placing `@TransactionalEventListener` on a method listening only to close can prevent the listener from running, because by default `fallbackExecution = false` when no transaction exists. Use `@EventListener` to observe context close events.

### 8.4. Listeners throwing exceptions during closing

In the `AbstractApplicationContext` implementation, the closing path handles errors when publishing `ContextClosedEvent` so subsequent closing steps continue. Nevertheless, an exception from one listener can affect the multicaster's invocation of other listeners, and the error must be recorded. Do not use exceptions from listeners to control the destruction of other beans.

If cleanup can fail, catch exceptions at the proper boundary, log/record metrics appropriately, and ensure critical resources are still closed by their owning beans via the official lifecycle.

### 8.5. Parent/child contexts and multiple application contexts

One process can have multiple contexts. Events published in a child context can propagate up to the parent context. A listener in the parent context can therefore receive `ContextClosedEvent`s pertaining to child contexts. Check `event.getApplicationContext()` if an operation should only execute for a specific context.

Do not conclude on your own that a child context close event means **the entire JVM** is stopping or all other contexts have closed.

### 8.6. Callback ordering and idempotency

A normal context only goes through the close procedure once, but real systems can create multiple contexts across tests, reloads, or multiple launch sessions. When a callback touches the same external resource, design the stop operation so it can run repeatedly without harm. For instance, closing a client should check state or rely on an idempotent close contract instead of failing when called again.

This does not mean Spring automatically guarantees exactly-once execution for external side effects.

## 9. Testing application closing events

A test should verify **the event is published**, **the right context**, and **relative order with cleanup**. From the example in section 5:

| Stage | Resource state | Expected outcome |
| --- | --- | --- |
| Context initialized | `open = true` | Resource can be used |
| Listener receives `ContextClosedEvent` | `open = true` | Listener knows the context is about to close |
| `DisposableBean.destroy()` | Switches `open` to `false` | Resource is released |
| After `close()` completes | `open = false` | Do not reuse beans/resources |

**Valuable additional tests:**

1. **Right event type:** register a listener receiving only `ContextClosedEvent`, confirm it does not mistakenly handle `ContextRefreshedEvent` or `ContextStoppedEvent`.
2. **Closing via API:** call `close()` or use try-with-resources on a real context; do not just call the `onContextClosed` method directly and treat it as an integration test.
3. **Right order:** record a simple trace, verify the close listener runs before destroy callbacks in the synchronous configuration in use.
4. **Parent/child contexts:** check whether the parent context's listener needs to ignore events originating from the child context.
5. **Listener errors:** induce a controlled error, verify logs and resource state after shutdown per the actual implementation.
6. **Shutdown in a real environment:** run through normal stop signals and time limits, then inspect persisted/checkpointed jobs. This test must be separate from in-memory unit tests.
7. **Multiple runs:** create and close multiple independent contexts, avoiding carrying over state from a previous run that skews results.

Testing shutdown hooks directly can terminate the test JVM; avoid running `System.exit(...)` inside the JVM running the main test suite. To test real hooks, spawn a **child process** and verify results from that process.

## 10. Common mistakes

1. **Confusing `ContextStoppedEvent` with `ContextClosedEvent`.** `stop()` is not synonymous with `close()`; a stopped context can be started again.
2. **Calling `close()` on a variable typed only as `ApplicationContext`.** Use `ConfigurableApplicationContext` or an implementation type supporting close.
3. **Assuming the event always runs when the process dies.** Shutdown is not guaranteed when the JVM is forcibly killed or crashes.
4. **Cramming all cleanup into one `@EventListener`.** Releasing resources should belong to the owning bean via destroy callbacks; stopping multiple phased services should use `SmartLifecycle`.
5. **Performing long I/O work inside the close callback.** This can prolong shutdown duration and hit container limits.
6. **Starting `@Async` tasks while the executor is closing.** Tasks may be rejected or fail to finish; stop handling must have proper waiting mechanisms.
7. **Manually creating a close event to replace `close()`.** Calling `publisher.publishEvent(new ContextClosedEvent(...))` only publishes an event object; it does not execute `close()`'s full bean-destruction procedure.
8. **Not checking the event-publishing context.** In parent/child structures you may receive close signals from another context.
9. **Assuming beans remain usable after `close()`.** Singletons have been destroyed; do not continue dispatching work based on closed beans or connections.
10. **Assuming close listeners have an available transaction.** Do not use `@TransactionalEventListener` when the goal is simply to receive context close events.
11. **Ignoring errors during closing.** Log sufficient information and coordinate cleanup, but do not treat listeners as a place to "block" the application from stopping.
12. **Relying on default ordering among multiple listeners.** If ordering is truly needed, define explicit orchestration or configure `SmartLifecycle` with appropriate phases; with async, completion order is even less guaranteed.

## 11. Adoption checklist

- The application has an explicit context-closing point: `close()`, try-with-resources, or a framework-managed hook.
- The listener accepts the right `ContextClosedEvent` and is registered as a Spring bean.
- With multiple contexts, `event.getApplicationContext()` is properly identified.
- The close callback performs only brief work fitting shutdown time limits.
- Bean-owned cleanup uses `DisposableBean`, `@PreDestroy`, or a destroy method.
- Tasks needing ordered stopping use `SmartLifecycle`, with completion/timeout callbacks tested.
- Not relying on shutdown events to save business data that must not be lost.
- Tested the event → destroy order and verified state after `close()`.
- Considered graceful shutdown and retry/checkpointing for in-flight tasks in production.

**Remember:** `ContextClosedEvent` notifies that **the Spring ApplicationContext is closing**. In `AbstractApplicationContext` with the normal synchronous multicaster, the event reaches listeners before singleton beans are destroyed. Use listeners to observe/coordinate; use lifecycle/destroy callbacks to stop and close resources properly; and do not treat shutdown events as a durable event-delivery guarantee.

## Official documentation

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Javadoc — ContextClosedEvent (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/ContextClosedEvent.html)
- [Javadoc — AbstractApplicationContext (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [Javadoc — ConfigurableApplicationContext (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
