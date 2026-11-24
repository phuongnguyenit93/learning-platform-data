# Responsibilities of the Application, Spring, and the Broker in JMS

In a system using **Jakarta Messaging (JMS)** with **Spring Framework**, three components participate in the same message flow while holding distinct responsibilities:

- **The application (producer/consumer)** decides *why* a message is sent, what business meaning it carries, what constitutes successful processing, and how to prevent duplicate side effects.
- **Spring JMS** provides the integration layer inside the Java process: managing JMS resources, data conversion, sending/receiving messages, invoking handler code, container configuration, acknowledgment, and JMS transaction boundaries.
- **The JMS provider/broker** implements the transport infrastructure: accepting, routing, storing, and distributing messages to queues/topics along with concrete operational policies.

**JMS is an API contract**, not the broker itself. With Spring Boot 3.x / Spring Framework 6.x, the API uses the **`jakarta.jms`** package. A broker such as Apache ActiveMQ Artemis is a *provider* implementing that contract; Spring does not replace the broker.

## 1. Flow Diagram and Ownership Boundaries

~~~text
SENDING APPLICATION           SPRING / JMS CLIENT                  BROKER
Create business event  ──>  JmsTemplate + converter  ──>  Queue or Topic
                                                         │
                                                         │ store/route/distribute
                                                         ▼
RECEIVING APPLICATION       SPRING / JMS CLIENT           JMS Consumer
Handle @JmsListener    <── container + converter    <── delivery from broker
        │
        ├── success: finish processing, commit/ack per configuration
        └── failure: exception/rollback; broker decides redelivery per policy
~~~

The diagram intentionally separates **business code** from **integration mechanics** and **where messages are stored/routed**. The broker does not intrinsically understand that an order was paid properly; nor does Spring decide which events are valid in the business domain.

| Task Needed | Application Owns | Spring JMS Assists With | Broker/Provider Owns |
| --- | --- | --- | --- |
| When an event is raised, event name, payload meaning | Designs and executes | Converts POJO/String to JMS Message when converter is configured | Only carries data and metadata |
| Where to send | Chooses target per business contract | `JmsTemplate`, `DestinationResolver`, `ConnectionFactory` | Provides actual queues/topics and distribution routes |
| Connections, sessions, consumers | Declares configuration and desired parameters | Creates/uses/closes or caches resources; listener container | Provides corresponding protocols and endpoints |
| Distribution to consumers | Chooses appropriate queue/topic and consumer group | Receives then invokes listener; manages concurrency | Queue competes among receivers; topic per subscription; stores and redelivers per policy |
| Data validity, permission to act | Validation, business authorization, duplicate prevention | Can invoke application-configured validation/conversion | Connection control, ACLs on destinations; does not check business rules |
| Ack/transactions | Chooses safety requirements and handles errors | Controls listener session/transaction | Records commit/ack, redelivery, and retention per configuration |
| Retries and persistently failing messages | Decides which errors retry, idempotency, poison message handling | Can rollback/throw, connection-recovery backoff; error handler integration | Redelivery delay policies, attempt counts, DLQ/expiry depending on provider |
| Observability and operations | Logs, traces, SLAs, business alerts | Exposes listener state and application errors | Queue depth, consumer count, disk, DLQ, connections, infrastructure alerts |

**Distinguish design responsibility from execution responsibility:** the application defines the requirements (e.g., needing safe handling on redelivery), while the broker executes distribution and storage mechanics under the guarantees provided by the specific provider and configuration.

## 2. Tracing a Message from Start to Finish

Suppose the order service emits an **OrderCreated** event to the **`orders.events`** queue for the fulfillment service to pick up.

