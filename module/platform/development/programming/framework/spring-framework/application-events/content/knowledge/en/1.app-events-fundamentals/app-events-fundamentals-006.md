# Limitations of Internal Events Compared to a Message Broker

Spring Framework Application Events are an in-application notification mechanism within a Spring application. One component publishes an event via `ApplicationEventPublisher`, while registered listeners in the application receive and handle that event. This mechanism helps components within the same application reduce direct dependencies on one another.

However, **an Application Event is an internal notification within the application process**, not a distributed messaging system. It does not automatically provide durable queues, acknowledgements, redelivery, history storage, or event distribution to another process. A message broker such as RabbitMQ or Apache Kafka is designed to handle those boundaries.

## 1. Within What Scope Do Internal Events Operate?

The basic flow consists of three steps:

1. The publishing component calls `ApplicationEventPublisher.publishEvent(event)`.
2. Spring forwards the event to `ApplicationEventMulticaster`.
3. The multicaster finds listeners matching the event type and invokes them.

Since Spring Framework 4.2, an event can be a plain Java object; extending `ApplicationEvent` is not required. Listeners can use `@EventListener` or implement `ApplicationListener`.

In the default configuration, `SimpleApplicationEventMulticaster` invokes listeners synchronously on the event-publishing thread if a `TaskExecutor` is not configured. Therefore, when calling `publishEvent`, the publishing component usually has to wait for synchronous listeners to finish running before moving on.

This is useful when components reside in the same application and need fast, simple notifications. For example: after creating an order, the order module publishes `OrderCreatedEvent`; the audit module or statistics module in the same application can listen without the order module having to call each of those modules directly.

This scope is also an important limitation: the listener must exist in the ApplicationContext handling the event. Another Spring instance, another process, or another service will not automatically receive that event.

## 2. Comparing Application Events and Message Brokers

| Aspect | Spring Application Event | Message Broker |
|---|---|---|
| Scope | Within the publishing Spring ApplicationContext/process | Can transmit across multiple processes, hosts, and services |
| Storage | No durable queue by default; events are passed in memory | Can persist messages/topics/queues according to broker configuration |
| Delivery acknowledgement | No acknowledgement protocol between publisher and listener | Has acknowledgement/offset mechanisms depending on the broker |
| Retry on failure | No built-in retry or dead-letter queue by default | Can configure retries, redelivery, and dead-letter |
| History replay | No event log to re-read by default | Kafka has retention and offsets to replay; other brokers have their own mechanisms |
| Multiple instances | An event published on instance A does not automatically reach a listener existing only on instance B | Consumers across multiple instances can participate in receiving messages |
| Load smoothing | Synchronous listeners can lengthen requests; an executor has its own limits | Queues/topics can absorb backlogs and decouple producer/consumer speeds |
| Operations | Fewer infrastructure components, easy to trace in a debugger/application logs | Requires operating the broker, connections, permissions, monitoring, and configuration |
| Data contract | Often shares Java classes within the same codebase | Requires managing schemas, payload versions, and compatibility across services |

A broker provides controlled message storage and transmission capabilities, but does not automatically guarantee end-to-end exactly-once processing for every system. Durability, ordering, delivery count, replayability, and duplicate handling depend on the broker type, producer/consumer configuration, replication, acknowledgement, retention, and how the application confirms processing.

For example, Kafka stores records in a topic according to a retention period and consumers read by offset; ordering is guaranteed within a partition. RabbitMQ routes messages through exchanges to queues; acknowledgements, durable queues, persistent messages, requeuing, and dead-lettering must be configured appropriately. Do not assume that merely installing a broker guarantees every message is processed exactly once.

## 3. Practical Limitations of Internal Events

### 3.1. Not Transmitted Across Instances

Suppose an application is deployed across three instances behind a load balancer:

- An order creation request is handled on instance A.
- Instance A publishes `OrderCreatedEvent`.
- A listener located in A's ApplicationContext can receive the event.
- A listener registered only in instance B or C will not receive the event from A.

