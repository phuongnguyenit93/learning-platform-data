# ApplicationListener<E>

**ApplicationListener<E>** is a Spring Framework interface used to register a bean to receive and handle an application event of type E. When a matching event is published in the ApplicationContext, Spring invokes the listener's onApplicationEvent(event) method. The generic type E explicitly states which event the listener is interested in, helping Spring filter listeners and helping your code avoid manual type casting.

## 1. Declaration and Meaning

The interface resides in the org.springframework.context package. Its general form is:

~~~java
@FunctionalInterface
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {

    void onApplicationEvent(E event);
}
~~~

Key points to understand:

- **E extends ApplicationEvent:** the event type must be ApplicationEvent or one of its subclasses.
- **onApplicationEvent(E event):** the callback Spring invokes when a compatible event occurs.
- **extends EventListener:** a marker interface for listeners.
- **Generic E:** describes the specific event type handled by the listener.

Example:

~~~java
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Order created: " + event.getOrderId());
    }
}
~~~

Here E is OrderCreatedEvent, so the method directly receives the specific event type. If you declare ApplicationListener<ApplicationEvent>, the listener may receive many kinds of application events and must branch manually when handling them. Usually, you should declare the narrowest type that the listener actually needs.

## 2. Events Received by the Listener

ApplicationListener<E> requires E to extend ApplicationEvent. A business event can be defined as follows:

~~~java
import org.springframework.context.ApplicationEvent;

public class OrderCreatedEvent extends ApplicationEvent {

    private final String orderId;

    public OrderCreatedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

ApplicationEvent stores the source, which is the object that originated the event. Domain-specific data is stored in fields of the subclass. An event should express something that has already happened, such as OrderCreatedEvent, PaymentCompletedEvent, or UserRegisteredEvent.

Prefer immutable events containing the data needed by listeners, such as IDs, values, and the timestamp of occurrence. Avoid passing a large mutable entity if the listener only needs an identifier; doing so couples the listener to state that can change.

Since Spring Framework 4.2, a publisher can also accept a regular POJO or record. Spring wraps the payload in **PayloadApplicationEvent**. However, the generic E of ApplicationListener must still be an ApplicationEvent type. If you want to receive a POJO payload via the interface, you can declare ApplicationListener<PayloadApplicationEvent<MyPayload>> and call event.getPayload(). If you want the listener method to receive MyPayload directly, @EventListener is usually more concise.

## 3. How Spring Detects and Invokes Listeners

A Spring-managed bean that implements ApplicationListener is detected during ApplicationContext initialization. The context registers the listener with the ApplicationEventMulticaster.

Basic flow:

1. The ApplicationContext initializes and detects beans implementing ApplicationListener.
2. Those listeners are registered with the context's ApplicationEventMulticaster.
3. A business bean calls ApplicationEventPublisher.publishEvent(event).
4. The context forwards the event to the multicaster.
5. The multicaster selects listeners whose event type matches.
6. Spring invokes onApplicationEvent(event) on the selected listeners.

The publisher does not need to know which listeners exist. Listeners also do not need to be called directly by the service that emits the event. The wiring is performed through the context and the multicaster.

### Registering a Listener as a Bean

You can use component scanning:

~~~java
@Component
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Handle the event.
    }
}
~~~

Or declare it with Java configuration:

~~~java
@Configuration
public class EventConfig {

    @Bean
    public OrderCreatedListener orderCreatedListener() {
        return new OrderCreatedListener();
    }
}
~~~

An important requirement is that the listener must be managed by Spring. An object created with new outside the container is not automatically registered with the multicaster. When manual registration is needed, you can use ConfigurableApplicationContext.addApplicationListener(...); in typical applications, declaring a bean is the simplest approach.

## 4. Generic E Helps Filter Events

Suppose an application has two events: OrderCreatedEvent and PaymentCompletedEvent. You can register separate listeners:

~~~java
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Handle new order.
    }
}

public class PaymentCompletedListener
        implements ApplicationListener<PaymentCompletedEvent> {

    @Override
    public void onApplicationEvent(PaymentCompletedEvent event) {
        // Handle completed payment.
    }
}
~~~

