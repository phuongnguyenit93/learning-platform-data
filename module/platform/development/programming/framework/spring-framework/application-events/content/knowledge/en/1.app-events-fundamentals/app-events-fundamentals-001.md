# What Are Application Events and What Problem Do They Solve?

## Objectives

After this lesson, you will be able to explain what Application Events in Spring are, describe how an event travels from the publisher to listeners, recognize the tight coupling problem that this mechanism helps reduce, and choose the right cases to use events instead of direct method calls.

## 1. What Are Application Events?

An **Application Event** is a notification indicating that something has happened inside an application. The event-publishing component describes that occurrence and dispatches the event through Spring's mechanism. Interested components register listeners to receive and handle the event.

For example, after an order is successfully created, the application can publish an **OrderPlaced** event. Other components can listen to this event to send a confirmation email, record an audit log, or update a statistics dashboard.

Spring provides this mechanism at the **ApplicationContext** level. You can think of the ApplicationContext as an application-scoped event dispatcher: a publisher publishes an event, and Spring finds matching listeners and invokes them.

An event typically represents **a fact that has already happened**, such as OrderPlaced, PaymentReceived, or UserRegistered. It should not mean a request asking another component to execute a command. Event names therefore usually use the past tense or describe a state that has been established.

### Key Roles

- **Publisher**: the component that publishes the event. It knows that the occurrence happened and publishes the necessary data, without needing to know how many listeners exist or where they are located.
- **Event**: the object carrying information about the occurrence. For example, OrderPlaced may contain the order ID and total amount.
- **Listener**: a component that subscribes to receive an event type and performs the corresponding reaction.
- **ApplicationContext**: the Spring environment that manages distributing events to registered listeners.

The publisher and listeners can be different beans within the same application. The publisher does not need to call each listener directly.

## 2. What Problem Do Application Events Solve?

Consider an order creation service. After saving an order, the system needs to send an email, write an audit log, and update reporting metrics.

If it calls each component directly, the order creation service must know the email, audit, and reporting classes. When adding a new task, such as notifying the warehouse department, you have to modify the order creation service again and may have to add a new dependency. The business component gradually learns too many details that do not belong to its core responsibility.

Application Events help reduce that coupling:

1. The order creation service completes its core business logic and publishes OrderPlaced.
2. Spring dispatches the event to all matching listeners.
3. The email listener handles the notification; the audit listener records the history; the reporting listener updates its data.
4. When a new reaction needs to be added, you can add a listener without having to add a direct call inside the publisher.

As a result, the event mechanism supports:

- **Reducing coupling between components**: the publisher only depends on the event-publishing contract, not on concrete handler classes.
- **Separating responsibilities**: the business service focuses on creating orders; each listener handles its own reaction.
- **Easier extensibility**: listeners can be added or removed without rewriting the event-publishing flow.
- **Allowing multiple parties to react together**: a single event can be handled independently by multiple listeners according to their responsibilities.

This is decoupling at the source-code and internal structure level within the application. Application Events themselves do not turn beans into independent services, nor do they automatically create a distributed message broker system.

## 3. How Are Events Published and Handled?

The basic flow proceeds in the following order:

1. A bean executes business logic, such as creating an order.
2. When there is an event to announce, the bean calls publishEvent and passes the event object.
3. The ApplicationContext forwards the event to Spring's dispatch mechanism.
4. Spring identifies listeners with a compatible event type.
5. The listeners are invoked to perform their work.

In the default configuration, Spring uses a synchronous dispatcher. Listeners run directly on the thread calling publishEvent. Therefore, the publish-event call usually finishes only after the synchronous listeners finish processing.

This has an important consequence: Application Events help decouple dependencies between beans, but **do not by default decouple execution time**. A slow listener can still slow down the business flow publishing the event. Errors from a synchronous listener can also affect the publishing flow, depending on how error handling is configured.

If you need to run a listener asynchronously, you can combine @Async with @EnableAsync. In that case, the listener runs on an executor, and you must pay attention to thread management, processing order, errors, and shared data. Do not assume that adding @Async automatically provides persistence, retries, or delivery guarantees.

