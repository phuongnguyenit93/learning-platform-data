# Distinguishing ApplicationContext Events from Inter-Process Messages

## Objectives

After this lesson, you will be able to:

- Explain how Spring ApplicationContext events are published and received.
- Distinguish internal events within an application from messages crossing process boundaries.
- Choose the right mechanism for communication between beans, between services, and for background processing.
- Recognize the impact of transactions, asynchronicity, retries, duplicates, and message durability.
- Design event contracts stable enough for multiple services to share.

## 1. Two Mechanisms Solving Two Different Scopes

**ApplicationContext event** is a notification mechanism between Spring-managed beans within the same ApplicationContext. One bean publishes an event via ApplicationEventPublisher; Spring dispatches the event to matching listeners in the context. This mechanism is based on the Observer pattern and primarily serves internal communication inside a single application.

**Inter-process message** is data sent from one process or service to another across a communication boundary. That boundary is typically a message broker or middleware such as RabbitMQ, Kafka, or a JMS broker; it can also be another communication protocol. The two sides may run in different JVMs, containers, or hosts and have independent deployment lifecycles.

The core difference lies in the communication boundary:

~~~text
Internal event:
OrderService
    -> ApplicationEventPublisher
    -> ApplicationEventMulticaster
    -> @EventListener within the same ApplicationContext

Inter-process message:
Service A
    -> client sends message
    -> broker / transport over network
    -> queue or topic
    -> consumer in Service B
~~~

A business event such as OrderPlaced can be published internally via ApplicationContext or packaged into a message sent to another service. The event's name does not determine its transport scope; the send and receive mechanism determines that scope.

Also distinguish **event** from **command**:

- An event describes something that has occurred, usually named in the past tense: OrderPlaced, PaymentReceived.
- A command asks a party to perform an action: PlaceOrder, CapturePayment.
- A message is the unit of data transmitted. A message can carry an event or a command.

## 2. How Do Spring ApplicationContext Events Work?

Spring provides the ApplicationEventPublisher interface to publish events. A bean can receive this interface via dependency injection and call publishEvent(...). Since Spring Framework 4.2, the published object does not have to extend ApplicationEvent; a plain POJO or Java record can also be used as an event.

A listener bean can implement ApplicationListener<T> or declare a method with @EventListener. Spring registers listeners during bean creation and selects listeners based on event type. You can use @Order to control the invocation order of synchronous listeners.

Key characteristics to remember:

1. **Scope:** listeners belonging to the ApplicationContext receive events published in that context. If an application uses parent-child contexts, events published in a child context are propagated up to the parent context; events in the parent context are not automatically broadcast down to child contexts. This is still communication within an application's context hierarchy, not transmission over a network.
2. **Synchronous by default:** SimpleApplicationEventMulticaster invokes listeners on the event-publishing thread by default. Therefore, publishEvent(...) normally waits for synchronous listeners to complete before returning.
3. **Error propagation:** in default synchronous mode, an exception from a listener can propagate back to the publisher and stop the current multicast iteration. You can configure an ErrorHandler to handle errors according to a custom policy.
4. **Transactions:** a synchronous listener runs on the same execution thread and can participate in the publisher's active transaction. This is a useful trait, yet it also means a slow listener can prolong the transaction.
5. **No durable storage:** ApplicationContext does not write events to a database or broker by itself. If the process stops before a listener finishes, the event has no durable queue from which to be replayed.

### Complete Example: Publishing an Internal Event

This example uses Java 17 and Spring Framework 6.2.9. OrderService publishes a record after simulating order intake. AuditListener receives the event within the same ApplicationContext.

Directory structure:

~~~text
application-event-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventDemo.java
~~~

File pom.xml:

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
            <version>6.2.9</version>
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

File src/main/java/demo/ApplicationEventDemo.java:

~~~java
package demo;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ApplicationEventDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(OrderService.class)
                    .placeOrder("ORD-1001", new BigDecimal("125.00"));
        }
    }
}

@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    OrderService orderService(ApplicationEventPublisher publisher) {
        return new OrderService(publisher);
    }

    @Bean
    AuditListener auditListener() {
        return new AuditListener();
    }
}

record OrderPlacedEvent(String orderId, BigDecimal total) {}

class OrderService {

    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void placeOrder(String orderId, BigDecimal total) {
        System.out.println("Order accepted: " + orderId);
        publisher.publishEvent(new OrderPlacedEvent(orderId, total));
    }
}

class AuditListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        System.out.printf(
                "Audit: order=%s, total=%s%n",
                event.orderId(),
                event.total()
        );
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.ApplicationEventDemo
~~~

Stdout output:

~~~text
Order accepted: ORD-1001
Audit: order=ORD-1001, total=125.00
~~~

The two lines appear in this order because listeners run synchronously on the publishing thread by default. The example only simulates a business operation and does not connect to a database. Notice that OrderService depends only on ApplicationEventPublisher; it does not need to know AuditListener exists.

## 3. Inter-Process Messages in the Spring Ecosystem

When two processes need to exchange data, it must travel over a transport accessible to both sides. In a message-driven architecture, a broker typically handles routing and retaining messages per configuration.

A typical RabbitMQ flow:

1. Service A constructs a payload following an agreed contract.
2. RabbitTemplate sends the payload to an exchange with a routing key.
3. The exchange routes the message to the matching queue.
4. The broker retains the message per queue policy and storage configuration.
5. Service B receives the message via a listener container and a `@RabbitListener` method.
6. The consumer processes it, and the message is then acknowledged or handled per configured retry/reject policies.

### Example Sending and Receiving with Spring AMQP

These are two illustrative snippets, not a complete RabbitMQ application. A real application needs the Spring AMQP dependency, ConnectionFactory, RabbitTemplate, exchange, queue, binding, and listener container. Infrastructure can be declared with Spring AMQP or via Spring Boot auto-configuration.

Sending side:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

class OrderEventPublisher {

    private final RabbitTemplate rabbitTemplate;

    OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishOrderPlaced() {
        String payload = """
                {"eventId":"evt-1001","eventType":"OrderPlaced",
                 "schemaVersion":1,"orderId":"ORD-1001","total":125.00}
                """;

        rabbitTemplate.convertAndSend(
                "orders.exchange",
                "order.placed",
                payload
        );
    }
}
~~~

Receiving side:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {

    @RabbitListener(queues = "order-events")
    public void onMessage(String payload) {
        System.out.println("Received order event: " + payload);
    }
}
~~~

In this example, the exchange orders.exchange must be bound to the queue order-events with routing key order.placed. A String payload is used to illustrate the contract carried over the transport; in real systems, producers and consumers must agree on format, encoding, schema, and compatibility rules.

Common choices:

- **Spring AMQP / RabbitMQ:** RabbitTemplate sends messages to an exchange; @RabbitListener receives messages from a queue. Well suited for flexible routing, queues, and background processing.
- **Spring for Apache Kafka:** KafkaTemplate sends records to a topic; consumers read by partition and manage offsets. Useful for event streams, retention, and replayability.
- **Spring JMS:** JmsTemplate sends to a JMS provider's queue or topic; a listener container receives messages. Suits systems standardized on JMS.
- **Spring Integration:** provides Message, MessageChannel, adapters, and gateways to connect systems. Distinguish abstractions from transports: an in-memory MessageChannel does not turn into inter-process communication on its own. An actual adapter or transport such as JMS, Kafka, AMQP, MQTT, etc. is required.

Spring Framework does not turn ApplicationEventPublisher into a message broker by itself. If a listener receives an ApplicationContext event and forwards it using RabbitTemplate or KafkaTemplate, that listener itself acts as a bridge from internal events to the messaging system.

## 4. Direct Comparison

| Criterion | ApplicationContext event | Inter-process message |
|---|---|---|
| Boundary | Beans within the same ApplicationContext or related context hierarchy | Across processes/services over a transport |
| Publisher | ApplicationEventPublisher | RabbitTemplate, KafkaTemplate, JmsTemplate, or corresponding client |
| Receiver | @EventListener or ApplicationListener | @RabbitListener, Kafka listener, JMS listener, etc. |
| Transport | Spring invokes listeners inside the app | Network, broker, or middleware |
| Payload | Can be a Java object or record in the same app | Contract needing serialize/deserialize, typically JSON, Avro, Protobuf, or an agreed format |
| Latency | Usually low because there is no network hop | Adds network and broker overhead; can be processed asynchronously |
| Storage | No durable queue by default | Can persist durably if broker and messages are configured accordingly |
| When consumer fails | Synchronous listener can propagate errors back to publisher; async needs dedicated handling | Broker can redeliver, retry, or route to DLQ depending on configuration |
| Duplicates | No broker redelivery; app logic can still emit events multiple times | Redelivery or retries can produce duplicates; consumers need idempotency |
| Ordering | Synchronous listener order can be controlled with @Order | Depends on queues, partitions, consumer count, and broker config |
| Transactions | Synchronous listeners can run in publisher's transaction | Transactions across database and broker require explicit design; not atomic by default |
| Scaling | Tied to the lifecycle and resources of the app hosting the context | Consumers can deploy, scale, and restart independently |
| Best suited for | Internal coordination among beans | Service integration, background work, buffering, and cross-system exchange |

