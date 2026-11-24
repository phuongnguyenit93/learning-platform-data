# Reusing JmsTemplate Once Configured

## Learning Objectives

In Spring Framework JMS, `JmsTemplate` is the central tool for sending and receiving messages synchronously without repeatedly writing code to open connections, create sessions, producers/consumers, and release resources. This lesson focuses on the **lifecycle and shared usage of a `JmsTemplate` once configuration is complete**.

After this lesson, you can:

1. Explain why `JmsTemplate` is **thread-safe once configured**, and the exact meaning of the phrase “once configured”.
2. Create **a singleton bean** and inject it into multiple services, even when those services are invoked concurrently.
3. Distinguish sharing a template from sharing `jakarta.jms.Session`, `MessageProducer`, `MessageConsumer`, `Connection`, and `ConnectionFactory`.
4. Identify which settings must be stable before the bean is used; and how to vary destination, headers, or content **per call** without mutating shared configuration.
5. Understand the distinct roles of `CachingConnectionFactory`, connection pools, transaction managers, and listener containers.
6. Write a Java 17 example with Spring Boot, Artemis, and two producer services sharing one `JmsTemplate`; verify that the exact same instance is shared and messages are sent/received.
7. Recognize thread-safety, transaction, resource, and performance bugs that can arise when reuse principles are misapplied.

> **Core rule:** configure `JmsTemplate` **once at application startup**, then **reuse that instance across operations**. Each call uses a context-appropriate JMS session/resource managed by Spring. Never retain a `Session` or mutate template properties across concurrent requests.

## 1. Why reuse `JmsTemplate`?

Suppose an application has three services that need to send messages: `OrderService`, `BillingService`, and `NotificationService`. All three use the same JMS broker, Queue rules, and message converter. If every request created a new `JmsTemplate`, the application would duplicate configuration code, make policies hard to govern, and gain no corresponding benefit. Spring lets you declare one template as a bean and share it across components.

~~~text
                   Spring ApplicationContext
                            |
                            v
                   JmsTemplate (singleton)
                      stable configuration
                     /       |        \
                    /        |         \
            OrderService BillingService NotificationService
                 |            |               |
                 +------------+---------------+
                           send(...)
                              |
                   Managed ConnectionFactory
                              |
                JMS Connection/Session/Producer
                              |
                           Broker
~~~

A `JmsTemplate` holds **configuration properties**, such as connection factory, destination resolver, message converter, default destination, receive timeout, and QoS. It **does not hold “in-flight conversation state” of an individual request** in a shared field. Therefore, multiple collaborators can share a reference to the template once configuration is finished.

Spring Framework documentation explicitly states that `JmsTemplate` is **thread-safe once configured**. This is a guarantee at the **template operation** level, not a guarantee that every collaborator, custom converter, or provider-specific extension is automatically thread-safe.

### Practical benefits

- **Consistency:** all services use the same broker, message conversion policy, and destination resolution strategy.
- **Easy governance:** change configuration via profiles/properties/bean definitions at startup instead of having templates constructed in scattered places.
- **Less boilerplate:** services mainly call `convertAndSend`, `send`, or `receive`.
- **Easier testing:** inject a preconfigured Spring abstraction that can be mocked/spied at the service level.
- **Better observability:** provides a single point to attach appropriate observation/interceptors or custom converters.
- **Easier resource optimization:** uses a managed `ConnectionFactory` that can combine pooling/caching. **Do not confuse** this with the template itself maintaining a session pool.

Do not conclude that “one template is fastest in every situation”. Performance depends on the broker, network, connection/session caching, message size, QoS, and concurrency. The main benefit of this principle is **proper lifecycle and safe sharing**.

## 2. What does “thread-safe once configured” mean?

Let us split the `JmsTemplate` lifecycle into two phases:

~~~text
PHASE A — CONFIGURE (startup)
  instantiate JmsTemplate
  setConnectionFactory(...)
  setMessageConverter(...)
  setDestinationResolver(...)
  setDefaultDestinationName(...)
  setPubSubDomain(...)
  setReceiveTimeout(...)
  set QoS / transaction defaults
  complete Spring bean initialization
           |
           v
PHASE B — USE (runtime)
  Thread A ──► convertAndSend(...)
  Thread B ──► convertAndSend(...)
  Thread C ──► receive(...) or send(...)
           |
           v
  Template is not reconfigured between calls
~~~

### Distinguishing three categories of state

| State category | Examples | Shared on the template? |
|---|---|---|
| **Long-lived configuration** | `ConnectionFactory`, `MessageConverter`, `DestinationResolver`, QoS, default destination, receive timeout | Yes; set before the bean is published to threads. |
| **Per-call data** | Payload, destination passed to method, `MessagePostProcessor`, correlation ID, custom JMS properties | Passed via parameters/callbacks; no need to write into shared config fields. |
| **Active JMS resources** | `Session`, `MessageProducer`, `MessageConsumer`, in-flight message, JMS transaction | Obtained and managed per operation/transaction; **never shared arbitrarily** across threads. |

“Once configured” does not mean the object is made immutable via Java `final` fields. `JmsTemplate` still has public setters. It means **the application must treat setters as configuration-phase operations**. Do not arbitrarily call setters on a template actively serving concurrent requests.

Risky example:

~~~java
// WRONG: service/request thread mutates shared configuration.
public void publishForTenant(String tenantId, String text) {
    sharedTemplate.setDefaultDestinationName("tenant." + tenantId);
    sharedTemplate.convertAndSend(text);
}
~~~

If two threads call this concurrently, Thread A might set queue A, Thread B sets queue B, and Thread A ends up sending to B. Nothing makes “set then send” an atomic operation.

Right approach: keep the template fixed and pass the destination into each call.

~~~java
// RIGHT: caller selects the destination for each send.
public void publishForTenant(String destination, String text) {
    sharedTemplate.convertAndSend(destination, text);
}
~~~

This is a snippet inside a service that has an injected `sharedTemplate` field. The actual destination name should still be validated/allowlisted to prevent arbitrary queue creation or cross-tenant privilege escalation.

### Setters to configure before startup completes

- `setConnectionFactory(...)`: source of JMS connections.
- `setDestinationResolver(...)`, `setPubSubDomain(...)`: destination resolution strategy and type (Queue/Topic).
- `setMessageConverter(...)`: conversion between Java objects and JMS messages.
- `setDefaultDestinationName(...)` or `setDefaultDestination(...)`: default destination for overloads that omit a name.
- `setReceiveTimeout(...)`: wait duration for synchronous receive operations.
- `setExplicitQosEnabled(...)`, `setDeliveryMode(...)`, `setPriority(...)`, `setTimeToLive(...)`: QoS settings if used by the application.
- `setSessionTransacted(...)` and `setSessionAcknowledgeMode(...)`: behavior of template-created sessions when no environment-managed transaction is active.

This list covers typical examples, not every property across all Spring versions. Do not confuse `setSessionTransacted` on the template with transaction settings on a **listener container**: those are two separate execution paths.

## 3. Using a singleton bean in Spring

### 3.1. Declare once in `@Configuration`

~~~java
@Configuration
public class MessagingConfig {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false); // Queue
        template.setDefaultDestinationName("app.orders");
        template.setReceiveTimeout(2_000L);
        return template;
    }
}
~~~

This is **a configuration class** (requires imports for `jakarta.jms.ConnectionFactory`, `org.springframework.jms.core.JmsTemplate`, `@Bean`, and `@Configuration`). Beans default to singleton scope in a Spring `ApplicationContext`. Spring creates the bean, runs the configuration method, and manages the reference for collaborators.

When using Spring Boot and `spring-boot-starter-artemis`, Boot can **auto-configure `JmsTemplate`** from properties. When the auto-configured template meets your requirements, you do not need to declare the bean manually. The example above suits cases where you want explicit policy control or demos; avoid accidentally having multiple templates of the same type causing injection ambiguity errors.

### 3.2. Inject the same bean into multiple services

~~~java
@Service
public class OrderService {
    private final JmsTemplate jmsTemplate;

    public OrderService(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publishOrder(String orderId) {
        jmsTemplate.convertAndSend("app.orders", orderId);
    }
}
~~~

~~~java
@Service
public class AuditService {
    private final JmsTemplate jmsTemplate;

