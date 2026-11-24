# Configuring selector, concurrency, and subscription with @JmsListener in Spring JMS

## 1. Learning Objectives

`@JmsListener` lets Spring Framework register a Java method to **receive and process JMS messages asynchronously**. However, simply annotating a method with `@JmsListener(destination = "...")` solves only a small part of consumer design. To run properly against a real broker, you must also answer three questions:

1. **Selector:** Which messages in the destination should this consumer receive?
2. **Concurrency:** At a given moment, how many JMS consumers/sessions are concurrently receiving messages for this listener?
3. **Subscription:** If the destination is a Topic, which subscription does the application own, does it retain backlog while offline, and do multiple instances share one subscription or does each instance receive its own copy?

These three choices interact directly. For example:
- A Queue has two worker groups using selectors `region = 'EU'` and `region = 'APAC'`.
- The EU worker uses `concurrency = "2-4"` for parallel processing, while the APAC worker only needs `"1-1"`.
- A Topic emits `order.paid` events; Billing and Notification must receive **two independent copies**, while three replicas of Billing must **share load within the same subscription** rather than processing each event three times.
- Billing must retain messages when no replica is online: it needs a **durable subscription** identified stably across deployments.

This lesson belongs to the **@JmsListener** section of Spring Framework – JMS. Examples use Java 17+, Spring Framework 6.x, Spring Boot 3.x, and `jakarta.jms.*`. When working with a vendor other than Artemis, check the broker/client characteristics and test on that exact environment.

### After This Lesson You Will Be Able To

- Correctly read the meanings of `id`, `destination`, `containerFactory`, `selector`, `concurrency`, and `subscription`.
- Write valid selectors for JMS headers/message properties, understanding NULL and value types.
- Choose concurrency based on Queue/Topic, throughput, thread-safety, and ordering importance.
- Distinguish the four subscription modes: non-durable/unshared, non-durable/shared, durable/unshared, durable/shared.
- Configure `DefaultJmsListenerContainerFactory` separately for Queues and Topics; understand `pubSubDomain`, `subscriptionDurable`, `subscriptionShared`, and `clientId`.
- Run a Queue demo with two listeners using different selectors and verify unmatched messages remain in the Queue.
- Design migrations, monitoring, retry/transactions, and scaling without accidentally creating duplicate subscriptions or losing backlog.

## 2. Three Configuration Axes Are Three Different Problems

~~~text
                           JMS broker
                              |
             +----------------+----------------+
             |                                 |
         Queue orders.jobs                Topic sales.events
             |                                 |
       selector on consumer             selector on subscription
             |                                 |
       concurrency = 2-4                 durable? shared?
             |                                 |
       N consumers on same Queue        subscription billing
       competing for jobs               subscription notification
                                               |
                                    Billing: can be shared across 3 replicas
                                    Notification: separate subscription
~~~

| Axis | Question | Where is it usually configured? | What it does NOT solve by itself |
|---|---|---|---|
| **Selector** | Is the message selected? | `@JmsListener(selector=...)` or endpoint/container. | Does not parse JSON bodies, enforce authorization, or handle ACK/retry. |
| **Concurrency** | How many consumers/sessions run concurrently? | `@JmsListener(concurrency=...)`; `DefaultJmsListenerContainerFactory.setConcurrency(...)`. | Does not turn a Queue into a Topic; does not create exactly-once semantics. |
| **Subscription** | Which Topic copy is received, and is it durable/shared? | `@JmsListener(subscription=...)` and factory `setPubSubDomain`/`setSubscriptionDurable`/`setSubscriptionShared`/`setClientId`. | Does not guarantee timely consumer processing, nor migrate backlog on rename. |

**A misconfiguration on the subscription axis can make concurrency behave opposite to your intent.** If each Topic replica creates an independent subscription, every replica can receive the same event. Meanwhile, on a Queue with competing consumers, each delivery normally goes to only one consumer, although redelivery can still cause the same business event to be processed again.

## 3. Key Attributes of @JmsListener

~~~java
@JmsListener(
    id = "euInvoiceWorker",
    destination = "orders.jobs",
    containerFactory = "queueListenerFactory",
    selector = "eventType = 'INVOICE' AND region = 'EU'",
    concurrency = "2-4"
)
public void processInvoice(String payload) {
    // Business handler
}
~~~

This is a code snippet inside a `@Component` with appropriate Spring JMS configuration.

| Attribute | Purpose | Values/limits |
|---|---|---|
| `destination` | Name of Queue/Topic to receive from, resolved via `DestinationResolver`. | Required; the name string alone does not determine Queue vs. Topic. |
| `id` | Unique ID of the listener container in the Spring registry. | Should be stable for observability, stop/start, and diagnostics. |
| `containerFactory` | `JmsListenerContainerFactory` bean that builds the container for the listener. | If omitted, defaults to bean `jmsListenerContainerFactory` or configured default. |
| `selector` | Message filter expression in JMS selector syntax. | Only TRUE matches; does not read JSON body. |
| `concurrency` | Consumer/session bounds for this specific endpoint. | Overrides factory concurrency; supports forms like `"2-4"` or `"4"`. |
| `subscription` | Subscription name when the listener runs on a Topic with a named subscription. | Not the Topic name, not a Queue name. Should be explicit for durable/shared. |

**There are no** `pubSubDomain`, `subscriptionShared`, or `subscriptionDurable` attributes directly on `@JmsListener`. Those choices come from the listener container factory. Simply adding `subscription="billing"` without enabling Topic/durable/shared appropriately will not produce the desired model.

`@JmsListener` can be repeated on a single method when multiple endpoints are needed. Each annotation creates a separate listener endpoint; reusing a method does not mean the endpoints share a subscription or transaction.

### Configuration Precedence

- The factory sets shared defaults for many listeners, e.g., `setConcurrency("1-3")`, `setSessionTransacted(true)`.
- Annotation `@JmsListener(concurrency="2-4")` **overrides concurrency** for that endpoint.
- Annotation `containerFactory="topicSharedFactory"` selects a Topic factory instead of using the default Queue factory.
- Annotation `subscription="billing-ledger-v1"` sets the subscription **name**; the factory still decides shared/durable/Topic.
- Property placeholders from `application.yml` can be used. Final values must resolve before the container creates the JMS consumer.

