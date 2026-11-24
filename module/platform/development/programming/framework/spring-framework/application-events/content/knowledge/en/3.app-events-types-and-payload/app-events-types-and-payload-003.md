# PayloadApplicationEvent and the Actual Payload

## Objectives

After this lesson, you can explain why Spring wraps a plain object into PayloadApplicationEvent, distinguish the event wrapper from the business payload, choose the right parameter type for a listener, read data using getPayload(), and handle cases where the payload has a generic type.

## 1. Payload and Event Wrapper Are Two Different Layers of Meaning

When publishing an Application Event, two concepts must be distinguished:

- **Payload** is the business data that the publisher wants to announce. For example: an OrderPlaced object containing an order ID and total amount.
- **Event wrapper** is the object Spring uses to feed the payload into the Application Events system. The wrapper contains the payload, the publishing source, and the type information needed for dispatching.

In Spring Framework, the class serving as this wrapper is **PayloadApplicationEvent<T>**. The class resides in the org.springframework.context package, extends ApplicationEvent, and implements ResolvableTypeProvider.

The type parameter T describes the data type inside the wrapper. For example:

~~~java
PayloadApplicationEvent<OrderPlaced>
~~~

means an event wrapper carrying a payload of type OrderPlaced.

Do not conflate the wrapper with the payload. The wrapper is the structure Spring uses for dispatching; the payload is the content that listeners typically care about to perform business logic.

## 2. Spring Automatically Wraps Plain Objects on publishEvent

ApplicationEventPublisher has the method:

~~~java
void publishEvent(Object event);
~~~

When the passed-in object is already an ApplicationEvent, Spring publishes that event itself. When the passed-in object is not an ApplicationEvent, Spring wraps it in a PayloadApplicationEvent before dispatching it to listeners.

Example:

~~~java
OrderPlaced payload =
        new OrderPlaced("DH-2001", new BigDecimal("250000"));

eventPublisher.publishEvent(payload);
~~~

The publisher only needs to pass the OrderPlaced object. There is no need to manually create a PayloadApplicationEvent for typical cases.

Conceptually, the processing flow is equivalent to Spring creating a wrapper carrying that payload:

~~~java
PayloadApplicationEvent<OrderPlaced> event =
        new PayloadApplicationEvent<>(source, payload);
~~~

This illustrates the data structure, not a required call in the service. When using ApplicationEventPublisher.publishEvent(Object), Spring performs the wrapping step automatically.

### When Does Spring Not Wrap?

If the published object already extends ApplicationEvent, Spring treats it as a complete event and publishes that object itself. It does not wrap it in an outer PayloadApplicationEvent.

This creates two common patterns:

| Object passed by publisher | Object dispatched |
|---|---|
| A plain record or POJO | PayloadApplicationEvent<T> containing that object |
| A class extending ApplicationEvent | That ApplicationEvent object itself |

Therefore, when designing an event, clearly determine whether you are publishing a complete event class or a plain payload.

## 3. Structure and Data of PayloadApplicationEvent

PayloadApplicationEvent<T> has three parts to pay attention to:

- **source**: the object associated with the event publishing source. When ApplicationContext automatically wraps a payload via publishEvent(Object), source is typically the ApplicationContext publishing the event.
- **payload**: the actual data passed by the publisher.
- **payload type**: the data type of the payload, represented through ResolvableType so Spring can identify matching listeners, including in some generic cases.

Useful methods:

| API | Meaning |
|---|---|
| getSource() | Retrieves the event publishing source, inherited from EventObject |
| getPayload() | Retrieves the inner payload object |
| getResolvableType() | Retrieves the ResolvableType describing the type of the event and payload |

Example of reading the wrapper:

~~~java
void inspect(PayloadApplicationEvent<OrderPlaced> event) {
    Object source = event.getSource();
    OrderPlaced payload = event.getPayload();

    System.out.println(source.getClass().getSimpleName());
    System.out.println(payload.orderId());
}
~~~

getSource() and getPayload() serve two different purposes. Do not use source as a substitute for business data. If a listener needs the order ID, total amount, or order status, read those fields from payload.