    public AuditService(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void logOrder(String orderId) {
        jmsTemplate.convertAndSend("app.audit", "created:" + orderId);
    }
}
~~~

These two classes are **illustrative snippets of two separate files**, requiring imports for `org.springframework.stereotype.Service` and `JmsTemplate`. When both live in the same context and only one `JmsTemplate` bean exists, Spring injects **the exact same instance**.

### 3.3. A singleton bean can still be invoked concurrently

Spring does not place a lock around calls to a singleton bean. Across two HTTP requests, two schedulers, or two workers, methods can run simultaneously. `JmsTemplate` itself is designed to be used this way once configured; the service using it must still keep **the service's own state** thread-safe under concurrent calls.

For example, a non-thread-safe counter in the service still suffers a data race:

~~~java
// Anti-pattern: a thread-safe template does not make a counter field thread-safe.
private int sentCount;

public void send(String payload) {
    sentCount++; // Race when multiple threads call concurrently.
    jmsTemplate.convertAndSend("app.orders", payload);
}
~~~

When counting is needed, use `AtomicLong` or appropriate metrics; never rely on a plain mutable field. Do not put `synchronized` on the whole service just to “protect `JmsTemplate`”, as that creates an unnecessary bottleneck and does nothing for broker reliability.

## 4. Sharing a template does NOT mean sharing a Session

### How JMS operates underneath

Conceptually, a simple send looks like:

~~~text
JmsTemplate.convertAndSend(...)
  ├─ selects MessageConverter / DestinationResolver
  ├─ obtains Connection/Session from ConnectionFactory or active transaction
  ├─ creates/borrows MessageProducer
  ├─ creates TextMessage and calls send()
  └─ releases/returns resources appropriately
~~~

Spring manages resources and translates standard `JMSException`s into runtime exceptions in the Spring `JmsException` hierarchy. You should never wrap `JmsTemplate` in `try-with-resources`, because the template is a bean and does not directly represent a single session or connection to be closed after each send.

### A JMS Session is single-threaded

Jakarta Messaging specifies that a `Session` is used sequentially by one thread of control at a time. `MessageProducer` and `MessageConsumer` instances created by a session follow the same usage rule.

~~~text
Thread A ─► JmsTemplate (shared) ─► Session A ─► Producer A
Thread B ─► JmsTemplate (shared) ─► Session B ─► Producer B
Thread C ─► JmsTemplate (shared) ─► Session C ─► Consumer C
                          |
                 same ConnectionFactory
~~~

The diagram illustrates the **valid model**, without requiring every call to open a brand-new physical connection/session: a pool may reuse a session **once it is no longer in use**, or a transaction manager may let a thread reuse the session bound to its active transaction.

**Mistake:** receiving a `Session` in a template callback and saving it to a field for another thread:

~~~java
// WRONG: Session belongs only to the callback/template operation scope.
private Session savedSession;

void captureSession() {
    jmsTemplate.execute(session -> {
        savedSession = session;
        return null;
    });
}
~~~

Once the callback completes, Spring may close or return the session to the cache. Reusing `savedSession` in a later request can cause lifecycle errors, concurrent-access failures, or out-of-scope transaction bugs. All work with a Spring-supplied session in a callback must complete **inside the callback**.

### At which levels does reuse happen?

| Level | Should it be shared? | Who manages it? |
|---|---|---|
| `JmsTemplate` | **Yes**, once configured | Spring container. |
| `ConnectionFactory` | Usually **yes** | Spring/managed JMS provider/connection pool. |
| JMS `Connection` | May be shared via wrapper/pool, depending on provider | Connection factory/pool/container. |
| JMS `Session` | **Never used concurrently** | Per operation/transaction/worker and pooling layer. |
| `MessageProducer` | Do not manually hold one shared producer for all threads | Created/obtained on a session; may be safely cached internally by ownership. |
| `MessageConsumer` | Do not turn into a global shared consumer | Listener container or session-owning code. |
| `Message` | A message being built/received belongs to one operation context | Caller/listener; never send one mutable message instance concurrently. |

## 5. Distinguishing `JmsTemplate` reuse from resource caching/pooling

A singleton template **is not itself a pool**. If `ConnectionFactory` creates a fresh connection/session/producer on every call, reusing the template is still correct, yet connection overhead can be high. To optimize, Spring provides `SingleConnectionFactory`, `CachingConnectionFactory`, and provider-specific pools can be used.

### 5.1. `SingleConnectionFactory`

`SingleConnectionFactory` wraps another `ConnectionFactory` and attempts to maintain a single shared connection. It reduces connection-opening overhead across repeated send/receive operations, but **does not mean** keeping one session shared concurrently across all threads.

### 5.2. `CachingConnectionFactory`

`CachingConnectionFactory` extends `SingleConnectionFactory` and can cache:

- `Session`.
- `MessageProducer`.
- `MessageConsumer` (depending on configuration and semantic caveats).

Spring documentation notes the default `sessionCacheSize` is **1**. Caching is bucketed by acknowledgement/transaction mode; the actual number of retained sessions can exceed one when an application uses multiple modes. When more threads are active than cached slots, the cache layer can create additional temporary sessions as needed and release them when returned; do not misread `sessionCacheSize=1` as “only one thread can call the template”.

Manual configuration example (only choose when **no** equivalent wrapping exists):

~~~java
@Bean
ConnectionFactory cachingConnectionFactory(
        @Qualifier("nativeConnectionFactory") ConnectionFactory nativeFactory) {
    CachingConnectionFactory cache =
            new CachingConnectionFactory(nativeFactory);
    cache.setSessionCacheSize(8);
    cache.setCacheProducers(true);
    return cache;
}
~~~

This snippet requires imports for `org.springframework.jms.connection.CachingConnectionFactory`, `jakarta.jms.ConnectionFactory`, and annotations; it assumes a raw `nativeConnectionFactory` bean exists. **Do not use verbatim** if it creates a circular dependency or double-wraps a connection factory already auto-configured by Spring Boot.

In Spring Boot 3.5, `spring-boot-starter-artemis` is typically auto-configured with `CachingConnectionFactory`. It can be tuned via properties:

~~~properties
spring.jms.cache.enabled=true
spring.jms.cache.session-cache-size=8
spring.jms.cache.producers=true
~~~

This configuration affects **JMS resource caching** in the connection factory layer, without changing the number of `JmsTemplate` beans. Increasing cache size should only be done after load measurement; the right value depends on the provider as well as thread, transaction, and consumer counts.

### 5.3. Pooling is not Session thread-safety

A proper pool lends an active session to only one owner at a time. Only when the owner releases/closes the logical handle does the session return to the pool. If you manually retain the session reference and share it across threads, you bypass this safeguard.

### 5.4. Note on listener containers

Listener containers have their own way of obtaining, caching, and closing consumers/sessions, and can integrate with a transaction manager. Do not assume changing `spring.jms.cache.session-cache-size` automatically changes the thread count of `@JmsListener`. Listener concurrency is tuned via container settings, while `JmsTemplate` usually represents the producer or synchronous receive side.

## 6. Varying per-call data while keeping the template stable

Many dynamic needs **do not require** calling setters on the template.

### 6.1. Destination passed into the method

~~~java
// JmsTemplate keeps pubSubDomain, resolver, and connection factory unchanged.
jmsTemplate.convertAndSend("orders.commands", "order-42");
jmsTemplate.convertAndSend("payments.commands", "payment-42");
~~~

Both calls use different destination names with the exact same configuration. Because `JmsTemplate` does not validate names against business rules, production should use constants/allowlists or governed mappings. Successful resolver lookup also does not guarantee the broker has provisioned the physical queue.

### 6.2. Per-message headers and properties

Use `MessagePostProcessor` per call:

~~~java
jmsTemplate.convertAndSend(
    "orders.commands",
    "order-42",
    message -> {
        message.setStringProperty("eventId", "evt-42");
        message.setJMSCorrelationID("order-42");
        return message;
    }
);
~~~

The callback receives the message **for the current call** and returns the modified message; the template keeps its existing settings. Attaching correlation/event IDs should use request-stable data and avoid sharing mutable objects across callbacks.

### 6.3. `MessageCreator` for custom message construction logic

~~~java
jmsTemplate.send("orders.commands", session -> {
    TextMessage message = session.createTextMessage("order-42");
    message.setStringProperty("schemaVersion", "1");
    return message;
});
~~~

`Session` is supplied by the template at the right moment; operations on the session complete inside the callback. This code is a snippet inside a bean that imports `jakarta.jms.TextMessage` and injects the template; it is not a standalone program.

### 6.4. When you need both Queue and Topic simultaneously

If two business flows require different `pubSubDomain` settings, use **two template beans** configured upfront:

~~~java
@Bean("queueJmsTemplate")
JmsTemplate queueJmsTemplate(ConnectionFactory cf) {
    JmsTemplate template = new JmsTemplate(cf);
    template.setPubSubDomain(false);
    return template;
}

@Bean("topicJmsTemplate")
JmsTemplate topicJmsTemplate(ConnectionFactory cf) {
    JmsTemplate template = new JmsTemplate(cf);
    template.setPubSubDomain(true);
    return template;
}
~~~

Both beans can share the same `ConnectionFactory` if compatible with the provider/configuration. When injecting, select explicitly with `@Qualifier("queueJmsTemplate")` or `@Qualifier("topicJmsTemplate")`. This is **separating fixed configurations**, not creating a new template per message.

### 6.5. When different QoS settings are needed

`JmsTemplate` has `setDeliveryMode`, `setPriority`, `setTimeToLive`, and `setExplicitQosEnabled(true)`. These are **template-level** properties, so if two fixed QoS policies are needed, use two clearly configured beans or choose an API supporting per-operation customization if supported by your Spring version. Never mutate `setTimeToLive` on a singleton before each call.

## 7. Configuration timing and Spring initialization rules

### Standard approach

- Place properties in `application.properties` or `application.yml` per environment.
- Let Spring Boot auto-configure the template, or have a `@Bean` method create the template and set all properties.
- Inject the bean via **constructor injection** into services.
- Use the template once the application context has initialized.

### Error-prone patterns

**Calling setters inside a request method:**

~~~java
public void sendToQueue(String queue, String payload) {
    jmsTemplate.setDefaultDestinationName(queue); // Race!
    jmsTemplate.convertAndSend(payload);
}
~~~

**Creating and configuring a template inside every method:**

~~~java
public void send(String text) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.convertAndSend("orders.commands", text);
}
~~~

The second snippet usually runs, yet scatters configuration, complicates review/auditing, and easily omits timeouts, converters, and QoS. It does not magically avoid resource contention on sending; resources still come from the connection factory.

**Storing a shared mutable `MessageConverter` without thread safety:** if a converter mutates fields during `toMessage/fromMessage`, the template is thread-safe yet the converter can race. Custom converters should be stateless or thread-safe and configured before the template becomes active.

### When production configuration truly needs to change

For example, changing broker endpoints, credentials, TLS, or policy from Queue to Topic is a **global configuration change**. Implement it through environment configuration and bean/context lifecycle (refresh/redeploy, provider-managed reconnect/failover); do not assume calling setters across active threads is safe or that existing sessions will automatically migrate to a new broker.

## 8. Complete Java 17 example: one template, multiple services, multiple threads

The example below uses Spring Boot **3.5.5**, Java **17+**, Maven, and ActiveMQ Artemis. The main goal is to demonstrate:

- `OrderPublisher` and `AuditPublisher` receive **the exact same `JmsTemplate` bean**.
- Two tasks send on two threads **without mutating** template configuration.
- A listener receives both messages on a test queue.
- The code uses `@Bean` and constructor injection, without storing a JMS `Session` in a singleton.

### 8.1. Start a local broker

Requires working Docker and an unused port `61616`. Use the official Artemis image:

~~~bash
docker run --detach --rm --name reuse-jms-demo \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

The broker starts with demo user/password. The admin console is typically at `http://localhost:8161`. Use a dedicated empty broker for this lesson and avoid running two app instances on the same queue if you want to compare output cleanly.

### 8.2. File structure

~~~text
reuse-jms-template/
├── pom.xml
└── src/main/
    ├── java/example/ReuseJmsTemplateApplication.java
    └── resources/application.properties
~~~

### 8.3. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.5</version>
    <relativePath/>
  </parent>

