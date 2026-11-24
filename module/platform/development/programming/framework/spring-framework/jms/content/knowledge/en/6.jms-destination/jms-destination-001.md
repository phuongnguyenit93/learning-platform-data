# Pre-existing Destinations and Destination Names in Application Code (Spring JMS)

## 1. The problem: connecting an application to an existing destination

In a JMS system, the broker receives, stores, and distributes messages through **destinations**. A destination can be a **queue** (point-to-point model) or a **topic** (publish/subscribe model). A common scenario in enterprise systems is that infrastructure has already created the queue/topic; the Spring application only needs to know the exact **name** and how to access it to send or receive messages.

For example: the operations team has configured the `orders.in` queue on the broker. The ordering service must send to this exact queue, while the order processing service listens on the same queue. Both sides need to agree on the name, destination type, broker/namespace, and access permissions. Declaring the string `"orders.in"` in Java does not by itself prove that the queue exists.

**After this lesson, you will be able to:** distinguish a physical destination from a JMS object and a logical name in code; configure Spring JMS to point to an existing queue; understand how Spring resolves names; choose between string configuration, `Destination` objects, and JNDI; and check for errors caused by wrong names or wrong destination types.

## 2. Three layers to distinguish

| Layer | Example | Role |
| --- | --- | --- |
| Physical resource managed by the broker | Queue `orders.in`, pre-provisioned | Where the broker routes/stores messages according to the broker's own configuration |
| JMS object in the application | `jakarta.jms.Queue` / `jakarta.jms.Topic`, both are `Destination` | Handle for the JMS API to send/receive; may simply wrap a name understood by the provider |
| Name that Spring receives from code/config | `"orders.in"`, `${app.jms.orders.input}`, or `"jms/OrdersQueue"` | Input to `DestinationResolver`; how it maps to a JMS object depends on the resolver |

`ConnectionFactory` defines how to connect to the provider/broker; **it does not replace the destination name**. The same string `orders.in` on two different brokers does not mean the same queue.

- **Queue:** each message is delivered to one eligible consumer among competing consumers on the same queue; not every consumer receives a copy.
- **Topic:** messages are broadcast to matching subscriptions; offline redelivery behavior depends on subscription type, durability, and provider configuration.
- **Logical/JNDI name:** `jms/OrdersQueue` may be a lookup key for a pre-administered `Queue` object, while the physical name in the broker may differ. Do not assume these two strings are the same.

## 3. Responsibilities when using a pre-existing destination

**The infrastructure/broker side** creates or provisions the queue/topic as supported by the provider, setting the routing type, address/name, send/receive permissions, storage policy, redelivery, and dead-letter settings when needed. With ActiveMQ Artemis, for example, a point-to-point queue is typically bound to an address with routing type `ANYCAST`; details depend on broker configuration.

**The Spring application side** uses the configured `ConnectionFactory`, selects the right destination name and type, and then sends via `JmsTemplate` or receives via `@JmsListener`. The application should not rely on the broker's auto-create feature if the deployment contract specifies that queues must be pre-provisioned.

A minimal configuration contract should specify:

| Attribute | Example |
| --- | --- |
| Broker or cluster | `tcp://localhost:61616` in the practice environment |
| Destination type | `queue` |
| Destination name at broker | `orders.in` |
| Direction of use | Producer sends, consumer receives |
| Permissions | Account allowed to send/consume on the right destination |
| Creation rule | Pre-provisioned; explicitly state whether the broker allows auto-create |

Names should be treated as an **integration contract between systems**. Avoid renaming arbitrarily or deriving names from class/method names. If each environment uses a different namespace, set the value in deployment configuration rather than concatenating prefixes scattered across code.

## 4. Spring JMS example: sending and receiving with an existing queue name

Assume the `orders.in` queue **has already been created on the broker** and the application account is permitted to send/receive. The example uses Java 17+, Spring Boot 3.x (Spring Framework 6+, `jakarta.jms` namespace), and ActiveMQ Artemis in external broker mode. The classes below belong to a Spring Boot project with JMS support; they are **not standalone Java SE programs**.

