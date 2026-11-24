# ContextRefreshedEvent in the Spring ApplicationContext Lifecycle

## 1. What is ContextRefreshedEvent?

`ContextRefreshedEvent` is an event in `org.springframework.context.event`, published by the Spring Framework when an `ApplicationContext` has **completed a successful initialization or refresh operation**. It is one of Spring's standard lifecycle events, allowing components within the same application to react after the container setup phase.

For example: After Spring finishes registering beans, processing configuration, initializing non-lazy singletons, and preparing the lifecycle management system, the application can update an internal cache or record that a specific context has finished refreshing.

Point to distinguish: `ContextRefreshedEvent` is a **Spring container signal**, not by default a signal that all external services are ready or that the entire Spring Boot startup process has completed. For Spring Boot, there are also `ApplicationStartedEvent` and `ApplicationReadyEvent` at separate milestones.

`ContextRefreshedEvent` extends `ApplicationContextEvent`; the source context can be retrieved using `event.getApplicationContext()`. It does not contain information about "which bean just changed" or "which configuration was just updated". Do not use it as a change notification for individual beans.

## 2. At what stage is the event published?

For a typical `AbstractApplicationContext`, calling `refresh()` performs many internal steps. You only need to know the key milestones:

```text
Create / register ApplicationContext
            |
            v
refresh()
  - prepare BeanFactory and BeanPostProcessors
  - create non-lazy singletons, inject dependencies
  - invoke init/@PostConstruct on relevant beans
  - set up LifecycleProcessor; start SmartLifecycle
            |
            v
publishEvent(new ContextRefreshedEvent(this))
            |
            v
Listeners are dispatched
            |
            v
refresh() completes if there are no errors
```

Spring publishes the event during the refresh completion phase (`finishRefresh()`). In the default multicaster mode, listeners run **synchronously** directly during event publication. An overly slow listener or one that throws an exception can slow down or fail `refresh()`/startup, depending on the configured error-handling mechanism.

The event **does not mean**:

- Every time a bean is initialized; lazy beans can still be created late after the event has been published.
- Every time a property value changes; changing a configuration file does not automatically cause the event to appear.
- Every application supports calling `refresh()` repeatedly on the same context: that depends on the `ApplicationContext` type.
- All `CommandLineRunner`, `ApplicationRunner`, and subsequent startup steps of Spring Boot have finished running.

### Comparison with closely related lifecycle events

| Event / callback | Timing or meaning |
| --- | --- |
| `@PostConstruct` | After a bean has dependencies injected and is initialized; tied to the **bean**, not the entire context |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | After regular non-lazy singletons have been instantiated |
| `ContextRefreshedEvent` | Context has finished initializing/refreshing according to the Spring lifecycle |
| `ContextStartedEvent` | When `start()` is called on the context and Spring sends the start event; **not** by default on every application startup |
| `ContextStoppedEvent` | When `stop()` is called on the context |
| `ContextClosedEvent` | When the context is closing via `close()` or the corresponding shutdown mechanism |
| `ApplicationReadyEvent` (Spring Boot) | Spring Boot has run the runners and is about to finish the startup process; more suitable when you need to know Boot is ready to serve |

Note: Spring Boot also has many other events throughout startup. The two groups `Context...Event` from Spring Framework and `Application...Event` from Spring Boot have different purposes and ordering.

## 3. Two ways to register a listener

### Approach 1: @EventListener

Place a method with a `ContextRefreshedEvent` parameter in a Spring-managed bean:

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ContextRefreshLogger {

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        System.out.println("Context refreshed: "
                + event.getApplicationContext().getId());
    }
}
```

This is **a class to drop into an existing Spring application**. Spring finds the `@EventListener` method and invokes it when an event of a compatible type is published. You do not need to call `onRefreshed(...)` manually.

### Approach 2: ApplicationListener<ContextRefreshedEvent>

Use the interface when you want to represent a listener as an object with an explicit interface:

```java
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.stereotype.Component;

