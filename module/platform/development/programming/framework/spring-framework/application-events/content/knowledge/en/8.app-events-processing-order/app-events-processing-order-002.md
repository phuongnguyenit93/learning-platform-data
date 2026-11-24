# Ordered and Priority of Application Event Listeners in Spring Framework

## 1. Objectives

When an event is published using `ApplicationEventPublisher.publishEvent(...)`, multiple listeners can receive that event simultaneously. Spring lets you set priorities to determine **which listener is invoked first** during event distribution. After this lesson, you will be able to:

- Explain the rule that **smaller order values mean higher priority**.
- Use `@Order` on `@EventListener` methods and `Ordered#getOrder()` for `ApplicationListener`-based listeners.
- Verify execution order in a synchronous Spring application.
- Distinguish **listener invocation order** from **completion order**, especially when using `@Async` or transaction-bound listeners.
- Recognize when priority ordering should not be turned into a business dependency mechanism.

## 2. Where Does Spring Order Listeners?

Basic flow:

1. A bean calls `publisher.publishEvent(event)`.
2. `ApplicationEventMulticaster` finds listeners matching the event type.
3. The listeners are sorted according to their order information.
4. The multicaster **invokes/dispatches** the listeners sequentially in that order.

With the default `SimpleApplicationEventMulticaster`, regular listeners run **synchronously on the event-publishing thread**. Therefore, if listener A finishes before the multicaster invokes listener B, a clear order is observed. Calling `publishEvent(...)` usually returns only after synchronous listeners have finished processing. If one listener takes a long time, the event publisher also has to wait.

Important condition: **Order is only compared among listeners that are actually eligible to handle the same event**. `@Order` does not make a listener receive the wrong event type, does not order across two independent `publishEvent` calls, and does not replace transactions or a workflow engine.

## 3. Numbering Rules of `Ordered`

In Spring, the `org.springframework.core.Ordered` interface defines the `int getOrder()` method; the `org.springframework.core.annotation.Order` annotation follows the same value rules.

| Value | Relative Priority | Example |
| --- | --- | --- |
| `-100` | Very high | Precondition validation |
| `-10` | Higher than `0` | Data normalization |
| `0` | Higher than `10` | Internal audit logging |
| `10` | Lower than `0` | Partial UI/display update |
| `Ordered.LOWEST_PRECEDENCE` | Default low priority | Listener without declared order |

- **Smaller numbers are ordered before larger numbers**: `@Order(-10)` comes before `@Order(0)`, which comes before `@Order(10)`.
- Negative numbers are valid; **values do not need to be consecutive**. You can leave gaps like `-100`, `0`, `100` to easily add listeners later.
- `Ordered.HIGHEST_PRECEDENCE` equals `Integer.MIN_VALUE`; `Ordered.LOWEST_PRECEDENCE` equals `Integer.MAX_VALUE`.
- Listeners that do not provide order information are generally treated as having `LOWEST_PRECEDENCE`.
- **Do not rely on a stable order when two listeners have the same order**. The order observed in a specific configuration is not a business contract to depend on long-term.

A smaller value represents **sorting priority**, not that the listener runs on a higher-priority CPU, gets a dedicated thread, or is more likely to succeed.

## 4. Approach 1: `@Order` on `@EventListener` Methods

For listeners declared via annotations, the most intuitive way is to place `@Order` **on the event-handling method itself**.

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class AccountEventHandlers {

    @EventListener
    @Order(-20)
    public void validate(AccountCreatedEvent event) {
        // Invoked before a listener with @Order(0) for the same event.
    }

    @EventListener
    @Order(0)
    public void recordAudit(AccountCreatedEvent event) {
        // Invoked after validate in synchronous dispatch.
    }
}
~~~

This is an **illustrative snippet**, not a standalone program: `AccountCreatedEvent` must be defined and `AccountEventHandlers` must be registered as a Spring bean. A complete runnable example is in Section 6.

When a class has multiple `@EventListener` methods, attaching order directly to each method lets readers clearly see each individual priority. Be sure to import Spring's `@Order` as shown above, avoiding confusion with order annotations meant for other purposes.