## 4. Selector in @JmsListener

A selector is a **boolean condition expression**, not a SQL statement with `SELECT` or a JSON query. The provider evaluates the expression against valid JMS message headers and properties.

### 4.1. Valid Examples

~~~sql
eventType = 'INVOICE'
region = 'EU' AND amount >= 100
eventType IN ('INVOICE', 'REFUND')
amount BETWEEN 100 AND 500
priorityLevel >= 7 AND ready = TRUE
JMSCorrelationID = 'request-42'
region IS NULL OR region <> 'EU'
~~~

Use single quotes for Strings; String literals are case-sensitive; property names are also case-sensitive. `setStringProperty("amount","100")` is not equivalent to `setIntProperty("amount",100)` when the selector performs a numeric comparison.

Spring does not automatically convert JSON bodies into JMS properties. The producer must attach properties to filter on when sending:

~~~java
jmsTemplate.convertAndSend("orders.jobs", "issue-invoice-42", m -> {
    m.setStringProperty("eventType", "INVOICE");
    m.setStringProperty("region", "EU");
    m.setIntProperty("amount", 200);
    m.setBooleanProperty("ready", true);
    m.setJMSCorrelationID("request-42");
    return m;
});
~~~

This snippet belongs in a service with an injected `JmsTemplate`. The properties live on `jakarta.jms.Message`; if they only exist inside the JSON payload, the selector `region = 'EU'` will not see them.

### 4.2. Standard Headers Available

Per Jakarta Messaging 3.1, the six JMS headers directly referenced in standard selectors are:

| Header | Type in selector | Example |
|---|---|---|
| `JMSDeliveryMode` | String: `'PERSISTENT'` or `'NON_PERSISTENT'` | `JMSDeliveryMode = 'PERSISTENT'` |
| `JMSPriority` | Integer 0..9 | `JMSPriority >= 7` |
| `JMSMessageID` | String | `JMSMessageID = 'ID:message-42'` |
| `JMSTimestamp` | Epoch milliseconds number | `JMSTimestamp > 1700000000000` |
| `JMSCorrelationID` | String | `JMSCorrelationID = 'request-42'` |
| `JMSType` | String | `JMSType = 'invoice.v1'` |

`JMSReplyTo`, `JMSDestination`, `JMSExpiration`, `JMSDeliveryTime`, and `JMSRedelivered` **are not part of the standard selector header list**, even though the `Message` API can read them. `JMSXDeliveryCount` is a provider-set property upon delivery; selecting on such properties is not portably defined, so do not use a selector like `JMSXDeliveryCount > 3` to replace a redelivery/DLQ policy.

### 4.3. NULL, UNKNOWN, and Unmatched Messages

When a message lacks `region`, the condition `region = 'EU'` evaluates to UNKNOWN. `NOT UNKNOWN` is still UNKNOWN; only TRUE messages are delivered.

| Selector | Message missing `region` |
|---|---|
| `region = 'EU'` | Does not match |
| `region <> 'EU'` | Does not match |
| `region IS NULL` | Matches |
| `region = 'EU' OR region IS NULL` | Matches |

If the producer renames a property or changes a type from String to number, the consumer can **silently receive no messages** without any exception in the listener. Monitor Queue depth, message age, and selector/version contracts.

### 4.4. Selectors and Security

**Do not use selectors as a security boundary.** A producer with send permission can set `tenantId` or `region` to anything. Broker ACLs, namespace isolation, and business authorization verification must remain independent of selector matching.

Never concatenate unvalidated user input into dynamic selectors. JMS selectors do not have bind parameters like JDBC prepared statements; prefer fixed expressions or proper allowlisting/escaping.

## 5. What Does Concurrency Actually Control?

With `DefaultMessageListenerContainer`, concurrency corresponds to **the number of consumers/sessions** the container can maintain to invoke the listener method. Multiple consumers can process messages concurrently on **different threads**, while a single JMS `Session` still obeys its sequential usage rules.

Example:

~~~java
@JmsListener(
    destination = "orders.jobs",
    containerFactory = "queueListenerFactory",
    concurrency = "2-4"
)
public void handle(String payload) {
    // One invocation processes one message.
}
~~~

With a container supporting scaling, `"2-4"` specifies **a minimum of 2 and maximum of 4** consumers; the actual count depends on load and scheduling. Each method invocation can run concurrently, so any shared mutable fields in the listener class must be thread-safe.

### 5.1. Distinguishing "4", "2-4", and "4-4"

| String | Meaning on `DefaultMessageListenerContainer` |
|---|---|
| `"1-1"` | Fixed one consumer. |
| `"4"` | Concurrency ceiling of 4; default lower bound is 1. Not equivalent to fixed 4. |
| `"2-4"` | Minimum 2 core/concurrent consumers, scalable up to 4. |
| `"4-4"` | Fixed 4 consumers. |
| `""` (omitted) | Inherits configuration from the listener factory. |

These bounds are **configuration intent**, not a guarantee that the exact thread count in the table is active at all times. Provider quotas, pools, thread scheduling, connection count, recovery, and broker load can alter the actual active consumer count.

### 5.2. Scaling Across Deployment Replicas

If a listener has `concurrency="2-4"` and is deployed across **3 replicas**, the total consumers for that endpoint in the cluster can grow up to:

~~~text
maxConsumersCluster ≈ 3 replicas × 4 consumers/replica = 12 consumers
~~~

This is a **theoretical budget** before accounting for session/connection pools, broker limits, task executors, and other listeners. Do not mistake "concurrency=4" for four jobs across the whole cluster. With multiple endpoints and replicas running simultaneously, total resource usage can escalate rapidly.

### 5.3. Does Increasing Concurrency Always Make It Faster?

Potentially, for Queues with many independent messages and I/O-bound handlers. However, it is not guaranteed:
- Broker prefetch may buffer many messages onto one consumer, starving others.
- The DB pool and downstream APIs become bottlenecks.
- Message groups/ordering/key affinity restrict parallel distribution.
- Consumers contend for locks or modify the same business entity.
- Adding threads increases redeliveries on container restarts or breaks sequentiality.

