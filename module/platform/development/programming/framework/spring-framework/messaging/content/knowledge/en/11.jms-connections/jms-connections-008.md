# pubSubDomain and Resolving Queue or Topic

## Objectives

In Spring JMS, the same name such as `orders.in` can be used to refer to either a Queue or a Topic. Spring needs to know which domain the application is operating in to resolve the name into the right type of JMS `Destination`. The `pubSubDomain` property provides that information to `JmsTemplate` and listener containers.

After this lesson, you will be able to:

- Explain how `pubSubDomain` controls destination resolution.
- Know the default value and scope of effect of this property.
- Distinguish resolving a `String` name from passing a `Destination` object directly.
- Configure `JmsTemplate`, `DefaultJmsListenerContainerFactory`, and `@JmsListener` for `Queue` or `Topic`.
- Configure Spring Boot and applications that use both domains simultaneously.
- Identify errors when sender and receiver use mismatched domains.

## 1. Queue and Topic Are Two JMS Domains

Jakarta Messaging defines two common destination types:

- **Queue (point-to-point):** consumers on the same Queue compete for messages; on each delivery, a message is distributed to only one consumer.
- **Topic (publish/subscribe):** each independent subscription receives a copy of messages published to the Topic. Multiple consumers sharing a shared subscription can split the messages of that subscription.

Both `Queue` and `Topic` implement `jakarta.jms.Destination`, but they belong to two different domains. Having the same string name does not make a Queue and a Topic the same target.

Example:

~~~text
Queue domain:
Producer -> orders.in -> one consumer in the group receives each message

Topic domain:
Publisher -> orders.events -> subscription A
                           -> subscription B
                           -> subscription C
Each independent subscription receives a copy.
~~~

Spring JMS needs to pick the right domain when it is given only a `String` destination name. That is the primary role of `pubSubDomain`.

## 2. What Is pubSubDomain?

`pubSubDomain` is a boolean property on `JmsDestinationAccessor`, used by `JmsTemplate` and listener container classes.

| Value | JMS domain | Destination type created during dynamic resolution |
|---|---|---|
| `false` | Point-to-point | Queue |
| `true` | Publish/subscribe | Topic |

The default value is `false`, i.e., the Queue domain.

Configuration on `JmsTemplate`:

~~~java
JmsTemplate queueTemplate = new JmsTemplate(connectionFactory);
queueTemplate.setPubSubDomain(false); // Queue, also the default

JmsTemplate topicTemplate = new JmsTemplate(connectionFactory);
topicTemplate.setPubSubDomain(true);  // Topic
~~~

The property name can easily mislead readers into thinking it enables or disables publish/subscribe features in general. More accurately, it specifies which JMS domain the accessor is using, especially when destinations are resolved dynamically from `String` names.

## 3. How pubSubDomain Participates in Name Resolution

When the application calls a method taking a `String` destination name, Spring uses a `DestinationResolver` to obtain a JMS `Destination` object.

The resolver contract looks like:

~~~java
Destination resolveDestinationName(
    Session session,
    String destinationName,
    boolean pubSubDomain
) throws JMSException;
~~~

The resolver receives three pieces of information:

- `session`: the JMS `Session` used for resolution, if the resolver needs it.
- `destinationName`: the Queue or Topic name.
- `pubSubDomain`: `false` for Queue and `true` for Topic.

With `DynamicDestinationResolver`, Spring performs the equivalent of:

~~~java
if (pubSubDomain) {
    return session.createTopic(destinationName);
}
return session.createQueue(destinationName);
~~~

This is pseudocode illustrating the resolver's decision. `Session.createQueue(name)` and `Session.createTopic(name)` create a JMS object representing the destination name. Under Jakarta Messaging, those two methods do not by themselves provision physical resources on the broker. The broker may create the resource automatically upon use if the provider's auto-create policy allows it.

## 4. Scope of Effect: String Name vs Destination Object

This is the most important point when configuring.

### 4.1. Passing a String name

When passing a `String` name, Spring needs the resolver to create or look up a `Destination` object:

~~~java
// pubSubDomain=false: resolve "orders.in" to a Queue.
queueTemplate.convertAndSend("orders.in", payload);

// pubSubDomain=true: resolve "orders.events" to a Topic.
topicTemplate.convertAndSend("orders.events", event);
~~~