1. **Producer application** completes the business decision and prepares a payload with a clear contract (order ID, event type, schema version, `eventId`). It determines when the message may be emitted, how to handle send errors, and whether a transactional outbox is needed to tie event creation to the DB transaction.
2. **Spring** receives the call via **`JmsTemplate.convertAndSend`** or **`send`**. If using a converter, Spring builds an appropriate JMS `Message`; through the provider's **`ConnectionFactory`**, it acquires JMS resources and dispatches the send command. Spring releases/manages resources according to configuration.
3. **Broker** accepts the message at the specified destination and applies access permissions, routing, persistence, and QoS per protocol/policy. The send call returning successfully **does not mean** the consumer code has executed successfully. When sending within a JMS transaction, message visibility also depends on that transaction's **commit**.
4. **Broker** selects an eligible consumer on the queue. If it is a topic, the broker distributes to eligible subscriptions; durable vs. non-durable subscribers have different rules when offline.
5. **Spring listener container** holds the consumer/session, retrieves the message, runs conversion, and invokes the method marked with **`@JmsListener`**. When the method finishes or throws an exception, the container applies the configured acknowledgment/transaction behavior.
6. **Consumer application** validates the payload, executes business operations, and records the **processed `eventId`** in a deduplicating way. If processing fails, it must surface the error per the listener contract (usually throwing an exception) so the JMS transaction can roll back.
7. **Broker** finalizes ack/commit, or returns the message to the delivery flow when rolled back and allowed by policy. A message failing repeatedly may be moved to a dead-letter queue (DLQ) **if configured on the broker**.

Point to remember: success at one layer does not prove success at subsequent layers. **Producer send succeeded ≠ consumer finished processing ≠ database update is safe.**

## 3. Specific Responsibilities of the Application

### 3.1. Event Contract

The application owns the schema and business semantics. A minimal payload should have a business identifier, a stable **`eventId`**, **`eventType`**, a schema version, and enough fields for the consumer to understand the event. Establish compatibility standards for adding fields, removing fields, or changing data types.

- **`eventId`** is the application-designed deduplication key; distinct from **`JMSMessageID`**, which the provider assigns to a specific JMS message.
- **`JMSCorrelationID`** is useful for request/reply correlation and tracing; if cross-system business correlation is needed, the application must proactively set and propagate appropriate metadata.
- JMS headers/properties serve routing and filtering; **message selectors do not read the body**, only headers/properties.
- Choose a testable, versionable format (typically JSON in a `TextMessage`). Do not rely by default on `ObjectMessage` to deserialize Java objects from untrusted sources.

### 3.2. Correctness and Idempotency

A consumer must tolerate **the same business event appearing again**. With standard queues and transactions, a failure between DB write and JMS acknowledgment can still cause message redelivery. Common strategy:

1. Attach a unique `eventId` to each event, stable across send attempts.
2. Create a **`processed_messages(event_id PRIMARY KEY, ...)`** table or equivalent unique constraint.
3. Within **the same DB transaction**, check/record `eventId` and apply the business mutation. Handle unique-key conflicts when multiple consumers compete; execute side effects only once.
4. Let the listener return normally only after business processing has committed. On any prior failure, throw an exception so the JMS transaction rolls back.

Pseudocode example (illustrates logic only; repository/service names are implemented by the application):

~~~java
@Transactional // Database transaction, does not automatically become a JMS transaction
public void applyOrderCreated(OrderCreated event) {
    if (processedMessages.existsByEventId(event.eventId())) {
        return; // Already processed: can acknowledge redelivered message
    }
    orders.markCreated(event.orderId());
    processedMessages.insert(event.eventId()); // UNIQUE/PRIMARY KEY
}
~~~

**Note:** the check-and-mark operation must be concurrency-safe; simply calling `exists` then `insert` in two steps without a unique constraint is insufficient. If producing side effects outside the DB (sending email, calling a payment API), you need an idempotency mechanism on the receiver side or an outbox for those side effects.

### 3.3. Intentional Error Handling

Distinguish **transient** errors (temporary DB connection loss), **permanent** errors (unrecognized schema, missing required fields), and **business** errors (non-existent order). The application decides which messages should be retried and which should be recorded/investigated. Never swallow an exception and treat it as success when a JMS rollback is expected.

## 4. Specific Responsibilities of Spring JMS

Spring reduces how much low-level JMS object management the application writes, but **does not create a broker**:

- **`ConnectionFactory`:** JMS entry point configured by the provider/Boot; contains endpoint, authentication, and connection settings, optionally paired with caching/pooling. In Spring Boot, the right JMS starter usually configures this bean and **`JmsTemplate`**.
- **`JmsTemplate`:** synchronous send and receive API, creating/using sessions/producers and managing resources. `convertAndSend` goes through a `MessageConverter`; `send` uses a `MessageCreator` to build messages directly.
- **`MessageConverter`:** converts between Java types and JMS `Message`. By default `String` becomes `TextMessage`; JSON POJOs require a converter and explicit schema conventions.
- **`@JmsListener`:** declares the receiving destination/method; Spring creates an endpoint and registers it in a **message listener container** to process asynchronously relative to the producer caller.
- **`DefaultMessageListenerContainer` / `DefaultJmsListenerContainerFactory`:** creates consumers, manages sessions, receive loops, concurrency, connection recovery, and ack/transaction boundaries per configuration. One listener instance can be invoked concurrently, so handler code must be thread-safe.
- **Transaction integration:** a JMS session can use local transactions; `JmsTransactionManager` manages transactions on a `ConnectionFactory`. For non-JMS resources like databases, a local JMS transaction **does not automatically** combine both resources into a single atomic transaction.
- **Exception handling:** with an appropriate container/session, an exception from the listener leads to rollback; error handling or logging must preserve the intended mechanism. Container recovery configuration differs from broker redelivery/poison-message policies.

Spring Boot can auto-configure certain beans/defaults, yet designers must still **explicitly review transacted sessions, converters, concurrency, queue/topic mode, destinations, timeouts, and credentials**. Do not assume an annotation alone guarantees all failure cases are handled safely.

## 5. Specific Responsibilities of the Broker and Scope of the JMS Standard

The broker implements infrastructure concerns: addresses/queues/topics, distribution to consumers, message storage, persistence, resource limits, ACLs/TLS, user administration, consumers/subscriptions, backpressure, expiry, and operations. **DLQ, backoff, redelivery limits, and dead-letter address names** are typically provider/broker policies rather than a universal algorithm implemented by Spring across every JMS provider.

| Concept | Meaning and Responsible Party |
| --- | --- |
| **Queue** | A message is delivered to **one** consumer in the queue's consumer group (may be redelivered after failure). The application chooses the work-queue model; the broker distributes. |
| **Topic** | Each eligible subscription gets its own copy. With non-durable subscribers, disconnecting can miss messages; durable/shared subscriptions have different rules and require proper identifiers/configuration. |
| **`PERSISTENT` delivery** | Requests delivery durability per the JMS contract and provider; does not guarantee the business handler committed to the DB. Operators must understand storage, replication, failover, and expiry configuration. |
| **Ack/commit** | Informs the provider that reception completed per mode/transaction; the broker updates delivery state. Ack does not validate business semantics. |
| **Redelivery** | When a delivery is unacknowledged or a transaction rolls back, the provider may redeliver per rules; the **`JMSRedelivered`** flag and **`JMSXDeliveryCount`** property aid diagnostics but do not replace a business `eventId`. |
| **TTL/expiration** | A message can expire before being processed. The application defines the lifespan; the broker executes expiry eviction/routing per its features and configuration. |
| **Ordering** | JMS provides certain ordering guarantees within a session/consumer scope; multiple consumers, priorities, redeliveries, selectors, and multiple destinations alter observed order. Do not assume global FIFO. |
| **DLQ** | Destination holding unprocessable messages per broker policy. Requires monitoring, classification, reprocessing procedures, and loop prevention. |

**Do not confuse queues with topics:** increasing consumers on the same queue typically increases job-processing capacity; adding subscriptions to a topic can multiply the number of copies processed per event. Both models require dedicated idempotency design.

## 6. Spring Boot 3.x Example: Who Does What?

The following example uses **Java 17+**, Spring Boot 3.3.x, and **an Apache ActiveMQ Artemis broker running outside the application**. The broker must be ready at `localhost:61616`, username/password must match configuration, and queue **`orders.events`** must exist or be allowed to auto-create by the broker. This is a complete Spring-side sample application; it **does not install/start the broker**.

**`build.gradle`** (in a Gradle project with a matching Gradle Wrapper):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

**`src/main/resources/application.properties`:**

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=demo
spring.artemis.password=demo
spring.jms.pub-sub-domain=false
spring.jms.listener.session.transacted=true
~~~

**`src/main/java/example/jms/JmsDemoApplication.java`:**