Tune based on **throughput, p95/p99 handler latency, Queue depth, consumer utilization, DB pool, prefetch**, and memory. Do not look only at thread counts.

### 5.4. Concurrency and Ordering

A Queue with one consumer, without priorities or special handling, preserves order more easily. With multiple consumers, `@JmsListener(concurrency="4-4")` does not guarantee **business completion order** matches send order. Messages A and B may be delivered in order, yet B finishes first because A makes a slow database call.

If ordering per `orderId` is required, consider:
- Keeping concurrency low for partitions requiring ordering.
- Message grouping or key-based partitioning if supported by the broker, verified with integration tests.
- Sequence numbers and idempotency at the business layer.
- Never using sleep or synchronizing the entire handler as an ad-hoc fix.

## 6. Queues and Topics: Concurrency Does Not Mean the Same Thing

| Aspect | Queue | Non-shared Topic | Shared subscription Topic |
|---|---|---|---|
| How many consumers receive one message? | Usually **one** consumer chosen from eligible ones. | Each separate subscription can receive **one copy**. | One message is delivered to **one consumer within the same subscription**. |
| Scaling consumers | Raising concurrency usually distributes Queue load. | Adding independent consumers/subscriptions can cause **duplicate copies** per consumer. | Multiple consumers share load within the same subscription. |
| Selector | Selects messages for the consumer; unmatched messages may remain in Queue. | Filters messages entering the subscription on publish. | Same selector applies to the shared subscription. |
| Offline backlog | Queues usually retain messages per retention/expiry. | No, if non-durable subscription was removed. | Yes, if subscription is **durable** and broker policy allows. |
| Typical use case | Job/command needing one worker to process. | Fan-out to independent services. | Fan-out across services, then load-balance replicas within each service. |

**Do not enable `pubSubDomain=true` and mechanically raise `concurrency="5-10"`.** With a non-shared Topic, consumers may form independent subscriptions, multiplying handler invocations unexpectedly. With an unshared durable subscription, multiple concurrent consumers on the same subscription are usually **invalid** and may be rejected by the broker. Scale Topics via shared subscriptions only when supported by the contract/provider.

## 7. Four Topic Subscription Types to Distinguish

Jakarta Messaging 2.0+ (Jakarta Messaging 3.x in Spring 6) distinguishes:

| Type | Durable? | Shared? | Concurrent consumers in same subscription | When all consumers go offline |
|---|---|---|---|---|
| **Unshared non-durable** | No | No | 1 | Subscription ends; new messages are not retained. |
| **Shared non-durable** | No | Yes | Multiple | Subscription ends when last consumer closes; future backlog is not retained. |
| **Unshared durable** | Yes | No | 1 | Subscription persists; matching messages can be retained until ACK/expiry. |
| **Shared durable** | Yes | Yes | Multiple | Subscription persists and retains matching backlog while no consumer is online. |

*Durable* describes **subscription lifecycle**, while *shared* describes **whether multiple consumers can consume from one subscription together**. The two properties are independent; shared is not automatically durable and durable is not automatically shared.

### 7.1. Non-Durable / Unshared Topic

By default, if you only set `setPubSubDomain(true)` without enabling shared/durable, each consumer can own a separate non-durable subscription. If you deploy three replicas, each replica can receive a copy of every message. This fits per-instance fan-out (e.g., local cache invalidation) but is **wrong** if a Billing event should be processed once across the replica group.

When consumers close and the non-durable subscription ceases to exist, messages published in the meantime are not accumulated for catch-up later. Persistent messages on a Topic do not automatically make a non-durable subscription durable.

### 7.2. Shared Non-Durable Topic

A subscription has a **name** and multiple consumers can share messages. While at least one consumer is active, each matching message is delivered to only one consumer in that subscription (aside from redelivery). When the last consumer closes, the subscription is deleted and retains no backlog from subsequent publishes.

Choose this when you want load sharing on a Topic and can tolerate dropping messages while the entire application is offline. Shared subscriptions do not automatically guarantee database-level exactly-once processing.

### 7.3. Durable / Unshared Topic

The subscription has an identity consisting of **subscription name + client identifier**. Jakarta Messaging requires a client ID for **unshared durable**. Only one active consumer is allowed on this subscription at a time; the same client ID cannot be used concurrently across multiple connections/instances.

Use this when a consumer must retain messages sent while offline yet only one active consumer is desired. **`Concurrency="1-1"`** is the safe setting; scale via sequential/active-passive failover, not by giving five replicas the same client ID and hoping the broker load-balances them.

### 7.4. Shared Durable Topic

The subscription has a stable name, multiple consumers share load within a group, and the broker continues retaining matching messages when the group is offline. Under Jakarta Messaging, **client ID may be omitted** for shared durable subscriptions; if set, consumers joining the same subscription must use compatible identities. Avoid hardcoding identical client IDs across independent connections where the provider rejects duplicate identities.

This is typically the right choice for a multi-replica service group where each event must reach **one replica in the group** and backlog must survive group downtime. Different business groups must use **different subscription names** so each group receives its own copy.

~~~text
Topic: sales.order.paid
   |
   +-- shared durable subscription "billing-ledger-v1"
   |       +-- billing replica A (consumer 1)
   |       +-- billing replica B (consumer 2)
   |       +-- billing replica C (consumer 3)
   |       -> each delivery goes to one consumer in the Billing group
   |
   +-- shared durable subscription "notification-mail-v1"
           +-- notification replica A
           +-- notification replica B
           -> each delivery goes to one consumer in the Notification group

The same event can have two copies:
one for Billing and one for Notification.
~~~

**Wrong subscription identity can lose backlog.** Renaming, changing selector/destination, or switching between shared and unshared requires a migration plan. In some cases the provider treats it as a new subscription or rejects it due to incompatible existing identity; it is not a harmless string update.

## 8. Configuring DefaultJmsListenerContainerFactory for the Right Destination Type

The container factory determines endpoint semantics. One application can have **multiple factories**, e.g., Queue commands and Topic events.

### 8.1. Factory for a Queue with Session Transactions

