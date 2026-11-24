# defaultDestination and defaultDestinationName in Spring JMS

**Scope:** Spring Framework - jms → Destination.

## 1. Why does JmsTemplate need a default destination?

In JMS/Jakarta Messaging, a **destination** is where a producer sends messages or a consumer receives messages. A destination is typically a `Queue` (point-to-point) or a `Topic` (publish/subscribe). Spring Framework provides `JmsTemplate` so applications do not have to repeat opening connections/sessions, creating producers, and converting messages.

If a service primarily sends to the same queue, repeating the destination name:

~~~java
jmsTemplate.convertAndSend("orders.created", "order-101");
jmsTemplate.convertAndSend("orders.created", "order-102");
jmsTemplate.convertAndSend("orders.created", "order-103");
~~~

can be replaced by configuring a **default destination**:

~~~java
jmsTemplate.setDefaultDestinationName("orders.created");

jmsTemplate.convertAndSend("order-101");
jmsTemplate.convertAndSend("order-102");
jmsTemplate.convertAndSend("order-103");
~~~

Both snippets assume `jmsTemplate` has already been created from a valid `ConnectionFactory`. The second snippet works because `convertAndSend(Object)` is an **overload without a destination parameter**. Spring retrieves the default destination of that `JmsTemplate` instance and sends the message there.

There are two configuration options:

- **`defaultDestination`:** a `jakarta.jms.Destination` object already supplied by the provider/application server.
- **`defaultDestinationName`:** a `String` representing the destination name; `JmsTemplate` uses `DestinationResolver` to turn the name into an object.

These are **two ways to represent a default target on Spring's JmsTemplate**. They are not two JMS destination types, do not create a broker, and do not dictate which queue every listener in the application must listen to.

## 2. Comparing defaultDestination and defaultDestinationName

| Criterion | `defaultDestination` | `defaultDestinationName` |
| --- | --- | --- |
| Configuration value | `jakarta.jms.Destination` object | `String` name |
| Setter | `setDefaultDestination(Destination)` | `setDefaultDestinationName(String)` |
| Getter | `getDefaultDestination()` | `getDefaultDestinationName()` |
| How target is determined | Uses the existing object | Calls `DestinationResolver` with name and session |
| Example | `Queue`/`Topic` object injected from provider or JNDI | `"orders.created"` |
| Characteristics | Used when app already has an administered destination | Convenient for application.properties and Java Config |
| Affects `convertAndSend("payload")` | Yes | Yes |
| Affects `convertAndSend("other.queue", "payload")` | No | No |

Processing flow:

~~~text
                 SPRING APPLICATION
                         |
                 JmsTemplate
                         |
      +------------------+------------------+
      |                                     |
defaultDestination                    defaultDestinationName
 (Destination object)                       (String)
      |                                     |
      |                               DestinationResolver
      |                                     |
      +------------------+------------------+
                         |
                     Destination
                         |
                  JMS Session/Producer
                         |
                    JMS provider
                         |
                   Queue or Topic
~~~

Key point: **the default destination is only used when the method is not passed an explicit destination**. If most operations specify a destination explicitly, the application is not required to configure a default.

## 3. Which methods use the default destination?

The table below distinguishes overloads of `org.springframework.jms.core.JmsTemplate`:

| Method | Destination source |
| --- | --- |
| `convertAndSend(Object message)` | Configured default |
| `send(MessageCreator creator)` | Default |
| `convertAndSend(Object message, MessagePostProcessor postProcessor)` | Default |
| `receive()` / `receiveAndConvert()` | Default |
| `receiveSelected(String selector)` | Default, plus selector |
| `sendAndReceive(MessageCreator creator)` | Default for the **request** destination |
| `convertAndSend(String destinationName, Object message)` | Passed destination name |
| `convertAndSend(Destination destination, Object message)` | Passed destination object |
| `send(String destinationName, MessageCreator creator)` | Passed name |
| `receive(String destinationName)` | Passed name |

Example:

~~~java
jmsTemplate.setDefaultDestinationName("orders.normal");

// One argument: payload sent is "order-101", destination is orders.normal.
jmsTemplate.convertAndSend("order-101");

// Two arguments: sends payload "order-202" to orders.priority.
jmsTemplate.convertAndSend("orders.priority", "order-202");
~~~

These are **two messages going to two different queues**, despite using the same template. Setting a default does not lock `JmsTemplate` to a single destination.

