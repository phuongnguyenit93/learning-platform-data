# Using @EventListener for Bean-Managed Listeners in Spring Boot

## 1. Goal: Reacting to Events with a Regular Spring Bean

In Spring Boot, a service class can **publish an event** when an action occurs—for example, when an order is created, a report finishes, or application state changes. Another component will **listen** and perform a related task without forcing the event publisher to call each recipient directly.

**@EventListener** is a Spring Framework annotation used to mark **a method on a bean managed by ApplicationContext** as an event-receiving method. The class is not required to implement **ApplicationListener**; the method parameter type typically determines the event type it handles.

Simple example in an application with component scanning configured:

~~~java
@Component
class AuditListener {

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        System.out.println("Audit: " + event.orderId());
    }
}
~~~

This is a **snippet** assuming an **OrderPlaced** type with an **orderId()** accessor and imports for **@Component** and **@EventListener**. Spring registers this method because **AuditListener is a bean**. When other code calls **ApplicationEventPublisher.publishEvent(new OrderPlaced(...))**, Spring routes the event to the matching method.

**Key points to remember right away:**

- **@EventListener goes on the method**, not on the class; the class containing the method must be managed as a Spring bean.
- **@Component**, **@Service**, **@Configuration**, or a **@Bean** factory method can all create a bean containing a listener, as long as the bean actually exists in the ApplicationContext.
- **@EventListener** does not automatically turn an object created with **new** into a Spring bean.
- By default, the listener receives the event **synchronously on the publishing thread**; there is no durable queue, automatic retry, or delivery guarantee like in a messaging system.
- Bean-based listeners are suitable for events published **after the context is ready to register listeners**. They are **not the way to receive very early SpringApplication events** before the context is created.

This lesson uses **Spring Boot 3.3.x, Spring Framework 6.1, and Java 17+** as its baseline.

## 2. Involved Components and How They Work Together

There are four basic components:

1. **Event**: a Java object describing what just happened. In modern Spring Framework, an event can be any object/record; **it does not have to extend ApplicationEvent**.
2. **ApplicationEventPublisher**: an interface allowing a bean to publish events via **publishEvent(Object event)**.
3. **ApplicationEventMulticaster**: the infrastructure that distributes events to matching listeners. In a standard context, Spring uses **SimpleApplicationEventMulticaster** with synchronous default behavior.
4. **Bean containing @EventListener**: a bean whose method is discovered and registered as a listener by Spring.

~~~text
OrderService / ApplicationRunner
     |
     | publishEvent(new OrderPlaced(...))
     v
ApplicationEventPublisher
     |
     v
ApplicationEventMulticaster
     |
     +--> Bean AuditListener
     |       @EventListener onOrderPlaced(...)
     |
     +--> Bean NotificationListener
     |       @EventListener(condition = "...")
     |
     +--> Bean MetricsListener
             @EventListener onOrderPlaced(...)
~~~

**A single publish can invoke multiple listeners**. The publisher does not need to know the number or names of recipients. With the synchronous default, listeners are called on the publishing thread and **publishEvent(...) usually returns only after synchronous callbacks finish**.

### 2.1. What Should an Event Carry?

A business event should express **something that already happened**, with the minimum data needed for listeners to process it:

~~~java
public record OrderPlaced(String orderId, int priority) {
}
~~~

A record is well suited for a small immutable event. If large or sensitive data needs to be accessed, pass an **ID** rather than an entire JPA entity or secrets in the payload. Avoid passing objects that are mutated concurrently, especially when moving to asynchronous listeners.

Events **do not need to extend ApplicationEvent**:

~~~java
publisher.publishEvent(new OrderPlaced("ORD-100", 5));
~~~

When publishing an object that does not extend ApplicationEvent, Spring can wrap it in **PayloadApplicationEvent** inside the multicaster layer; an **@EventListener** method can still receive **OrderPlaced** directly thanks to payload unwrapping.

### 2.2. How Does @EventListener Differ from ApplicationListener?

