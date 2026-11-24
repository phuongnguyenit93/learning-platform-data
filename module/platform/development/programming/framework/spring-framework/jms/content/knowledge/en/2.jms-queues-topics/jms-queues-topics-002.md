# Publish–Subscribe and the Topic Model in Spring JMS

## 1. Objectives and Context

After this lesson, you will be able to explain how a `Topic` distributes events to `subscriptions`, distinguish Topic from Queue, choose `durable/non-durable` and `shared/unshared` subscriptions, configure a publisher and listeners with Spring JMS, and identify risks of losing or duplicate-processing events.

`JMS` (Jakarta Messaging; formerly Java Message Service) is an asynchronous messaging API. A `Broker` is an intermediary system that accepts, routes, and stores messages according to configuration. A `Destination` is the send/receive target; the two main models are Queue and Topic. In Spring Framework 6 / Spring Boot 3, the JMS API resides under the `jakarta.jms` package (not `javax.jms`).

**Publish–subscribe (pub/sub)** solves the scenario where a single event needs to reach multiple independent systems. For example, when an order is created, the accounting, analytics, and notification systems all want to know, without the publisher needing to call each system individually.

## 2. How Does a Topic Actually Distribute Messages?

~~~text
OrderService (publisher)
        |
        |  publish "OrderCreated:42"
        v
   Topic: events.orders
        |
        +--> Subscription A --> Accounting consumer
        |
        +--> Subscription B --> Analytics consumer
        |
        +--> Subscription C --> Notification consumer
~~~

- **Publisher** sends a message to a Topic without needing to know how many recipients exist. Publisher and subscribers are decoupled in address, time, and deployment lifecycle.
- **Topic** is a logical destination on the broker side. The broker routes a copy of the message to **each matching subscription** at send time (or retains it for durable subscriptions).
- **Subscription** is the actual unit of message reception and acknowledgment. A completing processing does not mean B has completed processing; if B rolls back, redelivery to B does not force A to reprocess.
- **Consumer** is a process/thread reading from a subscription. A shared subscription can have multiple consumers competing to process **the single copy intended for that subscription**.

Key sentence: **"One message goes to every matching subscription" does not mean "every running instance receives a message".** Two instances sharing **one shared subscription** split the work; two **independent** subscriptions each receive a copy.

Basic sequence: (1) the broker provides the Topic; (2) consumers register subscriptions; (3) the publisher sends a message; (4) the broker copies/distributes according to subscriptions and selectors; (5) each consumer processes and acknowledges according to its acknowledgment/transaction mode. Whether a subscription continues to exist when consumers shut down depends on durability.

## 3. Comparing Queue and Topic

| Criterion | Queue — point-to-point | Topic — publish–subscribe |
|---|---|---|
| Receiving unit | One message is normally delivered to **one** consumer in the Queue's competing group. | Each **matching subscription** receives a copy of the message; within a shared subscription, one consumer receives each copy. |
| Common use cases | Work distribution: image processing, sending emails, executing jobs. | Event broadcasting: OrderCreated for accounting, reporting, notifications. |
| Multiple consumers | Compete to receive messages from the same Queue. | Can be independent subscribers (fan-out) or competing consumers within the same shared subscription. |
| Consumer offline | Messages can wait in the Queue, depending on TTL, broker policy, and acknowledgment. | Non-durable does not retain messages when the subscription has no consumers; durable can retain messages once already registered. |
| Scaling | Add consumers to the Queue to share load. | Add subscriptions for independent processing streams; add consumers to a **shared subscription** to share load for that stream alone. |

Do not switch a Queue to a Topic just to "speed up". A Topic typically creates multiple deliveries based on the number of subscriptions; the same message can cause N business executions. Choose the model based on **delivery semantics**, then optimize load.

## 4. Four Subscription Types and Lifecycles

Two independent axes form four combinations:

| Type | When no active consumer remains | Multiple consumers on same subscription? | Suitable use cases |
|---|---|---|---|
| Non-durable, unshared | Subscription ends; messages sent while no consumer is present are skipped for that subscription. | No, each unshared subscription has only one consumer. | Real-time UI updates, refreshable data. |
| Non-durable, shared | Exists while at least one consumer is active; deleted when the last consumer closes. | Yes; each message goes to one consumer in the group. | Online event-processing group that tolerates missing events while the whole group is offline. |
| Durable, unshared | Broker retains state and unprocessed messages for the registered subscription, subject to TTL/storage policies. | No, at most one active consumer on the same subscription. | Audit/reporting needing to catch up after downtime and running only a single consumer. |
| Durable, shared | Broker retains subscription when no consumer is active; multiple consumers share load when active. | Yes; each message in the subscription is received by one consumer. | A business flow that must not miss events while offline and wants to scale across multiple instances. |

