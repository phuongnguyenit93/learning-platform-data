# Event Propagation from Child to Parent Context and Filtering by Context in Spring Boot

## 1. Why Can a Listener Handle the Same Event Type Multiple Times?

A Spring application usually has only one `ApplicationContext`. However, Spring Framework and Spring Boot allow building a **context tree**: a child context has a `parent`, and the parent context can itself have another parent. Each context manages its own beans, listeners, and event sources.

When an event is **published from a child context**, Spring Framework does not only notify listeners inside that child context. Under `AbstractApplicationContext`'s standard mechanism, it also forwards the event **up to the parent context and onward to ancestors**. Therefore, a listener placed in the parent context can receive:

- Events originating from **the parent context itself**.
- Events of the same type originating from **a child context**.
- Events from **grandchildren/descendants** at deeper levels, if they belong to its child subtree.

A listener that does not distinguish the source can execute side effects multiple times: loading caches twice, running migrations repeatedly, sending a notification twice, registering duplicate resources, or reporting inaccurate metrics.

Typical example: a parent context contains a listener catching `ContextRefreshedEvent`. The parent refreshes, and the listener receives the `parent` event. Then a child context refreshes, Spring forwards the `child` event up to the parent, and **the parent listener is invoked again**. If the listener follows "whenever I see ContextRefreshedEvent, run once for the system," the result can be wrong.

**The most important filter for context lifecycle events:** compare the **identity** of the event-emitting context against the context owning the listener:

```java
if (event.getApplicationContext() != ownContext) {
    return;
}
```

Here `ownContext` is **the exact `ApplicationContext` injected into that context's listener**, not a randomly grabbed parent, not a global context variable, and not a string name.

This lesson applies to **Spring Framework 6.1.x, Spring Boot 3.3.x, and Java 17+**; the hands-on section uses standard contexts so propagation behavior is clearly observable.

## 2. Understanding the ApplicationContext Tree Properly

A minimal context tree:

```text
                  ROOT / PARENT
                 ApplicationContext
                 listeners: P, P2
                        |
           +------------+-------------+
           |                          |
       CHILD-A                    CHILD-B
   ApplicationContext          ApplicationContext
   listeners: A                listeners: B
           |                          |
       GRANDCHILD                 (no children)
       listeners: G
```

When `CHILD-A.publishEvent(event)` runs:

```text
CHILD-A listeners
       |
       v
PARENT listeners
       |
       v
ROOT listeners (if parent also has a parent)
```

When `GRANDCHILD.publishEvent(event)` runs, the event travels `GRANDCHILD → CHILD-A → PARENT → ROOT`. However, `CHILD-B` is a **sibling** branch not on that path, so it **does not automatically receive** events from `CHILD-A`. Likewise, when the parent publishes, events **do not automatically propagate down to children**.

This is an **emit within current context then forward up to ancestors** model, not a bidirectional broadcast across the entire tree.

### 2.1. "Can See Parent Beans" Differs from "Receives Parent Events"

A child context can usually look up beans from its parent context via parent BeanFactory delegation. That **does not mean** listeners in the child context automatically receive events emitted in the parent.

| Relationship | Typical behavior |
| --- | --- |
| Child looks up a bean from parent | Possible, if compatible and not shadowed by a child bean. |
| Parent automatically looks up a bean existing only in child | Not via normal lookup. |
| Event published by child reaches parent listener | **Yes**, under standard `AbstractApplicationContext` behavior. |
| Event published by parent reaches child listener | **Not automatically**. |
| Event in child A reaches listener in child B (two children of same parent) | **Not automatically**; only ancestors receive it. |
| A listener exists in both parent and child | May handle events multiple times depending on registration and propagation paths. |

Do not infer event propagation from dependency injection visibility. Both mechanisms involve context hierarchy, yet they follow different directions and rules.

## 3. Mechanism of AbstractApplicationContext.publishEvent

`ApplicationEventPublisher.publishEvent(...)` is the starting point. `ApplicationContext` normally implements this interface; you can publish an `ApplicationEvent` or an ordinary payload object.

In `AbstractApplicationContext`, the conceptual flow is:

1. Accept the event; if it is a plain payload, wrap it in a `PayloadApplicationEvent` if needed.
2. Determine the event type so matching listeners are invoked.
3. Dispatch the event to the **current context's** `ApplicationEventMulticaster`, or queue it early if still in an initialization phase before multicasting is ready.
4. If a parent exists, also publish the event **to the parent context** via the framework's mechanism.
5. Repeat up through further ancestors if present.

```text
child.publishEvent(event)
         |
         +--> child.applicationEventMulticaster
         |           |
         |           +--> listener in child
         |
         +--> parent.publishEvent(event)
                     |
                     +--> parent.applicationEventMulticaster
                     |           |
                     |           +--> listener in parent
                     |
                     +--> grandparent.publishEvent(event)
                                   |
                                   +--> listener in grandparent
```

