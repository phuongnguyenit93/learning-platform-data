# Configuring ConnectionFactory and Default Destination for JmsTemplate

## 1. Two configurations with distinct roles

In Spring JMS, **`JmsTemplate`** is the object that supports synchronous sending and receiving of messages. To operate, it requires a **`jakarta.jms.ConnectionFactory`**. In addition, the application can configure a **default destination** for calling methods that do not pass a destination argument.

```text
Spring Application
       |
       v
   JmsTemplate  --------------------------+
       |                                  |
       | ConnectionFactory                 | Default destination
       | (connects to broker)              | (e.g. orders.created)
       v                                  v
JMS Connection/Session  ------------>  Queue / Topic
       |                                  |
       +-------- producer/consumer -------+
```

Make sure to distinguish:

- **ConnectionFactory** answers the question: *How does the application connect to the JMS provider?* It involves the broker endpoint, authentication, TLS, connection/session lifecycle, caching, and potentially transactions.
- **Destination** answers the question: *Which Queue or Topic does the message go to?* It can be a `String` name resolved by Spring or a `jakarta.jms.Destination` object.
- **Default destination** is a **configuration belonging to the `JmsTemplate` instance itself**, used when a method does not take a destination argument. It is **not** a broker-wide default destination, does not create a special Queue/Topic, and does not assign a default address to all listeners.

Example:

```java
jmsTemplate.convertAndSend("ORDER-001");
```

This only works when `jmsTemplate` itself already has a default destination; the payload `"ORDER-001"` is the **message content**. In contrast:

```java
jmsTemplate.convertAndSend("orders.audit", "AUDIT-001");
```

The first argument is the explicit destination `"orders.audit"`, and the second argument is the payload. This call **does not use** the default destination even if the template has one configured.

## 2. ConnectionFactory: creating, obtaining, and wiring into JmsTemplate

### 2.1. Interface and configuration sources

Spring Framework 6/Spring Boot 3 uses the **`jakarta.jms.ConnectionFactory`** interface. This is the standard Jakarta Messaging API; the instance is provided by a JMS provider or managed container. Spring cannot create connections to the broker without an appropriate factory.

Common ways to obtain a factory:

| Environment | Source of `ConnectionFactory` | Example |
| --- | --- | --- |
| Spring Boot connecting to an external broker | Auto-configuration based on the JMS starter and provider properties | ActiveMQ Artemis with `spring-boot-starter-artemis` |
| Manually configured Spring Framework | Declaring a factory bean configured via vendor APIs | A Jakarta JMS-compatible `ActiveMQConnectionFactory` |
| Application server managing JMS | JNDI lookup to retrieve a managed factory | `spring.jms.jndi-name` or `JndiLocatorDelegate` |
| Tests | Factory from a test broker/environment or a JMS wrapper test double | Ephemeral broker in an integration test |

**Broker configuration does not live in `setDefaultDestinationName`**. If the factory points to the wrong broker, setting the right Queue name will not fix a connection error. Likewise, a factory pointing to the right broker does not replace choosing a destination when sending.

### 2.2. Declaring JmsTemplate in Spring Framework

In an application that already has a `ConnectionFactory` bean, you can declare:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsTemplateConfig {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDefaultDestinationName("orders.created");
        template.setPubSubDomain(false); // resolve String as a Queue
        return template;
    }
}
```

Notes:

1. Spring injects the `ConnectionFactory` bean into the `@Bean` method. This pattern **assumes the factory bean already exists**; otherwise, Spring reports a dependency error at startup.
2. `new JmsTemplate(connectionFactory)` and `template.setConnectionFactory(connectionFactory)` are two ways to supply the factory. You do not need to call both.
3. `setDefaultDestinationName("orders.created")` sets the destination name used for methods **that do not pass a destination**.
4. `setPubSubDomain(false)` instructs the dynamic resolver to treat that name as a **Queue** (Spring's default is Queue). If using a Topic with the dynamic resolver, set it to `true`.
5. Once configured, `JmsTemplate` is designed to be **thread-safe** and should usually be used as a **singleton bean**. Do not mutate the factory or default destination on a singleton serving concurrent requests to switch targets per request.

This approach does not require creating `Connection`/`Session` manually: `JmsTemplate` works with resources following the Spring JMS lifecycle and handles exception translation. Therefore, producers/services can inject the `JmsTemplate` bean and reuse it.

### 2.3. Managed factory from JNDI

In an application server where a factory is bound in JNDI, Spring Boot can look it up via:

```yaml
spring:
  jms:
    jndi-name: "java:comp/env/jms/OrdersCF"
