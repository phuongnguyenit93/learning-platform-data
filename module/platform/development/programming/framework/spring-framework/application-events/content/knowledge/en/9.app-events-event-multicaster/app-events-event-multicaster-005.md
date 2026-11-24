# Detecting Matching Listeners in Spring Framework Application Events

## 1. Purpose of Listener Detection

When a bean calls `ApplicationEventPublisher.publishEvent(event)`, Spring must determine **which listeners can receive that event type**, then deliver the event to the selected listeners. The same `ApplicationContext` can contain many listeners for payments, inventory, shipping, auditing, or Spring's own lifecycle events. Sending every event to every listener would both waste work and risk handling the wrong data type.

In Spring, the component that performs dispatching is `ApplicationEventMulticaster`. The common implementation is `SimpleApplicationEventMulticaster`, which inherits the ability to manage and **find the list of matching listeners** from `AbstractApplicationEventMulticaster`.

Business examples:

- `PaymentReceived`: payment listeners need to receive it; inventory listeners do not.
- `InventoryLow`: inventory listeners need to receive it; payment listeners do not.
- Two `PaymentReceived` events with the same Java type but different `source` types: a listener can register to receive only events originating from `CheckoutSource`.
- Among listeners that match by type, an `@EventListener(condition = "...")` method can still skip the event if the business condition is not satisfied.

**Distinguish clearly:** "found in the matching listener list" is the candidate-selection step by event type and, when supported, source type. Whether "the method actually runs" also depends on annotation conditions, transaction phases, execution configuration, and other factors.

## 2. Path from Publisher to Listener

At a conceptual level, the default synchronous flow is:

```text
A bean calls publishEvent(event)
         |
         v
ApplicationContext
         |
         v
ApplicationEventMulticaster.multicastEvent(...)
         |
         v
Retrieve registered listeners
         |
         v
Match event type / source type
         |
         v
Matching listener list
         |
         v
Invoke listeners (and check condition/phase if present)
```

Key roles:

| Component | Responsibility |
| --- | --- |
| `ApplicationEventPublisher` | API for application code to publish an event |
| `ApplicationEventMulticaster` | Coordinates finding and invoking listeners |
| `AbstractApplicationEventMulticaster` | Manages the listener set, selects candidates, and supports caching lookup results |
| `SimpleApplicationEventMulticaster` | Common multicast implementation; invokes listeners synchronously by default if no executor is configured |
| `ApplicationListener<E>` | Listener by event type `E`, where `E extends ApplicationEvent` |
| `GenericApplicationListener` | Listener capable of checking the event's `ResolvableType` and the `source` type |
| `@EventListener` | Declares a handler method; Spring creates a listener adapter to participate in the dispatch mechanism |

The diagram is an illustrative mental model, not a guarantee of every internal class or call order across all Spring releases. In particular, a method listener can be **selected first** and only evaluate its `condition` expression when the adapter prepares to invoke the target method.

## 3. Where Are Listeners Registered?

A listener can only be found if Spring already knows about it.

### 3.1. Beans Implementing `ApplicationListener<E>`

```java
@Component
public class PaymentAuditListener
        implements ApplicationListener<PaymentReceived> {

    @Override
    public void onApplicationEvent(PaymentReceived event) {
        // Record audit for payment event.
    }
}
```

The illustration above assumes `PaymentReceived extends ApplicationEvent`. For beans within the `ApplicationContext`'s component scan, Spring automatically discovers and registers the listener. You can also declare a bean returning `ApplicationListener<PaymentReceived>` with `@Bean`.

The generic type `PaymentReceived` is an important part for Spring to determine the supported event type. Avoid implementing `ApplicationListener` as a **raw type** without a specific reason, because event type inference becomes ambiguous.

### 3.2. Methods Annotated with `@EventListener`

```java
@Component
public class PaymentNotifications {

    @EventListener
    public void onPayment(PaymentReceived event) {
        // Notify when PaymentReceived is received.
    }
}
```

This class does not need to implement `ApplicationListener`. During context initialization, the `@EventListener` annotation processing mechanism discovers matching methods and registers adapters for the multicaster to use. The method parameter type helps Spring infer the event type of interest.