For an already-constructed `ApplicationEvent`, **the source/origin recorded inside the event is not automatically rewritten to the parent context** just because it is being forwarded upward. Thus a parent listener can receive a `ContextRefreshedEvent` whose `event.getApplicationContext()` **still returns child**.

### 3.1. Important Rule: Propagation Follows the Publishing Path, Not the Listener Class

Whether a parent listener receives an event also depends on:

- Whether the event was published via a child context / matching ancestor chain.
- Whether the listener is registered in the parent context.
- Whether the listener supports the published **event type**.
- Whether `@EventListener(condition=...)`, filters, `@Order`, or a custom multicaster applies.
- Whether the listener is synchronous or asynchronous, or uses error handlers / transaction bindings.

**Merely defining a listener class in a shared module does not mean events arrive there.** You must check which context actually holds the listener bean, the event type, and the publishing path.

### 3.2. This Is Not an Inter-Process Delivery Guarantee

Spring application events are an **in-process** mechanism. Parent and child in these examples live inside the same JVM process. They do not automatically publish over Kafka, RabbitMQ, HTTP, Kubernetes, or between two pods. When cross-service event delivery is required, use messaging/APIs/distributed systems with proper retry, idempotency, and delivery contracts.

## 4. Why Does Spring Boot Warn About Receiving Multiple Events?

Spring Boot documentation explicitly notes that events in a child context are published to listeners in ancestors. When an application uses a **`SpringApplication` hierarchy**, a listener in the parent can receive multiple events **of the same type**.

Example:

```text
Parent SpringApplication completes refresh
     |
     +--> ContextRefreshedEvent(parent) --> ParentListener

Child SpringApplication completes refresh
     |
     +--> ContextRefreshedEvent(child)  --> ChildListener
                                |
                                +----> ParentListener
```

The parent listener **is not necessarily registered twice**. It can be registered just once and still handle **two distinct events**: one for parent, one for child. This is a common reason developers mistake propagation for duplicate listener registration.

Distinguish clearly:

- **Multiple valid events:** parent refresh and child refresh each emit their own separate event.
- **One event handled by multiple listeners:** the child event passes through child and then ancestor listeners.
- **Same logic receiving events multiple times:** may be due to the listener existing in multiple contexts, or one parent listener receiving events from multiple contexts.
- **Same listener registered twice in the same context:** a separate issue; inspect registration configuration.

Log counts alone cannot reveal the root cause; log **event context identity** and **listener owner context identity**.

## 5. Choosing What Object Serves as the "Event Origin"

This is the core of filtering.

### 5.1. Events Extending ApplicationContextEvent

Spring Framework lifecycle events such as:

- `ContextRefreshedEvent`
- `ContextStartedEvent`
- `ContextStoppedEvent`
- `ContextClosedEvent`

all belong to the `ApplicationContextEvent` family and provide:

```java
ApplicationContext origin = event.getApplicationContext();
```

This value identifies **the context the event describes**—for example, the context that just refreshed or is closing. For an event propagated from child to parent, it remains child.

**Correct filter:**

```java
if (event.getApplicationContext() != ownContext) {
    return;
}
```

Use `!=`/`==` to compare **the context object itself**. Do not compare class names (both may be `AnnotationConfigApplicationContext`), do not rely solely on `getId()` (IDs can be configured identically), and do not merely check whether a parent exists.

### 5.2. Certain Spring Boot Events

Many post-context events expose `getApplicationContext()`, such as `ApplicationStartedEvent` and `ApplicationReadyEvent`. For those events, you can filter using **the context provided by the event**, consistent with each event's contract.

However, very early Boot events like `ApplicationStartingEvent`/`ApplicationEnvironmentPreparedEvent` occur before the application context is ready, so a `getApplicationContext()` recipe cannot be applied to **every** Boot event. Listeners for very early events must also be registered before the bean container is built.

### 5.3. Custom Business Events You Define Yourself

A custom `ApplicationEvent` may pass an entity ID, a service, a string, or the publisher itself to `getSource()`; Spring **does not automatically supply a `getApplicationContext()` method on all custom events**.

Example:

```java
public final class PaymentSubmittedEvent extends ApplicationEvent {
    private final ApplicationContext originContext;
    private final String paymentId;

    public PaymentSubmittedEvent(ApplicationContext originContext,
                                 String paymentId) {
        super(originContext);
        this.originContext = originContext;
        this.paymentId = paymentId;
    }

    public ApplicationContext originContext() {
        return originContext;
    }

    public String paymentId() {
        return paymentId;
    }
}
```

