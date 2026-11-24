# DestinationResolver, DynamicDestinationResolver, and JndiDestinationResolver

## Learning Objectives

After this lesson, you will be able to:

- Explain why Spring JMS needs a mechanism to convert a destination name into a JMS `Destination` object.
- Describe the `DestinationResolver` contract and how `JmsTemplate` uses the resolver.
- Distinguish `DynamicDestinationResolver` from `JndiDestinationResolver`.
- Choose `Queue` or `Topic` properly through `pubSubDomain`.
- Configure the JNDI environment, caching, and fallback to dynamic destinations.
- Understand the limitations of dynamic destination creation and the difference between regular destinations and temporary destinations.
- Identify errors caused by wrong JNDI names, mismatched Queue/Topic types, stale caches, or differences across JMS providers.
- Write configuration and tests for resolvers without confusing Spring JMS's `DestinationResolver` with the identically named interface in Spring Messaging.

## 1. Why Must Destinations Be Resolved?

JMS sends and receives messages through a `Destination` object. In practice, business code typically knows only logical names such as:

- `orders.in`: queue receiving order creation commands.
- `orders.events`: topic publishing order events.
- `tenant.42.notifications`: per-tenant destination determined at runtime.
- `java:comp/env/jms/OrdersQueue`: JNDI name of an environment-administered destination.

An API like `JmsTemplate` can accept a destination name as a `String`. However, the JMS provider requires an actual `Queue` or `Topic` object to create a `MessageProducer` or `MessageConsumer`. Spring must convert the `String` name into a `Destination` object before executing the JMS operation.

That is the responsibility of `DestinationResolver`.

~~~mermaid
flowchart LR
    A["Destination name<br/>String"]
    B["DestinationResolver"]
    C["JMS Destination"]
    D["JmsTemplate"]
    E["JMS provider"]

    A --> B --> C
    D --> B
    C --> D
    D --> E
~~~

The resolver decouples destination naming from send/receive code. An application can switch from dynamic resolution to JNDI via configuration without altering every business call.

## 2. DestinationResolver in Spring JMS

The interface to use resides in package:

~~~java
org.springframework.jms.support.destination.DestinationResolver
~~~

This is a strategy interface in the Spring JMS module, belonging to the `spring-jms` artifact. It has a single method:

~~~java
Destination resolveDestinationName(
        Session session,
        String destinationName,
        boolean pubSubDomain
) throws JMSException;
~~~

Meaning of the parameters:

- **session:** the current JMS `Session` used by the send/receive operation. Dynamic resolvers need the `Session` to invoke APIs for creating or obtaining a `Queue`/`Topic`.
- **destinationName:** logical name of the destination to resolve.
- **pubSubDomain:** `false` means Point-to-Point, so the resolver needs a `Queue`; `true` means Publish/Subscribe, so the resolver needs a `Topic`.

The return value is a `jakarta.jms.Destination` object, usually a `Queue` or `Topic`. If resolution fails, the resolver may throw `JMSException` or `DestinationResolutionException`.

`DestinationResolver` is a functional interface. In theory, an application can implement a resolver with a lambda. However, in most applications, `DynamicDestinationResolver` or `JndiDestinationResolver` covers common needs.

**Package note:** Spring also has an interface named `DestinationResolver` in `org.springframework.messaging.core` for a different messaging abstraction. This lesson covers `org.springframework.jms.support.destination.DestinationResolver`, used with Jakarta JMS, `Session`, and `JmsTemplate`. When importing, check the package to avoid mixing up the two identically named interfaces.

## 3. How Does JmsTemplate Use DestinationResolver?

`JmsTemplate` lets you call methods that take a destination name:

~~~java
jmsTemplate.convertAndSend("orders.in", payload);
~~~

In this call, `JmsTemplate` needs a `DestinationResolver` to convert `orders.in` into a `Queue` or `Topic` object. The resolver is configured on `JmsDestinationAccessor`, the parent class of `JmsTemplate`.

Key APIs:

~~~java
jmsTemplate.setDestinationResolver(destinationResolver);
DestinationResolver resolver = jmsTemplate.getDestinationResolver();
~~~

In Spring Framework 6.2, `JmsTemplate` uses `DynamicDestinationResolver` by default. It can be replaced with `JndiDestinationResolver` or an application-defined implementation.

