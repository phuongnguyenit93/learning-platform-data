# Parent-Child Context Receives Unexpected Events in Spring Framework

## 1. Symptom: Parent Listener Runs Even Though Event Was Published from Child

In an application with **multiple Spring ApplicationContexts arranged in a parent–child relationship**, a classic troubleshooting scenario is:

- A service in the **child context** publishes an event.
- The listener in the **child context** processes it as expected.
- Yet the listener in the **parent context** also receives the event, even though the author thought the event was child-scoped.
- For lifecycle events like **ContextRefreshedEvent**, a parent listener may be called multiple times because both parent and child have their own initialization lifecycles.
- If both parent and child register handlers performing a side effect, you may observe two log lines, two metric increments, or two notifications for a single business action.

This is **not necessarily a Spring bug or duplicate publishing in application code**. By **ApplicationContext event propagation**, events published from a child context are forwarded **up to ancestor contexts**. Each context maintains its own listener registry; hence parent listeners can observe events emitted by children.

Diagram:

~~~text
            ROOT / PARENT APPLICATION CONTEXT
            +---------------------------------+
            | parent listeners                |
            | @EventListener on(MyEvent)      |
            +----------------^----------------+
                             |
                   event bubbles UP
                             |
            CHILD APPLICATION CONTEXT
            +---------------------------------+
            | publisher.publishEvent(MyEvent) |
            | child listeners                 |
            | @EventListener on(MyEvent)      |
            +---------------------------------+
~~~

**Default direction to remember:** **child -> parent -> grandparent**; there is no automatic **parent -> child** or **child A -> child B** propagation merely because they share a hierarchy.

**Lesson objective** in **Troubleshooting**: identify which context an event came from, why the same event type can be handled multiple times, distinguish lifecycle events from POJO payloads, write a Java 17+ reproduction program, and choose the right fix instead of just "turning off listeners to quiet logs".

## 2. How Does an ApplicationContext Hierarchy Work?

### 2.1. Parent–Child Is More Than Just Bean Naming

An **ApplicationContext hierarchy** is a real relationship between contexts. A child can access many beans, properties, or resources of the parent depending on lookup mechanisms; the parent **does not** automatically see child-specific beans. Both contexts remain **two separate units of lifecycle, listener registry, and configuration**.

Example:

~~~text
RootContext (parent)
  +-- commonService
  +-- parentEventListener
  |
  +-- WebContext (child)
       +-- controller
       +-- childEventListener
~~~

A bean created in the parent and injected with **ApplicationEventPublisher** is normally bound to **the parent context's publisher**. Conversely, a bean in the child normally uses the child's publisher. Thus "request arrived at child" is **not enough** to conclude the event was published with the child's publisher: check **which context owns the publishing bean**, and which publisher was injected.

Do not confuse **bean visibility** with **event propagation**:

| Aspect | Default direction |
| --- | --- |
| Child looking up parent bean | Accessible via standard bean lookup |
| Parent looking up child-only bean | Not automatic |
| Event published via **child context** | Child listeners receive it, then event forwards up to ancestors |
| Event published via **parent context** | Parent listeners receive it; not auto-broadcast down to children |
| Event published via sibling child A | A and ancestors receive it; sibling B does not automatically |
| Listener owned by parent yet injected into child | Remains a parent bean and typically uses parent publisher if it publishes |

**Important:** Each context can have its own **ApplicationEventMulticaster**. The parent receiving child events does not mean all listeners sit in one global registry; Spring forwards publication up the hierarchy.

### 2.2. Spring Event Publishing Flow

For standard contexts extending **AbstractApplicationContext**, publishing works roughly as follows:

1. An object is passed to **ApplicationEventPublisher.publishEvent(Object)**.
2. The current context wraps the object in an appropriate **ApplicationEvent** if needed.
3. The context dispatches to listeners registered in that context via its **ApplicationEventMulticaster**.
4. If a parent exists, the original event is also published to the parent context.
5. The parent dispatches to its own listeners and forwards up to any grandparent.

Model:

~~~text
child.publishEvent(event)
   |
   +--> child.multicaster -> child local listeners
   |
   +--> parent.publishEvent(event)
          |
          +--> parent.multicaster -> parent local listeners
          |
          +--> grandparent.publishEvent(event)
                 |
                 +--> grandparent listeners
~~~

