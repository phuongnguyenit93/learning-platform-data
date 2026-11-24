# Consumers, Subscriptions, and Message Copies in JMS (Queue and Topic)

## 1. Three Distinct Concepts at Three Layers

In Jakarta Messaging (JMS), **producers send messages to destinations**, while the broker decides which receiving endpoints receive those messages. When reading a Queue/Topic diagram, you must separate:

| Concept | Nature | Question It Answers |
| --- | --- | --- |
| **Consumer** | The JMS object receiving messages (for example, `MessageConsumer`/`JMSConsumer`); in Spring, a listener container manages one or more consumers and invokes the `@JmsListener` method. | **Who** is actually receiving and processing the message? |
| **Subscription** | A registration relationship with a **Topic**, managed by the broker; it can be short-lived or durable, and can have one or multiple consumers. | **Which receiving group/stream** has the right to receive messages from the Topic? |
| **Message copy (delivery copy)** | An **independent logical** delivery unit created for each eligible subscription when publishing to a Topic. | **How many groups** need to receive this event? |

**Key point:** the number of consumers **does not by itself determine** the number of message copies. With a Topic, the number of matching subscriptions determines the number of logical deliveries; multiple consumers on the **same shared subscription** split processing **one** copy intended for that subscription. With a Queue, a message is distributed to **one** consumer among competing consumers.

The word "copy" describes **the independent semantics of delivery/acknowledgment**, without promising that the broker physically duplicates the payload into multiple memory regions or multiple physical records. The broker may use references, internal queues, or its own optimized structures. The models below assume messages have not expired, selectors match, and no delivery errors occur.

## 2. Queue: Multiple Consumers Competing for One Work Stream

```text
Producer --send(M1)--> Queue orders
                          |-- Consumer A
                          `-- Consumer B

M1 is delivered to A OR B, not intentionally duplicated to both.
```

- A Queue can exist and retain messages when there are no consumers yet, depending on the broker's retention/expiry configuration. A Queue does not use "Topic subscriptions" to fan out.
- If A and B both listen on the same Queue, one send of M1 has **one expected successful processing attempt** within the competing group. The broker chooses A or B according to its own dispatching schedule; JMS **does not promise round-robin, 50/50, or even distribution order**.
- Adding consumers is usually to **increase parallel processing capacity** and redundancy. It does not make every consumer receive all messages.
- If a consumer receives a message and then rolls back, loses connection, or fails to acknowledge validly, the message **may be redelivered** to A or B. That is **re-sending the same work**, not fan-out creating a new subscription.

**Example:** A Queue receives Q1, Q2, Q3; there are consumers A, B. One valid distribution is A receiving Q1 and Q3, and B receiving Q2; it is also possible for A to receive all three. You cannot infer which consumer receives a specific message merely from the consumer count.

## 3. Topic: Publish to Subscriptions, Then Distribute to Consumers

```text
                      Topic orders.events
                       publish(E-101)
                             |
          +------------------+------------------+
          |                  |                  |
  Subscription audit   Subscription billing  Subscription search
      (1 consumer)       (shared: B1, B2)       (1 consumer)
          |                  |                  |
       Audit A           B1 OR B2            Search S
       copy #1            copy #2              copy #3