## 4. Commonly Used Spring APIs

### ApplicationEventPublisher

ApplicationEventPublisher is the contract for publishing events. You can inject it into a bean that needs to publish events:

~~~java
private final ApplicationEventPublisher eventPublisher;

public OrderService(ApplicationEventPublisher eventPublisher) {
    this.eventPublisher = eventPublisher;
}
~~~

After the order creation business logic succeeds, the bean calls:

~~~java
eventPublisher.publishEvent(new OrderPlaced(orderId, total));
~~~

ApplicationContext also implements ApplicationEventPublisher, so in small examples you can call context.publishEvent directly. In a service, injecting ApplicationEventPublisher usually expresses more clearly that the service only needs the ability to publish events, without needing to depend on the entire ApplicationContext.

### @EventListener

@EventListener marks a bean method as a listener. The method's parameter type tells Spring which event type the method wants to receive:

~~~java
@EventListener
public void handle(OrderPlaced event) {
    // Handle the newly created order
}
~~~

A bean can have multiple listener methods. Multiple beans can also listen to the same event type.

### ApplicationListener

ApplicationListener is a way to register a listener using an interface:

~~~java
public class OrderAuditListener
        implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        // Record the event
    }
}
~~~

This approach is typically used with event types that extend ApplicationEvent. For plain object events, @EventListener is a concise and intuitive way to declare a listener.

### Must an Event Extend ApplicationEvent?

No. In modern Spring, publishEvent accepts an Object. You can publish a plain Java object, such as an OrderPlaced record. Spring wraps that payload in a PayloadApplicationEvent when needed for internal dispatch; listeners declaring a parameter of the payload type can still receive the OrderPlaced object directly.

Extending ApplicationEvent remains a valid choice when you need to use a traditional event type or need an explicit event inheritance model. For new business events, an immutable record is usually simpler and easier to read.

## 5. Runnable Example with Java 17 and Spring Framework

The example below simulates an order being created. Two independent listeners both receive OrderPlaced: one sends a confirmation and one writes an audit record.

### Minimal Structure

Create a Maven project with two files:

- pom.xml
- src/main/java/demo/ApplicationEventsDemo.java

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-events-demo</artifactId>
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
                    <mainClass>demo.ApplicationEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### ApplicationEventsDemo.java

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
@ComponentScan(basePackageClasses = ApplicationEventsDemo.class)
public class ApplicationEventsDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             ApplicationEventsDemo.class)) {
            context.publishEvent(
                    new OrderPlaced("DH-1001", new BigDecimal("125000")));
        }
    }
}

record OrderPlaced(String orderId, BigDecimal total) {
}

@Component
class EmailConfirmationListener {

    @EventListener
    @Order(1)
    void sendConfirmation(OrderPlaced event) {
        System.out.println("Sending confirmation for order " + event.orderId());
    }
}

@Component
class AuditListener {

    @EventListener
    @Order(2)
    void writeAudit(OrderPlaced event) {
        System.out.println(
                "Writing audit for order " + event.orderId()
                        + ", total " + event.total().toPlainString());
    }
}
~~~

### Running the Program

In the directory containing pom.xml, run:

~~~bash
mvn -q compile exec:java
~~~

Output:

~~~text
Sending confirmation for order DH-1001
Writing audit for order DH-1001, total 125000
~~~

### Reading the Example

- OrderPlaced is a record-based event. The components of a record are final, so the event data cannot be mutated after creation in the usual way.
- main creates the ApplicationContext and publishes OrderPlaced using publishEvent.
- EmailConfirmationListener and AuditListener are two independent beans. Both declare @EventListener with an OrderPlaced parameter.
- @Order(1) and @Order(2) specify the listener order so that the demonstration output is deterministic and easy to compare.
- The publisher does not call the two listeners directly. If a new listener for OrderPlaced is added, the publisher does not need to know that listener's name or class.

The example uses ApplicationContext directly to focus on the event-publishing mechanism. In a real application, a service typically receives ApplicationEventPublisher via constructor injection and calls publishEvent after the corresponding business logic completes.

