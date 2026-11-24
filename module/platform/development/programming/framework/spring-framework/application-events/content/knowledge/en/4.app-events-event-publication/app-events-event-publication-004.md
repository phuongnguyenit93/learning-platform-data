# Publishing Events from Services and Components in Spring

## Objectives

After this lesson, you will be able to:

- Explain why a Spring bean can publish application events.
- Inject ApplicationEventPublisher into beans stereotyped with @Service or @Component.
- Publish an event after a business action or a component task completes.
- Create events using Java records and have listeners receive them by data type.
- Understand the default processing flow when calling publishEvent.
- Choose the right place to publish events, avoiding premature or duplicate publication.
- Recognize the limitations of application events within the same ApplicationContext.

## 1. Which Beans Can Publish Events?

In Spring, publishing application events is not an exclusive capability of controllers or services. Any object managed by Spring as a bean can publish events if it receives an ApplicationEventPublisher.

Two common stereotypes are:

- @Service: denotes a bean containing business logic or coordinating a business operation.
- @Component: denotes a general-purpose Spring bean, such as an import coordinator, task tracker, or technical integration component.

Both are beans discovered by component scanning. Spring can inject ApplicationEventPublisher into their constructors.

A service typically publishes an event when business state has changed, such as when an order is created or a payment is completed. A component can publish an event when a task it is responsible for finishes, such as when a batch import has been processed.

The deciding factor is not which annotation is used, but whether the bean belongs to the ApplicationContext managing the listeners and whether the event accurately represents what just occurred.

## 2. What Does ApplicationEventPublisher Do?

ApplicationEventPublisher is Spring's interface used to publish an application event:

~~~java
public interface ApplicationEventPublisher {
    void publishEvent(Object event);
}
~~~

Once this interface is injected, the bean simply calls publishEvent with an event object. The publishing bean does not have to find listeners, invoke each listener individually, or know which beans are interested.

General flow:

1. Spring instantiates the publisher bean and injects ApplicationEventPublisher.
2. The publisher creates an event containing information about what just happened.
3. The publisher calls publishEvent(event).
4. The ApplicationContext dispatches the event to matching listeners registered in the context.
5. Listeners perform their work.

Since Spring Framework 4.2, custom events can be ordinary Java objects. Extending ApplicationEvent is no longer mandatory. With Java 17, a record is usually a concise way to represent an immutable payload.

## 3. Publishing Events from a Service

A service typically publishes an event after completing a business step. For example, OrderService creates an order and then notifies interested components with OrderPlacedEvent.

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void placeOrder(String orderId, String customerId) {
        // Perform or confirm the order creation step.
        System.out.println("1. OrderService: created order " + orderId);

        eventPublisher.publishEvent(
                new OrderPlacedEvent(orderId, customerId)
        );
    }
}
~~~

OrderService depends only on ApplicationEventPublisher. It does not need to inject OrderNotificationListener, AuditListener, or any concrete listener.

When a new listener needs to be added, the service can remain unchanged. The new listener simply needs to be Spring-managed and registered to receive OrderPlacedEvent.

In a real application, only publish OrderPlacedEvent after the order creation operation has reached the state the event name describes. If saving data fails, you should not publish an event asserting that the order was successfully created.

## 4. Publishing Events from a Component

A bean with the @Component stereotype can also receive ApplicationEventPublisher and publish events. For example, ImportComponent handles a batch import and notifies when the batch finishes.

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class ImportComponent {

    private final ApplicationEventPublisher eventPublisher;

    public ImportComponent(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void completeImport(String batchId, int importedRecords) {
        // Here we assume the import process has completed successfully.
        System.out.println(
                "3. ImportComponent: completed import batch " + batchId
        );

        eventPublisher.publishEvent(
                new ImportCompletedEvent(batchId, importedRecords)
        );
    }
}
~~~

ImportComponent does not need to extend a special class or access ApplicationContext directly. It uses the same ApplicationEventPublisher interface as OrderService.

Publishing events from a component is appropriate when the component owns a clearly meaningful event within the scope of its work. If the component is merely a small helper called inside a service, consider letting the service publish the event at the business boundary rather than publishing events from every intermediate class. This helps avoid duplicate publications or making the business flow hard to follow.

## 5. Defining Events

Each event should describe something that has happened and carry the data listeners need.

File OrderPlacedEvent.java:

~~~java
package com.example.events;

public record OrderPlacedEvent(
        String orderId,
        String customerId
) {
}
~~~

File ImportCompletedEvent.java:

~~~java
package com.example.events;

public record ImportCompletedEvent(
        String batchId,
        int importedRecords
) {
}
~~~

The two events are distinct data types. Based on the listener's parameter type, Spring can dispatch the right event to the right handler method.

Prefer past-tense event names such as OrderPlacedEvent or ImportCompletedEvent when the occurrence has already happened. If the object represents a request to be carried out in the future, choose a name that reflects that request semantics, such as ImportRequestedEvent.

Keep the payload just large enough for listeners. There is no need to put an entire service, repository, or ApplicationContext inside an event. If an event must carry collections or mutable objects, create a snapshot and protect the data before publishing.

## 6. Listeners Receiving Events

Publishers and listeners are connected via the event type. A listener must be a Spring bean and annotate its handler method with @EventListener.

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationEventListeners {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        System.out.println(
                "2. Listener: order " + event.orderId()
                        + " created for " + event.customerId()
        );
    }

    @EventListener
    public void onImportCompleted(ImportCompletedEvent event) {
        System.out.println(
                "4. Listener: batch " + event.batchId()
                        + " completed, " + event.importedRecords()
                        + " records"
        );
    }
}
~~~