```

Or configure plain Spring to look up `jakarta.jms.ConnectionFactory`, then pass that factory to `JmsTemplate` as in section 2.2. This JNDI configuration **selects the factory**, not the default destination; to send without passing a destination, you must also configure the default destination name or object.

Note that environments running outside an application server typically **do not have** `java:comp/env` unless you explicitly configure a JNDI provider/binding.

## 3. Two ways to configure a default destination

`JmsTemplate` supports two configuration styles for the same purpose; usually pick **one**:

### Option A — `setDefaultDestinationName(String)`

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDefaultDestinationName("orders.created");
```

When calling `send(MessageCreator)`, `convertAndSend(Object)`, `receive()`, or `receiveAndConvert()`, Spring takes `"orders.created"` and calls `DestinationResolver` to resolve it. With the default `DynamicDestinationResolver`, `Session.createQueue("orders.created")` is typically used if the template is in the Queue domain.

This is convenient when the destination name is known and the broker allows resolving it. **Resolving a dynamic destination does not mean the broker necessarily creates the Queue automatically**: provisioning and auto-create policies depend on the provider.

### Option B — `setDefaultDestination(Destination)`

```java
import jakarta.jms.Destination;
import org.springframework.jms.core.JmsTemplate;

// Assumes destination is a valid object provided by the JMS provider.
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDefaultDestination(destination);
```

This option accepts a `jakarta.jms.Destination` object directly, such as a `Queue` or `Topic` injected from JNDI/container. You do not have to re-resolve a String name for calls using the default.

**Do not instantiate `new Destination()`**: `Destination` is an interface. The real object is created by the provider or retrieved from a managed resource. If needed, you can use a valid `Queue` bean:

```java
@Bean
JmsTemplate ordersTemplate(
        ConnectionFactory connectionFactory,
        @Qualifier("ordersQueue") jakarta.jms.Queue ordersQueue) {
    var template = new JmsTemplate(connectionFactory);
    template.setDefaultDestination(ordersQueue);
    return template;
}
```

This is a **snippet inside a `@Configuration` class**; it requires importing `@Bean`, `@Qualifier`, `ConnectionFactory`, `JmsTemplate`, and having an `ordersQueue` bean available. If the provider's destination object is incompatible with the connection factory in use, sending messages may fail; do not take a Queue object from broker A and use it with the connection factory of broker B.

### Comparing the two options

| Criterion | Default destination name | Default Destination object |
| --- | --- | --- |
| Input | `String` | `jakarta.jms.Destination` |
| Configuration API | `setDefaultDestinationName(...)` | `setDefaultDestination(...)` |
| Resolution | Through `DestinationResolver` | Object already exists |
| Queue/Topic domain when using name | Depends on `pubSubDomain` and resolver | Actual type of the `Queue`/`Topic` object |
| Best suited for | Broker/client resolving destinations by name | Container/provisioning-managed resources injected upfront |
| Common pitfalls | Wrong name, wrong Queue/Topic domain, creation disallowed by policy | Wrong provider object or broken binding |

There is no need to set both properties as a fallback. Choose a single source of truth for the default destination.

## 4. Which methods use the default destination?

Suppose:

```java
JmsTemplate t = new JmsTemplate(connectionFactory);
t.setDefaultDestinationName("orders.created");
```