For Java objects that do not extend `ApplicationEvent`, Spring still supports `publishEvent(Object)`: the event can be wrapped into a `PayloadApplicationEvent`. An `@EventListener` method accepting the **payload type** can still be selected. Conversely, the `ApplicationListener<E>` interface requires `E` to be an `ApplicationEvent`; if you want to listen for payloads using this interface, you must handle the corresponding wrapper event type.

### 3.3. Registering via the Multicaster API

An `ApplicationEventMulticaster` also has APIs such as `addApplicationListener(...)` and `addApplicationListenerBean(...)`. Applications typically let `ApplicationContext` handle registration automatically rather than controlling the multicaster directly. Manual registration is useful in special integrations, but you must manage the lifecycle and remove the listener when no longer needed. Do not manually double-register a listener already managed by Spring.

**Note on scope:** listeners are tied to their respective `ApplicationContext`. If the application has parent/child contexts, you must consider where the event is published and how events propagate between contexts; do not assume every listener across the entire application is in the same list.

## 4. What Criteria Does Spring Use to Determine "Matching"?

### 4.1. Event Type

For example, `ApplicationListener<PaymentReceived>` is interested in `PaymentReceived`; `ApplicationListener<InventoryLow>` is interested in `InventoryLow`. Spring uses resolvable type information rather than waiting until listener code casts the object to discover whether it matches.

Inheritance also matters: a listener declaring a parent event type can match child events. This can be useful for general auditing, but can also cause the listener to receive more events than intended.

For complex generic events, Spring uses `ResolvableType` to represent detailed type information when available. However, Java generics undergo type erasure at runtime; if Spring does not have enough type information from the event class or metadata, you need an appropriate event / `ResolvableTypeProvider` design. You should not assume `List<OrderPaid>` and `List<OrderCancelled>` can always be distinguished at runtime just because the generics are written in source code.

### 4.2. Source Type (`source type`)

An `ApplicationEvent` has `getSource()`. A listener can distinguish the **Java class of the source object** via `supportsSourceType(Class<?> sourceType)` if it implements a supporting interface such as `GenericApplicationListener` or `SmartApplicationListener`.

Example:

```java
@Override
public boolean supportsSourceType(Class<?> sourceType) {
    return sourceType != null
            && CheckoutSource.class.isAssignableFrom(sourceType);
}
```

This snippet matches only when the source is `CheckoutSource` or a subtype. This is **filtering by the type of `source`**, not filtering by properties such as `checkoutId`, `tenantId`, or a `sourceName` string. If you want to inspect data inside the source, use a business condition in an appropriate handling layer.

### 4.3. `@EventListener(condition)`

```java
@EventListener(condition = "#p0.paymentId() == 'P-101'")
public void onSelectedPayment(PaymentReceived event) {
    // Runs only for paymentId P-101.
}
```

This method is a listener of **type** `PaymentReceived`. It can appear in the listener set selected by the multicaster for `PaymentReceived`, but the adapter only invokes the method when the SpEL expression evaluates to `true`. `#p0` means the first parameter; this notation does not depend on preserving parameter names at compile time.

Therefore, when debugging, ask two separate questions:

1. Is the listener **registered and matching the event/source type**?
2. After being selected, is it **allowed to run** according to the condition, transaction phase, and current execution mode?

## 5. Runnable Example: Event Type, Source Type, and Condition

This example uses JDK 17+, Spring Framework 6.2.0, and Maven. It demonstrates three ways of registering listeners in the same application: `ApplicationListener<T>`, `@EventListener`, and `GenericApplicationListener`.

**Directory structure**

```text
listener-selection-demo/
├── pom.xml
└── src/main/java/example/ListenerSelectionDemo.java
```

**File `pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>listener-selection-demo</artifactId>
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
                    <mainClass>example.ListenerSelectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**File `src/main/java/example/ListenerSelectionDemo.java`**

```java
package example;

import java.util.Set;
import java.util.TreeSet;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.GenericApplicationListener;
import org.springframework.core.ResolvableType;

public class ListenerSelectionDemo {

