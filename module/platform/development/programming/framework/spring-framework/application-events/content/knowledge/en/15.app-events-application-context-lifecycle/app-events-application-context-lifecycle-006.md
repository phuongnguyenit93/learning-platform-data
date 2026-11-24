# ApplicationContextEvent in the Spring ApplicationContext Lifecycle

## 1. Position of ApplicationContextEvent in the event system

`ApplicationContext` is the container managing beans, dependency injection, configuration, and the lifecycle of components in a Spring application. When a context is initialized, receives a start signal, stops, or closes, Spring can publish **context lifecycle events** so beans can observe and react.

`ApplicationContextEvent` is the **abstract base class** for these lifecycle events, located in the `org.springframework.context.event` package. It is part of the Spring Framework, independent of Spring Boot:

~~~text
java.util.EventObject
  └── org.springframework.context.ApplicationEvent
        └── org.springframework.context.event.ApplicationContextEvent
              ├── ContextRefreshedEvent
              ├── ContextStartedEvent
              ├── ContextStoppedEvent
              └── ContextClosedEvent
~~~

There are three main points:

1. `ApplicationContextEvent` represents **an event happening to the ApplicationContext itself**. It does not represent a business domain event such as placing an order, processing a payment, or creating an account.
2. This class is `abstract`. Typically we register a listener for the base class or a specific subclass, rather than trying to instantiate an `ApplicationContextEvent` directly.
3. The four subclasses above are used by the Spring Framework when executing the corresponding lifecycle operations. Listeners receive information on **which context** published the event and can distinguish events by type.

For instance, a listener that only needs to observe when the context is ready at the container level receives `ContextRefreshedEvent`; a listener serving resource reclamation when the context is closing receives `ContextClosedEvent`. Placing mandatory business logic inside lifecycle listeners requires careful consideration because their execution timing differs from request-level use cases.

## 2. Core API: constructor, event source, and timestamp

Conceptual class declaration:

~~~java
public abstract class ApplicationContextEvent extends ApplicationEvent {
    public ApplicationContextEvent(ApplicationContext source) { /* ... */ }

    public final ApplicationContext getApplicationContext() { /* ... */ }
}
~~~

This is a **condensed illustrative signature**; internal implementation details are omitted here.

- `ApplicationContextEvent(ApplicationContext source)` takes the context itself associated with the event; the source must not be `null`.
- `event.getApplicationContext()` returns the `ApplicationContext` object related to the event, with a more specific and convenient return type than `getSource()`.
- `event.getSource()` is inherited from `EventObject` and returns the source typed as `Object`. For this event family, the source is the context itself.
- `event.getTimestamp()` is inherited from `ApplicationEvent`, indicating when the event object was created (epoch milliseconds), **not** a guarantee of when the whole application became ready or when a transaction committed.
- `event.getClass()`/`instanceof` helps distinguish subclasses when a listener registers to receive the base class.

Example using the event source:

~~~java
@EventListener
public void onContextEvent(ApplicationContextEvent event) {
    ApplicationContext source = event.getApplicationContext();
    System.out.println(source.getId() + " -> "
        + event.getClass().getSimpleName());
}
~~~

This snippet must be placed in a Spring bean registered with the context, along with imports for `ApplicationContext`, `ApplicationContextEvent`, and `EventListener`. The listener receives compatible subclasses of `ApplicationContextEvent`, so the class name in the log can be `ContextRefreshedEvent`, `ContextStartedEvent`, `ContextStoppedEvent`, or `ContextClosedEvent`.

**Note:** a context ID is descriptive data; if multiple contexts share the same ID, use **context object comparison** to filter for the exact source rather than relying solely on the ID string.

## 3. Four standard lifecycle events

| Event | When Spring publishes it | Appropriate usage |
| --- | --- | --- |
| `ContextRefreshedEvent` | When `ApplicationContext` finishes initialization or a successful `refresh()` operation | Observing container initialization, checking metadata/readiness at the context level |
| `ContextStartedEvent` | When the context receives a `start()` call | Observing explicit start signals, coordinating `Lifecycle` components |
| `ContextStoppedEvent` | When the context receives a `stop()` call | Observing explicit stop signals, pausing part of operations |
| `ContextClosedEvent` | When the context is closing via `close()` or a shutdown hook | Releasing/recording closing status, ending the lifecycle |

