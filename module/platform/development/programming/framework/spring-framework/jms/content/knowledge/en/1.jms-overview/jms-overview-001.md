# What Is JMS and the Need for Message-Based Communication

> **Topic:** Spring Framework – JMS  
> **Knowledge Group:** JMS Overview

## Learning Objectives

After this lesson, you can explain what problems JMS solves, distinguish the JMS API from the message broker and Spring's integration layer, describe the send–receive flow through a queue/topic, and identify key trade-offs when moving from synchronous calls to message-based communication.

## 1. Why Do Systems Need Message-Based Communication?

Suppose the Order Service receives a purchase request. Besides saving the order, the system also needs to send a confirmation email, update inventory, create a shipping request, and record analytics data.

**A direct synchronous approach** might look like this:

```text
Client
  |
  v
Order Service
  |--HTTP--> Inventory Service
  |--HTTP--> Notification Service
  |--HTTP--> Shipping Service
  '--HTTP--> Analytics Service
  |
  '--> return response to Client
```

Each step may make sense if its result is truly needed before replying. However, when every secondary task sits on the request processing path, the system easily runs into problems:

1. **Temporal availability dependency:** Notification Service being under maintenance can also slow down or fail the order placement flow, even though the order has already been saved.
2. **Accumulated latency:** Multiple network calls and I/O operations prolong response times.
3. **Tight coupling between services:** Order Service must know which services to call, their addresses, APIs, and how to handle errors for each service.
4. **Traffic spikes:** When order volume surges rapidly, the email service can become overloaded even though order processing still has sufficient capacity.
5. **Hard to recover secondary tasks:** If email sending fails, the system must decide on its own where to store unfinished work and how to retry it.

**Message-based communication** adds an intermediary: the producer sends a message into the messaging infrastructure; the consumer receives the message and processes it at its own pace.

```text
Client -> Order Service -> [Broker / Queue: orders.created] -> Notification Worker
                  |                    |
                  |                    '--> message waits when worker pauses
                  '--> return "accepted" result when required operation completes
```

The order creation service can complete its own responsibility without waiting for the email to be sent. Notification Worker can be deployed, maintained, and scaled in instance count independently.

This **does not make the system instantaneous or guarantee absolute success**. It changes the processing contract: a task is *accepted* to be executed later, and final success must be tracked separately. For tasks requiring an immediate result (such as confirming payment before issuing a ticket), you still must explicitly design waiting points, intermediate states, and error rules.

## 2. What Is JMS?

**JMS (Java Message Service)** is the familiar name of the messaging API in the Java ecosystem. In modern Jakarta EE, the corresponding API is called **Jakarta Messaging**, using types in the `jakarta.jms` package; older Java EE systems typically use `javax.jms`. The purpose of the API is to provide a common programming model and contract for Java applications to create, send, receive, and process messages.

Three layers need to be separated:

| Layer | Role | Examples |
| --- | --- | --- |
| **JMS/Jakarta Messaging API** | Defines interfaces and semantics for sending and receiving messages | `ConnectionFactory`, `JMSContext`, `Message`, `Queue`, `Topic` |
| **JMS provider/message broker** | Provides connections, routing, storage, and message delivery according to configuration | Apache ActiveMQ Artemis and compatible providers |
| **Spring JMS** | Helps Spring applications work with JMS more conveniently | `JmsTemplate`, `@JmsListener`, listener container, message converter |

JMS **is not the message broker itself**, is not the HTTP protocol, and does not automatically create durable queues inside the application's JVM. For two processes to communicate via JMS in practice, there must be an appropriate provider, destination configuration, and a connection to that provider.

JMS is also **not synonymous with all forms of messaging**. Kafka, AMQP, and event streaming systems have their own contracts, features, and operational models; you should not apply the JMS model directly to them simply because they also pass messages.

### Basic Components

- **Producer:** the party that creates and sends messages. For example, Order Service announcing a new order.
- **Consumer:** the party that receives and processes messages. For example, Notification Worker sending confirmation emails.
- **Destination:** the place where messages are sent; in JMS, usually a `Queue` or a `Topic`.
- **Provider/broker:** the intermediary component that manages destinations and message delivery.
- **Message:** the unit of exchange containing the content (*body/payload*), standard headers, and application-attached properties.
- **Connection / Session / JMSContext:** client-side objects used to communicate with the provider, manage send–receive operations, and control acknowledgment or transaction semantics.

