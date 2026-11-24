# Coordinating Listeners with Ordered and @Order in Spring Boot

## 1. Why Coordinate Listener Ordering?

An event in Spring can interest multiple components: writing audit logs, updating metrics, logging diagnostics, warming caches, sending notifications, or checking a post-startup condition. When `ApplicationEventPublisher.publishEvent(...)` publishes an event, Spring finds **listeners matching the event type** and dispatches the event to them.

When multiple listeners react to the same event, we sometimes want listener A invoked before listener B. Spring supports two common approaches:

- Implementing **`org.springframework.core.Ordered`** on an `ApplicationListener`, returning a dynamic order via `getOrder()`.
- Placing **`org.springframework.core.annotation.Order`**, especially **on `@EventListener` methods**; or on a listener class when declaring order via metadata.

Both describe **priority within the list of matching callbacks**; they do not force the system to instantiate beans in that order, do not alter the sequence of different event types, and **do not guarantee asynchronous tasks complete in order**.

This content focuses on Spring Framework **6.1.x**, Spring Boot **3.3.x**, and Java **17+**. When using a custom `ApplicationEventMulticaster`, `@Async`, multiple `ApplicationContext` instances, or transactional listeners, check the limitations at the end of this lesson.

**Quick rule of thumb: a smaller `order` value gives higher priority to be invoked earlier.**

## 2. What Are Listeners in Spring Really?

There are two very common forms.

### 2.1. Interface-Based ApplicationListener

```java
@Component
class AuditListener implements ApplicationListener<OrderCreatedEvent> {
    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Handle when OrderCreatedEvent occurs.
    }
}
```

This is an **illustrative snippet**, not a standalone Java file: `OrderCreatedEvent` must be defined as an `ApplicationEvent`, and `ApplicationListener` and `@Component` must be imported. Once the listener bean is registered, the event multicaster can invoke `onApplicationEvent(...)`.

For a class instantiated manually with `new`, to participate in Boot's dispatch mechanism from an early stage, you must register the listener at bootstrap—for example via `SpringApplication.addListeners(...)`. Merely constructing a Java object does not make it a listener.

### 2.2. @EventListener Methods on Spring Beans

```java
@Component
class NotificationListener {
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        // Handle when OrderCreatedEvent occurs.
    }
}
```

This is also an illustrative snippet. Spring processes `@EventListener` on the bean and registers a listener adapter for the method. Advantage: a single bean can host multiple methods for different event types.

**Distinguish the listener style before choosing `@Order`:**

- For direct `ApplicationListener` implementations, use `Ordered` or declare `@Order` on the class where annotation-aware ordering applies.
- For an `@EventListener` method, **placing `@Order` directly on that method** is the approach recommended by Spring documentation. It is unambiguous and supported by the `@EventListener` adapter.
- Do not place `@Order` only on the class containing `@EventListener` methods and assume every method inherits that exact order. When coordinating method listeners, place the annotation on each method.

## 3. Sorting Rule: Smaller Numbers Run First

The `Ordered` interface defines:

```java
public interface Ordered {
    int HIGHEST_PRECEDENCE = Integer.MIN_VALUE;
    int LOWEST_PRECEDENCE = Integer.MAX_VALUE;
    int getOrder();
}
```

The snippet summarizes the API for learning; real projects use Spring's built-in interface. `getOrder()` returns an integer, where smaller means higher priority.

| Order value | Relative priority | When to use |
| --- | --- | --- |
| `Ordered.HIGHEST_PRECEDENCE`, equal to `Integer.MIN_VALUE` | Highest in the order comparison system | Very rare; be careful because the framework also has high-priority listeners |
| `-100` | Before `0`, `10`, `100` | Callbacks that need to run quite early |
| `0` | Before `10` | Common priority anchor |
| `10` | Before `20` | Step 1 in a group of callbacks of the same type |
| `20` | After `10`, before `30` | Step 2 |
| `Ordered.LOWEST_PRECEDENCE`, equal to `Integer.MAX_VALUE` | Lowest by order value | Listeners that do not need priority |

Spring uses a suitable comparator to sort the listener list. In standard event multicasting, matching listeners are sorted by order before dispatch.