Typical relationship diagram:

~~~text
new AnnotationConfigApplicationContext()
         |
         | register(config), refresh()
         v
 ContextRefreshedEvent
         |
         | start()
         v
 ContextStartedEvent
         |
         | stop()
         v
 ContextStoppedEvent
         |
         | start() (can be started again)
         v
 ContextStartedEvent
         |
         | close()
         v
 ContextClosedEvent
         |
         v
 Context closed, cannot be reused
~~~

Not every application triggers all four events shown in the diagram. For instance, a context that only calls `refresh()` and then `close()` might only publish `ContextRefreshedEvent` and `ContextClosedEvent`. A normally starting Spring Boot application **does not necessarily call `start()` explicitly to publish `ContextStartedEvent`**. Do not conclude that not receiving `ContextStartedEvent` is a startup failure.

### 3.1. ContextRefreshedEvent: initialization or refresh finished

Upon receiving `ContextRefreshedEvent`, container-building steps such as processing configuration, registering post-processors, instantiating non-lazy singletons, and completing refresh have occurred according to the context's lifecycle. This is a useful point to observe that bean initialization has finished.

However:

- It does not mean all post-startup tasks of **Spring Boot** have ended. `ApplicationRunner`/`CommandLineRunner` beans may run after the refresh milestone; `ApplicationReadyEvent` in Spring Boot represents a different readiness milestone.
- It does not guarantee all external systems (databases, message brokers, other applications) are ready.
- Do not assert the event occurs **only once in the application's entire lifetime**: some context types support multiple refreshes, and parent–child context structures can result in multiple observed events.
- Do not manually call `context.refresh()` a second time on `AnnotationConfigApplicationContext`/`GenericApplicationContext` assuming hot refresh is supported; this family of contexts is not designed for repeated refreshes.

### 3.2. ContextStartedEvent: explicit start

`ContextStartedEvent` is tied to the `ConfigurableApplicationContext.start()` operation. This call also involves `LifecycleProcessor` and beans implementing `Lifecycle`. Depending on configuration, `SmartLifecycle` can be started automatically during the refresh phase; that **does not mean** `ContextStartedEvent` will appear automatically simply because a `SmartLifecycle` bean started.

Therefore, distinguish:

- Context just underwent `refresh()` → `ContextRefreshedEvent`.
- Caller explicitly invokes `context.start()` → `ContextStartedEvent`.
- `Lifecycle` beans started per container policy → the event above **is not** an individual per-bean event.

### 3.3. ContextStoppedEvent: recoverable stop

`ContextStoppedEvent` is tied to `context.stop()`. `LifecycleProcessor` sends the stop signal to beans participating in the lifecycle mechanism; the context can receive `start()` later to resume. `stop()` **does not mean `close()`**: singleton beans are not destroyed by default and the context has not permanently ended.

Whether an in-flight HTTP request, message queue listener, or background task stops safely depends on the bean implementing `Lifecycle`/`SmartLifecycle` and shutdown rules. Receiving `ContextStoppedEvent` does not prove all tasks outside the container have quiesced.

### 3.4. ContextClosedEvent: closing in progress

`ContextClosedEvent` is published by Spring when proceeding to close the context. In `AbstractApplicationContext`, the event is published during `doClose()` before certain steps that stop the lifecycle processor and destroy singletons; therefore, when the event-handling callback runs, **you cannot claim all beans have already finished being destroyed**.

After `close()` completes, the context reaches the end of its lifecycle: it is not reused for refresh/start in the normal way. For cleanup, a `ContextClosedEvent` listener can log, mark state, or coordinate halting work; whereas resources owned by a bean should prefer bean destruction callbacks such as `@PreDestroy` or `DisposableBean`/`destroyMethod`, and use `SmartLifecycle.stop(...)` when stop ordering needs coordination.

If a close-handling listener takes too long or throws an error, shutdown can be delayed or complicated. Avoid relying on already-destroyed beans or async work that may not finish in time.