Pay special attention to the difference between:

~~~java
jmsTemplate.convertAndSend("orders.created");
jmsTemplate.convertAndSend("orders.created", "hello");
~~~

The first line treats `"orders.created"` as the **payload** and sends it to the **default**. The second line treats `"orders.created"` as the **destinationName**, while `"hello"` is the payload. This is an overload-confusion bug that can send messages to the wrong queue while still compiling cleanly.

If no default is set and you call an overload without a destination, Spring throws `IllegalStateException` with a message similar to:

~~~text
No 'defaultDestination' or 'defaultDestinationName' specified. Check configuration of JmsTemplate.
~~~

The fix is to **set a default** or **choose an overload with an explicit destination**.

## 4. defaultDestinationName: how is the String name resolved?

### 4.1. Configuring in Java

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

// connectionFactory must be provided beforehand by the provider or Spring.
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDefaultDestinationName("orders.created");
template.setPubSubDomain(false); // false => queue, which is the default configuration
template.convertAndSend("order-101");
~~~

This snippet is not standalone because it requires `connectionFactory`, a broker, and the corresponding destination. `setDefaultDestinationName` spares the application from writing out the queue name on every `convertAndSend` call.

### 4.2. DestinationResolver is the intermediary

`DestinationResolver` is the interface:

~~~java
Destination resolveDestinationName(
        Session session, String destinationName, boolean pubSubDomain
) throws JMSException;
~~~

Spring uses `DynamicDestinationResolver` by default. The resolver takes a `Session` and can call:

~~~java
session.createQueue("orders.created"); // if pubSubDomain=false
session.createTopic("orders.events"); // if pubSubDomain=true
~~~

This is an **illustrative excerpt** showing both cases; actual code chooses one of the two based on the boolean. With `defaultDestinationName="orders.created"` and `pubSubDomain=false`, Spring resolves it to a queue object and uses it for sending/receiving.

**Do not confuse resolving an object with provisioning on the broker.** `Session.createQueue(name)` only returns a `Queue` object per the JMS interface; whether the broker allows auto-creating physical queues or requires an admin to pre-create them depends on the provider and environment configuration. Thus a syntactically valid default configuration can still fail on send if the queue does not exist or the account lacks permissions.

### 4.3. A String name does not imply JNDI lookup

`DynamicDestinationResolver` **does not** use JNDI by default. If the application server provides queues/topics as JNDI administered objects, Spring offers `JndiDestinationResolver`:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;

@Configuration
class JndiJmsConfiguration {

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory factory) {
        JndiDestinationResolver resolver = new JndiDestinationResolver();
        resolver.setCache(true);

        JmsTemplate template = new JmsTemplate(factory);
        template.setDestinationResolver(resolver);
        template.setDefaultDestinationName("java:comp/env/jms/Orders");
        return template;
    }
}
~~~

This configuration compiles when Spring JMS dependencies are present, **but only works** if the environment actually has a JNDI context and the corresponding `java:comp/env/jms/Orders` name. Do not assume every JMS provider implements this JNDI structure.

### 4.4. pubSubDomain determines Queue or Topic during name resolution

| `pubSubDomain` | Destination type with `DynamicDestinationResolver` | Meaning |
| --- | --- | --- |
| `false` (default) | `Queue` | One message is processed by one competing consumer per delivery |
| `true` | `Topic` | Each matching subscription can receive a copy of the message per publish/subscribe rules |

The name `"events"` **does not by itself determine** the destination type. If the template sets `pubSubDomain=true`, the resolver creates/resolves a Topic object; consumers/listeners must also be configured with the right domain and subscription. Changing `pubSubDomain` can direct messages to a target with different semantics even if the string name stays unchanged.

With a directly assigned `Destination` object, Spring does not use this boolean to convert a Queue object into a Topic object. The supplied object already represents a specific destination.

## 5. defaultDestination: passing a Destination object directly

When the application holds a `jakarta.jms.Destination` object, configure:

~~~java
import jakarta.jms.Destination;
import org.springframework.jms.core.JmsTemplate;

// connectionFactory and ordersQueue are objects provided beforehand.
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDefaultDestination(ordersQueue);
template.convertAndSend("order-101");
~~~

**This is an illustrative excerpt**; `ordersQueue` has type `Destination` created beforehand by the provider/container/lookup. You cannot call `new Destination()` because it is an interface.

