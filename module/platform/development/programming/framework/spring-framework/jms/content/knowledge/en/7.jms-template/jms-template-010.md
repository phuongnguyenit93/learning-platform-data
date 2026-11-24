# Distinguishing Shared Configuration from Per-Operation Customization in JmsTemplate

## 1. The problem to solve

In Spring JMS, an application typically has multiple services sending/receiving messages through `org.springframework.jms.core.JmsTemplate`. The crucial question is: which properties should be configured **once at bean initialization**, which can **vary per send/receive call**, and when should a separate template be used?

Consider an invoicing system with three requirements:
- By default, all commands go to the `billing.invoice.commands` Queue, sharing `ConnectionFactory`, payload converter, and receive timeout.
- One specific send must attach a `correlationId` and `eventType` property for tracing/classification.
- An urgent message requires `priority=8` and `timeToLive=10_000 ms`; normal commands use `priority=4` and `timeToLive=60_000 ms`.

The solution is not calling `jmsTemplate.setPriority(8)` before sending and resetting it back to `4`. Because `JmsTemplate` is shared across multiple threads, mutating state like that introduces a **race condition**: another service might send while the template is temporarily modified.

**Core rule: finish configuring the `JmsTemplate` instance at initialization and reuse it; customize individual messages via method arguments/callbacks, or use a separate template configured for a different stable policy.**

This lesson uses Spring Framework 6.x, Spring Boot 3.x, `jakarta.jms.*`, and Java 17+. Here “shared configuration” refers to the template's stable state within the same Spring context, not that every Queue, Topic, or listener on the broker must share the same policy.

## 2. What does JmsTemplate do?

`JmsTemplate` is a helper class for synchronous JMS access: it obtains `Connection`/`Session` when needed, creates/sends or receives messages, reclaims resources, and translates checked `JMSException`s into Spring's unchecked `JmsException` hierarchy. It is not a broker and not a store of conversation state.

~~~text
Service A ───────┐
                 │
Service B ───────┼──> Shared JmsTemplate bean
                 │        │
Service C ───────┘        ├── ConnectionFactory
                          ├── DestinationResolver
                          ├── MessageConverter
                          ├── Default destination / Queue-Topic mode
                          ├── Default QoS / receive timeout
                          │
                          └── send/receive -> JMS provider -> broker

Each call can pass:
    explicit destination
    payload / MessageCreator
    MessagePostProcessor (headers, properties)
    ProducerCallback (send with custom QoS)
    selector (conditional receive)
~~~

According to Spring Framework, `JmsTemplate` is **thread-safe once configured**. Multiple services can inject the same bean and call `convertAndSend(...)` concurrently. The condition lies in “once configured”: setters such as `setDefaultDestinationName`, `setMessageConverter`, or `setTimeToLive` mutate the template itself, so never use them like per-request temporary variables.

Template thread-safety does not mean a `jakarta.jms.Session` or `MessageProducer` can be shared arbitrarily across threads. Those are managed by the framework/provider within the appropriate operation or callback scope.

## 3. Accurate classification: shared vs. per-operation

| Need | Shared configuration on the bean | Per-call customization |
|---|---|---|
| Broker connection | `setConnectionFactory(...)`; credentials/TLS/pool beneath `ConnectionFactory` | Normally do not switch factory per call; use a separate bean for another broker/policy. |
| Destination type | `setPubSubDomain(false)` for Queue or `true` for Topic when resolving dynamic names | `send(Destination, ...)` or a separate factory/template when another destination type is needed. |
| Destination name | `setDefaultDestinationName(...)` or `setDefaultDestination(...)` | Pass the name to `convertAndSend("queue.name", ...)`, `send("queue.name", ...)`, or `receiveSelected("queue.name", ...)`. |
| Payload conversion | `setMessageConverter(...)`, defaults to `SimpleMessageConverter` | `send(..., MessageCreator)` to build a specific `TextMessage`/`BytesMessage`; `convertAndSend(..., MessagePostProcessor)` to enrich after conversion. |
| Headers/properties | Shared convention in converter or service logic | `MessagePostProcessor` sets `JMSCorrelationID` and application properties such as `eventType`, `tenantCode`. |
| Send QoS | `setExplicitQosEnabled(true)` and `setDeliveryMode`, `setPriority`, `setTimeToLive` | `execute(destination, ProducerCallback)` calling `producer.send(message, deliveryMode, priority, timeToLive)` for a special send; or use another template bean. |
| Message delivery delay | `setDeliveryDelay(...)` (requires provider/JMS API support) | With lower-level APIs, use a per-call scoped producer; do not mutate singleton setters per request. |
| Receive timeout | `setReceiveTimeout(milliseconds)` | `receive(destination)`/`receiveSelected(destination, selector)` pick target/selector; these overloads do not take a per-call receive timeout. For a different timeout policy, consider another template or a carefully managed timeout callback. |
| Transaction/session | `setSessionTransacted(...)` and `JmsTransactionManager`/transaction manager setup | Scope transactions at the service layer; do not toggle `sessionTransacted` between calls. |
| Listener | **Not controlled by JmsTemplate**; belongs to `DefaultJmsListenerContainerFactory` and listener containers | `@JmsListener` has its own destination/selector/subscription; concurrency/acknowledgement usually live on the listener factory. |