PayloadApplicationEvent does not deep-copy the payload object. The wrapper holds a reference to the passed-in object. If the payload contains a collection or mutable object, modifying data after publishing the event can cause listeners to see altered state. Therefore, event payloads should be designed to be immutable or not modified after publishing.

## 4. Should a Listener Receive the Payload Directly or the Wrapper?

Spring supports both approaches. Choosing the parameter type determines whether the listener receives the business data or the entire event wrapper.

### Approach 1: Receiving the payload directly

This approach suits most business listeners:

~~~java
@EventListener
public void handleOrderPlaced(OrderPlaced event) {
    System.out.println(event.orderId());
}
~~~

Even though the publisher passed an OrderPlaced object and Spring wrapped it in PayloadApplicationEvent, Spring can recognize the payload type to invoke the listener method with the OrderPlaced object itself.

The listener does not need to know the wrapper details. This keeps handler code focused on business data.

### Approach 2: Receiving PayloadApplicationEvent

If you need to read the source, inspect the wrapper, or work with the event structure at the Spring level, declare the parameter with the wrapper type:

~~~java
@EventListener
public void inspectOrderEvent(
        PayloadApplicationEvent<OrderPlaced> event) {

    OrderPlaced payload = event.getPayload();

    System.out.println(event.getClass().getSimpleName());
    System.out.println(event.getSource().getClass().getSimpleName());
    System.out.println(payload.orderId());
}
~~~

With this approach, the listener receives the full PayloadApplicationEvent<OrderPlaced>, not just OrderPlaced.

Spring resolves the event type via ResolvableType and can match the payload type against the listener parameter type. Therefore, a payload-receiving listener and a wrapper-receiving listener can both listen to the same publish call.

### Which Approach to Choose?

- Use an OrderPlaced parameter when the listener only needs to process business data.
- Use PayloadApplicationEvent<OrderPlaced> when the listener genuinely needs the source, wrapper, or event type information.
- Avoid accepting PayloadApplicationEvent<?> only to manually cast it if the listener only handles one specific payload type.

A specific parameter type helps Spring filter events clearly and gives the compiler better type checking.

## 5. ApplicationListener and forPayload()

In addition to @EventListener, Spring also supports listeners implementing ApplicationListener.

ApplicationListener takes a type parameter that is a subclass of ApplicationEvent. For payload events, you can declare:

~~~java
ApplicationListener<PayloadApplicationEvent<OrderPlaced>> listener =
        event -> {
            OrderPlaced payload = event.getPayload();
            System.out.println(payload.orderId());
        };
~~~

This listener receives the wrapper and extracts the payload itself with getPayload().

Since Spring Framework 5.3, ApplicationListener provides the static method forPayload(Consumer<T>). This method creates a listener that receives PayloadApplicationEvent<T> but forwards only the payload to the Consumer:

~~~java
ApplicationListener<PayloadApplicationEvent<OrderPlaced>> listener =
        ApplicationListener.forPayload(
                payload -> System.out.println(payload.orderId()));
~~~

Registering the listener with ApplicationContext:

~~~java
context.addApplicationListener(listener);
~~~

Differences:

- ApplicationListener<PayloadApplicationEvent<OrderPlaced>> allows handling the wrapper and calling getPayload().
- ApplicationListener.forPayload(...) lets you write a consumer that only cares about the payload.
- @EventListener with an OrderPlaced parameter is the intuitive way to declare it inside a Spring bean.

Choose one approach based on the component's needs. There is no need to create multiple listeners performing the same reaction just to showcase different APIs.

## 6. Complete Example with Java 17 and Spring Framework

The following example publishes a plain OrderPlaced object. Spring automatically wraps it into PayloadApplicationEvent. One listener receives the payload directly, while the other receives the wrapper to read source and payload.

### Project Structure

~~~text
payload-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── PayloadEventsDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>payload-events-demo</artifactId>
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
                    <mainClass>demo.PayloadEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### PayloadEventsDemo.java

~~~java
package demo;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Configuration
@ComponentScan(basePackageClasses = PayloadEventsDemo.class)
public class PayloadEventsDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             PayloadEventsDemo.class)) {
            OrderPublisher publisher = context.getBean(OrderPublisher.class);
            publisher.publish(
                    new OrderPlaced("DH-2001", new BigDecimal("250000")));
        }
    }
}