With Gradle Groovy, add the starter (version managed by Spring Boot dependency management):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

Create `src/main/resources/application.yml`:

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
      input: "orders.in"
```

Here `spring.artemis.*` configures the connection, while `app.jms.orders.input` is the queue name used by the program. You must provide `JMS_USER` and `JMS_PASSWORD` environment variables matching the broker; the default URL value is only for practice convenience. In real deployments, destination configuration and connection details should come from a configuration/secrets management system.

Create `src/main/java/demo/jms/DemoApplication.java`:

```java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Create `src/main/java/demo/jms/OrderPublisher.java`:

```java
package demo.jms;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private final JmsTemplate jmsTemplate;
    private final String queueName;

    public OrderPublisher(
            JmsTemplate jmsTemplate,
            @Value("${app.jms.orders.input}") String queueName) {
        this.jmsTemplate = jmsTemplate;
        this.queueName = queueName;
    }

    public void publish(String orderId) {
        jmsTemplate.convertAndSend(queueName, orderId);
    }
}
```

In `convertAndSend(queueName, orderId)`, the first argument is the **destination name**, and the second argument is the payload. With Spring JMS's default converter, a `String` is sent as a JMS `TextMessage`. Do not swap the two arguments or confuse the queue name with the message content.

Create `src/main/java/demo/jms/OrderConsumer.java`:

```java
package demo.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {
    @JmsListener(destination = "${app.jms.orders.input}")
    public void receive(String orderId) {
        System.out.println("Received order: " + orderId);
    }
}
```

`@JmsListener` reads the destination name from the same property as the producer. `@EnableJms` enables the listener annotation infrastructure in Spring; Spring Boot can auto-configure `JmsTemplate`, `ConnectionFactory`, and the listener factory when the corresponding starter/provider is present.

To send a test message when running the `demo` profile, add `src/main/java/demo/jms/DemoSendRunner.java`:

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
        publisher.publish("ORDER-1001");
    }
}
```

Start a broker with the `orders.in` queue first, supply credentials, and run the application with the `demo` profile (for example `./gradlew bootRun --args='--spring.profiles.active=demo'` in a Gradle Boot project with the `bootRun` task configured). When the connection and permissions are correct, the runner sends a message and the listener can print:

```text
Received order: ORDER-1001
```

This is the **expected output line from the listener**, not the entire Spring Boot stdout. Receiving happens asynchronously; when the log line appears depends on the broker, listener, and environment. Do not enable the `demo` profile in production because it intentionally sends a sample order on every startup.

Processing flow:

```text
application.yml
  app.jms.orders.input = orders.in
        |
        +--> OrderPublisher --> JmsTemplate --> DestinationResolver
        |                                    --> broker queue orders.in
        |
        +--> @JmsListener --> listener container --> consumer of orders.in
