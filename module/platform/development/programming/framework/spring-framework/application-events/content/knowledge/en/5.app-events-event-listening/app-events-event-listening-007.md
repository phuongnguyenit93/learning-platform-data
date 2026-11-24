# Multiple Listener Methods in a Spring Bean

## Objectives

After this lesson, you will be able to:

- Register multiple @EventListener methods inside the same bean.
- Allow a single bean to handle multiple event types and multiple methods to listen to the same event type.
- Control ordering with @Order and filter events with condition.
- Use a listener's return value to publish a subsequent event.
- Understand how listener methods interact with asynchronous processing.
- Organize listeners in beans with clear, testable responsibilities.

## 1. A Bean Can Have Multiple Listener Methods

In Spring, @EventListener is placed on methods. Spring detects annotated methods in beans managed by ApplicationContext and registers each method as an individual event listener.

Therefore, a single bean can contain multiple listener methods:

- Each method can accept a different event type.
- Multiple methods can accept the same event type.
- Each method can have its own condition and processing order.
- A method can return a new event for Spring to publish next.

For example, OrderEventListeners can contain auditCreation(OrderCreatedEvent), notifyCreation(OrderCreatedEvent), and handlePayment(PaymentCompletedEvent). When OrderCreatedEvent is published, the first two methods can both run. When PaymentCompletedEvent is published, the handlePayment method is invoked.

These methods do not need to call each other directly. The publisher only emits events, and Spring selects listeners whose event types match.

## 2. How Does Spring Discover Listener Methods?

When ApplicationContext starts up, Spring scans for beans with methods annotated with @EventListener and registers those methods. When an event is published, Spring selects listeners whose parameter types match the event type.

Example:

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Order created: " + event.orderId());
    }

    @EventListener
    public void onPaymentCompleted(PaymentCompletedEvent event) {
        System.out.println("Payment completed: " + event.orderId());
    }
}
~~~

In the example above:

- onOrderCreated handles only OrderCreatedEvent.
- onPaymentCompleted handles only PaymentCompletedEvent.
- Both methods reside in the same bean yet are registered as two separate listeners.
- The publisher does not need to know the bean name or method names.

A typical listener method declares one event parameter. Spring infers the event type from that parameter type. Subtype events can also match a listener accepting a corresponding supertype.

The bean containing listeners must be Spring-managed, such as annotated with @Component or declared with @Bean. If you instantiate the object manually using the new keyword, Spring does not automatically detect @EventListener methods on that object.

## 3. Multiple Methods Receiving the Same Event Type

This is useful when a single event needs to trigger multiple independent actions within the same responsibility group.

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    public void auditCreation(OrderCreatedEvent event) {
        System.out.println("Audit order " + event.orderId());
    }

    @EventListener
    public void notifyCustomer(OrderCreatedEvent event) {
        System.out.println("Notify customer for " + event.orderId());
    }

    @EventListener
    public void updateMetrics(OrderCreatedEvent event) {
        System.out.println("Update metrics for " + event.orderId());
    }
}
~~~

When the publisher emits an OrderCreatedEvent, all three methods are matching listeners and are invoked by Spring. There is no need to create three distinct events just because there are three actions.

Do not rely on the declaration order of methods in the Java file to determine execution order. If order carries business meaning, declare @Order.

## 4. Controlling Order with @Order

You can place @Order on each listener method. Smaller values have higher priority and are invoked earlier among the listeners handling that event.

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    @Order(1)
    public void auditCreation(OrderCreatedEvent event) {
        System.out.println("1. Audit " + event.orderId());
    }

    @EventListener
    @Order(2)
    public void notifyCustomer(OrderCreatedEvent event) {
        System.out.println("2. Notify " + event.orderId());
    }

    @EventListener
    @Order(3)
    public void updateMetrics(OrderCreatedEvent event) {
        System.out.println("3. Metrics " + event.orderId());
    }
}
~~~

When receiving an OrderCreatedEvent, the expected order is:

~~~text
1. Audit ORD-1001
2. Notify ORD-1001
3. Metrics ORD-1001
~~~

If @Order is omitted, the listener uses the default lowest precedence. If multiple listeners share the same precedence, do not rely on their relative order for business logic.

@Order controls the synchronous listener invocation order during dispatch. It does not guarantee the completion order of listeners running asynchronously.

## 5. One Method Can Receive Multiple Event Types

If multiple event types only need to trigger the same operation without reading the payload, you can use the classes attribute of @EventListener:

~~~java
@Component
public class BusinessActivityListener {

    @EventListener(classes = {
            OrderCreatedEvent.class,
            PaymentCompletedEvent.class
    })
    public void recordBusinessActivity() {
        System.out.println("A business event was received");
    }
}
~~~

When using the classes attribute, the method declares no parameters. Spring invokes the method when one of the listed event types is published.

