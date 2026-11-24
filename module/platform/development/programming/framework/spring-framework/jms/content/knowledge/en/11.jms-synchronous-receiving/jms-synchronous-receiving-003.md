# Null Result on Timeout During Synchronous Receiving in Spring JMS

## 1. Objectives

When calling `JmsTemplate.receive(...)` or `JmsTemplate.receiveAndConvert(...)` to **receive a JMS message synchronously**, a program typically expects to obtain a message and continue processing. But what happens if no matching message is available before the wait window expires? The normal result is **`null`**, not an empty JMS message and not an exception by default.

This scenario is critical in polling, request/reply, scheduled workers, and applications that must bound how long a thread is held waiting for a message.

This lesson helps you:
- Distinguish `receive()`, `receive(timeout)`, and `receiveNoWait()` in Jakarta Messaging.
- Accurately understand how `receiveTimeout` is configured in Spring `JmsTemplate`: **positive = finite wait; `0` = indefinite wait; negative = no wait**.
- Handle `null` properly without confusing it with a broken connection, an empty message payload, a nonexistent Queue, or a closed consumer.
- Write Java 17+ code with both the raw JMS API and Spring Boot; know when to use `receiveAndConvert` or `receiveSelected`.
- Design appropriate retry, timeout policies, metrics, and transactions/acknowledgements for polling.
- Test all three branches: **message received**, **timeout**, and **real exception**.

Examples use **Jakarta Messaging 3.x** (`jakarta.jms.*`), **Spring Framework 6.x**, and **Spring Boot 3.5.x**; older Spring/JMS versions may use the `javax.jms` namespace. The principles of `null` and synchronous waiting remain similar, though matching dependency versions must be used.

## 2. How does synchronous receiving work?

Imagine a worker that wants to wait at most 2 seconds to pull a job from Queue `jobs.queue`.

```text
Worker thread                  JMS client / broker
     |                                 |
     | JmsTemplate.receive(...)        |
     |-------------------------------->|
     |  wait for matching message      |
     |                                 +-- Message before deadline?
     |                                 |      |
     |                                 |      +-- YES -> return Message
     |                                 |      |
     |                                 |      +-- NO -> timed out
     |<--------------------------------|
     | message != null ?               |
     |   process message               |
     | : branch to "none available"    |
```

**Synchronous receive** means the calling thread waits according to the timeout rules. It **does not mean the broker actively creates a "null message" and sends it to the Queue**. `null` is a client-side API result indicating no message was returned for that receive attempt.

A single `null` return does not justify concluding that the Queue is permanently empty. A message may:
- Arrive **right after** the timeout.
- Have already been taken by another consumer.
- Not match the **message selector** of this receive call.
- Be waiting on a delivery delay or held by broker policy.
- Fail to be delivered to the consumer because `start()` was not called on the connection in the raw API.
- Be affected by consumer lifecycle events (for instance, closed while waiting).

What can accurately be said is: **within the wait window of that specific call, no JMS `Message` was returned to the caller**.

## 3. Jakarta Messaging API: receive, receive(timeout), receiveNoWait

`jakarta.jms.MessageConsumer` provides three synchronous receive methods:

| Call | Wait behavior | Result when no matching message is available |
| --- | --- | --- |
| `consumer.receive()` | Waits until a message arrives or the consumer is closed | Typically keeps waiting; may return `null` if the consumer is closed concurrently. |
| `consumer.receive(2_000)` | Waits up to roughly 2,000 ms for a message | Returns `null` on timeout or concurrent consumer close. |
| `consumer.receive(0)` | **Waits indefinitely** (0 is not polling) | Does not time out on its own; may return `null` if the consumer closes. |
| `consumer.receiveNoWait()` | Checks for a message immediately at call time | Returns `null` if no message is immediately available. |

**Very easy to confuse:** In the **raw JMS API**, `receive(0)` is not synonymous with `receiveNoWait()`. `0` means **never expire**. If you want an immediate probe, call `receiveNoWait()` explicitly.

Per the Jakarta Messaging specification, `receive(long timeout)` blocks until a message arrives, the timeout expires, or the consumer closes. Calling `close()` on a consumer can cause a waiting `receive` to return `null`, so not every `null` proves a timeout occurred. Internal provider/transport errors are normally reported via `JMSException`, not by intentionally returning `null`.

### 3.1. Raw Java JMS example handling null

