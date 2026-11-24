# Selecting Listeners by Event Type

## 1. Objectives

In Spring Application Events, a publisher can emit multiple kinds of events, and each kind of event can be of interest to multiple listeners. Spring needs to determine which listeners match the event currently being published. This selection is based on the event type declared by the listener, after which additional filtering conditions can be applied.

For example, a retail application might publish OrderCreatedEvent, OrderCancelledEvent, and PaymentReceivedEvent. A listener watching OrderEvent can handle every event in the order group; a listener declaring only OrderCreatedEvent will receive only order-creation events; a listener watching PaymentReceivedEvent will receive payment notifications.

This lesson focuses on how Spring matches event types to listeners, how to use @EventListener and ApplicationListener, inheritance/interface relationships, POJO payloads, generic events, and common errors when declared types do not match.

After this lesson, you will be able to:
- Explain how Spring selects listeners based on event type.
- Write a listener for a specific type or a group of types via a superclass/interface.
- Distinguish listeners that accept a POJO payload from listeners that accept the PayloadApplicationEvent wrapper.
- Use SpEL conditions for finer filtering after the event type matches.
- Recognize the limits of generic types due to Java type erasure and how to provide type information at runtime.

## 2. Principles of Event Type Matching

For a listener using @EventListener, the method's parameter type indicates which event the listener wants to receive. Spring invokes the method only when the published event type is compatible with the type declared by the method.

The basic rules can be understood as follows:

- A listener declaring OrderCreatedEvent receives OrderCreatedEvent.
- A listener declaring OrderEvent receives concrete events implementing the OrderEvent interface.
- A listener declaring a superclass receives events of its corresponding subclasses.
- A listener declaring an unrelated type will not be invoked for that event.

In terms of Java type relationships, if the event object is assignable to a variable of the listener's parameter type, that listener can be a matching candidate. Spring uses event type information to select listeners inside ApplicationEventMulticaster.

Example:

~~~java
public interface OrderEvent {
    String orderId();
}

public record OrderCreatedEvent(String orderId) implements OrderEvent {
}

public record OrderCancelledEvent(String orderId) implements OrderEvent {
}
~~~

A listener accepting OrderEvent can handle both OrderCreatedEvent and OrderCancelledEvent. A listener accepting OrderCreatedEvent specifically handles only order creation. This lets you organize listeners by business domain group without requiring the publisher to know the list of concrete listeners.

## 3. Using @EventListener to Select by Type

The most common approach in a Spring application is placing @EventListener on a method of a Spring-managed bean. The method parameter itself is the event type the listener cares about.

~~~java
@Component
public class OrderListeners {

    @EventListener
    public void onCreated(OrderCreatedEvent event) {
        System.out.println("Order created: " + event.orderId());
    }

    @EventListener
    public void onCancelled(OrderCancelledEvent event) {
        System.out.println("Order cancelled: " + event.orderId());
    }
}
~~~

When the publisher emits OrderCreatedEvent, Spring invokes onCreated. When the publisher emits OrderCancelledEvent, Spring invokes onCancelled. Neither method needs to be called directly by the publisher.

One bean can have multiple @EventListener methods for different event types. Multiple beans can also subscribe to the same event type; all matching listeners can be invoked.

The listener must belong to a bean inside the ApplicationContext. Placing @EventListener on an object instantiated manually with new without registering it with Spring will not automatically make the method a listener.

## 4. Selecting Listeners by Interface or Superclass

When multiple events belong to the same business group, you can declare a common interface or superclass. A listener accepting that common type will process concrete events that share the corresponding inheritance or implementation relationship.

~~~java
public interface OrderEvent {
    String orderId();
}

public record OrderCreatedEvent(String orderId) implements OrderEvent {
}

public record OrderCancelledEvent(
        String orderId,
        String reason
) implements OrderEvent {
}
~~~

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    public void onAnyOrderEvent(OrderEvent event) {
        System.out.println("Order event: " + event.orderId());
    }

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Dedicated handling for new order: " + event.orderId());
    }
}
~~~

When OrderCreatedEvent is published, both methods match: one method accepts the OrderEvent interface and the other accepts the concrete OrderCreatedEvent type. When OrderCancelledEvent is published, only the method accepting OrderEvent matches in the example above.