If you need to read event-specific data, create separate methods with corresponding parameters. That clarifies the data types and avoids manual branching or casting.

## 6. Filtering Listeners with condition

You can add a SpEL condition so that a method runs only when the event satisfies an expression.

For example, handle only high-priority notifications:

~~~java
@Component
public class OrderEventListeners {

    @EventListener(
            condition = "#root.args[0].priority() == 'HIGH'"
    )
    public void handleHighPriority(OrderCreatedEvent event) {
        System.out.println(
                "High priority order: " + event.orderId()
        );
    }
}
~~~

For a method with an event parameter, #root.args is the array of arguments passed to the listener. #root.args[0] is the first event argument. In the example, priority() returns the order's priority level.

The condition is evaluated before calling the method. If the expression returns false, that listener method is skipped; other matching listeners for the same event are still processed.

Use condition for simple filtering cases. If conditional logic is complex, requires data queries, or has multiple business branches, move the decision into a separate service for easier testing.

## 7. Return Values Can Publish Subsequent Events

An @EventListener method can return a non-null object. Spring publishes that returned value as a new event within the same ApplicationContext.

Example:

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    public InventoryCheckRequestedEvent requestInventory(
            OrderCreatedEvent event
    ) {
        System.out.println(
                "Request inventory for " + event.orderId()
        );

        return new InventoryCheckRequestedEvent(event.orderId());
    }

    @EventListener
    public void checkInventory(InventoryCheckRequestedEvent event) {
        System.out.println(
                "Check inventory for " + event.orderId()
        );
    }
}
~~~

Execution flow:

1. The publisher emits OrderCreatedEvent.
2. requestInventory receives the event and creates InventoryCheckRequestedEvent.
3. Spring publishes the returned event.
4. checkInventory receives InventoryCheckRequestedEvent.

This is useful when one listener passes the flow to the next step without needing to inject ApplicationEventPublisher directly.

If the method returns a Collection, each element in the collection is published as a separate event. If you do not want to emit a subsequent event, declare the method return type as void.

Avoid creating circular event chains. For example, listener A emitting event B while listener B emits event A without a stopping condition. Such a loop can cause continuous processing or a stack overflow during synchronous dispatch.

## 8. Complete Example with Java 17 and Spring Boot

This example uses a single OrderEventListeners bean with multiple methods receiving two event types. The methods handling OrderCreatedEvent have an explicit order; another method runs only when the order has HIGH priority.

### Directory Structure

~~~text
spring-multiple-listeners-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        ├── MultipleListenersApplication.java
                        ├── OrderCreatedEvent.java
                        ├── PaymentCompletedEvent.java
                        ├── OrderService.java
                        └── OrderEventListeners.java
~~~

### 8.1. Dependencies

File pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-multiple-listeners-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
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

### 8.2. Defining Events

File OrderCreatedEvent.java:

~~~java
package com.example.events;

public record OrderCreatedEvent(
        String orderId,
        String customerId,
        String priority
) {
}
~~~

File PaymentCompletedEvent.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

public record PaymentCompletedEvent(
        String orderId,
        BigDecimal amount
) {
}
~~~

These are records containing only immutable data types, suitable for passing event information between beans.

### 8.3. Event Publisher

File OrderService.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void createOrder(String orderId, String customerId) {
        publisher.publishEvent(
                new OrderCreatedEvent(orderId, customerId, "HIGH")
        );
    }

    public void completePayment(String orderId, BigDecimal amount) {
        publisher.publishEvent(
                new PaymentCompletedEvent(orderId, amount)
        );
    }
}
~~~

OrderService only publishes events. It does not know which beans exist or how many listener methods they have.

### 8.4. One Bean Containing Multiple Listener Methods

File OrderEventListeners.java:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListeners {

    @EventListener
    @Order(1)
    public void auditCreation(OrderCreatedEvent event) {
        System.out.println(
                "Audit: created order " + event.orderId()
        );
    }

    @EventListener
    @Order(2)
    public void notifyCustomer(OrderCreatedEvent event) {
        System.out.println(
                "Notify: created order " + event.orderId()
        );
    }

    @EventListener(
            condition = "#root.args[0].priority() == 'HIGH'"
    )
    @Order(3)
    public void handleHighPriority(OrderCreatedEvent event) {
        System.out.println(
                "Priority queue: HIGH order " + event.orderId()
        );
    }

    @EventListener
    @Order(1)
    public void auditPayment(PaymentCompletedEvent event) {
        System.out.println(
                "Audit: payment completed " + event.orderId()
        );
    }

    @EventListener
    @Order(2)
    public void notifyPayment(PaymentCompletedEvent event) {
        System.out.println(
                "Notify: payment received for " + event.orderId()
        );
    }
}
~~~

There are five listener methods inside the same bean:

- Three methods accept OrderCreatedEvent.
- Two methods accept PaymentCompletedEvent.
- Each method handles only its declared event type.
- @Order determines the invocation order within the corresponding listener group.
- handleHighPriority runs only when priority is HIGH.

### 8.5. Running the Application

File MultipleListenersApplication.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultipleListenersApplication implements CommandLineRunner {

    private final OrderService orderService;

    public MultipleListenersApplication(OrderService orderService) {
        this.orderService = orderService;
    }

    public static void main(String[] args) {
        SpringApplication.run(MultipleListenersApplication.class, args);
    }

    @Override
    public void run(String... args) {
        orderService.createOrder("ORD-1001", "CUS-01");

        orderService.completePayment(
                "ORD-1001",
                new BigDecimal("125000.00")
        );
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Excluding Spring Boot startup logs, the output printed by the application is:

~~~text
Audit: created order ORD-1001
Notify: created order ORD-1001
Priority queue: HIGH order ORD-1001
Audit: payment completed ORD-1001
Notify: payment received for ORD-1001
~~~

The first three lines are printed when OrderCreatedEvent is published. The last two lines are printed when PaymentCompletedEvent is published. The publisher calls publishEvent only twice; Spring automatically dispatches to all matching listener methods.

## 9. Combining Multiple Listener Methods with @Async

You can annotate one or more listener methods with @Async to run them on an executor. Async must be enabled via @EnableAsync:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Example adding a listener method to the bean:

~~~java
@Async
@EventListener
public void sendCustomerEmail(OrderCreatedEvent event) {
    System.out.println(
            "Sending email for " + event.orderId()
    );
}
~~~

This method runs asynchronously if async configuration is active and the bean is managed by Spring. The publisher does not wait for the method to complete.

Points to remember:

- @Order does not guarantee completion order for asynchronous listeners.
- Multiple async methods in the same bean can execute concurrently.
- Do not use shared mutable fields across async methods without proper synchronization.
- Exceptions from async listeners do not propagate back to the publisher like synchronous listeners; configure and monitor the executor's error handling.
- The return value of an async listener is not used to emit a subsequent event. If you need to publish a follow-up event, inject ApplicationEventPublisher and call publishEvent explicitly inside the listener.

A bean containing multiple listener methods does not imply those methods always run sequentially. Clearly distinguish which methods are synchronous, which are asynchronous, and what data is shared.

## 10. Common Pitfalls

| Symptom | Cause | How to Handle |
|---|---|---|
| Only one of the methods is called | Some methods are missing @EventListener or parameter types do not match the event. | Annotate each method and verify event types. |
| Listeners run in unexpected order | Relying on source-code declaration order or omitting @Order. | Explicitly set @Order on listeners with ordering dependencies. |
| Method does not receive the second event | Method is declared for a different event type. | Check the parameter type or the classes attribute. |
| Error when using classes and an event parameter | Method declares a parameter while using the classes attribute. | When using classes, declare the method without parameters. |
| Listener runs unexpectedly | Missing condition or faulty SpEL expression. | Check the expression and event data; test both true and false cases. |
| Events are published in an infinite loop | Listeners emit events forming a cycle with no termination condition. | Design event flows with termination points and check re-publish conditions. |
| Shared data suffers race conditions | Multiple async listeners access the same mutable state. | Use immutable payloads and manage shared state with proper concurrency controls. |
| Listener does not run | Bean is not registered in ApplicationContext. | Ensure the class has @Component or is declared with @Bean within scan scope. |

## 11. Organizing Listener Beans Cleanly

Place multiple listener methods in the same bean when they belong to the same responsibility group and can be understood as a unified event handler. For example, OrderEventListeners can group audit, notification, and order-status tracking operations.

When the number of methods grows or actions belong to different modules, split them into separate beans:

- OrderAuditListeners: history recording.
- OrderNotificationListeners: sending notifications.
- OrderMetricsListeners: updating metrics.

Splitting beans lets each group have its own dependencies, async configuration, error policies, and tests. Whether grouped or separated, listeners can still receive the same event published in ApplicationContext.

Do not create a listener method merely to forward a call to another method in the same bean unless there is an event-coordination reason. Keep events reflective of meaningful business occurrences.

## 12. Self-Check

1. How does Spring register @EventListener methods within the same bean?
2. When an event has three matching listener methods in the same bean, how many methods are invoked?
3. Why should you not rely on method declaration order in a Java file?
4. When using @EventListener(classes = ...), may the method declare parameters?
5. How do @Order and condition solve two different problems?
6. When a listener returns an event object, how does Spring handle that value?
7. Why does @Order not guarantee completion order when listeners run with @Async?
8. When should multiple listener methods be split into separate beans?

**Key takeaway:** A Spring bean can contain multiple @EventListener methods, and each method is registered independently. One event can trigger multiple matching methods; use @Order to order them, condition to filter, and return values to emit follow-up events. When using async, manage concurrency carefully and do not depend on completion order.