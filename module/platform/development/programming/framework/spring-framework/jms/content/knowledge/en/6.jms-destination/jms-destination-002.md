# DestinationResolver and the Name Resolution Process in Spring JMS

## 1. The problem that DestinationResolver solves

When a Spring application sends a message with the call:

~~~java
jmsTemplate.convertAndSend("orders.requests", "ORDER-42");
~~~

"orders.requests" is a **String provided by the application**, whereas the JMS API actually needs a jakarta.jms.Destination object, typically jakarta.jms.Queue or jakarta.jms.Topic. Spring must have a way to translate a string name into the right Destination that the JMS provider understands.

The abstraction that does this is **org.springframework.jms.support.destination.DestinationResolver**. A DestinationResolver takes the name, a JMS Session, and whether it is a queue or topic, and returns a Destination. It allows business code to reference stable names without having to write JNDI lookups or Session.createQueue() at every send/receive site.

There are three common resolution approaches:

- **DynamicDestinationResolver**: uses the current JMS Session to create a Queue/Topic object by name; this is the default in JmsTemplate in Spring Framework 6.x.
- **JndiDestinationResolver**: looks up a JMS Destination already configured/bound in JNDI; includes caching and can optionally enable fallback to dynamic when lookup fails.
- **BeanFactoryDestinationResolver**: looks up a Spring bean with the matching name and type jakarta.jms.Destination.

This lesson distinguishes **name resolution**, **broker provisioning** (allocating/creating the physical destination on the broker), and **message delivery**. They are related, but they are not the same operation.

## 2. What is a Destination in JMS?

A JMS Destination is the target for sending or source for receiving messages. Two common types:

| JMS type | Meaning | Basic characteristics |
| --- | --- | --- |
| jakarta.jms.Queue | Point-to-point channel | Competing consumers on the same queue share messages; a message is consumed according to queue semantics. |
| jakarta.jms.Topic | Publish/subscribe channel | Each matching subscription can receive a delivery of the same message according to subscription policy. |

A Destination is not a message body, not a MessageConverter, and not an HTTP URL. A queue/topic can have different logical names, physical names, broker addresses, and permission rules depending on the provider.

Overview diagram:

~~~mermaid
flowchart LR
    A["Application: destinationName = orders.requests"] --> B["Spring JMS"]
    B --> C["DestinationResolver"]
    C --> D{"Strategy"}
    D --> E["Session.createQueue / createTopic"]
    D --> F["JNDI lookup"]
    D --> G["Spring BeanFactory lookup"]
    E --> H["jakarta.jms.Destination"]
    F --> H
    G --> H
    H --> I["JMS producer or consumer"]
    I --> J["Message broker"]
~~~

**Core point:** the resolver returns a Destination object for use with the JMS API. It **does not** prove that the queue has been declared, that permissions exist, that there is a consumer, or that messages will be persisted durably.

For example: the broker might allow the application to reference the name "orders.requests" but reject sending due to missing permissions; or the broker might only allow using queues pre-created by an administrator. Both cases lie outside the basic logic of turning a String into a Destination.

## 3. The DestinationResolver contract

In Spring Framework 6.x, the interface has the signature:

~~~java
package org.springframework.jms.support.destination;

import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Session;

@FunctionalInterface
public interface DestinationResolver {
    Destination resolveDestinationName(
            Session session,
            String destinationName,
            boolean pubSubDomain) throws JMSException;
}
~~~

This is an **illustrative signature** of the interface, not a file to copy into your project. Applications use the interface already provided in spring-jms; do not define a duplicate interface in the same package.

Explanation of each parameter:

| Parameter | Meaning |
| --- | --- |
| session | Current JMS Session. The dynamic resolver needs the session to call createQueue/createTopic; resolvers looking up registered resources might not use it. |
| destinationName | Name provided by code: for example "orders.requests" or "java:/jms/queue/Orders". Name semantics depend on the strategy. |
| pubSubDomain | true: requests publish/subscribe mode (Topic); false: point-to-point (Queue). Especially important during dynamic resolution. |
| Return value | Appropriate jakarta.jms.Destination, typically a Queue or Topic. |
| Errors | JMSException when the JMS API/provider fails; Spring's DestinationResolutionException when the name cannot be resolved by the strategy. |

The method name is **resolveDestinationName**, not createDestination; "resolve" means finding an appropriate representation. With JNDI, the result can be a pre-configured Queue/Topic object; with dynamic, it typically comes from Session.createQueue()/createTopic().

