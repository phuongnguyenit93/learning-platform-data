# PERSISTENT and NON_PERSISTENT Delivery Modes in Spring JMS

> **Topic:** Message delivery quality with Jakarta Messaging (JMS) and Spring Framework `JmsTemplate`.  
> **Goal:** Choose the right `DeliveryMode.PERSISTENT` or `DeliveryMode.NON_PERSISTENT` based on message loss cost; configure QoS so it actually takes effect; distinguish message durability from queue/topic, durable subscription, retention lifetime, ACK, transaction, and business correctness.

## 1. What Are the Two Delivery Modes?

Jakarta Messaging defines **two values** of `jakarta.jms.DeliveryMode`:

~~~java
DeliveryMode.PERSISTENT      // int 2
DeliveryMode.NON_PERSISTENT  // int 1
~~~

`PERSISTENT` instructs the JMS provider to take extra steps to **protect messages against provider/broker failures**, typically including writing data to durable storage. `NON_PERSISTENT` has lower overhead because the provider is not required to write messages to stable storage and **may lose messages when the provider fails**.

Key points to understand right away:

- The two modes are **delivery quality policies for a message when sent**, not message types (they work with `TextMessage`, `BytesMessage`, `ObjectMessage`, etc.) and not destination types.
- They **do not determine** "one consumer or multiple consumers" — that is Queue/Topic and subscription.
- They **do not by themselves determine** how long a message stays alive — that is TTL/expiration, retention, broker capacity, and acknowledgement behavior.
- They **do not confirm** that a business step such as writing to a DB, calling a payment API, or sending an email has completed.
- They **do not replace** duplicate handling, transactions, retries, and DLQ.
- The default delivery mode of a JMS producer/message is typically **`PERSISTENT`**, though the configuration of the JMS provider, producer, or JmsTemplate can change or override the default.

**Selection rule:** If losing a message causes business damage or an unrecoverable state, choose `PERSISTENT` together with appropriate retention/transaction mechanisms. If a message is transient data that can be missed or regenerated, `NON_PERSISTENT` is an option worth considering to reduce overhead.

## 2. Core Comparison Table

| Aspect | `PERSISTENT` | `NON_PERSISTENT` |
| --- | --- | --- |
| Constant value | `DeliveryMode.PERSISTENT = 2` | `DeliveryMode.NON_PERSISTENT = 1` |
| Producer intent | Prioritize durability across provider failures | Prioritize performance if losing some messages is acceptable |
| Written to stable storage | Requests the provider to use appropriate durable storage techniques to withstand provider failures | Not required to write to stable storage |
| When broker/process crashes | Higher level of protection **if the broker actually configures persistence/retention that meets requirements** | Undelivered or unprocessed messages may be lost |
| Resource overhead | Usually adds journal/disk I/O, synchronization, and replication depending on the broker | Usually less durable-write overhead |
| Can be sent to a Queue? | Yes | Yes |
| Can be published to a Topic? | Yes | Yes |
| Automatically kept for offline consumers? | Queue/durable subscription and retention must match; does not auto-create subscriptions | Also depends on queue/subscription; no guarantee of surviving provider failure |
| Does TTL/expiration apply? | Yes | Yes |
| What happens after successful ACK/commit? | Provider may remove the message from the backlog per the receive contract | Same |
| Guarantees exactly-once database side effects? | **No** | **No** |
| Can both be used on the same destination? | Yes | Yes |
| Need to test broker restart/persistence policy? | **Yes** | **Yes**, to observe actual risk rather than guessing |

**Terminology note:** The Jakarta Messaging specification describes provider-level delivery guarantees using the terms "once-and-only-once" for persistent and "at-most-once" for non-persistent with respect to provider failures. This is a **JMS-layer transport guarantee conditional on retention policy**, **not equivalent** to business execution exactly-once. A message that has not been ACKed, or whose transaction was rolled back, may be **redelivered** for processing according to valid policy.

## 3. What the Specification Actually Guarantees — and Its Limits

### 3.1. Definition at the JMS Provider Layer

The *Message delivery mode* section of Jakarta Messaging 3.1 specifies:

- **`NON_PERSISTENT`:** the provider is not required to write stably; messages may be lost when the provider fails. Within the scope of provider delivery guarantees, this is the *at-most-once* option.
- **`PERSISTENT`:** the provider must take extra protective measures so messages are not lost due to typical provider failures. The specification calls this *once-and-only-once* at the transport layer, provided the destination has an appropriate retention policy.
- **Neither mode** automatically guarantees that every intended subscriber already exists, that the message has not expired, that the client completed side effects, that the database committed, or that the broker has infinite capacity.
- Providers may enforce resource limits; full storage, broker policies, severe storage media failures, or incidents outside the configured scope may prevent the guarantee from being met.

Do not write in design documents that "`PERSISTENT` always survives every failure" or "`NON_PERSISTENT` always disappears after a restart." Both conclusions are overstatements.

### 3.2. Three Layers Commonly Conflated