```

Assuming all three subscriptions are active and selectors match, **one** publish of E-101 creates **three independent logical deliveries**: audit, billing, search. Within billing, B1 and B2 split **one** delivery belonging to the billing group; there are not two separate deliveries just because there are two consumers.

Important consequences:

1. **One subscription, multiple consumers (shared):** an event is delivered to **one** consumer in the group. Used to scale out a single business service.
2. **Multiple independent subscriptions:** the same event is delivered **once per subscription**. Used when different business functions all need the event, such as billing and audit.
3. **Two unshared Topic consumers:** each consumer creates its own **separate unshared non-durable subscription**. If both are active at publish time, each receives a copy; they do **not** automatically become "competing consumers" on the same subscription.
4. **Adding a consumer to an existing shared subscription** does not increase the number of logical copies. **Adding an independent subscription** typically increases the number of deliveries needed for each matching event.

For each copy across different subscriptions, acknowledgment/rollback, latency, and backlog are **independent**. Audit finishing E-101 does not mean billing has finished; an error in billing does not force audit to receive it again. A subscription whose selector does not match will not be given the corresponding copy.

### Scenario Table: One Message Sent/Published, No Errors

| Destination and Registration Method | Consumer Count | Topic Subscription Count | Expected Logical Deliveries |
| --- | ---: | ---: | --- |
| Queue, A and B both consume | 2 | Not applicable | **1 total**, to A or B |
| Topic, A and B each have their own unshared subscription, both online | 2 | 2 | **2**, 1 each |
| Topic, A and B share subscription `billing` | 2 | 1 | **1 total**, to A or B |
| Topic, shared `billing` has B1+B2; `audit` has A1 | 3 | 2 | **2**, 1 for billing and 1 for audit |
| Topic, `audit` is online; non-durable `email` is completely offline | 1 online | 1 existing | **1** for audit; email has no backlog |

"Deliveries" in the table is the number of copies **according to the routing model**, **not** the actual number of callback invocations when retries/redeliveries occur. Count only subscriptions that actually exist at publish time and satisfy selectors, TTL policies, etc.

## 4. Subscriptions Have Two Independent Configuration Dimensions

**Dimension 1 – shared vs. unshared:** how many consumers does a subscription allow to **concurrently** consume?

- **Unshared:** at most **one** active consumer on that subscription. Opening a second consumer on the same *unshared durable subscription* before the first closes will raise an error.
- **Shared:** **multiple** consumers can attach to one named subscription; each message of the subscription goes to **one** consumer in the group. This is competition **within the subscription**, not broadcasting to every consumer.

**Dimension 2 – durable vs. non-durable:** does the broker retain the subscription/backlog when no consumer is present?

- **Non-durable:** exists only while the corresponding consumer is active; when the last consumer closes, the subscription disappears. Events published during the absence of that subscription **cannot be retrieved retroactively later**.
- **Durable:** the broker maintains the subscription after consumers disconnect, retaining matching unacknowledged messages subject to existence conditions, expiry, and broker policies. A consumer reconnecting with the exact identity can receive the backlog. Durable **does not mean** retaining every message from before the subscription was created.

| Topic Subscription Type | Concurrent Consumers | Typical Identity | When All Consumers Are Offline |
| --- | --- | --- | --- |
| Unshared + non-durable | 1 | Implicitly created, unnamed | Deleted; accumulates no new messages |
| Shared + non-durable | Multiple | `subscriptionName` and `clientId` if set | Deleted after last consumer; accumulates no new messages |
| Unshared + durable | 1 | **Requires** `clientId + subscriptionName` | Remains; can accumulate valid messages |
| Shared + durable | Multiple | `subscriptionName` and **optional** `clientId` | Remains; can accumulate valid messages |

Two configurations with the same display name are **not necessarily** the same subscription: you must consider the domain/topic, shared/durable flags, and client identity used by the provider. Consumers sharing a subscription must use compatible topic and selector settings. Changing the topic/selector of a durable subscription while offline can have delete-and-recreate semantics per the specification; do not treat it as a harmless update.

**Distinguishing the two terms "durable/persistent":** durable subscription refers to **subscription lifecycle**; `PERSISTENT` delivery mode refers to **message durability across broker failures**. Recovering after a broker crash also depends on delivery mode, storage configuration, transactions, expiry, and provider policies. A durable subscription does not turn every `NON_PERSISTENT` message into absolute safety.

## 5. Separating "Copies Across Subscriptions" from "Redelivery Within One Subscription"

Consider E-42 published to two subscriptions `audit` and `billing`:

```text
                         E-42
                   /               \
             audit copy         billing copy
               ACK OK           processing error
              completed               |
                             rollback/recover
                                    |
                             redeliver E-42
                              to B1 or B2
```

- **Fan-out:** audit and billing have two **different** logical delivery units right from routing time; audit's ACK does not ACK on behalf of billing.
- **Redelivery:** the broker redelivers the **incomplete part of billing**. If billing is a shared subscription, B1 may receive the first attempt while B2 may receive the next. It does not create a third subscription.
- **Producer-side duplicate:** if the producer sends E-42 twice due to retries without deduplication, that is two separate publishes. Do not confuse this with two copies from two subscriptions or one copy being redelivered.
- **Concurrent processing:** with multiple consumers or multiple copies across different subscriptions, handlers can run in parallel; **do not infer** log order or completion order.

To observe retries, check `JMSRedelivered` and `JMSXDeliveryCount` (Jakarta Messaging 2.0+ providers set the delivery count property). Use a separate **business event ID** in the payload/header to track the same event across subscriptions and support idempotency; do not rely solely on log counts or `Message` instance counts in the JVM. `JMSMessageID` is provider-assigned metadata and does not replace a business key.

**Operational note:** JMS acknowledgment/transaction resolves whether the broker considers a message processed, but does not automatically guarantee "exactly once" side effects in databases or HTTP calls. Handlers should be **idempotent** by `eventId`; if needed, use an inbox table/unique constraint and appropriate transactions. Proper rollback enables retries; poison messages require an attempt limit and broker DLQ policy.

## 6. Spring Framework Hands-On: Clearly Seeing Which Consumers Share a Subscription

The example below uses Java 17, Spring Boot 3.3.13 / Spring Framework 6.x, Jakarta Messaging (`jakarta.jms`), and Apache ActiveMQ Artemis. It creates:

- One Queue `orders.queue` with **2 competing consumers** on the same listener.
- One Topic `orders.events` with two independent **unshared non-durable subscriptions**: audit and email.
- On the same Topic, one **shared durable subscription** named `analytics` with **2 competing consumers**.

Three messages are sent to the Queue and three other messages are published to the Topic. This is a demonstration application with a real broker; do not substitute an in-memory simulation for JMS.

### 6.1. Preparing the Broker

With Docker installed, run the following command from a terminal (default configuration creates a test broker, JMS port 61616):

```bash
docker run --detach --rm --name jms-demo-broker -p 61616:61616 \
  -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

