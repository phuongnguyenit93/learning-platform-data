# Parent Contexts and Lifecycle Events

In Spring Framework, an application can have multiple `ApplicationContext` instances arranged in a **parent–child** relationship. This relationship affects bean lookup and, in particular, **the path of application events**. A listener registered in the parent can also receive lifecycle events published by a child. If the listener treats every `ContextRefreshedEvent` it receives as the parent's own initialization event, initialization logic may run redundantly or with the wrong scope.

This lesson explains exactly how Spring propagates lifecycle events between contexts, how to identify the context that created an event, how to control listeners, and how to manage the lifecycle of the entire context tree.

## 1. What is a parent–child ApplicationContext?

`ApplicationContext` is the container that manages beans and provides capabilities such as publishing events, accessing resources, and managing lifecycles. A context can declare a parent using `setParent(...)` on implementations that allow configuration, such as `AnnotationConfigApplicationContext`.

Example of a hierarchical structure:

~~~text
Parent ApplicationContext
├── bean: sharedService
├── listener: parentListener
└── Child ApplicationContext
    ├── bean: requestHandler
    └── listener: childListener
~~~

Key points:

- A child can look up beans from the parent if the bean does not exist in the local container and lookup rules permit it. A bean with the same name in the child can shadow a bean in the parent during lookup.
- The parent **does not automatically see beans that exist only in the child**. This relationship does not merge two bean registries into a single shared registry.
- Each context has its own **multicaster** and listener registry. Spring does not require all listeners to belong to the same context.
- Events published by a child are processed in the child and then **propagated up to the parent** inside `AbstractApplicationContext`'s `publishEvent(...)` mechanism. Events published by the parent **do not automatically propagate down to the child**.

Visualizing the event path:

~~~text
                    parentListener
                          ▲
                          │ event from child propagated upward
                 [PARENT CONTEXT]
                          ▲
                          │
                    [CHILD CONTEXT]
                          │
                    childListener

CHILD-sourced event: childListener -> parentListener
PARENT-sourced event: parentListener
~~~

This is the **direction of event propagation**, not the direction of method calls or bean creation order. When there are multiple levels `grandchild → child → parent`, an event from a grandchild can continue traveling up through each ancestor level.

## 2. Standard lifecycle events to distinguish

Spring provides event classes extending `ApplicationContextEvent`:

| Event | Typical cause | Meaning |
| --- | --- | --- |
| `ContextRefreshedEvent` | Context was initialized or `refresh()` succeeded | That container has completed the refresh process |
| `ContextStartedEvent` | Calling `start()` on the context | Context emits a start signal after invoking the corresponding lifecycle mechanism |
| `ContextStoppedEvent` | Calling `stop()` on the context | Context emits a stop signal after executing the corresponding lifecycle step |
| `ContextClosedEvent` | Calling `close()` or completing an appropriate shutdown path | Context closes and publishes the event before finishing resource cleanup |

These events are different:

- `refresh()` builds or refreshes container configuration according to each implementation's capabilities; it **is not synonymous** with `start()`. During refresh, Spring may automatically start eligible `SmartLifecycle` beans; that still does not mean the context must publish `ContextStartedEvent`.
- `start()` and `stop()` invoke `LifecycleProcessor` to coordinate beans implementing the `Lifecycle`/`SmartLifecycle` interfaces. They do not rebuild the container and are not equivalent to closing the context.
- `close()` ends the context lifecycle: besides the event, Spring also performs bean stop/destroy and closes the bean factory. After closing, do not reuse the context as an active container.
- **`ContextRefreshedEvent` is not proof of "running only once in the entire application"**. There can be multiple contexts in a hierarchy and some implementations support multiple refreshes.

All four events hold a reference to the **event-publishing context**, accessible via:

~~~java
ApplicationContext origin = event.getApplicationContext();
~~~

The snippet above assumes `event` is of type `ApplicationContextEvent` and `org.springframework.context.ApplicationContext` is imported. The source context **does not change to the parent** merely because the event was propagated up to the parent.

## 3. Path of lifecycle events in a hierarchy

Suppose there are exactly two contexts: parent `P` and child `C`; each context has a logging listener.

### When refreshing the parent

~~~text
parent.refresh()
    -> P publishes ContextRefreshedEvent(source=P)
    -> P's listener receives 1 time