Some JmsTemplate methods take a **Destination object directly**, such as convertAndSend(Destination, Object). In that case the target object is already present, so the String does not need to go through DestinationResolver.

### 3.1. The contract can be implemented with a lambda

Because the interface has only one abstract method, it can be implemented with a lambda:

~~~java
DestinationResolver resolver = (session, name, pubSubDomain) -> {
    return pubSubDomain
            ? session.createTopic(name)
            : session.createQueue(name);
};
~~~

This is a Java snippet placed where DestinationResolver is imported and a JMS provider is present. The lambda above matches the basic dynamic resolver idea, without naming rules, logging, security, or provisioning.

### 3.2. Separating logical names and physical names

In large systems, business code may need to use a stable name like "orders.incoming", while the broker uses the address "corp.sales.orders.v2". A custom resolver can map between the two names:

~~~text
logical name:  orders.incoming
                      |
                      v
DestinationResolver: "corp.sales.orders.v2"
                      |
                      v
JMS Queue/Topic object sent to the broker
~~~

This is an application-designed policy, **not a built-in automatic mapping** for all resolvers.

## 4. The full resolution journey when sending

Consider sending with a String name:

~~~java
jmsTemplate.convertAndSend("orders.incoming", "ORDER-42");
~~~

Conceptual steps inside JmsTemplate:

1. Select the ConnectionFactory, and create/obtain a Connection and Session according to Spring configuration, transactions, and the active caching/pooling mechanism.
2. Receive the String "orders.incoming" as destinationName.
3. Call DestinationResolver.resolveDestinationName(session, "orders.incoming", pubSubDomain).
4. Receive a jakarta.jms.Destination object, such as a Queue.
5. Use MessageConverter to convert the String "ORDER-42" into a JMS Message, by default usually a TextMessage.
6. Use a JMS MessageProducer to send to the Destination, applying transactions, quality-of-service, and provider errors if any.
7. Release or return resources to the pool according to the Spring/provider mechanism.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant T as JmsTemplate
    participant R as DestinationResolver
    participant S as JMS Session
    participant B as Broker
    App->>T: convertAndSend("orders.incoming", payload)
    T->>R: resolveDestinationName(session, name, pubSubDomain)
    alt Dynamic
        R->>S: createQueue/createTopic(name)
        S-->>R: Destination
    else JNDI / Spring bean
        R->>R: lookup(name)
    end
    R-->>T: Destination
    T->>T: convert payload to JMS Message
    T->>B: send(message, Destination)
    B-->>T: result / exception
    T-->>App: complete / exception
~~~

This is a logical diagram; ConnectionFactory, transaction manager, caching, and the provider can alter specific resource-management steps. **DestinationResolver is not responsible for converting the payload**: MessageConverter handles that.

### 4.1. Role of the default destination

JmsTemplate can be configured with a default destination name:

~~~java
jmsTemplate.setDefaultDestinationName("orders.incoming");
jmsTemplate.convertAndSend("ORDER-42"); // Does not pass destination name at the call site.
~~~

When using defaultDestinationName, the name still needs to be resolved to a Destination. Conversely, if you configure defaultDestination with a **Destination object**, name-based lookup is not needed for that object.

Do not confuse calling convertAndSend(Object) with convertAndSend(String destinationName, Object). Method overload resolution determines whether the String is the **payload** or the **destination name**.

## 5. DynamicDestinationResolver: default and easy to start with

DynamicDestinationResolver resides in the package:

~~~java
org.springframework.jms.support.destination.DynamicDestinationResolver
~~~

This resolver relies on the current JMS Session:

~~~java
// Conceptual internal idea:
Destination destination = pubSubDomain
        ? session.createTopic(destinationName)
        : session.createQueue(destinationName);
~~~

This snippet illustrates the mechanism, not verbatim internal source code. When pubSubDomain=false, the name "orders.incoming" leads to a Queue; when pubSubDomain=true, the same string can lead to a Topic, i.e., **two different destination types**.

### 5.1. Does "Dynamic" mean auto-creating physical queues?

**There is no universal guarantee of that.** Per the JMS API, Session.createQueue(String) / createTopic(String) creates a destination representation; actual provisioning semantics depend on the JMS provider. Some brokers support auto-create on access, some only reference pre-configured destinations, and some require prior declaration/ACLs.

Therefore:

- If the broker allows auto-create, a corresponding physical destination may appear upon send/receive.
- If the broker disables auto-create or forbids permissions, resolution may produce a valid object while send/receive still fails.
- Configuring durable queues, routing type, DLQ, capacity limits, TTL, permissions, and retention remains the responsibility of the broker/operations team.
- **Dynamic destinations differ from TemporaryQueue/TemporaryTopic**. Temporary destinations are created by the JMS API for temporary use tied to the Connection lifecycle; dynamic names supplied by the application typically have a different lifecycle.

The class name DynamicDestinationResolver refers to the resolution strategy, not a command forcing the broker to "create new at all costs".

### 5.2. Advantages and limitations

Advantages: minimal configuration, convenient for demos and environments where the broker allows destinations following naming conventions. Limitations: String names can drift from broker config, security config, or routing; without naming governance, typos can lead to unintended queues or stranded messages.

Do not assume "JmsTemplate sent without error" means the destination name is business-correct: an accidentally created queue may still have no consumer.

## 6. JndiDestinationResolver: looking up registered destinations

An enterprise environment may pre-declare Destinations via **JNDI** (Java Naming and Directory Interface), bound under names like "java:/jms/queue/Orders". JndiDestinationResolver interprets destinationName as a JNDI name to look up a managed Queue/Topic.

Spring configuration example:

~~~java
import org.springframework.jms.support.destination.JndiDestinationResolver;

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setCache(true);
resolver.setFallbackToDynamicDestination(false);

jmsTemplate.setDestinationResolver(resolver);
jmsTemplate.setPubSubDomain(false);

// The name below must exist in the actual JNDI environment:
jmsTemplate.convertAndSend("java:/jms/queue/Orders", "ORDER-42");
~~~

This is a **configuration snippet**, not a standalone runnable project: jmsTemplate, the JNDI provider, the JNDI environment, and the binding must actually exist. JndiDestinationResolver inherits support for JNDI environment configuration; URL syntax, JNDI InitialContext, and namespaces **depend on the server/provider**.

**JNDI lookup does not automatically create destinations in the broker.** It retrieves the destination object already bound per the environment configuration. If the application server returns a destination incompatible with the active ConnectionFactory, send/receive can still fail.

### 6.1. Cache and invalidation

JndiDestinationResolver has important settings:

| Property | Default value | Meaning |
| --- | --- | --- |
| cache | true | Caches resolved destinations by name to avoid looking up every time. |
| fallbackToDynamicDestination | false | If JNDI lookup fails, by default it **does not** fall back to dynamic resolution. |
| dynamicDestinationResolver | Spring's DynamicDestinationResolver | Strategy used when fallback is explicitly enabled. |

You can control caching via setCache(boolean) and CachingDestinationResolver methods such as clearCache() / removeFromCache(name).

An easy-to-miss detail: the cache uses **destination name** as the key. If you mix Queue and Topic using the same name in JNDI/dynamic fallback, you can get the wrong cached representation. Therefore, use **distinct names for queues and topics**, such as "queue.orders" and "topic.orders", even when the broker supports identical physical names.

Caching helps by reducing lookups, but it can retain an old handle when operations rebinds JNDI or restarts a destination. If hot replacement is needed, consider invalidation or disabling the cache in appropriate scenarios, and retest with the provider.

### 6.2. Fallback is not the default

~~~java
resolver.setFallbackToDynamicDestination(true);
~~~

When enabled, if the name is **not found via JNDI** and the failure condition qualifies for fallback, the resolver uses the dynamic resolver to try creating a representation via the JMS Session. This is convenient in some development environments but **carries the risk of creating/reading the wrong queue** in production: a misspelled binding can silently turn into another dynamic destination.

If your organization requires every queue/topic to be declared and reviewed upfront, keep fallback=false so missing bindings are detected early.

### 6.3. Must a JNDI name equal the broker physical name?

No. For example:

~~~text
Name used in code:        java:/jms/queue/Orders
Binding in JNDI:           provider's jakarta.jms.Queue
Physical name on broker:   corp.sales.orders.v2
~~~

This is a valid mapping if the server/JNDI admin configures it that way. This separation makes it possible to change physical destinations with minimal code edits, at the cost of needing tight control over JNDI configuration and caching.

## 7. BeanFactoryDestinationResolver: resolving via Spring bean

BeanFactoryDestinationResolver looks up a bean in the Spring ApplicationContext/BeanFactory by name, requiring the bean to have type jakarta.jms.Destination.

~~~text
Application code: "ordersQueue"
         |
         v
Spring BeanFactory: bean name = ordersQueue
         |
         v
Object: JMS provider's jakarta.jms.Queue
~~~

Example of a resolver created by Spring:

~~~java
@Bean
DestinationResolver destinationResolver(BeanFactory beanFactory) {
    return new BeanFactoryDestinationResolver(beanFactory);
}
~~~

This is a snippet in a @Configuration class with the corresponding Spring imports. **There must be a bean named ordersQueue that actually returns a Destination**; this resolver does not create a Queue object if the bean does not exist.

The bean can be provided via JNDI lookup, JMS provider configuration, or a custom factory method. BeanFactoryDestinationResolver has a constructor accepting BeanFactory for use in addition to letting the container inject BeanFactoryAware.

Advantages: mapping String names to Destination beans is configured uniformly in Spring IoC; well-suited when the application already manages destination objects as beans. Disadvantages: depends on bean names, how the Destination is created, and bean lifecycle; does not by itself resolve broker permissions or physical queue creation.

## 8. Comparing the three strategies

| Criterion | DynamicDestinationResolver | JndiDestinationResolver | BeanFactoryDestinationResolver |
| --- | --- | --- | --- |
| String name is interpreted as | Queue/topic name for JMS Session | JNDI binding address | Spring bean name |
| Source of Destination object | Session.createQueue/createTopic | JNDI lookup | BeanFactory lookup |
| Needs JMS Session to resolve? | Yes | May not need it for lookup | Usually not needed |
| Built-in caching in resolver? | Does not use JNDI cache like Jndi | Yes, enabled by default | Follows BeanFactory and bean lifecycle |
| Needs pre-declared names? | Depends on broker and policy | Requires JNDI binding, unless fallback is enabled | Requires Destination bean |
| Common error reporting | JMSException/provider error | Missing binding, type mismatch, JNDI lookup error | Bean not found or wrong type |
| Best fit | Demos, governed dynamic names | Application server/enterprise naming | Mappings managed by Spring container |

**Choose a strategy based on where the source of truth for destinations actually lives.** If the broker uses auto-create following naming conventions, dynamic may suffice. If the deployment environment provisions Destinations via JNDI, the JNDI resolver is appropriate. If the application already has destination beans, use BeanFactory. A consistent strategy makes tracing naming bugs much easier.

## 9. pubSubDomain: same name, potentially different destination types

An important point is the boolean pubSubDomain in resolveDestinationName:

- **false** means Queue (point-to-point), the default of JmsTemplate.
- **true** means Topic (publish/subscribe).

~~~java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setPubSubDomain(false); // String will be resolved as a Queue.
template.convertAndSend("orders.events", "ORDER-42");
~~~

If changed to:

~~~java
template.setPubSubDomain(true);  // String will be resolved as a Topic.
template.convertAndSend("orders.events", "ORDER-42");
~~~

both calls use the String "orders.events" yet the target can be completely different. Both snippets require a provided connectionFactory variable; they illustrate the domain decision, not two standalone programs.

### 9.1. Design consequences

- Configuring the sender as Queue and the listener as Topic will result in them not communicating over the same destination as intended.
- Even if a queue is configured properly, a topic with no subscription at send time can cause published messages not to be received by a non-durable subscriber arriving later.
- JndiDestinationResolver usually expects the right Queue/Topic type from the binding; do not expect setPubSubDomain(true) to turn a Queue object into a Topic.
- In applications that use both queues and topics, configure separate templates/listener factories per purpose, or pass explicit Destination objects where type certainty is needed.
- **A JMS topic is not merely a queue with multiple consumers**: subscription models differ and affect message retention, selectors, and durable subscriptions.

### 9.2. Clear naming identification

You can adopt a convention:

~~~text
queue.orders.requests
topic.orders.events
queue.orders.retries
queue.orders.deadletter
~~~

This is only a naming convention within the application; the actual broker may apply its own address/routing naming. Align names across publishers/consumers, broker ACLs, monitoring, and deployment configuration.

## 10. Runnable example: Spring Boot 3.3.x + Artemis + Java 17

This section builds a minimal application to **observe when Spring resolves names**. The application sends and reads a message on the same queue using JmsTemplate, wrapping DynamicDestinationResolver with a logging resolver. The code does not use @JmsListener, avoiding a listener competing with receiveAndConvert in this synchronous demo.

### 10.1. Preparation

You need JDK 17+, Maven 3.9+, Docker, and port 61616 available. Run Apache ActiveMQ Artemis using the official image:

~~~bash
docker run --detach --rm --name jms-resolver-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Wait for the broker to be ready before running Spring Boot. The demo image defaults to username/password artemis/artemis; these credentials are for learning only, not for real environments. If the broker is configured to disallow auto-create, you must declare the demo.orders queue and grant permissions before running.