## 4. Listening with @EventListener and ApplicationListener

### 4.1. Filtering for a single event type

~~~java
@Component
public class RefreshObserver {
    @EventListener
    public void afterRefresh(ContextRefreshedEvent event) {
        System.out.println(event.getApplicationContext().getId());
    }
}
~~~

This is an illustrative snippet in a project configured with component scanning. You need to import `Component`, `EventListener`, and `ContextRefreshedEvent`. When the method accepts `ContextRefreshedEvent`, Spring infers the event type from the parameter and will not invoke it simply upon encountering `ContextStoppedEvent`.

### 4.2. One listener handling multiple subtypes

~~~java
@Component
public class ContextAudit {
    @EventListener
    public void onAnyContextEvent(ApplicationContextEvent event) {
        if (event instanceof ContextClosedEvent) {
            System.out.println("CLOSING");
        } else if (event instanceof ContextRefreshedEvent) {
            System.out.println("REFRESHED");
        }
    }
}
~~~

If you want to handle other subtypes, add `instanceof` branches. Using the base type is convenient for logging and observability, but **you should not assume all events share the same business meaning**.

### 4.3. Using the ApplicationListener interface

~~~java
@Component
public class CloseObserver
        implements ApplicationListener<ContextClosedEvent> {
    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        System.out.println("Closing: "
            + event.getApplicationContext().getId());
    }
}
~~~

`ApplicationListener<E>` is an explicitly typed listener mechanism, useful when you want to express the event-listening contract directly in the interface. `@EventListener` is well-suited when one bean has multiple methods listening to different event types. Both approaches must be registered by Spring; do not accidentally attach both mechanisms to the same logic and cause duplicate processing.

With `@EventListener({ContextStartedEvent.class, ContextStoppedEvent.class})`, you can declare a **parameterless** method to run for multiple types. If you need to inspect the event type at runtime, use a parameter with a suitable common type like `ApplicationContextEvent` instead of a parameterless method.

## 5. Complete example: observing refresh, start, stop, and close

This example uses **Java 17+** and **Spring Framework 6.2.8**. Only `spring-context` is needed; Spring Boot is not required. We create a context manually, set a fixed ID, register the listener bean before refresh, and then call lifecycle operations to observe the order.

### 5.1. Project structure

~~~text
context-event-demo/
├── pom.xml
└── src/main/java/ContextLifecycleDemo.java
~~~

### 5.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>context-event-demo</artifactId>
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
                    <mainClass>ContextLifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. File ContextLifecycleDemo.java

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationContextEvent;
import org.springframework.context.event.EventListener;

public final class ContextLifecycleDemo {