~~~text
PRODUCER                                  BROKER                            CONSUMER
   |                                         |                                  |
   | send(message, deliveryMode)             |                                  |
   +---------------------------------------->|                                  |
   |                                         | storage / retention / routing    |
   |                                         +--------------------------------->|
   |                                         |                                  | process DB/API
   |                                         |<------- ACK / COMMIT -------------+
   |                                         |  or rollback / redelivery        |
   v                                         v                                  v

Layer A: transport/send durability       Layer B: retention/destination        Layer C: business outcome
         (delivery mode)                 + subscription + TTL                  + ACK/transactions
~~~

- **Layer A — Delivery mode:** what level of durability the producer requests the provider to use when transporting and storing the message.
- **Layer B — Retention:** how long the destination keeps received messages; a queue can wait for a consumer, a durable topic subscription can keep a backlog, and TTL can remove messages.
- **Layer C — Completion:** did the consumer finish business work before ACK/commit? If it did not finish or commit failed, how do redelivery and idempotency handle it?

To build a reliable flow, you must design **all three layers**, not merely set the `PERSISTENT` mode.

### 3.3. Situations Where PERSISTENT Still Cannot Save You

1. **Non-durable topic with no subscriber at publish time:** messages do not accumulate for a subscriber that does not exist yet; sending persistent does not turn non-durable into durable.
2. **TTL has expired:** a message eligible for expiration is discarded according to semantics/configuration, even if initially persistent.
3. **ACK before finishing processing:** the consumer acknowledges the message and then the app crashes while writing to the DB; the broker believes it is done, so there is no message left to redeliver.
4. **Broker configured without persistence:** a lab environment may accept a mode 2 header without actually preserving a journal across restarts.
5. **Retention/resource policy:** capacity limits, purges, DLQs, administrative deletes, or storage failures can cause messages to no longer exist in the queue.
6. **Producer has not actually completed send/commit:** an asynchronous send call or a send inside an uncommitted transaction does not mean the message has been durably accepted.
7. **Publisher/consumer not atomic with the DB:** persistence only protects messages the broker has received; it does not create an atomic transaction between the data store and the broker.

Therefore, tests must verify **when send succeeds, transaction commit, broker restart, subscription existence, TTL, and ACK**, rather than only checking a single header.

## 4. Delivery Mode Is Not a Durable Subscription

In JMS there are two concepts that carry the word "durable" (or relate to durability) along different axes:

| Concept | Scope | Question Answered |
| --- | --- | --- |
| **`DeliveryMode.PERSISTENT`** | **Per message** when sent by the producer | "To what extent must the provider protect the message when a failure occurs?" |
| **Durable Topic Subscription** | **Subscription group** on a Topic | "When a consumer of the group is offline, does the subscription retain messages published after the subscription was created?" |

For example, a Topic `orders.paid.events` has two consumer groups:

~~~text
                 Topic: orders.paid.events
                /                         \
   billing-v1 (durable)                live-ui (non-durable)
       |                                    |
    Billing                              Dashboard
       |                                    |
   offline still keeps                  offline may
   valid backlog                        miss events
~~~

- If the producer sends **PERSISTENT** but the `live-ui` group is **non-durable** and went offline, that group will not automatically receive missed messages upon startup.
- If the `billing-v1` group is a **pre-created durable subscription**, the broker can keep a backlog for Billing while offline per retention/TTL; persistent delivery mode increases protection across broker failures.
- If the producer uses **NON_PERSISTENT** to a durable subscription, that group can still receive messages while online and may see a backlog while offline on a running broker, but cannot rely on surviving a broker failure.
- **Creating a durable subscription after events were already published** does not by default allow replaying past history.
- A subscription must also have an appropriate identity, shared/unshared policy, and broker support when running multiple replicas.

**Combination to remember:** "persistent message + durable subscription + broker persistence + proper retention + transacted/ack consumer" increases reliability, yet **still** requires idempotency and business reconciliation.

## 5. Queue and Topic: Contract-Driven Mode Selection Examples

### Scenario A — Work Queue That Must Not Drop Jobs

Checkout emits a `GenerateInvoice(invoiceId)` command for the InvoiceWorker group; workers may be offline during a deployment.

**Usually appropriate choice:**
- Dedicated queue for InvoiceWorker.
- `DeliveryMode.PERSISTENT`.
- Proper broker storage, quota, retention, and backup/recovery.
- Consumer uses a transacted session or ACKs after safe processing.
- Idempotency key on `invoiceId`; retries and DLQ in place.

Reason: if the broker crashes and loses the command, the invoice might never be created. Note that if the checkout DB commits and then the JVM crashes **before sending** the command, persistent mode does not solve that: use transactional outbox.

### Scenario B — Frequent Telemetry Where Dropping One Sample Is Acceptable

A sensor publishes temperature every few seconds; the dashboard only displays current readings and can recover from the next measurement.

**Potentially appropriate choice:**
- `DeliveryMode.NON_PERSISTENT`.
- Short TTL to avoid displaying stale data.
- Non-durable topic subscriber if only live data is needed.
- Metrics measuring packet loss and data freshness; do not use this if missing a single sample loses a safety alarm.

Reason: the cost of durably writing every sample may not be justified, provided you **prove** the app truly tolerates loss; safety alerting systems may require a different design.

### Scenario C — Payment Event for Multiple Groups