~~~

The child does not automatically receive events from the parent because Spring does not broadcast downward.

### When refreshing the child

~~~text
child.refresh()
    -> C publishes ContextRefreshedEvent(source=C)
    -> C's listener receives it
    -> AbstractApplicationContext propagates event up to parent P
    -> P's listener also receives event source=C
~~~

Therefore, **a parent listener can receive `ContextRefreshedEvent` at least twice** in a parent-then-child initialization sequence: first from the parent, next from the child. These are two valid events from **two different contexts**.

The same mechanism applies to `ContextStartedEvent`, `ContextStoppedEvent`, and `ContextClosedEvent` when each context actually publishes them. Do not infer that every event a parent listener sees describes the parent's own lifecycle.

### Two concepts easily confused

- **Where is the listener registered?** Parent has the parent's listener registry; child has the child's listener registry.
- **Which context did the event originate from?** Check `event.getApplicationContext()` (and optionally `getId()` for logging). The location where a listener is invoked **does not by itself determine** the source context.

If the exact same listener instance is manually registered in **both child and parent**, an event from the child can cause that same instance to be invoked from two different registries. Filtering by source context helps distinguish the origin, but does not by itself resolve duplicate registration of one instance across multiple multicasters.

## 4. Standalone runnable Java 17+ demo

This example uses only `spring-context`: no Spring Boot, servlets, or database required. Each context registers an `ApplicationListener<ApplicationContextEvent>` listener to print the event name and source context.

Structure:

~~~text
context-event-hierarchy/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ContextHierarchyDemo.java
~~~

Create `settings.gradle`:

~~~groovy
rootProject.name = 'context-event-hierarchy'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.ContextHierarchyDemo'
}
~~~

Create `src/main/java/demo/ContextHierarchyDemo.java`:

~~~java
package demo;

import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ApplicationContextEvent;

public final class ContextHierarchyDemo {

    static final class LifecycleLogger
            implements ApplicationListener<ApplicationContextEvent> {

        private final String registeredAt;

        LifecycleLogger(String registeredAt) {
            this.registeredAt = registeredAt;
        }

        @Override
        public void onApplicationEvent(ApplicationContextEvent event) {
            String name = event.getClass().getSimpleName();
            String origin = event.getApplicationContext().getId();

            System.out.println(
                registeredAt + " <- " + name + " @ " + origin
            );
        }
    }

    public static void main(String[] args) {
        // Register listeners before refresh to observe lifecycle events.
        try (var parent = new AnnotationConfigApplicationContext()) {
            parent.setId("parent");
            parent.addApplicationListener(
                new LifecycleLogger("P")
            );
            parent.refresh();

            try (var child = new AnnotationConfigApplicationContext()) {
                child.setId("child");
                child.setParent(parent);
                child.addApplicationListener(
                    new LifecycleLogger("C")
                );

                child.refresh();
                child.start();
                child.stop();
            } // child.close(): publishes child's ContextClosedEvent
        }     // parent.close(): publishes parent's ContextClosedEvent
    }
}
~~~

Run with Java 17+ and Gradle:

~~~bash
gradle run --quiet
# Or use an existing Gradle Wrapper: ./gradlew run --quiet
# On Windows: gradlew.bat run --quiet
~~~

With the listeners registered above and the default synchronous multicaster, lines printed by `System.out.println` appear in order:

~~~text
P <- ContextRefreshedEvent @ parent
C <- ContextRefreshedEvent @ child
P <- ContextRefreshedEvent @ child
C <- ContextStartedEvent @ child
P <- ContextStartedEvent @ child
C <- ContextStoppedEvent @ child
P <- ContextStoppedEvent @ child
C <- ContextClosedEvent @ child
P <- ContextClosedEvent @ child
P <- ContextClosedEvent @ parent
~~~

Output explanation:

1. Parent is refreshed first, so **only P** receives the `parent`-sourced event.
2. Child refreshes afterward: **C** receives the `child`-sourced event; this same event propagates up to parent, so **P** also receives it. This is the usual reason a parent sees multiple `ContextRefreshedEvent`s.
3. `child.start()` and `child.stop()` create events with source `child`. Each event is handled in child and then in parent.
4. When the inner try block ends, `child.close()` produces the child's `ContextClosedEvent`; P sees that event too.
5. When the outer try block ends, `parent.close()` produces the parent's `ContextClosedEvent`. No child listener receives this event.