**Easily confused details:**

1. Durable must **be created before** the publisher sends messages that need to be retained. It does not automatically retrieve messages sent prior to the first registration. Durable does not mean infinite history retention.
2. Non-durable has no "long-lived queue" when the client is offline. Even if the publisher uses delivery mode `PERSISTENT`, messages can still be lost for a terminated non-durable subscription.
3. Durable has a stable identity: for **unshared durable**, the pair `clientId + subscriptionName` identifies the subscription; subsequent connections must reuse the exact same identity. Shared durable uses a subscription name and client ID if present; follow provider-specific requirements. Do not change the name dynamically per pod ID if you want to consume the same stream.
4. With a shared subscription, 3 instances sharing one subscription do not receive 3 copies. If you want 3 services to all see the event, design **3 independent subscriptions**; each service can scale internally using a shared subscription.
5. Durable requires storage resources; you must monitor backlog, TTL, quotas, and clean up unused subscriptions. How subscriptions are managed/deleted depends on the broker.
6. When a subscriber has a `message selector`, the broker only delivers to the subscription messages whose **JMS properties/headers** match the condition. Selectors do not automatically read JSON or `TextMessage` body content.

### Timeline for Self-Check

Suppose Topic `events.orders` has non-durable S1 and durable S2 (S2 was already created beforehand):

~~~text
09:00  S1 online, S2 online       --> publish E1 --> S1 gets E1, S2 gets E1
09:05  S1 offline, S2 offline     --> publish E2 --> S1 does not get E2; S2 retains E2
09:10  S1 up, S2 up               --> S2 receives remaining E2; S1 does not receive E2 retroactively
~~~

This diagram is about **subscriptions**. If the broker runs out of storage, messages expire, or retention configuration differs, actual results may vary. If S2 had never been created before 09:05, S2 could not "retroactively" retrieve E2 from the past either.

## 5. A Spring Boot 3 + Artemis Application to Observe Fan-Out

The example uses Java 17, Spring Boot 3.3.5, Gradle, and an **embedded Apache ActiveMQ Artemis** broker for learning purposes. The program has two listeners independently subscribing to the same Topic; HTTP is called after the application starts to trigger publishing on demand. The embedded broker sets `persistent: false`, so the example does **not** demonstrate recovery across a full broker shutdown.

File structure:

~~~text
topic-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/application.yml
    └── java/demo/topic/
        ├── TopicDemoApplication.java
        ├── TopicConfiguration.java
        ├── AccountingListener.java
        ├── AnalyticsListener.java
        └── PublishController.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'topic-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  artemis:
    mode: embedded
    embedded:
      topics: events.orders
      persistent: false
  jms:
    cache:
      enabled: false
~~~

`cache.enabled: false` keeps the example easy to observe: listeners create dedicated connections, which is especially useful later when configuring a client ID for durable subscriptions. Production applications can use caching/pooling, but must choose the connection factory and client ID appropriate for the subscription model.

`src/main/java/demo/topic/TopicDemoApplication.java`:

~~~java
package demo.topic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TopicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TopicDemoApplication.class, args);
    }
}
~~~

`src/main/java/demo/topic/TopicConfiguration.java`:

~~~java
package demo.topic;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class TopicConfiguration {
    @Bean
    JmsTemplate topicTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true); // true = Topic, false = Queue
        return template;
    }

    @Bean
    DefaultJmsListenerContainerFactory topicListenerFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);       // Subscribe to Topic
        factory.setConcurrency("1");        // One consumer per unshared subscription
        factory.setSessionTransacted(true); // Commit/rollback JMS when listener processes
        return factory;
    }
}
~~~

The following two beans are **two independent subscriptions**, because each `@JmsListener` creates a separate listener container for the Topic.

`src/main/java/demo/topic/AccountingListener.java`:

~~~java
package demo.topic;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class AccountingListener {
    @JmsListener(
        destination = "events.orders",
        containerFactory = "topicListenerFactory"
    )
    public void onOrderCreated(String text) {
        System.out.println("accounting <- " + text);
    }
}
~~~

`src/main/java/demo/topic/AnalyticsListener.java`:

~~~java
package demo.topic;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class AnalyticsListener {
    @JmsListener(
        destination = "events.orders",
        containerFactory = "topicListenerFactory"
    )
    public void onOrderCreated(String text) {
        System.out.println("analytics <- " + text);
    }
}
~~~