Spring selects the method based on the parameter type:

- onOrderPlaced receives OrderPlacedEvent.
- onImportCompleted receives ImportCompletedEvent.

A single listener bean can have multiple @EventListener methods. You can also split listeners across multiple beans if they belong to different responsibilities.

The publisher does not need to call those methods directly. This keeps event-publishing services and components decoupled from the list of existing listeners.

## 7. Complete Runnable Example

The example below uses Java 17 and Spring Boot 3.5.0. OrderService publishes an event from a @Service bean; ImportComponent publishes an event from a @Component bean. One listener receives both event types.

### Directory Structure

~~~text
spring-publish-from-beans/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        ├── PublishFromBeansApplication.java
                        ├── OrderPlacedEvent.java
                        ├── ImportCompletedEvent.java
                        ├── OrderService.java
                        ├── ImportComponent.java
                        └── ApplicationEventListeners.java
~~~

### 7.1. Dependencies

File pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-publish-from-beans</artifactId>
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

### 7.2. Two Event Classes

File OrderPlacedEvent.java:

~~~java
package com.example.events;

public record OrderPlacedEvent(
        String orderId,
        String customerId
) {
}
~~~

File ImportCompletedEvent.java:

~~~java
package com.example.events;

public record ImportCompletedEvent(
        String batchId,
        int importedRecords
) {
}
~~~

### 7.3. Service Publisher

File OrderService.java:

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void placeOrder(String orderId, String customerId) {
        System.out.println("1. OrderService: created order " + orderId);

        eventPublisher.publishEvent(
                new OrderPlacedEvent(orderId, customerId)
        );
    }
}
~~~

### 7.4. Component Publisher

File ImportComponent.java:

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class ImportComponent {

    private final ApplicationEventPublisher eventPublisher;

    public ImportComponent(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void completeImport(String batchId, int importedRecords) {
        System.out.println(
                "3. ImportComponent: completed import batch " + batchId
        );

        eventPublisher.publishEvent(
                new ImportCompletedEvent(batchId, importedRecords)
        );
    }
}
~~~

### 7.5. Listener

File ApplicationEventListeners.java:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationEventListeners {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        System.out.println(
                "2. Listener: order " + event.orderId()
                        + " created for " + event.customerId()
        );
    }

    @EventListener
    public void onImportCompleted(ImportCompletedEvent event) {
        System.out.println(
                "4. Listener: batch " + event.batchId()
                        + " completed, " + event.importedRecords()
                        + " records"
        );
    }
}
~~~

### 7.6. Entry Point

File PublishFromBeansApplication.java:

~~~java
package com.example.events;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PublishFromBeansApplication implements CommandLineRunner {

    private final OrderService orderService;
    private final ImportComponent importComponent;

    public PublishFromBeansApplication(
            OrderService orderService,
            ImportComponent importComponent
    ) {
        this.orderService = orderService;
        this.importComponent = importComponent;
    }

    public static void main(String[] args) {
        SpringApplication.run(PublishFromBeansApplication.class, args);
    }

    @Override
    public void run(String... args) {
        orderService.placeOrder("ORD-1001", "CUS-01");

        importComponent.completeImport("BATCH-07", 120);
    }
}
~~~

Spring Boot scans the com.example.events package and creates the beans. When CommandLineRunner runs, it calls the service first, then the component.

Run the application from the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Ignoring Spring Boot startup logs, the exact output printed by the application is:

~~~text
1. OrderService: created order ORD-1001
2. Listener: order ORD-1001 created for CUS-01
3. ImportComponent: completed import batch BATCH-07
4. Listener: batch BATCH-07 completed, 120 records
~~~

Listeners run synchronously by default, so each listener's output appears right inside the corresponding publishEvent call. Once the listener finishes handling the event, the publisher resumes execution.

## 8. Constructor Injection Is Recommended

You can inject ApplicationEventPublisher via constructor:

~~~java
@Service
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }
}
~~~

Constructor injection offers several benefits:

- Dependencies are explicitly visible in the bean declaration.
- Fields can be declared final.
- It is easy to write unit tests with a fake or mock publisher.
- The bean cannot be instantiated without its required dependency.

There is no need to inject ApplicationContext just to call publishEvent. ApplicationEventPublisher is a narrower abstraction that accurately expresses the bean's intent.

