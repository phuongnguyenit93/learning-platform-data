# ApplicationEventPublisherAware and Choosing Narrow Contract Injection in Spring Framework

## Objectives

In the Spring Core Container, a bean sometimes needs to use a service provided by `ApplicationContext` itself. For **publishing internal events**, there is no need to bring the entire `ApplicationContext` into business code. Spring provides the **`ApplicationEventPublisher`** interface solely responsible for publishing events, and the **`ApplicationEventPublisherAware`** callback for the container to supply the publisher to the bean after creation.

This lesson belongs to the **Aware Callbacks** group and focuses on two directly related topics:

1. When Spring detects and invokes `ApplicationEventPublisherAware.setApplicationEventPublisher(...)`, and why this callback works.
2. Why you should **depend on the narrow `ApplicationEventPublisher` contract** (typically via constructor injection) rather than bringing the entire `ApplicationContext`/`ApplicationContextAware` into a service that only needs to publish events.

Upon completion, you will be able to write both the Aware callback and constructor injection approaches, publish/receive events with `@EventListener`, distinguish synchronous from async dispatch, write unit tests without booting a context, and recognize key limitations of Spring's internal event bus.

## 1. The Big Picture: A Bean Needs One Part of the Context's Capabilities

`ApplicationContext` extends container APIs and offers many features: retrieving beans, publishing events, reading messages, loading resources, managing lifecycle, and more. Yet a service that publishes business events typically only needs:

~~~java
publisher.publishEvent(event);
~~~

If the service depends directly on `ApplicationContext`, it can also call `getBean(...)`, look up resources, or control the container beyond its original need. This widens its dependencies and forces unit tests to mock many unnecessary capabilities.

Spring provides a narrow contract:

~~~java
package org.springframework.context;

@FunctionalInterface
public interface ApplicationEventPublisher {
    void publishEvent(Object event);

    // Overload for ApplicationEvent declared in the actual API.
    // default void publishEvent(ApplicationEvent event) ...
}
~~~

This is an **abbreviated API description**, not source code to create in your application. The actual import is:

~~~java
import org.springframework.context.ApplicationEventPublisher;
~~~

`ApplicationContext` extends `ApplicationEventPublisher`, so a context itself can act as the publisher. That does not mean a service must reference the context through the `ApplicationContext` type. It can know only the publisher interface.

~~~text
                     Spring ApplicationContext
                              |
                 implements ApplicationEventPublisher
                              |
                +-------------+--------------+
                |                            |
    ApplicationEventPublisherAware     Constructor injection
    setApplicationEventPublisher(...)  (ApplicationEventPublisher)
                |                            |
                +-------------+--------------+
                              |
                              v
                         Service bean
                              |
                        publishEvent(...)
                              |
                              v
                     ApplicationEventMulticaster
                              |
                              v
                    @EventListener / listener
~~~

**Scope of `ApplicationEventPublisher`:** this is an API for publishing **Spring application events** inside the context's eventing system. It is not a durable message broker like Kafka, not an HTTP publisher, and does not automatically guarantee events are persisted to disk or sent to another machine.

## 2. What Is an Aware Callback?

Spring defines the marker interface `org.springframework.beans.factory.Aware`. Its specialized sub-interfaces let a bean request a container infrastructure object via a callback. For example:

| Interface | Parameter Supplied by Spring | When Appropriate |
| --- | --- | --- |
| `BeanNameAware` | Bean name in BeanFactory | Infrastructure needing to know the bean name |
| `BeanFactoryAware` | `BeanFactory` | Infrastructure component genuinely needing the factory |
| `ApplicationContextAware` | `ApplicationContext` | Framework integration needing broad context APIs |
| `ApplicationEventPublisherAware` | `ApplicationEventPublisher` | Bean needing to publish application events |
| `MessageSourceAware` | `MessageSource` | Bean needing message/i18n resolution |
| `ResourceLoaderAware` | `ResourceLoader` | Bean needing only to load resources |

Notice that `ApplicationEventPublisherAware` clearly states the **need to receive a publisher**, whereas `ApplicationContextAware` grants a much broader dependency.

### 2.1. The ApplicationEventPublisherAware Interface

Signature:

~~~java
package org.springframework.context;

public interface ApplicationEventPublisherAware
        extends org.springframework.beans.factory.Aware {

    void setApplicationEventPublisher(
            ApplicationEventPublisher applicationEventPublisher);
}
~~~