| Call | Destination actually chosen | Explanation |
| --- | --- | --- |
| `t.send(session -> session.createTextMessage("A"))` | `orders.created` | Uses the default destination. |
| `t.convertAndSend("A")` | `orders.created` | Payload is a `String`; `SimpleMessageConverter` typically creates a `TextMessage`. |
| `t.convertAndSend("B", message -> message)` | `orders.created` | Overload with `MessagePostProcessor` and no destination passed. |
| `t.receive()` | `orders.created` | Synchronous receive from the default destination. |
| `t.receiveAndConvert()` | `orders.created` | Synchronous receive and body conversion. |
| `t.send("orders.audit", creator)` | `orders.audit` | Explicit destination overrides the default for this call. |
| `t.convertAndSend("orders.audit", "B")` | `orders.audit` | First String parameter is the destination, second is the payload. |
| `t.receive("orders.audit")` | `orders.audit` | Receives from the explicit destination. |
| `t.convertAndSend(destinationObject, "B")` | `destinationObject` | `Destination` object is passed directly. |

If no default destination is set, methods without a destination will throw an error (typically `IllegalStateException` from the template before sending). Do not “fix” this by stuffing the payload into a two-parameter overload or putting in a made-up name that the broker does not have.

**Important:** `@JmsListener(destination = "orders.created")` **does not** automatically inherit `JmsTemplate`'s default destination; listeners are configured by the **listener container factory** and their own annotation. Conversely, changing `JmsTemplate`'s default destination does not make a listener listening on another Queue automatically switch to the new destination.

## 5. How are destination names resolved?

By default, `JmsTemplate` typically uses `DynamicDestinationResolver`. When receiving a `String` name, it uses the domain to create a `Queue` or `Topic` object via the `Session`:

```text
defaultDestinationName = "orders.created"
pubSubDomain = false
    -> resolve Queue("orders.created")

defaultDestinationName = "orders.created"
pubSubDomain = true
    -> resolve Topic("orders.created")
```

**Queue and Topic are two different domains**. Having the same name does not mean the two destinations are the same object. If a producer sends to a Queue while a consumer listens to a Topic of the same name, they generally do not share messages.

If the actual destination is managed via JNDI, you can configure:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setResourceRef(true);
resolver.setFallbackToDynamicDestination(false);

JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDestinationResolver(resolver);
template.setDefaultDestinationName("jms/OrdersQueue");
```

This is a configuration snippet **inside a method that already has `ConnectionFactory connectionFactory`**. With `resourceRef=true`, Spring looks up `java:comp/env/jms/OrdersQueue` in the container. Disabling dynamic fallback prevents a mistyped JNDI name from silently being interpreted as a dynamic destination name. If JNDI lookup for destinations is not needed, use the default resolver.

The destination resolver configuration of **`JmsTemplate`** is separate from that of the **listener container**. If both sides rely on JNDI resources, both must be configured compatibly or use properly injected destination objects.

### Distinguishing three kinds of “default”

- Default `ConnectionFactory` bean: the object Spring injects when only one matching bean exists (or one is marked `@Primary`).
- `JmsTemplate.defaultDestinationName`: the target chosen for **methods that do not take a destination** on that template.
- `@JmsListener(destination=...)`: the explicit destination of the listener; it is not inferred from the template's default destination.

Do not conflate Spring's “default bean” concept with JMS's “default destination”.

## 6. Configuring with Spring Boot

With Spring Boot 3 and the appropriate JMS starter, Boot can auto-create the `ConnectionFactory` and `JmsTemplate` beans. Typically you only need to declare configuration, inject `JmsTemplate`, and send messages.

Example with **Apache ActiveMQ Artemis**:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
    template:
      default-destination: orders.created
      receive-timeout: 2s
```

Explanation of each property:

| Property | Purpose |
| --- | --- |
| `spring.artemis.mode=native` | Connects to an Artemis broker running externally to the application. |
| `spring.artemis.broker-url` | Broker endpoint used by the provider, e.g. `tcp://localhost:61616`. |
| `spring.artemis.user/password` | Demo broker credentials; production should source them from a secure secret/config. |
| `spring.jms.pub-sub-domain=false` | Defaults configuration toward Queue. For Topic, adjust consistently for both sender and listener. |
| `spring.jms.template.default-destination` | Target name for destination-less methods of the auto-configured `JmsTemplate`. |
| `spring.jms.template.receive-timeout` | Wait time limit when calling synchronous `receive()`/`receiveAndConvert()`. |