If a `Destination` object is passed directly to the corresponding overload, the application already has the destination and does not need name resolution for that operation:

~~~java
jmsTemplate.convertAndSend(queueObject, payload);
~~~

When using an overload that accepts a `String`, the resolver is involved.

### 3.1. Queue and Topic are selected via pubSubDomain

`JmsTemplate` has the `pubSubDomain` property:

~~~java
jmsTemplate.setPubSubDomain(false); // Queue, default
jmsTemplate.setPubSubDomain(true);  // Topic
~~~

The default is `false`, meaning the Point-to-Point domain and `Queue`. This property is especially important when the resolver must create a dynamic destination, because it determines whether the `Queue` or `Topic` creation API is called.

Example:

~~~java
// Resolver receives pubSubDomain=false and resolves to a Queue.
queueTemplate.convertAndSend("orders.in", payload);

// Resolver receives pubSubDomain=true and resolves to a Topic.
topicTemplate.convertAndSend("orders.events", event);
~~~

A single `JmsTemplate` holds one `pubSubDomain` value at a time. If an application sends to both `Queue` and `Topic` using `String` names, the clean approach is to configure two separate templates for the two domains. If `Queue`/`Topic` objects are already available, you can use the overloads accepting `Destination` to specify the target type explicitly.

Do not assume the resolver can infer `Queue` or `Topic` from name suffixes like `.queue` or `.topic`. The domain choice is passed via the `pubSubDomain` parameter or comes from the `Destination` object itself.

## 4. DynamicDestinationResolver

`DynamicDestinationResolver` is the basic implementation of `DestinationResolver`. It uses the current JMS `Session` to resolve a name into a dynamic destination:

- When `pubSubDomain=false`, calls `Session.createQueue(destinationName)`.
- When `pubSubDomain=true`, calls `Session.createTopic(destinationName)`.

Example:

~~~java
DynamicDestinationResolver resolver = new DynamicDestinationResolver();

Destination queue = resolver.resolveDestinationName(
        session, "orders.in", false
);

Destination topic = resolver.resolveDestinationName(
        session, "orders.events", true
);
~~~

### 4.1. What does dynamic destination mean?

A dynamic destination is a destination referenced by the application via a name known at runtime, rather than retrieving a pre-bound `Destination` object from JNDI.

Crucially, the JMS specification does not standardize how physical destinations are created dynamically. JMS providers usually support calling `createQueue`/`createTopic` to construct a destination object by name, but exact behavior depends on the provider:

- Some providers simply return an object representing the destination with that name.
- Some providers automatically create the physical queue/topic if the destination does not yet exist.
- Some providers require the destination to have been pre-created by an administrator.
- Specific attributes such as durability, retention, partitioning, or policies may have to be configured using provider-specific tools/APIs.

Therefore, calling `DynamicDestinationResolver` does not guarantee that the broker will automatically create a new physical queue/topic. Check your provider's documentation and destination administration policies.

### 4.2. A dynamic destination is not a temporary destination

These two concepts are distinct:

| Type | How it is created | Lifecycle |
|---|---|---|
| Dynamic destination | Resolves a name via `createQueue`/`createTopic` per provider | Name follows application convention; physical lifecycle depends on provider |
| `TemporaryQueue`/`TemporaryTopic` | Calls `Session.createTemporaryQueue`/`createTemporaryTopic` | Usually bound to the `Connection` that created it and deleted when the connection closes |
| JNDI destination | Looks up an object already bound in the naming service | Lifecycle is administered by the environment/provider |

`DynamicDestinationResolver` does not call `createTemporaryQueue` or `createTemporaryTopic`. Do not use this resolver if your goal is creating a temporary destination scoped to a single request-reply session.

### 4.3. When should DynamicDestinationResolver be used?

Use this default resolver when:

- Destination names are determined at runtime following an agreed naming convention.
- The JMS provider supports the corresponding dynamic destination resolution.
- The application does not need to look up destinations from JNDI.
- The `Queue`/`Topic` model is clearly configured via `pubSubDomain`.

It is simple and requires no JNDI configuration. However, if the system requires centralized destination administration, access permissions, policies, or provider-specific attributes, consider JNDI or a specialized resolver.