An application does not need to know which server the consumer resides on as long as both use the right destination and follow the message contract.

## 3. Two Distribution Models: Queue and Topic

### 3.1. Queue — one job received by one consumer

```text
Producer A --\
              >-- [Queue: invoices.generate] --> Consumer 1
Producer B --/                            \-----> Consumer 2
```

In the **point-to-point** model, a message is delivered to **one eligible consumer** of the queue. Multiple consumers reading from the same queue are typically used to distribute load: each message goes to one of them, rather than automatically broadcasting copies to all.

Example: the system has 10,000 invoices to generate as PDFs. Three workers read from `invoices.generate` to share the work, but each invoice only needs one successful business processing execution.

It is important to distinguish: "one consumer receives the message on a single delivery" **does not mean business processing is guaranteed to happen exactly once**. When errors occur, the broker may redeliver the message; the consumer must tolerate duplicate deliveries.

### 3.2. Topic — each matching subscription receives a copy

```text
                      /--> [Subscription: analytics] --> Analytics Worker
Producer --> [Topic: orders.events]
                      \--> [Subscription: audit] -----> Audit Worker
```

In the **publish/subscribe** model, independent subscriptions on a topic can receive separate copies of the same message. For instance, an `OrderCreated` event needs to reach both the reporting service and the audit service; processing in one subscription does not acknowledge on behalf of the other subscription.

There are two points to remember:

- **Non-durable subscription:** normally exists only while the consumer/subscription is active; messages published when no active subscriber is present may be missed.
- **Durable subscription:** the provider retains the subscription even when the consumer disconnects, allowing it to later receive messages still retained under delivery, expiration, quota, and provider policy conditions.

A subscription shared among multiple consumers can distribute each copy within that subscription to one consumer; it does not turn the entire topic into a single queue.

| Criterion | Queue | Topic |
| --- | --- | --- |
| Common purpose | Assign a job to one worker | Broadcast an event to multiple interested groups |
| Multiple consumers | Share work on a single queue | Each subscription receives its own stream; consumers can share load within a subscription |
| Examples | Invoice generation, email sending, image processing | Order created, customer address changed, status updated |
| When consumers are absent | Queue typically holds pending messages per retention policy | Must consider durable vs. non-durable subscription |
| What must not be assumed | Exactly-once processing | Every subscriber always receives every event |

## 4. How a Message Flows Through the System

Consider an example: Order Service emits a message to send an email.

1. **Order creation business logic:** the service saves the order and determines that it needs to notify `OrderCreated` (or assign a `SendOrderConfirmation` command).
2. **Producer sends:** converts the payload into a message and sends it to the configured destination.
3. **Provider accepts:** the broker decides how to store, route, and deliver to consumers according to the delivery mode and operational policies.
4. **Consumer receives:** the listener retrieves the message and invokes the email-sending logic.
5. **Processing acknowledgment:** depending on the session/transaction/acknowledgment mode, the consumer acknowledges so the broker can remove the processed message from pending items.
6. **If an error occurs:** the message may be redelivered or routed to an error-handling path; retry policies, attempt limits, and dead-letter destinations must be designed.

```text
[Order Service] --send--> [Broker / orders.confirm-email]
                               |
                               v
                         [Email Consumer]
                           |        |
                        success    error
                           |        |
                         ack/commit  retry / dead-letter (depending on configuration)
```

**A successful send** only confirms that the send operation to the provider met the configured conditions; it does not mean the email has been sent, the consumer's database has been updated, or the entire business workflow has completed.

### What Does a Message Carry?

A useful mindset is to separate business content from delivery metadata. Example JSON content placed inside a `TextMessage`:

```json
{
  "eventId": "evt-2048",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "ORD-42",
  "occurredAt": "2026-10-30T01:00:00Z"
}
```

This is an **example of an application-defined payload contract**, not mandatory fields mandated by JMS. JMS has headers such as `JMSMessageID`, `JMSCorrelationID`, `JMSTimestamp`, `JMSReplyTo`, `JMSExpiration`, and `JMSDeliveryMode`; applications can also attach properties for filtering or tracing. Do not assume `eventId` and `JMSMessageID` have the same meaning: an event ID can remain stable across business retries, whereas a message ID is tied to a single infrastructure-level transmission.

