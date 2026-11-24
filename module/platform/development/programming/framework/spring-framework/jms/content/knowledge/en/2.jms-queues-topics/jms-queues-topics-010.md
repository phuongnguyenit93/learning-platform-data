# Choosing Queue or Topic Based on the Communication Contract

## Lesson Objectives

When designing asynchronous communication with **JMS / Jakarta Messaging in Spring**, the decision "Queue or Topic?" must stem from **the contract between the message sender and the parties responsible for processing**. Technology names, running instance counts, or the fact that a system "has multiple services" do not by themselves dictate the destination type.

After this lesson, you should be able to determine:

1. Whether a message is a **work-dispatch command** for one worker group or an **event/notification** that multiple independent processing groups need to know about.
2. Who is permitted to receive, how many copies each group must receive, and whether misses are allowed when consumers disconnect.
3. How Queue, Topic, **subscriptions**, competing consumers, and durable/shared subscriptions affect outcomes.
4. How delivery guarantees, redelivery, idempotency, ordering, and replay limits must be specified in the contract.
5. How to apply and test the decision using `JmsTemplate`, `@JmsListener`, and Spring JMS configuration.

**Guiding rule:** If *a unit of work* should be processed by **any single member within the same group**, normally choose a **Queue**. If *an event* must be processed by multiple **independent receiving groups**, normally choose a **Topic with a corresponding subscription per group**. Exceptions exist; verify against the full contract in the following sections.

## 1. The Actual Delivery Models

### 1.1. Queue: Multiple Consumers Competing on the Same Queue

In Jakarta Messaging's point-to-point model:

- Producers send messages to a **queue**.
- Multiple consumers listening on the queue form **competing consumers**.
- On a normal delivery, each message is delivered to **one consumer** among eligible consumers; other consumers on the same queue do not automatically get a copy.
- Unprocessed messages can wait on the queue even if no consumer is temporarily present, within limits of TTL, storage, broker policies, and recovery capabilities.
- The specification **does not mandate** a load-sharing algorithm among consumers; do not promise "50/50 alternation".

~~~text
                          +---> Worker A
Producer ---> [orders.work QUEUE] ---> Worker B
                          +---> Worker C

One message per delivery: only one worker in the group receives it.
If the worker fails before acknowledging, the message may be redelivered.
~~~

Example: `GenerateInvoice(invoiceId=17)` is a request to perform a task. If there are three replicas of the Invoice Worker service to increase throughput, all three subscribe to one queue; one message needs **one business completion**, even if multiple attempts can occur.

**Easily misunderstood point:** "One consumer receives" is **delivery** semantics, not an **exactly-once business processing** guarantee. A consumer may process and crash before commit/ack, causing the same task to run again. The contract must require idempotency or a deduplication mechanism.

### 1.2. Topic: Multiple Subscriptions Receiving the Same Event

In Jakarta Messaging's publish/subscribe model:

- Producers publish messages to a **topic**.
- Each eligible **subscription** gets its own share of that message.
- A topic can have multiple subscriptions, for example Billing, Analytics, Notification.
- **Acknowledgment/rollback of one subscription is independent of another subscription** at the level of the message delivered to each subscription.
- A topic **does not by default broadcast every message to every existing process**. You must look at which subscription a process belongs to and whether that subscription existed at publish time.

~~~text
                               +---> [Billing subscription] ---> Billing worker(s)
Producer ---> [orders.events TOPIC]
                               +---> [Email subscription] -----> Email worker(s)
                               +---> [Audit subscription] -----> Audit worker(s)

One event -> each independent subscription gets its own share of messages.
Multiple workers sharing one subscription -> compete to process that subscription's copy.
~~~

Example: `OrderPlaced(orderId=17)` occurred. Billing issues an invoice, Stock reserves inventory, Analytics updates statistics: each **business group** must react independently. If all three services read from the **same queue**, only one service receives each message and the other two miss it.

### 1.3. "Consumer", "Subscription", and "Service" Are Different

This is the key to choosing correctly:

| Term | Meaning in the Decision |
| --- | --- |
| **Producer** | Message sender; publishes a command or event according to the contract |
| **Queue** | One place accumulating work; consumers reading the same queue compete with each other |
| **Topic** | Publish point; the broker distributes message copies to each matching subscription |
| **Subscription** | Registration of a topic receiving group; has identity, filters, durability/shared options |
| **Consumer** | Object/client actually calling receive or receiving callbacks; one service can have multiple consumers |
| **Service group** | Group of a business capability needing to process a message type; can run multiple replicas |
| **Replica/instance** | One deployed process/Pod of a service; replica count does not necessarily equal subscription count |