    public static class LifecycleLogger {
        @EventListener
        public void onContextEvent(ApplicationContextEvent event) {
            System.out.println(
                event.getClass().getSimpleName()
                    + " | " + event.getApplicationContext().getId()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        LifecycleLogger lifecycleLogger() {
            return new LifecycleLogger();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            context.setId("demo-context");
            context.register(Config.class);
            context.refresh();
            context.start();
            context.stop();
            context.start();
        }
        // close() from try-with-resources is called upon exiting the block.
    }
}
~~~

Run in `context-event-demo/` with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

Main lines printed by the program itself, in order:

~~~text
ContextRefreshedEvent | demo-context
ContextStartedEvent | demo-context
ContextStoppedEvent | demo-context
ContextStartedEvent | demo-context
ContextClosedEvent | demo-context
~~~

**Explanation:**

1. `context.register(Config.class)` registers the configuration definition; it does not yet initialize the whole context. `context.refresh()` builds the context, creates `LifecycleLogger`, and registers the `@EventListener` method; afterward it publishes `ContextRefreshedEvent`.
2. `context.start()` sends the start signal and publishes `ContextStartedEvent`. The example has no separate `Lifecycle` bean, yet the event marks the context's start call.
3. `context.stop()` publishes `ContextStoppedEvent`. The context can still continue operating after a subsequent `start()`.
4. The second `start()` call produces another `ContextStartedEvent`. The example proves **you must not assume each lifecycle event type appears strictly once**.
5. Upon exiting `try-with-resources`, `AnnotationConfigApplicationContext.close()` is called and publishes `ContextClosedEvent`.

Keeping `LifecycleLogger` as a **non-lazy** bean ensures the listener is present before the first refresh event. If you only instantiate a listener with `new LifecycleLogger()` in other code without registering it with Spring, the `@EventListener` annotation by itself will not cause the method to be called.

Note that the program does not call `refresh()` a second time: `AnnotationConfigApplicationContext` belongs to the `GenericApplicationContext` family, which does not support arbitrary repeated hot refreshes. The example also does not use a thread executor, so output is not scrambled by async listeners.

## 6. Bean lifecycle and ApplicationContext lifecycle are different

A common mistake is listening to `ContextRefreshedEvent` and treating it as the moment **each bean** is initialized, or listening to `ContextClosedEvent` and assuming every bean has been destroyed. This is a confusion of scope.

| Mechanism | Target / meaning |
| --- | --- |
| Constructor, dependency injection, and `@PostConstruct` | Initializing **a single bean** |
| `InitializingBean.afterPropertiesSet()` / custom init method | Bean initialization hook |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Hook after the instantiation phase of regular singletons |
| `SmartLifecycle.start()/stop(...)` | Managing activity of a **lifecycle-aware bean** by phase and auto-startup policy |
| `ContextRefreshedEvent` | Event after a **context refresh** |
| `ContextClosedEvent` | Event published **during context closing** |
| `@PreDestroy` / `DisposableBean.destroy()` | **Bean** destruction hook when the container cleans up |

A `prototype` bean has a different lifecycle from a singleton; do not rely on lifecycle events to release all prototype objects callers have retrieved. Similarly, `ContextClosedEvent` does not replace the closing methods of specific resources such as connection pools, executors, or clients.

### Why isn't ContextStartedEvent a SmartLifecycle startup?

`SmartLifecycle` can auto-start during context refresh, depending on `isAutoStartup()` and phase. When `context.start()` is called explicitly, the lifecycle processor can also send start signals. However, `ContextStartedEvent` is tied to the **context's** operation, not an individual event published each time a `SmartLifecycle` bean executes `start()`.

If you need to precisely manage the lifecycle of a consumer, server adapter, or scheduler, implement `SmartLifecycle`/`Lifecycle` with proper phases, state, and shutdown; only use lifecycle events for context-level observation or coordination.

## 7. Parent–child contexts: why might multiple events be received?

An application can have **multiple ApplicationContexts**, such as a root context and a child context for web components. When a child context publishes an event, Spring's `AbstractApplicationContext` mechanism typically **propagates the event up to the parent context**. Thus a listener located in the parent context can see both:

- Events from the parent context itself.
- Events published from the child context and propagated up to the parent.

The normal propagation direction is from **child up to parent**, not automatically from parent down to every child context. Thanks to `event.getApplicationContext()`, the listener still knows which original context the event pertains to.

Illustrative example for a bean in the parent context:

~~~java
@Component
public class RootOnlyRefreshListener
        implements ApplicationContextAware {

    private ApplicationContext owner;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.owner = context;
    }

    @EventListener
    public void handle(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != owner) {
            return;  // Ignore events from child contexts.
        }
        System.out.println("Root context refreshed");
    }
}
~~~

This is a code snippet depending on an application configured with parent–child contexts and component scanning, not a standalone program. You need to import `Component`, `ApplicationContextAware`, `ApplicationContext`, `EventListener`, and `ContextRefreshedEvent`. Comparing `!=` between the two references confirms **the exact context object**, avoiding false positives when context IDs are configured identically.

Do not write a listener based solely on `ContextRefreshedEvent` to increment a counter for "application started once" without accounting for the number of contexts and refreshes. Especially with Spring Boot, documentation also notes the phenomenon of listeners receiving multiple events of the same type when a hierarchy exists.

### Filtering events with condition

In some cases `@EventListener(condition = "...")` with Spring Expression Language (SpEL) can be used. However, source/owner comparison logic is usually clearer in the listener body or in a dedicated service. When using conditions, understand SpEL variables and the accessibility of corresponding beans; avoid long expressions or calling external services on the event-publishing path.

