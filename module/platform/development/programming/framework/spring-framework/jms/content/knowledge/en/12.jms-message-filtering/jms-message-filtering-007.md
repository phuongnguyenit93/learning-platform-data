# Combining Selectors with receive or @JmsListener

**Topic:** Spring Framework - jms → Message Filtering

## 1. Goal: receive only matching messages, instead of receiving and discarding

In a JMS system (Java Message Service, now part of Jakarta Messaging), a queue can contain many message types: high-priority orders, regular orders, payment events, notifications from multiple tenants. A consumer does not always want to process all of them.

For example, a queue `orders.events` contains:

| Message body | Property `eventType` | Property `priorityLevel` | Intended consumer |
| --- | --- | --- | --- |
| `order-101` | `ORDER_CREATED` | 2 (int) | Standard flow |
| `order-102` | `ORDER_CREATED` | 8 (int) | Priority flow |
| `refund-1` | `REFUND_REQUESTED` | 9 (int) | Refund flow |
| `order-103` | `ORDER_CREATED` | 6 (int) | Priority flow |

A consumer that only picks up orders marked high-priority can use:

~~~sql
eventType = 'ORDER_CREATED' AND priorityLevel >= 5
~~~

This is a **JMS message selector**, a conditional expression passed by the consumer to the JMS provider. The provider delivers only messages whose headers/properties match the selector to the corresponding consumer. With a queue, non-matching messages can remain in the queue or be received by another eligible consumer; they are **not** pulled and discarded by the consumer that just called receive.

In Spring JMS there are two common approaches:

- **Synchronous receive:** `JmsTemplate.receiveSelected(...)` or `receiveSelectedAndConvert(...)`.
- **Asynchronous receive:** `@JmsListener(destination = "...", selector = "...")`.

Both use **the same JMS selector language**, yet differ in lifecycle, resources, result handling, and concurrency. This article shows how to combine them properly in Spring Framework 6.x / Spring Boot 3.x applications on Java 17+, using `jakarta.jms.*`.

## 2. Where do selectors operate in the send–receive flow?

~~~text
                 Producer (Spring JmsTemplate)
                         |
          convertAndSend("orders.events", body,
              message -> {
                setStringProperty("eventType", ...);
                setIntProperty("priorityLevel", ...);
              })
                         |
                         v
                  JMS provider/broker
                         |
                  queue: orders.events
                         |
            +------------+------------+
            |                         |
   Consumer A                    Consumer B
   selector:                     selector:
   eventType='ORDER_CREATED'     eventType='REFUND_REQUESTED'
   AND priorityLevel >= 5
            |                         |
     receives only messages matching each consumer's condition
~~~

**Selectors are specified by the consumer, not a call that mutates messages.** The producer must attach the message properties or standard headers accessible to the selector; the consumer declares the expression when creating the consumer/endpoint. A selector does **not** add missing properties to a message.

In Jakarta Messaging, a selector is a `String` with syntax based on **a subset of SQL-92**, not a SQL statement running in a database. It is evaluated by the JMS provider against **JMS message properties and certain standard headers**. It **does not read body content**.

If a producer only sends JSON inside a `TextMessage`:

~~~json
{"eventType":"ORDER_CREATED","priorityLevel":8,"orderId":"order-102"}
~~~

then the selector `priorityLevel >= 5` **cannot read the JSON field** inside the body. The producer must set a property with the corresponding name/meaning if JMS-level filtering is desired:

~~~java
// Inside MessagePostProcessor callback, message is jakarta.jms.Message.
message.setStringProperty("eventType", "ORDER_CREATED");
message.setIntProperty("priorityLevel", 8);
~~~

Body and properties are two separate regions, even though they can hold duplicate values. Promote only the metadata genuinely needed for filtering into properties, avoiding duplicating every payload field.

## 3. Selector syntax fundamentals to master

### 3.1. Common operators

| Expression | Meaning |
| --- | --- |
| `eventType = 'ORDER_CREATED'` | String property equals a value |
| `priorityLevel >= 5` | Numeric property comparison |
| `express = TRUE` | Boolean property comparison |
| `priorityLevel BETWEEN 5 AND 9` | Value in a range, inclusive of both endpoints |
| `eventType IN ('ORDER_CREATED', 'ORDER_UPDATED')` | Belongs to a list of String literals |
| `source LIKE 'mobile%'` | String with prefix `mobile` |
| `tenantId IS NOT NULL` | Property exists with a non-NULL value |
| `tenantId IS NULL` | Property absent or NULL-valued |
| `NOT (status = 'CANCELLED')` | Negation under three-valued logic |
| `(a = 1 OR b = 2) AND active = TRUE` | Precedence grouping with parentheses |
| `JMSPriority >= 7` | Checks an allowed standard header |
| `JMSCorrelationID = 'corr-123'` | Matches standard correlation header |

Property names are **case-sensitive**: `priorityLevel` differs from `PriorityLevel`. Selector operator names and `TRUE`/`FALSE` literals are case-insensitive per specification, though consistent casing improves readability. String literals use **single quotes**; Java Strings holding selectors normally use double quotes around the outside.

Example combining multiple conditions:

~~~sql
eventType IN ('ORDER_CREATED', 'ORDER_UPDATED')
AND priorityLevel BETWEEN 5 AND 9
AND tenantId IS NOT NULL
AND (express = TRUE OR source LIKE 'mobile%')
~~~