Distinguish the **Spring Boot property** `spring.jms.template.default-destination` from the Java method **`setDefaultDestinationName`**: they set the same configuration when Boot creates the template. If you declare a custom `JmsTemplate` bean yourself, you must configure that bean directly or use appropriate configuration helpers; do not assume all Boot properties automatically apply to an object you instantiate manually with `new`.

### Caching ConnectionFactory

Spring Boot can wrap the native `ConnectionFactory` with `CachingConnectionFactory` via `spring.jms.cache.*` properties. A caching factory reduces the cost of repeatedly creating sessions/producers in some workloads; the default destination itself does not affect caching policy.

If an application server already manages pooling or XA for the factory, review transaction and lifecycle semantics before adding another cache/pool layer. Do not manually call `close()` on a managed `ConnectionFactory`: close only connections/sessions opened by application code per the JMS contract, or let `JmsTemplate`/containers manage them.

## 7. Complete demo: one default Queue and one explicit Queue

This example uses **Java 17, Spring Boot 3.3.x, Spring JMS, and an external Artemis broker**. It verifies three ways of calling `JmsTemplate`:

1. `convertAndSend(payload)` to the default Queue `orders.created`.
2. `send(creator)` to the **same default Queue**.
3. `convertAndSend("orders.audit", payload)` to a **different explicit Queue**.

Two listeners specify their own destinations in `@JmsListener`.

### 7.1. Prepare the broker

Install Docker and start a test Artemis instance:

```bash
docker run --detach --rm --name jms-template-demo -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

This command also works in PowerShell when written on one line. Wait for the broker to start and accept connections on port 61616 before running Spring. The broker used for the example must have or allow creating the two Queues `orders.created` and `orders.audit` (some Artemis configurations enable auto-create address/queue; on other brokers you may need to provision them beforehand). When finished, stop it with `docker stop jms-template-demo`.

### 7.2. Create the Gradle project

File `settings.gradle`:

```groovy
rootProject.name = 'jms-default-destination-demo'
```

File `build.gradle`:

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

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
    template:
      default-destination: orders.created
      receive-timeout: 2s
```

File `src/main/java/demo/jms/JmsDefaultsApplication.java`:

```java
package demo.jms;

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
public class JmsDefaultsApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsDefaultsApplication.class, args);
    }

    @Bean
    ApplicationRunner sendSamples(JmsTemplate jmsTemplate) {
        return args -> {
            // Uses default destination: orders.created.
            jmsTemplate.convertAndSend("ORDER-1");

            // Still uses default destination: orders.created.
            jmsTemplate.send(session ->
                    session.createTextMessage("ORDER-2"));

            // Selects explicit destination, ignoring default.
            jmsTemplate.convertAndSend(
                    "orders.audit",
                    "AUDIT-1"
            );
        };
    }
}

@Component
class DemoListeners {

    @JmsListener(destination = "orders.created")
    public void onOrder(String payload) {
        System.out.println("ORDER: " + payload);
    }

    @JmsListener(destination = "orders.audit")
    public void onAudit(String payload) {
        System.out.println("AUDIT: " + payload);
    }
}
```

**Reading the code in order:**

1. Spring Boot configures `ConnectionFactory` from the Artemis starter and `spring.artemis.*`.
2. Boot creates `JmsTemplate` and binds `default-destination: orders.created`.
3. `ApplicationRunner` sends two messages to `orders.created`; the third send uses `orders.audit` explicitly.
4. Two `@JmsListener` methods listen on their respective Queues. `SimpleMessageConverter` normally converts `String` to `TextMessage` when sending, and from `TextMessage` to `String` when passing into the handler.
5. No `@JmsListener` method uses `JmsTemplate`'s default destination; listener Queue names are written directly in the annotation.

### 7.3. Running, output, and observation limits

You need Gradle compatible with Spring Boot 3.3.x and JDK 17+, then run:

```bash
gradle bootRun
```