Payment service emits `PaymentCaptured`; Fulfillment, Accounting, and Fraud must each process it independently, including during deployments.

**Usually appropriate choice:** Topic, **one durable subscription per group**, `PERSISTENT` events, broker HA/persistence, idempotent consumers per group, schema versioning, and separate DLQs. Do not treat `PERSISTENT` as a "send to every process" command; the subscription topology determines who receives a copy.

### Scenario D — Regenerable User Notifications

Notification service sends "new email arrived" to a web client; if the client is offline, the next page load fetches the list from the database.

`NON_PERSISTENT` can be used for live notifications because **the source of truth is the DB**. However, an `EmailReceived` event used to update audit/billing may need to be persistent on a separate flow. The decision must be based on each *message's* contract, rather than setting a single unconditional mode across the entire system.

### Scenario E — Operational Systems That Must Preserve Ordering

If a destination mixes persistent and non-persistent messages, **do not assume strict ordering between the two modes**. The specification allows a `NON_PERSISTENT` message sent later to be received before a `PERSISTENT` message sent earlier, while other factors such as priority also affect delivery. For ordering-sensitive workflows, define an explicit ordering contract, control concurrency/producer sessions, and do not assume mixing modes preserves global FIFO.

## 6. Jakarta Messaging API: Setting the Mode on the Producer

### 6.1. Classic API — MessageProducer

For `jakarta.jms.MessageProducer`:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;

// Java 17+ snippet; session is already created and destination is already defined.
MessageProducer producer = session.createProducer(destination);

// Subsequent messages will use NON_PERSISTENT unless overridden on send:
producer.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
Message msg = session.createTextMessage("sample");
producer.send(msg);
~~~

This is a **code snippet** requiring `destination`, `session`, a broker/ConnectionFactory, and lifecycle cleanup. Do not copy it as a standalone Java file.

You can set the mode **per send** via the classic API overload:

~~~java
producer.send(
    msg,
    DeliveryMode.PERSISTENT,
    Message.DEFAULT_PRIORITY,
    Message.DEFAULT_TIME_TO_LIVE);
~~~

The four-argument overload overrides the delivery mode, priority, and TTL **for that specific send**. Do not share the same `MessageProducer` unsafely across threads and mutate its mode per request; use Spring/template utilities or properly lifecycle-managed producers.

### 6.2. Simplified API — JMSContext/JMSProducer

Java 17+ with Jakarta Messaging 3.1, with a provider supporting JMSContext:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

public final class DirectDeliveryModeExample {
    private DirectDeliveryModeExample() {}

    public static void sendStatus(
            ConnectionFactory factory, String payload) {
        try (JMSContext context = factory.createContext()) {
            Queue queue = context.createQueue("telemetry.live");
            context.createProducer()
                    .setDeliveryMode(DeliveryMode.NON_PERSISTENT)
                    .send(queue, payload);
        }
    }
}
~~~

Save as `DirectDeliveryModeExample.java`. This is a **valid Java 17+ class when Jakarta Messaging and a client/provider are on the classpath**; it has no `main` method so it does not run standalone, and requires a configured `ConnectionFactory` and a running broker. `JMSContext` is closed upon exiting try-with-resources; `JMSProducer` has no separate `close()`.

To switch the request to persistent, replace `DeliveryMode.NON_PERSISTENT` with `DeliveryMode.PERSISTENT`; changing a constant does not automatically configure storage, DLQ, or retention.

### 6.3. Do Not Edit the Header Expecting to Change the Send Policy

Calls like:

~~~java
message.setJMSDeliveryMode(DeliveryMode.PERSISTENT);
~~~

only affect the header of a `Message` object before send; **the provider ignores the client-assigned header value at send time and replaces it with the mode of the send/producer**. The right approach is `producer.setDeliveryMode(...)`, the `send(..., deliveryMode, priority, ttl)` overload, or proper QoS configuration in Spring.

After send/receive, `message.getJMSDeliveryMode()` reports the mode header assigned by the provider; it is for **observation**, not a way to configure broker policy when a consumer reads the message.

### 6.4. Other Defaults

In addition to delivery mode, a `MessageProducer` has:

- Default priority is typically **4** (0 lowest, 9 highest).
- Default TTL is typically **0** (no expiration time set by the client).
- Default delivery delay is **0**.
- Delivery mode, TTL, and priority can be configured directly on the producer or via the send overload.

Default persistent **does not mean** "never expires" if the broker enforces server-side expiry/retention policies.

## 7. Spring JmsTemplate: The Trap of Calling setDeliveryMode Without Enabling QoS

In Spring Framework 6.x, `org.springframework.jms.core.JmsTemplate` provides the setters:

~~~java
jmsTemplate.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
jmsTemplate.setDeliveryPersistent(false);
jmsTemplate.setExplicitQosEnabled(true);
~~~

**The crucial part:** calling `setDeliveryMode(...)` or `setDeliveryPersistent(false)` **alone is not enough**. According to Spring's Javadoc, only when `isExplicitQosEnabled()` is `true` does the template pass explicit QoS properties into the send call. Otherwise, the provider may apply the default/administrative delivery mode.