`src/main/java/demo/topic/PublishController.java`:

~~~java
package demo.topic;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublishController {
    private final JmsTemplate topicTemplate;

    public PublishController(@Qualifier("topicTemplate") JmsTemplate topicTemplate) {
        this.topicTemplate = topicTemplate;
    }

    @PostMapping("/publish/{orderId}")
    public ResponseEntity<String> publish(@PathVariable String orderId) {
        String event = "OrderCreated:" + orderId;
        topicTemplate.convertAndSend("events.orders", event);
        return ResponseEntity.accepted().body("published " + event);
    }
}
~~~

Run in the `topic-demo` directory (requires JDK 17+ and Gradle compatible with Spring Boot 3.3; if Gradle Wrapper is present, use `./gradlew` instead of `gradle`):

~~~bash
gradle bootRun
~~~

When the server reports it has started and listeners are registered, open another terminal:

~~~bash
curl -X POST http://localhost:8080/publish/42
~~~

Expected HTTP body:

~~~text
published OrderCreated:42
~~~

In the application log, **one line per listener** should appear (the order of the two lines is not guaranteed):

~~~text
accounting <- OrderCreated:42
analytics <- OrderCreated:42
~~~

This is fan-out: a single `convertAndSend`, two independent business functions processing concurrently. The Java files in the example are actual Spring Boot application code; plain `javac`/`java` cannot be used alone because dependencies and a broker are required. `JmsTemplate.convertAndSend` converts `String` to `TextMessage` via the default converter.

If replacing Topic with Queue, the `pubSubDomain` configuration must be changed consistently on **both publisher and listener**; then the two listeners will normally compete and only one will receive each message. With brokers/providers that support explicit destination types, `jakarta.jms.Topic` can be used to avoid name ambiguity.

## 6. Configuring Durable or Shared Subscriptions in Spring JMS

When messages need to be retained while a business service is offline, use a **dedicated factory for durable Topic**. This example is a configuration extension; if added to the application above, declare the bean in a `@Configuration` class and the listener in a `@Component`, and configure a broker with persistence if you want to test recovery across broker restarts.

~~~java
@Bean
DefaultJmsListenerContainerFactory durableTopicFactory(
        ConnectionFactory connectionFactory) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("reporting-service"); // Stable, unique identity for the connection
    factory.setConcurrency("1");               // Unshared durable: single consumer only
    factory.setSessionTransacted(true);
    return factory;
}
~~~

~~~java
@JmsListener(
    destination = "events.orders",
    subscription = "reporting-orders",
    containerFactory = "durableTopicFactory"
)
public void onEvent(String event) {
    System.out.println("reporting <- " + event);
}
~~~

Meaning:
- `setPubSubDomain(true)`: destination is a Topic.
- `setSubscriptionDurable(true)`: the broker retains the subscription after the consumer closes.
- `setClientId("reporting-service")` and `subscription = "reporting-orders"`: stable unshared durable identity to reconnect to the exact backlog; do **not** let two concurrently running processes use the same unshared durable/client ID.
- `setSessionTransacted(true)`: if the listener throws an exception, the JMS session rolls back so the message has a chance for redelivery according to provider configuration. Does not automatically merge database commit and JMS commit into a distributed transaction.

To have multiple replicas **share load on the same subscription**, change the design to shared durable with `factory.setSubscriptionShared(true)` together with `setSubscriptionDurable(true)` and a consistent subscription name. The provider must support JMS 2.0+/Jakarta Messaging shared subscriptions. With shared durable, each message goes to **one replica in the group**, not every replica. You must standardize how client IDs and connections are used in actual deployment environments; do not copy an unshared configuration with a fixed `clientId` into every pod and raise `concurrency`.

### Quick Selection by Requirement

- Must deliver to **both accounting and analytics**: create two independent subscriptions on the same Topic.
- Accounting has 5 replicas, but each event must be processed by accounting only once per consumption stream: use **one shared subscription for accounting**; analytics has its own separate subscription.
- Analytics may temporarily go offline and needs to catch up: use a **durable subscription**, with appropriate retention/TTL configuration.
- Subscriber only needs to know the "latest state" and can reload data on reconnect: consider **non-durable** to avoid unnecessary backlog.

## 7. Message Selectors, Ordering, and Reliability

### Receiving Only Matching Events

`@JmsListener` has a `selector` attribute accepting a JMS selector expression. Example of a publisher attaching the `region` property:

~~~java
topicTemplate.convertAndSend("events.orders", "OrderCreated:43", message -> {
    message.setStringProperty("region", "VN");
    return message;
});
~~~