The snippet above is an **illustrative class in a Spring project**; it requires importing `ApplicationEvent` and `ApplicationContext` and placing it in a matching file or nested class. It adds `originContext` metadata **by application design**. Such events can be filtered via `event.originContext() == ownContext`, yet **you must not blindly apply that rule to every other event type**.

**Caution:** holding a direct `ApplicationContext` reference inside a domain event is suitable only for in-process/diagnostic examples. In real messaging systems, carry a meaningful **context/component identifier** or tenant/aggregate ID—never serialize an entire `ApplicationContext`.

### 5.4. Do Not Arbitrarily Rely on getSource() of Payload Events

When publishing an object that does not extend `ApplicationEvent`, Spring can wrap it in `PayloadApplicationEvent`. The wrapper's `source` is an implementation detail tied to the context creating the wrapper; during propagation, wrappers may be created at different levels. Therefore, to identify the **business origin**, place explicit metadata inside the payload instead of assuming `event.getSource()` on every wrapper always points to the original publisher.

## 6. How to Filter by Context Properly in a Spring Bean Listener

Inside a context-managed bean, you can obtain its `ApplicationContext` via constructor injection or `ApplicationContextAware`.

**Example using constructor injection:**

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OwnContextRefreshListener {

    private final ApplicationContext ownContext;

    public OwnContextRefreshListener(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        System.out.println("My context refreshed: " + ownContext.getId());
    }
}
```

This is a **complete Java class** when the project has a Spring context and component scanning covers the package. When the bean resides in the parent context, it is injected with **the parent context**; when in a child context, it is injected with **the corresponding child context**.

When the child refreshes, the parent listener may be invoked, yet `event.getApplicationContext() != ownContext` causes it to **ignore** the child's event. For the parent's own event, the check passes and the listener executes.

### 6.1. Using ApplicationContextAware

If you want to show Spring's aware hook explicitly:

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OwnContextCloseListener implements ApplicationContextAware {

    private ApplicationContext ownContext;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.ownContext = context;
    }

    @EventListener
    public void onClosed(ContextClosedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        System.out.println("Closing own context: " + ownContext.getId());
    }
}
```

This is a **standalone class file** in the same package. Spring calls `setApplicationContext` when the bean is created, before normal close events. The guard prevents a parent listener from running cleanup merely because a **child** is closing.

Never call `setApplicationContext(...)` directly in business code; it is a container-managed callback.

### 6.2. Should You Use @EventListener(condition=...)?

`@EventListener(condition=...)` supports SpEL for filtering by payload/properties. However, for comparing **context identity** against the injected context, a Java guard is usually clearer, type-safe, and easier to unit test:

```java
@EventListener
public void onRefreshed(ContextRefreshedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return;
    }
    // Action dedicated to this context only.
}
```

This is an illustrative method inside a bean that already has `ownContext`. There is no need to write a complex SpEL expression just to replace a direct object reference check.

## 7. Runnable Example: One Parent, One Child, Two Types of Listeners

To verify the behavior, we use **Spring Framework contexts** directly: `AnnotationConfigApplicationContext`. They are included in the libraries pulled in by `spring-boot-starter`, so they run inside a **Spring Boot 3.3.x + Java 17+** project.

The example does not call `SpringApplication.run(...)`, because the goal is to observe **Spring Framework's event hierarchy** without mixing in Boot bootstrap events or auto-configuration. Events still follow the exact rules Boot uses when building parent/child contexts.

**Complete file:** `src/main/java/com/example/hierarchy/ContextPropagationDemo.java`

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;

public class ContextPropagationDemo {

    public static void main(String[] args) {
        AnnotationConfigApplicationContext parent =
                new AnnotationConfigApplicationContext();
        parent.setId("parent");

        // Listener 1: parent wants to log every context refresh in the branch.
        parent.addApplicationListener(
                new RefreshTrace("PARENT_ALL", parent, false));

        // Listener 2: parent wants to handle only its own refresh.
        parent.addApplicationListener(
                new RefreshTrace("PARENT_OWN", parent, true));

        // Business listener: parent also receives events from child.
        parent.addApplicationListener(
                new OrderTrace("PARENT_ALL", parent, false));

        parent.refresh();

        AnnotationConfigApplicationContext child =
                new AnnotationConfigApplicationContext();
        child.setId("child");
        child.setParent(parent);

        // Child listener handles only child's own refresh.
        child.addApplicationListener(
                new RefreshTrace("CHILD_OWN", child, true));

        // Child listener handles only child's own business events.
        child.addApplicationListener(
                new OrderTrace("CHILD_OWN", child, true));

        try {
            child.refresh();

            child.publishEvent(new OrderPlaced(child, "A-42"));
            parent.publishEvent(new OrderPlaced(parent, "P-1"));
        } finally {
            child.close();
            parent.close();
        }
    }

