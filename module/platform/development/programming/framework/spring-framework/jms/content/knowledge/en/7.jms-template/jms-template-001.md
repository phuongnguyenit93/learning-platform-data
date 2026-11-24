# The Role of JmsTemplate in Managing JMS Operations and Resources

## 1. What problem does JmsTemplate solve?

`JmsTemplate` is the central class in `org.springframework.jms.core` of **Spring Framework JMS**. It provides a **template** for **synchronous** message sending and receiving over Jakarta Messaging/JMS, allowing business code to focus on **what to send, where to send, and what to receive**, instead of repeating boilerplate for creating/closing `Connection`, `Session`, `MessageProducer`, `MessageConsumer`, handling `JMSException`, and coordinating resources with Spring transactions.

Lesson objectives:

1. Identify **what Spring handles for you** and **what the application remains responsible for**.
2. Understand the `ConnectionFactory → Connection → Session → Producer/Consumer` lifecycle when using `JmsTemplate`.
3. Distinguish `send`/`receive`, `convertAndSend`/`receiveAndConvert`, `MessageCreator`, `MessagePostProcessor`, and low-level callbacks.
4. Know the impact of `CachingConnectionFactory`, transactions, acknowledgement, timeouts, and exceptions.
5. Practice with a Spring Boot 3.x + Apache ActiveMQ Artemis example, including runnable code, commands, and verification results.

**Short definition:** `JmsTemplate` is **not a broker**, does not store messages on behalf of a broker, and does not replace a JMS provider. It is a Spring application-layer class that uses a `ConnectionFactory` to interact with the provider while managing resources consistently.

### 1.1. Before and after using the template

With the classic Jakarta Messaging API, a send operation basically goes through:

~~~text
ConnectionFactory
     │ createConnection()
     ▼
Connection
     │ createSession(...)
     ▼
Session
     │ createProducer(destination), createTextMessage(...)
     ▼
MessageProducer
     │ send(message)
     ▼
JMS provider ──────► Broker

finally: close MessageProducer, Session, Connection
~~~

With Spring JMS:

~~~text
BusinessService
     │
     │ jmsTemplate.convertAndSend("orders.queue", orderId)
     ▼
JmsTemplate
     ├── obtains Session/Connection from ConnectionFactory or Spring transaction
     ├── creates / uses MessageProducer
     ├── creates JMS Message (via MessageConverter)
     ├── sends message, applies appropriate QoS configuration
     ├── translates JMSException to Spring JmsException (unchecked)
     └── releases resources appropriately (closes or returns to cache/pool)
                    │
                    ▼
             JMS provider ───► Broker
~~~

**Important point:** “the template releases resources” does not necessarily mean every call closes the **physical TCP connection**. If the `ConnectionFactory` is wrapped by `CachingConnectionFactory` or a pool, the template's logical close may return the handle to the cache/pool for reuse.

## 2. Responsibility breakdown by layer

| Component | Primary responsibility | Not responsible for |
| --- | --- | --- |
| `ConnectionFactory` (Jakarta JMS API) | Provides `Connection` to the JMS provider; configures authentication, endpoint, and provider parameters | Deciding business message content |
| `Connection` | Links the client to the provider/broker, creates `Session`; classic consumers require the connection to be started | Ensuring every message is processed properly on its own |
| `Session` | Creates messages, producers, consumers, queue/topic objects; scopes JMS ack/transaction | Being a thread-safe object for concurrent use across threads |
| `MessageProducer` | Sends messages to a destination, applies certain QoS settings | Durable broker-side message storage |
| `MessageConsumer` | Receives messages; synchronously or by registering a listener depending on the API | Guaranteeing business handler success |
| `JmsTemplate` | Wraps synchronous send/receive operations, resource lifecycle, callbacks, conversion, error translation | Hosting the broker, auto-retrying all errors, or guaranteeing end-to-end exactly-once |
| `MessageConverter` | Converts Java payload ⇄ JMS `Message` according to converter rules | Inferring arbitrary unconfigured schemas |
| Listener container / `@JmsListener` | Manages asynchronous consume threads, long-lived sessions/consumers, and listener invocations | Replacing the need to define transactions, DLQ, and idempotency |
| JMS provider / broker | Implements JMS protocol/semantics, delivery, store/routing, and security | Understanding the application's order/payment business logic |

**JMS itself is only an API and semantics**; `JmsTemplate` requires a provider such as **Apache ActiveMQ Artemis**, ActiveMQ Classic, IBM MQ, etc., and an actual broker/service. Do not treat adding the `spring-jms` dependency without a JMS provider as a complete messaging system.

## 3. Sending messages without manual resource management

### 3.1. The manual approach: highly prone to boilerplate

The code below is an **illustrative method**, not a standalone program. `factory` is a `jakarta.jms.ConnectionFactory` configured to connect to the provider. `Connection` and `Session` are opened/closed via try-with-resources, and `MessageProducer` is closed via try-with-resources. This is what typically has to be done without Spring:

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

static void sendManually(ConnectionFactory factory, String body)
        throws JMSException {
    try (Connection connection = factory.createConnection();
         Session session =
             connection.createSession(false, Session.AUTO_ACKNOWLEDGE)) {
        Queue queue = session.createQueue("orders.queue");
        try (MessageProducer producer = session.createProducer(queue)) {
            TextMessage message = session.createTextMessage(body);
            producer.send(message);
        }
    }
}
~~~

Explanation:

- `createConnection()` requires a matching provider, credentials, and network; it can fail.
- `createSession(false, Session.AUTO_ACKNOWLEDGE)` creates a non-transacted session; the acknowledgement mode mainly relates to **received messages**.
- `session.createQueue("orders.queue")` creates a destination object by name, **without guaranteeing that the broker has provisioned the queue**; auto-create policy depends on the provider.
- Sending a message **does not require** `connection.start()`; starting relates to enabling delivery to classic API consumers.
- There are many checked `JMSException` types that must be handled or declared.
- If business code has dozens of send operations, manually writing open/close/catch blocks repeatedly increases the risk of incomplete or incorrect handling.

### 3.2. Using `JmsTemplate`

Once Spring has created the `JmsTemplate` bean from `ConnectionFactory`:

~~~java
import org.springframework.jms.core.JmsTemplate;

class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void sendOrder(String orderId) {
        jmsTemplate.convertAndSend("orders.queue", orderId);
    }
}
~~~

This is a service code snippet, without `main`. Spring handles creating/obtaining the JMS session, converting `String` into a `TextMessage` (with the default converter), sending, and cleaning up. Application code **does not call `Connection.close()` or `Session.close()`** on each send.

**Minimalism does not mean losing control:** when you need to add headers/properties or create a specific message format, use the callbacks below.

## 4. Three common ways to send: convertAndSend, send, and post-processor

### 4.1. `convertAndSend` — let the converter create the message

~~~java
jmsTemplate.convertAndSend("orders.queue", "order-42");
~~~

With the default `SimpleMessageConverter`, `String` is wrapped into a `TextMessage`. From the caller's side, this is the most concise call if the payload is of a type the converter understands.

Common mappings of `SimpleMessageConverter`:

| Java payload | JMS message typically created |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` | `MapMessage` (values within the JMS-supported type set) |
| `Serializable` | `ObjectMessage` (when none of the above types match) |

By default, not every POJO turns into JSON. If you want JSON, Avro, Protobuf, etc., you need an **appropriate `MessageConverter`** or explicit serialization. `ObjectMessage` uses Java serialization, which carries security and version-compatibility risks; do not arbitrarily deserialize Java payloads from untrusted sources.

### 4.2. `send` + `MessageCreator` — create the JMS Message manually

`MessageCreator` receives a `Session` provided by `JmsTemplate`. Inside it, the application creates the message and sets the required headers/properties:

~~~java
import jakarta.jms.TextMessage;

jmsTemplate.send("orders.queue", session -> {
    TextMessage message = session.createTextMessage("order-42");
    message.setStringProperty("eventType", "ORDER_CREATED");
    message.setJMSCorrelationID("request-42");
    return message;
});
~~~

This is a **callback scoped to a single operation**. Do not store `Session`/`MessageProducer`/`Message` in a long-lived cache for use after the callback completes, because Spring may have returned the session to the pool, closed the resource, or switched to another transaction.

`MessageCreator` is suitable when you need to create:

- `TextMessage`, `BytesMessage`, `MapMessage`, `StreamMessage`, `ObjectMessage`.
- Business-defined message properties, such as `eventType`, `tenantId`, or `schemaVersion`.
- JMS headers such as `JMSCorrelationID` or `JMSReplyTo`.
- Body formats that cannot be represented by the default converter.

Note that `JMSMessageID` and `JMSTimestamp` are headers typically updated by the provider upon send. Do not write logic assuming values manually assigned by the developer before sending are always preserved; check the JMS API and provider configuration.

### 4.3. `convertAndSend` + `MessagePostProcessor`

If you want to use the converter while adding headers/properties after conversion:

~~~java
jmsTemplate.convertAndSend(
    "orders.queue",
    "order-42",
    message -> {
        message.setStringProperty("eventType", "ORDER_CREATED");
        message.setJMSCorrelationID("request-42");
        return message;
    }
);
~~~

The sequence is:

~~~text
Java Object
   │ MessageConverter.toMessage(value, session)
   ▼
JMS Message (e.g., TextMessage)
   │ MessagePostProcessor.postProcessMessage(message)
   ▼
JMS Message with added headers/properties
   │ MessageProducer.send(...)
   ▼
Broker
~~~

`MessagePostProcessor` is **not** a consumer and does not perform asynchronous work after the broker receives the message. It runs **before sending** to modify the converted message.

### 4.4. Which approach to choose?

| Need | Choose |
| --- | --- |
| Send `String`/`byte[]`/simple payload using the configured converter | `convertAndSend` |
| Send a simple payload while adding properties/headers | `convertAndSend(..., MessagePostProcessor)` |
| Explicitly control body type/JMS writing methods | `send(..., MessageCreator)` |
| Perform multiple operations sharing a session or producer in one callback | `execute(SessionCallback)` / `execute(ProducerCallback)` |
| Long-lived asynchronous communication | Producer still uses template; receiving side prefers listener container/`@JmsListener` |

## 5. Synchronous message receiving and limitations of JmsTemplate

Primary methods:

- `receive("orders.queue")` returns **`jakarta.jms.Message`** or `null` when the wait expires/no message is available according to configuration.
- `receiveAndConvert("orders.queue")` returns the **converted Java object**, or `null` when no message is received.
- `receiveSelected("orders.queue", "eventType = 'ORDER_CREATED'")` uses a **JMS selector** to filter by selector-supported headers/properties; do not use selectors to query arbitrary JSON inside the body.
- Argumentless `receiveAndConvert()`/`receive()` use the configured default destination, if set.

Example:

~~~java
Object result = jmsTemplate.receiveAndConvert("orders.queue");
if (result instanceof String text) {
    System.out.println("Received: " + text);
} else if (result == null) {
    System.out.println("Receive timeout");
} else {
    throw new IllegalStateException("Unexpected payload type: " +
            result.getClass().getName());
}
~~~

### 5.1. `receive()` can block the thread

Synchronous receive **blocks the calling thread** up to the configured receive timeout. If an HTTP application calls `receive()` with an infinite wait, the request can hold the thread, session, and connection for a long time, exhausting threads/pools under load.

`JmsTemplate#setReceiveTimeout(long)` takes values in **milliseconds**:

| Value | Behavior |
| --- | --- |
| `0` | Wait indefinitely until a message/error/connection close; avoid on latency-sensitive endpoints |
| Positive number, e.g., `5000` | Wait up to approximately 5 seconds |
| Negative number, e.g., `-1` | Do not wait, check immediately for an available message (`receiveNoWait()`) |

With Spring Boot:

~~~properties
spring.jms.template.receive-timeout=5s
~~~

This limits `receive(...)` to approximately 5 seconds, returning `null` afterward if no message arrives. **Do not confuse** receiving `null` due to timeout with a payload whose body is `null`: to distinguish clearly, prefer raw `receive` and define a clear message contract.

**Do not write a listener using an uncontrolled infinite loop calling `receive()`** in Spring Boot when the framework already provides listener container infrastructure for asynchronous consumers.

### 5.2. Why `@JmsListener` is not synonymous with `JmsTemplate.receive`

| Criterion | `JmsTemplate.receive` | `@JmsListener` / listener container |
| --- | --- | --- |
| Processing model | Synchronous pull | Container-maintained consumer, invokes handler when messages arrive |
| Thread | Caller's thread | Listener container's thread/executor |
| Session/consumer | Template creates/obtains within operation scope | Container manages longer-lived lifecycle and concurrency |
| Timeout | Caller sets receive timeout | Container has its own polling/receive settings and lifecycle |
| Common use cases | Testing, bounded batch jobs, operational tools, single request–reply | Services continuously processing messages |
| Retry/transaction | Depends on template configuration, transaction manager, and business logic | Depends on listener transaction/ack settings and broker redelivery |

**In summary:** Spring JMS has two complementary branches: `JmsTemplate` is primarily for **synchronous send and receive**, while **listener containers** are for asynchronous receiving. `JmsTemplate` does not spawn a listener daemon after calling `convertAndSend`.

## 6. Resource management mechanism: what does Spring do internally?

### 6.1. A send operation

~~~text
1. Service calls jmsTemplate.send(...)
2. Template looks up a Session bound to a Spring transaction, if any
3. If none: obtains Connection from ConnectionFactory and creates Session per config
4. Creates MessageProducer for the destination
5. Invokes MessageCreator / converter / post-processor to create the message
6. Sends the message using the producer
7. For a local transacted session created by the template itself:
   commits/rolls back according to the template's operation logic
8. Closes producer and releases Session/Connection appropriately
   - standalone session/connection: closes handle
   - pooled/cached/transaction-bound: returns or retains via wrapper/manager
9. If Jakarta JMS throws an error: translates to Spring JmsException (unchecked)
~~~

The diagram above is a **conceptual model** and does not depict identical internal calls across every version/provider. For example, a transaction manager may supply a session already bound to the thread; in that case, the template **must not prematurely close/commit resources belonging to an external transaction**.

### 6.2. A receive operation

~~~text
1. Service calls jmsTemplate.receive("orders.queue")
2. Template obtains compatible Connection/Session
3. Resolves destination and creates MessageConsumer
4. Ensures the connection can receive messages
5. Consumer.receive(timeout) / receiveNoWait()
6. Returns Message or null
7. Acks/commits according to session, transaction, and template config
8. Closes consumer, releases remaining handles
~~~

In non-transacted **AUTO_ACKNOWLEDGE**, completing the receive may acknowledge the message before business code following `receive()` finishes. If business code after receiving fails, the message is **not automatically** redelivered by the broker. This is why continuous critical processing should typically live in a listener container with clear transaction/redelivery policies.

### 6.3. Resource ownership table

| Resource | Who creates/obtains it in template operations? | Should it be closed manually? |
| --- | --- | --- |
| `ConnectionFactory` | Bean provided by Spring/Boot/JNDI configuration | No; lifecycle is managed by application context/infrastructure |
| `Connection` | Template obtains from factory, or transaction manager holds it | Caller **must not** manually close the template's connection |
| `Session` | Template creates/obtains; or transaction-bound session | Caller **must not** manually close the session passed to a callback |
| `MessageProducer` | Template creates/obtains for send | Template cleans up in the appropriate scope |
| `MessageConsumer` | Template creates/obtains for receive | Template cleans up in the appropriate scope |
| `QueueBrowser` | `browse(...)` and browser callback | Template manages the browser within the callback scope |
| `Message` | Created by Provider/Session, passed back to caller | It is JMS data; must respect message state, type, and the lifetime of the associated session |
| Resources manually created inside a callback using raw API | Caller created them outside what the framework tracks | **Caller must identify and close** them properly to avoid resource leaks |

**Do not pass a `Session` out of a callback to another thread for later use:** a JMS `Session` is a single-threaded context. The fact that the template supports concurrent calls from multiple threads **does not** allow multiple threads to operate concurrently on a single session.

### 6.4. `SessionCallback` and `ProducerCallback`

When standard `send/receive` APIs are insufficient, the template lets you run logic inside a callback that receives already-opened valid resources. **Illustrative snippet** placed inside a service that has `JmsTemplate jmsTemplate`:

~~~java
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import org.springframework.jms.core.ProducerCallback;

Integer sentCount = jmsTemplate.execute(
    (ProducerCallback<Integer>) (session, producer) -> {
        Queue queue = session.createQueue("demo.batch");
        for (int i = 1; i <= 3; i++) {
            Message message = session.createTextMessage("item-" + i);
            producer.send(queue, message);
        }
        return 3;
    }
);
~~~