### 7.1. Example Configuring Two Separate JmsTemplates

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class DeliveryModeConfiguration {

    @Bean("persistentJmsTemplate")
    JmsTemplate persistentJmsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        return template;
    }

    @Bean("volatileJmsTemplate")
    JmsTemplate volatileJmsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
        return template;
    }
}
~~~

This is a complete Spring class if the project has the appropriate dependencies. You can inject them into a service using `@Qualifier("persistentJmsTemplate")` or `@Qualifier("volatileJmsTemplate")`. Both templates share the Spring-managed `ConnectionFactory`, while messages emitted by each template request different modes. You do not need to manually close `Session`/`Connection` inside `convertAndSend`.

**Important note:** Enabling `explicitQosEnabled` also makes the template explicitly send **priority** and **TTL** using the template's configured values, rather than using the broker administrator's defaults. Do not enable it without checking the expected priority/TTL. If your system relies on broker-side QoS policies, verify and decide explicitly.

### 7.2. Sending Messages with Each Mode

~~~java
// Code snippet inside a Spring @Service:
persistentJmsTemplate.convertAndSend(
        "invoices.commands", "invoice-2026-001");

volatileJmsTemplate.convertAndSend(
        "metrics.live", "cpu=63");
~~~

These are **two messages to two different destinations**, not two sends of the same job. With `SimpleMessageConverter`, `String` data becomes a `TextMessage`, but **body type is independent of delivery mode**.

### 7.3. Spring Boot 3.5 Auto-Configured JmsTemplate

In Spring Boot 3.5, properties that configure the Boot-managed template bean include:

~~~properties
# Example for a Spring Boot auto-configured JmsTemplate:
spring.jms.template.delivery-mode=non_persistent
spring.jms.template.receive-timeout=2s
~~~

In Boot 3.5, setting `spring.jms.template.delivery-mode` causes Boot to **automatically enable explicit QoS** on the auto-configured `JmsTemplate`. If you configure a custom `JmsTemplate` bean via `new` or a custom factory, Boot's properties **do not automatically** affect that bean; you must configure it directly or use a version-compatible configurer.

**Do not set a global non-persistent mode** for the entire app if the same app emits both critical jobs and droppable metrics. Use two named templates with distinct contracts, or a send operation configured with per-message QoS via the appropriate API.

### 7.4. Where Is the Setting Applied?

`JmsTemplate.convertAndSend(...)`:
1. Obtains a Connection/Session from the factory.
2. Converts the Java object via `MessageConverter` into a JMS `Message`.
3. Creates/borrows a `MessageProducer`.
4. **Sends** with explicit QoS if `explicitQosEnabled=true`; if false, uses the producer's default send.
5. Performs cleanup/transaction boundaries per Spring/broker configuration.

This lets you keep the message schema unchanged and vary QoS by the criticality of each workload without manually managing low-level JMS details.

## 8. Spring Boot 3.5 + Artemis Lab: Verifying the Actually Received JMSDeliveryMode

This lab proves that the **`JMSDeliveryMode` header was sent properly**. It does **not** prove that persistent messages survive a restart, because the embedded broker beneath is configured **not to store persistent data** and shuts down with the app. The real durability test is in Section 9.

### 8.1. Project Setup

Create a project at https://start.spring.io/ with:

- Project: Maven / Java.
- Spring Boot **3.5.x**, Java **17**.
- Group `com.example`; artifact `delivery-mode-demo`; package `com.example.deliverymodedemo`.
- Dependency **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).

Add to `pom.xml` (using Spring Boot's parent/BOM for version management):

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=delivery-mode-demo
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=qos.persisted,qos.volatile
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

Two independent demo queues keep the lab free of competing consumers or selectors. `persistent=false` **ensures the lab does not use durable storage**, to illustrate that **a mode 2 header alone is insufficient to verify broker durability**.

### 8.2. Complete Java Class

Create `src/main/java/com/example/deliverymodedemo/DeliveryModeDemoApplication.java`:

~~~java
package com.example.deliverymodedemo;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class DeliveryModeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DeliveryModeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner compareDeliveryModes(ConnectionFactory factory) {
        return args -> {
            JmsTemplate durableSender = createSender(
                    factory, DeliveryMode.PERSISTENT);
            JmsTemplate fastSender = createSender(
                    factory, DeliveryMode.NON_PERSISTENT);

            JmsTemplate receiver = new JmsTemplate(factory);
            receiver.setReceiveTimeout(2_000L);

            durableSender.convertAndSend("qos.persisted", "invoice-42");
            fastSender.convertAndSend("qos.volatile", "temperature-24");

            Message durable = receiver.receive("qos.persisted");
            Message fast = receiver.receive("qos.volatile");

            if (!(durable instanceof TextMessage durableText)) {
                throw new IllegalStateException(
                        "Missing persistent TextMessage");
            }
            if (!(fast instanceof TextMessage fastText)) {
                throw new IllegalStateException(
                        "Missing non-persistent TextMessage");
            }

            System.out.println("PERSISTENT mode="
                    + durableText.getJMSDeliveryMode()
                    + " body=" + durableText.getText());
            System.out.println("NON_PERSISTENT mode="
                    + fastText.getJMSDeliveryMode()
                    + " body=" + fastText.getText());
        };
    }

    private static JmsTemplate createSender(
            ConnectionFactory factory, int mode) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setPubSubDomain(false);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(mode);
        return template;
    }
}
~~~