### 3.1. @Order(value) Is Metadata, Ordered#getOrder() Is a Contract

Two ways to express an equivalent value:

```java
// Option A: class with getOrder() returning 10.
@Component
class FirstListener
        implements ApplicationListener<OrderCreatedEvent>, Ordered {
    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // ...
    }
}
```

```java
// Option B: @EventListener method with @Order(10).
@Component
class AnotherListener {
    @EventListener
    @Order(10)
    public void onOrderCreated(OrderCreatedEvent event) {
        // ...
    }
}
```

These are illustrative snippets, **not two standalone files**; they require defining `OrderCreatedEvent` and corresponding imports. In the lab section below, complete runnable code is provided.

**Key difference:** `Ordered` can return a value computed at runtime from constructor/configuration parameters, whereas `@Order(10)` is constant metadata on the code. When an object implements `Ordered` and also carries `@Order`, standard comparators prioritize the object's `Ordered#getOrder()` value. Avoid declaring two different numbers for the same listener, as it causes confusion during code review.

### 3.2. What About Equal Order Numbers?

If two listeners share the same order or have no explicit order configuration, **do not treat an accidentally observed order as a business contract**. Actual order can vary with bean registration, classpath, comparator, factory, or framework updates.

For instance, with two listeners both marked `@Order(10)`, you cannot infer which will be called first. If B genuinely needs A's output, assign distinct order values **and evaluate whether coupling through listeners is appropriate**.

### 3.3. What Is the Default Without Order Configuration?

For listeners following Spring order semantics, having no explicit ordering information generally corresponds to low priority `Ordered.LOWEST_PRECEDENCE` in standard comparators. **Do not rely on their relative positions within that same tier**, even if one run happens to yield a consistent sequence.

### 3.4. PriorityOrdered Can Affect the Comparator

Spring also has the `PriorityOrdered` interface in the `Ordered` family. It is a specialized precedence mechanism where supported by comparators, so do not arbitrarily mix `PriorityOrdered`, `Ordered`, and `@Order` and infer order solely from integer values. For typical business listener ordering, start with clear `Ordered`/`@Order` values and avoid competing for extreme framework precedence levels.

## 4. Choosing the Right Place to Declare Order

| Handler style | Appropriate priority declaration | Notes |
| --- | --- | --- |
| Bean implementing `ApplicationListener<MyEvent>` | `implements Ordered` and `getOrder()` | Clear runtime order control |
| Bean implementing `ApplicationListener<MyEvent>` | `@Order(20)` on the class | Good for fixed order; verify the active mechanism uses an annotation-aware comparator |
| Bean containing `@EventListener` method | `@Order(20)` placed **on the method** | Recommended by Spring docs for annotated event listeners |
| One bean with two `@EventListener` methods for the same event | Each method can have its own `@Order` | Coordinates at callback level; do not assume one class order applies to all |
| Listener registered via `SpringApplication.addListeners(...)` | Instance implementing `Ordered` or class with `@Order` metadata | Can hear early startup events before the context exists |
| `@TransactionalEventListener` | `@Order` alongside the appropriate transaction phase | Order does not replace `BEFORE_COMMIT`/`AFTER_COMMIT` phases |
| `@Async` listener | Can declare `@Order`, but do not use it to wait for completion | Start/scheduling order is not completion order |
| `ApplicationRunner` / `CommandLineRunner` | `@Order`/`Ordered` applies to **runners**, not event listeners | Same ordering family, different contract |

**Note:** Do not use `@Order` to demand that singleton X be instantiated before singleton Y. Bean initialization order is governed by the dependency graph, `@DependsOn`, and container lifecycle. Here `@Order` sorts **callbacks/listeners**.

## 5. Runnable Example: Ordered and @EventListener @Order Receiving the Same Event

Goal: in **one Spring Boot 3.3.x application**, have two listeners for an early startup event and three callbacks for a post-refresh custom event. We verify:

1. Two `ApplicationStartingEvent` listeners are registered on `SpringApplication` and ordered with `Ordered`.
2. An `@EventListener @Order(10)` method runs before an `Ordered(20)` interface listener.
3. An `@EventListener @Order(30)` method runs last.
4. With the default synchronous multicaster, `publishEvent(...)` returns **after** all three synchronous callbacks finish.