**Important note on overloads:** `execute(ProducerCallback<T>)` creates a producer according to the template's configuration and the callback can send with it; for a producer not bound to a fixed destination, the `producer.send(queue, message)` pattern is valid. The snippet above is not a standalone program; it requires a JMS provider, imports, and configured beans. Spring manages the lifecycle of the session/producer passed to the callback; do not close them inside the callback.

If you want multiple sends to form an **atomic transaction**, do not assume “one execute callback” automatically creates a transaction across all three sends. You must configure a transactional session or transaction manager and verify commit/rollback behavior per configuration; callbacks are primarily a way to **share resource scope**.

`SessionCallback<T>` provides only `Session`, for operations needing direct session control; `ProducerCallback<T>` provides both `Session` and `MessageProducer`. For simple sends, `convertAndSend` or `send(MessageCreator)` is clearer.

## 7. CachingConnectionFactory: optimizing resources without changing business semantics

Frequent JMS operations may create many intermediate objects. Spring provides several ways to reduce instantiation overhead:

### 7.1. `SingleConnectionFactory`

`SingleConnectionFactory` is a wrapper that holds one **shared physical connection** and typically ignores logical `close()` calls from clients until the wrapper itself is actually closed/reset. It is useful in certain standalone/test environments, though by itself it **does not cache all sessions/producers/consumers**.

### 7.2. `CachingConnectionFactory`

`CachingConnectionFactory` extends `SingleConnectionFactory`, adding caches for:

- `Session` by session type/acknowledge mode.
- `MessageProducer` by destination within a session.
- `MessageConsumer` by destination, selector, `noLocal`, durable subscription name, and relevant attributes.
- Producers/consumers for **TemporaryQueue/TemporaryTopic** are not cached per Spring's policy.

Example (bean configuration illustration only; do not blindly apply alongside other auto-configuration):

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.connection.CachingConnectionFactory;

@Bean
CachingConnectionFactory cachingConnectionFactory(
        ConnectionFactory providerConnectionFactory) {
    CachingConnectionFactory cache =
            new CachingConnectionFactory(providerConnectionFactory);
    cache.setSessionCacheSize(10);
    cache.setCacheProducers(true);
    cache.setCacheConsumers(false);
    return cache;
}
~~~

**This is a configuration snippet**: in a Spring Boot app that already auto-configures a connection factory, defining your own bean can cause circular dependencies or override auto-configuration intent without clear naming/qualifiers. Prefer **Boot configuration properties** when Boot manages the factory, for example:

~~~properties
spring.jms.cache.session-cache-size=5
~~~

Some Spring Boot versions wrap the native connection factory with `CachingConnectionFactory` by default when native pooling is not enabled. Inspect your actual configuration and application logs/bean graph rather than assuming every environment automatically has the same topology.

### 7.3. What must not be misunderstood

- `JmsTemplate` is **thread-safe once configured**, so it can be used as a **singleton bean** injected into multiple services/threads. Do not mutate properties such as timeout or default destination at runtime to create “per-request” state on a singleton.
- `Session` is **not thread-safe under normal JMS usage**; do not keep a `Session` supplied to a callback to share across threads.
- Caching/pooling reduces resource creation overhead; it **does not** turn sends into exactly-once, nor does it guarantee listener completion.
- `session-cache-size` is not equivalent to “strictly at most N sessions app-wide”. Spring caches per mode; the actual resource count can be higher, and under peak load there can also be temporary sessions outside the cache.
- Consumer caching can affect selectors, durable subscriptions, and broker/prefetch settings. Since listener containers already hold consumers and have their own caching strategies, do not enable consumer caching on every wrapper indiscriminately.
- Pools have their own connection/session limits and timeout policies; you must monitor connection, consumer, and session counts as well as provider exhaustion errors.

Conceptual diagram:

~~~text
Thread A ─┐
Thread B ─┼─> singleton JmsTemplate
Thread C ─┘          │
                    ▼
             ConnectionFactory
                    │
                    ├── native provider ConnectionFactory
                    │
                    └── (optionally) CachingConnectionFactory / pool
                          │
                          ├─ cached Connection
                          ├─ Session cache per mode
                          ├─ cached Producer (if enabled)
                          └─ cached Consumer (if enabled / applicable)
~~~

When the template finishes a call, it releases the **logical handle**; the wrapper may reuse the physical resource.

## 8. Exception translation: reducing reliance on checked JMSException

The traditional Jakarta JMS API has many checked `jakarta.jms.JMSException` exceptions. Spring uses `org.springframework.jms.JmsException` (unchecked) and its subclasses to surface errors to the business layer.

~~~text
jakarta.jms.JMSException (checked)
        │ Spring JMS exception translator
        ▼
org.springframework.jms.JmsException (RuntimeException)
        │
        ├─ connection / operation / format errors mapped when a matching type exists
        └─ UncategorizedJmsException for unclassified errors
~~~

Example:

~~~java
import org.springframework.jms.JmsException;

try {
    jmsTemplate.convertAndSend("orders.queue", "order-42");
} catch (JmsException ex) {
    // Do not swallow the exception; decide retry/DLQ/alert per policy.
    throw new IllegalStateException("Could not publish order event", ex);
}
~~~

`JmsTemplate` saves business code from having to declare `throws JMSException` for standard template operations. However, **unchecked does not mean errors disappear**: network issues, broker down, auth failures, invalid destinations, or schema mismatches still require handling, observability, and retry policies.