This is a complete Java 17+ file; the class requires Spring Boot 3.5, Spring JMS, Jakarta Messaging, and embedded Artemis as in Section 8.1. `ApplicationRunner` has no `@JmsListener`, so `@EnableJms` is not needed. With this configuration, `TextMessage.getText()` and `getJMSDeliveryMode()` can be read after `JmsTemplate.receive` returns.

Run from the project directory:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Ignoring Spring/Artemis startup logs, **expected business stdout**:

~~~text
PERSISTENT mode=2 body=invoice-42
NON_PERSISTENT mode=1 body=temperature-24
~~~

These two lines appear in order inside an `ApplicationRunner` if the embedded broker starts, both queues are initially empty, and there are no competing consumers. If the template does not enable `explicitQosEnabled`, the send from `fastSender` **may** use the default mode 2 instead of mode 1, demonstrating that calling the setter alone is not enough.

**What the lab verifies:** the mode attached to both messages by the JMS provider and read back accurately. **What the lab does not verify:** load handling, fsync latency, provider failover, broker restart, non-persistent loss, or business exactly-once. Do not infer storage quality from log lines.

### 8.3. Why Not Use the Same Queue to Benchmark "Which Is Faster"?

If you send both messages to the same queue with competing consumers, ordering/overhead cannot be determined from a single small run. Performance testing requires uniform load, separate groups, and measuring throughput/latency/storage on a **real broker** with sufficient samples; `PERSISTENT` is typically more expensive, but no single universal speed ratio can be stated across all providers.

## 9. Real Durability Lab: External Broker, Restart, and Retention

To verify post-restart behavior, **do not use** an embedded broker that shuts down with the application. Prepare a **standalone** Artemis broker with journal/persistence enabled, a data directory preserved across restarts, durable queues, and appropriate publish/consume permissions.

Test procedure in an isolated environment:

1. Create two separate queues `test.persisted` and `test.volatile`; have no consumers receiving during sends. Set retention/TTL high enough and disable auto-delete policies so results are not skewed.
2. Send the same number of uniquely ID'd messages to the first queue with `PERSISTENT` mode and the second queue with `NON_PERSISTENT` mode; log successful send results and transaction commits if applicable.
3. Read broker metrics to confirm message count and durable message count before restart. Preserve the storage volume and configuration.
4. Stop the broker in a **controlled** manner; start it back up. Check how many messages remain in both queues. Then repeat the experiment in staging with a **process crash** (not production) if infrastructure and operational permissions allow.
5. Start consumers with proper ACK/transactions, reconcile received IDs, expired messages, DLQ, and backlog. Record that delivery attempt count differs from successful business outcome count.
6. Repeat with an HA/replicated broker if production uses failover; do not extrapolate from a single broker to a cluster.

**How expectations must be stated:** In a properly configured durable broker, un-acked/unexpired persistent messages are expected to survive provider failures covered by the guarantee. Non-persistent messages **may** not survive a crash/restart, though some providers/policies may retain them; **observing non-persistent messages survive once does not create a standard guarantee**.

If the broker is running with `persistence-enabled=false`, both modes may lose data on restart — that is an **environment configuration limitation**, not evidence that the two `DeliveryMode` constants are equivalent in JMS.

## 10. Spring Boot/Artemis: System Factors Affecting Durability

### 10.1. Journal, Store, and Data Synchronization

Apache ActiveMQ Artemis has a journal storing messages and bindings, along with other storage options. When configured for persistence, the broker typically writes critical state to stable storage. However, observed durability also depends on:

- Is the storage volume preserved across restarts/Pod recreations?
- How are journaling/file sync/replication enabled and tuned?
- Does disk flush/batching affect send/commit latency?
- The broker uses paging under high load; paging-to-disk **is not equivalent** to a durable guarantee for every non-persistent message.
- Is there HA/failover or a single broker? Node, volume, and network split failures have different policies.
- Does the destination have an expiry address/DLQ, max-size, address-full-policy, or auto-delete?
- Was the transaction committed before the producer declared the send a business success?

**PERSISTENT is a delivery quality request**, not an assertion that any given broker already has full persistent disks/replicas. Check server configuration and test under fault scenarios.

### 10.2. NON_PERSISTENT Does Not Mean Never Written to Disk

Providers may page, buffer, snapshot, or temporarily store data according to policy. Therefore, non-persistent data **can** appear in storage under specific circumstances, yet it receives none of the durability guarantees of persistent mode. Do not try to "verify" it merely by checking that no new journal files appeared.

### 10.3. Durable Write Does Not Mean Consumer ACK

A message sent persistently by a producer and safely stored on the broker can still be:
- Not yet received by any consumer.
- Received, but not yet ACKed by the consumer.
- Waiting for retry because the consumer rolled back.
- Expired past TTL or moved to expiry/DLQ.
- Successfully ACKed, yet the business side effect failed due to transaction design.

That is why delivery/ack status and business status must be monitored independently.

