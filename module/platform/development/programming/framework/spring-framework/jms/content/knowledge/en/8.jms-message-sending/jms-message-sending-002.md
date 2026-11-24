# Sending to a Destination or a Resolved Name

> **Module:** Spring Framework – JMS  
> **Group:** Message Sending  
> **Topic:** Choosing a send target using an existing `jakarta.jms.Destination` or a `String` name resolved by Spring into a Destination.

## Learning Objectives

After this lesson, you will be able to:

1. Understand `Destination` as a logical address in Jakarta Messaging; `Queue` and `Topic` are two types with different delivery semantics.
2. Distinguish **sending with a `Destination` object** from **sending with a `String` name via `DestinationResolver`** in `JmsTemplate`: which steps occur and which do not.
3. Correctly use `send(...)`, `convertAndSend(...)` overloads, and targetless overloads when a default destination is configured.
4. Explain how `DynamicDestinationResolver`, `JndiDestinationResolver`, `pubSubDomain`, and broker/JNDI configuration interact.
5. Configure both queue and topic send paths in a Spring JMS application, using both names and objects, and match them with the right listener types.
6. Recognize errors such as "same name but wrong Queue/Topic type", missing JNDI bindings, unexpected auto-creation, unvalidated user-supplied names, and transaction handling mistakes.
7. Test with rigor: verify the resolved Destination type, physical resources, send permissions, message path, and business outcomes.

## 1. Big Picture: "Where to Send" Involves Two Decisions

JMS enables an application to send messages to a **Destination** rather than directly to a consumer's IP address. `Destination` is a standard interface; the provider/broker implements the routing.

```text
Application                            JMS provider / broker

Message payload
      |
      |      [Path A] Destination object -------------------+
      |                                                     |
      +----> JmsTemplate.send(...)                          |
      |                                                     v
      |      [Path B] "orders.work" (String)          [Queue orders.work]
      |                  |                                  |
      |                  v                                  v
      |             DestinationResolver                 Worker group
      |                  |
      |                  +--> Queue object ----------------> queue
      |
      +----> "orders.events" (String)
                        |
                        v
                DestinationResolver
                 pubSubDomain = true
                        |
                        +--> Topic object ----------------> topic
                                                            |
                                                   Subscriber A, B, ...
```

Two independent decisions must remain consistent:

- **Which target?** An existing `Destination` or a name that a resolver turns into a `Destination`?
- **What type of target?** A `Queue` typically delivers one message to one worker per delivery; a `Topic` delivers a matching copy to each independent subscription.

**Do not equate a name string with an address object.** `"orders.events"` might be a physical name understood by the provider, a JNDI binding name, or a logical name mapped by the application. A String itself carries no queue/topic type information. When sending by name, the resolver and `pubSubDomain` determine how the object is looked up or created.

### 1.1. Interfaces to Remember

```java
import jakarta.jms.Destination;
import jakarta.jms.Queue;
import jakarta.jms.Topic;
```

Type hierarchy in Jakarta Messaging:

```text
         Destination  (interface)
            /    \
           /      \
         Queue    Topic
            |      |
     TemporaryQueue  TemporaryTopic
```

The bottom two entries indicate that `TemporaryQueue extends Queue` and `TemporaryTopic extends Topic`, **not that every queue/topic is temporary**.

A method accepting `Destination` can be called with a `Queue` or a `Topic` thanks to subtyping. However, `Destination` has no common `getName()` method. You must check the subtype or query provider metadata if you want to display the name.

```java
public static String describe(Destination d)
        throws jakarta.jms.JMSException {
    if (d instanceof Queue queue) {
        return "Queue: " + queue.getQueueName();
    }
    if (d instanceof Topic topic) {
        return "Topic: " + topic.getTopicName();
    }
    return "Destination type unknown";
}
```

This is an illustrative snippet in a project with the Jakarta Messaging API, not a standalone executable Java file; names and provider rendering depend on the environment.

### 1.2. Queue and Topic Do Not Change Based on Body Type

- `TextMessage`, `BytesMessage`, and other message types **can all** be sent to either a queue or a topic.
- `Queue` fits distributing work across workers. When a message fails, acknowledgement/transaction behavior may trigger redelivery.
- `Topic` fits fanning out events to multiple subscriptions. Offline non-durable subscribers generally do not receive messages retroactively while no subscription exists.
- Enabling `DeliveryMode.PERSISTENT` does not turn a queue into a topic and does not automatically create a durable subscription.

**The Destination determines the delivery path; the Message/MessageConverter determines the body and metadata.** Never infer destination type from the chosen message type.

## 2. Two Send Paths in JmsTemplate: Object and Name

Spring JMS provides `org.springframework.jms.core.JmsTemplate`. Every send path ultimately requires a `jakarta.jms.Destination`; the difference is whether the application already holds that object **before the call** or Spring must **resolve the name**.

### Path A — Passing a Destination Object Directly

```java
// queue is a jakarta.jms.Queue/Destination injected from JNDI
// or supplied by the provider.
jmsTemplate.send(queue, session ->
        session.createTextMessage("generate-invoice:42"));
```

- This overload has the form `send(Destination, MessageCreator)`.
- `JmsTemplate` receives the **already-resolved** `queue` object and uses it for the send operation.
- **It does not need to call `DestinationResolver.resolveDestinationName(...)` to convert a string**, because there is no destination string to resolve.
- `pubSubDomain` does not "force" an existing `Queue` object into becoming a `Topic`. The actual type of `queue` remains a queue.
- The object must belong to a provider compatible with the `ConnectionFactory` used by `JmsTemplate`; do not obtain a handle from provider X and assume it can be sent through provider Y.