| Criterion | @EventListener | ApplicationListener<E> |
| --- | --- | --- |
| Declaration | Annotation on a bean **method** | Interface on a **class/object** |
| Event type selection | Parameter type or **classes/value** | Generic parameter **E** |
| Data-based filtering | Supports **condition** (SpEL) | Write conditional checks in code |
| Publishing follow-up events | Can **return** an event/collection when synchronous | Usually calls the publisher directly |
| Suitable as a regular bean | Yes | Yes |
| Receiving very early events before context | **No** if only a method on a bean | Possible, **if registered directly before run** |

**ApplicationListener** does not automatically gain an advantage in receiving early events if it is created just like a regular bean. The decisive factor is **whether the listener is registered before the event is published**, not merely the interface name.

## 3. Conditions for Spring to Discover @EventListener Methods

Check all three parts:

**One — The bean must belong to the context.** Example:

~~~java
@Component
class OrderEventHandler {

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        // Handle the event.
    }
}
~~~

If the class lies outside **@ComponentScan**, has no **@Import**, and is not declared via **@Bean**, the method will not be discovered. An object created manually outside Spring with **new OrderEventHandler()** will not be registered automatically either.

**Two — The method must have a valid signature.** The most common form takes one event-type parameter and returns **void**:

~~~java
@EventListener
public void handle(OrderPlaced event) {
    // ...
}
~~~

If you want one method to receive **multiple event types** with **no parameters**, you can declare the event classes on the annotation:

~~~java
@EventListener({
    ContextRefreshedEvent.class,
    ContextClosedEvent.class
})
public void onContextLifecycle() {
    // No parameter because the method receives multiple event types.
}
~~~

This is a **snippet** requiring Spring imports; it only illustrates the syntax. When a method has no parameters, the event types must be declared on the annotation. When a method has exactly one parameter, Spring typically infers the event type from that parameter.

**Three — The bean must be initialized/registered at the proper stage.** Spring processes **@EventListener** methods during the container lifecycle using **EventListenerMethodProcessor** and method adapters. Do not explicitly mark a listener bean as **@Lazy** if you want to ensure it is registered to receive events: Spring Framework documentation advises against making such listener beans lazy.

For beans using AOP/proxies, keep the listener method callable through the generated proxy (for example, a public method on an interface when using a JDK dynamic proxy, or an appropriate proxy configuration). If the method exists only on the implementation and the proxy interface does not expose it, Spring may fail to invoke the method via the proxy; inspect the error message and proxy type before troubleshooting.

### 3.1. Do Not Confuse @EventListener with @Bean

**@Bean** is used to create/register a bean. **@EventListener** is used to register **an event-handling method on an already created bean**. Both can be used for their separate roles:

~~~java
@Configuration(proxyBeanMethods = false)
class ListenerConfiguration {

    @Bean
    OrderEventHandler orderEventHandler() {
        return new OrderEventHandler();
    }
}
~~~

The **orderEventHandler()** method creates the bean; **OrderEventHandler.onOrderPlaced(...)** with **@EventListener** is the event callback. Do not place **@EventListener** on the **@Bean** factory method itself.

## 4. Runnable Example: Bean Listener Receiving, Filtering, and Chaining Events

This example deliberately uses an **application without an HTTP server** so stdout is easy to observe, though the **@EventListener** mechanism is the same in Spring MVC or WebFlux applications.

### 4.1. Setting Up the Project

Requires **Java 17+**, Maven 3.9+ (or Maven Wrapper), and Spring Boot 3.3.x. Create a project with the **spring-boot-starter** dependency and package **com.example.events**. A minimal **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>managed-events-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Place the application in **src/main/java/com/example/events/ManagedEventsApplication.java**:

~~~java
package com.example.events;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class ManagedEventsApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ManagedEventsApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("MAIN | active=" + context.isActive());
        }
    }

    public record OrderPlaced(String orderId, int priority) {
    }

    public record ImportantOrder(String orderId) {
    }

    @Bean
    ApplicationRunner publishSampleOrders(ApplicationEventPublisher publisher) {
        return args -> {
            System.out.println("RUNNER | publish normal");
            publisher.publishEvent(new OrderPlaced("ORD-100", 1));

            System.out.println("RUNNER | publish important");
            publisher.publishEvent(new OrderPlaced("ORD-200", 9));

            System.out.println("RUNNER | finished");
        };
    }

    @Component
    static class OrderEventHandlers {

        @EventListener
        @Order(10)
        public void logEveryOrder(OrderPlaced event) {
            System.out.println("LOG | " + event.orderId());
        }

        @EventListener(condition = "#a0.priority() >= 5")
        @Order(20)
        public ImportantOrder handleHighPriorityOrder(OrderPlaced event) {
            System.out.println("FILTER | " + event.orderId());
            return new ImportantOrder(event.orderId());
        }

        @EventListener
        public void handleImportantOrder(ImportantOrder event) {
            System.out.println("FOLLOWUP | " + event.orderId());
        }
    }
}
~~~

Run with Maven from the directory containing **pom.xml**:

~~~bash
mvn -q spring-boot:run
~~~

If the project has the Maven Wrapper, you can use:

~~~bash
./mvnw -q spring-boot:run
~~~

PowerShell on Windows with the Maven Wrapper:

~~~powershell
.\mvnw.cmd -q spring-boot:run
~~~

**The lines printed by the program itself, in expected order** when using the default synchronous multicaster:

~~~text
RUNNER | publish normal
LOG | ORD-100
RUNNER | publish important
LOG | ORD-200
FILTER | ORD-200
FOLLOWUP | ORD-200
RUNNER | finished
MAIN | active=true
~~~

Framework/build tool logs may appear in between those lines. **This is the order of the application's own printed lines**, not a guarantee that the entire stdout consists of only eight lines.

### 4.2. Step-by-Step Analysis

1. **SpringApplication.run(...)** creates and refreshes the ApplicationContext, completing listener bean registration.
2. Spring invokes the **ApplicationRunner** bean after refresh. The runner publishes **OrderPlaced("ORD-100", 1)**.
3. Listener **logEveryOrder** receives every **OrderPlaced** and prints **LOG | ORD-100**. The listener conditioned on **priority >= 5** does not run for this order.
4. The runner publishes **OrderPlaced("ORD-200", 9)**. Listener **logEveryOrder** runs first because **@Order(10)** is smaller than **@Order(20)**.
5. The filtering listener runs for priority 9, prints the **FILTER** line, and returns an **ImportantOrder** object.
6. Spring treats the return value of a **synchronous @EventListener** method as **a new event**, republishing it through the multicaster; **handleImportantOrder** receives this event and prints the **FOLLOWUP** line.
7. The second **publishEvent** completes, and the runner prints **RUNNER | finished**. After **run(...)** returns, main prints **MAIN | active=true**.
8. **try-with-resources** closes the context at the end of the CLI example. Do not use this pattern to close a web application immediately after startup if it needs to serve HTTP requests long-term.

To keep the example predictable, the events here are immutable **Java records**, with no thread pool and no transactions. When enabling async or adding transactional listeners, ordering and timing of effects can change.

### 4.3. Why Is a Nested @Component Still Managed by Spring?

**OrderEventHandlers** is a **static nested** class annotated with **@Component** inside the scanned package, so Spring can register it as a bean. That differs from a non-static inner class, which requires an instance of the outer class.

If you extract OrderEventHandlers into its own **OrderEventHandlers.java** file with **@Component**, the functional result stays the same. In real applications, separating classes by responsibility usually makes code clearer and easier to unit test.

## 5. @EventListener Signatures and Event Selection

### 5.1. Receiving One Event via a Parameter

The clearest and preferred approach:

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Handle a single event.
}
~~~

Spring selects the listener based on the **OrderPlaced** parameter type. The event can be a class, a record, or a type extending **ApplicationEvent**.

### 5.2. One Method Receiving Multiple Event Types

If a method needs to receive **ContextRefreshedEvent** and **ContextClosedEvent**, you can declare:

~~~java
@EventListener({
    ContextRefreshedEvent.class,
    ContextClosedEvent.class
})
public void onContextChange() {
    // Parameterless method.
}
~~~

You can use a method with a suitable common supertype parameter, but when the handling logic actually differs, **two separate methods** are easier to maintain.

