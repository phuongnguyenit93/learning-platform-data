# Event Types and the Listener Selection Mechanism

## Objectives

After this lesson, you can explain how Spring determines the type of a published event, how ApplicationEventMulticaster selects matching listeners, the difference between type-based filtering and SpEL condition filtering, how generic types affect listener selection, and how to control ordering as well as listener registration methods.

## 1. Why Does Spring Need to Determine the Event Type?

An application may publish many kinds of events: OrderPlaced, OrderCancelled, PaymentReceived, UserRegistered, or ContextRefreshedEvent. At the same time, there may be dozens of listeners in the ApplicationContext. Each listener should only be invoked when the event matches its responsibility.

For example:

- A confirmation email listener only cares about OrderPlaced.
- A refund listener only cares about OrderCancelled.
- An audit listener may care about both OrderPlaced and OrderCancelled.
- A Spring lifecycle monitoring listener may care about ContextRefreshedEvent.

If Spring invoked every listener for every event, each listener would have to check the type itself and ignore most events. That approach both wastes work and duplicates dispatching logic across many places.

Spring solves this with **event type matching**: a listener declares the event type it accepts, and Spring matches that type against the actual event type before invoking the listener.

## 2. Two Main Components: Publisher and Multicaster

The publisher is responsible for announcing an event through ApplicationEventPublisher. ApplicationContext implements this contract and delegates dispatching to an ApplicationEventMulticaster.

ApplicationEventMulticaster is the component that manages the list of listeners and broadcasts events to matching listeners. In the default configuration, Spring uses SimpleApplicationEventMulticaster.

General flow:

1. The publisher calls publishEvent(event).
2. ApplicationContext determines the event and its corresponding ResolvableType.
3. ApplicationEventMulticaster retrieves the registered listeners.
4. Spring filters listeners by event type; for listeners that support it, it can also filter by source type.
5. Matching listeners are sorted by priority order and invoked.
6. For listeners using a SpEL condition, Spring evaluates the condition before executing the method.

You can visualize it as:

~~~text
Publisher
   |
   | publishEvent(event)
   v
ApplicationContext
   |
   v
ApplicationEventMulticaster
   |
   +-- Listener A: event type matches? ------ condition true? ---> invoke
   |
   +-- Listener B: event type mismatch --------------------------> skip
   |
   +-- Listener C: event type matches? ------ condition false? --> skip
   |
   +-- Listener D: event type matches? ------ condition true? ---> invoke
~~~

Listener selection is a step handled by Spring's infrastructure. The publisher only needs to publish the event at the right time with the right data, without finding or calling each listener itself.

## 3. Where Is the Event Type Determined From?

### With ApplicationEvent

If the publisher passes an object extending ApplicationEvent, the event class type is the basis for Spring to determine matching listeners.

Example:

~~~java
public class OrderPlacedEvent extends ApplicationEvent {

    private final String orderId;

    public OrderPlacedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

A listener can declare the exact type:

~~~java
@EventListener
void onOrderPlaced(OrderPlacedEvent event) {
    System.out.println(event.getOrderId());
}
~~~

A listener declaring only OrderPlacedEvent will not be invoked for another event that has no compatible type relationship.

### With Plain Object Payloads

Spring Framework allows publishing a POJO or record that does not extend ApplicationEvent:

~~~java
eventPublisher.publishEvent(
        new OrderPlaced("DH-3001", new BigDecimal("120000"), "WEB"));
~~~

Spring wraps this object in PayloadApplicationEvent. When determining listeners for the payload, Spring uses the payload's type information to support listeners directly declaring the OrderPlaced type.

~~~java
@EventListener
void onOrderPlaced(OrderPlaced event) {
    System.out.println(event.orderId());
}
~~~

Listeners do not have to declare PayloadApplicationEvent<OrderPlaced> if they only need business data. When a listener needs to read the wrapper, it can declare PayloadApplicationEvent<OrderPlaced> and access getPayload().

### Supertypes and Subtypes

Listener selection is based on type compatibility. If an event is a subtype of the type declared by a listener, the listener for the supertype can receive that event.

For example, OrderPlacedEvent extends OrderEvent:

~~~java
abstract class OrderEvent extends ApplicationEvent {