If the project includes a Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

On a clean run, with the broker active and no handler errors, the lines printed by the application itself include:

```text
ORDER: ORDER-1
ORDER: ORDER-2
AUDIT: AUDIT-1
```

**The ordering across lines is not guaranteed** because the listeners run asynchronously; the above is one possible order, not a framework-guaranteed order. If the broker holds unprocessed messages from a previous run, or if producers/consumers retry, the number of log lines may differ. You can remove/recreate the demo broker for clean observation.

If you remove `spring.jms.template.default-destination` while still calling `convertAndSend("ORDER-1")`, the call no longer knows the target and will fail. However, `convertAndSend("orders.audit", "AUDIT-1")` can still work if the factory/broker are ready, because the destination was passed explicitly.

## 8. Manual configuration instead of auto-configured JmsTemplate

In a plain Spring Framework app or when deeper customization is needed, declare the bean in Java. The complete example below **is an alternative to Boot auto-creating the template in section 7**; do not add it to that demo unless you have explicitly decided on the bean override mechanism:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class ManualJmsTemplateConfig {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate();
        template.setConnectionFactory(connectionFactory);
        template.setDefaultDestinationName("orders.created");
        template.setPubSubDomain(false);
        template.setReceiveTimeout(2_000);
        return template;
    }
}
```

The destination behavior and no-argument calls match the demo above when beans/providers are compatible. The difference is that you **take responsibility** for `JmsTemplate` properties instead of relying on auto-configuration's `spring.jms.template.*`. You should not have two beans named `jmsTemplate` simultaneously unless controlled bean overriding is intentionally configured.

### Multiple templates for multiple destinations

An application may send to multiple Queues/Topics. Instead of mutating `setDefaultDestinationName` on a singleton per request, you can:

- Call overloads with an explicit destination on a single template when destinations share the same provider and domain.
- Or define **multiple templates with clear bean names**, each with a fixed default destination; inject via `@Qualifier`.

Example inside a `@Configuration` class that already has `ConnectionFactory`:

```java
@Bean("orderTemplate")
JmsTemplate orderTemplate(ConnectionFactory cf) {
    var template = new JmsTemplate(cf);
    template.setDefaultDestinationName("orders.created");
    return template;
}

@Bean("auditTemplate")
JmsTemplate auditTemplate(ConnectionFactory cf) {
    var template = new JmsTemplate(cf);
    template.setDefaultDestinationName("orders.audit");
    return template;
}
```

With two beans of the same type `JmsTemplate`, injecting without specifying a name can cause **`NoUniqueBeanDefinitionException`**. Use:

```java
public OrderPublisher(
        @Qualifier("orderTemplate") JmsTemplate orderTemplate) {
    this.orderTemplate = orderTemplate;
}
```

This is an **illustrative constructor inside class `OrderPublisher` having field `JmsTemplate orderTemplate`**, requiring imports for `@Qualifier` and `JmsTemplate`. If the templates target **two different brokers**, wire each template with its corresponding `ConnectionFactory`; changing only the default destination cannot switch the connection to a different broker.

## 9. Queue, Topic, and domain configuration

`JmsTemplate` defaults to the Point-to-Point domain (**Queue**). When using `String` names and `DynamicDestinationResolver`, `setPubSubDomain(true)` switches resolution to **Topic**:

```java
JmsTemplate topicPublisher = new JmsTemplate(connectionFactory);
topicPublisher.setPubSubDomain(true);
topicPublisher.setDefaultDestinationName("orders.events");