A Spring configuration can inject an administered destination object:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
class ObjectDestinationConfig {

    @Bean("objectBasedJmsTemplate")
    JmsTemplate objectBasedJmsTemplate(
            ConnectionFactory connectionFactory,
            @Qualifier("ordersQueue") Destination ordersQueue) {

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDefaultDestination(ordersQueue);
        return template;
    }
}
~~~

To run this configuration, an **actual `ordersQueue` bean** must exist and be compatible with `ConnectionFactory`. The example does not provide that bean itself because how administered destinations are created varies by provider/JNDI. Once the object is in hand, Spring uses it directly rather than resolving a String by name.

**Portability note:** a `Queue` or `Topic` object may carry provider-specific information. Do not assume an Artemis object can always be moved to IBM MQ or another broker without conversion.

### 5.1. The two setters are mutually exclusive alternatives

In `JmsTemplate`, the default can be stored as a `Destination` **or** a `String`. Do not set both and expect both settings to remain active together.

~~~java
template.setDefaultDestinationName("orders.a");
template.setDefaultDestination(ordersQueue);
~~~

In Spring Framework 6.x's implementation, the setter called later replaces the previous default representation. Thus in the snippet above, the active default is `ordersQueue`. Avoid relying on setter ordering across multiple configuration files or bean post-processors; **choose only one form per template**.

The getters reflect whichever form is currently stored:

~~~java
template.getDefaultDestination();     // Destination or null
template.getDefaultDestinationName(); // String or null
~~~

If configured via `setDefaultDestinationName`, `getDefaultDestination()` returning `null` is completely normal behavior. Check the getter matching how it was configured.

## 6. Spring Boot configuration with application.properties

In Spring Boot 3.x, when using a JMS starter with an auto-configured template, the property for setting the default destination name is:

~~~properties
spring.jms.template.default-destination=demo.orders.default
spring.jms.pub-sub-domain=false
~~~

Even though the Boot property is named `default-destination`, its value here is a **name string**, applied by Spring to the template's default destination configuration, not a Java `Destination` object.

| Configuration | What does it do? |
| --- | --- |
| `spring.jms.template.default-destination=demo.orders.default` | Target name used when `JmsTemplate` receives no destination |
| `spring.jms.pub-sub-domain=false` | Resolves names as queues (default configuration) |
| `spring.jms.pub-sub-domain=true` | Resolves names as topics |
| `spring.jms.template.receive-timeout=2s` | Wait limit for synchronous receive operations |
| `spring.artemis.mode=native` | Connects to an Artemis broker running outside the application |
| `@JmsListener(destination="demo.orders.default")` | Receiving target of **an individual listener endpoint**, independent of the template's default |

The exact Boot property name is **`spring.jms.template.default-destination`**. Do not assume a property `spring.jms.template.default-destination-name` exists.

If you declare your own `@Bean JmsTemplate`, Boot may skip creating the default bean and will not automatically apply properties to your custom bean as you might expect. In that case, configure the bean explicitly or use `JmsTemplateConfigurer` appropriate for your Boot version. An application should have a single, easy-to-audit source of configuration.

## 7. Runnable Java 17+ example: default and explicit destinations

This example uses **Spring Boot 3.x**, Java 17+, the Artemis JMS client, and **an external Artemis broker**. It sends two messages: one using the default queue, and one using an explicit destination. Two `@JmsListener`s help confirm both messages arrive at the right places.

### 7.1. Preparation

