# Acknowledgement and Transaction Responsibilities of Listener Containers in Spring JMS

## 1. The Problem: Who Decides a Message Is Done?

A **Spring Framework JMS** application commonly uses `@JmsListener` to receive messages asynchronously:

```java
@JmsListener(destination = "orders.in")
public void handle(String orderId) {
    processOrder(orderId);
}
```

The example above expresses only **business logic**. A more critical question is: when is the message **acknowledged** so the broker knows it can consider that delivery complete? If `processOrder` throws an exception, is the message redelivered? If the method both updates a database and sends a JMS response, do both operations commit together?

That is the responsibility of the **message listener container**, not just the `@JmsListener` annotation. In Spring, the container:

1. Opens/acquires connections via `jakarta.jms.ConnectionFactory`, creating or obtaining `Session` and `MessageConsumer`.
2. Receives messages from a Queue/Topic according to destination, selector, concurrency, and subscription settings.
3. Invokes the listener or adapter handling `@JmsListener`.
4. Decides **acknowledgement, commit, or rollback/recover**, based on container type, session acknowledge mode, and transaction manager.
5. Manages consumer lifecycle, connection errors, shutdown, recovery, and resource recreation.

```text
              JMS Broker
                  |
                  | dispatches a JMS Message
                  v
       Message Listener Container
       | ConnectionFactory/Session
       | acknowledgement/transaction
       | exception/recovery
       v
       @JmsListener handler
          |              |
          | succeeds     | throws exception
          v              v
    commit / ACK      rollback/recover?
          |              |
          v              v
    completes        broker may
     delivery        redeliver per policy
```

**Never confuse "method ran" with "broker acknowledged", and never confuse "broker acknowledged" with "database committed".** Those three milestones coincide only with a consistent transactional design.

## 2. Four Concepts to Distinguish

| Concept | Who is primarily responsible? | Meaning |
| --- | --- | --- |
| **Delivery** | JMS provider/broker and consumer | Message is delivered to a consumer/session. |
| **Acknowledgment (ACK)** | JMS Session + listener container per mode | Confirms receipt/completion of a delivery in non-transacted mode. |
| **JMS transaction** | Locally transacted Session or transaction manager | Groups JMS operations with commit/rollback. |
| **Business transaction** | Service, database, external systems | Updates business state, potentially completely independent of JMS. |

Order-processing example:

```text
T0   Broker delivers ORDER-42 to container
T1   Listener reads content and starts processing
T2   UPDATE orders SET status='PAID' ...
T3   Database COMMIT
T4   Container/JMS COMMIT or ACK
```

If the JVM crashes between **T3** and **T4**, the DB has changed yet JMS may redeliver the message because it never saw commit/ACK. If the handler is not idempotent, the order may be processed or charged twice. **This is not a Spring-specific bug**; it is the inconsistency window between two independent resources.

Conversely, in `AUTO_ACKNOWLEDGE` on certain containers, ACK can happen **before** processing code runs; if code fails afterward, the message may not be redelivered.

## 3. Separating Listener and Container Responsibilities

### 3.1. What is the listener responsible for?

A `@JmsListener` method should be responsible for:

- Validating schema/message type and business data.
- Executing business operations idempotently.
- Distinguishing transient errors from permanent errors.
- **Letting exceptions propagate** when you truly want the container to treat the attempt as failed and perform rollback/recovery per configuration.
- Logging/recording metrics using business event IDs and headers like `JMSMessageID` and `JMSRedelivered` (avoiding logging sensitive data).

### 3.2. What is the container responsible for?

The container handles:

- Creating `MessageConsumer`, choosing Queue/Topic, message selectors, and the receive loop.
- Setting `sessionTransacted`, `sessionAcknowledgeMode`, and transaction manager.
- Calling `commit()` or `rollback()` on a locally transacted Session when appropriate.
- Invoking ACK/recover in non-transacted modes per specific contracts.
- Managing concurrency, error handlers, resource caching, and broker recovery.
- Coordinating **auto-reply** sending on the same Session when supported by the adapter.

**A listener method has no `acknowledgment` attribute on `@JmsListener`** to switch modes per invocation. Configure `JmsListenerContainerFactory` (or the listener container itself) and select the factory via `containerFactory = "beanName"`.

## 4. Acknowledgment Modes in Jakarta Messaging

Jakarta Messaging defines constants on `jakarta.jms.Session`:

```java
Session.AUTO_ACKNOWLEDGE
Session.CLIENT_ACKNOWLEDGE
Session.DUPS_OK_ACKNOWLEDGE
Session.SESSION_TRANSACTED
```

However, **`SESSION_TRANSACTED` is not a simple drop-in acknowledge mode for a non-transacted session**. In Spring, when you want a local JMS transaction, use `setSessionTransacted(true)`.