Two notes:
1. “Per-call” means **arguments** or **callbacks** running with Spring-created resources. It never means calling setters on the shared bean.
2. Sending a message to a different destination does not automatically turn a Queue into a Topic. For dynamic names, `pubSubDomain` and `DestinationResolver` still determine how targets are created/resolved. With explicit destination objects, the JMS object's type determines semantics.

## 4. Shared configuration: a stable bean

The Spring configuration snippet below illustrates a default policy for **Queues**. It is a configuration class that compiles when the project declares `spring-jms` and has a matching `jakarta.jms.ConnectionFactory`.

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class SharedJmsConfiguration {

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);

        // Fixed settings for every call using this bean.
        template.setDefaultDestinationName("billing.invoice.commands");
        template.setPubSubDomain(false);           // Queue
        template.setReceiveTimeout(3_000L);       // Synchronous receive up to 3 seconds

        // Use template-specified QoS instead of provider defaults.
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(4);
        template.setTimeToLive(60_000L);

        return template;
    }
}
~~~

In practice, Spring Boot can auto-configure `JmsTemplate` when a provider `ConnectionFactory` exists and no replacement bean is declared. Create an explicit `@Bean` when you want a consistent policy or full control over configuration sources; you do not have to manually configure every property.

**What the setters mean:**
- `setDefaultDestinationName`: used when calling `convertAndSend(payload)`, `send(messageCreator)`, or `receive()` without passing a destination.
- `setPubSubDomain(false)`: names are resolved in Queue mode in this example. Queue/Topic semantics must match broker infrastructure.
- `setReceiveTimeout(3_000L)`: wait limit for the template's **synchronous receive** operations; it is not a broker connection timeout, `@JmsListener` processing timeout, or send timeout.
- `setExplicitQosEnabled(true)`: ensures the template's `deliveryMode`, `priority`, and `timeToLive` settings are applied when Spring calls `producer.send`; if `false`, provider defaults may be used.
- `DeliveryMode.PERSISTENT` and TTL do not guarantee a message survives indefinitely: actual durability still depends on broker persistence, transactions, retention, expiration policies, and destination/subscription setup.

You can leave the default `MessageConverter` as `SimpleMessageConverter` for `String`/`TextMessage`. When the entire application adopts a JSON standard, replacing the shared converter with a properly configured one is reasonable, though that introduces a separate payload contract requiring versioning.

## 5. Sharing one JmsTemplate across multiple services

A typical sending service does not need to care about JMS internals:

~~~java
package example.jms;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoiceCommandPublisher {
    private final JmsTemplate jmsTemplate;

    public InvoiceCommandPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void requestIssue(String invoiceId) {
        // Uses the bean's default destination and default QoS.
        jmsTemplate.convertAndSend(invoiceId);
    }

    public void requestCancel(String invoiceId) {
        // Overrides the destination ONLY for this call.
        jmsTemplate.convertAndSend(
                "billing.invoice.cancel", invoiceId);
    }
}
~~~

Both calls still share the same `ConnectionFactory`, converter, and QoS policy. The second call does not alter the template's `getDefaultDestinationName()`. The next call to `convertAndSend(invoiceId)` still targets `billing.invoice.commands`.

