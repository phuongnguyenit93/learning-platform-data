# A Single Method Receiving Multiple Event Types

## 1. When Does One Listener Need Multiple Events?

In a Spring application, multiple types of events may need to trigger the same reaction. For example, when an order is created or cancelled, the system needs to write an audit entry in both cases; when inventory runs low or payment fails, the system needs to raise an operational alert in both cases.

You can write a separate listener for each event type, but if the handling logic is identical, code gets duplicated. Spring allows a single @EventListener method to receive multiple event types. There are two common design approaches:

- Use a common supertype as the method's parameter type. The listener receives events of its subtypes and can read data from the event.
- Declare multiple event classes directly in the classes attribute of @EventListener. With multiple event classes, the method must take no parameters; this approach fits when every event only needs to trigger the same shared action.

You should choose an approach based on whether the handler needs to read the payload and whether the events share a type relationship.

## 2. Approach 1: Accepting a Common Event Supertype

If the events share an inheritance relationship, create a base class containing the shared data. The listener method accepts that base class; Spring invokes the method for concrete events whose types inherit from the base class.

For example, OrderCreatedEvent and OrderCancelledEvent are both kinds of OrderEvent. Both carry orderId, so a listener can handle them through a single OrderEvent parameter:

~~~java
import org.springframework.context.ApplicationEvent;

import java.util.Objects;

public abstract class OrderEvent extends ApplicationEvent {
    private final String orderId;