| Spring container config | When does ACK/commit occur? | Listener throws exception | Typical reliability |
| --- | --- | --- | --- |
| `AUTO_ACKNOWLEDGE`, `sessionTransacted=false` | Depends on container; see section 5. | No guaranteed redelivery on user exceptions. | Easy to lose messages during failures. |
| `DUPS_OK_ACKNOWLEDGE`, non-transacted | Delayed/lazy ACK. | No guaranteed redelivery when handler throws. | Duplicate deliveries possible; unsuitable when reliable rollback is needed. |
| `CLIENT_ACKNOWLEDGE`, non-transacted | Spring container normally ACKs after listener succeeds. | **Best-effort redelivery** if listener fails; depends on recovery/provider. | Better than auto ACK in some cases, yet not atomic with other sends. |
| **`sessionTransacted=true`** | Container commits JMS transaction when listener succeeds. | Container rolls back JMS transaction when listener fails; broker can redeliver per policy. | Preferred choice for reliable Queue processing with local JMS transactions. |
| External transaction manager | Coordinator decides commit/rollback. | Rolls back transaction if matching rules trigger. | Can coordinate multiple resources when JTA/XA is properly set up. |

Never infer from a mode alone that the system achieves **exactly-once processing**. Redelivery, duplicates, transaction boundaries, DLQs, and idempotency still must be designed and tested.

### 4.1. AUTO_ACKNOWLEDGE

`AUTO_ACKNOWLEDGE` is used when transactions are off and no other mode is configured. However, **exact ACK timing differs by container**:

- `DefaultMessageListenerContainer`: the message is JMS-acknowledged during the receive step, effectively **before** the listener processes it. A listener exception cannot recover an already-ACKed message.
- `SimpleMessageListenerContainer`: the provider invokes the `MessageListener` callback and auto-ACKs **after** the callback finishes; the Spring container catches listener exceptions, so thrown exceptions generally do not reach the provider intact to request redelivery.

Therefore **never use `AUTO_ACKNOWLEDGE` expecting "automatic retries on listener errors"**. That contradicts the Spring container contracts.

### 4.2. DUPS_OK_ACKNOWLEDGE

JMS may delay ACKs to optimize throughput. JVM crashes or connection failures around the ACK window can lead to redelivery; however, **business errors thrown by the listener are not a reliable rollback mechanism** in this mode.

The name `DUPS_OK` does not mean the broker intentionally sends every message twice; it simply allows lazy ACKs where duplicate deliveries may occur. Handlers should still be idempotent.

### 4.3. CLIENT_ACKNOWLEDGE

In the plain JMS API, `Message.acknowledge()` is called by the client when wanting to ACK. A common pitfall: **acknowledging one message in a Session normally confirms all messages consumed by that Session**, not merely one individual message chosen by the caller.

In a Spring listener container, `CLIENT_ACKNOWLEDGE` **does not mean you must call `message.acknowledge()` inside every `@JmsListener`**: the container normally ACKs after the listener succeeds. On errors, Spring may invoke recovery, so redelivery is **best effort**, not a substitute for a transacted session.

Spring Framework 6.2 also offers `setAcknowledgeAfterListener(...)` to tune certain client/vendor-specific acknowledgment modes. That is an advanced setting, not a toggle to flip carelessly; if you need a vendor-specific individual ACK mode, check the exact contract and Spring version.

### 4.4. Session transacted

When `sessionTransacted=true`, commit/rollback governs both **receiving the message** and **sending operations on that same JMS Session**. Normal acknowledge mode is no longer the switch deciding confirmation timing. Typical lifecycle:

```text
receive(message)
    |
    +-- begin local JMS transaction
    |
    +-- invoke listener
            |
            +-- OK  --> Session.commit() --> confirms receipt
            |
            +-- ERROR --> Session.rollback() --> possible redelivery
```

The diagram is a conceptual model; in actual execution, the `Session` is created as transacted and a transactional session is bound to the processing cycle. The application does not call `session.commit()` inside the listener: **the container does that**.

## 5. Differences Between DefaultMessageListenerContainer and SimpleMessageListenerContainer

Spring Framework JMS has two common listener containers:

### 5.1. DefaultMessageListenerContainer (DMLC)

`org.springframework.jms.listener.DefaultMessageListenerContainer`:

- Typically used for `@JmsListener` via `DefaultJmsListenerContainerFactory`.
- Uses an internal `MessageConsumer.receive()` loop, enabling proactive management of receive/commit/rollback.
- Can vary consumer count via `concurrency`, manage caching, and self-recover after connection failures.
- Supports **external transaction managers**, including JTA/XA when broker/factory and coordinator are properly configured.
- With non-transacted `AUTO_ACKNOWLEDGE`, messages may be ACKed **before the listener runs**, so Spring recommends local transactions or a transaction manager for reliability needs.

### 5.2. SimpleMessageListenerContainer (SMLC)

`org.springframework.jms.listener.SimpleMessageListenerContainer`:

- Registers listeners via JMS `MessageConsumer.setMessageListener(...)`.
- Typically creates a fixed number of Sessions and consumers at startup.
- Supports local JMS transactions via `sessionTransacted=true` yet **does not** participate in external transaction managers the way DMLC does.
- With `AUTO_ACKNOWLEDGE`, the provider ACKs after the callback, yet exceptions from listener code are handled by Spring and do not guarantee redelivery on business exceptions.
- Suitable when wanting a simple callback model in a fitting environment; should not be used expecting external XA.

### Decision table

| Criterion | DMLC | SMLC |
| --- | --- | --- |
| Receiving mechanism | Managed `receive()` polling | JMS listener callback |
| Concurrency | Adaptive scaling supported | Typically fixed |
| Local session transacted | Yes | Yes |
| External transaction/JTA | Yes | No |
| `AUTO_ACKNOWLEDGE` | ACKs before processing | ACKs after callback; app exceptions still do not guarantee redelivery |
| Connection recovery/scaling | Many options | Simpler |
| Common choice for `@JmsListener` | **DMLC** | When special requirements apply |