    static final class RefreshTrace
            implements ApplicationListener<ContextRefreshedEvent> {

        private final String label;
        private final ApplicationContext owner;
        private final boolean ownOnly;

        RefreshTrace(String label, ApplicationContext owner,
                     boolean ownOnly) {
            this.label = label;
            this.owner = owner;
            this.ownOnly = ownOnly;
        }

        @Override
        public void onApplicationEvent(ContextRefreshedEvent event) {
            ApplicationContext origin = event.getApplicationContext();
            if (ownOnly && origin != owner) {
                return;
            }
            System.out.println(label + " refresh origin=" + origin.getId());
        }
    }

    static final class OrderPlaced extends ApplicationEvent {

        private final ApplicationContext originContext;
        private final String orderId;

        OrderPlaced(ApplicationContext originContext, String orderId) {
            super(originContext);
            this.originContext = originContext;
            this.orderId = orderId;
        }

        ApplicationContext originContext() {
            return originContext;
        }

        String orderId() {
            return orderId;
        }
    }

    static final class OrderTrace
            implements ApplicationListener<OrderPlaced> {

        private final String label;
        private final ApplicationContext owner;
        private final boolean ownOnly;

        OrderTrace(String label, ApplicationContext owner, boolean ownOnly) {
            this.label = label;
            this.owner = owner;
            this.ownOnly = ownOnly;
        }

        @Override
        public void onApplicationEvent(OrderPlaced event) {
            ApplicationContext origin = event.originContext();
            if (ownOnly && origin != owner) {
                return;
            }
            System.out.println(label + " order origin=" + origin.getId()
                    + " id=" + event.orderId());
        }
    }
}
```

### 7.1. Details That Make the Example Accurate

- `parent.refresh()` runs first, so parent has a multicaster and can receive child events afterward.
- `child.setParent(parent)` is called **before `child.refresh()`**, defining the propagation path.
- Both `RefreshTrace` and `OrderTrace` implement `ApplicationListener` with **concrete generic event types**, so Spring accurately classifies which events to dispatch. Avoid registering raw lambda listeners with unclear event types and unsafe casts.
- `ownOnly` is the listener's business policy, **not** an automatic framework feature. When `false`, the parent handles events from descendants; when `true`, it handles only events whose origin matches its owning context.
- `OrderPlaced` exposes `originContext()` explicitly; do not rely on any implicit rule that all custom events carry an origin.
- `finally` closes **child before parent**, matching the dependency hierarchy. `close` also emits `ContextClosedEvent`, yet the example registers no listener for that event type, so the output below contains no close logs.
- In this program, both parent and child are `AnnotationConfigApplicationContext`, so comparing context **classes** cannot distinguish the source; comparing **object identity** is exact.

### 7.2. Run Configuration

In a project declaring Spring Boot plugin 3.3.x and Java 17+, the starter dependency suffices for the Spring context:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

This snippet is the **`dependencies` section** of `build.gradle`; if using Maven, add the equivalent starter in `pom.xml`. The project needs a Gradle Wrapper or compatible Gradle installation.

To specify the main class used by the `bootRun` task, configure in `build.gradle`:

```groovy
springBoot {
    mainClass = 'com.example.hierarchy.ContextPropagationDemo'
}
```

Then run:

```bash
./gradlew bootRun
```

On Windows CMD use `gradlew.bat bootRun`; on PowerShell use `.\gradlew.bat bootRun`. When testing in plain Java without applying the Boot plugin, you can use Gradle's `application` plugin with the corresponding main class.

### 7.3. Program Output

When using the default `SimpleApplicationEventMulticaster` (synchronous execution) and only the example's listeners are registered, the expected self-printed lines are:

```text
PARENT_ALL refresh origin=parent
PARENT_OWN refresh origin=parent
CHILD_OWN refresh origin=child
PARENT_ALL refresh origin=child
CHILD_OWN order origin=child id=A-42
PARENT_ALL order origin=child id=A-42
PARENT_ALL order origin=parent id=P-1
```

The most important line is:

```text
PARENT_ALL refresh origin=child
```

It proves **a listener belonging to parent receives `ContextRefreshedEvent` emitted by child**. Listener `PARENT_OWN` **does not** print for child's refresh because the `origin != owner` guard skipped it.

The business event `OrderPlaced(child, "A-42")` is handled by child first and then parent in the synchronous model, whereas `OrderPlaced(parent, "P-1")` **does not** propagate down to child. Thus there is no `CHILD_OWN order origin=parent` line.

**Output limitation:** the lines above are logs printed by the sample code itself. If you switch to a custom async multicaster, add listeners, or change topology, do not rely on global log order as a transactional guarantee. Origin semantics and filter conditions must still be verified against the event contract.

## 8. Building a Hierarchy in Real Spring Boot Applications

When a real application uses `SpringApplication` instead of constructing contexts manually, Spring Boot provides `SpringApplicationBuilder`:

```java
new SpringApplicationBuilder(ParentConfig.class)
        .child(ChildConfig.class)
        .run(args);