This is a **formal API excerpt for explanation**, not a Java file to create in your project.

To use it:

~~~java
import java.util.Objects;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;

public class AuditPublisher implements ApplicationEventPublisherAware {
    private ApplicationEventPublisher publisher;

    @Override
    public void setApplicationEventPublisher(
            ApplicationEventPublisher publisher) {
        this.publisher = Objects.requireNonNull(publisher);
    }

    public void audit(String action) {
        publisher.publishEvent(new AuditOccurred(action));
    }
}
~~~

`AuditOccurred` is an application-defined event type (for example, a record as in Section 6). This is an **illustrative snippet depending on a custom event type**, not yet a standalone compilable program.

Here Spring invokes the setter **automatically** when `AuditPublisher` is a Spring-managed bean inside an `ApplicationContext` with the corresponding processor. There is no need to call `setApplicationEventPublisher(...)` yourself in business code.

### 2.2. When the Container Invokes the Callback

Simplified lifecycle flow:

~~~text
BeanDefinition is registered
    |
    v
Constructor/factory method creates bean instance
    |
    v
Populate regular dependencies/properties
    |
    v
ApplicationContextAwareProcessor handles supported Aware callbacks
    |
    +--> ApplicationEventPublisherAware.setApplicationEventPublisher(...)
    |
    +--> ApplicationContextAware.setApplicationContext(...) if the bean implements it
    |
    v
Initialization callbacks (@PostConstruct, InitializingBean, init-method)
    |
    v
Bean ready for use
~~~

According to the Javadoc, `setApplicationEventPublisher(...)` is called **after populating regular properties but before initialization callbacks**, and before `ApplicationContextAware.setApplicationContext(...)` if the same bean implements both. Do not turn callback ordering into a business coordination mechanism; it is a container lifecycle contract.

**Important note:** the supplied publisher is usually the current context itself, provided through a **narrow interface type**. If you cast it back to `ApplicationContext` just to retrieve extra beans, you defeat the design goal of the narrow contract.

### 2.3. Who Actually Invokes the Callback?

Merely implementing the interface has no effect when a bean is created with `new`. `ApplicationContextAwareProcessor` is the Spring component responsible for infrastructure callbacks related to the application context, event publisher, resource loader, and message source.

When you write:

~~~java
AuditPublisher audit = new AuditPublisher();
audit.audit("created");
~~~

no container calls the setter, so `publisher` will be `null` and the call fails. For code running outside Spring, you must pass a real/fake publisher manually or switch to constructor injection.

## 3. Why Is ApplicationEventPublisher a Narrow Contract?

Compare:

~~~java
// Broad dependency: has access to many container APIs.
class LegacyService {
    private final ApplicationContext context;

    LegacyService(ApplicationContext context) {
        this.context = context;
    }

    void complete(String id) {
        context.publishEvent(new Completed(id));
    }
}
~~~

~~~java
// Narrow dependency: service only has the event publishing API.
class FocusedService {
    private final ApplicationEventPublisher publisher;

    FocusedService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void complete(String id) {
        publisher.publishEvent(new Completed(id));
    }
}
~~~

Both snippets are **illustrative code**, requiring the corresponding Spring imports and `Completed` event type. For publishing events, the runtime behavior is similar; however, the second constructor signature expresses the exact capability the service needs.

Benefits:

- **Reduces dependence on broad container APIs:** the service does not gain `getBean()`, `getEnvironment()`, or resource loading just because it wants to publish events.
- **Clearer responsibility:** reading the constructor immediately shows what the object does.
- **Easier unit testing:** you only need an `ApplicationEventPublisher` implementation that records events.
- **Avoids service locator:** prevents pulling additional beans by name/type in the middle of methods.
- **Easier to swap implementations:** you can use a fake publisher or another adapter without needing the entire context.
- **Clarity on dependency availability:** constructor injection creates the service already holding a valid dependency; there is no window where the instance exists with an unpopulated publisher field.

The term "narrow contract" here refers to the **API surface a consumer can call**, not a claim that the context's internal implementation only knows how to publish events.

## 4. Two Ways to Receive the Publisher: Aware Callback and Constructor Injection

### 4.1. Aware: Container Injects the Publisher After Bean Creation