### 5.1. Java 17+ Gradle Project

Create a Java 17 project from Spring Initializr or Gradle, with the Gradle Wrapper. File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

`settings.gradle`:

```groovy
rootProject.name = 'listener-order-lab'
```

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

The project uses `spring-boot-starter` **without a web server**; event dispatch works normally in a non-web `ApplicationContext`. Turning off the banner and startup INFO logs makes the code's stdout easier to read.

### 5.2. A Complete Single Java File

Create `src/main/java/com/example/listener/ListenerOrderApplication.java`:

```java
package com.example.listener;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class ListenerOrderApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ListenerOrderApplication.class);

        // Early events occur before the context has beans.
        application.addListeners(
                new EarlyListener(-10, "01 early: order=-10"),
                new EarlyListener(10, "02 early: order=10")
        );

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // SpringApplication.run has executed runners and listeners.
        }
    }

    // A custom event with an explicit type.
    public static final class CheckEvent extends ApplicationEvent {
        public CheckEvent(Object source) {
            super(source);
        }
    }

    // Registered directly at bootstrap; does not need to be a Spring bean.
    static final class EarlyListener
            implements ApplicationListener<ApplicationStartingEvent>, Ordered {

        private final int order;
        private final String label;

        EarlyListener(int order, String label) {
            this.order = order;
            this.label = label;
        }

        @Override
        public int getOrder() {
            return order;
        }

        @Override
        public void onApplicationEvent(ApplicationStartingEvent event) {
            System.out.println(label);
        }
    }

    // Bean listener: implements ApplicationListener + Ordered.
    @Component
    public static class ClassBasedListener
            implements ApplicationListener<CheckEvent>, Ordered {

        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public void onApplicationEvent(CheckEvent event) {
            System.out.println("05 event: interface Ordered(20)");
        }
    }

    // Bean listener: two methods on the same event, independent orders.
    @Component
    public static class MethodBasedListener {

        @EventListener
        @Order(10)
        public void first(CheckEvent event) {
            System.out.println("04 event: method @Order(10)");
        }

        @EventListener
        @Order(30)
        public void last(CheckEvent event) {
            System.out.println("06 event: method @Order(30)");
        }
    }

    @Bean
    ApplicationRunner publishCheckEvent(ApplicationEventPublisher publisher) {
        return args -> {
            System.out.println("03 publish: before");
            publisher.publishEvent(new CheckEvent(this));
            System.out.println("07 publish: after");
        };
    }
}
```

**Why is this a valid Spring Boot program?**

- `@SpringBootApplication` enables auto-configuration and component scanning for package `com.example.listener`. The two `public static` nested classes with `@Component` become listener beans during context refresh.
- `EarlyListener` is registered directly **before `run(...)`**, so it can receive `ApplicationStartingEvent` — an event published before beans exist in the context.
- `CheckEvent extends ApplicationEvent` ensures `ApplicationListener<CheckEvent>` is a valid generic type. The event's source is the application configuration instance (`this`), and it is published inside the runner.
- `ClassBasedListener` implements `Ordered` and returns `20`; Spring uses that value to sort matching listeners.
- The two `@EventListener` methods live in the same bean yet carry distinct `@Order(10)` and `@Order(30)` annotations. Spring registers them as two independent callbacks.
- `ApplicationRunner` runs after context refresh, once bean listeners already exist, and explicitly publishes `CheckEvent`.
- `try` closes the context after `run` completes. The example needs no embedded server or external resources.

### 5.3. Running the Application

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

On macOS or Linux:

```bash
./gradlew bootRun
```

With the Gradle Wrapper and resolved dependencies, the lines **printed by the Java program itself** when no other listeners or custom multicasters are present are:

```text
01 early: order=-10
02 early: order=10
03 publish: before
04 event: method @Order(10)
05 event: interface Ordered(20)
06 event: method @Order(30)
07 publish: after
```

Gradle may still print task/build messages; we compare only the numbered lines from the application. The first two listeners both receive `ApplicationStartingEvent` and are sorted `-10` before `10`. The middle three callbacks all receive `CheckEvent` and are sorted `10`, `20`, `30`. Because dispatch is synchronous by default, line `07` appears after all three callbacks return.