Advantages: target type is explicit in code and configuration, leverages objects supplied by JNDI/operations, and reduces type mistakes from arbitrary names. Trade-off: you must inject/look up and manage the configuration lifecycle of the object.

### Path B — Passing a String for Spring to Resolve

```java
jmsTemplate.send("orders.work", session ->
        session.createTextMessage("generate-invoice:42"));
```

- The overload is `send(String destinationName, MessageCreator)`.
- Spring invokes the configured `DestinationResolver` to look up or create a suitable `Destination` object from the name.
- The resolver usually needs to know **whether a queue or topic is intended**; the template's `pubSubDomain` property participates in this decision.
- Resolving a name **does not guarantee the broker already has the physical destination**: it may look up an object from JNDI or create a provider-specific name handle; the broker provisions physical destinations according to its own rules.

Advantages: the application does not need a separate Java bean per address; convenient for destinations governed by naming conventions. Risks: misconfigured resolver, `pubSubDomain`, logical/physical names, and broker permissions.

### Easy Rule to Remember

> `send(Destination, ...)`: **already have an address** → send.  
> `send(String, ...)`: **have a name** → resolver creates/finds address → send.

This is a difference in **how the address is obtained**, not two different send protocols or differences in message reliability.

## 3. Key JmsTemplate Send Overloads

| Call | Target meaning | Message body |
| --- | --- | --- |
| `send(Destination, MessageCreator)` | Existing destination object | Callback builds `jakarta.jms.Message` |
| `send(String, MessageCreator)` | Name resolved by `DestinationResolver` | Callback builds JMS message |
| `send(MessageCreator)` | Configured default destination | Callback builds JMS message |
| `convertAndSend(Destination, Object)` | Existing destination object | Converter transforms Java object to JMS message |
| `convertAndSend(String, Object)` | Name resolved by resolver | Converter transforms Java object to JMS message |
| `convertAndSend(Object)` | Configured default destination | Converter transforms Java object to JMS message |
| `convertAndSend(..., MessagePostProcessor)` | Target per chosen overload | Converter runs first, post-processor adds headers/properties afterward |

**Note on `String`:** In `send("orders.work", creator)`, the String is the **destination name**. In the single-argument `convertAndSend("hello")`, the String is the **payload** sent to the **default destination**. Meanwhile, `convertAndSend("orders.work", "hello")` specifies both destination name and payload. Distinguish them by **method signature and parameter count**, not by the String type alone.

### 3.1. How Do send and convertAndSend Differ?

`send(...)` takes a `MessageCreator`; the callback receives a `jakarta.jms.Session` to create the message and set headers/properties:

```java
jmsTemplate.send("orders.work", session -> {
    var m = session.createTextMessage("invoice-42");
    m.setStringProperty("eventType", "GENERATE_INVOICE");
    m.setJMSCorrelationID("request-42");
    return m;
});
```

`convertAndSend(...)` uses the `MessageConverter` attached to the template:

```java
jmsTemplate.convertAndSend("orders.work", "invoice-42");
jmsTemplate.convertAndSend("binary.tasks", new byte[] {1, 2, 3});
```

The default `SimpleMessageConverter` supports basic conversions such as `String → TextMessage`, `byte[] → BytesMessage`, and `Map → MapMessage` (when values are compatible types). For custom DTOs or JSON versioning, you must choose an explicit converter/schema; **do not assume an arbitrary Java record will serialize to JSON automatically**.

If you still want to set properties after conversion:

```java
jmsTemplate.convertAndSend(
        "orders.work",
        "invoice-42",
        message -> {
            message.setStringProperty("eventType", "GENERATE_INVOICE");
            message.setJMSCorrelationID("request-42");
            return message;
        });
```

In this snippet, `MessagePostProcessor` runs **after the converter, before sending**. All three examples are snippets inside an application that already has `JmsTemplate`, a broker, and the `spring-jms` dependency; they do not run standalone with `javac`.

### 3.2. Sending to the Default Destination

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setPubSubDomain(false);
template.setDefaultDestinationName("orders.work");

// Single argument is the payload; target comes from default configuration.
template.convertAndSend("invoice-42");

// MessageCreator callback uses the default destination.
template.send(session ->
        session.createTextMessage("invoice-43"));
```

Here `connectionFactory` is provided by the environment/provider. `setDefaultDestinationName(...)` is one way to configure it; you can also call `setDefaultDestination(Destination)` when you already have an object. Calling a destinationless overload when **no default is configured** causes Spring to throw an error.

Configure a template **once and share it**; `JmsTemplate` is thread-safe **after configuration is complete**, so do not continuously mutate `pubSubDomain` or the default destination on a singleton serving concurrent requests.

## 4. DestinationResolver: The Link Between Name and Object

Spring's core interface:

```java
public interface DestinationResolver {
    Destination resolveDestinationName(
            Session session,
            String destinationName,
            boolean pubSubDomain
    ) throws JMSException;
}
```

This is a simplified signature for learning purposes; in real code, import the interfaces from `org.springframework.jms.support.destination` and `jakarta.jms`. The resolver returns a `Destination` object for `JmsTemplate` to use.

Typical flow:

```text
JmsTemplate.send("orders.work", creator)
      |
      +--> DestinationResolver.resolveDestinationName(
      |        session,
      |        "orders.work",
      |        pubSubDomain
      |    )
      |           |
      |           +--> Queue or Topic object
      |
      +--> MessageCreator.createMessage(session)
      |
      +--> provider MessageProducer.send(destination, message)
      |
      +--> release Session/Producer per template