Below is a reusable class in an application that already provides a broker `ConnectionFactory`:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class ClassicTimedReceiver {

    public static String pollOnce(ConnectionFactory factory,
                                  String queueName,
                                  long timeoutMillis) throws JMSException {

        if (timeoutMillis <= 0) {
            throw new IllegalArgumentException(
                    "timeoutMillis must be greater than 0");
        }

        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageConsumer consumer =
                     session.createConsumer(session.createQueue(queueName))) {

            connection.start();  // Start delivery for the consumer.

            Message message = consumer.receive(timeoutMillis);

            if (message == null) {
                return null;      // No message in this receive attempt.
            }

            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalArgumentException(
                        "Expected TextMessage, got "
                        + message.getClass().getName());
            }

            return textMessage.getText();
        }
    }
}
```

This is a syntactically valid Java 17+ class when the Jakarta Messaging 3.x API/provider is on the classpath; it is **not yet a standalone runnable program** because `ConnectionFactory` must be injected or created from a specific provider. Any caller must distinguish the `pollOnce(...) == null` branch from exceptions. At the API level, `TextMessage.getText()` can return an empty string or even `null` if the message has no text; therefore returning a plain `String` from this method **cannot distinguish every state**. If you need to distinguish "TextMessage present with null body" accurately, return `Message` (or a result type with a `received` flag) and inspect the body separately. The `Message` section of the examples makes this clear.

**Why is `connection.start()` required?** In classic JMS, delivery to consumers on a connection is not started by default. Forgetting `start()` can cause `receive(timeout)` to return `null` even when the broker has waiting messages. Sending messages via a producer does not require `start()`, whereas synchronous receiving through a classic connection typically does.

**Why use `try-with-resources`?** `Connection`, `Session`, and `MessageConsumer` are `AutoCloseable` in Jakarta Messaging 3.x; resources created by the application must be cleaned up. A `Session` must not be shared arbitrarily across multiple threads.

### 3.2. Simplified API with JMSContext/JMSConsumer

Jakarta Messaging also provides `JMSContext` and `JMSConsumer`:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Message;

public final class ContextTimedReceiver {

    public static Message pollOnce(ConnectionFactory factory,
                                   String queueName) {
        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            JMSConsumer consumer =
                    context.createConsumer(context.createQueue(queueName));
            return consumer.receive(2_000L);
        }
    }
}
```

This is also a method requiring a runtime `ConnectionFactory` implementation, without a `main`. The Simplified API primarily uses `JMSRuntimeException` (unchecked) for API errors, whereas the classic API uses `JMSException` (checked). `JMSContext` automatically starts the connection when needed by default (`autoStart` defaults to `true`). If you explicitly disable auto-start, be sure to call `context.start()` before receiving.

**Lifetime note:** a finite `receive` is a blocking operation; exiting the `try` block closes `JMSContext`. For a continuous worker, do not create a new connection/context in a tight loop without considering caching/pooling and lifecycle.

## 4. Spring JmsTemplate: where does null appear?

In Spring Framework, `org.springframework.jms.core.JmsTemplate` provides these overloads:

```java
jakarta.jms.Message message = jmsTemplate.receive("jobs.queue");
Object payload = jmsTemplate.receiveAndConvert("jobs.queue");
```

This is a snippet inside a Spring-managed component with a `jmsTemplate` bean. Both perform **synchronous receiving**. They use `ConnectionFactory`, `Session`, `MessageConsumer`, and `DestinationResolver` underneath while letting Spring manage the lifecycle of those resources.

Results:
- `receive(...)` returns **`jakarta.jms.Message`** when received, or **`null`** when the receive attempt yields no message.
- `receiveAndConvert(...)` receives the message and uses `MessageConverter` to convert it to a Java object, or returns **`null`** when no message is received.
- If the provider throws a checked `JMSException`, Spring typically translates it into the unchecked `org.springframework.jms.JmsException` hierarchy.
- If a JMS message exists but the converter cannot handle it, the program may encounter **`MessageConversionException`** instead of `null`. With custom converters, check the `null` payload convention as well; to strictly distinguish *no Message received* from *payload has no value*, use `receive(...)` and inspect the `Message` before converting.

An accurate way to state this:

> A `null` from `JmsTemplate.receive(...)` means **no message was returned for that receive attempt**, usually due to timeout; it is not an exception and not confirmation that the broker failed.

### 4.1. Safe coding pattern

```java
Message message = jmsTemplate.receive("jobs.queue");

if (message == null) {
    // No message in this poll.
    // Can return NO_WORK or schedule a later check.
} else {
    // A real JMS Message is present.
    // Process/convert only when message is non-null.
}
```

This is a snippet using `jakarta.jms.Message`. Do not write `message.getJMSMessageID()`, `message.getBody(...)`, or cast to `TextMessage` before checking for `null`; otherwise you will get a `NullPointerException` due to a missing message rather than a JMS failure.

With `receiveAndConvert`:

```java
Object payload = jmsTemplate.receiveAndConvert("jobs.queue");

if (payload == null) {
    System.out.println("NO_WORK");
} else if (payload instanceof String text) {
    System.out.println("WORK=" + text);
} else {
    System.out.println("UNEXPECTED_PAYLOAD_TYPE");
}
```

`String text` uses Java 17 pattern matching for `instanceof`. If the broker sends a `BytesMessage` or another object, the converter may return a different type or throw an error; do not assume every payload is always a `String`.

### 4.2. Returning null is a result branch; do not replace it with exceptions

An **inappropriate** pattern:

```java
try {
    Message message = jmsTemplate.receive("jobs.queue");
    process(message); // Possible NPE on timeout.
} catch (Exception e) {
    // Treats every error as an empty Queue.
}
```