Do not catch every `RuntimeException` and unconditionally resend. Retrying can create **duplicate messages** if the previous send reached the broker without the client receiving confirmation; business logic requires idempotency/business keys.

## 9. Transactions and acknowledgement: boundaries to understand

### 9.1. What is a JMS transaction?

In a JMS local transaction, sends/receives belonging to **a single transacted session** can commit or roll back together per provider semantics. However, a local JMS transaction **does not automatically** include database writes or HTTP calls. A database transaction and a JMS transaction do not become a distributed transaction simply by sharing `@Transactional`.

Spring provides `JmsTransactionManager` for local JMS transactions on a single `ConnectionFactory`. When a transacted session is already bound to the thread by the manager, `JmsTemplate` detects and participates in it rather than creating an isolated session and committing/closing in the wrong scope.

~~~text
Service @Transactional("jmsTransactionManager")
  ├─ template.convertAndSend("q1", "A")
  └─ template.convertAndSend("q2", "B")
           │
           ▼
 JmsTransactionManager manages Session/commit/rollback
           │
           ├─ commits if the entire block succeeds
           └─ rolls back on exception per transaction config
~~~

The precondition for this diagram is that both operations use the same `ConnectionFactory` and the right transaction manager, without accidentally mixing multiple factories/providers. Do not manually create another `Session` from a different connection inside the block and expect it to automatically join that transaction.

### 9.2. Spring transaction example (illustrative configuration snippets)

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.connection.JmsTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Bean("jmsTransactionManager")
PlatformTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional("jmsTransactionManager")
public void publishPair() {
    jmsTemplate.convertAndSend("demo.orders", "order-created");
    jmsTemplate.convertAndSend("demo.audit", "audit-created");
}
~~~

Both snippets must be placed in proper Spring configuration/service classes with valid annotations/beans/fields; **they are not standalone Java files**. Ensure transaction management is enabled and the bean/qualifier matches. In Spring Boot, if a `JtaTransactionManager` or another default transaction manager is present, specify the JMS transaction manager by name as shown rather than using an unqualified `@Transactional` and guessing.

**A JMS exception thrown at the end of a transaction is not “fixed” simply by retrying blindly.** Verify delivery semantics, broker redelivery, and message idempotency.

### 9.3. How does `sessionTransacted` on the template differ from a transaction manager?

`JmsTemplate` has `sessionTransacted` to create a transacted `Session` in environments not managed by a Spring transaction manager. For standalone template operations, local commit/rollback may occur at the end of **a single call**. This **does not group multiple consecutive template calls into one business transaction**, unless a transaction manager coordinates the calls within the same scope.

| Case | Who manages commit/rollback? |
| --- | --- |
| Non-transacted template, AUTO_ACK | Provider + session acknowledge behavior |
| Template creates a transacted session for a single standalone operation | Template handles local transaction per operation |
| `@Transactional("jmsTransactionManager")` with matching resources | `JmsTransactionManager` manages the transaction boundary |
| JTA + properly configured XA providers/resources | JTA transaction manager coordinates XA resources |
| `@Transactional` using a DB transaction manager | **Does not automatically** make JMS operations XA/atomic with the DB |

A common production pattern to address the **dual-write problem** is the **transactional outbox**: write business data and an outbox record within the **same DB transaction**, then have a separate publisher send to JMS with retry/idempotency. You must design the consistency model, not just add an annotation.

### 9.4. Consumer ack/redelivery and business processing

Suppose a service calls `receiveAndConvert("q")`, then updates the DB, and the DB update fails. If the JMS receive was already acked/committed before the DB failed, the message may not return to the queue. When retry tied to business processing is needed, use a listener container with transacted sessions and a redelivery policy, or an appropriate transaction manager; also design **idempotency** because a failure between DB commit and JMS commit can produce duplicates.

Plain `JmsTemplate` does not replace consumer error-handling and transaction-control workflows.

## 10. QoS and default destination: what does JmsTemplate support?

Key settings for sending:

- `deliveryMode`: persistent/nonpersistent per JMS semantics.
- `priority`: message priority, typically in the 0–9 range.
- `timeToLive`: milliseconds before the message expires per the JMS provider mechanism.
- `deliveryDelay`: delays when the message becomes deliverable if supported by the provider/JMS version.
- `explicitQosEnabled`: whether the template uses its configured QoS values instead of always relying on provider defaults.

Boot example:

~~~properties
spring.jms.template.time-to-live=30s
spring.jms.template.priority=5
spring.jms.template.qos-enabled=true
~~~

In Boot 3.5, these properties are template configuration, not Java code. When configuring QoS via Boot, explicit QoS may also be enabled by the corresponding properties; `qos-enabled=true` makes the intent explicit.

**Do not equate message TTL with receive wait time.**

~~~text
time-to-live=30s    → message lifetime on the delivery/broker side
receive-timeout=5s  → thread calling receive waits at most 5 seconds
~~~

A message may not have expired its TTL yet, while `receive` still returns `null` because no message arrived within 5 seconds. Conversely, a message whose TTL has expired is not guaranteed to still be delivered by the broker even if the caller waits longer.

**Default destination** enables `convertAndSend(payload)` or `receive()` if the app has configured a default destination:

~~~properties
spring.jms.template.default-destination=demo.orders
~~~

However, services with multiple destinations should usually pass the destination name explicitly for easier review/audit. Setting a default destination does not physically create a queue/topic regardless of provider; provisioning still depends on the broker.

## 11. Complete example: Spring Boot 3.5.7 + Artemis

Goal: a Java 17+ application running two synchronous send/receive pairs, observing payloads, correlation IDs, and the difference between `convertAndSend` and `send(MessageCreator)`. This demo **has no listener** to prevent another consumer from “snatching” messages before `receive`.