Two instances of **the same service** normally *share load within one group*. Two **services with different purposes** normally need *one independent copy per group*. Scaling from 1 to 10 replicas should not change the number of **logical completions** required by the contract.

## 2. Selection Matrix by Contract Terms

| Term to Determine | Queue Direction | Topic Direction |
| --- | --- | --- |
| **Who must process?** | Any single worker within one group | Multiple independently subscribed groups |
| **Scaling replicas** | Consumers compete on the same queue | Replicas within *one* group use a shared subscription if load sharing is needed |
| **Receiving groups with different purposes** | Must create separate queues and an external fan-out mechanism | Each group has its own subscription on the topic |
| **Temporarily no consumers** | Queue normally holds messages waiting for consumers per broker policy | Only **already created durable** subscriptions retain while no consumer is present; non-durable may lose |
| **Subscription state** | No concept of durable topic subscription | Has non-durable/durable and shared/unshared |
| **Adding new receiving groups** | Usually requires adding a routing/copying step for messages | New groups can subscribe to the topic, but do not automatically get history prior to subscribing |
| **Failure handling** | Retry/redelivery tied to the message in the queue | Each subscription tracks processing of its own copy, with broker-specific retry/DLQ policies |
| **Arbitrary point-in-time history replay** | Not available by default | Also not available by default; durable subscriptions do not replace an event log |
| **Expected business message count** | Roughly one completed processing per command (idempotent design) | One completed processing **per eligible group** (per-group idempotent design) |

Distinguish a **topic durable subscription** from a **persistent message delivery mode**. Persistent relates to the broker's ability to preserve messages per policy; durable subscription relates to retaining messages while the subscriber is **offline**. Sending persistent messages to a topic **does not automatically create** a durable subscription for a consumer registering later.

## 3. Six-Question Decision Process

### Question 1 — Does the message describe an action to perform, or something that already happened?

- **Command** (imperative/work request): `SendReceipt`, `RebuildIndex`, `ReserveSeat`. Usually one capability holds primary responsibility, so Queue fits. Name and content describe a task.
- **Event**: `PaymentCaptured`, `UserRegistered`, `ProductPriceChanged`. Multiple capabilities can react independently; Topic usually fits. Name describes something that occurred.
- **Notification**: could be an event multiple groups need to receive or a request to send a single email. Look at the **number of processing responsibilities**, not just the name.

"Command = Queue, Event = Topic" is a **heuristic**, not an absolute law. An event can be routed through a single service's dedicated queue; a fan-out command may have its own contract. However, you must explicitly document who owns the message and who must receive copies.

### Question 2 — How many **independent business groups** must receive it?

- **Only one processing group** → Queue is the simple default.
- **Multiple groups, all must process** → Topic; each group gets a separate subscription.
- **Only one group currently, yet wanting to add a listener for metrics** → do not place a metrics reader competing on the business queue; consider publishing a separate event after state succeeds.
- **A subset of groups must receive conditionally** → Topic plus suitable message selectors/routing; selectors have syntax and schema constraints and can add significant load depending on the broker.

Do not count containers/Kubernetes Pods. Count the **number of independent business commitments** that must complete.

### Question 3 — May an offline consumer miss messages?

For a Queue, messages normally wait when the worker group is offline subject to TTL, quotas, and broker configuration.

For a Topic, you must choose the subscription type:

| Subscription | When no consumer is present | When multiple consumers exist in the same group |
| --- | --- | --- |
| **Non-durable, unshared** | Does not retain backlog after subscription ends | Only one consumer on the subscription |
| **Non-durable, shared** | Subscription gone once the last consumer closes; may miss while the whole group is offline | Multiple consumers split copies of the same subscription |
| **Durable, unshared** | Retains eligible messages published **after the subscription was created** (barring expiry/policy) | One active consumer at a time |
| **Durable, shared** | Also retains backlog by subscription identity | Multiple consumers share load on the same durable subscription |

In Jakarta Messaging 3.x, a **shared durable subscription** may not require a `clientID`, whereas **unshared durable** requires a stable `clientID` and subscription name. Do not assign the same inappropriate `clientID` to multiple instances and expect them to run in parallel.