This is an **anti-pattern**, not a complete program. It masks connection errors, destination configuration mistakes, converter errors, and business failures. Moreover, `process(message)` is not defined in this snippet.

A **meaningful** pattern: separate the two branches:

```java
try {
    Message message = jmsTemplate.receive("jobs.queue");
    if (message == null) {
        recordEmptyPoll();
        return;
    }
    process(message);
} catch (org.springframework.jms.JmsException ex) {
    recordReceiveFailure(ex);
    throw ex;
}
```

This is an illustrative method body; `recordEmptyPoll`, `recordReceiveFailure`, and `process` must be defined by the application. There is no need to throw an exception for a receive attempt with no message when polling is normal behavior.

## 5. Configuring receiveTimeout: 0 does not mean "do not wait"

A shared `JmsTemplate` is usually configured via `@Bean` or `application.properties`. `receiveTimeout` uses **milliseconds** in the Java API.

| `JmsTemplate.setReceiveTimeout(...)` value | Expected behavior |
| --- | --- |
| `2_000L` | Waits up to roughly 2 seconds to receive a message. |
| `250L` | Waits up to roughly 250 ms. |
| `0L` | **Waits indefinitely**; equivalent to indefinite receive. |
| `JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT` | Constant representing `0L`: waits with no receive deadline. |
| `JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT` | Negative constant: attempts immediate receive without blocking for a message. |
| Another negative number | Spring treats it as **no-wait**; does not pass negative directly to `MessageConsumer.receive(long)`. |

Per Spring Framework, **`JmsTemplate` defaults to indefinite wait**. If an HTTP endpoint uses the default template to receive when the Queue has no messages, the request thread can be held without limit. Therefore, set a finite timeout when the processing model requires one.

### 5.1. Setting timeout in Java

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

public final class TimedTemplateFactory {
    public static JmsTemplate create(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000L);
        return template;
    }
}
```

This is a Java 17+ helper class in a project with `spring-jms` and a configured `ConnectionFactory`. The `create` method returns a pre-configured template before handing it to threads. In a Spring application, define a bean once instead of creating a new template per request.

### 5.2. Configuration in Spring Boot

With Spring Boot 3.5.x using the auto-configured `JmsTemplate`, set:

```properties
spring.jms.template.receive-timeout=2s
```

This is a Spring Boot duration property. `2s` binds to roughly 2,000 ms on `JmsTemplate`. You can set `500ms` or `5s` as needed. If you define a custom `JmsTemplate` bean instead of relying on auto-configuration, verify that the bean has the right timeout set; do not assume Boot properties automatically apply to an instance you construct manually with `new`.

### 5.3. No-wait is a distinct mode

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JmsDestinationAccessor;

JmsTemplate noWait = new JmsTemplate(connectionFactory);
noWait.setReceiveTimeout(
        JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT);

Object value = noWait.receiveAndConvert("jobs.queue");
```

The code above is a snippet inside a method that already has `connectionFactory`. It suits a quick check, though `null` can still appear when no message is available **at the instant of checking**, even if a message arrives immediately afterward. Do not mutate the timeout of a shared singleton `JmsTemplate` continuously across threads; template parameters should be configured prior to concurrent use.

**Direct comparison of the two APIs:**

```text
Jakarta MessageConsumer.receive(0)        = wait indefinitely
Jakarta MessageConsumer.receiveNoWait()   = no wait

Spring JmsTemplate.setReceiveTimeout(0)   = wait indefinitely
Spring JmsTemplate.setReceiveTimeout(-1)  = no wait
Spring JmsTemplate.setReceiveTimeout(2000)= wait up to about 2 seconds
```

In production code, prefer the `RECEIVE_TIMEOUT_NO_WAIT` constant over an easily misread negative literal.

### 5.4. receiveTimeout is not a deadline for the entire request

`receiveTimeout` primarily governs **the consumer's message-waiting phase**. Connection creation, authentication, destination resolution, session setup, reconnection, or cleanup can have separate timeouts. Thus, total execution time of `JmsTemplate.receive(...)` can **exceed** `receiveTimeout`.

If an HTTP SLA must stay under 3 seconds, do not assume `receiveTimeout=3000` alone guarantees the endpoint finishes in 3 seconds. Configure connection/network timeouts, circuit breakers, and request deadlines, and load-test with a real broker.

## 6. Complete Spring Boot example: observing timeout, message receipt, and timeout again

The example below uses:
- **Java 17+** and **Spring Boot 3.5.8**.
- **An external Apache ActiveMQ Artemis broker**, connected natively over TCP.
- `spring-boot-starter-artemis` for the JMS/Jakarta client and Spring JMS.
- Boot's auto-configured `JmsTemplate` with a **2-second** timeout.
- Queue `learning.timeout.queue` **pre-created** or allowed to auto-create by broker policy.

The demo has three steps: receiving when the Queue is initially empty, sending a `TextMessage`, receiving the sent message, and receiving once more when the Queue is empty again.