Do not interpret this table as an absolute rule on performance or reliability. Messaging is neither durable nor exactly-once by default; results depend on the broker, topology, acknowledgements, persistence, retries, and how consumers update data.

## 5. Synchronous, Asynchronous, and Transactions

### @Async Does Not Mean Inter-Process

You can place `@Async` on an `@EventListener` method and enable asynchronous execution with `@EnableAsync`. The listener can then run on a different executor thread. However:

- The listener still belongs to the current application and ApplicationContext.
- There is no broker, durable queue, or automatic replay capability.
- Exceptions from an async listener do not propagate back to the publisher as in synchronous calls; configure an AsyncUncaughtExceptionHandler or an appropriate error-logging mechanism.
- ThreadLocal, logging context, and transaction context are not automatically propagated to another thread.
- Do not assume async listeners complete in the order they were published.

If the goal is merely to avoid blocking the calling thread, async listeners can help. If you need inter-process communication or persistent storage for reprocessing, you must use an appropriate transport.

### Use @TransactionalEventListener When Outcomes Depend on Transactions

A standard listener can run immediately at the time of publishEvent(...), even before the business transaction commits. If a listener should react only after the transaction succeeds, use @TransactionalEventListener:

~~~java
@Component
class OrderSearchIndexer {

    @TransactionalEventListener
    public void afterOrderCommitted(OrderPlacedEvent event) {
        // Update index after transaction commits.
    }
}
~~~

By default, the listener binds to the AFTER_COMMIT phase. You can choose BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, or AFTER_COMPLETION via the phase attribute. If no transaction is active, the listener is not invoked by default; fallbackExecution = true changes that behavior and should only be enabled intentionally.

Important point: AFTER_COMMIT does not make an event durable. There is a window between when the database commits and when the listener finishes. If the process stops during that window, post-commit work can be lost.

### Transactional Outbox for Reliable Integration

When a transaction must both update a database and emit a message to a broker, performing the database write and the message send as two independent operations creates failure modes:

- The database commits successfully, but sending the message fails.
- The message is sent, but the database transaction rolls back or fails to commit as expected.
- The process crashes between the two operations.

Transactional Outbox bridges this gap by:

1. Within the same database transaction, updating business data and inserting a record into an outbox table.
2. Having a background publisher or CDC read outbox records and publish them to the broker.
3. Recording sent status or advancing a checkpoint; errors can be retried.
4. Having consumers process idempotently using eventId so duplicates do not cause repeated business effects.

Outbox does not automatically guarantee end-to-end exactly-once behavior across all components. It ensures the intent to emit a message is persisted atomically with the business transaction; publishers and consumers still must handle retries, duplicates, and error states.

## 6. Durability, Acknowledgements, Retries, and Duplicates

With a broker, configure explicitly rather than assuming messages will always survive:

- **Durability:** queues/topics and messages need appropriate persistence settings; actual durability also depends on broker type, replication, and retention policy.
- **Publisher confirmation:** producers need to know at what level the broker confirmed receipt. A send call not throwing an exception is not enough to conclude the message reached the right queue.
- **Consumer acknowledgement:** acknowledge only after processing reaches the desired state. Acknowledging too early can lose messages if the consumer stops before completing business side effects.
- **Retries:** bound attempt counts, configure backoff intervals, and distinguish transient errors from unrecoverable errors. Infinite retries can clog queues.
- **Dead-letter queue (DLQ):** move persistently failing messages aside for investigation and controlled replay.
- **Idempotency:** use an eventId or unique business key so re-processing a message does not create duplicate side effects.
- **Ordering:** rely on ordering only within the scope guaranteed by the broker. For example, Kafka preserves order within a single partition; multiple partitions or parallel consumers may finish out of emission order.
- **Schema evolution:** include schemaVersion, preserve backwards compatibility where possible, and avoid renaming or changing field semantics without a migration plan.

