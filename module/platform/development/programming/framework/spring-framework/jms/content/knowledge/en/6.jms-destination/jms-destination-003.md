# DynamicDestinationResolver and Physical Provisioning Limits in Spring JMS

## Learning objectives

After this lesson, you will be able to:

1. Explain why `DynamicDestinationResolver` converts a **logical name** into a JMS `Queue` or `Topic` object yet **does not guarantee creating a physical resource** in the broker.
2. Trace the destination resolution flow of `JmsTemplate` and the listener container: `DestinationResolver.resolveDestinationName(Session, String, boolean)` → `Session.createQueue(...)` / `createTopic(...)`.
3. Distinguish a **declared/looked-up destination**, a **Java object representing a destination**, a **broker-provisioned address/queue/topic**, and a **temporary destination**.
4. Know when to use `JndiDestinationResolver`, pre-provision with broker tools, or allow broker auto-create.
5. Assess risks from dynamically named destinations: proliferating queues, Queue/Topic confusion, queue fragmentation, resource leaks, ACL/tenant isolation, and potential message loss.
6. Write and run a Spring Boot + Jakarta Messaging + Artemis example while verifying the actual resource state in the broker.

**Core idea:** `DynamicDestinationResolver` is a **name-resolution strategy on the Spring application side**, not a broker administration API or a tool that guarantees queue/topic provisioning. The word "dynamic" describes using the name at runtime; it **does not guarantee** that the broker will allocate a physical destination.

## 1. The problem: what does a destination name in code mean?

Spring applications often contain very short calls:

~~~java
jmsTemplate.convertAndSend("orders.incoming", "order-42");
~~~

Beginners easily infer that this statement means "Spring created the `orders.incoming` queue and stored the message in it." In reality there are three independent steps:

~~~text
Spring application
   |
   | String name = "orders.incoming"
   v
JmsTemplate / DestinationResolver
   |
   | returns javax.jms.Destination or jakarta.jms.Destination
   | (with Spring 6+ it is jakarta.jms)
   v
JMS client/provider
   |
   | uses Destination object for send/createConsumer
   v
Broker
   |
   | checks address/queue/topic/subscription, permissions, and policies
   | may: already exist / auto-create / return error / have no receiving route
   v
Physical resource and messages actually stored/routed
~~~

The "resolve name" step **is not synonymous with** the "allocate physical resource" step. A name identifier can be valid on the client while the broker lacks the queue, the broker has auto-create disabled, the user lacks create/write permissions, or the name refers to the wrong destination type.

### Layers of responsibility

| Layer | Object/example | Actual responsibility |
|---|---|---|
| Application | `"orders.incoming"`, config `app.jms.ordersQueue` | Chooses the name and business meaning. |
| Spring JMS | `DestinationResolver`, `JmsTemplate`, listener container | Turns the name into a `Destination` understood by the JMS client. |
| Jakarta Messaging API | `Session.createQueue(String)`, `createTopic(String)` | Creates a **reference object** to a destination named according to the provider. |
| JMS provider/client | E.g. Artemis Jakarta client | Translates Java calls into broker interactions per protocol/provider. |
| Broker | Address, queue, routing, subscription, journal, ACL | Manages actual resources, durability config, retention, routing, auto-create, DLQ. |
| Operations | Admin API, CLI, XML/IaC | Provisions/controls configuration and resource lifecycle. |

This lesson belongs to the **Destination** group. We focus on how destinations are identified and provisioning limits; transaction, acknowledgement, or retry are only mentioned where they affect testing and diagnosis.

## 2. What is `DestinationResolver`?

Spring declares the interface:

~~~java
package org.springframework.jms.support.destination;

// Illustrative signature; import from the actual spring-jms library.
public interface DestinationResolver {
    Destination resolveDestinationName(
            Session session,
            String destinationName,
            boolean pubSubDomain) throws JMSException;
}
~~~

In Spring 6/7, `Destination`, `Session`, and `JMSException` here belong to package `jakarta.jms`. Spring 5 projects use `javax.jms`; do not mix namespaces.

Parameter meanings:

- `session`: the JMS session currently used by Spring; the dynamic resolver needs the session to call the reference-creation API.
- `destinationName`: string name passed by the caller or listener configuration.
- `pubSubDomain`: `false` means **Queue** (point-to-point), `true` means **Topic** (publish/subscribe).
- Result: a `jakarta.jms.Destination`; can be a `Queue` or `Topic`. This is a reference, not proof that the broker already has the destination.

Spring has multiple resolution strategies. `DynamicDestinationResolver` is the **default** for `JmsTemplate`. `JndiDestinationResolver` finds a Destination placed in JNDI. Applications can also implement `DestinationResolver` themselves to enforce whitelists or map by environment or tenant.

### When must Spring resolve?