**Never conclude that "either container alone guarantees exactly-once".** Container type is only one part of configuring delivery semantics.

## 6. Safe Default Choice: Locally Transacted JMS Session

For Queues processing orders or critical tasks, `sessionTransacted=true` is usually the simplest and most effective choice before considering XA.

Normal case:

```text
Broker --> receive ORDER-100
         --> listener processes successfully
         --> container commits JMS Session
         --> broker marks delivery successful
```

Error case:

```text
Broker --> receive ORDER-101
         --> listener throws IllegalStateException
         --> container rolls back JMS Session
         --> broker marks for redelivery
         --> may dispatch ORDER-101 again
```

**Redelivery does not have to be immediate**: the broker may apply a delay, cap delivery attempts, route to a DLQ after repeated failures, or enforce custom policies. Never assume every broker calls the handler exactly twice when code fails on the first try.

### How it differs from a database transaction

A local JMS transaction only controls operations on its JMS Session. For instance:

```text
DB INSERT succeeds + DB COMMIT
         |
         v
JMS Session.commit() fails
         |
         v
Message is redelivered; DB may already contain persisted data
```

If the handler generates an invoice on every delivery without checking an event ID, you can create **two invoices**. You need an idempotent consumer, unique constraint, or inbox table, not just `sessionTransacted`.

## 7. Plain Spring Framework 6 Configuration

In Spring Framework with an existing `jakarta.jms.ConnectionFactory`, use `DefaultJmsListenerContainerFactory` to create transacted containers:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
public class ListenerConfig {

    @Bean("txListenerFactory")
    public DefaultJmsListenerContainerFactory txListenerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
```

This is a **compilable configuration class**, though the application must provide a valid `ConnectionFactory` bean and JMS infrastructure to register `@JmsListener`.

Listener selecting the factory:

```java
@Component
public class OrderListener {

    @JmsListener(
        destination = "orders.in",
        containerFactory = "txListenerFactory"
    )
    public void onOrder(String orderId) {
        service.process(orderId);
    }
}
```

The listener snippet above **only illustrates structure**: import `@Component`, `@JmsListener`, and supply a real `service` field/bean. Do not paste this class into a program without declaring its dependencies.

**Explanation:** `@JmsListener` selects `txListenerFactory`; the factory creates a DMLC with a transacted Session. When the listener completes normally, the container commits. When an exception escapes, the container rolls back and the provider can redeliver. `setConcurrency("1")` is helpful for easily observable experiments; production can tune based on Queue load and ordering needs.

Do not pair `setSessionAcknowledgeMode(Session.CLIENT_ACKNOWLEDGE)` with `setSessionTransacted(true)` to "double the guarantee"; in a transacted session, commit/rollback is the central mechanism.

## 8. Spring Boot: Distinguish Auto-Configured Factory vs Custom Factory

In **Spring Boot 3.x**, if JMS infrastructure is available and you **do not declare a custom factory**, Boot creates an appropriate default `JmsListenerContainerFactory`. Per official docs, **Spring Boot's default factory is transactional**:

- If an appropriate `JtaTransactionManager` exists, Boot can wire it into the listener container.
- If no JTA manager exists, Boot typically enables **`sessionTransacted=true`**.
- The Spring Boot starter/provider configures `ConnectionFactory` to connect to the broker.

This is a **critical difference**: in Spring Framework, a bare `new DefaultJmsListenerContainerFactory()` **does not automatically inherit** all of Spring Boot's transaction choices. Therefore, when declaring your own bean, explicitly configure what you need.

### 8.1. Preserving Boot defaults with Configurer

Use `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer` in Boot 3:

```java
@Bean("txListenerFactory")
DefaultJmsListenerContainerFactory txListenerFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {

    var factory = new DefaultJmsListenerContainerFactory();
    configurer.configure(
            factory,
            ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory)
    );
    factory.setSessionTransacted(true);
    factory.setConcurrency("1");
    return factory;
}
```

This snippet sits **inside a `@Configuration` class**, requiring imports for `@Bean`, `ConnectionFactory`, `DefaultJmsListenerContainerFactory`, `DefaultJmsListenerContainerFactoryConfigurer`, and `org.springframework.boot.jms.ConnectionFactoryUnwrapper`. `unwrapCaching` gives the listener container the native factory when it needs to manage connections/recovery itself rather than using Boot's caching wrapper.

**Note on external JTA:** this snippet sets `sessionTransacted=true` to illustrate local transactions without an external TM. If a real app uses JTA/XA, ensure the transaction manager/container participates via supported mechanisms; do not copy a local-tx configuration and assume it enables XA.

### 8.2. Boot configuration via application.yml

Local Artemis infrastructure example:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
    listener:
      concurrency: 1
      max-concurrency: 1
```

The values above control the broker connection, Queue domain, and concurrency for **Boot's auto-configured factory**. They do **not** substitute for setting `sessionTransacted` on a custom factory you instantiate yourself. On other Boot versions, verify property names for that version (some session property names changed across Boot releases).

**Do not confuse:**