    protected OrderEvent(Object source, String orderId) {
        super(Objects.requireNonNull(source, "source"));
        this.orderId = Objects.requireNonNull(orderId, "orderId");
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

Two concrete events extend the base class:

~~~java
public final class OrderCreatedEvent extends OrderEvent {
    public OrderCreatedEvent(Object source, String orderId) {
        super(source, orderId);
    }
}

public final class OrderCancelledEvent extends OrderEvent {
    public OrderCancelledEvent(Object source, String orderId) {
        super(source, orderId);
    }
}
~~~

The listener needs only one method:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {
    @EventListener
    public void handle(OrderEvent event) {
        System.out.println(
            event.getClass().getSimpleName()
                + " for order " + event.getOrderId()
        );
    }
}
~~~

When Spring receives OrderCreatedEvent or OrderCancelledEvent, the runtime type of the event is compatible with the OrderEvent parameter, so the same handle(...) method is invoked. The method can read shared data via getOrderId() and check the concrete type only when genuinely different behavior is required.

You can use a common interface if the event design fits an interface. However, if the events need to share state or a common constructor, an abstract base class is often easier to express. For events extending ApplicationEvent, the base class can also centralize source handling and shared data.

This approach is suitable when:

- The events share domain-level meaning or a common data contract.
- The listener needs to read the event payload.
- The relationship between events can be modeled by a superclass or interface.
- You want the compiler to check data types and avoid manual casting.

Do not create an overly broad superclass just to group unrelated events. The supertype should reflect a genuinely meaningful domain concept.

## 3. Approach 2: Declaring Multiple Types via classes

If the events do not share an appropriate supertype yet still need to trigger the same action, you can list the event classes in the classes attribute:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OperationsNotifier {
    @EventListener(classes = {
        InventoryLowEvent.class,
        PaymentFailedEvent.class
    })
    public void notifyOperations() {
        System.out.println("An operational event was received");
    }
}
~~~

In the example, InventoryLowEvent and PaymentFailedEvent can be two completely independent data types. When either type is published, Spring invokes notifyOperations().

The value attribute is an alias for classes, so you can write it concisely:

~~~java
@EventListener({
    InventoryLowEvent.class,
    PaymentFailedEvent.class
})
public void notifyOperations() {
    // Shared reaction for both event types.
}
~~~

Both styles have the same meaning. Using classes makes it clear to readers that this is the list of event types handled by the method.

**Method signature rule in Spring Framework 6.2:** if classes contains only one type, the method may accept one corresponding parameter; if classes contains multiple types, the method must declare no parameters. Spring relies on the type list on the annotation to determine which events trigger the method, so you cannot use a single parameter whose type is incompatible with all those independent events.

Because the method does not receive the event as a parameter, it is suitable when you only need to perform a uniform action, such as evicting a cache, incrementing a metric, or signaling a process to wake up. If you need to read event-specific data, use a common supertype as in Approach 1 or split into separate listener methods.

## 4. Comparing the Two Approaches

| Criterion | Common Supertype | The classes Attribute |
|---|---|---|
| Relationship between events | Share a superclass or interface | Can be completely independent |
| Listener parameter | Accepts the common supertype | Multiple types: no parameters |
| Payload access | Can read data through the supertype | Does not receive payload via parameter |
| Suitable behavior | Handling based on data or distinguishing subtypes | One identical action for every event |
| Type checking | Checked by the Java type system | Each type declared via class literals |

Neither approach is always better. Use a common supertype when events share a data contract. Use classes when events are independent yet trigger the same reaction without needing the payload.

If a method needs to accept multiple independent events and still needs data from each event, do not try to force unrelated types into a single parameter. Create a meaningful shared abstraction or use multiple listener methods with explicit parameters.

## 5. Complete Runnable Example

The example below uses Java 17 and Spring Framework 6.2.0. The program demonstrates both approaches:

- OrderAuditListener accepts OrderEvent, which is the superclass of OrderCreatedEvent and OrderCancelledEvent.
- OperationsNotifier declares two independent payload events via classes and takes no parameters.

Create the file src/main/java/demo/MultiEventListenerDemo.java:

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

import java.util.Objects;

public class MultiEventListenerDemo {
    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.publishEvent(
                new OrderCreatedEvent("order-service", "ORD-1001")
            );
            context.publishEvent(
                new OrderCancelledEvent("order-service", "ORD-1002")
            );

            context.publishEvent(new InventoryLowEvent("SKU-7"));
            context.publishEvent(new PaymentFailedEvent("PAY-9"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        OrderAuditListener orderAuditListener() {
            return new OrderAuditListener();
        }

        @Bean
        OperationsNotifier operationsNotifier() {
            return new OperationsNotifier();
        }
    }

    public abstract static class OrderEvent extends ApplicationEvent {
        private final String orderId;

        protected OrderEvent(Object source, String orderId) {
            super(Objects.requireNonNull(source, "source"));
            this.orderId = Objects.requireNonNull(orderId, "orderId");
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static final class OrderCreatedEvent extends OrderEvent {
        public OrderCreatedEvent(Object source, String orderId) {
            super(source, orderId);
        }
    }

    public static final class OrderCancelledEvent extends OrderEvent {
        public OrderCancelledEvent(Object source, String orderId) {
            super(source, orderId);
        }
    }

    public record InventoryLowEvent(String sku) {
    }

    public record PaymentFailedEvent(String paymentId) {
    }

    static class OrderAuditListener {
        @EventListener
        public void handle(OrderEvent event) {
            System.out.println(
                event.getClass().getSimpleName()
                    + " for order " + event.getOrderId()
            );
        }
    }

    static class OperationsNotifier {
        @EventListener(classes = {
            InventoryLowEvent.class,
            PaymentFailedEvent.class
        })
        public void notifyOperations() {
            System.out.println("An operational event was received");
        }
    }
}
~~~

Create pom.xml in the root directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multi-event-listener-demo</artifactId>
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
                    <mainClass>demo.MultiEventListenerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Run in the directory containing pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Expected stdout:

~~~text
OrderCreatedEvent for order ORD-1001
OrderCancelledEvent for order ORD-1002
An operational event was received
An operational event was received
~~~

Result explanation:

1. ApplicationContext registers the two listener beans in AppConfig.
2. OrderCreatedEvent is published. This type extends OrderEvent, so OrderAuditListener.handle(OrderEvent) is invoked.
3. OrderCancelledEvent also extends OrderEvent, so the same handle(...) method is invoked a second time.
4. InventoryLowEvent is published. This type is in the classes list, so OperationsNotifier.notifyOperations() is invoked.
5. PaymentFailedEvent is also in the classes list, so the same notifyOperations() method is invoked once more.
6. Listeners run synchronously by default, so the stdout order corresponds to the publishEvent order in main.

## 6. Combining SpEL Conditions

You can add the condition attribute to filter events using a Spring Expression Language expression. For a listener with one parameter, you can use properties of the event in the condition:

~~~java
@EventListener(condition = "#root.args[0].orderId.startsWith('ORD-')")
public void handle(OrderEvent event) {
    System.out.println("Accepted order " + event.getOrderId());
}
~~~

The condition is evaluated when the event matches the listener's type. If the expression returns false, the method is not called. In addition to parameter variables, SpEL provides #root.event to access the actual event and #root.args to access the method's arguments.

For a listener declaring multiple classes in classes, the method takes no parameters per the rule above. You can use #root.event in condition to filter on event information, though if the method body needs to handle different payloads, a common supertype or separate listeners are usually easier to read.

Do not use condition to replace a clear data type model. If multiple events have substantially different processing rules, splitting handlers makes the code easier to maintain and test.

## 7. Ordering, Asynchronous Execution, and Errors

If multiple listeners receive the same event, you can use @Order to specify priority when they are invoked synchronously:

~~~java
@EventListener
@Order(1)
public void updateCache(OrderEvent event) {
    // Update cache first.
}

@EventListener
@Order(2)
public void writeAudit(OrderEvent event) {
    // Write audit afterward.
}
~~~

Rely on this ordering only when it is genuinely a design requirement. If a later step depends on the result of an earlier step, an explicit coordinating service is usually easier to understand.

You can use @Async to run listeners on a different executor once @EnableAsync is enabled. When a listener runs asynchronously, the publisher does not wait for completion; listener exceptions do not propagate back to the publishEvent call. Async listeners also should not rely on @Order to guarantee completion order.

By default, synchronous listeners are invoked on the thread that publishes the event. Exceptions from a listener can affect the publishEvent call if no ErrorHandler handles them. Therefore, if a single method accepts multiple events and performs the same action, ensure that action is safe for every event and errors are handled according to your desired policy.

Application Events are an internal mechanism of an ApplicationContext. Having one method accept multiple events does not turn this mechanism into a message broker: Spring does not automatically provide persistence, retries, or durable delivery across multiple processes.

## 8. Common Pitfalls

- Declaring multiple classes in classes while keeping a parameter: invalid in Spring Framework 6.2. Remove the parameter or switch to a common supertype.
- Using classes with unrelated types and trying to cast inside the method: the method has no parameters per the multi-class rule, so use separate listeners if payloads are needed.
- Choosing an overly broad supertype such as ApplicationEvent: the listener may receive many framework events outside the intended business events. Create a specific domain supertype to limit scope.
- Forgetting that payload objects are also events: since Spring 4.2, any object can be published; Spring wraps payloads in PayloadApplicationEvent.
- Listener is not invoked: check whether the bean belongs to the right ApplicationContext and whether the event type matches the method or classes list.
- Grouping events just because they share naming or the same package: group them only when they truly share behavior or a data contract.
- Assuming multiple listeners run asynchronously: event listeners run synchronously by default. Configure async explicitly when required.

## 9. Selection Process

1. List the event types that need to trigger the same reaction.
2. Check whether they share a domain-meaningful superclass or interface.
3. If they do and you need to read the payload, use a single parameter of the common supertype.
4. If the types are independent and the handler does not need the payload, declare them in @EventListener(classes = {...}) and use a zero-argument method.
5. If different data needs to be processed, use an appropriate common supertype or split into multiple listener methods.
6. Test each event type to ensure all trigger the right behavior and no out-of-scope events match.

A listener method should combine multiple events when they genuinely share the same reaction. Choosing the right common supertype or classes list helps Spring dispatch events clearly while keeping the method signature aligned with the data the handler needs.