```

This is a **snippet inside `main`**, assuming `ParentConfig` and `ChildConfig` are real Spring configuration classes and importing `org.springframework.boot.builder.SpringApplicationBuilder`. When both configurations should run as non-web applications, configure `WebApplicationType.NONE` and appropriate dependencies for each context.

A system might have:

- Parent holding shared config/beans: audit, registry, metrics, shared services.
- Child holding isolated API, tenant, plugin, or workstream logic.
- Parent listeners monitoring events across multiple children.
- Dedicated listeners in each child handling only its own events.

Spring Boot **does not force** every microservice to use a context hierarchy; most services have a single context. Create a hierarchy only when you have a genuine need to isolate lifecycles/bean scopes and have weighed the added complexity.

### 8.1. A Context Hierarchy Is Not the Same as Maven/Gradle Modules

Multiple modules in a build project do not automatically create multiple `ApplicationContext` instances. If all code ends up in one `SpringApplication`, there may still be only a single context.

Conversely, a single JVM or test can create multiple contexts even when all source code sits in one module. Check `context.getParent()` and actual context identity—never infer from module or package counts.

## 9. Using @EventListener Properly with Parent-Child Contexts

`@EventListener` on a bean operates through the event multicaster of the context that owns that bean. It does not automatically restrict itself to events originating only from that context. Example parent listener:

```java
@Component
public class CacheWarmupListener {

    private final ApplicationContext ownContext;
    private final CacheService cacheService;

