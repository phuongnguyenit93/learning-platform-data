# MessageCreator and the Callback-Provided Session in JmsTemplate

## 1. The problem MessageCreator solves

When sending messages with Spring JMS, an application often needs to build a **JMS Message** in the exact format expected by the receiving system: a `TextMessage`, `MapMessage`, or `BytesMessage` body; properties such as `eventType` and `schemaVersion`; and a `JMSCorrelationID` for transaction tracking. These objects are created via the `jakarta.jms.Session` API.

With raw Jakarta Messaging, application code typically has to deal with `ConnectionFactory`, `Connection`, `Session`, and `MessageProducer`, handle `JMSException`, and manage resources. Spring provides `JmsTemplate` to handle those underlying steps. The application only supplies a **callback** dedicated to creating the message.

Core example:

```java
jmsTemplate.send("orders.in", session -> {
    TextMessage message = session.createTextMessage("ORDER-1001");
    message.setStringProperty("eventType", "ORDER_CREATED");
    return message;
});
```

In this snippet:

- `jmsTemplate.send(...)` is the synchronous send operation invoked by the application; it creates and sends the JMS message.
- `"orders.in"` is the destination name to send to; Spring resolves the name into a `Destination` per configuration.
- `session -> { ... }` is a `MessageCreator` written as a lambda. **Spring passes the `Session` into the callback**, rather than the application passing a `Session` it created itself.
- `session.createTextMessage(...)` uses the very session provided by Spring to create a `jakarta.jms.TextMessage`.
- `return message` hands the prepared object to `JmsTemplate`; the template proceeds to send it through the JMS provider.

This example is a call placed **inside a method that has `JmsTemplate` injected**; it is not yet a standalone Java class.

### Learning outcomes

After this lesson, you will be able to explain the `MessageCreator` contract, know where `Session` comes from and its valid scope, create and configure headers/properties across message types, distinguish `send`, `convertAndSend`, and other callbacks, and handle errors, transactions, and callback testing intentionally.

## 2. The exact contract of MessageCreator

`org.springframework.jms.core.MessageCreator` is a Spring JMS functional interface with a single abstract method:

```java
@FunctionalInterface
public interface MessageCreator {
    jakarta.jms.Message createMessage(jakarta.jms.Session session)
            throws jakarta.jms.JMSException;
}
```

This is an **API signature description**; in real projects, use the interface from the Spring library and do not redefine it.

Meaning:

| Element | Explanation |
| --- | --- |
| `createMessage(Session session)` | Callback invoked by `JmsTemplate` to create one message |
| `Session` | Jakarta Messaging object available for the current operation, used as the factory for creating messages |
| Returned `Message` | Complete message object that the template will send; e.g., `TextMessage`, `MapMessage`, `BytesMessage` |
| `throws JMSException` | Allows calling JMS APIs that throw checked exceptions directly inside the callback |
| `@FunctionalInterface` | Can be written as a lambda, method reference, or anonymous class |

This lambda declaration:

```java
MessageCreator creator = session -> session.createTextMessage("hello");
```

is conceptually equivalent to the anonymous class:

```java
MessageCreator creator = new MessageCreator() {
    @Override
    public Message createMessage(Session session) throws JMSException {
        return session.createTextMessage("hello");
    }
};
```

For the two examples above, required imports are `jakarta.jms.JMSException`, `jakarta.jms.Message`, `jakarta.jms.Session`, and `org.springframework.jms.core.MessageCreator`.

**Note:** the parameter name `session` is chosen by the lambda author; it is not a bean name for Spring to look up. Its parameter type is inferred from the `MessageCreator` signature. The lambda executes **when `JmsTemplate` invokes the callback during `send`**, not when the broker consumes the message, and it is not a `@JmsListener`.

## 3. Internal execution flow of JmsTemplate.send

The example `jmsTemplate.send("orders.in", creator)` can be understood through the following high-level flow:

```text
Application code calls JmsTemplate.send(destinationName, creator)
                 |
                 v
      JmsTemplate obtains JMS Connection/Session
      or joins Session bound to an active transaction
                 |
                 v
      Resolves name "orders.in" into a Destination
                 |
                 v
      Invokes creator.createMessage(session)
                 |
                 v
      Callback uses session.createXxxMessage(...)
      sets body / headers / properties, then returns Message
                 |
                 v
      JmsTemplate uses MessageProducer to send Message
                 |
                 v
      Spring completes resource handling and transactions
      per current configuration; returns or throws error
```

This is a **behavioral diagram**, not full internal source code or a guarantee of every provider optimization step.

Three critical boundaries:

1. **`MessageCreator` only creates the message.** It does not pick a broker, receive messages from consumers, or replace `MessageProducer`.
2. **`Session` is a template-supplied resource.** Do not call `session.close()`, `commit()`, or `rollback()` inside `MessageCreator`; closing and transaction management belong to the orchestration layer.
3. **`send` returning does not mean consumer-side business processing is done.** In a JMS transaction, the final outcome still depends on commit; in an asynchronous system, the message may not have been processed by a consumer yet when the send method finishes.

`JmsTemplate` handles `JMSException` and translates it into the unchecked Spring JMS exception `org.springframework.jms.JmsException`. Thus, the lambda can call APIs throwing checked `JMSException` without requiring the business method calling `send` to declare `throws JMSException`. An `IllegalArgumentException` thrown by application code itself remains a distinct application/programming error and should not be treated as a broker connection failure.

## 4. Why must the callback use the provided Session?

`jakarta.jms.Session` is the working context of JMS: it knows the provider, connection, how to create message types, and participates in the appropriate transaction/acknowledgement context. Common factory methods:

| Method on `Session` | Returned object | Scenario |
| --- | --- | --- |
| `createTextMessage(String text)` | `TextMessage` | Character strings, JSON, or XML represented as text |
| `createMapMessage()` | `MapMessage` | A set of named values using supported types |
| `createBytesMessage()` | `BytesMessage` | Byte payload following a custom protocol |
| `createStreamMessage()` | `StreamMessage` | Sequence of values read/written sequentially per JMS rules |
| `createObjectMessage(Serializable object)` | `ObjectMessage` | Serializable Java object; requires weighing compatibility and deserialization risks |

Specifically, **`jakarta.jms.Message` is an interface**, so it cannot be instantiated via `new Message()`. Never open a second `Connection`/`Session` inside the callback and return a message from a different context; doing so breaks `JmsTemplate`'s resource/transaction management and can cause provider-specific errors.

`Session` is also **not safe for concurrent access from multiple threads** under Jakarta Messaging rules. Do not store `Session` in a `static` field, singleton, or cache, do not pass it to a `CompletableFuture`/`Executor`, and do not reuse it after the callback ends. If you need to send asynchronously from another task, have that task call `JmsTemplate.send(...)` itself so Spring supplies an appropriate session for that send.

A configured `JmsTemplate` can be shared across services. That rule **does not mean** a specific `Session` instance may be used concurrently across threads.

## 5. Complete example with Spring Boot 3.x and Java 17+

Scenario: the broker already has a queue `orders.in`. When a user places an order, the producer sends the order ID as a `TextMessage`, attaching `eventType`, schema version, and correlation ID.

The example requires a Spring Boot 3.x application using Java 17+ and a **running, reachable ActiveMQ Artemis broker with the `orders.in` queue**. The configuration applies to a Gradle Spring Boot project, not a standalone Java SE program compiled only with `javac`.

### 5.1. Dependencies