When multiple beans inject the same singleton, there is no issue with **reading conventionally immutable configuration state**; problems arise when code calls `setDefaultDestinationName(...)` to change the target before a send. Instead, pass the target right in the method signature.

### Physical names and environment configuration

In `dev`, a Queue might be `dev.billing.invoice.commands`; in `prod`, `prod.billing.invoice.commands`. Put physical names in `application.yml`/environment variables and inject via `@Value` or `@ConfigurationProperties`; business code should not guess environments or concatenate prefixes from requests. Destination naming is deployment configuration, while logical keys inside the application should stay stable.

For example, you can replace `setDefaultDestinationName("billing.invoice.commands")` with a value injected into the `@Bean` method via a property. That is still **configured once when creating the template**, not changed on each request.

## 6. Customizing one message with MessagePostProcessor

`JmsTemplate.convertAndSend(destination, payload, postProcessor)` works in two steps: first `MessageConverter` converts the Java payload into a JMS `Message`; then `MessagePostProcessor` gets a chance to update headers/properties on **that newly created message** right before send.

Example sending an event with a correlation ID and filtering properties for consumers:

~~~java
package example.jms;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class EventPublisher {
    private final JmsTemplate jmsTemplate;

    public EventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String orderId, String correlationId) {
        jmsTemplate.convertAndSend(
                "billing.invoice.commands",
                "ISSUE:" + orderId,
                message -> {
                    message.setJMSCorrelationID(correlationId);
                    message.setStringProperty("eventType", "INVOICE_ISSUE");
                    message.setStringProperty("producer", "order-service");
                    return message;
                });
    }
}
~~~

This example runs with a broker/provider and Spring JMS config; it is not a standalone `main`. `MessagePostProcessor` may throw `jakarta.jms.JMSException`, and the template translates caught checked exceptions into `org.springframework.jms.JmsException`.

**Strength:** the callback is invoked for one send without changing the bean's `MessageConverter` or `defaultDestinationName`. Concurrent calls can carry different correlation IDs.

**Do not use MessagePostProcessor to simulate per-send QoS** via `message.setJMSPriority(8)` or `message.setJMSExpiration(...)` expecting the broker to honor them. `JMSPriority`, `JMSDeliveryMode`, and `JMSExpiration` are headers governed by `MessageProducer.send(...)` calls and provider rules; setting them pre-send can be updated/overwritten. For reliable per-send policies, pass `deliveryMode, priority, timeToLive` to the matching `producer.send(...)` overload or use a dedicated template.

### When is MessagePostProcessor not enough?

- Want to **change send QoS** for a single request: operate at the `MessageProducer` level or use a separate template.
- Want to change the **application-wide default converter**: configure the bean. For rare payloads, use `MessageCreator` to build an explicit message type without altering the converter.
- Want to change **broker/credentials/TLS** for one message: never do this by mutating the `ConnectionFactory` on a template shared by multiple services.

## 7. Using MessageCreator when you need control over message structure

`send(destinationName, MessageCreator)` gives the callback a `jakarta.jms.Session` to build a case-specific message. It does not automatically run `MessageConverter` on an application object.

~~~java
jmsTemplate.send("billing.invoice.commands", session -> {
    jakarta.jms.TextMessage message =
            session.createTextMessage("ISSUE:inv-17");
    message.setJMSCorrelationID("request-17");
    message.setStringProperty("schema", "invoice-issue-v1");
    return message;
});
~~~

The snippet above is a **code fragment** running inside a method where `jmsTemplate` is already injected; it is not a complete Java file. The `TextMessage` still goes through the template's default sending path, transactions, destination resolution, and QoS. Use it when you need `BytesMessage`, `MapMessage`, `TextMessage`, or complex headers unsupported by the shared converter.

Comparison:
- `convertAndSend("queue", object)`: uses the configured converter.
- `convertAndSend("queue", object, postProcessor)`: converts, then adds properties/headers for **that specific message**.
- `send("queue", session -> ...)`: builds the message manually using the JMS `Session`.
- `execute("queue", (session, producer) -> ...)`: works directly with the producer to pick QoS for one send or multiple sends inside the callback.

Never use a callback to retain `Session`/`MessageProducer` for calls after the callback ends. Spring manages callback resource lifecycles; retaining references can cause errors, leaks, or cross-thread session misuse.