~~~java
@Component
public class PaymentService implements ApplicationEventPublisherAware {
    private ApplicationEventPublisher publisher;

    @Override
    public void setApplicationEventPublisher(ApplicationEventPublisher publisher) {
        this.publisher = Objects.requireNonNull(publisher);
    }

    public void confirm(String paymentId) {
        publisher.publishEvent(new PaymentConfirmed(paymentId));
    }
}
~~~

This snippet illustrates a Spring-managed component requiring `@Component`, `Objects`, and Spring interface imports. The `PaymentConfirmed` event is application-defined.

**Advantages:** compatible with configuration/extension API styles that rely on Aware; the framework supplies the publisher without changing constructor signatures.

**Drawbacks:** the dependency is injected after the constructor, the field cannot be `final`, the object is not ready for immediate use when constructed directly with `new`, and readers see less of the dependency when inspecting the constructor.

### 4.2. Constructor Injection: Expressing Dependencies Explicitly

~~~java
@Component
public class PaymentService {
    private final ApplicationEventPublisher publisher;

    public PaymentService(ApplicationEventPublisher publisher) {
        this.publisher = Objects.requireNonNull(publisher);
    }

    public void confirm(String paymentId) {
        publisher.publishEvent(new PaymentConfirmed(paymentId));
    }
}
~~~

This is the option **you should generally choose for new application/service code**. Spring can resolve `ApplicationEventPublisher` during constructor injection because the context supplies the corresponding infrastructure dependency. A single constructor does not even require `@Autowired` in modern Spring configurations.

**There is no need to implement both** for the same purpose. If you already constructor-inject `ApplicationEventPublisher`, you normally do not need to implement `ApplicationEventPublisherAware`; conversely, when a framework class requires Aware or lifecycle wiring, the Aware callback is completely valid.

### 4.3. Injecting a Narrow Contract vs. Passing the Whole Context via Constructor

~~~java
public class OverpoweredService {
    private final ApplicationContext context;

    public OverpoweredService(ApplicationContext context) {
        this.context = context;
    }
}
~~~

Even though constructor injection is used, the dependency type here is still the **entire `ApplicationContext`**. The injection technique alone does not guarantee a narrow API: you must pick the **right contract type**.

### 4.4. When Does ApplicationContextAware Actually Make Sense?

An integration component might need to auto-register based on context metadata, load resources, inspect bean names, or handle framework bootstrap. If the job **genuinely** requires broad APIs, `ApplicationContextAware` can make sense. The problem is overusing it in business services merely to call `publishEvent`.

Do not treat `ApplicationContextAware` as a way to "grab any bean anytime" instead of using dependency injection; that hides dependency relationships, increases circular dependency risk, and makes unit testing harder.

## 5. Publishing Events: ApplicationEvent and Payload Objects

`ApplicationEventPublisher` provides these overloads:

~~~java
publisher.publishEvent(new OrderSubmittedEvent(source, orderId));
publisher.publishEvent(new OrderSubmitted(orderId));
~~~

This is an **illustrative snippet**. The first line uses a class extending `ApplicationEvent`, while the second uses an arbitrary object (such as a `record`), supported since Spring 4.2.

### 5.1. Class Extending ApplicationEvent

~~~java
import org.springframework.context.ApplicationEvent;

public final class OrderSubmittedEvent extends ApplicationEvent {
    private final String orderId;

    public OrderSubmittedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String orderId() {
        return orderId;
    }
}
~~~

This is a valid Java class that can be placed in `OrderSubmittedEvent.java` in the same package as the receiving code. `source` in the constructor must be non-null; the event adds custom business data via `orderId`. Extending `ApplicationEvent` fits when integrating with the classic `ApplicationListener<OrderSubmittedEvent>` interface style.

### 5.2. Payload Event Using a Java 17 Record

~~~java
public record OrderSubmitted(String orderId) {}
~~~

This is a valid standalone Java record in `OrderSubmitted.java` (when in the default package) or in a chosen package. It **does not extend `ApplicationEvent`**, yet Spring can publish that record via `publishEvent(Object)`. Spring wraps the payload in a `PayloadApplicationEvent` for infrastructure routing.

A listener using `@EventListener` can declare it directly:

~~~java
@EventListener
public void onOrderSubmitted(OrderSubmitted event) {
    System.out.println("received " + event.orderId());
}
~~~

