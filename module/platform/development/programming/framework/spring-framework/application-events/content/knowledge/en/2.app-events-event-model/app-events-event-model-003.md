# One Listener Receiving Multiple Event Types

In the Spring Framework, a publisher sends an event via `ApplicationEventPublisher.publishEvent(...)`. The ApplicationContext delivers the event to listeners with compatible types. Therefore, a single listener can handle multiple event classes within the same business flow, as long as we declare a suitable accepted type.

This lesson focuses on two common approaches with `@EventListener`:

- Declaring the parameter using a common interface or superclass. This is the right choice when events share a business meaning and the method needs to read each event's data.
- Listing multiple event classes via the `classes` attribute. This approach fits when multiple events need to run the same action and the method does not need to receive the payload.

Since Spring Framework 4.2, an event can be a regular Java object; the event class is not required to extend `ApplicationEvent`. Spring wraps the payload automatically when needed.

## 1. How Does Spring Determine Which Events a Listener Receives?

A method annotated with `@EventListener` becomes a listener when the bean containing it is registered in the ApplicationContext. With Java configuration or component scanning, Spring automatically registers the annotation processor to detect these methods.

When `classes` is not declared, Spring infers the event type from the method's single parameter. The listener is invoked when the published event type is compatible with the parameter type. Class inheritance and interface implementation both matter:

- Parameter is a superclass: receives instances of that class and its subclasses.
- Parameter is an interface: receives objects whose class implements that interface.
- The more specific the parameter, the narrower the listener; an overly general parameter such as `Object` can cause the method to receive a very large number of events.

Each time the publisher emits a matching event, Spring invokes the method once with that event. The listener does not receive a list of events, nor does Spring automatically group multiple publish calls into a batch.

## 2. Approach 1 — Using a Common Interface or Superclass

This is usually the clearest approach when multiple events belong to the same business group. We define a small contract containing common information, then have concrete events implement that contract.

For example, both order-placed and order-cancelled events have an order ID:

~~~java
public interface OrderEvent {
    String orderId();
}

public record OrderPlaced(String orderId) implements OrderEvent {
}

public record OrderCancelled(String orderId, String reason) implements OrderEvent {
}
~~~

The listener only needs to declare its parameter as `OrderEvent`:

~~~java
@Component
public class OrderAuditListener {

    @EventListener
    public void onOrderEvent(OrderEvent event) {
        if (event instanceof OrderPlaced placed) {
            System.out.println("Order created " + placed.orderId());
        } else if (event instanceof OrderCancelled cancelled) {
            System.out.println("Order cancelled " + cancelled.orderId()
                    + ": " + cancelled.reason());
        }
    }
}
~~~

When the publisher sends `OrderPlaced` or `OrderCancelled`, both are compatible with `OrderEvent`, so both enter the same method. Using `instanceof`, the method can still handle data specific to each event type.

An abstract class can be used instead of an interface if the events truly need to share state or behavior. Do not create a superclass merely to group unrelated events; a shared contract should reflect a real domain concept.

## 3. Complete Example with Java 17+

The following example uses Spring Framework 6.2.0, Java 17, and Maven. The entire program is in a single file for easy testing.

**File structure**

~~~text
spring-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventsDemo.java
~~~

**pom.xml**

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
                <configuration>
                    <mainClass>demo.ApplicationEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ApplicationEventsDemo.java**

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

@Configuration
public class ApplicationEventsDemo {

    @Bean
    public OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(ApplicationEventsDemo.class)) {
            context.publishEvent(new OrderPlaced("ORD-100"));
            context.publishEvent(
                    new OrderCancelled("ORD-200", "Customer requested cancellation"));
        }
    }

    public interface OrderEvent {
        String orderId();
    }

    public record OrderPlaced(String orderId) implements OrderEvent {
    }

    public record OrderCancelled(String orderId, String reason)
            implements OrderEvent {
    }

    public static class OrderAuditListener {

        @EventListener
        public void onOrderEvent(OrderEvent event) {
            if (event instanceof OrderPlaced placed) {
                System.out.println("Order created " + placed.orderId());
            } else if (event instanceof OrderCancelled cancelled) {
                System.out.println("Order cancelled " + cancelled.orderId()
                        + ": " + cancelled.reason());
            }
        }
    }
}
~~~

**Running the program**

From the directory containing `pom.xml`, run:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the listener:

~~~text
Order created ORD-100
Order cancelled ORD-200: Customer requested cancellation
~~~

**Execution flow**