- `jmsTemplate.send("orders.incoming", creator)` or `convertAndSend("orders.incoming", payload)`: caller passes a String, and the template needs to turn the name into a `Destination`.
- `@JmsListener(destination = "orders.incoming")`: the listener container needs a destination to create a JMS consumer; it typically uses the container's `DestinationResolver`.
- `jmsTemplate.receive("orders.incoming")`: needs a destination to create a synchronous receive consumer.

If code already passes a `Destination` object to the appropriate API overload, re-resolving from a String name may not be needed.

## 3. What does `DynamicDestinationResolver` do?

Class in package:

~~~java
org.springframework.jms.support.destination.DynamicDestinationResolver
~~~

In essence, how it works is:

~~~java
// MECHANISM ILLUSTRATION CODE, not verbatim Spring source.
public Destination resolveDestinationName(
        Session session, String destinationName, boolean pubSubDomain)
        throws JMSException {
    if (pubSubDomain) {
        return session.createTopic(destinationName);
    }
    return session.createQueue(destinationName);
}
~~~

The resolver's `resolveTopic(...)` and `resolveQueue(...)` methods let Spring branch to the corresponding type. The value of `pubSubDomain` takes effect at **resolution time**, not merely as a decorative label.

| Input | Typical JMS call | Result type |
|---|---|---|
| `"orders.incoming"`, `pubSubDomain=false` | `session.createQueue("orders.incoming")` | `Queue` |
| `"orders.incoming"`, `pubSubDomain=true` | `session.createTopic("orders.incoming")` | `Topic` |
| `"billing.queue"`, `pubSubDomain=false` | `session.createQueue("billing.queue")` | `Queue` |
| `"order.events"`, `pubSubDomain=true` | `session.createTopic("order.events")` | `Topic` |

A String name **does not by itself indicate** whether it is a Queue or a Topic. Two systems using the same String with different `pubSubDomain` settings may connect to different resources, experience different behavior, or be rejected by the broker.

### 3.1. Does not call JNDI by default

`DynamicDestinationResolver` does not look up names in JNDI on its own. It uses `Session`. If a deployment requires JNDI-administered destinations, configure `JndiDestinationResolver` or inject a `Destination` object obtained from JNDI directly.

### 3.2. Does not choose a good naming policy for you

The resolver accepts the passed-in name and delegates to the JMS provider. It does not guarantee:

- Adherence to an allowed queue list.
- Names matching the environment/tenant.
- Preventing accidental queue generation from user input.
- Queues being provisioned with proper retention, DLQ, max consumers, and quotas.
- The Queue/Topic existing on the right connected broker.
- The user having permission to send/receive/create the resource.

Those controls belong to the application layer, broker deployment, and operations.

## 4. Jakarta Messaging boundary: `createQueue` does not create a physical queue

The Java API defines:

~~~java
Queue queue = session.createQueue("orders.incoming");
Topic topic = session.createTopic("orders.events");
~~~

Key points in the Jakarta Messaging Javadoc:

- `Session.createQueue(String)` creates a **Queue object describing a queue name per the provider**.
- `Session.createTopic(String)` creates a **Topic object describing a topic name per the provider**.
- These two APIs **are not specified as operations that create physical resources** on the broker. The JMS API does not standardize a universal command to create physical queues/topics.
- A provider may **auto-create** the resource when the application sends/receives, or even during resolution, if extensions/auto-create exist; that is **provider-specific** behavior.
- Using provider-specific names can reduce application portability across different JMS brokers.

Therefore, the following two statements must be kept distinct:

1. "`DynamicDestinationResolver` resolved the name to a `Queue`" — describes the client-side result.
2. "The broker has allocated a durable queue and messages will be stored there" — requires checking **configuration, broker state, and send/receive results**.

**Do not treat a successful `createQueue` call as proof of successful provisioning.**

### 4.1. "Dynamic destination" differs from "Temporary destination"

| Aspect | Dynamic destination (by name) | Temporary destination (`createTemporaryQueue/Topic`) |
|---|---|---|
| Identity | Name chosen by application, e.g., `orders.incoming` | Provider generates temporary identity |
| JMS API called | `createQueue(name)` / `createTopic(name)` | `createTemporaryQueue()` / `createTemporaryTopic()` |
| Physical creation per spec | **Not guaranteed** | JMS API has a mechanism to create temporary destinations |
| Lifecycle | Broker/admin policy; may persist long-term | Bound to owning connection and temporary destination rules |
| Use case | Queue/Topic known by runtime name | Temporary reply queue in request-reply, temporary session |

`DynamicDestinationResolver` is **not** an alias for `Session.createTemporaryQueue()`. Despite having "dynamic" in its name, a destination resolved from a String may be a pre-existing queue, or auto-created by the broker per configuration and remain after the application stops.

### 4.2. "Destination object" differs from "producer/consumer"