Add to `build.gradle` of the Spring Boot project (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The project must already have the corresponding Spring Boot plugin and dependency management applied. The Artemis starter provides JMS integration; do not add `javax.jms` dependencies manually. Spring Framework 6 / Boot 3 uses the **`jakarta.jms`** namespace.

### 5.2. Connection and destination configuration

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"

app:
  jms:
    orders:
      input: "${JMS_ORDERS_QUEUE:orders.in}"
```

The environment variables `JMS_USER` and `JMS_PASSWORD` must be set for the broker; `JMS_BROKER_URL` and `JMS_ORDERS_QUEUE` have defaults for practice. Never hardcode real credentials in source code. The queue name must match a broker-managed resource; this configuration **does not guarantee the physical queue is created**.

### 5.3. Startup class

File `src/main/java/demo/jms/DemoApplication.java`:

```java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

A producer using only `JmsTemplate` does not need `@EnableJms`. That annotation is for `@JmsListener` receiving infrastructure when the application has listeners.

### 5.4. Producer using MessageCreator

File `src/main/java/demo/jms/OrderPublisher.java`:

```java
package demo.jms;

import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private final JmsTemplate jmsTemplate;
    private final String destinationName;

    public OrderPublisher(
            JmsTemplate jmsTemplate,
            @Value("${app.jms.orders.input}") String destinationName) {
        this.jmsTemplate = jmsTemplate;
        this.destinationName = destinationName;
    }

    public void publishOrderCreated(String orderId, String correlationId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (correlationId == null || correlationId.isBlank()) {
            throw new IllegalArgumentException("correlationId must not be blank");
        }

        jmsTemplate.send(destinationName, session -> {
            TextMessage message = session.createTextMessage(orderId);
            message.setStringProperty("eventType", "ORDER_CREATED");
            message.setIntProperty("schemaVersion", 1);
            message.setJMSCorrelationID(correlationId);
            return message;
        });
    }
}
```

Step-by-step analysis:

1. `OrderPublisher` receives `JmsTemplate` and the queue name via constructor injection; it does not create connections or sessions itself.
2. `publishOrderCreated(...)` validates input **before calling `send`**, avoiding broker operations for invalid requests.
3. The lambda's `session` parameter is **supplied by `JmsTemplate` at send time**.
4. `session.createTextMessage(orderId)` creates a message whose body is the order ID. `setStringProperty` and `setIntProperty` add strongly typed application properties.
5. `setJMSCorrelationID(correlationId)` sets the standard JMS header for correlation. This is an application-chosen ID, such as `corr-1001`; do not start it with the provider-generated message ID prefix `ID:`.
6. `return message` hands the `TextMessage` back to the template for sending. **You do not need and should not create a `MessageProducer` inside this callback.**

When a consumer reads the JMS message, it can retrieve `getText()` from `TextMessage`, `getStringProperty("eventType")`, `getIntProperty("schemaVersion")`, and `getJMSCorrelationID()`. These APIs differ from manually encoding all metadata inside a JSON body.

### 5.5. Controlled test run

Add a runner that only activates when the `demo` profile is enabled, in `src/main/java/demo/jms/DemoSendRunner.java`:

```java
package demo.jms;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("demo")
public class DemoSendRunner implements ApplicationRunner {
    private final OrderPublisher publisher;

    public DemoSendRunner(OrderPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        publisher.publishOrderCreated("ORDER-1001", "corr-1001");
        System.out.println("Called JMS send for ORDER-1001");
    }
}
```

Once the broker, queue, and credentials are ready, in a shell with the corresponding environment variables set, run:

```bash
./gradlew bootRun --args='--spring.profiles.active=demo'
```

If `send` completes without throwing an exception, the runner prints the **application** line:

```text
Called JMS send for ORDER-1001
```

That is not the entire stdout of Spring Boot. There is no guarantee a consumer has processed the message before this line prints. Check queue metrics, a message browser, or a test consumer to confirm the `ORDER-1001` payload and all three metadata fields were set. If the broker is unavailable or lacks permissions, the send operation may fail and that line **will not appear**.

The runner sends one message on every startup under the `demo` profile. Never enable this profile in production.

## 6. Other Message types with the same callback

### 6.1. Creating a MapMessage

When both sides agree to use JMS `MapMessage`, the callback can return this type:

```java
jmsTemplate.send(destinationName, session -> {
    jakarta.jms.MapMessage message = session.createMapMessage();
    message.setString("orderId", "ORDER-1001");
    message.setInt("quantity", 2);
    message.setStringProperty("eventType", "ORDER_CREATED");
    return message;
});
```

This is an illustrative snippet **inside a class that has `jmsTemplate` and `destinationName`**. The `orderId`/`quantity` fields belong to the **`MapMessage` body**; `eventType` is a **message property**, not in the same data region. The consumer must expect the right message type.

### 6.2. Creating a BytesMessage

```java
byte[] payload = "ORDER-1001"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

jmsTemplate.send(destinationName, session -> {
    jakarta.jms.BytesMessage message = session.createBytesMessage();
    message.writeBytes(payload);
    message.setStringProperty("contentType", "text/plain; charset=utf-8");
    return message;
});
```

The receiving application must agree on how to decode the bytes. The `contentType` property in this example is an **application convention**, not something JMS automatically interprets or converts from bytes to text.

### 6.3. Setting headers and properties vs. body

- **Body** is the primary payload, e.g. `ORDER-1001` in a `TextMessage`.
- **JMS standard headers** are metadata defined by the specification, e.g. `JMSCorrelationID`, `JMSReplyTo`, `JMSType`.
- **Application properties** are application-defined name/value pairs, e.g. `eventType`, `schemaVersion`; they can be read by consumers or used in JMS selectors.

`JMSMessageID` is normally assigned by the provider during send; do not treat it as an ID you proactively assign inside the callback. Producer QoS parameters such as `deliveryMode`, `priority`, and `timeToLive` should be configured through `JmsTemplate`/`MessageProducer` mechanisms. Merely calling setters on certain `Message` headers is not equivalent to configuring send-time QoS policies. For example, to instruct the template to use `setTimeToLive(...)`, you must also check `setExplicitQosEnabled(true)` and broker policies.

## 7. When to choose send, convertAndSend, or another callback?

| Mechanism | Entry point | Use when |
| --- | --- | --- |
| `send(String, MessageCreator)` | Callback receives `Session` and returns `Message` | You need explicit control over JMS message type, body structure, headers/properties |
| `convertAndSend(String, Object)` | Application object, routed through `MessageConverter` | You want Spring to convert `String`, `byte[]`, `Map`, or objects via the configured converter |
| `convertAndSend(String, Object, MessagePostProcessor)` | Converter creates message first, processor modifies it afterward | You only need to add headers/properties after the body has been converted |
| `execute(SessionCallback<T>)` | Callback works directly with `Session` and returns a result | You need multiple custom JMS operations beyond a single message |
| `execute(ProducerCallback<T>)` | Callback receives both `Session` and `MessageProducer` | You need low-level producer logic controlling multiple sends directly |

**Simple functionally equivalent examples:**

```java
// MessageCreator: you use Session directly to create TextMessage.
jmsTemplate.send("orders.in", session ->
        session.createTextMessage("ORDER-1001"));

// MessageConverter: Spring converts String to TextMessage
// when using the default SimpleMessageConverter.
jmsTemplate.convertAndSend("orders.in", "ORDER-1001");

// MessagePostProcessor: convert body first, add property afterward.
jmsTemplate.convertAndSend(
        "orders.in",
        "ORDER-1001",
        message -> {
            message.setStringProperty("eventType", "ORDER_CREATED");
            return message;
        });
```

The snippet above illustrates three call styles inside a method that has `jmsTemplate`. For `String`, the default `SimpleMessageConverter` typically creates a `TextMessage`; if the application replaces `MessageConverter`, the result depends on that converter.

Choose `MessageCreator` when you **truly need to control JMS Message creation using `Session`**. If you only need to attach a few properties to a message already produced in the right type by a converter, `MessagePostProcessor` is usually cleaner. `MessagePostProcessor` receives `Message`, **not `Session`**, so do not try to use it to call `session.createMapMessage()`.

Overloads of `JmsTemplate.send`:

```java
send(MessageCreator creator);                       // default destination
send(String destinationName, MessageCreator creator); // destination name
send(Destination destination, MessageCreator creator); // destination object
```

These are abbreviated signatures for reading, not a standalone class. The destination-less overload only works when the template has `defaultDestination` or `defaultDestinationName` set. A `String` name is mapped via `DestinationResolver`; depending on configuration, it can be a dynamic destination name or a JNDI lookup name.

## 8. Lifecycle, transactions, errors, and anti-patterns

### 8.1. Session is a scoped resource, not data to retain

Wrong:

```java
// ANTI-PATTERN: do not store Session from callback for use outside its lifecycle.
private jakarta.jms.Session storedSession;

void brokenSend() {
    jmsTemplate.send("orders.in", session -> {
        storedSession = session; // Wrong: retaining Spring-managed resource.
        return session.createTextMessage("hello");
    });
}
```

This is only an anti-pattern snippet in a hypothetical class. Once `send` returns, `storedSession` is no longer a resource the application is permitted to use arbitrarily; if the session is transaction-bound, its lifecycle is also governed by the transaction manager. Do not use `Session` on another thread or close the session inside the callback.

Right: keep **business data** outside the callback and let each `jmsTemplate.send(...)` call obtain an appropriate session at execution time.

### 8.2. The callback does not commit or roll back on its own

When JMS transactions are disabled, sending uses the corresponding session/provider configuration. If the application uses `JmsTransactionManager` or a suitable transaction coordinator, `JmsTemplate` can participate in a transaction-bound session; messages are then subject to commit/rollback. Therefore:

- Do not call `session.commit()`/`rollback()` directly inside `MessageCreator`.
- `@Transactional` only has meaning under the **transaction manager actually in effect**; never assume one annotation makes database and broker operations atomic.
- If you need cross-system DB + JMS consistency, design a transaction/outbox pattern or coordination mechanism per system requirements; that is a separate problem from creating a message in a callback.

### 8.3. Checked exceptions inside the callback

`Session.createTextMessage(...)` and setters on JMS messages can throw `JMSException`; the interface already declares `throws JMSException`. In this lambda:

```java
jmsTemplate.send("orders.in", session -> {
    TextMessage message = session.createTextMessage("ORDER-1001");
    message.setStringProperty("eventType", "ORDER_CREATED");
    return message;
});
```

you do not need to catch `JMSException` manually just to compile. When `send` runs through `JmsTemplate`, Spring translates eligible JMS errors into unchecked `JmsException`. Depending on the root cause, connection, routing, permission, converter, or application exceptions can also occur. Never catch broadly and silently treat the send as successful.

### 8.4. Avoid work outside the callback's responsibility

Do not execute slow HTTP calls, unnecessary database queries, spawn threads, loop to send repeatedly, or call `session.createProducer()` inside `MessageCreator` just to build one message. The callback should be **short, deterministic, and focused solely on creating the message**; actual sending is handled by the template. If multiple `Session`/`MessageProducer` operations are needed, use the appropriate callback level and manage transactions explicitly.

### 8.5. Returning from the callback does not mean the message is sent

`return message` finishes the message-*creation* step. `JmsTemplate` still has to send it via the producer and provider. A failure after the callback returns can still cause `send` to fail. Likewise, if the send occurs inside an uncommitted transaction, do not consider the message permanently present on the broker simply because the callback finished building it.

## 9. Testing that MessageCreator uses the provided Session

A unit test can capture the `MessageCreator` passed to `JmsTemplate.send`, invoke the callback itself with a mocked `Session`, and verify that exact session was used to create the message. No broker is needed for this test; at the same time, understand that **this test only verifies message-creation logic, not an actual JMS send**.

File `src/test/java/demo/jms/OrderPublisherTest.java`:

```java
package demo.jms;

import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.MessageCreator;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderPublisherTest {

    @Mock
    JmsTemplate jmsTemplate;

    @Mock
    Session session;

    @Mock
    TextMessage textMessage;

    @Test
    void callbackCreatesMessageUsingProvidedSession() throws Exception {
        OrderPublisher publisher =
                new OrderPublisher(jmsTemplate, "orders.in");

        publisher.publishOrderCreated("ORDER-1001", "corr-1001");

        ArgumentCaptor<MessageCreator> captor =
                ArgumentCaptor.forClass(MessageCreator.class);
        verify(jmsTemplate).send(eq("orders.in"), captor.capture());

        when(session.createTextMessage("ORDER-1001"))
                .thenReturn(textMessage);

        Message result = captor.getValue().createMessage(session);

        assertSame(textMessage, result);
        verify(session).createTextMessage("ORDER-1001");
        verify(textMessage).setStringProperty("eventType", "ORDER_CREATED");
        verify(textMessage).setIntProperty("schemaVersion", 1);
        verify(textMessage).setJMSCorrelationID("corr-1001");
    }
}
```

Run:

```bash
./gradlew test --tests demo.jms.OrderPublisherTest
```

**Expected result:** Gradle reports `BUILD SUCCESSFUL` if assertions pass and the project has valid test dependencies. No fixed stdout is guaranteed across all Gradle/JUnit versions since logs depend on configuration. `jmsTemplate` is mocked so no message is sent; the test itself invokes `createMessage(session)` on the captured callback. For integration testing, a real broker or suitable JMS test environment is required to verify send/receive end-to-end.

Benefits of this test: it catches mistakes such as hardcoding the wrong queue, forgetting properties, setting the wrong correlation ID, building the wrong payload, or failing to use the session supplied to the callback. It does not replace testing broker compatibility, transactions, or consumers.

## 10. Common mistakes

| Symptom / code pattern | Cause | Fix |
| --- | --- | --- |
| Unsure where `session` comes from in the lambda | Confusing a callback with a method you invoke directly | `JmsTemplate` invokes `createMessage(Session)` and supplies the session |
| Trying to pass `Session` into `jmsTemplate.send(...)` | Misreading the API signature | Pass a `MessageCreator`; receive `Session` as the lambda parameter |
| Using `new TextMessage(...)` | JMS messages are interfaces/provider objects | Call `session.createTextMessage(...)` |
| Calling `session.close()` or `commit()` inside the callback | Interfering with Spring-managed resources/transactions | Let the template/transaction manager coordinate |
| Storing `Session` in a field and using it on another thread | Session is not thread-safe and has a bounded lifecycle | Use the session only inside the callback; each thread/operation calls the template separately |
| Callback returns `null` | Failed to produce a valid JMS message to send | Always return a properly created `Message` or throw an exception |
| Message has the right body but lacks headers/properties | Used `convertAndSend` without post-processing, or forgot setters | Choose `MessageCreator` or `MessagePostProcessor` as needed |
| Only setting `JMSPriority` on the message and expecting QoS to apply | Confusing message metadata with producer send parameters | Configure `JmsTemplate` QoS and check `explicitQosEnabled` |
| Thinking `JMSException` must be caught in the lambda | Overlooking `MessageCreator` signature | The interface already declares `throws JMSException`; the template handles and translates it |
| `send` succeeds without error yet consumer hasn't processed | Confusing send with asynchronous business processing | Monitor the broker and consumer/acknowledgement separately |
| Wrong queue name or missing permissions | Broker/destination issue outside the callback | Verify broker URL, destination name, queue/topic type, and ACLs |

## 11. Self-check questions

1. In `jmsTemplate.send("orders.in", session -> session.createTextMessage("OK"))`, who creates and supplies `session`? Why don't you call `new Session()`?
2. Why does `return message` only complete the callback and is not enough to assert that the consumer has processed it?
3. Given a `String` where you only need to attach an `eventType` property, would you choose `MessageCreator` or `MessagePostProcessor`? Explain.
4. Why does the mocked-`Session` unit test in section 9 prove the callback uses the right factory, yet not prove the queue exists on the broker?
5. Which `Session` operations must not appear inside `MessageCreator`, and how does a transaction manager affect them?

**Remember:** `MessageCreator` is the code your application provides to *create a message*; `Session` is the JMS resource passed into the callback by `JmsTemplate`. Create the message using that exact session, return it to the template, and let the template handle sending and resource management.

### References

- Spring Framework 6.2 — Using `JmsTemplate`: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Sending a Message and `MessageCreator`: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework 6.2 — `MessageCreator` API: https://www.javadoc.io/static/org.springframework/spring-jms/6.2.13/org/springframework/jms/core/MessageCreator.html
- Jakarta Messaging 3.1 — `Session`, threading, and message headers: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