```

The diagram depicts the **primary relationships** and does not promise every provider/callback path executes the internal steps in the exact same order. What the API guarantees is: when using a name, a resolver must turn the name into a destination; when passing an object, no name resolution step is needed.

### 4.1. DynamicDestinationResolver — The Default Path

When no other resolver is configured, `JmsTemplate` defaults to `DynamicDestinationResolver`. It calls `Session.createQueue(name)` or `Session.createTopic(name)` based on `pubSubDomain`.

```text
JmsTemplate
  setPubSubDomain(false)   -- "billing.jobs" --> Session.createQueue(...)
  setPubSubDomain(true)    -- "order.events" --> Session.createTopic(...)
```

**By default `pubSubDomain=false`**: String names are resolved in the **queue** domain, not topics. Therefore:

```java
JmsTemplate queueSender = new JmsTemplate(connectionFactory);
queueSender.convertAndSend("orders.events", "hello");
```

This snippet **does not create a topic merely because the name contains "events"**. With `DynamicDestinationResolver` and the default queue domain, Spring requests a `Queue` handle named `"orders.events"`. If the application expects a topic, you must configure `setPubSubDomain(true)` or pass an actual `Topic` object.

### 4.2. createQueue(String) Does Not Necessarily Provision a Broker Queue

Jakarta Messaging specifies that `Session.createQueue(String)` and `JMSContext.createQueue(String)` create a **Queue object** wrapping a provider-specific name; the same applies to Topic. They are **not standard APIs for creating physical queues/topics** on the broker.

Consequences:

- Broker A might auto-create destinations when used by a client; Broker B might require manual pre-creation.
- A broker may reject the operation due to an invalid name, lack of create/send permissions, missing address/binding, or wrong routing type.
- An API-level `send(...)` success does not prove a consumer processed it.
- A resolver working properly at the object level can still fail when the provider attempts to send the message.

For production, declare queues/topics and policies for retention, quotas, DLQ, ACLs, and clustering using the provider's tools; do not rely on "calling createQueue automatically provisions the queue" as a standard guarantee.

### 4.3. JndiDestinationResolver — Looking Up Registered Names

If operations manages JNDI-administered destinations:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setCache(true);
resolver.setFallbackToDynamicDestination(false);

JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDestinationResolver(resolver);
template.setPubSubDomain(false);

// "jms/queue/BillingJobs" is the JNDI binding name defined by the environment.
template.send("jms/queue/BillingJobs",
        session -> session.createTextMessage("invoice-42"));
```

This is an integration snippet inside an application with an **established JNDI context**, broker, and Spring JMS; it does not run standalone. `JndiDestinationResolver` looks up the object by binding; the binding may point to a queue/provider name different from the lookup string.

By default on this JNDI resolver, **fallback to dynamic resolution when lookup fails is disabled**. If you deliberately enable `setFallbackToDynamicDestination(true)`, Spring can fall back to the dynamic resolver when JNDI lacks the name. However, accidentally enabling fallback in production can **mask binding errors** and result in an unintended queue/topic being created/resolved by name. Decide deliberately based on deployment policy.

`setCache(true)` can reduce lookup overhead, though you must consider JNDI binding changes, hot restarts, and cache management. Behavior depends on the provider; do not use a single logical name for both a queue and a topic within the same cache/resolver and assume perfect disambiguation.

### 4.4. Custom DestinationResolver

Complex applications can implement `DestinationResolver` themselves when logical-to-physical address mapping is required:

```java
// PSEUDOCODE illustrating the contract, not a complete implementation:
resolve("billing.commands", false) -> physical Queue "v1.billing.jobs"
resolve("orders.events", true)     -> physical Topic "v1.order.created"
```

A custom resolver should:

- Define a **controlled mapping**, never constructing addresses from unvalidated input.
- Respect `pubSubDomain` and return the matching object type; detect mismatches immediately.
- Use the correct `ConnectionFactory`/provider or JNDI scope.
- Have policies for caching, refresh, error reporting, and testing nonexistent names.
- Avoid dangerous side effects on lookup failure (such as auto-creating unplanned queues).

When there are only a few fixed destinations, injecting `Queue`/`Topic` directly or using two dedicated templates is usually clearer. A custom resolver is only justified when dynamic mapping is a real business requirement.

## 5. Which Step Does pubSubDomain Control?

`setPubSubDomain(boolean)` on `JmsTemplate` primarily instructs the **name resolution step** whether to request a queue or a topic. The default `false` corresponds to queue, and `true` corresponds to topic.

| Scenario | `pubSubDomain` | How is the actual target chosen? |
| --- | --- | --- |
| `send("orders.work", ...)` with DynamicDestinationResolver | `false` | Resolver creates a `Queue` handle |
| `send("orders.events", ...)` with DynamicDestinationResolver | `true` | Resolver creates a `Topic` handle |
| `send(queueObject, ...)` | `true` or `false` | Uses **`queueObject`**, never coerced into a Topic |
| `send(topicObject, ...)` | `true` or `false` | Uses **`topicObject`**, never coerced into a Queue |
| `send("jms/billing", ...)` with JndiDestinationResolver | Matching configuration | Looks up binding; result must match expected type, never guess solely from name |
| `send(creator)` with default `Destination` object | Depends on template | Uses the default object |
| `send(creator)` with default String name | Matching configuration | Resolves default name then sends |

The exact same string `"orders.events"` can be treated as a Queue in template A and as a Topic in template B. Do not use `pubSubDomain` as a global flag mutated at runtime per request on a singleton `JmsTemplate`; instead, define **two fixed template beans** or pass explicit `Destination` objects.

In `@JmsListener`, the container factory also has `setPubSubDomain(...)` so the listener resolves names to the right domain. **A producer using a topic and a listener using a queue with the same name** is a common configuration mistake.

## 6. Spring JMS Example: Properly Sending to Both Queue and Topic in One App

Assumptions:

- Spring Framework 6+ / Jakarta Messaging `jakarta.jms`, Java 17+, `spring-jms` dependency.
- A `jakarta.jms.ConnectionFactory` connected to a real broker is available.
- Queue `billing.jobs` and Topic `orders.events` are provisioned/administered or the broker is properly configured for auto-creation.
- Component scanning and `@EnableJms` are active; in a Spring Boot application, listener setup may be auto-provisioned under the corresponding conditions.
- Durable subscriptions are not yet required; the topic listeners in this example only demonstrate fan-out while subscribers are active.

### 6.1. Two Stably Configured JmsTemplates

**File `JmsSenderConfig.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsSenderConfig {

    @Bean("queueTemplate")
    public JmsTemplate queueTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false); // String -> Queue
        return template;
    }

    @Bean("topicTemplate")
    public JmsTemplate topicTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(true);  // String -> Topic
        return template;
    }

    @Bean("queueListenerFactory")
    public DefaultJmsListenerContainerFactory queueListenerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("topicListenerFactory")
    public DefaultJmsListenerContainerFactory topicListenerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(true);
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

Use distinct bean names to avoid ambiguity when injecting the two `JmsTemplate` beans. `setSessionTransacted(true)` on listeners enables rollback/redelivery within a local JMS transaction when processing fails; it **does not automatically combine a database transaction** with the JMS transaction.

### 6.2. Producer Sending to Resolved Names

**File `MessagingPublisher.java`:**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class MessagingPublisher {

    private final JmsTemplate queueTemplate;
    private final JmsTemplate topicTemplate;

    public MessagingPublisher(
            @Qualifier("queueTemplate") JmsTemplate queueTemplate,
            @Qualifier("topicTemplate") JmsTemplate topicTemplate) {
        this.queueTemplate = queueTemplate;
        this.topicTemplate = topicTemplate;
    }

    public void requestInvoice(String invoiceId) {
        queueTemplate.convertAndSend("billing.jobs", invoiceId);
    }

    public void publishOrderCreated(String orderId) {
        topicTemplate.convertAndSend("orders.events", orderId);
    }

    public void requestInvoiceWithProperties(String invoiceId) {
        queueTemplate.send("billing.jobs", session -> {
            var message = session.createTextMessage(invoiceId);
            message.setStringProperty("eventType", "CREATE_INVOICE");
            message.setStringProperty("schemaVersion", "1");
            return message;
        });
    }
}
```

`queueTemplate` resolves `"billing.jobs"` to a queue object; `topicTemplate` resolves `"orders.events"` to a topic object. A `String` payload can be converted into a `TextMessage` by the default converter. When you explicitly need JMS properties/headers, use `send(..., MessageCreator)` or `convertAndSend(..., MessagePostProcessor)`.

### 6.3. Corresponding Listeners

**File `InvoiceJobListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceJobListener {
    @JmsListener(
            destination = "billing.jobs",
            containerFactory = "queueListenerFactory")
    public void onInvoiceJob(String invoiceId) {
        System.out.println("Invoice: " + invoiceId);
    }
}
```

**File `OrderAuditListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {
    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicListenerFactory")
    public void audit(String orderId) {
        System.out.println("Audit: " + orderId);
    }
}
```

**File `OrderMetricsListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderMetricsListener {
    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicListenerFactory")
    public void collect(String orderId) {
        System.out.println("Metrics: " + orderId);
    }
}
```

When the broker is running, listeners are already registered, and no errors occur, calling:

```java
publisher.requestInvoice("INV-42");
publisher.publishOrderCreated("ORD-42");
```

May produce logs such as:

```text
Invoice: INV-42
Audit: ORD-42
Metrics: ORD-42
```

**This is conditional output with no ordering guarantee.** Listeners may run on different threads/processes; redelivery can occur, and an offline non-durable topic consumer can miss events. Systems require business idempotency and appropriate retry policies.

**Why use two topic listeners?** To illustrate two independent subscriptions needing the same event. If you run multiple replicas of the same non-durable listener without designing shared/durable subscriptions, each replica may receive a copy of every event rather than forming a load-sharing worker group like a queue.

### 6.4. Sending with an Injected Destination Object

Suppose the environment has bound a `jakarta.jms.Queue billingQueue` via JNDI or a provider adapter. Another service can accept the object directly:

```java
import jakarta.jms.Queue;
import org.springframework.jms.core.JmsTemplate;

public final class ExplicitDestinationSender {
    private final JmsTemplate jmsTemplate;
    private final Queue billingQueue;

    public ExplicitDestinationSender(
            JmsTemplate jmsTemplate, Queue billingQueue) {
        this.jmsTemplate = jmsTemplate;
        this.billingQueue = billingQueue;
    }

    public void sendInvoiceId(String invoiceId) {
        jmsTemplate.send(billingQueue,
                session -> session.createTextMessage(invoiceId));
    }
}
```

This class belongs to a Spring/JMS project where `JmsTemplate` and `Queue` are injected; it is not a standalone file. No `resolveDestinationName("...")` call happens on this path. Ensuring the `billingQueue` bean is configured for the right provider/broker remains the application's responsibility.

**Do not create a Queue object from broker A and assume a JmsTemplate connected to broker B can automatically send to it.** Handle portability depends on the JMS provider and namespace; integration tests must run against the actual target infrastructure.

## 7. Plain Jakarta Messaging Example: Using Only Destination Objects

Contrast with Spring's String API: in the Jakarta Messaging simplified API, `JMSProducer.send(...)` takes a `Destination` and has no portable `send(String destinationName, body)` overload.

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.Topic;

public final class RawJmsPublisher {
    private final ConnectionFactory connectionFactory;