- `spring.jms.template.session.transacted`: relates to **`JmsTemplate`** sessions.
- `spring.jms.listener.session.transacted`: relates to **listener container** session config in Boot versions supporting that name.
- `spring.jms.listener.session.acknowledge-mode`: relates to non-transacted acknowledge mode.
- `@Transactional`: creates/joins a Spring transaction using the chosen transaction manager; **does not automatically configure the listener container for XA**.

In this lab, we use a **custom factory with transactions explicitly enabled** to avoid relying on invisible defaults.

## 9. Complete Demo: Listener Fails Once, Container Rolls Back and Redelivers

The following example uses **Java 17, Spring Boot 3.3.13, Gradle 8.x, and an external Apache ActiveMQ Artemis broker**. The goal is to illustrate the exact responsibilities of the container:

1. Producer sends one `TextMessage("ORDER-001")`.
2. Listener receives it the first time and intentionally throws `IllegalStateException` to simulate a transient business failure.
3. `DefaultMessageListenerContainer` with `sessionTransacted=true` rolls back the JMS transaction.
4. Broker can resend the message per its redelivery policy.
5. When the listener succeeds on the next attempt, the container commits.

The example **does not** use a DB, so it tests only **JMS** transactions without claiming atomicity between DB and broker.

### 9.1. Test broker

If Docker is available, run Artemis:

```bash
docker run --detach --rm --name artemis-container-tx -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

Wait for the broker to be ready and inspect `docker logs artemis-container-tx`. The broker needs Queue `demo.tx.orders` or auto-create enabled; the user must have send/consume permissions. In production, pre-provision Queues, protect credentials/TLS, and configure redelivery/DLQs properly.

After the lesson, stop the broker:

```bash
docker stop artemis-container-tx
```

### 9.2. File structure

```text
listener-transaction-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/
    │   └── application.yml
    └── java/demo/jms/
        ├── ListenerTransactionApplication.java
        ├── ListenerTransactionConfig.java
        └── RetryOnceListener.java
```

`settings.gradle`:

```groovy
rootProject.name = 'listener-transaction-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

`src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
    listener:
      concurrency: 1
      max-concurrency: 1
```

The demo configures its own transacted listener factory; the concurrency properties in YAML mainly keep Boot's defaults consistent. If you create a custom factory bypassing Boot's configurer, set concurrency directly on the factory as shown next.

### 9.3. Application class: sending one request

`src/main/java/demo/jms/ListenerTransactionApplication.java`:

```java
package demo.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ListenerTransactionApplication {

    public static void main(String[] args) {
        SpringApplication.run(ListenerTransactionApplication.class, args);
    }

    @Bean
    ApplicationRunner sendTestMessage(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.convertAndSend(
                    "demo.tx.orders", "ORDER-001");
            System.out.println("SENT ORDER-001");
        };
    }
}
```

The send command executes once the context starts, while the listener runs on its own thread, so the `SENT` log may appear before or after receive logs. Never treat ordering between two threads as a business guarantee.

### 9.4. Factory: responsible for transactions

`src/main/java/demo/jms/ListenerTransactionConfig.java`:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
public class ListenerTransactionConfig {

    @Bean("txListenerFactory")
    public DefaultJmsListenerContainerFactory txListenerFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory)
        );

        // Explicitly enable the container to manage the local JMS transaction.
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
```

`configurer.configure` carries Spring Boot 3.x defaults onto the custom factory. `factory.setSessionTransacted(true)` is set explicitly afterward for demo clarity; `setConcurrency("1")` keeps one consumer so retries are easy to observe. No `JtaTransactionManager` is declared in this demo.

### 9.5. Listener: fails once, succeeds on the next attempt

`src/main/java/demo/jms/RetryOnceListener.java`:

```java
package demo.jms;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class RetryOnceListener {

    private final AtomicInteger attempts = new AtomicInteger();

    @JmsListener(
            destination = "demo.tx.orders",
            containerFactory = "txListenerFactory"
    )
    public void onOrder(String payload) {
        int attempt = attempts.incrementAndGet();
        System.out.println("ATTEMPT " + attempt + " " + payload);

        if (attempt == 1) {
            throw new IllegalStateException("Transient demo failure");
        }

        System.out.println("PROCESSED " + payload);
    }
}
```

The program intentionally throws a **runtime exception** on the first call; because the exception escapes the handler, the container detects failure and rolls back the Session. On the next delivery, the counter increments to 2, the method completes normally, and the container commits.

**Warning:** the `AtomicInteger` counter is **in-memory bean state**, not a production deduplication tool. If the JVM restarts or multiple instances/consumers exist, the counter resets or splits across instances. The demo only illustrates the transaction boundary.

### 9.6. Running and explaining the output

With Java 17+, compatible Gradle, and a clean broker:

```bash
gradle bootRun
```

If using Gradle Wrapper, run `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

With one fresh message, a broker supporting local JMS transactions, and a redelivery policy allowing resend, the lines **printed by the demo code** can be:

```text
SENT ORDER-001
ATTEMPT 1 ORDER-001
ATTEMPT 2 ORDER-001
PROCESSED ORDER-001
```

The position of the `SENT` line may vary; Spring also logs the exception from the first attempt, and the broker may delay redelivery. The lines above are **conditional expectations**, not stdout captured from an actual run during authoring.

What to observe:

- `ATTEMPT 1`: the listener **received and executed**, yet that does not mean JMS commit occurred.
- Exception: container rolls back, so the message **can** be redelivered.
- `ATTEMPT 2` then `PROCESSED`: handler completes.
- Container commits the JMS transaction after the listener returns normally; the code never calls `Message.acknowledge()` or `Session.commit()`.

