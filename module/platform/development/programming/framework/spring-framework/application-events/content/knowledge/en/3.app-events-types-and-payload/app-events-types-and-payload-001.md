# ApplicationEvent and Custom Subclasses

## 1. Application Events in Spring

Application Events is Spring's internal publish/subscribe mechanism. One component publishes an event to notify that something has occurred; other components register to listen and react to that event. The publisher does not need to call each listener directly, so parts of the application are less coupled to one another.

In Spring, ApplicationContext also implements ApplicationEventPublisher. When publishEvent(...) is called, the event is passed to the current context's ApplicationEventMulticaster mechanism, and then dispatched to matching listeners, such as beans with methods annotated with @EventListener or classes implementing ApplicationListener.

This is an event mechanism within the same application and the same process. It does not automatically create a durable queue, does not send events to another process, and does not replace a message broker such as RabbitMQ or Kafka.

## 2. What is ApplicationEvent?

ApplicationEvent is Spring's abstract base class, extending java.util.EventObject. This class provides two main pieces of information:

- source: the object that published the event. Can be retrieved via getSource(). The source value must be non-null.
- timestamp: the time when the event object was instantiated, retrieved via getTimestamp() and represented in milliseconds since the Unix epoch.

A custom event can extend ApplicationEvent to carry strongly typed business data. For example, OrderCreatedEvent represents that an order has been created and carries the order ID and total amount.

Event names usually describe something that has occurred, using the past tense such as OrderCreatedEvent, UserRegisteredEvent, or PaymentCompletedEvent. An event should be data describing the event; business processing belongs to the publisher or listener.

Note: ApplicationEvent's timestamp is the time when the event object was created. If business logic needs the exact domain occurrence time, pass a separate Instant occurredAt field instead of using timestamp as a substitute for business time.

## 3. Creating a Custom Event Class

A subclass typically has the following characteristics:

1. Extends ApplicationEvent.
2. Calls super(source) in the constructor to initialize the event source.
3. Declares fields holding the data needed by listeners.
4. Keeps data immutable after creating the event; use final and validate inputs.
5. Includes only the data listeners need in the event. Avoid holding references to the entire ApplicationContext, a service, or a large mutable object if unnecessary.

The example below creates an event containing an order ID and total amount:

~~~java
import org.springframework.context.ApplicationEvent;

import java.math.BigDecimal;
import java.util.Objects;

public final class OrderCreatedEvent extends ApplicationEvent {
    private final String orderId;
    private final BigDecimal total;

    public OrderCreatedEvent(Object source, String orderId, BigDecimal total) {
        super(Objects.requireNonNull(source, "source"));
        this.orderId = Objects.requireNonNull(orderId, "orderId");
        this.total = Objects.requireNonNull(total, "total");
    }

    public String getOrderId() {
        return orderId;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

In the example, source is the object that published the event, while orderId and total are the business payload. Using final ensures listeners receive a stable snapshot of the data at the time the event was created. For collections, create an immutable copy, such as List.copyOf(...), rather than holding a collection that can be modified externally.

Actions such as sending emails or updating a database should not be placed in the event's constructor. The constructor should only create the event data; listeners perform the corresponding reactions.

## 4. Publishing Events with ApplicationEventPublisher

The event-publishing component can receive ApplicationEventPublisher via constructor injection. When the business logic reaches the point where notification is needed, the publisher calls publishEvent(event):

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;

@Service
public class OrderService {
    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void createOrder(String orderId, BigDecimal total) {
        // Perform order validation and persistence here.
        eventPublisher.publishEvent(
            new OrderCreatedEvent(this, orderId, total)
        );
    }
}
~~~

Using this as the source is a common convention when a service publishes an event. If listeners do not need to know the specific publisher, a meaningful source that fits the design can still be used. Do not pass null.

Events should be published after the business operation has reached the state described by the event name. For example, only publish OrderCreatedEvent after the order has been created successfully. If published too early, a listener may act on data that does not yet exist or when the subsequent operation fails.

ApplicationEventPublisher is an abstraction; the service does not need to depend on a specific ApplicationContext implementation. This also makes it easier to test the service with a fake or mock publisher.

## 5. Listening for Events

A common approach is to declare a Spring bean with a method annotated with @EventListener. The parameter type indicates the type of event the method receives:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {
    @EventListener
    public void handle(OrderCreatedEvent event) {
        System.out.println(
            "Order " + event.getOrderId()
                + " created; total=" + event.getTotal()
        );
    }
}
~~~

The bean containing the listener must be registered in the ApplicationContext, for example via component scanning, @Bean, or registerBean. A plain Java method does not automatically become a listener if its object is not managed by Spring and processed for annotations.

Spring selects listeners based on event type. A listener accepting a superclass can also receive events of corresponding subclasses. For example, a listener accepting ApplicationEvent has a very broad scope and can receive many framework events as well as business events. Use specific event types to avoid handling events unintentionally.

In addition to @EventListener, you can implement ApplicationListener<OrderCreatedEvent> and define onApplicationEvent(...). This approach makes the type relationship explicit at the class level; @EventListener is usually more concise when a bean needs to listen to multiple event types.

If multiple listeners require a deterministic invocation order, @Order can be used. However, avoid making business outcomes depend on listener order; when steps have dependencies on each other, orchestrate them explicitly in a service.

## 6. Complete Runnable Example

The following example uses Java 17 and Spring Framework 6.2.0. The program creates an ApplicationContext, registers the listener, refreshes the context, and then publishes an OrderCreatedEvent.

Create the file src/main/java/demo/ApplicationEventDemo.java:

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;

import java.math.BigDecimal;
import java.util.Objects;

public class ApplicationEventDemo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(OrderCreatedListener.class);
            context.refresh();

            context.publishEvent(new OrderCreatedEvent(
                "order-service",
                "ORD-1001",
                new BigDecimal("125.50")
            ));
        }
    }

    public static final class OrderCreatedEvent extends ApplicationEvent {
        private final String orderId;
        private final BigDecimal total;

        public OrderCreatedEvent(
                Object source, String orderId, BigDecimal total) {
            super(Objects.requireNonNull(source, "source"));
            this.orderId = Objects.requireNonNull(orderId, "orderId");
            this.total = Objects.requireNonNull(total, "total");
        }

        public String getOrderId() {
            return orderId;
        }

        public BigDecimal getTotal() {
            return total;
        }
    }

    public static class OrderCreatedListener {
        @EventListener
        public void handle(OrderCreatedEvent event) {
            System.out.println(
                "Order " + event.getOrderId()
                    + " created; total=" + event.getTotal()
            );
        }
    }
}
~~~