## 5. Approach 2: Implementing `Ordered` with `ApplicationListener`

A listener written using the `ApplicationListener<E>` interface can directly implement `Ordered` to return its priority:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;

public class AuditListener
        implements ApplicationListener<AccountCreatedEvent>, Ordered {

    @Override
    public int getOrder() {
        return 0;
    }

    @Override
    public void onApplicationEvent(AccountCreatedEvent event) {
        // Handle event.
    }
}
~~~

The snippet above also requires defining `AccountCreatedEvent` and registering `AuditListener` in the context. The advantage of `getOrder()` is that it can return a value computed from configuration when the design requires per-bean priority. Avoid changing `getOrder()` erratically while the application is running because the listener set may be cached or re-sorted by internal mechanisms.

**Quick comparison:**

| Listener Type | Recommended Priority Setup | Unit Being Ordered |
| --- | --- | --- |
| `@EventListener` method | `@Order(value)` on the method | Listener method adapted by Spring into a listener adapter |
| Class implementing `ApplicationListener<E>` | Implement `Ordered` and return `getOrder()` | Listener instance |
| No priority declared | Leave as default | Typically at `LOWEST_PRECEDENCE` |

You may encounter `@Order` on classes/beans in various Spring components. For this use case, placing `@Order` on the `@EventListener` method or using `Ordered` directly on `ApplicationListener` are the two clearest ways to express intent.

## 6. Runnable Java 17+ Example: Three Listeners, One Event

This example uses **plain Spring Framework**, without Spring Boot and without a database. Two listeners are `@EventListener` methods, and the remaining listener implements `ApplicationListener` and `Ordered`. All three receive the same `SignupEvent`.

### 6.1. Project Structure

~~~text
listener-order-demo/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── example/
                └── ListenerOrderDemo.java
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
}

application {
    mainClass = 'example.ListenerOrderDemo'
}
~~~

Spring version 6.2.x in this example is compatible with Java 17+. You can use the Spring Framework version centrally managed by your actual project instead of this illustrative version number.

### 6.2. Complete Source Code

`src/main/java/example/ListenerOrderDemo.java`:

~~~java
package example;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

public class ListenerOrderDemo {

    public static final class SignupEvent extends ApplicationEvent {
        private final String username;

        public SignupEvent(Object source, String username) {
            super(source);
            this.username = username;
        }

        public String username() {
            return username;
        }
    }

    public static class AnnotatedHandlers {

        @EventListener
        @Order(-10)
        public void validate(SignupEvent event) {
            System.out.println("[-10] validate " + event.username());
        }

        @EventListener
        @Order(10)
        public void notifyUser(SignupEvent event) {
            System.out.println("[10] notify " + event.username());
        }
    }

    public static class AuditListener
            implements ApplicationListener<SignupEvent>, Ordered {

        @Override
        public int getOrder() {
            return 0;
        }

        @Override
        public void onApplicationEvent(SignupEvent event) {
            System.out.println("[0] audit " + event.username());
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(AnnotatedHandlers.class);
            context.registerBean(AuditListener.class);
            context.refresh();

            context.publishEvent(new SignupEvent(context, "Linh"));
        }
    }
}
~~~

### 6.3. Run and Verify the Output

From the project root directory, with Java 17+ and Gradle (or Gradle Wrapper configured):

~~~bash
gradle run
~~~

Three lines printed by the program, in order:

~~~text
[-10] validate Linh
[0] audit Linh
[10] notify Linh
~~~

Gradle may print additional build logs; the three lines above are the **stdout of event processing** in the program.

Explanation:

1. `context.refresh()` initializes the context and registers the listeners.
2. `publishEvent(new SignupEvent(...))` publishes a specific event.
3. `AnnotatedHandlers.validate` has order `-10`, so it comes first.
4. `AuditListener.getOrder()` returns `0`, so it comes in the middle.
5. `AnnotatedHandlers.notifyUser` has order `10`, so it comes last.