If the Queue has leftover backlog from an earlier run, competing listeners, broker redelivery limits, or DLQ routing, invocation counts and order may differ. Use a clean test Queue/broker for easy comparison.

## 10. Why Not Catch Exceptions Silently?

Typical mistake:

```java
@JmsListener(destination = "orders.in")
public void unsafeHandle(String text) {
    try {
        persistOrder(text);
    } catch (RuntimeException ex) {
        logger.error("Persist failed", ex);
        // Not rethrowing; the method returns normally.
    }
}
```

This is an **illustrative snippet inside a bean with real `logger` and `persistOrder`**, not a standalone Java program.

With a transacted container, when the method returns normally, the container **has every reason to treat processing as successful** and commit the JMS Session, even though the DB failed. The result can be **the message disappearing from the Queue while business data was never saved**.

A safer pattern for transient errors:

```java
@JmsListener(destination = "orders.in")
public void handle(String text) {
    try {
        persistOrder(text);
    } catch (TransientBusinessException ex) {
        logger.warn("Temporary failure; request rollback", ex);
        throw ex;
    }
}
```

This snippet requires the corresponding exception class and service. `TransientBusinessException` should extend `RuntimeException`, or rethrow a chosen runtime exception. Letting the exception reach the container permits rollback, though **rollback occurs only when the transaction/ACK configuration actually supports it**.

### What if the error is permanent?

For instance, an invalid message schema or unsupported event version. Throwing exceptions forever can create a **poison-message loop**. You need a policy:

1. Cap redelivery attempts at the broker.
2. Provide a dead-letter address/Queue (DLQ), recording failure reasons for analysis.
3. Quarantine or flag unprocessable event types.
4. Only allow controlled replay after fixing the data/application.
5. Never swallow exceptions merely to silence logs and drop messages without a trace.

"Permanent error" and "transient error" are **business classifications**, not properties Spring's listener container can completely infer from exception types alone.

## 11. ErrorHandler, JMS ExceptionListener, and Rollback Responsibility

Spring JMS has two easily confused hooks:

- `ErrorHandler`: receives exceptions raised during **listener processing**; typically used for logging, metrics, and alerts.
- JMS `ExceptionListener`: receives connection/provider error notifications per the JMS mechanism; not synonymous with every message handler failure.

Example:

```java
factory.setErrorHandler(ex -> {
    System.err.println("Listener processing error: " + ex.getMessage());
});
```

This is a snippet inside a factory configuration method. `ErrorHandler` does not replace `sessionTransacted` or a transaction manager. In Spring containers, listener exceptions are typically **caught and handled internally by the container** rather than propagating raw to the provider; the container itself decides commit/rollback per configuration.

**Do not assume merely setting an ErrorHandler guarantees broker redelivery.** To retry on failure, you need a transacted session or proper acknowledgement/recovery mechanism, plus a broker redelivery policy.

### Does throwing an exception inside ErrorHandler trigger rollback?

Do not use throwing from `ErrorHandler` as a "rollback button". The container already has its own exception-handling and transaction flow; `ErrorHandler` is mainly an observer. Keep it stable, avoid blocking I/O, and never obscure the root cause. Rollback decisions should come from listener errors and transaction configuration.

### Logging `JMSRedelivered` as an experiment

In a listener receiving raw messages:

```java
@JmsListener(
    destination = "orders.in",
    containerFactory = "txListenerFactory")
public void handleRaw(jakarta.jms.TextMessage msg)
        throws jakarta.jms.JMSException {

    boolean redelivered = msg.getJMSRedelivered();
    String body = msg.getText();
    System.out.println("redelivered=" + redelivered + "; body=" + body);
}
```

This is an illustrative method on a Spring bean; **do not add it to the same demo Queue in section 9** because it will create a competing consumer. `JMSRedelivered` helps observe redeliveries yet is not a stable business event ID for deduplication. Some brokers also support `JMSXDeliveryCount`; verify presence and provider policy before relying on it.

## 12. How Local JMS Transactions Differ from JmsTransactionManager

There are two related yet distinct concepts:

### Container using a local JMS Session transaction itself

With `factory.setSessionTransacted(true)`, the container creates/obtains a locally transacted `Session`, calls the listener, and then commits or rolls back itself. This configuration is usually sufficient for a consumer processing a Queue and performing sends on that same Session.

### Spring `JmsTransactionManager`

`org.springframework.jms.connection.JmsTransactionManager` is a `PlatformTransactionManager` coordinating **a local JMS transaction for a `ConnectionFactory`**, binding the appropriate Session to the thread so Spring JMS operations can participate together.

Example configuring a transaction manager for JMS services:

```java
@Bean("jmsTransactionManager")
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
```

This snippet lives in a `@Configuration` class; import `JmsTransactionManager`, `ConnectionFactory`, and `@Bean`.

If code runs under `@Transactional("jmsTransactionManager")` via a Spring proxy, eligible JMS operations using the same factory can join that JMS transaction. However, **`JmsTransactionManager` does not create a distributed transaction with a database merely because the DB also has a DataSource bean**.

In listener scenarios, you usually **do not need** both container local transactions enabled and a separate `JmsTransactionManager` just to "commit twice". Establish one consistent transaction strategy and test thoroughly before layering managers.