The listener for OrderCreatedEvent does not need to receive every event and filter with instanceof manually. Spring uses the event type declared by the listener to select compatible listeners. A listener declaring ApplicationListener<DomainEvent> can receive events of subclasses of DomainEvent.

### Generics and Runtime Type Matching

Java performs type erasure on generics, but Spring analyzes the generic type of a listener using ResolvableType and internal adapters. When the type is clearly declared in the class or class hierarchy, Spring can use that information to filter events.

Avoid raw types such as ApplicationListener without a generic parameter. Raw types lose type information at the source-code level, reduce type safety, and make the listener registration intent less clear. Keep the specific event type in the declaration.

## 5. Receiving a POJO Payload via ApplicationListener

You can publish an ordinary Java object:

~~~java
public record OrderCreated(String orderId) {
}

// Inside a bean:
publisher.publishEvent(new OrderCreated("ORD-1001"));
~~~

Spring wraps this object in PayloadApplicationEvent. An interface-based listener can receive the wrapper:

~~~java
public class OrderPayloadListener
        implements ApplicationListener<PayloadApplicationEvent<OrderCreated>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<OrderCreated> event) {
        OrderCreated payload = event.getPayload();
        System.out.println(payload.orderId());
    }
}
~~~

PayloadApplicationEvent is an ApplicationEvent and carries the payload type information so Spring can dispatch appropriately when the generic type is clearly preserved.

If you do not need access to the wrapper, you can use an annotation to receive the payload directly:

~~~java
@Component
public class OrderPayloadListener {

    @EventListener
    public void onOrderCreated(OrderCreated event) {
        System.out.println(event.orderId());
    }
}
~~~

Choose ApplicationListener when you want a class with an explicit interface contract and a single primary event entry point. Choose @EventListener when you want method-level handlers, direct POJO reception, multiple handlers, or SpEL conditions.

## 6. Listener Invocation Order

When multiple listeners receive the same event, you can specify the order using the Ordered interface or the @Order annotation. Lower values have higher priority.

~~~java
@Component
@Order(1)
public class AuditListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Audit: " + event.getOrderId());
    }
}

@Component
@Order(2)
public class NotificationListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Notify: " + event.getOrderId());
    }
}
~~~

You can implement Ordered if you want to determine the order programmatically:

~~~java
public class AuditListener
        implements ApplicationListener<OrderCreatedEvent>, Ordered {

    @Override
    public int getOrder() {
        return 1;
    }

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Record audit.
    }
}
~~~

Specify an order only when the listeners genuinely depend on a processing sequence. If they are independent, do not introduce an implicit dependency on invocation order. When configured asynchronously, completion order may differ from synchronous execution.

## 7. Synchronous, Asynchronous, and Exceptions

With the default SimpleApplicationEventMulticaster, listeners are invoked synchronously on the thread that publishes the event. Therefore:

- publishEvent typically returns only after synchronous listeners finish.
- A slow listener increases the processing time of the service or request that emits the event.
- An exception from a synchronous listener can propagate back to the publisher if no ErrorHandler is configured.

You can configure an executor on SimpleApplicationEventMulticaster for asynchronous dispatch. In that case, listeners may run on different threads and the publisher can continue before listeners complete. You must consider thread safety, completion order, transaction context, and exception handling in async tasks.

In modern Spring Framework, ApplicationListener has a supportsAsyncExecution method allowing a listener to customize its ability to run asynchronously. If overridden to return false, the listener requests synchronous invocation even when the multicaster has an executor. Use this only when there is a clear reason for the listener to run on the publisher thread.

If a listener must run after the transaction commits, you can use @TransactionalEventListener. A standard ApplicationListener does not express transaction phases on its own. When business logic depends on committed data, use the appropriate transaction-aware mechanism instead of assuming events are always published after commit.

## 8. Complete Example with Java 17 and Spring Framework

This example creates a context, injects ApplicationEventPublisher into OrderService, and registers two listeners implementing ApplicationListener<OrderCreatedEvent>. The two listeners are ordered using @Order. The example uses Java 17 and Spring Framework 6.2.0.

### Directory Structure

~~~text
application-listener-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationListenerDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>application-listener-demo</artifactId>
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
                <configuration>
                    <release>17</release>
                </configuration>
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

### ApplicationListenerDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