## 5. JndiDestinationResolver

`JndiDestinationResolver` is a `DestinationResolver` implementation that uses JNDI. Instead of calling `Session.createQueue`/`createTopic` to resolve a name, it treats `destinationName` as a name to look up in JNDI.

Examples of JNDI names typically look like:

~~~text
java:comp/env/jms/OrdersQueue
java:comp/env/jms/OrderEventsTopic
~~~

The actual name depends on the application server, JMS provider, and naming context configuration.

The resolver performs these core tasks:

1. Uses the configured JNDI environment/`JndiTemplate` to look up the name.
2. Retrieves the `Destination` object bound in the naming service.
3. Checks whether the destination type matches the expected domain.
4. Optionally caches the result for reuse.
5. If enabled, optionally falls back to a `DynamicDestinationResolver` when JNDI lookup fails.

JNDI lookup does not create bindings by itself. The `Queue` or `Topic` must be provisioned and bound in the JMS/JNDI environment beforehand, unless the application enables dynamic fallback and the provider supports it.

### 5.1. Fallback to dynamic destination

By default, `fallbackToDynamicDestination=false`. If the JNDI lookup does not find the destination, the resolver reports a resolution error.

Fallback can be enabled:

~~~java
JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setFallbackToDynamicDestination(true);
resolver.setDynamicDestinationResolver(
        new DynamicDestinationResolver()
);
~~~

When enabled, the flow is:

~~~mermaid
flowchart TD
    A["Receive destinationName"]
    B["JNDI Lookup"]
    C{"Destination found?"}
    D["Verify Queue/Topic type"]
    E["Return Destination"]
    F{"Dynamic fallback enabled?"}
    G["DynamicDestinationResolver"]
    H["Throw resolution error"]

    A --> B --> C
    C -->|Yes| D --> E
    C -->|No| F
    F -->|Yes| G --> E
    F -->|No| H
~~~

Fallback fits when an application has a set of destinations administered in JNDI along with some dynamic destinations per tenant or business convention. Enable it only when the provider and governance policy permit dynamic destination creation/resolution.

If fallback is enabled, remember that a typo in a JNDI name can also be routed into dynamic resolution. This can mask configuration errors and create unintended destinations if the provider auto-creates physical destinations.

### 5.2. Configuring the JNDI environment

`JndiDestinationResolver` inherits configuration capabilities from Spring's JNDI support. You can supply environment properties such as:

- `Context.INITIAL_CONTEXT_FACTORY`: the `InitialContextFactory` class provided by the provider or application server.
- `Context.PROVIDER_URL`: the URL of the naming service if required by the environment.
- Other security or provider-specific properties.

Java configuration example:

~~~java
Properties jndiEnvironment = new Properties();
jndiEnvironment.setProperty(
        Context.INITIAL_CONTEXT_FACTORY,
        initialContextFactory
);
jndiEnvironment.setProperty(
        Context.PROVIDER_URL,
        providerUrl
);

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setJndiEnvironment(jndiEnvironment);
resolver.setFallbackToDynamicDestination(false);
~~~

The two variables `initialContextFactory` and `providerUrl` must come from the environment's actual configuration. There is no universal value across all application servers or JMS providers.

If the application runs inside a Jakarta EE container, the naming context may already be supplied by the container. In that case, you may only need to use JNDI names following container conventions and environment-appropriate configuration.

## 6. Caching in JndiDestinationResolver

`JndiDestinationResolver` implements `CachingDestinationResolver`. By default, caching is enabled.

Cache management APIs:

~~~java
resolver.setCache(true);
resolver.setCache(false);

resolver.removeFromCache("orders.in");
resolver.clearCache();
~~~

Meaning:

- **cache=true:** stores resolved destinations for reuse, avoiding repeated lookups.
- **cache=false:** performs a fresh lookup on every operation; useful in certain development environments or when destinations must support hot restarts.
- **removeFromCache(name):** removes a single destination from the cache if cached.
- **clearCache():** clears the entire cache.

If accessing a destination fails and there is reason to believe the cached object has become invalid, you can evict that name from the cache and retry according to the application's recovery policy. Do not automatically clear the cache and retry infinitely, as the failure may stem from access permissions, a broker outage, or misconfiguration.

### 6.1. Queue and Topic names must be unique when caching