Requirements: Java 17+, Maven 3.9+, Docker, localhost port 61616 available, and ability to download dependencies/images. Uses a standalone **Apache ActiveMQ Artemis** broker and the `jakarta.jms` namespace of Spring 6/Boot 3.5.

### 11.1. Start the local broker

~~~bash
docker run --rm -d --name jms-template-demo \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine
~~~

These are **sample credentials for local lab use only** and must not be used in production. If your Docker/OS version requires different broker configuration, follow the official Artemis documentation. Wait for the broker to be ready:

~~~bash
docker logs jms-template-demo
~~~

Do not expose this demo broker to the internet. Queue auto-creation depends on broker configuration; the default Artemis demo image usually enables auto-create. In real environments, provision queues/addresses and permissions in advance.

### 11.2. Directory structure

~~~text
jms-template-guide/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/jms/JmsTemplateApplication.java
        └── resources/application.properties
~~~

### 11.3. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jms-template-guide</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-artemis` brings in Spring JMS and the corresponding Artemis client/provider. With auto-configuration enabled, Boot creates `ConnectionFactory` and `JmsTemplate` for injection. Configuring the broker via `spring.artemis.*` applies only to the **Artemis provider**, not standard JMS across providers.

### 11.4. `src/main/resources/application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

# Synchronous receive waits at most 5 seconds in this lab.
spring.jms.template.receive-timeout=5s
~~~

This is a **lab configuration using dummy/local credentials**. In real environments, **do not commit real passwords**: use environment placeholders or a secret store; connect over TLS with least-privilege broker permissions. If the demo uses a different broker port, update `broker-url` accordingly.

### 11.5. `src/main/java/com/example/jms/JmsTemplateApplication.java`

~~~java
package com.example.jms;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsTemplateApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsTemplateApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JmsTemplate jmsTemplate) {
        return args -> {
            // 1. The converter automatically creates a TextMessage from String.
            jmsTemplate.convertAndSend(
                    "demo.template.orders",
                    "order-42"
            );

            Object payload = jmsTemplate.receiveAndConvert(
                    "demo.template.orders"
            );
            if (!(payload instanceof String text)) {
                throw new IllegalStateException(
                        "Expected String payload, got " + payload);
            }
            System.out.println("Received: " + text);

            // 2. MessageCreator manually creates the TextMessage and header.
            jmsTemplate.send("demo.template.audit", session -> {
                TextMessage message =
                        session.createTextMessage("audit-1");
                message.setJMSCorrelationID("demo-1");
                return message;
            });

            Message raw = jmsTemplate.receive("demo.template.audit");
            if (!(raw instanceof TextMessage auditMessage)) {
                throw new IllegalStateException(
                        "Expected TextMessage, got " + raw);
            }
            System.out.println(
                    "Audit: " + auditMessage.getText()
                    + ", correlation=" + auditMessage.getJMSCorrelationID()
            );
        };
    }
}
~~~

**What the source code does *not* have to do:**

1. Does not manually create `Connection`, `Session`, or `MessageProducer` for each send.
2. Does not manually create `MessageConsumer`/call `connection.start()` for each receive.
3. Does not manually close the template's JMS resources.
4. Does not catch `JMSException` just to close the session after an operation.
5. Does not create/share a `Session` across multiple threads.
6. Does not manage raw message conversion manually for the `String` payload in the first send/receive pair.

**What the source code *still must* do:**

1. Choose destinations, define payloads/schemas and business headers.
2. Configure receive timeout and handle `null` responses/type mismatches.
3. Configure the connection factory/broker and permissions.
4. Control transactions, retries, and idempotency according to system goals.
5. Decide how to handle errors/monitoring; `JmsTemplate` does not automatically write to a DB or auto-retry every business error.

### 11.6. Running the project and expected output

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

When the broker is ready, queues are available, the application is the sole consumer of both demo queues, and operations complete within 5 seconds, the two lines printed by the code are:

~~~text
Received: order-42
Audit: audit-1, correlation=demo-1
~~~

Spring Boot and Artemis also print startup/connection logs depending on the environment; those two lines are the business output, **not the entirety of stdout**.

After the demo:

~~~bash
docker stop jms-template-demo
~~~

**Note on determinism:** if another producer/consumer is using the demo queues, the received payload may differ. To keep the lab reproducible, use a dedicated broker/queues and do not reuse queues from previous tests. If the broker has not started or authentication fails, the application throws an exception instead of printing the two lines above; check container logs, URI, credentials, and access permissions.

### 11.7. What does this example *not* prove?

- Does not prove end-to-end exactly-once or atomicity between JMS and a database.
- Does not prove continuous message consumption; it only performs **two synchronous receives**.
- Does not prove that a production broker auto-creates queues; auto-create behavior depends on the provider.
- Does not configure TLS/secret stores; this is a local lab.
- Does not test failures/reconnects/duplicate messages; these must be designed and tested separately for production.

## 12. Request–reply: a built-in convenience, not guaranteed RPC

`JmsTemplate.sendAndReceive(destination, messageCreator)` provides a synchronous request–reply pattern. The template creates a **temporary queue** as the reply destination, sets it in the `JMSReplyTo` header of the request, sends it, and waits for a response from the temporary destination.

~~~java
// Illustrative snippet; another service must read "demo.rpc.requests",
// inspect JMSReplyTo, and send the response there.
Message reply = jmsTemplate.sendAndReceive(
    "demo.rpc.requests",
    session -> session.createTextMessage("ping")
);

if (reply == null) {
    System.out.println("Reply timeout");
}
~~~