record OrderPlaced(String orderId, BigDecimal total) {
}

@Component
class OrderPublisher {

    private final ApplicationEventPublisher eventPublisher;

    OrderPublisher(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    void publish(OrderPlaced payload) {
        eventPublisher.publishEvent(payload);
    }
}

@Component
class OrderEventListeners {

    @EventListener
    @Order(1)
    void receivePayload(OrderPlaced payload) {
        System.out.println(
                "Payload listener: " + payload.orderId()
                        + ", total=" + payload.total().toPlainString());
    }

    @EventListener
    @Order(2)
    void inspectWrapper(PayloadApplicationEvent<OrderPlaced> event) {
        System.out.println(
                "Envelope listener: " + event.getClass().getSimpleName());
        System.out.println(
                "Source type: " + event.getSource().getClass().getSimpleName());
        System.out.println(
                "Payload type: " + event.getPayload().getClass().getSimpleName());
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
Payload listener: DH-2001, total=250000
Envelope listener: PayloadApplicationEvent
Source type: AnnotationConfigApplicationContext
Payload type: OrderPlaced
~~~

### Execution Flow Analysis

1. Spring creates the ApplicationContext and registers OrderPublisher and OrderEventListeners.
2. OrderPublisher receives ApplicationEventPublisher via constructor injection.
3. The publish method passes the OrderPlaced object to publishEvent.
4. OrderPlaced does not extend ApplicationEvent, so Spring creates PayloadApplicationEvent<OrderPlaced> for dispatching.
5. The receivePayload listener declares an OrderPlaced parameter. Spring extracts the payload inside the wrapper and passes it to the method.
6. The inspectWrapper listener declares a PayloadApplicationEvent<OrderPlaced> parameter. Spring passes the wrapper so the method can read source and payload.
7. @Order(1) and @Order(2) clarify the ordering of the two listeners in the example.

The key observation is that the publisher only publishes OrderPlaced. The publisher does not create the wrapper itself and does not need to know which listener receives the payload directly or receives the wrapper.

## 7. Generic Payloads and ResolvableType

PayloadApplicationEvent<T> supports generic types. This type information is useful when a listener only wants to receive payloads of a specific type.

Example:

~~~java
ApplicationListener<PayloadApplicationEvent<OrderPlaced>> listener =
        event -> System.out.println(event.getPayload().orderId());
~~~

PayloadApplicationEvent implements ResolvableTypeProvider to supply type information to the event dispatch mechanism. Spring can use that information when matching listeners by generic type.

### Limitations Due to Type Erasure

Java erases most generic type information at runtime. For a simple payload like OrderPlaced, Spring can infer the type from the instance. However, if the payload is a collection such as List<OrderLine>, looking only at the collection's runtime class is usually not enough to determine the exact element type OrderLine.

For example, the following two values have the same runtime class as a concrete List implementation:

~~~java
List<OrderLine> orderLines;
List<Customer> customers;
~~~

If listener filtering depends on the generic element type, do not assume Spring can always infer that information from the instance alone.

### Passing an Explicit Payload Type

The three-argument constructor of PayloadApplicationEvent can accept a ResolvableType describing the payload. This approach is useful when you need to preserve generic information that cannot be inferred at runtime:

~~~java
import java.util.List;

import org.springframework.context.PayloadApplicationEvent;
import org.springframework.core.ResolvableType;

List<OrderLine> lines = List.of(
        new OrderLine("SP-01", 2),
        new OrderLine("SP-02", 1));

ResolvableType payloadType =
        ResolvableType.forClassWithGenerics(List.class, OrderLine.class);

PayloadApplicationEvent<List<OrderLine>> event =
        new PayloadApplicationEvent<>(this, lines, payloadType);

eventPublisher.publishEvent(event);
~~~

The listener can declare the exact wrapper type:

~~~java
@EventListener
void handleOrderLines(
        PayloadApplicationEvent<List<OrderLine>> event) {

    List<OrderLine> lines = event.getPayload();
    System.out.println(lines.size());
}
~~~

In the example above, payloadType describes the payload type List<OrderLine>, not the wrapper type PayloadApplicationEvent<List<OrderLine>>.

The constructor with the ResolvableType parameter was added in Spring Framework 6.0. For payloads with a concrete type, do not create the wrapper manually; use publishEvent(payload) so Spring wraps it automatically.

## 8. Payload Object vs. Custom ApplicationEvent

Both options are valid, but they serve different needs.

### Using a payload object

~~~java
record OrderPlaced(String orderId, BigDecimal total) {
}

eventPublisher.publishEvent(
        new OrderPlaced("DH-2001", new BigDecimal("250000")));
~~~

Suitable when:

- The event can be represented by a clear data object.
- Extending ApplicationEvent is unnecessary.
- You want listeners to receive a record or POJO directly.
- You want to reduce boilerplate instantiation code and keep payloads easy to test.

### Using a custom ApplicationEvent

~~~java
public final class OrderPlacedEvent extends ApplicationEvent {

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

When publishing:

~~~java
eventPublisher.publishEvent(
        new OrderPlacedEvent(this, "DH-2001"));
~~~

Spring publishes OrderPlacedEvent directly because it is already an ApplicationEvent. The listener accepts the exact event class:

~~~java
@EventListener
void handleOrderPlaced(OrderPlacedEvent event) {
    System.out.println(event.getOrderId());
}
~~~

A custom ApplicationEvent is suitable when you want to explicitly define an event class extending ApplicationEvent, need to use the superclass's source/timestamp, or want to control the event structure in the traditional model.

There is no need to extend ApplicationEvent just so Spring recognizes an object as an event. Since Spring Framework 4.2, plain objects can be published and automatically wrapped into PayloadApplicationEvent.

## 9. Common Pitfalls

### Confusing source with payload

event.getSource() returns the publishing source, not the business data. For payloads automatically wrapped by ApplicationContext, source is usually the context. To get OrderPlaced, call event.getPayload().

### Listener receiving the wrong data level

If a listener declares a PayloadApplicationEvent<OrderPlaced> parameter, it must read data via getPayload(). If the listener only needs OrderPlaced, declare an OrderPlaced parameter so Spring passes the payload directly.

### Using overly broad types

A listener accepting Object or PayloadApplicationEvent<?> can match too many events. This makes the execution flow hard to follow and makes it easy to handle unexpected payloads accidentally. Prefer specific event types.

### Wrapping payloads manually unnecessarily

For plain objects, simply call publishEvent(payload). Manually creating PayloadApplicationEvent is usually unnecessary unless there is a specific reason such as passing ResolvableType for a generic payload.

### Assuming payloads are copied

The wrapper does not guarantee creating an independent copy of the payload. If multiple listeners read the same mutable object, state mutations can cause unpredictable results. Prefer records, immutable collections, or data that is not modified after publishing.

### Confusing payload events with a message broker

PayloadApplicationEvent is an internal wrapper of Spring Application Events. It does not automatically serialize, durably store, send to another process, or provide retries. If inter-service communication is needed, integrate an appropriate messaging mechanism.

## 10. Key Takeaways

When a publisher passes an object not extending ApplicationEvent to publishEvent(Object), Spring automatically wraps that object in PayloadApplicationEvent<T>. The payload is the business data; the wrapper is the event Spring uses for dispatching.

Listeners can receive the payload directly by declaring a parameter of the payload type, or receive the full wrapper with PayloadApplicationEvent<T> and read getPayload() and getSource(). ApplicationListener.forPayload() is a concise option when using ApplicationListener while only needing a Consumer receiving the payload.

For generic payloads, ResolvableTypeProvider helps Spring recognize types. When type erasure prevents inferring element types from an instance, an explicit ResolvableType can be passed via the three-argument constructor of PayloadApplicationEvent. Choose immutable payloads, specific types, and clearly scoped listeners so events remain easy to understand and safe to extend.

## Official References

- [ApplicationEventPublisher — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [PayloadApplicationEvent — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/PayloadApplicationEvent.html)
- [ApplicationListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationListener.html)
- [ResolvableType — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/ResolvableType.html)