### 5.3. Filtering with @EventListener's condition

**condition** is a **SpEL** expression evaluated by Spring before invoking the method. If the expression returns true, the listener executes:

~~~java
@EventListener(condition = "#a0.priority() >= 5")
public void onImportantOrder(OrderPlaced event) {
    // Handle only when priority >= 5.
}
~~~

Here **#a0** is the first parameter of the callback method. Using **#a0** or **#p0** avoids depending on whether the compiler preserves parameter names. Under certain conditions you can use **#event** if parameter names are retained and Spring can resolve the name; do not rely on this while ignoring compiler settings.

An equivalent syntax using the arguments array:

~~~java
@EventListener(condition = "#root.args[0].priority() >= 5")
public void onImportantOrder(OrderPlaced event) {
    // ...
}
~~~

When calling a method on a record, **priority()** is the actual Java accessor, without guessing field names. For other events, write expressions matching real getters/methods.

**Do not turn SpEL into a place for complex business logic.** Simple conditions such as type, state, or thresholds fit well; multi-branch business checks belong in Java methods/services that are unit tested.

### 5.4. Event Subtypes and Generics

Event-typed listeners normally receive events compatible with the registered type. With a generic event like **EntityCreatedEvent<T>**, accurately filtering by **T** requires ensuring type information remains available at runtime: use a concrete subclass or **ResolvableTypeProvider** when necessary. Merely instantiating **new EntityCreatedEvent<Person>(...)** does not guarantee the framework can always retain the generic type argument due to **type erasure**.

This is an advanced concern when building generic event systems. In straightforward business code, naming events after explicit actions (**CustomerRegistered**, **InvoicePaid**) is usually easier to understand and test.

## 6. Methods Returning Events and Limitations of This Mechanism

In our example, the method:

~~~java
@EventListener
public ImportantOrder handleHighPriorityOrder(OrderPlaced event) {
    return new ImportantOrder(event.orderId());
}
~~~

not only handles the original event but also **publishes a follow-up event** via its return value. For synchronous listeners, Spring supports returning:

- **A single object**: that object is published as an event.
- **A Collection** or **array**: each element is treated as an event to publish.
- **void**: no follow-up event is published via return value.

If a method only needs to perform a side effect and has no meaningful new event, use **void**. Do not return an ordinary data value expecting it to be a "processing result" delivered privately to the publisher: Spring may treat it as **another event**, triggering unintended reactions.

**Specifically: an @EventListener method executed asynchronously with @Async must not publish events via its return value.** If you need to publish a follow-up event from an async listener, inject **ApplicationEventPublisher** and call **publishEvent(...)** explicitly.

Avoid creating cycles with no termination condition: event A produces B, and B produces A continuously. With a synchronous multicaster, such a cycle can cause recursion and a stack overflow.

## 7. Synchronous Default: Implications for Performance and Errors

With the default **SimpleApplicationEventMulticaster**, synchronous callbacks run **on the thread calling publishEvent**. That means:

- If a listener takes 500 ms to run, the publisher may have to wait for that duration.
- The listener works on the same thread, so it may see thread-bound context such as an active transaction, but you must not infer that every event automatically has a transaction.
- An exception from a synchronous listener can **propagate back to the caller of publishEvent(...)** and block subsequent processing steps. If the event is published inside an **ApplicationRunner**, an unhandled exception can cause **SpringApplication.run(...)** to fail.
- Each context has its own multicaster; parent/child contexts can cause events from a child to be forwarded to an ancestor, requiring attention to multiple event deliveries.

**Do not treat @EventListener as a background queue by default.** Adding the annotation alone does not move the callback onto a separate thread.

### 7.1. Ordering Between Listeners Using @Order

If two listeners receive the same event type and dispatch order needs to be defined, use **@Order** on the method:

~~~java
@EventListener
@Order(10)
public void first(OrderPlaced event) {
    // ...
}

@EventListener
@Order(20)
public void second(OrderPlaced event) {
    // ...
}
~~~

A **smaller** value is generally called **earlier**. Do not rely on method name order or declaration order in the Java source file.