~~~java
package example.jms;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JmsDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner publishOneEvent(JmsTemplate jmsTemplate) {
        return args -> jmsTemplate.convertAndSend(
                "orders.events",
                "order-42",
                message -> {
                    message.setStringProperty("eventType", "OrderCreated");
                    message.setStringProperty("eventId", "evt-42");
                    return message;
                });
    }
}
~~~

**`src/main/java/example/jms/OrderListener.java`:**

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {
    @JmsListener(destination = "orders.events")
    public void onOrder(String payload) {
        // Demo: real applications need validation + DB transaction + idempotency.
        System.out.println("Received order: " + payload);
    }
}
~~~

Run once the broker is available: **`./gradlew bootRun`** (Linux/macOS) or **`gradlew.bat bootRun`** (Windows). On a successful message reception, the application output includes the line:

~~~text
Received order: order-42
~~~

This is the **expected output on the happy path**, not a guarantee of exactly one line in every environment: the queue may contain older messages, the broker may deliver messages after reconnecting, and startup also emits Spring logs.

**Line-by-line responsibility breakdown:**

1. **`JmsDemoApplication`** (application) decides the destination name, payload, and `eventType`/`eventId` properties. The sample data is a `String`; the default converter turns it into a **`TextMessage`**.
2. **`JmsTemplate.convertAndSend`** (Spring) creates/sends the message using the `ConnectionFactory` auto-configured by Spring Boot from the starter and Artemis properties.
3. **Artemis** (broker) must allow the connection, accept the address, and deliver the message to an eligible consumer. Spring cannot provide message durability if the broker/config does not support it.
4. **`@JmsListener`** (Spring) connects the message to **`onOrder`**; **`onOrder`** (application) runs business logic. In this simple example, the method only prints to the console and therefore **does not yet demonstrate idempotent processing or a DB transaction**.
5. Property **`spring.jms.listener.session.transacted=true`** instructs the listener container to use a local JMS transaction. If **`onOrder`** throws an exception, message reception rolls back via the container and the broker can redeliver per policy. DB transactions, if added, remain a separate boundary.

## 7. Who Is Responsible When Errors Occur?

| Failure | Possible Behavior | Required Action |
| --- | --- | --- |
| Broker unreachable at send time | Spring translates the JMS error into an exception; producer may be unsure of status if connection drops around broker receipt | Application manages bounded retries, stable `eventId`, and outbox if needed; infrastructure recovers broker/connectivity |
| Listener throws exception with transacted JMS session | Container rolls back; broker may redeliver message | Application classifies errors and preserves idempotency; broker has redelivery/DLQ policy |
| DB commits then JVM dies before JMS commit | Same message may be redelivered even though DB change succeeded | Idempotent consumer and `eventId` marker in the DB transaction; do not assume local JMS tx covers DB |
| Message has persistent data errors | Repeated redelivery blocks queue and increases load | Application validates/classifies; broker limits retries, delays, and DLQ; ops investigates/reprocesses |
| Broker disk full or slow consumer | Backlog grows; producers may be blocked/fail depending on policy | Monitor queue depth/age, throughput, memory/disk, backpressure; optimize consumers and capacity |
| Consumer adds concurrency while business logic requires ordering | Completion order drifts across multiple workers | Design partition keys/serialization in business logic; do not treat added concurrency as free |
| Message exceeds TTL | Never reaches consumer even though producer succeeded | Choose TTL per SLA, alert on expiry/age, and establish business reconciliation |
| Consumer swallows error and returns | Container considers method successful; ack/commit may occur | Only catch errors when handled per contract, or throw to trigger rollback; log with full correlation |

### Critical Transaction Boundaries

A **JMS transaction** manages operations on a JMS session. A **database transaction** manages DB updates. Using **`@Transactional`** with `DataSourceTransactionManager`/`JpaTransactionManager` **does not automatically** combine JMS commit and DB commit into one atomic transaction. When processing must affect both DB and JMS:

- Consider a **transactional outbox** when publishing messages alongside a DB change; a separate relay emits events and marks them sent, which can send duplicates and therefore still requires consumer idempotency.
- On the consumer side, use an **inbox/`processed_messages`** table or a unique constraint on `eventId` in the same DB transaction as the business update.
- Use **XA/JTA** only when multi-resource atomicity is genuinely needed and both provider and resources support it, accepting the added complexity and operational cost; do not assume every `@Transactional` is XA.