This is an illustrative method inside a Spring-managed bean. The `@EventListener` annotation belongs to `org.springframework.context.event.EventListener`. Spring selects listeners by event type; you do not have to unwrap `PayloadApplicationEvent` in a handler like this.

**Do not confuse an event object with a durable message:** a record is just a Java data structure. `ApplicationContext` event dispatch does not automatically persist the record to a database, Kafka, outbox, or filesystem.

## 6. Complete Java 17 Example: Aware and Constructor Injection Publishing Events Together

The example uses **Spring Framework 6.2.9**, with no Spring Boot or Servlet needed. The program intentionally uses **the same event record** to compare ways of providing the publisher, while `@EventListener` prints notifications upon receiving events.

### 6.1. Directory Tree

~~~text
publisher-aware-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── PublisherAwareDemo.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>publisher-aware-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. src/main/java/demo/PublisherAwareDemo.java

~~~java
package demo;

import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class PublisherAwareDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println("context ready");

            context.getBean(AwareOrderService.class).submit("A-1");
            context.getBean(ConstructorOrderService.class).submit("B-2");
        }
    }

    // A plain Java payload event; no need to extend ApplicationEvent.
    public record OrderSubmitted(String origin, String orderId) {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public AwareOrderService awareOrderService() {
            return new AwareOrderService();
        }

        @Bean
        public ConstructorOrderService constructorOrderService(
                ApplicationEventPublisher publisher) {
            return new ConstructorOrderService(publisher);
        }

        @Bean
        public OrderAuditListener orderAuditListener() {
            return new OrderAuditListener();
        }
    }

    public static class AwareOrderService
            implements ApplicationEventPublisherAware {

        private ApplicationEventPublisher publisher;

        @Override
        public void setApplicationEventPublisher(
                ApplicationEventPublisher publisher) {
            this.publisher = Objects.requireNonNull(publisher);
            System.out.println("aware callback");
        }

        public void submit(String orderId) {
            publisher.publishEvent(new OrderSubmitted("aware", orderId));
            System.out.println("aware publish returned");
        }
    }

    public static class ConstructorOrderService {
        private final ApplicationEventPublisher publisher;

        public ConstructorOrderService(ApplicationEventPublisher publisher) {
            this.publisher = Objects.requireNonNull(publisher);
        }

        public void submit(String orderId) {
            publisher.publishEvent(new OrderSubmitted("constructor", orderId));
            System.out.println("constructor publish returned");
        }
    }

    public static class OrderAuditListener {

        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            System.out.println(
                    "listener " + event.origin() + "/" + event.orderId());
        }
    }
}
~~~

### 6.4. Running the Program

From the `publisher-aware-demo` directory, ensure Java 17+ and Maven are available:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.PublisherAwareDemo
~~~

With the default `AnnotationConfigApplicationContext` configuration, the **program's** stdout (excluding Maven/SLF4J logs if present in the environment) is:

~~~text
aware callback
context ready
listener aware/A-1
aware publish returned
listener constructor/B-2
constructor publish returned
~~~

### 6.5. Exact Line-by-Line Explanation

1. `aware callback` is printed **when Spring creates the `AwareOrderService` bean**, after the `@Bean` factory method returns the instance and before initialization finishes. You do not call the setter in `main`.
2. `context ready` appears once `new AnnotationConfigApplicationContext(AppConfig.class)` has finished refreshing, regular beans are initialized, and `@EventListener` methods are registered.
3. `AwareOrderService.submit("A-1")` calls `publisher.publishEvent(...)`. The listener receives the record payload and prints `listener aware/A-1`.
4. Because the default multicaster is **synchronous**, the listener completes before `publishEvent` returns; next, `aware publish returned` is printed.
5. `ConstructorOrderService` uses the publisher received via constructor without implementing Aware. Event `B-2` goes through the same context event bus; the listener prints `listener constructor/B-2`, then the method prints `constructor publish returned`.

A few observations:

- `ApplicationEventPublisherAware` is not an event listener. It only helps the bean **receive the publisher object**. The bean listening to events is `OrderAuditListener`, thanks to `@EventListener`.
- Using `ApplicationEventPublisher` in a `@Bean` factory method is **narrow-interface injection via dependency resolution**; you do not need to manually register a separate publisher bean.
- The same payload type is published from two different services. The listener distinguishes them using the `origin` field defined by the example itself—Spring does not automatically attach source metadata.
- `OrderSubmitted` is a static nested record, validly named in Java as `PublisherAwareDemo.OrderSubmitted`. All classes in the example live in one file as shown in the directory tree, so no separate files are required.
- Spring Boot is not needed to use `ApplicationEventPublisherAware`, as long as the object is a bean registered in a properly configured `ApplicationContext`.