## 11. Acknowledgement, Transactions, Redelivery, and "Exactly Once"

### 11.1. Illustrating the Failure Window

~~~text
Producer ----- send(PERSISTENT) -----> Broker stores message
                                          |
                                          v
                                  Consumer receives
                                          |
                                    DB COMMIT OK
                                          |
                                  [JVM CRASH HERE]
                                          |
                               JMS ACK not performed yet
                                          |
                               Broker may REDELIVER
                                          |
                                  DB processed again?
~~~

If the message has not been ACKed/committed at the broker, redelivery after a restart/failover is behavior the design must accept. Therefore two concepts must be separated:

- **Provider-level delivery guarantee:** the provider is responsible for transporting and delivering the message per the JMS contract, subject to failure and retention conditions.
- **Business exactly once:** an effect such as "debit 100,000 VND" or "send one email" happens only once. This is **not guaranteed** by `PERSISTENT` alone.

The right approach in systems requiring reliability is combining persistent publishing, properly timed transactions/ACKs, **idempotent consumers**, and controlled side effects.

### 11.2. Transacted JMS Session

In a Spring listener:

~~~java
// Bean method snippet of a @Configuration:
@Bean("businessListenerFactory")
DefaultJmsListenerContainerFactory businessListenerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Requires imports for `jakarta.jms.ConnectionFactory`, Spring `@Bean`, and `DefaultJmsListenerContainerFactory`. This is not a complete class file. With `sessionTransacted=true`, when the listener finishes successfully, the session transaction is committed per the container lifecycle; if the handler throws an exception, rollback may cause the message to be redelivered per provider policy. If the handler writes to a DB outside the same JMS transaction, **a JMS local transaction does not automatically encompass the DB transaction**.

To minimize duplicate side effects:
- Use an immutable `eventId`/`commandId`/business key.
- Store processed state in an inbox/dedup table with a unique constraint.
- Only trigger side effects when the key has not been processed; define the transactional boundary with the DB.
- If publishing after a DB commit, use a transactional outbox to avoid the "DB has data but message never sent" failure.
- Implement bounded retries, backoff, DLQ, and replay/reconciliation procedures.
- Design consumers to tolerate multiple delivery attempts.

### 11.3. PERSISTENT Cannot Keep Messages If the Consumer ACKs Early

If a listener acknowledges before business work succeeds, the broker may remove the message from the backlog. If the code then fails, the message will not come back on its own. Identify the **ack mode** and **listener container type**; especially with `AUTO_ACKNOWLEDGE`, behavior between the direct API and a Spring listener container can differ. For critical workloads, a transacted session is usually a safer starting point.

### 11.4. Producer Commit Matters Too

If a producer sends a persistent message inside a local JMS transaction, the application must `commit()` before considering the message published. Closing an uncommitted session rolls back, even if the delivery mode is persistent. When both writing to a database and sending to JMS, do not assume both operations commit atomically; use an outbox or a validated coordinated transaction solution.

## 12. TTL, Expiration, Priority, and Ordering When Mixing Modes

### 12.1. TTL Can "Override" Persistence

`setTimeToLive(10_000)` means the message can expire roughly 10 seconds after send time, per `JMSExpiration` rules. A persistent message **is not an object stored forever**. A queue whose consumer is offline for 30 minutes with a 10-second TTL is under no obligation to deliver expired messages when the consumer returns.

~~~java
// Configuration snippet; setters take effect when explicit QoS is enabled.
jmsTemplate.setExplicitQosEnabled(true);
jmsTemplate.setDeliveryMode(DeliveryMode.PERSISTENT);
jmsTemplate.setTimeToLive(10_000L);
jmsTemplate.setPriority(4);
~~~

Remember that enabling explicit QoS sends **all three** parameters—priority, TTL, and mode—using the template's values, which can override admin defaults. TTL should result from business SLA/retention, not a number copied from a tutorial.

### 12.2. Delivery Delay Is a Separate Concern

`deliveryDelay` indicates the earliest time the provider may deliver a message to a consumer; it does not guarantee a message appears from a non-existent past, nor is it synonymous with retention. If you set a 30-second delay but a 10-second TTL, verify timestamp/expiry interactions and broker policy rather than assuming every subscriber will receive it.

### 12.3. Priority and Mixing Modes Can Affect Ordering

Within the same destination, among messages with different priorities, delivery times, or modes, JMS does not promise strict FIFO. In particular, **order-sensitive workflows** should not rely on "I sent persistent first and non-persistent second" to infer they will certainly be received in that exact order.

If ordering is required:
- Define the scope by `accountId`/`orderId`, not merely by queue name.
- Restrict concurrency or use message grouping/partitioning that the broker genuinely supports.
- Avoid mixing modes with different semantics inside the same ordering-dependent business flow.
- Test failover, rollback/redelivery, and priority.

### 12.4. JMS Selectors Can Inspect Delivery Mode

JMS selectors handle `JMSDeliveryMode` as a string:

~~~sql
JMSDeliveryMode = 'PERSISTENT'
~~~

This is JMS selector syntax, not a DB SQL query. A consumer can filter by delivery mode, but **selectors do not replace broker ACLs or message contract definitions**. If you want to route by business type, it is usually better to set an application property like `kind` or use dedicated destinations.