### Ack Does Not Mean Business Processing Succeeded

With a **transacted** JMS session, commit includes acknowledgment of message reception; rollback enables recovery/redelivery per provider. With non-transacted sessions:

- **`AUTO_ACKNOWLEDGE`:** per JMS rules, acknowledges automatically; with **`DefaultMessageListenerContainer`**, how Spring manages ack makes it an unreliable choice for rollback/redelivery when a listener fails.
- **`CLIENT_ACKNOWLEDGE`:** the application can call acknowledge, but a single acknowledge can confirm **all messages delivered by that session**, not simply a single `eventId`.
- **`DUPS_OK_ACKNOWLEDGE`:** permits lazy acknowledgment and potential duplicates, requiring consumers to tolerate duplication.

For reliability requirements, consider a **transacted listener session** and read the actual configuration rather than inferring behavior from annotation names.

## 8. System Observability and Troubleshooting

A successful transaction should be traceable across all three layers:

- **Application:** `eventId`, `businessId`, `eventType`, processing outcome, duration, whether errors are retryable, idempotency hit/miss, and business SLA. Do not log sensitive payloads indiscriminately.
- **Spring:** producer/consumer errors, container state, consumer count/concurrency, recovered connections, timeouts, listener processing duration, and listener exception counts.
- **Broker:** queue depth, message age, consumer count, enqueue/dequeue/ack rates, DLQ and expiry, connections/sessions, disk/memory, replication/failover, and ACL/TLS.

For example, when an **`OrderCreated`** message is not processed: first check whether **`eventId` was sent/written to the outbox** (application), next check whether **`JmsTemplate` and the listener container have connection/conversion errors** (Spring), and then inspect **queue depth, DLQ, expiry, subscribers, and ACLs** (broker). Checking all three layers prevents wrongly blaming the broker simply because a consumer failed to update the DB.

## 9. Misconceptions to Avoid

1. **"Using `@JmsListener` means Spring automatically guarantees business exactly-once."** False: Spring triggers the listener; redeliveries and DB/JMS races still require idempotency.
2. **"Broker accepted the message means the order has been processed."** False: that only tells you which step in send/commit succeeded; business completion requires separate confirmation.
3. **"Putting `@Transactional` on the consumer makes JMS and DB commit together."** False when the transaction manager only manages a single resource.
4. **"On error, Spring automatically moves the message to the DLQ."** No such universal DLQ rule exists; DLQ/retries depend on the broker and configuration.
5. **"Queues always process FIFO even with multiple consumers and retries."** Global completion order is not guaranteed in those scenarios.
6. **"Using persistent messages means data is never lost."** Durability depends on the JMS contract, provider configuration, storage/failover/retention, and how the producer handles errors.
7. **"When a consumer throws an exception, every acknowledge mode redelivers the same way."** False: different modes/containers/transactions behave differently; inspect configuration and test with fault injection.

## 10. Ownership Checklist When Designing a JMS Flow

- **Application team:** lock down schema/version/`eventId`; queue vs. topic; idempotency; ordering; retryable vs. non-retryable errors; when to send; outbox/inbox; business timeouts; logs/traces and reconciliation plans.
- **Spring integration team:** verify Jakarta JMS and compatible starter/provider; `ConnectionFactory`; converters; `JmsTemplate`; `@JmsListener`/container; ack/transactions; concurrency; connection/recovery; integration tests for rollbacks and duplicate deliveries.
- **Broker/operations team:** create/provision destinations; queues/topics and subscriptions; ACLs/TLS/secrets; persistence/replication; memory/disk limits; TTL; redelivery delay/max attempts; DLQ; monitoring depth/age/delivery/DLQ; backups and failover drills.

**Criterion for accurate understanding:** being able to explain why **`JmsTemplate` succeeded in sending** yet **the consumer may not have run**; why **a consumer that finished writing to the DB** can still **receive the message again**; and accurately pinpointing which layer needs fixing in each scenario.

### Reference Documentation

- Spring Framework, *Using Spring JMS*: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework, *@JmsListener annotation-driven endpoints*: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot, *Messaging with JMS*: https://spring.io/guides/gs/messaging-jms/
- Jakarta Messaging 3.1 specification (especially queues/topics, sessions, acknowledgment, transactions): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