Creating a `Queue` object is not the same as creating a `MessageProducer` or `MessageConsumer`. Only calls like `createProducer(queue)`, `createConsumer(queue)`, `send`, or Spring listener startup actually trigger the required interaction with the provider/broker; only then can the broker enforce permission, routing, and auto-create rules.

## 5. Real-world scenarios when resolving a name

Suppose `DynamicDestinationResolver` is called with `"orders.incoming"`, `pubSubDomain=false`:

### Scenario A — Queue is pre-provisioned

The broker already has the `orders.incoming` queue with managed routing, durability, ACLs, and DLQ. The resolver returns the `Queue` object, and producer/consumer use that queue. This is the most controllable model for production.

### Scenario B — Broker has matching auto-create enabled

The broker does not yet have the queue, but configuration allows auto-creating the queue when a producer sends or a consumer attaches. In that case the broker may create the physical queue with **default attributes** according to matching policies. This is broker behavior, not a Spring guarantee.

Suitable for experimentation or intentionally designed runtime destinations, though production requires clear quotas and lifecycles.

### Scenario C — Broker disables auto-create, queue does not exist

The resolver may still return a `Queue` object. When the producer sends or the consumer creates a listener, the broker/provider may report an invalid/non-existent destination, reject the consumer, or handle unrouted sends according to policy. **Do not assume a single exception or outcome across all brokers.**

### Scenario D — Valid name but no permission

The queue may exist, yet the connected principal lacks `send`/`consume` or creation permissions. The resolver does not grant permissions. The error occurs when the client performs the forbidden operation, typically at send or consumer initialization, and the error type depends on the provider.

### Scenario E — Destination is a Topic, code configures Queue

If the producer resolves `"orders.events"` as a Queue while the subscriber resolves the same name as a Topic, the two sides do not share semantics. With brokers that have addresses and anycast/multicast queue routing, a mismatch can result in no matching consumer or messages being misrouted.

### Scenario F — Send succeeds but subscriber receives nothing

With a JMS Topic, a **non-durable subscription** generally does not retroactively receive messages published while the subscriber was offline. Having a physical destination does not mean the broker will store all messages for a subscriber that did not exist yet. Choose durable/shared subscriptions as appropriate; do not blame the resolver.

## 6. `pubSubDomain`: lock in the destination type upfront

Spring `JmsDestinationAccessor` and `JmsTemplate` have the property:

~~~java
jmsTemplate.setPubSubDomain(false); // Queue; default value
jmsTemplate.setPubSubDomain(true);  // Topic
~~~

You should not repeatedly mutate this property on a singleton `JmsTemplate` at runtime while other threads are using it; finish configuring it before the bean starts serving requests.

- `false` = point-to-point `Queue` when resolving by name.
- `true` = publish/subscribe `Topic` when resolving by name.
- Flipping the flag alone never converts a physical queue into a physical topic.

In Spring Boot, the property `spring.jms.pub-sub-domain=true` can configure auto-configured JMS components for Topic mode. If you define `JmsTemplate` or listener factories manually, configure them consistently.

### Consequences when producer and listener use different domains

~~~text
Producer:
  JmsTemplate(pubSubDomain=false)
    └─ "orders.events" → Session.createQueue("orders.events")

Listener:
  ListenerFactory(pubSubDomain=true)
    └─ "orders.events" → Session.createTopic("orders.events")

Same String name but different JMS Destination types!
~~~

There is no rule that a Queue and Topic with the same name automatically connect to each other. Use clear names (for example `orders.commands` / `orders.events`), verify broker routing, and run end-to-end tests against the provisioned names.

## 7. How Spring JMS connects the resolver to `JmsTemplate`

### 7.1. Resolving names via `JmsTemplate`

~~~java
// Snippet inside a bean with jakarta.jms.ConnectionFactory injected.
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDestinationResolver(new DynamicDestinationResolver());
template.setPubSubDomain(false); // Select Queue
template.convertAndSend("orders.incoming", "order-42");
~~~

This snippet uses `org.springframework.jms.core.JmsTemplate` and `org.springframework.jms.support.destination.DynamicDestinationResolver`. Creating the resolver manually is unnecessary since it is already the **default**, though declaring it explicitly is illustrative. `convertAndSend` uses the template's message converter (String usually becomes `TextMessage`), opens/obtains a session, resolves the destination, and sends via the provider.

**You cannot conclude** that a physical queue was created solely from a `convertAndSend` call. Before sending, know the broker policy; after sending, verify the actual queue/subscription and routing.

### 7.2. Default destination

You can configure `template.setDefaultDestinationName("orders.incoming")` to use `convertAndSend(payload)` without passing a name every time. The default name is **still** subject to the resolver, Queue/Topic flag, permissions, and broker provisioning. Default destination is a naming configuration, not a resource-creation tool.

### 7.3. Listener containers also need a resolver

