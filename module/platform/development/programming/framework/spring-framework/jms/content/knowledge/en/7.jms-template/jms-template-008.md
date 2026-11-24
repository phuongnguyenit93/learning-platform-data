# SessionCallback and ProducerCallback for Custom Operations with JmsTemplate

## 1. Why are callbacks needed when you already have JmsTemplate?

In Spring Framework JMS, JmsTemplate provides convenient methods such as convertAndSend(...), send(...), receive(...), receiveAndConvert(...), and sendAndReceive(...). For a single message to send, these methods are usually enough: Spring creates/obtains the JMS Connection and Session, converts the body, creates the producer/consumer, calls the JMS API, and cleans up resources.

However, there are situations where you need **multiple operations on the same JMS Session** or need to customize MessageProducer directly:

- Sending two messages to two different Queues using the same Session, potentially within a properly managed JMS transaction.
- Creating multiple TextMessage/MapMessage instances with custom headers and properties, then sending them sequentially through one MessageProducer.
- Setting different delivery mode, priority, and time-to-live values per send, instead of applying a single shared configuration.
- Creating a QueueBrowser or MessageConsumer with a selector for a specialized JMS operation.
- Extracting message metadata directly within the Session context before JmsTemplate releases resources.

Two callbacks are designed by Spring for this need:

1. **SessionCallback<T>**: directly provides jakarta.jms.Session, allowing Session-level operations.
2. **ProducerCallback<T>**: provides both jakarta.jms.Session and jakarta.jms.MessageProducer, convenient when operations revolve around sending multiple messages.

Both are executed via **JmsTemplate.execute(...)**. The callback runs **synchronously on the calling thread**; it does not spawn a background worker and does not automatically make statements inside the callback an atomic transaction.

## 2. Where do they fit in Spring JMS architecture?

~~~mermaid
flowchart TD
    A["Application Service"] --> B{"JMS operation"}
    B -->|Simple send| C["convertAndSend / send"]
    B -->|Simple receive| D["receive / receiveAndConvert"]
    B -->|Multi-step, needs Session| E["execute(SessionCallback)"]
    B -->|Customize MessageProducer| F["execute(ProducerCallback)"]
    C --> G["JmsTemplate"]
    D --> G
    E --> G
    F --> G
    G --> H["ConnectionFactory / Session"]
    H --> I["JMS Provider / Broker"]
~~~

JmsTemplate acts as a **template method**: it sets up the resource context, invokes the custom code, and cleans up resources upon return or error.

With callbacks, the application must understand ownership boundaries:

| Resource | Typical owner | Responsibility inside the callback |
| --- | --- | --- |
| Connection | JmsTemplate/ConnectionFactory/transaction manager | Do not manually close or retain after the callback ends. |
| Passed-in Session | JmsTemplate or Spring transaction manager | Use sequentially inside the callback; do not close manually or pass to another thread. |
| MessageProducer passed to ProducerCallback | JmsTemplate | Do not close manually; JmsTemplate closes it when the callback ends. |
| MessageProducer created manually in SessionCallback | Application code | Must close via try-with-resources or finally. |
| MessageConsumer/QueueBrowser created manually | Application code | Close created resources, even when the callback throws. |
| Returned Message/value | Application code | Return independent results like String, DTO, or count; avoid returning JMS handles requiring a live Session. |

When a Session is bound to a thread by a Spring transaction manager, “cleaning up resources” may mean returning/unbinding per transaction lifecycle rather than closing physically right away. The callback **does not own** the Connection or Session to close them at will.

## 3. API signatures to know

### 3.1. SessionCallback<T>

In package **org.springframework.jms.core**:

~~~java
@FunctionalInterface
public interface SessionCallback<T> {
    T doInJms(jakarta.jms.Session session)
            throws jakarta.jms.JMSException;
}
~~~

This is an abbreviated signature for explanation; the actual interface is already provided in spring-jms. T is the result type returned by the callback; it can be String, Integer, a business record, or Void/null if only side effects are needed.

Two useful JmsTemplate overloads:

~~~java
<T> T execute(SessionCallback<T> action);

<T> T execute(SessionCallback<T> action, boolean startConnection);
~~~

By default, execute(action) **does not start the JMS Connection just to run the callback**. It fits sending messages or Session operations that do not require incoming delivery. If the callback creates a MessageConsumer itself and calls receive(...), you typically must use execute(action, true), or use JmsTemplate's receive()/receiveSelected() directly (recommended for normal receiving).

### 3.2. ProducerCallback<T>

In the same package:

~~~java
@FunctionalInterface
public interface ProducerCallback<T> {
    T doInJms(
            jakarta.jms.Session session,
            jakarta.jms.MessageProducer producer)
            throws jakarta.jms.JMSException;
}
~~~