These are two **independent event dispatches**. Do not compare `early @Order(10)` directly with `custom event @Order(10)` to claim callbacks of two different events must run together; cross-event sequence is determined by the bootstrap lifecycle.

### 5.4. Modifying and Predicting stdout Yourself

**Experiment A — change `getOrder()`:** Change `ClassBasedListener.getOrder()` from `20` to `5`. When `CheckEvent` is published, the interface callback will be invoked before `@Order(10)` and `@Order(30)`. The printed string still says `Ordered(20)` because it is hard-coded in the example; to avoid confusion, **update the log label to `Ordered(5)` as well** when practicing.

**Experiment B — swap annotations:** Change `@Order(10)` on method `first` to `@Order(40)`. Then `Ordered(20)` and `@Order(30)` run before the method numbered `40`. Again, update the log label to match the new value.

**Experiment C — remove @Order:** Remove both `@Order` annotations on the listener methods. Do not write tests depending on the order of those two methods. Both share the default unprioritized order with no strict contract.

**Experiment D — callback failure:** Inside method `first`, throw `IllegalStateException`. With the default synchronous multicaster **without an error handler swallowing exceptions**, the error propagates back to the publisher; subsequent listeners may not run, the runner may fail, and the Boot application may terminate startup with an error. Thus, order does not replace error handling.

**Experiment E — switch to @Async:** If listener methods run asynchronously, position in the dispatch list no longer guarantees completion timing. Do not assert completion order as in synchronous stdout.

## 6. Class-Level @Order vs. Method-Level @Order: Avoiding Scope Confusion

An `ApplicationListener` class can declare order at the class level:

```java
@Component
@Order(25)
class InventoryListener implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // handle...
    }
}
```

This is a **separate illustrative option**; do not drop it directly into the runnable project in Section 5 without defining `OrderCreatedEvent`. When the framework uses annotation-aware ordering on listener objects, class metadata acts as the fixed priority declaration.

By contrast, the following class has **two callbacks for the same event**:

```java
@Component
class EventMethods {

    @EventListener
    @Order(10)
    void record(OrderCreatedEvent event) {
        // callback 1
    }

    @EventListener
    @Order(50)
    void notifyClient(OrderCreatedEvent event) {
        // callback 2
    }
}
```

Here the two methods are two listener adapters with different orders, even though both reside in `EventMethods`. Placing `@Order` on each method is the clearest way to express intent; do not assume a class-level order applies equally to all methods when the adapter reads method-level metadata.

**When to choose which?**

- Need a listener class with complex logic and runtime priority: `ApplicationListener + Ordered`.
- Need a fixed order across an entire interface-based listener class: `@Order` on the class.
- Need concise callbacks coordinated individually within the same bean: `@EventListener + @Order` on each method.
- Need a listener registered from early Boot bootstrap: `SpringApplication.addListeners`; you can use `Ordered` on the listener instance.

## 7. Early Boot Startup Events and Listener Registration Eligibility

Some Spring Boot events occur **before `ApplicationContext` is created**:

- `ApplicationStartingEvent`: very early in `SpringApplication.run(...)`.
- `ApplicationEnvironmentPreparedEvent`: `Environment` exists, context not created yet.
- `ApplicationContextInitializedEvent`: context created, initializers have run, primary definitions not loaded yet.
- `ApplicationPreparedEvent`: primary definitions loaded, context not refreshed yet.

For these events, a callback is discovered only if it was **registered from bootstrap**, for example:

```java
SpringApplication app = new SpringApplication(MyApp.class);
app.addListeners(new EarlyApplicationListener());
app.run(args);
```

This is an **illustrative snippet** requiring your own `EarlyApplicationListener` class. Other options are `SpringApplicationBuilder.listeners(...)` or registering `org.springframework.context.ApplicationListener` in `META-INF/spring.factories` on the runtime classpath.

Example `spring.factories` configuration:

```properties
org.springframework.context.ApplicationListener=\
com.example.boot.EarlyApplicationListener
```

A real class and suitable constructor must exist before using it. Do not add this file to the Section 5 lab project unless you actually define that class.

**Common mistake:** A bean with only

```java
@EventListener
@Order(-100)
void onStarting(ApplicationStartingEvent event) {
    // ...
}
```