A `@JmsListener` does not automatically inherit every setting of an arbitrary `JmsTemplate` bean. Listener containers have their own `DestinationResolver` and `pubSubDomain` settings via `DefaultJmsListenerContainerFactory`, for example:

~~~java
@Bean
DefaultJmsListenerContainerFactory queueListenerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setDestinationResolver(new DynamicDestinationResolver());
    factory.setPubSubDomain(false);
    factory.setSessionTransacted(true);
    return factory;
}
~~~

If you define your own factory, remember to set `ConnectionFactory` and transaction/concurrency requirements. For messages to actually reach the listener, producer and consumer must agree on the name, destination type, broker cluster, credentials, and routing.

## 8. `DynamicDestinationResolver` vs `JndiDestinationResolver`

Spring provides `JndiDestinationResolver` to map names to Destination objects **already registered in JNDI** instead of creating references with `Session.createQueue/Topic`.

| Aspect | `DynamicDestinationResolver` | `JndiDestinationResolver` |
|---|---|---|
| Mapping source | `Session.createQueue/Topic(name)` | JNDI lookup of resource name |
| Requires JNDI registry | No | Yes, with matching JNDI environment |
| Name interpretation | Broker/provider name string | JNDI name, which may differ from physical name |
| Proves physical queue exists? | No | **Not operational proof either**; JNDI object may point to wrong/missing/unauthorized resource |
| When name fails to resolve | JMS provider may return reference/error | JNDI lookup fails, unless fallback is enabled |
| Fallback to dynamic | Dynamic itself | `setFallbackToDynamicDestination(true)` (default **false**) |
| Caching | Not a registry/provisioning manager | Caches JNDI results by default **true**, can disable via `setCache(false)` |
| Typical use case | Dev/test; broker auto-create; names managed outside code | App server/enterprise environments managing JMS destinations via JNDI |

Example of strict JNDI configuration:

~~~java
@Bean
JmsTemplate jndiTemplate(ConnectionFactory connectionFactory) {
    JndiDestinationResolver resolver = new JndiDestinationResolver();
    resolver.setCache(true);
    resolver.setFallbackToDynamicDestination(false);

    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setDestinationResolver(resolver);
    template.setPubSubDomain(false);
    return template;
}
~~~

*Snippet placed inside a `@Configuration` class with corresponding Spring imports; the JNDI context must be configured by the environment*. With `fallback=false`, looking up a missing name raises an error instead of trying dynamic resolution. This is useful when a resource must be approved by an admin.

Note that Spring's `JndiDestinationResolver` caches by **destination name**; if a Queue and Topic share the same name, caching/mismatch behavior can cause confusion. Use distinct names and clearly scoped resolvers/factories.

### 8.1. Should fallback be enabled?

~~~java
resolver.setFallbackToDynamicDestination(true);
~~~

Enabling fallback means if a JNDI entry is not found, the resolver can fall back to `DynamicDestinationResolver`. This is convenient in dev, yet **does not mean** "valid auto-provisioning." In production with strict governance policies, fallback can silently hide naming/JNDI errors and depend on broker auto-create; evaluate carefully before enabling.

## 9. Physical provisioning limits: what does a broker actually create?

Not every broker represents Queue/Topic with the same internal structure. Taking **ActiveMQ Artemis** as an example:

- **Address**: message routing point.
- **Queue**: resource receiving and storing messages bound to an address.
- **ANYCAST routing type**: messages are typically routed to one matching queue on the address.
- **MULTICAST routing type**: messages are distributed to matching queues/subscriptions on the address.

The JMS Queue and JMS Topic models are mapped by Artemis to corresponding addresses/queues/routing/subscriptions. This structure is **Artemis-specific**, not a JMS spec mandated across all providers.

### 9.1. Auto-create in Artemis

Artemis address settings allow managing:

- `auto-create-addresses`: whether to create an address when a client uses a non-existent address.
- `auto-create-queues`: whether to create the corresponding queue when needed.
- `default-address-routing-type` and `default-queue-routing-type`: default routing.
- `auto-delete-addresses`, `auto-delete-queues`, and deletion conditions/delays: lifecycle of auto-created resources.
- Permissions `createAddress`/`createDurableQueue`/`send`/`consume` and related privileges: what clients are allowed to do.

In common Artemis configurations, auto-create is enabled by default for supported protocols/clients. **Do not apply this assumption to every broker or every environment**: organizations may disable the feature or restrict it via address patterns and ACLs.

### 9.2. Broker configuration example

**Illustrative** configuration snippet inside Artemis's `broker.xml`, which must be placed in the right XML section per the broker schema and version:

~~~xml
<!-- Disable auto-create for critical production namespace. -->
<address-settings>
  <address-setting match="prod.orders.#">
    <auto-create-addresses>false</auto-create-addresses>
    <auto-create-queues>false</auto-create-queues>
  </address-setting>