    public record CheckoutSource(String name) {}
    public record WarehouseSource(String name) {}

    public static final class PaymentReceived extends ApplicationEvent {
        private final String paymentId;

        public PaymentReceived(Object source, String paymentId) {
            super(source);
            this.paymentId = paymentId;
        }

        public String paymentId() {
            return paymentId;
        }
    }

    public static final class InventoryLow extends ApplicationEvent {
        private final String sku;

        public InventoryLow(Object source, String sku) {
            super(source);
            this.sku = sku;
        }

        public String sku() {
            return sku;
        }
    }

    // Collects results to display in a deterministic order.
    // The example intentionally runs synchronously without async.
    public static final class Evidence {
        private final Set<String> lines = new TreeSet<>();

        public void record(String value) {
            lines.add(value);
        }

        public void print() {
            lines.forEach(System.out::println);
        }
    }

    public static final class AnnotatedListeners {
        private final Evidence evidence;

        public AnnotatedListeners(Evidence evidence) {
            this.evidence = evidence;
        }

        @EventListener
        public void onPayment(PaymentReceived event) {
            evidence.record("annotation: " + event.paymentId());
        }

        @EventListener(condition = "#p0.paymentId() == 'P-101'")
        public void onChosenPayment(PaymentReceived event) {
            evidence.record("condition: " + event.paymentId());
        }