Corresponding overloads on JmsTemplate:

~~~java
<T> T execute(ProducerCallback<T> action);

<T> T execute(
        jakarta.jms.Destination destination,
        ProducerCallback<T> action);

<T> T execute(
        String destinationName,
        ProducerCallback<T> action);
~~~

These are illustrative API signatures, not a standalone runnable Java file.

- Passing **String destinationName**: JmsTemplate uses DestinationResolver to resolve it into a Destination and creates a producer bound to that target.
- Passing **Destination object**: directly uses the supplied Destination.
- Omitting destination: uses the default destination if configured; if no default exists, JmsTemplate may create an unbound producer (anonymous producer), and inside the callback you must send using the overload that takes a Destination parameter.
- Inside the callback, the producer has already been created on the right Session; Spring closes the producer after the callback finishes.

Do not confuse ProducerCallback with MessageCreator: ProducerCallback **sends messages itself**, whereas MessageCreator primarily **creates a Message**, and JmsTemplate.send(...) performs the send.

### 3.3. Lambdas keep code concise

~~~java
Integer count = jmsTemplate.execute(
        (SessionCallback<Integer>) session -> {
            // Work with session.
            return 2;
        });

Integer sent = jmsTemplate.execute(
        "orders.requests",
        (session, producer) -> {
            // Work with session and producer.
            return 2;
        });
~~~

These are snippets where jmsTemplate is already injected in a Spring application. Casting to SessionCallback<Integer> in the example helps learners see clearly which overload is chosen, though a single-parameter lambda is often enough for Java type inference.

## 4. Execution flow and resource management

### 4.1. SessionCallback

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant J as JmsTemplate
    participant CF as ConnectionFactory
    participant S as JMS Session
    App->>J: execute(SessionCallback)
    J->>CF: Obtain/create appropriate Connection and Session
    J->>S: doInJms(session)
    S-->>J: Result T or JMSException
    J->>J: Clean up Session/Connection by ownership
    J-->>App: T or Spring JmsException
~~~

JmsTemplate guarantees the error-handling and resource-cleanup path within the scope it manages. If the callback throws **jakarta.jms.JMSException**, JmsTemplate translates it into an appropriate unchecked **org.springframework.jms.JmsException** before surfacing it to the call site. Application runtime exceptions are also never turned into success; resources are still cleaned up in the finally branch.

### 4.2. ProducerCallback

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant J as JmsTemplate
    participant S as JMS Session
    participant P as MessageProducer
    App->>J: execute(name, ProducerCallback)
    J->>S: resolve Destination
    J->>S: createProducer(destination)
    S-->>J: producer
    J->>App: doInJms(session, producer)
    App->>P: send(message 1)
    App->>P: send(message 2)
    App-->>J: return count
    J->>P: close()
    J->>J: Clean up Session/Connection
    J-->>App: count
~~~

JmsTemplate releases the producer even when the callback throws an exception. Therefore, never return the producer outside, put the producer into a thread pool, close the framework-supplied Session, or expect the producer to remain valid after execute(...).

## 5. SessionCallback: custom Session-level operations

### 5.1. Sending multiple messages to two queues

A SessionCallback can create multiple Destinations and producers, then send sequentially:

~~~java
Integer sent = jmsTemplate.execute(
        (SessionCallback<Integer>) session -> {
            Queue orders = session.createQueue("orders.requests");
            Queue audit = session.createQueue("audit.events");

            try (MessageProducer orderProducer =
                         session.createProducer(orders);
                 MessageProducer auditProducer =
                         session.createProducer(audit)) {

                TextMessage order =
                        session.createTextMessage("ORDER-42");
                order.setStringProperty("BusinessId", "order-42");
                orderProducer.send(order);

                TextMessage event =
                        session.createTextMessage("AUDIT-42");
                event.setStringProperty("BusinessId", "order-42");
                auditProducer.send(event);
            }
            return 2;
        });
~~~

**This snippet requires jmsTemplate and imports for jakarta.jms.Queue, MessageProducer, TextMessage, and Spring's SessionCallback**, so it is not a standalone runnable file. A complete program is provided in section 9.

What is happening:

1. The template provides a Session; there is no need to call ConnectionFactory.createConnection() manually.
2. The callback creates Queue objects and two producers in the **same Session**.
3. Each message is created via session.createTextMessage(...), with a property attached for business tracing.
4. Both manually created producers are closed via try-with-resources.
5. The callback returns Integer=2, meaning two send calls completed normally inside the callback.

**Important:** simply because two sends share the same Session does not mean they automatically commit together. Atomicity depends on whether the Session is transacted and how the transaction is committed/rolled back. With a non-transacted Session, the first send can succeed while the second fails. Section 8 covers transactions.