Policy example: Marketing dashboards tolerate missing telemetry when shut down and can use non-durable. Accounting must process every `PaymentCaptured` even across deploys/restarts, and usually requires a durable subscription **created before publish time**.

### Question 4 — Does one group need multiple instances to share load?

- With **Queue**: add consumers to the same queue; each message is distributed to one eligible consumer.
- With **Topic**: to have two replicas execute *different messages of the same group*, use a **shared subscription** (usually shared durable for critical business tasks). If two independent subscriptions are created, each replica can process **every event**, causing intentional duplicate processing by design.
- With an **unshared durable topic subscription**: do not enable multiple concurrent consumers on the same subscription; it will conflict under API/provider rules.

A topic with three business subscriptions, each having two workers, normally creates **three logical copies per event** (one copy per group), and then each copy is processed by one of the two workers in the corresponding group. Not six logical copies.

### Question 5 — What are the ordering, retry, and transaction recording needs?

Choosing Queue/Topic **does not by itself solve** ordering or transactions:

- **Ordering:** multiple producers, competing consumers, concurrent handlers, redeliveries, and message selectors can make business processing order differ from publish order. If sequential order per `orderId` is mandatory, specify the per-key invariant and evaluate concurrency limits/partitioning/message grouping actually supported by the provider.
- **Redelivery:** when a consumer fails, fails to ack, or rolls back, the broker may redeliver the message; another consumer may receive the redelivered copy.
- **Idempotency:** use `messageId`/`eventId` or a dedicated business key to prevent duplicates in the database. Do not use delivery count alone as proof that a message was processed only once.
- **Commit:** a JMS session transaction does not automatically fold DB writes into the same atomic transaction. You must design the DB–broker boundary: transaction boundaries, idempotent inbox, outbox, or XA/JTA as needed.
- **Poison message:** configure retry thresholds, backoff, DLQ, and fix/replay procedures per queue/subscription.
- **Expiration / TTL:** expired data can be lost whether the destination is a queue or a durable topic subscription.

### Question 6 — Is historical replay, large-scale fan-out, or indefinitely retained data required?

Queue and Topic in Jakarta Messaging are optimized for broker- and subscription-based messaging communication. **A durable subscription is not an event store supporting arbitrary replay from an old timestamp**; a new subscriber normally cannot automatically read events published before the subscription existed. If "re-read the entire history from 6 months ago" is a mandatory requirement, evaluate an event log (such as Kafka), dedicated domain event storage, or specific storage/replay features of the broker. Regardless of technology choice, retention policies, schema versioning, and data access controls are still required.

### Condensed Decision Tree

~~~text
A message is published, who MUST complete processing?
|
+-- Only one group is responsible
|     |
|     +-- Multiple replicas? --> Compete on one QUEUE
|     +-- Need another independent service later? --> Consider publishing an EVENT to a separate TOPIC
|
+-- Multiple groups receive independently
      |
      +-- TOPIC, one separate SUBSCRIPTION per group
            |
            +-- Tolerates misses while offline? --> NON-DURABLE
            +-- Must not miss while offline? -----> DURABLE, registered before publish
            |
            +-- Multiple replicas share load in a group? --> SHARED subscription
            +-- Single consumer? -------------------------> UNSHARED may also fit

Still define retries, idempotency, ordering, TTL, DLQ, auth, monitoring afterward.
~~~

## 4. Real-World Scenarios and Right Decisions

### Scenario A — Dispatching a Job to One of the Workers

A service receives PDF generation requests; there are 5 workers with equal capability. One job only needs to produce one final file.

**Contract:** `RenderPdf(jobId)`, queue `pdf.render.commands`, group `renderer`; each job has one business outcome. Choose **Queue**; 5 replicas compete to receive. Use `jobId` to prevent duplicate file writes/creation on redelivery. If a worker crashes after writing the file but before ack, another worker may receive it again; check job status instead of creating a duplicate output.

### Scenario B — One Event, Three Independent Actions

Order Service recorded an order successfully and emits `OrderPlaced`. Fulfillment prepares goods, Customer Care sends an email, Analytics updates reports. All three must process separately.