@Component
public class ContextRefreshAudit
        implements ApplicationListener<ContextRefreshedEvent> {

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        System.out.println("Refreshed context id="
                + event.getApplicationContext().getId());
    }
}
```

The two snippets above illustrate **two independent options**. If you include **both** in the same application, both listeners receive the event and both print logs. There is no need to register the same task both ways if you only want it to run once.

With `@EventListener`, the bean must be Spring-managed and event listener annotation configuration must be processed. With Spring Boot and most modern Spring configurations using `@Configuration`/component scan, that infrastructure is already set up.

## 4. Runnable Java 17+ example with Spring Framework only

This example creates a context using `AnnotationConfigApplicationContext`, sets a stable identifier, registers a listener via `@Bean`, calls `refresh()`, and finally closes the context. No web server startup is needed.

### Project structure

```text
context-refresh-demo/
├── pom.xml
└── src/main/java/example/lifecycle/ContextRefreshDemo.java
```

### pom.xml

Use JDK 17+, Maven 3.9+, and Spring Framework 6.2.x in the following example (pinned versions for reproducible results):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>context-refresh-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

### ContextRefreshDemo.java

```java
package example.lifecycle;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

public class ContextRefreshDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.setId("demo-context");
            context.register(DemoConfig.class);

            // Initialize beans and publish ContextRefreshedEvent.
            context.refresh();

            System.out.println("ACTIVE: " + context.isActive());
        }
        // try-with-resources calls close(), leading to ContextClosedEvent.
    }

    @Configuration(proxyBeanMethods = false)
    static class DemoConfig {
        @Bean
        ContextHooks contextHooks() {
            return new ContextHooks();
        }
    }

    static class ContextHooks {

        @EventListener
        public void onRefresh(ContextRefreshedEvent event) {
            String id = event.getApplicationContext().getId();
            System.out.println("REFRESHED: " + id);
        }

        @EventListener
        public void onClose(ContextClosedEvent event) {
            String id = event.getApplicationContext().getId();
            System.out.println("CLOSED: " + id);
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.lifecycle.ContextRefreshDemo
```

The lines actively printed by the program in order (if Maven/Spring emit extra logs of their own, they are not part of this output):

```text
REFRESHED: demo-context
ACTIVE: true
CLOSED: demo-context
```

**Explanation of why the output has this order:**

1. `new AnnotationConfigApplicationContext()` creates an **unrefreshed** context; we have time to set `id` and register `DemoConfig`.
2. `context.refresh()` builds the beans, including `ContextHooks`; at the end of this phase Spring publishes `ContextRefreshedEvent` and calls `onRefresh(...)` before `refresh()` returns.
3. The statement `context.isActive()` executes after refresh, so it returns `true`.
4. Upon exiting `try`, `close()` publishes `ContextClosedEvent`; `onClose(...)` prints the final line.

The program intentionally calls `refresh()` **only once**. Do not call it again on `AnnotationConfigApplicationContext` because it is based on `GenericApplicationContext`, which does not support a second refresh on the same instance.

## 5. Practical usage: what should and should not be done in a listener?

Consider `ContextRefreshedEvent` when a component needs to know that a **specific context** has been refreshed, for example:

- Initializing a lightweight cache based on beans already registered in the context.
- Aggregating already-available configuration/runtime information for logging or diagnostics.
- Performing lightweight, explicit, and intentional container state checks.
- Triggering an internal operation designed to re-run safely on context refresh, provided the operation does not depend on Spring Boot's readiness milestone.

Do not use this listener to automatically run heavy tasks or tasks required to run strictly once system-wide, such as irreversible migrations, billing/payments, campaign emails, or uncontrolled bulk data loading. If work needs to run after the Spring Boot application finishes its runners and is ready to serve, consider `ApplicationReadyEvent`. If work needs to run once when a bean has had its dependencies injected, bean initialization mechanisms can be used instead of listening to the entire context.

### Keep the listener method thin

```java
@EventListener
public void onRefreshed(ContextRefreshedEvent event) {
    // Example of delegation, not a standalone program.
    startupDiagnostics.recordContext(event.getApplicationContext());
}
```

The content above is an **illustrative method snippet**, assuming a `startupDiagnostics` bean is already injected. This approach centralizes domain logic and error handling into a testable service.

In the default dispatch mode, a long-running listener prolongs the refresh duration. `@Async` can offload processing to an executor if `@EnableAsync` is enabled and properly configured, but then the asynchronous result is no longer a synchronous part of `refresh()`; errors and the executor lifecycle must be handled separately. Do not add `@Async` merely to hide an oversized initialization step.

## 6. Avoiding duplicate handling in parent/child context hierarchies

Spring can organize multiple `ApplicationContext` instances in a parent–child tree, such as a root context and a separate context for a web component. **Events published in a child context can propagate up to the parent context.** Therefore, a listener in the parent context can receive:

- `ContextRefreshedEvent` published from the parent context itself.
- `ContextRefreshedEvent` published from a child context and forwarded to the parent.

Without checking the source, logic can be triggered multiple times when multiple contexts are created/refreshed. Filtering solely by the `ContextRefreshedEvent` type is not enough to guarantee the event came from the current context.

When a listener must only handle the refresh of the context containing that bean itself, compare the **context object**:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

public class OwnContextRefreshListener {
    private final ApplicationContext ownContext;

    public OwnContextRefreshListener(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return; // Ignore events from other child contexts.
        }

        System.out.println("Own context refreshed");
    }
}
```

This is an **illustrative class**; it needs to be registered as a bean and injected with the context that contains it. Identity comparison `!=` fits the goal "only this exact instance"; comparing `getId()` by string can cause confusion when contexts are given duplicate IDs.

Spring Boot does not assume every application has multiple contexts by default; verify the actual architecture before assuming every listener runs twice.

## 7. Multiple refreshes, multiple startups, and idempotency

Do not interpret `ContextRefreshedEvent` as an "event that occurs only once in the entire system lifecycle". There are many situations:

1. An application creates a new context: each refreshed context has its own event.
2. Some implementations belonging to the **refreshable context** family support repeated refreshes, which can publish the event again.
3. Parent/child contexts have their own events; propagation can cause a listener to observe multiple events.
4. A test suite can create/destroy multiple independent contexts.
5. In Spring Boot, restarting the application creates a new lifecycle, even when startup code has not changed.

Conversely, contexts in the `GenericApplicationContext` family (including `AnnotationConfigApplicationContext`) do not allow calling `refresh()` a second time on the same instance after the first time. Do not write an example that "refreshes one more time" using this class.

If a listener performs an action where running twice is dangerous, clearly define the scope of the requirement:

- **Once per context instance:** choose a state store tied to the context, check the event source, and ensure the operation can complete safely.
- **Once per refresh:** design the operation to allow repetition, avoiding inserting duplicate records/configurations.
- **Once across the entire system including restarts or multiple instances:** persistent state storage, distributed locks, or business idempotency mechanisms are required; a `boolean` field in a bean is not enough.

An `AtomicBoolean` flag only protects a **specific bean instance**. If a refresh recreates the bean, or the application has multiple instances, that flag does not guarantee once-only execution at the system level.

## 8. ContextRefreshedEvent and Spring Boot: do not confuse with ApplicationReadyEvent

In Spring Boot, Spring Framework events are still published when the context refreshes. However, the startup lifecycle also has a step running `ApplicationRunner` and `CommandLineRunner` after refresh. Overview:

```text
Spring Boot prepares and refreshes ApplicationContext
       |
       +--> ContextRefreshedEvent
       |
       +--> ApplicationStartedEvent
       |
       +--> ApplicationRunner / CommandLineRunner
       |
       +--> ApplicationReadyEvent
```

This order describes the typical Spring Boot startup flow; asynchronously configured listeners may finish at different times. Therefore:

- Use `ContextRefreshedEvent` when you care about the **container refreshed** state.
- Use `ApplicationReadyEvent` when you want to react at the milestone where **Boot startup has completed the runners**.
- If you need precise control over the application's traffic-receiving state, use Boot's readiness/availability mechanism instead of relying on a listener's log.
- If handling very early Spring Boot events, account for the possibility that `ApplicationContext` is not yet ready; do not apply that logic backward onto `ContextRefreshedEvent`.

A listener receiving `ContextRefreshedEvent` does not mean all external services such as databases, brokers, or remote endpoints are healthy. For dependencies that can lose connectivity after startup, separate health checks and recovery mechanisms must exist.

## 9. Synchronicity, errors, and listener responsibilities

By default, `SimpleApplicationEventMulticaster` dispatches events by calling them on the event-publishing thread. As a result:

- A listener can slow down `refresh()` or block startup while accessing the network/DB.
- A runtime exception from a synchronous listener can propagate back to the publisher; during refresh, this can cause startup to fail.
- If an executor is configured or `@Async` is attached, distinguish between **submission** errors and errors once the task has started running; asynchronous errors typically do not propagate directly back to the `refresh()` call.
- Do not assume completion order for async listeners, even when `@Order` is used to order dispatch.
- Listeners running during a lifecycle phase must be designed not to depend on a startup callback that occurs **after** refresh.

When heavy post-startup work needs processing, separate it into a job/service capable of progress tracking, timeouts, retries, and controlled shutdown. An event should be a **signal to start work**, not a dumping ground for all processing or a makeshift job queue system.

## 10. Testing behavior properly

### Testing without Spring Boot

The main example in section 4 demonstrated three milestones: publishing refresh, active context, and publishing close. In professional testing, you should not rely solely on `System.out`; replace it with a service that records callback invocations for assertions:

| Scenario | Expectation |
| --- | --- |
| Context created without calling `refresh()` | No `ContextRefreshedEvent` published by that context yet |
| Successful `refresh()` call | Context listener receives exactly one event for that refresh operation, assuming no other event path |
| Calling `close()` after refresh | `ContextClosedEvent` occurs; no new `ContextRefreshedEvent` is automatically generated |
| Listener placed in parent context; child context refreshed | Parent listener may receive the child context's event |
| Listener checks `event.getApplicationContext() != ownContext` | Ignores events from other contexts |
| Calling refresh again on `AnnotationConfigApplicationContext` | Not supported; do not use this operation as a repeated-refresh test |
| Slow listener in synchronous mode | Total refresh time can increase |
| Starting Spring Boot and running runners | `ContextRefreshedEvent` arrives before the `ApplicationReadyEvent` milestone in normal startup |

At a minimum, test: the listener receives the right event type; filtering by source context; the success branch; errors from dependencies; and that re-initializing a context does not produce duplicate side effects. If multi-instance idempotency needs testing, use real storage/locks or an appropriate simulation.

### How to read the event source

Calling `event.getApplicationContext()` returns the event source as `ApplicationContext`. Do not cast to `AnnotationConfigApplicationContext`, `WebApplicationContext`, or a concrete implementation unless the use case truly requires it and you have checked the type. Prefer the general interface; this keeps the listener less coupled to implementation structure.

## 11. Common mistakes and fixes

**Mistake 1 — Using ContextRefreshedEvent instead of @PostConstruct.** If you only need to build internal state in a bean from its own dependencies, use bean initialization mechanisms. Only listen to context refresh when the work depends on a container-wide milestone.

**Mistake 2 — Assuming the event appears only once.** Check the context type, context hierarchy, test lifecycle, and restart possibility; design for safe repeated handling.

**Mistake 3 — Not filtering the source context.** In parent–child hierarchies, a listener in the parent context can also process events from the child. Compare the identity of `getApplicationContext()` against the context owning the bean.

**Mistake 4 — Calling heavy processing directly in the listener.** With default dispatch, the listener sits on the startup path. Move complex logic into an appropriate service, measure timing, and choose an async mechanism or dedicated job when there is a clear need.

**Mistake 5 — Confusing the event with ready-to-serve status.** In Boot, `ApplicationReadyEvent` is a later milestone; readiness/health reflects serving capability better than a startup log.

**Mistake 6 — Registering two listeners for the same task.** `ApplicationListener` and `@EventListener` are both valid; if both call the same service without a guard, the task may run twice.

**Mistake 7 — Calling onRefreshed(event) manually in business code.** Let Spring dispatch the event; if logic needs to be callable from multiple places, extract it into an independent method/service and call that intentionally.

**Mistake 8 — Assuming every bean already exists.** Lazy or prototype beans may not have been created yet at the time the event occurs. "Context refreshed" does not guarantee every bean in every scope has been instantiated.

## 12. Adoption checklist

Before using `ContextRefreshedEvent`, answer:

1. Do I really need the **container refresh** milestone, or do I need bean init / Spring Boot ready?
2. Is the listener Spring-managed and registered properly?
3. Does the application have parent/child contexts or multiple independent contexts?
4. If the event arrives multiple times, is the task idempotent, and at what level?
5. Is the listener logic lightweight enough to run on the refresh thread?
6. If the listener fails, should startup fail or continue? Has a handling path been designed?
7. Are there integration tests for refresh, close, events from child contexts, and restart scenarios?

**Key takeaway:** `ContextRefreshedEvent` is the signal that Spring has completed **a refresh cycle of a specific ApplicationContext**. Use it for work tied to the container lifecycle, check the source context when needed, and design handlers to be safe when events repeat.

## References

- [Spring Framework — Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): events in ApplicationContext and the event lifecycle.
- [Spring Framework API — ContextRefreshedEvent](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html): event class and constructors.
- [Spring Framework API — AbstractApplicationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): refresh and finishRefresh.
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners): Boot startup event ordering.