  <groupId>example</groupId>
  <artifactId>reuse-jms-template</artifactId>
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

### 8.4. `application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

# Demo: cache idle sessions for reuse.
spring.jms.cache.enabled=true
spring.jms.cache.session-cache-size=4
~~~

`CachingConnectionFactory` is a separate connection/session caching layer; even when changing the cache size, both publishers **still inject the same template bean**. For production, never hardcode passwords; use a secret manager.

### 8.5. `ReuseJmsTemplateApplication.java`

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

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
public class ReuseJmsTemplateApplication {

    private static final String QUEUE = "lesson.jms.template.reuse";

    public static void main(String[] args) {
        SpringApplication.run(ReuseJmsTemplateApplication.class, args);
    }

    // Create exactly one bean, stably configured at startup.
    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false); // JMS Queue
        template.setDefaultDestinationName(QUEUE);
        template.setReceiveTimeout(2_000L);
        return template;
    }

    @Component
    public static class OrderPublisher {
        private final JmsTemplate template;

        public OrderPublisher(JmsTemplate template) {
            this.template = template;
        }

        void publish(String orderId) {
            // Do not call template.setDefaultDestinationName() here.
            template.convertAndSend("order:" + orderId);
        }

        JmsTemplate sharedTemplate() {
            return template;
        }
    }

    @Component
    public static class AuditPublisher {
        private final JmsTemplate template;

        public AuditPublisher(JmsTemplate template) {
            this.template = template;
        }

        void publish(String eventId) {
            template.convertAndSend("audit:" + eventId);
        }

        JmsTemplate sharedTemplate() {
            return template;
        }
    }

    @Component
    public static class DemoReceiver {
        private final CountDownLatch received = new CountDownLatch(2);

        @JmsListener(destination = QUEUE)
        public void onMessage(String body) {
            System.out.println("received=" + body);
            received.countDown();
        }

        boolean awaitTwoMessages() throws InterruptedException {
            return received.await(15, TimeUnit.SECONDS);
        }
    }

    @Bean
    ApplicationRunner runDemo(OrderPublisher orders,
                              AuditPublisher audits,
                              DemoReceiver receiver) {
        return args -> {
            boolean same = orders.sharedTemplate()
                    == audits.sharedTemplate();
            System.out.println("sameJmsTemplate=" + same);

            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                Future<?> orderTask =
                        pool.submit(() -> orders.publish("42"));
                Future<?> auditTask =
                        pool.submit(() -> audits.publish("evt-42"));

                orderTask.get(15, TimeUnit.SECONDS);
                auditTask.get(15, TimeUnit.SECONDS);
            } finally {
                pool.shutdown();
            }

            System.out.println(
                    "bothReceived=" + receiver.awaitTwoMessages());
        };
    }
}
~~~