## 13. Performance: Do Not Trade Guarantees on Faith

### 13.1. Why Is Persistent Usually Higher Overhead?

The broker may have to:
- Write to a journal/store and manage sync/batching.
- Replicate messages to replicas or wait for quorum depending on architecture.
- Store metadata to recover queues and transaction states.
- Record ACKs/deletions so storage does not grow unboundedly.
- Organize paging/large-message files when backlog or payload sizes grow.

`NON_PERSISTENT` does not mandate those durable write steps, so throughput can be higher and latency lower. **There is no fixed speedup ratio**: cost also depends on payload size, I/O, broker configuration, batching, HA, network, and consumer speed.

### 13.2. How to Benchmark Meaningfully

To evaluate mode selection, run the same broker software, same storage configuration, same payload size, same producer/consumer load, and same ACK mechanism:

1. Use separate queues per mode or run sequentially to avoid storage/CPU contention.
2. Warm up and keep message counts sufficiently large.
3. Measure throughput (msg/s), producer send latency p50/p95/p99, consumer end-to-end latency, CPU, disk IOPS/fsync, and backlog.
4. Repeat under high load, offline consumers, retries, and broker restarts in staging.
5. Observe DLQ, expiry, loss, and business impact/latency, not just raw speed.
6. Document broker version, storage, journal sync, HA, transactions, and persistence mode so others can reproduce the results.

If messages must not be lost, **do not pick NON_PERSISTENT simply because the benchmark is faster**; instead look at optimizing batching, event structure, volume/IOPS, producer/consumer concurrency, and workload design.

## 14. What Should a Delivery Quality Contract Document?

A good message contract should clearly specify:

| Field | Example or Question |
| --- | --- |
| `messageType` | `GenerateInvoice` or `TelemetrySample`? What does the command/event mean? |
| `destination` + `domain` | Queue `invoices.commands` or Topic `telemetry.live`? |
| **Delivery mode** | `PERSISTENT`/`NON_PERSISTENT` based on which business requirement? |
| **Producer send/commit** | Who publishes, when is it considered successful? Is there a transaction or outbox? |
| **Consumer subscription** | Which queue/group receives it? Is the topic subscription durable/shared? |
| **TTL and retention** | When does it expire? How long does the broker retain it at most? |
| **ACK/transaction** | What are the ACK/commit and rollback conditions? Does the DB have a separate transaction? |
| **Idempotency key** | Which `eventId`, `requestId`, or business key prevents duplicate side effects? |
| **Retry/DLQ** | Retry count, delay, poison-message policy, replay/reconciliation process? |
| **Availability** | What are broker persistence, volume, replication/failover, and RPO/RTO? |
| **Ordering** | Is per-key ordering required? Are modes/priorities mixed? |
| **Observability** | Message count by mode, ack, DLQ, expiry, age, send errors, p99 latency? |
| **Versioning** | Can older consumer versions read payloads stored long-term on the broker? |

### Example Contract: Critical Invoice

~~~yaml
kind: command
type: GenerateInvoice
destination: invoices.commands
domain: queue
deliveryMode: PERSISTENT
eventId: "invoice-request-id"
sourceOfTruth: checkout-db
publisherSafety: transactional-outbox
subscriberGroup: invoice-workers
acknowledge: transacted-after-success
idempotency: unique business key invoice-request-id
ttl: business-reviewed, not a short arbitrary default
failure: bounded retries with DLQ and reconciliation
storage: broker persistence/retention/HA verified
~~~

### Example Contract: Droppable Real-Time Metrics

~~~yaml
kind: event
type: LiveCpuSample
destination: telemetry.live
domain: topic
deliveryMode: NON_PERSISTENT
consumer: live dashboard, no guaranteed offline replay
ttl: short, determined by UI freshness SLA
lossTolerance: missing occasional samples is acceptable
historicalSource: metrics database (not live topic)
observability: sample-age, publish-failures, drop-rate
~~~

This is a **contract-description YAML file for discussion**, not an auto-running `application.yml`. Each organization must implement the policy via Spring code, broker configuration, access controls, and integration tests.

## 15. Common Mistakes and How to Fix Them