Create the file pom.xml in the project root directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>application-event-demo</artifactId>
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
                    <mainClass>demo.ApplicationEventDemo</mainClass>
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

Stdout output:

~~~text
Order ORD-1001 created; total=125.50
~~~

Execution flow:

1. AnnotationConfigApplicationContext is created.
2. OrderCreatedListener is registered as a bean.
3. refresh() completes the context initialization process and registers @EventListener handlers.
4. publishEvent(...) publishes OrderCreatedEvent.
5. The listener with the OrderCreatedEvent parameter is invoked and prints the order ID and total amount.
6. try-with-resources closes the context when the program ends.

## 7. ApplicationEvent and Payload Objects

Since Spring Framework 4.2, publishEvent(...) can accept any arbitrary object; it is no longer required for every event to extend ApplicationEvent. For a plain object, Spring wraps it in a PayloadApplicationEvent to pass it into the event dispatch mechanism.

For example, if you only need to pass simple data, you can define a record:

~~~java
import java.math.BigDecimal;

public record OrderCreatedPayload(String orderId, BigDecimal total) {
}
~~~

The publisher can call publishEvent(new OrderCreatedPayload(...)); the listener can directly accept OrderCreatedPayload as a parameter of the @EventListener method.

Choose the approach that fits your needs:

- Extend ApplicationEvent when you need an explicit event type, need to use source or timestamp provided by the base class, or want to build your own event hierarchy.
- Use a payload object or record when the event is primarily data and does not need to extend ApplicationEvent. This reduces constructor/getter boilerplate and fits immutable DTOs well.

You do not need to extend ApplicationEvent just so Spring recognizes an object as an event. What matters is that the publisher and listener agree on the data type and meaning of the event.

## 8. Synchronous, Asynchronous, and Transactions

By default, listeners are invoked synchronously on the event-publishing thread. Therefore, publishEvent(...) usually only completes after all synchronous listeners have finished processing. A slow listener can slow down the publisher's call; an exception from a listener can also affect the publish call if separate error handling is not configured.

You can run a listener asynchronously using @Async and enabling @EnableAsync in the Spring configuration. In that case, you need to configure an executor, monitor errors on background threads, and avoid assuming that the listener has finished immediately after publishEvent(...). Asynchronous processing also changes the thread context and how thread-bound data is propagated.

When a listener needs to read committed data from the database, consider @TransactionalEventListener. By default, this listener runs in the AFTER_COMMIT phase, meaning after the transaction commits successfully. It also supports phases such as BEFORE_COMMIT, AFTER_ROLLBACK, and AFTER_COMPLETION. If there is no active transaction, the listener is not invoked by default; only enable fallbackExecution when that behavior is genuinely appropriate.

Application Events is not a durable event storage mechanism. If the application stops before a listener processes an event, Spring does not automatically persist the event to replay after startup. For retry requirements, delivery guarantees, or inter-process communication, use an appropriate messaging solution; a transactional outbox can be combined when database writes and message publishing need to be synchronized.

## 9. Common Pitfalls and How to Avoid Them

- Forgetting to call super(source): the base class constructor requires a valid source. Pass a meaningful, non-null object.
- Putting too little data into the event: listeners having to call back into the publisher for information can increase coupling. Include the necessary data in the event, while avoiding carrying a large object graph.
- Using a mutable payload: one listener could modify data received by another listener. Prefer final fields, records, and immutable copies of collections.
- Naming events after future actions: a name like SendEmailEvent describes a command rather than an event that has occurred. Use names that express a fact that already happened, such as UserRegisteredEvent.
- Assuming events are always asynchronous: the default is synchronous. Background execution requires explicit async configuration.
- Publishing an event before a transaction commits: a listener may run while data is not yet committed. Use @TransactionalEventListener with the appropriate phase when synchronization with a transaction is needed.
- Using a listener accepting ApplicationEvent for everything: too broad a type can catch system events as well. Choose specific event classes.
- Treating internal events like a message broker: events do not inherently provide persistence, retries, consumer groups, or network delivery guarantees.

## 10. Implementation Workflow

1. Identify the business event that has occurred and the exact moment it should be published.
2. Create an immutable event class; extend ApplicationEvent if you need source, timestamp, or a type hierarchy.
3. Inject ApplicationEventPublisher into the event-publishing component.
4. Register the listener as a Spring bean and accept the exact event type.
5. Decide whether the listener runs synchronously, asynchronously, or bound to a transaction.
6. Test both that the event is published, that the listener receives the expected data, and that listener errors are handled as designed.

A good event clearly describes a fact that has happened, contains just enough data, and performs no actions itself. When publishers and listeners follow that convention, ApplicationEvent helps decouple components in a Spring application while keeping the execution flow easy to understand.