    public CacheWarmupListener(ApplicationContext ownContext,
                               CacheService cacheService) {
        this.ownContext = ownContext;
        this.cacheService = cacheService;
    }

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        cacheService.loadOnceForContext();
    }
}
```

This is an **illustrative snippet** in a project with `CacheService` and imports for `@Component`, `@EventListener`, `ApplicationContext`, and `ContextRefreshedEvent`. It is not a standalone program without `CacheService`.

Without the guard, the parent bean could invoke `loadOnceForContext()` on every child refresh. With the guard, it runs only for the parent itself. For loading large datasets or work that must finish before `ApplicationReadyEvent`, consider `ApplicationRunner` and readiness checks rather than doing heavy business work inside refresh events.

### 9.1. What If You Intentionally Want to Monitor All Children?

Yes. Not every parent listener has to filter out child events. For example, parent audit/telemetry may **intentionally** observe all descendants:

```java
@EventListener
void observe(ContextRefreshedEvent event) {
    System.out.println("Refreshed context: "
            + event.getApplicationContext().getId());
}
```

This is an illustrative method on a parent bean. The `event.getApplicationContext() != ownContext` check applies only when the requirement is **own-only**. If the requirement is **aggregate monitoring**, do not filter away valuable child events.

Best practice is naming/making the policy explicit—`ownContextOnly`, `allDescendants`, or `allowedContexts`—rather than silently dropping some events.

## 10. ContextClosedEvent: Duplicate Cleanup Is More Dangerous Than Duplicate Logs

Real-world scenario: a parent listener receives a child's `ContextClosedEvent` and accidentally closes a shared connection/database pool still used by the parent and other children.

Dangerous example:

```java
@EventListener
void onClosed(ContextClosedEvent event) {
    sharedResource.close();
}
```

This is a snippet in a parent bean assuming `sharedResource` has a `close()` method. Whenever **any child closes**, the parent listener can be invoked; that does not mean the parent itself is closing.

How to filter when the resource belongs to the parent:

```java
@EventListener
void onClosed(ContextClosedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return;
    }
    sharedResource.close();
}
```

However, if `sharedResource` is a **Spring-managed bean**, its own destroy method/`@PreDestroy`/`DisposableBean` or `SmartLifecycle` is usually the **proper place** to manage shutdown instead of closing manually in an event listener. Avoid both closing in a listener and letting the container destroy the same resource a second time.

### 10.1. Closing in the Right Order

When the parent owns shared dependencies, normally stop/close **children before the parent**. Closing the parent first while children are still running can leave children using beans/resources already destroyed by the parent.

The parent/child mechanism is not an all-powerful orchestrator guaranteeing every resource closes in the desired sequence. When you create multiple contexts yourself, own the lifecycle sequence explicitly.

## 11. When Is Filtering Unnecessary or Needs Different Logic?

### 11.1. Counting Every Child Refresh

A parent listener may intentionally record metrics for every `ContextRefreshedEvent` across the tree. In that case, the event's context is a metric **label/tag**, not a reason to skip. Use stable IDs/labels compatible with your metrics system, avoiding unbounded cardinality from random IDs.

### 11.2. Listening to Only One Specific Child

Comparing against owner alone is not enough; write a predicate matching the requirement:

```java
if (event.getApplicationContext() != targetChildContext) {
    return;
}
```

This is valid if you genuinely hold a reference to `targetChildContext`. If children can be recreated, identity references change; design a way to discover/register new children rather than holding stale references forever.

### 11.3. Distinguishing Tenants/Workspaces in Custom Events

Do not use context object identity as a stand-in for tenant ID in domain logic. One context may serve many tenants, or multiple contexts may handle one tenant over time. Put `tenantId`, `aggregateId`, `requestId`, or `correlationId` inside the event and filter by **business** meaning.

### 11.4. Handling an Event in Child Without Parent Knowing

Spring Framework's default hierarchy **has no `stopPropagation()` operation on `ApplicationEvent`** like DOM events. If isolation is a hard requirement, consider separate publishers/event buses, avoiding parent-child linking for scopes needing isolation, or filtering at the parent. Do not expect a hidden flag on `@EventListener` to block upward propagation to ancestors.

## 12. Do @Order and @Async Fix Duplicate Events?

**No.**

`@Order` changes priority among matching listeners within a multicaster's dispatch scope; it **does not change the event's origin** and does not restrict a listener to own-context events.

`@Async` lets handlers run asynchronously when async support is configured. It also **does not stop events from propagating to the parent**. Moreover, with multiple contexts and executors, log order becomes less predictable, making idempotent handling and accurate origin filtering even more important.

Example:

```java
@EventListener
@Order(10)
public void onRefreshed(ContextRefreshedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return;
    }
    // Logic valid for the current context.
}
```

This is an illustrative method in a bean with `ownContext`, requiring `@EventListener`/`@Order` imports. Ordering can be useful, yet **the guard is what excludes descendant events**.

### 12.1. Exceptions and Error Handlers

By default, Spring's `SimpleApplicationEventMulticaster` processes synchronously. An unhandled exception from a listener can propagate back to the publishing site and affect startup/shutdown or the request publishing the event.

If you replace the multicaster with an async/error-handler setup, error reporting and execution order change. Still, whether sync or async, **handling duplicates from propagation remains your listener design's responsibility**.

## 13. Distinguishing Listener Registration Mechanisms

A listener can be added to a context via:

- `@Component` + implementing `ApplicationListener<EventType>`.
- `@Component` containing an `@EventListener` method.
- `@Bean` returning `ApplicationListener<?>` or a bean with `@EventListener` methods.
- `ConfigurableApplicationContext.addApplicationListener(...)` before refresh.
- `SpringApplication.addListeners(...)` before `run(...)`, suitable for early Boot events.
- `META-INF/spring.factories` for library listeners needing early Boot loading.

**Important:** registering a listener in **one context** does not copy that listener bean into child contexts. The parent listener receives child events because of **propagation**, not because Spring "clones listener beans into every context."

### 13.1. Distinguishing Multiple Registrations from Multi-Context Events

If a listener produces duplicate logs, inspect two separate axes:

1. **Topology:** which context published the event, what is its parent, and which contexts did it pass through?
2. **Registration:** how many times is the bean/listener registered in each context? Does `@ComponentScan` scan a package twice? Are `addListeners` and `spring.factories` registering the same class?

Only by separating these two questions can you diagnose accurately and apply the minimal fix.

## 14. A Logging Pattern That Pinpoints the True Source

Do not log only:

```text
ContextRefreshedEvent received
ContextRefreshedEvent received
```

Those two lines do not reveal whether there are two contexts or two registrations.

Log non-sensitive information showing:

```text
listenerOwner=parent eventContext=parent type=ContextRefreshedEvent
listenerOwner=parent eventContext=child  type=ContextRefreshedEvent
```

Inside the handler:

```java
@EventListener
void trace(ContextRefreshedEvent event) {
    System.out.println("listenerOwner=" + ownContext.getId()
            + " eventContext=" + event.getApplicationContext().getId()
            + " type=" + event.getClass().getSimpleName());
}
```

The method above is a snippet inside a bean with `ownContext`. IDs are observability metadata, **not a replacement** for object identity comparison in the guard.

If logs need correlation across restarts/deploys, include an instance ID/startup ID; never log tokens, secrets, or the entire `Environment`.

## 15. Common Mistakes and Fixes

| Symptom | Likely cause | How to check / fix |
| --- | --- | --- |
| Parent listener prints two ContextRefreshedEvent lines | Both parent and child refreshed; child event propagated up | Print `event.getApplicationContext().getId()`; filter `!= ownContext` if own-only |
| A child listener receives parent's event without manual publish | Unexpected topology/registration or event was republished | Check publishing site, parent chain, and actual bean listeners; default propagation does not go down to children |
| Listener in child A receives child B's event | Shared listener outside context or custom bridge | Check multicasters and event buses; siblings do not automatically receive each other's events |
| Parent cleanup logic runs when child closes | Parent listens to `ContextClosedEvent(child)` | Filter event context before side effects; use bean destroy hooks for parent resources |
| Context name comparison still fails | Two contexts share the same class/name/id | Compare `event.getApplicationContext() == ownContext` |
| `getSource()` is a business object, not a context | Custom event defines its own source | Define `originContext`/`publisherId` explicitly |
| Custom payload lacks `getApplicationContext()` | Payload is not an `ApplicationContextEvent` | Carry origin in payload or filter by event type/metadata |
| Duplicate logs persist despite own-context filter | Listener may be registered twice in the same context | Check `@ComponentScan`, `@Bean`, `addListeners`, `spring.factories` |
| Origin filter present yet callback still runs multiple times | Guard only drops foreign events, does not provide exactly-once | Use idempotency or business keys when performing side effects |
| `@Order` did not stop duplicates | `@Order` only sorts callback order | Use proper guards and inspect topology |
| `@Async` changed log order | Executor runs callbacks asynchronously | Do not infer origin from log order; log context metadata |
| Startup fails when child refreshes | Parent listener throws exception in child callback | Inspect handler stack trace, limit side effects, define failure policy |
| Tests count different event counts than test count | TestContext caching, `@DirtiesContext` recreating contexts, hierarchy | Observe context identity, test scope, and caching |
| Want events only in child yet parent still sees them | Propagation is the hierarchy default | Build an isolated bridge or filter in parent |
| Spring Boot listener sees multiple `ApplicationReadyEvent`s | Multiple `SpringApplication`s in hierarchy | Check `event.getApplicationContext()` and owner per event contract |
| Using context filter to isolate tenants | Context is not necessarily a tenant | Add `tenantId` to the domain event |

## 16. Testing Propagation and Filtering Logic

Beyond manual logs, integration tests should verify **invocation counts and actual origins**.

Idea:

1. Create parent, register a `ContextRefreshedEvent` listener that increments separate counters for `parent` and `child`.
2. Refresh parent once: `parent-origin` counter must increment.
3. Create child, call `setParent(parent)`, refresh child: `child-origin` counter must increment on the parent listener.
4. Verify the parent's **own-only** listener does not increment during child refresh.
5. Publish a business event from child: matching child and parent listeners receive it; siblings do not.
6. Publish from parent: parent listeners receive it; child listeners do not.
7. Close child then parent: if tracking `ContextClosedEvent`, verify the parent listener does not run cleanup prematurely when child closes.

Example Java assertions checking refresh event origin:

```java
AtomicInteger parentOwnRefreshes = new AtomicInteger();
AtomicInteger parentObservedChildRefreshes = new AtomicInteger();