`JndiDestinationResolver` caches dynamic queues and topics by destination name. Because the cache key is based on the name, the Javadoc requires distinct names across `Queue` and `Topic`.

For example, do not reuse the same name `orders` for both:

- Queue `orders`
- Topic `orders`

Choose clear names such as `orders.queue` and `orders.topic`, or a separate namespace convention. This prevents a cache entry created for one domain from being reused in the context of the other domain.

### 6.2. Caching and broker configuration changes

If an administrator replaces a destination or rebinds JNDI while the application is running, the resolver may continue returning the cached object. Depending on the provider, the old object might remain valid or become stale.

Have a clear procedure for destination changes:

1. Change/bind the destination in the administrative environment.
2. Determine whether the cache needs refreshing.
3. Call `removeFromCache` or `clearCache` when necessary.
4. Monitor resolution errors and send errors to confirm the new destination works.

Setting `cache=false` can let development environments see changes faster, at the cost of more lookups. In production, choose based on destination lifecycle and actual lookup cost.

## 7. Configuring JmsTemplate with Each Resolver

### 7.1. Using the default DynamicDestinationResolver

If no resolver is configured, Spring Framework 6.2's `JmsTemplate` uses `DynamicDestinationResolver`.

It can be written explicitly:

~~~java
JmsTemplate queueTemplate = new JmsTemplate(connectionFactory);
queueTemplate.setDestinationResolver(
        new DynamicDestinationResolver()
);
queueTemplate.setPubSubDomain(false);

queueTemplate.convertAndSend("orders.in", payload);
~~~

To use a `Topic`:

~~~java
JmsTemplate topicTemplate = new JmsTemplate(connectionFactory);
topicTemplate.setDestinationResolver(
        new DynamicDestinationResolver()
);
topicTemplate.setPubSubDomain(true);

topicTemplate.convertAndSend("orders.events", event);
~~~

### 7.2. Using JndiDestinationResolver

~~~java
JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setJndiEnvironment(jndiEnvironment);
resolver.setCache(true);
resolver.setFallbackToDynamicDestination(false);

JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setDestinationResolver(resolver);
jmsTemplate.setPubSubDomain(false);

jmsTemplate.convertAndSend(
        "java:comp/env/jms/OrdersQueue",
        payload
);
~~~

In the example, `JmsTemplate` requests a `Queue` because `pubSubDomain=false`. `JndiDestinationResolver` looks up the JNDI name and verifies that the returned destination matches `Queue`.

If the JNDI destination is a `Topic`, configure the template with `pubSubDomain=true` or use a separate `JmsTemplate` for `Topic`.

### 7.3. Registering the resolver in the Spring container

In a Spring application, configure the resolver as a bean and inject it into `JmsTemplate`:

~~~java
@Configuration
public class JmsConfiguration {

    @Bean
    public DestinationResolver destinationResolver(
            Properties jndiEnvironment) {

        JndiDestinationResolver resolver =
                new JndiDestinationResolver();

        resolver.setJndiEnvironment(jndiEnvironment);
        resolver.setCache(true);
        resolver.setFallbackToDynamicDestination(false);

        return resolver;
    }

    @Bean
    public JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            DestinationResolver destinationResolver) {

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(destinationResolver);
        template.setPubSubDomain(false);
        return template;
    }
}
~~~

The `Properties` bean `jndiEnvironment` in the example must be supplied by application configuration. If using `DynamicDestinationResolver`, you can omit the JNDI environment and use the default implementation.

`JmsTemplate` should be fully configured before being shared across services. Once configured, the template can be injected and used concurrently per Spring's thread-safe design.

## 8. Runnable Java 17 Example: Testing DynamicDestinationResolver

The following example checks that the resolver calls the right JMS `Session` API for `Queue` and `Topic`. Mockito creates a mock `Session`, allowing resolution logic to be tested without running a real broker.

This example verifies how Spring chooses `createQueue`/`createTopic`. It does not test whether a provider auto-creates physical destinations; that behavior depends on the actual broker.

### 8.1. Maven configuration

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>destination-resolver-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <version>5.14.2</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.2. Complete program

Create `src/main/java/demo/DestinationResolverDemo.java`:

~~~java
package demo;