## 8. Cross-reference with Spring Boot events

Spring Framework has `ContextStartedEvent`, while Spring Boot has `ApplicationStartedEvent`. **The two names are similar but differ in type and timing**.

| Event | Belongs to | Meaning |
| --- | --- | --- |
| `ContextRefreshedEvent` | Spring Framework | Container has refreshed |
| `ContextStartedEvent` | Spring Framework | Explicit call to `ConfigurableApplicationContext.start()` |
| `ContextClosedEvent` | Spring Framework | Context is closing |
| `ApplicationStartedEvent` | Spring Boot | Spring Boot has refreshed the context, before running `ApplicationRunner`/`CommandLineRunner` |
| `ApplicationReadyEvent` | Spring Boot | After runners have finished, milestone where the application is ready to serve requests per Boot lifecycle |
| `ApplicationFailedEvent` | Spring Boot | An error occurred during Spring Boot startup |

Boot's `SpringApplicationEvent` classes are **not** the four standard subclasses of `ApplicationContextEvent` listed at the start of this lesson; a listener registered only for `ApplicationContextEvent` should not be expected to catch all Boot events. Conversely, a general `ApplicationEvent` listener may see many other events in the context if the registration method allows it.

If the goal is **readiness to receive traffic** in Spring Boot, look into `ApplicationReadyEvent` and the application availability/readiness mechanism; do not use `ContextRefreshedEvent` to conclude the entire bootstrap has finished. If the goal is to turn on a service with specific start/stop semantics, look into `SmartLifecycle` instead of faking state with events.

## 9. Errors in lifecycle listeners and asynchronous processing

By default, `SimpleApplicationEventMulticaster` processes listeners synchronously on the publishing thread. Therefore, a `ContextRefreshedEvent` listener doing too much work can prolong refresh time; an unhandled exception can affect startup. A `ContextClosedEvent` listener waiting indefinitely on a network call can delay shutdown.

If you annotate a listener with `@Async` or replace the multicaster with an executor, you can avoid blocking the publishing thread, but you must understand:

- Listener work may execute while the context is changing state; when closing the context, the executor or dependencies may already have stopped or be stopping.
- Exceptions in asynchronous listeners do not automatically propagate back to the original caller like synchronous listeners.
- Receiving the event does not mean an async task is guaranteed to finish before the process terminates.
- Do not use async lifecycle listeners to replace ordered shutdown management or guarantee data flushing before the application stops.

For mandatory cleanup, manage **the resource inside the bean itself** with destruction callbacks/`SmartLifecycle`, with timeouts and error-handling capability. For work requiring reliable delivery, use appropriate queues/outbox/retry mechanisms; internal Spring events do not provide durable delivery by themselves.

## 10. Testing and observing the lifecycle accurately

A direct test case using `AnnotationConfigApplicationContext` can follow this sequence:

1. Create an unrefreshed context, register configuration and listeners.
2. Call `refresh()`, verify `ContextRefreshedEvent` is received exactly once **in this specific run**.
3. Call `start()`, verify `ContextStartedEvent`.
4. Call `stop()`, verify `ContextStoppedEvent`.
5. Call `start()` again, verify an additional `ContextStartedEvent` occurs.
6. Call `close()`, verify `ContextClosedEvent` and proper resource cleanup.

The code in section 5 provides an observational check with stable output. For integration tests with a context hierarchy, add cases for receiving child events in a parent listener and filtering via `event.getApplicationContext() == ownContext`.

Things to check when a listener does not run:

- Is the listener bean actually managed by Spring? Is there a `@Bean` or scanned `@Component`?
- Does the `@EventListener` method have the right parameter type? Was `ContextStartedEvent` confused with `ContextRefreshedEvent`?
- Was the listener registered **before** the event to be observed was published? Very early events may require registration mechanisms different from beans created later.
- Did the application actually call `context.start()`/`context.stop()`? Do not automatically expect these two events after every `refresh()`.
- Are there multiple contexts? Did the event come from a child context?
- Is the listener running async, failing, or being rejected by an executor? Are there logs/monitors?
- Were `ApplicationEventMulticaster`, `ErrorHandler`, or other filtering mechanisms customized?