Project structure:

~~~text
spring-jms-resolver-demo/
├── pom.xml
└── src/main/
    ├── java/example/destination/DestinationResolverDemoApplication.java
    └── resources/application.properties
~~~

### 10.2. pom.xml

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
    <artifactId>spring-jms-resolver-demo</artifactId>
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

spring-boot-starter-artemis provides the Spring JMS and Artemis client dependencies so Spring Boot can configure ConnectionFactory. The example pins Spring Boot version 3.3.13 to ensure classes/imports are based on Spring Framework 6.x and jakarta.jms; do not use the legacy javax.jms namespace from Spring 5/Java EE.

### 10.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

This configures an external native broker, not an embedded broker. Port and user/password must match the running container. The application simply runs one CommandLineRunner and stops when no services/threads keep the process alive; Spring Boot and Artemis logs may appear around the demo stdout.

### 10.4. DestinationResolverDemoApplication.java

~~~java
package example.destination;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.DestinationResolver;
import org.springframework.jms.support.destination.DynamicDestinationResolver;

@SpringBootApplication
public class DestinationResolverDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DestinationResolverDemoApplication.class, args);
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        DynamicDestinationResolver delegate =
                new DynamicDestinationResolver();

        DestinationResolver tracingResolver =
                (session, destinationName, pubSubDomain) -> {
                    Destination resolved =
                            delegate.resolveDestinationName(
                                    session, destinationName, pubSubDomain);

                    System.out.printf(
                            "resolve %s: %s%n",
                            pubSubDomain ? "topic" : "queue",
                            destinationName);
                    return resolved;
                };

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(tracingResolver);
        template.setPubSubDomain(false);
        template.setReceiveTimeout(5_000L);
        return template;
    }

    @Bean
    CommandLineRunner demo(JmsTemplate jmsTemplate) {
        return args -> {
            String destinationName = "demo.orders";

            jmsTemplate.convertAndSend(destinationName, "Order-42");
            System.out.println("sent: Order-42");

            Object payload =
                    jmsTemplate.receiveAndConvert(destinationName);
            System.out.println("received: " + payload);
        };
    }
}
~~~

Explanation:

1. Spring Boot creates ConnectionFactory from the Artemis configuration.
2. The jmsTemplate bean is explicitly registered with tracingResolver attached. Because it is a JmsTemplate bean, Boot's default auto-configured template does not need to create a duplicate bean for the same purpose.
3. Inside tracingResolver, delegate is the official DynamicDestinationResolver; the lambda **does not alter the Queue/Topic creation logic itself**.
4. setPubSubDomain(false) causes "demo.orders" to be resolved as a Queue.
5. convertAndSend first resolves the name and sends a TextMessage with body "Order-42".
6. receiveAndConvert resolves the same name, receives the message, and converts the TextMessage to String using the default SimpleMessageConverter.
7. A 5-second receiveTimeout prevents receive from waiting indefinitely if the broker does not deliver a message.

**Production note:** keep logging at an appropriate level, avoiding exposing sensitive names or indiscriminately logging payload data. Custom resolvers should enforce consistent naming policies, mappings, validation, and exceptions across producers and consumers.

### 10.5. Running and expected output

In the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

When the broker/queue works normally, the lines printed by the program will be:

~~~text
resolve queue: demo.orders
sent: Order-42
resolve queue: demo.orders
received: Order-42
~~~

In addition, Spring Boot/provider logs appear depending on the environment. If the demo.orders queue already has old messages from a previous run, receiveAndConvert may pick up that message first; to reproduce the output, run against a clean test broker/queue, or use a distinct demo queue name for each run.

If the broker is not ready or forbids auto-create, you may receive an exception during resolution/send/receive. Do not jump to blaming the resolver when the exception actually comes from transport, ACLs, or a missing physical destination.

Stop the demo container after practicing:

~~~bash
docker stop jms-resolver-broker
~~~

### 10.6. Two small experiments

**Experiment 1 – switch queue to topic:** change setPubSubDomain(false) to true. The application sends first and only then creates a consumer to receive, so a **topic with no non-durable subscriber at publish time can lose that message**. When testing topics, plan for an existing subscriber or an appropriate durable/shared subscription; do not expect the program to receive it back like a queue.

**Experiment 2 – misspelled name:** change destinationName to "demo.orderz". If the broker has auto-create enabled, the program can still send/receive through the new queue and thus "run successfully" even though it sent to the wrong business name. This is why you need a naming contract, configuration checks, and broker policies instead of relying solely on send succeeding.