topicPublisher.convertAndSend("ORDER_CREATED");
```

This example is **inside a method that has `ConnectionFactory connectionFactory`**, and cannot run standalone without a provider. With a Topic, each matching subscription receives its own copy of messages; with a Queue, consumers compete over a single stream of work. **Default destination does not change Queue/Topic delivery rules.**

If using `@JmsListener` for a Topic, ensure the listener container factory is also configured with `pubSubDomain=true`. Switching only the sending template to Topic while leaving the listener listening on a Queue of the same name by default is a common mistake.

`spring.jms.pub-sub-domain=true` in Spring Boot configures the default domain for auto-created JMS infrastructure; when mixing Queues and Topics in the same application, use separate templates and listener factories with explicit domains so nothing is sent or received in the wrong domain.

### Explicit destination wins over default destination

```java
topicPublisher.convertAndSend("orders.events", "E1");
topicPublisher.convertAndSend("shipping.events", "E2");
```

Even though the template's default destination is `orders.events`, the second call still sends to `shipping.events`. However, both `String` names are still resolved under the template's Topic domain. If sending to a Queue with the same Topic template, use a separate Queue template or pass a compatible `Queue` object and verify with your provider. **Do not** treat passing a different name as a way to switch between Queue ↔ Topic.

## 10. Synchronous receive and the effect of default destination

`JmsTemplate` not only sends messages but also provides `receive()` and `receiveAndConvert()`. Once a default destination is set, calls without a destination receive **synchronously** from that target:

```java
JmsTemplate t = new JmsTemplate(connectionFactory);
t.setDefaultDestinationName("orders.created");
t.setReceiveTimeout(2_000); // 2000 ms

