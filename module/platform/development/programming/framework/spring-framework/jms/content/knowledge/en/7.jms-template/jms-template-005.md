# JmsTemplate: receive vs. receiveAndConvert

## Learning Objectives

In Spring Framework JMS, the two methods **`JmsTemplate.receive(...)`** and **`JmsTemplate.receiveAndConvert(...)`** are both used to **synchronously receive a message** from a JMS destination. They share the same waiting mechanism, yet differ in **the abstraction level of the returned data**: one returns the JMS message object (preserving headers, properties, and body type), while the other converts the body via `MessageConverter` into a Java object.

This lesson helps you master:

1. Exactly what type each method returns, when it returns `null`, and the destination overloads.
2. When you need to work with `TextMessage`, `BytesMessage`, `MapMessage`, JMS headers/properties, or only need a payload such as `String`/DTO.
3. The impact of `SimpleMessageConverter`, custom JSON converters, type-casting errors, and versioning/schemas.
4. **Blocking** behavior and `receiveTimeout`; why the default can wait indefinitely and is unsuitable for many HTTP requests.
5. The critical point of **acknowledgement and transactions**: completing a receive does not mean business processing succeeded. With synchronous receives self-managed by `JmsTemplate`, the message may already be acked/committed before subsequent code executes.
6. How to practice with Java 17+ using Spring Boot and ActiveMQ Artemis, test selectors, and choose `@JmsListener` for continuous processing.

**Scope:** Spring Framework 6.x, Spring Boot 3.x, Jakarta Messaging (`jakarta.jms` package). Spring 5.x uses the `javax.jms` namespace and some different auto-configuration conventions; do not mix both API generations in one project.

## 1. Quick comparison table

| Criterion | `receive(...)` | `receiveAndConvert(...)` |
| --- | --- | --- |
| Meaning | Receives a raw JMS message | Receives a JMS message and converts its data into a Java object |
| Declared return type | `jakarta.jms.Message`, nullable | `java.lang.Object`, nullable |
| Returned contents | Body type, JMS headers, message properties | Value produced by `MessageConverter.fromMessage(...)` |
| Automatically uses `MessageConverter`? | **No** | **Yes**, after receiving |
| On `TextMessage` with default converter | Remains `TextMessage` | Typically `String` |
| On `BytesMessage` with default converter | Remains `BytesMessage` | Typically `byte[]` |
| On `MapMessage` with default converter | Remains `MapMessage` | Typically `Map` |
| On `ObjectMessage` with default converter | Remains `ObjectMessage` | Typically deserialized Java object |
| Reading `JMSMessageID`, correlation ID, properties | Directly from `Message` | `Message` is no longer in the result; requires another convention if metadata is needed |
| Destination selection | Default, `String`, or `Destination` | Same |
| Filtering via JMS selector | `receiveSelected(...)` | `receiveSelectedAndConvert(...)` |
| Waiting for a message | Synchronous, can block | Synchronous, **also blocks** |
| On timeout with no message | `null` | `null` |
| Typical errors | JMS connection/receive/ack, reading body with wrong type | Those errors **plus** converter/schema/type errors |
| Appropriate usage | Need headers/properties or manual parsing control | Only need the payload per a mutually agreed converter |

**Formula to remember:**

~~~text
receive(destination)
    => jakarta.jms.Message (or null)
    => MANUALLY read headers, properties, body

receiveAndConvert(destination)
    => receive(destination)
    => messageConverter.fromMessage(message)
    => Java Object (or null)
~~~

Both **consume** the message from the destination. `receiveAndConvert` is not a “peek” or “read without removing” operation. Do not call the two methods back-to-back on **the same message** to compare: the first call may have already consumed it.

## 2. Methods used in practice

Representative signatures in `org.springframework.jms.core.JmsTemplate`:

~~~java
// Receive a JMS Message directly:
Message receive();
Message receive(String destinationName);
Message receive(Destination destination);

// Receive a Java payload via MessageConverter:
Object receiveAndConvert();
Object receiveAndConvert(String destinationName);
Object receiveAndConvert(Destination destination);

// Receive with a JMS selector:
Message receiveSelected(String destinationName, String messageSelector);
Object receiveSelectedAndConvert(String destinationName, String messageSelector);
~~~

These are **illustrative signatures** (not methods you need to define yourself). Actual APIs have additional overloads with default destinations or `Destination` objects; results are potentially nullable.

- Argumentless `receive()` and `receiveAndConvert()` only work when `JmsTemplate` already has a default destination configured (`defaultDestination` or `defaultDestinationName`).
- `receive("payments.in")` uses a string destination name; the template's `DestinationResolver` determines whether it is a queue/topic per configuration, such as `pubSubDomain=false` for queues.
- `receive(queueObject)` accepts a `jakarta.jms.Destination` supplied by infrastructure; avoids ambiguity when a system uses both queues and topics.
- `receiveSelected("payments.in", "kind = 'refund'")` filters on **queryable JMS message properties/headers**, not directly querying JSON fields inside the body.
- `receiveAndConvert` in `JmsTemplate` **does not** have an overload taking `Class<T>` and returning generic `T`. That convenience exists on **`JmsMessagingTemplate`** (the Spring Messaging abstraction) or other APIs. With `JmsTemplate`, check `instanceof` before casting.