An **Event** describes something that happened (`OrderCreated`). A **Command** requests a party to perform work (`SendOrderConfirmation`). Both can be transmitted over JMS, but destination names, success conditions, and duplicate handling should reflect this distinction. You should not send raw internal Java objects without a versioned contract to another service.

## 5. What You Gain and the Price You Pay

### Worthwhile Benefits

**Temporal decoupling.** Producer and consumer do not necessarily have to be online at the same time, especially with queues or appropriately configured durable subscriptions. The receiving service can pause while pending tasks remain intact.

**Deployment decoupling.** The producer does not need to call each consumer's dedicated endpoint. A new service can register a subscription without forcing the producer to modify its call flow for event broadcasting.

**Spike absorption.** When messages arrive faster than they can be processed over a short period, the queue acts as a buffer. Consumers can scale up instances to catch up gradually.

**Isolation of certain failures.** If a secondary task fails, the main order placement path can still complete according to the designed contract; the consumer has the opportunity to retry or process later.

**Well-suited for background work.** Sending emails, generating reports, syncing search indices, updating metrics, converting media, or many other time-consuming operations typically do not need to block an HTTP request.

### Trade-offs You Must Understand

**Eventual consistency.** The consumer may process after a few milliseconds or several minutes. Data-reading features must accept and display a "processing" state when needed.

**Operational infrastructure.** The broker also has capacity limits, quotas, disk space, connections, authentication, and potential failures. A queue is not infinite memory.

**Harder flow observability.** A single HTTP request no longer spans the entire job. Correlation IDs, logs, queue depth metrics, message age, and error rates are needed.

**Duplicate and out-of-order processing.** Retries, multiple workers, and parallel branches can cause messages to be processed multiple times or out of expected order. Business rules must tolerate those situations.

**Hard to maintain cross-service transactions.** Writing to the producer's database and publishing to JMS are two actions that can fail at different points; a consistency strategy such as transactional outbox is needed if there is no supported and properly configured unified transaction.

## 6. Reliability: Understand Enough Not to Overpromise

JMS provides delivery and acknowledgment mechanisms, but **end-to-end reliability is a property of the entire design**, not just the API name.

### Persistent Does Not Mean "Everything Is Guaranteed to Complete"

The `PERSISTENT` delivery mode asks the provider to prioritize protecting the message against failure modes within the provider's scope of guarantees; `NON_PERSISTENT` typically prioritizes performance and accepts some risk of message loss. Even when using `PERSISTENT`, messages can still expire (TTL), be affected by storage limits, or be governed by administrative policies. Topics require choosing the appropriate subscription to retain messages while consumers are absent.

### Acknowledgment Is a Critical Boundary

If a consumer reports it has processed a message before actually writing the data, a failure immediately afterward can lose the work. If the consumer has already written the data but fails before acknowledging the message, the broker may redeliver it and repeat the operation.

In a transacted session, `commit` and `rollback` determine the acknowledgment/recovery of the JMS work belonging to that session. With `AUTO_ACKNOWLEDGE` or `CLIENT_ACKNOWLEDGE`, the acknowledgment timing differs. How the Spring listener container configures transactions/acknowledgment directly affects when a message is considered done.

### A Duplicate Processing Example

A consumer receives `OrderCreated(orderId=ORD-42)` and writes a reward-points record. The database commits, but the broker connection drops before the broker sees the acknowledgment. The next redelivery could credit points a second time if the logic simply runs "add 100 points".

Defense approach: use a business key or `eventId` to detect already-processed messages; store the processing status and business effect in the same database transaction when possible, for example via a unique constraint on (`consumerName`, `eventId`). When a duplicate is detected, skip safely and then complete the acknowledgment mechanism.

**Do not call JMS-guaranteed delivery "exactly once end-to-end"** unless atomicity between the broker, database, and external side effects (such as email or payment APIs) has been proven. Even when a message is redelivered, the business outcome must be designed not to duplicate.

### Retry and Dead-Letter