will **not catch the very early `ApplicationStartingEvent`**, even with a "high" negative order. When the event is published, the bean method listener has not been registered yet. **Order applies only to listeners that already exist and are eligible for the event**; it does not take a listener back in time.

Later events, such as `ApplicationStartedEvent` or `ApplicationReadyEvent`, generally arrive after context refresh, so `@EventListener` beans can receive them. Rely on **event type** and **registration timing**, rather than assuming any event with "start" in its name happens before context creation.

## 8. Coordinating Within One Event, Not Reordering the Whole Boot Lifecycle

Suppose you have two listeners:

- `@EventListener @Order(-100)` listening for `ApplicationReadyEvent`.
- `@EventListener @Order(100)` listening for `ApplicationStartedEvent`.

Even though `-100` is smaller than `100`, `ApplicationReadyEvent` still happens **after** `ApplicationStartedEvent` in the normal startup sequence. `@Order` **never overrides** the order of events published by `SpringApplication`.

An abbreviated timeline:

```text
Context refresh
    |
    +--> ApplicationStartedEvent
    |      matching listeners sorted by order for this event
    |
    +--> ApplicationRunner / CommandLineRunner
    |
    +--> ApplicationReadyEvent
           matching listeners sorted by order for this event
```

Similarly, when listener A handles event X and synchronously calls `publishEvent(Y)`, listeners for Y can run **nested inside callback A** before the remaining listeners for X are invoked. That is nested event publication, not a broken comparator.

Do not use `@Order` to implicitly express a business flow such as transaction A → database write B → notification C when steps depend on each other's resulting state. When business steps truly depend on one another, use service orchestration, a workflow, or events with explicit contracts—not merely increasing order numbers.

## 9. Synchronous vs. Asynchronous: Invocation Order Differs from Completion Order

### 9.1. Default Mode Is Synchronous

Spring Framework's `SimpleApplicationEventMulticaster` normally invokes matching listeners **directly on the event-publishing thread**, following the sorted list. Picture it as:

```text
publisher.publishEvent(event)
     |
     +--> listener @Order(10): runs and returns
     +--> listener Ordered(20): runs and returns
     +--> listener @Order(30): runs and returns
     |
     +--> publishEvent returns
```

Consequently, a blocking synchronous listener can prolong `publishEvent(...)`, hold the request thread, or slow down startup if the event is published during bootstrap. An unhandled error in a synchronous listener can propagate back to the publisher and block subsequent listeners.

**Advice:** do not put long I/O or unbounded waits inside early startup listeners. If post-refresh work must finish before readiness, consider `ApplicationRunner`/`CommandLineRunner`. For background work, design an explicit executor, retry, and monitoring strategy.

### 9.2. @Async @EventListener

You can use `@EnableAsync` and `@Async` on a listener method, for example:

```java
@Async
@EventListener
@Order(10)
public void sendNotification(OrderCreatedEvent event) {
    // Runs on the configured executor.
}
```

This is an **illustrative snippet**, not standalone, and only runs asynchronously when Spring async support is enabled/configured appropriately. It requires imports for `org.springframework.scheduling.annotation.Async`, `org.springframework.context.event.EventListener`, and `Order`.

Although methods are sorted in the listener list by order, actual work is scheduled/dispatched through the async proxy. If `@Order(10)` takes 2 seconds and `@Order(20)` takes 5 ms, listener 20 can **finish before** listener 10. `@Order` does not create a `join` or `await` barrier.

With async listener methods, exceptions do not propagate back to the publisher the same way as synchronous listeners; inspect `AsyncUncaughtExceptionHandler` or appropriate async results. Async listener methods also have restrictions on returning events to republish via `@EventListener`'s return-value mechanism.

### 9.3. Custom ApplicationEventMulticaster with TaskExecutor

Some applications configure `applicationEventMulticaster` with a `TaskExecutor` to dispatch listeners on separate threads. Even then, the comparator may determine **iteration/scheduling order**, while tasks across threads do not necessarily complete in that order. There are also listeners that declare they do not support async execution; they must run on the publisher thread per the corresponding API, such as certain transactional listeners.