## 6. When Should You Use Application Events?

Consider Application Events when:

- A business action has just occurred and multiple components may need to react to it.
- The publisher does not need to receive a return value from listeners.
- The reactions have separate responsibilities and can be added or changed relatively independently.
- You want to keep the business service from having to know the list of auxiliary components.

Suitable examples include sending a notification after a user registers, recording an audit log after a profile changes, updating internal metrics after an order is created, or refreshing a cache after data is updated.

## 7. When Should You Not Use Events?

You should not use events just to replace every method call.

Call a method directly when:

- The caller needs a return value immediately.
- The called component's work is a mandatory step to complete the business operation.
- The processing flow needs to clearly express the order and error handling between steps.
- A direct call makes the source code easier to read and does not create problematic coupling.

For example, when OrderService needs to call PaymentService and must know whether payment succeeded or failed before confirming the order, a method API returning a result is usually more appropriate than a general notification event.

You also need to distinguish an **event** from a **command**. OrderPlaced states that an order has been created; PlaceOrder is a request to create an order. Listeners should react to an event that has occurred, rather than turning an event into a hidden command that makes readers unsure who is responsible for executing the business logic.

## 8. Limitations to Understand Correctly

### Events in ApplicationContext Are Internal Events

Application Events mainly serve communication between beans within the same Spring application. This mechanism does not automatically send events to another process, does not provide a durable queue, has no history for replay, and does not automatically retry when a listener fails.

If you need inter-service communication or durable message storage and delivery, consider a message broker such as RabbitMQ or Kafka with an appropriate integration mechanism.

### Events Do Not Wait for Transaction Commit by Default

With regular synchronous listeners, the listener is invoked at the moment the publisher publishes the event. If the publisher is inside a transaction, the listener may run before the transaction commits. Therefore, a listener should not assume that the data has already been committed and can be read from another transaction.

When you only want to process after a specific transaction phase, Spring provides @TransactionalEventListener. By default, this listener runs in the AFTER_COMMIT phase. If there is no active transaction, the listener is not invoked by default; enable fallbackExecution only when that behavior is genuinely appropriate.

If you need to guarantee that an event is persisted together with business data and can be resent after a failure, you must design a durable mechanism such as transactional outbox or an equivalent solution. Merely calling publishEvent does not create that guarantee.

### Synchronous Listeners Affect Latency and Errors

Because listeners run in the publisher's thread by default, a long-running listener increases the duration of the publish-event call. Exceptions from a listener can also propagate back and affect the publishing flow depending on the ErrorHandler configuration.

You can configure asynchronous processing or an ErrorHandler as needed, but you must explicitly decide how to observe errors, retries, ordering, and data consistency.

## 9. Best Practices

- Name events after the occurrence that happened, such as OrderPlaced or PaymentReceived.
- Use a small, meaningful, and preferably immutable payload. Include only the data listeners actually need, typically identifiers and relevant business information.
- Publish the event at the point where the business logic has reached the state asserted by the event name. Do not publish OrderPlaced before the order is actually created successfully.
- Keep listeners focused on a single responsibility for easier testing and modification.
- Specify ordering with @Order only when the order genuinely matters; avoid making listeners implicitly depend on each other.
- For listeners with side effects, consider idempotency so that repeated processing does not produce incorrect results.
- Do not include an entire managed entity or shared mutable object in an event if a listener could accidentally mutate the publisher's state.
- Do not create hard-to-trace cyclic event chains. If a business flow has multiple mandatory steps requiring explicit orchestration, express it using a service or an appropriate orchestration mechanism.

## 10. Takeaways

Application Events are Spring's internal notification mechanism. A publisher announces an occurrence; listeners subscribe to the event types they care about and process them independently. This approach reduces direct coupling, separates responsibilities, and makes adding new reactions easier.

By default, listeners run synchronously on the event-publishing thread. Application Events also do not automatically provide durable persistence, retries, inter-process communication, or post-commit transaction guarantees. Understanding these limitations helps you choose events in the right places and avoid using them in place of direct calls or a message broker.