- Transient errors (broker/DB connection loss, downstream HTTP timeout) can be retried after a reasonable delay.
- Unprocessable data errors (missing required fields, invalid schema) should be routed to an error path for inspection to avoid infinite retries.
- Retries should have an attempt limit, increasing backoff intervals, and clear monitoring of failed message counts.
- **Dead-letter queue (DLQ)** is a broker or application mechanism depending on configuration, not a guarantee that simply using JMS automatically provides a DLQ.

## 7. Relation to Spring Framework

Spring JMS provides a convenient way to use the JMS API without manually managing the entire connection and listener lifecycle:

- `JmsTemplate` assists with sending and receiving, converting payloads using a `MessageConverter`.
- `@JmsListener` marks a receiving method; the listener container is responsible for coordinating method invocation and interacting with the provider.
- `ConnectionFactory` is the connection point to the JMS provider; a real provider must be configured, such as ActiveMQ Artemis.
- Spring Boot can auto-configure part of the JMS infrastructure when appropriate dependencies and configuration are present. Defaults typically target queues; using topics requires appropriate pub/sub configuration.

The following example **illustrates code in a Spring application with an already configured broker connection**, not two standalone Java files runnable with `javac`:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final JmsTemplate jmsTemplate;

    public OrderEventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String orderId) {
        jmsTemplate.convertAndSend("orders.created", orderId);
    }
}
```

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class FulfillmentListener {
    @JmsListener(destination = "orders.created")
    public void onOrderCreated(String orderId) {
        // Perform business logic and record idempotency here.
        System.out.println("Received order: " + orderId);
    }
}
```

If the producer calls `publish("ORD-42")` and the listener receives/processes it successfully, an illustrative log line from the listener is:

```text
Received order: ORD-42
```

This log line **is not a guaranteed outcome of every run**: it also depends on the broker, connection, queue, listener, startup timing, and error state. The example uses `String`, so `JmsTemplate`'s default converter can create/read a text-format message. In practice, the payload should include a schema version, event identifier, correlation ID, and deduplication rules.

Additional note: `JmsTemplate.convertAndSend(...)` still performs the send operation with the provider on the calling thread. "Asynchronous messaging" primarily describes that **the producer does not wait for the consumer to finish business processing**, rather than claiming every send method never blocks or cannot fail.

## 8. Standalone Java 17 Demo: Visualizing Temporal Decoupling

The following program only simulates the producer–consumer idea using an in-memory queue. **It does not use JMS, has no broker, no persistence, and no acknowledgment**. Its purpose is to clarify the difference between "task accepted" and "task completed".

Create the file `MessagingIdeaDemo.java`:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;