**Contract:** topic `orders.lifecycle.events` with three **durable subscriptions**: `fulfillment-v1`, `customer-care-v1`, `analytics-v1`. Each group scales via **shared durable subscription** if broker/client are compatible. Events contain `eventId`, `orderId`, `occurredAt`, and `schemaVersion`.

**Do not** have all three services listen on `orders.lifecycle.queue` if you expect all three to receive. A queue delivers each message to only one consumer, which could cause Analytics to "steal" Fulfillment's message.

### Scenario C — Two Replicas of One Service Are Not Two Independent Recipients

There are 2 Billing Pods. Each `PaymentConfirmed` must update an invoice **once in business terms**. On a Topic, if both Pods create **two different non-shared subscriptions**, both receive the event: violating load-balancing intent.

**Right contract:** both Pods belong to the same subscription named `billing-v1`, configured as **shared durable**. They split work and still must guard against duplicates on redelivery. A **different** subscription like `audit-v1` is needed if Audit also needs its own copy.

### Scenario D — A Live Dashboard Allowed to Miss Updates

A dashboard only needs metrics while online, with no obligation to catch up on every old data point. Topic `live.telemetry` with **non-durable** subscriptions can be simple and save backlog; if the dashboard disconnects, messages during the offline window may be missed. If historical metrics are later needed to redraw charts, read from a metrics store rather than turning a non-durable Topic into a data store.

### Scenario E — Request/Reply Does Not Automatically Force Topic

A service sends `CheckFraud(requestId)` to the Fraud Worker group and waits for one result. A request Queue makes sense because one worker executes one request; the reply can travel via a temporary queue/reply queue with `JMSReplyTo` and `JMSCorrelationID`. Set timeouts, correlation, and duplicate-reply handling. Topic is only useful if **each independent group** needs to receive a copy of the request; that is a different contract.

### Scenario F — "One Queue per Service" Can Also Achieve Fan-Out

An integration service reads an incoming event and **copies** one message into each target queue of Billing, Audit, and Notification: each queue has its own competing consumers. This structure achieves fan-out thanks to the **router/application** handling duplication, not because of the inherent nature of a single queue. When using a Topic, the broker/subscription handles per-group distribution. Choose based on infrastructure, operations, route ownership, and observability requirements; do not claim queues broadcast *on their own*.

## 5. Writing the Communication Contract Before Coding

At minimum, finalize and version the following fields:

| Attribute | Question to Answer |
| --- | --- |
| `messageType` + `schemaVersion` | Is this a command or an event? What schema/version does the payload have? |
| `destination` + `domain` | What is the destination name, Queue or Topic? Who has permission to publish/consume? |
| **Producer ownership** | Who is responsible for publishing? At what point relative to source data commit is it published? |
| **Consumer group(s)** | Exactly which groups must process? How many subscriptions does each group have? |
| **Offline policy** | When all consumers in a group stop, how long must messages be retained? Has the durable subscription been created yet? |
| **Delivery/ack** | When does ack/commit occur? Maximum retries/redeliveries? TTL/expiration? |
| **Idempotency key** | Which `commandId`/`eventId` or business key is used to deduplicate? Where is it stored? |
| **Ordering requirement** | Is ordering per `accountId`/`orderId` required? At what concurrency? |
| **Poison-message policy** | What are the DLQ, retry delay, alerting, and reprocessing procedures? |
| **Observability** | How are pending message count/message age/redelivery count/DLQ/processing latency measured? |
| **Contract evolution** | How many consumer versions are still active? Who ensures backward compatibility? |

### Two Sample Contracts

**Sample 1: Single-Task Processing Command**

~~~yaml
name: GenerateInvoice
kind: command
destination: invoices.generate.queue
jmsDomain: queue
producer: Checkout
responsibleGroup: InvoiceWorkers
replicas: 3 # competing consumers on the same queue
idempotencyKey: invoiceRequestId
delivery: retryable, at-least-once business design
ack: after successful handling (transacted listener)
failure: bounded retries -> DLQ, operator review
ordering: no global ordering requirement
schemaVersion: 1
~~~

**Sample 2: Event with Multiple Independent Obligations**

~~~yaml
name: OrderPaid
kind: event
destination: orders.paid.topic
jmsDomain: topic
producer: PaymentService (after payment status is committed)
groups:
  - name: fulfillment-v1
    subscription: shared-durable
    replicas: 3
  - name: receipt-v1
    subscription: shared-durable
    replicas: 2
  - name: analytics-v1
    subscription: shared-durable
    replicas: 2