        @EventListener
        public void onInventory(InventoryLow event) {
            evidence.record("inventory: " + event.sku());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Evidence evidence() {
            return new Evidence();
        }

        @Bean
        public AnnotatedListeners annotatedListeners(Evidence evidence) {
            return new AnnotatedListeners(evidence);
        }

        @Bean
        public ApplicationListener<PaymentReceived> typedListener(
                Evidence evidence) {
            return event ->
                    evidence.record("typed: " + event.paymentId());
        }

        @Bean
        public GenericApplicationListener sourceFilteredListener(
                Evidence evidence) {
            return new GenericApplicationListener() {
                @Override
                public boolean supportsEventType(ResolvableType eventType) {
                    return PaymentReceived.class.isAssignableFrom(
                            eventType.toClass());
                }

                @Override
                public boolean supportsSourceType(Class<?> sourceType) {
                    return sourceType != null
                            && CheckoutSource.class.isAssignableFrom(
                                    sourceType);
                }

                @Override
                public void onApplicationEvent(ApplicationEvent event) {
                    PaymentReceived payment = (PaymentReceived) event;
                    evidence.record("generic: " + payment.paymentId());
                }
            };
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new PaymentReceived(
                    new CheckoutSource("web"), "P-101"));

            context.publishEvent(new PaymentReceived(
                    new WarehouseSource("batch"), "P-102"));

            context.publishEvent(new InventoryLow(
                    new WarehouseSource("warehouse"), "SKU-7"));

            context.getBean(Evidence.class).print();
        }
    }
}
```

**Run command:** from the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

**Lines printed by the program** (excluding runner tool logs if any):

```text
annotation: P-101
annotation: P-102
condition: P-101
generic: P-101
inventory: SKU-7
typed: P-101
typed: P-102
```

`TreeSet` is used in the example only to sort and print results deterministically; **it does not represent the actual execution order of listeners**, is not suitable for counting duplicate deliveries, and is not a safe structure for all asynchronous scenarios.

Explanation of each group of results:

- `typedListener` is `ApplicationListener<PaymentReceived>`: receives both `P-101` and `P-102`, does not receive `InventoryLow`.
- `onPayment` uses `@EventListener` with parameter `PaymentReceived`: receives both payments.
- `onChosenPayment` matches the same event type, but SpEL allows execution only for `P-101`.
- `sourceFilteredListener` uses `GenericApplicationListener`: receives only `PaymentReceived` whose source is `CheckoutSource`. Hence `P-102` from `WarehouseSource` does not produce a "generic" line.
- `onInventory` receives only `InventoryLow` and prints `SKU-7`.
- The context publishes some lifecycle events on its own (such as during refresh or close); the listeners declared here do not print for them because they do not match the type.

**Why is the cast in `GenericApplicationListener` safe in this example?** The `onApplicationEvent` method casts to `PaymentReceived` only after `supportsEventType` has checked the type. If you later expand the filter to other event types, you must update the handling/casting accordingly.

## 6. How Does Spring Detect Each Type of Listener?

### 6.1. `ApplicationListener<PaymentReceived>`

From the bean's generic type, Spring knows the listener is interested in `PaymentReceived`. In the example above, the multicaster does not need to invoke `onApplicationEvent` for `InventoryLow` only for the listener to ignore it.

### 6.2. `@EventListener`

Spring finds annotated methods on Spring beans and uses an adapter to register them with the event system. A method with a single event parameter typically uses the parameter type as the event type of interest. The annotation also allows specifying event types explicitly when needed:

```java
// Illustrative example placed inside a Spring bean:
@EventListener(classes = {PaymentReceived.class, InventoryLow.class})
public void onEitherType() {
    // Does not receive the event object in a parameter;
    // only knows one of the two types was published.
}
```

This is an additional illustrative snippet, not part of the runnable example in section 5. When specifying multiple event types without a parameter, the method has no data to distinguish which type just arrived unless the application has a separate mechanism. Normally, you should use listeners with specific parameter types.

### 6.3. `GenericApplicationListener` and `SmartApplicationListener`

`GenericApplicationListener` is appropriate when listener selection logic needs to understand `ResolvableType` or `source` type. For example, `supportsSourceType` is a **source filter** at the listener-lookup stage, not SpEL. `SmartApplicationListener` also supports checking event and source types, but uses a `Class<? extends ApplicationEvent>` API for the event type.

If you need a complex condition based on payload content, consider `@EventListener(condition)` or handling the condition in Java code. `supportsSourceType` receives only the source's class, not the full event object.

## 7. Caching When Finding Listeners: Benefits and Limits

`AbstractApplicationEventMulticaster` can cache listener lookup results so it does not have to re-filter the entire list for every event with the same lookup characteristics. An important lookup key is built from **event type** and **source type**. For instance, multiple `PaymentReceived` events arriving from `CheckoutSource` can usually reuse the candidate selection result.

Three limits must be understood:

1. **Candidate-selection caching is not result caching.** Each `publishEvent` call can still invoke the matching listeners; it does not mean the event is processed only once.
2. **Do not put per-event varying data into type filtering.** For example, `paymentId == 'P-101'` must be evaluated per event; you cannot conclude that every `PaymentReceived` from `CheckoutSource` is `P-101` based on the cache.
3. **Cached results are a conditional implementation detail.** Cacheability depends on type resolvability and class loaders, and when registering or removing listeners, Spring must ensure it does not keep using an outdated candidate set.

Therefore, the first optimization is declaring the right event and source types, rather than building your own cache for business logic inside listeners.

## 8. When Is a Listener Selected Yet Does Not Run?

These are special cases that easily cause confusion:

| Symptom | Likely explanation | How to check |
| --- | --- | --- |
| `@EventListener` method does not run | Bean not registered; wrong parameter type; condition returns false | Check component scan/`@Bean`, event type, SpEL expression |
| `GenericApplicationListener` does not run | `supportsEventType` or `supportsSourceType` returns false | Log the event type and `event.getSource()` class during testing |
| `@TransactionalEventListener` does not run | No active transaction; `fallbackExecution` defaults to false; phase does not match | Test inside a real transaction for both commit and rollback |
| Registered `ApplicationListener<ParentEvent>` receives many events | Child events also belong to the parent type | Use a more specific type or additional conditions |
| A listener is called multiple times | Multiple publications; duplicate registration; system retries | Check publishing sites and registration scope |
| Async listener has not finished when publisher returns | Executor or `@Async` is configured | Wait/synchronize properly in tests, monitor async errors |
| Published a POJO, but an `ApplicationEvent`-based listener does not handle payload as expected | POJO is wrapped into `PayloadApplicationEvent` | Use `@EventListener` with the payload parameter or a listener accepting the appropriate wrapper |

**Type filtering is not business filtering.** In section 5's example, `P-102` is selected for `onChosenPayment` by type `PaymentReceived` but skipped at the condition-evaluation step. If you only look at how many times the method ran, it is easy to conclude mistakenly that the adapter was not registered.

## 9. Ordering, Synchronization, and Exceptions

By default, `SimpleApplicationEventMulticaster` invokes listeners directly on the publishing thread if no `TaskExecutor` is configured. That makes the flow easy to observe, but **you should not depend on default ordering between listeners** to guarantee step A ran before B.

Spring supports ordering mechanisms such as `@Order` and `Ordered` in appropriate contexts. Even so, an event is still a notification that something happened. If business logic requires A to succeed before B can run, express that sequence explicitly in a service/workflow; do not turn multiple independent listeners into an implicitly ordered processing chain.

When configuring an executor or using `@Async`:

- Execution timing changes; do not assume `publishEvent` waits for all callbacks to finish.
- Some listeners, especially transaction-bound listeners, do not support async execution via the multicaster like regular listeners.
- Error propagation back to the publisher differs from synchronous calls. Configure appropriate error handling and failure observability.
- Event data should be immutable; do not use a mutable entity that continues to be updated as a reliable snapshot.

In synchronous mode, an unhandled exception in a listener can propagate to the publish call and interrupt dispatching. With asynchronous mechanisms, errors must be monitored on the corresponding execution thread; do not rely on a `try/catch` around the publisher to catch all callback exceptions.

## 10. Testing Listener Detection

A test suite should clearly demonstrate **event type filtering**, **source type filtering**, and **content-based conditions**. From section 5's example, the expected matrix is:

| Event and source | Typed Payment | Annotation Payment | SpEL `P-101` | Generic Checkout | Inventory |
| --- | --- | --- | --- | --- | --- |
| `PaymentReceived(P-101)` from `CheckoutSource` | Yes | Yes | Yes | Yes | No |
| `PaymentReceived(P-102)` from `WarehouseSource` | Yes | Yes | No | No | No |
| `InventoryLow(SKU-7)` from `WarehouseSource` | No | No | No | No | Yes |

Tests should verify that **the right listeners are called and non-matching listeners are not called**. Beyond primary data, test a subclass of the event type if the application needs inheritance, and a source of a different type with the same display string value to catch mistakes where source name is checked instead of source class.

For `@EventListener(condition)`, test the false case and changes to event properties. If a test needs to count invocations, use counters/spies instead of the demo's `TreeSet` (since a set deduplicates entries). For async listeners, use bounded waiting tools and test synchronization mechanisms; do not assert "not received" simply because the callback has not run yet.

If using `@TransactionalEventListener`, also test transaction commit, rollback, and publishing outside a transaction. These mechanisms affect **invocation timing**, even when the listener already matches by event type.

## 11. Checklist When a Listener Does Not Receive an Event

1. **Right context?** Which `ApplicationContext` is the event published to, and which context holds the listener bean?
2. **Properly registered?** Is the bean created by Spring? For `@EventListener`, is the method on a Spring bean with a valid signature?
3. **Right event type?** Are you publishing an `ApplicationEvent` subclass or a POJO payload wrapped by Spring? Does the generic type have enough information to be resolved?
4. **Right source type?** What class is `getSource()`? Does `supportsSourceType` filter it out?
5. **Right condition?** Does SpEL evaluate to true for this specific event? Is it accessing the wrong property or relying on parameter names?
6. **Right transaction phase?** For transactional listeners, is a transaction actually active and committing/rolling back in the expected phase?
7. **Right observation timing?** If the callback is asynchronous, did the test/logs wait properly and check for execution errors?

## 12. Key Takeaways

In Spring Application Events, listener detection relies on **listener registration in the context**, **event type**, and **source type** when the listener supports that check. `ApplicationListener<E>` provides the generic type, `@EventListener` is converted into an adapter, and `GenericApplicationListener` enables candidate selection by `ResolvableType` and `source type`. The `@EventListener(condition)` condition is evaluated **per event** at invocation time, so do not equate "type-compatible listener" with "method executed".

**Spring reference documentation:**

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events)
- [Javadoc — ApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
- [Javadoc — AbstractApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html)
- [Javadoc — GenericApplicationListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/GenericApplicationListener.html)