`src/main/java/example/jms/QueueConsumerConfiguration.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class QueueConsumerConfiguration {

    @Bean("queueListenerFactory")
    DefaultJmsListenerContainerFactory queueListenerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-4");
        factory.setReceiveTimeout(1_000L);
        return factory;
    }
}
~~~

Explanation:
- `setPubSubDomain(false)` means when resolving names dynamically, the listener works with a **Queue**.
- `setSessionTransacted(true)` creates a local JMS transaction for receiving/processing messages. An exception escaping the handler normally rolls back the session; the broker determines the redelivery policy.
- `setConcurrency("1-4")` is the general setting; `@JmsListener(concurrency="2-2")` can override it for a specific endpoint.
- `setReceiveTimeout(1_000L)` controls container receive polling, **distinct from `JmsTemplate.setReceiveTimeout`** for synchronous receives.
- The factory does not define a specific physical Queue: the name comes from `@JmsListener(destination=...)`.

### 8.2. Factory for a Shared Durable Topic

`src/main/java/example/jms/SharedDurableTopicConfiguration.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class SharedDurableTopicConfiguration {

    @Bean("sharedDurableTopicFactory")
    DefaultJmsListenerContainerFactory sharedDurableTopicFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);          // Topic, not Queue
        factory.setSubscriptionDurable(true);   // Retain backlog when offline
        factory.setSubscriptionShared(true);    // Multiple consumers on same sub
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-2");
        return factory;
    }
}
~~~

This is a complete configuration class when placed in a project with JMS infrastructure. You need **a broker/client supporting shared durable subscriptions** (Jakarta Messaging 2.0+ semantics). `setClientId` is omitted in the example because shared durable may not require a client ID per the standard; when a provider requires extra config, follow that provider's compatibility matrix rather than assigning the same client ID across replicas randomly.

Accompanying listener:

`src/main/java/example/jms/BillingTopicListener.java`:

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class BillingTopicListener {

    @JmsListener(
            id = "billingPaidEvents",
            destination = "sales.order.paid",
            containerFactory = "sharedDurableTopicFactory",
            subscription = "billing-ledger-v1",
            selector = "eventType = 'ORDER_PAID'",
            concurrency = "2-2")
    public void onOrderPaid(String json) {
        // Illustrative receiving point; in a real project,
        // call an idempotent service to update the ledger.
        System.out.println("Billing event: " + json);
    }
}
~~~

The same application binary across multiple replicas uses **the same topic, subscription name, selector, and shared-durable policy** to join the same group. Each distinct subscription name represents **a separate group receiving its own copy**. When deploying to a real broker, provision the Topic/ACLs/retention and verify the provider's routing configuration.

**Do not run** this Billing Topic listener class alongside the Queue demo in section 11 merely by copying the file without provisioning the Topic/routing. This is a standalone Topic example, independent of the Queue lab.

### 8.3. Factory for an Unshared Durable Topic

If requirements call for **one active consumer** and retaining backlog while offline, the configuration differs:

~~~java
@Bean("unsharedDurableTopicFactory")
DefaultJmsListenerContainerFactory unsharedDurableTopicFactory(
        ConnectionFactory cf) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(cf);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setSubscriptionShared(false);
    factory.setClientId("billing-exclusive-client");
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-1");
    return factory;
}
~~~

This snippet belongs in a `@Configuration` with `@Bean`, `ConnectionFactory`, and `DefaultJmsListenerContainerFactory` imported. On the Topic endpoint, set a stable `subscription`, such as `"billing-exclusive-v1"`. Client ID is mandatory for unshared durable and **must not** be used concurrently by another replica's connection. If the service needs active-active replicas, choose shared durable supported by the broker instead of sharing one unshared client ID across replicas.

### 8.4. Different Factories for Different Contracts

Not every listener has to use one factory. Separate them:
- `queueListenerFactory`: Queue, scalable concurrency.
- `sharedDurableTopicFactory`: Topic, durable/shared, allows multiple consumers on the same subscription.
- `unsharedDurableTopicFactory`: Topic, durable/unshared, concurrency 1 and dedicated client identity.

This is safer than mutating `factory.setPubSubDomain(...)` on a running bean per listener. The container factory creates the container; decide semantics before endpoints are registered.

## 9. Environment-Specific Configuration with Placeholders

Hardcoding production Queues/Topics and selectors often causes deployment errors. Extract them as:

~~~yaml
app:
  jms:
    queue:
      orders: "dev.orders.jobs"
      eu-selector: "eventType = 'INVOICE' AND region = 'EU'"
    topic:
      paid-events: "dev.sales.order.paid"
      billing-subscription: "billing-ledger-v1"
~~~

Referenced by annotations:

~~~java
@JmsListener(
    id = "euInvoiceWorker",
    destination = "${app.jms.queue.orders}",
    selector = "${app.jms.queue.eu-selector}",
    containerFactory = "queueListenerFactory",
    concurrency = "2-4")
public void handle(String payload) {
    // Business code
}
~~~

This is an illustrative method snippet inside a `@Component`. Spring supports property placeholders in annotation attributes. For a **durable** Topic subscription, the subscription name must usually remain **stable across deployments** within the same group and broker namespace; never append a pod ID, deployment timestamp, or random value to `subscription`.

Changing the selector of a durable subscription can cause the provider to consider the contract changed, requiring unsubscribe/recreate or creating a different subscription. Do not assume reloading YAML at runtime automatically updates all JMS consumers while preserving old backlog. If a selector change is needed, plan a migration and test against the broker.

## 10. Concurrency and Subscriptions When Deploying Multiple Replicas

Suppose there are 3 application replicas:

| Configuration | Meaning at scale |
|---|---|
| Queue listener `"2-4"` | Up to about 12 consumers for **one endpoint** across the cluster; competing on the Queue. |
| Non-durable/unshared Topic, one consumer per replica | Each replica can receive its own **copy** of messages; not a load-balanced group. |
| Durable/unshared Topic, same client ID/subscription name | Conflicts if multiple consumers/connections are active; cannot scale this way. |
| Shared non-durable Topic, same subscription identity | Multiple consumers share load while the group is online; completely offline drops new messages. |
| Shared durable Topic, same subscription identity | Multiple consumers share load; retains matching messages while the group is offline. |