If **there is no responder**, the call can time out and `reply == null`; the application does not automatically gain an RPC server simply by sending a request. The responder must read `request.getJMSReplyTo()` and send to that `Destination`; a correlation ID may be needed when sharing a reply queue or handling multiple concurrent requests.

A temporary destination lives for the lifetime of the connection and only the owning connection may create a consumer on it; the responder's connection can **send** to the reply destination. The template cleans up the temporary queue/resources for the call, but does not make messages durable after the requester disconnects. Timeouts and idempotency remain the system's responsibility.

If the RPC task is long-running, consider asynchronous replies/events, job status, or callbacks instead of holding many threads and sessions waiting.

## 13. Extensions: browsing, selectors, and multiple messages

### 13.1. JMS selector

~~~java
// Receives a message with property eventType = 'ORDER_CREATED' if available.
Message selected = jmsTemplate.receiveSelected(
    "orders.queue",
    "eventType = 'ORDER_CREATED'"
);
~~~

A selector is a filter expression on JMS **headers/properties**, not a JSON body parser. It has syntax and supported types defined by JMS; do not concatenate a selector String from unvalidated user input.

### 13.2. QueueBrowser

`JmsTemplate.browse(...)` lets you inspect an **approximate snapshot** of messages on a queue using `QueueBrowser` without consuming messages under browse semantics. However, concurrent changes on the broker mean the observed result **is not an immutable transactional snapshot**, and the browser is still a resource requiring cleanup. The template manages the browser within the callback scope:

~~~java
import jakarta.jms.Message;
import java.util.Enumeration;
import org.springframework.jms.core.BrowserCallback;

Integer visible = jmsTemplate.browse(
    "orders.queue",
    (BrowserCallback<Integer>) (session, browser) -> {
        Enumeration<?> items = browser.getEnumeration();
        int count = 0;
        while (items.hasMoreElements()) {
            Object item = items.nextElement();
            if (item instanceof Message) {
                count++;
            }
        }
        return count;
    }
);
~~~

This is a **code snippet**, not a runnable application. `visible` can change while producers/consumers operate concurrently; do not use a queue browser as an exact monitoring tool under load. For monitoring, use broker management APIs/metrics.

### 13.3. Batch sending/receiving

The template can perform multiple calls within a service, but:

- Each `convertAndSend` call has its own operation boundary unless grouped by an appropriate transaction/callback.
- An `execute` callback can share a session/producer; this does not turn it into a global transaction.
- Send order **does not always mean business processing order** when multiple consumers, redelivery, priorities, or topology reordering are involved.
- For high-volume sending, consider outbox/batching and limiting connection/session counts; do not cram millions of messages into a single long-running transaction.

## 14. Design choices in real-world scenarios

| Scenario | Appropriate design | What to control |
| --- | --- | --- |
| API publishing events quickly | `JmsTemplate.convertAndSend` + suitable connection factory | Send timeout, QoS, error handling, retry/idempotency |
| Must set headers/properties | `send(MessageCreator)` or post-processor | Schema, property types, correlation |
| Need a one-off message receive with timeout | `receive/receiveAndConvert` | Thread blocking, `null`, ack boundary |
| Service continuously processing a queue | `@JmsListener` / listener container | Concurrency, transaction, redelivery, DLQ |
| Simple request–reply needed | `sendAndReceive` | Responder, temporary queue, timeout/correlation |
| High load, very high request rate | `CachingConnectionFactory`/pool and tuning | Resource exhaustion, monitoring, session constraints |
| Sending JMS alongside database updates | Outbox or XA/JTA when genuinely supported | Dual-write, eventual consistency, idempotency |
| Need to convert DTOs to JSON | Custom `MessageConverter` | Schema versioning, content type, validation |
| Need multiple operations on the same session | `execute(SessionCallback/ProducerCallback)` | Do not retain resources outside callback; clear transaction scope |

## 15. Common mistakes and fixes

### Mistake 1. Treating the template as a broker or queue

`JmsTemplate` is only a client wrapper; if the broker is not running or credentials are wrong, `convertAndSend` still fails. **Fix:** configure `ConnectionFactory`/provider/broker and explicit health checks.

### Mistake 2. Manually closing the session/producer managed by the template

When a callback receives a session, the developer closes it manually or stores it in a static field for reuse. This breaks Spring/pool lifecycle management. **Fix:** operate synchronously only inside the callback; Spring cleans up resources it provides. Independently created resources must be managed manually.

### Mistake 3. Assuming every send closes the TCP connection

With connection factory caching/pooling, logical close returns the resource to the cache. **Fix:** monitor physical connection counts and cache config rather than inferring from `JmsTemplate` call counts.

### Mistake 4. Using a session across multiple threads

A singleton `JmsTemplate` is thread-safe once configured, but a JMS `Session` must not be shared concurrently across threads. **Fix:** inject the template, avoid storing a session in a singleton, and do not spawn async tasks that reuse a callback session.

### Mistake 5. Infinite receive wait

Setting `receiveTimeout=0` in high-load endpoints can hold threads indefinitely. **Fix:** use a positive timeout for synchronous calls; use a listener container for continuous consumption services.

### Mistake 6. Reading `receiveAndConvert` without null/type checks

Timeouts return `null`; the converter may return `String`, `byte[]`, `Map`, or an object depending on configuration. **Fix:** null-check, type-check, and schema validation.

### Mistake 7. Assuming the converter always uses JSON

`convertAndSend(dto)` does not mean automatic JSON serialization. **Fix:** configure an appropriate JSON `MessageConverter`; test raw message types/bodies.

### Mistake 8. Using `@Transactional` and assuming DB and JMS share one transaction