If using PowerShell, write the command above on **one line** (or replace the line continuation character with a PowerShell backtick). Wait for the broker to start before running the application. Use a fresh/empty broker so the counts below do not mix with backlog from a previous run. Command to stop after the lesson: `docker stop jms-demo-broker`.

### 6.2. Creating the Gradle Project

`settings.gradle`:

```groovy
rootProject.name = 'jms-copy-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.jms'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

`src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
```

`src/main/java/demo/jms/JmsDemoApplication.java`:

```java
package demo.jms;

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
public class JmsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsDemoApplication.class, args);
    }

    @Bean("queueFactory")
    DefaultJmsListenerContainerFactory queueFactory(ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);  // Queue
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("topicIndependentFactory")
    DefaultJmsListenerContainerFactory topicIndependentFactory(ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(true);   // Topic
        factory.setSessionTransacted(true);
        return factory;                  // non-durable, unshared (default)
    }

    @Bean("topicSharedFactory")
    DefaultJmsListenerContainerFactory topicSharedFactory(ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(true);
        factory.setSubscriptionShared(true);
        factory.setSubscriptionDurable(true);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("queueSender")
    JmsTemplate queueSender(ConnectionFactory cf) {
        var template = new JmsTemplate(cf);
        template.setPubSubDomain(false);
        return template;
    }

    @Bean("topicSender")
    JmsTemplate topicSender(ConnectionFactory cf) {
        var template = new JmsTemplate(cf);
        template.setPubSubDomain(true);
        return template;
    }

    @Bean
    ApplicationRunner publishDemo(
            @Qualifier("queueSender") JmsTemplate queue,
            @Qualifier("topicSender") JmsTemplate topic) {
        return args -> {
            for (int i = 1; i <= 3; i++) {
                queue.convertAndSend("orders.queue", "Q-" + i);
                topic.convertAndSend("orders.events", "T-" + i);
            }
        };
    }
}

@Component
class RoutingListeners {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "queueFactory",
            concurrency = "2-2")
    public void queueWorker(String message) {
        System.out.println("QUEUE [" + Thread.currentThread().getName() + "] " + message);
    }

    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicIndependentFactory")
    public void audit(String message) {
        System.out.println("AUDIT " + message);
    }

    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicIndependentFactory")
    public void email(String message) {
        System.out.println("EMAIL " + message);
    }

    @JmsListener(
            destination = "orders.events",
            subscription = "analytics",
            containerFactory = "topicSharedFactory",
            concurrency = "2-2")
    public void analytics(String message) {
        System.out.println("ANALYTICS [" + Thread.currentThread().getName() + "] " + message);
    }
}
```

Run using Gradle 8.5+ compatible with the Spring Boot version listed above:

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`. If the project does not yet have a Gradle Wrapper, generate a wrapper with an installed Gradle or run `gradle bootRun`.

### 6.3. Reading the Results Properly

With a fresh broker, listeners already started, no errors, and no expirations, the total lines printed by the four handlers will be:

| Handler | Messages Received | Expected Line Count |
| --- | --- | ---: |
| `QUEUE` | Each of `Q-1`, `Q-2`, `Q-3` appears **once in total** | 3 |
| `AUDIT` | `T-1`, `T-2`, `T-3` | 3 |
| `EMAIL` | `T-1`, `T-2`, `T-3` | 3 |
| `ANALYTICS` | `T-1`, `T-2`, `T-3` **once across the entire analytics group** | 3 |
| **Total** | 3 queue deliveries + 3 × 3 topic subscription deliveries | **12** |