</address-settings>
~~~

Meanwhile, resources are proactively managed:

~~~xml
<addresses>
  <address name="prod.orders.incoming">
    <anycast>
      <queue name="prod.orders.incoming" durable="true"/>
    </anycast>
  </address>
</addresses>
~~~

These two snippets are **parts of a broker configuration**, not a complete `broker.xml` file; integrate them according to your schema, security settings, and current deployment. After provisioning, verify in the broker console/management tool that the address and queue exist with the right routing and permissions.

**Key takeaway:** Disabling auto-create **does not disable** `DynamicDestinationResolver` on the Spring side. It only changes whether the broker allocates a queue/address when a client uses a non-existent destination.

### 9.3. If a queue is missing when auto-create is disabled, what happens?

Depending on the provider and policy, the producer may receive an exception, send to an address with no matching queue/subscription, or the message may not be routed to the intended consumer. Some clients validate early, while others validate late. Do not write a unit test asserting that an exception occurs **immediately at `createQueue()`** unless you have verified that the actual provider behaves that way.

Measure using two groups of signals:

1. **Application**: send success/failure, listener startup, metrics, and logs.
2. **Broker**: address/queue existence, routing type, queue message count, consumer count, routing failures, DLQ.

A "send successful" log entry is not enough to prove that all subscribers/workers have processed the message.

## 10. Complete demo: Spring Boot 3.5, Java 17, Artemis

This example demonstrates Spring resolving the name `"lesson.orders.incoming"` to a **Queue** and sending a message to a consumer. The broker runs in Docker with the default auto-create policy for ease of learning; a later section explains how to replace this with proactive provisioning.

### 10.1. Prerequisites

- JDK 17+, Maven 3.9+, and Docker.
- Ports `61616` (messaging) and `8161` (management console) available.
- No other application reading the demo queue.
- This is a demo on a dedicated broker; do not run it against production.

Start the Artemis broker using the official image:

~~~bash
docker run --detach --name resolver-artemis \
  -p 61616:61616 -p 8161:8161 --rm apache/artemis:latest-alpine
~~~

Once the broker is ready, the console is usually at `http://localhost:8161`. The official image provides default username/password `artemis` for demos. You can watch startup with:

~~~bash
docker logs resolver-artemis
~~~

### 10.2. Project structure

~~~text
dynamic-resolver-demo/
├── pom.xml
└── src/main/
    ├── java/example/DynamicResolverDemoApplication.java
    └── resources/application.properties
~~~

`pom.xml`:

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
  <artifactId>dynamic-resolver-demo</artifactId>
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

`src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

These credentials are for local practice only. For real deployments, place secrets into a secure configuration mechanism.

### 10.3. Complete Java source

Create `src/main/java/example/DynamicResolverDemoApplication.java`:

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.DynamicDestinationResolver;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class DynamicResolverDemoApplication {

    private static final String QUEUE = "lesson.orders.incoming";

    public static void main(String[] args) {
        SpringApplication.run(DynamicResolverDemoApplication.class, args);
    }

    @Bean
    JmsTemplate demoJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(new DynamicDestinationResolver());
        template.setPubSubDomain(false); // Queue
        return template;
    }

    @Bean
    DefaultJmsListenerContainerFactory demoListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setDestinationResolver(new DynamicDestinationResolver());
        factory.setPubSubDomain(false); // Same Queue type as producer
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    ApplicationRunner publish(JmsTemplate demoJmsTemplate) {
        return args -> {
            demoJmsTemplate.convertAndSend(QUEUE, "order-42");
            System.out.println("Sent to: " + QUEUE);
        };
    }

    @Component
    public static class OrderListener {
        @JmsListener(destination = QUEUE,
                containerFactory = "demoListenerFactory")
        public void onMessage(String payload) {
            System.out.println("Received: " + payload);
        }
    }
}
~~~

**Why does this example work?**

- The `spring-boot-starter-artemis` dependency includes JMS client/provider integration and Spring JMS.
- Boot creates `ConnectionFactory` pointing to Artemis from properties.
- `JmsTemplate` is explicitly defined with `DynamicDestinationResolver`. When sending by String, the resolver uses `Session.createQueue("lesson.orders.incoming")`.
- The listener factory uses the same Queue type and name to create the consumer.
- Artemis with auto-create enabled can create the address/queue on client demand if the resource does not yet exist. With other broker configurations, you must pre-provision it.
- `setSessionTransacted(true)` applies a local JMS transaction to the listener; it **does not turn the resolver into a transaction manager**.
- The listener receives a `String` converted from `TextMessage` by the message converter.

### 10.4. Run

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

With a fresh broker and no other consumers, the application prints two business lines roughly like:

~~~text
Sent to: lesson.orders.incoming
Received: order-42
~~~

**The order of the two lines is not guaranteed**, because the listener runs on a container thread and may process the message before or after the publisher prints "Sent". The console also includes Spring Boot/Artemis logs. If the queue exists from a previous run and still holds messages, results may differ; use a dedicated broker/queue to avoid interference.

Open the Artemis management console and check in reality:

1. Does the `lesson.orders.incoming` address/queue exist?
2. What routing type does the queue have? Does it match the JMS Queue model?
3. Did the producer send, is the consumer active, and did it receive the message?
4. Did the message count return to 0 after the listener processed it successfully (assuming no extra traffic), or are messages stuck?
5. Does the broker report that the resource was auto-created or pre-provisioned?

These checks verify **broker state**, completely distinct from merely seeing `DynamicDestinationResolver` return an object.

Finish the test:

~~~bash
docker stop resolver-artemis
~~~

The container was started with `--rm` so it will be removed on stop; **do not use this configuration for long-term message storage**.

### 10.5. Contrast experiment: disable auto-create

To observe physical limits:

- On a dedicated test broker, disable `auto-create-addresses` and `auto-create-queues` for the `lesson.#` namespace.
- Confirm that the `lesson.orders.incoming` queue **does not exist**, then try running the app: depending on the broker/client, the listener may fail to start, sending may fail, or messages may not route as expected.
- Provision the appropriate address/queue via broker CLI/admin/config and verify send/consume permissions.
- Re-run the app: the Java code is **unchanged**, yet because the broker resource is ready, sending and receiving succeed.