Once listeners run asynchronously, **@Order** does not guarantee one task will **finish** before another. If B strictly requires A's result, express that dependency via an API, an explicit chain, or a managed workflow rather than relying on completion order of two async listeners.

### 7.2. Use Events for Notifications, Not for Results You Must Wait On

For example, if OrderService needs a **tax calculation result** to confirm an order, calling **TaxService.calculate(...)** directly is more appropriate. If you need to notify analytics that "the order was accepted," an **OrderAccepted** event can help reduce coupling.

Internal events are suitable for **notifications within the same application/context**; they are not a promise of durable delivery or distributed transactions.

## 8. @Async with @EventListener: How It Differs and When to Use It

When a listener performs time-consuming work that does not need to block the publisher, you can use **@Async** on the method and **@EnableAsync** on the application configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncEventsConfiguration {
}
~~~

~~~java
@Component
class EmailNotificationListener {

    @Async
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        // Example: sending an I/O notification, requiring proper timeout/retry.
    }
}
~~~

These two are **snippets** in an application that already has **OrderPlaced** and imports for **@Configuration**, **@EnableAsync**, **@Async**, **@Component**, and **@EventListener**. Spring needs async infrastructure and an appropriate executor configured; in production projects, configure a **ThreadPoolTaskExecutor** with queue bounds, thread counts, thread naming, rejection policy, and shutdown handling.

Important limitations:

1. An **@Async** listener may run on another thread; **publishEvent** does not wait for the callback to finish by default.
2. Exceptions from an async listener **do not propagate directly** back to the publisher; you need logging, an **AsyncUncaughtExceptionHandler**, and an appropriate retry/monitoring strategy.
3. **Do not publish follow-up events via the return value** of an async listener; use **ApplicationEventPublisher.publishEvent**.
4. **ThreadLocal**-based data (such as thread-bound transactions, security context, or MDC) is **not automatically transferred** to another thread in all configurations.
5. **@Order** only helps with invocation/dispatch ordering where applicable; it provides no completion ordering across tasks running concurrently.
6. Use async only when the side effect is not a mandatory precondition before the business operation is considered successful.

**Do not add @EnableAsync to the main example in Section 4**, because the goal there is to print a predictable synchronous order.

## 9. @EventListener and Transactions: When to Use @TransactionalEventListener?

Suppose a service runs inside **@Transactional** and publishes **OrderPlaced**. If a regular listener sends an email immediately, the email can be sent **before the transaction commits**. If the transaction later rolls back, the customer has already received a notification for an order that was never actually saved.

Spring supports **@TransactionalEventListener** to bind an event callback to a transaction phase.

~~~java
@Component
class OrderConfirmationListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCommitted(OrderPlaced event) {
        // Handle only when the associated transaction commits successfully.
    }
}
~~~

This is a snippet requiring imports for **@TransactionalEventListener**, **TransactionPhase**, **@Component**, and the **OrderPlaced** class. Common phases:

| Phase | Timing |
| --- | --- |
| **BEFORE_COMMIT** | Right before commit |
| **AFTER_COMMIT** | After successful commit (**default**) |
| **AFTER_ROLLBACK** | After rollback |
| **AFTER_COMPLETION** | After the transaction finishes, regardless of commit/rollback |

**By default, if no transaction is active**, **@TransactionalEventListener** **does not invoke the callback**. To also handle events when there is no transaction, you can set **fallbackExecution = true**, while understanding that the "after commit only" guarantee no longer applies.

Several important caveats:

- **@EventListener** is generally invoked when the event is published; **@TransactionalEventListener** is bound to a transaction phase.
- Do not place both annotations on the same method hoping for two independent callback flows; choose the right semantics.
- An **AFTER_COMMIT** listener may still see old transaction resources, but **new data writes are not automatically committed as a new transaction**. If you must perform an independent DB write after commit, consider a service with **REQUIRES_NEW** and explicit transaction boundaries.
- In reactive applications, transaction context does not rely on ThreadLocal like imperative transactions; Spring Framework 6.1 provides a corresponding mechanism via Reactor context/event source. Use the right API instead of assuming reactive listeners behave identically to thread-bound transactions.
- **AFTER_COMMIT does not guarantee durable delivery to external systems**. If reliable delivery is needed when the app crashes between commit and publish/consume, consider a **transactional outbox** and a message broker.