Example of a purposeful call:

~~~java
// Code snippet in a Spring bean with JmsTemplate injected.
Object payload = jmsTemplate.receiveAndConvert("orders.in");
if (payload instanceof String orderId) {
    processOrder(orderId);
} else if (payload == null) {
    // No message before timeout; some custom converters may also return null.
} else {
    throw new IllegalArgumentException(
            "Expected String but got " + payload.getClass().getName());
}
~~~

`processOrder` is your business method; this is an **illustrative snippet**, not a standalone application. Note: if business logic `processOrder` throws an exception **after** `receiveAndConvert` has returned, message rollback **does not happen automatically**.

## 3. receive(): retaining the JMS Message and metadata

`jakarta.jms.Message` is the root interface for JMS messages. It carries headers and properties alongside the body. `receive()` lets you inspect them before deciding how to process.

~~~java
// Code snippet placed in a service that already has JmsTemplate.
Message message = jmsTemplate.receive("billing.in");
if (message == null) {
    return;
}

String messageId = message.getJMSMessageID();
String correlationId = message.getJMSCorrelationID();
boolean redelivered = message.getJMSRedelivered();
String kind = message.getStringProperty("kind");

if (message instanceof TextMessage textMessage) {
    String body = textMessage.getText();
    // Decode JSON, validate schema, execute business logic...
} else if (message instanceof BytesMessage bytesMessage) {
    // Read bytes per agreed codec/schema.
} else {
    // Handle unexpected format explicitly.
}
~~~

Requires imports for `jakarta.jms.Message`, `TextMessage`, and `BytesMessage`; the enclosing method must handle `JMSException` or declare an appropriate `throws`. This snippet is intentionally a code fragment.

Meaningful metadata fields:

| Component | When to use | Notes |
| --- | --- | --- |
| `JMSMessageID` | Message tracking and logging | Provider-assigned ID; does not automatically replace a business idempotency key |
| `JMSCorrelationID` | Request–reply correlation / logical tracing | Set by application convention or producer |
| `JMSType` | Convey message type info if used by the project | Not automatically validated by a schema registry |
| `JMSRedelivered` | Detect whether the message was previously delivered | Does not replace idempotency mechanisms |
| `JMSDestination` | Inspect the receiving destination | Can be a queue/topic object depending on provider |
| `JMSTimestamp` | Timestamp assigned by producer/provider | Does not equate to the business occurrence timestamp |
| `message.getStringProperty("kind")` | Routing, filtering, observability | A **JMS property**, not a JSON field inside the body |
| `JMSXDeliveryCount` | Delivery attempt count if the broker supports this optional standard property | Not every application/provider exposes it identically |

**Why does metadata matter?** Suppose a consumer needs to verify a response's `JMSCorrelationID`, check `kind` before parsing the body, and include `JMSMessageID` in logs. `receive()` fits because it returns the JMS object itself. When using `receiveAndConvert`, metadata **is not included in the default Java `String`**; you need an envelope/convention or a custom converter that preserves metadata if truly required.

### 3.1. Reading the body “manually” does not turn receive() into receiveAndConvert()

With `TextMessage`:

~~~java
Message raw = jmsTemplate.receive("queue.one");

if (raw instanceof TextMessage text) {
    String json = text.getText();
    // json is text, not a DTO yet.
}
~~~

`getText()` does not parse JSON, validate schemas, or automatically construct DTOs. If you want a typed DTO, use an explicit JSON mapper or configure a `MessageConverter` with `receiveAndConvert`.

With `ObjectMessage`, calling `getObject()` can trigger **Java native deserialization**, which couples to Java classes and carries security risks. Do not use `ObjectMessage` as the default for all events across service boundaries simply because returning a Java object seems convenient.

### 3.2. Do not hold onto Message and try to acknowledge later

`receive()` through `JmsTemplate` does not grant you ownership of the underlying `Session`/`Connection`. `JmsTemplate` has already coordinated acknowledgement/transaction and cleanup per configuration before the method returns. Do not write logic like “after the HTTP API call succeeds, I will call `message.acknowledge()`” assuming acknowledgement will control a session that the template has already closed or returned to the cache. To bind business processing and ack into a single transaction, see the transactions section.

## 4. receiveAndConvert(): receive and convert into a Java payload

`JmsTemplate` uses an `org.springframework.jms.support.converter.MessageConverter`; the core interface has two directions:

~~~java
// Interface shape (abbreviated; illustrative, not a standalone compilable file):
Message toMessage(Object object, Session session) throws JMSException;
Object fromMessage(Message message) throws JMSException;
~~~

`convertAndSend` uses `toMessage`; `receiveAndConvert` uses `fromMessage`. **Both ends need the same encoding/schema contract**, not just the same queue name.

The default converter is typically `SimpleMessageConverter`. For incoming messages:

| JMS message type | Typical Java result under SimpleMessageConverter | Notes |
| --- | --- | --- |
| `TextMessage` | `String` | `getText()` may be `null`; JSON remains a string |
| `BytesMessage` | `byte[]` | Does not automatically decode Protobuf/Avro/ZIP |
| `MapMessage` | `Map<String,Object>` | Value types are constrained by JMS MapMessage |
| `ObjectMessage` | `Serializable` Java object | Can deserialize Java binaries; class must be compatible and allowed |
| Unsupported message type | May return the raw `Message` or throw an error depending on converter/version | Check the exact implementation/version; do not cast blindly |

Do not infer the Java type from the destination name. `receiveAndConvert("orders.json")` does not automatically understand JSON; if the message is a `TextMessage` containing JSON, the default converter returns a **JSON `String`**, not an `OrderDto`.

Example:

~~~java
Object data = jmsTemplate.receiveAndConvert("orders.json");

if (!(data instanceof String json)) {
    throw new IllegalStateException("Expected JSON text payload");
}

// Example with an ObjectMapper configured in the application:
OrderEvent event = objectMapper.readValue(json, OrderEvent.class);
validate(event);
~~~

This is a **code snippet** requiring `objectMapper`, `OrderEvent`, `validate`, and exception handling; it illustrates two separate phases: `MessageConverter` reading the message as a `String`, and the JSON mapper binding the string to a DTO.

### 4.1. Custom converters change both sending and receiving sides

When configuring `MappingJackson2MessageConverter` (Spring Framework 6.x/Jackson 2) to serialize/deserialize JSON:

- Messages can be `TextMessage` or `BytesMessage` depending on `targetType`; configure explicitly.
- A type ID property helps the converter select the DTO; use stable mapping aliases rather than arbitrarily exposing Java class names.
- Type mappings must be configured consistently across producer/consumer; never enable broad polymorphic deserialization on untrusted data.
- A `MessageConverter` bean in Spring Boot may be auto-wired into `JmsTemplate`; however, if you create custom templates/factories yourself, ensure they use the intended converter.
- A converter does not automatically solve schema versioning, backwards compatibility, redelivery, idempotency, or transactions.

Configuration snippet compatible with Spring Framework 6.x:

~~~java
@Bean
MappingJackson2MessageConverter invoiceJsonConverter() {
    var converter = new MappingJackson2MessageConverter();
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(Map.of(
            "invoice-v1", InvoiceEvent.class));
    return converter;
}
~~~

This snippet requires imports for `org.springframework.context.annotation.Bean`, `java.util.Map`, `org.springframework.jms.support.converter.MappingJackson2MessageConverter`, `MessageType`, and an `InvoiceEvent` DTO definition. It is not a standalone runnable class. When upgrading to another Spring Framework version with Jackson converter changes, verify against the actual version before copying.

### 4.2. Check types instead of casting directly

Wrong:

~~~java
OrderEvent event = (OrderEvent)
        jmsTemplate.receiveAndConvert("orders.in");
~~~

If the default converter returns a `String`, the code throws `ClassCastException`. Crucially, the message may **already have been consumed and acked** before the cast error occurs.

Better approach:

~~~java
Object result = jmsTemplate.receiveAndConvert("orders.in");

if (result == null) {
    return;
}
if (result instanceof OrderEvent event) {
    handle(event);
} else {
    throw new IllegalStateException(
            "Unexpected payload: " + result.getClass().getName());
}
~~~

These are **code snippets** assuming `OrderEvent` and `handle` exist. They catch type-contract mismatches, **without** automatically triggering redelivery if the receive already committed.

## 5. Timeout: both receive synchronously and can block

Despite having `Convert` in its name, `receiveAndConvert` is **not** an asynchronous API. Both perform `receive` via `MessageConsumer` and wait for a message on the **calling thread**.

`JmsTemplate.setReceiveTimeout(long)` values in Spring Framework:

| Value | Practical meaning |
| --- | --- |
| Default: `RECEIVE_TIMEOUT_INDEFINITE_WAIT` (value `0`) | Waits until a message arrives or an error/disconnect occurs; can **block indefinitely** |
| `setReceiveTimeout(2000)` | Waits at most ~2,000 ms for one receive; returns `null` if no message arrives |
| `RECEIVE_TIMEOUT_NO_WAIT` or negative number (e.g., `-1`) | Checks immediately using `receiveNoWait()` semantics without actively waiting |
| Small positive value | Bounded short poll, though still blocking for that duration |

~~~java
// Configure an injected JmsTemplate during app startup/configuration:
jmsTemplate.setReceiveTimeout(2_000L);

// Each receive/receiveAndConvert call can wait up to ~2 seconds:
Message raw = jmsTemplate.receive("reports.in");
Object converted = jmsTemplate.receiveAndConvert("reports.in");
~~~

**Do not use this snippet verbatim to compare the same message**, because two calls on the same queue consume two different messages if present. To compare results, send two equivalent messages to two separate queues, as in the lab in section 8.