idempotencyKey: eventId (each group tracks independently)
offline: no-loss-after-subscription-created, subject to broker retention/TTL
failure: independent retries/DLQ for each subscription
schemaVersion: 1
~~~

The YAML snippets above are **descriptive contracts for discussion/documentation**, not Spring Boot configuration you can copy into `application.yml` to run automatically. "At-least-once business design" describes how the application tolerates redelivery; you cannot infer all delivery guarantees from a YAML file alone.

### Example Envelope for an Event

~~~json
{
  "eventId": "evt-2026-10-30-001",
  "type": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-10-30T01:00:00Z",
  "orderId": "order-42",
  "paymentId": "payment-77",
  "amountMinor": 155000,
  "currency": "VND"
}
~~~

`eventId` identifies the event for deduplication; `orderId` is the business entity key; `schemaVersion` helps consumers detect payloads needing upgrades. This is a JSON payload independent of Queue/Topic choice: JMS can carry a `TextMessage` containing JSON, though converters/schemas are needed on both ends. Do not place sensitive secrets directly in messages without appropriate protection.

## 6. Implementing Queue and Topic in Spring JMS

Spring JMS runs on top of Jakarta Messaging; `@JmsListener` methods use a Spring-created **listener container**, while `JmsTemplate` sends messages. With **String destination names**, domain configuration must be coordinated on **both producer and consumer**:

- `JmsTemplate.setPubSubDomain(false)`: interprets the destination name as a **Queue**.
- `JmsTemplate.setPubSubDomain(true)`: interprets the destination name as a **Topic**.
- `DefaultJmsListenerContainerFactory.setPubSubDomain(...)`: determines whether the container listens on a queue or topic.
- `@JmsListener(destination = "...", containerFactory = "...")`: uses the factory matching the domain.
- `setSubscriptionDurable(true)` and `setSubscriptionShared(true)` are for the corresponding topic subscription types; use a consistent subscription name per group.

Spring Boot's default usually configures JMS toward **Queue**; `spring.jms.pub-sub-domain=true` can be enabled for default configuration, but that affects both the default producer and listener, **which is unsuitable when the same application needs both queues and topics simultaneously**. In that case, use **two explicitly named templates/factories**.

### 6.1. Java 17+ Lab with Embedded ActiveMQ Artemis: One Queue and One Topic

Goal: in a single application, create two workers competing for **one** Queue message, and two independent topic listeners each receiving **one copy** of an event. The example uses **Java 17+ compatible Spring Boot 3.x/4.x**, Spring Framework 6+/7+, and the `jakarta.jms` package. The embedded broker is for lab use only; production typically uses an external broker.