The lesson lies not in a specific exception name, but in how the same `DynamicDestinationResolver` can yield **two different infrastructure outcomes** depending on provisioning policy.

## 11. When to allocate dynamically, when to pre-administer?

| Scenario | Recommended choice | Needs verification |
|---|---|---|
| Local demo, short-lived test container | Auto-create can be enabled on a dedicated broker | Isolated namespace, clean up after tests, do not expose ports to untrusted networks. |
| Fixed production queue for jobs/commands | Provision via broker config or IaC; app uses managed name | Durability, ACL, DLQ, routing, quota, monitoring, backup. |
| Event topic shared across multiple services | Provision address/topic and configure subscriptions before publishing if durable is needed | Consumer semantics, missing subscribers, TTL, and retention. |
| Each tenant needs its own queue | Only allow creation via a bounded control plane with quotas | Tenant isolation, naming, lifecycle, permissions, cardinality. |
| JMS destination managed by app server | `JndiDestinationResolver`/inject `Destination` | JNDI naming, broker binding, permissions, caching behavior. |
| Temporary request-reply | `TemporaryQueue/TemporaryTopic` or appropriate request-reply pattern | Connection lifecycle, reply timeout, cleanup. |
| Destination name comes from user input | Server-side allowlist/mapping; never pass raw input straight to `convertAndSend` | Resource abuse, ACL bypass, spelling errors, and "ghost queues". |

### 11.1. A wrong name can become a "junk queue"

If the broker has auto-create enabled, a typo like `orders.incomming` (extra `m`) can create a new queue. The producer sends "successfully" while the listener listens on `orders.incoming` and receives nothing. On the dashboard two different queues appear, one of which just piles up messages. If the same mistake repeats with names generated from UUIDs/request parameters, the broker can bloat with addresses/queues.

### 11.2. Creating one queue per request is not a default strategy

Every resource carries metadata, journal/binding state, consumers, metrics, and management overhead. With thousands or millions of runtime names, even if a provider supports auto-create, it is not sustainable. Prefer sharing a queue with message properties such as `tenantId`/`requestId` when isolation requirements allow, or a control plane that creates queues with quotas, TTL, and cleanup.

### 11.3. When does auto-delete cause data loss?

With brokers that have policies to auto-delete queues/addresses when no consumers remain, misconfiguration can leave unconsumed messages or non-durable subscriptions with nowhere to persist. Deletion rules typically consider message count, consumer count, delay, and resource type; verify actual behavior rather than inferring from the word "dynamic".

## 12. Blocking arbitrary dynamic names with a custom resolver

You can write a wrapper around `DynamicDestinationResolver` to **allow only approved Queue names**. This is a **client-side** control mechanism; broker ACLs and provisioning are still required.

~~~java
package example;

import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import java.util.Set;
import org.springframework.jms.support.destination.DestinationResolver;
import org.springframework.jms.support.destination.DynamicDestinationResolver;

public final class ApprovedQueueResolver implements DestinationResolver {

    private static final Set<String> APPROVED = Set.of(
            "orders.incoming",
            "orders.failed"
    );

    private final DynamicDestinationResolver delegate =
            new DynamicDestinationResolver();

    @Override
    public Destination resolveDestinationName(
            Session session, String name, boolean pubSubDomain)
            throws JMSException {

        if (pubSubDomain) {
            throw new IllegalArgumentException(
                    "This resolver only supports JMS Queues");
        }
        if (!APPROVED.contains(name)) {
            throw new IllegalArgumentException(
                    "Destination is not approved: " + name);
        }
        return delegate.resolveDestinationName(session, name, false);
    }
}
~~~