import jakarta.jms.Destination;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.Topic;

import org.springframework.jms.support.destination.DynamicDestinationResolver;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

public class DestinationResolverDemo {

    public static void main(String[] args) throws Exception {
        Session session = mock(Session.class);

        Queue ordersQueue = mock(Queue.class);
        Topic orderEventsTopic = mock(Topic.class);

        when(session.createQueue("orders.in"))
                .thenReturn(ordersQueue);

        when(session.createTopic("orders.events"))
                .thenReturn(orderEventsTopic);

        DynamicDestinationResolver resolver =
                new DynamicDestinationResolver();

        Destination resolvedQueue = resolver.resolveDestinationName(
                session,
                "orders.in",
                false
        );

        Destination resolvedTopic = resolver.resolveDestinationName(
                session,
                "orders.events",
                true
        );

        System.out.println("queueResolved=" + (resolvedQueue == ordersQueue));
        System.out.println(
                "topicResolved=" + (resolvedTopic == orderEventsTopic)
        );
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.DestinationResolverDemo
~~~

Stdout:

~~~text
queueResolved=true
topicResolved=true
~~~

### 8.3. Analyzing the output

The first call passes `pubSubDomain=false`, so `DynamicDestinationResolver` calls `session.createQueue("orders.in")`. Mockito returns `ordersQueue`; the resolved result is that exact object.

The second call passes `pubSubDomain=true`, so the resolver calls `session.createTopic("orders.events")`. The result is `orderEventsTopic`.

The example confirms the Queue/Topic selection rule inside the resolver. When running with a real JMS provider, `Session` and `Destination` are supplied by the provider; the provider decides whether a dynamic name corresponds to an automatically created physical destination.

## 9. Writing a Custom DestinationResolver When Custom Rules Are Needed

If the application's destination naming conventions are complex, you can implement the interface yourself:

~~~java
DestinationResolver resolver = (session, name, pubSubDomain) -> {
    if (name.startsWith("tenant.")) {
        return pubSubDomain
                ? session.createTopic(name)
                : session.createQueue(name);
    }

    throw new DestinationResolutionException(
            "Unsupported destination name: " + name
    );
};
~~~

This example only accepts names starting with `tenant.`. In a real application, a custom resolver can:

- Map logical names to physical names by tenant or environment.
- Validate against an allowlist of destinations.
- Select a namespace by business category.
- Call an internal registry to locate the `Destination`.
- Add caching or metrics per custom conventions.

Do not place critical authorization logic solely inside the resolver. The resolver is responsible for mapping a name to a `Destination`; publish/consume permissions must still be enforced at the broker and at the application boundary.

## 10. Common Pitfalls and How to Handle Them

### 10.1. Confusing a logical name with a JNDI name

A name like `orders.in` can be a dynamic destination name. A name like `java:comp/env/jms/OrdersQueue` is typically a JNDI name. When using `JndiDestinationResolver`, supply the exact name bound in the naming service.

### 10.2. Enabling fallback to mask JNDI errors

If dynamic fallback is enabled, a typo in a JNDI name can cause the resolver to try a dynamic destination. This can allow the application to keep running while sending to an unintended destination. Enable fallback only when that behavior is intentional.

### 10.3. Forgetting pubSubDomain

`DynamicDestinationResolver` needs to know whether to create a `Queue` or `Topic`. The default is `Queue`. If a name belongs to a `Topic` while the template still has `pubSubDomain=false`, the resolver will request a `Queue` and the provider may fail or create the wrong destination depending on provider configuration.

### 10.4. Reusing the same name for Queue and Topic

With `JndiDestinationResolver` caching, `Queue` and `Topic` names must be unique across both domains. Use clear namespaces to avoid cache key collisions and configuration confusion.

### 10.5. Assuming createQueue/createTopic always creates physical destinations

JMS does not standardize dynamic physical destination creation. Providers may require destinations to be pre-created by an administrator. Verify broker behavior before relying on dynamic resolution in production.

### 10.6. Confusing dynamic with temporary destinations

Dynamic destinations use application-chosen names. `TemporaryQueue`/`TemporaryTopic` have a lifecycle tied to the `Connection`. If you need a temporary reply queue, use the temporary destination API or an appropriate request-reply API.

### 10.7. Cache holding a stale destination

When JNDI bindings or broker destinations change, the cache may still hold an old object. Use `removeFromCache`/`clearCache` when you know a destination has become invalid; avoid infinite retries.

### 10.8. Ignoring resolution errors

`DestinationResolutionException` typically signals an error in converting a name to a `Destination`. Check the name, JNDI binding, lookup permissions, Queue/Topic domain, and provider. Distinguish this error from errors sending a `Message` after the destination has already been resolved.

### 10.9. Confusing the two DestinationResolver interfaces

Always verify imports. This lesson uses `org.springframework.jms.support.destination.DestinationResolver`; the interface in `org.springframework.messaging.core` belongs to a different abstraction and does not accept a Jakarta JMS `Session`.

### 10.10. Creating a new resolver for every operation

If the resolver caches results, creating a new instance each time defeats caching. Configure one resolver bean and inject it into a shared `JmsTemplate` at initialization.

## 11. Which Resolver Should You Choose?

| Requirement | Suitable resolver | Reason |
|---|---|---|
| Destination is determined by name at runtime and provider supports dynamic lookup | `DynamicDestinationResolver` | Uses `Session.createQueue`/`createTopic` |
| Destination is administered and bound in JNDI | `JndiDestinationResolver` | Looks up names in the naming service |
| Combining JNDI destinations with controlled dynamic fallback | `JndiDestinationResolver` | Enable fallback and configure the fallback resolver |
| Destination is a Spring bean | `BeanFactoryDestinationResolver` | Finds `Destination` from the Spring `BeanFactory` |
| Want custom name-mapping rules | Custom `DestinationResolver` | Full control over lookup, namespace, or policy |

To choose correctly, answer three questions: who administers the destination, when is the name known, and does the provider support dynamic destinations?

If destinations are already declared statically in the application, you can inject `Queue`/`Topic` beans or JNDI objects directly instead of resolving a `String` on every operation. When names are only known at runtime, a resolver keeps business code independent of how destinations are located.

## 12. Self-Check Questions

1. Which package contains Spring JMS's `DestinationResolver`?
2. What three parameters does `resolveDestinationName` accept?
3. Why does `JmsTemplate` need a resolver when APIs accept a `String` destination name?
4. Under what conditions does `DynamicDestinationResolver` call `Session.createQueue` vs `createTopic`?
5. Is `pubSubDomain` `true` or `false` by default?
6. Does a dynamic destination always cause the broker to create a physical queue/topic?
7. Where does `JndiDestinationResolver` look up destinations?
8. Is fallback to dynamic destinations enabled by default?
9. Is caching in `JndiDestinationResolver` enabled or disabled by default?
10. Why must `Queue` and `Topic` names be unique when caching?
11. How do you remove a single destination from the cache?
12. How does a dynamic destination differ from a `TemporaryQueue` in lifecycle?
13. When should you use two separate `JmsTemplate` instances for `Queue` and `Topic`?
14. Is `DestinationResolver` in `org.springframework.messaging.core` the same as the JMS interface covered here?

## 13. Conclusion

`DestinationResolver` is Spring JMS's strategy for converting a `String` name into a Jakarta JMS `Destination` object. `JmsTemplate` uses the resolver whenever send/receive operations are invoked with a destination name.

`DynamicDestinationResolver` uses `Session.createQueue`/`createTopic` and is the default implementation in Spring Framework 6.2. It fits when destination names are determined at runtime and the JMS provider supports dynamic resolution. `JndiDestinationResolver` looks up destinations bound in JNDI, supports caching, and can fall back to a dynamic resolver when explicitly enabled.

Configure `pubSubDomain` accurately for `Queue` or `Topic`, manage the cache in line with destination lifecycles, and verify JMS provider behavior before relying on dynamic destination creation. A resolver only resolves a name into a `Destination`; it does not provision brokers, configure durability, or grant access permissions.

## Official References

- Spring Framework 6.2 — Using Spring JMS, Destination Management: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- DestinationResolver API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html
- DynamicDestinationResolver API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/DynamicDestinationResolver.html
- JndiDestinationResolver API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html
- JmsDestinationAccessor API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/JmsDestinationAccessor.html
- JmsTemplate API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Jakarta Messaging specification: https://jakarta.ee/specifications/messaging/