// Register a typed listener for ContextRefreshedEvent in parent.
if (event.getApplicationContext() == parent) {
    parentOwnRefreshes.incrementAndGet();
} else if (event.getApplicationContext() == child) {
    parentObservedChildRefreshes.incrementAndGet();
}
```

This is an **illustrative snippet inside a test/listener**, not a standalone runnable file; it requires importing `AtomicInteger`, having `parent`/`child`/`event` in scope, and registering the listener in the right context before refresh.

### 16.1. Context Caching and Test Lifecycle

`@SpringBootTest` can reuse the same context via the TestContext cache. Thus a `ContextRefreshedEvent` does not necessarily fire before **every** test method. With `@DirtiesContext`, contexts can be closed and recreated, changing event counts. Do not build tests assuming "one test method = one refresh" without controlling cache/hierarchy configuration.

## 17. Operating with Multiple Child Contexts

When the parent shares database pools, metrics, message listeners, or caches:

- **Define ownership:** does a resource belong to the parent or to each child? Never close shared resources when one child stops.
- **Classify events:** which events are system-wide, and which concern only one child?
- **Record origin:** lifecycle events use `getApplicationContext()`; domain events should carry clear origin/business metadata.
- **Choose side-effect policy:** own-only, all descendants, or only permitted children.
- **Ensure idempotence:** filtering does not stop multiple valid events or business retries.
- **Ensure concurrency safety:** each context may use its own multicaster/executor; counters/caches must not assume sequential execution.
- **Ordered shutdown:** prefer stopping/closing children before parent when parent holds dependencies used by children.
- **Metrics and logs:** avoid high cardinality; include context ID/role, instance ID, and correlation ID as needed.
- **Verify readiness:** a child context refreshing does not mean the whole application is ready; Boot still runs runners and availability state transitions.

Remember that Spring Boot can build multiple contexts for specialized patterns, yet **not every application needs a hierarchy**. A complex hierarchy built just to share a few beans can be harder to operate than a single context with clean package/module boundaries.

## 18. Self-Check Questions

**1. Parent has one `ContextRefreshedEvent` listener; parent and child each refresh once. How many events can the parent listener receive?**

Typically **two**: one from parent, and one propagated up from child. These are two distinct events, not necessarily duplicate listener registration.

**2. Does a child automatically receive events from `parent.publishEvent(...)`?**

**No**, under default propagation. The direction is emitting context → parent → ancestors, not broadcasting downward to children.

**3. Do two children of the same parent automatically receive each other's events?**

**Not automatically**. The parent can receive both, yet does not forward them down to the sibling child.

**4. Is comparing `getId()` always enough to filter by exact context?**

**Not always**, because IDs can collide or change. For `ApplicationContextEvent`, compare **object identity** between `event.getApplicationContext()` and `ownContext`.

**5. Does a custom `ApplicationEvent` have `getApplicationContext()` like `ContextRefreshedEvent`?**

**Not by default**. It depends on the event class. For domain events, include `originContext` or appropriate metadata if source filtering is required.

**6. Does `@Order` stop the parent from receiving child events?**

**No**. `@Order` only affects listener ordering; a guard filters events by origin.

**7. A parent listener handles `ContextClosedEvent(child)` and closes a shared pool. Where is the bug?**

It failed to check origin, so it closed parent resources when the child shut down. Use an own-context guard and assign cleanup to the proper lifecycle owner.

**8. Does event propagation automatically send events across other microservices?**

**No**. This mechanism operates within a single JVM/context hierarchy. Use messaging or APIs for inter-process communication.

**9. If you want the parent to audit every child, do you need an own-only guard?**

**No**. The parent can intentionally listen to descendants; just identify origins properly, avoid duplicate logic, and bound side effects.

## 19. Knowledge Checklist

1. Know which context is parent/child; do not infer from packages or Gradle dependencies.
2. Remember propagation direction: **emitting context → ancestors**, never automatically down to children or across to siblings.
3. For `ContextRefreshedEvent`/`ContextClosedEvent` and other `ApplicationContextEvent`s, read origin with `event.getApplicationContext()`.
4. When handling **only your own context**, filter with `event.getApplicationContext() == ownContext`.
5. Obtain `ownContext` via constructor injection or `ApplicationContextAware` inside a **bean listener belonging to that exact context**.
6. For domain events, define origin metadata and filters per business contract.
7. Distinguish event propagation from duplicate listener registration and from multiple valid events.
8. Do not expect `@Order`/`@Async` to suppress propagation.
9. Use `ContextClosedEvent` carefully so closing a child context never destroys parent resources.
10. Write parent–child tests checking origin, invocation counts, and skip logic.
11. Design side effects to be idempotent; context filters do not provide exactly-once delivery.
12. Pick readiness/lifecycle events at the right stage; context refresh does not mean the app is fully ready.

## 20. Summary

```text
CHILD publishEvent(E)
    |
    +--> child listener(s)
    |
    +--> PARENT listener(s)
             |
             +--> ancestor listener(s)