**Important observation:** the line `P <- ContextClosedEvent @ child` does not mean the parent has closed; it only indicates **the parent's listener received notice that the child closed**. The parent continues operating until the parent itself is closed.

The demo data contains only listeners and container mechanisms, so no business beans alter the logs. If a custom multicaster with an executor or async listeners is configured, callback execution order may differ. This example uses the synchronous default for clear observation.

## 5. How to make a listener react only to the lifecycle of its owning context?

In practice, a parent listener might want to initialize a cache or scheduler **only when the parent refreshes**, not when any child refreshes.

The most reliable check is comparing **the context object itself**, not counting event occurrences:

~~~java
// Illustrative snippet: place listener inside a bean managed by parent.
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ParentInitializationHandler implements ApplicationContextAware {

    private ApplicationContext owningContext;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.owningContext = context;
    }

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != owningContext) {
            return; // Child's event: parent received it via propagation.
        }

        // Initialize resources tied to owningContext itself here.
        System.out.println("own context refreshed");
    }
}
~~~

This code illustrates a **Spring component** that must be placed in the context to be managed (e.g., parent) and component-scanned; it is not a standalone runnable file. `ApplicationContextAware` lets the bean know which container actually manages it. When an event arrives, compare references using `!=` or `==`.

A variant without `ApplicationContextAware` is injecting the context into the listener's constructor and checking `event.getApplicationContext() == injectedContext`; the precondition is that the injected object is the exact context owning the listener.

### Why not just compare class names or rely on execution count?

- Two contexts can both be `AnnotationConfigApplicationContext` yet represent two distinct containers.
- IDs like `"parent"` and `"child"` are helpful for logs, but object comparison avoids depending on ID-naming conventions. If using IDs, you must ensure IDs are configured uniquely across the system.
- Using `boolean initialized` to skip the second event can mask deployment bugs, miss valid refreshes, or depend on startup order.
- Filtering by event class (`ContextRefreshedEvent`) is still insufficient: parent and child publish **the exact same event class**.

If you want to handle **both parent and child**, do not use this filter condition; instead classify `event.getApplicationContext()` explicitly and ensure operations are safely repeatable (*idempotent*) when needed.

## 6. Bean visibility differs from event propagation

From a child, you can look up a parent's bean:

~~~java
// Illustrative in code with initialized parent and child:
SharedService service = child.getBean(SharedService.class);
~~~

This does not mean events in the parent will be sent to listeners in the child. Bean lookup and event routing are **two different mechanisms**.

In Spring MVC with a multi-context configuration, an application can have a root context for shared services and a child context for each `DispatcherServlet`. A child's `ContextRefreshedEvent` can reach a listener in root. Simple Spring Boot applications may use only a single context; do not assume every application has a root–child hierarchy.

Another scenario is an application creating multiple children under the same parent:

~~~text
          ROOT context
          /          \
      CHILD A       CHILD B
~~~

- Events published from A can reach listeners of A and root; **they do not automatically propagate sideways to B**.
- Events published from B can reach listeners of B and root; **they do not automatically propagate sideways to A**.
- Root listeners can observe events from both A and B. Distinguish the source using `getApplicationContext()` when needed.

This is an important point when a root context aggregates logs, metrics, or performs application-level operations.

## 7. Do start, stop, and close propagate automatically across parent–child relationships?

**Event propagation does not mean lifecycle orchestration.** When calling `child.start()`:

- Spring runs the **child's** `LifecycleProcessor` mechanism, coordinating lifecycle beans inside the child.
- Child publishes `ContextStartedEvent`; parent listeners can receive the event because the event travels upward.
- The upward event **does not mean** Spring just called `parent.start()` or restarted the parent's lifecycle beans.

The same applies to `child.stop()` and `child.close()`. Parent observes child events without automatically stopping or closing along with it.

When creating a hierarchy in code, **initialize parent before child and close child before parent** as in the demo. The parent reference relationship in `ApplicationContext` is not by itself a contract managing the entire shutdown process of all descendants. If an external framework/container manages both, follow that framework's lifecycle; if building contexts manually, manage each context proactively.