    public RawJmsPublisher(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void publish() {
        try (JMSContext context = connectionFactory.createContext()) {
            Queue queue = context.createQueue("billing.jobs");
            Topic topic = context.createTopic("orders.events");

            context.createProducer().send(queue, "INV-42");
            context.createProducer().send(topic, "ORD-42");
        }
    }
}
```

This is a syntactically complete class inside **an application with the Jakarta Messaging dependency and a valid provider**; it cannot be compiled with just the JDK without libraries. `createQueue/Topic(String)` creates an object handle for a provider-specific name, **without guaranteeing physical resource provisioning**. `JMSContext` is closed via try-with-resources.

The classic API allows binding a `MessageProducer` to a destination at creation time:

```java
// session is an active jakarta.jms.Session.
Destination queue = session.createQueue("billing.jobs");
MessageProducer producer = session.createProducer(queue);
producer.send(session.createTextMessage("INV-42"));
producer.close();
```

Or leaving the target unbound at creation to specify it on each send:

```java
MessageProducer producer = session.createProducer(null);
producer.send(queue, session.createTextMessage("INV-42"));
producer.send(replyTo, session.createTextMessage("READY"));
producer.close();
```

In the latter example, `replyTo` is a `Destination` obtained from a request's `JMSReplyTo`; both snippets assume an existing session and proper handling of checked `JMSException`. Per the JMS classic API, only an **unidentified** producer created with `null` accepts a destination on `send(destination, message)`; do not arbitrarily call that overload on a producer bound to another destination.

In the simplified API, `JMSProducer` accepts a `Destination` on **every send**. Both approaches ultimately send to a `Destination` object; Spring adds the String name resolution layer to reduce boilerplate.

## 8. Default Configuration vs. Explicit: Which Should You Choose?

### If destinations are fixed, strongly typed, and centrally administered

Use a `Destination` object injected from JNDI or provider configuration:

- Expresses queue/topic clearly via Java types.
- Easy to control bindings and deployment permissions.
- No guessing `pubSubDomain` on the object-based send path.
- Suitable where physical address changes are managed by operations.

### If there are many valid names within a single domain

Use `String + DynamicDestinationResolver` with a domain-dedicated template:

- Queue sender sends only to queues; topic sender sends only to topics.
- Fixed configured names rather than concatenating arbitrary input.
- With providers allowing auto-creation, enforce quotas/ACLs/cleanup to prevent destination explosion.
- Each name used belongs to the application's proper namespace and broker.

### If logical names are centrally managed via JNDI

Use `String + JndiDestinationResolver`:

- Decouples logical names from provider physical names.
- Prefer disabling dynamic fallback in production if JNDI is mandatory.
- Test startup/fail-fast behavior for missing bindings and wrong types.
- Account for cache invalidation and procedures for changing JNDI mappings.

### If the target varies by tenant or event

Never take a raw string from an HTTP request and call:

```java
// ANTI-PATTERN: destinationName supplied arbitrarily by the client.
jmsTemplate.convertAndSend(destinationNameFromRequest, payload);
```

An arbitrarily constructed string can route messages to the wrong tenant, create unauthorized resources, overload namespaces, or direct data to the wrong queue/topic. It is much safer to map values from an **allowlist**:

```java
public String destinationForRegion(String region) {
    return switch (region) {
        case "north" -> "billing.north.jobs";
        case "south" -> "billing.south.jobs";
        default -> throw new IllegalArgumentException(
                "Unsupported region");
    };
}
```

This is a plain Java 17 method you can place in a project, using a switch expression to route according to an allowed mapping. In production, enforce broker permissions per tenant/vhost, auditing, input JSON/schema validation, and separation across dev/staging/prod environments.

## 9. Concerns Distinct from MessageConverter, QoS, and Transactions

### 9.1. Destination Selection Does Not Determine Body Type

- `send(..., MessageCreator)` lets you build `TextMessage`, `BytesMessage`, `MapMessage`, etc., using `Session`.
- `convertAndSend(..., Object)` lets a Spring converter transform the payload as configured.
- Choosing between a `Destination` object or a `String` **does not alter** body conversion rules.
- For JSON/Avro/protobuf payloads, you need the corresponding schema and converter; do not assume the broker decodes them automatically.

### 9.2. QoS Does Not Come from DestinationResolver

`DeliveryMode.PERSISTENT`/`NON_PERSISTENT`, priority, and time-to-live are delivery attributes. `DestinationResolver` only looks up/creates the **address** per contract; it does not make messages persistent, create durable topic subscriptions, or provide exactly-once processing.

`JmsTemplate` can be configured as follows:

```java
import jakarta.jms.DeliveryMode;

jmsTemplate.setExplicitQosEnabled(true);
jmsTemplate.setDeliveryMode(DeliveryMode.PERSISTENT);
jmsTemplate.setTimeToLive(60_000L);
```

**Note:** for Spring to apply the template's QoS overrides, you must enable `setExplicitQosEnabled(true)`; otherwise, the producer/provider may use its own defaults. The 60-second TTL here is only an example, **not** a recommended setting for all messages. For long-running tasks, too short a TTL can cause messages to expire before a consumer processes them.

### 9.3. Transactions Are Not Solved by "Send Succeeded"

Calling `send(...)` or `convertAndSend(...)` successfully indicates that the send satisfied the API/provider conditions; it **does not prove the consumer committed the business action**. Specifically:

1. Producer writes an order to the database.
2. Database commit succeeds.
3. Application crashes before publishing `OrderCreated`.

Even with the right topic and resolver, the event may never appear. This is the **dual write** problem between DB and JMS. To solve it, consider a transactional outbox or an appropriate coordinated transaction mechanism.

On the consumer side, a message may be redelivered when an error occurs before ack/commit. For sensitive operations, use a business event ID, idempotency, or unique constraints to avoid duplicate side effects. Neither a Queue nor a Topic guarantees an exactly-once business effect on its own.

### 9.4. The `JMSDestination` Header and the Send Target

`JMSDestination` is the header indicating the destination used when the message was sent according to provider semantics. Do not call `message.setJMSDestination(...)` expecting the broker to route based on that header; the **send target** is determined by the `Destination` passed to `send(...)` or the configured default destination.

`JMSReplyTo` is a different header telling a responder where to send replies; a service can read this object and call `jmsTemplate.send(request.getJMSReplyTo(), ...)`. For temporary reply destinations, lifecycle and connection ownership rules also apply.

## 10. Debugging When Sending to the Right Name Yet the Listener Receives Nothing

### Case A: Queue/Topic Mismatch

Producer:

```java
JmsTemplate template = new JmsTemplate(cf); // pubSubDomain defaults to false
template.convertAndSend("orders.events", "ORD-42");
```

Listener:

```java
@JmsListener(
        destination = "orders.events",
        containerFactory = "topicListenerFactory")
public void onOrderCreated(String payload) { /* ... */ }
```

The producer requests a Queue handle, while the listener requests a Topic handle with the same name. Depending on the broker, the send may succeed into an unlistened queue, be rejected due to incompatible routing, or create a separate resource via auto-create policies. **Having the same name is not enough.**

Fix: set `setPubSubDomain(true)` on the producer if a topic is intended, or pass the exact `Topic` object. Verify physical destinations and subscriptions after deployment.

### Case B: Confusing JNDI Names with Broker Names

Suppose JNDI has a binding `jms/queue/Invoice` pointing to physical queue `billing.v2.jobs`. A template using `DynamicDestinationResolver` will try to create a Queue handle for **the literal string `"jms/queue/Invoice"`**; it **does not automatically know** about that JNDI binding. Only a template using `JndiDestinationResolver` resolves the JNDI binding.

Fix: align resolvers and naming conventions; log the logical name, object type, and physical destination using provider tools. Do not assume every String triggers a JNDI lookup.

### Case C: Auto-Create Lacks Permission or Is Disabled

`DynamicDestinationResolver` only creates an object handle; at send time, the provider may require the destination to already exist or allow auto-creation. If the broker forbids auto-creation or the principal lacks send/create permissions, sending can fail.

Fix: provision destinations outside the application, grant least-privilege ACLs, and inspect the broker's namespace/vhost and error codes. Do not enable system-wide auto-creation just to mask typos.

### Case D: Missing or Wrong Default Destination

`jmsTemplate.convertAndSend("HELLO")` without `defaultDestination` or `defaultDestinationName` fails; if the default name points to the wrong queue, messages go to the wrong place. Distinguish single-argument overloads from two-argument overloads during code reviews.

### Case E: Topic Subscription Created Too Late

The topic uses a non-durable subscription. The producer publishes at 10:00, while the listener starts up at 10:01; by default, the listener will not receive past events. You must create a durable subscription **before publishing**, with a stable identifier, delivery mode, and appropriate retention if offline delivery is required.

### Case F: Body Conversion Error

The destination is right, but the converter cannot handle a custom DTO, the payload violates the schema, or the consumer fails to decode it. This is a **body/schema** issue, not a resolver issue. Separate send/receive logs and verify message type/contentType/version.

### Case G: Send Succeeded, but Business Action Ran Twice

This may be JMS redelivery caused by a consumer error before ack/commit. Do not try to fix this by switching Queue to Topic or vice versa; design idempotency and transactions around business effects.

## 11. Error Handling with JmsTemplate and Testing Strategy

`JmsTemplate` translates checked `jakarta.jms.JMSException` into runtime exceptions under Spring JMS such as `org.springframework.jms.JmsException`. Callers do not need to declare checked `throws JMSException` just to invoke the template, but **must have an error classification policy**: unresolved name, invalid destination, send permission denied, broker down, conversion failure, or transaction rollback.

A useful boundary:

| Error | Which step can throw it? | Handling approach |
| --- | --- | --- |
| Missing JNDI binding | Resolver lookup | Fail fast; inspect naming and environment |
| Valid name but wrong Queue/Topic | Resolver/provider | Check `pubSubDomain` and object type |
| Physical destination not created | Broker send | Provision and check provider policy |
| Missing send permission | Broker/security | Grant proper ACL; do not retry infinitely on auth errors |
| Conversion exception | MessageConverter/creator | Fix contract/schema/codec |
| Temporary network/broker failure | Connection/send | Bounded retry with backoff and idempotency |
| Listener offline during topic publish | Subscription lifecycle | Durable subscription if missing events is unacceptable |
| Duplicate consumer processing | Ack/transaction/redelivery | Business ID and deduplication |
| Payload too large | Converter/broker quota | Limit size or pass a reference to object storage |

Do not just log `"JMS send failed"` and swallow every exception. Log the logical name, expected destination type, environment, event ID, correlation ID, and error class; avoid logging sensitive payloads.

### Step-by-Step Verification Procedure

1. **Inspect producer configuration:** which template bean, which resolver, `pubSubDomain`, default destination, and which converter?
2. **Identify target style:** String or `Destination` object? If String, does the resolver produce a Queue or a Topic?
3. **Inspect the broker:** physical destination, vhost/namespace, provisioning, bindings, routing type, ACLs, and capacity.
4. **Inspect the consumer:** listener factory, domain, subscription/durable/shared status, selector, connection, and session transaction.
5. **Send an event with a verifiable ID:** attach a unique business ID and correlation ID, and record safe timestamps.
6. **Observe at the broker:** queue depth/subscription backlog, consumer count, accepted/sent/enqueued counters, redeliveries, and DLQ.
7. **Verify end-to-end:** did the consumer receive it and complete the business side effect? A `"send done"` log alone is insufficient.
8. **Test negative cases:** wrong domain, missing binding, missing permissions, broker down, offline subscriber, and timeout/expiration.

## 12. Standalone Java 17 Demo: Simulating Destination Selection

The example below visually contrasts **explicit `Destination`** and **domain-resolved `String`** without needing JMS JARs or a broker. This is purely a Java model; in real JMS, `Destination` is a provider-supplied interface and names may be JNDI-mapped.

Create **`DestinationChoiceDemo.java`**:

```java
public final class DestinationChoiceDemo {
    enum Domain { QUEUE, TOPIC }