### 5.2. Using SessionCallback to create specialized messages

SessionCallback gives access to direct JMS APIs such as createBytesMessage(), createMapMessage(), createObjectMessage(), createTemporaryQueue(), createConsumer(...), and createBrowser(...).

Example MapMessage operation:

~~~java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    Queue queue = session.createQueue("inventory.updates");

    try (MessageProducer producer = session.createProducer(queue)) {
        MapMessage message = session.createMapMessage();
        message.setString("sku", "SKU-42");
        message.setInt("quantity", 5);
        message.setStringProperty("SourceSystem", "warehouse");
        producer.send(message);
    }
    return null;
});
~~~

This is a snippet requiring imports for jakarta.jms.MapMessage, Queue, and MessageProducer. MapMessage is a JMS message format; it differs from a Java Map converted by MessageConverter and also differs from message properties. This lesson uses it to illustrate Session access in a callback without diving deep into every JMS Message type.

### 5.3. When does SessionCallback make more sense than standard methods?

SessionCallback is helpful when an operation needs **multiple JMS calls sharing a Session**, needs custom destination/consumer/producer creation, or needs control over lower-level APIs. If only sending a single String:

~~~java
jmsTemplate.convertAndSend("orders.requests", "ORDER-42");
~~~

the convenience method is easier to read and carries less resource-management risk. Do not turn every simple send into a callback just to feel “more powerful”; broader API power also increases responsibility.

## 6. ProducerCallback: complex operations with MessageProducer

### 6.1. Reusing one producer across multiple sends

ProducerCallback provides a ready-made producer, so your code does not have to create/close it:

~~~java
Integer sent = jmsTemplate.execute(
        "orders.outbound",
        (session, producer) -> {
            TextMessage first =
                    session.createTextMessage("ORDER-101");
            first.setStringProperty("BatchId", "B-7");

            TextMessage second =
                    session.createTextMessage("ORDER-102");
            second.setStringProperty("BatchId", "B-7");

            producer.send(first);
            producer.send(second);
            return 2;
        });
~~~

This is a snippet inside a Spring bean. If the broker accepts both sends and the Session is non-transacted, the application receives 2. However, the value 2 is **the count of send operations executed in the callback**; it does not prove downstream business processing succeeded or messages were durably persisted forever.

**Do not call producer.close()** inside the callback. Spring closes the producer in finally when execute() finishes.

### 6.2. Setting per-message QoS

JMS MessageProducer has an overload for delivery mode, priority, and time-to-live:

~~~java
producer.send(
        message,
        DeliveryMode.PERSISTENT, // Durable delivery mode per the JMS contract.
        7,                       // Priority 0..9.
        60_000L);                // TTL 60 seconds.
~~~

This is a snippet; producer and message must already exist. When each message needs different QoS:

~~~java
jmsTemplate.execute(
        "reports.jobs",
        (session, producer) -> {
            TextMessage urgent =
                    session.createTextMessage("URGENT-1");
            urgent.setStringProperty("JobClass", "urgent");
            producer.send(
                    urgent,
                    DeliveryMode.PERSISTENT,
                    8,
                    120_000L);

            TextMessage routine =
                    session.createTextMessage("NORMAL-2");
            routine.setStringProperty("JobClass", "routine");
            producer.send(
                    routine,
                    DeliveryMode.NON_PERSISTENT,
                    4,
                    30_000L);

            return null;
        });
~~~

Requires imports for jakarta.jms.DeliveryMode and TextMessage. Both messages share one MessageProducer, yet each send has different QoS.

**Note:** when calling producer.send(...) directly inside ProducerCallback, your code controls the send directly. Internal JmsTemplate.send(...) paths have their own logic for explicit QoS, delivery delay, and local commit. Do not assume template settings will automatically reapply all QoS or call commit on behalf of custom callback sends. If you need a shared QoS policy, consider using JmsTemplate.send/convertAndSend with matching configuration, or specify QoS directly in producer.send as shown above.

### 6.3. Destination-bound producer vs. anonymous producer

If calling:

~~~java
jmsTemplate.execute("orders.queue", (session, producer) -> {
    producer.send(session.createTextMessage("A"));
    return null;
});
~~~

Spring has resolved "orders.queue" and created a producer bound to that Destination. Conversely, if using an unbound producer, JMS lets you send via the overload taking a Destination parameter:

~~~java
jmsTemplate.execute((ProducerCallback<Void>) (session, producer) -> {
    Queue first = session.createQueue("queue.first");
    Queue second = session.createQueue("queue.second");

    producer.send(first, session.createTextMessage("A"));
    producer.send(second, session.createTextMessage("B"));
    return null;
});
~~~