## 8. QoS: shared configuration vs. per-send customization

In JMS, `MessageProducer` has two common send groups:

~~~java
producer.send(message);                          // default QoS
producer.send(message, deliveryMode, priority, timeToLive);
~~~

`deliveryMode` is `DeliveryMode.PERSISTENT` or `NON_PERSISTENT`; `priority` is an integer from 0 to 9; `timeToLive` is in milliseconds, where 0 indicates no TTL expiration (though the broker may still apply its own policies).

On `JmsTemplate`, the setters:

~~~java
template.setExplicitQosEnabled(true);
template.setDeliveryMode(DeliveryMode.PERSISTENT);
template.setPriority(4);
template.setTimeToLive(60_000L);
~~~

establish the **policy for normal sends on that template**. If `explicitQosEnabled=false`, merely calling `setPriority(8)` does not guarantee the producer uses priority 8. The JMS provider may apply its own defaults.

Suppose an urgent request needs `NON_PERSISTENT, priority=8, TTL=10 seconds` **for one send only**. Never call `template.setPriority(...)` inside a business method, because setters mutate the shared singleton's state.

### Approach 1 — ProducerCallback with per-send QoS (without mutating template)

~~~java
jmsTemplate.execute("billing.invoice.commands", (session, producer) -> {
    jakarta.jms.TextMessage urgent =
            session.createTextMessage("ISSUE:inv-urgent");
    urgent.setStringProperty("eventType", "INVOICE_ISSUE");
    urgent.setJMSCorrelationID("request-urgent-1");

    producer.send(
            urgent,
            jakarta.jms.DeliveryMode.NON_PERSISTENT,
            8,       // priority for this send
            10_000L  // 10-second TTL for this send
    );
    return null;
});
~~~

This is a snippet inside a service that has `jmsTemplate`. The `execute(String, ProducerCallback<T>)` overload supplies a `Session` and a `MessageProducer` bound to the target destination. The `producer.send(...)` call directly uses the QoS parameters passed **in that call**, while other `convertAndSend(...)` calls continue using the template's default QoS. Checked `JMSException`s inside the callback are managed/translated by Spring at the template boundary.

**Scope note:** with `ProducerCallback`, your custom send code is responsible for choosing the right producer overload and parameters. Spring manages connection/session/producer around the callback, but business code must still handle idempotency, retries, and transactions properly. Never assume exactly-once merely because send returned normally.

### Approach 2 — Create two preconfigured templates for two stable policies

If the system regularly has two QoS groups (such as payment commands and telemetry), two named beans can be clearer than repeating callbacks:

~~~java
@Configuration
class MessagingTemplates {
    @Bean("standardJmsTemplate")
    JmsTemplate standard(ConnectionFactory factory) {
        JmsTemplate t = new JmsTemplate(factory);
        t.setDefaultDestinationName("billing.invoice.commands");
        t.setExplicitQosEnabled(true);
        t.setDeliveryMode(DeliveryMode.PERSISTENT);
        t.setPriority(4);
        t.setTimeToLive(60_000L);
        return t;
    }

    @Bean("expiringJmsTemplate")
    JmsTemplate expiring(ConnectionFactory factory) {
        JmsTemplate t = new JmsTemplate(factory);
        t.setDefaultDestinationName("billing.invoice.commands");
        t.setExplicitQosEnabled(true);
        t.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
        t.setPriority(8);
        t.setTimeToLive(10_000L);
        return t;
    }
}
~~~