Create Maven project `com.example:queue-topic-demo` via Spring Initializr (https://start.spring.io/) with the **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`) dependency. Add inside `<dependencies>` in `pom.xml`:

~~~xml
<dependency>
  <groupId>org.apache.activemq</groupId>
  <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

If the project uses the Spring Boot parent/BOM, let Spring Boot manage the Artemis version. Do not pull legacy `javax.jms` Artemis clients to mix with the `jakarta.jms` stack.

Contents of `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=jobs.demo
spring.artemis.embedded.topics=events.demo
spring.artemis.embedded.persistent=false
~~~

File `src/main/java/com/example/queuetopicdemo/QueueTopicDemoApplication.java` (adjust project package accordingly):

~~~java
package com.example.queuetopicdemo;

import jakarta.jms.ConnectionFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class QueueTopicDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(QueueTopicDemoApplication.class, args);
    }

    // Two publishers share one ConnectionFactory but use different domains.
    @Bean("queuePublisher")
    JmsTemplate queuePublisher(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        return template;
    }

    @Bean("topicPublisher")
    JmsTemplate topicPublisher(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);
        return template;
    }

    @Bean("queueFactory")
    DefaultJmsListenerContainerFactory queueFactory(ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }

    @Bean("topicFactory")
    DefaultJmsListenerContainerFactory topicFactory(ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(true);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }

    @Bean
    ApplicationRunner publish(
            @Qualifier("queuePublisher") JmsTemplate queue,
            @Qualifier("topicPublisher") JmsTemplate topic) {
        return args -> {
            queue.convertAndSend("jobs.demo", "job-1001");
            topic.convertAndSend("events.demo", "order-paid-2001");
        };
    }

    @Component
    public static class WorkerA {
        @JmsListener(destination = "jobs.demo", containerFactory = "queueFactory")
        public void handle(String jobId) {
            System.out.println("QUEUE WorkerA: " + jobId);
        }
    }

    @Component
    public static class WorkerB {
        @JmsListener(destination = "jobs.demo", containerFactory = "queueFactory")
        public void handle(String jobId) {
            System.out.println("QUEUE WorkerB: " + jobId);
        }
    }

    @Component
    public static class AuditSubscriber {
        @JmsListener(destination = "events.demo", containerFactory = "topicFactory")
        public void onEvent(String eventId) {
            System.out.println("TOPIC Audit: " + eventId);
        }
    }

    @Component
    public static class EmailSubscriber {
        @JmsListener(destination = "events.demo", containerFactory = "topicFactory")
        public void onEvent(String eventId) {
            System.out.println("TOPIC Email: " + eventId);
        }
    }
}
~~~

Run from the project root containing Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

After the application starts and listeners are active, look for lines **like** the following in the log (alongside Spring/Artemis logs):

~~~text
QUEUE WorkerA: job-1001
TOPIC Audit: order-paid-2001
TOPIC Email: order-paid-2001
~~~

**Other valid output:** replacing the `QUEUE WorkerA` line with `QUEUE WorkerB`. In a healthy run, it is expected that **only one** of the two workers receives `job-1001`, while **both Audit and Email** receive `order-paid-2001` because each topic listener belongs to its own non-durable subscription. **The order of the three lines is not guaranteed** because listeners run asynchronously; operational errors or redeliveries can produce different logs. Do not use this example to prove "exactly once" in failure environments.

**Why does the experiment cleanly distinguish the two contracts?** `jobs.demo` has only one queue but two competing consumers. `events.demo` has two independent non-durable subscriptions (each listener is a subscriber), so an event published while both are listening fans out into two copies.

**Lab limitations:** Non-durable topics are not a production configuration if Audit/Email must not miss events during downtime. An embedded broker with `spring.artemis.embedded.persistent=false` must not be used to prove durability when the application/broker loses power. Destination creation permissions, persistent store configuration, broker addresses, and production policies depend on the real system.

### 6.2. Switching a Business Subscriber to Shared Durable

For a group that must process even across offline periods, use a dedicated factory (for example, `sharedDurableTopicFactory`) and a subscription with a **fixed name**. The snippet below is a **replacement/addition configuration fragment**, placed in an existing `@Configuration` or `@SpringBootApplication` class; import the corresponding classes:

~~~java
@Bean("sharedDurableTopicFactory")
DefaultJmsListenerContainerFactory sharedDurableTopicFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setSubscriptionShared(true);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-4");
    return factory;
}
~~~

And an example listener **for one group**:

~~~java
@JmsListener(
    destination = "orders.lifecycle.events",
    subscription = "billing-v1",
    containerFactory = "sharedDurableTopicFactory")
public void onOrderPaid(String payload) {
    // Parse/validate schema, check if eventId was already processed, update business state,
    // return normally after safe processing.
}
~~~

This is a **method fragment** placed inside a Spring-managed bean; not a standalone Java class. All replicas of Billing use the **same subscription name** `billing-v1` to share load. The Fulfillment group needs its own name `fulfillment-v1`; **do not share** `billing-v1` with Fulfillment. When using shared durable in modern Jakarta Messaging, do not arbitrarily assign each replica a different `clientId` because subscription identity may split into separate groups; check how the provider identifies and supports shared subscriptions. A durable subscription only collects eligible events from when **it was created**, without re-providing earlier historical events.

Once you customize a listener factory bean in a Spring Boot application, ensure Boot's useful defaults (converter, error handler, transaction manager, destination resolver...) are carried over if needed. With Boot, you can use a `DefaultJmsListenerContainerFactoryConfigurer` compatible with your project version to initialize default settings before overriding domain/subscription properties.

### 6.3. Do Not Confuse Queue/Topic When Destination Names Are Identical

The same string name `orders.events` does not mean a Queue and a Topic have the same semantics. JMS distinguishes destination objects as `jakarta.jms.Queue` vs. `jakarta.jms.Topic`. The broker may map names to internal addresses/routing in its own way; state **type + name + ownership** explicitly in the contract. When sending via `JmsTemplate.convertAndSend("orders.events", ...)`, the `pubSubDomain` configuration determines how the name is resolved; receivers must also use the right domain.

## 7. Correctness and Reliability Do Not Come from the Queue/Topic Name

### 7.1. Delivery Semantics and Business Outcome

Suppose a producer publishes a message. There are separate steps:

~~~text
Producer publishes -> Broker accepts -> Consumer receives -> Business processing
      -> DB/side-effect completes -> ack/commit message
~~~

Queue guarantees one consumer is chosen for a delivery (not one permanent business execution). Topic guarantees each eligible subscription gets its own copy (not every process receives it). When a consumer dies at any point, reprocessing can occur or messages can be lost if misconfigured. Test under fault scenarios rather than inferring solely from Queue/Topic.

### 7.2. Per-Group Idempotency

- **Command Queue:** store `commandId`/business key and job status; if the same command is redelivered, the worker does not produce a second side effect.
- **Event Topic:** each group maintains a processed-event table keyed by `(consumerGroup, eventId)` or a separate store. Billing finishing processing does not mean Audit has also finished.
- **External side effects:** sending email, charging payments, calling external APIs may not sit in the same transaction as ack; use the recipient's idempotency key, outbox, or compensating actions.
- **At-most-once / at-least-once / exactly-once:** these are delivery/processing goals that require full context. The phrase "exactly-once" at the protocol level is insufficient to prove business effects happen only once.

### 7.3. Processing Order

If the requirement is "all changes for the same `accountId` in order", specify at which level ordering applies: whole topic, per queue, single consumer, or per business key. Concurrency, delivery retries, message selectors, priority, and TTL can affect observed ordering. Techniques for keeping messages ordered by key (such as broker-specific message groups) or partitioning architectures can be used, but provider support, dynamism, and failover behavior must be verified. Do not advertise "Topic loses order while Queue is always strictly FIFO".

### 7.4. Independent Failures and DLQs

In a Topic with multiple subscriptions, Billing can succeed while Email fails and gets retried. Redelivery policies, dead-letter addresses/queues, and retry counts are typically controlled by the broker and not fully standardized by Jakarta Messaging. Monitor **per subscription**, set backlog limits, and configure alerts. With a Queue, one worker group consumes the backlog; a poison message can tie up resources if retries are unbounded.

### 7.5. Scaling Across Multiple Services

Topics reduce the producer's need to know the list of subscribers, yet **a contract still exists**: schema, semantics, delivery guarantees, backward compatibility, ACLs, and ownership. Adding a new subscriber does not mean every old payload version will automatically be compatible. When adding a new business obligation, determine **from what point in time** the subscriber must begin receiving; if catching up on the past is required, backfill from another data source or a verified infrastructure replay feature.

## 8. Contract Tests Before Going to Production

| Test | Expectation If Properly Designed |
| --- | --- |
| Send 10 commands to a queue with 3 workers | Total **logical completions** is 10 with no errors; distribution per worker is not fixed |
| Send 10 events to a topic with 3 independent online subscriptions | Each subscription receives 10 eligible copies; 30 total processings across 3 groups |
| Scale Billing from 1 to 3 replicas using **shared durable** | The Billing group still gets 10 logical copies for 10 events, not multiplying to 30 |
| Close all non-durable consumers then publish | With no existing subscription, messages are not accumulated for later delivery |
| Create durable subscription, close consumer, then publish and reconnect | Subscription can receive valid backlog, provided TTL/retention/capacity and broker config permit |
| Publish before creating durable subscription | New subscriber **does not automatically receive the entire past** |
| Consumer crashes after side effect but before ack | Message may be redelivered; idempotency protects business state |
| One topic subscription fails, another subscription is healthy | The failing group's copy can retry/DLQ independently; other groups can still process their own copies |
| Enable concurrency and test same business key | Evaluate actual ordering instead of inferring global FIFO from destination name |
| Message expires TTL, backlog fills, broker restarts | Verify expiration/retention/persistence per configuration rather than assuming unconditionally |

When testing, record **published message count**, **delivery attempt count**, **successful business outcomes**, **DLQ count**, and backlog. The first three numbers differ when retries/redeliveries happen; do not merely count log lines to conclude business correctness.

## 9. Common Queue/Topic Selection Mistakes

1. **Three independent groups listening on one Queue:** only one group receives each message; replace with Topic + separate subscriptions or a contracted fan-out router.
2. **Each replica gets an independent Topic subscription:** every replica processes all events; use a shared subscription for the same group if load sharing is desired.
3. **Using a non-durable Topic for a business flow that cannot lose events while offline:** create durable subscriptions before publishing; verify retention and operations.
4. **Assuming a new durable subscriber automatically gets history:** durable only retains from when the subscription existed, not replacing an event log.
5. **Changing `spring.jms.pub-sub-domain` while forgetting the receiving factory:** producer sends to Topic while listener still listens on Queue or vice versa. Configure both explicitly.
6. **Using the same subscription name across two business groups:** they compete for shares of the same subscription instead of receiving two independent copies.
7. **Believing "one message delivered to one consumer" = exactly-once:** redeliveries happen; you must be idempotent and control transaction boundaries.
8. **Increasing concurrency and then demanding globally ordered processing:** you must explicitly define ordering constraints and enforcement mechanisms.
9. **Omitting TTL/retry/DLQ/monitoring:** a poison message or offline subscription can make backlog grow without bound.
10. **Changing schema without notice:** independent subscribers have separate deployment schedules; contract versioning and compatibility testing are required.
11. **Leaving orphaned durable subscriptions with no owner:** backlog/quotas accumulate when a service stops permanently; subscription creation/deletion lifecycle and runbooks are needed.
12. **Treating JMS as an API with a built-in broker:** Queue/Topic are provider abstractions; `ConnectionFactory`, compatible clients, destinations, and a running broker are required.

## 10. Decision Checklist for Architecture Reviews

Before finalizing a design, reviewers should require clear answers to all of the following:

- **Meaning:** Is the message a command, event, or notification? What causes it to be published?
- **Responsibility:** How many business groups must complete processing? How many copies **per group**?
- **Scaling:** Are replicas competing consumers on a Queue or members of a shared Topic subscription?
- **Downtime:** Can misses be tolerated when all consumers are offline? Who creates and manages durable subscriptions?
- **Data:** How are schema version, event/command ID, business key, and private data handled?
- **Reliability:** Specific ack/transaction, idempotency, redelivery/retry/DLQ, and timeout/expiration policies?
- **Ordering:** Is per-key ordering required? How do the broker and current configuration support it?
- **Operations:** Are backlog, message age, consumer health, error rates, and subscription cleanup monitored?
- **History:** Is backfill/replay of events published before group registration needed? What is the historical data source?

If the answer is "one responsibility, multiple workers taking turns", choosing Queue is usually right. If the answer is "multiple independent responsibilities all need to know about the same event", choosing Topic with separate per-group subscriptions is usually right. Finalize durability, shared subscription, idempotency, and failure policies **before** considering the contract ready for implementation.

## 11. Self-Check Exercises

1. An `OrderCancelled` event needs to be processed by Warehouse and RefundService, where RefundService runs 4 replicas. Draw a Topic diagram with **two subscriptions** and identify the subscription type for RefundService.
2. A Queue `email.send` has 5 workers. Send 100 messages; one worker crashes after sending an email but before ack. Explain why the total number of emails sent can exceed 100, and state an idempotency solution.
3. A dashboard stops for 30 minutes and then needs to view all telemetry. Explain why a non-durable topic does not satisfy this, and why enabling durable **after the 30 minutes** also does not automatically recover the past.
4. With the Java snippet in section 6, add one Queue message and one Topic message. Predict the **set** of consumers that receive them; do not predict log order.
5. Propose a contract for `PaymentCaptured` including subscription identity, offline requirements, `eventId`, retention, duplicate handling, retries, and DLQ. Indicate which parts are managed by Spring code and which must be configured on the broker.

## Reference Documentation for Lookup

- Jakarta Messaging 3.1, **Messaging domains**, queue semantics, topic subscription, durable/shared: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework, **JMS integration**: https://docs.spring.io/spring-framework/reference/integration/jms.html
- Spring Framework, **Annotation-driven listener endpoints**: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework, **JMS namespace/destination types**: https://docs.spring.io/spring-framework/reference/integration/jms/namespace.html
- Spring Boot, **JMS and Artemis auto-configuration**: https://docs.spring.io/spring-boot/reference/messaging/jms.html
- Spring guide, **Messaging with JMS**: https://spring.io/guides/gs/messaging-jms/
