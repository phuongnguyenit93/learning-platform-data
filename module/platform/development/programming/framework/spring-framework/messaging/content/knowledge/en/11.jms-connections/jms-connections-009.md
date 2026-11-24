# Distinguishing Destination Resolution from Broker Physical Resource Creation

## Objectives

In Spring JMS, applications often pass a destination name such as `orders.in` or `orders.events` to `JmsTemplate` or a listener container. Spring must convert that name into a JMS `Destination` object to send or receive messages. This work is called **destination resolution**.

Creating the physical Queue or Topic on the broker is a separate task. It may require an administrator, broker configuration, management commands, or a provider management API. Understanding both steps helps avoid errors such as "Spring found the destination object, yet the broker reports the queue does not exist."

After this lesson, you will be able to:

- Distinguish between a destination name, a JMS `Destination` object, and a physical resource on the broker.
- Explain what `Session.createQueue()` and `Session.createTopic()` actually do.
- Understand the roles of `DestinationResolver`, `DynamicDestinationResolver`, `SimpleDestinationResolver`, and `JndiDestinationResolver`.
- Configure `JmsTemplate` and listener containers to look up destinations.
- Determine when the broker auto-creates a destination and when pre-provisioning is required.
- Diagnose JNDI, Queue/Topic mismatch, cache, and broker permission errors.

## 1. Four Concepts to Keep Separate

An application may encounter four things sharing the same name, sitting at different layers:

| Concept | Example | Meaning |
|---|---|---|
| Destination name | `orders.in` | String name the application uses to refer to a Queue or Topic |
| JMS Destination object | `Queue` or `Topic` | Java object representing the destination under the Jakarta Messaging contract |
| Physical resource on broker | Queue `orders.in` declared on the broker | Where the broker actually stores, routes, and manages messages |
| Administered object in JNDI | `java:comp/env/jms/OrdersIn` | Lookup name in a JNDI registry pointing to an administered/configured JMS Destination |

Typical flow:

~~~text
Destination name in the application
        |
        v
Spring DestinationResolver
        |
        v
JMS Destination object (Queue / Topic)
        |
        v
JMS provider / broker handles send or receive operation
        |
        v
Physical resource on the broker
~~~

JNDI is another path to obtain a `Destination` object: the application looks up a registered administered object. Performing a JNDI lookup also does not automatically provision a physical Queue or Topic on the broker.

## 2. A Destination Object Is Not the Same as a Physical Resource

Jakarta Messaging defines `Session.createQueue(String)` and `Session.createTopic(String)` to create a `Queue` or `Topic` object wrapping a provider-specific name.

Example:

~~~java
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.Topic;

Queue queue = session.createQueue("orders.in");
Topic topic = session.createTopic("orders.events");
~~~

These two calls create JMS objects representing the Queue/Topic name. According to the Jakarta Messaging specification, they **do not create a physical Queue or Topic on the broker**. The specification also provides no standard API to create physical resources, because provisioning depends on the JMS provider.

Typically, physical resources are created via one of these ways:

- Broker management console.
- Broker CLI commands.
- Management/JMX/REST APIs provided by the broker.
- Configuration files or Infrastructure as Code declarations.
- Administration tools of the JMS/Jakarta EE platform.

There is one exception to keep in mind: `Session.createTemporaryQueue()` and `Session.createTemporaryTopic()` create temporary destinations tied to the provider's connection/session lifecycle. These are dedicated APIs for temporary resources, distinct from `createQueue(name)` and `createTopic(name)`.

### 2.1. Why does calling createQueue sometimes make a Queue appear on the broker?

Some JMS providers offer an **auto-create destination** feature. When a client sends to or registers a consumer on a name that does not yet exist, the broker can automatically create the physical resource according to provider policy.

That is broker-specific behavior, not a portable guarantee of Jakarta Messaging. For example:

- A broker may enable auto-create for Queues while disabling it for Topics.
- A broker may allow auto-create only within a specific namespace.
- Auto-created resources may receive default settings for durability, TTL, dead-lettering, size limits, or access permissions.
- Production environments often disable auto-create to prevent typos from creating unintended destinations.

Therefore, when a Queue appears after `session.createQueue("orders.in")`, check the broker's auto-create policy. Do not conclude that the JMS method provisioned a physical resource by specification.

## 3. DestinationResolver in Spring JMS

Spring provides the `org.springframework.jms.support.destination.DestinationResolver` interface to convert a `String` name into a JMS `Destination` object.

Core method:

~~~java
Destination resolveDestinationName(
    Session session,
    String destinationName,
    boolean pubSubDomain
) throws JMSException;
~~~

Parameter meanings:

- `session`: the current JMS `Session`, used when the resolver needs to invoke provider APIs.
- `destinationName`: the destination name passed by the application.
- `pubSubDomain`: `false` means Queue/point-to-point; `true` means Topic/publish-subscribe.

Classes such as `JmsTemplate` and listener containers use the resolver when given a destination name as a `String`. If the application passes a `Destination` object directly, it already has the target object and skips that name resolution step.

Two ways to send:

~~~java
// Spring resolves the String name into a Destination.
jmsTemplate.convertAndSend("orders.in", payload);

// The application already has a Destination object, passing it directly.
jmsTemplate.convertAndSend(ordersQueue, payload);
~~~

`DestinationResolver` is not a broker administration API. Its main job is to supply the right JMS object for the send/receive operation.

## 4. DynamicDestinationResolver and SimpleDestinationResolver

### 4.1. DynamicDestinationResolver

`DynamicDestinationResolver` resolves names via the JMS `Session`:

- If `pubSubDomain=false`, calls `Session.createQueue(destinationName)`.
- If `pubSubDomain=true`, calls `Session.createTopic(destinationName)`.

This resolver performs no JNDI lookup. It asks the JMS provider to create a `Destination` object for the given name. Whether the broker creates a physical resource when the destination is used remains up to the provider.

This resolver performs a fresh resolution on every call. It is useful when fresh resolution is required or when `Destination` objects depend on the `Session` in a provider-specific way.

### 4.2. SimpleDestinationResolver

`SimpleDestinationResolver` extends `DynamicDestinationResolver` and caches `Queue`/`Topic` objects by destination name. It fits providers whose `Destination` objects are stable and independent of individual `Session` lifecycles.

According to the Spring Framework API Javadocs:

- Spring Framework 6.2 uses `DynamicDestinationResolver` as the default resolver.
- Starting in Spring Framework 7.0, `SimpleDestinationResolver` is the default resolver for `JmsTemplate` and listener containers.

If fresh resolution on every call is needed in Spring 7, you can explicitly configure `DynamicDestinationResolver`.

Example:

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.DynamicDestinationResolver;
import org.springframework.jms.support.destination.SimpleDestinationResolver;

JmsTemplate template = new JmsTemplate(connectionFactory);

// Spring 7: default resolver that caches Destination objects.
template.setDestinationResolver(new SimpleDestinationResolver());

// Use only when fresh resolution is desired on every call.
template.setDestinationResolver(new DynamicDestinationResolver());
~~~

Both resolvers above rely on a JMS `Session` to construct `Queue`/`Topic` objects. They do not replace administrative actions to create physical resources on the broker.

## 5. JndiDestinationResolver: Looking Up Administered Objects

In enterprise environments, Queues/Topics are often pre-administered and registered in JNDI. Applications use JNDI names to obtain configured `Destination` objects.

Example JNDI names:

~~~text
java:comp/env/jms/OrdersIn
java:comp/env/jms/OrdersEvents
~~~

`JndiDestinationResolver` looks up the destination name as a JNDI location. It fits when:

- Destinations are pre-configured by an administrator or application server.
- The application must use the exact declared resource with pre-set policies and permissions.
- JNDI names are managed separately from code.
- You want to avoid dynamically creating destinations on lookup name mistakes.

Fallback to dynamic resolution is disabled by default. You can keep that behavior explicit:

~~~java
import org.springframework.jms.support.destination.JndiDestinationResolver;

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setFallbackToDynamicDestination(false);
~~~

If fallback is enabled:

~~~java
resolver.setFallbackToDynamicDestination(true);
~~~

when a JNDI lookup does not find the name, the resolver can fall back to dynamic resolution. That can be handy in development environments, but it can also hide typos or missing configuration in production.

A JNDI lookup returns a registered `Destination` object. The lookup operation itself does not create a physical Queue/Topic. Resource creation and configuration still belong to the broker or administration platform.

## 6. Common Resolvers

| Resolver | How it obtains the Destination object | Does it auto-provision physical resources? |
|---|---|---|
| `DynamicDestinationResolver` | Calls `Session.createQueue`/`createTopic` by name | Not by specification; provider may auto-create on use |
| `SimpleDestinationResolver` | Same as above, while caching objects by name | Not by specification; provider may auto-create on use |
| `JndiDestinationResolver` | Looks up name in JNDI; dynamic fallback is optional and off by default | No; JNDI lookup does not provision the broker |
| `BeanFactoryDestinationResolver` | Looks up a `Destination` bean in the Spring `BeanFactory` | No; the bean must be provided beforehand |