**Do not equate thread pool size with consumer count.** A container manages JMS Sessions/consumers and uses a task executor for polling/dispatch; increasing the application's thread pool does not create more JMS consumers if concurrency is capped low. Conversely, raising concurrency when broker/DB pools lack capacity yields no additional throughput.

### 10.1. Listener Objects Must Be Thread-Safe

Invocations of `@JmsListener` on the same singleton bean can run concurrently. Wrong:

~~~java
private int processedCount;

@JmsListener(destination = "orders.jobs", concurrency = "4-4")
public void process(String payload) {
    processedCount++; // Race condition: ++ is not atomic.
}
~~~

This is a class fragment. A safer approach is handling per-message data with local variables, calling stateless/idempotent services, or using `AtomicLong` for simple metrics:

~~~java
private final java.util.concurrent.atomic.AtomicLong processedCount =
        new java.util.concurrent.atomic.AtomicLong();

@JmsListener(destination = "orders.jobs", concurrency = "4-4")
public void process(String payload) {
    processedCount.incrementAndGet();
}
~~~

Even so, `AtomicLong` does not replace transactions/database uniqueness for business correctness when the same event is redelivered. Counting "callback invocations" and "distinct successfully processed business events" are two different metrics.

### 10.2. Sizing Rules

Initial estimate:
- `replicaCount × maxConcurrentConsumersPerReplica` is the JMS consumer ceiling for **one endpoint**.
- If there are N distinct listeners, total consumers can be the sum of ceilings across endpoints; different listeners have different Queue/Topic/subscription semantics.
- Broker prefetch, DB pools, broker connection limits, thread executors, and CPU must be evaluated together.
- Do not scale unboundedly in response to transient Queue depth; budget for arrival rate, transaction duration, and downstream quotas.

## 11. Runnable Lab: Queue with Different Selectors and Concurrency

This lab uses **Java 17 + Spring Boot 3.5.16 + embedded Artemis**. Two `@JmsListener` endpoints share Queue `demo.orders`, each with its own selector:
- `euOrderListener`: receives `kind='ORDER'` and `region='EU'`, with fixed concurrency `"2-2"`.
- `refundListener`: receives `kind='REFUND'`, with fixed concurrency `"1-1"`.

The application sends **four messages**; three match the two listeners, while one `region='US'` message does not match and remains in the Queue for a separate `receiveSelected` call. A `CountDownLatch` and `ConcurrentHashMap.newKeySet()` wait/verify **without depending on thread execution order**.

There is no Topic listener in this lab project; shared durable Topic is illustrated via dedicated configuration code in section 8 to avoid misleading learners about subscription identity, backlog, and Topic creation timing.

### 11.1. Structure

~~~text
jms-listener-routing-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jms/RoutingLabApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-listener-routing-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

Spring Boot dependency management manages compatible `spring-jms`/Jakarta JMS/Artemis versions for that Boot branch. Versions are pinned for reproducibility; in production, use a supported Boot release and patch per security advisories. Requires JDK 17+ and a Gradle version compatible with the Spring Boot plugin.

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.orders
      persistent: false
~~~

`persistent: false` is only to keep the lab lightweight and does **not** demonstrate durability across broker restarts.

### 11.2. Complete Java File

`src/main/java/example/jms/RoutingLabApplication.java`:

~~~java
package example.jms;

import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class RoutingLabApplication {
    private static final String QUEUE = "demo.orders";

    public static void main(String[] args) {
        SpringApplication.run(RoutingLabApplication.class, args);
    }

    @Bean("queueRoutingFactory")
    DefaultJmsListenerContainerFactory queueRoutingFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000L);
        return template;
    }

    static final class Results {
        private final Set<String> entries =
                ConcurrentHashMap.newKeySet();
        private final CountDownLatch latch =
                new CountDownLatch(3);

        void record(String value) {
            if (entries.add(value)) {
                latch.countDown();
            }
        }

        List<String> sortedResults() {
            return entries.stream().sorted().toList();
        }

        void awaitThree() throws InterruptedException {
            if (!latch.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for three matching messages");
            }
        }
    }

    @Bean
    Results results() {
        return new Results();
    }

    @Bean
    RoutingListener routingListener(Results results) {
        return new RoutingListener(results);
    }

    static final class RoutingListener {
        private final Results results;

        RoutingListener(Results results) {
            this.results = results;
        }

        @JmsListener(
                id = "euOrderListener",
                destination = QUEUE,
                containerFactory = "queueRoutingFactory",
                selector = "kind = 'ORDER' AND region = 'EU'",
                concurrency = "2-2")
        public void onEuOrder(String payload) {
            results.record("EU_ORDER=" + payload);
        }

        @JmsListener(
                id = "refundListener",
                destination = QUEUE,
                containerFactory = "queueRoutingFactory",
                selector = "kind = 'REFUND'",
                concurrency = "1-1")
        public void onRefund(String payload) {
            results.record("REFUND=" + payload);
        }
    }

    @Bean
    ApplicationRunner runCases(JmsTemplate template, Results results) {
        return args -> {
            send(template, "eu-01", "ORDER", "EU");
            send(template, "eu-02", "ORDER", "EU");
            send(template, "refund-03", "REFUND", "EU");
            send(template, "order-us-04", "ORDER", "US");

            results.awaitThree();

            List<String> observed = results.sortedResults();
            List<String> expected = List.of(
                    "EU_ORDER=eu-01",
                    "EU_ORDER=eu-02",
                    "REFUND=refund-03");

            if (!observed.equals(expected)) {
                throw new IllegalStateException(
                        "Unexpected listener result: " + observed);
            }

            for (String entry : observed) {
                System.out.println(entry);
            }

            // ORDER/US message does not match the two listeners above.
            Message remaining = template.receiveSelected(
                    QUEUE, "kind = 'ORDER' AND region = 'US'");

            if (!(remaining instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "ORDER/US message was not retained in the Queue");
            }
            System.out.println("UNMATCHED=" + text.getText());
        };
    }

    private static void send(
            JmsTemplate template, String payload,
            String kind, String region) {

        template.convertAndSend(QUEUE, payload, message -> {
            message.setStringProperty("kind", kind);
            message.setStringProperty("region", region);
            return message;
        });
    }
}
~~~