Since the example in Section 4 does not open a transaction, replacing **@EventListener** with the default **@TransactionalEventListener** would cause the callback to be skipped; that is the expected behavior according to the annotation's semantics.

## 10. Why Doesn't a Bean @EventListener Catch Very Early SpringApplication Events?

A common mistake is writing:

~~~java
@Component
class EarlyBootListener {

    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        System.out.println("Application starting");
    }
}
~~~

**Do not expect this method to receive the ApplicationStartingEvent of the current run**, because the event is published before the ApplicationContext exists and before listener beans are created/registered. Likewise, **ApplicationEnvironmentPreparedEvent** and **ApplicationContextInitializedEvent** occur during early bootstrap.

Spring Boot recommends **registering listeners before run** for early events:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners((ApplicationListener<ApplicationStartingEvent>) event -> {
    System.out.println("Early startup event");
});
app.run(args);
~~~

This is a snippet assuming **MyApplication** and imports for **SpringApplication**, **ApplicationListener**, and **ApplicationStartingEvent**. The listener is created and registered before run, without relying on bean discovery.

If a library needs an automatic early listener, Spring Boot also supports declaring it in **META-INF/spring.factories** under the key **org.springframework.context.ApplicationListener**.

### 10.1. Which Events Are Suitable for Bean-Based @EventListener?

Events published **after the context is refreshed** are typically suitable, for example:

- **ApplicationStartedEvent**: Spring Boot has refreshed the context, before runners execute.
- **ApplicationReadyEvent**: after runners finish, when the application is nearly done starting up.
- **ContextRefreshedEvent**, **ContextClosedEvent**: ApplicationContext lifecycle events, requiring attention to execution order/hierarchy.
- **Custom domain events** published by beans once the app is running.
- **AvailabilityChangeEvent**: availability state change events; bean listeners can observe these if timely registration is ensured.

**ApplicationPreparedEvent** is published before refresh, so you should not rely on a regular bean listener receiving it. **ApplicationFailedEvent** can occur very early, before the context/listener beans are ready; to catch bootstrap failures at every stage, use an early-registered listener rather than only an `@EventListener` bean.

### 10.2. Parent/Child Contexts and Repeated Event Delivery

In a system with an **ApplicationContext hierarchy**, an event published in a child context can be forwarded to listeners in the parent. If a parent listener performs side effects, it may receive multiple events of the same type from different contexts.

For events extending **ApplicationContextEvent**, the method can compare **event.getApplicationContext()** against the injected context to handle only events from the target context. For custom payload events, you can include a source/context identifier in the payload if distinguishing sources is required. Do not assume a listener runs only once across the whole JVM.

## 11. Testing Bean-Managed Listeners

Two levels should be distinguished:

- **Unit test**: call the Java logic inside the handler directly to verify transformations, validation, and business decisions.
- **Context/integration test**: create a real Spring context, register the bean, and publish an event to verify that Spring discovers **@EventListener**, filters by the right type, and invokes the callback.

The second kind of test is especially useful because **new OrderEventHandlers().handle...** runs the Java method but **does not prove Spring registered it as a listener**.

### 11.1. A Minimal Context Test with JUnit 5

When the project has **spring-boot-starter-test**, create **src/test/java/com/example/events/BeanEventListenerTest.java**:

~~~java
package com.example.events;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BeanEventListenerTest {

    record DemoEvent(String code) {
    }

    static class Recorder {
        final List<String> received = new ArrayList<>();
    }

    static class RecordingListener {
        private final Recorder recorder;

        RecordingListener(Recorder recorder) {
            this.recorder = recorder;
        }

        @EventListener
        public void onEvent(DemoEvent event) {
            recorder.received.add(event.code());
        }
    }

    @Test
    void managedBeanReceivesPublishedEvent() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(Recorder.class);
            context.registerBean(RecordingListener.class);
            context.refresh();

            context.publishEvent(new DemoEvent("EVT-1"));

            assertEquals(
                    List.of("EVT-1"),
                    context.getBean(Recorder.class).received);
        }
    }
}
~~~

