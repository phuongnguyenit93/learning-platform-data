# Destination, Queue, and Topic in the JMS API

> **Module:** Spring Framework – JMS  
> **Knowledge Group:** Core JMS API  
> **Lesson:** Destination, Queue, and Topic in the API

## Learning Objectives

After this lesson, you will be able to:

1. Explain why `Destination` is the common address type in Jakarta Messaging, while `Queue` and `Topic` determine how messages are distributed.
2. Recognize the `jakarta.jms.Destination`, `Queue`, `Topic`, `TemporaryQueue`, and `TemporaryTopic` interfaces; use them properly in `JMSContext` or `Session`.
3. Distinguish creating a **Destination object** via the API from **creating a physical resource on the broker**; know when to use JNDI, broker administration, or provider dynamic provisioning.
4. Predict how multiple consumers receive messages from a queue versus multiple subscriptions on a topic, including offline consumers, selectors, acknowledgment, and redelivery.
5. Choose the right queue/topic for business requirements, send/receive using the native API, and configure Spring JMS so producers and listeners use the matching destination type.
6. Understand `JMSReplyTo`, temporary destinations, lifecycle, and common configuration mistakes such as sending to a queue while a listener subscribes to a topic of the same name.

## 1. What Is a Destination?

In Jakarta Messaging (formerly well known as JMS), an application sends messages **to a destination** and creates consumers **on a destination**. `Destination` represents the logical address understood by the message broker / JMS provider, freeing application code from knowing connection details to individual consumers.

```text
                         Jakarta Messaging API
                                 |
                +----------------+----------------+
                |                                 |
           Producer                          Consumer
                |                                 ^
                v                                 |
          Destination ----------------------------+
            /       \
           /         \
        Queue        Topic
          |             |
     worker group   subscriptions
```

For example, Order Service can send `OrderCreated` to a destination named `orders.events`. It does not need to know the hosts of Analytics Service or Audit Service; the provider receives the message and delivers it according to destination type, subscriptions, and configuration.

**Key point:** `Destination` is only an **addressing interface**. It does not itself specify "broadcast" or "deliver once"; the queue/topic and subscription state determine distribution. Nor is it a Java variable storing all messages in the producer's memory.

In Jakarta Messaging 3.1, the type hierarchy is:

```java
public interface Destination { /* common address */ }

public interface Queue extends Destination {
    String getQueueName() throws JMSException;
}

public interface Topic extends Destination {
    String getTopicName() throws JMSException;
}

public interface TemporaryQueue extends Queue {
    void delete() throws JMSException;
}

public interface TemporaryTopic extends Topic {
    void delete() throws JMSException;
}
```

The snippet above is a **structural outline** of the standard interfaces to explain inheritance relationships, not a source file to create in your project. In real applications, import `jakarta.jms.*` from the Jakarta Messaging dependency.

### What Destination Does Not Specify

- There is no universal address syntax across all brokers. The string `"orders.events"` is a **name agreed upon by the application and provider**, not a single standard JMS URL.
- The `Destination` interface has no common `getName()` method; only the `Queue` subtype has `getQueueName()`, and `Topic` has `getTopicName()`.
- Java code creating a `Queue`/`Topic` object does not guarantee that the broker has created the corresponding physical entity, granted permissions, or configured persistence or bindings.
- Reusing the same **string name** does not make a queue and a topic the same destination. A broker may allow both destination types with the same name but different semantics, depending on the provider.

`Destination` is an **administered object** in traditional JMS deployments: an administrator configures destinations and applications retrieve references via JNDI. For convenience, the modern API also allows creating address objects by provider-specific name directly in code.

## 2. Queue in the API — Point-to-Point

`jakarta.jms.Queue` represents a **point-to-point** destination. Each message in a queue is delivered to **one eligible consumer** per delivery attempt. Multiple consumers on the same queue typically act as competing workers sharing work.

```text
       Producer 1 -----\
                        \
       Producer 2 -------> [ Queue: invoice.generate ]
                                     |             |
                                  Worker A     Worker B
                                     \             /
                           messages distributed for work
```

If there are three units of work `J1`, `J2`, `J3` and two workers, each message is given to one worker according to the provider's dispatching mechanism. JMS **does not require** the broker to distribute strictly round-robin or equally. Which worker receives which message depends on speed, selectors, priority, connection state, and the broker.

### When Two Consumers Share a Queue

```text
[orders.work]
  M1 --> Consumer A (or B)
  M2 --> Consumer B (or A)
  M3 --> Consumer A (or B)
```

**Do not confuse "one consumer" with "exactly-once business execution".** If a consumer processes a message and fails before acknowledgment/commit, the provider can redeliver the message (possibly to a different worker). Applications need idempotency whenever side effects like charging money, sending email, or updating a database must not happen twice.

If consumers shut down, messages can remain in the queue until consumers return, though retention duration and full-queue behavior depend on `PERSISTENT`/`NON_PERSISTENT`, TTL, transactions, and provider policies. Do not assume messages are stored forever simply because the destination is a queue.

### Message Selectors on a Queue

A consumer can specify a selector, for example:

```java
JMSConsumer vipConsumer = context.createConsumer(
        queue, "priorityGroup = 'VIP'");
```

Here `priorityGroup` is an application-set property, not a standard header. This consumer is only eligible to receive messages matching the expression. Non-matching messages may be received by other consumers or remain in the queue. This does not mean the queue creates a separate copy per selector.

A queue fits when a task needs **a worker group to execute it once successfully**: sending email, transcoding video, generating invoices, calling a shipping system, running background jobs.

## 3. Topic in the API — Publish/Subscribe

`jakarta.jms.Topic` represents a **publish/subscribe** destination. A producer publishes a message to the topic; **each eligible independent subscription** can receive a copy of that message.

```text
                 Producer
                    |
                    v
          [ Topic: orders.events ]
                /         \
               /           \
    Subscription A      Subscription B
       Analytics             Audit
          |                   |
      Consumer A          Consumer B
```

If Analytics and Audit are **two independent subscriptions**, a single `OrderCreated` event can be processed by both. Audit acknowledging receipt does **not** acknowledge on behalf of Analytics, because each has its own pending messages and processing boundary.

**Distinguish subscriber from consumer instance.** When a group uses a *shared subscription*, multiple consumer instances can split messages of **the same subscription**; in that case, each message for that subscription only needs to be handled by one instance rather than all instances in the group. Two independent subscriptions, by contrast, are used to fan out to two separate business responsibilities.

### Non-Durable and Durable Subscriptions

- **Non-durable:** normally exists only while an active consumer is attached; if the subscription disappears and new events are published, a restarted consumer does not automatically receive missed history from JMS.
- **Durable:** a subscription with a persistent identity retained by the provider while the consumer is temporarily offline. Upon reconnecting with the same identity, the consumer can receive waiting messages subject to delivery mode, TTL, selectors, and broker retention policies.

`PERSISTENT` on the producer **does not replace a durable subscription**. If a consumer's non-durable subscription has vanished, publishing `PERSISTENT` messages does not create a subscription for an offline consumer. Conversely, a durable subscription does not prevent message loss when using `NON_PERSISTENT` or an overly short TTL.

### A Topic Does Not Automatically Become a "Replayable History Stream"

A new subscription normally receives messages published **from the time that subscription exists**. JMS does not promise to replay all past topic history from before the subscription was created. If an application must reread events from months ago by offset, design a history store or use a technology with an event-log contract; do not implicitly attribute that capability to a Topic.

A topic fits when one event needs multiple interested groups to react: an order creation consumed independently by Audit, Analytics, and Notification; a price update sent to multiple monitoring systems.

## 4. API-Accurate Comparison Table: Queue vs. Topic

| Characteristic | `Queue` | `Topic` |
| --- | --- | --- |
| Model | Point-to-point | Publish/subscribe |
| Java type | `jakarta.jms.Queue` | `jakarta.jms.Topic` |
| How many recipients per message? | One eligible consumer **per delivery attempt**; redelivery can still occur | One copy for **each eligible independent subscription** |
| Multiple instances | Normally compete and share load on the queue | Different subscriptions: each group receives; same shared subscription: share load |
| When all consumers are offline | Queue can retain pending work per policy and mode | Non-durable can miss events; durable can retain backlog for an existing subscription |
| Creating address object | `context.createQueue(name)` | `context.createTopic(name)` |
| Accessing name | `queue.getQueueName()` | `topic.getTopicName()` |
| Suitable use case | Job needing one worker to process | Event multiple systems need to know about |
| What is not promised | Business exactly-once, system-wide FIFO, infinite retention | All consumers always online, replayable history, all subscriptions durable |

**Choosing by business contract:**

- "Generate one PDF invoice, scale workers as load grows" → usually a **queue**.
- "Notify that an invoice was created so accounting, reporting, and auditing all react" → usually a **topic with multiple subscriptions**.
- "Each deployment region must receive one copy, with 3 workers sharing load within each region" → **one separate shared subscription per region**, not all workers in a single global subscription.
- "Need an immediate result within the HTTP request" → synchronous processing may be preferable; JMS queues/topics do not inherently change response-time requirements.

## 5. Native API: How to Create and Use Destinations

Modern Java has two common JMS styles:

1. **Simplified API:** `ConnectionFactory.createContext(...)` returns `JMSContext`; uses `JMSProducer` and `JMSConsumer`, typically with less boilerplate.
2. **Classic API:** `ConnectionFactory.createConnection()`, `Connection.createSession(...)`, `Session.createProducer(...)` / `createConsumer(...)`; still widely used and present in integration libraries.

Spring JMS wraps these operations with `JmsTemplate` and listener containers, yet understanding the native API helps read logs, configurations, and errors accurately.

### 5.1. Creating Queue/Topic Objects with JMSContext

Assuming a valid `jakarta.jms.ConnectionFactory` from the provider:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.Topic;

public class DestinationHandles {
    private final ConnectionFactory connectionFactory;