With the default synchronous **SimpleApplicationEventMulticaster**, child callbacks generally execute before publication is forwarded to the parent. With **@Async** or custom executors, **completion order** and **execution threads** can differ; never use log order as a business contract across contexts.

This mechanism is **in-process** and is not a message broker, durable queue, or distributed event bus.

## 3. Why Can a Listener Receive "Unexpected" Events?

### 3.1. One Event from Child Reaches Both Child and Parent

If both contexts have listeners for **OrderConfirmed**, each listener may be called once for an event published through the child. From a business viewpoint, if both listeners call a notification service, it looks like "duplicate processing".

Those are **two valid subscriptions in two contexts**, not Spring calling the same listener twice inside a single registry.

### 3.2. Both Contexts Emit Lifecycle Events of the Same Type

When **parent.refresh()** and **child.refresh()** run, each context emits its own **ContextRefreshedEvent**. A parent listener can receive:

- **ContextRefreshedEvent** whose source is the **parent context**.
- **ContextRefreshedEvent** whose source is the **child context**, forwarded up to the parent.

Hence a parent listener listening for **ContextRefreshedEvent** may run **twice with two different sources**. Keep the same thing in mind at shutdown/close with **ContextClosedEvent**.

Specifically in Spring Boot using **SpringApplicationBuilder** to build hierarchies, the reference documentation warns that listeners may receive multiple events of the same type across a hierarchy.

### 3.3. Configuration or Component Scan Creates Listener Beans in Multiple Contexts

If both parent and child scan the same package, the same **@Component** class can be instantiated as **two separate bean instances**, each registering a listener in its own context. Events from the child pass through both registries. Here, beyond event propagation, there is also **architectural duplicate registration**.

Do not assume a listener instance was created twice without checking. Distinguish:

- **One parent bean** receiving events forwarded by the child.
- **One bean in parent and one bean in child** both processing.
- **Two registrations in the same context** due to duplicate configuration.
- **The application actually publishing two events** within the same use case.
- **Broker redelivery or retry** (if events come from messaging infrastructure).

These five situations have different fixes.

### 3.4. Overly Broad Listeners

Listeners such as **ApplicationListener<ApplicationEvent>** or methods accepting **ApplicationEvent** catch many framework events: **ContextRefreshedEvent**, **ContextClosedEvent**, **ContextStartedEvent**, and custom events extending **ApplicationEvent**. In a hierarchy, invocation counts multiply due to forwarding.

A listener meant to send an email when an order is confirmed should accept **OrderConfirmed**, rather than listening to all **ApplicationEvent**s and trying to guess business types from **toString()** or logs.

## 4. Identifying the Origin Context: Key Difference Between Two Event Kinds

This is the easiest place to make mistakes while debugging.

### 4.1. ApplicationContextEvent Has an API to Identify the Origin Context

For lifecycle events extending **ApplicationContextEvent**, such as **ContextRefreshedEvent** or **ContextClosedEvent**, use:

~~~java
ApplicationContext origin = event.getApplicationContext();
~~~

This is Spring's API returning the context associated with that lifecycle event. A parent listener can compare **origin** against the context owning the listener to know whether the event came from **the parent itself** or from a **descendant**.

Example:

~~~java
@Component
public final class LocalLifecycleListener
        implements ApplicationContextAware {

    private ApplicationContext owner;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.owner = context;
    }

    @EventListener
    public void on(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != owner) {
            // Refresh event from a descendant; ignore.
            return;
        }
        // Only handle when the context containing this listener refreshes.
    }
}
~~~

This is a **snippet**, requiring Spring imports and appropriate component scanning or bean registration. Use **identity comparison (== or !=)** for **ApplicationContext** objects when identifying the exact instance; do not compare only class names or `displayName`.

### 4.2. Custom ApplicationEvents Can Store the Context as Source

If defining a custom subclass of **ApplicationEvent**, you can design the contract so **source** is the publishing context:

~~~java
public final class ContextSignal extends ApplicationEvent {
    private final String eventId;

    public ContextSignal(ApplicationContext source, String eventId) {
        super(source);
        this.eventId = eventId;
    }

    public ApplicationContext originContext() {
        return (ApplicationContext) getSource();
    }

    public String eventId() {
        return eventId;
    }
}
~~~

This is an **illustrative class**; only use the cast above when **the constructor enforces that source is ApplicationContext**. In Spring's general API, **ApplicationEvent.getSource()** is **Object**, not automatically `ApplicationContext`. Other custom events may use an order, service, or entity as source.