## 7. Do Aware Callbacks Replace Dependency Injection?

**No.** `ApplicationEventPublisherAware` is a form of **container-managed callback injection**: the container invokes a method after creating the bean instance. Constructor injection is another way to declare dependencies.

Comparison by criteria:

| Criterion | `ApplicationEventPublisherAware` | Constructor Injection `ApplicationEventPublisher` |
| --- | --- | --- |
| Where dependency is declared | Implement interface and setter | Constructor parameter |
| When received | After instantiation/property population, before init | In the constructor |
| Can use `final` field | No, with a pure setter | Yes |
| Does bean created with `new` work immediately? | No, must call setter manually | Yes, if caller passes publisher |
| Clarity when reading constructor | Publisher not visible in signature | Explicit |
| Depends on Spring lifecycle callback | Yes | No Aware callback needed |
| Exposed API if keeping exact type | `ApplicationEventPublisher` only | `ApplicationEventPublisher` only |
| Suitable for new application code | When Aware contract makes sense | Usually preferred |
| Suitable for framework/extension beans | Very useful | Also suitable if framework supports it |

A bean can still implement Aware to satisfy an extension point it participates in. It is best to pick **one primary source of dependency** per publisher, avoiding situations where the constructor passes publisher A while an Aware setter overwrites it with publisher B, making behavior unpredictable.

## 8. Unit Testing Narrow Contracts Without Booting a Spring Context

Because `ApplicationEventPublisher` is a functional interface, you can use a lambda to record events instead of starting a Spring container. **Java 17 + Spring API** example showing how to test `ConstructorOrderService`:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.context.ApplicationEventPublisher;

// Code inside a test method, not a standalone file.
List<Object> published = new ArrayList<>();
ApplicationEventPublisher fakePublisher = published::add;

PublisherAwareDemo.ConstructorOrderService service =
        new PublisherAwareDemo.ConstructorOrderService(fakePublisher);

service.submit("T-1");

if (published.size() != 1) {
    throw new AssertionError("Expected exactly one event");
}

Object event = published.get(0);
if (!(event instanceof PublisherAwareDemo.OrderSubmitted submitted)) {
    throw new AssertionError("Wrong event type");
}
if (!submitted.orderId().equals("T-1")) {
    throw new AssertionError("Wrong order id");
}
~~~

This snippet is **illustrative test logic**, not a file with a class/`main`, and does not require running JUnit separately to understand the principle. Since `service.submit` also prints a line, running it has a stdout side effect; the assertions verify the event list independently of whether any real listener exists.

Similar check for Aware:

~~~java
List<Object> published = new ArrayList<>();
ApplicationEventPublisher fakePublisher = published::add;

PublisherAwareDemo.AwareOrderService service =
        new PublisherAwareDemo.AwareOrderService();

service.setApplicationEventPublisher(fakePublisher);
service.submit("T-2");

// Verify published contains one OrderSubmitted(origin="aware", orderId="T-2").
~~~

In the second case, the test **must invoke the setter itself** because there is no Spring-managed lifecycle. That is the ergonomic difference between Aware and constructor injection, even though both can be tested with a fake publisher.

### What the Test Above Proves and Does Not Prove

It proves the service **invokes the publisher with the right payload**. It does not prove Spring registers listeners or that events are dispatched through the multicaster. To test end-to-end, create an `AnnotationConfigApplicationContext` as in Section 6, or write a Spring integration test with an appropriate listener/test event recorder.

If a business service depends directly on `ApplicationContext`, creating a fake just for `publishEvent` becomes much harder because you must mock a broad interface or boot a real context. That is a major reason to choose a narrow dependency.

## 9. Publish and Receive: The Publisher Contract Does Not Mandate Synchronous or Asynchronous Execution

`ApplicationEventPublisher.publishEvent(...)` means **handing an event off to the event publishing infrastructure**. The interface does not promise that every listener runs synchronously, asynchronously, or immediately. The `ApplicationEventMulticaster` and listener configuration decide that.