This is a **standalone selector expression**, not a database SQL script. In Java, write it as a single `String` or concatenated string literals with `+`.

### 3.2. Pay strict attention to property types

JMS comparisons do not automatically convert numeric strings into numbers. These two calls create properties of **different types**:

~~~java
message.setStringProperty("priorityLevel", "8"); // String
message.setIntProperty("priorityLevel", 8);      // int
~~~

With the selector:

~~~sql
priorityLevel >= 5
~~~

only a **property with an appropriate numeric type** matches as intended. The value `"8"` is a String and is not automatically parsed into an int by the selector the way some JMS getters support. Similarly:

~~~java
message.setBooleanProperty("express", true);     // proper boolean
message.setStringProperty("express", "true");     // String, not boolean
~~~

The selector `express = TRUE` is designed to accept the first case. Agree on a **message contract** specifying property names, types, and meanings between producer and consumer.

### 3.3. NULL and three-valued logic

JMS selectors evaluate under three states: **TRUE**, **FALSE**, and **UNKNOWN**. Only **TRUE** counts as a match.

| Property `tenantId` | Selector | Result |
| --- | --- | --- |
| Unset | `tenantId = 'blue'` | UNKNOWN → no match |
| Unset | `tenantId IS NULL` | TRUE |
| `"blue"` | `tenantId = 'blue'` | TRUE |
| `"red"` | `tenantId = 'blue'` | FALSE |
| Unset | `NOT (tenantId = 'blue')` | UNKNOWN → no match |

Therefore, a selector like `NOT (tenantId = 'blue')` does **not** mean receiving every message missing `tenantId`. If business rules want to include messages missing the property, state it explicitly:

~~~sql
tenantId IS NULL OR tenantId <> 'blue'
~~~

Do not assume NULL is a special String or that `NULL = NULL` returns TRUE. Use `IS NULL`/`IS NOT NULL` when checking existence.

### 3.4. Which standard headers can be used?

Standard JMS allows referencing **six standard headers** in selectors:

- `JMSDeliveryMode`
- `JMSPriority`
- `JMSMessageID`
- `JMSTimestamp`
- `JMSCorrelationID`
- `JMSType`

Do **not** use `JMSDestination` or `JMSReplyTo` as standard selector headers, even though both have getters on `Message`. Also do not use `JMSExpiration` as a standard selector header.

For `JMSDeliveryMode`, in a selector the corresponding value is the literal **`'PERSISTENT'`** or **`'NON_PERSISTENT'`**, not the Java integer value of the `DeliveryMode.PERSISTENT` constant.

Properties like `JMSXGroupID` have dedicated JMS semantics; do not invent business names with `JMSX` or `JMS_` prefixes, as they belong to the standard/provider namespace.

## 4. Combining selectors with synchronous receive in JmsTemplate

### 4.1. Why not call receive(selector) directly?

In Spring JMS, the basic overloads:

~~~java
jakarta.jms.Message receive();
jakarta.jms.Message receive(String destinationName);
jakarta.jms.Message receive(jakarta.jms.Destination destination);
~~~

do **not** accept a selector as the second parameter. To filter messages synchronously, use the **`receiveSelected`** overloads:

~~~java
// JmsTemplate's default destination:
jakarta.jms.Message receiveSelected(String messageSelector);

// Destination specified by name:
jakarta.jms.Message receiveSelected(
        String destinationName, String messageSelector);

// Existing Destination object:
jakarta.jms.Message receiveSelected(
        jakarta.jms.Destination destination, String messageSelector);
~~~

These are **explanatory signatures for learning**, not a standalone Java file. The actual return value may be `null` on timeout. When code receives the raw JMS message, you can access the body, properties, headers, and JMS message type.

Snippet inside a service that has `JmsTemplate jmsTemplate`:

~~~java
String selector =
        "eventType = 'ORDER_CREATED' AND priorityLevel >= 5";

jakarta.jms.Message message =
        jmsTemplate.receiveSelected("orders.events", selector);

if (message == null) {
    System.out.println("NO_MATCH_IN_TIMEOUT");
} else {
    System.out.println("EVENT_TYPE="
            + message.getStringProperty("eventType"));
    System.out.println("PRIORITY="
            + message.getIntProperty("priorityLevel"));
}
~~~

**Run prerequisites:** the template has a valid `ConnectionFactory`, the queue exists, and consume permissions are granted. Calls to `getStringProperty`/`getIntProperty` throw `JMSException`, so the enclosing method must declare or catch the exception. On receiving a matching message, the code prints the actual type and priority; on an empty queue or no matching message before timeout, it prints only `NO_MATCH_IN_TIMEOUT`.

### 4.2. receiveSelectedAndConvert: filter first, convert after

If only the Java payload is needed, use:

~~~java
Object receiveSelectedAndConvert(String messageSelector);
Object receiveSelectedAndConvert(
        String destinationName, String messageSelector);
Object receiveSelectedAndConvert(
        jakarta.jms.Destination destination, String messageSelector);
~~~

Flow: JMS provider selects a message matching the selector → `JmsTemplate` receives the message → `MessageConverter.fromMessage` converts the body into a Java value. Example:

~~~java
Object payload = jmsTemplate.receiveSelectedAndConvert(
        "orders.events",
        "eventType = 'ORDER_CREATED' AND priorityLevel >= 5");

if (payload instanceof String text) {
    System.out.println("MATCHED_BODY=" + text);
} else if (payload == null) {
    System.out.println("NO_MATCH_IN_TIMEOUT");
}
~~~

With the default converter, `TextMessage` → `String`; `BytesMessage` → `byte[]`; `MapMessage` → `Map`; `ObjectMessage` → a deserialized Java object. **The selector does not determine the post-conversion Java type.** It only selects the message, while the converter determines the Java payload.

If you need to read `JMSCorrelationID` or properties of **the received message itself**, `receiveSelected` returning raw `jakarta.jms.Message` is more suitable; `receiveSelectedAndConvert` typically returns only the payload, without a wrapper carrying all metadata.

### 4.3. Default destination and the single-parameter overload

~~~java
jmsTemplate.setDefaultDestinationName("orders.events");
jmsTemplate.setReceiveTimeout(2_000L);

Object matched = jmsTemplate.receiveSelectedAndConvert(
        "eventType = 'ORDER_CREATED'");
~~~

The **single-parameter** `receiveSelectedAndConvert(String)` treats its argument as the **selector**, taking the default destination from the template. Do not confuse it with `receiveAndConvert("orders.events")`, where the argument is the **destination name**. If no default destination is configured, the single-parameter overload has no valid target and causes a configuration error.

Similarly, `receiveSelected("eventType = 'ORDER_CREATED'")` uses the default destination. If you need to pick the target queue on each call, use the two-parameter overload `receiveSelected("orders.events", selector)`.

### 4.4. receiveTimeout: no match does not mean no messages

Synchronous JMS receive can **block**. `JmsTemplate` provides:

~~~java
jmsTemplate.setReceiveTimeout(2_000L); // up to about 2 seconds
~~~

Rules:

| Timeout value | Behavior |
| --- | --- |
| `0` (default) | Wait indefinitely |
| Positive number | Wait at most the specified milliseconds |
| Negative number | Attempt immediate receive without waiting |

Example of a queue containing messages not matching the selector:

~~~text
Queue orders.events:
  m1 eventType=ORDER_CREATED priorityLevel=2
  m2 eventType=REFUND_REQUESTED priorityLevel=9

Consumer selector:
  eventType = 'ORDER_CREATED' AND priorityLevel >= 5
~~~

A call to `receiveSelected("orders.events", selector)` with a finite timeout can return `null`, **even though the queue is not empty at all**. The two non-matching messages can wait for another consumer or stay in the queue per provider policies, retention, and expiry.

There is no reason to dequeue and discard messages if the goal is simply filtering: that is what selectors are designed to do. However, if unfiltered consumers exist, they **can pick up** the messages that the selector-equipped consumer did not want to process.

### 4.5. Using MessageConsumer directly in the classic JMS API

Spring's `receiveSelected` relies on JMS consumer-side selection. In the underlying API, the equivalent syntax is:

~~~java
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

// session belongs to a valid connection.
// connection.start() must be called to allow delivery.
Queue queue = session.createQueue("orders.events");

try (MessageConsumer consumer = session.createConsumer(
        queue,
        "eventType = 'ORDER_CREATED' AND priorityLevel >= 5")) {

    Message message = consumer.receive(2_000L);
    if (message != null) {
        System.out.println(message.getJMSMessageID());
    }
}
~~~

This is an **excerpt**; the code still needs `Session`, `Connection`, a broker, and exception handling. `try (MessageConsumer...)` uses the JMS 2.0+/Jakarta Messaging API's `AutoCloseable` resource contract. Key point: the selector is attached to the **consumer at creation time**, not placed on messages, and the consumer receives only messages satisfying the expression.

Do not create thousands of new consumers per HTTP request under high throughput. When frequent polling is required, consider long-lived listeners, batching, transactions, backpressure, or a dedicated message-receiving service.

## 5. Combining selectors with @JmsListener

For continuously running consumers, Spring Framework provides the annotation:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class HighPriorityOrderListener {

    @JmsListener(
            destination = "orders.events",
            selector = "eventType = 'ORDER_CREATED' "
                    + "AND priorityLevel >= 5")
    public void onOrder(Message message) throws JMSException {
        System.out.println("BODY_TYPE="
                + message.getClass().getSimpleName());
        System.out.println("PRIORITY="
                + message.getIntProperty("priorityLevel"));
    }
}
~~~

This is an **illustrative Spring component**: to run, it requires a JMS provider, `ConnectionFactory`, listener infrastructure, and the matching queue. `@JmsListener.selector` is a **JMS selector**, configured on the listener container's endpoint/consumer. Only matching messages are dispatched to the method.

Spring can convert the payload for a `String` or DTO parameter via the configured converter. Receiving `jakarta.jms.Message` as above is convenient if you need to inspect the exact properties/headers used for filtering.

### 5.1. Spring setup and lifecycle

A listener has two parts:

1. **Endpoint registration:** Spring discovers `@JmsListener` on managed beans.
2. **Listener container/consumer creation:** the container uses `ConnectionFactory` and configures `destination`, `selector`, concurrency, transactions, and acknowledgment.