With an explicit context source, the event object forwards up to the parent while preserving the defined **originContext** semantics. Do not use event object identity in place of a **business event ID** when business-level deduplication is needed.

### 4.3. POJO/Record Events: Do Not Rely on PayloadApplicationEvent.getSource() to Guess the Original Source

Spring supports publishing plain Java objects directly, e.g.:

~~~java
public record OrderConfirmed(String orderId, String originContextId) {}
~~~

When publishing a POJO with **publishEvent(Object)**, the context may create a **PayloadApplicationEvent** wrapping the payload. **AbstractApplicationContext** forwards **the original object** to the parent; in the parent, the POJO can be **re-wrapped in a new PayloadApplicationEvent** whose **source is the parent context itself**.

Therefore:

- **PayloadApplicationEvent.getSource()** in the parent does not always reveal the **original child context**.
- **PayloadApplicationEvent.getPayload()** remains the proper event object/business value, while the wrapper's source metadata is a dispatch-step detail.
- To distinguish origin in the parent when handling **POJOs**, place **originContextId** (or context/correlation metadata) inside the **payload/event envelope** at the application/infrastructure boundary.
- Do not force plain Java domain events to depend directly on Spring just for context sources; mappers/adapters can attach technical metadata.
- **originContextId** in a payload is only for routing/filtering/logging per application contract, never as authorization proof or a trusted security token when payloads arrive externally.

This matters because blanket advice like "for every event call `getSource()` and compare with the current context" is **incorrect for POJO events** crossing multiple contexts.

### 4.4. Origin Identification Table

| Event type | Source to inspect | Notes |
| --- | --- | --- |
| **ContextRefreshedEvent** | **getApplicationContext()** | The exact context that refreshed |
| **ContextClosedEvent** | **getApplicationContext()** | The exact context emitting close |
| Custom **ApplicationEvent** with context-source contract | **getSource()** or type-safe accessor | Trust only when constructor/event contract guarantees it |
| **POJO/record** published via **publishEvent(Object)** | **originContextId** metadata in payload/envelope | Do not infer origin from wrapper source in ancestors |
| **SpringApplicationEvent** | Built-in APIs and corresponding Boot lifecycle context | Check version/type; do not force all Boot events into one pattern |
| Event arriving from broker | Producer/consumer headers and tracing metadata | Not Spring `ApplicationContext` hierarchy propagation |

## 5. Complete Java 17+ Demo: Child Events Go Up to Parent, Not Down

Pure **Spring Framework 6.2.9** project, **JDK 17+**, **Gradle 8.x**, requiring no Spring Boot, database, or message broker. Goal: clearly observe which listeners execute when publishing from child and parent, and verify origin using **ApplicationContext identity**.

Structure:

~~~text
context-event-hierarchy-demo/
  build.gradle
  src/main/java/demo/ContextEventHierarchyDemo.java
~~~

### 5.1. File build.gradle

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'demo.ContextEventHierarchyDemo'
}
~~~