Notes:
- `null` from `receive()` usually indicates no message was received within the wait window; it does not assert the broker will never have messages.
- `null` from `receiveAndConvert()` can mean no message arrived; with a converter that can return `null` for a valid body (e.g., a null text body), **you cannot distinguish the two by `null` alone**. Contracts should avoid sending “null” payloads or use raw `Message`/envelopes.
- The message receive deadline is not automatically the deadline for the **entire business flow**: after receiving, HTTP APIs, DBs, or converters may continue taking time.
- Brokers have selectors, expiry/TTL, delayed delivery, competing consumers, receive permissions, etc., so “the queue has a message” does not guarantee your call gets that exact message immediately.
- Using no-wait in a tight loop without sleep/backoff can cause **busy polling** and overload broker/CPU. Use `@JmsListener` when continuous processing is needed.
- Never let an HTTP request call `receiveAndConvert()` unboundedly on a request-handling thread. If using a request-reply pattern, use explicit timeouts and correlation IDs, or an async architecture.

### 5.1. Per-template configuration, not per-call by default

`setReceiveTimeout` is a **template** setting, not a `receiveAndConvert("q", timeout)` parameter on `JmsTemplate`. In a multi-threaded application, do not mutate the timeout of a shared template between requests, as this causes races and unpredictable behavior. You can define **two template beans** sharing a `ConnectionFactory` with different timeouts, or choose a uniform value.

Example of separate configuration (`@Configuration` snippet):

~~~java
@Bean("shortPollJmsTemplate")
JmsTemplate shortPollJmsTemplate(ConnectionFactory cf) {
    JmsTemplate template = new JmsTemplate(cf);
    template.setReceiveTimeout(250L);
    return template;
}
~~~

In Spring Boot, if you create a custom `JmsTemplate` replacing the default bean, pay attention to the converter, destination resolver, and transaction/pooling settings the application relies on. In Spring Boot, use version-appropriate configuration/configurer mechanisms when you need to preserve full auto-configuration.

## 6. Exact position of the converter relative to acknowledgement/commit

This is decisive for correctness and is frequently overlooked.

### 6.1. Execution path of JmsTemplate

Conceptually, in Spring Framework 6.x:

~~~text
receiveAndConvert("orders.in")
    |
    +-- receive("orders.in")
    |     |
    |     +-- obtain Connection/Session
    |     +-- create MessageConsumer
    |     +-- receive Message (blocking / timeout)
    |     +-- perform ACK or JMS local COMMIT if template owns the session
    |     +-- close/return consumer and resources per policy
    |
    +-- if Message != null:
    |     messageConverter.fromMessage(message)
    |
    +-- return payload Object (or null)
~~~

The **`receive()` path manages resources and acknowledgement itself**. When calling `receiveAndConvert()`, Spring first executes `receive()` and only then converts the message. If the session is a **local JMS transaction created by the template itself**, commit occurs inside `receive`—that is, **before** the converter. When using template-managed `CLIENT_ACKNOWLEDGE`, acknowledgement may likewise happen inside `receive` before returning.

Therefore:
- `MessageConverter.fromMessage(...)` throwing an exception **does not guarantee** the just-received message will be redelivered under a local template-controlled receive.
- `handleBusiness(...)` throwing an exception after `receiveAndConvert(...)` returns also **does not automatically roll back** the received message.
- Plain `receive()` also **does not let you** arbitrarily hold the session open and ack after finishing database work, because the template controls session lifecycle.
- Simply setting `jmsTemplate.setSessionTransacted(true)` **does not** make code after the receive call part of a long transaction spanning business logic. It may only make the **receive operation itself** transacted.

This is a key behavior of Spring `JmsTemplate`, not a claim that all JMS consumers in all frameworks always ack before the handler.

### 6.2. Externally scoped transaction

If receiving/converting/processing must belong to **a single JMS transaction**, consider a Spring-managed transaction boundary:

~~~java
@Service
public class TransactionalPullWorker {

    private final JmsTemplate jmsTemplate;