In plain Spring Framework, enable `@EnableJms` and configure an appropriate `JmsListenerContainerFactory`. With Spring Boot, the JMS starter and auto-configuration usually provide the required beans; `@EnableJms` can still be declared explicitly in examples.

Without a broker or proper bean factory, merely putting `@JmsListener` on a Java class is not enough to create an active listener. Non-Spring-managed classes are not scanned automatically either.

### 5.2. Selectors are attached on the consumer, not an if statement inside the method

Compare:

~~~java
// Approach WITHOUT broker-side filtering:
@JmsListener(destination = "orders.events")
public void receiveAll(Message msg) throws JMSException {
    if (msg.getIntProperty("priorityLevel") >= 5) {
        handle(msg);
    }
}
~~~

with:

~~~java
// Approach filtering before delivering message to method:
@JmsListener(
    destination = "orders.events",
    selector = "priorityLevel >= 5")
public void receiveHigh(Message msg) throws JMSException {
    handle(msg);
}
~~~

Both **illustrative snippets** assume a `handle(Message)` method and proper imports; they are not complete standalone classes.

In the first approach, the consumer **already pulled** the message from the queue; upon successful acknowledgment, an unwanted message may be treated as consumed even though the code skipped it. In the second approach, the selector prevents delivering non-matching messages to that consumer; those messages still have a chance to be received by another consumer or stay in the queue.

This is a difference in **semantics**, not just CPU optimization.

### 5.3. Multiple listeners on the same queue

Suppose the same queue has:

~~~java
@JmsListener(
    destination = "orders.events",
    selector = "eventType = 'ORDER_CREATED'")
public void orders(Message m) { /* ... */ }

@JmsListener(
    destination = "orders.events",
    selector = "eventType = 'REFUND_REQUESTED'")
public void refunds(Message m) { /* ... */ }
~~~

If the selectors are **mutually exclusive**, each consumer is only eligible to receive its corresponding group of messages (assuming normal queue permissions/provider operation). However, this is **not broadcast**. If two selectors **both match a message**, a JMS queue still delivers that message to **one eligible consumer**, rather than sending two copies to both listeners.

If an additional consumer **without a selector** exists, that consumer can also take messages from both groups. If you need fan-out to multiple independent services, consider a Topic/subscriptions or broker-side replication/routing mechanisms.

### 5.4. Annotation selectors are normally static endpoint configuration

Do not treat `@JmsListener(selector="...")` as an expression that automatically changes per message. The consumer selector is attached when the endpoint/consumer is established; changing the condition normally requires updating configuration and reinitializing the endpoint/container via Spring mechanisms.

If the application needs dynamic per-request tenant filtering, you cannot simply mutate a Java variable inside a method and expect the consumer selector to change immediately. Consider partitioned queues, logical subscriptions, per-instance configured selectors, or dedicated routing.

## 6. Choosing between receiveSelected and @JmsListener

| Criterion | `receiveSelected(...)` | `@JmsListener(selector = ...)` |
| --- | --- | --- |
| Model | Synchronous, caller explicitly invokes | Asynchronous, container invokes method |
| When does receiving start? | When the call runs | While the listener container is running |
| Messages per invocation | At most one message per call | One message processed per invocation |
| Thread | Caller thread blocks until match/timeout/error | Listener container thread |
| Timeout | `JmsTemplate.receiveTimeout` | Container manages its own receive/lifecycle loop |
| Startup/shutdown control | Decided by caller | Managed by listener container/registry |
| Property/filter | Selector String passed per call | Selector declared on endpoint |
| Payload | Can get raw Message or converted payload | Raw Message parameter or converter-processed payload |
| Resource | Can create/close JMS consumer per call | Long-lived consumer managed by container |
| Use case | Short-lived worker polling, receiving replies or conditional jobs | Continuous consumption service, background worker |
| Risks | Blocking threads, creating many consumers, timeouts | Concurrency, transaction/redelivery, assuming dynamic selector |

**Neither approach is universally better.** Use `receiveSelected` when a workflow needs to invoke receive **intentionally** at a specific point; use a listener when the application needs continuous consumption with container-managed lifecycle.

Both share the same JMS selector language. When designing a system, do not put an unfiltered polling consumer next to a selector-equipped listener on the same queue expecting the listener to always get the priority group; the unfiltered consumer can grab messages first.

## 7. Runnable example: Spring Boot 3.x + Artemis, comparing both approaches

The example uses two separate queues to **avoid competing for messages**:

- `demo.selector.poll`: demonstrates `JmsTemplate.receiveSelectedAndConvert`.
- `demo.selector.listen`: demonstrates `@JmsListener(selector = ...)`.

Each queue receives one message with `priorityLevel=2` and one message with `priorityLevel=8`, with a corresponding event type. Consumers with selectors receive only the high-priority message. Low-priority messages **are not taken by the selector-equipped consumers**; if there are no other consumers and messages have not expired, they can remain on the broker.

### 7.1. Environment preparation