Create a Maven project on [Spring Initializr](https://start.spring.io/) with:

- Group: `com.example`; Artifact: `jms-default-demo`; Java: **17+**.
- Dependency: **Spring for Apache ActiveMQ Artemis**, artifact `org.springframework.boot:spring-boot-starter-artemis`.
- An Artemis broker running at `tcp://localhost:61616`, with an account permitted to send/consume.
- Two queues `demo.orders.default` and `demo.orders.explicit` provisioned or auto-created by the broker per its policy.

Set environment variables `ARTEMIS_USER`, `ARTEMIS_PASSWORD`. File `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}

spring.jms.pub-sub-domain=false
spring.jms.template.default-destination=demo.orders.default
~~~

`mode=native` **does not start a broker** inside the application. The template will be auto-configured by Boot with the name `demo.orders.default` if JMS auto-configuration conditions are met.

File `src/main/java/com/example/JmsDefaultDestinationApplication.java`:

~~~java
package com.example;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsDefaultDestinationApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsDefaultDestinationApplication.class, args);
    }

    @Bean
    ApplicationRunner publish(JmsTemplate template) {
        return args -> {
            System.out.println(
                    "DEFAULT=" + template.getDefaultDestinationName());

            // Uses default destination: demo.orders.default.
            template.convertAndSend("order-101");

            // Passes explicit destination: demo.orders.explicit.
            template.convertAndSend(
                    "demo.orders.explicit", "order-202");
        };
    }
}

@Component
class DefaultQueueConsumer {

    @JmsListener(destination = "demo.orders.default")
    public void receive(String payload) {
        System.out.println("DEFAULT_RECEIVED=" + payload);
    }
}

@Component
class ExplicitQueueConsumer {

    @JmsListener(destination = "demo.orders.explicit")
    public void receive(String payload) {
        System.out.println("EXPLICIT_RECEIVED=" + payload);
    }
}
~~~

All classes sit in one Java file: there is exactly **one public class** matching the filename; the other two components are package-private, valid in Java. Spring Boot has JMS infrastructure from the starter and automatically detects `@JmsListener` in component-scanned packages.

### 7.2. Running and output

At the Maven project root:

~~~bash
mvn spring-boot:run
~~~

If using Maven Wrapper on Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

When the broker and queues/ACLs are properly prepared and there are no leftover messages, typical business output lines are:

~~~text
DEFAULT=demo.orders.default
DEFAULT_RECEIVED=order-101
EXPLICIT_RECEIVED=order-202
~~~

Spring startup logs also appear; the two `*_RECEIVED` lines may appear in reverse order because listeners process asynchronously. This is **expected stdout when infrastructure conditions are right**, not output from an actual broker run in the authoring environment.

**Cross-check:** `DEFAULT=...` confirms the name configured on `JmsTemplate`; the first listener receives the message sent by the one-argument overload; the second listener receives the message sent by the two-argument overload.

### 7.3. Why does default not change @JmsListener?

`@JmsListener(destination="...")` configures a message-receiving endpoint with its own destination. `JmsTemplate`'s default is only used for operations on **that template** that omit a destination. The listener container is a separate component with its own configuration; it does not automatically inherit the default from `JmsTemplate`.

To select Queue/Topic for a listener, check the listener container configuration or the corresponding Boot property. Setting a default queue on the template does not make every listener listen to that queue automatically.

## 8. Java Config when not using Spring Boot properties

In plain Spring Framework or when configuring beans explicitly:

~~~java
package com.example.config;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsConfig {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        template.setDefaultDestinationName("demo.orders.default");
        return template;
    }
}
~~~

**Requirements to run:** a `ConnectionFactory` bean must exist, the provider library must be compatible with Jakarta JMS, and the broker must be reachable. In plain Spring, if you want listeners, you must also configure `@EnableJms` and an appropriate listener container factory. In Spring Boot, declaring a custom bean is unnecessary if auto-configuration already meets your needs.

### 8.1. Multiple templates, each with its own default

An application may have different business queues, for example:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
class MultipleJmsTemplates {

    @Bean("orderTemplate")
    JmsTemplate orderTemplate(ConnectionFactory factory) {
        JmsTemplate t = new JmsTemplate(factory);
        t.setDefaultDestinationName("orders.requests");
        return t;
    }

    @Bean("billingTemplate")
    JmsTemplate billingTemplate(ConnectionFactory factory) {
        JmsTemplate t = new JmsTemplate(factory);
        t.setDefaultDestinationName("billing.requests");
        return t;
    }
}
~~~

In services, inject the right template via `@Qualifier("orderTemplate")` or `@Qualifier("billingTemplate")`. Configuring multiple templates means managing bean names/injection precedence clearly; if Spring sees multiple beans of the same type without a qualifier/primary, it may not know which bean to pick.

With multiple brokers/providers, each template must be bound to the **matching system's** `ConnectionFactory`, because a default destination does not automatically bridge messages across different brokers.

## 9. When to use a default name and when not to?

**Use a default destination when:**

- A service primarily publishes messages to **one stable queue or topic**.
- Each runtime environment has a different destination name and the name is externalized to configuration rather than hardcoded in business code.
- You want to reduce repetitive code and ensure a group of operations in the same publisher uses the same target.
- Tests verify that the default matches the producer/consumer contract.

**Specify an explicit destination when:**

- A service sends multiple message types to different destinations.
- The target validly varies by message type or tenant.
- You want the target visible right at the call site for easier review/auditing.
- You want to avoid depending on a shared default that could be misconfigured.
- Writing a reusable library without knowing the integrating application's destination in advance.

Example:

~~~java
// Publisher dedicated to one queue: uses the template's default.
jmsTemplate.convertAndSend("order-101");

// Multi-purpose service: destination stated explicitly at the call site.
jmsTemplate.convertAndSend("audit.events", "audit-101");
jmsTemplate.convertAndSend("billing.commands", "invoice-202");
~~~

For multi-tenant systems, **never** set the default per request with `setDefaultDestinationName(tenantQueue)` on a shared singleton `JmsTemplate`. Multiple threads can mutate the state of the same bean, leading to sending to the wrong queue. Use the explicit-destination overload or multiple statically configured templates.

### 9.1. Default does not determine message format

Both properties relate only to the **send/receive destination**. They do not alter the payload, enable JSON conversion, or set `JMSCorrelationID`. The default `SimpleMessageConverter` handles `String` as `TextMessage`, byte[] as `BytesMessage`, and other compatible types per converter policy.

If sending a POJO, check `MessageConverter` first: you cannot assume an arbitrary POJO turns into JSON just because `defaultDestinationName` is set. The runnable example in this lesson uses `String` to avoid needing an extra JSON converter.

## 10. Relationship with JMSDestination, JMSReplyTo, and sendAndReceive

Do not confuse the **template's default** with **message headers**:

| Concept | Purpose |
| --- | --- |
| `JmsTemplate.defaultDestinationName` | Chooses the destination name if the template call omits a destination |
| `Message.getJMSDestination()` | Provider records the actual destination of the sent message |
| `Message.getJMSReplyTo()` | Where the sender wants replies sent (may be null) |
| `Message.getJMSCorrelationID()` | Application data used to correlate messages/replies |
| `@JmsListener(destination = "...")` | Where a listener endpoint receives messages |

When calling `jmsTemplate.convertAndSend("hello")`, Spring resolves the default before sending; the provider populates `JMSDestination` with that send's destination. Default **does not automatically set `JMSReplyTo`** and does not make the broker auto-generate replies.

With `JmsTemplate.sendAndReceive(messageCreator)` (no destination), the default is used as the **request** destination, while the request/reply mechanism uses a separate reply destination (typically a temporary queue) and an appropriate timeout. Do not send replies back to the default merely because the configured name looks similar.

## 11. Receive, timeout, and common errors

`JmsTemplate`'s `receive()` and `receiveAndConvert()` also use the default if no destination is given. This is **synchronous receiving**, unlike listeners which run asynchronously. If no message is present, it can block depending on the timeout.

~~~java
import org.springframework.jms.core.JmsTemplate;

// template has a valid ConnectionFactory and default destination.
jmsTemplate.setReceiveTimeout(2_000);
Object value = jmsTemplate.receiveAndConvert();
System.out.println(value == null ? "NO_MESSAGE" : value);
~~~

With `receiveTimeout = 2000` ms, if the wait expires without receiving a message, it returns `null`. The example has no fixed stdout when the broker already has messages or multiple consumers are reading concurrently. In Boot you can set:

~~~properties
spring.jms.template.receive-timeout=2s
~~~

Diagnostic table:

| Situation | Possible cause | Resolution |
| --- | --- | --- |
| No default, calling `convertAndSend(payload)` | Template has neither default object nor default name | Set a default or call an overload passing destination |
| `getDefaultDestination() == null` yet sending works | Configured via String name | Check `getDefaultDestinationName()` |
| Message goes to the wrong queue | Wrong overload used or default points to wrong target | Check method signature, default name, and explicitly passed name |
| Template switches to topic | `pubSubDomain=true` | Align domain across producer, consumer, and resolver |
| Cannot find destination | Wrong name, JNDI lookup failed, queue not provisioned | Check resolver, broker resources, and ACLs |
| Boot property has no effect | Custom JmsTemplate bean created, overriding auto-config | Reconfigure custom bean or use Boot configurer |
| Listener does not receive message | `@JmsListener` listens to another destination, listener not running | Check listener endpoint and broker queue depth |
| `receiveAndConvert()` waits forever | Unsuitable receive timeout, empty queue | Configure timeout; for long-running consumers use a listener |
| Send succeeds yet conversion fails | `MessageConverter` does not support payload | Use String/byte[] or an appropriate converter |
| Works in dev, fails in prod | Dev auto-creates queues while prod requires provisioning | Administer destinations on broker, permissions, and naming |
| Multiple requests overwrite default | Singleton template mutated concurrently | Keep default immutable after setup, use explicit overloads |

Creating a `JmsTemplate` bean does not prove the broker is online: the client may open connections only on the first send/receive. Also check `ConnectionFactory`, host/port, TLS, credentials, queue/topic permissions, and networking.

## 12. Misconceptions to avoid

1. **"defaultDestinationName is a JMS header name."** No. It is Spring configuration for selecting a destination.
2. **"defaultDestination takes a String."** No. This setter takes a `Destination`; String names use `setDefaultDestinationName`.
3. **"Once default is set, every send goes there."** No. Overloads with an explicit destination still use the passed target.
4. **"A String is always looked up via JNDI."** No. The default resolver is `DynamicDestinationResolver`.
5. **"Setting defaultDestinationName automatically creates the queue on every broker."** No. Physical provisioning depends on the provider and policy.
6. **"getDefaultDestination returning null means unconfigured."** Not necessarily. It may be configured as a String; check the name getter.
7. **"spring.jms.template.default-destination configures all @JmsListener endpoints."** No. Listeners have their own destinations.
8. **"defaultDestinationName decides Queue vs Topic from the name."** No. With the dynamic resolver, `pubSubDomain` decides the domain.
9. **"There is only one JmsTemplate for the whole system."** No. You can create multiple templates each with its own default, with clear injection.
10. **"To send dynamically, change the default on every request."** Dangerous with a concurrently shared singleton; pass the destination at call time instead.
11. **"Setting a default enables transactions or guarantees exactly-once."** No. Ack, transactions, retries, redelivery, and idempotency are separate concerns.
12. **"A single String parameter in convertAndSend(String) is the queue name."** Wrong. It is the payload; to pass a queue name, use the two-argument overload or `send(String, MessageCreator)`.

## 13. Self-check questions

**Question 1.** `jmsTemplate.setDefaultDestinationName("queue.a")` has been called. Where does `jmsTemplate.convertAndSend("hello")` send?

**Answer:** `queue.a`. `"hello"` is the payload and is converted into a JMS message by the converter.

**Question 2.** On the same template, you call `convertAndSend("queue.b", "hello")`. Is the default used?

**Answer:** No. The message goes to `queue.b` because the two-argument overload passes an explicit destination.

**Question 3.** What is the difference between `defaultDestination` and `defaultDestinationName`?

**Answer:** The former is a `Destination` object; the latter is a String name converted into an object by `DestinationResolver` at operation time.

**Question 4.** By default, what type does `DynamicDestinationResolver` resolve a name as?

**Answer:** Queue, because `pubSubDomain=false` by default. Set true if you want a topic, along with matching consumer configuration.

**Question 5.** Can `defaultDestinationName` be used to create a physical queue in the broker without checking provider configuration?

**Answer:** No. The JMS client creates a logical object; broker auto-create/provisioning is a separate mechanism.

**Question 6.** Why does a String-configured template still send normally when `getDefaultDestination()` returns null?

**Answer:** Because the default is currently stored as a `String`; `getDefaultDestinationName()` returns the configured name.

**Question 7.** A listener declares `@JmsListener(destination="queue.x")`. Does changing the template's default to `queue.y` switch the listener to `queue.y`?

**Answer:** No. The listener container manages the endpoint's destination independently.

**Question 8.** Should an application sending to different queues per tenant call `setDefaultDestinationName` before each send or pass the queue into send?

**Answer:** Pass the destination explicitly or use fixed templates injected for each role; avoid mutating a multi-threaded singleton.

## Official references

- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): using `JmsTemplate`, `DestinationResolver`, `pubSubDomain`, and default destinations.
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `send`/`convertAndSend` overloads with and without a destination.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): setters/getters and send/receive operations.
- [Spring Framework — DestinationResolver API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html): destination name resolution interface.
- [Spring Boot 3.5 — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.jms.template.default-destination` and `spring.jms.pub-sub-domain` properties.
- [Spring Boot — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html): Artemis native broker, auto-configured ConnectionFactory/JmsTemplate, and listeners.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): Queue, Topic, Destination, and JMS message semantics.