This is **a complete single Java file**, with one public class and three nested static components detected by Spring. `CountDownLatch` is thread-safe and only used to observe both callback invocations in the demo; it is **not** a message acknowledgement, idempotency, or transaction mechanism.

### 8.6. Compile/run

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

With an empty broker, valid permissions, auto-creatable queues per Artemis policy, and no other consumers, the lines printed by application code look like:

~~~text
sameJmsTemplate=true
received=order:42
received=audit:evt-42
bothReceived=true
~~~

**Exact note on output:** the two `received=...` lines can appear in either order (two tasks send concurrently); Spring Boot also prints startup logs. `bothReceived=true` only shows the demo listener was invoked twice within the wait window; it **does not prove exactly-once** under retries/crashes. If the queue holds old messages or another consumer is competing, results must be adjusted accordingly.

### 8.7. Correctly interpreting what the demo proves

1. Inside `@Bean`, the template is created **once** and retained by the container as a singleton bean.
2. Both services use constructor injection for the same `JmsTemplate` type; printing `sameJmsTemplate=true` confirms identical object reference.
3. Each service executes in a different task, calling the same `convertAndSend(Object)` method with the configured default destination.
4. `JmsTemplate` manages operation-specific JMS resources; the two threads do **not** share a raw `Session` via a field.
5. `DemoReceiver` is driven by the listener container and has its **own** lifecycle/concurrency—it is not “a send running a callback on the producer's exact thread”.
6. `CachingConnectionFactory` underneath may cache idle sessions/producers without changing the principle that the template is reusable.

If you want to inspect on the broker, open the Artemis console and check `lesson.jms.template.reuse`, consumer count, and message count. Once the listener commits/acks successfully with no other traffic, queue depth typically returns to 0.

Stop the app with `Ctrl+C`, and stop the broker:

~~~bash
docker stop reuse-jms-demo
~~~

Because the container uses `--rm` and mounts no volumes, demo broker data is not retained on stop. Never use this disposable setup for production.

## 9. Transaction case: singleton template, per-thread/transaction Session

Spring provides `JmsTransactionManager` to manage **local JMS transactions** for a `ConnectionFactory`. When a thread participates in a Spring-managed JMS transaction, `JmsTemplate` looks up the session bound to the current thread/transaction and joins that transaction. In another thread or transaction, it uses a different matching resource context.

~~~text
JmsTemplate (one shared bean)
  |
  +-- Thread A [JMS Tx A] ──► Session A (thread-bound)
  |                            send(M1)
  |                            commit/rollback A
  |
  +-- Thread B [JMS Tx B] ──► Session B (thread-bound)
                               send(M2)
                               commit/rollback B
~~~

There is no single session or transaction instance shared by everyone just because they share the same template.

### 9.1. JMS transaction manager configuration example