public class ApplicationListenerDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            service.createOrder("ORD-1001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public AuditListener auditListener() {
            return new AuditListener();
        }

        @Bean
        public NotificationListener notificationListener() {
            return new NotificationListener();
        }
    }

    public static class OrderCreatedEvent extends ApplicationEvent {

        private final String orderId;

        public OrderCreatedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static class OrderService {

        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void createOrder(String orderId) {
            System.out.println("Created: " + orderId);
            publisher.publishEvent(new OrderCreatedEvent(this, orderId));
        }
    }

    @Order(1)
    public static class AuditListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println("Audit: " + event.getOrderId());
        }
    }

    @Order(2)
    public static class NotificationListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println("Notify: " + event.getOrderId());
        }
    }
}
~~~

### Compile and Run

Run in the directory containing pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ApplicationListenerDemo
~~~

Stdout output:

~~~text
Created: ORD-1001
Audit: ORD-1001
Notify: ORD-1001
~~~

Execution flow:

1. AnnotationConfigApplicationContext initializes AppConfig and the beans.
2. OrderService receives ApplicationEventPublisher from the context via the @Bean parameter.
3. createOrder prints the order creation message and publishes OrderCreatedEvent.
4. The multicaster selects both listeners because both declare ApplicationListener<OrderCreatedEvent>.
5. @Order(1) causes AuditListener to be invoked before @Order(2) NotificationListener during synchronous dispatch.
6. OrderService does not call any listener directly; Spring performs the dispatch.

## 9. Comparing ApplicationListener and @EventListener

| Criterion | ApplicationListener<E> | @EventListener |
|---|---|---|
| Form | Implements an interface | Annotates a method in a bean |
| Event type | E must extend ApplicationEvent | Accepts ApplicationEvent or POJO payload |
| Number of handlers | One onApplicationEvent method per implementation | A single bean can have multiple methods |
| Filtering conditions | Generic event type or logic inside handler | Can use condition with SpEL |
| Ordering | Ordered or @Order | Ordered or @Order |
| Best suited for | Listeners with an explicit interface contract | Flexible method-based handling |

Use ApplicationListener when you want a class to express its listener role explicitly via an interface, need a reusable contract, or integrate with interface-based Spring APIs. Use @EventListener when you want concise code, direct payload reception, or multiple handlers in the same bean.

## 10. Common Pitfalls

| Pitfall | Consequence | How to Handle |
|---|---|---|
| Using raw ApplicationListener type | Loses event type info and reduces type safety | Use ApplicationListener<OrderCreatedEvent> |
| Using a POJO directly as E | Fails to compile because E must extend ApplicationEvent | Use PayloadApplicationEvent<MyPayload> or @EventListener |
| Listener is not a Spring bean | Context does not auto-register the listener | Declare @Component or @Bean |
| Creating listener with new outside container | Listener is not managed by the multicaster | Let Spring create the bean or register it via the context |
| Every listener accepts ApplicationEvent | Forces manual branching and increases coupling | Declare a specific event type |
| Assuming listeners run in background by default | Publisher still waits for synchronous listeners | Configure an executor or @Async when appropriate |
| Relying on accidental registration order | Sequence lacks stability | Use @Order or Ordered when needed |
| Not handling exceptions | Listener failure can affect the publishing flow | Define error handling and logging |
| Using internal events instead of a message broker | No durability or cross-process delivery by default | Use a broker/outbox when needed |

## 11. Implementation Checklist

- Clearly identify the event the listener needs to receive.
- Use ApplicationListener with a specific generic event type.
- Ensure E extends ApplicationEvent; for POJO payloads, use PayloadApplicationEvent or @EventListener.
- Register the listener as a bean in the right ApplicationContext.
- Keep events immutable and include only necessary data.
- Use @Order or Ordered when an ordering requirement truly exists.
- Decide whether the listener runs synchronously or asynchronously.
- Handle exceptions and transactions according to business requirements.
- Write unit tests for listener logic and integration tests to verify context registration, filtering, and invocation.

**ApplicationListener<E>** provides an explicit contract for Spring beans to listen to events by type. When you declare a specific E, register the listener in the ApplicationContext, and keep events clearly structured, your application can decouple event emission from event handling while preserving type safety and testability.