Line order and which thread receives each message are **not fixed**. `QUEUE` does not guarantee a 1/2 split between the two threads; neither does `ANALYTICS`. If you run the application multiple times against a broker that already has a durable subscription, backlog messages may be received additionally. If a non-durable subscriber has not started before publish time, corresponding lines may be missing; ensure startup succeeds and retry with a fresh broker.

**Key points to understand when reading the code:**

- `@JmsListener` marks the **handler**; Spring creates the listener container and the actual underlying JMS consumers. `concurrency="2-2"` requests 2 concurrent consumers for the Queue and for the shared subscription (if supported by the broker).
- `setPubSubDomain(false/true)` selects **Queue/Topic**. The producer must also use the right domain; sending to Queue named X is not the same as publishing to Topic with the same name X.
- The two methods `audit()` and `email()` use **unshared non-durable**, creating **two independent subscriptions**; therefore both see T-1..T-3 while online.
- `analytics()` uses `setSubscriptionShared(true)` **and** `subscription="analytics"`: two consumers in **one group**. `setSubscriptionDurable(true)` allows this subscription to persist when the application shuts down. For **shared durable**, Jakarta Messaging allows omitting `clientId`; for **unshared durable**, a stable and unique `clientId` must be specified per broker policy.
- `setSessionTransacted(true)` lets the listener roll back JMS consumption when the handler throws an error; if the handler writes to a separate database, the JMS transaction **does not automatically** cover the database.
- Setting only `subscription="analytics"` in the annotation is **not enough** to make a Topic listener shared/durable; those two properties live on the container factory. Do not use the same shared subscription name for two business services that need **one copy each**.

## 7. Design Decisions and Common Mistakes

**Choose a Queue when** multiple workers perform **the same type of work**, such as processing an order on exactly one worker. **Choose a Topic with separate subscriptions when** multiple systems/business services need to **independently handle the same event**, such as audit, notification, analytics. **Use a shared subscription when** one business service needs multiple replicas while still wanting only **one replica to process each event**.

Mistakes to avoid:

1. **"A Topic has three consumers, so it always creates three copies."** False: two consumers may belong to one shared subscription; and an offline non-durable subscription retains no copies.
2. **"Two `@JmsListener`s on the same destination are two load-balanced consumers."** On a Queue they normally compete; on a Topic, unshared by default creates **two subscriptions**, each receiving events.
3. **"Durable = consumer staying open / infinite backlog."** Durable refers to the subscription surviving offline periods; retention duration, expiry, quotas, delivery mode, DLQ, and policies still apply.
4. **"ACK on one subscriber suffices for the whole Topic."** False: each subscription has an independent processing/ack state.
5. **"Seeing a message appear twice means the broker copied it wrong."** You must distinguish double publishing, fan-out to two subscriptions, redelivery after rollback, and clients logging multiple times.
6. **"Increase concurrency on unshared durable to scale."** Unshared durable allows only one active consumer; to scale the same group, choose shared durable and verify broker/provider compatibility.
7. **"Message selectors of individual consumers in a shared subscription can differ arbitrarily."** Topic/selector configuration must be consistent for the same shared subscription; do not use selectors to simulate independent business subscriptions when all sides should receive messages.
8. **"JMS handles every side effect exactly once."** Handlers can rerun; business keys/idempotency and proper transaction management are needed.
9. **"Same destination name definitely means the same type."** Queue and Topic are two distinct domains in JMS. Misconfiguring `pubSubDomain` can create an unintended destination or cause a broker error.

### Check Your Understanding

- Send one event to a Topic with `payment` (shared, 4 consumers) and `audit` (unshared, 1 consumer): **2 logical deliveries**, payment receives on **one of the four**, audit receives **one**.
- Shut down all `payment` consumers when `payment` is an already created **shared durable** subscription: matching new events can enter payment's backlog; when restarted, the group splits processing the remaining events.
- If `payment` is **shared non-durable** and the last consumer shuts down, the subscription disappears; events sent during the gap are **not retroactively delivered** merely by creating a consumer with the same name later.
- If a Queue consumer received a message but rolled back, the broker redelivers to another consumer: **it is still one logical Queue job**, generating a re-delivery because processing did not complete.

## 8. Official Reference Documentation

- [Jakarta Messaging 3.1 Specification, sections 4.1 (Queue) and 4.2/8.3 (Topic subscription)](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework: Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework: Using Spring JMS, transactions and listener containers](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Apache ActiveMQ Artemis: Official Docker image](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)

**Key takeaway:** Queue distributes **one job to one consumer**; Topic multiplies **deliveries per subscription**; consumers within the same **shared subscription** compete to process the deliveries of **one** subscription.