    protected OrderEvent(Object source) {
        super(source);
    }
}

final class OrderPlacedEvent extends OrderEvent {

    public OrderPlacedEvent(Object source) {
        super(source);
    }
}
~~~

A listener accepting any OrderEvent:

~~~java
@EventListener
void auditOrder(OrderEvent event) {
    System.out.println("Audit order event");
}
~~~

A listener accepting only OrderPlacedEvent:

~~~java
@EventListener
void sendConfirmation(OrderPlacedEvent event) {
    System.out.println("Send confirmation");
}
~~~

When OrderPlacedEvent is published, both listeners have compatible types. If another event also extending OrderEvent is published, the audit listener can still receive it, while the sendConfirmation listener will not be invoked.

This is why event hierarchies should be organized around meaningful business relationships. Avoid creating an overly broad superclass just so multiple listeners can conveniently receive events.

## 4. ApplicationListener Declares the Accepted Event Type

ApplicationListener is an interface with a generic type parameter:

~~~java
public interface ApplicationListener<E extends ApplicationEvent> {
    void onApplicationEvent(E event);
}
~~~

The generic parameter E specifies the type of ApplicationEvent the listener is interested in.

Example:

~~~java
@Component
public class OrderPlacedListener
        implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        System.out.println("Order placed");
    }
}
~~~

Spring can read the generic type OrderPlacedEvent to identify the matching listener. This approach has the advantage of being explicit and type-safe, though one class typically focuses on a single event type declared in the generic parameter.

For plain payload events, ApplicationListener does not directly accept an arbitrary POJO because the interface's generic bound is ApplicationEvent. You can register ApplicationListener<PayloadApplicationEvent<OrderPlaced>> if you need to work at the wrapper level, or use @EventListener to declare the payload type directly.

## 5. @EventListener Infers the Event Type from the Method Signature

@EventListener allows registering a listener as a method inside a Spring-managed bean:

~~~java
@Component
class OrderListeners {

    @EventListener
    void onOrderPlaced(OrderPlaced event) {
        // Handle OrderPlaced
    }

    @EventListener
    void onOrderCancelled(OrderCancelled event) {
        // Handle OrderCancelled
    }
}
~~~

With a single event type, the method parameter is usually the exact event type the listener accepts. Spring uses the method signature to create an adapter implementing ApplicationListener behind the scenes.

Annotation processing is performed by EventListenerMethodProcessor. The processor detects @EventListener methods on managed beans and registers corresponding listeners with ApplicationEventMulticaster.

An important condition is that the bean must be managed by Spring and discovered during context initialization. Do not mark a bean containing @EventListener as lazy if you want the listener registered as soon as the context starts; a lazy bean may not be instantiated yet, leaving its listener methods unregistered.

### One Method Accepting Multiple Event Types

If the method does not need an event parameter, you can declare multiple classes on the annotation:

~~~java
@EventListener(classes = {
        ContextStartedEvent.class,
        ContextRefreshedEvent.class
})
void handleContextLifecycle() {
    System.out.println("Context lifecycle changed");
}
~~~

When classes contains multiple event types, the method must not declare parameters. If there is only one type in classes, the method may accept one matching parameter.

This approach is useful when multiple events need to trigger the same action that does not depend on event-specific data. If event-specific data is needed, use separate listener methods with concrete parameter types.

## 6. Generic Events and ResolvableType

Spring can filter events by generic type when generic type information is available at runtime.

For example, a system publishes an event when creating an entity. A listener only wants to receive entities of type Person:

~~~java
@EventListener
void onPersonCreated(EntityCreatedEvent<Person> event) {
    // Handle Person
}
~~~

Because Java uses type erasure, generic parameters can be lost at runtime. If you simply publish an instance of a general generic class without providing additional information, Spring may not know whether the actual T is Person or another type.

There are two common ways to preserve generic type information:

### Approach 1: Using a subclass that fixes the generic type

~~~java
class EntityCreatedEvent<T> extends ApplicationEvent {

    private final T entity;

    public EntityCreatedEvent(Object source, T entity) {
        super(source);
        this.entity = entity;
    }

    public T getEntity() {
        return entity;
    }
}

final class PersonCreatedEvent
        extends EntityCreatedEvent<Person> {

    public PersonCreatedEvent(Object source, Person person) {
        super(source, person);
    }
}
~~~

The PersonCreatedEvent subclass fixes T as Person. Spring can resolve the generic type through the class hierarchy.

### Approach 2: Providing ResolvableTypeProvider

If you want to use the generic class directly without creating many subclasses, the event can implement ResolvableTypeProvider:

~~~java
public class EntityCreatedEvent<T>
        extends ApplicationEvent
        implements ResolvableTypeProvider {

    private final T entity;

    public EntityCreatedEvent(Object source, T entity) {
        super(source);
        this.entity = entity;
    }

    public T getEntity() {
        return entity;
    }

    @Override
    public ResolvableType getResolvableType() {
        return ResolvableType.forClassWithGenerics(
                getClass(),
                ResolvableType.forInstance(entity));
    }
}
~~~

When the event is published, ResolvableTypeProvider supplies the actual payload type for Spring to use during listener selection.

For plain payload objects, PayloadApplicationEvent also provides type metadata for the payload. However, if a payload contains generic parameters erased by type erasure that cannot be inferred at runtime, appropriate metadata must be provided instead of assuming Spring always knows the element type.

## 7. GenericApplicationListener and Filtering by Source Type

A standard ApplicationListener declares the event type using a generic parameter. When more advanced control is needed, Spring provides GenericApplicationListener.

This interface allows a listener to declare two capabilities:

- supportsEventType(ResolvableType): does the listener accept this event type?
- supportsSourceType(Class<?>): does the listener accept events published from this source type?

Illustrative example:

~~~java
public final class WebOrderListener
        implements GenericApplicationListener {

    @Override
    public boolean supportsEventType(ResolvableType eventType) {
        return ResolvableType.forClass(OrderPlacedEvent.class)
                .isAssignableFrom(eventType);
    }

    @Override
    public boolean supportsSourceType(Class<?> sourceType) {
        return sourceType != null
                && WebOrderPublisher.class.isAssignableFrom(sourceType);
    }

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        OrderPlacedEvent orderEvent = (OrderPlacedEvent) event;
        System.out.println(orderEvent.getOrderId());
    }
}
~~~

This example illustrates two-dimensional filtering: event type and source type. In production code, choose the right assignability check direction according to the actual event type, and register the listener with the ApplicationContext or multicaster.

GenericApplicationListener is useful when building shared listener infrastructure, plugins, or integration mechanisms with custom filtering rules. For typical business logic, @EventListener or ApplicationListener is usually easier to read and maintain.

## 8. Runtime Filtering with condition

Event type matching determines which listeners can receive an event by type. Sometimes the event type matches, but only certain event instances should trigger the listener.

@EventListener supports the condition attribute containing a SpEL expression:

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
void notifyWebOrder(OrderPlaced event) {
    System.out.println("Notify web order");
}
~~~

In the example, the listener is invoked only when the payload's channel is WEB.

The event listener SpEL context provides:

- event or #root.event: the original published event.
- args or #root.args: the array of arguments used to invoke the listener.
- #a0 or #p0: the first parameter.
- Parameter names such as #orderPlaced: can be used when parameter names are retained in bytecode.