Method names like `validate` or `notifyUser` and **the order of `registerBean` calls in the example are not what determine priority**. It is the declared order that expresses the desired sequence.

## 7. Synchronous Listeners, Asynchronous Listeners, and the Meaning of Order

### 7.1. Default: Synchronous

When using the default multicaster and all listeners are synchronous, it can be visualized as:

~~~text
Publisher
   |
   +--> listener order=-10  [completed]
   |
   +--> listener order=0    [completed]
   |
   +--> listener order=10   [completed]
   |
   +--> publishEvent(...) returns
~~~

Here, **invocation order** and **completion order** match because each listener finishes before the next listener runs. A synchronous listener throwing an unhandled exception can cause the event publication call to fail and prevent subsequent listeners from being invoked during that dispatch; custom error handling on the multicaster can alter this behavior.

### 7.2. With `@Async`

If an `@EventListener` method also has `@Async` and the application enables async processing (such as `@EnableAsync`), the listener invocation may only schedule the work; the method body runs on another thread:

~~~java
@EventListener
@Order(-10)
@org.springframework.scheduling.annotation.Async
public void slowStep(SignupEvent event) {
    // May complete after listener order=10.
}
~~~

This is a **separate illustrative snippet**, not part of the synchronous example in Section 6. Even though the listener with order `-10` is dispatched first, **you must not infer that the async work will complete before** listener `10`. Exceptions in async listeners are also not automatically propagated back to the caller of `publishEvent` as in synchronous execution.

Similarly, when attaching an asynchronous `TaskExecutor` to `SimpleApplicationEventMulticaster`, async-capable listeners can be submitted to the executor. Certain listener types, especially transaction-synchronized listeners, do not allow running asynchronously that way and still execute on the event-publishing thread. Sorting the listener list does not turn parallel tasks into an ordered completion chain.

**Usage rule:** If B **must** wait for A to produce data, express the dependency via an explicit processing flow or via a follow-up event published only after A succeeds; do not simply write `@Order(A=-10)` and `@Order(B=10)` and enable async.

## 8. Combining with `@TransactionalEventListener`