~~~java
@Bean
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

In a service using Spring transaction AOP:

~~~java
@Transactional("jmsTransactionManager")
public void publishBatch() {
    jmsTemplate.convertAndSend("orders.commands", "cmd-1");
    jmsTemplate.convertAndSend("orders.commands", "cmd-2");
    // If both use the same local JMS transaction,
    // the transaction manager decides commit/rollback when the method ends.
}
~~~

These are **two configuration and service snippets**, not a standalone project. Requires imports for `org.springframework.jms.connection.JmsTransactionManager`, `org.springframework.transaction.annotation.Transactional`, and a transaction manager name matching actual configuration. `@Transactional` takes effect when the method is called properly through a Spring proxy; self-invocation does not trigger proxy interception.

### 9.2. Do not “share a transaction” across an executor

~~~java
@Transactional("jmsTransactionManager")
public void badExample() {
    // Do not assume the calling thread's JMS transaction
    // automatically propagates to a thread in the executor.
    executor.submit(
        () -> jmsTemplate.convertAndSend("orders.commands", "x"));
}
~~~

This is an anti-pattern illustrating an expectation that everything stays in the same transaction; the snippet is not a standalone Java class. `JmsTransactionManager` binds sessions to threads, so new work on an executor may not join the same transaction. If atomicity is needed, organize execution and transaction boundaries properly or use an appropriate messaging/outbox mechanism.

### 9.3. JMS transactions differ from DB transactions

A local `JmsTransactionManager` does not automatically commit/roll back a database. If the DB was updated yet the JMS send fails, state can diverge. Use a transactional outbox/idempotency or JTA/XA when distributed transactions are truly needed and supported by infrastructure. “Thread-safe template” never implies “the whole chain of side effects is exactly-once”.

## 10. Spring Boot auto-configuration and avoiding duplicate beans

With `spring-boot-starter-artemis` and connection properties, Boot can auto-create:

- `ConnectionFactory` and an appropriate caching/pooling wrapper.
- `JmsTemplate` (when no bean of this type is declared by the application).
- Supporting infrastructure for `@JmsListener` when JMS infrastructure is enabled.

If defaults suffice, let Boot create the template and inject it directly:

~~~java
@Service
public class EventPublisher {
    private final JmsTemplate template;

    public EventPublisher(JmsTemplate template) {
        this.template = template;
    }

    public void publish(String eventId) {
        template.convertAndSend("events.queue", eventId);
    }
}
~~~

In `application.properties` you can use:

~~~properties
spring.jms.pub-sub-domain=false
spring.jms.template.default-destination=events.queue
spring.jms.template.receive-timeout=2s
spring.jms.cache.session-cache-size=5
~~~

Boot applies these properties during auto-configuration; when **declaring your own `@Bean JmsTemplate`**, verify whether the Boot properties you expect are still automatically bound. Do not assume a template you instantiate manually with `new JmsTemplate(...)` receives every setter from `spring.jms.template.*` unless you configure them yourself.

### When multiple templates exist

If using two brokers or two fixed policies, multiple templates make sense. However, injection must disambiguate:

~~~java
public EventPublisher(
        @Qualifier("ordersJmsTemplate") JmsTemplate template) {
    this.template = template;
}
~~~

This is a **constructor snippet**. Without a matching qualifier or `@Primary`, Spring may report multiple `JmsTemplate` beans and fail to choose one.

**Technical conclusion here:** “Reusing a template” means **each stable configuration set shares one instance**. It does not require every application to have strictly one template across all brokers, destination domains, and policies.

## 11. Synchronous receive and request-reply follow the same rules

### 11.1. `receive` needs a timeout

`JmsTemplate.receive(...)` and `receiveAndConvert(...)` are synchronous operations that can block the thread until a message arrives. If an application shares one template for both send and receive, configure `receiveTimeout` before using it. Example:

~~~java
@Bean
JmsTemplate pollingTemplate(ConnectionFactory cf) {
    JmsTemplate template = new JmsTemplate(cf);
    template.setReceiveTimeout(3_000L);
    return template;
}
~~~

Here `receiveTimeout` is a **bean-wide** setting. Do not change it before individual receives if the bean is shared. If two use cases require different fixed timeouts, declare two templates or choose an API supporting per-operation overrides in your Spring version.

### 11.2. Separate polling from listener containers when appropriate

A `@JmsListener` managed by a container has its own concurrency and message-receiving lifecycle. `JmsTemplate.receive()` creates a synchronous consumer for the operation. If you accidentally poll and run a listener on the same Queue, they can **compete to receive** messages. That is queue semantics, not a template thread-safety bug.

### 11.3. Request-reply

`JmsTemplate` provides synchronous request-reply operations like `sendAndReceive(...)`, which can create a temporary queue for replies. It can block according to reply timeout/API specifics; you need correlation, timeouts, and handling for late replies. Reusing the template remains valid once configured; never store per-request-reply state in a shared mutable field on the bean.

## 12. MessageConverter and MessagePostProcessor must be safe for concurrent calls

The default `SimpleMessageConverter` handles several standard message forms (such as text/bytes/serializable objects). To transmit JSON and business objects, applications typically define another converter.

When a converter is a bean invoked by multiple threads through the template:

- Prefer **stateless** converters or ones with thread-safe components.
- Serializer, schema, and mapping configurations should be initialized upfront.
- Never store “current payload”, “current tenant”, or “current requestId” in mutable converter fields.
- If the converter relies on a custom registry or cache, verify the thread-safety of that registry/cache.
- Never assume sending an arbitrary Java object automatically serializes it to JSON per contract; you must configure the converter, content type, and schema.

Anti-pattern example:

~~~java
// Bug illustration only — simplified converter class.
class UnsafeConverter {
    private String currentTenant;

    void setTenant(String tenant) {
        currentTenant = tenant;
    }

    String convert(String payload) {
        return currentTenant + ":" + payload;
    }
}
~~~

If Thread A sets tenant A and then Thread B sets tenant B, data can be mislabeled even though `JmsTemplate` itself is safe. Pass tenant in the payload/headers **per call**, or use explicitly designed, thread-verified context propagation.

## 13. Common mistakes when reusing `JmsTemplate`

| Anti-pattern | Potential consequence | Fix |
|---|---|---|
| Calling `setDefaultDestinationName` on each request | Two threads can send to the wrong queue | Pass destination to `convertAndSend(name, payload)`. |
| Calling `setPubSubDomain` before each send | Queue/Topic semantics can flip between calls | Separate template beans by domain. |
| Creating a new template for every message | Scattered configuration, hard to observe, inconsistent policies | Inject a configured singleton. |
| Storing template-callback `Session`/`MessageProducer` in a field | Expired resource lifecycle or concurrent misuse | Use only inside the callback; let Spring manage them. |
| Assuming a singleton template has one singleton Session | Leads to broken ack/transaction designs | Distinguish template state from per-operation resources. |
| Increasing `sessionCacheSize` to increase listener concurrency | Two parameters at different layers | Tune listener container and cache separately per workload. |
| Writing a custom converter with mutable request state | Data race, leaked/mixed payloads across requests | Thread-safe converters and per-message headers. |
| Sharing a template across tenants without access control | Sending to wrong namespace or broker | Allowlists, broker ACLs, and separate factories by security boundary. |
| Changing credentials/CF via setters at runtime | Unclear which old/new resources use which policy | Use clean lifecycle/reconfiguration management. |
| Assuming `convertAndSend` returning means consumer processed | Processing errors or backlogs go unnoticed | Monitor broker/consumer ack, retries, DLQ, idempotency. |
| Running async inside `@Transactional` expecting the same transaction | New thread lacks the prior thread's bound session/tx | Keep transaction boundaries intact or use outbox/JTA appropriately. |
| Using mutable counters/collections in sender services | Race conditions in service logic | Local variables, concurrent structures, or metrics. |

### Why can concurrency still fail even when the template is thread-safe?

When exceptions happen under load, analyze **the right layer**: JMS broker disconnect, exhausted session pool, unsafe custom converter, transaction timeout, listener redelivery, oversized messages, slow consumers, etc. These can be infrastructure/logic bugs rather than the shared template. Do not rush to switch the bean to `prototype`; that may mask symptoms without fixing the root cause.

## 14. Designing for multiple brokers or security levels

One `JmsTemplate` holds one `ConnectionFactory` reference in its configuration. If the application needs to send to **two different brokers**, create separate clearly named factories and templates:

~~~text
ordersConnectionFactory ─► ordersJmsTemplate ─► OrderService
auditConnectionFactory  ─► auditJmsTemplate  ─► AuditService
~~~

One broker using two destinations with the same policy can share one template with different names per call. Two different brokers/credentials/transaction policies normally mean two templates. For multi-tenancy:

- If multiple tenants share physical queues partitioned by metadata, use a validated per-message `tenantId` and matching broker/app ACLs.
- If each tenant needs a separate broker identity, do not swap credentials by mutating the `ConnectionFactory` of a running shared template.
- If tenant routes change frequently, consider a routing service/registry and preconfigured templates; bound the number of coexisting connections/resources.
- Never pass unvalidated `String` destinations from HTTP input, as the broker might auto-create queues or permit cross-tenant sends depending on config.

The key decision is always the **stable configuration boundary**: one template can serve many tasks, but it is not a substitute for isolation, authorization, and resource governance.

## 15. Observing and testing reuse in practice

### 15.1. Checking bean identity

In the demo, `orders.sharedTemplate() == audits.sharedTemplate()` returns `true` when both receive the same injected bean. This is an **identity** check, not a load test or proof of provider safety.

### 15.2. Concurrent load

Use multiple sender tasks sending messages with unique IDs, await results, and inspect message counts. Checking only for “no exceptions” is not enough: compare counts of sent, received, acked, DLQ, and errored messages. Under load, the broker may enforce quotas or network timeouts; tests must establish capacity and SLAs independently.

### 15.3. Measuring actual resources

Useful metrics:

- Active/idle connection and session counts of the pool/provider (if exposed).
- Producer send latency, error rate, and timeouts.
- Queue depth, consumer count, redeliveries, and dead letters.
- Listener processing latency and transaction failures.
- Resource churn (excessive session creation/closing) when cache size is too low.
- Cache hit/miss or session reuse (if the implementation exposes metrics).

Never use `JmsTemplate`'s hashcode to infer there is strictly one connection or one session; bean identity and physical resource count are two different measurements.