Never assume a system has end-to-end exactly-once semantics. A broker may provide certain delivery guarantees within a bounded scope, yet database updates, external API calls, and side effects can still repeat. Designing idempotent consumers is a practical requirement in most systems.

## 7. Which Mechanism Should You Choose?

| Need | Selection Guidance |
|---|---|
| One bean needs to notify a few other beans in the same app | ApplicationContext event |
| Want to decouple listeners from publisher while accepting same-app lifecycle and failure behavior | ApplicationContext event; weigh synchronous vs async listeners |
| Only need to run background work within the same app | Executor, @Async, or async event listener |
| Two independently deployed services need to communicate | Message broker or inter-process protocol |
| Consumer may go offline, needing buffering, retries, or replay | Broker with configured persistence, acknowledgements, and retention |
| Multiple independent consumers need the same event | Pub/sub via an appropriate topic or exchange |
| Need to ask a service to act and wait for an immediate result | Call the service directly via an API like HTTP/gRPC; use request-reply messaging when asynchronicity fits |
| Database updates and integration event publishing must stay consistent | Transactional Outbox or equivalent CDC solution |

A practical rule of thumb: start with ApplicationContext events when the boundary is strictly between beans inside the same application. Move to messaging when consumers need independent processes, deployments, fault isolation, buffering, or scaling.

## 8. Common Design Mistakes

1. **Assuming @Async creates durable messages.** It only offloads work to an executor; when the process stops, queued tasks are not automatically recovered.
2. **Using ApplicationContext events to call a remote service.** The event publisher knows nothing of network addresses, retries, authentication, or target service contracts. You need a client or bridge with an explicit transport.
3. **Putting internal entities into inter-process contracts.** Two services may have different code versions and data models. Use independent DTO/event contracts with schemas and versions.
4. **Putting heavy processing inside synchronous listeners.** The publisher is blocked and transactions may be held open too long. Move to background tasks or a broker if appropriate.
5. **Assuming @TransactionalEventListener guarantees message delivery.** It only aligns listener execution timing with the transaction; it does not persist events durably.
6. **Retrying without idempotency.** A redelivered message can create duplicate orders, charges, or emails.
7. **Not monitoring failed messages.** You need logs with eventId/correlationId, metrics, retry policies, and a DLQ to diagnose root causes.
8. **Changing message contracts arbitrarily.** Producers and consumers may deploy at different times; enforce schema compatibility rules and contract testing.

## 9. Pre-Implementation Checklist

- [ ] Identify whether consumers live in the same ApplicationContext or in independent processes.
- [ ] Clarify whether the event announces a past fact or is a command requesting an action.
- [ ] Choose synchronous, async executor, or broker based on real requirements.
- [ ] Define behavior when a listener or consumer fails.
- [ ] If using a broker, configure durability, acknowledgements, retries, DLQ, and publisher confirmations appropriately.
- [ ] Assign eventId/correlationId and design idempotent consumers.
- [ ] Identify transaction requirements; consider Outbox when synchronizing database writes with messages.
- [ ] Define schema, version, and compatibility policies.
- [ ] Ensure logging, metrics, and alerts for failed or backlogged messages.

## 10. Conclusion

ApplicationContext events are Spring's internal Observer mechanism, convenient for reducing direct coupling among beans inside the same application. Inter-process messages communicate across a transport, suited when components run and deploy independently. @Async does not replace a broker; @TransactionalEventListener does not replace an outbox; and a broker does not automatically deliver end-to-end exactly-once business effects. Choose based on process boundaries, transaction requirements, durability, retry capabilities, and the desired independence between producers and consumers.

## Official References

- [Spring Framework Reference: Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html) — ApplicationEventPublisher, ApplicationListener, @EventListener, and multicasting.
- [Spring Framework Reference: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — @TransactionalEventListener and transaction phases.
- [Spring Framework Javadoc: SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html) — executor, synchronous execution, and ErrorHandler.
- [Spring AMQP Reference: AmqpTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html) — sending messages, retries, publisher confirms, and returns.
- [Spring Integration Reference: Core Messaging](https://docs.spring.io/spring-integration/reference/core.html) — Message, MessageChannel, adapters, and enterprise integration patterns.
- [Spring Integration Reference: JMS Support](https://docs.spring.io/spring-integration/reference/jms.html) — adapters and gateways for JMS communication.
