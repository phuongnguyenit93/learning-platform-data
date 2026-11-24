# Topics When Subscribers Are Online or Offline in Spring JMS

## 1. Understanding the Problem Correctly

In Jakarta Messaging's (JMS) publish/subscribe model, a publisher sends messages to a **Topic**. The broker distributes messages to matching **subscriptions**; each subscription can have one or multiple consumers depending on the registration type. The core question of this lesson is: **what happens if a subscriber is active, shut down, or only reconnects after a message has been sent?**

The answer depends first on the **subscription type**, when the subscription was created, and message retention conditions on the broker.

- **Non-durable subscription**: exists only while active consumers remain. When no consumers remain, the subscription is deleted; messages appearing during the absence are not reserved for it to receive later.
- **Durable subscription**: the broker stores the subscription's identity across consumer disconnections. After the subscription **has been created**, matching messages sent while the consumer is offline can sit in the backlog to be received when the consumer reconnects.
- **No default history replay mechanism**: a subscriber created for the first time **after** messages were published does not automatically receive old messages, even when creating a durable subscription.
- **Online/offline is the consumer's state with respect to a subscription**. Merely having a running Java process or an open socket does not prove a consumer has subscribed to a Topic.

Goals after this lesson: explain when messages are received or lost, choose non-durable or durable based on business requirements, configure Topic in Spring JMS, and verify behavior yourself through disconnect/reconnect tests.

## 2. How Does a Topic Differ from a Queue?

With a **Queue**, multiple consumers pull work from a single queue; each message is normally processed successfully by one consumer. With a **Topic**, a message is fanned out to **each eligible subscription**; two independent subscriptions can both receive two delivery copies of the same message.

~~~text
                          +--> Subscription A --> Consumer A
Publisher --> Topic ------+
                          +--> Subscription B --> Consumer B
                          |
                          +--> Subscription C --> Consumer C
~~~

Example of a system publishing `orders.changed` events:

- A scoring service and an audit service have two separate subscriptions: both can receive event `Order-42`.
- Two consumers sharing **one shared subscription** compete for work within that subscription; each message in the subscription is delivered to only one consumer, not fanned out to both consumers.
- These two designs differ even though both can use a Topic.

**Easy rule to remember:** Topics distribute by **subscription**, while whether messages are received when a subscriber returns is determined by **subscription lifecycle**.

## 3. Online/Offline with Non-Durable and Durable

Assume the broker remains running, no selector excludes the message, the message has not expired, and it stays within storage limits.

| Scenario | Non-durable subscription | Existing durable subscription |
| --- | --- | --- |
| Consumer is active when M1 is published | Can receive M1 | Can receive M1 |
| Consumer closed/disconnected, M2 is published | Does not retain M2 for the vanished subscription | Broker accumulates M2 for the subscription |
| Consumer recreated/reconnected after M2 | Receives new messages from re-registration onward; does not automatically receive M2 | Can receive still-valid M2 backlog and then continue receiving new messages |
| M0 published **before the first** creation of the subscription | Does not receive M0 | Does not receive M0 |
| Consumer stops permanently | Subscription is removed | Subscription still occupies resources until deleted/administered |

The phrase **"durable subscriber"** is usually shorthand for **a consumer using a durable subscription**. The entity retained by the broker is the subscription and its message state, not a running Java thread/object.

### Timeline Example

Suppose Topic `news.events` has non-durable subscription A and durable subscription B. Both are created at T0; at T1 both are online.

~~~text
T0: Create A (non-durable) and B (durable)
T1: Publish M1        -> A receives M1; B receives M1
T2: Close consumers A/B
T3: Publish M2, M3    -> A has no backlog; B retains M2, M3
T4: Restart A/B       -> A does not receive M2/M3; B receives M2/M3 if still valid
T5: Publish M4        -> Both A and B can receive M4
~~~

Key conditions:

1. **B must be created before T3.** If B is only created at T4, `M2` and `M3` are not in B's backlog.
2. "Receive" means the message is delivered for processing; whether processing is durably completed still depends on ACK/transactions and application errors.
3. If M2's TTL expires, a selector filters it out, or the broker drops it due to storage policy, B cannot reclaim that message simply by having durable enabled.
4. If a non-durable consumer only experiences brief network flakiness without yet being considered closed by the broker, the transient state depends on the provider and error-detection timing. Do not rely on this flakiness window to guarantee data.

## 4. Subscription Lifecycle and Reconnection Identity

### 4.1. Non-Durable: Subscription Tied to Consumer

When creating a normal consumer for a Topic, the provider creates a non-durable subscription. In the **unshared** form, closing the consumer ends the subscription. In the **shared non-durable** form, the subscription can have multiple consumers but is still deleted when the last consumer closes. Messages published after that point are not accumulated for the vanished subscription.

Non-durable makes sense when data is only useful "right now": live screen updates, droppable telemetry signals, state that can be resynced from another source. Do not use it when every event must be processed after maintenance or a restart.

### 4.2. Durable: Broker Retains Identity and Backlog

For an **unshared durable subscription**, identity typically includes:

- **`clientId`** of the JMS connection: stable across restarts, unique among active connections per provider rules.
- **`subscriptionName`**: stable subscription name. In Spring, this can be set via the `subscription` attribute of `@JmsListener`.
- **Topic** bound to the subscription and conditions such as selector/noLocal: must remain consistent when reconnecting.

On first connection, the consumer registers the subscription. When the consumer closes, the broker does **not** delete the durable subscription; matching messages continue to accumulate. Next time, a consumer using the exact same identity can resume consuming the backlog.

**Do not change clientId or subscriptionName arbitrarily after deployment**: changing identity can cause the application to create a new subscription and leave the old backlog unprocessed. With an unshared durable subscription, only one active consumer can attach to the subscription at a time; horizontal scaling with multiple instances using the same identity will cause conflicts.

### 4.3. Shared Durable When Multiple Consumers Need to Process Backlog Together

Jakarta Messaging supports **shared durable subscriptions**. Multiple consumers can attach to *one* durable subscription and split messages. With the shared type, clientId may be omitted; if set upon creation, participating consumers must use the same identity per the JMS/provider contract.

Comparison:

| Consumer Organization | Result for One Matching Message |
| --- | --- |
| Independent `audit` and `analytics` subscriptions | Each subscription receives one delivery |
| Two consumers on the same shared `analytics` subscription | Only one of the two receives that message |
| Two unshared durable consumers using the same clientId/name concurrently | Invalid; the provider may report an error when the second consumer registers |

To **broadcast to each service**, create a separate subscription per service; to **share load across instances of the same service**, consider shared durable or a queue architecture suited to the broker.

### 4.4. When Is a Subscription Actually Deleted?

Closing a consumer or shutting down an application is **not** an action that deletes a durable subscription. To stop retaining backlog permanently, an appropriate administrative action or calling `Session.unsubscribe(name)` / `JMSContext.unsubscribe(name)` under valid conditions (no active consumers and no in-progress transactions/ACKs for messages) is required. Delete intentionally, after confirming pending data is no longer needed.

## 5. "Durable" Is Not Synonymous with "Persistent Message"

There are two independent dimensions:

1. **Subscription durability**: whether the subscription continues to exist when consumers are offline.
2. Message **delivery mode**: `PERSISTENT` instructs the provider to handle the message with stronger durability protection across transport/broker failures; `NON_PERSISTENT` prioritizes performance and risks loss on failure.

A message sent in `PERSISTENT` mode **does not automatically turn a non-durable subscription into a durable one**. If a non-durable consumer has closed, the broker has no obligation to build a backlog for it. Conversely, a durable subscription can receive messages sent as `NON_PERSISTENT` while the broker still holds them; however, you cannot assume messages survive a broker crash/restart.