This is a useful way to separate shared processing from dedicated processing. For instance, a general listener can write audit logs for all order changes, while a specific listener sends notifications only when an order is created.

If multiple listeners receive the same event and invocation order matters, use @Order or implement Ordered. Smaller order values have higher priority. @Order only orders listeners that match the same dispatch; it does not alter event types and does not turn an incompatible listener into a matching one.

Avoid overusing an overly broad superclass. If an interface merely groups events that share no common processing semantics, listeners accepting that interface may end up performing constant instanceof checks and become hard to maintain. Group events only when they share real behavior or data.

## 5. ApplicationListener and Generic Types

In addition to @EventListener, Spring provides the ApplicationListener<E extends ApplicationEvent> interface. The generic type E specifies the type of ApplicationEvent the listener wants to receive.

Example with an event extending ApplicationEvent:

~~~java
public class OrderCreatedApplicationEvent extends ApplicationEvent {

    private final String orderId;

    public OrderCreatedApplicationEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

~~~java
@Component
public class OrderCreatedApplicationListener
        implements ApplicationListener<OrderCreatedApplicationEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedApplicationEvent event) {
        System.out.println("Order created: " + event.getOrderId());
    }
}
~~~

Spring registers this listener according to the specific ApplicationEvent type declared. ApplicationListener is suitable when you want a bean dedicated to one event type and prefer an interface-based implementation. @EventListener is usually more concise when one bean needs multiple methods listening to different events.

Note the type constraint: ApplicationListener<E> accepts E as an ApplicationEvent. If a publisher emits a regular POJO or record, Spring wraps that payload in PayloadApplicationEvent. To receive the POJO payload directly by its type, use @EventListener with the payload type as the parameter, or use ApplicationListener<PayloadApplicationEvent<...>> when you truly want to work with the wrapper.

## 6. POJO Events and PayloadApplicationEvent

Since Spring Framework 4.2, a publisher can emit an ordinary Java object; the object does not need to extend ApplicationEvent:

~~~java
eventPublisher.publishEvent(new OrderCreatedEvent("ORD-1001"));
~~~

Spring represents this POJO using PayloadApplicationEvent. With @EventListener, Spring can match by payload type and pass the payload directly to the method:

~~~java
@EventListener
public void onCreated(OrderCreatedEvent event) {
    System.out.println(event.orderId());
}
~~~

The method above receives OrderCreatedEvent without needing to manually unwrap PayloadApplicationEvent.

If you want to receive the wrapper along with event metadata, you can declare the listener for PayloadApplicationEvent:

~~~java
@EventListener
public void onPayload(PayloadApplicationEvent<?> event) {
    Object payload = event.getPayload();
    System.out.println("Payload type: " + payload.getClass().getName());
}
~~~

Distinguish between the two declarations. A listener accepting the payload type is suitable when you need business data directly. A listener accepting PayloadApplicationEvent is suitable when you need to handle the wrapper or observe multiple payload types. Do not confuse a POJO payload with an event class extending ApplicationEvent.

## 7. Further Filtering with Conditions

The event type determines which group of listeners can receive an event. In some cases, a listener only needs to handle a subset of events of the same type. @EventListener supports the condition attribute to apply a SpEL expression for further filtering.

For example, only handle payments of 1,000 or more:

~~~java
@Component
public class PaymentListeners {

    @EventListener(condition = "#root.args[0].amount() >= 1000")
    public void onLargePayment(PaymentReceivedEvent event) {
        System.out.println("Large payment: " + event.amount());
    }
}
~~~

The condition is evaluated after the listener has already been considered a match by event type. If the condition returns false, the method is not called. #root.event references the dispatched ApplicationEvent; for POJOs/records, that is the PayloadApplicationEvent wrapper. #root.args[0] is the first argument of the listener, i.e., the payload the method receives directly.

Do not use condition as a substitute for clear event type design. If two groups of occurrences have distinct business meanings, two separate event types are usually easier to read and test than a single generic event with many conditional branches.

## 8. Generic Events and Type Erasure

