# Default Destination and Resolving Destination Names with DestinationResolver in Spring Messaging

## 1. Destinations in the Send and Receive Model

In Spring Messaging, a message is sent to a **destination**. A destination is the target object that a template uses for sending, receiving, or request-reply exchanges. The data type of the destination depends on the implementation: with GenericMessagingTemplate, the destination is a MessageChannel; with a JMS integration template, the destination can be a JMS Destination object.

Spring separates two ways of specifying a target:

1. **Passing the destination directly:** the caller already has the target object and passes it to the send/convertAndSend method.
2. **Passing a destination name:** the caller passes a String name; the template uses a DestinationResolver to look up the corresponding target object.

Additionally, a template can be configured with a **default destination** so that methods that do not take a destination parameter know where to send or receive.

Three concepts to distinguish:

- **Default destination:** the default target object stored on the template.
- **Destination name:** the string name passed by the caller, for example "ordersChannel".
- **DestinationResolver<D>:** a strategy for converting a String name into a destination object of type D.

Default destination and DestinationResolver solve two different needs. Default destination serves calls that omit a destination; the resolver serves calls that supply a destination name.

## 2. Default Destination in MessageSendingOperations

Spring defines MessageSendingOperations<D> for message-sending operations. Methods can accept a destination directly or use the default destination:

~~~java
template.send(destination, message);
template.send(message);

template.convertAndSend(destination, payload);
template.convertAndSend(payload);
~~~

Methods with a destination parameter use the passed object. Methods without a destination parameter use the default destination configured on the template.

The base class AbstractMessageSendingTemplate<D> provides:

- setDefaultDestination(D destination): sets the default destination.
- getDefaultDestination(): retrieves the configured destination.
- getRequiredDefaultDestination(): retrieves the required destination; throws IllegalStateException if not set.

Conceptual example:

~~~java
template.setDefaultDestination(ordersChannel);

// Send directly to the default destination.
template.convertAndSend("order-created");

// Send to another explicitly specified destination.
template.convertAndSend(paymentsChannel, "payment-request");
~~~

If no default destination is configured and you call a method without a destination parameter, the template will fail because it does not know where to send. You should not rely on an implicit destination that is not declared in configuration.

### 2.1. Default Destination of GenericMessagingTemplate

GenericMessagingTemplate extends AbstractDestinationResolvingMessagingTemplate<MessageChannel>. Because the template's type D is MessageChannel, its default destination is **a MessageChannel instance**, not a String channel name.

~~~java
MessageChannel ordersChannel = ...;

GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setDefaultDestination(ordersChannel);

template.convertAndSend("order-created");
~~~

Here, "order-created" is the payload. The template sends the payload to the MessageChannel configured as the default destination.

If you want to specify a channel by bean name, use the overload taking a String name:

~~~java
template.convertAndSend("ordersChannel", "order-created");
~~~

This method goes through DestinationResolver; it does not read the default destination as a substitute for name resolution.

## 3. What Is DestinationResolver<D>?

DestinationResolver<D> is a functional interface in the org.springframework.messaging.core package. It defines one method:

~~~java
D resolveDestination(String name);
~~~

The resolver's job is to convert a String name into an actual destination object of type D. For GenericMessagingTemplate, D is MessageChannel.

Simple mapping example:

~~~java
DestinationResolver<MessageChannel> resolver = name -> {
    if ("orders".equals(name)) {
        return ordersChannel;
    }
    throw new DestinationResolutionException(
        "Unknown destination: " + name
    );
};
~~~

A resolver must return a non-null destination. If the name does not exist or cannot be resolved, the implementation should throw DestinationResolutionException with enough details for diagnosis.

The resolver does not define how messages are sent. It only resolves the name into the target object; the template then invokes send/receive on the resolved destination.

### 3.1. AbstractDestinationResolvingMessagingTemplate

AbstractDestinationResolvingMessagingTemplate<D> extends AbstractMessagingTemplate<D> and adds operations that accept String destination names, for example:

~~~java
template.send("orders", message);
template.convertAndSend("orders", payload);
template.receive("orders");
template.sendAndReceive("orders", requestMessage);
~~~

The template must be configured with a DestinationResolver via setDestinationResolver(...). If no resolver is set, methods requiring name resolution will throw IllegalArgumentException. If the resolver cannot find the name, the resolution failure is typically represented by DestinationResolutionException.

This class does not provide a default resolver by itself. The concrete implementation or application configuration must supply an appropriate strategy.

## 4. GenericMessagingTemplate and BeanFactoryMessageChannelDestinationResolver

GenericMessagingTemplate is a general-purpose template for sending, receiving, and request-reply over MessageChannel. It supports both destination objects and destination names.

GenericMessagingTemplate implements BeanFactoryAware. When managed by Spring and given a BeanFactory, setBeanFactory(...) configures BeanFactoryMessageChannelDestinationResolver as the resolver.

BeanFactoryMessageChannelDestinationResolver interprets a destination name as **the bean name of a MessageChannel** and looks up that bean in the BeanFactory.

Spring configuration example:

~~~java
@Configuration
class MessagingConfig {

    @Bean
    MessageChannel ordersChannel() {
        return new ExecutorSubscribableChannel();
    }

    @Bean
    GenericMessagingTemplate messagingTemplate(
            ConfigurableListableBeanFactory beanFactory,
            MessageChannel ordersChannel) {

        GenericMessagingTemplate template = new GenericMessagingTemplate();
        template.setBeanFactory(beanFactory);
        template.setDefaultDestination(ordersChannel);
        return template;
    }
}
~~~

With this configuration:

- Calling template.convertAndSend("ordersChannel", payload) looks up the MessageChannel bean named ordersChannel.
- Calling template.convertAndSend(payload) sends to the ordersChannel instance set as the default destination.
- Calling template.convertAndSend(otherChannel, payload) sends directly to the passed channel.

The bean name must match and the bean must be a usable MessageChannel. This resolver is a BeanFactory bean lookup mechanism; it does not automatically create a new channel just because a name does not exist yet.

### 4.1. Manual Template Instantiation

If you instantiate GenericMessagingTemplate directly with new and no Spring container invokes setBeanFactory, the resolver is not configured automatically.

You can set the resolver directly:

~~~java
DefaultListableBeanFactory beanFactory = new DefaultListableBeanFactory();

beanFactory.registerSingleton("ordersChannel", ordersChannel);

GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setDestinationResolver(
    new BeanFactoryMessageChannelDestinationResolver(beanFactory)
);
~~~

Or call template.setBeanFactory(beanFactory), because GenericMessagingTemplate creates BeanFactoryMessageChannelDestinationResolver automatically when it receives a BeanFactory.

Distinguish two things:

- setDefaultDestination(ordersChannel): configures the default target as an object.
- setDestinationResolver(...): configures how to look up a destination from a String name.

Both can be configured on the same template.

## 5. Writing a Custom DestinationResolver

When destinations are not beans in a BeanFactory, you can write a resolver following application rules. For example, mapping aliases to channels via a Map:

~~~java
Map<String, MessageChannel> channels = Map.of(
    "orders", ordersChannel,
    "payments", paymentsChannel
);

DestinationResolver<MessageChannel> resolver = name -> {
    MessageChannel channel = channels.get(name);

    if (channel == null) {
        throw new DestinationResolutionException(
            "Destination not found: " + name
        );
    }

    return channel;
};

GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setDestinationResolver(resolver);

template.convertAndSend("orders", "order-created");
template.convertAndSend("payments", "payment-request");
~~~

A resolver can use a registry, tenant configuration, metadata, or another lookup service. However, do not allow a client-supplied destination string to arbitrarily select internal channels. Validate the name, check authorization, and restrict the list of allowed destinations.

### 5.1. Distinguishing Valid Names and Resolution Errors

You should define clear behavior when a destination is not found:

~~~java
DestinationResolver<MessageChannel> resolver = name -> {
    MessageChannel channel = channels.get(name);

    if (channel == null) {
        throw new DestinationResolutionException(
            "Unknown messaging destination: " + name
        );
    }

    return channel;
};
~~~

Do not return null to represent an invalid name. Under the DestinationResolver contract, the resolved result must be an actual, non-null destination. The error should mention the logical name being looked up to make logging and configuration troubleshooting easier, while avoiding putting secrets into error messages.

## 6. Caching Resolution Results

If resolution is expensive, such as looking up an external registry, you can use CachingDestinationResolverProxy<D>. This class wraps another DestinationResolver and caches successful resolveDestination(name) results.

~~~java
DestinationResolver<MessageChannel> targetResolver = name -> {
    // Look up from a registry or configuration system.
    return channelRegistry.lookup(name);
};

CachingDestinationResolverProxy<MessageChannel> cachedResolver =
    new CachingDestinationResolverProxy<>(targetResolver);

GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setDestinationResolver(cachedResolver);
~~~

Caching is useful when resolution results are stable and lookups are costly. If mappings change frequently, the cache may retain stale references; design appropriate cache lifecycle, invalidation capabilities, and resolver refresh timing. Do not use caching as a way to hide configuration errors or revoked destinations.

## 7. Processing Flow When Sending to a Destination Name

When calling:

~~~java
template.convertAndSend("orders", payload);
~~~

General flow:

1. The template receives the String destinationName "orders".
2. The template calls DestinationResolver.resolveDestination("orders").
3. The resolver returns a destination, for example ordersChannel.
4. The template converts the payload into a Message using MessageConverter.
5. The template sends the Message to the resolved destination.

If no resolver is configured, name-based calls cannot proceed. If the name does not exist, the resolver throws DestinationResolutionException. If resolution succeeds but the channel rejects or fails to send, the error raised during the send step belongs to the corresponding messaging/delivery error category.

Key point: the resolver only decides **which destination object corresponds to the name**. It does not decide how the payload is converted, which consumer processes the message, or whether the message is persisted durably.

## 8. Standalone Runnable Java 17+ Example

The following example simultaneously demonstrates three cases: bean name resolution, sending to a default destination, and using a custom resolver. The channel uses ExecutorSubscribableChannel with synchronous dispatch under the default configuration.

**Project structure**

~~~text
destination-resolver-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          DestinationResolverDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>destination-resolver-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-beans</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/DestinationResolverDemo.java**

~~~java
package demo;

import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.core.DestinationResolutionException;
import org.springframework.messaging.core.DestinationResolver;
import org.springframework.messaging.core.GenericMessagingTemplate;
import org.springframework.messaging.support.ExecutorSubscribableChannel;

public class DestinationResolverDemo {

    public static void main(String[] args) {
        SubscribableChannel ordersChannel = new ExecutorSubscribableChannel();
        ordersChannel.subscribe(message ->
            System.out.println("received=" + message.getPayload())
        );

        DefaultListableBeanFactory beanFactory = new DefaultListableBeanFactory();
        beanFactory.registerSingleton("ordersChannel", ordersChannel);

        GenericMessagingTemplate template = new GenericMessagingTemplate();
        template.setBeanFactory(beanFactory);
        template.setDefaultDestination((MessageChannel) ordersChannel);

        template.convertAndSend("ordersChannel", "by-name");
        template.convertAndSend("default-destination");

        DestinationResolver<MessageChannel> customResolver = name -> {
            if ("orders".equals(name)) {
                return ordersChannel;
            }

            throw new DestinationResolutionException(
                "Unknown destination: " + name
            );
        };

        GenericMessagingTemplate customTemplate = new GenericMessagingTemplate();
        customTemplate.setDestinationResolver(customResolver);
        customTemplate.setDefaultDestination((MessageChannel) ordersChannel);

        customTemplate.convertAndSend("orders", "custom");

        try {
            customTemplate.convertAndSend("missing", "not-sent");
        }
        catch (DestinationResolutionException ex) {
            System.out.println("missingDestination=failed");
        }
    }
}
~~~