**Do not verify "refresh once" by calling `refresh()` a second time on `AnnotationConfigApplicationContext`**; choose the right context type and supported lifecycle in examples.

## 11. Common confusions and mistakes

1. **Thinking ApplicationContextEvent covers all events in Spring.** It is the base class for the context lifecycle event group; business events can be POJOs or other `ApplicationEvent` types.
2. **Thinking ApplicationContextEvent can be instantiated directly with new.** It is abstract; register listeners for the base class or subclasses.
3. **Thinking ContextStartedEvent is published immediately after context refresh.** `start()` is an explicit operation; completing refresh publishes `ContextRefreshedEvent`.
4. **Thinking ContextStoppedEvent has destroyed all beans.** Stop and close are different; a stopped context can be started again.
5. **Thinking ContextClosedEvent only arrives after all singletons have been destroyed.** The event is published **during closing**, before many bean destruction steps.
6. **Thinking ContextRefreshedEvent means Spring Boot is ready to receive traffic.** Runners and readiness can occur after refresh.
7. **Counting events while ignoring context hierarchy.** A parent listener can see events from children; use `getApplicationContext()` to distinguish.
8. **Thinking repeated refresh is always supported.** `GenericApplicationContext`/`AnnotationConfigApplicationContext` are not arbitrary hot-refresh contexts.
9. **Using lifecycle events instead of bean hooks.** For bean-owned resources, use `@PreDestroy`/`DisposableBean`/`SmartLifecycle` as appropriate.
10. **Cramming heavy work into synchronous listeners at refresh/close.** This can increase startup time or obstruct shutdown.
11. **Manually publishing a ContextRefreshedEvent to simulate a real refresh.** Sending an event object does not execute the container refresh pipeline, nor does it create or reconfigure beans.
12. **Putting business transactions into ContextClosedEvent.** The context is stopping and dependencies may no longer be available; handle use cases within proper boundaries and controlled shutdown.

## 12. Practice questions

1. How does `ApplicationContextEvent` differ from `ApplicationEvent` and a POJO event? Can it be instantiated directly?
2. In the example, why are there two `ContextStartedEvent`s but only one `ContextRefreshedEvent`?
3. If you only call `refresh()` and then `close()`, are you guaranteed to receive `ContextStartedEvent`/`ContextStoppedEvent`?
4. Why shouldn't a `ContextClosedEvent` listener assert that all singletons have already been destroyed at the moment the event is received?
5. In a `root → child` hierarchy, why can a listener in root receive a child's `ContextRefreshedEvent`? How do you filter for root only?
6. Is `ContextRefreshedEvent` equivalent to Spring Boot's `ApplicationReadyEvent`?
7. A consumer needs to auto-start and stop in the proper phase with graceful shutdown. Should it catch an event or implement `SmartLifecycle`?
8. Why can't you call `context.publishEvent(new ContextRefreshedEvent(context))` to replace `context.refresh()`?
9. What risks can a close listener using `@Async` face while the context/executor is stopping?

**Reference answers:** (1) abstract base of the context lifecycle group, extending `ApplicationEvent`; (2) `start()` was called twice; (3) no, explicit operations are required; (4) the close event is published during the closing procedure; (5) events propagate up to the parent, compare objects via `getApplicationContext()`; (6) no, Boot readiness is later; (7) `SmartLifecycle`; (8) publishing does not run the refresh pipeline; (9) tasks may not finish or dependencies/executor may stop.

## References

- Spring Framework Reference, *Standard and Custom Events / ApplicationContext*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework 6.2 API, *ApplicationContextEvent*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/ApplicationContextEvent.html
- Spring Framework 6.2 API, *ContextRefreshedEvent*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html
- Spring Framework 6.2 API, *AbstractApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework Reference, *Lifecycle Callbacks*: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot Reference, *SpringApplication and Application Events*: https://docs.spring.io/spring-boot/3.4/reference/features/spring-application.html