## 11. Same resolver for @JmsListener and JmsTemplate

In real systems, producers and consumers may live in the same application or in two different services. You must ensure they understand the **same logical name** and **same destination type**.

Spring listener example:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {
    @JmsListener(destination = "orders.incoming")
    public void handle(String text) {
        // Handle the message after the broker delivers it to the listener.
    }
}
~~~

This is only a **snippet inside an application with JMS listener infrastructure enabled**, not a standalone Java program. @JmsListener selects the destination by String name; the listener container factory will use its DestinationResolver to resolve it.

A common mistake: configuring only JmsTemplate.setDestinationResolver(custom) and assuming @JmsListener automatically uses the same custom resolver. **They are separate configuration components.** For consistency, configure the appropriate resolver on both the template and the listener container factory.

Illustrative example using JNDI for both:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.DestinationResolver;
import org.springframework.jms.support.destination.JndiDestinationResolver;

@Configuration
@EnableJms
class JmsDestinationConfig {

    @Bean
    DestinationResolver destinationResolver() {
        JndiDestinationResolver resolver = new JndiDestinationResolver();
        resolver.setCache(true);
        resolver.setFallbackToDynamicDestination(false);
        return resolver;
    }

    @Bean
    JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            DestinationResolver destinationResolver) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(destinationResolver);
        template.setPubSubDomain(false);
        return template;
    }

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory connectionFactory,
            DestinationResolver destinationResolver) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setDestinationResolver(destinationResolver);
        factory.setPubSubDomain(false);
        return factory;
    }
}
~~~

The snippet above is a **configuration skeleton** and only works when the application has configured the JNDI provider, corresponding bindings, and Spring JMS components. For production, the listener factory also needs configuration for transactions, acknowledgement, error handling, concurrency, recovery, caching, and monitoring as required. The minimal template above **does not** replace all of Spring Boot JMS auto-configuration when those options are needed.

When calling:

~~~java
jmsTemplate.convertAndSend("java:/jms/queue/Orders", "Order-42");
~~~

and the listener uses:

~~~java
@JmsListener(destination = "java:/jms/queue/Orders")
~~~

both places can look up the same name in JNDI, provided they actually use the resolver/factory beans just configured. The annotation part is a snippet, not a standalone class.

### 11.1. When an application uses both Queue and Topic

The Spring listener factory has a matching pubSubDomain setting. You can register multiple listener factories with different configurations and choose one by name:

~~~java
@JmsListener(
    destination = "topic.orders.events",
    containerFactory = "topicListenerFactory")
~~~

Here topicListenerFactory must be configured with setPubSubDomain(true), the right DestinationResolver, and ConnectionFactory. With JNDI, the binding must return an appropriate Topic. On the producer side, use a separate JmsTemplate with pubSubDomain(true) enabled, or pass a Topic object directly when needed.

## 12. Writing a custom resolver when there is a naming contract

When names in code are fixed by business logic while broker names vary by system, you can implement DestinationResolver yourself for mapping and whitelist validation.

Complete Java class example of the mapping algorithm (must be run **in an application with Spring JMS dependencies and a JMS Session**):

~~~java
package example.destination;

import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import org.springframework.jms.support.destination.DestinationResolutionException;
import org.springframework.jms.support.destination.DestinationResolver;
import org.springframework.jms.support.destination.DynamicDestinationResolver;

public final class MappingDestinationResolver
        implements DestinationResolver {

    private final DynamicDestinationResolver delegate =
            new DynamicDestinationResolver();

    @Override
    public Destination resolveDestinationName(
            Session session,
            String destinationName,
            boolean pubSubDomain) throws JMSException {

        if (pubSubDomain) {
            throw new DestinationResolutionException(
                    "This resolver only accepts queues");
        }

        String physicalName;
        switch (destinationName) {
            case "orders.incoming":
                physicalName = "company.sales.orders.v1";
                break;
            case "payments.incoming":
                physicalName = "company.finance.payments.v1";
                break;
            default:
                throw new DestinationResolutionException(
                        "Unknown logical destination: " + destinationName);
        }

        return delegate.resolveDestinationName(
                session, physicalName, false);
    }
}
~~~

The class above compiles in a project with spring-jms/Jakarta Messaging, though it **has no main()** so it must be wired into JmsTemplate/listener factory to be used. This pattern lets call sites know only "orders.incoming", while the mapping lives in one place. To update mappings at runtime, consider configuration versioning, reload capability, and monitoring for wrong names.