Do not try to `refresh()` an already refreshed/closed `GenericApplicationContext` to replay events: multi-refresh capability depends on the context type. If work needs to run after every startup, choose an appropriate lifecycle API and design idempotently.

## 8. Choosing the right hook for business goals

| Goal | Hook to consider | Notes |
| --- | --- | --- |
| Initialize a single bean's own state | Constructor / `InitializingBean` / `@PostConstruct` | No need to observe all contexts; runs per bean lifecycle |
| Run after context finishes refreshing | `ContextRefreshedEvent` + context filtering | Parent can see child events; listener must know source |
| Coordinate starting/stopping resources | `Lifecycle` / `SmartLifecycle` | Managed by `LifecycleProcessor`; has phases and start/stop coordination |
| Clean up when container closes | `@PreDestroy` / `DisposableBean` | Bean-scoped cleanup; does not depend on receiving child events |
| Observe closing state of multiple contexts | `ContextClosedEvent` in root listener | Use event source to distinguish which context closed |
| Run after Spring Boot app is ready to serve | Boot-level application events, e.g., `ApplicationReadyEvent` | Belongs to Spring Boot, not synonymous with Spring Framework's `ContextRefreshedEvent` |

Common mistake example:

~~~java
@EventListener(ContextRefreshedEvent.class)
public void warmUpCache(ContextRefreshedEvent event) {
    // If bean is in parent, this may run for a child's event.
    warmUpEverything();
}
~~~

Add the condition `"event.getApplicationContext() == owningContext"` if the cache belongs to one context only. The illustrative snippet above needs surrounding methods, imports, and beans; it is not a standalone program.

## 9. Common bugs and how to verify

**Bug 1: Parent listener runs twice after startup.** Check logs for `event.getClass().getSimpleName()` and `event.getApplicationContext().getId()`. If once from parent and once from child, this is valid propagation; add filtering by owning context if only one source is desired.

**Bug 2: Expecting a child listener to receive parent events.** Spring dispatches events upward by default. To notify a child, proactively publish events into the child context or build an explicit coordination channel. Do not rely on bean visibility.

**Bug 3: Confusing "parent received ContextClosedEvent" with "parent has shut down".** Check `getApplicationContext()`: the event may have originated from a child, while the parent is still running.

**Bug 4: Registering one listener instance in both multicasters.** Investigate listener registration sites and avoid adding the same instance unintentionally. When needed, separate listeners per context or ensure idempotent handling; source filtering alone may not resolve duplicate calls if the same instance is present in both registries.

**Bug 5: Using `ContextRefreshedEvent` instead of `SmartLifecycle` for work needing stop/start.** Distinguish refresh, start, stop, and close timing. Do not use the refresh event to simulate the full bean lifecycle mechanism.

**Bug 6: Writing tests dependent on logs or async ordering.** If routing needs verification, register a listener collecting events into a thread-safe collection, create parent and child in an explicit order, and assert **event class + source context**. Only assert dispatch order when a known synchronous multicaster configuration is used.

### Short testing checklist

1. Refresh parent and verify the parent listener receives `ContextRefreshedEvent(source=parent)`.
2. Refresh child and verify the child listener receives event `source=child`; parent also receives event `source=child`.
3. Call `child.start()`, `child.stop()`, then `child.close()`, verifying parent observes the child's events while the events preserve their source context.
4. Close parent last, verifying the child listener does not automatically receive the parent's close event.
5. If adding a parent-only listener, test the condition `event.getApplicationContext() == owningContext` with both sources.

## 10. Mechanism summary

~~~text
Parent–child relationship:
  Bean lookup: child -> parent (when needed)
  Event propagation: child -> parent
  Event parent -> child: not automatic

Lifecycle events:
  ContextRefreshedEvent : refresh completed
  ContextStartedEvent   : start
  ContextStoppedEvent   : stop
  ContextClosedEvent    : close

Listener in parent receiving child event:
  getApplicationContext() == child
  -> parent observes child's event; parent has not necessarily changed state

Handle only own context's lifecycle:
  event.getApplicationContext() == owningContext
~~~

## References

- [Spring Framework 6.2 — Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [AbstractApplicationContext — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [ApplicationContextEvent — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/event/ApplicationContextEvent.html)
- [Spring Framework source — AbstractApplicationContext.publishEvent()](https://github.com/spring-projects/spring-framework/blob/6.2.x/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java)
