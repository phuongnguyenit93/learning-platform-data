# Communicating Between Beans in the Same ApplicationContext Using Application Events

## Objectives

After this lesson, you will be able to:

- Explain why beans in Spring need to communicate via application events.
- Create an event carrying business data using a Java record.
- Publish events using ApplicationEventPublisher.
- Register listening beans using @EventListener.
- Describe the default processing order, how to order listeners, and when asynchronous processing is needed.
- Recognize when to use an event and when to call a method directly.

## 1. What Problem Do Application Events Solve?

Suppose PaymentService confirms a payment. After the payment succeeds, the system needs to send a receipt, write an audit history, and update statistics.

If PaymentService calls ReceiptService, AuditService, and StatisticsService directly, it must know the names of and depend on all of those beans. Whenever you add a new task, you have to modify PaymentService again. The components thus become tightly coupled.

Application Events provide a publish-subscribe style of communication:

- The event-publishing bean only needs to know that an event has occurred.
- Interested beans register listeners to receive that event.
- A single event can be handled by multiple listeners in the same ApplicationContext.
- The event-publishing bean does not need to call each listener directly.

For example, PaymentService publishes PaymentCompletedEvent. ReceiptListener and AuditListener can both receive this event without PaymentService needing to know that the two listeners exist.

This approach fits when an action needs to notify multiple other parts of the application. If you need to invoke a specific operation and get a result immediately, calling a method directly is usually easier to understand.

## 2. Key Components

| Component | Role |
|---|---|
| Event | An object describing an occurrence that happened and carrying the data needed by listeners. |
| Publisher | A bean that publishes events via ApplicationEventPublisher. |
| Listener | A Spring bean with a method annotated with @EventListener to receive matching events. |
| ApplicationContext | Manages beans and dispatches events to listeners registered in that context. |

ApplicationContext implements ApplicationEventPublisher. When you inject ApplicationEventPublisher into a bean, you are using a dedicated interface for publishing events without having to depend directly on a concrete ApplicationContext class.

An event can be a plain Java object. Since Spring Framework 4.2, you do not need to extend ApplicationEvent for new custom events. Using a record is a concise choice and keeps event data immutable.

## 3. Processing Flow Within the Same ApplicationContext

1. Spring instantiates PaymentService and ReceiptListener as managed beans within the same ApplicationContext.
2. Spring injects ApplicationEventPublisher into PaymentService.
3. When the payment completes, PaymentService creates PaymentCompletedEvent and calls publishEvent.
4. The ApplicationContext dispatches the event to listeners with a matching parameter type.
5. ReceiptListener receives the event, reads the data, and sends the receipt.
6. After the synchronous listener finishes, the publishEvent call returns control to PaymentService.

The key point is that the publisher only publishes the event. The listener decides what to do upon receiving the event. An event should represent something that has happened, usually named in the past tense such as PaymentCompletedEvent, OrderCreatedEvent, or UserRegisteredEvent.

## 4. Complete Example with Java 17 and Spring Boot

This example creates a small application: PaymentService confirms a payment and publishes an event; ReceiptListener receives the event and prints receipt details. Both beans are managed by Spring in the same ApplicationContext.

### Directory Structure

~~~text
application-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        ├── ApplicationEventsDemoApplication.java
                        ├── PaymentCompletedEvent.java
                        ├── PaymentService.java
                        └── ReceiptListener.java
~~~

### 4.1. Declaring Dependencies

Create a pom.xml file in the root directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>application-events-demo</artifactId>
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

### 4.2. Creating the Event Class

File PaymentCompletedEvent.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

public record PaymentCompletedEvent(
        String paymentId,
        BigDecimal amount
) {
}
~~~

This record carries the payment ID and the amount paid. Because a record has immutable data components, a listener can read the information without worrying about another bean directly modifying the event's fields.

### 4.3. Publishing the Event from PaymentService

File PaymentService.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final ApplicationEventPublisher eventPublisher;

    public PaymentService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void completePayment(String paymentId, BigDecimal amount) {
        System.out.println(
                "1. PaymentService: confirming payment " + paymentId
        );

        eventPublisher.publishEvent(
                new PaymentCompletedEvent(paymentId, amount)
        );

        System.out.println(
                "3. PaymentService: continuing after publishing event"
        );
    }
}
~~~

PaymentService depends only on ApplicationEventPublisher. It does not inject ReceiptListener and does not need to know which listeners will handle the event.

The publishEvent call accepts an event object. In this example, the object is created from the PaymentCompletedEvent record.

### 4.4. Receiving the Event with @EventListener

File ReceiptListener.java:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReceiptListener {

    @EventListener
    public void onPaymentCompleted(PaymentCompletedEvent event) {
        System.out.println(
                "2. ReceiptListener: sending receipt for "
                        + event.paymentId()
                        + ", amount "
                        + event.amount()
        );
    }
}
~~~

Spring recognizes the onPaymentCompleted method as a listener thanks to @EventListener. The parameter type PaymentCompletedEvent tells Spring which event this method is interested in.

ReceiptListener must be a Spring-managed bean and must be registered in the ApplicationContext receiving the event. Placing @EventListener on an object created manually with the new keyword will not automatically register that object with Spring.

### 4.5. Starting the Application