If your design demands strict **completion** order, use controlled synchronous execution, an explicit task chain, or a single-threaded executor with appropriate bounds. Do not treat `@Order` alone as sufficient to guarantee cross-thread ordering.

### 9.4. Listener Failures Alter Observable Execution

With the default synchronous multicaster **having no `ErrorHandler` catching exceptions**, an earlier listener throwing an error can halt multicasting and prevent later listeners from running. With a custom error handler or executor, error behavior may differ.

When debugging "listener order looks wrong," check whether any listener is throwing exceptions or running asynchronously before concluding Spring sorted incorrectly.

## 10. TransactionalEventListener and Transaction-Bound Ordering

`@TransactionalEventListener` differs from regular `@EventListener` in that the callback is bound to a **transaction phase**, for example:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(10)
public void onPaymentCommitted(PaymentEvent event) {
    // Runs after the transaction commits successfully.
}
```

This is an **illustrative snippet** requiring imports for `TransactionalEventListener`, `TransactionPhase`, `Order`, and a `PaymentEvent` definition. In transactional applications, such listeners are normally deferred until the chosen phase rather than running immediately when the event is published.

**Never use order numbers to invert transaction boundaries.** An `AFTER_COMMIT @Order(-10)` listener cannot run before `BEFORE_COMMIT` just because of a negative number. When coordinating multiple transactional listeners in the same phase, `@Order` is one input; however, transaction presence, phase, thread, and callback ordering still depend on the transaction synchronization mechanism.

If an event is published outside a transaction, `@TransactionalEventListener` normally does not run unless fallback execution is enabled on the annotation. That is why a listener "missing" a callback is not necessarily an ordering bug.

## 11. Listeners in a Context Hierarchy Can Receive Events Multiple Times

Spring Boot can run parent/child contexts. Events published in a child context can also be propagated to ancestor contexts. As a result, a listener interested in an event type **may be invoked multiple times** for events coming from different contexts.

`@Order` only sorts listeners within the active dispatch set; it does not enforce **a global order across all contexts** and has no duplicate-event suppression feature. With a hierarchy:

- Identify which context published the event.
- Check which context the listener belongs to.
- For `SpringApplication` events carrying a context, compare the event's context with the injected local context when filtering is needed.
- Use correlation IDs in logs to distinguish separate dispatches.

Do not confuse the same callback appearing twice with the comparator picking two positions.

## 12. Common Misconceptions and How to Handle Them

| Symptom / misconception | Possible cause | How to check / fix |
| --- | --- | --- |
| "`@Order(100)` ran before `@Order(10)`" | The two callbacks belong to different events or use async | Compare event types and threads; compare order only within one dispatch |
| "Whichever listener registers first always runs first" | Spring sorts by order, not purely declaration order | Set `Ordered`/`@Order` explicitly |
| "`@Order` makes a bean instantiate earlier" | Confusing callback sorting with bean lifecycle | Check `@DependsOn` and dependency graph |
| "`@Order(-100)` lets `@EventListener` catch `ApplicationStartingEvent`" | Listener bean was not created/registered at early milestone | Register via `SpringApplication.addListeners` or `spring.factories` |
| "`@Order` on the class controls all `@EventListener` methods" | Method listener adapters read metadata on the method | Place `@Order` on each method that needs ordering |
| "Equal order numbers still have a guaranteed order" | Tie-breaking order is not a contract to rely on | Assign distinct numbers or remove the dependency |
| "`Ordered#getOrder()` and `@Order` on the same instance add up" | Both express the order value | Pick one clear source of order |
| "Async `@Order(10)` definitely finishes before `@Order(20)`" | Completion depends on executor and task duration | Use dedicated completion coordination if needed |
| "Listener 20 did not run so order is wrong" | Listener 10 threw an exception, filter/condition failed, or event type mismatched | Check exceptions, `@EventListener(condition=...)`, and event payload |
| "Order controls transaction phases too" | Phases have their own lifecycle | Use `@TransactionalEventListener` with the right phase |
| "An event heard twice is caused by `@Order`" | Context hierarchy or duplicate listener registration | Inspect context/event identity and registrations |
| "Callbacks always run on the publisher's thread" | Custom multicaster or `@Async` | Check executor, thread name, and error propagation |