`@TransactionalEventListener` is a separate mechanism for handling events at a **transaction phase**. By default, it listens at `TransactionPhase.AFTER_COMMIT`, meaning after the transaction commits successfully. Other phases include `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class TransactionBoundHandlers {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Order(0)
    public void updateIndex(SignupEvent event) {
        // Executed after successful commit.
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Order(10)
    public void sendNotification(SignupEvent event) {
        // Has lower priority than updateIndex in the same phase.
    }
}
~~~

This is an **illustrative snippet**, requiring a Spring bean and an actual transaction. If there is no active transaction, `@TransactionalEventListener` **is not invoked by default**; this can be changed with `fallbackExecution = true` if business logic genuinely accepts that.

Two axes must be distinguished:

- **Phase** determines **when** the transactional listener runs relative to the transaction (before commit, after commit, after rollback, etc.).
- **Order** determines **priority among listeners that can execute at the same phase**; it does not make an `AFTER_COMMIT` listener run before a `BEFORE_COMMIT` listener just because its order number is smaller.

For example: `AFTER_COMMIT @Order(-100)` still waits for commit; `BEFORE_COMMIT @Order(100)` belongs to the before-commit phase. Do not use `@Order` to replace the requirement "only send notification after data is written successfully".

## 9. Common Misconceptions and How to Avoid Them

| Misconception | Reality / How to Handle |
| --- | --- |
| `@Order(100)` has higher priority than `@Order(1)` because the number is larger | The opposite: **1 is ordered before 100**. |
| Omitting `@Order` guarantees listeners run in bean declaration order | No business-level ordering contract exists; declare explicit orders if order matters. |
| Two listeners both with `@Order(0)` always run in class name order | Not guaranteed; use different values or design an explicit sequence. |
| `@Order` makes `@Async` tasks complete in order | Only orders dispatch; completion depends on scheduling, processing time, and the executor. |
| `@Order` guarantees transaction commit between listener A and B | No; transaction boundaries are determined by transaction configuration. |
| `@Order` on a listener equals bean initialization order | No; initialization order depends on bean relationships, dependencies, and lifecycle mechanisms. |
| A higher-priority listener is guaranteed to succeed | No; a listener can throw exceptions, time out, or fail due to external systems. |
| `@Order` guarantees durable message delivery | No; application events are an in-application mechanism by default, not a durable queue. |

**Note on `PriorityOrdered`:** Spring also has the marker interface `PriorityOrdered extends Ordered`, used when a group of objects needs to be prioritized ahead of regular `Ordered` objects, regardless of order value. This is a special priority mechanism commonly seen in framework infrastructure. When designing regular application event listeners, starting with `@Order` or `Ordered` is sufficient; only use `PriorityOrdered` if you truly understand and need that grouping semantics.

## 10. Designing Ordered Listeners in Practice

Use order intentionally for listeners that are **independent in data yet have an invocation priority requirement**, such as writing an audit/validation log before a less critical secondary task runs on the same synchronous thread. Define priorities using named constants if multiple listeners need to share a convention:

~~~java
public final class ListenerPriorities {
    private ListenerPriorities() {}

    public static final int VALIDATION = -100;
    public static final int AUDIT = 0;
    public static final int NOTIFICATION = 100;
}
~~~

Then use `@Order(ListenerPriorities.VALIDATION)` to avoid "magic numbers". Values passed to annotations must be compile-time constants, so `public static final int` constants like above are suitable; values read directly from runtime configuration cannot be passed as parameters to `@Order`.

For `Ordered`-style listeners, configuration can be used to determine `getOrder()` per bean, but keep the value stable during normal operation. Avoid solving a multi-step business sequence solely with order:

~~~text
Avoid implicit dependencies:
Event X -> Listener A (writes to database) -> Listener B (reads A's result)

Clearer approach:
Service processes and confirms A -> publishes Event Y
                                 -> Listener B receives Event Y
~~~

If you need to guarantee that messages reach another system even when the application stops or a transaction rolls back, consider durable mechanisms such as **transactional outbox + message broker** according to business requirements. That is a reliability requirement, not a special `@Order` value.

### Checklist Before Using `@Order`

1. Do the listeners genuinely receive the **same event type** in the **same application context**?
2. Do they run synchronously or with `@Async`/a separate executor?
3. Does any listener depend on data produced by another listener? If so, should that dependency be moved to a service or a subsequent event?
4. Is the event published inside a transaction? Which handlers must run after commit?
5. Are there two handlers with the same order causing ambiguous dependencies?
6. Have you verified the actual order with a real publication and clear measurement/logging?

## 11. Self-Check Questions

**Scenario 1.** Three synchronous listeners for the same event have orders `5`, `-1`, `0`. What is the expected invocation order?

**Answer:** `-1 → 0 → 5`.

**Scenario 2.** Listener A has `@Order(-10)` and `@Async`; listener B has `@Order(10)` and runs synchronously. Can A be guaranteed to complete before B?

**Answer:** No. A being dispatched first does not constrain when the async work completes.

**Scenario 3.** One `AFTER_COMMIT` listener has order `-100`, and one `BEFORE_COMMIT` listener has order `100`. Which listener belongs to the before-commit phase?

**Answer:** The `BEFORE_COMMIT` listener. Phase and order are two separate rules.

**Scenario 4.** Two synchronous listeners share order `0`; B's functionality needs new data created by A. What is a good fix?

**Answer:** Do not rely on order when orders are equal. If the dependency has business significance, let a service orchestrate A then B, or publish a new event after A succeeds. Using two different order numbers is only appropriate when the dependency is minor, on the same thread, and explicitly accepted in the design.

## 12. References

- Spring Framework Reference — ApplicationContext: Application Events and **Ordering Listeners**: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Javadoc `Ordered`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/core/Ordered.html
- Javadoc `@Order`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/core/annotation/Order.html
- Javadoc `SimpleApplicationEventMulticaster`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