### 11.3. Why Does the Demo Not Rely on Asynchronous Order?

`@JmsListener` runs on listener threads; the two EU consumers can receive `eu-01` and `eu-02` in parallel. Which finishes first is not guaranteed. Therefore:
- `Results.entries` uses a concurrent set rather than a non-thread-safe `HashSet`.
- `CountDownLatch(3)` waits for the three eligible messages to be handled by callbacks.
- `sortedResults()` sorts results before printing.
- The US message stays in the Queue and is received afterward by `receiveSelected`; the other two listeners do not take it because it does not match their selectors.

`Results.record` only proves the callbacks were invoked and stored in memory; it is **not** a business database commit and does not replace outbox/idempotency. The demo sets `setSessionTransacted(true)` to illustrate listener transactions, while actual redelivery, max attempts, and DLQ are separate broker configurations.

### 11.4. Running and Checking Stdout

From the `jms-listener-routing-lab` directory, with the Gradle Wrapper present:

~~~bash
./gradlew bootRun
~~~

On PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Without the Wrapper, using a compatible pre-installed Gradle:

~~~bash
gradle bootRun
~~~

After Spring Boot/Artemis startup logs, the lines **printed by the program itself** on success are:

~~~text
EU_ORDER=eu-01
EU_ORDER=eu-02
REFUND=refund-03
UNMATCHED=order-us-04
~~~

The code validates results before printing. Printing is sorted, so stdout order is deterministic by code, **which does not mean the broker guarantees message completion in producer send order**.

A congested environment could exceed 15 seconds before all three listeners finish, causing the Runner to throw an exception; in that case inspect Artemis logs, listener consumer count, Queue config, and thread scheduling. That is a lab timeout, not standard JMS behavior.

### 11.5. Controlled Experiments

1. Change the EU selector to `region = 'APAC'` while keeping the same messages: the two EU orders no longer match and the Runner times out.
2. Change `concurrency = "2-2"` to `"1-1"`: the two EU messages are handled through one consumer; results stay accurate while active concurrency changes.
3. Add a third consumer **with no selector** on the same Queue: it can steal messages from the two listeners; the demo no longer produces deterministic output.
4. Change `setStringProperty("region", region)` to property name `Region`: the `region` selector stops matching because identifiers are case-sensitive.
5. Throw an exception in a listener and measure redelivery/DLQ per broker policy; do not treat `sessionTransacted=true` as sufficient configuration for poison messages.

## 12. End-to-End Topic Example in Terms of Contract

When using a Topic, **publisher and subscribers** must agree on:
- Physical Topic name: `sales.order.paid`.
- Message type/selector properties: `eventType = 'ORDER_PAID'`.
- Subscription identities: `billing-ledger-v1` and `notification-mail-v1`.
- Subscription mode: shared durable if multiple replicas per group need offline backlog retention.
- Client ID policy: never hardcode duplicate client IDs arbitrarily when replicas use shared subscriptions.
- Transaction/ACK, retention, expiry, redelivery, DLQ, and replay.

A Topic publisher in Spring JMS can be configured separately:

~~~java
@Bean("topicPublisher")
JmsTemplate topicPublisher(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setPubSubDomain(true);
    return template;
}
~~~

This snippet belongs in a `@Configuration` importing `@Bean`, `ConnectionFactory`, and `JmsTemplate`. Sending an event:

~~~java
topicPublisher.convertAndSend(
        "sales.order.paid", jsonPayload, m -> {
            m.setStringProperty("eventType", "ORDER_PAID");
            return m;
        });
~~~

This send snippet requires valid `topicPublisher` and `jsonPayload` variables in the application. **Use a real Topic publisher**: do not take a default Queue `JmsTemplate`, send with the same name string, and assume the broker infers Topic automatically. With Artemis, a Topic needs proper multicast addresses/subscription queues/routing; you can provision via `spring.artemis.embedded.topics` for an isolated lab or via managed broker configuration.

### When Do Subscribers Receive?

- Billing and Notification are two independent subscriptions: each group can receive one copy of matching events.
- Within Billing's shared subscription, replicas share messages that entered Billing's backlog; not every replica receives a copy.
- With a non-durable subscription deleted while offline, events published afterward do not appear when the group comes back online.
- With a durable subscription, the broker retains backlog per policy for an existing subscription, but **does not retroactively deliver** events published before the subscription was created.
- Changing a selector after a subscription exists can fail or recreate the subscription depending on subscription type and provider; plan a concrete cutover.

## 13. Creating Subscriptions, Changing Selectors, and Lifecycle Management

A small-looking change:

~~~text
Before: selector = eventType = 'ORDER_PAID'
After:  selector = eventType IN ('ORDER_PAID', 'ORDER_REFUNDED')
~~~

for a durable Topic **is not simply changing a condition to retroactively receive all past messages**.

Recommended procedure:

1. Identify the Topic, subscription name, client identity, shared/durable policy, selector, and which application replicas use it.
2. Inspect broker backlog and retention on the old subscription; verify which properties/data types producers actually send.
3. If an incompatible selector change is needed, create a new subscription version (e.g., `billing-ledger-v2`) through an approved process, or stop consumers and use provider-supported subscription reconfiguration.
4. While both subscriptions are active during cutover, note **the same business event may be delivered to both**, so consumers must be idempotent and prevent duplicate side effects.
5. Verify the consumer receives the new events properly, the old backlog drained cleanly, and the new subscription's metrics are stable.
6. Only delete/unsubscribe the old subscription after proving its backlog is no longer needed and with owner approval; never silently delete it on startup.

An easily overlooked pitfall: when `subscription` is omitted, Spring can generate a default name based on the **fully-qualified listener method name**. Refactoring packages/classes/methods can alter the default identity. Therefore, for durable/shared subscriptions, use **owner-managed stable names** independent of Java methods or replica IDs.

### Client ID and Replicas

With unshared durable subscriptions, client ID is part of the identity and must be configured. Two active applications sharing a client ID may be rejected by the provider or suffer state access conflicts. With shared durable subscriptions, client ID is not required by the standard; if set, align the identity and how the broker manages connections. Test single-replica restarts, full-group downtime, and replica scaling directly.

## 14. Transactions, ACK, Retries, and DLQ Are Independent of Selectors