1. **Only calling `setDeliveryMode(NON_PERSISTENT)` on `JmsTemplate`.** Without enabling explicit QoS, the setter may be ignored. Enable `setExplicitQosEnabled(true)` or use the corresponding Boot QoS property.
2. **Modifying `message.setJMSDeliveryMode(...)` before send.** The JMS provider ignores the caller-set header value on send; set the mode on the producer or send operation.
3. **Calling NON_PERSISTENT "never touches disk".** Providers may still page/temporarily store; it simply lacks persistent's durability obligation.
4. **Calling PERSISTENT "never lost".** TTL, retention, resource limits, subscriptions, and storage failures still apply.
5. **Believing PERSISTENT = business exactly-once.** Broker delivery and DB side effects are two separate layers; idempotency is still required.
6. **Assuming durable Topic subscription and persistent mode are the same.** One belongs to the subscription, the other to the message.
7. **Sending persistent Topic messages before a subscriber registers and expecting full history.** A non-existent subscription does not accumulate a backlog for the future.
8. **Testing persistence with an embedded broker whose storage is disabled.** The mode header still has a value, but it does not prove survival across restarts.
9. **Using NON_PERSISTENT for payment/invoice without a recovery path.** Dropping a message causes a missing business outcome; choose the mode based on the loss budget.
10. **Assuming queues are always strictly FIFO.** Priority, delay, concurrency, redelivery, and mixing modes can alter actual delivery order.
11. **Enabling explicit QoS and forgetting TTL/priority.** It affects all three properties; verify against admin defaults.
12. **Confusing a sent message with a committed transaction.** A transacted JMS session can roll back after send.
13. **ACKing a message before DB processing finishes.** The broker assumes completion, risking loss of the business effect.
14. **Not monitoring quota/disk/expiry/DLQ.** Persistent backlogs can fill storage; set alerts and intentional limits.
15. **Storing events long-term without controlling schema versions.** Durable backlogs mean new consumers must be able to read older events.
16. **Not testing broker failures/restarts.** A "sent successfully" log moments after publish does not prove provider behavior under fault.

## 16. Pre-Production Testing Checklist

- **Defaults**: With the actual config, what `getJMSDeliveryMode()` does a message sent without an explicit mode receive?
- **Explicit QoS**: After `setExplicitQosEnabled(true)`, is the message header 1 or 2 as expected?
- **Separate templates**: Are you sure the business publisher uses the persistent template while the telemetry publisher uses the non-persistent one?
- **TTL/priority**: Did enabling explicit QoS accidentally override TTL/priority in broker policy?
- **Broker persistence**: Are journal/store, volume, and fsync/replication actually enabled properly?
- **Topic**: Was the subscription needing offline delivery created as durable beforehand?
- **Failure**: In staging, restart/crash the broker with un-ACKed messages; is the remaining message count reconciled?
- **Transactions**: When do JMS send commit and receive ACK/commit occur?
- **Consumer crash**: After the business side effect but before JMS ACK, are there duplicates? Is the handler idempotent?
- **Resource limits**: When the queue grows large or disk fills up, what policy does the broker apply? Are there alerts or message drops?
- **Monitoring**: Are sent/confirmed counts, backlog, redelivery, expiry, DLQ, latency, and storage recorded?
- **Ordering**: If mixing both modes on the same queue, did you test ordering under real priority/concurrency?
- **Deployment**: Can the new consumer version still read persistent messages from the old version?
- **Runbook**: When the publisher times out or the broker fails over, how does the system reconcile duplicates/losses?

## 17. Reinforcement Exercises

1. Given queue `invoices.commands` and live topic `telemetry.live`: choose the delivery mode and explain using **message loss cost** rather than destination names.
2. Create two `JmsTemplate` beans as in Section 7. Remove `setExplicitQosEnabled(true)` on the `NON_PERSISTENT` template and run the lab; inspect the header and explain why the setter alone is insufficient.
3. The broker has persistence, but a Topic consumer has no durable subscription and is offline at publish time. Will a `PERSISTENT` message be delivered when the consumer joins later? Explain.
4. A queue retains messages for 20 minutes, and a message has a 30-second TTL. Why does `PERSISTENT` not keep the message alive until the consumer comes online?
5. Run a standalone broker with storage and two test queues. Send 100 persistent and 100 volatile messages, restart the broker in staging, and compare remaining ID counts. Why does a single observation of non-persistent messages surviving not become a guarantee?
6. A consumer writes to the DB successfully and crashes before JMS commit. Describe the redelivery scenario, the idempotency inbox table, and why persistent mode does not guarantee a single side effect.
7. Read a received message's metadata via `getJMSDeliveryMode()`. What does a value of 2 or 1 prove, and what does it **not yet** prove about the broker?
8. Design a benchmark suite on Artemis: which variables must be held constant, which metrics besides msg/s are needed, and why should you not state a generic performance ratio?
9. A producer on the same session sends a `PERSISTENT` message and then a `NON_PERSISTENT` message to the same destination. Should the consumer require strict global send-order processing? Why?
10. Write a go-live checklist for a payment event Topic with multiple durable subscriptions: QoS, retention, ACL, outbox, idempotency, retry/DLQ, schema, and failover testing.

## Official References

- **Jakarta Messaging 3.1 Specification**, especially `7.7 Message delivery mode`, `9.1 Reliability`, `3.4.2 JMSDeliveryMode`, and `6.2.9.2 Order of message sends`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- **Jakarta Messaging DeliveryMode API**, constant values and retention limits: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/deliverymode
- **Jakarta EE Tutorial**, message delivery modes, defaults, and trade-offs: https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html
- **Spring Framework 6.2 JmsTemplate Javadoc**, `setDeliveryMode`, `setDeliveryPersistent`, and `setExplicitQosEnabled`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- **Spring Framework 6.2 JMS sending**, Quality of Service: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- **Spring Boot 3.5 Common Application Properties**, `spring.jms.template.delivery-mode` and QoS: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- **Apache ActiveMQ Artemis — Persistence**, journal, storage, and policy: https://artemis.apache.org/components/artemis/documentation/latest/persistence