### 5.2. File src/main/java/demo/ContextEventHierarchyDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class ContextEventHierarchyDemo {

    public static final class TaggedEvent extends ApplicationEvent {
        private final String id;

        public TaggedEvent(ApplicationContext origin, String id) {
            super(origin);
            this.id = id;
        }

        public String id() {
            return id;
        }

        public ApplicationContext origin() {
            return (ApplicationContext) getSource();
        }
    }

    public static final class ParentHandler
            implements ApplicationContextAware {

        private ApplicationContext owner;

        @Override
        public void setApplicationContext(ApplicationContext context) {
            this.owner = context;
        }

        @EventListener
        public void on(TaggedEvent event) {
            String location = (event.origin() == owner)
                    ? "local"
                    : "forwarded";
            System.out.println("parent: " + location + " " + event.id());
        }
    }

    public static final class ChildHandler {

        @EventListener
        public void on(TaggedEvent event) {
            System.out.println("child: " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ParentConfig {
        @Bean
        ParentHandler parentHandler() {
            return new ParentHandler();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ChildConfig {
        @Bean
        ChildHandler childHandler() {
            return new ChildHandler();
        }
    }

    public static void main(String[] args) {
        try (var parent =
                     new AnnotationConfigApplicationContext(
                             ParentConfig.class)) {

            try (var child = new AnnotationConfigApplicationContext()) {
                child.setParent(parent);
                child.register(ChildConfig.class);
                child.refresh();

                System.out.println("publish: child");
                child.publishEvent(new TaggedEvent(child, "C1"));

                System.out.println("publish: parent");
                parent.publishEvent(new TaggedEvent(parent, "P1"));
            }
        }
    }
}
~~~

Run inside **context-event-hierarchy-demo**:

~~~bash
gradle --console=plain -q run
~~~

**Stdout printed by the program itself** with the default synchronous multicaster:

~~~text
publish: child
child: C1
parent: forwarded C1
publish: parent
parent: local P1
~~~

### 5.3. Line-by-Line Explanation

1. Parent is created first from **ParentConfig**; it registers **ParentHandler**.
2. Child is created with the empty constructor, then calls **child.setParent(parent)** **before** **child.refresh()**. Child registers **ChildHandler** in **ChildConfig**.
3. **child.publishEvent(TaggedEvent(child, "C1"))** is handled first by the local listener in child: **child: C1**.
4. The event continues forwarding up to parent. **ParentHandler** has **owner** equal to parent while **event.origin()** is child, so it prints **parent: forwarded C1**.
5. **parent.publishEvent(TaggedEvent(parent, "P1"))** is dispatched only in parent and its ancestors (no ancestor in this demo). ParentHandler sees `origin == owner` and prints **parent: local P1**.
6. ChildHandler does **not** print **child: P1** because events from parent **do not auto-propagate down to child**.
7. When closing child then parent, Spring also fires internal lifecycle events, yet the demo's listeners only accept **TaggedEvent**, producing no extra log lines.

**Source code note:** Here **TaggedEvent** intentionally takes **ApplicationContext** in its constructor as source so the cast in **origin()** is valid. Do not apply that cast to arbitrary `ApplicationEvent` types. The demo also configures no `@Async` or custom executor; hence stdout is explained by synchronous dispatch.

## 6. Fix 1: Filter Lifecycle Events by Owning Context

A listener performing cache initialization, metric registration, or lifecycle hooks should usually react only to **refreshes of the exact context containing it**.

Solution:

~~~java
@Component
public final class RefreshOncePerContext
        implements ApplicationContextAware {

    private ApplicationContext ownContext;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.ownContext = context;
    }

    @EventListener
    public void on(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        // Only handle ContextRefreshedEvent emitted by ownContext.
    }
}
~~~

This is a Spring Framework snippet requiring imports. Note:

- Compare **event.getApplicationContext()** with the listener bean's context, not merely class names or context IDs which could be configured identically.
- This is a **local-context filter**; it does not stop the event from forwarding up to parent. It only decides **whether the handler executes side effects**.
- If the same context can **refresh multiple times** (depending on context type), this filter still allows running on each refresh of that context. If business logic truly needs **only-once**, add explicit conditions/idempotency.
- For **ContextClosedEvent**, apply the same principle; when handling shutdown lifecycles, watch out for beans/services already being destroyed.
- When testing, create real parent and child contexts and verify the parent listener handles only parent-origin events and ignores child-origin events.

**Do not use @Order to fix this.** `@Order` only affects dispatch order among listeners in one scope; it does not stop child-to-parent forwarding.

## 7. Fix 2: Explicitly Scope POJO/Domain Events

For record events:

~~~java
public record OrderConfirmed(
        String orderId,
        String eventId,
        String originContextId) {}
~~~

A parent listener can inspect **originContextId** before executing side effects—for instance, handling only events published by the root-context application service:

~~~java
@EventListener
public void on(OrderConfirmed event) {
    if (!rootContext.getId().equals(event.originContextId())) {
        return;
    }
    // Handle domain event within the chosen scope.
}
~~~

The two snippets above require Spring beans and a **rootContext** reference resolved at the infrastructure layer. The domain does not need to know Spring: **originContextId** metadata can live in an integration envelope instead of domain records.

If a service has multiple contexts participating in business processing, a better option may be **one unified publisher/application service** responsible for emitting events for that workflow, with listeners placed in the exact context that should receive them. Avoid relying on context IDs as business IDs when tasks require **exactly once**.

### Which Context Should Hold the Listener?

Practical rules:

- Listener serving **only one web module**: register in that module's child context.
- Listener serving **the entire application**: can register in parent, understanding it will see events from descendants.
- Global listener that should handle only **parent-origin lifecycle events**: filter by context source.
- Listener executing critical external side effects: combine proper scope/filtering with **idempotency** and appropriate transactions/durable messaging.
- Multiple child modules sharing a service: consider publishing events through one clear boundary rather than letting multiple layers publish the same business fact.

Do not modify the hierarchy or block forwarding with a custom `AbstractApplicationContext` subclass just to eliminate two log lines, as doing so can break subsystems expecting those events. Prefer fixing **listener ownership, event types, and filtering** first.

## 8. Fix 3: Avoid Duplicate Registration from Bean Scanning

If two contexts use overlapping **@ComponentScan** paths, the same listener class can be instantiated in both contexts. An event published in the child flows through both registrations.

Investigation steps:

1. Inspect **@ComponentScan** in parent and child; verify package boundaries.
2. Inspect **@Import**, **@Bean**, auto-configurations, or manual registrations creating the same listener type.
3. Check which context owns the listener bean, **not just whether `ApplicationContext.getBean(...)` succeeds**: a child can look up parent beans through the hierarchy.
4. Remember singleton scope means **singleton per BeanFactory/context**, not singleton across the entire hierarchy.
5. Check whether a listener is both declared as a bean and added manually via **ApplicationContext.addApplicationListener(...)** in configuration.
6. After identifying unintended duplicate registrations, narrow scanning/imports so each listener has a clear owner.

**Do not delete a listener solely because the same class appears in multiple places** if the application genuinely needs two handlers for two independent modules. Decide by business scope, not log line count.

### Distinguishing Local Beans from Inherited Beans

Using **ConfigurableListableBeanFactory/BeanFactory** and corresponding APIs, you can inspect local bean definitions or local registrations. A call to **child.getBean(ParentHandler.class)** can return a parent bean because child contexts fall back to parent lookup. Therefore **getBean() succeeding does not prove the bean is locally registered in the child**.

When debugging bean lists, inspect **context ID**, **bean definition owner**, local bean factory, and instance identity. Avoid calling a **getBeanNamesForType(...)** variant that may inspect ancestors depending on parameters/implementation and assuming all returned beans are local.

## 9. Fix 4: Never Execute Business Side Effects Twice

Even when both contexts receive an event as designed, a business side effect **must not run twice** if the contract permits only once.

Bug example:

~~~text
child.listener(OrderPaid) -> send invoice email
parent.listener(OrderPaid) -> send invoice email
Result: one payment action can generate two emails.
~~~

Remediation:

- Assign a single owner for mandatory side effects, e.g., registering the notification adapter in only one context.
- If listeners are genuinely independent, give each a clear **consumer name/side-effect purpose** so they do not accidentally invoke the same handler.
- Include an **eventId** or business operation ID in the event to perform proper consumer-side deduplication.
- For durable processing via broker/outbox, implement **idempotency keys** and persist processed markers instead of using a static JVM boolean.
- Clarify transaction timing: a synchronous **@EventListener** can run before commit; use **@TransactionalEventListener(phase=AFTER_COMMIT)** or an **outbox** when truly needed. **AFTER_COMMIT does not prevent both parent and child from receiving the event**; it only controls execution phase when a compatible transaction exists.
- Separate business events from lifecycle events. Do not attach business side effects to **ContextRefreshedEvent** when they are not lifecycle facts.

If a parent listener must receive events from both parent and children for analytics, do not filter out all child-origin events. Instead, include **origin metadata** in metrics/logs and define aggregation clearly to avoid double counting.

## 10. Logging to Trace Event Paths

When a handler runs unexpectedly, log enough details to separate **publication**, **propagation**, and **registration**.

Recommended fields:

| Field | Purpose |
| --- | --- |
| **eventType** | Event type being handled by the listener |
| **eventId / businessKey** | Distinguish one business event from two separate events |
| **listenerName / beanName** | Identify which handler actually ran |
| **listenerContextId** | Context owning the listener bean |
| **parentContextId** | Parent context of owner, if any |
| **originContextId** | Context that published the event, per event contract |
| **traceId / correlationId** | Link requests and asynchronous processing |
| **threadName** | Detect executors/async and avoid inferring from log order |
| **phase** | immediate, BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, ... |
| **result** | success/failure/skipped and filter reason |

Example with **ContextRefreshedEvent**:

~~~java
@EventListener
public void on(ContextRefreshedEvent event) {
    String originId = event.getApplicationContext().getId();
    String listenerId = ownerContext.getId();
    String parentId = ownerContext.getParent() == null
            ? "none"
            : ownerContext.getParent().getId();

    log.info(
            "event=ContextRefreshedEvent owner={} parent={} origin={}",
            listenerId, parentId, originId);
}
~~~

This snippet requires **ownerContext**, **log**, and imports. A single parent + child refresh can produce:

~~~text
event=ContextRefreshedEvent owner=root parent=none origin=root
event=ContextRefreshedEvent owner=root parent=none origin=web-child
~~~

The second line illustrates **the parent listener observing the child's event**, not the parent refreshing a second time.

**Note:** For POJO events, do not populate **originContextId** using **PayloadApplicationEvent.getSource()** at the parent and infer the source context, because the wrapper may be recreated in the parent. Obtain origin metadata controlled by the application, or from a custom `ApplicationEvent` with an explicit contract.

### Do Not Just Count Logs

One event can produce multiple log lines inside one listener; logs can also be duplicated by appenders or log collectors. To detect duplicate processing, check **event ID**, **listener bean identity/context**, and **side-effect identity**, not just total log line counts.

## 11. Framework Events That Can Confuse Results

### 11.1. ContextRefreshedEvent

Parent refreshes first, child refreshes afterward: a parent listener can see **two events of the same type with different origins**. Avoid writing a listener like "whenever any context refreshes, initialize global cache" without checking source, as the global cache may be reinitialized.

### 11.2. ContextClosedEvent

Closing the child can emit **ContextClosedEvent** and forward it up to the parent. When the parent later closes as well, a parent listener sees events from both child and parent. If the listener cleans up a shared resource, avoid premature cleanup when **child** closes if the resource belongs to parent; conversely, child-owned resources should not be managed by parent listeners.

### 11.3. Spring Boot Application Events

In hierarchies built with **SpringApplicationBuilder**, each **SpringApplication** can emit its own startup/lifecycle events, and Spring Framework forwards events traversing child contexts up to ancestors. Thus the same Spring Boot application event type can appear multiple times in a parent listener.

**Do not apply a single assumption to all Spring Boot events**: some fire before context creation or refresh, with different APIs/sources from **ApplicationContextEvent**. For events with context accessors, compare via that type's API; for early startup events, examine listener registration timing, version, and Boot emission behavior.

### 11.4. ContextHierarchy in Spring Test

Spring TestContext supports **@ContextHierarchy** to build context hierarchies for integration tests. If test contexts are cached, dirtied, or reloaded between tests, lifecycle events can also appear outside minimal scenarios.

When testing event propagation bugs, use explicit **ApplicationContext objects** or a well-defined test hierarchy; if tests depend on lifecycle event counts, control context refresh/close and Spring TestContext caching.

## 12. Can @EventListener condition, @Order, and @Async Fix It?

### @EventListener(condition = "...")

SpEL-based conditions can filter events by payload or metadata. However, for **context origin**, an explicit Java **if** inside the listener is usually easier to read and test, and avoids depending on how wrappers construct sources per context. Conditions **filter handling**; they do not alter forwarding paths.

### @Order

**@Order** orders listener priority **within a matching event multicaster/dispatch path**. It does not make child events local-only and does not automatically make side effects run once. If both parent and child register listeners, setting the same or different `@Order` does not address the root cause.

### @Async

**@Async** offloads listeners onto thread pools, which can cause parent and child logs to interleave in different order and make guessing "who received first" from stdout unreliable. It does not block propagation and does not guarantee event processing. Trace context/MDC must be propagated properly where needed.

### @TransactionalEventListener

This annotation binds events to transaction outcomes, **not context origin**. It also requires compatible transaction synchronization; by default, listeners outside a transaction do not run (**fallbackExecution=false**). A parent listener can receive events forwarded by a child, yet whether the callback runs still depends on **the transaction actually active at publish time and thread/phase**.

**Conclusion:** Those annotations solve different concerns; to fix "unexpected" events, pinpoint **origin**, **listener owner**, **publish path**, and **side-effect owner** first.

## 13. Testing to Reproduce and Prevent Regressions

### 13.1. Integration Matrix

| Action | Child handler | Parent handler | Explanation |
| --- | --- | --- | --- |
| Publish **TaggedEvent** via child | Called | Called | Upward propagation |
| Publish **TaggedEvent** via parent | Not auto-called | Called | No automatic downward propagation |
| Refresh parent then child | If listener accepts only `TaggedEvent`: no | No | Type filter avoids lifecycle noise |
| Parent listener listening for **ContextRefreshedEvent** | Unrelated | May receive both parent and child | Same event type, different origins |
| Publish POJO via child | Child listener by payload type | Parent listener by payload type | Do not infer origin from `PayloadApplicationEvent` wrapper |
| Publish child with parent listener local-only filter | Child processes normally | Parent skips child-origin side effect | Event still forwards, handler filters |

### 13.2. Testing with a Recorder, Not Just System.out

In integration tests, replace **System.out.println** with a fake recorder:

~~~java
public final class EventRecorder {
    private final List<String> calls = new CopyOnWriteArrayList<>();

    public void record(String value) {
        calls.add(value);
    }

    public List<String> snapshot() {
        return List.copyOf(calls);
    }
}
~~~

This is a **snippet** requiring imports for **java.util.List** and **java.util.concurrent.CopyOnWriteArrayList**. Inject the recorder into parent/child handlers, publish events, and assert:

~~~text
child.publish(E1)
expect: ["child:E1", "parent:forwarded:E1"]

parent.publish(E2)
expect: ["parent:local:E2"]

parent listener with local-only filter:
child.publish(E3)
expect: ["child:E3"] in side-effects list
~~~

These are **test expectations**, not stdout from the recorder class. When executors/`@Async` are involved, use **CountDownLatch** or Awaitility to wait for handler completion; do not rely on fixed **Thread.sleep(...)**.

If testing custom **ApplicationEvent** context sources, assert **event.origin() == child** at the parent. If testing POJO events, assert **event.originContextId()** is preserved in the payload; tests should not depend on wrapper sources.

### 13.3. Testing Duplicate Registration

Create parent and child configurations that could register the same listener type, verifying:

- How many **local handler beans** exist in each context.
- For an event published via child, which handlers are invoked.
- If two handlers execute the same action, whether the **action count** matches the contract.
- After narrowing component scan, whether parent/child ownership is right.
- Under real retries/redeliveries, whether idempotency protects side effects even if the event is processed multiple times.

Asserting "handler was called" is not enough to find duplicate sources. Record **(eventId, listenerContextId, listenerName)** to see exactly where duplication occurs.

### 13.4. Testing Refresh/Close

If services use lifecycle events:

1. Parent refreshes, child refreshes.
2. Parent lifecycle listener receives events with **origin** equal to parent and child respectively where expected.
3. Local-only filter performs work only when **origin == owner**.
4. Child closes then parent closes; confirm shared resources are not cleaned up twice.
5. With more hierarchy levels, add a grandchild and verify events from grandchild flow through child and then parent.

## 14. Step-by-Step Production Investigation Procedure

Suppose logs show **OrderConfirmed** processed twice. Instead of slapping a global **synchronized** block to "stop it quickly", follow:

**Step 1 — Confirm whether there was truly one publish or multiple publishes.** At the publisher, log event ID, business ID, context ID, thread, and correlation ID. If one business operation creates two event IDs, the bug may be in application logic or upstream retries.

**Step 2 — Map the real hierarchy.** From the current context, inspect **getParent()** to identify root/child and IDs. Never guess that Actuator or a servlet always creates a child context; layout depends on the app and configuration.

**Step 3 — Identify the context containing the publisher bean.** A bean in parent may use parent's publisher even when invoked by a controller in child. Check which container owns the bean and where `ApplicationEventPublisher` was injected.

**Step 4 — Identify listener registrations.** Parent, child, both, or two instances in the same context? Check `ComponentScan`, `@Bean`, `@Import`, `addApplicationListener`, and auto-config scopes.

**Step 5 — Identify event type and origin extraction.** For `ContextRefreshedEvent` use `getApplicationContext`; for custom `ApplicationEvent` check source contract; for POJOs add explicit origin metadata.

**Step 6 — Check async.** If logs appear out of order, verify multicaster task executor, `@Async`, and `ThreadLocal`/MDC trace context. Do not confuse late arrival with duplicate arrival.

**Step 7 — Check transactions and side effects.** An event may be published before commit and the transaction may roll back. If listeners perform external side effects, apply after-commit/outbox policies; scope filters do not solve lost/duplicate delivery.

**Step 8 — Fix the exact boundary.** Only one listener owns the side effect; filter origin if appropriate, narrow scanning, or route the event to a boundary with a clear owner.

**Step 9 — Write integration tests.** Test child publication, parent publication, lifecycle origins, duplicate registrations, and idempotency.

**Step 10 — Observe post-deployment.** Monitor event counts by **originContextId** and **listenerContextId**, recheck dashboards, traces, and actual side-effect counts.

## 15. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming Spring events stay inside the publishing context | Parent listeners unexpectedly handle child events | Understand **child -> ancestors** propagation |
| Assuming parent-published events reach children too | Child listeners do not run | Publish in the right context/boundary or design an explicit bus |
| Parent listening to `ContextRefreshedEvent` without filtering source | Initializes/cleans up twice | Compare **event.getApplicationContext()** with owning context |
| Parent/child `@ComponentScan` both scanning the same listener | Two bean instances executing same side effect | Narrow scanning and assign ownership |
| Calling `getBean()` on child to conclude bean is local | Confuses inherited beans with child-owned beans | Inspect local bean definitions/owner |
| Treating every `ApplicationEvent.getSource()` as `ApplicationContext` | `ClassCastException` or wrong filter | Use only per that event type's source contract |
| Using `PayloadApplicationEvent.getSource()` to infer original context | Parent wrapper has parent as source | Carry **originContextId** in payload/envelope |
| Using `@Order` to stop events bubbling to parent | Has no effect on propagation | Filter or place listeners in the right context |
| Using `@Async` to "prevent duplicates" | Changes ordering/threads, still duplicates | Fix ownership, add idempotency |
| Believing a listener method running twice must mean one event | May be two distinct lifecycle events | Log `eventId`, `originContextId`, context owner |
| Using `ContextRefreshedEvent` to send business emails | Emails sent on deploy/refresh | Use proper domain events |
| Thinking `@TransactionalEventListener` makes listeners local-only | Parent still receives event; phase is orthogonal | Combine scope filtering with transaction semantics |
| Using event source/context ID for authentication | May trust untrusted metadata | Enforce proper authorization; never use technical metadata as permissions |
| Deduplicating with a non-durable static `Set` | Restarts/races allow duplicate side effects | Use durable idempotency store/`eventId` for critical effects |
| Not testing the real hierarchy | Single-context unit tests stay green | Write integration tests with real parent and child |

## 16. Checklist Before Concluding the Issue Is Resolved

- **Do parent and child truly have a `getParent()` relationship?**
- **Which context published the event? Which context owns the publisher bean?**
- **Are listeners in parent, child, or both? Are there duplicate registrations?**
- **Is the event an `ApplicationContextEvent`, custom `ApplicationEvent`, or POJO payload?**
- **Is the origin context identified via the appropriate API/contract?**
- **For POJO events, is origin metadata in the payload/envelope rather than guessed from wrapper source?**
- **Are child events forwarding up to parent as designed?**
- **Are parent events mistakenly expected to flow down to children automatically?**
- **Are same-type lifecycle events from parent/child being miscounted as a single duplicated event?**
- **Do side-effecting listeners have a single owner or idempotency?**
- **If async is present, are log ordering and trace context verified?**
- **If after-commit is needed, are transaction phase and durable delivery designed separately?**
- **Are integration tests covering child-origin, parent-origin, close/refresh, and siblings not auto-receiving?**

**Conclusion:** In a **Spring ApplicationContext hierarchy**, events published in a **child** travel **up to parent/ancestors**, causing parent listeners to receive unexpected events. Meanwhile, each context has its own lifecycle events, so listeners on **ContextRefreshedEvent/ContextClosedEvent** can observe multiple events of the same type. Diagnose accurately with **context owner + event origin + event ID + listener registration**. Use **getApplicationContext()** for lifecycle events, explicit source contracts for custom `ApplicationEvent`s, and separate origin metadata for **POJO events**; then filter scope, fix bean scanning, and guard side effects with idempotency where needed. Never use `@Order`, `@Async`, or log line counts as substitutes for mapping the propagation path.

### Official Documentation

- Spring Boot Reference — *Application Events and Listeners* (warning on event propagation in hierarchies): https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Framework Reference — *Additional Capabilities of ApplicationContext / Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Javadoc 6.2.9 — *AbstractApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework Javadoc 6.2.9 — *ApplicationContextEvent*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/ApplicationContextEvent.html
- Spring Framework Javadoc 6.2.9 — *PayloadApplicationEvent*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/PayloadApplicationEvent.html
- Spring Framework Javadoc 6.2.9 — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html