Another option is to inject `Queue`/`Topic` beans or JNDI objects directly into the application. Then, the application can pass the `Destination` object straight to `JmsTemplate`.

## 7. Configuring JmsTemplate with Administered Destinations

Example configuring a template using the JNDI resolver:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;

@Configuration
public class JmsConfiguration {

    @Bean
    JndiDestinationResolver destinationResolver() {
        var resolver = new JndiDestinationResolver();
        resolver.setFallbackToDynamicDestination(false);
        return resolver;
    }

    @Bean
    JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            JndiDestinationResolver destinationResolver) {
        var template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(destinationResolver);
        template.setPubSubDomain(false); // Queue domain
        return template;
    }
}
~~~

Sending using the JNDI name:

~~~java
jmsTemplate.convertAndSend(
    "java:comp/env/jms/OrdersIn",
    new OrderCreated("order-42")
);
~~~

The example above assumes the JNDI context is already configured and the administered object `java:comp/env/jms/OrdersIn` is registered. It does not create the Queue on the broker.

If the application uses a `Topic`, configure `pubSubDomain=true` or use a separate template for `Topic`. The resolver must return the exact `Destination` type requested by the operation.

## 8. Configuring a Resolver for Listener Containers

Listener containers must also resolve destination names. If `@JmsListener` uses a JNDI name, configure the resolver on the corresponding factory:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.destination.DestinationResolver;

@Configuration
public class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            DestinationResolver destinationResolver) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setDestinationResolver(destinationResolver);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Listener:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(
        destination = "java:comp/env/jms/OrdersIn",
        containerFactory = "jmsListenerContainerFactory"
    )
    public void handle(OrderCreated event) {
        // Process event.
    }
}
~~~

The destination name is looked up by the resolver when the listener container initializes or sets up its consumers. If the JNDI name is wrong, the context is unreachable, or the object is the wrong type, the listener may fail to start.

## 9. Provisioning Physical Resources on the Broker

Physical resources must be created using the tools and syntax of the broker in use. A typical production workflow includes:

1. Identify Queue vs Topic, physical name, and namespace.
2. Declare the resource via management console, CLI, management API, or Infrastructure as Code.
3. Configure properties such as durability, routing, TTL/expiry, maximum size, dead-letter address/queue, and redelivery policy if supported by the broker.
4. Grant send, consume, browse, or manage permissions to application accounts.
5. If the application looks up via JNDI, register an administered object pointing to the provisioned resource.
6. Configure Spring to use the JNDI resolver or injected `Destination` objects.
7. Verify connectivity, permissions, and send/receive capability with a smoke test.
8. Monitor message counts, consumers, capacity, dead-letter queues, and destination health on the broker.

There is no single command to create a physical Queue/Topic across all JMS providers. The same Jakarta Messaging API can be implemented by different brokers, each with its own administration commands and policies.

### 9.1. Example of auto-create policy

Suppose code sends to the name `orders.in`:

~~~java
jmsTemplate.convertAndSend("orders.in", payload);
~~~

There are three possibilities:

- The Queue already exists: the broker routes the message to that Queue if the application has permission.
- The Queue does not exist and auto-create is enabled: the broker may create the Queue using default settings or its policy.
- The Queue does not exist and auto-create is disabled: the send operation or consumer creation may fail, depending on the provider and when validation occurs.

All three outcomes can start from the exact same Java call. Therefore, reading Spring code alone is not enough to know whether a physical resource exists or gets created; you must check the broker configuration and administrative state.

## 10. Distinguishing Error Types

| Symptom | Layer at fault | How to check |
|---|---|---|
| JNDI name not found | JNDI lookup | Context factory, namespace, binding name, and lookup permissions |
| Cannot resolve Queue/Topic name | `DestinationResolver` | Name, `pubSubDomain`, `Destination` type, and configured resolver |
| Resolver returns object, yet send fails because destination does not exist | Broker provisioning or auto-create policy | Check physical resources and broker logs |
| Access denied on send/consume | Broker authorization | ACL/roles for the destination and `ConnectionFactory` principal |
| Consumer does not receive messages | Destination, selector, subscription, or routing | Queue/topic name, selector, subscription, and bindings |
| Works locally but fails in production | Broker policy differences | Auto-create, JNDI bindings, namespaces, and permissions between environments |
| Stale Destination object after broker change | Resolver cache or provider object | Check cache; clear cache or reinitialize resolver per supported API |