With a dynamic resolver, the `pubSubDomain` value determines whether Spring calls `Session.createQueue` or `Session.createTopic`.

Receive operations using `String` names also need the matching domain:

~~~java
Object queueMessage = queueTemplate.receive("orders.in");
Object topicMessage = topicTemplate.receive("orders.events");
~~~

### 4.2. Passing a Destination object directly

If the application already holds a `Queue` or `Topic` object, it can pass it directly:

~~~java
import jakarta.jms.Queue;
import jakarta.jms.Topic;

import org.springframework.jms.core.JmsTemplate;

public class DestinationObjectExample {
    private final JmsTemplate queueTemplate;
    private final JmsTemplate topicTemplate;
    private final Queue ordersQueue;
    private final Topic ordersTopic;

    public DestinationObjectExample(
            JmsTemplate queueTemplate,
            JmsTemplate topicTemplate,
            Queue ordersQueue,
            Topic ordersTopic) {
        this.queueTemplate = queueTemplate;
        this.topicTemplate = topicTemplate;
        this.ordersQueue = ordersQueue;
        this.ordersTopic = ordersTopic;
    }

    public void publish(Object payload, Object event) {
        queueTemplate.convertAndSend(ordersQueue, payload);
        topicTemplate.convertAndSend(ordersTopic, event);
    }
}
~~~

In this case, the type and value of the `Destination` object itself determine the target. `pubSubDomain` does not turn a `Queue` object into a `Topic` object or vice versa; Spring does not need to resolve a `String` name for overloads accepting an object.

That also means a template configured for the Queue domain can still work with a `Topic` object if the application passes that object directly and the provider supports the operation. However, to keep code readable and prevent confusion, use a template configured for the intended domain.

## 5. Influence of DestinationResolver

`pubSubDomain` only takes effect when the resolver uses domain information to resolve a name. Common resolvers handle this differently.

| Resolver | Resolution approach | Role of pubSubDomain |
|---|---|---|
| `DynamicDestinationResolver` | Calls `Session.createQueue` or `Session.createTopic` | Directly determines Queue or Topic |
| `SimpleDestinationResolver` | Dynamic resolution and caches `Destination` objects by name | Domain is used when creating the object; cache reuses results |
| `JndiDestinationResolver` | Looks up administered objects by JNDI name | Registered object type determines Queue/Topic; flag mainly affects dynamic fallback |
| Custom resolver | Follows application-implemented logic | Must handle the domain parameter per contract if supporting both types |

### 5.1. DynamicDestinationResolver

This resolver resolves names via the JMS `Session`:

- `pubSubDomain=false`: creates a `Queue` object.
- `pubSubDomain=true`: creates a `Topic` object.

It is the right choice when the application uses dynamic names and the provider supports the corresponding resolution.

### 5.2. SimpleDestinationResolver

This resolver builds on dynamic resolution and caches `Destination` objects by name. In newer Spring Framework versions, this is the default resolver on many JMS accessors. Caching lets resolved objects be reused.

When an application uses both a `Queue` and a `Topic` with the same name string, ensure the resolver or cache is used per the right domain and configuration. The straightforward approach is to use distinct names, separate templates, and appropriate resolvers.

### 5.3. JndiDestinationResolver

This resolver looks up an administered object registered in JNDI. Example JNDI names might be:

~~~text
java:comp/env/jms/OrdersQueue
java:comp/env/jms/OrdersTopic
~~~

JNDI lookup returns the registered object. `pubSubDomain` does not convert that object; if the object is a `Queue` it stays a `Queue`, and if it is a `Topic` it stays a `Topic`.

If fallback to dynamic resolution is enabled, the domain flag is used when the resolver must construct a destination by name after a lookup fails. Fallback should generally be configured deliberately to avoid masking JNDI naming mistakes in production.

## 6. Configuring JmsTemplate for Queue and Topic

`JmsTemplate` uses the Queue domain by default. To send to or receive from a `Topic` using a `String` name, set `pubSubDomain=true`.

Example creating two templates:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsTemplateConfiguration {

    @Bean
    JmsTemplate queueJmsTemplate(ConnectionFactory connectionFactory) {
        var template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        return template;
    }

    @Bean
    JmsTemplate topicJmsTemplate(ConnectionFactory connectionFactory) {
        var template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);
        return template;
    }
}
~~~

Usage:

~~~java
queueJmsTemplate.convertAndSend("orders.in", new OrderCreated("order-42"));
topicJmsTemplate.convertAndSend("orders.events", new OrderCreated("order-42"));
~~~

Both templates can share one `ConnectionFactory`, while keeping separate domain configurations makes the intent to send to a Queue or Topic immediately clear to readers.

Do not flip `pubSubDomain` repeatedly on a singleton template while the application is handling concurrent requests. It is a template configuration property. When the application needs both domains, create two beans or pass a `Destination` object of the right type.

## 7. Configuring Listener Containers for Queue and Topic

`@JmsListener` accepts destinations as `String` names. The destination type is determined by the listener container factory used by the endpoint.

`DefaultJmsListenerContainerFactory` has `setPubSubDomain(boolean)`:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory queueListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-6");
        return factory;
    }

    @Bean
    DefaultJmsListenerContainerFactory topicListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Attach the right factory to each listener:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListeners {

    @JmsListener(
        destination = "orders.in",
        containerFactory = "queueListenerFactory"
    )
    public void handleQueueOrder(OrderCreated order) {
        // One consumer in the Queue group processes the message.
    }

    @JmsListener(
        destination = "orders.events",
        containerFactory = "topicListenerFactory"
    )
    public void observeOrderEvent(OrderCreated event) {
        // The listener's subscription receives a copy from the Topic.
    }
}
~~~

If `containerFactory` is omitted, Spring uses the default factory configured for listener endpoints. If that factory is in the Queue domain, a listener with a `String` destination will be resolved in the Queue domain.

The `@JmsListener` annotation itself does not have a `pubSubDomain` attribute. Set the domain on the factory used by the endpoint.

## 8. Spring Boot Configuration

Spring Boot provides the property:

~~~properties
spring.jms.pub-sub-domain=true
~~~

With JMS auto-configuration, this property configures the default domain for the auto-configured `JmsTemplate` and listener container. The default value is `false`, i.e., Queue.

Example using Topic as the default domain:

~~~yaml
spring:
  jms:
    pub-sub-domain: true
~~~

Items to verify:

- Sender and receiver must use the same domain.
- If using a custom `JmsTemplate`, call `setPubSubDomain` explicitly on that bean.
- If creating `DefaultJmsListenerContainerFactory` manually, call `setPubSubDomain` explicitly or configure the factory via the appropriate Boot configurer.
- If the application uses both Queue and Topic, create separate templates and listener factories per domain instead of trying to rely on a single global default.

The Boot property is a default setting for auto-configured infrastructure. It does not turn every Queue into a Topic and does not replace configuration on custom beans.

## 9. What Does pubSubDomain Not Control?

Several other JMS settings can be confused with `pubSubDomain`:

| Setting | Controls | Decided by pubSubDomain? |
|---|---|---|
| Queue/Topic domain | Destination type when resolving names dynamically | Yes |
| Durable subscription | Whether messages are retained for an offline subscriber | No |
| Shared subscription | Whether multiple consumers share one subscription | No |
| Delivery mode | Persistent vs non-persistent messages | No |
| Message selector | Filtering messages by header/property | No |
| `MessageConverter` | Converting between payload and `Message` | No |
| Acknowledgement/transaction | Confirming or rolling back message receipt | No |
| Broker auto-create | Whether the broker automatically creates physical resources | No |

For instance, setting `pubSubDomain=true` only selects the Topic domain when the resolver needs to resolve a name. It does not create a durable subscription. To receive messages while a subscriber is offline, configure a durable subscription and an appropriate provider.

Similarly, `pubSubDomain=true` does not enable persistent delivery. Delivery mode is a separate message-sending policy.

## 10. Errors from Sender and Receiver Using Different Domains

Suppose a producer sends:

~~~java
queueJmsTemplate.convertAndSend("orders.events", event);
~~~

while the listener uses a Topic-domain factory:

~~~java
@JmsListener(
    destination = "orders.events",
    containerFactory = "topicListenerFactory"
)
public void receive(OrderCreated event) {
    // ...
}
~~~

The producer resolved the name as a Queue; the listener resolved the same name as a Topic. Even though the string names match, the two sides may be talking to two different destinations. As a result, the listener does not receive messages from the Queue the producer sent to.

Similar situations:

- Producer configured for Topic while consumer uses Queue.
- Spring Boot property set to Topic while a custom listener factory still uses Queue.
- Listener uses the default factory with the wrong domain.
- JNDI binding points to a Queue while the application expects a Topic.
- A custom `DestinationResolver` ignores the `pubSubDomain` parameter.
- Queue/Topic name is correct, but the broker has not provisioned the resource or the principal lacks permissions.

How to check:

1. Determine whether the sender passes a `String` name or a `Destination` object.
2. Check `pubSubDomain` on the sending template.
3. Identify which `containerFactory` the listener uses.
4. Check `pubSubDomain` on the factory.
5. Check the resolver and the type of `Destination` object it returns.
6. Check physical resources, JNDI bindings, auto-create policy, and broker permissions.

## 11. When an Application Needs Both Queue and Topic

A service may both send commands to a Queue and publish events to a Topic. For example:

- `orders.commands`: workers split command processing.
- `orders.events`: Billing, Analytics, and Notification each have independent subscriptions.

Readable design:

~~~text
Order Service
   | 
   +-- queueJmsTemplate (pubSubDomain=false)
   |       |
   |       v
   |   orders.commands
   |
   +-- topicJmsTemplate (pubSubDomain=true)
           |
           v
       orders.events
           |
           +--> Billing subscription
           +--> Analytics subscription
           +--> Notification subscription
~~~

On the receiving side, create one queue listener factory and one topic listener factory. Name beans to reflect their domain so you do not accidentally pick the wrong factory in `@JmsListener`.

If a Topic requires durable subscriptions, also configure the subscription name, durable flag, and client ID per the JMS provider's requirements. Do not infer durability from `pubSubDomain=true` alone.

## 12. Testing Domain Configuration

Test both sender and receiver against the broker/provider used in production or a compatible embedded broker.

Cases to cover:

- Queue template sends to a Queue and the Queue listener receives the message.
- Topic template publishes and two independent subscriptions both receive a copy.
- A Queue template and Topic listener using the same string name do not cross-deliver messages to each other.
- A listener using the wrong factory is caught in configuration tests.
- JNDI resolver returns the right `Destination` type.
- Custom resolver receives and handles `pubSubDomain` properly.
- Boot configuration and custom factories do not accidentally override the intended domain.

When testing, also inspect active broker destinations or subscriptions. Checking only annotation strings is not enough to prove Spring created the right consumer type.

## 13. Common Pitfalls

- **Thinking `pubSubDomain=true` merely turns on pub/sub features:** it selects the Topic domain during destination resolution.
- **Forgetting the default is false:** `String` names are resolved in the Queue domain.
- **Setting the flag only on JmsTemplate:** listener containers have their own configuration and must also use the right domain.
- **Sharing one template for Queue and Topic and toggling the flag at runtime:** easily causes inconsistent configuration across operations.
- **Assuming `@JmsListener` has a pubSubDomain attribute:** the domain lives on the listener container factory.
- **Assuming the flag converts an existing Destination object:** directly passed objects retain their original Queue or Topic type.
- **Assuming JNDI resolver turns a Queue into a Topic:** JNDI lookup returns the registered administered object.
- **Enabling Topic domain and expecting subscriptions to be durable automatically:** durability is a separate subscription setting.
- **Configuring only the Spring Boot property while overlooking custom factories:** manually created beans need explicit domain configuration.
- **Using the same string name and assuming both sides hit the same destination:** Queue and Topic are two separate domains.

## 14. Deployment Checklist

- [ ] Identified whether each destination needs to be a Queue or a Topic.
- [ ] Aware that `pubSubDomain` defaults to `false`.
- [ ] Verified whether code passes a `String` name or a `Destination` object.
- [ ] If using `String`, verified the resolver receives the right domain value.
- [ ] `JmsTemplate` sender is configured with the right domain.
- [ ] Listener container factory is configured with the right domain.
- [ ] Each `@JmsListener` uses the right `containerFactory`.
- [ ] Spring Boot property matches the application's default domain.
- [ ] Applications using both domains have separate templates/factories.
- [ ] JNDI bindings or custom resolvers return the right `Destination` type.
- [ ] Durable/shared subscriptions are configured separately when needed.
- [ ] Tested sender, receiver, and destination state on the broker.

## 15. References

- [Spring Framework — JmsDestinationAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/JmsDestinationAccessor.html)
- [Spring Framework — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework — DestinationResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html)
- [Spring Framework — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [Spring Framework — @JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