Actual ability to receive backlog is also affected by:

- **TTL/expiration**: expired messages are not delivered after the subscriber returns.
- **Message selector**: only messages with properties matching the subscription's filter are accumulated.
- **Retention, quotas, and broker policies**: running out of storage, message count limits, drop policies, dead-lettering, or administration can change outcomes.
- **Broker restart/failover**: appropriate journal/persistence configuration, broker clustering, and operations are required if survival across failures is desired.
- **ACK and transactions**: a delivered message does not mean business processing has committed; rollback or crash can cause redelivery.

Therefore, you must ask three separate questions properly: **does the subscription still exist? is the message retained? has processing been acknowledged?**

## 6. Spring Boot 3.3 / Spring JMS Example, Java 17

The example below uses **a separately running ActiveMQ Artemis broker**, so publisher/subscriber processes see the same Topic and backlog. Do not use a separate embedded broker per process, because then they will not communicate with each other.

Prerequisites: JDK 17+, Gradle 8.x, an Artemis broker supporting Jakarta Messaging and allowing clients to access `tcp://127.0.0.1:61616`. Username/password configuration, Topic auto-creation (if needed), and durable storage must match the actual broker. The sample project places Java files in `src/main/java/demo/jms/`.

### 6.1. Build and Broker Connection

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-topic-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://127.0.0.1:61616
spring.jms.pub-sub-domain=true
~~~

If the broker requires login, add `spring.artemis.user` and `spring.artemis.password` with credentials provided by the broker. The property **`spring.jms.pub-sub-domain=true`** makes `JmsTemplate` send to a **Topic**; the separate listener factory configuration below must also enable Topic. Spring Boot's default for `JmsTemplate` is typically queue mode, so omitting this step is a very common mistake.

### 6.2. Application and Two Listener Types

`TopicDemoApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TopicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TopicDemoApplication.class, args);
    }
}
~~~

`TopicConfig.java`:

~~~java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class TopicConfig {

    @Bean("nonDurableTopicFactory")
    DefaultJmsListenerContainerFactory nonDurableTopicFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("durableTopicFactory")
    DefaultJmsListenerContainerFactory durableTopicFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSubscriptionDurable(true);
        factory.setClientId("audit-service-v1");
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

`NonDurableSubscriber.java`:

~~~java
package demo.jms;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("non-durable")
public class NonDurableSubscriber {

    @JmsListener(
        destination = "demo.events",
        containerFactory = "nonDurableTopicFactory"
    )
    public void onMessage(String body) {
        System.out.println("LIVE RECEIVED: " + body);
    }
}
~~~

`DurableSubscriber.java`:

~~~java
package demo.jms;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("durable")
public class DurableSubscriber {

    @JmsListener(
        destination = "demo.events",
        containerFactory = "durableTopicFactory",
        subscription = "audit-events-v1"
    )
    public void onMessage(String body) {
        System.out.println("DURABLE RECEIVED: " + body);
    }
}
~~~

Explanation of decisive lines:

- `setPubSubDomain(true)`: listener receives from a **Topic**, not a Queue.
- `setSubscriptionDurable(true)`: the second factory creates a durable subscription.
- `setClientId("audit-service-v1")` + `subscription = "audit-events-v1"`: identity reused across runs. Keep them unchanged during the test.
- `setConcurrency("1")`: unshared durable subscriptions allow only one active consumer, so do not try to open multiple consumers on the same subscription.
- `setSessionTransacted(true)`: if the listener throws an exception, the session can roll back and the message can be redelivered; this is a better choice than default AUTO_ACKNOWLEDGE for reliability-sensitive problems.
- `@Profile` allows running the two subscriber types separately and prevents activating all listeners automatically when running the publisher.

### 6.3. Publisher Sending Messages to the Topic

`TopicPublisher.java`:

~~~java
package demo.jms;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
@Profile("publisher")
public class TopicPublisher implements ApplicationRunner {
    private final JmsTemplate jmsTemplate;

    public TopicPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        String body = args.getNonOptionArgs().isEmpty()
            ? "sample-event"
            : String.join(" ", args.getNonOptionArgs());

        jmsTemplate.convertAndSend("demo.events", body);
        System.out.println("PUBLISHED: " + body);
    }
}
~~~

Spring Boot provides `ConnectionFactory` and `JmsTemplate` from the Artemis starter. `convertAndSend` converts the string into a JMS text message and publishes it to `demo.events` once `pub-sub-domain` is enabled. The send call completing does not prove subscribers have processed it; check consumer logs or ACK state on the broker.

### 6.4. Repeatable Experiments

Build the JAR in the project directory:

~~~bash
gradle bootJar
~~~

The example JAR is `build/libs/jms-topic-demo-0.0.1-SNAPSHOT.jar`. Run each Java command below in a **separate terminal**; keep the shared broker running throughout the test. If the publisher runner does not exit automatically due to JMS infrastructure, stop it after the `PUBLISHED` log appears.

**Experiment A – non-durable**

1. Run the subscriber: `java -jar build/libs/jms-topic-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=non-durable`.
2. When logs show the listener has connected to the broker, in another terminal publish `live-1`:

   ~~~bash
   java -jar build/libs/jms-topic-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=publisher live-1
   ~~~

3. The online subscriber will print `LIVE RECEIVED: live-1` (upon successful delivery).
4. Completely stop the non-durable process. Publish `offline-1` while no non-durable consumer is present:

   ~~~bash
   java -jar build/libs/jms-topic-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=publisher offline-1
   ~~~

5. Restart the non-durable subscriber. You will **not** see `offline-1` replayed simply because the subscriber reconnected. If you publish `live-2` after the listener is ready, it can receive `live-2`.

**Experiment B – durable**

1. Run `java -jar build/libs/jms-topic-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=durable` at least once to **create the durable subscription first**. Wait for the listener to connect successfully.
2. Publish `durable-live-1`; confirm the log `DURABLE RECEIVED: durable-live-1`.
3. Completely stop the durable subscriber; **do not delete the subscription on the broker**.
4. Publish `durable-offline-1` and `durable-offline-2` while the subscriber is shut down.
5. Restart the durable subscriber **with the same** `clientId` and `subscription`. If messages have not expired, the broker retained the backlog, and storage policies did not drop them, the subscriber log will record the messages sent while offline. Observed order also depends on provider/producer ordering guarantees and concurrency conditions; do not rely on log line order across multiple processes.

**Experiment C – creating durable too late**

On a completely new subscription/name, publish `before-first-subscribe` **before** initializing the new durable subscription. Then initialize the subscription for the first time. You will **not** receive `before-first-subscribe` under standard JMS rules; durable only retains messages from after the subscription was created. Replaying history requires a dedicated event storage mechanism or broker-specific features.

To repeat Experiment B with a clean state, manage subscriptions on the broker following the provider's operational guide. Avoid deleting real subscriptions while business backlog still needs processing.

## 7. ACK, Errors, and Duplicate Handling

Durable subscriptions solve the **absent subscriber** problem, but do not by themselves solve every **exactly-once processing** problem:

1. The broker delivers the message to the listener.
2. The listener executes application logic.
3. The session commits or ACKs according to the configured mode.
4. If an error occurs before commit, the broker may redeliver the message; if the application already updated the DB without committing the JMS receive, side effects may be duplicated.

Therefore, when processing orders or sending important notifications, use an **idempotency key** (for example, `eventId`) and protect business operations against duplicates. `setSessionTransacted(true)` only transacts operations within the JMS session; it does not automatically turn an external database update into a distributed transaction with the broker. For continuously failing errors, configure retry, backoff, and dead-letter queue (DLQ) policies suitable for the broker.

Do not equate "delivered" = "successfully processed"; monitor pending message counts, redeliveries, and ACK/commits as well.

## 8. Common Mistakes and How to Diagnose Them

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| Subscriber receives no messages | Publisher/Listener configured in queue mode or different Topic names | `spring.jms.pub-sub-domain`, `setPubSubDomain(true)`, destination name |
| Messages lost after going offline and back online | Using non-durable, or durable was not created before publish | Subscription type and initial creation timing |
| Thinking PERSISTENT automatically saves for every subscriber | Confusing delivery mode with subscription durability | Durable state on the broker, not just message headers |
| Restart makes backlog "disappear" | Changed clientId/subscriptionName, expired TTL, retention policy, or deleted subscription | Identity before/after restart, expiry, quotas, and broker logs |
| Second instance fails with client ID or duplicate consumer error | Two unshared durable listeners with the same identity running | Unique clientId while active, concurrency=1; consider shared durable when scaling |
| Receiving a message again after an error | Transaction rollback, unacknowledged, crash before commit | Transaction configuration and idempotent processing |
| Messages exist on Topic but subscriber does not see them | Messages do not match selector/noLocal or were published before subscription existed | Selector, properties, creation time, and broker routing |
| Broker restarts and backlog is lost | Persistence/HA not configured or storage policy does not meet requirements | PERSISTENT mode, journal, and broker configuration |

When debugging, use the identity **Topic + clientId + subscriptionName** (or the appropriate shared subscription name) to locate the right subscription; do not just look at connection counts or total messages across the whole broker.

## 9. Choosing an Approach by Business Need

- **Live dashboard, droppable data**: Topic + non-durable subscription; upon reconnect, fetch a fresh snapshot if needed.
- **Audit, data synchronization, events that must catch up after maintenance**: durable subscription, appropriate delivery mode and broker persistence, transactions/ACK, and idempotency.
- **Each service needs a copy of the event**: separate subscriptions, with each service deciding independently whether to be durable.
- **Multiple instances of the same service want to share backlog**: shared durable subscription (if the provider supports the exact requirement), or an appropriate queue/consumer group design.
- **Need unlimited history replay by offset/time**: consider a dedicated event log or broker-specific features; a standard JMS durable Topic is an unacknowledged backlog for a subscription, not an infinite event store.

## 10. Knowledge Self-Check

1. Publisher sends M1, and only afterwards consumer A creates a **durable subscription for the first time**. Does A receive M1? **No** under standard JMS; M1 was sent before the subscription existed.
2. A already has a durable subscription and goes offline for 10 minutes; M2 is published during downtime with a 1-minute TTL. When A restarts after 10 minutes, is it guaranteed to receive M2? **No**; M2 may have already expired.
3. Two independent subscriptions A/B monitor a Topic. When a message is sent while both are active, who can receive it? **Both A and B** (one delivery copy per subscription).
4. Do two consumers on the same shared durable subscription both receive the same message? **No**; that message is delivered to only one consumer in the shared subscription.
5. Is a `PERSISTENT` message sent while a non-durable consumer is closed automatically replayed when it reopens? **No**.
6. Why does a durable listener need idempotency? Because a crash/rollback before ACK or commit can lead to **redelivery**.

## 11. Summary and Reference Documentation

**Decision formula:** *Is there an active subscriber right at publish time?* → non-durable can receive. *Durable subscription already exists, but consumer is temporarily offline?* → broker can retain valid messages for delivery upon reconnect. *Subscription has never been created?* → no automatic historical backlog.

Official documentation for detailed lookup, especially when deploying on other brokers:

- Jakarta Messaging 3.1 Specification, sections **Subscriptions**, **Creating a consumer on a topic**, **Reliability**: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework – **Annotation-driven Listener Endpoints**: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework – **Using Spring JMS** (listener container, ACK, and transactions): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot – **JMS / ActiveMQ Artemis Support**: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