Use #a0 or #p0 when you are unsure whether the compiler option to retain parameter names is enabled. The condition is evaluated when the event arrives and after the listener has been matched by type.

Do not place complex business logic inside condition. Keep conditions short and readable, and move main processing into the listener method.

## 9. Listener Invocation Ordering

Multiple listeners can receive the same event. If a specific order is needed, use @Order:

~~~java
@EventListener
@Order(1)
void writeAudit(OrderPlaced event) {
    System.out.println("Audit");
}

@EventListener
@Order(2)
void sendNotification(OrderPlaced event) {
    System.out.println("Notification");
}
~~~

Lower order values have higher priority and run first. Ordered or @Order can likewise be used on ApplicationListener implementations.

Only use ordering when it has genuine meaning. If the second listener must run after the first because of data or result dependencies, those two steps should likely live in an explicit orchestration service rather than relying implicitly on listener order.

## 10. Event Return Values Also Produce New Events

An @EventListener method can return a non-void object:

~~~java
@EventListener
OrderAuditedEvent audit(OrderPlaced event) {
    // Write audit log...
    return new OrderAuditedEvent(event.orderId());
}
~~~

Spring publishes the return value as a new event. If the method returns an array or Collection, each element is published as a separate event.

This mechanism is useful for short, easy-to-follow reaction chains. However, if the event chain grows long, branches heavily, or requires strict transaction and error control, use an orchestrating service or an explicit workflow.

Asynchronous listeners do not support publishing follow-up events via return values. When handling asynchronously and needing to publish another event, inject ApplicationEventPublisher and call publishEvent explicitly.

## 11. Listener Registration, Execution, and Errors

### Registration methods

There are three common ways:

- Beans implementing ApplicationListener<E>: Spring detects the listener interface when the bean is registered in the context.
- @EventListener methods: EventListenerMethodProcessor creates adapters and registers the methods as listeners.
- Programmatic registration: call addApplicationListener(...) on ConfigurableApplicationContext or ApplicationEventMulticaster when dynamic listener management is needed.

Avoid registering the same listener multiple times if you do not want it invoked repeatedly.

### Default multicaster

Spring defaults to SimpleApplicationEventMulticaster and invokes listeners synchronously on the publishEvent thread. Therefore, the publisher waits for synchronous listeners to finish before continuing.

You can configure a task executor on the multicaster or use @Async on a specific listener. When running asynchronously, exceptions do not propagate back to the publisher synchronously; errors must be observed through an appropriate async handling mechanism. ThreadLocal and logging context are also not automatically propagated to other threads.

### Exception handling

With default synchronous execution and no configured ErrorHandler, runtime exceptions from a listener can propagate back to where the event was published. That means a failing listener can cause the event-publishing flow to fail.

You can configure an ErrorHandler on SimpleApplicationEventMulticaster if you want to change how exceptions are handled. Do not swallow errors silently if listener processing is important to business correctness.

## 12. Complete Example with Java 17 and Spring Framework

The example uses two payload events implementing an OrderEvent interface. One listener receives all events of the interface, one receives only OrderPlaced and only processes orders from the WEB channel, and the remaining listener receives only OrderCancelled.

### Project Structure

~~~text
listener-selection-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ListenerSelectionDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
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
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ListenerSelectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### ListenerSelectionDemo.java

~~~java
package demo;

import java.math.BigDecimal;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Configuration
@ComponentScan(basePackageClasses = ListenerSelectionDemo.class)
public class ListenerSelectionDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             ListenerSelectionDemo.class)) {

            context.publishEvent(
                    new OrderPlaced("DH-3001",
                            new BigDecimal("120000"), "WEB"));

            context.publishEvent(
                    new OrderPlaced("DH-3002",
                            new BigDecimal("80000"), "STORE"));

            context.publishEvent(
                    new OrderCancelled("DH-3003", "Customer request"));
        }
    }
}