The second snippet relies on JmsTemplate.execute(ProducerCallback) having no default destination or creating an anonymous producer. If the template has a default destination, the producer will be bound to it and cannot arbitrarily use the destination-taking overload in all providers. When aiming to send to multiple destinations from one producer, **explicitly configure an unbound producer** or use SessionCallback with session.createProducer(null); do not rely on unchecked default-destination state.

## 7. Receiving messages in SessionCallback: startConnection and timeout

### 7.1. Why default execute(action) is not enough

A newly created classic JMS Connection **has not started incoming delivery yet**. Producers can send without starting, but consumer.receive(...) requires a started Connection to receive delivered messages.

JmsTemplate provides the overload:

~~~java
<T> T execute(SessionCallback<T> action, boolean startConnection);
~~~

When the callback creates a MessageConsumer itself, pass startConnection=true so JmsTemplate enables receiving within the resource lifecycle it manages.

~~~java
String received = jmsTemplate.execute(
        (SessionCallback<String>) session -> {
            Queue queue = session.createQueue("reports.replies");

            try (MessageConsumer consumer =
                         session.createConsumer(
                                 queue,
                                 "Region = 'VN'")) {

                Message message = consumer.receive(3_000L);
                if (message == null) {
                    return null;
                }
                if (message instanceof TextMessage text) {
                    return text.getText();
                }
                throw new JMSException("Expected TextMessage");
            }
        },
        true);
~~~

This is a selector-based receive snippet; import jakarta.jms.MessageConsumer, Queue, Message, TextMessage, JMSException. The timeout is 3 seconds. If no matching message exists, the result is null; do not treat null as a JMS error by default.

**Why return String instead of MessageConsumer?** The consumer created by the callback is closed before the callback returns. Returning that handle for later use will fail. Similarly, never return the Session to the caller to keep using after execute(...).

### 7.2. Preferred path for simple receives

If you only need a single message or a standard selector, JmsTemplate already provides:

~~~java
Object payload =
        jmsTemplate.receiveAndConvert("reports.replies");

Message message =
        jmsTemplate.receiveSelected(
                "reports.replies",
                "Region = 'VN'");
~~~

These methods handle startConnection and consumer management automatically. Setting a finite receiveTimeout is critical to avoid blocking threads indefinitely; some JMS configurations treat timeout 0 as wait forever.

### 7.3. Do not pass Session to another thread

JMS Sessions follow a sequential usage model; JmsTemplate only provides a valid Session **for the duration of the callback**. Do not do the following:

~~~java
// Wrong for lifecycle and thread-safety:
jmsTemplate.execute((SessionCallback<Void>) session -> {
    executor.submit(() -> {
        // Using session after the callback has returned is wrong.
    });
    return null;
});
~~~

This is an anti-pattern, not code to run. If asynchronous processing is needed, enqueue a job and let a separate @JmsListener/container process it. Each task manages its own resource context rather than borrowing an expired Session.

## 8. Transactions, acknowledgement, errors, and atomicity limits

### 8.1. A callback does not create a transaction by itself

Compare:

| Case | Consequence |
| --- | --- |
| Non-transacted Session (default in basic JmsTemplate config) | Two sends can succeed/fail independently; the callback does not group them into an atomic commit. |
| Application-managed transacted Session | Requires explicit commit/rollback if no transaction manager coordinates. |
| Session bound to JmsTransactionManager | Spring manages commit/rollback when the transaction boundary ends; the callback shares the thread-bound Session. |
| Properly configured JTA/XA participation | Can include JMS resources in a distributed transaction; requires XA-capable provider and transaction manager. |
| Separate DB transaction at the same time | Not atomic with JMS by default; requires an appropriate consistency architecture (outbox, idempotency, or XA/JTA if truly needed). |

A critical point for SessionCallback and ProducerCallback is **commit responsibility**. In JmsTemplate, convenience send/receive methods have built-in commit/ack logic for local transacted sessions; **custom execute callbacks do not automatically inherit those steps**. If sessionTransacted is enabled without a Spring transaction manager, you must clearly understand who commits/rolls back; otherwise closing a Session with an uncommitted transaction can leave messages unrecorded.

Never call session.commit() or session.rollback() on a Session participating in a Spring-managed transaction. That breaks the commit/rollback boundary owned by the transaction manager.

### 8.2. Example using a transaction manager for multiple sends

When both messages target **one JMS ConnectionFactory**, you can configure JmsTransactionManager and use TransactionTemplate to guard a group of JMS operations:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.connection.JmsTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

// Snippet inside an application that already has connectionFactory and jmsTemplate.
JmsTransactionManager txManager =
        new JmsTransactionManager(connectionFactory);
TransactionTemplate tx = new TransactionTemplate(txManager);