### 9.1. Synchronous by Default

With the Spring context's default `SimpleApplicationEventMulticaster` and no async task executor configured, regular listeners are invoked **on the publisher's thread**. In that case:

~~~text
service.submit()
    |
    +-- publisher.publishEvent(event)
    |      |
    |      +-- listener1.onEvent(event)  (runs and returns)
    |      +-- listener2.onEvent(event)  (runs and returns)
    |
    +-- publishEvent() returns
    |
    +-- service continues
~~~

That is why Section 6's example has deterministic stdout ordering. If a listener throws a `RuntimeException` and the multicaster has no alternative error handler, the exception can propagate to the caller of `publishEvent` and prevent subsequent listeners from running. Do not treat `publishEvent` as "guaranteed fire-and-forget that never fails".

### 9.2. When Configured as Async

Common options:

- Annotating individual listeners with `@Async` alongside `@EnableAsync` and a valid executor.
- Configuring the `applicationEventMulticaster` bean with `SimpleApplicationEventMulticaster.setTaskExecutor(...)`.
- Offloading major side effects to a queue/event broker when durability or out-of-process retries are needed.

With async execution, `publishEvent` may return before listeners finish. Exceptions from `@Async void` listeners do not automatically propagate back to the caller; appropriate error handling/observability must be used. `ThreadLocal` state such as security context, transaction context, and MDC does not transfer across worker threads without a propagation strategy.

Choosing constructor injection or Aware **does not make events async**. That is the responsibility of the event-receiving infrastructure.

### 9.3. Events and Transactions

If a synchronous listener runs on the publisher's thread, it can see the current transaction context if a transaction is active. However, that does not mean the event is persisted after commit.