**Do not confuse name validation with security:** even though a whitelist can limit accidental destination mistakes, producers/consumers must still be authenticated and authorized by the broker. Mapping also does not guarantee message schema compatibility or that a consumer is processing messages.

### 12.1. How should errors in a resolver be handled?

A resolver can throw JMSException from the Session/provider or DestinationResolutionException when a name cannot be found. JmsTemplate typically translates JMSException into Spring's runtime JmsException hierarchy; resolution errors are usually propagated to the call site as well. Do not catch everything and redirect invalid names to a default queue without business approval: doing so easily routes data to the wrong place.

For multi-producer systems, log at an appropriate level: logical name, physical target, domain, timestamp, and exception category; strictly avoid logging credentials or payloads containing sensitive information.

## 13. Operational issues commonly associated with resolution

### 13.1. Resolution can succeed while send/receive fails

A resolver returning a Queue object does not mean the broker has created the queue. Separate four layers when diagnosing:

1. **Application name:** are spelling/case, mapping, config, and environment right?
2. **Resolution strategy:** is it using Dynamic, JNDI, Spring bean, or custom?
3. **Broker/provider:** is the destination provisioned, routing mode right, and ACL/credentials still valid?
4. **Message delivery:** is there a consumer matching the selector, subscription, transaction/ack, and redelivery handling?

If an error occurs immediately at application startup, it may be due to JNDI lookup or misconfigured beans. If sending succeeds but nobody receives, the cause may be a queue/topic mismatch, a non-matching selector, a stopped listener, or messages being sent to a different name.

### 13.2. JNDI name differs from physical name

A name like "java:/jms/queue/Orders" may be bound by the server to the broker name "corp.order.in". Copying the JNDI name directly into DynamicDestinationResolver will **not automatically create the same mapping**; dynamic usually uses that string as the JMS destination name, causing environment drift.

If switching from JNDI to dynamic, explicitly verify the name-mapping table and broker configuration. Do not just swap the resolver implementation and expect messages to find the right recipients.

### 13.3. Caching with multiple domains/tenants

JndiDestinationResolver caches by name. If an application reuses the same destinationName string "orders" to point to two different environments/tenants without separating resolvers/contexts/caches, data can go to the wrong destination. Use clear naming namespaces, separate resolver lifecycles per environment, and test before going to production.

Multi-tenant systems need tenant authentication/authorization at the application/broker layers. Putting the tenant into destinationName is an architectural choice that requires bounding the number of destinations rather than generating unlimited queues unmanaged.

### 13.4. Spring Boot auto-configuration

Spring Boot typically creates ConnectionFactory/JmsTemplate and listener infrastructure based on classpath/properties. However, **DestinationResolver** options are part of Spring JMS configuration. When defining custom JmsTemplate or listener factory beans, understand whether Boot's defaults still apply.

If an application uses both @JmsListener and JmsTemplate, lacking a unified configuration can lead to the producer using JNDI while the consumer uses Dynamic; both write "orders" yet actually point to different Destinations.

### 13.5. Not conflating different resolver types in Spring

Spring also has the interface **org.springframework.messaging.core.DestinationResolver<D>** used for general messaging abstractions. This lesson covers **org.springframework.jms.support.destination.DestinationResolver** with the method resolveDestinationName(Session, String, boolean) and return type jakarta.jms.Destination. Accidentally importing the Spring Messaging interface can prevent lambdas or configuration from compiling even though both are named DestinationResolver.

## 14. Troubleshooting checklist

| Symptom | Causes to check | Remediation |
| --- | --- | --- |
| Queue has a name but JmsTemplate reports not found | JNDI resolver looking up wrong path or binding does not exist | Check JNDI context, binding name, and fallback. |
| Send succeeds but listener does not receive | Producer/consumer using different domains or resolvers | Compare Strings, pubSubDomain, JNDI mapping, listener factory. |
| Wrongly named queue appears on broker | Dynamic resolver + typo, auto-create enabled | Whitelist names, govern provisioning, check ACLs. |
| Switched to topic and program receives nothing | Subscriber did not exist at publish time | Design subscription lifecycle, use durable subscriptions when needed. |
| Sent to a different queue despite identical String | One side uses JNDI logical name, other side uses dynamic physical name | Align resolver contract and broker configuration. |
| Still uses old address after JNDI rebind | Destination cache still holds old handle | Consider removeFromCache/clearCache or disabling cache. |
| Queue and topic with same name confused by JNDI cache | Resolver caches by destination name | Distinct names per domain, do not share the same cache key. |
| Custom resolver does not run in @JmsListener | Only configured JmsTemplate, not container factory | Attach matching resolver to listener factory. |
| Wrong Destination type | JNDI returns Queue while caller expects Topic | Check binding type and pubSubDomain. |
| Cannot create queue in production | Broker disabled auto-create or ACL forbids it | Register destination beforehand, configure proper permissions. |
| Constructor confusion or compile type error | Imported org.springframework.messaging.core.DestinationResolver | Import org.springframework.jms.support.destination.DestinationResolver. |