1. Spring creates the ApplicationContext and registers the `OrderAuditListener` bean.
2. The `@EventListener` processor detects the `onOrderEvent(OrderEvent)` method.
3. The publisher sends an `OrderPlaced`. Because this record implements `OrderEvent`, the method is invoked and the `OrderPlaced` branch runs.
4. The publisher sends an `OrderCancelled`. The same method is invoked again, this time executing the `OrderCancelled` branch.
5. The context closes after both publish calls complete.

The records act as immutable event payloads. They do not need to extend `ApplicationEvent`; `AnnotationConfigApplicationContext.publishEvent(Object)` supports regular objects.

## 4. Approach 2 — Listing Multiple Events with the classes Attribute

If multiple event types need to trigger the same action and the method does not need to read the payload, you can declare the list of events directly on the annotation:

~~~java
@EventListener(classes = {
    ContextStartedEvent.class,
    ContextRefreshedEvent.class
})
public void onContextLifecycleChange() {
    System.out.println("ApplicationContext state changed");
}
~~~

Here, a single method is registered for both `ContextStartedEvent` and `ContextRefreshedEvent`. The method has no parameters, so it can only perform shared handling; it does not know which specific event type triggered that invocation.

In Spring Framework 6.2, when `classes` contains more than one event type, the method must declare no parameters. If only one class is declared in `classes`, the method can accept one event parameter. The `value` attribute is an alias for `classes`, so `@EventListener({A.class, B.class})` is equivalent to `@EventListener(classes = {A.class, B.class})`.

If you need to read the payload and branch by event type, prefer Approach 1: use a parameter that is a common interface or superclass. If the events do not share a reasonable contract, write separate listener methods so each method receives its exact data type.

## 5. Choosing the Right Approach

| Scenario | Recommended Approach | Reason |
|---|---|---|
| Events share common business data or behavior | Parameter is a common interface/superclass | One method receives the payload and can still check the concrete type |
| Multiple events need the same action, no payload needed | `@EventListener(classes = {...})` | Centralized declaration of the event list |
| Unrelated events requiring different data handling | Separate listener methods | Clear parameter types, fewer casts, and easier maintenance |
| Want to receive only a specific branch in an event hierarchy | Parameter is the concrete type | Limits the scope of events received |

## 6. Processing Order and Asynchronous Execution

By default, ApplicationContext event listeners run synchronously on the thread calling `publishEvent(...)`. The publisher continues only after synchronous listeners finish processing. Therefore, do not put long-running tasks such as calling external services or processing large files in a synchronous listener if doing so slows down the main flow.

You can combine `@Async` with `@EventListener` and enable `@EnableAsync` for asynchronous processing. In that case, note:

- Exceptions from an asynchronous listener are not thrown back to the publisher's calling thread.
- An asynchronous listener method cannot publish a follow-up event by returning an object; inject `ApplicationEventPublisher` and call `publishEvent(...)` explicitly.
- Do not assume `ThreadLocal` or logging context is automatically propagated to another thread.

If multiple listeners receive the same event and require an invocation order, you can use `@Order` on the listener methods. Order only has meaning among listeners handling a matching event.

## 7. Common Mistakes

- **Using an overly narrow parameter type:** A method accepting `OrderPlaced` will not receive `OrderCancelled`. Use a common contract if you want to group both types.
- **Using `Object` as the parameter for convenience:** This causes the listener to receive too many event types and forces type checks in every branch. Use it only when a truly generic handler is needed.
- **Declaring multiple classes in `classes` while still adding a parameter:** In Spring Framework 6.2, a list with more than one class requires a no-argument method.
- **Registering a listener outside the Spring container:** An object created with `new OrderAuditListener()` and not registered as a bean will not be automatically detected by the annotation processor.
- **Assuming one publish call delivers multiple events:** Each `publishEvent` call sends one event; the method may be called multiple times, once per matching event.
- **Putting heavy work in a synchronous listener:** That prolongs the duration of the publisher thread. Enable asynchronous execution only after clarifying thread, error, and ordering requirements.

## 8. Key Takeaways

A single listener method can receive multiple event classes via a common parameter type. Use an interface or superclass to model a group of events with shared business meaning; this approach preserves payloads and type safety.

Use `@EventListener(classes = {...})` when multiple events need to trigger the same parameterless handler. In Spring Framework 6.2, a method listing multiple events in `classes` must have no parameters.

## References

- [Spring Framework 6.2 — Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2.0 — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2.0 — ApplicationListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationListener.html)