**A selector match does not mean a message was processed successfully.** A message can be selected, the callback throws an exception, and the broker redelivers the same message. High concurrency makes duplicate business side-effect scenarios more complex.

In `DefaultJmsListenerContainerFactory`:

~~~java
factory.setSessionTransacted(true);
~~~

creates a **local JMS transaction** for the listener. If the handler throws an exception and the transaction rolls back, the provider can redeliver per policy. With `DefaultMessageListenerContainer`'s default `AUTO_ACKNOWLEDGE`, acknowledgement can happen before the method executes, offering no guarantee of redelivery when the handler throws. Hence production must configure transaction/ack deliberately.

Important:
- JMS transactions do not automatically merge with database transactions. Committing DB and then failing JMS commit can cause redelivery and duplicate side effects.
- Use business event IDs, unique constraints, or an inbox/idempotent consumer for non-repeatable operations.
- The broker sets max delivery attempts, backoff, and DLQ; `@JmsListener(selector=...)` does not solve poison messages.
- Never swallow all exceptions in the handler and return normally if business logic needs rollback/retry.
- With shared durable subscriptions, delivering once to one consumer in the subscription **does not** imply system-wide exactly-once; transaction failures/redeliveries can still cause reprocessing.
- A selector filtering on missing properties can build up an unconsumed backlog forever; without monitoring, you might falsely think the system has no work.

## 15. Observing Listener Containers and Changing State

An endpoint with an explicit `id`:

~~~java
@JmsListener(
    id = "euOrderListener",
    destination = "orders.jobs",
    concurrency = "2-4")
public void handle(String payload) {
    // Business handler
}
~~~

can be managed via `JmsListenerEndpointRegistry`:

~~~java
package example.jms;

import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ListenerControl {
    private final JmsListenerEndpointRegistry registry;

    public ListenerControl(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);
        return container != null && container.isRunning();
    }
}
~~~

This is a complete class inside a Spring context with JMS infrastructure. `id` is the **Spring listener container ID**, not the subscription name and not the Queue/Topic name. Calling `stop()/start()` is used for controlled lifecycle management; it **does not automatically delete a durable subscription**. Do not start/stop containers from arbitrary HTTP requests without authorization, graceful shutdown, and backlog checks.

### Recommended Metrics

| Metric/field | Used for |
|---|---|
| `listenerId` / factory / destination | Identifying exact endpoint and Queue/Topic. |
| selector ID / version | Knowing which properties/filters are active after deploy. |
| active consumers, scheduled consumers | Comparing against `concurrency` configuration. |
| queue depth, oldest message age, prefetch | Detecting backlogs and uneven distribution. |
| subscription name, durable/shared, online consumers | Distinguishing lost subscribers from insufficient capacity. |
| processing success/failure, latency, redelivery count | Measuring business progress and reliability. |
| DLQ count / expiry count | Detecting poison messages and expirations. |
| DB pool/external API latency | Diagnosing bottlenecks before adding consumers. |

Do not put unbounded dynamic user IDs/tenant IDs into metric labels or subscription names; avoid cardinality explosions. Be careful not to log sensitive payloads.

## 16. Tuning Throughput, Prefetch, and Resources

Start from workload and SLA, not from a large concurrency number.

| Signal | Action to evaluate |
|---|---|
| High Queue backlog, fast handler, DB still has headroom | Increase concurrency with bounds, measure throughput. |
| Many consumers yet DB pool constantly exhausted | Reduce consumer count or increase downstream capacity/queueing, do not just add threads. |
| One consumer holds many prefetched messages | Tune provider prefetch/pooling; monitor fairness. |
| Topic handler receives duplicate copies on same node | Check if using multiple **unshared subscriptions** instead of a shared subscription. |
| Durable Topic receives nothing after restart | Check client ID/subscription name/topic/selector and old backlog. |
| Subscription reports conflict after selector change | Check active consumers and contract change; plan a new version. |
| Business ordering breaks when scaling replicas | Check message groups/partitioning and idempotency/sequences. |
| One broker hosts multiple sensitive tenants | Never use selectors as authorization; evaluate separate namespaces/ACLs. |

### Concurrency Has Real Cost

Each JMS consumer requires sessions/connections or cached resources depending on container and provider settings. A Queue listener with maxConcurrency 8 across 5 replicas can reach 40 consumers; three such endpoints require a sizable budget for broker and thread scheduling. Do not equate `maxConcurrency` with CPU core count; it caps active consumers, while CPU, I/O, and pool capacity govern effective speed.

With non-shared Topics, raising concurrency can **create unwanted duplicate copies**; with shared durable, raising concurrency appropriately can share load, though downstream limits and idempotency against redelivery side effects remain essential.

## 17. Common Errors

| Symptom | Common Cause | How to Fix/Verify |
|---|---|---|
| `@JmsListener(selector=...)` receives nothing even though JSON has the field | Property exists only in body, not attached to JMS message. | Call `setStringProperty`/`setIntProperty` before sending, inspect on broker. |
| Numeric selector does not match | Producer attached a `String` for a number. | Standardize property types in the contract. |
| `concurrency="4"` does not immediately create four consumers | Single number is an upper bound, default lower is 1. | Use `"4-4"` if fixed 4 is truly needed; verify active consumer count. |
| Topic delivered multiple times per replica | Each replica has an independent unshared subscription. | Use a shared subscription with the same identity when one delivery per group is needed. |
| Unshared durable Topic fails to scale active-active | One subscription allows only one active consumer/client ID conflict. | Use shared durable if supported by provider and scaling is required. |
| `subscription="billing"` set yet messages lost when offline | `setPubSubDomain(true)` and `setSubscriptionDurable(true)` not enabled. | Inspect Topic factory and proper subscription lifecycle. |
| Method rename loses old Topic backlog | Using default subscription name derived from fully qualified method. | Set explicit subscription name and plan migrations. |
| Changed Topic selector yet old events not received | Selectors filter messages entering the subscription on publish; not retroactive. | Perform controlled subscription cutover and replay if needed. |
| Raising concurrency causes out-of-order processing | Multiple consumers finish asynchronously. | Partition/group by business key, use sequences/idempotency. |
| Listener reports success yet DB records duplicates | Redelivery after partial commit without idempotency. | Unique event IDs, inbox/outbox, or proper transactions. |
| Consumers exist yet Queue backlog keeps growing | Selector mismatch or insufficient capacity/skewed prefetch. | Inspect raw JMS properties, active selectors, broker metrics. |
| Same client ID across replicas throws errors | Unshared durable identity or duplicate connection policy. | Distinguish shared/unshared; manage client identities per standard/provider. |