tx.executeWithoutResult(status -> {
    jmsTemplate.execute(
            (SessionCallback<Void>) session -> {
                Queue a = session.createQueue("orders.outbound");
                Queue b = session.createQueue("audit.outbound");

                try (MessageProducer pa = session.createProducer(a);
                     MessageProducer pb = session.createProducer(b)) {
                    pa.send(session.createTextMessage("ORDER-42"));
                    pb.send(session.createTextMessage("AUDIT-42"));
                }
                return null;
            });
});
~~~

This is a **snippet**, not a standalone project. For transaction participation to work, JmsTemplate must use the **exact same ConnectionFactory instance** bound by the transaction manager, and the environment must permit transacted Sessions. On transaction success, the manager commits after the callback; when an eligible error exits the transaction, the manager rolls back. If a transaction manages only JMS, it does not simultaneously commit/roll back a JDBC database on a separate DB resource.

**Do not instantiate a new JmsTransactionManager per request** as in the local-variable illustration above. In real deployments, declare a managed transaction manager bean in configuration and inject it where needed.

### 8.3. Runtime exceptions and JMSException

A callback can throw checked jakarta.jms.JMSException. JmsTemplate converts this checked exception into an unchecked Spring JmsException hierarchy. This allows callers to handle errors at service boundaries without forcing every method to declare throws JMSException.

~~~java
try {
    Integer count =
            jmsTemplate.execute(
                    (SessionCallback<Integer>) session -> {
                        // JMS API calls that may throw JMSException.
                        return 1;
                    });
} catch (org.springframework.jms.JmsException ex) {
    // Record transport/JMS provider error; classify for retry.
}
~~~

This is a snippet. Spring JmsException does not imply every failure inside a callback is a connection error: the callback itself can throw a business RuntimeException. Never catch broadly and return "success" if messages were not properly sent.

### 8.4. Atomicity, redelivery, and idempotency

Suppose a callback sends "charge card" and "send receipt" messages:

- Without a JMS transaction: the first send can succeed while the second fails.
- With a local JMS transaction: two sends to compatible JMS resources can commit together in the same transaction; however, side effects on a database or payment service remain outside that boundary.
- If a failure happens after commit but before the sender observes success: retrying can create duplicate messages.
- If a consumer receives a message again when ack/commit fails: idempotency keys are still needed to prevent duplicate business effects.

Do not treat callbacks as a guarantee of **end-to-end exactly-once**. For complex applications, design transactional outbox, inbox/deduplication, or JTA/XA where appropriate.

## 9. Runnable project: Java 17 + Spring Boot 3.3 + Artemis

The application below runs both callback styles, then receives the exact sent messages back to prove they arrived at the right queues. The example intentionally uses a **non-transacted JMS Session** to keep the execution path simple, and later explains how to add transactions. Each run on a clean broker/queues yields deterministic stdout.

### 9.1. Environment setup

Requires JDK 17+, Maven, Docker, and TCP port 61616 free. Start a test Apache ActiveMQ Artemis instance:

~~~bash
docker run --detach --rm --name jms-callback-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Wait until the broker is ready before running the application. The default user and password artemis/artemis are for learning only; real systems require dedicated accounts and security configuration. If the broker disables queue auto-creation, declare the queues demo.callback.orders, demo.callback.audit, and demo.callback.batch and grant permissions beforehand.

Project structure:

~~~text
jms-callback-demo/
├── pom.xml
└── src/main/
    ├── java/example/jmscallback/CallbackDemoApplication.java
    └── resources/application.properties
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>jms-callback-demo</artifactId>
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

Spring Boot 3.x/Spring Framework 6.x uses **jakarta.jms.***. Avoid mixing legacy javax.jms.* dependencies into this project.

### 9.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

spring.jms.template.receive-timeout=5s
~~~

receive-timeout caps the wait time for JmsTemplate.receiveAndConvert calls, preventing the program from hanging if a message does not arrive. The sample uses queues, so pubSubDomain=true is not configured.

### 9.4. CallbackDemoApplication.java

~~~java
package example.jmscallback;

import jakarta.jms.DeliveryMode;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.SessionCallback;