### 15.4. A valuable integration test

A real integration test should start a dedicated broker, inject two senders, concurrently send *n* messages with unique event IDs, and wait for a consumer to collect all unique IDs within a timeout. Verify:

1. Both senders share the same template bean.
2. Zero concurrency bugs in custom converters/service logic.
3. Destination/Queue and transaction policies are right.
4. Messages are processed without data bleeding across threads.
5. Resource counts do not grow unboundedly after load finishes.

Do not write unit tests just to count how many times setters were called when configuration is already simple; end-to-end tests address real risks better.

## 16. Production readiness checklist

Before exposing a shared `JmsTemplate` bean, confirm:

1. **Bean declaration:** template is a Spring singleton, fully configured via Boot/`@Configuration` before any sender uses it.
2. **ConnectionFactory:** right broker, credentials, TLS, pool/cache, recovery, and lifecycle.
3. **Namespace:** Queue/Topic, destination resolver, default destination, and allowlist are clearly defined.
4. **Converter:** serializer/schema are thread-safe, holding no request context in mutable fields.
5. **QoS/receive:** priority, TTL, delivery mode, and reply/receive timeouts fit requirements; no runtime setter mutations on request paths.
6. **Transactions:** clarify when `JmsTransactionManager`/JTA applies and what is not covered (DB, HTTP APIs).
7. **Concurrency:** never retain `Session`/`Producer`/`Consumer` across threads; listeners/services also handle state thread-safely.
8. **Monitoring:** metrics/logs cover send errors, queue backlogs, consumer acks, retries/DLQ, and session pools.
9. **Resilience:** network failures and provider failovers are tested; send success is never assumed to be exactly-once.
10. **Configuration changes:** deploy/refresh follows controlled procedures; new templates are initialized and replaced via proper lifecycle.
11. **Multi-tenant/broker:** separate templates along genuine connection/policy differences; never use setters to swap identity.
12. **Resource sizing:** caches/pools are measured and tuned; never equate “one bean” with “one session”.

## 17. Self-check questions

**1. Can two different controllers inject the same `JmsTemplate` and call `convertAndSend` concurrently?** Yes, once the template is configured and any custom dependencies/callbacks are designed safely for concurrent calls.

**2. Does using one template mean there is only one JMS Session?** No. Spring obtains an appropriate session per operation/transaction; pooling can reuse idle sessions, yet a session is never used concurrently.

**3. To change the queue on every request, do you need `setDefaultDestinationName`?** No. Use the `convertAndSend(destinationName, payload)` overload and validate the destination name.

**4. What do you do if one template needs to send to Queues and another to Topics?** Configure two stable beans with different `pubSubDomain` settings and inject explicitly using qualifiers.

**5. Why not create a new template on every send?** It fragments policies and complicates management, whereas Spring already designed the template to be safely shared once configured.

**6. Does `CachingConnectionFactory.sessionCacheSize=1` prevent two threads from calling the template at the same time?** No. Cache size caps how many idle sessions are retained per mode, not a lock serializing all template calls.

**7. Does a thread-safe template make a custom `MessageConverter` with mutable fields thread-safe?** No. The converter must also be stateless or properly synchronized, and preferably receive metadata per message.

**8. Do two `@Transactional("jmsTransactionManager")` methods called from two threads share one common JMS Session?** No. Transactions and sessions are bound to their respective threads/transactions.

**9. A sender calls `convertAndSend` and sees no exception; is the consumer guaranteed to have processed it successfully?** No. You must monitor the broker, subscriber/consumer, acks, retries, DLQ, or business-level confirmation mechanisms.

**10. Why does the example have one template yet still need `CachingConnectionFactory`?** The template and cache solve two separate concerns: one is a shareable operations configuration; the other optimizes the cost of creating/closing JMS resources.

**11. Is it safe to change the broker URL on a shared template via a setter while running?** There is no safety guarantee under the “once configured” design. Use controlled reconfiguration/lifecycle instead.

**12. What is new in Spring Framework 7 in this area?** There is the `JmsClient` fluent API, which can build on `JmsTemplate` to leverage configured settings; it does not remove the principle separating template configuration from per-operation resources. In the Spring Boot 3.5/Framework 6.2 examples here, `JmsTemplate` is used directly.

## 18. Official reference documentation

- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — states thread-safe once configured, template lifecycle, callbacks, caching, and transactions.
- [Spring Framework — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — `convertAndSend`, `send`, `receive`, setters, and callbacks.
- [Spring Framework — CachingConnectionFactory API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html) — session caching and resource reuse.
- [Spring Framework — JmsTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html) — thread-bound JMS transaction resources.
- [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html) — Artemis starter, ConnectionFactory auto-configuration, and caching.
- [Spring Boot 3.5 — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) — `spring.jms.cache.*`, `spring.jms.template.*`, `spring.artemis.*`.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/) — threading restrictions of JMS Session and delivery/receive rules.
- [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html) — local broker for demos.

**Remember:** **A stably configured `JmsTemplate` can be shared across multiple services and threads.** Per-call JMS resources still have their own lifecycle/transaction managed by Spring and `ConnectionFactory`. When you need to vary data, use per-call arguments and callbacks; when you need to change long-lived policy, create/configure the appropriate bean within the application lifecycle.