Run from the destination-resolver-demo directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.DestinationResolverDemo
~~~

**stdout**

~~~text
received=by-name
received=default-destination
received=custom
missingDestination=failed
~~~

Explanation:

- The first send resolves the bean name ordersChannel using BeanFactoryMessageChannelDestinationResolver.
- The second send does not pass a destination name, so the template uses the default destination.
- customTemplate uses a custom resolver that maps the alias orders.
- The name missing causes DestinationResolutionException and the message is not sent.

## 9. Common Mistakes

1. **Confusing default destination with destination name:** default destination is an object of type D; for GenericMessagingTemplate, that is a MessageChannel. A String name requires a resolver.
2. **Forgetting to configure default destination:** send/convertAndSend methods without a destination parameter will fail if no default has been set.
3. **Forgetting to configure a resolver:** methods accepting a String destinationName require a resolver. A Spring-managed GenericMessagingTemplate receives a resolver via BeanFactoryAware; manual instantiation requires explicit configuration.
4. **Registering the wrong bean name:** BeanFactoryMessageChannelDestinationResolver looks up the exact MessageChannel bean name. A wrong name or wrong type will fail to resolve.
5. **Assuming the resolver creates channels automatically:** a resolver may look up or map depending on implementation. BeanFactoryMessageChannelDestinationResolver looks up already-registered beans.
6. **Returning null:** the contract requires a non-null destination. Throw DestinationResolutionException when not found.
7. **Using default destination as a fallback for every invalid name:** calls with a name go through the resolver. Invalid names must raise an error; do not silently route to the default because that can corrupt business flows.
8. **Not validating client-provided destinations:** destination names can affect routing. Validate and authorize before resolving.
9. **Caching dynamic mappings without invalidation:** CachingDestinationResolverProxy is suitable when results are stable; if the registry changes, the cache may hold stale destinations.
10. **Confusing Spring Messaging's resolver with Spring JMS's resolver:** packages and generic types differ. Check imports to use the right abstraction for the destination type you are working with.

## 10. When to Use Each Approach?

| Need | Approach |
|---|---|
| Application always sends to one primary channel | setDefaultDestination(channel) |
| Caller already knows the channel object | send(channel, message) or convertAndSend(channel, payload) |
| Caller only knows the channel bean name | GenericMessagingTemplate + BeanFactoryMessageChannelDestinationResolver |
| Need aliases or custom routing rules | Custom DestinationResolver<MessageChannel> |
| Destination lookup is expensive and results are stable | CachingDestinationResolverProxy |
| Need to send to a destination name with no default resolver | Configure setDestinationResolver(...) before calling |

## 11. Conclusion

Default destination lets a template send or receive when the caller does not specify a target. DestinationResolver lets the caller use a String name and let the template look up the corresponding destination object. In GenericMessagingTemplate, the destination is a MessageChannel; BeanFactoryMessageChannelDestinationResolver looks up channels by bean name in a BeanFactory.

Configure a default destination for default send flows, configure a resolver for name-based calls, and handle unresolvable errors explicitly. If destinations vary by tenant, permissions, or client-supplied data, validate names before use to avoid misrouting or exposing unauthorized channels.

## 12. References

- [MessageSendingOperations — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/MessageSendingOperations.html)
- [AbstractMessageSendingTemplate — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/AbstractMessageSendingTemplate.html)
- [DestinationResolver — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/DestinationResolver.html)
- [AbstractDestinationResolvingMessagingTemplate — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/AbstractDestinationResolvingMessagingTemplate.html)
- [GenericMessagingTemplate — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html)
- [BeanFactoryMessageChannelDestinationResolver — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/BeanFactoryMessageChannelDestinationResolver.html)
- [CachingDestinationResolverProxy — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/CachingDestinationResolverProxy.html)