@SpringBootApplication
public class CallbackDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallbackDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner run(JmsTemplate jmsTemplate) {
        return args -> {
            Integer sessionCount = jmsTemplate.execute(
                    (SessionCallback<Integer>) session -> {
                        Queue orders = session.createQueue(
                                "demo.callback.orders");
                        Queue audit = session.createQueue(
                                "demo.callback.audit");

                        // Producer created by callback: callback must close it.
                        try (MessageProducer orderProducer =
                                     session.createProducer(orders);
                             MessageProducer auditProducer =
                                     session.createProducer(audit)) {

                            TextMessage order =
                                    session.createTextMessage("ORDER-42");
                            order.setStringProperty(
                                    "BusinessId", "order-42");
                            orderProducer.send(order);

                            TextMessage event =
                                    session.createTextMessage("AUDIT-42");
                            event.setStringProperty(
                                    "BusinessId", "order-42");
                            auditProducer.send(event);
                        }
                        return 2;
                    });
            System.out.println("SessionCallback sent: " + sessionCount);

            // Producer created by JmsTemplate; Spring will close it.
            Integer producerCount = jmsTemplate.execute(
                    "demo.callback.batch",
                    (session, producer) -> {
                        TextMessage first =
                                session.createTextMessage("BATCH-1");
                        first.setStringProperty("BatchId", "batch-7");
                        producer.send(
                                first, DeliveryMode.PERSISTENT,
                                5, 60_000L);

                        TextMessage second =
                                session.createTextMessage("BATCH-2");
                        second.setStringProperty("BatchId", "batch-7");
                        producer.send(
                                second, DeliveryMode.PERSISTENT,
                                5, 60_000L);
                        return 2;
                    });
            System.out.println("ProducerCallback sent: " + producerCount);

            Object order =
                    jmsTemplate.receiveAndConvert("demo.callback.orders");
            Object audit =
                    jmsTemplate.receiveAndConvert("demo.callback.audit");
            Object firstBatch =
                    jmsTemplate.receiveAndConvert("demo.callback.batch");
            Object secondBatch =
                    jmsTemplate.receiveAndConvert("demo.callback.batch");

            System.out.println("order: " + order);
            System.out.println("audit: " + audit);
            System.out.println("batch first: " + firstBatch);
            System.out.println("batch second: " + secondBatch);
        };
    }
}
~~~

**Why is this snippet a complete example?** The Java file has main(), application.properties configures Artemis, and pom.xml includes the Spring Boot starter. No placeholder variables like session or producer are assumed outside callbacks. To run, the queues must be permitted by the broker; they are resolved through the JMS Session/Provider. Spring Boot auto-provides JmsTemplate/ConnectionFactory when the starter and broker are configured properly.

**Which lines are SessionCallback?** The first callback receives a Session, creates Queues, two producers, and two TextMessages, and sends them to two queues. Each self-created producer is closed automatically in try-with-resources.

**Which lines are ProducerCallback?** The second callback receives Session and a producer already bound to "demo.callback.batch"; the code reuses the producer to send two TextMessages and sets QoS per send. It does not close the producer because JmsTemplate owns it.

**Returned data:** each callback returns Integer=2. That describes the number of sends executed inside the callback, not persistent JMS queue depth or the number of jobs successfully processed.

### 9.5. Running

From the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

When the broker is running, queues are clean, no competing consumers exist, and all four messages are received within the timeout, the output produced by the application's System.out.println calls is:

~~~text
SessionCallback sent: 2
ProducerCallback sent: 2
order: ORDER-42
audit: AUDIT-42
batch first: BATCH-1
batch second: BATCH-2
~~~

Spring Boot/Artemis may print additional logs. On queues with backlogs from previous runs, received results may differ, so use a dedicated demo broker/queues. If the broker is not ready, permissions are denied, or receive times out, the code may throw an error or print null instead of the success output.

Stop the demo broker when done:

~~~bash
docker stop jms-callback-broker
~~~

### 9.6. What to observe in the demo?

1. **JmsTemplate manages Session**: code never opens/closes Connections manually.
2. **SessionCallback can operate across multiple destinations** within the same Session.
3. **ProducerCallback reuses MessageProducer** and avoids manual producer lifecycle management.
4. **Per-message QoS** goes into the producer.send(message, deliveryMode, priority, ttl) overload.
5. **JmsTemplate.receiveAndConvert** is the right path for simple receives; receive callbacks are unnecessary here.
6. **Sent messages are distinct**: both messages on the batch queue share the same BatchId yet have different bodies.
7. **No shared transaction** spans all four messages. To group sends into an atomic unit, see the transactions section rather than relying on code sitting in the same CommandLineRunner.

## 10. Advanced customization cases

### 10.1. Reading metadata or selecting a specific Message

If you need to extract a header/metadata from a directly received Message, SessionCallback lets you create a consumer, receive, and return a simple DTO:

~~~java
record ReceivedInfo(String messageId, String payload) {}

ReceivedInfo info = jmsTemplate.execute(
        (SessionCallback<ReceivedInfo>) session -> {
            Queue q = session.createQueue("orders.replies");
            try (MessageConsumer consumer =
                         session.createConsumer(q)) {
                Message msg = consumer.receive(2_000);
                if (msg == null) return null;

                return new ReceivedInfo(
                        msg.getJMSMessageID(),
                        msg.getBody(String.class));
            }
        },
        true);