To run the test, add the **spring-boot-starter-test** dependency with **test** scope to **pom.xml** from Section 4:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Run:

~~~bash
mvn test
~~~

The test **does not need to start an HTTP server**. **AnnotationConfigApplicationContext** registers the annotation/event processing infrastructure, registers **RecordingListener** as a bean, and publishes **DemoEvent**. If Spring discovers the method, **Recorder.received** contains exactly **EVT-1**.

**@Component is not needed on RecordingListener in this test** because **registerBean(RecordingListener.class)** registers the bean directly into the context. In real applications, you typically use **@ComponentScan**, **@Bean**, or imported configurations rather than programmatic registration like this.

### 11.2. Testing condition Filtering and Ordering

For listeners with **condition**, tests should publish at least two events:

~~~text
Event priority=1 -> listener does not run
Event priority=9 -> listener runs exactly once
~~~

For **@Order**, tests should record a list of callbacks within **the same synchronous context/multicaster** and assert the order. Do not write tests based on thread sleep durations or demand completion ordering across async callbacks.

For **@TransactionalEventListener**, tests need real transactions and must distinguish commit from rollback. Do not simply publish an event in a non-transactional context and conclude the listener is broken.

### 11.3. Why Are Unit Tests Alone Not Enough?

A unit test like:

~~~java
OrderEventHandlers handler = new OrderEventHandlers();
handler.logEveryOrder(new OrderPlaced("ORD-1", 1));
~~~

only proves **the Java method runs**. It does not test component scanning, EventListenerMethodProcessor, SpEL conditions, async proxies, event ordering, or event type matching. Use a context test when those framework behaviors are what you need to verify.

## 12. Common Mistakes and How to Fix Them

### 12.1. Listener Is Not Called Despite Having @EventListener

Check whether the class is a Spring bean, whether it is inside component scan, whether conditional configuration excluded it from the context, and whether the bean is lazy. For methods on a proxy, check whether the proxy can invoke the method. Ensure the event **is published to the same ApplicationContext** where the listener is registered.

### 12.2. Creating the Listener with new Instead of Registering a Bean

**new AuditListener()** creates a Java object but does not automatically add it to the context. Include the class in component scan, configure a **@Bean**, or register it through a Spring-supported mechanism.

### 12.3. Trying to Receive ApplicationEnvironmentPreparedEvent with @EventListener

This event arrives **before the context is created**; use **SpringApplication.addListeners(...)**, builder listeners, or **spring.factories**. Do not wait for Spring to scan beans and expect the framework to replay past bootstrap events.

### 12.4. Publishing an Event and Assuming the Listener Runs in the Background

By default, listeners are **synchronous**. Performing slow I/O inside a listener can block the publisher. Use an appropriate async mechanism only when business rules allow it; add timeouts, queue limits, logging, and error handling for production.

### 12.5. An Exception in a Listener Breaks the Main Operation

In synchronous mode, exceptions can propagate back to the publisher. A failed email notification should not necessarily fail the order creation transaction. Distinguish mandatory conditions from optional side effects; choose transaction phases, async execution, or messaging/outbox as needed.

### 12.6. SpEL Filtering Always Skips the Method or Throws an Expression Error

Check that accessors/properties really exist, along with return types, quote syntax, and parameter references. **#a0** is usually more stable than parameter names if the project does not retain **-parameters** metadata. A SpEL error can cause the event handling path to throw an exception.

### 12.7. Requiring Ordering Without Declaring It Explicitly

Two listeners without **@Order** should not rely on source file position or bean registration order. Declare ordering when truly needed, and verify it with a context test.

### 12.8. Using a Return Value in an @Async Listener to Publish Follow-Up Events

Automatic publishing of return values **is not supported for async listeners**. Inject **ApplicationEventPublisher**, call **publishEvent(...)** explicitly, and take responsibility for exception/retry handling.

### 12.9. @TransactionalEventListener Does Not Run Without a Transaction