    record Address(String name, Domain domain) {}

    static Address resolve(String name, boolean pubSubDomain) {
        return new Address(
                name,
                pubSubDomain ? Domain.TOPIC : Domain.QUEUE);
    }

    static String describe(Address destination) {
        return destination.domain() + ":" + destination.name();
    }

    public static void main(String[] args) {
        Address explicit =
                new Address("billing.jobs", Domain.QUEUE);

        // A name alone lacks enough information to decide the domain.
        Address byNameQueue = resolve("orders.events", false);
        Address byNameTopic = resolve("orders.events", true);

        System.out.println("Explicit -> " + describe(explicit));
        System.out.println("Name, false -> " + describe(byNameQueue));
        System.out.println("Name, true -> " + describe(byNameTopic));
        System.out.println("Same name: " +
                byNameQueue.name().equals(byNameTopic.name()));
        System.out.println("Same domain: " +
                (byNameQueue.domain() == byNameTopic.domain()));
    }
}
```

Compile and run with JDK 17+:

```bash
javac DestinationChoiceDemo.java
java DestinationChoiceDemo
```

Exact output:

```text
Explicit -> QUEUE:billing.jobs
Name, false -> QUEUE:orders.events
Name, true -> TOPIC:orders.events
Same name: true
Same domain: false
```

Takeaways from the demo:

- An explicit object already embeds its queue/topic type (represented as an enum in the demo).
- A String name alone is insufficient; a domain flag or an explicit resolver policy determines Queue vs. Topic.
- Two destinations with the same name can have different domains, so string matching does not verify routing.
- The demo does **not** send real messages, nor does it include JNDI, broker auto-creation, transactions, headers, or JMS semantics. All final routing verification requires integration tests against the target provider.

## 13. Hands-On Exercises with a Real Broker

### Exercise 1 — Two Overloads, Same Queue

1. Provision queue `billing.jobs` and create a corresponding queue listener.
2. Obtain the provider's `Queue` object or a JNDI binding.
3. Send message A using `jmsTemplate.send(queueObject, creator)`.
4. Send message B using `jmsTemplate.send("billing.jobs", creator)` with `DynamicDestinationResolver` and `pubSubDomain=false`.
5. Compare message IDs, bodies, and where the listener receives them. Verify **both go to the same destination** when resolver/binding/provider match.
6. Intentionally configure a wrong name to prove the string path is not statically validated by the object path.

### Exercise 2 — One Name, Both Queue and Topic Domains

1. Create two templates, one with `pubSubDomain=false` and one with `true`.
2. Try the same name `"demo.route"` in a test environment that permits creating both types.
3. Use the admin console to verify whether the provider creates/resolves two separate destination types, or returns an error if the broker forbids duplicate names/routing.
4. Configure a queue consumer and a topic subscriber and observe behavior.
5. Note that this is a **provider-specific detail**; do not treat one broker's behavior as a universal rule across all brokers.

### Exercise 3 — JNDI Mapping

1. Configure a binding `jms/queue/Invoice` pointing to a physical broker queue.
2. Use `JndiDestinationResolver` to send by binding and verify reception at the right destination.
3. Switch to `DynamicDestinationResolver` and try the same String in a test environment: it may map to a different physical name or be rejected.
4. Keep `fallbackToDynamicDestination=false` and delete the binding: the operation must throw a lookup error instead of silently falling back to a dynamic destination.
5. If caching is enabled, test refresh behavior after binding changes; never alter JNDI mappings hot without evaluation.

### Exercise 4 — Default Destination

1. Call `setDefaultDestinationName("billing.jobs")` on a queue template.
2. Send `convertAndSend("INV-10")` and `send(creator)`, confirming both use the default destination.
3. Remove the default configuration in another test run: confirm targetless overloads throw an error.
4. Pass an explicit different `Queue` to `send(Destination, creator)`: confirm the explicit destination overrides the default for that send.

### Exercise 5 — Reliability and Failure

1. Send a message with a business ID; verify the listener records successful processing.
2. Stop the consumer and send to the queue; observe backlog and TTL.
3. Restart the consumer and intentionally throw an exception before commit; verify redelivery and business idempotency.
4. With a topic, stop a non-durable subscriber and publish; verify no retroactive delivery is expected.
5. Drop the broker connection before/during a send: verify exception handling, retry policy, and deduplication when the send result is uncertain.

## 14. Code Review and Operations Checklist

Before approving a JMS send call in Spring, check:

- [ ] **Right business contract?** Queue for a worker group processing jobs, or Topic for multiple independent subscriptions?
- [ ] **Right overload?** `send(Destination,...)`, `send(String,...)`, or `send(creator)` using default?
- [ ] **If String, which resolver?** Dynamic, JNDI, or custom? Does it fail fast on invalid names?
- [ ] **Right `pubSubDomain`?** Do producer and listener resolve the String in the same domain?
- [ ] **Right environment?** Broker endpoint, vhost/namespace, queue/topic resources, and ACLs?
- [ ] **Right names/bindings?** Are application names, JNDI names, and physical provider names distinguished and documented?
- [ ] **No dangerous auto-creation?** Are allowlists, quotas, and restricted permissions enforced when names come from input data?
- [ ] **Intentional default destination?** Never call a targetless overload when no default is configured.
- [ ] **Valid body schema?** Do `MessageCreator` or `MessageConverter` match the consumer?
- [ ] **Clear QoS?** Are delivery mode, TTL, priority, and `explicitQosEnabled` configured as required?
- [ ] **Clear transaction/ack?** Send success does not guarantee consumer processing succeeded.
- [ ] **Idempotency present?** Redelivery/retry or dual writes can duplicate or drop business actions.
- [ ] **Observable?** Log business IDs and expected destination/domain, broker counters, DLQ, and alerting.
- [ ] **Stable configuration?** Never mutate a singleton template per request under multi-threading.
- [ ] **Real tests?** Both explicit `Destination` and `String` paths are tested against a real broker/provider.

## 15. Self-Check Knowledge Quiz

**Question 1.** In `jmsTemplate.send(queue, creator)`, `queue` is a `jakarta.jms.Queue` object. Does Spring still have to call `DestinationResolver` to convert a name into a Queue object?

**Answer:** No. The object path already provides a `Destination` and sends directly to that object; the resolver is needed for the String name path.

**Question 2.** A new `JmsTemplate` does not set `pubSubDomain`. Sending `"orders.events"` as a String via `DynamicDestinationResolver`—is this a Queue or a Topic?

**Answer:** A Queue, because `pubSubDomain=false` by default. The `"events"` suffix does not automatically make it a topic.

**Question 3.** Does `context.createQueue("billing.jobs")` guarantee that the broker has created the physical queue and granted send permission?

**Answer:** No. The API creates an object handle for a provider-specific name; provisioning and permissions belong to the provider/administration.

**Question 4.** Does `jmsTemplate.convertAndSend("invoice-42")` mean sending to a destination named `invoice-42`?

**Answer:** No. A single argument is the **payload**; the target is the configured default destination. With two arguments, `convertAndSend("billing.jobs", "invoice-42")`, the first argument is the destination name.

**Question 5.** Does `send(String, creator)` always use a JNDI lookup?

**Answer:** No. The default resolver is `DynamicDestinationResolver`. JNDI is used only when an appropriate resolver such as `JndiDestinationResolver` is configured.

**Question 6.** `JndiDestinationResolver` looks up a name missing from JNDI. By default, does it fall back to dynamic resolution?

**Answer:** No. `fallbackToDynamicDestination` defaults to false; you must enable it explicitly if you really want fallback.

**Question 7.** Does calling `setPubSubDomain(true)` on `JmsTemplate` turn a `Queue` object passed directly to `send(queue, creator)` into a `Topic`?

**Answer:** No. The domain flag primarily governs resolving **names**; a `Queue` object retains its type.

**Question 8.** Why might a message be sent successfully yet a topic listener still fails to receive it?

**Answer:** Possible causes include domain mismatch, JNDI/physical resource mix-up, non-durable subscription not existing at publish time, message expiration, non-matching selector, or listener/transaction/broker errors. You must inspect sender, resolver, broker, and subscriber.

**Question 9.** In an application that must send to both Queues and Topics by String name, should you use one singleton `JmsTemplate` and toggle `pubSubDomain` per request?

**Answer:** No. That risks race conditions and misrouting in concurrent applications. Use two stably configured templates or explicit `Destination` objects.

**Question 10.** Is converting a String payload into a `TextMessage` decided by `DestinationResolver` or `MessageConverter`?

**Answer:** `MessageConverter`, such as the default `SimpleMessageConverter`. The resolver only determines the destination.

**Question 11.** If you call `setDeliveryMode(PERSISTENT)` without calling `setExplicitQosEnabled(true)`, is `JmsTemplate`'s override guaranteed to be used on send?

**Answer:** Not guaranteed. You must enable explicit QoS if you need the template to apply its settings; verify provider behavior in integration tests.

**Question 12.** An event should be published, but the service writes to the DB and crashes before sending to JMS. Is this a `DestinationResolver` bug?

**Answer:** No. This is the dual-write problem; it requires transaction/outbox or consistent coordination, independent of how names are resolved.

## Conclusion

- `Destination` is the **JMS send address**; Queue/Topic determines delivery semantics.
- In Spring, **`send(Destination, ...)`** uses an existing object; **`send(String, ...)`** adds a `DestinationResolver` step to look up/create an object from a name.
- `DynamicDestinationResolver` is the default; `pubSubDomain=false` selects Queue and `true` selects Topic **during name resolution**.
- `JndiDestinationResolver` looks up operations-provided bindings; dynamic fallback is off by default.
- `createQueue(String)` and `createTopic(String)` create handles, **not a promise to provision physical resources**.
- `send(...)` builds messages via `MessageCreator`; `convertAndSend(...)` converts payloads via `MessageConverter`; QoS, transactions, and business idempotency are separate concerns.
- Choose the right overload and configure producer, listener, broker, ACLs, and schema clearly to avoid "sending to the right name but the wrong place".

### Official References

1. [Spring Framework – Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `JmsTemplate.send`/`convertAndSend`, default destination, callbacks, converters, and post-processors.
2. [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `DestinationResolver`, `DynamicDestinationResolver`, `JndiDestinationResolver`, `pubSubDomain`, connections, and QoS.
3. [Spring JMS – JmsOperations API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsOperations.html): overloads accepting `Destination`, `String`, and default destination.
4. [Spring JMS – DestinationResolver](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html): contract `resolveDestinationName(Session, String, boolean)`.
5. [Spring JMS – JndiDestinationResolver](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html): JNDI lookup, caching, and fallback.
6. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `Destination`, `JMSProducer`, `MessageProducer`, queue/topic, delivery mode, and producer send contract.
7. [Jakarta Messaging 3.1 – JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext): `createQueue(String)`, `createTopic(String)`, and managing provider-specific destination handles.