Object result = t.receiveAndConvert();
if (result == null) {
    System.out.println("No message within wait timeout");
} else {
    System.out.println("Received: " + result);
}
```

This is a **snippet inside a method that already has `ConnectionFactory`**, not a standalone program. `receiveAndConvert()` returns `null` when the wait time expires without receiving a message. Positive timeout values are in **milliseconds**; `JmsTemplate`'s default may wait **indefinitely**, so set an appropriate `receiveTimeout` when using synchronous receive in requests/workers.

**Warning about Queues:** if you use `receiveAndConvert()` and `@JmsListener` listening on `orders.created` at the same time, the two consumers **compete**. There is no guarantee `receiveAndConvert()` will get the message just sent; the listener may have consumed it first. The demo in section 7 uses only listeners for the default Queue for easy observation and to avoid this confusion.

When continuous asynchronous processing is needed, use `@JmsListener` instead of an arbitrary thread-blocking `receive()` loop. For Topics, online/offline subscription semantics must also be accounted for; calling `receive()` does not automatically create a long-lived durable subscription.

## 11. Default destination does not determine delivery semantics

Configuring a default destination only chooses **where to send or receive**. The remaining concerns are independent:

- **Message body:** `convertAndSend(String)` uses a `MessageConverter` (by default usually `SimpleMessageConverter`); `send(MessageCreator)` lets you create `TextMessage`, `BytesMessage`, etc. directly.
- **JMS headers/properties:** can be set in `MessageCreator` or via `MessagePostProcessor`; `setDefaultDestinationName` does not populate content type, schema, or event ID.
- **Transactions and acknowledgment:** determined by `JmsTemplate`, session, listener container, and transaction manager. If processing rolls back, the broker may redeliver; a default destination on the template does not automatically guarantee exactly-once side effects.
- **Delivery mode, priority, TTL:** configurable via QoS when appropriate; Spring `JmsTemplate` provides `setExplicitQosEnabled`, `setDeliveryMode`, `setPriority`, and `setTimeToLive`. Whether they take effect depends on explicit QoS settings and the provider.
- **Security and quotas:** factory credentials, broker authorization, destination policies, DLQ, retries, and max size must all be configured separately.

If using a shared template bean across multiple threads, set its properties **once at initialization**. Changing default destination, `MessageConverter`, or `pubSubDomain` while requests are actively sending can lead to unintended routing. Choose overloads with explicit destinations or multiple fixed templates when different routes are needed.

## 12. Common issues and troubleshooting

| Symptom | Likely cause | Check |
| --- | --- | --- |
| `JmsTemplate` bean fails to be created | Missing `ConnectionFactory`, missing JMS starter/client, or bean conflict. | Check dependencies and Spring context; inspect root cause. |
| `convertAndSend("A")` reports missing default | `defaultDestinationName`/`defaultDestination` is not set on the template in use. | Inspect the injected bean, Boot config, and bean names. |
| Sending with explicit destination works | Factory is likely fine, only default configuration is missing. | Distinguish `convertAndSend(Object)` vs `convertAndSend(String,Object)` overloads. |
| No messages seen on expected Queue | Sent to Topic instead of Queue, wrong name, wrong broker, or competing listener. | Check `pubSubDomain`, destination resolver, endpoint, and ACLs. |
| `@JmsListener` ignores template default | Listener has its own factory/annotation. | Inspect `@JmsListener(destination=...)` and listener container factory. |
| JNDI destination lookup fails | Resource name unbound or wrong `resourceRef`. | Check server naming context and `JndiDestinationResolver`. |
| Provider rejects send | Queue/Topic not created, missing permissions, TLS/broker error, or exhausted pool. | Check broker logs, ACLs, health, and resource provisioning. |
| `receive()` “hangs” | Synchronous receive called without timeout or no messages available. | Use `setReceiveTimeout`/Boot property and check for other consumers. |
| Intended template A but actually used B | Multiple `JmsTemplate` beans without `@Qualifier`/`@Primary` on injection. | Inspect bean graph and unit/integration tests. |
| Re-running demo shows duplicate logs | Broker kept backlog, producer ran again, or redelivery occurred. | Check message ID, event ID, session/ack, and transactions. |

### Debugging in order

1. Identify **the exact `JmsTemplate` instance** injected into the service; if there are multiple, verify `@Qualifier`.
2. Identify **which factory** is attached to the template, and which provider and broker endpoint it uses.
3. Check whether the default destination is set by **name or object**, and whether the called method passes an explicit destination.
4. Check `pubSubDomain` and `DestinationResolver`; for listeners, also check their separate container factory.
5. Check broker logs/management console, permissions, destination existence, and delivery/ack/transaction settings.
6. Run a smoke test with a clean Queue, a small payload with an event ID, and a single consumer, then scale concurrency once routing is confirmed.

Do not debug by adding more Queues or changing a batch of properties at once. Change one setting, verify where messages actually go, and then proceed.

## 13. Self-check

**Question 1.** A template has default `orders.created`. Where does `convertAndSend("hello")` send?

**Answer:** To the default destination `orders.created`, because this is the payload-only overload.

**Question 2.** Does `convertAndSend("orders.audit", "hello")` send to `orders.created`?

**Answer:** No. `orders.audit` is an explicit destination, overriding the default selection for that call.

**Question 3.** Why does setting `spring.jms.template.default-destination=orders.created` not automatically make `@JmsListener` start listening on `orders.created`?

**Answer:** The default belongs only to `JmsTemplate`; listeners determine their destination via their annotation and container factory.

**Question 4.** A `JmsTemplate` has `setPubSubDomain(true)` and default name `orders.created`. Is that name interpreted as a Queue or a Topic when using the default dynamic resolver?

**Answer:** **Topic**. With `false`, it is a Queue; if passing a `Destination` object, the object's type determines it.

**Question 5.** When an application has two `ConnectionFactory` beans pointing to two brokers, does changing `setDefaultDestinationName` switch to the other broker?

**Answer:** No. The template still uses the factory attached to it; switching brokers requires selecting the corresponding template/factory.

**Question 6.** Is `receiveAndConvert()` with a 2-second timeout guaranteed to get the message just sent if a `@JmsListener` is competing on the same Queue?

**Answer:** No. Two consumers are competing; the listener may receive it first. If the wait expires, the method can return `null`.

## 14. Reference documentation

- [Spring Framework 6.2: JmsTemplate JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework: Sending a Message with JmsTemplate](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework: Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework: DynamicDestinationResolver](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/DynamicDestinationResolver.html)
- [Spring Framework: JndiDestinationResolver](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html)
- [Spring Boot 3: JMS configuration and auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html)
- [Jakarta Messaging 3.1 API](https://jakarta.ee/specifications/messaging/3.1/)

**Remember:** `ConnectionFactory` decides **how to connect to the provider**; default destination in `JmsTemplate` decides **the target for calls that do not pass a destination**; Queue/Topic, listener routing, delivery QoS, and transactions are separate configurations that must be managed consistently.