An important diagnostic point: **a successful resolver call does not prove the broker has provisioned the destination**. The resolver may simply create an object holding a name. Errors only surface when the provider executes the send, creates a consumer, or checks permissions.

## 11. Caching and Destination Object Lifecycle

Caching resolvers should be used appropriately for the provider:

- `SimpleDestinationResolver` caches `Queue`/`Topic` objects by name.
- `JndiDestinationResolver` caches lookup results by default.
- `JndiDestinationResolver.setCache(false)` forces a fresh lookup every time.
- Resolvers implementing `CachingDestinationResolver` may expose `clearCache()` or `removeFromCache(name)`.

Caching avoids repeatedly creating or looking up objects. However, if the broker or JNDI binding changes, cached objects may no longer be valid. When encountering errors after destination changes, inspect the cache and the provider object's lifecycle.

Do not disable caching by default just to avoid errors. Determine whether the provider requires stable `Destination` objects and refresh the cache only with good reason.

## 12. Choosing How to Manage Destinations

| Requirement | Approach |
|---|---|
| Destinations centrally administered in an application server | JNDI + `JndiDestinationResolver` |
| Application wants to use injected `Destination` beans | `BeanFactoryDestinationResolver` or pass objects directly |
| Destination names determined at runtime; broker supports dynamic/auto-create | Dynamic resolution, along with verifying provider policy |
| Need stable objects reused by name on Spring 7 | Default `SimpleDestinationResolver` |
| Need fresh resolution on every call | `DynamicDestinationResolver` |
| Production requires explicit Queue/Topic configuration with policies and ACLs | Provision on the broker first, then look up via JNDI or managed configuration |

In production, pre-provisioning ensures resources have the right policies and access permissions from the start. Auto-create can be useful in local development or ephemeral environments, but must be controlled carefully so typos do not create unintended destinations.

## 13. Common Pitfalls

- **Calling `session.createQueue(name)` and assuming the broker now has a physical Queue:** the standard method only creates a `Queue` object wrapping the name. Provision resources through the broker.
- **Assuming Spring's DynamicDestinationResolver always creates a physical Queue:** the resolver calls the JMS API; whether the broker auto-creates depends on the provider.
- **Treating a JNDI name as the broker's physical name:** JNDI bindings and physical destination names can differ. Look up the exact registered binding.
- **Enabling dynamic fallback in production without control:** wrong JNDI names can fall through to dynamic resolution and mask missing configuration.
- **Using the wrong `pubSubDomain`:** the resolver creates a `Queue` when the application expects a `Topic` or vice versa.
- **Renaming a Queue on the broker while keeping an old resolver cache:** cached objects may need to be refreshed.
- **Thinking declaring a Destination bean in Spring provisions the broker:** the bean only supplies an object to the application; the broker still needs the resource or auto-create enabled.
- **Not checking permissions:** the destination exists, yet the application's principal is not allowed to send or consume.
- **Using dynamic auto-create for critical destinations without policies:** Queues may appear with unsuitable default settings.

## 14. Deployment Checklist

- [ ] Identified logical names in the application and physical names on the broker.
- [ ] Identified whether each destination is a Queue or a Topic.
- [ ] Selected the right resolver: JNDI, bean, simple, or dynamic.
- [ ] Checked the default resolver for the Spring version in use.
- [ ] Understood that `Session.createQueue`/`createTopic` only creates a `Destination` object per specification.
- [ ] Verified whether broker auto-create is enabled or disabled and which policies apply.
- [ ] Pre-provisioned physical resources if required by the broker.
- [ ] Configured administered objects/JNDI bindings if the application uses JNDI.
- [ ] `JmsTemplate` and listener containers use the right resolver and Queue/Topic domain.
- [ ] Granted send/consume/manage permissions under least privilege.
- [ ] Verified TTL, durability, dead-letter, redelivery, and capacity limits.
- [ ] Set up smoke tests and destination health monitoring on the broker.

## 15. References

- [Jakarta Messaging 3.1 — Session.createQueue/createTopic](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.jms/jakarta/jms/session)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework — Using Spring JMS: Destination Management](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — DestinationResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html)
- [Spring Framework — SimpleDestinationResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/SimpleDestinationResolver.html)
- [Spring Framework — DynamicDestinationResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/DynamicDestinationResolver.html)
- [Spring Framework — JndiDestinationResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html)
- [Spring Framework — JmsDestinationAccessor API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/JmsDestinationAccessor.html)