PARENT publishEvent(E)
    |
    +--> parent listener(s)
    X    does not automatically propagate down to child

For ApplicationContextEvent:
    event.getApplicationContext() = context THAT EMITTED the event

Guard to handle only your own context:
    if (event.getApplicationContext() != ownContext) return;
```

**Concise rule:** a listener in a parent context can receive events from child contexts; that is **intended Spring Framework behavior**. Before performing side effects, decide whether your listener needs **own-only** or **all-descendants**. If own-only, compare the event's context with the listener's owning context by **object identity**. For custom business events, include explicit origin metadata instead of guessing from event names.

## Official References

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners, filtering events from child contexts](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — SpringApplicationBuilder API and context hierarchies](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html)
- [Spring Boot — Build an ApplicationContext Hierarchy](https://docs.spring.io/spring-boot/3.3/how-to/application.html)
- [Spring Framework 6.1 — AbstractApplicationContext: publishEvent and parent propagation](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [Spring Framework — Application events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.1 — ApplicationContextEvent API](https://docs.spring.io/spring-framework/docs/6.1.5/javadoc-api/org/springframework/context/event/ApplicationContextEvent.html)
- [Spring Framework 6.1 — ContextRefreshedEvent API](https://docs.spring.io/spring-framework/docs/6.1.5/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html)