Each instance has its own memory and ApplicationContext. Spring Application Events are not a broadcast mechanism across replicas. If multiple services or multiple independent instances need to receive the same message, a shared communication channel is required, typically a message broker or an equivalent distributed messaging mechanism.

### 3.2. No Durable Storage or Replay

Internal events are not written to a durable queue or log by default. If the process stops abruptly, events waiting in memory may be lost. After restarting, the application has no default history to know which events were not yet processed or to replay old events.

This differs from a broker configured to persist messages. A broker can retain messages or records for a defined period, allowing consumers to resume processing after a restart and supporting re-reading according to the broker's policy.

Therefore, you should not use Application Events as the sole place holding critical work that must be processed reliably, such as sending invoices, payments, syncing data with external systems, or sending mandatory notifications.

### 3.3. No Default Acknowledgement, Retry, or Dead-Letter

When a synchronous listener is invoked, the publisher does not receive an independent acknowledgement indicating that the message has been persisted and durably processed by the consumer. Invoking a listener is just an in-application call.

If a listener throws an exception, with the default multicaster configuration without an ErrorHandler, the exception can propagate back to the `publishEvent` call site. If the listener runs asynchronously, the error occurs on the worker thread and does not propagate back to the publisher like a synchronous call. In either mode, Application Events do not automatically create a retry policy, retry count, backoff interval, or dead-letter queue.

If the business logic requires retries, you must design your own mechanism to persist job state, retry schedule, retry limits, final error handling, and idempotency. When those requirements become inter-service communication needs, a broker is usually more suitable.

### 3.4. Synchronous Listeners Can Slow Down the Main Flow

With the default configuration, listeners run on the event-publishing thread. If a listener calls an external API, runs slow queries, or performs heavy tasks, the duration of the event-publishing operation increases accordingly.

For example, an order creation request publishes an event and a listener sends an email on the same thread. The request completes only after the email-sending operation finishes. If the email service is slow or times out, the request experience is also affected.

You can use `@Async` or configure an executor on the multicaster to run listeners on another thread. However, asynchronous execution only changes how execution happens; it does not turn an in-memory event into a durable message and does not automatically add retries, acknowledgements, or replay capability.

### 3.5. Does Not Automatically Solve Transaction Boundaries

An event published while the database transaction has not yet committed can cause a listener to run before data becomes durable. A listener querying data may not yet see the changes just made, or the listener may produce an external side effect and then the original transaction rolls back.

For example:

1. The service writes an order inside a transaction.
2. The service publishes `OrderCreatedEvent`.
3. The listener sends a request to the shipping system.
4. The transaction saving the order rolls back.

The shipping system has already received the request while the order was not committed. External side effects cannot automatically roll back along with the database transaction.