### 6.1. File structure

```text
spring-jms-timeout-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── jms/
        │           └── ReceiveTimeoutApplication.java
        └── resources/
            └── application.properties
```

### 6.2. Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>spring-jms-timeout-demo</artifactId>
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
```

### 6.3. application.properties

```properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}

spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=2s
```

`native` here means connecting to an **external running Artemis broker**. The properties file does not start a broker. `JMS_USERNAME`/`JMS_PASSWORD` must be supplied from the environment. Passwords in real codebases must be protected using proper secret management.

### 6.4. Java application

**`src/main/java/example/jms/ReceiveTimeoutApplication.java`**

```java
package example.jms;

import jakarta.jms.Message;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ReceiveTimeoutApplication {

    private static final String QUEUE = "learning.timeout.queue";

    public static void main(String[] args) {
        SpringApplication.run(ReceiveTimeoutApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JmsTemplate jmsTemplate) {
        return args -> {
            // Step 1: Assume the Queue is clean and there are no other producers.
            Message before = jmsTemplate.receive(QUEUE);

            if (before == null) {
                System.out.println("first=NO_MESSAGE");
            } else {
                System.out.println("first=RECEIVED");
            }

            // Step 2: Send a TextMessage using the default converter.
            jmsTemplate.convertAndSend(QUEUE, "hello-timeout");

            Object received = jmsTemplate.receiveAndConvert(QUEUE);
            if (received == null) {
                System.out.println("second=NO_MESSAGE");
            } else {
                System.out.println("second=" + received);
            }

            // Step 3: Once the message has been received and no other producers exist,
            // the next receive typically waits ~2 seconds then returns null.
            Message after = jmsTemplate.receive(QUEUE);
            System.out.println(
                    after == null ? "third=NO_MESSAGE" : "third=RECEIVED");
        };
    }
}
```

Explanation:
1. `@SpringBootApplication` creates the application context and enables JMS auto-configuration from the starter.
2. Boot injects the `JmsTemplate` already configured with `receiveTimeout=2s` from the property.
3. `jmsTemplate.receive(QUEUE)` fetches a message or returns `null`. The first call on a truly empty Queue takes the `NO_MESSAGE` branch after the wait.
4. `convertAndSend` converts the Java `String` into a JMS `TextMessage` via the default `SimpleMessageConverter` and sends it.
5. `receiveAndConvert` receives the message and returns the `String` payload, so the second call returns `hello-timeout` if no other consumer grabs the message.
6. The final receive returns `null` when no messages remain, illustrating timeout once more.
7. There is no `@JmsListener` in this application: the demo uses **synchronous receiving** only.

### 6.5. How to run

Ensure the broker is running, Queue `learning.timeout.queue` exists or auto-create is enabled, and no other publishers/consumers are on the Queue during testing. **Clean the Queue before running the demo**; previous runs may leave messages behind.

PowerShell:

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"
mvn spring-boot:run
```

POSIX shell:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=dev-user \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Replace `dev-user`/`dev-password` with an actual account permitted to send/receive. Without an Artemis broker, the code will compile but fail to connect at runtime.

**Stdout from `System.out.println` when the Queue is initially clean, the broker is running, and there are no other consumers:**

```text
first=NO_MESSAGE
second=hello-timeout
third=NO_MESSAGE
```

Spring Boot/Artemis logs will also appear. Do not treat 2 seconds as an exact execution time: scheduling, broker/network latency, and resource creation/closing can cause variance. If the Queue contains old messages, step 1 may print `first=RECEIVED`; if a competing consumer takes the message or the broker is not ready, step 2 may print `NO_MESSAGE` or throw an exception.

**Build without a broker** (in the directory containing `pom.xml`):

```bash
mvn -q -DskipTests package
```

Verifying the actual message path requires running against a broker. Do not use this example to claim "every run prints these exact three lines" when the Queue is not isolated.

## 7. Do not confuse an empty message, a null payload, and a timeout null

### 7.1. Message exists, but payload is an empty string

Suppose the broker delivers a `TextMessage` with text `""`:

```java
Message message = jmsTemplate.receive("jobs.queue");

if (message == null) {
    // No JMS Message received.
} else if (message instanceof jakarta.jms.TextMessage text) {
    String body = text.getText();
    if ("".equals(body)) {
        // Real Message received; body is an empty string.
    }
}
```

This is a snippet inside a method that declares `throws JMSException` or catches `JMSException` around `getText()`. An empty string is **not** the `null` returned by `receive`. On a `TextMessage` whose text was never set, the body may be `null` even though the `Message` exists; check `message != null` before inspecting the payload.

### 7.2. receiveAndConvert returning null is a different abstraction

`JmsTemplate.receiveAndConvert` normally returns `null` when `receive` fails to obtain a message. However, if the application uses a custom `MessageConverter` that can return `null` for a valid message, a `null` return value no longer cleanly distinguishes "no message" from "converter returned no value."

If business logic must distinguish these strictly:
1. Call `jmsTemplate.receive(queueName)` to get `Message`.
2. If `message` is `null`, handle the no-message-received branch.
3. Only if `message` exists, read headers/body or invoke the converter safely.
4. If the converter throws `MessageConversionException`, handle it as a **data/conversion error**, not an empty Queue.

In many services that only send/receive `String` via the default `SimpleMessageConverter`, `receiveAndConvert` is convenient enough. Yet protocol or audit applications that need exact proof of Message presence should keep the two classification layers separate.

### 7.3. Null does not mean the broker sent a "null message"

A JMS `Message` is an object with headers/properties and a body. `null` is used by the Java API as a **sentinel** for no message returned, not a message placed onto the Queue. Never attempt `producer.send(null)` to produce an "empty poll" — that is an API error, not a broker signal.

## 8. Timeout with message selectors and competing consumers

### 8.1. Message selectors can return null even when the Queue has messages

`JmsTemplate` supports `receiveSelected`:

```java
jmsTemplate.setReceiveTimeout(1_500L);

Message urgent = jmsTemplate.receiveSelected(
        "jobs.queue", "priorityGroup = 'URGENT'");

if (urgent == null) {
    // No Message matched the selector in this wait window.
    // Do not infer that jobs.queue is completely empty.
}
```

This is a snippet for a template not yet shared concurrently; for a production singleton, configure timeout before startup. `priorityGroup` is a producer-set JMS message property, not the system priority header. If the Queue only contains `priorityGroup = 'NORMAL'` messages, a consumer filtering for `URGENT` can wait until timeout and receive `null` while other messages remain pending in the Queue.

Similarly, if you use `JMSCorrelationID` to await a reply:

```java
String id = java.util.UUID.randomUUID().toString();
String selector = "JMSCorrelationID = '" + id + "'";
Message reply = jmsTemplate.receiveSelected("replies.queue", selector);

if (reply == null) {
    // Reply matching correlation ID has not arrived within this timeout.
}
```

The example assumes the producer/responder knows the id and sets `JMSCorrelationID` accordingly. A `UUID` contains no single quotes, so the selector is safely constructed here; if taking IDs from user input, guard against selector injection/improper escaping. A **reply timeout** can happen because the responder is slow or the reply arrives later; it does not cancel the already-sent request.

### 8.2. Multiple consumers on one Queue

In the competing consumers model, a message is normally delivered to **one** consumer at a time according to broker semantics. If workers A and B both call `receive`:

```text
Queue has exactly one message
       |
       +---- Worker A receives the Message
       |
       +---- Worker B times out -> null
```

Worker B cannot conclude the Queue "never had a message." It can only conclude **B did not obtain a message during its wait window**. Prefetch, consumer priority, transaction rollback, and redelivery policies can affect distribution; "messages must be split evenly across workers" is not guaranteed on a single poll.

### 8.3. Topics and subscriptions

With a Topic, messages are broadcast per subscription, unlike a Queue storing work items for competing workers. If a subscriber was not active when the publisher sent a message, a non-durable subscription may not receive older messages. A synchronous receive on a Topic returning `null` does not necessarily mean nothing was ever published to the Topic.

Using a Topic with Spring JMS requires `pubSubDomain=true` and proper subscription/durable configuration if replay per provider rules is needed; merely changing the destination name string does not preserve Queue semantics.

## 9. Timeout is not JMSException: how to handle it in business logic?

The following table is useful when designing a polling service:

| State | Java/Spring return | Reasonable interpretation | Reaction to consider |
| --- | --- | --- | --- |
| Message arrives before deadline | `Message != null` | A message was received | Process payload and acknowledgement/transaction as designed. |
| No matching message before deadline | `Message == null` | Current poll received no message | Return `NO_WORK`, schedule next poll, or return empty response. |
| Consumer closed while waiting | May be `Message == null` | Call ended due to lifecycle | Distinguish shutdown/cancellation using application state. |
| Broker/connection/JMS provider error | Usually `JMSException` or `JmsException` | Real failure, not an empty Queue | Log, retry/backoff, alert, and monitor health. |
| Wrong destination/permissions | Usually an exception | Configuration or access issue | Fix config/authorization; do not poll endlessly. |
| Message received but converter failed | `MessageConversionException` | Message exists, payload invalid for converter | Handle poison message/transaction and DLQ. |
| Received body is `""` | `Message != null`, empty text | Real message, empty body | Apply business validation; do not treat as timeout. |

Do not map every `null` to HTTP `500`, because an empty poll is usually normal. Likewise, do not map every broker error to HTTP `204 No Content`: clients need to know the service is failing so they can retry or alert. HTTP status codes depend on the API contract; for example, a polling endpoint might return `204` when there is no work, `200` when work is present, and `503` when the broker is temporarily unavailable.

**Important:** receiving `null` does not trigger a "negative acknowledgement." No JMS message was delivered to the caller to ack/commit, so there is no "empty message" to send to a DLQ.

## 10. Transactions and acknowledgement: does null lose messages?

Normally **no**. A timeout does not cause an undelivered message to vanish from the Queue. A message may arrive later and be picked up on the next poll; however, expiry, purge, competing consumers, DLQ, routing, and broker policies can still affect messages actually residing on the broker.

You must distinguish **timing out before receiving** from **failing after already receiving a message**:

### 10.1. AUTO_ACKNOWLEDGE

In classic `Session.AUTO_ACKNOWLEDGE`, acknowledgement occurs per the JMS provider/receive semantics. If `receive(timeout)` returns `null`, no message was handed to the application, so there is nothing to acknowledge for that call.

However, when `receive` returns **a real message**, the application must be careful: if it subsequently writes to a database outside a transaction and fails, `AUTO_ACKNOWLEDGE` does not turn a database failure into a JMS rollback. Never expect throwing an exception in a Java method after receiving to make the broker redeliver as desired across all ack modes.

### 10.2. CLIENT_ACKNOWLEDGE

With the classic API, a consumer can use `Session.CLIENT_ACKNOWLEDGE` to control acknowledging after appropriate processing. With `JmsTemplate.receive(...)`, however, the Spring template handles acknowledgement according to its own lifecycle when receiving a message; do not treat calling `receive` on a template as identical to a client-managed raw `Session` spanning multiple business steps.

If you need to execute business logic before ack/commit, choose a transacted listener model or an explicitly managed session/transaction. Do not copy a `message.acknowledge()` snippet from raw JMS and expect the same effect after the template has already received and cleaned up the session.

### 10.3. Local JMS transaction

With `Session.SESSION_TRANSACTED` or `JmsTransactionManager`, a received message is governed by the **commit/rollback** of the session/transaction. If `receive(timeout)` returns `null`, essentially no new message was received in that call to roll back. Other operations may still be part of the same session transaction; do not assume "the transaction did nothing at all" solely from one null receive.

**Warning:** `JmsTransactionManager` manages only the JMS resource; database transactions are not automatically atomic with JMS. If the system must safely combine SQL writes and message processing, consider outbox/inbox, idempotency, or genuinely configured XA/JTA.

## 11. Designing efficient polling and avoiding busy loops

A common mistake is setting no-wait timeout and looping continuously:

```java
while (true) {
    Object payload = jmsTemplate.receiveAndConvert("jobs.queue");
    if (payload == null) {
        continue; // Busy spin if receiveTimeout is no-wait.
    }
    handle(payload);
}
```

This is an **anti-pattern**: no stop policy, no backoff, and `handle` is undefined. With `receiveTimeout < 0`, the loop can put heavy pressure on CPU, connections/sessions, and the broker when the Queue is empty.

### 11.1. Bounded polling with backoff and shutdown flag

A clearer pattern:

```java
public void pollLimited(int maxAttempts) throws InterruptedException {
    for (int attempt = 0; attempt < maxAttempts; attempt++) {
        Object payload = jmsTemplate.receiveAndConvert("jobs.queue");

        if (payload != null) {
            handle(payload);
            return;
        }

        // No message: wait before the next poll.
        Thread.sleep(500L);
    }
}
```

This snippet belongs to a service with a `jmsTemplate` field and an application-defined `handle` method, and is suitable only for a dedicated worker thread; do **not** use it as-is in an HTTP request thread, as it can hold the thread for a long time. The template should have a finite timeout and `maxAttempts` should be bounded. Production code needs a shutdown/interrupt flag and a load-aware backoff policy.

If you find yourself polling continuously to process jobs, a better option is usually **`@JmsListener` + a Spring listener container**. The container manages consumer lifecycle, concurrency, acknowledgement, recovery, and waiting for messages; business code simply defines the handler when a message arrives.

### 11.2. Do not change a shared bean's timeout per request

`JmsTemplate` is designed to be shared once configured. Having one request call `setReceiveTimeout(100)` and another call `setReceiveTimeout(5000)` on the same singleton can cause unpredictable behavior under concurrency.

A cleaner approach:
- One template configured for batch workers with a timeout of a few seconds.
- Another template configured as **no-wait** for quick checks.
- Or use the provider API when per-invocation consumer/timeout control is needed.

Do not create a new connection factory each time just to vary the timeout. Resource configuration and caching/pooling should be separated from per-worker wait duration goals.

### 11.3. Timeout for request/reply

With request/reply, a `null` from a correlation-ID reply Queue usually means **the reply has not arrived before the deadline**. The request may still be in progress on the responder side.

Therefore you need:
- A stable correlation ID or request ID.
- A clear deadline communicated in the API contract.
- Handling for **late replies** (arriving after the caller gave up waiting).
- Retrying requests only after analyzing responder idempotency.
- Separate metrics for reply timeouts and request failures.

Do not automatically resend a side-effecting operation when a reply is missing, because the first request may have already succeeded.

## 12. Logging, monitoring, and distinguishing root causes

### 12.1. What should be logged on null?

Example structured log fields:

```text
event=jms_receive_timeout destination=jobs.queue wait_ms=2000 outcome=no_message
```

Use `DEBUG` or metrics for normal polling timeouts rather than spamming `ERROR` whenever the Queue is empty. If timeout rates spike suddenly in a workflow that normally has steady work, alert based on **expected SLO/throughput**, not on a single `null`.

Useful metrics:
- `jms_receive_attempt_total` and `jms_receive_timeout_total`.
- `jms_receive_success_total`, `jms_receive_error_total`.
- Actual `receive` latency (p50/p95/p99).
- Queue depth/pending, consumer count, in-flight, and redelivery count from the broker.
- Count of messages failing selector match or expired replies.
- Connection setup time, authentication failures, and broker reconnects.

### 12.2. Use elapsed time for diagnosis, not as a substitute for API status

A `receive` returning `null` after roughly 2 seconds matches a 2,000 ms timeout. However, if it returns `null` unexpectedly early, check no-wait config, concurrent close/shutdown, selectors, connection start, or mutated timeout config. If elapsed time is much greater than 2 seconds, inspect connection/setup/recovery and thread scheduling.

Do not rely on `System.currentTimeMillis()` for accurate elapsed intervals in time-sensitive code because wall-clock time can jump; measure durations with `System.nanoTime()` or metrics timers. Even accurate timing cannot identify the exact cause without consumer and broker state.

## 13. Common mistakes and fixes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Treating `receive(0)` as no-wait | JMS and Spring use `0` for indefinite wait | Use `receiveNoWait()` or Spring's `RECEIVE_TIMEOUT_NO_WAIT` constant. |
| Leaving timeout unconfigured on request threads | Default template can block indefinitely | Set a finite `spring.jms.template.receive-timeout`. |
| Calling `message.getBody(...)` when message is null | Causes `NullPointerException` | Check `message != null` before reading. |
| Throwing `JMSException` when Queue has no messages | Timeout is a normal state in polling | Use a `NO_WORK`/empty result branch with proper logging/metrics. |
| Swallowing all `JmsException` and returning empty | Hides broker, destination, and permission errors | Separate exception paths from null; apply error-appropriate retry/backoff. |
| Casting `receiveAndConvert` result immediately | Null or different payload types cause NPE/CCE | Check null and payload type; handle converter errors separately. |
| Concluding Queue is empty because `receiveSelected` returned null | Non-matching messages may still exist | Inspect selector, Queue depth, and provider policies. |
| Omitting `connection.start()` in classic API | Delivery never starts; receive can time out | Call `start` before receiving. |
| Retrying immediately in a tight loop on null | Busy loop/CPU spike and higher broker load | Use finite timeout, backoff, or `@JmsListener`. |
| Sharing and mutating `receiveTimeout` across requests | Configuration race, unpredictable latency | Keep template configuration immutable after startup. |
| Treating timeout as an API response time guarantee | Setup/cleanup/network can take longer | Enforce overall deadlines, connection controls, and circuit breakers. |
| Treating timeout as message loss | Message may arrive later or go to another consumer | Distinguish polling result from queue state. |
| Treating null as "broker offline" | Offline broker typically throws an exception | Track connection health and exceptions separately. |
| Confusing null body with null Message | `TextMessage` may exist with empty/null text | Check Message first, then check body. |
| Switching to Topic while keeping Queue assumptions | Non-durable subscriptions have different delivery semantics | Configure subscription and domain properly. |

## 14. Testing: four minimum scenarios

### Scenario A: Empty Queue → timeout null

1. Provision an isolated test Queue and ensure no other producers/consumers exist.
2. Set `receiveTimeout=500ms` or `2s`.
3. Call `jmsTemplate.receive(queue)`.
4. Assert it returns `null`, **not a JMS exception**.
5. Measure wait duration near the timeout; allow scheduling/network tolerance.

Do not write tests asserting elapsed time equals exactly 500,000,000 ns. Assert a reasonable range, or use a mocked provider in unit tests to avoid clock/broker flakiness.

### Scenario B: Message arrives before timeout → successful receipt

1. Create/send a `TextMessage` to the Queue.
2. Call `receive` while the message is available.
3. Verify `Message != null` and the body matches.
4. Check queue/consumer counts per broker and ack mode. If other consumers exist, evaluate results under competing consumer semantics.

### Scenario C: Message arrives after timeout → null first, message next

For example: worker waits 500 ms, producer intentionally sends after 900 ms. The first attempt may return `null`, while the next receive attempt can pick up the message (unless taken by another consumer or expired). This demonstrates timeout **does not cancel publishing** and does not delete messages arriving later.

Do not make tests depend rigidly on `Thread.sleep(900)` under busy CI and assume the race always reproduces; use synchronization, fake clocks, or test harnesses with well-separated timings.

### Scenario D: Broker failure → exception rather than null

1. Use an invalid endpoint or stop the broker during the test.
2. Call `receive`.
3. Verify the exception path or provider health/recovery behavior.
4. Ensure the application does not turn connection errors into "Queue is empty."
5. Verify retry/backoff/alerting does not create a request storm.

### Unit testing the null branch without a broker

Extract the policy into a simple method and mock `JmsTemplate`:

```java
// Illustrative snippet in a test with Mockito and corresponding service declared.
when(jmsTemplate.receive("jobs.queue")).thenReturn(null);

PollResult result = service.pollOnce();

assertEquals(PollResult.NO_WORK, result);
verify(jmsTemplate).receive("jobs.queue");
```

This is not a standalone test class: `PollResult` and `service` are application types, `when/verify` come from Mockito, and `assertEquals` comes from JUnit. The goal is to verify **the null branch is handled**, not to prove the broker timed out accurately. Integration tests verify real provider behavior.

## 15. Production deployment checklist

- Decide whether business logic allows "no message" as a normal state.
- Set a finite `receiveTimeout` on threads that must meet an SLA; do not leave indefinite default unknowingly.
- Handle `Message == null` before reading headers/body, casting, or converting.
- Never call `receive(0)` thinking it means "check immediately"; use `receiveNoWait` or the corresponding no-wait constant.
- Distinguish `null`, broker errors, missing permissions, wrong destination, converter errors, and consumer shutdown.
- When using selectors, interpret `null` as no **selector-matching** message during that wait.
- With competing consumers, do not infer whole-Queue state from one worker's result.
- Design acknowledgement/transactions so messages are not lost if business processing fails **after receiving**.
- Set backoff/retry limits for polling; prefer `@JmsListener` when continuous consumption is needed.
- Measure timeout rate, success/error rate, receive latency, and Queue backlog separately.
- Verify request/reply contracts, late replies, and idempotency before auto-retrying.
- Test against a real broker covering null, message present, error, and shutdown paths; clean test Queues to avoid flakiness.

## 16. Self-check

**Q1.** Does `JmsTemplate.setReceiveTimeout(0)` mean inspect the Queue immediately?

**No.** A value of `0` means wait indefinitely; use `RECEIVE_TIMEOUT_NO_WAIT` or a negative number in Spring to avoid waiting.

**Q2.** If `consumer.receive(1500)` returns null, is the broker definitely disconnected?

**No.** The usual case is no matching message arrived within roughly 1.5 seconds. Broker/provider errors normally throw `JMSException`; concurrent consumer close can also return null.

**Q3.** If `receiveSelected("jobs.queue", "type = 'A'")` returns null, can you conclude the Queue is empty?

**No.** The Queue may still hold type B messages; the selector only accepts type A.

**Q4.** Why is `connection.start()` needed when using the classic JMS `MessageConsumer`?

Because delivery to consumers on a classic connection does not start automatically before `start()`; forgetting it can cause `receive(timeout)` to return null even when messages are waiting.

**Q5.** Does `receiveAndConvert` returning null mean the application processed an empty message?

**No.** With standard converters, null indicates no message was received; if you need to strictly separate null payloads/converters from a null Message, use `receive` and inspect the object first.

**Q6.** Does null from a timeout cause Queue messages to be moved to the DLQ?

**Not directly.** No message was delivered in that attempt to be rejected or rolled back. DLQ relates to processing error policies, redelivery, expiry, or broker-specific routing.

**Q7.** How do you prevent a worker from spinning hot when continuously polling an empty Queue?

Use an appropriate receive timeout, bounded attempts/backoff, and a shutdown policy; or switch to `@JmsListener` so the container manages consumer lifecycle.

## Conclusion

In **Spring JMS synchronous receiving**, `null` is a valid result when a `receive` call does not obtain a `Message`, typically due to **timeout**. It is not an empty JMS message, does not prove the Queue is strictly empty, and is not a substitute for a connection/provider exception.

The most important technical rule: **`receiveTimeout > 0` waits finitely; `receiveTimeout = 0` waits indefinitely; negative values in `JmsTemplate` mean no wait**. Always check for `null` before accessing message data, handle exceptions separately, account for selectors and competing consumers, and design retry/acknowledgement according to business requirements. One timeout only ends **that wait attempt**, without confirming that a job does not exist or will not arrive later.

## References

- Spring Framework — Receiving a Message, `receive` and `receiveTimeout`: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework 6.2 — `JmsTemplate` API, `setReceiveTimeout`/`receive`/`receiveAndConvert`: https://www.javadoc.io/static/org.springframework/spring-jms/6.2.13/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.2 — `JmsDestinationAccessor` timeout constants and `receiveFromConsumer`: https://www.javadoc.io/static/org.springframework/spring-jms/6.2.13/org/springframework/jms/support/destination/JmsDestinationAccessor.html
- Jakarta Messaging 3.1 — `MessageConsumer` API: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer
- Jakarta Messaging 3.1 — Specification, synchronous receive and message acknowledgement: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework — `JmsOperations` API: https://www.javadoc.io/static/org.springframework/spring-jms/6.2.13/org/springframework/jms/core/JmsOperations.html
- Spring Boot 3.5 — Artemis JMS integration: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Boot 3.5 — Common properties, `spring.jms.template.receive-timeout`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/