This is a **complete Java class file**; the filename must be `ApprovedQueueResolver.java` and it requires `spring-jms` and Jakarta Messaging dependencies on the classpath. It is not yet a standalone application with `main` or a broker.

Configure the template:

~~~java
// Inside a @Bean method or initialization configuration.
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDestinationResolver(new ApprovedQueueResolver());
template.setPubSubDomain(false);
~~~

When passing `"orders.incoming"`, the resolver checks the whitelist and then calls the JMS API. With `"orders.incomming"`, an error occurs **before using an unapproved name to send a message**. That catches typos in the app, yet **does not** prove the queue is provisioned.

**Do not rely solely on a client resolver to prevent unauthorized access.** Another service or client not using that resolver can still connect; the broker must enforce permissions by principal, address/queue, and action.

### 12.1. Policies you can place in a custom resolver

- Map logical name `"order-command"` → broker name `"prod.orders.commands.v1"`, decoupling domain from environment.
- Validate namespace and whitelist before calling JMS.
- Reject Queue/Topic mismatches based on module configuration.
- Log logical name and resolved name for auditing.
- Use JNDI or a trusted registry instead of deriving names from input.

Do not turn `DestinationResolver` into heavy provisioning code that calls HTTP admin APIs on every `send` or causes uncontrolled side effects. Provisioning belongs in deployment/control-plane layers, separating the long lifecycle of broker resources from the short lifecycle of JMS operations.

## 13. Lifecycle and ownership of dynamic destinations

A destination on the client and a physical resource on the broker have **different lifecycles**:

~~~text
App start ─► creates JMS Connection/Session
                └─ resolver is called (when using name)
                   └─ Destination Java object is used in send/receive

Broker start/provision ─► creates address/queue/topic with ACL, routing, DLQ
                            └─ persists until removed by admin/policy

App stop ─► closes connection/session
                └─ does NOT imply all queues used by the app will be deleted
~~~

`DynamicDestinationResolver` has no `deleteDestination()` contract, does not manage leases, does not count actual queues, has no broker quotas, and does not know whether a resource is used by another service. Having the application shut down while broker resources remain is normal in durable messaging.

If an organization truly needs dynamic queues:

1. A control plane reviews the name, type, and requester.
2. Provision on the broker via administrative tooling (or auto-create with strict ACLs + quotas).
3. Record a registry containing owner, tenant, creation time, and expiration time.
4. Inform applications to use the exact provisioned name.
5. Monitor consumer/message counts, depth, DLQ, and resource usage.
6. Clean up only after proving no consumers, messages, or business retention rules remain.

## 14. Diagnosing common errors

### Symptom 1 — `createQueue` succeeds without error, but `send` fails

Possible causes: broker disallows auto-create, queue not provisioned, ACL lacks send permission, wrong routing. Start with the broker's address/queue list and JMS provider logs; do not claim the resolver created the resource.

### Symptom 2 — `convertAndSend` returns successfully, but listener stays silent

Check *correct broker and vhost/cluster*, Queue vs Topic domain, typos, running consumers, queue depth, subscriptions, TTL, and routing. Do not use "send did not throw an exception" as proof that the consumer received it.

### Symptom 3 — Hundreds of unwanted queues appear

Check whether runtime names directly concatenate `tenantId`, `requestId`, timestamps, UUIDs, or HTTP request input. Check auto-create policy and namespaces. Block at ingress with mapping/allowlists; restrict creation permissions, quotas, and cleanup on the broker.

### Symptom 4 — Topic "loses" events while consumer is offline

Not a resolver bug. Non-durable subscribers have no guarantee of receiving messages sent before connecting; configure durable subscriptions with proper identity and broker policy. Do not use `JmsTemplate`'s default queue to mimic a topic just because the string contains `.events`.

### Symptom 5 — Works in dev, production reports invalid destination

Dev may have auto-create enabled while production disables it for governance. Check deployment provisioning and permissions; do not "fix" it by unconditionally enabling fallback or JMS auto-create if organizational policy requires managed resources.

### Symptom 6 — JNDI lookup fails even though the broker has the queue

The JNDI registry and broker resources are two separate naming systems. Having a physical queue does not automatically create a JNDI binding. Check the configured JNDI context, lookup name, and `JndiDestinationResolver.setFallbackToDynamicDestination(...)`.

### Symptom 7 — Using the same name for Queue and Topic

`DynamicDestinationResolver` chooses based on `pubSubDomain`, not the name. Separate namespaces or template/listener factory beans, or return a pre-typed `Destination`. Never change `pubSubDomain` on a singleton template per message.

### Symptom 8 — Queue disappears after stopping the listener