This is the default behavior because there is no commit/rollback phase to bind to. If you want to always receive the event, consider a regular listener or **fallbackExecution=true** with clear business semantics.

### 12.10. Listener Invoked Multiple Times in a Multi-Context Setup

Events from a child context can propagate to the parent. If handling the event causes side effects, filter by the right source, ensure idempotency, and consider that the same event type may be published from multiple places.

### 12.11. Confusing Internal Events with a Message Broker

Spring's **ApplicationEventPublisher** is a communication mechanism **within the same application/context**, without durable queues, consumer groups, dead-letter handling, exactly-once semantics, or cross-service delivery. If you need cross-process delivery or crash-safe persistence, use appropriate messaging/outbox patterns.

### 12.12. Listener Doing Too Much Work

When a single method accesses a database, sends HTTP requests, updates caches, and coordinates multiple systems, it becomes hard to test and hard to handle failures. Keep **@EventListener** methods as thin adapters; move complex logic into services with clear contracts, bounded side effects, and a clear separation between synchronous needs and deferrable work.

## 13. Self-Check Questions

**Question 1.** Does an object created with **new OrderEventHandlers()** containing an **@EventListener** method automatically receive Spring events?

**Answer:** No. The object must be managed/registered with the ApplicationContext and the method must be discovered to become a listener.

**Question 2.** Must a custom event extend **ApplicationEvent**?

**Answer:** No. Spring supports publishing ordinary objects/records as events; the framework can use PayloadApplicationEvent under the hood.

**Question 3.** An **@EventListener** method returns **ImportantOrder** in synchronous mode. What does that value mean?

**Answer:** Spring publishes it as a follow-up event so other listeners can handle it.

**Question 4.** To handle only OrderPlaced events with priority 5 or higher, which condition does not depend on compiler parameter names?

**Answer:** **@EventListener(condition = "#a0.priority() >= 5")**, where **#a0** is the first argument.

**Question 5.** One listener has **@Order(10)** and another has **@Order(20)**. Is completion order always guaranteed if both use **@Async**?

**Answer:** No. @Order guides dispatch order but does not guarantee scheduling or completion times for tasks running in parallel.

**Question 6.** Should you use @EventListener on a @Component to receive **ApplicationStartingEvent** for the first startup run?

**Answer:** No. That event occurs before the context and listener beans exist. Register the listener before run via SpringApplication or an appropriate bootstrap mechanism.

**Question 7.** Why can a listener calling a slow external API make publishEvent slow?

**Answer:** Because the default multicaster calls listeners synchronously on the publisher's thread; publishEvent waits for callbacks to finish.

**Question 8.** When does **@TransactionalEventListener** run by default?

**Answer:** After the associated transaction commits successfully (**AFTER_COMMIT**). If there is no transaction, it does not run by default.

**Question 9.** Does a unit test directly calling a handler's Java method verify that Spring registered @EventListener?

**Answer:** No. You need a context/integration test that creates the bean and publishes an event through Spring to verify registration and dispatch.

**Question 10.** If an internal event is published when an order is created, is the event automatically stored durably to replay after a crash?

**Answer:** No. ApplicationEventPublisher is an in-process mechanism by default; durable delivery guarantees require a suitable messaging/outbox architecture.

## 14. Summary and References

**@EventListener is a concise way to declare a listener on a method of a Spring-managed bean.** Spring discovers the method, selects events by parameter type/annotation, optionally filters with SpEL, orders dispatch with @Order, and publishes follow-up events from return values in synchronous mode. This technique is especially well suited for internal domain events and Spring application events that arrive once listener beans are registered.

Remember to distinguish **early events before ApplicationContext** from **post-refresh events**; understand the **synchronous default**, **@Async** limits, **@TransactionalEventListener** semantics, context scope, and the boundary between internal events and message brokers. The fewer unnecessary dependencies a listener has, the easier it is to test and operate.

Official references:

- Spring Framework — Application Events, Annotation-based Event Listeners, Asynchronous Listeners: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework 6.1 — @EventListener API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework 6.1 — ApplicationEventPublisher API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Boot 3.3 — SpringApplication, Application Events and Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html