## 13. Database @Transactional vs JMS Transaction: Critical Boundary

Example of a listener doing two things:

```text
JMS receive ORDER-101
   |
   v
@Transactional("jdbcTransactionManager")
update orders table
   |
   v
DB transaction commit
   |
   v
JMS container commits Session
```

In some Spring Boot setups, an application can run a database transaction inside a JMS-local transacted listener. That creates **two local transactions synchronized in a clean sequence**, yet **not a 2-phase commit XA transaction**. A crash between the two commits can still cause message redelivery when the DB is already updated.

### An idempotency example using an event key

Use a business event ID `eventId` in a JMS property or payload; never rely solely on `JMSMessageID` for business control if events can be republished.

Table design:

```sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Inside the DB transaction:

```text
BEGIN
  INSERT INTO processed_messages(consumer_name, event_id, ...)
  If duplicate key -> already processed, skip side effect
  If insert succeeds -> update orders table
COMMIT
```

This is **business pseudocode**, not complete SQL verbatim for every database. Use insert/duplicate-handling syntax appropriate for your DB, while ensuring the dedup insert and business update belong to **the same database transaction**.

Important scenario:

1. First attempt: listener finishes updating DB.
2. JMS commit fails due to connection loss.
3. Broker redelivers event.
4. Second attempt checks `processed_messages`, sees the event was already handled, **skips repeating side effects**, and lets the container finish the JMS transaction.

This pattern is commonly called **idempotent consumer / inbox pattern**.

### Transactional outbox when publishing new events as well

If the listener both writes to the DB and publishes an event to another broker, a local JMS transaction does not cover that other broker. A transactional outbox stores the outgoing event inside the DB transaction, and a dedicated publisher sends from the outbox. Combine with inbox/deduplication on downstream consumers to handle replays.

Choose XA only when true atomicity across multiple XA-coordinator-managed resources is required, not out of a misconception that it is a simple `@Transactional` flag.

## 14. When External JTA/XA Is Needed

`DefaultMessageListenerContainer` can use an external `PlatformTransactionManager` via `setTransactionManager`. In Jakarta EE or systems with a coordinator, **`JtaTransactionManager`** is typically used to participate in XA.

Model:

```text
            JTA Transaction Coordinator
                   /           \
                  /             \
       XA-aware JMS factory    XA DataSource
               |                  |
       consume / ACK           UPDATE DB
               |                  |
               +---- 2PC ---------+
                  commit / rollback
