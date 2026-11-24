# Boundary Between Internal Events and External Integration in Spring Framework

## Objectives

In a Spring application, events help one component announce that a business occurrence has happened so other components can react without calling each component directly. However, **Spring Application Events is an in-process communication mechanism**. It does not automatically become a message that can be sent to another service, persisted durably, replayed, or guaranteed for delivery.

This lesson helps you decide which parts should use Spring internal events, which parts need an external integration contract, and how to bridge those two boundaries without coupling your domain to Kafka, RabbitMQ, or HTTP.

After this lesson, you will be able to:

- Distinguish between domain events, internal application events, and integration events.
- Explain the lifecycle and delivery limitations of `ApplicationEventPublisher` and `@EventListener`.
- Choose the right timing for event handling when transactions are involved.
- Design adapters and transactional outboxes for reliable integration.
- Avoid leaking entities, internal data types, or infrastructure details into external contracts.

## 1. Three Concepts to Separate

### Domain Event

A domain event describes an occurrence that is meaningful in the business model: `OrderApproved`, `PaymentCaptured`, `CustomerAddressChanged`. It answers the question "what happened?" and is typically raised when an aggregate or domain service completes a valid state transition.

A domain event belongs to the domain's language. It may only be used within a single module, or be translated by an application service into an integration message. Not every domain event needs to be sent externally.

### Spring Internal Application Event

An application event is how a component within the same Spring ApplicationContext notifies other listeners. The publisher calls `ApplicationEventPublisher.publishEvent(...)`; Spring finds matching listeners and dispatches the event.

Since Spring Framework 4.2, an event can be a regular Java object; extending `ApplicationEvent` is not required. Thus, a record like `OrderApproved` can be published directly.

Application events are typically used to decouple internal reactions: updating projections within the same application, writing internal audit logs, refreshing caches, or triggering secondary processing steps. They are not a message broker and not an API contract between services.

### Integration Event

An integration event is a message published across a process or system boundary, for example via Kafka, RabbitMQ, a messaging platform, a webhook, or an HTTP API. It is a contract that another system can receive and interpret.

An integration event should be designed as exchange data: stable naming and meaning, versioned schema, event identifier, timestamp of occurrence, and the minimal fields consumers need. It should not depend on internal classes, ORM entities, or the publishing service's package structure.

| Criterion | Internal Application Event | Integration Event |
|---|---|---|
| Scope | Single process / Spring ApplicationContext | Across processes or systems |
| Mechanism | `ApplicationEventPublisher`, `@EventListener` | Broker, HTTP, webhook, or integration protocol |
| Contract | Can be internal Java types, evolving with the application | Schema should be stable and have a compatibility strategy |
| Durable persistence | Not automatically persisted | Depends on infrastructure; broker/outbox can store and replay |
| Delivery | No built-in durable/retry guarantees | Depends on broker and retry/ack design |
| Listener failure | Synchronous listener can fail the publish flow | Handled via adapter/broker retry, ack, and DLQ policies |
| Consumer | Beans within the same application | Consumers may belong to other services or organizations |

**Decision rule:** if the receiver is a bean in the same application and durable delivery is not required, an application event may fit. If the receiver is in another process, needs message persistence, retries after application restarts, replay, or an independent contract, use an external integration mechanism.

## 2. How Do Spring Application Events Work?

Basic flow:

1. A service performs a business action.
2. The service publishes an event object via `ApplicationEventPublisher`.
3. Spring's `ApplicationEventMulticaster` dispatches the event to listeners with compatible types.
4. Methods annotated with `@EventListener` process the event.

By default, `SimpleApplicationEventMulticaster` invokes listeners on the same thread publishing the event. Thus, synchronous listeners run directly inside the `publishEvent` call flow. If a listener throws an exception and it escapes, the publish call may fail and the exception propagates back to the publisher.

You can configure an executor for the multicaster or use `@Async` with `@EnableAsync` for asynchronous processing. In that case, the publisher does not wait for listeners to finish; exceptions from async listeners do not propagate back to the publisher as in the synchronous case. Appropriate logging, error handling, and executor configuration are required. **Asynchronous does not mean durable persistence:** an unexpected process termination can still lose pending in-memory work.

### Runnable Example with Java 17+

The example uses Spring Framework directly, without Spring Boot. Directory structure:

```text
spring-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventsDemo.java
```

**pom.xml**

```xml
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
            <version>6.2.8</version>
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
```

**src/main/java/demo/ApplicationEventsDemo.java**