### 14.1. Questions to narrow down the issue quickly

- Who supplies the destination name: code, properties, JNDI, environment variables, or a configuration table?
- Is JmsTemplate created by Boot or is it a custom bean?
- Which listener container factory is @JmsListener actually using?
- Do pubSubDomain values match between sender and receiver?
- Does the resolver return a Destination object of type Queue or Topic?
- Do logical and physical names match, and who owns the mapping?
- Does the broker have auto-create enabled or only allow pre-registered destinations?
- Is the JNDI cache holding stale mappings after a deployment?
- Was a message "lost" due to resolution or due to selector/transaction/TTL/subscription?

Do not read provider state from the destination name alone. Use application logs, broker console/metrics, access permissions, and deployment config to verify each layer.

## 15. Self-check questions

**1. Why does JmsTemplate.convertAndSend(String, Object) need a DestinationResolver?**

Because the JMS API works with Destination objects, while the method accepting String only supplies a name. The resolver translates the String into a Destination.

**2. What behavior does pubSubDomain=false lead to when using DynamicDestinationResolver?**

The resolver invokes the Queue mechanism on the JMS Session (Session.createQueue), representing the point-to-point domain.

**3. Does the JNDI resolver automatically create physical queues?**

No. It looks up existing bindings; if fallback is enabled, it may try dynamic resolution, while broker provisioning still depends on the environment.

**4. Does the default JndiDestinationResolver fall back to dynamic when a binding is not found?**

No. fallbackToDynamicDestination defaults to false.

**5. Why might the name "orders" route to two different destinations?**

Because Queue/Topic differ in type, or one side resolves via a JNDI logical binding while the other treats the String itself as a dynamic physical name.

**6. When should you pass a Destination object directly?**

When you already have a valid destination handle and want to avoid String-based lookup; JmsTemplate has overloads accepting Destination.

**7. Can you set a resolver on JmsTemplate and have it apply automatically to every @JmsListener?**

No. The listener container factory is configured separately; you must check and configure the container's resolver if needed.

**8. What should you be careful about with the JNDI cache?**

It caches by name; changing a JNDI binding can leave an old handle in use. A Queue and Topic sharing the same name can cause cache collisions.

**9. Does DynamicDestinationResolver guarantee auto-creation of physical queues?**

No. Auto-create behavior and permissions depend on the provider/broker, not guaranteed by the DestinationResolver interface.

**10. How does DestinationResolver differ from MessageConverter?**

The resolver determines the **destination** for sending/receiving; the converter determines the **JMS Message representation** of the payload.

### Practice exercises

1. Run the example in section 10 and record the two "resolve queue" lines. Explain why both sending and receiving must resolve a String name.
2. Change the lambda resolver to map "orders.incoming" to "demo.orders". Keep consumer/producer using the same logical name and verify the message is delivered.
3. Introduce a typo on the sender in a broker with auto-create enabled. Observe the newly created queue and discuss how to prevent the mistake.
4. Write a custom resolver that rejects any name outside an allowed set; verify the exception in JmsTemplate.
5. Use two separate JmsTemplates for Queue and Topic with distinct naming; explain why mixing domains should be avoided.
6. In an environment with real JNDI, try setCache(true), rebind the destination, and then call removeFromCache to observe the change.
7. Create a @JmsListener with a custom containerFactory and verify whether the listener's resolver and JmsTemplate share the same mapping.
8. Describe the integration test suite needed to prove the application sends to the right physical queue in staging/production environments.

## 16. Official references

- Spring Framework — JMS Destination Management: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — Sending a Message: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework 6.2 — DestinationResolver API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html
- Spring Framework 6.2 — JmsTemplate API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.2 — BeanFactoryDestinationResolver: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/BeanFactoryDestinationResolver.html
- Spring Framework 6.2 — DefaultJmsListenerContainerFactory: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 — JndiDestinationResolver: https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html
- Apache ActiveMQ Artemis — Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