public class MessagingIdeaDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        CountDownLatch allowProcessing = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                String orderId = queue.take();
                allowProcessing.await();
                System.out.println("Consumer handled: " + orderId);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        worker.start();

        queue.put("ORD-42");
        System.out.println("Producer accepted: ORD-42");

        allowProcessing.countDown();
        worker.join();
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac MessagingIdeaDemo.java
java MessagingIdeaDemo
```

Deterministic output of the program:

```text
Producer accepted: ORD-42
Consumer handled: ORD-42
```

`CountDownLatch` holds the consumer back so the print order clearly illustrates the flow; `join()` merely lets the demo program wait for the worker to finish before exiting. In real services, producer and consumer are usually independent processes; the provider acts as the intermediary. You should not substitute an internal queue like this for a broker when work must survive application restarts or communicate across multiple services.

## 9. Choosing Synchronous Communication or JMS?

Ask the first question: **Does the caller need the completed business result immediately to proceed?** Then examine latency, consistency, error, and operational constraints.

| Scenario | Preferred Choice | Reason |
| --- | --- | --- |
| Validate mandatory data before saving an order | Direct call or same-transaction processing | Must know the outcome before accepting |
| Send confirmation email after order is saved | Queue | Independent task; slowness should not block the request |
| Generate thumbnail after image upload | Queue | Background job; can distribute load and retry |
| Multiple services react when an order is created | Topic with appropriate subscriptions | One event processed by multiple groups |
| Query current balance needing immediate return | Synchronous | Data needed at the time of request |
| Payment requiring confirmed verification before the next step | Explicitly design confirmation flow, either synchronous or async workflow | Must not treat "placed in queue" as "paid" |

They can be combined: an HTTP API accepts the request, validates and writes the initial state, and then publishes a message; the client receives a task ID and tracks status via an API or subsequent notification. For work requiring an immediate result, do not force a queue just to make the system "microservices".

### Design Questions Before Implementation

1. **What does the message represent?** An event that already happened or a command requesting processing? Who owns the contract?
2. **Who receives it?** One worker in a group or multiple independent subscriptions?
3. **What happens when the consumer stops running?** How long must messages be retained? Queue or durable topic subscription?
4. **What counts as complete?** Order saved, message sent, message received, or side effect executed?
5. **What if duplicates arrive?** Where is the idempotency key stored and how long is it kept?
6. **What if processing fails repeatedly?** Retries, backoff, dead-letter, and manual intervention?
7. **What if the queue keeps growing?** Resource limits, alerts, and how to throttle or scale consumers?
8. **How is a request traced?** Event ID, correlation ID, trace ID, and queue/consumer metrics?
9. **Are DB write and message send atomic/synchronous?** If not, is a transactional outbox or reliable coordination mechanism needed?

## 10. Common Misconceptions

- **"JMS is ActiveMQ."** False: JMS is the API contract; ActiveMQ Artemis is one provider that can implement that contract.
- **"Using a queue means messages are never lost."** False: you must consider persistence, transactions, expiration, broker storage, acknowledgment, and operational policies.
- **"One message in a queue executes the business logic exactly once."** False: redelivery can cause duplicate processing; idempotency is required.
- **"A topic always delivers all messages to every application even when shut down."** False: non-durable and durable subscriptions have different semantics.
- **"Calling send completes the entire business flow."** False: the consumer may not have started yet, may be retrying, or may fail.
- **"All JMS operations are asynchronous."** False: JMS can receive synchronously; a send call can also wait for provider confirmation.
- **"Having a broker removes the need for load management."** False: the broker has limits and will experience pressure if production rate exceeds consumption rate over time.
- **"Messages always arrive in exact order across all consumers."** False: ordering depends on session, destination, selectors, multiple consumers, and retry mechanisms; do not assume system-wide ordering.
- **"JMS guarantees can replace database transactions."** False: you must consider transaction boundaries and updated data in each system.

## 11. Self-Check Questions

**Question 1.** Order Service places a `SendEmail` message into a queue and returns HTTP 202. Can it immediately display "Email sent"?

**Answer:** No. 202 expresses that the request has been accepted under the API contract. There must be a status or signal from the consumer to confirm the email was actually sent.

**Question 2.** The same `OrderCreated` needs to reach Analytics and Audit independently. Does using one queue for both achieve this goal?

**Answer:** Not if both compete on the same queue: typically each message goes to only one consumer. Use a topic with two independent subscriptions, or design two separate work channels depending on requirements.

**Question 3.** A consumer has written to the DB successfully but loses connection before ack; what must be prepared for?

**Answer:** The message may be redelivered. Duplicate messages must be detected and the business effect kept idempotent.

**Question 4.** Can a producer publish a persistent message to a topic while a non-durable subscriber is offline and guarantee that subscriber will receive it after restarting?

**Answer:** No. If receiving while absent is needed, a durable subscription with an appropriate retention policy must be designed.

**Question 5.** What is the biggest benefit of messaging in the email-sending example?

**Answer:** Separating the timing and responsibility of order creation from email sending, allowing secondary tasks to be processed at their own pace and recover from failures via a designed mechanism.

## Key Takeaways

JMS/Jakarta Messaging provides a **common language for Java applications to exchange messages**. Queues are suitable for delivering a job to one consumer in a group; topics are suitable for distributing events to independent subscriptions. Spring JMS helps Spring applications send and receive using familiar abstractions. Messaging is useful when work can be processed later and producers need to be decoupled from consumers, but completion states, duplicate tolerance, retention, retries, data consistency, and operational observability must be explicitly designed.

### Official References

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — definitions of queues, topics, subscriptions, acknowledgment, and reliability.
- [Spring Framework: Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate` and message converters.
- [Spring Framework: Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — synchronous receiving and `@JmsListener`.
- [Spring Guide: Messaging with JMS](https://spring.io/guides/gs/messaging-jms/) — example of JMS connection and listener in Spring Boot.