    public DestinationHandles(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void inspectDestinationNames() throws Exception {
        try (JMSContext context =
                     connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = context.createQueue("orders.work");
            Topic topic = context.createTopic("orders.events");

            System.out.println("Queue name: " + queue.getQueueName());
            System.out.println("Topic name: " + topic.getTopicName());
        }
    }
}
```

**This class is meant for a project with a JMS provider, not a standalone program compiled with `javac`.** It only creates handle objects by name and prints the names returned by the provider; log output depends on the provider. The existence of the `queue` object does not prove a real broker-side queue exists or that permissions are sufficient.

The Jakarta Messaging specification explicitly states that `JMSContext.createQueue(String)` and `createTopic(String)` only create objects representing **provider-specific names**. The API **does not standardize creating persistent physical destinations**. Some brokers auto-create destinations on first use, but that is a provider-specific feature/policy.

### 5.2. Producers and Consumers Accept Destination Parameters

Simple queue example:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Queue;

public class QueueApiExample {
    private final ConnectionFactory connectionFactory;

    public QueueApiExample(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public String sendThenReceive() {
        try (JMSContext context =
                     connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = context.createQueue("orders.work");
            JMSConsumer consumer = context.createConsumer(queue);

            context.createProducer().send(queue, "ORD-42");
            return consumer.receiveBody(String.class, 3_000L);
        }
    }
}
```

When the broker is running, the destination exists/is auto-created, no competing worker grabs the message, the send succeeds, and the consumer receives in time, the method can return `"ORD-42"`.

However, **do not treat this as a guaranteed output**: if the 3-second timeout expires or a connection error occurs, `receiveBody(...)` can return `null` or throw an exception. In real systems, producer and consumer are usually **two separate processes**, and consumer processing requires proper transactions, retries, logging, and idempotency.

Parts to understand:

- `context.createQueue(name)` → creates the `Queue` object.
- `context.createConsumer(queue)` → registers a consumer with the provider on the queue.
- `context.createProducer().send(queue, "ORD-42")` → sends a message to the destination.
- `receiveBody(String.class, timeout)` → receives the body converted to the requested type, or `null` on timeout; can fail if the body cannot be converted to that type.
- `try (JMSContext ...)` → releases context resources when finished.

**Sequencing note:** when creating a `JMSConsumer`, `JMSContext` automatically starts the connection for receiving unless `autoStart` has been disabled. That is why the sample can receive without calling `context.start()` manually.

### 5.3. Sending/Receiving on a Topic with JMSContext

```java
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Topic;

Topic topic = context.createTopic("orders.events");
JMSConsumer audit = context.createConsumer(topic);
JMSConsumer analytics = context.createConsumer(topic);

// Two non-durable subscriptions created before publishing.
context.createProducer().send(topic, "OrderCreated: ORD-42");

String auditEvent = audit.receiveBody(String.class, 3_000L);
String analyticsEvent = analytics.receiveBody(String.class, 3_000L);
```

This is an **illustrative code snippet inside a scope that already has `JMSContext context`** and a running provider, not a standalone Java file. These two consumers register **two independent non-durable subscriptions** on the same topic. If both remain active and the broker operates normally, each consumer can receive a copy; if a consumer is created **after** publishing, do not expect it to receive the event retroactively.

`createConsumer(topic)` creates a non-durable subscription by default. For durable subscriptions, use the corresponding API such as `createDurableConsumer(topic, subscriptionName)` with properly configured client identity; shared durable subscriptions require `createSharedDurableConsumer(...)` and provider support. Subscription names and client IDs must remain stable to reconnect to an existing backlog.

### 5.4. Classic API and Using the Common Destination Interface

```java
// Assume session is a jakarta.jms.Session created from a Connection.
Destination target = session.createQueue("orders.work");
MessageProducer producer = session.createProducer(target);
MessageConsumer consumer = session.createConsumer(target);

producer.send(session.createTextMessage("ORD-42"));
```

The general API accepts `Destination`, so high-level logic can accept a `Destination` variable without knowing all provider-specific queue/topic classes. **However, the application must still understand subtype semantics**. Using a `Destination` variable does not convert a queue into a topic or produce broadcast delivery on send.

In the classic API, you can create an unbound `MessageProducer` (`session.createProducer(null)`) and pass the `Destination` on each `send(destination, message)` call. This is useful when reply destinations vary per request. In the simplified API, `JMSProducer.send(destination, ...)` always takes the destination at send time.

### 5.5. Inspecting Destination Type at Runtime

```java
import jakarta.jms.Destination;
import jakarta.jms.Queue;
import jakarta.jms.Topic;

public static String destinationKind(Destination destination) {
    if (destination instanceof Queue) {
        return "QUEUE";
    }
    if (destination instanceof Topic) {
        return "TOPIC";
    }
    return "UNKNOWN";
}
```

This function takes a provider-created `Destination` object and checks its subtype. Because `TemporaryQueue extends Queue` and `TemporaryTopic extends Topic`, they are classified accordingly. This is **not a check of whether the physical destination still exists on the broker**; it only inspects the Java object type.

You can read the `message.getJMSDestination()` header to see the destination to which the producer sent the message as recorded by the provider. `JMSReplyTo` is a separate field indicating where to send a reply, **not** the inbound destination itself.

## 6. Administered Destinations, JNDI, and Dynamic Destinations

This is where many applications "work locally, fail in production".

### 6.1. A Destination Object Is Not a Physical Resource

```text
Java client                               JMS provider/broker
----------                                -------------------
context.createQueue("billing.work")  -->  Queue object(name="billing.work")
                                          (does not yet guarantee the real queue exists)

producer.send(queue, msg)             -->  provider looks up/checks destination
                                          -> uses it if it already exists
                                          -> may auto-create if permitted
                                          -> or reports InvalidDestination / permission error
```

**Physical resources** typically carry attributes that the standard `Destination` interface cannot express: max consumers, address routing, persistence, quotas, storage, security policies, dead-letter policies, auto-delete, retention, and cluster topology.

JMS has no portable API to create and administer all of these resource attributes. Each broker has its own CLI, management API, configuration files, or console. Consequently, critical production resources are usually **explicitly defined and managed per provider**.

### 6.2. JNDI: Looking Up Preconfigured Objects

In traditional JMS, `ConnectionFactory` and `Destination` can be administered objects stored in JNDI:

```java
// Illustration: JNDI must be pre-configured for the environment.
javax.naming.Context naming = new javax.naming.InitialContext();
jakarta.jms.Queue queue =
        (jakarta.jms.Queue) naming.lookup("jms/queue/OrdersWork");
```

Here `javax.naming` belongs to the **JDK's Java Naming and Directory Interface**, which is completely normal even when JMS uses `jakarta.jms`. Do not confuse `javax.naming` with the old `javax.jms` package.

The name `"jms/queue/OrdersWork"` is a **JNDI binding name defined by the deployment environment**, not necessarily the physical name used by the broker. Spring can inject administered destinations via JNDI. This model is convenient when physical configuration, permissions, and addresses are administered independently of source code.

### 6.3. Dynamic Destination Resolution

Spring `JmsTemplate` accepts both `Destination` objects and `String` destination names. When given a `String`, Spring uses a `DestinationResolver` to convert it into an object in the proper queue/topic domain.

- `DynamicDestinationResolver` is the typical default strategy and calls the API to create a `Queue`/`Topic` object from the name.
- `JndiDestinationResolver` looks up the object in JNDI; depending on configuration, it can fall back to dynamic resolution.
- The provider may auto-create the physical destination when referenced or used, **but that is not a universal JMS guarantee**.

```text
"orders.work" (String)
        |
        v
DestinationResolver.resolveDestinationName(
    session, "orders.work", pubSubDomain=false)
        |
        v
Queue handle -> broker provider
```

If `pubSubDomain=true`, the resolver looks up/creates a `Topic` handle. Thus the very same string `"orders.events"` can resolve to a Queue or a Topic depending on Spring configuration. Always inspect the destination type, not just the string.

## 7. Spring JMS: Using Queue and Topic Correctly

Spring Framework 6+ builds on `jakarta.jms`. `JmsTemplate` removes most send/receive boilerplate, while `@JmsListener` + container factories manage listeners. **Both producer and consumer must point to the same designed destination type**.

### 7.1. A Spring Application Using Both Queue and Topic

Assume a Spring project with `spring-jms`, a configured `jakarta.jms.ConnectionFactory` pointing to a real JMS provider, and two valid destinations: queue `orders.work` and topic `orders.events`. The example spans **multiple files in the same Spring project** using Java 17+; individual files cannot be compiled in isolation with just the JDK.

**File `JmsDestinationConfig.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsDestinationConfig {

    @Bean("queueTemplate")
    public JmsTemplate queueTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false); // String name is resolved to a Queue
        return template;
    }

    @Bean("topicTemplate")
    public JmsTemplate topicTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);  // String name is resolved to a Topic
        return template;
    }

    @Bean("queueListenerFactory")
    public DefaultJmsListenerContainerFactory queueListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("topicListenerFactory")
    public DefaultJmsListenerContainerFactory topicListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

In Spring, `setPubSubDomain(false)` selects queues; `true` selects topics. The default for `JmsTemplate` when resolving String names is typically queues, so **do not forget to enable topic mode when pub/sub is needed**.

**File `OrderPublisher.java`:**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private final JmsTemplate queueTemplate;
    private final JmsTemplate topicTemplate;

    public OrderPublisher(
            @Qualifier("queueTemplate") JmsTemplate queueTemplate,
            @Qualifier("topicTemplate") JmsTemplate topicTemplate) {
        this.queueTemplate = queueTemplate;
        this.topicTemplate = topicTemplate;
    }

    public void requestFulfillment(String orderId) {
        queueTemplate.convertAndSend("orders.work", orderId);
    }

    public void publishCreatedEvent(String orderId) {
        topicTemplate.convertAndSend("orders.events", orderId);
    }
}
```

A `String` is used as an example payload so `SimpleMessageConverter` normally converts it into a `TextMessage`. When using real DTOs/JSON/protobuf, design the message converter and schema; choosing Queue vs. Topic is **independent** of body type.

**File `FulfillmentWorker.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class FulfillmentWorker {

    @JmsListener(
            destination = "orders.work",
            containerFactory = "queueListenerFactory")
    public void handleWork(String orderId) {
        System.out.println("Fulfillment: " + orderId);
    }
}
```

If multiple instances of `FulfillmentWorker` are deployed on the same queue, they compete for jobs; each message normally reaches one worker per delivery attempt. Processing failures can trigger redelivery according to transaction and provider settings.

**File `OrderAuditSubscriber.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditSubscriber {

    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicListenerFactory")
    public void recordEvent(String orderId) {
        System.out.println("Audit: " + orderId);
    }
}
```

**File `OrderMetricsSubscriber.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderMetricsSubscriber {

    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicListenerFactory")
    public void updateMetrics(String orderId) {
        System.out.println("Metrics: " + orderId);
    }
}
```

When both topic listeners have initialized and are online **before** `publishCreatedEvent("ORD-42")` is called, both Audit and Metrics can receive the corresponding event. The order of those two log lines is not guaranteed. For the queue, calling `requestFulfillment("ORD-42")` can log:

```text
Fulfillment: ORD-42
```

For the topic, illustrative log output (order may be reversed):

```text
Audit: ORD-42
Metrics: ORD-42
```

This is **conditional output**, not guaranteed stdout on every run. The broker must be active, listeners properly registered, messages unexpired, delivery/transactions error-free, and neither subscriber offline at publish time. Both topic listeners in this example are **non-durable** under the current configuration; to receive events missed while offline, configure durable/shared subscriptions with proper identities.

### 7.2. Sending with an Existing Destination Object

Besides String names:

```java
// queue is a jakarta.jms.Queue supplied by the provider/JNDI.
queueTemplate.convertAndSend(queue, "ORD-42");
```

When passed a **Destination object**, Spring uses that object directly. `pubSubDomain` is mainly needed when Spring must **resolve a String** to a queue or topic, not to convert an existing `Queue` object into a `Topic`. If you mistakenly pass a `Topic` object to logic expecting a queue, renaming or toggling flags will not change the underlying destination's nature.

### 7.3. Durable Configuration for a Topic Listener

The earlier example lacks a durable subscription. If an audit subscription must accumulate events while the application is shut down, you can create a dedicated factory:

```java
@Bean("durableAuditFactory")
public DefaultJmsListenerContainerFactory durableAuditFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("audit-service");
    factory.setSessionTransacted(true);
    factory.setConcurrency("1"); // Unshared durable: only one active consumer
    return factory;
}
```

```java
@JmsListener(
        destination = "orders.events",
        subscription = "audit-orders-v1",
        containerFactory = "durableAuditFactory")
public void recordDurableEvent(String orderId) {
    // Handle event and check idempotency by eventId.
}
```

These two snippets are **illustrative configuration fragments inside a Spring project**, requiring imports as in the previous example, not standalone runnable files. A durable unshared subscription relies on a stable client/subscription identity; do not run multiple instances concurrently with the same client ID as if it were a load-sharing queue. For multi-instance setups, evaluate shared durable subscriptions, identities, selectors, and specific provider support.

Producers still need appropriate delivery mode, TTL, and transactions; a durable subscription does not guarantee "exactly once" or infinite message retention.

### 7.4. Diagnosing Queue/Topic Mismatch Errors

Common symptom: producer logs "send OK" yet `@JmsListener` never receives anything.

Check:

1. Which `JmsTemplate` is the producer using? Does `pubSubDomain` match the intent?
2. Which `containerFactory` is the listener using? Does `setPubSubDomain(...)` match the same destination type?
3. Is the resolver using `DynamicDestinationResolver`, JNDI, or a custom strategy?
4. Does the broker have the real queue/topic, matching routing type, and permissions?
5. Are the **provider-specific** name, namespace/vhost/address, and environment correct?
6. For a topic, did the subscription exist **before** publishing; if durable, are `clientId` and `subscription` configured properly?
7. Does the message have a selector, TTL, priority, delivery mode, or transaction state preventing delivery?
8. Is the consumer actively receiving, in retry/backoff, or routed to a DLQ per broker policy?

Using the same name `"orders.events"` on both sides is not enough to prove they refer to the same destination type.

## 8. TemporaryQueue and TemporaryTopic

Jakarta Messaging provides destination subtypes whose lifecycle is tied to a **connection**:

- `TemporaryQueue extends Queue`.
- `TemporaryTopic extends Topic`.

They are assigned unique identities by the system/provider when calling `Session.createTemporaryQueue()`/`createTemporaryTopic()` or the equivalent `JMSContext` APIs. Unlike `createQueue(String)`, these temporary methods actually instruct the provider to create a temporary destination.

**Only the connection that created a temporary destination may create consumers on it.** Producers on other connections can reply to the temporary destination if given a valid reference; this is very useful for the request/reply pattern.

```text
Service A                                    Service B
    |                                            ^
    | create TemporaryQueue (replyTo)             |
    |                                            |
    +---- request (JMSReplyTo=temporaryQueue) ---->|
    |                                            |
    |<----------- reply to temporaryQueue --------+
    |
  consume reply on owning connection
```

Request-side example on an existing context:

```java
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;

TemporaryQueue replyQueue = context.createTemporaryQueue();
Queue requests = context.createQueue("reports.request");

TextMessage request = context.createTextMessage("report-42");
request.setJMSReplyTo(replyQueue);
request.setJMSCorrelationID("request-42");

context.createProducer().send(requests, request);

// Consumer uses the same connection/context that created replyQueue.
String reply = context.createConsumer(replyQueue)
        .receiveBody(String.class, 5_000L);
```

**This is an illustrative API fragment**, not standalone runnable code: it requires a provider, a consumer handling `reports.request`, and agreed correlation and reply timing. If there is no responder or the reply arrives late, `reply` may be `null`. The responder must send its reply to the destination in the request's `getJMSReplyTo()` and set `JMSCorrelationID` per the contract between both systems.

Temporary destinations are deleted when the connection closes (or earlier via `delete()` when valid); **do not use them as fixed addresses** for jobs spanning multiple application sessions. Nor do they replace a persistent queue for long-running business workflows.

## 9. Message Headers and Destination Have Different Roles

Three addresses must be distinguished:

- **Actual send target:** the `Destination` object passed to `send(...)` or the name resolved by `JmsTemplate`.
- **`JMSDestination`:** provider-assigned header showing the destination to which the message was sent; consumers can read it for debugging/routing.
- **`JMSReplyTo`:** address set by the producer when requesting a reply, usually a response queue/topic or a temporary destination.

```text
Request message:
  sent to Destination = queue reports.request
  JMSDestination      = queue reports.request
  JMSReplyTo          = temporary queue client-123/reply-456

Response message:
  sent to Destination = temporary queue client-123/reply-456
  JMSCorrelationID    = request-42 (per application contract)
```

`JMSReplyTo` does not turn a message into automatic RPC: the application receiving the request must explicitly read the header, perform the work, construct a reply, and send it to the indicated destination. Producers usually need timeouts and handling for responder failures; correlation IDs match replies to requests.

Do not use `message.setJMSDestination(...)` to route a send: the send target is determined by the producer/`send(...)` call. The `JMSDestination` header may be written or overwritten by the provider per the JMS contract.

## 10. Operational Factors You Must Not Overlook When Choosing a Destination

### 10.1. Message Body Does Not Dictate Queue vs. Topic

The same `TextMessage`, `BytesMessage`, or `MapMessage` can be sent to a queue or a topic. **Payload type** answers "what data does the message carry?"; **destination type** answers "who receives the data?". Never assume JSON must go to a topic or binary must go to a queue.

### 10.2. Delivery Mode, TTL, and Acknowledgment Are Separate Axes

- `DeliveryMode.PERSISTENT`/`NON_PERSISTENT` determines the delivery protection level of **each message**.
- `timeToLive`/`JMSExpiration` determines how long a message remains eligible for delivery.
- `acknowledgment`/transactions determine when the broker considers the message handled on the JMS side.
- `Queue`/`Topic` determines routing and subscription semantics.

A queue with `PERSISTENT` messages still does not promise infinite storage if messages expire or the broker runs out of resources. A topic using `PERSISTENT` still does not preserve events for an offline non-durable subscriber.

### 10.3. Ordering and Fairness

JMS defines ordering rules within producer/session/consumer scopes, but does not allow assuming that multiple producers, multiple workers, selectors, and redelivery will yield a uniform global order everywhere. If business logic requires ordering per `aggregateId`, design partition keys, concurrency, and ordering rules according to the broker/provider.

JMS also does not force brokers to distribute messages to workers round-robin. Use throughput and queue backlog metrics to observe distribution; avoid making "worker A handles every first message, worker B every second message" an application contract.

### 10.4. Security and Lifecycle

Destinations can have separate **send**, **consume**, **browse**, create/delete, or administrative permissions; a valid destination name can still be rejected if the principal lacks permission. Broker connections should use proper TLS/authentication. Temporary queues or auto-created destinations also carry the risk of unbounded resource creation if left unconstrained.

Use stable destination names, separate environments (dev/test/prod), manage permissions, and apply controllable naming conventions, for example:

```text
orders.work.v1       queue: handled by one fulfillment group
orders.events.v1     topic: multiple systems receive events
reports.reply.<id>   temporary reply destination generated by the provider
```

These are **convention examples**, not standard JMS syntax. In environments with specific address rules, follow your provider's naming and routing rules.

### 10.5. Consistency Rule When Publishing Events After DB Writes

If Order Service commits an order and crashes before publishing `OrderCreated`, downstream services may never know the order exists. If it publishes before committing the DB and the DB transaction rolls back, consumers see an event for a non-existent transaction.

Consider **transactional outbox** or an explicitly designed transaction coordination mechanism to guarantee consistency between the DB and publishing. Simply choosing `Topic` does not solve "dual write", and choosing `Queue` does not guarantee side effects happen exactly once.

## 11. Standalone Java 17 Example Simulating Distribution Behavior

To visually verify the difference between "one message for one worker" and "one copy per subscriber", the following example uses plain Java collections. **This is an in-memory simulation, completely not a JMS provider**: it has no persistence, acknowledgment, selectors, transactions, subscription lifecycle, or broker.

Create `DestinationRoutingDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Queue;

public class DestinationRoutingDemo {
    public static void main(String[] args) {
        // One shared queue for two workers.
        Queue<String> work = new ArrayDeque<>();
        work.add("job-42");

        System.out.println("Queue Worker A: " + work.poll());
        System.out.println("Queue Worker B: " + work.poll());

        // Two independent subscriptions each holding a copy of the same event.
        Queue<String> auditSubscription = new ArrayDeque<>();
        Queue<String> metricsSubscription = new ArrayDeque<>();

        String event = "OrderCreated: ORD-42";
        auditSubscription.add(event);
        metricsSubscription.add(event);

        System.out.println("Topic Audit: " + auditSubscription.poll());
        System.out.println("Topic Metrics: " + metricsSubscription.poll());
    }
}
```

Run with JDK 17 or later:

```bash
javac DestinationRoutingDemo.java
java DestinationRoutingDemo
```

Exact output:

```text
Queue Worker A: job-42
Queue Worker B: null
Topic Audit: OrderCreated: ORD-42
Topic Metrics: OrderCreated: ORD-42
```

`Queue Worker B: null` appears because there is only **one** unit of work, already taken by worker A in the sequential simulation. In real JMS, you cannot assume worker A always wins the message or worker B is always second. The two queues `auditSubscription` and `metricsSubscription` in the demo simulate **two separate subscriptions**, each receiving a copy of the event. Fan-out is written manually here to illustrate semantics; in a real JMS system, the provider performs routing based on subscriptions and configured policies.

## 12. Checklist for Choosing and Checking Destinations in Real Applications

When designing a new producer/consumer, verify each item in turn:

1. **Is the message a command or an event?** A task handled by one group, or an event multiple groups need to receive?
2. **Destination type?** Queue or Topic, and the intended load-sharing and fan-out model?
3. **Name and provisioning?** Which provider-specific name, admin-created or broker auto-created, and environment namespacing?
4. **Resolver?** Do producer and consumer use JNDI objects, explicit Destinations, or strings + resolver?
5. **Spring config?** Do `JmsTemplate.pubSubDomain` and the listener factory match?
6. **Subscriptions?** For topics, how many subscriptions, durable vs. non-durable, shared vs. unshared, and stable identity?
7. **Errors and reliability?** TTL, delivery mode, acknowledgment/transactions, retries, DLQ, and idempotency?
8. **Metadata?** Correlation ID, message type, schema version, business key, monitoring, and audit?
9. **Security?** Who may send/receive/browse, and is the broker connection secured?
10. **Observability?** Pending messages, consumer count, per-subscription backlog, expirations, redeliveries, DLQ, and processing latency?

Do not treat "send threw no exception" as sufficient testing. It tells you the send met API/provider conditions; it does **not** prove consumers finished processing or every subscriber received the message.

## 13. Hands-On Scenarios to Distinguish Queue and Topic

**Scenario A — Queue with two workers**

1. Create/provision queue `orders.work` on your broker.
2. Start two queue listeners on the same destination.
3. Publish ten messages with distinct business IDs.
4. Observe that the group processes ten messages total successfully and each business ID applies its effect only once thanks to idempotent logic; distribution between workers **need not be 5–5**.
5. Intentionally throw an error after side effects but before JMS commit and observe provider redelivery. Verify the outcome is not duplicated.

**Scenario B — Topic with two subscriptions**

1. Create/provision topic `orders.events`.
2. Start two non-durable listeners (Analytics and Audit) **before publishing**.
3. Publish an `OrderCreated` event.
4. Verify each listener can receive its own copy. Stop Analytics, publish another event, then restart it: do not expect the non-durable listener to receive retroactively.
5. If offline event retention is required, configure a durable subscription beforehand, pick a suitable delivery mode, and verify backlog delivery upon reconnection.

**Scenario C — Same name, wrong type**

1. Configure the producer `JmsTemplate` with `pubSubDomain=false` and the listener with `pubSubDomain=true` using the same string name.
2. Observe behavior/errors on the broker: messages may enter a queue or find no matching consumer of the right type, even though the text name is identical.
3. Align both to Queue or both to Topic **matching business intent**; check broker-side resources and subscription settings.
4. Takeaway: both destination name and destination type are part of the deployment contract.

**Scenario D — Request/reply**

1. Client creates a `TemporaryQueue` and sends a request to the processing queue with header `JMSReplyTo`.
2. Service sends the result to that destination, setting `JMSCorrelationID` per contract.
3. Client receives within timeout; close the connection before the response arrives and observe potential reply loss.
4. Takeaway: temporary destinations are tied to connection lifecycle; do not use them for long-running processes returning results hours later.

## 14. Common Mistakes

**“`Destination` and `Queue`/`Topic` are three different places to store messages.”** False. `Destination` is the parent interface; Queue/Topic are subtypes defining the routing model.

**“`Destination` has `getName()`.”** False. The subtypes have `getQueueName()` and `getTopicName()`. Name syntax is provider-defined.

**“`createQueue("name")` always creates a physical queue on the broker by standard.”** False. It creates a handle object; physical resources and auto-creation belong to provider/administration.

**“A Queue guarantees an exactly-once business effect.”** False. A message is delivered to one consumer per delivery attempt, but retries/redelivery can cause repeat processing.

**“A Topic delivers every message to every thread across all instances.”** False. Fan-out is per **independent subscription**; consumers within a shared subscription split messages.

**“`PERSISTENT` lets a non-durable subscriber receive events missed while offline.”** False. Message delivery guarantees do not recreate an absent subscription.

**“A JMS topic automatically stores all events for new subscribers to replay.”** False. A durable subscription must exist before publishing to accumulate a backlog; historical replay is a separate requirement.

**“Spring only needs the same String name to connect.”** False. Producer and consumer must match destination type and resolve to the proper resource; `pubSubDomain` matters when using String names.

**“Setting `setPubSubDomain(true)` converts an injected `Queue` object into a `Topic`.”** False. The flag governs the resolver; it does not change the subtype of an explicit object.

**“`JMSReplyTo` is the request's original destination.”** False. It is the reply address; `JMSDestination` is the header reflecting the send target.

**“A temporary queue is a durable queue that automatically cleans up when empty.”** False. Its lifecycle is bound to the connection, unsuitable as a persistent address across sessions.

**“Every Queue/Topic has identical semantics across all JMS providers.”** False for aspects outside the spec: provisioning, storage quotas, auto-create, security, DLQ, clustering, provider-specific routing behaviors, and retention must still be checked per broker.

## 15. Knowledge Self-Check

**Question 1.** There is a `GenerateInvoice` message and three workers waiting. Each message needs one worker to process it successfully. What do you choose?

**Answer:** Queue. Multiple consumers on a queue share work; duplicate handling is still needed if redelivery occurs.

**Question 2.** `OrderCreated` must be processed independently by Audit and Analytics. Are two consumers reading the same queue sufficient?

**Answer:** No. They compete on a queue; each message normally goes to only one side. Choose a topic with **two independent subscriptions** or an equivalent fan-out design.

**Question 3.** Does `Destination d = context.createQueue("billing.work");` guarantee the broker created a physical queue?

**Answer:** No. The API creates a handle object by name; physical provisioning may be handled by an administrator or broker auto-create depending on the provider.

**Question 4.** In Spring, producer `convertAndSend("a", msg)` uses `pubSubDomain=false` and listener `@JmsListener(destination="a")` uses a topic factory. Since the names match, is the listener guaranteed to receive?

**Answer:** No. The producer resolves a queue, while the listener resolves a topic. Destination type and actual broker resources must match.

**Question 5.** If two instances share a **shared durable subscription** on a topic, does each instance receive every message?

**Answer:** No. They share load within one subscription; if two groups must both receive all matching events, create **two independent subscriptions**.

**Question 6.** A non-durable topic consumer shuts down at 10:00, the producer publishes at 10:05, and the consumer restarts at 10:10. Does the JMS specification entitle it to redelivery of that event?

**Answer:** No. The non-durable subscription no longer existed; even a producer using `PERSISTENT` does not create a backlog for it.

**Question 7.** What does `JMSReplyTo` specify?

**Answer:** The destination where the responder should send its reply, typically a response queue/topic or `TemporaryQueue`. It differs from the request's `JMSDestination`.

**Question 8.** Who may create a consumer on a temporary queue?

**Answer:** Only the connection that created the temporary queue; producers on other connections can still send to it given a valid reference.

**Question 9.** Sending a message to a queue succeeds, yet a business side effect happens twice. Does this contradict the queue model?

**Answer:** No. Uncompleted ack/transactions can cause redelivery; business idempotency must be built in.

**Question 10.** Can a Java method receiving `Destination` immediately call `destination.getQueueName()`?

**Answer:** No. `Destination` does not declare this method; you must check/cast to the `Queue` subtype or use separate resolver/metadata logic.

## Key Takeaways

- `Destination` is JMS's **common address**; `Queue` and `Topic` are subtypes representing two distinct distribution models.
- **Queue:** one message is delivered to one eligible consumer per delivery attempt, suited for distributing work among workers.
- **Topic:** each independent subscription can receive matching copies, suited for fanning out events to multiple responsibilities.
- `createQueue(String)`/`createTopic(String)` creates objects **by provider name**, without guaranteeing physical resource provisioning. Broker creation and policies still must be managed.
- Spring uses `DestinationResolver` and `pubSubDomain` when resolving **String names** to destinations; align producer and listener on name, type, and broker resource.
- Delivery mode, TTL, durable subscriptions, ack, transactions, retries, and idempotency are **independent** choices to design explicitly, not automatic properties of choosing Queue or Topic.

### Official References

1. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — `Destination`, Queue/Topic semantics, `JMSContext`, `Session`, temporary destinations, and delivery rules.
2. [Jakarta Messaging 3.1 — Destination API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/destination) — common address interface and subtype hierarchy.
3. [Jakarta Messaging 3.1 — JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext) — `createQueue`/`createTopic`, `createConsumer`, temporary destinations, and `createDurableConsumer`.
4. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — JNDI, dynamic destination resolution, `DestinationResolver`, and `pubSubDomain`.
5. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate` and sending by destination name or object.
6. [Spring Framework — Annotated JMS Listeners](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@JmsListener` and listener factories.
7. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — listener lifecycle, transactions, and acknowledgment.