~~~

This is a Java 17 snippet in a class with proper imports and no standalone main(). It returns a record **independent of Session**, unlike returning a MessageConsumer. For normal receive commands, consider receiveSelected(...)/receiveAndConvert(...) to benefit from JmsTemplate's timeout/ack/commit policies.

### 10.2. Sending content-customized messages

ProducerCallback lets you build the exact JMS Message type needed:

~~~java
jmsTemplate.execute(
        "inventory.queue",
        (session, producer) -> {
            MapMessage update = session.createMapMessage();
            update.setString("sku", "SKU-17");
            update.setInt("delta", 5);
            update.setJMSType("inventory.adjusted.v1");
            update.setStringProperty("Region", "VN");
            producer.send(update);
            return null;
        });
~~~

This snippet requires importing MapMessage. Remember to distinguish **MapMessage fields** inside the body from **message properties** such as Region in metadata, which can be used by JMS selectors.

### 10.3. Creating a temporary queue inside SessionCallback

~~~java
jmsTemplate.execute(
        (SessionCallback<Void>) session -> {
            TemporaryQueue replyQueue =
                    session.createTemporaryQueue();
            try {
                // Use replyQueue within the same request-reply workflow.
                // Do not return the queue handle outside to hold forever.
            } finally {
                replyQueue.delete();
            }
            return null;
        });
~~~

This is a lifecycle-illustration snippet and does not contain a full request-reply flow. Temporary destinations live only as long as the Connection; for standard request-reply, JmsTemplate.sendAndReceive(...) already provides a dedicated API and manages the temporary reply destination for you.

## 11. Comparison with MessageCreator and MessagePostProcessor

| API | What does the callback receive? | Who calls send()? | Best fit |
| --- | --- | --- | --- |
| convertAndSend(destination, Object) | Caller supplies object; JmsTemplate uses converter | JmsTemplate | A single simple message. |
| MessageCreator | Session to create Message | JmsTemplate | A single message needing custom type/body/headers. |
| MessagePostProcessor | Message after converter builds it | JmsTemplate | Adding properties/headers or adjusting metadata before send. |
| SessionCallback<T> | Session | Callback if it wants to send | Multiple API calls on the same Session; creating producer/consumer/browser. |
| ProducerCallback<T> | Session and MessageProducer | Callback | Multiple sends and per-message QoS through one producer. |
| @JmsListener | Message or payload when broker delivers | Not primarily a send API | Asynchronous receiving, processed in a listener container. |

Two cases that do not need low-level callbacks:

~~~java
// Just sending a String:
jmsTemplate.convertAndSend("orders.requests", "ORDER-42");

// A message needing a header and property:
jmsTemplate.convertAndSend(
        "orders.requests", "ORDER-42",
        message -> {
            message.setJMSType("order.created.v1");
            message.setStringProperty("Source", "api");
            return message;
        });
~~~

Whenever JmsTemplate.convertAndSend can handle the requirement, use it to keep code readable and consistently apply template-managed converter, transaction/ack/QoS settings. Only step up to execute(...) when you need APIs that convenience methods cannot express cleanly.

## 12. Safety checklist for implementation

### 12.1. Ownership and cleanup

- Sessions and Connections supplied by JmsTemplate **must not be closed manually** inside callbacks.
- The producer passed into ProducerCallback **must not be closed manually**; JmsTemplate owns it.
- Producers, consumers, and QueueBrowsers created manually inside SessionCallback must be closed explicitly, even on exceptions.
- Do not retain Sessions or producers after execute() returns; never use them across async callbacks/other threads.
- Never share a Session concurrently across multiple threads, even when ConnectionFactory uses a connection pool.

### 12.2. Transactions and errors

- Distinguish non-transacted Sessions from Spring-managed JMS transactions.
- Place transaction boundaries at the service/TransactionTemplate level, using the exact same ConnectionFactory instance for both the manager and JmsTemplate.
- Without a transaction, multiple sends in one callback are **not atomic**.
- If a callback operates directly on a local transacted Session, have an exact commit/rollback strategy; avoid closing the Session while a transaction remains open.
- Never call session.commit()/rollback() manually when the Session belongs to Spring's transaction manager.
- Never assume a JMS commit covers JDBC, HTTP calls, or third-party systems.
- Verify idempotency, retries, and DLQs whenever message resending/redelivery is possible.

### 12.3. QoS, timeout, and throughput

- Custom producer.send QoS can be specified per send if needed: delivery mode, priority, time-to-live.
- Priority is not a strict ordering guarantee across all brokers/configurations; TTL can expire messages before consumers receive them.
- Callbacks should not execute long CPU/network tasks unrelated to JMS while holding Session/Connection resources.
- When receiving manually, set a finite timeout and enable the Connection via execute(action, true).
- For continuous processing, use @JmsListener and a listener container rather than an infinite receive loop inside a synchronous SessionCallback.
- Measure send/receive latency, errors, and message counts; avoid printing or logging sensitive payloads.