## 18. Recommended Test Suite in CI and Staging

1. **Endpoint initialization:** each `@JmsListener` resolves the right destination, factory, selector, concurrency, and subscription. Syntax errors in selectors must fail during consumer creation.
2. **Message selection:** send matching and non-matching events; verify unfiltered consumers do not accidentally steal messages.
3. **Property types:** send String, int, boolean with right and wrong types, missing/NULL properties; verify selector matches as expected.
4. **Queue concurrency:** send hundreds of independent jobs, scale replicas; measure throughput, in-flight, active consumers, prefetch, ordering.
5. **Concurrency & thread safety:** concurrent listener invocations do not race on mutable state or duplicate database side effects.
6. **Topic fan-out:** two independent business subscriptions both receive one copy of a matching event; multiple replicas in one shared subscription do not each get a copy.
7. **Durability:** create durable subscription **before** publishing, disconnect all consumers, then publish; upon reconnect, verify backlog/retention/expiry.
8. **Identity:** test active-active with shared durable; test unshared durable with two consumers and verify the broker enforces the constraint properly.
9. **Selector migration:** update selector/version per plan; verify old backlog, duplicates, replay, and cleanup.
10. **Failure:** throw exceptions, kill processes, drop networks, roll back; verify retry/redelivery, DLQ, idempotency, and eventual state.
11. **Security:** a producer from another tenant cannot bypass ACLs even when setting properties mimicking a valid tenant.
12. **Resource budget:** actual consumer counts per replica, broker limits, DB connection pools, and peak-hour latency.

These tests require a **real broker/client** to draw conclusions about durable/shared semantics, performance, and failure modes. Java unit tests of the handler method alone cannot validate subscription names or transaction recovery.

## 19. Self-Check Questions

**Question 1.** A Queue has a listener with `concurrency="2-4"` across 3 replicas. What is the ceiling for JMS consumers for this endpoint?

**Answer:** Approximately `3 × 4 = 12` consumers if all replicas scale to their cap; actual counts depend on resources/broker. It is not 4 consumers across the entire cluster.

**Question 2.** A Topic feeds Billing and Notification; each service has 3 replicas, needs **each event once per service**, and must not lose events while the whole group is offline. Which subscription should you choose?

**Answer:** Two separate **shared durable subscriptions**, e.g., `billing-ledger-v1` and `notification-mail-v1`. Each subscription has multiple consumers sharing load within its group; the broker retains messages for the subscription while offline per durability/expiry policies.

**Question 3.** Does putting `@JmsListener(subscription="billing")` and `concurrency="3-3"` on a Queue factory create a shared durable Topic?

**Answer:** No. You need `setPubSubDomain(true)`, `setSubscriptionDurable(true)`, and `setSubscriptionShared(true)` on the appropriate factory, an existing Topic, and broker support for that subscription type.

**Question 4.** Why might `concurrency="4"` start with only one active consumer?

**Answer:** A single number expresses an upper bound with a default lower bound of 1; the container scales up as load increases. Use `"4-4"` if fixed 4 is required, and check actual active consumers.

**Question 5.** Does a shared non-durable Topic consumer retain messages published while no consumer is online?

**Answer:** No. Shared defines load sharing, not offline backlog retention. A durable subscription is required to retain newly published messages while the group is offline.

**Question 6.** Does changing the selector of a durable subscription that already has a backlog automatically re-filter old messages?

**Answer:** No. Selectors decide which messages enter the subscription at publish time; changing the contract can be rejected or recreate the subscription. Controlled migration and replay are required.

**Question 7.** A listener with concurrency=8 receives two events with the same `orderId`; the later event finishes before the earlier one. Is that a Spring bug?

**Answer:** Not necessarily. Concurrent processing does not guarantee completion order; design needs key-based grouping/partitioning, sequence numbers, and state machines/idempotency.

**Question 8.** Does `@JmsListener(id="billingPaidEvents")` mean the JMS subscription also carries that name?

**Answer:** No. `id` identifies the Spring listener container, whereas `subscription` specifies the Topic subscription identity. The two names have different lifecycles and purposes.

## 20. Deployment Checklist and Official References

- [ ] Clearly verified whether destination is Queue or Topic, without relying on name strings.
- [ ] Selectors reference valid JMS properties/headers; producers send matching types and consistent schemas.
- [ ] Factory has right `pubSubDomain`, transaction/ACK, concurrency, QoS/recovery; annotations pick the right factory.
- [ ] Understood `"4"` vs. `"4-4"` and per-endpoint/per-replica concurrency.
- [ ] Listener handlers are thread-safe and idempotent per business requirements.
- [ ] For Topics, properly selected shared/unshared and durable/non-durable; subscription name is stable.
- [ ] Unshared durable has an appropriate client ID and never multiple active consumers.
- [ ] For shared durable, client identity and broker support have been tested; replicas truly join the same subscription.
- [ ] Plans exist for changing selectors/subscriptions, retaining/draining backlog, and handling duplicates during migration.
- [ ] Tested concurrency, Queue/Topic semantics, broker restarts, recovery, redelivery/DLQ, and ACLs.
- [ ] Metrics exist for active consumers, Queue depth, subscription backlog, and alerts for unmatched selectors.

**Official References:**

- [Spring Framework — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Framework 6.2 — @JmsListener Javadoc: selector, concurrency, subscription, id](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html).
- [Spring Framework 6.2 — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html).
- [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc: concurrency and Topic caution](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html).
- [Spring Framework — Receiving messages and transactions](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html).
- [Jakarta Messaging 3.1 specification — Topic subscriptions, shared/durable, selector semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
- [Spring Boot 3.5 — JMS Artemis integration](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html).
- [Spring Boot 3.5 — Artemis embedded properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/).