The broker may have auto-delete enabled when there are no consumers and the queue is empty. Read broker settings and deletion event evidence; do not blame `DynamicDestinationResolver`. Temporary queues (`TemporaryQueue`) have an entirely different lifecycle.

## 15. Safe deployment checklist

Before taking a Spring JMS service to production:

1. **Destination catalog:** define the list of logical names, broker names, Queue/Topic types, owners, and environments.
2. **Resolver strategy:** lock in `DynamicDestinationResolver`, JNDI, or custom mapping; prevent an application from silently falling back to dynamic.
3. **Provisioning:** decide whether resources are pre-created via IaC/admin or broker auto-create is permitted; know specifically where addresses/queues/subscriptions are created.
4. **Permissions:** grant principals only `send`/`consume` and create permission only if genuinely needed; isolate permissions by namespace/tenant.
5. **Durability:** queue policies, retention/expiry, DLQ, auto-delete, backup, HA, and quotas must be defined on the broker side.
6. **Type:** producer and consumer agree on `pubSubDomain`, names, routing, and subscription type.
7. **Validation:** never pass raw user strings into destination names; enforce whitelists/prefixes/length limits and cardinality bounds.
8. **Observability:** broker exposes metrics for address/queue counts, queue depth, message rates, unrouted messages, active consumers, and DLQ; app logs resolved names and errors.
9. **Deployment test:** test both existing and missing resources, auto-create on/off, missing permissions, and name typos.
10. **Lifecycle:** establish a resource deletion process and avoid deleting queues with remaining messages/consumers; do not delegate this job to Spring's resolver.

## 16. Self-check questions

**1. Does `DynamicDestinationResolver.resolveDestinationName(session, "orders", false)` succeeding prove the broker created the `orders` queue?** No. It only proves the resolver could return a `Destination` object in the JMS client.

**2. What does `pubSubDomain=true` do?** The resolver chooses `Session.createTopic(name)` instead of `createQueue(name)`. It does not change the type of an existing resource on the broker.

**3. Does disabling `auto-create-queues` prevent Spring from calling `session.createQueue`?** Not necessarily. Creating the reference object and broker provisioning policy are two separate responsibilities. Actual errors may appear at send or consumer startup.

**4. Are dynamic destinations and TemporaryQueue the same?** No. Dynamic uses a name chosen by the application; temporary is created ad hoc by the JMS API and has a lifecycle tied to the connection.

**5. Why might the same code run locally yet fail in production?** The broker differs in auto-create policy, ACLs, provisioning, or destination type—not solely because of Java code.

**6. What does `JndiDestinationResolver.setFallbackToDynamicDestination(false)` mean?** If the JNDI lookup finds no resource, do not silently fall back to creating a destination reference dynamically; useful for controlled naming policies.

**7. What are the risks of using userId/UUID as a per-request queue name?** Resource explosion, leaked queues, hard-to-manage ACLs, high metric cardinality, unconsumed queues, wasted storage.

**8. Is a Topic listener started after the producer sends guaranteed to receive old events?** No. Non-durable subscriptions generally do not receive history from before they became active; design subscriptions and retention appropriately.

**9. When `JmsTemplate.convertAndSend(...)` succeeds, what else must be checked?** Broker routing/queue, consumer depth, delivery/ack, and logs. Success on the producer side does not prove the business consumer processed it successfully.

**10. What mechanism ensures a physical queue has the right DLQ and quota?** Broker provisioning/configuration/administration (or auto-create with controlled policies), not `DynamicDestinationResolver` itself.

## 17. Official references

- [Spring Framework — Using Spring JMS / Destination Management](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): describes `JmsTemplate`, default `DynamicDestinationResolver`, `JndiDestinationResolver`, and how physical destinations depend on the provider.
- [Spring Framework — DynamicDestinationResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/DynamicDestinationResolver.html): `resolveDestinationName`, `resolveQueue`, `resolveTopic`.
- [Spring Framework — JndiDestinationResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html): JNDI lookup, cache, and fallback.
- [Jakarta Messaging API — Session](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/session): `createQueue`/`createTopic` only create reference objects, not physical provisioning.
- [Spring Boot — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): configuring `spring-boot-starter-artemis`, `ConnectionFactory`, and JMS auto-configuration.
- [Apache ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): address, queue, ANYCAST/MULTICAST.
- [Apache ActiveMQ Artemis — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html): `auto-create-queues`/`auto-create-addresses` and auto-delete policy.
- [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): broker image used in the examples.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): `JmsTemplate`, `@JmsListener`, and Spring JMS configuration.

**Key takeaway:** `DynamicDestinationResolver` converts **String → JMS Destination object**, while the **broker + operational policies** determine **whether the physical destination exists, how it is created, what permissions apply, how long messages are retained, and when it is deleted**. Those two responsibilities must be designed and verified independently.