```

Requirements to actually achieve a shared transaction:

- The broker supports XA and an XA-capable `ConnectionFactory` is registered with the coordinator.
- The DataSource is also XA-capable and enlisted in the same JTA transaction.
- `DefaultMessageListenerContainer` uses the exact JTA transaction manager instance.
- Message receipt and DB work genuinely occur within the same transactional boundary without opening separate unmanaged connections.
- The coordinator persists transaction logs and handles recovery for in-doubt transactions.

Conceptual configuration snippet:

```java
factory.setTransactionManager(jtaTransactionManager);
```

That line alone is **not enough** for XA. `jtaTransactionManager` must be a real bean, and both broker and DB must be XA-aware and properly enlisted. Never wire an arbitrary `DataSourceTransactionManager` into a listener and call it a distributed transaction.

**XA costs:** transaction logging, coordinated recovery, extra round trips, and operational complexity. For many workloads, local JMS transactions + idempotency or inbox/outbox are easier to deploy and optimize.

## 15. Sending a Response in the Same Container Transaction

A listener can produce a **JMS response** after processing a request. If sent through **the exact JMS Session supplied by the container**, receiving and reply-sending can share a single local JMS transaction.

Example with `SessionAwareMessageListener` (Spring's Java interface model):

```java
public final class RespondingListener
        implements SessionAwareMessageListener<TextMessage> {

    @Override
    public void onMessage(TextMessage request, Session session)
            throws JMSException {

        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            throw new IllegalArgumentException(
                    "Request must provide JMSReplyTo");
        }

        try (MessageProducer producer =
                     session.createProducer(replyTo)) {
            TextMessage response =
                    session.createTextMessage("ACK:" + request.getText());
            producer.send(response);
        }
    }
}
```

This is an **illustrative class** requiring imports for `jakarta.jms.TextMessage`, `jakarta.jms.Session`, `jakarta.jms.Destination`, `jakarta.jms.MessageProducer`, `jakarta.jms.JMSException`, and `org.springframework.jms.listener.SessionAwareMessageListener`. If your provider/API version does not support `MessageProducer` in try-with-resources, use `try/finally` and `producer.close()` per contract. **Do not** paste this class into section 9's demo because that example uses `@JmsListener` and a different destination.

When the container uses a local Session transaction, **both receiving and sending the reply on that Session** can commit/roll back together. If an exception is thrown after `producer.send` yet before commit, the container rolls back the transaction; the uncommitted reply will not become a confirmed response.

### What about `@JmsListener` returning a String?

Spring's listener adapter can automatically send a reply when a method returns a value and has a valid `JMSReplyTo`, `@SendTo`, or `JmsResponse`. When the adapter sends the reply using the container's listener Session, the reply message can belong to the same JMS transaction as the receive.

However, if the handler **injects another `JmsTemplate`**, binds to another `ConnectionFactory`, or creates its own Session, do not assume that send joins the container's transaction. Verify the factory, session exposure, transaction synchronization, and integration tests.

## 16. Concurrency, Redelivery, DLQ, and Container Lifecycle

### 16.1. Increasing concurrency does not mean increasing exactly-once

For a Queue, running multiple consumers in parallel increases throughput, yet:

- Log processing order can differ from message send order.
- A rolled-back message may be delivered to **another consumer**, not necessarily the original handler instance.
- In-memory listener state (like `AtomicInteger` in the demo) cannot serve as system-wide deduplication.
- If ordering per order ID is required, consider partitioning/routing, single-active-consumer, or broker message grouping policies.

### 16.2. Retries are not just one Spring property

When the container rolls back, the provider decides when and how many times to redeliver per configured policy. Factors to review:

- Redelivery delay/backoff.
- Maximum delivery attempts.
- Dead-letter Queue/address.
- JMS header `JMSRedelivered` or property `JMSXDeliveryCount` if supported by the broker.
- Quotas, prefetch, connection recovery, and shutdown.

Spring can recover connections/consumers when the broker temporarily disconnects, yet **that does not automatically define business retry limits per message**. Redelivery and DLQ policies belong to the broker contract and application rules.

### 16.3. Shutdown, in-flight messages, and transactions

When the application stops, the listener container needs to wait for or handle active receives/tasks. If killed abruptly before a transaction commits, the JMS broker can redeliver. With pre-processing `AUTO_ACKNOWLEDGE`, you cannot assume messages are saved in the same way.

Monitor:

- Active consumer count.
- In-flight messages, message age, and Queue depth.
- Rollbacks, redeliveries, DLQ counts, and conversion failures.
- Listener processing time, DB transaction duration, and JMS commit latency.
- Messages missing or duplicating business event IDs.

**Never** tweak consumer counts or caches arbitrarily just to mask transaction bugs; inspect acknowledgement/transaction setup first.

## 17. Troubleshooting Table

| Symptom | Possible cause | Check/fix |
| --- | --- | --- |
| Listener throws exception yet message is not redelivered | Non-transacted `AUTO_ACKNOWLEDGE`, or broker policy/another consumer. | Check the actual factory, `sessionTransacted`, mode, Queue depth, and DLQ. |
| `AUTO_ACKNOWLEDGE` loses messages on processing errors | DMLC ACKed before the listener ran. | Enable local transactions or an external transaction properly. |
| `@JmsListener` lacks transactions despite Boot normally being transacted | Bare custom factory created without using configurer. | Explicitly set `setSessionTransacted(true)` or use Boot configurer. |
| Code catches exception without rethrowing | Container sees the listener finish normally. | Catch only when handled cleanly; rethrow if retry is needed. |
| One event causes side effects twice | JMS redelivery after DB commit, producer retry, or multiple consumers. | Business event ID, unique constraint, idempotent inbox. |
| Listener loops forever on a poison message | Unbounded broker redelivery or no DLQ configured. | Configure max attempts/backoff/DLQ and replay workflow. |
| ErrorHandler present yet no rollback | ErrorHandler does not itself enable JMS transactions. | Check transaction manager/Session and whether errors escape the listener. |
| `Message.acknowledge()` makes other messages disappear | CLIENT_ACK normally ACKs all consumed messages in the same Session. | Let Spring manage ACK or design Session/individual mode properly. |
| DB rolled back yet JMS ACKed | DB and JMS are two independent resources; modes/transactions out of sync. | Review transaction boundaries; use locally transacted Session + DB tx or XA. |
| JMS rolled back yet DB committed | Crash between two local commits. | Idempotency, inbox, outbox, or XA if required. |
| Reply sent yet cannot roll back with request | Reply sent via another factory/Session. | Use the same transacted Session or design an outbox. |
| `@Transactional` does not behave as expected | Proxy bypassed, wrong transaction manager selected, self-invocation. | Check proxy/bean, selected manager, and test real DB rollback. |
| Switching from SMLC to DMLC changed ACK behavior | Callback mechanism differs from polling. | Re-test `AUTO_ACKNOWLEDGE`, exceptions, and shutdown. |
| Multiple consumers process out of order | Concurrency, retries, requeueing. | Design ordering/grouping or lower concurrency on ordered streams. |
| Broker disconnected and listener stalled | Recovery/backoff or credentials/ACL, factory caching. | Inspect container logs, `ConnectionFactory`, and broker. |

### Short diagnostic workflow

1. Identify **the exact listener container factory** `@JmsListener` uses.
2. Determine whether the container is DMLC or SMLC; read `sessionTransacted`, `sessionAcknowledgeMode`, and external `transactionManager`.
3. Verify whether exceptions actually **escape the handler**.
4. Inspect the broker: was the message ACKed/committed or is it unacknowledged, redelivered, expired, or in the DLQ?
5. If a DB is involved, draw the **DB commit ↔ JMS commit** timeline and identify duplicate or loss windows.
6. Verify which transaction manager `@Transactional` uses and that the proxy is active.
7. Reproduce on a clean Queue with one consumer and a single injected failure, then scale concurrency and test shutdown/recovery.

## 18. Testing and Self-Practice Exercises

### 18.1. Unit testing configuration

You can unit test factory beans via a Spring context to verify bean names and `sessionTransacted` settings. Do not assume mocking `JmsTemplate` or mocking the listener container creates real JMS transactions; mocks only verify configuration calls.

More important is an **integration test with a real broker**:

1. Send a message, handler succeeds, verify the message is not redelivered after commit.
2. Inject failure before side effects, verify the container rolls back and the broker redelivers per policy.
3. Write to DB then inject failure after DB commit yet before JMS commit; verify the handler is idempotent on redelivery.
4. Test a permanently invalid message; verify max attempts, DLQ, and metrics.
5. Test abrupt shutdown while a handler is running; verify redelivery/duplicate handling.
6. Test `AUTO_ACKNOWLEDGE` vs `sessionTransacted=true` separately; record differences.
7. Verify replies sent via **the same Session** roll back with the request; if sent via another factory, document separate transaction boundaries.
8. Increase concurrency and verify handlers are thread-safe and deduplication does not rely on an in-memory counter.

Never write tests like "wait exactly 100 ms" or "always redeliver within 1 second": providers, backoff, and networks introduce latency. Use polling with a reasonable overall timeout, assert by business event ID, and inspect broker state.

### 18.2. Questions and answers

**Question 1.** A `DefaultMessageListenerContainer` uses `AUTO_ACKNOWLEDGE` and the listener throws `IllegalStateException`. Is the message guaranteed to be redelivered?

**Answer:** No. Non-transacted DMLC auto ACK may acknowledge the message **before calling the listener**; an exception afterward cannot roll back an already-ACKed message.

**Question 2.** With `sessionTransacted=true`, the listener receives a message and throws an exception. Who calls `rollback()`?

**Answer:** **The listener container** manages the locally transacted Session and rolls back when an error escapes. The listener does not call `session.rollback()` itself.

**Question 3.** A service uses `@Transactional` with a DB. Does that transaction automatically make JMS receive and DB commit part of one XA transaction?

**Answer:** No. That requires a JTA/XA coordinator and properly enlisted XA-aware resources. Two local transactions merely synchronized by design still have an inconsistency window.

**Question 4.** Does `CLIENT_ACKNOWLEDGE` mean the `@JmsListener` method must call `message.acknowledge()`?

**Answer:** No. Spring's container normally ACKs after the listener succeeds; check your specific mode/container. Manual ACKs can affect multiple messages on the same Session.

**Question 5.** The listener catches an exception, logs it, and returns normally. Even though the container is transacted, can the message be committed?

**Answer:** Yes. The container sees the handler complete normally; without a failure signal, it may commit the JMS transaction.

**Question 6.** Why do local JMS transactions + DB transactions need a business event ID?

**Answer:** A crash after DB commit yet before JMS commit can cause message redelivery; the event ID detects already-processed events and prevents duplicate side effects.

**Question 7.** Spring Boot 3 creates a transacted default factory; is an application's bare `new DefaultJmsListenerContainerFactory()` automatically transacted identically?

**Answer:** No. A custom bean must configure it explicitly or use `DefaultJmsListenerContainerFactoryConfigurer` to inherit the appropriate Boot settings.

**Question 8.** When a listener sends a reply on the same `Session` as receive and the Session is locally transacted, can rollback cancel the uncommitted reply too?

**Answer:** Yes, if both operations belong to **the exact same JMS Session transaction**. If the reply uses a different Session or broker, evaluate transaction boundaries separately.

**Question 9.** Can `DUPS_OK_ACKNOWLEDGE` be used to guarantee rollback when a listener throws an exception?

**Answer:** No. It is a lazy ACK mode, not a reliable replacement for `sessionTransacted=true`.

### 18.3. Exercises

**Exercise A.** Run section 9's demo on a clean Queue. Record output, delivery counts, and Queue state. Then remove `factory.setSessionTransacted(true)` **only in a test environment without a transaction manager**. Predict and observe the difference; never extrapolate from a single run that another provider behaves identically.

**Exercise B.** Add a `processed_messages` table with a unique key on `eventId`. Deliberately trigger JMS redelivery after the first processing attempt and verify business side effects happen only once.

**Exercise C.** Configure max redeliveries per broker documentation and send a message that always throws an exception. Inspect the DLQ, retry count, and operational alerts.

**Exercise D.** Implement request-reply within the same Session transaction and inject a failure before commit. Verify the response is not committed until the successful attempt.

## 19. Official Documentation

- [Spring Framework 6.2 — Receiving a Message / Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — Using Spring JMS / Simple vs Default Listener Container](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — AbstractMessageListenerContainer: acknowledgment modes](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 6.2 — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework 6.2 — SimpleMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html)
- [Spring Framework 6.2 — AbstractPollingMessageListenerContainer: external transaction manager](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html)
- [Spring Boot 3 — JMS listener auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html)
- [Spring Boot — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
- [Jakarta Messaging 3.1 — Session, acknowledgment, transaction semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Apache ActiveMQ Artemis — broker, addresses, DLQ/redelivery](https://artemis.apache.org/components/artemis/documentation/latest/)

**Conclusion:** The listener is where business logic runs, while **the listener container manages the Session, ACK, commit/rollback, and exception handling**. To prevent message loss when processing critical Queues, understand DMLC/SMLC and configure **`sessionTransacted=true`** or an appropriate external transaction manager. Even then, **JMS commit does not automatically mean DB commit**: safe processing under redelivery requires idempotency, retry/DLQ rules, and testing actual transaction boundaries.