    public TransactionalPullWorker(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void pollOne() {
        Object payload = jmsTemplate.receiveAndConvert("jobs.in");
        if (payload == null) {
            return;
        }
        if (!(payload instanceof String jobId)) {
            throw new IllegalArgumentException("Unexpected message type");
        }
        performIdempotentWork(jobId); // Business method you implement.
    }

    private void performIdempotentWork(String jobId) {
        // Execute appropriate logic; throw an exception if incomplete.
    }
}
~~~

This is a **Spring class pattern** requiring imports for `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, `JmsTemplate`, and a `JmsTransactionManager` bean named `jmsTransactionManager` using the **same compatible `ConnectionFactory`**. `@Transactional` must be invoked through the Spring proxy; calling `this.pollOne()` directly can bypass transaction advice.

When the JMS session is bound to an external transaction:
- JMS commit/rollback occurs at the end of the transaction instead of being committed immediately by the template inside `receive`.
- If the converter or business logic throws an unchecked exception causing the transaction to roll back, the broker can redeliver the message per policy.
- **`JmsTransactionManager` does not automatically include database transactions**. If `performIdempotentWork` writes to a DB, you need outbox/inbox/idempotency or verified coordinated transaction infrastructure. Do not infer exactly-once from annotations alone.
- If business work is long-running, holding a JMS transaction open incurs cost and risk on broker/network failure; consider listener containers and alternative architectures.

### 6.3. Why `@JmsListener` is usually a better fit

For continuous consumers:
- `DefaultMessageListenerContainer` or an equivalently configured container can manage lifecycle and a JMS transaction across **one listener invocation**.
- When a listener throws an exception and the session is configured with `sessionTransacted=true`, the transaction can roll back and lead to redelivery depending on the broker.
- Concurrency, retry/DLQ, metrics, and graceful shutdown are much cleaner than putting `receiveAndConvert` inside a `while(true)` loop.
- Consumers still need idempotency: a handler might finish updating the database and crash right before the JMS commit.

**Transaction section conclusion:** Choosing between `receive` and `receiveAndConvert` is not an ACK control switch. The distinction axis is **raw vs. converted payload**; the reliability axis lies in transactions/acknowledgement/lifecycle.

## 7. When to choose which method?

### Case A — Receiving a simple text command

A batch tool simply needs to pull the string `"rebuild-index"` from a dedicated queue, accepting a wait of up to 2 seconds. The contract guarantees the body is a `TextMessage` and no JMS metadata is needed.

**Prefer `receiveAndConvert`** with the default converter, verify the result is a `String`, and execute business logic within appropriate transaction/reliability boundaries.

### Case B — Need tracing/correlation, header inspection, routing

The service needs `JMSCorrelationID` to match replies, `JMSRedelivered` for logging, and a `tenant` property to validate context.

**Prefer `receive`** because it returns the `Message`. Inspect the body type, properties, and headers without depending on a converter that might change in auto-configuration.

### Case C — Multi-version JSON schemas

The producer sends JSON text with `schemaVersion`, `eventId`, and `type`; the consumer uses Jackson to parse a version-specific DTO.

**Both approaches are reasonable:**
- `receive()` → inspect headers/properties → read `TextMessage.getText()` → parse manually with Jackson.
- `receiveAndConvert()` → use a JSON `MessageConverter` with proper type mappings/version validation → receive the agreed DTO or object.

Do not assume `SimpleMessageConverter` parses JSON automatically.

### Case D — Pulling a message to perform critical business side effects

Involving payments, emails, bookings, or database updates. Calling `receiveAndConvert()` and then running external business logic without a transaction boundary can ack the message before a business failure occurs.

**Neither method solves this on its own.** Choose a listener container with transacted sessions, or wrap synchronous polling in a proper external JMS transaction. Design idempotent handlers and retry/DLQ.

### Case E — Service needing 24/7 consumption

An always-on consumer scaling across multiple instances and requiring backpressure/monitoring.

**Prefer `@JmsListener`** and configure the listener container; avoid polling loops using `receive`/`receiveAndConvert`. Synchronous receive fits admin tools, scheduled/paced batch polls, tests, or business cases that must actively pull one message.

## 8. Runnable lab: two queues to compare results

To see the same content produce two different result types, **do not** call `receive` and `receiveAndConvert` sequentially on **one queue holding a single message**. The lab creates **two queues**, each holding a copy of the String payload.

Explicit stack: Java 17+, Spring Boot **3.5.x** (Spring Framework 6.x), Maven, and embedded ActiveMQ Artemis. The embedded broker is for local experimentation only, not for testing production HA/persistence.

### 8.1. Maven dependencies

Generate a project via https://start.spring.io/ with:
- Project: **Maven**, Java.
- Java **17** or newer supported by Boot 3.5.
- Spring Boot **3.5.x**.
- Group `com.example`, artifact `receive-demo`, package `com.example.receivedemo`.
- Dependency: **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).

Add the embedded broker to `pom.xml` with the standard Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Boot manages compatible versions when the project uses the standard parent/BOM. In a project without the embedded broker dependency, `spring.artemis.mode=embedded` will not work as expected.

### 8.2. application.properties

Create `src/main/resources/application.properties`:

~~~properties
spring.application.name=receive-demo
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.raw,demo.converted
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

- `demo.raw` and `demo.converted` are **two independent queues**, not two consumers on the same message.
- `spring.jms.pub-sub-domain=false` selects queues when the template resolves destination names.
- Embedded persistence is disabled since this is only a lab; restarts are not used to prove durable backlogs.

### 8.3. Complete Java code

Save `src/main/java/com/example/receivedemo/ReceiveDemoApplication.java`:

~~~java
package com.example.receivedemo;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ReceiveDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReceiveDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner compareReceiveApis(JmsTemplate template) {
        return args -> {
            // Set a wait limit to prevent the lab from hanging on broker misconfiguration.
            template.setReceiveTimeout(2_000L);

            // Two messages with nearly identical content on two queues.
            template.send("demo.raw", session -> {
                TextMessage message =
                        session.createTextMessage("invoice-17");
                message.setStringProperty("eventType", "InvoiceReady");
                return message;
            });
            template.convertAndSend("demo.converted", "invoice-18");

            // Option 1: API returns a JMS Message.
            Message raw = template.receive("demo.raw");
            if (!(raw instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "Expected raw TextMessage but got " + raw);
            }

            System.out.println("RAW type=TextMessage");
            System.out.println("RAW body=" + text.getText());
            System.out.println("RAW eventType="
                    + text.getStringProperty("eventType"));

            // Option 2: default converter returns a String.
            Object converted =
                    template.receiveAndConvert("demo.converted");
            if (!(converted instanceof String body)) {
                throw new IllegalStateException(
                        "Expected converted String but got " + converted);
            }

            System.out.println("CONVERTED type=String");
            System.out.println("CONVERTED body=" + body);

            // Queue is now empty -> waits up to 2 seconds, then returns null.
            Object empty =
                    template.receiveAndConvert("demo.converted");
            System.out.println(
                    "EMPTY result=" + (empty == null ? "null" : empty));
        };
    }
}
~~~

The code uses only Java 17, Spring Boot 3.5, and Jakarta Messaging provided by the starter. `@EnableJms` is not needed since no `@JmsListener` is created in the lab; `JmsTemplate` is auto-configured by Boot given the right classpath.

Run from the project directory:

~~~bash
./mvnw spring-boot:run
~~~

On PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

With two fresh empty queues, no competing consumers, and the default `SimpleMessageConverter`, the **business** lines will be as follows (interleaved with Spring/Artemis logs):

~~~text
RAW type=TextMessage
RAW body=invoice-17
RAW eventType=InvoiceReady
CONVERTED type=String
CONVERTED body=invoice-18
EMPTY result=null
~~~

These lines are printed in the exact order of `ApplicationRunner`. The empty receive waits about 2 seconds; actual total elapsed time may vary due to startup and scheduling. If re-running against an external/persistent broker with a backlog or other consumers, results must be interpreted based on queue state rather than treating the sample output as an environment-independent guarantee.

**Step-by-step explanation:**

1. `send("demo.raw", ...)` manually creates a `TextMessage` with body `invoice-17` and JMS property `eventType`.
2. `convertAndSend("demo.converted", "invoice-18")` uses the default converter to create another `TextMessage`.
3. `receive("demo.raw")` returns the `TextMessage` object, allowing reading properties and `getText()`.
4. `receiveAndConvert("demo.converted")` reads the message and uses `SimpleMessageConverter` to return a `String`.
5. The next `receiveAndConvert` finds no message in the queue, waits until timeout, and returns `null`.

**What this lab does NOT prove:** rollback on business logic failure, exactly-once processing, durability across restarts, or conversion behavior with a custom JSON converter. Those are separate configuration properties and test cases.

### 8.4. Modifying the lab to observe a type mismatch

Change the producer for `demo.converted` to:

~~~java
// Replacement snippet for the convertAndSend(String) line
template.convertAndSend("demo.converted", new byte[] {65, 66});
~~~

With `SimpleMessageConverter`, the result from `receiveAndConvert("demo.converted")` is now typically `byte[]` instead of `String`. The `instanceof String` check will fail; that is why **type checking before casting** is critical. Switching to `receive("demo.converted")` shows the raw type is `BytesMessage`.

This experiment also demonstrates that a cast error in code after receiving does not automatically undo consumption of the message.

## 9. JMS message selectors: receiveSelected and receiveSelectedAndConvert

If you only want to consume a subset of messages in a queue, use a selector with valid JMS syntax. Selectors typically match **JMS message properties**, not by parsing JSON.

Producer example:

~~~java
// Code snippet in an app with JmsTemplate.
jmsTemplate.send("jobs.in", session -> {
    TextMessage message = session.createTextMessage("job-101");
    message.setStringProperty("kind", "render");
    message.setIntProperty("priorityGroup", 2);
    return message;
});
~~~

Raw receive:

~~~java
Message message = jmsTemplate.receiveSelected(
        "jobs.in", "kind = 'render' AND priorityGroup >= 2");

if (message instanceof TextMessage txt) {
    System.out.println(txt.getText());
}
~~~

Converted receive (on **another qualifying message**):

~~~java
Object payload = jmsTemplate.receiveSelectedAndConvert(
        "jobs.in", "kind = 'render' AND priorityGroup >= 2");
~~~

Notes:
- You need **two matching messages** for both examples to receive content; the first example already consumed the first message.
- A JMS selector is an expression evaluated by the broker/client per provider rules to match qualifying messages, not a SQL database query. Missing properties or mismatched data types can prevent a message from matching.
- `JMSType` and selector-supported headers follow specific rules; do not assume every JMS header is queryable in a selector.
- `receiveSelectedAndConvert` still obeys the same converter, timeout, and transaction semantics as `receiveAndConvert`.
- Selectors do not replace broker authorization; a consumer permitted to read a queue can supply a different selector unless restricted.

## 10. Conversion exceptions and retries: where did the error occur?

Separate the phases to diagnose:

~~~text
[Broker has message]
       |
[Receive via Session/MessageConsumer] ---- network/JMSException
       |
[JmsTemplate handles local ACK/COMMIT if it owns Session]
       |
[Return Message from receive()] -----> caller reads body/headers manually
       |
[Converter.fromMessage] -------------- conversion/schema/deserialization error
       |
[Return Object from receiveAndConvert()]
       |
[Business logic] --------------------- DB/API/validation failure
~~~

Error examples:

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| `receive` returns `null` | Timeout, empty queue, selector mismatch | Distinguish no messages from broken broker; check metrics |
| `receiveAndConvert` returns `String` instead of DTO | Default converter read a TextMessage | Configure a JSON converter or parse the string |
| `ClassCastException` after receive | Caller cast Java result to wrong type | Use `instanceof`, fix contract, avoid blind casts |
| `MessageConversionException` | Converter cannot handle message type/schema | Check converter bean, JMS type, type ID, schema |
| `JMSException`/Spring `JmsException` | Broker, session, permissions, protocol timeout, etc. | Log root cause and broker status |
| `ClassNotFoundException`/`InvalidClassException` | Incompatible Java serialization in ObjectMessage | Do not use native serialized objects as cross-service contracts |
| Another consumer “stole” the message first | Competing consumers on the queue | Clarify queue ownership and consumer groups |
| No messages seen in Topic when polling | Non-durable subscription did not exist at publish time | Clarify domain/subscription/durability |
| JSON parsing error after raw receive | JSON does not match schema | Separate transport errors from validation errors; use quarantine/DLQ if needed |
| Sent message then receive waits forever | Wrong queue/topic, name, timeout, broker, or session/selector | Verify exact destination, receive with finite timeout, check broker |

**Handling poison messages:** Do not repeatedly pull a malformed message in an unbounded loop. Design retries with backoff/max attempts, DLQ/quarantine, and alerts. When using `receiveAndConvert` outside an external transaction, conversion failures can happen **after local commit**, so do not rely on the broker automatically putting the failed message back on the queue.

## 11. Testing and contract strategy

### 11.1. Minimum test cases

| Test | Expectation |
| --- | --- |
| `TextMessage("ok")` + `receive` | Raw object is `TextMessage`, `getText()` yields `ok` |
| `TextMessage("ok")` + `receiveAndConvert` | Default converter returns `String "ok"` |
| `BytesMessage` + `receiveAndConvert` | Typically returns `byte[]` with `SimpleMessageConverter` |
| Empty queue + 500 ms timeout | Both methods return `null` instead of blocking forever |
| Empty queue + default timeout | Call can wait indefinitely; do not run unbounded tests directly |
| Two consumers competing on same queue | One message is received by one consumer, not duplicated to both |
| JSON TextMessage + default converter | Java result is a JSON string, not a DTO |
| JSON TextMessage + properly wired JSON converter | Can produce DTO per type/schema configuration |
| Headers/properties attached | `receive` reads them; plain `receiveAndConvert` only returns the payload |
| Receive + business failure after return | Does not automatically roll back local JMS commit |
| External JMS transaction + handler failure | Verify rollback/redelivery against a real broker and policy |
| Matching and non-matching selector | Only messages with matching properties are received |
| Producer sends unexpected type | Must report type-contract error and preserve observability |
| Message with `JMSRedelivered=true` | Can be logged/flagged, while still using business ID for deduplication |

### 11.2. Why mock-only tests are not enough

Unit-testing a custom `MessageConverter` is very useful: it checks whether `fromMessage` produces the expected DTO. However, mocks do not prove timeouts, broker acks, transaction boundaries, consumer concurrency, or DLQs. You need integration tests against a broker configured close to production (standalone or containerized Artemis) for transport behaviors.

A worthwhile reliability test:

1. Send a message with a fixed `businessId` to a test queue.
2. Receive inside an **external JMS transaction**.
3. Inside the converter/handler, intentionally throw an unhandled error.
4. Verify the transaction rolls back and the message can be redelivered per broker policy.
5. Then process successfully with idempotency and verify the business outcome is not created twice.
6. Repeat without an external transaction to see why `receiveAndConvert` does not hold the message until the handler finishes.

**Do not run destructive tests on a shared broker.** Use dedicated queues with controlled retry/DLQ settings.

## 12. @JmsListener and JmsMessagingTemplate: do not confuse APIs

`@JmsListener`:

~~~java
@Component
class OrderListener {

    @JmsListener(destination = "orders.in")
    public void onOrder(String orderId) {
        // Spring container listens continuously,
        // dispatching messages into the method per converter configuration.
    }
}
~~~

This is a **class snippet** requiring imports for `org.springframework.stereotype.Component`, `org.springframework.jms.annotation.JmsListener`, and listener infrastructure. It is not `receiveAndConvert` rewritten asynchronously: the container has its own lifecycle, error handling, and session transactions.

`JmsMessagingTemplate`:
- Uses the `org.springframework.messaging.Message<?>` abstraction, distinct from `jakarta.jms.Message`.
- Provides a typed `receiveAndConvert(destinationName, Class<T>)` API in corresponding Spring versions.
- Choosing it over `JmsTemplate` is an abstraction decision, not a substitute for timeouts, transactions, idempotency, or broker setup.
- If the requirement is primarily payload/domain-focused, the typed API can be convenient; if raw JMS headers are needed, `JmsTemplate.receive` is easier to inspect.

## 13. Common mistakes

1. **Thinking `receiveAndConvert` does not block.** The name only describes conversion, not execution model.
2. **Calling receive in an HTTP handler without a timeout.** The default can wait indefinitely, tying up worker threads.
3. **Calling receive then receiveAndConvert to “read the same message two ways”.** The first call already consumed the message; the second is an independent receive.
4. **Believing the default converter parses JSON automatically.** `TextMessage` typically becomes `String`; DTOs require a JSON codec/schema.
5. **Directly casting to a DTO.** The converter may return `String`, `byte[]`, `Map`, or another object.
6. **Assuming only `receiveAndConvert` can return null.** Both return null on timeout, and custom converters may also yield a null payload.
7. **Trying to call `acknowledge` after business processing on a template-received message.** The session may already be acked/committed/closed; you cannot retroactively enforce delayed ack semantics.
8. **Using `setSessionTransacted(true)` and assuming the handler after receive runs inside that JMS transaction.** The template-created local transaction may commit right during `receive`.
9. **Ignoring conversion failures that happen after commit.** Set the transaction boundary properly or use a listener container.
10. **Reading JSON fields via a JMS selector.** Selectors query supported JMS properties/headers, not JSON payloads.
11. **Putting no-wait in a loop without backoff.** Creates busy polling and wastes resources.
12. **Using `ObjectMessage` between independent services without controlling deserialization.** Couples Java classes and introduces security risks.
13. **Mismatched queue/topic domains.** A producer sending to a topic and a template receiving from a queue with the same name use two distinct logical destinations.
14. **Failing to separate broker delivery from business success.** JMS ACK/commit and DB/HTTP side effects are usually not atomic.
15. **Lacking idempotency keys or DLQs.** Redelivery after a process crash can still cause duplicate side effects.

## 14. Pre-coding decision checklist

- **Data:** Do I need the full JMS `Message` or only the Java payload?
- **Metadata:** Are `JMSMessageID`, `CorrelationID`, `JMSRedelivered`, or properties/selectors needed?
- **Converter:** Is it `SimpleMessageConverter` or a custom JSON converter? Is it configured on **both** producer and consumer?
- **Type:** Is the expected result `String`, `byte[]`, `Map`, or a DTO? Are `instanceof` checks/validation present?
- **Destination:** Is the queue/topic name right? Is a default destination configured if calling an argumentless overload?
- **Timeout:** Is there a wait limit and a strategy to handle `null`? Could it accidentally block HTTP threads?
- **Business ownership:** What work is this message pulled for? Is anything else competing on the same queue?
- **Reliability:** When does JMS local commit happen? Are conversion and business logic inside an external transaction?
- **Idempotency:** If the same message is redelivered, will data or side effects be duplicated?
- **Failure handling:** How are conversion/schema errors observed, retried, and routed to a DLQ?
- **Lifecycle:** Is the consumer a paced poll, or a 24/7 service that should use `@JmsListener`?
- **Integration tests:** Have real broker, timeouts, selectors, type mismatches, rollbacks, and retries been tested?

**Concluding rule:** Choose **`receive()`** to obtain the JMS message with headers/properties/body type and read data explicitly; choose **`receiveAndConvert()`** when the payload is all you need and the converter is standardized. Both are **synchronous receives** and both require designing timeouts, transactions, idempotency, and retry/DLQ handling. Do not let converter convenience obscure the exact moment a message is acknowledged to the broker.

## 15. Practice exercises

1. Send `TextMessage("hello")` with JMS property `traceId="t-1"`. Write two snippets: one using `receive()` to read body and property, the other using `receiveAndConvert()`; explain what information is lost in the second result.
2. Send a single message to `task.in`, then call `receive("task.in")` followed by `receiveAndConvert("task.in")` with a 1-second timeout. Why can the second call return null?
3. Using `SimpleMessageConverter`, receive a JSON payload `{"amount":25}`. What is the actual Java result type? What additional steps are needed to obtain a `Payment` DTO?
4. A batch processor uses `receiveAndConvert` then calls a payment API; the payment succeeds, but the app crashes before recording the business outcome. Analyze the JMS state, which idempotency key is needed, and the limits of a standalone JMS transaction.
5. Compare `setReceiveTimeout(0)`, `setReceiveTimeout(-1)`, and `setReceiveTimeout(1500)`. Why is a 100% CPU no-wait loop usually a bad design?
6. For `receiveSelectedAndConvert("orders.in", "kind = 'refund'")`, where should the `kind` property be set? Can you put a `kind` field only inside the JSON body and still have the selector match it automatically?
7. Write an integration test where a converter intentionally throws an exception inside and outside an external JMS transaction, verifying the difference in redelivery.
8. Modify the lab in section 8 to send `byte[]`, then update the handler branch with `instanceof byte[] bytes` and explain why you should not blindly cast to `String`.
9. When a service needs to process every message on a queue continuously across 5 replicas and requires redelivery on handler failure, should you choose a `receiveAndConvert` loop or `@JmsListener`? Explain in terms of ownership, transactions, and lifecycle.

## Official references

- Spring Framework 6.2 — **Receiving a Message**, synchronous vs listener container: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — **Sending a Message / Message Converters**: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework 6.2 — **JmsTemplate API**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.2 — **SimpleMessageConverter**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html
- Spring Framework — **Annotated JMS Listener Endpoints**: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Boot 3.5 — **JMS and Artemis support**: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Jakarta Messaging 3.1 — **Message, headers/properties, selectors and acknowledge**: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