sealed interface OrderEvent
        permits OrderPlaced, OrderCancelled {

    String orderId();
}

record OrderPlaced(
        String orderId,
        BigDecimal total,
        String channel) implements OrderEvent {
}

record OrderCancelled(
        String orderId,
        String reason) implements OrderEvent {
}

@Component
class OrderEventListeners {

    @EventListener
    @Order(1)
    void audit(OrderEvent event) {
        System.out.println(
                "Audit: " + event.getClass().getSimpleName()
                        + " " + event.orderId());
    }

    @EventListener(condition = "#a0.channel() == 'WEB'")
    @Order(2)
    void notifyWebOrder(OrderPlaced event) {
        System.out.println("Web notification: " + event.orderId());
    }

    @EventListener
    @Order(3)
    void handleCancellation(OrderCancelled event) {
        System.out.println("Cancellation follow-up: " + event.orderId());
    }
}
~~~

### Running the Program

In the directory containing pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Output:

~~~text
Audit: OrderPlaced DH-3001
Web notification: DH-3001
Audit: OrderPlaced DH-3002
Audit: OrderCancelled DH-3003
Cancellation follow-up: DH-3003
~~~

### Output Analysis

- OrderPlaced and OrderCancelled both implement OrderEvent. Therefore, the audit listener receives both payloads.
- notifyWebOrder only declares OrderPlaced, so it is not invoked when OrderCancelled is published.
- notifyWebOrder's condition is true only for payloads whose channel is WEB. Order DH-3002 from STORE still matches by type but is filtered out at the condition evaluation step.
- handleCancellation only receives OrderCancelled.
- @Order(1), @Order(2), and @Order(3) determine the ordering among listeners matching each respective event.
- The publisher only publishes three objects. It does not check channels, filter listeners itself, or call handler methods directly.

## 13. Common Pitfalls

### Assuming every listener receives every event

Listeners are selected by their declared event type. A listener accepting a specific type ignores incompatible events. If you want to receive multiple types, use a meaningful common supertype/interface or declare classes on @EventListener.

### Confusing event type matching with condition

Event type determines whether a listener is eligible to receive the event. A SpEL condition further filters individual event instances. Using condition instead of an explicit event type usually makes configuration harder to understand.

### Generic types not being resolved

Due to type erasure, a listener declaring EntityCreatedEvent<Person> filters accurately only when the event's generic type is determined through a subclass or ResolvableTypeProvider. Do not rely on generics in source code while ignoring runtime metadata.

### Listener bean not managed by Spring

An object instantiated with new outside ApplicationContext does not automatically become a listener. With @EventListener, the bean must be managed by Spring and the method must be discovered by EventListenerMethodProcessor.

### Relying on listener order for business orchestration

@Order only controls the invocation order of matching listeners. It does not create a shared transaction, guarantee retries, or turn multiple listeners into an atomic workflow.

### Using async while still expecting exceptions to propagate to the publisher

A listener running asynchronously cannot propagate exceptions back to the publishEvent thread synchronously. You must configure and monitor errors on the executor or AsyncUncaughtExceptionHandler.

## 14. Key Takeaways

Spring selects listeners based on the published event type and the type declared by the listener. ApplicationEventMulticaster manages registering, filtering, and invoking listeners. ApplicationListener uses a generic parameter; @EventListener infers the type from the method signature and can optionally add classes or condition.

ResolvableType helps handle generic events when type information is preserved. GenericApplicationListener enables advanced filtering by event type and source type. @Order controls ordering, while @Async changes execution behavior. Understanding these steps helps predict which listeners will be called and avoids making business logic depend on hidden dispatching rules.

## Official References

- [Additional Capabilities of the ApplicationContext — Spring Framework 6.2](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html)
- [ApplicationEventMulticaster — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
- [GenericApplicationListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/GenericApplicationListener.html)
- [EventListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [ResolvableTypeProvider — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/ResolvableTypeProvider.html)