```

Configuring the name in one place lets the producer and consumer share the same contract; they can still live in **two separate applications** as long as both connect to the right broker/destination.

## 5. Where can destination names appear in code?

| Usage | Example | When appropriate / notes |
| --- | --- | --- |
| Inline string literal | `jmsTemplate.convertAndSend("orders.in", body)` | Small demos; easy to mistype if repeated in many places |
| Java constant | `static final String ORDERS_IN = "orders.in";` | Reduces typos within one deployment; changing names per environment still requires rebuilding |
| Externalized configuration | `@Value("${app.jms.orders.input}")` | Usually best when infrastructure supplies the destination; value can vary by environment |
| Template default destination | `setDefaultDestinationName("orders.in")` then `convertAndSend(body)` | Producer mainly sends to one destination; must distinguish overloads with/without name parameter |
| `Destination` object | `convertAndSend(destination, body)` | When you already have a `Queue`/`Topic` object or it is injected from configuration/JNDI |
| JNDI lookup name | `jms/OrdersQueue` | Environments managing destinations under JNDI; requires an appropriate resolver/lookup |

If using constants, centralize them in a contract-definition class instead of duplicating literals. If using properties, ensure values are non-empty and validate at startup; log the effective destination name in configuration logs (do not log credentials). Do not construct different names by concatenating arbitrary user input, as this can create unintended destinations on brokers that allow auto-create.

## 6. How does Spring resolve a string into a Destination object?

`JmsTemplate` does not send directly to a string: it asks `DestinationResolver` to convert the name into a JMS `Destination` object. By default `JmsTemplate` uses `DynamicDestinationResolver`:

1. Spring receives `destinationName`, for example `orders.in`.
2. The resolver checks the `pubSubDomain` flag to choose `Session.createQueue("orders.in")` (queue) or `Session.createTopic("...")` (topic).
3. The JMS provider returns a `Queue`/`Topic` object, and Spring sends/receives through the provider.

**Common pitfall:** according to Jakarta Messaging, `Session.createQueue(name)` creates a **Java object representing the queue**, *not a standard command to create a physical queue on the broker*. Some providers have an auto-create feature when accessing a non-existent name; others require an administrator to create it beforehand or reject it. Therefore, "the code compiles", "`createQueue` was called", and "the queue exists on the broker" are three different things. To ensure you are using a pre-existing destination, check broker configuration/permissions and do not rely on auto-create.

By default `JmsTemplate` has `pubSubDomain=false`, meaning dynamic resolution as a queue. If the actual destination is a **topic**, you must configure both the producer and listener factory for the pub/sub domain; renaming a string from `queue.foo` to `topic.foo` does not automatically switch processing to topic mode. With topics, consider durable/shared subscriptions depending on message delivery requirements.

Two overloads to distinguish:

```java
// With a specific destination name: sends to the destination resolved from "orders.in".
jmsTemplate.convertAndSend("orders.in", "ORDER-1001");