File ApplicationEventsDemoApplication.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApplicationEventsDemoApplication
        implements CommandLineRunner {

    private final PaymentService paymentService;

    public ApplicationEventsDemoApplication(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public static void main(String[] args) {
        SpringApplication.run(
                ApplicationEventsDemoApplication.class,
                args
        );
    }

    @Override
    public void run(String... args) {
        paymentService.completePayment(
                "PAY-001",
                new BigDecimal("250000")
        );
    }
}
~~~

Run the application from the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Lines printed by the application, omitting Spring Boot startup logs:

~~~text
1. PaymentService: confirming payment PAY-001
2. ReceiptListener: sending receipt for PAY-001, amount 250000
3. PaymentService: continuing after publishing event
~~~

Line 2 appears before line 3 because listeners run synchronously by default. When publishEvent is called, Spring invokes the listener on the event-publishing thread. The publishEvent call only continues after the synchronous listener finishes processing.

## 5. An Event Can Have Multiple Listeners

Multiple beans can listen to the same event type. For example, after a payment completes, in addition to ReceiptListener there is AuditListener to record the history:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class AuditListener {

    @EventListener
    @Order(1)
    public void recordPayment(PaymentCompletedEvent event) {
        System.out.println(
                "Audit: recorded payment " + event.paymentId()
        );
    }
}
~~~

When PaymentCompletedEvent is published, both ReceiptListener and AuditListener can receive the event. The publisher does not have to add new calls when a new listener is added.

If you need to specify the order among multiple listeners handling the same event, use @Order. Lower order values take precedence and run first. If no order is declared, you should not rely on bean registration order to make business decisions.

## 6. Synchronous and Asynchronous

### Default: Synchronous

With the default configuration, listeners run on the event-publishing thread. This means:

- The publisher waits for the listener to finish processing before continuing.
- The listener can read data in the same execution thread.
- A long-running listener slows down the event-publishing operation.
- Errors raised by a synchronous listener can propagate back to the caller of publishEvent.

This approach is suitable for short tasks that need to complete immediately within the current execution flow.

### When Asynchronous Processing Is Needed

You can mark a listener with @Async and enable asynchronous processing with @EnableAsync:

~~~java
package com.example.events;

import org.springframework.scheduling.annotation.Async;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AsyncAuditListener {

    @Async
    @EventListener
    public void recordPayment(PaymentCompletedEvent event) {
        System.out.println(
                "Processing audit asynchronously for " + event.paymentId()
        );
    }
}
~~~

Add @EnableAsync to the configuration class or the application class annotated with @SpringBootApplication:

~~~java
@EnableAsync
@SpringBootApplication
public class ApplicationEventsDemoApplication {
    // Application startup part
}
~~~

When a listener runs asynchronously, the publisher does not wait for the listener to finish. Completion order among asynchronous listeners is not guaranteed. You need to pay attention to thread pool management, shared data, and exception handling in background tasks.

Do not enable asynchronous execution just to make events seem faster. Use it when the business logic allows the listener to complete later and the publisher does not need an immediate result.

## 7. Application Event or Direct Method Call?

| Need | Appropriate Approach |
|---|---|
| A bean needs to invoke a specific operation and use its return value | Call the method directly via dependency injection. |
| An action needs to notify multiple independent beans | Publish an application event. |
| The publisher needs to know whether the listener succeeded or returned data | Use a direct call or an API with an explicit result. |
| Handling background tasks within the same application | You can combine events with @Async if asynchronous processing is acceptable. |
| Sending a message to another service or process | Use an appropriate messaging mechanism such as a message broker; an application event within a context does not automatically become an inter-process message. |

Application Events are an in-memory communication mechanism within a Spring application. Events are not automatically persisted durably and are not automatically sent to another JVM or service. If the application stops before a listener finishes processing, this mechanism does not provide a queue to replay events.

## 8. Common Issues and How to Fix Them

| Symptom | Common Cause | How to Fix |
|---|---|---|
| Listener does not run | Listener is not registered as a bean or lies outside the component scan scope. | Ensure the listener has @Component or is declared with @Bean in the right ApplicationContext. |
| Listener does not receive the event | The listener parameter type does not match the published event type. | Check the event class in publishEvent and the parameter type of the @EventListener method. |
| Publisher does not trigger the listener | Publisher or listener was created manually with new instead of being managed by Spring. | Use constructor injection and let Spring create the beans. |
| The publishEvent method runs slowly | A synchronous listener performs I/O or heavy work. | Optimize the listener or consider @Async when business logic allows. |
| An error in a listener causes the event-publishing operation to fail | A synchronous listener throws an exception and the error propagates back to the publisher. | Define an error-handling policy, log the error, and handle exceptions according to business needs. |
| Asynchronous processing results are not in the expected order | Listeners run on different threads. | Do not depend on completion order; use serialization or dedicated orchestration if business logic requires it. |

## 9. Event Design Principles

- Name events after an occurrence that happened, such as PaymentCompletedEvent.
- Include only the data listeners actually need in the event; usually prefer an identifier and an immutable data snapshot.
- Use a record or a class with getters only to limit data mutation after publishing.
- Keep the publisher independent of listeners; do not turn events into a roundabout way of calling functions.
- Do not use application events in place of a request-response API when the publisher needs an immediate result.
- For listeners that need to run after a transaction commits, consider @TransactionalEventListener and choose the appropriate phase. This listener requires the corresponding transaction context; it is not a substitute for understanding the transaction lifecycle.
- If reliable communication across multiple processes is needed, choose a message broker or a storage and message delivery mechanism with appropriate durability.

## 10. Self-Check

1. Why does PaymentService inject ApplicationEventPublisher instead of injecting ReceiptListener?
2. If an AuditListener receiving PaymentCompletedEvent is added, does PaymentService need to change? Why?
3. Why does ReceiptListener's log line appear before log line 3 in the synchronous example?
4. When is @Async useful and what changes regarding completion order?
5. Why are application events within the same ApplicationContext unsuitable for sending messages to a service running in another process?

**Key Takeaway:** An event-publishing bean describes an occurrence with an event object and sends it through ApplicationEventPublisher. Listener beans in the same ApplicationContext receive the event via @EventListener. The default mechanism is synchronous; it can be extended to asynchronous execution when business logic allows.