For side effects that must execute after transaction commit, you can use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` in the appropriate Spring Transaction module, or a transactional outbox for stronger durability. By default, `@TransactionalEventListener` does not run when no transaction is active (unless `fallbackExecution = true` is configured).

Saying "the event was published" does not mean "the transaction committed", "other listeners definitely succeeded", or "a message was sent over the network".

## 10. Where Can Events Be Published From and Who Receives Them?

The bean publishing an event must belong to an active `ApplicationContext`, or be passed an appropriate `ApplicationEventPublisher` implementation. Event-receiving beans are also normally **registered in the same context** via `@Component`, `@Bean`, or listener registration.

Example annotation listener:

~~~java
@Component
public class ShippingListener {

    @EventListener
    public void afterOrderSubmitted(OrderSubmitted event) {
        // Read event data and perform the desired action.
    }
}
~~~

This snippet belongs in the same package/with valid imports and assumes an `OrderSubmitted` type exists. If referencing the nested record from Section 6 in another class, write `PublisherAwareDemo.OrderSubmitted` or import the nested type.

Conditions that are often overlooked:

1. **The listener must be a bean**, and Spring must detect `@EventListener` during context creation/refresh.
2. The event type must match the listener's argument. A listener for `InvoiceGenerated` does not automatically receive `OrderSubmitted`.
3. Do not publish business events from a **bean constructor** before the listener system is fully registered.
4. `@PostConstruct` can also be too early for publishing business events, because lifecycle initialization does not mean the context has completed listener registration. If you truly need an event after context startup, pick an appropriate hook such as `ContextRefreshedEvent` (Core) or `ApplicationReadyEvent` (Spring Boot) depending on your target.
5. `ApplicationEventPublisherAware` only supplies the publisher; it does not automatically register the object as a listener without `@EventListener`/`ApplicationListener`.
6. A hierarchy of parent/child contexts can affect where listeners are registered and propagation: events published from a child context can propagate up to the parent; they do not by default broadcast downward from parent to every child.
7. Lazy listeners may not register as expected if infrastructure does not initialize them along the right path. Avoid applying `@Lazy` to event listeners without understanding the lifecycle.

### @EventListener Compared to ApplicationListener

Two options for receiving events:

~~~java
@Component
class ModernListener {
    @EventListener
    public void receive(OrderSubmitted event) {
        // Handler discovered by Spring via annotation.
    }
}
~~~

~~~java
@Component
class ClassicListener
        implements ApplicationListener<OrderSubmittedEvent> {

    @Override
    public void onApplicationEvent(OrderSubmittedEvent event) {
        // Type-safe handler for a class extending ApplicationEvent.
    }
}
~~~

These snippets require importing `Component`, `EventListener`, `ApplicationListener`, and the corresponding event types. `ClassicListener` must accept a type extending `ApplicationEvent`, whereas `@EventListener` can accept a **payload record** like `OrderSubmitted`. Do not write `ApplicationListener<OrderSubmitted>` if `OrderSubmitted` is just a plain record; `ApplicationListener`'s generic contract requires `ApplicationEvent`.

## 11. Should You Define an Application Interface Even Narrower Than Publisher?

`ApplicationEventPublisher` is already much narrower than `ApplicationContext`, yet it is still a **Spring API** and allows publishing any `Object`. If the domain/application layer must stay Spring-independent or only publish one kind of event, you can define your own **port**:

~~~java
public interface OrderEventSink {
    void submitted(String orderId);
}
~~~

The business service depends on `OrderEventSink`:

~~~java
public final class CheckoutUseCase {
    private final OrderEventSink events;

    public CheckoutUseCase(OrderEventSink events) {
        this.events = events;
    }

    public void checkout(String orderId) {
        // Execute use case logic.
        events.submitted(orderId);
    }
}
~~~

Spring adapter:

~~~java
@Component
public class SpringOrderEventSink implements OrderEventSink {
    private final ApplicationEventPublisher publisher;

    public SpringOrderEventSink(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void submitted(String orderId) {
        publisher.publishEvent(new OrderSubmitted(orderId));
    }
}
~~~

This is a **set of architectural snippets**; each public type needs its own file and proper package/imports, and `OrderSubmitted` must have a matching constructor/record. It is not a standalone runnable project; the runnable example in Section 6 uses Spring's publisher directly.

The adapter design makes sense when a system needs a clear boundary between domain and framework or supports multiple backends (Spring events, a broker, test fakes). Do not add a custom abstraction when there is only a small service and `ApplicationEventPublisher` already meets the need well; abstraction overhead must be justified.

## 12. Common Errors and Diagnostics

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `publisher` is null when calling a method | Class implements Aware but was created with `new`; Spring did not invoke setter | Register as a Spring bean or inject publisher via constructor |
| Setter `setApplicationEventPublisher` is not called | Bean is not in the right ApplicationContext or Aware processing is not applied | Check bean registration, lifecycle processors, and context |
| Code only needs to publish but implements `ApplicationContextAware` | Unnecessarily broad dependency and service locator | Switch to constructor injection of `ApplicationEventPublisher` or `ApplicationEventPublisherAware` |
| Listener does not receive event | Listener is not a Spring bean, wrong context, wrong event type | Register in the right context and verify type/filter |
| Event published in constructor is missed by listener | Context has not finished infrastructure/listener registration | Publish after context is ready and when business triggers occur |
| Runtime exception in listener breaks the calling service | Synchronous dispatch by default with no error handler configured | Design error handling or offload long work to async/broker |
| `publishEvent` returns before listener finishes | Async listener/multicaster configured | Do not assume synchronous execution once infrastructure is customized |
| ThreadLocal/transaction/security context disappears in listener | Listener runs on a different thread | Use a propagation strategy or pass required data in the payload |
| `@EventListener` method does not fire | Method/class not managed by Spring or type mismatch | Check component scanning, `@Bean` registration, and event types |
| `ApplicationListener<OrderSubmitted>` fails to compile | Payload record does not extend `ApplicationEvent` | Use `@EventListener` with payload or create an event extending `ApplicationEvent` |
| Event after DB update causes receiver to read uncommitted data | Published inside transaction with synchronous listener or wrong phase | Use `@TransactionalEventListener` appropriately; understand commit/rollback semantics |
| Event is "lost" on application crash | Spring application events are not a durable queue | Use an outbox/message broker with durability/retries when needed |
| Injecting `ApplicationEventPublisher` works without declaring a bean yourself | Confusing context internal infrastructure with user-defined beans | In a normal context, Spring resolves the publisher via infrastructure; no separate `@Bean` is needed |
| Tests must boot all of Spring just to verify payload | Service depends on broad `ApplicationContext`/lifecycle callbacks | Inject the narrow interface and a fake publisher in unit tests |

### Brief Investigation Steps

1. Is there a bean definition for both publisher and consumer in the required **ApplicationContext**?
2. If using Aware: did Spring invoke the setter **before the business method ran**?
3. If using constructor injection: was the `ApplicationEventPublisher` dependency resolved?
4. Is the event an `ApplicationEvent` or a payload object? Is the listener expecting the right type?
5. Was the listener discovered/registered? Are there `@Lazy` annotations, event filters/conditions, or context hierarchies?
6. Is the multicaster synchronous or asynchronous? How are listener exceptions handled?
7. Does the expected business behavior depend on transaction commit/durability? If so, Spring in-process events alone may not suffice.

## 13. Design and Testing Checklist

- [ ] When only event publishing is needed, declare the dependency as **`ApplicationEventPublisher`** instead of `ApplicationContext`.
- [ ] Prefer **constructor injection** for new application code; implement `ApplicationEventPublisherAware` only when callback/lifecycle extensions call for it.
- [ ] Aware beans are **managed by `ApplicationContext`**, never instantiated directly while expecting callbacks to run.
- [ ] Do not publish business events inside constructors before listeners are ready.
- [ ] Event payloads contain only the required data and do not hold mutable entities/sessions/requests outliving their context.
- [ ] Listeners are registered as Spring beans and accept the exact right type.
- [ ] Test both default synchronous dispatch and async behavior if the application configures async execution.
- [ ] Do not assume events are durable or tied to commits.
- [ ] For transactional side effects, consider `@TransactionalEventListener` or an outbox.
- [ ] Unit test publishers with fakes/lambdas; write integration tests to verify listener registration and dispatch.
- [ ] Do not cast the publisher back to `ApplicationContext` just to call `getBean`.
- [ ] With multiple contexts, verify which context owns the publisher/listeners.

## 14. Self-Check Questions

**Question 1. What information does Spring supply to a bean implementing `ApplicationEventPublisherAware`?**  
An `ApplicationEventPublisher` object via `setApplicationEventPublisher(...)`. In standard setups, it is the context enclosing the bean, exposed through the narrow interface.

**Question 2. Is the callback invoked before or after the constructor and `@PostConstruct`?**  
It is invoked after instance creation and regular property population, and before initialization callbacks such as `@PostConstruct`.

**Question 3. Why shouldn't you use `ApplicationContextAware` just to publish events?**  
Because it grants unnecessarily broad APIs, hides dependencies, and encourages the service locator pattern. `ApplicationEventPublisher` expresses the exact capability the service needs.

**Question 4. Once `ApplicationEventPublisher` is injected via constructor, do you still need to implement Aware?**  
No. Constructor injection already supplies the dependency; the Aware callback is an alternative mechanism.

**Question 5. Can a Java 17 record be published even if it does not extend `ApplicationEvent`?**  
Yes. Spring supports payload objects; the framework wraps them in `PayloadApplicationEvent`. `@EventListener` can accept the payload type directly.

**Question 6. Does `ApplicationEventPublisherAware` make a bean an event listener?**  
No. It only supplies the publisher. To receive events, you need `@EventListener` or `ApplicationListener` with proper registration.

**Question 7. When `publisher.publishEvent(...)` returns, are all listeners guaranteed to have finished?**  
Not by interface contract. With the default synchronous multicaster they normally have finished, whereas async configuration allows listeners to keep running after publish returns.

**Question 8. Can a service be unit tested without booting a context?**  
Yes, especially a service receiving `ApplicationEventPublisher` via constructor. Use a fake publisher/lambda to capture payloads and assert; with Aware, you must invoke the setter manually.

**Question 9. Why not use Spring in-process events as a complete replacement for a durable broker?**  
Because they do not durably persist events, do not cross JVM boundaries automatically, and do not guarantee retries/acknowledgements if the process crashes.

**Question 10. Why can publishing events inside `@PostConstruct` cause confusion?**  
Because one bean finishing initialization does not guarantee the entire event listener infrastructure has completed registration. Business events should be published once the context is ready and a real trigger occurs.

## Official References

- Spring Framework Reference — [Other Aware Interfaces / Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html).
- Spring Framework Reference — [ApplicationContext: Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html).
- Spring Framework Javadoc 6.2 — [ApplicationEventPublisherAware](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisherAware.html).
- Spring Framework Javadoc 6.2 — [ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html).
- Spring Framework Javadoc 6.2 — [ApplicationContextAwareProcessor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/ApplicationContextAwareProcessor.html).
- Spring Framework Javadoc 6.2 — [EventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html).