Create a Maven project from [Spring Initializr](https://start.spring.io/) with:

- Java **17+**, Spring Boot **3.x**, Group `com.example`, Artifact `jms-selectors-demo`.
- Dependency **Spring for Apache ActiveMQ Artemis** (`org.springframework.boot:spring-boot-starter-artemis`).
- An Artemis broker running **externally** at `tcp://localhost:61616`.
- Both queues `demo.selector.poll` and `demo.selector.listen` exist or the broker has an appropriate auto-create policy, with an account having send/consume permissions.
- No stale messages in either queue, and no other consumers on either queue when running the demo.

Set environment variables `ARTEMIS_USER` and `ARTEMIS_PASSWORD` matching your broker. File `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}

spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=3s
~~~

`spring.artemis.mode=native` **does not start an embedded broker**. `receive-timeout=3s` bounds the wait duration of `JmsTemplate`, and does not define TTL or listener timeout.

### 7.2. Complete Java code

Create file `src/main/java/com/example/JmsSelectorsDemoApplication.java`:

~~~java
package com.example;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsSelectorsDemoApplication {

    private static final String POLL_QUEUE = "demo.selector.poll";
    private static final String LISTEN_QUEUE = "demo.selector.listen";

    public static void main(String[] args) {
        SpringApplication.run(JmsSelectorsDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(JmsTemplate template) {
        return args -> {
            // Group 1: polling queue has one low and one high.
            sendEvent(template, POLL_QUEUE,
                    "POLL_LOW", "ORDER_CREATED", 2);
            sendEvent(template, POLL_QUEUE,
                    "POLL_HIGH", "ORDER_CREATED", 8);

            Object chosen = template.receiveSelectedAndConvert(
                    POLL_QUEUE,
                    "eventType = 'ORDER_CREATED' "
                            + "AND priorityLevel >= 5");

            System.out.println("POLL_MATCH=" + chosen);

            // Group 2: listener queue, @JmsListener consumer with selector.
            sendEvent(template, LISTEN_QUEUE,
                    "LISTENER_LOW", "INVOICE_READY", 2);
            sendEvent(template, LISTEN_QUEUE,
                    "LISTENER_HIGH", "INVOICE_READY", 8);

            System.out.println("PUBLISHED=4");
        };
    }

    private static void sendEvent(
            JmsTemplate template,
            String destination,
            String body,
            String eventType,
            int priority) {

        template.convertAndSend(destination, body, message -> {
            message.setStringProperty("eventType", eventType);
            message.setIntProperty("priorityLevel", priority);
            return message;
        });
    }
}

@Component
class HighPriorityInvoiceListener {

    @JmsListener(
            destination = "demo.selector.listen",
            selector = "eventType = 'INVOICE_READY' "
                    + "AND priorityLevel >= 5")
    public void receive(Message message) throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected TextMessage");
        }

        System.out.println("LISTENER_MATCH="
                + textMessage.getText());
        System.out.println("LISTENER_PRIORITY="
                + message.getIntProperty("priorityLevel"));
    }
}
~~~

Why the code compiles:

1. One `public class JmsSelectorsDemoApplication` resides in the file of the same name; `HighPriorityInvoiceListener` is a package-private `@Component` in the same package, which Spring can still scan.
2. `@EnableJms` enables listener annotation infrastructure (Spring Boot supports an auto-configured listener factory when dependencies/ConnectionFactory are valid).
3. `MessagePostProcessor` sets native JMS properties before sending.
4. `receiveSelectedAndConvert` returns a Java `Object` (in the default TextMessage case, a String), and returns `null` on timeout if no matching message arrives.
5. `@JmsListener` receives raw `jakarta.jms.Message`, reading the `TextMessage` and the `int` property.
6. Both consumers use **two independent queues**, avoiding the risk of polling and listener on the same queue competing for a message during the illustration.

### 7.3. Running and observing

In the Maven project directory:

~~~bash
mvn spring-boot:run
~~~

On Windows, if the project has a Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

With a valid broker, permissions, queues, and consumer configuration, and no stale messages/other consumers, the expected business lines include:

~~~text
POLL_MATCH=POLL_HIGH
LISTENER_MATCH=LISTENER_HIGH
LISTENER_PRIORITY=8
PUBLISHED=4
~~~

**The line order is not guaranteed to always match the block above.** `POLL_MATCH=POLL_HIGH` happens inside ApplicationRunner before publishing to the listener group; the two lines from the listener may appear before or after `PUBLISHED=4` due to asynchronous execution. Spring also prints startup logs. The sample output is **expected**, not the result of running Maven/broker in the authoring environment.

If queues are unavailable or permissions are wrong, send/receive may throw exceptions. If receive reaches 3 seconds without a matching message, the code prints `POLL_MATCH=null`. Since a matching high message was just sent, a timeout in a clean environment signals that the broker, selector, or resources should be inspected. When leftover messages exist, order/values can differ.

### 7.4. Checking the two unmatched messages

In a test environment with **no other consumers** and before expiration, the broker may still retain:

~~~text
demo.selector.poll    -> POLL_LOW      priorityLevel=2
demo.selector.listen  -> LISTENER_LOW  priorityLevel=2
~~~

You can use the broker management UI/JMX/CLI to inspect queue depth and properties. There is no need to modify code to dequeue them in the main selector test.

**Important:** an unmatched message does not mean the provider must store it forever. TTL, expiration, broker policies, and other consumers can still cause messages to disappear or be delivered. For a queue, conclude only that the current consumer **was not delivered that message**.

### 7.5. Changing the property to test strong typing

Try replacing the line:

~~~java
message.setIntProperty("priorityLevel", priority);
~~~

with:

~~~java
message.setStringProperty(
        "priorityLevel", Integer.toString(priority));
~~~

in a **separate test run**, keeping `priorityLevel >= 5` in the selector. The String value `"8"` does not become numeric automatically, so `POLL_HIGH`/`LISTENER_HIGH` fail to match as intended. Restore the typed setter `setIntProperty`.

Do not change code and reuse broker queues that still hold backlog without cleaning test data, as mixed messages from previous runs can lead to wrong conclusions.

## 8. Queue vs. Topic when using selectors

Selectors apply to both `Queue` and `Topic`, but **the semantics of unmatched messages differ**.

| Scenario | Queue | Topic |
| --- | --- | --- |
| Consumer does not match selector | Message may remain in the queue or be received by another eligible consumer | Message is not added to that subscription when unmatched |
| Multiple consumers present | One message is delivered to one queue consumer per delivery | Each subscription can receive its own copy per pub/sub |
| Two selectors both match | No broadcast: one queue message is delivered to one consumer | Two independent subscriptions can both receive copies |
| No consumer yet | Queue can store backlog per policy | Non-durable subscriptions do not exist without a consumer; durable has its own rules |
| Need same event in multiple services | Usually requires multiple queues/broker routing | Topic + subscriptions is a better fit |

Example of a Topic `orders.events` with two subscriptions:

~~~text
Topic orders.events
    |
    +--> Subscription A:
    |      selector = "eventType = 'ORDER_CREATED'"
    |
    +--> Subscription B:
           selector = "priorityLevel >= 5"
~~~

A message with `eventType=ORDER_CREATED` and `priorityLevel=8` can be received by **both subscriptions** under topic semantics, unlike two `@JmsListener` endpoints competing on the same queue.

In Spring, topic configuration requires `pubSubDomain=true`/appropriate listener container factory, and may need a subscription name/client ID for durable subscriptions. Do **not** merely rename a queue to `"topic.orders"` assuming JMS turns it into a topic automatically; domain and provider destination must align.

## 9. Selectors by JMSCorrelationID in request/reply

An important use case of `receiveSelected` is receiving a reply by correlation ID on a **shared reply queue**. For example, when the requester already knows the correlation:

~~~java
import java.util.UUID;
import jakarta.jms.Message;

String correlation = "corr-" + UUID.randomUUID();
String selector =
        "JMSCorrelationID = '" + correlation + "'";

Message reply = jmsTemplate.receiveSelected(
        "replies.shared", selector);

if (reply == null) {
    System.out.println("REPLY_TIMEOUT");
} else if (!correlation.equals(reply.getJMSCorrelationID())) {
    throw new IllegalStateException("Correlation mismatch");
}
~~~

This is an **excerpt** requiring `jmsTemplate`, a broker, and a responder actually sending a reply to `replies.shared` **with JMSCorrelationID set to the matching value**. It does not send a request or create a reply itself. `UUID` produces a correlation without single quotes so the example avoids escaping the selector literal; if a correlation comes from free-form input, single quotes must be escaped per JMS selector syntax, or use application-generated IDs with a safe character set.

**Distinguish three things:**

- Destination determines which queue the reply is sent to.
- Selector determines which message a consumer receives on that queue.
- JMSCorrelationID helps the requester identify which request a reply belongs to; it does not guarantee responses arrive at the right destination and is not an authentication credential.

Under high request volume, **creating a separate MessageConsumer with a selector per request** can be expensive for broker/connection resources. Consider temporary reply queues or a shared reply dispatcher that routes by correlation via a pending-requests map.

Do not rely on selectors alone as a complete RPC system: timeouts, late replies, correlation uniqueness, security, idempotency, and proper lifecycle management are required.

## 10. Multiple selectors and overlapping conditions

If the same queue has two listeners:

~~~text
A: priorityLevel >= 5
B: eventType = 'ORDER_CREATED'
~~~

A message with `priorityLevel=8` and `eventType=ORDER_CREATED` matches **both A and B**. The queue does **not** send two copies to both listeners, and JMS does not guarantee the message will go to whichever listener business expects when both are eligible.

When routing by event type, design **mutually exclusive** selectors:

~~~sql
eventType = 'ORDER_CREATED' AND priorityLevel >= 5
~~~

and:

~~~sql
eventType = 'ORDER_CREATED' AND priorityLevel < 5
~~~

Then each `ORDER_CREATED` message with a valid numeric priority property matches only one branch. However, messages **missing `priorityLevel`** or having the wrong type may **match neither** due to NULL/UNKNOWN/type-mismatch rules; decide the rule for malformed/legacy-schema data.

You can add a dedicated consumer for missing metadata, such as `eventType = 'ORDER_CREATED' AND priorityLevel IS NULL`, provided the broker/provider handles the syntax properly and the contract is agreed upon. Avoid deploying overlapping selectors and expecting deterministic delivery to a fixed handler.

## 11. Selectors and security, performance, and operations

### 11.1. Selectors are not an authorization mechanism

A selector like `tenantId = 'tenantA'` is only a **message filtering condition**. It does not verify that the sender is authorized to write `tenantId`, nor does it prevent another consumer with queue access from reading tenantA's messages using a different selector.

To isolate tenants with security requirements, use broker ACLs, separate destinations/identities, encryption, and proper source authentication. Do not rely on a String property to enforce mandatory isolation.

### 11.2. Complex selectors have a cost

The broker/provider must evaluate expressions over metadata. Overly long selectors, many OR/LIKE clauses, or huge numbers of consumers each with its own selector can increase CPU/memory usage and make throughput harder to predict. Optimization depends on the provider; no JMS standard guarantees specific indexing or performance.

Consider:

- Separating destinations cleanly when message flows are completely different.
- Using a few stable, properly typed properties to keep selectors simple.
- Tracking metrics for queue depth, age of oldest message, expired/dead-lettered counts, and consumer count.
- Setting finite receive timeouts for synchronous polling.
- Using long-lived containers with appropriate concurrency for continuous workloads.
- Never constructing selectors directly from raw user input; apply validation and escaping.
- Distinguishing **unmatched** backlog from backlog caused by slow consumers or broker errors.

### 11.3. Single quotes and selector injection

If you must construct a selector from a String containing single quotes, JMS syntax escapes a literal with **two single quotes**. For example, a name containing `O'Neil` must be represented as the literal `'O''Neil'`:

~~~java
String tenant = "O'Neil";
String escaped = tenant.replace("'", "''");
String selector = "tenantName = '" + escaped + "'";
~~~

If filtering access involves sensitive data, do not rely on escaping alone: authenticate/authorize tenants, restrict length/characters, and protect broker resources. A selector is a meaningful expression, not a harmless search string.

### 11.4. Do not assume all of SQL-92 works

JMS selectors only support a **subset** of SQL-92. Do not write:

~~~sql
SELECT * FROM orders WHERE status = 'READY'
~~~

or use SQL comments `-- comment`, JOINs, subqueries, or arbitrary database functions; they are **not** valid message selectors. A selector is strictly a conditional expression, such as:

~~~sql
status = 'READY' AND priorityLevel >= 5
~~~

Property names must obey identifier rules; do not use names containing spaces or hyphens expecting the parser to accept them. If complex metadata names are needed, normalize valid names when the producer sets properties.

## 12. Transactions, acknowledgment, and redelivery

Selectors determine **which messages are offered** to a consumer, but do not replace ack/transaction mechanisms.

- With `receiveSelected`, once a message is received, how acknowledgment/commit occurs depends on the template's session/transaction. Do not assume throwing an exception **after** the method returns will automatically make the broker redeliver.
- With `@JmsListener`, the listener container manages session/concurrency/ack/transactions; when the method fails, rollback/redelivery follows the corresponding configuration.
- If a message is redelivered, it may match the same selector again because properties remain unchanged; business logic should be idempotent.
- Unmatched messages are typically not taken/acked by a selector-equipped consumer. However, expiry, broker policies, and other consumers can still alter the queue.
- No JMS selector guarantees exactly-once processing with a database; if atomicity/correctness is required, design transactions, idempotency, retries, and DLQ properly.

In a queue containing messages that match none of the active selectors, they can accumulate over time. Design an observable handling path for unknown/malformed-schema metadata, expiry, or DLQ; do not enable an unfiltered consumer merely to "drain" and silently drop all messages.

### 12.1. Poison messages and identifying schema-mismatched messages

Suppose the producer changes `priorityLevel` from int to String without upgrading consumers. Two listeners with selectors `priorityLevel >= 5` and `priorityLevel < 5` will both fail to receive the String version under numeric assumptions. The result can be steadily growing backlog without any listener code throwing an exception.

Monitor queue depth and message age, inspect actual properties, and run integration tests between producers and selectors before deploying type changes. Do not assume every stuck message is a "corrupted" message; sometimes it is valid, yet no consumer is registered with matching criteria.

## 13. Selector testing checklist

1. **Names and types:** does the producer call the right `setStringProperty`, `setIntProperty`, `setBooleanProperty` matching the selector?
2. **Destination:** do both sides use the same actual Queue/Topic and same name/namespace/provider?
3. **Syntax:** is the selector a JMS conditional expression with single-quoted Strings, boolean TRUE/FALSE, and clear parentheses?
4. **Null:** which properties may be missing? Are `IS NULL`, UNKNOWN, and `NOT` accounted for properly?
5. **Competing consumers:** is there an unfiltered consumer or overlapping selector on the queue?
6. **Timeout:** does synchronous receive have a reasonable timeout and handle `null`?
7. **Listener:** is `@JmsListener` scanned by Spring, is the listener factory running, and is the selector config active?
8. **Post-conversion type:** if using `receiveSelectedAndConvert`, is the runtime payload type checked?
9. **Transaction:** are ack, rollback, retry, and DLQ aligned when handlers fail?
10. **Observability:** are there metrics for backlog/no-matching-consumers/expired messages?
11. **Security:** are ACLs and authorization enforced outside selectors for sensitive tenants/objects?
12. **Rollout:** are property names/schemas compatible with older messages still sitting in the broker?

A minimal test suite should send a **matching message**, a **non-matching message**, a **missing property**, a **wrong-type property**, and **two overlapping selectors** if the architecture has multiple consumers. Cross-check queue depth and message bodies/metadata using broker management tooling, not just handler logs.

## 14. Common errors and troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `receiveSelected` always returns `null` | No matching message before timeout | Inspect queue depth, selector, and actual properties |
| Queue has messages yet listener does not run | Backlogged messages do not match, endpoint not started, or wrong destination | Check listener registry, selector, broker permissions |
| Numeric selector misses `"8"` | Property was written as String | Use `setIntProperty`, do not expect auto-conversion |
| Boolean selector misses `"true"` | Property was written as String | Use `setBooleanProperty` |
| `NOT (tenantId = ...)` misses messages lacking tenantId | UNKNOWN logic | Use `IS NULL` if missing cases should be included |
| Calling `receiveSelected("queue")` gets unexpected result | Single argument is the **selector** when using default destination | Call `receiveSelected(destinationName, selector)` overload |
| Calling `receive(...)` does not filter despite properties | `receive` does not take a selector | Use `receiveSelected` or a listener with selector |
| Listener receives messages from the wrong group | Overlapping selectors or an unfiltered consumer exists | Audit all consumers, design mutually exclusive conditions |
| Two listeners expected to receive the same queue message | Queues do not broadcast | Use topic/subscriptions or fan-out routing |
| `JMSReplyTo = ...` in selector does not work | Header is not in the JMS selector header set | Use allowed headers, properties, or select destination on consumer |
| `TextMessage` JSON has field yet selector misses it | Selectors do not read body | Copy filterable metadata into typed properties |
| Selector String literal with single quote errors | Unescaped `'` | Escape with `''` or generate safe IDs |
| Request/reply misses matching reply | Missing/wrong correlation or another consumer took it | Use `JMSCorrelationID` per contract; manage shared reply queue |
| Unmatched messages accumulate | No eligible consumer / unsuitable TTL | Monitor backlog, fix contract, add consumer/policy |
| Error after receive causes lost or duplicate messages | Incorrect ack/transaction/redelivery | Configure and test rollback/idempotency |
| Performance drops with thousands of selector consumers | Broker/consumer creation overhead | Consolidate dispatch, choose partitioning or long-lived listeners |

## 15. Self-check questions

**Question 1.** To synchronously read only orders with `priorityLevel>=5`, should you call `receive("orders.events")` and check in code, or `receiveSelected("orders.events", selector)`?

**Answer:** Use `receiveSelected` so the provider delivers only matching messages. Calling `receive` without a selector and skipping may consume/ack unwanted messages.

**Question 2.** Which destination does `receiveSelectedAndConvert("eventType = 'ORDER_CREATED'")` use?

**Answer:** The default destination configured on `JmsTemplate`. This single-argument overload takes the **selector**, not a destination name.

**Question 3.** Does `@JmsListener(selector="express = TRUE")` receive a message sent with `setStringProperty("express","true")`?

**Answer:** It does not match as a Boolean as intended: Strings are not auto-parsed into Booleans by selectors. The producer must use `setBooleanProperty`.

**Question 4.** A queue has messages that do not match a listener. Are those messages guaranteed to be deleted?

**Answer:** No. Those messages are simply not delivered to the consumer with that selector; they can stay in the queue or be received by another consumer, depending on expiry and broker policies.

**Question 5.** Two listeners on the same queue have overlapping selectors that both match a message. Are both invoked?

**Answer:** No. A queue delivers one message to one eligible consumer, not fan-out. If both services must receive it, consider Topic/subscriptions.

**Question 6.** Can a selector access `JMSDestination` or an `orderId` field inside a JSON body?

**Answer:** No. `JMSDestination` is not part of the standard JMS headers for selectors; bodies are not read by selectors either. Use appropriate properties or pick the destination directly.

**Question 7.** What is the difference between `receiveSelected` and `receiveSelectedAndConvert`?

**Answer:** Both select messages using a selector, while `receiveSelected` returns the raw JMS Message and `receiveSelectedAndConvert` returns the Java payload via `MessageConverter`.

**Question 8.** `tenantId` is missing and the selector is `NOT (tenantId='blue')`. Does the message match?

**Answer:** No, because comparing against a NULL property yields UNKNOWN, and negating UNKNOWN remains UNKNOWN. Only TRUE matches.

**Question 9.** Can `JMSCorrelationID` be used to filter responses on a shared reply queue?

**Answer:** Yes, because it is one of the six standard headers supported by JMS selectors. You still must manage reply destinations, timeouts, concurrency, and security separately.

**Question 10.** In the two-queue demo, why was it necessary to separate the polling queue from the listener queue?

**Answer:** If sharing one queue, the two consumers could compete for messages, making output timing-dependent. Separating into two queues demonstrates both selection mechanisms independently.

## Official documentation for reference

- [Jakarta Messaging 3.1 Specification — Message selection (3.8), queue semantics (4.1.2) and topic semantics (4.2.2)](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): syntax standard, selector-accessible headers/properties, NULL, and unmatched behavior.
- [Jakarta Messaging 3.1 API — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): property types, selector syntax, and rules.
- [Spring Framework 6.2.14 Javadoc — JmsTemplate](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `receiveSelected`, `receiveSelectedAndConvert`, `setReceiveTimeout`, and overloads.
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): synchronous receive, blocking and timeout.
- [Spring Framework Reference — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, endpoint/container lifecycle, listener arguments.
- [Spring Framework 6.2 — JmsListener Annotation](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/JmsListener.html): the `selector` attribute of the annotation.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): starter, native broker, listener auto-configuration.