In actual Spring config, add imports for `jakarta.jms.ConnectionFactory`, `jakarta.jms.DeliveryMode`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration`, and `org.springframework.jms.core.JmsTemplate`. The snippet above is an **illustrative configuration class**; if combining into the project alongside section 4, avoid duplicate bean names or ambiguous injection. Services should inject beans using `@Qualifier("standardJmsTemplate")` or `@Qualifier("expiringJmsTemplate")`.

Templates are shared by **policy**, not by request. Two templates can share the same `ConnectionFactory` while differing in QoS, converters, or default destinations. When the number of policies is small and stable, this is easier to test and less error-prone than mutating setters per request.

### Approach 3 — Policy derived from business logic

If QoS depends on an event's priority tier, the service should resolve the policy via an enum or value object and pass the QoS tuple into a producer callback. Never let callers pass arbitrary priority/TTL numbers from an HTTP request without validation: `priority` must be in 0..9, TTL non-negative, preventing overly long-lived messages and starvation caused by high priorities.

## 9. Complete runnable example: one template, two send styles

The **Java 17 + Spring Boot 3.3.5 + embedded Artemis** example illustrates two sends to the same Queue:
1. Regular message uses the template's shared QoS: `priority=4, TTL=60_000 ms`.
2. Urgent message uses `ProducerCallback` with per-send QoS: `priority=8, TTL=10_000 ms`.

Each message carries its own `kind` property. On receive, selectors pick each message **independently of broker delivery order**, verifying actual priority and correlation IDs. The embedded broker uses `persistent: false` for lab convenience, so this example does not demonstrate durability across restarts.

### Project structure

~~~text
jms-template-policy/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/application.yml
    └── java/example/jms/SharedPerCallDemo.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'jms-template-policy'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

The Spring Boot BOM manages Spring/Artemis versions tested together. For projects on another Boot version, use the dependency management of **that project's own Boot version**, rather than mixing arbitrary Jakarta/Artemis JARs.

### src/main/resources/application.yml

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.orders
      persistent: false
~~~

### src/main/java/example/jms/SharedPerCallDemo.java

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SharedPerCallDemo {

    public static void main(String[] args) {
        SpringApplication.run(SharedPerCallDemo.class, args);
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setDefaultDestinationName("demo.orders");
        template.setPubSubDomain(false); // Queue
        template.setReceiveTimeout(3_000L);

        // Shared policy for regular convertAndSend / send.
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
        template.setPriority(4);
        template.setTimeToLive(60_000L);
        return template;
    }

    @Bean
    ApplicationRunner demonstrate(JmsTemplate template) {
        return args -> {
            // Call 1: still uses shared QoS, only adding property/header.
            template.convertAndSend("regular", message -> {
                message.setStringProperty("kind", "STANDARD");
                message.setJMSCorrelationID("cid-normal");
                return message;
            });

            // Call 2: QoS tuple passed specifically for this send.
            // No setters mutated on the singleton JmsTemplate.
            template.execute("demo.orders", (session, producer) -> {
                TextMessage msg = session.createTextMessage("urgent");
                msg.setStringProperty("kind", "URGENT");
                msg.setJMSCorrelationID("cid-urgent");

                producer.send(
                        msg, DeliveryMode.NON_PERSISTENT, 8, 10_000L);
                return null;
            });

            // Selectors avoid depending on priority-based delivery order.
            Message standardMessage = template.receiveSelected(
                    "demo.orders", "kind = 'STANDARD'");
            Message urgentMessage = template.receiveSelected(
                    "demo.orders", "kind = 'URGENT'");

            if (!(standardMessage instanceof TextMessage standard)) {
                throw new IllegalStateException(
                        "STANDARD message not received");
            }
            if (!(urgentMessage instanceof TextMessage urgent)) {
                throw new IllegalStateException(
                        "URGENT message not received");
            }

            System.out.println("STANDARD|" + standard.getText()
                    + "|priority=" + standard.getJMSPriority()
                    + "|cid=" + standard.getJMSCorrelationID());
            System.out.println("URGENT|" + urgent.getText()
                    + "|priority=" + urgent.getJMSPriority()
                    + "|cid=" + urgent.getJMSCorrelationID());
        };
    }
}
~~~

`ApplicationRunner.run` allows `throws Exception`, so calling JMS header/payload methods that throw checked `JMSException` compiles directly here. In normal services, Spring templates handle checked `JMSException` inside callbacks and throw unchecked `JmsException` when needed.

### Running and observing

In the `jms-template-policy` directory, use JDK 17+ and a compatible Gradle version. If the project has a Gradle Wrapper, run `./gradlew bootRun`; otherwise run:

~~~bash
gradle bootRun
~~~

In PowerShell, the Wrapper (if present) is:

~~~powershell
.\gradlew.bat bootRun
~~~

After Spring/Artemis startup logs, the two lines **printed by application code itself** are expected to be:

~~~text
STANDARD|regular|priority=4|cid=cid-normal
URGENT|urgent|priority=8|cid=cid-urgent
~~~

The order of those two lines is **dictated by the program** receiving with selectors, not a guarantee that the broker always delivers STANDARD before URGENT. Fields such as `JMSMessageID`, `JMSTimestamp`, and `JMSExpiration` are set/interpreted by the provider, so avoid printing time- or implementation-dependent values into fixed expected output.

If a message does not arrive within 3 seconds, the check fails with a clear message. This lab confirms both send paths share the same `ConnectionFactory`/Queue while per-send QoS operates independently of the default state. Actual priority is a **delivery-priority hint** under JMS/provider rules, not a guarantee that urgent business tasks always finish before normal ones.

### Additional verification without modifying the template

In integration tests, you can assert before and after both calls:
- `template.getDefaultDestinationName()` remains `demo.orders`.
- `template.getPriority()` remains `4`.
- `template.getTimeToLive()` remains `60_000L`.
- `template.isExplicitQosEnabled()` remains `true`.

These getters reflect bean configuration; the priority header on the received message confirms each send's effective QoS. Do not just check getters and assume the broker received the right message; perform a real round-trip.

## 10. Synchronous receive: per-call destination/selector, template-level timeout

`JmsTemplate` has overloads such as:
- `receive()`: receives from the default destination.
- `receive("billing.invoice.commands")`: receives from the destination specified for that call.
- `receiveSelected("billing.invoice.commands", "kind = 'STANDARD'")`: only receives messages whose JMS properties/headers match the selector.
- `receiveAndConvert("billing.invoice.commands")`: receives and converts the JMS Message into an application object via the converter.

**Selectors do not read JSON fields in the body.** They apply to JMS headers/properties per JMS selector syntax; if filtering on `kind` is needed, the publisher must set that property on the JMS Message.

`setReceiveTimeout(3_000L)` is a setting on the template object, not a parameter to `receiveSelected(...)`. Wrong approach:

~~~java
template.setReceiveTimeout(100L);
Message m = template.receive("billing.invoice.commands");
template.setReceiveTimeout(3_000L);
~~~

If multiple threads share the template, another thread's second call might accidentally use a 100 ms timeout. Repeated setter updates also make tests flaky.

The right approach when two stable policies exist: declare two templates with different timeouts, or build a dedicated adapter/consumer using `SessionCallback` with JMS `MessageConsumer.receive(timeout)` and careful consumer/resource management. Pick the simplest approach that satisfies requirements.

**Receiving with the template is not a long-lived listener.** In applications with continuous asynchronous processing, `@JmsListener` is usually used; synchronous receiving suits certain request/reply workflows, testing tools, or application-paced consumption.

## 11. Listener containers have separate configuration from JmsTemplate

A common misconception: “Since I called `jmsTemplate.setSessionTransacted(true)`, every `@JmsListener` will roll back the same way.” This is false because listener containers use a **separate factory**.

~~~java
@Configuration
@EnableJms
class ListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);        // Queue
        factory.setSessionTransacted(true);    // For JMS listener sessions
        factory.setConcurrency("1-3");        // Listener resources
        return factory;
    }
}
~~~

Required imports in a complete Spring class are `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration`, `org.springframework.jms.annotation.EnableJms`, and `org.springframework.jms.config.DefaultJmsListenerContainerFactory`. The snippet above is an illustrative configuration fragment, not a standalone program.

Inside a listener:

~~~java
@JmsListener(destination = "billing.invoice.commands")
public void handle(String payload) {
    processInvoice(payload);
}
~~~

Here `processInvoice` is an application-provided business method. `@JmsListener` is only affected by the template if code inside the listener **explicitly injects/calls the template to send or receive further**; the listener's own message consumption is governed by its container factory and transaction manager.

Do not set a tiny `receiveTimeout` on the template expecting the listener container to change its polling timeout or scheduling. Container settings and template settings have separate scopes.

## 12. Transactions and sharing ConnectionFactory

“Shared” configuration does not mean transactions automatically bundle all operations with a database or across multiple brokers.

- `JmsTemplate` can participate in Spring-managed JMS transactions when configured with the right transaction manager/resources. `setSessionTransacted(true)` governs local session transactions when no higher-level transaction manager applies; check active transaction state.
- `@Transactional` applies only to the transaction manager bound to that call. A DB transaction and a JMS transaction are normally **two separate resources**; committing one does not automatically ensure atomic commit of the other.
- If business logic needs DB + publish atomicity, evaluate transactional outbox or appropriate transaction solutions; do not treat injecting the same `ConnectionFactory` as an XA guarantee.
- When a listener encounters an error and **swallows the exception**, the container may ACK/commit the message as succeeded. Rollback/redelivery/DLQ policies must be configured and tested in practice.
- On producer timeout, the send outcome can be uncertain: the broker received the message, yet the response was lost. Design event IDs/idempotent consumers to guard against duplicates regardless of whether a shared template or custom callback was used.

**One template can be reused across multiple threads**, yet it does not turn independent sends into a single transaction. Transactions attach to resources and thread/transaction-manager scopes, not “history” stored inside a singleton template.

## 13. Designing configuration around requirement stability

| Scenario | Appropriate solution | Why |
|---|---|---|
| All commands share broker, converter, QoS | One singleton `JmsTemplate` | Simple, reuses stable configuration. |
| Each message carries a different correlation ID/tenant tag | `convertAndSend(..., MessagePostProcessor)` | Headers/properties attach to that message without affecting other calls. |
| One send needs a different destination | `convertAndSend(destinationName, ...)` overload | Leaves the bean's default destination unchanged. |
| Special payload bypassing shared converter | `send(..., MessageCreator)` | Builds the exact JMS message for that call. |
| One send needs a different priority/TTL | `execute(..., ProducerCallback)` with `producer.send(msg, mode, priority, ttl)` | QoS is passed directly to that specific send. |
| Two message classes have distinct stable QoS | Two template beans and `@Qualifier` | Explicit policies without runtime state mutation. |
| Two different brokers | Two `ConnectionFactory` beans + named templates | Separates connections/auth/transactions and routing. |
| Each consumer listener needs different concurrency/ack | Multiple `JmsListenerContainerFactory` beans or per-endpoint config | Listeners do not use the template's receive policies to operate. |
| One flow needs a shorter receive timeout | Separate template or appropriate receive callback | Avoids mutating `setReceiveTimeout` while the app is running. |

If a method repeatedly sets setters before sending, that is a signal to refactor. Passing “per-request” settings into callbacks keeps behavior readable at the call site and avoids thread-ordering dependencies.

## 14. Common mistakes and consequences

### Mistake 1 — Mutating a shared JmsTemplate before each send

~~~java
// Do not use: race condition when multiple threads share the bean.
jmsTemplate.setPriority(9);
jmsTemplate.convertAndSend("urgent");
jmsTemplate.setPriority(4);
~~~

With `explicitQosEnabled=false`, this may not even take effect. With `true`, other threads can mistakenly send with priority 9. Even a `try/finally` resetting priority does not make this thread-safe.

**Fix:** `ProducerCallback` with per-send QoS or a dedicated policy template bean.

### Mistake 2 — Setting JMSPriority in MessagePostProcessor and treating it as real QoS

~~~java
// Do not use as a way to enforce priority on producer.send.
jmsTemplate.convertAndSend("urgent", message -> {
    message.setJMSPriority(9);
    return message;
});
~~~

The provider/template may overwrite the `JMSPriority` header with `producer.send`'s QoS. **Fix:** use the `producer.send` overload with explicit priority.

### Mistake 3 — Confusing message converter and message post processor

`MessageConverter` defines how **data types** convert: e.g., String → TextMessage, domain object → JSON TextMessage. `MessagePostProcessor` adjusts a **message already created by the converter** (headers/properties, correlation ID, metadata). Do not write a new converter just to add a per-request property.

### Mistake 4 — Believing `@JmsListener` obeys JmsTemplate settings

A listener can still run with concurrency 1 and auto-ack even if the publisher template uses `setSessionTransacted(true)`. **Fix:** inspect `DefaultJmsListenerContainerFactory`, transaction managers, and broker policies.

### Mistake 5 — Extending callback scope beyond its execution boundary

`Session` and `MessageProducer` must never be stored in fields and reused after `execute(...)` returns. Low-level JMS objects have lifecycles managed by the container/provider. Keep callbacks completely within a single call.

### Mistake 6 — Letting every service mutate receive timeout/default destination

Calling setters directly on an injected singleton causes cross-service side effects. **Fix:** pass destination/selector per call, use a separate template for different timeouts, or specialize an adapter.

### Mistake 7 — Treating TTL, priority, or persistent as business processing guarantees

TTL governs message validity; priority is a delivery hint; persistent delivery still depends on broker and storage policies. None of these settings automatically guarantee exactly-once in a database or business-handler completion ordering.

## 15. Testing checklist before production rollout

1. **Bean wiring:** confirm only one default bean exists when services inject `JmsTemplate` without a qualifier; if multiple beans exist, use `@Qualifier` or explicit primary config.
2. **Concurrency:** have two threads send payloads with different correlation IDs; confirm no property leaks across messages and no runtime setters exist in services.
3. **Destination:** test default and explicit destinations; verify Queue/Topic/routing types and broker ACLs.
4. **QoS:** compare `JMSPriority`, `JMSDeliveryMode`, and `JMSExpiration` on received messages alongside broker TTL policies; do not check only template getters.
5. **Callback exceptions:** simulate a provider `JMSException` and verify Spring throws `JmsException` and releases resources.
6. **Receive:** test timeouts, matching and non-matching selectors, and `null` handling on timeout.
7. **Transactions:** test consumer rollback, redelivery, DLQ, and resending after timeouts; ensure business logic is idempotent.
8. **Environments:** test on exact JDK/Spring/broker versions, verifying TLS/credentials and config across dev/staging/prod; never treat embedded results as production proof.
9. **Observability:** log correlation ID, logical destination, delivery attempts, and causes; avoid logging sensitive payload data.

During code reviews, ask: **“Does this operation mutate bean state, or only configure the message being sent?”** If a setter is called on a singleton inside a request/handler, move that logic into arguments, callbacks, or a separate bean.

## 16. Self-check questions

**Question 1.** Two services inject the same `JmsTemplate`. Service A wants to send to `billing.invoice.cancel` instead of the default Queue. Does it need to call `setDefaultDestinationName`?

**Answer:** No. Use `convertAndSend("billing.invoice.cancel", payload)`; the template keeps its default name for all other calls.

**Question 2.** An event must carry a per-request `JMSCorrelationID` and an `eventType` property. What should you choose?

**Answer:** `convertAndSend(destination, payload, message -> { ...; return message; })` with `MessagePostProcessor`. Validate/bound property length and format if sourced externally.

**Question 3.** One message needs a 5-second TTL while all others use a 60-second TTL. Why can calling `setTimeToLive(5_000L)` and then resetting to `60_000L` be wrong?

**Answer:** The setter mutates shared template state. Another thread might send while TTL is 5 seconds, causing its message to expire prematurely. Use `ProducerCallback` with TTL passed into `send`, or a separate template configured with its own policy.

**Question 4.** You called `setPriority(9)` yet received messages still carry the default priority. What should you check?

**Answer:** `setExplicitQosEnabled(true)`, the actual send path, and provider/broker policies. For per-send QoS, verify `producer.send(msg, mode, priority, ttl)` rather than just setters.

**Question 5.** `@JmsListener` does not roll back when the handler fails even though the publisher uses `JmsTemplate.setSessionTransacted(true)`. Why?

**Answer:** The publisher template and listener container have separate configurations; verify `JmsListenerContainerFactory`, transaction manager, handler exceptions, and redelivery policy.

**Question 6.** When two consumers use a shared template, messages have different `JMSCorrelationID`s yet a priority queue reorders them. Is that evidence of a race on the template?

**Answer:** No. Priority and provider policies can affect delivery order. Inspect the body and headers of each message rather than relying on log ordering across multiple producers/consumers.

## 17. Official references

- [Spring Framework 6.2 — Using JMS: JmsTemplate, QoS configuration, and thread safety](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html).
- [Spring Framework 6.2 — Sending a Message: MessageCreator and MessagePostProcessor](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html).
- [Spring Framework 6.2.14 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html).
- [Spring Framework 6.2 — ProducerCallback Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/ProducerCallback.html).
- [Spring Framework — Annotation-driven JMS listener containers](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html).
- [Spring Boot 3.3 — JMS and Artemis configuration](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html).
- [Jakarta Messaging 3.1 — JMS MessageProducer send and Quality of Service](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1).