```java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ApplicationEventsDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(OrderService.class).approve(42L);
        }
    }

    @Configuration
    static class AppConfig {

        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        AuditListener auditListener() {
            return new AuditListener();
        }
    }

    record OrderApproved(long orderId) {
    }

    static class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void approve(long orderId) {
            System.out.println("Order " + orderId + " approved");
            publisher.publishEvent(new OrderApproved(orderId));
        }
    }

    static class AuditListener {

        @EventListener
        void onOrderApproved(OrderApproved event) {
            System.out.println(
                    "Internal listener received OrderApproved: "
                            + event.orderId());
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Stdout:

```text
Order 42 approved
Internal listener received OrderApproved: 42
```

In the example, `OrderService` knows only `ApplicationEventPublisher`, not specific listeners. `AuditListener` receives the event via `@EventListener`. The event is a regular Java record and is dispatched synchronously under the default configuration.

The example demonstrates in-process dispatching; it does not produce a message on a broker and does not demonstrate durable delivery.

## 3. Placing Transaction Boundaries Properly

When a publisher runs inside a transaction, determine whether listeners must react before or after the transaction finishes.

A regular `@EventListener` is invoked immediately when the event is dispatched. If published inside a `@Transactional` method, a synchronous listener can run before commit time. If the transaction rolls back afterward, side effects already performed by the listener on other systems do not automatically roll back with the database transaction.

For listeners that depend on commit outcome, use `@TransactionalEventListener`:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class LocalProjectionListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void onOrderApproved(OrderApproved event) {
        // Runs only after the transaction containing the event commits successfully.
    }
}
```

This illustrative snippet requires the `spring-tx` dependency and a configured transaction manager in a real application.

Common phases:

- `BEFORE_COMMIT`: runs before the transaction commits.
- `AFTER_COMMIT`: runs after a successful commit; this is the default phase.
- `AFTER_ROLLBACK`: runs after a rollback.
- `AFTER_COMPLETION`: runs after the transaction completes, whether committed or rolled back.

By default, a transactional listener requires an active transaction at publish time. If there is no transaction, the listener will not be called. Only enable `fallbackExecution = true` when business logic genuinely accepts running even without a transaction.

`AFTER_COMMIT` prevents reacting as if data were committed while the transaction can still roll back. However, it **does not provide durable delivery guarantees**: the process can still stop after commit and before the side effect completes. Exceptions after commit also cannot undo an already-committed transaction. If a listener needs to write additional data via another transaction, explicitly define a new transaction, such as using `REQUIRES_NEW` propagation when appropriate.

## 4. Translating from Internal Events to Integration Events

Do not let domain models or business services depend directly on Kafka producers, RabbitMQ templates, or HTTP clients. Place the translation in an application/infrastructure adapter:

```text
Domain / Application service
        |
        | emits OrderApproved (business meaning)
        v
Internal application event
        |
        | adapter maps data
        v
Integration event OrderApprovedV1
        |
        v
Outbox / Broker / HTTP adapter
        |
        v
External system
```

The adapter is responsible for:

- Selecting data permitted to be published and mapping it to the integration schema.
- Assigning event ID, event type, version, and occurrence timestamp.
- Adding a correlation ID or causation ID when the business flow requires tracing.
- Translating infrastructure errors into retries, failure recording, or dead-letter handling per policy.
- Not exposing ORM entities, lazy proxies, internal details, or domain package structures.

An example integration contract might be:

```java
public record OrderApprovedV1(
        String eventId,
        long orderId,
        String occurredAt,
        String correlationId
) {
}
```

This is an example of an exchange schema. When serializing, choose a consistent format and time convention, such as ISO-8601 UTC for `occurredAt`. External consumers should depend only on fields published in the contract, not on the original Java class.

It is not necessary to emit every domain event externally. Publish only events that are meaningful to external consumers and have a clear contract owner. A domain event may serve internal processing only; an integration event may also be aggregated from multiple internal changes.

## 5. When Is a Transactional Outbox Needed?

Suppose a service both updates an order in the database and sends a message to a broker. There are two operations across two different systems:

1. Commit order data.
2. Publish a message to the broker.

If the database commit succeeds but the broker fails, the data has changed while consumers do not receive the message. If publishing happens first and the database rolls back, consumers may receive an event for a change that was never committed. This is the dual-write problem.

Transactional outbox solves this by writing the business change and an outbox record within the **same database transaction**:

```java
@Transactional
public void approveOrder(long orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();
    order.approve();

    outboxRepository.save(
            OutboxMessage.pending(
                    "OrderApproved",
                    "v1",
                    serialize(new OrderApprovedV1(
                            newEventId(),
                            order.getId(),
                            Instant.now().toString(),
                            currentCorrelationId()
                    ))
            )
    );
}
```

The snippet above is an architectural sketch; repositories, serializers, and ID generators must be implemented in a real application. The key point is that writing to the outbox and updating the order use the same transaction manager/database transaction.

A separate relay reads unsent outbox records, publishes them to the broker, and marks them sent after receiving proper acknowledgment. If the relay encounters an error, it can retry according to policy. Additional design considerations include:

- **Idempotency:** the relay or broker may deliver the same event multiple times; consumers use the event ID to detect and safely handle duplicates.
- **Bounded retries with backoff:** avoid tight retry loops when the broker is failing.
- **Dead-letter or intervention state:** retain messages that cannot be processed after a suitable number of attempts.
- **Operational observability:** monitor pending record age, retry counts, publish latency, and serialization errors.
- **Cleanup:** delete or archive records according to retention policies only after completion is confirmed.

An outbox typically provides at-least-once delivery rather than automatically guaranteeing end-to-end exactly-once delivery. Consumers still need idempotency. If using CDC to read the outbox, the CDC connector handles forwarding, while schema, duplicate handling, and operational observability still need to be designed.

You can use `@TransactionalEventListener(AFTER_COMMIT)` to trigger secondary processing after commit, but publishing directly to a broker from this listener still leaves a gap: the database has committed, yet the process stops before sending. Therefore, for critical integration messages that must not be lost, an outbox is the better choice.

## 6. Common Design Mistakes

| Practice | Risk | Resolution |
|---|---|---|
| Using `ApplicationEventPublisher` to send to another service | Events are dispatched only within the current process | Use a broker, HTTP, or webhook adapter |
| Assuming `@Async` equals durable | In-memory pending work can be lost when the process stops | Use an outbox or queue infrastructure with durable storage |
| Sending a JPA entity as an integration payload | Exposes persistence structure, lazy loading, excess data, and tight coupling | Map to a dedicated integration DTO/schema |
| Calling an external API directly inside a database transaction | Holds transactions open longer; network errors increase lock duration and create hard-to-recover states | Write to an outbox in the transaction and relay afterward |
| Using an `AFTER_COMMIT` listener as a retry mechanism | Commit has already finished; exceptions do not roll back data and do not automatically schedule retries | Persist delivery state and retry via outbox/broker |
| Letting consumers assume events arrive only once | Redelivery can create duplicate side effects | Use an event ID and idempotent handling |
| Sharing the same internal Java class across multiple services | Implementation changes can break consumers | Manage versioned integration schemas and compatibility rules |

Additional notes:

- `@Order` can order the invocation of synchronous listeners. With asynchronous processing, do not rely on completion order to guarantee business invariants.
- Listeners should perform a clear, observable, and independently testable task. Avoid creating long listener chains where the processing flow cannot be traced.
- Do not publish an event before a valid business state is established. Event names should describe something that happened (`OrderApproved`), not an ambiguous command (`ApproveOrder`).
- Do not put passwords, tokens, unnecessary personal data, or internal implementation details into integration events.
- If an event can be replayed, the payload must contain enough information for consumers to handle it without relying on transient in-memory state of the publisher.

## 7. Solution Selection Process

Answer the following questions in order:

1. **Where is the receiver?** If it is a bean in the same Spring ApplicationContext, consider an application event. If it is another process or system, an integration adapter is required.
2. **Is losing the event acceptable if the process stops?** If yes, internal best-effort secondary handling may suffice. If not, durable storage such as an outbox or suitable broker is needed.
3. **Does it need to wait for transaction commit?** If an internal listener must run only when commit succeeds, use `@TransactionalEventListener(AFTER_COMMIT)`. If an integration message must be guaranteed, write to an outbox in the same transaction.
4. **Who owns the schema?** For external consumers, define the owner, version, compatibility rules, and how unrecognized events are handled.
5. **Can the consumer tolerate duplicate delivery?** Design idempotency, retries, and dead-letter handling before going to production.

Decision examples:

- Refreshing an internal cache after configuration changes: an application event may fit.
- Writing an internal audit log synchronously in the same transaction: consider a synchronous listener or direct handling if it is a mandatory part of the business operation.
- Sending an email after an order commits: a transactional listener may fit if a separate retry policy is acceptable; if the send request must not be lost, persist a durable job/outbox record.
- Notifying an inventory system in another service that an order was approved: integration event via broker/API; if zero data loss is required, use an outbox.
- Refreshing a projection in the same application: application event or direct update depending on consistency needs and complexity.

## 8. Pre-Implementation Checklist

- [ ] The event name expresses a business occurrence that has happened.
- [ ] It is clearly decided whether the event is internal or an integration event.
- [ ] The payload contains only necessary data and does not expose internal entities.
- [ ] Synchronous, asynchronous, or post-commit execution is chosen based on business requirements.
- [ ] Behavior when a listener throws an exception and when a transaction rolls back is clearly understood.
- [ ] For critical integrations, outbox/broker, retries, idempotency, and error observability are in place.
- [ ] External schemas are versioned and have compatibility rules.
- [ ] Logs/traces are sufficient to correlate publisher, event, and consumer via a correlation ID.

## Conclusion

Spring Application Events is a tool for decoupling components within the same application. It keeps publishers unaware of specific listeners, but it does not provide a durable queue or an inter-service communication contract. Integration events belong at system boundaries and require managed schemas along with appropriate transport mechanisms. When you need to update a database and emit an external message reliably, write to an outbox in the same transaction and let a relay forward it.