## 13. Common incidents

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Callback sends only the first message | Second message failed, Session non-transacted | Account for partial sends; use a JMS transaction if atomicity is required. |
| ProducerCallback throws IllegalStateException after execute | Retained MessageProducer and used it after Spring closed it | Use the producer only inside the callback. |
| SessionCallback.receive(timeout) always returns null | Called execute(action) instead of execute(action, true), Connection not started | Use execute(action, true) or JmsTemplate.receive. |
| Receive blocks indefinitely | Used receive() or receive(0) without a limit | Set a finite positive timeout. |
| Enabled sessionTransacted and no messages appear | No transaction commit occurred for custom sends | Use JmsTransactionManager/TransactionTemplate or manage local commits explicitly. |
| @Transactional does not roll back DB and JMS together | Using a single local transaction manager | Design outbox/idempotency or XA/JTA if multi-resource atomicity is truly required. |
| TTL/priority differs from expected | Custom send went through direct producer.send without specifying QoS | Use the send overload with QoS and inspect provider config. |
| JMSException not caught | JmsTemplate translated it to unchecked Spring JmsException | Handle at the service boundary with retry/idempotency policies. |
| Callback blocks threads | Long-running logic inside callback holding Session/Connection | Move long work out and keep JMS callbacks short. |
| Exception when closing resources | Forgot cleanup for self-created producer/consumer | Use try-with-resources/finally, preserving the original exception. |
| Sent to right name yet no consumer receives | Wrong queue/topic domain, selector, broker ACL, or listener | Inspect DestinationResolver, broker, and listener configuration. |
| Wrong Session/Message cast | Mixed jakarta.jms.* with javax.jms.* | Use Jakarta JMS consistently in Spring Boot 3.x. |

## 14. Knowledge self-check

**1. What parameters does SessionCallback receive?** One jakarta.jms.Session; it creates any child resources it needs and must manage resources it creates itself.

**2. What parameters does ProducerCallback receive?** Session and MessageProducer supplied by JmsTemplate; the callback sends messages through that producer.

**3. Who closes the producer in ProducerCallback?** JmsTemplate. The callback must not retain or close the shared producer.

**4. What if you create a MessageProducer yourself inside SessionCallback?** Application code must close it in try-with-resources/finally.

**5. Does execute(SessionCallback) start the Connection for receiving by default?** No. If you need to receive manually with a consumer, call execute(action, true) or use JmsTemplate's receive methods.

**6. What does a callback return?** An application-defined value T, which can be null. Return Java results independent of cleaned-up JMS resources.

**7. Do two producer.send calls inside the same callback automatically become a transaction?** No. You need a transacted Session and commit/rollback at the proper boundary.

**8. Should you call session.commit() when JmsTransactionManager manages the Session?** No; the Spring transaction manager owns that responsibility.

**9. When should you use MessagePostProcessor instead of ProducerCallback?** When you only need to modify one Message after the converter and send via JmsTemplate, without performing multiple producer operations.

**10. Should you use a callback to run a long-lived consumer loop?** Generally no; @JmsListener/containers are designed for asynchronous processing and better lifecycle management.

### Extended exercises

1. Run the project in section 9, add a third message in ProducerCallback, and explain what the returned count means.
2. Try changing QoS between sends; inspect JMSPriority/JMSExpiration on received messages using an appropriate API/console.
3. Add another MessageProducer in SessionCallback to send to a new queue; test cleanup when intentionally throwing an exception.
4. Simulate a second-send failure with a non-transacted Session; compare queue depth with the completed send count.
5. Use JmsTransactionManager and TransactionTemplate for two sends on the same Session; intentionally throw a RuntimeException before the transaction finishes and verify rollback.
6. Create a consumer with a selector in SessionCallback, comparing execute(action, false) with execute(action, true); ensure a finite timeout.
7. Refactor a ProducerCallback that only sends a single String into convertAndSend and compare code, error handling, and extensibility.
8. Write an integration test with real Artemis to verify producer resources are released after a callback exception.

## 15. Official references

- Spring Framework 6.2 — Using Spring JMS: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Sending a Message, SessionCallback and ProducerCallback: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework 6.2 — JmsTemplate API: https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.1 — SessionCallback API: https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/jms/core/SessionCallback.html
- Spring Framework 6.1 — ProducerCallback API: https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/jms/core/ProducerCallback.html
- Jakarta Messaging 3.1 Specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Apache ActiveMQ Artemis Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