Listener interested only in the Vietnam market:

~~~java
@JmsListener(
    destination = "events.orders",
    containerFactory = "topicListenerFactory",
    selector = "region = 'VN'"
)
public void onOrderCreatedInVn(String text) {
    System.out.println("VN <- " + text);
}
~~~

Selectors evaluate against **JMS headers/properties**, not by querying fields inside the `OrderCreated:43` string. Messages without a matching `region` will not match. Avoid changing the selector of an active durable subscription without understanding the impact on the existing subscription and backlog.

### Delivery, Acknowledgment, and Transactions

1. **Acknowledgment is per subscription.** A committing does not cause B to commit; B failing can trigger redelivery to B without affecting A.
2. **Persistent delivery does not replace durable subscriptions.** To receive messages published while the consumer is offline, the subscription must be durable **and already exist**, and the broker must persist messages according to appropriate policies.
3. **Do not infer business-level exactly-once from JMS.** After a crash, timeout, rollback, or a DB write that committed before JMS commit, the same event can be reprocessed. Design **idempotent** consumers using an event ID/business key, unique constraint, or inbox/deduplication.
4. **Ordering is scoped to guaranteed delivery semantics, not global completion order across the system.** Subscriptions run independently; parallel processing, selectors, retries, and multiple producers can cause logs across services to differ in order. If per-order sequence is required, design sequential keys/processing streams and verify broker capabilities.
5. **Do not catch an exception and treat processing as complete.** If a listener swallows an error, the transaction may commit and the message will be acknowledged even though business logic failed. Explicitly define retries, dead-letter queues (DLQ), backoff, maximum delivery attempts, and alerting.
6. **Do not treat a Topic as an event store.** Replaying history, retaining events for months, and querying by time have separate requirements; standard JMS Topics/subscriptions are subject to TTL, quotas, and broker policies.

### Operational Checklist

Monitor at minimum: published and consumed message counts per subscription; backlog/lag of durable subscriptions; redelivery counts and DLQ; listener connection status; message TTL, size, and broker quotas. Use stable Topic and subscription names, manage payload schema versioning, avoid logging sensitive data, and test consumer restarts, rollbacks, duplicates, and slow processing scenarios.

## 8. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| "A Topic stores every message for all future subscribers." | Non-durable misses messages while offline; durable only receives backlog starting from when the subscription was created, subject to broker policy. |
| "If 3 instances subscribe to a Topic, all 3 definitely receive every message." | You must ask whether those are **3 independent subscriptions** or **3 consumers of the same shared subscription**. |
| "Setting `pubSubDomain=true` on the producer is enough." | The listener container must also resolve to Topic correctly; misconfiguration easily leaves one side talking to a Queue of the same name. |
| "Durable means end-to-end exactly-once." | Durable preserves backlog; the application still needs to handle duplicates, retries, and transaction boundaries. |
| "Increase concurrency on unshared durable to scale." | Unshared durable allows only one active consumer; for multiple consumers, use a shared subscription with a compatible provider. |
| "Selectors can filter JSON body content." | JMS selectors filter headers/properties; to filter by business fields, the publisher must place the needed attributes into JMS properties or use appropriate routing. |

## 9. Self-Check Exercise

**Scenario:** Topic `orders.created` has three subscriptions: `accounting` durable unshared, `analytics` non-durable unshared, and `notifications` shared durable with two consumers N1, N2. When event `E7` is published, analytics is offline; the other two groups are active.

1. How many **subscriptions** receive/retain `E7`? Why?
2. Do N1 and N2 each receive a copy of `E7`?
3. If accounting goes offline before `E8` and comes back online after `E8`, what conditions allow it to catch up?
4. If accounting wrote to the DB but the application crashed before committing JMS, what failure must be guarded against?

**Answers:** (1) Two: accounting and notifications; non-durable offline analytics does not retain E7. (2) No: within the same shared subscription, only one consumer processes the E7 copy. (3) The durable subscription already existed, has the exact same identity, and the broker still retains E8 per storage/TTL policies. (4) E8 can be redelivered and write duplicate data to the DB; use idempotency/deduplication and appropriate transaction design.

## 10. Official Reference Documentation

- [Jakarta Messaging 3.1 — Publish/subscribe model and subscription lifecycle](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
- [Spring Framework — JMS annotation-driven listener](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Framework — JMS listener, transaction and acknowledgement](https://docs.spring.io/spring-framework/reference/integration/jms/using.html).
- [Spring — Getting Started: Messaging with JMS](https://spring.io/guides/gs/messaging-jms/).