If the annotation is bound to a different transaction manager, the JMS resource might not participate. **Fix:** specify the manager and resource factory, or properly implement outbox/JTA.

### Mistake 9. Relying on a successful send to conclude business completion

A successful send does not confirm the consumer processed the message, committed to DB, or sent a response. **Fix:** use ack/response/job state/outbox appropriate to business semantics.

### Mistake 10. Blindly retrying on timeout or connection loss

The broker may have already received the message even though the client did not receive the result. **Fix:** idempotent handlers, unique event IDs, deduplication, and bounded retries with backoff.

### Mistake 11. Enabling consumer caching everywhere

Cached consumers can have long-lived effects on subscriptions/prefetch; listener containers manage their own consumers. **Fix:** configure caching per workload and provider, test under load, and monitor active consumers.

### Mistake 12. Ignoring TLS and broker permissions

Passwords in source code or plain TCP in production networks are security risks; the template does not replace auth/authorization. **Fix:** externalized secrets, TLS, least privilege, access auditing.

### Mistake 13. Confusing checked and unchecked exceptions

`JmsTemplate` typically throws unchecked Spring `JmsException`; `MessageCreator` can still declare `jakarta.jms.JMSException` inside the callback per its interface. **Fix:** distinguish JMS API inside callbacks from exception translation at the template boundary; log sanitized root causes.

### Mistake 14. Not setting TTL or DLQ policies

Stale messages can linger in queues, and processing errors can loop indefinitely. **Fix:** align on TTL, redelivery, dead-letter addresses, replay runbooks, and broker monitoring.

## 16. Checklist for code review/deployment

- [ ] `ConnectionFactory` comes from the right JMS provider with valid endpoint and credentials; queues/topics are created/authorized per policy.
- [ ] `JmsTemplate` is injected as a shared bean after configuration, without mutating settings per request concurrently.
- [ ] Use `convertAndSend` when the converter understands the payload; use `send(MessageCreator)` when raw JMS types/headers are needed.
- [ ] Do not create/close/retain template-managed `Connection`, `Session`, or `Producer` outside callbacks.
- [ ] Synchronous `receive` and asynchronous `@JmsListener` are properly distinguished.
- [ ] `receiveTimeout` is set for synchronous calls and `null` is handled.
- [ ] Schema/message converter and data validation are in place; never deserialize Java objects from untrusted sources.
- [ ] Ack/transaction manager matches the `ConnectionFactory`, and the JMS–DB boundary is clearly understood.
- [ ] Bounded retries, idempotency keys, poison message/DLQ handling, and timeout observability are implemented.
- [ ] Cache/pool is sized for concurrency without assuming physical close after every operation; connection/session/consumer metrics exist.
- [ ] QoS, TTL, priority, delivery mode, and selectors are verified against a real broker.
- [ ] Credentials come from environment/secret manager with no hardcoded production secrets; TLS and least privilege are enforced.
- [ ] Integration tests cover broker unavailable, unauthorized send, duplicates, timeouts, redelivery, and graceful shutdown.

## 17. Review questions

**Question 1. Can `JmsTemplate` replace `ConnectionFactory`?**  
No. The template **needs** `ConnectionFactory` to obtain JMS connections/sessions; it is not itself a broker/provider.

**Question 2. When using `JmsTemplate`, do you need `try-with-resources` to close `Session`?**  
Not for sessions created/supplied by the template to callbacks. The template/transaction infrastructure manages lifecycle; only clean up resources you created independently.

**Question 3. Why can the template be used as a singleton?**  
It is thread-safe **once configured**, because each operation obtains appropriate resources via the factory/transaction. That does not make sharing a single JMS `Session` across threads safe.

**Question 4. How does `convertAndSend("q", "hi")` differ from `send("q", callback)`?**  
The first uses a converter to create a JMS message from a Java object. The second lets the developer create and customize the message using a `Session` supplied by the template.

**Question 5. How does `receive` differ from `@JmsListener`?**  
`receive` is a synchronous call that can block the caller's thread; `@JmsListener` uses a container to create consumers and invoke handlers asynchronously.

**Question 6. Does `receiveAndConvert` always return a String?**  
No. It depends on the message type/converter; it can also return `null` when no message is received within the timeout.

**Question 7. Does caching/pooling make messaging exactly-once?**  
No. Caching optimizes resources; delivery/processing guarantees require transaction design, ack, retries, deduplication, and idempotency.

**Question 8. Is a service that both writes to a DB and sends JMS under `@Transactional` atomic?**  
Not by default. You must check the transaction manager; usually an outbox or proper JTA/XA infrastructure is used if distributed atomicity is truly required.

**Question 9. Does `sendAndReceive` automatically write a responder?**  
No. It creates a temporary reply queue and waits; another service must read the request and send the reply.

**Question 10. What happens when a callback throws `JMSException`?**  
The template translates the JMS error into an appropriate unchecked `JmsException` for the caller to handle; the session/producer is cleaned up per lifecycle even on error. If inside a transaction, rollback/commit follows the transaction manager.

## 18. Official references

1. [Spring Framework 6.2 — Using Spring JMS: JmsTemplate, callbacks, resource caching, and transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
2. [Spring Framework — JMS overview: core abstractions, converters, exceptions, and listeners](https://docs.spring.io/spring-framework/reference/6.2/integration/jms.html)
3. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html)
4. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
5. [Spring Framework Javadoc — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
6. [Spring Framework — Message listener endpoints and `@JmsListener`](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
7. [Spring Boot 3.5 — JMS with Apache ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
8. [Spring Boot 3.5 — Common Application Properties: `spring.jms.*`](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
9. [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
10. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)