Avoid using a static ApplicationContext holder or calling ApplicationContextAware just to obtain a global publisher. Those approaches hide dependencies and make testing and configuration changes harder.

## 9. Synchronous, Asynchronous, and Listener Errors

By default, application events are dispatched synchronously. Listeners run on the thread publishing the event:

- The publisher waits for synchronous listeners to finish.
- Slow listeners make the publishEvent call take longer.
- Exceptions from synchronous listeners can propagate back to the publisher and affect the calling thread.

If the work does not need to finish immediately, you can annotate the listener with @Async and enable @EnableAsync:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Component
public class ImportEventListener {

    @Async
    @EventListener
    public void processImportCompleted(ImportCompletedEvent event) {
        System.out.println(
                "Background processing for " + event.batchId()
        );
    }
}
~~~

With asynchronous listeners, the publisher does not wait for the task to finish. Completion order is not guaranteed, and exceptions do not propagate back to the publisher the way they do for synchronous listeners. You must configure an executor, monitor errors, and avoid sharing mutable state across threads.

If multiple listeners need to run after a transaction commits, consider @TransactionalEventListener with an appropriate phase. For example, AFTER_COMMIT runs only after the transaction succeeds; the listener requires an active transaction accordingly. Regular application events do not automatically guarantee that data has committed before the listener runs.

## 10. Choosing Where to Publish Events

| Scenario | Suitable Publication Point |
|---|---|
| An order is created after the service finishes business logic | The service publishes OrderPlacedEvent. |
| A payment is confirmed in business logic | PaymentService publishes PaymentCompletedEvent. |
| An import component completes a batch and owns batch details | The component publishes ImportCompletedEvent. |
| A helper only performs a small step inside a service | Usually let the service publish the event after completing the overall action. |
| Another application or service needs to be notified | Use a message broker or inter-process messaging mechanism. |

Publish the event where it is known for certain that the occurrence happened and where sufficient data is available to describe it. Do not have multiple classes publish the same event for the same action, as listeners could process duplicates.

Events should carry clear business or technical meaning. Avoid publishing overly generic events like SomethingChangedEvent when listeners cannot tell exactly what changed.

## 11. Limitations of Application Events

Application events are dispatched within Spring's ApplicationContext event mechanism. They are useful for decoupling beans within the same application, but they do not replace a message broker.

Keep in mind:

- Events are not automatically persisted for replay when the application restarts.
- Events are not automatically sent to another JVM or service.
- The publisher does not automatically receive business results from listeners.
- Synchronous listeners can directly affect the duration and outcome of the publisher's call.
- Asynchronous listeners require dedicated thread management and error-handling policies.

If reliable message delivery across multiple services is needed, use an appropriate messaging solution. If you must guarantee an event is sent when a data transaction commits, look into a transactional outbox or equivalent mechanism rather than assuming publishEvent is durable.

## 12. Common Errors

| Error | Cause | Resolution |
|---|---|---|
| Cannot inject publisher | The bean is not Spring-managed or the constructor declares the wrong dependency. | Ensure the bean has @Service/@Component or is declared with @Bean. |
| Listener does not receive the event | The listener is not registered or its parameter type does not match. | Check component scanning and the event type in the @EventListener method. |
| Component publishes an event but no listener runs | The component and listener are not in the same appropriate ApplicationContext scope or the listener is not registered. | Check context configuration and bean registration. |
| Listener runs before business logic finishes | The publisher publishes the event too early. | Publish the event after the required business step or use @TransactionalEventListener. |
| Listener processes duplicates | Multiple places publish the same event for one action. | Pick one clear publication point and enforce idempotency when needed. |
| Publisher is slow | A synchronous listener performs a long-running task. | Optimize the listener or consider @Async if business rules permit. |
| Expecting events to be sent to another service | Confusing application events with a message broker. | Use an inter-process messaging mechanism. |
| Listener reads unstable data | The payload contains mutable collections or objects modified after publishing. | Use records and defensive copies to create immutable snapshots. |

## 13. Self-Check

1. Why can both @Service and @Component inject ApplicationEventPublisher?
2. When publishing OrderPlacedEvent, why does OrderService not need to know about ApplicationEventListeners?
3. If a component is not managed by Spring and is instantiated with new, can it have the publisher injected automatically?
4. Why should events be published after the business action has completed?
5. Does publishEvent wait for listeners to finish by default?
6. When should @TransactionalEventListener be used?
7. Can ApplicationEventPublisher replace a message broker to send events to another service?
8. Why should only one publication point be chosen for a specific occurrence?

**Key takeaway:** Any Spring bean, including @Service and @Component, can inject ApplicationEventPublisher and publish events. The bean simply describes what happened with an event object; Spring dispatches it to matching listeners in the ApplicationContext. Publish events at the right business boundary, use constructor injection, and choose synchronous, asynchronous, or transactional listeners according to your actual requirements.