Spring provides `@TransactionalEventListener` to tie listener invocation timing to the current transaction. The default phase is `AFTER_COMMIT`; other phases include `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. If there is no active transaction, a transactional listener is not invoked by default, unless `fallbackExecution` is enabled.

This mechanism helps pick the right processing timing within a Spring application, but **does not create a durable queue**. If the process stops after the database commits yet before the listener finishes, work can still be missed. When a listener needs to write new data after commit, consider an appropriate separate transaction, such as `REQUIRES_NEW`, rather than assuming the old transaction can still commit additional changes.

## 4. Example: Publishing Events Within the Same Application

The following example uses Java 17+ and Spring Boot. The classes are placed together in one file to clarify the flow; in a real project each class can be separated into its own file. The application creates a simulated order and publishes an event for a listener to print a notification.

~~~java
package com.example.events;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService orderService) {
        return args -> orderService.create("order-1001");
    }
}

record OrderCreatedEvent(String orderId) {}

@Service
class OrderService {
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void create(String orderId) {
        // Simulate order creation operation.
        publisher.publishEvent(new OrderCreatedEvent(orderId));
        System.out.println("Order service: " + orderId);
    }
}

@Component
class OrderNotificationListener {
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Notification listener: " + event.orderId());
    }
}
~~~

When running the application, the two output lines generated by the example are:

~~~text
Notification listener: order-1001
Order service: order-1001
~~~

The listener runs before the print line after `publishEvent` because the event is dispatched synchronously. Spring Boot startup logs are not listed here. The example only illustrates passing notifications within the same application; it has no database, broker, retries, or message persistence.

The run command depends on how the Spring Boot project was created. With the project's Gradle Wrapper, you can run the application using:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

## 5. Binding Listeners to Commit Timing

If an event reflects a data change, it is often necessary to avoid processing before the transaction commits. For example, the following listener runs only after the transaction succeeds:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderAuditListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        System.out.println("Committed order: " + event.orderId());
    }
}
~~~

Service publishing the event in a transactional method:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TransactionalOrderService {
    private final ApplicationEventPublisher publisher;

    TransactionalOrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Transactional
    public void create(String orderId) {
        // Save the order using a repository here.
        publisher.publishEvent(new OrderCreatedEvent(orderId));
    }
}
~~~

Once the transaction commits, the listener in the `AFTER_COMMIT` phase is invoked. If the transaction rolls back, this listener does not run. For the example to work in a real application, you need to configure a transaction manager and use a transactional method invoked through a Spring proxy.

Two guarantees must be distinguished:

- `AFTER_COMMIT` guarantees the listener is triggered only after the transaction commits successfully during normal execution flow.
- It does not guarantee that the event has been written to durable storage or will be replayed if the process crashes at that exact moment.

If losing a post-commit notification is unacceptable, using `@TransactionalEventListener` alone is not enough.

## 6. Asynchronous Execution Is Not Equivalent to a Message Broker

Listeners can be run on an executor using `@Async`:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
class AsyncOrderListener {
    @Async
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        // Perform a task that may take time.
        System.out.println("Async notification: " + event.orderId());
    }
}
~~~

Enable async processing in Spring configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
class AsyncConfiguration {}
~~~

When using this approach, keep in mind:

- You must configure an executor suited to the load, thread count, queue capacity, and task rejection policy.
- Exceptions from an asynchronous listener are not returned to the thread that called `publishEvent`; configure separate logging and error handling, such as `AsyncUncaughtExceptionHandler` for methods returning `void`.
- If the process stops while tasks are still sitting in the executor's queue, tasks may be lost.
- Do not assume ThreadLocals, security context, or the publishing thread's transaction context are automatically present in the worker thread; explicit context propagation mechanisms are needed when business logic requires them.
- `@Async` relies on Spring's proxy mechanism; internal calls between methods within the same object may not go through the proxy as expected.

An executor separates processing time from the event-publishing thread, yet the executor's queue still belongs to the process. It does not have the persistence and recovery characteristics of a durably configured broker.

## 7. When Should You Use a Message Broker?

A message broker is appropriate when the system needs one or more of the following characteristics:

- Producers and consumers run in independent processes, services, or deployment groups.
- Consumers can pause temporarily or lose connection while messages still need to be retained for later processing.
- Retries, acknowledgements, dead-lettering, backlog monitoring, or consumption rate throttling are needed.
- Multiple independent consumers need to receive the same event type.
- History needs to be retained for a period of time or data needs to be replayed to rebuild state.
- Scaling the number of consumers is needed without forcing producers to know the topology of receiving services.

Two common options:

**RabbitMQ** fits a model of routing messages through exchanges to queues. You can use acknowledgements to confirm processing, configure durable queues and persistent messages, retries/requeueing, or dead-letter exchanges. You must design routing keys, exchange types, queue limits, and redelivery policies.

**Apache Kafka** fits event streams stored in topics with retention. Consumers read records by offset; consumer groups distribute load across consumers and can re-read from older offsets while data remains within retention. Ordering is guaranteed within each partition, not a global order across all partitions.

Brokers increase operational overhead: deploying and monitoring infrastructure, configuring security, handling network errors, managing schemas, monitoring lag/backlogs, and designing idempotent consumers. Do not add a broker just to replace a call between two classes in the same application.

## 8. The Dual-Write Problem and Transactional Outbox

A common mistake when moving to a broker is writing to the database and publishing a message as two independent operations:

1. Write the order to the database.
2. Publish `OrderCreated` to the broker.

If the database commits successfully but publishing fails, the data exists yet consumers never receive the event. If publishing succeeds yet the database rolls back, consumers receive an event describing nonexistent data. This is the dual-write problem.

Transactional Outbox solves this by writing business data and an outbox record within the same database transaction:

1. The service writes the order.
2. The service writes the event to be published into an outbox table.
3. Both changes commit or roll back together.
4. A relay reads the outbox and publishes messages to the broker.
5. Once publication is confirmed according to the chosen policy, the relay marks the record as sent or updates the corresponding status.

Outbox avoids losing the link between the business commit and the intent to publish an event. However, the relay may publish duplicates if the broker already received the message before the relay could record the sent status. Therefore, consumers should still be idempotent, using an event ID or business key to identify and skip duplicate processing.

Outbox is an architectural pattern complementing a broker; it is not an automatic feature of Spring Application Events. You can use an Application Event to wake up the relay within the same process, yet the outbox record itself is the durable source of data that must be polled/recovered.

## 9. Selection Criteria

| Scenario | Appropriate Direction |
|---|---|
| Modules in a modular monolith need to notify each other | Spring Application Event |
| Listener only updates a cache or performs an auxiliary task where loss is acceptable | Application Event, optionally combined with async |
| Listener needs to run after transaction commit while remaining in the same application | `@TransactionalEventListener` |
| Need communication across multiple microservices | Message broker or an appropriate inter-service protocol |
| Need to retain work when a consumer pauses or a process restarts | Broker with appropriate persistence/acknowledgement configuration |
| Need retries, dead-letter, backlog, and multiple independent consumers | Message broker |
| Need to guarantee event-publishing intent accompanies the business transaction | Transactional Outbox combined with a broker |
| Only want to reduce coupling between two classes in the same application | Application Event is usually sufficient |

A practical way to decide:

1. Determine whether the event needs to cross process/service boundaries.
2. Determine whether losing events when the application stops abruptly is acceptable.
3. Determine whether retries, replay, acknowledgements, or dead-lettering are needed.
4. Determine whether load needs to be absorbed by a backlog and independently scaled consumers.
5. If the requirements above do not exist and events only serve internal modules, starting with Spring Application Events is usually simpler.
6. When reliability or distribution requirements grow, design a broker and outbox based on specific delivery requirements.

## 10. Common Misconceptions

- **"Having `@Async` means the event is already in a durable queue."** False. Executors usually keep tasks in the process's memory.
- **"Using `@TransactionalEventListener(AFTER_COMMIT)` means events cannot be lost."** False. It controls when the listener is invoked, not persisting events for crash recovery.
- **"The publisher calling `publishEvent` successfully means every listener's business work is complete."** It can only mean that the dispatch call took place under the current execution mode; there is no durable acknowledgement across all listeners.
- **"Application Events automatically broadcast to every replica."** False. Each ApplicationContext is a separate scope.
- **"A broker always delivers exactly once."** False. You need to understand the delivery semantics, configuration, and duplicate handling of each system.
- **"Simply using a broker eliminates the need for idempotency."** False. Retries and redelivery can cause a consumer to receive the same message multiple times.

## 11. Pre-Selection Checklist

- [ ] Does the event only serve modules within the same ApplicationContext?
- [ ] Is it acceptable for listeners to run on the event-publishing thread or the application's executor?
- [ ] Is the lack of default persistence and replay acceptable?
- [ ] If a listener fails, does the application have a proper way to log and handle it?
- [ ] If the event is tied to a transaction, has the listener execution timing been determined?
- [ ] If durable delivery is needed, do the broker and acknowledgement/retention configuration meet the requirements?
- [ ] Does the consumer safely handle receiving duplicate messages?
- [ ] If writing to a database and publishing to a broker, has Transactional Outbox been considered?

Spring Application Events are well-suited for loosely coupling components **within a single Spring application**. Message brokers are well-suited when messages need to cross process boundaries, live independently of the producer's lifecycle, or require explicit delivery and recovery capabilities. Choosing the mechanism according to the scope and guarantees required by the business keeps the system simple while still meeting the needed reliability.