Java erases generic type parameter information at runtime in many situations. For example, two objects GenericEvent<Order> and GenericEvent<Customer> may share the same runtime class GenericEvent. Therefore, relying solely on the generic type declared in source code may not be enough to distinguish specific payloads when Spring inspects the event at runtime.

If Spring needs to distinguish generic event types, the event can implement ResolvableTypeProvider to provide a complete ResolvableType:

~~~java
import org.springframework.core.ResolvableType;
import org.springframework.core.ResolvableTypeProvider;

public class EntityCreatedEvent<T> implements ResolvableTypeProvider {

    private final T entity;

    public EntityCreatedEvent(T entity) {
        this.entity = entity;
    }

    public T getEntity() {
        return entity;
    }

    @Override
    public ResolvableType getResolvableType() {
        return ResolvableType.forClassWithGenerics(
                getClass(),
                ResolvableType.forInstance(entity)
        );
    }
}
~~~

ResolvableType allows Spring to inspect the generic type arguments rather than just the raw class. A listener can declare the corresponding generic type when the event supplies sufficient type information at runtime.

In typical applications, if there are only a few distinct event types, using concrete event classes is simpler and less error-prone. Use generic events only when there is a clear design reason and you have tested type matching with your actual event structure.

## 9. Runnable Example with Java 17+ and Spring Framework 6.2.0

This example demonstrates how Spring selects listeners by event type. OrderCreatedEvent and OrderCancelledEvent both implement OrderEvent. PaymentReceivedEvent is a separate type. A publisher emits three objects sequentially and the matching listeners are invoked.

### 9.1. Project Structure

~~~text
spring-listener-type/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        ├── EventDemo.java
                        ├── Events.java
                        ├── EventPublisherService.java
                        └── EventListeners.java
~~~

### 9.2. Maven Configuration

The pom.xml file:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-listener-type</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.3. Defining Events

File src/main/java/com/example/events/Events.java:

~~~java
package com.example.events;

public final class Events {

    private Events() {
    }

    public interface OrderEvent {
        String orderId();
    }

    public record OrderCreatedEvent(String orderId)
            implements OrderEvent {
    }

    public record OrderCancelledEvent(String orderId, String reason)
            implements OrderEvent {
    }

    public record PaymentReceivedEvent(String orderId, long amount) {
    }
}
~~~

OrderCreatedEvent and OrderCancelledEvent belong to the OrderEvent group. PaymentReceivedEvent does not implement that interface, so it is not handled by the listener accepting OrderEvent.

### 9.4. Creating Type-Specific Listeners

File src/main/java/com/example/events/EventListeners.java:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class EventListeners {

    @Order(1)
    @EventListener
    public void onAnyOrderEvent(Events.OrderEvent event) {
        System.out.println("OrderEvent listener: "
                + event.getClass().getSimpleName()
                + " " + event.orderId());
    }

    @Order(2)
    @EventListener
    public void onOrderCreated(Events.OrderCreatedEvent event) {
        System.out.println("OrderCreated listener: " + event.orderId());
    }

    @EventListener
    public void onPaymentReceived(Events.PaymentReceivedEvent event) {
        System.out.println("Payment listener: "
                + event.orderId() + " amount=" + event.amount());
    }
}
~~~

The listener onAnyOrderEvent receives every event implementing OrderEvent. The listener onOrderCreated receives only OrderCreatedEvent. Since both methods accept OrderCreatedEvent, @Order defines the invocation order between them. The listener onPaymentReceived receives only PaymentReceivedEvent.

### 9.5. Creating the Publisher

File src/main/java/com/example/events/EventPublisherService.java:

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class EventPublisherService {

    private final ApplicationEventPublisher eventPublisher;

    public EventPublisherService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void publishExamples() {
        eventPublisher.publishEvent(
                new Events.OrderCreatedEvent("ORD-1001"));

        eventPublisher.publishEvent(
                new Events.PaymentReceivedEvent("ORD-1001", 1200));

        eventPublisher.publishEvent(
                new Events.OrderCancelledEvent("ORD-1002", "Customer request"));
    }
}
~~~

The publisher only emits event objects. It does not need to check which listeners are registered or call each method directly.

### 9.6. Starting the Application

File src/main/java/com/example/events/EventDemo.java:

~~~java
package com.example.events;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan
public class EventDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(EventDemo.class)) {
            context.getBean(EventPublisherService.class).publishExamples();
        }
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.events.EventDemo
~~~

Stdout output:

~~~text
OrderEvent listener: OrderCreatedEvent ORD-1001
OrderCreated listener: ORD-1001
Payment listener: ORD-1001 amount=1200
OrderEvent listener: OrderCancelledEvent ORD-1002
~~~

Result explanation:

- OrderCreatedEvent implements OrderEvent so onAnyOrderEvent is called; it also matches onOrderCreated. @Order(1) causes the group listener to run before the specific listener with @Order(2).
- PaymentReceivedEvent does not implement OrderEvent so neither order listener is invoked. It invokes only onPaymentReceived.
- OrderCancelledEvent implements OrderEvent so only onAnyOrderEvent is invoked in this example.

The example uses POJO records, so Spring automatically wraps them in PayloadApplicationEvent upon publishing. @EventListener receives the payload record directly according to the declared parameter type.

## 10. Common Errors and How to Handle Them

| Symptom | Possible Cause | How to Check or Handle |
|---|---|---|
| Listener does not run | Bean is not registered in ApplicationContext | Check @Component, @Bean, and component scan scope |
| Listener does not receive event | Parameter type is incompatible with event | Check class, interface, and inheritance relationships |
| Listener receives more events than expected | Listener declares a broad superclass or common interface | Check supertype scope; split event types if clearer boundaries are needed |
| POJO listener does not run | Confusing PayloadApplicationEvent wrapper with payload type | Use @EventListener with the payload type or an appropriate wrapper listener |
| Two listeners run in unexpected order | Order not declared for listeners of the same event | Use @Order or Ordered when ordering is truly required |
| Generic listener cannot distinguish arguments | Type erasure drops generic information at runtime | Use concrete event types or ResolvableTypeProvider |
| Listener runs despite data not meeting criteria | Only type is checked, content is not filtered | Use condition or perform business checks inside the listener |

When debugging, log the runtime class of the event and verify whether the listener is registered. For payload events, check both the payload type and the wrapper. For generic events, inspect the actual ResolvableType rather than just looking at the generic declaration in source code.

## 11. Design Recommendations

Choose event types according to business meaning and subscriber needs:

- Use a specific event type when only one group of listeners needs to receive a single occurrence.
- Use an interface or superclass when multiple events share data and behavior that listeners genuinely need to process.
- Use @EventListener when you want concise method-based listener declarations.
- Use ApplicationListener when you want to implement a specialized interface-based listener for ApplicationEvent.
- Use condition for additional filtering by event data after the type already matches.
- Use ResolvableTypeProvider when a generic event needs to preserve type parameter information at runtime.

Keep event payloads immutable if possible. Avoid publishing a mutable object and then mutating it after publishing; listeners could observe data in an inconsistent state. If multiple subscribers need to process independently, the payload should hold sufficiently clear data without depending on mutable internal state of the publisher.

## 12. Verification Checklist

- [ ] Event name and type accurately reflect the business occurrence.
- [ ] Listener is a Spring-managed bean.
- [ ] @EventListener parameter type is compatible with the published event type.
- [ ] Interface/superclass relationships are used intentionally.
- [ ] POJO payloads and PayloadApplicationEvent are properly distinguished when needed.
- [ ] Generic events provide runtime type info if generic matching depends on it.
- [ ] SpEL conditions are used only for supplementary filtering, not to obscure the event model.
- [ ] Order among listeners for the same event is configured when business logic requires it.
- [ ] Tested which events invoke which listeners and verified any required ordering.

## 13. Key Takeaways

Spring selects listeners based on the event type declared by the listener. With @EventListener, the method's parameter type is the matched type; events implementing an interface or extending a superclass can be received by a listener declaring that general type. @Order sorts listeners that match the same event.

For POJOs or records, Spring uses PayloadApplicationEvent as a wrapper, though @EventListener can receive the payload directly. ApplicationListener<E> is intended for types E extending ApplicationEvent. When you need to filter by data, use condition; when generic types must be distinguished at runtime, provide ResolvableType information or prefer concrete event classes. Understanding these rules helps ensure listeners handle only the events they genuinely care about.