// Without a destination name: only valid when a default destination is configured.
jmsTemplate.convertAndSend("ORDER-1001");
```

The snippet above illustrates calls inside a method with an injected `JmsTemplate`; it is not a standalone runnable Java class. The second call requires `defaultDestination` or `defaultDestinationName` to be configured appropriately.

## 7. When the broker provides destinations via JNDI

Some enterprise environments do not want application code to contain physical names. Infrastructure publishes pre-administered JMS objects through JNDI, such as `jms/OrdersQueue`, mapped to an actual queue. In that case, `JndiDestinationResolver` can be used so Spring resolves the **lookup name** into a `Destination`.

The following Java configuration example is a **snippet inside a `@Configuration` class**, assuming the JNDI context is configured and lookup works:

```java
@Bean
DestinationResolver destinationResolver() {
    JndiDestinationResolver resolver = new JndiDestinationResolver();
    resolver.setFallbackToDynamicDestination(false);
    return resolver;
}
```

The corresponding imports are `org.springframework.context.annotation.Bean`, `org.springframework.jms.support.destination.DestinationResolver`, and `org.springframework.jms.support.destination.JndiDestinationResolver`. In Spring Boot, when using JMS auto-configuration, a `DestinationResolver` bean can be applied to `JmsTemplate` and the default listener factory; if you create these beans manually, attach the resolver consistently to both.

With JNDI, `@JmsListener(destination = "jms/OrdersQueue")` and `JmsTemplate.convertAndSend("jms/OrdersQueue", payload)` refer to a **lookup key**, not necessarily a physical queue name. A matching provider/JNDI binding must exist. `JndiDestinationResolver` does not fall back to dynamic destinations by default; setting `false` in the example makes explicit the intent to catch lookup errors rather than silently accepting an unexpected destination name.

**Which approach to choose?** If the system only provides queue names on the broker and has no JNDI, using externalized properties with the dynamic resolver is usually simpler. If infrastructure provisions objects via JNDI, use the JNDI name per the contract and configure lookup. Do not turn a JNDI name into a broker name on your own.

## 8. Pre-deployment checklist

1. **Confirm existence:** check the broker console/CLI or IaC configuration to confirm the queue/topic exists, along with its exact name and routing type. If the broker has multiple namespaces/vhosts/clusters, confirm the right scope.
2. **Confirm producer and consumer:** both sides reference the same actual destination; agree on queue/topic and `pubSubDomain`/listener factory configuration. If using JNDI, confirm the mapping on both sides.
3. **Confirm permissions:** the application user has connect, send, and consume permissions respectively; do not infer from a successful connection that permissions on the destination are sufficient.
4. **Send a test message with an identifier:** observe that the producer sends successfully, the broker receives the message, and the consumer processes it once as expected in the test environment; check queue depth, consumer count, and listener logs.
5. **Control auto-creation:** know for sure whether the broker has auto-create enabled. When testing with a wrong name on a broker with auto-create, a "ghost" queue can appear and make the producer think it sent to the right place.
6. **Verify contract stability:** document the name, type, owner, configuration location, renaming rules, payload schema, and error-handling policy.

If messages are consumed quickly, a queue depth returning to 0 does not mean no message ever arrived; combine enqueue/dequeue statistics, traces, or logs with correlation IDs.

## 9. Common errors and how to identify them

| Symptom | Causes to check | Remediation |
| --- | --- | --- |
| `InvalidDestinationException` or destination-not-found error | Wrong name; queue/topic not provisioned; broker disallows auto-create; wrong JNDI lookup | Cross-check name/routing on broker; fix config or provision via operations process |
| Producer reports success but consumer receives nothing | Sides point to different brokers/namespaces or different names; wrong queue auto-created; consumer not running | Compare effective config values, broker URL, consumer count, and metrics of the real destination |
| Listener runs but does not receive as expected | Queue/topic mismatch; incorrect topic subscription; message selector filtering out; another consumer competing on queue | Check `pubSubDomain`, listener container, selector, and queue/topic model |
| Access permission error | User can connect but lacks send/consume or create/read destination permissions | Grant least-privilege permissions on the exact queue/topic |
| Queues with nearly identical names exist | Literal typo, case difference, environment prefix, or concatenated names | Standardize contract and properties; inspect list of generated destinations |
| `convertAndSend(payload)` has no destination | Calling the overload without a name when no default destination is configured | Use `convertAndSend(destinationName, payload)` or configure default explicitly |
| JNDI cannot find `jms/OrdersQueue` | Missing binding/Context or wrong lookup configuration | Verify JNDI context/binding; distinguish lookup name from physical name |

Do not fix destination naming errors by letting applications auto-create every queue in production: that hides contract bugs and can bypass broker operational policies.

## 10. Key takeaways and self-check questions

- **The name in code** is input for Spring to resolve a destination; **the physical resource** belongs to the broker and has its own lifecycle and permissions.
- Both `JmsTemplate` and `@JmsListener` can use the same property; choosing the right queue/topic and the right environment matters more than class naming.
- According to the standard, `Session.createQueue` / `createTopic` only creates a reference object; auto-creating physical resources depends on the JMS provider/broker.
- Use properties for deployment names, use JNDI when infrastructure provides bindings, and verify readback/metrics on the broker when testing connectivity.

Self-check: (1) If `convertAndSend("orders.in", body)` succeeds but the listener does not receive anything, which values would you compare? (2) Does `Session.createQueue("orders.in")` guarantee that the physical queue has been created? (3) Why does `@JmsListener(destination = "jms/OrdersQueue")` not necessarily use the physical queue name `jms/OrdersQueue`?

### References

- Spring Framework 6.2 — Using Spring JMS, Destination Management section: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Boot — JMS and ActiveMQ Artemis configuration: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Jakarta Messaging — `Session.createQueue(String)` and meaning of destination objects: https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/session