### 12.1. Listener Order Debugging Checklist

1. Record the exact **event type name** and publishing context. Different events must be analyzed separately.
2. List **all matching listeners**: `ApplicationListener<T>`, `@EventListener` methods, whether conditions exist, and whether registered before the event fired.
3. Record **order values**: `Ordered#getOrder()` or `@Order` on method/class. Flag ties where two listeners share the same order.
4. Record **thread names** and check for `@Async` or a custom multicaster executor.
5. Check exceptions/`ErrorHandler`; one failing callback can block later callbacks.
6. If the event involves a DB transaction, inspect `TransactionPhase` and actual transaction presence.
7. If parent/child contexts exist, check event propagation and the listener's context.
8. Write tests with dedicated events and distinct order values rather than relying on bean declaration order.

Diagnostic logs should include timestamp, event class, callback, order, thread, and a **non-sensitive** correlation ID. Never log tokens, customer data, or secret payloads just to trace sorting.

## 13. Self-Check Questions

**Question 1.** An `@EventListener @Order(5)` method and an `ApplicationListener` implementing `Ordered#getOrder() == 20` both listen synchronously to the same event. Which is invoked first?

**Answer:** The `@Order(5)` method is typically invoked first because 5 is less than 20, under standard dispatcher/ordering behavior.

**Question 2.** Two methods both have `@EventListener @Order(10)`. Which runs first?

**Answer:** You must not rely on any ordering between methods sharing the same order; assign distinct orders if ordering is required.

**Question 3.** Is placing `@Order(-100)` on a bean listening for `ApplicationStartingEvent` enough?

**Answer:** No. `ApplicationStartingEvent` fires very early; you must register the listener at bootstrap rather than waiting for component scanning.

**Question 4.** Can `@Order(10)` make `ApplicationReadyEvent` happen before `ApplicationStartedEvent`?

**Answer:** No. Listener order does not alter the sequence of event types in the Spring Boot lifecycle.

**Question 5.** Why can `@Async @EventListener @Order(10)` log after `@Order(20)`?

**Answer:** Sorting listeners does not guarantee **completion** order of asynchronous tasks.

**Question 6.** Should you use `@Order` to force singleton A to be created before singleton B?

**Answer:** No. Use dependency injection and `@DependsOn` when controlling valid lifecycle creation constraints.

**Question 7.** Does the runner in the example print `07 publish: after` before or after the three custom event callbacks?

**Answer:** After all three callbacks in the default configuration because the multicaster is synchronous and no callback throws an exception.

**Question 8.** Can a `@TransactionalEventListener(AFTER_COMMIT)` listener be ordered to run before commit via a negative order?

**Answer:** No. Transaction phases define timing boundaries; order only applies within callbacks eligible for that same phase.

## 14. Summary and References

- **`Ordered#getOrder()`** programmatically supplies a listener class's priority; **`@Order`** declares a fixed value, especially convenient directly on `@EventListener` methods.
- **Smaller numbers take precedence earlier**, yet **comparison applies only among listeners participating in the same event dispatch**.
- **Synchronous default:** callbacks typically execute sequentially; `publishEvent` returns after callbacks succeed. **Async:** `@Order` does not guarantee completion order.
- **Bean listeners do not receive events published before they are registered.** Early startup events require `SpringApplication.addListeners(...)`/`spring.factories`.
- **Listener order ≠ bean initialization order ≠ event publication order ≠ transaction phase.** Distinguish them before using `@Order` for coordination.

Official sources aligned with Spring Boot 3.x / Spring Framework 6.1:

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), early listener registration and startup event sequence.
- [Spring Framework 6.1 — Ordered API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/Ordered.html), meaning of order values and priority constants.
- [Spring Framework 6.1 — EventListener API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/event/EventListener.html), `@Order` on event listener methods.
- [Spring Framework 6.1 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html), synchronous default, executor, and error handler.
- [Spring Framework — Ordering Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html), example of `@Order` on `@EventListener` methods.

In production designs, treat ordering as **callback execution priority** rather than a workflow orchestration engine with dependencies, transactions, and retries. If B strictly depends on A succeeding, express that relationship through explicit APIs, services, or workflows instead of merely placing `@Order(10)` ahead of `@Order(20)`.
